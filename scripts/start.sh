#!/usr/bin/env bash
# Start room matcher on Linux.
# Usage:
#   ./scripts/start.sh <public-host-ip>
#   PUBLIC_HOST=1.2.3.4 ./scripts/start.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PUBLIC_HOST="${1:-${PUBLIC_HOST:-}}"
DS_BINARY="${DS_BINARY:-${ROOT_DIR}/ds/SwitchGame.x86_64}"
API_HOST="${DS_API_HOST:-0.0.0.0}"
API_PORT="${DS_API_PORT:-1096}"
PORT_MIN="${DS_PORT_MIN:-7777}"
PORT_MAX="${DS_PORT_MAX:-7780}"
MAX_ROOMS="${DS_MAX_ROOMS:-4}"

if [[ -z "${PUBLIC_HOST}" ]]; then
  echo "usage: $0 <public-host-ip>" >&2
  echo "  public-host-ip = address clients use to join rooms" >&2
  exit 1
fi

if [[ ! -x "${DS_BINARY}" && ! -f "${DS_BINARY}" ]]; then
  echo "DS binary missing: ${DS_BINARY}" >&2
  echo "run: ./scripts/download_ds.sh" >&2
  exit 1
fi

chmod +x "${DS_BINARY}" || true
find "$(dirname "${DS_BINARY}")" -type f -name "*.so" -exec chmod +x {} \; 2>/dev/null || true

DOWNLOAD_SCRIPT="${DS_DOWNLOAD_SCRIPT:-${ROOT_DIR}/scripts/download_ds.sh}"
ADMIN_TOKEN="${DS_ADMIN_TOKEN:-}"

echo "Starting matcher api=${API_HOST}:${API_PORT} ds=${DS_BINARY} public=${PUBLIC_HOST}"
ARGS=(
  --ds-binary "${DS_BINARY}"
  --port-min "${PORT_MIN}"
  --port-max "${PORT_MAX}"
  --max-rooms "${MAX_ROOMS}"
  --public-host "${PUBLIC_HOST}"
  --api-host "${API_HOST}"
  --api-port "${API_PORT}"
  --download-script "${DOWNLOAD_SCRIPT}"
)
if [[ -n "${ADMIN_TOKEN}" ]]; then
  ARGS+=(--admin-token "${ADMIN_TOKEN}")
fi
exec python3 -m ds_launcher "${ARGS[@]}"
