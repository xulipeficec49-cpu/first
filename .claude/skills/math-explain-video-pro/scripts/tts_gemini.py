# -*- coding: utf-8 -*-
"""Gemini 3.8 Flash TTS 配音后端（经 OpenRouter）+ 百炼语音识别对时（make_video.py 的 tts 阶段调用）

- 合成：一个场景的口播整段一次合成（语调有上下文），OpenRouter `POST /api/v1/audio/speech`，
  Gemini 在 OpenRouter 上只接受 response_format="pcm"（24kHz 单声道 16bit）；`instructions` 传讲课风格提示。
- 对时：Gemini 不返回字级时间戳 → 用百炼 paraformer-realtime-v2 把配音识别回来拿词级时间戳，
  输出与百炼后端同格式的 words [{text, t, t_end}]，下游 align.py 照常对齐锚点。
- 节奏：Gemini 句间只停 0.5~0.7 秒，讲题偏赶 → 按句末标点把句间停顿补到 GAP（句中原有的换气不动）；
  口播里的全角 ｜ 每个再多停 BAR 秒。
- 兜底：识别回来和口播对不齐（漏读、读错）就重新合成，最多 3 次，取对齐率最高的一版。
2026-09-28 用户 A/B 试听后选定 Erinome + 讲课风格提示（试听页：视频讲解 新版（pro）\\配音试听）。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

SR = 24000
URL = "https://openrouter.ai/api/v1/audio/speech"
GAP = {"。": 0.9, "；": 0.9, "？": 1.05, "！": 0.95}    # 句末标点 -> 句间停顿下限（秒）
BAR = 1.05                                           # 每个 ｜ 再多停的秒数
MIN_RATE = 0.92                                      # 识别对齐率低于此值视为漏读/错读，重合成


def load_key(cfg):
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        p = os.path.expanduser(cfg.get("openrouter_key_file", "~/.openrouter_api_key"))
        if os.path.exists(p):
            k = open(p, "rb").read().decode("utf-8-sig", "ignore").strip().strip('"').strip("'")
    if not k:
        sys.exit("Gemini 配音需要 OpenRouter Key：设置环境变量 OPENROUTER_API_KEY，或写入 ~/.openrouter_api_key（由用户自己写入）")
    return k


def _speak(text, cfg, key, log):
    body = {"model": cfg.get("gemini_model", "google/gemini-3.8-flash-tts"), "input": text,
            "voice": cfg.get("gemini_voice", "Erinome"), "response_format": "pcm"}
    if cfg.get("gemini_style"):
        body["instructions"] = cfg["gemini_style"]
    last = None
    for i in range(3):
        try:
            r = requests.post(URL, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                              data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=900)
        except requests.RequestException as e:
            last = e
            log("   [Gemini 重试 %d/3] %s" % (i + 1, str(e)[:80]))
            time.sleep(3 * (i + 1))
            continue
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and "json" not in ct:
            rate = SR
            for part in ct.replace(" ", "").split(";"):
                if part.lower().startswith("rate="):
                    rate = int(part.split("=")[1])
            if rate != SR:
                raise RuntimeError("Gemini 返回采样率 %d，预期 %d" % (rate, SR))
            return r.content
        last = RuntimeError("HTTP %s %s" % (r.status_code, r.text[:200]))
        # OpenRouter 偶发 "Provider returned 400" 是上游临时错误，重试即可（白板专题课项目踩过）；其余 4xx 是请求本身错，不重试
        if r.status_code in (400, 401, 402, 403) and "Provider returned" not in r.text:
            break
        log("   [Gemini 重试 %d/3] %s" % (i + 1, str(last)[:80]))
        time.sleep(3 * (i + 1))
    raise RuntimeError("Gemini 配音失败: %s" % last)


def _asr_words(pcm, cfg):
    """百炼 paraformer-realtime-v2 识别 -> [{text, t, t_end}]（秒）"""
    import dashscope
    import imageio_ffmpeg
    from dashscope.audio.asr import Recognition
    import tts_bailian
    dashscope.api_key = tts_bailian.load_key(cfg)
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1",
                        "-i", "-", "-ar", "16000", "-ac", "1", tmp], input=pcm, check=True)
        for i in range(4):                     # 建连偶发失败（网络抖动），退避重试
            res = Recognition(model="paraformer-realtime-v2", format="wav", sample_rate=16000, callback=None,
                              language_hints=["zh", "en"]).call(tmp)
            if getattr(res, "status_code", 200) == 200:
                break
            time.sleep(3 * (i + 1))
    finally:
        os.remove(tmp)
    if getattr(res, "status_code", 200) != 200:
        raise RuntimeError("百炼识别失败: %s" % getattr(res, "message", res))
    words = []
    for s in (res.get_sentence() or []):
        for w in (s.get("words") or []):
            words.append({"text": w.get("text", ""), "t": w.get("begin_time", 0) / 1000.0,
                          "t_end": w.get("end_time", 0) / 1000.0})
    return words


def frame_db(pcm, hop=0.01):
    """PCM -> 每 10ms 一帧的能量（dB，相对满幅）"""
    import numpy as np
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    n = int(hop * SR)
    m = len(x) // n
    if m == 0:
        return np.zeros(0)
    fr = x[:m * n].reshape(m, n)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)


def quiet_point(db, t_lo, t_hi, hop=0.01, min_run=0.04, strict=True):
    """在 [t_lo, t_hi] 里找真正没声音的地方下刀：最长一段低能量帧的中点。
    低能量 = 比本段说话音量（能量 95 分位）低 32 dB 以上。插静音只在这种点插，不会切进字音。
    strict=True（可插可不插，如句间补停顿）：没有静音段返回 None；
    strict=False（非插不可，如等动画）：没有静音段就往两边各放宽 0.3 秒再找，还没有就取 30ms 平滑后能量最低处（字与字之间的气口）。"""
    import numpy as np
    if len(db) == 0:
        return None
    ref = np.percentile(db, 95)
    a, b = max(0, int(t_lo / hop)), min(len(db), int(t_hi / hop) + 1)
    if b - a < 2:
        return None if strict else t_lo
    if not strict:
        p = quiet_point(db, t_lo, t_hi, hop, min_run, True)
        if p is None:
            p = quiet_point(db, max(0.0, t_lo - 0.3), t_hi + 0.3, hop, min_run, True)
        if p is not None:
            return p
        sm = np.convolve(db[a:b], np.ones(3) / 3, mode="same")
        return (a + int(np.argmin(sm))) * hop + hop / 2
    quiet = db[a:b] < ref - 32
    best, run_s, best_len = None, None, 0
    for i, q in enumerate(list(quiet) + [False]):
        if q and run_s is None:
            run_s = i
        elif not q and run_s is not None:
            if i - run_s > best_len:
                best_len, best = i - run_s, (run_s + i) / 2
            run_s = None
    if best is None or best_len * hop < min_run:
        return None
    return (a + best) * hop


def quiet_run(db, at, hop=0.01):
    """at 所在那段静音的起止（秒）；at 不在静音里就返回 (at, at)"""
    import numpy as np
    if len(db) == 0:
        return at, at
    thr = np.percentile(db, 95) - 32
    i = int(at / hop)
    if i >= len(db) or db[i] >= thr:
        return at, at
    lo, hi = i, i
    while lo > 0 and db[lo - 1] < thr:
        lo -= 1
    while hi < len(db) - 1 and db[hi + 1] < thr:
        hi += 1
    return lo * hop, (hi + 1) * hop


def tagged_text(sents):
    """送 Gemini 的文本：每句后加 <short pause>（2026-09-28 实测：句间自然停 1.0~1.6 秒，明显长于句中换气；
    不加标记时句间只停 0.2~0.5 秒，和"所以……"这类句中顿挫分不清，补停顿会插错地方）。连写两个以上 ｜ 用 <long pause>（约 3 秒）。"""
    out = []
    for i, (s, end) in enumerate(sents):
        tag = "<long pause>" if (end and set(end) == {"｜"} and len(end) >= 2) else "<short pause>"
        out.append(s + (" %s " % tag if i < len(sents) - 1 or end == "｜" else ""))
    return "".join(out)


def insert_silences(pcm, inserts, fade=0.005):
    """在若干时刻插静音（inserts: [(秒, 时长)]，须已落在静音点上）；切口两侧各做 5ms 淡出淡入防爆音"""
    import numpy as np
    x = np.frombuffer(pcm, np.int16).astype(np.float32)
    nf = int(fade * SR)
    out, prev = [], 0
    for at, g in sorted(inserts):
        i = min(len(x), int(at * SR))
        seg = x[prev:i].copy()
        if len(seg) > nf:
            seg[-nf:] *= np.linspace(1, 0, nf)
        out.append(seg)
        out.append(np.zeros(int(g * SR), np.float32))
        prev = i
        if prev + nf < len(x):
            x = x.copy()
            x[prev:prev + nf] *= np.linspace(0, 1, nf)
    out.append(x[prev:])
    return np.clip(np.concatenate(out), -32768, 32767).astype(np.int16).tobytes()


def apply_edits(pcm, edits, fade=0.005):
    """edits: [(秒, 增量)]，增量>0 在该处插静音，增量<0 以该处为中心删掉这么长的静音（只用于静音段中间）；切口 5ms 淡出淡入"""
    import numpy as np
    x = np.frombuffer(pcm, np.int16).astype(np.float32).copy()
    nf = int(fade * SR)
    out, prev = [], 0
    for at, d in sorted(edits):
        if d >= 0:
            i, j = min(len(x), int(at * SR)), min(len(x), int(at * SR))
        else:
            i = max(prev, int((at + d / 2) * SR))
            j = min(len(x), int((at - d / 2) * SR))
        seg = x[prev:i].copy()
        if len(seg) > nf:
            seg[-nf:] *= np.linspace(1, 0, nf)
        out.append(seg)
        if d > 0:
            out.append(np.zeros(int(d * SR), np.float32))
        prev = j
        if prev + nf < len(x):
            x[prev:prev + nf] *= np.linspace(0, 1, nf)
    out.append(x[prev:])
    return np.clip(np.concatenate(out), -32768, 32767).astype(np.int16).tobytes()


GAP_MAX_EXTRA = 0.25     # 模型自己停得比目标长超过这么多（且没有动画要等）就删掉多余的静音，节奏更匀


def _pad_sentences(pcm, sents, offs, stream_len, times, words, log):
    """句间停顿调到讲题节奏：不够的补（插静音），太长的删（删静音段中间）；只动两句之间真正的静音，
    找不到静音（模型连读）就不动。等动画要多停的时间由 make_video 另外插。"""
    db = frame_db(pcm)
    inserts = []
    for k in range(len(sents) - 1):
        a, b = offs[k + 1] - 1, offs[k + 1]
        if a < offs[k] or b >= stream_len:
            continue
        s, end = sents[k]
        # 识别时间戳在停顿附近可能差出半秒，窗口放宽，取窗口里最长的静音（有 <short pause> 后句间停顿总是最长的）
        at = quiet_point(db, times[a] - 0.3, times[b] + 0.4)
        if at is None:
            continue
        lo, hi = quiet_run(db, at)
        have = hi - lo                 # 这里原本已停了多久（模型自己停的）
        target = GAP.get(s.rstrip()[-1:], 0.9) + (len(end) * BAR if end and set(end) == {"｜"} else 0)
        if have < target:
            inserts.append((at, target - have))
        elif have > target + GAP_MAX_EXTRA + 0.05:
            inserts.append(((lo + hi) / 2, -(have - target - GAP_MAX_EXTRA)))
    out = apply_edits(pcm, inserts)

    def shift(t):
        d = 0.0
        for at, g in inserts:
            if g > 0 and at <= t:                  # 插在它前面的静音
                d += g
            elif g < 0 and at - g / 2 <= t + 1e-6:  # 删掉的静音段整个在它前面
                d += g
        return d
    for w in words:
        d = shift(w["t"])
        w["t"] = round(max(0.0, w["t"] + d), 3)
        if "t_end" in w:
            w["t_end"] = round(max(0.0, w["t_end"] + d), 3)
    return out, words, inserts


def synth_film(texts, cfg, log=print, raw_dir=None, raw_key=None):
    """整片所有场景的口播一次合成（保证全片同一个音色），再按场景之间的真实静音切开。
    texts: 各场景口播 -> [(pcm, words, 采样率)]，每个场景一份，接口同 synth_narration。
    raw_dir/raw_key：选中的那遍原始合成（未切未调停顿）+ 识别结果存下来；口播没变时只重做后期（调停顿等），不再花钱重合成。"""
    import align as AL
    from tts_bailian import split_sentences
    key = load_key(cfg)
    scenes = []                     # 每场景：sents, 读音流起点
    stream, clean = [], ""
    for text in texts:
        sents = split_sentences(text)
        offs = []
        for s, _ in sents:
            offs.append(len(stream))
            stream += AL.stream(s)[0]
        scenes.append({"sents": sents, "offs": offs, "s0": offs[0] if offs else len(stream), "s1": len(stream)})
        clean += tagged_text(sents) + (" <short pause> " if not tagged_text(sents).endswith("> ") else "")
    # 第一遍没有明显问题就直接用（用户 9-28："三遍太奢侈了"）；有明显问题才再合成，gemini_takes 是封顶遍数。
    # 多遍时挑明显问题最少、再比可疑处最少、再比最差场景对齐率的一遍
    takes = int(cfg.get("gemini_takes", 3))
    best = None
    raw_wav = Path(raw_dir) / "_raw.pcm" if raw_dir else None
    raw_meta = Path(raw_dir) / "_raw.json" if raw_dir else None
    if raw_wav and raw_wav.exists() and raw_meta.exists() and json.loads(raw_meta.read_text(encoding="utf-8")).get("key") == raw_key:
        meta = json.loads(raw_meta.read_text(encoding="utf-8"))
        pcm, words = raw_wav.read_bytes(), meta["words"]
        times, _ = AL.align_times(stream, words)
        best = (pcm, words, times, 1.0, (meta.get("suspicious", 0), -1.0))
        log("   用已存的原始合成（口播未变，只重做后期）")
        takes = 0
    for attempt in range(takes):
        pcm = _speak(clean, cfg, key, log)
        words = _asr_words(pcm, cfg)
        times, rate = AL.align_times(stream, words)
        rates = [_scene_rate(stream, words, sc) for sc in scenes]
        worst = min(rates)
        if worst < 0.9:            # 对齐率低的场景：打出来是哪一个、差在哪，别让人猜（9-30 函数压轴题）
            k = rates.index(worst)
            sc = scenes[k]
            act, _ = AL.word_stream(words)
            import difflib as _dl
            diffs = []
            for tag, i1, i2, j1, j2 in _dl.SequenceMatcher(None, AL.canon(stream), AL.canon(act), autojunk=False).get_opcodes():
                if tag != "equal" and i2 > sc["s0"] and i1 < sc["s1"]:
                    diffs.append("「%s」→「%s」" % ("".join(stream[i1:i2]), "".join(act[j1:j2])))
            log("   [对齐] 场景 %d 对齐率 %.0f%%：%s" % (k + 1, worst * 100, "；".join(diffs[:12])))
        sus = suspicious(stream, words)
        num_bad, num_ok = number_slips(pcm, stream, sus, times, cfg, log)
        sus = [x for x in sus if x not in num_ok]            # 第二个识别核实是识别听错的，不算可疑
        bad = obvious_problems(stream, sus, worst, num_bad)
        jump, jt = voice_jump(pcm, [times[o] for sc in scenes for o in sc["offs"]] + [times[-1] + 0.3])
        if abs(jump) > VOICE_JUMP:
            bad.append("音色突变：前后各 3 句的中位音高差 %.1f 个半音（%d:%02d 附近）" % (jump, int(jt // 60), int(jt % 60)))
        log("   Gemini %s 整片第 %d 遍：%d 场景 %d 字 -> %.1fs，对齐 %.0f%%（最差场景 %.0f%%），可疑 %d 处%s" % (
            cfg.get("gemini_voice", "Erinome"), attempt + 1, len(texts), len(clean), len(pcm) / 2 / SR, rate * 100,
            worst * 100, len(sus), ("：" + "；".join("「%s」→「%s」" % (e, a) for _, e, a in sus)) if sus else ""))
        score = (len(bad), len(sus), -worst)
        if best is None or score < best[4]:
            best = (pcm, words, times, worst, score)
        if not bad:
            log("   没有明显问题，直接用这一遍")
            break
        log("   明显问题：%s%s" % ("；".join(bad), "，再合成一遍" if attempt + 1 < takes else "，已到封顶遍数，用问题最少的一遍"))
    pcm, words, times, _, score = best
    if takes:
        if raw_wav:
            raw_wav.write_bytes(pcm)
            raw_meta.write_text(json.dumps({"key": raw_key, "words": words, "suspicious": score[1] if len(score) > 2 else score[0]},
                                           ensure_ascii=False), encoding="utf-8")
    words = [dict(w) for w in words]
    db = frame_db(pcm)
    # 场景切点：上一场景末字与下一场景首字之间最长静音段的中点
    cuts = [0.0]
    for k in range(len(scenes) - 1):
        lo, hi = times[scenes[k]["s1"] - 1] - 0.3, times[scenes[k + 1]["s0"]] + 0.4
        at = quiet_point(db, lo, hi)
        if at is None:
            at = (times[scenes[k]["s1"] - 1] + times[scenes[k + 1]["s0"]]) / 2 + 0.12
            log("   [Gemini] 场景 %d/%d 之间没找到静音，按时间戳中点切" % (k + 1, k + 2))
        cuts.append(at)
    cuts.append(len(pcm) / 2 / SR)
    out = []
    for k, sc in enumerate(scenes):
        a, b = cuts[k], cuts[k + 1]
        seg = pcm[int(a * SR) * 2:int(b * SR) * 2]
        ws = [dict(w, t=round(w["t"] - a, 3), **({"t_end": round(w["t_end"] - a, 3)} if "t_end" in w else {}))
              for w in words if a <= w["t"] < b]
        loc = [t - a for t in times[sc["s0"]:sc["s1"]]]
        offs = [o - sc["s0"] for o in sc["offs"]]
        seg, ws, ins = _pad_sentences(seg, sc["sents"], offs, sc["s1"] - sc["s0"], loc, ws, log)
        # 首尾静音修齐：开头留 0.15 秒、结尾留 0.3 秒
        seg, ws = _trim(seg, ws, lead=0.15, tail=0.3)
        out.append((seg, ws, SR))
        log("   场景 %d：%.1fs，句间停顿调整 %d 处（补 %d、删 %d）" % (k + 1, len(seg) / 2 / SR, len(ins),
                                                          sum(1 for _, g in ins if g > 0), sum(1 for _, g in ins if g < 0)))
    return out


NUMS = set("零〇一二两三四五六七八九十百千万")
# 音色突变判定线（半音）：前后各 3 句的中位音高之差。2026-09-30 标定：已交付的几片最大 3.0~3.6，
# 赵爽弦图那遍 5.4（前两分半慢慢压低到 165Hz，换场景一下子跳回 210~239Hz、明亮度 +16%，就是用户说过的"突然两段音色有差别"）
VOICE_JUMP = 4.5


def voice_jump(pcm, starts):
    """整片合成里一句一句量中位音高（starts：各句开始时刻，最后一个是结尾），返回 (最大台阶 半音, 所在时刻)。
    同一遍合成里模型也会慢慢跑调、再突然跳回去（9-30 实测），分段请求那种换人更不用说"""
    import numpy as np
    import parselmouth
    x = np.frombuffer(pcm, np.int16).astype(np.float64) / 32768
    p = parselmouth.Sound(x, sampling_frequency=SR).to_pitch(time_step=0.01, pitch_floor=90, pitch_ceiling=400)
    f0, ts = p.selected_array["frequency"], p.xs()
    meds, t0s = [], []
    for a, b in zip(starts[:-1], starts[1:]):
        v = f0[(ts >= a) & (ts < b) & (f0 > 0)]
        if len(v) >= 30:
            meds.append(12 * np.log2(np.median(v) / 100))
            t0s.append(a)
    best = (0.0, 0.0)
    for i in range(3, len(meds) - 2):
        d = float(np.median(meds[i:i + 3]) - np.median(meds[i - 3:i]))
        if abs(d) > abs(best[0]):
            best = (d, t0s[i])
    return best


def _has_num(s):
    return any(c in NUMS or c.isdigit() for c in s)


def _asr2(pcm, cfg):
    """第二个识别模型（百炼 qwen3-asr-flash，不做数字归一化）听一小段，返回文字"""
    import dashscope
    import wave
    from dashscope import MultiModalConversation
    import tts_bailian
    dashscope.api_key = tts_bailian.load_key(cfg)
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)
        for k in range(4):                           # 9-29：百炼上传偶尔 SSL 断开（UNEXPECTED_EOF），歇一下重试
            try:
                r = MultiModalConversation.call(model="qwen3-asr-flash", asr_options={"enable_itn": False},
                                                messages=[{"role": "user", "content": [{"audio": "file://" + tmp.replace("\\", "/")}]}])
                return r.output.choices[0].message.content[0]["text"]
            except Exception:
                if k == 3:
                    raise
                time.sleep(2 + 2 * k)
    finally:
        os.remove(tmp)


def _sound_seq(s):
    """文字 -> 读音序列（不带声调的拼音；数字转读法；字母 R 念"er"，与 二/儿/尔 同；其余字母保留原样），复核比对用。
    9-30 电阻网络题：第二个识别把"R零"写成"二零"/"R0"、"代进"写成"带进"，按字比对全算没听到原文，被当成"数字念错"。"""
    import re
    import align as AL
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        lazy_pinyin = None
    s = re.sub(r"\d+(?:\.\d+)?", lambda m: AL.num_cn(m.group(0)), s)
    s = s.replace("″", "两撇").replace("''", "两撇").replace("′", "撇").replace("'", "撇")     # R′ 念"R撇"，识别写 R'
    toks, cn = [], []
    for c in s:
        if "一" <= c <= "鿿":
            toks.append(None)
            cn.append("二" if c == "两" else c)
        elif c.isascii() and c.isalpha():
            toks.append("er" if c.upper() == "R" else c.upper())
    pys = iter(lazy_pinyin("".join(cn)) if lazy_pinyin else cn)
    return [t if t is not None else next(pys) for t in toks]


def number_slips(pcm, stream, sus, times, cfg, log):
    """每处可疑切出前后一小段，让第二个识别模型再听一遍。第二个模型听到的逐字就是原文 → 第一个识别听错，放过；
    没听到原文：涉及数字的算真念错（9-28 盈亏问题："7减3，等于4个"真被读成了"7减4"，只算 1 处零碎可疑，差点就用了），
    不涉及数字的仍算可疑。9-29 物理课以前只复核数字：第一个识别把"浸入""浸没""乘g"听成"侵入""寂寞""呈质"，
    三遍都凑够"零碎可疑 5 处"，白白多合成两遍（第二个识别一听全是原文）。返回 (数字念错的, 核实是识别听错的)。"""
    bad, ok = [], []
    norm = _sound_seq
    for item in sus:
        i1, e, a = item
        numeric = _has_num(e) or _has_num(a)
        lo, hi = max(0, i1 - 1), min(len(stream), i1 + max(1, len(e)) + 1)
        want = "".join(stream[lo:hi])
        t0 = max(0.0, times[max(0, i1 - 6)] - 0.4)
        t1 = times[min(len(times) - 1, i1 + max(1, len(e)) + 6)] + 0.6
        try:
            heard = _asr2(pcm[int(t0 * SR) * 2:int(t1 * SR) * 2], cfg)
        except Exception as ex:                       # 复核不了就当真念错（宁可多合成一遍，不能把念错的数交出去）
            heard = "（复核失败：%s）" % str(ex)[:60]
        w_, h_ = norm(want), norm(heard)
        if w_ and any(h_[k:k + len(w_)] == w_ for k in range(len(h_) - len(w_) + 1)):
            ok.append(item)
            log("   [复核] 「%s」第二个识别听到原文（%s），是识别听错" % (want, heard))
        elif numeric:
            bad.append((i1, e, a, want, heard))
            log("   [复核] 数字念错：原文「%s」，第二个识别听到「%s」" % (want, heard))
        else:
            log("   [复核] 「%s」第二个识别听到「%s」，仍算可疑" % (want, heard))
    return bad, ok


def obvious_problems(stream, sus, worst, num_bad=()):
    """明显问题（有才再合成）：① 某个场景对齐率 < 90%（大段漏读、读乱）；② 口播中间连续 ≥4 个字的多读、漏读、读错
    （自己加话、跳句）；③ 零碎可疑处（单字、两字）累计 ≥5 处；④ 数字念错（两个识别都听到念的不是原文，数学课里是硬伤）。
    结尾多说的（build.fix_tail 自动截掉）、句间念出半个音的杂音（stray_sounds 自动静音）能自动修，不算。"""
    out = ["数字念错：原文「%s」听成「%s」" % (w, h) for _, _, _, w, h in num_bad]
    if worst < 0.9:
        out.append("有场景对齐率只有 %.0f%%" % (worst * 100))
    n = len(stream)
    long_ = [(i1, e, a) for i1, e, a in sus if max(len(e), len(a)) >= 4 and i1 < n - 6]
    out += ["「%s」→「%s」" % (e, a) for _, e, a in long_]
    if len(sus) - len(long_) >= 5:
        out.append("零碎可疑 %d 处" % (len(sus) - len(long_)))
    return out


def suspicious(stream, words):
    """配音识别回来与口播逐字比对，挑出"真可疑"的地方：读成了别的音、漏读、多读。
    不算：字母（识别器对 A/B/PN 本身不稳）、同音字（点→碘、作→做，识别器选字问题，不是读错）。
    2026-09-28 实测：被标可疑的地方与用户耳听的吞音位置吻合（两条腰→两条摇）。"""
    import difflib
    import align as AL
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        lazy_pinyin = None
    act, _ = AL.word_stream(words)
    is_cn = lambda c: "一" <= c <= "鿿"

    def py_seq(seq):
        """整串带上下文注音（重叠→chong die，不会把"重"单独注成 zhong），逐字对齐；字母位置为 None"""
        cn = [c for c in seq if is_cn(c)]
        pys = iter(lazy_pinyin("".join(cn)) if lazy_pinyin else cn)
        return [next(pys) if is_cn(c) else None for c in seq]
    pe, pa = py_seq(stream), py_seq(act)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, AL.canon(stream), AL.canon(act), autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        e, a = "".join(stream[i1:i2]), "".join(act[j1:j2])
        if e and not any(is_cn(c) for c in e):
            continue                    # 口播里是字母（D、PN…）：老师式读法被识别成"地""皮恩"很正常，不算
        if not any(is_cn(c) for c in e + a):
            continue
        if tag == "replace":
            ye = [p for p in pe[i1:i2] if p]
            ya = [p for p in pa[j1:j2] if p]
            if ye == ya:
                continue                # 同音字（点→碘、作→做），识别器选字问题
            # 白板课 9-28：数字 2 在"2只""2个"前读"两"是对的；结构助词 地/的/得 识别器写法随意，都不算读错
            ne = e.replace("地", "的").replace("得", "的")
            na = a.replace("地", "的").replace("得", "的")
            # 两/二 互换（两千→二千、2个→两个）是识别器/归一化的写法，不是读错
            if ne == na or (set(e) <= {"二", "两"} and set(a) <= {"二", "两"} and len(e) == len(a)):
                continue
            ye2 = [x.replace("di", "de") for x in ye]
            ya2 = [x.replace("di", "de") for x in ya]
            if ye2 == ya2:
                continue
            ye3 = [x for x in py_seq(list(e.replace("二", "两")))]
            if lazy_pinyin and [x for x in ye3 if x] == ya:
                continue
        out.append((i1, e, a))
    # 挨着的几处（相隔 ≤3 字）是同一件事（例：6、4、2、0 被连读成"六千四百二十"会报出 千/百/零→十 三处），并成一处
    merged = []
    for i1, e, a in out:
        if merged and i1 - (merged[-1][0] + max(1, len(merged[-1][1]))) <= 3:
            j, e0, a0 = merged[-1]
            merged[-1] = (j, "".join(stream[j:i1 + len(e)]) if e else e0, a0 + a)
        else:
            merged.append((i1, e, a))
    return merged


def _pinyin_seq(seq):
    """读音流 -> 逐字不带声调的拼音（字母、符号原样），比对时同音字算对上"""
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        return list(seq)
    return [lazy_pinyin(c)[0] if "一" <= c <= "鿿" else c for c in seq]


def _scene_rate(stream, words, sc):
    """场景对齐率：按读音比（同音字算对上）。9-30 函数压轴题：18 个字的标题句里"滑→划""交→焦"两个同音字
    就把对齐率压到 89%，被当成"明显问题"白白多合成一遍"""
    import difflib
    import align as AL
    act, _ = AL.word_stream(words)
    sm = difflib.SequenceMatcher(None, _pinyin_seq(AL.canon(stream)), _pinyin_seq(AL.canon(act)), autojunk=False)
    hit = 0
    for i, j, n in sm.get_matching_blocks():
        lo, hi = max(i, sc["s0"]), min(i + n, sc["s1"])
        hit += max(0, hi - lo)
    return hit / max(1, sc["s1"] - sc["s0"])


def _trim(pcm, words, lead=0.15, tail=0.3):
    """切掉场景首尾多余静音（保留 lead/tail），时间戳跟着平移"""
    db = frame_db(pcm)
    if len(db) == 0:
        return pcm, words
    import numpy as np
    loud = np.where(db > np.percentile(db, 95) - 32)[0]
    if len(loud) == 0:
        return pcm, words
    a = max(0.0, loud[0] * 0.01 - lead)
    b = min(len(pcm) / 2 / SR, (loud[-1] + 1) * 0.01 + tail)
    seg = pcm[int(a * SR) * 2:int(b * SR) * 2]
    for w in words:
        w["t"] = round(max(0.0, w["t"] - a), 3)
        if "t_end" in w:
            w["t_end"] = round(max(0.0, w["t_end"] - a), 3)
    return seg, words


def synth_narration(text, cfg, log=print):
    """一个场景的口播 -> (pcm_bytes, words[{text, t, t_end}], 采样率)，接口与 tts_bailian.synth_narration 一致"""
    import align as AL
    from tts_bailian import split_sentences
    key = load_key(cfg)
    sents = split_sentences(text)                      # [(句子含句末标点, 句末标记：标点或 ｜)]
    clean = tagged_text(sents)                         # 送 Gemini 的文本：｜ 换成停顿标记，每句后 <short pause>
    offs, stream = [], []
    for s, _ in sents:
        offs.append(len(stream))
        stream += AL.stream(s)[0]
    best = None
    for attempt in range(3):
        pcm = _speak(clean, cfg, key, log)
        words = _asr_words(pcm, cfg)
        times, rate = AL.align_times(stream, words)
        log("   Gemini %s: %d 句 %d 字 -> %.1fs, 识别对齐 %.0f%%" % (
            cfg.get("gemini_voice", "Erinome"), len(sents), len(clean), len(pcm) / 2 / SR, rate * 100))
        if best is None or rate > best[3]:
            best = (pcm, words, times, rate)
        if rate >= MIN_RATE:
            break
        log("   [Gemini] 对齐率偏低（可能漏读/读错），重新合成")
    pcm, words, times, rate = best
    out, words, inserts = _pad_sentences(pcm, sents, offs, len(stream), times, words, log)
    log("   句间补停顿 %d 处，共 %.1fs；成段 %.1fs" % (len(inserts), sum(g for _, g in inserts), len(out) / 2 / SR))
    return out, words, SR
