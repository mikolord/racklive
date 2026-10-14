/* Rack view */
const U_PX = 46;
const PLACE_KINDS = { rack: { label: 'Стойка 19″', icon: 'rack', hint: 'Серверный шкаф с юнитами по U' },
  box: { label: 'Щиток / бокс', icon: 'box', hint: 'Настенный бокс, GPON-щиток — устройства плиткой' },
  place: { label: 'Комната', icon: 'home', hint: 'Оборудование разбросано — просто карточки устройств' } };
const placeKind = r => PLACE_KINDS[r.kind] || PLACE_KINDS.rack;
// what can stand in a place without a monitored device
const PLAIN_TYPES = ['patch', 'cross', 'shelf', 'ups', 'modem', 'pdu', 'organizer', 'blank', 'other'];
const OTHER_TYPES = ['other', 'router', 'switch', 'server', 'nas', 'nvr'];   // «Другое» without a device: say what it is
const PLAIN_HINT = { patch: 'подписи портов: куда идёт кабель', cross: 'волокна и магистрали', shelf: 'до 5 мелких устройств рядом',
  ups: 'нагрузка и сколько продержится', modem: 'ONT / модем провайдера', pdu: 'розетки', organizer: 'кабельный органайзер',
  blank: 'пустая панель', other: 'любое оборудование без мониторинга' };
const devUnitType = d => (UNIT_TYPES.includes(d.kind) ? d.kind : 'other');

// one tap between kinds (rack ⇄ box ⇄ room): devices stay, U positions / tile spots are recalculated;
// blanks and cable organizers only make sense in a 19″ rack and are dropped on the way out
const RACK_ONLY = ['blank', 'organizer'];
function convertPlace(rack, kind) {
  const from = rack.kind || 'rack';
  let units = [...rack.units];
  if (kind !== 'rack') {
    if (from === 'rack') units = units.sort((a, b) => (a.uStart || 0) - (b.uStart || 0)).filter(u => !RACK_ONLY.includes(u.type));
    return { ...rack, kind, units };
  }
  if (from === 'rack') return { ...rack, kind };
  // into a rack: top-down in tile order (row, then column; never-moved tiles keep their order at the end)
  const pos = u => (typeof u.y === 'number' ? u.y * 1e4 + (u.x || 0) : 1e12);
  units = units.map((u, i) => [u, i]).sort((a, b) => (pos(a[0]) - pos(b[0])) || (a[1] - b[1])).map(p => p[0]);
  let n = 1;
  units = units.map(u => { const s = u.uSize || 1; const r = { ...u, uStart: n, uSize: s, side: u.side || 'front' }; n += s; return r; });
  return { ...rack, kind, units, totalU: Math.max(rack.totalU || 12, 12, n - 1) };
}
const UNIT_COLORS = ['#0a84ff', '#30d158', '#bf5af2', '#ff9f0a', '#ff453a', '#64d2ff', '#5e5ce6', '#ffd60a', '#8e8e93'];

// a shelf holds up to 5 devices side by side (deviceIds); any other unit — one (deviceId)
const SHELF_MAX = 5;
const unitDevIds = u => (u && u.deviceIds && u.deviceIds.length ? u.deviceIds.slice(0, SHELF_MAX) : u && u.deviceId ? [u.deviceId] : []);

function deviceLine(dev) {
  if (!dev) return '';
  const st = dev.state || {}; const s = st.summary || {};
  if (st.status === 'offline') return st.error ? 'Нет связи · ' + st.error : 'Нет связи';
  if (st.ups) { const u = st.ups, m = u.runtimeMin;
    return [`${u.loadW} Вт${u.loadPct != null ? ` (${u.loadPct}%)` : ''}`, m != null ? `${u.runtimeEstimated ? '≈' : ''}${m >= 60 ? Math.floor(m / 60) + ' ч ' + (m % 60) + ' мин' : m + ' мин'}` : '',
      u.charge != null ? `заряд ${Math.round(u.charge)}%` : '', u.onBattery ? 'от батареи!' : ''].filter(Boolean).join(' · '); }
  const parts = [];
  const ports = st.ports || [];
  if (ports.length > 6) {
    parts.push(`${ports.filter(p => p.link).length}/${ports.length} портов`);
    const poe = ports.reduce((a, p) => a + (p.poeW || 0), 0); if (poe) parts.push(`PoE ${poe.toFixed(0)} Вт`);
  }
  if ((st.clients || []).length) parts.push(`${st.clients.length} клиентов`);
  if ((st.children || []).length) parts.push(`${st.children.length} точки`);
  if (s.cpu != null) parts.push(`CPU ${Math.round(s.cpu)}%`);
  if (s.temp != null) parts.push(`${s.temp}°C`);
  const vol = st.storage && (st.storage.volumes || [])[0];
  if (vol && vol.total) parts.push(`том ${Math.round(vol.used * 100 / vol.total)}%`);
  (st.metrics || []).slice(0, 2).forEach(m => { if (!parts.length || m.label === 'Недоступно') parts.push(`${m.label}: ${m.value}${m.unit ? ' ' + m.unit : ''}`); });
  if (!parts.length && s.fw) parts.push(s.fw);
  return parts.join(' · ');
}

function Leds({ ports, min = 4, round }) {
  if (!ports || ports.length < min) return null;
  const list = ports.filter(p => p.kind !== 'sfp').slice(0, 48);
  return <div className={'leds' + (round ? ' round' : '')} style={{ gridTemplateRows: list.length > 8 ? 'repeat(2, 7px)' : '7px' }}>
    {list.map(p => <i key={p.n} className={p.cls || (p.disabled ? 'off' : speedClass(p))} />)}</div>;
}

