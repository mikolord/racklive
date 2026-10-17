/* Tab «Инструменты»: three sections — «Устройства» (the old tab), «Плагины» (by device) and «Инструменты» (a catalog of helpers; first: cameras and recorders).
   Backend: GET /api/plugins/catalog · rackd/cameras.py (/api/cameras*). */
const PLUGIN_GROUPS = [
  { id: 'keenetic', title: 'Keenetic / Netcraze', drivers: ['keenetic', 'demo_router'], icon: 'router', empty: 'роутер Keenetic или Netcraze' },
  { id: 'openwrt', title: 'OpenWrt', drivers: ['openwrt', 'demo_openwrt'], icon: 'router', empty: 'роутер на OpenWrt (логин root, SSH включён)' },
  { id: 'ssh', title: 'Сервер / VPS по SSH', drivers: ['ssh', 'demo_server'], icon: 'server', empty: 'сервер или VPS по SSH' },
  { id: 'synology', title: 'Synology', drivers: ['synology'], icon: 'server', empty: 'NAS Synology (нужен включённый SSH)' },
];
const groupOfDriver = d => PLUGIN_GROUPS.find(g => g.drivers.includes(d));
const realDriver = g => g.drivers[0];          // the driver names plugins are declared for (rackd/plugins.py, vps.py)
const TOOLS = [
  { id: 'cameras', title: 'Камеры и видеорегистраторы', icon: 'camera', color: '#ff375f',
    text: 'Сам найдёт камеры в вашей сети, отличит камеру от регистратора, поможет сменить пароли и адреса — хоть всем сразу — и покажет кадр.' },
  { id: 'scenes', title: 'Демо-сцены и планы', icon: 'home', color: '#ff9f0a',
    text: 'Большая выдуманная сеть с домами, этажами и комнатами — посмотреть в отдельной демо-копии или перенести раскладку на свой план. Сцены можно составить с нейросетью.' },
  { id: 'sites', title: 'Удалённые площадки и агенты', icon: 'globe2', color: '#5e5ce6',
    text: 'Следить за другой сетью без белого IP и проброса портов: офис, дача, квартира родителей. Там ставится свой Rack Live (сборщик) или маленький агент — данные приходят сюда сами.' },
];

/* open an instrument from anywhere: the Tools tab → «Инструменты» → the tool (and a camera's address to pick in it) */
function openToolById(ctx, id, cam) {
  try { sessionStorage.setItem('rl_pending_tool', id); if (cam) sessionStorage.setItem('rl_pending_cam', cam); } catch (e) { }
  ctx.setToolsSec('catalog'); ctx.setTab('tools');
  setTimeout(() => window.dispatchEvent(new CustomEvent('rl-open-tool', { detail: id })), 120);
}

function ToolsView() {
  const { toolsSec: sec, setToolsSec: setSec } = useApp();
  const [tool, setTool] = useState(() => { const t = new URLSearchParams(location.search).get('tool') || ssGet('rl_pending_tool') || null; try { sessionStorage.removeItem('rl_pending_tool'); } catch (e) { } return t; });
  useEffect(() => { const h = e => setTool(e.detail); window.addEventListener('rl-open-tool', h); return () => window.removeEventListener('rl-open-tool', h); }, []);       // «open the cameras tool» from elsewhere (the scan window, a client's card)
  return <>
    <div className="view-switch"><Seg value={sec} onChange={s => { setSec(s); setTool(null); }}
      options={[{ value: 'devices', label: T('tab.devices', 'Устройства'), icon: 'list' }, { value: 'plugins', label: 'Плагины', icon: 'box' }, { value: 'catalog', label: 'Инструменты', icon: 'wrench' }]} /></div>
    {sec === 'devices' ? <DevicesView /> : sec === 'plugins' ? <PluginsOverview /> : tool === 'cameras' ? <CameraTool onBack={() => setTool(null)} /> : tool === 'sites' ? <SitesTool onBack={() => setTool(null)} /> : tool === 'scenes' ? <ScenesTool onBack={() => setTool(null)} /> : String(tool).startsWith('x-') ? <CommunityTool id={tool.slice(2)} onBack={() => setTool(null)} /> : <ToolsCatalog onOpen={setTool} />}
  </>;
}

/* ───────── «where to look»: automatic by default; a small button opens the choice of networks ───────── */
function WhereToSearch({ subnets, value, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const [own, setOwn] = useState('');
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('pointerdown', h); return () => document.removeEventListener('pointerdown', h);
  }, [open]);
  const auto = !value.length;
  const known = new Set(subnets.map(s => s.cidr));
  const toggle = c => onChange(value.includes(c) ? value.filter(x => x !== c) : [...value, c]);
  const okOwn = /^\d+\.\d+\.\d+\.\d+\/\d+$/.test(own.trim());
  const add = () => { const c = own.trim(); if (okOwn && !value.includes(c)) { onChange([...value, c]); setOwn(''); } };
  return <div className="where" ref={ref}>
    <button type="button" className="btn sm where-btn" disabled={disabled} onClick={() => setOpen(!open)}>
      <Icon name="map" size={14} />{auto ? 'Сети: автоматически' : 'Сети: ' + (value.length === 1 ? value[0] : value.length + ' выбрано')}<Icon name="chevron" size={12} style={{ transform: open ? 'rotate(-90deg)' : 'rotate(90deg)' }} /></button>
    {open ? <div className="where-pop card">
      <button type="button" className={'where-row' + (auto ? ' on' : '')} onClick={() => onChange([])}><span className="where-dot" />
        <span className="grow" style={{ textAlign: 'left' }}><b>Автоматически</b><small>все сети, о которых знает Rack Live: ваша, сети роутеров и устройств</small></span></button>
      <div className="dim3" style={{ fontSize: 11.5, margin: '8px 4px 4px' }}>Или выберите сами:</div>
      {subnets.map(s => <button type="button" key={s.cidr} className={'where-row' + (value.includes(s.cidr) ? ' on' : '')} onClick={() => toggle(s.cidr)}><span className="where-dot sq" />
        <span className="grow" style={{ textAlign: 'left' }}><b className="mono">{s.cidr}</b><small>{s.label}</small></span></button>)}
      {value.filter(c => !known.has(c)).map(c => <button type="button" key={c} className="where-row on" onClick={() => toggle(c)}><span className="where-dot sq" /><span className="grow" style={{ textAlign: 'left' }}><b className="mono">{c}</b><small>ваша сеть</small></span></button>)}
      <div className="row" style={{ gap: 6, marginTop: 8 }}><input className="input mono grow" value={own} onChange={e => setOwn(e.target.value)} placeholder="Своя: 192.168.50.0/24" onKeyDown={e => e.key === 'Enter' && add()} />
        <Btn size="sm" disabled={!okOwn} onClick={add}>Добавить</Btn></div>
    </div> : null}
  </div>;
}

