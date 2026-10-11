/* Settings, events, login and first-run setup */
function SettingsView() {
  const { data, refresh, logout } = useApp(); const toast = useToast();
  const [s, setS] = useState({ ...data.settings });
  const [pw, setPw] = useState({ old: '', n1: '', n2: '' });
  const fileRef = useRef(null);
  const set = (k, v) => setS(x => ({ ...x, [k]: v }));
  const save = async () => { try { await api('/api/settings', { method: 'PUT', body: { title: s.title, poll: +s.poll, publicView: s.publicView, showClients: s.showClients, vlans: s.vlans } }); toast('Сохранено'); refresh(); } catch (e) { toast(e.message, true); } };
  const changePw = async () => {
    if (pw.n1 !== pw.n2) return toast('Пароли не совпадают', true);
    try { await api('/api/settings', { method: 'PUT', body: { oldPassword: pw.old, newPassword: pw.n1 } }); toast('Пароль изменён'); setPw({ old: '', n1: '', n2: '' }); } catch (e) { toast(e.message, true); }
  };
  const importFile = async e => {
    const file = e.target.files[0]; if (!file) return; const text = await file.text(); let obj = null;
    try { obj = JSON.parse(text); } catch (_) { const m = text.match(/window\.__SAVED__=(\{[\s\S]*?\});(?=<)/); if (m) obj = JSON.parse(m[1]); }
    if (!obj) return toast('Не удалось прочитать файл', true);
    try { await api('/api/import', { method: 'POST', body: { data: obj } }); toast(obj.version === 2 ? 'Резервная копия восстановлена' : 'Схема шкафа импортирована'); refresh(); } catch (er) { toast(er.message, true); }
    e.target.value = '';
  };
  const vl = s.vlans || [];
  return <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', alignItems: 'start' }}>
    <Card title="Общие">
      <div className="col" style={{ gap: 14 }}>
        <Field label="Название"><input className="input" value={s.title} onChange={e => set('title', e.target.value)} /></Field>
        <Field label="Интервал опроса" hint="Как часто собирать данные с устройств"><select className="select" value={s.poll} onChange={e => set('poll', +e.target.value)}>
          {[15, 30, 60, 120, 300].map(n => <option key={n} value={n}>{n < 60 ? n + ' секунд' : n / 60 + ' мин'}</option>)}</select></Field>
        <div className="row"><Switch on={!!s.publicView} onChange={v => set('publicView', v)} /><div className="grow"><div>Просмотр без пароля</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Схему и статусы видно всем, кто откроет адрес. Управление — только после входа.</div></div></div>
        <div className="row"><Switch on={s.showClients !== false} onChange={v => set('showClients', v)} /><div className="grow"><div>Клиенты на карте</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Показывать телефоны, камеры и другие устройства, а не только оборудование</div></div></div>
        <Btn kind="primary" onClick={save}>Сохранить</Btn>
      </div>
    </Card>
    <Card title="VLAN" right={<Btn size="sm" icon="plus" onClick={() => set('vlans', [...vl, { vid: (vl.length ? Math.max(...vl.map(v => +v.vid)) + 1 : 1), name: '', color: '#8e8e93' }])} />}>
      <div className="dim" style={{ fontSize: 13, marginBottom: 10 }}>Названия и цвета VLAN для портов и карты</div>
      <div className="col">{vl.map((v, i) => <div className="row" key={i}>
        <input className="input mono" style={{ width: 70 }} value={v.vid} onChange={e => set('vlans', vl.map((x, j) => j === i ? { ...x, vid: +e.target.value || '' } : x))} />
        <input className="input" value={v.name} placeholder="Название" onChange={e => set('vlans', vl.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
        <input type="color" value={v.color} onChange={e => set('vlans', vl.map((x, j) => j === i ? { ...x, color: e.target.value } : x))} style={{ width: 40, height: 38, border: 0, background: 'none', padding: 0 }} />
        <Btn size="sm" icon="trash" onClick={() => set('vlans', vl.filter((_, j) => j !== i))} /></div>)}</div>
      <Btn style={{ marginTop: 12 }} onClick={save}>Сохранить VLAN</Btn>
    </Card>
    <Card title="Пароль администратора">
      <div className="col" style={{ gap: 12 }}>
        <input className="input" type="password" placeholder="Текущий пароль" value={pw.old} onChange={e => setPw({ ...pw, old: e.target.value })} />
        <input className="input" type="password" placeholder="Новый пароль (от 8 символов)" value={pw.n1} onChange={e => setPw({ ...pw, n1: e.target.value })} />
        <input className="input" type="password" placeholder="Повторите новый пароль" value={pw.n2} onChange={e => setPw({ ...pw, n2: e.target.value })} />
        <Btn onClick={changePw} disabled={!pw.old || pw.n1.length < 8}>Сменить пароль</Btn>
      </div>
    </Card>
    <Card title="Резервная копия и импорт">
      <div className="col" style={{ gap: 12 }}>
        <div className="dim" style={{ fontSize: 13.5 }}>Копия содержит устройства (с паролями), схему шкафа, карту и настройки. Храните её в надёжном месте.</div>
        <a className="btn" href="/api/export"><Icon name="download" size={17} />Скачать резервную копию</a>
        <Btn icon="upload" onClick={() => fileRef.current.click()}>Восстановить или импортировать…</Btn>
        <div className="dim3" style={{ fontSize: 12.5 }}>Подходит резервная копия Rack Live или файл server-rack.html / JSON из старого «Конструктора шкафа»</div>
        <input ref={fileRef} type="file" accept=".json,.html,application/json,text/html" style={{ display: 'none' }} onChange={importFile} />
      </div>
    </Card>
    <Card title="О программе"><KV rows={[['Версия', 'Rack Live ' + data.version], ['Драйверы', data.drivers.length], ['Устройств', data.devices.length]]} />
      <Btn style={{ marginTop: 12 }} icon="logout" onClick={logout}>Выйти</Btn></Card>
  </div>;
}

function EventsView() {
  const { data } = useApp(); const [flt, setFlt] = useState('');
  const ev = data.events.filter(e => !flt || e.level === flt);
  return <><div className="row wrap" style={{ marginBottom: 14 }}>{[['', 'Все'], ['offline', 'Сбои'], ['online', 'Восстановления'], ['warning', 'Предупреждения'], ['info', 'Действия']].map(([k, l]) =>
    <button key={k} className={'chip' + (flt === k ? ' on' : '')} onClick={() => setFlt(k)}>{l}</button>)}</div>
    <EventsList events={ev} /></>;
}

function AuthScreen({ setup, title, onDone }) {
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [t, setT] = useState(title || 'Серверный шкаф');
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false);
  const submit = async e => {
    e.preventDefault(); setErr('');
    if (setup && pw !== pw2) return setErr('Пароли не совпадают');
    setBusy(true);
    try { await api(setup ? '/api/setup' : '/api/login', { method: 'POST', body: { password: pw, title: t } }); onDone(); }
    catch (er) { setErr(er.message); } finally { setBusy(false); }
  };
  return <div className="auth"><div className="app-bg" /><form className="card" onSubmit={submit}>
    <div className="brand-logo" style={{ width: 64, height: 64, borderRadius: 18, margin: '0 auto' }}><Icon name="rack" size={34} color="#fff" /></div>
    <h1>{setup ? 'Добро пожаловать' : (title || 'Rack Live')}</h1>
    <div className="dim">{setup ? 'Задайте название и пароль администратора — с ним можно будет добавлять устройства и управлять ими.' : 'Войдите, чтобы продолжить'}</div>
    <div className="col">
      {setup ? <Field label="Название"><input className="input" value={t} onChange={e => setT(e.target.value)} /></Field> : null}
      <Field label="Пароль"><input className="input" type="password" autoFocus value={pw} onChange={e => setPw(e.target.value)} placeholder={setup ? 'Не короче 8 символов' : ''} /></Field>
      {setup ? <Field label="Ещё раз"><input className="input" type="password" value={pw2} onChange={e => setPw2(e.target.value)} /></Field> : null}
      {err ? <div style={{ color: 'var(--red)', fontSize: 14 }}>{err}</div> : null}
      <button className={'btn primary' + (busy ? ' busy' : '')} type="submit" style={{ padding: 13, marginTop: 4 }}>{setup ? 'Начать' : 'Войти'}</button>
    </div>
  </form></div>;
}
