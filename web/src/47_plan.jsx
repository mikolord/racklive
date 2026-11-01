/* Floor plan: territory (buildings + backbone) → a building's floors (walls, rooms, equipment) */
const PG = 20;
const uid = p => p + Math.random().toString(36).slice(2, 7);
const snap = v => Math.round(v / PG) * PG;
const clampK = k => Math.min(6, Math.max(.08, k));
const planRoomsOverlap = (a,b) => a.x < b.x+b.w && a.x+a.w > b.x && a.y < b.y+b.h && a.y+a.h > b.y;

// The network map also contains discovered APs, clients and units without a poller.
function planNetworkDevices(data) {
  const devices = new Map((data.devices || []).map(d => [d.id, d]));
  (data.topology?.nodes || []).forEach(n => {
    if (n.deviceId || n.kind === 'internet' || n.kind === 'group' || n.id.startsWith('x:')) return;
    devices.set(n.id, { id: n.id, name: n.label || n.id, kind: n.kind || 'other', host: n.sub || '', mac: n.mac || '',
      state: { status: n.status || 'unknown' }, _topology: true, _node: n });
  });
  (data.plan?.buildings || []).forEach(b => (b.floors || []).forEach(f => (f.items || []).forEach(it => {
    if (it.kind === 'device' && it.deviceSnapshot && !devices.has(it.ref)) devices.set(it.ref, { ...it.deviceSnapshot, id: it.ref, state: { status: 'unknown' }, _topology: true });
  })));
  return [...devices.values()];
}

function placeStatus(rack, devById) {
  const s = (rack.units || []).flatMap(u => unitDevIds(u)).map(id => devById[id] && devById[id].state && devById[id].state.status).filter(Boolean);
  return s.includes('offline') ? 'offline' : s.includes('warning') ? 'warning' : s.length ? 'online' : '';
}
function floorDevices(f, data, devById) {
  const out = [];
  (f.items || []).forEach(it => {
    if (it.kind === 'device' && devById[it.ref]) out.push(devById[it.ref]);
    if (it.kind === 'place') { const r = data.racks.find(x => x.id === it.ref); (r ? r.units : []).forEach(u => unitDevIds(u).forEach(id => devById[id] && out.push(devById[id]))); }
  });
  return out;
}
function worst(devs) { const s = devs.map(d => d.state && d.state.status).filter(Boolean);
  return s.includes('offline') ? 'offline' : s.includes('warning') ? 'warning' : s.length ? 'online' : ''; }
const statusColor = s => s === 'online' ? 'var(--green)' : s === 'warning' ? 'var(--orange)' : s === 'offline' ? 'var(--red)' : 'var(--text3)';
const ISO_A = .72, ISO_B = .38, ISO_C = -.72, ISO_D = .38, ISO_FLOOR = 330, ISO_WALL = 145, ISO_SLAB = 18;
const isoPoint = (x, y) => ({ x: ISO_A * x + ISO_C * y, y: ISO_B * x + ISO_D * y });
const isoPoly = pts => pts.map(p => { const q = isoPoint(p[0], p[1]); return `${q.x},${q.y}`; }).join(' ');
function planBounds(floors) {
  const xs = [], ys = [];
  (floors || []).forEach(f => {
    (f.walls || []).forEach(w => { xs.push(w.x1, w.x2); ys.push(w.y1, w.y2); });
    (f.rooms || []).forEach(r => { xs.push(r.x, r.x + r.w); ys.push(r.y, r.y + r.h); });
    (f.items || []).forEach(i => { xs.push(i.x - 30, i.x + 30); ys.push(i.y - 30, i.y + 30); });
  });
  if (!xs.length) return { x1: -360, y1: -260, x2: 360, y2: 260 };
  const pad = 180;
  return { x1: Math.min(...xs) - pad, y1: Math.min(...ys) - pad, x2: Math.max(...xs) + pad, y2: Math.max(...ys) + pad };
}
function planStructureBounds(floors) {
  const xs = [], ys = [];
  (floors || []).forEach(f => {
    (f.walls || []).forEach(w => { xs.push(w.x1, w.x2); ys.push(w.y1, w.y2); });
    (f.rooms || []).forEach(r => { xs.push(r.x, r.x + r.w); ys.push(r.y, r.y + r.h); });
  });
  if (!xs.length) return { x1: -300, y1: -220, x2: 300, y2: 220 };
  const pad = 24;
  return { x1: Math.min(...xs) - pad, y1: Math.min(...ys) - pad, x2: Math.max(...xs) + pad, y2: Math.max(...ys) + pad };
}
function planFloorFrame(floor, fallback) {
  const b = floor && floor.frame;
  return b && [b.x1, b.y1, b.x2, b.y2].every(Number.isFinite) && b.x2 > b.x1 && b.y2 > b.y1 ? b : fallback;
}
function outsideFloorPoint(p, floor) {
  const rooms = floor.rooms || [];
  if (rooms.length) return !rooms.some(r => p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h);
  const walls = floor.walls || [];
  if (!walls.length) return false;
  const xs = walls.flatMap(w => [w.x1, w.x2]), ys = walls.flatMap(w => [w.y1, w.y2]);
  return p.x < Math.min(...xs) || p.x > Math.max(...xs) || p.y < Math.min(...ys) || p.y > Math.max(...ys);
}
function segDist(p, s) {                                     // distance from point to a wall segment
  const dx = s.x2 - s.x1, dy = s.y2 - s.y1, l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p.x - s.x1) * dx + (p.y - s.y1) * dy) / l2)) : 0;
  return Math.hypot(p.x - (s.x1 + t * dx), p.y - (s.y1 + t * dy));
}

/* snap marker + wall draft, so the pointer is visible on any background */
function PlanCursor({ wrap, view, tool, wallPt, planeRef }) {
  const [c, setC] = useState(null);
  useEffect(() => { const el = wrap.current; if (!el) return;
    const h = e => { const plane = planeRef && planeRef.current, m = plane && plane.getScreenCTM();
      if (m) { const pt = el.querySelector('svg').createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY; const q = pt.matrixTransform(m.inverse()); setC({ x: snap(q.x), y: snap(q.y) }); }
      else { const r = el.getBoundingClientRect(); setC({ x: snap((e.clientX - r.left - view.x) / view.k), y: snap((e.clientY - r.top - view.y) / view.k) }); } };
    const leave = () => setC(null);
    el.addEventListener('pointermove', h); el.addEventListener('pointerleave', leave);
    return () => { el.removeEventListener('pointermove', h); el.removeEventListener('pointerleave', leave); }; }, [view, wrap]);
  if (!c || tool === 'select') return null;
  return <g pointerEvents="none">
    {wallPt && tool === 'wall' ? <line className="plan-wall draft" x1={wallPt.x} y1={wallPt.y} x2={c.x} y2={c.y} /> : null}
    <circle cx={c.x} cy={c.y} r={6} className="plan-cursor" />
    <line className="plan-cursor-x" x1={c.x - 13} y1={c.y} x2={c.x + 13} y2={c.y} />
    <line className="plan-cursor-x" x1={c.x} y1={c.y - 13} x2={c.x} y2={c.y + 13} /></g>;
}

/* a smooth change of a set of numbers: when `target` changes, the returned values glide to it (ease in-out) instead of jumping — floors sliding apart, fading in and out, walls growing */
const planEase = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const planReduceMotion = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
function useTween(target, ms = 520) {
  const [val, setVal] = useState(target);
  const cur = useRef(target), raf = useRef(0), key = JSON.stringify(target);
  useEffect(() => {
    const to = target, from = { ...cur.current };
    cancelAnimationFrame(raf.current);
    if (planReduceMotion() || !ms) { cur.current = to; setVal(to); return; }
    const t0 = performance.now();
    const step = now => {
      const p = Math.min(1, (now - t0) / ms), e = planEase(p), next = {};
      for (const k in to) next[k] = p >= 1 || !(k in from) ? to[k] : from[k] + (to[k] - from[k]) * e;
      cur.current = next; setVal(next);
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [key]);
  return val;
}

/* pan + wheel + pinch, with tap / drag-draw callbacks (opts read fresh each render) */
function usePanZoom(wrapRef, opts, initial) {
  useFillScreen(wrapRef);
  const [view, setView] = useState(initial || { x: 60, y: 60, k: 1 });
  const vr = useRef(view); vr.current = view;
  const or = useRef(opts); or.current = opts;
  const ptrs = useRef({}); const mode = useRef(null);
  const toWorld = (cx, cy) => {
    if (or.current.mapPoint) { const p = or.current.mapPoint(cx, cy); if (p) return p; }
    const r = wrapRef.current.getBoundingClientRect(); return { x: (cx - r.left - vr.current.x) / vr.current.k, y: (cy - r.top - vr.current.y) / vr.current.k };
  };
  const wheel = e => { e.preventDefault(); const r = wrapRef.current.getBoundingClientRect(); const mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = clampK(vr.current.k * Math.exp(-e.deltaY * .0015)); setView(v => ({ k, x: mx - (mx - v.x) * k / v.k, y: my - (my - v.y) * k / v.k })); };
  useEffect(() => { const el = wrapRef.current; if (!el) return; el.addEventListener('wheel', wheel, { passive: false }); return () => el.removeEventListener('wheel', wheel); }, []);
  const pinchBase = () => { const p = Object.values(ptrs.current); const r = wrapRef.current.getBoundingClientRect();
    return { pinch: true, dist: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1, cx: (p[0].x + p[1].x) / 2 - r.left, cy: (p[0].y + p[1].y) / 2 - r.top, v: { ...vr.current } }; };
  const down = e => {
    // items handle their own drag; buttons/overlays must get their click (pointer capture would steal it)
    if (e.target.closest('button, .zoom-btns, .plan-hint, .plan-open, .plan-ovl, .plan-open-g, .live-bar')) return;
    const itemTarget = e.target.closest('.plan-item, .plan-room');
    if (itemTarget && e.pointerType !== 'touch' && !(or.current.panItems && or.current.panItems()) && !(or.current.allowCanvasOnItems && or.current.allowCanvasOnItems())) return;
    ptrs.current[e.pointerId] = { x: e.clientX, y: e.clientY, target: e.target };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}
    if (Object.keys(ptrs.current).length >= 2) { mode.current = pinchBase(); return; }
    mode.current = { pinch: false, sx: e.clientX, sy: e.clientY, lx: e.clientX, ly: e.clientY, vx: vr.current.x, vy: vr.current.y, moved: false, w0: toWorld(e.clientX, e.clientY), drawing: false, target: e.target };
  };
  const move = e => {
    if (!ptrs.current[e.pointerId]) return; ptrs.current[e.pointerId] = { ...ptrs.current[e.pointerId], x: e.clientX, y: e.clientY };
    const pts = Object.values(ptrs.current); const m = mode.current; if (!m) return;
    if (m.pinch && pts.length >= 2) { e.preventDefault(); const r = wrapRef.current.getBoundingClientRect();
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y); const cx = (pts[0].x + pts[1].x) / 2 - r.left, cy = (pts[0].y + pts[1].y) / 2 - r.top;
      const k = clampK(m.v.k * dist / m.dist); setView({ k, x: cx - (m.cx - m.v.x) * k / m.v.k, y: cy - (m.cy - m.v.y) * k / m.v.k }); return; }
    if (m.pinch) return;
    const dx = e.clientX - m.sx, dy = e.clientY - m.sy; if (Math.abs(dx) + Math.abs(dy) > 5) m.moved = true;
    const o = or.current;
    if (o.onDraw && m.moved) { if (!m.drawing) { m.drawing = true; } o.onDraw(m.w0, toWorld(e.clientX, e.clientY), false); e.preventDefault(); return; }
    if (o.canPan && o.canPan() && m.moved) { e.preventDefault(); setView(v => ({ ...v, x: m.vx + dx, y: m.vy + dy })); }
  };
  const up = e => {
    if (!ptrs.current[e.pointerId]) return;
    const m = mode.current; delete ptrs.current[e.pointerId];
    const left = Object.keys(ptrs.current).length;
    if (left === 0) { const o = or.current; mode.current = null;
      if (m && !m.pinch) { if (m.drawing && o.onDraw) o.onDraw(m.w0, toWorld(e.clientX, e.clientY), true); else if (!m.moved && o.onTap) o.onTap(m.w0, m.target); }
      mode.current = null;
    } else if (left === 1) { const p = Object.values(ptrs.current)[0]; mode.current = { pinch: false, sx: p.x, sy: p.y, vx: vr.current.x, vy: vr.current.y, moved: true, target: p.target }; }
  };
  const cancel = () => { ptrs.current = {}; mode.current = null; if (or.current.onCancel) or.current.onCancel(); };
  return { view, setView, toWorld, bind: { onPointerDown: down, onPointerMove: move, onPointerUp: up, onPointerCancel: cancel } };
}

function ZoomBtns({ setView, onFit }) {
  const zoom = (factor,e) => { const el = e.currentTarget.closest('.plan-canvas'), x = (el?.clientWidth || 0)/2, y = (el?.clientHeight || 0)/2;
    setView(v => { const k = clampK(v.k*factor); return { k, x: x-(x-v.x)*k/v.k, y: y-(y-v.y)*k/v.k }; }); };
  return <div className="zoom-btns">
    {onFit ? <button className="btn" onClick={onFit} title="Показать всё"><Icon name="fit" size={17} /></button> : null}
    <button className="btn" aria-label="Увеличить" onClick={e => zoom(1.3,e)}>+</button>
    <button className="btn" aria-label="Уменьшить" onClick={e => zoom(1/1.3,e)}>−</button></div>;
}
/* fit a set of world points into the canvas (used on open and by the «показать всё» button) */
function fitView(el, xs, ys, setView, pad = 40) {
  if (!el) return; const W = el.clientWidth, H = el.clientHeight;
  if (!xs.length) { setView({ x: W / 2, y: H / 2, k: 1 }); return; }
  const x1 = Math.min(...xs) - pad, y1 = Math.min(...ys) - pad, x2 = Math.max(...xs) + pad, y2 = Math.max(...ys) + pad;
  const k = clampK(Math.min(1.2, Math.min(W / (x2 - x1), H / (y2 - y1))));
  setView({ k, x: (W - (x2 - x1) * k) / 2 - x1 * k, y: (H - (y2 - y1) * k) / 2 - y1 * k });
}

function PlanStandalone() {
  const { data } = useApp();
  return <div className="plan-standalone">
    <header className="topbar plan-app-header"><div className="plan-app-brand"><AppIcon app="plan" size={32}/><div><b>План</b><small className="ellipsis">{data.settings.title}</small></div></div><div className="grow"/>
    </header>
    <main className="page page-full"><PlanView/></main>
  </div>;
}
function PlanView() {
  const { data, edit } = useApp();
  const plan = data.plan || { buildings: [], links: [] };
  const buildings = plan.buildings || [];
  const deep = new URLSearchParams(location.search).get('building');
  const [level, setLevel] = useState(deep && buildings.find(b => b.id === deep) ? 'building' : 'territory');
  const [bid, setBid] = useState((deep && buildings.find(b => b.id === deep) && deep) || (buildings[0] && buildings[0].id));
  useEffect(() => { if (level === 'building' && !buildings.find(x => x.id === bid)) setLevel('territory'); }, [buildings.length]);

  const { pinTest, setPinTest } = useApp();
  const banner = pinTest ? <div className="pin-banner"><Icon name="pin" size={17} />
    <span className="grow">{level === 'building' ? 'Нажмите на план там, где вы делали замер' : 'Выберите дом, затем нажмите место замера на плане'}</span>
    <Btn size="sm" onClick={() => setPinTest(null)}>Отмена</Btn></div> : null;
  if (!buildings.length) return <>{banner}<Territory plan={plan} enter={() => {}} net={() => {}} /></>;      // тот же вид разметки, что ниже: когда появится первый дом, карта не перезапускается
  const goNet = id => { setBid(id); setLevel('net'); };
  if (level === 'building') { const b = buildings.find(x => x.id === bid) || buildings[0];
    return <>{banner}<BuildingPlan key={b.id} building={b} plan={plan} back={() => setLevel('territory')} net={() => goNet(b.id)} /></>; }
  if (level === 'net') { const b = buildings.find(x => x.id === bid) || buildings[0];
    return <MapView scope={houseScope(b, data, () => setLevel('territory'), () => { setBid(b.id); setLevel('building'); })} />; }
  return <>{banner}<Territory plan={plan} enter={id => { setBid(id); setLevel('building'); }} net={goNet} /></>;
}
/* «Сеть дома»: что в доме стоит (устройства и шкафы с его этажей) — карта сети сузится до этого (см. scopeData в 40_map.jsx) */
function houseScope(b, data, back, openHouse) {
  const devices = new Set(), racks = new Set();
  (b.floors || []).forEach(f => (f.items || []).forEach(it => { if (it.kind === 'device') devices.add(it.ref); else if (it.kind === 'place') racks.add(it.ref); }));
  return { seed: { devices, racks }, key: b.id + ':' + [...devices].sort().join(',') + '|' + [...racks].sort().join(','), title: b.name, back, backLabel: 'К плану', openHouse };
}

