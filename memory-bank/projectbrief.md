# Project Brief: FunASR 企业内网部署

## 项目定位
基于 [FunASR](https://github.com/modelscope/FunASR) 的生产级语音识别服务，面向企业内网环境部署。

## 核心目标
- 提供兼容 OpenAI Audio API 的 HTTP 文件转写服务
- 提供 WebSocket 实时流式语音识别服务
- 支持水平扩展（多 API 实例负载均衡）
- 提供生产级日志、健康检查、优雅启停

## 架构概览
```
Client → Nginx (port 80)
           ├── /v1/* → funasr-api (HTTP, load balanced)
           ├── /ws   → funasr-ws  (WebSocket, sticky session)
           └── /health, /docs → funasr-api
```

## 关键约束
- **内网部署**：不直接暴露公网，未来通过 frp 接入外网
- **GPU 依赖**：需要 NVIDIA GPU (CUDA)，每实例约 3~4GB 显存
- **模型预下载**：首次启动前需预先下载模型，避免启动超时
- **ModelScope 源**：模型从 ModelScope Hub 拉取，国内网络友好

## 服务端口
| 服务 | 端口 | 说明 |
|------|------|------|
| Nginx | 80 | 统一入口 |
| funasr-api | 8000 | 内部端口，文件转写 |
| funasr-ws | 10095 | 内部端口，实时流式 |