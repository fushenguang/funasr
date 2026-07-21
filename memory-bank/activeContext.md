# Active Context: FunASR 企业内网部署

## 当前工作焦点
Cline Memory Bank 初始化 — 为项目建立完整的文档体系，确保后续开发会话能快速恢复上下文。

## 最近变更
- 新建 `memory-bank/` 目录，包含完整的项目文档
- 创建 `projectbrief.md`、`productContext.md`、`systemPatterns.md`、`techContext.md`

## 项目当前状态
- **代码完整度**：核心服务已实现，Docker Compose 编排已完成
- **部署状态**：未部署（本地开发环境）
- **Git 状态**：a08424d3c2ea652fdeabb8cef6c8e26a87f8067f
- **关联远程**：`git@github.com:fushenguang/funasr.git`

## 未完成的工作
- `docs/offline_setup.md` — 离线模型安装文档（代码中已引用但文件不存在）
- 外网 frp 接入方案（TLS 配置已预留但未启用）
- `services/openai-api/` 目录下的增强版 API 服务（`server.py`、`logging_config.py`）似乎与 `services/funasr/` 存在功能重叠，需确认设计意图
- `services/runtime-ws/` 目录包含一个独立的 WebSocket 服务实现，但与 docker-compose.yml 中使用的 `services/funasr/` 路径不一致

## 重要发现 & 待澄清问题

### services/ 目录结构存在冗余
项目中存在两套服务实现：

1. **`services/funasr/`**（docker-compose.yml 实际使用）
   - Dockerfile 基于 `pytorch/pytorch:2.4.0-cuda12.1`
   - 安装 funasr 官方包，提取 `funasr_wss_server.py`
   - command 使用 `funasr-server` CLI

2. **`services/openai-api/`**（未被 docker-compose.yml 引用）
   - 独立的 Dockerfile + `server.py`（增强版 API，带结构化日志）
   - 似乎是备选/升级方案，但目前未启用

3. **`services/runtime-ws/`**（未被 docker-compose.yml 引用）
   - 包含完整的 `funasr_wss_server.py`（内联版本）
   - 与 `services/funasr/Dockerfile` 中从 pip 包提取的版本功能相同
   - 可能是开发时期的遗留目录

**需要确认**：`services/openai-api/` 和 `services/runtime-ws/` 是遗留代码还是计划中的未来方案？

## 当前决策
- Memory Bank 使用中英文混合编写，技术术语保留英文
- 文档聚焦于实际使用的配置（docker-compose.yml + services/funasr/）

## 下一步计划
1. 完成 `activeContext.md` 和 `progress.md` 编写
2. 等待用户确认 `services/openai-api/` 和 `services/runtime-ws/` 的处理方式
3. 后续可根据需要补充 `docs/offline_setup.md`