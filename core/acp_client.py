"""Generic ACP client core built on a JSON-RPC transport."""

import asyncio
from contextlib import suppress
from typing import Any, Optional

from .acp_models import ACPError, NotificationHandler
from .acp_transport_stdio import ACPStdioTransport


class ACPClient:
    """Generic ACP client with initialize, request tracking, and notifications."""

    def __init__(self, transport: ACPStdioTransport):
        self.transport = transport
        self._request_id = 0
        self._pending: dict[str, asyncio.Future] = {}
        self._notification_handlers: list[NotificationHandler] = []
        self._reader_task: Optional[asyncio.Task] = None
        self._reader_failure: Optional[BaseException] = None
        self._initialized = False
        self.protocol_capabilities: dict[str, Any] = {}
        self.protocol_info: dict[str, Any] = {}

    async def start(self) -> None:
        self._raise_if_reader_failed()
        await self.transport.start()
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())
        elif self._reader_task.done():
            self._raise_if_reader_failed()
            raise ACPError(message="ACP reader task stopped unexpectedly.")

    async def aclose(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        await self.transport.aclose()

    def add_notification_handler(self, handler: NotificationHandler) -> None:
        self._notification_handlers.append(handler)

    async def initialize(
        self,
        client_capabilities: Optional[dict[str, Any]] = None,
        client_info: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        params = {
            "protocolVersion": 1,
            "clientCapabilities": dict(client_capabilities or {}),
            "clientInfo": dict(client_info or {}),
        }
        response = await self.request("initialize", params)
        self.protocol_capabilities = dict(
            response.get("agentCapabilities") or response.get("capabilities") or {}
        )
        self.protocol_info = dict(response)
        self._initialized = True
        return response

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def request(
        self, method: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        await self.start()
        self._raise_if_reader_failed()

        request_id = self._next_request_id()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future

        try:
            await self.transport.send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": dict(params or {}),
                }
            )
        except Exception:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            raise

        try:
            result = await future
        finally:
            self._pending.pop(request_id, None)

        if not isinstance(result, dict):
            raise ACPError(message="ACP response payload is not an object.")
        return result

    async def notify(
        self, method: str, params: Optional[dict[str, Any]] = None
    ) -> None:
        await self.start()
        self._raise_if_reader_failed()
        await self.transport.send(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": dict(params or {}),
            }
        )

    async def new_session(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/new", payload)

    async def load_session(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/load", payload)

    async def prompt_session(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/prompt", payload)

    async def cancel_session(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/cancel", payload)

    async def list_sessions(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/list", payload)

    async def set_session_config_option(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/set_config_option", payload)

    async def set_session_mode(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/set_mode", payload)

    async def respond_permission(
        self, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        return await self.request("session/respond_permission", payload)

    def _next_request_id(self) -> str:
        self._request_id += 1
        return str(self._request_id)

    async def _read_loop(self) -> None:
        try:
            while True:
                message = await self.transport.receive()
                await self._dispatch_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._reader_failure = exc
            self._fail_pending_requests(exc)

    def _fail_pending_requests(self, exc: BaseException) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)

    def _raise_if_reader_failed(self) -> None:
        if self._reader_failure is not None:
            raise self._reader_failure

    async def _dispatch_message(self, message: dict[str, Any]) -> None:
        if "id" in message:
            request_id = str(message["id"])
            future = self._pending.get(request_id)
            if future is None or future.done():
                return

            if "error" in message:
                error = message["error"] or {}
                if isinstance(error, dict):
                    future.set_exception(
                        ACPError(
                            message=str(error.get("message") or "ACP request failed."),
                            code=error.get("code"),
                            data=error.get("data"),
                        )
                    )
                else:
                    future.set_exception(ACPError(message="ACP request failed."))
                return

            future.set_result(message.get("result") or {})
            return

        method = message.get("method")
        if not isinstance(method, str):
            return

        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {"value": params}

        for handler in list(self._notification_handlers):
            maybe_awaitable = handler(method, params)
            if asyncio.iscoroutine(maybe_awaitable):
                await maybe_awaitable
