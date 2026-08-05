# ============================================================
# CosyVoice2-0.5B TTS 服务镜像
#
# 基础镜像与 services/funasr/Dockerfile 保持一致（PyTorch 2.4.0 +
# CUDA 12.1），通过 git clone 官方仓库 + pip 安装依赖的方式集成
# CosyVoice，尽量不修改上游代码，只新增 server.py 作为 OpenAI 兼容
# 适配层（参照项目 "尽量不改官方代码" 的设计原则）。
#
# 已知坑（构建前务必确认）：
#   1. pynini 必须用 conda-forge 预编译包，且必须在 pip 安装
#      requirements.txt 之前装好，否则 pip 会尝试从源码编译 pynini
#      （依赖 OpenFst，极易失败/耗时很长）。
#   2. ttsfrd（CosyVoice 可选的高精度文本前端）只提供 cp310 专用
#      wheel，与本镜像的 Python 版本（随 PyTorch 基础镜像，约 3.11）
#      不匹配，这里主动跳过，退回用 wetext 兜底（详见下方 wetext 版本
#      覆盖说明，功能可用，精度略低于 ttsfrd）。
#   3. 模型落盘目录是 iic_CosyVoice2-0.5B（单个下划线）。
#      download_models.sh 的 tr '/' '__' 是字符映射不是字符串替换，
#      '/' 只映射成一个 '_'；已在部署服务器上以 iic_SenseVoiceSmall 实证。
#      不是 iic/CosyVoice2-0.5B 子目录，详见 server.py 启动时的校验逻辑。
#   4. wetext==0.0.4（requirements.txt 原始钉版）在 Normalizer.__init__
#      里无条件 snapshot_download("pengzhendong/wetext")，实测（2026-08-05）
#      在部署服务器与本地网络均对 pengzhendong/wetext 这个**个人命名空间**
#      仓库的 /revisions 与文件下载接口返回 403（网关消息是"操作过于频繁"，
#      但对照官方 iic/SenseVoiceSmall、iic/CosyVoice2-0.5B 两个**官方命名
#      空间**模型的同一接口均 200 成功，确认是 ModelScope 对个人命名空间
#      仓库的下载接口要求登录态，不是速率限制、也不是网络问题），运行时
#      报错 "Authentication token does not exist"，最终 frontend 落到
#      "no frontend is avaliable"，文本前端完全不可用。
#      根治方案：把 wetext 升级到 0.1.6（见下方 requirements 改写步骤）——
#      pip 官方元数据确认从 0.0.7 起 wetext wheel 体积从 ~10KB 跳到
#      ~1.5MB+（0.1.6 是 2.9MB），改为把 FST 资源文件直接打进 wheel
#      （package-data，通过 importlib.resources 加载），requires-dist
#      变成只有 contractions + kaldifst，不再依赖 modelscope，构建期装完
#      即可用，运行时零联网。已核对 0.1.6 的 Normalizer(remove_erhua=...)
#      构造签名与 .normalize(text) 返回值类型（nbest=1 时返回 str）与
#      0.0.4 完全兼容，CosyVoice frontend.py 的调用方式不用改。
# ============================================================
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime
# 基础镜像来自 Docker Hub，未改写为国内镜像：已实测阿里云容器镜像服务
# （registry.cn-hangzhou.aliyuncs.com）对 pytorch/pytorch 这类非官方
# （非 library/）命名空间镜像要求鉴权（GET /v2/pytorch/pytorch/tags/list
# 返回 401 UNAUTHORIZED），没有可公开直接替换的国内 tag；而部署服务器的
# Docker daemon 已在 /etc/docker/daemon.json 配置了 registry-mirrors
# （docker.m.daocloud.io / docker.nju.edu.cn / dockerproxy.com 等），
# `docker pull` 会透明走这些镜像加速，不需要也不应该在 Dockerfile 里
# 硬编码某个国内镜像 registry 主机名（这类第三方加速服务可用性变化快，
# 写死在 Dockerfile 里反而更脆弱；daemon 级配置是更稳妥的改法层级）。

