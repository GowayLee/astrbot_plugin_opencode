"""
输出处理模块
"""

import asyncio
import html
import os
import random
import re
import time
from typing import Any, List, Callable, Awaitable, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Node, Plain, Image, File, Nodes

from .acp_models import ACPNormalizedEvent
from .session import OpenCodeSession
from .utils import write_text_file_sync


# ANSI 颜色码到 CSS 颜色的映射
ANSI_COLORS = {
    # 标准前景色 (30-37)
    "30": "#000000",  # 黑色
    "31": "#cd3131",  # 红色
    "32": "#0dbc79",  # 绿色
    "33": "#e5e510",  # 黄色
    "34": "#2472c8",  # 蓝色
    "35": "#bc3fbc",  # 洋红
    "36": "#11a8cd",  # 青色
    "37": "#e5e5e5",  # 白色
    # 亮色前景 (90-97)
    "90": "#666666",  # 亮黑（灰）
    "91": "#f14c4c",  # 亮红
    "92": "#23d18b",  # 亮绿
    "93": "#f5f543",  # 亮黄
    "94": "#3b8eea",  # 亮蓝
    "95": "#d670d6",  # 亮洋红
    "96": "#29b8db",  # 亮青
    "97": "#ffffff",  # 亮白
}


def ansi_to_html(text: str) -> str:
    """将 ANSI 转义码转换为 HTML span 标签，保留颜色信息。

    支持的格式：
    - ESC[Xm 单个属性
    - ESC[X;Y;Zm 多个属性组合
    - ESC[0m 重置

    不支持的 ANSI 码会被静默移除，确保不会破坏 HTML 渲染。
    """
    # 先对文本进行 HTML 转义，防止特殊字符破坏渲染
    # 但要保留 ANSI 转义码，所以先用占位符替换
    ansi_pattern = re.compile(r"\x1B\[[0-9;]*m")

    # 提取所有 ANSI 码并用占位符替换
    ansi_codes = []

    def save_ansi(match):
        ansi_codes.append(match.group(0))
        return f"\x00ANSI{len(ansi_codes) - 1}\x00"

    text_with_placeholders = ansi_pattern.sub(save_ansi, text)

    # HTML 转义
    safe_text = html.escape(text_with_placeholders)

    # 恢复 ANSI 码占位符
    for i, code in enumerate(ansi_codes):
        safe_text = safe_text.replace(f"\x00ANSI{i}\x00", code)

    # 现在处理 ANSI 码转换为 HTML
    result = []
    current_color = None
    last_end = 0

    for match in ansi_pattern.finditer(safe_text):
        # 添加匹配前的文本
        result.append(safe_text[last_end : match.start()])

        # 解析 ANSI 码
        codes_str = match.group(0)[2:-1]  # 去掉 ESC[ 和 m

        if not codes_str or codes_str == "0":
            # 重置：关闭当前 span
            if current_color:
                result.append("</span>")
                current_color = None
        else:
            # 解析颜色码
            codes = codes_str.split(";")
            new_color = None
            for code in codes:
                if code in ANSI_COLORS:
                    new_color = ANSI_COLORS[code]
                    break

            if new_color and new_color != current_color:
                # 关闭旧的 span，打开新的
                if current_color:
                    result.append("</span>")
                result.append(f'<span style="color:{new_color}">')
                current_color = new_color

        last_end = match.end()

    # 添加剩余文本
    result.append(safe_text[last_end:])

    # 确保所有 span 都关闭
    if current_color:
        result.append("</span>")

    return "".join(result)


