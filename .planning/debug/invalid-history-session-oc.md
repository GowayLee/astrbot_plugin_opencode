---
status: investigating
trigger: "Issue from Phase 02 UAT. Goal: find_root_cause_only. Expected behavior: 当 sender 绑定到失效历史会话后，再次执行 `/oc` 应先清掉坏绑定并恢复到可继续对话的状态，而不是因为会话管理异常导致检查无法成立。 Actual behavior: 用户报告“每次调用`/oc`都会新建一个会话, 所以当前检查点无意义”。 Severity: major. Reproduction: Test 2 in `/home/LiHaoyuan/workspace/cool_stuff/astrbot_plugin_opencode/.planning/phases/02-会话内核与生命周期统一/02-UAT.md`. Timeline: Discovered during UAT."
created: 2026-03-29T16:36:26Z
updated: 2026-03-29T16:40:05Z
---

## Current Focus

hypothesis: 根因是执行器没有区分“当前连接里已 live 的 session”和“需要从历史恢复的 session”。只要 `backend_session_id` 存在，`_ensure_session_ready()` 就会再次调用 `session/load`；这会把普通连续 `/oc` 误当成历史恢复路径，若 load 失败就直接丢绑定并 `session/new`，于是用户看到每次都新建 session。
test: 用协议文档核对 `session/new -> session/prompt` 与 `session/load` 的适用边界，再对照 `core/executor.py`、`core/session.py` 和现有测试，确认代码是否真的缺少“当前 live 已就绪”状态判定。
expecting: 若协议要求连续对话直接复用现有 sessionId 发 `session/prompt`，而代码却在每次已有 ID 时都先 `session/load`，那么 Test 1 与 Test 2 都会被这个上游设计错误扭曲。
next_action: 汇总协议文档、执行器逻辑和测试中对 `session/load` 的错误假设，形成最终根因结论。

## Symptoms

expected: 当 sender 绑定到失效历史会话后，再次执行 `/oc` 应先清掉坏绑定并恢复到可继续对话的状态，而不是因为会话管理异常导致检查无法成立。
actual: 用户报告“每次调用`/oc`都会新建一个会话, 所以当前检查点无意义”。
errors: 无明确报错；表现为 `/oc` 每次都会新建一个 session，导致无法验证失效历史会话绑定后的恢复逻辑。
reproduction: Test 2 in `.planning/phases/02-会话内核与生命周期统一/02-UAT.md`.
started: Discovered during UAT.

## Eliminated

- hypothesis: `loadSession` 能力字段读取错了，导致 `_ensure_session_ready()` 始终误判为“不支持恢复”。
  evidence: ACP 官方 initialization / session-setup 文档明确 `loadSession` 位于 `initialize` 响应的 `agentCapabilities`；`core/acp_client.py` 也确实优先读取 `agentCapabilities`。因此能力字段映射本身不是本次问题的主因。
  timestamp: 2026-03-29T16:36:26Z

## Evidence

- timestamp: 2026-03-29T16:36:26Z
  checked: .planning/debug/knowledge-base.md
  found: 未找到 knowledge base 文件。
  implication: 本次调查没有可直接复用的历史已知模式，需要从代码事实重新建模。

- timestamp: 2026-03-29T16:36:26Z
  checked: core/AGENTS.md 与 main.py 符号搜索
  found: `/oc` 主流程位于 main.py 的 `_prepare_oc_execution`、`_start_oc_execution`、`oc_handler`；`/oc-session` 位于 `oc_session`，会话状态源头在 `core/session.py`，后端调用在 `core/executor.py`。
  implication: 已定位需要完整阅读的核心代码路径。

- timestamp: 2026-03-29T16:36:26Z
  checked: main.py、core/session.py、core/executor.py
  found: `/oc` 复用 sender 级 `OpenCodeSession`；真正决定是否续用历史/当前 backend session 的逻辑在 `CommandExecutor._ensure_session_ready()`。该函数在 `session.backend_session_id` 存在时，只有 `load_supported` 为真才会调用 `client.load_session(...)`；否则会直接 `session.drop_backend_session()` 并创建新会话。
  implication: “每次 `/oc` 新建 session” 不像是 handler 丢 session，更像是执行器判定“后端不支持 loadSession”后主动丢弃绑定造成的。

- timestamp: 2026-03-29T16:36:26Z
  checked: core/acp_client.py
  found: ACP initialize 后，`ACPClient.protocol_capabilities` 被赋值为 `response.get("agentCapabilities") or response.get("capabilities") or {}`。
  implication: 结合 ACP 官方文档可知这里对 `loadSession` 的读取方向基本正确，能力字段映射不是最可能根因。

- timestamp: 2026-03-29T16:36:26Z
  checked: ACP 官方文档 `protocol/initialization` 与 `protocol/session-setup`
  found: 文档明确 `loadSession` 是 `initialize` 响应里 `agentCapabilities` 的能力；`session/load` 只用于“resume previous conversations”，而完成 `session/new` 或 `session/load` 后，客户端即可继续发送 `session/prompt`。
  implication: 在同一连接里的连续对话不应每轮都先走 `session/load`；`session/load` 是历史恢复路径，不是普通 prompt 前置动作。

- timestamp: 2026-03-29T16:36:26Z
  checked: core/executor.py `_ensure_session_ready()` 与 core/session.py `OpenCodeSession`
  found: 代码里没有任何字段区分“当前 live session 已经在此 ACP client 中创建/恢复完成”与“仅有一个待恢复的历史 session_id”。只要 `session.backend_session_id` 存在，且 `loadSession` 支持为真，就会再次发 `client.load_session(...)`；若失败则 `session.drop_backend_session()` 后立刻 `_create_session()`。
  implication: 同一 sender 连续执行 `/oc` 时，第一轮创建出的 live session 也会在第二轮被误走历史恢复路径；一旦 backend 对该 `session/load` 不接受，就会直接新建 fresh session，表现为“每次 /oc 都新建会话”。

- timestamp: 2026-03-29T16:36:26Z
  checked: tests/core/test_executor_acp.py
  found: 现有测试 `test_executor_loads_existing_session_when_backend_supports_recovery` 明确把“只要已有 backend_session_id，下一轮 run_prompt 就应先调 session/load”写成了期望；仓库中没有测试覆盖“同一 live session 连续 /oc 直接 prompt、不得重复 load”的协议边界。
  implication: 该错误假设被测试固化，导致实现虽然符合单测，却与 UAT 暴露出的真实连续对话语义不一致。

## Resolution

root_cause:
fix:
verification:
files_changed: []
