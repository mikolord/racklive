/* App shell */
const TABS = [
  { id: 'rack', label: 'Шкаф', icon: 'rack' },
  { id: 'map', label: 'Карта сети', icon: 'map' },
  { id: 'plan', label: 'План', icon: 'home' },
  { id: 'devices', label: 'Устройства', icon: 'list' },
  { id: 'events', label: 'События', icon: 'bell' },
  { id: 'settings', label: 'Настройки', icon: 'settings', admin: true },
];
const lsGet = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { } };

function useTheme() {
  const [pref, setPref] = useState(lsGet('rl_theme', 'auto'));
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
  const [tab, setTab] = useState(() => (location.hash.slice(1) || lsGet('rl_tab', 'rack')));
  const [mode, setMode] = useState('view');
  const [sheet, setSheet] = useState(null);
  const [editor, setEditor] = useState(undefined);
  const [login, setLogin] = useState(false);
  const [theme, setTheme] = useTheme();
  const toast = useToast();

  const refresh = useCallback(async () => {
    try { const d = await api('/api/state'); setData(d); setErr(null); }
    catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 15000); return () => clearInterval(t); }, [refresh]);
  const scrollerRef = useRef(null);
  useEffect(() => { location.hash = tab; lsSet('rl_tab', tab); window.scrollTo(0, 0); }, [tab]);
  // deep link: ?device=<id>&tab=ports&port=9 opens the device sheet
  const deep = useRef(new URLSearchParams(location.search));
  useEffect(() => {
    const p = deep.current; if (!data || !data.devices || !p.get('device')) return;
    const d = data.devices.find(x => x.id === p.get('device') || x.name === p.get('device'));
    if (d) setSheet({ id: d.id, tab: p.get('tab'), port: p.get('port') ? +p.get('port') : null });
    deep.current = new URLSearchParams();
  }, [data]);
  useEffect(() => { if (data && data.settings && data.settings.title) document.title = data.settings.title + ' · Rack Live'; }, [data && data.settings && data.settings.title]);

  if (!data) return <div className="auth"><div className="app-bg" />{err ? <div className="card pad">Сервер недоступен: {err}<br /><Btn style={{ marginTop: 12 }} onClick={refresh}>Повторить</Btn></div>
    : <div className="dim">Загрузка…</div>}</div>;
  if (data.setupNeeded) return <AuthScreen setup title={data.settings && data.settings.title} onDone={refresh} />;
  if ((data.needLogin && !data.devices) || login) return <AuthScreen title={data.settings && data.settings.title} onDone={() => { setLogin(false); refresh(); }} />;

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
  const savePlan = async buildings => {
    setData(d => ({ ...d, plan: { buildings } }));
    try { await api('/api/plan', { method: 'PUT', body: { buildings } }); } catch (e) { toast(e.message, true); refresh(); }
  };
  const logout = async () => { await api('/api/logout', { method: 'POST' }); setMode('view'); refresh(); };
  const applyState = (id, state) => setData(d => ({ ...d, devices: d.devices.map(x => x.id === id ? { ...x, state } : x) }));
  const ctx = { data, admin, edit, refresh, saveRack, saveRacks, saveMap, savePlan, logout, applyState, setTab,
    openDevice: (d, t, port) => d && setSheet({ id: d.id, tab: t, port }), openEditor: d => setEditor(d) };
  const sheetDev = sheet && data.devices.find(d => d.id === sheet.id);
  const newest = Math.max(0, ...data.devices.map(d => (d.state && d.state.updated) || 0));
  const stale = data.devices.length && (data.now - newest > Math.max(180, (data.settings.poll || 60) * 3));
  const problems = data.devices.filter(d => ['offline', 'warning'].includes((d.state || {}).status)).length;
  const tabs = TABS.filter(t => !t.admin || admin);
  const cur = tabs.find(t => t.id === tab) ? tab : 'rack';
  const subtitle = {
    rack: `${data.racks.length > 1 ? data.racks.length + ' шкафа · ' : ''}${data.devices.filter(d => (d.state || {}).status === 'online').length} из ${data.devices.length} устройств в сети`,
    map: 'Как всё соединено: шкаф, кабели, точки доступа и клиенты',
    plan: 'План помещений: дома, этажи, двор — где физически стоит оборудование',
    devices: 'Всё, что собирает данные: локальные и удалённые устройства',
    events: 'Сбои, восстановления и действия администратора',
    settings: 'Название, доступ, VLAN и резервные копии',
  }[cur];

  return <AppCtx.Provider value={ctx}>
    <div className="app-bg" />
    <header className="topbar">
      <div className="brand"><div className="brand-logo"><Icon name="rack" size={19} color="#fff" /></div>
        <div style={{ minWidth: 0 }}><div className="brand-title ellipsis">{data.settings.title}</div>
          <div className={'live' + (stale ? ' stale' : '')}><i />{stale ? 'нет свежих данных' : 'live · ' + fmt.ago(newest, data.now)}</div></div></div>
      <nav className="tabs">{tabs.map(t => <button key={t.id} className={'tab' + (cur === t.id ? ' on' : '')} onClick={() => setTab(t.id)}>
        <Icon name={t.icon} size={15} />{t.label}{t.id === 'events' && problems ? <span className="count">{problems}</span> : null}</button>)}</nav>
      <div className="grow" />
      {admin ? <Seg className="edit" value={mode} onChange={setMode} options={[{ value: 'view', label: 'Просмотр', icon: 'eye' },
        { value: 'edit', label: 'Редактирование', icon: 'edit', cls: 'editing' }]} /> : <Btn size="sm" icon="lock" onClick={() => setLogin(true)}>Войти</Btn>}
      <Btn size="sm" icon={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'eye'} title={'Тема: ' + ({ auto: 'как в системе', dark: 'тёмная', light: 'светлая' })[theme]}
        onClick={() => setTheme(theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto')} />
    </header>
    <main className="page">
      <div className="row" style={{ alignItems: 'flex-end', marginBottom: 14 }}>
        <div className="grow"><div className="page-title">{tabs.find(t => t.id === cur).label}</div><div className="page-sub" style={{ marginBottom: 0 }}>{subtitle}</div></div>
        {edit ? <span className="badge warning"><Icon name="edit" size={12} />Режим редактирования</span> : null}
      </div>
      {cur === 'rack' ? <RackView /> : null}
      {cur === 'map' ? <MapView /> : null}
      {cur === 'plan' ? <PlanView /> : null}
      {cur === 'devices' ? <DevicesView /> : null}
      {cur === 'events' ? <EventsView /> : null}
      {cur === 'settings' && admin ? <SettingsView /> : null}
    </main>
    <nav className="bottombar">{tabs.map(t => <button key={t.id} className={cur === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>
      <Icon name={t.icon} size={24} />{t.id === 'map' ? 'Карта' : t.label}{t.id === 'events' && problems ? <span className="count">{problems}</span> : null}</button>)}</nav>
    {sheetDev ? <DeviceSheet key={sheetDev.id} device={sheetDev} initialTab={sheet.tab} initialPort={sheet.port} onClose={() => setSheet(null)} /> : null}
    {editor !== undefined ? <DeviceEditor device={editor} onClose={() => setEditor(undefined)} /> : null}
  </AppCtx.Provider>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<ToastHost><ConfirmHost><App /></ConfirmHost></ToastHost>);
