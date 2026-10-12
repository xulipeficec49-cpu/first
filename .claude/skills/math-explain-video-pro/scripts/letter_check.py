# -*- coding: utf-8 -*-
"""几何题配音的字母复核：逐句让第二个识别模型（百炼 qwen3-asr-flash）再听，比对每句里的字母序列（ABE、DGO、MH……）。
第一个识别（paraformer）对字母不稳，suspicious() 里字母差异一律不算；几何题字母念错（DGO 念成 DOG、MH 念成 MD）是硬伤，要单独复核。
用法：python letter_check.py <分镜.json>        （tts 之后、render 之前跑）
（2026-09-30 赵爽弦图几何题加）"""
import difflib
import json
import re
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_video as MV     # noqa: E402
import tts_gemini as TG     # noqa: E402


def letters(s):
    return re.sub(r"[^A-Z]", "", s.upper())


def main():
    bd = MV.Board(sys.argv[1])
    cfg = bd.tts_config()
    adir = bd.audio_dir()
    n = bad = 0
    for scn in bd.scenes:
        sp = bd.speech(scn, False)
        with wave.open(str(adir / (scn["id"] + ".wav")), "rb") as w:
            pcm = w.readframes(w.getnframes())
        for b in scn["beats"]:
            for s in b["sents"]:
                want = letters(s["norm"])
                if not want:
                    continue
                n += 1
                t0, t1 = max(0.0, s["start"] - 0.25), s["stop"] + 0.35
                heard = TG._asr2(pcm[int(t0 * TG.SR) * 2:int(t1 * TG.SR) * 2], cfg)
                got = letters(heard)
                ok = got == want
                if not ok:
                    # 识别把"x"写成"X"、"h₁"写成"H1"之类不算：只看差异里有没有大写几何字母对不上
                    sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
                    diff = [(want[i1:i2], got[j1:j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
                    bad += 1
                    print("%s ✗ %s\n      要：%s\n      听：%s   差异：%s\n      第二个识别原文：%s" % (scn["id"], s["disp"], want, got, diff, heard))
    print("共 %d 句含字母，字母序列对不上的 %d 句（逐条人工判断：识别漏字母/多字母常见，念反、念错才要重合成）" % (n, bad))


if __name__ == "__main__":
    main()
