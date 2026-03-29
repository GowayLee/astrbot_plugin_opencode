"""
AstrBot ACP Client 插件 - 让 AstrBot 通过 ACP 会话对接 OpenCode 等智能体，在聊天中完成编程与文件任务。使用此插件，意味着你已知晓相关风险。
"""

import asyncio
import copy
import os
import re
import shlex
from datetime import datetime
from typing import Any, Optional

from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api.all import *
from astrbot.core.utils.session_waiter import session_waiter, SessionController
from astrbot.api.message_components import File

# 导入核心模块
from .core.session import SessionManager
from .core.storage import StorageManager
from .core.security import SecurityChecker
from .core.input import InputProcessor
from .core.executor import CommandExecutor
from .core.output import OutputProcessor


PLUGIN_ID = "astrbot_plugin_acp"
PLUGIN_DISPLAY_NAME = "ACP Client"
PLUGIN_AUTHOR = "Hauryn Lee"
PLUGIN_DESCRIPTION = "让 AstrBot 通过 ACP 会话对接 OpenCode 等智能体，在聊天中完成编程与文件任务。使用此插件，意味着你已知晓相关风险。"
PLUGIN_VERSION = "1.3.1"
PLUGIN_REPO = "https://github.com/GowayLee/astrbot_plugin_opencode"


