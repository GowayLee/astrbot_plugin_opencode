# Codebase Concerns

**Analysis Date:** 2026-03-29

## Tech Debt

**main.py is a 1194-line god class:**

- Issue: `OpenCodePlugin` in `main.py` handles command routing, rendering helpers, argument parsing, file scanning, session binding logic, permission flow orchestration, and background task dispatch all in one class. This makes it difficult to reason about any single responsibility and increases merge-conflict risk.
- Files: `main.py` (entire file)
- Impact: Any feature that touches commands, output rendering, or permission flow must edit the same large file. Hard to test individual behaviors without loading the whole plugin.
- Fix approach: Extract rendering helpers (`_render_exec_status`, `_render_live_state_lines`, `_render_agent_overview`, `_render_mode_overview`) into a dedicated renderer module. Extract `/oc-send` file scanning, indexing, and pagination into a dedicated send-handler module. Keep `main.py` as thin command wiring only.

**Duplicate module-loading boilerplate across all test files:**

- Issue: Every test file (`tests/test_main_commands.py`, `tests/core/test_session_state.py`, `tests/core/test_output_events.py`, `tests/core/test_executor_acp.py`, `tests/core/test_acp_client.py`, `tests/core/test_acp_adapter.py`) independently builds its own `astrbot` mock module tree with `types.ModuleType` and `sys.modules` injection. This is ~60–100 lines of identical boilerplate per file.
- Files: `tests/test_main_commands.py`, `tests/core/test_session_state.py`, `tests/core/test_output_events.py`, `tests/core/test_executor_acp.py`, `tests/core/test_acp_client.py`, `tests/core/test_acp_adapter.py`
- Impact: Adding a new AstrBot API import requires updating all 6 test files. High maintenance cost, easy to introduce subtle mock mismatches.
- Fix approach: Create a single `tests/conftest.py` or `tests/helpers.py` that provides a shared `load_module()` fixture or helper. Individual tests call into the shared loader instead of rebuilding it.

**Dead legacy alias surface on OpenCodeSession:**

- Issue: `OpenCodeSession` in `core/session.py` carries `opencode_session_id` property/setter (lines 37–42) and `set_opencode_session_id`/`clear_opencode_session_id` methods (lines 81–87) that are pure wrappers around `backend_session_id`. These were migration helpers that are no longer called by production code.
- Files: `core/session.py` lines 37–42, 81–87
- Impact: Confusing API surface for future contributors. Two ways to do the same thing.
- Fix approach: Audit for any external callers; if none exist, remove `opencode_session_id` property and the `set_opencode_session_id`/`clear_opencode_session_id` methods.

**Unused `httpx` dependency:**

- Issue: `requirements.txt` lists `httpx` but the codebase no longer uses it anywhere. The executor was refactored from HTTP remote calls to ACP stdio transport. Old test files still mock `httpx` modules (`tests/core/test_session_state.py` lines 68–77) but the production code has zero `httpx` imports.
- Files: `requirements.txt` (line 2), `tests/core/test_session_state.py` (lines 68–77)
- Impact: Unnecessary dependency install; dead mock code in tests.
- Fix approach: Remove `httpx` from `requirements.txt`. Remove `httpx` mock setup from `tests/core/test_session_state.py`.

## Known Bugs

**`/oc-send` file list cache never expires:**

- Issue: `self._send_file_list_cache` in `main.py` (line 56) is a plain dict that caches file listings per sender. It is never expired or invalidated. If the workspace changes (files added/removed), the cache becomes stale. The cache persists for the entire plugin lifetime (process uptime).
- Files: `main.py` lines 56, 822–823, 829–833
- Impact: Users see outdated file lists after workspace changes. Index-based sends (`/oc-send 1,2`) may target wrong files.
- Trigger: Add/remove files in workspace, then use `/oc-send` with index numbers.
- Workaround: Use explicit file paths instead of index numbers.

**`_expand_index_tokens` uses O(n²) dedup:**

