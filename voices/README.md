# voices/ — CosyVoice2 命名音色参考音频

`cosyvoice-tts` 服务使用**服务端预注册命名音色**（zero-shot 音色克隆）：
客户端调用 `POST /v1/audio/speech` 时只传 `{input, voice}`，`voice` 是这里配置好的
音色 id（例如 `xiaoxi`），参考音频与其文字转录全部在服务端准备，不接受客户端上传参考音频。

## 目录约定

本目录挂载进 `cosyvoice-tts` 容器的 `/opt/voices`（只读）。每个命名音色需要一对配置：

1. **参考音频**：`16kHz 单声道 WAV`。CosyVoice 内部会用它做 zero-shot 音色克隆的 prompt。
2. **准确文字转录**：参考音频里念的那句话，逐字对应（标点、语气词都尽量还原），
   通过 `.env` 里的 `<NAME>_PROMPT_TEXT` 配置——转录不准会明显拉低合成效果。

`server.py` 启动时按环境变量命名约定自动发现并注册音色：
`<NAME>_PROMPT_WAV` + `<NAME>_PROMPT_TEXT` 成对出现，`NAME` 小写后作为音色 id。
例如 `.env` 里的：

```
XIAOXI_PROMPT_WAV=/opt/voices/xiaoxi_16k.wav
XIAOXI_PROMPT_TEXT=参考音频里念的那句话的准确转录
```

会注册出音色 `xiaoxi`。**新增音色只需要把 WAV 放进本目录、在 `.env` 里加一对同名变量、
重启 `cosyvoice-tts` 容器**，不需要改代码。

## 快速跑通（先用官方示例音频占位）

在准备自己的音色之前，可以先用 CosyVoice 仓库自带的示例音频跑通链路：

```bash
# 容器内已 clone 到 /opt/CosyVoice，示例音频在 /opt/CosyVoice/asset/ 下
docker compose exec cosyvoice-tts cp /opt/CosyVoice/asset/zero_shot_prompt.wav /tmp/
docker compose cp cosyvoice-tts:/tmp/zero_shot_prompt.wav ./voices/xiaoxi_16k.wav
```

具体文件名以 CosyVoice 仓库 `asset/` 目录实际内容为准（不同版本可能不同），
配套的转录文本可在官方 README / 示例脚本中找到，抄进 `.env` 的 `XIAOXI_PROMPT_TEXT`。

## ⚠️ 重要：音色合规要求

- **参考音频必须是自己录制的，或已获得明确授权的音源**。
- **不得克隆真实人物（尤其是公众人物、他人）的声音而未经其同意** —— 这既是法律风险，
  也是本项目内网部署场景下必须遵守的红线。仅用于内部测试的官方示例音频除外。
- 生产环境音色建议由专人录制标准普通话/目标语种样本，时长与内容需覆盖足够的音素多样性。

## 关于版本控制

本目录下的 `.wav` 文件**不进 Git**（见根目录 `.gitignore` 的 `voices/*.wav`），
原因与 `models/` 一致：音频物料体积大、且可能涉及肖像权/声音权风险，不适合入库。
只有 `.gitkeep` 与本 README 会被提交。
