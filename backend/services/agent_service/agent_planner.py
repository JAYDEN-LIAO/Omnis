# backend/services/agent_service/agent_planner.py
"""
Agent 规划层 — phase_plan + 模板匹配 + 计划执行
"""
from __future__ import annotations
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

from core.config import settings, get_agent_config
from openai import OpenAI

from backend.core.logger import get_logger
from backend.services.agent_service.tools._base import ToolResult

if TYPE_CHECKING:
    from .agent_core import AgentContext

logger = get_logger("agent.planner")


# ==================== v2.0 P2: 四维智能规划 ====================


def _get_last_user_message(ctx: AgentContext) -> str:
    for m in reversed(ctx.messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _list_tool_names_for_planning() -> str:
    try:
        from backend.services.agent_service.tools import AVAILABLE_TOOLS
        return ", ".join(sorted(AVAILABLE_TOOLS.keys()))
    except Exception:
        return ""


def _parse_plan_json(content: str) -> dict:
    """解析 LLM 返回的 plan JSON。失败时尝试从 markdown 提取，否则返回 fallback。"""
    import json as _json
    content = content.strip()
    try:
        plan = _json.loads(content)
        if isinstance(plan, dict) and "steps" in plan:
            return plan
    except _json.JSONDecodeError:
        pass
    if "```json" in content:
        try:
            inner = content.split("```json", 1)[1].split("```", 1)[0]
            plan = _json.loads(inner)
            if isinstance(plan, dict):
                return plan
        except Exception:
            pass
    from backend.core.metrics import AGENT_PLAN_GENERATION_TOTAL
    logger.warning(f"[Plan] JSON 解析失败: {content[:200]}")
    try:
        AGENT_PLAN_GENERATION_TOTAL.labels(status="parse_error").inc()
    except Exception:
        pass
    return {"goal": "直接回答", "steps": [], "mode": "immediate", "constraints": {}}


def _extract_entities(user_msg: str) -> dict:
    """从用户输入中提取实体（简单实现：jieba 切词后取名词）。"""
    try:
        import jieba.posseg as pseg
        entities = {}
        for word, flag in pseg.cut(user_msg):
            if flag.startswith("n") and len(word) >= 2:
                if "keyword" not in entities:
                    entities["keyword"] = word
                entities[word] = word
        return entities
    except ImportError:
        # jieba 未安装，用简单分词
        words = user_msg.split()
        return {"keyword": words[0] if words else user_msg} if user_msg else {}


# 模板匹配（同步版，在线程池运行）
def _match_workflow_template_sync(user_msg: str, owner_id: str):
    """Jaccard 相似度匹配（同步版，运行在线程池中）。"""
    try:
        import jieba
    except ImportError:
        return None
    from backend.services.agent_service.workflows_db import WorkflowsDB
    db = WorkflowsDB()
    candidates = db.query(
        "SELECT * FROM workflows WHERE source IN ('preset','auto_template') AND enabled=1"
    )
    if not candidates:
        return None
    user_keywords = set(jieba.cut(user_msg))
    if not user_keywords:
        return None
    best_score, best_template = 0.0, None
    for t in candidates:
        pattern_text = (t.get("name") or "") + " " + (t.get("description") or "")
        pattern_keywords = set(jieba.cut(pattern_text))
        if not pattern_keywords:
            continue
        score = len(user_keywords & pattern_keywords) / max(len(user_keywords | pattern_keywords), 1)
        if score > best_score:
            best_score = score
            best_template = t
    return best_template if best_score > 0.6 else None


async def _match_workflow_template(user_msg: str, owner_id: str):
    """异步包装：模板匹配放线程池。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _match_workflow_template_sync, user_msg, owner_id
    )


def _instantiate_template(template: dict, user_msg: str) -> dict:
    """将 workflow 条目实例化为具体 plan。"""
    import json as _json
    from datetime import datetime
    steps = _json.loads(template["steps_json"])
    constraints = _json.loads(template.get("constraints_template") or "{}")
    entities = _extract_entities(user_msg)
    for step in steps:
        for key, val in list(step.get("params", {}).items()):
            if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
                ref = val[2:-2].strip()
                if ref.startswith("step_"):
                    continue
                if ref in entities:
                    step["params"][key] = entities[ref]
    try:
        from backend.services.agent_service.workflows_db import WorkflowsDB
        db = WorkflowsDB()
        with db._get_conn() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE workflows
                SET hit_count = hit_count + 1, last_hit = ?
                WHERE id = ?
            """, [datetime.now().isoformat(), template["id"]])
            conn.commit()
    except Exception as e:
        logger.warning(f"[Plan] 更新 hit_count 失败: {e}")
    return {
        "goal": f"复用模板: {template['name']}",
        "mode": "immediate",
        "constraints": constraints,
        "steps": steps,
        "from_template": True,
        "template_id": template["id"],
    }


