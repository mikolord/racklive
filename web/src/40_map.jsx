/* Network map: the rack in the middle, cables from its units to everything else. */
const M = { NW: 214, NH: 56, CW: 196, CH: 46, COL: 130, GAP: 12, RW: 310, RU: 38, MT: 150, MTH: 48 };     // MT×MTH: a box tile

function layoutMap(data, collapsed) {
  const topo = data.topology || { nodes: [], edges: [] };
  const nodes = {}; topo.nodes.forEach(n => nodes[n.id] = { ...n });
  const tree = topo.edges.filter(e => !e.extra && !e.manual && nodes[e.source] && nodes[e.target]).map(e => ({ ...e }));
  const parentEdge = {}; const kids = {};
  tree.forEach(e => { parentEdge[e.target] = e; (kids[e.source] = kids[e.source] || []).push(e); });

  // racks and boxes stacked on the left, each in its own frame; rooms have no frame — their devices are ordinary nodes (a star, like UniFi)
  const racks = data.racks || [];
  const rackMeta = {}; let ry = 0;
  const pos = {}; const rackNode = {};
  const nidOf = (u, did) => did ? 'd:' + did : 'u:' + u.id;          // u: — a unit without a device still on the map (the ONT)
  const rooms = [];                                                  // rooms: no frame — kept for «Шкафы и места» (highlight their devices)
  // a device linked in several places is drawn where it is listed first (racks before boxes); elsewhere it is a dimmed copy
  racks.forEach(r => {
    const kind = r.kind || 'rack';
    if (kind === 'place') {                                          // a room: no box; its devices get a room tag and are laid out like the rest
      const ids = [];
      r.units.forEach(u => unitDevIds(u).forEach(did => { if (nodes['d:' + did]) { ids.push('d:' + did); if (!nodes['d:' + did].room) nodes['d:' + did].room = r.name; } }));
      rooms.push({ id: r.id, name: r.name, ids, units: r.units.length });
      return;
    }
    if (kind === 'rack') {
      const h = r.totalU * M.RU;
      rackMeta[r.id] = { id: r.id, name: r.name, kind, isRack: true, total: r.totalU, rows: r.totalU, y: ry, w: M.RW, h, units: r.units };
      r.units.forEach(u => {
        if ((u.side || 'front') === 'back') return;                 // back-side units aren't drawn on the map
        const ids = unitDevIds(u); const list = ids.length ? ids : [null];
        const cw = (M.RW - (list.length - 1) * 4) / list.length;      // a shelf with several devices: one cell each
        list.forEach((did, k) => { const nid = nidOf(u, did); if (!nodes[nid] || rackNode[nid]) return;
          rackNode[nid] = { ...u, rackId: r.id };
          pos[nid] = { x: k * (cw + 4), y: ry + (u.uStart - 1) * M.RU, w: cw, h: u.uSize * M.RU - 4, rack: true, rackId: r.id }; });
      });
      ry += h + 92; return;
    }
    // a box (щиток): tiles where they stand in «Размещение» (its grid scaled down), the frame as big as they need
    const tiles = []; let auto = 0;
    r.units.forEach(u => { const ids = unitDevIds(u); (ids.length ? ids : [null]).forEach(did => {
      const nid = nidOf(u, did);                                   // every tile, linked or not — as in «Размещение»
      let c, rw;
      if (typeof u.x === 'number' && typeof u.y === 'number' && ids.length <= 1) { c = Math.round(u.x / 226); rw = Math.round(u.y / 76); }
      else { c = auto % 2; rw = 100 + Math.floor(auto / 2); auto++; }
      tiles.push({ u, nid: nodes[nid] ? nid : null, c, r: rw }); }); });
    if (!tiles.length) return;                                       // an empty box: nothing to draw on the map
    const rowsUsed = [...new Set(tiles.map(t => t.r))].sort((a, b) => a - b);      // pack: no empty rows between
    tiles.forEach(t => { t.r = rowsUsed.indexOf(t.r); });
    const cols = Math.max(1, ...tiles.map(t => t.c + 1)), rows = Math.max(1, rowsUsed.length);
    const w = Math.max(M.MT * 2 + 10, cols * (M.MT + 10) - 10), h = rows * (M.MTH + 10) - 10;
    tiles.forEach(t => { t.x = t.c * (M.MT + 10); t.y = t.r * (M.MTH + 10);
      if (t.nid && rackNode[t.nid]) { t.dup = true; return; }                       // already drawn in another place
      if (t.nid) { rackNode[t.nid] = { ...t.u, rackId: r.id }; pos[t.nid] = { x: t.x, y: ry + t.y, w: M.MT, h: M.MTH, rack: true, rackId: r.id, tile: true }; } });
    rackMeta[r.id] = { id: r.id, name: r.name, kind, isRack: false, total: 0, rows, y: ry, w, h, tiles, units: r.units };
    ry += h + 92;
  });
  const stackH = Math.max(0, ry - 92);
  const frameW = Math.max(M.RW, ...Object.values(rackMeta).map(m => m.w));
  const hasRack = Object.keys(rackNode).length > 0;

  // collapse big groups of Wi-Fi leaf clients
  const groups = {}; const hiddenIds = new Set();
  Object.entries(kids).forEach(([pid, es]) => {
    const wifiLeaves = es.filter(e => e.kind === 'wifi' && !kids[e.target]);
    if (wifiLeaves.length > 3 && collapsed[pid] !== false) {
      const gid = 'g:' + pid;
      groups[gid] = { id: gid, label: `${wifiLeaves.length} устройств по Wi-Fi`, members: wifiLeaves.map(e => nodes[e.target]), kind: 'group', parent: pid };
      wifiLeaves.forEach(e => { e.hidden = true; hiddenIds.add(e.target); });
      kids[pid] = es.filter(e => !e.hidden).concat([{ id: 'ge:' + pid, source: pid, target: gid, kind: 'wifi', group: true }]);
    }
  });
  Object.values(groups).forEach(g => { nodes[g.id] = g; });

  // columns: BFS from the rack (or from the internet's direct children when there is no rack)
  const inet = nodes['inet'];
  let roots = hasRack ? Object.keys(rackNode) : (kids['inet'] || []).filter(e => e.kind !== 'remote').map(e => e.target);
  if (!roots.length) roots = Object.keys(nodes).filter(id => !parentEdge[id] && id !== 'inet');
  const col = {}; const queue = [];
  roots.forEach(r => { col[r] = 0; queue.push(r); });
  while (queue.length) {
    const id = queue.shift();
    (kids[id] || []).filter(e => !e.hidden).forEach(e => { if (col[e.target] == null && !rackNode[e.target]) { col[e.target] = col[id] + 1; queue.push(e.target); } });
  }
  const colX = c => hasRack ? frameW + M.COL + (c - 1) * (M.NW + M.COL) : c * (M.NW + M.COL);
  const sizeOf = id => { const n = nodes[id]; return n.kind === 'group' || n.client ? [M.CW, M.CH] : [M.NW, M.NH]; };
  if (!hasRack) roots.forEach((r, i) => { const [w, h] = sizeOf(r); pos[r] = { x: 0, y: i * (h + 40), w, h }; });
  const maxCol = Math.max(0, ...Object.values(col));
  for (let c = 1; c <= maxCol; c++) {
    const ids = Object.keys(col).filter(id => col[id] === c);
    const pyOf = id => { const pe = parentEdge[id] || Object.values(kids).flat().find(e => e.target === id); const p = pe && pos[pe.source]; return p ? p.y + p.h / 2 : 0; };
    const byParent = {};
    ids.forEach(id => { const pe = parentEdge[id] || Object.values(kids).flat().find(e => e.target === id); (byParent[pe ? pe.source : '_'] = byParent[pe ? pe.source : '_'] || []).push({ id, port: pe ? (pe.sourcePort || 999) : 999 }); });
    let cursor = -Infinity;
    Object.entries(byParent).sort((a, b) => pyOf(a[1][0].id) - pyOf(b[1][0].id)).forEach(([pid, list]) => {
      list.sort((a, b) => a.port - b.port || String(nodes[a.id].label).localeCompare(String(nodes[b.id].label)));
      const heights = list.map(x => sizeOf(x.id)[1]);
      const groupH = heights.reduce((a, h) => a + h + M.GAP, -M.GAP);
      const p = pos[pid]; const center = p ? p.y + p.h / 2 : 0;
      let y = Math.max(cursor, center - groupH / 2);
      list.forEach((x, i) => { const [w, h] = sizeOf(x.id); pos[x.id] = { x: colX(c), y, w, h }; y += h + M.GAP; });
      cursor = y + M.GAP * 2;
    });
  }
  // internet + remote devices on top; an ONT / modem that isn't in a rack sits between the internet and the rack
  const box = hasRack && nodes['wan:box'] && !pos['wan:box'];
  const topY = (hasRack ? -170 : Math.min(0, ...Object.values(pos).map(p => p.y)) - 170) - (box ? M.NH + 70 : 0);
  const fw0 = (Object.values(rackMeta)[0] || {}).w || M.RW;
  if (inet) pos['inet'] = { x: (hasRack ? fw0 / 2 : M.NW / 2) - M.NW / 2, y: topY, w: M.NW, h: M.NH };
  if (box) { pos['wan:box'] = { x: fw0 / 2 - M.NW / 2, y: topY + M.NH + 70, w: M.NW, h: M.NH }; col['wan:box'] = -1; }
  const remotes = (kids['inet'] || []).filter(e => e.kind === 'remote').map(e => e.target);
  // remote devices go to the left of the internet node, so they never collide with the columns on the right
  remotes.forEach((id, i) => { pos[id] = { x: (pos.inet ? pos.inet.x : 0) - (M.NW + 50) * (i + 1), y: topY, w: M.NW, h: M.NH }; col[id] = -1; });
  // nodes never reached (shouldn't happen) go to a bottom row
  let stray = 0; Object.keys(nodes).forEach(id => { if (!pos[id] && !hiddenIds.has(id)) {
    const [w, h] = sizeOf(id); pos[id] = { x: colX(1) + stray * (w + 20), y: stackH + 80, w, h }; stray++; } });
  // user overrides (edit mode drag)
  Object.entries(data.map.positions || {}).forEach(([id, [x, y]]) => { if (pos[id] && !pos[id].rack) Object.assign(pos[id], { x, y }); });
  const edges = [...Object.values(kids).flat().filter(e => !e.hidden), ...topo.edges.filter(e => (e.extra || e.manual) && pos[e.source] && pos[e.target])];
  return { nodes, pos, edges, groups, hasRack, rackNode, racks: Object.values(rackMeta), rooms };
}

