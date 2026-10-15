/* App shell */
const TABS = [
  { id: 'rack', label: 'Главная', icon: 'home' },          // widgets (92_dashboard.jsx); the id stays for old #rack links
  { id: 'map', label: 'Карта', icon: 'map' },              // inside: «Карта сети» / «План» switch (#plan opens the plan)
  { id: 'devices', label: 'Устройства', icon: 'list' },
  { id: 'events', label: 'События', icon: 'bell' },
  { id: 'settings', label: 'Настройки', icon: 'settings', admin: true },
];
/* one hint per tab (and a different one while editing) — shown above the page until dismissed */
const TAB_HINTS = {
  rack: ['Главная собрана из виджетов: шкаф, состояние сети, интернет, доступность… Нажмите на устройство — откроется карточка. ' +
    'Чтобы переставить, растянуть или добавить виджеты (карту, план, Frank, заметку…), включите «Редактирование» вверху (на телефоне — в меню «⋯»).',
    'Включите «Расстановка виджетов» (тумблер рядом с «Редактирование», на телефоне — в меню «⋯»), чтобы двигать виджеты, менять их размер (кнопка в углу виджета), добавлять и убирать. ' +
    'Пока расстановка выключена, редактируется содержимое: в шкафу двигается оборудование, «+ Место» добавит стойку, щиток или комнату.'],
  map: ['Карта строится сама по данным роутера и коммутатора: кто к какому порту подключён. Цвет линии — скорость: зелёный — 1 Гбит, ' +
    'жёлтый — 100 Мбит. Кнопка «Анализ» покажет слабые места сети: точки отказа, медленные кабели, ошибки.',
    'Перетаскивайте узлы, чтобы разложить карту по-своему — положение запоминается. Связь, которую Rack Live не видит сам ' +
    '(например, через неуправляемый коммутатор), можно добавить вручную.'],
  plan: ['План показывает, где физически стоит оборудование. Цветные пятна — замеры скорости Wi-Fi: пройдитесь с телефоном по дому, ' +
    'нажмите кнопку-спидометр вверху, сделайте тест и отметьте место — получится карта покрытия.',
    'Сначала нарисуйте комнаты инструментом «Комната», потом «Оборудование» → выберите устройство и нажмите на план. ' +
    'Дома и столбы на территории соединяются инструментом «Магистраль».'],
  devices: ['Устройства — то, с чего Rack Live собирает данные. «Добавить» → выберите тип (роутер, коммутатор, NAS, сервер по SSH…), ' +
    'введите адрес и пароль и нажмите «Проверить» — сразу будет видно, подключается ли.'],
  events: ['Журнал: сбои, восстановления, входы и действия. Чтобы узнавать о сбоях сразу, подключите Telegram-бота в «Настройках» → «Уведомления».'],
  settings: ['Начните с уведомлений: подключите Telegram-бота, и Rack Live сам напишет, если что-то сломается. ' +
    'Подсказки вроде этой выключаются переключателем «Подсказки» в разделе «Основные».'],
};
const APP_MODE = window.RL_APP || (window.RL_FRANK ? 'frank' : '');     // /frank, /speed: separate installable apps
const FRANK = APP_MODE === 'frank', SPEED_APP = APP_MODE === 'speed';
const lsGet = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { } };

function useTheme() {
  const [pref, setPref] = useState(lsGet('rl_theme', (TG && TG.scheme) || 'auto'));     // inside Telegram: follow its theme
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const t = pref === 'auto' ? (mq.matches ? 'dark' : 'light') : pref;
      document.documentElement.setAttribute('data-theme', t);
      document.querySelectorAll('meta[name=theme-color]').forEach(m => {
        if (pref === 'auto') { m.setAttribute('media', m === document.querySelectorAll('meta[name=theme-color]')[0] ? '(prefers-color-scheme: light)' : '(prefers-color-scheme: dark)');
          m.setAttribute('content', m.getAttribute('media').includes('light') ? '#f2f2f7' : '#000000'); }
        else { m.removeAttribute('media'); m.setAttribute('content', t === 'dark' ? '#000000' : '#f2f2f7'); }
      });
    };
    apply(); mq.addEventListener('change', apply); return () => mq.removeEventListener('change', apply);
  }, [pref]);
  return [pref, p => { setPref(p); lsSet('rl_theme', p); }];
}

