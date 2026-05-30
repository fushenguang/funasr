#!/usr/bin/env bash
# ============================================================
# logs.sh - 日志查看工具
#
# 用法:
#   bash scripts/logs.sh                 # 查看所有服务实时日志
#   bash scripts/logs.sh api             # 只看 API 服务日志
#   bash scripts/logs.sh ws              # 只看 WebSocket Runtime 日志
#   bash scripts/logs.sh nginx           # 只看 Nginx 日志
#   bash scripts/logs.sh --errors        # 只看错误日志
#   bash scripts/logs.sh --tail 100      # 查看最后 100 行
#   bash scripts/logs.sh --since 1h      # 查看最近 1 小时
#   bash scripts/logs.sh --stats         # 显示请求统计
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'
log() { echo -e "${BLUE}[logs]${NC} $*"; }

SERVICE=""
TAIL=50
SINCE=""
ERRORS_ONLY=false
STATS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        api|funasr-api)     SERVICE="funasr-api"; shift ;;
        ws|funasr-ws)       SERVICE="funasr-ws"; shift ;;
        nginx)              SERVICE="nginx"; shift ;;
        --errors)           ERRORS_ONLY=true; shift ;;
        --tail)             TAIL="$2"; shift 2 ;;
        --since)            SINCE="$2"; shift 2 ;;
        --stats)            STATS=true; shift ;;
        --help|-h)
            grep '^# ' "$0" | head -12 | sed 's/^# //'
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# ── 统计模式 ──────────────────────────────────────────────────
if $STATS; then
    LOG_FILE="$PROJECT_DIR/logs/api/funasr-api.log"
    if [[ ! -f "$LOG_FILE" ]]; then
        echo "日志文件不存在: $LOG_FILE"
        exit 1
    fi

    echo ""
    echo "════════════════════════════════════════════════════════"
    echo " FunASR API 请求统计"
    echo "════════════════════════════════════════════════════════"
    echo ""

    # 需要 jq
    if command -v jq &>/dev/null; then
        echo "📊 总请求数:"
        grep -c '"event":"transcription_done"' "$LOG_FILE" 2>/dev/null || echo "  0"

        echo ""
        echo "📊 错误数:"
        grep -c '"event":"transcription_error"' "$LOG_FILE" 2>/dev/null || echo "  0"

        echo ""
        echo "📊 平均推理时间 (s):"
        grep '"event":"transcription_done"' "$LOG_FILE" 2>/dev/null | \
            jq -r '.inference_time_s' 2>/dev/null | \
            awk '{sum+=$1; count++} END {if(count>0) printf "  %.3f s (n=%d)\n", sum/count, count}' \
            || echo "  N/A"

        echo ""
        echo "📊 最近 10 次转写:"
        grep '"event":"transcription_done"' "$LOG_FILE" 2>/dev/null | \
            tail -10 | \
            jq -r '[.timestamp, .filename, .inference_time_s, .audio_duration_s] | @tsv' 2>/dev/null | \
            awk 'BEGIN{printf "  %-25s %-30s %-12s %-12s\n","时间","文件","推理(s)","时长(s)"}
                       {printf "  %-25s %-30s %-12s %-12s\n",$1,$2,$3,$4}' \
            || echo "  N/A"
    else
        warn "安装 jq 后可以看详细统计: sudo apt install jq"
        echo ""
        echo "简易统计:"
        echo "  转写成功: $(grep -c 'transcription_done' "$LOG_FILE" 2>/dev/null || echo 0)"
        echo "  转写失败: $(grep -c 'transcription_error' "$LOG_FILE" 2>/dev/null || echo 0)"
    fi

    echo ""

    # Nginx 访问统计
    NGINX_LOG="$PROJECT_DIR/logs/nginx/access.log"
    if [[ -f "$NGINX_LOG" ]] && command -v jq &>/dev/null; then
        echo "📊 Nginx 请求统计 (最近 1000 条):"
        tail -1000 "$NGINX_LOG" 2>/dev/null | \
            jq -r '.status' 2>/dev/null | \
            sort | uniq -c | sort -rn | \
            awk '{printf "  HTTP %-6s %s 次\n", $2, $1}' \
            || true
    fi

    exit 0
fi

# ── 构建 docker compose logs 参数 ─────────────────────────────
COMPOSE_ARGS=("logs" "--tail=$TAIL" "--follow")
[[ -n "$SINCE" ]] && COMPOSE_ARGS+=("--since=$SINCE")
[[ -n "$SERVICE" ]] && COMPOSE_ARGS+=("$SERVICE")

if $ERRORS_ONLY; then
    # 过滤错误日志
    docker compose "${COMPOSE_ARGS[@]}" 2>&1 | grep -i "error\|ERROR\|failed\|FAILED\|exception" || true
else
    docker compose "${COMPOSE_ARGS[@]}"
fi
