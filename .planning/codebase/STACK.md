# Technology Stack

**Analysis Date:** 2026-03-29

## Languages

**Primary:**

- Python 3.10+ — all plugin runtime code (`main.py`, `core/*.py`, `tests/`)
  - Uses `dataclass(slots=True)` (3.10+)
  - Uses `X | None` union type syntax (3.10+)
  - Fully async (`asyncio`) architecture throughout

**Secondary:**

- HTML — long-image rendering template (`assets/long_text.html`)
- JSON — config schema (`_conf_schema.json`), ACP protocol payloads
- YAML — plugin metadata (`metadata.yaml`)
- JSON-RPC 2.0 — wire protocol for ACP backend communication

## Runtime

**Environment:**

- Python 3.10+ (no `.python-version` file; minimum inferred from syntax features)
- Async-first: all I/O uses `asyncio`; blocking file writes offloaded via `asyncio.to_thread`

**Package Manager:**

- pip (inferred from `requirements.txt`)
- Lockfile: not present

## Frameworks

**Core:**

- AstrBot Plugin SDK — host framework providing plugin lifecycle, command routing, LLM tool registration, message primitives, session waiter, and HTML rendering
  - Registration: `@register("id", "author", "desc", "version", "repo")` in `main.py:31-37`
  - Commands: `@filter.command("oc")` in `main.py:657`
  - LLM tools: `@filter.llm_tool(name="call_opencode")` in `main.py:1099`
  - Session waiter: `from astrbot.core.utils.session_waiter import session_waiter, SessionController` in `main.py:19`

**Testing:**

- pytest — test runner (`.pytest_cache/` present, `tests/` directory)
- No test config file; tests self-bootstrap via manual module stubbing (see `tests/test_main_commands.py:11-146`)

**Build/Dev:**

- ruff — linter/formatter (`.ruff_cache/` present, no config file found)
- No build system (`pyproject.toml` absent, `setup.py` absent)
- No CI/CD configuration

## Key Dependencies

**Critical:**

- `aiohttp` — async HTTP client; used in `core/input.py:169` for downloading media resources (images, files) from chat platform URLs into the `downloaded/` directory
- `httpx` — listed in `requirements.txt` but not directly imported in current source files; likely a transitive or future-use dependency

**Host-provided (not in requirements.txt):**

- `astrbot.api` — plugin SDK (lifecycle, events, logger, message components)
- `astrbot.api.event` — `AstrMessageEvent`, `MessageEventResult`, `filter`, `MessageChain`
- `astrbot.api.star` — `Context`, `Star`, `register`
- `astrbot.api.message_components` — `Plain`, `Image`, `File`, `Node`, `Nodes`, `Reply`
- `astrbot.core.utils.astrbot_path` — `get_astrbot_data_path()`
- `astrbot.core.utils.session_waiter` — `session_waiter()`, `SessionController`

## Key Protocols

**ACP (Agent Communication Protocol):**

- JSON-RPC 2.0 over stdio (subprocess transport)
- Implemented in `core/acp_transport_stdio.py`, `core/acp_client.py`, `core/acp_models.py`, `core/acp_adapter.py`
- Transport: spawns OpenCode CLI as subprocess (`opencode acp`), communicates via stdin/stdout JSON lines
- Methods: `initialize`, `session/new`, `session/load`, `session/prompt`, `session/cancel`, `session/list`, `session/set_config_option`, `session/set_mode`, `session/respond_permission`
- Server-push notifications handled via JSON-RPC notification handlers (permission requests, runtime events)

## Configuration

**Plugin Config Schema:**

- `_conf_schema.json` — defines all user-facing config with defaults and descriptions
- Three config sections: `basic_config`, `tool_config`, `output_config`
- Loaded by AstrBot and passed to plugin constructor as `config` dict

**Key Config Values (from `_conf_schema.json`):**

- `basic_config.backend_type` — `"acp_opencode"` (only supported backend)
- `basic_config.acp_command` — `"opencode"` (CLI command to launch ACP backend)
- `basic_config.acp_args` — `["acp"]` (subcommand arguments)
- `basic_config.acp_startup_timeout` — 30 seconds
- `basic_config.work_dir` — default working directory (empty = `<plugin_data>/workspace`)
- `basic_config.proxy_url` — HTTP proxy for ACP subprocess environment
- `output_config.output_modes` — `["ai_summary", "txt_file", "long_image", "full_text"]`

**Environment:**

- Proxy settings propagated to ACP subprocess via `session.env` in `core/session.py:178-188`
- `http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY` set from config

**ContextWeaver (optional dev tool):**

- `cwconfig.json` — semantic code indexing config; indexes `core/**` and `main.py`

## Platform Requirements

**Development:**

- Python 3.10+
- AstrBot running instance (provides plugin SDK at runtime)
- OpenCode CLI installed and accessible in PATH (for ACP backend)
- Dependencies: `pip install -r requirements.txt`

**Production:**

- Deployed as an AstrBot plugin via plugin marketplace or git clone
- Plugin data directory: `<astrbot_data>/plugin_data/astrbot_plugin_opencode/`
- Runtime spawns OpenCode CLI subprocess for each ACP session

---

_Stack analysis: 2026-03-29_
