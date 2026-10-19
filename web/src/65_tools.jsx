/* Tab «Инструменты»: one list of sections — like Настройки (coloured icon, name, live status, chevron).
   «Устройства» and «Плагины» are built in; every helper (cameras, remote sites, community tools) is its own row too.
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
  { id: 'sites', title: 'Удалённые площадки и агенты', icon: 'globe2', color: '#5e5ce6',
    text: 'Следить за другой сетью без белого IP и проброса портов: офис, дача, квартира родителей. Там ставится свой Rack Live (сборщик) или маленький агент — данные приходят сюда сами.' },
];
const TOOLS_BASE = [
  { id: 'devices', label: () => T('tab.devices', 'Устройства'), icon: 'list', color: '#8e8e93', desc: 'Все устройства в сети, поиск и фильтр' },
  { id: 'plugins', label: () => 'Плагины', icon: 'box', color: '#0a84ff', desc: 'Установка дополнений: роутер, OpenWrt, сервер, NAS' },
];
const TOOLS_GROUPS = [['devices', 'plugins'], ['tools']];           // «tools» stands for every TOOLS.* / community row, in order
const COMMUNITY_COLORS = ['#0a84ff', '#30b0c7', '#34c759', '#ff9f0a', '#bf5af2', '#ff375f'];

/* open an instrument from anywhere: the Tools tab → the tool (and a camera's address to pick in it) */
function openToolById(ctx, id, cam) {
  try { sessionStorage.setItem('rl_pending_tool', id); if (cam) sessionStorage.setItem('rl_pending_cam', cam); } catch (e) { }
  ctx.setTab('tools');
  setTimeout(() => window.dispatchEvent(new CustomEvent('rl-open-tool', { detail: id })), 120);
}

const ADD_SEC = { id: 'add', label: () => 'Свой инструмент или из каталога', icon: 'plus', color: '#8e8e93', desc: 'Загрузить .zip или взять из каталога сообщества' };

