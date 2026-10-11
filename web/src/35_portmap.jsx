/* Port maps for passive gear entered by hand: patch panel, optical cross, modem / ONT sockets.
   A port can be wired to a device port (live link status) or to a port of another patch / cross / ONT unit ("u:<unitId>"). */
const FIBER_COLORS = [['синий', '#2f6fe4'], ['оранжевый', '#ff8a1f'], ['зелёный', '#2fb04a'], ['коричневый', '#8b5a2b'], ['серый', '#8e8e93'],
  ['белый', '#f2f2f2'], ['красный', '#e53935'], ['чёрный', '#1c1c1e'], ['жёлтый', '#ffd60a'], ['фиолетовый', '#9b59d0'], ['розовый', '#ff7eb6'], ['бирюзовый', '#32c5c5']];
const PATCH_COUNTS = [6, 8, 12, 16, 24, 32, 48];
const CROSS_COUNTS = [4, 8, 12, 16, 24, 32, 48, 64, 96];
const MODEM_COUNTS = [1, 2, 3, 4, 5, 6, 8, 10];
const CONNECTORS = ['SC', 'LC', 'FC', 'ST', 'E2000'];
const isPortMap = t => t === 'patch' || t === 'cross' || t === 'modem';
const PM_TITLE = { patch: 'Порты патч-панели', cross: 'Оптический кросс', modem: 'Гнёзда модема / ONT' };

function pmDefault(type) {
  if (type === 'cross') return { count: 8, connector: 'SC', fiber: 'SM', ports: {} };
  if (type === 'modem') return { count: 5, ports: { 1: { name: 'PON' }, 2: { name: 'LAN1' }, 3: { name: 'LAN2' }, 4: { name: 'LAN3' }, 5: { name: 'LAN4' } } };
  return { count: 24, ports: {} };
}
const allUnits = data => (data.racks || []).flatMap(r => r.units.map(u => ({ ...u, rackName: r.name })));
const portName = (unit, n) => ((unit && unit.portmap && unit.portmap.ports || {})[n] || {}).name || String(n);
const fiberHex = name => (FIBER_COLORS.find(c => c[0] === name) || [])[1];

/* what a port is wired to: a device port (live) or another unit's port */
function linkedPort(data, m) {
  if (!m || !m.dev) return null;
  if (String(m.dev).startsWith('u:')) {
    const u = allUnits(data).find(x => x.id === m.dev.slice(2)); if (!u) return { missing: true };
    const far = ((u.portmap || {}).ports || {})[m.port] || {};
    return { unit: u, far, text: `${u.name}, ${u.type === 'modem' ? '' : 'порт '}${portName(u, m.port)}${far.color ? ' (' + far.color + ')' : ''}${far.label ? ' · ' + far.label : ''}` };
  }
  const d = data.devices.find(x => x.id === m.dev); if (!d) return { missing: true };
  const p = ((d.state || {}).ports || []).find(x => String(x.n) === String(m.port));
  const peers = p ? (p.peers || []).map(x => x.name || x.mac).filter(Boolean) : [];
  return { d, p, peers, text: `${d.name}${m.port ? ', порт ' + m.port : ''}` };
}
/* ports of other units wired INTO port n of this unit (e.g. ONT PON → cross fibre 1) */
function incoming(data, unitId, n) {
  const out = [];
  allUnits(data).forEach(u => Object.entries((u.portmap || {}).ports || {}).forEach(([k, m]) => {
    if (m && m.dev === 'u:' + unitId && String(m.port) === String(n)) out.push({ unit: u, n: k, m }); }));
  return out;
}
/* backbones on the floor plan that physically run through port n of this unit */
function backbonesFor(data, unitId, n) {
  const plan = data.plan || {}; const nodes = [...(plan.buildings || []), ...(plan.poles || [])];
  const name = id => (nodes.find(x => x.id === id) || {}).name || '?';
  return (plan.links || []).filter(l => l.via && l.via.unit === unitId && String(l.via.port) === String(n))
    .map(l => `магистраль ${name(l.from)} ↔ ${name(l.to)}${l.label ? ' (' + l.label + ')' : ''}`);
}
/* patch / cross / ONT ports wired to a device port — shown on the switch's port card */
function patchesFor(data, devId, portN) {
  const out = [];
  (data.racks || []).forEach(r => r.units.forEach(u => { const pm = u.portmap; if (!pm) return;
    Object.entries(pm.ports || {}).forEach(([n, m]) => { if (m && m.dev === devId && String(m.port) === String(portN)) out.push({ unit: u, n: +n, m, rack: r }); }); }));
  return out;
}

