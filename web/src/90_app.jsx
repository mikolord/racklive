/* App shell */
const TABS = [
  { id: 'rack', label: 'Главная', icon: 'home' },          // widgets (92_dashboard.jsx); the id stays for old #rack links
  { id: 'map', label: 'Карта', icon: 'map' },
  { id: 'plan', label: 'План', icon: 'plan' },
  { id: 'tools', label: 'Инструменты', icon: 'wrench', admin: true },      // «Устройства» · «Плагины» · «Инструменты» (65_tools.jsx); the old #devices address opens «Устройства» there
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
  events: ['Журнал: сбои, восстановления, входы и действия. Чтобы узнавать о сбоях сразу, подключите Telegram-бота в «Настройках» → «Уведомления».'],
  settings: ['Начните с уведомлений: подключите Telegram-бота, и Rack Live сам напишет, если что-то сломается. ' +
    'Подсказки вроде этой выключаются переключателем «Подсказки» в разделе «Основные».'],
};
const APP_MODE = window.RL_APP || (window.RL_FRANK ? 'frank' : '');     // /frank, /speed: separate installable apps
const FRANK = APP_MODE === 'frank', SPEED_APP = APP_MODE === 'speed', TERM_APP = APP_MODE === 'terminal', CARDS_APP = APP_MODE === 'cards', PLAN_APP = APP_MODE === 'plan';
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
        if (FRANK) {                                      // /frank paints the whole screen with --bg of the current look: the status bar must be exactly that, not a fixed black
          const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
          if (bg) { m.removeAttribute('media'); m.setAttribute('content', bg); }
        }
      });
    };
    apply(); mq.addEventListener('change', apply); return () => mq.removeEventListener('change', apply);
  }, [pref]);
  return [pref, p => { setPref(p); lsSet('rl_theme', p); }];
}

