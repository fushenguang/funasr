#!/usr/bin/env bash
set -euo pipefail

echo "[ws-start] FunASR WebSocket Server 启动"
echo "[ws-start] Device=${FUNASR_DEVICE:-cuda}, Port=${WS_PORT:-10095}"

exec python /app/funasr_wss_server.py \
    --host 0.0.0.0 \
    --port "${WS_PORT:-10095}" \
    --device "${FUNASR_DEVICE:-cuda}" \
    --asr-model "${WS_ASR_MODEL:-iic/SenseVoiceSmall}" \
    --asr-model-online "${WS_ASR_ONLINE_MODEL:-iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online}" \
    --vad-model "${WS_VAD_MODEL:-iic/speech_fsmn_vad_zh-cn-16k-common-pytorch}" \
    --punc-model "${WS_PUNC_MODEL:-iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch}"
