# Tech Context: FunASR 企业内网部署

## 技术栈

### 基础设施
| 组件 | 版本/规格 |
|------|-----------|
| Docker Engine | 生产版本（需支持 GPU） |
| Docker Compose | Plugin v2 |
| NVIDIA Container Toolkit | 最新 |
| 操作系统 | Ubuntu / Linux |
| GPU | NVIDIA GPU（≥8GB 显存推荐，≥12GB 生产） |
| 内存 | ≥16GB 推荐 |
| 磁盘 | ≥50GB 推荐 |

### 镜像与依赖
| 组件 | 技术 |
|------|------|
| 基础镜像 | `pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime` |
| ASR 框架 | FunASR (pip install funasr) |
| HTTP 服务 | `funasr-server` CLI（官方内置） |
| WebSocket 服务 | `funasr_wss_server.py`（官方 SDK 内提取） |
| 反向代理 | Nginx 1.27-alpine |
| Python 版本 | 3.x（基础镜像内置） |
| 深度学习框架 | PyTorch 2.4.0 + CUDA 12.1 |
| 其他依赖 | vllm, fastapi, uvicorn, python-multipart, ffmpeg, websockets |

### 镜像源配置
- apt: 阿里云镜像 (`mirrors.aliyun.com`)
- pip: 清华镜像 (`pypi.tuna.tsinghua.edu.cn`)
- 模型: ModelScope Hub（默认）

## 模型配置

### funasr-api 模型
| 模型 | ModelScope ID |
|------|---------------|
| SenseVoice | `iic/SenseVoiceSmall`（默认，CLI 的 `--model` 参数） |

### funasr-ws 模型
| 模型 | ModelScope ID | 用途 |
|------|---------------|------|
| 离线 ASR | `iic/SenseVoiceSmall` | 最终离线纠错 |
| 流式 ASR | `iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online` | 实时流式识别 |
| VAD | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | 语音活动检测 |
| 标点 | `iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch` | 标点恢复 |

## 开发环境设置

### 前置条件
```bash
# Docker + NVIDIA Container Toolkit
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 安装 NVIDIA Container Toolkit 后重启

# 克隆项目
git clone <repo-url>
cd funasr-deploy
cp .env.example .env
```

### 常用命令
```bash
# 环境检查
bash scripts/preflight.sh

# 预下载模型
bash scripts/download_models.sh

# 启动服务
bash scripts/start.sh

# 扩展 API 实例
bash scripts/start.sh --scale-api 3

# 停止服务
bash scripts/stop.sh

# 查看日志
bash scripts/logs.sh
```

## 技术约束

1. **GPU 独占**：每个 API 实例约占用 3~4GB 显存，多实例需确保显存充足
2. **模型下载**：首次启动会自动从 ModelScope 下载多个模型（总计数 GB），可能超时，建议预下载
3. **内网限制**：无外网环境需手动模型离线安装（`docs/offline_setup.md` 预留）
4. **端口冲突**：需确保 80 和 10095 端口未被占用
5. **WebSocket 状态**：`funasr-ws` 使用 ip_hash 保证粘性会话，扩展时需注意
6. **API 鉴权**：当前通过 Nginx 注入固定的 `Authorization: Bearer funasr-internal`，仅适用于内网

## 工具使用模式

### 脚本体系
```
scripts/
├── preflight.sh       # 部署前检查（OS/Docker/GPU/内存/磁盘/端口/配置/网络）
├── download_models.sh # 模型预下载
├── start.sh           # 启动 + 等待健康检查 + 打印状态
├── stop.sh            # 优雅停止（等待请求完成）+ 可选清理
├── logs.sh            # 日志查看（支持服务过滤、时间过滤、统计）
└── logrotate.sh       # 日志轮转（由容器定期调用）
```

### 配置文件约定
- `.env`：主配置（不提交 Git）
- `.env.example`：配置模板（提交 Git）
- `config/hotwords.txt`：WebSocket Runtime 热词
- `nginx/conf.d/funasr.conf`：路由 + upstream 配置