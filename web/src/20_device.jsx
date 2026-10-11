/* Device detail sheet */
function useAction() {
  const { refresh, applyState } = useApp();
  const toast = useToast();
  const confirm = useConfirm();
  return async (device, action, params = {}) => {
    const text = (action.confirm || '').replace('{port}', params.port).replace('{name}', params.name || '');
    if (text && !(await confirm(text, { title: action.label, ok: action.label, danger: true }))) return false;
    if (!action.instant) toast(`${action.label}${params.port ? ' · порт ' + params.port : ''}: выполняю…`);
    try {
      const r = await api(`/api/devices/${device.id}/action`, { method: 'POST', body: { action: action.id, params } });
      if (r.state) applyState(device.id, r.state);            // instant actions return the fresh device state
      if (!action.instant) toast('✓ ' + (r.message || 'Готово'));
      refresh(); if (!action.instant && !r.cable) { setTimeout(refresh, 8000); setTimeout(refresh, 25000); setTimeout(refresh, 50000); }
      return r;
    } catch (e) { toast(e.message, true); return false; }
  };
}

function DeviceHead({ device, drv }) {
  const st = device.state || {}; const s = st.summary || {};
  return <div className="row" style={{ gap: 12 }}>
    <KindIcon kind={device.kind || drv?.kind} size={46} round={13} />
    <div className="grow">
      <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: -.4 }} className="ellipsis">{device.name}</div>
      <div className="row wrap" style={{ gap: 6, marginTop: 3 }}>
        <StatusBadge status={st.status} />
        {device.location === 'remote' ? <span className="badge info"><Icon name="globe" size={12} />Удалённое</span> : null}
        <span className="dim" style={{ fontSize: 13 }}>{[s.model, s.ip].filter(Boolean).join(' · ')}</span>
      </div>
    </div>
  </div>;
}

function DeviceSheet({ device, onClose, initialTab, initialPort }) {
  const { data, admin, openEditor } = useApp();
  const drv = data.drivers.find(d => d.id === device.driver);
  const st = device.state || {};
  const tabs = [{ id: 'overview', label: 'Обзор' }];
  if ((st.ports || []).length) tabs.push({ id: 'ports', label: `Порты · ${(st.ports || []).filter(p => p.link).length}/${st.ports.length}` });
  if ((st.children || []).length) tabs.push({ id: 'children', label: `Точки · ${st.children.length}` });
  if ((st.clients || []).length) tabs.push({ id: 'clients', label: `Клиенты · ${st.clients.length}` });
  if (st.storage) tabs.push({ id: 'storage', label: 'Хранилище' });
  if ((st.services || []).length || (st.entities || []).length) tabs.push({ id: 'services', label: st.entities ? 'Управление' : `Сервисы · ${st.services.length}` });
  const [tab, setTab] = useState(initialTab && tabs.find(t => t.id === initialTab) ? initialTab : 'overview');
  return <Sheet onClose={onClose} tab={tab} setTab={setTab} tabs={tabs}
    head={<div className="col" style={{ gap: 10 }}>
      <DeviceHead device={device} drv={drv} />
      {admin ? <div className="row"><Btn size="sm" icon="edit" onClick={() => { onClose(); openEditor(device); }}>Настроить</Btn>
        <PollNow device={device} /></div> : null}
    </div>}>
    {tab === 'overview' ? <Overview device={device} drv={drv} /> : null}
    {tab === 'ports' ? <PortsTab device={device} drv={drv} initialPort={initialPort} /> : null}
    {tab === 'children' ? <ChildrenTab device={device} drv={drv} /> : null}
    {tab === 'clients' ? <ClientsTab clients={st.clients} children={st.children} /> : null}
    {tab === 'storage' ? <StorageTab storage={st.storage} /> : null}
    {tab === 'services' ? <ServicesTab device={device} drv={drv} /> : null}
  </Sheet>;
}

function PollNow({ device }) {
  const { refresh } = useApp(); const toast = useToast();
  return <Btn size="sm" icon="refresh" onClick={async () => {
    try { const r = await api(`/api/devices/${device.id}/poll`, { method: 'POST' }); toast(r.state.error ? 'Ошибка: ' + r.state.error : 'Данные обновлены', !!r.state.error); refresh(); }
    catch (e) { toast(e.message, true); }
  }}>Обновить</Btn>;
}

