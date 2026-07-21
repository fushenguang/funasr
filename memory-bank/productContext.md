# Product Context: FunASR 企业内网部署

## 为什么有这个项目
企业内网环境下需要高精度、低延迟的语音识别服务，用于：
- 会议录音转写（文件模式）
- 实时语音转文字（流式模式）
- 兼容 OpenAI Audio API，方便现有生态集成

## 解决的问题
1. **模型部署复杂**：通过 Docker 镜像封装 GPU 环境、FunASR 依赖、模型文件，一键部署
2. **多实例扩展**：GPU 推理是瓶颈，通过 Nginx 负载均衡支持水平扩展
3. **内网环境适配**：预下载模型、换用国内镜像源，避免外网依赖
4. **生产可观测性**：结构化 JSON 日志（request_id 贯穿）、健康检查、日志轮转

## 用户体验

### 接入方式
- **HTTP API 用户**：直接使用 OpenAI Python/JS SDK，只需改 `base_url`
- **WebSocket 用户**：连接 `ws://<server-ip>/ws`，流式接收识别结果
- **运维人员**：通过 `scripts/` 下的脚本管理服务启停、日志查看

### 典型使用流程
1. 运维执行 `preflight.sh` 检查环境
2. 执行 `download_models.sh` 预下载模型
3. 执行 `start.sh` 启动全部服务
4. 用户通过 HTTP API 或 WebSocket 接入使用
5. 高峰期执行 `start.sh --scale-api 3` 扩容

## 设计理念
- **尽量不改官方代码**：镜像直接使用官方 `funasr-server` CLI 和 `funasr_wss_server.py`
- **Nginx 作为统一网关**：鉴权、路由、限流、负载均衡都在网关层处理
- **零配置接入**：Nginx 自动注入 `Authorization` header，内网用户无需关心 API key