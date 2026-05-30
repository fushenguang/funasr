FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

LABEL service="funasr-api"

RUN sed -i 's|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list \
 && sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
 && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py logging_config.py ./

RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8000"]
