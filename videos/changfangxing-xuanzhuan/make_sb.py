# -*- coding: utf-8 -*-
"""生成分镜 长方形旋转体积.json（图元多、显隐多，用脚本写比手写 JSON 稳）。改讲解改这里，再跑一遍。

题：长方形 ABCD，BC=6 厘米，AB=10 厘米，对角线 AC、BD 交于 O。图①涂色部分（上下两个三角形 AOD、BOC）
以 CD 所在直线为轴旋转一周，求扫出的立体图形体积。参考答案：
    1/3×3.14×6²×10 − 1/3×3.14×3²×5×2 = 282.6，282.6×2 = 565.2（立方厘米）

世界坐标 = 厘米：轴 CD 竖直，C=(0,0)、D=(0,10)；长方形在轴左侧，A=(-6,10)、B=(-6,0)、O=(-3,5)。
立体感：变量 ph 是长方形绕轴转过的角度；点 (x,y) 转 ph 后的屏幕坐标 = (x·cos ph, y + 0.3·|x|·sin ph)
（斜二测式的俯视，圆画成扁椭圆，半径 r 的椭圆竖直半轴 0.3r）。ph=0 就是图①的平面图。
先用 Python 把关键数算一遍，分镜里写的每个数都要和它一致（见 check_numbers）。
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAU = 0.3          # 椭圆竖直半轴 / 水平半轴
R_BIG, R_SMALL = 6.0, 3.0
H_ALL, H_SMALL = 10.0, 5.0


def check_numbers():
    """答案与参考答案、与分层积分两种方法对一遍"""
    pi = 3.14
    big = pi * R_BIG ** 2 * H_ALL / 3
    small = pi * R_SMALL ** 2 * H_SMALL / 3
    half = big - 2 * small
    assert abs(big - 376.8) < 1e-9 and abs(2 * small - 94.2) < 1e-9, (big, small)
    assert abs(half - 282.6) < 1e-9 and abs(2 * half - 565.2) < 1e-9
    assert abs(2 * big - 753.6) < 1e-9 and abs((2 * big - 2 * half) - 188.4) < 1e-9
    # 第二种方法：按高度切片。y∈[5,10] 的圆环外半径 0.6y、内半径 0.6(10-y)；下半对称
    n, tot = 200000, 0.0
    for i in range(n):
        y = 5 + 5 * (i + 0.5) / n
        tot += math.pi * ((0.6 * y) ** 2 - (0.6 * (10 - y)) ** 2) * (5 / n)
    assert abs(2 * tot - 180 * math.pi) < 1e-3, tot            # 180π ≈ 565.2（π 取 3.14）
    return half, 2 * half


check_numbers()

# ---------------------------------------------------------------- 世界
POINTS = {
    "A": ["-6*cos(ph)", "10+1.8*sin(ph)"], "B": ["-6*cos(ph)", "1.8*sin(ph)"], "O": ["-3*cos(ph)", "5+0.9*sin(ph)"],
    "C": [0, 0], "D": [0, 10], "F": [0, 5],
    "A0": [-6, 10], "B0": [-6, 0], "O0": [-3, 5], "A2": [6, 10], "B2": [6, 0], "O2": [3, 5],
    "X0": [0, -1.5], "X1": [0, 11.4],
}


def pc(id_, rx, cy, t0, t1, **kw):
    """立体感椭圆（pcurve）：水平半轴 rx，圆心 (0,cy)；t 增大 = 从左边经后侧（上）转到右边，再经前侧（下）回来"""
    o = {"id": id_, "type": "pcurve", "fx": "-%g*cos(t)" % rx, "fy": "%g+%g*sin(t)" % (cy, round(TAU * rx, 3)), "t": [t0, t1], "n": 200}
    o.update(kw)
    return o


OBJECTS = [
    # —— 旋转后的立体（静态，与 ph 无关）
    {"id": "solid", "type": "polygon", "pts": ["A0", "O0", "B0", "B2", "O2", "A2"], "stroke": "blue", "width": 3.2, "fill": "blue", "fillOpacity": 0.26},
    pc("eTop", 6, 10, 0, "2*PI", close=True, stroke="blue", width=3, fill="blue", fillOpacity=0.16),
    {"id": "cavity", "type": "polygon", "pts": ["D", "O0", "C", "O2"], "stroke": "orange", "width": 2.6, "dash": [9, 7], "fill": "paper", "fillOpacity": 1},
    pc("eMidB", 3, 5, 0, "PI", stroke="blue", width=2.6, dash=[8, 7]),
    pc("eMidF", 3, 5, "PI", "2*PI", stroke="blue", width=3),
    pc("eBotB", 6, 0, 0, "PI", stroke="blue", width=2.6, dash=[8, 7]),
    pc("eBotF", 6, 0, "PI", "2*PI", stroke="blue", width=3),
    # —— 补成的大圆锥（轴截面）与上下两个小圆锥（空腔）
    {"id": "bigCone", "type": "polygon", "pts": ["C", "A0", "A2"], "stroke": "orange", "width": 3.2, "fill": "orange", "fillOpacity": 0.12},
    {"id": "dbl", "type": "polygon", "pts": ["D", "O0", "C", "O2"], "stroke": "green", "width": 3, "fill": "green", "fillOpacity": 0.34},
    # —— 平面图①（随 ph 转）
    {"id": "rect", "type": "polygon", "pts": ["A", "B", "C", "D"], "stroke": "ink", "width": 3, "fill": None},
    {"id": "triT", "type": "polygon", "pts": ["A", "O", "D"], "stroke": "blue", "width": 2.6, "fill": "blue", "fillOpacity": 0.36},
    {"id": "triB", "type": "polygon", "pts": ["B", "O", "C"], "stroke": "blue", "width": 2.6, "fill": "blue", "fillOpacity": 0.36},
    {"id": "triADC", "type": "polygon", "pts": ["A", "D", "C"], "stroke": "orange", "width": 3.2, "fill": "orange", "fillOpacity": 0.08},
    {"id": "triDOC", "type": "polygon", "pts": ["D", "O", "C"], "stroke": "green", "width": 3.2, "fill": "green", "fillOpacity": 0.4},
    {"id": "dgAC", "type": "segment", "pts": ["A", "C"], "stroke": "ink", "width": 2.2},
    {"id": "dgBD", "type": "segment", "pts": ["B", "D"], "stroke": "ink", "width": 2.2},
    # —— 点转一圈留下的轨迹（t 从 0 画到 ph）
    pc("trA", 6, 10, 0, "ph", stroke="orange", width=3.6),
    pc("trB", 6, 0, 0, "ph", stroke="orange", width=3.6),
    pc("trO", 3, 5, 0, "ph", stroke="orange", width=3.6),
    # —— 轴
    {"id": "axis", "type": "segment", "pts": ["X0", "X1"], "stroke": "orange", "width": 3, "dash": [12, 8]},
    {"id": "axT", "type": "text", "at": [0.25, 8.6], "text": "旋转轴", "cls": "wt", "color": "orange", "dir": "E"},
    # —— 辅助线与记号
    {"id": "oF", "type": "segment", "pts": ["O0", "F"], "stroke": "ink", "width": 2.4, "dash": [8, 6]},
    {"id": "rtF", "type": "right", "pts": ["O0", "F", "D"], "stroke": "ink", "size": 14},
    {"id": "rtD", "type": "right", "pts": ["A", "D", "C"], "stroke": "orange", "size": 16},
    {"id": "mir", "type": "segment", "pts": [[-6.6, 5], [0.7, 5]], "stroke": "gray", "width": 2.2, "dash": [9, 7]},
    # —— 尺寸
    {"id": "dBC", "type": "dim", "pts": ["B0", "C"], "text": "6 cm", "off": -52, "stroke": "gray", "lcolor": "ink"},
    {"id": "dAB", "type": "dim", "pts": ["B0", "A0"], "text": "10 cm", "off": 58, "loff": 50, "stroke": "gray", "lcolor": "ink"},
    {"id": "dAD", "type": "dim", "pts": ["A0", "D"], "text": "6 cm", "off": -40, "stroke": "orange", "lcolor": "ink"},
    {"id": "dDC", "type": "dim", "pts": ["D", "C"], "text": "10 cm", "off": 0, "loff": 52, "stroke": "orange", "lcolor": "ink"},
    {"id": "dDF", "type": "dim", "pts": ["D", "F"], "text": "5 cm", "off": 62, "stroke": "green", "lcolor": "ink"},
    {"id": "dFC", "type": "dim", "pts": ["F", "C"], "text": "5 cm", "off": 62, "stroke": "ink", "lcolor": "ink"},
    {"id": "dOF", "type": "dim", "pts": ["O0", "F"], "text": "3 cm", "off": -38, "stroke": "green", "lcolor": "ink"},
    # —— 点与标签
    {"id": "pO", "type": "point", "at": "O", "r": 6, "fill": "ink"},
    {"id": "lA", "type": "label", "at": "A", "text": "A", "dir": "NW"},
    {"id": "lB", "type": "label", "at": "B", "text": "B", "dir": "SW"},
    {"id": "lC", "type": "label", "at": "C", "text": "C", "dir": "SE"},
    {"id": "lD", "type": "label", "at": "D", "text": "D", "dir": "NE"},
    {"id": "lO", "type": "label", "at": "O", "text": "O", "dir": "E", "dist": 26},
    {"id": "lF", "type": "label", "at": "F", "text": "F", "dir": "E", "dist": 20},
]
OBJ_IDS = {o["id"] for o in OBJECTS}

FLAT = ["rect", "triT", "triB", "dgAC", "dgBD", "pO", "lA", "lB", "lO"]
SOLID = ["solid", "eTop", "eMidB", "eMidF", "eBotB", "eBotF"]
TRAILS = ["trA", "trB", "trO"]
INIT = ["rect", "lA", "lB", "lC", "lD"]

VIEW_PROB = {"x": [-8.4, 2.7], "y": [-2.2, 12.6]}
VIEW_BOARD = {"x": [-8.0, 8.0], "y": [-2.7, 12.9]}
BOX_PROB = {"x": 1240, "y": 150, "w": 640, "h": 790}
BOX_BOARD = {"x": 70, "y": 140, "w": 1130, "h": 800}
TWO_PI = 6.283185307

# ---------------------------------------------------------------- 显隐跟踪：scene 开头自动补 hide/show，避免上一场景的东西留下来
cur = set(INIT)


def show(ids, at="^", fx=None, dur=None, delay=None):
    ids = [ids] if isinstance(ids, str) else list(ids)
    for i in ids:
        assert i in OBJ_IDS, i
        cur.add(i)
    a = {"at": at, "show": ids if len(ids) > 1 else ids[0]}
    if fx:
        a["fx"] = fx
    if dur:
        a["dur"] = dur
    if delay:
        a["delay"] = delay
    return a


def hide(ids, at="^", dur=None, delay=None):
    ids = [ids] if isinstance(ids, str) else list(ids)
    for i in ids:
        assert i in OBJ_IDS, i
        cur.discard(i)
    a = {"at": at, "hide": ids if len(ids) > 1 else ids[0]}
    if dur:
        a["dur"] = dur
    if delay:
        a["delay"] = delay
    return a


def sync(want, at="^"):
    """场景开头：把可见的图元变成 want（多的淡出、少的淡入）"""
    want = set(want)
    out = []
    gone = sorted(cur - want)
    if gone:
        out.append(hide(gone, at, dur=0.5))
    come = [i for i in OBJECTS_ORDER if i in want - cur]
    if come:
        out.append(show(come, at, fx="fade", dur=0.6))
    return out


OBJECTS_ORDER = [o["id"] for o in OBJECTS]


def focus(ids, at="^", color=None, dur=1.5):
    a = {"at": at, "focus": ids, "dur": dur}
    if color:
        a["color"] = color
    return a


def note(text, at="^", cls=None, np=None, gap=False):
    a = {"at": at, "note": text}
    if cls:
        a["cls"] = cls
    if np:
        a["np"] = np
    if gap:
        a["gap"] = True
    return a


def spin(at="^", dur=6.0):
    return {"at": at, "tween": {"ph": TWO_PI}, "dur": dur, "ease": "linear"}


def beat(say, *do, hold=None):
    b = {"say": say}
    if do:
        b["do"] = [x for grp in do for x in (grp if isinstance(grp, list) else [grp])]
    if hold:
        b["hold"] = hold
    return b


problem = {
    "tag": "旋转体积",
    "text": "如图①，有这样一个{k1|长方形 $ABCD$}，{k2|$BC=6$ 厘米}，{k3|$AB=10$ 厘米}。已知{k4|对角线 $AC$、$BD$ 相交于点 $O$}。"
            "如果图①中的{k5|涂色部分}以{k6|$CD$ 所在的直线为轴}旋转一周，那么涂色部分扫出的立体图形（图②）的{q1|体积是多少立方厘米}？",
    "width": 1090,
    "size": 35,
}

scenes = []

# ============ 标题
scenes.append({"id": "s0", "layout": "title", "beats": [beat("两个三角形转一圈，扫出的立体图形有多大？｜")]})

# ============ 读题
scenes.append({"id": "s1", "layout": "problem", "num": "题", "title": "读题", "box": BOX_PROB, "view": VIEW_PROB, "beats": [
    beat("长方形 ABCD，BC 长 6 厘米，AB 长 10 厘米。",
         {"at": "长方形", "mark": "k1"}, {"at": "长方形", "focus": "rect", "color": "blue", "dur": 1.2},
         {"at": "6厘米", "mark": "k2"}, show("dBC", "6厘米"),
         {"at": "10厘米", "mark": "k3"}, show("dAB", "10厘米")),
    beat("对角线 AC、BD 相交于点 O。",
         {"at": "对角线", "mark": "k4"}, show(["dgAC", "dgBD"], "对角线"), show(["pO", "lO"], "点O")),
    beat("图中涂色的，是上下两个三角形。",
         {"at": "涂色", "mark": "k5"}, show(["triT", "triB"], "涂色", fx="fade", dur=0.8)),
    beat("它们以 CD 所在的直线为轴，转一周。",
         {"at": "CD", "mark": "k6"}, show(["axis", "axT"], "CD所在", fx="draw", dur=0.9)),
    beat("转出来的立体图形，体积是多少立方厘米？｜",
         {"at": "体积", "mark": "q1"}),
]})

# ============ 01 转起来看一看
WANT = set(FLAT) | {"axis", "lC", "lD"}
cur_after_s1 = None
b = []
b.append(beat("先让它转起来，看看会扫出什么。",
              hide(["dBC", "dAB", "axT"], dur=0.5),
              show(TRAILS, "转起来", fx="fade", dur=0.3),
              spin("转起来", 6.5),
              note("涂色部分绕 $CD$ 转一周")))
b.append(beat("点 A 转一圈，画出一个大圆。", focus("trA", "大圆", "orange", 1.6)))
b.append(beat("点 B 转一圈，也画出一个大圆。", focus("trB", "大圆", "orange", 1.6)))
b.append(beat("点 O 转一圈，画出一个小圆。", focus("trO", "小圆", "orange", 1.6)))
b.append(beat("两个三角形扫过的地方，像一个沙漏。",
              hide(TRAILS, "沙漏", dur=0.6),
              hide([x for x in FLAT if x not in ("lC", "lD")], "沙漏", dur=0.6),
              show(SOLID, "沙漏", fx="fade", dur=0.9),
              note("扫出的立体图形：像沙漏", "沙漏")))
b.append(beat("不过，它的中间是空的。",
              show("cavity", "空的", fx="fade", dur=0.8), focus("cavity", "空的", "orange", 1.8),
              note("中间有一个空腔", "空的", "key")))
b.append(beat("求体积的时候，这个空腔要减掉。"))
scenes.append({"id": "s2", "layout": "board", "num": "01", "title": "转一周，扫出什么", "tag": "旋转体", "view": VIEW_BOARD, "beats": b})

# ============ 02 补成大三角形
b = []
b.append(beat("先看上面的三角形 AOD，它不好直接算。",
              hide(SOLID + ["cavity"], dur=0.5),
              sync(set(FLAT) | {"axis", "lC", "lD"}),
              {"at": "^", "set": {"ph": 0}, "delay": 0.7},
              {"at": "AOD", "dim": ["triB", "dgBD"], "to": 0.25},
              focus("triT", "AOD", "blue", 1.6)))
b.append(beat("我们把它补成大三角形 ADC。",
              show("triADC", "补成", fx="fade", dur=0.9),
              note("补成大三角形 $ADC$", "补成")))
b.append(beat("补上去的，是三角形 DOC。",
              show("triDOC", "DOC", fx="fade", dur=0.8), focus("triDOC", "DOC", "green", 1.6),
              note("补上的是 $\\triangle DOC$", "DOC")))
b.append(beat("AD 垂直于 CD，让大三角形 ADC 绕 CD 转一周。",
              show("rtD", "垂直", fx="fade", dur=0.5),
              show("trA", "转一周", fx="fade", dur=0.3),
              spin("转一周", 5.5)))
b.append(beat("转出来的，是一个大圆锥。",
              hide("trA", "大圆锥", dur=0.5),
              show(["bigCone", "eTop"], "大圆锥", fx="fade", dur=0.9),
              note("$\\triangle ADC$ 转一周 → 大圆锥", "大圆锥")))
b.append(beat("它的底面半径 AD 是 6 厘米，高 CD 是 10 厘米。",
              show("dAD", "半径", fx="draw", dur=0.8), show("dDC", "高", fx="draw", dur=0.8),
              note("大圆锥：半径 $6$，高 $10$（厘米）", "6厘米")))
b.append(beat("补上去的三角形 DOC，转出来是上下两个小圆锥。",
              show(["dbl", "eMidB", "eMidF"], "小圆锥", fx="fade", dur=0.9),
              focus("dbl", "小圆锥", "green", 1.6),
              note("$\\triangle DOC$ 转一周 → 两个小圆锥", "小圆锥")))
b.append(beat("上面三角形转出的体积，是大圆锥减两个小圆锥。",
              focus("triT", "大圆锥", "blue", 1.4),
              note("上半部分 ＝ 大圆锥 － 两个小圆锥", "是大圆锥", "key")))
scenes.append({"id": "s3", "layout": "board", "num": "02", "title": "补成大三角形", "tag": "化繁为简", "view": VIEW_BOARD, "beats": b})

# ============ 03 小圆锥的半径和高
b = []
b.append(beat("小圆锥的半径和高，要回到长方形里找。",
              hide(["bigCone", "eTop", "dbl", "eMidB", "eMidF", "dAD", "dDC", "triADC", "rtD"], dur=0.5),
              {"at": "^", "dim": ["triB", "dgBD"], "to": 1},
              note("小圆锥：半径、高？", "^", "sub")))
b.append(beat("对角线的交点 O，是长方形的中心。",
              focus(["pO", "lO"], "中心", "orange", 1.6),
              note("$O$ 是长方形的中心", "中心")))
b.append(beat("过 O 作 CD 的垂线，垂足是 F。",
              show(["oF", "rtF", "lF"], "垂线", fx="draw", dur=0.8)))
b.append(beat("F 是 CD 的中点，DF 是 CD 的一半。",
              show(["dDF", "dFC"], "中点", fx="draw", dur=0.8)))
b.append(beat("10÷2=5，所以高是 5 厘米。",
              focus("dDF", "5", "green", 1.4),
              note("$10\\div2=5$（厘米）", "10")))
b.append(beat("OF 是 BC 的一半，6÷2=3，所以半径是 3 厘米。",
              show("dOF", "OF", fx="draw", dur=0.8), focus("dOF", "半径", "green", 1.4),
              note("$6\\div2=3$（厘米）", "6")))
b.append(beat("每个小圆锥，底面半径 3 厘米，高 5 厘米。",
              note("小圆锥：半径 $3$，高 $5$（厘米）", "半径", "key")))
scenes.append({"id": "s4", "layout": "board", "num": "03", "title": "小圆锥的半径和高", "tag": "找数据", "view": VIEW_BOARD, "beats": b})

# ============ 04 算体积
b = []
b.append(beat("大圆锥：三分之一乘 3.14 乘 6 的平方乘 10。",
              hide(["oF", "rtF", "lF", "dOF", "dDF", "dFC", "triDOC"], dur=0.5),
              show(["bigCone", "eTop"], "大圆锥", fx="fade", dur=0.8),
              focus("bigCone", "大圆锥", "orange", 1.5),
              note("$\\dfrac{1}{3}\\times3.14\\times6^2\\times10$", "大圆锥")))
b.append(beat("小圆锥：三分之一乘 3.14 乘 3 的平方乘 5。一共有两个，所以再乘 2。",
              show(["dbl", "eMidB", "eMidF"], "小圆锥", fx="fade", dur=0.8),
              focus("dbl", "小圆锥", "green", 1.5),
              note("$-\\dfrac{1}{3}\\times3.14\\times3^2\\times5\\times2$", "一共")))
b.append(beat("大圆锥减去两个小圆锥，等于 282.6 立方厘米。",
              note("$=282.6$（立方厘米）", "等于", "key"),
              note("大圆锥 $376.8$，两个小圆锥 $94.2$", "等于", "sub")))
b.append(beat("这是上面的三角形转出来的体积。",
              focus("triT", "上面", "blue", 1.6)))
b.append(beat("下面的三角形 BOC，和它上下对称。",
              show("mir", "对称", fx="draw", dur=0.8), focus("triB", "BOC", "blue", 1.6)))
b.append(beat("它转出来的体积，也是 282.6 立方厘米。"))
b.append(beat("所以再乘 2，282.6×2=565.2 立方厘米。",
              note("$282.6\\times2=565.2$（立方厘米）", "再乘", "key")))
b.append(beat("答：扫出的立体图形，体积是 565.2 立方厘米。",
              note("体积是 $565.2$ 立方厘米", "答", "ans", gap=True)))
scenes.append({"id": "s5", "layout": "board", "num": "04", "title": "算出体积", "tag": "列式计算", "view": VIEW_BOARD, "beats": b})

# ============ 05 想一想
b = []
b.append(beat("想一想：如果忘了减掉空腔，会算成多少？",
              hide(["bigCone", "dbl", "mir"] + FLAT, dur=0.5),
              sync(set(SOLID) | {"axis", "lC", "lD"}),
              show("cavity", "^", fx="fade", dur=0.8, delay=0.2), focus("cavity", "空腔", "orange", 1.8)))
b.append(beat("只算两个大圆锥：376.8×2=753.6。",
              note("不减空腔：$376.8\\times2=753.6$", "只算")))
b.append(beat("两个大圆锥里，都把空腔算成了实心。",
              focus("cavity", "空腔", "orange", 1.8)))
b.append(beat("所以多出两份空腔，94.2×2=188.4。",
              note("多算：$94.2\\times2=188.4$", "多出"),
              note("空腔一定要减掉", "多出", "key")))
scenes.append({"id": "s6", "layout": "board", "num": "05", "title": "想一想", "tag": "反思", "view": VIEW_BOARD, "beats": b})

# ============ 总结
scenes.append({"id": "s7", "layout": "summary", "num": "06", "title": "总结",
               "chain": [
                   {"id": "c1", "title": "补成大三角形", "sub": "$AOD$ 补上 $DOC$"},
                   {"id": "c2", "title": "转出大圆锥", "sub": "半径 $6$，高 $10$"},
                   {"id": "c3", "title": "减去空腔", "sub": "两个小圆锥\n半径 $3$，高 $5$"},
                   {"id": "c4", "title": "上下相同", "sub": "再乘 $2$"}],
               "answers": [{"id": "ans1", "text": "体积是（[[565.2]]）立方厘米。"}],
               "tagline": "旋转体：补成大的，减掉空的",
               "beats": [
                   beat("回顾一下。先把涂色三角形补成大三角形。", {"at": "补成", "show": "c1"}),
                   beat("转成大圆锥，再减去中间的两个小圆锥。", {"at": "大圆锥", "show": "c2"}, {"at": "减去", "show": "c3"}),
                   beat("上下两个一样，所以再乘 2。", {"at": "再乘", "show": "c4"}),
                   beat("最后的答案，是 565.2 立方厘米。", {"at": "565.2", "show": "ans1", "delay": 0.2}),
                   beat("遇到旋转体，就想：补成大的，减掉空的。｜", {"at": "补成", "show": "tagline"}),
               ]})

# ============ 片尾
scenes.append({"id": "s8", "layout": "outro", "main": "这道题就讲到这里", "sub": "我们下次再见",
               "beats": [beat("好，这道题就讲到这里。同学们，我们下次再见！")]})

sb = {
    "meta": {"title": "旋转一周的体积", "tag": "旋转体", "subtitle": "涂色的两个三角形，转一圈会扫出什么？",
             "out": "旋转体_长方形绕边旋转的体积.mp4", "theme": "light", "fps": 30,
             "tts": {"engine": "mai"}},
    "problem": problem,
    "world": {"vars": {"ph": 0}, "view": VIEW_BOARD, "points": POINTS, "objects": OBJECTS, "init": INIT},
    "layouts": {"board": {"box": BOX_BOARD}},
    "scenes": scenes,
}

if __name__ == "__main__":
    out = HERE / "长方形旋转体积.json"
    out.write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
    print("写出", out, "（%d 个场景，%d 个图元）" % (len(scenes), len(OBJECTS)))
