import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import Config
from .port_pool import PortPool

log = logging.getLogger("ds_launcher")


class Room(object):
    def __init__(self, room_id, name, port, pid, process):
        self.room_id = room_id
        self.name = name
        self.port = port
        self.pid = pid
        self.process = process
        self.endpoint = ""
        self.status = "starting"  # starting | ready | dead | failed
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.error = ""

    def to_dict(self):
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


class RoomManager(object):
    def __init__(self, config):
        # type: (Config) -> None
        self._config = config
        self._ports = PortPool(config.port_min, config.port_max)
        self._lock = threading.Lock()
        self._rooms = {}  # type: Dict[str, Room]
        self._closed = False
        self._updating = False

    def create_room(self, name):
        # type: (str) -> Room
        if self._closed:
            raise RuntimeError("manager is shutting down")

        name = (name or "").strip()
        if not name:
            raise ValueError("room name is required")
        if len(name) > 64:
            raise ValueError("room name too long (max 64)")

        with self._lock:
            if self._updating:
                raise RuntimeError("DS update in progress")
            live_rooms = [r for r in self._rooms.values() if r.status in ("starting", "ready")]
            if len(live_rooms) >= self._config.max_rooms:
                raise RuntimeError("max rooms reached ({0})".format(self._config.max_rooms))
            if any(r.name == name for r in live_rooms):
                raise RuntimeError("room name already exists: {0}".format(name))

        port = self._ports.acquire()
        if port is None:
            raise RuntimeError("no free port in configured range")

        room_id = uuid.uuid4().hex[:12]
        cmd = [self._config.ds_binary, "-port", str(port)] + list(self._config.ds_extra_args)
        log.info("spawn room=%s name=%s port=%s cmd=%s", room_id, name, port, cmd)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                start_new_session=True,
            )
        except OSError as exc:
            self._ports.release(port)
            raise RuntimeError("failed to spawn DS: {0}".format(exc))

        room = Room(room_id=room_id, name=name, port=port, pid=proc.pid, process=proc)
        with self._lock:
            self._rooms[room_id] = room

        worker = threading.Thread(
            target=self._watch_room,
            args=(room,),
            name="ds-room-{0}".format(room_id),
        )
        worker.daemon = True
        worker.start()

        if not self._wait_ready(room, self._config.ready_timeout_sec):
            self.stop_room(room_id)
            raise RuntimeError(room.error or "timeout waiting for {0}".format(self._config.ready_token))

        return room

    def list_rooms(self):
        # type: () -> List[dict]
        with self._lock:
            return [r.to_dict() for r in self._rooms.values()]

    def get_room(self, room_id):
        # type: (str) -> Optional[dict]
        with self._lock:
            room = self._rooms.get(room_id)
            return room.to_dict() if room else None

    def stop_room(self, room_id):
        # type: (str) -> bool
        with self._lock:
            room = self._rooms.get(room_id)
        if room is None:
            return False
        self._terminate(room)
        return True

    def shutdown(self):
        self._closed = True
        with self._lock:
            room_ids = list(self._rooms.keys())
        for room_id in room_ids:
            self.stop_room(room_id)

    def stats(self):
        with self._lock:
            rooms = list(self._rooms.values())
            updating = self._updating
        return {
            "rooms": len(rooms),
            "ready": sum(1 for r in rooms if r.status == "ready"),
            "starting": sum(1 for r in rooms if r.status == "starting"),
            "ports_in_use": self._ports.in_use_count(),
            "port_min": self._config.port_min,
            "port_max": self._config.port_max,
            "max_rooms": self._config.max_rooms,
            "updating": updating,
        }

    def live_room_count(self):
        with self._lock:
            return sum(1 for r in self._rooms.values() if r.status in ("starting", "ready"))

    def update_ds(self, force=False):
        # type: (bool) -> dict
        """Re-download DS zip via scripts/download_ds.sh."""
        script = self._config.download_script
        if not script or not os.path.isfile(script):
            raise RuntimeError("download script not found: {0}".format(script))

        with self._lock:
            if self._updating:
                raise RuntimeError("DS update already in progress")
            live = [r for r in self._rooms.values() if r.status in ("starting", "ready")]
            if live and not force:
                raise RuntimeError(
                    "active rooms exist ({0}); pass force=true to stop them and update".format(len(live))
                )
            self._updating = True
            stop_ids = [r.room_id for r in live] if force else []

        stopped = 0
        try:
            for room_id in stop_ids:
                if self.stop_room(room_id):
                    stopped += 1

            env = os.environ.copy()
            ds_dir = os.path.dirname(os.path.abspath(self._config.ds_binary))
            env["DS_DIR"] = ds_dir
            log.info("updating DS via %s DS_DIR=%s", script, ds_dir)
            started = time.time()
            proc = subprocess.Popen(
                ["/bin/bash", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                env=env,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(script))),
            )
            out, _ = proc.communicate()
            elapsed = time.time() - started
            if out:
                for line in out.splitlines():
                    log.info("ds-update: %s", line)
            if proc.returncode != 0:
                raise RuntimeError("download_ds.sh failed, code={0}".format(proc.returncode))

            if not os.path.isfile(self._config.ds_binary):
                raise RuntimeError("DS binary missing after update: {0}".format(self._config.ds_binary))
            try:
                os.chmod(self._config.ds_binary, 0o755)
            except OSError:
                pass

            return {
                "ok": True,
                "stopped_rooms": stopped,
                "elapsed_sec": round(elapsed, 2),
                "ds_binary": self._config.ds_binary,
            }
        finally:
            with self._lock:
                self._updating = False

    def _wait_ready(self, room, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if room.status == "ready":
                return True
            if room.status in ("dead", "failed"):
                return False
            time.sleep(0.05)
        if room.status != "ready":
            room.status = "failed"
            room.error = "timeout waiting for {0}".format(self._config.ready_token)
            return False
        return True

    def _watch_room(self, room):
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
        except Exception as exc:
            room.status = "failed"
            room.error = str(exc)
            log.exception("room watcher failed id=%s", room.room_id)

        code = room.process.wait()
        if room.status == "ready":
            room.status = "dead"
        elif room.status == "starting":
            room.status = "failed"
            if not room.error:
                room.error = "DS exited before ready, code={0}".format(code)
        log.info("room exited id=%s code=%s status=%s", room.room_id, code, room.status)
        self._ports.release(room.port)

    def _terminate(self, room):
        proc = room.process
        if proc.poll() is not None:
            self._ports.release(room.port)
            return

        log.info("stopping room id=%s pid=%s", room.room_id, room.pid)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            try:
                proc.terminate()
            except OSError:
                pass

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

        if room.status not in ("failed", "dead"):
            room.status = "dead"
        self._ports.release(room.port)

    def _rewrite_endpoint(self, endpoint):
        host = self._config.public_host
        if not host:
            return endpoint
        if ":" not in endpoint:
            return endpoint
        _, port_text = endpoint.rsplit(":", 1)
        return "{0}:{1}".format(host, port_text)

    @staticmethod
    def _parse_ready(line, token):
        # type: (str, str) -> Optional[str]
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
