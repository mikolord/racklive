/* «Сканировать сеть»: who is on my network? One window: pick the network, watch the progress, add what was recognised with one press
   (the editor opens with the address and the connection type already filled in). Rack Live only knocks on ports (rackd/netscan.py). */
const PHASE_TEXT = { ping: 'Ищу включённые устройства', ports: 'Проверяю открытые порты', detect: 'Определяю, что это за устройства' };
const hostOf = d => String(d.host || (d.state && d.state.summary && d.state.summary.ip) || '').replace(/^\w+:\/\//, '').replace(/[:/].*$/, '');

function NetScanModal({ onClose }) {
  const ctx = useApp(); const { data, newDevice } = ctx; const toast = useToast();
  const [edit, setEdit] = useState(null);             // mac → ClientEditor (a device the network tree already shows)
  const [info, setInfo] = useState(null);
  const [where, setWhere] = useState([]);                // [] = every network Rack Live knows about
  const [more, setMore] = useState(false);
  const load = async () => { try { const r = await api('/api/netscan'); setInfo(r); return r; } catch (e) { return null; } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!info || !info.running) return; const t = setInterval(load, 1000); return () => clearInterval(t); }, [info && info.running]);
  const start = async () => { try { await api('/api/netscan/start', { method: 'POST', body: { cidrs: where } }); load(); } catch (e) { toast(e.message, true); } };
  const stop = async () => { try { await api('/api/netscan/stop', { method: 'POST', body: {} }); } catch (e) { } };
  if (!info) return <Modal title="Сканировать сеть" wide onClose={onClose} icon={<Icon name="search" size={20} color="var(--accent)" />}><div className="dim">Загрузка…</div></Modal>;
  const mine = new Set(data.devices.map(hostOf));
  const isCam = it => it.kind === 'camera' || (it.ports || []).some(p => [554, 8000, 8554, 37777, 34567].includes(p));
  const items = (info.items || []).map(it => ({ ...it, have: it.added || mine.has(it.ip) }));
  // what Rack Live can manage and does not have yet comes first — even if a router already lists it as its client (a second router, a NAS…)
  const addable = items.filter(it => it.driver && !it.have && it.driver !== 'ping' && !isCam(it));
  const seen = items.filter(it => it.tree && !it.have && !addable.includes(it));        // phones, TVs, cameras the routers already show: folded, with what can be done
  const others = items.filter(it => !it.have && !it.tree && !addable.includes(it));
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
  const driverTitle = id => (data.drivers.find(d => d.id === id) || {}).title || id;
  const seenRow = it => <div className="li netscan-row" key={it.ip}>
    <KindIcon kind={it.driver && it.driver !== 'ping' ? (drvKind(it.driver) || it.kind) : it.kind} size={36} round={10} />
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="row" style={{ gap: 6 }}><b style={{ fontSize: 14 }} className="ellipsis">{it.tree.name || it.name || it.ip}</b><span className="badge online">в дереве сети</span></div>
      <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{it.what}</div>
      <div className="dim3 mono ellipsis" style={{ fontSize: 11.5 }}>{[it.ip, it.mac, it.ports.length ? 'порты ' + it.ports.join(' ') : ''].filter(Boolean).join(' · ')}</div>
      <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
        {isCam(it) ? <Btn size="sm" icon="camera" onClick={() => { onClose(); openToolById(ctx, 'cameras', it.ip); }}>Камеры: вход, пароль, кадр</Btn> : null}
        {it.driver && it.driver !== 'ping' && !isCam(it) ? <Btn size="sm" icon="plus" onClick={() => add(it)}>Подключить как «{driverTitle(it.driver).slice(0, 34)}»</Btn> : null}
        {it.kind === 'pc' && !it.driver ? <Btn size="sm" icon="plus" onClick={() => newDevice({ driver: 'windows', kind: 'pc', name: it.tree.name || it.name, fields: { host: it.ip, location: 'local' } })}>Windows: нагрузка и диски</Btn> : null}
        {it.mac && findClient(data, it.mac) ? <Btn size="sm" onClick={() => setEdit(it.mac)}>Настройки на роутере</Btn> : null}
      </div></div></div>;
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
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Rack Live сам проверит все известные сети (или те, что выберете кнопкой «Сети»): кто включён, какие порты открыты и что это за устройства. Он только
      «стучится» — никуда не входит, ничего не меняет, пароли не нужны. Занимает около минуты.</div>
    <div className="row wrap" style={{ gap: 8 }}>
      {info.running ? <Btn onClick={stop}>Остановить</Btn> : <Btn kind="primary" icon="search" onClick={start}>{info.finished ? 'Сканировать снова' : 'Сканировать'}</Btn>}
      <WhereToSearch subnets={info.subnets} value={where} onChange={setWhere} disabled={info.running} />
    </div>
    {info.cidr && (info.running || info.finished) ? <div className="dim3" style={{ fontSize: 12 }}>Сканировали: {info.cidr}{info.skipped && info.skipped.length ? '. Роутеры (' + info.skipped.join(', ') + ') проверяем бережно, без перебора портов: иначе роутер примет это за атаку и на несколько минут закроет доступ.' : ''}</div> : null}
    {info.running ? <div><div className="row between" style={{ fontSize: 13, marginBottom: 6 }}><span>{PHASE_TEXT[info.phase] || 'Работаю'}…</span><span className="dim3">{info.done} из {info.total}</span></div>
      <div className="gauge-bar" style={{ maxWidth: 'none' }}><i style={{ width: pct + '%' }} /></div></div> : null}
    {info.error ? <div style={{ color: 'var(--orange)', fontSize: 13 }}>{info.error}</div> : null}
    {info.finished && info.arp === false ? <div className="dim" style={{ fontSize: 12.5 }}>Rack Live не видит таблицу соседей (ARP) на этом устройстве — найдены только те, кто ответил на порт. Выключенные в «спящем» режиме и телефоны могли не попасть в список.</div> : null}
    {info.finished || items.length ? <>
      <div className="card-title" style={{ margin: '4px 0 0' }}><Icon name="plus" size={14} />Можно добавить в Rack Live · {addable.length}</div>
      {addable.length ? <div className="list">{addable.map(it => row(it, true))}</div>
        : <div className="dim3" style={{ fontSize: 13 }}>{info.running ? 'Пока ничего не определено…' : 'Ничего подходящего не нашлось — смотрите «Другие устройства» ниже или добавьте по адресу вручную.'}</div>}
      {seen.length + others.length ? <>
        <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setMore(!more)}>{more ? 'Скрыть' : 'Показать'} остальные устройства в сети · {seen.length + others.length}</button>
        {more ? <><div className="dim3" style={{ fontSize: 12.5 }}>Телефоны, компьютеры, камеры и прочее, чем Rack Live не управляет. Обычно добавлять их не нужно — роутер и так показывает их на карте.</div>
          <div className="list">{seen.map(seenRow)}{others.map(it => row(it, false))}</div></> : null}
      </> : null}
      {have.length ? <div className="dim3" style={{ fontSize: 12.5 }}>Уже есть в Rack Live: {have.length} {ruPlural(have.length, 'устройство', 'устройства', 'устройств')}.</div> : null}
      {info.finished ? <div className="dim3" style={{ fontSize: 11.5 }}>Просканировано {fmt.ago(info.finished, data.now)} · сеть {info.cidr} · всего найдено {items.length}</div> : null}
    </> : null}
    {edit ? <ClientEditor mac={edit} onClose={() => setEdit(null)} /> : null}
  </Modal>;
}