function Overview({ device, drv }) {
  const { admin, data } = useApp();
  const st = device.state || {}; const s = st.summary || {};
  const hist = useHistory(device.id, true);
  const runAction = useAction();
  const stats = [];
  if (s.cpu != null) stats.push(<Stat key="cpu" k="Процессор" v={Math.round(s.cpu)} unit="%" level={s.cpu > 85 ? 'warn' : ''} spark={hist} sparkField="cpu" />);
  if (s.mem != null) stats.push(<Stat key="mem" k="Память" v={Math.round(s.mem)} unit="%" level={s.mem > 90 ? 'warn' : ''} spark={hist} sparkField="mem" color="var(--purple)" />);
  if (s.temp != null) stats.push(<Stat key="temp" k="Температура" v={s.temp} unit="°C" level={s.temp > 65 ? 'warn' : ''} spark={hist} sparkField="temp" color="var(--orange)" />);
  if (s.uptime != null) stats.push(<Stat key="up" k="Аптайм" v={fmt.uptime(s.uptime)} />);
  (st.metrics || []).forEach((m, i) => stats.push(<Stat key={'m' + i} k={m.label} v={m.value} unit={m.unit} level={m.level}
    spark={m.label === 'Задержка' || m.label === 'PoE' ? hist : null} sparkField={m.label === 'Задержка' ? 'ms' : 'poe'} color="var(--green)" />));
  const devActions = (drv?.actions || []).filter(a => a.scope === 'device');
  return <>
    {st.error ? <div className="card pad" style={{ borderColor: 'var(--red)', color: 'var(--red)' }}><b>Нет связи:</b> {st.error}
      {st.updated && st.summary ? <div className="dim" style={{ fontSize: 13, marginTop: 4 }}>Показаны последние известные данные</div> : null}</div> : null}
    {stats.length ? <div className="stats">{stats}</div> : null}
    <Card title="Сведения">
      <KV rows={[['Модель', s.model], ['Прошивка', s.fw], ['IP-адрес', s.ip ? <span className="mono">{s.ip}</span> : null],
        ['MAC', s.mac ? <span className="mono">{s.mac}</span> : null], ['Тип подключения', drv?.title],
        ['Обновлено', st.updated ? `${fmt.ago(st.updated, data.now)} · ${st.durationMs} мс` : 'ещё не опрашивалось'],
        ...(device.site ? [['Площадка', device.site]] : [])]} />
    </Card>
    {(st.sections || []).filter(x => x.rows && x.rows.length).map((sec, i) => <Card key={i} title={sec.title}><KV rows={sec.rows} /></Card>)}
    {device.notes ? <Card title="Заметки"><div style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{device.notes}</div></Card> : null}
    {admin && devActions.length ? <Card title="Действия"><div className="row wrap">{devActions.map(a =>
      <Btn key={a.id} kind="danger" icon="power" onClick={() => runAction(device, a)}>{a.label}</Btn>)}</div></Card> : null}
    <EventsList events={data.events.filter(e => e.device === device.id).slice(0, 8)} compact />
  </>;
}

function vlanColor(vid, vlans) { const v = (vlans || []).find(x => +x.vid === +vid); return v ? v.color : 'var(--text3)'; }
function vlanName(vid, vlans) { const v = (vlans || []).find(x => +x.vid === +vid); return v ? v.name : 'VLAN ' + vid; }

