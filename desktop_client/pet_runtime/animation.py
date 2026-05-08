"""OpenPet-compatible animation timing rules for Codex pet packages."""

from __future__ import annotations

from dataclasses import dataclass


ANIMATION_TIMER_MS = 33
IDLE_ANIMATION_ID = "idle"


@dataclass(frozen=True)
class PetAnimation:
    """A fixed OpenPet atlas row animation."""

    id: str
    row: int
    frame_count: int
    frame_durations_ms: tuple[int, ...]


PET_ANIMATIONS: dict[str, PetAnimation] = {
    "idle": PetAnimation(
        id="idle",
        row=0,
        frame_count=6,
        frame_durations_ms=(2400, 900, 900, 1300, 1300, 2800),
    ),
    "running-right": PetAnimation(
        id="running-right",
        row=1,
        frame_count=8,
        frame_durations_ms=(120, 120, 120, 120, 120, 120, 120, 220),
    ),
    "running-left": PetAnimation(
        id="running-left",
        row=2,
        frame_count=8,
        frame_durations_ms=(120, 120, 120, 120, 120, 120, 120, 220),
    ),
    "waving": PetAnimation(
        id="waving",
        row=3,
        frame_count=4,
        frame_durations_ms=(140, 140, 140, 280),
    ),
    "jumping": PetAnimation(
        id="jumping",
        row=4,
        frame_count=5,
        frame_durations_ms=(140, 140, 140, 140, 280),
    ),
    "failed": PetAnimation(
        id="failed",
        row=5,
        frame_count=8,
        frame_durations_ms=(140, 140, 140, 140, 140, 140, 140, 240),
    ),
    "waiting": PetAnimation(
        id="waiting",
        row=6,
        frame_count=6,
        frame_durations_ms=(150, 150, 150, 150, 150, 260),
    ),
    "running": PetAnimation(
        id="running",
        row=7,
        frame_count=6,
        frame_durations_ms=(120, 120, 120, 120, 120, 220),
    ),
    "review": PetAnimation(
        id="review",
        row=8,
        frame_count=6,
        frame_durations_ms=(150, 150, 150, 150, 150, 280),
    ),
}

PUBLIC_ACTION_IDS = frozenset(
    {"waving", "jumping", "waiting", "running", "review", "failed"}
)


def is_animation_id(value: str | None) -> bool:
    """Return whether a value is a known internal OpenPet animation id."""
    return bool(value and value in PET_ANIMATIONS)


def is_public_action_id(value: str | None) -> bool:
    """Return whether a value is accepted by the OpenPet action API."""
    return bool(value and value in PUBLIC_ACTION_IDS)


def get_animation(animation_id: str) -> PetAnimation:
    """Return an animation definition, falling back to idle for unknown ids."""
    return PET_ANIMATIONS.get(animation_id, PET_ANIMATIONS[IDLE_ANIMATION_ID])


def animation_duration_ms(animation_id: str) -> int:
    """Return the full loop duration for an animation."""
    animation = get_animation(animation_id)
    return sum(animation.frame_durations_ms)


def frame_at_elapsed_ms(animation: PetAnimation, elapsed_ms: int) -> int:
    """Return the frame number for elapsed time using per-frame durations."""
    total_duration = sum(animation.frame_durations_ms)
    if total_duration <= 0:
        return 0

    cursor = elapsed_ms % total_duration
    consumed = 0
    for index, duration in enumerate(animation.frame_durations_ms):
        consumed += duration
        if cursor < consumed:
            return min(index, animation.frame_count - 1)
    return max(0, animation.frame_count - 1)


def frame_index_for_animation(
    animation_id: str,
    elapsed_ms: int,
    rows: int = 9,
    cols: int = 8,
) -> int:
    """Return the atlas frame index for an animation at elapsed time."""
    animation = get_animation(animation_id)
    if animation.row >= rows:
        animation = get_animation(IDLE_ANIMATION_ID)
    frame = frame_at_elapsed_ms(animation, elapsed_ms)
    return animation.row * cols + frame


def action_frame_sequence(action: str, rows: int = 9, cols: int = 8) -> list[int]:
    """Return fixed atlas frame indexes for a known animation.

    The Codex/OpenPet pet package format keeps animation semantics in the runtime,
    not in pet.json. Do not scan blank cells or infer row mappings from pixels.
    """
    animation = get_animation(action)
    if animation.row >= rows:
        animation = get_animation(IDLE_ANIMATION_ID)
    frame_count = min(animation.frame_count, max(1, cols))
    return [animation.row * cols + frame for frame in range(frame_count)]
