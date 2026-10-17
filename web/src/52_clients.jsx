/* Networks and clients: what each network of the router is for (its role decides how new devices are treated),
   and one client's settings on the router — name (registration), permanent IP, speed limit, policy / block. */
const NET_ROLES = [
  { id: 'main', label: 'Основная', icon: 'home', color: '#0a84ff', hint: 'Ваши устройства. Зарегистрированные на роутере — молча, незнакомые — вопрос вам.' },
  { id: 'subscribers', label: 'Абоненты', icon: 'list', color: '#bf5af2', hint: 'Каждый новый абонент — вопрос «вы в курсе?».' },
  { id: 'guest', label: 'Гостевая', icon: 'wifi', color: '#30d158', hint: 'Без уведомлений. Тревога, только если кто-то ломится аномально.' },
  { id: 'iot', label: 'Умный дом', icon: 'iot', color: '#ff9f0a', hint: 'Новое умное устройство — нужно подтверждение.' },
  { id: 'cameras', label: 'Камеры', icon: 'camera', color: '#ff375f', hint: 'Новое устройство среди камер — нужно подтверждение.' },
  { id: 'service', label: 'Служебная', icon: 'link', color: '#8e8e93', hint: 'Технические связи (VPN, WAN другого роутера) — без уведомлений.' },
];
const roleOf = id => NET_ROLES.find(r => r.id === id);
const privateMac = mac => { try { return (parseInt(String(mac).split(':')[0], 16) & 2) === 2; } catch (e) { return false; } };
// a «private» MAC matters only if it keeps changing: the router knowing it as registered (or for 3+ days) means it is fixed
// (iOS «Фиксированный» private address, or the option already switched off)
const macChanges = c => privateMac(c && c.mac) && !(c.registered || (c.firstSeen || 0) > 3 * 86400);

/* where is this client now: the router that reports it, and its record there */
function findClient(data, mac) {
  mac = String(mac || '').toLowerCase();
  for (const d of data.devices) {
    const c = ((d.state || {}).clients || []).find(x => (x.mac || '').toLowerCase() === mac);
    if (c) return { router: d, client: c };
  }
  return null;
}

function NetworkRoles({ compact }) {
  const { data, refresh } = useApp(); const toast = useToast();
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('roles') === '1');
  const nets = data.networks || [];                 // every network of the router — even with nobody on it right now
  if (!nets.length) return null;
  const done = nets.filter(n => n.role).length;
  if (!open) return <button type="button" className="net-roles-row" onClick={() => setOpen(true)}>
    <Icon name="wifi" size={16} /><span className="grow">Сети роутера: отмечено {done} из {nets.length}
      {done < nets.length ? <span className="dim"> — отметьте, какая для чего, чтобы Rack Live знал, о чём спрашивать</span> : null}</span>
    <Icon name="chevron" size={15} /></button>;
  const set = async (n, role) => { try { await api('/api/netroles', { method: 'PUT', body: { key: n.key, role: n.role === role ? null : role } }); refresh(); } catch (e) { toast(e.message, true); } };
  const todo = nets.filter(n => !n.role).length;
  return <div className="net-roles">
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>{todo ? <><b style={{ color: 'var(--text)' }}>Какая это сеть?</b> Отметьте каждую — от этого зависит, о каких новых устройствах спрашивать. Осталось: {todo}.</>
      : 'Сети размечены — Rack Live спрашивает только о том, что требует решения.'}</div>
    <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setOpen(false)}>Свернуть ▴</button>
    {nets.map(n => { const r = roleOf(n.role);
      return <div key={n.key} className={'net-role' + (n.role ? '' : ' todo')}>
        <div className="row" style={{ gap: 8 }}><b>{n.name}</b><span className="dim3 mono" style={{ fontSize: 11.5 }}>{n.ip ? n.ip.replace(/\.\d+$/, '.0/24') : ''}{n.vlan ? ' · VLAN ' + n.vlan : ''} · {n.clients} устр.</span></div>
        <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>{NET_ROLES.map(x => <button key={x.id} type="button" className={'chip' + (n.role === x.id ? ' on' : '')}
          style={n.role === x.id ? { background: x.color, borderColor: x.color, color: '#fff' } : null} onClick={() => set(n, x.id)}>{x.label}</button>)}</div>
        {r && !compact ? <div className="dim3" style={{ fontSize: 12, marginTop: 5 }}>{r.hint}</div> : null}
      </div>; })}
  </div>;
}

