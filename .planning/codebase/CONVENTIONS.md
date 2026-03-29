# Coding Conventions

**Analysis Date:** 2026-03-29

## Naming Patterns

**Files:**

- Use `snake_case.py` for all Python modules: `session.py`, `executor.py`, `acp_client.py`
- Test files use `test_` prefix: `test_session_state.py`, `test_acp_adapter.py`
- Package-level files use underscore prefix for AstrBot framework integration: `_conf_schema.json`
- ACP subsystem files use `acp_` prefix: `acp_client.py`, `acp_models.py`, `acp_adapter.py`, `acp_transport_stdio.py`

**Classes:**

- Use `PascalCase`: `OpenCodePlugin`, `SessionManager`, `SecurityChecker`, `ACPClient`, `OpenCodeACPAdapter`
- Result DTOs use descriptive noun phrases: `ExecutionResult`, `SessionEnsureResult`, `PreflightDecision`
- Test doubles use `Fake` prefix: `FakeEvent`, `FakeExecutor`, `FakeClient`, `FakeSecurity`
- ACP model dataclasses use `ACP` prefix: `ACPError`, `ACPModeView`, `ACPAgentInfo`

**Functions:**

- Use `snake_case`: `process_input_message()`, `is_destructive()`, `record_workdir()`
- Private/internal methods use single `_` prefix: `_render_exec_status()`, `_get_basic_config()`, `_coerce_prompt_payload()`
- Async generators use descriptive verb phrases: `stream_prompt()`, `stream_permission_response()`
- Command handlers follow `oc_<command>` pattern: `oc_handler()`, `oc_agent()`, `oc_mode()`, `oc_session()`

**Variables:**

- Use `snake_case`: `final_message`, `sender_id`, `work_dir`, `base_data_dir`
- Boolean variables use `is_`, `has_`, or descriptive nouns: `is_long`, `truncated`, `approved`
- Private instance attributes use single `_` prefix: `_client`, `_pending`, `_reader_task`
- Callback references use `_callback` suffix: `_record_workdir_callback`, `_load_history_callback`

**Constants:**

- Module-level constants use `UPPER_SNAKE_CASE`: `ANSI_COLORS`, `REPO_ROOT`
- Class-level constant sets use `UPPER_SNAKE_CASE`: `STANDARD_PERMISSION_OPTION_IDS`, `UNSUPPORTED_COMMANDS`

**Types:**

- Type aliases use `PascalCase`: `NotificationHandler = Callable[...]`
- Generic type vars follow Python convention

## Code Style

**Formatting:**

- No project-level formatter configuration detected (no `.prettierrc`, `pyproject.toml` `[tool.black]`, etc.)
- Code follows PEP 8 conventions informally: 4-space indent, max ~120 char lines
- `.ruff_cache/` directory present, suggesting Ruff linter is used at some point but no config file is committed

**Linting:**

- No committed linter config file (no `.flake8`, `ruff.toml`, `pyproject.toml` with `[tool.ruff]`)
- Ruff cache directory exists (`.ruff_cache/`) but no configuration

**String Quotes:**

- Consistent use of double quotes throughout: `"basic_config"`, `"only_admin"`
- Single quotes used only in regex patterns: `r"写"`, `r"rm\b"`

**Imports:**

- Standard library first, third-party second, local third
- Use explicit imports over wildcards: `from astrbot.api.event import filter, AstrMessageEvent`
- One known wildcard import at `main.py:18`: `from astrbot.api.all import *` (for `AstrBotConfig`)

## Import Organization

**Order:**

1. Standard library: `import asyncio`, `import os`, `import re`
2. Third-party: `from astrbot.api import logger`, `import aiohttp`
3. Local/relative: `from .core.session import SessionManager`

**Path Aliases:**

- No path aliases configured (no `pyproject.toml` with `[tool.setuptools]`)
- Internal imports use relative paths within `core/`: `from .acp_models import ACPError`
- Test files use `importlib.util` to load source files under `fakepkg.core.*` namespace

**Module Structure (source files):**

```python
"""Module docstring in Chinese or English."""

# imports (stdlib, third-party, local)

# constants

# dataclasses / exception classes

# main classes

# functions
```

Example from `core/acp_models.py`:

```python
"""Shared ACP data models used by transport, client, and adapters."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

NotificationHandler = Callable[[str, dict[str, Any]], Any]

@dataclass(slots=True)
class ACPError(Exception):
    message: str
    # ...
```

## Error Handling

**Patterns:**

- Use typed exception hierarchy for ACP errors: `ACPError → ACPTransportError → ACPStartupError / ACPTimeoutError`
- All ACP operations catch specific exception types and return `ExecutionResult(ok=False, ...)`
- Never let ACP exceptions propagate to command handlers; always wrap in `ExecutionResult`

Example from `core/executor.py`:

```python
try:
    response = await self._get_or_create_client(session).prompt_session(payload)
except (ACPTransportError, ACPError) as exc:
    return ExecutionResult(
        ok=False,
        error_type="acp_prompt_failed",
        message=f"ACP prompt failed: {exc}",
        session_id=session.backend_session_id,
    )
```

