# -*- coding: utf-8 -*-
"""生成分镜 函数压轴.json（点、边、交点都随 t 变，用脚本写）。改讲解改这里，再跑一遍。

题：抛物线 y=x²−2x+c 过 A(−1,0)，交 x 轴于 B、y 轴于 C；P 在直线 BC 上，横坐标 t。
(1) c=−3；(2) t=1 时 H(1+√2,−2)；(3) Q 在 BC 上、P 右上方、PQ=2√2，正方形 PEQF，与抛物线两个交点 M、N，纵坐标和 f。
讲法照参考答案：Q(t+2,t−1)，正方形边长 2；E 在 y=x−1、F 在 y=x−5 上走；J、K、L、T；两个交点时 −2<t<(3+√17)/2；
① 0≤t≤1：f=t²+3t−6，1<t≤3：f=2t−4；② 其余四段，逐段解 f=−11/2，得 t=−3/4、(1−√3)/2、(−3+√11)/2。
帮学生想通的地方（不另起解法）：分段点 = 正方形的某个顶点落在抛物线上的时刻；交点经过顶点，就换到相邻的边。
交点的纵坐标：在横边上取这条边的纵坐标，在竖边上把横坐标代进抛物线（答案每一段就是这么算的）。
世界坐标 = 题目坐标；右边 x≈6.4~13 是 f 随 t 变化的图像（横轴 t：X=8.9+t，纵轴 f：Y=−1+0.55f）；x≈20~31 是解方程的表。
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
S17, S3, S11 = math.sqrt(17), math.sqrt(3), math.sqrt(11)
TJ, TK = (3 - S17) / 2, (3 + S17) / 2
PX0, PY0, PKY = 8.9, -1.0, 0.55                 # f 图像：X = 8.9 + t，Y = −1 + 0.55 f


def PX(t):
    return round(PX0 + t, 4)


def PY(f):
    return round(PY0 + PKY * f, 4)


FUNCS = {
    "IS": "(t) => { const par = x => x * x - 2 * x - 3, e = 1e-9, pts = [];"
          " const add = (x, y) => { for (const p of pts) if (Math.abs(p[0] - x) < 1e-7 && Math.abs(p[1] - y) < 1e-7) return; pts.push([x, y]); };"
          " let y = par(t); if (y >= t - 3 - e && y <= t - 1 + e) add(t, y);"
          " y = par(t + 2); if (y >= t - 3 - e && y <= t - 1 + e) add(t + 2, y);"
          " for (const [yy, d] of [[t - 3, 1 + t], [t - 1, 3 + t]]) if (d >= -e) { const s = Math.sqrt(Math.max(0, d));"
          " for (const x of [1 - s, 1 + s]) if (x >= t - e && x <= t + 2 + e) add(x, yy); }"
          " pts.sort((a, b) => a[0] - b[0]); return pts; }",
    "MX": "(t) => { const p = IS(t); return p.length ? p[0][0] : t + 2; }",
    "MY": "(t) => { const p = IS(t); return p.length ? p[0][1] : t - 1; }",
    "NX": "(t) => { const p = IS(t); return p.length ? p[p.length - 1][0] : t + 2; }",
    "NY": "(t) => { const p = IS(t); return p.length ? p[p.length - 1][1] : t - 1; }",
    "FV": "(t) => { const p = IS(t); return p.length ? p[0][1] + p[p.length - 1][1] : NaN; }",
}

points = {
    "A": [-1, 0], "B": [3, 0], "C": [0, -3], "O": [0, 0], "H": ["1+sqrt(2)", -2],
    "P": ["t", "t-3"], "Q": ["t+2", "t-1"], "E": ["t", "t-1"], "F": ["t+2", "t-3"],
    "J": ["(3-sqrt(17))/2", "(1-sqrt(17))/2"], "K": ["(3+sqrt(17))/2", "(1+sqrt(17))/2"], "L": [1, -4], "T": [2, -3],
    "M": ["MX(t)", "MY(t)"], "N": ["NX(t)", "NY(t)"],
    "G": ["%g+sw" % PX0, "%g+%g*FV(sw)" % (PY0, PKY)],
}


def seg(i, a, b, color="ink", width=2.6, **kw):
    return dict(id=i, type="segment", pts=[a, b], stroke=color, width=width, **kw)


def txt(i, at, text, color="ink", cls="fmb", d="C", dist=0, **kw):
    return dict(id=i, type="text", at=at, text=text, color=color, cls=cls, dir=d, dist=dist, **kw)


def pt(i, at, color="ink", r=6, **kw):
    return dict(id=i, type="point", at=at, r=r, fill=color, **kw)


def lab(i, at, text, d, **kw):
    return dict(id=i, type="label", at=at, text=text, dir=d, repel=False, **kw)


objects = [
    {"id": "sq", "type": "region", "pts": ["P", "F", "Q", "E"], "fill": "purple", "fillOpacity": 0.07},
    {"id": "ax", "type": "axes", "x": ["vx(0)+0.15", "min(vx(1)-0.2,6.1)"], "y": ["max(vy(0)+0.15,-6.1)", "min(vy(1)-0.15,3.25)"],
     "origin": [0, 0], "olabel": ""},
    {"id": "trE", "type": "curve", "fx": "x-1", "x": [-3.1, 4.2], "stroke": "gold", "width": 2.2, "dash": [9, 8]},
    {"id": "trF", "type": "curve", "fx": "x-5", "x": [-1.1, 6.05], "stroke": "green", "width": 2.2, "dash": [9, 8]},
    {"id": "lBC", "type": "curve", "fx": "x-3", "x": [-3.1, 5.9], "stroke": "gray", "width": 2.6},
    {"id": "par", "type": "curve", "fx": "x*x-2*x-3", "x": [-2.3, 4.3], "n": 400, "stroke": "blue", "width": 3.6},
    seg("sPH", "P", "H", "hl", 3.4),
    # 正方形四条边 + 交点所在边的高亮（M 红、N 紫）
    seg("eB", "P", "F", "ink", 3), seg("eT", "E", "Q", "ink", 3), seg("eL", "P", "E", "ink", 3), seg("eR", "Q", "F", "ink", 3),
    seg("mB", "P", "F", "hl", 6, glow=True), seg("mT", "E", "Q", "hl", 6, glow=True),
    seg("mL", "P", "E", "hl", 6, glow=True), seg("mR", "Q", "F", "hl", 6, glow=True),
    seg("nB", "P", "F", "purple", 6, glow=True), seg("nT", "E", "Q", "purple", 6, glow=True),
    seg("nL", "P", "E", "purple", 6, glow=True), seg("nR", "Q", "F", "purple", 6, glow=True),
    seg("sPQ", "P", "Q", "hl", 3.2, dash=[8, 7]),
    txt("l2b", "mid(P,F)", "$2$", "ink", "fmb", "S", 26), txt("l2r", "mid(Q,F)", "$2$", "ink", "fmb", "E", 24),
    txt("lPQ", "mid(P,Q)", "$2\\sqrt2$", "red", "fm", "NW", 40),
    # 边上的"交点纵坐标怎么求"（讲这两句时先把 M、N 藏起来，免得标签打架）
    txt("vB", "mid(P,F)", "$y=t-3$", "hl", "fm", "S", 30), txt("vT", "mid(E,Q)", "$y=t-1$", "hl", "fm", "N", 30),
    txt("vL", "mid(P,E)", "$x=t$", "purple", "fm", "W", 56), txt("vR", "mid(Q,F)", "$x=t+2$", "purple", "fm", "E", 74),
    # 点
    pt("pA", "A"), pt("pB", "B"), pt("pC", "C"), pt("pH", "H", "hl", 7),
    pt("pP", "P", "ink", 7), pt("pQ", "Q", "ink", 7), pt("pE", "E", "gold", 7), pt("pF", "F", "green", 7),
    pt("pJ", "J", "gold", 7), pt("pK", "K", "gold", 7), pt("pL", "L", "green", 7), pt("pT", "T", "green", 7),
    pt("pM", "M", "hl", 9), pt("pN", "N", "purple", 9),
    lab("lA", "A", "A", "NW"), lab("lB", "B", "B", "SE"), lab("lC", "C", "C", "W"), lab("lO", "O", "O", "SW"),
    lab("lH", "H", "H", "SE"), lab("lP", "P", "P", "SW"), lab("lQ", "Q", "Q", "E"),
    lab("lE", "E", "E", "NW"), lab("lF", "F", "F", "SE"),
    lab("lJ", "J", "J", "W"), lab("lK", "K", "K", "SE"), lab("lL", "L", "L", "S"), lab("lT", "T", "T", "E"),
    lab("lM", "M", "M", "NW", color="red"), lab("lN", "N", "N", "NE", color="purple"),
    # M 在上边、紧挨着 E 时（第 5 段 t=−0.8），NW 的 M 会叠在 E 上：这一拍换成放右上的这个
    lab("lM2", "M", "M", "NE", color="red"),
    # 两条虚线的名字放在带子外侧（正方形只在两条虚线之间走）。F 的字母也在带子外侧、离线约 28 像素，
    # 所以 y=x−5 的名字要离线更远（字框最近的角离线 ≥45 像素），否则 F 经过时会被盖住（9-30 成片 s3 里 F 被压住）
    txt("tE", [1.85, 2.35], "$y=x-1$", "gold", "fm"), txt("tF", [3.85, -2.85], "$y=x-5$", "green", "fm"),
    txt("tBC", [5.25, 1.75], "$y=x-3$", "ink", "fm"),
    txt("rdT", [6.55, 3.0], "$t=$ {#}", "ink", "rdl", align="left", num="t", digits=2),
    txt("rdF", [6.55, 2.25], "$f=$ {#}", "purple", "rdl", align="left", num="FV(t)", digits=2),
]
# ---- f 随 t 变化的图像（右边一块）
objects += [
    {"id": "axP", "type": "axes", "x": [PX(-2.5), PX(4.15)], "y": [PY(-7.3), PY(6.5)], "origin": [PX(0), PY(0)],
     "xlabel": "$t$", "ylabel": "$f$", "olabel": "$O$"},
    {"id": "tkPt", "type": "ticks", "axis": "x", "on": PY(0), "at": [PX(v) for v in (-2, -1, 1, 2, 3)], "labels": ["$-2$", "$-1$", "$1$", "$2$", "$3$"]},
    {"id": "tkPf", "type": "ticks", "axis": "y", "on": PX(0), "at": [PY(v) for v in (-6, -4, -2, 2, 4)], "labels": ["$-6$", "$-4$", "$-2$", "$2$", "$4$"]},
    {"id": "fG", "type": "curve", "fx": "%g+%g*FV(x-%g)" % (PY0, PKY, PX0), "x": [PX(-1.9995), "%g+sw" % PX0], "n": 900, "stroke": "purple", "width": 3.6},
    pt("pG", "G", "purple", 8),
    seg("lf", [PX(-2.4), PY(-5.5)], [PX(4.0), PY(-5.5)], "hl", 2.6, dash=[9, 7]),
    txt("lfL", [PX(4.05), PY(-5.5)], "$f=-\\dfrac{11}{2}$", "red", "fm", "E", 70),
]
# 推近后三个解的标签：各放在曲线不经过的那一侧（左上/左下/右下），不压曲线、不压纵轴
SOLS = [(-0.75, "$-\\dfrac34$", "NW", 60), ((1 - S3) / 2, "$\\dfrac{1-\\sqrt3}{2}$", "SW", 75),
        ((-3 + S11) / 2, "$\\dfrac{-3+\\sqrt{11}}{2}$", "SE", 95)]
for k, (tv, tx, d, dist) in enumerate(SOLS):
    objects.append(pt("s%d" % k, [PX(tv), PY(-5.5)], "hl", 8))
    objects.append(txt("sl%d" % k, [PX(tv), PY(-5.5)], tx, "red", "fm", d, dist))
# 推近后横线原来的名字在画面外，另放一个
objects.append(txt("lfZ", [PX(1.0), PY(-5.5)], "$f=-\\dfrac{11}{2}$", "red", "fm", "N", 45))
# ---- 解方程的表（x≈20~31）
ROWS = [
    ("$-2<t\\le-1$", "$t^2+3t-4=-\\dfrac{11}{2}$", "$t=\\dfrac{-3\\pm\\sqrt3}{2}$", "舍去", "red"),
    ("$-1<t\\le\\dfrac{3-\\sqrt{17}}{2}$", "$2t-4=-\\dfrac{11}{2}$", "$t=-\\dfrac34$", "✓", "green"),
    ("$\\dfrac{3-\\sqrt{17}}{2}<t<0$", "$t^2-t-6=-\\dfrac{11}{2}$", "$t=\\dfrac{1\\pm\\sqrt3}{2}$", "取 $\\dfrac{1-\\sqrt3}{2}$", "green"),
    ("$0\\le t\\le1$", "$t^2+3t-6=-\\dfrac{11}{2}$", "$t=\\dfrac{-3\\pm\\sqrt{11}}{2}$", "取 $\\dfrac{-3+\\sqrt{11}}{2}$", "green"),
    ("$1<t\\le3$", "$2t-4=-\\dfrac{11}{2}$", "$t=-\\dfrac34$", "舍去", "red"),
    ("$3<t<\\dfrac{3+\\sqrt{17}}{2}$", "$t^2-t-4=-\\dfrac{11}{2}$", "$\\Delta<0$", "无解", "red"),
]
TX = (19.9, 22.9, 26.4, 30.3)
objects += [txt("th%d" % k, [x + (0 if k < 3 else 0), 4.05], h, "gray", "wt", align="left" if k < 3 else None)
            for k, (x, h) in enumerate(zip(TX, ("分段", "列方程", "解", "检验")))]
for r, (a, b, c, v, col) in enumerate(ROWS):
    y = 3.1 - 1.05 * r
    objects += [txt("r%da" % r, [TX[0], y], a, "ink", "fmb", align="left"), txt("r%db" % r, [TX[1], y], b, "ink", "fmb", align="left"),
                txt("r%dc" % r, [TX[2], y], c, "ink", "fmb", align="left"), txt("r%dd" % r, [TX[3], y], v, col, "wt")]
# 这个场景不要板书面板（表格占满全宽），答案写在表格下面
objects.append(txt("ansT", [25.65, -3.35], "② $t=-\\dfrac34$ 或 $\\dfrac{1-\\sqrt3}{2}$ 或 $\\dfrac{-3+\\sqrt{11}}{2}$", "teal", "fmbox"))

INIT = ["ax", "par", "lBC", "pA", "pB", "pC", "lA", "lB", "lC", "lO", "pP", "lP", "pH", "lH", "sPH"]
SQUARE = ["sq", "eB", "eT", "eL", "eR"]
HILITE = ["mB", "mT", "mL", "mR", "nB", "nT", "nL", "nR"]
MN = ["pM", "pN", "lM", "lN"]
# 最后推近看 f 图像时，左边的几何图会露出一截：一起淡掉
ZOOM_HIDE = ["ax", "rdT", "rdF", "par", "lBC", "trE", "trF", "pA", "pB", "pC", "lA", "lB", "lC", "lO",
             "pP", "pQ", "pE", "pF", "lP", "lQ", "lE", "lF"] + SQUARE + MN

NARROW = {"x": 70, "y": 140, "w": 830, "h": 800}      # 图框收窄，板书面板加宽（公式长）
WIDE_NOTES = {"x": 930, "w": 922}
FULL = {"x": 70, "y": 140, "w": 1780, "h": 800}       # 不要板书面板，图占满全宽
V_READ = {"x": [-2.3, 4.4], "y": [-4.8, 3.0]}
V_12 = {"x": [-2.5, 4.6], "y": [-4.9, 3.0]}
V_GEO = {"x": [-3.3, 6.4], "y": [-6.3, 3.4]}
V_SWEEP = {"x": [-3.2, 13.4], "y": [-6.3, 3.4]}
V_ZOOM = {"x": [PX(-1.5), PX(1.3)], "y": [PY(-6.9), PY(-4.2)]}     # 只看三个解附近，标签才摆得开
V_TAB = {"x": [19.6, 31.7], "y": [-4.6, 4.5]}


def tw(at, vals, dur, **kw):
    return {"at": at, "tween": vals, "dur": dur, **kw}


def B(s, *do, **kw):
    d = {"say": s}
    if do:
        d["do"] = list(do)
    d.update(kw)
    return d


R = {  # 口播读法：{显示|读法}
    "par": "{y=x²−2x−3|y 等于 x平方 减 2x 减 3}",
    "tJK": "{(3±√17)/2|2分之 3加减根号17}",
    "tK": "{(3+√17)/2|2分之 3加根号17}",
    "tJ": "{(3−√17)/2|2分之 3减根号17}",
    "s2": "{(1−√3)/2|2分之 1减根号3}",
    "s3": "{(−3+√11)/2|2分之 负3加根号11}",
}

problem = {
    "tag": "二次函数 · 压轴",
    "size": 29,
    "width": 1080,
    "text": ("{k1|抛物线 $y=x^2-2x+c$ 与 $x$ 轴交于点 $A(-1,0)$ 和点 $B$，与 $y$ 轴交于点 $C$}．{k2|点 $P$ 在直线 $BC$ 上，设点 $P$ 的横坐标为 $t$}．"),
    "parts": [
        "（1）{q1|求 $c$ 的值}；",
        "（2）如图 1，{q2|点 $H$ 是抛物线上位于第四象限的点，$PH$ 平行于 $x$ 轴．当 $t=1$ 时，求点 $H$ 的坐标}；",
        "（3）{q3|点 $Q$ 在直线 $BC$ 上且位于点 $P$ 的右上方，$PQ=2\\sqrt2$}．{q4|过点 $P$，$Q$ 分别作 $x$ 轴和 $y$ 轴的垂线，四条垂线围成四边形 $PEQF$}．"
        "{q5|若四边形 $PEQF$ 的边与抛物线有两个交点 $M$，$N$，记 $M$，$N$ 的纵坐标之和为 $f$}．",
        "　①{q6|当点 $P$ 在线段 $BC$ 上时，求 $f$ 关于 $t$ 的函数解析式}；",
        "　②{q7|当 $f=-\\dfrac{11}{2}$ 时，直接写出 $t$ 的值}．",
    ],
}

GEO12 = ["pP", "lP", "pH", "lH", "sPH"]

scenes = [
    {"id": "s0", "layout": "title", "beats": [B("一个正方形沿着直线滑过抛物线，交点怎么变？｜")]},

    {"id": "s1", "layout": "problem", "num": "题", "title": "读题",
     "box": {"x": 1290, "y": 150, "w": 590, "h": 700}, "view": V_READ,
     "beats": [
         B("抛物线 {y=x²−2x+c|y 等于 x平方 减 2x 加 c} 经过点 {A(−1,0)|A 负1 逗号 0}。它与坐标轴交于 B、C。",
           {"at": "^", "mark": "k1", "dur": 1.2}, {"at": "经过", "focus": ["pA", "lA"], "dur": 1.2}),
         B("点 P 在直线 BC 上，横坐标是 t。", {"at": "^", "mark": "k2"}, {"at": "P", "focus": ["pP", "lP"], "dur": 1.4}),
         B("第1问求 c；第2问，t=1 时，求 H 的坐标。", {"at": "第1问", "mark": "q1"}, {"at": "第2问", "mark": "q2", "dur": 1.0},
           {"at": "H", "focus": ["sPH", "pH"], "dur": 1.4}),
         B("第3问，Q 也在 BC 上，在 P 的右上方，PQ=2√2。", {"at": "^", "mark": "q3"}),
         B("过 P、Q 作两条轴的垂线，围成四边形 PEQF。", {"at": "^", "mark": "q4", "dur": 1.0}),
         B("它的边和抛物线交于 M、N 两点，纵坐标之和记为 f。", {"at": "^", "mark": "q5", "dur": 1.0}),
         B("先求 P 在线段 BC 上时，f 的解析式。再求 f 等于 {−11/2|负2分之11} 时 t 的值。｜",
           {"at": "先求", "mark": "q6"}, {"at": "再求", "mark": "q7"}),
     ]},

    {"id": "s2", "layout": "board", "num": "01", "title": "求 $c$ 与点 $H$", "tag": "第（1）（2）问", "view": V_12,
     "beats": [
         B("先看第1问：把点 {A(−1,0)|A 负1 逗号 0} 代入。1+2+c=0，所以 c=−3。",
           {"at": "^", "hide": ["pH", "lH", "sPH"], "dur": 0.4}, {"at": "代入", "focus": ["pA", "lA"], "dur": 1.4},
           {"at": "代入", "note": "代入 $A(-1,0)$：$0=1+2+c$", "cls": "sm"},
           {"at": "所以", "note": "$c=-3$", "np": "（1）", "cls": "ans"}),
         B("抛物线是 %s。令 y=0，得 {B(3,0)|B 3 逗号 0}；令 x=0，得 {C(0,−3)|C 0 逗号 负3}。" % R["par"],
           {"at": "令y=0", "focus": ["pB", "lB"], "dur": 1.3}, {"at": "令x=0", "focus": ["pC", "lC"], "dur": 1.3},
           {"at": "令y=0", "note": "$y=x^2-2x-3$，$B(3,0)$，$C(0,-3)$", "cls": "sm"}),
         B("由 B、C 两点，求出直线 BC：y=x−3。",
           {"at": "直线", "focus": "lBC", "color": "red", "dur": 1.6}, {"at": "直线", "show": "tBC"},
           {"at": "直线", "note": "直线 $BC$：$y=x-3$"}),
         B("第2问，t=1 时，P 的纵坐标是 1−3=−2。P 就是 {(1,−2)|1 逗号 负2}。",
           {"at": "第2问", "focus": ["pP", "lP"], "dur": 1.6}, {"at": "纵坐标", "note": "$t=1$：$P(1,-2)$"}),
         B("PH 平行于 x 轴，H 的纵坐标也是 −2。", {"at": "PH", "show": ["sPH", "pH", "lH"], "dur": 0.8}),
         B("令 {x²−2x−3=−2|x平方 减 2x 减 3 等于 负2}，解得 {x=1±√2|x 等于 1加减根号2}。",
           {"at": "解得", "note": "$x^2-2x-3=-2$，$x=1\\pm\\sqrt2$", "cls": "sm"}),
         B("H 在第四象限，横坐标取正的，H 是 {(1+√2,−2)|1加根号2 逗号 负2}。",
           {"at": "第四象限", "focus": ["pH", "lH"], "dur": 1.6},
           {"at": "横坐标", "note": "$H(1+\\sqrt2,-2)$", "np": "（2）", "cls": "ans"}),
     ]},

    {"id": "s3", "layout": "board", "num": "02", "title": "正方形 $PEQF$ 怎么动", "tag": "第（3）问", "view": V_GEO,
     "box": NARROW, "notes": WIDE_NOTES,
     "beats": [
         B("第3问：P 在直线 BC 上，坐标是 {(t, t−3)|t 逗号 t减3}。",
           {"at": "^", "hide": ["sPH", "pH", "lH", "tBC"], "dur": 0.4}, tw("^", {"t": 0.5}, 1.2),
           {"at": "坐标", "note": "$P(t,t-3)$"}),
         B("设 {Q(a, a−3)|Q a 逗号 a减3}。由 PQ=2√2，得 {(a−t)²+(a−t)²=8|a减t的平方 加 a减t的平方 等于8}。",
           {"at": "^", "note": "设 $Q(a,a-3)$：$(a-t)^2+(a-t)^2=(2\\sqrt2)^2$"}),
         B("Q 在 P 的右上方，a−t=2。所以 Q 是 {(t+2, t−1)|t加2 逗号 t减1}。",
           {"at": "所以", "show": ["pQ", "lQ", "sPQ", "lPQ"], "dur": 0.7},
           {"at": "所以", "note": "$a-t=2$，$Q(t+2,t-1)$"}),
         B("从 P 到 Q，横着走 2，竖着也走 2。PQ 是正方形 PEQF 的对角线，边长是 2。",
           {"at": "横着", "show": ["eB", "l2b"], "dur": 0.7}, {"at": "竖着", "show": ["eR", "l2r"], "dur": 0.7},
           {"at": "对角线", "show": ["eL", "eT", "sq", "pE", "pF", "lE", "lF"], "dur": 0.8},
           {"at": "边长", "note": "$PEQF$ 是边长为 $2$ 的正方形", "cls": "key"}),
         B("E 在 P 的正上方、Q 的正左方，E 是 {(t, t−1)|t 逗号 t减1}；同理 F 是 {(t+2, t−3)|t加2 逗号 t减3}。",
           {"at": "E在", "focus": ["pE", "lE"], "color": "gold", "dur": 1.6}, {"at": "同理", "focus": ["pF", "lF"], "color": "green", "dur": 1.6},
           {"at": "^", "hide": ["sPQ", "lPQ", "l2b", "l2r"], "dur": 0.4},
           {"at": "同理", "note": "$E(t,t-1)$，$F(t+2,t-3)$"}),
         B("E 的纵坐标总比横坐标小 1，E 在直线 y=x−1 上走；F 在直线 y=x−5 上走。",
           {"at": "E在直线", "show": ["trE", "tE"], "dur": 1.0}, {"at": "F在直线", "show": ["trF", "tF"], "dur": 1.0},
           {"at": "F在直线", "note": "$E$ 在 $y=x-1$ 上，$F$ 在 $y=x-5$ 上"}),
         B("t 一变，正方形就沿着 BC 滑，E、F 在两条虚线上走。",
           tw("^", {"t": 2.4}, 2.2), tw("^", {"t": -1.6}, 3.2, delay=2.3), tw("^", {"t": 0.5}, 1.6, delay=5.6)),
     ]},

    {"id": "s4", "layout": "board", "num": "03", "title": "什么时候有两个交点？", "tag": "第（3）问", "view": V_GEO,
     "box": NARROW, "notes": WIDE_NOTES,
     "beats": [
         B("什么时候有两个交点呢？让 t 从小到大，把正方形往右上推。", tw("^", {"t": -2.6}, 1.8)),
         B("开始时，正方形在抛物线外面，没有交点。"),
         B("Q 到达 C，刚好碰到抛物线，这时 t=−2。",
           tw("^", {"t": -2}, 1.4), {"at": "C", "focus": ["pQ", "pC"], "dur": 1.6}, {"at": "这时", "note": "$Q$ 到 $C$：$t=-2$，开始有交点", "cls": "sm"}),
         B("再往右上，就有了两个交点 M、N。", {"at": "^", "show": MN, "dur": 0.4}, tw("^", {"t": -1.2}, 1.6)),
         B("最后离开抛物线的，是左上角 E。E 在直线 y=x−1 上，和抛物线交于 J、K。",
           {"at": "^", "hide": MN, "dur": 0.4}, tw("^", {"t": 2.6}, 3.0), {"at": "J、K", "show": ["pJ", "pK", "lJ", "lK"]}),
         B("令 {x²−2x−3=x−1|x平方 减 2x 减 3 等于 x减1}。解得 J、K 的横坐标是 %s。" % R["tJK"],
           {"at": "解得", "note": "$x^2-2x-3=x-1$，$x=\\dfrac{3\\pm\\sqrt{17}}{2}$", "cls": "sm"}),
         B("E 到 K 时，t=%s，再往后就没有交点了。" % R["tK"],
           tw("^", {"t": TK}, 1.2),
           {"at": "E到K", "focus": ["pE", "pK"], "color": "gold", "dur": 1.6}, tw("再往后", {"t": 3.95}, 0.8)),
         B("所以有两个交点时，−2<t<%s。" % R["tK"],
           tw("^", {"t": 1.6}, 1.6), {"at": "两个交点", "show": MN, "dur": 0.4},
           {"at": "所以", "note": "两个交点：$-2<t<\\dfrac{3+\\sqrt{17}}{2}$", "cls": "key"}),
         B("同样，F 所在的直线 y=x−5，也和抛物线相交。交点是 {L(1,−4)|L 1 逗号 负4} 和 {T(2,−3)|T 2 逗号 负3}。",
           {"at": "F所在", "show": ["pL", "pT", "lL", "lT"]},
           {"at": "交点是", "note": "$y=x-5$ 与抛物线交于 $L(1,-4)$，$T(2,-3)$", "cls": "sm"}),
         B("在这个范围里，只要有一个顶点落到抛物线上，交点就换一条边。",
           tw("^", {"t": 0.62}, 2.0), {"at": "顶点", "show": MN, "dur": 0.4},
           tw("顶点", {"t": 1.4}, 4.2, ease="linear"), {"at": "换一条边", "focus": ["pQ", "lQ"], "dur": 2.0}),
         B("把这些时刻都找出来。Q 到 C 是 t=−2，F 到 L 是 t=−1。E 到 J 是 t=%s。" % R["tJ"],
           {"at": "把这些", "note": "分段点（顶点落在抛物线上）：", "cls": "gap"},
           {"at": "Q到C", "note": "$Q$ 到 $C$：$-2$；$F$ 到 $L$：$-1$；$E$ 到 $J$：$\\dfrac{3-\\sqrt{17}}{2}$", "cls": "sm"}),
         B("P 到 C、F 到 T 都是 t=0；Q 到 B 是 1；P 到 B 是 3；E 到 K 是 %s。" % R["tK"],
           {"at": "P到C", "note": "$P$ 到 $C$、$F$ 到 $T$：$0$；$Q$ 到 $B$：$1$", "cls": "sm"},
           {"at": "P到B", "note": "$P$ 到 $B$：$3$；$E$ 到 $K$：$\\dfrac{3+\\sqrt{17}}{2}$", "cls": "sm"}),
     ]},

    {"id": "s5", "layout": "board", "num": "04", "title": "①求 $f$ 的解析式", "tag": "第（3）问①", "view": V_GEO,
     "box": NARROW, "notes": WIDE_NOTES,
     "beats": [
         B("先做第一小问：P 在线段 BC 上，0≤t≤3。",
           {"at": "^", "hide": ["pJ", "pK", "lJ", "lK", "pL", "pT", "lL", "lT", "tE", "tF"], "dur": 0.4},
           tw("^", {"t": 0.5}, 1.4), {"at": "0≤t≤3", "note": "$P$ 在线段 $BC$ 上：$0\\le t\\le3$"}),
         B("交点的纵坐标怎么求？看它在哪条边上。", {"at": "^", "hide": MN, "dur": 0.4}),
         B("在横着的边上，纵坐标就是这条边的。下边是 t−3，上边是 t−1。",
           {"at": "下边", "show": "vB"}, {"at": "上边", "show": "vT"},
           {"at": "下边", "note": "横边：下边 $y=t-3$，上边 $y=t-1$"}),
         B("在竖着的边上，就把横坐标代进抛物线。左边 x=t，右边 x=t+2。",
           {"at": "左边", "show": "vL"}, {"at": "右边", "show": "vR"},
           {"at": "代进", "note": "竖边：左边 $y=t^2-2t-3$"},
           {"at": "右边", "note": "右边 $y=(t+2)^2-2(t+2)-3=t^2+2t-3$"}),
         B("0≤t≤1 时，Q 还没到 B。M 在下边，N 在右边。",
           {"at": "^", "hide": ["vB", "vT", "vL", "vR"], "dur": 0.4}, {"at": "^", "show": MN, "dur": 0.4, "delay": 0.3},
           {"at": "M在下边", "show": "mB", "dur": 0.5}, {"at": "N在右边", "show": "nR", "dur": 0.5}),
         B("f 等于 t−3 加上 {t²+2t−3|t平方 加 2t 减 3}，就是 {t²+3t−6|t平方 加 3t 减 6}。",
           {"at": "f", "note": "$0\\le t\\le1$：$f=(t-3)+(t^2+2t-3)=t^2+3t-6$"}),
         B("t 过了 1，Q 越过 B，N 从右边换到了上边。",
           {"at": "^", "hide": ["mB", "nR"], "dur": 0.3}, tw("^", {"t": 2.0}, 2.6)),
         B("1<t≤3 时，M 在下边，N 在上边。f 等于 t−3 加 t−1，等于 2t−4。",
           {"at": "M在下边", "show": "mB", "dur": 0.5}, {"at": "N在上边", "show": "nT", "dur": 0.5},
           {"at": "f=", "note": "$1<t\\le3$：$f=(t-3)+(t-1)=2t-4$"}),
         B("这就是第一小问的答案。",
           {"at": "^", "note": "$f=\\begin{cases}t^2+3t-6&(0\\le t\\le1)\\\\2t-4&(1<t\\le3)\\end{cases}$", "np": "①", "cls": "ans sm"}),
     ]},

    {"id": "s6", "layout": "board", "num": "05", "title": "②其余四段", "tag": "第（3）问②", "view": V_GEO,
     "box": NARROW, "notes": WIDE_NOTES,
     "beats": [
         B("第二小问，要在 t 的整个范围里找，还剩四段。",
           {"at": "^", "hide": ["mB", "nT"], "dur": 0.3}, tw("^", {"t": -1.5}, 2.2),
           {"at": "还剩", "note": "横边取纵坐标，竖边代抛物线", "cls": "sub"}),
         B("−2<t≤−1 时，M 在上边，N 在右边。f={t²+3t−4|t平方 加 3t 减 4}。",
           {"at": "M在上边", "show": "mT", "dur": 0.5}, {"at": "N在右边", "show": "nR", "dur": 0.5},
           {"at": "f=", "note": "$-2<t\\le-1$：$f=(t-1)+(t^2+2t-3)=t^2+3t-4$", "cls": "sm"}),
         B("t 过了 −1，F 越过 L，N 换到下边：f=2t−4。",
           {"at": "^", "hide": ["mT", "nR", "lM"], "dur": 0.3}, {"at": "^", "show": "lM2", "dur": 0.3},
           tw("^", {"t": -0.8}, 2.0),
           {"at": "N换到", "show": ["mT", "nB"], "dur": 0.5},
           {"at": "f=", "note": "$-1<t\\le\\dfrac{3-\\sqrt{17}}{2}$：$f=(t-1)+(t-3)=2t-4$", "cls": "sm"}),
         B("E 越过 J 以后，M 换到左边：f={t²−t−6|t平方 减 t 减 6}。",
           {"at": "^", "hide": ["mT", "nB", "lM2"], "dur": 0.3}, {"at": "^", "show": "lM", "dur": 0.3},
           tw("^", {"t": -0.3}, 2.0),
           {"at": "M换到", "show": ["mL", "nB"], "dur": 0.5},
           {"at": "f=", "note": "$\\dfrac{3-\\sqrt{17}}{2}<t<0$：$f=(t^2-2t-3)+(t-3)=t^2-t-6$", "cls": "sm"}),
         B("t 过了 3，P 越过 B，M 换到左边：f={t²−t−4|t平方 减 t 减 4}。",
           {"at": "^", "hide": ["mL", "nB"], "dur": 0.3}, tw("^", {"t": 3.45}, 3.0),
           {"at": "M换到", "show": ["mL", "nT"], "dur": 0.5},
           {"at": "f=", "note": "$3<t<\\dfrac{3+\\sqrt{17}}{2}$：$f=(t^2-2t-3)+(t-1)=t^2-t-4$", "cls": "sm"}),
         B("加上第一小问的两段，一共六段。",
           {"at": "^", "note": "加上①的两段，$f$ 共分六段", "cls": "key"}),
     ]},

    {"id": "s7", "layout": "board", "num": "06", "title": "②解方程 $f=-\\tfrac{11}{2}$", "tag": "第（3）问②", "view": V_TAB,
     "box": FULL, "notes": False,
     "beats": [
         B("令 f 等于 {−11/2|负2分之11}，六段分别解方程。解出来，还要看在不在这一段里。",
           {"at": "^", "hide": ["mL", "nT", "ax"] + MN, "dur": 0.3},
           {"at": "六段", "show": ["th0", "th1", "th2", "th3"]}),
         B("第一段，两个根都不在 −2 到 −1 之间，舍去。", {"at": "^", "show": ["r0a", "r0b", "r0c"]}, {"at": "舍去", "show": "r0d"}),
         B("第二段，t 等于 {−3/4|负4分之3}，在这一段里。", {"at": "^", "show": ["r1a", "r1b", "r1c"]}, {"at": "在这一段", "show": "r1d"}),
         B("第三段，两个根里，只有 %s 在这一段。" % R["s2"], {"at": "^", "show": ["r2a", "r2b", "r2c"]}, {"at": "只有", "show": "r2d"}),
         B("第四段，只有 %s 在 0 到 1 之间。" % R["s3"], {"at": "^", "show": ["r3a", "r3b", "r3c"]}, {"at": "只有", "show": "r3d"}),
         B("第五段，{−3/4|负4分之3} 不在 1 到 3 之间，舍去。", {"at": "^", "show": ["r4a", "r4b", "r4c"]}, {"at": "舍去", "show": "r4d"}),
         B("第六段，判别式小于 0，没有解。", {"at": "^", "show": ["r5a", "r5b", "r5c"]}, {"at": "没有解", "show": "r5d"}),
         B("所以 t 等于 {−3/4|负4分之3}、%s 或 %s。" % (R["s2"], R["s3"]),
           {"at": "^", "show": "ansT", "fx": "pop", "dur": 0.5}),
     ]},

    {"id": "s8", "layout": "board", "num": "07", "title": "动起来看一看", "tag": "验证", "view": V_SWEEP,
     "box": FULL, "notes": False,
     "beats": [
         B("用动画看一看：t 从 −2 往右走。右边同时描出 f 随 t 的变化。",
           {"at": "^", "hide": ["th0", "th1", "th2", "th3", "ansT"] + ["r%d%s" % (r, c) for r in range(6) for c in "abcd"], "dur": 0.3},
           {"at": "^", "set": {"t": -1.9995, "sw": -1.9995}},
           {"at": "^", "show": MN + ["ax", "rdT", "rdF", "axP", "tkPt", "tkPf", "fG", "pG"], "dur": 0.6, "delay": 0.4},
           tw("右边", {"t": -0.45, "sw": -0.45}, 4.2, ease="linear")),    # 停在 −0.56 时 M 正好和 E 重合，两个字母叠在一起
         B("M、N 每经过正方形的一个顶点，就换一条边。", tw("^", {"t": 1.2, "sw": 1.2}, 4.0, ease="linear")),
         B("右边的曲线，就是分成六段的 f，段与段首尾相连。", tw("^", {"t": 3.45, "sw": 3.45}, 3.6, ease="linear")),  # 3.3 时 P 的字母压在 B 上
         B("画上 f 等于 {−11/2|负2分之11} 这条横线，和曲线正好交于三点。",
           tw("^", {"t": TK - 0.0005, "sw": TK - 0.0005}, 0.8, ease="linear"),
           {"at": "横线", "show": ["lf", "lfL"], "dur": 0.8},
           {"at": "三点", "show": ["s0", "s1", "s2"], "dur": 0.4},
           {"at": "三点", "hide": ZOOM_HIDE + ["tkPf", "lfL"], "dur": 0.4},
           {"at": "三点", "camera": V_ZOOM, "dur": 1.4},
           {"at": "三点", "show": "lfZ", "dur": 0.4, "delay": 1.2}),
         B("横坐标就是刚才解出的三个 t。｜", {"at": "^", "show": ["sl0", "sl1", "sl2"], "dur": 0.5}),
     ]},

    {"id": "s9", "layout": "summary", "num": "08", "title": "总结",
     "chain": [
         {"id": "c1", "title": "代点求式", "sub": "$c=-3$\n$BC$：$y=x-3$"},
         {"id": "c2", "title": "设出坐标", "sub": "$P(t,t-3)$\n$Q(t+2,t-1)$"},
         {"id": "c3", "title": "找分段点", "sub": "顶点落在\n抛物线上"},
         {"id": "c4", "title": "分段列式", "sub": "横边取纵坐标\n竖边代抛物线"},
         {"id": "c5", "title": "解后验段", "sub": "解出的 $t$\n要在这一段"},
     ],
     "answers": [
         {"id": "ans1", "text": "（1）$c=$[[$-3$]]；（2）$H$[[$(1+\\sqrt2,-2)$]]"},
         {"id": "ans2", "text": "（3）①[[$f=t^2+3t-6\\ (0\\le t\\le1)$，$f=2t-4\\ (1<t\\le3)$]]"},
         {"id": "ans3", "text": "　　 ②[[$t=-\\dfrac34$ 或 $\\dfrac{1-\\sqrt3}{2}$ 或 $\\dfrac{-3+\\sqrt{11}}{2}$]]"},
     ],
     "tagline": "顶点过抛物线，交点换一条边",
     "beats": [
         B("回顾一下：先代点求出抛物线和直线 BC。", {"at": "代点", "show": "c1"}),
         B("用 t 表示 P、Q，看出 PEQF 是边长为 2 的正方形。", {"at": "用t", "show": "c2"}),
         B("找分段点，就看正方形的顶点什么时候落在抛物线上。", {"at": "分段点", "show": "c3"}),
         B("每一段里，横边上的交点取边的纵坐标。竖边上的交点，代进抛物线。", {"at": "每一段", "show": "c4"}),
         B("解出 t 以后，还要看它在不在这一段里。",
           {"at": "解出", "show": "c5"}, {"at": "这一段", "show": ["ans1", "ans2", "ans3"], "delay": 0.3}),
         B("顶点过抛物线，交点换一条边。｜", {"at": "^", "show": "tagline"}),
     ]},

    {"id": "s10", "layout": "outro", "main": "这道题就讲到这里", "sub": "我们下次再见",
     "beats": [B("好，这道题就讲到这里。同学们，我们下次再见！")]},
]

sb = {
    "meta": {"title": "正方形滑过抛物线", "tag": "二次函数 · 压轴", "subtitle": "求点坐标 · 动点分段 · 逐段解方程",
             "out": "函数压轴_正方形滑过抛物线.mp4", "theme": "light", "fps": 30},
    "problem": problem,
    "layouts": {"board": {"box": {"x": 70, "y": 140, "w": 1130, "h": 800}}},
    "world": {"vars": {"t": 1, "sw": -1.9995}, "funcs": FUNCS, "view": V_READ, "clip": 6,
              "points": points, "objects": objects, "init": INIT},
    "scenes": scenes,
}
(HERE / "函数压轴.json").write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
print("写好 函数压轴.json：%d 个图元，%d 个场景" % (len(objects), len(scenes)))