function edgePath(e, L) {
  const a = L.pos[e.source], b = L.pos[e.target];
  if (!a || !b) return null;
  if (a.rack && b.rack) {            // both in a rack: patch cable (same rack) or backbone (between racks)
    const y1 = a.y + a.h / 2, y2 = b.y + b.h / 2, cross = a.rackId !== b.rackId;
    const d = cross ? 80 + Math.min(130, Math.abs(y2 - y1) * .12) : 26 + Math.min(70, Math.abs(y2 - y1) * .18);
    const mx = Math.min(a.x, b.x) - d;                       // out of the frame on the left and back in
    return { d: `M${a.x},${y1} C${mx},${y1} ${mx},${y2} ${b.x},${y2}`, lx: mx + 8, ly: (y1 + y2) / 2, inside: true, cross };
  }
  if (!a.rack && !b.rack && b.y >= a.y + a.h && b.x < a.x + a.w && b.x + b.w > a.x) {   // straight down (internet → ONT above the rack)
    const x = (Math.max(a.x, b.x) + Math.min(a.x + a.w, b.x + b.w)) / 2, y1 = a.y + a.h, y2 = b.y;
    return { d: `M${x},${y1} L${x},${y2}`, lx: x + 34, ly: (y1 + y2) / 2 + 4 };
  }
  if ((e.source === 'inet' || (L.nodes[e.source] || {}).wan) && b.rack && !a.rack) {
    const sx = a.x + a.w / 2, sy = a.y + a.h, ty = b.y + b.h / 2, tx = (L.racks.find(r => r.id === b.rackId) || {}).w || b.x + b.w;
    const lane = tx + 34;                                                     // run down a lane beside the rack, not across its face
    if (ty - sy > 160) {
      const y1 = sy + 60;
      return { d: `M${sx},${sy} C${sx},${y1 - 10} ${lane},${sy + 10} ${lane},${y1 + 30} L${lane},${ty - 22} Q${lane},${ty} ${tx + 2},${ty}`,
        lx: lane + 26, ly: y1 + 40 };
    }
    return { d: `M${sx},${sy} C${sx},${sy + 60} ${tx + 70},${ty - 40} ${tx + 2},${ty}`, lx: tx + 34, ly: (sy + ty) / 2 };
  }
  if (e.source === 'inet' && b.x + b.w <= a.x) {      // remote device to the left of the internet node
    const sx = a.x, sy = a.y + a.h / 2, tx = b.x + b.w, ty = b.y + b.h / 2;
    return { d: `M${sx},${sy} C${sx - 30},${sy} ${tx + 30},${ty} ${tx},${ty}`, lx: (sx + tx) / 2, ly: sy - 8 };
  }
  if (e.source === 'inet') {
    const sx = a.x + a.w, sy = a.y + a.h / 2, tx = b.x, ty = b.y + b.h / 2;
    if (Math.abs(sy - ty) < 4) return { d: `M${sx},${sy} L${tx},${ty}`, lx: (sx + tx) / 2, ly: sy - 8 };
    return { d: `M${a.x + a.w / 2},${a.y + a.h} C${a.x + a.w / 2},${ty} ${tx - 60},${ty} ${tx},${ty}`, lx: tx - 40, ly: ty - 8 };
  }
  const sx = a.x + a.w, sy = a.y + a.h / 2, tx = b.x, ty = b.y + b.h / 2;
  if (tx < sx) {                     // target to the left (user moved it): connect centres
    const ax = a.x + a.w / 2, bx = b.x + b.w / 2;
    return { d: `M${ax},${a.y + a.h} C${ax},${ty} ${bx},${a.y + a.h} ${bx},${b.y}`, lx: (ax + bx) / 2, ly: (sy + ty) / 2 };
  }
  const dx = Math.max(50, (tx - sx) * .5);
  return { d: `M${sx},${sy} C${sx + dx},${sy} ${tx - dx},${ty} ${tx},${ty}`, lx: tx - 22, ly: ty, mx: (sx + tx) / 2, my: (sy + ty) / 2 };
}