/* ───────── plugins: by device ───────── */
function PluginsOverview() {
  const { data, openDevice } = useApp(); const toast = useToast();
  const [cat, setCat] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [comm, setComm] = useState(() => new URLSearchParams(location.search).get('community') === '1');      // ?community=1 opens the manager
  const [status, setStatus] = useState({});            // deviceId → {pluginId: installed} | 'error' | 'loading'
  useEffect(() => { api('/api/plugins/catalog').then(r => setCat(r.plugins)).catch(e => toast(e.message, true)); }, []);
  const check = async d => {
    setStatus(s => ({ ...s, [d.id]: 'loading' }));
    try { const r = await api(`/api/devices/${d.id}/plugins`, { method: 'POST', body: { op: 'status' } }); setStatus(s => ({ ...s, [d.id]: Object.fromEntries(r.plugins.map(p => [p.id, !!p.installed])) })); }
    catch (e) { setStatus(s => ({ ...s, [d.id]: 'error' })); }
  };
  if (!cat) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  const devs = data.devices.filter(d => groupOfDriver(d.driver));
  const missing = PLUGIN_GROUPS.filter(g => !devs.some(d => g.drivers.includes(d.driver)));
  const open = (d, pid) => { const u = new URL(location.href); u.searchParams.set('plugin', pid); try { history.replaceState(null, '', u.pathname + u.search + u.hash); } catch (e) { } openDevice(d, 'plugins'); };
  const toggle = d => { const o = openId === d.id ? null : d.id; setOpenId(o); if (o && !status[d.id]) check(d); };
  return <>
    <Hint id="tools-plugins2">Здесь устройства, на которые Rack Live умеет ставить дополнения. Нажмите на устройство — раскроется список плагинов; нажмите на плагин — откроется установка с проверкой и журналом.</Hint>
    <div className="card plug-comm" style={{ marginBottom: 10 }}><div className="row" style={{ gap: 10, alignItems: 'center' }}>
      <div className="ico-circle"><Icon name="box" size={18} /></div>
      <div className="grow" style={{ minWidth: 0 }}><b>Плагины сообщества</b><div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4 }}>Каталог от других пользователей, загрузка своего плагина и инструкция, как его написать. Каждый плагин проверяется и запускается только после вашего подтверждения.</div></div>
      <Btn onClick={() => { setComm(true); }}>Открыть</Btn></div></div>
    {comm ? <CommunityManager onClose={() => { setComm(false); api('/api/plugins/catalog').then(r => setCat(r.plugins)).catch(() => { }); }} /> : null}
    {!devs.length ? <div className="card" style={{ marginBottom: 10 }}><div className="dim" style={{ fontSize: 13.5 }}>Пока нет устройств, для которых есть плагины. Ниже все плагины по типам устройств: откройте нужный тип и добавьте такое устройство.</div></div> : null}
    <div className="col" style={{ gap: 10 }}>{devs.map(d => {
      const g = groupOfDriver(d.driver);
      const list = cat.filter(p => (p.drivers || []).includes(realDriver(g)));
      const st = status[d.id]; const isOpen = openId === d.id;
      const inst = st && typeof st === 'object' ? list.filter(p => st[p.id]).length : null;
      return <div className={'card plugin plug-dev-card' + (isOpen ? ' open' : '')} key={d.id}>
        <button type="button" className="plugin-head" onClick={() => toggle(d)}>
          <KindIcon kind={d.kind || 'router'} size={38} round={11} />
          <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}><b className="ellipsis" style={{ display: 'block' }}>{d.name}</b>
            <div className="dim" style={{ fontSize: 12.5 }}>{g.title} · плагинов: {list.length}{inst != null ? ' · установлено: ' + inst : ''}</div></div>
          {st === 'loading' ? <span className="spin-dot" /> : null}
          <Icon name="chevron" size={16} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} />
        </button>
        {isOpen ? <div className="plug-list">
          {st === 'error' ? <div className="cam-warn">Не удалось проверить устройство — статус плагинов неизвестен. <Btn size="sm" onClick={() => check(d)}>Повторить</Btn></div> : null}
          {list.map(p => { const i = st && typeof st === 'object' ? st[p.id] : undefined;
            return <button type="button" key={p.id} className="plug-row" onClick={() => open(d, p.id)}>
              <span className="ico-circle"><Icon name={p.icon || 'box'} size={17} /></span>
              <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{p.title}</b><small>{p.description}</small></span>
              {i === true ? <span className="badge online"><Icon name="check" size={11} />установлено</span> : i === false ? <span className="badge">не установлено</span> : null}
              <Icon name="chevron" size={14} /></button>; })}
        </div> : null}
      </div>;
    })}</div>
    {missing.map(g => <MissingGroup key={g.id} g={g} list={cat.filter(p => (p.drivers || []).includes(realDriver(g)))} />)}
  </>;
}

/* a device type the user has none of: its plugins are still shown (greyed), with the reason they cannot be installed yet */
function MissingGroup({ g, list }) {
  const { newDevice } = useApp(); const [open, setOpen] = useState(false);
  if (!list.length) return null;
  return <div className={'card plugin plug-dev-card plug-missing' + (open ? ' open' : '')} style={{ marginTop: 10, opacity: .92 }}>
    <button type="button" className="plugin-head" onClick={() => setOpen(!open)}>
      <div className="ico-circle" style={{ opacity: .6 }}><Icon name={g.icon} size={18} /></div>
      <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}><b className="ellipsis" style={{ display: 'block' }}>{g.title}</b>
        <div className="dim" style={{ fontSize: 12.5 }}>плагинов: {list.length} · устройства этого типа нет</div></div>
      <span className="badge">недоступно</span>
      <Icon name="chevron" size={16} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} /></button>
    {open ? <div className="plug-list">
      <div className="err-note" style={{ marginTop: 0 }}>Эти плагины сейчас установить нельзя: у вас нет устройства типа «{g.title}» ({g.empty}).
        Добавьте такое устройство — или, если оно уже есть в Rack Live, но с другим типом, откройте его и выберите тип вручную. После этого плагины станут доступны.</div>
      <div><Btn size="sm" kind="primary" icon="plus" onClick={() => newDevice({ driver: realDriver(g) })}>Добавить устройство этого типа</Btn></div>
      {list.map(p => <div key={p.id} className="plug-row" style={{ opacity: .6, cursor: 'default' }}>
        <span className="ico-circle"><Icon name={p.icon || 'box'} size={17} /></span>
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{p.title}</b><small>{p.description}</small></span></div>)}
    </div> : null}
  </div>;
}

