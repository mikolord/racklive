/* Network map: the rack in the middle, cables from its units to everything else. */
const M = { NW: 214, NH: 56, CW: 196, CH: 46, COL: 130, GAP: 12, RW: 310, RU: 38 };

function layoutMap(data, collapsed) {
  const topo = data.topology || { nodes: [], edges: [] };
  const nodes = {}; topo.nodes.forEach(n => nodes[n.id] = { ...n });
  const tree = topo.edges.filter(e => !e.extra && !e.manual && nodes[e.source] && nodes[e.target]).map(e => ({ ...e }));
  const parentEdge = {}; const kids = {};
  tree.forEach(e => { parentEdge[e.target] = e; (kids[e.source] = kids[e.source] || []).push(e); });

  // rack units shown on the map (front + back, linked ones get live data)
  const units = [...data.rack.units].sort((a, b) => (a.side === 'back') - (b.side === 'back') || a.uStart - b.uStart);
  const rackNode = {}; units.forEach(u => { if (u.deviceId && nodes['d:' + u.deviceId]) rackNode['d:' + u.deviceId] = u; });
  const hasRack = Object.keys(rackNode).length > 0;
  const pos = {};
  const total = data.rack.totalU;
  Object.entries(rackNode).forEach(([id, u]) => {
    const y = (u.uStart - 1) * M.RU + (u.side === 'back' ? 0 : 0);
    pos[id] = { x: 0, y, w: M.RW, h: u.uSize * M.RU - 4, rack: true };
  });

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
  const colX = c => hasRack ? M.RW + M.COL + (c - 1) * (M.NW + M.COL) : c * (M.NW + M.COL);
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
  // internet + remote devices on top
  const topY = hasRack ? -170 : Math.min(0, ...Object.values(pos).map(p => p.y)) - 170;
  if (inet) pos['inet'] = { x: (hasRack ? M.RW / 2 : M.NW / 2) - M.NW / 2, y: topY, w: M.NW, h: M.NH };
  const remotes = (kids['inet'] || []).filter(e => e.kind === 'remote').map(e => e.target);
  remotes.forEach((id, i) => { pos[id] = { x: (pos.inet ? pos.inet.x : 0) + (M.NW + 40) * (i + 1), y: topY, w: M.NW, h: M.NH }; col[id] = -1; });
  // nodes never reached (shouldn't happen) go to a bottom row
  let stray = 0; Object.keys(nodes).forEach(id => { if (!pos[id] && !hiddenIds.has(id)) {
    const [w, h] = sizeOf(id); pos[id] = { x: colX(1) + stray * (w + 20), y: total * M.RU + 80, w, h }; stray++; } });
  // user overrides (edit mode drag)
  Object.entries(data.map.positions || {}).forEach(([id, [x, y]]) => { if (pos[id] && !pos[id].rack) Object.assign(pos[id], { x, y }); });
  const edges = [...Object.values(kids).flat().filter(e => !e.hidden), ...topo.edges.filter(e => (e.extra || e.manual) && pos[e.source] && pos[e.target])];
  return { nodes, pos, edges, groups, hasRack, units, rackNode };
}

