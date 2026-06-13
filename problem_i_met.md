# 已知问题

## P1. 上下文重建的竞态窗口

**问题**：`_write_memory_async` 是异步后台任务，`phase_build_context` 从 DB 重建历史时可能读到落后一轮的数据。

**触发条件**：用户在当前轮次 stream 结束后很快（< 1-2s）发送下一条消息，此时上一轮的 `_write_memory_async` 还未完成 `replace_messages`，`get_messages` 返回的是上上轮的数据，导致最新一轮的对话内容从 LLM 上下文中丢失。

**原因**：`chat_messages` 写入和 LLM 抽取在同一个异步任务里串行执行，消息表不是即时更新的。

**当前缓解**：
- `_write_memory_async` 中已将 `replace_messages` 移到 LLM 抽取之前（SQLite 写入优先，约 <10ms）
- 无摘要时回退到尾消息重建

**理想修复**（未实现）：`replace_messages` 应在 stream 结束时同步写入（而非异步），或者使用版本号机制检测数据陈旧程度。

---

## P2. 尾巴消息数硬编码

**问题**：`phase_build_context` 从 `chat_messages` 取最近 N 条作为上下文尾巴，目前 N=6 是硬编码。

**影响**：
- 短场景（单轮问答）够用
- 长场景（多工具调用、多轮 Agent 推理）可能截断关键上下文

**当前状态**：结构约束 + 摘要兜底，6 条在绝大多数场景下够用。

**理想修复**（未实现）：根据 `ctx.current_messages` 实际 token 占用动态调整 N，或根据工具调用链长度自适应。
