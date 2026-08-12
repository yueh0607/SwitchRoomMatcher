#!/usr/bin/env bash
# Download one DS zip from Tencent COS and extract into ./ds
#
# Usage:
#   ./scripts/download_ds.sh
#   DS_ZIP_URL=https://..../ds.zip ./scripts/download_ds.sh
#   DS_DIR=./ds ./scripts/download_ds.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DS_DIR="${DS_DIR:-${ROOT_DIR}/ds}"
DS_ZIP_URL="${DS_ZIP_URL:-https://switch-ds-1302238740.cos.ap-guangzhou.myqcloud.com/ds.zip}"
TMP_ZIP="${TMPDIR:-/tmp}/switch-ds-$$.zip"

if ! command -v curl >/dev/null 2>&1; then
  echo "need curl" >&2
  exit 1
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo "need unzip (yum install -y unzip / apt install -y unzip)" >&2
  exit 1
fi

echo "Downloading: ${DS_ZIP_URL}"
curl -fL --retry 3 --progress-bar -o "${TMP_ZIP}" "${DS_ZIP_URL}"

size_mb="$("$(command -v python3 || command -v python)" -c "import os; print(round(os.path.getsize('${TMP_ZIP}')/1024/1024, 2))")"
echo "Downloaded ${size_mb} MB, extracting -> ${DS_DIR}"

rm -rf "${DS_DIR}"
mkdir -p "${DS_DIR}"
unzip -q "${TMP_ZIP}" -d "${DS_DIR}"
rm -f "${TMP_ZIP}"

# If zip contains a single top-level folder, flatten it.
shopt -s nullglob
entries=("${DS_DIR}"/*)
if [[ "${#entries[@]}" -eq 1 && -d "${entries[0]}" ]]; then
  tmp_flat="${DS_DIR}.flatten.$$"
  mv "${entries[0]}" "${tmp_flat}"
  rm -rf "${DS_DIR}"
  mv "${tmp_flat}" "${DS_DIR}"
fi
shopt -u nullglob

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
  echo "extract ok, but no .x86_64 binary found under ${DS_DIR}" >&2
  echo "zip top-level listing:" >&2
  ls -la "${DS_DIR}" >&2 || true
  exit 1
fi

chmod +x "${BINARY}"
find "${DS_DIR}" -type f -name "*.so" -exec chmod +x {} \;

echo "DS ready: ${BINARY}"
echo "Start matcher with:"
echo "  ./scripts/start.sh <public-host-ip>"
