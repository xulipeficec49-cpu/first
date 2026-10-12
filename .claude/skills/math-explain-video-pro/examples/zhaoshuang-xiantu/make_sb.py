# -*- coding: utf-8 -*-
"""生成分镜 赵爽弦图.json（点多、四种构形共用一个世界，用脚本写）。改讲解改这里，再跑一遍。

世界坐标以矩形 EFGH 的中心 O 为原点。先在"局部坐标"里把矩形摆得横平竖直：
  E(-w/2,-h/2) F(w/2,-h/2) G(w/2,h/2) H(-w/2,h/2)
  A(-w/2,h/2+q) B(-w/2-p,-h/2) C(w/2,-h/2-q) D(w/2+p,h/2)
  p = BE = DG，q = AH = CF，w = HG，h = HE —— 两对全等 △ABE≌△CDG、△ADH≌△CBF 自动成立，ABCD 自动是平行四边形。
再整体绕 O 转 ah·atan2(q, w+p)：ah=0 矩形横平竖直（课本图①），ah=1 让 AD 水平（课本图②③）。
四种构形：赵爽弦图原图（p=q，w=h，大正方形摆正）→ 图①（第(1)问数据 BE=3，AB=6）→ 图②（一般情形）→ 图③（AH=HE，HG/DG=2）。
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
H1 = 3 * math.sqrt(3) - 3                      # 图①：q+h = AE = 3√3

CFG = {
    "CL": dict(p=3, q=3, h=H1, w=H1, ah=1),         # 赵爽弦图原图
    "F1": dict(p=3, q=3, h=H1, w=3.2, ah=0),        # 图①
    "F2": dict(p=2.4, q=3.0, h=2.16, w=4.8, ah=1),  # 图②
    "F3": dict(p=2.4, q=2.16, h=2.16, w=4.8, ah=1), # 图③：AH=HE，HG/DG=2
}
LOCAL = {"E": ("-w/2", "-h/2"), "F": ("w/2", "-h/2"), "G": ("w/2", "h/2"), "H": ("-w/2", "h/2"),
         "A": ("-w/2", "h/2+q"), "B": ("-w/2-p", "-h/2"), "C": ("w/2", "-h/2-q"), "D": ("w/2+p", "h/2")}


def coords(c):
    """Python 里同样算一遍（定视野用）"""
    p, q, h, w, ah = c["p"], c["q"], c["h"], c["w"], c["ah"]
    a = ah * math.atan2(q, w + p)
    env = dict(p=p, q=q, h=h, w=w)
    out = {}
    for k, (lx, ly) in LOCAL.items():
        x, y = eval(lx, {}, env), eval(ly, {}, env)
        out[k] = (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
    return out


def bbox(c, pad):
    P = coords(c)
    xs, ys = [v[0] for v in P.values()], [v[1] for v in P.values()]
    return {"x": [round(min(xs) - pad[0], 2), round(max(xs) + pad[0], 2)], "y": [round(min(ys) - pad[1], 2), round(max(ys) + pad[1], 2)]}


ANG = "an(q,w,p,ah)"
points = {k: ["rx(%s,%s,%s)" % (lx, ly, ANG), "ry(%s,%s,%s)" % (lx, ly, ANG)] for k, (lx, ly) in LOCAL.items()}
points.update({
    "O": [0, 0],
    "M": ["(px('A')+px('B'))/2", "(py('A')+py('B'))/2"],
    "N": ["(px('A')+px('D'))/2", "(py('A')+py('D'))/2"],
    "K": ["px('N')/2", "py('N')/2"],                               # ON 的中点（AH=HE 时正好在 MD 上）
    "Br": ["rx(px('B'),py('B'),r)", "ry(px('B'),py('B'),r)"],     # △BEO 绕 O 转 r 后的 B、E
    "Er": ["rx(px('E'),py('E'),r)", "ry(px('E'),py('E'),r)"],
})

FUNCS = {
    "rx": "(x, y, a) => x * Math.cos(a) - y * Math.sin(a)",
    "ry": "(x, y, a) => x * Math.sin(a) + y * Math.cos(a)",
    "an": "(q, w, p, ah) => ah * Math.atan2(q, w + p)",
    "dist": "(x1, y1, x2, y2) => Math.hypot(x2 - x1, y2 - y1)",
}

PAIR1, PAIR2 = ["fABE", "fCDG"], ["fADH", "fCBF"]
FILLS = PAIR1 + PAIR2 + ["fRect"]
RIGHTS = ["rE", "rG", "rH", "rF"]


def seg(i, a, b, color="ink", width=2.6, **kw):
    return dict(id=i, type="segment", pts=[a, b], stroke=color, width=width, **kw)


def txt(i, at, text, d="C", dist=28, color="ink", cls="fmb", **kw):
    return dict(id=i, type="text", at=at, text=text, dir=d, dist=dist, color=color, cls=cls, **kw)


objects = [
    # 填色（最底层）
    {"id": "fABE", "type": "region", "pts": ["A", "B", "E"], "fill": "blue", "fillOpacity": 0.2},
    {"id": "fCDG", "type": "region", "pts": ["C", "D", "G"], "fill": "blue", "fillOpacity": 0.2},
    {"id": "fADH", "type": "region", "pts": ["A", "D", "H"], "fill": "blue", "fillOpacity": 0.2},
    {"id": "fCBF", "type": "region", "pts": ["C", "B", "F"], "fill": "blue", "fillOpacity": 0.2},
    {"id": "fRect", "type": "region", "pts": ["E", "F", "G", "H"], "fill": "yellow", "fillOpacity": 0.4},
    {"id": "fABD", "type": "region", "pts": ["A", "B", "D"], "fill": "purple", "fillOpacity": 0.14},
    {"id": "fBEO", "type": "region", "pts": ["B", "E", "O"], "fill": "orange", "fillOpacity": 0.38},
    {"id": "fDGO", "type": "region", "pts": ["D", "G", "O"], "fill": "orange", "fillOpacity": 0.38},
    {"id": "fDNK", "type": "region", "pts": ["D", "N", "K"], "fill": "cyan", "fillOpacity": 0.32},
    {"id": "fMOK", "type": "region", "pts": ["M", "O", "K"], "fill": "cyan", "fillOpacity": 0.32},
    {"id": "fMOH", "type": "region", "pts": ["M", "O", "H"], "fill": "orange", "fillOpacity": 0.45},
    {"id": "fNOG", "type": "region", "pts": ["N", "O", "G"], "fill": "purple", "fillOpacity": 0.3},
    {"id": "fNKG", "type": "region", "pts": ["N", "K", "G"], "fill": "purple", "fillOpacity": 0.22},
    {"id": "fOKG", "type": "region", "pts": ["O", "K", "G"], "fill": "purple", "fillOpacity": 0.5},
    # 图形主体：平行四边形 + 四条直角边所在的线（矩形的边就在这四条线上）
    {"id": "par", "type": "polygon", "pts": ["A", "B", "C", "D"], "stroke": "ink", "width": 3.4},
    seg("lAE", "A", "E"), seg("lBF", "B", "F"), seg("lCG", "C", "G"), seg("lDH", "D", "H"),
    {"id": "rE", "type": "right", "pts": ["A", "E", "B"], "stroke": "ink", "size": 14},
    {"id": "rG", "type": "right", "pts": ["C", "G", "D"], "stroke": "ink", "size": 14},
    {"id": "rH", "type": "right", "pts": ["A", "H", "D"], "stroke": "ink", "size": 14},
    {"id": "rF", "type": "right", "pts": ["C", "F", "B"], "stroke": "ink", "size": 14},
    # 第(1)问
    seg("sME", "M", "E", "hl", 4.5),
    {"id": "circ", "type": "pcurve", "fx": "px('M')+dist(px('A'),py('A'),px('B'),py('B'))/2*cos(t)",
     "fy": "py('M')+dist(px('A'),py('A'),px('B'),py('B'))/2*sin(t)", "t": [0, "2*PI"], "n": 240, "close": True,
     "stroke": "gray", "width": 2.2, "dash": [9, 8]},
    seg("hBE", "B", "E", "hl", 5.5), seg("hDG", "D", "G", "hl", 5.5),
    seg("hAE", "A", "E", "gold", 5.5), seg("hCG", "C", "G", "gold", 5.5),
    {"id": "dAB", "type": "dim", "pts": ["B", "A"], "text": "6", "off": 46, "stroke": "gray"},
    # 第(2)问①
    seg("dHF", "H", "F", "ink", 2.2), seg("dEG", "E", "G", "ink", 2.2),
    seg("sOM", "O", "M", "hl", 4.5),
    seg("sOB", "O", "B", "gray", 2.4, dash=[9, 7]), seg("sOD", "O", "D", "gray", 2.4, dash=[9, 7]),
    seg("sOE", "O", "E", "teal", 5.5), seg("sOG", "O", "G", "teal", 5.5),
    {"id": "aOEF", "type": "angle", "pts": ["O", "E", "F"], "r": 34, "stroke": "green", "width": 3},
    {"id": "aOGH", "type": "angle", "pts": ["O", "G", "H"], "r": 34, "stroke": "green", "width": 3},
    {"id": "aBEO", "type": "angle", "pts": ["B", "E", "O"], "r": 50, "stroke": "orange", "width": 3},
    {"id": "aDGO", "type": "angle", "pts": ["D", "G", "O"], "r": 50, "stroke": "orange", "width": 3},
    {"id": "fBEOr", "type": "polygon", "pts": ["Br", "Er", "O"], "stroke": "orange", "width": 3, "dash": [10, 7],
     "fill": "orange", "fillOpacity": 0.3},
    # 第(2)问②
    seg("sAH", "A", "H", "gold", 5.5), seg("sHE", "H", "E", "gold", 5.5),
    seg("sHGx", "D", "H", "gray", 2.2, dash=[8, 7], ext=[0, 2.2]),
    seg("sMD", "M", "D", "teal", 4.5),
    seg("sMH", "M", "H", "hl", 5),
    seg("sON", "O", "N", "ink", 2.6), seg("sNG", "N", "G", "ink", 2.6),
    seg("sKM", "K", "M", "cyan", 6), seg("sKD", "K", "D", "orange", 6), seg("sGK", "G", "K", "hl", 5),
    seg("hO", "O", "foot(O,M,D)", "blue", 2.6, dash=[7, 6]), seg("hN", "N", "foot(N,M,D)", "blue", 2.6, dash=[7, 6]),
    {"id": "rtO", "type": "right", "pts": ["O", "foot(O,M,D)", "M"], "stroke": "blue", "size": 12},
    {"id": "rtN", "type": "right", "pts": ["N", "foot(N,M,D)", "D"], "stroke": "blue", "size": 12},
    # 点
    {"id": "pM", "type": "point", "at": "M", "r": 6, "fill": "ink"},
    {"id": "pH", "type": "point", "at": "H", "r": 6, "fill": "ink"},
    {"id": "pO", "type": "point", "at": "O", "r": 6, "fill": "ink"},
    {"id": "pN", "type": "point", "at": "N", "r": 6, "fill": "ink"},
    {"id": "pK", "type": "point", "at": "K", "r": 6, "fill": "hl"},
    # 点名
    {"id": "lA", "type": "label", "at": "A", "text": "A", "dir": "N"},
    {"id": "lB", "type": "label", "at": "B", "text": "B", "dir": "W"},
    {"id": "lC", "type": "label", "at": "C", "text": "C", "dir": "S"},
    {"id": "lD", "type": "label", "at": "D", "text": "D", "dir": "E"},
    {"id": "lE", "type": "label", "at": "E", "text": "E", "dir": "S"},
    {"id": "lF", "type": "label", "at": "F", "text": "F", "dir": "E"},
    {"id": "lG", "type": "label", "at": "G", "text": "G", "dir": "N"},
    {"id": "lH", "type": "label", "at": "H", "text": "H", "dir": "NE"},
    {"id": "lM", "type": "label", "at": "M", "text": "M", "dir": "W"},
    {"id": "lO", "type": "label", "at": "O", "text": "O", "dir": "S"},
    {"id": "lN", "type": "label", "at": "N", "text": "N", "dir": "N"},
    {"id": "lK", "type": "label", "at": "K", "text": "K", "dir": "NW"},
    # 长度、高的标注
    txt("t3a", "mid(A,M)", "$3$", "SE", 30), txt("t3b", "mid(M,B)", "$3$", "SE", 30), txt("t3e", "mid(M,E)", "$3$", "NE", 30),
    txt("t3dg", "mid(D,G)", "$3$", "N", 26, "red"), txt("t3be", "mid(B,E)", "$3$", "S", 26, "red"),
    txt("tAE", "mid(A,H)", "$3\\sqrt3$", "E", 46, "gold"), txt("tCG", "mid(C,F)", "$3\\sqrt3$", "W", 46, "gold"),
    txt("lh1", "mid(O,foot(O,M,D))", "$h_1$", "W", 30, "blue"), txt("lh2", "mid(N,foot(N,M,D))", "$h_2$", "E", 30, "blue"),
    txt("x2", "mid(M,H)", "$2x$", "N", 36, "red", "fm"), txt("x5", "mid(H,K)", "$5x$", "N", 30, "ink", "fm"),
    txt("x3", "mid(K,G)", "$3x$", "N", 30, "red", "fm"), txt("x4", "mid(G,D)", "$4x$", "S", 30, "orange", "fm"),
    txt("cap", [0, -3.75], "赵爽弦图", "C", 0, "ink", "wt"),
    # 动态展示的实时读数（放在三角形填色之后：area() 要用到它们）
    {"id": "rdHG", "type": "text", "at": [-5.5, -3.45], "dir": "C", "align": "left", "cls": "rdl", "color": "ink",
     "text": "$\\dfrac{HG}{DG}=$ {#}", "num": "dist(px('H'),py('H'),px('G'),py('G'))/dist(px('G'),py('G'),px('D'),py('D'))", "digits": 2},
    {"id": "rdS", "type": "text", "at": [0.3, -3.45], "dir": "C", "align": "left", "cls": "rdl", "color": "purple",
     "text": "$\\dfrac{S_{\\triangle NOG}}{S_{\\triangle MOH}}=$ {#}", "num": "area('fNOG')/area('fMOH')", "digits": 2},
]

INIT = FILLS[:] + ["par", "lAE", "lBF", "lCG", "lDH"] + RIGHTS + ["cap"]
LABELS8 = ["lA", "lB", "lC", "lD", "lE", "lF", "lG", "lH"]

V_READ = bbox(CFG["F1"], (0.7, 0.75))
V1 = {"x": [-6.4, 5.3], "y": [-4.75, 4.85]}          # 图①（含以 M 为圆心的圆）
V2 = bbox(CFG["F2"], (1.45, 1.2))
V3 = {"x": [-5.85, 5.85], "y": [-4.2, 3.9]}          # 图③（下方留读数的位置；HG 拉长到 6 时也放得下）


def N(note, cls=None, np=None, **kw):
    d = {"note": note}
    if cls:
        d["cls"] = cls
    if np:
        d["np"] = np
    d.update(kw)
    return d


def tw(at, vals, dur, **kw):
    return {"at": at, "tween": vals, "dur": dur, **kw}


problem = {
    "tag": "四边形综合",
    "size": 30,
    "width": 1040,
    "text": ("（宁波期末）我国著名的{k1|“赵爽弦图”是由四个全等的直角三角形与一个小正方形拼成一个大正方形}．如图，数学兴趣小组的小伙伴们"
             "尝试用{k2|两对全等的直角三角形与一个矩形 $EFGH$ 拼出了一个平行四边形 $ABCD$}．其中{k3|$M$ 是 $AB$ 的中点}．"),
    "parts": [
        "（1）如图①，若{q1|$ME=DG$，$AB=6$，求 $CG$ 的长}．",
        "（2）如图②，{q2|连接 $HF$，$EG$ 交于点 $O$，连接 $OM$}．",
        "　①求证：{q3|$OM\\parallel AD$}；",
        "　②如图③，{q4|若 $AH=HE$，取 $AD$ 的中点 $N$，连接 $ON$，$NG$，$MH$}，{q5|若 $S_{\\triangle NOG}=3S_{\\triangle MOH}$，求 $\\dfrac{HG}{DG}$ 的值}．",
    ],
}

S1_HIDE = ["sME", "circ", "t3a", "t3b", "t3e", "hDG", "t3dg", "hBE", "t3be", "hAE", "tAE", "hCG", "tCG", "dAB"]
S2_HIDE = ["fABD", "sOB", "sOD", "sOE", "sOG", "hBE", "hDG", "aOEF", "aOGH", "aBEO", "aDGO", "fBEO", "fDGO", "fBEOr"]

scenes = [
    {"id": "s0", "layout": "title", "beats": [
        {"say": "把赵爽弦图换一种拼法，会拼出什么？｜"}]},

    {"id": "s1", "layout": "problem", "num": "题", "title": "读题",
     "box": {"x": 1250, "y": 150, "w": 630, "h": 790}, "view": V_READ,
     "beats": [
         {"say": "赵爽弦图，是四个全等的直角三角形，围着一个小正方形。",
          "do": [{"at": "^", "mark": "k1", "dur": 1.4},
                 {"at": "四个", "focus": FILLS[:4], "color": "blue", "dur": 1.6},
                 {"at": "小正方形", "focus": "fRect", "color": "gold", "dur": 1.4}]},
         {"say": "本题换成两对全等的直角三角形，中间是矩形 EFGH。",
          "do": [{"at": "^", "mark": "k2", "dur": 1.4}, {"at": "^", "hide": "cap", "dur": 0.4},
                 tw("两对", {"w": CFG["F1"]["w"], "ah": 0}, 2.6),
                 {"at": "两对", "paint": PAIR2, "color": "green", "dur": 1.2},
                 {"at": "矩形", "show": ["lE", "lF", "lG", "lH"]}]},
         {"say": "拼出来的是平行四边形 ABCD。",
          "do": [{"at": "平行四边形", "show": ["lA", "lB", "lC", "lD"]},
                 {"at": "平行四边形", "focus": "par", "dur": 1.4}]},
         {"say": "△ABE 和 △CDG 全等，△ADH 和 △CBF 全等。",
          "do": [{"at": "△ABE", "focus": PAIR1, "color": "blue", "dur": 1.6},
                 {"at": "△ADH", "focus": PAIR2, "color": "green", "dur": 1.6}]},
         {"say": "M 是 AB 的中点。",
          "do": [{"at": "^", "mark": "k3"}, {"at": "^", "show": ["pM", "lM"]}]},
         {"say": "第1问：ME=DG，AB=6，求 CG 的长。",
          "do": [{"at": "第1问", "mark": "q1"}]},
         {"say": "第2问，连接 HF、EG 交于点 O，先证明 OM∥AD。",
          "do": [{"at": "连接", "mark": "q2"}, {"at": "先证明", "mark": "q3"}]},
         {"say": "再加上 AH=HE，取 AD 的中点 N。",
          "do": [{"at": "^", "mark": "q4", "dur": 1.0}]},
         {"say": "由面积关系，求 HG 与 DG 的比值。｜",
          "do": [{"at": "^", "mark": "q5", "dur": 1.0}]},
     ]},

    {"id": "s2", "layout": "board", "num": "01", "title": "求 $CG$ 的长", "tag": "第（1）问", "view": V1,
     "beats": [
         {"say": "先看第1问：M 是直角三角形 ABE 斜边 AB 的中点。",
          "do": [{"at": "^", "hide": ["rG", "rH", "rF"], "dur": 0.4},
                 {"at": "^", "dim": ["fCDG", "fADH", "fCBF", "fRect"], "to": 0.35},
                 {"at": "直角三角形", "focus": ["fABE", "rE"], "color": "blue", "dur": 1.6},
                 {"at": "斜边", "show": "dAB"}]},
         {"say": "连接 ME。直角三角形斜边上的中线，等于斜边的一半。",
          "do": [{"at": "连接", "show": "sME", "dur": 0.6},
                 {"at": "中线", "show": "circ", "dur": 1.6},
                 {"at": "中线", "note": "Rt$\\triangle ABE$ 中，$ME$ 是斜边上的中线"}]},
         {"say": "M 到 A、B、E 三点一样远，所以 ME=3。",
          "do": [{"at": "一样远", "show": ["t3a", "t3b", "t3e"]},
                 {"at": "所以", "note": "$ME=\\dfrac12AB=3$", "cls": "key"}]},
         {"say": "又因为 ME=DG，所以 DG=3。",
          "do": [{"at": "^", "hide": "circ", "dur": 0.5},
                 {"at": "DG=3", "show": ["hDG", "t3dg"]}, {"at": "DG=3", "dim": "fCDG", "to": 1},
                 {"at": "DG=3", "note": "$DG=ME=3$"}]},
         {"say": "△ABE 和 △CDG 全等，所以 BE=DG=3，CG=AE。",
          "do": [{"at": "△ABE", "focus": PAIR1, "color": "blue", "dur": 1.6},
                 {"at": "BE", "show": ["hBE", "t3be"]},
                 {"at": "BE", "note": "$\\triangle ABE\\cong\\triangle CDG$：$BE=DG=3$，$CG=AE$", "cls": "sm"}]},
         {"say": "在直角三角形 ABE 中，用勾股定理求 AE。",
          "do": [{"at": "勾股定理", "show": "hAE", "dur": 0.7}]},
         {"say": "AE 等于根号下36减9，也就是 3√3。",
          "do": [{"at": "3√3", "show": "tAE"},
                 {"at": "^", "note": "$AE=\\sqrt{AB^2-BE^2}=\\sqrt{6^2-3^2}=3\\sqrt3$", "cls": "sm"}]},
         {"say": "所以 CG=AE=3√3。",
          "do": [{"at": "CG", "show": ["hCG", "tCG"]},
                 {"at": "^", "note": "$CG=AE=3\\sqrt3$", "np": "（1）", "cls": "ans"}]},
     ]},

    {"id": "s3", "layout": "board", "num": "02", "title": "证明 $OM\\parallel AD$", "tag": "第（2）问①", "view": V1,
     "beats": [
         {"say": "第2问，图形变成这样。",
          "do": [{"at": "^", "hide": S1_HIDE + ["rE"], "dur": 0.4},
                 {"at": "^", "dim": FILLS, "to": 0.45},
                 tw("^", {k: CFG["F2"][k] for k in ("p", "q", "h", "w", "ah")}, 2.6, delay=0.4),
                 {"at": "^", "camera": V2, "dur": 2.6, "delay": 0.4}]},
         {"say": "连接 HF、EG，交于点 O，再连接 OM。",
          "do": [{"at": "连接", "show": ["dHF", "dEG"], "dur": 0.8},
                 {"at": "交于", "show": ["pO", "lO"]},
                 {"at": "OM", "show": "sOM", "dur": 0.6}]},
         {"say": "M 是 AB 的中点，要证平行，就想到中位线。",
          "do": [{"at": "中点", "focus": "pM", "dur": 1.2}]},
         {"say": "连接 OB、OD，只要证明 O 是 BD 的中点。",
          "do": [{"at": "连接", "show": ["sOB", "sOD"], "dur": 0.8},
                 {"at": "只要", "note": "连接 $OB$，$OD$，证 $O$ 是 $BD$ 的中点", "cls": "sm"}]},
         {"say": "矩形的对角线互相平分，所以 OE=OG。",
          "do": [{"at": "OE", "show": ["sOE", "sOG"], "dur": 0.6},
                 {"at": "OE", "note": "矩形 $EFGH$：$OE=OG$"}]},
         {"say": "HG∥EF，所以 ∠OEF=∠OGH。",
          "do": [{"at": "∠OEF", "show": ["aOEF", "aOGH"], "dur": 0.6},
                 {"at": "∠OEF", "note": "$HG\\parallel EF$：$\\angle OEF=\\angle OGH$"}]},
         {"say": "它们的补角也相等：∠BEO=∠DGO。",
          "do": [{"at": "∠BEO", "show": ["aBEO", "aDGO"], "dur": 0.6},
                 {"at": "∠BEO", "note": "$\\therefore\\angle BEO=\\angle DGO$（等角的补角相等）", "cls": "sm"}]},
         {"say": "又有 BE=DG，所以 △BEO≌△DGO。",
          "do": [{"at": "BE=DG", "show": ["hBE", "hDG"], "dur": 0.5},
                 {"at": "所以", "show": ["fBEO", "fDGO"]},
                 {"at": "所以", "note": "$\\triangle BEO\\cong\\triangle DGO$（SAS）", "cls": "key"}]},
         {"say": "所以 OB=OD，∠BOE=∠DOG。",
          "do": [{"at": "^", "note": "$OB=OD$，$\\angle BOE=\\angle DOG$"}]},
         {"say": "E、O、G 在一条直线上，这两个角又相等。所以 B、O、D 也在一条直线上。",
          "do": [{"at": "E", "focus": "dEG", "dur": 1.4},
                 {"at": "B、O、D", "focus": ["sOB", "sOD"], "dur": 1.4},
                 {"at": "B、O、D", "note": "$\\therefore B$，$O$，$D$ 三点共线，$O$ 是 $BD$ 中点", "cls": "sm"}]},
         {"say": "用动画看一看：把 △BEO 绕点 O 转半圈。",
          "do": [{"at": "看一看", "show": "fBEOr", "dur": 0.4}, tw("转半圈", {"r": math.pi}, 3.2)]},
         {"say": "正好和 △DGO 重合，B 转到了 D。",
          "do": [{"at": "重合", "focus": "fDGO", "dur": 1.4}, {"at": "B", "focus": "lD", "dur": 1.2}]},
         {"say": "O 是 BD 的中点，M 是 AB 的中点，OM 是 △ABD 的中位线。",
          "do": [{"at": "^", "hide": ["fBEOr", "fBEO", "fDGO", "aOEF", "aOGH", "aBEO", "aDGO", "sOE", "sOG", "hBE", "hDG"], "dur": 0.5},
                 {"at": "中位线", "show": "fABD"}, {"at": "中位线", "focus": "sOM", "dur": 1.4}]},
         {"say": "所以 OM∥AD。",
          "do": [{"at": "^", "note": "$OM$ 是 $\\triangle ABD$ 的中位线，$OM\\parallel AD$", "np": "（2）①", "cls": "ans sm"}]},
     ]},

    {"id": "s4", "layout": "board", "num": "03", "title": "②：先找共线与中点", "tag": "第（2）问②", "view": V2,
     "beats": [
         {"say": "再看最后一小问：加上条件 AH=HE。",
          "do": [{"at": "^", "hide": S2_HIDE, "dur": 0.4},
                 tw("^", {"q": CFG["F3"]["q"]}, 1.8, delay=0.3), {"at": "^", "camera": V3, "dur": 1.8, "delay": 0.3},
                 {"at": "AH=HE", "show": ["sAH", "sHE"], "dur": 0.6}]},
         {"say": "H 是 AE 的中点，M 是 AB 的中点。",
          "do": [{"at": "H", "show": "pH"}, {"at": "M", "focus": "pM", "dur": 1.2}]},
         {"say": "所以 MH 是 △ABE 的中位线，MH∥BE，BE=2MH。",
          "do": [{"at": "^", "hide": ["sAH", "sHE"], "dur": 0.4},
                 {"at": "MH", "show": "sMH", "dur": 0.6},
                 {"at": "中位线", "note": "$MH$ 是 $\\triangle ABE$ 的中位线"},
                 {"at": "MH∥BE", "note": "$MH\\parallel BE$，$BE=2MH$"}]},
         {"say": "HG 也平行于 BE，所以 M、H、G 在一条直线上。",
          "do": [{"at": "HG", "focus": "lDH", "dur": 1.4},
                 {"at": "所以", "note": "$HG\\parallel BE\\Rightarrow M$，$H$，$G$ 共线"}]},
         {"say": "D 在 HG 的延长线上，所以 M、H、G、D 四点共线。",
          "do": [{"at": "四点", "show": "sMD", "dur": 0.8},
                 {"at": "四点", "note": "$\\Rightarrow M$，$H$，$G$，$D$ 四点共线", "cls": "key"}]},
         {"say": "取 AD 的中点 N，连接 ON、NG，ON 交 MD 于点 K。",
          "do": [{"at": "中点", "show": ["pN", "lN"]},
                 {"at": "连接", "show": ["sON", "sNG"], "dur": 0.8},
                 {"at": "点K", "show": ["pK", "lK"]}]},
         {"say": "由第①问，OM∥AD，OM 等于 AD 的一半。",
          "do": [{"at": "OM∥AD", "focus": "sOM", "dur": 1.4},
                 {"at": "一半", "note": "由①：$OM\\parallel AD$，$OM=\\dfrac12AD$"}]},
         {"say": "N 是 AD 的中点，DN 也等于 AD 的一半，所以 OM=DN。",
          "do": [{"at": "所以", "note": "$DN=\\dfrac12AD$，$\\therefore OM=DN$"}]},
         {"say": "OM∥DN，内错角相等，所以 △DNK≌△MOK。",
          "do": [{"at": "△DNK", "show": ["fDNK", "fMOK"]},
                 {"at": "△DNK", "note": "$\\triangle DNK\\cong\\triangle MOK$（ASA）", "cls": "key"}]},
         {"say": "所以 KD=KM，KN=KO，K 是 MD 和 ON 的中点。",
          "do": [{"at": "KD=KM", "show": ["sKM", "sKD"], "dur": 0.6},
                 {"at": "^", "note": "$KD=KM$，$KN=KO$"}]},
     ]},

    {"id": "s5", "layout": "board", "num": "04", "title": "②：用面积比求比值", "tag": "第（2）问②",
     "beats": [
         {"say": "作 △MOH 的高 h₁，△NKG 的高 h₂。",
          "do": [{"at": "^", "hide": ["fDNK", "fMOK", "sKM", "sKD"], "dur": 0.4},
                 {"at": "h₁", "show": ["hO", "rtO", "lh1"], "dur": 0.6},
                 {"at": "h₂", "show": ["hN", "rtN", "lh2"], "dur": 0.6}]},
         {"say": "△DNK 和 △MOK 全等，对应的高相等，h₁=h₂。",
          "do": [{"at": "h₁=h₂", "focus": ["hO", "hN"], "dur": 1.4},
                 {"at": "h₁=h₂", "note": "$\\triangle DNK\\cong\\triangle MOK\\Rightarrow h_1=h_2$"}]},
         {"say": "△MOH 的面积，等于 MH 乘 h₁ 的一半。",
          "do": [{"at": "面积", "show": "fMOH"},
                 {"at": "面积", "note": "$S_{\\triangle MOH}=\\dfrac12MH\\cdot h_1$"}]},
         {"say": "△NOG 被 MD 分成上下两块，底边都是 KG。",
          "do": [{"at": "分成", "show": ["fNKG", "fOKG"]}, {"at": "KG", "show": "sGK", "dur": 0.5}]},
         {"say": "它的面积，等于 KG 乘两条高之和的一半。",
          "do": [{"at": "面积", "note": "$S_{\\triangle NOG}=\\dfrac12KG\\cdot(h_1+h_2)=KG\\cdot h_1$", "cls": "sm"}]},
         {"say": "△NOG 的面积是 △MOH 的3倍，所以 MH 与 KG 的比是2比3。",
          "do": [{"at": "所以", "note": "$KG\\cdot h_1=3\\times\\dfrac12MH\\cdot h_1$，$\\dfrac{MH}{KG}=\\dfrac23$", "cls": "sm"}]},
         {"say": "设 MH=2x，KG=3x，那么 DG=BE=2MH=4x。",
          "do": [{"at": "^", "hide": ["hO", "rtO", "lh1", "hN", "rtN", "lh2", "fNKG", "fOKG", "fMOH", "sGK"], "dur": 0.4},
                 {"at": "MH", "show": "x2"}, {"at": "KG", "show": "x3"}, {"at": "DG", "show": "x4"},
                 {"at": "^", "note": "设 $MH=2x$，$KG=3x$，则 $DG=BE=4x$", "cls": "sm"}]},
         {"say": "KD=KG+GD=7x，KM=KD，也是7x。",
          "do": [{"at": "KD", "show": "sKD", "dur": 0.5}, {"at": "KM", "show": "sKM", "dur": 0.5},
                 {"at": "^", "note": "$KM=KD=3x+4x=7x$"}]},
         {"say": "所以 HK=7x−2x=5x，HG=5x+3x=8x。",
          "do": [{"at": "^", "hide": ["sKD", "sKM"], "dur": 0.4}, {"at": "HK", "show": "x5"},
                 {"at": "^", "note": "$HK=7x-2x=5x$，$HG=HK+KG=8x$", "cls": "sm"}]},
         {"say": "HG 与 DG 的比值，是8x比4x，等于2。",
          "do": [{"at": "^", "note": "$\\dfrac{HG}{DG}=\\dfrac{8x}{4x}=2$", "np": "（2）②", "cls": "ans"}]},
         {"say": "用动画看一看：DG 不变，让 HG 先变短，再变长。",
          "do": [{"at": "^", "hide": ["x2", "x3", "x4", "x5"], "dur": 0.4},
                 {"at": "^", "show": ["fMOH", "fNOG", "rdHG", "rdS"]},
                 tw("变短", {"w": 3.6}, 2.4), tw("变短", {"w": 6.0}, 3.4, delay=2.6), tw("变短", {"w": 4.8}, 2.4, delay=6.2)]},
         {"say": "HG 越长，面积比越大；HG 正好是 DG 的2倍，面积比才是3。",
          "do": [{"at": "2倍", "focus": ["rdHG", "rdS"], "dur": 1.8}]},
     ]},

    {"id": "s6", "layout": "board", "num": "05", "title": "②的方法二：中线分面积", "tag": "第（2）问② · 方法二",
     "beats": [
         {"say": "面积关系，还可以换个角度看。",
          "do": [{"at": "^", "hide": ["rdHG", "rdS", "fNOG"], "dur": 0.4},
                 {"at": "^", "show": ["fNKG", "fOKG"], "delay": 0.4}]},
         {"say": "K 是 ON 的中点，GK 就是 △NOG 的中线。",
          "do": [{"at": "中线", "show": "sGK", "dur": 0.6}]},
         {"say": "中线把三角形分成面积相等的两块。",
          "do": [{"at": "两块", "focus": ["fNKG", "fOKG"], "color": "purple", "dur": 1.6},
                 {"at": "两块", "note": "$GK$ 是中线：$S_{\\triangle NOG}=2S_{\\triangle OKG}$"}]},
         {"say": "△OKG 和 △MOH 顶点都是 O，底边在同一条直线上。",
          "do": [{"at": "△OKG", "focus": ["fOKG", "fMOH"], "dur": 1.6}]},
         {"say": "高相同，面积比就等于底的比。",
          "do": [{"at": "^", "note": "同高：$\\dfrac{S_{\\triangle OKG}}{S_{\\triangle MOH}}=\\dfrac{KG}{MH}$"}]},
         {"say": "所以 KG 与 MH 的比是3比2，和方法一一样。",
          "do": [{"at": "^", "note": "$2\\times\\dfrac{KG}{MH}=3$，$\\dfrac{KG}{MH}=\\dfrac32$", "cls": "key"}]},
     ]},

    {"id": "s7", "layout": "board", "num": "06", "title": "想一想", "tag": "反思",
     "beats": [
         {"say": "想一想：如果没有 AH=HE 这个条件呢？",
          "do": [{"at": "^", "hide": ["fNKG", "fOKG", "fMOH", "sGK", "sMD", "pK", "lK", "sON", "sNG", "pN", "lN"], "dur": 0.4},
                 {"at": "^", "show": "sHGx", "dur": 0.6, "delay": 0.3},
                 tw("没有", {"q": 1.2}, 2.2)]},
         {"say": "H 不再是 AE 的中点，M 就离开了 GH 这条直线。",
          "do": [{"at": "离开", "focus": "sMH", "color": "red", "dur": 1.6}]},
         {"say": "四点不共线，前面拆面积的办法就用不上了。",
          "do": [{"at": "^", "note": "没有 $AH=HE$：$M$，$H$，$G$，$D$ 不共线"}]},
         {"say": "AH=HE，正是为了让 M、H、G、D 连成一条直线。｜",
          "do": [tw("^", {"q": CFG["F3"]["q"]}, 2.0),
                 {"at": "连成", "note": "$AH=HE\\Rightarrow MH$ 是中位线 $\\Rightarrow$ 四点共线", "cls": "key sm"}]},
     ]},

    {"id": "s8", "layout": "summary", "num": "07", "title": "总结",
     "chain": [
         {"id": "c1", "title": "斜边中线", "sub": "$ME=\\dfrac12AB$"},
         {"id": "c2", "title": "全等搬边", "sub": "$BE=DG$\n$CG=AE$"},
         {"id": "c3", "title": "证中点", "sub": "$\\triangle BEO\\cong\\triangle DGO$\n$O$ 是 $BD$ 中点"},
         {"id": "c4", "title": "中位线", "sub": "$OM\\parallel AD$\n$MH\\parallel BE$"},
         {"id": "c5", "title": "等高比底", "sub": "面积比\n＝底之比"},
     ],
     "answers": [
         {"id": "ans1", "text": "（1）$CG=$[[$3\\sqrt3$]]；（2）①$O$ 是 $BD$ 中点，$OM$ 是中位线，[[$OM\\parallel AD$]]"},
         {"id": "ans2", "text": "（2）②[[$\\dfrac{HG}{DG}=2$]]"},
     ],
     "tagline": "见中点，想中位线；比面积，找等高",
     "beats": [
         {"say": "回顾一下：直角三角形斜边上的中线，等于斜边的一半。", "do": [{"at": "斜边", "show": "c1"}]},
         {"say": "全等三角形把边搬过来，再用勾股定理。", "do": [{"at": "全等", "show": "c2"}]},
         {"say": "证 O 是 BD 的中点，靠 △BEO 和 △DGO 全等。", "do": [{"at": "证", "show": "c3"}]},
         {"say": "有两个中点，就想到中位线：OM∥AD，MH∥BE。", "do": [{"at": "中位线", "show": "c4"}]},
         {"say": "比面积，找等高的三角形，转化成底的比。",
          "do": [{"at": "比面积", "show": "c5"}, {"at": "底的比", "show": ["ans1", "ans2"], "delay": 0.3}]},
         {"say": "见中点，想中位线；比面积，找等高。｜", "do": [{"at": "^", "show": "tagline"}]},
     ]},

    {"id": "s9", "layout": "outro", "main": "这道题就讲到这里", "sub": "我们下次再见",
     "beats": [{"say": "好，这道题就讲到这里。同学们，我们下次再见！"}]},
]

sb = {
    "meta": {"title": "由赵爽弦图拼出的平行四边形", "tag": "四边形综合", "subtitle": "斜边中线 · 全等 · 中位线 · 面积比",
             "out": "四边形综合_赵爽弦图拼出的平行四边形.mp4", "theme": "light", "fps": 30},
    "problem": problem,
    "layouts": {"board": {"box": {"x": 70, "y": 140, "w": 1130, "h": 800}}},
    "world": {"vars": dict(CFG["CL"], r=0), "funcs": FUNCS, "view": V_READ, "points": points, "objects": objects, "init": INIT},
    "scenes": scenes,
}
(HERE / "赵爽弦图.json").write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
print("写好 赵爽弦图.json：%d 个图元，%d 个场景" % (len(objects), len(scenes)))
print("视野 读题 %s | 图① %s | 图② %s | 图③ %s" % (V_READ, V1, V2, V3))
for k, c in CFG.items():
    P = coords(c)
    print(k, " ".join("%s(%.2f,%.2f)" % (n, *P[n]) for n in "ABCDEFGH"))
