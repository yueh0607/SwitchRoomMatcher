#!/usr/bin/env bash
# Download DS files from Tencent COS (public-read objects) into ./ds
# Matcher only downloads + schedules; packaging/upload is out of scope.
#
# Usage:
#   ./scripts/download_ds.sh
#   DS_BASE_URL=https://....myqcloud.com ./scripts/download_ds.sh
#   DS_DIR=./ds ./scripts/download_ds.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="${DS_MANIFEST:-${ROOT_DIR}/scripts/ds_manifest.txt}"
DS_DIR="${DS_DIR:-${ROOT_DIR}/ds}"
DS_BASE_URL="${DS_BASE_URL:-https://switch-ds-1302238740.cos.ap-guangzhou.myqcloud.com}"
DS_BASE_URL="${DS_BASE_URL%/}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "manifest not found: ${MANIFEST}" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "need curl" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "need python3" >&2
  exit 1
fi

FILES=()
while IFS= read -r line || [[ -n "${line}" ]]; do
  line="${line//$'\r'/}"
  [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
  FILES+=("${line}")
done < "${MANIFEST}"

total="${#FILES[@]}"
if [[ "${total}" -eq 0 ]]; then
  echo "manifest is empty: ${MANIFEST}" >&2
  exit 1
fi

echo "Downloading ${total} files from ${DS_BASE_URL} -> ${DS_DIR}"
rm -rf "${DS_DIR}"
mkdir -p "${DS_DIR}"

failed=0
ok=0
idx=0
start_ts="$(date +%s)"

for rel in "${FILES[@]}"; do
  idx=$((idx + 1))
  pct=$((idx * 100 / total))
  dest="${DS_DIR}/${rel}"
  mkdir -p "$(dirname "${dest}")"
  enc="$("$PY" -c 'import sys,urllib.parse; print("/".join(urllib.parse.quote(p, safe="") for p in sys.argv[1].split("/")))' "${rel}")"
  url="${DS_BASE_URL}/${enc}"

  # Same-line progress: [12/257] 4% path...
  printf "\r[%d/%d] %d%%  %s" "${idx}" "${total}" "${pct}" "${rel}"
  # Pad/clear rest of previous longer filename.
  printf "%-40s" ""
  printf "\r[%d/%d] %d%%  %s" "${idx}" "${total}" "${pct}" "${rel}"

  if curl -fsSL --retry 3 --globoff -o "${dest}" "${url}"; then
    ok=$((ok + 1))
  else
    printf "\nFAILED: %s\n" "${rel}" >&2
    failed=$((failed + 1))
  fi
done

elapsed=$(( $(date +%s) - start_ts ))
printf "\nDone in %ds: ok=%d failed=%d\n" "${elapsed}" "${ok}" "${failed}"

if [[ "${failed}" -ne 0 ]]; then
  echo "download finished with ${failed} failures (check COS upload completeness)" >&2
  if [[ "${DS_ALLOW_MISSING:-0}" == "1" ]]; then
    echo "DS_ALLOW_MISSING=1 set; continuing despite missing files" >&2
  else
    exit 1
  fi
fi

BINARY=""
for candidate in \
  "${DS_DIR}/SwitchGame.x86_64" \
  "${DS_DIR}/SwitchGame" \
  "${DS_DIR}"/*.x86_64
do
  if [[ -f "${candidate}" ]]; then
    BINARY="${candidate}"
    break
  fi
done

if [[ -z "${BINARY}" ]]; then
  echo "download ok, but no .x86_64 binary found under ${DS_DIR}" >&2
  exit 1
fi

chmod +x "${BINARY}"
find "${DS_DIR}" -type f -name "*.so" -exec chmod +x {} \;

echo "DS ready: ${BINARY}"
echo "Start matcher with:"
echo "  python3 -m ds_launcher --ds-binary ${BINARY} --public-host <ip>"
