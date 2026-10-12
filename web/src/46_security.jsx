/* Security advisor: findings with a one-click fix where it is safe, instructions otherwise, «это нормально» to hide */
const SEC_LEVEL = { bad: 'Критично', warn: 'Стоит исправить', info: 'К сведению' };

function SecurityItem({ f, onFix, onIgnore, hidden }) {
  const [open, setOpen] = useState(false);
  const [col, icon] = CHECK_LOOK[f.level] || CHECK_LOOK.info;
  return <div className={'li sec-item' + (hidden ? ' hidden' : '')}>
    <div className="check-ic" style={{ color: col, background: `color-mix(in srgb, ${col} 14%, transparent)` }}><Icon name={f.level === 'info' ? 'other' : 'shield'} size={16} /></div>
    <div className="grow" style={{ minWidth: 0 }}>
      <button type="button" className="sec-title" onClick={() => setOpen(!open)}><span className="grow">{f.title}</span>
        <Icon name="chevron" size={14} style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s', flexShrink: 0 }} /></button>
      {open ? <div className="col" style={{ gap: 8, marginTop: 6 }}>
        <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>{f.text}</div>
        {f.how ? <div style={{ fontSize: 13, lineHeight: 1.45 }}><b>Как исправить: </b>{f.how}</div> : null}
        <div className="row wrap" style={{ gap: 6 }}>
          {f.fix && onFix && !hidden ? <Btn size="sm" kind="primary" icon="check" onClick={() => onFix(f)}>{f.fix.label}</Btn> : null}
          {onIgnore ? <Btn size="sm" onClick={() => onIgnore(f, !hidden)}>{hidden ? 'Снова показывать' : 'Это нормально, не показывать'}</Btn> : null}
        </div></div> : null}
    </div></div>;
}

function SecurityBody({ s }) {
  const { data, refresh, applyState } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [showHidden, setShowHidden] = useState(false);
  const fix = async f => {
    if (!(await confirm(f.fix.confirm || f.fix.label + '?', { title: 'Исправить', ok: f.fix.label }))) return;
    try { const r = await api(`/api/devices/${f.deviceId}/action`, { method: 'POST', body: { action: f.fix.action, params: f.fix.params } });
      toast('✓ ' + (r.message || 'Готово')); refresh(); setTimeout(refresh, 6000); }
    catch (e) { toast(e.message, true); }
  };
  const ignore = async (f, on) => {
    try { await api('/api/security/ignore', { method: 'POST', body: { id: f.id, ignore: on } }); toast(on ? 'Скрыто — на оценку больше не влияет' : 'Снова показывается'); refresh(); }
    catch (e) { toast(e.message, true); }
  };
  const groups = ['bad', 'warn', 'info'].map(l => [l, s.findings.filter(f => f.level === l)]).filter(([, x]) => x.length);
  return <div className="health">
    <div className="row" style={{ gap: 16, alignItems: 'center' }}>
      <ScoreRing score={s.score} />
      <div className="grow" style={{ minWidth: 0 }}>
        <div style={{ fontSize: 18, fontWeight: 750, letterSpacing: '-.3px' }}>{s.findings.length ? s.counts.bad ? 'Есть критичные проблемы' : 'Есть что улучшить' : 'Всё хорошо'}</div>
        <div className="dim" style={{ fontSize: 13, marginTop: 3 }}>{['bad', 'warn', 'info'].filter(l => s.counts[l]).map(l => `${SEC_LEVEL[l].toLowerCase()}: ${s.counts[l]}`).join(' · ') || 'Rack Live не нашёл открытых портов, паролей по умолчанию и небезопасных протоколов.'}</div>
      </div>
    </div>
    <Hint id="security">Rack Live проверяет то, что видит сам: пробросы портов и удалённый доступ к роутеру, пароли по умолчанию, telnet и SNMP, прошивки.
      Где безопасно — есть кнопка «Исправить»; где нет — инструкция. Если что-то открыто специально, нажмите «Это нормально» — пункт уйдёт из оценки.</Hint>
    <ExtScanBox />
    {groups.map(([l, list]) => <div key={l}>
      <div className="card-title" style={{ marginBottom: 6 }}>{SEC_LEVEL[l]} · {list.length}</div>
      <div className="list">{list.map(f => <SecurityItem key={f.id} f={f} onFix={fix} onIgnore={ignore} />)}</div>
    </div>)}
    {s.ignored.length ? <div>
      <button className="link-btn" onClick={() => setShowHidden(!showHidden)}><Icon name="chevron" size={13} style={{ transform: showHidden ? 'rotate(90deg)' : '' }} />Скрытые («это нормально») · {s.ignored.length}</button>
      {showHidden ? <div className="list">{s.ignored.map(f => <SecurityItem key={f.id} f={f} onIgnore={ignore} hidden />)}</div> : null}
    </div> : null}
  </div>;
}

