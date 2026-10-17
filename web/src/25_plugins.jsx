/* Device plugins: Entware guide, AWG native (AmneziaWG from a .conf), installers (soon) */
function PluginsTab({ device }) {
  const toast = useToast();
  const [st, setSt] = useState(null);
  const [err, setErr] = useState('');
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('plugin'));      // ?…&tab=plugins&plugin=awg
  const load = async () => {
    setErr('');
    try { const r = await api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { op: 'status' } }); setSt(r); }
    catch (e) { setErr(e.message); }
  };
  useEffect(() => { load(); }, [device.id]);
  if (err) return <Card><div style={{ color: 'var(--red)' }}>Не удалось связаться с роутером: {err}</div><Btn style={{ marginTop: 10 }} icon="refresh" onClick={load}>Повторить</Btn></Card>;
  if (!st) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Проверяю, что уже установлено на роутере…</div>;
  return <>
    <Hint id="plugins">Дополнения, которые ставятся прямо на это устройство. Rack Live сам проверяет, что уже есть, и подсказывает, чего не хватает.
      Перед любым изменением спросит подтверждение и покажет журнал установки.</Hint>
    {st.plugins.map(p => <PluginCard key={p.id} p={p} st={st} device={device} open={open === p.id} toggle={() => setOpen(open === p.id ? null : p.id)}
      reload={load} openPlugin={setOpen} />)}
  </>;
}

function PluginBadge({ p }) {
  if (p.installed) return <span className="badge online"><Icon name="check" size={12} />{p.id === 'awg' ? 'подключено' : 'установлено'}</span>;
  if (p.soon) return <span className="badge">скоро</span>;
  if (p.kind === 'guide') return <span className="badge warning">не установлено</span>;
  return null;
}

function Checks({ checks }) {
  return <div className="checks">{checks.map((c, i) => <div key={i} className={'check' + (c.ok ? ' ok' : c.optional ? ' opt' : ' no')}>
    <span className="check-ico"><Icon name={c.ok ? 'check' : c.optional ? 'other' : 'x'} size={13} stroke={2.4} /></span>
    <span className="grow">{c.label}{c.optional && !c.ok ? <span className="dim3"> · по желанию</span> : null}</span>
    {c.hint ? <span className="dim mono" style={{ fontSize: 11.5 }}>{c.hint}</span> : null}</div>)}</div>;
}

function PluginCard({ p, st, device, open, toggle, reload, openPlugin }) {
  return <div className={'card plugin' + (open ? ' open' : '')}>
    <button type="button" className="plugin-head" onClick={toggle}>
      <div className="ico-circle"><Icon name={p.icon} size={18} /></div>
      <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}><div className="row" style={{ gap: 8 }}><b>{p.title}</b><PluginBadge p={p} /></div>
        <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4, marginTop: 2 }}>{p.description}</div></div>
      <Icon name="chevron" size={16} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} />
    </button>
    {open ? <div className="plugin-body">
      {p.id === 'entware' ? <EntwareGuide p={p} reload={reload} /> : null}
      {p.id === 'awg' ? <AwgPlugin p={p} device={device} reload={reload} openPlugin={openPlugin} /> : null}
      {p.kind === 'installer' ? <InstallerPlugin p={p} device={device} reload={reload} openPlugin={openPlugin} /> : null}
      {p.kind === 'modem' ? <ModemPlugin p={p} device={device} reload={reload} /> : null}
      {p.kind === 'panel' ? <PanelPlugin p={p} device={device} reload={reload} /> : null}
      {p.kind === 'agents' ? <AgentsPlugin p={p} device={device} reload={reload} /> : null}
      {p.kind === 'collector' ? <CollectorPlugin p={p} device={device} reload={reload} /> : null}
      {p.kind === 'community' ? <CommunityPlugin p={p} device={device} reload={reload} /> : null}
    </div> : null}
  </div>;
}

function EntwareGuide({ p, reload }) {
  return <>
    <Checks checks={p.checks} />
    {p.installed ? <div className="dim" style={{ fontSize: 13 }}>Entware установлен — можно ставить дополнения из каталога ниже.</div> : null}
    <ol className="steps">
      <li><b>Компоненты.</b> Веб-интерфейс роутера → «Управление» → «Общие настройки» (на новых прошивках — «Параметры системы») → <b>«Изменить набор компонентов»</b>.
        Включите <b>«Поддержка открытых пакетов»</b> и <b>«Модули ядра подсистемы Netfilter»</b> → «Установить». Роутер перезагрузится.</li>
      <li><b>Накопитель.</b> USB-флешка, отформатированная в <b>ext4</b>, или встроенная память, если роутер предлагает её в разделе OPKG.</li>
      <li><b>Установщик.</b> На накопителе создайте папку <code>install</code> и положите в неё файл
        {p.installer ? <> <a href={p.installer} target="_blank" rel="noreferrer">{p.installer.split('/').pop()}</a> (для вашего роутера — процессор {p.arch})</> : ' установщика Entware для процессора вашего роутера'}.</li>
      <li><b>Запуск.</b> Раздел <b>OPKG</b> (в меню «Управление» или «Приложения») → выберите накопитель → «Сохранить». Установка идёт 1–3 минуты,
        ход видно в «Диагностика» → «Системный журнал».</li>
      <li><b>Вход.</b> SSH на порт <code>222</code>, логин <code>root</code>, пароль <code>keenetic</code> — сразу смените его командой <code>passwd</code>.</li>
    </ol>
    <Btn icon="refresh" onClick={reload}>Проверить снова</Btn>
  </>;
}

