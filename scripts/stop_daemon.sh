#!/usr/bin/env bash
# Stop background room matcher started by start_daemon.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${PID_FILE:-${ROOT_DIR}/matcher.pid}"

if [[ ! -f "${PID_FILE}" ]]; then
  # Fallback: kill by module name
  if pgrep -f "python3 -m ds_launcher" >/dev/null 2>&1; then
    pkill -f "python3 -m ds_launcher" || true
    echo "stopped matcher by process name"
    exit 0
  fi
  echo "not running (no ${PID_FILE})" >&2
  exit 1
fi

pid="$(cat "${PID_FILE}")"
if [[ -z "${pid}" ]]; then
  rm -f "${PID_FILE}"
  echo "empty pidfile removed" >&2
  exit 1
fi

if kill -0 "${pid}" 2>/dev/null; then
  kill "${pid}" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      break
    fi
    sleep 0.3
  done
  if kill -0 "${pid}" 2>/dev/null; then
    kill -9 "${pid}" 2>/dev/null || true
  fi
  echo "stopped pid=${pid}"
else
  echo "process ${pid} not running"
fi
rm -f "${PID_FILE}"
