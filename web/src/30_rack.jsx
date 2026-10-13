/* Rack view */
const U_PX = 46;
const PLACE_KINDS = { rack: { label: 'Стойка 19″', icon: 'rack', hint: 'Серверный шкаф с юнитами по U' },
  box: { label: 'Щиток / бокс', icon: 'box', hint: 'Настенный бокс, GPON-щиток — устройства плиткой' },
  place: { label: 'Комната', icon: 'home', hint: 'Оборудование разбросано — просто карточки устройств' } };
const placeKind = r => PLACE_KINDS[r.kind] || PLACE_KINDS.rack;
// unit type → the connection that usually fits it (offered when a unit has no device yet)
const UNIT_DRIVER = { ups: 'ups', server: 'ssh', nas: 'synology', router: 'keenetic', switch: 'tplink_jetstream', modem: 'ping', nvr: 'ping', pdu: 'snmp' };
const UNIT_COLORS = ['#0a84ff', '#30d158', '#bf5af2', '#ff9f0a', '#ff453a', '#64d2ff', '#5e5ce6', '#ffd60a', '#8e8e93'];

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

function Leds({ ports }) {
  if (!ports || ports.length < 4) return null;
  const list = ports.filter(p => p.kind !== 'sfp').slice(0, 48);
  return <div className="leds" style={{ gridTemplateRows: list.length > 8 ? 'repeat(2, 7px)' : '7px' }}>
    {list.map(p => <i key={p.n} className={p.disabled ? 'off' : speedClass(p)} />)}</div>;
}

function RackUnit({ unit, dev, edit, onClick, onPointerDown, dragging, swap, top }) {
  const { data } = useApp();
  const kind = PASSIVE.includes(unit.type) ? unit.type : (dev && dev.kind) || unit.type;
  // patch / cross: light each port by the switch port it is wired to
  const pmPorts = unit.portmap ? Array.from({ length: unit.portmap.count }, (_, i) => { const lp = linkedPort(data, (unit.portmap.ports || {})[i + 1]);
    return { n: i + 1, kind: 'rj45', link: !!(lp && lp.p && lp.p.link), speed: lp && lp.p ? lp.p.speed : 0 }; }) : null;
  const st = dev && dev.state ? dev.state.status : null;
  const h = unit.uSize * U_PX - 4;
  return <div className={['unit', PASSIVE.includes(unit.type) ? 'passive' : '', unit.type === 'blank' ? 'blank' : '', dragging ? 'dragging' : '', swap ? 'swap' : ''].join(' ')}
    style={{ top: top + 2, height: h, cursor: edit ? 'grab' : 'pointer' }} onClick={onClick} onPointerDown={onPointerDown}>
    <div className="strip" style={{ background: unit.color || '#0a84ff' }} />
    {unit.type !== 'blank' ? <div className="uicon"><Icon name={kind} size={16} color="currentColor" /></div> : null}
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="row" style={{ gap: 7 }}>{st ? <span className={'dot ' + st} /> : null}<span className="uname ellipsis">{unit.name}</span></div>
      {h > 30 ? <div className="umeta ellipsis">{dev ? deviceLine(dev) : (KIND_TEXT[unit.type] || '') + (unit.uSize > 1 ? ` · ${unit.uSize}U` : '')}</div> : null}
    </div>
    <Leds ports={pmPorts || (dev && dev.state && dev.state.ports)} />
  </div>;
}

function RackView() {
  const { data, edit, saveRack, saveRacks, openDevice } = useApp();
  const [rackId, setRackId] = useState(() => { const p = new URLSearchParams(location.search).get('place'); return (data.racks.find(r => r.id === p) || data.racks[0]).id; });
  const [side, setSide] = useState('front');
  const [editing, setEditing] = useState(() => { const id = new URLSearchParams(location.search).get('editunit');   // unit being edited / created
    return id && edit ? data.racks.flatMap(r => r.units).find(u => u.id === id) || null : null; });
  const [info, setInfo] = useState(() => { const id = new URLSearchParams(location.search).get('unit');
    return id ? data.racks.flatMap(r => r.units).find(u => u.id === id) || null : null; });
  const [rackSettings, setRackSettings] = useState(null);
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
        ? <TileView rack={rack} edit={edit} devById={devById} openDevice={openDevice} onEdit={setEditing} onInfo={setInfo} onSettings={() => setRackSettings(rack)} />
        : <><div className="rack">
        <div className="rack-top"><div><div className="title">{rack.name}
          {edit ? <button className="icon-link" onClick={() => setRackSettings(rack)} title="Настройки шкафа"><Icon name="settings" size={15} /></button> : null}</div>
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
    {newPlace ? <NewPlace onClose={() => setNewPlace(false)} onCreate={addPlace} /> : null}
    {info ? <Modal title={info.name} onClose={() => setInfo(null)} icon={<KindIcon kind={info.type} />} wide={!!info.portmap}>
      <KV rows={[['Тип', KIND_TEXT[info.type]], ...(rack.kind === 'rack' || !rack.kind ? [['Позиция', `U${info.uStart}${info.uSize > 1 ? '–' + (info.uStart + info.uSize - 1) : ''}`], ['Сторона', info.side === 'back' ? 'Тыл' : 'Фронт']] : [])]} />
      {info.portmap ? <PortMapView unit={info} /> : null}
      {info.notes ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }} className="card pad">{info.notes}</div> : null}
      {info.webUrl ? <a className="btn" href={info.webUrl} target="_blank" rel="noreferrer">Открыть веб-интерфейс</a> : null}
    </Modal> : null}
  </>;
  // «Главная»: the rack is one widget; the cards around it are widgets of their own
  return <>{left}{modals}</>;
}