# apt 换阿里云镜像（与 services/funasr/Dockerfile 一致）
RUN sed -i 's|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list \
 && sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list

# git: clone CosyVoice 源码 + Matcha-TTS 子模块
# curl: docker healthcheck 探活 /health
# sox/libsox-dev: CosyVoice 音频前端依赖
# ffmpeg: 音频编解码兜底
# build-essential: requirements.txt 里的 pyworld==0.3.4 是带 C++ 扩展的源码包
#   （没有预编译 wheel），装的时候要现场编译 cheaptrick.cpp 等文件，需要 g++。
#   部署服务器实测复现：没有这条会在 pip install 阶段报
#   "error: command 'g++' failed: No such file or directory"。
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl sox libsox-dev ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

# pip 换清华镜像
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
 && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 部署服务器实测：requirements.txt 里 torch==2.3.1 拉起的
# nvidia_cudnn_cu12（731.7MB）等大体积 wheel 在 download.pytorch.org 上
# 连续两次触发 pip 默认 15s 读超时（urllib3.exceptions.ReadTimeoutError,
# "Read timed out"）——这条链路吞吐量会有短暂波动，默认超时对大文件偏紧。
# 调大到 120s，只影响单次读操作的超时阈值，不改变下载的实际内容。
ENV PIP_DEFAULT_TIMEOUT=120

# 已在部署服务器实测（2026-08-05）：pytorch/pytorch:*-runtime 系列镜像确实
# 自带 conda（`conda install` 直接可用，本层实测约 79s 完成，含 conda 自身
# 从 pkgs/main 切到 conda-forge 索引的一次性升级），不需要退路方案。
#
# pynini 必须在 pip 安装 requirements.txt 之前装好预编译包，这是头号坑：
# pip 装 pynini 会触发从源码编译（依赖系统级 OpenFst），既慢又容易失败。
#
# --override-channels -c <清华镜像> 而不是 -c conda-forge：后者会解析到
# conda.anaconda.org（国外），--override-channels 确保完全不触碰默认的
# defaults 频道（repo.anaconda.com，国外），只用清华这一个源。
# 已实测清华镜像的 conda-forge/linux-64 repodata 里存在 pynini==2.1.5 的
# py311 构建（本镜像 Python 版本），与原先的 conda-forge 官方源等价。
RUN conda install -y --override-channels \
    -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
    pynini==2.1.5 && conda clean -afy

# 拉取 CosyVoice 官方源码（含 Matcha-TTS 子模块），不修改上游代码。
#
# COSYVOICE_GIT_MIRROR 默认直连 GitHub（git clone 相比 pip/conda 的大体积
# 二进制传输对国内网络更友好，多数环境不需要镜像）；如果部署环境访问
# github.com 不稳定，构建时可覆盖为国内镜像，例如：
#   docker compose build --build-arg COSYVOICE_GIT_MIRROR=https://ghfast.top/https://github.com/ cosyvoice-tts
# ghfast.top 已实测（2026-08-05，部署服务器）：主仓库 + third_party/Matcha-TTS
# 子模块（子模块地址是另一个仓库 shivammehta25/Matcha-TTS，不在 FunAudioLLM
# 命名空间下）都能通过 `git config --global url.insteadOf` 透明代理，
# --recursive 全量克隆约 16s 完成。用 insteadOf 而不是直接改 clone 的 URL，
# 是因为这样子模块地址也会被同一条规则重写，不用额外处理 .gitmodules。
ARG COSYVOICE_GIT_MIRROR=https://github.com/
RUN git config --global url."${COSYVOICE_GIT_MIRROR}".insteadOf "https://github.com/" \
 && git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git /opt/CosyVoice \
 && git config --global --unset url."${COSYVOICE_GIT_MIRROR}".insteadOf

