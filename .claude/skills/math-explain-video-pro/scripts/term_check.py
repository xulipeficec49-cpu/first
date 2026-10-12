# -*- coding: utf-8 -*-
"""配音里易读错的地方复听：切出前后一小段让第二个识别模型（百炼 qwen3-asr-flash）再听一遍。

用法：
  python term_check.py <分镜.json> [字 ...]      物理/化学易误读字（默认 浸）：听到的字读音相同就算读对（"浸入"写成"进入"也算对），
                                                 读音不同（"侵入""沁入"）列出来，人再去听
  python term_check.py <分镜.json> --letters     几何题的字母对：ME、HE、ON、AD 这种两个大写字母正好拼成英文单词的，
                                                 看识别出来的是不是大写字母（读成单词 me/he/on 会被识别成小写或汉字）
（2026-09-30：初中物理珠串浮力题加"浸"；赵爽弦图几何题加字母对。9-29 白板课物理课踩过"浸"被第一个识别听成"侵/寂寞"的坑）"""
import json
import re
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import align as AL          # noqa: E402
import make_video as MV     # noqa: E402
import tts_gemini as TG     # noqa: E402

# 两个字母恰好是常见英文单词的（几何题里最容易撞上的）
WORDS = {"AD", "AH", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "HI", "IF", "IN", "IS", "IT", "ME", "MY",
         "NO", "OF", "OH", "OK", "ON", "OR", "SO", "TO", "UP", "US", "WE"}


def scenes_audio(bd):
    adir = bd.audio_dir()
    for scn in bd.scenes:
        info = json.loads((adir / (scn["id"] + ".json")).read_text(encoding="utf-8"))
        stream = AL.stream(info["text"])[0]
        times, _ = AL.align_times(stream, info["words"])
        with wave.open(str(adir / (scn["id"] + ".wav")), "rb") as w:
            pcm = w.readframes(w.getnframes())
        yield scn["id"], stream, times, pcm


def clip(pcm, times, i, j, cfg):
    t0 = max(0.0, times[max(0, i - 4)] - 0.3)
    t1 = times[min(len(times) - 1, j + 4)] + 0.5
    return TG._asr2(pcm[int(t0 * TG.SR) * 2:int(t1 * TG.SR) * 2], cfg)


def check_chars(bd, chars, cfg):
    from pypinyin import lazy_pinyin
    n, bad = 0, 0
    for sid, stream, times, pcm in scenes_audio(bd):
        for i, ch in enumerate(stream):
            if ch not in chars:
                continue
            n += 1
            heard = clip(pcm, times, i, i, cfg)
            want = "".join(stream[max(0, i - 2):i + 3])
            py = lazy_pinyin(ch)[0]
            ok = any(lazy_pinyin(c)[0] == py for c in heard if "一" <= c <= "鿿")
            bad += not ok
            print("%s %s「%s」→ 听到「%s」%s" % (sid, "✓" if ok else "✗", want, heard, "" if ok else "  ← 请人工复听"))
    print("共 %d 处，读音存疑 %d 处" % (n, bad))


def check_letters(bd, cfg):
    isL = lambda c: "A" <= c <= "Z"
    n, bad = 0, 0
    for sid, stream, times, pcm in scenes_audio(bd):
        for i in range(len(stream) - 1):
            pair = stream[i] + stream[i + 1]
            if pair not in WORDS or not (isL(stream[i]) and isL(stream[i + 1])):
                continue
            if (i > 0 and isL(stream[i - 1])) or (i + 2 < len(stream) and isL(stream[i + 2])):
                continue                      # 三个及以上字母连写（如 ABCD、EFGH）不是这里要查的
            n += 1
            heard = clip(pcm, times, i, i + 1, cfg)
            ok = re.search(r"%s\s*%s" % (pair[0], pair[1]), heard) is not None      # 听成大写字母 = 按字母读
            bad += not ok
            print("%s %s「%s」→ 听到「%s」%s" % (sid, "✓" if ok else "✗", pair, heard, "" if ok else "  ← 可能读成了英文单词，请人工复听"))
    print("共 %d 处字母对，存疑 %d 处" % (n, bad))


def main():
    bd = MV.Board(sys.argv[1])
    cfg = bd.tts_config()
    args = sys.argv[2:]
    if "--letters" in args:
        check_letters(bd, cfg)
    else:
        check_chars(bd, args or ["浸"], cfg)


if __name__ == "__main__":
    main()
