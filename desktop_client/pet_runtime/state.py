"""Runtime state and public action/event names for the pet runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .animation import IDLE_ANIMATION_ID


class PetAction(str, Enum):
    """OpenPet-compatible public action ids."""

    WAVING = "waving"
    JUMPING = "jumping"
    WAITING = "waiting"
    RUNNING = "running"
    REVIEW = "review"
    FAILED = "failed"


class PetEventType(str, Enum):
    """OpenPet-compatible companion event types."""

    THINKING = "thinking"
    TOOL_RUNNING = "tool-running"
    REVIEWING = "reviewing"
    SUCCESS = "success"
    FAILURE = "failure"
    ATTENTION = "attention"


EVENT_ACTION_MAP: dict[PetEventType, str] = {
    PetEventType.THINKING: PetAction.JUMPING,
    PetEventType.TOOL_RUNNING: IDLE_ANIMATION_ID,
    PetEventType.REVIEWING: IDLE_ANIMATION_ID,
    PetEventType.SUCCESS: IDLE_ANIMATION_ID,
    PetEventType.FAILURE: IDLE_ANIMATION_ID,
    PetEventType.ATTENTION: IDLE_ANIMATION_ID,
}


@dataclass
class RuntimeState:
    """Mutable runtime state shared by the window and local API."""

    current_pet_id: str = "taotao"
    current_action: str = IDLE_ANIMATION_ID
    last_event_type: str = ""
    bubble_text: str = ""
    bubble_expires_at: float = 0.0
    last_error: str = ""
    updated_at: float = field(default_factory=time.time)

    def set_action(self, action: str) -> None:
        self.current_action = action
        self.updated_at = time.time()

    def set_bubble(self, text: str, ttl_ms: Optional[int] = None) -> None:
        self.bubble_text = text
        if ttl_ms and ttl_ms > 0:
            self.bubble_expires_at = time.time() + ttl_ms / 1000
        else:
            self.bubble_expires_at = 0.0
        self.updated_at = time.time()

    def clear_bubble_if_expired(self) -> None:
        if self.bubble_expires_at and time.time() >= self.bubble_expires_at:
            self.bubble_text = ""
            self.bubble_expires_at = 0.0
            self.updated_at = time.time()

    def set_event(self, event_type: str, message: str = "", ttl_ms: Optional[int] = None) -> None:
        self.last_event_type = event_type
        if message:
            self.set_bubble(message, ttl_ms)
        else:
            self.updated_at = time.time()

    def to_dict(self, pet: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        self.clear_bubble_if_expired()
        return {
            "currentPetId": self.current_pet_id,
            "currentAction": self.current_action,
            "lastEventType": self.last_event_type,
            "bubbleText": self.bubble_text,
            "bubbleExpiresAt": int(self.bubble_expires_at * 1000)
            if self.bubble_expires_at
            else None,
            "lastError": self.last_error,
            "updatedAt": int(self.updated_at * 1000),
            "pet": pet,
        }


@dataclass(frozen=True)
class PetRuntimeSnapshot:
    """Serializable status response for the OpenPet-compatible API."""

    state: RuntimeState
    pet: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return self.state.to_dict(self.pet)
