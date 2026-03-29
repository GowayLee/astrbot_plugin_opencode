# Codebase Structure

**Analysis Date:** 2026-03-29

## Directory Layout

```
astrbot_plugin_opencode/
├── main.py                 # Plugin entrypoint, command handlers, LLM tool, orchestration hub
├── core/                   # Runtime manager layer (one module per concern)
│   ├── AGENTS.md           # Sub-agent instructions for core/ subtree
│   ├── acp_adapter.py      # ACP payload normalization (OpenCode-specific mapping)
│   ├── acp_client.py       # Generic ACP JSON-RPC client (request/response/notifications)
│   ├── acp_models.py       # Shared ACP data models and error types
│   ├── acp_transport_stdio.py  # Async stdio subprocess transport for JSON-RPC
│   ├── executor.py         # Command executor — ACP backend lifecycle, session dispatch
│   ├── input.py            # Input processor — media download, quote handling, prompt assembly
│   ├── output.py           # Output processor — formatting, AI summary, TXT, long-image, send plan
│   ├── security.py         # Security checker — admin gating, destructive-op detection, path safety
│   ├── session.py          # Session manager + OpenCodeSession state object
│   ├── storage.py          # Storage manager — workdir history, temp file cleanup
│   └── utils.py            # Sync file-write helpers (for asyncio.to_thread offload)
├── assets/
│   └── long_text.html      # HTML template for long-image rendering
├── tests/
│   ├── test_main_commands.py   # Tests for main.py command logic
│   └── core/
│       ├── test_acp_adapter.py # Tests for ACP adapter normalization
│       ├── test_acp_client.py  # Tests for ACP client JSON-RPC dispatch
│       ├── test_executor_acp.py # Tests for executor ACP integration
│       ├── test_output_events.py # Tests for output event handling
│       └── test_session_state.py # Tests for session state management
├── docs/
│   └── references/         # External documentation (ACP spec, OpenCode docs, AstrBot docs)
├── .opencode/              # OpenCode contributor tooling (NOT runtime source)
├── _conf_schema.json       # Plugin config schema — all settings, defaults, descriptions
├── metadata.yaml           # Plugin metadata (id, name, version, author)
├── requirements.txt        # Runtime Python dependencies
├── AGENTS.md               # Root sub-agent instructions
├── README.md               # User-facing documentation
├── CHANGELOG.md            # Release notes
├── LICENSE                 # License file
├── logo.png                # Plugin logo
├── screenshots/            # Documentation screenshots
├── cwconfig.json           # ContextWeaver configuration
└── .planning/              # Planning and codebase analysis docs
```

## Directory Purposes

**`core/`:**

- Purpose: Runtime manager layer — each module owns one operational concern
- Contains: 11 Python modules organized by responsibility
- Key files:
  - `core/executor.py` (828 lines) — largest module; ACP backend lifecycle, session management, streaming, notification dispatch
  - `core/output.py` (656 lines) — output pipeline with ANSI→HTML, AI summary, TXT export, long-image, merge-forward
  - `core/session.py` (203 lines) — `OpenCodeSession` state object and `SessionManager` CRUD
  - `core/acp_client.py` (217 lines) — JSON-RPC client with future-based request tracking
  - `core/acp_transport_stdio.py` (194 lines) — subprocess stdio transport
  - `core/acp_adapter.py` (234 lines) — OpenCode-specific payload normalization
  - `core/input.py` (238 lines) — media download, quote processing, prompt construction
  - `core/security.py` (132 lines) — admin check, destructive keyword detection, path safety
  - `core/storage.py` (191 lines) — workdir history persistence, auto-clean loop
  - `core/acp_models.py` (116 lines) — shared dataclasses for ACP protocol
  - `core/utils.py` (15 lines) — two sync file-write helpers

**`assets/`:**

- Purpose: Static assets for output rendering
- Contains: `long_text.html` — Jinja-like template for rendering long text as an image via AstrBot's `html_render`
- Key files: `assets/long_text.html`