/* outside port check: an SSH server outside the home knocks on the home public IP */
function ExtScanBox() {
  const { data, refresh } = useApp(); const toast = useToast();
  const x = data.extscan;
  useEffect(() => { if (!x || !x.running) return; const t = setInterval(refresh, 4000); return () => clearInterval(t); }, [x && x.running]);
  if (!x) return null;
  const servers = data.devices.filter(d => d.driver === 'ssh' || d.driver === 'demo_server');
  const run = async () => { try { await api('/api/extscan/run', { method: 'POST', body: {} }); toast('Проверка снаружи началась'); setTimeout(refresh, 1500); } catch (e) { toast(e.message, true); } };
  const pick = async id => { try { await api('/api/extscan', { method: 'PUT', body: { device: id } }); refresh(); } catch (e) { toast(e.message, true); } };
  return <div className="awg-form">
    <div className="row wrap" style={{ gap: 8 }}><Icon name="globe" size={17} color="var(--accent)" /><b className="grow">Проверка снаружи</b>
      {servers.length ? <Btn size="sm" kind="primary" icon="refresh" busy={x.running} onClick={run}>{x.running ? 'Проверяю…' : 'Проверить сейчас'}</Btn> : null}</div>
    {!servers.length ? <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>Изнутри своей сети нельзя честно проверить, что видно из интернета. Добавьте любой VPS как
      «Сервер / VPS по SSH» — с него Rack Live раз в сутки «постучится» на ваш внешний IP и покажет, какие порты действительно открыты.</div> : <>
      {servers.length > 1 ? <div className="row wrap" style={{ gap: 6 }}><span className="dim" style={{ fontSize: 13 }}>Проверять с:</span>
        {servers.map(d => <button key={d.id} type="button" className={'chip' + (x.scanner && x.scanner.id === d.id ? ' on' : '')} onClick={() => pick(d.id)}>{d.name}</button>)}</div> : null}
      {x.t ? x.error ? <div style={{ color: 'var(--red)', fontSize: 13 }}>{x.error}</div>
        : <div style={{ fontSize: 13.5, lineHeight: 1.45 }}>{fmt.ago(x.t, data.now)} с «{x.viaName}» на {x.ip}: проверено {x.checked.length} портов,{' '}
          {x.open.length ? <>открыто <b>{x.open.length}</b>: <span className="mono">{x.open.join(', ')}</span></> : <b style={{ color: 'var(--green)' }}>ничего не открыто</b>}.
          <div className="dim3" style={{ fontSize: 12 }}>Открытые порты учтены в замечаниях ниже: «✔ проверено снаружи» или отдельный пункт, если проброса для порта нет.</div></div>
        : <div className="dim3" style={{ fontSize: 13 }}>Проверок ещё не было — «Проверить сейчас» или подождите, проверка идёт раз в сутки.</div>}</>}
  </div>;
}

function SecurityCard() {
  const { data } = useApp();
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('security') === '1');
  const s = data.security; if (!s) return null;
  const top = s.findings.filter(f => f.level !== 'info').slice(0, 2);
  return <>
    <Card title="Безопасность" right={<Btn size="sm" onClick={() => setOpen(true)}>Подробнее</Btn>}>
      <div className="row" style={{ gap: 14, cursor: 'pointer' }} onClick={() => setOpen(true)}>
        <ScoreRing score={s.score} size={58} />
        <div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 700 }}>{s.counts.bad ? `Критично: ${s.counts.bad}` : s.counts.warn ? 'Есть что улучшить' : 'Серьёзных проблем нет'}</div>
          <div className="dim" style={{ fontSize: 12.5 }}>Открытые порты, пароли, протоколы, прошивки</div></div>
      </div>
      {top.length ? <div className="list" style={{ marginTop: 8 }}>{top.map(f => <CheckItem key={f.id} c={{ level: f.level, title: f.title }} onClick={null} />)}</div> : null}
    </Card>
    {open ? <Modal title="Безопасность сети" wide onClose={() => setOpen(false)} icon={<Icon name="shield" size={20} color="var(--accent)" />}><SecurityBody s={s} /></Modal> : null}
  </>;
}
