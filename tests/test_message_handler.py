from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from desktop_client.bridge import OutputMessage
from desktop_client.handlers.message_handler import MessageHandler


class FakeFloatingBall:
    def __init__(self, *, visible: bool = False, active: bool = False):
        self.visible = visible
        self.active = active
        self.calls = []

    def update_streaming_response(self, content: str, metadata=None):
        self.calls.append(("stream", content, metadata))
        self.active = True

    def finish_response(self):
        self.calls.append(("finish",))
        self.active = False

    def show_bubble(
        self, content: str, duration: int = 0, msg_type: str = "text", metadata=None
    ):
        self.calls.append(("bubble", content, msg_type, metadata))

    def set_unread_message(self, value: bool = True):
        self.calls.append(("unread", value))

    def set_state(self, state):
        self.calls.append(("state", state))

    def show_system_message(self, text: str):
        self.calls.append(("system", text))

    def has_active_response(self) -> bool:
        return self.active

    def is_chat_window_visible(self) -> bool:
        return self.visible

    def is_waiting_response(self) -> bool:
        return False


class TestMessageHandler:
    @pytest.mark.unit
    def test_duplicate_status_notice_is_throttled(self, sample_config):
        floating_ball = FakeFloatingBall()
        handler = MessageHandler(config=sample_config, floating_ball=floating_ball)

        handler._show_status_notice_once("❌ 与服务器断开连接")
        with patch(
            "desktop_client.handlers.message_handler.time.monotonic",
            return_value=5.0,
        ):
            handler._show_status_notice_once("❌ 与服务器断开连接")

        assert floating_ball.calls.count(("system", "❌ 与服务器断开连接")) == 1

    @pytest.mark.unit
    def test_streaming_text_updates_even_when_chat_window_hidden(self, sample_config):
        floating_ball = FakeFloatingBall(visible=False, active=False)
        handler = MessageHandler(
            config=sample_config,
            floating_ball=floating_ball,
            chat_history_manager=MagicMock(),
        )

        handler.handle_output_message(
            OutputMessage(
                msg_type="text",
                content="流式片段",
                session_id="session_123",
                streaming=True,
            )
        )

        assert ("stream", "流式片段", {}) in floating_ball.calls

    @pytest.mark.unit
    def test_new_request_finishes_stale_active_response(self, sample_config):
        floating_ball = FakeFloatingBall(visible=True, active=False)
        handler = MessageHandler(
            config=sample_config,
            floating_ball=floating_ball,
            chat_history_manager=MagicMock(),
        )

        handler.handle_output_message(
            OutputMessage(
                msg_type="text",
                content="第一段",
                session_id="session_123",
                streaming=True,
                metadata={"request_id": "req_1"},
            )
        )
        handler.handle_output_message(
            OutputMessage(
                msg_type="text",
                content="第二段",
                session_id="session_123",
                streaming=True,
                metadata={"request_id": "req_2"},
            )
        )

        assert floating_ball.calls == [
            ("stream", "第一段", {"request_id": "req_1"}),
            ("finish",),
            ("stream", "第二段", {"request_id": "req_2"}),
        ]

    @pytest.mark.unit
    def test_end_message_finishes_active_response_and_marks_unread_when_hidden(
        self, sample_config
    ):
        floating_ball = FakeFloatingBall(visible=False, active=True)
        handler = MessageHandler(
            config=sample_config,
            floating_ball=floating_ball,
            chat_history_manager=MagicMock(),
        )

        handler.handle_output_message(
            OutputMessage(msg_type="end", content="", session_id="session_123")
        )

        assert ("finish",) in floating_ball.calls
        assert ("unread", True) in floating_ball.calls

    @pytest.mark.unit
    def test_non_streaming_text_shows_full_content_instead_of_summary(
        self, sample_config
    ):
        floating_ball = FakeFloatingBall(visible=False, active=False)
        handler = MessageHandler(
            config=sample_config,
            floating_ball=floating_ball,
            chat_history_manager=MagicMock(),
        )
        long_content = "A" * 150

        handler.handle_output_message(
            OutputMessage(
                msg_type="text",
                content=long_content,
                session_id="session_123",
                streaming=False,
            )
        )

        assert ("bubble", long_content, "text", {}) in floating_ball.calls

    @pytest.mark.unit
    def test_streaming_text_without_floating_ball_falls_back_to_history(
        self, sample_config
    ):
        history_manager = MagicMock()
        handler = MessageHandler(
            config=sample_config,
            floating_ball=None,
            chat_history_manager=history_manager,
        )

        handler.handle_output_message(
            OutputMessage(
                msg_type="text",
                content="Hello",
                session_id="session_123",
                streaming=True,
            )
        )
        handler.handle_output_message(
            OutputMessage(msg_type="end", content="", session_id="session_123")
        )

        history_manager.add_message.assert_called_once_with(
            role="assistant",
            content="Hello",
            msg_type="text",
            metadata={},
        )

    @pytest.mark.unit
    def test_file_message_delegates_to_media_handler(self, sample_config):
        media_handler = MagicMock()
        handler = MessageHandler(
            config=sample_config,
            floating_ball=FakeFloatingBall(),
            media_handler=media_handler,
            chat_history_manager=MagicMock(),
        )

        message = OutputMessage(
            msg_type="file",
            content="document.pdf",
            session_id="session_123",
            metadata={"source": "sse"},
        )

        handler.handle_output_message(message)

        media_handler.handle_file_response.assert_called_once_with(
            "document.pdf",
            {"source": "sse"},
            False,
        )

    @pytest.mark.unit
    def test_saved_message_updates_matching_assistant_metadata(self, sample_config):
        assistant_message = SimpleNamespace(
            id="assistant_1", role="assistant", metadata={"request_id": "req_1"}
        )
        newer_assistant_message = SimpleNamespace(
            id="assistant_2", role="assistant", metadata={"request_id": "req_2"}
        )
        history_manager = MagicMock()
        history_manager.get_messages.return_value = [
            SimpleNamespace(role="user", metadata={}),
            assistant_message,
            newer_assistant_message,
        ]

        handler = MessageHandler(
            config=sample_config,
            floating_ball=FakeFloatingBall(),
            chat_history_manager=history_manager,
        )

        handler.handle_output_message(
            OutputMessage(
                msg_type="saved",
                content="",
                session_id="session_123",
                metadata={
                    "message_id": "srv_msg_1",
                    "created_at": "2024-01-01T00:00:00Z",
                    "request_id": "req_1",
                },
            )
        )

        history_manager.update_message_metadata.assert_called_once_with(
            "assistant_1",
            {
                "server_message_id": "srv_msg_1",
                "server_created_at": "2024-01-01T00:00:00Z",
                "request_id": "req_1",
            },
        )
        history_manager.save_to_file.assert_called_once_with()

    @pytest.mark.unit
    def test_streaming_text_without_floating_ball_preserves_request_id_metadata(
        self, sample_config
    ):
        history_manager = MagicMock()
        handler = MessageHandler(
            config=sample_config,
            floating_ball=None,
            chat_history_manager=history_manager,
        )

        handler.handle_output_message(
            OutputMessage(
                msg_type="text",
                content="Hello",
                session_id="session_123",
                streaming=True,
                metadata={"request_id": "req_1"},
            )
        )
        handler.handle_output_message(
            OutputMessage(msg_type="end", content="", session_id="session_123")
        )

        history_manager.add_message.assert_called_once_with(
            role="assistant",
            content="Hello",
            msg_type="text",
            metadata={"request_id": "req_1"},
        )