function ToolsView() {
  const [mine, setMine] = useState([]);              // community tools (uploaded or from the catalog)
  const loadMine = () => api('/api/community').then(r => setMine(r.plugins.filter(p => p.kind === 'tool'))).catch(() => { });
  useEffect(() => { loadMine(); }, []);
  const toolRows = [...TOOLS.map(t => ({ id: t.id, label: () => t.title, icon: t.icon, color: t.color, desc: t.text })),
    ...mine.map((t, i) => ({ id: 'x-' + t.id, label: () => t.title, icon: t.icon || 'wrench', color: COMMUNITY_COLORS[i % COMMUNITY_COLORS.length], desc: t.description, tag: t.source === 'community' ? 'сообщество' : 'своё' }))];
  const secs = [...TOOLS_BASE, ...toolRows, ADD_SEC];
  const phone = useMedia('(max-width: 900px)');
  const pendingTool = () => { const q = new URLSearchParams(location.search).get('tsec') || ssGet('rl_pending_tool'); try { sessionStorage.removeItem('rl_pending_tool'); } catch (e) { } return q || ''; };
  const [sec, setSec] = useState(() => pendingTool() || 'devices');
  const [open, setOpen] = useState(() => pendingTool() || null);
  const pick = id => {
    if (phone) { setOpen(id); try { history.pushState({ rltool: id }, ''); } catch (e) { } window.scrollTo({ top: 0 }); return; }
    setSec(id); window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const back = () => { if (history.state && history.state.rltool) history.back(); else setOpen(null); window.scrollTo({ top: 0 }); };
  useEffect(() => { const h = e => pick(e.detail); window.addEventListener('rl-open-tool', h); return () => window.removeEventListener('rl-open-tool', h); }, [phone]);     // «open the cameras tool» from elsewhere (the scan window, a client's card)
  useEffect(() => { const h = e => setOpen(e.state && e.state.rltool ? e.state.rltool : null); window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h); }, []);
  useEffect(() => { document.documentElement.classList.toggle('set-detail', !!(phone && open)); return () => document.documentElement.classList.remove('set-detail'); }, [phone, open]);
  const cur = secs.find(x => x.id === (phone ? open : sec)) || secs[0];
  const listMode = phone && !open;
  const content = cur.id === 'devices' ? <DevicesView /> : cur.id === 'plugins' ? <PluginsOverview /> : cur.id === 'cameras' ? <CameraTool /> : cur.id === 'sites' ? <SitesTool /> : cur.id === 'add' ? <CommunityToolsView onChange={loadMine} /> : String(cur.id).startsWith('x-') ? <CommunityTool id={cur.id.slice(2)} /> : null;
  return <div className={'set-layout' + (phone ? ' ios' : '')}>
    {listMode ? <div className="ios-list">{TOOLS_GROUPS.map((g, gi) => { const items = g[0] === 'tools' ? toolRows : g.map(id => secs.find(x => x.id === id)).filter(Boolean); if (!items.length) return null;
      return <div className="ios-group" key={gi}>{items.map(x => <button type="button" key={x.id} className="ios-cell" onClick={() => pick(x.id)}>
        <span className="ios-ico"><span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={18} color="#fff" stroke={2} /></span></span>
        <span className="ios-label">{x.label()}</span>{x.tag ? <span className="badge">{x.tag}</span> : null}
        <Icon name="chevron" size={15} color="var(--text3)" stroke={2.4} /></button>)}
        {gi === TOOLS_GROUPS.length - 1 ? <button type="button" className="ios-cell" onClick={() => pick('add')}>
          <span className="ios-ico"><span className="set-ic" style={{ background: 'var(--fill)' }}><Icon name="plus" size={18} /></span></span>
          <span className="ios-label">Свой инструмент или из каталога</span><Icon name="chevron" size={15} color="var(--text3)" stroke={2.4} /></button> : null}
      </div>; })}</div> : null}
    {!phone ? <nav className="set-nav">{TOOLS_BASE.map(x => <button key={x.id} type="button" className={'set-item' + (x.id === cur.id ? ' on' : '')} onClick={() => pick(x.id)}>
        <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>
        <span className="set-txt"><b>{x.label()}</b><small>{x.desc}</small></span><Icon name="chevron" size={14} color="var(--text3)" /></button>)}
      <div className="set-nav-sep" />
      {toolRows.map(x => <button key={x.id} type="button" className={'set-item' + (x.id === cur.id ? ' on' : '')} onClick={() => pick(x.id)}>
        <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>
        <span className="set-txt"><b>{x.label()}</b><small>{x.desc}</small></span><Icon name="chevron" size={14} color="var(--text3)" /></button>)}
      <button type="button" className="set-item" onClick={() => pick('add')}>
        <span className="set-ic" style={{ background: 'var(--fill)' }}><Icon name="plus" size={16} /></span>
        <span className="set-txt"><b>Свой инструмент или из каталога</b><small>Загрузить .zip или взять из каталога сообщества</small></span></button>
    </nav> : null}
    <div className={'set-body' + (listMode ? ' ios-hidden' : phone ? ' ios-push' : '')} key={phone ? 'p' + cur.id : 'd' + cur.id}>
      {phone ? <div className="ios-nav"><button type="button" className="ios-back" onClick={back}><Icon name="chevron" size={20} stroke={2.6} style={{ transform: 'rotate(180deg)' }} />Инструменты</button><b className="ios-title">{cur.label()}</b><span /></div>
        : <div className="set-head"><b>{cur.label()}</b><span>{cur.desc}</span></div>}
      {content}
    </div>
  </div>;
}

