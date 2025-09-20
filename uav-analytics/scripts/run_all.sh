#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 1) Python env + deps (always ensure up-to-date)
echo "[SETUP] Preparing Python venv and dependencies..."
bash scripts/setup_venv.sh
source .venv/bin/activate

# 2) Pick data files (prefer provided env, else docs/, else local)
pick_data_file() {
  local varname="$1"; shift
  local explicit="${!varname:-}"
  if [ -n "$explicit" ] && [ -f "$explicit" ]; then
    echo "$explicit"; return 0
  fi
  # try docs/
  local base="$ROOT_DIR/.."  # parent of uav-analytics
  local fname="$1"; shift || true
  if [ -f "$base/docs/$fname" ]; then
    echo "$base/docs/$fname"; return 0
  fi
  # try local
  if [ -f "$ROOT_DIR/$fname" ]; then
    echo "$ROOT_DIR/$fname"; return 0
  fi
  echo ""; return 1
}

FLIGHTS_FILE="$(pick_data_file FILE_FLIGHTS flights_normalized.csv || true)"
DAILY_FILE="$(pick_data_file FILE_DAILY daily_aggregates.csv || true)"
FORECAST_FILE="$(pick_data_file FILE_FORECAST forecast_14d.csv || true)"

if [ -n "$FLIGHTS_FILE" ]; then
  echo "[ETL] Using flights file: $FLIGHTS_FILE"
  export FILE_FLIGHTS="$FLIGHTS_FILE"
  # Optional enrichment recompute
  python3 etl_from_csv.py || true
else
  echo "[ETL] Flights file not found. Set FILE_FLIGHTS=/path/to/your.csv and re-run." >&2
fi

# Export other known files for API convenience (if present)
[ -n "$DAILY_FILE" ] && export FILE_DAILY="$DAILY_FILE"
[ -n "$FORECAST_FILE" ] && export FILE_FORECAST="$FORECAST_FILE"

# 3) Start API in background and wait until ready (pick a free port)
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT_BASE="${API_PORT:-8000}"

find_free_port() {
  local start=${1:-8000}
  local end=$((start+20))
  for p in $(seq "$start" "$end"); do
    if ! lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

API_PORT="$(find_free_port "$API_PORT_BASE")"
if [ -z "$API_PORT" ]; then
  echo "[API] No free port found in range $API_PORT_BASE..$((API_PORT_BASE+20))." >&2
  exit 1
fi

echo "[API] Starting at http://$API_HOST:$API_PORT ..."
mkdir -p logs
uvicorn api.main:app --host "$API_HOST" --port "$API_PORT" --reload > logs/api.log 2>&1 &
API_PID=$!

wait_api() {
  local tries=40
  for i in $(seq 1 $tries); do
    if curl -fsS "http://$API_HOST:$API_PORT/health" >/dev/null 2>&1; then
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

# 4) Web dev server
cd web
export NEXT_PUBLIC_API_BASE="http://$API_HOST:$API_PORT"
if [ ! -d node_modules ]; then
  echo "[WEB] Installing npm deps..."
  if ! npm ci; then
    echo "[WEB] npm ci failed, retrying with --legacy-peer-deps..."
    npm ci --legacy-peer-deps
  fi
fi
echo "[WEB] Starting Next.js dev server (API=$NEXT_PUBLIC_API_BASE)..."
npm run dev
