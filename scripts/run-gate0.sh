#!/bin/sh
set -eu

api_pid=""
web_pid=""

cleanup() {
  if [ -n "$web_pid" ]; then
    kill "$web_pid" 2>/dev/null || true
  fi
  if [ -n "$api_pid" ]; then
    kill "$api_pid" 2>/dev/null || true
  fi
}

stop() {
  cleanup
  trap - EXIT
  echo "Gate 0 services stopped"
  exit 0
}

trap cleanup EXIT
trap stop INT TERM

PHOTOFOLD_DEMO_DATASET="${PHOTOFOLD_DEMO_DATASET:-data/demo/hdrplus-static}" \
  .venv/bin/uvicorn photofold.main:app --host 127.0.0.1 --port 8000 &
api_pid=$!

npm run dev --workspace apps/web &
web_pid=$!

attempt=0
while [ "$attempt" -lt 60 ]; do
  if curl --silent --fail http://127.0.0.1:8000/v1/health >/dev/null 2>&1 && \
     curl --silent --fail http://127.0.0.1:3000 >/dev/null 2>&1; then
    echo "Gate 0 services ready"
    echo "Frontend: http://127.0.0.1:3000"
    echo "API docs: http://127.0.0.1:8000/docs"
    wait
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done

echo "Gate 0 services failed to become ready" >&2
exit 1
