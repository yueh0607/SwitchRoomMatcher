#!/usr/bin/env bash
# Start room matcher in background (survives SSH logout).
# Usage:
#   ./scripts/start_daemon.sh <public-host-ip>
#   PUBLIC_HOST=1.2.3.4 ./scripts/start_daemon.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PUBLIC_HOST="${1:-${PUBLIC_HOST:-}}"
PID_FILE="${PID_FILE:-${ROOT_DIR}/matcher.pid}"
LOG_FILE="${LOG_FILE:-${ROOT_DIR}/matcher.log}"

if [[ -z "${PUBLIC_HOST}" ]]; then
  echo "usage: $0 <public-host-ip>" >&2
  exit 1
fi

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "already running pid=${old_pid} (pidfile=${PID_FILE})" >&2
    exit 1
  fi
  rm -f "${PID_FILE}"
fi

chmod +x "${ROOT_DIR}/scripts/start.sh"
# nohup + disown-equivalent: close stdin, ignore HUP
nohup "${ROOT_DIR}/scripts/start.sh" "${PUBLIC_HOST}" >>"${LOG_FILE}" 2>&1 &
pid=$!
echo "${pid}" > "${PID_FILE}"
sleep 0.5
if ! kill -0 "${pid}" 2>/dev/null; then
  echo "failed to start; see ${LOG_FILE}" >&2
  rm -f "${PID_FILE}"
  exit 1
fi

echo "matcher started pid=${pid}"
echo "  log: ${LOG_FILE}"
echo "  pid: ${PID_FILE}"
echo "  health: curl -s http://127.0.0.1:${DS_API_PORT:-1096}/health"
echo "  stop:   ./scripts/stop_daemon.sh"