/* ───────── catalog of tools ───────── */
function ToolsCatalog({ onOpen }) {
  const toast = useToast();
  const [mine, setMine] = useState([]); const [mgr, setMgr] = useState(false);
  const loadMine = () => api('/api/community').then(r => setMine(r.plugins.filter(p => p.kind === 'tool'))).catch(() => { });
  useEffect(() => { loadMine(); }, []);
  const ICON_COLORS = ['#0a84ff', '#30b0c7', '#34c759', '#ff9f0a', '#bf5af2', '#ff375f'];
  return <>
    <Hint id="tools-catalog">Инструменты — помощники для администратора. Встроенные только смотрят и сами ничего не меняют. Инструменты сообщества (свои или из каталога) перед запуском показывают, что именно будут делать.</Hint>
    <div className="plug-grid">{TOOLS.map(t => <button type="button" key={t.id} className="card tool-card" onClick={() => onOpen(t.id)}>
      <div className="tool-ic" style={{ background: t.color }}><Icon name={t.icon} size={24} color="#fff" stroke={2} /></div>
      <div className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{t.title}</b><div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4, marginTop: 3 }}>{t.text}</div></div>
      <Icon name="chevron" size={16} /></button>)}
      {mine.map((t, i) => <button type="button" key={t.id} className="card tool-card" onClick={() => onOpen('x-' + t.id)}>
        <div className="tool-ic" style={{ background: ICON_COLORS[i % ICON_COLORS.length] }}><Icon name={t.icon || 'wrench'} size={24} color="#fff" stroke={2} /></div>
        <div className="grow" style={{ textAlign: 'left', minWidth: 0 }}><div className="row" style={{ gap: 6 }}><b>{t.title}</b><span className="badge">{t.source === 'community' ? 'сообщество' : 'своё'}</span></div>
          <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4, marginTop: 3 }}>{t.description}</div></div>
        <Icon name="chevron" size={16} /></button>)}
      <button type="button" className="card tool-card soon" onClick={() => setMgr(true)}><div className="tool-ic" style={{ background: 'var(--fill)' }}><Icon name="plus" size={22} /></div>
        <div className="grow" style={{ textAlign: 'left' }}><b>Свой инструмент или из каталога</b><div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4, marginTop: 3 }}>Загрузите .zip или выберите готовый в каталоге сообщества. Плагины и инструменты добавляются в одном окне, каждый появляется на своём месте.</div></div></button>
    </div>
    {mgr ? <CommunityManager onClose={() => { setMgr(false); loadMine(); }} /> : null}
  </>;
}

