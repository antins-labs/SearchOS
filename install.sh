#!/usr/bin/env bash
# SearchOS 一键安装：Python 环境、Access Skill、浏览器运行时与 Web 前端。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SEARCHOS_VENV:-$ROOT/.venv}"
PROFILE="access"
WITH_DEV=0
WITH_WEB=1
WITH_BROWSER=1
PYTHON_BIN="${PYTHON:-}"

usage() {
  printf '%s\n' \
    "用法：./install.sh [选项]" \
    "" \
    "  --core           只安装 CLI/TUI 与 Web 后端的基础 Python 依赖" \
    "  --all            安装评测、可选搜索/浏览后端与可观测性依赖" \
    "  --dev            额外安装 pytest、pytest-asyncio 与 Ruff" \
    "  --no-web         跳过 Web 前端 npm 依赖" \
    "  --no-browser     跳过 Playwright Chromium 下载" \
    "  --python PATH    指定 Python 3.11+ 可执行文件" \
    "  --venv PATH      指定虚拟环境目录（默认 .venv）" \
    "  -h, --help       显示帮助"
}

while (($#)); do
  case "$1" in
    --core) PROFILE="core" ;;
    --all) PROFILE="all" ;;
    --dev) WITH_DEV=1 ;;
    --no-web) WITH_WEB=0 ;;
    --no-browser) WITH_BROWSER=0 ;;
    --python)
      shift
      [[ $# -gt 0 ]] || { echo "--python 需要一个路径" >&2; exit 2; }
      PYTHON_BIN="$1"
      ;;
    --venv)
      shift
      [[ $# -gt 0 ]] || { echo "--venv 需要一个路径" >&2; exit 2; }
      VENV_DIR="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知选项：$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

python_is_compatible() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    >/dev/null 2>&1
}

if [[ -n "$PYTHON_BIN" ]]; then
  python_is_compatible "$PYTHON_BIN" || {
    echo "指定的 Python 不可用或版本低于 3.11：$PYTHON_BIN" >&2
    exit 1
  }
else
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_compatible "$candidate"; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "未找到 Python 3.11+。请先安装 Python，再运行 ./install.sh。" >&2
  exit 1
fi

if [[ "$VENV_DIR" != /* ]]; then
  VENV_DIR="$ROOT/$VENV_DIR"
fi

echo "使用 $($PYTHON_BIN --version) 创建环境：$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  VENV_PYTHON="$VENV_DIR/bin/python"
  VENV_SEARCHOS="$VENV_DIR/bin/searchos"
  ACTIVATE="$VENV_DIR/bin/activate"
elif [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
  VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
  VENV_SEARCHOS="$VENV_DIR/Scripts/searchos.exe"
  ACTIVATE="$VENV_DIR/Scripts/activate"
else
  echo "虚拟环境创建失败：找不到 Python 可执行文件" >&2
  exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip

case "$PROFILE" in
  core) EXTRAS="" ;;
  access) EXTRAS="access" ;;
  all) EXTRAS="all" ;;
esac
if ((WITH_DEV)); then
  EXTRAS="${EXTRAS:+$EXTRAS,}dev"
fi

cd "$ROOT"
if [[ -n "$EXTRAS" ]]; then
  "$VENV_PYTHON" -m pip install -e ".[${EXTRAS}]"
else
  "$VENV_PYTHON" -m pip install -e .
fi

if ((WITH_BROWSER)) && [[ "$PROFILE" != "core" ]]; then
  echo "安装 Playwright Chromium…"
  "$VENV_PYTHON" -m playwright install chromium
fi

if ((WITH_WEB)); then
  command -v node >/dev/null 2>&1 || {
    echo "未找到 Node.js；Web 前端要求 Node.js >= 20.9。" >&2
    exit 1
  }
  node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>20 || (a===20 && b>=9) ? 0 : 1)' || {
    echo "Node.js 版本过低：$(node --version)；Web 前端要求 >= 20.9。" >&2
    exit 1
  }
  command -v npm >/dev/null 2>&1 || {
    echo "未找到 npm。" >&2
    exit 1
  }
  echo "安装 Web 前端依赖…"
  npm ci --prefix "$ROOT/web/frontend"
fi

echo "执行安装自检…"
"$VENV_PYTHON" -m pip check
"$VENV_SEARCHOS" --help >/dev/null
PYTHONPATH="$ROOT:$ROOT/web" "$VENV_PYTHON" -c 'from api.main import app; assert app.title == "SearchOS API"'

ACTIVE_SEARCHOS="$(command -v searchos 2>/dev/null || true)"
if [[ -n "$ACTIVE_SEARCHOS" && "$ACTIVE_SEARCHOS" != "$VENV_SEARCHOS" ]]; then
  printf '\n%s\n' \
    "检测到同名 searchos 命令：$ACTIVE_SEARCHOS" \
    "它不属于当前仓库。请激活下面的虚拟环境并刷新 Shell 命令缓存。"
fi

printf '\n%s\n' \
  "安装完成。" \
  "激活环境：source \"$ACTIVATE\"" \
  "刷新缓存：hash -r" \
  "入口校验：command -v searchos  # 应输出 $VENV_SEARCHOS" \
  "启动 CLI：searchos" \
  "无需激活也可运行：\"$VENV_SEARCHOS\"" \
  "启动 Web：./web/start.sh"
