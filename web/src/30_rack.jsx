/* Rack view */
const U_PX = 46;
const UNIT_COLORS = ['#0a84ff', '#30d158', '#bf5af2', '#ff9f0a', '#ff453a', '#64d2ff', '#5e5ce6', '#ffd60a', '#8e8e93'];

function deviceLine(dev) {
  if (!dev) return '';
  const st = dev.state || {}; const s = st.summary || {};
  if (st.status === 'offline') return st.error ? 'Нет связи · ' + st.error : 'Нет связи';
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

function RackUnit({ unit, dev, edit, onClick, onPointerDown, dragging, top }) {
  const kind = PASSIVE.includes(unit.type) ? unit.type : (dev && dev.kind) || unit.type;
  const st = dev && dev.state ? dev.state.status : null;
  const h = unit.uSize * U_PX - 4;
  return <div className={['unit', PASSIVE.includes(unit.type) ? 'passive' : '', unit.type === 'blank' ? 'blank' : '', dragging ? 'dragging' : ''].join(' ')}
    style={{ top: top + 2, height: h, cursor: edit ? 'grab' : 'pointer' }} onClick={onClick} onPointerDown={onPointerDown}>
    <div className="strip" style={{ background: unit.color || '#0a84ff' }} />
    {unit.type !== 'blank' ? <div className="uicon"><Icon name={kind} size={16} color="#f5f5f7" /></div> : null}
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="row" style={{ gap: 7 }}>{st ? <span className={'dot ' + st} /> : null}<span className="uname ellipsis">{unit.name}</span></div>
      {h > 30 ? <div className="umeta ellipsis">{dev ? deviceLine(dev) : (KIND_TEXT[unit.type] || '') + (unit.uSize > 1 ? ` · ${unit.uSize}U` : '')}</div> : null}
    </div>
    <Leds ports={dev && dev.state && dev.state.ports} />
  </div>;
}

function RackView() {
  const { data, edit, saveRack, saveRacks, openDevice } = useApp();
  const [rackId, setRackId] = useState(data.racks[0].id);
  const [side, setSide] = useState('front');
  const [editing, setEditing] = useState(null);       // unit being edited / created
  const [info, setInfo] = useState(null);
  const [rackSettings, setRackSettings] = useState(null);
  const [drag, setDrag] = useState(null);              // {id, slot}
  const slotsRef = useRef(null);
  const toast = useToast(); const confirm = useConfirm();
  useEffect(() => { if (!data.racks.find(r => r.id === rackId)) setRackId(data.racks[0].id); }, [data.racks]);
  const rack = data.racks.find(r => r.id === rackId) || data.racks[0]; const total = rack.totalU;
  const minU = Math.max(1, ...rack.units.map(u => u.uStart + u.uSize - 1));
  const addRack = () => { const id = 'rack' + Date.now().toString(36);
    saveRacks([...data.racks, { id, name: `Шкаф ${data.racks.length + 1}`, totalU: 12, units: [] }]); setRackId(id); };
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
      if (slot !== u.uStart && fits(u, slot, u.id)) saveRack({ ...rack, units: rack.units.map(x => x.id === u.id ? { ...x, uStart: slot } : x) });
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };

  const occ = occupied();
  const dragUnit = drag && units.find(u => u.id === drag.id);
  const dropOk = dragUnit && fits(dragUnit, drag.slot, drag.id);

  const devices = data.devices; const problems = devices.filter(d => ['offline', 'warning'].includes(d.state && d.state.status));
  const allPorts = devices.flatMap(d => (d.state && d.state.ports) || []);
  const clients = devices.reduce((a, d) => a + ((d.state && d.state.clients) || []).length, 0);
  const poe = allPorts.reduce((a, p) => a + (p.poeW || 0), 0);

  return <div className="rack-layout">
    <div>
      {data.racks.length > 1 || edit ? <div className="row wrap rack-tabs" style={{ marginBottom: 12 }}>
        {data.racks.map(r => <button key={r.id} className={'chip' + (r.id === rackId ? ' on' : '')} onClick={() => setRackId(r.id)}>
          <Icon name="rack" size={13} />{r.name}</button>)}
        {edit ? <Btn size="sm" icon="plus" onClick={addRack}>Шкаф</Btn> : null}
      </div> : null}
      <div className="rack">
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
              dragging={drag && drag.id === u.id}
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
    </div>

    <div className="side-stack">
      <div className="stats">
        <Stat k="Устройства" v={`${devices.filter(d => d.state && d.state.status === 'online').length}/${devices.length}`} />
        <Stat k="Проблемы" v={problems.length} level={problems.length ? 'warn' : ''} />
        <Stat k="Клиенты" v={clients} />
        <Stat k="PoE" v={poe ? poe.toFixed(1) : 0} unit="Вт" />
      </div>
      {problems.length ? <Card title="Требуют внимания"><div className="list">{problems.map(d => <div className="li" key={d.id} style={{ cursor: 'pointer' }} onClick={() => openDevice(d)}>
        <KindIcon kind={d.kind} size={34} /><div className="grow"><div style={{ fontWeight: 600 }}>{d.name}</div>
          <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{d.state.error || (d.state.metrics || []).filter(m => m.level).map(m => `${m.label}: ${m.value}`).join(', ') || STATUS_TEXT[d.state.status]}</div></div>
        <StatusBadge status={d.state.status} /></div>)}</div></Card> : <Card><div className="row"><span className="dot online" /><b>Всё работает</b><span className="dim">— все устройства на связи</span></div></Card>}
      <HealthCard />
      <Card title="Устройства в шкафу"><div className="list">{rack.units.filter(u => u.deviceId && devById[u.deviceId]).sort((a, b) => a.uStart - b.uStart).map(u => {
        const d = devById[u.deviceId]; return <div className="li" key={u.id} style={{ cursor: 'pointer' }} onClick={() => openDevice(d)}>
          <KindIcon kind={d.kind} size={34} /><div className="grow" style={{ minWidth: 0 }}><div className="row" style={{ gap: 6 }}><span style={{ fontWeight: 600 }}>{d.name}</span><span className="dim3 mono" style={{ fontSize: 11 }}>U{u.uStart}</span></div>
            <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{deviceLine(d)}</div></div><Icon name="chevron" size={16} color="var(--text3)" /></div>;
      })}</div></Card>
      <EventsList events={data.events.slice(0, 6)} compact />
    </div>

    {editing ? <UnitEditor unit={editing} rack={rack} onClose={() => setEditing(null)} fits={fits} /> : null}
    {rackSettings ? <RackSettings rack={rackSettings} canDelete={data.racks.length > 1} onClose={() => setRackSettings(null)}
      onSelect={setRackId} /> : null}
    {info ? <Modal title={info.name} onClose={() => setInfo(null)} icon={<KindIcon kind={info.type} />}>
      <KV rows={[['Тип', KIND_TEXT[info.type]], ['Позиция', `U${info.uStart}${info.uSize > 1 ? '–' + (info.uStart + info.uSize - 1) : ''}`], ['Сторона', info.side === 'back' ? 'Тыл' : 'Фронт']]} />
      {info.notes ? <div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }} className="card pad">{info.notes}</div> : null}
      {info.webUrl ? <a className="btn" href={info.webUrl} target="_blank" rel="noreferrer">Открыть веб-интерфейс</a> : null}
    </Modal> : null}
  </div>;
}