/* ───────── cameras ───────── */
const LOGIN_TEXT = { password: ['запрашивает пароль', 'online'], open: ['открыта без пароля!', 'offline'], inactive: ['не активирована', 'warning'], unknown: ['пароль не проверен', ''] };
const KIND_WORD = { camera: 'Камера', recorder: 'Видеорегистратор', unknown: 'Видеоустройство' };
const genPassword = () => { const a = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'; const v = new Uint32Array(12); (window.crypto || window.msCrypto).getRandomValues(v); return Array.from(v, x => a[x % a.length]).join(''); };

function CameraTool({ onBack }) {
  const { data, newDevice } = useApp(); const toast = useToast();
  const [info, setInfo] = useState(null);
  const [where, setWhere] = useState([]);                // [] = automatically
  const [manual, setManual] = useState('');
  const [sel, setSel] = useState(() => new Set());       // ips ticked for «several at once»
  const [open, setOpen] = useState(null);                // the camera whose window is open
  const [bulk, setBulk] = useState(false);
  const [credsOpen, setCredsOpen] = useState(false);
  const [brandsOpen, setBrandsOpen] = useState(false);
  const [recs, setRecs] = useState([]); const [rec, setRec] = useState(null);       // recorders that live on your devices (Synology Surveillance Station)
  useEffect(() => { api('/api/cameras/recorders').then(r => setRecs(r.recorders || [])).catch(() => { }); }, []);
  const load = async () => { try { const r = await api('/api/cameras'); setInfo(r); return r; } catch (e) { return null; } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!info || !info.running) return; const t = setInterval(load, 1000); return () => clearInterval(t); }, [info && info.running]);
  const start = async () => { try { setSel(new Set()); await api('/api/cameras/start', { method: 'POST', body: { cidrs: where } }); load(); } catch (e) { toast(e.message, true); } };
  const stop = async () => { try { await api('/api/cameras/stop', { method: 'POST', body: {} }); } catch (e) { } };
  const probe = async () => { try { const r = await api('/api/cameras/probe', { method: 'POST', body: { ip: manual } }); await load(); setOpen(r.item); setManual(''); } catch (e) { toast(e.message, true); } };
  useEffect(() => { const ip = new URLSearchParams(location.search).get('cam') || ssGet('rl_pending_cam'); if (ip && info && !open) { const it = (info.items || []).find(x => x.ip === ip); if (it) setOpen(it); } }, [info && info.items && info.items.length]);
  if (!info) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  const pct = info.total ? Math.min(100, Math.round(info.done * 100 / info.total)) : 0;
  const mine = new Set(data.devices.map(hostOf));
  const items = info.items || [];
  const tick = ip => setSel(s => { const n = new Set(s); n.has(ip) ? n.delete(ip) : n.add(ip); return n; });
  const allOn = items.length > 0 && items.every(i => sel.has(i.ip));
  const follow = it => newDevice({ driver: 'ping', kind: 'camera', name: (it.what || '').split('·').slice(-1)[0].trim() || it.ip, fields: { host: it.ip, location: 'local', notes: [it.vendor, it.mac].filter(Boolean).join(' · ') } });
  return <>
    <button type="button" className="btn sm" onClick={onBack} style={{ marginBottom: 12 }}><Icon name="chevron" size={13} style={{ transform: 'rotate(180deg)' }} />Все инструменты</button>
    <Card>
      <div className="row between" style={{ gap: 8, alignItems: 'flex-start' }}>
        <div className="card-title" style={{ margin: 0 }}><Icon name="camera" size={15} />Камеры и видеорегистраторы</div>
        <Btn size="sm" icon="lock" onClick={() => setCredsOpen(true)}>Пароли камер · {info.creds.length}</Btn>
      </div>
      <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5, marginTop: 6 }}>Нажмите «Искать» — Rack Live сам найдёт камеры и регистраторы во всех известных сетях. Найденные можно отметить и сменить им пароль или адрес сразу всем.
        При поиске никуда не входим и ничего не меняем.</div>
      <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
        {info.running ? <Btn onClick={stop}>Остановить</Btn> : <Btn kind="primary" icon="search" onClick={start}>{info.finished ? 'Искать снова' : 'Искать камеры'}</Btn>}
        <WhereToSearch subnets={info.subnets} value={where} onChange={setWhere} disabled={info.running} />
      </div>
      {info.running ? <div style={{ marginTop: 10 }}><div className="row between" style={{ fontSize: 13, marginBottom: 6 }}><span>Ищу камеры{info.cidr ? ' · ' + info.cidr : ''}…</span><span className="dim3">{info.done} из {info.total}</span></div>
        <div className="gauge-bar" style={{ maxWidth: 'none' }}><i style={{ width: pct + '%' }} /></div></div> : null}
      {info.error ? <div style={{ color: 'var(--orange)', fontSize: 13, marginTop: 8 }}>{info.error}</div> : null}
      {!info.running && info.finished && info.cidr ? <div className="dim3" style={{ fontSize: 12, marginTop: 8 }}>Искали в: {info.cidr}{info.skipped && info.skipped.length ? '. Адреса роутеров (' + info.skipped.join(', ') + ') не проверяем: роутер принимает это за сканирование и на несколько минут закрывает доступ.' : ''}</div> : null}
    </Card>
    {recs.length ? <>
      <div className="card-title" style={{ margin: '16px 0 8px' }}><Icon name="server" size={14} />Видеорегистраторы на ваших устройствах · {recs.length}</div>
      <div className="list">{recs.map((r, i) => <div className="li netscan-row cam-row" key={i}>
        <button type="button" className="cam-main" onClick={() => setRec(r)}>
          <KindIcon kind="nas" size={36} round={10} />
          <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}>
            <div className="row" style={{ gap: 6 }}><b style={{ fontSize: 14 }} className="ellipsis">{r.name}</b><span className="found-type">Видеорегистратор</span></div>
            <div className="dim ellipsis" style={{ fontSize: 12.5 }}>на «{r.deviceName}» · {r.host}{r.version ? ' · версия ' + r.version : ''}</div>
            <div className="row wrap" style={{ gap: 5, marginTop: 3 }}>{r.error ? <span className="badge warning">{r.error}</span> : <><span className="badge online">{r.cameras.length} камер</span>{r.licences ? <span className="badge">лицензий {r.licences}</span> : null}</>}</div>
          </div><Icon name="chevron" size={14} /></button></div>)}</div></> : null}
    <div className="row between" style={{ margin: '16px 0 8px', gap: 8 }}>
      <div className="card-title" style={{ margin: 0 }}><Icon name="camera" size={14} />Найдено в сети · {items.length}</div>
      {items.length ? <button type="button" className="btn sm" onClick={() => setSel(allOn ? new Set() : new Set(items.map(i => i.ip)))}>{allOn ? 'Снять выбор' : 'Выбрать все'}</button> : null}
    </div>
    {!items.length ? <div className="dim" style={{ fontSize: 13.5 }}>{info.finished ? 'Камер не найдено. Выберите сеть камер в «Сети» (они часто в своём VLAN) или введите адрес вручную ниже.' : 'Пока ничего. Нажмите «Искать камеры».'}</div>
      : <div className="list">{items.map(it => {
        const lt = LOGIN_TEXT[it.login] || LOGIN_TEXT.unknown;
        return <div className={'li netscan-row cam-row' + (sel.has(it.ip) ? ' picked' : '')} key={it.ip}>
          <input type="checkbox" className="cam-check" checked={sel.has(it.ip)} onChange={() => tick(it.ip)} aria-label={'Выбрать ' + it.ip} />
          <button type="button" className="cam-main" onClick={() => setOpen(it)}>
            <KindIcon kind="camera" size={36} round={10} />
            <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}>
              <div className="row" style={{ gap: 6 }}><b style={{ fontSize: 14 }} className="ellipsis">{it.ip}</b><span className="found-type">{KIND_WORD[it.kind] || KIND_WORD.unknown}</span></div>
              <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{it.what}</div>
              <div className="row wrap" style={{ gap: 5, marginTop: 3 }}><span className={'badge ' + lt[1]}>{lt[0]}</span>{it.onvif ? <span className="badge">ONVIF</span> : <span className="badge warning">без ONVIF</span>}
                {it.mac ? <span className="dim3 mono" style={{ fontSize: 11 }}>{it.mac}</span> : null}{recs.some(r => r.cameras.some(c => c.ip === it.ip)) ? <span className="badge" title="Эту камеру записывает видеорегистратор">пишет {recs.find(r => r.cameras.some(c => c.ip === it.ip)).name}</span> : null}</div>
            </div><Icon name="chevron" size={14} /></button>
          {mine.has(it.ip) ? <span className="badge online hide-sm">в Rack Live</span> : <Btn size="sm" icon="plus" title="Следить, на связи ли" onClick={() => follow(it)}><span className="hide-sm">Следить</span></Btn>}
        </div>;
      })}</div>}
    <div className="row" style={{ gap: 8, marginTop: 14 }}>
      <input className="input mono grow" value={manual} onChange={e => setManual(e.target.value)} placeholder="Добавить по адресу: 192.168.7.15" onKeyDown={e => e.key === 'Enter' && manual && probe()} />
      <Btn icon="plus" disabled={!manual} onClick={probe}>Проверить адрес</Btn>
    </div>
    <button type="button" className="where-link" onClick={() => setBrandsOpen(!brandsOpen)}>Какие бренды узнаём: {info.brands.length} <Icon name="chevron" size={12} style={{ transform: brandsOpen ? 'rotate(-90deg)' : 'rotate(90deg)' }} /></button>
    {brandsOpen ? <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>{info.brands.map(b => <span key={b.name} className="found-type" title={b.family === 'hikvision' ? 'есть активация и ISAPI' : b.family === 'dahua' ? 'есть запасной путь смены пароля' : 'управление по ONVIF'}>{b.name}</span>)}
      <div className="dim3" style={{ fontSize: 12, width: '100%' }}>Управление — по стандарту ONVIF, который понимают почти все камеры. У Hikvision (и EZVIZ, HiWatch, HiLook) дополнительно есть активация новой камеры, у Dahua (и Imou, Amcrest, Lorex, RVi) — запасной путь смены пароля.</div></div> : null}
    {sel.size ? <div className="cam-bar"><span><b>{sel.size}</b> выбрано</span>
      <div className="row" style={{ gap: 8 }}><Btn size="sm" onClick={() => setSel(new Set())}>Снять</Btn><Btn size="sm" kind="primary" icon="edit" onClick={() => setBulk(true)}>Действия с выбранными</Btn></div></div> : null}
    {open ? <CameraSheet item={open} creds={info.creds} reloadCreds={load} onClose={() => { setOpen(null); load(); }} /> : null}
    {bulk ? <BulkModal items={items.filter(i => sel.has(i.ip))} creds={info.creds} onClose={() => { setBulk(false); load(); }} /> : null}
    {rec ? <RecorderModal rec={rec} found={items} onClose={() => setRec(null)} onOpenCam={ip => { const it = items.find(x => x.ip === ip); if (it) { setRec(null); setOpen(it); } }} /> : null}
    {credsOpen ? <CredsModal creds={info.creds} onChange={load} onClose={() => setCredsOpen(false)} /> : null}
  </>;
}

