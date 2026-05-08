"""
消息处理器

负责处理从服务器接收到的各类消息，包括：
- 文本消息（流式/非流式）
- 图片、语音、视频消息
- 结束标记和错误消息
"""

import logging
import time
from typing import TYPE_CHECKING, Optional, Any

from PySide6.QtCore import QObject, Slot

if TYPE_CHECKING:
    from ..bridge import OutputMessage
    from ..config import ClientConfig

logger = logging.getLogger(__name__)


class MessageHandler(QObject):
    """消息处理器 - 处理接收到的消息"""

    def __init__(
        self,
        config: "ClientConfig",
        floating_ball: Optional[Any] = None,
        media_handler: Optional[Any] = None,
        chat_history_manager: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ):
        """
        初始化消息处理器

        Args:
            config: 客户端配置
            floating_ball: 悬浮球窗口实例
            media_handler: 媒体处理器实例
            chat_history_manager: 聊天记录管理器
            parent: 父对象
        """
        super().__init__(parent)
        self._config = config
        self._floating_ball = floating_ball
        self._media_handler = media_handler
        self._chat_history_manager = chat_history_manager

        # 主动对话响应状态
        self._proactive_dialog_pending = False

        # 静默响应缓冲区
        self._silent_response_buffer = ""
        self._streaming_response_buffer = ""
        self._silent_response_metadata: dict = {}
        self._streaming_response_metadata: dict = {}
        self._active_response_request_id: Optional[str] = None
        self._last_status_notice: tuple[str, float] = ("", 0.0)
        self._status_notice_cooldown = 10.0

    def set_floating_ball(self, floating_ball: Any) -> None:
        """设置悬浮球实例"""
        self._floating_ball = floating_ball

    def set_media_handler(self, media_handler: Any) -> None:
        """设置媒体处理器"""
        self._media_handler = media_handler

    def set_chat_history_manager(self, manager: Any) -> None:
        """设置聊天记录管理器"""
        self._chat_history_manager = manager

    def set_proactive_pending(self, pending: bool) -> None:
        """设置主动对话等待状态"""
        self._proactive_dialog_pending = pending

    def is_proactive_pending(self) -> bool:
        """获取主动对话等待状态"""
        return self._proactive_dialog_pending

    @Slot(object)
    def handle_output_message(self, message: "OutputMessage") -> None:
        """
        处理接收到的消息 (Slot)

        Args:
            message: 输出消息对象
        """
        msg_type = message.msg_type
        content = message.content

        # 检查是否是主动对话的响应
        is_proactive_response = self._proactive_dialog_pending

        # 检查免打扰模式
        do_not_disturb = self._config.interaction.do_not_disturb

        # 判断是否需要静默处理（免打扰模式）
        should_silent = do_not_disturb

        if msg_type == "text":
            self._handle_text_message(
                content,
                message.streaming,
                is_proactive_response,
                should_silent,
                do_not_disturb,
                message.metadata,
            )

        elif msg_type == "image":
            # AI 返回的图片
            if self._media_handler:
                self._media_handler.handle_image_response(
                    content, message.metadata, should_silent
                )

        elif msg_type == "voice":
            # AI 返回的语音
            if self._media_handler:
                self._media_handler.handle_voice_response(
                    content, message.metadata, should_silent
                )

        elif msg_type == "video":
            # AI 返回的视频
            if self._media_handler:
                self._media_handler.handle_video_response(
                    content, message.metadata, should_silent
                )

        elif msg_type == "file":
            if self._media_handler:
                self._media_handler.handle_file_response(
                    content, message.metadata, should_silent
                )

        elif msg_type == "end":
            self._handle_end_message(is_proactive_response, should_silent)

        elif msg_type == "status":
            self._handle_status_message(content)

        elif msg_type == "error":
            self._handle_error_message(content, is_proactive_response, should_silent)

        elif msg_type == "saved":
            self._handle_saved_message(message.metadata)

    def _handle_status_message(self, content: str) -> None:
        """处理状态消息（连接状态变更）"""
        if not self._floating_ball:
            return

        from ..api_client import ConnectionState
        from ..gui.floating_ball import FloatingBallState

        # content 是 ConnectionState 的 value
        if content == ConnectionState.DISCONNECTED.value:
            self._floating_ball.set_state(FloatingBallState.DISCONNECTED)
            self._show_status_notice_once("❌ 与服务器断开连接")
        elif content == ConnectionState.CONNECTED.value:
            self._floating_ball.set_state(FloatingBallState.NORMAL)
            self._show_status_notice_once("✅ 已连接到服务器")
        elif content == ConnectionState.CONNECTING.value:
            # 连接中，暂不处理，保持当前状态或显示加载动画
            pass
        elif content == ConnectionState.ERROR.value:
            self._floating_ball.set_state(FloatingBallState.DISCONNECTED)

    def _show_status_notice_once(self, text: str) -> None:
        now = time.monotonic()
        last_text, last_time = self._last_status_notice
        if text == last_text and now - last_time < self._status_notice_cooldown:
            return
        self._last_status_notice = (text, now)
        self._floating_ball.show_system_message(text)

    def _handle_text_message(
        self,
        content: str,
        streaming: bool,
        is_proactive_response: bool,
        should_silent: bool,
        do_not_disturb: bool,
        message_metadata: Optional[dict] = None,
    ) -> None:
        """处理文本消息"""
        # 忽略空消息
        if not content:
            return

        # 过滤掉语音消息的冗余文本提示
        if content.strip() in ["[收到语音]", "🔊 [收到语音]"]:
            return

        if not (is_proactive_response or should_silent):
            self._ensure_response_request_scope(message_metadata)

        # 主动对话响应或静默模式：静默处理，不弹窗
        if is_proactive_response or should_silent:
            if streaming:
                # 流式响应时累积内容
                self._silent_response_buffer += content
                self._silent_response_metadata = self._merge_message_metadata(
                    self._silent_response_metadata, message_metadata
                )
            else:
                # 非流式完整响应：静默添加到历史记录，不显示气泡
                if self._chat_history_manager:
                    self._chat_history_manager.add_message(
                        role="assistant",
                        content=content,
                        msg_type="text",
                        metadata=message_metadata,
                    )
                # 仅设置未读消息标记（显示动画效果）
                if self._floating_ball:
                    self._floating_ball.set_unread_message(True)
                if is_proactive_response:
                    self._proactive_dialog_pending = False
                self._silent_response_metadata = {}
            return

        if streaming:
            # 流式响应
            self._streaming_response_buffer += content
            self._streaming_response_metadata = self._merge_message_metadata(
                self._streaming_response_metadata, message_metadata
            )
            if self._floating_ball:
                self._floating_ball.update_streaming_response(
                    content, metadata=message_metadata
                )

        else:
            # 完整响应（非流式）
            if self._floating_ball:
                if self._has_active_response():
                    combined_metadata = self._merge_message_metadata(
                        self._streaming_response_metadata, message_metadata
                    )
                    self._floating_ball.update_streaming_response(
                        content, metadata=combined_metadata
                    )
                    self._floating_ball.finish_response()
                    if not self._is_chat_window_visible():
                        self._floating_ball.set_unread_message(True)
                else:
                    self._floating_ball.show_bubble(content, metadata=message_metadata)
            else:
                # 没有 UI 实例，直接写入历史
                if self._chat_history_manager:
                    combined_metadata = self._merge_message_metadata(
                        self._streaming_response_metadata, message_metadata
                    )
                    full_content = (
                        self._streaming_response_buffer + content
                        if self._streaming_response_buffer
                        else content
                    )
                    self._chat_history_manager.add_message(
                        role="assistant",
                        content=full_content,
                        msg_type="text",
                        metadata=combined_metadata,
                    )

            self._streaming_response_buffer = ""
            self._streaming_response_metadata = {}
            self._active_response_request_id = None

    def _handle_end_message(
        self, is_proactive_response: bool, should_silent: bool
    ) -> None:
        """处理结束消息"""
        # 主动对话响应或静默模式结束
        if is_proactive_response or should_silent:
            # 静默添加累积的响应内容到历史记录，不显示气泡
            buffer = self._silent_response_buffer
            if buffer and self._chat_history_manager:
                self._chat_history_manager.add_message(
                    role="assistant",
                    content=buffer,
                    msg_type="text",
                    metadata=self._silent_response_metadata,
                )
                # 仅设置未读消息标记（显示动画效果）
                if self._floating_ball:
                    self._floating_ball.set_unread_message(True)

            # 如果是用户等待中（但被静默了），需要重置等待状态
            if self._floating_ball and self._has_active_response():
                self._floating_ball.finish_response()

            # 清理状态
            if is_proactive_response:
                self._proactive_dialog_pending = False
            self._silent_response_buffer = ""
            self._silent_response_metadata = {}
            return

        if self._floating_ball and self._has_active_response():
            self._floating_ball.finish_response()
            if not self._is_chat_window_visible():
                self._floating_ball.set_unread_message(True)
        elif self._streaming_response_buffer and self._chat_history_manager:
            self._chat_history_manager.add_message(
                role="assistant",
                content=self._streaming_response_buffer,
                msg_type="text",
                metadata=self._streaming_response_metadata,
            )

        self._streaming_response_buffer = ""
        self._streaming_response_metadata = {}
        self._active_response_request_id = None

    def _handle_error_message(
        self, content: str, is_proactive_response: bool, should_silent: bool
    ) -> None:
        """处理错误消息"""
        # 主动对话或静默模式错误
        if is_proactive_response or should_silent:
            logger.error(f"静默模式响应错误: {content}")
            if is_proactive_response:
                self._proactive_dialog_pending = False
            self._silent_response_buffer = ""
            self._streaming_response_buffer = ""
            self._silent_response_metadata = {}
            self._streaming_response_metadata = {}
            self._active_response_request_id = None

            # 如果是用户等待中（但被静默了），需要重置等待状态
            if self._floating_ball and self._has_active_response():
                self._floating_ball.finish_response()

            # 静默模式下错误也只显示未读标记
            if self._floating_ball:
                self._floating_ball.set_unread_message(True)
            return

        self._streaming_response_buffer = ""
        self._streaming_response_metadata = {}
        self._active_response_request_id = None

        if self._floating_ball:
            # 如果气泡输入框在等待，也需要结束等待并显示错误
            if self._has_active_response():
                self._floating_ball.update_streaming_response(f"❌ {content}")
                self._floating_ball.finish_response()
                if not self._is_chat_window_visible():
                    self._floating_ball.set_unread_message(True)
            else:
                self._floating_ball.show_bubble(f"❌ {content}")
        elif self._chat_history_manager:
            self._chat_history_manager.add_message(
                role="assistant", content=f"❌ {content}", msg_type="text"
            )

    def _handle_saved_message(self, metadata: Optional[dict]) -> None:
        """记录服务端保存后的消息元数据。"""
        if not metadata or not self._chat_history_manager:
            return

        getter = getattr(self._chat_history_manager, "get_messages", None)
        updater = getattr(self._chat_history_manager, "update_message_metadata", None)
        saver = getattr(self._chat_history_manager, "save_to_file", None)
        if not callable(getter) or not callable(updater):
            return

        server_message_id = metadata.get("message_id")
        server_created_at = metadata.get("created_at")
        request_id = metadata.get("request_id")

        if not any((server_message_id, server_created_at, request_id)):
            return

        target_message_id = None

        try:
            for msg in reversed(getter()):
                if getattr(msg, "role", None) != "assistant":
                    continue

                current_metadata = getattr(msg, "metadata", None)
                if not isinstance(current_metadata, dict):
                    current_metadata = {}

                if request_id and current_metadata.get("request_id") != request_id:
                    continue

                target_message_id = getattr(msg, "id", None)
                break

            if not target_message_id and not request_id:
                for msg in reversed(getter()):
                    if getattr(msg, "role", None) == "assistant":
                        target_message_id = getattr(msg, "id", None)
                        break

            if not target_message_id:
                logger.debug(
                    "未找到可绑定的服务端消息元数据: request_id=%s, server_message_id=%s",
                    request_id,
                    server_message_id,
                )
                return

            updated = updater(
                target_message_id,
                {
                    key: value
                    for key, value in {
                        "server_message_id": server_message_id,
                        "server_created_at": server_created_at,
                        "request_id": request_id,
                    }.items()
                    if value
                },
            )
            if updated and callable(saver):
                saver()

            logger.debug(
                "已记录服务端消息元数据: message_id=%s, server_message_id=%s, request_id=%s",
                target_message_id,
                server_message_id,
                request_id,
            )
        except Exception as e:
            logger.debug(f"记录服务端消息元数据失败: {e}")

    @staticmethod
    def _merge_message_metadata(
        current_metadata: Optional[dict], incoming_metadata: Optional[dict]
    ) -> dict:
        """合并消息元数据，保留已有字段。"""
        merged = dict(current_metadata or {})
        if incoming_metadata:
            merged.update(incoming_metadata)
        return merged

    def _ensure_response_request_scope(
        self, message_metadata: Optional[dict]
    ) -> None:
        """避免缺失结束事件时将新请求继续写入旧气泡。"""
        request_id = self._get_request_id(message_metadata)
        if not request_id:
            return

        if (
            self._active_response_request_id
            and self._active_response_request_id != request_id
        ):
            if self._floating_ball and self._has_active_response():
                self._floating_ball.finish_response()
            self._streaming_response_buffer = ""
            self._streaming_response_metadata = {}

        self._active_response_request_id = request_id

    @staticmethod
    def _get_request_id(message_metadata: Optional[dict]) -> Optional[str]:
        if not isinstance(message_metadata, dict):
            return None
        request_id = message_metadata.get("request_id")
        return str(request_id) if request_id else None

    def _has_active_response(self) -> bool:
        """检查当前是否有未收尾的前台响应。"""
        if not self._floating_ball:
            return False
        checker = getattr(self._floating_ball, "has_active_response", None)
        if callable(checker):
            return bool(checker())
        return False

    def _is_chat_window_visible(self) -> bool:
        """检查聊天窗口当前是否可见。"""
        if not self._floating_ball:
            return False
        checker = getattr(self._floating_ball, "is_chat_window_visible", None)
        if callable(checker):
            return bool(checker())
        return False
