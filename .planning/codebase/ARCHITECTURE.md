# Architecture

**Analysis Date:** 2026-03-29

## Pattern Overview

**Overall:** Plugin-with-managers — a single AstrBot plugin class (`OpenCodePlugin` in `main.py`) orchestrates six specialized manager classes in `core/`, each owning one operational concern. Communication between managers flows through injected callbacks and shared session objects rather than a message bus or event system.

**Key Characteristics:**

- **Manager-per-concern separation**: Each `core/` module owns a single runtime boundary (input, execution, session state, security, output, storage). Cross-concern logic lives in `main.py` which wires managers together.
- **ACP-only execution**: All backend communication goes through a JSON-RPC-over-stdio ACP protocol. There is no local CLI subprocess or HTTP remote mode anymore; the codebase previously supported local/remote splits but now exclusively uses ACP.
- **Session-per-sender model**: Each chat sender gets an independent `OpenCodeSession` object holding workdir, environment variables, backend session ID, agent/mode preferences, and live state. Sessions are in-memory only and keyed by `sender_id`.
- **Config-driven output pipeline**: Output formatting is a composable pipeline of configurable "blocks" (AI summary, full text, TXT file, long image, last-line truncation). The config schema `_conf_schema.json` is the authority for all defaults and toggles.
- **Streaming + fallback execution**: The executor supports both streaming (via notification queue + `asyncio.wait`) and one-shot `run_prompt` calls. Streaming is preferred; non-streaming is the fallback path.

## Layers

**Presentation / Command Layer:**

- Purpose: AstrBot command handlers, LLM tool entry, user-facing rendering helpers
- Location: `main.py`
- Contains: `@filter.command` handlers (`oc`, `oc-agent`, `oc-mode`, `oc-send`, `oc-new`, `oc-end`, `oc-clean`, `oc-history`, `oc-session`), `@filter.llm_tool` handler (`call_opencode`), rendering helpers (`_render_exec_status`, `_render_agent_overview`, `_render_mode_overview`), permission-wait helpers
- Depends on: All `core/` managers, AstrBot SDK (`astrbot.api.*`)
- Used by: AstrBot framework (invokes handlers on incoming messages)

**Manager / Orchestration Layer:**

- Purpose: Runtime managers each owning one operational boundary
- Location: `core/session.py`, `core/executor.py`, `core/security.py`, `core/input.py`, `core/output.py`, `core/storage.py`
- Contains: `SessionManager`, `CommandExecutor`, `SecurityChecker`, `InputProcessor`, `OutputProcessor`, `StorageManager` classes
- Depends on: AstrBot SDK, `core/` peer modules (via explicit imports), `aiohttp`, `asyncio`
- Used by: `main.py`

**Protocol / Transport Layer:**

- Purpose: ACP JSON-RPC protocol implementation, subprocess management, payload normalization
- Location: `core/acp_client.py`, `core/acp_transport_stdio.py`, `core/acp_adapter.py`, `core/acp_models.py`
- Contains: `ACPClient` (JSON-RPC request/response/notification dispatch), `ACPStdioTransport` (subprocess stdio pipe management), `OpenCodeACPAdapter` (payload normalization), dataclasses for protocol models and errors
- Depends on: `asyncio`, `json`, standard library only
- Used by: `core/executor.py`

**Utilities Layer:**

- Purpose: Synchronous file-write helpers designed for `asyncio.to_thread` offload
- Location: `core/utils.py`
- Contains: `write_file_sync()`, `write_text_file_sync()`
- Depends on: Standard library only
- Used by: `core/input.py`, `core/output.py`

## Data Flow

**Primary Task Flow (`/oc <task>`):**

