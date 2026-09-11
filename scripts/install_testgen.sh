#!/usr/bin/env bash
set -euo pipefail
mkdir -p "${HOME}/testgen"
cd "${HOME}/testgen"
curl -o dk-installer.py 'https://raw.githubusercontent.com/DataKitchen/data-observability-installer/main/dk-installer.py'
python3 dk-installer.py tg install
