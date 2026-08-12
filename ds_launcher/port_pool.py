from __future__ import annotations

import socket
import threading
from typing import Optional, Set


class PortPool:
    """Allocate UDP/TCP ports from a fixed range on this machine."""

    def __init__(self, port_min: int, port_max: int) -> None:
        self._port_min = port_min
        self._port_max = port_max
        self._lock = threading.Lock()
        self._in_use: Set[int] = set()

    def acquire(self) -> Optional[int]:
        with self._lock:
            for port in range(self._port_min, self._port_max + 1):
                if port in self._in_use:
                    continue
                if not self._is_free(port):
                    continue
                self._in_use.add(port)
                return port
        return None

    def release(self, port: int) -> None:
        with self._lock:
            self._in_use.discard(port)

    def in_use_count(self) -> int:
        with self._lock:
            return len(self._in_use)

    @staticmethod
    def _is_free(port: int) -> bool:
        # Best-effort check; Unity KCP uses UDP. Also probe TCP for common conflicts.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.bind(("0.0.0.0", port))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                tcp.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False
