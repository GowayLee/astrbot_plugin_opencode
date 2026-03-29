import importlib.util
import asyncio
import json
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_session_module():
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")

    class DummyLogger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

    api_module.logger = DummyLogger()
    astrbot_module.api = api_module
    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules["astrbot.api"] = api_module

    spec = importlib.util.spec_from_file_location(
        "session_module", REPO_ROOT / "core" / "session.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_executor_module():
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")

    class DummyLogger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

    class DummyTimeout:
        def __init__(self, *args, **kwargs):
            return None

    class DummyHTTPStatusError(Exception):
        pass

    class DummyRequestError(Exception):
        pass

    httpx_module = types.ModuleType("httpx")
    httpx_module.AsyncClient = DummyAsyncClient
    httpx_module.Timeout = DummyTimeout
    httpx_module.HTTPStatusError = DummyHTTPStatusError
    httpx_module.RequestError = DummyRequestError

    api_module.logger = DummyLogger()
    astrbot_module.api = api_module
    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules["astrbot.api"] = api_module
    sys.modules["httpx"] = httpx_module

    package_module = types.ModuleType("fakepkg")
    package_module.__path__ = [str(REPO_ROOT)]
    core_package_module = types.ModuleType("fakepkg.core")
    core_package_module.__path__ = [str(REPO_ROOT / "core")]
    sys.modules["fakepkg"] = package_module
    sys.modules["fakepkg.core"] = core_package_module

    session_spec = importlib.util.spec_from_file_location(
        "fakepkg.core.session", REPO_ROOT / "core" / "session.py"
    )
    session_module = importlib.util.module_from_spec(session_spec)
    assert session_spec.loader is not None
    session_spec.loader.exec_module(session_module)
    sys.modules["fakepkg.core.session"] = session_module

    executor_spec = importlib.util.spec_from_file_location(
        "fakepkg.core.executor", REPO_ROOT / "core" / "executor.py"
    )
    executor_module = importlib.util.module_from_spec(executor_spec)
    assert executor_spec.loader is not None
    executor_spec.loader.exec_module(executor_module)
    return executor_module


def read_source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_conf_schema_is_acp_only_contract():
    schema = json.loads((REPO_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    items = schema["basic_config"]["items"]

    assert "acp_command" in items
    assert "acp_args" in items
    assert "acp_startup_timeout" in items
    assert "allow_file_writes" in items
    assert "backend_type" not in items
    assert "acp_client_capabilities" not in items
    assert "default_agent" not in items
    assert "default_mode" not in items
    assert "default_config_options" not in items
    assert "confirm_all_write_ops" not in items
    assert "tool_config" not in schema
    assert "output_config" not in schema

    assert "connection_mode" not in items
    assert "remote_server_url" not in items
    assert "remote_username" not in items
    assert "remote_password" not in items
    assert "remote_timeout" not in items
    assert "opencode_path" not in items


def test_session_defaults_keep_preference_and_live_state_separate():
    session_module = load_session_module()
    session = session_module.OpenCodeSession(
        work_dir="/tmp/demo",
        env={},
        backend_kind="acp_opencode",
        default_agent="build",
        default_mode="ask",
        default_config_options={"model": "gpt-5"},
    )

    session.agent_name = "plan"
    session.current_mode_id = "code"
    session.config_options = [{"id": "model", "value": "gpt-5"}]
    session.current_config_values["model"] = "claude"

    assert session.default_agent == "build"
    assert session.default_mode == "ask"
    assert session.default_config_options == {"model": "gpt-5"}
    assert session.agent_name == "plan"
    assert session.current_mode_id == "code"
    assert session.current_config_values == {"model": "claude"}


def test_reset_live_session_preserves_defaults_and_work_dir():
    session_module = load_session_module()
    session = session_module.OpenCodeSession(
        work_dir="/tmp/demo",
        env={},
        backend_kind="acp_opencode",
        default_agent="build",
        default_mode="ask",
        default_config_options={"model": "gpt-5"},
    )
    session.backend_session_id = "ses_123"
    session.protocol_version = 1
    session.agent_name = "plan"
    session.current_mode_id = "code"
    session.config_options = [{"id": "model"}]
    session.current_config_values = {"model": "claude"}
    session.available_modes = [{"id": "ask"}]
    session.available_commands = [{"name": "/help"}]
    session.session_capabilities = {"loadSession": True}
    session.pending_permission = {"id": "perm_1"}
    session.prompt_running = True

    session.reset_live_session()

    assert session.work_dir == "/tmp/demo"
    assert session.default_agent == "build"
    assert session.default_mode == "ask"
    assert session.default_config_options == {"model": "gpt-5"}
    assert session.backend_session_id is None
    assert session.protocol_version is None
    assert session.agent_name is None
    assert session.current_mode_id is None
    assert session.config_options == []
    assert session.current_config_values == {}
    assert session.available_modes == []
    assert session.available_commands == []
    assert session.session_capabilities == {}
    assert session.pending_permission is None
    assert session.prompt_running is False


def test_drop_backend_session_clears_live_state_but_keeps_defaults_and_work_dir():
    session_module = load_session_module()
    session = session_module.OpenCodeSession(
        work_dir="/tmp/demo",
        env={},
        backend_kind="acp_opencode",
        default_agent="build",
        default_mode="ask",
        default_config_options={"model": "gpt-5"},
    )
    session.backend_session_id = "ses_stale"
    session.agent_name = "plan"
    session.current_mode_id = "code"
    session.pending_permission = {"id": "perm_1"}
    session.prompt_running = True

    session.drop_backend_session()

    assert session.work_dir == "/tmp/demo"
    assert session.default_agent == "build"
    assert session.default_mode == "ask"
    assert session.default_config_options == {"model": "gpt-5"}
    assert session.backend_session_id is None
    assert session.agent_name is None
    assert session.current_mode_id is None
    assert session.pending_permission is None
    assert session.prompt_running is False


def test_session_manager_reset_preserves_preferences_and_updates_work_dir(tmp_path):
    session_module = load_session_module()
    config = {
        "basic_config": {
            "backend_type": "acp_opencode",
            "work_dir": str(tmp_path / "default"),
            "default_agent": "build",
            "default_mode": "ask",
            "default_config_options": {"model": "gpt-5"},
            "proxy_url": "",
        }
    }
    manager = session_module.SessionManager(config, str(tmp_path / "data"))

    session = manager.get_or_create_session("alice")
    session.default_agent = "plan"
    session.default_mode = "code"
    session.default_config_options["model"] = "claude"
    session.backend_session_id = "ses_123"
    session.pending_permission = {"id": "perm_1"}
    session.prompt_running = True

    reset_session = manager.reset_session(
        "alice", work_dir=str(tmp_path / "workspace-next")
    )

    assert reset_session is session
    assert reset_session.work_dir == str(tmp_path / "workspace-next")
    assert reset_session.backend_session_id is None
    assert reset_session.pending_permission is None
    assert reset_session.prompt_running is False
    assert reset_session.default_agent == "plan"
    assert reset_session.default_mode == "code"
    assert reset_session.default_config_options == {"model": "claude"}


def test_session_manager_reset_falls_back_when_target_workdir_cannot_be_created(
    tmp_path, monkeypatch
):
    session_module = load_session_module()
    config = {
        "basic_config": {
            "backend_type": "acp_opencode",
            "work_dir": str(tmp_path / "default"),
            "default_agent": "build",
            "default_mode": "ask",
            "default_config_options": {"model": "gpt-5"},
            "proxy_url": "",
        }
    }
    manager = session_module.SessionManager(config, str(tmp_path / "data"))
    session = manager.get_or_create_session("alice")
    session.default_agent = "plan"
    session.default_mode = "code"
    session.backend_session_id = "ses_123"

    blocked_path = str(tmp_path / "blocked")
    original_exists = session_module.os.path.exists
    original_makedirs = session_module.os.makedirs
    original_getcwd = session_module.os.getcwd

    monkeypatch.setattr(
        session_module.os.path,
        "exists",
        lambda path: False if path == blocked_path else original_exists(path),
    )

    def fail_makedirs(path, exist_ok=False):
        if path == blocked_path:
            raise OSError("permission denied")
        return original_makedirs(path, exist_ok=exist_ok)

    monkeypatch.setattr(session_module.os, "makedirs", fail_makedirs)
    monkeypatch.setattr(
        session_module.os, "getcwd", lambda: str(tmp_path / "cwd-fallback")
    )

    reset_session = manager.reset_session("alice", work_dir=blocked_path)

    assert reset_session.work_dir == str(tmp_path / "cwd-fallback")
    assert reset_session.backend_session_id is None
    assert reset_session.default_agent == "plan"
    assert reset_session.default_mode == "code"
    assert reset_session.default_config_options == {"model": "gpt-5"}


def test_binding_existing_backend_session_does_not_overwrite_defaults_or_work_dir(
    tmp_path,
):
    session_module = load_session_module()
    config = {
        "basic_config": {
            "backend_type": "acp_opencode",
            "work_dir": str(tmp_path / "default"),
            "default_agent": "build",
            "default_mode": "ask",
            "default_config_options": {},
            "proxy_url": "",
        }
    }
    manager = session_module.SessionManager(config, str(tmp_path / "data"))

    session = manager.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path / "cwd")
    )
    session.default_agent = "plan"
    session.default_mode = "code"

    session.set_backend_session_id("ses_existing")

    assert session.work_dir == str(tmp_path / "cwd")
    assert session.backend_session_id == "ses_existing"
    assert session.default_agent == "plan"
    assert session.default_mode == "code"


def test_session_manager_does_not_hardcode_backend_default(tmp_path):
    session_module = load_session_module()
    config = {
        "basic_config": {
            "work_dir": str(tmp_path / "default"),
            "default_agent": "build",
            "default_mode": "ask",
            "default_config_options": {},
            "proxy_url": "",
        }
    }
    manager = session_module.SessionManager(config, str(tmp_path / "data"))

    session = manager.get_or_create_session("alice")

    assert session.backend_kind is None


def test_session_manager_uses_builtin_agent_and_mode_fallbacks(tmp_path):
    session_module = load_session_module()
    config = {
        "basic_config": {
            "work_dir": str(tmp_path / "default"),
            "proxy_url": "",
        }
    }
    manager = session_module.SessionManager(config, str(tmp_path / "data"))

    session = manager.get_or_create_session("alice")

    assert session.default_agent == "build"
    assert session.default_mode == "ask"


def test_main_source_has_no_deleted_mode_guidance():
    source = read_source("main.py")

    assert "connection_mode" not in source
    assert "服务器远程模式" not in source
    assert "本地模式" not in source
    assert "切换为 local" not in source


def test_executor_source_has_no_deleted_config_key_lookups():
    source = read_source("core/executor.py")

    assert "connection_mode" not in source
    assert "remote_server_url" not in source
    assert "remote_username" not in source
    assert "remote_password" not in source
    assert "remote_timeout" not in source
    assert "opencode_path" not in source


def test_executor_exposes_canonical_acp_launch_config():
    executor_module = load_executor_module()
    executor = executor_module.CommandExecutor(
        {
            "basic_config": {
                "acp_command": "opencode",
                "acp_args": ["acp", "--stdio"],
                "acp_startup_timeout": 45,
                "acp_client_capabilities": {"terminal": True},
            }
        }
    )

    config = executor.get_acp_launch_config()

    assert config == {
        "backend_type": "acp_opencode",
        "acp_command": "opencode",
        "acp_args": ["acp", "--stdio"],
        "acp_startup_timeout": 45,
        "acp_client_capabilities": {"terminal": True},
    }


def test_executor_health_check_consumes_acp_launch_config():
    executor_module = load_executor_module()
    executor = executor_module.CommandExecutor(
        {
            "basic_config": {
                "acp_command": "opencode",
                "acp_args": ["acp"],
                "acp_startup_timeout": 12,
                "acp_client_capabilities": {
                    "fs_read_text": True,
                    "terminal": True,
                },
            }
        }
    )

    ok, detail = asyncio.run(executor.health_check())

    assert ok is True
    assert (
        detail == "acp_opencode(command=opencode, args=1, timeout=12, capabilities=2)"
    )