/* a recorder on one of your devices (Synology Surveillance Station): its cameras and their state */
function RecorderModal({ rec, found, onClose, onOpenCam }) {
  return <Modal title={rec.name} wide onClose={onClose} icon={<Icon name="server" size={20} color="var(--accent)" />}>
    <div className="row wrap" style={{ gap: 8 }}><span className="found-type">Видеорегистратор</span><span className="dim" style={{ fontSize: 13 }}>на «{rec.deviceName}» ({rec.host}){rec.version ? ' · версия ' + rec.version : ''}</span></div>
    {rec.error ? <div className="cam-warn">Не удалось прочитать список камер: {rec.error}</div> : <div className="dk-sum" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
      <div><b>{rec.cameras.length}</b><span>камер подключено</span></div><div><b>{rec.cameras.filter(c => c.status === 1).length}</b><span>работают</span></div><div><b>{rec.licences != null ? rec.licences : '—'}</b><span>лицензий (макс. {rec.max || '—'})</span></div></div>}
    <div className="list">{rec.cameras.map(c => { const f = found.find(x => x.ip === c.ip);
      return <div className="li" key={c.id}><span className={'dot ' + (c.status === 1 ? 'online' : c.status === 7 ? '' : 'offline')} />
        <div className="grow" style={{ minWidth: 0 }}><b>{c.name}</b><div className="dim mono" style={{ fontSize: 12 }}>{c.ip}{c.port ? ':' + c.port : ''} · {[c.vendor, c.model].filter(Boolean).join(' ')}</div></div>
        <span className="dim" style={{ fontSize: 12.5 }}>{c.statusText}{c.keepDays ? ' · хранит ' + c.keepDays + ' дн' : ''}</span>
        {f ? <Btn size="sm" onClick={() => onOpenCam(c.ip)}>Настроить</Btn> : null}</div>; })}</div>
    {rec.url ? <a className="btn" href={rec.url} target="_blank" rel="noopener">Открыть {rec.name}</a> : null}
    <div className="dim3" style={{ fontSize: 12 }}>Это список камер, которые видит сам регистратор. Чтобы сменить пароль или адрес камеры, нажмите «Настроить» (если Rack Live её нашёл) — но потом обновите данные камеры и в Surveillance Station.</div>
  </Modal>;
}

/* the list of saved camera passwords: the passwords themselves never come back from the server — only the login, a label and dots */
function CredsModal({ creds, onChange, onClose }) {
  const toast = useToast();
  const [u, setU] = useState('admin'); const [p, setP] = useState(''); const [l, setL] = useState('');
  const add = async () => { try { await api('/api/cameras/creds', { method: 'POST', body: { user: u, password: p, label: l } }); setP(''); setL(''); onChange(); toast('Добавлено в список'); } catch (e) { toast(e.message, true); } };
  const del = async c => { try { await api('/api/cameras/creds/' + c.id, { method: 'DELETE' }); onChange(); } catch (e) { toast(e.message, true); } };
  return <Modal title="Пароли камер" onClose={onClose} icon={<Icon name="lock" size={20} color="var(--accent)" />}>
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Список, из которого Rack Live подбирает вход в камеры: воткнули новую камеру — нажали «Войти», и он сам пробует пароли отсюда (не больше трёх за раз: камеры блокируют вход после нескольких неверных).
      Введённый вручную пароль, который подошёл, добавляется сюда сам. Пароли хранятся только на сервере Rack Live и в браузер не отдаются.</div>
    {creds.length ? <div className="list">{creds.map(c => <div className="li" key={c.id}>
      <div className="grow" style={{ minWidth: 0 }}><b>{c.user}</b> <span className="mono dim3">{c.mask}</span>{c.label ? <span className="dim" style={{ fontSize: 12.5 }}> · {c.label}</span> : null}
        <div className="dim3" style={{ fontSize: 11.5 }}>{c.cameras ? 'подошёл камерам: ' + c.cameras : 'пока не использовался'}</div></div>
      <Btn size="sm" onClick={() => del(c)}>Удалить</Btn></div>)}</div> : <div className="dim" style={{ fontSize: 13 }}>Список пуст.</div>}
    <div className="card-title" style={{ margin: '6px 0 0' }}><Icon name="plus" size={14} />Добавить</div>
    <div className="row wrap" style={{ gap: 8 }}>
      <input className="input" style={{ maxWidth: 130 }} value={u} onChange={e => setU(e.target.value)} placeholder="Логин" autoComplete="off" />
      <input className="input grow" type="password" value={p} onChange={e => setP(e.target.value)} placeholder="Пароль" autoComplete="new-password" />
      <input className="input" style={{ maxWidth: 150 }} value={l} onChange={e => setL(e.target.value)} placeholder="Метка (необяз.)" autoComplete="off" />
      <Btn kind="primary" disabled={!u || !p} onClick={add}>Добавить</Btn></div>
  </Modal>;
}

/* a login choice shared by one camera and by the group: «from the list» (all saved, or a chosen one) or typed */
function LoginChoice({ creds, v, set }) {
  return <div className="col" style={{ gap: 8 }}>
    <Seg value={v.mode} onChange={m => set({ ...v, mode: m })} options={[{ value: 'list', label: 'Из списка паролей' }, { value: 'manual', label: 'Ввести' }]} />
    {v.mode === 'list'
      ? <select className="input" value={v.credId} onChange={e => set({ ...v, credId: e.target.value, offset: 0 })}>
        <option value="">Автоматически — пробую сохранённые</option>
        {creds.map(c => <option key={c.id} value={c.id}>{c.user} · {c.mask}{c.label ? ' · ' + c.label : ''}</option>)}</select>
      : <div className="col" style={{ gap: 8 }}><div className="row" style={{ gap: 8 }}>
        <input className="input" style={{ maxWidth: 150 }} value={v.user} onChange={e => set({ ...v, user: e.target.value })} placeholder="Логин" autoComplete="off" />
        <input className="input grow" type="password" value={v.pw} onChange={e => set({ ...v, pw: e.target.value })} placeholder="Пароль" autoComplete="off" /></div>
        <label className="row" style={{ gap: 8, fontSize: 13 }}><input type="checkbox" checked={v.remember} onChange={e => set({ ...v, remember: e.target.checked })} />Запомнить в списке паролей</label></div>}
  </div>;
}
const loginBody = v => v.mode === 'manual' ? { user: v.user, password: v.pw, remember: v.remember } : v.credId ? { credId: v.credId } : { offset: v.offset || 0 };

