# -*- coding: utf-8 -*-
"""讲题视频 Pro：分镜 JSON -> 带配音的 1080p 讲解视频（mp4）

用法（在任意目录）:
  python make_video.py <分镜.json> check                   分镜闸门（结构/锚点/标点/口播长度），ERROR 必须清零
  python make_video.py <分镜.json> tts                     配音（按场景缓存：文案与音色不变就不重合成）
  python make_video.py <分镜.json> preview [--fake] [t ...] 抽帧预览：不给时刻则每个节拍的"定格"各出一帧 + 拼图
  python make_video.py <分镜.json> render [--fake]          全片渲染 + 合成 mp4
  python make_video.py <分镜.json> all                     check + tts + render
  --fake：不调配音，按 4.3 字/秒估算时间轴（排版调试用，出片无声）

画面是 HTML/SVG + 无头 Chrome 逐帧截图（runtime/engine.js 的 seek(t) 是时间的纯函数），
几何点坐标由分镜里的表达式精确算出，动点问题直接把变量（如 t）做补间，重叠区域逐帧裁剪计算。
"""
import base64
import hashlib
import html as _html
import json
import math
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNTIME = ROOT / "runtime"
ASSETS = ROOT / "assets"
sys.path.insert(0, str(HERE))
import narr_norm  # noqa: E402
import align as AL  # noqa: E402
import tts_gemini as TG  # noqa: E402  （静音检测/插静音工具，两种配音引擎都用）

SR = 24000
LEAD = {"title": 0.6, "problem": 0.9, "board": 1.0, "summary": 0.9, "outro": 0.8}   # 场景开头留白（版式入场）
TAIL = 0.8                                                           # 场景结尾留白
OUTRO_TAIL = 2.2                                                     # 片尾说完后多留一会儿，全片缓缓淡出
CPS = 4.3                                                            # --fake 估算语速
GAP_SENT = {"。": 0.95, "；": 0.95, "？": 1.1, "！": 1.0}             # --fake 估算句间停顿
DEFAULT_BOX = {"problem": {"x": 250, "y": 560, "w": 1420, "h": 370},
               "board": {"x": 70, "y": 140, "w": 1130, "h": 588}}
BRAND_LOGO = {"light": "brand/jlxb_logo_teal.png",     # 经纶学霸标志：浅色主题用青色字（透明底）
              "dark": "brand/jlxb_logo_white.png"}     # 深色主题用白色字
# 标题卡右下角的淡色尺规作图装饰（通用，不针对具体题目）
TITLE_DECO = ('<svg class="tdeco" viewBox="0 0 560 480" fill="none" stroke="#00a5a5" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
              '<g stroke-opacity="0.16"><circle cx="300" cy="262" r="178" stroke-dasharray="10 12"/>'
              '<path d="M120 404 L300 118 L500 404 Z"/><path d="M300 118 V404" stroke-dasharray="8 10"/>'
              '<path d="M300 384 h20 v20"/><path d="M156 404 A 38 38 0 0 0 141 372"/>'
              '<path d="M40 452 H540"/>'
              + "".join('<path d="M%d 452 v%d"/>' % (40 + 24 * i, -14 if i % 5 == 0 else -8) for i in range(21)) +
              '</g><g fill="#00a5a5" fill-opacity="0.22" stroke="none"><circle cx="300" cy="118" r="8"/><circle cx="120" cy="404" r="8"/>'
              '<circle cx="500" cy="404" r="8"/><circle cx="300" cy="404" r="6"/></g></svg>')
LINE_TYPES = {"polygon", "segment", "polyline", "arrow", "angle", "right", "dim", "curve", "pcurve", "axes", "ticks"}
WORLD_TYPES = LINE_TYPES | {"clip", "region", "point", "label", "text"}
FORBID = ["综上所述", "值得注意的是", "让我们", "众所周知", "总而言之", "由此可见", "不难发现", "不在话下",
          "首先", "其次", "此外", "接下来我们将"]
MAX_SENT = 30      # 单句硬上限（字）
WARN_SENT = 24     # 单句建议上限


def log(*a):
    print(*a, flush=True)


def esc(s):
    return _html.escape(str(s), quote=False)


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# ============================================================ 文本 -> HTML
def marks(s):
    """题干标记 {id|文字} -> [(起, 止, id, 文字)]。文字里可以有 $..$ 公式，公式里的花括号（\\frac{..}{..}）不算标记的边界"""
    out, i, math = [], 0, False
    while i < len(s):
        ch = s[i]
        if ch == "$":
            math = not math
        elif ch == "{" and not math:
            m = re.match(r"\{(\w+)\|", s[i:])
            if m:
                j, mm = i + m.end(), False
                while j < len(s) and not (s[j] == "}" and not mm):
                    if s[j] == "$":
                        mm = not mm
                    j += 1
                out.append((i, j + 1, m.group(1), s[i + m.end():j]))
                i = j + 1
                continue
        i += 1
    return out


def rich(s):
    """文本 -> HTML：$..$ 数学段（KaTeX）、[[..]] 填空答案、{id|..} 题干标记"""
    def inner(t):
        out = []
        for p in re.split(r"(\$[^$]+\$|\[\[.+?\]\])", t):
            if not p:
                continue
            if len(p) > 1 and p[0] == "$" and p[-1] == "$":
                out.append('<span class="math">%s</span>' % esc(p[1:-1]))
            elif p.startswith("[[") and p.endswith("]]"):
                out.append('<span class="fill">%s</span>' % inner(p[2:-2]))
            else:
                out.append(esc(p).replace("\n", "<br>"))
        return "".join(out)
    res, pos = [], 0
    for a, b, mid, txt in marks(s):
        res.append(inner(s[pos:a]))
        res.append('<span class="mk" data-id="%s" data-kind="mark">%s</span>' % (mid, inner(txt)))
        pos = b
    res.append(inner(s[pos:]))
    return "".join(res)


def plain(s):
    """去掉标记语法，得到纯显示文字（用于量长度/查标点）"""
    out, pos = [], 0
    for a, b, mid, txt in marks(s):
        out += [s[pos:a], txt]
        pos = b
    s = "".join(out) + s[pos:]
    s = s.replace("[[", "").replace("]]", "")
    return s


SENT_RE = re.compile(r"[^。！？；]*[。！？；]｜*|[^。！？；]+$")
# 口播里的 {显示|读法}：字幕显示前一半，配音念后一半（2026-09-30 物理竞赛题：r 和 R 念出来一样，
# 口播写 {r|小r}、{R|大R}；公式写 {2rR/(2r−R)|2小r减大R 分之 2小r大R}，字幕干净、念得清楚）
SAY_ALT = re.compile(r"\{([^{}|]*)\|([^{}]*)\}")


def split_say(say):
    """口播 -> [{disp 显示句, punct 句末标点, bars 句后长停顿个数}]"""
    res = []
    for m in SENT_RE.finditer((say or "").strip()):
        s = m.group(0).strip()
        if not s or set(s) <= {"｜"}:
            if res and s:
                res[-1]["bars"] += s.count("｜")
            continue
        bars = len(s) - len(s.rstrip("｜"))
        s2 = s.rstrip("｜").strip()
        punct = s2[-1] if s2[-1] in "。！？；" else "。"
        res.append({"disp": s2, "punct": punct, "bars": bars})
    return res


def sub_html(disp):
    """字幕：去 $，太长的句子在靠近中点的逗号处折成两行"""
    s = disp.replace("$", "")
    if len(s) > 28:
        cands = [i for i, ch in enumerate(s) if ch in "，、：" and 6 < i < len(s) - 4]
        if cands:
            k = min(cands, key=lambda i: abs(i - len(s) / 2))
            return esc(s[:k + 1]) + "<br>" + esc(s[k + 1:])
    return esc(s)