WORKDIR /opt/CosyVoice

# 已在部署服务器实测（2026-08-05）：requirements.txt 里的依赖版本在本镜像
# Python 3.11 下基本都能装，唯一的坑是 openai-whisper==20231117 ——它的
# legacy setup.py 里直接 `import pkg_resources`，而 pip 默认给隔离构建环境
# （pip-build-env-*/overlay）装的是当前最新 setuptools（实测 83.0.0），该
# 版本在这个隔离 venv 场景下解析不到 pkg_resources，导致
# "Getting requirements to build wheel" 阶段直接 ModuleNotFoundError。
# 用 PIP_CONSTRAINT 把隔离构建环境里的 setuptools 钉在仍可用的版本
# （<81，验证可行），不影响 requirements.txt 里其它包的版本解析——
# PIP_CONSTRAINT 只是上限约束，不会强制安装 setuptools 本身。
#
# ttsfrd 跳过（见文件头说明），依赖 wetext 兜底（版本改写见下方）
#
# 另一处网络相关的坑（部署服务器实测确认，2026-08-05）：requirements.txt 里的
# tensorrt-cu12 / tensorrt-cu12-bindings / tensorrt-cu12-libs 是可选加速依赖，
# 其中 tensorrt-cu12-libs 是个 "wheel_stub" 占位包，安装时会硬编码请求
# https://pypi.nvidia.com/ 下载真正的 wheel（不走我们配置的清华镜像，也不支持
# 覆盖），且该域名本身就无国内可用镜像（不是"选错源"，是这个可选加速依赖
# 本身不适合国内环境）。
# 已对照 CosyVoice 源码确认可以安全跳过：tensorrt 只在
# CosyVoiceModel.load_trt() / convert_onnx_to_trt() 方法体内惰性
# `import tensorrt`，不在任何模块顶层，而 server.py 的 lifespan() 固定传
# CosyVoice2(..., load_trt=False)，这两个方法从不会被调用，跳过安装不影响
# 本服务运行时行为（只是放弃一个我们本就没用的可选加速选项）。
#
# 同样跳过 deepspeed==0.15.1（requirements.txt 第 4 行，仅用于分布式训练，
# 已对照 cosyvoice/cli/model.py、cosyvoice/cli/cosyvoice.py 确认推理路径
# 完全不引用 deepspeed）。部署服务器实测复现：deepspeed 装上后，
# transformers.modeling_utils 在 import 时会无条件 `import deepspeed`
# （只要包已安装就触发，不看是否用得到），深入到
# deepspeed/git_version_info.py 会在**每次 import 时**重新执行
# `installed_cuda_version()`——这个函数要求 `torch.utils.cpp_extension.
# CUDA_HOME` 非空且能跑通 `$CUDA_HOME/bin/nvcc -V`。基础镜像是
# pytorch/pytorch:*-runtime（刻意精简、不含 CUDA 开发工具链 nvcc），
# 不是 *-devel，所以这个检查必然失败并原样抛出未捕获异常，直接导致
# 容器启动时崩溃重启（CrashLoopBackOff），日志报
# "CUDA_HOME does not exist, unable to compile CUDA op(s)"。
# 装 nvcc 只为满足这一个用不到的依赖代价过高（镜像体积、构建时间），
# 跳过是更合理的选择。
#
# 国内镜像改写（2026-08-05，全部已用 curl 单独核实可达）：
#   - 第 1 行 --extra-index-url download.pytorch.org/whl/cu121
#     → 阿里云 mirrors.aliyun.com/pytorch-wheels/cu121/（与官方索引目录结构
#       1:1 镜像，已核实存在本镜像所需的 torch/torchaudio/torchvision
#       cp311+cu121 wheel）。
#   - 第 2 行 --extra-index-url aiinfra.pkgs.visualstudio.com/...
#     直接删除，不找替代：这条是给 onnxruntime-gpu 提供 CUDA12 专用构建的
#     私有 Azure Artifacts feed（见行内原注释链接的 onnxruntime#21684），
#     实测（部署服务器 + 本地）访问该域名返回 401
#     "not authorized to access this resource"，需要微软内部凭据，任何
#     镜像站都代理不了这种鉴权流。同时实测确认不需要它：现有镜像
#     onnxruntime-gpu==1.18.0 实际是从清华 pip 主索引装的（这条国外
#     extra-index-url 本来就没生效过，pip 在它不可达时会跳过并回退主索引），
#     生产环境 campplus/speech_tokenizer 两个 onnxruntime session 一直
#     正常跑在 CUDA EP 上，删除这行只是去掉一次必然失败的无效探测，不改变
#     实际安装结果。
#   - wetext==0.0.4 → wetext==0.1.6：见文件头大段说明，根治 ModelScope
#     个人命名空间仓库下载 403 的问题，运行时不再需要任何下载源（国内国外
#     都不需要），比"找镜像"更彻底。
# 用改写后的临时文件安装，不修改 git clone 下来的 requirements.txt 本身。
ENV PIP_CONSTRAINT=/tmp/pip-build-constraints.txt
RUN echo "setuptools<81" > /tmp/pip-build-constraints.txt
RUN sed -E \
      -e 's#^--extra-index-url https://download\.pytorch\.org/whl/cu121$#--extra-index-url https://mirrors.aliyun.com/pytorch-wheels/cu121/#' \
      -e '/^--extra-index-url https:\/\/aiinfra\.pkgs\.visualstudio\.com/d' \
      -e 's/^wetext==0\.0\.4$/wetext==0.1.6/' \
      -e '/^(tensorrt-cu12|deepspeed)/d' \
      requirements.txt > /tmp/requirements.mirrored.txt \
 && pip install --no-cache-dir -r /tmp/requirements.mirrored.txt \
 && pip install --no-cache-dir fastapi "uvicorn[standard]"