function Faceplate({ ports, sel, onSel, vlans }) {
  const rj = ports.filter(p => p.kind !== 'sfp'), sfp = ports.filter(p => p.kind === 'sfp');
  const two = rj.length > 8;
  const P = p => <div key={p.n} className={['port', speedClass(p), p.kind, p.disabled ? 'dis' : '', sel === p.n ? 'sel' : ''].join(' ')} onClick={() => onSel(p.n)}
    title={`${p.n}: ${p.label || ''} ${p.link ? fmt.speedShort(p.speed) : 'нет линка'}`}>
    {p.n}
    {p.poeW > 0 ? <span className="poe"><Icon name="bolt" size={9} color="#000" stroke={2.4} /></span> : null}
    {p.link ? <span className="vl">{[...(p.vlansU || []), ...(p.vlansT || [])].slice(0, 4).map((v, i) => <b key={i} style={{ background: vlanColor(v, vlans) }} />)}</span> : null}
  </div>;
  return <div className="faceplate"><div className="row" style={{ gap: 14, alignItems: 'flex-end' }}>
    <div className={'ports' + (two ? '' : ' one')}>{rj.map(P)}</div>
    {sfp.length ? <div className="ports" style={{ gridTemplateRows: 'repeat(2, auto)' }}>{sfp.map(P)}</div> : null}
  </div></div>;
}

/* Cable test: four twisted pairs drawn to scale, with the fault position marked */
const PAIR_COLOR = { A: '#ff9f0a', B: '#30d158', C: '#0a84ff', D: '#a2845e' };
const CABLE_ST = { normal: ['норма', 'online'], open: ['обрыв', 'offline'], short: ['замыкание', 'offline'], impedance: ['плохое сопротивление', 'warning'],
  crosstalk: ['наводки', 'warning'], unknown: ['не измерено', ''] };
const CABLE_VERDICT = { ok: ['var(--green)', 'check'], warn: ['var(--orange)', 'alert'], bad: ['var(--red)', 'alert'], empty: ['var(--text2)', 'cable'], unknown: ['var(--text2)', 'other'] };
function CableResult({ c, now }) {
  const far = Math.max(c.length || 0, ...c.pairs.map(p => p.len || 0));
  const scale = Math.max(10, Math.ceil(far * 1.15 / 5) * 5);
  const [col, icon] = CABLE_VERDICT[c.verdict] || CABLE_VERDICT.unknown;
  return <div className="cable">
    <div className="row" style={{ gap: 8, fontWeight: 650, color: col, alignItems: 'flex-start' }}><Icon name={icon} size={17} /><span>{c.text}</span></div>
    <div className="cable-pairs">
      {c.pairs.map(p => { const [t, s] = CABLE_ST[p.status] || [p.status, '']; const ok = p.status === 'normal';
        const pos = p.len != null ? Math.min(100, p.len / scale * 100) : null; const w = ok ? (pos != null ? pos : 100) : (pos || 0);
        return <div key={p.pair} className="cable-pair">
          <div className="cp-name"><b>{p.pair}</b><span className="mono">{p.pins}</span></div>
          <div className="cp-wire"><i className={ok ? '' : 'broken'} style={{ width: Math.max(w, 1.5) + '%', '--c': PAIR_COLOR[p.pair] }} />
            {!ok && p.status !== 'unknown' ? <span className={'cp-x ' + s} style={{ left: w + '%' }} /> : null}</div>
          <div className="cp-st"><span className={'dot ' + s} />{t}{p.len != null ? <span className="dim3"> · {p.len} м</span> : null}</div>
        </div>; })}
      <div className="cable-pair cp-ruler"><div /><div className="row between mono"><span>коммутатор</span><span>{Math.round(scale / 2)} м</span><span>{scale} м</span></div><div /></div>
    </div>
    {(c.details || []).length ? <ul className="cable-details">{c.details.map((d, i) => <li key={i}>{d}</li>)}</ul> : null}
    {c.hint ? <div className="dim" style={{ fontSize: 13 }}>{c.hint}</div> : null}
    <div className="dim3" style={{ fontSize: 11.5 }}>Измерено {fmt.ago(c.t, now)}{c.link ? ` · линк ${fmt.speedShort(c.speed)}` : ''} · точность ±5–10 м</div>
  </div>;
}

