# -*- coding: utf-8 -*-
"""配音里的"杂音"：句间静音中间孤零零的一小段响声（9-28 白板课实测：Gemini 把 <short pause> 标记读出半个音，
识别成 "Bye"）。规则：一段有声 ≤0.45 秒、两边各有 ≥0.3 秒静音、且识别不是口播里的字 → 算杂音，静音掉（两边 10ms 淡变）。

make_video.py tts 合成完会自动调 clean()；也可以单独跑：
    python stray_sounds.py <分镜.json> [--fix]   不带 --fix 只列出；带 --fix 改写 audio_gemini/_raw.pcm 与 _raw.json，
之后跑 make_video.py tts 会用改过的原始合成重做切段和调停顿（不重新花钱合成）。
（2026-09-29 从白板专题课 engine\\scripts 移植过来，只改了 main() 读讲题分镜的格式）
"""
import difflib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import align as AL          # noqa: E402
import tts_gemini as TG     # noqa: E402

SR = 24000


def find(raw, words, script_stream):
    db = TG.frame_db(raw)
    thr = float(np.percentile(db, 95)) - 32
    q = np.concatenate([[False], db > thr, [False]])
    ed = np.flatnonzero(np.diff(q.astype(np.int8)))
    merged = []
    for a, b in zip(ed[::2], ed[1::2]):                    # 帧下标 [a, b)；字内短暂低能量不算断
        if merged and a - merged[-1][1] < 8:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    act, at = AL.word_stream(words)
    matched = np.zeros(len(act), bool)
    for i, j, n in difflib.SequenceMatcher(None, AL.canon(script_stream), AL.canon(act), autojunk=False).get_matching_blocks():
        matched[j:j + n] = True
    out = []
    for k, (a, b) in enumerate(merged):
        dur = (b - a) * 0.01
        gap_l = (a - merged[k - 1][1]) * 0.01 if k else a * 0.01
        gap_r = (merged[k + 1][0] - b) * 0.01 if k + 1 < len(merged) else 9.9
        if dur > 0.45 or gap_l < 0.3 or gap_r < 0.3:
            continue
        t0, t1 = a * 0.01, b * 0.01
        idx = [j for j, tt in enumerate(at) if t0 - 0.15 <= tt <= t1 + 0.1]
        if any(matched[j] for j in idx):
            continue
        # 识别成口播里有的单个字母/数字（"到 B。"的 B 前后都停顿，看上去像孤立杂音）→ 是真话，别静音。
        # 9-30 函数压轴题：真的"B"被当杂音静音了，口播变成"Q 还没到，M 在下边"。"Bye" 这种多字母的仍当杂音
        ws = [w["text"].strip() for w in words if t0 - 0.35 <= w["t"] <= t1 + 0.1]
        if any(len(x) <= 2 and x and all(c.isascii() and c.isalnum() for c in x) and x.upper() in "".join(script_stream).upper()
               for x in ws):
            continue
        out.append((t0, t1, "".join(act[j] for j in idx), [w["text"] for w in words if t0 - 0.35 <= w["t"] <= t1 + 0.1]))
    return out


def clean(adir, script_stream, log=print):
    """把 adir/_raw.pcm 里的杂音静音、识别结果里对应的词删掉；返回处理了几处（0 = 没有杂音，没改文件）"""
    adir = Path(adir)
    raw = (adir / "_raw.pcm").read_bytes()
    meta = json.loads((adir / "_raw.json").read_text(encoding="utf-8"))
    hits = find(raw, meta["words"], script_stream)
    if not hits:
        return 0
    # 改原始合成之前先备份（9-30 静音掉了真话、又没备份，只好重配）
    import shutil
    shutil.copy(adir / "_raw.pcm", adir / "_raw_before_clean.pcm")
    shutil.copy(adir / "_raw.json", adir / "_raw_before_clean.json")
    x = np.frombuffer(raw, np.int16).astype(np.float32).copy()
    nf = int(0.01 * SR)
    for t0, t1, txt, ws in hits:
        i0, i1 = int((t0 - 0.03) * SR), int((t1 + 0.03) * SR)
        x[max(0, i0 - nf):i0] *= np.linspace(1, 0, i0 - max(0, i0 - nf))
        x[i0:i1] = 0
        x[i1:i1 + nf] *= np.linspace(0, 1, len(x[i1:i1 + nf]))
        log("   [杂音] %.2f~%.2f 秒（%.2f 秒）静音掉，识别：%s %s" % (t0, t1, t1 - t0, txt or "（无）", ws))
    (adir / "_raw.pcm").write_bytes(x.astype(np.int16).tobytes())
    script = "".join(script_stream)
    meta["words"] = [w for w in meta["words"]
                     if not any(t0 - 0.35 <= w["t"] <= t1 + 0.1 and not any(ch in script for ch in w["text"]) for t0, t1, _, _ in hits)]
    (adir / "_raw.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (adir / "_film.json").unlink(missing_ok=True)
    return len(hits)


def main():
    import make_video as MV
    bd = MV.Board(sys.argv[1])
    adir = bd.audio_dir()
    stream = [c for scn in bd.scenes for c in AL.stream(bd.scene_tts_text(scn))[0]]
    if "--fix" in sys.argv:
        n = clean(adir, stream)
        print("已静音 %d 处；接着跑 build.py tts（不会重新合成）" % n if n else "没有杂音")
        return
    raw = (adir / "_raw.pcm").read_bytes()
    meta = json.loads((adir / "_raw.json").read_text(encoding="utf-8"))
    hits = find(raw, meta["words"], stream)
    print("孤立杂音 %d 处" % len(hits))
    for t0, t1, txt, ws in hits:
        print("   %6.2f~%6.2f 秒（%.2f 秒）识别：%s %s" % (t0, t1, t1 - t0, txt or "（无）", ws))


if __name__ == "__main__":
    main()
