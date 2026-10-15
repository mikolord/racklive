/* «Сканировать сеть»: who is on my network? One window: pick the network, watch the progress, add what was recognised with one press
   (the editor opens with the address and the connection type already filled in). Rack Live only knocks on ports (rackd/netscan.py). */
const PHASE_TEXT = { ping: 'Ищу включённые устройства', ports: 'Проверяю открытые порты', detect: 'Определяю, что это за устройства' };
const hostOf = d => String(d.host || (d.state && d.state.summary && d.state.summary.ip) || '').replace(/^\w+:\/\//, '').replace(/[:/].*$/, '');

function NetScanModal({ onClose }) {
  const { data, newDevice } = useApp(); const toast = useToast();
  const [info, setInfo] = useState(null);
  const [cidr, setCidr] = useState('');
  const [more, setMore] = useState(false);
  const load = async () => { try { const r = await api('/api/netscan'); setInfo(r); setCidr(c => c || (r.cidr || (r.subnets[0] || {}).cidr || '')); return r; } catch (e) { return null; } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!info || !info.running) return; const t = setInterval(load, 1000); return () => clearInterval(t); }, [info && info.running]);
  const start = async () => { try { await api('/api/netscan/start', { method: 'POST', body: { cidr } }); load(); } catch (e) { toast(e.message, true); } };
  const stop = async () => { try { await api('/api/netscan/stop', { method: 'POST', body: {} }); } catch (e) { } };
  if (!info) return <Modal title="Сканировать сеть" wide onClose={onClose} icon={<Icon name="search" size={20} color="var(--accent)" />}><div className="dim">Загрузка…</div></Modal>;
  const mine = new Set(data.devices.map(hostOf));
  const items = (info.items || []).map(it => ({ ...it, have: it.added || mine.has(it.ip) }));
  const addable = items.filter(it => it.driver && !it.have && it.driver !== 'ping');
  const others = items.filter(it => !it.have && !(it.driver && it.driver !== 'ping'));
  const have = items.filter(it => it.have);
  const pct = info.total ? Math.min(100, Math.round(info.done * 100 / info.total)) : 0;
  const drvKind = id => (data.drivers.find(d => d.id === id) || {}).kind;
  const add = it => {
    if (it.driver && it.driver !== 'ping') {
      newDevice({ driver: it.driver, kind: drvKind(it.driver) || it.kind, name: it.name && it.name !== it.ip ? it.name : (it.what || '').split(/[(:—]/)[0].trim().slice(0, 40),
        fields: { host: it.host || it.ip, location: 'local', notes: [it.vendor, it.mac].filter(Boolean).join(' · '), ...(it.mode ? { mode: it.mode } : {}) } });
    } else {
      newDevice({ driver: 'ping', kind: ['camera', 'printer', 'pc'].includes(it.kind) ? it.kind : 'other', name: it.name || it.what,
        fields: { host: it.ip, location: 'local', notes: [it.vendor, it.mac, it.ports.length ? 'порты ' + it.ports.join(', ') : ''].filter(Boolean).join(' · ') } });
    }
  };
  const row = (it, primary) => <div className="li netscan-row" key={it.ip}>
    <KindIcon kind={it.driver && it.driver !== 'ping' ? (drvKind(it.driver) || it.kind) : it.kind} size={36} round={10} />
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="row" style={{ gap: 6 }}><b style={{ fontSize: 14 }} className="ellipsis">{it.name || it.ip}</b>{it.vendor ? <span className="found-type">{it.vendor}</span> : null}</div>
      <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{it.what}</div>
      <div className="dim3 mono ellipsis" style={{ fontSize: 11.5 }}>{[it.ip, it.mac, it.ports.length ? 'порты ' + it.ports.join(' ') : '', it.also && it.also.length ? 'ещё адреса: ' + it.also.join(', ') : ''].filter(Boolean).join(' · ')}</div>
    </div>
    {it.self && !it.driver ? null : <Btn size="sm" kind={primary ? 'primary' : undefined} icon="plus" onClick={() => add(it)}>{primary ? 'Добавить' : 'На связи ли'}</Btn>}
  </div>;
  return <Modal title="Сканировать сеть" wide onClose={onClose} icon={<Icon name="search" size={20} color="var(--accent)" />}>
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Rack Live проверит адреса выбранной сети: кто включён, какие порты открыты и что это за устройства. Он только
      «стучится» — никуда не входит, ничего не меняет, пароли не нужны. Занимает около минуты.</div>
    <div className="col" style={{ gap: 8 }}>
      <div className="row wrap" style={{ gap: 6 }}>{info.subnets.map(s => <button type="button" key={s.cidr} className={'chip' + (cidr === s.cidr ? ' on' : '')} disabled={info.running}
        onClick={() => setCidr(s.cidr)} title={s.label}>{s.cidr}</button>)}</div>
      <div className="row" style={{ gap: 8 }}>
        <input className="input mono grow" value={cidr} disabled={info.running} onChange={e => setCidr(e.target.value)} placeholder="192.168.1.0/24" />
        {info.running ? <Btn onClick={stop}>Остановить</Btn> : <Btn kind="primary" icon="search" onClick={start}>{info.finished ? 'Сканировать снова' : 'Сканировать'}</Btn>}
      </div>
      <div className="dim3" style={{ fontSize: 12 }}>{(info.subnets.find(s => s.cidr === cidr) || {}).label || 'Своя сеть: только домашние адреса, не больше /22'}</div>
    </div>
    {info.running ? <div><div className="row between" style={{ fontSize: 13, marginBottom: 6 }}><span>{PHASE_TEXT[info.phase] || 'Работаю'}…</span><span className="dim3">{info.done} из {info.total}</span></div>
      <div className="gauge-bar" style={{ maxWidth: 'none' }}><i style={{ width: pct + '%' }} /></div></div> : null}
    {info.error ? <div style={{ color: 'var(--orange)', fontSize: 13 }}>{info.error}</div> : null}
    {info.finished && info.arp === false ? <div className="dim" style={{ fontSize: 12.5 }}>Rack Live не видит таблицу соседей (ARP) на этом устройстве — найдены только те, кто ответил на порт. Выключенные в «спящем» режиме и телефоны могли не попасть в список.</div> : null}
    {info.finished || items.length ? <>
      <div className="card-title" style={{ margin: '4px 0 0' }}><Icon name="plus" size={14} />Можно добавить в Rack Live · {addable.length}</div>
      {addable.length ? <div className="list">{addable.map(it => row(it, true))}</div>
        : <div className="dim3" style={{ fontSize: 13 }}>{info.running ? 'Пока ничего не определено…' : 'Ничего подходящего не нашлось — смотрите «Другие устройства» ниже или добавьте по адресу вручную.'}</div>}
      {others.length ? <>
        <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setMore(!more)}>{more ? 'Скрыть' : 'Показать'} другие устройства · {others.length}</button>
        {more ? <div className="list">{others.map(it => row(it, false))}</div> : null}
      </> : null}
      {have.length ? <div className="dim3" style={{ fontSize: 12.5 }}>Уже есть в Rack Live: {have.length} {ruPlural(have.length, 'устройство', 'устройства', 'устройств')}.</div> : null}
      {info.finished ? <div className="dim3" style={{ fontSize: 11.5 }}>Просканировано {fmt.ago(info.finished, data.now)} · сеть {info.cidr} · всего найдено {items.length}</div> : null}
    </> : null}
  </Modal>;
}
