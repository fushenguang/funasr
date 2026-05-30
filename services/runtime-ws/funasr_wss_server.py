#!/usr/bin/env python3
"""
FunASR WebSocket Server
源自官方 runtime/python/websocket/funasr_wss_server.py
内联进镜像，无需 clone GitHub
支持: 2pass 模式（streaming + offline 纠错）, VAD, 标点恢复
"""
import argparse
import asyncio
import json
import logging
import os
import ssl
import time
from datetime import datetime
from typing import Optional

import websockets
from funasr import AutoModel

# ── 日志 ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("funasr.ws")

# ── 全局模型 ──────────────────────────────────────────────────
model_asr = None
model_asr_online = None
model_vad = None
model_punc = None

websocket_users = set()


def load_models(args):
    global model_asr, model_asr_online, model_vad, model_punc

    common = dict(
        device=args.device,
        disable_pbar=True,
        disable_log=True,
        cache_dir=os.getenv("FUNASR_MODEL_DIR", "/app/models"),
        hub="modelscope",
    )

    log.info(f"加载离线 ASR 模型: {args.asr_model}")
    model_asr = AutoModel(model=args.asr_model, **common)

    log.info(f"加载流式 ASR 模型: {args.asr_model_online}")
    model_asr_online = AutoModel(model=args.asr_model_online, **common)

    log.info(f"加载 VAD 模型: {args.vad_model}")
    model_vad = AutoModel(model=args.vad_model, **common)

    if args.punc_model:
        log.info(f"加载标点模型: {args.punc_model}")
        model_punc = AutoModel(model=args.punc_model, **common)

    log.info("所有模型加载完成")


async def ws_handler(websocket, path=""):
    """处理单个 WebSocket 连接"""
    client_id = id(websocket)
    remote = websocket.remote_address
    log.info(f"[{client_id}] 连接建立: {remote}")
    websocket_users.add(websocket)

    # 每个连接维护自己的流式状态
    cache = {}
    speech_start = False
    final_results = []
    t_start = time.time()

    try:
        async for message in websocket:
            if isinstance(message, str):
                # 控制消息（JSON）
                try:
                    msg = json.loads(message)
                    if msg.get("is_speaking") is False:
                        # 客户端说话结束，做离线纠错
                        if final_results:
                            combined = "".join(final_results)
                            if model_punc:
                                result = model_punc.generate(input=combined, cache={})
                                combined = result[0]["text"] if result else combined
                            await websocket.send(json.dumps({
                                "mode": "offline",
                                "text": combined,
                                "is_final": True,
                                "timestamp": datetime.utcnow().isoformat(),
                            }))
                        final_results.clear()
                        cache.clear()
                except json.JSONDecodeError:
                    pass

            elif isinstance(message, bytes):
                # 音频数据块 → 流式识别
                try:
                    result = model_asr_online.generate(
                        input=message,
                        cache=cache,
                        is_final=False,
                        chunk_size=[5, 10, 5],
                        encoder_chunk_look_back=4,
                        decoder_chunk_look_back=1,
                    )
                    if result and result[0].get("text"):
                        text = result[0]["text"]
                        final_results.append(text)
                        await websocket.send(json.dumps({
                            "mode": "online",
                            "text": text,
                            "is_final": False,
                            "timestamp": datetime.utcnow().isoformat(),
                        }))
                except Exception as e:
                    log.error(f"[{client_id}] 推理失败: {e}")

    except websockets.exceptions.ConnectionClosedOK:
        pass
    except websockets.exceptions.ConnectionClosedError as e:
        log.warning(f"[{client_id}] 连接异常关闭: {e}")
    except Exception as e:
        log.error(f"[{client_id}] 未预期错误: {e}", exc_info=True)
    finally:
        websocket_users.discard(websocket)
        elapsed = round(time.time() - t_start, 2)
        log.info(f"[{client_id}] 连接关闭: {remote}, 持续 {elapsed}s")


def parse_args():
    p = argparse.ArgumentParser("FunASR WebSocket Server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=10095)
    p.add_argument("--device", default=os.getenv("FUNASR_DEVICE", "cuda"))
    p.add_argument("--asr-model", default=os.getenv("WS_ASR_MODEL", "iic/SenseVoiceSmall"))
    p.add_argument("--asr-model-online", default=os.getenv("WS_ASR_ONLINE_MODEL",
        "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"))
    p.add_argument("--vad-model", default=os.getenv("WS_VAD_MODEL",
        "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"))
    p.add_argument("--punc-model", default=os.getenv("WS_PUNC_MODEL",
        "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"))
    p.add_argument("--hotword", default="")
    p.add_argument("--ngpu", type=int, default=1)
    p.add_argument("--ncpu", type=int, default=4)
    return p.parse_args()


async def main_async(args):
    load_models(args)
    log.info(f"WebSocket 服务启动: ws://{args.host}:{args.port}")
    async with websockets.serve(
        ws_handler,
        args.host,
        args.port,
        max_size=100 * 1024 * 1024,  # 100MB 最大消息
        ping_interval=20,
        ping_timeout=30,
    ):
        await asyncio.Future()  # 永久运行


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main_async(args))
