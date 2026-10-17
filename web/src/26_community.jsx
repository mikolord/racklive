/* Community plugins (rackd/community.py): a plugin is data — a form + shell steps. Before anything runs the administrator sees the exact commands and the risk. */
const PERM_RU = { network: 'скачивает файлы из интернета', packages: 'ставит или удаляет пакеты', services: 'управляет службами и расписанием', docker: 'работает с Docker', reboot: 'перезагружает устройство' };
const RISK_RU = { low: ['низкий', 'online'], medium: ['средний', 'warning'], high: ['высокий', 'offline'] };
const TARGET_RU = { ssh: 'сервер по SSH', openwrt: 'OpenWrt', synology: 'Synology' };

function RiskBadge({ risk }) { const [t, c] = RISK_RU[risk] || ['?', '']; return <span className={'badge ' + c}>риск: {t}</span>; }

function CommunityPlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm();
  const [vals, setVals] = useState(() => Object.fromEntries((p.fields || []).map(f => [f.id, f.default ?? (f.type === 'switch' ? false : '')])));
  const [detail, setDetail] = useState(null);
  const [job, setJob] = useState(null);
  const [now, setNow] = useState(Date.now());
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: p.id, ...body } });
  const showCmds = async () => { if (detail) { setDetail(null); return; } try { setDetail(await api('/api/community/' + p.pid)); } catch (e) { toast(e.message, true); } };
  useEffect(() => {
    if (!job || job.done) return;
    const t = setInterval(async () => { setNow(Date.now());
      try { const j = await call({ op: 'job', job: job.id }); setJob(x => ({ ...x, ...j })); if (j.done) { toast(j.error ? 'Не получилось: ' + j.error : (j.result && j.result.message) || 'Готово', !!j.error); reload(); } } catch (e) { }
    }, 3000);
    return () => clearInterval(t);
  }, [job && job.id, job && job.done]);
  const missing = (p.fields || []).find(f => f.required && !String(vals[f.id] ?? '').trim() && f.type !== 'switch');
  const run = async op => {
    let d = detail; if (!d) { try { d = await api('/api/community/' + p.pid); setDetail(d); } catch (e) { toast(e.message, true); return; } }
    const perms = (p.permissions || []).map(x => PERM_RU[x]).filter(Boolean);
    const steps = d[op].map((s, i) => `${i + 1}. ${s.title}`).join('\n');
    const ok = await confirm(`${op === 'install' ? 'Установить' : 'Удалить'} «${p.title}» на «${device.name}»?\n\nПлагин: ${p.source === 'community' ? 'из каталога сообщества' : 'загружен вручную, никем не проверен'} · риск ${(RISK_RU[p.risk] || ['?'])[0]}\n`
      + (perms.length ? 'Он ' + perms.join(', ') + '.\n' : '') + ((p.network || []).length ? 'Скачивает с: ' + p.network.join(', ') + '.\n' : '')
      + (p.targets.includes('synology') && device.driver === 'synology' ? 'На Synology команды выполняются от root.\n' : '') + `\nШаги:\n${steps}\n\nКоманды этих шагов показаны ниже на странице (отпечаток ${p.digest.slice(0, 8)}). Выполнить?`,
      { title: 'Плагин сообщества', ok: op === 'install' ? 'Установить' : 'Удалить', danger: op === 'remove' || p.risk === 'high' });
    if (!ok) return;
    try { const r = await call({ op, digest: p.digest, values: vals }); setJob({ id: r.job, stage: 'Запуск…', done: false, t: Date.now() / 1000 }); } catch (e) { toast(e.message, true); }
  };
  const running = job && !job.done;
  return <>
    <div className="row wrap" style={{ gap: 6, marginBottom: 6 }}>
      <RiskBadge risk={p.risk} />
      <span className={'badge' + (p.source === 'community' ? ' online' : '')}>{p.source === 'community' ? 'из каталога сообщества' : 'своё, не проверено'}</span>
      <span className="badge">версия {p.version}</span>{p.author ? <span className="badge">автор: {p.author}</span> : null}
    </div>
    {(p.permissions || []).length || (p.network || []).length ? <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.5, marginBottom: 6 }}>
      Что делает на устройстве: {[...(p.permissions || []).map(x => PERM_RU[x]), (p.network || []).length ? 'скачивает с ' + p.network.join(', ') : null].filter(Boolean).join('; ')}.</div> : null}
    {(p.checks || []).length ? <Checks checks={p.checks} /> : null}
    {(p.info || []).length ? <div className="col" style={{ gap: 4, marginBottom: 6 }}>{p.info.map((i, k) => <div key={k} className="copy-row"><span className="dim">{i.label}</span><span className="grow ellipsis" title={i.value}>{i.value}</span></div>)}</div> : null}
    {(p.warn || []).map((w, i) => <div key={i} className="err-note" style={{ marginTop: 0 }}>{w}</div>)}
    {p.url ? <a className="btn" href={p.url} target="_blank" rel="noreferrer"><Icon name="link" size={16} />Открыть</a> : null}
    {!p.installed && (p.fields || []).length ? <div className="awg-form">{p.fields.map(f => f.type === 'switch'
      ? <div key={f.id} className="row" style={{ alignItems: 'flex-start' }}><Switch on={!!vals[f.id]} onChange={v => setVals({ ...vals, [f.id]: v })} /><div className="grow">{f.label}{f.hint ? <div className="dim3" style={{ fontSize: 12.5 }}>{f.hint}</div> : null}</div></div>
      : <Field key={f.id} label={f.label + (f.required ? ' *' : '')} hint={f.hint}>{f.type === 'select'
        ? <select className="input" value={vals[f.id]} onChange={e => setVals({ ...vals, [f.id]: e.target.value })}>{f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        : <input className="input" type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'} autoComplete="off" value={vals[f.id]} onChange={e => setVals({ ...vals, [f.id]: e.target.value })} />}</Field>)}</div> : null}
    <div className="row wrap" style={{ marginTop: 8 }}>
      {!p.installed ? <Btn kind="primary" icon="download" busy={running} disabled={running || !!missing} onClick={() => run('install')}>{running ? 'Работаю…' : 'Установить'}</Btn> : null}
      {p.installed && p.steps.remove.length ? <Btn kind="danger" icon="trash" disabled={running} onClick={() => run('remove')}>Удалить с устройства</Btn> : null}
      <Btn icon="terminal" onClick={showCmds}>{detail ? 'Скрыть команды' : 'Показать команды'}</Btn>
      {p.home ? <a className="btn" href={p.home} target="_blank" rel="noreferrer"><Icon name="link" size={16} />О плагине</a> : null}
    </div>
    {missing && !p.installed ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 4 }}>Заполните: {missing.label}.</div> : null}
    {detail ? <div className="col" style={{ gap: 8, marginTop: 8 }}>
      {[['status', 'Проверка статуса (только чтение)', detail.status ? [{ title: 'status', script: detail.status }] : []], ['install', 'Установка', detail.install], ['remove', 'Удаление', detail.remove]].filter(x => x[2].length).map(([k, label, steps]) =>
        <div key={k}><div className="card-title">{label}</div>{steps.map((s, i) => <div key={i}><div className="dim3" style={{ fontSize: 12 }}>{s.title}</div><pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 12, background: 'var(--fill)', borderRadius: 10, padding: 10, margin: '4px 0 8px', maxHeight: 260, overflow: 'auto' }}>{s.script}</pre></div>)}</div>)}
      <div className="dim3" style={{ fontSize: 12 }}>Отпечаток: {p.digest}. Значения полей передаются в скрипт переменными окружения (RL_P_…), а не вставляются в текст.</div></div> : null}
    {running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{job.stage}</b>
      <div className="dim3" style={{ fontSize: 12 }}>идёт {Math.max(0, Math.round(now / 1000 - job.t))} с · окно можно закрыть</div></div></div> : null}
    {job && job.done ? (job.error ? <PluginResult r={{ error: job.error, kept: true, log: [] }} /> : <PluginResult r={{ ...job.result, kept: true, up: true }} />) : null}
  </>;
}

