#!/usr/bin/env bash
# ============================================================
# start.sh - 启动 FunASR 服务
#
# 用法:
#   bash scripts/start.sh                   # 正常启动
#   bash scripts/start.sh --skip-preflight  # 跳过预检（不推荐）
#   bash scripts/start.sh --scale-api 2     # 启动 2 个 API 实例
#   bash scripts/start.sh --build           # 强制重新构建镜像
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $*"; }

# ── 参数解析 ──────────────────────────────────────────────────
SKIP_PREFLIGHT=false
API_SCALE=1
BUILD_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-preflight) SKIP_PREFLIGHT=true; shift ;;
        --scale-api)      API_SCALE="$2"; shift 2 ;;
        --build)          BUILD_FLAG="--build"; shift ;;
        --help|-h)
            grep '^# ' "$0" | head -10 | sed 's/^# //'
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

echo ""
echo "════════════════════════════════════════════════════════"
echo " FunASR 服务启动"
echo "════════════════════════════════════════════════════════"

# ── 环境预检 ──────────────────────────────────────────────────
if ! $SKIP_PREFLIGHT; then
    log "运行环境预检..."
    if ! bash "$SCRIPT_DIR/preflight.sh"; then
        echo ""
        echo -e "${RED}预检失败，启动终止。使用 --skip-preflight 强制跳过（不推荐）。${NC}"
        exit 1
    fi
fi

# ── 确保 .env 存在 ─────────────────────────────────────────────
if [[ ! -f .env ]]; then
    warn ".env 不存在，从 .env.example 复制..."
    cp .env.example .env
    warn "请检查 .env 配置是否符合你的环境"
fi

# ── 创建必要目录 ──────────────────────────────────────────────
for DIR in models logs/nginx logs/api logs/runtime logs/system; do
    mkdir -p "$DIR"
done
touch config/hotwords.txt 2>/dev/null || true

# ── 构建并启动 ────────────────────────────────────────────────
log "启动服务 (API 实例数: $API_SCALE)..."

docker compose up -d $BUILD_FLAG \
    --scale funasr-api="$API_SCALE" \
    --remove-orphans

# ── 等待健康检查 ──────────────────────────────────────────────
log "等待服务就绪（模型加载约需 30~120 秒）..."

MAX_WAIT=180
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))

    # 检查 nginx 是否运行
    if ! docker compose ps nginx | grep -q "running\|Up"; then
        continue
    fi

    # 通过 nginx 做健康检查
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time 5 http://localhost/health 2>/dev/null || echo "000")

    if [[ "$HTTP_STATUS" == "200" ]]; then
        ok "服务已就绪！(等待了 ${ELAPSED}s)"
        break
    fi

    echo -ne "\r  等待中... ${ELAPSED}s / ${MAX_WAIT}s  (HTTP: $HTTP_STATUS)"
done

echo ""

if [[ "$HTTP_STATUS" != "200" ]]; then
    warn "服务启动超时，请检查日志:"
    warn "  docker compose logs --tail=50 funasr-api"
    warn "  docker compose logs --tail=50 funasr-ws"
    exit 1
fi

# ── 打印访问信息 ──────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo -e " ${GREEN}FunASR 服务已启动${NC}"
echo "════════════════════════════════════════════════════════"

# 获取本机 IP
HOST_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")

echo ""
echo "  HTTP API (文件转写):"
echo -e "    ${GREEN}http://$HOST_IP/v1/audio/transcriptions${NC}"
echo ""
echo "  WebSocket (实时流):"
echo -e "    ${GREEN}ws://$HOST_IP/ws${NC}"
echo ""
echo "  Swagger 文档:"
echo -e "    ${GREEN}http://$HOST_IP/docs${NC}"
echo ""
echo "  健康检查:"
echo -e "    ${GREEN}http://$HOST_IP/health${NC}"
echo ""
echo "  日志查看:"
echo "    bash scripts/logs.sh"
echo ""
echo "  停止服务:"
echo "    bash scripts/stop.sh"
echo ""

# ── 运行 smoke test ───────────────────────────────────────────
log "运行快速 smoke test..."
SMOKE_RESULT=$(curl -sf \
    -o /dev/null -w "%{http_code}" \
    --max-time 10 \
    http://localhost/health || echo "000")

if [[ "$SMOKE_RESULT" == "200" ]]; then
    ok "Smoke test 通过 ✓"
else
    warn "Smoke test 失败 (HTTP $SMOKE_RESULT)，请手动检查"
fi

echo ""