function PortsTab({ device, drv, initialPort }) {
  const { data, admin } = useApp();
  const ports = device.state.ports || [];
  const vlans = data.settings.vlans || [];
  const [sel, setSel] = useState(initialPort || (ports.find(p => p.link) || ports[0] || {}).n);
  const p = ports.find(x => x.n === sel);
  const runAction = useAction();
  const hasTraffic = ports.some(x => x.rxBytes != null);
  const [restarted, setRestarted] = useState({});          // port -> timestamp of a successful restart
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick(x => x + 1), 5000); return () => clearInterval(t); }, []);
  const rebooting = n => { const ts = restarted[n]; if (!ts) return false; const age = Date.now() - ts;
    const port = ports.find(x => x.n === n); return age < 150000 && !(port && port.link && age > 30000); };
  const doPortAction = async (a, n) => { if (await runAction(device, a, { port: n })) setRestarted(r => ({ ...r, [n]: Date.now() })); };
  const [cableRes, setCableRes] = useState({});           // port -> fresh test result (until the next refresh brings it)
  const [testing, setTesting] = useState(null);
  const doCableTest = async (a, n) => { setTesting(n); try { const r = await runAction(device, a, { port: n }); if (r && r.cable) setCableRes(c => ({ ...c, [n]: r.cable })); } finally { setTesting(null); } };
  const traffic = useHistory(device.id, hasTraffic && p && p.rxBytes != null, sel);
  const allPortActions = (drv?.actions || []).filter(a => a.scope === 'port' && (!a.needs || (a.needs === 'poe' && p && p.poe)));
  const portActions = allPortActions.filter(a => a.kind !== 'cable'), cableAction = allPortActions.find(a => a.kind === 'cable');
  const cab = p ? (cableRes[p.n] && (!p.cable || cableRes[p.n].t >= p.cable.t) ? cableRes[p.n] : p.cable) : null;
  const slow = p && p.link && p.kind !== 'sfp' && p.speed > 0 && p.speed < 1000 && ports.some(x => x.speed >= 1000);
  const used = [...new Set(ports.flatMap(x => [...(x.vlansU || []), ...(x.vlansT || [])]))].sort((a, b) => a - b);
  const totalPoe = ports.reduce((a, x) => a + (x.poeW || 0), 0);
  return <>
    <Faceplate ports={ports} sel={sel} onSel={setSel} vlans={vlans} />
    <div className="legend">
      <span><i style={{ background: 'var(--green)' }} />1 Гбит+</span><span><i style={{ background: '#ffd60a' }} />100 Мбит</span>
      <span><i style={{ background: '#ff9f0a' }} />10 Мбит</span><span><i style={{ background: '#48484a' }} />нет линка</span>
      {totalPoe ? <span><Icon name="bolt" size={13} color="#ffd60a" />PoE {totalPoe.toFixed(1)} Вт</span> : null}
      {used.map(v => <span key={v}><i style={{ background: vlanColor(v, vlans) }} />{vlanName(v, vlans)}</span>)}
    </div>
    {p ? <Card title={`Порт ${p.n}${p.label ? ' · ' + p.label : ''}`} right={rebooting(p.n) ? <span className="badge warning"><span className="spin-dot" />Перезагружается…</span>
      : <StatusBadge status={p.disabled ? 'offline' : p.link ? 'online' : ''} text={p.disabled ? 'Выключен' : p.link ? 'Линк' : 'Нет линка'} />}>
      <KV rows={[['Скорость', p.link ? fmt.speed(p.speed) : '—'], ...(p.poe ? [['PoE', p.poeW ? `${p.poeW} Вт` : 'нет потребителя']] : []),
        ['VLAN (untagged)', (p.vlansU || []).map(v => vlanName(v, vlans)).join(', ')],
        ['VLAN (tagged)', (p.vlansT || []).map(v => vlanName(v, vlans)).join(', ')], ...(p.ip ? [['IP', p.ip]] : []), ['Интерфейс', p.name],
        ...(p.lldp ? [['Сосед (LLDP)', p.lldp]] : []), ...(p.rxBytes != null ? [['Всего передано', `↓ ${fmt.bytes(p.txBytes)} · ↑ ${fmt.bytes(p.rxBytes)}`]] : [])]} />
      {p.rxBytes != null ? <div style={{ marginTop: 14 }}><div className="card-title" style={{ marginBottom: 8 }}>Трафик за сутки</div><TrafficChart points={traffic} /></div> : null}
      {(p.peers || []).length ? <div style={{ marginTop: 12 }}>
        <div className="card-title" style={{ marginBottom: 4 }}>Подключено ({p.peers.length})</div>
        <div className="list">{p.peers.slice(0, 40).map(x => <div className="li" key={x.mac}>
          <KindIcon kind={x.kind || 'other'} size={30} round={8} />
          <div className="grow"><div className="ellipsis" style={{ fontWeight: 600, fontSize: 14 }}>{x.name || 'Неизвестное устройство'}</div>
            <div className="dim mono" style={{ fontSize: 12 }}>{[x.ip, x.mac].filter(Boolean).join(' · ')}</div></div>
          {x.vlan ? <span className="badge" style={{ color: vlanColor(x.vlan, vlans) }}>{vlanName(x.vlan, vlans)}</span> : null}
        </div>)}</div></div> : null}
      {cab || slow || (admin && cableAction && p.kind !== 'sfp') ? <div style={{ marginTop: 14 }}>
        <div className="card-title" style={{ marginBottom: 8 }}><span className="grow">Кабель</span>
          {admin && cableAction && p.kind !== 'sfp' ? <Btn size="sm" icon="cable" busy={testing === p.n} onClick={() => doCableTest(cableAction, p.n)}>
            {testing === p.n ? 'Измеряю…' : cab ? 'Проверить снова' : cableAction.label}</Btn> : null}</div>
        {cab ? <CableResult c={cab} now={data.now} />
          : slow ? <div className="dim" style={{ fontSize: 13 }}>Порт работает на {fmt.speed(p.speed)}. Если устройство гигабитное — скорее всего в кабеле работают не все пары. {admin && cableAction ? 'Нажмите «Проверить кабель».' : ''}</div>
          : <div className="dim3" style={{ fontSize: 13 }}>Коммутатор измерит длину кабеля и проверит каждую из 4 пар — видно обрыв, замыкание и плохой обжим.</div>}
      </div> : null}
      {admin && portActions.length ? <div className="row wrap" style={{ marginTop: 14 }}>{portActions.map(a =>
        <Btn key={a.id} kind="danger" size="sm" icon={a.id === 'poe_cycle' ? 'bolt' : 'refresh'} onClick={() => doPortAction(a, p.n)}>{a.label}</Btn>)}</div> : null}
      {admin && portActions.length ? <div className="dim3" style={{ fontSize: 12, marginTop: 8 }}>Перезапуск PoE занимает ~20 секунд, затем устройству нужно 1–2 минуты, чтобы загрузиться.</div> : null}
    </Card> : null}
    <Card title="Все порты" pad={false}><div style={{ overflowX: 'auto' }}><table className="table"><thead><tr><th>#</th><th>Подпись</th><th>Линк</th>{hasTraffic ? <th>Трафик ↓/↑</th> : null}<th>PoE</th><th>VLAN</th><th>Устройства</th></tr></thead>
      <tbody>{ports.map(x => <tr key={x.n} onClick={() => setSel(x.n)} style={{ cursor: 'pointer' }}>
        <td className="mono">{x.n}</td><td>{x.label}{x.cable && ['warn', 'bad'].includes(x.cable.verdict) ? <span title={x.cable.text} style={{ marginLeft: 6, color: 'var(--orange)' }}><Icon name="alert" size={13} /></span> : null}</td><td>{x.link ? <span className="row" style={{ gap: 6 }}><span className={'dot ' + (x.speed >= 1000 ? 'online' : 'warning')} />{fmt.speedShort(x.speed)}</span> : <span className="dim3">—</span>}</td>
        {hasTraffic ? <td className="mono" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{x.txBps != null ? `${fmt.bps(x.txBps)} / ${fmt.bps(x.rxBps)}` : ''}</td> : null}
        <td>{x.poeW ? x.poeW + ' Вт' : ''}</td><td>{[...(x.vlansU || []), ...(x.vlansT || []).map(v => v + 't')].join(', ')}</td>
        <td className="ellipsis" style={{ maxWidth: 200 }}>{(x.peers || []).length > 2 ? `${x.peers.length} устр.` : (x.peers || []).map(y => y.name || y.mac).join(', ')}</td></tr>)}</tbody></table></div></Card>
  </>;
}

