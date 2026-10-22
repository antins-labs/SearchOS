#!/usr/bin/env bash
set -euo pipefail
umask 077
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"

usage() {
  cat <<'HELP'
用法：bash deploy/searchos.sh COMMAND
  build               从当前代码构建镜像
  up                  启动服务并等待健康检查
  status              查看服务状态
  doctor              检查存储、浏览器与技能沙箱（不调用模型）
  logs                查看最近日志（Ctrl-C 退出）
  token               在当前终端显示管理员凭据（不要转发）
  stop                停止服务，保留全部数据
  backup [FILE.tgz]    停止写入，备份全部数据，再恢复原运行服务
  restore FILE.tgz    仅恢复到空数据卷；不会覆盖已有数据或自动启动服务
HELP
}

if [[ "${1:-}" == "--help" || $# -eq 0 ]]; then usage; exit 0; fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "请先复制 deploy/.env.example 为 deploy/.env，填写域名和邮箱。" >&2
  exit 1
fi
command -v docker >/dev/null || { echo "请先安装 Docker Engine 和 Compose v2。" >&2; exit 1; }
compose() { docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/compose.yaml" "$@"; }
compose config --quiet

case "$1" in
  build) compose build --pull ;;
  up) compose up -d --wait --wait-timeout 180 ;;
  status) compose ps ;;
  doctor) compose exec -T api python /app/deploy/doctor.py ;;
  logs) compose logs --tail=100 -f ;;
  token) compose exec -T api cat /data/assistant/admin-token; printf '\n' ;;
  stop) compose stop ;;
  backup)
    OUTPUT="${2:-$DEPLOY_DIR/backups/searchos-$(date -u +%Y%m%dT%H%M%SZ).tgz}"
    [[ "$OUTPUT" = /* ]] || OUTPUT="$(pwd)/$OUTPUT"
    [[ ! -e "$OUTPUT" ]] || { echo "备份文件已存在：$OUTPUT" >&2; exit 1; }
    mkdir -p "$(dirname "$OUTPUT")"
    RUNNING=()
    while IFS= read -r item; do [[ -z "$item" ]] || RUNNING+=("$item"); done < <(compose ps --status running --services)
    resume() { if ((${#RUNNING[@]})); then compose start "${RUNNING[@]}" >&2; fi; }
    trap resume EXIT
    compose stop >&2
    if compose run --rm --no-deps -T --entrypoint python api /app/deploy/data_archive.py backup > "$OUTPUT.partial"; then
      mv "$OUTPUT.partial" "$OUTPUT"
      echo "备份完成：$OUTPUT（包含密钥，请妥善保存到服务器之外）"
    else
      rm -f "$OUTPUT.partial"
      exit 1
    fi
    ;;
  restore)
    [[ $# -eq 2 && -f "$2" ]] || { echo "请指定备份文件路径。" >&2; exit 1; }
    compose stop
    compose run --rm --no-deps -T --entrypoint python api /app/deploy/data_archive.py restore < "$2"
    echo "恢复完成。核对域名与镜像版本后，再执行 up。"
    ;;
  *) usage; exit 2 ;;
esac