function PortMapView({ unit, compact }) {
  const { data } = useApp();
  const [sel, setSel] = useState(null);
  const pm = unit.portmap; if (!pm) return null;
  const cross = unit.type === 'cross', modem = unit.type === 'modem';
  const used = n => { const m = (pm.ports || {})[n]; return (m && (m.label || m.dev || m.color)) || incoming(data, unit.id, n).length || backbonesFor(data, unit.id, n).length; };
  const rows = Array.from({ length: pm.count }, (_, i) => i + 1).filter(used);
  const cell = n => { const m = (pm.ports || {})[n]; const lp = linkedPort(data, m); const inc = incoming(data, unit.id, n);
    const st = !used(n) ? 'pm-empty' : lp && lp.p ? (lp.p.link ? (lp.p.speed >= 1000 ? 'g' : 'y') : 'down') : 'set';
    const fc = cross && m && m.color ? fiberHex(m.color) : null;
    return <button type="button" key={n} className={'pm-port ' + st + (sel === n ? ' sel' : '') + (modem ? ' named' : '')} onClick={() => setSel(sel === n ? null : n)}
      title={[m && m.label, lp && lp.text, ...inc.map(x => '← ' + x.unit.name)].filter(Boolean).join(' · ') || 'не подписан'}>
      {fc ? <i className="pm-fiber" style={{ background: fc }} /> : null}{modem ? portName(unit, n) : n}</button>; };
  const line = n => { const m = (pm.ports || {})[n] || {}; const lp = linkedPort(data, m); const inc = incoming(data, unit.id, n);
    return [lp && (lp.d || lp.unit) ? '→ ' + lp.text + (lp.p ? ` · ${lp.p.link ? fmt.speedShort(lp.p.speed) : 'нет линка'}` : '') + (lp.peers && lp.peers.length ? ' · ' + lp.peers.slice(0, 2).join(', ') : '') : '',
      ...inc.map(x => `← ${x.unit.name}, ${x.unit.type === 'modem' ? portName(x.unit, x.n) : 'порт ' + x.n}`),
      ...backbonesFor(data, unit.id, n).map(t => '⇄ ' + t)].filter(Boolean).join('   ') || 'никуда не подключён'; };
  return <div className="pm">
    <div className="row wrap dim" style={{ gap: 10, fontSize: 12 }}>
      <span>{modem ? `${pm.count} гнёзд` : `${pm.count} портов`}{cross ? ` · ${pm.connector || 'SC'} · ${pm.fiber === 'MM' ? 'многомод' : 'одномод'}` : ''}</span>
      <span>подписано {rows.length}</span>
      <span className="row" style={{ gap: 4 }}><i className="pm-lg g" />1G</span><span className="row" style={{ gap: 4 }}><i className="pm-lg y" />100M</span>
      <span className="row" style={{ gap: 4 }}><i className="pm-lg down" />нет линка</span>
    </div>
    <div className={'pm-grid' + (modem ? ' named' : '')} style={{ '--cols': Math.min(pm.count > 24 ? Math.ceil(pm.count / 2) : pm.count, 24) }}>
      {Array.from({ length: pm.count }, (_, i) => cell(i + 1))}</div>
    {sel ? <div className="pm-detail"><b>{modem ? portName(unit, sel) : (cross ? 'Волокно ' : 'Порт ') + sel}</b>
      {((pm.ports || {})[sel] || {}).label ? <div>{pm.ports[sel].label}</div> : null}<div className="dim" style={{ fontSize: 12.5 }}>{line(sel)}</div>
      {((pm.ports || {})[sel] || {}).db ? <div className="dim" style={{ fontSize: 12.5 }}>Затухание {pm.ports[sel].db} дБ</div> : null}
      {((pm.ports || {})[sel] || {}).note ? <div className="dim" style={{ fontSize: 12.5 }}>{pm.ports[sel].note}</div> : null}</div> : null}
    {!compact && rows.length ? <div className="list" style={{ marginTop: 8 }}>{rows.map(n => { const m = (pm.ports || {})[n] || {}; const lp = linkedPort(data, m);
      const fc = cross && m.color ? fiberHex(m.color) : null;
      return <div className="li" key={n} onClick={() => setSel(n)} style={{ cursor: 'pointer' }}>
        <span className="pm-num" style={fc ? { boxShadow: `inset 4px 0 0 ${fc}` } : null}>{modem ? portName(unit, n) : n}</span>
        <div className="grow" style={{ minWidth: 0 }}><div className="ellipsis" style={{ fontWeight: 600, fontSize: 13.5 }}>{m.label || (cross && m.color ? m.color : '—')}</div>
          <div className="dim ellipsis" style={{ fontSize: 12 }}>{line(n)}</div></div>
        {lp && lp.p ? <span className={'dot ' + (lp.p.link ? 'online' : '')} /> : null}</div>; })}</div> : null}
    {!rows.length ? <div className="dim3" style={{ fontSize: 12.5 }}>Порты ещё не подписаны — включите «Редактирование» и откройте этот юнит.</div> : null}
  </div>;
}

