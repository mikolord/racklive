/* ───────── «Схема» дома: своя картинка-чертёж + линии и зоны поверх (провода, помещения) ─────────
   Мировые координаты — пиксели самой картинки (её «природный» размер); в данных хранится доля 0..1 (rackd/scheme.py),
   поэтому при замене фото на другое по размеру линии остаются на тех же относительных местах. */
const SCHEME_COLORS = ['blue', 'green', 'red', 'orange', 'purple', 'teal'];
const SCHEME_COLOR_VAR = { blue: 'var(--accent)', green: 'var(--green)', red: 'var(--red)', orange: 'var(--orange)', purple: 'var(--purple)', teal: 'var(--teal)' };

function schemeClamp01(v) { return Math.max(-4, Math.min(5, v)); }       // поле не ограничено картинкой: можно и за её краями

const SCHEME_WMUL = [1, 1.8, 2.8], SCHEME_FMUL = [1, 1.6, 2.4];
function schemeFont(s, W) { return Math.max(12, W / 60) * SCHEME_FMUL[(s.fs || 1) - 1]; }
function schemeTextBox(s, W, H) {                             // рамка надписи в мировых пикселях (точка — левый край базовой линии)
  const f = schemeFont(s, W), w = (s.label || '').length * f * .6 + 10;
  return { x: s.x1 * W - 4, y: s.y1 * H - f, w, h: f * 1.35, f };
}
function schemeArrowHead(x0, y0, x1, y1, size) {              // треугольник стрелки на конце отрезка (x0,y0)→(x1,y1)
  const a = Math.atan2(y1 - y0, x1 - x0), c = Math.cos(a), sn = Math.sin(a);
  const bx = x1 - c * size, by = y1 - sn * size, nx = -sn * size * .55, ny = c * size * .55;
  return `${x1},${y1} ${bx + nx},${by + ny} ${bx - nx},${by - ny}`;
}
/* перенос и растягивание: shape → новая фигура. mode: 'move' или 1/2 (потянули за конец) */
function schemeDrag(shape, mode, start, p, W, H, others) {
  if (mode === 'move') {
    const xs = [], ys = [];
    if (shape.pts) shape.pts.forEach(q => { xs.push(q[0]); ys.push(q[1]); }); else { xs.push(shape.x1, shape.x2); ys.push(shape.y1, shape.y2); }
    let dx = (p.x - start.x) / W, dy = (p.y - start.y) / H;
    dx = Math.max(-4 - Math.min(...xs), Math.min(5 - Math.max(...xs), dx)); dy = Math.max(-4 - Math.min(...ys), Math.min(5 - Math.max(...ys), dy));
    const out = { ...shape, x1: shape.x1 + dx, y1: shape.y1 + dy, x2: shape.x2 + dx, y2: shape.y2 + dy };
    if (shape.pts) out.pts = shape.pts.map(q => [q[0] + dx, q[1] + dy]);
    return out;
  }
  if (mode === 'rot') {                                       // разворот за ручку над фигурой: шаг 15° (липнет, когда рядом)
    const c = schemeBoxCenter(shape, W, H);
    let a = Math.atan2(p.y - c.y, p.x - c.x) * 180 / Math.PI + 90;
    const r15 = Math.round(a / 15) * 15; if (Math.abs(a - r15) < 5) a = r15;
    return { ...shape, rot: Math.round((((a + 180) % 360 + 360) % 360 - 180) * 10) / 10 };
  }
  if (shape.kind === 'rect' || shape.kind === 'node') {       // растягивание за угол с учётом разворота: противоположный угол стоит на месте
    const th = shape.rot || 0, c = schemeBoxCenter(shape, W, H);
    const opp = mode === 1 ? { x: shape.x2 * W, y: shape.y2 * H } : { x: shape.x1 * W, y: shape.y1 * H };
    const wo = schemeRot(opp, c, th), c2 = { x: (p.x + wo.x) / 2, y: (p.y + wo.y) / 2 };
    const d = schemeRot({ x: (p.x - wo.x) / 2, y: (p.y - wo.y) / 2 }, { x: 0, y: 0 }, -th);
    if (Math.abs(d.x) * 2 < 8 || Math.abs(d.y) * 2 < 4) return shape;
    const m = { x: c2.x + d.x, y: c2.y + d.y }, o = { x: c2.x - d.x, y: c2.y - d.y };
    const f = (v, M) => schemeClamp01(v / M);
    return mode === 1 ? { ...shape, x1: f(m.x, W), y1: f(m.y, H), x2: f(o.x, W), y2: f(o.y, H) } : { ...shape, x1: f(o.x, W), y1: f(o.y, H), x2: f(m.x, W), y2: f(m.y, H) };
  }
  const q = schemeSnapPoint(others.filter(x => x.id !== shape.id), p, W, H), fx = schemeClamp01(q.x / W), fy = schemeClamp01(q.y / H);
  if (shape.kind === 'wire' && shape.pts) {
    const first = shape.pts[0], last = shape.pts[shape.pts.length - 1];
    const a = mode === 1 ? { x: fx * W, y: fy * H } : { x: first[0] * W, y: first[1] * H };
    const b2 = mode === 2 ? { x: fx * W, y: fy * H } : { x: last[0] * W, y: last[1] * H };
    const pts = schemeRoute(a, b2).map(r => [schemeClamp01(r.x / W), schemeClamp01(r.y / H)]);
    return { ...shape, pts, x1: pts[0][0], y1: pts[0][1], x2: pts[pts.length - 1][0], y2: pts[pts.length - 1][1] };
  }
  return mode === 1 ? { ...shape, x1: fx, y1: fy } : { ...shape, x2: fx, y2: fy };
}

/* умные направляющие при переносе, как в Canva: фигура «прилипает» краями и центром к соседям, а равный промежуток между объектами в ряд показывается и сохраняется.
   Всё в мировых пикселях; коробка — {l, t, r, b}. Рисуется серым, в цвет интерфейса */
const SG_AX = { x: { lo: 'l', hi: 'r', a: 't', b: 'b' }, y: { lo: 't', hi: 'b', a: 'l', b: 'r' } };
const sgPt = (ax, u, v) => ax === 'x' ? { x: u, y: v } : { x: v, y: u };       // u — вдоль оси, v — поперёк
function schemeBoxOf(s, W, H) {
  if (s.kind === 'text') { const r = schemeTextBox(s, W, H); return { l: r.x, t: r.y, r: r.x + r.w, b: r.y + r.h }; }
  if (s.pts && s.pts.length) { const xs = s.pts.map(q => q[0] * W), ys = s.pts.map(q => q[1] * H); return { l: Math.min(...xs), r: Math.max(...xs), t: Math.min(...ys), b: Math.max(...ys) }; }
  const x1 = s.x1 * W, x2 = s.x2 * W, y1 = s.y1 * H, y2 = s.y2 * H;
  return { l: Math.min(x1, x2), r: Math.max(x1, x2), t: Math.min(y1, y2), b: Math.max(y1, y2) };
}
function schemeShift(s, dx, dy) {
  const o = { ...s, x1: s.x1 + dx, y1: s.y1 + dy, x2: s.x2 + dx, y2: s.y2 + dy };
  if (s.pts) o.pts = s.pts.map(q => [q[0] + dx, q[1] + dy]);
  return o;
}
function schemeGaps(others, ax) {                                // промежутки между соседями в ряду: {A, B, g}
  const K = SG_AX[ax], rows = others.slice(0, 80), out = [];
  const ovl = (p, q) => Math.min(p[K.b], q[K.b]) - Math.max(p[K.a], q[K.a]) >= 0;
  for (const A of rows) for (const B of rows) if (A !== B && A[K.hi] <= B[K.lo] && ovl(A, B) && B[K.lo] - A[K.hi] >= 2
    && !rows.some(C => C !== A && C !== B && A[K.hi] <= C[K.lo] && C[K.hi] <= B[K.lo] && ovl(A, C) && ovl(C, B))) out.push({ A, B, g: B[K.lo] - A[K.hi] });      // только соседи: между ними никого
  return out;
}
function schemeSnapAxis(M, others, ax, T) {                      // на сколько сдвинуть M вдоль оси, чтобы прилипнуть (0 — не липнет)
  const K = SG_AX[ax], mid = o => (o[K.lo] + o[K.hi]) / 2, ov = (p, q) => Math.min(p[K.b], q[K.b]) - Math.max(p[K.a], q[K.a]) >= 0, mw = M[K.hi] - M[K.lo];
  let best = null; const take = d => { if (Math.abs(d) <= T && (best === null || Math.abs(d) < Math.abs(best))) best = d; };
  for (const o of others) [o[K.lo], mid(o), o[K.hi]].forEach(v => [M[K.lo], mid(M), M[K.hi]].forEach(a => take(v - a)));
  const gaps = schemeGaps(others, ax);
  for (const o of others.slice(0, 80)) if (ov(M, o)) for (const q of gaps) { take(o[K.hi] + q.g - M[K.lo]); take(o[K.lo] - q.g - M[K.hi]); }
  for (const q of gaps) if (ov(M, q.A) && ov(M, q.B) && q.g - mw >= 2) take(q.A[K.hi] + (q.g - mw) / 2 - M[K.lo]);
  return best || 0;
}
function schemeGuideOf(M, others, ax) {                          // линии совпадения и отрезки равных промежутков для уже сдвинутого M
  const K = SG_AX[ax], mid = o => (o[K.lo] + o[K.hi]) / 2, ov = (p, q) => Math.min(p[K.b], q[K.b]) - Math.max(p[K.a], q[K.a]) >= 0, lines = [], marks = [];
  for (const o of others) [o[K.lo], mid(o), o[K.hi]].forEach(v => { if ([M[K.lo], mid(M), M[K.hi]].some(a => Math.abs(v - a) < .75)) lines.push([sgPt(ax, v, Math.min(M[K.a], o[K.a])), sgPt(ax, v, Math.max(M[K.b], o[K.b]))]); });
  const gaps = schemeGaps(others, ax), mg = [];
  others.slice(0, 80).forEach(o => { if (!ov(M, o)) return; if (o[K.hi] <= M[K.lo] && M[K.lo] - o[K.hi] >= 2) mg.push({ o, g: M[K.lo] - o[K.hi], side: -1 }); else if (M[K.hi] <= o[K.lo] && o[K.lo] - M[K.hi] >= 2) mg.push({ o, g: o[K.lo] - M[K.hi], side: 1 }); });
  const near = side => mg.filter(x => x.side === side).sort((p, q) => p.g - q.g)[0];
  const keep = [near(-1), near(1)].filter(Boolean); mg.length = 0; keep.forEach(x => mg.push(x));      // только ближайший сосед с каждой стороны
  const seg = (p, q, u0, u1) => { const v = (Math.max(p[K.a], q[K.a]) + Math.min(p[K.b], q[K.b])) / 2; marks.push([sgPt(ax, u0, v), sgPt(ax, u1, v)]); };
  mg.forEach(x => {
    const ref = gaps.find(q => Math.abs(q.g - x.g) < .75), opp = mg.find(y => y !== x && y.side !== x.side && Math.abs(y.g - x.g) < .75);
    if (!ref && !opp) return;
    if (x.side < 0) seg(x.o, M, x.o[K.hi], M[K.lo]); else seg(M, x.o, M[K.hi], x.o[K.lo]);
    if (ref) seg(ref.A, ref.B, ref.A[K.hi], ref.B[K.lo]);
  });
  return { lines, marks };
}
/* цвет индикатора: всегда один из двух — зелёный (работает) или красный (не отвечает); без данных точки нет */
const schemeLed = st => st === 'offline' ? 'var(--red)' : st ? 'var(--green)' : '';

