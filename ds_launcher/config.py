import argparse
import os
from typing import List, Optional


class Config(object):
    """Runtime config for the single-machine DS allocator."""

    def __init__(
        self,
        ds_binary,
        ds_extra_args=None,
        port_min=7777,
        port_max=7780,
        max_rooms=4,
        ready_timeout_sec=60.0,
        public_host="",
        api_host="0.0.0.0",
        api_port=1096,
        ready_token="DS_READY",
    ):
        self.ds_binary = ds_binary
        self.ds_extra_args = list(ds_extra_args or [])
        self.port_min = port_min
        self.port_max = port_max
        self.max_rooms = max_rooms
        self.ready_timeout_sec = ready_timeout_sec
        self.public_host = public_host
        self.api_host = api_host
        self.api_port = api_port
        self.ready_token = ready_token

    @property
    def port_capacity(self):
        return max(0, self.port_max - self.port_min + 1)


def _split_args(raw):
    # type: (str) -> List[str]
    raw = (raw or "").strip()
    if not raw:
        return []
    return raw.split()


def load_config(argv=None):
    # type: (Optional[List[str]]) -> Config
    parser = argparse.ArgumentParser(
        description="Allocate Dedicated Server processes on a single Linux machine.",
    )
    parser.add_argument(
        "--ds-binary",
        default=os.environ.get("DS_BINARY", ""),
        help="Path to Unity DS executable (env: DS_BINARY)",
    )
    parser.add_argument(
        "--ds-extra-args",
        default=os.environ.get("DS_EXTRA_ARGS", "-batchmode -nographics -logFile -"),
        help='Extra args appended after "-port N" (env: DS_EXTRA_ARGS)',
    )
    parser.add_argument("--port-min", type=int, default=int(os.environ.get("DS_PORT_MIN", "7777")))
    parser.add_argument("--port-max", type=int, default=int(os.environ.get("DS_PORT_MAX", "7780")))
    parser.add_argument("--max-rooms", type=int, default=int(os.environ.get("DS_MAX_ROOMS", "4")))
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=float(os.environ.get("DS_READY_TIMEOUT", "60")),
        help="Seconds to wait for DS_READY line",
    )
    parser.add_argument(
        "--public-host",
        default=os.environ.get("DS_PUBLIC_HOST", ""),
        help="Rewrite advertised host for clients (env: DS_PUBLIC_HOST)",
    )
    parser.add_argument("--api-host", default=os.environ.get("DS_API_HOST", "0.0.0.0"))
    parser.add_argument("--api-port", type=int, default=int(os.environ.get("DS_API_PORT", "1096")))

    args = parser.parse_args(argv)
    if not args.ds_binary:
        parser.error("--ds-binary / DS_BINARY is required")

    if args.port_min <= 0 or args.port_max <= 0 or args.port_min > args.port_max:
        parser.error("invalid port range")

    if args.max_rooms <= 0:
        parser.error("--max-rooms must be > 0")

    return Config(
        ds_binary=args.ds_binary,
        ds_extra_args=_split_args(args.ds_extra_args),
        port_min=args.port_min,
        port_max=args.port_max,
        max_rooms=min(args.max_rooms, args.port_max - args.port_min + 1),
        ready_timeout_sec=args.ready_timeout,
        public_host=args.public_host.strip(),
        api_host=args.api_host,
        api_port=args.api_port,
    )
