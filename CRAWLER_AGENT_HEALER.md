# 爬虫智能自修复方案

> 目标：覆盖进程级和数据级两类故障的自愈体系。
> 原则：只做增量，不搞翻新。与 Admin Agent 解耦——Admin 只看不控，Healer 自己决策执行。

## 实施状态

| 组件 | 状态 | 说明 |
|------|------|------|
| `healer/crawler_healer.py` | ✅ | 正则 + LLM 双通道分类 + 机械恢复 + 平台级熔断 |
| `healer/error_patterns.py` | ✅ | 5 种错误模式（ip_blocked/login_expired/rate_limited/captcha_required/network_error） |
| `crawler_manager.py` 集成 | ✅ | 进程退出后触发 Healer |
| `GET /crawler/heal/status` | ✅ | 自愈事件查询 + 平台健康状态 |
| **P0: 产出物质量检测** | ✅ | `output_validator.py` — 数量/字段/同质化/编码 4 项检测 |
| **P0: 恢复验证环** | ✅ | `_probe()` 探针 — 重启后 GET 确认平台可达，不可达标记失败 |
| **P0: 跨时间模式识别** | ✅ | `_analyze_trend()` — 2h 窗口识别 structural / predictable / isolated failure |
| **P1: LLM 诊断升级** | ⬜ | 见下方扩展方案 |
| **P1: 跨进程优雅取消** | ⬜ | 见打断机制.md（已完成跨进程信号文件） |
| **P2: 数据级故障修复** | ⬜ | 见下方扩展方案 |

缺失的能力见下方扩展方案。

---

## 一、现有架构（已实施）

### 流程

```
爬虫子进程退出
    │
_read_output 检测到 poll() is not None
    │
    ├─ exit_code == 0 → 正常结束（当前不触发 Healer）
    │
    └─ exit_code != 0 → CrawlerHealer.analyze_and_recover(exit_code)
         │
         ├─ 冷却检查（同平台 60s 防抖）
         ├─ 熔断检查（3 次失败 → OPEN → 600s 恢复）
         ├─ 分类: classify_error() 正则毫秒级 / LLM 兜底
         ├─ 恢复: rotate_proxy / re_login / slow_down / retry_with_backoff / escalate
         ├─ 重启: manager.start()
         └─ 存事件: heal_events 表 (SQLite)
```

### 分层恢复

| 层级 | 触发 | 方式 | 成本 |
|------|------|------|------|
| L0 即时重试 | 爬虫进程内 tenacity | 指数退避 | 0（已有）|
| L1 启发式 | 进程异常退出 | 正则扫描 → 匹配恢复 → 重启 | 毫秒级 |
| L2 LLM 诊断 | L1 未命中 | LLM 分析最后 10 行 → 分类 → 重启 | 秒级，~500 token |
| L3 熔断升级 | L1/L2 连续 3 次失败 | CircuitBreaker OPEN → 暂停 10min | 分钟级 |

---

## 二、核心弱点（当前代码不能做）

| 问题 | 当前状态 | 后果 |
|------|---------|------|
| 恢复无验证 | `start()` 成功 = success | 进程起了但平台可能仍不可用 |
| 每次失败隔离分析 | 不看历史 | 3 种错误交替出现也当 3 次独立的故障 |
| 不检测数据质量 | exit_code=0 直接跳过 | 页面改版了也完全不知道 |
| 无法跨进程通信 | 没有信号机制 | 子进程无法感知"该停了" |
| LLM 只是标签机 | 只输出 `{error_type, recovery}` | 浪费 LLM 的理解力 |
| 不修数据级故障 | CSS 改版、字段变更不会触发 Healer | 数据入库全是 null |

以下方案逐一填补。

---

## 三、扩展方案 P0：产出物质量检测

### 问题

进程正常退出并不代表数据可用。页面改版、字段空洞、编码异常导致的悄无声息的数据丢失远比进程 crash 更隐蔽。

### 方案

新增 `OutputValidator`，在 `exit_code == 0` 分支调用，发现异常后触发 Healer。

