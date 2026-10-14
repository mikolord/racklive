/* Power chain: outlet blocks (unit type «Блок розеток»), the UPS and what is plugged where.
   One row of load = {dev | unit | pdu | label} + {v, a, w} (volts, amps, watts) — the same in a block's outlet and in a UPS socket.
   Totals are computed on the server (rackd/power.py) and arrive as unit.powerLoad. */
const PDU_COUNTS = [4, 5, 6, 8, 10, 12, 16, 24];
const pduUnits = data => allUnits(data).filter(u => u.type === 'pdu');
const pduDefault = () => ({ count: 6, ports: {} });
const num0 = v => { const n = parseFloat(String(v == null ? '' : v).replace(',', '.')); return isFinite(n) ? n : 0; };
const specW = s => (s ? (num0(s.w) || num0(s.v) * num0(s.a)) : 0);
const rowHas = r => !!(r && (r.dev || r.pdu || r.unit || r.label || num0(r.w) || num0(r.v)));
// equipment of the places without a monitored device: ONT, injector, router in a box… (not passive gear, not blocks / UPS)
const plainUnits = data => allUnits(data).filter(u => !u.deviceId && !(u.deviceIds || []).length && !PASSIVE.includes(u.type) && u.type !== 'ups');

/* outlet blocks reachable from these ones through their outlets */
function pduReach(data, ids) {
  const byId = Object.fromEntries(pduUnits(data).map(u => [u.id, u])); const out = new Set(); const todo = [...ids];
  while (todo.length) { const i = todo.pop(); if (out.has(i) || !byId[i]) continue; out.add(i);
    Object.values((byId[i].power || {}).ports || {}).forEach(p => p && p.pdu && todo.push(p.pdu)); }
  return out;
}
/* blocks that (directly or through others) feed block `id` */
const pduAbove = (data, id) => new Set(pduUnits(data).filter(u => pduReach(data, [u.id]).has(id)).map(u => u.id));

/* row of load → select value, and back */
const rowKey = r => (r.pdu ? 'p:' + r.pdu : r.unit ? 'u:' + r.unit : r.dev ? 'd:' + r.dev : r.label !== undefined || num0(r.w) || num0(r.v) ? 'l' : '');
const rowPick = v => (v.startsWith('p:') ? { pdu: v.slice(2), dev: undefined, unit: undefined, label: undefined, v: '', a: '', w: '' }
  : v.startsWith('u:') ? { unit: v.slice(2), dev: undefined, pdu: undefined, label: undefined }
  : v.startsWith('d:') ? { dev: v.slice(2), unit: undefined, pdu: undefined, label: undefined }
  : v === 'l' ? { dev: undefined, unit: undefined, pdu: undefined, label: '' } : { dev: undefined, unit: undefined, pdu: undefined, label: undefined, v: '', a: '', w: '' });
/* custom lines must say how much they draw — otherwise the UPS cannot count */
const rowsMissing = rows => (rows || []).filter(r => r && rowKey(r) === 'l' && !specW(r)).map(r => r.label || 'без названия');

/* «В × А = Вт»: volts and amps from the power adapter's label, or watts directly */
function SpecInputs({ spec, onChange, auto }) {
  const s = spec || {}; const calc = num0(s.v) * num0(s.a);
  const set = (k, v) => onChange({ ...s, [k]: v });
  return <span className="spec">
    <input className="input" inputMode="decimal" value={s.v || ''} placeholder="В" title="Вольты (на блоке питания: Output 12 V)" onChange={e => set('v', e.target.value)} />
    <i>×</i>
    <input className="input" inputMode="decimal" value={s.a || ''} placeholder="А" title="Амперы (Output 1 A)" onChange={e => set('a', e.target.value)} />
    <i>=</i>
    <input className="input" inputMode="decimal" value={s.w || ''} placeholder={calc ? String(Math.round(calc * 10) / 10) : auto ? 'авто' : 'Вт'} title="Ватты (пусто — В × А)" onChange={e => set('w', e.target.value)} />
    <b>Вт</b></span>;
}