function RackUnit({ unit, dev, edit, onClick, onPointerDown, dragging, swap, top }) {
  const { data, openDevice } = useApp();
  const many = unitDevIds(unit);
  if (many.length > 1) {                          // a shelf with several devices: one cell each
    const h = unit.uSize * U_PX - 4;
    return <div className={['unit', 'shelf-multi', dragging ? 'dragging' : '', swap ? 'swap' : ''].join(' ')}
      style={{ top: top + 2, height: h, cursor: edit ? 'grab' : 'pointer' }} onClick={edit ? onClick : undefined} onPointerDown={onPointerDown}>
      <div className="strip" style={{ background: unit.color || '#0a84ff' }} />
      {many.map(id => { const d = data.devices.find(x => x.id === id); if (!d) return null; const st = (d.state || {}).status;
        return <div key={id} className="shelf-cell" onClick={e => { if (edit) return; e.stopPropagation(); openDevice(d); }}>
          <Icon name={d.kind} size={14} color="currentColor" />{st ? <span className={'dot ' + st} /> : null}<span className="ellipsis">{d.name}</span></div>; })}
    </div>;
  }
  const kind = PASSIVE.includes(unit.type) ? unit.type : (dev && dev.kind) || unit.type;
  // patch / cross / ONT: light each port by what is live at the other end (switch port, or cross → ONT → router)
  const pmPorts = pmLeds(data, unit);
  const st = dev && dev.state ? dev.state.status : null;
  const h = unit.uSize * U_PX - 4;
  return <div className={['unit', PASSIVE.includes(unit.type) ? 'passive' : '', unit.type === 'blank' ? 'blank' : '', dragging ? 'dragging' : '', swap ? 'swap' : ''].join(' ')}
    style={{ top: top + 2, height: h, cursor: edit ? 'grab' : 'pointer' }} onClick={onClick} onPointerDown={onPointerDown}>
    <div className="strip" style={{ background: unit.color || '#0a84ff' }} />
    {unit.type !== 'blank' ? <div className="uicon"><Icon name={kind} size={16} color="currentColor" /></div> : null}
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="row" style={{ gap: 7 }}>{st ? <span className={'dot ' + st} /> : null}<span className="uname ellipsis">{unit.name}</span></div>
      {h > 30 ? <div className="umeta ellipsis">{dev ? deviceLine(dev) : (KIND_TEXT[unit.type] || '') + (unit.uSize > 1 ? ` · ${unit.uSize}U` : '')
        + (unit.powerLoad && unit.powerLoad.w ? ` · ${unit.powerLoad.w} Вт` : '')}</div> : null}
    </div>
    {socketLeds(unit, dev) ? <Leds ports={socketLeds(unit, dev)} min={1} round />
      : <Leds ports={pmPorts || (dev && dev.state && dev.state.ports)} min={pmPorts ? 2 : 4} />}
  </div>
}

