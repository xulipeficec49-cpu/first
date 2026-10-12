# -*- coding: utf-8 -*-
"""口播文本 <-> 配音字级时间戳 对齐

百炼返回的字级时间戳把数字按读法给出（10 -> 十，2.25 -> 二点二五），字母逐个给出。
这里把"归一化后的口播"也转成同样的"读音流"（汉字 + 大写字母，数字转汉字读法），
再用 difflib 做序列对齐：每个读音字都拿到一个时刻，对不上的按前后插值。
句子起点、锚点词的时刻都从这条流上取。
"""
import difflib
import re

CN = "零一二三四五六七八九"


def _int_cn(n):
    """0~99999999 -> 读法汉字（10 -> 十，105 -> 一百零五，1000 -> 一千）"""
    n = int(n)
    if n == 0:
        return "零"
    units = ["", "十", "百", "千"]

    def four(x):
        s, zero = "", False
        for i in range(3, -1, -1):
            d = x // (10 ** i) % 10
            if d == 0:
                zero = bool(s)
                continue
            if zero:
                s += "零"
                zero = False
            s += CN[d] + units[i]
        return s
    hi, lo = divmod(n, 10000)
    s = (four(hi) + "万" if hi else "") + ("零" if hi and 0 < lo < 1000 else "") + (four(lo) if lo else "")
    if s.startswith("一十"):
        s = s[1:]
    return s


def num_cn(tok):
    """'2.25' -> 二点二五；'10' -> 十"""
    if "." in tok:
        a, b = tok.split(".", 1)
        return _int_cn(a or "0") + "点" + "".join(CN[int(c)] for c in b)
    return _int_cn(tok)


def is_sound(ch):
    return ("一" <= ch <= "鿿") or ("A" <= ch <= "Z") or ("a" <= ch <= "z")


# 数学符号按读音进流（口播写 π、识别写 派 或 π，两边都算"派"才对得上；2026-09-29 高中函数题）
SYM = {"π": "派", "√": "根号", "∞": "无穷", "∈": "属于", "≤": "小于等于", "≥": "大于等于", "α": "阿尔法", "θ": "西塔"}
# 圈号数字：口播写"第①问"，Gemini 读"第一问"（9-30 赵爽弦图题：没映射时读音流里少了"一"，被误判成"数字念错"，白白多合成两遍）
SYM.update({c: n for c, n in zip("①②③④⑤⑥⑦⑧⑨⑩", ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"])})

# 比对用的"同音归一"：字母 R 念出来识别器常写成 二/儿/尔（9-30 电阻网络题："R零"被听成"二零"、"小r"被听成"小二"，
# 对齐率掉到 89%、还被当成数字念错，白白多合成）。只用于两边序列比对，不改时刻
CANON = {"R": "二", "儿": "二", "尔": "二", "两": "二"}


def canon(seq):
    return [CANON.get(c, c) for c in seq]


def stream(text):
    """归一化文本 -> (读音字列表, 每个文本下标对应的读音流下标)"""
    out, pos = [], [0] * (len(text) + 1)
    i = 0
    while i < len(text):
        m = re.match(r"\d+(?:\.\d+)?", text[i:])
        if m:
            for k in range(len(m.group(0))):
                pos[i + k] = len(out)
            out.extend(num_cn(m.group(0)))
            i += len(m.group(0))
            continue
        pos[i] = len(out)
        ch = text[i]
        if ch in SYM:
            out.extend(SYM[ch])
        elif is_sound(ch):
            out.append(ch.upper())
        i += 1
    pos[len(text)] = len(out)
    return out, pos


def word_stream(words):
    """[{text, t}] -> (读音字列表, 各字时刻)。一个词含多字时，字间时刻在本词与下一词之间均分"""
    chars, times = [], []
    for i, w in enumerate(words):
        txt = w.get("text", "")
        seq = []
        j = 0
        while j < len(txt):
            # 识别器把"负二"写成"-2"（9-30 函数压轴题：负数多的场景对齐率掉到 89%，被误判成明显问题），减号当"负"
            # 前面是字母或数字的减号是"减"（"x-1""3-2"），否则是"负"
            if txt[j] in "-−" and j + 1 < len(txt) and txt[j + 1].isalnum():
                prev = txt[j - 1] if j else " "
                seq.append("减" if prev.isascii() and prev.isalnum() else "负")
                j += 1
                continue
            m = re.match(r"\d+(?:\.\d+)?", txt[j:])
            if m:
                seq.extend(num_cn(m.group(0)))
                j += len(m.group(0))
                continue
            if txt[j] in SYM:
                seq.extend(SYM[txt[j]])
            elif is_sound(txt[j]):
                seq.append(txt[j].upper())
            j += 1
        if not seq:
            continue
        t0 = float(w["t"])
        if w.get("t_end") and float(w["t_end"]) > t0:       # 识别结果带词尾时刻（Gemini 路径）：字在本词时长内均分
            t1 = float(w["t_end"])
        else:
            t1 = float(words[i + 1]["t"]) if i + 1 < len(words) else t0 + 0.25 * len(seq)
        step = max(0.0, (t1 - t0)) / len(seq)
        step = min(step, 0.3)
        for k, ch in enumerate(seq):
            chars.append(ch)
            times.append(t0 + k * step)
    return chars, times


def align_times(expected, words):
    """期望读音流 -> 每个字的时刻（对不上的插值）；返回 (times, 匹配率)"""
    act, at = word_stream(words)
    n = len(expected)
    res = [None] * n
    sm = difflib.SequenceMatcher(None, canon(expected), canon(act), autojunk=False)
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            res[a + k] = at[b + k]
        matched += size
    # 插值
    known = [i for i in range(n) if res[i] is not None]
    if not known:
        total = at[-1] if at else n / 4.3
        return [total * i / max(1, n) for i in range(n)], 0.0
    for i in range(n):
        if res[i] is not None:
            continue
        lo = max([k for k in known if k < i], default=None)
        hi = min([k for k in known if k > i], default=None)
        if lo is None:
            res[i] = max(0.0, res[hi] - 0.23 * (hi - i))
        elif hi is None:
            res[i] = res[lo] + 0.23 * (i - lo)
        else:
            res[i] = res[lo] + (res[hi] - res[lo]) * (i - lo) / (hi - lo)
    return res, matched / max(1, n)


def find_sub(seq, sub, start=0, end=None):
    """在读音流 seq[start:end] 里找子序列 sub，返回起始下标或 -1"""
    end = len(seq) if end is None else end
    L = len(sub)
    if L == 0:
        return -1
    for i in range(start, end - L + 1):
        if seq[i:i + L] == sub:
            return i
    return -1


if __name__ == "__main__":
    for s in ["10", "21", "105", "1000", "2.25", "45", "0", "10000", "12000"]:
        print(s, num_cn(s))
    print(stream("梯形ABCD，角DAB是45度。"))