function MapNode({ n, p, sel, dim, mark, onDown, onClick, onDoubleClick }) {
  const small = n.kind === 'group' || n.client;
  const iconKind = n.kind === 'group' ? 'wifi' : n.kind;
  const c = KIND_COLOR[iconKind] || KIND_COLOR.other;
  const is = small ? 28 : 34;
  return <g className={'node' + (small ? ' client' : '') + (n.kind === 'group' ? ' group' : '') + (sel ? ' sel' : '') + (dim ? ' dim-out' : '')}
    transform={`translate(${p.x},${p.y})`} onPointerDown={onDown} onClick={onClick} onDoubleClick={onDoubleClick}>
    {mark ? <rect className="spof-mark" x={-5} y={-5} width={p.w + 10} height={p.h + 10} rx={small ? 16 : 19} /> : null}
    <rect className="box" width={p.w} height={p.h} rx={small ? 12 : 15} />
    {n.room ? <g transform="translate(10,-9)"><rect width={Math.min(p.w - 20, 14 + n.room.length * 6.4)} height={15} rx={7.5} className="room-tag" />
      <text x={7} y={11} className="room-tag-t">{trunc(n.room, Math.floor((p.w - 34) / 6.4))}</text></g> : null}
    <rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} fill={c} opacity=".16" />
    <g transform={`translate(${9 + is * .2},${(p.h - is) / 2 + is * .2})`}><Icon name={iconKind} size={is * .6} color={c} /></g>
    <text className="lbl" x={is + 18} y={n.sub || n.kind === 'group' ? p.h / 2 - 3 : p.h / 2 + 4}>{trunc(n.label, small ? 19 : 22)}</text>
    {n.kind === 'group' ? <text className="sub" x={is + 18} y={p.h / 2 + 12}>нажмите, чтобы раскрыть</text>
      : n.sub ? <text className="sub" x={is + 18} y={p.h / 2 + 13}>{trunc(n.sub, 24)}</text> : null}
    {n.status && n.kind !== 'group' ? <circle cx={p.w - 13} cy={13} r={4.5} fill={n.status === 'online' ? 'var(--green)' : n.status === 'warning' ? 'var(--orange)' : n.status === 'offline' ? 'var(--red)' : 'var(--text3)'} /> : null}
  </g>;
}
const trunc = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