/* short tips on measuring — shown where the numbers are typed (can be hidden with «Понятно», or all at once in Настройки → Подсказки) */
function MeasureHint({ id = 'pw-measure', kind }) {
  const auto = kind === 'switch' || kind === 'router' ? <>Пусто — возьмём <b>~15 Вт самого коммутатора + PoE с портов</b> (PoE ещё делится на 0,9 — потери блока питания). Тут PoE уже учтён, вписывать не нужно.</>
    : kind === 'nas' ? <>Пусто — посчитаем <b>18 Вт + 7 Вт на каждый диск</b>. Точнее — ваттметром.</>
    : kind === 'server' || kind === 'pc' || kind === 'laptop' ? <>Пусто — взято типичное число для такого устройства (оно часто занижено). Лучше замерить <b>ваттметром</b> в розетке.</>
    : <>Пусто — ИБП возьмёт типичное потребление для такого устройства.</>;
  return <Hint id={id + '-' + (kind || 'any')} title="Как узнать, сколько берёт устройство">
    <ul className="tips">
      <li><b>Компьютер, сервер, NAS</b> — ваттметр в розетку (он стоит копейки). Не ориентируйтесь на мощность блока питания: «750 Вт» — это максимум, а не то, что он берёт.</li>
      <li><b>Роутер, ONT, свич, камера</b> — на блоке питания строка <b>Output</b>, например «12 V, 1 A»: впишите 12 и 1. Строку Input (220 В) не берите.</li>
      <li>Цифры на блоке питания — максимум, реально обычно меньше. Для ИБП это запас — и хорошо.</li>
      <li>{auto}</li></ul></Hint>;
}

/* what is plugged in: one select with everything electrical — devices, equipment without a device, outlet blocks, own line */
function RowPick({ value, onChange, skipPdu = [], skipDev = [] }) {
  const { data } = useApp();
  const units = plainUnits(data); const pdus = pduUnits(data).filter(u => !skipPdu.includes(u.id));
  return <select className="select grow" value={value} onChange={e => onChange(e.target.value)}>
    {value === '' ? <option value="">— свободна —</option> : null}
    <optgroup label="Устройства">{data.devices.filter(d => !skipDev.includes(d.id)).map(d => <option key={d.id} value={'d:' + d.id}>{d.name}</option>)}</optgroup>
    {units.length ? <optgroup label="Оборудование без устройства (ONT, инжектор…)">{units.map(u => <option key={u.id} value={'u:' + u.id}>{u.name} ({u.rackName})</option>)}</optgroup> : null}
    {pdus.length ? <optgroup label="Блоки розеток">{pdus.map(u => <option key={u.id} value={'p:' + u.id}>{u.name} ({u.rackName})</option>)}</optgroup> : null}
    <option value="l">Своё устройство (назвать и указать В и А)…</option></select>;
}

/* the tree of what a block / UPS feeds: outlet, name, watts — blocks inside open their own lists */
function PowerTree({ items, depth = 0 }) {
  const { data, openDevice } = useApp();
  if (!items || !items.length) return null;
  return <div className="ptree" style={{ marginLeft: depth ? 14 : 0 }}>{items.map((c, i) => { const d = c.id && data.devices.find(x => x.id === c.id);
    return <div key={(c.id || c.unit || 'r') + i}>
      <div className="li" style={{ cursor: d ? 'pointer' : 'default', padding: '7px 0' }} onClick={() => d && openDevice(d)}>
        <span className="pt-out">{c.outlet ? c.outlet : '·'}</span>
        <KindIcon kind={c.kind === 'ups' ? 'ups' : c.kind || 'other'} size={26} round={7} />
        <div className="grow" style={{ minWidth: 0 }}><div className="row" style={{ gap: 6 }}>{c.status ? <span className={'dot ' + c.status} /> : null}
          <b className="ellipsis" style={{ fontSize: 13.5 }}>{c.name}</b></div>
          <div className="ellipsis" style={{ fontSize: 11.5, color: c.missing ? 'var(--orange)' : 'var(--text3)' }}>{c.src}</div></div>
        <b className="mono" style={{ fontSize: 13 }}>{c.w} Вт</b></div>
      {c.children && c.children.length ? <PowerTree items={c.children} depth={depth + 1} /> : null}</div>; })}</div>;
}

/* round LEDs of an outlet block (and of a UPS): red = something is plugged in, grey = free */
function socketLeds(unit, dev) {
  if (unit.type === 'pdu' && unit.power) {
    const cnt = unit.power.count || 0; if (!cnt) return null;
    const used = new Set(((unit.powerLoad || {}).items || []).map(i => String(i.outlet)));
    Object.entries(unit.power.ports || {}).forEach(([n, p]) => { if (rowHas(p)) used.add(String(n)); });
    return Array.from({ length: cnt }, (_, i) => ({ n: i + 1, cls: used.has(String(i + 1)) ? 'r' : '' }));
  }
  const u = dev && dev.state && dev.state.ups;
  if (unit.type === 'ups' && u && u.outlets) {
    const used = new Set((u.connected || []).map(c => String(c.outlet)));
    return Array.from({ length: u.outlets }, (_, i) => ({ n: i + 1, cls: used.has(String(i + 1)) ? 'r' : '' }));
  }
  return null;
}