/* ───────── «where to look»: automatic by default; a small button opens the choice of networks ───────── */
function WhereToSearch({ subnets, value, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const [own, setOwn] = useState('');
  const [align, setAlign] = useState('left');          // the popup can go off the right edge on a phone — flip it to the right-anchored variant when there is no room
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('pointerdown', h); return () => document.removeEventListener('pointerdown', h);
  }, [open]);
  useLayoutEffect(() => {
    if (!open || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const popW = Math.min(380, window.innerWidth - 32);
    setAlign(r.left + popW > window.innerWidth - 16 ? 'right' : 'left');
  }, [open]);
  const auto = !value.length;
  const known = new Set(subnets.map(s => s.cidr));
  const toggle = c => onChange(value.includes(c) ? value.filter(x => x !== c) : [...value, c]);
  const okOwn = /^\d+\.\d+\.\d+\.\d+\/\d+$/.test(own.trim());
  const add = () => { const c = own.trim(); if (okOwn && !value.includes(c)) { onChange([...value, c]); setOwn(''); } };
  return <div className="where" ref={ref}>
    <button type="button" className="btn sm where-btn" disabled={disabled} onClick={() => setOpen(!open)}>
      <Icon name="map" size={14} />{auto ? 'Сети: автоматически' : 'Сети: ' + (value.length === 1 ? value[0] : value.length + ' выбрано')}<Icon name="chevron" size={12} style={{ transform: open ? 'rotate(-90deg)' : 'rotate(90deg)' }} /></button>
    {open ? <div className={'where-pop card' + (align === 'right' ? ' right' : '')}>
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

/* ───────── plugins: by plugin, then pick the device ───────── */
function PluginsOverview() {
  const { data } = useApp(); const toast = useToast();
  const [cat, setCat] = useState(null);
  const [comm, setComm] = useState(() => new URLSearchParams(location.search).get('community') === '1');      // ?community=1 opens the manager
  useEffect(() => { api('/api/plugins/catalog').then(r => setCat(r.plugins)).catch(e => toast(e.message, true)); }, []);
  if (!cat) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  return <>
    <Hint id="tools-plugins3">Выберите плагин — потом выберите, на каком устройстве его сделать. Если нужного роутера ещё нет в Rack Live, нажмите «Найти в сети» — Rack Live просканирует сеть и покажет подходящие.</Hint>
    <CommunityCard reloadCat={() => api('/api/plugins/catalog').then(r => setCat(r.plugins)).catch(() => { })} />
    {comm ? <CommunityManager onClose={() => { setComm(false); api('/api/plugins/catalog').then(r => setCat(r.plugins)).catch(() => { }); }} /> : null}
    {PLUGIN_GROUPS.map(g => {
      const gp = cat.filter(p => (p.drivers || []).includes(realDriver(g)) && !String(p.id).startsWith('x-'));
      if (!gp.length) return null;
      const gDevs = data.devices.filter(d => g.drivers.includes(d.driver));
      const normal = gp.filter(p => !p.experimental), exp = gp.filter(p => p.experimental);
      return <div key={g.id} style={{ marginBottom: 16 }}>
        <div className="card-title" style={{ margin: '4px 2px 8px' }}><Icon name={g.icon} size={14} />{g.title}
          <span className="dim3" style={{ fontWeight: 500, textTransform: 'none', letterSpacing: 0 }}>· {gDevs.length ? `устройств: ${gDevs.length}` : 'устройств этого типа нет'}</span></div>
        <div className="col" style={{ gap: 10 }}>{normal.map(p => <PluginRow key={p.id} p={p} g={g} devs={gDevs} />)}</div>
        {exp.length ? <>
          <div className="card-title" style={{ margin: '14px 2px 8px', color: 'var(--orange)' }}><Icon name="bulb" size={14} />Экспериментальные</div>
          <div className="col" style={{ gap: 10 }}>{exp.map(p => <PluginRow key={p.id} p={p} g={g} devs={gDevs} exp />)}</div>
        </> : null}
      </div>;
    })}
  </>;
}

/* shared body for community plugins / tools: description, blue upload + hints, GitHub catalog, the installed list.
   kind = 'plugin' | 'tool' — filters the catalog and the installed list, and picks the wording. */
function CommunityBody({ kind, onChange }) {
  const toast = useToast(); const confirm = useConfirm();
  const isTool = kind === 'tool';
  const noun = isTool ? 'инструмент' : 'плагин';
  const [busy, setBusy] = useState('');
  const [rep, setRep] = useState(null);
  const [mine, setMine] = useState(null);
  const [idx, setIdx] = useState(null);
  const [catOpen, setCatOpen] = useState(false);
  const fileRef = useRef(null);
  const ofKind = arr => (arr || []).filter(p => (isTool ? p.kind === 'tool' : (p.kind || 'plugin') !== 'tool'));
  const loadMine = () => api('/api/community').then(r => setMine(ofKind(r.plugins))).catch(() => setMine([]));
  useEffect(() => { loadMine(); }, []);
  const loadIdx = (refresh) => { setIdx({}); api('/api/community/index' + (refresh ? '?refresh=1' : '')).then(r => setIdx({ ...r, plugins: ofKind(r.plugins) })).catch(e => setIdx({ ok: false, plugins: [], error: e.message })); };
  const showCatalog = () => { const n = !catOpen; setCatOpen(n); if (n && (!idx || !idx.plugins)) loadIdx(); };
  const changed = () => { loadMine(); if (onChange) onChange(); };
  const upload = async f => {
    if (!f) return; setBusy('upload'); setRep(null);
    try {
      const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: f };
      const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
      const r = await fetch('/api/community/upload', init); const j = await r.json();
      if (!r.ok && !j.errors) throw new Error(j.error || 'ошибка ' + r.status);
      setRep(j); if (j.ok) { toast('Добавлено: ' + j.name); changed(); }
    } catch (e) { toast(e.message, true); } finally { setBusy(''); if (fileRef.current) fileRef.current.value = ''; }
  };
  const install = async p => {
    setBusy(p.id); setRep(null);
    try { const r = await api('/api/community/install', { method: 'POST', body: { id: p.id } }); setRep(r); if (r.ok) { toast('Добавлено'); changed(); loadIdx(); } }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const remove = async p => {
    if (!(await confirm(`Убрать «${p.title}» из Rack Live? На устройствах он не удаляется — только пропадает из списка.`, { danger: true, ok: 'Убрать' }))) return;
    try { await api('/api/community/' + p.id, { method: 'DELETE' }); changed(); loadIdx(); } catch (e) { toast(e.message, true); }
  };
  return <>
    <div className="dim" style={{ fontSize: 12.8, lineHeight: 1.45, margin: '0 0 10px' }}>{isTool
      ? 'Инструменты от других пользователей (разовый запуск на устройстве: отчёт, проверка, настройка). Можно загрузить свой из файла .zip или взять из каталога на GitHub.'
      : 'Плагины от других пользователей. Можно загрузить свой из файла .zip или взять из каталога на GitHub.'} Это только данные (без программ):
      Rack Live проверяет каждый архив, а запускается он лишь после того, как вы выберете устройство, прочитаете команды и подтвердите.</div>
    <input ref={fileRef} type="file" accept=".zip,application/zip" style={{ display: 'none' }} onChange={e => upload(e.target.files[0])} />
    <div className="row wrap" style={{ gap: 8 }}>
      <Btn kind="primary" icon="plus" busy={busy === 'upload'} onClick={() => fileRef.current && fileRef.current.click()}>Загрузить .zip</Btn>
      <Btn icon={catOpen ? 'chevron' : 'list'} onClick={showCatalog}>Каталог сообщества (GitHub)</Btn>
    </div>
    <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
      <a className="btn" href={'/api/community/guide.txt' + (isTool ? '?kind=tool' : '')} download><Icon name="file" size={15} />Инструкция для нейросети</a>
      <a className="btn" href={'/api/community/template.zip' + (isTool ? '?kind=tool' : '')} download><Icon name="download" size={15} />Пример {noun}а</a>
    </div>
    <div className="dim3" style={{ fontSize: 12, marginTop: 8, lineHeight: 1.4 }}>Как сделать свой: скачайте инструкцию, отдайте её нейросети вместе с задачей, загрузите полученный архив — Rack Live проверит и покажет ошибки.</div>
    {rep ? <div className={'plugin-result' + (rep.ok ? '' : ' bad')} style={{ marginTop: 10 }}>
      <b>{rep.ok ? 'Добавлено: ' + (rep.name || '') : 'Не принято'}</b>
      {(rep.errors || []).length ? <div className="dim" style={{ fontSize: 12.5, marginTop: 4 }}>{rep.errors.slice(0, 4).join(' · ')}</div> : null}</div> : null}

    {catOpen ? <div style={{ marginTop: 12 }}>
      <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px', margin: '0 0 4px' }}>Каталог на GitHub</div>
      {!idx || !idx.plugins && idx.ok === undefined ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю каталог…</div>
        : !idx.ok ? <div className="err-note" style={{ marginTop: 0 }}>{idx.error || 'Каталог недоступен.'} <Btn size="sm" onClick={() => loadIdx(true)}>Повторить</Btn></div>
        : !idx.plugins.length ? <div className="dim" style={{ fontSize: 13 }}>В каталоге пока нет {isTool ? 'инструментов' : 'плагинов'}. Станьте первым — сделайте {noun} и отправьте его в репозиторий racklive-plugins.</div>
        : idx.plugins.map(p => <div key={p.id} className="plug-row" style={{ cursor: 'default', alignItems: 'flex-start' }}>
            <span className="ico-circle"><Icon name={p.icon || 'box'} size={16} /></span>
            <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{p.title}</b> <span className="dim3" style={{ fontSize: 12 }}>{p.version}{p.author ? ' · ' + p.author : ''}</span>
              {p.description ? <small>{p.description}</small> : null}</span>
            {(idx.installed || {})[p.id] === p.version ? <span className="badge online" style={{ flexShrink: 0 }}>добавлен</span>
              : <Btn size="sm" kind="primary" busy={busy === p.id} onClick={() => install(p)}>{(idx.installed || {})[p.id] ? 'Обновить' : 'Добавить'}</Btn>}
          </div>)}
    </div> : null}

    <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px', margin: '14px 0 2px' }}>Установленные{mine && mine.length ? ' · ' + mine.length : ''}</div>
    {mine === null ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />…</div>
      : !mine.length ? <div className="dim3" style={{ fontSize: 12.5 }}>Пока ничего не добавлено. Загрузите .zip или возьмите из каталога GitHub выше.</div>
      : mine.map(p => <div key={p.id} className="plug-row" style={{ cursor: 'default', alignItems: 'flex-start' }}>
          <span className="ico-circle"><Icon name={p.icon || 'box'} size={16} /></span>
          <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{p.title}</b> <span className="dim3" style={{ fontSize: 12 }}>{noun}{p.version ? ' · ' + p.version : ''}</span>
            {p.description ? <small>{p.description}</small> : null}</span>
          <Btn size="sm" kind="danger" icon="trash" onClick={() => remove(p)} />
        </div>)}
    {mine && mine.length ? <div className="dim3" style={{ fontSize: 11.5, marginTop: 4 }}>{isTool ? 'Запуск инструмента — в разделе «Инструменты»: выберите устройство и подтвердите команды.' : 'Запуск — в карточке подходящего устройства (вкладка «Плагины»), после выбора устройства и подтверждения команд.'}</div> : null}
  </>;
}

/* community plugins: expandable card on the Плагины page */
function CommunityCard({ reloadCat }) {
  const [open, setOpen] = useState(false);
  const [n, setN] = useState(null);
  useEffect(() => { api('/api/community').then(r => setN(r.plugins.filter(p => (p.kind || 'plugin') !== 'tool').length)).catch(() => { }); }, []);
  return <div className={'card plugin plug-dev-card' + (open ? ' open' : '')} style={{ marginBottom: 16 }}>
    <button type="button" className="plugin-head" onClick={() => setOpen(!open)}>
      <span className="ico-circle"><Icon name="box" size={18} /></span>
      <b className="grow ellipsis" style={{ minWidth: 0, textAlign: 'left' }}>Плагины сообщества</b>
      {n ? <span className="badge" style={{ flexShrink: 0 }}>{n}</span> : null}
      <Icon name="chevron" size={16} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} />
    </button>
    {open ? <div className="plug-list"><CommunityBody kind="plugin" onChange={() => { reloadCat(); api('/api/community').then(r => setN(r.plugins.filter(p => (p.kind || 'plugin') !== 'tool').length)).catch(() => { }); }} /></div> : null}
  </div>;
}

/* community tools: the «Свой инструмент или из каталога» section of the Инструменты tab */
function CommunityToolsView({ onChange }) {
  return <CommunityBody kind="tool" onChange={onChange} />;
}

/* one plugin: expand → pick the device (added ones + «найти в сети») */
function PluginRow({ p, g, devs, exp }) {
  const { openDevice } = useApp();
  const [open, setOpen] = useState(false);
  const openOn = (d) => { const u = new URL(location.href); u.searchParams.set('plugin', p.id); try { history.replaceState(null, '', u.pathname + u.search + u.hash); } catch (e) { } openDevice(d, 'plugins'); };
  return <div className={'card plugin plug-dev-card' + (open ? ' open' : '')}>
    <button type="button" className="plugin-head" onClick={() => setOpen(!open)}>
      <span className="ico-circle"><Icon name={p.icon || 'box'} size={18} /></span>
      <b className="grow ellipsis" style={{ minWidth: 0, textAlign: 'left' }}>{p.title}</b>
      {exp ? <span className="badge warning" style={{ flexShrink: 0 }}>эксперимент</span> : null}
      <Icon name="chevron" size={16} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} />
    </button>
    {open ? <div className="plug-list">
      <div className="dim" style={{ fontSize: 12.8, lineHeight: 1.45, margin: '0 0 8px' }}>{p.description}</div>
      {p.author ? <div className="dim3" style={{ fontSize: 12, margin: '-4px 0 8px' }}>Автор способа: {p.author}</div> : null}
      <PluginTargets p={p} g={g} devs={devs} openOn={openOn} />
    </div> : null}
  </div>;
}