function PendingIp({ c }) {
  if (!c || !c.staticIp || !c.ip || c.staticIp === c.ip) return null;
  return <span className="pending-ip" title={`Постоянный адрес ${c.staticIp} — устройство получит его после переподключения`}>
    <Icon name="clock" size={12} />{c.staticIp} после переподключения</span>;
}

/* what else can be done with a device the tree already shows: from the last network scan (cameras → the camera tool, a Windows PC → disks and load, a recognised server → connect it) */
function ClientActions({ c, onClose }) {
  const ctx = useApp(); const { data, newDevice } = ctx;
  const [it, setIt] = useState(undefined);
  useEffect(() => { api('/api/netscan').then(r => setIt((r.items || []).find(x => x.ip === c.ip || (x.also || []).includes(c.ip) || (x.mac && c.mac && x.mac.toLowerCase() === c.mac.toLowerCase())) || null)).catch(() => setIt(null)); }, [c.ip]);
  const ports = (it && it.ports) || [];
  const cam = c.kind === 'camera' || (it && it.kind === 'camera') || ports.some(p => [554, 8000, 8554, 37777, 34567].includes(p));
  const win = (c.kind === 'pc' || (it && it.kind === 'pc')) && !(it && it.driver && it.driver !== 'ping');
  const drv = it && it.driver && it.driver !== 'ping' && !cam ? it : null;        // never «connect as a router» for a camera: its web server answers anything
  const have = data.devices.some(d => hostOf(d) === c.ip);
  const [guess, setGuess] = useState(null);                   // «what is it?»: the auto-detect of the add-device form, run on this address
  const title = id => (data.drivers.find(d => d.id === id) || {}).title || id;
  if (!cam && !win && !drv) {
    if (!c.ip || it === undefined || have) return null;
    return <div className="card" style={{ marginTop: 10, padding: 12 }}>
      <div className="card-title" style={{ marginTop: 0 }}>Что ещё можно сделать с этим устройством</div>
      {guess === null ? <Btn size="sm" icon="search" onClick={async () => { setGuess('wait'); try { const r = await api('/api/detect', { method: 'POST', body: { host: c.ip } }); setGuess(r.found || []); } catch (e) { setGuess([]); } }}>Определить, что это за устройство</Btn>
        : guess === 'wait' ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Проверяю…</div>
        : !guess.length ? <div className="dim3" style={{ fontSize: 12.5 }}>Ничего управляемого не нашлось: устройство не отвечает на известные порты. Если это камера — откройте «Инструменты → Инструменты → Камеры» и найдите её там.</div>
        : <div className="col" style={{ gap: 6 }}>{guess.filter(g => g.driver && g.driver !== 'ping').slice(0, 3).map((g, i) => <div key={i} className="row" style={{ gap: 8 }}><span className="grow dim" style={{ fontSize: 12.5 }}>{g.what || title(g.driver)}</span>
          <Btn size="sm" icon="plus" onClick={() => { onClose(); newDevice({ driver: g.driver, kind: g.kind || (data.drivers.find(d => d.id === g.driver) || {}).kind, name: c.name, fields: { host: g.host || c.ip, location: 'local' } }); }}>Подключить</Btn></div>)}</div>}
    </div>;
  }
  return <div className="card" style={{ marginTop: 10, padding: 12 }}>
    <div className="card-title" style={{ marginTop: 0 }}>Что ещё можно сделать с этим устройством</div>
    <div className="row wrap" style={{ gap: 6 }}>
      {cam ? <Btn size="sm" icon="camera" onClick={() => { onClose(); openToolById(ctx, 'cameras', c.ip); }}>Камеры: вход, пароль, адрес, кадр</Btn> : null}
      {win && !have ? <Btn size="sm" icon="plus" onClick={() => { onClose(); newDevice({ driver: 'windows', kind: 'pc', name: c.name, fields: { host: c.ip, location: 'local' } }); }}>Windows: нагрузка, диски, их состояние</Btn> : null}
      {drv && !have ? <Btn size="sm" icon="plus" onClick={() => { onClose(); newDevice({ driver: drv.driver, kind: (data.drivers.find(d => d.id === drv.driver) || {}).kind, name: c.name || drv.name, fields: { host: drv.host || c.ip, location: 'local' } }); }}>Подключить: {title(drv.driver)}</Btn> : null}
    </div>
    {win && !have ? <div className="dim3" style={{ fontSize: 12, marginTop: 6 }}>Для Windows нужно один раз включить встроенный OpenSSH-сервер — подсказка будет в форме.</div> : null}
  </div>;
}