# 约束注入映射
TOOL_CONSTRAINT_MAP = {
    "search_posts": ["preferred_platforms"],
    "filter_content": ["exclude", "language"],
    "generate_itinerary": ["budget_max", "accessibility", "duration", "exclude"],
    "extract_slots": ["exclude"],
}


def _inject_constraints(params: dict, constraints: dict, tool_name: str) -> dict:
    """将约束注入工具参数。"""
    allowed = TOOL_CONSTRAINT_MAP.get(tool_name, [])
    for key in allowed:
        if key in constraints and key not in params:
            params[key] = constraints[key]
    return params


# 异常检测
def _detect_anomaly(result) -> str:
    """检测步骤结果是否异常。"""
    import json as _json
    if isinstance(result, str):
        try:
            result = _json.loads(result)
        except Exception:
            return ""
    if not isinstance(result, dict):
        return ""
    if result.get("error"):
        return f"工具返回错误: {str(result['error'])[:100]}"
    raw_data = result.get("data")
    if isinstance(raw_data, dict):
        data = raw_data.get("posts") or raw_data.get("results")
    elif isinstance(raw_data, list):
        data = raw_data
    else:
        data = result.get("posts") or result.get("results")
    if isinstance(data, list) and len(data) == 0:
        return "返回空数据，可能是过滤条件过严或数据源无匹配"
    return ""


def _call_plan_adjust_llm_sync(prompt: str, owner_id: str) -> str:
    from openai import OpenAI
    from .agent_core import _get_agent_config_for
    key, url, model = _get_agent_config_for(owner_id)
    client = OpenAI(api_key=key, base_url=url)
    resp = client.chat.completions.create(
        model=model or settings.DEFAULT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200,
    )
    return resp.choices[0].message.content.strip()


async def _maybe_adjust_plan(step_result, step_idx: int, ctx: AgentContext) -> str:
    """检查步骤结果，必要时触发计划修正。

    ★ R-006：返回 emit_plan_adjusted 字符串或 None，不是 generator。
    """
    anomaly = _detect_anomaly(step_result)
    if not anomaly:
        return ""
    if ctx.plan.get("adjustment_count", 0) >= 2:
        logger.warning(f"[Plan] 已达最大调整次数 (2)，不再修正")
        return ""

    import json as _json
    from .prompts import PLAN_ADJUST_PROMPT

    adjust_prompt = PLAN_ADJUST_PROMPT.format(
        original_plan=_json.dumps(ctx.plan, ensure_ascii=False, default=str),
        failed_step=step_idx + 1,
        failed_result=_json.dumps(step_result, ensure_ascii=False, default=str)[:500],
        anomaly_reason=anomaly,
        remaining_steps=_json.dumps(ctx.plan["steps"][step_idx:], ensure_ascii=False, default=str),
    )
    try:
        loop = asyncio.get_running_loop()
        adjusted = await loop.run_in_executor(
            None, _call_plan_adjust_llm_sync, adjust_prompt, ctx.owner_id,
        )
        if not adjusted:
            logger.warning("[Plan] LLM 返回空内容，跳过计划修正")
            return ""
        new_steps_data = _json.loads(adjusted)
        ctx.plan["steps"] = ctx.plan["steps"][:step_idx] + new_steps_data["adjusted_steps"]
        ctx.plan["adjustment_note"] = new_steps_data.get("note", "")
        ctx.plan["adjustment_count"] = ctx.plan.get("adjustment_count", 0) + 1
        return emit_plan_adjusted(ctx.plan)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[Plan] 计划修正失败: {e}")
        return ""


async def _persist_workflow(ctx: AgentContext):
    """phase_plan 输出 mode=scheduled 时落库。"""
    import json as _json
    if not (ctx.plan and ctx.plan.get("mode") == "scheduled"):
        return None
    schedule = ctx.plan.get("schedule") or {}
    cron = schedule.get("cron", "")
    desc = schedule.get("description", "")
    if not cron:
        logger.warning(f"[Plan] mode=scheduled 但缺 cron 字段，跳过持久化")
        return None

    # 弱点2：cron 合法性校验
    cron_valid = True
    cron_error = ""
    try:
        from croniter import croniter
        croniter(cron)
    except ImportError:
        import re
        if not re.match(r"^[\d*/,\-\s]+$", cron):
            cron_valid = False
            cron_error = "cron 含非数字字符且 croniter 库未安装"
        else:
            parts = cron.split()
            if len(parts) not in (5, 6):
                cron_valid = False
                cron_error = f"cron 段数 {len(parts)} 不在 5/6 范围内"
    except Exception as e:
        cron_valid = False
        cron_error = str(e)

    try:
        from backend.services.agent_service.workflows_db import WorkflowsDB
        db = WorkflowsDB()
        wf_id = db.insert_workflow(
            owner_id=ctx.owner_id,
            name=ctx.plan.get("goal", "未命名工作流")[:200],
            steps_json=_json.dumps(ctx.plan.get("steps", []), ensure_ascii=False),
            constraints_template=_json.dumps(ctx.plan.get("constraints", {}), ensure_ascii=False),
            source="user",
            schedule_cron=cron,
            schedule_desc=desc,
            is_composite_tool=0,
            enabled=1 if cron_valid else 0,
        )
        ctx.workflow_id = wf_id
        ctx.cron_valid = cron_valid
        ctx.cron_error = cron_error
        return wf_id
    except Exception as e:
        logger.error(f"[Plan] 持久化 scheduled 工作流失败: {e}")
        return None