```python
# crawler_manager.py — 新增验证器

class OutputValidator:
    """验证爬虫产出物质量。不修、不打捞，只检测和标记。"""

    MIN_EXPECTED: dict = {
        "wb": 5, "xhs": 5, "bili": 3, "dy": 5, "ks": 3,
    }

    def validate(self, platform: str, posts: list, logs: list) -> dict:
        issues = []

        # 1. 数量空洞
        expected = self.MIN_EXPECTED.get(platform, 3)
        if len(posts) < expected:
            issues.append({
                "type": "empty_result",
                "severity": "critical" if len(posts) == 0 else "warning",
                "detail": f"采集到 {len(posts)} 条，预期 ≥ {expected}",
            })

        # 2. 字段空洞（标题/正文大量缺失 → 可能 HTML 选择器失效）
        if posts:
            null_titles = sum(1 for p in posts if not p.get("title", "").strip())
            null_contents = sum(1 for p in posts if not p.get("content", "").strip())
            total = len(posts)
            if null_titles > total * 0.5:
                issues.append({
                    "type": "structural_change",
                    "severity": "critical",
                    "detail": f"标题缺失率 {null_titles}/{total}，疑似页面结构变更",
                })
            if null_contents > total * 0.5:
                issues.append({
                    "type": "structural_change",
                    "severity": "critical",
                    "detail": f"正文缺失率 {null_contents}/{total}，疑似页面结构变更",
                })

        # 3. 内容同质化（反爬返回了统一提示文案）
        if len(posts) >= 3:
            first50 = [p.get("content", "")[:50] for p in posts[:5]]
            if len(set(first50)) <= 1:
                issues.append({
                    "type": "likely_blocked",
                    "severity": "critical",
                    "detail": "多条内容高度相似，可能进入了验证页",
                })

        # 4. 编码异常
        garbled = self._check_garbled(posts)
        if garbled > 0:
            issues.append({
                "type": "encoding_error",
                "severity": "warning",
                "detail": f"检测到 {garbled} 条含异常字符",
            })

        return {"platform": platform, "posts": len(posts), "issues": issues}

    def _check_garbled(self, posts: list) -> int:
        import re
        count = 0
        for p in posts:
            text = json.dumps(p, ensure_ascii=False)
            if len(re.findall(r'[�\ufffd]', text)) > 50:
                count += 1
        return count
```

### 调用时机

```python
# CrawlerManager._read_output() 中
if exit_code == 0:
    issues = OutputValidator().validate(platform, collected_posts, self.logs)
    if issues["issues"]:
        if hasattr(self, '_healer'):
            self._healer.handle_data_anomaly(issues)  # 触发数据级恢复
```

### 产出物异常的分级处置

| 严重程度 | 条件 | 响应 |
|---------|------|------|
| critical | 0 条 / 标题缺失 > 50% / 同质化 | 触发 Healer 数据级恢复，尝试切换采集方法 |
| warning | 字段缺失但 < 50% / 编码异常 | 仅标记进 heal_events，不触发恢复，留待运维看板 |
| info | 数量略低于预期 | 只日志，不记录 heal_events |

---

## 四、扩展方案 P0：恢复验证环

### 问题

当前 `_recover` 执行 `manager.start()` 后只要不抛异常就记 success。但"进程启动成功"不等于"爬虫能干活"。

### 方案

`_recover` 末尾、`manager.start()` 之后插入探针请求，确认平台正常响应。失败后记录真实失败。

```python
def _probe(self, platform: str) -> bool:
    """轻量探针 GET 请求，确认平台服务端可达。0 token，< 10s。"""
    import aiohttp
    probe_urls = {
        "wb": "https://weibo.com",
        "xhs": "https://www.xiaohongshu.com/explore",
        "bili": "https://www.bilibili.com",
    }
    url = probe_urls.get(platform)
    if not url:
        return True
    try:
        resp = asyncio.wait_for(
            aiohttp.request("GET", url, timeout=aiohttp.ClientTimeout(total=10)),
            timeout=15,
        )
        return resp.status < 500
    except Exception:
        return False
```

在 `_recover` 末尾调用：

```python
if ok:
    probe_ok = await self._probe(platform)
    if not probe_ok:
        logger.warning(f"[Healer] {platform} 重启成功但探针失败，标记恢复失败")
        cb.record_failure()
        return {"action": recovery, "success": False, "restarted": True}
```

效果：对下游透明，但 `heal_events` 中记录的真实成功/失败更准确。后续结合跨时间模式分析，可以更早识别结构性故障。

