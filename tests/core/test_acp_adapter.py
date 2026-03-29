import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_acp_module(module_name: str):
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")

    class DummyLogger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    setattr(api_module, "logger", DummyLogger())
    setattr(astrbot_module, "api", api_module)
    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules["astrbot.api"] = api_module

    package_module = types.ModuleType("fakepkg")
    package_module.__path__ = [str(REPO_ROOT)]
    core_package_module = types.ModuleType("fakepkg.core")
    core_package_module.__path__ = [str(REPO_ROOT / "core")]
    sys.modules["fakepkg"] = package_module
    sys.modules["fakepkg.core"] = core_package_module

    models_spec = importlib.util.spec_from_file_location(
        "fakepkg.core.acp_models", REPO_ROOT / "core" / "acp_models.py"
    )
    assert models_spec is not None
    models_module = importlib.util.module_from_spec(models_spec)
    assert models_spec.loader is not None
    sys.modules["fakepkg.core.acp_models"] = models_module
    models_spec.loader.exec_module(models_module)

    module_spec = importlib.util.spec_from_file_location(
        f"fakepkg.core.{module_name}", REPO_ROOT / "core" / f"{module_name}.py"
    )
    assert module_spec is not None
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    sys.modules[f"fakepkg.core.{module_name}"] = module
    module_spec.loader.exec_module(module)
    return module


def test_mode_options_prefer_config_options_over_modes():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    mode_view = adapter.extract_mode_view(
        config_options=[
            {
                "id": "mode.ask",
                "name": "Ask",
                "category": "mode",
                "value": "ask",
            },
            {
                "id": "model.gpt5",
                "name": "GPT-5",
                "category": "model",
                "value": "gpt-5",
            },
        ],
        modes=[{"id": "legacy-code", "name": "Legacy Code"}],
        current_config_values={"mode.ask": "ask"},
        current_mode_id="legacy-code",
    )

    assert mode_view.source == "configOptions"
    assert [option.option_id for option in mode_view.options] == ["mode.ask"]
    assert mode_view.current_mode_id == "ask"


def test_agent_view_keeps_agent_separate_from_mode_state():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    session_state = adapter.normalize_session_state(
        session_payload={
            "sessionId": "ses_123",
            "agent": {"name": "build", "title": "Build Agent"},
            "configOptions": [
                {
                    "id": "mode.code",
                    "name": "Code",
                    "category": "mode",
                    "value": "code",
                }
            ],
            "currentConfigValues": {"mode.code": "code"},
            "availableCommands": [{"name": "/plan", "title": "Plan"}],
        }
    )

    assert session_state.agent.name == "build"
    assert session_state.agent.title == "Build Agent"
    assert session_state.mode.current_mode_id == "code"
    assert session_state.mode.source == "configOptions"
    assert [option.semantic_kind for option in session_state.config_options] == ["mode"]


def test_session_state_reads_modes_object_and_agent_capabilities_from_acp_v1_payload():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    session_state = adapter.normalize_session_state(
        session_payload={
            "sessionId": "ses_v1",
            "modes": {
                "availableModes": [
                    {"id": "ask", "name": "Ask"},
                    {"id": "code", "name": "Code"},
                ],
                "currentModeId": "code",
            },
            "agentCapabilities": {"imageInput": True},
        }
    )

    assert session_state.mode.source == "modes"
    assert session_state.mode.current_mode_id == "code"
    assert [option.option_id for option in session_state.mode.options] == [
        "ask",
        "code",
    ]
    assert session_state.capabilities == {"imageInput": True}


def test_config_option_semantics_are_explicit_for_mode_and_model():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    session_state = adapter.normalize_session_state(
        session_payload={
            "configOptions": [
                {
                    "id": "mode.ask",
                    "name": "Ask",
                    "category": "mode",
                    "value": "ask",
                },
                {
                    "id": "model.gpt5",
                    "name": "GPT-5",
                    "category": "model",
                    "value": "gpt-5",
                },
                {
                    "id": "approval.default",
                    "name": "Approval",
                    "category": "approval",
                    "value": "manual",
                },
            ]
        }
    )

    assert [option.semantic_kind for option in session_state.config_options] == [
        "mode",
        "model",
        "other",
    ]


def test_permission_options_are_passed_through_without_rewriting():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    permission = adapter.normalize_permission_request(
        {
            "id": "perm_1",
            "sessionId": "ses_123",
            "tool": {"name": "write_file", "title": "Write File", "kind": "write"},
            "arguments": {"path": "/tmp/demo.txt"},
            "options": [
                {"id": "allow_once", "name": "Allow Once"},
                {"id": "allow_custom", "name": "Allow for this folder"},
                {"id": "reject_once", "name": "Reject"},
            ],
        }
    )

    assert permission.request_id == "perm_1"
    assert permission.tool_name == "Write File"
    assert permission.tool_kind == "write"
    assert permission.arguments == {"path": "/tmp/demo.txt"}
    assert [option.option_id for option in permission.options] == [
        "allow_once",
        "allow_custom",
        "reject_once",
    ]
    assert [option.label for option in permission.options] == [
        "Allow Once",
        "Allow for this folder",
        "Reject",
    ]


def test_permission_request_uses_safe_unknown_tool_fallback():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    permission = adapter.normalize_permission_request(
        {
            "id": "perm_missing_tool_name",
            "tool": {"kind": "write"},
            "options": [{"id": "allow_once", "name": "Allow Once"}],
        }
    )

    assert permission.tool_name == "未知工具"


def test_unsupported_commands_are_exposed_alongside_available_commands():
    adapter_module = load_acp_module("acp_adapter")
    adapter = adapter_module.OpenCodeACPAdapter()

    commands = adapter.normalize_commands(
        [{"name": "/plan", "title": "Plan"}, {"name": "/help", "title": "Help"}]
    )

    supported = {command.name for command in commands if command.supported}
    unsupported = {command.name for command in commands if not command.supported}

    assert supported == {"/plan", "/help"}
    assert unsupported == {"/undo", "/redo"}
