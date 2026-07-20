#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET="${1:-data/real-bursts/static-handheld}"
cd "$ROOT"

make prepare-gate3

npm run dev --workspace apps/web &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}

stop() {
  cleanup
  trap - EXIT
  echo "Gate 3P app stopped"
  exit 0
}

trap cleanup EXIT
trap stop INT TERM

for _ in {1..60}; do
  if curl --fail --silent --output /dev/null http://127.0.0.1:3000; then
    echo "Gate 3P app ready at http://127.0.0.1:3000"
    echo "Upload the image files from: $DATASET"
    echo "Press Ctrl-C to stop; run 'make clean-gate3' for complete manual cleanup."
    wait "$SERVER_PID"
    exit $?
  fi
  sleep 1
done

echo "Gate 3P app did not become ready within 60 seconds." >&2
exit 1
