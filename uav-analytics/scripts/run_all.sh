#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 1) Python env + deps (always ensure up-to-date)
echo "[SETUP] Preparing Python venv and dependencies..."
./scripts/setup_venv.sh
source .venv/bin/activate

# 2) ETL from CSV (uses FILE_FLIGHTS if set, else flights_normalized.csv)
if [ -n "${FILE_FLIGHTS:-}" ]; then
  FLIGHTS_FILE="$FILE_FLIGHTS"
else
  FLIGHTS_FILE="${FILE_FLIGHTS:-$ROOT_DIR/flights_normalized.csv}"
fi
if [ -f "$FLIGHTS_FILE" ]; then
  echo "[ETL] Using flights file: $FLIGHTS_FILE"
  export FILE_FLIGHTS="$FLIGHTS_FILE"
  python3 etl_from_csv.py || true
else
  echo "[ETL] Flights file not found ($FLIGHTS_FILE). Skipping ETL."
  echo "      If you have your own CSV, set env FILE_FLIGHTS=/path/to/your.csv and re-run."
fi

# 3) Start API in background and wait until ready
echo "[API] Starting at http://127.0.0.1:8000 ..."
mkdir -p logs
uvicorn api.main:app --host :: --port 8000 --reload > logs/api.log 2>&1 &
API_PID=$!

wait_api() {
  local tries=30
  for i in $(seq 1 $tries); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
      echo "[API] Ready."
      return 0
    fi
    sleep 1
  done
  echo "[API] Failed to become ready. Last logs:" >&2
  tail -n 100 logs/api.log >&2 || true
  return 1
}

cleanup() {
  echo "\n[STOP] Stopping API (pid $API_PID)..."
  kill $API_PID 2>/dev/null || true
}
trap cleanup EXIT

wait_api

# 4) Web dev server (uses IPv4 URL to avoid ::1 issues)
cd web
export NEXT_PUBLIC_API_BASE="http://127.0.0.1:8000"
if [ ! -d node_modules ]; then
  echo "[WEB] Installing npm deps..."
  npm ci
fi
echo "[WEB] Starting Next.js dev server..."
npm run dev
