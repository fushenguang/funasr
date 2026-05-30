#!/usr/bin/env sh
# ============================================================
# logrotate.sh - 日志轮转（每小时由 log-rotate 容器调用）
# 保留策略: 30 天，超过 100MB 的文件立即轮转
# ============================================================

LOG_DIR="/logs"
RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"
MAX_SIZE_MB=100

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [logrotate] $*"; }

log "开始日志轮转检查 (保留: ${RETENTION_DAYS}天, 单文件上限: ${MAX_SIZE_MB}MB)"

# 删除超过保留天数的日志
find "$LOG_DIR" -type f -name "*.log.*" -mtime "+$RETENTION_DAYS" -delete 2>/dev/null && \
    log "清理 ${RETENTION_DAYS} 天前的日志完成"

# 超大文件截断（避免单文件过大）
find "$LOG_DIR" -type f -name "*.log" | while read -r logfile; do
    SIZE_MB=$(du -m "$logfile" 2>/dev/null | cut -f1)
    if [ "${SIZE_MB:-0}" -gt "$MAX_SIZE_MB" ]; then
        BACKUP="${logfile}.$(date '+%Y%m%d-%H%M%S')"
        mv "$logfile" "$BACKUP"
        touch "$logfile"
        log "轮转大文件: $logfile -> $BACKUP (${SIZE_MB}MB)"
    fi
done

# 统计当前日志使用量
TOTAL=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
log "日志总占用: $TOTAL"
