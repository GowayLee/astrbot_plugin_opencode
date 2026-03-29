# Testing Patterns

**Analysis Date:** 2026-03-29

## Test Framework

**Runner:**

- pytest (implied by `.pytest_cache/` and `tests/` structure)
- No `pytest.ini`, `conftest.py`, or `pyproject.toml` with pytest config detected
- Tests run against source files loaded via `importlib.util` with manual module injection

**Assertion Library:**

- Standard Python `assert` statements exclusively — no `unittest.TestCase`, no `assertpy`, no `pytest.assert`

**Run Commands:**

```bash
pytest tests/                       # Run all tests
pytest tests/core/test_session_state.py  # Run single file
pytest -x                           # Stop on first failure
```

## Test File Organization

**Location:**

- Tests in separate `tests/` directory, mirroring source structure
- Core tests: `tests/core/test_session_state.py`, `tests/core/test_acp_adapter.py`, `tests/core/test_acp_client.py`, `tests/core/test_executor_acp.py`, `tests/core/test_output_events.py`
- Main command tests: `tests/test_main_commands.py`
- No `tests/` sub-init files

**Naming:**

- Pattern: `test_<module_or_feature>.py`
- Examples: `test_session_state.py`, `test_acp_adapter.py`, `test_executor_acp.py`

**Structure:**

```
tests/
├── test_main_commands.py          # Plugin command handler tests
└── core/
    ├── test_session_state.py      # Session & config schema tests
    ├── test_acp_adapter.py        # ACP adapter normalization tests
    ├── test_acp_client.py         # ACP client transport tests
    ├── test_executor_acp.py       # ACP executor integration tests
    └── test_output_events.py      # Output processor & event tests
```

## Module Loading Pattern (Critical)

This project uses a **manual module injection** pattern because it depends on the AstrBot framework, which is not available in a test environment. Every test file implements its own module loader.

**Standard Pattern:**

```python
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # or parents[1] for root tests

def load_core_module(module_name: str):
    # 1. Create fake astrbot modules
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")

    # 2. Create DummyLogger
    class DummyLogger:
        def info(self, *args, **kwargs): return None
        def warning(self, *args, **kwargs): return None
        def error(self, *args, **kwargs): return None

    api_module.logger = DummyLogger()

    # 3. Register in sys.modules
    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules["astrbot.api"] = api_module

    # 4. Create fake package namespace
    package_module = types.ModuleType("fakepkg")
    package_module.__path__ = [str(REPO_ROOT)]
    core_package_module = types.ModuleType("fakepkg.core")
    core_package_module.__path__ = [str(REPO_ROOT / "core")]
    sys.modules["fakepkg"] = package_module
    sys.modules["fakepkg.core"] = core_package_module

    # 5. Load dependencies first
    for dependency in ("acp_models", "acp_transport_stdio", "session"):
        spec = importlib.util.spec_from_file_location(
            f"fakepkg.core.{dependency}", REPO_ROOT / "core" / f"{dependency}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"fakepkg.core.{dependency}"] = module
        spec.loader.exec_module(module)

    # 6. Load target module
    module_spec = importlib.util.spec_from_file_location(
        f"fakepkg.core.{module_name}", REPO_ROOT / "core" / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[f"fakepkg.core.{module_name}"] = module
    module_spec.loader.exec_module(module)
    return module
```

**Key Points:**

- Source modules are loaded under `fakepkg.core.*` namespace (not their real names) to avoid import conflicts
- AstrBot dependencies are stubbed as `types.ModuleType` with dummy classes
- Each test file repeats this pattern with slight variations for its specific dependencies
- No shared `conftest.py` — each file is self-contained

## Test Doubles (Fakes)

**Pattern:** Use `Fake*` classes with manual state tracking, not `unittest.mock.Mock`.

**FakeExecutor** (`tests/test_main_commands.py`):

```python
class FakeExecutor:
    def __init__(self):
        self.calls = []                    # Tracks all method calls
        self.sessions_result = FakeExecutionResult(items=[])
        self.prompt_result = FakeExecutionResult(final_text="完成")

    async def run_prompt(self, prompt_payload, session):
        self.calls.append(("run_prompt", prompt_payload))
        return self.prompt_result

    async def stream_prompt(self, prompt_payload, session):
        self.calls.append(("stream_prompt", prompt_payload))
        yield {"kind": "result", "result": await self.run_prompt(prompt_payload, session)}
```

**FakeClient** (`tests/core/test_executor_acp.py`):

```python
class FakeClient:
    def __init__(self, *, responses=None, initialize_error=None, load_error=None):
        self.responses = responses or {}
        self.initialize_error = initialize_error
        self.calls = []

    async def initialize(self, client_capabilities=None, client_info=None):
        self.calls.append(("initialize", client_capabilities or {}, client_info or {}))
        if self.initialize_error:
            raise self.initialize_error
        return dict(self.responses.get("initialize") or {})
```

**FakeEvent** (`tests/test_main_commands.py`):

```python
class FakeEvent:
    def __init__(self, sender_id="alice", message_str=""):
        self._sender_id = sender_id
        self.message_str = message_str
        self.sent = []

    def get_sender_id(self):
        return self._sender_id

    def plain_result(self, text):
        return text

    async def send(self, payload):
        self.sent.append(payload)
```

**What to Fake:**