# ============================================================ 分镜预处理
class Board:
    def __init__(self, sb_path):
        self.path = Path(sb_path).resolve()
        self.dir = self.path.parent
        self.sb = json.loads(self.path.read_text(encoding="utf-8"))
        self.meta = self.sb.get("meta", {})
        self.fps = int(self.meta.get("fps", 30))
        self.theme = "dark" if self.meta.get("theme") == "dark" else "light"
        self.build = self.dir / ("build_" + self.path.stem)
        self.build.mkdir(exist_ok=True)
        self.errors, self.warns = [], []
        self._prep()

    # ---------------- 预处理：句子、读音流、界面元素 id
    def _prep(self):
        sb = self.sb
        self.world = sb.get("world") or {"vars": {}, "points": {}, "objects": []}
        self.wtype = {}
        for o in self.world.get("objects", []):
            if o.get("id") in self.wtype:
                self.errors.append("world 图元 id 重复: %s" % o.get("id"))
            self.wtype[o.get("id")] = o.get("type")
            if o.get("type") not in WORLD_TYPES:
                self.errors.append("world 图元 %s 类型未知: %s" % (o.get("id"), o.get("type")))
        self.ui = {}          # id -> kind
        self.scenes = []
        for si, sc in enumerate(sb.get("scenes", [])):
            beats = []
            for b in sc.get("beats", []):
                sents = split_say(b.get("say", ""))
                for s in sents:
                    raw = s["disp"]
                    s["disp"] = SAY_ALT.sub(r"\1", raw)
                    s["norm"] = narr_norm.normalize(SAY_ALT.sub(r"\2", raw))
                    s["tts"] = s["norm"] + "｜" * s["bars"]
                    s["stream"] = AL.stream(s["norm"])[0]
                beats.append({"src": b, "sents": sents})
            self.scenes.append({"src": sc, "beats": beats, "id": sc.get("id") or "s%d" % si,
                                "layout": sc.get("layout", "board")})
        self._html()

    # ---------------- 界面 HTML
    def _reg(self, id_, kind):
        if id_ in self.ui or id_ in self.wtype:
            self.errors.append("界面元素 id 重复(或与图元重名): %s" % id_)
        self.ui[id_] = kind

    def _hdr(self, num, title, tag):
        """章节标题：青色编号块 + 标题 + 标签"""
        return '<div class="hdr">%s<span class="ttl">%s</span>%s</div>' % (
            '<span class="num">%s</span>' % esc(num) if num else "", rich(title),
            '<span class="htag">%s</span>' % rich(tag) if tag else "")

    def _html(self):
        sb, meta = self.sb, self.meta
        parts = []
        self.note_ids = {}
        # 章节进度条只算讲解场景（标题卡、片尾不算）
        self.chapters = [s["id"] for s in self.scenes if s["layout"] not in ("title", "outro")]
        for scn in self.scenes:
            sc, sid, lay = scn["src"], scn["id"], scn["layout"]
            h = ['<div class="scene" id="scene-%s">' % sid]
            if lay == "title":
                for k in ("t-tag", "t-main", "t-sub", "t-line"):
                    self._reg(k if si_first(self, scn) else k + "-" + sid, "title")
                sfx = "" if si_first(self, scn) else "-" + sid
                h.append(TITLE_DECO)
                h.append('<div class="titlecard">')
                if meta.get("tag"):
                    h.append('<div class="ttag" data-id="t-tag%s">%s</div>' % (sfx, esc(meta["tag"])))
                h.append('<div class="tmain" data-id="t-main%s">%s</div>' % (sfx, rich(sc.get("title") or meta.get("title", ""))))
                if sc.get("subtitle") or meta.get("subtitle"):
                    h.append('<div class="tsub" data-id="t-sub%s">%s</div>' % (sfx, rich(sc.get("subtitle") or meta.get("subtitle"))))
                h.append('<div class="tline" data-id="t-line%s"><div class="tdot"></div></div></div>' % sfx)
            elif lay == "outro":
                for k in ("o-badge", "o-main", "o-sub", "o-line"):
                    self._reg(k + "-" + sid, "outro")
                h.append('<div class="outro"><div class="obadge" data-id="o-badge-%s"><img src="%s/%s"></div>'
                         '<div class="omain" data-id="o-main-%s">%s</div><div class="osub" data-id="o-sub-%s">%s</div>'
                         '<div class="oline" data-id="o-line-%s"></div></div>' % (
                             sid, ASSETS.as_uri(), BRAND_LOGO[self.theme], sid, rich(sc.get("main", "这道题就讲到这里")),
                             sid, rich(sc.get("sub", "我们下次再见")), sid))
            elif lay == "problem":
                p = sb.get("problem") or {}
                h.append(self._hdr(sc.get("num", "题"), sc.get("title", "读题"), sc.get("tag", p.get("tag"))))
                body = '<p>' + rich(p.get("text", "")) + '</p>'
                for part in p.get("parts", []):
                    body += '<p class="part">' + rich(part) + '</p>'
                for _, _, mid, _ in marks(p.get("text", "") + "".join(p.get("parts", []))):
                    self._reg(mid, "mark")
                # problem.size：题干字号（没有图、题干只占上半屏时可放大）；problem.width：题干宽度（图放题干右侧时收窄）
                sty = ("font-size:%dpx;" % int(p["size"]) if p.get("size") else "") + ("width:%dpx;" % int(p["width"]) if p.get("width") else "")
                h.append('<div class="prob"%s>%s</div>' % (' style="%s"' % sty if sty else "", body))
            else:
                if sc.get("title"):
                    h.append(self._hdr(sc.get("num", ""), sc["title"], sc.get("tag")))
            if lay == "board":
                # 板书面板的位置与宽度：场景 "notes": {"x":左, "w":宽} 或 false（不要面板，图占满全宽）；
                # 不写就用 layouts.board.notes，再没有就用样式表默认（x 1240、w 612）。公式长的题把面板加宽、图框收窄（2026-09-30 函数压轴题）
                ncfg = sc.get("notes", ((sb.get("layouts") or {}).get("board") or {}).get("notes"))
                notes = []
                k = 0
                for b in scn["beats"]:
                    for a in b["src"].get("do", []):
                        if "note" in a:
                            k += 1
                            nid = a.get("id") or "n-%s-%d" % (sid, k)
                            a["_nid"] = nid
                            self._reg(nid, "note")
                            np = '<span class="np">%s</span>' % rich(a["np"]) if a.get("np") else ""
                            notes.append('<div class="note %s" data-id="%s" data-kind="note">%s%s</div>' % (
                                esc(a.get("cls", "")), nid, np, rich(a["note"])))
                if ncfg is False:
                    if notes:
                        self.errors.append("%s: 场景写了 notes:false（不要板书面板），但动作里有 note" % sid)
                else:
                    sty = ""
                    if isinstance(ncfg, dict):
                        sty = ' style="left:%dpx;width:%dpx;--nmax:%dpx"' % (ncfg["x"], ncfg["w"], ncfg["w"] - 60)
                    h.append('<div class="notes"%s><div class="ntitle">板书</div>%s</div>' % (sty, "".join(notes)))
            if lay == "summary":
                chain = sc.get("chain") or []
                if chain:
                    h.append('<div class="chain">')
                    for i, c in enumerate(chain):
                        cid = c.get("id") or "c%d" % (i + 1)
                        if i > 0:
                            self._reg(cid + "-a", "carrow")
                            h.append('<div class="carrow" data-id="%s-a" data-kind="carrow"></div>' % cid)
                        self._reg(cid, "cbox")
                        h.append('<div class="cbox" data-id="%s" data-kind="cbox"><div class="ci">%s</div><div class="ct">%s</div>%s</div>' % (
                            cid, "%02d" % (i + 1), rich(c.get("title", "")),
                            '<div class="cs">%s</div>' % rich(c["sub"]) if c.get("sub") else ""))
                    h.append('</div>')
                if sc.get("answers"):
                    h.append('<div class="answers">')
                    for i, a in enumerate(sc["answers"]):
                        aid = a.get("id") or "ans%d" % (i + 1)
                        self._reg(aid, "answer")
                        h.append('<p data-id="%s" data-kind="answer">%s</p>' % (aid, rich(a["text"])))
                    h.append('</div>')
                if sc.get("tagline"):
                    tid = sc.get("tagline_id", "tagline")
                    self._reg(tid, "tagline")
                    h.append('<div class="tagline"><span data-id="%s" data-kind="tagline">%s</span></div>' % (tid, rich(sc["tagline"])))
            h.append('</div>')
            parts.append("".join(h))
        parts.append(self._widgets_html())
        self.ui_html = "".join(parts)

    def _widgets_html(self):
        wd = self.sb.get("widgets") or {}
        out = ['<div id="boardwrap"><div id="deck"></div>']
        tb = wd.get("timebar")
        if tb:
            self._reg("timebar", "widget")
            a, b = float(tb["from"]), float(tb["to"])
            pct = lambda x: (float(x) - a) / (b - a) * 100
            h = ['<div id="timebar" data-id="timebar" data-kind="widget"><div id="tb-name">%s</div>' % esc(tb.get("name", "时间")),
                 '<div id="tb-track"><div id="tb-fill"></div></div>']
            step = tb.get("tick", 1)
            every = tb.get("label_every", 2)
            x, k = a, 0
            while x <= b + 1e-9:
                h.append('<div class="tick" style="left:%.3f%%"></div>' % pct(x))
                if k % every == 0:
                    h.append('<div class="tickl" style="left:%.3f%%">%s</div>' % (pct(x), ("%g" % x)))
                x += step
                k += 1
            for bd in tb.get("bands", []):
                self._reg(bd["id"], "band")
                c = {"yellow": "rgba(255,201,64,.85)", "green": "rgba(111,207,151,.9)", "blue": "rgba(120,178,240,.85)",
                     "orange": "rgba(255,170,110,.85)"}.get(bd.get("color", "yellow"), bd.get("color"))
                h.append('<div class="band" data-id="%s" data-kind="band" style="left:%.3f%%;width:%.3f%%;background:%s">%s</div>' % (
                    bd["id"], pct(bd["from"]), pct(bd["to"]) - pct(bd["from"]), c, rich(bd.get("text", ""))))
            for fl in tb.get("flags", []):
                self._reg(fl["id"], "flag")
                h.append('<div class="flag" data-id="%s" data-kind="flag" style="left:%.3f%%">%s</div>' % (fl["id"], pct(fl["at"]), rich(fl.get("text", ""))))
            h.append('<div id="tb-knob"></div><div id="tb-val"></div></div>')
            out.append("".join(h))
        mt = wd.get("meter")
        if mt:
            self._reg("meter", "widget")
            full = ""
            if mt.get("full"):
                self._reg("mt-full", "widget")
                full = '<div id="mt-full" data-id="mt-full" data-kind="widget">%s</div>' % rich(mt["full"])
            out.append('<div id="meter" data-id="meter" data-kind="widget"><div id="mt-name">%s</div><div id="mt-bar"><div id="mt-fill"></div></div>%s</div>' % (
                esc(mt.get("name", "面积")), full))
        out.append('</div>')
        return "".join(out)

    # ============================================================ check
    def check(self):
        E, Wn = self.errors, self.warns
        sb = self.sb
        ids = set(self.wtype) | set(self.ui)
        pts = set((self.world.get("points") or {}).keys())
        for o in self.world.get("objects", []):
            for r in (o.get("pts") or []) + [o.get(k) for k in ("at", "from", "to") if o.get(k)]:
                if isinstance(r, str):
                    # 点函数可以嵌套（mid(O,foot(O,M,D))）：后面紧跟"("的是函数名，不当点名查
                    fns = set(re.findall(r"\b([A-Za-z]\w*)\s*\(", r))
                    names = [n for n in re.findall(r"\b([A-Za-z]\w*)\b(?!\s*\()", r)]
                    for n in names:
                        if "centroid" in fns and re.search(r"centroid\(\s*%s\s*\)" % re.escape(n), r):
                            if n not in self.wtype:
                                E.append("图元 %s: centroid(%s) 引用的图元不存在" % (o["id"], n))
                            continue
                        if n not in pts and not re.match(r"^\d", n):
                            E.append("图元 %s 引用了未定义的点 %s" % (o["id"], n))
                    for f in fns - {"mid", "lerp", "off", "centroid", "foot"}:
                        E.append("图元 %s 用了未知的点函数 %s（只有 mid/lerp/off/centroid/foot）" % (o["id"], f))
            if o.get("type") == "clip":
                for i2 in o.get("of", []):
                    if self.wtype.get(i2) not in ("polygon", "region", "clip"):
                        E.append("clip %s 的 of 引用 %s 不是多边形" % (o["id"], i2))
            if o.get("type") == "curve" and not (o.get("fx") and isinstance(o.get("x"), list) and len(o["x"]) == 2):
                E.append("curve %s 需要 fx（x 的表达式）和 x:[起, 止]" % o["id"])
            if o.get("type") == "pcurve" and not (o.get("fx") and o.get("fy") and isinstance(o.get("t"), list) and len(o["t"]) == 2):
                E.append("pcurve %s 需要 fx、fy（t 的表达式）和 t:[起, 止]" % o["id"])
            if o.get("type") == "ticks" and len(o.get("labels", [])) not in (0, len(o.get("at", []))):
                E.append("ticks %s 的 labels 个数要和 at 一样" % o["id"])
        for i in self.world.get("init", []):
            if i not in self.wtype:
                E.append("world.init 引用了不存在的图元 %s" % i)
        vars_ = set((self.world.get("vars") or {}).keys())
        total_chars = 0
        est = 0.0
        seen = set()
        for scn in self.scenes:
            sc, sid = scn["src"], scn["id"]
            if sid in seen:
                E.append("场景 id 重复: %s" % sid)
            seen.add(sid)
            if scn["layout"] not in LEAD:
                E.append("%s: layout 只能是 title/problem/board/summary/outro" % sid)
            if scn["layout"] == "problem" and not sb.get("problem"):
                E.append("%s: problem 版式需要顶层 problem 字段" % sid)
            if not scn["beats"]:
                E.append("%s: 没有 beats" % sid)
            for bi, b in enumerate(scn["beats"]):
                where = "%s.beats[%d]" % (sid, bi)
                say = b["src"].get("say", "")
                if not b["sents"]:
                    E.append("%s: say 为空" % where)
                    continue
                if not re.search(r"[。！？；]｜*$", say.strip()):
                    E.append("%s: say 必须以 。！？ 结尾" % where)
                for s in b["sents"]:
                    n = len(re.sub(r"\s", "", s["disp"]))
                    total_chars += n
                    est += n / CPS + GAP_SENT.get(s["punct"], 0.95) + 1.05 * s["bars"]
                    if n > MAX_SENT:
                        E.append("%s: 句子 %d 字，超过 %d：%s" % (where, n, MAX_SENT, s["disp"]))
                    elif n > WARN_SENT:
                        Wn.append("%s: 句子 %d 字，偏长（建议 ≤%d）：%s" % (where, n, WARN_SENT, s["disp"]))
                    for f in FORBID:
                        if f in s["disp"]:
                            E.append("%s: 禁用语「%s」" % (where, f))
                    if re.search(r"[\u4e00-\u9fff][,.;:?!]|[,.;:?!][\u4e00-\u9fff]", s["disp"]):
                        E.append("%s: 口播/字幕里有半角标点：%s" % (where, s["disp"]))
                    if "$" in s["disp"]:
                        Wn.append("%s: 口播里不要写 $..$（字幕会原样显示）：%s" % (where, s["disp"]))
                stream = sum((s["stream"] for s in b["sents"]), [])
                for ai, a in enumerate(b["src"].get("do", [])):
                    aw = "%s.do[%d]" % (where, ai)
                    at = a.get("at")
                    if at and at not in ("^", "$"):
                        name, occ = (at.rsplit("#", 1) + ["1"])[:2] if "#" in at else (at, "1")
                        sub = AL.stream(narr_norm.normalize(name))[0]
                        pos, k = -1, 0
                        for _ in range(int(occ)):
                            pos = AL.find_sub(stream, sub, pos + 1)
                        if not sub or pos < 0:
                            E.append("%s: 锚点「%s」在本节拍口播里找不到" % (aw, at))
                    ops = [k for k in ("show", "hide", "focus", "paint", "dim", "tween", "set", "camera", "note", "mark") if k in a]
                    if len(ops) != 1:
                        E.append("%s: 每个动作只能有一个操作键(show/hide/focus/paint/dim/tween/set/camera/note/mark)，现在是 %s" % (aw, ops))
                        continue
                    op = ops[0]
                    if op in ("show", "hide", "focus", "paint", "dim", "mark"):
                        tg = a[op] if isinstance(a[op], list) else [a[op]]
                        for t in tg:
                            if t not in ids:
                                E.append("%s: %s 的目标 %s 不存在" % (aw, op, t))
                    if op in ("tween", "set"):
                        for k in a[op]:
                            if k not in vars_:
                                E.append("%s: 变量 %s 没在 world.vars 里声明" % (aw, k))
                        if op == "tween" and not a.get("dur"):
                            E.append("%s: tween 必须给 dur（秒）" % aw)
                    if op == "note":
                        txt = plain(a["note"])
                        if re.search(r"[\u4e00-\u9fff][,.;:?!()]|[,.;:?!()][\u4e00-\u9fff]", re.sub(r"\$[^$]*\$", "", txt)):
                            E.append("%s: 板书标点要全角：%s" % (aw, a["note"]))
                        if len(re.sub(r"\$[^$]*\$", "M", txt)) > 26:
                            Wn.append("%s: 板书一行偏长（>26 字），面板可能折行：%s" % (aw, a["note"]))
                    if op == "camera" and not ("x" in a["camera"] and "y" in a["camera"]):
                        E.append("%s: camera 需要 x、y 两个区间" % aw)
        p = sb.get("problem") or {}
        for txt in [p.get("text", "")] + p.get("parts", []):
            t2 = re.sub(r"\$[^$]*\$", "", plain(txt))
            if re.search(r"[\u4e00-\u9fff][,.;:?!()]|[,.;:?!()][\u4e00-\u9fff]", t2):
                E.append("题干标点要全角：%s" % t2[:40])
        log("[INFO] 口播 %d 字，估算时长 %.0f 秒（%.1f 分钟，未计动画等待）" % (total_chars, est, est / 60))
        for w in Wn:
            log("[WARN] " + w)
        for e in E:
            log("[ERROR] " + e)
        log("check: %d ERROR, %d WARN" % (len(E), len(Wn)))
        return not E

    # ============================================================ 配音
    def tts_config(self):
        cfg = json.loads((HERE / "tts_config.json").read_text(encoding="utf-8"))
        cfg.update(self.meta.get("tts") or {})
        return cfg

    def scene_tts_text(self, scn):
        return "".join(s["tts"] for b in scn["beats"] for s in b["sents"])

    def audio_dir(self):
        """各配音引擎的缓存分开放（百炼沿用 audio/，其余 audio_<引擎>/），换引擎不覆盖旧配音"""
        eng = self.tts_config().get("engine", "bailian")
        return self.build / ("audio" if eng == "bailian" else "audio_" + eng)

    def tts(self, force=False):
        cfg = self.tts_config()
        if cfg.get("engine") == "gemini":
            import tts_gemini as TB
            sig = [cfg.get("engine"), cfg.get("gemini_model"), cfg.get("gemini_voice"), cfg.get("gemini_style")]
        else:
            import tts_bailian as TB
            sig = [cfg.get("model"), cfg.get("voice"), cfg.get("rate"), cfg.get("break"), cfg.get("mode")]
        adir = self.audio_dir()
        adir.mkdir(exist_ok=True)

        def save(scn, key, text, pcm, words, sr):
            with wave.open(str(adir / (scn["id"] + ".wav")), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(pcm)
            (adir / (scn["id"] + ".json")).write_text(json.dumps(
                {"key": key, "text": text, "words": words, "dur": len(pcm) / 2 / sr, "sr": sr},
                ensure_ascii=False, indent=0), encoding="utf-8")

        if cfg.get("engine") == "gemini":
            # Gemini 每次请求的嗓音会变（2026-09-28 实测各场景中位音高 175~234Hz，换场景能听出换人）→ 整片一次合成；
            # 任何一个场景的口播改了，整片重配（约 5 毛钱），保证全片同一个声音
            texts = [self.scene_tts_text(scn) for scn in self.scenes]
            fkey = hashlib.sha1(json.dumps(texts + sig, ensure_ascii=False).encode("utf-8")).hexdigest()
            fp = adir / "_film.json"
            if fp.exists() and not force and json.loads(fp.read_text(encoding="utf-8")).get("key") == fkey \
                    and all((adir / (s["id"] + ".json")).exists() for s in self.scenes):
                log("  整片配音已缓存（%d 个场景）" % len(self.scenes))
                self.fix_tail()
                return
            if force:                  # --force：连选中的原始合成一起作废，真的重新合成
                for f in (adir / "_raw.pcm", adir / "_raw.json"):
                    if f.exists():
                        f.unlink()
            log("  整片一次合成 %d 个场景、%d 字 ..." % (len(texts), sum(len(t) for t in texts)))
            outs = TB.synth_film(texts, cfg, log=log, raw_dir=adir, raw_key=fkey)
            # 句间孤立杂音（<short pause> 被读出半个音等）自动静音，再用改过的原始合成重做切段、调停顿（不重新花钱）
            import stray_sounds
            if stray_sounds.clean(adir, [c for x in texts for c in AL.stream(x)[0]], log=log):
                outs = TB.synth_film(texts, cfg, log=log, raw_dir=adir, raw_key=fkey)
            for scn, text, (pcm, words, sr) in zip(self.scenes, texts, outs):
                save(scn, fkey + ":" + scn["id"], text, pcm, words, sr)
            fp.write_text(json.dumps({"key": fkey}), encoding="utf-8")
            self.fix_tail()
            return
        for scn in self.scenes:
            text = self.scene_tts_text(scn)
            key = hashlib.sha1(json.dumps([text] + sig, ensure_ascii=False).encode("utf-8")).hexdigest()
            mp = adir / (scn["id"] + ".json")
            if mp.exists() and not force:
                old = json.loads(mp.read_text(encoding="utf-8"))
                if old.get("key") == key:
                    log("  [%s] 配音已缓存（%.1f 秒）" % (scn["id"], old["dur"]))
                    continue
            log("  [%s] 合成 %d 字 ..." % (scn["id"], len(text)))
            pcm, words, sr = TB.synth_narration(text, cfg, log=log)
            save(scn, key, text, pcm, words, sr)

    def fix_tail(self):
        """生成式 TTS 偶尔在全片结尾自己加一句（白板课 9-28 实测第 1 遍在"我们下次再见"后多了"好了我们下个视频见"）：
        最后一个场景在口播最后几个字之后的第一段静音处截断，只留 0.3 秒尾音（从白板课 build.fix_tail 移植）"""
        import numpy as np
        if self.tts_config().get("engine") != "gemini":
            return
        scn = self.scenes[-1]
        adir = self.audio_dir()
        pj, pw = adir / (scn["id"] + ".json"), adir / (scn["id"] + ".wav")
        if not pj.exists():
            return
        d = json.loads(pj.read_text(encoding="utf-8"))
        with wave.open(str(pw), "rb") as w:
            pcm = w.readframes(w.getnframes())
        words = d["words"]
        tail = AL.stream(d["text"])[0][-4:]
        chars, ctimes = AL.word_stream(words)
        k = next((i for i in range(len(chars) - len(tail) + 1) if chars[i:i + len(tail)] == tail), -1)
        if k < 0:
            log("[结尾检查] 没在识别结果里找到口播最后几个字，跳过")
            return
        t_end = ctimes[k + len(tail) - 1] + 0.3
        at = TG.quiet_point(TG.frame_db(pcm), t_end - 0.1, t_end + 1.5)
        if at is None:
            return
        extra = "".join(chars[k + len(tail):])
        cut = min(len(pcm) // 2, int((at + 0.3) * SR))
        if cut * 2 < len(pcm) - int(0.05 * SR) * 2:
            if extra:
                log("[结尾检查] 截掉口播之后多出来的：「%s」（%.1f 秒）" % (extra, len(pcm) / 2 / SR - cut / SR))
            x = np.frombuffer(pcm[:cut * 2], np.int16).astype(np.float32)
            nf = int(0.02 * SR)
            x[-nf:] *= np.linspace(1, 0, nf)
            with wave.open(str(pw), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(x.astype(np.int16).tobytes())
            d["words"] = [w for w in words if w["t"] < at]
            d["dur"] = cut / SR
            pj.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")

    # ============================================================ 时间轴
    def speech(self, scn, fake):
        """场景口播 -> 每句的起止时刻（场景音频内的时间）+ 读音流逐字时刻 + PCM"""
        stream = []
        sents = [s for b in scn["beats"] for s in b["sents"]]
        for s in sents:
            s["o0"] = len(stream)
            stream += s["stream"]
            s["o1"] = len(stream)
        if fake:
            times, t = [], 0.0
            for s in sents:
                n = s["o1"] - s["o0"]
                s["start"] = t
                for k in range(n):
                    times.append(t + k / CPS)
                s["stop"] = t + n / CPS
                t = s["stop"] + GAP_SENT.get(s["punct"], 0.95) + 1.05 * s["bars"]
            dur = sents[-1]["stop"] + 0.2 if sents else 0.0
            return {"times": times, "stream": stream, "pcm": None, "dur": dur, "rate": 1.0}
        adir = self.audio_dir()
        mp = adir / (scn["id"] + ".json")
        if not mp.exists():
            sys.exit("缺少配音 %s：先跑 tts（或加 --fake）" % mp)
        info = json.loads(mp.read_text(encoding="utf-8"))
        if info.get("text") != self.scene_tts_text(scn):
            sys.exit("场景 %s 的口播改过了，配音过期：重跑 tts" % scn["id"])
        times, rate = AL.align_times(stream, info["words"])
        if rate < 0.85:
            log("[WARN] 场景 %s 口播与配音时间戳对齐率只有 %.0f%%，锚点时刻可能不准" % (scn["id"], rate * 100))
        with wave.open(str(adir / (scn["id"] + ".wav")), "rb") as w:
            pcm = w.readframes(w.getnframes())
        # 识别时间戳在停顿附近不准（2026-09-28 实测）：停顿后第一个字常报早 0.9~1.5 秒（字幕、动画比声音早出来），
        # 停顿前最后一个字又常报进停顿里（句末被算晚，时间轴以为这句还没说完，又多插 0.8 秒等待 → 句间停 1.7 秒）。
        # 按句界对照波形校正：每个句界找"上句末字到本句首字附近"最长那段静音 [lo, hi]（与插静音找位置同一规则），
        # 本句的字一律不早于 hi，上句的字一律不晚于 lo——声音、字幕、动画三者一致
        db = TG.frame_db(pcm)
        if len(db):
            thr = float(__import__("numpy").percentile(db, 95)) - 32
            s0 = sents[0] if sents else None
            if s0 and s0["o1"] > s0["o0"]:           # 场景第一个字若报在开头静音里，挪到开口处
                t = times[s0["o0"]]
                k = int(t / 0.01)
                if 0 <= k < len(db) and db[k] < thr:
                    lo, hi = TG.quiet_run(db, t)
                    for i in range(s0["o0"], s0["o1"]):
                        times[i] = max(times[i], hi + 0.02)
            for k in range(1, len(sents)):
                s, p = sents[k], sents[k - 1]
                if s["o1"] <= s["o0"] or p["o1"] <= p["o0"]:
                    continue
                at = TG.quiet_point(db, times[p["o1"] - 1] - 0.3, times[s["o0"]] + 0.5)
                if at is None:
                    continue
                lo, hi = TG.quiet_run(db, at)
                if hi - lo < 0.25:
                    continue
                for i in range(s["o0"], s["o1"]):
                    times[i] = max(times[i], hi + 0.02)
                for i in range(p["o0"], p["o1"]):
                    times[i] = min(times[i], lo - 0.12)
            for i in range(1, len(times)):
                times[i] = max(times[i], times[i - 1])
        for s in sents:
            s["start"] = times[s["o0"]] if s["o1"] > s["o0"] else 0.0
            s["stop"] = (times[s["o1"] - 1] + 0.26) if s["o1"] > s["o0"] else s["start"]
        return {"times": times, "stream": stream, "pcm": pcm, "dur": len(pcm) / 2 / SR, "rate": rate}

    def anchor_time(self, at, beat, sp):
        s0, s1 = beat["sents"][0], beat["sents"][-1]
        if not at or at == "^":
            return s0["start"]
        if at == "$":
            return s1["stop"]
        name, occ = (at.rsplit("#", 1)) if "#" in at else (at, "1")
        sub = AL.stream(narr_norm.normalize(name))[0]
        pos = s0["o0"] - 1
        for _ in range(int(occ)):
            pos = AL.find_sub(sp["stream"], sub, pos + 1, s1["o1"])
            if pos < 0:
                sys.exit("锚点「%s」找不到（先跑 check）" % at)
        return sp["times"][pos]

    def default_fx(self, tid, op):
        ty = self.wtype.get(tid)
        if ty:
            if ty in LINE_TYPES:
                return "draw"
            return "pop" if ty == "point" else "fade"
        kind = self.ui.get(tid, "")
        return {"note": "wipe", "mark": "wipe", "cbox": "pop", "carrow": "wipe", "answer": "wipe", "band": "wipe",
                "flag": "pop", "tagline": "pop"}.get(kind, "fade")

    def expand(self, a, t0):
        """作者写的动作 -> 引擎动作（绝对时刻）；返回 (动作列表, 占用到的时刻)"""
        out = []
        if "note" in a:
            n = len(re.sub(r"\$[^$]*\$", "MM", plain(a["note"])))
            dur = a.get("dur", min(1.6, max(0.5, 0.25 + 0.045 * n)))
            out.append({"op": "show", "ids": [a["_nid"]], "fx": "wipe", "t0": t0, "dur": dur})
            return out, t0 + dur
        if "mark" in a:
            ids = a["mark"] if isinstance(a["mark"], list) else [a["mark"]]
            dur = a.get("dur", 0.6)
            out.append({"op": "show", "ids": ids, "fx": "wipe", "t0": t0, "dur": dur, "mark": True})
            return out, t0 + dur
        for op in ("show", "hide", "focus", "paint", "dim"):
            if op in a:
                ids = a[op] if isinstance(a[op], list) else [a[op]]
                if op == "show":
                    # 同一动作里目标类型不同：按类型分别取默认出现方式
                    groups = {}
                    for i in ids:
                        groups.setdefault(a.get("fx") or self.default_fx(i, op), []).append(i)
                    end = t0
                    for fx, gids in groups.items():
                        dur = a.get("dur", {"draw": 0.8, "pop": 0.45, "wipe": 0.6}.get(fx, 0.5))
                        # 总结页链条：箭头先画，方框随后弹出
                        for i in list(gids):
                            if self.ui.get(i) == "cbox" and (i + "-a") in self.ui:
                                out.append({"op": "show", "ids": [i + "-a"], "fx": "wipe", "t0": t0, "dur": 0.3})
                        out.append({"op": "show", "ids": gids, "fx": fx, "t0": t0 + (0.2 if any(self.ui.get(i) == "cbox" for i in gids) else 0), "dur": dur,
                                    **({"ease": a["ease"]} if a.get("ease") else {})})
                        end = max(end, t0 + dur)
                    return out, end
                dur = a.get("dur", {"hide": 0.4, "focus": 1.5, "paint": 0.5, "dim": 0.5}[op])
                x = {"op": op, "ids": ids, "t0": t0, "dur": dur}
                for k in ("color", "width", "to"):
                    if k in a:
                        x[k] = a[k]
                out.append(x)
                return out, t0 + (min(dur, 0.6) if op == "focus" else dur)
        if "tween" in a:
            out.append({"op": "tween", "vars": a["tween"], "t0": t0, "dur": a["dur"], "ease": a.get("ease", "inout")})
            return out, t0 + a["dur"]
        if "set" in a:
            out.append({"op": "set", "vars": a["set"], "t0": t0, "dur": 0})
            return out, t0
        if "camera" in a:
            dur = a.get("dur", 1.0)
            out.append({"op": "camera", "view": {"x": a["camera"]["x"], "y": a["camera"]["y"],
                                                 **({"free": True} if a["camera"].get("free") else {})}, "t0": t0, "dur": dur})
            return out, t0 + dur
        return out, t0

    @staticmethod
    def blocking_end(a, t0, end):
        """这个动作要让下一句等到什么时候。默认只有真正的运动（tween 图形运动、camera 镜头）要等它做完；
        show 最多等 0.4 秒（刚出现就可以接着讲）；板书擦入、划重点、强调发光、隐藏都不用等（边写边讲）。
        作者写 "wait": true 强制等完，"wait": false 完全不等。
        2026-09-28：原先所有动作都等，板书写字、强调发光把句间拖到 1.6~1.8 秒，用户听着是"明显的停顿"。"""
        w = a.get("wait")
        if w is True:
            return end
        if w is False:
            return t0
        if "tween" in a or "camera" in a:
            return end
        if "show" in a:
            return min(end, t0 + 0.4)
        return t0

    def timeline(self, fake=False):
        T = 0.0
        scenes, actions, subs, stops = [], [], [], []
        pcm_all = bytearray()
        cur_view = self.world.get("view")
        lay_cfg = self.sb.get("layouts") or {}
        for scn in self.scenes:
            sc, lay = scn["src"], scn["layout"]
            lead = sc.get("lead", LEAD[lay])
            sp = self.speech(scn, fake)
            base = T + lead
            shift, cuts = 0.0, []
            db = None if fake else TG.frame_db(sp["pcm"])     # 等动画插静音：只插在真正没声音的地方
            scene_end = base
            beat_ends = []
            if lay == "title":        # 标题卡自动入场
                sfx = "" if si_first(self, scn) else "-" + scn["id"]
                for k, dt, fx, du in (("t-tag", 0.05, "pop", 0.5), ("t-main", 0.25, "fade", 0.6), ("t-sub", 0.6, "fade", 0.6), ("t-line", 0.8, "wipe", 0.9)):
                    if (k + sfx) in self.ui:
                        actions.append({"op": "show", "ids": [k + sfx], "fx": fx, "t0": T + dt, "dur": du})
            if lay == "outro":        # 片尾卡自动入场
                for k, dt, fx, du in (("o-badge", 0.1, "pop", 0.6), ("o-main", 0.45, "fade", 0.6), ("o-sub", 0.8, "fade", 0.6), ("o-line", 1.0, "wipe", 0.9)):
                    actions.append({"op": "show", "ids": [k + "-" + scn["id"]], "fx": fx, "t0": T + dt, "dur": du})
            for bi, beat in enumerate(scn["beats"]):
                busy = 0.0
                for a in beat["src"].get("do", []):
                    ta = self.anchor_time(a.get("at"), beat, sp)
                    t0 = base + ta + shift + a.get("delay", 0)
                    acts, end = self.expand(a, t0)
                    actions.extend(acts)
                    busy = max(busy, self.blocking_end(a, t0, end))
                sp_end = base + beat["sents"][-1]["stop"] + shift
                req = max(busy + 0.35, sp_end + 0.55 + beat["src"].get("hold", 0))
                settled = max(busy + 0.15, sp_end + 0.3)     # 预览抽帧点：本节拍动作做完、字幕还在
                if bi + 1 < len(scn["beats"]):
                    nxt_a = scn["beats"][bi + 1]["sents"][0]["start"]
                    nxt = base + nxt_a + shift
                    if req > nxt:
                        g = req - nxt
                        c = None
                        if db is not None:     # 本节拍末字与下一节拍首字之间最长静音段的中点（时间戳有误差，直接按时间下刀会切进字音）
                            c = TG.quiet_point(db, beat["sents"][-1]["stop"] - 0.5, nxt_a + 0.4, strict=False)
                        cuts.append((c if c is not None else max(0.0, nxt_a - 0.1), g))
                        shift += g
                    beat_ends.append(min(settled, base + nxt_a + shift - 0.1))
                else:
                    scene_end = max(busy + 0.6, sp_end + (OUTRO_TAIL if lay == "outro" else TAIL) + beat["src"].get("hold", 0))
                    beat_ends.append(min(settled, scene_end - 0.45))
            # 字幕：每句一条
            sents = [s for b in scn["beats"] for s in b["sents"]]
            sh = lambda a: a + sum(g for c, g in cuts if c <= a)
            if self.meta.get("subtitles", True) and sc.get("subs", lay != "outro"):   # 片尾卡上字就是口播，不再出字幕
                for k, s in enumerate(sents):
                    t0 = base + sh(s["start"]) - 0.05
                    t_end = base + sh(s["stop"]) + 1.4
                    t_next = (base + sh(sents[k + 1]["start"]) - 0.1) if k + 1 < len(sents) else scene_end - 0.15
                    subs.append({"t0": round(t0, 3), "t1": round(min(t_end, t_next), 3), "html": sub_html(s["disp"])})
            # 音频：开头留白 + 口播（在切点插入静音）+ 结尾补齐
            if not fake:
                seg = bytearray(int(lead * SR) * 2)
                seg += TG.insert_silences(sp["pcm"], cuts)      # 切口两侧 5ms 淡出淡入，防爆音
                need = int((scene_end - T) * SR) * 2
                if len(seg) < need:
                    seg += bytes(need - len(seg))
                else:
                    scene_end = T + len(seg) / 2 / SR
                pcm_all += seg
            # 版式框与视野
            box = view = None
            if lay in ("problem", "board"):
                box = (sc.get("box") or (lay_cfg.get(lay) or {}).get("box") or DEFAULT_BOX[lay])
                if lay == "problem":
                    view = sc.get("view") or (lay_cfg.get("problem") or {}).get("view") or self.world.get("view")
                else:
                    view = sc.get("view") or cur_view or (lay_cfg.get("board") or {}).get("view") or self.world.get("view")
                cams = [x for x in actions if x["op"] == "camera" and T <= x["t0"] < scene_end]
                cur_view = cams[-1]["view"] if cams else view
            prev_lay = scenes[-1]["layout"] if scenes else None
            scenes.append({"id": scn["id"], "layout": lay, "t0": round(T, 3), "t1": round(scene_end, 3),
                           "world": sc.get("world", lay in ("problem", "board")), "board": lay == "board",
                           "box": box, "view": view,
                           # 题干 -> 讲台：等图搬得差不多了再亮出板书面板，免得图从面板底下穿过
                           "fin_delay": 0.55 if (prev_lay == "problem" and lay == "board") else 0,
                           **({"chap": self.chapters.index(scn["id"])} if scn["id"] in self.chapters else {})})
            stops.extend((scn["id"], bi, round(x, 3)) for bi, x in enumerate(beat_ends))
            T = scene_end
        dur = T + 0.3
        if not fake:
            pcm_all += bytes(int(0.3 * SR) * 2)
        world = dict(self.world)
        objs = []
        for o in self.world.get("objects", []):
            o2 = dict(o)
            if o.get("text") is not None:
                # {#} = 实时读数的位置（配 num 表达式、digits 小数位），放在 $..$ 外面
                o2["html"] = rich(str(o["text"])).replace("{#}", '<span class="nv"></span>')
            if o.get("type") == "axes":          # 轴名 x、y 与原点 O（写 "" 不显示）
                o2["htmls"] = [rich(o.get(k, d)) if o.get(k, d) else "" for k, d in (("xlabel", "$x$"), ("ylabel", "$y$"), ("olabel", "$O$"))]
            if o.get("type") == "ticks":
                o2["htmls"] = [rich(str(x)) for x in o.get("labels", [])]
            objs.append(o2)
        world["objects"] = objs
        wd = self.sb.get("widgets") or {}
        tl = {"fps": self.fps, "duration": round(dur, 3), "scenes": scenes, "actions": actions, "subs": subs,
              "world": world, "widgets": {"timebar": wd.get("timebar"), "meter": wd.get("meter")}, "stops": stops,
              "theme": self.meta.get("theme", "light"), "fade_in": 0.5,
              "fade_out": 1.4 if any(s["layout"] == "outro" for s in self.scenes) else 0.6}
        return tl, (bytes(pcm_all) if not fake else None)

    # ============================================================ 页面
    def write_page(self, tl, name="video.html"):
        assets = ASSETS.as_uri()
        css = (RUNTIME / "style.css").read_text(encoding="utf-8").replace("{{ASSETS}}", assets)
        data = json.dumps(tl, ensure_ascii=False)
        page = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
                '<link rel="stylesheet" href="%s/katex/katex.min.css"><style>%s</style>'
                '<script src="%s/katex/katex.min.js"></script></head><body>'
                '<div id="stage" class="%s"><div id="bg"></div><div id="paper"></div>'
                '<div id="worldwrap"><svg id="world" width="1920" height="1080" xmlns="http://www.w3.org/2000/svg"></svg><div id="wlabels"></div></div>'
                '<div id="ui">%s<div id="sub"><div class="txt"></div></div></div>'
                '<div id="brand"><img src="%s/%s"></div><div id="progress">%s</div><div id="fade"></div></div>'
                '<script>window.__DATA__ = %s;</script><script src="%s/engine.js"></script></body></html>') % (
            assets, css, assets, "dark" if tl.get("theme") == "dark" else "light", self.ui_html,
            assets, BRAND_LOGO[self.theme], "<i></i>" * len(self.chapters), data, RUNTIME.as_uri())
        p = self.build / name
        p.write_text(page, encoding="utf-8")
        return p


def si_first(bd, scn):
    """第一个标题卡场景的元素 id 不带后缀（t-tag 等），其余标题卡带场景后缀"""
    firsts = [s for s in bd.scenes if s["layout"] == "title"]
    return firsts and firsts[0] is scn


# ============================================================ 浏览器
def open_page(pw, html_path):
    try:
        br = pw.chromium.launch(channel="chrome", headless=True)
    except Exception:
        br = pw.chromium.launch(headless=True)
    pg = br.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    pg.goto(Path(html_path).as_uri())
    info = pg.evaluate("window.__init()")
    if errs:
        log("[页面错误] " + " | ".join(errs[:5]))
    return br, pg, info


def shot(cdp):
    r = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
    return base64.b64decode(r["data"])


def _render_chunk(html_path, i0, i1, fps, seg_path, prog_path):
    """一段帧（单独的子进程里跑）：每 15 帧往 prog_path 写一次进度，写完写 done——看门狗靠它判断卡没卡住"""
    from playwright.sync_api import sync_playwright
    ff = ffmpeg_exe()
    prog = Path(prog_path)
    with sync_playwright() as pw:
        br, pg, info = open_page(pw, html_path)
        cdp = pg.context.new_cdp_session(pg)
        # x264 默认线程数按 CPU 核数开，10 路并行时每路吃 1 GB 多（白板课 9-28 把 31GB 内存占满）→ 每路限 3 线程
        proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-threads", "1", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                                 "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-threads", "3",
                                 "-x264-params", "keyint=%d" % (fps * 4), str(seg_path)], stdin=subprocess.PIPE)
        last_sig, img, fresh = None, None, 0
        for i in range(i0, i1):
            sig = pg.evaluate("window.seek(%.5f)" % (i / fps))
            if sig != last_sig or img is None:
                img = shot(cdp)
                last_sig = sig
                fresh += 1
            proc.stdin.write(img)
            if (i - i0) % 15 == 0:
                prog.write_text("%d %d" % (i - i0 + 1, fresh), encoding="utf-8")
        proc.stdin.close()
        proc.wait()
        br.close()
    prog.write_text("%d %d done" % (i1 - i0, fresh), encoding="utf-8")


