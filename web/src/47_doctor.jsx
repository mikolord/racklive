/* «Сетевой доктор»: a checkup of one chosen device. Backend: rackd/doctor.py (/api/doctor*).
   «Не проверено» is shown as such: a check that could not look is never painted green. */
const DOC_STATE = { ok: ['var(--green)', 'check', 'в порядке'], warn: ['var(--orange)', 'alert', 'стоит исправить'], bad: ['var(--red)', 'alert', 'проблема'],
  unknown: ['var(--text3)', 'other', 'не проверено'], na: ['var(--text3)', 'minus', 'не относится'] };
const DOC_EXPOSURE = { all: 'на всех адресах', lan: 'только в локальной сети', local: 'только на самом устройстве' };

function DoctorTool() {
  const { refresh: refreshApp } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [list, setList] = useState(null);
  const [cur, setCur] = useState(() => new URLSearchParams(location.search).get('docdev') || lsGet('rl_doctor_dev', ''));
  const [rep, setRep] = useState(null);
  const [job, setJob] = useState(null);
  const [showHidden, setShowHidden] = useState(false);
  const load = async () => { try { const r = await api('/api/doctor'); setList(r.devices); return r.devices; } catch (e) { toast(e.message, true); return []; } };
  const loadRep = async id => { if (!id) return setRep(null); try { setRep(await api('/api/doctor/' + id)); } catch (e) { if (e.status === 404) setRep(null); else toast(e.message, true); } };
  useEffect(() => { load().then(ds => { const d = ds.find(x => x.id === cur); if (d && d.job) setJob({ id: d.job, device: d.id, stage: 'Идёт проверка…' }); }); }, []);
  useEffect(() => { lsSet('rl_doctor_dev', cur || ''); setRep(null); loadRep(cur); }, [cur]);
  useEffect(() => {
    if (!job) return;
    const t = setInterval(async () => {
      try { const j = await api('/api/doctor/job', { method: 'POST', body: { job: job.id } }); setJob(x => x && ({ ...x, ...j }));
        if (j.done) { setJob(null); if (j.error) toast(j.error, true); else if (j.message) toast('✓ ' + j.message); await loadRep(job.device); load(); } } catch (e) { }
    }, 1500);
    return () => clearInterval(t);
  }, [job && job.id]);
  const start = async (fix, full) => { if (!cur) return;
    try { const r = await api('/api/doctor/run', { method: 'POST', body: { device: cur, fix, full } }); setJob({ id: r.job, device: cur, stage: 'Запуск…', full }); } catch (e) { toast(e.message, true); } };
  const startFull = async () => {
    if (await confirm('Проверить все 65535 портов TCP? Займёт до 8 минут. Настройки не меняются, а проверка ловит то, чего нет в настройках роутера. Запрос идёт с вашего VPS или из Rack Live, в журнале устройства это выглядит как сканирование портов.', { title: 'Полная проверка', ok: 'Проверить' })) start(undefined, true);
  };
  const doFix = async f => {
    if (!(await confirm(f.fix.confirm || f.fix.label + '?', { title: 'Исправить', ok: f.fix.label }))) return;
    if (f.fix.kind === 'doctor') return start(f.fix.id);
    try { const r = await api(`/api/devices/${f.deviceId}/action`, { method: 'POST', body: { action: f.fix.action, params: f.fix.params } }); toast('✓ ' + (r.message || 'Готово')); refreshApp(); start(); }
    catch (e) { toast(e.message, true); }
  };
  const ignore = async (f, on) => { try { await api('/api/security/ignore', { method: 'POST', body: { id: f.id, ignore: on } }); toast(on ? 'Скрыто: на оценку больше не влияет' : 'Снова показывается'); loadRep(cur); load(); } catch (e) { toast(e.message, true); } };
  if (!list) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  const dev = list.find(d => d.id === cur);
  const running = job && job.device === cur;
  const groups = rep ? ['bad', 'warn', 'info'].map(l => [l, rep.findings.filter(f => f.level === l)]).filter(([, x]) => x.length) : [];
  const allGreen = rep && !rep.findings.length;
  const unknown = rep ? rep.checks.filter(c => c.state === 'unknown').length : 0;
  return <div className="col" style={{ gap: 14 }}>
    <Hint id="doctor">Выберите устройство: доктор посмотрит открытые порты, вход по SSH, fail2ban, файрвол, обновления и учётные записи. Проверка ничего не меняет.
      Исправляет только по вашей кнопке и с подтверждением. Для остального даёт готовые команды.</Hint>
    <Card title="Устройство">
      <div className="row wrap" style={{ gap: 8 }}>
        <select className="input select grow" style={{ minWidth: 200, flexBasis: 240 }} value={cur} disabled={!!running} onChange={e => setCur(e.target.value)}>
          <option value="">Выберите устройство…</option>
          {list.map(d => <option key={d.id} value={d.id}>{nameNoFlag(d.name)}{d.last ? ` · ${d.last.score} из 100` : ''}</option>)}
        </select>
        <Btn kind="primary" icon="shield" disabled={!cur || !!running} busy={!!running} onClick={() => start()}>{running ? 'Проверяю…' : rep ? 'Проверить снова' : 'Проверить'}</Btn>
        {dev && dev.fullable ? <Btn icon="search" disabled={!!running} onClick={startFull}>Полная проверка</Btn> : null}
      </div>
      {dev ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 8 }}>Как проверяется: {dev.accessNote}.</div> : null}
    </Card>
    {running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{job.stage}</b><div className="dim3" style={{ fontSize: 12 }}>{job.full ? 'до 8 минут · окно можно закрыть, проверка продолжится на сервере' : 'обычно до минуты'}</div></div></div> : null}
    {rep ? <>
      <Card>
        <div className="row" style={{ gap: 16, alignItems: 'center' }}>
          <ScoreRing score={rep.score} />
          <div className="grow" style={{ minWidth: 0 }}>
            <div style={{ fontSize: 18, fontWeight: 750, letterSpacing: '-.3px' }}>{rep.counts.bad ? 'Есть критичные проблемы' : rep.counts.warn ? 'Есть что улучшить' : unknown ? (allGreen ? 'Проблем не найдено, но проверено не всё' : 'Серьёзных проблем нет, но проверено не всё') : allGreen ? 'Проблем не найдено' : 'Серьёзных проблем нет'}</div>
            <div className="dim" style={{ fontSize: 13, marginTop: 3 }}>{[rep.facts.os, fmt.ago(rep.t, Date.now() / 1000)].filter(Boolean).join(' · ')}{rep.facts.fails24h != null ? ` · неудачных входов за сутки: ${rep.facts.fails24h}` : ''}</div>
          </div>
        </div>
        {rep.errors && rep.errors.length ? <div className="err-note">{rep.errors.join(' ')}</div> : null}
        {rep.access !== 'inside' ? <div className="dim" style={{ fontSize: 13, marginTop: 10 }}>Глубина проверки ограничена: {rep.accessNote}. Оценка учитывает только то, что удалось посмотреть.</div> : null}
        {rep.findings.length ? <div style={{ marginTop: 10 }}><AskAi label="Что исправить в первую очередь?" q={`Сетевой доктор проверил устройство «${dev ? dev.name : ''}» и нашёл: ${rep.findings.map(f => f.title).join('; ')}. Что исправить в первую очередь и как, по шагам?`} /></div> : null}
      </Card>
      {rep.outside ? <Card title={`Открыто в интернет · ${rep.outside.rows.length}`}>
        {rep.outside.error ? <div style={{ color: 'var(--orange)', fontSize: 13, marginBottom: 6 }}>Свежей проверки снаружи нет: {rep.outside.error}. Ниже только пробросы из настроек роутера.</div>
          : <div className="dim3" style={{ fontSize: 12.5, marginBottom: 6 }}>С «{rep.outside.via}» на внешний адрес роутера, {fmt.ago(rep.outside.t, Date.now() / 1000)}: {rep.outside.full ? 'проверены все порты TCP' : `проверено портов TCP ${rep.outside.checked}, самые вероятные`}. UDP снаружи проверить нельзя.</div>}
        {rep.outside.fullError ? <div style={{ color: 'var(--orange)', fontSize: 13, marginBottom: 6 }}>Полная проверка не удалась: {rep.outside.fullError}. Показан обычный список.</div> : null}
        {rep.outside.rows.length ? <div className="list">{rep.outside.rows.map(r => <div key={r.proto + r.port} className="li" style={{ gap: 8 }}>
          <b className="mono" style={{ minWidth: 92 }}>{r.port}<span className="dim3" style={{ fontWeight: 400 }}>/{r.proto}</span></b>
          <span className="grow" style={{ minWidth: 0 }}><span className="ellipsis" style={{ display: 'block' }}>{r.name || (r.forward ? 'проброс без названия' : 'неизвестно, кто открыл')}</span>
            <span className="dim3 ellipsis" style={{ display: 'block', fontSize: 12 }}>{r.forward ? `проброс → ${r.target}` : 'проброса нет: сервис роутера или UPnP'}</span></span>
          {r.answers === true ? <span className="badge warning">отвечает</span> : r.answers === false ? <span className="badge">не отвечает</span> : <span className="badge">не проверено</span>}</div>)}</div>
          : <div className="dim" style={{ fontSize: 13 }}>Ни один проверенный порт снаружи не отвечает, пробросов нет.</div>}
      </Card> : null}
      <Card title="Что проверено"><div className="checks">{rep.checks.map(c => { const [col, ic, word] = DOC_STATE[c.state] || DOC_STATE.unknown;
        return <div key={c.id} className="row" style={{ gap: 8, alignItems: 'flex-start', padding: '5px 0' }}>
          <Icon name={ic} size={15} color={col} style={{ marginTop: 2, flexShrink: 0 }} />
          <span className="grow" style={{ minWidth: 0 }}><b style={{ fontWeight: 600 }}>{c.label}</b><span className="dim" style={{ fontSize: 13 }}> · {c.note || word}</span></span>
          <span className="dim3" style={{ fontSize: 12, flexShrink: 0 }}>{word}</span></div>; })}</div></Card>
      {groups.map(([l, items]) => <div key={l}>
        <div className="card-title" style={{ marginBottom: 6 }}>{SEC_LEVEL[l]} · {items.length}</div>
        <div className="list">{items.map(f => <SecurityItem key={f.id} f={f} onFix={doFix} onIgnore={ignore} />)}</div>
      </div>)}
      {rep.ignored.length ? <div>
        <button className="link-btn" onClick={() => setShowHidden(!showHidden)}><Icon name="chevron" size={13} style={{ transform: showHidden ? 'rotate(90deg)' : '' }} />Скрытые («это нормально») · {rep.ignored.length}</button>
        {showHidden ? <div className="list">{rep.ignored.map(f => <SecurityItem key={f.id} f={f} onIgnore={ignore} hidden />)}</div> : null}
      </div> : null}
      {rep.ports.length ? <Card title={`${rep.outside ? 'Порты самого роутера' : 'Порты'} · ${rep.ports.length}`}>
        <div className="dim3" style={{ fontSize: 12.5, marginBottom: 6 }}>{rep.outside ? 'Что слушает сам роутер. Это ещё не значит, что порт открыт наружу: что видно из интернета, показано в карточке выше.'
          : <>«Отвечает» значит, что {rep.fullVia ? `«${rep.fullVia}»` : 'Rack Live'} смог подключиться{rep.fullVia ? ' (проверены все порты TCP)' : rep.knocked ? ` (проверено портов TCP: ${rep.knocked})` : ''}. UDP снаружи не проверяется.</>}</div>
        <div className="list">{rep.ports.map(p => <div key={p.proto + p.port} className="li" style={{ gap: 8 }}>
          <b className="mono" style={{ minWidth: 76 }}>{p.port}/{p.proto}</b>
          <span className="grow" style={{ minWidth: 0 }}><span className="ellipsis" style={{ display: 'block' }}>{p.proc || 'программа неизвестна'}{p.count ? ` · портов: ${p.count}` : ''}</span>
            <span className="dim3" style={{ fontSize: 12 }}>{p.addr === '' ? 'найден только снаружи' : DOC_EXPOSURE[p.exposure]}</span></span>
          {p.opened ? <span className={'badge ' + (rep.facts.exposed ? 'warning' : '')}>отвечает</span> : null}</div>)}</div>
      </Card> : null}
    </> : cur && !running ? <div className="dim" style={{ fontSize: 13 }}>Это устройство ещё не проверялось.</div> : null}
  </div>;
}
