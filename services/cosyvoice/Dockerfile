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
#      不匹配，这里主动跳过，退回用 requirements.txt 自带的
#      WeTextProcessing 兜底（功能可用，精度略低于 ttsfrd）。
#   3. 模型落盘目录是 iic_CosyVoice2-0.5B（单个下划线）。
#      download_models.sh 的 tr '/' '__' 是字符映射不是字符串替换，
#      '/' 只映射成一个 '_'；已在部署服务器上以 iic_SenseVoiceSmall 实证。
#      不是 iic/CosyVoice2-0.5B 子目录，详见 server.py 启动时的校验逻辑。
# ============================================================
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

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
RUN conda install -y -c conda-forge pynini==2.1.5 && conda clean -afy

# 拉取 CosyVoice 官方源码（含 Matcha-TTS 子模块），不修改上游代码
RUN git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git /opt/CosyVoice

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
# ttsfrd 跳过（见文件头说明），依赖 requirements.txt 自带的 WeTextProcessing 兜底
#
# 另一处网络相关的坑（部署服务器实测确认，2026-08-05）：requirements.txt 里的
# tensorrt-cu12 / tensorrt-cu12-bindings / tensorrt-cu12-libs 是可选加速依赖，
# 其中 tensorrt-cu12-libs 是个 "wheel_stub" 占位包，安装时会硬编码请求
# https://pypi.nvidia.com/ 下载真正的 wheel（不走我们配置的清华镜像，也不支持
# 覆盖）。部署服务器所在网络访问 pypi.nvidia.com（以及 download.pytorch.org、
# aiinfra.pkgs.visualstudio.com）均是 TLS 层直接失败（SSL: wrong version
# number，用 curl 对这几个域名单独测试也复现，是网络层面而非 pip/镜像问题），
# 导致这一步必然装不上。
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
# 用过滤后的临时文件安装，不修改 git clone 下来的 requirements.txt 本身。
ENV PIP_CONSTRAINT=/tmp/pip-build-constraints.txt
RUN echo "setuptools<81" > /tmp/pip-build-constraints.txt
RUN grep -vE '^(tensorrt-cu12|deepspeed)' requirements.txt > /tmp/requirements.no-trt.txt \
 && pip install --no-cache-dir -r /tmp/requirements.no-trt.txt \
 && pip install --no-cache-dir fastapi "uvicorn[standard]"

# 部署服务器实测确认（2026-08-05）：requirements.txt 只显式钉了
# torch==2.3.1 / torchaudio==2.3.1，没有钉 torchvision 版本。torchvision
# 没有版本约束时 pip 会解析到当前最新的 0.19.0——但 0.19.0 是配 torch 2.4.x
# 发布的，其 _meta_registrations.py 在 import 时用到
# `torch.library.register_fake`，这个 API 在 torch 2.3.1 里不存在，
# 导致容器启动时 `from cosyvoice.cli.cosyvoice import CosyVoice2` 触发的
# import 链在 torchvision 这一步直接 AttributeError，服务反复重启。
# torch 2.3.1 官方配套的 torchvision 版本是 0.18.1，显式重装覆盖上一步
# 装出来的不兼容版本；沿用同一个 --extra-index-url 拿到 +cu121 编译版。
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu121 \
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
