# Phase 3: 直接聊天交互体验 - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

让用户在 IM 中可以像直接操控 Coding Agent 一样发起任务、接收即时反馈、看到执行过程中的关键状态，并通过纯文本确认与显式会话命令控制上下文边界。这个 phase 聚焦 slash-command 聊天体验本身，包括把 ACP 服务器返回的对话信息稳定传回 AstrBot；tool 返回 schema 与统一高层安全策略属于 Phase 4。

</domain>

<decisions>
## Implementation Decisions

### 基础回传链路

- **D-01:** Phase 3 必须先修好“ACP 服务器返回的对话信息传回 AstrBot”的基础链路，再在其上优化交互体验。
- **D-02:** `message_chunk` 一类正文增量消息纳入 Phase 3 范围，不再继续只依赖结构化事件和最终结果。
- **D-03:** 正文回传采用节流/合并后的稳定增量展示，而不是逐 token 或逐小片段刷屏。

### 过程播报策略

- **D-04:** 执行中的聊天播报以关键节点为主：已接收/开始、关键计划变化、权限确认、完成/失败等必须可见。
- **D-05:** 在关键节点之外补充“极简工具流”信息，但不做完整工具级细节刷屏。

### 权限确认呈现

- **D-06:** 权限确认消息改为更适合 IM 阅读的分行说明，明确操作类型、目标对象和可选项。
- **D-07:** 权限确认仍保持纯文本编号或关键词回复的交互方式；超时、拒绝时默认失败关闭。

### 会话命令回显

- **D-08:** `/oc-new`、`/oc-end`、`/oc-session` 的结果提示采用“摘要优先”策略。
- **D-09:** 默认只展示少量关键状态：工作目录、当前会话绑定、当前 agent/mode；默认偏好和完整状态快照不再每次全部展开。

### 错误与帮助提示

- **D-10:** 命令缺参、用法错误、目标不存在等场景，提示先说明问题，再给 1-2 条用户可直接照抄的命令示例。
- **D-11:** CHAT-05 的帮助提示应优先服务立即纠错，而不是长篇教学说明。

### Folded Todos

- 将“简化 slash-command 与 sender 状态提示”并入本 phase，作为过程播报与生命周期回显收敛的一部分。
- 将“修好 ACP 服务器对话信息回传到 AstrBot”并入本 phase，作为直接聊天交互体验的前置基础能力。

### the agent's Discretion

- 正文节流的时间窗口、字符阈值与 flush 时机
- 哪些 tool 事件属于“极简工具流”而哪些应被折叠掉
- 分行权限确认的具体排版和措辞
- 各命令示例的精确文案与条数

</decisions>

<canonical_refs>

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase and project boundary

- `.planning/ROADMAP.md` — Phase 3 的目标、成功标准与与 Phase 4 的边界
- `.planning/PROJECT.md` — 产品定位、`stdio` 约束、slash-command 与 tool 输出归属分离
- `.planning/REQUIREMENTS.md` — CHAT-01~05、SAFE-02 的正式需求定义
- `.planning/STATE.md` — 当前阶段上下文、已知 concern，以及与 Phase 3 相关的 pending todos

### Prior decisions

- `.planning/phases/02.2-astrbot-acp-opencode-acp-server/02.2-CONTEXT.md` — 参考文档基线；确认后续 Phase 3/4 应优先依赖 `docs/references/` 作为规范导航

### Protocol and host references

- `docs/references/README.md` — Phase 3/4 的统一参考入口与阅读顺序
- `docs/references/astrbot/README.md` — AstrBot 消息发送、session waiter、命令反馈与会话控制映射
- `docs/references/acp/README.md` — `session/prompt`、`session/update`、`session/request_permission`、事件回传边界
- `docs/references/opencode/README.md` — OpenCode 作为本地 `stdio` ACP server 的职责、支持面与限制

</canonical_refs>

<code_context>

## Existing Code Insights

### Reusable Assets

- `main.py:_run_oc_prompt` — 已经串起执行开始提示、流式事件消费、权限确认和最终输出发送，是 Phase 3 最直接的聊天链路入口。
- `core/executor.py:_stream_execution` / `_handle_client_notification` — 已具备把 ACP runtime notification 转成流式事件的底座。
- `core/output.py:build_chat_updates` — 已集中处理聊天进度折叠；后续可在这里扩展“极简工具流”和正文 chunk 展示策略。
- `main.py:_render_exec_status`、`_render_lifecycle_status` — 当前状态提示与生命周期回显模板，可在此基础上做“摘要优先”收敛。
- `main.py:_wait_for_permission_choice` + `session_waiter` — 已有纯文本确认等待机制，可复用到改进后的权限确认呈现。

### Established Patterns

- slash-command 与 tool 必须共用同一套执行内核，但聊天输出语义与 tool 输出归属不能混淆。
- 运行时事件优先通过 executor 的 ACP notification 流转，不应额外发明协议外旁路。
- 输出处理应继续收敛到 `OutputProcessor`，避免在命令处理器里散落新的渲染分支。
- 会话边界由 `SessionManager` 和现有 lifecycle 命令维护，Phase 3 关注的是提示语义和用户感知，而不是重写生命周期模型。

### Integration Points

- `core/executor.py` runtime notifications -> `main.py:_run_oc_prompt` -> `core/output.py:build_chat_updates` -> AstrBot 聊天消息
- `core/executor.py:_extract_output_text` / ExecutionResult -> `core/output.py:build_final_result_plan` -> 最终文本输出
- `/oc-new`、`/oc-end`、`/oc-session` 位于 `main.py`，需要与新的“摘要优先”回显策略一起收敛
- 相关验证入口已存在于 `tests/test_main_commands.py` 与 `tests/core/test_output_events.py`

</code_context>

<specifics>
## Specific Ideas

- 目标体验是“像直接操控 Coding Agent”，而不是只在最后收到一段长文本。
- 过程感要保留，但必须避免 IM 环境被工具细节或正文碎片刷屏。
- 当前最先要补的是 ACP 服务器对话信息回传到 AstrBot 这条基础能力；交互优化建立在这条链路可用的前提上。

</specifics>

<deferred>
## Deferred Ideas

- `重构 main.py` — 属于更宽泛的代码结构治理，不作为 Phase 3 的锁定交付结果；若 Phase 3 中需要局部重构，应以支撑聊天链路改造为限。

### Reviewed Todos (not folded)

- `重构 main.py` — 已审阅，但其范围超出本 phase 的用户可见交互边界，保留为后续结构治理议题。

</deferred>

---

_Phase: 03-直接聊天交互体验_
_Context gathered: 2026-03-30_
