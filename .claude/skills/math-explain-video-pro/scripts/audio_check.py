# -*- coding: utf-8 -*-
"""成片配音体检：① 插进去的静音有没有切进字音（吞音/消音）② 各场景音色是否一致（中位音高）
用法：python audio_check.py <分镜.json>     （render 之后跑，读 build_<名>/narration.wav 与 timeline.json）
2026-09-28 用户反馈 Gemini 配音"换音色、吞音"后加：根因是分场景各合成一次、插静音按时间戳下刀。"""
import json
import sys
import wave
from pathlib import Path

import numpy as np
import parselmouth


def main():
    sb = Path(sys.argv[1]).resolve()
    build = sb.parent / ("build_" + sb.stem)
    tl = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    with wave.open(str(build / "narration.wav"), "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    # ① 插入的静音 = 连续精确为 0 的样本（>=30ms）；切口前后 15ms 仍有说话音量 = 切进了字音
    z = x == 0
    edges = np.flatnonzero(np.diff(np.concatenate([[0], z.astype(np.int8), [0]])))
    runs = [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= int(0.03 * sr)]

    def rms_db(seg):
        return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) / 32768 + 1e-9)
    speech_db = rms_db(x[np.abs(x) > 300])
    bad = []
    for a, b in runs:
        pre, post = x[max(0, a - int(0.015 * sr)):a], x[b:b + int(0.015 * sr)]
        if len(pre) and len(post) and max(rms_db(pre), rms_db(post)) > speech_db - 14:
            bad.append((a / sr, (b - a) / sr, rms_db(pre), rms_db(post)))
    print("插入静音 %d 段；切进字音的 %d 段" % (len(runs), len(bad)))
    for t, d, dp, dq in bad:
        print("   %d:%05.2f  静音 %.2fs  切口前 %.0f dB / 后 %.0f dB" % (int(t // 60), t % 60, d, dp, dq))
    # ③ 句子中间的长停顿（>1.2 秒且结束处不是下一句开头）——2026-09-28 "所以——（1.5 秒）——高 DF" 这类
    hop = int(0.01 * sr)
    m = len(x) // hop
    fdb = 20 * np.log10(np.sqrt((x[:m * hop].reshape(m, hop) ** 2).mean(axis=1)) / 32768 + 1e-9)
    thr = np.percentile(fdb, 95) - 32
    starts = [s["t0"] + 0.05 for s in tl["subs"]]
    q = np.concatenate([[False], fdb < thr, [False]])
    ed = np.flatnonzero(np.diff(q.astype(np.int8)))
    mid = []
    for a, b in zip(ed[::2], ed[1::2]):
        s_, e_ = a * 0.01, b * 0.01
        if e_ - s_ > 1.2 and not any(e_ - 0.45 <= st <= e_ + 0.45 for st in starts) \
                and any(sc["t0"] + 1.2 < s_ < sc["t1"] - 1.2 and sc["layout"] != "outro" for sc in tl["scenes"]):
            mid.append((s_, e_ - s_))
    print("句子中间的长停顿（>1.2 秒）%d 处" % len(mid))
    for t, d in mid:
        print("   %d:%05.2f  停 %.2fs" % (int(t // 60), t % 60, d))
    # ④ 句间停顿分布（不含换场景、不含等图形运动）与字幕对不对得上开口
    #    2026-09-28：识别把句末字报进停顿 → 时间轴多等 0.8 秒，句间拖到 1.7 秒；句首报早 → 字幕比声音早 1 秒多
    plain, late = [], []
    for s in tl["subs"][1:]:
        k0 = int((s["t0"] + 0.05) / 0.01)
        if k0 >= len(fdb):
            continue
        k = k0
        while k > 0 and fdb[k] >= thr and k > k0 - 15:
            k -= 1
        n = 0
        while k > 0 and fdb[k] < thr:
            k -= 1
            n += 1
        j = k0
        while j < len(fdb) and fdb[j] < thr:
            j += 1
        late.append((j - k0) * 0.01)
        lo_, hi_ = s["t0"] - n * 0.01, s["t0"]
        moving = any(a["op"] in ("tween", "camera") and a["t0"] < hi_ and a["t0"] + a["dur"] > lo_ for a in tl["actions"])
        change = any(abs(sc["t0"] - hi_) < 3.0 and sc["t0"] > lo_ - 0.5 for sc in tl["scenes"])
        if not moving and not change:
            plain.append((n * 0.01, s["t0"]))
    if plain:
        g = np.array([p for p, _ in plain])
        print("句间停顿（不含换场景、等运动）%d 处：中位 %.2fs，最长 %.2fs；超过 1.3 秒 %d 处" % (len(g), np.median(g), g.max(), (g > 1.3).sum()))
        for p, t in plain:
            if p > 1.3:
                print("   %d:%05.2f 前停 %.2fs" % (int(t // 60), t % 60, p))
    if late:
        print("字幕出现到开口：中位 %.2fs，最大 %.2fs（应接近 0）" % (np.median(late), max(late)))
    # ② 各场景中位音高（换场景音色跳变 = 相邻场景差 >1.5 个半音）
    snd = parselmouth.Sound(x / 32768.0, sampling_frequency=sr)
    p = snd.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=600)
    fv, ts = p.selected_array["frequency"], p.xs()
    med = []
    for s in tl["scenes"]:
        m = (ts >= s["t0"]) & (ts < s["t1"]) & (fv > 0)
        if m.sum() > 20:
            med.append((s["id"], float(np.median(fv[m]))))
    print("各场景中位音高：" + "  ".join("%s %.0fHz" % m for m in med))
    jumps = [(a[0], b[0], 12 * np.log2(b[1] / a[1])) for a, b in zip(med, med[1:])]
    worst = max(jumps, key=lambda j: abs(j[2])) if jumps else None
    if worst:
        print("相邻场景最大跳变：%s→%s %.1f 个半音（>1.5 能听出换人）" % worst)


if __name__ == "__main__":
    main()
