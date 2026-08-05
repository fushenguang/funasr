"""
CosyVoice2-0.5B OpenAI 兼容 TTS 服务

只暴露一个核心接口：POST /v1/audio/speech（OpenAI Audio Speech 兼容），
流式返回裸 PCM16LE mono @ 24000Hz（无 WAV 头），音色用服务端预注册的
命名音色（zero_shot_spk_id），客户端只需传 {input, voice}，参考音频与其
文字转录全部在服务端配置，不接受客户端上传参考音频。

设计参照 services/openai-api/server.py 的骨架风格（lifespan 载模型 /
请求追踪 / OpenAI 路由 / parse_args + uvicorn.run），但不 import 它——
那是另一个未启用的备选服务，两者相互独立。

★ 关键坑（务必先读，改动前确认没有破坏这些点）：
  1. 模型路径：download_models.sh 用 `tr '/' '__'` 处理 model_id。注意
     tr 是**字符映射**不是字符串替换——SET1 只有 '/' 一个字符，映射到
     SET2 的第一个字符 '_'，多余的 '_' 被忽略。所以落盘目录是
     iic_CosyVoice2-0.5B（单个下划线），既不是双下划线，也不是
     iic/CosyVoice2-0.5B 子目录。已在部署服务器上以既有的
     iic_SenseVoiceSmall 目录实证。启动时会显式校验目录存在，
     不存在直接 fail fast 并打印期望路径。
  2. CosyVoice 的 inference_zero_shot 是阻塞的同步生成器（GPU 推理），
     绝不能在 async 生成器里直接 for 迭代——那会卡死整个 event loop，
     合成期间 /health 无响应，docker healthcheck（10s 超时）会判
     unhealthy 进而反复重启容器。这里用 asyncio.to_thread 把同步生成器
     的迭代丢进线程池，通过 asyncio.Queue 桥接回 async 世界。
  3. asyncio.Lock 用来串行化 GPU 访问（CosyVoice 单实例非线程安全），
     锁的生命周期覆盖到"本请求流式产出结束"为止，而不是只包住调用
     inference_zero_shot() 那一行——否则并发请求会同时抢 GPU。
  4. 客户端中途断连（GeneratorExit / CancelledError）要能正确停止推理
     线程、关闭底层生成器、并释放锁，不能让线程和显存占用悬空。
"""
import argparse
import asyncio
import logging
import logging.handlers
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Tuple

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

# ── 常量 ──────────────────────────────────────────────────────
SAMPLE_RATE = 24000  # CosyVoice2 固定输出采样率，与 API 契约一致
PCM_MEDIA_TYPE = "application/octet-stream"


# ── 日志初始化（简单版：stdout + 可选文件，风格上呼应 openai-api 的
#    setup_logging，但不引入外部依赖，保持本文件自包含）───────────
def setup_logging() -> logging.Logger:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "/app/logs")

    logger = logging.getLogger("cosyvoice-tts")
    logger.setLevel(log_level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "cosyvoice-tts.log"),
            maxBytes=50 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as e:
        # 日志目录不可写不应该阻塞服务启动，降级为仅 stdout
        logger.warning("无法写入日志文件 %s，降级为仅 stdout: %s", log_dir, e)

    return logger


log = setup_logging()

# ── 全局状态 ──────────────────────────────────────────────────
_model = None
# _device 报告的是**实际**运行设备（由 torch 探测），不是 .env 里请求的值。
# CosyVoice2() 构造函数没有 device 参数（见 wiki/…/tts-cosyvoice.mdx 的 API 表），
# 设备完全由 torch 自行决定，所以把 COSYVOICE_DEVICE 的值直接回显到 /health
# 会在「请求 cuda 但实际跑在 CPU」时给出错误信号，误导排查。
_device: str = ""
_device_requested: str = ""
_gpu_lock = asyncio.Lock()  # 串行化 GPU 访问；Python 3.10+ 无需绑定 event loop 构造
# 服务端预注册的命名音色：{voice_id: (prompt_wav_path, prompt_text)}
# 只保存"已成功注册"的音色，供 /health、/v1/audio/voices 与请求校验使用
VOICE_SEEDS: Dict[str, Tuple[str, str]] = {}


def _discover_voice_seeds() -> Dict[str, Tuple[str, str]]:
    """
    从环境变量发现待注册的命名音色。

    约定：<NAME>_PROMPT_WAV 与 <NAME>_PROMPT_TEXT 成对出现，NAME 小写后
    作为音色 id。例如 XIAOXI_PROMPT_WAV / XIAOXI_PROMPT_TEXT 会注册出
    音色 "xiaoxi"。这是本服务相对需求文档的一点主动加固：新增音色只需要
    在 .env / compose environment 里加一对变量，不需要改代码。
    当前 docker-compose.yml 只声明了 XIAOXI_* 一对，属于该机制下的默认值。
    """
    seeds: Dict[str, Tuple[str, str]] = {}
    suffix = "_PROMPT_WAV"
    for key, value in os.environ.items():
        if not key.endswith(suffix) or not value:
            continue
        prefix = key[: -len(suffix)]
        voice_id = prefix.lower()
        prompt_text = os.environ.get(f"{prefix}_PROMPT_TEXT", "")
        seeds[voice_id] = (value, prompt_text)
    return seeds