/* Only the measured hull is coloured; pins remain available with one or two samples. */
function CoverageSurface({ mesh, metric }) {
  const image=useMemo(()=>coverageRaster(mesh,metric),[mesh,metric]);
  return image ? <image className="coverage-heatmap" x={image.x} y={image.y} width={image.w} height={image.h} href={image.url} pointerEvents="none" /> : null;
}
function CoverageLayer({ tests, mesh, metric, sel, onSel, placing, view, projection, markerScale = .3 }) {
  const scale=coverageScale(mesh,metric), {a,b,c,d}=projection, det=a*d-b*c;
  const screenMatrix=`matrix(${d/det/view.k} ${-b/det/view.k} ${-c/det/view.k} ${a/det/view.k} 0 0)`;
  const marker=Math.max(.2,Math.min(1,markerScale))/.3;
  return <g className="coverage" data-metric={metric}>
    {tests.map(t => { const value=coverageValue(t,metric), color='rgb('+coverageColor(value,scale).join(',')+')';
      const label=metric==='signal' ? (value==null ? '—' : Math.round(value)+' дБм') : mbpsText(value);
      return <g key={t.id} className={'cov-pin' + (sel === t.id ? ' sel' : '')} transform={`translate(${t.where.x},${t.where.y})`}
        onPointerDown={e => { if (!placing) { e.stopPropagation(); onSel(sel === t.id ? null : t.id); } }}>
        <title>{coverageGroupLabel(t)} · {metric==='signal' ? (value==null ? 'Свежий уровень сигнала недоступен' : label) : label+' Мбит/с'}</title>
        <g transform={screenMatrix}>
          <rect className="cov-hit" x={-(Math.max(40,(Math.max(40,label.length*6.5+16)*marker))/2)-5} y={-Math.max(20,20*marker)} width={Math.max(40,Math.max(40,label.length*6.5+16)*marker)+10} height={Math.max(40,40*marker)} rx={13} />
          <rect x={-(Math.max(40,label.length*6.5+16)*marker)/2} y={-11*marker} width={Math.max(40,label.length*6.5+16)*marker} height={22*marker} rx={8*marker} fill={color} />
          <text y={4*marker} textAnchor="middle" className="cov-txt" style={{fontSize:11*marker}}>{label}</text>
        </g>
      </g>; })}
  </g>;
}

