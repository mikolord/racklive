/* Tools → «Удалённые площадки и агенты»: the places Rack Live watches from far away.
   • Площадка — a second Rack Live in «collector» mode stands there, watches that network by itself and reports here over one outgoing connection (rackd/sites.py, rackd/collector.py).
   • Агент — one remote server that sends its own data (web/agent.py).
   • «Эта установка — сборщик» — turn THIS Rack Live into such a collector for a main one. */
const siteBase = apps => { const o = location.origin; return PRIVATE_URL.test(o) && apps && apps.url ? apps.url : o; };
const siteKey = (base, token) => 'RL1.' + btoa(unescape(encodeURIComponent(JSON.stringify({ u: base, t: token })))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

function SitesTool() {
  const { data, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [info, setInfo] = useState(null);
  const [name, setName] = useState(''); const [agentName, setAgentName] = useState('');
  const [shown, setShown] = useState(null);                   // {kind: 'site'|'agent', name, token}
  const [busy, setBusy] = useState('');
  const load = async () => { try { setInfo(await api('/api/sites')); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
  if (!info) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  const base = siteBase(data.apps); const priv = PRIVATE_URL.test(base);
  const addSite = async () => { setBusy('site'); try { const r = await api('/api/sites', { method: 'POST', body: { name } }); setName(''); setShown({ kind: 'site', name: r.name, token: r.token }); load(); refresh(); } catch (e) { toast(e.message, true); } finally { setBusy(''); } };
  const showSite = async s => { try { const r = await api(`/api/sites/${s.id}/token`, { method: 'POST', body: {} }); setShown({ kind: 'site', name: r.name, token: r.token }); } catch (e) { toast(e.message, true); } };
  const delSite = async s => {
    if (!(await confirm(`Удалить площадку «${s.name}»? Её устройства (${s.devices}) исчезнут из списка и с карты. Сам сборщик на площадке останется, но главная установка перестанет его принимать.`, { danger: true, ok: 'Удалить', title: 'Площадка' }))) return;
    try { await api('/api/sites/' + s.id, { method: 'DELETE', body: {} }); load(); refresh(); } catch (e) { toast(e.message, true); }
  };
  const addAgent = async () => {
    setBusy('agent');
    try { const r = await api('/api/devices', { method: 'POST', body: { name: agentName.trim() || 'Удалённый сервер', driver: 'agent', kind: 'server', location: 'remote' } }); setAgentName(''); setShown({ kind: 'agent', name: r.device.name, token: r.agentToken }); load(); refresh(); }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const showAgent = async a => { try { const r = await api(`/api/devices/${a.id}/token`, { method: 'POST' }); setShown({ kind: 'agent', name: a.name, token: r.agentToken }); } catch (e) { toast(e.message, true); } };
  const ago = t => (t ? fmt.ago(t, data.now) : 'ещё не выходила на связь');
  return <>
    <Hint id="sites">Когда в другом месте нет белого IP и нельзя открыть порты (офис, дача, квартира родителей), Rack Live всё равно может следить за той сетью: там ставится свой Rack Live, он сам собирает данные и присылает их сюда одним исходящим соединением. Для одного сервера хватит маленького агента.</Hint>
    {priv ? <div className="warn-box"><Icon name="alert" size={16} /><div>Адрес <b>{base}</b> домашний — с другой площадки он не откроется. Сделайте внешнее имя: Настройки → Приложения на телефон. Ключи ниже подставят его сами.</div></div> : null}

    <Card title="Площадки (там стоит свой Rack Live)">
      {info.sites.length ? <div className="list">{info.sites.map(s => <div className="li" key={s.id} style={{ alignItems: 'center' }}>
        <KindIcon kind="server" size={36} round={10} />
        <div className="grow" style={{ minWidth: 0 }}><div className="row" style={{ gap: 6 }}><b>{s.name}</b><span className={'badge ' + (s.alive ? 'online' : 'offline')}>{s.alive ? 'на связи' : 'нет связи'}</span>{s.link ? <span className="badge" title="Можно смотреть и управлять устройствами площадки">управление: {({ view: 'смотреть', actions: 'кнопки', terminal: 'терминал' })[s.level] || 'есть'}</span> : null}</div>
          <div className="dim" style={{ fontSize: 12.5 }}>устройств: {s.devices} (в сети {s.online}) · {ago(s.last)}{s.version ? ' · версия ' + s.version : ''}</div></div>
        <Btn size="sm" onClick={() => showSite(s)}>Ключ</Btn><Btn size="sm" kind="danger" icon="trash" onClick={() => delSite(s)} />
      </div>)}</div> : <div className="dim" style={{ fontSize: 13.5 }}>Пока нет ни одной площадки.</div>}
      <div className="row" style={{ gap: 8, marginTop: 10 }}><input className="input grow" value={name} placeholder="Название, например «Дача» или «Офис на Ленина»" onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && name.trim() && addSite()} />
        <Btn kind="primary" icon="plus" busy={busy === 'site'} disabled={!name.trim()} onClick={addSite}>Добавить площадку</Btn></div>
    </Card>

    {shown && shown.kind === 'site' ? <Card title={`Как подключить «${shown.name}»`} style={{ marginTop: 10 }}>
      <ol className="steps">
        <li>На месте (в той сети) установите Rack Live: на роутер Keenetic / OpenWrt, мини-ПК, Raspberry или NAS — инструкция есть в папке <span className="mono">install</span> на GitHub.</li>
        <li>Откройте его: <b>Инструменты → Удалённые площадки и агенты → «Эта установка — сборщик»</b>.</li>
        <li>Вставьте этот ключ и включите отправку. Дальше устройства той сети появятся здесь сами.</li>
      </ol>
      <CodeBox text={siteKey(base, shown.token)} />
      <div className="dim3" style={{ fontSize: 12.5 }}>Ключ — это адрес этой установки и пароль для передачи данных. Он позволяет только присылать данные, управлять чем-либо здесь по нему нельзя. Кому не доверяете — не показывайте.</div>
    </Card> : null}

    <Card title="Агенты (один сервер без Rack Live)" style={{ marginTop: 10 }}>
      <div className="dim" style={{ fontSize: 12.5, marginBottom: 6 }}>Небольшая программа на удалённом сервере сама раз в минуту присылает нагрузку, память, диски, температуру и Docker. Запускается как служба и стартует вместе с системой (Linux, роутер с Entware, OpenWrt).</div>
      {info.agents.length ? <div className="list">{info.agents.map(a => <div className="li" key={a.id} style={{ alignItems: 'center' }}>
        <KindIcon kind="server" size={36} round={10} />
        <div className="grow" style={{ minWidth: 0 }}><div className="row" style={{ gap: 6 }}><b>{a.name}</b><span className={'badge ' + (a.status === 'online' || a.status === 'warning' ? 'online' : 'offline')}>{a.status === 'online' || a.status === 'warning' ? 'на связи' : 'нет данных'}</span></div>
          <div className="dim" style={{ fontSize: 12.5 }}>{a.updated ? 'последние данные ' + fmt.ago(a.updated, data.now) : 'ещё не подключался'}{a.ip ? ' · ' + a.ip : ''}</div></div>
        <Btn size="sm" onClick={() => showAgent(a)}>Команда</Btn>
      </div>)}</div> : null}
      <div className="row" style={{ gap: 8, marginTop: 10 }}><input className="input grow" value={agentName} placeholder="Название сервера" onChange={e => setAgentName(e.target.value)} onKeyDown={e => e.key === 'Enter' && addAgent()} />
        <Btn kind="primary" icon="plus" busy={busy === 'agent'} onClick={addAgent}>Добавить агента</Btn></div>
    </Card>

    {shown && shown.kind === 'agent' ? <Card title={`Установка агента «${shown.name}»`} style={{ marginTop: 10 }}>
      <div className="dim" style={{ fontSize: 13, marginBottom: 6 }}>Выполните на удалённом сервере (нужен Python 3). Открывать порты там не нужно.</div>
      <CodeBox text={agentCommand(shown.token, base)} />
    </Card> : null}

    <CollectorCard info={info} onChange={load} />
  </>;
}

/* THIS installation as a collector of a remote place */
function CollectorCard({ info, onChange }) {
  const toast = useToast(); const c = info.collector;
  const [key, setKey] = useState(''); const [busy, setBusy] = useState(false);
  const save = async (body, ok) => { setBusy(true); try { await api('/api/collector', { method: 'PUT', body }); if (ok) toast(ok); setKey(''); onChange(); } catch (e) { toast(e.message, true); } finally { setBusy(false); } };
  const now = async () => { setBusy(true); try { await api('/api/collector/push', { method: 'POST', body: {} }); toast('Отправлено'); onChange(); } catch (e) { toast(e.message, true); onChange(); } finally { setBusy(false); } };
  return <Card title="Эта установка — сборщик" style={{ marginTop: 10 }}>
    <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Если эта копия Rack Live стоит в удалённом месте, она может присылать список своих устройств и их состояние на главную установку. Пароли и ключи ваших устройств никуда не отправляются.</div>
    {c.keySet ? <div className="row" style={{ gap: 8, marginTop: 8, alignItems: 'center' }}><Switch on={c.enabled} onChange={v => save({ enabled: v }, v ? 'Отправка включена' : 'Отправка выключена')} />
      <div className="grow"><div>Отправлять на {c.server}</div>
        <div className="dim3" style={{ fontSize: 12.5 }}>{c.error ? <span style={{ color: 'var(--orange)' }}>{c.error}</span> : c.last ? `последняя отправка успешна · устройств: ${c.devices}` : c.enabled ? 'ждём первой отправки…' : 'выключено'}</div></div>
      <Btn size="sm" icon="refresh" busy={busy} onClick={now}>Отправить сейчас</Btn></div> : null}
    <Field label="Что разрешить главной установке" hint={c.link && c.link.connected ? 'Канал открыт' : c.link && c.link.error ? 'Канал не открыт: ' + c.link.error : 'Канал откроется сам, когда включите любой пункт кроме «Ничего»'}>
      <select className="input" value={c.level} onChange={e => save({ level: e.target.value }, 'Сохранено')}>
        <option value="off">Ничего — только присылать данные</option><option value="view">Смотреть: состояние, клиенты, порты</option>
        <option value="actions">Смотреть и нажимать кнопки устройств (перезагрузка, PoE…)</option><option value="terminal">Всё это и открывать терминал на устройствах</option></select></Field>
    <div className="dim3" style={{ fontSize: 12.5, marginBottom: 6 }}>Главная установка не получает пароли: все действия выполняются здесь, этой копией Rack Live, с её сохранёнными доступами. Каждое использование записывается в «События» обеих установок.</div>
    <div className="row" style={{ gap: 8, marginTop: 10 }}><input className="input mono grow" value={key} placeholder={c.keySet ? 'Новый ключ (если нужно заменить)' : 'Ключ площадки: RL1.…'} onChange={e => setKey(e.target.value)} />
      <Btn kind="primary" busy={busy} disabled={!key.trim()} onClick={() => save({ key: key.trim(), enabled: true }, 'Ключ принят, отправка включена')}>Подключить</Btn></div>
    <div className="row" style={{ gap: 8, marginTop: 8, alignItems: 'center' }}><Switch on={c.insecure} onChange={v => save({ insecure: v })} /><span className="dim" style={{ fontSize: 12.5 }}>Не проверять сертификат главной установки (для адреса с http или своим сертификатом)</span></div>
  </Card>;
}

/* a device of a remote site: its full live state and its buttons, fetched through the site's collector right now (rackd/sitelink.py) */
const LEVEL_RU = { view: 'смотреть', actions: 'смотреть и нажимать кнопки', terminal: 'смотреть, кнопки и терминал' };
function RemoteTab({ device }) {
  const toast = useToast(); const confirm = useConfirm();
  const [r, setR] = useState(null); const [err, setErr] = useState(''); const [busy, setBusy] = useState(''); const [term, setTerm] = useState(false);
  const rpc = body => api(`/api/sites/${device.siteId}/rpc`, { method: 'POST', body: { key: device.siteKey, ...body } });
  const load = async () => { setErr(''); try { setR((await rpc({ op: 'state' })).result); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, [device.id]);
  if (err) return <Card><div className="err-note" style={{ marginTop: 0 }}><b>Нет связи с площадкой «{device.siteName}».</b> {err}</div>
    <div className="dim3" style={{ fontSize: 12.5, marginTop: 8 }}>Управление работает, когда на площадке включён канал: там открыть Инструменты → Удалённые площадки и агенты → «Эта установка — сборщик» → «Что разрешить главной установке».</div>
    <Btn style={{ marginTop: 10 }} icon="refresh" onClick={load}>Повторить</Btn></Card>;
  if (!r) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Спрашиваю площадку…</div>;
  const st = r.state || {};
  const act = async a => {
    if (!(await confirm(a.confirm || `Выполнить «${a.label || a.id}» на площадке «${device.siteName}»?`, { title: device.name, ok: 'Выполнить', danger: /перезагр|reboot/i.test(a.label + a.id) }))) return;
    setBusy(a.id);
    try { const x = (await rpc({ op: 'action', action: a.id, params: {} })).result; toast((x && x.message) || 'Готово'); setTimeout(load, 3500); } catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const clients = (st.clients || []).slice(0, 120); const ports = st.ports || [];
  const buttons = (r.actions || []).filter(a => !(a.fields || []).length);
  return <>
    <Card title="С площадки, прямо сейчас">
      <div className="row wrap" style={{ gap: 6 }}><span className="badge online">канал открыт</span><span className="badge">разрешено: {LEVEL_RU[r.level] || r.level}</span>
        <Btn size="sm" icon="refresh" onClick={load}>Обновить</Btn>
        {r.terminal ? <Btn size="sm" icon="terminal" onClick={() => setTerm(true)}>Терминал</Btn> : null}</div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>Данные запрашиваются у сборщика на площадке по каналу, который он сам открыл. Пароли устройств остаются там.</div>
    </Card>
    {buttons.length ? <Card title="Действия"><div className="row wrap" style={{ gap: 6 }}>{buttons.map(a => <Btn key={a.id} size="sm" busy={busy === a.id} onClick={() => act(a)}>{a.label || a.id}</Btn>)}</div></Card>
      : r.level === 'view' ? <div className="dim3" style={{ fontSize: 12.5 }}>На площадке разрешён только просмотр: кнопки управления появятся, когда там выберут «смотреть и нажимать кнопки».</div> : null}
    {ports.length ? <Card title={`Порты · ${ports.filter(p => p.link).length}/${ports.length}`}><div className="list">{ports.slice(0, 64).map(p => <div className="li" key={p.n} style={{ fontSize: 13 }}>
      <b style={{ minWidth: 26 }}>{p.n}</b><span className={'badge ' + (p.link ? 'online' : '')}>{p.link ? (p.speed ? p.speed + ' Мбит/с' : 'есть линк') : 'нет линка'}</span>
      <span className="grow dim ellipsis">{p.label || ''}{(p.peers || []).length ? ' · ' + (p.peers[0].name || p.peers[0].mac) : ''}</span></div>)}</div></Card> : null}
    {clients.length ? <Card title={`Клиенты · ${(st.clients || []).length}`}><div className="list">{clients.map((c, i) => <div className="li" key={i} style={{ fontSize: 13 }}>
      <KindIcon kind={c.kind || 'other'} size={26} round={8} /><div className="grow" style={{ minWidth: 0 }}><div className="ellipsis">{c.name || c.hostname || c.mac}</div>
        <div className="dim3 mono ellipsis" style={{ fontSize: 11.5 }}>{[c.ip, c.mac, c.segment].filter(Boolean).join(' · ')}</div></div></div>)}</div></Card> : null}
    {term ? <Modal title={`Терминал · ${device.name} (${device.siteName})`} wide onClose={() => setTerm(false)} icon={<Icon name="terminal" size={20} color="var(--accent)" />}>
      <TerminalView extra={`&site=${encodeURIComponent(device.siteId)}&device=${encodeURIComponent(device.siteKey)}`} onClose={() => setTerm(false)} /></Modal> : null}
  </>;
}
