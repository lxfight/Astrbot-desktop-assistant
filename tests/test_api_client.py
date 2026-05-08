import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from desktop_client.api_client import AstrBotApiClient


class _FakeSseResponse:
    def __init__(self, status_code: int = 200, lines: list[str] | None = None):
        self.status_code = status_code
        self._lines = lines or []

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeSseContext:
    def __init__(self, response: _FakeSseResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestAstrBotApiClientOpenApiMode:
    @pytest.mark.unit
    def test_openapi_headers_prefer_api_key(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
            token="legacy_token",
        )

        headers = client._get_headers()

        assert client.uses_openapi is True
        assert headers["Authorization"] == "Bearer abk_test"

    @pytest.mark.unit
    def test_legacy_headers_use_token_when_forced(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            api_key="abk_test",
            auth_mode="legacy",
            token="legacy_token",
        )

        headers = client._get_headers()

        assert client.uses_openapi is False
        assert headers["Authorization"] == "Bearer legacy_token"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_openapi_check_connection_uses_username(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = MagicMock(status_code=200)
        response.json.return_value = {"status": "ok", "data": {"sessions": []}}
        http_client = MagicMock()
        http_client.get = AsyncMock(return_value=response)
        client._ensure_client = AsyncMock(return_value=http_client)

        ok = await client.check_connection()

        assert ok is True
        assert client.state.name == "CONNECTED"
        http_client.get.assert_awaited_once()
        _, kwargs = http_client.get.call_args
        assert kwargs["params"] == {"username": "alice", "page": 1, "page_size": 1}
        assert kwargs["headers"]["Authorization"] == "Bearer abk_test"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_openapi_create_session_is_local_uuid(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )

        success, session_id = await client.create_session()

        assert success is True
        assert session_id.startswith("desktop_")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_openapi_upload_file_hits_v1_endpoint(self, tmp_path: Path):
        file_path = tmp_path / "demo.png"
        file_path.write_bytes(b"fake image bytes")

        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "status": "ok",
            "data": {"attachment_id": "att_123", "filename": "demo.png"},
        }
        http_client = MagicMock()
        http_client.post = AsyncMock(return_value=response)
        client._ensure_client = AsyncMock(return_value=http_client)

        success, payload = await client.upload_file(str(file_path))

        assert success is True
        assert payload["attachment_id"] == "att_123"
        http_client.post.assert_awaited_once()
        args, kwargs = http_client.post.call_args
        assert args[0] == "http://localhost:6185/api/v1/file"
        assert kwargs["headers"]["Authorization"] == "Bearer abk_test"
        assert kwargs["files"]["file"][0] == "demo.png"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_openapi_download_file_uses_v1_attachment_endpoint(self, tmp_path: Path):
        save_path = tmp_path / "downloaded.jpg"
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = MagicMock(status_code=200)
        response.content = b"image-bytes"
        http_client = MagicMock()
        http_client.get = AsyncMock(return_value=response)
        client._ensure_client = AsyncMock(return_value=http_client)

        success = await client.download_file("attachment_123", str(save_path))

        assert success is True
        assert save_path.read_bytes() == b"image-bytes"
        http_client.get.assert_awaited_once()
        args, kwargs = http_client.get.call_args
        assert args[0] == "http://localhost:6185/api/v1/file"
        assert kwargs["params"] == {"attachment_id": "attachment_123"}

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_openapi_send_message_hits_v1_chat_and_injects_username(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = _FakeSseResponse(
            200,
            [
                'data: {"type":"plain","data":{"text":"hello"},"streaming":true}',
                'data: {"type":"end","data":"","streaming":false}',
            ],
        )
        http_client = MagicMock()
        http_client.stream = MagicMock(return_value=_FakeSseContext(response))
        http_client.aclose = AsyncMock()
        client._create_sse_client = MagicMock(return_value=http_client)

        events = []
        async for event in client.send_message("session_001", "hi"):
            events.append(event)

        assert [event.event_type for event in events] == ["plain", "end"]
        assert json.loads(events[0].data) == {"text": "hello"}
        args, kwargs = http_client.stream.call_args
        assert args == ("POST", "http://localhost:6185/api/v1/chat")
        assert kwargs["headers"]["Authorization"] == "Bearer abk_test"
        assert kwargs["json"]["username"] == "alice"
        assert kwargs["json"]["session_id"] == "session_001"
        http_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_openapi_send_message_omits_blank_session_id(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = _FakeSseResponse(200, ['data: {"type":"end","data":"","streaming":false}'])
        http_client = MagicMock()
        http_client.stream = MagicMock(return_value=_FakeSseContext(response))
        http_client.aclose = AsyncMock()
        client._create_sse_client = MagicMock(return_value=http_client)

        events = []
        async for event in client.send_message("", "hi"):
            events.append(event)

        assert [event.event_type for event in events] == ["end"]
        _, kwargs = http_client.stream.call_args
        assert kwargs["json"]["username"] == "alice"
        assert "session_id" not in kwargs["json"]
        http_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_message_accepts_data_without_space_and_done_marker(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = _FakeSseResponse(
            200,
            [
                ": heartbeat",
                'data:{"type":"plain","data":"hello","streaming":true}',
                "data: [DONE]",
            ],
        )
        http_client = MagicMock()
        http_client.stream = MagicMock(return_value=_FakeSseContext(response))
        http_client.aclose = AsyncMock()
        client._create_sse_client = MagicMock(return_value=http_client)

        events = []
        async for event in client.send_message("session_001", "hi"):
            events.append(event)

        assert [event.event_type for event in events] == ["plain", "end"]
        assert events[0].data == "hello"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_message_adds_end_when_stream_closes_without_terminal_event(self):
        client = AstrBotApiClient(
            "http://localhost:6185",
            username="alice",
            api_key="abk_test",
        )
        response = _FakeSseResponse(
            200,
            ['data: {"type":"plain","data":"hello","streaming":true}'],
        )
        http_client = MagicMock()
        http_client.stream = MagicMock(return_value=_FakeSseContext(response))
        http_client.aclose = AsyncMock()
        client._create_sse_client = MagicMock(return_value=http_client)

        events = []
        async for event in client.send_message("session_001", "hi"):
            events.append(event)

        assert [event.event_type for event in events] == ["plain", "end"]


class TestAstrBotApiClientSSEDataNormalization:
    @pytest.mark.unit
    def test_normalize_sse_data_value_keeps_structured_json(self):
        raw_data = {"id": "call_123", "name": "search", "args": {"q": "hello"}}

        normalized = AstrBotApiClient._normalize_sse_data_value(raw_data)

        assert json.loads(normalized) == raw_data

    @pytest.mark.unit
    def test_normalize_sse_data_value_handles_plain_string(self):
        normalized = AstrBotApiClient._normalize_sse_data_value("hello")

        assert normalized == "hello"