function RackView() {
  const { data, edit, saveRack, saveRacks, openDevice } = useApp();
  const [rackId, setRackId] = useState(() => { const p = new URLSearchParams(location.search).get('place'); return (data.racks.find(r => r.id === p) || data.racks[0]).id; });
  const [side, setSide] = useState('front');
  const [editing, setEditing] = useState(() => { const id = new URLSearchParams(location.search).get('editunit');   // unit being edited / created
    if (id === 'new' && edit) return { id: null, name: '', type: 'switch', uSize: 1, uStart: 1, side: 'front', color: '#0a84ff', deviceId: null, notes: '' };
    return id && edit ? data.racks.flatMap(r => r.units).find(u => u.id === id) || null : null; });
  const [info, setInfo] = useState(() => { const id = new URLSearchParams(location.search).get('unit');
    return id ? data.racks.flatMap(r => r.units).find(u => u.id === id) || null : null; });
  const [rackSettings, setRackSettings] = useState(null);
  const [moving, setMoving] = useState(() => new URLSearchParams(location.search).has('move'));   // «Переезд» rack ⇄ box ⇄ room
  const [drag, setDrag] = useState(null);              // {id, slot}
  const slotsRef = useRef(null);
  const toast = useToast(); const confirm = useConfirm();
  useEffect(() => { if (!data.racks.find(r => r.id === rackId)) setRackId(data.racks[0].id); }, [data.racks]);
  const rack = data.racks.find(r => r.id === rackId) || data.racks[0]; const total = rack.totalU;
  const minU = Math.max(1, ...rack.units.map(u => u.uStart + u.uSize - 1));
  const [newPlace, setNewPlace] = useState(false);
  const addPlace = (kind, name) => { const id = 'rack' + Date.now().toString(36);
    saveRacks([...data.racks, { id, name: name || PLACE_KINDS[kind].label, kind, totalU: kind === 'rack' ? 12 : 1, units: [] }]); setRackId(id); setNewPlace(false); };
  const units = rack.units.filter(u => (u.side || 'front') === side);
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));

  const occupied = (exceptId) => {
    const o = new Array(total + 2).fill(null);
    units.forEach(u => { if (u.id !== exceptId) for (let i = u.uStart; i < u.uStart + u.uSize; i++) o[i] = u.id; });
    return o;
  };
  const fits = (u, start, exceptId) => {
    if (start < 1 || start + u.uSize - 1 > total) return false;
    const o = occupied(exceptId); for (let i = start; i < start + u.uSize; i++) if (o[i]) return false; return true;
  };

  const startDrag = (u, e) => {
    if (!edit) return;
    e.preventDefault();
    const rect = slotsRef.current.getBoundingClientRect();
    const offset = Math.floor((e.clientY - rect.top) / U_PX) + 1 - u.uStart;
    let moved = false;
    const move = ev => { moved = true; const slot = Math.floor((ev.clientY - rect.top) / U_PX) + 1 - offset; setDrag({ id: u.id, slot }); };
    const up = ev => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      const slot = Math.floor((ev.clientY - rect.top) / U_PX) + 1 - offset;
      setDrag(null);
      if (!moved) { setEditing(u); return; }
      const plan = planMove(u, slot);
      if (plan) saveRack({ ...rack, units: rack.units.map(x => plan[x.id] ? { ...x, uStart: plan[x.id] } : x) });
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  // move into free space, or swap with the one unit sitting where it is dropped → {unitId: newStart}
  const planMove = (u, slot) => {
    if (slot === u.uStart) return null;
    if (fits(u, slot, u.id)) return { [u.id]: slot };
    const hit = units.filter(o => o.id !== u.id && o.uStart < slot + u.uSize && slot < o.uStart + o.uSize);
    if (hit.length !== 1) return null;
    const o = hit[0];
    const ok = (a, b) => {
      if (a < 1 || a + u.uSize - 1 > total || b < 1 || b + o.uSize - 1 > total) return false;
      if (a < b + o.uSize && b < a + u.uSize) return false;
      const busy = new Array(total + 2).fill(false);
      units.forEach(x => { if (x.id !== u.id && x.id !== o.id) for (let i = x.uStart; i < x.uStart + x.uSize; i++) busy[i] = true; });
      for (let i = a; i < a + u.uSize; i++) if (busy[i]) return false;
      for (let i = b; i < b + o.uSize; i++) if (busy[i]) return false;
      return true;
    };
    const top = Math.min(u.uStart, o.uStart);
    const cands = [[o.uStart, u.uStart],                                              // same top positions
      u.uStart < o.uStart ? [top + o.uSize, top] : [top, top + u.uSize],           // swap order in a contiguous block
      [o.uStart + o.uSize - u.uSize, u.uStart + u.uSize - o.uSize]];               // bottom-aligned
    const c = cands.find(([a, b]) => ok(a, b));
    return c ? { [u.id]: c[0], [o.id]: c[1] } : null;
  };

  const occ = occupied();
  const dragUnit = drag && units.find(u => u.id === drag.id);
  const dropPlan = dragUnit && planMove(dragUnit, drag.slot);
  const dropOk = !!dropPlan;
  const swapWith = dropPlan && Object.keys(dropPlan).length > 1 ? Object.keys(dropPlan).find(id => id !== drag.id) : null;

  const devices = data.devices; const problems = devices.filter(d => ['offline', 'warning'].includes(d.state && d.state.status));
  const allPorts = devices.flatMap(d => (d.state && d.state.ports) || []);
  const clients = devices.reduce((a, d) => a + ((d.state && d.state.clients) || []).length, 0);
  const poe = allPorts.reduce((a, p) => a + (p.poeW || 0), 0);

  const left = <div>
      {data.racks.length > 1 || edit ? <div className="row wrap rack-tabs" style={{ marginBottom: 12 }}>
        {data.racks.map(r => <button key={r.id} className={'chip' + (r.id === rackId ? ' on' : '')} onClick={() => setRackId(r.id)}>
          <Icon name={placeKind(r).icon} size={13} />{r.name}</button>)}
        {edit ? <Btn size="sm" icon="plus" onClick={() => setNewPlace(true)}>Место</Btn> : null}
      </div> : null}
      {rack.kind && rack.kind !== 'rack'
        ? <TileView rack={rack} edit={edit} devById={devById} openDevice={openDevice} onEdit={setEditing} onInfo={setInfo} onSettings={() => setRackSettings(rack)} onMove={() => setMoving(true)} />
        : <><div className="rack">
        <div className="rack-top"><div><div className="title">{rack.name}
          {edit ? <button className="icon-link" onClick={() => setRackSettings(rack)} title="Настройки шкафа"><Icon name="settings" size={15} /></button> : null}
          {edit ? <button className="icon-link" onClick={() => setMoving(true)} title="Переезд: сделать щитком или комнатой"><Icon name="swap" size={15} /><span className="move-lbl">Переезд</span></button> : null}</div>
          <div className="meta">{total}U · занято {occ.filter(Boolean).length}U · {side === 'front' ? 'вид спереди' : 'вид сзади'}</div></div>
          <Seg value={side} onChange={setSide} options={[{ value: 'front', label: 'Фронт' }, { value: 'back', label: 'Тыл' }]} />
        </div>
        <div className="rack-body" style={{ '--u': U_PX + 'px' }}>
          <div className="rack-rail">{Array.from({ length: total }, (_, i) => <div key={i}>{i + 1}</div>)}</div>
          <div className="rack-slots" ref={slotsRef}>
            {Array.from({ length: total }, (_, i) => {
              const n = i + 1; const inDrop = dragUnit && n >= drag.slot && n < drag.slot + dragUnit.uSize;
              return <div key={n} className={'rack-slot' + (inDrop && dropOk ? ' drop' : '') + (edit && !occ[n] ? ' addable' : '')}
                onClick={() => edit && !occ[n] && setEditing({ id: null, name: '', type: 'switch', uSize: 1, uStart: n, side, color: '#0a84ff', deviceId: null, notes: '' })} />;
            })}
            {units.map(u => <RackUnit key={u.id} unit={u} dev={devById[u.deviceId]} edit={edit} top={(u.uStart - 1) * U_PX}
              dragging={drag && drag.id === u.id} swap={swapWith === u.id}
              onPointerDown={e => startDrag(u, e)}
              onClick={() => { if (edit) return; const d = devById[u.deviceId]; d ? openDevice(d) : setInfo(u); }} />)}
          </div>
          <div className="rack-rail">{Array.from({ length: total }, (_, i) => <div key={i}>{i + 1}</div>)}</div>
        </div>
      </div>
      {edit ? <div className="row" style={{ marginTop: 12 }}>
        <Btn kind="primary" icon="plus" onClick={() => { const free = occ.findIndex((x, i) => i > 0 && i <= total && !x);
          setEditing({ id: null, name: '', type: 'switch', uSize: 1, uStart: free > 0 ? free : 1, side, color: '#0a84ff', deviceId: null, notes: '' }); }}>Юнит</Btn>
        <div className="grow" /><span className="dim" style={{ fontSize: 13 }}>Высота{minU > 1 ? ` (занято до U${minU})` : ''}</span>
        <select className="select" style={{ width: 96 }} value={total} onChange={e => {
          const n = +e.target.value;
          if (n < minU) { toast(`Нельзя меньше ${minU}U — внизу стоит оборудование. Сначала переместите его выше.`, true); return; }
          saveRack({ ...rack, totalU: n });
        }}>
          {[...new Set([6, 9, 12, 15, 18, 20, 22, 24, 27, 32, 36, 42, 45, 47, total])].sort((a, b) => a - b).map(n =>
            <option key={n} value={n} disabled={n < minU}>{n}U{n < minU ? ' — мало' : ''}</option>)}</select>
      </div> : <div className="dim" style={{ fontSize: 12.5, marginTop: 10, textAlign: 'center' }}>Нажмите на устройство, чтобы открыть подробности</div>}
      </>}
    </div>;
  const modals = <>
    {editing ? <UnitEditor unit={editing} rack={rack} onClose={() => setEditing(null)} fits={fits} /> : null}
    {rackSettings ? <RackSettings rack={rackSettings} canDelete={data.racks.length > 1} onClose={() => setRackSettings(null)}
      onSelect={setRackId} /> : null}
    {moving ? <PlaceMove rack={rack} onClose={() => setMoving(false)} /> : null}
    {newPlace ? <NewPlace onClose={() => setNewPlace(false)} onCreate={addPlace} /> : null}
    {info ? <Modal title={info.name} onClose={() => setInfo(null)} icon={<KindIcon kind={info.type} />} wide={!!info.portmap}>
      <KV rows={[['Тип', KIND_TEXT[info.type]], ...(rack.kind === 'rack' || !rack.kind ? [['Позиция', `U${info.uStart}${info.uSize > 1 ? '–' + (info.uStart + info.uSize - 1) : ''}`], ['Сторона', info.side === 'back' ? 'Тыл' : 'Фронт']] : [])]} />
      {info.portmap ? <PortMapView unit={info} /> : null}
      {info.type === 'pdu' ? (() => { const u = allUnits(data).find(x => x.id === info.id) || info; const pl = u.powerLoad || { w: 0, items: [], feeders: [] };
        return <div className="card pad">
          <div className="row between"><b>Нагрузка блока</b><b className="mono">{pl.w} Вт</b></div>
          <div className="dim3" style={{ fontSize: 12, margin: '2px 0 6px' }}>{pl.feeders && pl.feeders.length ? 'Питается от: ' + pl.feeders.map(f => `${f.name}${f.outlet ? ', гнездо ' + f.outlet : ''}`).join('; ') : 'Питание — прямо из сети 220 В'}</div>
          {pl.items.length ? <PowerTree items={pl.items} /> : <div className="dim" style={{ fontSize: 13 }}>Розетки пока не заполнены — «Редактирование» → этот юнит → «Что в каких розетках».</div>}</div>; })() : null}
      {info.notes ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }} className="card pad">{info.notes}</div> : null}
      {info.webUrl ? <a className="btn" href={info.webUrl} target="_blank" rel="noreferrer">Открыть веб-интерфейс</a> : null}
    </Modal> : null}
  </>;
  // «Главная»: the rack is one widget; the cards around it are widgets of their own
  return <>{left}{modals}</>;
}