/* ───────── territory: buildings + backbone links ───────── */
const BW = 240, BH = 150;
function Territory({ plan, enter, net }) {
  const { data, edit, savePlan, openDevice, openPlace, setTab } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const buildings = plan.buildings || []; const links = plan.links || []; const poles = plan.poles || []; const nodes = plan.nodes || [];
  const devById = Object.fromEntries(planNetworkDevices(data).map(d => [d.id, d]));
  const wrap = useRef(null);
  const [tool, setTool] = useState('select');               // select | link | pole | outline | bg
  const [linkFrom, setLinkFrom] = useState(null);
  const [sel, setSel] = useState(null);
  const [draft, setDraft] = useState([]);                    // «Обвести»: углы, поставленные до сих пор
  const [selV, setSelV] = useState(null);                    // выбранный угол выбранного дома (его можно убрать)
  const [live, setLive] = useState(null);                    // дом, который тащат (контур целиком или один угол): сохраняется один раз, когда отпустили
  const [bgOpen, setBgOpen] = useState(false);
  const [bgLive, setBgLive] = useState(null);                // фон, который тащат
  const bgDrag = useRef(null);
  const [nodeBind, setNodeBind] = useState(null);              // узел, к которому подбирают шкаф или устройство
  const [pickLink, setPickLink] = useState(null);               // 3D: первая точка магистрали (дом, столб или узел)
  const [styleFor, setStyleFor] = useState(null);                // дом, у которого открыто окно «Цвета и высота» (плоский вид)
  const [bgMove, setBgMove] = useState(null);              // какой фон тащит инструмент «Фон»
  const bgs = (plan.bgs || []).map(b => bgLive && bgLive.id === b.id ? { ...b, x: bgLive.x, y: bgLive.y } : b).sort((a, b) => b.w - a.w);     // большие внизу, подробные поверх
  const moving = (plan.bgs || []).find(b => b.id === bgMove) || (plan.bgs || [])[0];
  const geo = geoRef(plan.bgs, plan.geo);                          // фон с координатами: по нему знаем, где на земле дома
  const save = (b, l, p, n) => savePlan({ ...plan, buildings: b || buildings, links: l || links, poles: p || poles, nodes: n || nodes });
  const isOut = b => Array.isArray(b.outline) && b.outline.length >= 3;
  const outlineOf = b => live && live.id === b.id ? live.outline : b.outline;
  const pos = b => ({ x: typeof b.x === 'number' ? b.x : 40 + (buildings.indexOf(b) % 3) * (BW + 80), y: typeof b.y === 'number' ? b.y : 40 + Math.floor(buildings.indexOf(b) / 3) * (BH + 120) });
  const boxOf = b => { if (isOut(b)) { const q = polyBox(outlineOf(b)); return { x: q.x0, y: q.y0, w: q.x1 - q.x0, h: q.y1 - q.y0 }; } const p = pos(b); return { x: p.x, y: p.y, w: BW, h: BH }; };
  const nodeName = id => (buildings.find(x => x.id === id) || poles.find(x => x.id === id) || nodes.find(x => x.id === id) || {}).name || '';
  const [linkEdit, setLinkEdit] = useState(null);             // {link, isNew}
  const pickNode = id => {                                    // link tool: building or pole, two taps
    if (!linkFrom) { setLinkFrom(id); toast('Теперь выберите второй дом или столб'); return; }
    if (linkFrom === id) { setLinkFrom(null); return; }
    setLinkEdit({ link: { id: uid('l'), from: linkFrom, to: id, label: '' }, isNew: true });
    setLinkFrom(null);
  };
  const saveLink = l => save(null, linkEdit.isNew ? [...links, l] : links.map(x => x.id === l.id ? l : x));
  const hit = w => [...buildings].reverse().find(x => { if (isOut(x)) return inPoly(w, x.outline); const p = pos(x); return w.x >= p.x && w.x <= p.x + BW && w.y >= p.y && w.y <= p.y + BH; });

  /* «Обвести»: нажимайте по углам дома; замкнуть — нажать на первый угол или «Готово» */
  const finishOutline = () => {
    if (draft.length < 3) { toast('Нужно хотя бы три угла', true); return; }
    const id = uid('b'), n = buildings.length, b0 = polyBox(draft);
    const name = ((typeof prompt === 'function' ? prompt('Название дома', `Дом ${n + 1}`) : '') || '').trim() || `Дом ${n + 1}`;
    save([...buildings, { id, name, x: b0.x0, y: b0.y0, outline: draft, floors: [{ id: uid('f'), name: '1 этаж', walls: [], rooms: [], items: [] }] }]);
    setDraft([]); setSel(id); setTool('select');
  };
  const addCorner = w => {
    const p = [snapO(w.x), snapO(w.y)];
    if (draft.length >= 3 && Math.hypot(p[0] - draft[0][0], p[1] - draft[0][1]) <= 16 / view.k) { finishOutline(); return; }
    const last = draft[draft.length - 1];
    if (last && last[0] === p[0] && last[1] === p[1]) return;
    if (draft.length >= 120) { toast('Достаточно углов — нажмите «Готово»', true); return; }
    setDraft([...draft, p]);
  };
  const onTap = w => {
    if (edit && tool === 'outline') { addCorner(w); return; }
    if (tool === 'pole') { save(null, null, [...poles, { id: uid('p'), name: `Столб ${poles.length + 1}`, x: snap(w.x), y: snap(w.y) }]); return; }
    if (!edit) {                                               // viewing: 1st tap selects a house, 2nd tap (or «Открыть») goes inside
      const b = hit(w);
      if (b && sel === b.id) { enter(b.id); return; }
      setSel(b ? b.id : null); return;
    }
    setSel(null); setSelV(null);
  };
  /* фон: тащить пальцем / мышью (инструмент «Фон») */
  const onBgDraw = (w0, w1, fin) => {
    if (!moving) return;
    if (!bgDrag.current) bgDrag.current = { x: moving.x, y: moving.y };
    const nx = Math.round(bgDrag.current.x + w1.x - w0.x), ny = Math.round(bgDrag.current.y + w1.y - w0.y);
    if (fin) { savePlan({ ...plan, bgs: (plan.bgs || []).map(b => b.id === moving.id ? { ...b, x: nx, y: ny } : b) }); setBgLive(null); bgDrag.current = null; } else setBgLive({ id: moving.id, x: nx, y: ny });
  };
  // viewing: a swipe that starts on a house pans the plan instead of opening it
  const { view, setView, bind } = usePanZoom(wrap, { canPan: () => tool === 'select' || tool === 'outline', onTap, panItems: () => !edit || tool === 'outline' || tool === 'bg',
    onDraw: edit && tool === 'bg' && moving ? onBgDraw : null });
  // open centred on all buildings, poles and their yards — not on an empty corner of the grid
  const fitAll = () => { const xs = [], ys = [];
    buildings.forEach(b => { const q = boxOf(b); xs.push(q.x - 18, q.x + q.w + 18); ys.push(q.y - 18, q.y + q.h + 18); });
    poles.forEach(p => { xs.push(p.x - 20, p.x + 20); ys.push(p.y - 20, p.y + 34); });
    if (!xs.length && bgs.length) { const s = [...bgs].sort((a, b) => a.w - b.w)[0]; xs.push(s.x, s.x + s.w); ys.push(s.y, s.y + s.h); }          // без домов — на самый подробный фон
    fitView(wrap.current, xs, ys, setView); };
  useEffect(() => { const t = setTimeout(fitAll, 30); return () => clearTimeout(t); }, [buildings.length, poles.length, bgs.map(b => b.id).join()]);
  const delPole = async id => { const p = poles.find(x => x.id === id);
    if (!(await confirm(`Удалить «${p.name}» и его магистрали?`, { danger: true, ok: 'Удалить' }))) return;
    save(null, links.filter(l => l.from !== id && l.to !== id), poles.filter(x => x.id !== id)); setSel(null); };
  const dragPole = (p, e) => {
    if (tool === 'link') { pickNode(p.id); return; }
    if (!edit || tool !== 'select') return;
    e.stopPropagation(); const sx = e.clientX, sy = e.clientY; let moved = false;
    const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 5) moved = true; if (moved) {
      const nx = snap(p.x + (ev.clientX - sx) / view.k), ny = snap(p.y + (ev.clientY - sy) / view.k);
      savePlan({ ...plan, poles: poles.map(x => x.id === p.id ? { ...x, x: nx, y: ny } : x) }); } };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) setSel(p.id); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };

  const addBuilding = () => { const id = uid('b'); const n = buildings.length;
    save([...buildings, { id, name: `Дом ${n + 1}`, x: 40 + (n % 3) * (BW + 80), y: 40 + Math.floor(n / 3) * (BH + 120),
      floors: [{ id: uid('f'), name: '1 этаж', walls: [], rooms: [], items: [] }] }]); };
  const delBuilding = async id => { const b = buildings.find(x => x.id === id);
    if (!(await confirm(`Удалить дом «${b.name}» со всеми этажами? Оборудование и шкафы останутся — удалится только их размещение на плане.`, { danger: true, ok: 'Удалить дом' }))) return;
    save(buildings.filter(x => x.id !== id), links.filter(l => l.from !== id && l.to !== id)); setSel(null); setSelV(null); };
  const dragB = (b, e) => {
    if (tool === 'link') { pickNode(b.id); return; }
    if (tool === 'pole' || tool === 'outline' || tool === 'bg') return;
    if (!edit) return;                                         // handled by the pan/tap hook (onTap)
    e.stopPropagation(); const p = pos(b);
    const sx = e.clientX, sy = e.clientY; let moved = false;
    if (isOut(b)) {                                            // контур: тащим целиком, сохраняем один раз — когда отпустили
      const o0 = b.outline; let cur = null;
      const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 5) moved = true; if (moved) {
        const dx = snapO((ev.clientX - sx) / view.k), dy = snapO((ev.clientY - sy) / view.k);
        cur = { id: b.id, outline: o0.map(([x, y]) => [x + dx, y + dy]) }; setLive(cur); } };
      const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
        if (moved && cur) { const q = polyBox(cur.outline); save(buildings.map(x => x.id === b.id ? { ...x, outline: cur.outline, x: q.x0, y: q.y0 } : x)); }
        setLive(null); if (!moved) { setSel(b.id); setSelV(null); } };
      window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
      return;
    }
    const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 5) moved = true; if (moved) {
      const nx = snap(p.x + (ev.clientX - sx) / view.k), ny = snap(p.y + (ev.clientY - sy) / view.k);
      savePlan({ ...plan, buildings: buildings.map(x => x.id === b.id ? { ...x, x: nx, y: ny } : x) }); } };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) { setSel(b.id); } };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  /* углы выбранного контура: потянуть — подвинуть, нажать — выбрать (тогда можно убрать), «+» на середине стороны — добавить угол */
  const setOutline = (b, o) => save(buildings.map(x => x.id === b.id ? { ...x, outline: o, x: polyBox(o).x0, y: polyBox(o).y0 } : x));
  const worldOf = ev => { const r = wrap.current.getBoundingClientRect(); return { x: (ev.clientX - r.left - view.x) / view.k, y: (ev.clientY - r.top - view.y) / view.k }; };
  const dragV = (b, i, e) => {
    if (!edit || tool !== 'select') return;
    e.stopPropagation(); const sx = e.clientX, sy = e.clientY; let moved = false, cur = null; const o0 = b.outline;
    const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 5) moved = true; if (moved) {
      const w = worldOf(ev); cur = o0.map((q, k) => k === i ? [snapO(w.x), snapO(w.y)] : q); setLive({ id: b.id, outline: cur }); } };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      if (moved && cur) setOutline(b, cur); else setSelV(i); setLive(null); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const addV = (b, i, e) => { e.stopPropagation(); const o = b.outline, a = o[i], c = o[(i + 1) % o.length];
    if (o.length >= 120) { toast('Больше углов нельзя', true); return; }
    setOutline(b, [...o.slice(0, i + 1), [snapO((a[0] + c[0]) / 2), snapO((a[1] + c[1]) / 2)], ...o.slice(i + 1)]); setSelV(i + 1); };
  const delV = () => { const b = buildings.find(x => x.id === sel); if (!b || !isOut(b) || selV === null) return;
    if (b.outline.length <= 3) { toast('У дома должно остаться хотя бы три угла', true); return; }
    setOutline(b, b.outline.filter((_, k) => k !== selV)); setSelV(null); };

  if (!buildings.length && !bgs.length && !geo) return <div className="plan-empty card pad">
    <WorkMenu title="План">
      <WorkSec title="Карта"><WorkItem icon="map" label="Выбрать место на карте" sub="адрес участка → живая карта 3D" onClick={() => { if (edit) setBgOpen(true); else toast('Сначала включите «Редактирование»', true); }} /></WorkSec>
      {edit ? <WorkSec title="Дома"><WorkItem icon="home" label="Создать дом без карты" onClick={addBuilding} /></WorkSec> : null}
    </WorkMenu>
    <div style={{ fontSize: 42 }}>🗺️</div><div style={{ fontSize: 17, fontWeight: 700, margin: '8px 0 4px' }}>Плана пока нет</div>
    <div className="dim" style={{ marginBottom: 16, maxWidth: 440 }}>Выберите место на карте — откроется живая 3D-карта района, на ней можно обвести свои дома.
      Дальше у каждого дома есть этажи, комнаты, оборудование и своя карта сети, связанная с общей.</div>
    {edit ? <div className="row wrap" style={{ gap: 8 }}><Btn kind="primary" icon="map" onClick={() => setBgOpen(true)}>Выбрать место на карте</Btn><Btn icon="home" onClick={addBuilding}>Создать дом без карты</Btn></div>
      : <div className="dim">Включите «Редактирование» в меню (кнопка вверху справа), чтобы начать.</div>}
    {bgOpen ? <PlanBgModal plan={plan} center={{ x: 400, y: 300 }} onClose={() => setBgOpen(false)} onMove={() => {}} onLive={() => {}} /> : null}
  </div>;

  const center = id => { const b = buildings.find(x => x.id === id); if (b) { if (isOut(b)) return polyCenter(outlineOf(b)); const p = pos(b); return { x: p.x + BW / 2, y: p.y + BH / 2 }; }
    const p = poles.find(x => x.id === id) || nodes.find(x => x.id === id); return p ? { x: p.x, y: p.y } : null; };
  const selB = buildings.find(b => b.id === sel), selP = poles.find(p => p.id === sel);
  const selOut = selB && isOut(selB) ? outlineOf(selB) : null;
  const contentCenter = (() => { const xs = [], ys = []; buildings.forEach(b => { const q = boxOf(b); xs.push(q.x, q.x + q.w); ys.push(q.y, q.y + q.h); });
    return xs.length ? { x: (Math.min(...xs) + Math.max(...xs)) / 2, y: (Math.min(...ys) + Math.max(...ys)) / 2 } : { x: 400, y: 300 }; })();
  const toWorldRing = ring => {                              // углы из широты/долготы → точки плана (через 1 м, без повторов)
    const pts = []; ring.forEach(([lon, lat]) => { const w = geoToWorld(lat, lon, geo), p = [snapO(w.x), snapO(w.y)], l = pts[pts.length - 1];
      if (!l || l[0] !== p[0] || l[1] !== p[1]) pts.push(p); });
    if (pts.length > 1 && pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1]) pts.pop();
    return pts; };
  const addHouseGeo = (ring, name) => {                      // дом, обведённый на 3D-карте
    const pts = toWorldRing(ring);
    if (pts.length < 3) { toast('Дом получился слишком маленьким — обведите его крупнее', true); return false; }
    const id = uid('b'), b0 = polyBox(pts), n = buildings.length;
    save([...buildings, { id, name: name || `Дом ${n + 1}`, x: b0.x0, y: b0.y0, outline: pts, floors: [{ id: uid('f'), name: '1 этаж', walls: [], rooms: [], items: [] }] }]);
    setSel(id);
    return true;
  };
  const editRingGeo = (id, ring) => {                        // углы выбранного дома тянули на 3D-карте
    const pts = toWorldRing(ring);
    if (pts.length < 3) { toast('Дом получился слишком маленьким', true); return; }
    const b0 = polyBox(pts); save(buildings.map(x => x.id === id ? { ...x, outline: pts, x: b0.x0, y: b0.y0 } : x));
  };
  const styleHouse = (id, patch) => save(buildings.map(x => x.id === id ? { ...x, ...patch } : x));       // цвет, контур, подсветка, высота
  const renameB = id => { const b = buildings.find(x => x.id === id); if (!b) return;
    const name = ((typeof prompt === 'function' ? prompt('Название дома', b.name) : '') || '').trim(); if (name) save(buildings.map(x => x.id === id ? { ...x, name } : x)); };
  const geoPt = (lon, lat) => { const w = geoToWorld(lat, lon, geo); return { x: snapO(w.x), y: snapO(w.y) }; };
  const addPoleGeo = (lon, lat) => { const w = geoPt(lon, lat), id = uid('p'); save(null, null, [...poles, { id, name: `Столб ${poles.length + 1}`, x: w.x, y: w.y }]); setSel(id); };
  const addNodeGeo = (lon, lat) => {                         // узел: ставим, называем и сразу предлагаем подвязать к шкафу или устройству
    const w = geoPt(lon, lat), id = uid('n'), nm = ((typeof prompt === 'function' ? prompt('Название узла', `Узел ${nodes.length + 1}`) : '') || '').trim() || `Узел ${nodes.length + 1}`;
    save(null, null, null, [...nodes, { id, name: nm, x: w.x, y: w.y }]); setSel(id); setNodeBind(id); };
  const movePointGeo = (kind, id, lon, lat) => { const w = geoPt(lon, lat);
    if (kind === 'pole') save(null, null, poles.map(p => p.id === id ? { ...p, x: w.x, y: w.y } : p)); else save(null, null, null, nodes.map(p => p.id === id ? { ...p, x: w.x, y: w.y } : p)); };
  const renamePoint = id => { const p = poles.find(x => x.id === id) || nodes.find(x => x.id === id); if (!p) return;
    const nm = ((typeof prompt === 'function' ? prompt('Название', p.name) : '') || '').trim(); if (!nm) return;
    if (poles.some(x => x.id === id)) save(null, null, poles.map(x => x.id === id ? { ...x, name: nm } : x)); else save(null, null, null, nodes.map(x => x.id === id ? { ...x, name: nm } : x)); };
  const deletePoint = async id => { const p = poles.find(x => x.id === id) || nodes.find(x => x.id === id); if (!p) return;
    if (!(await confirm(`Удалить «${p.name}» и его магистрали?`, { danger: true, ok: 'Удалить' }))) return;
    const l2 = links.filter(l => l.from !== id && l.to !== id);
    if (poles.some(x => x.id === id)) save(null, l2, poles.filter(x => x.id !== id)); else save(null, l2, null, nodes.filter(x => x.id !== id)); setSel(null); };
  const bindNode = (id, ref) => save(null, null, null, nodes.map(x => { if (x.id !== id) return x; const { ref: _old, ...rest } = x; return ref ? { ...rest, ref } : rest; }));
  const refOf = n => {                                       // к чему подвязан узел: имя и состояние шкафа или устройства
    const r = n.ref; if (!r) return null;
    if (r.kind === 'device') { const d = devById[r.id]; return d ? { name: d.name, status: (d.state && d.state.status) || '' } : null; }
    const rk = data.racks.find(x => x.id === r.id); return rk ? { name: rk.name, status: placeStatus(rk, devById) } : null; };
  const openRef = id => { const n = nodes.find(x => x.id === id); if (!n || !n.ref) return; if (n.ref.kind === 'device') { const d = devById[n.ref.id]; if (d) openDevice(d, undefined, undefined, true); } else openPlace(n.ref.id); };
  const linkPick3 = id => {                                   // 3D, «Магистраль»: два нажатия — дом, столб или узел
    if (id == null) { setPickLink(null); return; }
    if (!pickLink) { setPickLink(id); return; }
    if (pickLink === id) { setPickLink(null); return; }
    setLinkEdit({ link: { id: uid('l'), from: pickLink, to: id, label: '' }, isNew: true }); setPickLink(null); };
  const editLink3 = id => { const l = links.find(x => x.id === id); if (l) setLinkEdit({ link: l }); };
  const noOutline = buildings.filter(b => !isOut(b));
  const liveSpec = () => {                                  // дома, столбы и магистрали в координатах для 3D-карты
    const ll = (x, y) => { const g = worldToGeo(x, y, geo); return [g.lon, g.lat]; };
    const houses = buildings.filter(isOut).map(b => { const o = b.outline, c = polyCenter(o), g = worldToGeo(c.x, c.y, geo); const devs = (b.floors || []).flatMap(f => floorDevices(f, data, devById));
      return { id: b.id, name: b.name, ring: o.map(([x, y]) => ll(x, y)), center: { lon: g.lon, lat: g.lat }, floors: Math.max(1, (b.floors || []).filter(f => !f.outdoor).length), devs: devs.length, status: worst(devs),
        color: b.color || '', edge: b.edge || '', hl: !!b.hl, height: +b.height || 0 }; });
    const polesG = poles.map(p => { const g = worldToGeo(p.x, p.y, geo); return { id: p.id, name: p.name, lon: g.lon, lat: g.lat }; });
    const nodesG = nodes.map(p => { const g = worldToGeo(p.x, p.y, geo), r = refOf(p); return { id: p.id, name: p.name, lon: g.lon, lat: g.lat, status: r ? r.status || 'none' : 'none', refName: r ? r.name : '', refKind: p.ref ? p.ref.kind : '' }; });
    const linksG = links.map(l => { const a = center(l.from), b2 = center(l.to); return a && b2 ? { id: l.id, coords: [ll(a.x, a.y), ll(b2.x, b2.y)] } : null; }).filter(Boolean);
    const mid = houses.length ? { lon: houses.reduce((s, h) => s + h.center.lon, 0) / houses.length, lat: houses.reduce((s, h) => s + h.center.lat, 0) / houses.length } : { lon: geo.lon, lat: geo.lat };
    const search = [                                          // что можно найти по имени: дома, столбы, узлы, а также устройства и шкафы — переход к дому, где они стоят
      ...houses.map(h => ({ id: h.id, kind: 'house', name: h.name, sub: 'дом', hay: h.name, lon: h.center.lon, lat: h.center.lat })),
      ...polesG.map(p => ({ id: p.id, kind: 'pole', name: p.name, sub: 'столб', hay: p.name, lon: p.lon, lat: p.lat })),
      ...nodesG.map(p => ({ id: p.id, kind: 'node', name: p.name, sub: p.refName ? 'узел · ' + p.refName : 'узел', hay: p.name + ' ' + p.refName, lon: p.lon, lat: p.lat })),
      ...houses.flatMap(h => { const b = buildings.find(x => x.id === h.id), seen = new Set(), out = [];
        (b.floors || []).forEach(f => (f.items || []).forEach(it => {
          if (it.kind === 'device' && devById[it.ref] && !seen.has(it.ref)) { seen.add(it.ref); const d = devById[it.ref]; out.push({ id: h.id, kind: 'device', name: d.name, sub: 'устройство · ' + h.name, hay: d.name + ' ' + (d.host || d.ip || ''), lon: h.center.lon, lat: h.center.lat }); }
          if (it.kind === 'place' && !seen.has(it.ref)) { seen.add(it.ref); const r = data.racks.find(x => x.id === it.ref); if (r) out.push({ id: h.id, kind: 'rack', name: r.name, sub: 'шкаф · ' + h.name, hay: r.name, lon: h.center.lon, lat: h.center.lat }); } }));
        return out; })];
    return { center: [mid.lon, mid.lat], houses, poles: polesG, nodes: nodesG, links: linksG, search };
  };
  const styleView = b => b ? { color: b.color || '', edge: b.edge || '', hl: !!b.hl, height: +b.height || 0, floors: Math.max(1, (b.floors || []).filter(f => !f.outdoor).length) } : null;
  const is3d = !!geo;                                        // есть место на земле — всегда живая карта; плоская схема только пока места нет
  const r1 = 7 / view.k;                                         // кружки углов одного размера на экране при любом зуме
  const barText = !edit ? '' : tool === 'pole' ? 'Нажмите на план, куда поставить столб' : tool === 'link' ? (linkFrom ? `От «${nodeName(linkFrom)}» — выберите второй дом или столб` : 'Выберите первый дом или столб магистрали')
    : tool === 'outline' ? (draft.length ? `Углов: ${draft.length}. Чтобы замкнуть, нажмите на первый угол или «Готово»` : 'Нажимайте по углам дома на карте — по кругу')
    : tool === 'bg' && moving ? `Тащите карту «${moving.name || 'Фон'}», чтобы совместить её с домами` : '';
  return <div className="plan">
    <WorkMenu title="План">
      {edit && !is3d ? <WorkSec title="Инструменты плана">
        <WorkChoice value={tool} options={[{ value: 'select', label: 'Двигать', icon: 'cursor' }, { value: 'outline', label: 'Обвести дом', icon: 'edit' }, { value: 'pole', label: 'Столб', icon: 'pole' },
          { value: 'link', label: 'Магистраль', icon: 'link' }, ...(bgs.length ? [{ value: 'bg', label: 'Фон', icon: 'resize' }] : [])]}
          onChange={v => { setTool(v); setLinkFrom(null); setDraft([]); setSelV(null); }} />
        <WorkItem icon="plus" label="Добавить дом-плитку" sub="без контура на карте" onClick={addBuilding} />
      </WorkSec> : null}
      <WorkSec title="Карта и фон">
        <WorkItem icon="map" label={geo ? 'Место и фон карты…' : 'Выбрать место на карте'} sub={geo ? 'адрес, спутниковый снимок, свой файл' : 'адрес участка → живая карта 3D'}
          onClick={() => { if (edit) setBgOpen(true); else toast('Включите «Редактирование», чтобы менять карту', true); }} />
      </WorkSec>
      {selB && !is3d ? <WorkSec title={'Дом «' + selB.name + '»'}>
        <WorkItem icon="home" label="Открыть дом" sub="этажи, комнаты, оборудование" onClick={() => enter(selB.id)} />
        {edit ? <>
          <WorkItem icon="edit" label="Переименовать" onClick={() => renameB(selB.id)} />
          <WorkItem icon="tag" label="Цвета и высота" onClick={() => setStyleFor(selB.id)} />
          {selOut && selV !== null ? <WorkItem icon="minus" label="Убрать выбранный угол" onClick={delV} /> : null}
          <WorkItem icon="trash" danger label="Удалить дом" onClick={() => delBuilding(selB.id)} /></> : null}
      </WorkSec> : null}
      {selP && !is3d && edit ? <WorkSec title={'Столб «' + selP.name + '»'}>
        <WorkItem icon="edit" label="Переименовать" onClick={() => { const name = prompt('Название столба', selP.name); if (name && name.trim()) save(null, null, poles.map(x => x.id === sel ? { ...x, name: name.trim() } : x)); }} />
        <WorkItem icon="trash" danger label="Удалить столб" onClick={() => delPole(sel)} />
      </WorkSec> : null}
    </WorkMenu>
    {is3d ? <LiveMap3D spec={liveSpec()} edit={edit} sel={sel} onSel={id => setSel(id)} onAddHouse={addHouseGeo} onEditRing={editRingGeo} onStyle={styleHouse} onRename={renameB}
      onDelete={delBuilding} onOpen={enter} onNet={net} onAddPole={addPoleGeo} onAddNode={addNodeGeo} onMovePoint={movePointGeo} onLinkPick={linkPick3} linkFrom={pickLink} onEditLink={editLink3}
      onRenamePoint={renamePoint} onDeletePoint={deletePoint} onBindNode={id => setNodeBind(id)} onOpenRef={openRef} noOutline={noOutline} />
    : <div className={'plan-canvas' + (tool !== 'select' && tool !== 'bg' && edit ? ' crosshair' : '')} ref={wrap} {...bind}>
      <svg>
        <defs><pattern id="pgridT" width={PG} height={PG} patternUnits="userSpaceOnUse" patternTransform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <circle cx={1} cy={1} r={.8} fill="var(--line)" /></pattern></defs>
        <rect x={0} y={0} width="100%" height="100%" fill="url(#pgridT)" />
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {bgs.map(b => <image key={b.id} href={`/api/plan/bg/${b.id}?v=${b.v}`} x={b.x} y={b.y} width={b.w} height={b.h} preserveAspectRatio="none" opacity={b.op} style={{ pointerEvents: 'none' }} />)}
          {links.map((l, idx) => { const c1 = center(l.from), c2 = center(l.to); if (!c1 || !c2) return null;
            const key = [l.from, l.to].sort().join('>');                    // offset parallel links between the same pair
            const sib = links.filter(x => [x.from, x.to].sort().join('>') === key);
            const pos2 = sib.indexOf(l), off = (pos2 - (sib.length - 1) / 2) * 22;
            const dx = c2.x - c1.x, dy = c2.y - c1.y, len = Math.hypot(dx, dy) || 1;
            const nx = -dy / len * off, ny = dx / len * off;
            const p1 = { x: c1.x + nx, y: c1.y + ny }, p2 = { x: c2.x + nx, y: c2.y + ny };
            return <g key={l.id}>
              <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} className="plan-link" onClick={() => edit && setLinkEdit({ link: l })} />
              {l.label || l.via ? <text x={(p1.x + p2.x) / 2} y={(p1.y + p2.y) / 2 - 8} textAnchor="middle" className="plan-link-label">
                {[l.label, viaText(data, l.via, true)].filter(Boolean).join(' · ')}</text> : null}</g>; })}
          {buildings.map(b => { const p = pos(b); const devs = (b.floors || []).flatMap(f => floorDevices(f, data, devById)); const st = worst(devs);
            const hasYard = (b.floors || []).some(f => f.outdoor);
            if (isOut(b)) { const o = outlineOf(b), c = polyCenter(o); const nm = b.name.length > 22 ? b.name.slice(0, 21) + '…' : b.name; const fs = Math.max(14, Math.min(44, 13 / view.k));     // подпись читается на любом зуме
              const hx = s => typeof s === 'string' && /^#[0-9a-fA-F]{6}$/.test(s) ? s : '';
              const oc = { ...(hx(b.color) ? { fill: hx(b.color) + '47' } : {}), ...(hx(b.edge) || hx(b.color) ? { stroke: hx(b.edge) || hx(b.color) } : {}),
                ...(b.hl ? { filter: `drop-shadow(0 0 ${Math.max(4, 8 / view.k)}px ${hx(b.edge) || hx(b.color) || 'var(--accent)'})` } : {}) };
              return <g key={b.id} className={'plan-item plan-building plan-outlined' + (sel === b.id ? ' sel' : '') + (linkFrom === b.id ? ' sel' : '')}
                onPointerDown={e => dragB(b, e)} style={{ cursor: edit && tool === 'select' ? 'move' : 'pointer' }}>
                <polygon points={o.map(q => q.join(',')).join(' ')} className="plan-outline" style={oc} />
                <circle cx={c.x} cy={c.y - fs * 1.9} r={fs * .36} fill={statusColor(st)} />
                <text x={c.x} y={c.y - fs * .25} textAnchor="middle" className="plan-outline-name" style={{ fontSize: fs }}>{nm}</text>
                <text x={c.x} y={c.y + fs * .95} textAnchor="middle" className="plan-outline-sub" style={{ fontSize: fs * .82 }}>{(b.floors || []).length} эт. · {devs.length} устр.{bgs.length ? ` · ${Math.round(polyArea(o) / (PPM * PPM))} м²` : ''}</text>
              </g>; }
            return <g key={b.id} className={'plan-item plan-building' + (sel === b.id ? ' sel' : '') + (linkFrom === b.id ? ' sel' : '')} transform={`translate(${p.x},${p.y})`}
              onPointerDown={e => dragB(b, e)} style={{ cursor: edit && tool === 'select' ? 'move' : 'pointer' }}>
              {hasYard ? <rect x={-18} y={-18} width={BW + 36} height={BH + 36} rx={18} className="plan-yard" /> : null}
              <rect x={0} y={0} width={BW} height={BH} rx={14} className="pi-card" />
              <g transform="translate(18,18)"><Icon name="home" size={26} color="var(--accent)" /></g>
              <text x={54} y={30} className="pb-name">{b.name.length > 20 ? b.name.slice(0, 19) + '…' : b.name}</text>
              <text x={54} y={50} className="pb-sub">{(b.floors || []).length} эт.{hasYard ? ' · двор' : ''} · {devs.length} устр.</text>
              <circle cx={BW - 20} cy={22} r={6} fill={statusColor(st)} />
              <text x={18} y={BH - 18} className="pb-hint">{edit ? 'перетащите · нажмите — выбрать' : sel === b.id ? 'нажмите ещё раз, чтобы зайти' : 'нажмите, чтобы выбрать'}</text>
            </g>; })}
          {poles.map(p => <g key={p.id} className={'plan-item plan-pole' + (sel === p.id || linkFrom === p.id ? ' sel' : '')} transform={`translate(${p.x},${p.y})`}
            onPointerDown={e => dragPole(p, e)} style={{ cursor: edit && tool === 'select' ? 'move' : 'pointer' }}>
            <circle r={16} className="pole-bg" />
            <line x1={0} y1={-8} x2={0} y2={11} className="pole-mast" /><line x1={-9} y1={-8} x2={9} y2={-8} className="pole-mast" />
            <circle cx={-9} cy={-10.5} r={2} className="pole-ins" /><circle cx={0} cy={-10.5} r={2} className="pole-ins" /><circle cx={9} cy={-10.5} r={2} className="pole-ins" />
            <text y={30} textAnchor="middle" className="pi-label">{p.name.length > 16 ? p.name.slice(0, 15) + '…' : p.name}</text></g>)}
          {edit && tool === 'select' && selOut ? <g className="plan-item plan-vtxs">
            {selOut.map((q, i) => { const n2 = selOut[(i + 1) % selOut.length];
              return <circle key={'m' + i} cx={(q[0] + n2[0]) / 2} cy={(q[1] + n2[1]) / 2} r={r1 * .75} className="plan-vtx ghost" onPointerDown={e => addV(selB, i, e)} />; })}
            {selOut.map((q, i) => <circle key={'v' + i} cx={q[0]} cy={q[1]} r={r1} className={'plan-vtx' + (selV === i ? ' sel' : '')} onPointerDown={e => dragV(selB, i, e)} />)}</g> : null}
          {draft.length ? <g className="plan-draft" style={{ pointerEvents: 'none' }}>
            <polyline points={draft.map(q => q.join(',')).join(' ')} className="plan-draft-line" />
            {draft.map((q, i) => <circle key={i} cx={q[0]} cy={q[1]} r={i === 0 && draft.length >= 3 ? r1 * 1.5 : r1 * .8} className={'plan-vtx' + (i === 0 ? ' first' : '')} />)}</g> : null}

        </g>
      </svg>
      {edit && barText ? <div className="live-bar"><div className="live-bar-t">{barText}</div>
        <div className="live-bar-b">{tool === 'outline' && draft.length >= 3 ? <Btn size="sm" kind="primary" icon="check" onClick={finishOutline}>Готово</Btn> : null}
          {tool === 'outline' && draft.length ? <Btn size="sm" onClick={() => setDraft(draft.slice(0, -1))}>Убрать угол</Btn> : null}
          {tool === 'outline' && draft.length ? <Btn size="sm" onClick={() => setDraft([])}>Сбросить</Btn> : null}
          {tool !== 'select' ? <Btn size="sm" onClick={() => { setTool('select'); setDraft([]); setLinkFrom(null); }}>Готово</Btn> : null}</div></div> : null}
      {selB && tool === 'select' ? <div className="plan-open-g">
        <button className="plan-open" onClick={() => enter(selB.id)}><Icon name="home" size={16} />Открыть «{selB.name.length > 14 ? selB.name.slice(0, 13) + '…' : selB.name}»</button></div> : null}
      {bgs.some(b => b.attr) ? <div className="plan-attrib">{(bgs.find(b => b.attr) || {}).attr}</div> : null}
      <ZoomBtns setView={setView} onFit={fitAll} />
    </div>}
    {bgOpen ? <PlanBgModal plan={plan} center={contentCenter} onClose={() => setBgOpen(false)} onMove={geo ? null : (id => { setBgMove(id); setBgOpen(false); setTool('bg'); })} onLive={() => setSel(null)} /> : null}
    {nodeBind && nodes.find(n => n.id === nodeBind) ? <NodeBind node={nodes.find(n => n.id === nodeBind)} data={data} onPick={ref => { bindNode(nodeBind, ref); setNodeBind(null); }} onClose={() => setNodeBind(null)} /> : null}
    {styleFor && buildings.find(b => b.id === styleFor) ? <Modal title="Цвета и высота дома" onClose={() => setStyleFor(null)} footer={<><div className="grow" /><Btn kind="primary" icon="check" onClick={() => setStyleFor(null)}>Готово</Btn></>}>
      <HouseStyle h={styleView(buildings.find(b => b.id === styleFor))} onChange={p => styleHouse(styleFor, p)} /></Modal> : null}
    {linkEdit ? <LinkEditor link={linkEdit.link} isNew={linkEdit.isNew} title={`${nodeName(linkEdit.link.from)} → ${nodeName(linkEdit.link.to)}`}
      onSave={saveLink} onDelete={() => save(null, links.filter(x => x.id !== linkEdit.link.id))} onClose={() => setLinkEdit(null)} /> : null}
  </div>;
}

