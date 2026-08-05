# Progress: FunASR 企业内网部署

## 已完成

### 核心基础设施
- [x] Docker Compose 多服务编排（nginx + funasr-api + funasr-ws + log-rotate）
- [x] NVIDIA GPU 支持（`deploy.resources.reservations.devices`）
- [x] Docker 镜像构建（`services/funasr/Dockerfile`）
  - PyTorch 2.4.0 + CUDA 12.1 基础镜像
  - 阿里云 apt 镜像 + 清华 pip 镜像
  - funasr-server CLI + funasr_wss_server.py 集成
- [x] 模型缓存卷映射（`./models` → ModelScope Hub 缓存）

### Nginx 网关
- [x] HTTP API 路由（`/v1/*` → funasr-api，least_conn 负载均衡）
- [x] WebSocket 路由（`/ws` → funasr-ws，ip_hash 粘性会话）
- [x] 健康检查代理（`/health`）
- [x] Swagger 文档代理（`/docs`）
- [x] 根路径状态页（返回 JSON 服务信息）
- [x] 鉴权注入（自动添加 `Authorization: Bearer funasr-internal`）
- [x] JSON 格式访问日志
- [x] 预留 TLS 配置（frp 外网接入）

### 运维脚本
- [x] `preflight.sh` — 环境预检（OS/Docker/GPU/内存/磁盘/端口/配置/网络）
- [x] `download_models.sh` — 模型预下载
- [x] `start.sh` — 服务启动 + 健康检查等待 + 状态打印
- [x] `stop.sh` — 优雅停止（等待请求完成）+ 可选清理
- [x] `logs.sh` — 日志查看工具（服务过滤、时间过滤、统计）
- [x] `logrotate.sh` — 日志轮转

### 健康检查
- [x] Nginx: `wget http://localhost/`
- [x] funasr-api: `curl http://localhost:8000/health`
- [x] funasr-ws: TCP socket 连接检测

### 日志管理
- [x] Docker json-file 日志驱动（50MB 轮转，10 个文件）
- [x] 独立 log-rotate 容器（>100MB 轮转，>30 天删除）
- [x] 结构化日志目录（nginx/api/runtime/system）
- [x] API 日志字段：request_id, filename, file_size_mb, model, audio_duration_s, inference_time_s, rtf, text_length, status_code

## 待完成

### 功能增强
- [ ] `docs/offline_setup.md` — 离线模型安装文档
- [ ] 外网 frp + TLS 最终方案验证
- [ ] WebSocket 鉴权机制（当前无鉴权）
- [ ] 请求限流（rate limiting）

### 代码清理
- [ ] 确认 `services/openai-api/` 的用途（增强版 API vs 官方 CLI）
- [ ] 确认 `services/runtime-ws/` 是否为遗留代码
- [ ] 统一服务实现路径，消除冗余

### 测试
- [ ] HTTP API 转写功能测试
- [ ] WebSocket 实时流功能测试
- [ ] 多实例负载均衡测试
- [ ] 故障恢复测试（单实例宕机）

## 已知问题

1. ~~**`services/` 目录存在冗余**~~ → 2026-08-04 定性为**备选方案（保留但未启用）**，已在 README 与 wiki 中显式标注，不再作为待办
2. **WebSocket 无鉴权**：`funasr-ws` 直接对外暴露，没有认证机制
3. **env 变量 `$$` 转义**：docker-compose.yml 中 `funasr-ws` 的 command 使用 `$${}` 语法（Docker Compose 变量转义），需要注意 `.env` 变量是否被正确解析

## 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 初始 | 使用官方 `funasr-server` CLI 而非自建 API 服务 | 减少维护成本，跟随官方更新 |
| 初始 | Nginx 注入固定 API key | 内网环境，简化接入 |
| 初始 | WebSocket 不使用 Nginx 鉴权 | WebSocket 鉴权需在应用层处理 |
| 2026-07-21 | 初始化 Cline Memory Bank | 确保跨会话上下文连续性 |
| 2026-08-04 | `services/openai-api/` 与 `services/runtime-ws/` 保留为**备选方案**，不删除、不启用 | 官方 CLI 方案维护成本更低；两个目录在需要结构化日志或自定义 WebSocket 行为时仍有价值 |
| 2026-08-04 | 修正 README 与 wiki 中的结构化 API 日志描述 | 原文档描述的 `request_id`/`rtf` 等字段来自未启用的 `services/openai-api/server.py`，与实际运行的官方 `funasr-server` CLI 不符，会误导按文档排查日志的运维人员 |
| 2026-08-04 | 配置 Claude Code 工程环境（`CLAUDE.md` + `.claude/`），并加入 `.gitignore` | 本地 AI 协作配置，不随仓库分发 |