async def _maybe_save_template(ctx: AgentContext):
    """如果 Agent 自主完成所有步骤，UPSERT auto_template。

    弱点1：必须所有 critical 步骤都成功才累积。
    """
    import json as _json
    if not (ctx.plan and ctx.plan.get("steps")):
        return
    if ctx.plan.get("from_template"):
        return
    if ctx.user_intervened:
        return
    if ctx.plan.get("mode") == "scheduled":
        return

    step_results = ctx.plan.get("step_results", {})
    critical_failed = []
    for step in ctx.plan["steps"]:
        if step.get("criticality") != "critical":
            continue
        sid = step.get("step")
        sr = step_results.get(f"step_{sid}") or step_results.get(sid) or {}
        if isinstance(sr, str):
            try:
                sr = _json.loads(sr)
            except Exception:
                sr = {}
        success = sr.get("success", True) if isinstance(sr, dict) else True
        skipped = sr.get("skipped", False) if isinstance(sr, dict) else False
        if not success or skipped:
            critical_failed.append(sid)

    if critical_failed:
        logger.info(f"[Plan] 跳过 auto_template 累积：critical 步骤失败 {critical_failed}")
        return

    try:
        from backend.services.agent_service.workflows_db import WorkflowsDB
        db = WorkflowsDB()
        user_msg = _get_last_user_message(ctx)
        entities = _extract_entities(user_msg)
        kw = entities.get("keyword", "")
        name = user_msg.replace(kw, "{" + kw + "}") if kw else (ctx.plan.get("goal", "auto_template"))
        name = name[:200]
        constraints = _json.dumps(ctx.plan.get("constraints", {}), ensure_ascii=False)
        steps_json = _json.dumps(ctx.plan["steps"], ensure_ascii=False)
        wf_id = db.upsert_auto_template(
            owner_id=ctx.owner_id,
            name=name,
            steps_json=steps_json,
            constraints_template=constraints,
        )
        logger.info(f"[Plan] auto_template 累积: id={wf_id}, name={name}")
    except Exception as e:
        logger.warning(f"[Plan] 保存 auto_template 失败: {e}")


async def phase_plan(ctx: AgentContext):
    """四维智能规划：模板匹配 → LLM 规划 → 约束提取 → 关键路径。"""
    from backend.core.metrics import AGENT_PLAN_GENERATION_TOTAL

    user_msg = _get_last_user_message(ctx)
    if not user_msg:
        return

    # 维度2: 模板匹配
    try:
        template = await _match_workflow_template(user_msg, ctx.owner_id)
        if template and template.get("hit_count", 0) >= 2:
            plan = _instantiate_template(template, user_msg)
            ctx.plan = plan
            ctx.adjustment_count = 0
            ctx.user_intervened = False
            try:
                AGENT_PLAN_GENERATION_TOTAL.labels(status="template_hit").inc()
            except Exception:
                pass
            logger.info(f"[Plan] 模板命中: {template['name']} (hit_count={template['hit_count']})")
            yield emit_plan(plan)
            return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[Plan] 模板匹配异常（继续走 LLM）: {e}")

    # 维度1+3: LLM 规划
    from .prompts import PLAN_PROMPT
    plan_prompt = PLAN_PROMPT.format(
        user_message=user_msg,
        tools=_list_tool_names_for_planning(),
    )
    try:
        from .agent_core import _get_agent_config_for
        key, url, model = _get_agent_config_for(ctx.owner_id)
        client = OpenAI(api_key=key, base_url=url)
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=[{"role": "user", "content": plan_prompt}],
                temperature=0.2,
                max_tokens=400,
            ).choices[0].message.content.strip(),
        )
        plan = _parse_plan_json(content)
        try:
            AGENT_PLAN_GENERATION_TOTAL.labels(status="success").inc()
        except Exception:
            pass
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[Plan] LLM 规划失败，回退到无计划模式: {e}")
        plan = {"goal": "直接回答", "steps": [], "mode": "immediate", "constraints": {}}
        try:
            AGENT_PLAN_GENERATION_TOTAL.labels(status="fallback").inc()
        except Exception:
            pass

    ctx.plan = plan
    ctx.adjustment_count = 0
    ctx.user_intervened = False
    logger.info(f"[Plan] LLM 出 plan: goal={plan.get('goal', '')}, steps={len(plan.get('steps', []))}")
    yield emit_plan(plan)


# ──────────────── 主循环 ────────────────