const MAP_GRID = 20;
function MapView() {
  const { data, edit, openDevice, saveMap } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const [collapsed, setCollapsed] = useState(data.map.collapsed || {});
  const [view, setView] = useState(null);                 // {x, y, k}
  const [sel, setSel] = useState(null);
  const [linking, setLinking] = useState(null);           // null | 'pick' | nodeId
  const [q, setQ] = useState('');
  const [dragPos, setDragPos] = useState({});
  const [guides, setGuides] = useState(null);             // {x, y}: alignment lines shown while a card is dragged
  const [healthOpen, setHealthOpen] = useState(() => lsGet('rl_health', '') === '1' || new URLSearchParams(location.search).has('analysis'));
  useEffect(() => { lsSet('rl_health', healthOpen ? '1' : ''); }, [healthOpen]);
  const spofSet = healthOpen && data.health ? new Set(data.health.spof.filter(s => s.affected >= 3).map(s => s.id)) : null;
  const openCheck = useCheckOpener();
  const wrap = useRef(null);
  const L = useMemo(() => {
    const l = layoutMap(data, collapsed);
    Object.entries(dragPos).forEach(([id, [x, y]]) => { if (l.pos[id]) Object.assign(l.pos[id], { x, y }); });
    return l;
  }, [data, collapsed, dragPos]);

  const bbox = () => {
    const ps = Object.values(L.pos); if (!ps.length) return { x: 0, y: 0, w: 100, h: 100 };
    const rackBottom = Math.max(0, ...(L.racks || []).map(r => r.y + (r.h || 0)));   // include empty racks
    const x1 = Math.min(-110, ...ps.map(p => p.x)) - 20, y1 = Math.min(-60, ...ps.map(p => p.y)) - 20;
    const x2 = Math.max(...ps.map(p => p.x + p.w)) + 20, y2 = Math.max(rackBottom, ...ps.map(p => p.y + p.h)) + 30;
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  };
  const fit = () => {
    const el = wrap.current; if (!el) return; const b = bbox();
    const off = healthOpen && el.clientWidth > 760 ? 424 : 0;      // keep the map clear of the analysis panel
    const W = el.clientWidth - off, H = el.clientHeight;
    const k = Math.min(1.2, Math.max(.2, Math.min(W / (b.w + 60), H / (b.h + 60))));
    setView({ k, x: off + (W - b.w * k) / 2 - b.x * k, y: (H - b.h * k) / 2 - b.y * k });
  };
  useEffect(() => { if (!view) fit(); }, [L]);
  useEffect(() => { if (view) fit(); }, [healthOpen]);
  const [focus, setFocus] = useState(null);               // a room picked in «Шкафы и места»: its devices lit up
  const focusRoom = rm => {
    const ps = rm.ids.map(id => L.pos[id]).filter(Boolean);
    if (!ps.length) { toast(rm.units ? `В «${rm.name}» нет устройств, которые можно показать: они не привязаны или уже стоят в шкафу` : `«${rm.name}» пока пустая — добавьте оборудование на «Главной»`, true); return; }
    const el = wrap.current; const W = el.clientWidth, H = el.clientHeight;
    const x1 = Math.min(...ps.map(p => p.x)), y1 = Math.min(...ps.map(p => p.y)), x2 = Math.max(...ps.map(p => p.x + p.w)), y2 = Math.max(...ps.map(p => p.y + p.h));
    const k = Math.min(1.1, Math.max(.3, Math.min((W - 120) / (x2 - x1 + 1), (H - 160) / (y2 - y1 + 1))));
    setView({ k, x: W / 2 - (x1 + x2) / 2 * k, y: H / 2 - (y1 + y2) / 2 * k }); setSel(null); setFocus(new Set(rm.ids));
  };
  const focusRack = rk => {                                 // centre the map on one rack (quick jump when there are many)
    const el = wrap.current; if (!el) return; const W = el.clientWidth, H = el.clientHeight; const rh = rk.h || rk.rows * M.RU;
    const k = Math.min(1.15, Math.max(.3, (H - 130) / (rh + 110)));
    setView({ k, x: W * 0.36 - ((rk.w || M.RW) / 2) * k, y: H / 2 - (rk.y + rh / 2) * k }); setSel(null);
  };

  // pan / zoom / pinch. The gesture baseline is re-captured whenever the number of fingers changes,
  // so lifting one finger after a pinch no longer snaps the map back.
  const ptrs = useRef({}); const panRef = useRef(null); const viewRef = useRef(view); viewRef.current = view;
  const clampK = k => Math.min(4, Math.max(.12, k));
  const baseline = () => {
    const pts = Object.values(ptrs.current); const v = { ...viewRef.current };
    if (!pts.length) return null;
    if (pts.length >= 2) { const r = wrap.current.getBoundingClientRect();
      return { pinch: true, dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1, cx: (pts[0].x + pts[1].x) / 2 - r.left, cy: (pts[0].y + pts[1].y) / 2 - r.top, v }; }
    return { pinch: false, sx: pts[0].x, sy: pts[0].y, v };
  };
  const onBgDown = e => {
    if (e.target.closest('.node, .rackbox .u, .edge-hit')) return;
    ptrs.current[e.pointerId] = { x: e.clientX, y: e.clientY };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) { }
    panRef.current = baseline();
    if (Object.keys(ptrs.current).length === 1) { setSel(null); setFocus(null); }
  };
  const onBgMove = e => {
    if (!ptrs.current[e.pointerId] || !panRef.current) return;
    e.preventDefault();
    ptrs.current[e.pointerId] = { x: e.clientX, y: e.clientY };
    const pts = Object.values(ptrs.current); const b = panRef.current;
    if (b.pinch && pts.length >= 2) {
      const r = wrap.current.getBoundingClientRect();
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const cx = (pts[0].x + pts[1].x) / 2 - r.left, cy = (pts[0].y + pts[1].y) / 2 - r.top;
      const k = clampK(b.v.k * dist / b.dist);
      setView({ k, x: cx - (b.cx - b.v.x) * k / b.v.k, y: cy - (b.cy - b.v.y) * k / b.v.k });
    } else if (!b.pinch) setView({ ...b.v, x: b.v.x + e.clientX - b.sx, y: b.v.y + e.clientY - b.sy });
  };
  const onBgUp = e => { delete ptrs.current[e.pointerId]; panRef.current = baseline(); };
  const zoomAt = (factor, cx, cy) => setView(v => {
    const W = wrap.current.clientWidth, H = wrap.current.clientHeight; cx = cx == null ? W / 2 : cx; cy = cy == null ? H / 2 : cy;
    const k = clampK(v.k * factor); return { k, x: cx - (cx - v.x) * k / v.k, y: cy - (cy - v.y) * k / v.k };
  });
  // panels over the map (analysis, node info, rack list) scroll on their own — gestures there are not map gestures
  const inPanel = e => e.target && e.target.closest && e.target.closest('.health-panel, .node-info, .rack-jump');
  const onWheel = e => {
    if (inPanel(e)) return;
    e.preventDefault(); const r = wrap.current.getBoundingClientRect();
    zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? .01 : .0025)), e.clientX - r.left, e.clientY - r.top);
  };
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const stop = ev => { if (!inPanel(ev)) ev.preventDefault(); };     // block Safari page zoom gestures on the map
    el.addEventListener('wheel', onWheel, { passive: false });
    el.addEventListener('gesturestart', stop); el.addEventListener('gesturechange', stop);
    el.addEventListener('touchmove', stop, { passive: false });
    return () => { el.removeEventListener('wheel', onWheel); el.removeEventListener('gesturestart', stop); el.removeEventListener('gesturechange', stop); el.removeEventListener('touchmove', stop); };
  }, [wrap.current, !!view]);

  // node drag in edit mode
  const dragEnd = useRef(0), ptr = useRef('');            // when the last drag ended / which pointer was used (mouse | touch | pen)
  const nodeDown = (id, e) => {
    ptr.current = e.pointerType || '';
    if (!edit || L.pos[id].rack || linking) return;
    e.stopPropagation(); const p0 = { ...L.pos[id] }; const sx = e.clientX, sy = e.clientY; let moved = false;
    // magnet: a card sticks to the grid and to the edges / centres of its neighbours (same idea as the tiles in «Размещение»)
    const others = Object.entries(L.pos).filter(([oid, o]) => oid !== id && !o.rack && L.nodes[oid]).map(([, o]) => o);
    const at = ev => {
      const x = p0.x + (ev.clientX - sx) / view.k, y = p0.y + (ev.clientY - sy) / view.k, T = 9 / view.k;
      let nx = Math.round(x / MAP_GRID) * MAP_GRID, ny = Math.round(y / MAP_GRID) * MAP_GRID, gx = null, gy = null, bx = T, by = T;
      others.forEach(o => {
        [o.x, o.x + o.w - p0.w, o.x + (o.w - p0.w) / 2].forEach(c => { if (Math.abs(x - c) < bx) { bx = Math.abs(x - c); nx = Math.round(c); gx = c === o.x ? o.x : c === o.x + o.w - p0.w ? o.x + o.w : o.x + o.w / 2; } });
        [o.y, o.y + o.h - p0.h, o.y + (o.h - p0.h) / 2].forEach(c => { if (Math.abs(y - c) < by) { by = Math.abs(y - c); ny = Math.round(c); gy = c === o.y ? o.y : c === o.y + o.h - p0.h ? o.y + o.h : o.y + o.h / 2; } });
      });
      return { np: [nx, ny], gx, gy };
    };
    const move = ev => { moved = true; const r = at(ev); setDragPos(d => ({ ...d, [id]: r.np })); setGuides({ x: r.gx, y: r.gy }); };
    const up = ev => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); setGuides(null);
      if (moved) dragEnd.current = Date.now();
      if (moved) saveMap({ positions: { ...(data.map.positions || {}), [id]: at(ev).np } });
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const nodeClick = async (id) => {
    const n = L.nodes[id];
    if (linking) {
      if (linking === 'pick') { setLinking(id); toast('Теперь выберите второе устройство'); return; }
      if (linking !== id) {
        const label = prompt('Подпись для связи (необязательно), например «Оптика 1 Гбит»', '') || '';
        await saveMap({ links: [...(data.map.links || []), { id: 'm' + Date.now().toString(36), source: linking, target: id, label }] });
        toast('Связь добавлена');
      }
      setLinking(null); return;
    }
    if (n.kind === 'group') { const nc = { ...collapsed, [n.parent]: false }; setCollapsed(nc); setView(null); if (edit) saveMap({ collapsed: nc }); return; }
    if (Date.now() - dragEnd.current < 350) return;                     // the click that ends a drag is not a tap
    if (edit && ptr.current === 'mouse') return;                        // on a computer in edit mode the card opens on double click (single click = grab)
    setSel(id);
  };
  const nodeDbl = id => { if (edit && ptr.current === 'mouse' && L.nodes[id] && L.nodes[id].kind !== 'group' && !linking) setSel(id); };
  const edgeClick = async (e) => {
    if (!edit || !e.manual) return;
    if (await confirm('Удалить эту связь?', { danger: true, ok: 'Удалить' })) saveMap({ links: (data.map.links || []).filter(l => l.id !== e.id && `m:${l.source}>${l.target}` !== e.id) });
  };

  // highlight path to the root for the selected node
  const pathSet = useMemo(() => {
    if (!sel) return focus; const s = new Set([sel]); let cur = sel, guard = 0;
    while (guard++ < 30) { const pe = L.edges.find(e => e.target === cur && !e.extra && !e.manual); if (!pe) break; s.add(pe.id); s.add(pe.source); cur = pe.source; }
    L.edges.filter(e => e.source === sel).forEach(e => { s.add(e.id); s.add(e.target); });
    return s;
  }, [sel, L, focus]);
  const searchHit = q ? Object.values(L.nodes).filter(n => [n.label, n.sub].join(' ').toLowerCase().includes(q.toLowerCase())).map(n => n.id) : [];
  useEffect(() => {
    if (searchHit.length === 1 && wrap.current) { const p = L.pos[searchHit[0]]; if (!p) return; const W = wrap.current.clientWidth, H = wrap.current.clientHeight;
      setSel(searchHit[0]); setView(v => ({ k: Math.max(v.k, .9), x: W / 2 - (p.x + p.w / 2) * Math.max(v.k, .9), y: H / 2 - (p.y + p.h / 2) * Math.max(v.k, .9) })); }
  }, [q]);

  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const selNode = sel && L.nodes[sel];
  const [findOpen, setFindOpen] = useState(false);
  const [racksOpen, setRacksOpen] = useState(false);
  const anyCollapsedOpen = Object.values(collapsed).some(v => v === false);
  if (!view) return <div className="map-wrap" ref={wrap} />;
  return <div className="map-wrap" ref={wrap}>
    <div className="map-tools">
      {/* compact: a magnifier that opens the search field, a cabinet button with the list of places */}
      <div className="map-panel map-find">
        {findOpen || q ? <><div className="map-search"><SearchBox value={q} onChange={setQ} placeholder="Найти устройство" autoFocus /></div>
          <Btn size="sm" icon="x" title="Закрыть поиск" onClick={() => { setQ(''); setFindOpen(false); }} /></>
          : <Btn size="sm" icon="search" title="Найти устройство" onClick={() => { setFindOpen(true); setRacksOpen(false); }} />}
        {((L.racks || []).length + (L.rooms || []).length) > 1 ? <Btn size="sm" icon="rack" kind={racksOpen ? 'primary' : ''} title="Шкафы и места" onClick={() => setRacksOpen(!racksOpen)} /> : null}
      </div>
      <div className="grow" />
      <div className="map-panel">
        {data.health ? <Btn size="sm" icon="pulse" kind={healthOpen ? 'primary' : ''} onClick={() => setHealthOpen(!healthOpen)} title="Анализ сети">Анализ</Btn> : null}
        <Btn size="sm" icon="fit" onClick={fit} title="Показать всё" />
        <Btn size="sm" icon="wifi" onClick={() => { const nc = {}; if (!anyCollapsedOpen) Object.keys(L.groups).forEach(g => nc[g.slice(2)] = false); setCollapsed(nc); setView(null); }}
          title={anyCollapsedOpen ? 'Свернуть Wi-Fi-клиентов' : 'Показать всех Wi-Fi-клиентов'} />
        {edit ? <><Btn size="sm" icon="link" kind={linking ? 'primary' : ''} onClick={() => setLinking(linking ? null : 'pick')}>{linking ? 'Отмена' : 'Связь'}</Btn>
          <Btn size="sm" icon="refresh" onClick={async () => { if (await confirm('Сбросить ручное расположение узлов?')) { setDragPos({}); saveMap({ positions: {} }); } }} title="Сбросить раскладку" /></> : null}
      </div>
    </div>
    {racksOpen && ((L.racks || []).length + (L.rooms || []).length) > 1 ? <div className="map-panel rack-jump">
      <span className="rack-jump-title">Шкафы и места</span>
      {L.racks.map(rk => <button key={rk.id} className="rack-jump-btn" onClick={() => { focusRack(rk); setRacksOpen(false); }} title={`Показать «${rk.name}»`}>
        <Icon name="rack" size={13} /><span className="ellipsis">{rk.name}</span></button>)}
      {(L.rooms || []).map(rm => <button key={rm.id} className="rack-jump-btn" onClick={() => { focusRoom(rm); setRacksOpen(false); }} title={`Показать устройства «${rm.name}»`}>
        <Icon name="home" size={13} /><span className="ellipsis">{rm.name}</span></button>)}
      <button className="rack-jump-btn" onClick={() => { fit(); setFocus(null); setRacksOpen(false); }}><Icon name="fit" size={13} />Все</button>
    </div> : null}
    {linking ? <div className="toast" style={{ position: 'absolute', top: 64, left: '50%', transform: 'translateX(-50%)', zIndex: 3 }}>
      <Icon name="link" size={15} />{linking === 'pick' ? 'Выберите первое устройство' : 'Выберите второе устройство'}</div> : null}
    <svg onPointerDown={onBgDown} onPointerMove={onBgMove} onPointerUp={onBgUp} onPointerCancel={onBgUp} className={panRef.current ? 'panning' : ''}>
      <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
        {L.hasRack ? <RackBox L={L} data={data} devById={devById} dimSet={pathSet} markSet={spofSet} onOpen={d => openDevice(d)} onSel={setSel} /> : null}
        {edit ? <><defs><pattern id="mapgrid" width={MAP_GRID} height={MAP_GRID} patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="var(--text3)" opacity=".35" /></pattern></defs>
          <rect x={-4000} y={-4000} width={9000} height={9000} fill="url(#mapgrid)" pointerEvents="none" /></> : null}
        {L.edges.map(e => { const g = edgePath(e, L); if (!g) return null; const col = speedColor(e.speed, e.kind);
          const dim = pathSet && !pathSet.has(e.id) ? ' dim-out' : '';
          return <g key={e.id} className={dim}>
            <path className={'edge' + (e.kind === 'wifi' || e.kind === 'mesh' ? ' wifi' : '') + (e.kind === 'remote' || e.extra || e.kind === 'lan' ? ' dashed' : '') + (e.kind === 'isp' ? ' isp' : '')} d={g.d} stroke={col} opacity={e.extra ? .55 : 1} />
            {(e.kind === 'wan' || e.kind === 'isp' || (e.kind === 'wire' && e.speed >= 1000)) && !e.extra ? <path className="edge flow" d={g.d} stroke="#fff" opacity=".5" /> : null}
            {e.manual ? <path className="edge-hit" d={g.d} onClick={() => edgeClick(e)} /> : null}
          </g>; })}
        {/* labels in their own layer: above every wire, with the watts lifted over the line so it stays readable */}
        {L.edges.map(e => { const g = edgePath(e, L); if (!g) return null;
          const dim = pathSet && !pathSet.has(e.id) ? ' dim-out' : '';
          return <g key={'l' + e.id} className={dim} pointerEvents="none">
            {e.sourcePort && !g.inside ? <g className="port-pill" transform={`translate(${g.lx - 14},${g.ly - 9})`}><rect width="28" height="18" rx="9" /><text x="14" y="12.5" textAnchor="middle">{e.sourcePort}</text></g> : null}
            {g.cross ? <g transform={`translate(${g.lx},${g.ly})`}><rect x={-52} y={-10} width={104} height={20} rx={10} fill="var(--accent)" opacity=".92" />
              <text x={0} y={4} textAnchor="middle" fontSize="11" fontWeight="600" fill="#fff">между шкафами{e.sourcePort ? ' · ' + e.sourcePort : ''}</text></g> : null}
            {e.poeW > 0 && g.mx ? <g transform={`translate(${g.lx - 14 - 50},${g.ly - 24})`}><rect width="44" height="18" rx="9" fill="#ffd60a" stroke="var(--bg)" strokeWidth="2" /><text x="22" y="12.5" textAnchor="middle" fontSize="10" fontWeight="700" fill="#000">⚡{e.poeW}W</text></g> : null}
            {(e.label && (e.manual || e.kind === 'wan' || e.kind === 'isp')) ? <text x={g.lx} y={g.ly - 14} fontSize="11" fill="var(--text2)" textAnchor="middle" stroke="var(--bg)" strokeWidth="3" paintOrder="stroke">{e.label}</text> : null}
          </g>; })}
        {guides ? <g pointerEvents="none" stroke="var(--accent)" strokeWidth={1 / view.k} strokeDasharray={`${4 / view.k} ${4 / view.k}`} opacity=".7">
          {guides.x != null ? <line x1={guides.x} x2={guides.x} y1={-4000} y2={5000} /> : null}
          {guides.y != null ? <line y1={guides.y} y2={guides.y} x1={-4000} x2={5000} /> : null}</g> : null}
        {Object.values(L.nodes).map(n => { const p = L.pos[n.id]; if (!p || p.rack) return null;
          return <MapNode key={n.id} n={n} p={p} sel={sel === n.id || searchHit.includes(n.id) || linking === n.id} dim={pathSet && !pathSet.has(n.id)} mark={spofSet && spofSet.has(n.id)}
            onDown={e => nodeDown(n.id, e)} onClick={() => nodeClick(n.id)} onDoubleClick={() => nodeDbl(n.id)} />; })}
      </g>
    </svg>
    <div className="map-legend legend">
      <span><i style={{ background: 'var(--green)' }} />1 Гбит</span><span><i style={{ background: 'var(--yellow)' }} />100 Мбит</span>
      <span><i style={{ background: 'var(--accent)' }} />Wi-Fi</span><span><i style={{ background: 'var(--teal)' }} />Mesh</span><span><i style={{ background: 'var(--purple)' }} />Интернет</span>
      <span><b style={{ color: '#ffd60a' }}>⚡</b>PoE</span></div>
    <div className="zoom-btns"><button className="btn" onClick={() => zoomAt(1.35)}>+</button><button className="btn" onClick={() => zoomAt(1 / 1.35)}>−</button></div>
    {healthOpen && data.health ? <div className="card pad fade-in health-panel">
      <div className="row" style={{ marginBottom: 4 }}><b className="grow" style={{ fontSize: 16 }}>Анализ сети</b><Btn size="sm" icon="x" onClick={() => setHealthOpen(false)} /></div>
      <HealthBody h={data.health} onCheck={c => { if (c.nodeId && L.nodes[c.nodeId] && !c.port) { setSel(c.nodeId); if (innerWidth < 760) setHealthOpen(false); } else openCheck(c); }}
        onNode={id => { if (L.nodes[id]) { setSel(id); if (innerWidth < 760) setHealthOpen(false); } }} />
    </div> : null}
    {selNode ? <NodeInfo n={selNode} L={L} data={data} devById={devById} onOpen={openDevice} onClose={() => setSel(null)} /> : null}
  </div>;
}