- Issue: `main.py` line 547–551 deduplicates index list with `if idx not in deduped_indexes`, which is O(n) membership check on a list, yielding O(n²) overall.
- Files: `main.py` lines 547–551
- Impact: Negligible at current page_size=50, but if scan limits grow this could become noticeable.
- Fix approach: Use a set for membership tracking while preserving order.

**`/oc-send` path resolution does not normalize symlinks:**

- Issue: `is_path_safe()` in `core/security.py` compares absolute paths, but `os.path.abspath()` does not resolve symlinks. A symlink inside the workspace pointing outside would pass the safety check.
- Files: `core/security.py` lines 110–128
- Impact: If `check_path_safety` is enabled (currently defaults to `false`), symlinks could bypass path restrictions.
- Fix approach: Use `os.path.realpath()` instead of `os.path.abspath()` in `is_path_safe()`.

## Security Considerations

**`check_path_safety` defaults to disabled:**

- Risk: Path safety is opt-in with default `false` (`_conf_schema.json` line 106). Users who install the plugin may not realize `/oc-send` can read any file the AstrBot process has access to.
- Files: `_conf_schema.json` lines 105–109, `core/security.py` lines 103–108
- Current mitigation: Admin-only gating is enabled by default (`only_admin: true`).
- Recommendations: Consider changing default to `true` or adding a startup warning when disabled. Document the risk in README.

**Destructive keyword detection is regex-based and language-dependent:**

- Risk: The preflight check in `core/security.py` uses `re.search()` against user input. The keyword list includes both Chinese and English terms. False negatives are possible if a user crafts input that doesn't match but is still destructive (e.g., "移除" isn't in the default list). False positives are common—any message containing "更新" (update) triggers confirmation when `confirm_all_write_ops` is enabled.
- Files: `core/security.py` lines 47–84, `_conf_schema.json` lines 79–98
- Current mitigation: Configurable keyword list; ACP backend has its own runtime permission system.
- Recommendations: Document that this is a best-effort preflight, not a security boundary. The ACP runtime permission system is the real control.

**`_conf_schema.json` destructive_keywords are treated as regex but look like literal strings:**

- Risk: Keywords like `rm\b` and `dd\b` use word-boundary anchors, but others like "删除" and "格式化" are plain text. If a user adds a keyword containing regex metacharacters without intending regex behavior, `re.search()` could raise or match unexpectedly.
- Files: `core/security.py` line 58, `_conf_schema.json` lines 82–97
- Current mitigation: The config is admin-controlled.
- Recommendations: Either escape all keywords before regex matching (treat as literal) or clearly document that values are full regex patterns.

**Fire-and-forget background task without error boundary in call_opencode_tool:**

- Risk: `main.py` line 1160 uses `asyncio.create_task()` to run `_execute_opencode_background` without storing the task handle. If the task raises an unhandled exception before the try/except inside `_execute_opencode_background`, the error is silently swallowed by the asyncio event loop.
- Files: `main.py` lines 1160–1162, 1166–1194
- Current mitigation: `_execute_opencode_background` wraps its body in try/except and attempts to send error messages.
- Recommendations: Store the task handle and add a done-callback for unhandled exceptions.

**ACP subprocess inherits full environment:**

- Risk: `core/session.py` line 179 copies `os.environ` entirely into the ACP subprocess environment. This means all environment variables from the AstrBot host process (including potential secrets, API keys, etc.) are available to the ACP backend.
- Files: `core/session.py` lines 178–188
- Current mitigation: This is by design—the ACP backend needs environment access to function. Proxy settings are injected this way.
- Recommendations: Document that the ACP subprocess has full host env access. Consider an allowlist or denylist for sensitive env vars if needed in multi-tenant scenarios.

## Performance Bottlenecks

**Synchronous filesystem operations on async event loop:**

