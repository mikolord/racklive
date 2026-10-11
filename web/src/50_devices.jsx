/* Devices list and the add / edit wizard */
function DevicesView() {
  const { data, admin, edit, openDevice, openEditor } = useApp();
  const [flt, setFlt] = useState('all'); const [q, setQ] = useState('');
  const drvTitle = id => (data.drivers.find(d => d.id === id) || {}).title || id;
  const list = data.devices.filter(d => {
    const s = (d.state || {}).status;
    if (flt === 'problems' && !['offline', 'warning'].includes(s)) return false;
    if (flt === 'remote' && d.location !== 'remote') return false;
    if (flt === 'local' && d.location === 'remote') return false;
    return !q || [d.name, d.host, (d.state && d.state.summary || {}).ip, d.site].join(' ').toLowerCase().includes(q.toLowerCase());
  });
  const sites = [...new Set(data.devices.map(d => d.site).filter(Boolean))];
  const counts = { all: data.devices.length, problems: data.devices.filter(d => ['offline', 'warning'].includes((d.state || {}).status)).length,
    local: data.devices.filter(d => d.location !== 'remote').length, remote: data.devices.filter(d => d.location === 'remote').length };
  return <>
    <div className="row wrap" style={{ marginBottom: 14 }}>
      {[['all', 'Все'], ['problems', 'Проблемы'], ['local', 'Локальные'], ['remote', 'Удалённые']].map(([k, l]) =>
        <button key={k} className={'chip' + (flt === k ? ' on' : '')} onClick={() => setFlt(k)}>{l} · {counts[k]}</button>)}
      <div className="grow" />
      <div style={{ width: 240 }}><SearchBox value={q} onChange={setQ} /></div>
      {admin ? <Btn kind="primary" icon="plus" onClick={() => openEditor(null)}>Добавить</Btn> : null}
    </div>
    {!data.devices.length ? <Card><div className="empty" style={{ padding: 50 }}>
      <div style={{ fontSize: 40, marginBottom: 10 }}>🛰️</div><div style={{ fontSize: 17, fontWeight: 600, color: 'var(--text)' }}>Пока нет ни одного устройства</div>
      <div style={{ margin: '6px 0 16px' }}>Добавьте роутер, коммутатор, NAS или любой сервер — данные начнут собираться автоматически.</div>
      {admin ? <Btn kind="primary" icon="plus" onClick={() => openEditor(null)}>Добавить устройство</Btn> : null}</div></Card> : null}
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

function DeviceEditor({ device, onClose }) {
  const { data, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [drvId, setDrvId] = useState(device ? device.driver : null);
  const drv = data.drivers.find(d => d.id === drvId);
  const [f, setF] = useState(() => device ? { ...device } : { name: '', location: 'local', site: '', notes: '', enabled: true });
  const [test, setTest] = useState(null);
  const [token, setToken] = useState(null);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  useEffect(() => { if (drv && !device) { setF(x => { const n = { ...x, kind: x.kind || drv.kind }; drv.fields.forEach(fl => { if (fl.default && !n[fl.name]) n[fl.name] = fl.default; }); return n; }); } }, [drvId]);

  if (!drvId) return <Modal title="Новое устройство" wide onClose={onClose}>
    <div className="dim" style={{ fontSize: 14 }}>Как подключиться к устройству?</div>
    <div className="driver-pick">{data.drivers.filter(d => !d.hidden).map(d => <button key={d.id} onClick={() => setDrvId(d.id)}>
      <KindIcon kind={d.kind} size={38} /><div><b>{d.title}</b><small>{d.description}</small></div></button>)}</div>
  </Modal>;

  const payload = () => { const p = { ...f, driver: drvId }; delete p.state; Object.keys(p).filter(k => k.endsWith('Set')).forEach(k => delete p[k]); return p; };
  const doTest = async () => {
    setTest({ busy: true });
    try { const r = await api('/api/test', { method: 'POST', body: payload() }); setTest(r); }
    catch (e) { setTest({ ok: false, error: e.message }); }
  };
  const save = async () => {
    const missing = drv.fields.filter(fl => fl.required && !f[fl.name] && !(device && device[fl.name + 'Set']));
    if (!f.name.trim()) return toast('Укажите название', true);
    if (missing.length) return toast('Заполните: ' + missing.map(m => m.label).join(', '), true);
    try {
      const r = device ? await api('/api/devices/' + device.id, { method: 'PUT', body: payload() }) : await api('/api/devices', { method: 'POST', body: payload() });
      refresh();
      if (r.agentToken) { setToken({ token: r.agentToken, id: r.device.id }); return; }
      toast(device ? 'Сохранено' : 'Устройство добавлено'); onClose();
    } catch (e) { toast(e.message, true); }
  };
  const del = async () => {
    if (!(await confirm(`Удалить «${device.name}»? История и связи на карте будут удалены.`, { danger: true, ok: 'Удалить' }))) return;
    await api('/api/devices/' + device.id, { method: 'DELETE' }); refresh(); toast('Удалено'); onClose();
  };
  if (token) return <AgentInstall token={token.token} onClose={onClose} />;

  return <Modal title={device ? 'Настройки устройства' : drv.title} wide onClose={onClose} icon={<KindIcon kind={f.kind || drv.kind} />}
    footer={<>{device ? <Btn kind="danger" icon="trash" onClick={del}>Удалить</Btn> : <Btn onClick={() => setDrvId(null)}>Назад</Btn>}<div className="grow" />
      {drvId !== 'agent' ? <Btn onClick={doTest} busy={test && test.busy}>Проверить</Btn> : null}<Btn kind="primary" onClick={save}>Сохранить</Btn></>}>
    {drv.description ? <div className="dim" style={{ fontSize: 13.5 }}>{drv.description}</div> : null}
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))' }}>
      <Field label="Название"><input className="input" value={f.name} onChange={e => set('name', e.target.value)} placeholder="Например, Роутер дома" /></Field>
      <Field label="Тип (иконка)"><select className="select" value={f.kind || drv.kind} onChange={e => set('kind', e.target.value)}>
        {DEVICE_KINDS.map(k => <option key={k} value={k}>{KIND_TEXT[k]}</option>)}</select></Field>
      {drv.fields.map(fl => <Field key={fl.name} label={fl.label} hint={fl.hint}>
        <input className="input" type={fl.type === 'password' ? 'password' : 'text'} value={f[fl.name] || ''} onChange={e => set(fl.name, e.target.value)}
          placeholder={fl.secret && device && device[fl.name + 'Set'] ? '•••••••• (не менять)' : (fl.placeholder || '')} autoComplete="off" /></Field>)}
      <Field label="Расположение"><Seg value={f.location || 'local'} onChange={v => set('location', v)} options={[{ value: 'local', label: 'Локальное' }, { value: 'remote', label: 'Удалённое' }]} /></Field>
      <Field label="Площадка / объект" hint="Например «Дача» или «Офис» — устройства группируются по площадкам"><input className="input" value={f.site || ''} onChange={e => set('site', e.target.value)} /></Field>
    </div>
    <Field label="Заметки"><textarea className="textarea" value={f.notes || ''} onChange={e => set('notes', e.target.value)} /></Field>
    <div className="row"><Switch on={f.enabled !== false} onChange={v => set('enabled', v)} /><span>Опрашивать устройство</span></div>
    {device && drvId === 'agent' ? <AgentInstallInline device={device} /> : null}
    {test && !test.busy ? <div className="card pad" style={{ borderColor: test.ok ? 'var(--green)' : 'var(--red)' }}>
      {test.ok ? <><div className="row" style={{ color: 'var(--green)', fontWeight: 700 }}><Icon name="check" />Подключение работает</div>
        <div className="dim" style={{ fontSize: 13.5, marginTop: 6 }}>{[test.summary.model, test.summary.fw, test.summary.ip].filter(Boolean).join(' · ')}
          {test.ports ? ` · портов: ${test.ports}` : ''}{test.clients ? ` · клиентов: ${test.clients}` : ''}</div></>
        : <div style={{ color: 'var(--red)' }}><b>Не получилось:</b> {test.error}</div>}</div> : null}
  </Modal>;
}

function agentCommand(token) {
  const base = location.origin;
  return `curl -fsSL ${base}/agent.py -o /opt/racklive-agent.py\npython3 /opt/racklive-agent.py --server ${base} --token ${token} --install`;
}
function AgentInstall({ token, onClose }) {
  return <Modal title="Установка агента" onClose={onClose} footer={<Btn kind="primary" onClick={onClose}>Готово</Btn>}>
    <div>Выполните на удалённом сервере (Linux, нужен Python 3). Агент будет каждые 60 секунд отправлять данные — открывать порты на сервере не нужно.</div>
    <div className="code">{agentCommand(token)}</div>
    <div className="dim" style={{ fontSize: 13 }}>Сервер Rack Live должен быть доступен с удалённой машины по этому адресу. Если адрес внутренний — укажите внешний домен в команде.</div>
  </Modal>;
}
function AgentInstallInline({ device }) {
  const [tok, setTok] = useState(null);
  return <Card title="Агент">{tok ? <div className="code">{agentCommand(tok)}</div>
    : <Btn size="sm" onClick={async () => setTok((await api(`/api/devices/${device.id}/token`, { method: 'POST' })).agentToken)}>Показать команду установки</Btn>}</Card>;
}