/* «Добавить» → a type is chosen: Rack Live looks for devices of exactly this type in the network by itself (a fresh scan if the last one is older
   than 10 minutes) and offers them; pressing one fills the address. The fields below can always be filled by hand. */
const SCAN_DRIVERS = new Set(['keenetic', 'openwrt', 'synology', 'homeassistant', 'proxmox', 'ssh', 'tplink_jetstream', 'windows']);
function ScanForType({ driver, onPick, picked }) {
  const { data } = useApp();
  const [info, setInfo] = useState(null); const [open, setOpen] = useState(true);
  const on = SCAN_DRIVERS.has(driver);
  const load = async () => { try { const r = await api('/api/netscan'); setInfo(r); return r; } catch (e) { return null; } };
  useEffect(() => { if (!on) return;
    (async () => { const r = await load();
      if (r && !r.running && (!r.finished || Date.now() / 1000 - r.finished > 600)) { try { await api('/api/netscan/start', { method: 'POST', body: { cidrs: [] } }); load(); } catch (e) { } } })(); }, [driver]);
  useEffect(() => { if (!info || !info.running) return; const t = setInterval(load, 1200); return () => clearInterval(t); }, [info && info.running]);
  if (!on || !info) return null;
  const mine = new Set(data.devices.map(hostOf).filter(Boolean));
  const found = (info.items || []).filter(it => it.driver === driver && !it.added && !mine.has(it.ip) && !mine.has(String(it.host || '').replace(/^\w+:\/\//, '').replace(/[:/].*$/, '')));
  const pct = info.total ? Math.min(100, Math.round(info.done * 100 / info.total)) : 0;
  return <div className="sft">
    <button type="button" className="sft-h" onClick={() => setOpen(!open)}><Icon name="search" size={15} /><b className="grow">{info.running ? 'Ищу такие устройства в вашей сети…' : found.length ? `Найдено в сети: ${found.length}` : 'В сети такие устройства не нашлись'}</b>
      {info.running ? <span className="dim3 mono" style={{ fontSize: 11.5 }}>{pct}%</span> : null}<Icon name="chevron" size={14} style={{ transform: open ? 'rotate(90deg)' : 'none' }} /></button>
    {open ? <>
      {info.running ? <div className="gauge-bar" style={{ maxWidth: 'none' }}><i style={{ width: pct + '%' }} /></div> : null}
      {found.map(it => { const h = it.host || it.ip, on2 = picked && (picked === h || picked === it.ip);
        return <button key={it.ip} type="button" className={'sft-row' + (on2 ? ' on' : '')} onClick={() => onPick(it)}>
          <span className="sft-dot" /><span className="grow" style={{ minWidth: 0, textAlign: 'left' }}><b className="ellipsis" style={{ display: 'block' }}>{it.name || it.what || it.ip}</b>
            <small className="dim3 mono">{[h, it.mac].filter(Boolean).join(' · ')}</small></span>{on2 ? <Icon name="check" size={16} /> : <span className="dim3" style={{ fontSize: 12 }}>выбрать</span>}</button>; })}
      {!info.running ? <div className="dim3" style={{ fontSize: 12 }}>{found.length ? 'Нажмите на устройство — адрес подставится сам. ' : ''}Или впишите адрес вручную ниже.
        {' '}<button type="button" className="linkbtn" onClick={async () => { try { await api('/api/netscan/start', { method: 'POST', body: { cidrs: [] } }); load(); } catch (e) { } }}>Искать снова</button></div> : null}
    </> : null}
  </div>;
}
