from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from desktop_client.handlers.media_handler import MediaHandler


class FakeFloatingBall:
    def __init__(self):
        self.calls = []

    def show_bubble(
        self,
        content: str,
        duration: int = 0,
        msg_type: str = "text",
        metadata=None,
    ):
        self.calls.append(("bubble", content, msg_type, metadata))

    def show_input(self):
        self.calls.append(("show_input",))

    def set_unread_message(self, value: bool = True):
        self.calls.append(("unread", value))

    def is_waiting_response(self) -> bool:
        return False


class TestMediaHandler:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_download_file_response_uses_floating_ball_proxy(
        self, sample_config, tmp_path
    ):
        floating_ball = FakeFloatingBall()

        async def fake_download(filename: str, save_path: str) -> bool:
            with open(save_path, "wb") as f:
                f.write(b"demo")
            return True

        bridge = SimpleNamespace(
            api_client=SimpleNamespace(download_file=AsyncMock(side_effect=fake_download))
        )

        handler = MediaHandler(
            config=sample_config,
            bridge=bridge,
            floating_ball=floating_ball,
            chat_history_manager=MagicMock(),
        )
        handler.set_storage_dirs(
            {
                "image": str(tmp_path / "images"),
                "voice": str(tmp_path / "voices"),
                "video": str(tmp_path / "videos"),
                "file": str(tmp_path / "files"),
            }
        )

        for path in handler._storage_dirs.values():
            Path(path).mkdir(parents=True, exist_ok=True)

        await handler._download_media(
            "document.pdf",
            "file",
            metadata={"request_id": "req_1"},
            should_silent=False,
        )

        expected_path = str(tmp_path / "files" / "document.pdf")
        expected_content = f"{expected_path}|document.pdf|4"

        assert ("bubble", expected_content, "file", {"request_id": "req_1"}) in floating_ball.calls
        assert ("show_input",) in floating_ball.calls

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_download_media_prefers_attachment_id_from_metadata(
        self, sample_config, tmp_path
    ):
        floating_ball = FakeFloatingBall()

        async def fake_download(download_name: str, save_path: str) -> bool:
            assert download_name == "att_123"
            with open(save_path, "wb") as f:
                f.write(b"image")
            return True

        bridge = SimpleNamespace(
            api_client=SimpleNamespace(download_file=AsyncMock(side_effect=fake_download))
        )
        handler = MediaHandler(
            config=sample_config,
            bridge=bridge,
            floating_ball=floating_ball,
            chat_history_manager=MagicMock(),
        )
        handler.set_storage_dirs(
            {
                "image": str(tmp_path / "images"),
                "voice": str(tmp_path / "voices"),
                "video": str(tmp_path / "videos"),
                "file": str(tmp_path / "files"),
            }
        )
        for path in handler._storage_dirs.values():
            Path(path).mkdir(parents=True, exist_ok=True)

        await handler._download_media(
            "image_123.jpg",
            "image",
            metadata={"attachment_id": "att_123"},
            should_silent=False,
        )

        expected_path = str(tmp_path / "images" / "image_123.jpg")
        assert ("bubble", expected_path, "image", {"attachment_id": "att_123"}) in floating_ball.calls