function CameraSheet({ item, creds, reloadCreds, onClose }) {
  const [ip, setIp] = useState(item.ip);
  const [lg, setLg] = useState({ mode: creds.length ? 'list' : 'manual', credId: '', offset: 0, user: 'admin', pw: '', remember: true });
  const [auth, setAuth] = useState(null);                // what the next calls use: {credId} or {user, password}
  const [ses, setSes] = useState(null);                  // what login returned
  const [busy, setBusy] = useState('');
  const [msg, setMsg] = useState(null);                  // {ok, text, more}
  const [tab, setTab] = useState('shot');
  const [act, setAct] = useState('');                    // first password for an inactive camera
  const call = async (op, extra = {}, label = 'Работаю…', who) => {
    setBusy(label); setMsg(null);
    try { return await api('/api/cameras/op', { method: 'POST', body: { op, ip, port: ses && ses.port, ...(who || auth || {}), ...extra } }); }
    catch (e) { setMsg({ ok: false, text: e.message, more: /следующие/.test(e.message) }); return null; } finally { setBusy(''); }
  };
  const login = async offset => {
    const body = { ...loginBody(lg), ...(offset != null ? { offset } : {}) };
    const r = await call('login', {}, 'Вхожу…', body);
    if (r) { setSes(r); setAuth(r.credId ? { credId: r.credId } : { user: body.user, password: body.password }); reloadCreds(); }
  };
  const activate = async () => {
    const r = await call('activate', { password: act }, 'Активирую…', {});
    if (r) { setMsg({ ok: true, text: r.message }); setLg({ ...lg, mode: 'list', credId: r.credId || '' }); reloadCreds(); }
  };
  // ?camlogin=admin:pass&camtab=net — opens the camera already signed in (for tests / screenshots of the demo)
  useEffect(() => {
    const q = new URLSearchParams(location.search); const a = q.get('camlogin'); if (!a) return;
    const [u, p] = a.split(':');
    api('/api/cameras/op', { method: 'POST', body: { op: 'login', ip: item.ip, user: u, password: p } }).then(r => { setSes(r); setAuth(r.credId ? { credId: r.credId } : { user: u, password: p }); if (q.get('camtab')) setTab(q.get('camtab')); reloadCreds(); }).catch(e => setMsg({ ok: false, text: e.message }));
  }, []);
  const kind = (ses && ses.kind) || item.kind;
  return <Modal title={ip} wide onClose={onClose} icon={<Icon name="camera" size={20} color="var(--accent)" />}>
    <div className="row wrap" style={{ gap: 8 }}><span className="found-type">{KIND_WORD[kind] || KIND_WORD.unknown}</span>{item.vendor ? <span className="found-type">{item.vendor}</span> : null}
      <span className="dim" style={{ fontSize: 13 }}>{ses ? [ses.info.manufacturer, ses.info.model].filter(Boolean).join(' ') : item.what}</span></div>
    {item.login === 'open' && !ses ? <div className="cam-warn">Видеопоток этой камеры открыт без пароля — любой в сети может его смотреть. Войдите и задайте пароль.</div> : null}
    {!ses && item.login === 'inactive' ? <div className="card cam-box">
      <b>Камера не активирована</b>
      <div className="dim" style={{ fontSize: 13, margin: '4px 0 8px', lineHeight: 1.45 }}>У новой камеры нет пароля. Придумайте его (не меньше 8 знаков, буквы и цифры) — это будет пароль пользователя admin, он сохранится в список.
        {item.family === 'hikvision' ? ' Работает на камерах Hikvision и их «родственниках»; если не получится — ' : ' У этого производителя первый пароль задаётся так: '}{item.tip || 'программой производителя'}.</div>
      <div className="row" style={{ gap: 8 }}><input className="input grow" type="text" value={act} onChange={e => setAct(e.target.value)} placeholder="Новый пароль" autoComplete="off" />
        <Btn size="sm" onClick={() => setAct(genPassword())}>Придумать</Btn>
        <Btn kind="primary" disabled={!!busy || act.length < 8 || item.family !== 'hikvision'} onClick={activate}>Активировать</Btn></div>
    </div> : null}
    {!ses ? <div className="card cam-box">
      <b>Вход в камеру</b>
      <div className="dim" style={{ fontSize: 12.5, margin: '3px 0 8px' }}>Rack Live подберёт пароль из вашего списка. Не подошёл ни один — введите свой, он тоже сохранится.</div>
      <LoginChoice creds={creds} v={lg} set={setLg} />
      <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
        <Btn kind="primary" disabled={!!busy || (lg.mode === 'manual' && (!lg.user || !lg.pw)) || (lg.mode === 'list' && !creds.length)} onClick={() => login()}>Войти</Btn>
        {msg && msg.more ? <Btn onClick={() => { const o = (lg.offset || 0) + 3; setLg({ ...lg, offset: o }); login(o); }}>Пробовать следующие</Btn> : null}
        {msg && !msg.ok && lg.mode === 'list' ? <Btn onClick={() => setLg({ ...lg, mode: 'manual' })}>Ввести свой пароль</Btn> : null}
        {lg.mode === 'list' && !creds.length ? <span className="dim" style={{ fontSize: 12.5 }}>Список паролей пуст — переключитесь на «Ввести».</span> : null}
      </div>
    </div> : <>
      <div className="card cam-box"><div className="kv"><span>Модель</span><b>{ses.info.model || '—'}</b></div><div className="kv"><span>Производитель</span><b>{ses.info.manufacturer || '—'}</b></div>
        <div className="kv"><span>Прошивка</span><b className="mono">{ses.info.firmware || '—'}</b></div><div className="kv"><span>Серийный номер</span><b className="mono">{ses.info.serial || '—'}</b></div>
        <div className="kv"><span>Видеоканалов</span><b>{ses.channels || '—'}{ses.channels > 1 ? ' — это регистратор' : ''}</b></div><div className="kv"><span>MAC</span><b className="mono">{ses.net.mac || '—'}</b></div></div>
      <Seg value={tab} onChange={setTab} options={[{ value: 'shot', label: 'Кадр' }, { value: 'net', label: 'Сеть' }, { value: 'users', label: 'Доступ' }]} />
      {tab === 'shot' ? <ShotPane call={call} busy={busy} /> : null}
      {tab === 'net' ? <NetPane ses={ses} ip={ip} call={call} busy={busy} setMsg={setMsg} onMoved={n => { setIp(n); setSes(null); setLg({ ...lg, mode: auth && auth.credId ? 'list' : 'manual', credId: (auth && auth.credId) || '' }); }} /> : null}
      {tab === 'users' ? <UsersPane ses={ses} call={call} busy={busy} setMsg={setMsg} onCred={cid => { if (cid) setAuth({ credId: cid }); reloadCreds(); }} /> : null}
    </>}
    {busy ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />{busy}</div> : null}
    {msg ? <div className={msg.ok ? 'cam-ok' : 'cam-err'}>{msg.text}</div> : null}
  </Modal>;
}

function ShotPane({ call, busy }) {
  const [r, setR] = useState(null);
  const go = async () => { const x = await call('snapshot', {}, 'Запрашиваю кадр…'); if (x) setR(x); };
  const toast = useToast();
  return <div className="col" style={{ gap: 10 }}>
    <Btn icon="camera" disabled={!!busy} onClick={go}>{r ? 'Обновить кадр' : 'Показать кадр'}</Btn>
    {r && r.image ? <img className="cam-shot" src={r.image} alt="кадр с камеры" /> : null}
    {r && r.rtsp ? <div className="col" style={{ gap: 6 }}>
      <div className="dim" style={{ fontSize: 12.5 }}>Адрес потока для VLC, Frigate, регистратора (RTSP):</div>
      <div className="row" style={{ gap: 6 }}><input className="input mono grow" readOnly value={r.rtsp} onFocus={e => e.target.select()} />
        <Btn size="sm" icon="copy" onClick={() => toast(copyText(r.rtsp) ? 'Скопировано' : 'Не удалось скопировать — выделите и скопируйте вручную')}>Копировать</Btn></div>
      <Btn size="sm" onClick={() => toast(copyText(r.rtspAuth) ? 'Скопировано вместе с логином и паролем' : 'Не удалось скопировать')}>Копировать с логином и паролем</Btn></div> : null}
  </div>;
}