class OutputProcessor:
    """输出处理器 - 负责处理和格式化输出"""

    STANDARD_PERMISSION_OPTION_IDS = {
        "allow_once",
        "allow_always",
        "reject_once",
        "reject_always",
        "cancelled",
    }

    def __init__(self, config: dict, base_data_dir: str):
        self.config = config
        self.base_data_dir = base_data_dir
        self.logger = logger
        # html_render 方法由外部注入
        self._html_render: Optional[Callable[[str, dict], Awaitable[str]]] = None
        # context.llm_generate 方法由外部注入
        self._llm_generate: Optional[Callable] = None
        # context.get_current_chat_provider_id 方法由外部注入
        self._get_provider_id: Optional[Callable] = None
        # 模板目录（用于长图渲染）
        self._template_dir: Optional[str] = None

    def set_html_render(self, html_render_func):
        """设置 HTML 渲染函数"""
        self._html_render = html_render_func

    def set_llm_functions(self, llm_generate, get_provider_id):
        """设置 LLM 相关函数"""
        self._llm_generate = llm_generate
        self._get_provider_id = get_provider_id

    def set_template_dir(self, template_dir: str):
        """设置模板目录"""
        self._template_dir = template_dir

    def normalize_acp_event(
        self, event: ACPNormalizedEvent | dict[str, Any]
    ) -> ACPNormalizedEvent:
        """将原始 ACP update 统一成聊天层消费的内部事件。"""
        if isinstance(event, ACPNormalizedEvent):
            return event

        payload = dict(event or {})
        event_type = str(payload.get("type") or payload.get("event_type") or "").strip()
        title = str(
            payload.get("title")
            or payload.get("tool_name")
            or payload.get("toolTitle")
            or payload.get("name")
            or ""
        ).strip()
        detail = str(payload.get("detail") or payload.get("message") or "").strip()
        if not detail:
            detail = str(payload.get("text") or payload.get("chunk") or "").strip()
        session_id = payload.get("sessionId") or payload.get("session_id")

        return ACPNormalizedEvent(
            event_type=event_type,
            session_id=None if session_id is None else str(session_id),
            title=title,
            detail=detail,
            data=payload,
        )

    def build_chat_updates(
        self,
        events: list[ACPNormalizedEvent | dict[str, Any]],
        session: Optional[OpenCodeSession] = None,
    ) -> list[str]:
        """将 ACP 事件折叠成聊天侧简洁进度提示。"""
        updates: list[str] = []
        chunk_parts: list[str] = []

        def flush_chunks() -> None:
            if not chunk_parts:
                return
            updates.append("".join(chunk_parts))
            chunk_parts.clear()

        for item in events:
            event = self.normalize_acp_event(item)
            if event.event_type == "message_chunk":
                chunk_text = self._extract_message_chunk_text(event)
                if chunk_text:
                    chunk_parts.append(chunk_text)
                continue

            flush_chunks()
            message = self._build_chat_update(event, session)
            if message:
                updates.append(message)

        flush_chunks()
        return updates

    def _build_chat_update(
        self, event: ACPNormalizedEvent, session: Optional[OpenCodeSession] = None
    ) -> str:
        event_type = event.event_type

        if event_type == "run_started":
            if session:
                session.prompt_running = True
            return "🚀 开始执行任务"

        if event_type == "plan_updated":
            summary = (
                event.detail or event.title or self._extract_plan_summary(event.data)
            )
            return f"📝 计划更新: {summary}" if summary else "📝 计划已更新"

        if event_type == "tool_started":
            return self._format_tool_update("🛠️", event)

        if event_type == "tool_updated":
            return self._format_tool_update("🔄", event)

        if event_type == "permission_requested":
            permission_payload = self._extract_permission_payload(event)
            if session:
                session.set_pending_permission(permission_payload)
            return self._format_permission_update(permission_payload)

        if event_type == "config_updated":
            summary = event.detail or event.title or "配置已更新"
            return f"⚙️ {summary}"

        if event_type == "mode_updated":
            summary = event.detail or event.title or "模式已更新"
            return f"🎛️ {summary}"

        if event_type == "run_finished":
            if session:
                session.prompt_running = False
                session.clear_pending_permission()
            stop_reason = str(
                event.data.get("stopReason")
                or event.data.get("stop_reason")
                or "end_turn"
            )
            if stop_reason == "cancelled":
                return "🛑 本轮任务已取消"
            if stop_reason == "refusal":
                return "🚫 当前请求被拒绝"
            return "✅ 执行完成"

        if event_type == "run_failed":
            if session:
                session.prompt_running = False
                session.clear_pending_permission()
            summary = (
                event.detail or event.title or event.data.get("message") or "执行失败"
            )
            return f"❌ {summary}"

        return ""

    async def build_final_result_plan(
        self,
        result: Any,
        event: AstrMessageEvent,
        session: Optional[OpenCodeSession] = None,
    ) -> List[List]:
        """将最终 stop reason 映射为聊天输出，并复用既有输出积木链路。"""
        event_updates = self.build_chat_updates(
            self._extract_embedded_events(result),
            session=session,
        )
        prefix_plan = self._build_update_plan(event_updates)
        stop_reason = getattr(result, "stop_reason", None) or getattr(
            result, "error_type", None
        )
        final_text = getattr(result, "final_text", "") or ""
        message = getattr(result, "message", "") or ""
        streamed_text = self._extract_streamed_text(
            result, self._extract_embedded_events(result)
        )
        live_stream_used = bool(
            getattr(result, "payload", {}).get("_astrbot_live_stream")
            if isinstance(getattr(result, "payload", None), dict)
            else False
        )

        self._finalize_terminal_session_state(session, stop_reason)

        if stop_reason == "cancelled":
            return prefix_plan + [[Plain("🛑 本轮任务已取消")]]

        if stop_reason == "refusal":
            if final_text.strip():
                return prefix_plan + await self.parse_output_plan(
                    final_text, event, session
                )
            return prefix_plan + [[Plain("🚫 当前请求被拒绝")]]

        if final_text.strip():
            if self._texts_equivalent(final_text, streamed_text):
                if prefix_plan:
                    return prefix_plan
                if live_stream_used:
                    return []
                return [[Plain("✅ 执行完成")]]
            return prefix_plan + await self.parse_output_plan(
                final_text, event, session
            )

        if message.strip():
            return prefix_plan + [[Plain(message.strip())]]

        if prefix_plan:
            return prefix_plan

        return [[Plain("OpenCode 执行完毕，无输出。")]]

    def _format_tool_update(self, prefix: str, event: ACPNormalizedEvent) -> str:
        title = event.title or "工具执行"
        detail = event.detail or self._extract_tool_detail(event.data)
        return f"{prefix} {title}: {detail}" if detail else f"{prefix} {title}"

    def _extract_message_chunk_text(self, event: ACPNormalizedEvent) -> str:
        payload = event.data
        for key in ("text", "chunk", "content", "delta", "detail", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return event.detail or ""

    def _extract_plan_summary(self, payload: dict[str, Any]) -> str:
        plan = payload.get("plan") or payload.get("steps") or []
        if isinstance(plan, list) and plan:
            first = plan[0]
            if isinstance(first, dict):
                return str(first.get("title") or first.get("text") or "").strip()
            return str(first).strip()
        return ""

    def _extract_tool_detail(self, payload: dict[str, Any]) -> str:
        for key in ("detail", "path", "command", "summary", "message"):
            value = payload.get(key)
            if value:
                return str(value).strip()
        return ""

    def _extract_permission_payload(self, event: ACPNormalizedEvent) -> dict[str, Any]:
        payload = dict(event.data)
        normalized_options = []
        for index, option in enumerate(payload.get("options") or [], start=1):
            if not isinstance(option, dict):
                continue
            option_id = (
                option.get("optionId") or option.get("option_id") or option.get("id")
            )
            label = (
                option.get("label") or option.get("name") or option_id or f"选项{index}"
            )
            normalized_options.append(
                {
                    "optionId": "" if option_id is None else str(option_id),
                    "label": str(label),
                    "index": index,
                    "display": self._format_permission_option_display(option_id, label),
                }
            )

        return {
            "requestId": payload.get("requestId")
            or payload.get("request_id")
            or payload.get("id"),
            "toolName": payload.get("tool_name")
            or payload.get("toolName")
            or event.title
            or "未知工具",
            "toolKind": payload.get("tool_kind")
            or payload.get("toolKind")
            or payload.get("kind")
            or "",
            "arguments": dict(payload.get("arguments") or {}),
            "options": normalized_options,
        }

    def _format_permission_update(self, permission_payload: dict[str, Any]) -> str:
        tool_name = str(permission_payload.get("toolName") or "未知工具")
        tool_kind = str(permission_payload.get("toolKind") or "")
        arguments = permission_payload.get("arguments") or {}
        detail = self._extract_tool_detail(arguments)
        options = permission_payload.get("options") or []
        action_text = f"{tool_name} ({tool_kind})" if tool_kind else tool_name
        lines = [
            "⚠️ 权限确认",
            f"操作: {action_text}",
            f"目标: {detail or '未提供'}",
        ]
        for item in options:
            display = str(item.get("display") or "").strip()
            index = item.get("index")
            if display and index is not None:
                lines.append(f"{index}. {display}")
        return "\n".join(lines)

    def _extract_embedded_events(self, result: Any) -> list[Any]:
        payload = getattr(result, "payload", {}) or {}
        if isinstance(payload, dict):
            for key in ("events", "updates", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return list(value)

        items = getattr(result, "items", None)
        if isinstance(items, list):
            return list(items)

        return []

    def _extract_streamed_text(self, result: Any, embedded_events: list[Any]) -> str:
        payload = getattr(result, "payload", {}) or {}
        if isinstance(payload, dict):
            streamed_text = payload.get("_astrbot_streamed_text")
            if isinstance(streamed_text, str) and streamed_text:
                return streamed_text

        text_parts: list[str] = []
        for item in embedded_events:
            event = self.normalize_acp_event(item)
            if event.event_type != "message_chunk":
                continue
            chunk_text = self._extract_message_chunk_text(event)
            if chunk_text:
                text_parts.append(chunk_text)
        return "".join(text_parts)

    def _texts_equivalent(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        return left.strip() == right.strip()

    def _build_update_plan(self, updates: list[str]) -> List[List]:
        if not updates:
            return []
        return [[Plain("\n".join(updates))]]

    def _finalize_terminal_session_state(
        self, session: Optional[OpenCodeSession], stop_reason: Any
    ) -> None:
        if not session:
            return
        if stop_reason is None:
            return
        session.prompt_running = False
        session.clear_pending_permission()

    def _format_permission_option_display(self, option_id: Any, label: Any) -> str:
        option_id_text = "" if option_id is None else str(option_id).strip()
        label_text = "" if label is None else str(label).strip()
        if option_id_text and option_id_text not in self.STANDARD_PERMISSION_OPTION_IDS:
            if label_text:
                return f"{option_id_text} + {label_text}"
            return option_id_text
        return label_text or option_id_text

    def next_send_delay(self) -> float:
        """获取逐条发送时的随机间隔，降低风控风险。"""
        return random.uniform(0.7, 1.3)

    @staticmethod
    def _should_show_mode(
        mode: str,
        output_modes: list,
        is_long: bool,
        smart_trigger_enabled: bool,
    ) -> bool:
        """统一判断积木是否应当出现。"""
        if mode not in output_modes:
            return False
        if smart_trigger_enabled:
            return is_long
        return True

    async def render_long_image(self, text: str) -> Optional[str]:
        """渲染长图"""
        if not self._template_dir or not self._html_render:
            self.logger.error("模板目录或 HTML 渲染函数未设置")
            return None

        template_path = os.path.join(self._template_dir, "assets", "long_text.html")
        if not os.path.exists(template_path):
            self.logger.error(f"Template file not found: {template_path}")
            return None

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()

            # 将 ANSI 颜色码转换为 HTML，同时转义其他特殊字符
            html_content = ansi_to_html(text)
            result = await self._html_render(template, {"content": html_content})
            return result
        except Exception as e:
            self.logger.error(f"模板渲染失败: {e}")
            return None

    async def parse_output_plan(
        self, output: Any, event: AstrMessageEvent, session: OpenCodeSession = None
    ) -> List[List]:
        """解析输出并构造发送计划（每个元素代表一次消息发送的组件列表）。"""
        if self._looks_like_execution_result(output):
            return await self.build_final_result_plan(output, event, session)

        output_config = self.config.get("output_config", {})
        output_modes = output_config.get("output_modes", ["full_text", "txt_file"])
        max_length = output_config.get("max_text_length", 1000)
        merge_forward_enabled = output_config.get("merge_forward_enabled", True)
        smart_trigger_ai_summary = output_config.get("smart_trigger_ai_summary", True)
        smart_trigger_txt_file = output_config.get("smart_trigger_txt_file", True)
        smart_trigger_long_image = output_config.get("smart_trigger_long_image", True)

        # 兼容性处理
        if "forward_msg" in output_modes:
            if "full_text" not in output_modes:
                output_modes.append("full_text")
            output_modes = [m for m in output_modes if m != "forward_msg"]

        # 修复 re.error: bad character range @-?
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_text = ansi_escape.sub("", str(output))

        # 统一处理文本换行
        text_lines = []
        if clean_text.strip():
            for line in clean_text.splitlines():
                text_lines.append(line)
        final_text = "\n".join(text_lines).strip()

        if not final_text:
            return [Plain("OpenCode 执行完毕，无输出。")]

        is_long = len(final_text) > max_length

        # === 1. 准备各个积木的数据 ===
        blocks = {}

        # (1) AI Summary
        if self._should_show_mode(
            "ai_summary", output_modes, is_long, smart_trigger_ai_summary
        ):
            try:
                umo = event.unified_msg_origin
                provider_id = await self._get_provider_id(umo=umo)
                prompt = f"请简要总结以下命令行输出的关键结果（成功/失败/核心报错），去除冗余信息，用一两句话概括：\n\n{final_text[:2000]}..."
                llm_resp = await self._llm_generate(
                    chat_provider_id=provider_id, prompt=prompt
                )
                if llm_resp:
                    blocks["ai_summary"] = Plain(
                        f"🤖 AI 摘要: {llm_resp.completion_text}"
                    )
            except Exception:
                blocks["ai_summary"] = Plain("AI 摘要生成失败。")

        # (2) Long Image
        if self._should_show_mode(
            "long_image", output_modes, is_long, smart_trigger_long_image
        ):
            try:
                img_url = await self.render_long_image(final_text)
                if img_url:
                    blocks["long_image"] = Image.fromURL(img_url)
            except Exception as e:
                self.logger.error(f"长图渲染失败: {e}")

        # (3) TXT File
        if self._should_show_mode(
            "txt_file", output_modes, is_long, smart_trigger_txt_file
        ):
            log_dir = self.base_data_dir
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"opencode_output_{int(time.time())}.txt")
            try:
                await asyncio.to_thread(write_text_file_sync, log_path, clean_text)
                # 使用绝对路径，并按照官方文档格式：File(file=路径, name=文件名)
                abs_log_path = os.path.abspath(log_path)
                blocks["txt_file"] = File(
                    file=abs_log_path, name=os.path.basename(log_path)
                )
            except OSError as e:
                self.logger.warning(f"日志文件写入失败: {e}")

        # (4) Last Line (Truncated Text)
        if "last_line" in output_modes:
            if len(final_text) > max_length:
                tail = final_text[-max_length:]
                omitted_count = len(final_text) - max_length
                display_text = f"...(前略 {omitted_count} 字符)\n{tail}"
                blocks["last_line"] = Plain(display_text)
            else:
                blocks["last_line"] = Plain(final_text)

        # (5) Full Text (Splitted)
        if "full_text" in output_modes:
            chunk_size = max_length if max_length > 0 else 1000
            if len(final_text) <= chunk_size:
                blocks["full_text"] = [Plain(final_text)]
            else:
                chunks = []
                for i in range(0, len(final_text), chunk_size):
                    chunks.append(Plain(final_text[i : i + chunk_size]))
                blocks["full_text"] = chunks

        # === 2. 调度逻辑 ===
        valid_block_keys = [k for k in blocks.keys() if blocks[k]]
        count = len(valid_block_keys)
        ordered_keys = [
            "ai_summary",
            "last_line",
            "txt_file",
            "long_image",
            "full_text",
        ]

        # 辅助函数：构造合并转发节点
        def make_node(content_list):
            uin = event.get_self_id()
            name = "OpenCode"
            return Node(uin=uin, name=name, content=content_list)

        # Case A: merge 开启，沿用原有的合并转发主路径
        if merge_forward_enabled and count > 1:
            forward_nodes = Nodes([])

            for key in ordered_keys:
                if key not in blocks:
                    continue
                if key == "full_text":
                    for p in blocks["full_text"]:
                        forward_nodes.nodes.append(make_node([p]))
                else:
                    forward_nodes.nodes.append(make_node([blocks[key]]))

            return [[forward_nodes]]

        # Case B: merge 开启 + 只有一个积木
        if merge_forward_enabled and count == 1:
            key = valid_block_keys[0]
            content = blocks[key]

            if key in ["ai_summary", "long_image", "txt_file"]:
                return [[content]]

            elif key == "last_line":
                return [[content]]

            elif key == "full_text":
                if len(content) == 1:
                    return [[content[0]]]
                else:
                    forward_nodes = Nodes([])
                    for p in content:
                        forward_nodes.nodes.append(make_node([p]))
                    return [[forward_nodes]]

        # Case C: merge 关闭 -> 顺序逐条发；full_text 单独一次合并转发
        if not merge_forward_enabled:
            send_plan: List[List] = []

            for key in ordered_keys:
                if key not in blocks or key == "full_text":
                    continue
                send_plan.append([blocks[key]])

            if "full_text" in blocks:
                forward_nodes = Nodes([])
                for p in blocks["full_text"]:
                    forward_nodes.nodes.append(make_node([p]))
                send_plan.append([forward_nodes])

            if send_plan:
                return send_plan

        # Case D: 兜底
        return [[Plain("执行完成 (无符合条件的输出)。")]]

    async def parse_output(
        self, output: Any, event: AstrMessageEvent, session: OpenCodeSession = None
    ) -> List:
        """兼容接口：返回发送计划中的第一条消息组件。"""
        send_plan = await self.parse_output_plan(output, event, session)
        if not send_plan:
            return [Plain("执行完成 (无符合条件的输出)。")]
        return send_plan[0]

    def _looks_like_execution_result(self, output: Any) -> bool:
        return hasattr(output, "stop_reason") and hasattr(output, "final_text")
