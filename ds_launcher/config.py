from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """Runtime config for the single-machine DS allocator."""

    ds_binary: str
    ds_extra_args: List[str] = field(default_factory=list)
    port_min: int = 7777
    port_max: int = 7877
    max_rooms: int = 32
    ready_timeout_sec: float = 60.0
    public_host: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    ready_token: str = "DS_READY"

    @property
    def port_capacity(self) -> int:
        return max(0, self.port_max - self.port_min + 1)


def _split_args(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    # Simple split; quote-aware parsing is unnecessary for typical Unity flags.
    return raw.split()


def load_config(argv: List[str] | None = None) -> Config:
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
    parser.add_argument("--port-max", type=int, default=int(os.environ.get("DS_PORT_MAX", "7877")))
    parser.add_argument("--max-rooms", type=int, default=int(os.environ.get("DS_MAX_ROOMS", "32")))
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
    parser.add_argument("--api-port", type=int, default=int(os.environ.get("DS_API_PORT", "8080")))

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