# ── 应用生命周期：加载模型 + 注册命名音色 ─────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _device, _device_requested

    # 兜底 parse_args()：正常路径是 __main__ 里已设好 app.state.args，
    # 但用 `uvicorn server:app` 这类外部 ASGI 启动方式时 state 是空的，
    # 没有兜底会在 lifespan 里抛 AttributeError，报错信息还很难懂
    args = getattr(app.state, "args", None) or parse_args()
    _device_requested = args.device
    model_dir = args.model_dir

    # 坑 1：fail fast，不要让路径错误在模型加载深处报一个难懂的错
    if not os.path.isdir(model_dir):
        raise RuntimeError(
            f"CosyVoice2 模型目录不存在: {model_dir}\n"
            "请确认已执行 `bash scripts/download_models.sh --tts-only`，"
            "且 ModelScope 实际落盘目录名与此路径一致 —— "
            "正确形态是 iic_CosyVoice2-0.5B（单下划线），"
            "不是 iic/CosyVoice2-0.5B 子目录。"
            "服务器上可用 `ls /root/.cache/modelscope/hub` 核实真实目录名。"
        )

    # 延迟 import：避免模块加载期就依赖 cosyvoice 包（例如 --help 场景）
    import torch

    from cosyvoice.cli.cosyvoice import CosyVoice2

    # 探测真实设备而不是回显配置值，见 _device 的定义处说明
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    if _device_requested == "cuda" and _device != "cuda":
        log.warning(
            "配置请求 device=cuda，但 torch.cuda.is_available() 为 False，"
            "实际将在 CPU 上推理（会非常慢）。请检查 NVIDIA Container Toolkit "
            "与 compose 的 deploy.resources.reservations.devices 配置。"
        )

    log.info("加载 CosyVoice2 模型: %s (device=%s) ...", model_dir, _device)
    t0 = time.time()
    try:
        _model = CosyVoice2(
            model_dir, load_jit=False, load_trt=False, load_vllm=False, fp16=True
        )
    except Exception:
        log.error("CosyVoice2 模型加载失败", exc_info=True)
        raise

    if _model.sample_rate != SAMPLE_RATE:
        # API 契约写死 24000Hz，模型实际采样率不符就直接拒绝启动，
        # 避免悄悄返回和契约不一致的音频
        raise RuntimeError(
            f"CosyVoice2 模型采样率为 {_model.sample_rate}Hz，"
            f"与 API 契约约定的 {SAMPLE_RATE}Hz 不符，拒绝启动。"
        )
    log.info("模型加载完成，用时 %.1fs", time.time() - t0)

    # 注册服务端预置命名音色（zero_shot_spk_id）
    seeds = _discover_voice_seeds()
    if not seeds:
        log.warning(
            "未发现任何 <NAME>_PROMPT_WAV 环境变量，没有可用命名音色，"
            "/v1/audio/speech 会对所有请求返回 400"
        )

    for voice_id, (wav_path, prompt_text) in seeds.items():
        if not os.path.isfile(wav_path):
            log.warning("音色 %s 的参考音频不存在，跳过注册: %s", voice_id, wav_path)
            continue
        if not prompt_text.strip():
            log.warning(
                "音色 %s 缺少 PROMPT_TEXT（参考音频的准确文字转录），跳过注册", voice_id
            )
            continue
        try:
            # 部署服务器实测踩坑（2026-08-05）：add_zero_shot_spk 的第二个参数
            # 官方签名叫 prompt_wav，必须是**文件路径字符串**，不是预加载的波形
            # tensor——内部 frontend_zero_shot -> _extract_speech_feat 会自己
            # 用 load_wav(prompt_wav, 24000) 重新按需要的采样率加载一次（且和
            # 说话人向量提取用的采样率不是同一个，由 CosyVoice 内部各自处理，
            # 不需要也不应该由调用方预先 resample）。旧代码在这里手动
            # load_wav(wav_path, 16000) 传了个 tensor 进去，导致
            # torchaudio.load 收到 tensor 而不是路径直接 TypeError，
            # 音色注册在服务器上 100% 复现失败。对照官方 example.py 的用法
            # （add_zero_shot_spk(text, './asset/xxx.wav', spk_id)）确认应
            # 该直接传路径。
            _model.add_zero_shot_spk(prompt_text, wav_path, voice_id)
            VOICE_SEEDS[voice_id] = (wav_path, prompt_text)
            log.info("已注册命名音色: %s (%s)", voice_id, wav_path)
        except Exception:
            log.error("注册音色 %s 失败，跳过", voice_id, exc_info=True)

    if VOICE_SEEDS:
        try:
            # 落盘 <model_dir>/spk2info.pt；仅内存注册（add_zero_shot_spk）
            # 在进程重启后会丢失，需要显式 save_spkinfo() 才能持久化。
            # 若模型目录以只读方式挂载，这里会失败——降级为"仅本次运行内存
            # 注册"并 warn，不影响本次服务可用性。
            _model.save_spkinfo()
            log.info("已落盘 spk2info.pt（%d 个音色）", len(VOICE_SEEDS))
        except Exception as e:
            log.warning(
                "落盘 spk2info.pt 失败（模型目录可能只读），"
                "本次运行仅内存注册音色，不影响使用: %s",
                e,
            )

    yield

    log.info("CosyVoice TTS 服务关闭")


