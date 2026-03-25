"""
会话管理模块
"""

import copy
import os
import time
from typing import Any, Dict, Optional

from astrbot.api import logger


class OpenCodeSession:
    """OpenCode 会话对象"""

    def __init__(
        self,
        work_dir: str,
        env: dict,
        backend_kind: Optional[str] = None,
        default_agent: Optional[str] = None,
        default_mode: Optional[str] = None,
        default_config_options: Optional[dict] = None,
    ):
        self.work_dir = work_dir
        self.env = env
        self.created_at = time.time()

        self.backend_kind = backend_kind
        self.default_agent = default_agent
        self.default_mode = default_mode
        self.default_config_options = copy.deepcopy(default_config_options or {})

        self.reset_live_session()

    @property
    def opencode_session_id(self) -> Optional[str]:
        return self.backend_session_id

    @opencode_session_id.setter
    def opencode_session_id(self, session_id: Optional[str]):
        self.backend_session_id = session_id

    def set_backend_session_id(self, session_id: str):
        """设置后端 session ID"""
        self.backend_session_id = session_id

    def clear_backend_session_id(self):
        """清除后端 session ID"""
        self.backend_session_id = None

    def bind_backend_session(self, session_id: str):
        """绑定历史会话，并清理旧的 live 状态"""
        self.reset_live_session()
        self.backend_session_id = session_id

    def reset_live_session(self):
        """清空当前 live 会话状态，但保留默认偏好和工作目录"""
        self.backend_session_id: Optional[str] = None
        self.protocol_version: Optional[Any] = None
        self.agent_name: Optional[str] = None
        self.agent_title: Optional[str] = None
        self.available_agents: list[dict] = []
        self.current_mode_id: Optional[str] = None
        self.config_options: list[dict] = []
        self.current_config_values: dict = {}
        self.available_modes: list[dict] = []
        self.available_commands: list[dict] = []
        self.session_capabilities: dict = {}
        self.pending_permission: Optional[dict] = None
        self.prompt_running = False

    def set_pending_permission(self, permission: Optional[dict]):
        """记录当前等待用户确认的权限请求。"""
        self.pending_permission = copy.deepcopy(permission) if permission else None

    def clear_pending_permission(self):
        """清空当前权限等待状态。"""
        self.pending_permission = None

    def set_opencode_session_id(self, session_id: str):
        """兼容旧调用路径，内部统一写入后端 session ID"""
        self.set_backend_session_id(session_id)

    def clear_opencode_session_id(self):
        """兼容旧调用路径，内部统一清除后端 session ID"""
        self.clear_backend_session_id()


class SessionManager:
    """会话管理器"""

    def __init__(self, config: dict, base_data_dir: str):
        self.config = config
        self.base_data_dir = base_data_dir
        self.sessions: Dict[str, OpenCodeSession] = {}
        self.logger = logger
        self._record_workdir_callback = None

    def set_record_workdir_callback(self, callback):
        """设置记录工作目录的回调函数"""
        self._record_workdir_callback = callback

    def get_session(self, sender_id: str) -> Optional[OpenCodeSession]:
        """获取已有会话"""
        return self.sessions.get(sender_id)

    def delete_session(self, sender_id: str) -> bool:
        """删除会话"""
        if sender_id in self.sessions:
            del self.sessions[sender_id]
            return True
        return False

    def get_or_create_session(
        self, sender_id: str, custom_work_dir: Optional[str] = None
    ) -> OpenCodeSession:
        """获取或创建会话"""
        session = self.sessions.get(sender_id)
        if session:
            if custom_work_dir:
                resolved_work_dir = self._prepare_work_dir(custom_work_dir)
                if resolved_work_dir != session.work_dir:
                    session.work_dir = resolved_work_dir
                    session.env = self._build_env(sender_id)
                    self._record_workdir(resolved_work_dir, sender_id)
            return session

        work_dir = self._resolve_work_dir(custom_work_dir)
        session = self._create_session(work_dir)
        self.sessions[sender_id] = session
        self._record_workdir(work_dir, sender_id)
        self.logger.info(f"Session created for {sender_id} at {work_dir}")
        return session

    def reset_session(
        self, sender_id: str, work_dir: Optional[str] = None
    ) -> OpenCodeSession:
        """重置 live 会话状态，保留默认偏好；可选更新工作目录"""
        session = self.get_or_create_session(sender_id, work_dir)
        if work_dir:
            session.work_dir = self._prepare_work_dir(work_dir)
            self._record_workdir(session.work_dir, sender_id)
        session.env = self._build_env(sender_id)
        session.reset_live_session()
        return session

    def get_all_workdirs(self) -> list:
        """获取所有活跃会话的工作目录"""
        return [s.work_dir for s in self.sessions.values()]

    def _get_basic_config(self) -> dict:
        return self.config.get("basic_config", {})

    def _get_default_work_dir(self) -> str:
        basic_cfg = self._get_basic_config()
        default_wd = basic_cfg.get("work_dir", "").strip()
        if default_wd:
            return default_wd
        return os.path.join(self.base_data_dir, "workspace")

    def _resolve_work_dir(self, custom_work_dir: Optional[str]) -> str:
        return self._prepare_work_dir(custom_work_dir or self._get_default_work_dir())

    def _prepare_work_dir(self, work_dir: str) -> str:
        if not os.path.exists(work_dir):
            try:
                os.makedirs(work_dir, exist_ok=True)
            except Exception as e:
                self.logger.warning(
                    f"Failed to create work dir {work_dir}: {e}, fallback to cwd"
                )
                fallback = os.getcwd()
                self.logger.warning(f"Fallback to cwd: {fallback}")
                return fallback
        return work_dir

    def _build_env(self, sender_id: str) -> dict:
        env = os.environ.copy()
        basic_cfg = self._get_basic_config()
        proxy_url = basic_cfg.get("proxy_url", "").strip()
        if proxy_url:
            env["http_proxy"] = proxy_url
            env["https_proxy"] = proxy_url
            env["HTTP_PROXY"] = proxy_url
            env["HTTPS_PROXY"] = proxy_url
            self.logger.info(f"Proxy configured for session {sender_id}: {proxy_url}")
        return env

    def _create_session(self, work_dir: str) -> OpenCodeSession:
        basic_cfg = self._get_basic_config()
        return OpenCodeSession(
            work_dir=work_dir,
            env=self._build_env("new-session"),
            backend_kind=basic_cfg.get("backend_type"),
            default_agent=basic_cfg.get("default_agent"),
            default_mode=basic_cfg.get("default_mode"),
            default_config_options=basic_cfg.get("default_config_options") or {},
        )

    def _record_workdir(self, work_dir: str, sender_id: str):
        if self._record_workdir_callback:
            self._record_workdir_callback(work_dir, sender_id)