function AwgPlugin({ p, device, reload, openPlugin }) {
  const toast = useToast(); const confirm = useConfirm(); const { refresh } = useApp();
  const comp = (p.checks || [])[0] || {};
  const [name, setName] = useState('');
  const [conf, setConf] = useState('');
  const [prev, setPrev] = useState(null);
  const [prevErr, setPrevErr] = useState('');
  const [routing, setRouting] = useState(true);
  const [domains, setDomains] = useState('');
  const [domInfo, setDomInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [editDom, setEditDom] = useState(null);           // tunnel whose site list is being replaced
  const fileRef = useRef(null);
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: 'awg', ...body } });
  const preview = async (text, dom) => {
    if (!text.trim()) { setPrev(null); setPrevErr(''); return; }
    try { const r = await call({ op: 'preview', conf: text, domains: dom }); setPrev(r.preview); setPrevErr(''); setDomInfo(dom ? r : null); }
    catch (e) { setPrev(null); setPrevErr(e.message); }
  };
  const onFile = async e => {
    const f = e.target.files[0]; if (!f) return; const text = await f.text(); e.target.value = '';
    setConf(text); if (!name) setName(f.name.replace(/\.conf$/i, '').slice(0, 40)); preview(text, domains);
  };
  const install = async () => {
    const what = routing ? `Создать подключение «${name || 'AmneziaWG'}» и направить через него ${domInfo ? domInfo.domains : 'указанные'} сайтов?`
      : `Создать подключение «${name || 'AmneziaWG'}» без маршрутизации? Трафик в него сам не пойдёт, пока вы не направите нужные сайты.`;
    if (!(await confirm(what + ' Интернет при этом не прервётся.', { title: 'AWG native', ok: 'Создать' }))) return;
    setBusy(true); setResult(null);
    try { const r = await call({ op: 'install', conf, name, routing, domains: routing ? domains : '' }); setResult({ ...r, routing });
      toast(r.message, !r.up); setConf(''); setPrev(null); setDomains(''); setDomInfo(null); setName(''); reload(); refresh(); }
    catch (e) { setResult({ error: e.message }); toast(e.message, true); }
    finally { setBusy(false); }
  };
  const component = async () => {
    if (!(await confirm('Роутер скачает компонент WireGuard и перезагрузится — интернет пропадёт на 2–5 минут. Продолжить?', { danger: true, ok: 'Установить' }))) return;
    try { const r = await call({ op: 'component' }); toast(r.message); } catch (e) { toast(e.message + ' — установите компонент вручную: «Изменить набор компонентов» → «WireGuard VPN»', true); }
  };
  const remove = async t => {
    if (!(await confirm(`Удалить подключение «${t.name}» (${t.iface}) и его списки сайтов?`, { danger: true, ok: 'Удалить' }))) return;
    try { const r = await call({ op: 'remove', iface: t.iface }); toast(r.message); reload(); refresh(); } catch (e) { toast(e.message, true); }
  };
  const tunnels = p.tunnels || [];
  return <>
    <Checks checks={p.checks || []} />
    {!comp.ok ? <div className="row wrap"><Btn kind="primary" icon="download" onClick={component}>Установить компонент WireGuard</Btn>
      <span className="dim3" style={{ fontSize: 12.5 }}>роутер перезагрузится</span></div> : null}
    {tunnels.length ? <div>
      <div className="card-title" style={{ marginBottom: 4 }}>Подключения WireGuard на роутере</div>
      <div className="list">{tunnels.map(t => <div className="li" key={t.iface}>
        <div className="ico-circle"><Icon name="shield" size={16} /></div>
        <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>{t.name}</b>
          <div className="dim" style={{ fontSize: 12 }}>{t.iface}{t.managed ? ' · создано Rack Live' : ''}{t.managed ? (t.groups ? ` · ${t.domains} сайтов через туннель` : ' · без маршрутизации') : ''}</div></div>
        {t.managed ? <><Btn size="sm" onClick={() => setEditDom(t)}>Сайты</Btn><Btn size="sm" kind="danger" icon="trash" onClick={() => remove(t)} title="Удалить" /></> : null}
      </div>)}</div></div> : null}
    {comp.ok ? <div className="awg-form">
      <div className="card-title">Новое подключение из файла</div>
      <div className="row wrap" style={{ gap: 8 }}>
        <Btn icon="upload" onClick={() => fileRef.current.click()}>Выбрать файл .conf</Btn>
        <span className="dim3" style={{ fontSize: 12.5 }}>или вставьте текст конфига ниже</span>
        <input ref={fileRef} type="file" accept=".conf,text/plain" style={{ display: 'none' }} onChange={onFile} />
      </div>
      <textarea className="input mono" rows={4} value={conf} placeholder={'[Interface]\nPrivateKey = …\nJc = 4 …\n[Peer]\nEndpoint = …'}
        onChange={e => setConf(e.target.value)} onBlur={() => preview(conf, domains)} style={{ fontSize: 12 }} />
      {prevErr ? <div style={{ color: 'var(--red)', fontSize: 13 }}>{prevErr}</div> : null}
      {prev ? <div className="awg-prev">
        <KV rows={[['Тип', prev.type], ['Сервер', <span className="mono">{prev.server}</span>], ['Адрес в туннеле', <span className="mono">{prev.address}</span>],
          ['MTU', prev.mtu], ...(prev.psk ? [['Общий ключ (PSK)', 'есть']] : []),
          ...(prev.dns ? [['DNS из конфига', <span className="dim">{prev.dns} — не используется, роутер оставит свой DNS</span>]] : [])]} />
        {prev.ipv6Skipped ? <div className="dim3" style={{ fontSize: 12 }}>IPv6-адрес из конфига пропущен — туннель будет работать по IPv4.</div> : null}
      </div> : null}
      <Field label="Название подключения"><input className="input" value={name} maxLength={40} placeholder="Например: AWG Нидерланды" onChange={e => setName(e.target.value)} /></Field>
      <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={routing} onChange={setRouting} />
        <div className="grow"><div>Маршрутизация по доменам</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>{routing ? 'Через туннель пойдут только сайты из списка ниже — для всех устройств в сети. Остальное как обычно.'
            : 'Только создать подключение — трафик в него сам не пойдёт.'}</div></div></div>
      {routing ? <Field label="Сайты, которые пойдут через туннель" hint={domInfo ? `Распознано: ${domInfo.domains}${domInfo.skipped.length ? ' · пропущено: ' + domInfo.skipped.join(', ') : ''}`
        : 'По одному на строку: домены (youtube.com — со всеми поддоменами), IP или подсети (1.2.3.0/24). Можно вставить готовый список.'}>
        <textarea className="input mono" rows={6} value={domains} placeholder={'youtube.com\ngooglevideo.com\nytimg.com'} style={{ fontSize: 12 }}
          onChange={e => setDomains(e.target.value)} onBlur={() => conf.trim() && preview(conf, domains)} /></Field>
        : <div className="awg-suggest"><Icon name="globe2" size={18} /><div className="grow">Для удобной маршрутизации — готовые списки сайтов, веб-панель, несколько туннелей — поставьте
          <b> HydraRoute Neo</b>. <button type="button" className="linkbtn" onClick={() => openPlugin('hydraroute')}>Открыть плагин</button></div></div>}
      <Btn kind="primary" busy={busy} disabled={!prev || (routing && !domains.trim())} onClick={install} style={{ padding: 12 }}>
        {busy ? 'Создаю подключение…' : 'Создать подключение'}</Btn>
    </div> : null}
    {result ? <PluginResult r={result} openPlugin={openPlugin} /> : null}
    {editDom ? <DomainsEditor t={editDom} call={call} onClose={() => setEditDom(null)} onDone={() => { setEditDom(null); reload(); }} /> : null}
  </>;
}