**`tests/`:**

- Purpose: Test suite organized to mirror source structure
- Contains: 6 test files covering ACP protocol layer, executor, output, session, and main commands
- Key files: `tests/core/test_executor_acp.py`, `tests/core/test_output_events.py`

**`docs/references/`:**

- Purpose: External documentation for ACP protocol, OpenCode, and AstrBot
- Contains: Reference docs consumed by sub-agents and developers

**`.opencode/`:**

- Purpose: OpenCode contributor tooling — config, plugin manifest, lockfile, generated `node_modules/`
- Contains: NOT runtime source; contributor-local tooling only
- Generated: Yes (contains `node_modules/`)
- Committed: Partially (config and manifest are committed; `node_modules/` is generated)

## Key File Locations

**Entry Points:**

- `main.py`: Plugin class `OpenCodePlugin`, all command handlers, LLM tool entry, plugin lifecycle
- `_conf_schema.json`: Config contract and default-value authority — every config-driven behavior should have a matching entry here

**Configuration:**

- `_conf_schema.json`: Plugin settings with descriptions, types, defaults, and hints for the AstrBot config UI
- `metadata.yaml`: Plugin identity (id, version, author, repo)
- `requirements.txt`: Runtime deps (`aiohttp`, `httpx`)

**Core Logic:**

- `core/executor.py`: ACP backend lifecycle, session create/load/prompt/cancel, streaming execution, notification routing
- `core/session.py`: `OpenCodeSession` state object (the per-sender source of truth), `SessionManager` CRUD
- `core/acp_client.py`: Generic ACP JSON-RPC client
- `core/acp_transport_stdio.py`: Subprocess stdio transport for ACP protocol

**Input/Output:**

- `core/input.py`: Message normalization, media download, `ACPPromptPayload` construction
- `core/output.py`: Output pipeline — ANSI cleanup, AI summary, TXT export, long-image, merge-forward, send plan

**Security:**

- `core/security.py`: Admin gating, destructive-op regex, write-op confirmation, path safety

**Persistence:**

- `core/storage.py`: Workdir history JSON persistence, auto-clean background task

**Protocol Models:**

- `core/acp_models.py`: Dataclass definitions for all ACP protocol entities
- `core/acp_adapter.py`: OpenCode-specific payload normalization into plugin-internal models

**Testing:**

- `tests/test_main_commands.py`: Command handler tests
- `tests/core/test_acp_adapter.py`: ACP adapter tests
- `tests/core/test_acp_client.py`: ACP client tests
- `tests/core/test_executor_acp.py`: Executor ACP integration tests
- `tests/core/test_output_events.py`: Output event handling tests
- `tests/core/test_session_state.py`: Session state tests

## Naming Conventions

**Files:**

- Python modules: `snake_case.py` (e.g., `acp_client.py`, `session.py`, `output.py`)
- Config schema: `_conf_schema.json` (underscore prefix, AstrBot convention)
- Metadata: `metadata.yaml` (AstrBot plugin standard)
- Templates: `snake_case.html` (e.g., `long_text.html`)
- Tests: `test_{module_name}.py` mirroring the source structure (e.g., `tests/core/test_acp_client.py` tests `core/acp_client.py`)
- AGENTS.md: One per directory level with sub-agent instructions (root, `core/`, `docs/references/`)

**Directories:**

- `core/` — runtime managers (no subdirectories)
- `tests/core/` — mirrors `core/` structure
- `assets/` — static rendering assets
- `docs/references/` — external documentation
- `.opencode/` — contributor tooling (not runtime source)

**Classes:**

- Managers: PascalCase noun phrases (e.g., `CommandExecutor`, `SessionManager`, `SecurityChecker`, `InputProcessor`, `OutputProcessor`, `StorageManager`)
- Protocol types: PascalCase with ACP prefix (e.g., `ACPClient`, `ACPStdioTransport`, `ACPError`, `ACPSessionState`)
- Session object: `OpenCodeSession` (represents per-sender state)
- Config/decision types: PascalCase (e.g., `ExecutionResult`, `PreflightDecision`, `ACPPromptPayload`)