# ── FastAPI 应用 ──────────────────────────────────────────────
app = FastAPI(
    title="CosyVoice2 TTS API",
    description="OpenAI 兼容语音合成服务（流式 PCM16LE @ 24000Hz）",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 内网部署，与 funasr-api 一致放开；外网时收紧
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    t0 = time.time()

    response = await call_next(request)

    elapsed_ms = round((time.time() - t0) * 1000, 1)
    log.info(
        "%s %s -> %s (%.1fms) [request_id=%s]",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ── 健康检查 / 音色列表 ──────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok" if _model is not None else "loading",
        "model": "cosyvoice2",
        "device": _device,                     # torch 探测到的真实设备
        "device_requested": _device_requested,  # .env 里请求的值，两者不一致说明 GPU 没挂上
        "model_loaded": _model is not None,
        "voices": sorted(VOICE_SEEDS.keys()),
    }


@app.get("/v1/audio/voices")
async def list_voices():
    return {
        "object": "list",
        "data": [{"id": voice_id, "object": "voice"} for voice_id in sorted(VOICE_SEEDS.keys())],
    }


# ── 核心合成接口 ──────────────────────────────────────────────
class SpeechRequest(BaseModel):
    model: str = "cosyvoice2"
    input: str
    voice: str
    response_format: str = "pcm"
    speed: float = 1.0
    stream: bool = True


def _validate_speech_request(body: SpeechRequest) -> None:
    if not body.input or not body.input.strip():
        raise HTTPException(status_code=400, detail="input 不能为空")
    if body.response_format != "pcm":
        raise HTTPException(
            status_code=400,
            detail=f"仅支持 response_format=pcm（裸 PCM16LE mono @ {SAMPLE_RATE}Hz），"
            f"收到: {body.response_format!r}",
        )
    if body.voice not in VOICE_SEEDS:
        raise HTTPException(
            status_code=400,
            detail=f"未注册的音色: {body.voice!r}，可用音色: {sorted(VOICE_SEEDS.keys())}",
        )
    # 与 OpenAI Audio Speech 一致限定 0.25~4.0。不校验的话 speed=0 / 负数
    # 会在推理深处炸成 500，而契约要求这类输入问题一律以 4xx 明确拒绝
    if not (0.25 <= body.speed <= 4.0):
        raise HTTPException(
            status_code=400,
            detail=f"speed 需在 0.25~4.0 之间，收到: {body.speed}",
        )


async def _pcm_stream(text: str, voice: str, speed: float, request_id: str) -> AsyncGenerator[bytes, None]:
    """
    合成并流式产出 PCM16LE 字节块。

    坑 2/3/4 都在这里处理：
      - 用 asyncio.to_thread 把同步阻塞的 inference_zero_shot 生成器丢进
        线程池迭代，通过 asyncio.Queue 把每个音频块桥接回 async 世界，
        绝不在这个 async 生成器里直接 for 迭代同步生成器。
      - async with _gpu_lock 包住"从开始推理到流式产出结束"的全过程，
        串行化 GPU 访问；请求异常/客户端断连时锁也会正常释放。
      - stop_event 用于客户端中途断连（GeneratorExit / CancelledError）
        时通知生产者线程尽快停止，并显式 close() 底层生成器。
    """
    async with _gpu_lock:
        loop = asyncio.get_running_loop()
        # 队列必须无界：生产者线程只能用 call_soon_threadsafe(queue.put_nowait, ...)
        # 往回投递，而 put_nowait 在队列满时抛 QueueFull——异常发生在 event loop
        # 的回调里而不是生产者线程里，结果是「音频块被静默丢弃 + loop 里冒出一个
        # 无人处理的异常」，客户端听到的是缺帧的音频却收不到任何错误。
        # 设 maxsize 只会制造背压的假象（生产者根本不会被阻塞）。
        # 内存上界可控：合成时长 × 48KB/s（24000Hz × 2B），且 _gpu_lock 保证
        # 同一时刻只有一个请求在缓冲。真要背压得改用
        # asyncio.run_coroutine_threadsafe(queue.put(x), loop).result(timeout=...)
        # 配合 stop_event 轮询，代价是复杂度上升。
        queue: "asyncio.Queue" = asyncio.Queue()
        stop_event = threading.Event()
        SENTINEL = object()
        error_box: Dict[str, BaseException] = {}

        def producer() -> None:
            gen = _model.inference_zero_shot(
                text, "", "", zero_shot_spk_id=voice, stream=True, speed=speed
            )
            try:
                for out in gen:
                    if stop_event.is_set():
                        break
                    chunk = out["tts_speech"]
                    # .cpu() 必须有：stream 模式下 tensor 可能仍在 GPU 上，
                    # 直接 .numpy() 会报错
                    pcm_f32 = chunk.cpu().numpy()
                    # 官方实现没有 clip；极端幅值转 int16 时会 wrap 产生爆音，
                    # 这里的 np.clip 是我们相对官方的主动加固
                    pcm_f32 = np.clip(pcm_f32, -1.0, 1.0)
                    pcm_bytes = (pcm_f32 * 32767.0).astype(np.int16).tobytes()
                    loop.call_soon_threadsafe(queue.put_nowait, pcm_bytes)
            except BaseException as e:  # noqa: BLE001 - 需要把异常带回 async 侧
                error_box["error"] = e
            finally:
                closer = getattr(gen, "close", None)
                if closer:
                    closer()
                loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

        producer_task = asyncio.create_task(asyncio.to_thread(producer))
        chunk_count = 0
        try:
            while True:
                item = await queue.get()
                if item is SENTINEL:
                    break
                chunk_count += 1
                yield item

            if "error" in error_box:
                raise error_box["error"]

            log.info(
                "TTS 合成完成 voice=%s chunks=%d [request_id=%s]",
                voice,
                chunk_count,
                request_id,
            )
        except (asyncio.CancelledError, GeneratorExit):
            log.warning(
                "客户端断连，停止 TTS 推理 voice=%s [request_id=%s]", voice, request_id
            )
            stop_event.set()
            raise
        finally:
            stop_event.set()
            # 等待生产者线程真正退出，避免线程/显存占用悬空
            try:
                await producer_task
            except Exception:
                # 生产者内部异常已经通过 error_box 处理过，这里只是确保线程收尾
                pass


@app.post("/v1/audio/speech")
async def audio_speech(request: Request, body: SpeechRequest):
    _validate_speech_request(body)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    log.info(
        "TTS 请求 voice=%s stream=%s speed=%s input_len=%d [request_id=%s]",
        body.voice,
        body.stream,
        body.speed,
        len(body.input),
        request_id,
    )

    if body.stream:
        return StreamingResponse(
            _pcm_stream(body.input, body.voice, body.speed, request_id),
            media_type=PCM_MEDIA_TYPE,
            headers={"X-Request-ID": request_id},
        )

    # 非流式：仍然复用同一条推理路径（同样受 _gpu_lock 保护），
    # 只是在返回给客户端前把所有分片在服务端拼完整
    buf = bytearray()
    async for chunk in _pcm_stream(body.input, body.voice, body.speed, request_id):
        buf.extend(chunk)
    return Response(
        content=bytes(buf),
        media_type=PCM_MEDIA_TYPE,
        headers={"X-Request-ID": request_id},
    )


# TODO(须服务器核实): inference_instruct2 + 命名音色 + 空 prompt_wav 的缓存分支
# 本轮不实现 instruct2（指令控制情感/语速等更细粒度合成），只在此处留扩展点。
# 若后续需要，预期是新增 body.instruct 字段，命中时改调用
# model.inference_instruct2(text, instruct_text, '', zero_shot_spk_id=voice, ...)。


# ── 入口 ──────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="CosyVoice2 OpenAI 兼容 TTS API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--device", default=os.getenv("COSYVOICE_DEVICE", "cuda"))
    parser.add_argument(
        "--model-dir",
        default=os.getenv(
            "COSYVOICE_MODEL_DIR",
            "/root/.cache/modelscope/hub/iic_CosyVoice2-0.5B",
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app.state.args = args

    log.info(
        "启动 CosyVoice TTS 服务 host=%s port=%s device=%s model_dir=%s",
        args.host,
        args.port,
        args.device,
        args.model_dir,
    )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=1,  # GPU 服务只能单进程，多实例靠 Compose scale（当前未开放 scale，见 wiki 文档的显存提示）
        log_config=None,
        access_log=False,  # 访问日志由中间件统一处理
    )
