# -*- coding: utf-8 -*-
"""口播读法归一化：把写稿人写的算式 / 单位 / 分数 / 百分数 / 比 等，转成 TTS 能稳读的汉字读法。

写稿人可以直接写 "240÷8=30"、"(5+3)"、"1/4"、"5:3"、"12.5%"、"km/h"、"第(1)问"、"$\\frac{1}{2}$"，
tts 阶段自动转成 "240除以8等于30"、"5加3的和"、"四分之一"... 等读法；数字本身保留阿拉伯数字
（引擎读得准，且数字一致性闸门靠它对账）。锚点词校验同时接受原文与归一化后的文本。

用法:  python narr_norm.py "文本"          直接看转换结果
       python narr_norm.py --sb 分镜.json   打印每个环节归一化后的口播, 供人工过一遍读法
"""
import json
import re
import sys

CN_DIGITS = "零一二三四五六七八九"
NUM = r"\d+(?:\.\d+)?"


def _cn_small(n):
    """1~99 -> 汉字(第(1)问 -> 第一问)"""
    n = int(n)
    if n < 10:
        return CN_DIGITS[n]
    if n < 20:
        return "十" + (CN_DIGITS[n % 10] if n % 10 else "")
    if n < 100:
        return CN_DIGITS[n // 10] + "十" + (CN_DIGITS[n % 10] if n % 10 else "")
    return str(n)


# 复合/字母单位（替换时按长度从长到短，免得 cm² 先被 m² 吃成"c平方米"——2026-09-30 修）
UNIT_COMPOUND = [
    ("kg/m³", "千克每立方米"), ("g/cm³", "克每立方厘米"), ("N/kg", "牛每千克"),
    ("km/h", "千米每小时"), ("m/s", "米每秒"), ("km²", "平方千米"), ("m²", "平方米"),
    ("dm²", "平方分米"), ("cm²", "平方厘米"), ("mm²", "平方毫米"), ("m³", "立方米"),
    ("dm³", "立方分米"), ("cm³", "立方厘米"), ("km", "千米"), ("cm", "厘米"),
    ("mm", "毫米"), ("dm", "分米"), ("kg", "千克"), ("mL", "毫升"), ("ml", "毫升"),
    ("min", "分钟"), ("℃", "摄氏度"),
]
UNIT_SINGLE = {"m": "米", "g": "克", "L": "升", "l": "升", "h": "小时", "s": "秒", "t": "吨"}
CN_UNIT = ("米|千米|厘米|分米|毫米|元|角|分|千克|克|吨|升|毫升|个|件|页|棵|张|本|人|次|块|盒|箱|桶|袋|"
           "平方米|平方厘米|平方分米|平方千米|立方米|立方厘米|立方分米|字|题|道|支|辆|条|只|头|朵|台|间|"
           "kg|km|m|g|L")
CN_PER = ("秒|分钟|分|小时|时|天|日|周|月|年|米|千米|厘米|千克|克|个|件|人|次|页|台|辆|桶|盒|箱|"
          "平方米|亩|公顷|h|s|min")

MATH_TEX = [
    (r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\2分之\1"),
    (r"\\sqrt\{([^{}]+)\}", r"根号\1"),
    (r"\\sqrt(\w)", r"根号\1"),
    (r"\^\{?2\}?", "的平方"),
    (r"\^\{?3\}?", "的立方"),
    (r"\^\{?(\w+)\}?", r"的\1次方"),
    (r"\\times", "乘"), (r"\\div", "除以"), (r"\\cdot", "乘"),
    (r"\\triangle", "三角形"), (r"\\angle", "角"), (r"\\pi", "π"),
    (r"_\{?(\w+)\}?", r"\1"),
]
OPS = {"+": ("加", "和"), "-": ("减", "差"), "×": ("乘", "积"), "*": ("乘", "积"),
       "÷": ("除以", "商"), "/": ("除以", "商")}


def hs_math(t):
    """高中函数题的读法（只改配音文本，字幕照原样显示）：
    sin/cos 读 sine/cosine（老师读 [saɪn]；写 sin 怕被读成英文单词 sin）；f(x) 读 f x；x₁ 读 x一；
    π/4 读 4分之π，3π/2 读 2分之3π；√2/2 读 2分之根号2；∈ ∀ ∃ ∞ ∪ · 读 属于 任意 存在 无穷 并 乘"""
    t = t.replace("−", "-").replace("₁", "一").replace("₂", "二").replace("₀", "零")
    t = t.replace("″", "两撇").replace("′", "撇")          # R′ 念 R撇，R″ 念 R两撇
    t = re.sub(r"cos(?!ine)", "cosine", t)
    t = re.sub(r"sin(?!e)", "sine", t)
    t = re.sub(r"√\s*(\d+)\s*/\s*(\d+)", r"\2分之根号\1", t)                 # √2/2 -> 2分之根号2
    t = re.sub(r"(\d*)\s*π\s*/\s*(\d+)", lambda m: "%s分之%sπ" % (m.group(2), m.group(1)), t)   # 3π/4 -> 4分之3π
    t = re.sub(r"(?<![A-Za-z0-9])([a-z])\s*/\s*(\d+)", r"\2分之\1", t)                              # a/2 -> 2分之a
    t = t.replace("√", "根号")
    t = re.sub(r"\b([fgh])\(\s*([^()]*?)\s*\)", r"\1 \2", t)              # f(x) -> f x，g(x+2π) -> g x+2π
    t = t.replace("+∞", "正无穷").replace("-∞", "负无穷")
    for a, b in (("∈", "属于"), ("∉", "不属于"), ("∀", "任意"), ("∃", "存在"), ("∞", "无穷"), ("∪", "并"), ("·", "乘"),
                 ("⇔", "等价于"), ("⇒", "推出")):
        t = t.replace(a, b)
    return t


def normalize(text):
    t = text
    for a, b in (("∠", "角"), ("△", "三角形"), ("∥", "平行于"), ("⊥", "垂直于"), ("≌", "全等于"), ("→", "到")):
        t = t.replace(a, b)
    t = hs_math(t)

    def tex(m):
        s = m.group(1)
        for pat, rep in MATH_TEX:
            s = re.sub(pat, rep, s)
        return s
    t = re.sub(r"\$([^$]*)\$", tex, t)                       # $...$ 数学段
    t = re.sub(r"第\s*[（(]\s*(\d{1,2})\s*[)）]\s*问",
               lambda m: "第" + _cn_small(m.group(1)) + "问", t)
    t = re.sub(r"第(\d{1,2})问", lambda m: "第" + _cn_small(m.group(1)) + "问", t)

    def paren(m):                                            # (a+b) -> a加b的和
        a, op, b = m.group(1), m.group(2), m.group(3)
        w, n = OPS[op]
        return "%s%s%s的%s" % (a, w, b, n)
    t = re.sub(r"[（(]\s*(%s)\s*([+\-×*÷/])\s*(%s)\s*[)）]" % (NUM, NUM), paren, t)
    for pat, rep in sorted(UNIT_COMPOUND, key=lambda x: -len(x[0])):   # 单位
        t = t.replace(pat, rep)
    # 单位后面紧跟汉字时 \b 不成立（汉字也算 \w），"1.6 N减1.5 N"的第一个 N 会漏掉 → 用"后面不是字母数字"判断
    t = re.sub(r"(?<=\d)\s*(kPa|Pa|N)(?![A-Za-z0-9])", lambda m: {"kPa": "千帕", "Pa": "帕", "N": "牛"}[m.group(1)], t)   # 物理：力、压强
    # 单字母单位要和数字之间有空格（"20 g""3 s"）：紧挨着的是代数式（"2t""3x"），9-30 函数压轴题 "2t−4" 被读成"2吨负4"
    t = re.sub(r"(?<=\d)\s+(m|g|L|l|h|s|t)(?![A-Za-z0-9])", lambda m: UNIT_SINGLE[m.group(1)], t)
    t = re.sub(r"(%s)\s*/\s*(%s)" % (CN_UNIT, CN_PER), r"\1每\2", t)   # 米/秒 -> 米每秒
    t = re.sub(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])", r"\2分之\1", t)    # 1/4 -> 四分之一(数字保留)
    t = re.sub(r"(%s)\s*[:：]\s*(%s)" % (NUM, NUM), r"\1比\2", t)          # 5:3 -> 5比3
    t = re.sub(r"(%s)\s*%%" % NUM, r"百分之\1", t)                          # 12.5% -> 百分之12.5
    t = re.sub(r"\s*×\s*", "乘", t)
    t = re.sub(r"\s*÷\s*", "除以", t)
    t = re.sub(r"(?<=[0-9A-Za-zπαθ)）一二米克牛帕升秒度])\s*\+\s*(?=[0-9A-Za-zπαθ(（根])", "加", t)
    t = re.sub(r"(?<=[0-9A-Za-zπαθ)）一二米克牛帕升秒度])\s*-\s*(?=[0-9A-Za-zπαθ(（根])", "减", t)
    t = re.sub(r"(?<![0-9A-Za-zπαθ)）])-(?=[\dπ根a-zαθ])", "负", t)        # 负数、-a/2、−cos α
    for a, b in (("≠", "不等于"), ("≈", "约等于"), ("≥", "大于等于"), ("≤", "小于等于"),
                 ("=", "等于"), (">", "大于"), ("<", "小于")):
        t = re.sub(r"\s*%s\s*" % re.escape(a), b, t)
    t = t.replace("°", "度")
    t = t.replace("α", "阿尔法").replace("θ", "西塔")      # 希腊字母按老师读法（算符规则之后再换，免得"α+"不认）
    return t


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--sb":
        sb = json.load(open(sys.argv[2], encoding="utf-8"))
        for st in sb["stages"]:
            n = st.get("narration", "")
            print("== %s [%s]" % (st.get("id"), st.get("template")))
            print(normalize(n))
            print()
    elif len(sys.argv) >= 2:
        print(normalize(" ".join(sys.argv[1:])))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