/* «Откуда питается ИБП»: which outlet block and which of its outlets (never a block this UPS feeds itself) */
function PowerFrom({ f, set }) {
  const { data } = useApp();
  const below = pduReach(data, (f.loads || []).filter(r => r && r.pdu).map(r => r.pdu));
  const pdus = pduUnits(data).filter(u => !below.has(u.id)); const cur = pdus.find(u => u.id === f.powerFrom);
  if (!pduUnits(data).length) return <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>Блоков розеток пока нет. Добавьте в шкаф или щиток юнит «Блок розеток» — и здесь можно будет выбрать, откуда питается ИБП.</div>;
  return <div>
    <div className="row wrap" style={{ gap: 8 }}>
      <select className="select grow" value={cur ? f.powerFrom : ''} onChange={e => { set('powerFrom', e.target.value || undefined); set('powerFromOutlet', ''); }}>
        <option value="">Прямо из розетки (не из блока)</option>
        {pdus.map(u => <option key={u.id} value={u.id}>{u.name} ({u.rackName})</option>)}</select>
      {cur ? <select className="select" style={{ width: 130 }} value={f.powerFromOutlet || ''} onChange={e => set('powerFromOutlet', e.target.value)}>
        <option value="">розетка —</option>
        {Array.from({ length: (cur.power || {}).count || 6 }, (_, i) => <option key={i} value={i + 1}>{'розетка ' + (i + 1)}</option>)}</select> : null}</div>
    {below.size ? <div className="dim3" style={{ fontSize: 12, marginTop: 6 }}>Блоки, которые питаются от этого ИБП, здесь не показаны — один блок не может и питать ИБП, и питаться от него.</div> : null}
  </div>;
}

/* outlets of a block: what is plugged into each */
function PowerEditor({ unit, onClose, onSave }) {
  const { data } = useApp(); const toast = useToast();
  const [pw, setPw] = useState(() => JSON.parse(JSON.stringify(unit.power || pduDefault())));
  const [open, setOpen] = useState(null);                 // a nested block whose outlets are edited from here
  const ports = pw.ports || {};
  const setPort = (n, patch) => setPw(x => ({ ...x, ports: { ...x.ports, [n]: { ...(x.ports[n] || {}), ...patch } } }));
  const skip = [unit.id, ...pduAbove(data, unit.id)];     // a block cannot be plugged into itself or into what it feeds
  const feeders = (unit.powerLoad || {}).feeders || [];
  const done = () => { const bad = rowsMissing(Object.values(ports)); if (bad.length) return toast(`Укажите потребление (В и А или Вт): ${bad.join(', ')}`, true); onSave(pw); onClose(); };
  return <Modal title={`«${unit.name || 'Блок розеток'}» — что в какой розетке`} wide onClose={onClose}
    footer={<><div className="grow" /><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={done}>Готово</Btn></>}>
    <div className="dim" style={{ fontSize: 13 }}>Для каждой розетки выберите, что в неё включено. Число в «Вт» (или В × А) заменяет оценку; пусто — потребление берётся из настроек устройства.
      {feeders.length ? ` Сейчас блок питается от: ${feeders.map(f => `${f.name}${f.outlet ? ', гнездо ' + f.outlet : ''}`).join('; ')}.` : ''}</div>
    <MeasureHint id="pw-block" />
    <div className="loads">{Array.from({ length: pw.count }, (_, i) => { const n = i + 1, p = ports[n] || {}, k = rowKey(p);
      return <div className="load-row" key={n}>
        <span className="pt-out">{n}</span>
        <RowPick value={k} skipPdu={skip} onChange={v => setPort(n, rowPick(v))} />
        {k === 'l' ? <input className="input grow" value={p.label || ''} placeholder="Название, например «Камеры»" onChange={e => setPort(n, { label: e.target.value })} /> : null}
        {k && k[0] !== 'p' ? <SpecInputs spec={p} auto={k[0] === 'd'} onChange={s => setPort(n, { v: s.v, a: s.a, w: s.w })} /> : null}
        {k && k[0] === 'p' ? <Btn size="sm" onClick={() => setOpen(p.pdu)}>Розетки…</Btn> : null}
      </div>; })}</div>
    {open ? <PduPortsModal unitId={open} onClose={() => setOpen(null)} /> : null}
  </Modal>;
}

/* edit the outlets of a block from anywhere (a UPS socket, another block): saved straight into that unit — one source of truth */
function PduPortsModal({ unitId, onClose }) {
  const { data, saveRack } = useApp();
  const rack = data.racks.find(r => r.units.some(u => u.id === unitId)); const unit = allUnits(data).find(u => u.id === unitId);
  if (!rack || !unit) return null;
  return <PowerEditor unit={unit} onClose={onClose}
    onSave={power => saveRack({ ...rack, units: rack.units.map(u => (u.id === unitId ? { ...u, power } : u)) })} />;
}
