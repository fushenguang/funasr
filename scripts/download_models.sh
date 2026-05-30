#!/usr/bin/env bash
# ============================================================
# download_models.sh - 从 ModelScope 预下载模型到本地
#
# 用法:
#   bash scripts/download_models.sh              # 下载默认模型集
#   bash scripts/download_models.sh --ws-only    # 只下载 WebSocket Runtime 模型
#   bash scripts/download_models.sh --api-only   # 只下载 HTTP API 模型
#   bash scripts/download_models.sh --list       # 列出已下载的模型
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_DIR/models"

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 解析参数 ──────────────────────────────────────────────────
DOWNLOAD_WS=true
DOWNLOAD_API=true
LIST_ONLY=false

for arg in "$@"; do
    case $arg in
        --ws-only)  DOWNLOAD_API=false ;;
        --api-only) DOWNLOAD_WS=false ;;
        --list)     LIST_ONLY=true ;;
        --help|-h)
            grep '^# ' "$0" | head -12 | sed 's/^# //'
            exit 0
            ;;
    esac
done

# ── 列出已有模型 ──────────────────────────────────────────────
if $LIST_ONLY; then
    log "已下载的模型:"
    if [[ -d "$MODELS_DIR" ]]; then
        find "$MODELS_DIR" -mindepth 1 -maxdepth 2 -type d | sort
        echo ""
        TOTAL=$(du -sh "$MODELS_DIR" 2>/dev/null | cut -f1)
        log "总占用: $TOTAL"
    else
        warn "模型目录不存在: $MODELS_DIR"
    fi
    exit 0
fi

# ── 前置检查 ──────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    err "需要 python3，请先安装"
fi

mkdir -p "$MODELS_DIR"
log "模型将下载到: $MODELS_DIR"

# ── 安装 modelscope（如果没有）────────────────────────────────
if ! python3 -c "import modelscope" &>/dev/null; then
    log "安装 modelscope..."
    pip install modelscope --quiet
fi

# ── 下载函数 ──────────────────────────────────────────────────
download_model() {
    local model_id="$1"
    local desc="$2"
    local target_dir="$MODELS_DIR/$(echo "$model_id" | tr '/' '__')"

    if [[ -d "$target_dir" ]] && [[ -n "$(ls -A "$target_dir" 2>/dev/null)" ]]; then
        ok "已存在，跳过: $desc ($model_id)"
        return 0
    fi

    log "下载 $desc ..."
    log "  模型 ID: $model_id"

    python3 - <<EOF
import sys
import os
os.environ["MODELSCOPE_CACHE"] = "${MODELS_DIR}"
from modelscope import snapshot_download
try:
    path = snapshot_download(
        model_id="${model_id}",
        cache_dir="${MODELS_DIR}",
        local_dir="${target_dir}",
    )
    print(f"  下载完成: {path}")
except Exception as e:
    print(f"  下载失败: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    ok "下载完成: $desc"
}

# ── 模型列表 ──────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo " FunASR 模型下载"
echo "════════════════════════════════════════════════════════"

# HTTP API 模型（SenseVoice - 主力模型）
if $DOWNLOAD_API; then
    echo ""
    log "─ HTTP API 模型 ─"

    download_model \
        "iic/SenseVoiceSmall" \
        "SenseVoice Small（多语言，推荐）"

    # Paraformer 可选，注释掉节省空间
    # download_model \
    #     "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch" \
    #     "Paraformer Large（中文离线）"
fi

# WebSocket Runtime 模型
if $DOWNLOAD_WS; then
    echo ""
    log "─ WebSocket Runtime 模型 ─"

    download_model \
        "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch" \
        "Paraformer Large ASR（实时流）"

    download_model \
        "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch" \
        "FSMN VAD（语音活动检测）"

    download_model \
        "damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch" \
        "CT-Transformer 标点恢复"

    download_model \
        "thuduj12/fst_itn_zh" \
        "FST ITN 反文本规范化"
fi

# ── 完成 ──────────────────────────────────────────────────────
echo ""
TOTAL=$(du -sh "$MODELS_DIR" 2>/dev/null | cut -f1)
ok "所有模型下载完成！总占用: $TOTAL"
log "模型目录: $MODELS_DIR"
echo ""
echo "下一步: bash scripts/start.sh"