# 分段渲染 + 看门狗（2026-09-30 从白板课 engine 移植）：原来一个进程一大段、进程池 map 死等，
# 别的程序把内存吃到只剩 4GB 时有几路浏览器卡死，整片渲染挂了一个半小时没人知道。
# 现在 450 帧一段、每段一个子进程，75 秒没进度就杀掉整棵进程树重渲，最多 3 次
CHUNK = 450
STALL = 75
RETRY = 3


def _kill_tree(p):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()


def _run_chunk_watched(job, state):
    html_path, i0, i1, fps, seg = job
    prog = Path(seg).with_suffix(".prog")
    for attempt in range(1, RETRY + 1):
        if prog.exists():
            prog.unlink()
        logf = open(Path(seg).with_suffix(".log"), "w", encoding="utf-8")
        p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_chunk", html_path, str(i0), str(i1), str(fps), seg, str(prog)],
                             stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        last, last_t = None, time.time()
        while True:
            try:
                rc = p.wait(timeout=3)
                break
            except subprocess.TimeoutExpired:
                rc = None
            cur = prog.read_text(encoding="utf-8") if prog.exists() else ""
            if cur != last:
                last, last_t = cur, time.time()
                try:
                    state[seg] = int(cur.split()[0])
                except (ValueError, IndexError):
                    pass
            elif time.time() - last_t > STALL:
                _kill_tree(p)
                p.wait()
                rc = "stall"
                break
        logf.close()
        txt = prog.read_text(encoding="utf-8") if prog.exists() else ""
        if rc == 0 and txt.endswith("done"):
            state[seg] = i1 - i0
            return i1 - i0, int(txt.split()[1])
        log("  [看门狗] 段 %s 第 %d 次%s，重渲" % (Path(seg).stem, attempt, "卡住（%d 秒没进度）" % STALL if rc == "stall" else "出错(%s)" % rc))
        state[seg] = 0
    raise RuntimeError("段 %s 连续 %d 次失败，看 %s" % (Path(seg).stem, RETRY, Path(seg).with_suffix(".log")))