/* the physical cable behind a backbone: a fibre of an optical cross or a patch-panel port */
function viaText(data, via, short) {
  if (!via) return '';
  const u = allUnits(data).find(x => x.id === via.unit); if (!u) return '';
  const m = ((u.portmap || {}).ports || {})[via.port] || {};
  return short ? `${u.type === 'cross' ? 'волокно' : 'порт'} ${via.port}${m.color ? ' ' + m.color : ''}`
    : `${u.name} · ${u.type === 'cross' ? 'волокно' : 'порт'} ${via.port}${m.color ? ' (' + m.color + ')' : ''}${m.label ? ' · ' + m.label : ''}`;
}
/* к чему подвязать узел: шкаф (место) или устройство; узел потом показывает их состояние и открывает их */
function NodeBind({ node, data, onPick, onClose }) {
  const [q, setQ] = useState('');
  const ok = s => !q.trim() || String(s).toLowerCase().includes(q.trim().toLowerCase());
  const racks = (data.racks || []).filter(r => ok(r.name)), devs = (data.devices || []).filter(d => ok(d.name));
  const cur = node.ref || {};
  return <Modal title={`Узел «${node.name}» — к чему подвязать`} onClose={onClose}
    footer={<>{node.ref ? <Btn kind="danger" onClick={() => onPick(null)}>Отвязать</Btn> : null}<div className="grow" /><Btn onClick={onClose}>{node.ref ? 'Закрыть' : 'Позже'}</Btn></>}>
    <SearchBox value={q} onChange={setQ} placeholder="Найти шкаф или устройство" />
    {racks.length ? <><div className="dim" style={{ fontSize: 12.5, margin: '10px 0 4px' }}>Шкафы и места</div>
      <div className="list">{racks.map(r => <div key={r.id} className="li" style={{ cursor: 'pointer' }} onClick={() => onPick({ kind: 'place', id: r.id })}>
        <Icon name="rack" size={16} /><span className="grow" style={{ marginLeft: 8 }}>{r.name}</span>{cur.kind === 'place' && cur.id === r.id ? <Icon name="check" size={15} /> : null}</div>)}</div></> : null}
    {devs.length ? <><div className="dim" style={{ fontSize: 12.5, margin: '10px 0 4px' }}>Устройства и серверы</div>
      <div className="list">{devs.slice(0, 80).map(d => <div key={d.id} className="li" style={{ cursor: 'pointer' }} onClick={() => onPick({ kind: 'device', id: d.id })}>
        <Icon name={d.kind} size={16} /><span className="grow" style={{ marginLeft: 8 }}>{d.name}</span>{cur.kind === 'device' && cur.id === d.id ? <Icon name="check" size={15} /> : null}</div>)}</div></> : null}
    {!racks.length && !devs.length ? <div className="dim" style={{ marginTop: 10 }}>Ничего не нашлось.</div> : null}
  </Modal>;
}

function LinkEditor({ link, isNew, title, onSave, onDelete, onClose }) {
  const { data } = useApp(); const confirm = useConfirm();
  const [label, setLabel] = useState(link.label || '');
  const [via, setVia] = useState(link.via ? link.via.unit + '|' + link.via.port : '');
  const opts = allUnits(data).filter(u => u.portmap && (u.type === 'cross' || u.type === 'patch')).flatMap(u =>
    Array.from({ length: u.portmap.count }, (_, i) => { const n = i + 1, m = u.portmap.ports[n] || {};
      return { v: u.id + '|' + n, u, t: viaText(data, { unit: u.id, port: n }), used: !!(m.label || m.color || m.dev) }; }));
  const groups = [...new Set(opts.map(o => o.u.id))].map(id => opts.filter(o => o.u.id === id));
  const save = () => { const [unit, port] = via ? via.split('|') : [];
    onSave({ ...link, label: label.trim(), via: via ? { unit, port: +port } : undefined }); onClose(); };
  return <Modal title={isNew ? 'Новая магистраль' : 'Магистраль'} onClose={onClose}
    footer={<>{!isNew ? <Btn kind="danger" icon="trash" onClick={async () => { if (await confirm('Удалить эту магистраль?', { danger: true, ok: 'Удалить' })) { onDelete(); onClose(); } }}>Удалить</Btn> : null}
      <div className="grow" /><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={save}>Сохранить</Btn></>}>
    <div className="dim" style={{ fontSize: 13.5 }}>{title}</div>
    <Field label="Подпись"><input className="input" value={label} autoFocus placeholder="Оптика 1 Гбит, воздушка, витая пара…" onChange={e => setLabel(e.target.value)} /></Field>
    <Field label="Физически идёт через" hint={opts.length ? 'Волокно оптического кросса или порт патч-панели — у кросса тоже будет видно, что это за магистраль' : 'Подпишите порты кросса или патч-панели на вкладке «Размещение» — тогда их можно будет выбрать здесь'}>
      <select className="select" value={via} onChange={e => setVia(e.target.value)}>
        <option value="">— не указано —</option>
        {groups.map(g => <optgroup key={g[0].u.id} label={g[0].u.name}>{g.sort((a, b) => b.used - a.used).map(o => <option key={o.v} value={o.v}>{o.t}</option>)}</optgroup>)}
      </select></Field>
  </Modal>;
}