function App() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTabRaw] = useState(() => { const t = location.hash.slice(1) || lsGet('rl_tab', 'rack'); return t === 'plan' ? 'map' : t; });
  const [mapView, setMapView] = useState(() => location.hash === '#plan' ? 'plan' : 'map');     // «Карта» opens on the network map
  const setTab = t => { if (t === 'plan' || t === 'map') { setMapView(t); setTabRaw('map'); } else setTabRaw(t); };
  const [mode, setMode] = useState(() => new URLSearchParams(location.search).get('mode') === 'edit' ? 'edit' : 'view');
  const [sheet, setSheet] = useState(null);
  const [arrange, setArrange] = useState(() => new URLSearchParams(location.search).get('arrange') === '1');     // «Расстановка виджетов» on the home page (switch beside «Редактирование»)
  const [editor, setEditor] = useState(() => new URLSearchParams(location.search).get('add') === '1' ? null : undefined);    // ?add=1 → «Новое устройство»
  const [login, setLogin] = useState(false);
  const [speed, setSpeed] = useState(() => new URLSearchParams(location.search).get('speedtest'));      // '1' open · 'run' open and start
  const [pinTest, setPinTest] = useState(null);             // speed test id waiting for a tap on the plan
  const [menu, setMenu] = useState(() => new URLSearchParams(location.search).get('hmenu') === '1');   // phone header menu «⋯»
  const [ai, setAi] = useState(() => new URLSearchParams(location.search).get('ai') ? { n: 0 } : null);     // assistant panel: {q, n}
  const [tour, setTour] = useState(() => new URLSearchParams(location.search).get('tour') === '1' || tourResume());      // Frank's welcome tour (95_tour.jsx); ?tour=1 starts it; a tour that was in progress when the page blinked continues
  const [theme, setTheme] = useTheme();
  const toast = useToast();
  // opened from the Telegram bot: log in with the signed launch data, no password
  const [tg, setTg] = useState(TG ? 'pending' : null);       // 'pending' | 'ok' | error text
  useEffect(() => {
    if (!TG || !data || data.authed || data.setupNeeded || tg !== 'pending') return;
    api('/api/tglogin', { method: 'POST', body: { initData: TG.initData } })
      .then(r => { ssSet('rl_tok', r.token); setTg('ok'); refresh(); })
      .catch(e => { setTg(e.message); toast('Вход через Telegram: ' + e.message, true); });
  }, [data && data.authed, data && data.setupNeeded]);

  const refresh = useCallback(async () => {
    try { const d = await api('/api/state'); setData(d); setErr(null); if (d.authed) diagFlush(); }
    catch (e) { setErr(e.message); diag('связь: ' + String(e.message).slice(0, 60)); }
  }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 15000); return () => clearInterval(t); }, [refresh]);
  // the very first visit of the administrator: the server says tourDone=false (an installation that already has an administrator never gets it)
  useEffect(() => { if (!APP_MODE && data && data.authed && data.settings && data.settings.tourDone === false) setTour(true); }, [data && data.authed, data && data.settings && data.settings.tourDone]);
  useEffect(() => {                                       // ?editdev=<id> opens that device's settings form (needs admin)
    const id = new URLSearchParams(location.search).get('editdev'); const d = id && data && data.devices.find(x => x.id === id);
    if (d) setEditor(d);
  }, [!!data]);
  const scrollerRef = useRef(null);
  // the tab goes into the address (#devices): on iPhone / iPad (also the home-screen app) the address is rewritten in place — assigning location.hash there made the app
  // load the page anew on every tab press (the journal showed «pagehide → загружена (navigate)» each time)
  useEffect(() => {
    if (APP_MODE) return; const h = tab === 'map' && mapView === 'plan' ? 'plan' : tab;
    if (/iPhone|iPad|iPod/.test(navigator.userAgent) || navigator.standalone) { try { history.replaceState(null, '', '#' + h); } catch (e) { location.hash = h; } } else location.hash = h;
    lsSet('rl_tab', tab); window.scrollTo(0, 0);
  }, [tab, mapView]);
  // «События»: the badge counts new alarming events since the tab was last opened (not the devices that are down right now)
  const [evSeen, setEvSeen] = useState(() => +lsGet('rl_ev_seen', 0));
  useEffect(() => { if (!data || evSeen) return; setEvSeen(data.now); lsSet('rl_ev_seen', String(data.now)); }, [data]);
  useEffect(() => { if (tab === 'events' && data) { setEvSeen(data.now); lsSet('rl_ev_seen', String(data.now)); } }, [tab, data]);
  // deep link: ?device=<id>&tab=ports&port=9 opens the device sheet
  const deep = useRef(new URLSearchParams(location.search));
  useEffect(() => {
    const p = deep.current; if (!data || !data.devices || !p.get('device')) return;
    const d = data.devices.find(x => x.id === p.get('device') || x.name === p.get('device'));
    if (d) setSheet({ id: d.id, tab: p.get('tab'), port: p.get('port') ? +p.get('port') : null });
    deep.current = new URLSearchParams();
  }, [data]);
  useEffect(() => { if (!APP_MODE && data && data.settings && data.settings.title) document.title = data.settings.title + ' · Rack Live'; }, [data && data.settings && data.settings.title]);

  if (!data) return <div className="auth"><div className="app-bg" />{err ? <div className="card pad">Сервер недоступен: {err}<br /><Btn style={{ marginTop: 12 }} onClick={refresh}>Повторить</Btn></div>
    : <div className="dim">Загрузка…</div>}</div>;
  if (data.setupNeeded) return <AuthScreen setup title={data.settings && data.settings.title} onDone={refresh} />;
  if (tg === 'pending' && !data.authed) return <div className="auth"><div className="app-bg" /><div className="dim">Вход через Telegram…</div></div>;
  if ((data.needLogin && !data.devices) || login || (FRANK && !data.authed)) return <AuthScreen title={FRANK ? 'Frank' : SPEED_APP ? 'Тест скорости' : data.settings && data.settings.title} note={TG && tg !== 'ok' ? 'Вход через Telegram не удался: ' + tg : ''} tgLogin={data.tgLogin} codeLogin={data.loginCodes}
    onDone={() => { setLogin(false); refresh(); }} />;

  const admin = !!data.authed;
  const edit = admin && mode === 'edit';
  const saveRacks = async racks => {
    setData(d => ({ ...d, racks }));
    try { await api('/api/racks', { method: 'PUT', body: { racks } }); } catch (e) { toast(e.message, true); refresh(); }
  };
  const saveRack = rack => saveRacks(data.racks.map(r => r.id === rack.id ? rack : r));
  const saveMap = async part => {
    setData(d => ({ ...d, map: { ...d.map, ...part } }));
    try { await api('/api/map', { method: 'PUT', body: part }); refresh(); } catch (e) { toast(e.message, true); }
  };
  const savePlan = async plan => {                         // plan = { buildings, links }
    setData(d => ({ ...d, plan }));
    try { await api('/api/plan', { method: 'PUT', body: plan }); } catch (e) { toast(e.message, true); refresh(); }
  };
  const logout = async () => { await api('/api/logout', { method: 'POST' }); ssSet('rl_tok', null); setMode('view'); refresh(); };
  const finishTour = async () => {                          // done or skipped: it is not shown again by itself
    setTour(false);
    if (data.settings.tourDone !== true) { try { await api('/api/tour', { method: 'POST', body: {} }); } catch (e) { } refresh(); }
  };
  const applyState = (id, state) => setData(d => ({ ...d, devices: d.devices.map(x => x.id === id ? { ...x, state } : x) }));
  const ctx = { data, admin, edit, arrange, setArrange, theme, setTheme, refresh, saveRack, saveRacks, saveMap, savePlan, logout, applyState, setTab,
    pinTest, setPinTest, pinSpeedTest: id => { setPinTest(id); setMode('view'); setTab('plan'); }, openSpeed: () => setSpeed(true),
    openDevice: (d, t, port) => d && setSheet({ id: d.id, tab: t, port }), openEditor: d => setEditor(d),
    newDevice: preset => setEditor({ __preset: preset }),             // «Новое устройство» with the type and fields already filled in
    startTour: () => { lsSet('rl_tour_step', ''); setMode('view'); setTour(true); },       // «Показать обучение» always starts from the beginning
    askAi: q => setAi({ q, n: Date.now() }) };
  if (FRANK) return <AppCtx.Provider value={ctx}><div className="app-bg" /><AiPanel standalone /></AppCtx.Provider>;
  if (SPEED_APP) return <AppCtx.Provider value={ctx}><div className="app-bg" /><SpeedApp /></AppCtx.Provider>;
  const sheetDev = sheet && data.devices.find(d => d.id === sheet.id);
  const newest = Math.max(0, ...data.devices.map(d => (d.state && d.state.updated) || 0));
  const stale = data.devices.length && (data.now - newest > Math.max(180, (data.settings.poll || 60) * 3));
  const problems = (data.events || []).filter(e => e.t > evSeen && ['offline', 'warning'].includes(e.level)).length;
  const badge = problems > 99 ? '99+' : problems;
  const tabs = TABS.filter(t => !t.admin || admin);
  const cur = tabs.find(t => t.id === tab) ? tab : 'rack';
  const view = cur === 'map' && mapView === 'plan' ? 'plan' : cur;          // what is shown: subtitle and hint follow it
  const subtitle = {
    rack: `${data.devices.filter(d => (d.state || {}).status === 'online').length} из ${data.devices.length} устройств в сети${data.racks.length > 1 ? ' · мест: ' + data.racks.length : ''}`,
    map: 'Как всё соединено: шкаф, кабели, точки доступа и клиенты',
    plan: 'План помещений: дома, этажи, двор — где физически стоит оборудование',
    devices: 'Всё, что собирает данные: локальные и удалённые устройства',
    events: 'Сбои, восстановления и действия администратора',
    settings: 'Уведомления, Frank, приложения на телефон, доступ и резервные копии',
  }[view];

  return <AppCtx.Provider value={ctx}>
    <div className="app-bg" />
    <header className="topbar">
      <div className="brand"><AppIcon size={34} radius={10} style={{ boxShadow: '0 4px 14px rgba(0,60,200,.25)' }} />
        <div className="brand-text"><div className="brand-title ellipsis">{data.settings.title}</div>
          <div className={'live' + (stale ? ' stale' : '')}><i />{stale ? 'нет свежих данных' : 'live · ' + fmt.ago(newest, data.now)}</div></div></div>
      <nav className="tabs">{tabs.map(t => <button key={t.id} data-tour={'tab-' + t.id} className={'tab' + (cur === t.id ? ' on' : '')} title={t.label} onClick={() => setTab(t.id)}>
        <Icon name={t.icon} size={15} /><span className="tab-label">{t.label}</span>{t.id === 'events' && problems ? <span className="count">{badge}</span> : null}</button>)}</nav>
      <div className="grow" />
      <div className="hdr-tools hide-sm">
        {admin ? <span data-tour="edit-toggle" style={{ display: 'inline-flex' }}><Seg className="edit" value={mode} onChange={setMode} options={[{ value: 'view', label: 'Просмотр', icon: 'eye' },
          { value: 'edit', label: 'Редактирование', icon: 'edit', cls: 'editing' }]} /></span> : <Btn size="sm" icon="lock" onClick={() => setLogin(true)}>Войти</Btn>}
        {admin && edit && cur === 'rack' ? <label className="arrange-sw" title="Двигать, менять размер, добавлять и убирать виджеты на главной"><Switch on={arrange} onChange={setArrange} /><span>Расстановка виджетов</span></label> : null}
        {admin ? <button type="button" data-tour="frank-btn" className="btn sm icon frank-btn" title="Frank — помощник: вопросы о сети" onClick={() => setAi({ n: Date.now() })}><FrankEye size={26} round={8} /></button> : null}
        <Btn size="sm" icon="gauge" title="Тест скорости Wi-Fi и сети" onClick={() => setSpeed(true)} />
        <Btn size="sm" icon={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'eye'} title={'Тема: ' + ({ auto: 'как в системе', dark: 'тёмная', light: 'светлая' })[theme]}
          onClick={() => setTheme(theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto')} />
      </div>
      {/* phones: everything above folds into one «⋯» button with a menu, like iOS */}
      <button type="button" data-tour="hdr-more" className={'hdr-more only-sm' + (edit ? ' editing' : '')} title="Меню" onClick={() => setMenu(true)}><Icon name="more" size={22} stroke={2.6} /></button>
    </header>
    {menu ? <HeaderMenu admin={admin} mode={mode} arrange={admin && edit && cur === 'rack' ? arrange : null} setArrange={setArrange} setMode={setMode} theme={theme} setTheme={setTheme} onClose={() => setMenu(false)}
      onFrank={() => setAi({ n: Date.now() })} onSpeed={() => setSpeed(true)} onRefresh={refresh} onLogin={() => setLogin(true)} onLogout={logout} /> : null}
    <main className="page">
      <div className="row" style={{ alignItems: 'flex-end', marginBottom: 14 }}>
        <div className="grow"><div className="page-title">{tabs.find(t => t.id === cur).label}</div><div className="page-sub" style={{ marginBottom: 0 }}>{subtitle}</div></div>
        {edit ? <span className="badge warning"><Icon name="edit" size={12} />Режим редактирования</span> : null}
      </div>
      {cur === 'map' ? <div className="view-switch"><Seg value={mapView} onChange={setMapView}
        options={[{ value: 'map', label: 'Карта сети', icon: 'map' }, { value: 'plan', label: 'План', icon: 'plan' }]} /></div> : null}
      {TAB_HINTS[view] ? (edit && TAB_HINTS[view][1] ? <Hint key={view + '-edit'} id={view + '-edit'}>{TAB_HINTS[view][1]}</Hint>
        : <Hint key={view} id={view}>{TAB_HINTS[view][0]}</Hint>) : null}
      {cur === 'rack' ? <Dashboard /> : null}
      {view === 'map' ? <MapView /> : null}
      {view === 'plan' ? <PlanView /> : null}
      {cur === 'devices' ? <DevicesView /> : null}
      {cur === 'events' ? <EventsView /> : null}
      {cur === 'settings' && admin ? <SettingsView /> : null}
    </main>
    <nav className="bottombar">{tabs.map(t => <button key={t.id} data-tour={'tab-' + t.id} className={cur === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
      <Icon name={t.icon} size={24} />{t.label}{t.id === 'events' && problems ? <span className="count">{badge}</span> : null}</button>)}</nav>
    {sheetDev ? <DeviceSheet key={sheetDev.id} device={sheetDev} initialTab={sheet.tab} initialPort={sheet.port} onClose={() => setSheet(null)} /> : null}
    {editor !== undefined ? <DeviceEditor device={editor && editor.__preset ? null : editor} preset={editor && editor.__preset} onClose={() => setEditor(undefined)} /> : null}
    {ai && admin ? <AiPanel key={ai.n} initial={ai.q} onClose={() => setAi(null)} /> : null}
    {speed ? <SpeedTestModal autoRun={speed === 'run'} onClose={() => setSpeed(null)} /> : null}
    {tour && admin ? <Tour onDone={finishTour} /> : null}
  </AppCtx.Provider>;
}

/* phone header menu: tiles on top (Frank, speed test, refresh), rows below (editing, theme, sign in / out) — like an iOS context menu */
function HeaderMenu({ admin, mode, arrange, setArrange, setMode, theme, setTheme, onClose, onFrank, onSpeed, onRefresh, onLogin, onLogout }) {
  useEffect(() => { const h = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);
  const go = fn => () => { onClose(); fn(); };
  return <div className="hdr-menu-wrap" onClick={e => e.target === e.currentTarget && onClose()}>
    <div className="hdr-menu">
      <div className="hdr-tiles">
        {admin ? <button type="button" onClick={go(onFrank)}><FrankEye size={30} round={9} /><span>Frank</span></button> : null}
        <button type="button" onClick={go(onSpeed)}><Icon name="gauge" size={24} /><span>Тест скорости</span></button>
        <button type="button" onClick={go(onRefresh)}><Icon name="refresh" size={24} /><span>Обновить</span></button>
      </div>
      {admin ? <div className="hdr-row">
        <Icon name="edit" size={20} /><span className="grow">Редактирование</span><Switch on={mode === 'edit'} onChange={v => setMode(v ? 'edit' : 'view')} /></div> : null}
      {arrange != null ? <div className="hdr-row"><Icon name="list" size={20} /><span className="grow">Расстановка виджетов</span><Switch on={arrange} onChange={setArrange} /></div> : null}
      <div className="hdr-row"><Icon name={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'eye'} size={20} /><span className="grow">Тема</span>
        <Seg value={theme} onChange={setTheme} options={[{ value: 'auto', label: 'Авто' }, { value: 'dark', label: 'Тёмная' }, { value: 'light', label: 'Светлая' }]} /></div>
      {admin ? <button type="button" className="hdr-row" onClick={go(onLogout)}><Icon name="logout" size={20} /><span className="grow">Выйти</span></button>
        : <button type="button" className="hdr-row" onClick={go(onLogin)}><Icon name="lock" size={20} /><span className="grow">Войти</span></button>}
    </div>
  </div>;
}

/* a render error shows a readable message instead of a blank page (and marks <html data-js-error> for the smoke test) */
const markError = msg => { document.documentElement.dataset.jsError = String(msg || 'error').slice(0, 300); };
window.addEventListener('error', e => { markError(e.message); diag('ошибка JS: ' + (e.message || '').slice(0, 90)); });
window.addEventListener('unhandledrejection', e => { if (e.reason && !e.reason.status) { markError(e.reason.message || e.reason); diag('ошибка JS: ' + String(e.reason.message || e.reason).slice(0, 90)); } });
try {                                                      // how the page came to be here: reload / opened / back-forward; and whether it is the home-screen app
  const nav = performance.getEntriesByType('navigation')[0];
  diag(`загружена (${nav ? nav.type : '?'}) ${innerWidth}×${innerHeight}${navigator.standalone ? ' приложение' : ''} ${location.pathname}${location.hash}`);
  window.addEventListener('hashchange', () => diag('hashchange ' + location.hash));
  window.addEventListener('pagehide', e => diag('pagehide' + (e.persisted ? ' (в кэше)' : '')));
  window.addEventListener('pageshow', e => { if (e.persisted) diag('pageshow из кэша'); });
  document.addEventListener('visibilitychange', () => diag(document.visibilityState === 'hidden' ? 'свёрнута' : 'снова видна'));
} catch (e) { }
class Crash extends React.Component {
  constructor(p) { super(p); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err) { markError(err && err.message); }
  render() {
    if (!this.state.err) return this.props.children;
    return <div className="auth"><div className="card pad" id="rl-crash" style={{ maxWidth: 460 }}>
      <b style={{ fontSize: 17 }}>Что-то пошло не так в интерфейсе</b>
      <div className="dim mono" style={{ fontSize: 12, margin: '8px 0 14px', wordBreak: 'break-word' }}>{String(this.state.err && this.state.err.message || this.state.err)}</div>
      <button className="btn primary" onClick={() => location.reload()}>Обновить страницу</button></div></div>;
  }
}
ReactDOM.createRoot(document.getElementById('root')).render(<Crash><ToastHost><ConfirmHost><App /></ConfirmHost></ToastHost></Crash>);