/* one-click installers (HydraRoute Neo, AWG Manager): the authors' official script, run over SSH in Entware */
function InstallerPlugin({ p, device, reload, openPlugin }) {
  const toast = useToast(); const confirm = useConfirm(); const { refresh } = useApp();
  const ssh = p.ssh || {};
  const [cred, setCred] = useState({ port: ssh.port || 222, user: ssh.user || 'root', password: '' });
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState(null);
  const [opts, setOpts] = useState(() => Object.fromEntries((p.options || []).map(o => [o.id, o.on])));
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: p.id, ...opts, ...body } });
  const saveSsh = async () => { setBusy('ssh');
    try { const r = await call({ op: 'ssh', ...cred }); toast(r.message); setCred(c => ({ ...c, password: '' })); reload(); } catch (e) { toast(e.message, true); } finally { setBusy(''); } };
  const run = async op => {
    const text = op === 'remove' ? `Удалить ${p.title} с роутера? Его настройки будут удалены.`
      : `Rack Live скачает официальный установщик ${p.title} (автор — ${p.author}) и запустит его в Entware. Это займёт 1–5 минут, интернет не прервётся. Продолжить?`;
    if (!(await confirm(text, { title: p.title, ok: op === 'remove' ? 'Удалить' : p.installed ? 'Обновить' : 'Установить', danger: op === 'remove' }))) return;
    setBusy(op); setResult(null);
    try { const r = await call({ op }); setResult({ ...r, routing: true, up: r.ok, kept: true }); toast(r.message, !r.ok); reload(); refresh(); }
    catch (e) { setResult({ error: e.message, kept: true }); toast(e.message, true); }
    finally { setBusy(''); }
  };
  const required = (p.checks || []).filter(c => !c.optional && !/SSH/.test(c.label));
  const ready = required.every(c => c.ok) && ssh.ok;
  return <>
    <Checks checks={p.checks || []} />
    {!required.find(c => /Entware/.test(c.label)) || required.find(c => /Entware/.test(c.label)).ok ? null
      : <div className="dim" style={{ fontSize: 13 }}>Сначала установите Entware — <button type="button" className="linkbtn" onClick={() => openPlugin('entware')}>инструкция</button></div>}
    {!ssh.ok ? <div className="awg-form">
      <div className="card-title">Доступ к Entware по SSH</div>
      <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>Установка идёт командами внутри Entware. Укажите пароль root, который вы задали после установки Entware
        (по умолчанию <code>keenetic</code>). Пароль хранится на сервере Rack Live и в браузер не передаётся.</div>
      {ssh.error ? <div style={{ color: 'var(--red)', fontSize: 13 }}>{ssh.error}</div> : null}
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
        <div style={{ width: 90 }}><Field label="Порт"><input className="input" value={cred.port} onChange={e => setCred({ ...cred, port: e.target.value })} /></Field></div>
        <div style={{ width: 120 }}><Field label="Логин"><input className="input" value={cred.user} onChange={e => setCred({ ...cred, user: e.target.value })} /></Field></div>
        <div className="grow" style={{ minWidth: 150 }}><Field label="Пароль"><input className="input" type="password" value={cred.password} placeholder={ssh.set ? '•••••••• (сохранён)' : ''}
          onChange={e => setCred({ ...cred, password: e.target.value })} autoComplete="off" /></Field></div>
      </div>
      <Btn kind="primary" busy={busy === 'ssh'} disabled={!cred.password && !ssh.set} onClick={saveSsh}>Проверить и сохранить</Btn>
    </div> : null}
    {p.installed ? <div className="plugin-result">
      <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}><Icon name="check" size={18} />
        <div className="grow"><b>{p.title}{p.version ? ' ' + p.version : ''} установлен.</b> Панель: <a href={p.url} target="_blank" rel="noreferrer">{p.url}</a>
          <div className="dim" style={{ fontSize: 12.5 }}>Вход: {p.login}{p.singbox ? ' · ' + p.singbox.replace('sing-box version ', 'sing-box ') : ''}</div></div></div></div> : null}
    {p.warning ? <div className="err-note" style={{ marginTop: 0 }}>{p.warning}</div> : null}
    {(p.options || []).map(o => <div className="row" key={o.id} style={{ alignItems: 'flex-start' }}><Switch on={!!opts[o.id]} onChange={v => setOpts({ ...opts, [o.id]: v })} />
      <div className="grow"><div>{o.label}</div>{o.hint ? <div className="dim3" style={{ fontSize: 12.5 }}>{o.hint}</div> : null}</div></div>)}
    <div className="row wrap">
      <Btn kind="primary" icon={p.installed ? 'refresh' : 'download'} busy={busy === 'install'} disabled={!ready || !!busy} onClick={() => run('install')}>
        {busy === 'install' ? 'Устанавливаю… (до 5 минут)' : p.installed ? 'Обновить / переустановить' : 'Установить'}</Btn>
      {p.installed && ssh.ok ? <Btn kind="danger" icon="trash" busy={busy === 'remove'} disabled={!!busy} onClick={() => run('remove')}>Удалить</Btn> : null}
      {p.home ? <a className="btn" href={p.home} target="_blank" rel="noreferrer"><Icon name="link" size={16} />О проекте</a> : null}
    </div>
    {!ready && !p.installed ? <div className="dim3" style={{ fontSize: 12.5 }}>Кнопка станет активной, когда все пункты выше будут отмечены зелёным.</div> : null}
    {result ? <PluginResult r={result} openPlugin={openPlugin} /> : null}
  </>;
}

