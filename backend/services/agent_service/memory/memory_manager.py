"""
AgentMemoryManager: 检索/写入时机决策，LLM 摘要生成，context 注入
"""
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from openai import OpenAI
from backend.core.config import settings, get_agent_config
from backend.core.logger import get_logger
from .memory_store import AgentMemoryStore

logger = get_logger("agent.memory")

# working_memory 800 字符上限
WORKING_MEMORY_MAX_CHARS = 1200


class AgentMemoryManager:
    """记忆管理器"""

    def __init__(self):
        self.store = AgentMemoryStore()
        self.ttl_days = getattr(settings, 'AGENT_MEMORY_TTL_DAYS', 90)

    def _fresh_client(self):
        """每次新建客户端（配置热刷新）"""
        key, url, _ = get_agent_config()
        return OpenAI(api_key=key, base_url=url)

    def build_working_memory(self, session_id: str, owner_id: str = "") -> str:
        """
        对话开始时调用：检索长期记忆 + 用户订阅画像，构建【用户记忆】段落。
        >1200 字符时降级（只保留最先的两个区块）。
        owner_id 必传，store 内部按 owner_id 隔离检索。
        """
        parts = []

        # 1. 用户订阅画像（继承自系统配置）
        sub_profile = self._build_subscription_profile(owner_id)
        if sub_profile:
            parts.append(sub_profile)

        # 2. 跨 session 长期关注实体
        global_entities = self.store.get_global_entities(owner_id, min_count=2, limit=8)
        if global_entities:
            lines = [
                f"- {e['entity']}（{e['entity_type']}），累计关注 {e['total_count']} 次"
                for e in global_entities
            ]
            parts.append("【长期关注】\n" + "\n".join(lines))

        # 3. 事实记忆（跨 session）
        facts = self.store.get_valid_facts(session_id, owner_id)
        if facts:
            lines = [f"- {f['entity']}: {f['content']}" for f in facts[:6]]
            parts.append("【已确认事实】\n" + "\n".join(lines))

        if not parts:
            return ""

        full = "\n\n".join(parts)

        if len(full) > WORKING_MEMORY_MAX_CHARS:
            # 取前两个区块
            kept = []
            char_count = 0
            for p in parts:
                if char_count + len(p) > WORKING_MEMORY_MAX_CHARS:
                    break
                kept.append(p)
                char_count += len(p)
            return "\n\n".join(kept) if kept else parts[0]

        return full

    def _build_subscription_profile(self, owner_id: str) -> str:
        """
        从 subscription / quota 表拉取用户配置，返回格式化字符串。
        无数据或出错时返回空字符串。
        """
        if not owner_id:
            return ""
        try:
            from backend.core.subscription_db import list_subscriptions
            from backend.core.quota_db import get_scan_config

            subs = list_subscriptions(owner_id) if callable(list_subscriptions) else []
            scan = get_scan_config(owner_id) if callable(get_scan_config) else {}

            lines = []

            # 订阅关键词
            keywords = [s["name"] for s in subs if s.get("type") == "keyword" and s.get("name")]
            if keywords:
                lines.append(f"- 监控关键词：{'、'.join(keywords[:8])}")

            # 其他订阅类型
            for s_type, label in [("person", "人物"), ("event", "事件"), ("competitor", "竞品")]:
                items = [s["name"] for s in subs if s.get("type") == s_type and s.get("name")]
                if items:
                    lines.append(f"- 监控{label}：{'、'.join(items[:4])}")

            # 扫描配置
            interval = scan.get("interval_min", 0)
            paused = scan.get("paused", False)
            if interval:
                status = "已暂停" if paused else "运行中"
                lines.append(f"- 扫描频率：每 {interval} 分钟（{status}）")

            if not lines:
                return ""

            return "【用户配置】\n" + "\n".join(lines)
        except Exception as e:
            logger.warning(f"[Memory] 构建用户画像失败（非致命）: {e}")
            return ""

    def write_from_conversation(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        outcome: str = None,
        owner_id: str = "",
    ):
        """
        对话结束时调用（v2.2 per-user）：提取实体、写入 fact_memory、生成摘要。
        owner_id 透传到所有 store 写入路径，避免多用户数据串读。
        """
        summary = self._summarize_conversation(messages)
        entities = self._extract_entities_from_messages(messages)
        self.store.save_summary(session_id, summary, entities, outcome, owner_id)

        # 写入实体记忆
        for entity_text, entity_type in entities:
            self.store.upsert_entity(session_id, entity_text, entity_type, owner_id=owner_id)

        # 抽取并写入事实记忆（LLM 从对话中提取结构化事实）
        self._extract_and_save_facts(session_id, messages, owner_id=owner_id)

        logger.info(
            f"[Memory] 已写入对话 {session_id} 的记忆："
            f"{len(entities)} 个实体 (owner={owner_id[:8] if owner_id else 'legacy'})"
        )

    def _summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """LLM 生成 200 字以内对话摘要"""
        if not messages:
            return "用户未提问"

        messages_text = "\n".join([
            f"{'用户' if m['role']=='user' else '助手'}: {m['content'][:200]}"
            for m in messages[-8:]  # 最近 8 条
        ])

        prompt = f"""用200字以内概括以下对话的核心意图、用户关注点和关键结论：

{messages_text}

直接返回摘要文字，不需要解释。"""

        try:
            key, url, model = get_agent_config()
            client = OpenAI(api_key=key, base_url=url)
            response = client.chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3
            )
            if not response.choices:
                logger.warning("[Memory] LLM 返回空 choices (摘要)")
                return f"对话包含 {len(messages)} 条消息"
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            return f"对话包含 {len(messages)} 条消息"

    def _extract_and_save_facts(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
        owner_id: str = "",
    ):
        """
        从对话中提取结构化事实（实体相关 key-value），写入 fact_memory。
        最多取最近 6 条消息，避免长对话消耗过多 token。
        """
        relevant = [m for m in messages if m.get("role") in ("user", "assistant")][-6:]
        full_text = " ".join(m.get("content", "") for m in relevant)
        if not full_text.strip():
            return

        try:
            key, url, model = get_agent_config()
            client = OpenAI(api_key=key, base_url=url)
            resp = client.chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=[{"role": "user", "content": (
                    "从以下对话中提取可验证的事实（不包含观点、猜测）。"
                    "返回 JSON 数组，每个元素包含：\n"
                    "- entity: 主体名称\n"
                    "- fact_type: 事实类型（如 preference, attribute, relationship, event）\n"
                    "- content: 事实描述（20字以内）\n"
                    "- confidence: 置信度 0.0-1.0\n\n"
                    "没有可提取的事实则返回空数组。\n\n" + full_text
                )}],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            if not resp.choices:
                logger.warning("[Memory] LLM 返回空 choices (事实抽取)")
                return
            raw = resp.choices[0].message.content
            parsed = json.loads(raw)
            facts = parsed if isinstance(parsed, list) else parsed.get("facts", [])
            for f in facts:
                entity = f.get("entity", "")
                fact_type = f.get("fact_type", "general")
                content = f.get("content", "")
                confidence = float(f.get("confidence", 0.6))
                if entity and content:
                    self.store.insert_fact(
                        session_id, entity, fact_type, content,
                        owner_id=owner_id, confidence=min(confidence, 1.0),
                    )
            if facts:
                logger.info(f"[Memory] 已写入 {len(facts)} 条事实记忆")
        except Exception as e:
            logger.warning(f"[Memory] 事实抽取失败（非致命）: {e}")

    def _extract_entities_from_messages(self, messages: List[Dict[str, str]]) -> List[tuple]:
        """
        从最后 6 条 user/assistant 原文中抽取实体。
        优先 LLM 抽取（语义准确），LLM 失败时回退 jieba POS 标注。
        """
        if not messages:
            return []
        relevant = [m for m in messages if m.get("role") in ("user", "assistant")][-6:]
        full_text = " ".join(m.get("content", "") for m in relevant)
        if not full_text.strip():
            return []

        # 优先 LLM 抽取
        try:
            key, url, model = get_agent_config()
            client = OpenAI(api_key=key, base_url=url)
            resp = client.chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=[{"role": "user", "content": (
                    "从以下对话中提取所有重要实体（品牌、人名、产品名、公司名、事件名）。"
                    "返回 JSON 数组，每个元素包含 name（实体名）和 type（brand|person|product|org|event）。"
                    "不要返回不在文本中的实体。\n\n" + full_text
                )}],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            if not resp.choices:
                logger.warning("[Memory] LLM 返回空 choices (实体抽取)")
                return []
            raw = resp.choices[0].message.content
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else parsed.get("entities", [])
            return [(e["name"], e["type"]) for e in items if e.get("name") and e.get("type")]
        except Exception as e:
            logger.warning(f"[Memory] LLM 实体抽取失败，回退 jieba: {e}")

        # 回退 jieba
        try:
            import jieba.posseg as pseg
        except ImportError:
            return []

        pos_map = {"nr": "person", "ns": "place", "nt": "org", "nz": "brand", "n": "concept"}
        found, seen = [], set()
        try:
            for word, flag in pseg.cut(full_text):
                if len(word) >= 2 and flag in pos_map and word not in seen:
                    seen.add(word)
                    found.append((word, pos_map[flag]))
        except Exception:
            pass
        return found

    def cleanup_expired_memory(self) -> Dict[str, int]:
        """v2.2 P2.5：全表 TTL 清理，返回各表清理条数"""
        return self.store.cleanup_expired_all()

    def delete_session(self, session_id: str, owner_id: str = "") -> int:
        """删除某次对话记忆（传 owner_id 限定删除范围）"""
        return self.store.delete_session(session_id, owner_id=owner_id)

    def get_stats(self) -> Dict[str, int]:
        """获取记忆统计"""
        return self.store.get_memory_stats()