function schemeRot(p, c, deg) {                              // повернуть точку p вокруг c на deg градусов
  const a = deg * Math.PI / 180, co = Math.cos(a), si = Math.sin(a), dx = p.x - c.x, dy = p.y - c.y;
  return { x: c.x + dx * co - dy * si, y: c.y + dx * si + dy * co };
}
function schemeBoxCenter(s, W, H) {
  if (s.kind === 'text') { const r = schemeTextBox(s, W, H); return { x: r.x + r.w / 2, y: r.y + r.h / 2 }; }
  return { x: (s.x1 + s.x2) / 2 * W, y: (s.y1 + s.y2) / 2 * H };
}
const SCHEME_BOXY = ['rect', 'node', 'text'];                 // эти фигуры можно разворачивать

/* набор объектов («как в Диаграммах»): фигуры, сетевое оборудование (значки Rack Live), помещения, UML */
const SCHEME_NET = [['router', 'Роутер'], ['switch', 'Коммутатор'], ['hub', 'Хаб'], ['ap', 'Точка доступа'], ['wifi', 'Усилитель'], ['server', 'Сервер'], ['firewall', 'Файрвол'], ['pc', 'ПК'],
  ['rack', 'Серв. шкаф'], ['patch', 'Патч-панель'], ['bolt', 'Эл. щит'], ['camera', 'Камера'], ['nvr', 'NVR'], ['modem', 'Модем'], ['nas', 'NAS'], ['ups', 'ИБП']];
const SCHEME_NETSET = Object.fromEntries(SCHEME_NET);
const SCHEME_LIB = [
  ['shapes', 'Фигуры', [['block', 'Блок'], ['cond', 'Условие'], ['circle', 'Круг'], ['pill', 'Таблетка'], ['para', 'Паралл.'], ['db', 'БД'], ['note', 'Заметка'], ['frame', 'Рамка']]],
  ['net', 'Сеть', SCHEME_NET],
  ['rooms', 'Помещения', [['wall', 'Стена'], ['door', 'Дверь'], ['window', 'Окно'], ['stairs', 'Лестница']]],
  ['uml', 'UML', [['class', 'Класс'], ['actor', 'Актор'], ['start', 'Старт'], ['end', 'Конец']]],
];
function schemeDefSize(shape, u) {                            // размер нового объекта при единице u
  if (SCHEME_NETSET[shape]) return [u, u];
  return ({ wall: [u * 2.4, u * .2], door: [u * .9, u * .9], window: [u * 1.3, u * .24], stairs: [u * .9, u * 1.5], actor: [u * .6, u], start: [u * .45, u * .45], end: [u * .5, u * .5] })[shape] || [u * 1.7, u];
}
/* рисунок объекта в рамке (x,y,w,h); без разворота — его делает внешняя группа */
function SchemeNodeArt({ shape, x, y, w, h, stroke, sw, dash, on }) {
  const cx = x + w / 2, cy = y + h / 2, fo = on ? .2 : .12;
  const common = { fill: stroke, fillOpacity: fo, stroke, strokeWidth: sw, strokeDasharray: dash, strokeLinejoin: 'round', strokeLinecap: 'round' };
  const line = { fill: 'none', stroke, strokeWidth: sw, strokeLinecap: 'round', strokeLinejoin: 'round' };
  if (SCHEME_NETSET[shape]) {
    const g = Math.min(w, h) * .56, d = THEME.icons[shape] || ICON_PATHS[shape] || PACK_PATHS[shape] || ICON_PATHS.other;
    return <><rect x={x} y={y} width={w} height={h} rx={Math.min(w, h) * .22} {...common} />
      <g transform={`translate(${cx - g / 2},${cy - g / 2}) scale(${g / 24})`} fill="none" stroke={stroke} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        {d.split('M').filter(Boolean).map((p, i) => <path key={i} d={'M' + p} />)}</g></>;
  }
  switch (shape) {
    case 'cond': return <polygon points={`${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}`} {...common} />;
    case 'circle': return <ellipse cx={cx} cy={cy} rx={w / 2} ry={h / 2} {...common} />;
    case 'pill': return <rect x={x} y={y} width={w} height={h} rx={h / 2} {...common} />;
    case 'para': return <polygon points={`${x + w * .18},${y} ${x + w},${y} ${x + w * .82},${y + h} ${x},${y + h}`} {...common} />;
    case 'db': { const ry = Math.min(h * .16, w * .3);
      return <><path d={`M${x} ${y + ry} A${w / 2} ${ry} 0 0 1 ${x + w} ${y + ry} V${y + h - ry} A${w / 2} ${ry} 0 0 1 ${x} ${y + h - ry} Z`} {...common} />
        <path d={`M${x} ${y + ry} A${w / 2} ${ry} 0 0 0 ${x + w} ${y + ry}`} {...line} /></>; }
    case 'note': { const f = Math.min(w, h) * .26;
      return <><polygon points={`${x},${y} ${x + w - f},${y} ${x + w},${y + f} ${x + w},${y + h} ${x},${y + h}`} {...common} /><path d={`M${x + w - f} ${y} V${y + f} H${x + w}`} {...line} /></>; }
    case 'frame': return <rect x={x} y={y} width={w} height={h} rx={4} fill="none" stroke={stroke} strokeWidth={sw} strokeDasharray={dash || `${sw * 4} ${sw * 3}`} />;
    case 'wall': return <rect x={x} y={y} width={w} height={h} fill={stroke} fillOpacity={on ? .95 : .8} stroke={stroke} strokeWidth={sw * .5} />;
    case 'door': return <><path d={`M${x} ${y + h} V${y} A${w} ${h} 0 0 1 ${x + w} ${y + h}`} {...line} /><line x1={x} y1={y + h} x2={x + w} y2={y + h} {...line} strokeDasharray={`${sw * 2} ${sw * 2}`} /></>;
    case 'window': return <><rect x={x} y={y} width={w} height={h} {...common} /><line x1={x} y1={cy} x2={x + w} y2={cy} {...line} /></>;
    case 'stairs': return <><rect x={x} y={y} width={w} height={h} {...common} />{[1, 2, 3, 4].map(i => <line key={i} x1={x} y1={y + h * i / 5} x2={x + w} y2={y + h * i / 5} {...line} />)}</>;
    case 'class': return <><rect x={x} y={y} width={w} height={h} rx={3} {...common} /><line x1={x} y1={y + h * .3} x2={x + w} y2={y + h * .3} {...line} /><line x1={x} y1={y + h * .66} x2={x + w} y2={y + h * .66} {...line} /></>;
    case 'actor': return <><circle cx={cx} cy={y + h * .15} r={Math.min(w, h) * .15} {...common} /><path d={`M${cx} ${y + h * .3}V${y + h * .66}M${x + w * .1} ${y + h * .44}H${x + w * .9}M${cx} ${y + h * .66}L${x + w * .15} ${y + h}M${cx} ${y + h * .66}L${x + w * .85} ${y + h}`} {...line} /></>;
    case 'start': return <circle cx={cx} cy={cy} r={Math.min(w, h) / 2} fill={stroke} stroke={stroke} strokeWidth={sw} />;
    case 'end': return <><circle cx={cx} cy={cy} r={Math.min(w, h) / 2} fill="none" stroke={stroke} strokeWidth={sw} /><circle cx={cx} cy={cy} r={Math.min(w, h) * .3} fill={stroke} /></>;
    default: return <rect x={x} y={y} width={w} height={h} rx={Math.min(w, h) * .12} {...common} />;       // block
  }
}

function schemeLinePts(s, W, H) {                            // точки линии/провода в мировых пикселях (дуга — ломаная из точек)
  if (s.kind === 'wire' && s.pts) return s.pts.map(q => [q[0] * W, q[1] * H]);
  const x1 = s.x1 * W, y1 = s.y1 * H, x2 = s.x2 * W, y2 = s.y2 * H;
  if (s.curve) {
    const dx = x2 - x1, dy = y2 - y1, cx = (x1 + x2) / 2 - dy * .3, cy = (y1 + y2) / 2 + dx * .3, out = [];
    for (let i = 0; i <= 20; i++) { const t = i / 20, u = 1 - t; out.push([u * u * x1 + 2 * u * t * cx + t * t * x2, u * u * y1 + 2 * u * t * cy + t * t * y2]); }
    return out;
  }
  return [[x1, y1], [x2, y2]];
}
function schemeDrop(list, ids) {                              // убрать фигуры вместе с проводами «узел → узел», которые к ним привязаны
  return list.filter(x => !ids.includes(x.id) && !(x.from && (ids.includes(x.from) || ids.includes(x.to))));
}
function schemeResolveLinks(list, W, H) {                     // провод «узел → узел» каждый раз заново ложится между краями объектов
  if (!list.some(x => x.from)) return list;
  const byId = {}; list.forEach(x => { byId[x.id] = x; });
  const box = n => { const l = Math.min(n.x1, n.x2) * W, r = Math.max(n.x1, n.x2) * W, t = Math.min(n.y1, n.y2) * H, b = Math.max(n.y1, n.y2) * H; return { l, r, t, b, cx: (l + r) / 2, cy: (t + b) / 2 }; };
  return list.map(x => {
    if (x.kind !== 'wire' || !x.from) return x;
    const a = byId[x.from], b = byId[x.to];
    if (!a || !b || a.kind !== 'node' || b.kind !== 'node') return x;
    const A = box(a), B = box(b); let p1, p2;
    if (Math.abs(B.cx - A.cx) >= Math.abs(B.cy - A.cy)) { const right = B.cx >= A.cx; p1 = { x: right ? A.r : A.l, y: A.cy }; p2 = { x: right ? B.l : B.r, y: B.cy }; }
    else { const down = B.cy >= A.cy; p1 = { x: A.cx, y: down ? A.b : A.t }; p2 = { x: B.cx, y: down ? B.t : B.b }; }
    const pts = schemeRoute(p1, p2).map(q => [q.x / W, q.y / H]);
    return { ...x, pts, x1: pts[0][0], y1: pts[0][1], x2: pts[pts.length - 1][0], y2: pts[pts.length - 1][1] };
  });
}

