# -*- coding: utf-8 -*-
"""从整片原始合成里剪掉一段多念的话（不重新花钱合成），之后跑 make_video.py tts 会用剪过的原始合成重做切段和调停顿。

用法：python cut_raw.py <分镜.json> <起秒> <止秒>
  起止时刻是原始合成（build_*/audio_gemini/_raw.pcm）里的时刻，先用第二个识别听小段定位：多念的内容前后各找一个
  能量谷（字与字之间）或静音点当切口，切口 5ms 淡出淡入。会先备份 _raw.pcm/_raw.json（_raw_before_cut_*）。
例（2026-09-30 赵爽弦图）：模型把"把 △BEO 绕点 O 转半圈"念成"把 A B C D 三角形 BEO……"，
  识别小段定位"把"止于 149.95、"三"起于 151.02 → python cut_raw.py 赵爽弦图.json 149.96 150.90
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_video as MV     # noqa: E402
import tts_gemini as TG     # noqa: E402


def main():
    bd = MV.Board(sys.argv[1])
    a, b = float(sys.argv[2]), float(sys.argv[3])
    adir = bd.audio_dir()
    rp, rj = adir / "_raw.pcm", adir / "_raw.json"
    tag = "%.2f-%.2f" % (a, b)
    shutil.copy(rp, adir / ("_raw_before_cut_%s.pcm" % tag))
    shutil.copy(rj, adir / ("_raw_before_cut_%s.json" % tag))
    pcm = rp.read_bytes()
    meta = json.loads(rj.read_text(encoding="utf-8"))
    d = b - a
    rp.write_bytes(TG.apply_edits(pcm, [((a + b) / 2, -d)]))
    # 起点落在切掉那段里的识别词不删（识别时间戳常报早：9-30 两次把真话"把""这样"的起点报进了切口），挪到切口处；
    # 真正多念的那几个字留在识别结果里也无妨——对齐时只当多出来的字，不影响口播各字的时刻
    words = []
    for w in meta["words"]:
        if a <= w["t"] < b:
            print("  识别词起点在切口里，挪到切口：%s（%.2f）" % (w["text"], w["t"]))
            w = dict(w, t=round(a, 3), **({"t_end": round(max(a, w["t_end"] - d), 3)} if "t_end" in w else {}))
        elif w["t"] >= b:
            w = dict(w, t=round(w["t"] - d, 3), **({"t_end": round(w["t_end"] - d, 3)} if "t_end" in w else {}))
        words.append(w)
    meta["words"] = words
    rj.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (adir / "_film.json").unlink(missing_ok=True)       # 让下一次 tts 用剪过的原始合成重做后期
    print("已剪掉 %.2f~%.2f 秒（%.2f 秒）；接着跑 make_video.py tts（不会重新合成）" % (a, b, d))


if __name__ == "__main__":
    main()