---

## 五、扩展方案 P0：跨时间模式识别

### 问题

同平台短时间内 3 种不同错误交替出现（ip_blocked → login_expired → rate_limited），每次各自恢复成功，但根因没变——只有从时间维度看才能发现"这不是孤立故障"。

### 方案

`analyze_and_recover` 入口、冷却之后、分类之前，查历史事件做趋势分析。

```python
def _analyze_trend(self, platform: str, window_hours: int = 2) -> dict:
    """分析过去 window_hours 内同一平台的失败模式。
    
    返回 pattern:
      - insufficient_data     : 不足 3 条，不足以判断
      - structural_failure    : 多错误类型密集出现 → 升级
      - predictable_failure   : 单一错误规律出现   → 可预判
      - isolated_failure      : 偶发，正常处理
    """
    events = self.get_history(platform, limit=20)
    relevant = [
        e for e in events
        if (datetime.now() - datetime.fromisoformat(e["created_at"])).total_seconds() / 3600 < window_hours
    ]
    if len(relevant) < 3:
        return {"pattern": "insufficient_data"}

    error_types = {e["error_type"] for e in relevant}
    time_span_h = (
        datetime.fromisoformat(relevant[0]["created_at"]) -
        datetime.fromisoformat(relevant[-1]["created_at"])
    ).total_seconds() / 3600

    if len(error_types) >= 3 and time_span_h < window_hours:
        return {"pattern": "structural_failure", "error_types": list(error_types)}

    if len(error_types) == 1 and time_span_h > 6:
        return {"pattern": "predictable_failure", "interval_h": time_span_h / len(relevant)}

    return {"pattern": "isolated_failure"}
```

在 `analyze_and_recover` 中调用（冷却检查之后、分类之前）：

```python
trend = self._analyze_trend(platform)
if trend["pattern"] == "structural_failure":
    logger.warning(f"[Healer] {platform} 结构性故障（多种错误交替），跳过常规恢复")
    # 直接 escalate，不浪费一次失败的恢复
    cb.record_failure()
    self._save_event(platform, "structural_failure", "escalate", "trend",
                     False, return_code, "\n".join(errors[-5:]))
    return {"action": "escalate", "success": False, "restarted": False,
            "reason": "结构性故障（多种错误类型交替出现）"}
```

---

## 六、扩展方案 P1：LLM 诊断升级

### 问题

当前 LLM 只输出 `{error_type, recovery}`——本质是把正则分类器的后端换成了 LLM，完全没有利用 LLM 的理解能力。

### 方案

喂更多上下文：历史事件 + 当前配置 + 完整错误日志。输出恢复计划 + 置信度。

```python
async def _llm_diagnose_v2(self, errors: list, platform: str) -> dict | None:
    snippet = "\n".join(errors[-15:])[:2000]
    history = self.get_history(platform, limit=5)
    hist_lines = "\n".join([
        f"  [{h['created_at'][:16]}] {h['error_type']} → {h['recovery']} ({'成功' if h['success'] else '失败'})"
        for h in history
    ])
    current_config = {
        "interval": self._delays.get(platform, 2.0),
        "method": os.environ.get("CRAWLER_METHOD", "http"),
        "circuit": self._circuits.get(platform).state.value if platform in self._circuits else "closed",
    }

    prompt = f"""你是爬虫反爬对抗专家。

平台: {platform}
当前配置: {json.dumps(current_config, ensure_ascii=False)}

最近恢复历史:
{hist_lines if hist_lines else "  (无)"}

错误日志（最后 15 行）:
{snippet}

输出 JSON（禁止其他内容）：
{{
  "root_cause": "根因简析，1-2 句话",
  "confidence": "high|medium|low",
  "plan": [
    {{"action": "rotate_proxy|re_login|slow_down|switch_method|degrade|clear_profile|test_request|escalate", "params": {{}}}}
  ],
  "if_fails_next": "escalate|manual"
}}

规则：
- plan 按优先级排列，第一个最推荐
- confidence=low 时 if_fails_next 必须为 manual
- 如果怀疑结构性故障，plan 第一个 action 应为 test_request 做验证"""
    # ... LLM 调用和 JSON 解析，与原逻辑一致 ...
```