function ClientEditor({ mac, onClose, initialName }) {
  const { data, refresh } = useApp(); const toast = useToast();
  const found = findClient(data, mac);
  const c = (found || {}).client || {}; const router = (found || {}).router;
  const drv = router && data.drivers.find(x => x.id === router.driver);
  const policies = ((router || {}).state || {}).policies || [];
  const net = (data.networks || []).find(n => router && n.router === router.id && n.id === c.segId);
  const cur = { name: c.registered ? c.name || '' : '', ip: c.staticIp || '', limit: c.limit || 0, policy: c.access === 'deny' ? 'deny' : c.policy || '' };
  const [f, setF] = useState({ ...cur, name: cur.name || initialName || '' });     // not registered: the name is only suggested
  const [busy, setBusy] = useState(false); const [done, setDone] = useState(null);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  if (!found) return <Modal title="Клиент" onClose={onClose}><div className="dim">Устройство {mac} сейчас не подключено — настройки можно поменять, когда оно появится в сети.</div></Modal>;
  if (!drv || !drv.clientMgmt) return <Modal title={c.name || mac} onClose={onClose}><div className="dim">Роутер «{router.name}» не умеет настраивать клиентов из Rack Live.</div></Modal>;
  const mg = (router.state || {}).clientMgmt; const caps = (router.state || {}).clientCaps || { limit: true, policy: true, deny: true };
  if (mg && !mg.ok) return <Modal title={c.name || c.mac} onClose={onClose} icon={<KindIcon kind={c.kind} size={30} />}>
    <div className="dim mono" style={{ fontSize: 12.5 }}>{c.ip} · {c.mac} · {router.name}</div>
    <div className="warn-box"><Icon name="lock" size={16} /><div><b>Настройки клиентов на «{router.name}» отключены.</b> {mg.reason[0].toUpperCase() + mg.reason.slice(1)}.
      Имя, постоянный адрес и доступ этого устройства настраиваются в самом роутере.</div></div>
  </Modal>;
  const sameNet = net && net.ip ? net.ip.split('.').slice(0, 3).join('.') + '.' : '';
  const ipBad = (() => { const v = f.ip.trim(); if (!v) return '';
    if (!/^\d+\.\d+\.\d+\.\d+$/.test(v)) return 'неверный адрес';
    if (sameNet && !v.startsWith(sameNet)) return `только адрес этой сети: ${sameNet}…`;
    if (/\.(0|255)$/.test(v) || (net && v === net.ip)) return 'служебный адрес или адрес роутера';
    return ''; })();
  const [polling, setPolling] = useState(false);
  const repoll = async () => { setPolling(true);
    try { await api(`/api/devices/${router.id}/poll`, { method: 'POST' }); await refresh(); toast('Данные с роутера обновлены'); }
    catch (e) { toast(e.message, true); } finally { setPolling(false); } };
  const save = async () => {
    const body = { router: router.id, mac: c.mac, label: f.name || c.name || c.mac };
    if (f.name.trim() !== cur.name) body.name = f.name.trim();
    if (f.ip.trim() !== cur.ip) body.ip = f.ip.trim();
    if (+f.limit !== +cur.limit) body.limit = +f.limit || 0;
    if (f.policy !== cur.policy) body.policy = f.policy;
    if (Object.keys(body).length <= 3) { onClose(); return; }
    setBusy(true);
    try { const r = await api('/api/clients', { method: 'POST', body }); setDone(r.done); toast('Сохранено на роутере: ' + r.done.join(', ')); refresh(); }
    catch (e) { toast(e.message, true); }
    finally { setBusy(false); }
  };
  const registeredSoon = c.registered || f.name.trim();
  return <Modal title={c.name || c.mac} onClose={onClose} icon={<KindIcon kind={c.kind} size={30} />}
    footer={<><Btn icon="refresh" busy={polling} onClick={repoll} title="Ещё раз прочитать данные с роутера">Обновить</Btn><div className="grow" />
      <Btn onClick={onClose}>Закрыть</Btn><Btn kind="primary" busy={busy} disabled={!!ipBad} onClick={save}>Сохранить на роутере</Btn></>}>
    <div className="dim mono" style={{ fontSize: 12.5 }}>{c.ip} · {c.mac} · {net ? net.name : c.segment}{c.registered ? ' · зарегистрировано' : ' · не зарегистрировано'}</div>
    <PendingIp c={c} />
    {macChanges(c) ? <div className="warn-box"><Icon name="alert" size={16} /><div><b>Частный адрес Wi-Fi.</b> Телефон подставляет случайный MAC и время от времени меняет его —
      тогда регистрация, постоянный IP и ограничения «потеряются». Чтобы закрепить устройство, на iPhone: Настройки → Wi-Fi → (i) у этой сети → «Частный адрес Wi-Fi» → «Выкл»
      (на Android — «MAC-адрес устройства» вместо случайного), потом зарегистрируйте заново.</div></div> : null}
    <Field label="Имя на роутере" hint={c.registered ? 'Переименовать устройство в списке роутера' : 'С именем устройство станет зарегистрированным — «своим» для роутера'}>
      <div className="row" style={{ gap: 6 }}><input className="input grow" value={f.name} placeholder={c.name || 'Например, iPhone Миши'} onChange={e => set('name', e.target.value)} />
        {!f.name && c.name ? <Btn size="sm" onClick={() => set('name', c.name)}>Взять «{c.name.length > 16 ? c.name.slice(0, 15) + '…' : c.name}»</Btn> : null}</div></Field>
    <Field label="Постоянный IP-адрес" hint={ipBad ? <span style={{ color: 'var(--red)' }}>{ipBad}</span> : f.ip && f.ip !== c.ip ? 'Устройство получит новый адрес после переподключения к сети (или перезапуска Wi-Fi на нём)' : 'Пусто — адрес выдаётся автоматически'}>
      <div className="row" style={{ gap: 6 }}><input className="input grow mono" value={f.ip} placeholder={sameNet ? sameNet + '…' : 'IP'} onChange={e => set('ip', e.target.value)} />
        {c.ip && f.ip !== c.ip ? <Btn size="sm" onClick={() => set('ip', c.ip)}>Текущий {c.ip}</Btn> : null}</div></Field>
    {caps.limit ? <Field label="Ограничение скорости" hint={registeredSoon ? '0 — без ограничения' : 'Сначала задайте имя: роутер ограничивает только зарегистрированные устройства'}>
      <div className="row" style={{ gap: 6 }}><input className="input mono" style={{ width: 110 }} type="number" min="0" step="1" disabled={!registeredSoon} value={f.limit || ''} placeholder="0"
        onChange={e => set('limit', e.target.value)} /><span className="dim">Мбит/с</span>
        {[0, 10, 50, 100].map(v => <button key={v} type="button" className={'chip' + (+f.limit === v ? ' on' : '')} disabled={!registeredSoon} onClick={() => set('limit', v)}>{v || 'без'}</button>)}</div></Field>
      : <div className="dim3" style={{ fontSize: 12.5 }}>Ограничение скорости на этом роутере пока не поддерживается.</div>}
    <Field label="Доступ в интернет и политика">
      <select className="select" value={f.policy} onChange={e => set('policy', e.target.value)}>
        <option value="">По умолчанию (как у сети)</option>
        {(caps.policy ? policies : []).map(p => <option key={p.id} value={p.id}>{p.name}{p.name !== p.id ? ` (${p.id})` : ''}</option>)}
        <option value="deny">Запретить интернет</option>
      </select></Field>
    {done ? <div className="ok-box"><Icon name="check" size={16} />{done.join(' · ')}</div> : null}
    <ClientActions c={c} onClose={onClose} />
  </Modal>;
}