- All AstrBot framework classes: `AstrMessageEvent`, `Context`, `Star`, `filter`, `session_waiter`
- External HTTP clients: `aiohttp.ClientSession`, `httpx.AsyncClient`
- Subprocess-based transports: Replace `ACPStdioTransport` with `FailingReceiveTransport` / `FailingSendTransport`

**What NOT to Fake:**

- ACP model dataclasses (`ACPError`, `ExecutionResult`) — use real instances
- Session state (`OpenCodeSession`) — always use real instances
- ACP adapter logic (`OpenCodeACPAdapter`) — test with real instances and fake payloads

## Test Structure

**Suite Organization:**

```python
# Flat test functions (no classes)
def test_executor_creates_session_then_prompts():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(responses={...})
    executor._client = fake_client

    result = asyncio.run(executor.run_prompt(...))

    assert result.ok is True
    assert result.final_text == "你好"
    assert session.backend_session_id == "ses_123"
    assert [call[0] for call in fake_client.calls] == [
        "initialize", "session/new", "session/prompt",
    ]
```

**Patterns:**

- All tests are flat `def test_*()` functions — no `unittest.TestCase` classes
- Setup: call `make_*()` factory function, inject fakes, configure responses
- Execute: `asyncio.run()` for async code, `asyncio.run(collect(...))` for async generators
- Assert: check return values, side-effect state, call histories

**Helper — Async Generator Collection:**

```python
async def collect(async_gen):
    items = []
    async for item in async_gen:
        items.append(item)
    return items
```

**Helper — Plugin Construction:**

```python
def make_plugin(tmp_path):
    main_module, session_module = load_modules()
    plugin = main_module.OpenCodePlugin.__new__(main_module.OpenCodePlugin)
    plugin.config = {"basic_config": {"confirm_timeout": 30}}
    plugin.base_data_dir = str(tmp_path / "data")
    plugin.security = FakeSecurity()
    plugin.session_mgr = session_module.SessionManager(plugin.config, plugin.base_data_dir)
    plugin.executor = FakeExecutor()
    # ...
    return main_module, session_module, plugin
```

## Fixtures and Factories

**Test Data:**

- No shared fixtures or `conftest.py`
- Each test constructs its own data inline
- `FakeExecutionResult` used as a lightweight DTO for simulating executor returns:
  ```python
  class FakeExecutionResult:
      def __init__(self, *, ok=True, items=None, final_text="", message="", payload=None):
          self.ok = ok
          self.items = list(items or [])
          self.final_text = final_text
          self.message = message
          self.payload = dict(payload or {})
  ```

**Location:**

- Fakes defined at module level in each test file
- No shared `fixtures/` or `helpers/` directory

## Coverage

**Requirements:** None enforced (no `--cov` config, no coverage target)

**View Coverage:**

```bash
pytest --cov=. tests/    # If pytest-cov is installed
```

## Test Types

**Unit Tests:**

- Primary test type for all core modules
- Test individual functions/methods in isolation with fake dependencies
- Examples: `test_mode_options_prefer_config_options_over_modes()`, `test_session_defaults_keep_preference_and_live_state_separate()`

**Integration Tests:**

- `test_executor_acp.py` tests the executor → ACP client → response pipeline with `FakeClient`
- `test_main_commands.py` tests command handler → executor → output pipeline with all fakes wired
- `test_output_events.py` tests the full output processing chain including event folding

**E2E Tests:** Not used. No tests launch the actual OpenCode binary or connect to real backends.

## Common Patterns

**Async Testing:**

```python
# Simple async function
result = asyncio.run(executor.run_prompt(payload, session))

# Async generator
outputs = asyncio.run(collect(plugin.oc_handler(event, "message")))

# Background task testing
async def exercise():
    created_tasks = []
    original_create_task = asyncio.create_task
    def run_immediately(coro):
        task = asyncio.get_running_loop().create_task(coro)
        created_tasks.append(task)
        return task
    asyncio.create_task = run_immediately
    try:
        await plugin.call_opencode_tool(event, "task")
        if created_tasks:
            await asyncio.gather(*created_tasks)
    finally:
        asyncio.create_task = original_create_task
asyncio.run(exercise())
```

**Error Testing:**

```python
# Test that errors are caught and returned as ExecutionResult
async def scenario():
    try:
        await client.request("initialize", {})
    except ACPTransportError as exc:
        assert str(exc) == "Expected message"
        return
    raise AssertionError("expected ACPTransportError to be raised")
asyncio.run(scenario())
```

**Call Tracking:**

```python
# Verify method calls and arguments
assert [call[0] for call in fake_client.calls] == [
    "initialize", "session/new", "session/prompt",
]
assert ("respond_permission", "perm_1", "allow_once") in plugin.executor.calls
```

**State Verification:**

```python
# Check session state after operations
assert session.backend_session_id is None
assert session.pending_permission is None
assert session.default_agent == "plan"
```

**Source-Level Regression Guards:**

```python
def test_main_source_has_no_deleted_mode_guidance():
    source = read_source("main.py")
    assert "connection_mode" not in source
    assert "服务器远程模式" not in source
```

**Schema Contract Tests:**

```python
def test_conf_schema_is_acp_only_contract():
    schema = json.loads((REPO_ROOT / "_conf_schema.json").read_text())
    items = schema["basic_config"]["items"]
    assert "backend_type" in items
    assert "acp_command" in items
    assert "connection_mode" not in items
```

---

_Testing analysis: 2026-03-29_