function NetPane({ ses, ip, call, busy, setMsg, onMoved }) {
  const n = ses.net;
  const [mode, setMode] = useState(n.dhcp ? 'dhcp' : 'static');
  const [addr, setAddr] = useState(n.ip || ip); const [prefix, setPrefix] = useState(String(n.prefix || 24)); const [gw, setGw] = useState(n.gateway || '');
  const [sure, setSure] = useState(false);
  const go = async () => {
    const r = await call('set_ip', mode === 'dhcp' ? { mode: 'dhcp' } : { mode: 'static', address: addr, prefix: +prefix, gateway: gw }, 'Меняю адрес…');
    setSure(false);
    if (!r) return;
    setMsg({ ok: true, text: r.message });
    if (r.ip && r.ip !== ip) onMoved(r.ip);
  };
  const changes = mode === 'dhcp' || addr !== ip;
  return <div className="col" style={{ gap: 10 }}>
    <div className="dim" style={{ fontSize: 13 }}>Сейчас: <b>{n.dhcp ? 'адрес по DHCP' : 'постоянный адрес'}</b> {n.ip} /{n.prefix}{n.gateway ? ', шлюз ' + n.gateway : ''}</div>
    <Seg value={mode} onChange={m => { setMode(m); setSure(false); }} options={[{ value: 'static', label: 'Постоянный адрес' }, { value: 'dhcp', label: 'DHCP (от роутера)' }]} />
    {mode === 'static' ? <div className="row wrap" style={{ gap: 8 }}>
      <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Адрес</span><input className="input mono" value={addr} onChange={e => { setAddr(e.target.value); setSure(false); }} /></label>
      <label className="col" style={{ gap: 3, width: 80 }}><span className="dim3" style={{ fontSize: 11.5 }}>Маска /</span><input className="input mono" value={prefix} onChange={e => setPrefix(e.target.value)} /></label>
      <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Шлюз (роутер)</span><input className="input mono" value={gw} onChange={e => setGw(e.target.value)} /></label></div>
      : <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.45 }}>Камера сама получит адрес от роутера. Чтобы он не менялся, потом закрепите его за камерой в настройках клиента на роутере (Rack Live → Клиенты → «Постоянный IP»).</div>}
    {!sure ? <Btn kind="primary" disabled={!!busy || !changes} onClick={() => setSure(true)}>{mode === 'dhcp' ? 'Включить DHCP' : 'Сменить адрес'}</Btn>
      : <div className="cam-warn">Связь с камерой по адресу {ip} <b>пропадёт</b>{mode === 'static' ? ': она сразу перейдёт на ' + addr : ' и вернётся уже по новому адресу из пула роутера'}.
        Если адрес или шлюз неверны, камеру придётся искать заново (или сбрасывать). Продолжить?
        <div className="row" style={{ gap: 8, marginTop: 8 }}><Btn kind="primary" disabled={!!busy} onClick={go}>Да, менять</Btn><Btn onClick={() => setSure(false)}>Отмена</Btn></div></div>}
  </div>;
}

function UsersPane({ ses, call, busy, setMsg, onCred }) {
  const [edit, setEdit] = useState(null); const [np, setNp] = useState('');
  const [nu, setNu] = useState(''); const [nup, setNup] = useState('');
  const change = async u => { const r = await call('set_password', { ...(u ? { target: u } : {}), new: np }, 'Меняю пароль…'); if (r) { setMsg({ ok: true, text: r.message }); setEdit(null); setNp(''); onCred(r.credId); } };
  const create = async () => { const r = await call('create_user', { name: nu, new: nup }, 'Создаю…'); if (r) { setMsg({ ok: true, text: r.message }); setNu(''); setNup(''); } };
  return <div className="col" style={{ gap: 10 }}>
    <div className="dim" style={{ fontSize: 13 }}>Пользователи камеры. Пароль лучше сделать длинным (8+ знаков, буквы и цифры) и разным для разных камер. Новый пароль сразу запоминается в списке паролей.</div>
    {ses.users.length ? <div className="list">{ses.users.map(u => <div className="li" key={u.name}>
      <div className="grow"><b>{u.name}</b> <span className="dim3" style={{ fontSize: 12 }}>{u.level}</span></div>
      {edit === u.name ? <div className="row" style={{ gap: 6 }}><input className="input" type="text" value={np} onChange={e => setNp(e.target.value)} placeholder="Новый пароль" autoComplete="off" style={{ width: 150 }} />
        <Btn size="sm" onClick={() => setNp(genPassword())}>Придумать</Btn>
        <Btn size="sm" kind="primary" disabled={!!busy || np.length < 6} onClick={() => change(u.name)}>Сменить</Btn><Btn size="sm" onClick={() => setEdit(null)}>×</Btn></div>
        : <Btn size="sm" onClick={() => { setEdit(u.name); setNp(''); }}>Сменить пароль</Btn>}</div>)}</div>
      : <div className="row" style={{ gap: 6 }}><input className="input grow" type="text" value={np} onChange={e => setNp(e.target.value)} placeholder="Новый пароль для вашего пользователя" autoComplete="off" /><Btn size="sm" onClick={() => setNp(genPassword())}>Придумать</Btn>
        <Btn size="sm" kind="primary" disabled={!!busy || np.length < 6} onClick={() => change(null)}>Сменить</Btn></div>}
    <div className="card-title" style={{ margin: '6px 0 0' }}><Icon name="plus" size={14} />Новый пользователь</div>
    <div className="row wrap" style={{ gap: 8 }}><input className="input" style={{ maxWidth: 160 }} value={nu} onChange={e => setNu(e.target.value)} placeholder="Логин" autoComplete="off" />
      <input className="input grow" type="text" value={nup} onChange={e => setNup(e.target.value)} placeholder="Пароль" autoComplete="off" />
      <Btn disabled={!!busy || !nu || nup.length < 6} onClick={create}>Создать</Btn></div>
    <div className="dim3" style={{ fontSize: 12 }}>Создаётся пользователь с обычными правами (смотреть). Права администратора выдаются в самой камере.</div>
  </div>;
}

