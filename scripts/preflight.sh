#!/usr/bin/env bash
# ============================================================
# preflight.sh - 部署前环境预检
#
# 用法: bash scripts/preflight.sh
# 通过所有检查后，才应该运行 start.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

pass()  { echo -e "  ${GREEN}✓${NC} $*"; ((PASS++))  || true; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $*"; ((WARN++))  || true; }
fail()  { echo -e "  ${RED}✗${NC} $*"; ((FAIL++))  || true; }
section() { echo -e "\n${BLUE}── $* ──${NC}"; }

# ============================================================
section "操作系统"
# ============================================================

OS=$(uname -s)
if [[ "$OS" != "Linux" ]]; then
    fail "当前系统: $OS，生产部署需要 Linux"
else
    DISTRO=$(lsb_release -d 2>/dev/null | cut -f2 || echo "未知")
    pass "操作系统: $DISTRO"
fi

# ============================================================
section "Docker"
# ============================================================

if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "未知")
    pass "Docker 已安装: v$DOCKER_VER"
else
    fail "Docker 未安装。运行: curl -fsSL https://get.docker.com | sh"
fi

if docker compose version &>/dev/null; then
    COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "未知")
    pass "Docker Compose Plugin 已安装: v$COMPOSE_VER"
else
    fail "Docker Compose (plugin 版本) 未安装"
fi

if docker info &>/dev/null; then
    pass "Docker daemon 运行中"
else
    fail "Docker daemon 未运行。运行: sudo systemctl start docker"
fi

# 检查当前用户是否在 docker 组
if groups | grep -q docker; then
    pass "当前用户在 docker 组"
else
    warn "当前用户不在 docker 组，可能需要 sudo 运行 docker 命令"
    warn "修复: sudo usermod -aG docker \$USER && newgrp docker"
fi

# ============================================================
section "NVIDIA GPU"
# ============================================================

if command -v nvidia-smi &>/dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>/dev/null | head -1)
    GPU_NAME=$(echo "$GPU_INFO" | cut -d',' -f1 | xargs)
    GPU_MEM=$(echo "$GPU_INFO" | cut -d',' -f2 | xargs)
    DRIVER=$(echo "$GPU_INFO" | cut -d',' -f3 | xargs)
    pass "GPU: $GPU_NAME (显存: ${GPU_MEM}MiB, 驱动: $DRIVER)"

    # 显存警告
    GPU_MEM_INT=${GPU_MEM%.*}
    if [[ "$GPU_MEM_INT" -lt 8000 ]]; then
        warn "显存 < 8GB，可能无法稳定运行 sensevoice（推荐 ≥ 10GB）"
    elif [[ "$GPU_MEM_INT" -lt 12000 ]]; then
        warn "显存 < 12GB，多实例扩展时注意显存上限"
    else
        pass "显存充足（$GPU_MEM_INT MiB）"
    fi
else
    warn "nvidia-smi 未找到，GPU 不可用，将回退到 CPU 模式（性能会大幅下降）"
fi

# 检查 NVIDIA Container Toolkit
if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi &>/dev/null; then
    pass "NVIDIA Container Toolkit 正常，容器可以访问 GPU"
else
    fail "NVIDIA Container Toolkit 未配置或 GPU 在容器内不可用"
    fail "安装: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
fi

# ============================================================
section "系统资源"
# ============================================================

# 内存
MEM_TOTAL_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
if [[ "$MEM_TOTAL_GB" -lt 8 ]]; then
    fail "内存不足: ${MEM_TOTAL_GB}GB（建议 ≥ 16GB）"
elif [[ "$MEM_TOTAL_GB" -lt 16 ]]; then
    warn "内存: ${MEM_TOTAL_GB}GB（建议 ≥ 16GB，当前可能在高负载下受限）"
else
    pass "内存: ${MEM_TOTAL_GB}GB"
fi

# 磁盘（检查项目目录所在磁盘）
DISK_FREE_GB=$(df -BG "$PROJECT_DIR" | awk 'NR==2 {print $4}' | tr -d 'G')
if [[ "$DISK_FREE_GB" -lt 20 ]]; then
    fail "磁盘可用空间不足: ${DISK_FREE_GB}GB（模型 + 日志需要至少 20GB）"
elif [[ "$DISK_FREE_GB" -lt 50 ]]; then
    warn "磁盘可用空间: ${DISK_FREE_GB}GB（日志长期积累可能不够，建议 ≥ 50GB）"
