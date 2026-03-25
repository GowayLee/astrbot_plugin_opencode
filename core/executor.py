"""ACP backend dispatcher for command execution."""

import asyncio
import contextlib
import os
import shutil
from dataclasses import dataclass, field
from typing import Any, Optional

from astrbot.api import logger

from .acp_adapter import OpenCodeACPAdapter
from .acp_client import ACPClient
from .acp_models import ACPError, ACPStartupError, ACPTimeoutError, ACPTransportError
from .acp_transport_stdio import ACPStdioTransport
from .session import OpenCodeSession


@dataclass(slots=True)
class ExecutionResult:
    ok: bool
    message: str = ""
    error_type: Optional[str] = None
    final_text: str = ""
    stop_reason: Optional[str] = None
    session_id: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    recovered_session: bool = False
    session_recovery_failed: bool = False


@dataclass(slots=True)
class SessionEnsureResult:
    ok: bool
    error: Optional[ExecutionResult] = None
    recovered_session: bool = False
    session_recovery_failed: bool = False


class CommandExecutor:
    """ACP-only executor that owns backend lifecycle and session dispatch."""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logger
        self.adapter = OpenCodeACPAdapter()
        self._client: Optional[ACPClient] = None
        self._runtime_update_queues: dict[int, asyncio.Queue] = {}
        self._active_runtime_sessions: dict[int, OpenCodeSession] = {}

    def _get_basic_config(self) -> dict:
        return self.config.get("basic_config", {})

    def get_acp_launch_config(self) -> dict:
        basic_cfg = self._get_basic_config()
        acp_args = basic_cfg.get("acp_args", [])
        if not isinstance(acp_args, list):
            acp_args = []

        client_capabilities = basic_cfg.get("acp_client_capabilities", {})
        if not isinstance(client_capabilities, dict):
            client_capabilities = {}

        startup_timeout = basic_cfg.get("acp_startup_timeout", 0)
        try:
            startup_timeout = int(startup_timeout)
        except (TypeError, ValueError):
            startup_timeout = 0

        return {
            "backend_type": str(basic_cfg.get("backend_type", "")).strip(),
            "acp_command": str(basic_cfg.get("acp_command", "")).strip(),
            "acp_args": [str(arg) for arg in acp_args],
            "acp_startup_timeout": startup_timeout,
            "acp_client_capabilities": dict(client_capabilities),
        }

    def _resolve_command_path(self) -> Optional[str]:
        command = self.get_acp_launch_config()["acp_command"]
        if not command:
            return None

        resolved_path = shutil.which(command)
        if resolved_path:
            return resolved_path

        return command

    async def close(self):
        client = self._client
        self._client = None
        if client and hasattr(client, "aclose"):
            await client.aclose()

    def get_protocol_capabilities(self) -> dict[str, Any]:
        client = self._client
        if client is None:
            return {}
        return dict(getattr(client, "protocol_capabilities", {}) or {})

    async def health_check(self) -> tuple[bool, str]:
        launch_cfg = self.get_acp_launch_config()
        backend_type = launch_cfg["backend_type"]
        if not backend_type:
            return False, "backend_type_missing"
        if backend_type != "acp_opencode":
            return False, f"unsupported_backend_type({backend_type})"

        command = launch_cfg["acp_command"]
        if not command:
            return False, "acp_command_missing"

        timeout = launch_cfg["acp_startup_timeout"]
        if timeout <= 0:
            return False, "acp_startup_timeout_invalid"

        try:
            await self._probe_backend_startup()
        except (ACPStartupError, ACPTimeoutError, ACPTransportError, ACPError) as exc:
            return False, self._format_initialize_error(exc)

        return (
            True,
            f"{backend_type}(command={command}, args={len(launch_cfg['acp_args'])}, timeout={timeout}, capabilities={len(launch_cfg['acp_client_capabilities'])})",
        )

    async def initialize_if_needed(
        self, session: Optional[OpenCodeSession] = None
    ) -> ExecutionResult:
        client = self._get_or_create_client(session)
        if client.initialized:
            if session and getattr(client, "protocol_info", None):
                session.protocol_version = client.protocol_info.get("protocolVersion")
            return ExecutionResult(
                ok=True, payload=dict(getattr(client, "protocol_info", {}))
            )

        try:
            response = await client.initialize(
                client_capabilities=self.get_acp_launch_config()[
                    "acp_client_capabilities"
                ],
                client_info={"name": "astrbot_plugin_opencode"},
            )
        except (ACPStartupError, ACPTimeoutError, ACPTransportError, ACPError) as exc:
            await self.close()
            return ExecutionResult(
                ok=False,
                error_type="acp_initialize_failed",
                message=self._format_initialize_error(exc),
            )

        if session:
            session.protocol_version = response.get("protocolVersion")
        return ExecutionResult(ok=True, payload=response)

    async def ensure_session(self, session: OpenCodeSession) -> ExecutionResult:
        init_result = await self.initialize_if_needed(session)
        if not init_result.ok:
            return init_result

        ensured = await self._ensure_session_ready(session)
        if ensured.error:
            return ensured.error

        return ExecutionResult(
            ok=True,
            session_id=session.backend_session_id,
            recovered_session=ensured.recovered_session,
            session_recovery_failed=ensured.session_recovery_failed,
        )

    async def load_session(self, session: OpenCodeSession) -> ExecutionResult:
        init_result = await self.initialize_if_needed(session)
        if not init_result.ok:
            return init_result

        ensured = await self._ensure_session_ready(
            session, allow_recreate_after_load_failure=False
        )
        if ensured.error:
            return ensured.error

        return ExecutionResult(
            ok=True,
            session_id=session.backend_session_id,
            recovered_session=ensured.recovered_session,
            session_recovery_failed=ensured.session_recovery_failed,
        )

    async def prompt(
        self,
        session: OpenCodeSession,
        prompt_payload: Optional[dict[str, Any]] = None,
    ) -> ExecutionResult:
        init_result = await self.initialize_if_needed(session)
        if not init_result.ok:
            return init_result

        ensured = await self._ensure_session_ready(session)
        if ensured.error:
            return ensured.error

        payload = self._coerce_prompt_payload(prompt_payload)
        payload.setdefault("sessionId", session.backend_session_id)

        try:
            response = await self._get_or_create_client(session).prompt_session(payload)
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_prompt_failed",
                message=f"ACP prompt failed: {exc}",
                session_id=session.backend_session_id,
            )

        self._apply_session_state(session, response)
        stop_reason = self._extract_stop_reason(response)
        final_text = self._extract_output_text(response)
        session.prompt_running = False

        if stop_reason == "cancelled":
            return ExecutionResult(
                ok=False,
                error_type="cancelled",
                message="🛑 本轮任务已取消",
                final_text=final_text,
                stop_reason=stop_reason,
                session_id=session.backend_session_id,
                payload=response,
                recovered_session=ensured.recovered_session,
                session_recovery_failed=ensured.session_recovery_failed,
            )

        return ExecutionResult(
            ok=True,
            final_text=final_text,
            stop_reason=stop_reason,
            session_id=session.backend_session_id,
            payload=response,
            recovered_session=ensured.recovered_session,
            session_recovery_failed=ensured.session_recovery_failed,
        )

    async def run_prompt(
        self,
        prompt_payload: Optional[dict[str, Any]],
        session: OpenCodeSession,
    ) -> ExecutionResult:
        return await self.prompt(session, self._coerce_prompt_payload(prompt_payload))

    async def stream_prompt(self, prompt_payload: Any, session: OpenCodeSession):
        async for item in self._stream_execution(
            session,
            lambda: self.run_prompt(prompt_payload, session),
        ):
            yield item

    async def stream_permission_response(
        self, session: OpenCodeSession, request_id: str, option_id: str
    ):
        async for item in self._stream_execution(
            session,
            lambda: self.respond_permission(session, request_id, option_id),
        ):
            yield item

    async def run_opencode(
        self, message: Any, session: OpenCodeSession
    ) -> ExecutionResult:
        return await self.run_prompt(self._coerce_prompt_payload(message), session)

    async def cancel(self, session: OpenCodeSession) -> ExecutionResult:
        init_result = await self.initialize_if_needed(session)
        if not init_result.ok:
            return init_result

        payload = {}
        if session.backend_session_id:
            payload["sessionId"] = session.backend_session_id

        try:
            response = await self._get_or_create_client(session).cancel_session(payload)
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_cancel_failed",
                message=f"ACP cancel failed: {exc}",
                session_id=session.backend_session_id,
            )

        session.prompt_running = False
        session.pending_permission = None
        return ExecutionResult(
            ok=True,
            stop_reason=self._extract_stop_reason(response),
            session_id=session.backend_session_id,
            payload=response,
        )

    async def respond_permission(
        self, session: OpenCodeSession, request_id: str, option_id: str
    ) -> ExecutionResult:
        init_result = await self.initialize_if_needed(session)
        if not init_result.ok:
            return init_result

        payload = {
            "requestId": request_id,
            "optionId": option_id,
        }
        if session.backend_session_id:
            payload["sessionId"] = session.backend_session_id

        try:
            response = await self._get_or_create_client(session).respond_permission(
                payload
            )
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_permission_response_failed",
                message=f"ACP permission response failed: {exc}",
                session_id=session.backend_session_id,
            )

        session.pending_permission = None
        self._apply_session_state(session, response)
        return ExecutionResult(
            ok=True,
            final_text=self._extract_output_text(response),
            stop_reason=self._extract_stop_reason(response),
            session_id=session.backend_session_id,
            payload=response,
        )

    async def list_sessions(self, limit: int = 10) -> ExecutionResult:
        init_result = await self.initialize_if_needed(None)
        if not init_result.ok:
            return init_result

        try:
            response = await self._get_or_create_client(None).list_sessions(
                {"limit": limit}
            )
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_list_sessions_failed",
                message=f"ACP session list failed: {exc}",
            )

        items = response.get("sessions") or response.get("items") or []
        if not isinstance(items, list):
            items = []
        return ExecutionResult(ok=True, items=list(items), payload=response)

    async def set_config_option(
        self, session: OpenCodeSession, option_id: str, value: Any
    ) -> ExecutionResult:
        ensured = await self.ensure_session(session)
        if not ensured.ok:
            return ensured

        payload = {
            "sessionId": session.backend_session_id,
            "optionId": option_id,
            "value": value,
        }
        try:
            response = await self._get_or_create_client(
                session
            ).set_session_config_option(payload)
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_set_config_option_failed",
                message=f"ACP set config option failed: {exc}",
                session_id=session.backend_session_id,
            )

        self._apply_session_state(session, response)
        return ExecutionResult(
            ok=True, session_id=session.backend_session_id, payload=response
        )

    async def set_mode(self, session: OpenCodeSession, mode_id: str) -> ExecutionResult:
        ensured = await self.ensure_session(session)
        if not ensured.ok:
            return ensured

        payload = {"sessionId": session.backend_session_id, "modeId": mode_id}
        try:
            response = await self._get_or_create_client(session).set_session_mode(
                payload
            )
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_set_mode_failed",
                message=f"ACP set mode failed: {exc}",
                session_id=session.backend_session_id,
            )

        self._apply_session_state(session, response)
        return ExecutionResult(
            ok=True, session_id=session.backend_session_id, payload=response
        )

    def _get_or_create_client(
        self, session: Optional[OpenCodeSession] = None
    ) -> ACPClient:
        if self._client is None:
            self._client = self._build_client(session)
        self._ensure_notification_handler(self._client)
        return self._client

    def _build_client(self, session: Optional[OpenCodeSession]) -> ACPClient:
        launch_cfg = self.get_acp_launch_config()
        transport = ACPStdioTransport(
            command=self._resolve_command_path() or launch_cfg["acp_command"],
            args=launch_cfg["acp_args"],
            env=dict(session.env) if session else dict(os.environ),
            startup_timeout=launch_cfg["acp_startup_timeout"],
        )
        client = ACPClient(transport)
        self._ensure_notification_handler(client)
        return client

    def _ensure_notification_handler(self, client: ACPClient) -> None:
        if getattr(client, "_astrbot_runtime_updates_registered", False):
            return
        client.add_notification_handler(self._handle_client_notification)
        setattr(client, "_astrbot_runtime_updates_registered", True)

    async def _probe_backend_startup(self) -> None:
        launch_cfg = self.get_acp_launch_config()
        transport = ACPStdioTransport(
            command=self._resolve_command_path() or launch_cfg["acp_command"],
            args=launch_cfg["acp_args"],
            env=dict(os.environ),
            startup_timeout=launch_cfg["acp_startup_timeout"],
        )
        try:
            await transport.start()
        finally:
            await transport.aclose()

    async def _ensure_session_ready(
        self,
        session: OpenCodeSession,
        allow_recreate_after_load_failure: bool = True,
    ) -> SessionEnsureResult:
        client = self._get_or_create_client(session)
        load_supported = bool(
            getattr(client, "protocol_capabilities", {}).get("loadSession")
        )

        if session.backend_session_id:
            if load_supported:
                try:
                    response = await client.load_session(
                        {
                            "sessionId": session.backend_session_id,
                            "cwd": session.work_dir,
                        }
                    )
                except (ACPTransportError, ACPError) as exc:
                    stale_session_id = session.backend_session_id
                    session.reset_live_session()
                    self.logger.warning(
                        f"ACP session recovery failed for {stale_session_id}: {exc}"
                    )
                    if not allow_recreate_after_load_failure:
                        return SessionEnsureResult(
                            ok=False,
                            error=ExecutionResult(
                                ok=False,
                                error_type="acp_load_session_failed",
                                message=f"ACP load session failed: {exc}",
                                session_id=stale_session_id,
                            ),
                        )
                    created = await self._create_session(session)
                    created.recovered_session = False
                    created.session_recovery_failed = True
                    return SessionEnsureResult(
                        ok=created.ok,
                        error=None if created.ok else created,
                        recovered_session=False,
                        session_recovery_failed=created.ok,
                    )

                self._apply_session_state(session, response)
                return SessionEnsureResult(ok=True, recovered_session=True)

            session.reset_live_session()

        created = await self._create_session(session)
        if not created.ok:
            return SessionEnsureResult(ok=False, error=created)
        return SessionEnsureResult(ok=True)

    async def _create_session(self, session: OpenCodeSession) -> ExecutionResult:
        payload: dict[str, Any] = {"cwd": session.work_dir}
        if session.default_agent:
            payload["agent"] = session.default_agent
        if session.default_mode:
            payload["mode"] = session.default_mode
        if session.default_config_options:
            payload["config"] = dict(session.default_config_options)

        try:
            response = await self._get_or_create_client(session).new_session(payload)
        except (ACPTransportError, ACPError) as exc:
            return ExecutionResult(
                ok=False,
                error_type="acp_session_new_failed",
                message=f"ACP session creation failed: {exc}",
            )

        self._apply_session_state(session, response)
        return ExecutionResult(
            ok=True, session_id=session.backend_session_id, payload=response
        )

    def _apply_session_state(
        self, session: OpenCodeSession, payload: Optional[dict[str, Any]]
    ) -> None:
        payload = dict(payload or {})
        if not payload:
            return

        normalized = self.adapter.normalize_session_state(payload)
        if normalized.session_id:
            session.backend_session_id = normalized.session_id
        if "agent" in payload:
            session.agent_name = normalized.agent.name if normalized.agent else None
            session.agent_title = normalized.agent.title if normalized.agent else None
        if any(key in payload for key in ("availableAgents", "agents")):
            session.available_agents = self._extract_available_agents(payload)
        if any(
            key in payload
            for key in ("mode", "configOptions", "currentConfigValues", "modes")
        ):
            session.current_mode_id = normalized.mode.current_mode_id
        if "configOptions" in payload:
            session.config_options = [
                self._config_option_to_dict(item) for item in normalized.config_options
            ]
        if "currentConfigValues" in payload:
            session.current_config_values = dict(normalized.current_config_values)
        if "modes" in payload:
            session.available_modes = [dict(item) for item in normalized.mode.raw_modes]
        if "availableCommands" in payload:
            session.available_commands = [
                self._command_to_dict(item) for item in normalized.commands
            ]
        if "capabilities" in payload:
            session.session_capabilities = dict(normalized.capabilities)

    def _config_option_to_dict(self, option) -> dict[str, Any]:
        return {
            "id": option.option_id,
            "name": option.label,
            "category": option.category,
            "value": option.value,
            "description": option.description,
            **dict(option.raw),
        }

    def _command_to_dict(self, command) -> dict[str, Any]:
        return {
            "name": command.name,
            "title": command.title,
            "supported": command.supported,
            "description": command.description,
            **dict(command.raw),
        }

    def _extract_available_agents(
        self, payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        agents = payload.get("availableAgents") or payload.get("agents") or []
        if not isinstance(agents, list):
            return []

        normalized = []
        seen = set()
        for item in agents:
            if isinstance(item, str):
                name = item.strip()
                title = ""
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("id") or "").strip()
                title = str(item.get("title") or item.get("label") or "").strip()
            else:
                continue

            if not name or name in seen:
                continue
            seen.add(name)
            normalized.append({"name": name, "title": title})
        return normalized

    def _extract_stop_reason(self, payload: dict[str, Any]) -> Optional[str]:
        for key in ("stopReason", "stop_reason"):
            value = payload.get(key)
            if value is not None:
                return str(value)
        return None

    def _extract_output_text(self, payload: dict[str, Any]) -> str:
        for key in ("outputText", "finalText", "text"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value

        blocks = payload.get("contentBlocks") or payload.get("parts") or []
        if not isinstance(blocks, list):
            return ""

        texts = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
        return "\n".join(texts)

    def _coerce_prompt_payload(self, prompt_input: Any) -> dict[str, Any]:
        if hasattr(prompt_input, "to_payload") and callable(prompt_input.to_payload):
            payload = prompt_input.to_payload()
            if isinstance(payload, dict):
                return dict(payload)

        if isinstance(prompt_input, dict):
            return dict(prompt_input)

        text = "" if prompt_input is None else str(prompt_input)
        return {"contentBlocks": [{"type": "text", "text": text}]}

    async def _stream_execution(self, session: OpenCodeSession, request_factory):
        session_key = id(session)
        queue = self._runtime_update_queues.setdefault(session_key, asyncio.Queue())
        self._active_runtime_sessions[session_key] = session
        task = asyncio.create_task(request_factory())

        try:
            while True:
                queue_task = asyncio.create_task(queue.get())
                done, pending = await asyncio.wait(
                    {task, queue_task}, return_when=asyncio.FIRST_COMPLETED
                )

                if queue_task in done:
                    yield {"kind": "event", "event": queue_task.result()}
                else:
                    queue_task.cancel()

                for pending_task in pending:
                    pending_task.cancel()

                if task in done:
                    while not queue.empty():
                        yield {"kind": "event", "event": queue.get_nowait()}
                    yield {"kind": "result", "result": task.result()}
                    break
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._active_runtime_sessions.pop(session_key, None)
            self._runtime_update_queues.pop(session_key, None)

    async def _handle_client_notification(
        self, method: str, params: Optional[dict[str, Any]] = None
    ) -> None:
        event = self._normalize_runtime_event(method, params)
        if not event:
            return

        for session in self._resolve_runtime_sessions(event):
            self._apply_runtime_session_update(session, event)
            queue = self._runtime_update_queues.get(id(session))
            if queue is not None:
                queue.put_nowait(dict(event))

    def _normalize_runtime_event(
        self, method: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        payload = dict(params or {})
        if not payload and not method:
            return {}

        normalized_method = str(method or "").strip().replace(".", "/")
        event_type = str(payload.get("type") or payload.get("event_type") or "").strip()
        if not event_type:
            if (
                payload.get("permission")
                or normalized_method == "session/request_permission"
            ):
                event_type = "permission_requested"
            else:
                event_type = method.replace("/", "_").replace(".", "_")

        event = dict(payload)
        event["type"] = event_type

        permission_payload = payload.get("permission")
        if event_type == "permission_requested" and isinstance(
            permission_payload, dict
        ):
            event = self._normalize_permission_event(permission_payload, event)
            event["type"] = "permission_requested"
        elif event_type == "permission_requested":
            event = self._normalize_permission_event(payload, event)

        return event

    def _normalize_permission_event(
        self, payload: dict[str, Any], fallback: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        event = dict(fallback or {})
        event.update(dict(payload or {}))

        request_id = (
            event.get("requestId") or event.get("request_id") or event.get("id")
        )
        session_id = event.get("sessionId") or event.get("session_id")
        tool_name = event.get("tool_name") or event.get("toolName")
        tool_kind = event.get("tool_kind") or event.get("toolKind") or event.get("kind")
        arguments = event.get("arguments")
        options = event.get("options")

        if not tool_name or not request_id:
            normalized = self.adapter.normalize_permission_request(payload)
            request_id = request_id or normalized.request_id
            session_id = session_id or normalized.session_id
            tool_name = tool_name or normalized.tool_name
            tool_kind = tool_kind or normalized.tool_kind
            if not isinstance(arguments, dict):
                arguments = dict(normalized.arguments)
            if not isinstance(options, list) or not options:
                options = [
                    {"optionId": item.option_id, "label": item.label, **dict(item.raw)}
                    for item in normalized.options
                ]

        event["requestId"] = request_id
        if session_id is not None:
            event["sessionId"] = session_id
        event["tool_name"] = tool_name or "未知工具"
        event["tool_kind"] = tool_kind or ""
        event["arguments"] = dict(arguments or {})
        normalized_options = []
        for option in options or []:
            if not isinstance(option, dict):
                continue
            normalized_option = dict(option)
            if "optionId" not in normalized_option and "id" in normalized_option:
                normalized_option["optionId"] = normalized_option.get("id")
            if "label" not in normalized_option and "name" in normalized_option:
                normalized_option["label"] = normalized_option.get("name")
            normalized_options.append(normalized_option)
        event["options"] = normalized_options
        return event

    def _resolve_runtime_sessions(
        self, event: Optional[dict[str, Any]] = None
    ) -> list[OpenCodeSession]:
        session_id = None
        if isinstance(event, dict):
            session_id = event.get("sessionId") or event.get("session_id")

        if session_id is not None:
            matched = [
                session
                for session in self._active_runtime_sessions.values()
                if session.backend_session_id == str(session_id)
            ]
            if matched:
                return matched

        if len(self._active_runtime_sessions) == 1:
            return list(self._active_runtime_sessions.values())

        return []

    def _apply_runtime_session_update(
        self, session: OpenCodeSession, event: dict[str, Any]
    ) -> None:
        session_payload_keys = {
            "sessionId",
            "id",
            "agent",
            "mode",
            "configOptions",
            "currentConfigValues",
            "modes",
            "availableCommands",
            "capabilities",
        }
        if any(key in event for key in session_payload_keys):
            self._apply_session_state(session, event)

    def _format_initialize_error(self, exc: BaseException) -> str:
        launch_cfg = self.get_acp_launch_config()
        command = (
            launch_cfg["acp_command"] or self._resolve_command_path() or "<unknown>"
        )
        if isinstance(exc, ACPStartupError):
            detail = f"ACP 后端启动失败: {command}"
            if exc.exit_code is not None:
                detail += f" (exit={exc.exit_code})"
            if exc.stderr_text:
                detail += f"\n{exc.stderr_text.strip()}"
            elif exc.message:
                detail += f"\n{exc.message}"
            return detail
        if isinstance(exc, ACPTimeoutError):
            return f"ACP 后端启动失败: {command}\n{exc.message}"
        return f"ACP 后端启动失败: {command}\n{exc}"