/* ───────── several cameras at once ───────── */
function BulkModal({ items, creds, onClose }) {
  const toast = useToast();
  const [action, setAction] = useState('set_password');
  const [lg, setLg] = useState({ mode: creds.length ? 'list' : 'manual', credId: '', offset: 0, user: 'admin', pw: '', remember: true });
  const [np, setNp] = useState(''); const [target, setTarget] = useState('');
  const [ipMode, setIpMode] = useState('dhcp'); const [start, setStart] = useState(''); const [prefix, setPrefix] = useState('24'); const [gw, setGw] = useState('');
  const [nu, setNu] = useState(''); const [nup, setNup] = useState('');
  const [sure, setSure] = useState(false);
  const [job, setJob] = useState(null);
  const ips = items.map(i => i.ip);
  const body = () => ({ ips, action, ...loginBody(lg), ...(action === 'set_password' ? { new: np, ...(target ? { target } : {}) } : action === 'create_user' ? { name: nu, new: nup }
    : ipMode === 'dhcp' ? { mode: 'dhcp' } : { mode: 'static', address: start, prefix: +prefix, gateway: gw }) });
  const run = async () => {
    try { const r = await api('/api/cameras/bulk', { method: 'POST', body: body() }); setJob({ id: r.job, total: ips.length, done: 0, results: [], finished: false }); setSure(false); }
    catch (e) { toast(e.message, true); setSure(false); }
  };
  useEffect(() => {
    if (!job || job.finished) return;
    const t = setInterval(async () => { try { const j = await api('/api/cameras/bulk/' + job.id); setJob(o => ({ ...j, id: o.id })); } catch (e) { } }, 900);
    return () => clearInterval(t);
  }, [job && job.id, job && job.finished]);
  const ready = action === 'set_password' ? np.length >= 6 : action === 'create_user' ? nu && nup.length >= 6 : ipMode === 'dhcp' || /^\d+\.\d+\.\d+\.\d+$/.test(start);
  const loginOk = lg.mode === 'list' ? creds.length > 0 : lg.user && lg.pw;
  const okN = job ? job.results.filter(r => r.ok).length : 0;
  const verb = { set_password: 'сменить пароль', set_ip: ipMode === 'dhcp' ? 'включить DHCP' : 'задать постоянные адреса', create_user: 'создать пользователя' }[action];
  return <Modal title={`Действия с камерами · ${ips.length}`} wide onClose={onClose} icon={<Icon name="camera" size={20} color="var(--accent)" />}>
    {!job ? <>
      <div className="row wrap" style={{ gap: 6 }}>{ips.slice(0, 12).map(i => <span key={i} className="found-type mono">{i}</span>)}{ips.length > 12 ? <span className="dim3">и ещё {ips.length - 12}</span> : null}</div>
      <Seg value={action} onChange={a => { setAction(a); setSure(false); }} options={[{ value: 'set_password', label: 'Пароль' }, { value: 'set_ip', label: 'Адрес' }, { value: 'create_user', label: 'Новый пользователь' }]} />
      <div className="card cam-box"><b>Как входить в камеры</b><div className="dim" style={{ fontSize: 12.5, margin: '3px 0 8px' }}>Автоматически — Rack Live пробует для каждой камеры сохранённые пароли (её собственный — первым).</div>
        <LoginChoice creds={creds} v={lg} set={setLg} /></div>
      {action === 'set_password' ? <div className="col" style={{ gap: 8 }}>
        <div className="row" style={{ gap: 8 }}><input className="input grow" type="text" value={np} onChange={e => { setNp(e.target.value); setSure(false); }} placeholder="Один новый пароль для всех" autoComplete="off" /><Btn onClick={() => setNp(genPassword())}>Придумать</Btn></div>
        <input className="input" style={{ maxWidth: 240 }} value={target} onChange={e => setTarget(e.target.value)} placeholder="Чей пароль (пусто — того, под кем вошли)" autoComplete="off" />
        <div className="dim3" style={{ fontSize: 12 }}>Не меньше 6 знаков, без знаков &lt; &gt; &amp; " ' . Если нужны разные пароли — меняйте по одной камере (кнопка в её окне).</div></div> : null}
      {action === 'set_ip' ? <div className="col" style={{ gap: 8 }}>
        <Seg value={ipMode} onChange={m => { setIpMode(m); setSure(false); }} options={[{ value: 'dhcp', label: 'DHCP (от роутера)' }, { value: 'static', label: 'Постоянные адреса подряд' }]} />
        {ipMode === 'static' ? <div className="row wrap" style={{ gap: 8 }}>
          <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Первой камере</span><input className="input mono" value={start} onChange={e => { setStart(e.target.value); setSure(false); }} placeholder="192.168.7.20" /></label>
          <label className="col" style={{ gap: 3, width: 80 }}><span className="dim3" style={{ fontSize: 11.5 }}>Маска /</span><input className="input mono" value={prefix} onChange={e => setPrefix(e.target.value)} /></label>
          <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Шлюз (роутер)</span><input className="input mono" value={gw} onChange={e => setGw(e.target.value)} placeholder="192.168.7.1" /></label>
          <div className="dim3" style={{ fontSize: 12, width: '100%' }}>Остальные получат следующие адреса по порядку; занятые Rack Live пропустит.</div></div>
          : <div className="dim" style={{ fontSize: 12.5 }}>Камеры сами возьмут адреса от роутера и исчезнут со старых. Новые адреса — в списке клиентов роутера (по MAC).</div>}</div> : null}
      {action === 'create_user' ? <div className="row wrap" style={{ gap: 8 }}><input className="input" style={{ maxWidth: 160 }} value={nu} onChange={e => setNu(e.target.value)} placeholder="Логин" autoComplete="off" />
        <input className="input grow" type="text" value={nup} onChange={e => setNup(e.target.value)} placeholder="Пароль" autoComplete="off" /></div> : null}
      {!sure ? <Btn kind="primary" disabled={!ready || !loginOk} onClick={() => setSure(true)}>Дальше</Btn>
        : <div className="cam-warn">Вы собираетесь <b>{verb}</b> у {ips.length} камер{action === 'set_ip' ? '. Связь с ними по старым адресам пропадёт; если адрес или шлюз неверны, камеры придётся искать заново' : ''}. Продолжить?
          <div className="row" style={{ gap: 8, marginTop: 8 }}><Btn kind="primary" onClick={run}>Да, применить</Btn><Btn onClick={() => setSure(false)}>Отмена</Btn></div></div>}
    </> : <>
      <div><div className="row between" style={{ fontSize: 13, marginBottom: 6 }}><span>{job.finished ? 'Готово' : 'Работаю…'}</span><span className="dim3">{job.done} из {job.total} · успешно {okN}</span></div>
        <div className="gauge-bar" style={{ maxWidth: 'none' }}><i style={{ width: Math.round(job.done * 100 / Math.max(1, job.total)) + '%' }} /></div></div>
      <div className="list">{job.results.map(r => <div className="li" key={r.ip}>
        <span className={'badge ' + (r.ok ? 'online' : 'offline')}>{r.ok ? 'готово' : 'не вышло'}</span>
        <div className="grow" style={{ minWidth: 0 }}><b className="mono">{r.ip}{r.newIp ? ' → ' + r.newIp : ''}</b><div className="dim" style={{ fontSize: 12.5 }}>{r.message}</div></div></div>)}</div>
      {job.finished && action === 'set_password' && np ? <Btn size="sm" icon="copy" onClick={() => toast(copyText(np) ? 'Новый пароль скопирован' : 'Не удалось скопировать')}>Копировать новый пароль</Btn> : null}
      {job.finished ? <Btn kind="primary" onClick={onClose}>Закрыть</Btn> : null}
    </>}
  </Modal>;
}