def black_frames(video, fps):
    """逐帧扫成片（缩到 96×54）：浅色版式里不该有黑屏帧；有就是渲染出了毛病。返回这些帧的时刻"""
    import numpy as np
    raw = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", str(video), "-vf", "scale=96:54", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, 54, 96, 3)
    return [round(i / fps, 2) for i in np.where(f.mean(axis=(1, 2, 3)) < 12)[0]]


def free_gb():
    """空闲物理内存（GB）；拿不到返回 None（从白板课 build.py 移植）"""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullAvailPhys / 1024 ** 3
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024 ** 3
    except Exception:
        return None


def level_filter(wav, target=-16.0, peak_db=-1.5):
    """全片统一响度：先量整体响度，再全片乘同一个增益，只有个别尖峰由限幅器压一下。
    单遍 loudnorm 是动态模式（随时间自动调音量），白板课 9-28 片子前后音量差到 2.5 分贝，用户听着"前后声音不一致"。"""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", "-i", str(wav), "-af", "loudnorm=I=%s:TP=%s:LRA=11:print_format=json" % (
        target, peak_db), "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    err = r.stderr
    m = json.loads(err[err.rfind("{"):err.rfind("}") + 1])
    g = target - float(m["input_i"])
    log("  响度：原片 %.1f LUFS，全片统一增益 %+.1f 分贝" % (float(m["input_i"]), g))
    return "volume=%.2fdB,alimiter=limit=%.4f:attack=5:release=60:level=disabled" % (g, 10 ** (peak_db / 20))


