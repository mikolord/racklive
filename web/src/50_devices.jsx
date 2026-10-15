/* Devices list and the add / edit wizard */
const DEV_SORTS = [['group', 'По площадкам'], ['name', 'По имени'], ['status', 'Сначала проблемы']];
function DevicesView() {
  const { data, admin, edit, openDevice, openEditor } = useApp();
  // two tabs «Локальные / Удалённые» (+ «Все»); «только с проблемами» is a switch in the menu
  const [loc, setLoc] = useState(() => { const v = lsGet('rl_dev_loc', 'all'); return ['all', 'local', 'remote'].includes(v) ? v : 'all'; });
  const [onlyBad, setOnlyBad] = useState(() => lsGet('rl_dev_bad', '0') === '1'); const [sort, setSort] = useState(() => lsGet('rl_dev_sort', 'group'));
  const [q, setQ] = useState(''); const [find, setFind] = useState(false); const [menu, setMenu] = useState(false);
  useEffect(() => { lsSet('rl_dev_loc', loc); lsSet('rl_dev_bad', onlyBad ? '1' : '0'); lsSet('rl_dev_sort', sort); }, [loc, onlyBad, sort]);
  useEffect(() => { if (!menu) return; const close = e => { if (!e.target.closest('.sort-menu, .sort-btn')) setMenu(false); };
    document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close); }, [menu]);
  const drvTitle = id => (data.drivers.find(d => d.id === id) || {}).title || id;
  const bad = d => ['offline', 'warning'].includes((d.state || {}).status);
  const list = data.devices.filter(d => {
    if (onlyBad && !bad(d)) return false;
    if (loc === 'remote' && d.location !== 'remote') return false;
    if (loc === 'local' && d.location === 'remote') return false;
    return !q || [d.name, d.host, (d.state && d.state.summary || {}).ip, d.site].join(' ').toLowerCase().includes(q.toLowerCase());
  }).sort((a, b) => sort === 'name' ? (a.name || '').localeCompare(b.name || '') : sort === 'status' ? bad(b) - bad(a) || (a.name || '').localeCompare(b.name || '') : 0);
  const sites = sort === 'group' ? [...new Set(data.devices.map(d => d.site).filter(Boolean))] : [];
  const counts = { all: data.devices.length, problems: data.devices.filter(bad).length,
    local: data.devices.filter(d => d.location !== 'remote').length, remote: data.devices.filter(d => d.location === 'remote').length };
  const LOC_TABS = [{ value: 'all', label: `Все · ${counts.all}` }, { value: 'local', label: `Локальные · ${counts.local}` }, { value: 'remote', label: `Удалённые · ${counts.remote}` }];
  const routers = ((data.routerScan || {}).list || []).filter(r => !r.dismissed);
  const [showRouters, setShowRouters] = useState(() => new URLSearchParams(location.search).get('routers') === '1');
  const [scan, setScan] = useState(() => new URLSearchParams(location.search).get('netscan') === '1');       // «Сканировать сеть» (?netscan=1)
  const changed = onlyBad || sort !== 'group';
  return <>
    <div className="dev-loc"><Seg value={loc} onChange={setLoc} options={LOC_TABS} /></div>
    <div className="dev-tools">
      {find || q ? <div className="dev-find"><SearchBox value={q} onChange={setQ} placeholder="Имя, адрес, площадка" autoFocus />
        <Btn size="sm" icon="x" title="Закрыть поиск" onClick={() => { setQ(''); setFind(false); }} /></div>
        : <button type="button" className="round-btn" title="Найти устройство" onClick={() => setFind(true)}><Icon name="search" size={18} /></button>}
      <div style={{ position: 'relative' }}>
        <button type="button" className={'round-btn sort-btn' + (changed ? ' on' : '')} title="Фильтр и сортировка" onClick={() => setMenu(!menu)}><Icon name="sort" size={18} /></button>
        {menu ? <div className="sort-menu">
          <div className="sort-head">Показать</div>
          <button type="button" className="sort-opt" onClick={() => { setOnlyBad(!onlyBad); setMenu(false); }}>
            <span className="sort-check">{onlyBad ? <Icon name="check" size={15} stroke={2.6} /> : null}</span><span className="grow">Только с проблемами</span><span className="dim3">{counts.problems}</span></button>
          <div className="sort-head">Сортировать</div>
          {DEV_SORTS.map(([k, l]) => <button key={k} type="button" className="sort-opt" onClick={() => { setSort(k); setMenu(false); }}>
            <span className="sort-check">{sort === k ? <Icon name="check" size={15} stroke={2.6} /> : null}</span><span className="grow">{l}</span></button>)}
        </div> : null}
      </div>
      {changed ? <span className="dim" style={{ fontSize: 13 }}>{[onlyBad ? 'только с проблемами' : '', sort !== 'group' ? DEV_SORTS.find(x => x[0] === sort)[1].toLowerCase() : ''].filter(Boolean).join(' · ')}</span> : null}
      <div className="grow" />
      {admin ? <Btn icon="search" title="Найти устройства в сети" onClick={() => setScan(true)}>Сканировать сеть</Btn> : null}
      {admin ? <span data-tour="add-dev" style={{ display: 'inline-flex' }}><Btn kind="primary" icon="plus" onClick={() => openEditor(null)}>Добавить</Btn></span> : null}
    </div>
    {scan ? <NetScanModal onClose={() => setScan(false)} /> : null}
    {!data.devices.length ? <Card><div className="empty" style={{ padding: 50 }}>
      <div style={{ fontSize: 40, marginBottom: 10 }}>🛰️</div><div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text)' }}>Пока нет ни одного устройства</div>
      <div style={{ margin: '6px 0 16px' }}>Добавьте роутер, коммутатор, NAS или любой сервер — данные начнут собираться автоматически.</div>
      {admin ? <div className="row center wrap" style={{ gap: 10 }}><Btn kind="primary" icon="search" onClick={() => setScan(true)}>Сканировать сеть</Btn>
        <Btn icon="plus" onClick={() => openEditor(null)}>Добавить вручную</Btn></div> : null}</div></Card> : null}
    {data.newDevices ? <div style={{ marginBottom: 10 }}><NewDevicesCard /></div> : null}
    {admin && data.routerScan && routers.length ? <div style={{ marginBottom: 14 }}>
      <button type="button" className="card newdev-row" onClick={() => setShowRouters(true)}>
        <div className="newdev-ic"><Icon name="search" size={18} /></div>
        <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}><b style={{ fontSize: 14.5 }}>Найдено в сети: {routers.length}</b>
          <div className="dim ellipsis" style={{ fontSize: 12.5 }}>можно добавить в Rack Live: {routers.slice(0, 3).map(r => r.name).join(', ')}{routers.length > 3 ? '…' : ''}</div></div>
        <Icon name="chevron" size={16} color="var(--text3)" /></button>
      {showRouters ? <Modal title="Найдено в сети" wide onClose={() => setShowRouters(false)} icon={<Icon name="search" size={20} color="var(--accent)" />}><RoutersCard /></Modal> : null}
    </div> : null}
    {!list.length && data.devices.length ? <div className="empty" style={{ lineHeight: 1.5 }}>
      {loc === 'remote' && !counts.remote ? <>Удалённых устройств пока нет. Это устройства в другом месте: сервер или VPS, роутер на даче, сайт.<br />Нажмите «Добавить» → «Проверка доступности» (агент, сайт) или выберите «Удалённое» в настройках устройства.</>
        : loc === 'local' && !counts.local ? 'Локальных устройств пока нет.' : `Ничего не найдено${onlyBad ? ' — включён фильтр «только с проблемами»' : ''}`}</div> : null}
    {(sites.length ? [...sites, ''] : ['']).map(site => {
      const items = list.filter(d => (d.site || '') === site); if (!items.length) return null;
      return <div key={site || '_'} style={{ marginBottom: 20 }}>
        {sites.length ? <div className="card-title" style={{ margin: '4px 2px 10px' }}><Icon name="globe" size={14} />{site || 'Локальная сеть'}</div> : null}
        <div className="grid cards">{items.map(d => { const st = d.state || {}; const s = st.summary || {};
          return <div key={d.id} className="card dev-card fade-in" onClick={() => openDevice(d)}>
            <div className="row"><KindIcon kind={d.kind} size={42} round={12} />
              <div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 700, fontSize: 15.5 }} className="ellipsis">{d.name}</div>
                <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{drvTitle(d.driver)}{s.ip ? ' · ' + s.ip : ''}</div></div>
              <StatusBadge status={st.status} /></div>
            <div className="dim ellipsis" style={{ fontSize: 13, marginTop: 10, minHeight: 18 }}>{deviceLine(d) || (s.model || '')}</div>
            <div className="row between dim3" style={{ fontSize: 12, marginTop: 6 }}>
              <span>{d.location === 'remote' ? 'Удалённое' : 'Локальное'}{d.enabled === false ? ' · выключено' : ''}</span><span>{st.updated ? fmt.ago(st.updated, data.now) : ''}</span></div>
          </div>; })}</div></div>;
    })}
  </>;
}

