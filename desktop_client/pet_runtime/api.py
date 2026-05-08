"""Local OpenPet-compatible HTTP API."""

from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlparse

from .catalog import PetCatalog
from .state import EVENT_ACTION_MAP, PetAction, PetEventType, RuntimeState

logger = logging.getLogger(__name__)


class PetRuntimeApiServer:
    """Small localhost API server used by Codex-compatible agents."""

    def __init__(
        self,
        host: str,
        port: int,
        state: RuntimeState,
        catalog: PetCatalog,
        on_action: Optional[Callable[[str], None]] = None,
        on_say: Optional[Callable[[str, Optional[int]], None]] = None,
        on_event: Optional[Callable[[str, str, Optional[int]], None]] = None,
        on_import: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = int(port)
        self.state = state
        self.catalog = catalog
        self.on_action = on_action
        self.on_say = on_say
        self.on_event = on_event
        self.on_import = on_import
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return bool(self._server and self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.is_running:
            return

        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="PetRuntimeApiServer",
            daemon=True,
        )
        self._thread.start()
        logger.info("Pet runtime API listening on http://%s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _snapshot(self) -> dict[str, Any]:
        pet = self.catalog.get(self.state.current_pet_id)
        return self.state.to_dict(pet.to_dict() if pet else None)

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AstrBotPetRuntime/1.0"

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    self._send_json(HTTPStatus.OK, outer._snapshot())
                    return

                prefix = "/api/pets/"
                suffix = "/spritesheet"
                if parsed.path.startswith(prefix) and parsed.path.endswith(suffix):
                    pet_id = unquote(parsed.path[len(prefix) : -len(suffix)])
                    pet = outer.catalog.get(pet_id)
                    if not pet:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "pet not found"})
                        return
                    self._send_file(pet.spritesheet_path, "image/webp")
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                try:
                    body = self._read_json()
                    if parsed.path == "/api/action":
                        self._handle_action(body)
                    elif parsed.path == "/api/say":
                        self._handle_say(body)
                    elif parsed.path == "/api/event":
                        self._handle_event(body)
                    elif parsed.path == "/api/import/local":
                        self._handle_import_local(body)
                    else:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                except Exception as e:
                    logger.debug("Pet runtime API request failed: %s", e)
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})

            def log_message(self, format: str, *args: Any) -> None:
                logger.debug("Pet runtime API: " + format, *args)

            def _handle_action(self, body: dict[str, Any]) -> None:
                action = str(body.get("animationId") or "").strip()
                if action not in {item.value for item in PetAction}:
                    raise ValueError(f"unsupported animationId: {action}")
                outer.state.set_action(action)
                if outer.on_action:
                    outer.on_action(action)
                self._send_json(HTTPStatus.OK, outer._snapshot())

            def _handle_say(self, body: dict[str, Any]) -> None:
                text = str(body.get("text") or "").strip()
                ttl_ms = _optional_int(body.get("ttlMs"))
                if not text:
                    raise ValueError("text is required")
                outer.state.set_bubble(text, ttl_ms)
                if outer.on_say:
                    outer.on_say(text, ttl_ms)
                self._send_json(HTTPStatus.OK, outer._snapshot())

            def _handle_event(self, body: dict[str, Any]) -> None:
                event_type = str(body.get("type") or "").strip()
                if event_type not in {item.value for item in PetEventType}:
                    raise ValueError(f"unsupported event type: {event_type}")
                message = str(body.get("message") or "").strip()
                ttl_ms = _optional_int(body.get("ttlMs"))
                outer.state.set_event(event_type, message, ttl_ms)
                action = EVENT_ACTION_MAP.get(PetEventType(event_type))
                if action:
                    action_id = getattr(action, "value", str(action))
                    outer.state.set_action(action_id)
                    if outer.on_action and not outer.on_event:
                        outer.on_action(action_id)
                if outer.on_event:
                    outer.on_event(event_type, message, ttl_ms)
                self._send_json(HTTPStatus.OK, outer._snapshot())

            def _handle_import_local(self, body: dict[str, Any]) -> None:
                source = str(body.get("source") or "").strip()
                if not source:
                    raise ValueError("source is required")
                pet = outer.catalog.import_local(
                    source=source,
                    force=bool(body.get("force", False)),
                    pet_id=body.get("id"),
                    display_name=body.get("displayName"),
                    description=body.get("description"),
                )
                outer.state.current_pet_id = pet.id
                if outer.on_import:
                    outer.on_import(pet.id)
                self._send_json(HTTPStatus.OK, outer._snapshot())

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                return json.loads(raw.decode("utf-8"))

            def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(int(status))
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_file(self, path, content_type: str) -> None:
                data = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)
