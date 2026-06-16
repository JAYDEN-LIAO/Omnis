"""
ReflectionEngine: 置信度评估 + 补充探查 prompt 生成
"""
import json
from typing import Literal
from openai import OpenAI
from backend.core.config import settings
from backend.core.logger import get_logger
from .prompts import REFLECTION_PROMPT, REFLECTION_MEDI_PROMPT

logger = get_logger("agent.reflection")

class ReflectionEngine:
    """反思引擎：评估工具返回质量，决定后续动作"""

    def __init__(self):
        self.enabled = getattr(settings, 'AGENT_REFLECTION_ENABLED', True)

    def get_client(self, owner_id: str = ""):
        """v2.2 P0.3：按 owner_id 读 per-user 配置，未传时回退全局默认"""
        from backend.core.config import get_agent_config_for_user, get_agent_config
        if owner_id:
            key, url, _ = get_agent_config_for_user(owner_id)
        else:
            key, url, _ = get_agent_config()
        return OpenAI(api_key=key, base_url=url)

    def _get_model(self, owner_id: str = "") -> str:
        """v2.2 P0.3：取用户配置的模型名，空则用 settings.DEFAULT_MODEL"""
        from backend.core.config import get_agent_config_for_user, get_agent_config
        if owner_id:
            _, _, model = get_agent_config_for_user(owner_id)
        else:
            _, _, model = get_agent_config()
        return model or settings.DEFAULT_MODEL

    def evaluate(
        self,
        user_question: str,
        tool_result: str,
        owner_id: str = "",
    ) -> dict:
        """
        评估工具返回的置信度。
        返回 {confidence: "high"/"medi"/"low", reasoning, missing_info}
        v2.2 P0.3：owner_id 透传，按用户配置选模型
        """
        if not self.enabled:
            return {"confidence": "high", "reasoning": "Reflection 已禁用", "missing_info": ""}

        prompt = REFLECTION_PROMPT.format(
            user_question=user_question,
            tool_result=tool_result
        )

        try:
            response = self.get_client(owner_id).chat.completions.create(
                model=self._get_model(owner_id),
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            if not response.choices:
                logger.warning("[Reflection] LLM 返回空 choices (置信度评估)")
                return {"confidence": "high", "reasoning": "LLM 返回空 choices，默认通过", "missing_info": ""}
            content = response.choices[0].message.content.strip()

            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            logger.info(f"[Reflection] 置信度评估: {result.get('confidence')} | {result.get('reasoning', '')[:50]}")
            return result
        except Exception as e:
            logger.error(f"Reflection LLM 调用失败: {e}")
            return {"confidence": "high", "reasoning": "评估异常，默认通过", "missing_info": ""}

    def handle_medi(
        self,
        user_question: str,
        tool_result: str,
        missing_info: str,
        owner_id: str = "",
    ) -> dict:
        """
        置信度为 medi 时，生成补充探查 prompt。
        返回 {action: "follow_up"/"degrade", follow_up_question/degrade_answer}
        v2.2 P0.3：owner_id 透传
        """
        prompt = REFLECTION_MEDI_PROMPT.format(
            user_question=user_question,
            tool_result=tool_result,
            missing_info=missing_info
        )

        try:
            response = self.get_client(owner_id).chat.completions.create(
                model=self._get_model(owner_id),
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            if not response.choices:
                logger.warning("[Reflection] LLM 返回空 choices (补充探查)")
                return {"action": "degrade", "degrade_answer": "分析引擎暂时无法完成评估，请稍后重试。"}
            content = response.choices[0].message.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)
        except Exception as e:
            logger.error(f"Reflection medi 处理失败: {e}")
            return {"action": "degrade", "degrade_answer": "基于目前数据，暂时无法给出准确回答。"}

    def get_degrade_answer(self, tool_result: str) -> str:
        """生成降级回答模板"""
        try:
            parsed = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
            data = parsed.get("data", tool_result)
            if isinstance(data, str):
                data_preview = data[:100]
            else:
                data_preview = str(data)[:100]
            return f"基于目前数据倾向于：{data_preview}..."
        except Exception:
            return "基于目前数据，暂时无法给出准确回答，请稍后重试。"