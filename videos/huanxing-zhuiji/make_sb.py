# -*- coding: utf-8 -*-
"""生成分镜 环形跑道.json（讲题视频 Pro 技能）。改讲解改这里，再跑一遍：python make_sb.py

题目：490 米环形跑道，A、B 间 50 米；甲从 A、乙从 B 反向跑，相遇后乙转身同向，甲提速 25%、乙提速 20%，
甲到 A 时乙恰到 B；之后速度方向不变，甲追上乙时一共跑了多少米？答案 2690。

世界坐标：跑道是以原点为圆心、半径 3 的圆；s = 从 A 起逆时针量的跑道长度（米），A 在正上方，
B 在 A 顺时针 50 米处（s=440）。点的位置 PX(s, r)、PY(s, r)。
速度只有比值是确定的，取甲 6、乙 5（米/单位时间）做仿真，变量 tm 是仿真时间：
  第一段 tm∈[0,40]：甲 s=6tm，乙 s=440−5tm，tm=40 在 s=240 相遇（点 P）
  第二段 tm∈[40,T2]：甲 7.5、乙 6，都逆时针；T2=40+100/3 时甲到 A（s=490）、乙到 B（s=440）
  第三段 tm∈[T2,T3]：追及，T3=T2+440/1.5，甲 s=2690（≡240，又在 P 追上），乙 s=2200（≡240）
"""
import json
from fractions import Fraction as Fr
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 先把数算一遍（s0 复核）
L, AB = 490, 50
a, b = 240, 200                      # 相遇前甲、乙的路程
assert a + b == L - AB
assert Fr(b + AB) / Fr(5, 4) / a == Fr(b) / Fr(6, 5) / b          # 甲到 A、乙到 B 同时
vj, vy = Fr(6), Fr(5)                 # 速度比 240:200 = 6:5
vj2, vy2 = vj * Fr(5, 4), vy * Fr(6, 5)
assert vj2 / vy2 == Fr(5, 4)
T1 = Fr(L - AB) / (vj + vy)
T2 = T1 + Fr(b + AB) / vj2
assert vy2 * (T2 - T1) == b
T3 = T2 + Fr(L - AB) / (vj2 - vy2)
total = a + (b + AB) + vj2 * (T3 - T2)
assert total == 2690 and (a + vj2 * (T3 - T1)) == total and vj2 * (T3 - T1) == 5 * L
T1f, T2f, T3f = float(T1), float(T2), float(T3)

RJ, RY, RY2 = 2.68, 3.32, 3.62       # 甲的跑道内侧、乙的外侧（乙第二段的轨迹再往外一圈，看得出"原路返回"）

FUNCS = {
    "PX": "(s, r) => r * Math.cos(Math.PI / 2 + 2 * Math.PI * s / 490)",
    "PY": "(s, r) => r * Math.sin(Math.PI / 2 + 2 * Math.PI * s / 490)",
    # 甲、乙的位置（s 累计，不取模：转几圈就加几个 490）
    "SJ": "(m) => m <= %r ? 6 * m : 240 + 7.5 * (m - %r)" % (T1f, T1f),
    "SY": "(m) => m <= %r ? 440 - 5 * m : (m <= %r ? 240 + 6 * (m - %r) : 440 + 6 * (m - %r))" % (T1f, T2f, T1f, T2f),
    # 各段轨迹的端点
    "J1e": "(m) => Math.min(SJ(m), 240)",
    "J2e": "(m) => m <= %r ? 240 : Math.min(SJ(m), 490)" % T1f,
    "Y1s": "(m) => Math.max(240, 440 - 5 * Math.min(m, %r))" % T1f,
    "Y2e": "(m) => m <= %r ? 240 : Math.min(SY(m), 440)" % T1f,
}


def arc(id_, s0, s1, r, **kw):
    """跑道上从 s0 到 s1 的一段弧（s0、s1 可写表达式）"""
    o = {"id": id_, "type": "pcurve", "fx": "PX(t,%g)" % r, "fy": "PY(t,%g)" % r, "t": [s0, s1], "n": 200}
    o.update(kw)
    return o


def at(s, r):
    return ["PX(%s,%g)" % (s, r), "PY(%s,%g)" % (s, r)]


def txt(id_, pos, text, cls="rd", color="ink", **kw):
    o = {"id": id_, "type": "text", "at": pos, "text": text, "cls": cls, "color": color, "dir": "C"}
    o.update(kw)
    return o


