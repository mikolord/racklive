/* «Проверка VPN»: does a VPN work from this network right now. Backend: rackd/vpncheck.py (/api/vpncheck*).
   The pasted text goes to the server once and is cleared here; reports hold no identifier, password or key. */
const VC_STATE = { ok: ['var(--green)', 'check'], warn: ['var(--orange)', 'alert'], bad: ['var(--red)', 'alert'], unknown: ['var(--text3)', 'other'], info: ['var(--text3)', 'other'] };
const vcNum = (x, unit) => x == null ? '—' : `${x < 10 ? x : Math.round(x)} ${unit}`;
const vcSec = s => s === 'reality' ? 'Reality' : s === 'tls' ? 'TLS' : s === 'none' ? 'без шифрования снаружи' : s;

function VcRow({ state, label, value }) {
  const [col, ic] = VC_STATE[state] || VC_STATE.unknown;
  return <div className="row" style={{ gap: 8, alignItems: 'flex-start', padding: '4px 0' }}>
    <Icon name={ic} size={15} color={col} style={{ marginTop: 2, flexShrink: 0 }} />
    <span className="grow" style={{ minWidth: 0, overflowWrap: 'anywhere' }}><b style={{ fontWeight: 600 }}>{label}</b><span className="dim" style={{ fontSize: 13 }}> · {value}</span></span>
  </div>;
}

function VcSpeeds({ m, base }) {
  const cell = (title, val, cmp) => <div style={{ flex: '1 1 92px', minWidth: 0 }}>
    <div className="dim3" style={{ fontSize: 12 }}>{title}</div>
    <div style={{ fontSize: 17, fontWeight: 700 }}>{val}</div>
    {cmp ? <div className="dim3" style={{ fontSize: 11.5 }}>{cmp}</div> : null}
  </div>;
  return <div className="row wrap" style={{ gap: 10, margin: '6px 0' }}>
    {cell('Задержка', vcNum(m.ms, 'мс'), base && base.ms != null ? `напрямую ${vcNum(base.ms, 'мс')}` : null)}
    {cell('Загрузка', vcNum(m.down, 'Мбит/с'), base && base.down != null ? `напрямую ${vcNum(base.down, 'Мбит/с')}` : null)}
    {cell('Отдача', vcNum(m.up, 'Мбит/с'), base && base.up != null ? `напрямую ${vcNum(base.up, 'Мбит/с')}` : null)}
  </div>;
}

