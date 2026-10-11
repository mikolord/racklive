/* Floor plan: territory (buildings + backbone) → a building's floors (walls, rooms, equipment) */
const PG = 20;
const uid = p => p + Math.random().toString(36).slice(2, 7);
const snap = v => Math.round(v / PG) * PG;
const clampK = k => Math.min(3, Math.max(.25, k));

function placeStatus(rack, devById) {
  const s = (rack.units || []).map(u => devById[u.deviceId] && devById[u.deviceId].state && devById[u.deviceId].state.status).filter(Boolean);
  return s.includes('offline') ? 'offline' : s.includes('warning') ? 'warning' : s.length ? 'online' : '';
}
function floorDevices(f, data, devById) {
  const out = [];
  (f.items || []).forEach(it => {
    if (it.kind === 'device' && devById[it.ref]) out.push(devById[it.ref]);
    if (it.kind === 'place') { const r = data.racks.find(x => x.id === it.ref); (r ? r.units : []).forEach(u => devById[u.deviceId] && out.push(devById[u.deviceId])); }
  });
  return out;
}
function worst(devs) { const s = devs.map(d => d.state && d.state.status).filter(Boolean);
  return s.includes('offline') ? 'offline' : s.includes('warning') ? 'warning' : s.length ? 'online' : ''; }
const statusColor = s => s === 'online' ? 'var(--green)' : s === 'warning' ? 'var(--orange)' : s === 'offline' ? 'var(--red)' : 'var(--text3)';

/* pan + wheel + pinch, with tap / drag-draw callbacks (opts read fresh each render) */
function usePanZoom(wrapRef, opts, initial) {
  const [view, setView] = useState(initial || { x: 60, y: 60, k: 1 });
  const vr = useRef(view); vr.current = view;
  const or = useRef(opts); or.current = opts;
  const ptrs = useRef({}); const mode = useRef(null);
  const toWorld = (cx, cy) => { const r = wrapRef.current.getBoundingClientRect(); return { x: (cx - r.left - vr.current.x) / vr.current.k, y: (cy - r.top - vr.current.y) / vr.current.k }; };
  const wheel = e => { e.preventDefault(); const r = wrapRef.current.getBoundingClientRect(); const mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = clampK(vr.current.k * Math.exp(-e.deltaY * .0015)); setView(v => ({ k, x: mx - (mx - v.x) * k / v.k, y: my - (my - v.y) * k / v.k })); };
  useEffect(() => { const el = wrapRef.current; if (!el) return; el.addEventListener('wheel', wheel, { passive: false }); return () => el.removeEventListener('wheel', wheel); }, []);
  const pinchBase = () => { const p = Object.values(ptrs.current); const r = wrapRef.current.getBoundingClientRect();
    return { pinch: true, dist: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1, cx: (p[0].x + p[1].x) / 2 - r.left, cy: (p[0].y + p[1].y) / 2 - r.top, v: { ...vr.current } }; };
  const down = e => {
    if (e.target.closest('.plan-item, .plan-room')) return;
    ptrs.current[e.pointerId] = { x: e.clientX, y: e.clientY };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}
    if (Object.keys(ptrs.current).length >= 2) { mode.current = pinchBase(); return; }
    mode.current = { pinch: false, sx: e.clientX, sy: e.clientY, vx: vr.current.x, vy: vr.current.y, moved: false, w0: toWorld(e.clientX, e.clientY), drawing: false };
  };
  const move = e => {
    if (!ptrs.current[e.pointerId]) return; ptrs.current[e.pointerId] = { x: e.clientX, y: e.clientY };
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
    const m = mode.current; delete ptrs.current[e.pointerId];
    const left = Object.keys(ptrs.current).length;
    if (left === 0) { const o = or.current;
      if (m && !m.pinch) { if (m.drawing && o.onDraw) o.onDraw(m.w0, toWorld(e.clientX, e.clientY), true); else if (!m.moved && o.onTap) o.onTap(m.w0); }
      mode.current = null;
    } else if (left === 1) { const p = Object.values(ptrs.current)[0]; mode.current = { pinch: false, sx: p.x, sy: p.y, vx: vr.current.x, vy: vr.current.y, moved: true }; }
  };
  return { view, setView, toWorld, bind: { onPointerDown: down, onPointerMove: move, onPointerUp: up, onPointerCancel: up } };
}