/* Box / room: devices as free tiles you can drag around (edit mode), snapped to a grid */
const TW = 214, TH = 64, TGRID = 12;
function TileView({ rack, edit, devById, openDevice, onEdit, onInfo, onSettings, onMove }) {
  const { data, saveRack } = useApp();
  const kinfo = placeKind(rack);
  const linked = rack.units.filter(u => u.deviceId).length;
  const ref = useRef(null);
  const [w, setW] = useState(900);
  const [drag, setDrag] = useState(null);                 // {id, x, y}
  useEffect(() => { const el = ref.current; if (!el || !window.ResizeObserver) return;
    const ro = new ResizeObserver(es => setW(es[0].contentRect.width)); ro.observe(el); return () => ro.disconnect(); }, []);
  const cols = Math.max(1, Math.floor((w + TGRID) / (TW + TGRID)));
  // position each tile: its saved x/y, or an auto grid slot for ones never moved
  let auto = 0;
  const placed = rack.units.map(u => {
    if (typeof u.x === 'number' && typeof u.y === 'number') return { u, x: u.x, y: u.y };
    const c = auto % cols, r = Math.floor(auto / cols); auto++;
    return { u, x: c * (TW + TGRID), y: r * (TH + TGRID) };
  });
  const maxX = Math.max(0, w - TW);
  const height = Math.max(TH + TGRID, ...placed.map(p => p.y + TH)) + TGRID + (edit ? TH + TGRID : 0);
  const newTile = () => { const n = auto, c = n % cols, r = Math.floor(n / cols);
    onEdit({ id: null, name: '', type: 'router', uSize: 1, uStart: 1, side: 'front', color: '#0a84ff', deviceId: null, notes: '', x: c * (TW + TGRID), y: r * (TH + TGRID) }); };
  const start = (u, p, e) => {
    if (!edit) return; e.preventDefault(); e.stopPropagation();
    const sx = e.clientX, sy = e.clientY; let moved = false;
    const at = ev => ({ x: Math.min(maxX, Math.max(0, Math.round((p.x + ev.clientX - sx) / TGRID) * TGRID)), y: Math.max(0, Math.round((p.y + ev.clientY - sy) / TGRID) * TGRID) });
    const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 4) moved = true; if (moved) setDrag({ id: u.id, ...at(ev) }); };
    const up = ev => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      if (moved) { const np = at(ev); saveRack({ ...rack, units: rack.units.map(x => x.id === u.id ? { ...x, x: np.x, y: np.y } : x) }); }
      else onEdit(u);
      setDrag(null); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  return <div className="tilebox">
    <div className="rack-top"><div><div className="title row" style={{ gap: 8 }}><Icon name={kinfo.icon} size={17} />{rack.name}
      {edit ? <button className="icon-link" onClick={onSettings} title="Настройки места"><Icon name="settings" size={15} /></button> : null}
      {edit ? <button className="icon-link" onClick={onMove} title="Переезд: сменить тип места"><Icon name="swap" size={15} /><span className="move-lbl">Переезд</span></button> : null}</div>
      <div className="meta">{kinfo.label} · {linked} {linked === 1 ? 'устройство' : linked >= 2 && linked <= 4 ? 'устройства' : 'устройств'}{edit ? ' · перетаскивайте плитки' : ''}</div></div>
      {edit ? <Btn size="sm" icon="plus" onClick={newTile}>Оборудование</Btn> : null}</div>
    <div className={'tiles-canvas' + (edit ? ' editing' : '')} ref={ref} style={{ height }}>
      {placed.map(({ u, x, y }) => { const d = devById[u.deviceId]; const st = d && d.state; const kind = PASSIVE.includes(u.type) ? u.type : (d && d.kind) || u.type;
        const dp = drag && drag.id === u.id ? drag : null;
        return <div key={u.id} className={'tile free' + (PASSIVE.includes(u.type) ? ' passive' : '') + (dp ? ' grabbing' : '')}
          style={{ left: dp ? dp.x : x, top: dp ? dp.y : y, width: TW }}
          onPointerDown={e => start(u, { x, y }, e)} onClick={() => { if (edit) return; d ? openDevice(d) : onInfo(u); }}>
          <div className="strip" style={{ background: u.color || '#0a84ff' }} />
          <div className="row" style={{ gap: 9, minWidth: 0 }}><KindIcon kind={kind} size={32} round={9} />
            <div className="grow" style={{ minWidth: 0 }}><div className="row" style={{ gap: 6 }}>{st ? <span className={'dot ' + st.status} /> : null}<span className="ellipsis" style={{ fontWeight: 650, fontSize: 14 }}>{u.name}</span></div>
              <div className="dim ellipsis" style={{ fontSize: 12 }}>{d ? deviceLine(d) : KIND_TEXT[u.type]}</div></div></div>
          {socketLeds(u, d) ? <Leds ports={socketLeds(u, d)} min={1} round /> : <Leds ports={u.portmap ? pmLeds(data, u) : st && st.ports} min={u.portmap ? 2 : 4} />}
        </div>; })}
      {!rack.units.length ? <div className="empty" style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
        {edit ? 'Нажмите «Оборудование», чтобы добавить' : 'Пусто. Включите «Редактирование».'}</div> : null}
    </div>
  </div>;
}