1. AstrBot dispatches incoming message to `OpenCodePlugin.oc_handler()` in `main.py`
2. `SecurityChecker.is_admin()` gates access; `InputProcessor.process_input_message()` normalizes input (downloads media, handles quotes, builds `ACPPromptPayload`)
3. `SecurityChecker.is_destructive()` checks for dangerous keywords; if triggered, waits for user confirmation via `session_waiter`
4. `_run_oc_prompt()` is called:
   - Emits "🚀 执行中..." status
   - Attempts `CommandExecutor.stream_prompt()` which calls `_stream_execution()` — this starts an `asyncio.Task` for the ACP request and simultaneously listens to a notification `asyncio.Queue`
   - Stream yields `{"kind": "event", ...}` items (permission requests, tool updates, plan changes) that are formatted by `OutputProcessor.build_chat_updates()` and sent to user
   - If a permission request arrives, `_wait_for_permission_choice()` uses `session_waiter` to collect user's choice, then calls `executor.stream_permission_response()` or `executor.respond_permission()`
   - Stream yields `{"kind": "result", ...}` with the final `ExecutionResult`
   - Falls back to `CommandExecutor.run_prompt()` if stream is unavailable
5. `OutputProcessor.parse_output_plan()` receives the result and builds a send plan — an ordered list of message component lists based on config-driven output blocks
6. Each element of the send plan is emitted to chat via `event.chain_result()` or `event.plain_result()`, with a small random delay between sends

**LLM Tool Flow (`call_opencode` tool):**

1. AstrBot's LLM decides to call the `call_opencode` tool
2. `call_opencode_tool()` processes input, checks security
3. For destructive tasks, uses "确认执行" confirmation (stricter than `/oc` which uses "确认")
4. Emits status, then spawns `asyncio.create_task(_execute_opencode_background(...))` to avoid framework 60s timeout
5. Background task reuses `_run_oc_prompt()` but pushes results via `self.context.send_message(umo, ...)` instead of yielding

**Session Lifecycle:**

1. `SessionManager.get_or_create_session(sender_id)` creates `OpenCodeSession` with workdir and env on first use
2. `CommandExecutor.ensure_session()` initializes ACP client if needed, then creates or loads a backend session
3. `SessionManager.reset_session()` resets live state (clears backend_session_id, agent, mode) while preserving preferences
4. `OpenCodeSession.bind_backend_session()` binds to an existing backend session (via `/oc-session`)
5. `OpenCodeSession.reset_live_session()` clears all runtime state but keeps defaults

**State Management:**

- Per-sender state lives in `SessionManager.sessions: Dict[str, OpenCodeSession]` — in-memory only, lost on plugin restart
- `OpenCodeSession` tracks: `work_dir`, `env`, `backend_session_id`, `default_agent`, `default_mode`, `default_config_options`, live runtime fields (`agent_name`, `available_agents`, `current_mode_id`, `config_options`, `pending_permission`, `prompt_running`, etc.)
- Workdir history persisted to JSON file via `StorageManager` at `{base_data_dir}/workdir_history.json`

## Key Abstractions

**`ExecutionResult` (dataclass):**

- Purpose: Uniform result from all executor operations
- Examples: `core/executor.py` (line 20-31)
- Pattern: Dataclass with `ok`, `message`, `error_type`, `final_text`, `stop_reason`, `session_id`, `payload`, `items`, `recovered_session`, `session_recovery_failed`
- Every executor method returns this; callers check `result.ok` then inspect fields

**`OpenCodeSession` (class):**

- Purpose: Per-sender runtime state — the single source of truth for session continuity
- Examples: `core/session.py` (line 13-88)
- Pattern: Mutable object with `reset_live_session()` to clear runtime state while preserving defaults; `bind_backend_session()` for history restore
- Shared across all managers; executor writes backend state back into it via `_apply_session_state()`

**`ACPClient` (class):**

- Purpose: Generic JSON-RPC client for ACP protocol over stdio
- Examples: `core/acp_client.py` (line 11-217)
- Pattern: Manages request/response correlation via `asyncio.Future`, dispatches notifications to registered handlers, owns a `ACPStdioTransport`

**`ACPStdioTransport` (class):**

- Purpose: Async subprocess management with JSON-RPC message framing over stdin/stdout
- Examples: `core/acp_transport_stdio.py` (line 12-194)
- Pattern: One JSON object per newline (`\n`-delimited), thread-safe reads/writes via `asyncio.Lock`, stderr collection for error diagnostics

**`ACPPromptPayload` (str subclass):**

- Purpose: Carries both text and structured content blocks for ACP prompt calls
- Examples: `core/input.py` (line 20-39)
- Pattern: Subclasses `str` for backward compatibility; `to_payload()` method produces the dict expected by ACP

