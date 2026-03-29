---
status: diagnosed
phase: 02-会话内核与生命周期统一
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md]
started: 2026-03-29T16:12:07Z
updated: 2026-03-29T16:41:38Z
---

## Current Test

[testing complete]

## Tests

### 1. 连续 `/oc` 对话会沿用同一 sender 会话

expected: 在同一发送者下，先用 `/oc` 发起一个需要记住上下文的请求，再紧接着发送一个依赖上文的跟进问题。第二次回复应延续第一次的上下文，不需要你重新重复前文信息，也不会像全新会话那样失忆。
result: issue
reported: "我实际测试了连续两个`/oc`指令, 发现ACP服务器实际上创建了两个session"
severity: major

### 2. 绑定失效历史会话后再次 `/oc` 仍能回到可用状态

expected: 如果当前 sender 绑定到了一个已经失效或不可恢复的历史会话，再执行 `/oc` 时，插件应明确清掉失效绑定并恢复到可继续对话的状态。表现上不应卡在半绑定状态，也不应后续每次都重复报同一个坏会话错误。
result: issue
reported: "每次调用`/oc`都会新建一个会话, 所以当前检查点无意义"
severity: major

### 3. `/oc-new` 不带路径时会回到默认工作目录并解除当前绑定

expected: 执行 `/oc-new` 且不提供路径后，返回消息会显示已切回默认工作目录，同时当前会话处于未绑定状态。之后再发 `/oc` 会从新的会话上下文开始。
result: pass

### 4. `/oc-new <existing-path>` 会切换到目标目录并保留可用状态快照

expected: 执行 `/oc-new <已存在目录>` 后，返回消息会显示当前工作目录已切换到目标目录，并给出当前 sender 的状态快照。后续在该目录上下文中执行 `/oc` 不会仍停留在旧目录。
result: pass

### 5. `/oc-end` 在有会话和无会话两种情况下都返回稳定状态快照

expected: 无论当前是否已有 live session，执行 `/oc-end` 都会返回当前 sender 的工作目录、默认偏好和当前绑定状态。若原本已有会话，则结束后显示未绑定；若原本就没有会话，也不会只得到一句模糊的“没有活跃会话”。
result: pass

### 6. `/oc-session` 在恢复失败时会 fail-closed 回退到未绑定状态

expected: 执行 `/oc-session` 查看或切换历史会话时，返回内容会带上当前 sender 的状态信息。如果尝试绑定的历史会话已经不可恢复，插件会明确提示失败，并把当前 sender 回退到未绑定状态，而不是残留一个看似已绑定但实际上不可用的会话。
result: issue
reported: "`/oc-session`的交互没有问题. 但是如果尝试绑定不存在的session, 它没有去检查session是否存在, 没有错误提示, 依然绑定了一个不存在的会话. 而且工作目录也没有改变会被绑定会话的目录"
severity: major

## Summary

total: 6
passed: 3
issues: 3
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "在同一发送者下连续执行 `/oc` 时，第二次请求应复用第一次建立的会话上下文，而不是新建 session"
  status: failed
  reason: "User reported: 我实际测试了连续两个`/oc`指令, 发现ACP服务器实际上创建了两个session"
  severity: major
  test: 1
  root_cause: "`CommandExecutor._ensure_session_ready()` 把继续使用当前 sender 已绑定 live backend session 错误依赖在可选的 `loadSession` 能力上；当协商结果 `loadSession=False` 时，代码会先 `drop_backend_session()` 再 `session/new`，导致连续 `/oc` 实际新建 backend session。"
  artifacts: [{path: "core/executor.py", issue: "`_ensure_session_ready()` 在已有 `backend_session_id` 且 `loadSession` 不支持时直接丢弃绑定并新建 session。"}, {path: "tests/core/test_executor_acp.py", issue: "现有测试把 `loadSession=False` 时新建 session 固化成预期。"}]
  missing: ["把 live 会话续用和历史会话恢复拆开处理，不要让连续 `/oc` 依赖 `loadSession`。", "补充连续 `/oc` 必须复用同一 backend session 的回归测试。"]
  debug_session: ".planning/debug/oc-reuses-session-fails.md"
- truth: "当 sender 绑定到失效历史会话后，再次执行 `/oc` 应先清掉坏绑定并恢复到可继续对话的状态，而不是因为会话管理异常导致检查无法成立"
  status: failed
  reason: "User reported: 每次调用`/oc`都会新建一个会话, 所以当前检查点无意义"
  severity: major
  test: 2
  root_cause: "执行器把所有已有 `backend_session_id` 的情况都当成必须先做历史恢复 `session/load`，却没有状态区分当前连接中已经 live 的会话和仅保存的历史会话 ID；一旦 load 失败就会 `drop_backend_session()` 后新建 session，掩盖了失效绑定后的真实恢复语义。"
  artifacts: [{path: "core/executor.py", issue: "`_ensure_session_ready()` 对所有已有 session_id 都强制走 `session/load`，失败后直接创建新 session。"}, {path: "core/session.py", issue: "`OpenCodeSession` 缺少当前 ACP 连接内 live/ready 状态标记，无法区分续用与恢复。"}, {path: "tests/core/test_executor_acp.py", issue: "测试模型也把已有 session_id 必须先 load 写成了预期。"}]
  missing: ["为会话状态建模区分 live 会话续用与历史会话恢复。", "补上失效历史绑定 fail-closed 与连续 `/oc` 续会话的测试。"]
  debug_session: ".planning/debug/invalid-history-session-oc.md"
- truth: "尝试通过 `/oc-session` 绑定不存在或不可恢复的会话时，应先校验目标 session 是否存在，并在失败时给出错误提示、回退到未绑定状态，同时工作目录应与绑定结果保持一致"
  status: failed
  reason: "User reported: `/oc-session`的交互没有问题. 但是如果尝试绑定不存在的session, 它没有去检查session是否存在, 没有错误提示, 依然绑定了一个不存在的会话. 而且工作目录也没有改变会被绑定会话的目录"
  severity: major
  test: 6
  root_cause: "`/oc-session` 绑定流程先写入 `bind_backend_session()`，后验证 `load_session()` 是否真的恢复成功；而 `load_session/_apply_session_state` 只在抛异常时认定失败，不校验返回 payload 是否真的恢复了目标 session，也没有同步历史会话的 `cwd/workdir`。"
  artifacts: [{path: "main.py", issue: "`/oc-session` 处理流程先绑定再校验，成功文案还固定声明工作目录保持不变。"}, {path: "core/executor.py", issue: "`load_session()` 仅依赖异常判断失败，未验证返回的 sessionId/状态。"}, {path: "core/acp_adapter.py", issue: "session state 归一化未提取 `cwd/workdir`，无法同步绑定目标目录。"}]
  missing: ["改成先验证恢复结果、后提交绑定的 fail-closed 流程。", "显式校验返回 payload 中的 sessionId/恢复状态。", "在成功绑定历史会话后同步其 `cwd/workdir` 到 sender 状态。"]
  debug_session: "/home/LiHaoyuan/workspace/cool_stuff/astrbot_plugin_opencode/.planning/debug/oc-session-invalid-bind.md"