function RackBox({ L, data, devById, dimSet, markSet, onOpen, onSel }) {
  return <>{L.racks.map(rk => <RackFrame key={rk.id} rk={rk} devById={devById} dimSet={dimSet} markSet={markSet} onOpen={onOpen} nodes={L.nodes} onSel={onSel} />)}</>;
}

function RackFrame({ rk, devById, dimSet, markSet, onOpen, nodes = {}, onSel }) {
  const W = rk.w || M.RW, h = rk.h || rk.rows * M.RU;
  const stCol = st => st === 'online' ? 'var(--green)' : st === 'warning' ? 'var(--orange)' : st === 'unknown' ? 'var(--text3)' : 'var(--red)';
  // one cell: a whole unit, a shelf's slot or a box tile
  const cell = (key, u, did, x, y, w, hh, compact) => {
    const d = did ? devById[did] : null; const un = !d && !did && nodes['u:' + u.id];   // un: ONT / modem without a device
    const st = d ? d.state : un ? { status: un.status } : null;
    const dim = dimSet && !(d ? dimSet.has('d:' + d.id) : un && dimSet.has(un.id));
    const kind = PASSIVE.includes(u.type) ? u.type : (d && d.kind) || u.type;
    const name = d && (compact || unitDevIds(u).length > 1) ? d.name : u.name;
    return <g key={key} className={'u' + (dim ? ' dim-out' : '')} style={{ cursor: d || un ? 'pointer' : 'default' }} onClick={() => d ? onOpen(d) : un && onSel && onSel(un.id)}>
      <rect x={x} y={y} width={w} height={hh} rx={compact ? 10 : 6} />
      {d && markSet && markSet.has('d:' + d.id) ? <rect className="spof-mark" x={x - 3} y={y - 3} width={w + 6} height={hh + 6} rx={compact ? 12 : 8} /> : null}
      <rect x={x} y={y} width={4} height={hh} rx={2} fill={u.color || '#0a84ff'} stroke="none" />
      <g className="u-ic" transform={`translate(${x + 12},${y + hh / 2 - 9})`}><Icon name={kind} size={18} color="currentColor" /></g>
      <text x={x + 38} y={y + (hh > 30 ? hh / 2 - 2 : hh / 2 + 4)} fontSize="12.5" fontWeight="600">{trunc(name, Math.max(8, Math.floor((w - 50) / 7.2)))}</text>
      {hh > 30 && w > 120 ? <text x={x + 38} y={y + hh / 2 + 12} className="usub">{trunc(d ? deviceLine(d) : KIND_TEXT[u.type], Math.floor((w - 50) / 5.6))}</text> : null}
      {st ? <circle cx={x + w - 11} cy={y + 11} r={4} fill={stCol(st.status)} /> : null}
      {st && !compact && w > 220 && (st.ports || []).length > 4 ? <g transform={`translate(${x + w - 14 - Math.ceil(Math.min(st.ports.length, 28) / 2) * 7},${y + hh - 17})`}>
        {st.ports.slice(0, 28).map((p, i) => <rect key={i} x={Math.floor(i / 2) * 7} y={(i % 2) * 7} width={5} height={5} rx={1}
          fill={!p.link ? '#3a3a3c' : p.speed >= 1000 ? '#30d158' : p.speed >= 100 ? '#ffd60a' : '#ff9f0a'} stroke="none" />)}</g> : null}
    </g>;
  };
  if (!rk.isRack) return <g className="rackbox boxframe" transform={`translate(0,${rk.y})`}>
    <rect className="frame" x={-14} y={-46} width={W + 28} height={h + 60} rx={20} />
    <g className="u-ic" transform="translate(0,-34)"><Icon name="box" size={16} color="currentColor" /></g>
    <text x={22} y={-22} fontSize="14" fontWeight="700">{rk.name}</text>
    <text x={W} y={-22} fontSize="11" textAnchor="end" className="usub">щиток</text>
    {(rk.tiles || []).map((t, i) => t.dup ? <g key={'t' + i} opacity=".4">{cell('t' + i, t.u, t.nid.slice(2), t.x, t.y, M.MT, M.MTH, true)}</g>
      : cell('t' + i, t.u, t.nid && t.nid.startsWith('d:') ? t.nid.slice(2) : null, t.x, t.y, M.MT, M.MTH, true))}
  </g>;
  const rows = rk.units.filter(u => (u.side || 'front') === 'front');
  return <g className="rackbox" transform={`translate(0,${rk.y})`}>
    <rect className="frame" x={-14} y={-46} width={W + 28} height={h + 60} rx={16} />
    <text x={0} y={-22} fontSize="14" fontWeight="700">{rk.name}</text>
    <text x={W} y={-22} fontSize="11" textAnchor="end" className="usub">{rk.total + 'U'}</text>
    {Array.from({ length: rk.total }, (_, i) => <text key={i} x={-7} y={i * M.RU + M.RU / 2 + 3} fontSize="8" textAnchor="middle" className="usub">{i + 1}</text>)}
    {rows.flatMap(u => { const y = (u.uStart - 1) * M.RU, hh = u.uSize * M.RU - 4; const ids = unitDevIds(u);
      if (ids.length <= 1) return [cell(u.id, u, ids[0] || null, 0, y, W, hh, false)];
      const cw = (W - (ids.length - 1) * 4) / ids.length;            // a shelf with several devices
      return ids.map((did, k) => cell(u.id + k, u, did, k * (cw + 4), y, cw, hh, false)); })}
  </g>;
}