function NewPlace({ onClose, onCreate }) {
  const [kind, setKind] = useState('rack'); const [name, setName] = useState('');
  return <Modal title="Новое место" onClose={onClose}
    footer={<><div className="grow" /><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={() => onCreate(kind, name.trim())}>Создать</Btn></>}>
    <div className="place-pick">{Object.entries(PLACE_KINDS).map(([k, v]) => <button key={k} className={'place-opt' + (kind === k ? ' on' : '')} onClick={() => setKind(k)}>
      <Icon name={v.icon} size={24} color={kind === k ? 'var(--accent)' : 'var(--text2)'} /><div><b>{v.label}</b><small>{v.hint}</small></div></button>)}</div>
    <Field label="Название" hint="Например «Серверная», «Щиток у входа», «Квартира»"><input className="input" value={name} autoFocus placeholder={PLACE_KINDS[kind].label} onChange={e => setName(e.target.value)} /></Field>
  </Modal>;
}

/* «Переезд»: one tap turns a rack into a box / room (or back) — devices, port maps and links stay */
function PlaceMove({ rack, onClose }) {
  const { saveRack } = useApp(); const toast = useToast();
  const cur = rack.kind || 'rack';
  const dropped = rack.units.filter(u => RACK_ONLY.includes(u.type)).length;
  const go = k => { saveRack(convertPlace(rack, k)); toast(`«${rack.name}» теперь: ${PLACE_KINDS[k].label.toLowerCase()}`); onClose(); };
  return <Modal title={`Переезд «${rack.name}»`} onClose={onClose}>
    <div className="dim" style={{ fontSize: 13.5 }}>Сейчас: {PLACE_KINDS[cur].label}. Устройства, подписи портов и связи на карте сохранятся.</div>
    <div className="place-pick">{Object.entries(PLACE_KINDS).filter(([k]) => k !== cur).map(([k, v]) => <button key={k} className="place-opt" onClick={() => go(k)}>
      <Icon name={v.icon} size={24} color="var(--accent)" /><div><b>Сделать: {v.label.toLowerCase()}</b><small>{
        k === 'rack' ? 'Оборудование встанет в юниты сверху вниз — потом поправьте высоту и позиции'
          : cur === 'rack' ? `Юниты станут плитками в том же порядке${dropped ? ` · заглушки и органайзеры (${dropped}) уберутся` : ''}`
          : v.hint}</small></div></button>)}</div>
  </Modal>;
}

