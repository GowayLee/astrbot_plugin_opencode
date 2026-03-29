# External Integrations

**Analysis Date:** 2026-03-29

## APIs & External Services

**AstrBot Plugin SDK (host framework):**

- Provides the entire plugin lifecycle: registration, command routing, event handling, message construction, LLM tool management
- Plugin registers via `@register()` decorator in `main.py:31-37`
- Commands via `@filter.command()` and LLM tools via `@filter.llm_tool()` — all routed by AstrBot
- SDK modules consumed: `astrbot.api.event`, `astrbot.api.star`, `astrbot.api.all`, `astrbot.api.message_components`, `astrbot.core.utils.astrbot_path`, `astrbot.core.utils.session_waiter`
- Auth: inherited from AstrBot's admin system (`event.is_admin()`)
- SDK injected at runtime; not installable via pip separately

**OpenCode ACP Backend (subprocess):**

- Protocol: JSON-RPC 2.0 over stdio
- Launch: spawns `opencode acp` as a subprocess via `asyncio.create_subprocess_exec` in `core/acp_transport_stdio.py:46-57`
- Transport layer: `core/acp_transport_stdio.py` — owns subprocess lifecycle, stdin/stdout JSON line framing, stderr capture
- Client layer: `core/acp_client.py` — request/response tracking with futures, notification dispatch, protocol initialization
- Adapter layer: `core/acp_adapter.py` — normalizes OpenCode-specific ACP payloads into plugin-internal models
- Models: `core/acp_models.py` — dataclasses for ACP protocol entities (errors, sessions, permissions, config options, commands)
- Executor: `core/executor.py` — orchestrates ACP client lifecycle, session management, prompt execution, streaming, and permission flows
- SDK/Client: custom implementation (no third-party ACP library)
- Auth: none at protocol level; trust established via local subprocess ownership
- Methods invoked:
  - `initialize` — protocol handshake with capability negotiation
  - `session/new` — create new backend session with agent, mode, config, and cwd
  - `session/load` — resume existing session by ID (capability-gated: `loadSession`)
  - `session/prompt` — send prompt to active session
  - `session/cancel` — cancel running prompt
  - `session/list` — enumerate backend sessions
  - `session/set_config_option` — update live config option (e.g., mode)
  - `session/set_mode` — switch active mode
  - `session/respond_permission` — approve/reject permission request
- Server-push notifications: permission requests, runtime state updates (tool started, plan updated, run finished, etc.)
- Health check: `core/executor.py:102-126` — probes subprocess startup during plugin init

**LLM Provider (via AstrBot):**

- Used for AI summary generation in output pipeline
- Injected via `context.llm_generate` and `context.get_current_chat_provider_id` in `main.py:629-631`
- Consumed in `core/output.py:511-521` — sends prompt text to configured LLM for summarization
- Provider selection: configured via `output_config.summary_provider` in `_conf_schema.json`
- Auth: managed by AstrBot's provider configuration

**HTML Rendering (via AstrBot):**

- Used for long-image generation from output text
- Injected via `self.html_render` callback in `main.py:628`
- Template: `assets/long_text.html` — simple dark-theme monospace HTML with `{{ content }}` placeholder
- Consumed in `core/output.py:443-464` — renders ANSI-colored text to image URL
- ANSI-to-HTML conversion: `core/output.py:45-117` (`ansi_to_html()` function)

## Data Storage

**Databases:**

- None — no database dependencies

**File Storage:**

- Local filesystem only
- Plugin data directory: `<astrbot_data>/plugin_data/astrbot_plugin_opencode/`
  - `workdir_history.json` — persisted workdir usage history (up to 100 records) in `core/storage.py:20`
  - `opencode_output_*.txt` — temporary output text files in `core/output.py:541`
  - `workspace/` — default working directory for OpenCode sessions
  - `workspace/downloaded/` — downloaded media resources in `core/input.py:61`

**Caching:**

- None — in-memory session state only (`core/session.py:96`)

## Authentication & Identity

**Auth Provider:**

- AstrBot's built-in admin system
  - Implementation: `event.is_admin()` check in `core/security.py:39-41`
  - Gating: `basic_config.only_admin` in `_conf_schema.json` (default: `true`)
  - Applied to all commands and LLM tool invocation in `main.py`

**ACP Backend Auth:**

- None — local subprocess trust model; no authentication at protocol level

## Monitoring & Observability

**Error Tracking:**

- None (no Sentry, etc.)

**Logs:**

- AstrBot logger via `astrbot.api.logger` — used throughout all modules
- ACP subprocess stderr captured and stored in `core/acp_transport_stdio.py:100-101`
- Stderr surfaced in error messages on startup failure via `core/executor.py:812-828`

## CI/CD & Deployment

**Hosting:**

- AstrBot plugin ecosystem — deployed as a plugin package
- Plugin metadata: `metadata.yaml` (plugin_id: `astrbot_plugin_acp_client`, version: `1.3.0`)
- Repository: `https://github.com/gowaylee/astrbot_plugin_opencode`

**CI Pipeline:**

- None detected — no `.github/workflows/`, no Makefile, no CI config

## Environment Configuration

**Required env vars:**

- None explicitly required by the plugin itself
- AstrBot host environment provides plugin SDK and data paths

**Plugin config (via `_conf_schema.json`):**

- `basic_config.acp_command` — path to OpenCode CLI binary (default: `"opencode"`)
- `basic_config.proxy_url` — HTTP proxy URL (optional)
- `output_config.summary_provider` — LLM provider for AI summaries (optional, uses AstrBot default if empty)

**Secrets location:**

- No plugin-managed secrets
- `.opencode/opencode.jsonc` exists in repo but is gitignored; may contain contributor-local tokens (treat as potentially compromised per AGENTS.md guidance)

## Webhooks & Callbacks

**Incoming:**

- None — plugin is purely reactive to AstrBot events

**Outgoing:**

- None — no outbound webhooks; all external communication is via subprocess (ACP) or AstrBot SDK

## Inter-Module Communication

**Manager Callback Wiring (in `main.py:59-61`):**

- `session_mgr.set_record_workdir_callback(storage_mgr.record_workdir)` — session creation triggers history persistence
- `storage_mgr.set_get_workdirs_callback(session_mgr.get_all_workdirs)` — cleanup uses active session workdirs
- `security.set_load_history_callback(storage_mgr.load_workdir_history)` — path safety checks use history

**Notification Flow (in `core/executor.py`):**

- ACP client notifications → `_handle_client_notification` → per-session asyncio queues → streamed to `_run_oc_prompt` in `main.py` → output processor → chat messages

**Output Pipeline (in `core/output.py`):**

- Configurable output modes: `last_line`, `ai_summary`, `full_text`, `txt_file`, `long_image`
- Smart trigger: each mode has a `smart_trigger_*` flag; only activates when output exceeds `max_text_length`
- Merge forward: optional `merge_forward_enabled` combines multiple output blocks into a single merged-forward message

---

_Integration audit: 2026-03-29_
