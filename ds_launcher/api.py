from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Tuple
from urllib.parse import urlparse

from .manager import RoomManager

log = logging.getLogger("ds_launcher")


def _json_bytes(payload: dict, status: int = 200) -> Tuple[int, bytes, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def make_handler(manager: RoomManager) -> Callable[..., BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            log.info("http " + fmt, *args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/health":
                status, body, ctype = _json_bytes({"ok": True, **manager.stats()})
                self._send(status, body, ctype)
                return

            if path == "/rooms":
                status, body, ctype = _json_bytes({"rooms": manager.list_rooms()})
                self._send(status, body, ctype)
                return

            if path.startswith("/rooms/"):
                room_id = path.split("/", 2)[2]
                room = manager.get_room(room_id)
                if room is None:
                    status, body, ctype = _json_bytes({"error": "not found"}, 404)
                else:
                    status, body, ctype = _json_bytes(room)
                self._send(status, body, ctype)
                return

            status, body, ctype = _json_bytes({"error": "not found"}, 404)
            self._send(status, body, ctype)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path != "/rooms":
                status, body, ctype = _json_bytes({"error": "not found"}, 404)
                self._send(status, body, ctype)
                return

            try:
                payload = self._read_json()
                name = payload.get("name") if isinstance(payload, dict) else None
                if not isinstance(name, str) or not name.strip():
                    status, body, ctype = _json_bytes(
                        {"error": 'missing required field: "name"'},
                        400,
                    )
                else:
                    room = manager.create_room(name)
                    status, body, ctype = _json_bytes(room.to_dict(), 201)
            except json.JSONDecodeError:
                status, body, ctype = _json_bytes({"error": "invalid json"}, 400)
            except ValueError as exc:
                status, body, ctype = _json_bytes({"error": str(exc)}, 400)
            except RuntimeError as exc:
                status, body, ctype = _json_bytes({"error": str(exc)}, 409)
            except Exception as exc:  # noqa: BLE001
                log.exception("create room failed")
                status, body, ctype = _json_bytes({"error": str(exc)}, 500)
            self._send(status, body, ctype)

        def do_DELETE(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if not path.startswith("/rooms/"):
                status, body, ctype = _json_bytes({"error": "not found"}, 404)
                self._send(status, body, ctype)
                return

            room_id = path.split("/", 2)[2]
            ok = manager.stop_room(room_id)
            if not ok:
                status, body, ctype = _json_bytes({"error": "not found"}, 404)
            else:
                status, body, ctype = _json_bytes({"ok": True, "room_id": room_id})
            self._send(status, body, ctype)

    return Handler


def serve(manager: RoomManager, host: str, port: int) -> ThreadingHTTPServer:
    handler = make_handler(manager)
    server = ThreadingHTTPServer((host, port), handler)
    log.info("API listening on http://%s:%s", host, port)
    return server
