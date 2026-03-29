---
phase: 02-会话内核与生命周期统一
plan: 01
subsystem: session
tags: [session, acp, lifecycle, tool, slash-command]

# Dependency graph
requires:
  - phase: 01-配置收敛与兼容迁移
    provides: ACP-only 配置基线与默认值迁移
provides:
  - slash-command 与 tool 共用的会话执行启动入口
  - 后端会话失效后的确定性清理与重建语义
  - 会话共享、恢复、权限流的回归测试覆盖
affects: [phase-02-plan-02, chat-ux, tool-mediation]

# Tech tracking
tech-stack:
  added: [python-venv, pytest]
  patterns: [shared execution launcher, explicit backend session drop helper]

key-files:
  created: []
  modified:
    - core/session.py
    - core/executor.py
    - main.py
    - tests/core/test_executor_acp.py
    - tests/core/test_session_state.py
    - tests/test_main_commands.py

key-decisions:
  - "把 backend_session_id 的失效清理显式收敛为 drop_backend_session，避免恢复失败后残留半绑定状态。"
  - "让 /oc 与 call_opencode_tool 先共用执行准备与启动入口，只保留输出归属差异。"

patterns-established:
  - "Pattern 1: 前台 chat 与后台 tool 先共享 prompt 准备和启动，再分别处理消息归属。"
  - "Pattern 2: 会话恢复失败时先清空 live runtime 状态，再决定报错还是重建。"

requirements-completed: [SESS-01, SESS-03]

# Metrics
duration: 1 min
completed: 2026-03-29
---

# Phase 2 Plan 1: 统一 slash-command 与 tool 的共享会话执行内核 Summary

**共享 chat/tool 的 ACP 会话启动内核，并在恢复失败时用显式清理语义重建 backend session。**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-29T10:02:52Z
- **Completed:** 2026-03-29T10:03:53Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- 为会话对象补上显式的 backend 解绑辅助方法，收紧 live 状态边界。
- 让 executor 在历史会话恢复失败或不可恢复时走一致的清理与重建路径。
- 把 `/oc` 与 `call_opencode_tool` 的输入准备和执行启动收敛到同一套私有入口，并补齐回归测试。

## task Commits

Each task was committed atomically:

1. **task 1: 收紧会话状态模型并补齐恢复语义测试** - `0f67036` (test)
2. **task 1: 收紧会话状态模型并补齐恢复语义测试** - `a9fbd00` (feat)
3. **task 2: 统一 chat 与 tool 的执行编排入口** - `2e060f1` (test)
4. **task 2: 统一 chat 与 tool 的执行编排入口** - `ebb5112` (feat)

**Plan metadata:** `pending` (docs)

_Note: 本计划按 TDD 执行，每个 task 含 test → feat 两个原子提交。_

## Files Created/Modified

- `core/session.py` - 提炼 runtime 状态清理与 backend 解绑辅助方法。
- `core/executor.py` - 统一历史 session 恢复失败时的清理/重建分支。
- `main.py` - 抽出共享的执行准备与启动入口，复用到 chat/tool。
- `tests/core/test_executor_acp.py` - 覆盖恢复失败后的会话重建与 runtime 清理。
- `tests/core/test_session_state.py` - 覆盖 backend 解绑与 live 状态边界。
- `tests/test_main_commands.py` - 覆盖 chat/tool 共用启动链路与同 sender 会话延续。

## Decisions Made

- 用 `drop_backend_session()` 明确表示“丢弃后端绑定但保留默认偏好/工作目录”，减少 `reset_live_session()` 的语义歧义。
- 只统一执行准备与启动，不改动 chat/tool 的输出归属：chat 继续 yield，tool 继续后台推送。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 本地环境缺少 pytest 与 pip 可用入口**

- **Found during:** task 1（RED）
- **Issue:** 运行计划要求的 pytest 时，系统 Python 缺少 pytest，且受 PEP 668 限制不能直接写入全局环境。
- **Fix:** 在仓库内创建 `.venv`，并在虚拟环境中安装 pytest 后执行验证。
- **Files modified:** 无仓库源码文件
- **Verification:** `".venv/bin/python" -m pytest tests/core/test_executor_acp.py tests/core/test_session_state.py` 与 `".venv/bin/python" -m pytest tests/test_main_commands.py -k "session or tool or oc_end or oc_new"` 均通过
- **Committed in:** 未纳入源码 task commit（本地验证环境）

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** 仅补齐本地验证环境，无额外功能扩张。

## Issues Encountered

- 系统环境未预装 pytest；已通过仓库内虚拟环境解决，不影响运行时代码。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 02-01 已把共享执行内核与恢复语义收紧，可继续执行 02-02 的 `/oc-new`、`/oc-end`、`/oc-session` 生命周期语义固化。
- 当前没有阻塞下一计划的已知问题。

---

_Phase: 02-会话内核与生命周期统一_
_Completed: 2026-03-29_

## Self-Check: PASSED
