---
phase: 02-会话内核与生命周期统一
plan: 04
subsystem: session
tags: [session, lifecycle, acp, workdir, pytest]

# Dependency graph
requires:
  - phase: 02-会话内核与生命周期统一
    provides: live 会话续用与历史恢复的双态语义
provides:
  - /oc-session 先验证恢复结果、后提交 sender 绑定的 fail-closed 流程
  - 历史会话 cwd/workdir 归一化与 sender 工作目录同步
  - load_session 对缺失或错配 sessionId 的显式拒绝校验
affects: [phase-03, chat-ux, lifecycle-commands]

# Tech tracking
tech-stack:
  added: []
  patterns:
    [verified history bind, normalized session workdir, fail-closed ACP restore]

key-files:
  created: []
  modified:
    - core/acp_models.py
    - core/acp_adapter.py
    - core/executor.py
    - main.py
    - tests/core/test_acp_adapter.py
    - tests/core/test_executor_acp.py
    - tests/test_main_commands.py

key-decisions:
  - "把历史会话恢复的 sessionId 校验放在 executor.load_session 内部，避免上层各自判断 payload 是否可信。"
  - "`/oc-session` 先在临时 probe session 上验证恢复结果，再把成功恢复后的状态提交回 sender。"

patterns-established:
  - "Pattern 1: 历史会话绑定必须验证目标 sessionId 精确命中，否则直接 fail closed。"
  - "Pattern 2: 绑定历史会话成功时，同步采用 payload 返回的 cwd/workdir 作为 sender 当前工作目录。"

requirements-completed: [SESS-02, SESS-03]

# Metrics
duration: 8 min
completed: 2026-03-29
---

# Phase 2 Plan 4: 收紧 /oc-session 的历史绑定校验与目录同步 Summary

**`/oc-session` 现在只会在目标历史会话真实恢复成功后才提交绑定，并把 sender 工作目录同步到该会话返回的 cwd/workdir。**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-29T17:01:00Z
- **Completed:** 2026-03-29T17:09:18Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- 为 ACP session state 补上历史会话 workdir 归一化，打通 cwd/workdir 到 sender 状态同步链路。
- 收紧 `CommandExecutor.load_session()`，对缺失或错配的 `sessionId` 直接 fail-closed。
- 把 `/oc-session` 改成先 probe 恢复、后提交绑定，并补齐成功同步目录与失败回退未绑定的命令级回归测试。

## Task Commits

Each task was committed atomically:

1. **Task 1: 先把 `/oc-session` 的 fail-closed 绑定契约补进测试** - `c7af077` (test)
2. **Task 2: 实现先验证后绑定的历史会话恢复流程** - `aae7240` (feat)

**Plan metadata:** `pending` (docs)

## Files Created/Modified

- `core/acp_models.py` - 为标准化 session state 增加 `work_dir` 字段。
- `core/acp_adapter.py` - 从 ACP payload 的 `cwd/workdir` 提取历史会话目录。
- `core/executor.py` - 校验恢复结果必须命中目标 `sessionId`，并在成功时同步工作目录。
- `main.py` - `/oc-session` 改为 probe 成功后再提交 sender 绑定。
- `tests/core/test_acp_adapter.py` - 覆盖 `cwd/workdir` 归一化。
- `tests/core/test_executor_acp.py` - 覆盖 load_session 缺失/错配 `sessionId` 的 fail-closed 行为。
- `tests/test_main_commands.py` - 覆盖 `/oc-session` 成功同步目录与失败回退未绑定。

## Decisions Made

- 在 executor 层统一做历史恢复结果校验，这样 `/oc-session` 与其他潜在调用者都能共享同一套 fail-closed 规则。
- 使用临时 probe session 承接历史恢复验证，避免在 sender 真状态上先写入一个尚未证实可用的绑定。

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2 的历史会话绑定语义已补齐，后续 Phase 3 可以直接复用这套稳定的生命周期快照与恢复契约。
- 当前未发现会阻塞下一阶段聊天交互增强的会话恢复问题。

## Self-Check: PASSED

- FOUND: `.planning/phases/02-会话内核与生命周期统一/02-04-SUMMARY.md`
- FOUND: `c7af077`
- FOUND: `aae7240`
