import asyncio
import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_core_module(module_name: str):
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    components_module = types.ModuleType("astrbot.api.message_components")
    aiohttp_module = types.ModuleType("aiohttp")

    class DummyLogger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    api_module.logger = DummyLogger()
    event_module.AstrMessageEvent = object
    components_module.Plain = type("Plain", (), {})
    components_module.Image = type("Image", (), {})
    components_module.File = type("File", (), {})
    components_module.Reply = type("Reply", (), {})
    aiohttp_module.ClientSession = object
    aiohttp_module.ClientError = Exception
    astrbot_module.api = api_module
    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.message_components"] = components_module
    sys.modules["aiohttp"] = aiohttp_module

    package_module = types.ModuleType("fakepkg")
    package_module.__path__ = [str(REPO_ROOT)]
    core_package_module = types.ModuleType("fakepkg.core")
    core_package_module.__path__ = [str(REPO_ROOT / "core")]
    sys.modules["fakepkg"] = package_module
    sys.modules["fakepkg.core"] = core_package_module

    for dependency in (
        "acp_models",
        "acp_transport_stdio",
        "acp_client",
        "acp_adapter",
        "session",
    ):
        spec = importlib.util.spec_from_file_location(
            f"fakepkg.core.{dependency}", REPO_ROOT / "core" / f"{dependency}.py"
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[f"fakepkg.core.{dependency}"] = module
        spec.loader.exec_module(module)

    module_spec = importlib.util.spec_from_file_location(
        f"fakepkg.core.{module_name}", REPO_ROOT / "core" / f"{module_name}.py"
    )
    assert module_spec is not None
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    sys.modules[f"fakepkg.core.{module_name}"] = module
    module_spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, *, responses=None, initialize_error=None, load_error=None):
        self.responses = responses or {}
        self.initialize_error = initialize_error
        self.load_error = load_error
        self.calls = []
        self.initialized = False
        self.protocol_capabilities = {}
        self.notification_handlers = []

    async def initialize(self, client_capabilities=None, client_info=None):
        self.calls.append(("initialize", client_capabilities or {}, client_info or {}))
        if self.initialize_error:
            raise self.initialize_error
        payload = dict(self.responses.get("initialize") or {})
        self.protocol_capabilities = dict(
            payload.get("agentCapabilities") or payload.get("capabilities") or {}
        )
        self.initialized = True
        return payload

    async def new_session(self, payload=None):
        self.calls.append(("session/new", dict(payload or {})))
        return dict(self.responses.get("session/new") or {})

    async def load_session(self, payload=None):
        self.calls.append(("session/load", dict(payload or {})))
        if self.load_error:
            raise self.load_error
        return dict(self.responses.get("session/load") or {})

    async def prompt_session(self, payload=None):
        self.calls.append(("session/prompt", dict(payload or {})))
        for method, params in self.responses.get("notifications", []):
            for handler in list(self.notification_handlers):
                maybe_awaitable = handler(method, dict(params or {}))
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable
        return dict(self.responses.get("session/prompt") or {})

    async def cancel_session(self, payload=None):
        self.calls.append(("session/cancel", dict(payload or {})))
        return dict(self.responses.get("session/cancel") or {})

    async def list_sessions(self, payload=None):
        self.calls.append(("session/list", dict(payload or {})))
        return dict(self.responses.get("session/list") or {})

    async def set_session_config_option(self, payload=None):
        self.calls.append(("session/set_config_option", dict(payload or {})))
        return dict(self.responses.get("session/set_config_option") or {})

    async def set_session_mode(self, payload=None):
        self.calls.append(("session/set_mode", dict(payload or {})))
        return dict(self.responses.get("session/set_mode") or {})

    def add_notification_handler(self, handler):
        self.notification_handlers.append(handler)


def make_executor_and_session():
    executor_module = load_core_module("executor")
    session_module = load_core_module("session")
    input_module = load_core_module("input")
    executor = executor_module.CommandExecutor(
        {
            "basic_config": {
                "acp_command": "opencode",
                "acp_args": ["acp"],
                "acp_startup_timeout": 30,
                "acp_client_capabilities": {"terminal": True},
            }
        }
    )
    session = session_module.OpenCodeSession(
        work_dir="/tmp/acp-demo",
        env={"DEMO": "1"},
        backend_kind="acp_opencode",
        default_agent="build",
        default_mode="ask",
    )
    return executor_module, executor, session, input_module