/* USB modem drivers: what is plugged in → suggested variant; any variant can be installed, removed, and another one tried */
function ModemPlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm(); const { refresh } = useApp();
  const [busy, setBusy] = useState('');
  const [result, setResult] = useState(null);
  const run = async (m, op) => {
    const text = op === 'remove' ? `Удалить драйверы варианта «${m.title}»? Общие пакеты, нужные другим вариантам, останутся.`
      : `Установить «${m.title}»? Пакеты: ${m.packages.join(', ')}. Интернет не прервётся.`;
    if (!(await confirm(text, { title: 'USB-модем', ok: op === 'remove' ? 'Удалить' : 'Установить', danger: op === 'remove' }))) return;
    setBusy(m.id + op); setResult(null);
    try { const r = await api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: 'modem', op, profile: m.id } });
      setResult({ ...r, kept: true, routing: true, up: r.ok }); toast(r.message, !r.ok); reload(); refresh(); }
    catch (e) { setResult({ error: e.message, kept: true }); toast(e.message, true); }
    finally { setBusy(''); }
  };
  const sug = (p.profiles || []).find(m => m.suggested);
  return <>
    <div className="awg-prev" style={{ padding: '10px 12px', fontSize: 13.5, lineHeight: 1.45 }}>
      {(p.usb || []).length ? <><b>Подключено к USB:</b> {p.usb.join('; ')}
        {(p.drivers || []).length ? <div className="dim" style={{ fontSize: 12.5 }}>Работающие драйверы: {p.drivers.join(', ')}{(p.devs || []).length ? ' · ' + p.devs.join(', ') : ''}</div> : null}
        <div style={{ marginTop: 4 }}>{sug ? <>Похоже, подойдёт: <b>{sug.title}</b>.</> : 'Определить тип модема не удалось — начните с первого варианта.'}</div></>
        : 'К USB ничего не подключено. Вставьте модем и нажмите «Обновить» — Rack Live подскажет вариант.'}
    </div>
    <div className="list">{(p.profiles || []).map(m => <div className={'li modem-opt' + (m.suggested ? ' sug' : '')} key={m.id} style={{ alignItems: 'flex-start' }}>
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="row wrap" style={{ gap: 6 }}><b style={{ fontSize: 14 }}>{m.title}</b>
          {m.installed ? <span className="badge online">установлено</span> : null}{m.suggested ? <span className="badge info">подходит</span> : null}</div>
        <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4 }}>{m.note}</div>
        <div className="dim3 mono" style={{ fontSize: 11 }}>{m.packages.join(' · ')}</div></div>
      {m.installed ? <Btn size="sm" kind="danger" icon="trash" busy={busy === m.id + 'remove'} disabled={!!busy} onClick={() => run(m, 'remove')}>Удалить</Btn>
        : <Btn size="sm" kind={m.suggested ? 'primary' : ''} icon="download" busy={busy === m.id + 'install'} disabled={!!busy} onClick={() => run(m, 'install')}>Установить</Btn>}
    </div>)}</div>
    <div className="row"><Btn size="sm" icon="refresh" onClick={reload}>Обновить</Btn>
      <span className="dim3" style={{ fontSize: 12.5 }}>Не заработало — удалите вариант и попробуйте следующий; иногда помогает переподключить модем.</span></div>
    {result ? <PluginResult r={result} /> : null}
  </>;
}

/* VPS panels (3x-ui, Remnawave): optional domain (waits for the A record), optional inbounds + test user; installs as a background job */
function CopyRow({ k, v, mono = true }) {
  const toast = useToast();
  return <div className="copy-row"><span className="dim">{k}</span><span className={'grow ellipsis' + (mono ? ' mono' : '')} title={v}>{v}</span>
    <Btn size="sm" icon="copy" title="Скопировать" onClick={() => { try { navigator.clipboard.writeText(v); toast('Скопировано'); } catch (e) { toast('Не удалось скопировать', true); } }} /></div>;
}
function PanelInfo({ info, title }) {
  return <div className="plugin-result">
    <div className="row" style={{ gap: 8, alignItems: 'flex-start', marginBottom: 8 }}><Icon name="check" size={18} /><b className="grow">{title} работает</b></div>
    <div className="col" style={{ gap: 6 }}>
      <div className="copy-row"><span className="dim">Панель</span><a className="grow ellipsis" href={info.url} target="_blank" rel="noreferrer">{info.url}</a></div>
      <CopyRow k="Логин" v={info.user} /><CopyRow k="Пароль" v={info.password} />
      {info.note ? <div className="dim3" style={{ fontSize: 12.5 }}>{info.note}</div> : null}
      {(info.links || []).length ? <><div className="card-title" style={{ marginTop: 6 }}>Тестовый пользователь</div>
        {info.links.map((l, i) => <CopyRow key={i} k={l.name} v={l.url} />)}
        <div className="dim3" style={{ fontSize: 12.5 }}>Вставьте ссылку в клиент (v2rayN, Hiddify, Streisand, v2RayTun) — подключение должно заработать сразу.</div></> : null}
    </div></div>;
}

function PanelPlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm(); const { refresh } = useApp();
  const [withDomain, setWithDomain] = useState(!!p.needsDomain);
  const [domain, setDomain] = useState('');
  const [inbounds, setInbounds] = useState(true);
  const [dns, setDns] = useState(null);                       // {match, records, ip, domain}
  const [waiting, setWaiting] = useState(false);
  const [job, setJob] = useState(null);                       // {id, stage, done, error, result, t}
  const [now, setNow] = useState(Date.now());
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: p.id, ...body } });
  const checkDns = async () => { try { const r = await call({ op: 'dns', domain, ip: p.ip }); setDns(r); return r; } catch (e) { setDns({ error: e.message }); return null; } };
  const startJob = async op => {
    try { const r = await call({ op, withDomain, domain, inbounds: withDomain && inbounds }); setJob({ id: r.job, stage: 'Запуск…', done: false, t: Date.now() / 1000 }); }
    catch (e) { toast(e.message, true); }
  };
  useEffect(() => {                                            // poll the background job
    if (!job || job.done) return;
    const t = setInterval(async () => { setNow(Date.now());
      try { const j = await call({ op: 'job', job: job.id }); setJob(x => ({ ...x, ...j }));
        if (j.done) { toast(j.error ? 'Не получилось: ' + j.error : (j.result && j.result.message) || 'Готово', !!j.error); reload(); refresh(); } } catch (e) { }
    }, 3000);
    return () => clearInterval(t);
  }, [job && job.id, job && job.done]);
  useEffect(() => {                                            // waiting for the A record: check every 20 s, then install by itself
    if (!waiting) return;
    let alive = true;
    const tick = async () => { const r = await checkDns(); if (!alive) return;
      if (r && r.match) { setWaiting(false); toast('Домен заработал — начинаю установку'); startJob('install'); } };
    const t = setInterval(tick, 20000); return () => { alive = false; clearInterval(t); };
  }, [waiting]);
  const install = async () => {
    const what = `Установить ${p.title}${withDomain ? ` на ${domain}` : ''}? Будут поставлены ${withDomain ? 'nginx с сайтом-заглушкой, сертификат Let\'s Encrypt с автопродлением, ' : ''}`
      + `${p.title}${withDomain && inbounds ? `, инбаунды VLESS TCP (${8443}) и XHTTP (${2053}) и тестовый пользователь` : ''}. Займёт ${p.id === 'remnawave' ? '5–15' : '2–5'} минут.`
      + (withDomain ? ' Если домен ещё не указывает на сервер, Rack Live дождётся этого и начнёт сам.' : '');
    if (!(await confirm(what, { title: p.title, ok: 'Установить' }))) return;
    if (withDomain) {
      const r = await checkDns(); if (!r) return;
      if (!r.match) { setWaiting(true); return; }        // the 20-second loop starts the install when the A record appears
    }
    startJob('install');
  };
  const remove = async () => {
    if (!(await confirm(`Удалить ${p.title} с сервера?${p.id === 'remnawave' ? ' База данных (пользователи, подписки) будет удалена безвозвратно.' : ' Пользователи и инбаунды будут удалены.'}`,
      { title: p.title, ok: 'Удалить', danger: true }))) return;
    startJob('remove');
  };
  const required = (p.checks || []).filter(c => !c.optional);
  const ready = required.every(c => c.ok) && (!withDomain || domain.trim());
  const running = job && !job.done;
  return <>
    <Checks checks={p.checks || []} />
    {p.installed && p.info ? <PanelInfo info={p.info} title={p.title} /> : p.installed ? <div className="plugin-result"><Icon name="check" size={16} /> {p.title} уже установлен на сервере{p.version ? ' (' + p.version + ')' : ''} — не через Rack Live, поэтому данных для входа здесь нет.</div> : null}
    {!p.installed ? <div className="awg-form">
      <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={withDomain} onChange={v => !p.needsDomain && setWithDomain(v)} disabled={p.needsDomain} />
        <div className="grow"><div>Установить с доменом{p.needsDomain ? ' (обязательно)' : ''}</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>nginx с сайтом-заглушкой, сертификат Let's Encrypt с автопродлением, панель — за HTTPS на вашем домене.
            {!withDomain && !p.needsDomain ? ' Без домена панель получит сертификат на IP (продлевается сам).' : ''}</div></div></div>
      {withDomain ? <Field label="Домен" hint={p.ip ? `Нужна A-запись: домен → ${p.ip} (IP этого сервера)` : 'Нужна A-запись на IP этого сервера'}>
        <div className="row" style={{ gap: 8 }}><input className="input grow" value={domain} placeholder="vpn.example.com" onChange={e => { setDomain(e.target.value); setDns(null); setWaiting(false); }} />
          <Btn onClick={checkDns} disabled={!domain.trim()}>Проверить DNS</Btn></div></Field> : null}
      {dns ? dns.error ? <div style={{ color: 'var(--red)', fontSize: 13 }}>{dns.error}</div>
        : dns.match ? <div className="check ok"><span className="check-ico"><Icon name="check" size={13} stroke={2.4} /></span>{dns.domain} → {dns.ip} — всё готово</div>
        : <div className="err-note" style={{ marginTop: 0 }}><b>Домен пока не указывает на этот сервер.</b> {dns.records.length ? `Сейчас ${dns.domain} → ${dns.records.join(', ')}.` : `У ${dns.domain} нет A-записи.`}
          {' '}У регистратора домена (reg.ru, Cloudflare…) создайте <b>A-запись</b>: имя <code>{dns.domain}</code>, значение <code>{dns.ip}</code>. Обычно начинает работать через 5–30 минут.</div> : null}
      {waiting ? <div className="row" style={{ gap: 8, fontSize: 13.5 }}><span className="spin-dot" /><span className="grow">Жду, когда {dns && dns.domain} начнёт указывать на {p.ip} — проверяю каждые 20 секунд, установка начнётся сама. Можно закрыть окно и вернуться позже.</span>
        <Btn size="sm" onClick={() => setWaiting(false)}>Отмена</Btn></div> : null}
      <div className="row" style={{ alignItems: 'flex-start', opacity: withDomain ? 1 : .55 }}><Switch on={withDomain && inbounds} onChange={setInbounds} disabled={!withDomain} />
        <div className="grow"><div>Создать инбаунды VLESS TCP + XHTTP и тестового пользователя</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>{withDomain ? 'VLESS TCP+TLS на порту 8443 и VLESS XHTTP+TLS на порту 2053 на сертификате домена; ссылки тестового пользователя покажу здесь.'
            : 'Нужен домен: инбаунды используют его сертификат.'}</div></div></div>
      <Btn kind="primary" icon="download" busy={running} disabled={!ready || running || waiting} onClick={install} style={{ padding: 12 }}>
        {running ? 'Устанавливаю…' : waiting ? 'Жду DNS…' : 'Установить ' + p.title}</Btn>
      {!ready && !running ? <div className="dim3" style={{ fontSize: 12.5 }}>{withDomain && !domain.trim() ? 'Укажите домен.' : 'Кнопка станет активной, когда все пункты выше будут отмечены зелёным.'}</div> : null}
    </div> : null}
    {running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{job.stage}</b>
      <div className="dim3" style={{ fontSize: 12 }}>идёт {Math.max(0, Math.round(now / 1000 - job.t))} с · окно можно закрыть, установка продолжится на сервере Rack Live</div></div></div> : null}
    {job && job.done ? (job.error ? <PluginResult r={{ error: job.error, kept: true, log: [] }} />
      : <>{job.result && job.result.info ? <PanelInfo info={job.result.info} title={p.title} /> : <PluginResult r={{ ...job.result, kept: true, up: true }} />}
        {job.result && (job.result.log || []).length ? <PluginResult r={{ message: `Журнал (${Math.round(job.dur / 60)} мин)`, log: job.result.log, kept: true, up: true }} /> : null}</>) : null}
    <div className="row wrap">
      {p.installed ? <Btn kind="danger" icon="trash" disabled={running} onClick={remove}>Удалить {p.title}</Btn> : null}
      {p.home ? <a className="btn" href={p.home} target="_blank" rel="noreferrer"><Icon name="link" size={16} />О проекте</a> : null}
    </div>
  </>;
}

/* «Сборщик площадки»: a whole Rack Live in collector mode on this server / mini PC, installed over SSH (rackd/collector_install.py) */
const COLLECTOR_LEVELS = [['view', 'Только смотреть'], ['actions', 'Смотреть и нажимать кнопки устройств'], ['terminal', 'Смотреть, нажимать кнопки и открывать терминал']];
function CollectorInfo({ info, site, title }) {
  const level = (COLLECTOR_LEVELS.find(l => l[0] === info.level) || [])[1];
  return <div className="plugin-result">
    <div className="row" style={{ gap: 8, alignItems: 'flex-start', marginBottom: 8 }}><Icon name="check" size={18} /><b className="grow">{title}</b></div>
    <div className="col" style={{ gap: 6 }}>
      <div className="copy-row"><span className="dim">Панель там</span><a className="grow ellipsis" href={info.url} target="_blank" rel="noreferrer">{info.url}</a></div>
      {info.password ? <CopyRow k="Пароль администратора" v={info.password} /> : <div className="dim3" style={{ fontSize: 12.5 }}>Пароль администратора задан при прошлой установке — здесь он не показывается.</div>}
      <div className="copy-row"><span className="dim">Площадка</span><span className="grow">{info.siteName}{site ? <> · {site.alive ? <span style={{ color: 'var(--green)' }}>на связи</span> : <span className="dim3">{site.last ? 'давно не отвечает' : 'ждём первого сообщения (до минуты)'}</span>}{site.devices ? ` · устройств: ${site.devices}` : ''}</> : null}</span></div>
      {info.version ? <div className="copy-row"><span className="dim">Версия</span><span className="grow">{info.version}</span></div> : null}
      {level ? <div className="copy-row"><span className="dim">Управление отсюда</span><span className="grow">{level}</span></div> : null}
      <div className="dim3" style={{ fontSize: 12.5 }}>Откройте панель по ссылке, войдите этим паролем — это обычный Rack Live: «Инструменты → Устройства → Сканировать сеть» найдёт всё в сети площадки, «Камеры» настроит камеры.
        Все найденные устройства сами появятся на этой панели в «Инструменты → Удалённые площадки и агенты».</div>
    </div></div>;
}

function CollectorPlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm(); const { refresh } = useApp();
  const [name, setName] = useState(device.name || '');
  const [server, setServer] = useState(p.serverUrl || '');
  const [port, setPort] = useState(String(p.defaultPort || 9998));
  const [level, setLevel] = useState('view');
  const [insecure, setInsecure] = useState(false);
  const [dropSite, setDropSite] = useState(false);
  const [job, setJob] = useState(null);
  const [now, setNow] = useState(Date.now());
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: 'collector', ...body } });
  const start = async (op, extra) => {
    try { const r = await call({ op, ...extra }); setJob({ id: r.job, stage: 'Запуск…', done: false, t: Date.now() / 1000 }); }
    catch (e) { toast(e.message, true); }
  };
  useEffect(() => {
    if (!job || job.done) return;
    const t = setInterval(async () => { setNow(Date.now());
      try { const j = await call({ op: 'job', job: job.id }); setJob(x => ({ ...x, ...j }));
        if (j.done) { toast(j.error ? 'Не получилось: ' + j.error : (j.result && j.result.message) || 'Готово', !!j.error); reload(); refresh(); } } catch (e) { }
    }, 3000);
    return () => clearInterval(t);
  }, [job && job.id, job && job.done]);
  const required = (p.checks || []).filter(c => !c.optional);
  const ready = required.every(c => c.ok) && server.trim() && name.trim() && /^\d+$/.test(port);
  const running = job && !job.done;
  const install = async () => {
    const local = /^https?:\/\/(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(server.trim());
    if (!(await confirm(`Поставить Rack Live на «${device.name}» как сборщик площадки «${name.trim()}»? Rack Live по SSH установит пакеты (python3, ssh, ping, curl), скачает себя с этой панели (${server.trim()}), `
      + `создаст службу racklive на порту ${port} и площадку здесь, на главной панели. Займёт 1–4 минуты.`
      + (local ? ' Адрес главной панели — из домашней сети: сервер сможет достучаться до него, только пока он в этой же сети.' : ''), { title: p.title, ok: 'Установить' }))) return;
    start('install', { name: name.trim(), server: server.trim(), port: +port, level, insecure });
  };
  const remove = async () => {
    if (!(await confirm(`Удалить сборщик с «${device.name}»? Служба и программа будут удалены с сервера, данные останутся в /var/lib/racklive.${dropSite && p.info ? ` Площадка «${p.info.siteName}» и её устройства исчезнут с этой панели.` : ''}`,
      { title: p.title, ok: 'Удалить', danger: true }))) return;
    start('remove', { removeSite: dropSite });
  };
  const info = (job && job.done && job.result && job.result.info) || p.info;
  return <>
    <Checks checks={p.checks || []} />
    {info && p.installed ? <CollectorInfo info={info} site={p.site} title="Сборщик работает" />
      : p.installed ? <div className="plugin-result"><Icon name="check" size={16} /> Rack Live уже стоит на этом сервере{p.version ? ' (' + p.version + ')' : ''} — не через плагин, поэтому данных для входа здесь нет.</div> : null}
    {!p.installed ? <div className="awg-form">
      <Field label="Название площадки" hint="Так она будет называться на этой панели: например «Квартира Ивановых» или «Офис».">
        <input className="input" value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field label="Адрес этой панели" hint={p.serverUrl ? 'Взят из «Настройки → Приложения». Сервер скачает Rack Live и будет присылать данные по этому адресу.' : 'Адрес, по которому сервер достучится до этой панели: домен (https://racklive.example.com) или http://192.168.1.3:9998, если сервер в этой же сети. «Настройки → Приложения» создаст домен.'}>
        <input className="input mono" value={server} placeholder="https://racklive.example.com" onChange={e => setServer(e.target.value)} /></Field>
      <div className="row wrap" style={{ gap: 8 }}>
        <Field label="Порт панели на сервере"><input className="input mono" style={{ maxWidth: 120 }} value={port} onChange={e => setPort(e.target.value.replace(/\D/g, ''))} /></Field>
        <Field label="Управление отсюда"><select className="input" value={level} onChange={e => setLevel(e.target.value)}>
          {COLLECTOR_LEVELS.map(l => <option key={l[0]} value={l[0]}>{l[1]}</option>)}</select></Field></div>
      <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={insecure} onChange={setInsecure} />
        <div className="grow"><div>Не проверять сертификат этой панели</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Только если адрес выше — https с самоподписанным сертификатом. С обычным доменом оставьте выключенным.</div></div></div>
      <Btn kind="primary" icon="download" busy={running} disabled={!ready || running} onClick={install} style={{ padding: 12 }}>{running ? 'Устанавливаю…' : 'Установить сборщик'}</Btn>
      {!ready && !running ? <div className="dim3" style={{ fontSize: 12.5 }}>{!server.trim() ? 'Укажите адрес этой панели.' : 'Кнопка станет активной, когда все пункты выше будут отмечены зелёным.'}</div> : null}
    </div> : null}
    {running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{job.stage}</b>
      <div className="dim3" style={{ fontSize: 12 }}>идёт {Math.max(0, Math.round(now / 1000 - job.t))} с · окно можно закрыть, установка продолжится</div></div></div> : null}
    {job && job.done ? (job.error ? <PluginResult r={{ error: job.error, kept: true, log: [] }} />
      : (job.result && (job.result.log || []).length ? <PluginResult r={{ message: `Журнал (${Math.round(job.dur / 60)} мин)`, log: job.result.log, kept: true, up: true }} /> : null)) : null}
    <div className="row wrap">
      {p.installed ? <Btn kind="danger" icon="trash" disabled={running} onClick={remove}>Удалить сборщик</Btn> : null}
      {p.installed && p.info ? <div className="row" style={{ gap: 8 }}><Switch on={dropSite} onChange={setDropSite} /><span className="dim" style={{ fontSize: 13 }}>вместе с площадкой на этой панели</span></div> : null}
    </div>
  </>;
}