LX = -8.95      # 讲台左侧读数区（左对齐）的 x

objects = [
    # 跑道：浅色跑道带 + 中线
    {"id": "band", "type": "pcurve", "fx": "3*cos(t)", "fy": "3*sin(t)", "t": [0, "2*PI"], "n": 200, "close": True,
     "stroke": "#e6eef0", "width": 58},
    {"id": "track", "type": "pcurve", "fx": "3*cos(t)", "fy": "3*sin(t)", "t": [0, "2*PI"], "n": 240, "close": True,
     "stroke": "ink", "width": 3},
    # A、B 之间的 50 米
    arc("arcAB", 440, 490, 3, stroke="green", width=7, glow=True),
    # 轨迹：实线 = 提速前，虚线 = 提速后
    arc("j1", 0, "J1e(tm)", RJ, stroke="orange", width=6),
    arc("j2", 240, "J2e(tm)", RJ, stroke="orange", width=6, dash=[14, 10]),
    arc("y1", "Y1s(tm)", 440, RY, stroke="blue", width=6),
    arc("y2", 240, "Y2e(tm)", RY2, stroke="blue", width=6, dash=[14, 10]),
    # 追及：甲前方到乙的距离（红）；想一想：甲领先乙的距离（绿）
    arc("gapA", "SJ(tm)", "SY(tm)+490", 3, stroke="hl", width=8, glow=True, n=320),
    arc("lead", "SY(tm)", "SJ(tm)", 3, stroke="green", width=8, glow=True, n=320),
    # 方向箭头：出发时（反向）、相遇后（同向）
    arc("arrJ", 16, 62, 2.12, stroke="orange", width=4, arrow=True, n=60),
    arc("arrY", 424, 378, 3.98, stroke="blue", width=4, arrow=True, n=60),
    arc("arrJ2", 262, 308, 2.12, stroke="orange", width=4, arrow=True, n=60),
    arc("arrY2", 262, 308, 3.98, stroke="blue", width=4, arrow=True, n=60),
    # 定点
    {"id": "ptA", "type": "point", "at": "A", "r": 6},
    {"id": "ptB", "type": "point", "at": "B", "r": 6},
    {"id": "ptP", "type": "point", "at": "P", "r": 7, "fill": "purple"},
    {"id": "lA", "type": "label", "at": "A", "text": "A", "dir": "N", "dist": 52},
    {"id": "lB", "type": "label", "at": "B", "text": "B", "dir": "NE", "dist": 72},
    {"id": "lP", "type": "label", "at": "P", "text": "P", "dir": "N", "dist": 80, "color": "purple"},
    # 两个人：圆点里写名字
    {"id": "J", "type": "point", "at": "J", "r": 20, "fill": "orange"},
    {"id": "Y", "type": "point", "at": "Y", "r": 20, "fill": "blue"},
    txt("tJ", "J", "甲", color="#ffffff", dy=-1),
    txt("tY", "Y", "乙", color="#ffffff", dy=-1),
    # 路程标注
    txt("L50", at(465, 4.08), "50 米", color="green"),
    txt("L440", [0, 0], "两人合跑 440 米", cls="rdl", color="ink"),
    txt("L24", at(120, 1.62), "24 份", color="orange"),
    txt("L25", at(365, 1.62), "25 份", color="orange"),
    txt("L240", at(120, 1.62), "240 米", color="orange"),
    txt("L250", at(365, 1.62), "250 米", color="orange"),
    txt("L200", at(337, 4.62), "200 米", color="blue"),
    # 图例（讲台左侧）
    txt("lg1", [LX, 3.3], "实线：提速前", cls="wt", color="ink", align="left"),
    txt("lg2", [LX, 2.55], "虚线：提速后", cls="wt", color="ink", align="left"),
    # 速度比（讲台左侧）
    txt("tR1", [LX, 0.9], "原速度比 甲∶乙 $=6:5$", cls="rdl", color="ink", align="left"),
    txt("tR2", [LX, -0.5], "提速后 甲∶乙 $=5:4$", cls="rdl", color="red", align="left"),
    # 追及的实时读数
    txt("tGap", [0, 0], "甲要追 {#} 米", cls="rdl", color="red", num="SY(tm)+490-SJ(tm)", digits=0),
    txt("tLead", [0, 0], "甲领先 {#} 米", cls="rdl", color="green", num="SJ(tm)-SY(tm)", digits=0),
    txt("rH3", [LX, 1.3], "追及这一段", cls="wt", color="ink", align="left"),
    txt("rJ3", [LX, 0.3], "甲跑了 {#} 米", cls="rdl", color="orange", align="left", num="max(0,SJ(tm)-490)", digits=0),
    txt("rY3", [LX, -0.95], "乙跑了 {#} 米", cls="rdl", color="blue", align="left", num="max(0,SY(tm)-440)", digits=0),
    txt("rHL", [LX, 1.3], "从 $P$ 点算起", cls="wt", color="ink", align="left"),
    txt("rJL", [LX, 0.3], "甲跑了 {#} 圈", cls="rdl", color="orange", align="left", num="(SJ(tm)-240)/490", digits=1),
    txt("rYL", [LX, -0.95], "乙跑了 {#} 圈", cls="rdl", color="blue", align="left", num="(SY(tm)-240)/490", digits=1),
    txt("tCatch", at(240, 1.3), "追上！", cls="shape", color="red"),
]