- Security checks return `ExecutionResult` or boolean, never raise
- Path safety catches all exceptions and returns `False`: `except Exception as e: ... return False`
- File I/O in storage uses `try/except` with logger warnings, never crashes
- Test doubles raise exceptions to simulate failures

**User-Facing Error Messages:**

- Use Chinese with emoji prefixes: `"❌ 发送失败"`, `"⚠️ 敏感操作确认"`
- Include context: `f"❌ 绑定历史会话失败：{loaded.message}"`
- Consistent format: emoji + description + optional detail

## Logging

**Framework:** AstrBot `logger` from `astrbot.api`

**Access Pattern:**

- Each manager receives `self.logger = logger` in `__init__`
- Use `self.logger.info()` for lifecycle events, `self.logger.warning()` for recoverable issues, `self.logger.error()` for failures

**Patterns:**

```python
self.logger.info(f"Session created for {sender_id} at {work_dir}")
self.logger.warning(f"Failed to create work dir {work_dir}: {e}")
self.logger.error(f"OpenCode 后台执行失败: {e}")
```

**Language:** English for internal log messages, Chinese for user-facing errors (but mixed in practice)

## Comments

**When to Comment:**

- Module-level docstrings describe purpose (Chinese or English)
- Section dividers use `# ===` format for command handlers:
  ```python
  # ==================== 命令处理器 ====================
  # ==================== LLM 工具 ====================
  ```
- Inline comments explain non-obvious logic, compatibility workarounds

**Docstrings:**

- Class docstrings: single line in Chinese: `"""会话管理器"""`
- Method docstrings: present for public APIs, sometimes in Chinese:
  ```python
  def is_path_safe(self, path: str, session=None) -> bool:
      """检查路径是否在允许的范围内"""
  ```
- No JSDoc/TSDoc equivalent; Python docstrings are standard

## Function Design

**Size:** Functions range from 5 to ~100 lines. Larger functions (like `parse_output_plan` at ~180 lines) exist in `core/output.py` and could benefit from decomposition.

**Parameters:**

- Use `Optional[T]` for optional parameters with default `None`
- Config access pattern: `self.config.get("section", {}).get("key", default)`
- Use `**kwargs` sparingly; prefer explicit parameters

**Return Values:**

- Use `ExecutionResult` dataclass for all executor methods (consistent `ok`/`message`/`payload` shape)
- Use tuples for multi-value returns: `tuple[bool, str]`, `tuple[list[int], list[str]]`
- Async generators use `yield` for streaming: `async for item in stream: yield item`
- Command handlers use `yield event.plain_result(...)` / `yield event.chain_result(...)` pattern

## Module Design

**Exports:**

- No `__init__.py` files — the package uses AstrBot's plugin discovery via `@register` decorator
- Each module exports its primary class(es) at module level
- No `__all__` exports defined

**Barrel Files:** Not used. Each module is imported directly:

```python
from .core.session import SessionManager
from .core.storage import StorageManager
from .core.security import SecurityChecker
```

## Data Modeling

**Dataclasses:**

- Use `@dataclass(slots=True)` for all model classes: `ExecutionResult`, `ACPError`, `ACPAgentInfo`
- Use `field(default_factory=...)` for mutable defaults: `field(default_factory=dict)`
- Keep a `raw: dict` field on ACP models for pass-through of unrecognized fields

**Configuration:**

- All config keys and defaults live in `_conf_schema.json` — never hardcode defaults in Python
- Access config via nested dict: `self.config.get("basic_config", {}).get("key", default)`
- Config changes must update `_conf_schema.json` in the same patch

## Async Patterns

**Rules:**

- All command handlers are `async def` methods that `yield` results
- Blocking I/O must use `asyncio.to_thread()`: `await asyncio.to_thread(write_text_file_sync, ...)`
- Background tasks use `asyncio.create_task()`
- Session waiting uses `@session_waiter(timeout=...)` decorator from AstrBot
- Cleanup/termination cancels tasks properly: `task.cancel()` then `await task` with `asyncio.CancelledError` suppression

**Streaming:**

- Use async generators with `{"kind": "event", ...}` and `{"kind": "result", ...}` dicts
- Use `asyncio.Queue` for real-time notification routing
- Use `asyncio.wait({task, queue_task}, return_when=FIRST_COMPLETED)` for interleaved stream/result

## User-Facing Text

**Language:** Chinese for all user-visible strings

**Format:**

- Emoji prefixes for status: `🚀 执行中...`, `✅ 已重置`, `❌ 发送失败`, `⚠️ 敏感操作确认`
- Concise operational style: short status lines, explicit outcome, low fluff
- Safety messages are direct: detect risk → explain why → ask confirmation → fail closed

**Examples:**

```python
"权限不足。"
"✅ 已重置当前 ACP 会话绑定"
"📂 工作目录使用历史（最近10条）：\n"
"❌ 未找到匹配的会话：{query}\n请先使用 /oc-session 查看列表。"
```

---

_Convention analysis: 2026-03-29_
