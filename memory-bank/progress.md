# Progress: FunASR 企业内网部署

## 已完成

### 核心基础设施
- [x] Docker Compose 多服务编排（nginx + funasr-api + funasr-ws + cosyvoice-tts + log-rotate）
- [x] CosyVoice2-0.5B TTS 后端接入（`services/cosyvoice/`），**2026-08-05 已在部署服务器（RTX 3060 12GB）实测跑通**
  - 自建 FastAPI，OpenAI 兼容 `POST /v1/audio/speech`，流式 PCM16LE @ 24000Hz
  - 服务端预注册命名音色（zero-shot 音色克隆，`<NAME>_PROMPT_WAV`/`<NAME>_PROMPT_TEXT` 环境变量成对发现），实测 `xiaoxi` 音色（官方示例 `zero_shot_prompt.wav` + 在容器内核实的转录文本）注册成功
  - 同步推理生成器通过 `asyncio.to_thread` + `asyncio.Queue` 桥接，避免卡死 event loop
  - `asyncio.Lock` 串行化 GPU 访问，覆盖整个流式产出周期，客户端断连正确释放（实测验证：`curl -m 1` 中断后锁立即释放，紧接着的新请求无需等待）
  - 实测首个音频分片延迟约 1.55s，端到端 RTF 约 0.35；详见 wiki `guide/tts-cosyvoice.mdx`「构建与部署实测记录」
  - **2026-08-05 补测**：首包延迟在 8~227 字文本区间稳定在 1.49~1.60s，不随文本变长而线性增长（CosyVoice 官方 `text_normalize()` 内部已用 `split_paragraph()` 做等价切句），**结论是不需要在服务端再实现一层切句优化**
  - **2026-08-05 已根治**文本前端问题：`wetext` 从 `0.0.4` 升级到 `0.1.6`（FST 资源打包进 wheel，不再依赖 ModelScope 运行时下载），容器内实测 `Normalizer(remove_erhua=False).normalize('2026年8月5日下午3点，收费128元，涨幅12.5%。')` → `'二零二六年八月五日下午三点，收费一百二十八元，涨幅百分之十二点五。'`，日志不再出现 `no frontend is avaliable`
  - **2026-08-05 下载源国内化**：`services/cosyvoice/Dockerfile` 的 pip/conda/git 源全部改为国内镜像（阿里云 pytorch-wheels、清华 conda-forge、可选 GitHub 镜像 build arg），真实重建验证 pip 安装阶段耗时从 627.4s 降到 412.0s（约快 34%），总构建时间从约 11m51s 降到 10m27s（约快 12%）
- [x] NVIDIA GPU 支持（`deploy.resources.reservations.devices`）
- [x] Docker 镜像构建（`services/funasr/Dockerfile`）
  - PyTorch 2.4.0 + CUDA 12.1 基础镜像
  - 阿里云 apt 镜像 + 清华 pip 镜像
  - funasr-server CLI + funasr_wss_server.py 集成
- [x] 模型缓存卷映射（`./models` → ModelScope Hub 缓存）

