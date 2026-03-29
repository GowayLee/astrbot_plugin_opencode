---
status: diagnosed
trigger: "Issue from Phase 02 UAT. Goal: find_root_cause_only. Expected behavior: 在同一发送者下连续执行 `/oc` 时，第二次请求应复用第一次建立的会话上下文，而不是新建 session。 Actual behavior: 用户报告“我实际测试了连续两个`/oc`指令, 发现ACP服务器实际上创建了两个session”。"
created: 2026-03-30T00:00:00Z
updated: 2026-03-30T00:16:00Z
---

## Current Focus

hypothesis: 根因已确认：executor 错把“继续当前 live session”当成 `loadSession` 能力的前提，导致不支持 `loadSession` 的后端在第二次 `/oc` 时强制新建 session。
test: 无需继续测试；整理诊断结论并返回。
expecting: 最终报告应能说明 sender 会话对象实际被复用，但 backend session 被 executor 主动丢弃重建。
next_action: 输出 root cause 报告

## Symptoms

expected: 在同一发送者下连续执行 `/oc` 时，第二次请求应复用第一次建立的会话上下文，而不是新建 session。
actual: 用户报告“我实际测试了连续两个`/oc`指令, 发现ACP服务器实际上创建了两个session”。
errors: 无直接报错；ACP 服务器连续创建两个 session。
reproduction: 参考 `.planning/phases/02-会话内核与生命周期统一/02-UAT.md` 中 Test 1，在同一发送者下连续执行两个 `/oc`。
started: UAT 阶段发现。

## Eliminated

## Evidence

- timestamp: 2026-03-30T00:05:00Z
  checked: `.planning/debug/knowledge-base.md`
  found: 知识库文件不存在。
  implication: 本次调查没有现成已知模式可直接优先验证，需要从代码路径自行建模。

- timestamp: 2026-03-30T00:05:00Z
  checked: `core/AGENTS.md`
  found: 会话连续性由 `core/session.py` 负责，local/remote 行为差异集中在 `core/executor.py`。
  implication: 需要重点检查 `/oc` 在 `main.py` 中如何调用 session manager 与 executor，以及 remote session 回写链路。

- timestamp: 2026-03-30T00:12:00Z
  checked: `main.py:_prepare_oc_execution()` 与 `core/session.py:get_or_create_session()`
  found: `/oc` 每次都按 `event.get_sender_id()` 取同一个 `OpenCodeSession`；`SessionManager` 会缓存并返回已有 sender 会话，不会在普通 `/oc` 路径主动 reset。
  implication: “第二次 `/oc` 新建 backend session” 不是因为聊天层为同一 sender 创建了新的插件会话对象。

- timestamp: 2026-03-30T00:12:00Z
  checked: `core/executor.py:_ensure_session_ready()`
  found: 当 `session.backend_session_id` 已存在且 `protocol_capabilities.loadSession` 为假时，代码直接执行 `session.drop_backend_session()`，随后无条件调用 `_create_session(session)` 新建后端 session。
  implication: 只要后端不声明 `loadSession`，第二次 `/oc` 就会丢弃第一次拿到的 session 绑定并创建新 session，完全符合 UAT 现象。

- timestamp: 2026-03-30T00:12:00Z
  checked: `tests/core/test_executor_acp.py:test_executor_skips_recovery_when_backend_does_not_support_it`
  found: 仓库测试明确断言：已有 `session.backend_session_id="ses_old"` 且 `agentCapabilities.loadSession=False` 时，执行器应调用 `session/new` 而不是继续使用旧 session。
  implication: 当前错误行为不仅存在于实现里，还被测试固化，因此 UAT 现象是代码当前设计结果，不是偶发回归。

- timestamp: 2026-03-30T00:15:00Z
  checked: `pytest tests/core/test_executor_acp.py::test_executor_skips_recovery_when_backend_does_not_support_it`
  found: 当前环境没有 `pytest` 可执行命令（`zsh:1: command not found: pytest`）。
  implication: 需要改用 `python -m pytest` 或仅依赖静态代码/测试内容作为证据；这不影响已观察到的实现逻辑。

- timestamp: 2026-03-30T00:16:00Z
  checked: `python -m pytest tests/core/test_executor_acp.py::test_executor_skips_recovery_when_backend_does_not_support_it`
  found: 当前环境也未安装 `pytest` 模块（`No module named pytest`）。
  implication: 无法在此环境直接执行仓库测试，但测试源码本身与实现代码已足以构成静态证据链。

## Resolution

root_cause: 执行器把“同一 sender 下继续使用当前 live backend session”错误地依赖于可选的 `loadSession` 能力；当后端宣告 `loadSession=false` 时，第二次 `/oc` 不会继续使用已有 `backend_session_id`，而是先 `drop_backend_session()` 再 `session/new`，导致 ACP 服务器新建第二个 session。
fix:
verification:
files_changed: []