function ZoomBtns({ setView }) {
  return <div className="zoom-btns"><button className="btn" onClick={() => setView(v => ({ ...v, k: clampK(v.k * 1.3) }))}>+</button>
    <button className="btn" onClick={() => setView(v => ({ ...v, k: clampK(v.k / 1.3) }))}>−</button></div>;
}

function PlanView() {
  const { data, edit } = useApp();
  const plan = data.plan || { buildings: [], links: [] };
  const buildings = plan.buildings || [];
  const deep = new URLSearchParams(location.search).get('building');
  const [level, setLevel] = useState(deep && buildings.find(b => b.id === deep) ? 'building' : 'territory');
  const [bid, setBid] = useState((deep && buildings.find(b => b.id === deep) && deep) || (buildings[0] && buildings[0].id));
  useEffect(() => { if (level === 'building' && !buildings.find(x => x.id === bid)) setLevel('territory'); }, [buildings.length]);

  if (!buildings.length) return <Territory plan={plan} enter={() => {}} />;
  if (level === 'building') { const b = buildings.find(x => x.id === bid) || buildings[0];
    return <BuildingPlan building={b} plan={plan} back={() => setLevel('territory')} />; }
  return <Territory plan={plan} enter={id => { setBid(id); setLevel('building'); }} />;
}