function schemeSegDist(p, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1, len2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((p.x - x1) * dx + (p.y - y1) * dy) / len2));
  return Math.hypot(p.x - (x1 + dx * t), p.y - (y1 + dy * t));
}

function schemeHitTest(shapes, p0, W, H) {                     // мировые пиксели → ближайшая фигура под точкой (или null)
  const T = 10 * Math.max(W, H) / 1000;                       // допуск на попадание, по масштабу картинки
  let best = null, bestD = T;
  for (const s of shapes) {
    const x1 = s.x1 * W, y1 = s.y1 * H, x2 = s.x2 * W, y2 = s.y2 * H;
    const p = s.rot ? schemeRot(p0, schemeBoxCenter(s, W, H), -s.rot) : p0;        // развёрнутую фигуру проверяем в её осях
    if (s.kind === 'rect') {
      const l = Math.min(x1, x2), r = Math.max(x1, x2), t = Math.min(y1, y2), b = Math.max(y1, y2);
      const dEdge = Math.min(Math.abs(p.x - l), Math.abs(p.x - r), Math.abs(p.y - t), Math.abs(p.y - b));
      if (p.x >= l - T && p.x <= r + T && p.y >= t - T && p.y <= b + T && dEdge < bestD) { best = s; bestD = dEdge; }
    } else if (s.kind === 'node') {
      const l = Math.min(x1, x2), r = Math.max(x1, x2), t = Math.min(y1, y2), b = Math.max(y1, y2);
      if (p.x >= l - T && p.x <= r + T && p.y >= t - T && p.y <= b + T && 1 < bestD) { best = s; bestD = 1; }
    } else if (s.kind === 'text') {
      const r = schemeTextBox(s, W, H);
      if (p.x >= r.x - T && p.x <= r.x + r.w + T && p.y >= r.y - T && p.y <= r.y + r.h + T && 0.5 < bestD) { best = s; bestD = 0.5; }
    } else {
      const lp = schemeLinePts(s, W, H);
      for (let i = 1; i < lp.length; i++) { const d = schemeSegDist(p, lp[i - 1][0], lp[i - 1][1], lp[i][0], lp[i][1]); if (d < bestD) { best = s; bestD = d; } }
      if (s.closed && lp.length > 2) { const d = schemeSegDist(p, lp[lp.length - 1][0], lp[lp.length - 1][1], lp[0][0], lp[0][1]); if (d < bestD) { best = s; bestD = d; } }
    }
  }
  return best;
}

/* привязка точки А/Б к уже нарисованному: концы линий и проводов, углы зон (как «привязка» в «Диаграммах»); иначе — точка как есть */
function schemeSnapPoint(shapes, p, W, H) {
  const T = 16 * Math.max(W, H) / 1000;
  let best = null, bestD = T;
  const tryPt = (x, y) => { const d = Math.hypot(p.x - x, p.y - y); if (d < bestD) { bestD = d; best = { x, y }; } };
  for (const s of shapes) {
    if (s.kind === 'text' || s.kind === 'node') continue;
    if (s.kind === 'rect') { tryPt(s.x1 * W, s.y1 * H); tryPt(s.x2 * W, s.y1 * H); tryPt(s.x1 * W, s.y2 * H); tryPt(s.x2 * W, s.y2 * H); }
    else if (s.kind === 'wire' && s.pts) s.pts.forEach(q => tryPt(q[0] * W, q[1] * H));
    else { tryPt(s.x1 * W, s.y1 * H); tryPt(s.x2 * W, s.y2 * H); }
  }
  return best || p;
}

/* провод А→Б сам: ломаная с прямыми углами «Z» — по длинной стороне до середины, поперёк, дальше до Б (как «умная стрелка» в «Диаграммах»);
   если А и Б почти на одной линии — прямая. Возвращает точки в мировых пикселях. */
function schemeRoute(a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, eps = 2;
  if (Math.abs(dx) < eps || Math.abs(dy) < eps) return [a, b];
  if (Math.abs(dx) >= Math.abs(dy)) { const mx = a.x + dx / 2; return [a, { x: mx, y: a.y }, { x: mx, y: b.y }, b]; }
  const my = a.y + dy / 2; return [a, { x: a.x, y: my }, { x: b.x, y: my }, b];
}

function schemeLabelAt(s, W, H) {                             // где ставить подпись фигуры
  if (s.kind === 'wire' && s.pts && s.pts.length > 1) {
    const i = Math.floor((s.pts.length - 1) / 2), p = s.pts[i], q = s.pts[i + 1];
    return { x: (p[0] + q[0]) / 2 * W, y: (p[1] + q[1]) / 2 * H };
  }
  return { x: (s.x1 + s.x2) / 2 * W, y: (s.y1 + s.y2) / 2 * H };
}