function RackSettings({ rack, canDelete, onClose, onSelect }) {
  const { data, saveRack, saveRacks } = useApp(); const confirm = useConfirm(); const toast = useToast();
  const [name, setName] = useState(rack.name);
  const used = rack.units.filter(u => u.deviceId).length;
  const save = () => { saveRack({ ...rack, name: name.trim() || 'Шкаф' }); onClose(); };
  const del = async () => {
    if (!(await confirm(`Удалить шкаф «${rack.name}»? Его юниты будут удалены${used ? `, ${used} устройств отвяжутся (сами устройства останутся)` : ''}.`, { danger: true, ok: 'Удалить шкаф' }))) return;
    const rest = data.racks.filter(r => r.id !== rack.id); onSelect(rest[0].id); saveRacks(rest); onClose();
  };
  return <Modal title="Настройки шкафа" onClose={onClose}
    footer={<>{canDelete ? <Btn kind="danger" icon="trash" onClick={del}>Удалить шкаф</Btn> : null}<div className="grow" /><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={save}>Сохранить</Btn></>}>
    <Field label="Название шкафа" hint="Например «Серверная», «Этаж 2», «Дача»"><input className="input" value={name} autoFocus onChange={e => setName(e.target.value)} /></Field>
    {!canDelete ? <div className="dim" style={{ fontSize: 13 }}>Это единственный шкаф — удалить нельзя. Добавьте ещё один на вкладке «Шкаф».</div> : null}
  </Modal>;
}