/* «Новое устройство»: types in groups. Each entry says what Rack Live gets from it, how it knows (a protocol that really works —
   tested on a live device, or a documented standard) and what to prepare on the device itself. */
const DEVICE_CATALOG = [
  { id: 'router', title: 'Роутеры', icon: 'router', color: '#0a84ff', text: 'Keenetic, OpenWrt, другие по стандарту SNMP, любой — через веб-панель', items: [
    { driver: 'keenetic', title: 'Keenetic / Netcraze', proof: 'проверено на живом роутере',
      text: 'Самая полная поддержка: порты и VLAN, клиенты по сетям, mesh-точки, VPN, настройка клиентов, перезагрузка, плагины.',
      steps: ['Адрес — IP роутера в вашей сети (обычно 192.168.1.1).', 'Логин и пароль — те же, что для входа в веб-интерфейс. Лучше завести отдельного пользователя: Управление → Пользователи и доступ.',
        'Роутер не у вас дома: нужен прямой доступ к его веб-интерфейсу (белый IP или домен с прямым доступом). Облачный KeenDNS не подходит — он пускает только браузер.'] },
    { driver: 'openwrt', title: 'OpenWrt', proof: 'проверено на живом роутере',
      text: 'Порты (с настоящими номерами гнёзд), интерфейсы, DHCP-клиенты, USB-модем, плагины Forkop и Podkop.',
      steps: ['Нужен пароль root (задаётся в LuCI: Система → Администрирование).', 'Должен открываться веб-интерфейс LuCI — через него идёт опрос. SSH (порт 22) не закрывайте: по нему ставятся плагины и читаются порты.',
        'Адрес — любой IP роутера, доступный из вашей сети.'] },
    { driver: 'snmp', title: 'Другой роутер по SNMP', preset: { kind: 'router' }, proof: 'стандартный протокол',
      text: 'MikroTik, Zyxel, ASUS, TP-Link и любой роутер, который умеет SNMP: порты и скорость, трафик, процессор, память, время работы. Клиентов и настройку по SNMP получить нельзя.',
      steps: ['В роутере включите SNMP версии 2c (MikroTik: IP → SNMP → Enabled; на OpenWrt нужен пакет snmpd).', 'Задайте community только для чтения — не оставляйте «public», если роутер виден из интернета. Разрешите доступ только с адреса Rack Live.',
        'Если не опрашивается: проверьте, что порт UDP 161 не закрыт файрволом самого роутера.'] },
    { driver: 'remote_web', title: 'Роутер без управления (веб-панель)', proof: 'проверяет, что панель открывается',
      text: 'Любой роутер, у которого открывается веб-интерфейс: у абонентов, родных, на даче. Rack Live следит, что он жив, и хранит вход в панель с кнопками «Открыть» и «Скопировать».',
      steps: ['Адрес веб-интерфейса — http://IP или https://домен:порт.', 'Логин и пароль необязательны: они нужны только для кнопок в карточке. Если окажется, что это Keenetic, Rack Live подскажет сменить тип.'] },
    { driver: 'ping', title: 'Только на связи ли', preset: { kind: 'router' }, proof: 'ping',
      text: 'Если ничего другого не подходит: покажет, отвечает ли роутер, и задержку.', steps: ['Нужен только адрес.'] }] },
  { id: 'switch', title: 'Коммутаторы', icon: 'switch', color: '#30d158', text: 'TP-Link JetStream, другие по SNMP, неуправляемые', items: [
    { driver: 'tplink_jetstream', title: 'TP-Link JetStream', proof: 'проверено на живом коммутаторе',
      text: 'Линк и скорость портов, PoE по каждому порту, VLAN, кто подключён, перезапуск порта и PoE, проверка кабеля.',
      steps: ['Включите на коммутаторе Telnet (в TP-Link JetStream он есть в настройках доступа).', 'Логин и пароль — как для веб-интерфейса. Если стоит admin / admin — смените.'] },
    { driver: 'snmp', title: 'Другой коммутатор по SNMP', preset: { kind: 'switch' }, proof: 'стандартный протокол',
      text: 'Управляемые коммутаторы любых брендов: порты, скорость, трафик, VLAN, кто на каком порту (LLDP), процессор.',
      steps: ['Включите SNMP версии 2c, задайте community только для чтения.', 'Разрешите доступ с адреса Rack Live. Порт UDP 161.'] },
    { driver: 'unmanaged', title: 'Неуправляемый коммутатор', proof: 'без опроса',
      text: 'Простой коммутатор без настроек. Опросить его нельзя — вы указываете, в какой порт чего он включён, и всё за ним появится на карте.', steps: ['Нужно знать, в какое устройство и какой порт он включён.'] }] },
  { id: 'server', title: 'Серверы и хранилища', icon: 'server', color: '#5e5ce6', text: 'Synology, Proxmox, Linux по SSH, Home Assistant', items: [
    { driver: 'synology', title: 'Synology DSM', proof: 'проверено на живом NAS',
      text: 'Диски, тома, температура, процессор и память, сетевые карты, контейнеры Docker.',
      steps: ['Адрес DSM: https://IP:5001.', 'Логин администратора. Двухфакторная защита (2FA) у этого пользователя должна быть выключена — заведите отдельного.', 'Хотите дать Frank полный доступ — включите SSH: Панель управления → Терминал.'] },
    { driver: 'proxmox', title: 'Proxmox VE', proof: 'по документации API, на живом сервере не проверено',
      text: 'Виртуальные машины и контейнеры (запуск, выключение, перезагрузка), нагрузка, хранилища, диски.',
      steps: ['Адрес — IP сервера (порт 8006 подставится сам).', 'Лучше API-токен: Datacenter → Permissions → API Tokens → Add. Для просмотра дайте роль PVEAuditor, для управления машинами — PVEVMUser.'] },
    { driver: 'ssh', title: 'Linux-сервер / VPS по SSH', proof: 'проверено на живых серверах',
      text: 'Процессор, память, диски, температура, контейнеры Docker. На сервер ничего ставить не нужно.', steps: ['Адрес, логин и пароль (или приватный ключ) для SSH.', 'Для перезапуска контейнеров пользователь должен иметь доступ к docker.'] },
    { driver: 'homeassistant', title: 'Home Assistant', proof: 'проверено на живой системе',
      text: 'Версия, число объектов, недоступные устройства; выключатели можно включать и выключать.',
      steps: ['Адрес вида http://IP:8123.', 'Нужен долгосрочный токен: профиль пользователя → Безопасность → Долгосрочные токены доступа.'] }] },
  { id: 'power', title: 'Питание', icon: 'ups', color: '#f5b800', text: 'ИБП — как обычный, так и умный', items: [
    { driver: 'ups', title: 'ИБП (бесперебойник)', proof: 'расчёт и NUT / SNMP',
      text: 'Сколько потребляет всё, что подключено, на сколько хватит батареи. Обычный ИБП — расчётом по данным с наклейки, умный — живыми данными.',
      steps: ['ИБП просто в розетке: выберите «Вручную» и впишите мощность и аккумулятор с наклейки, что подключено.', 'ИБП с USB-кабелем к NAS или серверу: включите там NUT (Synology: Панель управления → Оборудование и питание → ИБП → Сетевой ИБП-сервер).',
        'ИБП всегда локальный — удалённым он быть не может.'] }] },
  { id: 'watch', title: 'Проверка доступности', icon: 'pulse', color: '#ff9f0a', text: 'Ping, сайт, удалённый сервер с агентом', items: [
    { driver: 'ping', title: 'Доступность (ping / порт)', proof: 'ping или проверка порта',
      text: 'Для всего, у чего нет своего интерфейса: камера, принтер, телевизор. Показывает, отвечает ли устройство, и задержку. Если ping закрыт — укажите TCP-порт (80 — веб, 554 — камера, 22 — SSH): проверяться будет, открыт ли он.',
      steps: ['Нужен адрес (IP или домен). Порт — по желанию.'] },
    { driver: 'http', title: 'Сайт / веб-сервис', proof: 'как браузер',
      text: 'Открывает адрес, как браузер: показывает код ответа (200 — всё хорошо), время ответа и сколько дней осталось сертификату. Можно потребовать, чтобы на странице был нужный текст.',
      steps: ['Адрес вида https://example.com.', 'Для своего сайта, Nextcloud, Home Assistant «снаружи» — предупредит, если сайт упал или сертификат кончается.'] },
    { driver: 'agent', title: 'Агент (удалённый сервер)', proof: 'сервер сам присылает данные',
      text: 'Для серверов в другом месте или за NAT: на сервере запускается небольшой agent.py и сам раз в минуту присылает данные. Открывать порты не нужно.',
      steps: ['После сохранения Rack Live выдаст команду с кнопкой «Скопировать» — выполните её на удалённом сервере (Linux, Python 3).', 'С удалённого сервера должен открываться адрес Rack Live — см. Настройки → Приложения на телефон.'] }] },
];
function CatalogPick({ grp, setGrp, onPick }) {
  const { data } = useApp();
  const have = id => data.drivers.some(d => d.id === id && !d.hidden);
  const known = new Set(DEVICE_CATALOG.flatMap(g => g.items.map(i => i.driver)));
  const rest = data.drivers.filter(d => !d.hidden && !known.has(d.id)).map(d => ({ driver: d.id, title: d.title, text: d.description, steps: [] }));
  const groups = [...DEVICE_CATALOG, ...(rest.length ? [{ id: 'other', title: 'Прочее', icon: 'other', color: '#8e8e93', text: 'Остальные типы', items: rest }] : [])]
    .map(g => ({ ...g, items: g.items.filter(i => have(i.driver)) })).filter(g => g.items.length);
  const cur = groups.find(g => g.id === grp);
  if (cur) return <div className="col" style={{ gap: 10 }}>
    <button type="button" className="icon-link" style={{ alignSelf: 'flex-start' }} onClick={() => setGrp(null)}><Icon name="chevron" size={14} style={{ transform: 'rotate(180deg)' }} /> Все типы</button>
    <div className="dev-cat-list">{cur.items.map((i, k) => <button type="button" key={k} className="dev-cat-item" onClick={() => onPick(i)}>
      <KindIcon kind={(i.preset && i.preset.kind) || (data.drivers.find(d => d.id === i.driver) || {}).kind} size={40} />
      <div style={{ minWidth: 0 }}><b>{i.title}</b>{i.proof ? <span className="dev-cat-proof">{i.proof}</span> : null}<small>{i.text}</small></div></button>)}</div></div>;
  return <div className="dev-cat" data-tour="dev-cat">{groups.map(g => <button type="button" key={g.id} className="dev-cat-grp" onClick={() => setGrp(g.id)}>
    <span className="set-ic" style={{ background: g.color, width: 38, height: 38 }}><Icon name={g.icon} size={19} color="#fff" /></span>
    <div style={{ minWidth: 0 }}><b>{g.title}</b><small>{g.text}</small></div><Icon name="chevron" size={15} color="var(--text3)" /></button>)}</div>;
}