function ChildrenTab({ device, drv }) {
  const { admin } = useApp(); const runAction = useAction();
  const act = (drv?.actions || []).find(a => a.scope === 'child');
  return <div className="col" style={{ gap: 10 }}>{device.state.children.map(c => <Card key={c.key}>
    <div className="row"><KindIcon kind="ap" size={40} /><div className="grow">
      <div style={{ fontWeight: 700 }}>{c.name}</div><div className="dim mono" style={{ fontSize: 12.5 }}>{c.model} · {c.ip}</div></div>
      <StatusBadge status={c.status} /></div>
    <div className="stats" style={{ marginTop: 12 }}><Stat k="Клиенты" v={c.clients} /><Stat k="Аптайм" v={fmt.uptime(c.uptime)} />
      <Stat k="Uplink" v={c.uplink ? fmt.speedShort(+c.uplink) : '—'} level={+c.uplink && +c.uplink < 1000 ? 'warn' : ''} /><Stat k="Прошивка" v={c.fw} /></div>
    {c.fwUpdate ? <div className="badge info" style={{ marginTop: 10 }}>Доступно обновление прошивки</div> : null}
    {admin && act ? <div style={{ marginTop: 12 }}><Btn size="sm" kind="danger" icon="power" onClick={() => runAction(device, act, { ip: c.ip })}>{act.label}</Btn></div> : null}
  </Card>)}</div>;
}