function App() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTabRaw] = useState(() => { const t = PLAN_APP ? 'plan' : location.hash.slice(1) || lsGet('rl_tab', 'rack'); return t === 'devices' ? 'tools' : t; });
  // The press is answered at once (the dock moves its lens, the icon plays), while the heavy page is drawn in a transition: before, the main
  // thread was busy building the dashboard and the animation of the press stuttered. tabNow = the tab pressed, whose page is not on the screen yet.
  const [tabNow, setTabNow] = useState(null);
  const setTab = t => {
    if (PLAN_APP && t!=='plan') { location.assign('/#'+encodeURIComponent(t==='devices'?'tools':t)); return; }
    const n = t === 'devices' ? 'tools' : t;
    setTabNow(n); React.startTransition(() => setTabRaw(n));
  };
  useEffect(() => { if (tabNow != null && tabNow === tab) setTabNow(null); }, [tab, tabNow]);
  const [mode, setMode] = useState(() => new URLSearchParams(location.search).get('mode') === 'edit' ? 'edit' : 'view');
  const [sheet, setSheet] = useState(null);
  const [place, setPlace] = useState(null);           // a rack / panel opened from the plan: a window of its own, not a jump to the main screen
  const [arrange, setArrange] = useState(() => new URLSearchParams(location.search).get('arrange') === '1');     // «Расстановка виджетов» on the home page (switch beside «Редактирование»)
  const [editor, setEditor] = useState(() => new URLSearchParams(location.search).get('add') === '1' ? null : undefined);    // ?add=1 → «Новое устройство»
  const [login, setLogin] = useState(false);
  const [speed, setSpeed] = useState(() => new URLSearchParams(location.search).get('speedtest'));      // '1' open · 'run' open and start
  const [pinTest, setPinTest] = useState(null);             // speed test id waiting for a tap on the plan
  const [menu, setMenu] = useState(() => new URLSearchParams(location.search).get('hmenu') === '1');   // phone header menu «⋯»
  const [nav, setNav] = useState(() => new URLSearchParams(location.search).get('nav') === '1');        // «Test»: the side menu
  const [navKey, setNavKey] = useState(0); const tourNav = useRef(false);      // the welcome tour can hold the menu open between its steps
  useEffect(() => { const h = e => { tourNav.current = !!e.detail; if (e.detail) { setNav(true); setNavKey(k => k + 1); } else setNav(false); };
    window.addEventListener('rl-tour-nav', h); return () => window.removeEventListener('rl-tour-nav', h); }, []);
  const [ai, setAi] = useState(() => new URLSearchParams(location.search).get('ai') ? { n: 0 } : null);     // assistant panel: {q, n}
  const [tour, setTour] = useState(() => new URLSearchParams(location.search).get('tour') === '1' || tourResume());      // Frank's welcome tour (95_tour.jsx); ?tour=1 starts it; a tour that was in progress when the page blinked continues
  const [theme, setTheme] = useTheme();
  const toast = useToast();
  useEffect(() => { if (THEME.offNote) { toast(`Оформление «${THEME.offNote}» отключено: оно не подходит к этой версии Rack Live. Включено стандартное.`, true); THEME.offNote = null; } }, []);
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
  // the look chosen before 2.51 lives only in this browser: the administrator's device hands it to the server once, so that the installed apps (Frank, the speed test…) get it too
  useEffect(() => { if (!APP_MODE && data && data.authed && !window.RL_LOOK && (getSkin() !== DEFAULT_SKIN || getAccent())) pushLook(); }, [data && data.authed]);
  useEffect(() => {                                       // ui.js of the administrator's own local plugins (rackd/localplug.py), once per page load
    if (APP_MODE || !data || !data.authed || window.__rlLocalScripts) return; window.__rlLocalScripts = true;
    api('/api/x/_scripts').then(r => (r.scripts || []).forEach(u => { const s = document.createElement('script'); s.src = u; s.defer = true; document.head.appendChild(s); })).catch(() => { });
  }, [data && data.authed]);
  useEffect(() => {                                       // ?editdev=<id> opens that device's settings form (needs admin)
    const id = new URLSearchParams(location.search).get('editdev'); const d = id && data && data.devices.find(x => x.id === id);
    if (d) setEditor(d);
  }, [!!data]);
  const scrollerRef = useRef(null);
  // the tab goes into the address (#devices): on iPhone / iPad (also the home-screen app) the address is rewritten in place — assigning location.hash there made the app
  // load the page anew on every tab press (the journal showed «pagehide → загружена (navigate)» each time)
  useEffect(() => {
    if (APP_MODE) return; const h = tab;
    if (/iPhone|iPad|iPod/.test(navigator.userAgent) || navigator.standalone) { try { history.replaceState(null, '', '#' + h); } catch (e) { location.hash = h; } } else location.hash = h;
    lsSet('rl_tab', tab); window.scrollTo(0, 0);
  }, [tab]);
  // «Карта» и «План» — рабочая область на весь экран (38_workmenu.jsx): размеры шапки и нижней панели в переменных CSS, у <html> метка data-mapfull
  const mapFull = PLAN_APP || !APP_MODE && (tab === 'map' || tab === 'plan');
  useLayoutEffect(() => {
    const h = document.documentElement;
    if (mapFull) h.setAttribute('data-mapfull', '1'); else h.removeAttribute('data-mapfull');
    const set = () => {
      const t = document.querySelector('.topbar'), b = document.querySelector('.bottombar'), bs = b ? getComputedStyle(b) : null;
      h.style.setProperty('--tb-h', (t ? t.offsetHeight : 62) + 'px');
      h.style.setProperty('--bb-h', (b && bs.display !== 'none' ? b.offsetHeight + (parseFloat(bs.marginBottom) || 0) : 0) + 'px');
    };
    set(); window.addEventListener('resize', set);
    const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(set) : null;
    if (ro) { const t = document.querySelector('.topbar'); if (t) ro.observe(t); const b = document.querySelector('.bottombar'); if (b) ro.observe(b); }
    const t2 = setTimeout(set, 400);                                  // стили темы подключаются чуть позже
    return () => { window.removeEventListener('resize', set); if (ro) ro.disconnect(); clearTimeout(t2); h.removeAttribute('data-mapfull'); };
  }, [mapFull, data && data.authed]);
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
  if ((data.needLogin && !data.devices) || login || ((FRANK || TERM_APP || CARDS_APP || PLAN_APP) && !data.authed)) return <AuthScreen title={FRANK ? 'Frank' : SPEED_APP ? 'Тест скорости' : TERM_APP ? 'Терминал' : CARDS_APP ? 'Сканер' : PLAN_APP ? 'План' : data.settings && data.settings.title} note={TG && tg !== 'ok' ? 'Вход через Telegram не удался: ' + tg : ''} tgLogin={data.tgLogin} codeLogin={data.loginCodes} passkey={data.passkeyLogin}
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
  const ctx = { data, admin, edit, arrange, setArrange, setMode, theme, setTheme, refresh, saveRack, saveRacks, saveMap, savePlan, logout, applyState, setTab,
    pinTest, setPinTest, pinSpeedTest: id => { setPinTest(id); setMode('view'); setTab('plan'); }, openSpeed: () => setSpeed(true),
    openPlace: id => setPlace(id), openDevice: (d, t, port, popup) => d && setSheet({ id: d.id, tab: t, port, popup: !!popup }), openEditor: d => setEditor(d),
    newDevice: preset => setEditor({ __preset: preset }),             // «Новое устройство» with the type and fields already filled in
    startTour: () => { lsSet('rl_tour_step', ''); setMode('view'); setTour(true); },       // «Показать обучение» always starts from the beginning
    askAi: q => setAi({ q, n: Date.now() }), openFrank: () => setAi({ n: Date.now() }), mode, setMode };
  if (FRANK) return <AppCtx.Provider value={ctx}><div className="app-bg" /><AiPanel standalone /></AppCtx.Provider>;
  if (SPEED_APP) return <AppCtx.Provider value={ctx}><div className="app-bg" /><SpeedApp /></AppCtx.Provider>;
  if (TERM_APP) return <AppCtx.Provider value={ctx}><div className="app-bg" /><TerminalApp /></AppCtx.Provider>;
  if (CARDS_APP) return <AppCtx.Provider value={ctx}><div className="app-bg" /><CardsApp /></AppCtx.Provider>;
  const sheetDev = sheet && data.devices.find(d => d.id === sheet.id);
  if (PLAN_APP) return <AppCtx.Provider value={ctx}><div className="app-bg"/><PlanStandalone/>
    {place ? <PlaceModal rackId={place} onClose={() => setPlace(null)} /> : null}
    {sheetDev ? <DeviceSheet key={sheetDev.id} device={sheetDev} initialTab={sheet.tab} initialPort={sheet.port} popup={sheet.popup} onClose={()=>setSheet(null)}/> : null}
    {editor!==undefined ? <DeviceEditor device={editor&&editor.__preset?null:editor} preset={editor&&editor.__preset} onClose={()=>setEditor(undefined)}/> : null}
    {ai && admin ? <AiPanel key={ai.n} initial={ai.q} onClose={()=>setAi(null)}/> : null}
    {speed ? <SpeedTestModal autoRun={speed==='run'} onClose={()=>setSpeed(null)}/> : null}
  </AppCtx.Provider>;
  const newest = Math.max(0, ...data.devices.map(d => (d.state && d.state.updated) || 0));
  const stale = data.devices.length && (data.now - newest > Math.max(180, (data.settings.poll || 60) * 3));
  const problems = (data.events || []).filter(e => e.t > evSeen && ['offline', 'warning'].includes(e.level)).length;
  const badge = problems > 99 ? '99+' : problems;
  const tabs = TABS.filter(t => !t.admin || admin).map(t => ({ ...t, label: T('tab.' + t.id, t.label) }));      // a custom look may rename the tabs
  const cur = tabs.find(t => t.id === tab) ? tab : 'rack';
  const view = cur;          // what is shown: subtitle and hint follow it
  const dockCur = tabNow != null && tabs.find(t => t.id === tabNow) ? tabNow : cur;      // the dock shows the pressed tab at once, the page follows
  // «Аврора», расстановка виджетов: верхняя капсула превращается в «Готово», левый круг дока — в «Как было» (см. AuTop, AuDock)
  const auArr = isAurora() && admin && edit && arrange && cur === 'rack';
  const subtitle = {
    rack: `${data.devices.filter(d => !d.healthSkip && (d.state || {}).status === 'online').length} из ${data.devices.filter(d => !d.healthSkip).length} устройств в сети${data.racks.length > 1 ? ' · мест: ' + data.racks.length : ''}`,       // «без слежки» не считаются
    map: 'Как всё соединено: шкаф, кабели, точки доступа и клиенты',
    plan: 'План помещений: дома, этажи, двор — где физически стоит оборудование',
    events: 'Сбои, восстановления и действия администратора',
    tools: 'Устройства, плагины и готовые помощники: камеры, удалённые площадки',
    settings: 'Уведомления, Frank, приложения на телефон, доступ и резервные копии',
  }[view];

  return <AppCtx.Provider value={ctx}>
    <div className="app-bg" />
    <header className="topbar">
      {isTestLook() ? <button type="button" className="tl-burger" aria-label="Меню" onClick={() => setNav(true)}><i /><i /><i /></button> : null}
      <div className="brand"><AppIcon size={34} radius={10} style={{ boxShadow: '0 4px 14px rgba(0,60,200,.25)' }} />
        <div className="brand-text"><div className="brand-title ellipsis">{data.settings.title}</div>
          <div className={'live' + (stale ? ' stale' : '')}><i />{stale ? 'нет свежих данных' : 'live · ' + fmt.ago(newest, data.now)}</div></div></div>
      <nav className="tabs">{tabs.map(t => <button key={t.id} data-tour={'tab-' + t.id} className={'tab' + (cur === t.id ? ' on' : '')} title={t.label} onClick={() => setTab(t.id)}>
        <Icon name={t.icon} size={15} /><span className="tab-label">{t.label}</span>{t.id === 'events' && problems ? <span className="count">{badge}</span> : null}</button>)}</nav>
      <div className="grow" />
      <div className="hdr-tools hide-sm">
        {admin ? (mapFull ? null : <span data-tour="edit-toggle" style={{ display: 'inline-flex' }}><Seg className="edit" value={mode} onChange={setMode} options={[{ value: 'view', label: 'Просмотр', icon: 'eye' },
          { value: 'edit', label: 'Редактирование', icon: 'edit', cls: 'editing' }]} /></span>) : <Btn size="sm" icon="lock" onClick={() => setLogin(true)}>Войти</Btn>}
        {admin && edit && cur === 'rack' ? <label className="arrange-sw" title="Двигать, менять размер, добавлять и убирать виджеты на главной"><Switch on={arrange} onChange={setArrange} /><span>Расстановка виджетов</span></label> : null}
        {admin ? <button type="button" data-tour="frank-btn" className="btn sm icon frank-btn" title="Frank — помощник: вопросы о сети" onClick={() => setAi({ n: Date.now() })}>{isAurora() ? <AuEye size={19} /> : <FrankEye size={26} round={8} />}</button> : null}
        <Btn size="sm" icon="gauge" title="Тест скорости Wi-Fi и сети" onClick={() => setSpeed(true)} />
        <Btn size="sm" icon={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'eye'} title={'Тема: ' + ({ auto: 'как в системе', dark: 'тёмная', light: 'светлая' })[theme]}
          onClick={() => setTheme(theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto')} />
      </div>
      {/* phones: everything above folds into one «⋯» button with a menu, like iOS */}
      <button type="button" data-tour="hdr-more" className={'hdr-more only-sm' + (edit ? ' editing' : '')} title="Меню" onClick={() => setMenu(true)}><Icon name="more" size={22} stroke={2.6} /></button>
    </header>
    {nav ? <SideNav key={navKey} tabs={tabs} cur={cur} setTab={setTab} problems={problems} admin={admin} edit={edit} noEdit={mapFull} mode={mode} setMode={setMode} arrange={admin && edit && cur === 'rack' ? arrange : null} setArrange={setArrange}
      theme={theme} setTheme={setTheme} onFrank={() => setAi({ n: Date.now() })} onSpeed={() => setSpeed(true)} onRefresh={refresh} onLogin={() => setLogin(true)} onLogout={logout} onClose={() => { if (tourNav.current) setNavKey(k => k + 1); else setNav(false); }} title={data.settings.title} stale={stale} live={stale ? 'нет свежих данных' : 'live · ' + fmt.ago(newest, data.now)} /> : null}
    {menu ? <HeaderMenu admin={admin} noEdit={mapFull} mode={mode} arrange={admin && edit && cur === 'rack' ? arrange : null} setArrange={setArrange} setMode={setMode} theme={theme} setTheme={setTheme} onClose={() => setMenu(false)}
      onFrank={() => setAi({ n: Date.now() })} onSpeed={() => setSpeed(true)} onRefresh={refresh} onLogin={() => setLogin(true)} onLogout={logout} /> : null}
    <main className={'page' + (mapFull ? ' page-full' : '') + (auArr ? ' au-arr' : '')}>
      {mapFull ? null : <div className="row" style={{ alignItems: 'flex-end', marginBottom: 14 }}>
        <div className="grow"><div className="page-title">{tabs.find(t => t.id === cur).label}</div><div className="page-sub" style={{ marginBottom: 0 }}>{subtitle}</div></div>
        {edit ? <span className="badge warning"><Icon name="edit" size={12} />Режим редактирования</span> : null}
      </div>}
      {cur === 'map' || cur === 'plan' ? null : TAB_HINTS[view] ? (edit && TAB_HINTS[view][1] ? <Hint key={view + '-edit'} id={view + '-edit'}>{TAB_HINTS[view][1]}</Hint>
        : <Hint key={view} id={view}>{TAB_HINTS[view][0]}</Hint>) : null}
      {cur === 'rack' ? <Dashboard /> : null}
      {view === 'map' ? <MapView /> : null}
      {view === 'plan' ? <PlanView /> : null}
      {cur === 'events' ? <EventsView /> : null}
      {cur === 'tools' && admin ? <ToolsView /> : null}
      {cur === 'settings' && admin ? <SettingsView /> : null}
    </main>
    {isAurora() ? <AuTop admin={admin} onDevices={() => { ssSet('rl_pending_tool', 'devices'); if (cur === 'tools') window.dispatchEvent(new CustomEvent('rl-open-tool', { detail: 'devices' })); else setTab('tools'); }} onFrank={() => setAi({ n: Date.now() })} onSpeed={() => setSpeed(true)} onMenu={() => setMenu(true)}
      arr={auArr} onDone={() => { setArrange(false); setMode('view'); }} /> : null}
    {isAurora() && mapFull ? <AuTuck /> : null}
    {isAurora() && mapFull ? <AuFullFit /> : null}
    {isAurora() ? <AuDock tabs={tabs} cur={dockCur} setTab={setTab} problems={problems} badge={badge} onLogin={() => setLogin(true)} arr={auArr} /> : null}
    <nav className="bottombar">{tabs.map(t => <button key={t.id} data-tour={'tab-' + t.id} className={cur === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
      <Icon name={t.icon} size={24} />{t.label}{t.id === 'events' && problems ? <span className="count">{badge}</span> : null}</button>)}</nav>
    {place ? <PlaceModal rackId={place} onClose={() => setPlace(null)} /> : null}
    {sheetDev ? <DeviceSheet key={sheetDev.id} device={sheetDev} initialTab={sheet.tab} initialPort={sheet.port} popup={sheet.popup} onClose={() => setSheet(null)} /> : null}
    {editor !== undefined ? <DeviceEditor device={editor && editor.__preset ? null : editor} preset={editor && editor.__preset} onClose={() => setEditor(undefined)} /> : null}
    {ai && admin ? <AiPanel key={ai.n} initial={ai.q} onClose={() => setAi(null)} /> : null}
    {speed ? <SpeedTestModal autoRun={speed === 'run'} onClose={() => setSpeed(null)} /> : null}
    {tour && admin ? <Tour onDone={finishTour} /> : null}
  </AppCtx.Provider>;
}

/* «Аврора» on a phone (Apple Liquid Glass, iOS 26): on top a round button (the app, with the live dot) and a capsule of actions;
   at the bottom a small dock of the main sections in the middle and two round buttons at the sides (Инструменты, Настройки — or «Войти»).
   Shown only by the CSS of that look at phone width; elsewhere the usual header and tab bar stay. */
const isAurora = () => document.documentElement.getAttribute('data-look') === 'aurora';
/* значок главной кнопки «оживает» по нажатию: у каждой своё движение (data-fx) — шестерёнка проворачивается, ключ качается, колокольчик звенит, глаз моргает…
   Запуск — атрибутом data-go прямо на кнопке (React его не трогает, а класс перезаписал бы при смене раздела) */
const AU_FX = { rack: 'hop', map: 'fold', plan: 'draw', tools: 'wiggle', events: 'ring', settings: 'spin' };
const auFx = e => { const b = e.currentTarget; b.removeAttribute('data-go'); void b.offsetWidth; b.setAttribute('data-go', '1');
  clearTimeout(b._fx); b._fx = setTimeout(() => b.removeAttribute('data-go'), 950); };
/* плавная подмена кнопки: прежняя сжимается и тает (класс out), потом выпрыгивает новая (класс in) */
function useAuSwap(v, ms = 180) {
  const [s, setS] = useState({ v, ph: '' });
  useEffect(() => {
    if (s.v === v) { if (s.ph === 'out') setS({ v, ph: 'in' }); return; }
    setS(x => ({ ...x, ph: 'out' })); const t = setTimeout(() => setS({ v, ph: 'in' }), ms); return () => clearTimeout(t);
  }, [v]);
  return s;
}
function AuTop({ admin, onDevices, onFrank, onSpeed, onMenu, arr, onDone }) {
  const back = useAuBackTop();                                  // a screen with somewhere to go back to turns the button into «Назад»
  const sw = useAuSwap(!!arr);                                  // расстановка виджетов: вся капсула справа превращается в одну кнопку «Готово»
  const left = sw.v ? <span key="none" className="au-spacer" />
    : back ? <button type="button" key="back" data-fx="nudge" className={'au-glass au-circle au-morph au-sw ' + sw.ph} title={'Назад: ' + back.label} aria-label={'Назад: ' + back.label} onClick={e => { auFx(e); back.fn(); }}>
      <Icon name="chevron" size={22} stroke={2.6} style={{ transform: 'rotate(180deg)' }} /></button>
    : admin ? <button type="button" key="dev" data-fx="stack" className={'au-glass au-circle au-morph au-sw ' + sw.ph} title="Устройства" aria-label="Устройства" onClick={e => { auFx(e); onDevices(); }}><Icon name="server" size={21} /></button>
    : <span key="none" className="au-spacer" />;
  return <div className="au-top">
    {left}
    {sw.v ? <button type="button" key="done" className={'au-circle au-done au-sw ' + sw.ph} title="Готово" aria-label="Готово" onClick={onDone}><Icon name="check" size={25} stroke={2.8} /></button>
      : <div key="pill" className={'au-glass au-pill au-sw ' + sw.ph}>
        {admin ? <button type="button" data-fx="blink" title="Frank — помощник" aria-label="Frank" onClick={e => { auFx(e); onFrank(); }}><AuEye size={23} /></button> : null}
        <button type="button" data-fx="rev" title="Тест скорости" aria-label="Тест скорости" onClick={e => { auFx(e); onSpeed(); }}><Icon name="gauge" size={21} /></button>
        <button type="button" data-fx="dots" title="Меню" aria-label="Меню" onClick={e => { auFx(e); onMenu(); }}><Icon name="more" size={21} stroke={2.6} /></button>
      </div>}
  </div>;
}
function AuDock({ tabs, cur, setTab, problems, badge, onLogin, arr }) {
  const SIDE = ['tools', 'settings'];
  const main = tabs.filter(t => !SIDE.includes(t.id)), left = tabs.find(t => t.id === 'tools'), right = tabs.find(t => t.id === 'settings');
  const btn = t => <button key={t.id} type="button" data-fx={AU_FX[t.id] || 'hop'} title={t.label} aria-label={t.label} className={cur === t.id ? 'on' : ''} onClick={e => { auFx(e); setTab(t.id); setMini(false); }}>
    <Icon name={t.icon} size={23} />{t.id === 'events' && problems ? <span className="count">{badge}</span> : null}</button>;
  const sw = useAuSwap(!!arr);                                  // расстановка виджетов: «Инструменты» на время становятся кнопкой «Как было»
  const nav = useRef(null);
  const idx = main.findIndex(t => t.id === cur);
  // a side section is open (tools, settings): its circle steps back when the dock shrinks, so the shrunk capsule shows that section's icon instead of staying empty
  const curSide = idx < 0 ? tabs.find(t => t.id === cur && SIDE.includes(t.id)) : null;
  // iOS 26: scrolling down shrinks the dock to the open section (the side buttons step back), scrolling up or a tap brings it back
  const [mini, setMini] = useState(false);
  useEffect(() => {
    let last = window.scrollY, acc = 0, rest = 0;
    // сжатый док живёт от прокрутки: значок открытого раздела наклоняется по ходу пальца и пружинит обратно (шестерёнка — катится), по кромке бежит кольцо «сколько пролистано»
    const fx = (d, y) => { const el = nav.current; if (!el) return;
      const max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
      el.style.setProperty('--au-sv', Math.max(-1, Math.min(1, d / 26)).toFixed(3)); el.style.setProperty('--au-sy', Math.round(y)); el.style.setProperty('--au-sp', Math.max(0, Math.min(1, y / max)).toFixed(4));
      clearTimeout(rest); rest = setTimeout(() => el.style.setProperty('--au-sv', '0'), 110); };
    const on = () => { if (document.querySelector('main.page-full')) return;   // map / plan: the page is scrolled by AuFullFit, not by the finger
      const y = window.scrollY, d = y - last; last = y; acc = Math.sign(d) === Math.sign(acc) ? acc + d : d; fx(d, y);
      if (y < 40) setMini(false); else if (acc > 60) setMini(true); else if (acc < -40) setMini(false); };
    window.addEventListener('scroll', on, { passive: true }); return () => { window.removeEventListener('scroll', on); clearTimeout(rest); };
  }, []);
  useEffect(() => { setMini(false); }, [cur]);
  return <nav ref={nav} className={'au-dock' + (mini && !arr ? ' mini' : '')}>
    {sw.v ? <div key="reset" className={'au-glass au-circle au-side au-sw ' + sw.ph}><button type="button" data-fx="back" title="Как было" aria-label="Вернуть главную как было"
        onClick={e => { auFx(e); window.dispatchEvent(new Event('rl-dash-reset')); }}><Icon name="undo" size={22} stroke={2.1} /></button></div>
      : left ? <div key="tools" className={'au-glass au-circle au-side au-sw ' + sw.ph}>{btn(left)}</div> : <span className="au-spacer" />}
    <div className="au-glass au-pill au-tabs" style={{ '--i': idx, '--n': main.length }} onClick={() => mini && setMini(false)}>
      {idx >= 0 ? <span className="au-lens" aria-hidden="true" /> : curSide ? <span className="au-lens au-lens-side" aria-hidden="true" /> : null}{main.map(btn)}
      {curSide ? <button key="side-mini" type="button" tabIndex={-1} data-fx={AU_FX[curSide.id]} title={curSide.label} aria-label={curSide.label} className="on au-side-mini" onClick={() => setMini(false)}><Icon name={curSide.icon} size={23} /></button> : null}</div>
    {right ? <div className="au-glass au-circle au-side">{btn(right)}</div>
      : <div className="au-glass au-circle au-side"><button type="button" title="Войти" aria-label="Войти" onClick={onLogin}><Icon name="lock" size={22} /></button></div>}
  </nav>;
}

/* «Аврора», карта и план на телефоне в установленном приложении: iOS начинает страницу ниже строки статуса, а в зоне под часами показывает то,
   что на странице выше прокрутки. Поэтому холст делается ровно по видимой высоте плюс запас сверху, и страница прокручивается на этот запас —
   под часами видна сама карта, как содержимое других вкладок. Верхние панели холста сдвигаются на тот же запас (--au-shift в CSS). */
const AU_SHIFT = 120;
function AuFullFit() {
  useEffect(() => {
    const h = document.documentElement;
    const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    const fit = () => {
      if (innerWidth > 760) { h.style.removeProperty('--au-vh'); h.style.removeProperty('--au-shift'); return; }
      const shift = standalone ? AU_SHIFT : 0;
      h.style.setProperty('--au-vh', innerHeight + 'px'); h.style.setProperty('--au-shift', shift + 'px');
      requestAnimationFrame(() => window.scrollTo(0, shift));
    };
    // iOS moves the page by itself now and then (a tap on a house, the map flying to it, coming back to the app): the bottom of the canvas with the
    // house card would slide off the screen. The page is pinned: any drift is put back at once.
    const pin =() => { const want = parseFloat(h.style.getPropertyValue('--au-shift')) || 0;
      if (innerWidth <= 760 && Math.abs(window.scrollY - want) > 1) window.scrollTo(0, want); };
    const again = () => { if (!document.hidden) { fit(); setTimeout(fit, 300); } };
    fit(); const t = setTimeout(fit, 350);
    addEventListener('resize', fit); addEventListener('orientationchange', fit); addEventListener('scroll', pin, { passive: true });
    addEventListener('pageshow', again); document.addEventListener('visibilitychange', again);
    if (window.visualViewport) visualViewport.addEventListener('resize', fit);
    return () => { clearTimeout(t); removeEventListener('resize', fit); removeEventListener('orientationchange', fit); removeEventListener('scroll', pin);
      removeEventListener('pageshow', again); document.removeEventListener('visibilitychange', again);
      if (window.visualViewport) visualViewport.removeEventListener('resize', fit);
      h.style.removeProperty('--au-vh'); h.style.removeProperty('--au-shift'); window.scrollTo(0, 0); };
  }, []);
  return null;
}

/* «Аврора», карта и план на телефоне: свои кнопки экрана сворачиваются в один стеклянный круг — с анимацией, как окно в Dock macOS
   (втягивается к кнопке, сужаясь), и разворачиваются обратно. Выбор помнится на устройстве; по умолчанию свёрнуто. */
const AU_TUCK_SEL = '.page-full :is(.plan-ctx, .plan-floors, .plan-tool-current, .map-tools, .zoom-btns, .map-legend, .plan-hint, .rack-jump, .plan-edit-dock), .wm-fab';
function AuTuck() {
  const ref = useRef(null); const busy = useRef(false);
  const [tucked, setTucked] = useState(() => lsGet('rl_au_tuck', '1') !== '0');
  useEffect(() => { document.documentElement.classList.toggle('au-tucked', tucked); }, [tucked]);
  useEffect(() => () => document.documentElement.classList.remove('au-tucked'), []);
  const genie = closing => {
    const b = ref.current.getBoundingClientRect(), bx = b.left + b.width / 2, by = b.top + b.height / 2;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const els = [...document.querySelectorAll(AU_TUCK_SEL)].filter(el => el.getBoundingClientRect().width);
    return Promise.all(els.map((el, k) => {
      const r = el.getBoundingClientRect(), dx = bx - (r.left + r.width / 2), dy = by - (r.top + r.height / 2);
      const open = { transform: 'none', opacity: 1 }, mid = { transform: `translate(${dx * .2}px, ${dy * .62}px) scale(.5, .82)`, opacity: .9 },
        shut = { transform: `translate(${dx}px, ${dy}px) scale(.04, .06)`, opacity: 0 };
      const frames = closing ? [open, { ...mid, offset: .45 }, shut] : [shut, { ...mid, offset: .55 }, open];
      const a = el.animate(frames, { duration: reduce ? 1 : 520, delay: reduce ? 0 : k * 40, easing: closing ? 'cubic-bezier(.55,0,.75,.3)' : 'cubic-bezier(.2,.75,.25,1)', fill: 'both' });
      return a.finished.then(() => a).catch(() => a);
    }));
  };
  const toggle = async () => {
    if (busy.current) return; busy.current = true;
    try {
      if (!tucked) { const anims = await genie(true); document.documentElement.classList.add('au-tucked'); anims.forEach(a => a.cancel()); setTucked(true); lsSet('rl_au_tuck', '1'); }
      else { document.documentElement.classList.remove('au-tucked'); const anims = await genie(false); anims.forEach(a => a.cancel()); setTucked(false); lsSet('rl_au_tuck', '0'); }
    } finally { busy.current = false; }
  };
  return <button type="button" ref={ref} className="au-tuck au-glass" title={tucked ? 'Показать кнопки' : 'Спрятать кнопки'} aria-label={tucked ? 'Показать кнопки' : 'Спрятать кнопки'} onClick={toggle}>
    <Icon key={tucked ? 'm' : 'x'} name={tucked ? 'more' : 'x'} size={21} stroke={2.4} /></button>;
}

/* phone header menu: tiles on top (Frank, speed test, refresh), rows below (editing, theme, sign in / out) — like an iOS context menu */
function HeaderMenu({ admin, noEdit, mode, arrange, setArrange, setMode, theme, setTheme, onClose, onFrank, onSpeed, onRefresh, onLogin, onLogout }) {
  useEffect(() => { const h = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);
  const go = fn => () => { onClose(); fn(); };
  return <div className="hdr-menu-wrap" onClick={e => e.target === e.currentTarget && onClose()}>
    <div className="hdr-menu">
      <div className="hdr-tiles">
        {admin ? <button type="button" onClick={go(onFrank)}>{isAurora() ? <AuEye size={26} /> : <FrankEye size={30} round={9} />}<span>Frank</span></button> : null}
        <button type="button" onClick={go(onSpeed)}><Icon name="gauge" size={24} /><span>Тест скорости</span></button>
        <button type="button" onClick={go(onRefresh)}><Icon name="refresh" size={24} /><span>Обновить</span></button>
      </div>
      {admin && !noEdit ? <div className="hdr-row">
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
// a custom look's texts / icons are read first (they live in a global), then the page is drawn; a failure here never blocks the start
loadTheme().catch(() => { }).finally(() => ReactDOM.createRoot(document.getElementById('root')).render(<Crash><ToastHost><ConfirmHost><App /></ConfirmHost></ToastHost></Crash>));
