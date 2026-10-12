/* «Apps on the phone»: Frank and the speed test install as separate home-screen apps.
   Settings card: an https address (made on the Keenetic as a KeenDNS name, or typed by hand), install window with a QR code;
   inside the apps: a banner with the install steps until the app runs from the home screen. */
const APPS = [
  { id: 'frank', path: '/frank', name: 'Frank', icon: '/frank-icon.svg', text: 'Помощник: вопросы о сети простыми словами, разговоры сохраняются' },
  // the speed test measures the home network: it is installed by the LAN address — through the domain the traffic would go via the router's https proxy
  { id: 'speed', path: '/speed', name: 'Тест скорости', icon: '/speed-icon.svg', text: 'Замер Wi-Fi и домашней сети с телефона — в каждой комнате', lan: true },
  { id: 'rack', path: '/', name: 'Rack Live', icon: '/icon.svg', text: 'Вся панель: шкафы, карта, устройства, уведомления' },
];
const IS_IOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isInstalled = () => { try { return matchMedia('(display-mode: standalone)').matches || navigator.standalone === true; } catch (e) { return false; } };

function InstallBanner({ app, name }) {
  const [bip, setBip] = useState(() => window.__bip || null);
  const [hidden, setHidden] = useState(() => isInstalled() || lsGet('rl_inst_' + app, '') === '1');
  useEffect(() => { const h = () => setBip(window.__bip); window.addEventListener('rl-bip', h); return () => window.removeEventListener('rl-bip', h); }, []);
  if (hidden) return null;
  const close = () => { lsSet('rl_inst_' + app, '1'); setHidden(true); };
  const install = async () => { try { bip.prompt(); const r = await bip.userChoice; if (r && r.outcome === 'accepted') setHidden(true); } catch (e) { } };
  return <div className="inst-banner">
    <div className="grow" style={{ minWidth: 0 }}><b>Установите «{name}» как приложение</b>
      <div>{IS_IOS ? <>Нажмите <Icon name="share" size={15} style={{ verticalAlign: '-2px' }} /> «Поделиться» внизу Safari → <b>«На экран „Домой“»</b></>
        : bip ? 'Отдельный значок на экране, открывается без браузера' : <>Меню браузера <b>⋮</b> → <b>«Установить приложение»</b> или «Добавить на главный экран»</>}</div></div>
    {bip && !IS_IOS ? <button type="button" className="inst-go" onClick={install}>Установить</button> : null}
    <button type="button" className="inst-x" title="Скрыть" onClick={close}><Icon name="x" size={16} /></button>
  </div>;
}

function QrCode({ text, size = 200 }) {
  const svg = useMemo(() => {
    if (typeof qrcode !== 'function') return null;
    try {
      if (qrcode.stringToBytesFuncs && qrcode.stringToBytesFuncs['UTF-8']) qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8'];
      const q = qrcode(0, 'M'); q.addData(text); q.make();
      return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    } catch (e) { return null; }
  }, [text]);
  if (!svg) return null;
  return <div className="qr" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: svg }} />;
}

