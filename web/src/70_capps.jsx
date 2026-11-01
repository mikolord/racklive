/* ───────── «Приложения»: чужие программы в контейнерах (описание app.json → Docker на сервере или NAS) ─────────
   Описание проверяется (rackd/capps.py), администратору показывают, что будет запущено и какие права, и только после подтверждения оно ставится на выбранное устройство.
   Backend: /api/capps* */
const CAPP_RISK = { low: ['низкий риск', 'ok'], medium: ['средний риск', 'wait'], high: ['высокий риск', 'bad'] };
const capSleep = ms => new Promise(r => setTimeout(r, ms));

function capUrl(app, host, mine, scheme) {
  const u = app.ui || {};
  if (!u.mode || u.mode === 'none' || !host) return '';
  const real = ((mine && mine.ports) || []).find(p => p.container === u.cport && p.proto === 'tcp');       // the port the app really got (it may have been changed at install)
  return `${scheme || u.scheme || 'http'}://${host}:${real ? real.host : u.port}${u.path || '/'}`;
}

/* ports before the install: the administrator may pick other ones; Rack Live asks the device which are busy */
function CappPorts({ app, dev, chosen, setChosen, onBusy }) {
  const [rep, setRep] = useState(null); const [err, setErr] = useState('');
  const key = JSON.stringify(chosen);
  useEffect(() => {
    if (!dev) return; let live = true; setErr('');
    const t = setTimeout(async () => {
      try { const r = await api('/api/capps/ports', { method: 'POST', body: { device: dev, app: app.id, ports: chosen } }); if (live) { setRep(r); onBusy(r.ports.some(p => p.busy)); } }
      catch (x) { if (live) { setErr(x.message); onBusy(false); } }
    }, 450);
    return () => { live = false; clearTimeout(t); };
  }, [dev, key]);
  const info = k => (rep && rep.ports || []).find(p => p.key === k);
  return <div className="col" style={{ gap: 6 }}>
    <b style={{ fontSize: 13 }}>Порты на устройстве</b>
    <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Проверяю, не занят ли порт другой программой. Если занят, выберите другой: приложение будет доступно по новому порту.</div>
    {err ? <div className="cam-warn">{err}</div> : null}
    {app.ports.map(p => {
      const r = info(p.key); const val = chosen[p.key] ?? p.host;
      return <div key={p.key} className="col" style={{ gap: 3 }}>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span className="grow" style={{ fontSize: 13, minWidth: 0 }}>{p.label || p.key} <span className="dim mono" style={{ fontSize: 11.5 }}>{p.proto}</span></span>
          <input className="input mono" type="number" min="1" max="65535" style={{ width: 92 }} disabled={p.fixed} value={val} onChange={ev => setChosen({ ...chosen, [p.key]: ev.target.value === '' ? '' : Number(ev.target.value) })} />
          <span style={{ width: 18, textAlign: 'center' }}>{r ? (r.busy ? '⚠' : '✓') : ''}</span></div>
        {p.fixed ? <div className="dim" style={{ fontSize: 12 }}>Порт менять нельзя: иначе приложение не заработает.</div> : null}
        {r && r.busy ? <div className="cam-warn" style={{ fontSize: 12.5 }}>Порт {r.host}/{r.proto} уже занят{r.by ? ' контейнером «' + r.by + '»' : ' другой программой'}.
          {r.free && !p.fixed ? <> <button type="button" className="link-btn" onClick={() => setChosen({ ...chosen, [p.key]: r.free })}>Взять свободный {r.free}</button></> : null}
          {p.fixed ? ' Освободите его, иначе установка не пройдёт.' : null}</div> : null}
      </div>;
    })}
    {rep && rep.installed ? <div className="dim" style={{ fontSize: 12 }}>Приложение уже установлено на этом устройстве.</div> : null}
  </div>;
}

