"""Backend-specific ACP adapters."""

from typing import Any, Optional

from .acp_models import (
    ACPAgentInfo,
    ACPCommandInfo,
    ACPConfigOption,
    ACPModeView,
    ACPPermissionOption,
    ACPPermissionRequest,
    ACPSessionState,
)


class OpenCodeACPAdapter:
    """Maps OpenCode ACP payloads into plugin-internal models."""

    UNSUPPORTED_COMMANDS = {"/undo", "/redo"}

    def extract_mode_view(
        self,
        config_options: Optional[list[dict[str, Any]]] = None,
        modes: Optional[list[dict[str, Any]] | dict[str, Any]] = None,
        current_config_values: Optional[dict[str, Any]] = None,
        current_mode_id: Optional[str] = None,
    ) -> ACPModeView:
        current_config_values = dict(current_config_values or {})
        config_options = list(config_options or [])
        modes_payload = dict(modes) if isinstance(modes, dict) else None
        normalized_raw_modes: list[dict[str, Any]] = []
        if modes_payload is not None:
            normalized_raw_modes = [
                item
                for item in list(modes_payload.get("availableModes") or [])
                if isinstance(item, dict)
            ]
            current_mode_id = (
                self._as_optional_str(modes_payload.get("currentModeId"))
                or current_mode_id
            )
        else:
            normalized_raw_modes = [
                item for item in list(modes or []) if isinstance(item, dict)
            ]

        mode_options = [
            self._normalize_config_option(item)
            for item in config_options
            if str(item.get("category", "")).strip() == "mode"
        ]
        if mode_options:
            resolved_mode = self._resolve_current_mode_from_options(
                mode_options=mode_options,
                current_config_values=current_config_values,
                fallback_mode_id=current_mode_id,
            )
            return ACPModeView(
                source="configOptions",
                current_mode_id=resolved_mode,
                options=mode_options,
                raw_modes=normalized_raw_modes,
            )

        normalized_modes = [
            self._normalize_mode_as_option(item) for item in normalized_raw_modes
        ]
        return ACPModeView(
            source="modes" if normalized_modes else "none",
            current_mode_id=current_mode_id,
            options=normalized_modes,
            raw_modes=normalized_raw_modes,
        )

    def normalize_session_state(
        self, session_payload: Optional[dict[str, Any]] = None
    ) -> ACPSessionState:
        session_payload = dict(session_payload or {})
        config_options_payload = list(session_payload.get("configOptions") or [])
        current_config_values = dict(session_payload.get("currentConfigValues") or {})
        modes_payload = session_payload.get("modes")

        current_mode_id = self._as_optional_str(session_payload.get("mode"))
        if isinstance(modes_payload, dict):
            current_mode_id = (
                self._as_optional_str(modes_payload.get("currentModeId"))
                or current_mode_id
            )

        return ACPSessionState(
            session_id=self._as_optional_str(
                session_payload.get("sessionId") or session_payload.get("id")
            ),
            work_dir=self._as_optional_str(
                session_payload.get("cwd") or session_payload.get("workdir")
            ),
            agent=self.normalize_agent(session_payload.get("agent")),
            mode=self.extract_mode_view(
                config_options=config_options_payload,
                modes=modes_payload,
                current_config_values=current_config_values,
                current_mode_id=current_mode_id,
            ),
            config_options=[
                self._normalize_config_option(item) for item in config_options_payload
            ],
            current_config_values=current_config_values,
            commands=self.normalize_commands(
                session_payload.get("availableCommands") or []
            ),
            capabilities=dict(
                session_payload.get("capabilities")
                or session_payload.get("agentCapabilities")
                or {}
            ),
            raw=session_payload,
        )

    def normalize_agent(
        self, agent_payload: Optional[dict[str, Any] | str]
    ) -> Optional[ACPAgentInfo]:
        if isinstance(agent_payload, str):
            name = agent_payload.strip()
            if not name:
                return None
            return ACPAgentInfo(name=name, raw={"name": name})

        if not isinstance(agent_payload, dict):
            return None

        name = self._as_optional_str(agent_payload.get("name"))
        if not name:
            return None

        return ACPAgentInfo(
            name=name,
            title=self._as_str(agent_payload.get("title")),
            raw=dict(agent_payload),
        )

    def normalize_permission_request(
        self, payload: Optional[dict[str, Any]] = None
    ) -> ACPPermissionRequest:
        payload = dict(payload or {})
        tool_payload = payload.get("tool") or {}
        if not isinstance(tool_payload, dict):
            tool_payload = {}

        options = []
        for item in payload.get("options") or []:
            if not isinstance(item, dict):
                continue
            options.append(
                ACPPermissionOption(
                    option_id=self._as_str(item.get("id")),
                    label=self._as_str(item.get("name") or item.get("label")),
                    raw=dict(item),
                )
            )

        arguments = payload.get("arguments") or tool_payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        return ACPPermissionRequest(
            request_id=self._as_str(
                payload.get("requestId")
                or payload.get("request_id")
                or payload.get("id")
            ),
            session_id=self._as_optional_str(payload.get("sessionId")),
            tool_name=self._as_str(
                tool_payload.get("title") or tool_payload.get("name")
            )
            or "未知工具",
            tool_kind=self._as_str(tool_payload.get("kind")),
            arguments=arguments,
            options=options,
            raw=payload,
        )

    def normalize_commands(
        self, commands_payload: Optional[list[dict[str, Any]]] = None
    ) -> list[ACPCommandInfo]:
        commands: list[ACPCommandInfo] = []
        seen = set()

        for item in commands_payload or []:
            if not isinstance(item, dict):
                continue
            name = self._as_optional_str(item.get("name"))
            if not name or name in seen:
                continue
            seen.add(name)
            commands.append(
                ACPCommandInfo(
                    name=name,
                    title=self._as_str(item.get("title") or item.get("name")),
                    supported=name not in self.UNSUPPORTED_COMMANDS,
                    description=self._as_str(item.get("description")),
                    raw=dict(item),
                )
            )

        for name in sorted(self.UNSUPPORTED_COMMANDS):
            if name in seen:
                continue
            commands.append(
                ACPCommandInfo(
                    name=name,
                    title=name,
                    supported=False,
                    description="ACP backend currently does not support this command.",
                    raw={"name": name, "unsupported": True},
                )
            )

        return commands

    def _normalize_config_option(self, payload: dict[str, Any]) -> ACPConfigOption:
        category = self._as_str(payload.get("category"))
        return ACPConfigOption(
            option_id=self._as_str(payload.get("id")),
            label=self._as_str(payload.get("name") or payload.get("label")),
            category=category,
            semantic_kind=self._semantic_kind_from_category(category),
            value=payload.get("value"),
            description=self._as_str(payload.get("description")),
            raw=dict(payload),
        )

    def _normalize_mode_as_option(self, payload: dict[str, Any]) -> ACPConfigOption:
        return ACPConfigOption(
            option_id=self._as_str(payload.get("id")),
            label=self._as_str(payload.get("name") or payload.get("title")),
            category="mode",
            semantic_kind="mode",
            value=payload.get("id"),
            description=self._as_str(payload.get("description")),
            raw=dict(payload),
        )

    def _semantic_kind_from_category(self, category: str) -> str:
        normalized = category.strip().lower()
        if normalized == "mode":
            return "mode"
        if normalized == "model":
            return "model"
        return "other"

    def _resolve_current_mode_from_options(
        self,
        mode_options: list[ACPConfigOption],
        current_config_values: dict[str, Any],
        fallback_mode_id: Optional[str],
    ) -> Optional[str]:
        for option in mode_options:
            if option.option_id in current_config_values:
                value = current_config_values[option.option_id]
                return None if value is None else str(value)
        return fallback_mode_id

    def _as_str(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    def _as_optional_str(self, value: Any) -> Optional[str]:
        text = self._as_str(value).strip()
        return text or None
