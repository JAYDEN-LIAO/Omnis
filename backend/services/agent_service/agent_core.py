# backend/services/agent_service/agent_core.py
"""
Agent Core - 主循环重构

架构：TokenBudgetManager → AgentMemory → ToolExecutor → ReflectionEngine → SelfHealingExecutor
"""
import json
import time
import uuid
import asyncio
from typing import Optional
from openai import OpenAI, AsyncOpenAI
from core.config import settings, get_agent_config
from core.logger import get_logger
from core.metrics import (
    AGENT_TURNS,
    AGENT_TOOL_CALLS,
    AGENT_TOOL_LATENCY,
    AGENT_MEMORY_WRITES,
)

logger = get_logger("agent")

# 导入工具适配器
from .tools import TOOLS_SCHEMA, AVAILABLE_TOOLS, STREAMABLE_TOOLS
from .sse import (
    emit_done,
    emit_error,
    emit_text,
    emit_tool_call,
    emit_tool_progress,
    emit_tool_result,
)
from .adapters import DirectAdapter, MCPAdapter
from .memory import AgentMemoryManager
from .reflection import ReflectionEngine
from .diagnosis import DiagnosisEngine

# ==================== v2.2 P1: Agent Context ====================
from dataclasses import dataclass, field
from typing import List as _List, Optional as _Optional

@dataclass
class AgentContext:
    """v2.2 P1：统一状态对象，贯穿所有 phase 函数。"""
    session_id: str
    owner_id: str
    request: dict
    messages: list                                  # 原始用户消息
    current_messages: list = field(default_factory=list)
    text_collector: _Optional[list] = None
    max_iterations: int = 6
    iteration: int = 0
    final_text: str = ""


# ==================== v2.2 P1: 工具结果截断 ====================
def _truncate_tool_result(result_str: str) -> str:
    """工具返回结果超过上限时截断，避免 LLM 上下文爆炸。"""
    max_chars = getattr(settings, "AGENT_MAX_TOOL_RESULT_CHARS", 3000)
    if len(result_str) > max_chars:
        return result_str[:max_chars] + f"\n\n...(结果已截断，共 {len(result_str)} 字符)"
    return result_str


# ==================== Token Budget Manager ====================

class TokenBudgetManager:
    """Token 预算管理器：实时计算 tokens，超限触发 context summarization"""

    def __init__(self, budget: int = None):
        self.budget = budget or getattr(settings, 'AGENT_TOKEN_BUDGET', 1500)

    def _fresh_client(self):
        """每次返回新 OpenAI 客户端实例（配置热刷新）"""
        key, url, _ = get_agent_config()
        return OpenAI(api_key=key, base_url=url)

    def count_tokens(self, messages: list) -> int:
        """估算 tokens（char/2 而非 char/4，中文偏差 < 20%）"""
        total = 0
        for m in messages:
            # ChatCompletionMessage 等 SDK 对象无法 json.dumps，先转 dict
            if hasattr(m, 'model_dump'):
                m = m.model_dump()
            total += len(json.dumps(m, ensure_ascii=False)) // 2
        return total

    def should_summarize(self, messages: list) -> bool:
        return self.count_tokens(messages) > self.budget

    def summarize_history(self, messages: list) -> list:
        """将历史压缩为摘要（使用 get_agent_config 替代硬编码 deepseek-chat）"""
        # 保留 system prompt + 最近 2 条 + 摘要
        system = messages[0] if messages and messages[0]["role"] == "system" else None
        recent = messages[-4:] if len(messages) > 4 else messages

        history_text = "\n".join([
            f"{'用户' if m['role']=='user' else '助手'}: {m['content'][:80]}"
            for m in recent if m.get("role") != "system"
        ])

        prompt = f"""将以下对话历史压缩为一段简洁摘要（100字以内）：

{history_text}

直接返回摘要，不要有其他内容。"""

        try:
            key, url, model = get_agent_config()
            response = self._fresh_client().chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3
            )
            summary = response.choices[0].message.content.strip()
        except Exception:
            summary = f"[历史对话，包含 {len(recent)} 条消息]"

        result = []
        if system:
            result.append(system)
        result.append({"role": "system", "content": f"【对话历史摘要】{summary}"})
        result.append({"role": "system", "content": "（以上为历史摘要，请基于此回答后续问题）"})
        result.extend(recent[-2:])  # 保留最近 2 条

        return result


# ==================== Tool Executor ====================