/* how the internet reaches the router: straight in, or through an ONT (PON) / modem — map.wan */
const WAN_OPTS = [{ value: 'auto', label: 'Авто' }, { value: 'direct', label: 'Напрямую' }, { value: 'ont', label: 'ONT (PON)' }, { value: 'modem', label: 'Модем' }];
function WanSetup({ n, L, data }) {
  const { admin, saveMap } = useApp();
  const wan = data.map.wan || {}; const via = wan.via || 'auto';
  const box = Object.values(L.nodes).find(x => x.wan);
  const wanEdge = L.edges.find(e => e.kind === 'wan');
  const set = patch => saveMap({ wan: { ...wan, ...patch } });
  const units = allUnits(data).filter(u => !['cross', 'patch', 'router', 'switch', 'blank', 'organizer', 'shelf'].includes(u.type) && (u.side || 'front') === 'front');
  const isp = L.edges.find(e => e.kind === 'isp');
  const mainNode = Object.values(L.nodes).find(x => x.main);
  const routers = data.devices.filter(d => ['keenetic', 'openwrt', 'demo_router'].includes(d.driver) && d.enabled !== false);
  const now = box ? `${n.id === 'inet' ? 'Интернет → ' : ''}${box.label} → ${wanEdge && L.nodes[wanEdge.target] ? L.nodes[wanEdge.target].label : 'роутер'}`
    : wanEdge && L.nodes[wanEdge.target] ? `Интернет → ${L.nodes[wanEdge.target].label} (кабель провайдера прямо в роутер)` : '';
  return <div className="wan-setup">
    <div className="dim" style={{ fontSize: 12.5, marginBottom: 6 }}>{now}{wanEdge && wanEdge.targetPort ? ` · порт ${wanEdge.targetPort}` : ''}{wanEdge && wanEdge.label ? ` · ${wanEdge.label}` : ''}
      {isp && isp.label ? <><br />Линия провайдера: {isp.label}</> : null}
      {mainNode ? <><br />Главный роутер: <b>{mainNode.label}</b> — {mainNode.main}</> : null}</div>
    {admin && routers.length > 1 ? <div className="row" style={{ gap: 8, margin: '8px 0 0', alignItems: 'center' }}>
      <span className="dim" style={{ fontSize: 13 }}>Главный роутер</span>
      <select className="select grow" value={wan.main || ''} onChange={e => set({ main: e.target.value || undefined })}>
        <option value="">Определять самому</option>
        {routers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></div> : null}
    {admin ? <>
      <div className="card-title" style={{ margin: '8px 0 6px' }}>Как приходит интернет</div>
      <Seg value={via} onChange={v => set({ via: v })} options={WAN_OPTS} />
      <div className="dim3" style={{ fontSize: 12, margin: '6px 0 0', lineHeight: 1.4 }}>
        {via === 'auto' ? 'Rack Live сам ищет в шкафу юнит «Модем / ONT» или с «PON», «ONT», «модем» в названии.' : via === 'direct' ? 'Кабель провайдера включён прямо в роутер.'
          : via === 'ont' ? 'Оптика приходит в PON-терминал, от него кабель в роутер.' : 'Линия (DSL, кабельный, LTE) приходит в модем, от него кабель в роутер.'}</div>
      {via !== 'direct' ? <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
        <select className="select grow" style={{ minWidth: 150 }} value={wan.unit || ''} onChange={e => set({ unit: e.target.value || undefined })}>
          <option value="">Найти в шкафу сам</option>
          <option value="none">Не в шкафу</option>
          {units.map(u => <option key={u.id} value={u.id}>{u.rackName} · {u.name}</option>)}
        </select>
        <input className="input grow" style={{ minWidth: 130 }} defaultValue={wan.line || ''} placeholder={via === 'modem' ? 'Линия: DSL, LTE…' : 'Линия: оптика'}
          onBlur={e => e.target.value.trim() !== (wan.line || '') && set({ line: e.target.value.trim() || undefined })} />
      </div> : null}
    </> : null}
  </div>;
}

function NodeInfo({ n, L, data, devById, onOpen, onClose }) {
  const pe = L.edges.find(e => e.target === n.id && !e.extra);
  const parent = pe && L.nodes[pe.source];
  const dev = n.deviceId && devById[n.deviceId];
  const client = n.mac && data.devices.flatMap(d => (d.state && d.state.clients) || []).find(c => (c.mac || '').toLowerCase() === n.mac);
  const conn = pe ? (pe.kind === 'wifi' ? `Wi-Fi · ${parent ? parent.label : ''}${pe.band ? ' · ' + pe.band : ''}${pe.rssi ? ' · ' + pe.rssi + ' дБм' : ''}`
    : pe.kind === 'mesh' ? 'Mesh (беспроводной)' : pe.kind === 'remote' ? 'Через интернет' : `${parent ? parent.label : ''}${pe.sourcePort ? ', порт ' + pe.sourcePort : ''}${pe.speed ? ' · ' + fmt.speed(pe.speed) : ''}`) : '';
  return <div className="card pad fade-in node-info">
    <div className="row"><KindIcon kind={n.kind} size={40} /><div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 700 }} className="ellipsis">{n.label}</div>
      <div className="dim" style={{ fontSize: 12.5 }}>{KIND_TEXT[n.kind] || ''}{n.model ? ' · ' + n.model : ''}</div></div><Btn size="sm" icon="x" onClick={onClose} /></div>
    <div style={{ marginTop: 10 }}><KV rows={[['IP', n.sub ? <span className="mono">{n.sub}</span> : null], ...(n.mac ? [['MAC', <span className="mono">{n.mac}</span>]] : []),
      ...(client && client.segment ? [['Сеть', client.segment]] : []), ['Подключение', conn], ...(pe && pe.poeW ? [['PoE', pe.poeW + ' Вт']] : []),
      ...(dev ? [['Состояние', STATUS_TEXT[(dev.state || {}).status]]] : [])]} /></div>
    {n.id === 'inet' || n.wan ? <WanSetup n={n} L={L} data={data} /> : null}
    {dev ? <Btn kind="primary" style={{ width: '100%', marginTop: 12 }} onClick={() => onOpen(dev)}>Подробнее</Btn> : null}
    {!dev && pe && pe.sourcePort && parent && parent.deviceId ? <Btn style={{ width: '100%', marginTop: 12 }} onClick={() => onOpen(devById[parent.deviceId], 'ports', pe.sourcePort)}>Порт {pe.sourcePort} на {parent.label}</Btn> : null}
  </div>;
}
