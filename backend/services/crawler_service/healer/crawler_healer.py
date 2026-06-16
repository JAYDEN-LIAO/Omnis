"""
CrawlerHealer：爬虫自愈引擎（事后分析模式）
在 CrawlerManager._read_output() 检测到子进程退出时调用
"""
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from backend.core.logger import get_logger
from backend.core.circuit_breaker import CircuitBreaker
from backend.core.config import settings

from .error_patterns import classify_error

logger = get_logger("crawler.healer")


class CrawlerHealer:
    def __init__(self, manager):
        self.manager = manager
        self._circuits: Dict[str, CircuitBreaker] = {}
        self._delays: Dict[str, float] = {}
        self._last_failure: Dict[str, float] = {}
        self._init_db()

    # ──────────────── SQLite ────────────────

    def _init_db(self):
        db = Path(__file__).parent.parent.parent.parent.parent / "data" / "crawler_heal.db"
        with sqlite3.connect(str(db)) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS heal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL, error_type TEXT NOT NULL,
                    recovery TEXT NOT NULL, source TEXT DEFAULT 'heuristic',
                    success INTEGER DEFAULT 0, exit_code INTEGER,
                    log_snippet TEXT, created_at TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_heal_platform_created
                ON heal_events(platform, created_at DESC)
            """)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
            conn.commit()
        self._db_path = str(db)

    def _save_event(self, platform: str, error_type: str, recovery: str,
                    source: str, success: bool, exit_code: int, snippet: str):
        with sqlite3.connect(self._db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO heal_events
                (platform, error_type, recovery, source, success, exit_code, log_snippet, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (platform, error_type, recovery, source, int(success), exit_code,
                  snippet[:500], datetime.now().isoformat()))
            conn.commit()

    def get_history(self, platform: str = "", limit: int = 20) -> list:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            if platform:
                c.execute(
                    "SELECT * FROM heal_events WHERE platform=? ORDER BY created_at DESC LIMIT ?",
                    (platform, limit))
            else:
                c.execute(
                    "SELECT * FROM heal_events ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in c.fetchall()]

    # ──────────────── 主入口 ────────────────

    async def analyze_and_recover(self, return_code: int) -> Dict:
        platform = self._current_platform()
        if not platform or return_code == 0:
            return {"action": "none"}

        errors = [log.message for log in self.manager.logs
                  if log.level in ("error", "warning")]
        if not errors:
            return {"action": "none"}

        # 冷却: 同平台 60s 内不重复触发
        now = datetime.now().timestamp()
        if platform in self._last_failure and now - self._last_failure[platform] < 60:
            return {"action": "cooldown"}
        self._last_failure[platform] = now

        # 熔断检查
        cb = self._circuits.setdefault(platform, CircuitBreaker(
            name=f"crawler_{platform}", failure_threshold=3, recovery_timeout=600.0))
        if cb.state.value == "open":
            return {"action": "circuit_open"}

        # P0: 跨时间模式识别（在分类之前，结构性故障直接 escalate）
        trend = self._analyze_trend(platform)
        if trend["pattern"] == "structural_failure":
            logger.warning(f"[Healer] {platform} 结构性故障（多种错误交替），跳过常规恢复")
            cb.record_failure()
            self._save_event(platform, "structural_failure", "escalate", "trend",
                             False, return_code, "\n".join(errors[-5:]))
            return {"action": "escalate", "success": False, "restarted": False,
                    "reason": "结构性故障（多种错误类型交替出现）"}

        # 分类: 启发式 → LLM 兜底
        matched = classify_error(errors)
        if not matched:
            matched = await self._llm_diagnose(errors, platform)
        if not matched:
            return {"action": "unknown"}

        # 恢复
        result = await self._recover(matched, platform, return_code)

        cb.record_success() if result.get("success") else cb.record_failure()
        self._save_event(platform, matched["error_type"], matched["recovery"],
                         matched.get("source", "?"), result.get("success", False),
                         return_code, "\n".join(errors[-5:]))
        logger.info("[Healer] %s: %s → %s (%s)",
                     platform, matched["error_type"], matched["recovery"],
                     "ok" if result.get("success") else "fail")
        return result

    # ──────────────── LLM 诊断 ────────────────

    async def _llm_diagnose(self, errors: list[str], platform: str) -> Optional[Dict]:
        snippet = "\n".join(errors[-10:])[:1500]
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.DEFAULT_API_KEY, base_url=settings.DEFAULT_BASE_URL)
            resp = client.chat.completions.create(
                model=settings.DEFAULT_MODEL,
                messages=[{"role": "user", "content":
                    "分析爬虫错误日志，返回JSON: error_type(ip_blocked|login_expired|rate_limited|captcha_required|network_error|unknown), recovery(rotate_proxy|re_login|slow_down|escalate|retry_with_backoff|none)\n\n"
                    "平台:" + platform + "\n日志:\n" + snippet}],
                temperature=0)
            content = resp.choices[0].message.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            diag = json.loads(content)
            if diag.get("recovery") == "none":
                return None
            return {
                "error_type": diag.get("error_type", "unknown"),
                "recovery": diag.get("recovery", "escalate"),
                "severity": "high", "source": "llm",
            }
        except Exception as e:
            logger.error("[Healer] LLM 诊断失败: %s", e)
            return None

    # ──────────────── 恢复 ────────────────

    async def _recover(self, matched: Dict, platform: str, exit_code: int) -> Dict:
        import os
        import shutil
        recovery = matched["recovery"]

        if recovery == "rotate_proxy":
            os.environ["CRAWLER_FORCE_PROXY_REFRESH"] = "1"
        elif recovery == "re_login":
            profile = Path(__file__).parent.parent.parent / f"browser_data/cdp_{platform}_user_data_dir"
            if profile.exists():
                shutil.rmtree(profile, ignore_errors=True)
        elif recovery == "slow_down":
            new_delay = min(self._delays.get(platform, 2.0) * 2, 30.0)
            self._delays[platform] = new_delay
            os.environ["CRAWLER_MAX_SLEEP_SEC"] = str(new_delay)
        elif recovery == "retry_with_backoff":
            await asyncio.sleep(5)
        elif recovery == "escalate":
            return {"action": "escalate", "success": False, "restarted": False}

        try:
            ok = await self.manager.start(self.manager.current_config)
            if ok:
                # P0: 恢复验证探针 — "进程启动" ≠ "平台可达"
                probe_ok = await self._probe(platform)
                if not probe_ok:
                    logger.warning(f"[Healer] {platform} 重启成功但探针失败，标记恢复失败")
                    cb = self._circuits.get(platform)
                    if cb:
                        cb.record_failure()
                    self._save_event(platform, "probe_failed", recovery, "probe",
                                     False, 0, f"{platform} 重启后探针不可达")
                    return {"action": recovery, "success": False, "restarted": True,
                            "reason": "进程启动但平台不可达"}
            return {"action": recovery, "success": ok, "restarted": True}
        except Exception as e:
            return {"action": recovery, "success": False, "restarted": False, "error": str(e)}

    # ──────────────── P0: 探针验证 ────────────────

    async def _probe(self, platform: str) -> bool:
        """轻量探针 GET 请求，确认平台服务端可达。失败时静默返回 False。"""
        probe_urls = {
            "wb": "https://weibo.com",
            "xhs": "https://www.xiaohongshu.com/explore",
            "bili": "https://www.bilibili.com",
            "dy": "https://www.douyin.com",
            "ks": "https://www.kuaishou.com",
        }
        url = probe_urls.get(platform)
        if not url:
            return True  # 没有探针 url 的平台默认通过
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, ssl=False) as resp:
                    reachable = resp.status < 500
                    if not reachable:
                        logger.warning(f"[Healer] {platform} 探针返回 {resp.status}")
                    return reachable
        except ImportError:
            logger.debug("[Healer] aiohttp 未安装，跳过探针验证")
            return True
        except Exception as e:
            logger.debug(f"[Healer] {platform} 探针异常: {e}")
            return False

    # ──────────────── P0: 跨时间模式识别 ────────────────

    def _analyze_trend(self, platform: str, window_hours: int = 2) -> dict:
        """分析过去 window_hours 内同一平台的失败模式。"""
        events = self.get_history(platform, limit=20)
        now = datetime.now()
        relevant = [
            e for e in events
            if (now - datetime.fromisoformat(e["created_at"])).total_seconds() / 3600 < window_hours
        ]
        if len(relevant) < 3:
            return {"pattern": "insufficient_data"}

        error_types = {e["error_type"] for e in relevant if e.get("error_type")}
        if not error_types:
            return {"pattern": "insufficient_data"}

        time_span_h = (
            datetime.fromisoformat(relevant[0]["created_at"]) -
            datetime.fromisoformat(relevant[-1]["created_at"])
        ).total_seconds() / 3600

        if len(error_types) >= 3 and time_span_h < window_hours:
            return {"pattern": "structural_failure", "error_types": list(error_types)}

        if len(error_types) == 1 and time_span_h > 6:
            return {
                "pattern": "predictable_failure",
                "interval_h": round(time_span_h / len(relevant), 2),
            }

        return {"pattern": "isolated_failure"}

    def _current_platform(self) -> Optional[str]:
        c = self.manager.current_config
        return c.platform.value if c else None

    def get_platform_health(self, platform: str) -> Dict:
        cb = self._circuits.get(platform)
        return {
            "platform": platform,
            "circuit_state": cb.state.value if cb else "unknown",
            "failure_count": cb.failure_count if cb else 0,
            "adaptive_delay": self._delays.get(platform, 2.0),
        }