class ToolExecutor:
    """统一工具执行器：直调 / MCP 自适应"""

    def __init__(self):
        self.direct = DirectAdapter()
        self.mcp = MCPAdapter() if getattr(settings, 'AGENT_MCP_ENABLED', False) else None
        self.diagnosis_engine = DiagnosisEngine()

    async def execute(
        self,
        tool_name: str,
        args: dict,
        messages: list,
        on_progress=None,
        _request: Optional[dict] = None,
    ) -> str:
        """
        执行工具：
        1. 优先直调（快）
        2. 直调失败且启用 MCP → 走 MCP HTTP
        3. 所有工具走 SelfHealingExecutor
        4. 记录 AGENT_TOOL_CALLS / AGENT_TOOL_LATENCY 指标

        v2.2 P2 新增：
        - on_progress(partial)：流式工具调它推送增量；普通工具为 None
        - _request：请求上下文 dict（owner_id/session_id/trace_id），
          DirectAdapter 会把它注入到工具函数（仅当函数声明 `_request=None` 参数时）
        """
        import time as _time
        start_ts = _time.perf_counter()
        status_label = "success"
        _owner_id = (_request or {}).get("owner_id", "")

        # 优先直调
        if self.direct.supports(tool_name):
            try:
                result = await self.diagnosis_engine.execute_with_diagnosis(
                    self.direct.execute,
                    {
                        "tool_name": tool_name,
                        "args": args,
                        "on_progress": on_progress,
                        "_request": _request,
                    },
                    tool_name=tool_name,
                    other_tools={k: v for k, v in AVAILABLE_TOOLS.items() if k != tool_name},
                    owner_id=_owner_id,
                )
                # 解析 DirectAdapter.execute 返回（它是两层 JSON）
                parsed = json.loads(result)
                if not parsed.get("success", False):
                    status_label = "error"
                    # 直调失败，尝试 MCP
                    if self.mcp:
                        logger.info(f"[ToolExecutor] 直调 {tool_name} 失败，切换 MCP...")
                        mcp_result = await self.diagnosis_engine.execute_with_diagnosis(
                            self.mcp.execute,
                            {
                                "tool_name": tool_name,
                                "args": args,
                                "on_progress": on_progress,
                                "_request": _request,
                            },
                            tool_name=tool_name,
                            owner_id=_owner_id,
                        )
                        return mcp_result
                return result
            except Exception as e:
                status_label = "error"
                raise
            finally:
                # 记录指标
                latency = _time.perf_counter() - start_ts
                AGENT_TOOL_CALLS.labels(tool=tool_name, status=status_label).inc()
                AGENT_TOOL_LATENCY.labels(tool=tool_name).observe(latency)

        # MCP 专属工具
        if self.mcp and self.mcp.supports(tool_name):
            try:
                return await self.diagnosis_engine.execute_with_diagnosis(
                    self.mcp.execute,
                    {
                        "tool_name": tool_name,
                        "args": args,
                        "on_progress": on_progress,
                        "_request": _request,
                    },
                    tool_name=tool_name,
                    owner_id=_owner_id,
                )
            except Exception as e:
                status_label = "error"
                raise
            finally:
                latency = _time.perf_counter() - start_ts
                AGENT_TOOL_CALLS.labels(tool=tool_name, status=status_label).inc()
                AGENT_TOOL_LATENCY.labels(tool=tool_name).observe(latency)

        return json.dumps({
            "success": False,
            "data": None,
            "error": f"不支持的工具: {tool_name}",
            "error_type": "unknown"
        }, ensure_ascii=False)


# ==================== Agent 主循环 ====================

# 全局组件实例（客户端不缓存，每次 _get_agent_client 重新创建以支持热刷新）
memory_manager = AgentMemoryManager()
reflection_engine = ReflectionEngine()
token_budget_manager = TokenBudgetManager()
tool_executor = ToolExecutor()


def _get_agent_config_for(owner_id: str = ""):
    """v2.2 per-user：优先读用户 model_config，未配置时回退全局"""
    if owner_id:
        from core.config import get_agent_config_for_user
        return get_agent_config_for_user(owner_id)
    return get_agent_config()


def _get_agent_client(owner_id: str = ""):
    """返回全新 OpenAI 客户端（配置热刷新）"""
    key, url, _ = _get_agent_config_for(owner_id)
    return OpenAI(api_key=key, base_url=url)


# ==================== 每 session 最多 1 次 medi 追问 ====================
# 每新用户消息调用函数时 medi_count 重置为 0，
# 改为 session 级状态：module-level dict + TTL 懒清理，跨 chat 调用共享计数。
_SESSION_MEDI_TTL_SEC = 3600  # 1 小时不活跃即清空（防止内存膨胀）
_session_medi_followups: dict[str, tuple[int, float]] = {}  # session_id -> (count, last_used_ts)


