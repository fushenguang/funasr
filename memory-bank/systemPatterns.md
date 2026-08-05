# System Patterns: FunASR 企业内网部署

## 架构模式

### API Gateway Pattern
Nginx 作为统一入口网关：
- 路由分发（`/v1/*` → API, `/ws` → WebSocket）
- 负载均衡（`least_conn` for API, `ip_hash` for WebSocket）
- 鉴权注入（Nginx 统一添加 `Authorization` header）
- 日志记录（JSON 格式访问日志）

### 微服务编排
Docker Compose 管理 5 个服务：
```
docker-compose.yml
├── nginx          # API 网关
├── funasr-api     # HTTP 文件转写（可水平扩展）
├── funasr-ws      # WebSocket 实时流
├── cosyvoice-tts  # TTS 语音合成（CosyVoice2-0.5B，OpenAI 兼容 /v1/audio/speech）
└── log-rotate     # 日志轮转守护进程
```

### 模型加载策略
- **基础镜像**：`pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime`
- **两个 ASR 服务共用同一镜像**：`funasr-api` 和 `funasr-ws` 都使用 `funasr:latest`
- **`cosyvoice-tts` 独立镜像**：`services/cosyvoice/Dockerfile`，同一基础镜像但通过 git clone
  CosyVoice 官方源码 + pip 安装依赖集成，不与 ASR 镜像共用（TTS/ASR 依赖树差异较大）
- **模型缓存**：`./models` 映射到容器的 ModelScope Hub 缓存目录，避免重复下载
  （`cosyvoice-tts` 与两个 ASR 服务共用同一份 `./models` 卷）
- **模型分离**：api 只用 SenseVoice（离线），ws 加载 4 个模型（ASR + 流式 ASR + VAD + 标点），
  tts 加载 CosyVoice2-0.5B（fp16）+ 服务端预注册命名音色（`./voices` 只读卷）

## 关键设计决策

### 负载均衡策略
| 服务 | 策略 | 原因 |
|------|------|------|
| funasr-api | `least_conn` | GPU 推理耗时不均，按连接数分配比轮询更均衡 |
| funasr-ws | `ip_hash` | WebSocket 是长连接，同一客户端 IP 必须打到同一实例 |
| cosyvoice-tts | 单实例，`upstream` 仅一个 `server` | 服务内部已用 `asyncio.Lock` 串行化 GPU 访问；未开放 `--scale`，多实例扩展属于后续架构变更 |

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
- TTS（`/v1/audio/speech`、`/v1/audio/voices`）与 `/v1/` 同策略：Nginx 注入固定 key，
  `cosyvoice-tts` 本身不校验 `Authorization`（keyless，仅 `expose` 不 `ports`）

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
  ├─ /v1/* ──────────────────► funasr-api:8000 (×N) ──► SenseVoice 模型
  ├─ /health ────────────────► funasr-api:8000
  ├─ /docs ──────────────────► funasr-api:8000
  ├─ /ws ────────────────────► funasr-ws:10095 ────────► 4 个模型 (ASR + Online + VAD + Punc)
  ├─ /v1/audio/speech ───────► cosyvoice-tts:8100 ─────► CosyVoice2-0.5B（流式 PCM16LE @ 24000Hz）
  └─ /v1/audio/voices ───────► cosyvoice-tts:8100 ─────► 已注册命名音色列表
```

`/v1/audio/speech`、`/v1/audio/voices` 是精确到路径的 nginx location，
按最长前缀匹配优先于更短的 `/v1/`，因此 `/v1/models` 等其余 `/v1/*` 路径
不受影响，继续由 `funasr-api` 独占（决策：不新增会与 `/v1/` 冲突的 location）。

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

### TTS 语音合成流程
1. 客户端 `POST /v1/audio/speech`，body 只带 `{input, voice, response_format:"pcm", stream}`
2. Nginx 转发到 `cosyvoice-tts:8100`，`proxy_buffering off` 保证下行不被 nginx 攒块
3. `server.py` 校验 `input` 非空 / `voice` 已注册 / `response_format=="pcm"`，否则 4xx
4. 获取 `asyncio.Lock`（串行化 GPU），把 `model.inference_zero_shot(...)` 这个**同步阻塞生成器**
   通过 `asyncio.to_thread` 丢进线程池迭代，产出的每个音频 chunk 经 `asyncio.Queue`
   （`loop.call_soon_threadsafe`）桥接回 async 世界，逐块 `yield` 给 `StreamingResponse`
   —— 这一步是关键设计约束：绝不能在 async 生成器里直接 `for` 迭代同步生成器，
   否则合成期间会卡死整个 event loop，导致 `/health` 无响应、docker healthcheck 超时、
   容器被判 unhealthy 反复重启
5. 客户端断连（`GeneratorExit`/`CancelledError`）时设置 `stop_event`、显式 `close()` 底层生成器、
   `async with` 退出时释放锁，避免线程/显存悬空
6. `stream=false` 时复用同一条推理路径，在服务端拼完整字节后一次性返回（仍受同一把锁保护）