function LinkTarget({ m, onDev, onPort, selfId }) {             // device or another unit + its port
  const { data } = useApp();
  const devs = data.devices.filter(d => ((d.state || {}).ports || []).length);
  const units = allUnits(data).filter(u => u.portmap && u.id !== selfId);
  const isUnit = m.dev && String(m.dev).startsWith('u:');
  const dev = !isUnit && data.devices.find(d => d.id === m.dev);
  const unit = isUnit && units.find(u => u.id === m.dev.slice(2));
  const ports = dev ? ((dev.state || {}).ports || []).map(p => ({ v: p.n, t: p.n + (p.label ? ' · ' + p.label.slice(0, 12) : '') }))
    : unit ? Array.from({ length: unit.portmap.count }, (_, i) => { const pp = unit.portmap.ports[i + 1] || {};
      return { v: i + 1, t: (unit.type === 'modem' ? portName(unit, i + 1) : i + 1) + (pp.color ? ' · ' + pp.color : '') + (pp.label ? ' · ' + pp.label.slice(0, 12) : '') }; }) : [];
  return <><td><select className="select pm-sel" value={m.dev || ''} onChange={e => onDev(e.target.value)}>
      <option value="">—</option>
      {devs.length ? <optgroup label="Устройства">{devs.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</optgroup> : null}
      {units.length ? <optgroup label="Кроссы, патч-панели, ONT">{units.map(u => <option key={u.id} value={'u:' + u.id}>{u.name} ({u.rackName})</option>)}</optgroup> : null}
    </select></td>
    <td>{ports.length ? <select className="select pm-sel" style={{ width: 110 }} value={m.port || ''} onChange={e => onPort(e.target.value)}>
      <option value="">—</option>{ports.map(p => <option key={p.v} value={p.v}>{p.t}</option>)}</select>
      : <input className="input pm-in" style={{ width: 70 }} value={m.port || ''} placeholder="№" onChange={e => onPort(e.target.value)} />}</td></>;
}

function PortMapEditor({ unit, onClose, onSave }) {
  const cross = unit.type === 'cross', modem = unit.type === 'modem';
  const [pm, setPm] = useState(() => JSON.parse(JSON.stringify(unit.portmap || pmDefault(unit.type))));
  const setPort = (n, k, v) => setPm(x => ({ ...x, ports: { ...x.ports, [n]: { ...(x.ports[n] || {}), [k]: v } } }));
  const fill = () => {                                   // quick start: port N → port N of the chosen target
    const first = (pm.ports[1] || {}).dev; if (!first) return alert('Сначала выберите, куда подключён порт 1');
    const id = prompt('С какого порта начинать? (номер порта у выбранного в первой строке)', String((pm.ports[1] || {}).port || 1));
    if (!id) return; const start = +id || 1;
    setPm(x => { const ports = { ...x.ports }; for (let n = 1; n <= x.count; n++) ports[n] = { ...(ports[n] || {}), dev: first, port: String(start + n - 1) }; return { ...x, ports }; });
  };
  const title = modem ? 'Модем / ONT' : cross ? 'Кросс' : 'Патч-панель';
  return <Modal title={`${title} «${unit.name || KIND_TEXT[unit.type]}» — ${modem ? 'гнёзда' : 'порты'}`} wide onClose={onClose}
    footer={<>{!modem ? <Btn onClick={fill} title="Заполнить подряд">Подряд</Btn> : null}<div className="grow" /><Btn onClick={onClose}>Отмена</Btn>
      <Btn kind="primary" onClick={() => { onSave(pm); onClose(); }}>Готово</Btn></>}>
    <div className="dim" style={{ fontSize: 13 }}>{modem
      ? 'Назовите гнёзда (PON, LAN1, TEL…) и укажите, куда каждое подключено: PON — в волокно оптического кросса, LAN — в WAN-порт роутера или в коммутатор.'
      : cross ? 'Для каждого волокна: цвет, куда идёт кабель, и куда включён патч-корд — SFP-порт коммутатора, ONT или медиаконвертер.'
        : 'Для каждого порта: куда идёт кабель (комната, розетка) и в какой порт коммутатора включён патч-корд — тогда будет видно линк и кто подключён.'}</div>
    <div className="pm-table-wrap"><table className="table pm-table"><thead><tr><th>#</th>{modem ? <th>Гнездо</th> : null}{cross ? <th>Цвет</th> : null}
      <th>{modem ? 'Описание' : cross ? 'Направление / кабель' : 'Куда идёт'}</th><th>Подключён к</th><th>Порт</th>{cross ? <th>дБ</th> : null}<th>Заметка</th></tr></thead>
      <tbody>{Array.from({ length: pm.count }, (_, i) => { const n = i + 1, m = pm.ports[n] || {};
        return <tr key={n}>
          <td className="mono">{n}</td>
          {modem ? <td><input className="input pm-in" style={{ width: 80 }} value={m.name || ''} placeholder={n === 1 ? 'PON' : 'LAN' + (n - 1)} onChange={e => setPort(n, 'name', e.target.value)} /></td> : null}
          {cross ? <td><select className="select pm-sel" value={m.color || ''} onChange={e => setPort(n, 'color', e.target.value)}
            style={{ boxShadow: m.color ? `inset 5px 0 0 ${fiberHex(m.color)}` : 'none' }}>
            <option value="">—</option>{FIBER_COLORS.map(c => <option key={c[0]} value={c[0]}>{c[0]}</option>)}</select></td> : null}
          <td><input className="input pm-in" value={m.label || ''} placeholder={modem ? (n === 1 ? 'оптика провайдера' : 'к роутеру') : cross ? 'Склад, ОКЛ-8' : 'Кабинет, розетка 3'}
            onChange={e => setPort(n, 'label', e.target.value)} /></td>
          <LinkTarget m={m} selfId={unit.id} onDev={v => { setPort(n, 'dev', v); setPort(n, 'port', ''); }} onPort={v => setPort(n, 'port', v)} />
          {cross ? <td><input className="input pm-in" style={{ width: 58 }} value={m.db || ''} placeholder="0.3" onChange={e => setPort(n, 'db', e.target.value)} /></td> : null}
          <td><input className="input pm-in" value={m.note || ''} onChange={e => setPort(n, 'note', e.target.value)} /></td>
        </tr>; })}</tbody></table></div>
  </Modal>;
}