function RackSettings({ rack, canDelete, onClose, onSelect }) {
  const { data, saveRack, saveRacks } = useApp(); const confirm = useConfirm(); const toast = useToast();
  const [name, setName] = useState(rack.name);
  const [kind, setKind] = useState(rack.kind || 'rack');
  const used = rack.units.filter(u => u.deviceId).length;
  const save = () => {
    const r = kind !== (rack.kind || 'rack') ? convertPlace(rack, kind) : rack;
    saveRack({ ...r, name: name.trim() || 'Место' }); onClose();
  };
  const del = async () => {
    if (!(await confirm(`Удалить шкаф «${rack.name}»? Его юниты будут удалены${used ? `, ${used} устройств отвяжутся (сами устройства останутся)` : ''}.`, { danger: true, ok: 'Удалить шкаф' }))) return;
    const rest = data.racks.filter(r => r.id !== rack.id); onSelect(rest[0].id); saveRacks(rest); onClose();
  };
  return <Modal title="Настройки шкафа" onClose={onClose}
    footer={<>{canDelete ? <Btn kind="danger" icon="trash" onClick={del}>Удалить шкаф</Btn> : null}<div className="grow" /><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={save}>Сохранить</Btn></>}>
    <Field label="Название" hint="Например «Серверная», «Щиток у входа», «Квартира»"><input className="input" value={name} autoFocus onChange={e => setName(e.target.value)} /></Field>
    <Field label="Тип места"><div className="place-pick">{Object.entries(PLACE_KINDS).map(([k, v]) => <button key={k} className={'place-opt' + (kind === k ? ' on' : '')} onClick={() => setKind(k)}>
      <Icon name={v.icon} size={22} color={kind === k ? 'var(--accent)' : 'var(--text2)'} /><div><b>{v.label}</b><small>{v.hint}</small></div></button>)}</div></Field>
    {kind === 'rack' && rack.kind && rack.kind !== 'rack' && used ? <div className="dim" style={{ fontSize: 13 }}>При переходе в стойку устройства встанут в юниты по порядку — потом поправьте позиции.</div> : null}
    {!canDelete ? <div className="dim" style={{ fontSize: 13 }}>Это единственное место — удалить нельзя. Добавьте ещё одно кнопкой «+ Место».</div> : null}
  </Modal>;
}

