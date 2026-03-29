import asyncio
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

    for dependency in ("acp_models", "acp_transport_stdio"):
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


class FailingReceiveTransport:
    def __init__(self, error):
        self.error = error
        self.started = False
        self.closed = False
        self.sent_messages = []

    async def start(self):
        self.started = True

    async def send(self, payload):
        self.sent_messages.append(payload)

    async def receive(self):
        raise self.error

    async def aclose(self):
        self.closed = True


class FailingSendTransport:
    def __init__(self, error):
        self.error = error
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def send(self, payload):
        raise self.error

    async def receive(self):
        await asyncio.sleep(60)

    async def aclose(self):
        self.closed = True


class RecordingInitializeTransport:
    def __init__(self, response=None):
        self.started = False
        self.closed = False
        self.sent_messages = []
        self._responses = asyncio.Queue()
        self._response = response or {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"protocolVersion": 1, "agentCapabilities": {}},
        }

    async def start(self):
        self.started = True

    async def send(self, payload):
        self.sent_messages.append(payload)
        await self._responses.put(dict(self._response))

    async def receive(self):
        return await self._responses.get()

    async def aclose(self):
        self.closed = True


def test_request_fails_pending_future_when_reader_transport_breaks():
    acp_client_module = load_acp_module("acp_client")
    acp_models_module = load_acp_module("acp_models")

    async def scenario():
        transport_error = acp_models_module.ACPTransportError(
            "Received invalid JSON-RPC payload from ACP."
        )
        client = acp_client_module.ACPClient(FailingReceiveTransport(transport_error))
        try:
            await asyncio.wait_for(client.request("initialize", {}), timeout=0.2)
        except acp_models_module.ACPTransportError as exc:
            assert str(exc) == "Received invalid JSON-RPC payload from ACP."
            return
        raise AssertionError("expected ACPTransportError to be raised")

    asyncio.run(scenario())


def test_request_cleans_pending_future_when_send_fails_immediately():
    acp_client_module = load_acp_module("acp_client")
    acp_models_module = load_acp_module("acp_models")

    async def scenario():
        transport_error = acp_models_module.ACPTransportError(
            "ACP stdin closed while sending message."
        )
        client = acp_client_module.ACPClient(FailingSendTransport(transport_error))
        try:
            await client.request("initialize", {})
        except acp_models_module.ACPTransportError as exc:
            assert str(exc) == "ACP stdin closed while sending message."
            assert client._pending == {}
            return
        raise AssertionError("expected ACPTransportError to be raised")

    asyncio.run(scenario())


def test_initialize_sends_acp_v1_request_contract():
    acp_client_module = load_acp_module("acp_client")

    async def scenario():
        transport = RecordingInitializeTransport()
        client = acp_client_module.ACPClient(transport)

        response = await client.initialize(
            client_capabilities={"terminal": True},
            client_info={
                "name": "astrbot_plugin_acp",
                "title": "ACP Client",
                "version": "1.3.1",
            },
        )

        assert response["protocolVersion"] == 1
        request = transport.sent_messages[0]
        assert request["method"] == "initialize"
        assert request["params"] == {
            "protocolVersion": 1,
            "clientCapabilities": {"terminal": True},
            "clientInfo": {
                "name": "astrbot_plugin_acp",
                "title": "ACP Client",
                "version": "1.3.1",
            },
        }
        assert "capabilities" not in request["params"]

        await client.aclose()

    asyncio.run(scenario())