function VcItem({ it, base }) {
  const v = it.verdict || {}; const [col, ic] = VC_STATE[v.state] || VC_STATE.unknown;
  const t = it.tunnel || {};
  const place = [it.countryName, it.org].filter(Boolean).join(' · ');
  const sc = it.score; const scCol = !sc ? 'var(--text3)' : sc.value >= 8 ? 'var(--green)' : sc.value >= 5 ? 'var(--orange)' : 'var(--red)';
  return <Card>
    <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
      <Icon name={ic} size={20} color={col} style={{ marginTop: 2, flexShrink: 0 }} />
      <div className="grow" style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>{it.name || it.host}</div>
        <div style={{ fontSize: 14, marginTop: 2 }}>{v.text}</div>
      </div>
      {sc ? <div style={{ textAlign: 'right', flexShrink: 0 }}><div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1, color: scCol }}>{String(sc.value).replace('.', ',')}</div><div className="dim3" style={{ fontSize: 11.5, marginTop: 2 }}>из 10</div></div> : null}
    </div>
    {sc ? <details style={{ marginTop: 8 }}>
      <summary className="dim" style={{ fontSize: 13, cursor: 'pointer' }}>Из чего сложилась оценка</summary>
      <div style={{ marginTop: 4 }}>{sc.parts.map(x => <div key={x.label} className="row" style={{ gap: 8, padding: '3px 0', fontSize: 13 }}>
        <b className="mono" style={{ minWidth: 58, flexShrink: 0 }}>{String(x.got).replace('.', ',')} / {x.max}</b>
        <span className="grow" style={{ minWidth: 0, overflowWrap: 'anywhere' }}><b style={{ fontWeight: 600 }}>{x.label}</b><span className="dim"> · {x.note}</span></span></div>)}
        {sc.limits.map(x => <div key={x} style={{ color: 'var(--orange)', fontSize: 13, marginTop: 3 }}>Ограничение: {x}.</div>)}
        <div className="dim3" style={{ fontSize: 12, marginTop: 4 }}>Это ориентир по правилам Rack Live, а не замер ТСПУ и не гарантия.</div>
      </div>
    </details> : null}
    <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
      <span className="badge">{it.awg ? `AmneziaWG ${it.awg.version}` : it.proto}</span><span className="badge">{it.kind}</span>
      {it.net && it.net !== 'udp' ? <span className="badge">{it.net}</span> : null}
      {it.net !== 'udp' ? <span className="badge">{vcSec(it.security)}</span> : null}
      <span className="badge">порт {it.port}</span>
      {it.cdn ? <span className="badge">CDN {it.cdn}</span> : null}
    </div>
    {t.state === 'ok' ? <VcSpeeds m={t} base={base} /> : null}
    <div style={{ marginTop: 6 }}>
      {place ? <VcRow state="info" label="Сервер" value={`${it.host}${it.ip && it.ip !== it.host ? ` (${it.ip})` : ''} · ${place}`} /> : null}
      {it.awg ? <VcRow state="info" label={`Версия AmneziaWG: ${it.awg.version}`} value={`${it.awg.note}${it.awg.mimicry ? ' Имитация других протоколов (I1) включена.' : ''} Определено по параметрам настроек.`} /> : null}
      {it.decoy ? <VcRow state={it.decoy.state} label="Сайт-заглушка" value={it.decoy.text} /> : null}
      {(it.neighbours || []).map(n => <VcRow key={n.port} state={n.state} label={`Порт ${n.port} этого сервера`} value={n.text} />)}
      {it.route ? <VcRow state={it.route.state === 'direct' ? 'ok' : it.route.state === 'vpn' ? 'warn' : 'unknown'} label="Путь до сервера" value={it.route.note} /> : null}
      {it.sni ? <VcRow state="info" label="Имя сайта (SNI)" value={it.sni} /> : null}
      {it.ping ? <VcRow state="info" label="Ping" value={it.ping.avg != null ? `${it.ping.avg} мс, потери ${it.ping.loss}%` : 'не отвечает (для VPN это не страшно)'} /> : null}
      {it.tcp ? <VcRow state={it.tcp.ok ? 'ok' : 'bad'} label="Соединение" value={it.tcp.ok ? `${it.tcp.ms} мс, удачно ${it.tcp.okCount} из ${it.tcp.tries}` : it.tcp.error || 'нет'} /> : null}
      {it.tls ? <VcRow state={it.tls.reached ? 'ok' : 'bad'} label="TLS" value={it.tls.reached ? [`отвечает за ${it.tls.ms} мс`, it.tls.version, it.tls.trusted === true ? `сертификат настоящий (${it.tls.issuer || 'издатель неизвестен'})` : 'сертификат не подтверждён'].filter(Boolean).join(', ') : it.tls.error || 'нет ответа'} /> : null}
      {it.block && it.block.state !== 'ok' && it.block.text !== v.text ? <VcRow state={it.block.state} label="Путь" value={it.block.text} /> : null}
      <VcRow state={t.state === 'ok' ? (t.freeze ? 'bad' : t.stalled ? 'warn' : 'ok') : t.state === 'fail' ? 'bad' : 'unknown'} label="Туннель"
        value={t.state === 'ok' ? `страница открылась ${t.okCount} из ${t.tries}, первая за ${vcNum(t.firstMs, 'мс')}${t.stalled ? `, загрузка встала на ${Math.round((t.stallAt || 0) / 1024)} КБ` : ''}${t.downError ? `, скорость не измерена (${t.downError})` : ''}` : (t.note || 'не проверен') + (t.detail ? ` ${t.detail}` : '')} />
      {t.exit ? <VcRow state="info" label="Выход в интернет" value={`${t.exit}${t.exitCountryName ? ` · ${t.exitCountryName}` : ''}${t.exitOrg ? ` · ${t.exitOrg}` : ''}${t.exitSame ? '' : ' · не тот адрес, к которому подключаемся'}`} /> : null}
      {(it.cdns || []).map(c => <VcRow key={c.name} state={c.error || (c.tls && !c.tls.reached) || (c.volume && !c.volume.ok) ? 'bad' : c.tunnel && c.tunnel.state === 'fail' ? 'warn' : 'ok'} label={`CDN${c.cdn ? ' ' + c.cdn : ''}`}
        value={c.error ? `${c.name}: ${c.error}` : [c.name, c.tls && (c.tls.reached ? `TLS за ${c.tls.ms} мс` : `TLS: ${c.tls.error || 'нет ответа'}`), c.volume && (c.volume.ok ? '256 КБ загружено, обрыва нет' : `встало на ${Math.round(c.volume.bytes / 1024)} КБ`), c.volume && c.volume.way === 'vpn' ? 'замер прошёл через ваш VPN, про провайдера не говорит' : '', c.tunnel && (c.tunnel.state === 'ok' ? `туннель через CDN работает, ${vcNum(c.tunnel.down, 'Мбит/с')}` : `туннель через CDN не поднялся`), !c.cdn ? 'CDN по адресу не определён' : ''].filter(Boolean).join(' · ')} />)}
    </div>
    {it.advice && it.advice.length ? <div style={{ marginTop: 8 }}>
      <div className="dim3" style={{ fontSize: 12.5 }}>Что выдаёт подключение (общие правила, не замер):</div>
      {it.advice.map((a, i) => <VcRow key={i} state={a.level} label={a.level === 'bad' ? 'Заметно' : a.level === 'warn' ? 'Стоит поправить' : 'К сведению'} value={a.text} />)}
    </div> : null}
  </Card>;
}