function UnitEditor({ unit, rack, onClose, fits }) {
  const { data, saveRack, refresh, openEditor } = useApp();
  const confirm = useConfirm(); const toast = useToast();
  const [f, setF] = useState({ ...unit });
  const [addDev, setAddDev] = useState(false);
  const [pmOpen, setPmOpen] = useState(() => new URLSearchParams(location.search).has('pm'));
  const [pwOpen, setPwOpen] = useState(() => new URLSearchParams(location.search).has('pw'));
  const pw = f.type === 'pdu' ? (f.power || pduDefault()) : null;
  const pwFilled = pw ? Object.values(pw.ports || {}).filter(p => p && (p.dev || p.pdu || p.label || p.w)).length : 0;
  const [autoUps, setAutoUps] = useState(true);              // a UPS needs no connection data → create its device automatically
  const [picking, setPicking] = useState(!unit.id);          // new unit → first «Что ставим?»
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const dev = f.type !== 'shelf' && f.deviceId ? data.devices.find(d => d.id === f.deviceId) : null;
  const placedIn = id => { const pl = data.racks.find(r => r.units.some(x => x.id !== unit.id && unitDevIds(x).includes(id))); return pl ? pl.name : null; };
  const pickDev = d => { setF(x => ({ ...x, deviceId: d.id, deviceIds: undefined, type: devUnitType(d), name: d.name })); setPicking(false); };
  const pickType = t => { setF(x => ({ ...x, deviceId: null, deviceIds: undefined, type: t, name: x.deviceId ? '' : x.name })); setPicking(false); };
  const pm = isPortMap(f.type) ? (f.portmap || pmDefault(f.type)) : null;
  const setPm = (k, v) => set('portmap', { ...pm, [k]: v });
  const pmFilled = pm ? Object.values(pm.ports || {}).filter(m => m && (m.label || m.dev)).length : 0;
  const isRack = rack.kind === 'rack' || !rack.kind;         // box / place don't use U positions
  const ok = !isRack || fits(f, +f.uStart, unit.id);
  const save = async () => {
    const u = { ...f, uStart: +f.uStart, uSize: +f.uSize, name: f.name.trim() || (f.deviceId ? (data.devices.find(d => d.id === f.deviceId) || {}).name : KIND_TEXT[f.type]) };
    if (u.type !== 'shelf') delete u.deviceIds;           // only a shelf holds several devices
    if (isPortMap(u.type)) u.portmap = pm; else delete u.portmap;
    if (u.type === 'pdu') u.power = pw; else delete u.power;
    delete u.powerLoad;                                   // computed by the server for display
    let fillUps = null;                                    // a plain UPS (no data cable): open its form right away to type the sticker data
    if (u.type === 'ups' && !u.deviceId && autoUps) {
      // an UPS device nobody uses yet is reused — never a second empty one
      const spare = data.devices.find(d => d.driver === 'ups' && !data.racks.some(r => r.units.some(x => x.deviceId === d.id)));
      if (spare) { u.deviceId = spare.id; fillUps = spare; }
      else try { const r = await api('/api/devices', { method: 'POST', body: { driver: 'ups', name: u.name, kind: 'ups', mode: 'manual', batteryV: '12', batteryAh: '9', batteryCount: '1', enabled: true, location: 'local' } });
        u.deviceId = r.device.id; fillUps = r.device; refresh(); }
      catch (e) { toast(e.message, true); }
    }
    const units = unit.id ? rack.units.map(x => x.id === unit.id ? u : x) : [...rack.units, { ...u, id: 'u' + Date.now().toString(36) }];
    saveRack({ ...rack, units }); onClose();
    if (fillUps) setTimeout(() => { toast('Укажите данные ИБП с наклейки — мощность, аккумулятор, что подключено'); openEditor(fillUps); }, 250);
  };
  const del = async () => { if (await confirm(`Убрать «${unit.name}»?`, { danger: true, ok: 'Убрать' })) { saveRack({ ...rack, units: rack.units.filter(x => x.id !== unit.id) }); onClose(); } };
  const localDevs = data.devices.filter(d => d.location !== 'remote');           // remote devices live only in the «Устройства» list
  const remoteCount = data.devices.length - localDevs.length;
  const newDev = addDev ? <DeviceEditor device={null} onClose={() => setAddDev(false)} onCreated={d => {
    refresh(); if (d.location === 'remote') toast('Удалённое устройство добавлено в «Устройства» — в шкаф, щиток и комнату оно не ставится', true); else pickDev(d); }} /> : null;

  // step 1: pick what stands here — one of your devices (live data comes by itself) or plain equipment
  if (picking) {
    const devs = [...localDevs].sort((a, b) => (!!placedIn(a.id) - !!placedIn(b.id)) || a.name.localeCompare(b.name));
    const plain = PLAIN_TYPES.filter(t => isRack || !RACK_ONLY.includes(t));
    return <Modal title={isRack ? 'Что ставим в шкаф?' : 'Что ставим?'} wide onClose={unit.id ? () => setPicking(false) : onClose}>
      <div className="up-sec">Ваши устройства <small>живые данные появятся сами{remoteCount ? ` · удалённые (${remoteCount}) сюда не ставятся — они в списке «Устройства»` : ''}</small></div>
      <div className="unit-pick">
        {devs.map(d => { const pl = placedIn(d.id);
          return <button key={d.id} className={'up-opt' + (pl ? ' placed' : '') + (f.deviceId === d.id ? ' on' : '')} onClick={() => pickDev(d)}>
            <KindIcon kind={d.kind} size={32} round={9} /><div><b>{d.name}</b><small>{pl ? `уже стоит в «${pl}»` : KIND_TEXT[d.kind] || ''}</small></div></button>; })}
        <button className="up-opt add" onClick={() => setAddDev(true)}><span className="up-plus"><Icon name="plus" size={18} /></span>
          <div><b>Новое устройство</b><small>введите адрес — тип определится сам</small></div></button>
      </div>
      <div className="up-sec">Без данных <small>просто показать, что тут стоит</small></div>
      <div className="unit-pick">{plain.map(t => <button key={t} className={'up-opt' + (!f.deviceId && f.type === t && unit.id ? ' on' : '')} onClick={() => pickType(t)}>
        <KindIcon kind={t} size={32} round={9} /><div><b>{KIND_TEXT[t]}</b><small>{PLAIN_HINT[t]}</small></div></button>)}</div>
      {newDev}
    </Modal>;
  }

  return <Modal title={unit.id ? (isRack ? 'Юнит' : 'Оборудование') : (isRack ? 'Новый юнит' : 'Новое оборудование')} onClose={onClose}
    footer={<>{unit.id ? <Btn kind="danger" icon="trash" onClick={del}>Убрать</Btn> : null}<div className="grow" /><Btn onClick={onClose}>Отмена</Btn>
      <Btn kind="primary" onClick={save} disabled={!ok}>Сохранить</Btn></>}>
    <div className="up-what">
      <KindIcon kind={dev ? dev.kind : f.type} size={38} round={10} />
      <div className="grow" style={{ minWidth: 0 }}><b className="ellipsis">{dev ? dev.name : KIND_TEXT[f.type]}</b>
        <small>{dev ? <>{dev.state ? <span className={'dot ' + dev.state.status} /> : null}живые данные с устройства</>
          : f.type === 'shelf' ? 'отметьте, что на ней стоит' : 'без данных — просто отметка'}</small></div>
      <Btn size="sm" onClick={() => setPicking(true)}>Заменить</Btn></div>
    {f.type === 'shelf' ? <Field label={`Устройства на полке · до ${SHELF_MAX}`} hint="Мелкие устройства рядом на одной полке (роутер, мини-ПК, модем…): в шкафу и на карте у каждого своя ячейка.">
      <div className="shelf-pick">{localDevs.map(d => { const ids = unitDevIds(f); const on = ids.includes(d.id);
        return <label key={d.id} className={'chip' + (on ? ' on' : '')} style={{ opacity: !on && ids.length >= SHELF_MAX ? .4 : 1 }}>
          <input type="checkbox" checked={on} disabled={!on && ids.length >= SHELF_MAX} style={{ display: 'none' }}
            onChange={() => { const next = on ? ids.filter(x => x !== d.id) : [...ids, d.id]; setF(x => ({ ...x, deviceIds: next, deviceId: next[0] || null })); }} />
          <Icon name={d.kind} size={13} />{d.name}</label>; })}</div></Field> : null}
    {!f.deviceId && f.type === 'ups' ? <label className="row" style={{ gap: 8, fontSize: 13.5, cursor: 'pointer' }}>
      <Switch on={autoUps} onChange={setAutoUps} /><span>Показывать нагрузку и сколько продержится — после «Сохранить» откроется форма: мощность с наклейки и что подключено</span></label> : null}
    {(() => { const where = unitDevIds(f).map(id => { const pl = data.racks.find(r => r.units.some(x => x.id !== unit.id && unitDevIds(x).includes(id)));
        return pl ? `«${(data.devices.find(d => d.id === id) || {}).name}» уже стоит в «${pl.name}»` : null; }).filter(Boolean);
      return where.length ? <div className="warn-box"><Icon name="alert" size={16} /><div>{where.join('; ')}. Одно устройство лучше держать в одном месте —
        на карте оно будет показано там, где указано первым (шкаф раньше щитка и комнаты).</div></div> : null; })()}
    <Field label={dev ? 'Подпись' : 'Название'}><input className="input" value={f.name} onChange={e => set('name', e.target.value)} placeholder={dev ? dev.name : 'Например, Коммутатор ядра'} /></Field>
    <div className="row" style={{ alignItems: 'flex-start' }}>
      {!dev && (f.type === 'other' || !PLAIN_TYPES.includes(f.type)) ? <Field label="Что это"><select className="select" value={f.type} onChange={e => set('type', e.target.value)}>
        {OTHER_TYPES.map(t => <option key={t} value={t}>{KIND_TEXT[t]}</option>)}</select></Field> : null}
      {isRack ? <Field label="Высота"><select className="select" value={f.uSize} onChange={e => set('uSize', +e.target.value)}>{[1, 2, 3, 4, 5, 6, 8, 10].map(n => <option key={n} value={n}>{n}U</option>)}</select></Field> : null}
      {isRack ? <Field label="Позиция"><select className="select" value={f.uStart} onChange={e => set('uStart', +e.target.value)}>{Array.from({ length: rack.totalU }, (_, i) => <option key={i} value={i + 1}>U{i + 1}</option>)}</select></Field> : null}
    </div>
    {!ok ? <div style={{ color: 'var(--red)', fontSize: 13 }}>На этом месте не хватает свободных юнитов</div> : null}
    {!dev && f.type !== 'shelf' && f.type !== 'ups' && !PASSIVE.includes(f.type) ? <Field label="Потребление питания" hint="Нужно для расчёта ИБП и блоков розеток. Например, ONT: на блоке питания «Output 12 V, 1 A» — впишите 12 и 1.">
      <SpecInputs spec={f.pwr} onChange={s => set('pwr', s)} /></Field> : null}
    {pm && f.type === 'modem' ? <OntSetup pm={pm} selfId={unit.id} onChange={v => set('portmap', v)} /> : null}
    {pm && f.type !== 'modem' ? <div className="card pad" style={{ background: 'var(--fill)', border: 0 }}>
      <div className="card-title" style={{ marginBottom: 8 }}>{PM_TITLE[f.type]}</div>
      <div className="row wrap" style={{ alignItems: 'flex-start' }}>
        <Field label={f.type === 'cross' ? 'Портов (волокон)' : f.type === 'modem' ? 'Гнёзд' : 'Портов'}><select className="select" value={pm.count} onChange={e => setPm('count', +e.target.value)}>
          {(f.type === 'cross' ? CROSS_COUNTS : f.type === 'modem' ? MODEM_COUNTS : PATCH_COUNTS).map(n => <option key={n} value={n}>{n}</option>)}</select></Field>
        {f.type === 'cross' ? <><Field label="Разъём"><select className="select" value={pm.connector || 'SC'} onChange={e => setPm('connector', e.target.value)}>
          {CONNECTORS.map(c => <option key={c}>{c}</option>)}</select></Field>
          <Field label="Волокно"><select className="select" value={pm.fiber || 'SM'} onChange={e => setPm('fiber', e.target.value)}>
            <option value="SM">Одномод (SM, жёлтый кабель)</option><option value="MM">Многомод (MM, оранжевый / бирюзовый)</option></select></Field></> : null}
      </div>
      <Btn icon="edit" onClick={() => setPmOpen(true)}>{f.type === 'modem' ? 'Гнёзда и подключения' : 'Распиновка портов'} · подписано {pmFilled} из {pm.count}</Btn>
    </div> : null}
    {pmOpen ? <PortMapEditor unit={{ ...f, portmap: pm }} onClose={() => setPmOpen(false)} onSave={v => set('portmap', v)} /> : null}
    {pw ? <div className="card pad" style={{ background: 'var(--fill)', border: 0 }}>
      <div className="card-title" style={{ marginBottom: 8 }}>Розетки блока</div>
      <div className="row wrap" style={{ alignItems: 'flex-start' }}>
        <Field label="Розеток"><select className="select" value={pw.count} onChange={e => set('power', { ...pw, count: +e.target.value })}>
          {PDU_COUNTS.map(n => <option key={n} value={n}>{n}</option>)}</select></Field></div>
      <Btn icon="bolt" onClick={() => setPwOpen(true)}>Что в каких розетках · занято {pwFilled} из {pw.count}</Btn>
      {unit.powerLoad && unit.powerLoad.w ? <div className="dim" style={{ fontSize: 13, marginTop: 8 }}>Сейчас нагрузка ≈ {unit.powerLoad.w} Вт</div> : null}
    </div> : null}
    {pwOpen ? <PowerEditor unit={{ ...f, power: pw, powerLoad: unit.powerLoad }} onClose={() => setPwOpen(false)} onSave={v => set('power', v)} /> : null}
    {isRack ? <Field label="Сторона"><Seg value={f.side || 'front'} onChange={v => set('side', v)} options={[{ value: 'front', label: 'Фронт' }, { value: 'back', label: 'Тыл' }]} /></Field> : null}
    <Field label="Цвет"><div className="row">{UNIT_COLORS.map(c => <button key={c} onClick={() => set('color', c)} style={{ width: 28, height: 28, borderRadius: 8, border: f.color === c ? '3px solid var(--text)' : '0', background: c, cursor: 'pointer' }} />)}</div></Field>
    {dev || PASSIVE.includes(f.type) ? null : <Field label="Ссылка на веб-интерфейс"><input className="input" value={f.webUrl || ''} onChange={e => set('webUrl', e.target.value)} placeholder="http://192.168.1.1" /></Field>}
    <Field label="Заметки"><textarea className="textarea" value={f.notes || ''} onChange={e => set('notes', e.target.value)} /></Field>
  </Modal>;
}
