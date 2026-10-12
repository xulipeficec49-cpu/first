# -*- coding: utf-8 -*-
"""微软 MAI-Voice-2.1 配音后端（经 OpenRouter）。make_video.py 的 tts 阶段在 engine="mai" 时调用。

接口事实（OpenRouter 模型页 llms.txt，2026-10）：
  POST https://openrouter.ai/api/v1/audio/speech，model "microsoft/mai-voice-2.1"，
  voice 形如 "zh-CN-Mei:MAI-Voice-2.1"（中文还有 Bo / Lan / Wei / Grant / Harper），
  response_format 只有 "pcm"（默认）和 "mp3"；成功时返回裸音频字节（不是 JSON），不返回字级时间戳。

做法：逐句合成 + 自己控制句间停顿 + 按波形估字时刻。
- 为什么逐句：MAI-Voice 的 voice 参数固定说话人（不像 Gemini 每次请求"重新挑嗓音"，见 references/voice-lessons.md），
  逐句合成音色一致；每句音频的长度就是精确的句界，不需要再接语音识别对时（所以不要百炼 Key）。
- 句间停顿：按标点补到讲题节奏（句号 0.9 秒，同 tts_gemini.GAP），静音只补在句子之间，不会切进字音。
- 字时刻：一句里的字按"读音流"逐字给时刻（与 align.stream 一致，下游 align_times 对齐率恒为 100%）。
  句内的逗号停顿从波形里找（静音段对应到逗号），每段内按字权重均分；锚点动作的误差一般 ≤0.15 秒。
  想更准：以后可接 OpenRouter 的识别模型（verbose_json 词时间戳）替换 _char_times，接口不变。
- 缓存：每句合成结果存 ~/.cache/explain-video-pro/mai/，口播没改的句子不再花钱。
Key 由用户自己放（模型不经手，不进任何配置文件）：环境变量 OPENROUTER_API_KEY、~/.openrouter_api_key，
或云环境里的 Network secret（Bearer，允许站点 openrouter.ai，由出口代理注入 Authorization，容器里可以没有 Key）。
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import align as AL
import tts_gemini as TG
from tts_bailian import split_sentences

SR = 24000
URL = "https://openrouter.ai/api/v1/audio/speech"
CACHE_VERSION = 1
LEAD, TAIL = 0.15, 0.30                 # 场景开头/结尾留白（秒），同 tts_gemini._trim
KEEP_LEAD, KEEP_TAIL = 0.03, 0.08       # 每句修齐后保留的首尾静音（秒）
LETTER_W = 1.4                          # 读字母（诶 比 西…）比读汉字慢，按 1.4 个字的时长算
CPS_RANGE = (2.0, 8.0)                  # 合理语速（字/秒）；超出说明采样率猜错了


def load_key(cfg):
    """本地 Key：环境变量 OPENROUTER_API_KEY 或 ~/.openrouter_api_key。找不到就返回 ""（不退出）：
    云环境里若把 Key 配成"Network secret"（Bearer，允许站点 openrouter.ai），由出口代理给发往 openrouter.ai 的请求加 Authorization，
    容器里不一定有 Key（或只有占位符）——这时请求不带本地 Key 照样发，真没有 Key 会得到 401，报错里有提示"""
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        p = os.path.expanduser(cfg.get("openrouter_key_file", "~/.openrouter_api_key"))
        if os.path.exists(p):
            k = open(p, "rb").read().decode("utf-8-sig", "ignore").strip().strip('"').strip("'")
    return k


def headers(key):
    """请求头：有本地 Key 才带 Authorization（没有就交给 Network secret 代理注入）"""
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    return h


def _ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _resample(pcm, rate):
    """int16 单声道 PCM 从 rate 变到 24kHz"""
    if rate == SR:
        return pcm
    return subprocess.run([_ffmpeg(), "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "-",
                           "-f", "s16le", "-ar", str(SR), "-ac", "1", "-"], input=pcm, check=True, capture_output=True).stdout


def _decode(body, ctype, cfg):
    """响应体 -> 24kHz 单声道 int16 PCM。裸 PCM 的采样率取 Content-Type 的 rate=，没有就用 mai_pcm_rate（默认 24000）"""
    if body[:4] == b"RIFF":                                     # 带头的 wav
        with wave.open(io.BytesIO(body), "rb") as w:
            ch, rate, raw = w.getnchannels(), w.getframerate(), w.readframes(w.getnframes())
        if ch != 1:
            raw = subprocess.run([_ffmpeg(), "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", str(ch), "-i", "-",
                                  "-f", "s16le", "-ar", str(rate), "-ac", "1", "-"], input=raw, check=True, capture_output=True).stdout
        return _resample(raw, rate)
    if "mpeg" in ctype or "mp3" in ctype or body[:3] == b"ID3" or body[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return subprocess.run([_ffmpeg(), "-loglevel", "error", "-i", "-", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-"],
                              input=body, check=True, capture_output=True).stdout
    rate = int(cfg.get("mai_pcm_rate", SR))
    for part in ctype.replace(" ", "").split(";"):
        if part.lower().startswith("rate="):
            rate = int(part.split("=")[1])
    return _resample(body, rate)


def _request(text, cfg, key, log):
    """一句话 -> 24kHz 单声道 PCM 字节（网络请求；偶发 429/5xx 退避重试）"""
    body = {"model": cfg.get("mai_model", "microsoft/mai-voice-2.1"), "input": text,
            "voice": cfg.get("mai_voice", "zh-CN-Mei:MAI-Voice-2.1"), "response_format": cfg.get("mai_format", "pcm")}
    last = None
    for i in range(4):
        try:
            r = requests.post(URL, headers=headers(key), data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=300)
        except requests.RequestException as e:
            last = e
            log("   [MAI 重试 %d/4] %s" % (i + 1, str(e)[:80]))
            time.sleep(2 * (i + 1))
            continue
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and "json" not in ct:
            return _decode(r.content, ct, cfg)
        last = RuntimeError("HTTP %s %s" % (r.status_code, r.text[:200]))
        if r.status_code == 401:
            last = RuntimeError("HTTP 401：没有可用的 OpenRouter Key（环境变量 OPENROUTER_API_KEY / ~/.openrouter_api_key 都没有，"
                                "Network secret 也没生效？）或 Key 无效。%s" % r.text[:120])
        if r.status_code in (400, 401, 402, 403, 404):          # 请求本身的问题（Key、余额、音色名），重试没用
            break
        log("   [MAI 重试 %d/4] %s" % (i + 1, str(last)[:80]))
        time.sleep(2 * (i + 1))
    raise RuntimeError("MAI-Voice 配音失败: %s" % last)


def _prep(sentence, cfg):
    """送去合成的文本：大写字母连写（AOD、BC）拆成一个个字母读，避免被当英文单词；｜ 不发音"""
    s = sentence.replace("｜", "").strip()
    if cfg.get("mai_space_letters", True):
        s = re.sub(r"[A-Z]{2,}", lambda m: " ".join(m.group(0)), s)
    return s


def _cache_file(text, cfg):
    d = Path(os.path.expanduser(cfg.get("mai_cache", "~/.cache/explain-video-pro/mai")))
    d.mkdir(parents=True, exist_ok=True)
    k = hashlib.sha1(json.dumps([CACHE_VERSION, cfg.get("mai_model"), cfg.get("mai_voice"), cfg.get("mai_format", "pcm"), text],
                                ensure_ascii=False).encode("utf-8")).hexdigest()
    return d / (k + ".pcm")


def _get(text, cfg, key, log):
    f = _cache_file(text, cfg)
    if f.exists() and f.stat().st_size > 0:
        return f.read_bytes()
    pcm = _request(text, cfg, key, log)
    if len(pcm) < SR * 2 * 0.15:
        raise RuntimeError("MAI-Voice 返回的音频太短（%d 字节），文本：%s" % (len(pcm), text))
    f.write_bytes(pcm)
    return pcm


def _silence(sec):
    return b"\x00\x00" * int(round(sec * SR))


def _trim(pcm):
    """修齐一句的首尾静音，只留 KEEP_LEAD / KEEP_TAIL；返回 (pcm, 有声起点, 有声终点)（秒，相对修齐后的音频）"""
    import numpy as np
    db = TG.frame_db(pcm)
    loud = np.where(db > np.percentile(db, 95) - 35)[0] if len(db) else []
    if len(loud) == 0:
        return pcm, 0.0, len(pcm) / 2 / SR
    a = max(0.0, loud[0] * 0.01 - KEEP_LEAD)
    b = min(len(pcm) / 2 / SR, (loud[-1] + 1) * 0.01 + KEEP_TAIL)
    x = np.frombuffer(pcm[int(a * SR) * 2:int(b * SR) * 2], np.int16).astype(np.float32).copy()
    nf = min(len(x) // 4, int(0.004 * SR))
    if nf:
        x[:nf] *= np.linspace(0, 1, nf)
        x[-nf * 4:] *= np.linspace(1, 0, nf * 4)           # 尾部 16ms 淡出，收得干净
    return x.astype(np.int16).tobytes(), loud[0] * 0.01 - a, (loud[-1] + 1) * 0.01 - a


def _clause_streams(sentence):
    """一句 -> 各分句（逗号、顿号、冒号断开）的读音字列表；拼起来与 align.stream(整句) 一致"""
    parts = [p for p in re.split(r"(?<=[，、：])", sentence) if p.strip()]
    outs = [AL.stream(p)[0] for p in parts]
    return [o for o in outs if o]


def _char_times(pcm, v0, v1, clauses):
    """一句的读音字时刻（相对这句音频起点，秒）。
    句内的逗号停顿：从波形里找静音段（比本句说话音量低 30 dB 以上、≥90ms），按位置对应到各分句的分界；
    找不到的分界就按字数比例估计。每个分句内按字权重（字母 1.4、其余 1）均分有声时长。"""
    import numpy as np
    db = TG.frame_db(pcm)
    n = [len(c) for c in clauses]
    total = sum(n)
    # 分界处的期望位置（按字权重的累计比例）
    w = [sum(LETTER_W if "A" <= ch <= "Z" else 1.0 for ch in c) for c in clauses]
    cum = [sum(w[:k + 1]) / sum(w) for k in range(len(clauses) - 1)]
    gaps = []
    if len(db) and len(clauses) > 1:
        thr = np.percentile(db, 95) - 30
        i, lo_f, hi_f = 0, int((v0 + 0.08) / 0.01), int((v1 - 0.08) / 0.01)
        while i < min(len(db), hi_f):
            if i >= lo_f and db[i] < thr:
                j = i
                while j < len(db) and db[j] < thr:
                    j += 1
                if (j - i) * 0.01 >= 0.09 and j <= hi_f:
                    gaps.append((i * 0.01, j * 0.01))
                i = j
            else:
                i += 1
    # 静音段 -> 分界：按位置就近一一对应（容差：本句有声长度的 12%）
    bounds = [None] * (len(clauses) - 1)
    tol = 0.12 * (v1 - v0)
    for ga, gb in gaps:
        mid = (ga + gb) / 2
        k = min(range(len(cum)), key=lambda q: abs(v0 + cum[q] * (v1 - v0) - mid))
        if bounds[k] is None and abs(v0 + cum[k] * (v1 - v0) - mid) <= max(tol, 0.25):
            bounds[k] = (ga, gb)
    # 每个分句的 [起, 止]：中间静音之间；没找到静音的分界按比例切开（零长度）
    spans, start = [], v0
    for k in range(len(clauses)):
        if k < len(bounds):
            if bounds[k]:
                end, nxt = bounds[k][0], bounds[k][1]
            else:
                end = nxt = v0 + cum[k] * (v1 - v0)
        else:
            end, nxt = v1, v1
        spans.append((start, max(start + 0.05, end)))
        start = nxt
    out = []
    for c, (a, b) in zip(clauses, spans):
        ws = [LETTER_W if "A" <= ch <= "Z" else 1.0 for ch in c]
        tot, t = sum(ws), a
        for ch, x in zip(c, ws):
            d = (b - a) * x / tot
            out.append((ch, t, t + d))
            t += d
    return out


def synth_narration(text, cfg, log=print):
    """一个场景的口播 -> (pcm_bytes, words[{text, t, t_end}], 采样率)，接口同 tts_bailian / tts_gemini.synth_narration"""
    key = load_key(cfg)
    sents = split_sentences(text)                          # [(含句末标点的句子, 句末标记：标点或 ｜)]
    speak = [_prep(s, cfg) for s, _ in sents]
    uniq = list(dict.fromkeys(speak))
    got = {}
    with ThreadPoolExecutor(max_workers=int(cfg.get("mai_workers", 4))) as ex:
        for t, pcm in zip(uniq, ex.map(lambda x: _get(x, cfg, key, log), uniq)):
            got[t] = pcm
    out = bytearray(_silence(LEAD - KEEP_LEAD))
    words, slow = [], []
    for k, ((s, end), sp) in enumerate(zip(sents, speak)):
        pcm, v0, v1 = _trim(got[sp])
        t0 = len(out) / 2 / SR
        clauses = _clause_streams(s)
        for ch, a, b in _char_times(pcm, v0, v1, clauses):
            words.append({"text": ch, "t": round(t0 + a, 3), "t_end": round(t0 + b, 3)})
        n = sum(len(c) for c in clauses)
        cps = n / max(0.1, v1 - v0)
        if not CPS_RANGE[0] <= cps <= CPS_RANGE[1]:
            slow.append("「%s」%.1f 字/秒" % (s[:12], cps))
        out += pcm
        if k < len(sents) - 1:                             # 句间停顿补到讲题节奏（句号 0.9 秒；每个 ｜ 再多 1.05 秒）
            target = TG.GAP.get(s.rstrip()[-1:], 0.9) + (len(end) * TG.BAR if end and set(end) == {"｜"} else 0)
            out += _silence(max(0.2, target - KEEP_TAIL - KEEP_LEAD))
    out += _silence(TAIL - KEEP_TAIL)
    if slow:
        log("   [MAI] 语速异常（可能采样率不是 24kHz：在 meta.tts 里写 mai_pcm_rate，或 mai_format 改 mp3）：%s" % "；".join(slow[:4]))
    log("   MAI %s: %d 句 -> %.1fs" % (cfg.get("mai_voice", "zh-CN-Mei:MAI-Voice-2.1").split(":")[0], len(sents), len(out) / 2 / SR))
    return bytes(out), words, SR