PROB_BOX = {"x": 1236, "y": 168, "w": 640, "h": 750}
PROB_VIEW = {"x": [-4.6, 4.6], "y": [-4.6, 4.6]}
BOX = {"x": 70, "y": 150, "w": 1130, "h": 780}
VIEW = {"x": [-9.2, 5.6], "y": [-4.5, 4.5]}


def board(id_, num, title, tag, beats):
    return {"id": id_, "layout": "board", "num": num, "title": title, "tag": tag, "box": BOX, "view": VIEW, "beats": beats}


T2s, T3s = round(T2f, 6), round(T3f, 6)
DOTS = ["J", "Y", "tJ", "tY"]

scenes = [
    {"id": "s0", "layout": "title",
     "beats": [{"say": "环形跑道上，两人先相遇、再追及。甲一共跑了多少米？｜"}]},

    {"id": "s1", "layout": "problem", "num": "题", "title": "读题", "box": PROB_BOX, "view": PROB_VIEW,
     "beats": [
         {"say": "环形跑道，一圈长 490 米。",
          "do": [{"at": "环形跑道", "mark": "k1"}, {"at": "490", "focus": "track", "color": "cyan", "dur": 1.4}]},
         {"say": "A、B 之间的这一小段，长 50 米。",
          "do": [{"at": "^", "mark": "k2"}, {"at": "这一小段", "show": "arcAB"}, {"at": "50", "show": "L50"}]},
         {"say": "甲从 A 出发，乙从 B 出发，两人同时反向跑。",
          "do": [{"at": "甲从", "mark": "k3"}, {"at": "甲从", "show": ["J", "tJ"]}, {"at": "甲从", "show": "arrJ", "delay": 0.3},
                 {"at": "乙从", "show": ["Y", "tY"]}, {"at": "乙从", "show": "arrY", "delay": 0.3}]},
         {"say": "相遇以后，乙立刻转身，和甲同向跑。",
          "do": [{"at": "相遇以后", "mark": "k4"}]},
         {"say": "同时，甲提速 25%，乙提速 20%。",
          "do": [{"at": "甲提速", "mark": "k5"}, {"at": "甲提速", "focus": ["J", "tJ"], "dur": 1.0},
                 {"at": "乙提速", "mark": "k6"}, {"at": "乙提速", "focus": ["Y", "tY"], "dur": 1.0}]},
         {"say": "结果甲跑到 A 时，乙恰好跑到 B。",
          "do": [{"at": "结果", "mark": "k7"}, {"at": "甲跑到", "focus": "lA", "dur": 1.2}, {"at": "乙恰好", "focus": "lB", "dur": 1.2}]},
         {"say": "以后速度和方向都不变。甲追上乙时，一共跑了多少米？｜",
          "do": [{"at": "^", "mark": "k8"}, {"at": "甲追上乙", "mark": "q1"}]},
     ]},

    board("s2", "01", "先看相遇", "第一段", [
        {"say": "先看第一段。两人反向跑，一起跑完跑道的另一边。",
         "do": [{"at": "^", "hide": ["L50"]}, {"at": "^", "show": ["j1", "y1"]},
                {"at": "反向跑", "tween": {"tm": T1f}, "dur": 5.0, "ease": "linear"}]},
        {"say": "两人在这里相遇，记作点 P。",
         "do": [{"at": "点P", "show": ["ptP", "lP"]}, {"at": "点P", "focus": "ptP", "dur": 1.2}]},
        {"say": "两人合起来，跑了 490 减 50，等于 440 米。",
         "do": [{"at": "合起来", "focus": ["j1", "y1"], "dur": 1.6},
                {"at": "490", "note": "两人合跑：$490-50=440$（米）"},
                {"at": "440", "show": "L440"}]},
        {"say": "题目没给速度，P 在哪儿，只能从后面的条件倒推。｜",
         "do": [{"at": "倒推", "note": "点 $P$ 在哪？从后面的条件倒推", "cls": "sub"}]},
    ]),

    board("s3", "02", "相遇以后", "第二段", [
        {"say": "相遇后，乙转身，两人朝同一个方向跑。",
         "do": [{"at": "^", "hide": ["arrJ", "arrY", "L440"]},
                {"at": "乙转身", "show": "arrY2"}, {"at": "同一个方向", "show": "arrJ2"}]},
        {"say": "甲跑回 A 的时候，乙正好跑回 B。",
         "do": [{"at": "^", "show": ["j2", "y2", "lg1", "lg2"]},
                {"at": "甲跑回", "tween": {"tm": T2f}, "dur": 4.5, "ease": "linear"}]},
        {"say": "看乙：从 B 跑到 P，又从 P 原路跑回 B。",
         "do": [{"at": "^", "dim": ["j1", "j2", "J", "tJ"], "to": 0.3},
                {"at": "从B", "focus": "y1", "color": "blue", "dur": 1.4},
                {"at": "原路", "focus": "y2", "color": "blue", "dur": 1.4}]},
        {"say": "去和回，跑的是同一段路，路程相同。",
         "do": [{"at": "同一段路", "note": "乙：去、回跑同一段，路程相同", "cls": "key"}]},
        {"say": "再看甲：从 A 出发，跑了一圈又回到 A。",
         "do": [{"at": "^", "dim": ["j1", "j2", "J", "tJ"], "to": 1}, {"at": "^", "dim": ["y1", "y2", "Y", "tY"], "to": 0.3},
                {"at": "从A", "focus": ["j1", "j2"], "color": "orange", "dur": 2.0}]},
        {"say": "甲前后两段合起来，正好一圈 490 米。",
         "do": [{"at": "合起来", "note": "甲：两段合起来正好一圈 $490$ 米", "cls": "key"}]},
        {"say": "抓住这两点，题目就能解开。｜",
         "do": [{"at": "^", "dim": ["y1", "y2", "Y", "tY"], "to": 1}]},
    ]),

    board("s4", "03", "看乙：去回用时之比", "关键一步", [
        {"say": "先看乙。去和回的路程一样长。",
         "do": [{"at": "^", "hide": ["arrJ2", "arrY2"]}, {"at": "^", "dim": ["j1", "j2", "J", "tJ"], "to": 0.3},
                {"at": "去和回", "focus": ["y1", "y2"], "color": "blue", "dur": 1.6},
                {"at": "一样长", "note": "乙：去、回路程相同"}]},
        {"say": "回来时速度提高 20%，是去时的 1.2 倍。",
         "do": [{"at": "1.2倍", "note": "速度 去∶回 $=1:1.2=5:6$"}]},
        {"say": "路程相同，时间和速度成反比。",
         "do": []},
        {"say": "所以乙去和回的用时之比，是 6 比 5。",
         "do": [{"at": "6比5", "note": "用时 去∶回 $=6:5$", "cls": "key"}]},
        {"say": "甲和乙同时起跑，同时相遇，又同时到点。",
         "do": [{"at": "^", "dim": ["j1", "j2", "J", "tJ"], "to": 1},
                {"at": "同时相遇", "focus": ["j1", "y1"], "dur": 1.2},
                {"at": "同时到点", "focus": ["j2", "y2"], "dur": 1.2},
                {"at": "同时起跑", "note": "甲、乙每段都同时开始、同时结束"}]},
        {"say": "所以甲前后两段的用时之比，也是 6 比 5。",
         "do": [{"at": "也是", "note": "甲：用时 前∶后 $=6:5$", "cls": "key"}]},
    ]),

    board("s5", "04", "看甲：一圈分成 49 份", "关键一步", [
        {"say": "再看甲。前后速度之比是 1 比 1.25，也就是 4 比 5。",
         "do": [{"at": "^", "dim": ["y1", "y2", "Y", "tY"], "to": 0.3},
                {"at": "再看甲", "focus": ["j1", "j2"], "color": "orange", "dur": 1.4},
                {"at": "1比1.25", "note": "甲：速度 前∶后 $=1:1.25=4:5$"}]},
        {"say": "路程等于速度乘时间。",
         "do": []},
        {"say": "前一段 4×6，是 24 份。后一段 5×5，是 25 份。",
         "do": [{"at": "24份", "show": "L24"}, {"at": "25份", "show": "L25"},
                {"at": "前一段", "focus": "j1", "color": "orange", "dur": 1.2},
                {"at": "后一段", "focus": "j2", "color": "orange", "dur": 1.2},
                {"at": "前一段", "note": "路程比 $=(4\\times6):(5\\times5)=24:25$"}]},
        {"say": "两段合起来是一整圈，一共 49 份。",
         "do": [{"at": "一整圈", "focus": ["j1", "j2"], "color": "gold", "dur": 1.6}]},
        {"say": "490 米分成 49 份，1 份就是 10 米。",
         "do": [{"at": "1份", "note": "1 份：$490\\div(24+25)=10$（米）", "cls": "key"}]},
        {"say": "所以甲到 P 跑了 240 米，后一段跑了 250 米。",
         "do": [{"at": "240", "hide": "L24"}, {"at": "240", "show": "L240"},
                {"at": "250", "hide": "L25"}, {"at": "250", "show": "L250"},
                {"at": "240", "note": "甲：前段 $240$ 米，后段 $250$ 米", "cls": "key"}]},
        {"say": "乙去的那段，就是 440 减 240，等于 200 米。",
         "do": [{"at": "^", "dim": ["y1", "y2", "Y", "tY"], "to": 1},
                {"at": "乙去", "focus": "y1", "color": "blue", "dur": 1.4},
                {"at": "200", "show": "L200"},
                {"at": "200", "note": "乙：$440-240=200$（米）"}]},
    ]),

    board("s6", "05", "求速度比", "提速前后", [
        {"say": "同样的时间里，甲跑 240 米，乙跑 200 米。",
         "do": [{"at": "^", "hide": ["lg1", "lg2"]},
                {"at": "甲跑", "focus": ["j1", "L240"], "color": "orange", "dur": 1.3},
                {"at": "乙跑", "focus": ["y1", "L200"], "color": "blue", "dur": 1.3},
                {"at": "同样的时间", "note": "相同时间：甲 $240$ 米，乙 $200$ 米"}]},
        {"say": "所以原来的速度比，甲比乙是 6 比 5。",
         "do": [{"at": "6比5", "note": "原速度比 甲∶乙 $=240:200=6:5$"}, {"at": "6比5", "show": "tR1"}]},
        {"say": "提速以后，甲是 6×1.25，等于 7.5。",
         "do": [{"at": "甲是", "note": "甲：$6\\times1.25=7.5$"}]},
        {"say": "乙是 5×1.2，等于 6。",
         "do": [{"at": "乙是", "note": "乙：$5\\times1.2=6$"}]},
        {"say": "新的速度比是 7.5 比 6，也就是 5 比 4。",
         "do": [{"at": "5比4", "note": "新速度比 甲∶乙 $=7.5:6=5:4$", "cls": "key"}, {"at": "5比4", "show": "tR2"}]},
    ]),

    board("s7", "06", "追及：甲追上乙", "第三段", [
        {"say": "现在甲在 A，乙在 B，两人同向跑。",
         "do": [{"at": "^", "hide": ["j1", "j2", "y1", "y2", "L240", "L250", "L200", "tR1", "arcAB"]},
                {"at": "甲在", "focus": ["J", "tJ"], "dur": 1.0}, {"at": "乙在", "focus": ["Y", "tY"], "dur": 1.0},
                {"at": "同向", "show": ["arrJ2", "arrY2"]},
                {"at": "甲在", "note": "甲在 $A$，乙在 $B$，同向跑"}]},
        {"say": "顺着跑的方向，乙在甲前面多远呢？",
         "do": [{"at": "前面", "show": "gapA", "dur": 1.4}]},
        {"say": "从 A 往前跑到 B，是 490 减 50，440 米。",
         "do": [{"at": "440", "show": "tGap"},
                {"at": "490", "note": "追及路程：$490-50=440$（米）", "cls": "key"}]},
        {"say": "速度比 5 比 4。甲跑 5 份，就比乙多跑 1 份。",
         "do": [{"at": "甲跑", "note": "甲跑 $5$ 份，比乙多跑 $1$ 份"}]},
        {"say": "这 440 米是 1 份，甲跑 5 份，就是 2200 米。",
         "do": [{"at": "2200", "note": "甲：$440\\div(5-4)\\times5=2200$（米）", "cls": "key"}]},
        {"say": "快进看一看，红色这段越来越短，直到追上。",
         "do": [{"at": "^", "hide": ["arrJ2", "arrY2", "tR2"]}, {"at": "^", "show": ["rH3", "rJ3", "rY3"]},
                {"at": "快进", "tween": {"tm": T3f}, "dur": 10.0, "ease": "linear"},
                {"at": "追上", "show": "tCatch", "delay": 0.2}]},
        {"say": "甲这一段正好跑了 2200 米。",
         "do": [{"at": "2200", "focus": "rJ3", "dur": 1.4}]},
        {"say": "再加上前面跑的一整圈，甲一共跑了 2690 米。",
         "do": [{"at": "一整圈", "note": "$490+2200=2690$（米）", "np": "答", "cls": "ans"}]},
    ]),

    board("s8", "07", "方法二：从相遇点 $P$ 看", "方法二", [
        {"say": "换个角度，回到两人相遇的那一刻。",
         "do": [{"at": "^", "hide": ["gapA", "tGap", "rH3", "rJ3", "rY3", "tCatch"]},
                {"at": "回到", "set": {"tm": T1f}}]},
        {"say": "这时两人在同一点 P，朝同一个方向跑。",
         "do": [{"at": "同一点", "focus": ["ptP", "lP"], "color": "purple", "dur": 1.4},
                {"at": "同一个方向", "show": ["arrJ2", "arrY2"]},
                {"at": "同一点", "note": "相遇后：同时、同地（点 $P$）、同向"}]},
        {"say": "从这以后，速度比一直是 5 比 4。",
         "do": [{"at": "5比4", "note": "速度比一直是 $5:4$"}]},
        {"say": "甲要追上乙，就得比乙多跑整整一圈。",
         "do": [{"at": "多跑", "note": "追上 ＝ 甲比乙多跑一圈", "cls": "key"}]},
        {"say": "多跑的一圈是 1 份，甲跑 5 份，也就是 5 圈。",
         "do": [{"at": "5圈", "note": "甲跑 $5$ 圈：$490\\times5=2450$（米）"}]},
        {"say": "快进验证：甲跑 5 圈，乙跑 4 圈，又在 P 碰头。",
         "do": [{"at": "^", "hide": ["arrJ2", "arrY2"]}, {"at": "^", "show": ["rHL", "rJL", "rYL"]},
                {"at": "快进", "tween": {"tm": T3f}, "dur": 10.0, "ease": "linear"},
                {"at": "碰头", "focus": ["ptP", "lP"], "color": "purple", "dur": 1.4}]},
        {"say": "加上相遇前的 240 米，一共 2690 米，答案一样。",
         "do": [{"at": "240", "note": "$240+2450=2690$（米）", "np": "答", "cls": "ans"}]},
    ]),

    board("s9", "08", "想一想", "反思", [
        {"say": "想一想：甲到 A 时，两人只隔 50 米。",
         "do": [{"at": "^", "hide": ["rHL", "rJL", "rYL"] + DOTS, "dur": 0.3},
                {"at": "^", "set": {"tm": T2f}, "delay": 0.35},
                {"at": "^", "show": DOTS, "delay": 0.4},
                {"at": "50", "show": "lead"}]},
        {"say": "为什么追及路程是 440 米，不是 50 米？",
         "do": []},
        {"say": "顺着跑的方向，甲在前，乙在后，甲领先 50 米。",
         "do": [{"at": "甲在前", "show": "tLead"},
                {"at": "甲在前", "note": "甲在前、乙在后：甲领先 $50$ 米"}]},
        {"say": "甲跑得快，领先只会越来越多。",
         "do": [{"at": "越来越多", "tween": {"tm": T3f}, "dur": 9.0, "ease": "linear"}]},
        {"say": "领先满一圈 490 米时，甲正好从后面追上乙。",
         "do": [{"at": "领先满一圈", "note": "领先满一圈 $490$ 米 → 追上", "cls": "key"}]},
        {"say": "所以还要多跑 490 减 50，也就是 440 米。",
         "do": [{"at": "所以", "note": "要多跑 $490-50=440$（米）", "cls": "key"}]},
    ]),

    {"id": "s10", "layout": "summary", "num": "09", "title": "总结",
     "chain": [
         {"id": "c1", "title": "画图定方向", "sub": "相遇：两人\n合跑 $440$ 米"},
         {"id": "c2", "title": "抓不变量", "sub": "乙往返路程同\n甲正好跑一圈"},
         {"id": "c3", "title": "按份数算", "sub": "用时 $6:5$\n路程 $24:25$"},
         {"id": "c4", "title": "求速度比", "sub": "原来 $6:5$\n提速后 $5:4$"},
         {"id": "c5", "title": "追及", "sub": "多跑一圈追上\n追 $440$ 米"},
     ],
     "answers": [
         {"id": "ans1", "text": "甲从 $A$ 跑回 $A$ 是一整圈 $490$ 米，追及又跑了 $2200$ 米。"},
         {"id": "ans2", "text": "甲一共跑了（[[2690]]）米。"},
     ],
     "tagline": "往返看时间，一圈看份数，追上多一圈",
     "beats": [
         {"say": "回顾一下。先画图定方向，相遇时两人合跑 440 米。",
          "do": [{"at": "画图", "show": "c1"}]},
         {"say": "再抓住不变的量：乙往返路程相同，甲正好跑一圈。",
          "do": [{"at": "不变的量", "show": "c2"}]},
         {"say": "用份数算出两段的路程，再求出速度比。",
          "do": [{"at": "份数", "show": "c3"}, {"at": "速度比", "show": "c4"}]},
         {"say": "最后追及，甲比乙多跑一圈才追上。",
          "do": [{"at": "追及", "show": "c5"}, {"at": "多跑一圈", "show": ["ans1", "ans2"], "delay": 0.5}]},
         {"say": "往返看时间，一圈看份数，追上多一圈。｜",
          "do": [{"at": "往返", "show": "tagline"}]},
     ]},

    {"id": "s11", "layout": "outro", "main": "这道题就讲到这里", "sub": "我们下次再见",
     "beats": [{"say": "好，这道题就讲到这里。同学们，我们下次再见！"}]},
]

