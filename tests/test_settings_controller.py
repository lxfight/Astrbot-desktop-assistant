from unittest.mock import MagicMock

import pytest

from desktop_client.controllers.settings_controller import SettingsController


class TestSettingsController:
    @pytest.mark.unit
    def test_server_settings_without_modification_do_not_trigger_reconnect(
        self, sample_config
    ):
        bridge = MagicMock()
        controller = SettingsController(config=sample_config, bridge=bridge)

        result = controller._update_server_settings(
            {
                "url": sample_config.server.url,
                "username": sample_config.server.username,
                "password": sample_config.server.password,
                "api_key": sample_config.server.api_key,
                "auth_mode": sample_config.server.auth_mode,
                "ws_url": sample_config.server.ws_url,
                "enable_remote_control": sample_config.server.enable_remote_control,
                "enable_streaming": sample_config.server.enable_streaming,
                "url_modified": False,
                "username_modified": False,
                "password_modified": False,
                "api_key_modified": False,
                "auth_mode_modified": False,
                "ws_url_modified": False,
                "enable_remote_control_modified": False,
            }
        )

        assert result is False
        bridge.update_server_config.assert_not_called()

    @pytest.mark.unit
    def test_blank_password_without_user_edit_keeps_existing_password(
        self, sample_config
    ):
        bridge = MagicMock()
        controller = SettingsController(config=sample_config, bridge=bridge)

        result = controller._update_server_settings(
            {
                "url": sample_config.server.url,
                "username": sample_config.server.username,
                "password": "",
                "api_key": sample_config.server.api_key,
                "auth_mode": sample_config.server.auth_mode,
                "ws_url": sample_config.server.ws_url,
                "enable_remote_control": sample_config.server.enable_remote_control,
                "enable_streaming": sample_config.server.enable_streaming,
                "url_modified": False,
                "username_modified": False,
                "password_modified": False,
                "api_key_modified": False,
                "auth_mode_modified": False,
                "ws_url_modified": False,
                "enable_remote_control_modified": False,
            }
        )

        assert result is False
        assert sample_config.server.password == "test_password"
        bridge.update_server_config.assert_not_called()

    @pytest.mark.unit
    def test_modified_server_url_triggers_reconnect_with_new_values(
        self, sample_config
    ):
        bridge = MagicMock()
        sample_config.server.url = "http://real-server:6185"
        controller = SettingsController(config=sample_config, bridge=bridge)

        result = controller._update_server_settings(
            {
                "url": "http://real-server:6185",
                "username": sample_config.server.username,
                "password": sample_config.server.password,
                "api_key": sample_config.server.api_key,
                "auth_mode": sample_config.server.auth_mode,
                "ws_url": sample_config.server.ws_url,
                "enable_remote_control": sample_config.server.enable_remote_control,
                "enable_streaming": sample_config.server.enable_streaming,
                "url_modified": True,
                "username_modified": False,
                "password_modified": False,
                "api_key_modified": False,
                "auth_mode_modified": False,
                "ws_url_modified": False,
                "enable_remote_control_modified": False,
            }
        )

        assert result is True
        bridge.update_server_config.assert_called_once_with(
            url="http://real-server:6185",
            username=sample_config.server.username,
            password=sample_config.server.password,
            api_key=sample_config.server.api_key,
            auth_mode=sample_config.server.auth_mode,
            ws_url=sample_config.server.ws_url,
            enable_remote_control=sample_config.server.enable_remote_control,
        )

    @pytest.mark.unit
    def test_api_key_change_triggers_reconnect(self, sample_config):
        bridge = MagicMock()
        controller = SettingsController(config=sample_config, bridge=bridge)

        result = controller._update_server_settings(
            {
                "api_key": "abk_new",
                "api_key_modified": True,
            }
        )

        assert result is True
        assert sample_config.server.api_key == "abk_new"
        bridge.update_server_config.assert_called_once()

    @pytest.mark.unit
    def test_pet_runtime_settings_update_config_and_window(self, sample_config):
        floating_ball = MagicMock()
        controller = SettingsController(
            config=sample_config,
            floating_ball=floating_ball,
        )

        controller._update_pet_runtime_settings(
            {
                "enabled": True,
                "display_mode": "pet",
                "current_pet_id": "taotao",
                "window_scale": 1.2,
                "always_on_top": False,
            }
        )

        assert sample_config.pet_runtime.display_mode == "pet"
        assert sample_config.pet_runtime.current_pet_id == "taotao"
        assert sample_config.pet_runtime.window_scale == 1.2
        assert sample_config.pet_runtime.always_on_top is False
        floating_ball.update_pet_runtime_config.assert_called_once_with(sample_config)

    @pytest.mark.unit
    def test_pet_runtime_ball_mode_prompts_restart(self, sample_config):
        floating_ball = MagicMock()
        controller = SettingsController(
            config=sample_config,
            floating_ball=floating_ball,
        )

        controller._update_pet_runtime_settings({"display_mode": "ball"})

        assert sample_config.pet_runtime.display_mode == "ball"
        floating_ball.show_system_message.assert_called_once_with(
            "桌面形象切换将在重启后生效"
        )