/* which device to run the plugin on: the added ones of this type, plus scanning the network for more */
function PluginTargets({ p, g, devs, openOn }) {
  const { newDevice } = useApp(); const toast = useToast();
  const [scan, setScan] = useState(null);          // null | {running, items, done, total} | 'error'
  const stop = useRef(false);
  useEffect(() => () => { stop.current = true; }, []);
  const addrOf = d => (d.fields && (d.fields.host || d.fields.webUrl)) || d.host || '';
  const found = scan && scan.items ? scan.items.filter(it => g.drivers.includes(it.driver) && !it.added && !devs.some(d => addrOf(d) === it.ip)) : [];
  const runScan = async () => {
    stop.current = false; setScan({ running: true, items: [], done: 0, total: 0 });
    try {
      await api('/api/netscan/start', { method: 'POST', body: {} });
      for (let i = 0; i < 90; i++) {
        if (stop.current) return;
        await new Promise(r => setTimeout(r, 2000));
        const s = await api('/api/netscan');
        setScan({ running: s.running, items: s.items || [], done: s.done, total: s.total });
        if (!s.running) break;
      }
    } catch (e) { setScan('error'); toast(e.message, true); }
  };
  return <>
    {devs.length ? <>
      <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px', margin: '2px 0 2px' }}>На каком устройстве</div>
      {devs.map(d => <button type="button" key={d.id} className="plug-row" onClick={() => openOn(d)}>
        <KindIcon kind={d.kind || 'router'} size={30} round={9} />
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{d.name}</b><small>{addrOf(d) || g.title}</small></span>
        <Icon name="chevron" size={14} /></button>)}
    </> : <div className="dim" style={{ fontSize: 13, padding: '2px 0 6px' }}>Устройств типа «{g.title}» в Rack Live пока нет. Найдите роутер в сети или добавьте вручную.</div>}
    <div className="row wrap" style={{ marginTop: 8 }}>
      <Btn size="sm" icon="search" busy={!!(scan && scan.running)} onClick={runScan}>{scan && scan.running ? 'Сканирую сеть…' : 'Найти в сети'}</Btn>
      <Btn size="sm" icon="plus" onClick={() => newDevice({ driver: realDriver(g) })}>Добавить вручную</Btn>
    </div>
    {scan === 'error' ? <div className="cam-warn" style={{ marginTop: 8 }}>Не удалось просканировать сеть.</div> : null}
    {scan && typeof scan === 'object' ? <div style={{ marginTop: 8 }}>
      {scan.running ? <div className="dim3" style={{ fontSize: 12 }}>Идёт поиск… проверено {scan.done}{scan.total ? ' из ' + scan.total : ''}</div> : null}
      {found.length ? <>
        <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px', margin: '6px 0 2px' }}>Найдено в сети</div>
        {found.map(it => <div key={it.ip} className="plug-row" style={{ cursor: 'default' }}>
          <span className="ico-circle"><Icon name={g.icon} size={16} /></span>
          <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{it.name && it.name !== it.ip ? it.name : it.ip}</b><small>{it.ip}{it.what ? ' · ' + it.what : ''}</small></span>
          <Btn size="sm" kind="primary" icon="plus" onClick={() => newDevice({ driver: it.driver, kind: it.kind || g.id, name: it.name && it.name !== it.ip ? it.name : (it.what || g.title), fields: { host: it.ip } })}>Добавить</Btn>
        </div>)}
        <div className="dim3" style={{ fontSize: 11.5, marginTop: 4 }}>После добавления роутер появится в списке «На каком устройстве» выше — выберите его.</div>
      </> : !scan.running ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 4 }}>Подходящих роутеров ({g.title}) в сети не найдено. Проверьте, что на роутере включён SSH, или добавьте его вручную.</div> : null}
    </div> : null}
  </>;
}

/* ───────── cameras ───────── */
const LOGIN_TEXT = { password: ['запрашивает пароль', 'online'], open: ['открыта без пароля!', 'offline'], inactive: ['не активирована', 'warning'], unknown: ['пароль не проверен', ''] };
const KIND_WORD = { camera: 'Камера', recorder: 'Видеорегистратор', unknown: 'Видеоустройство' };
const genPassword = () => { const a = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'; const v = new Uint32Array(12); (window.crypto || window.msCrypto).getRandomValues(v); return Array.from(v, x => a[x % a.length]).join(''); };

function CameraTool() {
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