/* ───────── territory: buildings + backbone links ───────── */
const BW = 240, BH = 150;
function Territory({ plan, enter }) {
  const { data, edit, savePlan } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const buildings = plan.buildings || []; const links = plan.links || [];
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const wrap = useRef(null);
  const [tool, setTool] = useState('select');               // select | link
  const [linkFrom, setLinkFrom] = useState(null);
  const [sel, setSel] = useState(null);
  const save = (b, l) => savePlan({ buildings: b || buildings, links: l || links });
  const pos = b => ({ x: typeof b.x === 'number' ? b.x : 40 + (buildings.indexOf(b) % 3) * (BW + 80), y: typeof b.y === 'number' ? b.y : 40 + Math.floor(buildings.indexOf(b) / 3) * (BH + 120) });
  const { view, setView, bind } = usePanZoom(wrap, { canPan: () => tool === 'select', onTap: () => setSel(null) });

  const addBuilding = () => { const id = uid('b'); const n = buildings.length;
    save([...buildings, { id, name: `Дом ${n + 1}`, x: 40 + (n % 3) * (BW + 80), y: 40 + Math.floor(n / 3) * (BH + 120),
      floors: [{ id: uid('f'), name: '1 этаж', walls: [], rooms: [], items: [] }] }]); };
  const delBuilding = async id => { const b = buildings.find(x => x.id === id);
    if (!(await confirm(`Удалить дом «${b.name}» со всеми этажами? Оборудование и шкафы останутся — удалится только их размещение на плане.`, { danger: true, ok: 'Удалить дом' }))) return;
    save(buildings.filter(x => x.id !== id), links.filter(l => l.from !== id && l.to !== id)); setSel(null); };
  const dragB = (b, e) => {
    if (tool === 'link') { if (!linkFrom) { setLinkFrom(b.id); toast('Теперь выберите второй дом'); } else if (linkFrom !== b.id) {
        const label = prompt('Подпись магистрали (например «Оптика 1 Гбит»)', '') || '';
        save(null, [...links, { id: uid('l'), from: linkFrom, to: b.id, label }]); setLinkFrom(null); } else setLinkFrom(null); return; }
    if (!edit) { enter(b.id); return; }
    e.stopPropagation(); const p = pos(b); const r = wrap.current.getBoundingClientRect();
    const sx = e.clientX, sy = e.clientY; let moved = false;
    const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 5) moved = true; if (moved) {
      const nx = snap(p.x + (ev.clientX - sx) / view.k), ny = snap(p.y + (ev.clientY - sy) / view.k);
      savePlan({ buildings: buildings.map(x => x.id === b.id ? { ...x, x: nx, y: ny } : x), links }); } };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) { setSel(b.id); } };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };

  if (!buildings.length) return <div className="plan-empty card pad">
    <div style={{ fontSize: 42 }}>🏠</div><div style={{ fontSize: 17, fontWeight: 700, margin: '8px 0 4px' }}>Плана пока нет</div>
    <div className="dim" style={{ marginBottom: 16, maxWidth: 440 }}>Добавьте дом, нарисуйте этажи и двор, начертите комнаты и расставьте шкафы, щитки и устройства. Несколько домов можно соединить магистралью.</div>
    {edit ? <Btn kind="primary" icon="home" onClick={addBuilding}>Создать дом</Btn> : <div className="dim">Включите «Редактирование», чтобы начать.</div>}
  </div>;

  const center = b => { const p = pos(b); return { x: p.x + BW / 2, y: p.y + BH / 2 }; };
  const selB = buildings.find(b => b.id === sel);
  return <div className="plan">
    {edit ? <div className="plan-tools">
      <Seg value={tool} onChange={v => { setTool(v); setLinkFrom(null); }} options={[{ value: 'select', label: 'Дома', icon: 'cursor' }, { value: 'link', label: 'Магистраль', icon: 'link' }]} />
      <Btn size="sm" icon="plus" onClick={addBuilding}>Дом</Btn>
      {selB ? <><span className="dim" style={{ fontSize: 13 }}>·</span>
        <Btn size="sm" onClick={() => { const name = prompt('Название дома', selB.name); if (name && name.trim()) save(buildings.map(x => x.id === sel ? { ...x, name: name.trim() } : x)); }}>Переименовать</Btn>
        <Btn size="sm" kind="danger" icon="trash" onClick={() => delBuilding(sel)}>Удалить дом</Btn></> : null}
    </div> : null}
    {linkFrom ? <div className="toast" style={{ marginBottom: 8 }}><Icon name="link" size={15} />Выберите второй дом для магистрали</div> : null}
    <div className="plan-canvas" ref={wrap} {...bind}>
      <svg>
        <defs><pattern id="pgridT" width={PG} height={PG} patternUnits="userSpaceOnUse" patternTransform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <circle cx={1} cy={1} r={.8} fill="var(--line)" /></pattern></defs>
        <rect x={0} y={0} width="100%" height="100%" fill="url(#pgridT)" />
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {links.map(l => { const a = buildings.find(x => x.id === l.from), b = buildings.find(x => x.id === l.to); if (!a || !b) return null;
            const c1 = center(a), c2 = center(b); return <g key={l.id}>
              <line x1={c1.x} y1={c1.y} x2={c2.x} y2={c2.y} className="plan-link" onClick={() => edit && confirm('Удалить магистраль?', { danger: true, ok: 'Удалить' }).then(ok => ok && save(null, links.filter(x => x.id !== l.id)))} />
              {l.label ? <text x={(c1.x + c2.x) / 2} y={(c1.y + c2.y) / 2 - 8} textAnchor="middle" className="plan-link-label">{l.label}</text> : null}</g>; })}
          {buildings.map(b => { const p = pos(b); const devs = (b.floors || []).flatMap(f => floorDevices(f, data, devById)); const st = worst(devs);
            const hasYard = (b.floors || []).some(f => f.outdoor);
            return <g key={b.id} className={'plan-item plan-building' + (sel === b.id ? ' sel' : '') + (linkFrom === b.id ? ' sel' : '')} transform={`translate(${p.x},${p.y})`}
              onPointerDown={e => dragB(b, e)} style={{ cursor: edit && tool === 'select' ? 'move' : 'pointer' }}>
              {hasYard ? <rect x={-18} y={-18} width={BW + 36} height={BH + 36} rx={18} className="plan-yard" /> : null}
              <rect x={0} y={0} width={BW} height={BH} rx={14} className="pi-card" />
              <g transform="translate(18,18)"><Icon name="home" size={26} color="var(--accent)" /></g>
              <text x={54} y={30} className="pb-name">{b.name.length > 20 ? b.name.slice(0, 19) + '…' : b.name}</text>
              <text x={54} y={50} className="pb-sub">{(b.floors || []).length} эт.{hasYard ? ' · двор' : ''} · {devs.length} устр.</text>
              <circle cx={BW - 20} cy={22} r={6} fill={statusColor(st)} />
              <text x={18} y={BH - 18} className="pb-hint">{edit ? 'перетащите · нажмите — внутрь' : 'нажмите, чтобы зайти'}</text>
            </g>; })}
        </g>
      </svg>
      <ZoomBtns setView={setView} />
    </div>
  </div>;
}