def test_executor_creates_session_then_prompts():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/new": {
                "sessionId": "ses_123",
                "agent": {"name": "build", "title": "Build"},
            },
            "session/prompt": {
                "sessionId": "ses_123",
                "stopReason": "end_turn",
                "outputText": "你好",
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "你好"}]},
            session,
        )
    )

    assert result.ok is True
    assert result.stop_reason == "end_turn"
    assert result.final_text == "你好"
    assert session.backend_session_id == "ses_123"
    assert [call[0] for call in fake_client.calls] == [
        "initialize",
        "session/new",
        "session/prompt",
    ]
    assert fake_client.calls[0][2] == {
        "name": "astrbot_plugin_acp",
        "title": "ACP Client",
        "version": "1.3.1",
    }
    assert fake_client.calls[1][1]["cwd"] == "/tmp/acp-demo"
    assert fake_client.calls[1][1]["mcpServers"] == []
    assert fake_client.calls[2][1]["prompt"] == [{"type": "text", "text": "你好"}]


def test_executor_loads_existing_session_when_backend_supports_recovery():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_existing")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/load": {
                "sessionId": "ses_existing",
                "agent": {"name": "plan", "title": "Plan"},
            },
            "session/prompt": {
                "sessionId": "ses_existing",
                "stopReason": "end_turn",
                "outputText": "继续",
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "继续"}]},
            session,
        )
    )

    assert result.ok is True
    assert session.backend_session_id == "ses_existing"
    assert [call[0] for call in fake_client.calls] == [
        "initialize",
        "session/load",
        "session/prompt",
    ]
    assert fake_client.calls[1][1] == {
        "sessionId": "ses_existing",
        "cwd": "/tmp/acp-demo",
        "mcpServers": [],
    }
    assert fake_client.calls[2][1]["prompt"] == [{"type": "text", "text": "继续"}]


def test_executor_prefers_agent_capabilities_for_session_recovery_support():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_existing")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
                "capabilities": {"loadSession": False},
            },
            "session/load": {
                "sessionId": "ses_existing",
                "agent": {"name": "plan", "title": "Plan"},
            },
            "session/prompt": {
                "sessionId": "ses_existing",
                "stopReason": "end_turn",
                "outputText": "继续",
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "继续"}]},
            session,
        )
    )

    assert result.ok is True
    assert fake_client.protocol_capabilities == {"loadSession": True}
    assert [call[0] for call in fake_client.calls] == [
        "initialize",
        "session/load",
        "session/prompt",
    ]


def test_executor_exposes_public_load_session_entry():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_existing")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/load": {
                "sessionId": "ses_existing",
                "agent": {"name": "plan", "title": "Plan"},
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(executor.load_session(session))

    assert result.ok is True
    assert result.session_id == "ses_existing"
    assert result.recovered_session is True
    assert session.backend_session_id == "ses_existing"
    assert [call[0] for call in fake_client.calls] == ["initialize", "session/load"]
    assert fake_client.calls[1][1] == {
        "sessionId": "ses_existing",
        "cwd": "/tmp/acp-demo",
        "mcpServers": [],
    }


def test_executor_explicit_load_session_does_not_fallback_to_new_session_on_failure():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_missing")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/new": {"sessionId": "ses_fresh"},
        },
        load_error=executor_module.ACPError(message="session missing"),
    )
    executor._client = fake_client

    result = asyncio.run(executor.load_session(session))

    assert result.ok is False
    assert result.error_type == "acp_load_session_failed"
    assert "session missing" in result.message
    assert session.backend_session_id is None
    assert [call[0] for call in fake_client.calls] == ["initialize", "session/load"]


def test_executor_explicit_load_session_fails_closed_when_payload_has_no_session_id():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_missing")
    session.pending_permission = {"id": "perm_1"}
    session.prompt_running = True
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/load": {"agent": {"name": "plan", "title": "Plan"}},
        }
    )
    executor._client = fake_client

    result = asyncio.run(executor.load_session(session))

    assert result.ok is False
    assert result.error_type == "acp_load_session_failed"
    assert session.backend_session_id is None
    assert session.pending_permission is None
    assert session.prompt_running is False
    assert [call[0] for call in fake_client.calls] == ["initialize", "session/load"]