function ClientsTab({ clients, children }) {
  const [q, setQ] = useState(''); const [seg, setSeg] = useState('');
  const apName = k => k === 'self' ? 'Роутер' : ((children || []).find(c => c.key === k) || {}).name || '';
  const segs = [...new Set(clients.map(c => c.segment || '—'))];
  const list = clients.filter(c => (!seg || (c.segment || '—') === seg) &&
    (!q || [c.name, c.ip, c.mac].join(' ').toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => (a.segment || '').localeCompare(b.segment || '') || (a.name || '').localeCompare(b.name || ''));
  return <>
    <SearchBox value={q} onChange={setQ} placeholder="Имя, IP или MAC" />
    <div className="row wrap"><button className={'chip' + (!seg ? ' on' : '')} onClick={() => setSeg('')}>Все · {clients.length}</button>
      {segs.map(s => <button key={s} className={'chip' + (seg === s ? ' on' : '')} onClick={() => setSeg(s)}>{s} · {clients.filter(c => (c.segment || '—') === s).length}</button>)}</div>
    <Card pad={false}><div className="list" style={{ padding: '0 14px' }}>{list.map(c => <div className="li" key={c.mac}>
      <KindIcon kind={c.kind} size={34} round={9} />
      <div className="grow" style={{ minWidth: 0 }}><div className="ellipsis" style={{ fontWeight: 600, fontSize: 14 }}>{c.name || c.mac}</div>
        <div className="dim mono ellipsis" style={{ fontSize: 12 }}>{c.ip} · {c.mac}</div></div>
      <div style={{ textAlign: 'right', fontSize: 12 }} className="dim">
        {c.ap ? <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}><Icon name="wifi" size={13} />{apName(c.ap)} {c.band}</div> : <div>{c.port ? 'порт ' + c.port : 'кабель'}</div>}
        {c.rssi ? <div style={{ color: c.rssi > -65 ? 'var(--green)' : c.rssi > -75 ? 'var(--orange)' : 'var(--red)' }}>{c.rssi} дБм{c.rate ? ' · ' + c.rate + ' Мбит' : ''}</div> : <div>{c.segment}</div>}
      </div></div>)}
      {!list.length ? <div className="empty">Ничего не найдено</div> : null}</div></Card>
  </>;
}