sb = {
    "meta": {
        "title": "环形跑道上的相遇与追及",
        "tag": "行程问题",
        "subtitle": "相遇后转身提速，甲追上乙时一共跑了多少米？",
        "out": "行程问题_环形跑道相遇与追及.mp4",
        "theme": "light",
        "fps": 30,
    },
    "problem": {
        "tag": "行程问题",
        "width": 1030,
        "size": 34,
        "text": ("如图，在{k1|长为 $490$ 米的环形跑道}上，{k2|$A$、$B$ 两点之间的跑道长 $50$ 米}，甲、乙两人"
                 "{k3|同时从 $A$、$B$ 两点出发反向奔跑}。两人相遇后，{k4|乙立刻转身与甲同向奔跑}，同时"
                 "{k5|甲把速度提高了 $25\\%$}，{k6|乙把速度提高了 $20\\%$}，结果{k7|当甲跑到点 $A$ 时，乙恰好跑到了点 $B$}。"
                 "如果{k8|以后甲、乙的速度和方向都不变}，那么{q1|当甲追上乙时，从一开始算起，甲一共跑了（　　）米}。"),
    },
    "world": {
        "vars": {"tm": 0},
        "view": PROB_VIEW,
        "funcs": FUNCS,
        "points": {
            "A": at(0, 3), "B": at(440, 3), "P": at(240, 3),
            "J": at("SJ(tm)", RJ), "Y": at("SY(tm)", RY),
        },
        "objects": objects,
        "init": ["band", "track", "ptA", "ptB", "lA", "lB"],
    },
    "scenes": scenes,
}

out = HERE / "环形跑道.json"
out.write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
print("写出", out, "（T1=%.4f T2=%.4f T3=%.4f）" % (T1f, T2f, T3f))