- Problem: `main.py` `_scan_workspace_files()` (lines 413–452) walks the entire workspace directory tree synchronously with `os.walk()`. For large workspaces (approaching the 10,000 file scan limit), this blocks the async event loop.
- Files: `main.py` lines 413–452
- Cause: `os.walk()` is a synchronous blocking call executed directly in an async command handler.
- Improvement path: Wrap in `asyncio.to_thread()` or use `aiofiles.os` / async directory walking.

**`record_workdir` reads and writes JSON on every call:**

- Problem: `core/storage.py` `record_workdir()` (lines 54–95) reads the entire history JSON file, modifies it, and writes it back on every invocation. This happens synchronously in the event loop during session creation.
- Files: `core/storage.py` lines 54–95
- Cause: No in-memory write-back cache; every call is a full file round-trip.
- Improvement path: Maintain an in-memory history dict, flush to disk on a timer or on plugin shutdown.

**Storage auto-clean blocks on directory listing:**

- Problem: `core/storage.py` `clean_temp_files()` (lines 142–191) iterates workspace directories synchronously. Called periodically by the auto-clean loop, this blocks the event loop each cycle.
- Files: `core/storage.py` lines 142–191
- Cause: `os.listdir()` and `os.remove()` are synchronous.
- Improvement path: Wrap cleanup in `asyncio.to_thread()`.

## Fragile Areas

**`_build_chat_update` event-type dispatch in output.py:**

- Files: `core/output.py` lines 200–263
- Why fragile: A long if/elif chain maps event type strings to output messages. Adding a new event type requires editing this chain. Missing an event type silently drops it (returns `""`).
- Safe modification: Add new event types at the end of the chain. Always return a non-empty string for new types to ensure visibility. Consider converting to a dict dispatch.
- Test coverage: Covered in `tests/core/test_output_events.py` for permission and run events. Other event types (plan_updated, tool_started, config_updated, mode_updated) have no explicit tests.

**Permission flow orchestration in main.py:**

- Files: `main.py` lines 249–269, 271–367, 1120–1151
- Why fragile: The permission flow involves `_run_oc_prompt` iterating a stream, detecting `pending_permission`, calling `_wait_for_permission_choice`, then calling `stream_permission_response` or `respond_permission`. Two code paths exist: streaming (lines 289–325) and polling (lines 339–354). They must stay in sync.
- Safe modification: Any change to permission handling must update both paths. Add tests for both streaming and polling permission flows.
- Test coverage: Both paths are tested in `tests/test_main_commands.py` (`test_call_opencode_tool_uses_permission_flow_in_background` and `test_oc_handler_consumes_live_permission_updates_before_prompt_returns`).

**`_normalize_runtime_event` in executor.py:**

- Files: `core/executor.py` lines 694–773
- Why fragile: This method normalizes heterogeneous ACP notification payloads into a consistent internal shape. It uses multiple fallback paths for field names (e.g., `requestId` / `request_id` / `id`). Different ACP backends may structure notifications differently.
- Safe modification: When adding support for a new ACP backend, thoroughly test notification normalization with that backend's actual payloads.
- Test coverage: Covered in `tests/core/test_executor_acp.py` (`test_normalize_runtime_event_maps_direct_permission_method_to_internal_shape`).

**`_apply_session_state` in executor.py:**

- Files: `core/executor.py` lines 528–561
- Why fragile: This method conditionally updates session fields based on which keys are present in the payload. Missing a key check means a field won't be updated from backend responses. Extra keys in the payload are silently ignored.
- Safe modification: When adding new session state fields, add the corresponding key check here.
- Test coverage: Indirectly covered through executor integration tests. No direct unit test for `_apply_session_state` in isolation.

## Scaling Limits

**In-memory session store with no eviction:**

- Current capacity: `SessionManager.sessions` dict grows without bound (`core/session.py` line 96). Every unique sender_id creates a permanent in-memory session.
- Limit: In a large chat group with many users, memory grows linearly with unique users. No LRU eviction or max-session cap.
- Scaling path: Add an LRU eviction policy or max-session limit. Consider persisting sessions to disk and loading on demand.

**Single global ACP client:**