def test_executor_explicit_load_session_fails_closed_when_payload_session_id_mismatches_target():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_target")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/load": {
                "sessionId": "ses_other",
                "agent": {"name": "plan", "title": "Plan"},
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(executor.load_session(session))

    assert result.ok is False
    assert result.error_type == "acp_load_session_failed"
    assert session.backend_session_id is None
    assert [call[0] for call in fake_client.calls] == ["initialize", "session/load"]


def test_health_check_reports_unhealthy_when_acp_command_cannot_start():
    executor_module = load_core_module("executor")
    executor = executor_module.CommandExecutor(
        {
            "basic_config": {
                "acp_command": "definitely-not-a-real-opencode-command-xyz",
                "acp_args": ["acp"],
                "acp_startup_timeout": 1,
                "acp_client_capabilities": {"terminal": True},
            }
        }
    )

    ok, detail = asyncio.run(executor.health_check())

    assert ok is False
    assert "ACP" in detail or "acp" in detail.lower()


def test_executor_compat_run_opencode_returns_plain_text_for_current_callers():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/new": {"sessionId": "ses_compat"},
            "session/prompt": {
                "sessionId": "ses_compat",
                "stopReason": "end_turn",
                "outputText": "兼容输出",
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(executor.run_opencode("你好", session))

    assert isinstance(result, executor_module.ExecutionResult)
    assert result.final_text == "兼容输出"


def test_executor_run_opencode_preserves_structured_prompt_payload_for_acp_calls():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/new": {"sessionId": "ses_structured"},
            "session/prompt": {
                "sessionId": "ses_structured",
                "stopReason": "end_turn",
                "outputText": "结构化完成",
            },
        }
    )
    executor._client = fake_client

    class RichPrompt(str):
        def __new__(cls):
            obj = str.__new__(cls, "处理图片")
            obj.content_blocks = [
                {"type": "text", "text": "处理图片"},
                {"type": "image", "uri": "/tmp/demo.png", "mimeType": "image/png"},
            ]
            return obj

        def to_payload(self):
            return {"text": str(self), "prompt": list(self.content_blocks)}

    result = asyncio.run(executor.run_opencode(RichPrompt(), session))

    assert isinstance(result, executor_module.ExecutionResult)
    assert result.final_text == "结构化完成"
    assert fake_client.calls[2][1]["prompt"] == [
        {"type": "text", "text": "处理图片"},
        {"type": "image", "uri": "/tmp/demo.png", "mimeType": "image/png"},
    ]


def test_executor_exposes_only_acp_session_listing_api():
    executor_module, executor, session, input_module = make_executor_and_session()

    assert not hasattr(executor, "list_opencode_sessions")
    assert not hasattr(executor, "exec_shell_cmd")
    assert not hasattr(executor, "is_remote_mode")


def test_executor_list_sessions_returns_execution_result_items_for_acp_callers():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/list": {
                "sessions": [
                    {"sessionId": "ses_1", "title": "First"},
                    {"id": "ses_2", "title": "Second"},
                ]
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(executor.list_sessions(limit=10))

    assert isinstance(result, executor_module.ExecutionResult)
    assert result.ok is True
    assert result.items == [
        {"sessionId": "ses_1", "title": "First"},
        {"id": "ses_2", "title": "Second"},
    ]


def test_executor_falls_back_to_new_session_when_recovery_is_unavailable_or_invalid():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_stale")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/new": {
                "sessionId": "ses_fresh",
                "agent": {"name": "build", "title": "Build"},
            },
            "session/prompt": {
                "sessionId": "ses_fresh",
                "stopReason": "end_turn",
                "outputText": "新会话",
            },
        },
        load_error=executor_module.ACPError(message="session missing"),
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "新会话"}]},
            session,
        )
    )

    assert result.ok is True
    assert result.recovered_session is False
    assert result.session_recovery_failed is True
    assert session.backend_session_id == "ses_fresh"
    assert [call[0] for call in fake_client.calls] == [
        "initialize",
        "session/load",
        "session/new",
        "session/prompt",
    ]


def test_executor_recovery_failure_clears_runtime_flags_before_recreate():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_stale")
    session.pending_permission = {"id": "perm_1"}
    session.prompt_running = True
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/new": {"sessionId": "ses_fresh"},
            "session/prompt": {
                "sessionId": "ses_fresh",
                "stopReason": "end_turn",
                "outputText": "新会话",
            },
        },
        load_error=executor_module.ACPError(message="session missing"),
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "继续"}]},
            session,
        )
    )

    assert result.ok is True
    assert session.backend_session_id == "ses_fresh"
    assert session.pending_permission is None
    assert session.prompt_running is False


def test_executor_reuses_live_session_without_load_when_backend_does_not_support_recovery():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_live")
    session.mark_backend_session_live()
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": False},
            },
            "session/prompt": {
                "sessionId": "ses_live",
                "stopReason": "end_turn",
                "outputText": "continued",
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "fresh"}]},
            session,
        )
    )

    assert result.ok is True
    assert result.recovered_session is False
    assert result.session_recovery_failed is False
    assert session.backend_session_id == "ses_live"
    assert [call[0] for call in fake_client.calls] == [
        "initialize",
        "session/prompt",
    ]


