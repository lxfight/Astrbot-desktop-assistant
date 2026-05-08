import json
import socket
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from desktop_client.config import ClientConfig
from desktop_client.pet_runtime.api import PetRuntimeApiServer
from desktop_client.pet_runtime.animation import (
    PET_ANIMATIONS,
    action_frame_sequence,
    animation_duration_ms,
    frame_index_for_animation,
)
from desktop_client.pet_runtime.catalog import BUILTIN_PETS_DIR, PetCatalog
from desktop_client.pet_runtime.window import JUMP_REPEAT_COUNT, PetRuntimeWindow
from desktop_client.pet_runtime.state import EVENT_ACTION_MAP, PetAction, PetEventType, RuntimeState


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json_request(url: str, payload: dict | None = None):
    if payload is None:
        with urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class TestPetCatalog:
    @pytest.mark.unit
    def test_bundled_taotao_package_loads(self):
        catalog = PetCatalog()
        pet = catalog.default_pet("taotao")

        assert pet.id == "taotao"
        assert pet.display_name == "桃桃"
        assert pet.manifest_path.name == "pet.json"
        assert pet.spritesheet_path.name == "spritesheet.webp"
        assert pet.spritesheet_path.exists()
        assert pet.package_dir == BUILTIN_PETS_DIR / "taotao"
        assert "animations" not in pet.manifest

    @pytest.mark.unit
    def test_bundled_taotao_release_files_exist(self):
        package_dir = BUILTIN_PETS_DIR / "taotao"

        assert (package_dir / "pet.json").is_file()
        assert (package_dir / "spritesheet.webp").is_file()
        assert (package_dir / "spritesheet.webp").stat().st_size > 0

    @pytest.mark.unit
    def test_import_local_package(self, tmp_path: Path):
        catalog = PetCatalog(user_dir=tmp_path / "pets")

        imported = catalog.import_local(BUILTIN_PETS_DIR / "taotao")

        assert imported.id == "taotao"
        assert imported.spritesheet_path.exists()
        assert (tmp_path / "pets" / "taotao" / "pet.json").exists()


class TestPetRuntimeApi:
    @pytest.mark.unit
    def test_status_action_say_event_and_spritesheet(self, tmp_path: Path):
        catalog = PetCatalog(user_dir=tmp_path / "pets")
        state = RuntimeState(current_pet_id="taotao")
        port = _free_port()
        server = PetRuntimeApiServer("127.0.0.1", port, state, catalog)
        server.start()
        base_url = f"http://127.0.0.1:{port}"

        try:
            status = _json_request(f"{base_url}/api/status")
            assert status["currentPetId"] == "taotao"
            assert status["currentAction"] == "idle"
            assert status["pet"]["id"] == "taotao"

            action = _json_request(
                f"{base_url}/api/action", {"animationId": "waving"}
            )
            assert action["currentAction"] == "waving"

            say = _json_request(
                f"{base_url}/api/say", {"text": "Thinking...", "ttlMs": 1000}
            )
            assert say["bubbleText"] == "Thinking..."

            event = _json_request(
                f"{base_url}/api/event",
                {"type": "failure", "message": "Tests failed", "ttlMs": 1000},
            )
            assert event["lastEventType"] == "failure"
            assert event["currentAction"] == "idle"

            with urlopen(f"{base_url}/api/pets/taotao/spritesheet", timeout=5) as response:
                assert response.headers["Content-Type"] == "image/webp"
                assert len(response.read(16)) > 0
        finally:
            server.stop()