/* Box / room: devices as free tiles you can drag around (edit mode), snapped to a grid */
const TW = 214, TH = 64, TGRID = 12;
function TileView({ rack, edit, devById, openDevice, onEdit, onInfo, onSettings }) {
  const { saveRack } = useApp();
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
      {edit ? <button className="icon-link" onClick={onSettings} title="Настройки места"><Icon name="settings" size={15} /></button> : null}</div>
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
          <Leds ports={st && st.ports} />
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

function RackSettings({ rack, canDelete, onClose, onSelect }) {
  const { data, saveRack, saveRacks } = useApp(); const confirm = useConfirm(); const toast = useToast();
  const [name, setName] = useState(rack.name);
  const [kind, setKind] = useState(rack.kind || 'rack');
  const used = rack.units.filter(u => u.deviceId).length;
  const save = () => {
    const r = { ...rack, name: name.trim() || 'Место', kind };
    if (kind === 'rack' && rack.kind && rack.kind !== 'rack') {   // give devices real U positions
      let u = 1; r.units = rack.units.map(x => ({ ...x, uStart: u++, uSize: x.uSize || 1, side: x.side || 'front' }));
      r.totalU = Math.max(12, r.units.length);
    }
    saveRack(r); onClose();
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
  const { data, saveRack, refresh } = useApp();
  const confirm = useConfirm(); const toast = useToast();
  const [f, setF] = useState({ ...unit });
  const [addDev, setAddDev] = useState(false);
  const [pmOpen, setPmOpen] = useState(() => new URLSearchParams(location.search).has('pm'));
  const [autoUps, setAutoUps] = useState(true);              // a UPS needs no connection data → create its device automatically
  const sugg = UNIT_DRIVER[f.type]; const suggDrv = sugg && data.drivers.find(d => d.id === sugg && !d.hidden);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const pm = isPortMap(f.type) ? (f.portmap || pmDefault(f.type)) : null;
  const setPm = (k, v) => set('portmap', { ...pm, [k]: v });
  const pmFilled = pm ? Object.values(pm.ports || {}).filter(m => m && (m.label || m.dev)).length : 0;
  const isRack = rack.kind === 'rack' || !rack.kind;         // box / place don't use U positions
  const ok = !isRack || fits(f, +f.uStart, unit.id);
  const save = async () => {
    const u = { ...f, uStart: +f.uStart, uSize: +f.uSize, name: f.name.trim() || (f.deviceId ? (data.devices.find(d => d.id === f.deviceId) || {}).name : KIND_TEXT[f.type]) };
    if (isPortMap(u.type)) u.portmap = pm; else delete u.portmap;
    if (u.type === 'ups' && !u.deviceId && autoUps) {
      try { const r = await api('/api/devices', { method: 'POST', body: { driver: 'ups', name: u.name, kind: 'ups', mode: 'manual', batteryV: '12', batteryAh: '9', batteryCount: '1', enabled: true, location: 'local' } });
        u.deviceId = r.device.id; toast('ИБП добавлен в «Устройства» — откройте его и отметьте, что подключено'); refresh(); }
      catch (e) { toast(e.message, true); }
    }
    const units = unit.id ? rack.units.map(x => x.id === unit.id ? u : x) : [...rack.units, { ...u, id: 'u' + Date.now().toString(36) }];
    saveRack({ ...rack, units }); onClose();
  };
  const del = async () => { if (await confirm(`Убрать «${unit.name}»?`, { danger: true, ok: 'Убрать' })) { saveRack({ ...rack, units: rack.units.filter(x => x.id !== unit.id) }); onClose(); } };
  return <Modal title={unit.id ? (isRack ? 'Юнит' : 'Оборудование') : (isRack ? 'Новый юнит' : 'Новое оборудование')} onClose={onClose}
    footer={<>{unit.id ? <Btn kind="danger" icon="trash" onClick={del}>Убрать</Btn> : null}<div className="grow" /><Btn onClick={onClose}>Отмена</Btn>
      <Btn kind="primary" onClick={save} disabled={!ok}>Сохранить</Btn></>}>
    <Field label="Связанное устройство" hint="Живые данные этого устройства будут показаны на юните. Нет нужного? Создайте новое прямо здесь — оно сразу привяжется к юниту.">
      <div className="row" style={{ gap: 8 }}>
        <select className="select grow" value={f.deviceId || ''} onChange={e => { const d = data.devices.find(x => x.id === e.target.value);
          setF(x => ({ ...x, deviceId: e.target.value || null, name: x.name || (d ? d.name : ''), type: d && UNIT_TYPES.includes(d.kind) ? d.kind : x.type })); }}>
          <option value="">— не связан (пассивное оборудование) —</option>
          {data.devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <Btn icon="plus" onClick={() => setAddDev(true)} title="Добавить новое устройство">Устройство</Btn>
      </div></Field>
    {!f.deviceId && f.type === 'ups' ? <label className="row" style={{ gap: 8, fontSize: 13.5, cursor: 'pointer' }}>
      <Switch on={autoUps} onChange={setAutoUps} /><span>Следить за ИБП — добавить его в «Устройства» (нагрузка, сколько продержится)</span></label> : null}
    {!f.deviceId && suggDrv && f.type !== 'ups' ? <div className="unit-hint">
      <Icon name="pulse" size={15} /><span className="grow">Сейчас это просто место в шкафу. Чтобы видеть живые данные, подключите устройство:</span>
      <Btn size="sm" kind="primary" onClick={() => setAddDev(true)}>{suggDrv.title}</Btn></div> : null}
    {addDev ? <DeviceEditor device={null} preset={suggDrv ? { driver: suggDrv.id, name: f.name || '', kind: f.type } : null} onClose={() => setAddDev(false)} onCreated={d => {
      setF(x => ({ ...x, deviceId: d.id, name: x.name && x.name !== KIND_TEXT[x.type] ? x.name : d.name,
        type: UNIT_TYPES.includes(d.kind) ? d.kind : x.type })); }} /> : null}
    <Field label="Название"><input className="input" value={f.name} onChange={e => set('name', e.target.value)} placeholder="Например, Коммутатор ядра" /></Field>
    <div className="row" style={{ alignItems: 'flex-start' }}>
      <Field label="Тип"><select className="select" value={f.type} onChange={e => set('type', e.target.value)}>{UNIT_TYPES.map(t => <option key={t} value={t}>{KIND_TEXT[t]}</option>)}</select></Field>
      {isRack ? <Field label="Высота"><select className="select" value={f.uSize} onChange={e => set('uSize', +e.target.value)}>{[1, 2, 3, 4, 5, 6, 8, 10].map(n => <option key={n} value={n}>{n}U</option>)}</select></Field> : null}
      {isRack ? <Field label="Позиция"><select className="select" value={f.uStart} onChange={e => set('uStart', +e.target.value)}>{Array.from({ length: rack.totalU }, (_, i) => <option key={i} value={i + 1}>U{i + 1}</option>)}</select></Field> : null}
    </div>
    {!ok ? <div style={{ color: 'var(--red)', fontSize: 13 }}>На этом месте не хватает свободных юнитов</div> : null}
    {pm ? <div className="card pad" style={{ background: 'var(--fill)', border: 0 }}>
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
    {isRack ? <Field label="Сторона"><Seg value={f.side || 'front'} onChange={v => set('side', v)} options={[{ value: 'front', label: 'Фронт' }, { value: 'back', label: 'Тыл' }]} /></Field> : null}
    <Field label="Цвет"><div className="row">{UNIT_COLORS.map(c => <button key={c} onClick={() => set('color', c)} style={{ width: 28, height: 28, borderRadius: 8, border: f.color === c ? '3px solid var(--text)' : '0', background: c, cursor: 'pointer' }} />)}</div></Field>
    <Field label="Ссылка на веб-интерфейс"><input className="input" value={f.webUrl || ''} onChange={e => set('webUrl', e.target.value)} placeholder="http://192.168.1.1" /></Field>
    <Field label="Заметки"><textarea className="textarea" value={f.notes || ''} onChange={e => set('notes', e.target.value)} /></Field>
  </Modal>;
}
