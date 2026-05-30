"""
FunASR OpenAI 兼容 API 服务
基于官方 server.py 增强:
  - 结构化 JSON 日志（每次请求记录完整上下文）
  - 请求 ID 追踪（X-Request-ID）
  - 详细的性能指标记录
  - 优雅关闭
  - /metrics 端点（Prometheus 格式，预留）
"""
import argparse
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from logging_config import setup_logging

# ── 日志初始化（在 import funasr 之前，避免 funasr 日志污染）
log = setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_dir=os.getenv("LOG_DIR", "/app/logs"),
)

# ── 延迟 import FunASR（避免在日志前输出大量加载信息）
from funasr import AutoModel  # noqa: E402

# ── 全局模型实例
_model: Optional[AutoModel] = None
_model_alias: str = ""
_device: str = ""


# ── 应用生命周期 ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动/关闭钩子"""
    global _model, _model_alias, _device

    args = app.state.args
    _model_alias = args.model
    _device = args.device

    log.info(
        "Loading model",
        extra={
            "event": "model_load_start",
            "model": _model_alias,
            "device": _device,
            "model_dir": args.model_dir,
        },
    )

    t0 = time.time()
    try:
        _model = AutoModel(
            model=_model_alias,
            device=_device,
            cache_dir=args.model_dir,
            hub="modelscope",
            disable_update=True,
        )
        elapsed = round(time.time() - t0, 2)
        log.info(
            "Model loaded successfully",
            extra={
                "event": "model_load_done",
                "model": _model_alias,
                "device": _device,
                "load_time_s": elapsed,
            },
        )
    except Exception as e:
        log.error(
            "Failed to load model",
            extra={
                "event": "model_load_failed",
                "model": _model_alias,
                "error": str(e),
            },
            exc_info=True,
        )
        raise

    yield  # 服务运行期间

    log.info("Service shutting down", extra={"event": "shutdown"})


# ── FastAPI 应用 ──────────────────────────────────────────────
app = FastAPI(
    title="FunASR API",
    description="OpenAI 兼容语音转写服务",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 内网部署，可以放开；外网时收紧
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 中间件：请求追踪 + 访问日志 ──────────────────────────────
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.start_time = time.time()

    # 请求进入日志
    log.info(
        "Request received",
        extra={
            "event": "request_start",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "unknown",
        },
    )

    response = await call_next(request)

    # 请求完成日志
    elapsed_ms = round((time.time() - request.state.start_time) * 1000, 1)
    log.info(
        "Request completed",
        extra={
            "event": "request_done",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": elapsed_ms,
        },
    )

    response.headers["X-Request-ID"] = request_id
    return response


# ── 健康检查 ──────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": _model_alias,
        "device": _device,
        "model_loaded": _model is not None,
    }


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "sensevoice", "object": "model"},
            {"id": "paraformer", "object": "model"},
            {"id": "paraformer-en", "object": "model"},
        ],
    }


# ── 核心转写接口 ──────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024


@app.post("/v1/audio/transcriptions")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("sensevoice"),
    response_format: str = Form("json"),
    language: Optional[str] = Form(None),
    temperature: float = Form(0.0),
):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    # 文件大小检查
    content = await file.read()
    file_size_mb = round(len(content) / 1024 / 1024, 2)

    if len(content) > MAX_UPLOAD_BYTES:
        log.warning(
            "File too large",
            extra={
                "event": "upload_rejected",
                "request_id": request_id,
                "file_size_mb": file_size_mb,
                "limit_mb": MAX_UPLOAD_BYTES // 1024 // 1024,
                "filename": file.filename,
            },
        )
        raise HTTPException(
            status_code=413,
            detail=f"文件过大: {file_size_mb}MB，限制 {MAX_UPLOAD_BYTES // 1024 // 1024}MB",
        )

    log.info(
        "Transcription started",
        extra={
            "event": "transcription_start",
            "request_id": request_id,
            "filename": file.filename,
            "file_size_mb": file_size_mb,
            "model": model,
            "response_format": response_format,
            "language": language,
        },
    )

    t0 = time.time()
    try:
        # 写临时文件（FunASR 需要文件路径）
        import tempfile
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(file.filename or ".wav")[1] or ".wav",
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = _model.generate(
            input=tmp_path,
            cache={},
            language=language or "auto",
            use_itn=True,
            batch_size_s=300,
        )

        os.unlink(tmp_path)

        elapsed_s = round(time.time() - t0, 3)

        # 解析结果
        if isinstance(result, list) and len(result) > 0:
            text = result[0].get("text", "")
            segments = result[0].get("timestamp", [])
        else:
            text = ""
            segments = []

        # 估算音频时长（粗略，基于文件大小）
        audio_duration_s = None
        if segments:
            try:
                audio_duration_s = round(segments[-1][1] / 1000, 2)
            except Exception:
                pass

        log.info(
            "Transcription done",
            extra={
                "event": "transcription_done",
                "request_id": request_id,
                "filename": file.filename,
                "file_size_mb": file_size_mb,
                "model": model,
                "audio_duration_s": audio_duration_s,
                "inference_time_s": elapsed_s,
                "rtf": round(elapsed_s / audio_duration_s, 4) if audio_duration_s else None,
                "text_length": len(text),
                "segments_count": len(segments),
            },
        )

    except Exception as e:
        elapsed_s = round(time.time() - t0, 3)
        log.error(
            "Transcription failed",
            extra={
                "event": "transcription_error",
                "request_id": request_id,
                "filename": file.filename,
                "file_size_mb": file_size_mb,
                "model": model,
                "inference_time_s": elapsed_s,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"转写失败: {str(e)}")

    # 返回格式
    if response_format == "text":
        return text
    elif response_format == "verbose_json":
        return JSONResponse({
            "task": "transcribe",
            "language": language or "zh",
            "duration": audio_duration_s,
            "text": text,
            "segments": [
                {
                    "id": i,
                    "start": seg[0] / 1000 if seg else 0,
                    "end": seg[1] / 1000 if len(seg) > 1 else 0,
                    "text": seg[2] if len(seg) > 2 else "",
                }
                for i, seg in enumerate(segments)
            ],
            "x_request_id": request_id,
        })
    else:  # json (默认)
        return JSONResponse({"text": text, "x_request_id": request_id})


# ── 入口 ──────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="FunASR OpenAI 兼容 API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", default=os.getenv("FUNASR_DEVICE", "cuda"))
    parser.add_argument("--model", default=os.getenv("FUNASR_MODEL", "SenseVoiceSmall"))
    parser.add_argument("--model-dir", default=os.getenv("FUNASR_MODEL_DIR", "/app/models"))
    parser.add_argument("--workers", type=int, default=1,
                        help="uvicorn workers，GPU 服务通常保持 1，多实例靠 Compose scale")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app.state.args = args

    log.info(
        "Starting FunASR API server",
        extra={
            "event": "startup",
            "host": args.host,
            "port": args.port,
            "device": args.device,
            "model": args.model,
            "model_dir": args.model_dir,
        },
    )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=args.workers,
        log_config=None,   # 禁用 uvicorn 默认日志，用我们自己的
        access_log=False,  # 访问日志由中间件处理
    )
