import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import Any, Callable, Dict, Tuple
from urllib.parse import parse_qs, urlparse

from .manager import RoomManager

log = logging.getLogger("ds_launcher")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _json_bytes(payload, status=200):
    # type: (Dict[str, Any], int) -> Tuple[int, bytes, str]
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def make_handler(manager):
    # type: (RoomManager) -> Callable[..., BaseHTTPRequestHandler]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.info("http " + fmt, *args)

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _check_admin(self):
            token = manager._config.admin_token
            if not token:
                return True
            header = self.headers.get("X-Admin-Token", "")
            auth = self.headers.get("Authorization", "")
            if header == token:
                return True
            if auth.startswith("Bearer ") and auth[7:] == token:
                return True
            return False

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/health":
                payload = {"ok": True}
                payload.update(manager.stats())
                status, body, ctype = _json_bytes(payload)
                self._send(status, body, ctype)
                return

            if path == "/ds/update":
                status, body, ctype = _json_bytes(manager.get_update_status())
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

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query or "")

            if path == "/ds/update":
                if not self._check_admin():
                    status, body, ctype = _json_bytes({"error": "unauthorized"}, 401)
                    self._send(status, body, ctype)
                    return
                try:
                    payload = self._read_json()
                except json.JSONDecodeError:
                    status, body, ctype = _json_bytes({"error": "invalid json"}, 400)
                    self._send(status, body, ctype)
                    return
                force = False
                if isinstance(payload, dict) and payload.get("force") in (True, 1, "1", "true", "True"):
                    force = True
                if query.get("force", [""])[0] in ("1", "true", "True"):
                    force = True
                try:
                    result = manager.start_update_ds(force=force)
                    status, body, ctype = _json_bytes(result, 202)
                except RuntimeError as exc:
                    status, body, ctype = _json_bytes({"error": str(exc)}, 409)
                except Exception as exc:
                    log.exception("ds update failed")
                    status, body, ctype = _json_bytes({"error": str(exc)}, 500)
                self._send(status, body, ctype)
                return

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
            except Exception as exc:
                log.exception("create room failed")
                status, body, ctype = _json_bytes({"error": str(exc)}, 500)
            self._send(status, body, ctype)

        def do_DELETE(self):
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


def serve(manager, host, port):
    # type: (RoomManager, str, int) -> ThreadingHTTPServer
    handler = make_handler(manager)
    server = ThreadingHTTPServer((host, port), handler)
    log.info("API listening on http://%s:%s", host, port)
    return server