/* AI agents on a server: Claude Code (+ Remote Control, autostart, «new chat»), Codex, Gemini CLI, OpenCode, Aider (rackd/agents.py) */
function AgentsPlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm();
  const cfg = p.config || {};
  const [sel, setSel] = useState(() => new Set(p.agents.some(a => a.installed) ? [] : ['claude']));
  const [rc, setRc] = useState(p.helper ? !!cfg.rc : true);
  const [auto, setAuto] = useState(p.helper ? !!cfg.auto : true);
  const [name, setName] = useState(cfg.name || device.name || 'server');
  const [model, setModel] = useState(cfg.model || '');
  const [auth, setAuth] = useState(cfg.auth === 'key' ? 'key' : 'sub');
  const [apiKey, setApiKey] = useState('');
  const [keys, setKeys] = useState({ codex: '', gemini: '' });
  const [chat, setChat] = useState('');
  const [job, setJob] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [term, setTerm] = useState(null);                   // '&run=agent-setup' | '&run=agent-attach&session=…'
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: 'agents', ...body } });
  const claudeOn = sel.has('claude') || p.agents.find(a => a.id === 'claude').installed;
  const useKey = auth === 'key' && !rc;
  const toggle = id => setSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const payload = () => ({ agents: [...sel], claude: { rc, auto, name, model, auth: useKey ? 'key' : 'sub', apiKey }, keys });
  const start = async op => {
    try { const r = await call(op === 'install' ? { op, ...payload() } : { op }); setJob({ id: r.job, stage: 'Запуск…', done: false, t: Date.now() / 1000 }); }
    catch (e) { toast(e.message, true); }
  };
  useEffect(() => {
    if (!job || job.done) return;
    const t = setInterval(async () => { setNow(Date.now());
      try { const j = await call({ op: 'job', job: job.id }); setJob(x => ({ ...x, ...j }));
        if (j.done) { toast(j.error ? 'Не получилось: ' + j.error : (j.result && j.result.message) || 'Готово', !!j.error); setApiKey(''); setKeys({ codex: '', gemini: '' }); setSel(new Set()); reload(); } } catch (e) { }
    }, 3000);
    return () => clearInterval(t);
  }, [job && job.id, job && job.done]);
  const quick = async (body, ok) => { try { const r = await call(body); toast(r.message || ok); reload(); } catch (e) { toast(e.message, true); } };
  const remove = async a => {
    if (!(await confirm(`Удалить ${a.title} с сервера?${a.id === 'claude' ? ' Вместе с ним уберу команду racklive-agent, автозапуск и сохранённые ключи; вход в аккаунт и история чатов Claude останутся в папке ~/.claude.' : ''}`,
      { title: a.title, ok: 'Удалить', danger: true }))) return;
    try { const r = await call({ op: 'remove', agent: a.id }); setJob({ id: r.job, stage: 'Удаление…', done: false, t: Date.now() / 1000 }); } catch (e) { toast(e.message, true); }
  };
  const running = job && !job.done;
  const loggedIn = /logged in|signed in|authenticated|email|account/i.test(p.claudeAuth || '') && !/not logged|not signed|no auth|not authenticated/i.test(p.claudeAuth || '');
  const needSetup = rc && claudeOn && !loggedIn;
  const noRoot = (p.checks || []).find(c => c.label.startsWith('Вход под root'));
  return <>
    <Checks checks={p.checks || []} />
    <div className="card-title" style={{ marginTop: 6 }}>Что установить</div>
    {p.agents.map(a => <div key={a.id} className="row" style={{ gap: 10, padding: '6px 0', alignItems: 'center' }}>
      <Switch on={a.installed || sel.has(a.id)} disabled={a.installed || running} onChange={() => toggle(a.id)} />
      <div className="grow" style={{ minWidth: 0 }}><b>{a.title}</b> <span className="dim3" style={{ fontSize: 12.5 }}>{a.by}{a.installed ? ` · установлен${a.version ? ' ' + a.version : ''}` : ''}</span></div>
      <a className="btn sm" href={a.home} target="_blank" rel="noreferrer" title="О проекте"><Icon name="link" size={14} /></a>
      {a.installed ? <Btn size="sm" kind="danger" icon="trash" disabled={running} onClick={() => remove(a)} /> : null}
    </div>)}
    {claudeOn ? <div className="awg-form" style={{ marginTop: 8 }}>
      <div className="card-title">Claude Code</div>
      <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={rc} onChange={setRc} />
        <div className="grow"><div>Remote Control — управлять с телефона и из браузера</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Сессия появится в приложении Claude и на claude.ai/code. Работает только при входе по подписке Pro / Max / Team — ключ API для этого не подходит.</div></div></div>
      <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={auto} onChange={setAuto} />
        <div className="grow"><div>Автозапуск после перезагрузки сервера</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>{noRoot && !noRoot.ok ? 'Через cron @reboot.' : 'Службой systemd.'} Новые чаты тоже запоминаются и поднимаются сами.</div></div></div>
      <Field label="Название сессии" hint="Так она будет называться в приложении Claude"><input className="input" value={name} onChange={e => setName(e.target.value)} /></Field>
      <Field label="Модель"><select className="input" value={model} onChange={e => setModel(e.target.value)}>{p.models.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
      <Field label="Как входить" hint={rc ? 'С Remote Control — только подписка (вход один раз кнопкой ниже).' : undefined}>
        <select className="input" value={useKey ? 'key' : 'sub'} disabled={rc} onChange={e => setAuth(e.target.value)}>
          <option value="sub">Подписка claude.ai (вход один раз)</option><option value="key">Ключ API (платишь за токены)</option></select></Field>
      {useKey ? <Field label="Ключ API Anthropic" hint={(cfg.keys || []).includes('ANTHROPIC_API_KEY') ? 'Ключ уже сохранён на сервере. Оставьте пустым, чтобы не менять.' : 'Сохраняется только на сервере в ~/.racklive-agents/env (доступ 600), Rack Live его не хранит.'}>
        <input className="input" type="password" value={apiKey} autoComplete="off" placeholder="sk-ant-…" onChange={e => setApiKey(e.target.value)} /></Field> : null}
    </div> : null}
    {['codex', 'gemini'].filter(id => sel.has(id) || p.agents.find(a => a.id === id).installed).map(id => <Field key={id} label={`Ключ ${id === 'codex' ? 'OpenAI (Codex)' : 'Gemini'} — по желанию`}
      hint={(cfg.keys || []).includes(id === 'codex' ? 'OPENAI_API_KEY' : 'GEMINI_API_KEY') ? 'Ключ уже сохранён на сервере.' : 'Можно войти и внутри программы.'}>
      <input className="input" type="password" value={keys[id]} autoComplete="off" onChange={e => setKeys({ ...keys, [id]: e.target.value })} /></Field>)}
    <div className="row wrap" style={{ marginTop: 8 }}>
      <Btn kind="primary" icon="download" busy={running} disabled={running || (!sel.size && !claudeOn)} onClick={async () => {
        if (sel.size && !(await confirm(`Установить на «${device.name}»: ${[...sel].map(id => p.agents.find(a => a.id === id).title).join(', ')}? Rack Live по SSH поставит программы${claudeOn ? ', настроит автозапуск и команду racklive-agent' : ''}. Займёт несколько минут.`, { title: 'ИИ-агенты', ok: 'Установить' }))) return;
        start('install'); }}>{running ? 'Работаю…' : sel.size ? 'Установить' : 'Сохранить настройки'}</Btn>
      {needSetup ? <Btn icon="terminal" disabled={running} onClick={() => setTerm('&run=agent-setup')}>Войти и запустить</Btn> : null}
      {p.helper && claudeOn ? <Btn icon="refresh" disabled={running} onClick={() => quick({ op: 'restart' }, 'Перезапущено')}>Перезапустить сессии</Btn> : null}
    </div>
    {needSetup ? <div className="err-note" style={{ marginTop: 8 }}><b>Нужен один вход в аккаунт Claude.</b> Нажмите «Войти и запустить»: откроется терминал сервера, он покажет ссылку — откройте её на телефоне, войдите и вставьте код. Потом ответьте <code>y</code> на два вопроса.
      Или вручную в любом SSH (Termius): <code>~/.racklive-agents/racklive-agent setup</code>. Это нужно один раз; дальше сессия сама поднимается после перезагрузки.</div> : null}
    {running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{job.stage}</b>
      <div className="dim3" style={{ fontSize: 12 }}>идёт {Math.max(0, Math.round(now / 1000 - job.t))} с · окно можно закрыть, работа продолжится</div></div></div> : null}
    {job && job.done ? (job.error ? <PluginResult r={{ error: job.error, kept: true, log: [] }} /> : <PluginResult r={{ ...job.result, kept: true, up: true }} />) : null}
    {p.helper ? <>
      <div className="card-title" style={{ marginTop: 12 }}>Чаты</div>
      {(p.sessions || []).length ? p.sessions.map(s => <div key={s.name} className="row" style={{ gap: 8, padding: '4px 0' }}>
        <div className="grow ellipsis"><b>{s.name.replace(/^rl-c-/, '').replace(/^rl-main$/, 'основная сессия')}</b> <span className="dim3" style={{ fontSize: 12 }}>{s.name}</span></div>
        <Btn size="sm" icon="terminal" onClick={() => setTerm('&run=agent-attach&session=' + encodeURIComponent(s.name))}>Открыть</Btn>
        <Btn size="sm" kind="danger" icon="x" onClick={() => quick({ op: 'stop', session: s.name }, 'Остановлено')} /></div>) : <div className="dim3" style={{ fontSize: 13 }}>Сейчас ни одна сессия не запущена.</div>}
      <div className="row" style={{ gap: 8, marginTop: 6 }}><input className="input grow" value={chat} placeholder="Название нового чата" onChange={e => setChat(e.target.value)} />
        <Btn icon="plus" onClick={async () => { await quick({ op: 'new_chat', name: chat.trim() || undefined }, 'Чат запущен'); setChat(''); }}>Новый чат</Btn></div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 4 }}>Новый чат наследует модель и Remote Control{auto ? ' и автозапуск' : ''}. С Remote Control он сразу виден в приложении Claude; «Открыть» показывает его здесь, в терминале.</div>
    </> : null}
    {term ? <Modal title="Терминал сервера" wide onClose={() => { setTerm(null); reload(); }} icon={<Icon name="terminal" size={20} color="var(--accent)" />}>
      <TerminalView extra={`&device=${encodeURIComponent(device.id)}${term}`} onClose={() => { setTerm(null); reload(); }} /></Modal> : null}
  </>;
}