响应结构从单字段改为多维，恢复动作新增 `switch_method` 和 `degrade`，对接数据级故障的恢复策略。

---

## 七、扩展方案 P1：跨进程优雅取消

### 问题

当前 `CrawlerManager.stop()` 只有 SIGTERM → kill 一条路，子进程无法感知"该保存进度退出了"。

### 方案

通过临时文件信号量实现跨进程通信。子进程定期检测信号文件，检测到后保存 checkpoint 自行退出。

```python
# crawler_manager.py

_SIGNAL_DIR = Path(tempfile.gettempdir()) / "mediaradar_crawler_signals"

class CrawlerManager:
    def __init__(self, platform: str):
        _SIGNAL_DIR.mkdir(exist_ok=True)
        self._stop_flag = _SIGNAL_DIR / f"{platform}_stop"
        self._pause_flag = _SIGNAL_DIR / f"{platform}_pause"
        # ...

    async def graceful_stop(self) -> bool:
        """优雅停止：通知子进程自行退出，超时后 SIGTERM 兜底。"""
        self._stop_flag.touch()
        self.status = "stopping"
        try:
            await asyncio.wait_for(
                self._wait_process_exit(),
                timeout=30,
            )
        except asyncio.TimeoutError:
            return await self.stop()  # SIGTERM → kill
        finally:
            self._stop_flag.unlink(missing_ok=True)
            self._pause_flag.unlink(missing_ok=True)
        return True

    async def pause(self) -> bool:
        """暂停：子进程完成当前页面后停止。"""
        self._pause_flag.touch()
        self.status = "paused"
        return True

    async def resume(self) -> bool:
        """恢复。"""
        self._pause_flag.unlink(missing_ok=True)
        self.status = "running"
        return True
```

爬虫子进程中检测：

```python
# 爬虫主循环中，每页之间检查
import os, sys

STOP = Path(tempfile.gettempdir()) / "mediaradar_crawler_signals" / f"{PLATFORM}_stop"

for page in pages:
    if STOP.exists():
        save_checkpoint(page)  # 保存进度
        sys.exit(0)           # 优雅退出，Healer 决定是否重启
    crawl(page)
```

---

## 八、扩展方案 P2：数据级故障修复

### 问题

当前 Healer 只处理进程退出导致的故障。如果爬虫正常退出但数据质量差（页面改版、字段变更），没有任何恢复动作。

### 检测与修复链路

```
exit_code == 0
    │
OutputValidator.validate()
    │
    ├─ healthy → 无事发生
    │
    └─ 异常 → CrawlerHealer.handle_data_anomaly()
                  │
                  ├─ switch_method        → 换采集方式（http → playwright → cdp）
                  ├─ degrade              → 降级到简版采集（只采标题+正文）
                  ├─ dead_letter          → 标记死信，记录证据，继续
                  └─ escalate             → 保存上下文等人修
```

### 恢复策略

```python
async def _recover_data_quality(self, platform: str, issues: list) -> dict:
    """尝试数据级故障恢复。"""
    current = os.environ.get("CRAWLER_METHOD", "http")

    if current == "http":
        # HTTP 模式数据异常 → 切 Playwright
        os.environ["CRAWLER_METHOD"] = "playwright"
        logger.info(f"[Healer] {platform} HTTP 数据异常，切换为 Playwright")
    elif current == "playwright":
        # 浏览器也异常 → 切 CDP（远程调试）
        os.environ["CRAWLER_METHOD"] = "cdp"
        logger.info(f"[Healer] {platform} Playwright 数据异常，切换为 CDP")
    else:
        # 所有采集方式均产出异常 → 降级到简版采集合约
        os.environ["CRAWLER_DEGRADE"] = "1"
        logger.warning(f"[Healer] {platform} 采集方法均失败，降级到简版模式")

    try:
        ok = await self.manager.start(self.manager.current_config)
        return {"action": "data_recovery", "success": ok, "restarted": True}
    except Exception as e:
        # 标记死信，保存证据
        self._save_dead_letter(platform, issues, str(e))
        return {"action": "escalate", "success": False, "restarted": False, "error": str(e)}
```

### 死信队列

所有恢复尝试耗尽后仍失败的数据故障，保存完整的调试上下文供人工排查：