### Nginx 网关
- [x] HTTP API 路由（`/v1/*` → funasr-api，least_conn 负载均衡）
- [x] WebSocket 路由（`/ws` → funasr-ws，ip_hash 粘性会话）
- [x] TTS 路由（`/v1/audio/speech`、`/v1/audio/voices` → cosyvoice-tts，`proxy_buffering off` 保证真流式）
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
- [x] cosyvoice-tts: `curl http://localhost:8100/health`（`start_period: 180s`，与模型加载 + 音色注册耗时匹配）

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
- [ ] TTS `inference_instruct2`（指令控制情感/语速等）扩展点已在 `server.py` 留注释，本轮未实现
- [x] ~~TTS 服务器实测（构建、显存共存、首包延迟）~~ → **2026-08-05 已在部署服务器完整实测并跑通**，见下方「已知问题」核实结论与 wiki `guide/tts-cosyvoice.mdx` 的「构建与部署实测记录」
- [x] ~~TTS 文本前端（`wetext`）运行时需要访问 ModelScope 下载资源，实测遇 403 无法完整初始化，`no frontend is avaliable`~~ → **2026-08-05 已根治**：升级 `wetext` 到 `0.1.6`（资源打包进 wheel，不再依赖 ModelScope），容器内实测数字/日期/百分号归一化正确，见上方「已完成」与 wiki `guide/tts-cosyvoice.mdx`
- [x] ~~所有下载源改为国内镜像（用户明确要求，主要市场在国内）~~ → **2026-08-05 已完成**：`services/cosyvoice/Dockerfile` 的 `requirements.txt` extra-index-url（阿里云 pytorch-wheels，删除不可达的 aiinfra 源）、conda pynini（清华 conda-forge）、git clone（新增可选 `COSYVOICE_GIT_MIRROR` build arg）均已改造并真实重建验证；基础镜像 `pytorch/pytorch:*` 保持不变（阿里云 ACR 对非官方命名空间要求鉴权，服务器 Docker daemon 已有 `registry-mirrors` 兜底），原因见 Dockerfile 头部注释
- [ ] onnxruntime-gpu 的 CUDA 执行器加载失败，静默回退 CPU（`libcublasLt.so.11` 找不到，因为 PyPI 上的 `onnxruntime-gpu==1.18.0` 是面向 CUDA 11 的构建，镜像里只有 CUDA 12 的库）——**不影响当前生产请求路径**（该 ONNX session 只在启动时注册命名音色用一次，`/v1/audio/speech` 走预注册音色分支完全不触发），但如果未来要支持 ad-hoc zero-shot（非预注册音色）克隆，需要单独解决（换一个显式支持 cu12 的 onnxruntime-gpu 版本或来源）

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
4. **TTS 待服务器核实项**（本机 macOS 无 GPU，无法本地验证，均已在代码中用 `# TODO(须服务器核实):` 标注）—— **2026-08-05 已在部署服务器（RTX 3060 12GB）全部核实并跑通**：
   - ~~`pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime` 是否自带 conda~~ → **是**，`conda install pynini` 直接可用，实测约 79s
   - ~~CosyVoice `requirements.txt` 在该镜像 Python 版本（≈3.11）下能否全部装上~~ → **基本能，发现并修复 5 处真实缺陷**：`openai-whisper` 缺 `pkg_resources`（需 `PIP_CONSTRAINT=setuptools<81`）、`tensorrt-cu12*` 访问受限且推理路径用不到（跳过安装）、`pyworld` 编译需要 `g++`（装 `build-essential`）、`torchvision` 未钉版本导致与 `torch==2.3.1` 不兼容（显式钉 `0.18.1`）、`deepspeed` 在无 `nvcc` 的 runtime 镜像里启动即崩溃且推理路径不引用（跳过安装）。详见 `services/cosyvoice/Dockerfile` 注释与 wiki
   - ~~ModelScope 实际落盘目录名~~ → **2026-08-05 已在部署服务器核实**：是 `iic_CosyVoice2-0.5B`（单个下划线）。
     此前规格里断言的"双下划线"是错的——`tr '/' '__'` 是字符映射不是字符串替换，`/` 只映射成一个 `_`；
     服务器上既有的 `iic_SenseVoiceSmall` 目录即为佐证
   - ~~3060 12GB 上 `funasr-api` + `funasr-ws` + CosyVoice2 fp16 三者能否共存~~ → **能**，实测三者共存占用 7218~7320 MiB / 12288 MiB（约 60%），余量约 5GB
   - ~~流式首包延迟与块粒度的实测值~~ → **真实首个音频分片延迟约 1.55s**（约 40 字长句，Python 直连测得；注意 `curl` 的 `time_starttransfer` 只反映 HTTP 响应头提交时刻，接近 0，不能代表真实首包延迟，是本轮排查中发现的一个测量陷阱）；端到端 RTF 约 0.35（约 3 倍实时速度），模型内部逐分片 RTF 0.30~0.45
   - **新发现，非预埋 TODO**：`server.py` 的 `add_zero_shot_spk` 调用传参类型错误（预加载 tensor 而非文件路径），导致音色注册在真实环境下 100% 失败；`docker-compose.yml` 的 nginx 健康检查用 `http://localhost/` 在容器内解析到 IPv6 被拒绝连接，导致 nginx 持续报 unhealthy（服务本身正常）。两者均已修复并验证，详见 wiki「构建与部署实测记录」表格

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
| 2026-08-04 | 新增 CosyVoice2-0.5B 作为第 4 个后端服务（`cosyvoice-tts`），自建 FastAPI 而非套用 `services/openai-api/` 骨架 import | TTS 与 ASR 的推理模型/生命周期完全不同，独立服务便于跟随 CosyVoice 上游单独升级；只借鉴 `services/openai-api/server.py` 的骨架风格（lifespan/请求追踪/parse_args），不引入依赖耦合 |
| 2026-08-04 | TTS 命名音色通过 `<NAME>_PROMPT_WAV`/`<NAME>_PROMPT_TEXT` 环境变量成对扫描自动注册，而非硬编码音色列表 | 新增音色只需要在 `.env`/compose environment 加一对变量 + 放参考 wav，不用改 `server.py` 代码 |
| 2026-08-04 | `download_models.sh` 新增 `--tts-only`，但 CosyVoice2 模型**默认不随** `--api-only`/`--ws-only` 之外的无参数默认运行一起下载 | TTS 模型体积达数 GB，不应在现有用户执行不带参数的默认下载命令时静默新增一次大体积下载；需要显式执行一次 `--tts-only` |
| 2026-08-05 | TTS 服务在部署服务器（RTX 3060 12GB）首次实测跑通，构建阶段跳过 `tensorrt-cu12*` 与 `deepspeed` 两组依赖，不安装进镜像 | 均已对照 CosyVoice 源码确认推理路径（`load_trt=False`、非分布式训练）完全不引用；`tensorrt-cu12-libs` 依赖的 `pypi.nvidia.com`、`deepspeed` 依赖的 `nvcc`（runtime 镜像不含开发工具链）在本次部署环境下都不可用/不存在，装不上或装上就崩溃，跳过是明确更优的选择而非临时绕过 |
| 2026-08-05 | Nginx 健康检查目标从 `http://localhost/` 改为 `http://127.0.0.1/` | 实测复现：`nginx/conf.d/funasr.conf` 只 `listen 80;`（无 IPv6），但容器内 `wget` 解析 `localhost` 优先拿到 `::1`，连接被拒绝，导致健康检查持续失败而服务本身正常；这是配置解析歧义，非本次部署服务器特有，换任何环境都会复现 |
| 2026-08-05 | TTS 文本前端（`wetext`/WeTextProcessing）在无 ModelScope 访问令牌的环境下判定为**已知限制，暂不解决** | 运行时资源下载遇 403，`no frontend is avaliable`，文本归一化完全不可用；根治需要配置访问令牌或手工预置资源文件，超出本轮部署验证范围，留待后续按需处理 |
| 2026-08-05 | 上一条决策被推翻：`wetext` 从 `0.0.4` 升级到 `0.1.6` 彻底解决文本前端问题，不需要 ModelScope 令牌 | 排查确认根因不是"需要令牌"这么简单，而是 `pengzhendong/wetext` 作为 ModelScope **个人命名空间**仓库要求登录态下载（对照 `iic/*` 官方命名空间模型同一接口正常，排除网络/限流），且这条限制在其官方最新版本里已经被解决——`wetext` 从 0.0.7 起把 FST 资源直接打进 wheel，不再依赖 ModelScope；比申请令牌更彻底（运行时零联网），且不违反"不改 CosyVoice 上游代码"的原则（升级的是 pip 依赖版本，不是改代码） |
| 2026-08-05 | `services/cosyvoice/Dockerfile` 的 `requirements.txt` 两条 `--extra-index-url` 分别改写：`download.pytorch.org` 换阿里云 pytorch-wheels 镜像；`aiinfra.pkgs.visualstudio.com` 直接删除不找替代 | 前者已实测阿里云镜像有对应 cp311+cu121 wheel；后者实测返回 `401`（需要微软内部凭据，任何镜像站都代理不了这种鉴权），且确认现有 `onnxruntime-gpu` 本来就不是从这条线装的，删除不改变安装结果，只是去掉一次必然失败的探测 |
| 2026-08-05 | conda 装 pynini 改用清华 conda-forge 镜像 + `--override-channels`，不再退回 `-c conda-forge`（国外）或触碰默认 `defaults` 频道 | 已实测清华镜像 repodata 里存在所需的 `pynini==2.1.5` py311 构建，与 conda-forge 官方源等价；`--override-channels` 避免 conda 在解析依赖时仍尝试连国外的默认频道 |
| 2026-08-05 | git clone CosyVoice 新增可选 `COSYVOICE_GIT_MIRROR` build arg，但**默认值仍是直连 GitHub**，不强制走镜像 | git clone 相比 pip/conda 的大体积二进制传输对国内网络通常更友好，多数环境不需要镜像；镜像可用性变化快，写死在默认值里反而更脆弱。已实测推荐值 `https://ghfast.top/https://github.com/` 可用（含 `third_party/Matcha-TTS` 子模块），作为环境不稳定时的可选覆盖项 |
| 2026-08-05 | 基础镜像 `pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime` **不改为国内镜像** | 已实测阿里云容器镜像服务（ACR）对 `pytorch/pytorch` 这类非官方命名空间镜像要求鉴权（`GET /v2/pytorch/pytorch/tags/list` 返回 `401`），没有可公开替换的国内 tag；部署服务器 Docker daemon 已配置 `registry-mirrors`（daocloud/nju.edu.cn/dockerproxy 等），`docker pull` 已透明加速，Dockerfile 层面硬编码某个第三方镜像 registry 主机名反而更脆弱（这类服务可用性变化快） |
| 2026-08-05 | 不在服务端实现客户端可见的"切句优化"来降低 TTS 首包延迟 | 实测 8~227 字文本首包延迟稳定在 1.49~1.60s，不随文本变长线性增长，因为 CosyVoice 官方 `text_normalize()` 内部已用 `split_paragraph()`（`token_max_n=80`）做等价切句、逐段流式产出；自己再切一遍没有延迟收益，反而会因多次 HTTP 往返增加总耗时 |
| 2026-08-05 | 新增 wiki 文档 `guide/agent-tts-integration.mdx`，独立于 `guide/tts-cosyvoice.mdx` | 前者面向接入方（AI Agent/开发者），聚焦请求契约、错误码、流式实现边界、并发限制，信息密度优先；后者是部署方视角的产品说明+实测记录，两者读者不同，合并会让部署文档过长、也会让接入方要在业务说明里翻找技术契约 |