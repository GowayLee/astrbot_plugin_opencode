"""Shared ACP data models used by transport, client, and adapters."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


NotificationHandler = Callable[[str, dict[str, Any]], Any]


@dataclass(slots=True)
class ACPError(Exception):
    message: str
    code: Optional[int] = None
    data: Any = None

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class ACPTransportError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class ACPStartupError(ACPTransportError):
    command: str = ""
    exit_code: Optional[int] = None
    stderr_text: str = ""


@dataclass(slots=True)
class ACPTimeoutError(ACPTransportError):
    timeout_seconds: float = 0.0


@dataclass(slots=True)
class ACPMessage:
    payload: dict[str, Any]


@dataclass(slots=True)
class ACPConfigOption:
    option_id: str
    label: str
    category: str
    semantic_kind: str = "other"
    value: Any = None
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ACPModeView:
    source: str
    current_mode_id: Optional[str]
    options: list[ACPConfigOption] = field(default_factory=list)
    raw_modes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ACPAgentInfo:
    name: str
    title: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ACPCommandInfo:
    name: str
    title: str = ""
    supported: bool = True
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ACPPermissionOption:
    option_id: str
    label: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ACPPermissionRequest:
    request_id: str
    session_id: Optional[str]
    tool_name: str
    tool_kind: str
    arguments: dict[str, Any] = field(default_factory=dict)
    options: list[ACPPermissionOption] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ACPNormalizedEvent:
    event_type: str
    session_id: Optional[str] = None
    title: str = ""
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ACPSessionState:
    session_id: Optional[str]
    work_dir: Optional[str]
    agent: Optional[ACPAgentInfo]
    mode: ACPModeView
    config_options: list[ACPConfigOption] = field(default_factory=list)
    current_config_values: dict[str, Any] = field(default_factory=dict)
    commands: list[ACPCommandInfo] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