class TestPetRuntimeAnimation:
    @pytest.mark.unit
    def test_openpet_animation_table_matches_codex_runtime(self):
        assert PET_ANIMATIONS["idle"].row == 0
        assert PET_ANIMATIONS["idle"].frame_count == 6
        assert animation_duration_ms("idle") == 9600
        assert PET_ANIMATIONS["waiting"].row == 6
        assert PET_ANIMATIONS["running"].row == 7
        assert PET_ANIMATIONS["review"].row == 8

    @pytest.mark.unit
    def test_event_action_map_matches_desktop_pet_interactions(self):
        assert EVENT_ACTION_MAP[PetEventType.THINKING] == PetAction.JUMPING
        assert EVENT_ACTION_MAP[PetEventType.TOOL_RUNNING] == "idle"
        assert EVENT_ACTION_MAP[PetEventType.REVIEWING] == "idle"
        assert EVENT_ACTION_MAP[PetEventType.SUCCESS] == "idle"
        assert EVENT_ACTION_MAP[PetEventType.FAILURE] == "idle"
        assert EVENT_ACTION_MAP[PetEventType.ATTENTION] == "idle"

    @pytest.mark.unit
    def test_idle_sequence_uses_fixed_openpet_row_without_blank_cells(self):
        assert action_frame_sequence("idle", rows=9, cols=8) == [0, 1, 2, 3, 4, 5]
        assert action_frame_sequence(PetAction.WAVING.value, rows=9, cols=8) == [
            24,
            25,
            26,
            27,
        ]

    @pytest.mark.unit
    def test_frame_index_uses_per_frame_durations(self):
        assert frame_index_for_animation("idle", 0) == 0
        assert frame_index_for_animation("idle", 2399) == 0
        assert frame_index_for_animation("idle", 2400) == 1
        assert frame_index_for_animation("idle", 3299) == 1
        assert frame_index_for_animation("idle", 3300) == 2
        assert frame_index_for_animation("idle", 9600) == 0

    @pytest.mark.unit
    def test_window_hover_and_thinking_jump_three_times(self):
        app = QApplication.instance() or QApplication([])
        config = ClientConfig()
        config.pet_runtime.api_enabled = False
        window = PetRuntimeWindow(config=config)

        try:
            window.enterEvent(QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
            assert window._state.current_action == PetAction.JUMPING.value
            assert window._transient_action_until > 0

            duration = window._transient_action_until - window._action_started_at
            assert duration == pytest.approx(
                animation_duration_ms(PetAction.JUMPING.value)
                * JUMP_REPEAT_COUNT
                / 1000,
                rel=0.05,
            )

            window._transient_action_until = 1
            window._advance_frame()
            assert window._state.current_action == "idle"

            window.emit_event(PetEventType.THINKING.value)
            assert window._state.current_action == PetAction.JUMPING.value
            assert window._state.bubble_text == ""
        finally:
            window.close()

    @pytest.mark.unit
    def test_window_drag_uses_directional_running_and_release_returns_idle(self):
        app = QApplication.instance() or QApplication([])
        config = ClientConfig()
        config.pet_runtime.api_enabled = False
        window = PetRuntimeWindow(config=config)

        try:
            press_pos = QPointF(100, 100)
            press = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                press_pos,
                press_pos,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.mousePressEvent(press)

            move_pos = QPointF(120, 100)
            move = QMouseEvent(
                QEvent.Type.MouseMove,
                move_pos,
                move_pos,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.mouseMoveEvent(move)
            assert window._state.current_action == "running-right"

            move_left_pos = QPointF(80, 100)
            move_left = QMouseEvent(
                QEvent.Type.MouseMove,
                move_left_pos,
                move_left_pos,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.mouseMoveEvent(move_left)
            assert window._state.current_action == "running-left"

            release = QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                move_left_pos,
                move_left_pos,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.mouseReleaseEvent(release)
            assert window._state.current_action == "idle"
        finally:
            window.close()

    @pytest.mark.unit
    def test_api_event_message_keeps_event_action(self, tmp_path: Path):
        catalog = PetCatalog(user_dir=tmp_path / "pets")
        state = RuntimeState(current_pet_id="taotao")
        actions: list[str] = []
        says: list[str] = []
        events: list[str] = []
        port = _free_port()
        server = PetRuntimeApiServer(
            "127.0.0.1",
            port,
            state,
            catalog,
            on_action=actions.append,
            on_say=lambda text, ttl_ms: says.append(text),
            on_event=lambda event_type, message, ttl_ms: events.append(event_type),
        )
        server.start()

        try:
            response = _json_request(
                f"http://127.0.0.1:{port}/api/event",
                {"type": "failure", "message": "Tests failed", "ttlMs": 1000},
            )

            assert response["currentAction"] == "idle"
            assert actions == []
            assert says == []
            assert events == ["failure"]
        finally:
            server.stop()

    @pytest.mark.unit
    def test_rejects_unsupported_action(self, tmp_path: Path):
        catalog = PetCatalog(user_dir=tmp_path / "pets")
        state = RuntimeState(current_pet_id="taotao")
        port = _free_port()
        server = PetRuntimeApiServer("127.0.0.1", port, state, catalog)
        server.start()

        try:
            with pytest.raises(HTTPError) as exc:
                _json_request(
                    f"http://127.0.0.1:{port}/api/action",
                    {"animationId": "nope"},
                )
            assert exc.value.code == 400
        finally:
            server.stop()