function UnitEditor({ unit, rack, onClose, fits }) {
  const { data, saveRack } = useApp();
  const confirm = useConfirm();
  const [f, setF] = useState({ ...unit });
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const ok = fits(f, +f.uStart, unit.id);
  const save = () => {
    const u = { ...f, uStart: +f.uStart, uSize: +f.uSize, name: f.name.trim() || (f.deviceId ? (data.devices.find(d => d.id === f.deviceId) || {}).name : KIND_TEXT[f.type]) };
    const units = unit.id ? rack.units.map(x => x.id === unit.id ? u : x) : [...rack.units, { ...u, id: 'u' + Date.now().toString(36) }];
    saveRack({ ...rack, units }); onClose();
  };
  const del = async () => { if (await confirm(`Убрать «${unit.name}» из шкафа?`, { danger: true, ok: 'Убрать' })) { saveRack({ ...rack, units: rack.units.filter(x => x.id !== unit.id) }); onClose(); } };
  return <Modal title={unit.id ? 'Юнит' : 'Новый юнит'} onClose={onClose}
    footer={<>{unit.id ? <Btn kind="danger" icon="trash" onClick={del}>Убрать</Btn> : null}<div className="grow" /><Btn onClick={onClose}>Отмена</Btn>
      <Btn kind="primary" onClick={save} disabled={!ok}>Сохранить</Btn></>}>
    <Field label="Связанное устройство" hint="Живые данные этого устройства будут показаны на юните">
      <select className="select" value={f.deviceId || ''} onChange={e => { const d = data.devices.find(x => x.id === e.target.value);
        setF(x => ({ ...x, deviceId: e.target.value || null, name: x.name || (d ? d.name : ''), type: d && UNIT_TYPES.includes(d.kind) ? d.kind : x.type })); }}>
        <option value="">— не связан (пассивное оборудование) —</option>
        {data.devices.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
    <Field label="Название"><input className="input" value={f.name} onChange={e => set('name', e.target.value)} placeholder="Например, Коммутатор ядра" /></Field>
    <div className="row" style={{ alignItems: 'flex-start' }}>
      <Field label="Тип"><select className="select" value={f.type} onChange={e => set('type', e.target.value)}>{UNIT_TYPES.map(t => <option key={t} value={t}>{KIND_TEXT[t]}</option>)}</select></Field>
      <Field label="Высота"><select className="select" value={f.uSize} onChange={e => set('uSize', +e.target.value)}>{[1, 2, 3, 4, 5, 6, 8, 10].map(n => <option key={n} value={n}>{n}U</option>)}</select></Field>
      <Field label="Позиция"><select className="select" value={f.uStart} onChange={e => set('uStart', +e.target.value)}>{Array.from({ length: rack.totalU }, (_, i) => <option key={i} value={i + 1}>U{i + 1}</option>)}</select></Field>
    </div>
    {!ok ? <div style={{ color: 'var(--red)', fontSize: 13 }}>На этом месте не хватает свободных юнитов</div> : null}
    <Field label="Сторона"><Seg value={f.side || 'front'} onChange={v => set('side', v)} options={[{ value: 'front', label: 'Фронт' }, { value: 'back', label: 'Тыл' }]} /></Field>
    <Field label="Цвет"><div className="row">{UNIT_COLORS.map(c => <button key={c} onClick={() => set('color', c)} style={{ width: 28, height: 28, borderRadius: 8, border: f.color === c ? '3px solid var(--text)' : '0', background: c, cursor: 'pointer' }} />)}</div></Field>
    <Field label="Ссылка на веб-интерфейс"><input className="input" value={f.webUrl || ''} onChange={e => set('webUrl', e.target.value)} placeholder="http://192.168.1.1" /></Field>
    <Field label="Заметки"><textarea className="textarea" value={f.notes || ''} onChange={e => set('notes', e.target.value)} /></Field>
  </Modal>;
}