/* the manager: catalog of the community · upload · installed · how to write */
function CommunityManager({ onClose }) {
  const toast = useToast(); const confirm = useConfirm();
  const [sec, setSec] = useState('catalog');
  const [idx, setIdx] = useState(null);
  const [list, setList] = useState(null);
  const [rep, setRep] = useState(null);
  const [busy, setBusy] = useState('');
  const fileRef = useRef(null);
  const load = () => { api('/api/community').then(r => setList(r.plugins)).catch(e => toast(e.message, true)); };
  const loadIdx = (refresh) => { setIdx(null); api('/api/community/index' + (refresh ? '?refresh=1' : '')).then(setIdx).catch(e => setIdx({ ok: false, plugins: [], error: e.message })); };
  useEffect(() => { load(); loadIdx(); }, []);
  const upload = async f => {
    if (!f) return; setBusy('upload'); setRep(null);
    try {
      const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: f };
      const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
      const r = await fetch('/api/community/upload', init); const j = await r.json();
      if (!r.ok && !j.errors) throw new Error(j.error || 'ошибка ' + r.status);
      setRep(j); if (j.ok) { load(); loadIdx(); }
    } catch (e) { toast(e.message, true); } finally { setBusy(''); if (fileRef.current) fileRef.current.value = ''; }
  };
  const install = async p => {
    if (!(await confirm(`Добавить в Rack Live плагин «${p.title}» ${p.version} из каталога сообщества? Он только добавится в список: ничего не запустится, пока вы сами не выберете устройство, не прочитаете команды и не подтвердите.`, { title: 'Каталог сообщества', ok: 'Добавить' }))) return;
    setBusy(p.id);
    try { const r = await api('/api/community/install', { method: 'POST', body: { id: p.id } }); setRep(r); if (r.ok) { toast('Плагин добавлен'); load(); loadIdx(); } } catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const remove = async p => {
    if (!(await confirm(`Убрать плагин «${p.title}» из Rack Live? На устройствах он не удаляется — только пропадает из списка.`, { danger: true, ok: 'Убрать' }))) return;
    try { await api('/api/community/' + p.id, { method: 'DELETE' }); load(); loadIdx(); } catch (e) { toast(e.message, true); }
  };
  const Row = ({ p, right }) => <div className="row" style={{ gap: 10, padding: '8px 0', borderTop: '1px solid var(--line)', alignItems: 'flex-start' }}>
    <div className="grow" style={{ minWidth: 0 }}><b>{p.title}</b> <span className="dim3" style={{ fontSize: 12.5 }}>{p.version}{p.author ? ' · ' + p.author : ''}</span>
      <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4 }}>{p.description}</div>
      <div className="row wrap" style={{ gap: 4, marginTop: 4 }}>{p.risk ? <RiskBadge risk={p.risk} /> : null}{(p.targets || []).map(t => <span key={t} className="badge">{TARGET_RU[t] || t}</span>)}</div></div>{right}</div>;
  return <Modal title="Плагины сообщества" wide onClose={onClose} icon={<Icon name="box" size={20} color="var(--accent)" />}>
    <Seg value={sec} onChange={s => { setSec(s); setRep(null); }} options={[{ value: 'catalog', label: 'Каталог' }, { value: 'upload', label: 'Загрузить' }, { value: 'mine', label: 'Мои' + (list ? ` · ${list.length}` : '') }, { value: 'how', label: 'Как написать' }]} />
    <div style={{ marginTop: 10 }}>
      {sec === 'catalog' ? (!idx ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю каталог…</div> : <>
        {!idx.ok ? <div className="err-note" style={{ marginTop: 0 }}>{idx.error || 'Каталог недоступен.'} <Btn size="sm" onClick={() => loadIdx(true)}>Повторить</Btn></div>
          : !idx.plugins.length ? <div className="dim" style={{ fontSize: 13.5 }}>В каталоге пока нет плагинов. Станьте первым: сделайте плагин и отправьте его в репозиторий racklive-plugins.</div> : null}
        {idx.plugins.map(p => <Row key={p.id} p={p} right={(idx.installed || {})[p.id] === p.version ? <span className="badge online">добавлен</span>
          : <Btn size="sm" kind="primary" busy={busy === p.id} onClick={() => install(p)}>{(idx.installed || {})[p.id] ? 'Обновить' : 'Добавить'}</Btn>} />)}
        <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Каталог — отдельный репозиторий на GitHub. Каждый плагин в нём принят после просмотра, а Rack Live сверяет контрольную сумму архива и заново проверяет его так же строго, как загруженный вручную.</div></>) : null}
      {sec === 'upload' ? <>
        <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Выберите .zip с плагином. Rack Live проверит его: запрещённые действия, всё ли объявлено (права и серверы, с которых скачивается), нет ли лишнего. Если проверка пройдена, плагин <b>добавится в список</b>, но ничего не запустится, пока вы не выберете устройство и не подтвердите команды.</div>
        <input ref={fileRef} type="file" accept=".zip,application/zip" style={{ display: 'none' }} onChange={e => upload(e.target.files[0])} />
        <div style={{ marginTop: 10 }}><Btn kind="primary" icon="plus" busy={busy === 'upload'} onClick={() => fileRef.current && fileRef.current.click()}>Выбрать .zip</Btn></div></> : null}
      {sec === 'mine' ? (!list ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />…</div> : !list.length ? <div className="dim" style={{ fontSize: 13.5 }}>Пока нет. Добавьте из каталога или загрузите свой.</div>
        : list.map(p => <Row key={p.id} p={p} right={<Btn size="sm" kind="danger" icon="trash" onClick={() => remove(p)} />} />)) : null}
      {sec === 'how' ? <>
        <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.55 }}>Плагин — это не программа, а <b>описание</b>: форма для человека и несколько shell-шагов. Он не может ничего сломать в самом Rack Live — выполняется только на выбранном устройстве и только после вашего подтверждения.
          Как сделать свой: скачайте инструкцию, отдайте её нейросети вместе с описанием задачи («плагин, который ставит X на мой сервер»), загрузите полученный архив во вкладке «Загрузить» и исправьте ошибки по отчёту.</div>
        <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
          <a className="btn" href="/api/community/guide.txt" download>Инструкция для нейросети (.txt)</a>
          <a className="btn" href="/api/community/template.zip" download>Пример плагина (.zip)</a></div>
        <div className="dim3" style={{ fontSize: 12.5, marginTop: 10, lineHeight: 1.5 }}>Отклоняется сразу: форматирование дисков, пользователи и пароли, SSH-ключи, выключение, сброс файрвола, обратные оболочки, отправка секретов наружу, скрытые команды.
          Всё остальное нужно объявить (permissions, network) — иначе плагин не пройдёт. Риск считается автоматически и показывается перед установкой.</div></> : null}
      {rep ? <div style={{ marginTop: 12 }}>
        {rep.ok ? <div className="plugin-result"><Icon name="check" size={16} /> <b>Проверка пройдена.</b> Плагин «{rep.plugin.title}» {rep.plugin.version} добавлен · <RiskBadge risk={rep.plugin.risk} /></div>
          : <div className="err-note" style={{ marginTop: 0 }}><b>Плагин не принят:</b><ul style={{ margin: '6px 0 0 18px' }}>{(rep.errors || []).map((e, i) => <li key={i}>{e}</li>)}</ul></div>}
        {(rep.warnings || []).length ? <div className="dim" style={{ fontSize: 12.5, marginTop: 6 }}><b>Замечания:</b><ul style={{ margin: '4px 0 0 18px' }}>{rep.warnings.map((e, i) => <li key={i}>{e}</li>)}</ul></div> : null}
      </div> : null}
    </div>
  </Modal>;
}
