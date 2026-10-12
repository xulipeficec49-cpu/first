# -*- coding: utf-8 -*-
"""OpenRouter 语音识别（POST /api/v1/audio/transcriptions）：配音复核的"第二个识别"，没有百炼 Key 时用。

tts_gemini._asr2 在没有百炼 Key（或 cfg.asr2 == "openrouter"）时转到这里；letter_check.py / term_check.py 经 _asr2 间接用到。
接口（OpenRouter 模型页 llms.txt）：JSON {model, input_audio: {data: base64, format: "wav"}}，返回 {text, usage}；
response_format "verbose_json" 可额外给词时间戳（取决于上游是否支持）。
识别模型默认 openai/whisper-large-v3（中文字母序列、数字都比较稳；cfg.asr_model 可换，如 openai/gpt-4o-transcribe）。
Key 同配音（tts_mai.load_key / headers）：环境变量、~/.openrouter_api_key，或 Network secret 由代理注入。
"""
import base64
import io
import json
import time
import wave

import requests

import tts_mai

URL = "https://openrouter.ai/api/v1/audio/transcriptions"


def _wav(pcm, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def transcribe(pcm, sr, cfg, words=False):
    """24kHz 单声道 int16 PCM -> 识别文字（words=True 时返回 (文字, 词时间戳列表或 None)）"""
    key = tts_mai.load_key(cfg)
    audio = {"data": base64.b64encode(_wav(pcm, sr)).decode("ascii"), "format": "wav"}
    model = cfg.get("asr_model", "openai/whisper-large-v3")
    full = {"model": model, "input_audio": audio, "language": "zh"}
    if words:
        full["response_format"] = "verbose_json"
        full["timestamp_granularities"] = ["word"]
    last = None
    for body in (full, {"model": model, "input_audio": audio}):       # 带可选参数被上游拒绝（400）就退回最小请求
        for i in range(3):
            try:
                r = requests.post(URL, headers=tts_mai.headers(key), data=json.dumps(body).encode("utf-8"), timeout=120)
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (i + 1))
                continue
            if r.status_code == 200:
                j = r.json()
                text = j.get("text", "")
                return (text, j.get("words") or None) if words else text
            last = RuntimeError("HTTP %s %s" % (r.status_code, r.text[:200]))
            if r.status_code == 400:
                break
            if r.status_code in (401, 402, 403, 404):
                raise last
            time.sleep(2 * (i + 1))
    raise RuntimeError("OpenRouter 识别失败: %s" % last)