**`PreflightDecision` (dataclass):**

- Purpose: Security preflight check result with reason and runtime permission delegation flag
- Examples: `core/security.py` (line 17-20)
- Pattern: `requires_confirmation: bool`, `reason: str`, `relies_on_runtime_permission: bool`

**ACP Data Models (dataclasses):**

- Purpose: Strongly-typed representations of ACP protocol payloads
- Examples: `core/acp_models.py` — `ACPSessionState`, `ACPAgentInfo`, `ACPModeView`, `ACPConfigOption`, `ACPPermissionRequest`, `ACPNormalizedEvent`, etc.
- Pattern: All use `@dataclass(slots=True)` with a `raw: dict` field preserving the original payload for passthrough

## Entry Points

**`OpenCodePlugin.initialize()` (plugin lifecycle):**

- Location: `main.py` (line 606)
- Triggers: AstrBot framework calls after plugin registration
- Responsibilities: Configures LLM tool description/args, injects HTML render and LLM functions into `OutputProcessor`, starts auto-clean background task, runs ACP backend health check

**`OpenCodePlugin.terminate()` (plugin lifecycle):**

- Location: `main.py` (line 649)
- Triggers: AstrBot framework calls on plugin unload
- Responsibilities: Closes ACP client (`executor.close()`), stops auto-clean task

**`oc_handler` (`/oc` command):**

- Location: `main.py` (line 657)
- Triggers: User sends `/oc <task>` in chat
- Responsibilities: Admin check → input preprocessing → destructive-op confirmation → streaming execution → output plan delivery

**`call_opencode_tool` (LLM function tool):**

- Location: `main.py` (line 1099)
- Triggers: AstrBot's LLM decides to invoke the `call_opencode` tool
- Responsibilities: Same pipeline as `/oc` but runs in background task with push delivery instead of yielding

**`@register` decorator:**

- Location: `main.py` (line 31)
- Triggers: Plugin discovery by AstrBot framework
- Responsibilities: Registers plugin metadata (id, author, description, version, repo URL)

## Error Handling

**Strategy:** Layered error types with fallbacks, fail-closed on security.

**Patterns:**

- **ACP protocol errors**: `ACPError`, `ACPTransportError`, `ACPStartupError`, `ACPTimeoutError` hierarchy in `core/acp_models.py` — caught at executor boundary and converted to `ExecutionResult(ok=False, error_type=..., message=...)`
- **Session recovery**: When `load_session` fails, the executor attempts to create a fresh session automatically (controlled by `allow_recreate_after_load_failure` flag). Sets `session_recovery_failed=True` on the result.
- **Security fail-closed**: `SecurityChecker` defaults to requiring confirmation; `check_path_safety` defaults to permissive (off) but can be enabled
- **Output rendering failures**: AI summary, long image, and TXT file generation failures are caught individually — each block degrades gracefully (e.g., "AI 摘要生成失败" message instead of crash)
- **Confirmation timeouts**: `session_waiter` with configurable timeout; timeout results in cancellation/fallback
- **Subprocess management**: `ACPStdioTransport` collects stderr for diagnostics; process is terminated then killed on timeout during `aclose()`

## Cross-Cutting Concerns

**Logging:** Uses AstrBot's `logger` (from `astrbot.api`), injected into every manager via `self.logger = logger`. All managers log at info/warning/error levels with context.

**Validation:** Security validation centralized in `core/security.py`. Input validation happens in `core/input.py` (media type detection, file extension resolution). Config validation is implicit via `_conf_schema.json` defaults.

**Authentication:** Admin gating via `event.is_admin()` controlled by `only_admin` config toggle. No other auth layer — the plugin trusts AstrBot's identity system.

**Configuration:** All behavior is config-driven via `AstrBotConfig` (loaded from `_conf_schema.json`). Config is accessed as nested dicts (`self.config.get("basic_config", {}).get(...)`) with defaults specified both in the schema and as fallback values in code.

**Async Boundaries:** Blocking I/O (file writes) is offloaded via `asyncio.to_thread()` calling sync helpers in `core/utils.py`. ACP transport uses `asyncio.subprocess`. All command handlers are async generators (`async def ... yield`).