@register(
    PLUGIN_ID,
    PLUGIN_AUTHOR,
    PLUGIN_DESCRIPTION,
    PLUGIN_VERSION,
    PLUGIN_REPO,
)
class OpenCodePlugin(Star):
    def __init__(self, context: Context, config: Optional[AstrBotConfig] = None):
        super().__init__(context)
        resolved_config = config
        if resolved_config is None:
            resolved_config = getattr(self, "config", None)
        if resolved_config is None:
            resolved_config = {}

        self.config = resolved_config
        self.runtime_config = copy.deepcopy(resolved_config)
        self._migrate_config(self.runtime_config)
        self.logger = logger

        # 基础数据目录（使用框架 API 获取，兼容不同部署环境）
        self.base_data_dir = str(
            Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_opencode"
        )

        # 初始化各个核心模块
        runtime_config = self._get_runtime_config()
        self.session_mgr = SessionManager(runtime_config, self.base_data_dir)
        self.storage_mgr = StorageManager(self.base_data_dir, runtime_config)
        self.security = SecurityChecker(runtime_config, self.base_data_dir)
        self.input_proc = InputProcessor()
        self.executor = CommandExecutor(runtime_config)
        self.output_proc = OutputProcessor(runtime_config, self.base_data_dir)
        self._send_file_list_cache: dict[str, dict] = {}

        # 设置模块间的回调函数，建立模块间的通信
        self.session_mgr.set_record_workdir_callback(self.storage_mgr.record_workdir)
        self.storage_mgr.set_get_workdirs_callback(self.session_mgr.get_all_workdirs)
        self.security.set_load_history_callback(self.storage_mgr.load_workdir_history)

    def _get_runtime_config(self) -> dict:
        runtime_config = getattr(self, "runtime_config", None)
        if isinstance(runtime_config, dict):
            return runtime_config
        return self.config

    def _migrate_config(self, target_config: Optional[dict] = None):
        """仅补齐运行时默认值，避免把隐藏字段写回 AstrBot 面板配置。"""
        config = (
            target_config if target_config is not None else self._get_runtime_config()
        )
        basic_cfg = config.setdefault("basic_config", {})

        if (
            "confirm_all_write_ops" in basic_cfg
            and "allow_file_writes" not in basic_cfg
        ):
            basic_cfg["allow_file_writes"] = True

        basic_cfg.setdefault("only_admin", True)
        basic_cfg.setdefault("acp_command", "opencode")
        basic_cfg.setdefault("acp_args", ["acp"])
        basic_cfg.setdefault("acp_startup_timeout", 30)
        basic_cfg.setdefault("work_dir", "")
        basic_cfg.setdefault("proxy_url", "")
        basic_cfg.setdefault("allow_file_writes", True)
        basic_cfg.setdefault("confirm_timeout", 30)

        basic_cfg.setdefault("backend_type", "acp_opencode")
        capabilities_default = {
            "fs_read_text": True,
            "fs_write_text": True,
            "terminal": True,
        }
        existing_capabilities = basic_cfg.get("acp_client_capabilities")
        if not isinstance(existing_capabilities, dict):
            basic_cfg["acp_client_capabilities"] = dict(capabilities_default)
        else:
            for key, value in capabilities_default.items():
                existing_capabilities.setdefault(key, value)

        basic_cfg.setdefault("default_agent", "build")
        basic_cfg.setdefault("default_mode", "ask")
        if not isinstance(basic_cfg.get("default_config_options"), dict):
            basic_cfg["default_config_options"] = {}

        if "destructive_keywords" not in basic_cfg:
            basic_cfg["destructive_keywords"] = [
                "删除",
                "格式化",
                "清空",
                "rm\\b",
                "delete\\b",
                "format\\b",
                "wipe\\b",
                "destroy\\b",
                "shutdown\\b",
                "reboot\\b",
                "mkfs",
                "dd\\b",
                "> /dev/",
            ]
        basic_cfg.setdefault("check_path_safety", False)
        basic_cfg.setdefault("confirm_all_write_ops", False)

        tool_cfg = config.setdefault("tool_config", {})
        tool_cfg.setdefault(
            "tool_description",
            "在用户电脑上调用 OpenCode 等 AI 智能体 Agent 的工具。当用户有执行编程、处理文档等复杂任务的高级需求时，调用此工具。",
        )
        tool_cfg.setdefault(
            "arg_description",
            "详细的任务描述。保持原意，允许适当编辑以提升精准度，也可以不修改。此参数会被传送给 OpenCode 作为输入。",
        )

        output_cfg = config.setdefault("output_config", {})
        output_cfg.setdefault(
            "output_modes", ["ai_summary", "txt_file", "long_image", "full_text"]
        )
        output_cfg.setdefault("max_text_length", 1000)
        output_cfg.setdefault("merge_forward_enabled", False)
        output_cfg.setdefault("smart_trigger_ai_summary", True)
        output_cfg.setdefault("smart_trigger_txt_file", True)
        output_cfg.setdefault("smart_trigger_long_image", True)

    async def _check_and_confirm_destructive(
        self,
        event: AstrMessageEvent,
        task: str,
        timeout: int,
        *,
        prompt_text: str,
        confirm_text: str,
        timeout_text: str,
        reject_text: str,
    ) -> tuple[bool, Optional[str]]:
        """统一处理前置安全检查和纯文本确认。"""
        decision = self.security.evaluate_preflight(task)
        if not decision.requires_confirmation:
            return True, None
        if decision.reason == "file_write_blocked":
            return False, "file_write_blocked"

        await event.send(event.plain_result(prompt_text))

        user_choice = asyncio.Event()
        approved = False

        @session_waiter(timeout=timeout)
        async def confirm(c: SessionController, e: AstrMessageEvent):
            nonlocal approved
            if e.message_str == confirm_text:
                approved = True
            user_choice.set()
            c.stop()

        try:
            await confirm(event)
            await user_choice.wait()
        except TimeoutError:
            await event.send(event.plain_result(timeout_text))
            return False, decision.reason

        if not approved:
            await event.send(event.plain_result(reject_text))
            return False, decision.reason

        return True, decision.reason

    def _render_exec_status(self, session) -> str:
        """渲染执行中提示"""
        lines = ["🚀 执行中...", f"📂 工作目录: {session.work_dir}"]
        lines.extend(self._render_live_state_lines(session, include_defaults=True))
        return "\n".join(lines)

    def _render_live_state_lines(
        self, session, include_defaults: bool = False
    ) -> list[str]:
        agent_text = session.agent_name or "未提供"
        mode_text = session.current_mode_id or "未提供"
        config_values = session.current_config_values or {}
        config_text = (
            ", ".join(f"{key}={value}" for key, value in sorted(config_values.items()))
            if config_values
            else "无"
        )
        lines = [
            f"🤖 当前 agent: {agent_text}",
            f"🎛️ 当前 mode: {mode_text}",
            f"⚙️ 当前配置: {config_text}",
        ]
        if include_defaults:
            lines.extend(
                [
                    f"🧭 默认 agent: {session.default_agent or '未设置'}",
                    f"🪄 默认 mode: {session.default_mode or '未设置'}",
                ]
            )
        if session.backend_session_id:
            lines.append(f"🔗 当前会话: {session.backend_session_id}")
        else:
            lines.append("🔗 当前会话: 未绑定（下次 /oc 会创建新会话）")
        return lines

    def _render_lifecycle_status(
        self,
        session,
        headline: str,
        *,
        include_proxy: bool = False,
        extra_lines: Optional[list[str]] = None,
    ) -> str:
        lines = [headline, f"📂 工作目录: {session.work_dir}"]
        if include_proxy:
            lines.append(f"🌐 代理环境: {session.env.get('http_proxy', '无')}")
        if extra_lines:
            lines.extend(extra_lines)
        lines.extend(self._render_live_state_lines(session, include_defaults=True))
        return "\n".join(lines)

    def _get_mode_options(self, session) -> tuple[str, list[dict[str, Any]]]:
        config_mode_options = [
            item
            for item in (session.config_options or [])
            if str(item.get("category") or "").strip() == "mode"
        ]
        if config_mode_options:
            return "configOptions", config_mode_options
        if session.available_modes:
            return "modes", list(session.available_modes)
        return "none", []

    def _resolve_mode_selection(
        self, session, mode_value: str
    ) -> tuple[str, Optional[dict[str, Any]]]:
        source, options = self._get_mode_options(session)
        normalized_value = mode_value.strip().lower()
        for item in options:
            candidates = [
                str(item.get("id") or "").strip().lower(),
                str(item.get("name") or item.get("label") or "").strip().lower(),
                str(item.get("value") or "").strip().lower(),
            ]
            if normalized_value in {candidate for candidate in candidates if candidate}:
                return source, item
        return source, None

    def _collect_available_agents(self, session) -> list[str]:
        values = []
        for item in session.available_agents or []:
            if isinstance(item, dict):
                text = str(item.get("name") or item.get("title") or "").strip()
            else:
                text = str(item or "").strip()
            if text and text not in values:
                values.append(text)
        for item in [
            session.agent_name,
            session.default_agent,
            self._get_runtime_config().get("basic_config", {}).get("default_agent"),
        ]:
            text = str(item or "").strip()
            if text and text not in values:
                values.append(text)
        return values

    def _render_agent_overview(self, session) -> str:
        available_agents = self._collect_available_agents(session)
        lines = ["🤖 Agent 状态"]
        lines.extend(self._render_live_state_lines(session, include_defaults=True))
        if available_agents:
            lines.append(f"📚 可选 agent: {', '.join(available_agents)}")
        else:
            lines.append("📚 可选 agent: 当前后端未提供，先展示已知偏好")
        return "\n".join(lines)

    def _render_mode_overview(self, session) -> str:
        source, options = self._get_mode_options(session)
        lines = ["🎛️ Mode 状态"]
        lines.extend(self._render_live_state_lines(session, include_defaults=True))
        if source == "none":
            lines.append("📚 当前后端未暴露可切换 mode")
            return "\n".join(lines)

        prefix = "configOptions" if source == "configOptions" else "modes"
        lines.append(f"📚 可切换来源: {prefix}")
        for item in options:
            label = item.get("name") or item.get("label") or item.get("id") or "未命名"
            value = item.get("value")
            if value is not None and str(value).strip():
                lines.append(f"- {label} ({value})")
            else:
                lines.append(f"- {label}")
        return "\n".join(lines)

    def _normalize_backend_sessions(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            session_id = item.get("id") or item.get("sessionId")
            if not session_id:
                continue
            normalized.append(
                {
                    "id": str(session_id),
                    "title": str(item.get("title") or "无标题"),
                }
            )
        return normalized

    def _match_backend_session(
        self, sessions: list[dict[str, str]], query: str
    ) -> Optional[dict[str, str]]:
        if query.isdigit():
            index = int(query)
            if 1 <= index <= len(sessions):
                return sessions[index - 1]
        for item in sessions:
            if item["id"] == query:
                return item
        query_lower = query.lower()
        for item in sessions:
            if query_lower in item["title"].lower():
                return item
        return None

    def _extract_permission_update(self, output, session) -> Optional[str]:
        events = []
        if hasattr(self.output_proc, "_extract_embedded_events"):
            events = self.output_proc._extract_embedded_events(output)
        if not events or not hasattr(self.output_proc, "build_chat_updates"):
            return None
        updates = self.output_proc.build_chat_updates(events, session=session)
        if session.pending_permission:
            for item in reversed(updates):
                if "权限确认" in item:
                    return item
        return None

    def _map_permission_reply(self, reply_text: str, permission: dict) -> Optional[str]:
        text = (reply_text or "").strip()
        if not text:
            return None
        options = permission.get("options") or []
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(options):
                return str(options[index - 1].get("optionId") or "") or None

        alias_map = {
            "允许一次": "allow_once",
            "始终允许": "allow_always",
            "拒绝": "reject_once",
            "拒绝一次": "reject_once",
            "始终拒绝": "reject_always",
            "取消": "cancelled",
        }
        if text in alias_map:
            return alias_map[text]

        lowered = text.lower()
        for item in options:
            option_id = str(item.get("optionId") or "").strip()
            label = str(item.get("label") or item.get("display") or "").strip()
            if lowered in {option_id.lower(), label.lower()}:
                return option_id or None
        return None

    async def _wait_for_permission_choice(self, event, session) -> tuple[str, bool]:
        permission = dict(session.pending_permission or {})
        timeout = (
            self._get_runtime_config()
            .get("basic_config", {})
            .get("confirm_timeout", 30)
        )
        completed = asyncio.Event()
        selected = {"option": ""}

        @session_waiter(timeout=timeout)
        async def wait_permission(c: SessionController, e: AstrMessageEvent):
            option_id = self._map_permission_reply(e.message_str, permission)
            if not option_id:
                return
            selected["option"] = option_id
            completed.set()
            c.stop()

        try:
            await wait_permission(event)
            await completed.wait()
            return str(selected["option"]), False
        except TimeoutError:
            return "cancelled", True

    async def _run_oc_prompt(
        self,
        event: AstrMessageEvent,
        session,
        prompt_payload: Any,
        emit_status: bool = True,
    ):
        if emit_status:
            yield event.plain_result(self._render_exec_status(session))

        output = None
        stream = None
        used_live_stream = False

        if hasattr(self.executor, "stream_prompt"):
            stream = self.executor.stream_prompt(prompt_payload, session)
            used_live_stream = True

        while stream is not None:
            next_stream = None
            async for item in stream:
                if not isinstance(item, dict):
                    continue

                kind = str(item.get("kind") or "").strip()
                if kind == "event":
                    updates = []
                    if hasattr(self.output_proc, "build_chat_updates"):
                        updates = self.output_proc.build_chat_updates(
                            [item.get("event") or {}], session=session
                        )
                    for update in updates:
                        if update:
                            yield event.plain_result(update)

                    if session.pending_permission:
                        permission = dict(session.pending_permission or {})
                        option_id, timed_out = await self._wait_for_permission_choice(
                            event, session
                        )
                        if timed_out:
                            yield event.plain_result("⏱️ 已因超时取消本次授权请求")
                        if hasattr(self.executor, "stream_permission_response"):
                            next_stream = self.executor.stream_permission_response(
                                session,
                                request_id=str(permission.get("requestId") or ""),
                                option_id=option_id,
                            )
                        else:
                            output = await self.executor.respond_permission(
                                session,
                                request_id=str(permission.get("requestId") or ""),
                                option_id=option_id,
                            )
                        break
                    continue

                if kind == "result":
                    output = item.get("result")
                    break

            if output is not None:
                break
            stream = next_stream

        if output is None:
            output = await self.executor.run_prompt(prompt_payload, session)

        while True:
            permission_message = self._extract_permission_update(output, session)
            if not permission_message or not session.pending_permission:
                break

            yield event.plain_result(permission_message)
            option_id, timed_out = await self._wait_for_permission_choice(
                event, session
            )
            if timed_out:
                yield event.plain_result("⏱️ 已因超时取消本次授权请求")
            output = await self.executor.respond_permission(
                session,
                request_id=str(session.pending_permission.get("requestId") or ""),
                option_id=option_id,
            )

        if used_live_stream:
            payload = getattr(output, "payload", None)
            if isinstance(payload, dict):
                for key in ("events", "updates", "items"):
                    payload.pop(key, None)

        send_plan = await self.output_proc.parse_output_plan(output, event, session)
        for idx, components in enumerate(send_plan):
            if idx > 0:
                await asyncio.sleep(self.output_proc.next_send_delay())
            yield event.chain_result(components)

    async def _prepare_oc_execution(
        self,
        event: AstrMessageEvent,
        task_description: str,
        *,
        empty_message: str,
    ):
        session = self.session_mgr.get_or_create_session(event.get_sender_id())
        prompt_payload = await self.input_proc.process_input_message(
            event, session, task_description
        )
        if not prompt_payload:
            return session, None, empty_message
        return session, prompt_payload, ""

    async def _start_oc_execution(
        self,
        event: AstrMessageEvent,
        session,
        prompt_payload: Any,
        *,
        background: bool,
        emit_status: bool,
    ):
        if background:
            if emit_status:
                await event.send(event.plain_result(self._render_exec_status(session)))
            asyncio.create_task(
                self._execute_opencode_background(
                    event.unified_msg_origin,
                    prompt_payload,
                    session,
                    event,
                )
            )
            return

        async for result in self._run_oc_prompt(
            event,
            session,
            prompt_payload,
            emit_status=emit_status,
        ):
            yield result

    async def _prepare_history_session_bind(self, session) -> tuple[bool, str]:
        init_result = await self.executor.initialize_if_needed(session)
        if not init_result.ok:
            return False, f"❌ 初始化 ACP backend 失败：{init_result.message}"

        capabilities = self.executor.get_protocol_capabilities()
        if not capabilities.get("loadSession"):
            return False, "⚠️ 当前 backend 不支持恢复历史会话，无法绑定该 session。"

        return True, ""

    def _make_history_probe_session(self, session):
        return type(session)(
            work_dir=session.work_dir,
            env=dict(session.env),
            backend_kind=session.backend_kind,
            default_agent=session.default_agent,
            default_mode=session.default_mode,
            default_config_options=dict(session.default_config_options or {}),
        )

    def _commit_loaded_history_session(self, target_session, loaded_session) -> None:
        target_session.work_dir = loaded_session.work_dir
        target_session.backend_session_id = loaded_session.backend_session_id
        target_session.backend_session_live = loaded_session.backend_session_live
        target_session.protocol_version = loaded_session.protocol_version
        target_session.agent_name = loaded_session.agent_name
        target_session.agent_title = loaded_session.agent_title
        target_session.available_agents = list(loaded_session.available_agents)
        target_session.current_mode_id = loaded_session.current_mode_id
        target_session.config_options = list(loaded_session.config_options)
        target_session.current_config_values = dict(
            loaded_session.current_config_values
        )
        target_session.available_modes = list(loaded_session.available_modes)
        target_session.available_commands = list(loaded_session.available_commands)
        target_session.session_capabilities = dict(loaded_session.session_capabilities)
        target_session.pending_permission = loaded_session.pending_permission
        target_session.prompt_running = loaded_session.prompt_running

    def _get_send_page_size(self) -> int:
        return 50

    def _get_send_scan_limit(self) -> int:
        return 10000

    def _extract_oc_send_args(self, event: AstrMessageEvent, fallback_path: str) -> str:
        full_command = event.message_str.strip()
        parts = full_command.split(" ", 1)
        if len(parts) > 1:
            return parts[1].strip()
        return (fallback_path or "").strip()

    def _is_absolute_like_path(self, path_text: str) -> bool:
        if os.path.isabs(path_text):
            return True
        return bool(re.match(r"^[A-Za-z]:[\\/]", path_text))

    def _tokenize_send_args(self, arg_text: str) -> list[str]:
        if not arg_text:
            return []
        try:
            pieces = shlex.split(arg_text, posix=False)
        except ValueError:
            pieces = arg_text.split()

        tokens: list[str] = []
        for piece in pieces:
            for part in piece.split(","):
                token = part.strip().strip('"').strip("'")
                if token:
                    tokens.append(token)
        return tokens

    def _scan_workspace_files(self, work_dir: str, keyword: str = "") -> dict:
        page_size = self._get_send_page_size()
        scan_limit = self._get_send_scan_limit()
        keyword_lower = keyword.lower().strip()

        rel_files: list[str] = []
        scanned = 0
        truncated = False

        for root, _, files in os.walk(work_dir, onerror=lambda _: None):
            for filename in files:
                scanned += 1
                if scanned > scan_limit:
                    truncated = True
                    break

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, work_dir).replace("\\", "/")
                if keyword_lower and keyword_lower not in rel_path.lower():
                    continue
                rel_files.append(rel_path)

            if truncated:
                break

        rel_files.sort()
        total = len(rel_files)
        total_pages = max(1, (total + page_size - 1) // page_size)

        return {
            "work_dir": work_dir,
            "files": rel_files,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "keyword": keyword,
            "scanned": scanned,
            "truncated": truncated,
            "created_at": datetime.now().isoformat(),
        }

    def _render_send_file_page(self, snapshot: dict, page: int) -> str:
        files = snapshot["files"]
        total = snapshot["total"]
        page_size = snapshot["page_size"]
        total_pages = snapshot["total_pages"]
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        end = min(start + page_size, total)

        lines = [
            "📄 可发送文件列表（当前工作区，递归）",
            f"📂 目录: {snapshot['work_dir']}",
            f"📊 共 {total} 个文件 | 第 {page}/{total_pages} 页 | 每页 {page_size} 条",
        ]

        keyword = (snapshot.get("keyword") or "").strip()
        if keyword:
            lines.append(f"🔎 过滤关键词: {keyword}")

        if snapshot.get("truncated"):
            lines.append(
                f"⚠️ 已触发扫描上限（{self._get_send_scan_limit()}），结果可能不完整。建议使用 /oc-send --find 关键词 缩小范围。"
            )

        lines.append("")

        if total == 0:
            lines.append("（没有可发送的文件）")
        else:
            for idx in range(start, end):
                rel_path = files[idx]
                display = (
                    rel_path
                    if len(rel_path) <= 120
                    else rel_path[:57] + "..." + rel_path[-60:]
                )
                lines.append(f"{idx + 1}. {display}")

        lines.extend(
            [
                "",
                "快捷发送示例:",
                "- /oc-send 1",
                "- /oc-send 2,5,8",
                "- /oc-send 10-15",
                "- /oc-send src/main.py docs/readme.md",
                "- /oc-send --page 2",
                "- /oc-send --find config",
            ]
        )
        return "\n".join(lines)

    def _parse_send_page_query(self, arg_text: str) -> Optional[int]:
        match = re.fullmatch(r"--page\s+(\d+)", arg_text.strip())
        if not match:
            return None
        return int(match.group(1))

    def _parse_send_find_query(self, arg_text: str) -> Optional[str]:
        match = re.fullmatch(r"--find\s+(.+)", arg_text.strip())
        if not match:
            return None
        return match.group(1).strip()

    def _expand_index_tokens(
        self, tokens: list[str], max_index: int
    ) -> tuple[list[int], list[str]]:
        indexes: list[int] = []
        errors: list[str] = []

        for token in tokens:
            range_match = re.fullmatch(r"(\d+)-(\d+)", token)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                if start > end:
                    errors.append(f"无效范围: {token}")
                    continue
                for idx in range(start, end + 1):
                    if 1 <= idx <= max_index:
                        indexes.append(idx)
                    else:
                        errors.append(f"序号越界: {idx}")
                continue

            if token.isdigit():
                idx = int(token)
                if 1 <= idx <= max_index:
                    indexes.append(idx)
                else:
                    errors.append(f"序号越界: {idx}")

        deduped_indexes: list[int] = []
        for idx in indexes:
            if idx not in deduped_indexes:
                deduped_indexes.append(idx)
        return deduped_indexes, errors

    def _resolve_send_targets(
        self,
        sender_id: str,
        session,
        arg_text: str,
    ) -> tuple[list[str], list[str]]:
        tokens = self._tokenize_send_args(arg_text)
        if not tokens:
            return [], ["未提供可识别的文件参数。"]

        snapshot = self._send_file_list_cache.get(sender_id)
        max_index = len(snapshot["files"]) if snapshot else 0

        index_tokens: list[str] = []
        path_tokens: list[str] = []
        for token in tokens:
            if re.fullmatch(r"\d+", token) or re.fullmatch(r"\d+-\d+", token):
                index_tokens.append(token)
            else:
                path_tokens.append(token)

        resolved: list[str] = []
        errors: list[str] = []

        if index_tokens:
            if not snapshot:
                errors.append(
                    "未找到可用编号快照，请先执行一次 /oc-send 获取列表后再按序号发送。"
                )
            else:
                indexes, idx_errors = self._expand_index_tokens(index_tokens, max_index)
                errors.extend(idx_errors)
                for idx in indexes:
                    rel_path = snapshot["files"][idx - 1]
                    abs_path = os.path.abspath(
                        os.path.join(snapshot["work_dir"], rel_path)
                    )
                    resolved.append(abs_path)

        for token in path_tokens:
            candidate = os.path.expanduser(token)
            if self._is_absolute_like_path(candidate):
                abs_path = os.path.abspath(candidate)
            else:
                abs_path = os.path.abspath(os.path.join(session.work_dir, candidate))
            resolved.append(abs_path)

        deduped: list[str] = []
        for p in resolved:
            if p not in deduped:
                deduped.append(p)
        return deduped, errors

    async def initialize(self):
        """插件初始化"""
        # 配置 LLM 工具描述
        tool_mgr = self.context.get_llm_tool_manager()
        tool = tool_mgr.get_func("call_opencode")
        if tool:
            tool_cfg = self._get_runtime_config().get("tool_config", {})
            desc = tool_cfg.get("tool_description")
            if desc:
                tool.description = desc

            arg_desc = tool_cfg.get("arg_description")
            if (
                arg_desc
                and "properties" in tool.parameters
                and "task_description" in tool.parameters["properties"]
            ):
                tool.parameters["properties"]["task_description"]["description"] = (
                    arg_desc
                )

        # 配置输出处理器
        self.output_proc.set_html_render(self.html_render)
        self.output_proc.set_llm_functions(
            self.context.llm_generate, self.context.get_current_chat_provider_id
        )
        self.output_proc.set_template_dir(os.path.dirname(__file__))

        # 运行模式健康检查
        ok, detail = await self.executor.health_check()
        mode_text = "ACP 后端"
        if ok:
            self.logger.info(
                f"{PLUGIN_DISPLAY_NAME} initialized. mode={mode_text}, detail={detail}"
            )
        else:
            self.logger.warning(
                f"{PLUGIN_DISPLAY_NAME} initialized with warning. mode={mode_text}, detail={detail}"
            )

    async def terminate(self):
        """插件卸载/停用时的清理"""
        await self.executor.close()
        await self.storage_mgr.stop_auto_clean_task()
        self.logger.info(f"{PLUGIN_DISPLAY_NAME} terminated.")

    # ==================== 命令处理器 ====================

    @filter.command("oc")
    async def oc_handler(self, event: AstrMessageEvent, message: str = ""):
        """调用 OpenCode 执行任务。用法：/oc [任务描述]。同一会话内的多次调用会保持对话上下文。"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        # 手动解析完整指令，保留空格和换行
        full_command = event.message_str.strip()
        parts = full_command.split(" ", 1)
        actual_message = parts[1].strip() if len(parts) > 1 else ""

        session, final_message, empty_message = await self._prepare_oc_execution(
            event,
            actual_message,
            empty_message="请输入任务、发送图片或引用消息。",
        )
        if not final_message:
            yield event.plain_result(empty_message)
            return

        # 获取超时配置
        timeout = (
            self._get_runtime_config()
            .get("basic_config", {})
            .get("confirm_timeout", 30)
        )

        approved, reason = await self._check_and_confirm_destructive(
            event,
            final_message,
            timeout,
            prompt_text=f"⚠️ 敏感操作确认：'{final_message}'\n回复'确认'继续，其他取消 ({timeout}s)",
            confirm_text="确认",
            timeout_text="超时取消",
            reject_text="已取消",
        )
        if not approved:
            if reason == "file_write_blocked":
                yield event.plain_result("❌ 当前已禁止文件写入操作")
            return

        async for result in self._start_oc_execution(
            event,
            session,
            final_message,
            background=False,
            emit_status=True,
        ):
            yield result

    @filter.command("oc-agent")
    async def oc_agent(self, event: AstrMessageEvent, agent_name: str = ""):
        """查看或设置默认 agent。用法：/oc-agent [名称]"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        session = self.session_mgr.get_or_create_session(event.get_sender_id())
        agent_name = agent_name.strip()

        if not agent_name:
            yield event.plain_result(self._render_agent_overview(session))
            return

        session.default_agent = agent_name
        yield event.plain_result(
            "✅ 已更新默认 agent。\n"
            f"🧭 下次新会话默认使用: {session.default_agent}\n"
            f"🤖 当前 live agent 保持: {session.agent_name or '未提供'}\n"
            f"📚 可选 agent: {', '.join(self._collect_available_agents(session)) or '当前后端未提供'}"
        )

    @filter.command("oc-mode")
    async def oc_mode(self, event: AstrMessageEvent, mode_value: str = ""):
        """查看或设置当前 mode。用法：/oc-mode [值]"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        session = self.session_mgr.get_or_create_session(event.get_sender_id())
        mode_value = mode_value.strip()

        if not mode_value:
            yield event.plain_result(self._render_mode_overview(session))
            return

        source, selected = self._resolve_mode_selection(session, mode_value)
        if source == "none":
            session.default_mode = mode_value
            yield event.plain_result(
                f"✅ 已更新默认 mode: {mode_value}\n📚 当前 backend 未暴露可切换 mode"
            )
            return

        if not selected:
            yield event.plain_result(
                f"❌ 未找到可用 mode：{mode_value}\n{self._render_mode_overview(session)}"
            )
            return

        result = None
        if source == "configOptions":
            option_id = str(selected.get("id") or "")
            value = selected.get("value")
            if value is None or str(value).strip() == "":
                value = mode_value
            for option in session.config_options or []:
                if str(option.get("category") or "").strip() == "mode":
                    session.default_config_options.pop(
                        str(option.get("id") or ""), None
                    )
            session.default_config_options[option_id] = value
            if session.backend_session_id:
                result = await self.executor.set_config_option(
                    session, option_id, value
                )
        else:
            session.default_mode = str(selected.get("id") or mode_value)
            if session.backend_session_id:
                result = await self.executor.set_mode(session, session.default_mode)

        session.default_mode = str(
            selected.get("value")
            or selected.get("name")
            or selected.get("id")
            or mode_value
        )

        if result is not None and not result.ok:
            yield event.plain_result(f"❌ mode 切换失败：{result.message}")
            return

        yield event.plain_result(
            "✅ 已更新 mode 偏好。\n"
            f"🎛️ 默认 mode: {session.default_mode}\n"
            f"🎛️ 当前模式: {session.current_mode_id or session.default_mode}\n"
            f"⚙️ 当前配置: {session.current_config_values or session.default_config_options or {}}"
        )

    @filter.command("oc-send")
    async def oc_send(self, event: AstrMessageEvent, path: str = ""):
        """发送文件。用法：/oc-send（列文件）| /oc-send 1,2 | /oc-send 相对路径/绝对路径"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        sender_id = event.get_sender_id()
        session = self.session_mgr.get_or_create_session(sender_id)
        arg_text = self._extract_oc_send_args(event, path)

        if not arg_text:
            snapshot = self._scan_workspace_files(session.work_dir)
            self._send_file_list_cache[sender_id] = snapshot
            yield event.plain_result(self._render_send_file_page(snapshot, page=1))
            return

        page_query = self._parse_send_page_query(arg_text)
        if page_query is not None:
            snapshot = self._send_file_list_cache.get(sender_id)
            if not snapshot:
                snapshot = self._scan_workspace_files(session.work_dir)
                self._send_file_list_cache[sender_id] = snapshot
            yield event.plain_result(
                self._render_send_file_page(snapshot, page=page_query)
            )
            return

        keyword = self._parse_send_find_query(arg_text)
        if keyword is not None:
            snapshot = self._scan_workspace_files(session.work_dir, keyword=keyword)
            self._send_file_list_cache[sender_id] = snapshot
            yield event.plain_result(self._render_send_file_page(snapshot, page=1))
            return

        resolved_paths, parse_errors = self._resolve_send_targets(
            sender_id, session, arg_text
        )
        valid_files: list[str] = []
        validation_errors: list[str] = []

        for target_path in resolved_paths:
            if not os.path.exists(target_path) or not os.path.isfile(target_path):
                validation_errors.append(f"不存在或不是文件: {target_path}")
                continue

            if not self.security.is_path_safe(target_path, session):
                validation_errors.append(f"不在允许目录范围内: {target_path}")
                continue

            valid_files.append(target_path)

        all_errors = parse_errors + validation_errors
        if not valid_files:
            if all_errors:
                lines = "\n".join([f"- {msg}" for msg in all_errors[:20]])
                yield event.plain_result(
                    "❌ 没有可发送的有效文件：\n"
                    f"{lines}\n\n"
                    "提示：先执行 /oc-send 查看编号，或改用明确的相对/绝对路径。"
                )
            else:
                yield event.plain_result("❌ 没有可发送的有效文件。")
            return

        try:
            components = [
                File(file=os.path.abspath(p), name=os.path.basename(p))
                for p in valid_files
            ]
            yield event.chain_result(components)

            if all_errors:
                lines = "\n".join([f"- {msg}" for msg in all_errors[:20]])
                yield event.plain_result(
                    f"✅ 已发送 {len(valid_files)} 个文件。\n"
                    f"⚠️ 另有 {len(all_errors)} 项未发送：\n{lines}"
                )
        except OSError as e:
            self.logger.error(f"文件发送失败 (权限或路径问题): {e}")
            yield event.plain_result(f"❌ 发送失败: {e}")
        except Exception as e:
            self.logger.error(f"文件发送失败: {e}")
            yield event.plain_result(f"❌ 发送失败: {e}")

    @filter.command("oc-new")
    async def oc_new(self, event: AstrMessageEvent, path: str = ""):
        """重置会话并切换工作目录。用法：/oc-new [路径]。会清除对话上下文，下次 /oc 开始全新对话。"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        sender_id = event.get_sender_id()
        target_path = path.strip() if path else None

        # 默认工作目录逻辑
        basic_cfg = self._get_runtime_config().get("basic_config", {})
        default_wd = basic_cfg.get("work_dir", "").strip()
        if not default_wd:
            default_wd = os.path.join(self.base_data_dir, "workspace")

        final_wd = default_wd

        if target_path:
            if not os.path.exists(target_path):
                yield event.plain_result(
                    f"⚠️ 目录不存在：{target_path}\n是否创建并使用此目录？(y/n, 30s超时)"
                )

                @session_waiter(timeout=30)
                async def confirm_path(c: SessionController, e: AstrMessageEvent):
                    if e.message_str.lower() in ["y", "yes", "确认", "是"]:
                        try:
                            os.makedirs(target_path, exist_ok=True)
                            await e.send(
                                e.plain_result(
                                    await self._init_session(sender_id, target_path)
                                )
                            )
                            c.stop()
                        except Exception as ex:
                            await e.send(
                                e.plain_result(
                                    f"❌ 创建目录失败: {ex}\n已回退到默认目录。"
                                )
                            )
                            await e.send(
                                e.plain_result(
                                    await self._init_session(sender_id, default_wd)
                                )
                            )
                            c.stop()
                    else:
                        await e.send(e.plain_result("已取消自定义路径，使用默认目录。"))
                        await e.send(
                            e.plain_result(
                                await self._init_session(sender_id, default_wd)
                            )
                        )
                        c.stop()

                try:
                    await confirm_path(event)
                except TimeoutError:
                    yield event.plain_result("超时，自动使用默认工作目录。")
                    yield event.plain_result(
                        await self._init_session(sender_id, default_wd)
                    )
                return
            else:
                final_wd = target_path

        yield event.plain_result(await self._init_session(sender_id, final_wd))

    async def _init_session(self, sender_id, work_dir):
        """初始化会话的辅助函数"""
        session = self.session_mgr.reset_session(sender_id, work_dir=work_dir)
        return self._render_lifecycle_status(
            session,
            "✅ 已重置当前 ACP 会话绑定",
            include_proxy=True,
        )

    @filter.command("oc-end")
    async def oc_end(self, event: AstrMessageEvent):
        """清除当前对话上下文，但保留工作目录。下次 /oc 将开始新对话。"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        sender_id = event.get_sender_id()
        session = self.session_mgr.get_or_create_session(sender_id)
        had_live_session = bool(session.backend_session_id)
        session.reset_live_session()
        headline = (
            "🚫 已结束当前 ACP 会话绑定。"
            if had_live_session
            else "🚫 当前没有正在绑定的 ACP 会话，已结束空会话并保持未绑定状态。"
        )
        yield event.plain_result(self._render_lifecycle_status(session, headline))

    @filter.command("oc-clean")
    async def oc_clean(self, event: AstrMessageEvent):
        """手动清理临时文件"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        count, size_mb = await self.storage_mgr.clean_temp_files()
        yield event.plain_result(
            f"🧹 清理完成：共删除 {count} 个文件，释放 {size_mb:.2f} MB 空间。"
        )

    @filter.command("oc-history")
    async def oc_history(self, event: AstrMessageEvent):
        """查看工作目录使用历史。用法：/oc-history"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        history = self.storage_mgr.load_workdir_history()

        if not history:
            yield event.plain_result("📂 暂无工作目录使用历史。")
            return

        lines = ["📂 工作目录使用历史（最近10条）：\n"]
        for i, record in enumerate(history[:10], 1):
            path = record.get("path", "未知")
            last_used = record.get("last_used", "未知")
            used_count = record.get("used_count", 0)

            try:
                dt = datetime.fromisoformat(last_used)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                time_str = last_used

            lines.append(f"{i}. {path}")
            lines.append(f"   最后使用: {time_str} | 使用次数: {used_count}\n")

        yield event.plain_result("\n".join(lines))

    @filter.command("oc-session")
    async def oc_session(self, event: AstrMessageEvent, query: str = ""):
        """管理 ACP backend 会话。用法：/oc-session [序号/ID/标题]"""
        if not self.security.is_admin(event):
            yield event.plain_result("权限不足。")
            return

        sender_id = event.get_sender_id()
        query = query.strip()

        session = self.session_mgr.get_or_create_session(sender_id)
        listed = await self.executor.list_sessions(limit=50 if query else 10)
        if not listed.ok:
            yield event.plain_result(f"❌ 获取 ACP 会话列表失败：{listed.message}")
            return

        sessions = self._normalize_backend_sessions(listed.items)

        if not query:
            if not sessions:
                yield event.plain_result("📋 当前 backend 暂无可列出的 ACP 会话。")
                return

            lines = ["📋 ACP 会话列表："]
            for index, item in enumerate(sessions, start=1):
                title = item["title"]
                if len(title) > 40:
                    title = title[:37] + "..."
                lines.append(f"{index}. {title}")
                lines.append(f"   ID: {item['id']}")
            lines.extend(self._render_live_state_lines(session, include_defaults=True))
            yield event.plain_result("\n".join(lines))
            return

        target_session = self._match_backend_session(sessions, query)
        if not target_session:
            yield event.plain_result(
                f"❌ 未找到匹配的会话：{query}\n请先使用 /oc-session 查看列表。"
            )
            return

        can_bind, error_message = await self._prepare_history_session_bind(session)
        if not can_bind:
            yield event.plain_result(error_message)
            return

        probe_session = self._make_history_probe_session(session)
        probe_session.bind_backend_session(target_session["id"])
        loaded = await self.executor.load_session(probe_session)
        if not loaded.ok:
            session.reset_live_session()
            yield event.plain_result(
                self._render_lifecycle_status(
                    session,
                    f"❌ 绑定历史会话失败：{loaded.message}",
                    extra_lines=[f"📝 目标标题: {target_session['title']}"],
                )
            )
            return

        self._commit_loaded_history_session(session, probe_session)

        lines = [
            "✅ 已绑定 ACP 会话。",
            f"📝 标题: {target_session['title']}",
            f"🔑 ID: {target_session['id']}",
            f"📂 已同步到历史会话工作目录: {session.work_dir}",
        ]
        lines.extend(self._render_live_state_lines(session, include_defaults=True))
        yield event.plain_result("\n".join(lines))

    # ==================== LLM 工具 ====================

    @filter.llm_tool(name="call_opencode")
    async def call_opencode_tool(
        self, event: AstrMessageEvent, task_description: str
    ) -> MessageEventResult:
        """在用户电脑上调用 OpenCode 等 AI 智能体 Agent 的工具。当用户有执行编程、处理文档等复杂任务的高级需求时，调用此工具。

        Args:
            task_description(string): 详细的任务描述。保持原意，允许适当编辑以提升精准度，也可以不修改。此参数会被传送给 OpenCode 作为输入。
        """
        if not self.security.is_admin(event):
            await event.send(event.plain_result("权限不足。"))
            return

        session, final_task, empty_message = await self._prepare_oc_execution(
            event,
            task_description,
            empty_message="请输入任务、发送图片或引用消息。",
        )
        if not final_task:
            await event.send(event.plain_result(empty_message))
            return

        timeout = (
            self._get_runtime_config()
            .get("basic_config", {})
            .get("confirm_timeout", 30)
        )
        approved, reason = await self._check_and_confirm_destructive(
            event,
            final_task,
            timeout,
            prompt_text=f"⚠️ AI 请求敏感操作：'{final_task}'\n回复'确认执行'批准 ({timeout}s)",
            confirm_text="确认执行",
            timeout_text="超时拒绝",
            reject_text="拒绝执行",
        )
        if not approved:
            if reason == "file_write_blocked":
                await event.send(event.plain_result("❌ 当前已禁止文件写入操作"))
                return

        async for _ in self._start_oc_execution(
            event,
            session,
            final_task,
            background=True,
            emit_status=True,
        ):
            pass

        # 不 yield 任何内容，框架会认为工具已自行处理，AI 不再额外回复

    async def _execute_opencode_background(
        self,
        umo: str,
        prompt_payload: Any,
        session,
        event: AstrMessageEvent,
    ):
        """后台执行 OpenCode 任务并主动推送结果"""
        from astrbot.api.event import MessageChain

        try:
            async for payload in self._run_oc_prompt(
                event, session, prompt_payload, emit_status=False
            ):
                message_chain = MessageChain()
                if isinstance(payload, list):
                    for comp in payload:
                        message_chain.chain.append(comp)
                else:
                    message_chain.message(str(payload))
                await self.context.send_message(umo, message_chain)
        except Exception as e:
            self.logger.error(f"OpenCode 后台执行失败: {e}")
            try:
                await self.context.send_message(
                    umo, MessageChain().message(f"❌ OpenCode 执行失败: {e}")
                )
            except Exception as send_err:
                self.logger.error(f"发送错误消息失败: {send_err}")