def _try_acquire_medi_slot(session_id: str) -> bool:
    """
    尝试占用一次 medi 追问配额（每 session 最多 1 次）。
    返回 True=成功占用（已 +1），False=本 session 已达上限。

    设计：
    - key=session_id：跨 chat_with_agent_stream 调用共享
    - TTL=1h：避免内存膨胀（旧 session 自动清理）
    - 进程重启清空：可接受（session 客户端通常也会重新建立连接）
    - session_id 空/None 时不限制（防御性，单轮调试场景）
    """
    if not session_id:
        return True
    now = time.time()
    cutoff = now - _SESSION_MEDI_TTL_SEC
    # 懒清理过期项（避免长跑进程内存膨胀）
    expired_keys = [k for k, (_, ts) in _session_medi_followups.items() if ts < cutoff]
    for k in expired_keys:
        _session_medi_followups.pop(k, None)

    count, _ = _session_medi_followups.get(session_id, (0, now))
    if count >= 1:
        return False
    _session_medi_followups[session_id] = (count + 1, now)
    return True


def _get_medi_slot_status(session_id: str) -> dict:
    """
    暴露 session 的 medi 配额状态（供调试 / 可观测性）。
    无记录返回 {"count": 0, "used": False, "last_used_ts": None}。
    """
    if not session_id:
        return {"count": 0, "used": False, "last_used_ts": None}
    count, ts = _session_medi_followups.get(session_id, (0, 0.0))
    return {
        "count": count,
        "used": count >= 1,
        "last_used_ts": ts if ts else None,
    }



# ==================== v2.2 P1: 阶段函数 ====================
def phase_build_context(ctx: AgentContext):
    """构造 current_messages，注入 system prompt + 长期记忆。"""
    system_prompt = {
        "role": "system",
        "content": "你是 MediaRadar 媒体信息订阅平台的 AI 管家。回答专业简洁，用中文。"
    }
    working_memory = memory_manager.build_working_memory(ctx.session_id, owner_id=ctx.owner_id)
    if working_memory:
        system_prompt["content"] += f"\n\n【用户记忆】\n{working_memory}"
    ctx.current_messages = [system_prompt] + list(ctx.messages)
    # 首次 token 预算检查
    if token_budget_manager.should_summarize(ctx.current_messages):
        ctx.current_messages = token_budget_manager.summarize_history(ctx.current_messages)
    ctx.max_iterations = getattr(settings, "AGENT_MAX_ITERATIONS", 6)


