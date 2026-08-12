from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import Config
from .port_pool import PortPool

log = logging.getLogger("ds_launcher")


@dataclass
class Room:
    room_id: str
    name: str
    port: int
    pid: int
    endpoint: str = ""
    status: str = "starting"  # starting | ready | dead | failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str = ""
    process: subprocess.Popen = field(repr=False, default=None)  # type: ignore[assignment]

    def to_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "port": self.port,
            "pid": self.pid,
            "endpoint": self.endpoint,
            "status": self.status,
            "created_at": self.created_at,
            "error": self.error,
        }


class RoomManager:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._ports = PortPool(config.port_min, config.port_max)
        self._lock = threading.Lock()
        self._rooms: Dict[str, Room] = {}
        self._closed = False

    def create_room(self, name: str) -> Room:
        if self._closed:
            raise RuntimeError("manager is shutting down")

        name = (name or "").strip()
        if not name:
            raise ValueError("room name is required")
        if len(name) > 64:
            raise ValueError("room name too long (max 64)")

        with self._lock:
            live_rooms = [r for r in self._rooms.values() if r.status in ("starting", "ready")]
            if len(live_rooms) >= self._config.max_rooms:
                raise RuntimeError(f"max rooms reached ({self._config.max_rooms})")
            if any(r.name == name for r in live_rooms):
                raise RuntimeError(f"room name already exists: {name}")

        port = self._ports.acquire()
        if port is None:
            raise RuntimeError("no free port in configured range")

        room_id = uuid.uuid4().hex[:12]
        cmd = [self._config.ds_binary, "-port", str(port), *self._config.ds_extra_args]
        log.info("spawn room=%s name=%s port=%s cmd=%s", room_id, name, port, cmd)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            self._ports.release(port)
            raise RuntimeError(f"failed to spawn DS: {exc}") from exc

        room = Room(room_id=room_id, name=name, port=port, pid=proc.pid, process=proc)
        with self._lock:
            self._rooms[room_id] = room

        worker = threading.Thread(
            target=self._watch_room,
            args=(room,),
            name=f"ds-room-{room_id}",
            daemon=True,
        )
        worker.start()

        if not self._wait_ready(room, self._config.ready_timeout_sec):
            self.stop_room(room_id)
            raise RuntimeError(room.error or f"timeout waiting for {self._config.ready_token}")

        return room

    def list_rooms(self) -> List[dict]:
        with self._lock:
            return [r.to_dict() for r in self._rooms.values()]

    def get_room(self, room_id: str) -> Optional[dict]:
        with self._lock:
            room = self._rooms.get(room_id)
            return room.to_dict() if room else None

    def stop_room(self, room_id: str) -> bool:
        with self._lock:
            room = self._rooms.get(room_id)
        if room is None:
            return False
        self._terminate(room)
        return True

    def shutdown(self) -> None:
        self._closed = True
        with self._lock:
            room_ids = list(self._rooms.keys())
        for room_id in room_ids:
            self.stop_room(room_id)

    def stats(self) -> dict:
        with self._lock:
            rooms = list(self._rooms.values())
        return {
            "rooms": len(rooms),
            "ready": sum(1 for r in rooms if r.status == "ready"),
            "starting": sum(1 for r in rooms if r.status == "starting"),
            "ports_in_use": self._ports.in_use_count(),
            "port_min": self._config.port_min,
            "port_max": self._config.port_max,
            "max_rooms": self._config.max_rooms,
        }

    def _wait_ready(self, room: Room, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if room.status == "ready":
                return True
            if room.status in ("dead", "failed"):
                return False
            time.sleep(0.05)
        if room.status != "ready":
            room.status = "failed"
            room.error = f"timeout waiting for {self._config.ready_token}"
            return False
        return True

    def _watch_room(self, room: Room) -> None:
        assert room.process.stdout is not None
        token = self._config.ready_token
        try:
            for line in room.process.stdout:
                line = line.rstrip("\r\n")
                if line:
                    log.debug("ds[%s] %s", room.room_id, line)
                endpoint = self._parse_ready(line, token)
                if endpoint is None:
                    continue
                endpoint = self._rewrite_endpoint(endpoint)
                room.endpoint = endpoint
                room.status = "ready"
                log.info("room ready id=%s endpoint=%s", room.room_id, endpoint)
        except Exception as exc:  # noqa: BLE001 - worker must not die silently
            room.status = "failed"
            room.error = str(exc)
            log.exception("room watcher failed id=%s", room.room_id)

        code = room.process.wait()
        if room.status == "ready":
            room.status = "dead"
        elif room.status == "starting":
            room.status = "failed"
            if not room.error:
                room.error = f"DS exited before ready, code={code}"
        log.info("room exited id=%s code=%s status=%s", room.room_id, code, room.status)
        self._ports.release(room.port)

    def _terminate(self, room: Room) -> None:
        proc = room.process
        if proc.poll() is not None:
            self._ports.release(room.port)
            return

        log.info("stopping room id=%s pid=%s", room.room_id, room.pid)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.terminate()
            except OSError:
                pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
            proc.wait(timeout=3)

        if room.status not in ("failed", "dead"):
            room.status = "dead"
        self._ports.release(room.port)

    def _rewrite_endpoint(self, endpoint: str) -> str:
        host = self._config.public_host
        if not host:
            return endpoint
        if ":" not in endpoint:
            return endpoint
        _, port_text = endpoint.rsplit(":", 1)
        return f"{host}:{port_text}"

    @staticmethod
    def _parse_ready(line: str, token: str) -> Optional[str]:
        # Expected: "DS_READY 192.168.1.10:7777"
        parts = line.strip().split()
        if len(parts) < 2:
            return None
        if parts[0] != token:
            return None
        endpoint = parts[1].strip()
        if ":" not in endpoint:
            return None
        host, port_text = endpoint.rsplit(":", 1)
        if not host or not port_text.isdigit():
            return None
        return endpoint