def test_executor_ensure_session_recreates_only_after_history_recovery_failure():
    executor_module, executor, session, input_module = make_executor_and_session()
    session.bind_backend_session("ses_history")
    fake_client = FakeClient(
        responses={
            "initialize": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            },
            "session/new": {"sessionId": "ses_fresh"},
            "session/prompt": {
                "sessionId": "ses_fresh",
                "stopReason": "end_turn",
                "outputText": "fresh",
            },
        },
        load_error=executor_module.ACPError(message="session missing"),
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "fresh"}]},
            session,
        )
    )

    assert result.ok is True
    assert result.recovered_session is False
    assert result.session_recovery_failed is True
    assert session.backend_session_id == "ses_fresh"
    assert session.backend_session_live is True
    assert [call[0] for call in fake_client.calls] == [
        "initialize",
        "session/load",
        "session/new",
        "session/prompt",
    ]


def test_executor_returns_explicit_initialize_failure_result():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        initialize_error=executor_module.ACPStartupError(
            message="ACP process exited during startup.",
            command="opencode",
            exit_code=7,
            stderr_text="boom",
        )
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "hello"}]},
            session,
        )
    )

    assert result.ok is False
    assert result.error_type == "acp_initialize_failed"
    assert "ACP" in result.message
    assert "opencode" in result.message
    assert session.backend_session_id is None


def test_executor_marks_cancelled_run_explicitly():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/new": {"sessionId": "ses_123"},
            "session/prompt": {
                "sessionId": "ses_123",
                "stopReason": "cancelled",
                "outputText": "",
            },
        }
    )
    executor._client = fake_client

    result = asyncio.run(
        executor.run_prompt(
            {"prompt": [{"type": "text", "text": "stop"}]},
            session,
        )
    )

    assert result.ok is False
    assert result.error_type == "cancelled"
    assert result.stop_reason == "cancelled"
    assert "取消" in result.message


def test_executor_run_prompt_accepts_real_acp_prompt_payload_objects():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/new": {"sessionId": "ses_payload"},
            "session/prompt": {
                "sessionId": "ses_payload",
                "stopReason": "end_turn",
                "outputText": "收到",
            },
        }
    )
    executor._client = fake_client
    payload = input_module.ACPPromptPayload(
        "处理图片",
        [
            {"type": "text", "text": "处理图片"},
            {"type": "image", "uri": "/tmp/demo.png", "mimeType": "image/png"},
        ],
    )

    result = asyncio.run(executor.run_prompt(payload, session))

    assert result.ok is True
    assert result.final_text == "收到"
    assert fake_client.calls[2][1]["prompt"] == [
        {"type": "text", "text": "处理图片"},
        {"type": "image", "uri": "/tmp/demo.png", "mimeType": "image/png"},
    ]


def test_executor_coerces_string_dict_and_payload_objects_to_prompt_blocks():
    executor_module, executor, session, input_module = make_executor_and_session()

    plain_payload = executor._coerce_prompt_payload("你好")
    dict_payload = executor._coerce_prompt_payload(
        {"contentBlocks": [{"type": "text", "text": "旧字段"}]}
    )
    rich_payload = executor._coerce_prompt_payload(
        input_module.ACPPromptPayload(
            "处理图片", [{"type": "text", "text": "处理图片"}]
        )
    )

    assert plain_payload == {"prompt": [{"type": "text", "text": "你好"}]}
    assert dict_payload == {"prompt": [{"type": "text", "text": "旧字段"}]}
    assert rich_payload == {
        "text": "处理图片",
        "prompt": [{"type": "text", "text": "处理图片"}],
    }


