from unittest.mock import AsyncMock, MagicMock

import pytest

from desktop_client.app import DesktopClientApp
from desktop_client.config import ClientConfig


class TestDesktopClientApp:
    @pytest.mark.unit
    def test_on_screenshot_captured_forwards_path_to_handler(self):
        app = DesktopClientApp.__new__(DesktopClientApp)
        app._screenshot_handler = MagicMock()

        DesktopClientApp._on_screenshot_captured(app, "C:/tmp/region.png")

        app._screenshot_handler.add_screenshot_to_chat.assert_called_once_with(
            "C:/tmp/region.png"
        )

    @pytest.mark.unit
    def test_on_screenshot_captured_ignores_empty_path(self):
        app = DesktopClientApp.__new__(DesktopClientApp)
        app._screenshot_handler = MagicMock()

        DesktopClientApp._on_screenshot_captured(app, "")

        app._screenshot_handler.add_screenshot_to_chat.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_start_websocket_skips_when_remote_control_disabled(self):
        app = DesktopClientApp.__new__(DesktopClientApp)
        app.config = ClientConfig()
        app.config.server.enable_remote_control = False
        app._bridge = MagicMock()

        await DesktopClientApp._start_websocket_connection(app)

        app._bridge.api_client.start_websocket.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_start_websocket_skips_in_openapi_mode(self):
        app = DesktopClientApp.__new__(DesktopClientApp)
        app.config = ClientConfig()
        app.config.server.enable_remote_control = True
        app.config.server.auth_mode = "openapi"
        app._bridge = MagicMock()

        await DesktopClientApp._start_websocket_connection(app)

        app._bridge.api_client.start_websocket.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reconnect_server_skips_websocket_in_openapi_mode(self):
        app = DesktopClientApp.__new__(DesktopClientApp)
        app.config = ClientConfig()
        app.config.server.enable_remote_control = True
        app.config.server.auth_mode = "openapi"
        app.config.proactive.enabled = False
        app._bridge = MagicMock()
        app._bridge.connect_server = AsyncMock(return_value=(True, "OpenAPI 连接成功"))
        app._bridge.api_client = MagicMock()
        app._bridge.api_client.start_websocket = AsyncMock()
        app._floating_ball = None
        app._proactive_service = None

        await DesktopClientApp._reconnect_server(app)

        app._bridge.connect_server.assert_awaited_once()
        app._bridge.api_client.start_websocket.assert_not_called()