function InstallModal({ app, base, lanBase, onClose }) {
  // the speed test can go either way: the domain works anywhere, the home address measures Wi-Fi exactly (and sees the access point)
  const both = app.lan && lanBase && lanBase !== base;
  const [via, setVia] = useState('domain');
  const url = ((both && via === 'lan') ? lanBase : base).replace(/\/$/, '') + app.path;
  const http = url.startsWith('http://');
  const toast = useToast();
  const copy = () => { try { navigator.clipboard.writeText(url); toast('Ссылка скопирована'); } catch (e) { } };
  return <Modal title={'Установить «' + app.name + '»'} onClose={onClose} icon={<img src={app.icon} width="28" height="28" style={{ borderRadius: 7 }} alt="" />}>
    {both ? <div className="col" style={{ gap: 8 }}>
      <Seg value={via} onChange={setVia} options={[{ value: 'domain', label: 'Через домен' }, { value: 'lan', label: 'Домашний адрес' }]} />
      <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.45 }}>{via === 'domain'
        ? 'Работает везде, в том числе вне дома, по https. Но запросы идут через роутер: точку доступа и сигнал Rack Live не увидит, а очень высокие скорости может упереться в роутер.'
        : 'Самый точный замер Wi-Fi: видно точку доступа, диапазон и сигнал. Работает только дома. Можно поставить оба значка.'}</div>
    </div> : null}
    <div className="inst-modal">
      <QrCode text={url} />
      <div className="col" style={{ gap: 10, minWidth: 0 }}>
        <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.45 }}>Наведите камеру телефона на код — откроется {app.name}. Или откройте ссылку на самом телефоне:</div>
        <div className="row" style={{ gap: 6 }}><a className="mono ellipsis inst-url" href={url} target="_blank" rel="noreferrer">{url}</a><Btn size="sm" icon="copy" onClick={copy} title="Скопировать" /></div>
        <a className="btn primary" href={url} target="_blank" rel="noreferrer"><Icon name="download" size={16} />Открыть и установить</a>
      </div>
    </div>
    <div className="inst-steps">
      <div><b>iPhone / iPad</b> — в <b>Safari</b>: <Icon name="share" size={14} style={{ verticalAlign: '-2px' }} /> «Поделиться» → «На экран „Домой“» → «Добавить».</div>
      <div><b>Android</b> — в Chrome появится «Установить», или меню <b>⋮</b> → «Установить приложение».</div>
      <div><b>Компьютер</b> — Chrome / Edge: значок установки в адресной строке.</div>
    </div>
    <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.45 }}>
      {app.id !== 'rack' ? 'Приложение открывается сразу на весь экран, без вкладок Rack Live. ' : ''}На новом адресе нужно один раз войти тем же паролем.
      {http && !app.lan ? ' Адрес без https: на iPhone установка работает, но на Android не будет кнопки «Установить», а голосовой ввод в Frank не включится. Лучше сделать доменное имя (в карточке «Приложения на телефон»).' : ''}</div>
  </Modal>;
}