function PluginResult({ r, openPlugin }) {
  const [showLog, setShowLog] = useState(!!r.error);
  return <div className={'plugin-result' + (r.error ? ' bad' : r.up === false ? ' warn' : '')}>
    <div className="row" style={{ alignItems: 'flex-start', gap: 8 }}><Icon name={r.error ? 'x' : r.up === false ? 'alert' : 'check'} size={18} />
      <div className="grow">{r.error ? <><b>Не получилось.</b> {r.error}{r.kept ? '' : '. Всё созданное убрано, роутер в прежнем состоянии.'}</> : r.message}</div></div>
    {!r.error && !r.routing ? <div style={{ marginTop: 8, fontSize: 13 }}>Хотите направлять сайты через этот туннель удобно? <button type="button" className="linkbtn" onClick={() => openPlugin('hydraroute')}>HydraRoute Neo</button></div> : null}
    {(r.log || []).length ? <><button type="button" className="linkbtn" onClick={() => setShowLog(!showLog)}>{showLog ? 'Скрыть' : 'Показать'} журнал ({r.log.length})</button>
      {showLog ? <div className="plugin-log mono">{r.log.map((l, i) => <div key={i} className={l.ok ? '' : 'bad'}>{l.ok ? '✓' : '✗'} {l.cmd}{l.msg ? <span className="dim3"> — {l.msg}</span> : null}</div>)}</div> : null}</> : null}
  </div>;
}

function DomainsEditor({ t, call, onClose, onDone }) {
  const toast = useToast();
  const [text, setText] = useState('');
  const save = async () => {
    try { const r = await call({ op: 'domains', iface: t.iface, name: t.name, domains: text }); toast(r.message); onDone(); } catch (e) { toast(e.message, true); }
  };
  return <Modal title={`Сайты через «${t.name}»`} onClose={onClose} footer={<><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={save}>Сохранить</Btn></>}>
    <div className="dim" style={{ fontSize: 13.5 }}>Новый список заменит текущий ({t.domains} сайтов). Пустой список — выключить маршрутизацию через этот туннель.</div>
    <textarea className="input mono" rows={10} value={text} onChange={e => setText(e.target.value)} placeholder={'youtube.com\ngooglevideo.com'} style={{ fontSize: 12 }} />
  </Modal>;
}
