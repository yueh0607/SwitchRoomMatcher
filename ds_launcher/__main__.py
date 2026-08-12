import logging
import signal
import sys
from typing import List, Optional

from .api import serve
from .config import load_config
from .manager import RoomManager


def main(argv=None):
    # type: (Optional[List[str]]) -> int
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(argv)
    manager = RoomManager(config)
    server = serve(manager, config.api_host, config.api_port)

    def _shutdown(signum, _frame):
        logging.info("signal %s received, shutting down", signum)
        manager.shutdown()
        server.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        manager.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
