#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source .venv/bin/activate || { echo "Run scripts/setup_venv.sh first"; exit 1; }

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
exec uvicorn api.main:app --host "$API_HOST" --port "$API_PORT" --reload