function AppsCard() {
  const { data, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [st, setSt] = useState(null);                         // {apps, router}
  const [pub, setPub] = useState(false);
  const [name, setName] = useState('racklive');
  const [manual, setManual] = useState('');
  const [inst, setInst] = useState(() => APPS.find(a => a.id === new URLSearchParams(location.search).get('install')) || null);    // ?install=frank
  const [busy, setBusy] = useState(false);
  const load = async () => { try { const r = await api('/api/apps', { method: 'POST', body: { op: 'status' } }); setSt(r); if (r.router && r.router.public != null) setPub(!!r.router.public); } catch (e) { setSt({ apps: data.apps || {}, error: e.message }); } };
  useEffect(() => { load(); }, []);
  const call = async (body, ok) => {
    setBusy(true);
    try { const r = await api('/api/apps', { method: 'POST', body }); setSt(r); if (r.ok === false) toast(r.error, true); else { if (ok) toast(ok); refresh(); } }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const create = async () => {
    if (pub && !(await confirm('Rack Live станет доступен из интернета по этому адресу (вход — по паролю администратора или через Telegram). Включить?',
      { title: 'Доступ из интернета', ok: 'Включить' }))) return;
    call({ op: 'create', public: pub, name }, 'Готово: адрес создан на роутере');
  };
  const apps = (st && st.apps) || data.apps || {};
  const r = st && st.router;
  const base = apps.url || location.origin;
  const lanBase = location.protocol === 'http:' ? location.origin : r && r.target ? 'http://' + r.target : base;
  return <Card title={<span className="row" style={{ gap: 8 }}><Icon name="phone" size={15} />Приложения на телефон</span>} style={{ gridColumn: '1 / -1' }}>
    <div className="notify-grid">
      <div className="col" style={{ gap: 12 }}>
        <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>Frank и тест скорости ставятся на экран телефона отдельными значками — как обычные приложения.
          Лучше ставить по адресу с <b>https</b>: тогда на Android работает установка, а в Frank — голосовой ввод.</div>
        <div className="apps-addr">
          <div className="dim3" style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.4px' }}>Адрес для установки</div>
          {apps.url ? <div className="row wrap" style={{ gap: 8 }}><a className="mono" href={apps.url} target="_blank" rel="noreferrer" style={{ fontSize: 14, fontWeight: 600 }}>{apps.url}</a>
            {apps.public != null ? <span className={'badge ' + (apps.public ? 'warning' : 'online')}>{apps.public ? 'из интернета' : 'только из дома'}</span> : null}</div>
            : <div style={{ fontSize: 14 }}><span className="mono">{location.origin}</span> <span className="dim3" style={{ fontSize: 12.5 }}>— текущий, без https</span></div>}
        </div>
        {st == null ? <div className="dim row" style={{ gap: 8, fontSize: 13 }}><span className="spin-dot" />Смотрю роутер…</div>
          : r && r.ndns ? <div className="apps-router">
            <div className="row" style={{ gap: 10 }}><KindIcon kind="router" size={34} />
              <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>{r.name}</b><div className="dim" style={{ fontSize: 12.5 }}>KeenDNS: {r.keendns}{r.access === 'cloud' ? ' (через облако)' : ''}</div></div></div>
            {r.proxy && !apps.url ? <div style={{ fontSize: 13.5, lineHeight: 1.45 }}>На роутере уже есть имя для Rack Live: <b className="mono">{r.url}</b> ({r.public ? 'доступ из интернета' : 'только из дома'}).</div>
              : !r.proxy ? <div style={{ fontSize: 13.5, lineHeight: 1.45 }}>Rack Live сам создаст на роутере имя вида <b className="mono">{(name || 'racklive')}.{r.keendns}</b> с https-сертификатом роутера.</div> : null}
            {!r.proxy ? <Field label="Имя (латиница и цифры)"><input className="input mono" value={name} onChange={e => setName(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, ''))} /></Field> : null}
            <div className="row"><Switch on={pub} onChange={setPub} /><div className="grow"><div style={{ fontSize: 14 }}>Доступ из интернета</div>
              <div className="dim3" style={{ fontSize: 12.5 }}>{pub ? 'Приложения работают и вне дома (мобильный интернет). Вход — по паролю.' : 'Только из домашней сети — безопаснее. Вне дома не откроется.'}</div></div></div>
            <div className="row wrap">
              <Btn kind="primary" busy={busy} onClick={create}>{r.proxy ? (apps.url === r.url ? 'Сохранить доступ' : 'Использовать этот адрес') : 'Создать доменное имя'}</Btn>
              {apps.url && apps.created ? <Btn busy={busy} onClick={async () => { if (await confirm('Удалить доменное имя на роутере? Установленные по нему приложения перестанут открываться.', { danger: true, ok: 'Удалить' })) call({ op: 'remove' }, 'Удалено'); }}>Удалить с роутера</Btn> : null}
            </div>
            {r.target ? <div className="dim3" style={{ fontSize: 11.5 }}>Роутер будет отправлять запросы на {r.target}</div> : null}
          </div>
          : r && !r.ndns ? <div className="apps-router" style={{ fontSize: 13.5, lineHeight: 1.45 }}><b>{r.name}</b>: {r.error || 'на роутере ещё нет доменного имени KeenDNS.'}
              {!r.error ? <> Откройте веб-интерфейс роутера → <b>«Доменное имя»</b>, получите бесплатное имя и вернитесь сюда.</> : null}
              <div><Btn size="sm" icon="refresh" onClick={load} style={{ marginTop: 8 }}>Проверить снова</Btn></div></div>
          : st.error ? <div style={{ color: 'var(--red)', fontSize: 13 }}>{st.error}</div> : null}
        <details className="guide"><summary>Свой адрес (другой роутер или обратный прокси)</summary>
          <div className="col" style={{ gap: 8, marginTop: 8 }}>
            <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.45 }}>Если у вас не Keenetic: настройте обратный прокси с https (Synology, nginx, Caddy, Cloudflare Tunnel) на этот Rack Live и впишите адрес.</div>
            <div className="row"><input className="input mono grow" value={manual} placeholder="https://rack.ваш-домен" onChange={e => setManual(e.target.value)} />
              <Btn onClick={() => call({ op: 'set', url: manual }, manual ? 'Адрес сохранён' : 'Адрес убран')}>Сохранить</Btn></div>
          </div></details>
      </div>
      <div className="col" style={{ gap: 8 }}>
        <div className="card-title" style={{ marginBottom: 2 }}>Установить</div>
        {APPS.map(a => <div key={a.id} className="li app-row">
          <img src={a.icon} width="44" height="44" alt="" style={{ borderRadius: 11, flexShrink: 0 }} />
          <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14.5 }}>{a.name}</b><div className="dim" style={{ fontSize: 12.5, lineHeight: 1.35 }}>{a.text}</div></div>
          <Btn size="sm" kind={a.id === 'rack' ? '' : 'primary'} onClick={() => setInst(a)}>Установить</Btn>
        </div>)}
      </div>
    </div>
    {/* a portal: the card's backdrop-filter would otherwise trap the fixed overlay inside the card */}
    {inst ? ReactDOM.createPortal(<InstallModal app={inst} base={base} lanBase={lanBase} onClose={() => setInst(null)} />, document.body) : null}
  </Card>;
}