- Current capacity: `CommandExecutor._client` is a single shared ACP client instance (`core/executor.py` line 48). All sessions share the same JSON-RPC subprocess connection.
- Limit: Concurrent prompt requests are serialized through the single transport. The `_stream_execution` method (line 647) uses per-session queues but the underlying transport can only handle one request/response at a time.
- Scaling path: If concurrent users need independent backends, consider a client pool or per-session transport. Current design is adequate for single-user or low-concurrency deployments.

**File scan limit at 10,000:**

- Current capacity: `_get_send_scan_limit()` returns 10000 (`main.py` line 383).
- Limit: Workspaces with more than 10,000 files will have truncated `/oc-send` listings.
- Scaling path: Make configurable or use a more efficient indexing approach (e.g., `.gitignore`-aware scanning, cached index).

## Dependencies at Risk

**aiohttp (unpinned version):**

- Risk: `requirements.txt` lists `aiohttp` without a version constraint. A major version bump could break the download logic in `core/input.py`.
- Impact: Resource downloads (images, files) would fail.
- Migration plan: Pin to a minimum version (e.g., `aiohttp>=3.8,<4`).

**httpx (unused):**

- Risk: Listed in `requirements.txt` but not imported anywhere in production code. Wastes install time and adds an unnecessary dependency surface.
- Impact: No functional impact, but increases supply-chain attack surface.
- Migration plan: Remove from `requirements.txt`.

## Missing Critical Features

**No session persistence across plugin restarts:**

- Problem: All session state (workdir, agent preferences, backend session IDs) is lost when the plugin restarts. Users must reconfigure agent, mode, and workdir after every restart.
- Files: `core/session.py` — `SessionManager.sessions` is a plain dict.
- Blocks: Seamless restart experience; long-running multi-session workflows.

**No per-session ACP process isolation:**

- Problem: All users share a single ACP subprocess. One user's session creation or prompt execution blocks others.
- Files: `core/executor.py` — single `_client` instance.
- Blocks: Multi-user concurrent operation at scale.

## Test Coverage Gaps

**`core/security.py` has zero test coverage:**

- What's not tested: `is_destructive()`, `evaluate_preflight()`, `is_path_safe()`, `check_admin()`. These are security-critical functions.
- Files: `core/security.py`
- Risk: Changes to keyword matching, path safety logic, or admin checks could introduce regressions without detection.
- Priority: High — security-sensitive code.

**`core/storage.py` has zero test coverage:**

- What's not tested: `record_workdir()`, `load_workdir_history()`, `clean_temp_files()`, auto-clean loop behavior.
- Files: `core/storage.py`
- Risk: History corruption, cleanup failures, or file I/O regressions go undetected.
- Priority: Medium.

**`core/input.py` download logic is untested:**

- What's not tested: `_download_resource()` actual HTTP download, file extension detection, conflict resolution. Tests mock `_download_resource` instead of exercising it.
- Files: `core/input.py` lines 162–238
- Risk: Network error handling, extension detection regressions, filename collision bugs.
- Priority: Medium.

**`main.py` command handlers beyond oc/oc-agent/oc-mode/oc-session/oc-end/oc-new:**

- What's not tested: `/oc-send` file scanning, indexing, pagination, and actual file sending. `/oc-clean` and `/oc-history` handlers.
- Files: `main.py` lines 413–605 (oc-send logic), 993–1033 (oc-clean, oc-history)
- Risk: File listing and sending regressions go undetected.
- Priority: Medium.

**`core/output.py` long-image rendering and TXT export:**

- What's not tested: `render_long_image()`, the actual TXT file writing path, the `ansi_to_html()` conversion, and the full `parse_output_plan()` dispatch logic for different output mode combinations.
- Files: `core/output.py` lines 45–117 (ansi_to_html), 443–464 (render_long_image), 466–644 (parse_output_plan)
- Risk: Output rendering regressions after template or ANSI handling changes.
- Priority: Low-Medium.

---

_Concerns audit: 2026-03-29_
