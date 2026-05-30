# FunASR 企业内网部署

基于 [FunASR](https://github.com/modelscope/FunASR) 的生产级语音识别服务，支持文件转写（HTTP API）和实时流式识别（WebSocket）。

## 项目结构

```
funasr-deploy/
├── docker-compose.yml          # 主编排文件
├── .env.example                # 环境变量模板（复制为 .env 使用）
├── .gitignore
│
├── services/
│   └── openai-api/
│       ├── Dockerfile          # API 服务镜像
│       ├── server.py           # 增强版 API 服务（带结构化日志）
│       ├── logging_config.py   # JSON 日志配置
│       └── requirements.txt
│
├── nginx/
│   ├── nginx.conf              # Nginx 主配置（JSON 访问日志）
│   └── conf.d/
│       └── funasr.conf         # 路由规则 + upstream 负载均衡
│
├── scripts/
│   ├── preflight.sh            # 部署前环境预检
│   ├── download_models.sh      # 模型预下载（ModelScope）
│   ├── start.sh                # 启动服务
│   ├── stop.sh                 # 停止服务
│   ├── logs.sh                 # 日志查看工具
│   └── logrotate.sh            # 日志轮转（由容器定期调用）
│
├── config/
│   └── hotwords.txt            # WebSocket Runtime 热词（可选）
│
├── models/                     # 模型文件（不进 Git，由脚本管理）
│   └── .gitkeep
│
└── logs/                       # 日志目录（不进 Git）
    ├── nginx/                  # Nginx JSON 访问日志
    ├── api/                    # API 服务结构化日志
    ├── runtime/                # WebSocket Runtime 日志
    └── system/                 # 系统级日志（预留）
```

## 快速开始

### 1. 克隆并配置

```bash
git clone <your-repo>/funasr-deploy.git
cd funasr-deploy
cp .env.example .env
# 按需编辑 .env
```

### 2. 环境预检

```bash
bash scripts/preflight.sh
```

### 3. 预下载模型（推荐，避免首次启动时下载超时）

```bash
bash scripts/download_models.sh
```

### 4. 启动服务

```bash
bash scripts/start.sh
```

### 5. 验证

```bash
# 健康检查
curl http://localhost/health

# 转写测试
curl http://localhost/v1/audio/transcriptions \
  -F file=@your_audio.wav \
  -F model=sensevoice \
  -F response_format=verbose_json
```

## 扩展 API 实例

当单实例 GPU 成为瓶颈时（每实例约占 3~4GB 显存）：

```bash
# 启动 2 个 API 实例（Nginx 自动负载均衡）
bash scripts/start.sh --scale-api 2

# 或直接用 compose
docker compose up -d --scale funasr-api=2
```

## 日志管理

```bash
# 实时查看所有日志
bash scripts/logs.sh

# 只看 API 错误
bash scripts/logs.sh api --errors

# 查看请求统计（需要 jq）
bash scripts/logs.sh --stats

# 查看最近 1 小时的 Nginx 日志
bash scripts/logs.sh nginx --since 1h
```

日志文件位置：
- Nginx 访问日志（JSON）：`logs/nginx/access.log`
- API 服务日志（JSON）：`logs/api/funasr-api.log`
- WebSocket Runtime 日志：`logs/runtime/`

每条 API 日志记录：`request_id`, `filename`, `file_size_mb`, `model`, `audio_duration_s`, `inference_time_s`, `rtf`, `text_length`, `status_code`

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Nginx (统一入口) | 80 | 所有流量走这里 |
| funasr-api | 8000 | 内部端口，不对外 |
| funasr-ws | 10095 | 内部端口，不对外 |

## 接入方式

### HTTP API（文件转写）

兼容 OpenAI Audio API，可直接使用 OpenAI SDK：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<server-ip>/v1",
    api_key="not-needed",
)
result = client.audio.transcriptions.create(
    model="sensevoice",
    file=open("audio.wav", "rb"),
    response_format="verbose_json",
)
print(result.text)
```

### WebSocket（实时流式）

```
ws://<server-ip>/ws
```

参考 [FunASR WebSocket 客户端示例](https://github.com/modelscope/FunASR/blob/main/runtime/docs/SDK_advanced_guide_online_zh.md)

## 未来接外网（frp 方案）

1. frp 在服务器上监听，把外网流量转到本机 80 端口
2. Nginx 的 `nginx/conf.d/funasr.conf` 中取消 TLS server 的注释
3. 把证书放到 `nginx/certs/` 目录
4. 无需改动 docker-compose.yml 和服务代码

## 维护

```bash
# 停止服务（优雅，等待正在处理的请求完成）
bash scripts/stop.sh

# 停止并清理容器
bash scripts/stop.sh --clean

# 更新镜像后重启
docker compose pull
bash scripts/start.sh --build
```
