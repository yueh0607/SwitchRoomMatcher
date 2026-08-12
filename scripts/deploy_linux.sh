#!/usr/bin/env bash
# One-shot Linux deploy: download DS from COS, then start matcher.
# Usage:
#   ./scripts/deploy_linux.sh <public-host-ip>
#   PUBLIC_HOST=1.2.3.4 ./scripts/deploy_linux.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PUBLIC_HOST="${1:-${PUBLIC_HOST:-}}"
if [[ -z "${PUBLIC_HOST}" ]]; then
  echo "usage: $0 <public-host-ip>" >&2
  exit 1
fi

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing dependency: $1" >&2
    exit 1
  }
}

need python3
need curl

chmod +x scripts/download_ds.sh scripts/start.sh
./scripts/download_ds.sh
./scripts/start.sh "${PUBLIC_HOST}"
