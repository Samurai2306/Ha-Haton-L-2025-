#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source .venv/bin/activate || { echo "Run scripts/setup_venv.sh first"; exit 1; }

# Allow custom flights file via env FILE_FLIGHTS
python3 etl_from_csv.py

