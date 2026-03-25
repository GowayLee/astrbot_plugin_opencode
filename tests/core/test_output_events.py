import asyncio
import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_core_modules():
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

    class Plain:
        def __init__(self, text):
            self.text = text

    class Image:
        def __init__(self, url=None, mime_type=None, name=None):
            self.url = url
            self.mime_type = mime_type
            self.name = name

        @classmethod
        def fromURL(cls, url):
            obj = cls()
            obj.url = url
            return obj

    class File:
        def __init__(self, file=None, name=None):
            self.file = file
            self.name = name

    class Reply:
        def __init__(self, chain=None):
            self.chain = chain or []

    class Node:
        def __init__(self, uin=None, name=None, content=None):
            self.uin = uin
            self.name = name
            self.content = content or []

    class Nodes:
        def __init__(self, nodes=None):
            self.nodes = nodes or []

    class AstrMessageEvent:
        unified_msg_origin = "test-origin"

        def get_self_id(self):
            return "bot"

    api_module.logger = DummyLogger()
    aiohttp_module.ClientSession = object
    aiohttp_module.ClientError = Exception
    event_module.AstrMessageEvent = AstrMessageEvent
    components_module.Plain = Plain
    components_module.Image = Image
    components_module.File = File
    components_module.Reply = Reply
    components_module.Node = Node
    components_module.Nodes = Nodes

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

    for dependency in ("session", "executor", "utils"):
        spec = importlib.util.spec_from_file_location(
            f"fakepkg.core.{dependency}", REPO_ROOT / "core" / f"{dependency}.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[f"fakepkg.core.{dependency}"] = module
        spec.loader.exec_module(module)

    output_spec = importlib.util.spec_from_file_location(
        "fakepkg.core.output", REPO_ROOT / "core" / "output.py"
    )
    output_module = importlib.util.module_from_spec(output_spec)
    assert output_spec.loader is not None
    sys.modules["fakepkg.core.output"] = output_module
    output_spec.loader.exec_module(output_module)

    input_spec = importlib.util.spec_from_file_location(
        "fakepkg.core.input", REPO_ROOT / "core" / "input.py"
    )
    input_module = importlib.util.module_from_spec(input_spec)
    assert input_spec.loader is not None
    sys.modules["fakepkg.core.input"] = input_module
    input_spec.loader.exec_module(input_module)

    return (
        output_module,
        input_module,
        sys.modules["fakepkg.core.session"],
        sys.modules["fakepkg.core.executor"],
    )


def make_processor():
    output_module, input_module, session_module, executor_module = load_core_modules()
    processor = output_module.OutputProcessor(
        {
            "output_config": {
                "output_modes": ["full_text"],
                "max_text_length": 1000,
                "merge_forward_enabled": True,
                "smart_trigger_ai_summary": False,
                "smart_trigger_txt_file": False,
                "smart_trigger_long_image": False,
            }
        },
        "/tmp/opencode-tests",
    )
    event = sys.modules["astrbot.api.event"].AstrMessageEvent()
    session = session_module.OpenCodeSession(work_dir="/tmp/demo", env={})
    return processor, event, session, executor_module, input_module


def extract_plain_text(send_plan):
    component = send_plan[0][0]
    return getattr(component, "text", None)


def test_permission_event_interrupts_normal_progress_output():
    processor, event, session, executor_module, input_module = make_processor()

    updates = processor.build_chat_updates(
        [
            {"type": "run_started"},
            {"type": "tool_started", "title": "编辑文件", "detail": "core/output.py"},
            {
                "type": "permission_requested",
                "tool_name": "write_file",
                "tool_kind": "edit",
                "arguments": {"path": "core/output.py"},
                "options": [
                    {"optionId": "allow_once", "label": "允许一次"},
                    {"optionId": "sandbox.bypass", "label": "跳过沙箱"},
                ],
            },
        ],
        session=session,
    )

    assert updates[0].startswith("🚀")
    assert any("编辑文件" in item for item in updates)
    assert updates[-1].startswith("⚠️ 权限确认")
    assert "allow_once" not in updates[-1]
    assert "sandbox.bypass + 跳过沙箱" in updates[-1]
    assert session.pending_permission is not None


def test_cancelled_result_returns_clear_status_message():
    processor, event, session, executor_module, input_module = make_processor()
    result = executor_module.ExecutionResult(
        ok=False,
        error_type="cancelled",
        stop_reason="cancelled",
        final_text="",
    )

    send_plan = asyncio.run(processor.build_final_result_plan(result, event, session))

    assert extract_plain_text(send_plan) == "🛑 本轮任务已取消"


def test_refusal_result_uses_existing_output_pipeline_for_final_text():
    processor, event, session, executor_module, input_module = make_processor()
    calls = []

    async def fake_parse_output_plan(output, current_event, current_session=None):
        calls.append((output, current_event, current_session))
        return [
            [sys.modules["astrbot.api.message_components"].Plain(f"PIPE::{output}")]
        ]

    processor.parse_output_plan = fake_parse_output_plan
    result = executor_module.ExecutionResult(
        ok=False,
        error_type="refusal",
        stop_reason="refusal",
        final_text="不能帮你执行这个请求",
    )

    send_plan = asyncio.run(processor.build_final_result_plan(result, event, session))

    assert calls == [("不能帮你执行这个请求", event, session)]
    assert extract_plain_text(send_plan) == "PIPE::不能帮你执行这个请求"


def test_normal_completion_hands_final_text_to_existing_output_pipeline():
    processor, event, session, executor_module, input_module = make_processor()
    calls = []

    async def fake_parse_output_plan(output, current_event, current_session=None):
        calls.append((output, current_event, current_session))
        return [
            [sys.modules["astrbot.api.message_components"].Plain(f"PIPE::{output}")]
        ]

    processor.parse_output_plan = fake_parse_output_plan
    result = executor_module.ExecutionResult(
        ok=True,
        stop_reason="end_turn",
        final_text="最终答案",
    )

    send_plan = asyncio.run(processor.build_final_result_plan(result, event, session))

    assert calls == [("最终答案", event, session)]
    assert extract_plain_text(send_plan) == "PIPE::最终答案"


def test_parse_output_plan_accepts_execution_result_and_routes_to_final_result_helper():
    processor, event, session, executor_module, input_module = make_processor()
    result = executor_module.ExecutionResult(
        ok=True,
        stop_reason="end_turn",
        final_text="最终答案",
    )
    sentinel = [[sys.modules["astrbot.api.message_components"].Plain("SENTINEL")]]
    calls = []

    async def fake_build_final_result_plan(
        exec_result, current_event, current_session=None
    ):
        calls.append((exec_result, current_event, current_session))
        return sentinel

    processor.build_final_result_plan = fake_build_final_result_plan

    send_plan = asyncio.run(processor.parse_output_plan(result, event, session))

    assert calls == [(result, event, session)]
    assert send_plan == sentinel


def test_parse_output_plan_executes_embedded_acp_event_folding_for_runtime_path():
    processor, event, session, executor_module, input_module = make_processor()
    result = executor_module.ExecutionResult(
        ok=True,
        stop_reason="end_turn",
        final_text="最终答案",
        payload={
            "events": [
                {"type": "run_started"},
                {
                    "type": "permission_requested",
                    "tool_name": "write_file",
                    "tool_kind": "edit",
                    "arguments": {"path": "core/output.py"},
                    "options": [{"optionId": "allow_once", "label": "允许一次"}],
                },
            ]
        },
    )

    send_plan = asyncio.run(processor.parse_output_plan(result, event, session))

    assert session.prompt_running is False
    assert session.pending_permission is None
    assert (
        extract_plain_text(send_plan)
        == "🚀 开始执行任务\n⚠️ 权限确认: write_file | 类型: edit | 目标: core/output.py | 选项: 1.允许一次"
    )


def test_reply_media_becomes_structured_content_blocks_instead_of_text_only_paths():
    processor, event, session, executor_module, input_module = make_processor()
    components = sys.modules["astrbot.api.message_components"]
    session.session_capabilities = {"imageInput": True}

    class MessageObj:
        def __init__(self, message):
            self.message = message

    reply = components.Reply(
        chain=[
            components.Plain("请参考"),
            components.Image(
                url="https://example.com/reply.png", mime_type="image/png"
            ),
            components.File(name="doc.txt"),
        ]
    )
    event.message_obj = MessageObj([reply])

    processor = input_module.InputProcessor()

    async def fake_download(component, save_dir):
        if isinstance(component, components.Image):
            return "/tmp/reply.png"
        return "/tmp/doc.txt"

    processor._download_resource = fake_download
    payload = asyncio.run(processor.process_input_message(event, session, "处理一下"))

    assert payload.content_blocks[0] == {
        "type": "text",
        "text": "[引用:请参考 /tmp/reply.png  /tmp/doc.txt]",
    }
    assert payload.content_blocks[1]["type"] == "image"
    assert payload.content_blocks[1]["uri"] == "/tmp/reply.png"
    assert payload.content_blocks[2]["type"] == "resource"
    assert payload.content_blocks[2]["uri"] == "/tmp/doc.txt"


def test_image_input_downgrades_to_resource_when_session_lacks_image_capability():
    processor, event, session, executor_module, input_module = make_processor()
    components = sys.modules["astrbot.api.message_components"]
    session.session_capabilities = {"imageInput": False}

    block = input_module.InputProcessor()._make_media_block(
        components.Image(url="https://example.com/a.png", mime_type="image/png"),
        "/tmp/a.png",
        session,
    )

    assert block == {"type": "text", "text": "[图片: /tmp/a.png]"}


def test_image_input_without_declared_capability_also_downgrades_to_text_description():
    processor, event, session, executor_module, input_module = make_processor()
    components = sys.modules["astrbot.api.message_components"]
    session.session_capabilities = {}

    block = input_module.InputProcessor()._make_media_block(
        components.Image(url="https://example.com/b.png", mime_type="image/png"),
        "/tmp/b.png",
        session,
    )

    assert block == {"type": "text", "text": "[图片: /tmp/b.png]"}