/* значки, которых нет в общем наборе */
const SCHEME_IC = {
  wire: <><circle cx="5" cy="18" r="2.2" /><circle cx="19" cy="6" r="2.2" /><path d="M7.2 18H12V6h4.8" /></>,
  redo: <path d="M15 14l5-5-5-5M20 9H9.5a5.5 5.5 0 0 0 0 11H13" />,
  line: <path d="M5 19L19 5" />,
  rect: <rect x="4" y="6" width="16" height="12" rx="2" />,
  text: <path d="M5 6h14M12 6v13M9 19h6" />,
  dup: <><rect x="8.5" y="8.5" width="11" height="11" rx="2" /><path d="M5 15.5V6.5a1.5 1.5 0 0 1 1.5-1.5h9" /></>,
  dash: <path d="M3.5 12h3.5M10.2 12h3.6M17 12h3.5" />,
  arrow: <path d="M4 12h15M14 6.5l5.5 5.5-5.5 5.5" />,
  thick: <path d="M4 7h16M4 12h16M4 18h16" strokeWidth="1" />,
  fsize: <path d="M3 18l5-12 5 12M5 14h6M15 18l3-7 3 7M16 16h4" />,
  pen: <path d="M4 20l1-4L16 5l3 3L8 19zM14 7l3 3" />,
  rotL: <path d="M4 12a8 8 0 1 0 2.6-5.9M4 4v4.5h4.5" />,
  rotR: <path d="M20 12a8 8 0 1 1-2.6-5.9M20 4v4.5h-4.5" />,
  plus: <path d="M12 5v14M5 12h14" />,
  multi: <><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" /><path d="M12 9v6M9 12h6" /></>,
  curve: <path d="M4 19C4 10 10 5 20 5" />,
  grip: <path d="M12 3v18M3 12h18M12 3l-2.5 2.5M12 3l2.5 2.5M12 21l-2.5-2.5M12 21l2.5-2.5M3 12l2.5-2.5M3 12l2.5 2.5M21 12l-2.5-2.5M21 12l-2.5 2.5" />,
  noimg: <><rect x="3.5" y="5" width="17" height="14" rx="2" /><path d="M3.5 19L20.5 5" /></>,
};
function SchemeIc({ name, size = 22 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{SCHEME_IC[name]}</svg>;
}

async function schemeFileToBlob(file) {                       // как в 46_planbg.jsx: не больше 2000 px по стороне, JPEG
  const img = await new Promise((ok, bad) => { const im = new Image(); im.onload = () => ok(im); im.onerror = bad; im.src = URL.createObjectURL(file); });
  const M = 2000, k = Math.min(1, M / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.round(img.naturalWidth * k), h = Math.round(img.naturalHeight * k);
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  cv.getContext('2d').drawImage(img, 0, 0, w, h);
  URL.revokeObjectURL(img.src);
  return await new Promise(ok => cv.toBlob(ok, 'image/jpeg', .88));
}

/* длины кабелей, которые уже знает Rack Live (последний кабельный тест порта) — чтобы не искать и не вводить вручную */
function schemeCableOptions(data) {
  const out = [];
  (data.devices || []).forEach(d => (((d.state || {}).ports) || []).forEach(p => {
    if (p.cable && p.cable.length) out.push({ key: d.id + ':' + p.n, text: `${nameNoFlag(d.name)}, порт ${p.n} — ${p.cable.length} м`, label: `${p.cable.length} м` });
  }));
  return out;
}

/* настоящие объекты Rack Live на схеме: устройства из локальной сети (не удалённые) и места (шкафы, щитки, комнаты); связь хранится в dev: id устройства или «p:» + id места */
const SCHEME_KIND_SHAPE = { router: 'router', switch: 'switch', server: 'server', nas: 'nas', ap: 'ap', camera: 'camera', nvr: 'nvr', ups: 'ups', modem: 'modem', pc: 'pc', laptop: 'pc' };
const SCHEME_PLACE_SHAPE = { rack: 'rack', box: 'patch', place: 'block' };
const schemeLocal = d => d.location !== 'remote';
function schemeReal(data) {                                  // всё, что можно поставить: { key, dev, shape, name, sub, status, place }
  const devs = data.devices || [], byId = Object.fromEntries(devs.map(d => [d.id, d])), out = [];
  (data.racks || []).forEach(r => {
    const st = (r.units || []).flatMap(u => unitDevIds(u)).map(id => byId[id] && byId[id].state && byId[id].state.status).filter(Boolean);
    out.push({ key: 'p:' + r.id, dev: 'p:' + r.id, shape: SCHEME_PLACE_SHAPE[r.kind] || 'rack', name: r.name, sub: (PLACE_KINDS[r.kind] || PLACE_KINDS.rack).label, group: 'Шкафы, щитки, комнаты', place: true,
      status: st.includes('offline') ? 'offline' : st.includes('warning') ? 'warning' : st.length ? 'online' : '' });
  });
  devs.filter(schemeLocal).forEach(d => out.push({ key: d.id, dev: d.id, shape: SCHEME_KIND_SHAPE[d.kind] || 'pc', name: nameNoFlag(d.name), sub: KIND_TEXT[d.kind] || '', group: KIND_TEXT[d.kind] || 'Другое', place: false, status: (d.state && d.state.status) || '' }));
  return out;
}

function SchemeLabelBox({ shape, data, onSave, onDelete, onClose }) {
  const [v, setV] = useState(shape.label || '');
  const [pick, setPick] = useState(false);
  const [dv, setDv] = useState(shape.dev || '');
  const opts = useMemo(() => schemeCableOptions(data), [data]);
  const real = useMemo(() => schemeReal(data), [data]);
  return <div className="scheme-labelbox">
    <input className="input grow" value={v} autoFocus placeholder={shape.kind === 'text' ? 'Текст на схеме' : shape.kind === 'node' ? 'Название объекта' : shape.kind === 'rect' ? 'Название зоны, например «Серверная»' : 'Подпись, например «24 м»'} onChange={e => setV(e.target.value)} />
    {shape.kind === 'node' ? <select className="input" aria-label="Устройство" value={dv} style={{ width: '100%', marginTop: 8 }}
      onChange={e => { setDv(e.target.value); const d = real.find(x => x.dev === e.target.value); if (d && !v.trim()) setV(d.name); }}>
      <option value="">Не связано с реальным объектом</option>
      <optgroup label="Шкафы, щитки, комнаты">{real.filter(x => x.place).map(x => <option key={x.key} value={x.dev}>{x.name}</option>)}</optgroup>
      <optgroup label="Локальная сеть">{real.filter(x => !x.place).map(x => <option key={x.key} value={x.dev}>{x.name}</option>)}</optgroup>
      {dv && !real.some(x => x.dev === dv) ? <option value={dv}>{(((data.devices || []).find(x => x.id === dv)) || {}).name || dv} (удалённое)</option> : null}</select> : null}
    <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
      {opts.length ? <Btn size="sm" onClick={() => setPick(!pick)}>Взять из теста кабеля</Btn> : null}
      <div className="grow" />
      <Btn size="sm" kind="danger" onClick={onDelete}>Удалить</Btn>
      <Btn size="sm" onClick={onClose}>Отмена</Btn>
      <Btn size="sm" kind="primary" onClick={() => onSave(v, dv)}>Сохранить</Btn>
    </div>
    {pick ? <div className="scheme-cable-pick">{opts.map(o => <button type="button" key={o.key} onClick={() => { setV(o.label); setPick(false); }}>{o.text}</button>)}</div> : null}
  </div>;
}

function SchemeView({ building, back }) {
  const { data, admin, edit, setMode, refresh, openDevice, openPlace } = useApp();
  const ed = !!(admin && edit);                              // правка — только в режиме редактирования, иначе просмотр готовой схемы
  const toast = useToast(); const confirm = useConfirm();
  const scheme = building.scheme || { bg: null, shapes: [] };
  const [shapes, setShapes] = useState(scheme.shapes || []);
  const [imgSize, setImgSize] = useState(null);
  const [tool, setTool] = useState('select');                 // select | line | rect | wire | text | erase
  const [color, setColor] = useState('blue');
  const [style, setStyle] = useState({ w: 1, dash: false, arrow: 0, fs: 1 });
  const [draft, setDraft] = useState(null);
  const [wireA, setWireA] = useState(null);                    // провод А→Б: первая точка (мировые пиксели), ждём точку Б
  const [sel, setSel] = useState(null);
  const [editing, setEditing] = useState(null);                // {id} — открыта подпись
  const [busy, setBusy] = useState('');
  const [more, setMore] = useState([]);                    // ещё выбранные фигуры (выбор нескольких)
  const [addMode, setAddMode] = useState(false);               // «выбрать ещё»: касание добавляет/убирает фигуру из выбора
  const [wireMode, setWireMode] = useState('ab');              // провод: ab — по двум точкам, poly — по точкам, link — между объектами
  const [polyPts, setPolyPts] = useState([]);
  const [linkA, setLinkA] = useState(null);
  const [lib, setLib] = useState(null);                       // открыт набор объектов: null или id вкладки («real» — настоящие объекты сети)
  const [libQ, setLibQ] = useState('');
  const [guides, setGuides] = useState(null);                   // направляющие при переносе: { lines, marks }
  const real = useMemo(() => schemeReal(data), [data]);
  const realByDev = useMemo(() => Object.fromEntries(real.map(x => [x.dev, x])), [real]);
  const [, setHv] = useState(0);                               // перерисовать док после отмены/возврата
  const fileRef = useRef(null);
  const wrap = useRef(null);
  const saveTimer = useRef(0);
  const undoSt = useRef([]), redoSt = useRef([]);
  const viewRef = useRef({ x: 0, y: 0, k: 1 });

  useEffect(() => { setShapes(scheme.shapes || []); setSel(null); setEditing(null); setWireA(null); setMore([]); setPolyPts([]); setLinkA(null); undoSt.current = []; redoSt.current = []; }, [building.id, scheme.bg && scheme.bg.v]);
  useEffect(() => { if (!ed) { setTool('select'); setSel(null); setEditing(null); setWireA(null); setDraft(null); setLib(null); setMore([]); setAddMode(false); setPolyPts([]); setLinkA(null); } }, [ed]);
  const bgUrl = scheme.bg ? `/api/plan/scheme/${building.id}?v=${scheme.bg.v}` : null;
  useEffect(() => {
    if (!bgUrl) { setImgSize(null); return; }
    let dead = false; const im = new Image();
    im.onload = () => { if (!dead) setImgSize({ w: im.naturalWidth, h: im.naturalHeight }); };
    im.src = bgUrl;
    return () => { dead = true; };
  }, [bgUrl]);
  const W = imgSize ? imgSize.w : 1200, H = imgSize ? imgSize.h : 800;
  const shapesV = useMemo(() => schemeResolveLinks(shapes, W, H), [shapes, W, H]);

  /* нижний док переключается в режим схемы только пока включено редактирование: обычные значки скрываются (CSS по классу на <html>) */
  useEffect(() => {
    if (!ed) return;
    const h = document.documentElement; h.classList.add('scheme-edit');
    return () => h.classList.remove('scheme-edit');
  }, [ed]);

  useEffect(() => {                                           // высота дока — в переменную CSS: кнопки сбоку (кружок «⋯/×», «+», «−», «Редактирование») стоят над ним
    if (!ed) return;
    const el = document.querySelector('.scheme-dock'); if (!el) return;
    const h = document.documentElement, set = () => h.style.setProperty('--scheme-dock-h', el.offsetHeight + 'px');
    set(); const ro = window.ResizeObserver ? new ResizeObserver(set) : null; if (ro) ro.observe(el);
    return () => { if (ro) ro.disconnect(); h.style.removeProperty('--scheme-dock-h'); };
  }, [ed]);

  /* клавиатура: когда выезжает (подпись, текст), док и боковые кнопки поднимаются над ней, а фигура, которую подписывают, плавно уезжает в видимую часть */
  const [kb, setKb] = useState(0);
  useEffect(() => {
    const vv = window.visualViewport; if (!ed || !vv) return;
    let raf = 0, t1 = 0, t2 = 0;
    const calc = () => {
      const a = document.activeElement, typing = a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable);
      const k = Math.round(window.innerHeight - vv.height - vv.offsetTop);
      setKb(typing && k > 80 ? k : 0);
    };
    const on = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(calc); };
    const off = () => { clearTimeout(t1); clearTimeout(t2); t1 = setTimeout(calc, 120); t2 = setTimeout(calc, 500); };
    on(); vv.addEventListener('resize', on); vv.addEventListener('scroll', on);
    window.addEventListener('focusout', off); window.addEventListener('orientationchange', off);
    return () => { cancelAnimationFrame(raf); clearTimeout(t1); clearTimeout(t2); vv.removeEventListener('resize', on); vv.removeEventListener('scroll', on); window.removeEventListener('focusout', off); window.removeEventListener('orientationchange', off); setKb(0); };
  }, [ed]);
  useEffect(() => { const h = document.documentElement; h.style.setProperty('--scheme-kb', kb + 'px'); return () => h.style.removeProperty('--scheme-kb'); }, [kb]);
  const panShift = useRef(0), prevKb = useRef(0);
  useEffect(() => {                                           // клавиатура закрылась: схема возвращается на место, куда её сдвигали
    if (prevKb.current > 0 && kb === 0 && panShift.current) { const d = panShift.current; panShift.current = 0; setView(p => ({ ...p, y: p.y - d })); }
    if (kb === 0) panShift.current = 0;
    prevKb.current = kb;
  }, [kb]);
  useEffect(() => {
    if (!ed || !editing) return;
    const t = setTimeout(() => {
      const sh = shapesV.find(x => x.id === editing.id), dockEl = document.querySelector('.scheme-dock'), el = wrap.current;
      if (!sh || !dockEl || !el) return;
      const r = el.getBoundingClientRect(), v = viewRef.current, c = schemeBoxCenter(sh, W, H);
      const sy = r.top + v.y + c.y * v.k, top = r.top + 80, bottom = dockEl.getBoundingClientRect().top - 24;
      if (sy > bottom || sy < top) { const dy = (top + bottom) / 2 - sy; if (kb > 0) panShift.current += dy; setView(p => ({ ...p, y: p.y + dy })); }
    }, 380);
    return () => clearTimeout(t);
  }, [editing && editing.id, kb]);

  const persist = (next) => {
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try { await api('/api/plan/scheme', { method: 'PUT', body: { building: building.id, shapes: next } }); await refresh(); }
      catch (e) { toast(e.message, true); }
    }, 500);
  };
  const saveShapes = (next) => {
    undoSt.current = [...undoSt.current.slice(-49), shapes]; redoSt.current = [];
    setShapes(next); persist(next); setHv(n => n + 1);
  };
  const undo = () => { const prev = undoSt.current.pop(); if (!prev) return; redoSt.current.push(shapes); setSel(null); setEditing(null); setShapes(prev); persist(prev); setHv(n => n + 1); };
  const redo = () => { const nx = redoSt.current.pop(); if (!nx) return; undoSt.current.push(shapes); setSel(null); setEditing(null); setShapes(nx); persist(nx); setHv(n => n + 1); };

  const pickTool = (id) => { setTool(id); setSel(null); setMore([]); setAddMode(false); setEditing(null); setWireA(null); setDraft(null); setPolyPts([]); setLinkA(null); };
  const pickWireMode = (m) => { setWireMode(m); setWireA(null); setPolyPts([]); setLinkA(null); };
  const selShape = shapesV.find(s => s.id === sel);
  const editShape = editing && shapesV.find(s => s.id === editing.id);
  const groupIds = selShape ? [selShape.id, ...more.filter(id => shapes.some(x => x.id === id))] : [];
  const setProp = (patch) => {                                 // стиль: выбранной фигуре, а если ничего не выбрано — тем, что будут нарисованы дальше
    if (selShape) saveShapes(shapes.map(x => x.id === selShape.id ? { ...x, ...patch } : x)); else setStyle(st => ({ ...st, ...patch }));
  };
  const pickColor = (c) => { setColor(c); if (selShape) saveShapes(shapes.map(x => groupIds.includes(x.id) ? { ...x, color: c } : x)); };
  const toFront = () => { const x = shapes.find(q => q.id === selShape.id); saveShapes([...shapes.filter(q => q.id !== x.id), x]); };
  const toBack = () => { const x = shapes.find(q => q.id === selShape.id); saveShapes([x, ...shapes.filter(q => q.id !== x.id)]); };
  const closeEdit = (sh) => { setEditing(null); if (sh && sh.kind === 'text' && !sh.label) { saveShapes(schemeDrop(shapes, [sh.id])); setSel(null); } };
  const duplicate = () => {
    if (!selShape) return; const d = 0.02, copies = [], ids = [];
    shapes.filter(x => groupIds.includes(x.id) && !x.from).forEach(x => {
      const id = uid('s'), cp = { ...x, id, x1: x.x1 + d, y1: x.y1 + d, x2: x.x2 + d, y2: x.y2 + d };
      if (x.pts) cp.pts = x.pts.map(q => [q[0] + d, q[1] + d]);
      copies.push(cp); ids.push(id);
    });
    if (!copies.length) return;
    saveShapes([...shapes, ...copies]); setSel(ids[0]); setMore(ids.slice(1));
  };

  const place = (shape, extra) => {                            // поставить объект в центр экрана (extra — связь с реальным объектом)
    const u = Math.max(W, H) / 14, [bw, bh] = schemeDefSize(shape, u), r = wrap.current.getBoundingClientRect(), v = viewRef.current;
    const off = (shapes.filter(x => x.kind === 'node').length % 5) * u * .18;
    const cx = (r.width / 2 - v.x) / v.k + off, cy = (r.height / 2 - v.y) / v.k + off;
    const id = uid('s');
    const node = { id, kind: 'node', shape, x1: (cx - bw / 2) / W, y1: (cy - bh / 2) / H, x2: (cx + bw / 2) / W, y2: (cy + bh / 2) / H, color, label: '', ...(style.w > 1 ? { w: style.w } : {}), ...(style.dash ? { dash: true } : {}), ...(extra || {}) };
    saveShapes([...shapes, node]); setSel(id); setTool('select'); setLib(null); setEditing(extra ? null : SCHEME_NETSET[shape] || ['block', 'cond', 'circle', 'pill', 'para', 'db', 'note', 'class'].includes(shape) ? { id } : null);
  };
  const addWire = (a, b) => {
    const route = schemeRoute(a, b);
    const id = uid('s');
    const pts = route.map(q => [schemeClamp01(q.x / W), schemeClamp01(q.y / H)]);
    const shape = { id, kind: 'wire', x1: pts[0][0], y1: pts[0][1], x2: pts[pts.length - 1][0], y2: pts[pts.length - 1][1], pts, color, label: '', ...(style.w > 1 ? { w: style.w } : {}), ...(style.dash ? { dash: true } : {}), ...(style.arrow ? { arrow: style.arrow } : {}) };
    setSel(id); setEditing({ id });
    saveShapes([...shapes, shape]);
  };
  const finishPoly = (closed) => {                            // провод «по точкам»: касались углов, закончили
    if (polyPts.length < 2) return;
    const pts = polyPts.map(q => [schemeClamp01(q.x / W), schemeClamp01(q.y / H)]), id = uid('s');
    const shape = { id, kind: 'wire', free: true, ...(closed && pts.length > 2 ? { closed: true } : {}), pts, x1: pts[0][0], y1: pts[0][1], x2: pts[pts.length - 1][0], y2: pts[pts.length - 1][1], color, label: '', ...(style.w > 1 ? { w: style.w } : {}), ...(style.dash ? { dash: true } : {}), ...(style.arrow && !closed ? { arrow: style.arrow } : {}) };
    setPolyPts([]); setSel(id); setEditing({ id }); saveShapes([...shapes, shape]);
  };
  const addLink = (from, to) => {                              // провод «узел → узел»
    const id = uid('s');
    const base = { id, kind: 'wire', from, to, pts: [[0, 0], [0, 0]], x1: 0, y1: 0, x2: 0, y2: 0, color, label: '', ...(style.w > 1 ? { w: style.w } : {}), ...(style.dash ? { dash: true } : {}), ...(style.arrow ? { arrow: style.arrow } : {}) };
    const shape = schemeResolveLinks([...shapes, base], W, H).pop();
    setSel(id); setEditing({ id }); saveShapes([...shapes, shape]);
  };

  /* перенос: потянуть фигуру; растягивание: потянуть кружок на конце. Пока тянем — правится локально, на сервер уходит один раз в конце */
  const toWorld = (e) => { const r = wrap.current.getBoundingClientRect(), v = viewRef.current; return { x: (e.clientX - r.left - v.x) / v.k, y: (e.clientY - r.top - v.y) / v.k }; };
  const startDrag = (e, sh, mode) => {
    if (!ed || tool !== 'select') return;
    e.stopPropagation();
    if (addMode && sel && mode === 'move' && sh.id !== sel) { setMore(m => m.includes(sh.id) ? m.filter(i => i !== sh.id) : [...m, sh.id]); return; }
    const inGroup = mode === 'move' && more.length && (sh.id === sel || more.includes(sh.id));
    if (!inGroup) { setSel(sh.id); setMore([]); }
    setEditing(null);
    if (sh.lock || sh.from) return;                          // с замком и связанные провода не двигаются
    const ids = inGroup ? groupIds.filter(i => { const q = shapes.find(x => x.id === i); return q && !q.lock && !q.from; }) : [sh.id];
    const start = toWorld(e), orig = shapes; let moved = false, live = orig;
    const onMove = (ev) => {
      const p = toWorld(ev);
      if (!moved && Math.hypot(p.x - start.x, p.y - start.y) * viewRef.current.k < 4) return;
      moved = true;
      live = orig.map(x => ids.includes(x.id) ? schemeDrag(x, mode, start, p, W, H, orig) : x);
      if (mode === 'move') {                                   // магнит: липнем к соседям и показываем линии и равные промежутки
        const mv = live.filter(x => ids.includes(x.id)).map(x => schemeBoxOf(x, W, H));
        let M = { l: Math.min(...mv.map(b => b.l)), t: Math.min(...mv.map(b => b.t)), r: Math.max(...mv.map(b => b.r)), b: Math.max(...mv.map(b => b.b)) };
        const oth = live.filter(x => !ids.includes(x.id) && ['node', 'rect', 'text'].includes(x.kind)).map(x => schemeBoxOf(x, W, H)), T = 7 / viewRef.current.k;
        const sx = schemeSnapAxis(M, oth, 'x', T), sy = schemeSnapAxis(M, oth, 'y', T);
        if (sx || sy) { live = live.map(x => ids.includes(x.id) ? schemeShift(x, sx / W, sy / H) : x); M = { l: M.l + sx, r: M.r + sx, t: M.t + sy, b: M.b + sy }; }
        const gx = schemeGuideOf(M, oth, 'x'), gy = schemeGuideOf(M, oth, 'y');
        setGuides({ lines: [...gx.lines, ...gy.lines], marks: [...gx.marks, ...gy.marks] });
      }
      setShapes(live);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); window.removeEventListener('pointercancel', onUp);
      setGuides(null);
      if (moved) { undoSt.current = [...undoSt.current.slice(-49), orig]; redoSt.current = []; persist(live); setHv(n => n + 1); }
    };
    window.addEventListener('pointermove', onMove); window.addEventListener('pointerup', onUp); window.addEventListener('pointercancel', onUp);
  };

  const { view, setView, bind } = usePanZoom(wrap, {
    canPan: () => tool !== 'line' && tool !== 'rect' || !ed,
    onDraw: ed ? (w0, w1, up) => {
      if (tool !== 'line' && tool !== 'rect') return;
      setDraft({ kind: tool, x1: w0.x, y1: w0.y, x2: w1.x, y2: w1.y });
      if (up) {
        setDraft(null);
        if (Math.hypot(w1.x - w0.x, w1.y - w0.y) < 6) return;      // короткий тап — не фигура
        const id = uid('s');
        const shape = { id, kind: tool, x1: schemeClamp01(w0.x / W), y1: schemeClamp01(w0.y / H), x2: schemeClamp01(w1.x / W), y2: schemeClamp01(w1.y / H), color, label: '', ...(style.w > 1 ? { w: style.w } : {}), ...(style.dash ? { dash: true } : {}), ...(tool === 'line' && style.arrow ? { arrow: style.arrow } : {}) };
        setSel(id); setEditing({ id });
        saveShapes([...shapes, shape]);
      }
    } : undefined,
    onTap: (w0, target) => {
      if (!ed) {                                              // просмотр: касание объекта, привязанного к устройству, открывает его
        const h = schemeHitTest(shapesV, w0, W, H);
        if (h && h.dev && String(h.dev).startsWith('p:')) { if (openPlace) openPlace(String(h.dev).slice(2)); return; }
        const d = h && h.dev && (data.devices || []).find(x => x.id === h.dev);
        if (d && openDevice) openDevice(d);
        return;
      }
      if (tool === 'erase') {
        const hit = schemeHitTest(shapesV, w0, W, H);
        if (hit) saveShapes(schemeDrop(shapes, [hit.id]));
        return;
      }
      if (tool === 'text') {                                    // надпись: коснулись места — открылось поле ввода
        const id = uid('s'), x = schemeClamp01(w0.x / W), y = schemeClamp01(w0.y / H);
        setSel(id); setEditing({ id });
        saveShapes([...shapes, { id, kind: 'text', x1: x, y1: y, x2: x, y2: y, color, label: '', ...(style.fs > 1 ? { fs: style.fs } : {}) }]);
        return;
      }
      if (tool === 'wire' && wireMode === 'link') {           // провод «узел → узел»: коснулись объекта А, потом Б
        const hit = schemeHitTest(shapesV.filter(x => x.kind === 'node'), w0, W, H);
        if (!hit) { toast('Коснитесь объекта из набора'); return; }
        if (!linkA) { setLinkA(hit.id); return; }
        if (hit.id === linkA) { setLinkA(null); return; }
        addLink(linkA, hit.id); setLinkA(null);
        return;
      }
      if (tool === 'wire' && wireMode === 'poly') {           // провод по точкам: касайтесь углов, потом «Готово»
        const p = schemeSnapPoint(shapesV, w0, W, H);
        if (polyPts.length >= 40) { toast('Не больше 40 точек — закончите провод'); return; }
        setPolyPts([...polyPts, p]);
        return;
      }
      if (tool === 'wire') {                                  // точка А, потом точка Б — провод между ними ложится сам
        const p = schemeSnapPoint(shapesV, w0, W, H);
        if (!wireA) { setWireA(p); return; }
        if (Math.hypot(p.x - wireA.x, p.y - wireA.y) < 6) { toast('Точка Б совпала с А — выберите другое место'); return; }
        addWire(wireA, p); setWireA(null);
        return;
      }
      if (tool === 'select') {
        const hit = schemeHitTest(shapesV, w0, W, H);
        setSel(hit ? hit.id : null); setMore([]);
      }
    },
  }, null);
  useEffect(() => { if (wrap.current) fitView(wrap.current, [0, W], [0, H], setView); }, [W, H, wrap.current]);

  const upload = async (file) => {
    if (!file) return; setBusy('upload');
    try {
      const blob = await schemeFileToBlob(file);
      await fetch(`/api/plan/scheme/bg?building=${encodeURIComponent(building.id)}`, {
        method: 'POST', credentials: 'same-origin', headers: ssGet('rl_tok') ? { 'X-RL-Session': ssGet('rl_tok') } : {}, body: blob,
      }).then(r => r.json()).then(j => { if (!j.ok) throw new Error(j.error || 'не получилось загрузить'); });
      await refresh(); toast('Фото добавлено');
    } catch (e) { toast(e.message, true); } finally { setBusy(''); if (fileRef.current) fileRef.current.value = ''; }
  };
  const removeBg = async () => {
    if (!(await confirm('Убрать фото чертежа? Линии и зоны останутся.', { title: 'Убрать фото' }))) return;
    setBusy('remove');
    try { await fetch(`/api/plan/scheme/bg?building=${encodeURIComponent(building.id)}`, { method: 'DELETE', credentials: 'same-origin', headers: ssGet('rl_tok') ? { 'X-RL-Session': ssGet('rl_tok') } : {} }); await refresh(); }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };

  const tv = view || { x: 0, y: 0, k: 1 };
  viewRef.current = tv;
  const interactive = ed && tool === 'select';
  const sw0 = Math.max(2, W / 500);
  const TOOLS = [['select', 'cursor', 'Выбрать и двигать'], ['line', 'line', 'Линия'], ['rect', 'rect', 'Зона'], ['wire', 'wire', 'Провод А→Б'], ['text', 'text', 'Текст'], ['erase', 'eraser', 'Стереть']];
  const ic = (n) => SCHEME_IC[n] ? <SchemeIc name={n} /> : <Icon name={n} size={22} />;
  const hint = tool === 'wire' ? (wireMode === 'link' ? (linkA ? 'Теперь коснитесь объекта Б' : 'Коснитесь объекта А: провод потянется за объектами')
      : wireMode === 'poly' ? (polyPts.length ? `Точек: ${polyPts.length}. Касайтесь дальше или закончите` : 'Касайтесь углов провода по очереди')
      : (wireA ? 'Теперь коснитесь точки Б' : 'Коснитесь точки А'))
    : tool === 'line' || tool === 'rect' ? 'Проведите пальцем по фото от начала до конца'
    : tool === 'text' ? 'Коснитесь места, где будет надпись'
    : tool === 'erase' ? 'Нажмите на линию, провод, зону или текст — они удалятся'
    : addMode ? 'Касайтесь фигур: они добавятся к выбору или уйдут из него'
    : !selShape ? 'Нажмите на фигуру и тяните — она переедет' : '';
  const sk = selShape ? selShape.kind : tool;                 // что настраиваем: выбранную фигуру или то, что будет нарисовано
  const cur = selShape || style, curW = cur.w || 1, curFs = cur.fs || 1;
  const showStyle = sk === 'line' || sk === 'wire' || sk === 'rect' || sk === 'text' || sk === 'node';
  const boxSel = selShape && SCHEME_BOXY.includes(selShape.kind);

  const dock = ed ? ReactDOM.createPortal(<div className="scheme-dock">
    {lib && !editShape ? <div className="scheme-dock-card scheme-lib">
      <div className="scheme-lib-tabs">{[['real', 'Из сети'], ...SCHEME_LIB].map(([id, name]) => <button key={id} type="button" className={lib === id ? 'on' : ''} onClick={() => setLib(id)}>{name}</button>)}
        <div className="grow" /><button type="button" aria-label="Закрыть" onClick={() => setLib(null)}><Icon name="x" size={18} /></button></div>
      {lib === 'real' ? <div className="scheme-real">
        <input className="input" value={libQ} placeholder="Найти: камера, шкаф, роутер…" onChange={e => setLibQ(e.target.value)} />
        {(() => {
          const q = libQ.trim().toLowerCase(), list = real.filter(x => !q || (x.name + ' ' + x.sub).toLowerCase().includes(q)), groups = [];
          list.forEach(x => { let g = groups.find(y => y[0] === x.group); if (!g) groups.push(g = [x.group, []]); g[1].push(x); });
          if (!list.length) return <div className="scheme-real-empty">{real.length ? 'Ничего не найдено' : 'В сети пока нет устройств'}</div>;
          return groups.map(([gn, items]) => <div key={gn}><div className="scheme-real-h">{gn}</div>
            <div className="scheme-lib-grid">{items.map(x => {
              const [bw, bh] = schemeDefSize(x.shape, 1), k = Math.min(54 / bw, 38 / bh), used = shapes.some(s => s.dev === x.dev);
              return <button key={x.key} type="button" className={'scheme-lib-tile' + (used ? ' used' : '')} title={x.name + (used ? ' — уже на схеме' : '')} onClick={() => place(x.shape, { dev: x.dev })}>
                <svg viewBox="0 0 80 52" width="80" height="52"><SchemeNodeArt shape={x.shape} x={40 - bw * k / 2} y={24 - bh * k / 2} w={bw * k} h={bh * k} stroke={SCHEME_COLOR_VAR[color]} sw={1.6} />
                  {schemeLed(x.status) ? <circle cx="68" cy="8" r="4.5" fill={schemeLed(x.status)} stroke="var(--bg2)" strokeWidth="1.5" /> : null}</svg><span>{x.name}</span></button>; })}</div></div>);
        })()}</div> :
      <div className="scheme-lib-grid">{(SCHEME_LIB.find(t => t[0] === lib) || SCHEME_LIB[0])[2].map(([sh, name]) => {
        const [bw, bh] = schemeDefSize(sh, 1), k = Math.min(54 / bw, 38 / bh);
        return <button key={sh} type="button" className="scheme-lib-tile" onClick={() => place(sh)}>
          <svg viewBox="0 0 80 52" width="80" height="52"><SchemeNodeArt shape={sh} x={40 - bw * k / 2} y={24 - bh * k / 2} w={bw * k} h={bh * k} stroke={SCHEME_COLOR_VAR[color]} sw={1.6} /></svg><span>{name}</span></button>; })}</div>}
    </div> : null}
    {tool === 'wire' && !editShape && !lib ? <div className="scheme-dock-row scheme-chips">{[['ab', 'А→Б'], ['poly', 'По точкам'], ['link', 'Узел→Узел']].map(([m, n]) => <button key={m} type="button" className={wireMode === m ? 'on' : ''} onClick={() => pickWireMode(m)}>{n}</button>)}</div> : null}
    {hint && !editShape && !lib ? <div className="scheme-dock-hint">{hint}{tool === 'wire' && wireMode === 'ab' && wireA ? <button type="button" onClick={() => setWireA(null)}>Сбросить А</button> : null}
      {tool === 'wire' && wireMode === 'link' && linkA ? <button type="button" onClick={() => setLinkA(null)}>Сбросить А</button> : null}
      {tool === 'wire' && wireMode === 'poly' && polyPts.length > 1 ? <button type="button" onClick={() => finishPoly(false)}>Готово</button> : null}
      {tool === 'wire' && wireMode === 'poly' && polyPts.length > 2 ? <button type="button" onClick={() => finishPoly(true)}>Замкнуть</button> : null}
      {tool === 'wire' && wireMode === 'poly' && polyPts.length ? <button type="button" onClick={() => setPolyPts([])}>Сбросить</button> : null}</div> : null}
    {editShape ? <div className="scheme-dock-card">
      <SchemeLabelBox shape={editShape} data={data}
        onSave={(v, dv) => { const t = v.trim(); if (editShape.kind === 'text' && !t) { closeEdit(editShape); return; } saveShapes(shapes.map(x => x.id === editShape.id ? { ...x, label: t, ...(editShape.kind === 'node' ? { dev: dv || undefined } : {}) } : x)); setEditing(null); }}
        onDelete={() => { saveShapes(schemeDrop(shapes, [editShape.id])); setEditing(null); setSel(null); }}
        onClose={() => closeEdit(editShape)} />
    </div> : null}
    {(selShape && !editShape) || (showStyle && !editShape) ? <div className="scheme-dock-row">
      {selShape && !editShape ? <>
        <span className="scheme-dock-name ellipsis">{selShape.label || (selShape.kind === 'rect' ? 'Зона без названия' : selShape.kind === 'wire' ? 'Провод без подписи' : selShape.kind === 'text' ? 'Текст' : 'Линия без подписи')}</span>
        <button type="button" className="sd" title={selShape.kind === 'text' ? 'Изменить текст' : 'Подпись'} aria-label="Подпись" onClick={() => setEditing({ id: selShape.id })}><SchemeIc name="pen" /></button>
        {boxSel ? <button type="button" className="sd" title="Повернуть на 90° влево" aria-label="Влево" onClick={() => setProp({ rot: Math.round((((selShape.rot || 0) - 90 + 180 + 720) % 360 - 180) * 10) / 10 })}><SchemeIc name="rotL" /></button> : null}
        {boxSel ? <button type="button" className="sd" title="Повернуть на 90° вправо" aria-label="Вправо" onClick={() => setProp({ rot: Math.round((((selShape.rot || 0) + 90 + 180 + 720) % 360 - 180) * 10) / 10 })}><SchemeIc name="rotR" /></button> : null}
        <button type="button" className="sd" title="Дублировать" aria-label="Дублировать" onClick={duplicate}><SchemeIc name="dup" /></button>
        <button type="button" className={'sd' + (addMode ? ' on' : '')} title="Выбрать несколько" aria-label="Выбрать несколько" aria-pressed={addMode} onClick={() => setAddMode(v => !v)}><SchemeIc name="multi" /></button>
        <button type="button" className="sd" title="На передний план" aria-label="Вперёд" onClick={toFront}><Icon name="arrowUp" size={21} /></button>
        <button type="button" className="sd" title="На задний план" aria-label="Назад" onClick={toBack}><Icon name="arrowUp" size={21} style={{ transform: 'rotate(180deg)' }} /></button>
        <button type="button" className={'sd' + (selShape.lock ? ' on' : '')} title={selShape.lock ? 'Снять замок' : 'Закрепить (не двигается)'} aria-label="Замок" aria-pressed={!!selShape.lock} onClick={() => setProp({ lock: !selShape.lock })}><Icon name="lock" size={20} /></button>
        <button type="button" className="sd danger" title="Удалить" aria-label="Удалить" onClick={() => { saveShapes(schemeDrop(shapes, groupIds)); setSel(null); setMore([]); setAddMode(false); }}><Icon name="trash" size={21} /></button>
        <button type="button" className="sd" title="Снять выбор" aria-label="Снять выбор" onClick={() => { setSel(null); setMore([]); setAddMode(false); }}><Icon name="x" size={21} /></button>
        {showStyle ? <div className="scheme-sep" /> : null}
      </> : null}
      {showStyle && sk !== 'text' ? <button type="button" className={'sd' + (curW > 1 ? ' on' : '')} title={'Толщина: ' + curW} aria-label="Толщина" onClick={() => setProp({ w: curW % 3 + 1 })}><SchemeIc name="thick" /></button> : null}
      {showStyle && sk !== 'text' ? <button type="button" className={'sd' + (cur.dash ? ' on' : '')} title="Пунктир" aria-label="Пунктир" aria-pressed={!!cur.dash} onClick={() => setProp({ dash: !cur.dash })}><SchemeIc name="dash" /></button> : null}
      {sk === 'line' || sk === 'wire' ? <button type="button" className={'sd' + (cur.arrow ? ' on' : '')} title={'Стрелка: ' + (['нет', 'на конце', 'на обоих концах'][Number(cur.arrow) | 0])} aria-label="Стрелка" aria-pressed={!!cur.arrow} onClick={() => setProp({ arrow: ((Number(cur.arrow) | 0) + 1) % 3 })}><SchemeIc name="arrow" /></button> : null}
      {selShape && (sk === 'line' || sk === 'wire') ? <button type="button" className={'sd' + (selShape.anim ? ' on' : '')} title="Бегущий пунктир (анимация)" aria-label="Анимация" aria-pressed={!!selShape.anim} onClick={() => setProp({ anim: !selShape.anim })}><Icon name="pulse" size={21} /></button> : null}
      {selShape && sk === 'line' ? <button type="button" className={'sd' + (selShape.curve ? ' on' : '')} title="Дуга" aria-label="Дуга" aria-pressed={!!selShape.curve} onClick={() => setProp({ curve: !selShape.curve })}><SchemeIc name="curve" /></button> : null}
      {sk === 'text' ? <button type="button" className={'sd' + (curFs > 1 ? ' on' : '')} title={'Размер текста: ' + curFs} aria-label="Размер текста" onClick={() => setProp({ fs: curFs % 3 + 1 })}><SchemeIc name="fsize" /></button> : null}
    </div> : null}
    <div className="scheme-dock-row">
      {SCHEME_COLORS.map(c => <button key={c} type="button" className={'scheme-swatch' + ((selShape ? selShape.color : color) === c ? ' on' : '')} style={{ background: SCHEME_COLOR_VAR[c] }} aria-label={c} onClick={() => pickColor(c)} />)}
      <div className="scheme-sep" />
      <button type="button" className="sd" title="Отменить" aria-label="Отменить" disabled={!undoSt.current.length} onClick={undo}><Icon name="undo" size={21} /></button>
      <button type="button" className="sd" title="Вернуть" aria-label="Вернуть" disabled={!redoSt.current.length} onClick={redo}><SchemeIc name="redo" size={21} /></button>
      <div className="scheme-sep" />
      <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => upload(e.target.files[0])} />
      <button type="button" className="sd" title={bgUrl ? 'Заменить фото чертежа' : 'Загрузить фото чертежа'} aria-label="Фото чертежа" disabled={busy === 'upload'} onClick={() => fileRef.current.click()}><Icon name="camera" size={21} /></button>
      {bgUrl ? <button type="button" className="sd" title="Убрать фото чертежа" aria-label="Убрать фото" disabled={busy === 'remove'} onClick={removeBg}><SchemeIc name="noimg" size={21} /></button> : null}
    </div>
    <div className="scheme-dock-row scheme-dock-tools">
      <button type="button" className="sd" title="Готово — выйти из редактирования" aria-label="Готово" onClick={() => setMode('view')}><Icon name="check" size={23} /></button>
      <button type="button" className={'sd' + (lib ? ' on' : '')} title="Набор объектов: фигуры, сеть, помещения, UML" aria-label="Объекты" aria-pressed={!!lib} onClick={() => setLib(l => l ? null : 'real')}><SchemeIc name="plus" /></button>
      <div className="scheme-sep" />
      {TOOLS.map(([id, icon, label]) => <button key={id} type="button" className={'sd' + (tool === id ? ' on' : '')} title={label} aria-label={label} aria-pressed={tool === id} onClick={() => pickTool(id)}>{ic(icon)}</button>)}
    </div>
  </div>, document.body) : null;

  const hr = 9 / tv.k;
  const bc = selShape ? schemeBoxCenter(selShape, W, H) : null;
  const rp = (x, y) => schemeRot({ x, y }, bc, selShape.rot || 0);                                          // радиус кружка-ручки: одинаковый на экране при любом масштабе
  let handles = [];
  if (ed && tool === 'select' && selShape && !editShape) {
    if (selShape.kind === 'text') { const r = schemeTextBox(selShape, W, H), q = rp(r.x + r.w / 2, r.y - 30 / tv.k), t = rp(r.x + r.w / 2, r.y); handles = [['rot', q.x, q.y, t]]; }
    else if (selShape.kind === 'rect' || selShape.kind === 'node') {
      const a1 = rp(selShape.x1 * W, selShape.y1 * H), a2 = rp(selShape.x2 * W, selShape.y2 * H), top = Math.min(selShape.y1, selShape.y2) * H, mx = (selShape.x1 + selShape.x2) / 2 * W;
      handles = [[1, a1.x, a1.y], [2, a2.x, a2.y], ['rot', rp(mx, top - 30 / tv.k).x, rp(mx, top - 30 / tv.k).y, rp(mx, top)]];
    } else if (!selShape.from && !selShape.closed && !selShape.free && selShape.kind !== 'node') handles = [[1, selShape.x1 * W, selShape.y1 * H], [2, selShape.x2 * W, selShape.y2 * H]];
    if (!selShape.lock && !selShape.from) { const gc = schemeBoxCenter(selShape, W, H); handles = [...handles, ['move', gc.x, gc.y]]; }      // большой кружок: тянуть за него удобнее, чем за саму фигуру
  }

  return <div className="plan-canvas scheme-canvas" ref={wrap} {...bind}>
    <AuBack fn={back} label="К дому" />
    <div className="plan-ctx plan-ovl"><Btn size="sm" icon="chevronLeft" className="au-inpage-back" onClick={back}>К дому</Btn><b className="ellipsis">Схема · {nameNoFlag(building.name)}</b>
    </div>
    <svg width="100%" height="100%" style={{ touchAction: 'none', display: 'block' }}>
      <g transform={`translate(${tv.x},${tv.y}) scale(${tv.k})`}>
        <defs><pattern id="scheme-dots" width={Math.max(W, H) / 40} height={Math.max(W, H) / 40} patternUnits="userSpaceOnUse"><circle cx={Math.max(W, H) / 80} cy={Math.max(W, H) / 80} r={Math.max(1.2, W / 800)} fill="var(--text3)" opacity=".3" /></pattern></defs>
        <rect x={-4 * W} y={-4 * H} width={9 * W} height={9 * H} fill="var(--bg2)" />
        <rect x={-4 * W} y={-4 * H} width={9 * W} height={9 * H} fill="url(#scheme-dots)" pointerEvents="none" />
        {bgUrl ? <image href={bgUrl} x={0} y={0} width={W} height={H} preserveAspectRatio="xMidYMid meet" /> : null}
        {!bgUrl ? <text x={W / 2} y={H / 2} textAnchor="middle" fontSize={Math.max(14, W / 40)} fill="var(--text3)">{ed ? 'Загрузите фото чертежа' : 'Фото чертежа не добавлено'}</text> : null}
        {shapesV.map(s => {
          const x1 = s.x1 * W, y1 = s.y1 * H, x2 = s.x2 * W, y2 = s.y2 * H;
          const stroke = SCHEME_COLOR_VAR[s.color] || SCHEME_COLOR_VAR.blue, on = (sel === s.id || more.includes(s.id)) && ed;
          const sw = sw0 * SCHEME_WMUL[(s.w || 1) - 1] * (on ? 1.3 : 1);
          const dash = s.dash ? `${sw * 3} ${sw * 2.2}` : undefined;
          const mid = schemeLabelAt(s, W, H);
          let el, hit = null;
          if (s.kind === 'node') {
            const bx = Math.min(x1, x2), by = Math.min(y1, y2), bw = Math.abs(x2 - x1), bh = Math.abs(y2 - y1), net = !!SCHEME_NETSET[s.shape], f = Math.max(11, Math.min(bh * .3, W / 70)) * (net ? 1 : 1);
            const lk = s.dev ? realByDev[s.dev] : null, lbl = s.label || (lk ? lk.name : '');
            el = <><SchemeNodeArt shape={s.shape} x={bx} y={by} w={bw} h={bh} stroke={stroke} sw={sw} dash={dash} on={on} />
              {s.dev ? (() => { const dx = bx + bw - Math.min(bw, bh) * .08, dy = by + Math.min(bw, bh) * .08, dr = Math.max(4, Math.min(bw, bh) * .11), col = schemeLed(lk && lk.status), cls = 'scheme-led ' + (lk && lk.status === 'offline' ? 'st-offline' : 'st-online');
                return !col ? null : <g className={cls} style={{ color: col }}><circle className="scheme-led-ring" cx={dx} cy={dy} r={dr} fill={col} /><circle className="scheme-led-dot" cx={dx} cy={dy} r={dr} fill={col} stroke="var(--bg2)" strokeWidth={Math.max(1.5, Math.min(bw, bh) * .03)} /></g>; })() : null}
              {lbl ? <text x={bx + bw / 2} y={net ? by + bh + f * 1.15 : by + bh / 2} dy={net ? 0 : '.34em'} textAnchor="middle" fontSize={f} fontWeight="600" fill="var(--text)" stroke="var(--bg2)" strokeWidth={f / 6} paintOrder="stroke" strokeLinejoin="round">{lbl}</text> : null}</>;
          } else if (s.kind === 'text') {
            const r = schemeTextBox(s, W, H);
            el = <><rect x={r.x} y={r.y} width={r.w} height={r.h} fill="transparent" stroke={on ? stroke : 'none'} strokeDasharray="4 3" strokeWidth={1.2 / tv.k} rx={4} />
              <text x={s.x1 * W} y={s.y1 * H} fontSize={r.f} fontWeight="600" fill={stroke} stroke="var(--bg2)" strokeWidth={r.f / 7} paintOrder="stroke" strokeLinejoin="round">{s.label}</text></>;
          } else if (s.kind === 'rect') {
            el = <rect x={Math.min(x1, x2)} y={Math.min(y1, y2)} width={Math.abs(x2 - x1)} height={Math.abs(y2 - y1)} fill={stroke} fillOpacity={on ? .18 : .1} stroke={stroke} strokeWidth={sw} strokeDasharray={dash} />;
          } else {
            const pts = schemeLinePts(s, W, H), n = pts.length, ar = Number(s.arrow) | 0;
            const poly = pts.map(q => q.join(',')).join(' ');
            const dash2 = s.anim ? (dash || `${sw * 3} ${sw * 2.2}`) : dash, cls = s.anim ? 'scheme-flow' : undefined;
            hit = <polyline points={poly} fill="none" stroke="transparent" strokeWidth={18 / tv.k} strokeLinecap="round" strokeLinejoin="round" />;
            el = <>{s.closed && n > 2
              ? <polygon points={poly} fill={stroke} fillOpacity={on ? .2 : .1} stroke={stroke} strokeWidth={sw} strokeLinejoin="round" strokeDasharray={dash2} className={cls} />
              : <polyline points={poly} fill="none" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={dash2} className={cls} />}
              {s.kind === 'wire' && !s.closed && ar < 2 ? <circle cx={pts[0][0]} cy={pts[0][1]} r={sw * 1.8} fill={stroke} /> : null}
              {ar === 2 && !s.closed ? <polygon points={schemeArrowHead(pts[1][0], pts[1][1], pts[0][0], pts[0][1], sw * 5.5)} fill={stroke} /> : null}
              {s.closed ? null : ar ? <polygon points={schemeArrowHead(pts[n - 2][0], pts[n - 2][1], pts[n - 1][0], pts[n - 1][1], sw * 5.5)} fill={stroke} />
                : s.kind === 'wire' ? <circle cx={pts[n - 1][0]} cy={pts[n - 1][1]} r={sw * 1.8} fill={stroke} /> : null}</>;
          }
          const rc = s.rot ? schemeBoxCenter(s, W, H) : null;
          return <g key={s.id} transform={rc ? `rotate(${s.rot} ${rc.x} ${rc.y})` : undefined} onPointerDown={interactive ? (e => startDrag(e, s, 'move')) : undefined} style={{ cursor: interactive ? 'move' : 'default', pointerEvents: interactive ? 'auto' : 'none' }}>
            {hit}{el}
            {s.label && s.kind !== 'text' && s.kind !== 'node' ? <g transform={`translate(${mid.x},${mid.y})`}><rect x={-4} y={-11} width={Math.max(20, s.label.length * 6.6 * (W / 1200) + 8)} height={16 * (W / 1200) || 16} rx={6} fill="var(--card-solid, #1c1c1e)" opacity=".86" />
              <text x={0} y={2} fontSize={Math.max(11, W / 100)} fill="var(--text)" textAnchor="start">{s.label}</text></g> : null}
          </g>;
        })}
        {guides ? <g pointerEvents="none">
          {guides.lines.map((l, i) => <line key={'gl' + i} x1={l[0].x} y1={l[0].y} x2={l[1].x} y2={l[1].y} stroke="var(--text3)" strokeWidth={1 / tv.k} strokeDasharray={`${5 / tv.k} ${4 / tv.k}`} />)}
          {guides.marks.map((l, i) => { const horiz = Math.abs(l[0].y - l[1].y) < Math.abs(l[0].x - l[1].x), t = 5 / tv.k;
            return <g key={'gm' + i} stroke="var(--text2)" strokeWidth={1.4 / tv.k}><line x1={l[0].x} y1={l[0].y} x2={l[1].x} y2={l[1].y} />
              {horiz ? <><line x1={l[0].x} y1={l[0].y - t} x2={l[0].x} y2={l[0].y + t} /><line x1={l[1].x} y1={l[1].y - t} x2={l[1].x} y2={l[1].y + t} /></>
                : <><line x1={l[0].x - t} y1={l[0].y} x2={l[0].x + t} y2={l[0].y} /><line x1={l[1].x - t} y1={l[1].y} x2={l[1].x + t} y2={l[1].y} /></>}</g>; })}
        </g> : null}
        {handles.map(([m, hx, hy, tp]) => <g key={m}>{tp ? <line x1={tp.x} y1={tp.y} x2={hx} y2={hy} stroke="var(--accent)" strokeWidth={1.8 / tv.k} /> : null}
          {m === 'move'
            ? <g transform={`translate(${hx},${hy}) scale(${hr * 1.7 / 12})`} style={{ cursor: 'move' }} onPointerDown={e => startDrag(e, selShape, 'move')}><circle r="12" fill="var(--accent)" fillOpacity=".92" stroke="#fff" strokeWidth="1.5" /><g transform="translate(-8,-8) scale(.667)" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{SCHEME_IC.grip.props.d.split('M').filter(Boolean).map((d, i) => <path key={i} d={'M' + d} />)}</g></g>
            : <circle cx={hx} cy={hy} r={hr} fill={m === 'rot' ? 'var(--accent)' : 'var(--card-solid, #fff)'} stroke="var(--accent)" strokeWidth={2.5 / tv.k} style={{ cursor: 'grab' }} onPointerDown={e => startDrag(e, selShape, m)} />}</g>)}
        {draft ? (draft.kind === 'rect'
          ? <rect x={Math.min(draft.x1, draft.x2)} y={Math.min(draft.y1, draft.y2)} width={Math.abs(draft.x2 - draft.x1)} height={Math.abs(draft.y2 - draft.y1)} fill={SCHEME_COLOR_VAR[color]} fillOpacity=".15" stroke={SCHEME_COLOR_VAR[color]} strokeDasharray="6 4" strokeWidth={2} />
          : <line x1={draft.x1} y1={draft.y1} x2={draft.x2} y2={draft.y2} stroke={SCHEME_COLOR_VAR[color]} strokeDasharray="6 4" strokeWidth={2} />) : null}
        {polyPts.length ? <g pointerEvents="none"><polyline points={polyPts.map(q => q.x + ',' + q.y).join(' ')} fill="none" stroke={SCHEME_COLOR_VAR[color]} strokeWidth={sw0} strokeDasharray={`${sw0 * 3} ${sw0 * 2}`} strokeLinejoin="round" />{polyPts.map((q, i) => <circle key={i} cx={q.x} cy={q.y} r={sw0 * 2.2} fill={SCHEME_COLOR_VAR[color]} />)}</g> : null}
        {linkA && shapesV.find(x => x.id === linkA) ? (() => { const n = shapesV.find(x => x.id === linkA); return <rect pointerEvents="none" x={Math.min(n.x1, n.x2) * W - 6} y={Math.min(n.y1, n.y2) * H - 6} width={Math.abs(n.x2 - n.x1) * W + 12} height={Math.abs(n.y2 - n.y1) * H + 12} rx={10} fill="none" stroke="var(--accent)" strokeWidth={2.5 / tv.k} strokeDasharray="6 4" />; })() : null}
        {wireA ? <g pointerEvents="none"><circle cx={wireA.x} cy={wireA.y} r={sw0 * 5} fill={SCHEME_COLOR_VAR[color]} fillOpacity=".25" /><circle cx={wireA.x} cy={wireA.y} r={sw0 * 2.2} fill={SCHEME_COLOR_VAR[color]} />
          <text x={wireA.x + sw0 * 6} y={wireA.y - sw0 * 4} fontSize={Math.max(12, W / 80)} fontWeight="700" fill="var(--text)">А</text></g> : null}
      </g>
    </svg>
    <ZoomBtns setView={setView} onFit={() => fitView(wrap.current, [0, W], [0, H], setView)} />
    {dock}
  </div>;
}