def render(bd, fake=False, workers=None):
    t_start = time.time()
    tl, pcm = bd.timeline(fake)
    html_path = bd.write_page(tl)
    fps = bd.fps
    n = int(math.ceil(tl["duration"] * fps))
    workers = workers or min(10, max(2, (os.cpu_count() or 4) // 2))
    # 别的程序（如别的会话的 Remotion、白板课渲染）在吃内存时按空闲内存定路数：每路浏览器 + 编码器约 1.3 GB，留 2 GB 余量
    fg = free_gb()
    if fg is not None:
        fit = max(1, int((fg - 2) // 1.3))
        if fit < workers:
            log("  空闲内存只有 %.1f GB，并行从 %d 路降到 %d 路" % (fg, workers, fit))
            workers = fit
    segdir = bd.build / "segs"
    segdir.mkdir(exist_ok=True)
    for f in list(segdir.glob("*.mp4")) + list(segdir.glob("*.prog")) + list(segdir.glob("*.log")):
        f.unlink()
    jobs = [(str(html_path), i0, min(n, i0 + CHUNK), fps, str(segdir / ("seg_%03d.mp4" % k)))
            for k, i0 in enumerate(range(0, n, CHUNK))]
    log("渲染 %d 帧（%.1f 秒），%d 段 × %d 进程并行 ..." % (n, tl["duration"], len(jobs), workers))
    from concurrent.futures import ThreadPoolExecutor
    state, tot_fresh = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_run_chunk_watched, j, state) for j in jobs]
        last_log = time.time()
        while not all(f.done() for f in futs):
            time.sleep(2)
            if time.time() - last_log > 30:
                last_log = time.time()
                d = sum(state.values())
                log("  进度 %d/%d 帧（%.0f%%），已用 %.0f 秒" % (d, n, 100 * d / max(1, n), time.time() - t_start))
        for f in futs:
            tot_fresh += f.result()[1]
    log("  实拍 %d 帧，复用 %d 帧，用时 %.0f 秒" % (tot_fresh, n - tot_fresh, time.time() - t_start))
    ff = ffmpeg_exe()
    lst = segdir / "list.txt"
    lst.write_text("".join("file '%s'\n" % Path(j[4]).as_posix() for j in jobs), encoding="utf-8")
    silent = bd.build / "video_silent.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    bad = black_frames(silent, fps)
    if bad:
        raise RuntimeError("成片里有 %d 帧黑屏（%.1f 秒起），别交付" % (len(bad), bad[0]))
    log("  成片逐帧扫描：没有黑屏帧")
    out = bd.dir / bd.meta.get("out", bd.path.stem + ".mp4")
    if pcm:
        wav = bd.build / "narration.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)
        # 响度到网络视频常用的 -16 LUFS、峰值 -1.5 dB：全片同一个增益（不用单遍 loudnorm 的动态调音量）
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
                        "-af", level_filter(wav), "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    else:
        out = bd.dir / (Path(bd.meta.get("out", bd.path.stem + ".mp4")).stem + "_无声预览.mp4")
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(silent), "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    (bd.build / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    log("成片：%s（%.1f 秒，总用时 %.0f 秒）" % (out, tl["duration"], time.time() - t_start))
    return out


def preview(bd, fake=False, times=None, sheet=True):
    from playwright.sync_api import sync_playwright
    tl, _ = bd.timeline(fake)
    html_path = bd.write_page(tl)
    pdir = bd.build / "preview"
    pdir.mkdir(exist_ok=True)
    for f in pdir.glob("*.png"):
        f.unlink()
    if times:
        pts = [("t", i, float(x)) for i, x in enumerate(times)]
    else:
        pts = [(sid, bi, x) for sid, bi, x in tl["stops"]]
    files = []
    with sync_playwright() as pw:
        br, pg, info = open_page(pw, html_path)
        cdp = pg.context.new_cdp_session(pg)
        for sid, bi, x in pts:
            pg.evaluate("window.seek(%.4f)" % x)
            p = pdir / ("%s_%02d_%06.2f.png" % (sid, bi, x))
            p.write_bytes(shot(cdp))
            files.append(p)
        br.close()
    log("预览帧 %d 张 -> %s（时长 %.1f 秒）" % (len(files), pdir, tl["duration"]))
    if sheet and len(files) > 1:
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
        for k in range(0, len(files), 4):
            grp = files[k:k + 4]
            im = Image.new("RGB", (1920, 1080), "black")
            for j, f in enumerate(grp):
                s = Image.open(f).resize((960, 540))
                im.paste(s, ((j % 2) * 960, (j // 2) * 540))
                d = ImageDraw.Draw(im)
                d.rectangle([(j % 2) * 960, (j // 2) * 540, (j % 2) * 960 + 330, (j // 2) * 540 + 28], fill="black")
                d.text(((j % 2) * 960 + 6, (j // 2) * 540 + 3), f.stem, fill="yellow", font=font)
            sp = pdir / ("_sheet_%02d.png" % (k // 4 + 1))
            im.save(sp)
        log("拼图：%s/_sheet_*.png" % pdir)
    return files


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "_chunk":      # 渲染子进程（由 _run_chunk_watched 启动）
        _, _, html_path, i0, i1, fps, seg, prog = sys.argv
        _render_chunk(html_path, int(i0), int(i1), int(fps), seg, prog)
        return
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    sb_path, cmd = sys.argv[1], sys.argv[2]
    rest = sys.argv[3:]
    fake = "--fake" in rest
    rest = [r for r in rest if r != "--fake"]
    bd = Board(sb_path)
    if cmd == "check":
        sys.exit(0 if bd.check() else 1)
    if not bd.check():
        sys.exit("check 有 ERROR，先改分镜")
    if cmd == "tts":
        bd.tts(force="--force" in rest)
    elif cmd == "preview":
        preview(bd, fake, [float(x) for x in rest] or None)
    elif cmd == "render":
        render(bd, fake)
    elif cmd == "all":
        bd.tts()
        render(bd, False)
    elif cmd == "page":
        tl, _ = bd.timeline(fake)
        log(bd.write_page(tl))
    else:
        sys.exit("未知命令 " + cmd)


if __name__ == "__main__":
    main()
