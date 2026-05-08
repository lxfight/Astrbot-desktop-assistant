"""PySide6 pet window that replaces the legacy floating ball by default."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from ..config import ClientConfig
from ..gui.floating_ball import CompactChatWindow
from ..gui.icons import icon_manager
from ..gui.themes import theme_manager
from .animation import (
    ANIMATION_TIMER_MS,
    IDLE_ANIMATION_ID,
    action_frame_sequence,
    animation_duration_ms,
    frame_index_for_animation,
    is_animation_id,
    is_public_action_id,
)
from .api import PetRuntimeApiServer
from .catalog import PetCatalog
from .state import EVENT_ACTION_MAP, PetAction, PetEventType, RuntimeState

JUMP_REPEAT_COUNT = 3
HOVER_ACTION_COOLDOWN_MS = 900
DRAG_DIRECTION_THRESHOLD_PX = 2


class PetRuntimeWindow(QWidget):
    """Transparent desktop pet window with legacy FloatingBall-compatible methods."""

    clicked = Signal()
    double_clicked = Signal()
    settings_requested = Signal()
    restart_requested = Signal()
    quit_requested = Signal()
    screenshot_requested = Signal(str)
    message_sent = Signal(str)
    image_sent = Signal(str, str)
    _api_action_requested = Signal(str)
    _api_say_requested = Signal(str, object)
    _api_event_requested = Signal(str, str, object)
    _api_import_requested = Signal(str)

    def __init__(self, config: Optional[ClientConfig] = None, parent=None):
        super().__init__(parent)
        self.config = config or ClientConfig()
        self.pet_config = self.config.pet_runtime

        user_dir = Path(self.pet_config.resolved_pet_packages_dir)
        self._catalog = PetCatalog(user_dir=user_dir)
        self._state = RuntimeState(current_pet_id=self.pet_config.current_pet_id)
        self._pet = self._catalog.default_pet(self.pet_config.current_pet_id)
        self._state.current_pet_id = self._pet.id

        self._sprite = QPixmap(str(self._pet.spritesheet_path))
        self._action_started_at = time.monotonic()
        self._base_action = IDLE_ANIMATION_ID
        self._transient_action_until = 0.0
        self._has_unread = False
        self._dragging = False
        self._hovered = False
        self._drag_start_pos = QPoint()
        self._press_global_pos = QPoint()
        self._last_drag_global_pos = QPoint()
        self._has_moved_significantly = False
        self._last_hover_action_at = 0.0
        self._last_release_time = 0
        self._pending_click = False
        self._drag_threshold = 5
        self._double_click_interval = 300

        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_single_click)

        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._advance_frame)
        self._animation_timer.start(ANIMATION_TIMER_MS)

        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.pet_config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self._window_size(), self._window_size())

        self._compact_window = CompactChatWindow(config=self.config)
        self._compact_window.message_sent.connect(self.message_sent)
        self._compact_window.image_sent.connect(self.image_sent)
        self._compact_window.window_moved.connect(self._on_compact_window_moved)
        self._compact_window.window_resized.connect(self._on_compact_window_resized)
        self._apply_chat_assets()
        self._api_action_requested.connect(self.perform_action)
        self._api_say_requested.connect(
            lambda text, ttl_ms: self.show_bubble(text, duration=ttl_ms or 0)
        )
        self._api_event_requested.connect(self.emit_event)
        self._api_import_requested.connect(self.load_pet)

        self._api_server: Optional[PetRuntimeApiServer] = None
        if self.pet_config.api_enabled:
            self._api_server = PetRuntimeApiServer(
                host=self.pet_config.listen_host,
                port=self.pet_config.listen_port,
                state=self._state,
                catalog=self._catalog,
                on_action=self._on_api_action,
                on_say=self._on_api_say,
                on_event=self._on_api_event,
                on_import=self._on_api_import,
            )
            try:
                self._api_server.start()
            except OSError as e:
                self._state.last_error = str(e)

        self._move_to_default_position()

    def closeEvent(self, event):  # noqa: N802
        if self._api_server:
            self._api_server.stop()
        super().closeEvent(event)

    def _window_size(self) -> int:
        return max(96, int(180 * float(self.pet_config.window_scale)))

    def _apply_chat_assets(self) -> None:
        appearance = self.config.appearance
        if appearance.user_avatar_path:
            self._compact_window.set_user_avatar(appearance.user_avatar_path)
        if appearance.bot_avatar_path:
            self._compact_window.set_bot_avatar(appearance.bot_avatar_path)
        elif appearance.avatar_path:
            self._compact_window.set_bot_avatar(appearance.avatar_path)
        if appearance.background_image_path:
            self._compact_window.set_background_config(
                appearance.background_image_path,
                appearance.background_opacity,
                appearance.background_blur,
            )
        self._compact_window.set_auto_hide(
            self.config.interaction.bubble_auto_hide,
            self.config.interaction.bubble_duration * 1000,
        )

    def _move_to_default_position(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        x = geometry.right() - self.width() - 40
        y = geometry.center().y() - self.height() // 2
        self.move(x, y)

    def _advance_frame(self) -> None:
        self._state.clear_bubble_if_expired()
        if self._state.bubble_expires_at == 0 and not self._state.bubble_text:
            self._hide_bubble_only_if_empty()
        now = time.monotonic()
        if self._transient_action_until and now >= self._transient_action_until:
            self._transient_action_until = 0.0
            self._set_animation(self._base_action, publish_action=False)
        self.update()

    def _grid_size(self) -> tuple[int, int]:
        if self._sprite.isNull():
            return (1, 1)
        width = self._sprite.width()
        height = self._sprite.height()
        if width % 8 == 0 and height % 9 == 0:
            return (8, 9)
        if width % 8 == 0:
            return (8, max(1, height // (width // 8)))
        return (1, 1)

    def _frame_size(self) -> tuple[int, int]:
        if self._sprite.isNull():
            return (self.width(), self.height())
        cols, rows = self._grid_size()
        return (self._sprite.width() // cols, self._sprite.height() // rows)

    def _action_frames(self) -> list[int]:
        cols, rows = self._grid_size()
        return action_frame_sequence(
            self._state.current_action,
            rows=rows,
            cols=cols,
        )

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._sprite.isNull():
            self._paint_fallback(painter)
            return

        frame_width, frame_height = self._frame_size()
        cols, _rows = self._grid_size()
        frame = self._mapped_frame_index()
        source_x = (frame % cols) * frame_width
        source_y = (frame // cols) * frame_height
        target_margin = 4
        target_size = min(self.width(), self.height()) - target_margin * 2

        painter.drawPixmap(
            target_margin,
            target_margin,
            target_size,
            target_size,
            self._sprite,
            source_x,
            source_y,
            frame_width,
            frame_height,
        )

    def _paint_fallback(self, painter: QPainter) -> None:
        icon_size = min(self.width(), self.height()) - 24
        pixmap = icon_manager.get_pixmap("bot", "#FFFFFF", icon_size)
        painter.drawPixmap((self.width() - icon_size) // 2, 12, pixmap)

    def _mapped_frame_index(self) -> int:
        cols, rows = self._grid_size()
        elapsed_ms = int((time.monotonic() - self._action_started_at) * 1000)
        return frame_index_for_animation(
            self._state.current_action,
            elapsed_ms,
            rows=rows,
            cols=cols,
        )

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.pos()
            self._press_global_pos = event.globalPosition().toPoint()
            self._last_drag_global_pos = self._press_global_pos
            self._has_moved_significantly = False
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        if self._dragging:
            current = event.globalPosition().toPoint()
            delta_x = current.x() - self._last_drag_global_pos.x()
            if not self._has_moved_significantly:
                distance = (current - self._press_global_pos).manhattanLength()
                self._has_moved_significantly = distance > self._drag_threshold
            if abs(delta_x) >= DRAG_DIRECTION_THRESHOLD_PX:
                self._set_animation(
                    "running-right" if delta_x > 0 else "running-left",
                    publish_action=False,
                )
            self._last_drag_global_pos = current
            self.move(current - self._drag_start_pos)
            if self._compact_window.isVisible():
                self._update_compact_window_position()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = False
        self._set_animation(IDLE_ANIMATION_ID, publish_action=False)
        if not self._has_moved_significantly:
            from PySide6.QtCore import QDateTime

            now = QDateTime.currentMSecsSinceEpoch()
            if now - self._last_release_time < self._double_click_interval:
                self._click_timer.stop()
                self._pending_click = False
            else:
                self._pending_click = True
                self._click_timer.start(self._double_click_interval)
            self._last_release_time = now
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self._pending_click = False
            self.perform_action(PetAction.JUMPING.value, repeat=JUMP_REPEAT_COUNT)
            self.double_clicked.emit()
            event.accept()

    def enterEvent(self, event):  # noqa: N802
        self._hovered = True
        if not self._dragging:
            now = time.monotonic()
            if now - self._last_hover_action_at >= HOVER_ACTION_COOLDOWN_MS / 1000:
                self._last_hover_action_at = now
                self.perform_action(PetAction.JUMPING.value, repeat=JUMP_REPEAT_COUNT)
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hovered = False
        super().leaveEvent(event)

    def moveEvent(self, event):  # noqa: N802
        super().moveEvent(event)
        if self._compact_window.isVisible():
            self._update_compact_window_position()

    def _on_single_click(self) -> None:
        if self._pending_click:
            self._pending_click = False
            self.clicked.emit()

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        colors = theme_manager.get_current_colors()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {colors.bg_primary};
                border: 1px solid {colors.border_light};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 20px 8px 12px;
                border-radius: 4px;
                color: {colors.text_primary};
            }}
            QMenu::item:selected {{ background-color: {colors.bg_hover}; }}
        """)

        chat_action = menu.addAction("打开对话")
        chat_action.triggered.connect(self.show_input)
        region_action = menu.addAction("区域截图")
        region_action.triggered.connect(self._on_region_screenshot)
        full_action = menu.addAction("全屏截图")
        full_action.triggered.connect(self._on_full_screenshot)
        settings_action = menu.addAction("设置")
        settings_action.triggered.connect(self.settings_requested.emit)
        restart_action = menu.addAction("重启")
        restart_action.triggered.connect(self.restart_requested.emit)
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.exec(pos)

    def _on_region_screenshot(self) -> None:
        self.screenshot_requested.emit("region")

    def _on_full_screenshot(self) -> None:
        self.screenshot_requested.emit("full")

    def perform_action(
        self,
        action: str,
        duration_ms: Optional[int] = None,
        force: bool = False,
        repeat: int = 1,
    ) -> None:
        if not is_public_action_id(action):
            action = PetAction.WAVING.value
        if duration_ms is None:
            duration_ms = animation_duration_ms(action) * max(1, int(repeat))
        self._set_animation(action, duration_ms=max(1, duration_ms), force=force)

    def _set_animation(
        self,
        animation_id: str,
        duration_ms: Optional[int] = None,
        publish_action: bool = True,
        force: bool = False,
    ) -> None:
        if not is_animation_id(animation_id):
            animation_id = IDLE_ANIMATION_ID

        if duration_ms and duration_ms > 0 and animation_id != IDLE_ANIMATION_ID:
            self._transient_action_until = time.monotonic() + duration_ms / 1000
        else:
            self._transient_action_until = 0.0

        if not force and animation_id == self._state.current_action:
            self._state.set_action(animation_id)
            self.update()
            return

        self._state.set_action(animation_id)
        self._action_started_at = time.monotonic()
        self.update()

    def emit_event(
        self, event_type: str, message: str = "", ttl_ms: Optional[int] = None
    ) -> None:
        if event_type not in {item.value for item in PetEventType}:
            return
        self._state.set_event(event_type, message, ttl_ms)
        action = EVENT_ACTION_MAP.get(PetEventType(event_type))
        if action:
            action_id = getattr(action, "value", str(action))
            if action_id == IDLE_ANIMATION_ID:
                self._set_animation(IDLE_ANIMATION_ID, publish_action=False)
            else:
                repeat = JUMP_REPEAT_COUNT if action_id == PetAction.JUMPING.value else 1
                self.perform_action(action_id, repeat=repeat)
        if message:
            self.show_bubble(
                message,
                duration=ttl_ms or 0,
                animate=False,
            )

    def _on_api_action(self, action: str) -> None:
        self._api_action_requested.emit(action)

    def _on_api_say(self, text: str, ttl_ms: Optional[int]) -> None:
        self._api_say_requested.emit(text, ttl_ms)

    def _on_api_event(
        self, event_type: str, message: str, ttl_ms: Optional[int]
    ) -> None:
        self._api_event_requested.emit(event_type, message, ttl_ms)

    def _on_api_import(self, pet_id: str) -> None:
        self._api_import_requested.emit(pet_id)

    def load_pet(self, pet_id: str) -> None:
        self._catalog.refresh()
        pet = self._catalog.get(pet_id)
        if not pet:
            return
        self._pet = pet
        self._state.current_pet_id = pet.id
        self.config.pet_runtime.current_pet_id = pet.id
        self._sprite = QPixmap(str(pet.spritesheet_path))
        self._set_animation(IDLE_ANIMATION_ID, publish_action=False, force=True)
        self.update()

    def show_bubble(
        self,
        text: str,
        duration: int = 0,
        msg_type: str = "text",
        metadata: Optional[dict[str, Any]] = None,
        animate: bool = False,
    ) -> None:
        ttl_ms = duration or self.pet_config.bubble_ttl_ms
        self._state.set_bubble(text, ttl_ms)
        self._update_compact_window_position()
        self._compact_window.add_ai_message(text, msg_type=msg_type, metadata=metadata)
        self._compact_window.show()
        if animate:
            self.perform_action(PetAction.WAVING.value, duration_ms=min(ttl_ms, 1600))

    def show_system_message(self, text: str) -> None:
        self._state.set_bubble(text, self.pet_config.bubble_ttl_ms)
        self._compact_window.add_system_message(text)

    def toggle_input(self) -> None:
        if self._compact_window.isVisible():
            self._compact_window.hide()
        else:
            self.show_input()

    def show_input(self) -> None:
        self._update_compact_window_position()
        self._compact_window.show()
        self._compact_window.activateWindow()

    def add_user_message(self, text: str, image_path: Optional[str] = None) -> None:
        self._compact_window.add_user_message(text, image_path)

    def update_streaming_response(
        self, content: str, metadata: Optional[dict[str, Any]] = None
    ) -> None:
        self._compact_window.update_streaming_response(content, metadata=metadata)
        self._state.set_bubble(content, self.pet_config.bubble_ttl_ms)

    def finish_response(self) -> None:
        self._compact_window.finish_response()

    def set_attachment(self, path: str) -> None:
        self._compact_window.set_attachment(path)

    def set_breathing(self, enabled: bool) -> None:
        if enabled:
            self._animation_timer.start(ANIMATION_TIMER_MS)
        else:
            self._animation_timer.stop()

    def set_unread_message(self, has_unread: bool = True) -> None:
        self._has_unread = has_unread
        if has_unread:
            self.emit_event(PetEventType.ATTENTION.value)

    def clear_unread_message(self) -> None:
        self.set_unread_message(False)

    def has_unread_message(self) -> bool:
        return self._has_unread

    def is_waiting_response(self) -> bool:
        return self._compact_window._is_waiting

    def has_active_response(self) -> bool:
        return bool(
            self._compact_window._current_ai_message_id
            or self._compact_window._current_ai_message
        )

    def is_chat_window_visible(self) -> bool:
        return self._compact_window.isVisible()

    def set_state(self, state: Any) -> None:
        value = getattr(state, "value", str(state))
        mapping = {
            "normal": IDLE_ANIMATION_ID,
            "busy": IDLE_ANIMATION_ID,
            "processing": PetAction.RUNNING.value,
            "disconnected": PetAction.FAILED.value,
            "unread_message": PetAction.WAVING.value,
        }
        action = mapping.get(value, IDLE_ANIMATION_ID)
        if action == IDLE_ANIMATION_ID:
            self._set_animation(IDLE_ANIMATION_ID, publish_action=False)
        else:
            self.perform_action(action)

    def set_avatar(self, avatar_path: str) -> None:
        if avatar_path and os.path.exists(avatar_path):
            self._compact_window.set_bot_avatar(avatar_path)

    def set_user_avatar(self, avatar_path: str) -> None:
        self._compact_window.set_user_avatar(avatar_path)

    def set_bot_avatar(self, avatar_path: str) -> None:
        self._compact_window.set_bot_avatar(avatar_path)

    def update_appearance_config(self, config) -> None:
        self.config = config
        self._apply_chat_assets()

    def update_pet_runtime_config(self, config) -> None:
        self.config = config
        self.pet_config = config.pet_runtime
        self.load_pet(self.pet_config.current_pet_id)
        self.setFixedSize(self._window_size(), self._window_size())
        self.update()

    def prepare_for_screen_capture(self) -> dict[str, Any]:
        state = {
            "chat_visible": self._compact_window.isVisible(),
            "window_pos": self.pos(),
            "chat_pos": self._compact_window.pos(),
        }
        self.setWindowOpacity(0)
        self._compact_window.setWindowOpacity(0)
        self.move(-10000, -10000)
        self._compact_window.move(-10000, -10000)
        QApplication.processEvents()
        self._compact_window.hide()
        self.hide()
        QApplication.processEvents()
        return state

    def restore_after_screen_capture(self, state: Optional[dict[str, Any]] = None) -> None:
        state = state or {}
        window_pos = state.get("window_pos")
        chat_pos = state.get("chat_pos")
        if window_pos is not None:
            self.move(window_pos)
        if chat_pos is not None:
            self._compact_window.move(chat_pos)
        self.setWindowOpacity(1)
        self._compact_window.setWindowOpacity(1)
        self.show()
        if state.get("chat_visible"):
            self._compact_window.show()

    def _hide_bubble_only_if_empty(self) -> None:
        # The chat/input window stays user-controlled; this only keeps runtime state tidy.
        return

    def _update_compact_window_position(self) -> None:
        w = self._compact_window.width()
        h = self._compact_window.height()
        x = self.x() - w - 10
        y = self.y() + (self.height() - h) // 2
        if x < 0:
            x = self.x() + self.width() + 10
        self._compact_window.move(x, y)

    def _on_compact_window_moved(self, delta_x: int, delta_y: int) -> None:
        self.move(self.x() + delta_x, self.y() + delta_y)

    def _on_compact_window_resized(self) -> None:
        self._update_compact_window_position()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if sys.platform == "darwin":
            try:
                from ..gui.floating_ball import _set_macos_window_level

                QTimer.singleShot(50, lambda: _set_macos_window_level(self))
            except Exception:
                pass
