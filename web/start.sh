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
  echo "Starting API on http://127.0.0.1:8000 …"
  PYTHON_BIN="$(resolve_python)"
  [ -n "$PYTHON_BIN" ] || {
    echo "Python 未找到；请先运行 ./install.sh。" >&2
    return 1
  }
  "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || {
    echo "SearchOS 要求 Python 3.11+；请先运行 ./install.sh。" >&2
    return 1
  }
  "$PYTHON_BIN" -c 'import uvicorn, multipart' 2>/dev/null || {
    echo "当前 Python 环境缺少 Web API 依赖；请先运行 ./install.sh --core。" >&2
    return 1
  }
  # API 承载长时间后台作业，不能监视生成中的技能脚本并自动重启。
  # 后端代码修改后手动重启；前端仍由 Next.js 提供热更新。
  # --app-dir web makes the `api` package importable; PYTHONPATH=repo for `searchos`.
  PYTHONPATH="$REPO" "$PYTHON_BIN" -m uvicorn api.main:app --app-dir web --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
}

start_web() {
  echo "Starting frontend on http://127.0.0.1:3000 …"
  cd "$REPO/web/frontend"
  # node_modules is intentionally not versioned. A branch switch can therefore
  # leave it populated with another branch's dependency tree; merely checking
  # that the directory exists misses packages newly required by this branch.
  local dependency_fingerprint
  dependency_fingerprint="$(shasum package.json package-lock.json | shasum | awk '{print $1}')"
  local fingerprint_file="node_modules/.searchos-dependency-fingerprint"
  local installed_fingerprint=""
  [ -f "$fingerprint_file" ] && installed_fingerprint="$(<"$fingerprint_file")"

  if [ ! -d node_modules ] || [ "$installed_fingerprint" != "$dependency_fingerprint" ]; then
    echo "Frontend dependencies changed; synchronizing with package-lock.json …"
    npm ci
    printf '%s\n' "$dependency_fingerprint" > "$fingerprint_file"
  fi
  npm run dev -- --hostname 127.0.0.1
}

case "${1:-all}" in
  api) start_api ;;
  web|frontend) start_web ;;
  all)
    start_api & API_PID=$!
    start_web & WEB_PID=$!
    cleanup() {
      kill "$API_PID" "$WEB_PID" 2>/dev/null || true
    }
    trap cleanup EXIT
    trap 'cleanup; exit 130' INT TERM

    # Bash 3.2 has no `wait -n`. Monitor both children so a failed backend
    # cannot leave a misleading, half-running frontend behind.
    while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
      sleep 1
    done

    STATUS=1
    if ! kill -0 "$API_PID" 2>/dev/null; then
      if wait "$API_PID"; then
        STATUS=0
      else
        STATUS=$?
      fi
      echo "API 已退出（状态码 ${STATUS}），正在停止前端。" >&2
    else
      if wait "$WEB_PID"; then
        STATUS=0
      else
        STATUS=$?
      fi
      echo "前端已退出（状态码 ${STATUS}），正在停止 API。" >&2
    fi
    exit "$STATUS"
    ;;
  *) echo "usage: $0 [all|api|web]"; exit 1 ;;
esac
