# -*- coding: utf-8 -*-
"""阿里百炼 CosyVoice 配音后端（build_video.py 的 tts 阶段调用）

接法（mode=ssml，默认）：整个环节一次合成，句间停顿写成 SSML <break>，由引擎在同一段语流里渲染，
语调有上下文、停顿是自然收尾起音；字级时间戳照常返回。回退（mode=sentence）：逐句合成 + 句间插静音。
停顿必须显式给：真人成片静音占比约 40%，整段直合只有 14%（2026-09-14 实测）；
break 表 0.6/0.7 秒加引擎自带停顿后平均约 1 秒，与真人 0.95 秒对齐（2026-09-15 试听拍板）。

配置来自 scripts/tts_config.json（默认）与分镜 meta.tts（覆盖）：
  engine / model / voice(voice_id 或系统音色) / rate / mode / break{标点: 秒} / pause{标点: 秒} / workspace / key_file
API Key 只从环境变量 DASHSCOPE_API_KEY 或 key_file（默认 ~/.dashscope_api_key）读取，不进任何配置文件。
"""
import json
import os
import re
import sys
import threading
import time
import wave

SR = 24000
# 默认模式 ssml：整段一次合成，句间停顿用 SSML <break> 交给引擎渲染（2026-09-15 试听拍板 D2 方案：
# 语调有上下文、停顿是引擎自然收尾起音；break 取值加上引擎自带停顿后平均约 1 秒，对齐真人成片）
DEFAULT_BREAK = {"。": 0.6, "；": 0.6, "？": 0.7, "！": 0.65, "｜": 1.05}
# 回退模式 sentence：逐句合成 + 句间插静音（SSML 不可用时自动回退）
DEFAULT_PAUSE = {"。": 0.9, "；": 0.9, "？": 1.1, "！": 1.0, "｜": 1.6}
PAUSE_MARK = "｜"                    # 口播里的显式长停顿标记(全角竖线)，不发音
PRICE = {"qwen-audio-3.0-tts-plus": 1.4, "qwen-audio-3.0-tts-flash": 1.0,
         "cosyvoice-v3.5-plus": 1.5, "cosyvoice-v3.5-flash": 0.8,
         "cosyvoice-v3-plus": 2.0, "cosyvoice-v3-flash": 1.0}      # 元/万字符, 汉字计 2 字符


def load_key(cfg):
    k = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    key_file = cfg.get("key_file", "~/.dashscope_api_key")
    if not k:
        p = os.path.expanduser(key_file)
        if os.path.exists(p):
            raw = open(p, "rb").read()
            if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                k = raw.decode("utf-16")
            else:
                k = raw.decode("utf-8-sig", "ignore")
            k = k.strip().strip('"').strip("'").strip("<>").strip()
    if not k:
        sys.exit("百炼配音需要 API Key：设置环境变量 DASHSCOPE_API_KEY，或把 Key 写入 %s。"
                 "离线想临时改用 edge-tts：设环境变量 PM_TTS_ENGINE=edge" % key_file)
    return k


def split_sentences(text):
    """按句末标点切句 -> [(句子文本, 句末字符)]。｜ 单独出现或跟在句尾时，
    把这一处停顿改成 PAUSE['｜']，标记本身不送 TTS。"""
    parts = [p.strip() for p in re.split("(?<=[。！？；｜])", text) if p.strip()]
    out = []
    for p in parts:
        if p == PAUSE_MARK:
            if out:       # 连写几个 ｜ 就停几倍(练一练"先自己算一算"这类要几秒思考时间: ｜｜｜｜ ≈ 4 秒)
                out[-1][1] = (out[-1][1] + PAUSE_MARK) if set(out[-1][1]) == {PAUSE_MARK} else PAUSE_MARK
            continue
        end = p[-1]
        if end == PAUSE_MARK:
            p = p[:-1].rstrip()
            if not p:
                continue
        out.append([p, end])
    return [(p, e) for p, e in out]


