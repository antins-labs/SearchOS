#!/usr/bin/env bash
# SearchOS — one command to start API (8000) + Frontend (3000).
#   ./web/start.sh          # both
#   ./web/start.sh api      # API only
#   ./web/start.sh web      # frontend only
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"   # web/.. = repo root
cd "$REPO"

resolve_python() {
  if [ -n "${SEARCHOS_PYTHON:-}" ]; then
    printf '%s\n' "$SEARCHOS_PYTHON"
  elif [ -x "$REPO/.venv/bin/python" ]; then
    printf '%s\n' "$REPO/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python
  fi
}

start_api() {
  echo "Starting API on :8000 …"
  PYTHON_BIN="$(resolve_python)"
  [ -n "$PYTHON_BIN" ] || {
    echo "Python 未找到；请先运行 ./install.sh。" >&2
    return 1
  }
  "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
    echo "SearchOS 要求 Python 3.11+；请先运行 ./install.sh。" >&2
    return 1
  }
  "$PYTHON_BIN" -c 'import uvicorn' 2>/dev/null || {
    echo "当前 Python 环境未安装 SearchOS；请先运行 ./install.sh。" >&2
    return 1
  }
  # --app-dir web makes the `api` package importable; PYTHONPATH=repo for `searchos`.
  PYTHONPATH="$REPO" "$PYTHON_BIN" -m uvicorn api.main:app --app-dir web --host 0.0.0.0 --port 8000 --reload
}

start_web() {
  echo "Starting frontend on :3000 …"
  cd "$REPO/web/frontend"
  [ -d node_modules ] || npm ci
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