/* ───────── one building: floors with walls, rooms, equipment ───────── */
function loadPlanSurvey(id) {
  try { const s=JSON.parse(ssGet('rl_plan_survey:'+id));
    return s?.v===1 && s.buildingId===id && typeof s.floorId==='string' && typeof s.roomId==='string' &&
      Number.isInteger(s.index) && s.index>=0 && s.index<=5 && s.roomRect && ['x','y','w','h'].every(k=>Number.isFinite(s.roomRect[k])) && s.points?.length===5 && s.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)) ? s : null;
  } catch (_) { return null; }
}
function BuildingPlan({ building, plan, back }) {
  const { data, edit, admin, savePlan, openDevice, openPlace, setTab, setMode, refresh, pinTest, setPinTest } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const defaults = planPreferences(data.settings);
  const buildings = plan.buildings; const links = plan.links || [];
  const [cov, setCov] = useState(() => defaults.coverage !== false);
  const [covMode, setCovMode] = useState('auto');
  const [covSource, setCovSource] = useState('');
  const [selTest, setSelTest] = useState(null);
  const networkDevices = planNetworkDevices(data);
  const devById = Object.fromEntries(networkDevices.map(d => [d.id, d]));
  const projection = { a: ISO_A, b: ISO_B, c: ISO_C, d: ISO_D };
  const [roomResize, setRoomResize] = useState(null);
  const indoorFloors = building.floors.filter(f => !f.outdoor);
  const [fid, setFid] = useState(() => loadPlanSurvey(building.id)?.floorId || ((defaults.houseView === 'first' ? indoorFloors[0] : indoorFloors[indoorFloors.length - 1]) || building.floors[0]).id);
  const floor = indoorFloors.find(f => f.id === fid) || indoorFloors[indoorFloors.length - 1] || building.floors[0];
  const floorIndex = Math.max(0, indoorFloors.findIndex(f => f.id === floor.id));
  const legacyOutsideItems = building.floors.filter(f => f.outdoor).flatMap(f => (f.items || []).map(it => ({ ...it, outdoor: true, _originFloorId: f.id })));
  const sceneFloors = indoorFloors.map((f,i) => ({ ...f,
    ...(roomResize?.floorId === f.id ? { rooms: (f.rooms || []).map(r => r.id === roomResize.id ? roomResize.rect : r) } : {}),
    ...(i === 0 && legacyOutsideItems.length ? { items: [...(f.items || []), ...legacyOutsideItems] } : {}) }));
  const sceneBounds = useMemo(() => planBounds(sceneFloors), [building.id, building.floors]);
  const houseBounds = useMemo(() => planStructureBounds(indoorFloors), [building.id, building.floors]);
  const [tool, setTool] = useState('select');               // select | room | wall | place | erase
  const [pending, setPending] = useState(null);
  const [equipQuery, setEquipQuery] = useState('');
  const [wallPt, setWallPt] = useState(null);
  const [frameDraft, setFrameDraft] = useState(null);
  const [draft, setDraft] = useState(null);                 // room rubber-band {x,y,w,h}
  const [sel, setSel] = useState(null);
  // Open multi-floor buildings in the exploded overview so the user can pick a floor immediately.
  const [ghost, setGhost] = useState(() => defaults.lowerFloors !== false && indoorFloors.length > 1);
  const [overview, setOverview] = useState(() => defaults.houseView === 'all' && !pinTest && !loadPlanSurvey(building.id));
  const equipmentScale = Math.max(.6, Math.min(2.4, Number(building.equipmentScale) || Number(defaults.equipmentSize) || 1.2));
  const coverageMarkerScale = Math.max(.2, Math.min(1, Number(building.coverageMarkerScale) || Number(defaults.markerSize) || .3));
  const sceneIndex = overview ? indoorFloors.length-1 : floorIndex;
  const floorStep = overview ? ISO_WALL + ISO_SLAB + 24 : ISO_FLOOR;
  // «Весь дом» ↔ этаж ↔ другой этаж: этажи плавно раздвигаются / сдвигаются, лишние растворяются, стены вырастают; камера едет следом (fitFloor)
  const animTarget = { idx: sceneIndex, step: floorStep, wall: overview ? 72 : ISO_WALL, shell: overview ? 1 : 0, ground: overview || ghost || sceneIndex === 0 ? 1 : 0 };
  sceneFloors.forEach((f, i) => { animTarget['o' + f.id] = overview ? (i === indoorFloors.length - 1 ? 1 : .9) : i === floorIndex ? 1 : ghost && i < floorIndex ? .46 : 0; });
  const anim = useTween(animTarget, 520);
  const [editOpen, setEditOpen] = useState(false);
  const [roomEditor, setRoomEditor] = useState(null);
  const [survey, setSurvey] = useState(()=>loadPlanSurvey(building.id));
  const [surveyChoose, setSurveyChoose] = useState(false);
  const [surveyConnection, setSurveyConnection] = useState(null);
  const [surveyHidden, setSurveyHidden] = useState(false);
  const [surveyPicking, setSurveyPicking] = useState(false);
  const [surveyMeasuring, setSurveyMeasuring] = useState(false);
  const [surveySaving, setSurveySaving] = useState(false);
  const surveySavingRef = useRef(false);
  const surveyRef = useRef(survey); surveyRef.current=survey;
  useEffect(()=>ssSet('rl_plan_survey:'+building.id,survey?JSON.stringify(survey):null),[survey,building.id]);
  useEffect(()=>{if(!surveyChoose)return;let active=true;setSurveyConnection(null);api('/api/speedtest/who').then(c=>{if(active)setSurveyConnection(c)}).catch(()=>{if(active)setSurveyConnection({})});return()=>{active=false}},[surveyChoose]);
  const surveyFloor = survey && indoorFloors.find(f=>f.id===survey.floorId);
  const surveyRoom = surveyFloor?.rooms?.find(r=>r.id===survey.roomId);
  const surveyValid = !!surveyRoom && ['x','y','w','h'].every(k=>surveyRoom[k]===survey.roomRect[k]);
  const surveyOnFloor = survey && survey.floorId===floor.id && !overview;
  const surveyVisible = admin && !!survey && !surveyHidden;
  const placingPoint = !!pinTest || surveyPicking;
  const roomSaving = useRef(false);
  const deleteConfirmOpen = useRef(false);
  const pinSaving = useRef(false);
  const deviceConfirmOpen = useRef(false);
  const wrap = useRef(null);
  const planeRef = useRef(null);
  const visibleItems = floor.id === (indoorFloors[0] && indoorFloors[0].id) ? [...(floor.items || []), ...legacyOutsideItems] : (floor.items || []);
  useEffect(() => { if (!indoorFloors.find(f => f.id === fid) && indoorFloors.length) setFid(indoorFloors[indoorFloors.length - 1].id); }, [building.floors.length]);
  useEffect(() => { if (!edit) { setTool('select'); setPending(null); setWallPt(null); } }, [edit]);

  const saveFloors = floors => savePlan({ ...plan, buildings: buildings.map(b => b.id === building.id ? { ...b, floors } : b), links });
  const setEquipmentScale = value => savePlan({ ...plan, buildings: buildings.map(b => b.id === building.id ? { ...b, equipmentScale: Math.round(Math.max(.6,Math.min(2.4,value))*10)/10 } : b), links });
  const setCoverageMarkerScale = value => savePlan({ ...plan, buildings: buildings.map(b => b.id === building.id ? { ...b, coverageMarkerScale: Math.round(Math.max(.2,Math.min(1,value))*10)/10 } : b), links });
  const resetSize = key => savePlan({ ...plan, buildings: buildings.map(b => { if (b.id !== building.id) return b; const next = { ...b }; delete next[key]; return next; }), links });
  const mutateFloor = (id, fn) => saveFloors(building.floors.map(f => f.id === id ? fn(f) : f));
  const mutate = fn => mutateFloor(floor.id, fn);
  const itemFloorId = it => it._originFloorId || floor.id;
  const changeItems = (it, fn) => mutateFloor(itemFloorId(it), f => ({ ...f, items: fn(f.items || []) }));
  const placeEquipment = w => {
    const next = { id: uid('i'), kind: pending.kind, ref: pending.ref, x: snap(w.x), y: snap(w.y), outdoor: outsideFloorPoint(w, floor),
      ...(pending.snapshot ? { deviceSnapshot: pending.snapshot } : {}) };
    const nextBuildings = buildings.map(b => ({ ...b, floors: b.floors.map(f => {
      let items = (f.items || []).filter(it => !(it.kind === pending.kind && it.ref === pending.ref));
      if (b.id === building.id && f.id === floor.id) items = [...items, next];
      return items.length === (f.items || []).length && items.every((it, i) => it === (f.items || [])[i]) ? f : { ...f, items };
    }) }));
    savePlan({ ...plan, buildings: nextBuildings, links });
  };
  const addFloor = () => { const id = uid('f');
    saveFloors([...building.floors, { id, name: `${indoorFloors.length + 1} этаж`, walls: [], rooms: [], items: [] }]); setFid(id); };
  const delFloor = async () => { if (indoorFloors.length < 2) return toast('Нельзя удалить единственный этаж', true);
    if (!(await confirm(`Удалить «${floor.name}»?`, { danger: true, ok: 'Удалить' }))) return;
    const rest = building.floors.filter(f => f.id !== floor.id); setFid(rest.find(f => !f.outdoor).id); saveFloors(rest); };
  const resetFloorFrame = () => mutateFloor(floor.id, f => { const { frame, ...rest } = f; return rest; });

  const confirmDelete = async (message, action) => {
    if (deleteConfirmOpen.current) return;
    deleteConfirmOpen.current = true;
    try { if (await confirm(message, { danger: true, ok: 'Удалить' })) { await action(); setSel(null); } }
    finally { deleteConfirmOpen.current = false; }
  };
  const eraseAt = w => {
    const th = 14; let wi = -1, bd = th;
    (floor.walls || []).forEach((wl, i) => { const d = segDist(w, wl); if (d < bd) { bd = d; wi = i; } });
    if (wi >= 0) return confirmDelete('Удалить выбранную стену?', () => mutate(f => ({ ...f, walls: f.walls.filter((_, j) => j !== wi) })));
    const rm = (floor.rooms || []).find(r => w.x >= r.x && w.x <= r.x + r.w && w.y >= r.y && w.y <= r.y + r.h);
    if (rm) return confirmDelete(`Удалить комнату «${rm.text || 'Без названия'}»?`, () => mutate(f => ({ ...f, rooms: f.rooms.filter(x => x.id !== rm.id) })));
    const it = visibleItems.find(i => Math.hypot(i.x - w.x, i.y - w.y) < 32);
    if (it) return confirmDelete('Убрать оборудование с плана?', () => changeItems(it, items => items.filter(x => x.id !== it.id)));
  };
  const saveRoom = async e => {
    if (e) e.preventDefault();
    if (!roomEditor || roomSaving.current) return;
    const text = roomEditor.name.trim();
    if (!text) return toast('Введите название комнаты', true);
    const f = building.floors.find(f => f.id === roomEditor.floorId);
    if (!f || (f.rooms || []).some(r => planRoomsOverlap(roomEditor.rect,r))) return toast('Комнаты не должны перекрываться', true);
    roomSaving.current = true;
    const id = uid('r');
    try { await mutateFloor(f.id, f => ({ ...f, rooms: [...(f.rooms || []), { id, ...roomEditor.rect, text, color: '#0a84ff' }] }));
      setRoomEditor(null); setTool('select'); setSel('room:' + id); }
    catch (err) { toast(err.message, true); }
    finally { roomSaving.current = false; }
  };
  const tests = useMemo(() => (data.speedtests || []).filter(t => t.where && t.where.b === building.id && t.where.f === floor.id && Number.isFinite(t.where.x) && Number.isFinite(t.where.y)), [data.speedtests,building.id,floor.id]);
  const coverageSources = useMemo(() => {
    const groups=new Map(); [...tests].sort((a,b)=>(b.t||0)-(a.t||0)).forEach(t=>{const key=coverageGroup(t);if(!groups.has(key))groups.set(key,coverageGroupLabel(t))});
    return [...groups].map(([id,label])=>({id,label}));
  }, [tests]);
  const coverageSource = coverageSources.some(g=>g.id===covSource) ? covSource : coverageSources[0]?.id || '';
  const coverageTests = useMemo(()=>tests.filter(t=>coverageGroup(t)===coverageSource),[tests,coverageSource]);
  const hasSignal = coverageTests.some(t=>coverageValue(t,'signal')!=null);
  const coverageMetric = covMode==='auto' ? (hasSignal ? 'signal' : 'speed') : covMode;
  const coverageData = useMemo(()=>coverageMesh(coverageTests,coverageMetric,floor),[coverageTests,coverageMetric,floor]);
  const coverageReference = coverageScale(coverageData,coverageMetric);
  const legacySignal = coverageMetric==='signal' && coverageTests.some(t=>coverageValue(t,'signal')!=null && t.client?.signalFresh==null);
  const coverageHint = !tests.length ? 'На этом этаже пока нет замеров.' :
    (covMode==='auto' && !hasSignal ? 'Уровень сигнала недоступен — показана скорость. ' : '') +
    (coverageData.triangles.length ? 'Цвет между отметками — оценка по замерам. Пустые участки не измерены. ' :
      'Пока только отметки. Для цветной области сделайте минимум 3 замера в разных местах одной комнаты, не на одной линии. ') +
    (legacySignal ? 'Время опроса старых замеров неизвестно; для точности повторите их. ' : '') +
    (coverageMetric==='signal' && !hasSignal ? 'Нет свежих данных сигнала. Замерьте через локальный адрес NAS; роутер должен видеть телефон. ' : '') +
    'Карты разных точек и диапазонов показаны отдельно. ' + (coverageMetric==='signal' ? 'Это сигнал телефона на роутере. Для сравнения используйте один телефон.' : 'Скорость не определяет границу радиосигнала.');
  const pinAt = async (id, where) => {
    try { await api('/api/speedtest/' + id, { method: 'PUT', body: { where } }); toast(where ? 'Замер отмечен на плане' : 'Отметка убрана'); refresh(); return true; }
    catch (e) { toast(e.message, true); return false; }
  };
  const returnToSurvey = () => { if (!survey) return; setFid(survey.floorId); setOverview(false); setGhost(false); setSurveyHidden(false); setTool('select'); setSel(null); setEditOpen(false); setCov(true); };
  const startSurvey = room => {
    const points=[[.08,.08],[.92,.08],[.92,.92],[.08,.92],[.5,.5]].map(([x,y])=>({x:Math.round(room.x+room.w*x),y:Math.round(room.y+room.h*y)}));
    setSurvey({v:1,buildingId:building.id,floorId:floor.id,roomId:room.id,roomName:room.text||'Комната '+((floor.rooms||[]).indexOf(room)+1),roomRect:{x:room.x,y:room.y,w:room.w,h:room.h},points,index:0,pendingTest:null});
    setSurveyChoose(false); setSurveyHidden(false); setSurveyPicking(false); setPinTest(null); setTool('select'); setSel(null); setOverview(false); setGhost(false); setMode('view'); setEditOpen(false); setCov(true); setCovMode('auto');
  };
  const surveyMeasured = test => setSurvey(s=>s ? {...s,pendingTest:{id:test.id,down:test.down,client:test.client||{}}} : s);
  const saveSurveyPoint = async test => {
    const s=surveyRef.current;
    if (!s || !surveyValid || s.index>=s.points.length || surveySavingRef.current) return false;
    surveySavingRef.current=true; setSurveySaving(true);
    const p=s.points[s.index];
    try {
      if (!(await pinAt(test.id,{b:building.id,f:s.floorId,x:p.x,y:p.y}))) return false;
      const points=s.points.map((p,i)=>i===s.index?{...p,testId:test.id,source:coverageGroup(test)}:p);
      const next=points.findIndex(p=>!p.testId);
      setSurvey({...s,points,index:next<0?points.length:next,pendingTest:null});
      setCov(true); setCovSource(coverageGroup(test)); setCovMode('auto'); setSelTest(null); setSurveyPicking(false);
      return true;
    } finally {surveySavingRef.current=false;setSurveySaving(false)}
  };
  const surveySources = survey ? new Set(survey.points.filter(p=>p.testId).map(p=>p.source)) : new Set();
  const surveySourceChanged = survey?.pendingTest && survey.points.some(p=>p.testId&&p.source!==coverageGroup(survey.pendingTest));
  useEffect(() => { if (pinTest) { setTool('select'); setSel(null); setWallPt(null); setPending(null); setDraft(null); setOverview(false); setSurveyPicking(false); } }, [pinTest]);
  const onTap = async (w, target) => {
    if (overview) return;
    if (pinTest) {
      if (pinSaving.current) return; pinSaving.current=true;
      try { if (await pinAt(pinTest, { b: building.id, f: floor.id, x: Math.round(w.x), y: Math.round(w.y) })) { setPinTest(null); setCov(true); } }
      finally { pinSaving.current=false; } return;
    }
    if (surveyPicking) {
      if (!survey || !surveyValid || !surveyOnFloor) return toast('Вернитесь к комнате обхода',true);
      const room=(floor.rooms||[]).find(r=>r.id===survey.roomId);
      if (coverageRoom(w,floor.rooms||[])!==(floor.rooms||[]).indexOf(room) || survey.points.some((p,i)=>i!==survey.index&&Math.hypot(p.x-w.x,p.y-w.y)<PG)) return toast('Выберите другое место внутри этой комнаты',true);
      setSurvey(s=>({...s,points:s.points.map((p,i)=>i===s.index?{x:Math.round(w.x),y:Math.round(w.y)}:p)}));setSurveyPicking(false);return;
    }
    const wallEl = target && target.closest && target.closest('[data-plan-wall]');
    if (wallEl && admin && edit) {
      const wi = Number(wallEl.getAttribute('data-plan-wall'));
      if (tool === 'select') { setSel('wall:' + wi); return; }
      if (tool === 'erase') { confirmDelete('Удалить выбранную стену?', () => mutate(f => ({ ...f, walls: (f.walls || []).filter((_, j) => j !== wi) }))); return; }
    }
    if (tool === 'wall') { const p = { x: snap(w.x), y: snap(w.y) }; if (wallPt) mutate(f => ({ ...f, walls: [...(f.walls || []), { x1: wallPt.x, y1: wallPt.y, x2: p.x, y2: p.y }] })); setWallPt(p); return; }
    if (tool === 'place' && pending) { placeEquipment(w); setPending(null); setTool('select'); return; }
    if (tool === 'erase') { eraseAt(w); return; }
    if (tool === 'select') setSel(null);
  };
  const rectOf = (w0, w1) => ({ x: snap(Math.min(w0.x, w1.x)), y: snap(Math.min(w0.y, w1.y)), w: snap(Math.abs(w1.x - w0.x)), h: snap(Math.abs(w1.y - w0.y)) });
  const onDraw = (w0, w1, end) => {
    const r = rectOf(w0, w1);
    if (tool === 'room') {
      if (!end) { setDraft(r); return; }
      setDraft(null); if (r.w < PG || r.h < PG) return;
      if ((floor.rooms || []).some(rm => planRoomsOverlap(r,rm))) return toast('Комнаты не должны перекрываться', true);
      setRoomEditor({ floorId: floor.id, rect: r, name: '' }); return;
    }
    if (tool === 'erase') {
      if (!end) { setDraft(r); return; } setDraft(null); if (r.w < PG && r.h < PG) return;
      const inside = (x,y) => x >= r.x && x <= r.x+r.w && y >= r.y && y <= r.y+r.h;
      const wallIds = new Set((floor.walls || []).map((w,i) => inside(w.x1,w.y1) && inside(w.x2,w.y2) ? i : -1).filter(i => i >= 0));
      const roomIds = new Set((floor.rooms || []).filter(rm => inside(rm.x,rm.y) && inside(rm.x+rm.w,rm.y+rm.h)).map(x => x.id));
      const itemIds = new Set((floor.items || []).filter(it => inside(it.x,it.y)).map(x => x.id));
      const total = wallIds.size + roomIds.size + itemIds.size;
      if (total) confirmDelete(`Удалить объекты в выделенной области (${total})?`, () => mutate(f => ({ ...f,
        walls: (f.walls || []).filter((_,i) => !wallIds.has(i)), rooms: (f.rooms || []).filter(x => !roomIds.has(x.id)), items: (f.items || []).filter(x => !itemIds.has(x.id)) })));
    }
  };
  const mapPoint = (cx, cy) => {
    const plane = planeRef.current, svg = wrap.current && wrap.current.querySelector('svg'), m = plane && plane.getScreenCTM();
    if (!m || !svg) return null;
    const pt = svg.createSVGPoint(); pt.x = cx; pt.y = cy; const q = pt.matrixTransform(m.inverse());
    return { x: q.x, y: q.y };
  };
  const { view, setView, toWorld, bind } = usePanZoom(wrap, { canPan: () => placingPoint || tool === 'select', panItems: () => placingPoint || !edit,
    allowCanvasOnItems: () => placingPoint || edit && (tool === 'wall' || tool === 'place'), onTap,
    onDraw: !placingPoint && (tool === 'room' || tool === 'erase') ? onDraw : null, onCancel: () => setDraft(null), mapPoint });

  const resizeFloor = (corner, e) => {
    if (placingPoint) return;
    if (!admin || !edit || tool !== 'select') return;
    e.stopPropagation(); e.preventDefault();
    const base = planFloorFrame(floor, houseBounds), hasContent = !!((floor.rooms || []).length || (floor.walls || []).length), content = planStructureBounds([floor]);
    const nextBounds = p => {
      const n = { ...base }, minW = hasContent ? Math.max(100, content.x2 - content.x1) : 100, minH = hasContent ? Math.max(100, content.y2 - content.y1) : 100;
      if (corner.includes('l')) n.x1 = Math.min(snap(p.x), hasContent ? content.x1 : Infinity, n.x2 - minW);
      else n.x2 = Math.max(snap(p.x), hasContent ? content.x2 : -Infinity, n.x1 + minW);
      if (corner.includes('t')) n.y1 = Math.min(snap(p.y), hasContent ? content.y1 : Infinity, n.y2 - minH);
      else n.y2 = Math.max(snap(p.y), hasContent ? content.y2 : -Infinity, n.y1 + minH);
      return n;
    };
    let moved = false, preview = base;
    const move = ev => { const p = toWorld(ev.clientX, ev.clientY); moved = true; preview = nextBounds(p); setFrameDraft(preview); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      if (moved) mutateFloor(floor.id, f => ({ ...f, frame: preview })); setFrameDraft(null); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };

  // centre the view on the floor's content whenever the floor changes
  const viewAnim = useRef(0);
  const animateView = (to, animate) => {                      // the camera glides to the new framing; a touch or the wheel stops it at once
    cancelAnimationFrame(viewAnim.current);
    const from = view;
    if (!animate || planReduceMotion() || (Math.abs(from.k - to.k) < 1e-6 && Math.abs(from.x - to.x) < .5 && Math.abs(from.y - to.y) < .5)) { setView(to); return; }
    const t0 = performance.now(), ms = 520;
    const tick = now => { const p = Math.min(1, (now - t0) / ms), e = planEase(p);
      setView(p >= 1 ? to : { k: from.k + (to.k - from.k) * e, x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e });
      if (p < 1) viewAnim.current = requestAnimationFrame(tick); };
    viewAnim.current = requestAnimationFrame(tick);
  };
  useEffect(() => { const el = wrap.current, stop = () => cancelAnimationFrame(viewAnim.current); if (!el) return stop;
    el.addEventListener('pointerdown', stop, true); el.addEventListener('wheel', stop, { passive: true });
    return () => { stop(); el.removeEventListener('pointerdown', stop, true); el.removeEventListener('wheel', stop); }; }, []);
  const fitFloor = (animate = false) => { const xs = [], ys = [];
    const shown = overview ? sceneFloors : ghost ? sceneFloors.slice(0,floorIndex+1) : [floor];
    const b = planBounds(shown);
    const corners = [[b.x1, b.y1], [b.x2, b.y1], [b.x2, b.y2], [b.x1, b.y2]];
    const footprint = [[houseBounds.x1, houseBounds.y1], [houseBounds.x2, houseBounds.y1], [houseBounds.x2, houseBounds.y2], [houseBounds.x1, houseBounds.y2]].map(([x,y]) => isoPoint(x,y));
    footprint.forEach(p => { xs.push(p.x); ys.push(p.y - ISO_WALL); });
    shown.forEach(f => { const i = indoorFloors.findIndex(x => x.id === f.id), dy = overview || ghost ? (sceneIndex - i) * floorStep : 0;
      const fb = f.id === floor.id && frameDraft ? frameDraft : planFloorFrame(f, houseBounds);
      [[fb.x1,fb.y1],[fb.x2,fb.y1],[fb.x2,fb.y2],[fb.x1,fb.y2]].forEach(([x,y]) => { const p = isoPoint(x,y); xs.push(p.x); ys.push(p.y + dy, p.y + dy - ISO_WALL); });
      corners.forEach(([x, y]) => { const p = isoPoint(x, y); xs.push(p.x); ys.push(p.y + dy, p.y + dy - ISO_WALL); }); });
    const el = wrap.current; if (!el || !xs.length) return;
    const W = el.clientWidth, H = el.clientHeight, mobile = W < 760;
    const cardMargin = shown.some(f => (f.items || []).length) ? equipmentScale*.6*82+12 : 0;
    const inset = { left: Math.max(mobile ? 26 : 48,cardMargin), right: Math.max(mobile ? 82 : 100,cardMargin), top: 112, bottom: surveyVisible ? (mobile ? 265 : 235) : mobile ? 74 : 60 };
    if (surveyVisible && surveyOnFloor && surveyValid) {
      xs.length=0;ys.length=0;
      const r=surveyRoom,pad=Math.max(PG,Math.min(r.w,r.h)*.06);
      [[r.x-pad,r.y-pad],[r.x+r.w+pad,r.y-pad],[r.x+r.w+pad,r.y+r.h+pad],[r.x-pad,r.y+r.h+pad]].forEach(([x,y])=>{const p=isoPoint(x,y);xs.push(p.x);ys.push(p.y,p.y-ISO_WALL)});
    }
    const x1 = Math.min(...xs), x2 = Math.max(...xs), y1 = Math.min(...ys), y2 = Math.max(...ys);
    const width = Math.max(100,W-inset.left-inset.right), height = Math.max(120,H-inset.top-inset.bottom);
    const k = Math.max(.001,Math.min(1, width/Math.max(1,x2-x1), height/Math.max(1,y2-y1)) * (mobile ? .86 : .92));
    animateView({ k, x: inset.left+(width-(x2-x1)*k)/2-x1*k, y: inset.top+(height-(y2-y1)*k)/2-y1*k }, animate);
  };
  const fitFloorRef = useRef(fitFloor); fitFloorRef.current = fitFloor;
  const firstFit = useRef(true);
  useEffect(() => {
    const animate = !firstFit.current; firstFit.current = false;          // the very first framing is instant; later changes (floor, «Весь дом», обход) glide
    let timer, skip = true; const schedule = glide => { clearTimeout(timer); timer = setTimeout(() => fitFloorRef.current(glide), glide ? 0 : 60); };
    const resized = () => schedule(false);
    const observer = new ResizeObserver(() => { if (skip) { skip = false; return; } resized(); });       // observe() reports once at the start: that is not a resize
    if (wrap.current) observer.observe(wrap.current);
    window.addEventListener('orientationchange',resized); schedule(animate);
    return () => { clearTimeout(timer); observer.disconnect(); window.removeEventListener('orientationchange',resized); };
  }, [fid, building.id, ghost, overview, surveyVisible, survey?.roomId, surveyValid, surveyOnFloor]);

  const openPlanItem = async it => {
    if (deviceConfirmOpen.current) return;
    const d = devById[it.ref], place = data.racks.find(r => r.id === it.ref);
    const name = it.kind === 'place' ? place?.name : d?.name;
    if (!name) return;
    deviceConfirmOpen.current = true;
    try {
      if (!(await confirm(`Открыть «${name}»?`, { title: 'Открыть оборудование', ok: 'Открыть' }))) return;
      if (it.kind === 'place') openPlace(it.ref);
      else if (!d._topology) openDevice(d, undefined, undefined, true);
      else if (d._node?.childOf) { const parent = data.devices.find(x => x.id === d._node.childOf); if (parent) openDevice(parent, undefined, undefined, true); }
      else toast(`${d.name}${d.host ? ' · ' + d.host : ''}`);
    } finally { deviceConfirmOpen.current = false; }
  };
  const resizeRoom = (room, edge, e) => {
    if (placingPoint) return;
    if (!admin || !edit || tool !== 'select' || overview) return;
    e.stopPropagation(); e.preventDefault(); setSel('room:' + room.id);
    const pointer = e.pointerId, start = toWorld(e.clientX,e.clientY), floorId = floor.id;
    let preview = room, changed = false, blocked = false;
    const cleanup = () => { window.removeEventListener('pointermove',move); window.removeEventListener('pointerup',up); window.removeEventListener('pointercancel',cancel); };
    const move = ev => {
      if (ev.pointerId !== pointer) return;
      const p = toWorld(ev.clientX,ev.clientY), dx = p.x-start.x, dy = p.y-start.y;
      let l=room.x, t=room.y, r=room.x+room.w, b=room.y+room.h;
      if (edge.includes('l')) l=Math.min(snap(room.x+dx),r-PG*2);
      if (edge.includes('r')) r=Math.max(snap(room.x+room.w+dx),l+PG*2);
      if (edge.includes('t')) t=Math.min(snap(room.y+dy),b-PG*2);
      if (edge.includes('b')) b=Math.max(snap(room.y+room.h+dy),t+PG*2);
      const next={ ...room, x:l, y:t, w:r-l, h:b-t };
      if ((floor.rooms || []).some(other => other.id !== room.id && planRoomsOverlap(next,other))) { blocked=true; return; }
      blocked=false; preview=next; changed=['x','y','w','h'].some(k => next[k] !== room[k]);
      setRoomResize({floorId,id:room.id,rect:next});
    };
    const up = ev => { if (ev.pointerId !== pointer) return; cleanup();
      if (changed) mutateFloor(floorId,f => ({ ...f, rooms:(f.rooms || []).map(r => r.id === room.id ? preview : r) }));
      setRoomResize(null); if (blocked) toast('Комнаты не должны перекрываться',true);
    };
    const cancel = ev => { if (ev.pointerId !== pointer) return; cleanup(); setRoomResize(null); };
    window.addEventListener('pointermove',move); window.addEventListener('pointerup',up); window.addEventListener('pointercancel',cancel);
  };

  const dragItem = (it, e) => {
    if (placingPoint) return;                                // let the canvas place the measurement
    if (tool === 'erase') { e.stopPropagation(); confirmDelete('Убрать оборудование с плана?', () => changeItems(it, items => items.filter(x => x.id !== it.id))); return; }
    if (!edit) {
      if (e.pointerType === 'touch' && e.isPrimary === false) return;
      const pointer=e.pointerId, sx=e.clientX, sy=e.clientY; let moved=false, multi=false;
      const cleanup=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerdown',down);window.removeEventListener('pointerup',up);window.removeEventListener('pointercancel',cancel);};
      const move=ev=>{if(ev.pointerId===pointer && Math.hypot(ev.clientX-sx,ev.clientY-sy)>8)moved=true;};
      const down=ev=>{if(ev.pointerId!==pointer)multi=true;};
      const up=ev=>{if(ev.pointerId!==pointer)return;cleanup();if(!moved&&!multi)openPlanItem(it);};
      const cancel=ev=>{if(ev.pointerId===pointer)cleanup();};
      window.addEventListener('pointermove',move);window.addEventListener('pointerdown',down);window.addEventListener('pointerup',up);window.addEventListener('pointercancel',cancel);return;
    }
    if (tool !== 'select') return;
    e.stopPropagation(); const s = toWorld(e.clientX, e.clientY); const o = { x: it.x, y: it.y }; let moved = false;
    const move = ev => { const w = toWorld(ev.clientX, ev.clientY); moved = true; const p = { x: snap(o.x + w.x - s.x), y: snap(o.y + w.y - s.y) };
      changeItems(it, items => items.map(x => x.id === it.id ? { ...x, ...p, outdoor: x._originFloorId ? true : outsideFloorPoint(p, floor) } : x)); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) setSel(it.id); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const dragRoom = (rm, e) => {
    if (placingPoint) return;
    if (tool === 'erase') { e.stopPropagation(); confirmDelete(`Удалить комнату «${rm.text || 'Без названия'}»?`, () => mutate(f => ({ ...f, rooms: f.rooms.filter(x => x.id !== rm.id) }))); return; }
    if (!edit || tool !== 'select') return;
    e.stopPropagation(); setSel('room:' + rm.id); const s = toWorld(e.clientX, e.clientY); const o = { x: rm.x, y: rm.y }; let moved = false;
    const move = ev => { const w = toWorld(ev.clientX, ev.clientY); moved = true; const next = { ...rm, x: snap(o.x + w.x - s.x), y: snap(o.y + w.y - s.y) }; if ((floor.rooms || []).some(x => x.id !== rm.id && planRoomsOverlap(next,x))) return; mutate(f => ({ ...f, rooms: f.rooms.map(x => x.id === rm.id ? next : x) })); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) setSel('room:' + rm.id); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const removeSel = () => {
    if (!sel) return;
    const message = sel.startsWith('room:') ? 'Удалить выбранную комнату?' : sel.startsWith('wall:') ? 'Удалить выбранную стену?' : 'Убрать оборудование с плана?';
    return confirmDelete(message, () => {
      if (sel.startsWith('room:')) return mutate(f => ({ ...f, rooms: f.rooms.filter(r => 'room:' + r.id !== sel) }));
      if (sel.startsWith('wall:')) { const wi = Number(sel.slice(5)); return mutate(f => ({ ...f, walls: (f.walls || []).filter((_,j) => j !== wi) })); }
      const it = visibleItems.find(i => i.id === sel); if (it) return changeItems(it, items => items.filter(i => i.id !== it.id));
    });
  };

  const placedRefs = new Set(buildings.flatMap(b => b.floors).flatMap(f => f.items).filter(i => i.kind !== 'label').map(i => `${i.kind}:${i.ref}`));
  const allPalette = [...data.racks.map(r => ({ kind: 'place', ref: r.id, name: r.name, icon: (PLACE_KINDS[r.kind] || PLACE_KINDS.rack).icon,
      typeLabel: PLACE_KINDS[r.kind]?.label || PLACE_KINDS.rack.label, group: 'Места', search: `${r.name} ${r.kind}` })),
    ...networkDevices.map(d => ({ kind: 'device', ref: d.id, name: d.name, icon: d.kind, typeLabel: KIND_TEXT[d.kind] || d.kind,
      snapshot: d._topology ? { name: d.name, kind: d.kind, host: d.host || '' } : null,
      group: 'Устройства сети', search: `${d.name} ${d.kind} ${KIND_TEXT[d.kind] || d.kind} ${d.driver || ''} ${d.ip || ''} ${d.host || ''} ${d.mac || ''} ${d.kind === 'ap' ? 'точки доступа точка доступа access point' : ''}` }))]
    .map(x => ({ ...x, placed: placedRefs.has(`${x.kind}:${x.ref}`) }));
  const q = equipQuery.trim().toLowerCase();
  const palette = allPalette.filter(x => !q || `${x.search} ${x.typeLabel} ${x.group}`.toLowerCase().includes(q));
  return <div className="plan">
    <WorkMenu title={building.name}>
      <WorkSec title="Этаж">
        {indoorFloors.length > 1 ? <WorkSwitch icon="eye" label="Показать нижние этажи" on={ghost} onChange={setGhost} /> : null}
      </WorkSec>
      {admin ? <WorkSec title="Размер оборудования"><div className="plan-equipment-size row">
        <Btn size="sm" icon="minus" title="Уменьшить оборудование" disabled={equipmentScale <= .6} onClick={() => setEquipmentScale(equipmentScale-.2)} />
        <b aria-label="Масштаб оборудования">{Math.round(equipmentScale*100)}%</b>
        <Btn size="sm" icon="plus" title="Увеличить оборудование" disabled={equipmentScale >= 2.4} onClick={() => setEquipmentScale(equipmentScale+.2)} />
        <Btn size="sm" onClick={() => resetSize('equipmentScale')}>Сброс</Btn>
      </div></WorkSec> : null}
      <WorkSec title="Покрытие Wi-Fi">
        <WorkSwitch icon="wifi" label="Показать покрытие Wi-Fi" on={cov && !overview} onChange={value => { setCov(value); setSelTest(null); if (value) setOverview(false); }} />
        {admin ? <WorkItem icon="pin" label={survey ? 'Продолжить обход комнаты' : 'Обход комнаты · 5 точек'} onClick={()=>survey ? returnToSurvey() : setSurveyChoose(true)} /> : null}
        <div className="plan-coverage-settings">
          <label>Размер отметок<div className="plan-equipment-size row">
            <Btn size="sm" icon="minus" title="Уменьшить отметки" disabled={coverageMarkerScale <= .2} onClick={() => setCoverageMarkerScale(coverageMarkerScale-.1)} />
            <b aria-label="Размер отметок">{Math.round(coverageMarkerScale*100)}%</b>
            <Btn size="sm" icon="plus" title="Увеличить отметки" disabled={coverageMarkerScale >= 1} onClick={() => setCoverageMarkerScale(coverageMarkerScale+.1)} />
            <Btn size="sm" onClick={() => resetSize('coverageMarkerScale')}>Сброс</Btn>
          </div></label>
          <label>Показатель<select className="select" aria-label="Показатель покрытия" value={covMode} onChange={e=>{setCovMode(e.target.value);setSelTest(null)}}>
            <option value="auto">Авто · сигнал при наличии</option><option value="signal">Сигнал · дБм</option><option value="speed">Скорость · Мбит/с</option>
          </select></label>
          {coverageSources.length ? <label>Точка доступа и диапазон<select className="select" aria-label="Источник покрытия" value={coverageSource} onChange={e=>{setCovSource(e.target.value);setSelTest(null)}}>
            {coverageSources.map(g=><option key={g.id} value={g.id}>{g.label}</option>)}
          </select></label> : null}
        </div>
        <div className="dim" style={{ fontSize: 12, padding: '0 10px 8px' }}>
          {tests.length ? <div>На этаже: {tests.length} · в выбранной карте: {coverageTests.length} · мест с данными: {coverageData.samples.length}</div> : null}
          {coverageHint}
        </div>
      </WorkSec>
      <WorkSec title="План дома"><WorkItem icon="chevronLeft" label="Все дома" onClick={back} /></WorkSec>
    </WorkMenu>
    <div className={'plan-canvas' + (tool !== 'select' || placingPoint ? ' crosshair' : '')} ref={wrap} {...bind}>
      <svg>
        <defs><pattern id="pgridB" width={PG} height={PG} patternUnits="userSpaceOnUse" patternTransform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <circle cx={1} cy={1} r={.8} fill="var(--line)" /></pattern></defs>
        <rect x={0} y={0} width="100%" height="100%" fill="var(--bg2)" />
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <PlanIsoScene floors={sceneFloors} activeId={overview ? indoorFloors[indoorFloors.length-1].id : floor.id} activeIndex={sceneIndex} bounds={sceneBounds} houseBounds={houseBounds} ghost={ghost} planeRef={planeRef}
            draft={draft} tool={tool} edit={edit && !overview} cov={cov && !overview} tests={coverageTests} coverageData={coverageData} coverageMetric={coverageMetric} selTest={selTest} setSelTest={setSelTest} placingPoint={placingPoint}
            survey={surveyVisible && surveyOnFloor && surveyValid && !pinTest ? survey : null}
            devById={devById} racks={data.racks} sel={sel} dragRoom={dragRoom} dragItem={dragItem} wrap={wrap} view={view} wallPt={wallPt}
            admin={admin} frameDraft={frameDraft} resizeFloor={resizeFloor} projection={projection} overview={overview} equipmentScale={equipmentScale} coverageMarkerScale={coverageMarkerScale} floorStep={floorStep} anim={anim} resizeRoom={resizeRoom} icons={data.icons || {}} />
        </g>
      </svg>
      <div className="plan-ctx plan-ovl"><Btn size="sm" icon="chevronLeft" onClick={back}>Все дома</Btn><b className="ellipsis">{building.name}</b>
        <Btn size="sm" icon="home" kind={overview ? 'primary' : ''} onClick={() => { setOverview(v => !v); setTool('select'); setPending(null); setWallPt(null); setSel(null); }}>{overview ? 'К этажу' : 'Весь дом'}</Btn>
      </div>
      {indoorFloors.length > 1 ? <div className="plan-floors plan-ovl"><label className="plan-floor-picker"><Icon name="home" size={16} /><span>Этаж</span>
        <select aria-label="Выбрать этаж" value={overview ? '' : floor.id} onChange={e => { setOverview(false); setFid(e.target.value); setSel(null); }}>
          {overview ? <option value="" disabled>Общий вид</option> : null}
          {indoorFloors.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select></label></div> : null}
      {admin && edit ? <div className="plan-tool-current plan-ovl"><Icon name={tool === 'select' ? 'cursor' : tool === 'room' ? 'tag' : tool === 'wall' ? 'wall' : tool === 'place' ? 'plus' : 'eraser'} size={14} />
        {overview ? 'Общий вид дома' : 'Инструмент: ' + ({ select: 'Выбрать / двигать', room: 'Комната', wall: 'Стена', place: 'Оборудование', erase: 'Удаление' })[tool]}</div> : null}
      <div className="plan-edit-dock plan-ovl">
        {editOpen ? <div className="plan-edit-panel card pad">
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}><b>Инструменты плана</b><button className="icon-btn" title="Закрыть" onClick={() => setEditOpen(false)}><Icon name="x" size={16} /></button></div>
          {admin && edit ? <>
              <div className="plan-tool-grid" aria-label="Инструменты редактирования">
                {[['select','Выбрать / двигать','cursor'],['room','Комната','tag'],['wall','Стена','wall'],['place','Оборудование','plus'],['erase','Удалить','eraser']].map(([v,label,icon]) =>
                  <button key={v} className={'chip' + (!overview && tool === v ? ' on' : '')} onClick={() => { setOverview(false); setTool(v); setWallPt(null); setPending(null); }}><Icon name={icon} size={15} />{label}</button>)}
              </div>
              <div className="plan-tool-status"><Icon name={tool === 'select' ? 'cursor' : tool === 'room' ? 'tag' : tool === 'wall' ? 'wall' : tool === 'place' ? 'plus' : 'eraser'} size={14} />
                Сейчас: {({ select: 'Выбрать / двигать', room: 'Комната', wall: 'Стена', place: 'Оборудование', erase: 'Удаление' })[tool]}</div>
              {!overview ? <div className="row wrap" style={{ marginTop: 8 }}>
                <Btn size="sm" icon="plus" onClick={addFloor}>Добавить этаж</Btn>
                {indoorFloors.length > 1 ? <Btn size="sm" icon="trash" kind="danger" onClick={delFloor}>Удалить этаж</Btn> : null}
                {floor.frame ? <Btn size="sm" icon="fit" onClick={resetFloorFrame}>Сбросить размер этажа</Btn> : null}
                {tool === 'wall' && wallPt ? <Btn size="sm" icon="check" onClick={() => setWallPt(null)}>Готово со стеной</Btn> : null}
                {sel ? <Btn size="sm" icon="trash" kind="danger" onClick={removeSel}>{sel.startsWith('wall:') ? 'Удалить стену' : sel.startsWith('room:') ? 'Удалить комнату' : 'Удалить выбранное'}</Btn> : null}
              </div> : null}
              {tool === 'place' ? <div className="plan-equip-list">
                <div className="dim" style={{ fontSize: 12, margin: '8px 0 5px' }}>{pending ? 'Нажмите на место установки' : 'Все устройства и места сети'}</div>
                <input className="input plan-equip-search" value={equipQuery} onChange={e => setEquipQuery(e.target.value)} placeholder="Найти устройство или точку доступа" />
                {palette.map(p => <button key={p.kind + ':' + p.ref} className={'plan-equip-option' + (pending && pending.ref === p.ref && pending.kind === p.kind ? ' on' : '')} onClick={() => { setPending(p); setEditOpen(false); }}>
                  <Icon name={p.icon} size={19} /><span className="plan-equip-copy"><b>{p.name}</b><small>{p.typeLabel} · {p.group}{p.placed ? ' · уже на плане, переместить' : ''}</small></span></button>)}
                {!palette.length ? <div className="dim" style={{ fontSize: 12 }}>{allPalette.length ? 'Ничего не найдено.' : 'В сети пока нет оборудования.'}</div> : null}
                {pending ? <div className="dim" style={{ fontSize: 11, marginTop: 5 }}>Можно поставить за пределами стен, на участке.</div> : null}
              </div> : null}
          </> : <div className="dim" style={{ fontSize: 12, marginTop: 8 }}>Переключатели этажей и редактирования находятся в меню вверху.</div>}
        </div> : null}
        <button className={'plan-edit-fab' + (editOpen ? ' on' : '')} aria-label="Инструменты плана" title="Инструменты плана" onClick={() => setEditOpen(!editOpen)}>
          <Icon name={editOpen ? 'x' : 'plus'} size={23} stroke={2.4} />
        </button>
      </div>
      {cov && !overview && selTest && coverageTests.find(t => t.id === selTest) ? (() => { const t = coverageTests.find(x => x.id === selTest);
        return <div className="plan-testcard plan-ovl"><Card title={t.note || 'Замер скорости'} right={<Btn size="sm" icon="x" onClick={() => setSelTest(null)} />}>
          <div className="list"><SpeedRow t={t} now={data.now} /></div>
          {admin ? <div className="row wrap" style={{ marginTop: 8 }}>
            <Btn size="sm" icon="pin" onClick={() => { setPinTest(t.id); setSelTest(null); }}>Переставить</Btn>
            <Btn size="sm" kind="danger" icon="trash" onClick={() => { pinAt(t.id, null); setSelTest(null); }}>Убрать с плана</Btn></div> : null}
        </Card></div>; })() : null}
      {edit && !overview && tool === 'place' && pending ? <div className="plan-placement-prompt plan-ovl">
        <span className="ellipsis">Куда поставить «{pending.name}»?</span><Btn size="sm" icon="x" onClick={() => { setPending(null); setTool('select'); }}>Отмена</Btn>
      </div> : null}
      {surveyVisible && !pinTest ? <div className="plan-survey-card plan-ovl" role="region" aria-label="Обход комнаты">
        <div className="plan-survey-head"><span className="plan-survey-badge"><Icon name="wifi" size={18} /></span><div className="grow"><small>ОБХОД КОМНАТЫ</small><b>{survey.roomName}</b></div>
          <button className="plan-survey-close" aria-label="Свернуть обход" onClick={()=>{setSurveyHidden(true);setSurveyPicking(false)}}><Icon name="x" size={17} /></button></div>
        <div className="plan-survey-progress" aria-label="Прогресс обхода">{survey.points.map((p,i)=><button key={i} className={(p.testId?'done ':'')+(survey.index===i?'current':'')} aria-label={'Точка обхода '+(i+1)} aria-current={survey.index===i?'step':undefined}
          disabled={surveySaving || !surveyValid || !surveyOnFloor || !!survey.pendingTest} onClick={()=>{setSurvey(s=>({...s,index:i}));setSurveyPicking(false)}}>{i+1}</button>)}</div>
        {!surveyValid ? <><p>Комната изменилась. Построим новый маршрут; сохранённые замеры останутся.</p><Btn size="sm" onClick={()=>{setSurvey(null);setSurveyPicking(false);setSurveyChoose(true)}}>Выбрать комнату</Btn></> :
          !surveyOnFloor ? <><p>Маршрут находится на этаже «{surveyFloor.name}».</p><Btn kind="primary" onClick={returnToSurvey}>Вернуться к обходу</Btn></> :
          survey.index>=5 ? <><p><b>Все 5 точек сохранены</b><br />{surveySources.size>1 ? 'Точка доступа или диапазон менялись — результаты находятся в разных картах.' : 'Посмотрите карту или повторите любую точку, нажав её номер.'}</p>
            <div className="row wrap"><Btn size="sm" kind="primary" onClick={()=>{setSurveyChoose(true);setSurveyPicking(false)}}>Другая комната</Btn><Btn size="sm" onClick={()=>{setSurvey(null);setSurveyPicking(false)}}>Закончить</Btn></div></> :
          <><p><b>{surveyPicking ? 'Укажите, где сможете встать' : survey.pendingTest ? 'Замер готов к сохранению' : 'Подойдите к точке '+(survey.index+1)+' из 5'}</b><br />
            {surveyPicking ? 'Нажмите внутри этой комнаты. Затем подойдите туда для замера.' : survey.pendingTest ? 'Подтвердите: во время замера вы стояли у подсвеченной отметки.' : 'Подсвеченная отметка — ваше место. Во время замера постойте спокойно.'}</p>
            {surveySourceChanged ? <div className="plan-survey-warning">Точка доступа или диапазон изменились — этот замер попадёт в другую карту.</div> : null}
            {survey.pendingTest && coverageValue(survey.pendingTest,'signal')==null ? <div className="plan-survey-note">Сигнал недоступен: сохранится скорость. Для сигнала откройте локальный адрес NAS.</div> : null}
            <div className="row wrap">{surveyPicking ? <Btn size="sm" onClick={()=>setSurveyPicking(false)}>Отмена</Btn> : survey.pendingTest ? <>
              <Btn size="sm" kind="primary" busy={surveySaving} disabled={surveySaving} onClick={()=>saveSurveyPoint(survey.pendingTest)}>Сохранить эту точку</Btn>
              <Btn size="sm" disabled={surveySaving} onClick={()=>setSurvey(s=>({...s,pendingTest:null}))}>Повторить замер</Btn></> : <>
              <Btn size="sm" kind="primary" icon="gauge" onClick={()=>{setPinTest(null);setSurveyMeasuring(true)}}>Я на месте · измерить</Btn>
              <Btn size="sm" onClick={()=>{setSurveyPicking(true);setTool('select');setSel(null);setSelTest(null)}}>Уточнить место</Btn></>}</div>
          </>}
        <div className="plan-survey-foot">{survey.points.filter(p=>p.testId).length} из 5 сохранено · прогресс в этой вкладке
          {survey.index<5 ? <button className="plan-survey-end" disabled={surveySaving} onClick={async()=>{if(await confirm('Завершить обход? Сохранённые замеры останутся; новый маршрут можно начать позже.',{ok:'Завершить'})){setSurvey(null);setSurveyPicking(false)}}}>Завершить обход</button> : null}</div>
      </div> : null}
      {edit && !overview && !(tool === 'place') && !placingPoint && !surveyVisible ? <div className="plan-hint plan-ovl">{tool === 'wall' ? 'Нажимайте на план, чтобы провести стену · затем нажмите «Готово со стеной»' : tool === 'room' ? 'Обведите прямоугольник комнаты' :
        tool === 'select' ? (sel?.startsWith('room:') ? 'Комната выбрана · тяните за углы или края, чтобы изменить размер' : 'Перетаскивайте оборудование и комнаты. Потяните угловые точки пола, чтобы изменить его размер.') :
        tool === 'erase' ? 'Нажмите на стену, комнату или устройство' : 'Перетаскивайте объекты · оборудование можно ставить снаружи'}</div> : null}
      <ZoomBtns setView={setView} onFit={fitFloor} />
    </div>
    {surveyChoose ? <Modal title="Обход комнаты" icon={<Icon name="wifi" size={21} color="var(--accent)" />} onClose={()=>setSurveyChoose(false)}>
      <div className="survey-intro"><b>Пять точек для понятной карты</b><p>Выберите комнату. Покажем маршрут у четырёх углов и в центре, поможем сделать замеры и сохранить их на нужных местах.</p>
        <span className="dim">Если к отметке нельзя подойти, уточните её место перед замером. Используйте один телефон.</span></div>
      <div className="plan-survey-note">{surveyConnection?.proxy || surveyConnection?.nat ? 'Сейчас телефон не определяется: получится карта скорости. Для карты сигнала откройте локальный адрес NAS.' : 'Для карты сигнала нужен локальный адрес NAS и определение телефона роутером. Если сигнал недоступен, покажем скорость.'}</div>
      <div className="survey-room-list">{(floor.rooms||[]).map((r,i)=><button className="survey-room-choice" key={r.id} onClick={()=>startSurvey(r)}><Icon name="home" size={21} /><span><b>{r.text||'Комната '+(i+1)}</b><small>{floor.name} · 5 точек</small></span><Icon name="chevronRight" size={18}/></button>)}</div>
      {!(floor.rooms||[]).length ? <div className="dim">На этом этаже ещё нет комнат. Добавьте комнату или выберите другой этаж.</div> : null}
    </Modal> : null}
    {surveyMeasuring && survey && surveyValid && survey.index<5 ? <SpeedTestModal autoRun survey={{name:survey.roomName,step:survey.index+1,source:survey.points.find(p=>p.testId)?.source}} onSurveyMeasured={surveyMeasured} onSurveySave={saveSurveyPoint} onClose={()=>setSurveyMeasuring(false)} /> : null}
    {roomEditor ? <Modal title="Новая комната" onClose={() => setRoomEditor(null)}>
      <form onSubmit={saveRoom}>
        <Field label="Название комнаты"><input className="input" aria-label="Название комнаты" autoFocus required maxLength={80} value={roomEditor.name}
          onChange={e => setRoomEditor(r => ({ ...r, name: e.target.value }))} /></Field>
        <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
          <Btn onClick={() => setRoomEditor(null)}>Отмена</Btn><Btn kind="primary" type="submit" icon="check">Создать комнату</Btn>
        </div>
      </form>
    </Modal> : null}
  </div>;
}

function PlanIsoScene({ floors, activeId, activeIndex, bounds, houseBounds, ghost, planeRef, draft, tool, edit, cov, tests, coverageData, coverageMetric, selTest, setSelTest, placingPoint, survey,
  devById, racks, sel, dragRoom, dragItem, wrap, view, wallPt, admin, frameDraft, resizeFloor, projection, overview, equipmentScale, coverageMarkerScale, floorStep, anim, resizeRoom, icons }) {
  const { a, b, c, d } = projection;
  const isoPoint = (x,y) => ({ x: a*x + c*y, y: b*x + d*y });
  const isoPoly = pts => pts.map(([x,y]) => { const p = isoPoint(x,y); return `${p.x},${p.y}`; }).join(' ');
  const corners = [[bounds.x1, bounds.y1], [bounds.x2, bounds.y1], [bounds.x2, bounds.y2], [bounds.x1, bounds.y2]];
  const ground = corners.map(([x, y]) => isoPoint(x, y));
  const shellBounds = floors.reduce((b,f) => { const q = planFloorFrame(f,houseBounds); return { x1: Math.min(b.x1,q.x1), y1: Math.min(b.y1,q.y1), x2: Math.max(b.x2,q.x2), y2: Math.max(b.y2,q.y2) }; },houseBounds);
  // while a change of view is gliding, every number comes from `anim` (floor spacing, how many floors up, wall height, who is faded in); at rest they equal the targets
  const aIdx = anim ? anim.idx : activeIndex, aStep = anim ? anim.step : floorStep, aWall = anim ? anim.wall : (overview ? 72 : ISO_WALL);
  const alphaOf = f => anim ? (anim['o' + f.id] ?? 0) : overview ? (f.id === activeId ? 1 : .9) : f.id === activeId ? 1 : .46;
  const shellA = anim ? anim.shell : overview ? 1 : 0, groundA = anim ? anim.ground : (overview || ghost || activeIndex === 0 ? 1 : 0);
  const houseCorners = [[shellBounds.x1, shellBounds.y1], [shellBounds.x2, shellBounds.y1], [shellBounds.x2, shellBounds.y2], [shellBounds.x1, shellBounds.y2]];
  const top = houseCorners.map(([x, y]) => isoPoint(x, y));
  const cutWallHeight = aWall;
  const wallFace = w => { const a = isoPoint(w.x1, w.y1), b = isoPoint(w.x2, w.y2);
    return `${a.x},${a.y} ${b.x},${b.y} ${b.x},${b.y - cutWallHeight} ${a.x},${a.y - cutWallHeight}`; };
  const roomPoints = r => isoPoly([[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]]);
  const draftPoints = draft && isoPoly([[draft.x, draft.y], [draft.x + draft.w, draft.y], [draft.x + draft.w, draft.y + draft.h], [draft.x, draft.y + draft.h]]);
  const visibleFloors = (anim ? floors.filter(f => alphaOf(f) > .01) : overview ? floors : ghost ? floors.slice(0,activeIndex+1) : floors.filter(f => f.id === activeId)).slice().sort((a,b) => floors.indexOf(a)-floors.indexOf(b));
  const groundDy = aIdx * aStep + ISO_SLAB;
  return <g className={'plan-iso-scene' + (overview ? ' overview' : '')}>
    <defs>
      <linearGradient id="plan-wall-matte" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox">
        <stop offset="0" stopColor="var(--plan-wall-active)" /><stop offset="1" stopColor="var(--plan-wall-shade)" />
      </linearGradient>
      <linearGradient id="plan-wall-matte-side" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox">
        <stop offset="0" stopColor="var(--plan-wall-shade)" /><stop offset="1" stopColor="var(--plan-wall-edge)" />
      </linearGradient>
    </defs>
    {groundA > .01 ? <polygon points={ground.map(p => `${p.x},${p.y + groundDy}`).join(' ')} className="plan-iso-ground" opacity={groundA} /> : null}
    {shellA > .01 ? <g className="plan-building-shell" pointerEvents="none" opacity={shellA}>
      {[[top[0],top[1]],[top[3],top[0]]].map(([p,q],k) => <g key={k}>
        <polygon points={`${p.x},${p.y-ISO_WALL} ${q.x},${q.y-ISO_WALL} ${q.x},${q.y+groundDy} ${p.x},${p.y+groundDy}`} className={'plan-building-facade side-'+k} />
        {floors.map((f,i) => { const y = (aIdx-i)*aStep+ISO_SLAB; return <line key={f.id} x1={p.x} y1={p.y+y} x2={q.x} y2={q.y+y} className="plan-building-seam" />; })}
      </g>)}
    </g> : null}
    {visibleFloors.map(f => { const i = floors.findIndex(x => x.id === f.id), active = f.id === activeId, dy = (aIdx - i) * aStep;
      const frame = active && frameDraft ? frameDraft : planFloorFrame(f, houseBounds);
      const ft = [[frame.x1,frame.y1],[frame.x2,frame.y1],[frame.x2,frame.y2],[frame.x1,frame.y2]].map(([x,y]) => isoPoint(x,y));
      const fBottom = ft.map((p,k) => [p,ft[(k+1)%4]]);
      const fRooms = f.rooms || [], fWalls = f.walls || [], fItems = f.items || [];
      const walls3d = fWalls.length ? fWalls : fRooms.flatMap(r => [
        { x1: r.x, y1: r.y, x2: r.x + r.w, y2: r.y }, { x1: r.x + r.w, y1: r.y, x2: r.x + r.w, y2: r.y + r.h },
        { x1: r.x + r.w, y1: r.y + r.h, x2: r.x, y2: r.y + r.h }, { x1: r.x, y1: r.y + r.h, x2: r.x, y2: r.y }
      ]);
      return <g key={f.id} data-floor-id={f.id} transform={`translate(0,${dy})`} opacity={alphaOf(f)} pointerEvents={!overview && active ? 'auto' : 'none'} className={active ? 'plan-iso-level active' : 'plan-iso-level'}>
        {fBottom.map((edge, k) => <polygon key={k} points={`${edge[0].x},${edge[0].y + ISO_SLAB} ${edge[1].x},${edge[1].y + ISO_SLAB} ${edge[1].x},${edge[1].y} ${edge[0].x},${edge[0].y}`}
          className="plan-iso-slab-side" />)}
        <polygon points={ft.map(p => `${p.x},${p.y}`).join(' ')} className="plan-iso-slab" />
        {fRooms.map(r => { const rc = r.color || '#0a84ff', p = isoPoint(r.x + r.w / 2, r.y + r.h / 2);
          return <g key={r.id} className={'plan-room plan-iso-room' + (active && sel === 'room:' + r.id ? ' sel' : '')}
            onPointerDown={active ? e => dragRoom(r, e) : undefined} style={{ cursor: active && edit && tool === 'select' ? 'move' : active && tool === 'erase' ? 'pointer' : 'default' }}>
            <polygon points={roomPoints(r)} className="pr-fill" style={{ fill: `color-mix(in srgb, ${rc} ${active ? 32 : 18}%, var(--bg2))`, stroke: rc }} />
            {r.text ? <text x={p.x} y={p.y + 4} className="plan-iso-label" textAnchor="middle">{r.text}</text> : null}
          </g>; })}
        {active && cov && tests.length ? <g transform={`matrix(${a} ${b} ${c} ${d} 0 0)`}><CoverageSurface mesh={coverageData} metric={coverageMetric} /></g> : null}
        {walls3d.map((w,wi) => ({w,wi})).sort((a,b) => isoPoint(a.w.x1+a.w.x2,a.w.y1+a.w.y2).y-isoPoint(b.w.x1+b.w.x2,b.w.y1+b.w.y2).y).map(({w,wi}) => <g key={wi} data-wall-side={Math.abs(w.x2-w.x1) >= Math.abs(w.y2-w.y1) ? 'x' : 'y'} data-plan-wall={wi < fWalls.length ? wi : undefined} className={'plan-iso-wall' + (active && sel === 'wall:' + wi ? ' selected' : '')}>
          <polygon points={wallFace(w)} className="plan-iso-wall-face" />
          {(() => { const a = isoPoint(w.x1, w.y1), b = isoPoint(w.x2, w.y2); return <>
            <line x1={a.x} y1={a.y - cutWallHeight} x2={b.x} y2={b.y - cutWallHeight} className="plan-iso-wall-top" />
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="plan-iso-wall-base" />
          </>; })()}
        </g>)}
        {active && draft ? <polygon points={draftPoints} className={tool === 'erase' ? 'plan-erase-draft' : 'plan-room-draft'} /> : null}
        {fItems.map(it => { const p = isoPoint(it.x, it.y); return <g key={it.id} transform={`translate(${p.x - it.x},${p.y - it.y})`}>
          <PlanItem it={it} devById={devById} racks={racks} sel={active && sel === it.id} edit={edit} scale={equipmentScale*Math.max(1,.6/view.k)} icons={icons} onDown={active ? e => dragItem(it, e) : undefined} />
        </g>; })}
        {active && cov && tests.length ? <g transform={`matrix(${a} ${b} ${c} ${d} 0 0)`}><CoverageLayer tests={tests} mesh={coverageData} metric={coverageMetric} sel={selTest} onSel={setSelTest} placing={placingPoint} view={view} projection={projection} markerScale={coverageMarkerScale} /></g> : null}
        {active && survey ? <g className="plan-survey-route" pointerEvents="none">
          <polyline points={survey.points.map(p=>{const q=isoPoint(p.x,p.y);return q.x+','+q.y}).join(' ')} fill="none" stroke="var(--accent)" opacity=".45" strokeWidth={2/view.k} strokeDasharray={`${6/view.k} ${6/view.k}`} />
          {survey.points.map((p,i)=>{const q=isoPoint(p.x,p.y);return <g key={i} className={'plan-survey-stop'+(i===survey.index?' current':'')+(p.testId?' done':'')} data-survey-stop={i} transform={`translate(${q.x},${q.y}) scale(${1/view.k})`}>
            {i===survey.index?<circle className="plan-survey-halo" r={24}/>:null}<circle className="plan-survey-dot" r={14}/><text y={4.5} textAnchor="middle">{p.testId?'✓':i+1}</text></g>})}
        </g> : null}
        {active && admin && edit && tool === 'select' && sel?.startsWith('room:') ? (() => {
          const room=fRooms.find(r => sel === 'room:' + r.id); if (!room) return null;
          const x=room.x,y=room.y,w=room.w,h=room.h;
          const handles=[[x,y,'lt'],[x+w/2,y,'t'],[x+w,y,'rt'],[x+w,y+h/2,'r'],[x+w,y+h,'rb'],[x+w/2,y+h,'b'],[x,y+h,'lb'],[x,y+h/2,'l']];
          return <g className="plan-room-selection" data-selected-room={room.id}>
            <polygon points={roomPoints(room)} className="plan-room-selection-ring" strokeWidth={3/view.k} strokeDasharray={`${6/view.k} ${4/view.k}`} pointerEvents="none" />
            {handles.map(([hx,hy,edge]) => { const p=isoPoint(hx,hy); return <g key={edge} className="plan-room-resize-handle" data-room-edge={edge} onPointerDown={e => resizeRoom(room,edge,e)}>
              <circle cx={p.x} cy={p.y} r={22/view.k} fill="transparent" pointerEvents="all" />
              <circle cx={p.x} cy={p.y} r={(edge.length===2?9:7.5)/view.k} className="plan-room-resize-dot" strokeWidth={2/view.k} pointerEvents="none" />
            </g>; })}
          </g>;
        })() : null}
        {active && admin && edit && tool === 'select' && !sel?.startsWith('room:') ? ft.map((p,k) => <g key={k} className="plan-floor-resize" onPointerDown={e => resizeFloor(['lt','rt','rb','lb'][k], e)}>
          <circle cx={p.x} cy={p.y} r={24/view.k} className="plan-floor-handle" style={{ strokeWidth: 3/view.k }} />
          <text x={p.x} y={p.y} textAnchor="middle" dominantBaseline="central" style={{ fontSize: 25/view.k, fill: '#fff', pointerEvents: 'none' }}>↔</text>
        </g>) : null}
        {ghost ? <text x={ft[0].x} y={ft[0].y - 20} className="plan-iso-level-name">{f.name}</text> : null}
        {active ? <g ref={planeRef} transform={`matrix(${a} ${b} ${c} ${d} 0 0)`} pointerEvents="none">
          <rect x={bounds.x1} y={bounds.y1} width={bounds.x2 - bounds.x1} height={bounds.y2 - bounds.y1} fill="transparent" />
          {edit ? <PlanCursor wrap={wrap} view={view} tool={tool} wallPt={wallPt} planeRef={planeRef} /> : null}
        </g> : null}
      </g>;
    })}
  </g>;
}

function PlanItem({ it, devById, racks, sel, edit, onDown, scale = 1, icons = {} }) {
  if (it.kind === 'label') return <g className="plan-item plan-label" transform={`translate(${it.x},${it.y})`} onPointerDown={onDown}>
    <text textAnchor="middle" className={sel ? 'sel' : ''}>{it.text}</text></g>;
  const isPlace = it.kind === 'place';
  const ref = isPlace ? racks.find(r => r.id === it.ref) : devById[it.ref];
  const name = ref ? ref.name : '—';
  const kind = isPlace ? (ref ? (PLACE_KINDS[ref.kind] || PLACE_KINDS.rack).icon : 'rack') : (ref ? ref.kind : 'other');
  const status = isPlace ? (ref ? placeStatus(ref, devById) : '') : (ref && ref.state ? ref.state.status : '');
  const col = THEME.kindColors[kind] || (document.documentElement.getAttribute('data-look') === 'test' ? (KIND_COLOR[kind] || 'var(--accent)') : kindColor(kind));
  return <g className={'plan-item' + (sel ? ' sel' : '') + (it.outdoor ? ' outdoor' : '')} transform={`translate(${it.x},${it.y}) scale(${scale})`} onPointerDown={onDown} style={{ cursor: edit ? 'move' : 'pointer' }}>
    <title>{name}</title>
    <rect x={-82} y={-31} width={164} height={62} rx={12} className="pi-bg" />
    <rect x={-73} y={-22} width={44} height={44} rx={9} className="pi-core" style={{ fill: `color-mix(in srgb, ${col} 16%, var(--card-solid))` }} />
    <g className="pi-glyph" transform="translate(-67,-16)"><NodeGlyph svg spec={icons[it.ref] || icons['d:' + it.ref]} kind={kind} size={32} color={col} /></g>
    {status ? <circle cx={69} cy={-19} r={5} fill={statusColor(status)} stroke="var(--card-solid)" strokeWidth={2} /> : null}
    <text className="pi-label" x={-19} y={-2}>{name.length > 13 ? name.slice(0,12) + '…' : name}</text>
    <text className="pi-type" x={-19} y={15}>{isPlace ? (PLACE_KINDS[ref?.kind] || PLACE_KINDS.rack).label : KIND_TEXT[kind] || 'Устройство'}</text>
    {it.outdoor ? <text className="pi-outdoor" y={45} textAnchor="middle">УЛИЦА</text> : null}
  </g>;
}
