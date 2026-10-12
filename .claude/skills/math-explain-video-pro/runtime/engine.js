/* 讲题视频 Pro 运行时：确定性时间轴渲染器
 *
 * Python 端把分镜解析成绝对时间轴（window.__DATA__），页面加载后调 window.__init()，
 * 之后每帧调 window.seek(t)：画面是 t 的纯函数，返回状态签名（与上一帧相同 = 画面没变，可直接复用上一帧）。
 *
 * 画面三层：背景 → 几何世界（SVG 图形 + HTML 标签，坐标由表达式精确算出）→ 界面（标题卡/题干/板书/时间条/字幕/总结）。
 * 所有可控元素都有 id，动作 show/hide/focus/paint/dim 对几何图元和界面元素一视同仁。
 */
'use strict';
(function () {
  const DATA = window.__DATA__;
  const W = 1920, H = 1080;
  // 调色板按主题取（与 style.css 的变量一致）。white 在浅色主题里就是墨色（默认线色），hl = 讨论中的边界高亮色，focus = 默认强调色
  const PALS = {
    light: { ink: '#2b3a46', white: '#2b3a46', blue: '#2f7edb', orange: '#f08029', yellow: '#ffc940', gold: '#c98a00', green: '#2da46a',
             red: '#e5484d', gray: '#8795a1', cyan: '#00a5a5', teal: '#00a5a5', purple: '#7b61d1', hl: '#e5484d', focus: '#f29d00', paper: '#fdfdfb' },
    dark:  { ink: '#eef3f8', white: '#eef3f8', blue: '#5ec8f2', orange: '#ff9a5c', yellow: '#ffd23f', gold: '#ffd23f', green: '#6fdc8c',
             red: '#ff6b7f', gray: '#8ea3ba', cyan: '#4fe3d6', teal: '#4fe3d6', purple: '#b794ff', hl: '#ffffff', focus: '#ffd23f', paper: '#132a40' }
  };
  const PAL = PALS[DATA.theme] || PALS.light;
  const col = c => (c && PAL[c]) || c || PAL.ink;
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const EASE = {
    linear: k => k,
    inout: k => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
    out: k => 1 - Math.pow(1 - k, 3),
    in: k => k * k * k,
    back: k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); }
  };
  const ease = (name, k) => (EASE[name] || EASE.inout)(clamp(k));

  function rgb(c) {
    c = col(c);
    if (c.startsWith('rgb')) return c.match(/[\d.]+/g).slice(0, 3).map(Number);
    let h = c.replace('#', '');
    if (h.length === 3) h = h.split('').map(x => x + x).join('');
    return [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16));
  }
  function mix(c1, c2, k) {
    const a = rgb(c1), b = rgb(c2);
    return 'rgb(' + a.map((x, i) => Math.round(lerp(x, b[i], clamp(k)))).join(',') + ')';
  }
  const q = (x, d = 3) => (Math.abs(x) < 1e-9 ? '0' : x.toFixed(d));

  // ---------------------------------------------------------------- 表达式与点
  const VARS = Object.keys((DATA.world && DATA.world.vars) || {});
  const MATHFN = 'const {sin,cos,tan,sqrt,abs,min,max,PI,atan2,floor,round,pow,log,log2,exp}=Math;';
  // world.funcs：分镜自带的辅助函数（JS 函数源码），表达式里直接调用。物理题的"水深随珠串位置变"这类要解方程的量放这里。
  // 同一作用域里依次定义，函数之间可以互相调用
  const FSRC = (DATA.world && DATA.world.funcs) || {};
  const FNAMES = Object.keys(FSRC);
  const FUNCS = FNAMES.length ? new Function(MATHFN + FNAMES.map(k => 'const ' + k + ' = (' + FSRC[k] + ');').join('\n') +
                                             '\nreturn {' + FNAMES.join(',') + '};')() : {};
  const FDECL = FNAMES.length ? 'const {' + FNAMES.join(',') + '}=FN;' : '';
  let AREA = () => 0;
  // 表达式里可用：变量名、Math 函数、area('图元')、cx/cy('图元') 形心坐标、px/py('点') 点坐标、
  // vx(0)/vx(1)、vy(0)/vy(1) 当前镜头视野的左右/下上边（坐标轴、带状区域跟着镜头伸缩）
  const HELP = {
    area: id => AREA(id),
    cx: id => centroid(GEO[id] && GEO[id].poly)[0], cy: id => centroid(GEO[id] && GEO[id].poly)[1],
    px: n => CUR[n][0], py: n => CUR[n][1],
    vx: i => VIEW.x[i], vy: i => VIEW.y[i]
  };
  function cexpr(e) {
    if (typeof e === 'number') return () => e;
    const f = new Function('v', 'H', 'FN', 'const {area,cx,cy,px,py,vx,vy}=H;' + FDECL + (VARS.length ? 'const {' + VARS.join(',') + '}=v;' : '') + MATHFN + 'return (' + e + ');');
    return v => f(v, HELP, FUNCS);
  }
  const PTS = {};
  const CUR = {};   // 当前帧各点世界坐标
  for (const [k, v] of Object.entries((DATA.world && DATA.world.points) || {})) PTS[k] = [cexpr(v[0]), cexpr(v[1])];

  const GEO = {};   // 当前帧各图元的世界几何（多边形顶点等），供 centroid()/area() 引用
  function splitArgs(s) {
    const out = []; let depth = 0, cur = '';
    for (const ch of s) {
      if (ch === '(' || ch === '[') depth++;
      if (ch === ')' || ch === ']') depth--;
      if (ch === ',' && depth === 0) { out.push(cur.trim()); cur = ''; } else cur += ch;
    }
    if (cur.trim()) out.push(cur.trim());
    return out;
  }
  // 点引用 -> (v) => [x, y]：点名 / [ex, ey] / mid(A,B) / lerp(A,B,k) / off(A,dx,dy) / centroid(id) / foot(P,A,B)
  function cref(ref) {
    if (Array.isArray(ref)) { const fx = cexpr(ref[0]), fy = cexpr(ref[1]); return v => [fx(v), fy(v)]; }
    if (typeof ref !== 'string') throw new Error('bad point ref ' + JSON.stringify(ref));
    const m = ref.match(/^(\w+)\((.*)\)$/);
    if (!m) {
      if (!PTS[ref]) throw new Error('未定义的点 ' + ref);
      return () => CUR[ref];
    }
    const fn = m[1], args = splitArgs(m[2]);
    if (fn === 'mid') { const a = cref(args[0]), b = cref(args[1]); return v => { const p = a(v), r = b(v); return [(p[0] + r[0]) / 2, (p[1] + r[1]) / 2]; }; }
    if (fn === 'lerp') { const a = cref(args[0]), b = cref(args[1]), k = cexpr(args[2]); return v => { const p = a(v), r = b(v), kk = k(v); return [lerp(p[0], r[0], kk), lerp(p[1], r[1], kk)]; }; }
    if (fn === 'off') { const a = cref(args[0]), dx = cexpr(args[1]), dy = cexpr(args[2]); return v => { const p = a(v); return [p[0] + dx(v), p[1] + dy(v)]; }; }
    if (fn === 'centroid') { const id = args[0]; return () => centroid(GEO[id] && GEO[id].poly); }
    if (fn === 'foot') {
      const p = cref(args[0]), a = cref(args[1]), b = cref(args[2]);
      return v => { const P = p(v), A = a(v), B = b(v); const dx = B[0] - A[0], dy = B[1] - A[1]; const k = ((P[0] - A[0]) * dx + (P[1] - A[1]) * dy) / (dx * dx + dy * dy); return [A[0] + k * dx, A[1] + k * dy]; };
    }
    throw new Error('未知点函数 ' + fn);
  }

  // ---------------------------------------------------------------- 几何工具
  function polyArea(poly) {
    if (!poly || poly.length < 3) return 0;
    let s = 0;
    for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; s += a[0] * b[1] - b[0] * a[1]; }
    return Math.abs(s) / 2;
  }
  function centroid(poly) {
    if (!poly || !poly.length) return [0, 0];
    if (poly.length < 3) return poly.reduce((s, p) => [s[0] + p[0] / poly.length, s[1] + p[1] / poly.length], [0, 0]);
    let a = 0, cx = 0, cy = 0;
    for (let i = 0; i < poly.length; i++) {
      const p = poly[i], r = poly[(i + 1) % poly.length], c = p[0] * r[1] - r[0] * p[1];
      a += c; cx += (p[0] + r[0]) * c; cy += (p[1] + r[1]) * c;
    }
    if (Math.abs(a) < 1e-9) return poly.reduce((s, p) => [s[0] + p[0] / poly.length, s[1] + p[1] / poly.length], [0, 0]);
    return [cx / (3 * a), cy / (3 * a)];
  }
  function signedArea(poly) {
    let s = 0;
    for (let i = 0; i < poly.length; i++) { const a = poly[i], b = poly[(i + 1) % poly.length]; s += a[0] * b[1] - b[0] * a[1]; }
    return s / 2;
  }
  // Sutherland–Hodgman：subject 被凸多边形 clip 裁剪
  function clipPoly(subject, clip) {
    if (!subject || !clip || subject.length < 3 || clip.length < 3) return [];
    const ccw = signedArea(clip) > 0;
    const inside = (p, a, b) => { const c = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]); return ccw ? c >= -1e-9 : c <= 1e-9; };
    const inter = (p, r, a, b) => {
      const x1 = p[0], y1 = p[1], x2 = r[0], y2 = r[1], x3 = a[0], y3 = a[1], x4 = b[0], y4 = b[1];
      const den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
      if (Math.abs(den) < 1e-12) return r;
      const tt = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den;
      return [x1 + tt * (x2 - x1), y1 + tt * (y2 - y1)];
    };
    let out = subject.slice();
    for (let i = 0; i < clip.length && out.length; i++) {
      const a = clip[i], b = clip[(i + 1) % clip.length], inp = out; out = [];
      for (let j = 0; j < inp.length; j++) {
        const p = inp[j], r = inp[(j + 1) % inp.length], pin = inside(p, a, b), rin = inside(r, a, b);
        if (pin) { out.push(p); if (!rin) out.push(inter(p, r, a, b)); } else if (rin) { out.push(inter(p, r, a, b)); }
      }
    }
    // 去掉重合顶点
    const res = [];
    for (const p of out) { const l = res[res.length - 1]; if (!l || Math.hypot(l[0] - p[0], l[1] - p[1]) > 1e-7) res.push(p); }
    if (res.length > 1 && Math.hypot(res[0][0] - res[res.length - 1][0], res[0][1] - res[res.length - 1][1]) < 1e-7) res.pop();
    return polyArea(res) < 1e-9 ? [] : res;
  }
  AREA = id => polyArea(GEO[id] && GEO[id].poly);

  // ---------------------------------------------------------------- 画布映射（世界 -> 屏幕）
  let BOX = { x: 0, y: 0, w: W, h: H }, VIEW = { x: [-10, 10], y: [-5, 5] }, SC = 1, SCX = 1, SCY = 1, OX = 0, OY = 0;
  // 视野默认横纵同比例（几何图不变形）；view.free=true 时横纵各自铺满画框（函数图像用：x 以弧度计、y 范围小）
  function setMapping(box, view) {
    BOX = box; VIEW = view;
    const vw = view.x[1] - view.x[0], vh = view.y[1] - view.y[0];
    if (view.free) {
      SCX = box.w / vw; SCY = box.h / vh; SC = Math.min(SCX, SCY);
      OX = box.x; OY = box.y;
    } else {
      SC = SCX = SCY = Math.min(box.w / vw, box.h / vh);
      OX = box.x + (box.w - SC * vw) / 2;
      OY = box.y + (box.h - SC * vh) / 2;
    }
  }
  const S = p => [OX + (p[0] - VIEW.x[0]) * SCX, OY + (VIEW.y[1] - p[1]) * SCY];
  const pathOf = (pts, close) => pts.length ? 'M' + pts.map(p => q(p[0], 2) + ' ' + q(p[1], 2)).join('L') + (close ? 'Z' : '') : '';

  // ---------------------------------------------------------------- DOM
  const $ = s => document.querySelector(s);
  const NS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };

  function renderMathIn(root) {
    root.querySelectorAll('.math').forEach(el => {
      if (el.dataset.done) return;
      try { katex.render(el.textContent, el, { throwOnError: false, output: 'html' }); } catch (e) { /* 留原文 */ }
      el.dataset.done = '1';
    });
  }

  // ---------------------------------------------------------------- 世界图元
  const OBJ = {};        // id -> 图元运行时
  const ORDER = [];
  const DEF_STYLE = {
    polygon: { stroke: 'ink', width: 3, fill: null, fillOpacity: 0.12 },
    region: { stroke: null, width: 0, fill: 'yellow', fillOpacity: 0.4 },
    clip: { stroke: 'gold', width: 2.5, fill: 'yellow', fillOpacity: 0.45 },
    segment: { stroke: 'ink', width: 3 },
    polyline: { stroke: 'ink', width: 3 },
    arrow: { stroke: 'gray', width: 3 },
    angle: { stroke: 'gold', width: 2.5 },
    right: { stroke: 'ink', width: 2 },
    dim: { stroke: 'gray', width: 2 },
    point: { stroke: null, fill: 'ink', r: 5 },
    label: {},
    text: {},
    curve: { stroke: 'blue', width: 3.5 },
    pcurve: { stroke: 'ink', width: 3 },
    axes: { stroke: 'gray', width: 2.2 },
    ticks: { stroke: 'gray', width: 2 }
  };
  const LINEISH = ['polygon', 'region', 'clip', 'segment', 'polyline', 'arrow', 'angle', 'right', 'dim', 'curve', 'pcurve', 'axes', 'ticks'];
  // 函数图像：fx 是 x 的表达式（可用变量、Math 函数），x 为定义区间 [起, 止]（表达式）
  // 曲线表达式里也能用 px/py('点')、vx/vy 等（例：以 M 为圆心、过 A 的圆：fx "px('M')+R*cos(t)"）
  function cfun(e, arg = 'x') {
    const f = new Function(arg, 'v', 'FN', 'H', 'const {area,cx,cy,px,py,vx,vy}=H;' + FDECL + (VARS.length ? 'const {' + VARS.join(',') + '}=v;' : '') + MATHFN + 'return (' + e + ');');
    return (x, v) => { try { return f(x, v, FUNCS, HELP); } catch (err) { return NaN; } };
  }

  function initWorld() {
    const svg = $('#world');
    const defs = svgEl('defs', {}, svg);
    const f = svgEl('filter', { id: 'glow', x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    svgEl('feGaussianBlur', { stdDeviation: '7' }, f);
    const labels = $('#wlabels');
    for (const o of (DATA.world && DATA.world.objects) || []) {
      const st = Object.assign({}, DEF_STYLE[o.type] || {}, o);
      const R = { def: o, st, id: o.id, type: o.type };
      const g = svgEl('g', { 'data-id': o.id }, svg);
      R.g = g;
      if (LINEISH.includes(o.type)) {
        R.glow = svgEl('path', { fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', filter: 'url(#glow)', opacity: 0 }, g);
        R.fillEl = svgEl('path', { stroke: 'none' }, g);
        R.path = svgEl('path', { fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, g);
        if (o.type === 'arrow' || ((o.type === 'dim' || o.type === 'axes') && o.arrows !== false) || (o.type === 'pcurve' && o.arrow)) R.head = svgEl('path', { stroke: 'none' }, g);
      }
      if (o.type === 'point') {
        R.glow = svgEl('circle', { r: 14, filter: 'url(#glow)', opacity: 0 }, g);
        R.dot = svgEl('circle', { r: st.r || 5 }, g);
      }
      // 坐标轴名（x / y / O）、刻度值：一组标签（HTML 由 Python 端预先排好，放在 htmls 里）
      if (o.type === 'axes' || o.type === 'ticks') {
        R.labs = (o.htmls || []).map(hh => {
          const d = document.createElement('div');
          d.className = 'wl ' + (o.cls || (o.type === 'axes' ? 'axl' : 'tkl'));
          d.innerHTML = hh || '';
          d.dataset.id = o.id;
          labels.appendChild(d);
          return d;
        });
      }
      if (o.type === 'curve') {
        R.fx = cfun(o.fx);
        R.x0 = cexpr(o.x[0]); R.x1 = cexpr(o.x[1]);
      }
      // 电流流动：flow 表达式 = 沿线走过的距离（px），配 dash 点状虚线，点子就顺着线走（负值反向走）
      if (o.flow !== undefined) R.flowf = cexpr(o.flow);
      if (o.type === 'pcurve') {      // 参数曲线：x=fx(t), y=fy(t)，t 从 t[0] 到 t[1]（单位圆、角弧、转圈的螺线）
        R.fx = cfun(o.fx, 't'); R.fy = cfun(o.fy, 't');
        R.t0 = cexpr(o.t[0]); R.t1 = cexpr(o.t[1]);
      }
      if (o.type === 'axes') {
        R.ax = (o.x || [-1, 1]).map(cexpr); R.ay = (o.y || [-1, 1]).map(cexpr); R.ao = (o.origin || [0, 0]).map(cexpr);
      }
      if (o.type === 'ticks') { R.tk = (o.at || []).map(cexpr); R.on = cexpr(o.on === undefined ? 0 : o.on); }
      if (o.type === 'label' || o.type === 'text' || ((o.type === 'angle' || o.type === 'dim') && o.text)) {
        const d = document.createElement('div');
        d.className = 'wl ' + (o.cls || (o.type === 'label' ? 'pt' : o.type === 'dim' ? 'dimt' : o.type === 'angle' ? 'angt' : 'wt'));
        d.innerHTML = o.html || '';
        d.dataset.id = o.id;
        labels.appendChild(d);
        R.lab = d;
        // 实时读数：text 里的 {#} 换成 num 表达式的值（传感器示数、水深……随变量逐帧变）
        if (o.num !== undefined) { R.numf = cexpr(o.num); R.nv = d.querySelector('.nv'); R.digits = o.digits === undefined ? 2 : o.digits; }
      }
      // 预编译几何引用
      const pts = o.pts ? o.pts.map(cref) : null;
      R.pts = pts;
      if (o.at) R.at = cref(o.at);
      if (o.from) R.from = cref(o.from);
      if (o.to) R.to = cref(o.to);
      OBJ[o.id] = R;
      ORDER.push(R);
    }
    renderMathIn(labels);
  }

  // 每帧：计算世界几何（全部图元，含不可见的，供 area()/centroid() 引用）
  function computeGeometry(v) {
    for (const k in PTS) CUR[k] = [PTS[k][0](v), PTS[k][1](v)];
    for (const R of ORDER) {
      const o = R.def, G = {};
      if (o.type === 'polygon' || o.type === 'region' || o.type === 'polyline') G.poly = R.pts.map(f => f(v));
      else if (o.type === 'clip') G.poly = o.of.slice(1).reduce((acc, id) => clipPoly(acc, GEO[id] && GEO[id].poly), (GEO[o.of[0]] && GEO[o.of[0]].poly) || []);
      else if (o.type === 'segment' || o.type === 'dim') {
        let [a, b] = R.pts.map(f => f(v));
        if (o.ext) { const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1; a = [a[0] - dx / L * o.ext[0], a[1] - dy / L * o.ext[0]]; b = [b[0] + dx / L * o.ext[1], b[1] + dy / L * o.ext[1]]; }
        G.poly = [a, b];
      } else if (o.type === 'arrow') G.poly = [R.from(v), R.to(v)];
      else if (o.type === 'angle' || o.type === 'right') G.poly = R.pts.map(f => f(v));
      else if (o.type === 'point' || o.type === 'label' || o.type === 'text') { G.at = R.at(v); if (R.numf) G.num = R.numf(v); }
      else if (o.type === 'curve') { G.x0 = R.x0(v); G.x1 = R.x1(v); G.v = v; }
      else if (o.type === 'pcurve') { G.t0 = R.t0(v); G.t1 = R.t1(v); G.v = v; }
      else if (o.type === 'axes') { G.x = R.ax.map(f => f(v)); G.y = R.ay.map(f => f(v)); G.o = R.ao.map(f => f(v)); }
      else if (o.type === 'ticks') { G.at = R.tk.map(f => f(v)); G.on = R.on(v); }
      if (R.flowf) G.flow = R.flowf(v);
      GEO[o.id] = G;
    }
  }

  // ---------------------------------------------------------------- 动作 -> 通道
  // 每个目标 id 的通道：vis（可见度 + 出现方式）、emph（强调包络）、paint（持久改色/线宽）、dim（压暗）
  const CH = {};       // id -> {shows:[], focus:[], paint:[], dim:[]}
  const TWEENS = [];   // 变量补间/赋值，按时间排序
  const CAMS = [];     // 镜头
  const chOf = id => (CH[id] = CH[id] || { vis: [], focus: [], paint: [], dim: [] });
  function initActions() {
    for (const a of DATA.actions) {
      const ids = a.ids || [];
      if (a.op === 'show' || a.op === 'hide') ids.forEach(id => chOf(id).vis.push(a));
      else if (a.op === 'focus') ids.forEach(id => chOf(id).focus.push(a));
      else if (a.op === 'paint') ids.forEach(id => chOf(id).paint.push(a));
      else if (a.op === 'dim') ids.forEach(id => chOf(id).dim.push(a));
      else if (a.op === 'tween' || a.op === 'set') TWEENS.push(a);
      else if (a.op === 'camera') CAMS.push(a);
    }
    for (const id in CH) for (const k in CH[id]) CH[id][k].sort((x, y) => x.t0 - y.t0);
    TWEENS.sort((x, y) => x.t0 - y.t0);
    CAMS.sort((x, y) => x.t0 - y.t0);
  }
  const prog = (a, t) => (a.dur > 0 ? clamp((t - a.t0) / a.dur) : (t >= a.t0 ? 1 : 0));

  function varsAt(t) {
    const v = Object.assign({}, DATA.world.vars || {});
    for (const a of TWEENS) {
      if (t < a.t0) break;
      const p = a.op === 'set' ? 1 : ease(a.ease || 'inout', prog(a, t));
      for (const k in a.vars) v[k] = lerp(a.from && a.from[k] !== undefined ? a.from[k] : v[k], a.vars[k], p);
    }
    return v;
  }
  // 补间的起点值 = 开始时刻的变量值（预先算好，避免重叠补间互相污染）
  function bakeTweenFrom() {
    for (const a of TWEENS) {
      if (a.op !== 'tween') continue;
      const v = varsAt(a.t0 - 1e-6);
      a.from = {};
      for (const k in a.vars) a.from[k] = v[k];
    }
  }

  // 目标状态：alpha 不透明度、draw 描出进度、scale 弹出缩放、wipe 擦入进度、emph 强调 0~1、ecol 强调色、paint 改色、dim 压暗
  function stateOf(id, t, initVis) {
    const c = CH[id];
    const s = { alpha: initVis ? 1 : 0, draw: 1, scale: 1, wipe: 1, emph: 0, ecol: 'focus', color: null, width: null, dim: 1, sig: '' };
    if (!c) return s;
    for (const a of c.vis) {
      if (t < a.t0) break;
      const p = prog(a, t);
      if (a.op === 'show') {
        const e = ease(a.ease || (a.fx === 'draw' ? 'inout' : 'out'), p);
        if (a.fx === 'draw') { s.alpha = Math.max(s.alpha, p > 0 ? 1 : 0); s.draw = e; }
        else if (a.fx === 'pop') { s.alpha = Math.max(s.alpha, e); s.scale = lerp(0.55, 1, ease('back', p)); s.draw = 1; }
        else if (a.fx === 'wipe') { s.alpha = Math.max(s.alpha, p > 0 ? 1 : 0); s.wipe = e; s.draw = 1; }
        else { s.alpha = Math.max(s.alpha, e); s.draw = 1; }
      } else {
        s.alpha = s.alpha * (1 - ease('inout', p));
      }
      s.sig += q(p, 3) + ',';
    }
    for (const a of c.focus) {
      if (t < a.t0) break;
      const u = t - a.t0, rise = 0.25, fall = 0.4;
      if (u > a.dur + fall) { s.sig += 'F,'; continue; }
      const e = u < rise ? ease('out', u / rise) : (u < a.dur ? 1 : 1 - ease('inout', (u - a.dur) / fall));
      if (e > s.emph) { s.emph = e; s.ecol = a.color || 'focus'; }
      s.sig += 'f' + q(e, 3) + ',';
    }
    for (const a of c.paint) {
      if (t < a.t0) break;
      const p = ease('inout', prog(a, t));
      // 上一次改色可能还是 {from,to,p} 对象（第一次改色时不知道原色）：先落成字符串再混，第二次 paint 才不会出错
      const base = s.color ? (typeof s.color === 'string' ? s.color : col(s.color.to)) : null;
      s.color = a.color ? (base ? mix(base, a.color, p) : { from: null, to: a.color, p }) : s.color;
      if (a.width) s.width = { to: a.width, p, from: s.width && s.width.to };
      s.sig += 'p' + q(p, 3) + ',';
    }
    for (const a of c.dim) {
      if (t < a.t0) break;
      const p = ease('inout', prog(a, t));
      s.dim = lerp(s.dim, a.to === undefined ? 0.28 : a.to, p);
      s.sig += 'd' + q(p, 3) + ',';
    }
    return s;
  }
  function resolveColor(s, base) {
    if (!s.color) return col(base);
    if (typeof s.color === 'string') return s.color;
    return mix(col(base), s.color.to, s.color.p);
  }
  function resolveWidth(s, base) {
    if (!s.width) return base;
    return lerp(s.width.from || base, s.width.to, s.width.p);
  }

  // ---------------------------------------------------------------- 绘制世界
  const INIT_VIS = new Set((DATA.world && DATA.world.init) || []);
  function drawWorld(t, worldAlpha) {
    let sig = '';
    const labelsToRepel = [];
    for (const R of ORDER) {
      const o = R.def, st = R.st, G = GEO[o.id];
      const s = stateOf(o.id, t, INIT_VIS.has(o.id));
      sig += s.sig + '|';
      const alpha = s.alpha * s.dim * (st.opacity === undefined ? 1 : st.opacity);
      if (alpha <= 0.002) {
        R.g.style.display = 'none';
        if (R.lab) R.lab.style.opacity = 0;
        if (R.labs) R.labs.forEach(d => { d.style.opacity = 0; });
        continue;
      }
      R.g.style.display = '';
      R.g.setAttribute('opacity', q(alpha, 3));
      const stroke = resolveColor(s, st.stroke || 'ink');
      const width = resolveWidth(s, st.width || 3) * (1 + 0.6 * s.emph);
      const ecol = col(s.ecol);
      const strokeNow = s.emph > 0 ? mix(stroke, ecol, s.emph * 0.85) : stroke;

      if (o.type === 'point') {
        const p = S(G.at);
        R.dot.setAttribute('cx', q(p[0], 2)); R.dot.setAttribute('cy', q(p[1], 2));
        const dc = s.emph > 0 ? mix(col(st.fill || 'ink'), ecol, s.emph) : resolveColor(s, st.fill || 'ink');
        if (st.hollow) {        // 空心点：取不到的端点（纸色填充 + 彩色圈）
          R.dot.setAttribute('fill', PAL.paper); R.dot.setAttribute('stroke', dc); R.dot.setAttribute('stroke-width', q(st.sw || 3, 2));
        } else R.dot.setAttribute('fill', dc);
        R.dot.setAttribute('r', q((st.r || 5) * s.scale * (1 + 0.5 * s.emph), 2));
        R.glow.setAttribute('cx', q(p[0], 2)); R.glow.setAttribute('cy', q(p[1], 2));
        R.glow.setAttribute('fill', ecol); R.glow.setAttribute('opacity', q(s.emph * 0.9, 3));
        continue;
      }
      if (o.type === 'label' || o.type === 'text') {
        const p = S(G.at);
        const off = dirOffset(o.dir, o.dist);
        const x = p[0] + off[0] + (o.dx || 0), y = p[1] + off[1] + (o.dy || 0);
        R.lab.style.opacity = q(alpha, 3);
        const base = st.color || (o.type === 'label' ? 'ink' : 'gold');
        R.lab.style.color = s.emph > 0 ? mix(resolveColor(s, base), ecol, s.emph) : resolveColor(s, base);
        R.lab.style.textShadow = s.emph > 0.01 ? '0 0 ' + q(14 * s.emph, 1) + 'px ' + ecol : '';
        R._pos = [x, y];
        R._scale = s.scale * (1 + 0.15 * s.emph);
        if (R.nv) {
          let val = G.num;
          if (Math.abs(val) < 0.5 * Math.pow(10, -R.digits)) val = 0;     // 不显示 -0.00
          const txt = isFinite(val) ? val.toFixed(R.digits) : '—';
          if (R._nvs !== txt) { R.nv.textContent = txt; R._nvs = txt; }
          sig += 'n' + txt;
        }
        if (o.type === 'label' && o.repel !== false) labelsToRepel.push(R);
        else if (o.align === 'left' || o.align === 'right') {     // 左/右对齐（公式推导区、读数牌）
          R.lab.style.transformOrigin = o.align === 'left' ? '0 50%' : '100% 50%';
          R.lab.style.transform = 'translate(' + q(x, 1) + 'px,' + q(y, 1) + 'px) translate(' + (o.align === 'left' ? '0' : '-100%') + ',-50%) scale(' + q(R._scale, 3) + ')';
        } else R.lab.style.transform = 'translate(' + q(x, 1) + 'px,' + q(y, 1) + 'px) translate(-50%,-50%) scale(' + q(R._scale, 3) + ')';
        continue;
      }
      // 线类 / 面类
      let d = '', dFill = '', head = '', labPos = null;
      const poly = (G.poly || []).map(S);
      if (o.type === 'polygon' || o.type === 'region' || o.type === 'clip') {
        d = pathOf(poly, true); dFill = d;
      } else if (o.type === 'segment' || o.type === 'polyline') {
        d = pathOf(poly, false);
      } else if (o.type === 'arrow') {
        const [a, b] = poly; const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), L = 18, Wd = 8;
        const bb = [b[0] - Math.cos(ang) * L * 0.7, b[1] - Math.sin(ang) * L * 0.7];
        d = pathOf([a, bb], false);
        head = arrowHead(b, ang, L, Wd);
      } else if (o.type === 'angle') {
        const [A, O, B] = poly; const r = o.r || 34;
        let a1 = Math.atan2(A[1] - O[1], A[0] - O[0]), a2 = Math.atan2(B[1] - O[1], B[0] - O[0]);
        let da = a2 - a1; while (da > Math.PI) da -= 2 * Math.PI; while (da < -Math.PI) da += 2 * Math.PI;
        const n = 24, arc = [];
        for (let i = 0; i <= n; i++) { const an = a1 + da * i / n; arc.push([O[0] + r * Math.cos(an), O[1] + r * Math.sin(an)]); }
        d = pathOf(arc, false);
        const mid = a1 + da / 2, lr = r + (o.lr || 24);
        labPos = [O[0] + lr * Math.cos(mid), O[1] + lr * Math.sin(mid)];
      } else if (o.type === 'right') {
        const [A, O, B] = poly; const sz = o.size || 16;
        const u = unit(A, O), w = unit(B, O);
        d = pathOf([[O[0] + u[0] * sz, O[1] + u[1] * sz], [O[0] + (u[0] + w[0]) * sz, O[1] + (u[1] + w[1]) * sz], [O[0] + w[0] * sz, O[1] + w[1] * sz]], false);
      } else if (o.type === 'dim') {
        const [A, B] = poly; const off = o.off === undefined ? 34 : o.off;
        const u = unit(B, A), nrm = [u[1], -u[0]];   // 屏幕坐标下的法向：off>0 在 A→B 的左手侧（A→B 从左到右时在上方），off<0 在下方
        const a = [A[0] + nrm[0] * off, A[1] + nrm[1] * off], b = [B[0] + nrm[0] * off, B[1] + nrm[1] * off];
        const tk = 9;
        const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
        if (o.arrows !== false) {
          const L = 14, Wd = 6;
          const a2 = [a[0] + Math.cos(ang) * L * 0.6, a[1] + Math.sin(ang) * L * 0.6], b2 = [b[0] - Math.cos(ang) * L * 0.6, b[1] - Math.sin(ang) * L * 0.6];
          d = pathOf([a2, b2], false) + pathOf([[a[0] - nrm[0] * tk, a[1] - nrm[1] * tk], [a[0] + nrm[0] * tk, a[1] + nrm[1] * tk]], false) + pathOf([[b[0] - nrm[0] * tk, b[1] - nrm[1] * tk], [b[0] + nrm[0] * tk, b[1] + nrm[1] * tk]], false);
          head = arrowHead(b, ang, L, Wd) + arrowHead(a, ang + Math.PI, L, Wd);
        } else {
          d = pathOf([a, b], false);
        }
        const lo = (o.loff === undefined ? 26 : o.loff) * (off < 0 ? -1 : 1);
        labPos = [(a[0] + b[0]) / 2 + nrm[0] * lo, (a[1] + b[1]) / 2 + nrm[1] * lo];
      } else if (o.type === 'curve') {
        d = curvePath(R, G, s.draw);
      } else if (o.type === 'pcurve') {
        const n = o.n || 240, ta = G.t0, tb = lerp(G.t0, G.t1, clamp(s.draw)), pts = [];
        if (tb !== ta) for (let i = 0; i <= n; i++) {
          const tt = ta + (tb - ta) * i / n, x = R.fx(tt, G.v), y = R.fy(tt, G.v);
          if (isFinite(x) && isFinite(y)) pts.push(S([x, y]));
        }
        d = pts.length > 1 ? pathOf(pts, !!o.close && s.draw > 0.999) : '';
        if (o.close && st.fill) dFill = d;          // 闭合参数曲线可填色（珠子、气泡等椭圆）
        if (o.arrow && pts.length > 1) {       // 末端箭头（转圈方向）
          const a = pts[pts.length - 2], b = pts[pts.length - 1];
          head = arrowHead(b, Math.atan2(b[1] - a[1], b[0] - a[0]), 16, 7);
        }
      } else if (o.type === 'axes') {
        // 坐标轴：自己按 draw 进度从起点往箭头方向画（不用虚线技巧，多段路径时更稳）
        const [xa, xb] = G.x, [ya, yb] = G.y, [ox, oy] = G.o, k = s.draw, L = 16, Wd = 7;
        const A1 = S([xa, oy]), A2 = S([lerp(xa, xb, k), oy]), B1 = S([ox, ya]), B2 = S([ox, lerp(ya, yb, k)]);
        if (o.nox !== true) d += pathOf([A1, [A2[0] - L * 0.7, A2[1]]], false);
        if (o.noy !== true) d += pathOf([B1, [B2[0], B2[1] + L * 0.7]], false);
        if (o.arrows !== false) head = (o.nox !== true ? arrowHead(A2, 0, L, Wd) : '') + (o.noy !== true ? arrowHead(B2, -Math.PI / 2, L, Wd) : '');
        const O = S([ox, oy]);
        // 轴名 x 默认在箭头下方；xlabelDir:"N" 放上方（曲线从下方穿过轴的右端时用）
        R._labPos = [[A2[0] - 4, A2[1] + (o.xlabelDir === 'N' ? -30 : 30)], [B2[0] + 26, B2[1] + 10], [O[0] - 22, O[1] + 24]];
        R._labOn = [o.nox !== true, o.noy !== true, o.nox !== true && o.noy !== true];
      } else if (o.type === 'ticks') {
        const len = o.len || 9, dist = o.dist === undefined ? 30 : o.dist, dir = o.dir || (o.axis === 'y' ? 'W' : 'S');
        R._labPos = [];
        G.at.forEach((val, i) => {
          const p = o.axis === 'y' ? S([G.on, val]) : S([val, G.on]);
          d += o.axis === 'y' ? pathOf([p, [p[0] + len, p[1]]], false) : pathOf([p, [p[0], p[1] - len]], false);
          const off = dirOffset(dir, dist);
          R._labPos.push([p[0] + off[0] + ((o.ldx || [])[i] || 0), p[1] + off[1] + ((o.ldy || [])[i] || 0)]);
        });
        R._labOn = G.at.map(() => true);
      }
      R.path.setAttribute('d', d);
      R.glow.setAttribute('d', d);
      if (st.stroke && (width > 0)) {
        R.path.setAttribute('stroke', strokeNow);
        R.path.setAttribute('stroke-width', q(width, 2));
        R.path.style.display = '';
      } else if (s.emph > 0.01 && dFill) {
        R.path.setAttribute('stroke', ecol); R.path.setAttribute('stroke-width', q(3 * s.emph, 2)); R.path.style.display = '';
      } else R.path.style.display = 'none';
      const selfDraw = o.type === 'curve' || o.type === 'pcurve' || o.type === 'axes' || o.type === 'ticks';   // 这几类自己按 draw 进度截断路径
      if (st.dash) R.path.setAttribute('stroke-dasharray', Array.isArray(st.dash) ? st.dash.join(' ') : '10 9');
      else if (s.draw < 0.999 && !selfDraw) { R.path.setAttribute('pathLength', '1'); R.path.setAttribute('stroke-dasharray', q(s.draw, 4) + ' 2'); }
      else { R.path.removeAttribute('pathLength'); R.path.removeAttribute('stroke-dasharray'); }
      if (st.dash && s.draw < 0.999 && !selfDraw) R.path.setAttribute('opacity', q(s.draw, 3)); else R.path.removeAttribute('opacity');
      if (G.flow !== undefined) {
        R.path.style.strokeDashoffset = q(-G.flow, 2);
        sig += 'w' + q(G.flow, 1);
      }
      R.glow.setAttribute('stroke', s.emph > 0.01 ? ecol : stroke);
      R.glow.setAttribute('stroke-width', q(width + 10, 2));
      R.glow.setAttribute('opacity', q(Math.max(s.emph * 0.75, st.glow ? 0.35 : 0), 3));
      if (dFill && (st.fill || s.emph > 0.01)) {
        R.fillEl.setAttribute('d', dFill);
        const fc = st.fill ? resolveColorFill(s, st.fill) : ecol;
        R.fillEl.setAttribute('fill', s.emph > 0 && st.fill ? mix(fc, ecol, s.emph * 0.5) : fc);
        const fo = (st.fill ? (st.fillOpacity === undefined ? 0.15 : st.fillOpacity) : 0) + 0.18 * s.emph;
        R.fillEl.setAttribute('fill-opacity', q(fo * Math.min(1, s.draw * 1.5), 3));
        R.fillEl.style.display = '';
      } else R.fillEl.style.display = 'none';
      if (R.head) { R.head.setAttribute('d', head); R.head.setAttribute('fill', strokeNow); R.head.setAttribute('opacity', q(s.draw > 0.97 || o.type === 'axes' || o.type === 'pcurve' ? 1 : 0, 2)); }
      if (R.labs) {
        const la = alpha * (o.type === 'ticks' ? clamp((s.draw - 0.3) / 0.7) : clamp((s.draw - 0.8) / 0.2));
        const lc = col(st.lcolor || 'ink');
        R.labs.forEach((el, i) => {
          const p = R._labPos && R._labPos[i];
          if (!p || !R._labOn[i]) { el.style.opacity = 0; return; }
          el.style.opacity = q(la, 3);
          el.style.color = s.emph > 0 ? mix(lc, ecol, s.emph) : lc;
          el.style.transform = 'translate(' + q(p[0], 1) + 'px,' + q(p[1], 1) + 'px) translate(-50%,-50%) scale(' + q(1 + 0.15 * s.emph, 3) + ')';
        });
      }
      if (R.lab) {
        if (labPos) {
          R.lab.style.opacity = q(alpha * clamp((s.draw - 0.6) / 0.4), 3);
          R.lab.style.color = s.emph > 0 ? mix(col(st.lcolor || st.stroke || 'ink'), ecol, s.emph) : col(st.lcolor || resolveColor(s, st.stroke || 'ink'));
          R.lab.style.transform = 'translate(' + q(labPos[0] + (o.ldx || 0), 1) + 'px,' + q(labPos[1] + (o.ldy || 0), 1) + 'px) translate(-50%,-50%) scale(' + q(1 + 0.15 * s.emph, 3) + ')';
        } else R.lab.style.opacity = 0;
      }
    }
    repel(labelsToRepel);
    return sig;
  }
  // 函数图像：在 [x0, x0+(x1-x0)*draw] 上取样，超出视野上下沿（或 ymin/ymax）的部分截掉，出入边界处插值到边沿，
  // 函数无定义（NaN）处断开——渐近线附近的曲线正好画到画框边上
  function curvePath(R, G, draw) {
    const o = R.def, n = o.n || 480;
    // 只在镜头看得见的那段 x 上取样（曲线可以写得很长，推拉镜头时自动露出来；描出动画也只扫看得见的部分）
    const xa = Math.max(G.x0, VIEW.x[0]), xe = Math.min(G.x1, VIEW.x[1]);
    const xb = lerp(xa, xe, clamp(draw));
    if (!(xb > xa)) return '';
    const ylo = Math.max(VIEW.y[0], o.ymin === undefined ? -Infinity : o.ymin);
    const yhi = Math.min(VIEW.y[1], o.ymax === undefined ? Infinity : o.ymax);
    const segs = [];
    let cur = [], px = null, py = NaN;
    for (let i = 0; i <= n; i++) {
      const x = xa + (xb - xa) * i / n, y = R.fx(x, G.v);
      const ok = isFinite(y) && y >= ylo && y <= yhi;
      if (ok) {
        if (!cur.length && px !== null && isFinite(py)) {          // 从画框外进来：补上边沿交点
          const yb = py > yhi ? yhi : (py < ylo ? ylo : null);
          if (yb !== null) cur.push([px + (yb - py) / (y - py) * (x - px), yb]);
        }
        cur.push([x, y]);
      } else {
        if (cur.length && isFinite(y)) {                           // 出画框：补上边沿交点
          const yb = y > yhi ? yhi : ylo;
          cur.push([px + (yb - py) / (y - py) * (x - px), yb]);
        }
        if (cur.length) { segs.push(cur); cur = []; }
      }
      px = x; py = y;
    }
    if (cur.length) segs.push(cur);
    return segs.filter(sg => sg.length > 1).map(sg => pathOf(sg.map(S), false)).join('');
  }
  function resolveColorFill(s, base) { return s.color && s.color.to && typeof s.color !== 'string' ? mix(col(base), s.color.to, s.color.p) : (typeof s.color === 'string' ? s.color : col(base)); }
  function unit(A, O) { const dx = A[0] - O[0], dy = A[1] - O[1], L = Math.hypot(dx, dy) || 1; return [dx / L, dy / L]; }
  function arrowHead(tip, ang, L, Wd) {
    const b = [tip[0] - Math.cos(ang) * L, tip[1] - Math.sin(ang) * L];
    const n = [-Math.sin(ang) * Wd, Math.cos(ang) * Wd];
    return pathOf([tip, [b[0] + n[0], b[1] + n[1]], [b[0] - n[0], b[1] - n[1]]], true);
  }
  const DIRS = { N: [0, -1], S: [0, 1], E: [1, 0], W: [-1, 0], NE: [0.72, -0.72], NW: [-0.72, -0.72], SE: [0.72, 0.72], SW: [-0.72, 0.72], C: [0, 0] };
  function dirOffset(dir, dist) { const d = DIRS[dir || 'N'] || DIRS.N, r = dist === undefined ? 28 : dist; return [d[0] * r, d[1] * r]; }
  // 点标签互斥：重叠的标签沿水平方向推开（推力随距离连续变化，运动中不跳）
  function repel(list) {
    const pos = list.map(R => R._pos.slice());
    const half = 16;
    for (let it = 0; it < 3; it++) {
      for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
        if (+list[i].lab.style.opacity < 0.05 || +list[j].lab.style.opacity < 0.05) continue;
        const dx = pos[j][0] - pos[i][0], dy = pos[j][1] - pos[i][1];
        const wi = half * (list[i].def.text || 'A').length, wj = half * (list[j].def.text || 'A').length;
        const need = wi + wj + 4;
        if (Math.abs(dy) < 34 && Math.abs(dx) < need) {
          const push = (need - Math.abs(dx)) / 2, sgn = dx >= 0 ? 1 : -1;
          pos[i][0] -= push * sgn; pos[j][0] += push * sgn;
        }
      }
    }
    list.forEach((R, i) => { R.lab.style.transform = 'translate(' + q(pos[i][0], 1) + 'px,' + q(pos[i][1], 1) + 'px) translate(-50%,-50%) scale(' + q(R._scale, 3) + ')'; });
  }

  // ---------------------------------------------------------------- 界面元素
  const UI = {};   // id -> element（带 data-id 的界面元素）
  function initUI() {
    document.querySelectorAll('#ui [data-id]').forEach(el => { UI[el.dataset.id] = el; });
    renderMathIn(document.getElementById('ui'));
  }
  function drawUI(t) {
    let sig = '';
    for (const id in UI) {
      const el = UI[id];
      const s = stateOf(id, t, el.dataset.init === '1');
      sig += s.sig + '|';
      const kind = el.dataset.kind || '';
      if (kind === 'mark') {           // 题干标记：荧光笔扫过；最近的一处最亮
        const on = s.alpha > 0;
        el.style.backgroundSize = q((on ? s.wipe : 0) * 100, 2) + '% 100%';
        el.classList.toggle('on', on);
        const active = on && isLatestMark(id, t);
        el.classList.toggle('active', active);
        sig += active ? 'A' : 'a';
        continue;
      }
      el.style.opacity = q(s.alpha * s.dim, 3);
      // 用独立的 scale 属性，不覆盖元素自身 CSS 里的 transform（居中用的 translate 等）
      el.style.scale = (s.scale !== 1 || s.emph > 0) ? q(s.scale * (1 + 0.04 * s.emph), 3) : '';
      el.style.clipPath = s.wipe < 0.999 ? 'inset(-12px ' + q((1 - s.wipe) * 100, 2) + '% -12px -12px)' : '';
      if (s.emph > 0.01) { el.style.setProperty('--em', q(s.emph, 3)); el.classList.add('em'); el.style.setProperty('--ecol', col(s.ecol)); }
      else el.classList.remove('em');
    }
    // 时间条/面积条底下的白卡片：跟着部件显隐；只剩面积条时缩成小卡片
    const deck = document.getElementById('deck');
    if (deck) {
      const ta = UI.timebar ? +UI.timebar.style.opacity || 0 : 0, ma = UI.meter ? +UI.meter.style.opacity || 0 : 0;
      deck.style.opacity = q(Math.max(ta, ma), 3);
      const small = ta < 0.01 && ma > 0.01;
      deck.style.left = small ? '964px' : '';
      deck.style.width = small ? '232px' : '';
      sig += 'k' + q(ta, 2) + q(ma, 2) + (small ? 's' : '');
    }
    return sig;
  }
  const MARKS = [];
  function isLatestMark(id, t) {
    let best = null;
    for (const a of MARKS) { if (a.t0 <= t) best = a; else break; }
    return best && best.ids.includes(id) && (!best.until || t < best.until);
  }

  // ---------------------------------------------------------------- 场景与版式
  const SCENES = DATA.scenes;
  const FIN = 0.4, FOUT = 0.35, MOVE = 0.8;   // MOVE：几何图在两种版式间搬家的时长   // 场景先淡出再淡入（不交叉，避免两个标题叠在一起）
  function sceneAlpha(sc, t) {
    return Math.min(clamp((t - sc.t0 - (sc.fin_delay || 0)) / FIN), clamp((sc.t1 - t) / FOUT));
  }
  function activeScene(t) {
    let i = 0;
    for (let k = 0; k < SCENES.length; k++) if (t >= SCENES[k].t0) i = k;
    return i;
  }
  // 几何画框与视野：按场景版式取值，场景切换时 0.9 秒补间
  function boxView(t) {
    const i = activeScene(t), sc = SCENES[i];
    const cur = { box: sc.box, view: sc.view };
    let res = cur;
    if (i > 0 && sc.box && SCENES[i - 1].box) {
      const pv = SCENES[i - 1];
      const endV = viewAt(pv.t1 - 1e-3, pv);
      const k = ease('inout', clamp((t - sc.t0) / MOVE));
      if (k < 1) res = { box: lerpBox(pv.box, sc.box, k), view: lerpView(endV, sc.view, k), k };
    }
    res = { box: res.box, view: viewAt(t, sc, res.view), k: res.k };
    return res;
  }
  function viewAt(t, sc, base) {
    let v = base || sc.view;
    for (const a of CAMS) {
      if (a.t0 > t) break;
      if (a.t0 < sc.t0 || a.t0 >= sc.t1) continue;
      const p = ease('inout', prog(a, t));
      v = lerpView(a.fromView || v, a.view, p);
    }
    return v;
  }
  function bakeCams() {
    for (const a of CAMS) {
      const sc = SCENES.find(s => a.t0 >= s.t0 && a.t0 < s.t1) || SCENES[0];
      a.fromView = viewAt(a.t0 - 1e-6, sc);
    }
  }
  const lerpBox = (a, b, k) => ({ x: lerp(a.x, b.x, k), y: lerp(a.y, b.y, k), w: lerp(a.w, b.w, k), h: lerp(a.h, b.h, k) });
  const lerpView = (a, b, k) => ({ x: [lerp(a.x[0], b.x[0], k), lerp(a.x[1], b.x[1], k)], y: [lerp(a.y[0], b.y[0], k), lerp(a.y[1], b.y[1], k)],
                                   free: k < 0.5 ? !!a.free : !!b.free });

  // ---------------------------------------------------------------- 时间条与面积条
  const TB = DATA.widgets && DATA.widgets.timebar;
  const MT = DATA.widgets && DATA.widgets.meter;
  let tbEls = null, mtEls = null, mtExpr = null;
  function initWidgets() {
    if (TB) {
      tbEls = { knob: $('#tb-knob'), fill: $('#tb-fill'), val: $('#tb-val'), track: $('#tb-track') };
    }
    if (MT) { mtEls = { fill: $('#mt-fill'), val: $('#mt-val') }; mtExpr = cexpr(MT.expr); }
  }
  function drawWidgets(v) {
    let sig = '';
    if (TB && tbEls) {
      const x = clamp((v[TB.var] - TB.from) / (TB.to - TB.from));
      tbEls.knob.style.left = q(x * 100, 3) + '%';
      tbEls.fill.style.width = q(x * 100, 3) + '%';
      tbEls.val.textContent = (Math.round(v[TB.var] * 10) / 10).toFixed(1) + ' ' + (TB.unit || '');
      sig += 'tb' + q(x, 4);
    }
    if (MT && mtEls) {
      const r = clamp(mtExpr(v), 0, 1.2);
      mtEls.fill.style.width = q(Math.min(r, 1) * 100, 3) + '%';
      mtEls.fill.classList.toggle('full', r > 0.999);
      sig += 'mt' + q(r, 4);
    }
    return sig;
  }

  // ---------------------------------------------------------------- 字幕
  const SUBS = DATA.subs || [];
  const subEl = () => $('#sub');
  let subIdx = -2;
  function drawSub(t) {
    let k = -1;
    for (let i = 0; i < SUBS.length; i++) if (t >= SUBS[i].t0 && t < SUBS[i].t1) k = i;
    const el = subEl();
    if (!el) return '';
    if (k !== subIdx) { el.querySelector('.txt').innerHTML = k >= 0 ? SUBS[k].html : ''; subIdx = k; }
    let a = 0;
    if (k >= 0) { const s = SUBS[k]; a = Math.min(clamp((t - s.t0) / 0.18), clamp((s.t1 - t) / 0.18)); }
    el.style.opacity = q(a, 3);
    return 's' + k + ':' + q(a, 2);
  }

  // ---------------------------------------------------------------- 主入口
  window.__init = async function () {
    initWorld();
    initActions();
    MARKS.push(...DATA.actions.filter(a => a.op === 'show' && a.mark).sort((x, y) => x.t0 - y.t0));
    bakeTweenFrom();
    bakeCams();
    initUI();
    initWidgets();
    const fams = ['400 40px "Noto Sans SC"', '700 40px "Noto Sans SC"', '400 40px "Noto Serif SC"', '500 40px "LXGW WenKai"', '40px KaTeX_Main', 'italic 40px KaTeX_Math'];
    await Promise.all(fams.map(f => document.fonts.load(f, '中文字ABC123')));
    await document.fonts.ready;
    return { duration: DATA.duration, frames: Math.ceil(DATA.duration * DATA.fps) };
  };

  window.seek = function (t) {
    let sig = '';
    // 场景容器
    for (const sc of SCENES) {
      const el = document.getElementById('scene-' + sc.id);
      const a = sceneAlpha(sc, t);
      if (el) { el.style.opacity = q(a, 3); el.style.visibility = a > 0.001 ? 'visible' : 'hidden'; }
      sig += q(a, 3) + ',';
    }
    const i = activeScene(t), sc = SCENES[i];
    // 几何世界 / 讲台部件（时间条、面积条）：可见度随场景（相邻场景都有时不淡出，直接搬家）
    const wa = layerAlpha(t, 'world');
    const world = $('#worldwrap');
    world.style.opacity = q(wa, 3);
    world.style.visibility = wa > 0.001 ? 'visible' : 'hidden';
    const ba = layerAlpha(t, 'board');
    const board = $('#boardwrap');
    board.style.opacity = q(ba, 3);
    board.style.visibility = ba > 0.001 ? 'visible' : 'hidden';
    sig += 'w' + q(wa, 3) + 'k' + q(ba, 3);
    if (sc.layout === 'title') drawTitle(t, sc);
    sig += drawChrome(t, i);
    const bv = boxView(t);
    if (bv.box) setMapping(bv.box, bv.view);
    // world.clip（px 边距）：图只画在画框里。物理装置这类高的东西推近景时会伸出画框，压到标题、板书上
    if (DATA.world && DATA.world.clip !== undefined && bv.box) {
      const m = DATA.world.clip, b = bv.box;
      world.style.clipPath = 'inset(' + [b.y - m, W - b.x - b.w - m, H - b.y - b.h - m, b.x - m].map(x => q(x, 1) + 'px').join(' ') + ')';
    }
    sig += 'b' + [bv.box && bv.box.x, bv.box && bv.box.y, bv.box && bv.box.w, bv.view && bv.view.x[0], bv.view && bv.view.x[1], bv.view && bv.view.y[0]].map(x => q(x || 0, 2)).join(',');
    const v = varsAt(t);
    sig += 'v' + VARS.map(k => q(v[k], 4)).join(',');
    computeGeometry(v);
    if (wa > 0.001) sig += drawWorld(t, wa);
    sig += drawWidgets(v);
    sig += drawUI(t);
    sig += drawSub(t);
    if (sc.layout === 'title') sig += 'T' + q(t, 2);   // 标题卡有持续的光点动画
    return sig;
  };
  // 品牌外框：章节进度条 + 全片开头/结尾淡入淡出
  let progIdx = -2;
  function drawChrome(t, i) {
    const k = SCENES[i].chap === undefined ? -1 : SCENES[i].chap;
    if (k !== progIdx) {
      document.querySelectorAll('#progress i').forEach((el, j) => { el.className = j < k ? 'done' : (j === k ? 'now' : ''); });
      progIdx = k;
    }
    const pr = document.getElementById('progress');
    if (pr) pr.style.opacity = k < 0 ? '0' : '1';
    // 片尾卡中间已有大标志：角标淡出，不重复
    let hb = 0;
    for (const sc of SCENES) if (sc.layout === 'outro') hb = Math.max(hb, sceneAlpha(sc, t));
    const br = document.getElementById('brand');
    if (br) br.style.opacity = q(1 - hb, 3);
    const D = DATA.duration, fin = DATA.fade_in || 0.5, fout = DATA.fade_out || 1.2;
    const f = Math.max(1 - clamp(t / fin), clamp((t - (D - fout)) / fout));
    const fe = document.getElementById('fade');
    if (fe) fe.style.opacity = q(f, 3);
    return 'c' + k + 'f' + q(f, 3) + 'h' + q(hb, 3);
  }
  function drawTitle(t, sc) {
    const dot = document.querySelector('#scene-' + sc.id + ' .tdot');
    if (dot) dot.style.left = q(clamp((t - sc.t0 - 1.0) / Math.max(0.5, sc.t1 - sc.t0 - 1.3)) * 100, 3) + '%';
  }
  function layerAlpha(t, key) {
    let a = 0;
    for (const sc of SCENES) {
      if (!sc[key]) continue;
      // 相邻两场景都有这一层：中间不淡出
      const i = SCENES.indexOf(sc);
      const prevW = i > 0 && SCENES[i - 1][key], nextW = i < SCENES.length - 1 && SCENES[i + 1][key];
      const fa = prevW ? (t >= sc.t0 ? 1 : 0) : clamp((t - sc.t0) / FIN);
      const fb = nextW ? (t < sc.t1 ? 1 : 0) : clamp((sc.t1 - t) / FOUT);
      a = Math.max(a, Math.min(fa, fb));
    }
    return a;
  }
})();