**Functions/Methods:**

- Private: `_leading_underscore` (e.g., `_build_env`, `_ensure_session_ready`, `_extract_output_text`)
- Callbacks: `set_*_callback` pattern (e.g., `set_record_workdir_callback`, `set_load_history_callback`)
- Async: Standard `async def` prefix
- Command handlers: Named after command (e.g., `oc_handler`, `oc_agent`, `oc_mode`, `oc_send`)

## Where to Add New Code

**New Command:**

- Handler: Add `@filter.command("oc-<name>")` method to `OpenCodePlugin` in `main.py`
- Security: If the command needs admin gating, add `self.security.is_admin(event)` check at the top
- Tests: Add test cases to `tests/test_main_commands.py`

**New ACP Method:**

- Client method: Add `async def method_name(...)` to `ACPClient` in `core/acp_client.py`
- Executor wrapper: Add corresponding method to `CommandExecutor` in `core/executor.py` that calls the client method and returns `ExecutionResult`
- Adapter: Add normalization logic to `OpenCodeACPAdapter` in `core/acp_adapter.py` if payload shape needs mapping
- Model: Add dataclass to `core/acp_models.py` if new protocol entities are needed

**New Output Block:**

- Config: Add block definition to `output_config.output_modes` in `_conf_schema.json`
- Logic: Add block preparation and rendering in `OutputProcessor.parse_output_plan()` in `core/output.py`
- Smart trigger: Add corresponding `smart_trigger_<block_name>` config toggle in `_conf_schema.json`
- Add block key to `ordered_keys` list in `parse_output_plan()`

**New Security Check:**

- Logic: Add method to `SecurityChecker` in `core/security.py`
- Config: Add toggle/keywords to `basic_config` section of `_conf_schema.json`
- Integration: Call from the appropriate handler in `main.py`

**New Session State Field:**

- Field: Add to `OpenCodeSession` in `core/session.py` with initialization in `reset_live_session()`
- Application: Add mapping in `CommandExecutor._apply_session_state()` in `core/executor.py`
- Config: Add default in `_conf_schema.json` if user-configurable

**New Protocol Transport:**

- Transport: Create new transport class implementing the same `send/receive/start/aclose` interface as `ACPStdioTransport`
- Client: Pass the new transport to `ACPClient` constructor
- Executor: Modify `_build_client()` in `core/executor.py` to construct the new transport

**Utilities:**

- Sync helpers: Add to `core/utils.py` — must be pure functions callable from `asyncio.to_thread`
- Do NOT add runtime behavior, managers, or stateful logic to `utils.py`

## Special Directories

**`.opencode/`:**

- Purpose: OpenCode contributor tooling — local config, plugin manifest, lockfile
- Generated: Contains `node_modules/` (generated, not runtime source)
- Committed: Config and manifest files are committed; `node_modules/` is generated locally
- Important: Do NOT treat as runtime source or edit generated content

**`docs/references/`:**

- Purpose: External documentation for ACP protocol, OpenCode, and AstrBot APIs
- Used by sub-agents for context during development
- Consult when implementing protocol changes or AstrBot integration

**`assets/`:**

- Purpose: Rendering template only (`long_text.html`)
- Not a general asset bucket — do not add arbitrary files here
- Template is loaded by `OutputProcessor.render_long_image()` and rendered via AstrBot's `html_render` function

**`.planning/`:**

- Purpose: Codebase analysis documents and implementation plans
- Contains: `codebase/` subdirectory with architecture, structure, conventions docs

**`__pycache__/`, `.ruff_cache/`, `.pytest_cache/`:**

- Purpose: Python bytecode cache, linter cache, pytest cache
- Generated: Yes
- Committed: No (in `.gitignore`)
