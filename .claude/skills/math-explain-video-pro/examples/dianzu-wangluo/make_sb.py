# -*- coding: utf-8 -*-
"""生成分镜 电阻网络.json（格点、电阻、电流点子多，用脚本写）。改讲解改这里，再跑一遍。

网络：4×4 格点（3×3 个小方格）转 45°，节点 (i,j) 画在 X=i+j−3, Y=j−i；A=(1,1) 左、B=(2,2) 右、C=(1,2) 上、D=(2,1) 下，
中间小方格 ACBD 四边为 r，其余 20 根相等（未知）。
讲法照参考答案：①上下对称 → C、D 等势 → 接电阻无电流 → R′=R；②AB 间相当于 2r、2r、R₀ 三路并联，R₀ 不变 → R″=2rR/(2r−R)。
答案没说"为什么能看成并联"，这里补上：左右对称 → 中线上 C、D 电压恰为一半 → AC、CB 电流相等 → 小方格在 C、D 处与外网不交换电流 → 可拆开。
方法二：1/R=1/r+1/R₀，1/R″=1/(2r)+1/R₀，相减消去 R₀。
演示用的电流（点子速度）按"其余每根也取 r"把整张网精确解出来（numpy），口播点明是演示取值。
变量：fy 上下翻（1→−1）、fo 左右对折（0→1）、sp 小方格在 C、D 处拆开（0→1）、ft 电流点子走的时间。
"""
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 网络与演示电流
NODES = [(i, j) for i in range(4) for j in range(4)]
XY = {(i, j): (i + j - 3, j - i) for i, j in NODES}
NAME = {(1, 1): "A", (2, 2): "B", (1, 2): "C", (2, 1): "D"}
nm = lambda n: NAME.get(n, "n%d%d" % n)
CENTER = {frozenset(((1, 1), (1, 2))), frozenset(((1, 2), (2, 2))), frozenset(((2, 2), (2, 1))), frozenset(((2, 1), (1, 1)))}
EDGES = []
for i, j in NODES:
    for di, dj in ((0, 1), (1, 0)):
        if i + di < 4 and j + dj < 4:
            EDGES.append(((i, j), (i + di, j + dj)))


def solve(rc=1.0, x=1.0):
    idx = {n: k for k, n in enumerate(NODES)}
    L = np.zeros((16, 16))
    for u, v in EDGES:
        g = 1 / (rc if frozenset((u, v)) in CENTER else x)
        a, b = idx[u], idx[v]
        L[a, a] += g; L[b, b] += g; L[a, b] -= g; L[b, a] -= g
    I = np.zeros(16); I[idx[1, 1]] = 1; I[idx[2, 2]] = -1
    V = np.linalg.pinv(L) @ I
    V = V - V[idx[2, 2]]
    Rab = V[idx[1, 1]]
    V = V / Rab                                     # 归一到 U_AB = 1
    cur = {}
    for u, v in EDGES:
        rr = rc if frozenset((u, v)) in CENTER else x
        cur[(u, v)] = (V[idx[u]] - V[idx[v]]) / rr
    return Rab, V, cur


R1, V1, CUR = solve(1.0, 1.0)          # 其余也取 r：R = 5/7 r
R2, _, _ = solve(2.0, 1.0)             # 中间换成 2r：R″ = 10/9 r
R0 = R1 / (1 - R1)                     # rR/(r−R)，r=1
assert abs(R1 - 5 / 7) < 1e-9 and abs(R2 - 10 / 9) < 1e-9 and abs(2 * R1 / (2 - R1) - R2) < 1e-9 and abs(R0 - 2.5) < 1e-9
K = 190                                # 电流 → 点子速度（px/秒）：最大的 AC、CB 约 95 px/秒

# ---------------------------------------------------------------- 世界
FUNCS = {"PX": "(X, fo) => (X < 0 ? X * (1 - 2 * fo) : X)"}


def P(n):
    X, Y = XY[n]
    return ["PX(%d,fo)" % X, "%d*fy" % Y]