function DeviceEditor({ device, onClose, onCreated, preset }) {
  const { data, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [drvId, setDrvId] = useState(device ? device.driver : (preset && preset.driver) || null);
  const catalogEntry = id => DEVICE_CATALOG.flatMap(g => g.items).find(i => i.driver === id && !i.preset) || null;
  const [entry, setEntry] = useState(() => (!device && preset && preset.driver ? catalogEntry(preset.driver) : null));   // catalog entry → the «что нужно сделать» steps
  const [grp, setGrp] = useState(() => new URLSearchParams(location.search).get('addgrp'));     // opened group of the picker (?addgrp=router)
  const toPicker = () => { setDrvId(null); setEntry(null); };                                    // from the form one step back — to the group that was open
  const drv = data.drivers.find(d => d.id === drvId);
  const [f, setF] = useState(() => device ? { ...device } : { name: (preset && preset.name) || '', location: 'local', site: '', notes: '', enabled: true,
    ...(preset && preset.kind ? { kind: preset.kind } : {}), ...((preset && preset.fields) || {}) });
  const [test, setTest] = useState(null);
  const [token, setToken] = useState(null);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  useEffect(() => { if (drv && !device) { setF(x => { const n = { ...x, kind: x.kind || drv.kind }; drv.fields.forEach(fl => { if (fl.default && !n[fl.name]) n[fl.name] = fl.default; }); return n; }); } }, [drvId]);

  const pick = c => {                                          // a detected candidate → driver + prefilled address
    const d = data.drivers.find(x => x.id === c.driver); if (!d) return;
    const outside = c.driver === 'remote_web' || (/:\/\//.test(c.host || '') && !/^https?:\/\/(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.|localhost)/.test(c.host));
    setF(x => ({ ...x, host: c.host, kind: d.kind, name: x.name || c.what.split(/[(:—]/)[0].trim().slice(0, 40), ...(c.mode ? { mode: c.mode } : {}),
      ...(outside ? { location: 'remote' } : {}) }));
    setDrvId(c.driver); setEntry(catalogEntry(c.driver));
  };
  if (!drvId) return <Modal title={(DEVICE_CATALOG.find(g => g.id === grp) || {}).title || 'Новое устройство'} wide onClose={onClose} onBack={grp ? () => setGrp(null) : null}>
    <DetectBox onPick={pick} />
    <div className="dim" style={{ fontSize: 14 }}>…или выберите вручную, что это за устройство:</div>
    <CatalogPick grp={grp} setGrp={setGrp} onPick={i => { setEntry(i); setDrvId(i.driver); if (i.preset) setF(x => ({ ...x, ...i.preset })); }} />
  </Modal>;

  const payload = () => { const p = { ...f, driver: drvId }; delete p.state; Object.keys(p).filter(k => k.endsWith('Set')).forEach(k => delete p[k]); return p; };
  const doTest = async () => {
    setTest({ busy: true });
    try { const r = await api('/api/test', { method: 'POST', body: payload() }); setTest(r); }
    catch (e) { setTest({ ok: false, error: e.message }); }
  };
  const visible = fl => !fl.showIf || fl.showIf.in.includes(f[fl.showIf.field] != null ? f[fl.showIf.field]
    : (drv.fields.find(x => x.name === fl.showIf.field) || {}).default);
  const renderField = fl => {
    const ph = fl.secret && device && device[fl.name + 'Set'] ? '•••••••• (не менять)' : (fl.placeholder || '');
    if (fl.type === 'select') return <Field key={fl.name} label={fl.label} hint={fl.hint}>
      <select className="select" value={f[fl.name] || fl.default || ''} onChange={e => set(fl.name, e.target.value)}>
        {fl.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></Field>;
    if (fl.type === 'device') return <Field key={fl.name} label={fl.label} hint={fl.hint}>
      <select className="select" value={f[fl.name] || ''} onChange={e => set(fl.name, e.target.value)}>
        <option value="">— выберите —</option>
        {data.devices.filter(d => !device || d.id !== device.id).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>;
    if (fl.type === 'textarea') return <div key={fl.name} style={{ gridColumn: '1 / -1' }}><Field label={fl.label} hint={fl.hint}>
      <textarea className="textarea mono" style={{ fontSize: 12, minHeight: 90 }} value={f[fl.name] || ''} placeholder={ph} onChange={e => set(fl.name, e.target.value)} autoComplete="off" spellCheck={false} /></Field></div>;
    if (fl.type === 'loads') return <div key={fl.name} style={{ gridColumn: '1 / -1' }}><Field label={fl.label} hint={fl.hint}>
      <LoadsField value={f.loads || legacyLoads(f)} self={device && device.id} outlets={Math.max(0, Math.min(24, parseInt(f.outlets) || 0))} powerFrom={f.powerFrom} onChange={v => set('loads', v)} /></Field></div>;
    if (fl.type === 'powerfrom') return <div key={fl.name} style={{ gridColumn: '1 / -1' }}><Field label={fl.label} hint={fl.hint}><PowerFrom f={f} set={set} /></Field></div>;
    if (fl.type === 'upsfind') return <div key={fl.name} style={{ gridColumn: '1 / -1' }}><Field label={fl.label} hint={fl.hint}>
      <UpsFind onPick={c => setF(x => ({ ...x, mode: c.mode, host: c.host, ...(c.upsName ? { upsName: c.upsName } : {}), ...(c.community ? { community: c.community } : {}),
        name: x.name || c.model }))} /></Field></div>;
    if (fl.type === 'devices') { const cur = f[fl.name] || [];
      const opts = data.devices.filter(d => !device || d.id !== device.id);
      return <div key={fl.name} style={{ gridColumn: '1 / -1' }}><Field label={`${fl.label}${cur.length ? ' · ' + cur.length : ''}`} hint={fl.hint}>
        <div className="dev-pick">{opts.map(d => { const on = cur.includes(d.id);
          return <button type="button" key={d.id} className={'chip' + (on ? ' on' : '')} onClick={() => set(fl.name, on ? cur.filter(x => x !== d.id) : [...cur, d.id])}>
            <Icon name={on ? 'check' : d.kind} size={13} />{d.name}</button>; })}
          {!opts.length ? <span className="dim" style={{ fontSize: 13 }}>Сначала добавьте устройства</span> : null}</div></Field></div>; }
    return <Field key={fl.name} label={fl.label} hint={fl.hint}>
      <input className="input" type={fl.type === 'password' ? 'password' : 'text'} value={f[fl.name] || ''} onChange={e => set(fl.name, e.target.value)}
        placeholder={ph} autoComplete="off" /></Field>;
  };
  const save = async () => {
    const missing = drv.fields.filter(fl => fl.required && visible(fl) && !f[fl.name] && !(device && device[fl.name + 'Set']));
    if (!f.name.trim()) return toast('Укажите название', true);
    const noPower = drvId === 'ups' ? rowsMissing(f.loads) : [];
    if (noPower.length) return toast(`У своих устройств нужно указать потребление (В и А или Вт): ${noPower.join(', ')}`, true);
    if (missing.length) return toast('Заполните: ' + missing.map(m => m.label).join(', '), true);
    try {
      const r = device ? await api('/api/devices/' + device.id, { method: 'PUT', body: payload() }) : await api('/api/devices', { method: 'POST', body: payload() });
      refresh();
      if (r.agentToken) { setToken({ token: r.agentToken, id: r.device.id }); return; }
      toast(device ? 'Сохранено' : 'Устройство добавлено');
      if (!device && onCreated) onCreated(r.device);
      onClose();
    } catch (e) { toast(e.message, true); }
  };
  const del = async () => {
    if (!(await confirm(`Удалить «${device.name}»? История и связи на карте будут удалены.`, { danger: true, ok: 'Удалить' }))) return;
    await api('/api/devices/' + device.id, { method: 'DELETE' }); refresh(); toast('Удалено'); onClose();
  };
  if (token) return <AgentInstall token={token.token} onClose={onClose} />;

  return <Modal title={device ? 'Настройки устройства' : (entry && entry.title) || drv.title} wide onClose={onClose} onBack={device ? null : toPicker} icon={<KindIcon kind={f.kind || drv.kind} />}
    footer={<>{device ? <Btn kind="danger" icon="trash" onClick={del}>Удалить</Btn> : <Btn onClick={toPicker}>Назад</Btn>}<div className="grow" />
      {drvId !== 'agent' ? <Btn onClick={doTest} busy={test && test.busy}>Проверить</Btn> : null}<Btn kind="primary" onClick={save}>Сохранить</Btn></>}>
    {entry ? <div className="dim" style={{ fontSize: 13.5 }}>{entry.text}</div> : drv.description ? <div className="dim" style={{ fontSize: 13.5 }}>{drv.description}</div> : null}
    {entry && entry.steps && entry.steps.length ? <details className="guide" open>
      <summary>Что нужно сделать</summary>
      <ol className="steps">{entry.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
      {entry.proof ? <div className="dim3" style={{ fontSize: 12 }}>Как это работает: {entry.proof}.</div> : null}</details> : null}
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))' }}>
      <Field label="Название"><input className="input" value={f.name} onChange={e => set('name', e.target.value)} placeholder="Например, Роутер дома" /></Field>
      <Field label="Тип (иконка)"><select className="select" value={f.kind || drv.kind} onChange={e => set('kind', e.target.value)}>
        {DEVICE_KINDS.map(k => <option key={k} value={k}>{KIND_TEXT[k]}</option>)}</select></Field>
      {drv.fields.filter(visible).map(renderField)}
      {drvId === 'ups' ? <Field label="Расположение" hint="ИБП стоит рядом с оборудованием, поэтому он всегда локальный. Удалённые устройства к местному ИБП не подключаются.">
        <div className="badge info"><Icon name="home" size={12} />Локальное</div></Field>
        : <Field label="Расположение"><Seg value={f.location || 'local'} onChange={v => set('location', v)} options={[{ value: 'local', label: 'Локальное' }, { value: 'remote', label: 'Удалённое' }]} /></Field>}
      <Field label="Площадка / объект" hint="Например «Дача» или «Офис» — устройства группируются по площадкам"><input className="input" value={f.site || ''} onChange={e => set('site', e.target.value)} /></Field>
    </div>
    <Field label="Заметки"><textarea className="textarea" value={f.notes || ''} onChange={e => set('notes', e.target.value)} /></Field>
    {drvId !== 'ups' && drvId !== 'remote_web' ? <details className="guide" open={!!specW(f.pwr)}>
      <summary>Потребление питания (для расчёта ИБП и блоков розеток){specW(f.pwr) ? ` · ${Math.round(specW(f.pwr) * 10) / 10} Вт` : ''}</summary>
      <div style={{ margin: '8px 0' }}><MeasureHint kind={f.kind || drv.kind} /></div>
      <SpecInputs spec={f.pwr} onChange={s => set('pwr', s)} /></details> : null}
    {drvId !== 'remote_web' ? <details className="guide" open={!!(f.webUrl || f.webUser || (device && device.webPasswordSet))}>
      <summary>Вход в веб-интерфейс (необязательно)</summary>
      <div className="dim" style={{ fontSize: 12.5, margin: '6px 0 10px', lineHeight: 1.45 }}>В карточке устройства появятся кнопка «Открыть» и логин с паролем с кнопкой «Скопировать».
        Пусто — берутся адрес, логин и пароль подключения выше.</div>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
        <Field label="Адрес веб-интерфейса"><input className="input" value={f.webUrl || ''} placeholder="https://… или http://IP:порт" onChange={e => set('webUrl', e.target.value)} autoComplete="off" /></Field>
        <Field label="Логин"><input className="input" value={f.webUser || ''} onChange={e => set('webUser', e.target.value)} autoComplete="off" /></Field>
        <Field label="Пароль"><input className="input" type="password" value={f.webPassword || ''} placeholder={device && device.webPasswordSet ? '•••••••• (не менять)' : ''}
          onChange={e => set('webPassword', e.target.value)} autoComplete="new-password" /></Field>
      </div></details> : null}
    <div className="row wrap" style={{ gap: 18 }}>
      <span className="row"><Switch on={f.enabled !== false} onChange={v => set('enabled', v)} /><span>Опрашивать устройство</span></span>
      <span className="row"><Switch on={f.notify !== false} onChange={v => set('notify', v)} /><span>Уведомлять о проблемах</span></span></div>
    {device && drvId === 'agent' ? <AgentInstallInline device={device} /> : null}
    {test && !test.busy ? <div className="card pad" style={{ borderColor: test.ok ? 'var(--green)' : 'var(--red)' }}>
      {test.ok ? <><div className="row" style={{ color: 'var(--green)', fontWeight: 700 }}><Icon name="check" />Подключение работает</div>
        <div className="dim" style={{ fontSize: 13.5, marginTop: 6 }}>{[test.summary.model, test.summary.fw, test.summary.ip].filter(Boolean).join(' · ')}
          {test.ports ? ` · портов: ${test.ports}` : ''}{test.clients ? ` · клиентов: ${test.clients}` : ''}</div></>
        : <div style={{ color: 'var(--red)' }}><b>Не получилось:</b> {test.error}</div>}</div> : null}
  </Modal>;
}

/* UPS load rows: a device (draw estimated by itself, or own watts) or a free line «Камеры, 20 Вт».
   Older configs kept connected (ids) + extraW / extraNote. */
const legacyLoads = f => [...(f.connected || []).map(id => ({ dev: id })), ...(+f.extraW ? [{ label: f.extraNote || 'Прочая нагрузка', w: f.extraW }] : [])];
function LoadsField({ value, onChange, self, outlets, powerFrom }) {
  const { data } = useApp();
  const rows = value.length ? value : [];
  const [open, setOpen] = useState(null);                         // an outlet block whose outlets are edited right here
  const upd = (i, patch) => onChange(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const skipPdu = powerFrom ? [powerFrom, ...pduAbove(data, powerFrom)] : [];       // the block feeding this UPS cannot hang on it
  const taken = rows.map(r => r.outlet).filter(Boolean);
  const nextFree = () => { for (let n = 1; n <= (outlets || 99); n++) if (!taken.includes(String(n))) return String(n); return ''; };
  const dup = rows.some((r, i) => r.outlet && rows.findIndex(x => x.outlet === r.outlet) !== i);
  const blocks = pduUnits(data).filter(u => !skipPdu.includes(u.id));
  return <div className="loads">
    <MeasureHint id="pw-ups" />
    {rows.map((r, i) => { const k = rowKey(r);
      return <div className="load-row" key={i}>
        {outlets ? <select className="select" style={{ width: 92 }} value={r.outlet || ''} onChange={e => upd(i, { outlet: e.target.value })}>
          <option value="">гнездо</option>{Array.from({ length: outlets }, (_, n) => <option key={n} value={n + 1}>{'№ ' + (n + 1)}</option>)}</select> : null}
        <RowPick value={k || 'l'} skipPdu={skipPdu} skipDev={[self]} onChange={v => upd(i, rowPick(v))} />
        {k === 'l' || !k ? <input className="input grow" value={r.label || ''} placeholder="Название, например «Камеры»" onChange={e => upd(i, { label: e.target.value })} /> : null}
        {k[0] === 'p' ? <Btn size="sm" onClick={() => setOpen(r.pdu)} title="Что включено в розетки этого блока — меняется и в самом блоке">Розетки…</Btn>
          : <SpecInputs spec={r} auto={k[0] === 'd'} onChange={s => upd(i, { v: s.v, a: s.a, w: s.w })} />}
        <button type="button" className="icon-link" title="Убрать" onClick={() => onChange(rows.filter((_, n) => n !== i))}><Icon name="x" size={16} /></button>
      </div>; })}
    {dup ? <div style={{ color: 'var(--orange)', fontSize: 12.5 }}>Одно гнездо указано у двух строк — проверьте номера (к гнезду можно подключить удлинитель, тогда выберите блок розеток).</div> : null}
    <div className="row wrap" style={{ gap: 8 }}>
      <Btn size="sm" icon="plus" onClick={() => onChange([...rows, { dev: (data.devices.find(d => d.id !== self && d.location !== 'remote' && !rows.some(r => r.dev === d.id)) || {}).id, outlet: nextFree() }])}>Устройство</Btn>
      <Btn size="sm" icon="plus" disabled={!blocks.length} onClick={() => onChange([...rows, { pdu: (blocks.find(u => !rows.some(r => r.pdu === u.id)) || blocks[0]).id, outlet: nextFree() }])}
        title={blocks.length ? '' : 'Сначала добавьте юнит «Блок розеток» в шкаф или щиток'}>Блок розеток</Btn>
      <Btn size="sm" icon="plus" onClick={() => onChange([...rows, { label: '', outlet: nextFree() }])}>Своё устройство</Btn></div>
    {open ? <PduPortsModal unitId={open} onClose={() => setOpen(null)} /> : null}
  </div>;
}

/* «Найти умный ИБП»: NUT servers and UPS network cards among our devices and the routers' clients */
function UpsFind({ onPick }) {
  const [st, setSt] = useState(null);
  const go = async () => { setSt({ busy: true });
    try { const r = await api('/api/ups/find', { method: 'POST', body: {} }); setSt({ found: r.found }); } catch (e) { setSt({ error: e.message }); } };
  return <div>
    <Btn icon="search" onClick={go} busy={st && st.busy}>Найти умный ИБП в сети</Btn>
    {st && st.found ? <div className="ups-found">{st.found.length ? st.found.map((c, i) => <button type="button" key={i} className="up-opt" onClick={() => onPick(c)} disabled={!!c.error}>
      <KindIcon kind="ups" size={32} round={9} /><div><b>{c.model}</b><small>{c.mode === 'nut' ? `USB через ${c.host} (NUT${c.upsName ? ' · ' + c.upsName : ''})` : `сетевая карта ${c.host}`}
        {c.charge != null ? ` · заряд ${Math.round(c.charge)}%` : ''}{c.error ? ' · ' + c.error : ''}</small></div></button>)
      : <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>Умный ИБП не найден. Если он подключён по USB к Synology — включите там «Панель управления → Оборудование и питание →
        ИБП → Сетевой ИБП-сервер» и разрешите адрес Rack Live. Иначе заполните данные вручную ниже.</div>}</div> : null}
    {st && st.error ? <div style={{ color: 'var(--red)', fontSize: 13, marginTop: 6 }}>{st.error}</div> : null}
  </div>;
}

/* «Определить автоматически»: the server knocks on the address (no login, nothing changed) and suggests the type */
function DetectBox({ onPick }) {
  const { data } = useApp();
  const [host, setHost] = useState('');
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState(null);
  const [err, setErr] = useState('');
  const run = async e => {
    if (e) e.preventDefault(); if (!host.trim()) return;
    setBusy(true); setErr(''); setFound(null);
    try { setFound((await api('/api/detect', { method: 'POST', body: { host } })).found); } catch (er) { setErr(er.message); } finally { setBusy(false); }
  };
  const title = id => (data.drivers.find(d => d.id === id) || {}).title || id;
  return <form className="detect" data-tour="detect-box" onSubmit={run}>
    <div className="row" style={{ gap: 8 }}><Icon name="search" size={18} color="var(--accent)" /><b>Определить автоматически</b></div>
    <div className="row wrap" style={{ gap: 8 }}>
      <input className="input grow" style={{ minWidth: 180 }} value={host} onChange={e => setHost(e.target.value)} placeholder="Адрес устройства, например 192.168.1.1" />
      <Btn kind="primary" type="submit" busy={busy}>{busy ? 'Опрашиваю…' : 'Определить'}</Btn></div>
    <div className="dim3" style={{ fontSize: 12.5 }}>Rack Live постучится по адресу (веб-интерфейс, SNMP, telnet, SSH) и подскажет тип. Ничего не меняет и пароли не нужны.</div>
    {err ? <div style={{ color: 'var(--red)', fontSize: 13 }}>{err}</div> : null}
    {found ? <div className="list">{found.map((c, i) => { const best = i === 0 && c.score >= 60;
      return <button type="button" key={c.driver} className={'li detect-hit' + (best ? ' best' : '')} onClick={() => onPick(c)}>
        <KindIcon kind={(data.drivers.find(d => d.id === c.driver) || {}).kind || 'other'} size={34} round={9} />
        <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}><b style={{ fontSize: 14 }}>{c.what}</b>
          <div className="dim" style={{ fontSize: 12 }}>Подключение: {title(c.driver)}{best ? ' · скорее всего это оно' : ''}</div></div>
        <Icon name="chevron" size={16} /></button>; })}</div> : null}
  </form>;
}

const PRIVATE_URL = /^https?:\/\/(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/;
/* the address a remote machine can reach: the home address is useless to it, so the public one from «Приложения на телефон» is preferred */
function agentBase(apps) { const o = location.origin; return PRIVATE_URL.test(o) && apps && apps.url ? apps.url : o; }
function agentCommand(token, base) {
  return `curl -fsSL ${base}/agent.py -o /opt/racklive-agent.py\npython3 /opt/racklive-agent.py --server ${base} --token ${token} --install`;
}
/* a command to run elsewhere: the text plus a «Скопировать» button (no selecting by hand) */
function CodeBox({ text }) {
  const toast = useToast(); const [done, setDone] = useState(false);
  const copy = () => { if (copyText(text)) { setDone(true); setTimeout(() => setDone(false), 2000); } else toast('Не получилось скопировать — выделите текст вручную', true); };
  return <div className="codebox"><div className="code">{text}</div>
    <Btn size="sm" icon={done ? 'check' : 'copy'} kind={done ? undefined : 'primary'} onClick={copy}>{done ? 'Скопировано' : 'Скопировать'}</Btn></div>;
}
function AgentInstall({ token, onClose }) {
  const { data } = useApp(); const base = agentBase(data.apps); const priv = PRIVATE_URL.test(base);
  return <Modal title="Установка агента" onClose={onClose} footer={<Btn kind="primary" onClick={onClose}>Готово</Btn>}>
    <div>Выполните на удалённом сервере (Linux, нужен Python 3). Агент будет каждые 60 секунд отправлять данные — открывать порты на сервере не нужно.</div>
    <CodeBox text={agentCommand(token, base)} />
    {priv ? <div className="warn-box"><Icon name="alert" size={16} /><div>Адрес <b>{base}</b> домашний — с удалённого сервера он не откроется. Создайте внешнее имя в Настройки → Приложения на телефон, и команда подставит его сама.</div></div>
      : <div className="dim" style={{ fontSize: 13 }}>Адрес {base} должен открываться с удалённой машины.</div>}
  </Modal>;
}
function AgentInstallInline({ device }) {
  const { data } = useApp(); const [tok, setTok] = useState(null);
  return <Card title="Агент">{tok ? <CodeBox text={agentCommand(tok, agentBase(data.apps))} />
    : <Btn size="sm" onClick={async () => setTok((await api(`/api/devices/${device.id}/token`, { method: 'POST' })).agentToken)}>Показать команду установки</Btn>}</Card>;
}