def phase_think(ctx: AgentContext):
    """LLM 调用 + 3 次重试。返回 (msg, tool_calls) 或 (None, None)。"""
    for attempt in range(3):
        try:
            client = _get_agent_client(ctx.owner_id)
            _, _, model = _get_agent_config_for(ctx.owner_id)
            response = client.chat.completions.create(
                model=model or settings.DEFAULT_MODEL,
                messages=ctx.current_messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            if msg.content:
                msg.content = (
                    msg.content.replace("<|DSML|>", "").replace("</|DSML|>", "").strip()
                )
            return msg, msg.tool_calls
        except Exception as e:
            logger.warning(f"[phase_think] 第 {attempt+1} 次失败: {e}")
            if attempt == 2:
                logger.error(f"[phase_think] 3 次重试全部失败: {e}")
                return None, None
            time.sleep(2 ** attempt)
    return None, None


async def phase_respond(ctx: AgentContext):
    """流式生成最终回答。AsyncOpenAI 失败时 emit_error，不静默。"""
    # 提示 LLM 用自然语言回答
    ctx.current_messages.append({
        "role": "system",
        "content": "请用自然语言回答用户，不要输出JSON或代码格式。"
    })
    try:
        key, url, model = _get_agent_config_for(ctx.owner_id)
        client = AsyncOpenAI(api_key=key, base_url=url)
        response = await client.chat.completions.create(
            model=model or settings.DEFAULT_MODEL,
            messages=ctx.current_messages,
            stream=True,
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                if ctx.text_collector is not None:
                    ctx.text_collector.append(text)
                yield emit_text(text)
    except Exception as e:
        logger.error(f"[phase_respond] 流式生成失败: {e}", exc_info=True)
        yield emit_error(f"生成回复失败: {e}", error_type="stream_error")


async def phase_act(ctx: AgentContext, tool_call):
    """
    执行单个工具。yield SSE 事件，最后 yield 一个 _PHASE_ACT_DONE 信号携带解析结果。
    失败/超时 yield emit_error 但不中断流程，由主循环 continue 走下一轮。
    """
    from collections import deque

    call_id = tool_call.id
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
    except Exception:
        args = {}

    yield emit_tool_call(call_id, name, args)

    progress_queue = deque()

    def on_progress(partial, _cid=call_id):
        progress_queue.append((_cid, partial))

    try:
        result = await asyncio.wait_for(
            tool_executor.execute(
                name, args, ctx.current_messages,
                on_progress=on_progress, _request=ctx.request,
            ),
            timeout=getattr(settings, "AGENT_TOOL_TIMEOUT", 120),
        )
    except asyncio.TimeoutError:
        logger.error(f"[phase_act] 工具 {name} 超时")
        yield emit_error(f"工具 {name} 执行超时", error_type="timeout", call_id=call_id)
        yield _PHASE_ACT_DONE(None)
        return
    except Exception as e:
        logger.error(f"[phase_act] 工具 {name} 异常: {e}", exc_info=True)
        yield emit_error(f"工具 {name} 执行失败: {e}", error_type="tool_error", call_id=call_id)
        yield _PHASE_ACT_DONE(None)
        return

    # flush progress
    while progress_queue:
        yield emit_tool_progress(*progress_queue.popleft())

    # 截断
    result = _truncate_tool_result(result)

    # 解析
    try:
        parsed = json.loads(result)
    except Exception:
        parsed = {"success": False, "data": None, "error": "工具返回非 JSON", "error_type": "tool_format_error"}

    yield emit_tool_result(
        call_id=call_id,
        success=parsed.get("success", False),
        data=parsed.get("data"),
        ui=parsed.get("ui") or {},
        error=parsed.get("error", ""),
        error_type=parsed.get("error_type", ""),
    )
    yield _PHASE_ACT_DONE(parsed)


_PHASE_ACT_DONE_MARKER = "__phase_act_result__"


def _PHASE_ACT_DONE(value):
    """phase_act 完成信号（async generator 不能 return value，用 yield 替代）"""
    return {_PHASE_ACT_DONE_MARKER: value}


def phase_evaluate(ctx: AgentContext, tool_result: dict) -> str:
    """
    评估工具结果。返回 "high" | "medi" | "low"。
    失败时返回 "high"（不阻塞主流程）。
    """
    try:
        tool_result_str = json.dumps(tool_result, ensure_ascii=False)
        user_q = ctx.messages[-1]["content"] if ctx.messages else ""
        eval_result = reflection_engine.evaluate(
            user_q, tool_result_str, owner_id=ctx.owner_id
        )
        confidence = eval_result.get("confidence", "high")
        if confidence not in ("high", "medi", "low"):
            return "high"
        return confidence
    except Exception as e:
        logger.warning(f"[phase_evaluate] 异常: {e}")
        return "high"


async def phase_finish(ctx: AgentContext, final_text: str = ""):
    """
    统一收尾。所有 exit 都走这里（无遗漏）。emit_done 后异步写记忆。
    """
    if final_text:
        if ctx.text_collector is not None:
            ctx.text_collector.append(final_text)
        yield emit_text(final_text)
    yield emit_done()
    asyncio.create_task(_write_memory_async(
        ctx.session_id, ctx.messages, ctx.owner_id, ctx.text_collector
    ))


async def chat_with_agent_stream(
    messages: list,
    session_id: str = None,
    _request: Optional[dict] = None,
):
    """
    Agent 主循环（v2.2 P1 重构版）

    事件顺序：text / tool_call / [tool_progress]* / tool_result / text / done
    统一收尾：所有 exit 都走 phase_finish()，修复原版漏写 _write_memory_async 的 bug。
    """
    session_id = session_id or str(uuid.uuid4())
    owner_id = (_request or {}).get("owner_id", "")
    _text_collector: list = (_request or {}).get("_text_collector")

    ctx = AgentContext(
        session_id=session_id,
        owner_id=owner_id,
        request=_request or {},
        messages=messages,
        text_collector=_text_collector,
    )
    phase_build_context(ctx)

    for i in range(ctx.max_iterations):
        ctx.iteration = i
        logger.info(f"[Agent Core] 第 {i+1} 轮思考")
        AGENT_TURNS.inc()

        # 1) Think
        msg, tool_calls = phase_think(ctx)
        if msg is None:
            async for chunk in phase_finish(ctx, "LLM 调用失败，请稍后重试。"):
                yield chunk
            return

        # 把 assistant 消息加入上下文
        ctx.current_messages.append(msg.model_dump())

        if not tool_calls:
            # 2) Respond (无工具调用 → 流式回答)
            async for chunk in phase_respond(ctx):
                yield chunk
            async for chunk in phase_finish(ctx):
                yield chunk
            return

        # 3) Act + Evaluate (对每个 tool_call)
        for tc in tool_calls:
            parsed = None
            gen = phase_act(ctx, tc)
            try:
                while True:
                    chunk = await gen.__anext__()
                    if isinstance(chunk, dict) and _PHASE_ACT_DONE_MARKER in chunk:
                        parsed = chunk[_PHASE_ACT_DONE_MARKER]
                        break
                    yield chunk
            except Exception as e:
                logger.error(f"[MainLoop] phase_act 异常: {e}", exc_info=True)
                yield emit_error(f"工具执行异常: {e}", error_type="tool_execution_error", call_id=tc.id)
                parsed = None

            if parsed is None:
                continue  # 工具失败/超时，让 LLM 下一轮决定

            # 工具结果入上下文
            ctx.current_messages.append({
                "tool_call_id": tc.id, "role": "tool", "name": tc.function.name,
                "content": json.dumps(parsed, ensure_ascii=False),
            })

            # 4) Evaluate
            confidence = phase_evaluate(ctx, parsed)

            if confidence == "low":
                degrade = reflection_engine.get_degrade_answer(json.dumps(parsed, ensure_ascii=False))
                ctx.final_text = degrade
                async for chunk in phase_finish(ctx, degrade):
                    yield chunk
                return

            if confidence == "medi":
                if _try_acquire_medi_slot(ctx.session_id):
                    user_q = ctx.messages[-1]["content"] if ctx.messages else ""
                    missing = ""
                    medi_action = reflection_engine.handle_medi(
                        user_q,
                        json.dumps(parsed, ensure_ascii=False),
                        missing,
                        owner_id=ctx.owner_id,
                    )
                    follow_up = medi_action.get("follow_up_question", "")
                    if follow_up:
                        ctx.current_messages.append({
                            "role": "user",
                            "content": f"【系统追问】{follow_up}",
                        })
                        continue
                    # 没拿到 follow_up_question → 降级
                    degrade = (
                        medi_action.get("degrade_answer", "")
                        or reflection_engine.get_degrade_answer(json.dumps(parsed, ensure_ascii=False))
                    )
                    async for chunk in phase_finish(ctx, degrade):
                        yield chunk
                    return
                else:
                    degrade = reflection_engine.get_degrade_answer(json.dumps(parsed, ensure_ascii=False))
                    async for chunk in phase_finish(ctx, degrade):
                        yield chunk
                    return
            # high → 继续

        # 5) Token 预算检查（每轮迭代后）
        try:
            if token_budget_manager.should_summarize(ctx.current_messages):
                ctx.current_messages = token_budget_manager.summarize_history(ctx.current_messages)
        except Exception as e:
            logger.warning(f"[Agent Core] Token 摘要失败: {e}")

    # 超过最大迭代次数
    async for chunk in phase_finish(ctx, "抱歉，处理该指令时逻辑过于复杂，已自动中止。请换个问法。"):
        yield chunk


async def _write_memory_async(
    session_id: str,
    messages: list,
    owner_id: str = "",
    _text_collector: list = None,
):
    """
    异步写入对话记忆 + 聊天消息（v2.2 P3.1：失败重试一次）。
    """
    # 重试一次：首次失败 sleep 1s 再试
    last_err = None
    for attempt in range(2):
        try:
            memory_manager.write_from_conversation(session_id, messages, owner_id=owner_id)
            AGENT_MEMORY_WRITES.labels(status="success").inc()
            last_err = None
            break
        except Exception as e:
            last_err = e
            logger.warning(f"[MemoryWrite] 第 {attempt+1} 次失败: {e}")
            if attempt == 0:
                await asyncio.sleep(1)
    if last_err:
        AGENT_MEMORY_WRITES.labels(status="error").inc()
        logger.error(f"记忆写入彻底失败: {last_err}")

    # chat_messages 写入（同样加重试）
    if session_id and messages:
        for attempt in range(2):
            try:
                all_messages = list(messages)
                if _text_collector is not None:
                    assistant_text = "".join(_text_collector).strip()
                    if assistant_text:
                        all_messages.append({"role": "assistant", "content": assistant_text})
                memory_manager.store.replace_messages(session_id, owner_id, all_messages)
                logger.info(f"[ChatMessages] session {session_id[:8]} 已保存 {len(all_messages)} 条消息")
                break
            except Exception as e:
                logger.warning(f"[ChatMessages] 第 {attempt+1} 次失败: {e}")
                if attempt == 0:
                    await asyncio.sleep(1)
                else:
                    logger.error(f"[ChatMessages] 保存彻底失败: {e}")