function CappFields({ app, vals, setVals }) {
  if (!app.fields.length) return null;
  return <div className="col" style={{ gap: 10 }}>{app.fields.map(f => <Field key={f.id} label={f.label || f.id} hint={f.hint}>
    {f.type === 'switch' ? <label className="row" style={{ gap: 8 }}><input type="checkbox" checked={!!vals[f.id]} onChange={ev => setVals({ ...vals, [f.id]: ev.target.checked })} />включить</label>
      : f.type === 'select' ? <select className="input" value={vals[f.id] ?? ''} onChange={ev => setVals({ ...vals, [f.id]: ev.target.value })}>{(f.options || []).map(o => <option key={o[0]} value={o[0]}>{o[1]}</option>)}</select>
      : <input className="input" type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'} autoComplete="off" placeholder={f.type === 'path' ? '/volume1/папка' : ''} value={vals[f.id] ?? ''} onChange={ev => setVals({ ...vals, [f.id]: ev.target.value })} />}
  </Field>)}</div>;
}

function CappDetail({ app, devices, onBack, onRemoved }) {
  const toast = useToast(); const confirm = useConfirm();
  const eligible = devices.filter(d => app.targets.includes(d.target));
  const [dev, setDev] = useState(() => (eligible[0] || {}).id || '');
  const [vals, setVals] = useState(() => Object.fromEntries(app.fields.filter(f => f.default !== undefined).map(f => [f.id, f.default])));
  const [stat, setStat] = useState(null); const [host, setHost] = useState(''); const [err, setErr] = useState('');
  const [chosen, setChosen] = useState({}); const [portBusy, setPortBusy] = useState(false);
  const [busy, setBusy] = useState(''); const [stage, setStage] = useState(''); const [showYaml, setShowYaml] = useState(false); const [wipe, setWipe] = useState(false); const [frame, setFrame] = useState(false);
  const load = async () => { if (!dev) return; setStat(null); setErr(''); try { const r = await api('/api/capps/states?device=' + encodeURIComponent(dev)); setHost(r.host || ''); setStat(r.states || {}); } catch (x) { setErr(x.message); setStat({}); } };
  useEffect(() => { load(); }, [dev]);
  useEffect(() => {                         // open the card on the device where the app already runs (if several devices can run it)
    if (eligible.length < 2) return; let live = true;
    Promise.all(eligible.map(d => api('/api/capps/states?device=' + encodeURIComponent(d.id)).then(r => (r.states && r.states[app.id] ? d.id : null)).catch(() => null)))
      .then(ids => { const hit = ids.find(Boolean); if (live && hit) setDev(hit); });
    return () => { live = false; };
  }, []);
  const mine = stat && stat[app.id];
  const nodocker = stat && stat._nodocker;
  const state = mine ? mine.state : 'none';
  const run = async (op, extra) => {
    setBusy(op); setStage('Подключаюсь к устройству…'); setErr('');
    try {
      const r = await api('/api/capps/run', { method: 'POST', body: { device: dev, app: app.id, op, digest: app.digest, values: vals, ports: chosen, ...extra } });
      let j; for (let i = 0; i < 500; i++) { await capSleep(1800); j = await api('/api/capps/job', { method: 'POST', body: { job: r.job } }); if (j.stage) setStage(j.stage); if (j.done) break; }
      if (!j || !j.done) throw new Error('операция идёт слишком долго — проверьте устройство вручную');
      if (j.error) throw new Error(j.error);
      toast((j.result && j.result.message) || 'Готово'); await load();
    } catch (x) { setErr(x.message); toast(x.message, true); } finally { setBusy(''); setStage(''); }
  };
  const install = async () => {
    const dv = devices.find(d => d.id === dev);
    const ok = await confirm(`Установить «${app.title}» на «${dv ? dv.name : dev}»?\n\nУровень риска: ${CAPP_RISK[app.risk][0]}.\nПриложение:\n• ` + app.permissions.join('\n• ') + `\n\nМы скачаем образы и запустим контейнеры. Файл запуска можно посмотреть ниже, в «Что будет запущено».`, { title: 'Подтвердите установку', ok: 'Установить', danger: app.risk === 'high' });
    if (ok) run('install');
  };
  const remove = async () => {
    const ok = await confirm(`Удалить «${app.title}» с устройства?` + (wipe ? '\n\nБудут удалены и данные приложения (тома) и образы. Это нельзя отменить.' : '\n\nДанные приложения останутся на устройстве.'), { title: 'Удалить приложение', ok: 'Удалить', danger: true });
    if (ok) run('remove', { keep_data: !wipe });
  };
  const url = capUrl(app, host, mine);
  const altScheme = (app.ui && app.ui.scheme) === 'https' ? 'http' : 'https';
  const altUrl = capUrl(app, host, mine, altScheme);
  const rk = CAPP_RISK[app.risk];
  return <div className="col" style={{ gap: 12 }}>
    <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={onBack}>← К списку приложений</button>
    <div><b style={{ fontSize: 17 }}>{app.title}</b> <span className={'st-badge ' + rk[1]}>{rk[0]}</span>
      <div className="dim" style={{ fontSize: 12.5 }}>версия {app.version}{app.author ? ' · ' + app.author : ''}{app.license ? ' · ' + app.license : ''}{app.home ? <> · <a href={app.home} target="_blank" rel="noopener noreferrer">сайт</a></> : null}</div></div>
    <div style={{ fontSize: 14, lineHeight: 1.5 }}>{app.description}</div>
    <div><b style={{ fontSize: 13 }}>Что приложению разрешено:</b><ul style={{ margin: '4px 0 0', paddingLeft: 20, fontSize: 13, lineHeight: 1.55 }}>{app.permissions.map((p, i) => <li key={i}>{p}</li>)}</ul></div>
    <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>{app.expose_note}</div>
    <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => setShowYaml(!showYaml)}>{showYaml ? '▾' : '▸'} Что будет запущено (файл docker compose)</button>
    {showYaml ? <pre className="m3-guide" style={{ maxHeight: 300 }}>{app.compose}</pre> : null}
    <div className="card" style={{ padding: 12 }}><div className="col" style={{ gap: 10 }}>
      <b style={{ fontSize: 14 }}>Где запускать</b>
      {!eligible.length ? <div className="cam-warn">Нет подходящих устройств. Добавьте сервер по SSH или NAS Synology (на нём должен быть Docker), и вернитесь сюда.</div>
        : <select className="input" value={dev} onChange={ev => setDev(ev.target.value)}>{eligible.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>}
      {err ? <div className="cam-warn">{err}</div> : null}
      {nodocker ? <div className="cam-warn">На этом устройстве не найден Docker.</div> : null}
      {dev && !stat ? <div className="dim" style={{ fontSize: 13 }}>Смотрю, что запущено на устройстве…</div> : null}
      {stat && !nodocker ? <>
        <div style={{ fontSize: 14 }}>Состояние: <b>{{ none: 'не установлено', running: 'работает', stopped: 'остановлено', partial: 'работает частично' }[state]}</b>
          {mine ? <span className="dim" style={{ fontSize: 12.5 }}> · {mine.containers.map(c => c.name + ' (' + c.state + ')').join(', ')}</span> : null}</div>
        {mine && state !== 'stopped' && mine.containers.some(c => /starting|Up (\d+ seconds?|About a minute|1 minute)/.test(c.status)) ? <div className="cam-warn">Приложение ещё запускается. Первый запуск может занять 2–5 минут (UniFi, например, поднимает базу данных): если страница не открывается, подождите и обновите её.</div> : null}
        {state === 'none' ? <><CappFields app={app} vals={vals} setVals={setVals} />
          {app.ports.length ? <CappPorts app={app} dev={dev} chosen={chosen} setChosen={setChosen} onBusy={setPortBusy} /> : null}
          <div><Btn kind="primary" icon="download" busy={busy === 'install'} disabled={!!busy || !dev || portBusy} onClick={install}>Установить на устройство</Btn>
            {portBusy ? <div className="dim" style={{ fontSize: 12.5, marginTop: 4 }}>Выберите свободный порт, чтобы установить.</div> : null}</div></> : <>
          <div className="row wrap" style={{ gap: 8 }}>
            {url ? <a className="btn primary" href={url} target="_blank" rel="noopener noreferrer"><Icon name="globe" size={15} />{(app.ui && app.ui.title) || 'Открыть'} ({(app.ui && app.ui.scheme) || 'http'})</a> : null}
            {altUrl ? <a className="btn" href={altUrl} target="_blank" rel="noopener noreferrer"><Icon name="globe" size={15} />по {altScheme}</a> : null}
            {app.ui && app.ui.mode === 'embed' && url ? <Btn onClick={() => setFrame(!frame)}>{frame ? 'Скрыть здесь' : 'Открыть здесь'}</Btn> : null}
            {state !== 'running' ? <Btn busy={busy === 'start'} disabled={!!busy} onClick={() => run('start')}>Запустить</Btn> : <Btn busy={busy === 'stop'} disabled={!!busy} onClick={() => run('stop')}>Остановить</Btn>}
            <Btn busy={busy === 'restart'} disabled={!!busy} onClick={() => run('restart')}>Перезапустить</Btn></div>
          {url ? <div className="mono dim" style={{ fontSize: 12 }}>{url}</div> : null}
          {mine && mine.ports && mine.ports.length ? <div className="dim" style={{ fontSize: 12 }}>Порты: {mine.ports.map(p => p.host + '/' + p.proto).join(', ')}</div> : null}
          {frame && url ? <iframe src={url} title={app.title} style={{ width: '100%', height: '70vh', border: '1px solid var(--line)', borderRadius: 10 }} /> : null}
          <label className="row" style={{ gap: 8, fontSize: 13 }}><input type="checkbox" checked={wipe} onChange={ev => setWipe(ev.target.checked)} />при удалении стереть и данные приложения</label>
          <div><Btn kind="danger" busy={busy === 'remove'} disabled={!!busy} onClick={remove}>Удалить с устройства</Btn></div></>}
        {busy ? <div className="dim" style={{ fontSize: 13 }}><span className="spin-dot" /> {stage}</div> : null}</> : null}
    </div></div>
    <div><Btn size="sm" onClick={async () => { if (await confirm(`Убрать описание «${app.title}» из Rack Live? Уже запущенное на устройствах приложение останется работать.`, { title: 'Убрать описание', ok: 'Убрать' })) { await api('/api/capps/remove', { method: 'POST', body: { id: app.id } }); onRemoved(); } }}>Убрать описание из Rack Live</Btn></div>
  </div>;
}

function AppsTool() {
  const toast = useToast();
  const [data, setData] = useState(null); const [ex, setEx] = useState([]); const [cur, setCur] = useState(null);
  const [text, setText] = useState(''); const [rep, setRep] = useState(null); const [busy, setBusy] = useState(false);
  const load = async () => { try { setData(await api('/api/capps')); setEx((await api('/api/capps/examples')).examples); } catch (x) { setData({ apps: [], devices: [], error: x.message }); } };
  useEffect(() => { load(); }, []);
  const check = async () => { setBusy(true); try { setRep(await api('/api/capps/check', { method: 'POST', body: { app: text } })); } catch (x) { setRep({ ok: false, errors: [x.message] }); } finally { setBusy(false); } };
  const add = async src => { setBusy(true); try { const r = await api('/api/capps/add', { method: 'POST', body: { app: src } }); if (!r.ok) { setRep(r); return; } toast('Описание добавлено'); setText(''); setRep(null); await load(); } catch (x) { toast(x.message, true); } finally { setBusy(false); } };
  if (!data) return <div className="dim" style={{ padding: 20, textAlign: 'center' }}>Загружаю…</div>;
  if (cur) { const a = data.apps.find(x => x.id === cur); if (a) return <CappDetail app={a} devices={data.devices} onBack={() => setCur(null)} onRemoved={() => { setCur(null); load(); }} />; }
  return <div className="col" style={{ gap: 14 }}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.55 }}>Приложения — это готовые программы, которые запускаются в контейнерах Docker на вашем сервере или NAS: контроллер UniFi, мониторинг и другие. Описание приложения проверяется, вам показывают, что именно будет запущено и какие у него права, и только после вашего подтверждения оно ставится. Rack Live сам порты в интернет не открывает: это делается на роутере.</div>
    {data.error ? <div className="cam-warn">{data.error}</div> : null}
    {data.demo ? <div className="cam-warn">В демо-режиме приложения не запускаются, можно только смотреть описания.</div> : null}
    <b style={{ fontSize: 15 }}>Мои приложения</b>
    {!data.apps.length ? <div className="dim" style={{ fontSize: 13 }}>Пока нет ни одного. Добавьте готовый пример ниже или вставьте своё описание.</div>
      : data.apps.map(a => <button key={a.id} type="button" className="plug-row" onClick={() => setCur(a.id)}>
        <span className="ico-circle"><Icon name="box" size={16} /></span>
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{a.title}</b>
          <small><span className={'st-badge ' + CAPP_RISK[a.risk][1]}>{CAPP_RISK[a.risk][0]}</span> версия {a.version}</small></span><Icon name="chevron" size={14} /></button>)}
    {ex.length ? <><b style={{ fontSize: 15 }}>Готовые примеры</b>
      {ex.map(e => <div key={e.id} className="plug-row" style={{ cursor: 'default', alignItems: 'flex-start' }}>
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{e.title}</b> <span className={'st-badge ' + CAPP_RISK[e.risk][1]}>{CAPP_RISK[e.risk][0]}</span><small style={{ display: 'block', whiteSpace: 'normal' }}>{e.description}</small></span>
        {e.added ? <span className="dim" style={{ fontSize: 12.5 }}>добавлено</span> : <Btn size="sm" kind="primary" busy={busy} onClick={() => add(e.app)}>Добавить</Btn>}</div>)}</> : null}
    <b style={{ fontSize: 15 }}>Своё описание</b>
    <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Вставьте app.json. Формат и правила описаны в документации «Контейнерные приложения» (образ закрепляется по хешу, предел памяти обязателен, лишних прав нет).</div>
    <textarea className="input mono" rows={6} placeholder='{"app_api": 1, "id": "…", …}' value={text} onChange={ev => { setText(ev.target.value); setRep(null); }} />
    <div className="row wrap" style={{ gap: 8 }}><Btn busy={busy} disabled={!text.trim()} onClick={check}>Проверить</Btn><Btn kind="primary" busy={busy} disabled={!text.trim()} onClick={() => add(text)}>Добавить</Btn></div>
    {rep ? <div className={rep.ok ? '' : 'cam-warn'}>
      {rep.errors && rep.errors.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{rep.errors.map((e, i) => <li key={i}>{e}</li>)}</ul> : null}
      {rep.warnings && rep.warnings.length ? <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text2)' }}>{rep.warnings.map((e, i) => <li key={i}>{e}</li>)}</ul> : null}
      {rep.ok && rep.app ? <div style={{ fontSize: 13.5, lineHeight: 1.5 }}><b>{rep.app.title}</b> принято: <span className={'st-badge ' + CAPP_RISK[rep.app.risk][1]}>{CAPP_RISK[rep.app.risk][0]}</span>
        <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{rep.app.permissions.map((p, i) => <li key={i}>{p}</li>)}</ul></div> : null}</div> : null}
  </div>;
}