function VpnCheckTool() {
  const toast = useToast();
  const [text, setText] = useState(''); const [cdn, setCdn] = useState('');
  const [rep, setRep] = useState(null); const [job, setJob] = useState(null); const [ready, setReady] = useState(false); const [hasXray, setHasXray] = useState(true);
  const load = async () => { try { const r = await api('/api/vpncheck'); setRep(r.report); setHasXray(r.hasXray); if (r.job) setJob(j => j || { id: r.job, stage: 'Идёт проверка…' }); } catch (e) { toast(e.message, true); } setReady(true); };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!job) return;
    const t = setInterval(async () => {
      try { const j = await api('/api/vpncheck/job', { method: 'POST', body: { job: job.id } }); setJob(x => x && ({ ...x, ...j }));
        if (j.done) { setJob(null); if (j.error) toast(j.error, true); load(); } } catch (e) { }
    }, 1500);
    return () => clearInterval(t);
  }, [job && job.id]);
  const start = async () => {
    try { const r = await api('/api/vpncheck/run', { method: 'POST', body: { text, cdn } }); setJob({ id: r.job, stage: 'Запуск…' }); setText(''); } catch (e) { toast(e.message, true); }
  };
  if (!ready) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  const p = rep && rep.path; const b = rep && rep.base;
  return <div className="col" style={{ gap: 14 }}>
    <Hint id="vpncheck">Показывает, работает ли подключение из этой сети и у этого провайдера прямо сейчас, какие у него задержка и скорость и что в настройках его выдаёт. Гарантии от ТСПУ нет ни у кого: у другого провайдера и завтра результат может быть другим.</Hint>
    <Card title="Подключение">
      <textarea className="input" rows={4} autoComplete="off" spellCheck={false} style={{ width: '100%', fontFamily: 'var(--mono, monospace)', fontSize: 13, resize: 'vertical' }} value={text} disabled={!!job} onChange={e => setText(e.target.value)}
        placeholder={'vless://… vmess://… trojan://… ss://… socks://… hysteria2://… tuic://…\nили адрес подписки, ссылка vpn:// из Amnezia, настройки WireGuard / AmneziaWG. Можно несколько ссылок, каждая с новой строки.'} />
      <input className="input" style={{ width: '100%', marginTop: 8 }} autoComplete="off" spellCheck={false} value={cdn} disabled={!!job} onChange={e => setCdn(e.target.value)} placeholder="Домен CDN, если его нет в ссылке" />
      <div className="row wrap" style={{ gap: 10, marginTop: 10, alignItems: 'center' }}>
        <Btn kind="primary" icon="search" disabled={!text.trim() || !!job} busy={!!job} onClick={start}>{job ? 'Проверяю…' : 'Проверить'}</Btn>
        <span className="dim3" style={{ fontSize: 12.5, flexBasis: 240 }} >Ссылка не сохраняется. Для одного подключения обычно до минуты.</span>
      </div>
      {!hasXray ? <div style={{ color: 'var(--orange)', fontSize: 13, marginTop: 8 }}>В этой установке нет ядра Xray: настоящий туннель не проверить, только путь до сервера.</div> : null}
    </Card>
    {job ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{job.stage}</b><div className="dim3" style={{ fontSize: 12 }}>окно можно закрыть, проверка продолжится на сервере</div></div></div> : null}
    {rep ? <>
      <Card title="Откуда проверяли">
        <VcRow state={p.state === 'direct' ? 'ok' : p.state === 'vpn' ? 'bad' : 'warn'} label={p.state === 'direct' ? 'Напрямую через провайдера' : p.state === 'vpn' ? 'Сейчас трафик идёт через VPN' : p.state === 'mixed' ? 'Часть трафика идёт через VPN' : 'Неясно, напрямую ли'}
          value={[p.isp, p.countryName, p.ip, p.note].filter(Boolean).join(' · ')} />
        {p.state === 'vpn' ? <div style={{ color: 'var(--red)', fontSize: 13, marginTop: 4 }}>Результат ниже показывает путь через этот VPN и ничего не говорит о вашем провайдере.</div> : null}
        {b ? <VcRow state="info" label="Обычный интернет" value={`задержка ${vcNum(b.ms, 'мс')}, загрузка ${vcNum(b.down, 'Мбит/с')}, отдача ${vcNum(b.up, 'Мбит/с')}${b.downError ? ` (скорость: ${b.downError})` : ''}${b.cloudflare && b.cloudflare.way === 'vpn' ? '. Замер скорости прошёл через VPN' : ''}`} /> : null}
        {b && b.cloudflare ? <VcRow state={b.cloudflare.way === 'vpn' ? 'warn' : b.cloudflare.ok ? 'ok' : 'bad'} label="Cloudflare отсюда" value={b.cloudflare.way === 'vpn' ? 'идёт через ваш VPN, поэтому про провайдера не говорит' : b.cloudflare.ok ? '256 КБ загружено, обрыва нет' : b.cloudflare.stalled ? `загрузка встала на ${Math.round(b.cloudflare.bytes / 1024)} КБ` : b.cloudflare.error || `код ${b.cloudflare.status}`} /> : null}
        <VcRow state="unknown" label="Мобильный интернет" value="не проверен, эта проверка идёт только из сети Rack Live" />
        <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>{fmt.ago(rep.t, Date.now() / 1000)}. Путь до каждого сервера указан в его карточке.</div>
      </Card>
      {rep.errors && rep.errors.length ? <div className="err-note">{rep.errors.join(' ')}</div> : null}
      {rep.items.map((it, i) => <VcItem key={i} it={it} base={b} />)}
    </> : null}
  </div>;
}
