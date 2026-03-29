import asyncio
import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_metadata_yaml():
    items = {}
    for raw_line in (
        (REPO_ROOT / "metadata.yaml").read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        items[key.strip()] = value.strip()
    return items


def load_modules():
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    star_module = types.ModuleType("astrbot.api.star")
    all_module = types.ModuleType("astrbot.api.all")
    message_components_module = types.ModuleType("astrbot.api.message_components")
    astrbot_path_module = types.ModuleType("astrbot.core.utils.astrbot_path")
    session_waiter_module = types.ModuleType("astrbot.core.utils.session_waiter")

    class DummyLogger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    class DummyFilter:
        def command(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def llm_tool(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    class DummyStar:
        def __init__(self, context=None):
            self.context = context

    class DummyContext:
        pass

    class DummySessionController:
        def stop(self):
            return None

    class DummyMessageChain:
        def __init__(self):
            self.chain = []

        def message(self, text):
            self.chain.append(text)
            return self

    def register(*args, **kwargs):
        def decorator(cls):
            return cls

        return decorator

    def session_waiter(*args, **kwargs):
        def decorator(func):
            async def runner(event):
                return await func(DummySessionController(), event)

            return runner

        return decorator

    class DummyFile:
        def __init__(self, file=None, name=None):
            self.file = file
            self.name = name

    api_module.logger = DummyLogger()
    event_module.filter = DummyFilter()
    event_module.AstrMessageEvent = object
    event_module.MessageEventResult = object
    event_module.MessageChain = DummyMessageChain
    star_module.Context = DummyContext
    star_module.Star = DummyStar
    star_module.register = register
    all_module.AstrBotConfig = dict
    message_components_module.File = DummyFile
    astrbot_path_module.get_astrbot_data_path = lambda: "/tmp/astrbot"
    session_waiter_module.session_waiter = session_waiter
    session_waiter_module.SessionController = DummySessionController

    astrbot_module.api = api_module
    sys.modules.setdefault("astrbot", astrbot_module)
    sys.modules["astrbot.api"] = api_module
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module
    sys.modules["astrbot.api.all"] = all_module
    sys.modules["astrbot.api.message_components"] = message_components_module
    sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path_module
    sys.modules["astrbot.core.utils.session_waiter"] = session_waiter_module

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
    sys.modules["fakepkg.core.session"] = session_module
    session_spec.loader.exec_module(session_module)

    for name in ("storage", "security", "input", "executor", "output"):
        module = types.ModuleType(f"fakepkg.core.{name}")
        placeholder = type(f"{name.title()}Placeholder", (), {})
        setattr(
            module,
            {
                "storage": "StorageManager",
                "security": "SecurityChecker",
                "input": "InputProcessor",
                "executor": "CommandExecutor",
                "output": "OutputProcessor",
            }[name],
            placeholder,
        )
        sys.modules[f"fakepkg.core.{name}"] = module

    main_spec = importlib.util.spec_from_file_location(
        "fakepkg.main", REPO_ROOT / "main.py"
    )
    main_module = importlib.util.module_from_spec(main_spec)
    assert main_spec.loader is not None
    sys.modules["fakepkg.main"] = main_module
    main_spec.loader.exec_module(main_module)

    return main_module, session_module


class FakeEvent:
    def __init__(self, sender_id="alice", message_str=""):
        self._sender_id = sender_id
        self.message_str = message_str
        self.sent = []
        self.unified_msg_origin = "umo:test"

    def get_sender_id(self):
        return self._sender_id

    def plain_result(self, text):
        return text

    def chain_result(self, components):
        return components

    async def send(self, payload):
        self.sent.append(payload)


class FakeSecurity:
    def is_admin(self, event):
        return True

    def is_destructive(self, text):
        return False

    def evaluate_preflight(self, text):
        return types.SimpleNamespace(requires_confirmation=False, reason="")

    def is_path_safe(self, path, session):
        return True


class FakeInputProcessor:
    async def process_input_message(self, event, session, raw_command_text=""):
        return {"contentBlocks": [{"type": "text", "text": raw_command_text}]}


class FakeOutputProcessor:
    async def parse_output_plan(self, output, event, session):
        text = getattr(output, "final_text", "") or getattr(output, "message", "")
        return [[[text]]]

    def next_send_delay(self):
        return 0

    def _extract_embedded_events(self, result):
        return list(getattr(result, "payload", {}).get("events", []))

    def build_chat_updates(self, events, session=None):
        updates = []
        for event in events:
            if event.get("type") == "permission_requested":
                if session is not None:
                    session.set_pending_permission(event.get("permission"))
                updates.append("⚠️ 权限确认: write_file")
        return updates


class FakeExecutionResult:
    def __init__(self, *, ok=True, items=None, final_text="", message="", payload=None):
        self.ok = ok
        self.items = list(items or [])
        self.final_text = final_text
        self.message = message
        self.payload = dict(payload or {})


class FakeExecutor:
    def __init__(self):
        self.calls = []
        self.sessions_result = FakeExecutionResult(items=[])
        self.prompt_result = FakeExecutionResult(final_text="完成")
        self.load_session_result = FakeExecutionResult(ok=True)
        self.mode_result = FakeExecutionResult(ok=True)
        self.permission_result = FakeExecutionResult(final_text="权限后完成")
        self.load_session_supported = True
        self.stream_prompt_items = []
        self.stream_permission_items = []

    async def initialize_if_needed(self, session=None):
        self.calls.append(("initialize_if_needed", session is not None))
        return FakeExecutionResult(ok=True)

    def get_protocol_capabilities(self):
        return {"loadSession": self.load_session_supported}

    async def list_sessions(self, limit=10):
        self.calls.append(("list_sessions", limit))
        return self.sessions_result

    async def load_session(self, session):
        self.calls.append(("load_session", session.backend_session_id))
        payload = getattr(self.load_session_result, "payload", {})
        if payload:
            session.agent_name = payload.get("agent_name")
            session.current_mode_id = payload.get("current_mode_id")
            session.current_config_values = dict(
                payload.get("current_config_values", {})
            )
        return self.load_session_result

    async def set_config_option(self, session, option_id, value):
        self.calls.append(("set_config_option", option_id, value))
        return self.mode_result

    async def set_mode(self, session, mode_id):
        self.calls.append(("set_mode", mode_id))
        return self.mode_result

    async def run_prompt(self, prompt_payload, session):
        self.calls.append(("run_prompt", prompt_payload))
        return self.prompt_result

    async def respond_permission(self, session, request_id, option_id):
        self.calls.append(("respond_permission", request_id, option_id))
        session.clear_pending_permission()
        return self.permission_result

    async def stream_prompt(self, prompt_payload, session):
        self.calls.append(("stream_prompt", prompt_payload))
        if self.stream_prompt_items:
            for item in self.stream_prompt_items:
                yield item
            return
        yield {
            "kind": "result",
            "result": await self.run_prompt(prompt_payload, session),
        }

    async def stream_permission_response(self, session, request_id, option_id):
        self.calls.append(("stream_permission_response", request_id, option_id))
        if self.stream_permission_items:
            for item in self.stream_permission_items:
                yield item
            return
        yield {
            "kind": "result",
            "result": await self.respond_permission(session, request_id, option_id),
        }


class FakeContext:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, umo, message_chain):
        self.sent_messages.append((umo, list(message_chain.chain)))


async def collect(async_gen):
    items = []
    async for item in async_gen:
        items.append(item)
    return items


def make_plugin(tmp_path):
    main_module, session_module = load_modules()
    plugin = main_module.OpenCodePlugin.__new__(main_module.OpenCodePlugin)
    plugin.config = {"basic_config": {"confirm_timeout": 30}}
    plugin.base_data_dir = str(tmp_path / "data")
    plugin.logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    plugin.security = FakeSecurity()
    plugin.session_mgr = session_module.SessionManager(
        plugin.config, plugin.base_data_dir
    )
    plugin.input_proc = FakeInputProcessor()
    plugin.output_proc = FakeOutputProcessor()
    plugin.executor = FakeExecutor()
    plugin.context = FakeContext()
    plugin._send_file_list_cache = {}
    return main_module, session_module, plugin


def test_migrate_config_fills_new_runtime_defaults(tmp_path):
    main_module, session_module = load_modules()
    plugin = main_module.OpenCodePlugin.__new__(main_module.OpenCodePlugin)
    plugin.config = {"basic_config": {"confirm_all_write_ops": False}}
    plugin._migrate_config()

    basic_cfg = plugin.config["basic_config"]
    assert basic_cfg["allow_file_writes"] is True
    assert basic_cfg["backend_type"] == "acp_opencode"
    assert basic_cfg["default_agent"] == "build"
    assert basic_cfg["default_mode"] == "ask"
    assert basic_cfg["acp_client_capabilities"]["terminal"] is True
    assert plugin.config["tool_config"]["tool_description"]
    assert plugin.config["output_config"]["output_modes"]


def test_metadata_identity_matches():
    metadata = load_metadata_yaml()
    main_module, _ = load_modules()

    assert metadata["plugin_id"] == metadata["name"]
    assert main_module.PLUGIN_ID == metadata["plugin_id"]
    assert main_module.PLUGIN_DISPLAY_NAME == metadata["display_name"]
    assert main_module.PLUGIN_AUTHOR == metadata["author"]
    assert main_module.PLUGIN_DESCRIPTION == metadata["description"]
    assert main_module.PLUGIN_REPO == metadata["repo"]

    assert "OpenCode" in main_module.PLUGIN_DESCRIPTION
    assert main_module.PLUGIN_ID != "astrbot_plugin_opencode"
    assert main_module.PLUGIN_DISPLAY_NAME != "OpenCode Bridge"
    assert main_module.PLUGIN_AUTHOR != "GowayLee"


def test_oc_handler_blocks_write_when_file_writes_disabled(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)

    plugin.security.evaluate_preflight = lambda text: types.SimpleNamespace(
        requires_confirmation=True,
        reason="file_write_blocked",
    )

    outputs = asyncio.run(
        collect(
            plugin.oc_handler(FakeEvent(message_str="/oc 帮我写文件"), "帮我写文件")
        )
    )

    assert outputs == ["❌ 当前已禁止文件写入操作"]
    assert not plugin.executor.calls


def test_call_opencode_tool_blocks_write_when_file_writes_disabled(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    event = FakeEvent(message_str="/tool")

    plugin.security.evaluate_preflight = lambda text: types.SimpleNamespace(
        requires_confirmation=True,
        reason="file_write_blocked",
    )

    asyncio.run(plugin.call_opencode_tool(event, "帮我写文件"))

    assert plugin.executor.calls == []
    assert event.sent == ["❌ 当前已禁止文件写入操作"]


def test_oc_shell_handler_removed_from_plugin_surface(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)

    assert not hasattr(main_module.OpenCodePlugin, "oc_shell")


def test_exec_status_includes_live_agent_mode_and_config(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.agent_name = "build"
    session.current_mode_id = "ask"
    session.current_config_values = {"mode.ask": "ask", "model": "gpt-5"}

    result = plugin._render_exec_status(session)

    assert "工作目录" in result
    assert "agent" in result.lower()
    assert "build" in result
    assert "ask" in result
    assert "gpt-5" in result


def test_oc_agent_updates_default_only_and_reports_available_agents(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.agent_name = "build"
    session.available_agents = [
        {"name": "build", "title": "Build"},
        {"name": "plan", "title": "Plan"},
        {"name": "review", "title": "Review"},
    ]

    event = FakeEvent(message_str="/oc-agent plan")
    outputs = asyncio.run(collect(plugin.oc_agent(event, "plan")))

    assert session.default_agent == "plan"
    assert session.agent_name == "build"
    assert any("默认 agent" in output for output in outputs)
    assert any(
        "build" in output and "plan" in output and "review" in output
        for output in outputs
    )


def test_oc_session_reports_when_backend_cannot_load_history_session(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    plugin.executor.load_session_supported = False
    plugin.executor.sessions_result = FakeExecutionResult(
        items=[{"sessionId": "ses_1", "title": "第一条"}]
    )

    outputs = asyncio.run(
        collect(plugin.oc_session(FakeEvent(message_str="/oc-session 1"), "1"))
    )

    assert session.backend_session_id is None
    assert ("load_session", "ses_1") not in plugin.executor.calls
    assert any("不支持恢复历史会话" in output for output in outputs)


def test_oc_session_eagerly_loads_and_hydrates_live_state_after_bind(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    plugin.executor.sessions_result = FakeExecutionResult(
        items=[{"sessionId": "ses_1", "title": "第一条"}]
    )
    plugin.executor.load_session_result = FakeExecutionResult(
        ok=True,
        payload={
            "agent_name": "plan",
            "current_mode_id": "code",
            "current_config_values": {"mode.code": "code"},
        },
    )

    outputs = asyncio.run(
        collect(plugin.oc_session(FakeEvent(message_str="/oc-session 1"), "1"))
    )

    assert session.backend_session_id == "ses_1"
    assert ("load_session", "ses_1") in plugin.executor.calls
    assert session.agent_name == "plan"
    assert session.current_mode_id == "code"
    assert any("plan" in output and "code" in output for output in outputs)


def test_oc_session_reports_load_failure_without_leaving_fake_bound_session(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    plugin.executor.sessions_result = FakeExecutionResult(
        items=[{"sessionId": "ses_1", "title": "第一条"}]
    )
    plugin.executor.load_session_result = FakeExecutionResult(
        ok=False,
        message="session missing",
    )

    outputs = asyncio.run(
        collect(plugin.oc_session(FakeEvent(message_str="/oc-session 1"), "1"))
    )

    assert ("load_session", "ses_1") in plugin.executor.calls
    assert session.backend_session_id is None
    assert any("绑定历史会话失败" in output for output in outputs)
    assert any("当前会话: 未绑定" in output for output in outputs)
    assert any(str(tmp_path) in output for output in outputs)


def test_call_opencode_tool_uses_permission_flow_in_background(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    plugin.executor.prompt_result = FakeExecutionResult(
        payload={
            "events": [
                {
                    "type": "permission_requested",
                    "permission": {
                        "requestId": "perm_1",
                        "options": [{"optionId": "allow_once", "label": "允许一次"}],
                    },
                }
            ]
        }
    )
    plugin.executor.permission_result = FakeExecutionResult(final_text="工具执行完成")

    async def fake_wait(event, session):
        return "allow_once", False

    plugin._wait_for_permission_choice = fake_wait

    async def exercise():
        created_tasks = []
        original_create_task = asyncio.create_task

        def run_immediately(coro):
            task = asyncio.get_running_loop().create_task(coro)
            created_tasks.append(task)
            return task

        asyncio.create_task = run_immediately
        try:
            await plugin.call_opencode_tool(
                FakeEvent(message_str="/tool"), "帮我写文件"
            )
            if created_tasks:
                await asyncio.gather(*created_tasks)
        finally:
            asyncio.create_task = original_create_task

    asyncio.run(exercise())

    assert ("respond_permission", "perm_1", "allow_once") in plugin.executor.calls
    assert plugin.context.sent_messages
    assert any(
        "工具执行完成" in str(message) for _, message in plugin.context.sent_messages
    )


def test_oc_and_tool_share_common_execution_launcher(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    calls = []

    async def fake_prepare(event, task_description, *, empty_message):
        session = plugin.session_mgr.get_or_create_session(event.get_sender_id())
        return (
            session,
            {"contentBlocks": [{"type": "text", "text": task_description}]},
            "",
        )

    async def fake_start(
        event,
        session,
        prompt_payload,
        *,
        background,
        emit_status,
    ):
        calls.append(
            {
                "sender": event.get_sender_id(),
                "session": session,
                "payload": prompt_payload,
                "background": background,
                "emit_status": emit_status,
            }
        )
        if not background:
            if False:
                yield None
            return

    plugin._prepare_oc_execution = fake_prepare
    plugin._start_oc_execution = fake_start

    async def exercise():
        chat_outputs = await collect(
            plugin.oc_handler(FakeEvent(message_str="/oc 第一条"), "第一条")
        )
        await plugin.call_opencode_tool(FakeEvent(message_str="/tool"), "第二条")
        return chat_outputs

    outputs = asyncio.run(exercise())

    assert outputs == []
    assert len(calls) == 2
    assert calls[0]["session"] is calls[1]["session"]
    assert calls[0]["background"] is False
    assert calls[1]["background"] is True
    assert calls[0]["emit_status"] is True
    assert calls[1]["emit_status"] is True


def test_oc_handler_consumes_live_permission_updates_before_prompt_returns(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    plugin.executor.stream_prompt_items = [
        {
            "kind": "event",
            "event": {
                "type": "permission_requested",
                "permission": {
                    "requestId": "perm_live",
                    "options": [{"optionId": "allow_once", "label": "允许一次"}],
                },
            },
        }
    ]
    plugin.executor.stream_permission_items = [
        {
            "kind": "result",
            "result": FakeExecutionResult(final_text="直播权限后完成"),
        }
    ]

    async def fake_wait(event, session):
        return "allow_once", False

    plugin._wait_for_permission_choice = fake_wait

    outputs = asyncio.run(
        collect(
            plugin.oc_handler(FakeEvent(message_str="/oc 帮我写文件"), "帮我写文件")
        )
    )

    assert any("权限确认" in str(output) for output in outputs)
    assert (
        "stream_prompt",
        {"contentBlocks": [{"type": "text", "text": "帮我写文件"}]},
    ) in plugin.executor.calls
    assert (
        "stream_permission_response",
        "perm_live",
        "allow_once",
    ) in plugin.executor.calls
    assert any("直播权限后完成" in str(output) for output in outputs)


def test_oc_mode_lists_config_options_before_legacy_modes(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.current_mode_id = "ask"
    session.config_options = [
        {"id": "mode.ask", "category": "mode", "name": "ask", "value": "ask"},
        {"id": "mode.code", "category": "mode", "name": "code", "value": "code"},
    ]
    session.available_modes = [{"id": "legacy", "name": "legacy"}]

    outputs = asyncio.run(
        collect(plugin.oc_mode(FakeEvent(message_str="/oc-mode"), ""))
    )

    rendered = "\n".join(outputs)
    assert "ask" in rendered
    assert "code" in rendered
    assert "legacy" not in rendered


def test_oc_mode_setting_updates_live_session_and_defaults(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.backend_session_id = "ses_live"
    session.config_options = [
        {"id": "mode.ask", "category": "mode", "name": "ask", "value": "ask"},
        {"id": "mode.code", "category": "mode", "name": "code", "value": "code"},
    ]

    outputs = asyncio.run(
        collect(plugin.oc_mode(FakeEvent(message_str="/oc-mode code"), "code"))
    )

    assert session.default_mode == "code"
    assert session.default_config_options["mode.code"] == "code"
    assert ("set_config_option", "mode.code", "code") in plugin.executor.calls
    assert any("当前模式" in output or "mode" in output.lower() for output in outputs)


def test_oc_session_lists_and_binds_backend_sessions(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    plugin.executor.sessions_result = FakeExecutionResult(
        items=[
            {"sessionId": "ses_1", "title": "第一条"},
            {"id": "ses_2", "title": "第二条"},
        ]
    )

    list_outputs = asyncio.run(
        collect(plugin.oc_session(FakeEvent(message_str="/oc-session"), ""))
    )
    bind_outputs = asyncio.run(
        collect(plugin.oc_session(FakeEvent(message_str="/oc-session 2"), "2"))
    )

    assert "ses_1" in "\n".join(list_outputs)
    assert session.backend_session_id == "ses_2"
    assert any("已绑定" in output or "已切换" in output for output in bind_outputs)


def test_oc_end_clears_live_session_but_keeps_preferences(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.backend_session_id = "ses_live"
    session.default_agent = "plan"
    session.default_mode = "code"
    session.pending_permission = {"id": "perm_1"}

    outputs = asyncio.run(collect(plugin.oc_end(FakeEvent(message_str="/oc-end"))))

    assert session.backend_session_id is None
    assert session.pending_permission is None
    assert session.default_agent == "plan"
    assert session.default_mode == "code"
    assert any("已结束" in output for output in outputs)
    assert any(str(tmp_path) in output for output in outputs)
    assert any("当前会话: 未绑定" in output for output in outputs)


def test_oc_end_without_existing_session_still_reports_stable_sender_state(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    plugin.config["basic_config"]["work_dir"] = str(tmp_path / "default")

    outputs = asyncio.run(collect(plugin.oc_end(FakeEvent(message_str="/oc-end"))))

    session = plugin.session_mgr.get_session("alice")
    assert session is not None
    assert session.backend_session_id is None
    assert any("已结束" in output for output in outputs)
    assert any("当前会话: 未绑定" in output for output in outputs)
    assert any(str(tmp_path / "default") in output for output in outputs)


def test_oc_new_resets_live_session_and_switches_workdir(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    session = plugin.session_mgr.get_or_create_session("alice")
    session.backend_session_id = "ses_live"
    session.default_agent = "plan"
    target_dir = tmp_path / "next-workdir"
    target_dir.mkdir()

    outputs = asyncio.run(
        collect(
            plugin.oc_new(
                FakeEvent(message_str=f"/oc-new {target_dir}"), str(target_dir)
            )
        )
    )

    assert session.work_dir == str(target_dir)
    assert session.backend_session_id is None
    assert session.default_agent == "plan"
    assert any(str(target_dir) in output for output in outputs)
    assert any("当前会话: 未绑定" in output for output in outputs)


def test_oc_new_without_path_resets_to_default_workdir_and_keeps_preferences(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    plugin.config["basic_config"]["work_dir"] = str(tmp_path / "default")
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.backend_session_id = "ses_live"
    session.default_agent = "plan"
    session.default_mode = "code"

    outputs = asyncio.run(collect(plugin.oc_new(FakeEvent(message_str="/oc-new"), "")))

    assert session.work_dir == str(tmp_path / "default")
    assert session.backend_session_id is None
    assert session.default_agent == "plan"
    assert session.default_mode == "code"
    assert any(str(tmp_path / "default") in output for output in outputs)
    assert any("当前会话: 未绑定" in output for output in outputs)


def test_oc_new_rejects_missing_directory_and_falls_back_to_default_workdir(tmp_path):
    main_module, session_module, plugin = make_plugin(tmp_path)
    plugin.config["basic_config"]["work_dir"] = str(tmp_path / "default")
    session = plugin.session_mgr.get_or_create_session(
        "alice", custom_work_dir=str(tmp_path)
    )
    session.backend_session_id = "ses_live"
    session.default_agent = "plan"
    missing_dir = tmp_path / "missing"
    event = FakeEvent(message_str="n")

    outputs = asyncio.run(collect(plugin.oc_new(event, str(missing_dir))))

    assert any("目录不存在" in output for output in outputs)
    assert any("已取消自定义路径" in output for output in event.sent)
    assert any(str(tmp_path / "default") in output for output in event.sent)
    assert session.work_dir == str(tmp_path / "default")
    assert session.backend_session_id is None
    assert session.default_agent == "plan"