function edgePath(e, L) {
  const a = L.pos[e.source], b = L.pos[e.target];
  if (!a || !b) return null;
  if (a.rack && b.rack) {            // patch cable inside the rack: loop on the left side
    const y1 = a.y + a.h / 2, y2 = b.y + b.h / 2, d = 26 + Math.min(70, Math.abs(y2 - y1) * .18);
    return { d: `M0,${y1} C${-d},${y1} ${-d},${y2} 0,${y2}`, lx: -d * .75, ly: (y1 + y2) / 2, inside: true };
  }
  if (e.source === 'inet' && b.rack) {
    const sx = a.x + a.w / 2, sy = a.y + a.h, ty = b.y + b.h / 2, tx = M.RW;
    return { d: `M${sx},${sy} C${sx},${sy + 60} ${tx + 70},${ty - 40} ${tx + 2},${ty}`, lx: tx + 34, ly: (sy + ty) / 2 };
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

function MapNode({ n, p, sel, dim, onDown, onClick }) {
  const small = n.kind === 'group' || n.client;
  const iconKind = n.kind === 'group' ? 'wifi' : n.kind;
  const c = KIND_COLOR[iconKind] || KIND_COLOR.other;
  const is = small ? 28 : 34;
  return <g className={'node' + (small ? ' client' : '') + (n.kind === 'group' ? ' group' : '') + (sel ? ' sel' : '') + (dim ? ' dim-out' : '')}
    transform={`translate(${p.x},${p.y})`} onPointerDown={onDown} onClick={onClick}>
    <rect className="box" width={p.w} height={p.h} rx={small ? 12 : 15} />
    <rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} fill={c} opacity=".16" />
    <g transform={`translate(${9 + is * .2},${(p.h - is) / 2 + is * .2})`}><Icon name={iconKind} size={is * .6} color={c} /></g>
    <text className="lbl" x={is + 18} y={n.sub || n.kind === 'group' ? p.h / 2 - 3 : p.h / 2 + 4}>{trunc(n.label, small ? 19 : 22)}</text>
    {n.kind === 'group' ? <text className="sub" x={is + 18} y={p.h / 2 + 12}>нажмите, чтобы раскрыть</text>
      : n.sub ? <text className="sub" x={is + 18} y={p.h / 2 + 13}>{trunc(n.sub, 24)}</text> : null}
    {n.status && n.kind !== 'group' ? <circle cx={p.w - 13} cy={13} r={4.5} fill={n.status === 'online' ? 'var(--green)' : n.status === 'warning' ? 'var(--orange)' : n.status === 'offline' ? 'var(--red)' : 'var(--text3)'} /> : null}
  </g>;
}
const trunc = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

function MapView() {
  const { data, edit, openDevice, saveMap } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const [collapsed, setCollapsed] = useState(data.map.collapsed || {});
  const [view, setView] = useState(null);                 // {x, y, k}
  const [sel, setSel] = useState(null);
  const [linking, setLinking] = useState(null);           // null | 'pick' | nodeId
  const [q, setQ] = useState('');
  const [dragPos, setDragPos] = useState({});
  const wrap = useRef(null);
  const L = useMemo(() => {
    const l = layoutMap(data, collapsed);
    Object.entries(dragPos).forEach(([id, [x, y]]) => { if (l.pos[id]) Object.assign(l.pos[id], { x, y }); });
    return l;
  }, [data, collapsed, dragPos]);

  const bbox = () => {
    const ps = Object.values(L.pos); if (!ps.length) return { x: 0, y: 0, w: 100, h: 100 };
    const x1 = Math.min(-110, ...ps.map(p => p.x)), y1 = Math.min(-60, ...ps.map(p => p.y)) - 20;
    const x2 = Math.max(...ps.map(p => p.x + p.w)) + 20, y2 = Math.max(data.rack.totalU * M.RU, ...ps.map(p => p.y + p.h)) + 30;
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  };
  const fit = () => {
    const el = wrap.current; if (!el) return; const b = bbox(); const W = el.clientWidth, H = el.clientHeight;
    const k = Math.min(1.2, Math.max(.2, Math.min(W / (b.w + 60), H / (b.h + 60))));
    setView({ k, x: (W - b.w * k) / 2 - b.x * k, y: (H - b.h * k) / 2 - b.y * k });
  };
  useEffect(() => { if (!view) fit(); }, [L]);

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
    if (Object.keys(ptrs.current).length === 1) setSel(null);
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
  const onWheel = e => {
    e.preventDefault(); const r = wrap.current.getBoundingClientRect();
    zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? .01 : .0025)), e.clientX - r.left, e.clientY - r.top);
  };
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const stop = ev => ev.preventDefault();                  // block Safari page zoom gestures on the map
    el.addEventListener('wheel', onWheel, { passive: false });
    el.addEventListener('gesturestart', stop); el.addEventListener('gesturechange', stop);
    el.addEventListener('touchmove', stop, { passive: false });
    return () => { el.removeEventListener('wheel', onWheel); el.removeEventListener('gesturestart', stop); el.removeEventListener('gesturechange', stop); el.removeEventListener('touchmove', stop); };
  }, [wrap.current, !!view]);

  // node drag in edit mode
  const nodeDown = (id, e) => {
    if (!edit || L.pos[id].rack || linking) return;
    e.stopPropagation(); const p0 = { ...L.pos[id] }; const sx = e.clientX, sy = e.clientY; let moved = false;
    const move = ev => { moved = true; setDragPos(d => ({ ...d, [id]: [Math.round(p0.x + (ev.clientX - sx) / view.k), Math.round(p0.y + (ev.clientY - sy) / view.k)] })); };
    const up = ev => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      if (moved) { const np = [Math.round(p0.x + (ev.clientX - sx) / view.k), Math.round(p0.y + (ev.clientY - sy) / view.k)];
        saveMap({ positions: { ...(data.map.positions || {}), [id]: np } }); }
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
    setSel(id);
  };
  const edgeClick = async (e) => {
    if (!edit || !e.manual) return;
    if (await confirm('Удалить эту связь?', { danger: true, ok: 'Удалить' })) saveMap({ links: (data.map.links || []).filter(l => l.id !== e.id && `m:${l.source}>${l.target}` !== e.id) });
  };

  // highlight path to the root for the selected node
  const pathSet = useMemo(() => {
    if (!sel) return null; const s = new Set([sel]); let cur = sel, guard = 0;
    while (guard++ < 30) { const pe = L.edges.find(e => e.target === cur && !e.extra && !e.manual); if (!pe) break; s.add(pe.id); s.add(pe.source); cur = pe.source; }
    L.edges.filter(e => e.source === sel).forEach(e => { s.add(e.id); s.add(e.target); });
    return s;
  }, [sel, L]);
  const searchHit = q ? Object.values(L.nodes).filter(n => [n.label, n.sub].join(' ').toLowerCase().includes(q.toLowerCase())).map(n => n.id) : [];
  useEffect(() => {
    if (searchHit.length === 1 && wrap.current) { const p = L.pos[searchHit[0]]; if (!p) return; const W = wrap.current.clientWidth, H = wrap.current.clientHeight;
      setSel(searchHit[0]); setView(v => ({ k: Math.max(v.k, .9), x: W / 2 - (p.x + p.w / 2) * Math.max(v.k, .9), y: H / 2 - (p.y + p.h / 2) * Math.max(v.k, .9) })); }
  }, [q]);

  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const selNode = sel && L.nodes[sel];
  const anyCollapsedOpen = Object.values(collapsed).some(v => v === false);
  if (!view) return <div className="map-wrap" ref={wrap} />;
  return <div className="map-wrap" ref={wrap}>
    <div className="map-tools">
      <div className="map-panel" style={{ width: 230 }}><SearchBox value={q} onChange={setQ} placeholder="Найти устройство" /></div>
      <div className="grow" />
      <div className="map-panel">
        <Btn size="sm" icon="fit" onClick={fit} title="Показать всё" />
        <Btn size="sm" icon="wifi" onClick={() => { const nc = {}; if (!anyCollapsedOpen) Object.keys(L.groups).forEach(g => nc[g.slice(2)] = false); setCollapsed(nc); setView(null); }}
          title={anyCollapsedOpen ? 'Свернуть Wi-Fi-клиентов' : 'Показать всех Wi-Fi-клиентов'} />
        {edit ? <><Btn size="sm" icon="link" kind={linking ? 'primary' : ''} onClick={() => setLinking(linking ? null : 'pick')}>{linking ? 'Отмена' : 'Связь'}</Btn>
          <Btn size="sm" icon="refresh" onClick={async () => { if (await confirm('Сбросить ручное расположение узлов?')) { setDragPos({}); saveMap({ positions: {} }); } }} title="Сбросить раскладку" /></> : null}
      </div>
    </div>
    {linking ? <div className="toast" style={{ position: 'absolute', top: 64, left: '50%', transform: 'translateX(-50%)', zIndex: 3 }}>
      <Icon name="link" size={15} />{linking === 'pick' ? 'Выберите первое устройство' : 'Выберите второе устройство'}</div> : null}
    <svg onPointerDown={onBgDown} onPointerMove={onBgMove} onPointerUp={onBgUp} onPointerCancel={onBgUp} className={panRef.current ? 'panning' : ''}>
      <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
        {L.hasRack ? <RackBox L={L} data={data} devById={devById} dimSet={pathSet} onOpen={d => openDevice(d)} total={data.rack.totalU} /> : null}
        {L.edges.map(e => { const g = edgePath(e, L); if (!g) return null; const col = speedColor(e.speed, e.kind);
          const dim = pathSet && !pathSet.has(e.id) ? ' dim-out' : '';
          return <g key={e.id} className={dim}>
            <path className={'edge' + (e.kind === 'wifi' || e.kind === 'mesh' ? ' wifi' : '') + (e.kind === 'remote' || e.extra || e.kind === 'lan' ? ' dashed' : '')} d={g.d} stroke={col} opacity={e.extra ? .55 : 1} />
            {(e.kind === 'wan' || (e.kind === 'wire' && e.speed >= 1000)) && !e.extra ? <path className="edge flow" d={g.d} stroke="#fff" opacity=".5" /> : null}
            {e.manual ? <path className="edge-hit" d={g.d} onClick={() => edgeClick(e)} /> : null}
            {e.sourcePort && !g.inside ? <g className="port-pill" transform={`translate(${g.lx - 14},${g.ly - 9})`}><rect width="28" height="18" rx="9" /><text x="14" y="12.5" textAnchor="middle">{e.sourcePort}</text></g> : null}
            {e.poeW > 0 && g.mx ? <g transform={`translate(${g.lx - 14 - 50},${g.ly - 9})`}><rect width="44" height="18" rx="9" fill="#ffd60a" /><text x="22" y="12.5" textAnchor="middle" fontSize="10" fontWeight="700" fill="#000">⚡{e.poeW}W</text></g> : null}
            {(e.label && (e.manual || e.kind === 'wan')) ? <text x={g.lx} y={g.ly - 14} fontSize="11" fill="var(--text2)" textAnchor="middle">{e.label}</text> : null}
          </g>; })}
        {Object.values(L.nodes).map(n => { const p = L.pos[n.id]; if (!p || p.rack) return null;
          return <MapNode key={n.id} n={n} p={p} sel={sel === n.id || searchHit.includes(n.id) || linking === n.id} dim={pathSet && !pathSet.has(n.id)}
            onDown={e => nodeDown(n.id, e)} onClick={() => nodeClick(n.id)} />; })}
      </g>
    </svg>
    <div className="map-legend legend">
      <span><i style={{ background: 'var(--green)' }} />1 Гбит</span><span><i style={{ background: 'var(--yellow)' }} />100 Мбит</span>
      <span><i style={{ background: 'var(--accent)' }} />Wi-Fi</span><span><i style={{ background: 'var(--teal)' }} />Mesh</span><span><i style={{ background: 'var(--purple)' }} />Интернет</span>
      <span><b style={{ color: '#ffd60a' }}>⚡</b>PoE</span></div>
    <div className="zoom-btns"><button className="btn" onClick={() => zoomAt(1.35)}>+</button><button className="btn" onClick={() => zoomAt(1 / 1.35)}>−</button></div>
    {selNode ? <NodeInfo n={selNode} L={L} data={data} devById={devById} onOpen={openDevice} onClose={() => setSel(null)} /> : null}
  </div>;
}

