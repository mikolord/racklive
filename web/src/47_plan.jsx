/* Floor plan: buildings → floors (and a yard) with walls and placed equipment */
const PG = 20;                                             // snap grid, world units
const uid = p => p + Math.random().toString(36).slice(2, 7);
const snap = v => Math.round(v / PG) * PG;

function placeStatus(rack, devById) {
  const sts = (rack.units || []).map(u => devById[u.deviceId] && devById[u.deviceId].state && devById[u.deviceId].state.status).filter(Boolean);
  return sts.includes('offline') ? 'offline' : sts.includes('warning') ? 'warning' : sts.length ? 'online' : '';
}

function PlanView() {
  const { data, edit, savePlan, openDevice, setTab } = useApp();
  const toast = useToast(); const confirm = useConfirm();
  const buildings = (data.plan && data.plan.buildings) || [];
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const [bid, setBid] = useState(buildings[0] && buildings[0].id);
  const b = buildings.find(x => x.id === bid) || buildings[0];
  const [fid, setFid] = useState(b && b.floors[0] && b.floors[0].id);
  const floor = b && (b.floors.find(f => f.id === fid) || b.floors[0]);
  const [tool, setTool] = useState('select');
  const [pending, setPending] = useState(null);           // ref waiting to be dropped on the plan
  const [wallPt, setWallPt] = useState(null);             // last point of the wall being drawn
  const [cursor, setCursor] = useState(null);
  const [view, setView] = useState({ x: 60, y: 60, k: 1 });
  const [sel, setSel] = useState(null);
  const wrap = useRef(null);
  useEffect(() => { if (!buildings.find(x => x.id === bid)) setBid(buildings[0] && buildings[0].id); }, [buildings.length]);
  useEffect(() => { if (b && !b.floors.find(f => f.id === fid)) setFid(b.floors[0] && b.floors[0].id); }, [bid, b && b.floors.length]);
  useEffect(() => { if (!edit) { setTool('select'); setPending(null); setWallPt(null); } }, [edit]);

  const mutate = fn => savePlan(buildings.map(x => x.id !== bid ? x : { ...x, floors: x.floors.map(f => f.id !== floor.id ? f : fn(f)) }));
  const addBuilding = () => { const id = uid('b'); savePlan([...buildings, { id, name: `Дом ${buildings.length + 1}`, floors: [{ id: uid('f'), name: '1 этаж', walls: [], items: [] }] }]); setBid(id); };
  const addFloor = (outdoor) => { const id = uid('f');
    savePlan(buildings.map(x => x.id !== bid ? x : { ...x, floors: [...x.floors, { id, name: outdoor ? 'Двор' : `${x.floors.filter(f => !f.outdoor).length + 1} этаж`, outdoor, walls: [], items: [] }] })); setFid(id); };

  const toWorld = e => { const r = wrap.current.getBoundingClientRect(); return { x: (e.clientX - r.left - view.x) / view.k, y: (e.clientY - r.top - view.y) / view.k }; };
  const onWheel = e => { e.preventDefault(); const r = wrap.current.getBoundingClientRect(); const mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.min(3, Math.max(.3, view.k * Math.exp(-e.deltaY * .0015)));
    setView(v => ({ k, x: mx - (mx - v.x) * k / v.k, y: my - (my - v.y) * k / v.k })); };
  useEffect(() => { const el = wrap.current; if (!el) return; el.addEventListener('wheel', onWheel, { passive: false }); return () => el.removeEventListener('wheel', onWheel); }, [view]);

  // background interactions: pan (select), draw wall, drop item, add label
  const panRef = useRef(null);
  const onDown = e => {
    if (e.target.closest('.plan-item')) return;
    const w = toWorld(e);
    if (tool === 'select') { panRef.current = { sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y }; setSel(null);
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {} return; }
    if (tool === 'wall') { const p = { x: snap(w.x), y: snap(w.y) };
      if (wallPt) mutate(f => ({ ...f, walls: [...f.walls, { x1: wallPt.x, y1: wallPt.y, x2: p.x, y2: p.y }] }));
      setWallPt(p); return; }
    if (tool === 'place' && pending) { mutate(f => ({ ...f, items: [...f.items, { id: uid('i'), kind: pending.kind, ref: pending.ref, x: snap(w.x), y: snap(w.y) }] }));
      setPending(null); setTool('select'); return; }
    if (tool === 'label') { const text = prompt('Название комнаты / подпись'); if (text) mutate(f => ({ ...f, items: [...f.items, { id: uid('i'), kind: 'label', text, x: snap(w.x), y: snap(w.y) }] })); return; }
  };
  const onMove = e => { setCursor(toWorld(e));
    if (panRef.current) { const p = panRef.current; setView(v => ({ ...v, x: p.vx + e.clientX - p.sx, y: p.vy + e.clientY - p.sy })); } };
  const onUp = e => { panRef.current = null; };
  const finishWall = () => setWallPt(null);

  // drag a placed item
  const dragItem = (it, e) => {
    if (!edit || tool === 'erase') { if (tool === 'erase') mutate(f => ({ ...f, items: f.items.filter(x => x.id !== it.id) })); else itemClick(it); return; }
    if (tool !== 'select') return;
    e.stopPropagation(); const start = toWorld(e); const o = { x: it.x, y: it.y }; let moved = false;
    const move = ev => { const w = toWorld(ev); moved = true; mutateLocal(it.id, { x: snap(o.x + w.x - start.x), y: snap(o.y + w.y - start.y) }); };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      if (!moved) itemClick(it); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const mutateLocal = (id, patch) => mutate(f => ({ ...f, items: f.items.map(x => x.id === id ? { ...x, ...patch } : x) }));
  const itemClick = it => {
    if (edit) { setSel(it.id); return; }
    if (it.kind === 'device') { const d = devById[it.ref]; if (d) openDevice(d); }
    else if (it.kind === 'place') setTab('rack');
  };
  const delItem = id => mutate(f => ({ ...f, items: f.items.filter(x => x.id !== id) }));
  const eraseWall = i => mutate(f => ({ ...f, walls: f.walls.filter((_, j) => j !== i) }));

  if (!buildings.length) return <div className="plan-empty card pad">
    <div style={{ fontSize: 42 }}>🏠</div>
    <div style={{ fontSize: 17, fontWeight: 700, margin: '8px 0 4px' }}>Плана пока нет</div>
    <div className="dim" style={{ marginBottom: 16, maxWidth: 420 }}>Нарисуйте дом, этажи и двор, начертите стены и расставьте шкафы, щитки и отдельные устройства по комнатам.</div>
    {edit ? <Btn kind="primary" icon="home" onClick={addBuilding}>Создать дом</Btn> : <div className="dim">Включите «Редактирование», чтобы начать.</div>}
  </div>;

  const placed = new Set(buildings.flatMap(x => x.floors).flatMap(f => f.items).map(i => i.ref));
  const palette = [...data.racks.map(r => ({ kind: 'place', ref: r.id, name: r.name, icon: (PLACE_KINDS[r.kind] || PLACE_KINDS.rack).icon })),
    ...data.devices.map(d => ({ kind: 'device', ref: d.id, name: d.name, icon: d.kind }))].filter(x => !placed.has(x.ref) || (pending && pending.ref === x.ref));

  return <div className="plan">
    <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
      {(buildings.length > 1 || edit) && buildings.map(x => <button key={x.id} className={'chip' + (x.id === bid ? ' on' : '')} onClick={() => setBid(x.id)}><Icon name="home" size={13} />{x.name}</button>)}
      {edit ? <Btn size="sm" icon="plus" onClick={addBuilding}>Дом</Btn> : null}
      <div className="grow" />
      {edit ? <button className="icon-link" title="Переименовать / удалить дом" onClick={async () => {
        const name = prompt('Название дома', b.name); if (name === null) return;
        if (name.trim()) savePlan(buildings.map(x => x.id === bid ? { ...x, name: name.trim() } : x));
      }}><Icon name="settings" size={16} /></button> : null}
    </div>
    <div className="row wrap" style={{ gap: 6, marginBottom: 10 }}>
      {b.floors.map(f => <button key={f.id} className={'chip' + (f.id === floor.id ? ' on' : '')} onClick={() => setFid(f.id)}>
        <Icon name={f.outdoor ? 'tree' : 'home'} size={13} />{f.name}</button>)}
      {edit ? <><Btn size="sm" icon="plus" onClick={() => addFloor(false)}>Этаж</Btn>
        {!b.floors.some(f => f.outdoor) ? <Btn size="sm" icon="tree" onClick={() => addFloor(true)}>Двор</Btn> : null}</> : null}
    </div>

    {edit ? <div className="plan-tools">
      <Seg value={tool} onChange={v => { setTool(v); setWallPt(null); setPending(null); }} options={[
        { value: 'select', label: 'Двигать', icon: 'cursor' }, { value: 'wall', label: 'Стена', icon: 'wall' },
        { value: 'place', label: 'Оборудование', icon: 'plus' }, { value: 'label', label: 'Комната', icon: 'tag' }, { value: 'erase', label: 'Удалить', icon: 'eraser' }]} />
      {tool === 'wall' && wallPt ? <Btn size="sm" onClick={finishWall}>Готово</Btn> : null}
      {sel ? <Btn size="sm" kind="danger" icon="trash" onClick={() => { delItem(sel); setSel(null); }}>Убрать</Btn> : null}
    </div> : null}

    {tool === 'place' && edit ? <div className="plan-palette card pad">
      <div className="dim" style={{ fontSize: 13, marginBottom: 8 }}>{pending ? 'Теперь нажмите на план, куда поставить' : 'Выберите, что разместить, затем нажмите на план:'}</div>
      <div className="row wrap" style={{ gap: 6 }}>{palette.map(p => <button key={p.ref} className={'chip' + (pending && pending.ref === p.ref ? ' on' : '')} onClick={() => setPending(p)}>
        <Icon name={p.icon} size={13} />{p.name}</button>)}
        {!palette.length ? <span className="dim" style={{ fontSize: 13 }}>Всё уже размещено</span> : null}</div>
    </div> : null}

    <div className={'plan-canvas' + (tool !== 'select' ? ' crosshair' : '')} ref={wrap}
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => setCursor(null)}>
      <svg>
        <defs><pattern id="pgrid" width={PG} height={PG} patternUnits="userSpaceOnUse" patternTransform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          <circle cx={1} cy={1} r={.8} fill="var(--line)" /></pattern></defs>
        <rect x={0} y={0} width="100%" height="100%" fill="url(#pgrid)" />
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {floor.outdoor ? <rect x={-40} y={-40} width={1400} height={1000} rx={16} fill="color-mix(in srgb, var(--green) 10%, transparent)" /> : null}
          {floor.walls.map((w, i) => <line key={i} className="plan-wall" x1={w.x1} y1={w.y1} x2={w.x2} y2={w.y2}
            onClick={() => tool === 'erase' && eraseWall(i)} style={{ cursor: tool === 'erase' ? 'pointer' : 'default' }} />)}
          {wallPt && cursor ? <line className="plan-wall draft" x1={wallPt.x} y1={wallPt.y} x2={snap(cursor.x)} y2={snap(cursor.y)} /> : null}
          {floor.items.map(it => <PlanItem key={it.id} it={it} devById={devById} racks={data.racks} sel={sel === it.id} edit={edit}
            onDown={e => dragItem(it, e)} />)}
        </g>
      </svg>
      {edit ? <div className="plan-hint">{tool === 'wall' ? 'Нажимайте, чтобы ставить углы стен · «Готово» завершает' :
        tool === 'place' ? 'Выберите в палитре и нажмите на план' : tool === 'label' ? 'Нажмите, где подписать комнату' :
        tool === 'erase' ? 'Нажмите на стену или устройство, чтобы убрать' : 'Тащите устройства · колесо — зум'}</div> : null}
      <div className="zoom-btns"><button className="btn" onClick={() => setView(v => ({ ...v, k: Math.min(3, v.k * 1.3) }))}>+</button>
        <button className="btn" onClick={() => setView(v => ({ ...v, k: Math.max(.3, v.k / 1.3) }))}>−</button></div>
    </div>
  </div>;
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
    {status ? <circle cx={15} cy={-15} r={5} fill={status === 'online' ? 'var(--green)' : status === 'warning' ? 'var(--orange)' : 'var(--red)'} stroke="var(--card-solid)" strokeWidth={2} /> : null}
    {isPlace ? <rect x={-14} y={14} width={28} height={10} rx={3} fill={col} opacity=".9" /> : null}
    {isPlace ? <text y={22} textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#fff">{(PLACE_KINDS[ref && ref.kind] || PLACE_KINDS.rack).label.split(' ')[0].toUpperCase()}</text> : null}
    <text className="pi-label" y={38} textAnchor="middle">{name.length > 16 ? name.slice(0, 15) + '…' : name}</text>
  </g>;
}
