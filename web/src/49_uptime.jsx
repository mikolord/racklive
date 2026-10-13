/* Availability over 30 days: a bar per day, % in the network, outages (data.uptime from rackd/uptime.py) */
const fmtDur = s => { s = Math.round(s || 0);
  if (s < 60) return s + ' с'; const m = Math.round(s / 60); if (m < 60) return m + ' мин';
  const h = Math.floor(m / 60); if (h < 24) return h + ' ч' + (m % 60 ? ' ' + (m % 60) + ' мин' : '');
  const d = Math.floor(h / 24); return d + ' д' + (h % 24 ? ' ' + (h % 24) + ' ч' : ''); };
const pctText = p => p == null ? '—' : p >= 100 ? '100%' : (p >= 99.99 ? '99,99' : p.toFixed(p >= 99 ? 2 : 1).replace('.', ',')) + '%';
const pctColor = p => p == null ? 'var(--fill2)' : p >= 99.9 ? 'var(--green)' : p >= 99 ? '#7bd88f' : p >= 95 ? 'var(--yellow)' : p >= 80 ? 'var(--orange)' : 'var(--red)';

function UptimeBars({ days, now }) {
  return <div className="up-bars">{days.map((p, i) => {
    const t = now - (days.length - 1 - i) * 86400;
    return <i key={i} style={{ background: pctColor(p) }} title={`${new Date(t * 1000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}: ${p == null ? 'нет данных' : pctText(p)}`} />; })}</div>;
}

function uptimeLine(u, now) {
  if (u.downNow) return `сейчас нет связи · уже ${fmtDur(u.last ? u.last.dur : 0)}`;
  if (!u.outs) return 'без сбоев';
  const l = u.last;
  return `${u.outs} ${ruPlural(u.outs, 'сбой', 'сбоя', 'сбоев')} · последний ${fmt.ago(l.end || l.start, now)} на ${fmtDur(l.dur)}` +
    (u.outs > 1 && u.longest > l.dur ? ` · самый долгий ${fmtDur(u.longest)}` : '');
}

function UptimeRow({ u, now, onClick, sub }) {
  return <div className="li up-row" style={{ cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
    <KindIcon kind={u.kind === 'ap' ? 'ap' : u.devKind || 'other'} size={34} />
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="row" style={{ gap: 8 }}><span className="ellipsis" style={{ fontWeight: 600 }}>{u.name}</span>
        {sub ? <span className="dim3" style={{ fontSize: 11.5 }}>{sub}</span> : null}<div className="grow" />
        <b style={{ color: pctColor(u.pct), fontVariantNumeric: 'tabular-nums' }}>{pctText(u.pct)}</b></div>
      <UptimeBars days={u.days} now={now} />
      <div className="dim ellipsis" style={{ fontSize: 12, color: u.downNow ? 'var(--red)' : undefined }}>{uptimeLine(u, now)}</div>
    </div>
  </div>;
}

function useUptime() {
  const { data } = useApp();
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  return (data.uptime || []).filter(u => devById[u.dev]).map(u => ({ ...u, devKind: (devById[u.dev] || {}).kind,
    parent: u.kind === 'ap' ? (devById[u.dev] || {}).name : null }));
}

/* in the device card: the device itself and the mesh points it reports */
function DeviceUptime({ device }) {
  const { data } = useApp();
  const list = useUptime().filter(u => u.dev === device.id).sort((a, b) => (a.kind === 'ap') - (b.kind === 'ap'));
  if (!list.length) return null;
  const since = list.map(u => u.since).filter(Boolean).sort()[0];
  return <Card title="Доступность · 30 дней" right={since ? <span className="dim3" style={{ fontSize: 12 }}>данные с {new Date(since).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span> : null}>
    <div className="list">{list.map(u => <UptimeRow key={u.key} u={u} now={data.now} sub={u.kind === 'ap' ? 'mesh-точка' : null} />)}</div>
  </Card>;
}

/* on «Размещение»: who was flaky lately; the full list in a window (?uptime=1) */
function UptimeCard() {
  const { data, openDevice } = useApp();
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('uptime') === '1');
  const list = useUptime();
  if (!list.length) return null;
  const flaky = list.filter(u => u.downNow || u.outs7 > 0 || (u.pct7 != null && u.pct7 < 99.9));
  const known = list.filter(u => u.pct != null);
  const avg = known.length ? known.reduce((a, u) => a + u.pct, 0) / known.length : null;
  const since = list.map(u => u.since).filter(Boolean).sort()[0];
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const click = u => u.kind !== 'ap' && devById[u.dev] ? () => { setOpen(false); openDevice(devById[u.dev]); } : null;
  return <>
    <Card title="Доступность · 30 дней" right={<Btn size="sm" onClick={() => setOpen(true)}>Подробнее</Btn>}>
      {flaky.length ? <div className="list">{flaky.slice(0, 4).map(u => <UptimeRow key={u.key} u={u} now={data.now} onClick={click(u)} sub={u.parent ? '· ' + u.parent : null} />)}</div>
        : <div className="row" style={{ cursor: 'pointer' }} onClick={() => setOpen(true)}><span className="dot online" />
          <b>Всё стабильно</b><span className="dim">— за неделю ни одного сбоя{avg != null ? ` · в среднем ${pctText(avg)}` : ''}</span></div>}
      {flaky.length > 4 ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>и ещё {flaky.length - 4} — в «Подробнее»</div> : null}
    </Card>
    {open ? <Modal title="Доступность за 30 дней" wide onClose={() => setOpen(false)} icon={<Icon name="pulse" size={20} color="var(--accent)" />}>
      <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>Сколько времени каждое устройство и mesh-точка были в сети. Каждый столбик — один день: зелёный — без сбоев,
        жёлтый и красный — пропадало. {since ? `Rack Live собирает данные с ${new Date(since).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}.` : ''}</div>
      <div className="list">{list.map(u => <UptimeRow key={u.key} u={u} now={data.now} onClick={click(u)} sub={u.parent ? '· ' + u.parent : null} />)}</div>
      <div><AskAi label="Что барахлило?" q="Посмотри доступность за 30 дней: что барахлило, есть ли закономерность (время, дни) и что проверить в первую очередь?" /></div>
    </Modal> : null}
  </>;
}
