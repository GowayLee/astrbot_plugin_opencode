---
status: diagnosed
trigger: "Issue from Phase 02 UAT: /oc-session 绑定不存在或不可恢复会话时仍然绑定且工作目录未同步"
created: 2026-03-30T00:00:00Z
updated: 2026-03-30T00:07:00Z
---

## Current Focus

hypothesis: `/oc-session` 在 handler 中先写入 backend_session_id，再把 `load_session` 的“未抛异常”当作成功；同时绑定流程完全没有从已加载会话同步工作目录。
test: verify oc_session success/failure branches, executor load-session validation, and workdir update path
expecting: find that invalid/stale session can remain bound when load response lacks explicit validation, and session.work_dir is never overwritten from loaded session metadata
next_action: return diagnosis with files involved and suggested fix direction

## Symptoms

expected: 尝试通过 `/oc-session` 绑定不存在或不可恢复的会话时，应先校验目标 session 是否存在，并在失败时给出错误提示、回退到未绑定状态，同时工作目录应与绑定结果保持一致。
actual: `/oc-session` 的交互没有问题，但尝试绑定不存在的 session 时，没有去检查 session 是否存在，没有错误提示，依然绑定了一个不存在的会话，而且工作目录也没有改变为被绑定会话的目录。
errors: 无明确报错；用户观察到错误绑定和目录未同步。
reproduction: 参考 `.planning/phases/02-会话内核与生命周期统一/02-UAT.md` 中 Test 6，执行 `/oc-session` 并尝试绑定不存在的历史会话。
started: Discovered during UAT.

## Eliminated

## Evidence

- timestamp: 2026-03-30T00:01:00Z
  checked: .planning/debug/knowledge-base.md
  found: 文件不存在，没有可复用的已知模式。
  implication: 需要从代码路径直接建立假设并取证。

- timestamp: 2026-03-30T00:03:00Z
  checked: main.py:1229-1295
  found: `/oc-session` 先通过列表匹配目标，再在 1275 行直接 `session.bind_backend_session(target_session["id"])`，随后才调用 `executor.load_session(session)`；成功分支固定输出 `📂 当前工作目录保持: {session.work_dir}`。
  implication: 绑定 ID 发生在恢复验证之前；而且当前实现明确选择“不切换工作目录”，与 UAT 期望相反。

- timestamp: 2026-03-30T00:04:00Z
  checked: core/executor.py:176-192,452-506,531-581
  found: `load_session()` 依赖 `_ensure_session_ready(...allow_recreate_after_load_failure=False)`；该函数只在 `client.load_session()` 抛出异常时才判定失败并 `drop_backend_session()`，若请求返回的是空/不完整 payload，`_apply_session_state()` 不会校验返回的 `sessionId` 是否存在或与目标一致，最终仍返回 `ok=True`。
  implication: 代码把“RPC 未抛异常”当成“历史会话恢复成功”，缺少对目标 session 实际存在/已恢复的显式校验，因此可能残留一个逻辑上无效但字段上已绑定的 session id。

- timestamp: 2026-03-30T00:05:00Z
  checked: core/session.py:67-79; core/acp_adapter.py:75-114
  found: `bind_backend_session()` 只重置 live 状态并写入 `backend_session_id`，不处理 `work_dir`；adapter 归一化 session state 时也只解析 session_id/agent/mode/config/capabilities，不解析 cwd/workdir，`_apply_session_state()` 因此没有任何更新 `session.work_dir` 的路径。
  implication: 即使历史会话恢复成功，当前 sender 的工作目录也不会与被绑定会话同步，只会保留原目录。

- timestamp: 2026-03-30T00:05:30Z
  checked: tests/test_main_commands.py:479-527; tests/core/test_executor_acp.py:291-344
  found: 现有测试只覆盖“load_session 抛错时 fail-closed”和“成功后水合 agent/mode”；没有覆盖“load_session 返回不完整 payload 但未报错”或“绑定后工作目录应切到历史会话目录”。
  implication: 当前缺口与 UAT 现象一致：代码路径中的两个关键行为（恢复成功判定、workdir 同步）都没有测试兜底。

## Resolution

root_cause:
root_cause: `/oc-session` 的绑定语义实现错位：handler 在验证恢复结果前就把 `backend_session_id` 写进 sender 状态，而 executor 的 `load_session` 又只把“RPC 没抛异常”视为成功，不校验返回 payload 是否真的恢复了目标 session；同时整个加载链路从未解析或回写历史会话的 cwd/workdir，成功文案还显式声明“当前工作目录保持”。因此当目标 session 已失效但后端未以异常形式返回时，插件会留下一个表面已绑定的无效 session id，且工作目录仍停留在旧值。
fix:
verification:
files_changed: []
