#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="${TESTGEN_INSTALL_DIR:-${HOME}/testgen}"
TESTGEN_UI_PORT="${TESTGEN_UI_PORT:-8501}"
TESTGEN_API_PORT="${TESTGEN_API_PORT:-8530}"
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"
curl -o dk-installer.py 'https://raw.githubusercontent.com/DataKitchen/data-observability-installer/main/dk-installer.py'
python3 dk-installer.py --no-analytics tg install --docker --no-demo --port="${TESTGEN_UI_PORT}" --api-port="${TESTGEN_API_PORT}"
echo "TestGen UI:  http://localhost:${TESTGEN_UI_PORT}"
echo "TestGen API: http://localhost:${TESTGEN_API_PORT}"
echo "Credentials: ${INSTALL_DIR}/dk-tg-credentials.txt"