# 部署服务器实测确认（2026-08-05）：requirements.txt 只显式钉了
# torch==2.3.1 / torchaudio==2.3.1，没有钉 torchvision 版本。torchvision
# 没有版本约束时 pip 会解析到当前最新的 0.19.0——但 0.19.0 是配 torch 2.4.x
# 发布的，其 _meta_registrations.py 在 import 时用到
# `torch.library.register_fake`，这个 API 在 torch 2.3.1 里不存在，
# 导致容器启动时 `from cosyvoice.cli.cosyvoice import CosyVoice2` 触发的
# import 链在 torchvision 这一步直接 AttributeError，服务反复重启。
# torch 2.3.1 官方配套的 torchvision 版本是 0.18.1，显式重装覆盖上一步
# 装出来的不兼容版本；沿用同一个国内镜像（阿里云 pytorch-wheels）拿到
# +cu121 编译版，与上面 requirements 改写用的是同一个源。
RUN pip install --no-cache-dir --extra-index-url https://mirrors.aliyun.com/pytorch-wheels/cu121/ \
    "torchvision==0.18.1"

# CosyVoice 源码与内置的 Matcha-TTS 子模块都需要在 PYTHONPATH 上，
# 官方 README 与示例代码都是这么处理的
ENV PYTHONPATH=/opt/CosyVoice:/opt/CosyVoice/third_party/Matcha-TTS

COPY server.py /opt/CosyVoice/server.py

RUN mkdir -p /app/logs /root/.cache/modelscope/hub

EXPOSE 8100

# host/port 固定，模型目录与设备通过环境变量传入（COSYVOICE_MODEL_DIR /
# COSYVOICE_DEVICE，见 server.py parse_args 与 docker-compose.yml），
# 与项目 "参数走 .env，不硬编码进镜像" 的约定一致
CMD ["python", "/opt/CosyVoice/server.py"]