def pause_sec(end, table):
    """句末标记 -> 停顿秒数; 连写 k 个 ｜ = k 倍 ｜ 的停顿"""
    if end and set(end) == {PAUSE_MARK}:
        return len(end) * table.get(PAUSE_MARK, 1.05)
    return table.get(end, table.get("。", 0.6))


def write_wav(path, pcm, sr=SR):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)


class _Collector:
    """dashscope ResultCallback：收 PCM 分片与 sentence 事件里的字级时间戳"""

    def __init__(self):
        self.pcm = bytearray()
        self.sent = {}
        self.err = None
        self.done = threading.Event()

    def on_open(self):
        pass

    def on_data(self, data):
        self.pcm.extend(data)

    def on_event(self, message):
        try:
            j = json.loads(message) if isinstance(message, str) else message
        except Exception:
            return
        out = (j.get("payload") or {}).get("output") or {}
        s = out.get("sentence") or {}
        if s.get("words"):
            self.sent[s.get("index", len(self.sent))] = s["words"]

    def on_error(self, message):
        self.err = str(message)
        self.done.set()

    def on_complete(self):
        self.done.set()

    def on_close(self):
        self.done.set()

    def words(self):
        ws = []
        for k in sorted(self.sent):
            ws.extend(self.sent[k])
        return ws


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


MAX_SSML_CHARS = 600     # 实测: 单次请求 SSML 超过约 750 字符后字级时间戳被截断(音频不缺), 故按句分块


def chunk_sentences(sents, limit=MAX_SSML_CHARS):
    """按句切成若干块, 每块 SSML(含 break 标签约 24 字符/句)不超过 limit"""
    chunks, cur, n = [], [], 0
    for s, end in sents:
        add = len(s) + 24
        if cur and n + add > limit:
            chunks.append(cur)
            cur, n = [], 0
        cur.append((s, end))
        n += add
    if cur:
        chunks.append(cur)
    return chunks


def build_ssml(text, brk, sents=None):
    """口播 -> <speak>句1<break time="600ms"/>句2...</speak>；末句后不加 break（渲染端 TAIL 接管）"""
    sents = sents if sents is not None else split_sentences(text)
    parts = []
    for i, (s, end) in enumerate(sents):
        parts.append(_xml_escape(s))
        if i < len(sents) - 1:
            ms = int(round(pause_sec(end, brk) * 1000))
            parts.append('<break time="%dms"/>' % max(50, min(10000, ms)))
    return "<speak>" + "".join(parts) + "</speak>"


def _synth_once(model, voice, text, rate, workspace, instruction, ssml=False):
    from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback, AudioFormat

    class CB(ResultCallback):
        def __init__(self, c):
            self.c = c

        def on_open(self):
            self.c.on_open()

        def on_data(self, data):
            self.c.on_data(data)

        def on_event(self, message):
            self.c.on_event(message)

        def on_error(self, message):
            self.c.on_error(message)

        def on_complete(self):
            self.c.on_complete()

        def on_close(self):
            self.c.on_close()

    c = _Collector()
    params = {"word_timestamp_enabled": True}
    if ssml:
        params["enable_ssml"] = True
    syn = SpeechSynthesizer(model=model, voice=voice, format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                            speech_rate=rate, instruction=instruction, callback=CB(c),
                            workspace=workspace, additional_params=params)
    if ssml:                       # SSML 只支持非流式/单向流式
        syn.call(text, timeout_millis=180000)
    else:
        syn.streaming_call(text)
        syn.streaming_complete(complete_timeout_millis=180000)
    c.done.wait(timeout=30)
    if c.err:
        raise RuntimeError("百炼合成失败: %s (request_id=%s)" % (c.err[:300], syn.get_last_request_id()))
    return bytes(c.pcm), c.words()


