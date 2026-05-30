#!/usr/bin/env bash
# ============================================================
# stop.sh - 停止 FunASR 服务
#
# 用法:
#   bash scripts/stop.sh           # 优雅停止
#   bash scripts/stop.sh --clean   # 停止并清理容器/网络（保留数据）
#   bash scripts/stop.sh --purge   # 停止并删除所有数据（危险！）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $*"; }

CLEAN=false
PURGE=false

for arg in "$@"; do
    case $arg in
        --clean) CLEAN=true ;;
        --purge) PURGE=true ;;
    esac
done

if $PURGE; then
    echo -e "${RED}警告: --purge 将删除所有日志数据！${NC}"
    read -rp "确认? (输入 'yes' 继续): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        echo "已取消"
        exit 0
    fi
fi

log "停止 FunASR 服务..."

if $PURGE; then
    docker compose down -v --remove-orphans
    warn "日志数据已删除"
elif $CLEAN; then
    docker compose down --remove-orphans
    ok "服务已停止并清理"
else
    # 优雅停止：给服务 30 秒完成正在处理的请求
    docker compose stop --timeout 30
    ok "服务已优雅停止（正在处理的请求已完成）"
fi

echo ""
echo "重新启动: bash scripts/start.sh"