function StorageTab({ storage }) {
  return <>
    {(storage.volumes || []).map(v => { const pct = v.total ? v.used * 100 / v.total : 0; return <Card key={v.name} title={v.name} right={<StatusBadge status={v.status === 'normal' ? 'online' : 'warning'} text={v.status} />}>
      <Bar value={pct} /><div className="row between dim" style={{ fontSize: 13, marginTop: 8 }}><span>Занято {fmt.bytes(v.used)}</span><span>{Math.round(pct)}%</span><span>Всего {fmt.bytes(v.total)}</span></div></Card>; })}
    <Card title="Диски"><div className="list">{(storage.disks || []).map(d => <div className="li" key={d.name}>
      <div className="ico-circle"><Icon name="nas" size={18} /></div>
      <div className="grow"><div style={{ fontWeight: 600 }}>{d.name} <span className="badge" style={{ marginLeft: 4 }}>{(d.kind || '').toUpperCase()}</span></div>
        <div className="dim" style={{ fontSize: 12.5 }}>{d.model} · {fmt.gb(d.sizeGB)}</div></div>
      <div style={{ textAlign: 'right' }}><div style={{ fontWeight: 600, color: d.temp > 50 ? 'var(--orange)' : '' }}>{d.temp != null ? d.temp + '°C' : ''}</div>
        <StatusBadge status={d.status === 'normal' ? 'online' : d.status === 'not_use' ? '' : 'warning'} text={d.status === 'not_use' ? 'не используется' : d.status} /></div>
    </div>)}</div></Card>
  </>;
}

function ServicesTab({ device, drv }) {
  const { admin } = useApp(); const runAction = useAction();
  const st = device.state; const [q, setQ] = useState('');
  const [pending, setPending] = useState({});               // entity -> state shown until the server confirms
  const restart = (drv?.actions || []).find(a => a.scope === 'service');
  const toggle = (drv?.actions || []).find(a => a.scope === 'entity');
  useEffect(() => {                                          // drop optimistic values once real data agrees
    setPending(p => { const n = { ...p }; (st.entities || []).forEach(e => { if (n[e.id] === e.state) delete n[e.id]; }); return n; });
  }, [st.entities]);
  const flip = async e => {
    const target = (pending[e.id] || e.state) === 'on' ? 'off' : 'on';
    setPending(p => ({ ...p, [e.id]: target }));
    const ok = await runAction(device, toggle, { entity: e.id });
    if (!ok) setPending(p => { const n = { ...p }; delete n[e.id]; return n; });
    else setTimeout(() => setPending(p => { const n = { ...p }; delete n[e.id]; return n; }), 8000);
  };
  if (st.entities) return <>
    <SearchBox value={q} onChange={setQ} />
    <Card pad={false}><div className="list" style={{ padding: '0 14px' }}>{st.entities.filter(e => !q || e.name.toLowerCase().includes(q.toLowerCase())).map(e => {
      const cur = pending[e.id] || e.state;
      return <div className="li" key={e.id}><div className="ico-circle"><Icon name={e.id.startsWith('light') ? 'sun' : 'toggle'} size={18} color={cur === 'on' ? 'var(--orange)' : undefined} /></div>
        <div className="grow"><div style={{ fontWeight: 600, fontSize: 14 }}>{e.name}</div><div className="dim mono" style={{ fontSize: 12 }}>{e.id}</div></div>
        {admin && toggle ? <Switch on={cur === 'on'} disabled={e.state === 'unavailable'} onChange={() => flip(e)} />
          : <span className="badge">{e.state}</span>}</div>; })}</div></Card></>;
  return <Card pad={false}><div className="list" style={{ padding: '0 14px' }}>{(st.services || []).map(s => {
    const ok = /running|up/i.test(s.state || '');
    return <div className="li" key={s.name}><span className={'dot ' + (ok ? 'online' : 'offline')} /><div className="grow" style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</div>
      <span className="dim" style={{ fontSize: 13 }}>{s.state}</span>
      {admin && restart ? <Btn size="sm" icon="refresh" onClick={() => runAction(device, restart, { name: s.name })} title="Перезапустить" /> : null}</div>;
  })}</div></Card>;
}

function EventsList({ events, compact }) {
  const { data } = useApp();
  if (!events.length) return compact ? null : <div className="empty">Событий пока нет</div>;
  return <Card title={compact ? 'Последние события' : null}>{events.map((e, i) => <div className="ev" key={i}>
    <span className={'dot ' + (e.level === 'info' ? '' : e.level)} style={{ marginTop: 6, background: e.level === 'info' ? 'var(--accent)' : undefined }} />
    <div className="grow"><div style={{ fontSize: 14 }}><b>{e.name}</b> — {e.text}</div><div className="dim3" style={{ fontSize: 12 }}>{fmt.time(e.t)} · {fmt.ago(e.t, data.now)}</div></div>
  </div>)}</Card>;
}
