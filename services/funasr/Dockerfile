FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

# apt 换阿里云镜像
RUN sed -i 's|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list \
 && sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# pip 换清华镜像
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
 && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 安装 funasr-server 所需的全部依赖（官方 README 的完整列表）
RUN pip install --no-cache-dir \
    torch torchaudio \
    funasr \
    vllm \
    fastapi \
    uvicorn \
    python-multipart

# 从安装好的 funasr 包里提取官方 funasr_wss_server.py 到固定路径
# 这样 command 里直接 python /opt/funasr_wss_server.py 即可
RUN python -c "\
import funasr, os, shutil; \
src = os.path.join(os.path.dirname(funasr.__file__), \
    'runtime', 'python', 'websocket', 'funasr_wss_server.py'); \
print('found:', src, os.path.exists(src)); \
shutil.copy(src, '/opt/funasr_wss_server.py') if os.path.exists(src) else print('not found, will download at runtime') \
"

COPY ensure_wss_server.sh /opt/ensure_wss_server.sh
RUN chmod +x /opt/ensure_wss_server.sh

RUN mkdir -p /app/logs /root/.cache/modelscope/hub

EXPOSE 8000 10095