def _synth_retry(model, voice, text, rate, workspace, instruction, log, retries=3, ssml=False):
    """websocket 建连偶发 5 秒超时（网络/代理抖动；SDK 把握手失败也报成超时），自动重试"""
    last = None
    for i in range(retries):
        try:
            return _synth_once(model, voice, text, rate, workspace, instruction, ssml)
        except (TimeoutError, ConnectionError, OSError) as e:
            last = e
            log("   [百炼重试 %d/%d] %s" % (i + 1, retries, str(e)[:80]))
            time.sleep(2 * (i + 1))
    raise RuntimeError("百炼连接多次失败: %s" % last)


def synth_narration(text, cfg, log=print):
    """一个环节的口播 -> (pcm_bytes, words[{text, t秒}], 采样率)。
    words 的 t 是整段音频内的绝对时刻，格式与 edge-tts 路径一致，渲染端锚点逻辑不变。
    注意引擎会把数字按读法返回（240 -> 二百四十），锚点词本就只许汉字，不受影响。"""
    import dashscope
    dashscope.api_key = load_key(cfg)
    model = cfg.get("model", "cosyvoice-v3.5-plus")
    voice = cfg["voice"]
    rate = float(cfg.get("rate", 1.0))
    if cfg.get("mode", "ssml") == "ssml":
        brk = dict(DEFAULT_BREAK)
        brk.update(cfg.get("break") or {})
        sents = split_sentences(text)
        chunks = chunk_sentences(sents)
        try:
            pcm, words, t = bytearray(), [], 0.0
            for ci, ch in enumerate(chunks):
                audio, ws = _synth_retry(model, voice, build_ssml(text, brk, ch), rate,
                                         cfg.get("workspace"), cfg.get("instruction"), log, ssml=True)
                for w in ws:
                    words.append({"text": w.get("text", ""),
                                  "t": round(t + float(w.get("begin_time", 0)) / 1000.0, 3)})
                pcm += audio
                t += len(audio) / (SR * 2)
                if ci < len(chunks) - 1:          # 块间补上这一句该有的停顿(+引擎自带约 0.35s)
                    gap = pause_sec(ch[-1][1], brk) + 0.35
                    pcm += bytes(int(SR * gap) * 2)
                    t += gap
            chars = len(text.replace(PAUSE_MARK, ""))
            covered = len([c for w in words for c in w["text"] if "一" <= c <= "鿿"])
            log("   百炼 %s [ssml]: %d 句/%d 块 %d 字 -> %.1fs, 词界覆盖 %d 汉字, 约 %.2f 元" % (
                model, len(sents), len(chunks), chars, t, covered, chars * 2 / 1e4 * PRICE.get(model, 2.0)))
            return bytes(pcm), words, SR
        except Exception as e:
            log("   [百炼] SSML 模式失败(%s), 回退逐句模式" % str(e)[:100])
    pause = dict(DEFAULT_PAUSE)
    pause.update(cfg.get("pause") or {})
    sents = split_sentences(text)
    pcm = bytearray()
    words = []
    t = 0.0
    chars = 0
    for i, (sent, end) in enumerate(sents):
        audio, ws = _synth_retry(model, voice, sent, rate, cfg.get("workspace"), cfg.get("instruction"), log)
        for w in ws:
            words.append({"text": w.get("text", ""),
                          "t": round(t + float(w.get("begin_time", 0)) / 1000.0, 3)})
        pcm += audio
        t += len(audio) / (SR * 2)
        chars += len(sent)
        if i < len(sents) - 1:            # 末句不补停顿，由渲染端 TAIL/LEAD 接管
            p = pause_sec(end, pause)
            pcm += bytes(int(SR * p) * 2)
            t += p
    log("   百炼 %s: %d 句 %d 字 -> %.1fs, 约 %.2f 元" % (
        model, len(sents), chars, t, chars * 2 / 1e4 * PRICE.get(model, 2.0)))
    return bytes(pcm), words, SR
