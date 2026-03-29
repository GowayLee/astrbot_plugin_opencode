---
phase: 02-会话内核与生命周期统一
plan: 03
subsystem: session
tags: [session, acp, executor, lifecycle, recovery]

# Dependency graph
requires:
  - phase: 02-会话内核与生命周期统一
    provides: 共享执行内核与基础生命周期语义
provides:
  - 区分 live 会话续用与历史 session 恢复的 sender 状态模型
  - 普通 /oc 路径对坏历史绑定的清理后重建语义
  - 显式 load_session 失败时的 fail-closed 回归覆盖
affects: [phase-02-plan-04, chat-ux, session-recovery]

# Tech tracking
tech-stack:
  added: []
  patterns: [live-vs-history session state, fail-closed explicit session load]

key-files:
  created: []
  modified:
    - core/session.py
    - core/executor.py
    - tests/core/test_executor_acp.py
    - tests/core/test_session_state.py

key-decisions:
  - "bind_backend_session 只表示历史绑定，真正进入当前连接 live 状态要靠显式标记。"
  - "_ensure_session_ready 优先直通 live 会话，只有历史绑定才尝试 session/load。"

patterns-established:
  - "Pattern 1: sender 状态在 session.py 内同时表达 has_bound 与 has_live，避免把恢复和续用混成一个布尔判断。"
  - "Pattern 2: 显式恢复失败保持 fail-closed，普通执行失败才 drop 坏绑定后重建。"

requirements-completed: [SESS-01]

# Metrics
duration: 1 min
completed: 2026-03-29
---

# Phase 2 Plan 3: 修正 live 会话续用与坏历史绑定恢复语义 Summary

**ACP sender 会话现在能区分当前连接中的 live 续用与仅保存 ID 的历史恢复，并在坏历史绑定上按入口分别重建或 fail-closed。**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-29T17:00:17Z
- **Completed:** 2026-03-29T17:01:53Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- 先用回归测试钉死 live 会话续用、历史恢复失败重建、显式 load 失败 fail-closed 三条路径。
- 为 `OpenCodeSession` 补上 live/history 双态表达，避免单看 `backend_session_id` 混淆语义。
- 重写 executor ensure 分支，让连续 `/oc` 不再因 `loadSession=False` 误建新 session。

## Task Commits

Each task was committed atomically:

1. **Task 1: 先把 live 会话续用 / 历史恢复分流写成回归测试** - `049ac17` (test)
2. **Task 2: 在 session/executor 中落地 live 与 history 的双态语义** - `2d11e68` (feat)

**Plan metadata:** `pending` (docs)

## Files Created/Modified

- `tests/core/test_executor_acp.py` - 覆盖 live 续用直通、坏历史绑定恢复失败后重建、显式 load fail-closed。
- `tests/core/test_session_state.py` - 覆盖 sender 的 has_bound / has_live 状态边界与状态提升。
- `core/session.py` - 为 backend session 增加 live 标记与显式状态辅助属性/方法。
- `core/executor.py` - 将 ensure 流程拆分为 live 直通、history load、失败后重建或报错。

## Decisions Made

- `bind_backend_session()` 仅保留“绑定历史 session ID”语义，不再顺便暗示当前 ACP 连接已 live。
- `session/load` 只用于历史恢复；若 sender 已持有 live backend session，直接复用并跳过 `session/load` / `session/new`。

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 02-03 已收紧 live/history 的状态边界，可继续执行 02-04 的历史绑定校验与目录同步。
- 当前没有阻塞下一计划的已知问题。

---

_Phase: 02-会话内核与生命周期统一_
_Completed: 2026-03-29_

## Self-Check: PASSED
