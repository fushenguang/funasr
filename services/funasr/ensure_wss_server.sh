#!/bin/sh
# 确保 /opt/funasr_wss_server.py 存在并修正 certfile 默认值

WSS="/opt/funasr_wss_server.py"

if [ ! -f "$WSS" ]; then
    PKG_PATH=$(python3 -c "import funasr,os; print(os.path.dirname(funasr.__file__))" 2>/dev/null)
    SRC="$PKG_PATH/runtime/python/websocket/funasr_wss_server.py"
    if [ -f "$SRC" ]; then
        cp "$SRC" "$WSS"
        echo "[ws] 从包内复制: $SRC"
    else
        echo "[ws] 错误: 找不到 funasr_wss_server.py"
        exit 1
    fi
else
    echo "[ws] 使用已有 $WSS"
fi

# ── 关键 patch：把 certfile 默认值从路径字符串改成空字符串 ──────────
# 官方脚本默认值是 "../../ssl_key/server.crt"，len > 0 会触发 SSL 加载
# 改成 "" 后 len == 0，走 else 分支，不启用 SSL
sed -i 's|default="../../ssl_key/server.crt"|default=""|g' "$WSS"
sed -i 's|default="../../ssl_key/server.key"|default=""|g' "$WSS"
echo "[ws] certfile/keyfile 默认值已 patch 为空字符串（禁用 SSL）"
