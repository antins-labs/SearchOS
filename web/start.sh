#!/usr/bin/env bash
# SearchOS — one command to start API (8000) + Frontend (3000).
#   ./web/start.sh          # both
#   ./web/start.sh api      # API only
#   ./web/start.sh web      # frontend only
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"   # web/.. = repo root
cd "$REPO"

start_api() {
  echo "Starting API on :8000 …"
  # --app-dir web makes the `api` package importable; PYTHONPATH=repo for `searchos`.
  if command -v uv >/dev/null 2>&1; then
    PYTHONPATH="$REPO" uv run uvicorn api.main:app --app-dir web --host 0.0.0.0 --port 8000 --reload
  else
    # Fallback: no uv installed — use uvicorn from the current Python env.
    PYTHONPATH="$REPO" python -m uvicorn api.main:app --app-dir web --host 0.0.0.0 --port 8000 --reload
  fi
}

start_web() {
  echo "Starting frontend on :3000 …"
  cd "$REPO/web/frontend"
  [ -d node_modules ] || npm install
  npm run dev
}

case "${1:-all}" in
  api) start_api ;;
  web|frontend) start_web ;;
  all)
    start_api & API_PID=$!
    start_web & WEB_PID=$!
    trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT INT TERM
    wait
    ;;
  *) echo "usage: $0 [all|api|web]"; exit 1 ;;
esac