else
    pass "磁盘可用空间: ${DISK_FREE_GB}GB"
fi

# CPU
CPU_CORES=$(nproc)
pass "CPU 核数: $CPU_CORES"

# ============================================================
section "端口冲突检查"
# ============================================================

# 只检查对宿主机暴露的端口（8000 是容器内部端口，不暴露，不检查）
for PORT in 80 10095; do
    if ss -tlnp 2>/dev/null | grep -q ":${PORT} " || \
       netstat -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        PROC=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | awk '{print $NF}' | head -1)
        warn "端口 $PORT 已被占用: $PROC"
        warn "修改 .env 中对应端口，或停止占用进程"
    else
        pass "端口 $PORT 空闲"
    fi
done

# ============================================================
section "项目配置"
# ============================================================

if [[ -f "$PROJECT_DIR/.env" ]]; then
    pass ".env 文件存在"
    # 用 grep 安全读取（|| true 防止 grep 无匹配时触发 set -e 退出）
    _DEVICE=$(grep -E '^FUNASR_DEVICE=' "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d ' ' | head -1 || true)
    _MODEL=$(grep -E '^FUNASR_MODEL=' "$PROJECT_DIR/.env" | cut -d'=' -f2 | tr -d ' ' | head -1 || true)
    [[ -n "${_DEVICE}" ]] && pass "FUNASR_DEVICE=${_DEVICE}" || warn "FUNASR_DEVICE 未设置，将使用默认值 cuda"
    [[ -n "${_MODEL}" ]] && pass "FUNASR_MODEL=${_MODEL}" || warn "FUNASR_MODEL 未设置，将使用默认值 SenseVoiceSmall"
else
    fail ".env 文件不存在"
    fail "运行: cp .env.example .env 并按需修改"
fi

# 检查模型目录
MODELS_DIR="$PROJECT_DIR/models"
if [[ -d "$MODELS_DIR" ]]; then
    MODEL_COUNT=$(find "$MODELS_DIR" -name "*.pt" -o -name "*.onnx" -o -name "*.bin" 2>/dev/null | wc -l)
    if [[ "$MODEL_COUNT" -gt 0 ]]; then
        pass "模型目录存在，找到 $MODEL_COUNT 个模型文件"
    else
        warn "模型目录存在但为空，首次启动将自动从 ModelScope 下载"
        warn "如需预下载: bash scripts/download_models.sh"
    fi
else
    warn "模型目录不存在，将在首次启动时创建并下载模型"
fi

# 检查热词文件
if [[ -f "$PROJECT_DIR/config/hotwords.txt" ]]; then
    pass "热词文件存在"
else
    warn "config/hotwords.txt 不存在，将创建空文件"
    touch "$PROJECT_DIR/config/hotwords.txt"
fi

# 检查日志目录
for LOG_DIR in logs/nginx logs/api logs/runtime logs/system; do
    if [[ ! -d "$PROJECT_DIR/$LOG_DIR" ]]; then
        mkdir -p "$PROJECT_DIR/$LOG_DIR"
        warn "$LOG_DIR 不存在，已自动创建"
    else
        pass "$LOG_DIR 目录存在"
    fi
done

# ============================================================
section "网络连通性"
# ============================================================

if curl -sf --max-time 5 https://modelscope.cn &>/dev/null; then
    pass "ModelScope 可访问"
elif curl -sf --max-time 5 https://www.modelscope.cn &>/dev/null; then
    pass "ModelScope 可访问（www）"
else
    warn "ModelScope 访问超时，模型下载可能失败"
    warn "如果服务器无法访问外网，请先手动下载模型（参考 docs/offline_setup.md）"
fi

# ============================================================
# 汇总
# ============================================================
echo ""
echo "════════════════════════════════════════"
echo -e "预检结果: ${GREEN}通过 $PASS${NC}  ${YELLOW}警告 $WARN${NC}  ${RED}失败 $FAIL${NC}"
echo "════════════════════════════════════════"

if [[ "$FAIL" -gt 0 ]]; then
    echo -e "${RED}存在 $FAIL 个严重问题，请先修复后再部署。${NC}"
    exit 1
elif [[ "$WARN" -gt 0 ]]; then
    echo -e "${YELLOW}存在 $WARN 个警告，建议处理后继续（非阻塞）。${NC}"
    exit 0
else
    echo -e "${GREEN}所有检查通过，可以运行 bash scripts/start.sh 启动服务。${NC}"
    exit 0
fi
