import socket
import threading
from typing import Optional, Set


class PortPool(object):
    """Allocate UDP/TCP ports from a fixed range on this machine."""

    def __init__(self, port_min, port_max):
        self._port_min = port_min
        self._port_max = port_max
        self._lock = threading.Lock()
        self._in_use = set()  # type: Set[int]

    def acquire(self):
        # type: () -> Optional[int]
        with self._lock:
            for port in range(self._port_min, self._port_max + 1):
                if port in self._in_use:
                    continue
                if not self._is_free(port):
                    continue
                self._in_use.add(port)
                return port
        return None

    def release(self, port):
        with self._lock:
            self._in_use.discard(port)

    def in_use_count(self):
        with self._lock:
            return len(self._in_use)

    @staticmethod
    def _is_free(port):
        try:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                udp.bind(("0.0.0.0", port))
            finally:
                udp.close()
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                tcp.bind(("0.0.0.0", port))
            finally:
                tcp.close()
            return True
        except OSError:
            return False