```python
def _save_dead_letter(self, platform: str, issues: list, error: str = ""):
    """写入 SQLite dead_letters 表，供 Admin 看板消费。"""
    with sqlite3.connect(self._db_path) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS dead_letters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT, issue_types TEXT, error TEXT,
                config_snapshot TEXT, created_at TEXT
            )
        """)
        c.execute("""
            INSERT INTO dead_letters (platform, issue_types, error, config_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            platform,
            json.dumps([i["type"] for i in issues], ensure_ascii=False),
            error[:500],
            json.dumps({
                "interval": self._delays.get(platform, 2.0),
                "method": os.environ.get("CRAWLER_METHOD", "http"),
                "circuit": self._circuits.get(platform).state.value if platform in self._circuits else "unknown",
            }, ensure_ascii=False),
            datetime.now().isoformat(),
        ))
        conn.commit()
```

---

## 九、完整恢复体系概览

```
故障入口                             检测机制                       恢复路径
───────                             ────────                       ────────
进程 crash (exit_code ≠ 0)          _read_output 捕获              L1 启发式 / L2 LLM → 机械恢复 → 重启
进程正常但数据异常 (exit_code=0)     OutputValidator.validate()     switch_method → degrade → dead_letter
多错误交替（同平台短时间密集失败）     _analyze_trend() 跨时间扫描    structural_failure → escalate
用户主动取消                         _stop_flag 信号文件            保存 checkpoint → exit(0)
```

| 恢复策略 | 触发条件 | 效果 |
|---------|---------|------|
| `rotate_proxy` | IP 被封 / 429 | 强制刷新代理池 |
| `re_login` | 登录过期 / cookie 无效 | 清除浏览器 profile，重新登录 |
| `slow_down` | 限流 / 频率超限 | 请求间隔加倍（上限 30s） |
| `retry_with_backoff` | 网络错误 / 超时 | 等 5s 后重试 |
| `switch_method` | 数据字段空洞 / 同质化 | http ↔ playwright ↔ cdp 切换 |
| `degrade` | 所有方法均数据异常 | 降级到简版采集（标题+正文） |
| `escalate` | 结构性故障 / 未知错误 | 保存死信，暂停平台，等人工 |

分层恢复（L0-L3 不变，新增 L0.5/L1.5）：

| 层级 | 触发 | 方式 | 成本 |
|------|------|------|------|
| L0 即时重试 | 进程内 tenacity | 指数退避 | 0 token，已实现 |
| **L0.5 数据质检** | 进程正常退出后 | OutputValidator 扫描产出物 | 0 token，毫秒级 |
| L1 启发式 | 进程异常退出 | 正则匹配 → 机械恢复 | 0 token，毫秒级 |
| **L1.5 跨时间分析** | 每次入口 | 查历史事件判断模式 | 0 token，毫秒级 |
| L2 LLM 诊断 | L1 未命中 | LLM 分析日志 → 恢复计划 | ~500 token |
| L3 熔断升级 | 连续失败 | CircuitBreaker OPEN 暂停平台 10min | 分钟级 |

---

## 十、与 Admin Agent 的职责边界

| 系统 | 能碰什么 | 不能碰什么 |
|------|---------|-----------|
| Crawler Healer | 决策恢复策略、执行探针、存 heal_events、读/写信号文件 | 不将决策权交给外部 |
| Admin Agent | 读 heal_events 表做运维看板、读 dead_letters 查看待处理项 | 不触发恢复、不改爬虫参数、不写配置 |

Admin Agent 对爬虫唯一能做的事情是：**给 Admin 用户展示爬虫健康状态**——哪个平台熔断了几次、最新的死信是什么。它不驱动恢复。

---

## 十一、实施路线

| 优先 | 项 | 行数 | 效果 |
|------|----|------|------|
| P0 | 产出物质量检测 | ~60 | 发现"跑完了但数据是垃圾" |
| P0 | 恢复验证环 | ~30 | "进程启动了"≠"恢复成功了" |
| P0 | 跨时间模式识别 | ~50 | 识别"多种错误交替=结构性故障" |
| P1 | LLM 诊断升级 | ~30 | 从打标签升级为出诊断计划 |
| P1 | 跨进程优雅取消 | ~60 | SIGTERM 不再是唯一选择 |
| P2 | 数据级故障修复 | ~80 | 自动切换采集方法 + 降级 + 死信 |