def test_executor_stream_prompt_emits_runtime_notifications_and_refreshes_session_state():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/new": {
                "sessionId": "ses_runtime",
                "agent": {"name": "build", "title": "Build"},
            },
            "notifications": [
                (
                    "session/update",
                    {
                        "sessionId": "ses_runtime",
                        "update": {
                            "sessionUpdate": "mode_updated",
                            "detail": "已切换到 code",
                            "modes": {
                                "availableModes": [
                                    {"id": "ask", "name": "Ask"},
                                    {"id": "code", "name": "Code"},
                                ],
                                "currentModeId": "code",
                            },
                            "currentConfigValues": {"mode.code": "code"},
                        },
                    },
                ),
                (
                    "session/update",
                    {
                        "sessionId": "ses_runtime",
                        "update": {
                            "sessionUpdate": "permission_requested",
                            "requestId": "perm_runtime",
                            "tool": {
                                "name": "write_file",
                                "kind": "edit",
                                "arguments": {"path": "core/output.py"},
                            },
                            "options": [{"id": "allow_once", "name": "允许一次"}],
                        },
                    },
                ),
            ],
            "session/prompt": {
                "sessionId": "ses_runtime",
                "stopReason": "end_turn",
                "outputText": "完成",
            },
        }
    )
    executor._client = fake_client

    async def collect_stream():
        items = []
        async for item in executor.stream_prompt(
            input_module.ACPPromptPayload(
                "继续",
                [{"type": "text", "text": "继续"}],
            ),
            session,
        ):
            items.append(item)
        return items

    items = asyncio.run(collect_stream())

    assert [item["kind"] for item in items] == ["event", "event", "result"]
    assert items[0]["event"]["type"] == "mode_updated"
    assert items[1]["event"]["type"] == "permission_requested"
    assert items[1]["event"]["requestId"] == "perm_runtime"
    assert items[2]["result"].final_text == "完成"
    assert session.current_mode_id == "code"
    assert session.current_config_values == {"mode.code": "code"}
    assert session.available_modes == [
        {"id": "ask", "name": "Ask"},
        {"id": "code", "name": "Code"},
    ]


def test_normalize_runtime_event_maps_direct_permission_method_to_internal_shape():
    executor_module, executor, session, input_module = make_executor_and_session()

    event = executor._normalize_runtime_event(
        "session/request_permission",
        {
            "id": "perm_123",
            "sessionId": "ses_runtime",
            "tool": {
                "name": "write_file",
                "kind": "edit",
                "arguments": {"path": "core/output.py"},
            },
            "options": [{"id": "allow_once", "name": "允许一次"}],
        },
    )

    assert event["type"] == "permission_requested"
    assert event["requestId"] == "perm_123"
    assert event["sessionId"] == "ses_runtime"
    assert event["tool_name"] == "write_file"
    assert event["tool_kind"] == "edit"
    assert event["arguments"] == {"path": "core/output.py"}
    assert event["options"] == [
        {
            "id": "allow_once",
            "name": "允许一次",
            "optionId": "allow_once",
            "label": "允许一次",
        }
    ]


def test_normalize_runtime_event_unwraps_session_update_payload_and_preserves_permission_shape():
    executor_module, executor, session, input_module = make_executor_and_session()

    event = executor._normalize_runtime_event(
        "session/update",
        {
            "sessionId": "ses_runtime",
            "update": {
                "sessionUpdate": "permission_requested",
                "requestId": "perm_456",
                "tool": {
                    "name": "write_file",
                    "kind": "edit",
                    "arguments": {"path": "core/output.py"},
                },
                "options": [{"id": "allow_once", "name": "允许一次"}],
            },
        },
    )

    assert event["type"] == "permission_requested"
    assert event["requestId"] == "perm_456"
    assert event["sessionId"] == "ses_runtime"
    assert event["tool_name"] == "write_file"
    assert event["tool_kind"] == "edit"
    assert event["arguments"] == {"path": "core/output.py"}
    assert event["options"] == [
        {
            "id": "allow_once",
            "name": "允许一次",
            "optionId": "allow_once",
            "label": "允许一次",
        }
    ]


def test_executor_stream_prompt_emits_permission_event_for_direct_protocol_method():
    executor_module, executor, session, input_module = make_executor_and_session()
    fake_client = FakeClient(
        responses={
            "initialize": {"protocolVersion": 1, "agentCapabilities": {}},
            "session/new": {
                "sessionId": "ses_runtime",
                "agent": {"name": "build", "title": "Build"},
            },
            "notifications": [
                (
                    "session/request_permission",
                    {
                        "id": "perm_123",
                        "sessionId": "ses_runtime",
                        "tool": {
                            "name": "write_file",
                            "kind": "edit",
                            "arguments": {"path": "core/output.py"},
                        },
                        "options": [{"id": "allow_once", "name": "允许一次"}],
                    },
                )
            ],
            "session/prompt": {
                "sessionId": "ses_runtime",
                "stopReason": "end_turn",
                "outputText": "完成",
            },
        }
    )
    executor._client = fake_client

    async def collect_stream():
        items = []
        async for item in executor.stream_prompt(
            input_module.ACPPromptPayload(
                "继续",
                [{"type": "text", "text": "继续"}],
            ),
            session,
        ):
            items.append(item)
        return items

    items = asyncio.run(collect_stream())

    assert [item["kind"] for item in items] == ["event", "result"]
    assert items[0]["event"]["type"] == "permission_requested"
    assert items[0]["event"]["tool_name"] == "write_file"
    assert items[1]["result"].final_text == "完成"