function RackBox({ L, data, devById, dimSet, onOpen, total }) {
  const h = total * M.RU;
  return <g className="rackbox">
    <rect className="frame" x={-14} y={-46} width={M.RW + 28} height={h + 60} rx={16} />
    <text x={0} y={-22} fontSize="14" fontWeight="700">{data.settings.title}</text>
    <text x={M.RW} y={-22} fontSize="11" textAnchor="end" className="usub">{total}U</text>
    {Array.from({ length: total }, (_, i) => <text key={i} x={-7} y={i * M.RU + M.RU / 2 + 3} fontSize="8" textAnchor="middle" className="usub">{i + 1}</text>)}
    {L.units.filter(u => (u.side || 'front') === 'front').map(u => {
      const d = devById[u.deviceId]; const st = d && d.state; const y = (u.uStart - 1) * M.RU; const hh = u.uSize * M.RU - 4;
      const dim = dimSet && !(d && dimSet.has('d:' + d.id));
      const kind = PASSIVE.includes(u.type) ? u.type : (d && d.kind) || u.type;
      return <g key={u.id} className={'u' + (dim ? ' dim-out' : '')} style={{ cursor: d ? 'pointer' : 'default' }} onClick={() => d && onOpen(d)}>
        <rect x={0} y={y} width={M.RW} height={hh} rx={6} />
        <rect x={0} y={y} width={4} height={hh} rx={2} fill={u.color || '#0a84ff'} stroke="none" />
        <g transform={`translate(12,${y + hh / 2 - 9})`}><Icon name={kind} size={18} color="#f5f5f7" /></g>
        <text x={38} y={y + (hh > 30 ? hh / 2 - 2 : hh / 2 + 4)} fontSize="12.5" fontWeight="600">{trunc(u.name, 30)}</text>
        {hh > 30 ? <text x={38} y={y + hh / 2 + 12} className="usub">{trunc(d ? deviceLine(d) : KIND_TEXT[u.type], 40)}</text> : null}
        {st ? <circle cx={M.RW - 12} cy={y + 11} r={4} fill={st.status === 'online' ? 'var(--green)' : st.status === 'warning' ? 'var(--orange)' : 'var(--red)'} /> : null}
        {st && (st.ports || []).length > 4 ? <g transform={`translate(${M.RW - 14 - Math.ceil(Math.min(st.ports.length, 28) / 2) * 7},${y + hh - 17})`}>
          {st.ports.slice(0, 28).map((p, i) => <rect key={i} x={Math.floor(i / 2) * 7} y={(i % 2) * 7} width={5} height={5} rx={1}
            fill={!p.link ? '#3a3a3c' : p.speed >= 1000 ? '#30d158' : p.speed >= 100 ? '#ffd60a' : '#ff9f0a'} stroke="none" />)}</g> : null}
      </g>;
    })}
  </g>;
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
    {dev ? <Btn kind="primary" style={{ width: '100%', marginTop: 12 }} onClick={() => onOpen(dev)}>Подробнее</Btn> : null}
    {!dev && pe && pe.sourcePort && parent && parent.deviceId ? <Btn style={{ width: '100%', marginTop: 12 }} onClick={() => onOpen(devById[parent.deviceId], 'ports', pe.sourcePort)}>Порт {pe.sourcePort} на {parent.label}</Btn> : null}
  </div>;
}