/* ───────── one building: floors with walls, rooms, equipment ───────── */
function BuildingPlan({ building, plan, back }) {
  const { data, edit, savePlan, openDevice, setTab } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const buildings = plan.buildings; const links = plan.links || [];
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const [fid, setFid] = useState(building.floors[0] && building.floors[0].id);
  const floor = building.floors.find(f => f.id === fid) || building.floors[0];
  const [tool, setTool] = useState('select');               // select | room | wall | place | erase
  const [pending, setPending] = useState(null);
  const [wallPt, setWallPt] = useState(null);
  const [draft, setDraft] = useState(null);                 // room rubber-band {x,y,w,h}
  const [sel, setSel] = useState(null);
  const [ghost, setGhost] = useState(false);
  const wrap = useRef(null);
  useEffect(() => { if (!building.floors.find(f => f.id === fid)) setFid(building.floors[0] && building.floors[0].id); }, [building.floors.length]);
  useEffect(() => { if (!edit) { setTool('select'); setPending(null); setWallPt(null); } }, [edit]);

  const saveFloors = floors => savePlan({ buildings: buildings.map(b => b.id === building.id ? { ...b, floors } : b), links });
  const mutate = fn => saveFloors(building.floors.map(f => f.id === floor.id ? fn(f) : f));
  const addFloor = outdoor => { const id = uid('f');
    saveFloors([...building.floors, { id, name: outdoor ? 'Двор' : `${building.floors.filter(f => !f.outdoor).length + 1} этаж`, outdoor, walls: [], rooms: [], items: [] }]); setFid(id); };
  const delFloor = async () => { if (building.floors.length < 2) return toast('Нельзя удалить единственный этаж', true);
    if (!(await confirm(`Удалить «${floor.name}»?`, { danger: true, ok: 'Удалить' }))) return;
    const rest = building.floors.filter(f => f.id !== floor.id); setFid(rest[0].id); saveFloors(rest); };

  const onTap = w => {
    if (tool === 'wall') { const p = { x: snap(w.x), y: snap(w.y) }; if (wallPt) mutate(f => ({ ...f, walls: [...(f.walls || []), { x1: wallPt.x, y1: wallPt.y, x2: p.x, y2: p.y }] })); setWallPt(p); return; }
    if (tool === 'place' && pending) { mutate(f => ({ ...f, items: [...f.items, { id: uid('i'), kind: pending.kind, ref: pending.ref, x: snap(w.x), y: snap(w.y) }] })); setPending(null); setTool('select'); return; }
    if (tool === 'select') setSel(null);
  };
  const onDraw = (w0, w1, end) => {                          // room rectangle rubber-band
    if (tool !== 'room') return;
    const x = snap(Math.min(w0.x, w1.x)), y = snap(Math.min(w0.y, w1.y)), ww = snap(Math.abs(w1.x - w0.x)), hh = snap(Math.abs(w1.y - w0.y));
    if (!end) { setDraft({ x, y, w: ww, h: hh }); return; }
    setDraft(null); if (ww < PG || hh < PG) return;
    const text = prompt('Название комнаты', '') || '';
    mutate(f => ({ ...f, rooms: [...(f.rooms || []), { id: uid('r'), x, y, w: ww, h: hh, text, color: '#0a84ff' }] }));
  };
  const { view, setView, toWorld, bind } = usePanZoom(wrap, { canPan: () => tool === 'select', onTap, onDraw: tool === 'room' ? onDraw : null });

  const dragItem = (it, e) => {
    if (tool === 'erase') { mutate(f => ({ ...f, items: f.items.filter(x => x.id !== it.id) })); return; }
    if (!edit) { if (it.kind === 'device') { const d = devById[it.ref]; if (d) openDevice(d); } else if (it.kind === 'place') setTab('rack'); return; }
    if (tool !== 'select') return;
    e.stopPropagation(); const s = toWorld(e.clientX, e.clientY); const o = { x: it.x, y: it.y }; let moved = false;
    const move = ev => { const w = toWorld(ev.clientX, ev.clientY); moved = true; mutate(f => ({ ...f, items: f.items.map(x => x.id === it.id ? { ...x, x: snap(o.x + w.x - s.x), y: snap(o.y + w.y - s.y) } : x) })); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) setSel(it.id); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const dragRoom = (rm, e) => {
    if (tool === 'erase') { mutate(f => ({ ...f, rooms: f.rooms.filter(x => x.id !== rm.id) })); return; }
    if (!edit || tool !== 'select') return;
    e.stopPropagation(); const s = toWorld(e.clientX, e.clientY); const o = { x: rm.x, y: rm.y }; let moved = false;
    const move = ev => { const w = toWorld(ev.clientX, ev.clientY); moved = true; mutate(f => ({ ...f, rooms: f.rooms.map(x => x.id === rm.id ? { ...x, x: snap(o.x + w.x - s.x), y: snap(o.y + w.y - s.y) } : x) })); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (!moved) setSel('room:' + rm.id); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const eraseWall = i => mutate(f => ({ ...f, walls: f.walls.filter((_, j) => j !== i) }));
  const removeSel = () => { if (!sel) return; if (sel.startsWith('room:')) mutate(f => ({ ...f, rooms: f.rooms.filter(r => 'room:' + r.id !== sel) })); else mutate(f => ({ ...f, items: f.items.filter(i => i.id !== sel) })); setSel(null); };

  const placedRefs = new Set(buildings.flatMap(b => b.floors).flatMap(f => f.items).filter(i => i.kind !== 'label').map(i => i.ref));
  const palette = [...data.racks.map(r => ({ kind: 'place', ref: r.id, name: r.name, icon: (PLACE_KINDS[r.kind] || PLACE_KINDS.rack).icon })),
    ...data.devices.map(d => ({ kind: 'device', ref: d.id, name: d.name, icon: d.kind }))].filter(x => !placedRefs.has(x.ref) || (pending && pending.ref === x.ref));
  const others = ghost ? building.floors.filter(f => f.id !== floor.id && f.outdoor === floor.outdoor) : [];

  return <div className="plan">
    <div className="row wrap" style={{ gap: 8, marginBottom: 10, alignItems: 'center' }}>
      <Btn size="sm" icon="chevron" onClick={back} style={{ transform: 'none' }}><span style={{ transform: 'scaleX(-1)', display: 'inline-block' }}>›</span> Все дома</Btn>
      <b style={{ fontSize: 15 }}>{building.name}</b>
      <div className="grow" />
      {edit ? <label className="row" style={{ gap: 6, fontSize: 13, cursor: 'pointer' }}><Switch on={ghost} onChange={setGhost} /><span className="dim">соседний этаж</span></label> : null}
    </div>
    <div className="row wrap" style={{ gap: 6, marginBottom: 10 }}>
      {building.floors.map(f => <button key={f.id} className={'chip' + (f.id === floor.id ? ' on' : '')} onClick={() => setFid(f.id)}>
        <Icon name={f.outdoor ? 'tree' : 'home'} size={13} />{f.name}</button>)}
      {edit ? <><Btn size="sm" icon="plus" onClick={() => addFloor(false)}>Этаж</Btn>
        {!building.floors.some(f => f.outdoor) ? <Btn size="sm" icon="tree" onClick={() => addFloor(true)}>Двор</Btn> : null}
        {building.floors.length > 1 ? <Btn size="sm" kind="danger" icon="trash" onClick={delFloor} title="Удалить этаж" /> : null}</> : null}
    </div>
    {edit ? <div className="plan-tools">
      <Seg value={tool} onChange={v => { setTool(v); setWallPt(null); setPending(null); }} options={[
        { value: 'select', label: 'Двигать', icon: 'cursor' }, { value: 'room', label: 'Комната', icon: 'tag' },
        { value: 'wall', label: 'Стена', icon: 'wall' }, { value: 'place', label: 'Оборудование', icon: 'plus' }, { value: 'erase', label: 'Удалить', icon: 'eraser' }]} />
      {tool === 'wall' && wallPt ? <Btn size="sm" onClick={() => setWallPt(null)}>Готово</Btn> : null}
      {sel ? <Btn size="sm" kind="danger" icon="trash" onClick={removeSel}>Убрать</Btn> : null}
    </div> : null}
    {tool === 'place' && edit ? <div className="plan-palette card pad">
      <div className="dim" style={{ fontSize: 13, marginBottom: 8 }}>{pending ? 'Теперь нажмите на план, куда поставить' : 'Выберите, что разместить:'}</div>
      <div className="row wrap" style={{ gap: 6 }}>{palette.map(p => <button key={p.ref} className={'chip' + (pending && pending.ref === p.ref ? ' on' : '')} onClick={() => setPending(p)}><Icon name={p.icon} size={13} />{p.name}</button>)}
        {!palette.length ? <span className="dim" style={{ fontSize: 13 }}>Всё уже размещено. Нет нужного? Добавьте устройство на вкладке «Устройства» (можно «Пинг»/«Агент» как заглушку).</span> : null}</div>
    </div> : null}

    <div className={'plan-canvas' + (tool !== 'select' ? ' crosshair' : '')} ref={wrap} {...bind}>
      <svg>
        <defs><pattern id="pgridB" width={PG} height={PG} patternUnits="userSpaceOnUse" patternTransform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <circle cx={1} cy={1} r={.8} fill="var(--line)" /></pattern></defs>
        <rect x={0} y={0} width="100%" height="100%" fill="url(#pgridB)" />
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {floor.outdoor ? <rect x={-60} y={-60} width={1600} height={1100} rx={16} fill="color-mix(in srgb, var(--green) 10%, transparent)" /> : null}
          <g className="ghost">
            {others.flatMap(f => (f.rooms || []).map(r => <rect key={f.id + r.id} x={r.x} y={r.y} width={r.w} height={r.h} rx={6} className="plan-room-ghost" />))}
            {others.flatMap(f => (f.walls || []).map((w, i) => <line key={f.id + 'w' + i} x1={w.x1} y1={w.y1} x2={w.x2} y2={w.y2} className="plan-wall ghost" />))}
            {others.flatMap(f => (f.items || []).map(it => <circle key={f.id + it.id} cx={it.x} cy={it.y} r={16} className="plan-item-ghost" />))}
          </g>
          {(floor.rooms || []).map(r => <g key={r.id} className={'plan-room' + (sel === 'room:' + r.id ? ' sel' : '')} onPointerDown={e => dragRoom(r, e)} style={{ cursor: edit && tool === 'select' ? 'move' : tool === 'erase' ? 'pointer' : 'default' }}>
            <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={6} style={{ fill: `color-mix(in srgb, ${r.color || '#0a84ff'} 9%, transparent)`, stroke: `color-mix(in srgb, ${r.color || '#0a84ff'} 45%, transparent)` }} />
            {r.text ? <text x={r.x + 8} y={r.y + 17} className="plan-room-label">{r.text}</text> : null}</g>)}
          {draft ? <rect x={draft.x} y={draft.y} width={draft.w} height={draft.h} rx={6} className="plan-room-draft" /> : null}
          {(floor.walls || []).map((w, i) => <line key={i} className="plan-wall" x1={w.x1} y1={w.y1} x2={w.x2} y2={w.y2}
            onClick={() => tool === 'erase' && eraseWall(i)} style={{ cursor: tool === 'erase' ? 'pointer' : 'default' }} />)}
          {wallPt ? <PlanWallDraft wallPt={wallPt} wrap={wrap} view={view} /> : null}
          {(floor.items || []).map(it => <PlanItem key={it.id} it={it} devById={devById} racks={data.racks} sel={sel === it.id} edit={edit} onDown={e => dragItem(it, e)} />)}
        </g>
      </svg>
      {edit ? <div className="plan-hint">{tool === 'wall' ? 'Нажимайте, чтобы ставить углы · «Готово» завершает' : tool === 'room' ? 'Обведите прямоугольник комнаты' :
        tool === 'place' ? 'Выберите в палитре и нажмите на план' : tool === 'erase' ? 'Нажмите на стену, комнату или устройство' : 'Тащите устройства · два пальца / колесо — зум'}</div> : null}
      <ZoomBtns setView={setView} />
    </div>
  </div>;
}

function PlanWallDraft({ wallPt, wrap, view }) {
  const [c, setC] = useState(null);
  useEffect(() => { const el = wrap.current; if (!el) return;
    const h = e => { const r = el.getBoundingClientRect(); setC({ x: snap((e.clientX - r.left - view.x) / view.k), y: snap((e.clientY - r.top - view.y) / view.k) }); };
    el.addEventListener('pointermove', h); return () => el.removeEventListener('pointermove', h); }, [view, wrap]);
  if (!c) return null;
  return <line className="plan-wall draft" x1={wallPt.x} y1={wallPt.y} x2={c.x} y2={c.y} />;
}

function PlanItem({ it, devById, racks, sel, edit, onDown }) {
  if (it.kind === 'label') return <g className="plan-item plan-label" transform={`translate(${it.x},${it.y})`} onPointerDown={onDown}>
    <text textAnchor="middle" className={sel ? 'sel' : ''}>{it.text}</text></g>;
  const isPlace = it.kind === 'place';
  const ref = isPlace ? racks.find(r => r.id === it.ref) : devById[it.ref];
  const name = ref ? ref.name : '—';
  const kind = isPlace ? (ref ? (PLACE_KINDS[ref.kind] || PLACE_KINDS.rack).icon : 'rack') : (ref ? ref.kind : 'other');
  const status = isPlace ? (ref ? placeStatus(ref, devById) : '') : (ref && ref.state ? ref.state.status : '');
  const col = KIND_COLOR[kind] || KIND_COLOR.other;
  return <g className={'plan-item' + (sel ? ' sel' : '')} transform={`translate(${it.x},${it.y})`} onPointerDown={onDown} style={{ cursor: edit ? 'move' : 'pointer' }}>
    <circle r={21} className="pi-bg" style={{ fill: `color-mix(in srgb, ${col} 22%, var(--card-solid))`, stroke: col }} />
    <g transform="translate(-11,-11)"><Icon name={kind} size={22} color={col} /></g>
    {status ? <circle cx={15} cy={-15} r={5} fill={statusColor(status)} stroke="var(--card-solid)" strokeWidth={2} /> : null}
    {isPlace && ref ? <><rect x={-16} y={14} width={32} height={10} rx={3} fill={col} opacity=".9" />
      <text y={22} textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#fff">{(PLACE_KINDS[ref.kind] || PLACE_KINDS.rack).label.split(' ')[0].toUpperCase()}</text></> : null}
    <text className="pi-label" y={38} textAnchor="middle">{name.length > 16 ? name.slice(0, 15) + '…' : name}</text>
  </g>;
}