points = {nm(n): P(n) for n in NODES}
points["Cs"] = ["0", "fy*(1-0.55*sp)"]            # 小方格自己的 C、D（拆开时往中间收）
points["Ds"] = ["0", "-fy*(1-0.55*sp)"]
SQ = {"C": "Cs", "D": "Ds"}


def ends(u, v):
    if frozenset((u, v)) in CENTER:
        return [SQ.get(nm(u), nm(u)), SQ.get(nm(v), nm(v))]
    return [nm(u), nm(v)]


def rect(x0, x1, y0, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def seg(i, a, b, color="ink", width=2.4, **kw):
    return dict(id=i, type="segment", pts=[a, b], stroke=color, width=width, **kw)


def txt(i, at, text, color="ink", cls="fmb", d="C", dist=0, **kw):
    return dict(id=i, type="text", at=at, text=text, color=color, cls=cls, dir=d, dist=dist, **kw)


OUTER = [(u, v) for u, v in EDGES if frozenset((u, v)) not in CENTER]
SQE = [(u, v) for u, v in EDGES if frozenset((u, v)) in CENTER]
objects = [
    {"id": "shL", "type": "region", "pts": [["PX(-3,fo)", 0], [0, 3], [0, -3]], "fill": "red", "fillOpacity": 0.1},
    {"id": "shR", "type": "region", "pts": [[3, 0], [0, 3], [0, -3]], "fill": "blue", "fillOpacity": 0.1},
]
objects += [seg("o_%s_%s" % (nm(u), nm(v)), *ends(u, v), "ink", 2.4) for u, v in OUTER]
objects += [seg("s_%s_%s" % (nm(u), nm(v)), *ends(u, v), "blue", 4.4) for u, v in SQE]
OUT_IDS = ["o_%s_%s" % (nm(u), nm(v)) for u, v in OUTER]
SQ_IDS = ["s_%s_%s" % (nm(u), nm(v)) for u, v in SQE]
# 最左、最右两个角上的四根：两端是上下对称的两点（等势），演示网里电流为 0（口播要点出来，不能说"每根都有电流"）
ZERO = [(u, v) for (u, v), c in CUR.items() if abs(c) < 1e-9]
CORNER_IDS = ["o_%s_%s" % (nm(u), nm(v)) for u, v in ZERO]
assert len(CORNER_IDS) == 4, ZERO
# 电流点子（每根一条，速度按演示电流）
FLOW_IDS = []
for u, v in EDGES:
    i = "f_%s_%s" % (nm(u), nm(v))
    FLOW_IDS.append(i)
    objects.append(seg(i, *ends(u, v), "orange", 7, dash=[0.1, 17], flow="ft*%.3f" % (CUR[(u, v)] * K), opacity=0.9))
objects += [
    # C、D 之间接的电阻（第 1 问）
    seg("cdW1", "Cs", [0, 0.34], "purple", 2.6), seg("cdW2", [0, -0.34], "Ds", "purple", 2.6),
    {"id": "cdBox", "type": "polygon", "pts": rect(-0.15, 0.15, -0.34, 0.34), "stroke": "purple", "width": 3, "fill": "paper", "fillOpacity": 1},
    txt("cdL", [-0.43, 0], "$R$", "purple"),
    seg("f_cd", "Cs", "Ds", "orange", 7, dash=[0.1, 17], flow="0", opacity=0.5),
    txt("cdI", [0.52, 0], "$I=0$", "red", "fms"),
    # 中线、对折说明
    seg("midL", [0, 3.45], [0, -3.45], "gray", 2.2, dash=[9, 8]),
    txt("dropL", [-1.75, -3.62], "$A$ 到竖线：降 $\\dfrac U2$", "red", "wt"),
    txt("dropR", [1.75, -3.62], "竖线到 $B$：降 $\\dfrac U2$", "blue", "wt"),
    txt("uC", [0, 2.05], "$\\dfrac U2$", "red", "fm"), txt("uD", [0, -2.05], "$\\dfrac U2$", "red", "fm"),
    txt("i1a", ["(px('A')+px('Cs'))/2*0.52", "(py('A')+py('Cs'))/2*0.52"], "$I_1$", "orange"),
    txt("i1b", ["(px('B')+px('Cs'))/2*0.52", "(py('B')+py('Cs'))/2*0.52"], "$I_1$", "orange"),
    # 电流进出
    {"id": "arIn", "type": "arrow", "from": [-2.78, 0], "to": [-1.55, 0], "stroke": "orange", "width": 3.4},
    {"id": "arOut", "type": "arrow", "from": [1.55, 0], "to": [2.78, 0], "stroke": "orange", "width": 3.4},
    txt("lIn", [-2.17, 0.3], "电流进", "orange", "wt"), txt("lOut", [2.17, 0.3], "电流出", "orange", "wt"),
    txt("demo", [-4.25, -3.95], "演示：其余每根也取 $r$", "gray", "wt", align="left"),
    txt("legend", [0, -3.62], "其余各边：阻值相等，未知", "gray", "wt"),
]
# 中间四根的 r 标注（放在小方格外侧）
for a, b, i in (("A", "Cs", "rAC"), ("Cs", "B", "rCB"), ("B", "Ds", "rBD"), ("Ds", "A", "rDA")):
    objects.append(txt(i, ["(px('%s')+px('%s'))/2*1.36" % (a, b), "(py('%s')+py('%s'))/2*1.36" % (a, b)], "$r$", "blue"))
R_IDS = ["rAC", "rCB", "rBD", "rDA"]
objects += [
    {"id": "pA", "type": "point", "at": "A", "r": 7, "fill": "ink"}, {"id": "pB", "type": "point", "at": "B", "r": 7, "fill": "ink"},
    {"id": "pC", "type": "point", "at": "Cs", "r": 7, "fill": "ink"}, {"id": "pD", "type": "point", "at": "Ds", "r": 7, "fill": "ink"},
    {"id": "pC2", "type": "point", "at": "C", "r": 6, "fill": "ink", "hollow": True},
    {"id": "pD2", "type": "point", "at": "D", "r": 6, "fill": "ink", "hollow": True},
    {"id": "lA", "type": "label", "at": "A", "text": "A", "dir": "W"}, {"id": "lB", "type": "label", "at": "B", "text": "B", "dir": "E"},
    {"id": "lC", "type": "label", "at": "Cs", "text": "C", "dir": "N"}, {"id": "lD", "type": "label", "at": "Ds", "text": "D", "dir": "S"},
]

# ---------------------------------------------------------------- 等效电路（世界右边，x 10~18）
def box(i, x0, x1, y, h=0.25, stroke="ink"):
    return dict(id=i, type="polygon", pts=rect(x0, x1, y - h, y + h), stroke=stroke, width=2.6, fill="paper", fillOpacity=1)


CIR = []
for y, mid in ((2.2, "C"), (0.0, "D")):
    k = "t" if mid == "C" else "m"
    CIR += [seg("e%sw1" % k, [10, y], [11.3, y]), box("e%sb1" % k, 11.3, 12.7, y, stroke="blue"),
            seg("e%sw2" % k, [12.7, y], [15.3, y]), box("e%sb2" % k, 15.3, 16.7, y, stroke="blue"),
            seg("e%sw3" % k, [16.7, y], [18, y]),
            {"id": "e%sP" % k, "type": "point", "at": [14, y], "r": 6, "fill": "ink"},
            {"id": "e%sL" % k, "type": "label", "at": [14, y], "text": mid, "dir": "N" if mid == "C" else "S"},
            txt("e%sr1" % k, [12, y], "$r$", "blue"), txt("e%sr2" % k, [16, y], "$r$", "blue"),
            txt("e%sR1" % k, [12, y], "$2r$", "blue"), txt("e%sR2" % k, [16, y], "$2r$", "blue")]
CIR += [
    seg("ebL", [10, 2.2], [10, -2.2]), seg("ebR", [18, 2.2], [18, -2.2]),
    seg("ebw1", [10, -2.2], [12.3, -2.2]), box("ebB", 12.3, 15.7, -2.2, h=0.42, stroke="gray"), seg("ebw2", [15.7, -2.2], [18, -2.2]),
    txt("ebL0", [14, -2.2], "$R_0$", "ink"), txt("ebCap", [14, -3.02], "外面的整个网络", "gray", "wt"),
    {"id": "eA", "type": "point", "at": [10, 0], "r": 7, "fill": "ink"}, {"id": "eB", "type": "point", "at": [18, 0], "r": 7, "fill": "ink"},
    {"id": "eAL", "type": "label", "at": [10, 0], "text": "A", "dir": "W"}, {"id": "eBL", "type": "label", "at": [18, 0], "text": "B", "dir": "E"},
    txt("eTot", [14, 3.0], "三条支路并联", "red", "wt"),
    # 方法二：上面两条合成一条
    seg("mbL", [10, 1.1], [10, -2.2]), seg("mbR", [18, 1.1], [18, -2.2]),
    seg("mw1", [10, 1.1], [12.8, 1.1]), box("mB", 12.8, 15.2, 1.1, stroke="blue"), seg("mw2", [15.2, 1.1], [18, 1.1]),
    txt("mR1", [14, 1.1], "$r$", "blue"), txt("mR2", [14, 1.1], "$2r$", "blue"),
    txt("mCap1", [14, 1.85], "$2r$ 与 $2r$ 并联", "blue", "wt"), txt("mCap2", [14, 1.85], "$4r$ 与 $4r$ 并联", "blue", "wt"),
]
objects += CIR
CIR_TOP = [o["id"] for o in CIR if o["id"][:2] in ("et", "em")]
CIR_R2 = ["etR1", "etR2", "emR1", "emR2"]
CIR_R1 = ["etr1", "etr2", "emr1", "emr2"]
CIR_BASE = [i for i in CIR_TOP if i not in CIR_R1 + CIR_R2] + CIR_R1 + ["ebL", "ebR", "ebw1", "ebB", "ebw2", "ebL0", "ebCap", "eA", "eB", "eAL", "eBL"]

# 验证读数
objects += [
    txt("vR", [4.0, 1.75], "电脑算：$R\\approx0.714\\,r$", "ink", "rdl", align="left"),
    txt("vR2", [4.0, 0.35], "中间换成 $2r$：$R''\\approx1.111\\,r$", "ink", "rdl", align="left"),
    txt("vF", [4.0, -1.2], "公式 $\\dfrac{2rR}{2r-R}\\approx1.111\\,r$ ✓", "green", "rdl", align="left"),
]

NET = OUT_IDS + SQ_IDS + R_IDS + ["pA", "pB", "pC", "pD", "lA", "lB", "lC", "lD"]
INIT = NET + ["legend"]

V_READ = {"x": [-3.7, 3.7], "y": [-4.1, 3.7]}
V_NET = {"x": [-4.4, 4.4], "y": [-4.25, 3.95]}
V_CIR = {"x": [8.4, 19.6], "y": [-3.65, 3.55]}
V_VER = {"x": [-4.4, 10.6], "y": [-4.3, 3.95]}


def N(note, cls=None, np_=None, **kw):
    d = {"note": note}
    if cls:
        d["cls"] = cls
    if np_:
        d["np"] = np_
    d.update(kw)
    return d


def tw(at, vals, dur, **kw):
    return {"at": at, "tween": vals, "dur": dur, **kw}


def say(s):
    """口播里：〈r〉念"小r"、〈R〉念"大R"（两个字母读音一样，必须说清）"""
    for a, b in (("〈2r〉", "{2r|2小r}"), ("〈4r〉", "{4r|4小r}"), ("〈r〉", "{r|小r}"), ("〈R〉", "{R|大R}")):
        s = s.replace(a, b)
    return s


def B(s, *do, **kw):
    d = {"say": say(s)}
    if do:
        d["do"] = list(do)
    d.update(kw)
    return d


problem = {
    "tag": "电阻网络",
    "size": 31,
    "width": 1100,
    "text": ("（上海第 28 届初中物理竞赛“大同杯”复赛）如图所示的电阻网络中，{k1|$AC$、$CB$、$BD$、$DA$ 四边形的电阻为 $r$}，"
             "{k2|其余各边的电阻都相等，但阻值未知}，{k3|测得 $AB$ 两点之间的总电阻为 $R$}。"
             "{q1|当在 $C$、$D$ 两点之间连接一段阻值为 $R$ 的电阻时，$AB$ 两点之间的总电阻 $R'=$______}；"
             "{q2|若将 $AC$、$CB$、$BD$、$DA$ 四根电阻丝皆换成阻值为 $2r$ 的电阻，则 $AB$ 两点之间的总电阻 $R''=$______}。"),
    "parts": [],
}

S2_OFF = ["cdW1", "cdW2", "cdBox", "cdL", "f_cd", "cdI", "arIn", "arOut", "lIn", "lOut", "demo"] + FLOW_IDS
S3_OFF = ["midL", "shL", "shR", "dropL", "dropR", "uC", "uD", "i1a", "i1b", "pC2", "pD2", "demo"] + FLOW_IDS

scenes = [
    {"id": "s0", "layout": "title", "beats": [
        B("一张网里，大部分电阻都不知道多大，还能求总电阻吗？｜")]},

    {"id": "s1", "layout": "problem", "num": "题", "title": "读题",
     "box": {"x": 1290, "y": 150, "w": 590, "h": 700}, "view": V_READ,
     "beats": [
         B("中间小方格的四条边，AC、CB、BD、DA，电阻都是〈r〉。",
           {"at": "^", "mark": "k1", "dur": 1.0}, {"at": "AC", "focus": SQ_IDS + R_IDS, "color": "blue", "dur": 2.0}),
         B("其余各边的电阻都相等，但不知道是多少。",
           {"at": "^", "mark": "k2"}, {"at": "其余", "focus": OUT_IDS, "color": "gold", "dur": 1.8}),
         B("测得 A、B 两点之间的总电阻是〈R〉。",
           {"at": "^", "mark": "k3"}, {"at": "A、B", "focus": ["pA", "pB", "lA", "lB"], "dur": 1.6}),
         B("第1问：在 C、D 之间再接一个阻值为〈R〉的电阻。AB 间的总电阻变成多少？",
           {"at": "第1问", "mark": "q1", "dur": 1.2}),
         B("第2问：中间四根都换成〈2r〉，AB 间的总电阻又是多少？｜",
           {"at": "第2问", "mark": "q2", "dur": 1.2}),
     ]},

    {"id": "s2", "layout": "board", "num": "01", "title": "接上的电阻里有电流吗？", "tag": "第（1）问", "view": V_NET,
     "beats": [
         B("先看第1问：C、D 之间接上电阻，里面会有电流吗？",
           {"at": "^", "hide": "legend", "dur": 0.3},
           {"at": "接上电阻", "show": ["cdW1", "cdW2", "cdBox", "cdL"], "dur": 0.7}),
         B("这要看 C、D 两点之间有没有电压。",
           {"at": "C、D", "focus": ["pC", "pD", "lC", "lD"], "dur": 1.5}),
         B("电流从 A 流进，从 B 流出。",
           {"at": "流进", "show": ["arIn", "lIn"], "dur": 0.6}, {"at": "流出", "show": ["arOut", "lOut"], "dur": 0.6}),
         B("把整张网沿着 AB 这条线，上下翻过来。",
           {"at": "^", "hide": ["arIn", "arOut", "lIn", "lOut"], "dur": 0.3},
           tw("翻过来", {"fy": -1}, 2.6)),
         B("网还是原来的网，A、B 没动，只是 C 和 D 对调了。",
           {"at": "A、B", "focus": ["lA", "lB"], "dur": 1.2}, {"at": "对调", "focus": ["lC", "lD"], "color": "red", "dur": 1.6}),
         B("翻过来前后一模一样，所以 C、D 电压一样高，是等势点。",
           tw("^", {"fy": 1}, 1.4),
           {"at": "等势点", "note": "上下对称：$C$、$D$ 两点等势", "cls": "key"}),
         B("等势的两点之间没有电压，接上电阻，也没有电流。",
           {"at": "没有电压", "note": "$U_{CD}=0$，接入的电阻中没有电流"}),
         B("这根电阻接不接都一样，所以 {R′=R|R撇等于大R}。",
           {"at": "所以", "note": "$R'=R$", "np": "（1）", "cls": "ans"}),
         B("用动画看一看：电流从 A 流到 B，点子走得越快，电流越大。",
           {"at": "^", "show": ["demo"] + FLOW_IDS + ["f_cd"], "dur": 0.5},
           tw("^", {"ft": 22}, 22, ease="linear", wait=False)),
         B("C、D 之间的这根电阻，点子一动不动，没有电流。",
           {"at": "这根", "focus": ["cdBox", "f_cd"], "color": "red", "dur": 2.0}, {"at": "没有电流", "show": "cdI"}),
         B("再看最左、最右两个角，这四根也没有电流。",
           {"at": "两个角", "focus": CORNER_IDS, "color": "red", "dur": 2.6}),
         B("因为角上这两根连着的两个点，也是上下对称的，电压一样高。",
           {"at": "上下对称", "focus": CORNER_IDS, "color": "red", "dur": 2.0}),
     ]},

    {"id": "s3", "layout": "board", "num": "02", "title": "为什么能看成并联？", "tag": "第（2）问", "view": V_NET,
     "beats": [
         B("再看第2问：中间四根换成〈2r〉，外面的电阻还是不知道。",
           {"at": "^", "hide": S2_OFF, "dur": 0.4}, {"at": "^", "set": {"ft": 0}},
           {"at": "中间四根", "focus": SQ_IDS, "color": "blue", "dur": 1.6}),
         B("办法是，把中间的小方格和外面的网络，分开来算。"),
         B("能分开吗？这次沿着 C、D 这条竖线，左右对折。",
           {"at": "竖线", "show": ["midL", "shL", "shR"], "dur": 0.8}, tw("对折", {"fo": 1}, 2.4)),
         B("左右两半一模一样；电流从左边的 A 进，从右边的 B 出。",
           {"at": "一模一样", "focus": OUT_IDS, "dur": 1.4}, tw("电流", {"fo": 0}, 1.6)),
         B("所以从 A 到竖线降的电压，和从竖线到 B 降的，一样多。",
           {"at": "从A", "show": "dropL"}, {"at": "从竖线", "show": "dropR"}),
         B("所以竖线上的 C、D，电压都正好是一半。",
           {"at": "竖线", "show": ["uC", "uD"]},
           {"at": "一半", "note": "左右对称：$U_{AC}=U_{CB}=\\dfrac U2$"}),
         B("这样一来，AC 和 CB 电压相同、电阻也相同，电流就一样大。",
           {"at": "电流", "show": ["i1a", "i1b"]}, {"at": "电流", "note": "$I_{AC}=I_{CB}=I_1$"}),
         B("从 A 流进 C 的电流，全部从 CB 流走，不往外面分。",
           {"at": "全部", "note": "$C$ 点：小方格与外面不交换电流", "cls": "sm"}),
         B("D 点也一样。那就把小方格在 C、D 两处拆开，电路不变。",
           {"at": "^", "hide": ["dropL", "dropR", "uC", "uD", "i1a", "i1b", "midL", "shL", "shR"], "dur": 0.4},
           {"at": "拆开", "show": ["pC2", "pD2"]}, tw("拆开", {"sp": 1}, 2.4),
           {"at": "拆开", "note": "$D$ 点同理 → 小方格可以拆开"}),
         B("用动画看一看：拆开前后，每根电阻里的电流都一样。",
           tw("^", {"sp": 0}, 1.6), {"at": "^", "show": ["demo"] + FLOW_IDS, "dur": 0.5},
           tw("^", {"ft": 11}, 11, ease="linear", wait=False),
           tw("拆开", {"sp": 1}, 2.6, delay=1.6)),
         B("于是 AB 之间，就是三条支路并联。",
           {"at": "三条", "note": "$AB$ 间：$2r$、$2r$、$R_0$ 三路并联", "cls": "key"}),
     ]},

    {"id": "s4", "layout": "board", "num": "03", "title": "列式求 $R''$", "tag": "第（2）问", "view": V_CIR,
     "beats": [
         B("A、C、B 这条是两个〈r〉串联，共〈2r〉；A、D、B 这条也是〈2r〉。",
           {"at": "^", "show": CIR_BASE, "dur": 0.8},
           {"at": "A、C、B", "focus": [i for i in CIR_TOP if i.startswith("et")], "color": "blue", "dur": 1.6},
           {"at": "A、D、B", "focus": [i for i in CIR_TOP if i.startswith("em")], "color": "blue", "dur": 1.6}),
         B("外面的网络不知道有多复杂，就把它整体设为 R₀。",
           {"at": "整体", "focus": ["ebB", "ebL0"], "dur": 1.6}, {"at": "整体", "show": "eTot"}),
         B("三条支路并联，总电阻是〈R〉，列出式子。",
           {"at": "列出", "note": "$\\dfrac1R=\\dfrac1{2r}+\\dfrac1{2r}+\\dfrac1{R_0}$"}),
         B("解出 {R₀=rR/(r−R)|R零等于 小r减大R 分之 小r大R}。",
           {"at": "解出", "note": "$R_0=\\dfrac{rR}{r-R}$"}),
         B("中间四根换成〈2r〉，这两条支路都变成〈4r〉。",
           {"at": "换成", "hide": CIR_R1, "dur": 0.4}, {"at": "换成", "show": CIR_R2, "delay": 0.3}),
         B("外面一根没动，R₀ 不变；左右对称也还在，照样三路并联。",
           {"at": "不变", "focus": ["ebB", "ebL0"], "color": "green", "dur": 1.6}),
         B("列出式子，把 R₀ 代进去。",
           {"at": "列出", "note": "$\\dfrac1{R''}=\\dfrac1{4r}+\\dfrac1{4r}+\\dfrac1{R_0}$"},
           {"at": "代进", "note": "$R''=\\dfrac{2rR_0}{2r+R_0}$", "cls": "sm"}),
         B("化简得到：{R″=2rR/(2r−R)|R两撇等于 2小r减大R 分之 2小r大R}。",
           {"at": "化简", "note": "$R''=\\dfrac{2rR}{2r-R}$", "np": "（2）", "cls": "ans"}),
     ]},

    {"id": "s5", "layout": "board", "num": "04", "title": "方法二：两式相减", "tag": "第（2）问 · 方法二", "view": V_CIR,
     "beats": [
         B("方法二：其实 R₀ 不用求出来。",
           {"at": "^", "hide": CIR_TOP + CIR_R2 + ["ebL", "ebR", "eTot"], "dur": 0.5},
           {"at": "^", "show": ["mbL", "mbR", "mw1", "mB", "mw2", "mR1"], "dur": 0.6, "delay": 0.4}),
         B("两条〈2r〉并联，合起来就是〈r〉。",
           {"at": "^", "show": "mCap1", "dur": 0.5},
           {"at": "合起来", "note": "$\\dfrac1R=\\dfrac1r+\\dfrac1{R_0}$"}),
         B("换成〈2r〉以后，两条〈4r〉并联，合起来是〈2r〉。",
           {"at": "换成", "hide": ["mR1", "mCap1"], "dur": 0.4}, {"at": "换成", "show": ["mR2", "mCap2"], "delay": 0.3},
           {"at": "合起来", "note": "$\\dfrac1{R''}=\\dfrac1{2r}+\\dfrac1{R_0}$"}),
         B("两个式子一减，R₀ 就消掉了。",
           {"at": "一减", "note": "相减：$\\dfrac1{R''}=\\dfrac1R-\\dfrac1{2r}$", "cls": "key"}),
         B("通分，得到同样的答案。",
           {"at": "通分", "note": "$R''=\\dfrac{2rR}{2r-R}$"}),
     ]},

    {"id": "s6", "layout": "board", "num": "05", "title": "电脑验证 · 想一想", "tag": "反思",
     "beats": [
         B("用电脑验证一下：假如外面每根也是〈r〉，把整张网精确算一遍。",
           {"at": "^", "hide": ["mbL", "mbR", "mw1", "mB", "mw2", "mR2", "mCap2", "ebw1", "ebB", "ebw2", "ebL0", "ebCap", "eA", "eB", "eAL", "eBL"], "dur": 0.4},
           {"at": "^", "set": {"sp": 0, "ft": 0}},
           {"at": "^", "camera": V_VER, "dur": 1.4},
           {"at": "精确", "show": ["demo"] + FLOW_IDS, "dur": 0.5},
           tw("精确", {"ft": 26}, 26, ease="linear", wait=False)),
         B("算出总电阻 {R≈0.714r|大R约等于0.714小r}。",
           {"at": "算出", "show": "vR"}),
         B("中间换成〈2r〉，电脑算出 {R″≈1.111r|R两撇约等于1.111小r}。",
           {"at": "电脑算出", "show": "vR2"}),
         B("代进公式，也是 {1.111r|1.111小r}，对上了。",
           {"at": "代进", "show": "vF"}, {"at": "对上", "focus": "vF", "color": "green", "dur": 1.4}),
         B("想一想：C、D 之间接的不是〈R〉，而是一根导线呢？",
           {"at": "想一想", "note": "想一想：$C$、$D$ 间接导线呢？", "cls": "sub"}),
         B("C、D 等势，接什么都没有电流，总电阻还是〈R〉。｜",
           {"at": "等势", "note": "等势点之间接什么都没有电流，$R'=R$", "cls": "key sm"}),
     ]},

    {"id": "s7", "layout": "summary", "num": "06", "title": "总结",
     "chain": [
         {"id": "c1", "title": "上下对称", "sub": "$C$、$D$ 等势\n接电阻无电流"},
         {"id": "c2", "title": "左右对称", "sub": "竖线上电压一半\n小方格可拆开"},
         {"id": "c3", "title": "整体设未知", "sub": "外面网络\n设为 $R_0$"},
         {"id": "c4", "title": "并联列式", "sub": "$R_0$ 不变\n相减消去 $R_0$"},
     ],
     "answers": [
         {"id": "ans1", "text": "$R'=$[[$R$]]；　$R''=$[[$\\dfrac{2rR}{2r-R}$]]"},
     ],
     "tagline": "看对称，找等势；不知道的，整体设",
     "beats": [
         B("回顾一下：上下对称，C、D 等势，接电阻没有电流。", {"at": "上下", "show": "c1"}),
         B("左右对称，竖线上的电压都是一半，小方格可以拆开。", {"at": "左右", "show": "c2"}),
         B("再把外面的网络，不管多复杂，整体设成 R₀。", {"at": "整体", "show": "c3"}),
         B("三路并联列式，R₀ 不变，两式一减就出答案。",
           {"at": "三路", "show": "c4"}, {"at": "答案", "show": "ans1", "delay": 0.3}),
         B("看对称，找等势；不知道的，整体设。｜", {"at": "^", "show": "tagline"}),
     ]},

    {"id": "s8", "layout": "outro", "main": "这道题就讲到这里", "sub": "我们下次再见",
     "beats": [B("好，这道题就讲到这里。同学们，我们下次再见！")]},
]

sb = {
    "meta": {"title": "一张不知道阻值的电阻网", "tag": "电阻网络 · 竞赛", "subtitle": "对称找等势 · 拆成并联 · 整体设未知",
             "out": "电阻网络_对称与等势.mp4", "theme": "light", "fps": 30},
    "problem": problem,
    "layouts": {"board": {"box": {"x": 70, "y": 140, "w": 1130, "h": 800}}},
    "world": {"vars": {"fy": 1, "fo": 0, "sp": 0, "ft": 0}, "funcs": FUNCS, "view": V_READ, "clip": 6,
              "points": points, "objects": objects, "init": INIT},
    "scenes": scenes,
}
(HERE / "电阻网络.json").write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
print("写好 电阻网络.json：%d 个图元，%d 个场景；演示 R=%.4f r，R″=%.4f r，R₀=%.2f r" % (len(objects), len(scenes), R1, R2, R0))
