# System Patterns: FunASR 企业内网部署

## 架构模式

### API Gateway Pattern
Nginx 作为统一入口网关：
- 路由分发（`/v1/*` → API, `/ws` → WebSocket）
- 负载均衡（`least_conn` for API, `ip_hash` for WebSocket）
- 鉴权注入（Nginx 统一添加 `Authorization` header）
- 日志记录（JSON 格式访问日志）

### 微服务编排
Docker Compose 管理 4 个服务：
```
docker-compose.yml
├── nginx          # API 网关
├── funasr-api     # HTTP 文件转写（可水平扩展）
├── funasr-ws      # WebSocket 实时流
└── log-rotate     # 日志轮转守护进程
```

### 模型加载策略
- **基础镜像**：`pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime`
- **两个服务共用同一镜像**：`funasr-api` 和 `funasr-ws` 都使用 `funasr:latest`
- **模型缓存**：`./models` 映射到容器的 ModelScope Hub 缓存目录，避免重复下载
- **模型分离**：api 只用 SenseVoice（离线），ws 加载 4 个模型（ASR + 流式 ASR + VAD + 标点）

## 关键设计决策

### 负载均衡策略
| 服务 | 策略 | 原因 |
|------|------|------|
| funasr-api | `least_conn` | GPU 推理耗时不均，按连接数分配比轮询更均衡 |
| funasr-ws | `ip_hash` | WebSocket 是长连接，同一客户端 IP 必须打到同一实例 |

### 日志架构
```
logs/
├── nginx/access.log     # Nginx JSON 访问日志
├── api/funasr-api.log   # API 结构化日志（request_id, rtf, audio_duration_s 等）
├── runtime/             # WebSocket Runtime 日志
└── system/              # 系统级日志（预留）
```
- 日志轮转由独立 `log-rotate` 容器处理（>100MB 轮转，>30 天删除）
- Docker json-file 日志驱动 + 本地文件双重保障

### 内网安全模型
- Nginx 统一注入 `Authorization: Bearer funasr-internal`，后端简单校验
- API 服务不对外暴露端口（仅 `expose`，不 `ports`）
- WebSocket 需对外暴露（客户端直接连接），但目前无鉴权

### 扩容模型
```bash
docker compose up -d --scale funasr-api=3
```
- Docker DNS 自动解析 `funasr-api` 为所有实例 IP
- Nginx upstream 无需手动修改
- 每个实例独立占用 3~4GB 显存

## 组件关系
```
Client
  │
  ▼
Nginx (80)
  │
  ├─ /v1/* ──────────► funasr-api:8000 (×N) ──► SenseVoice 模型
  ├─ /health ────────► funasr-api:8000
  ├─ /docs ──────────► funasr-api:8000
  └─ /ws ────────────► funasr-ws:10095 ────────► 4 个模型 (ASR + Online + VAD + Punc)
```

## 关键实现路径

### HTTP 转写流程
1. Nginx 接收 multipart/form-data 请求
2. 路由到 `funasr-api`（least_conn）
3. `funasr-server` CLI 处理：音频解码 → VAD → ASR → 返回文本
4. 返回 JSON（支持 `verbose_json` 格式）

### WebSocket 流式流程
1. 客户端连接 `ws://host/ws`
2. Nginx 升级为 WebSocket，ip_hash 路由到 `funasr-ws`
3. 客户端发送二进制音频块 → 流式 ASR 识别 → 实时返回文本片段
4. 客户端发送 `{"is_speaking": false}` → 触发离线纠错 + 标点恢复 → 返回最终文本