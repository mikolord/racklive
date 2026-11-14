/* «Главная»: a grid of widgets. In edit mode — drag by the handle to move (others glide out of the way),
   pull the corner to resize (width snaps to columns, height is free), «+ Виджет» adds, × removes.
   The layout lives on the server (data.dashboard) — the same on every device; phones show one column. */
const DASH_ROW = 8, DASH_GAP = 14;

function StatsWidget() {
  if (isTestLook()) return <StatsInstr />;
  const { data } = useApp(); const devices = data.devices;
  const problems = devices.filter(d => !d.healthSkip && ['offline', 'warning'].includes(d.state && d.state.status));
  const clients = devices.reduce((a, d) => a + ((d.state && d.state.clients) || []).length, 0);
  const poe = devices.flatMap(d => (d.state && d.state.ports) || []).reduce((a, p) => a + (p.poeW || 0), 0);
  return <div className="stats">
    <Stat k="Устройства" v={`${devices.filter(d => !d.healthSkip && d.state && d.state.status === 'online').length}/${devices.filter(d => !d.healthSkip).length}`} />
    <Stat k="Проблемы" v={problems.length} level={problems.length ? 'warn' : ''} />
    <Stat k="Клиенты" v={clients} />
    <Stat k="PoE" v={poe ? poe.toFixed(1) : 0} unit="Вт" />
  </div>;
}




function SpeedWidget() {
  const { data, openSpeed } = useApp();
  const last = (data.speedtests || []).filter(t => t.kind !== 'iperf').slice(-1)[0];
  return <Card title="Тест скорости" right={<Btn size="sm" kind="primary" icon="gauge" onClick={openSpeed}>Начать</Btn>}>
    {last ? <div className="row" style={{ gap: 16, alignItems: 'flex-end' }}>
      <div><div className="inet-big">{mbpsText(last.down)}<small> ↓</small></div><div className="dim3" style={{ fontSize: 11.5 }}>Мбит/с загрузка</div></div>
      <div><div className="inet-big">{mbpsText(last.up)}<small> ↑</small></div><div className="dim3" style={{ fontSize: 11.5 }}>отдача</div></div>
      <div className="grow" /><div className="dim3" style={{ fontSize: 11.5, textAlign: 'right' }}>{last.note || ''}<div>{fmt.ago(last.t, data.now)}</div></div></div>
      : <div className="dim" style={{ fontSize: 13 }}>Замеров ещё не было — скорость Wi-Fi и домашней сети с этого устройства.</div>}
  </Card>;
}

function FrankWidget() {
  const { admin, askAi } = useApp(); const [q, setQ] = useState('');
  if (!admin) return <Card title="Frank"><div className="dim" style={{ fontSize: 13 }}>Войдите, чтобы задавать вопросы помощнику.</div></Card>;
  const go = () => { if (q.trim()) { askAi(q.trim()); setQ(''); } };
  return <Card title={<span className="row" style={{ gap: 8 }}>{isAurora() ? <AuEye size={21} /> : <AppIcon app="frank" size={20} radius={6} />}Спросить Frank</span>}>
    <div className="row" style={{ gap: 8 }}><input className="input grow" value={q} placeholder="Например: всё ли в порядке с сетью?" onChange={e => setQ(e.target.value)}
      onKeyDown={e => e.key === 'Enter' && go()} /><Btn kind="primary" icon="chevron" onClick={go} /></div>
    <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>{['Всё ли в порядке?', 'Что барахлило на неделе?', 'Почему медленный Wi-Fi?'].map(x =>
      <button key={x} type="button" className="chip" onClick={() => askAi(x)}>{x}</button>)}</div>
  </Card>;
}


function NoteWidget({ w, edit: editMode, onOpts }) {
  const { admin } = useApp(); const edit = !!admin;               // a note is written right where it lies, no edit mode needed
  const text = (w.opts || {}).text || '';
  const [draft, setDraft] = useState(text);
  const latest = useRef({ draft: text, saved: text, onOpts }); latest.current.onOpts = onOpts;
  const timer = useRef(0);
  useEffect(() => { if (!timer.current && draft === latest.current.saved) setDraft(text); latest.current.saved = text; }, [text]);       // a change from another screen
  const flush = () => { clearTimeout(timer.current); timer.current = 0; const l = latest.current; if (l.draft !== l.saved) { l.saved = l.draft; l.onOpts({ text: l.draft }); } };
  const type = v => { setDraft(v); latest.current.draft = v; clearTimeout(timer.current); timer.current = setTimeout(flush, 700); };      // saved by itself 0.7 s after the last key
  useEffect(() => () => flush(), []);                                                                                                   // leaving the edit mode / the page: nothing is lost
  return <Card title={w.title || 'Заметка'}>
    {edit ? <textarea className="input note-pad" rows={4} value={draft} placeholder="Что угодно: пароль от гостевого Wi-Fi, телефон провайдера, что купить…"
      onChange={e => type(e.target.value)} onBlur={flush} style={{ width: '100%', resize: 'vertical' }} />
      : <div className="note-pad" style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.5 }}>{text || <span className="dim3">Пусто. Войдите как администратор, чтобы написать.</span>}</div>}
  </Card>;
}

/* UPS: which one runs out first is the one the square shows; the wide forms list every UPS with what it feeds */
const upsList = d => d.devices.filter(x => x.driver === 'ups' && x.state && x.state.ups);
const upsFirst = d => [...upsList(d)].sort((a, b) => (a.state.ups.runtimeMin == null ? 1e9 : a.state.ups.runtimeMin) - (b.state.ups.runtimeMin == null ? 1e9 : b.state.ups.runtimeMin))[0];
const upsTone = u => (u.onBattery || u.lowBattery || u.replace || (u.loadPct || 0) > 85 || (u.charge != null && u.charge < 40) ? (u.lowBattery || (u.charge != null && u.charge < 20) ? 'red' : 'orange') : 'green');
const upsColor = u => ({ green: 'var(--green)', orange: 'var(--orange)', red: 'var(--red)' }[upsTone(u)]);
const fmtMinShort = m => (m == null ? '—' : m >= 60 ? `${Math.floor(m / 60)} ч ${m % 60 ? m % 60 + ' м' : ''}`.trim() : `${m} мин`);

/* a battery: filled by the charge (or full when the UPS has no data cable — it is a calculation then), a bolt in the middle */
function BatteryArt({ u, vertical }) {
  const f = u ? (u.charge != null ? Math.max(.06, Math.min(1, u.charge / 100)) : 1) : 0; const col = u ? upsColor(u) : 'var(--text3)';
  const bolt = 'M0 -13 L-8 3 H-1.5 L-3 13 L8 -4 H1.5 Z';
  return vertical ? <svg viewBox="0 0 100 100" className="mini-svg">
    <rect x="42" y="7" width="16" height="9" rx="3.5" fill="var(--fill2)" />
    <rect x="29" y="14" width="42" height="80" rx="11" fill="none" stroke="var(--fill2)" strokeWidth="5" />
    <clipPath id="ubv"><rect x="33" y="18" width="34" height="72" rx="8" /></clipPath>
    <g clipPath="url(#ubv)"><rect x="33" y={18 + 72 * (1 - f)} width="34" height={72 * f} fill={col} opacity=".92" /></g>
    <path d={bolt} transform="translate(50 56) scale(1.25)" fill="#fff" stroke="#fff" strokeWidth="1.2" strokeLinejoin="round" />
  </svg> : <svg viewBox="0 0 132 64" className="upsw-bat">
    <rect x="124" y="21" width="7" height="22" rx="3" fill="var(--fill2)" />
    <rect x="3" y="4" width="118" height="56" rx="15" fill="none" stroke="var(--fill2)" strokeWidth="5" />
    <clipPath id="ubh"><rect x="8" y="9" width="108" height="46" rx="11" /></clipPath>
    <g clipPath="url(#ubh)"><rect x="8" y="9" width={108 * f} height="46" fill={col} opacity=".92" /></g>
    <path d={bolt} transform="translate(62 32) scale(1.35)" fill="#fff" stroke="#fff" strokeWidth="1.2" strokeLinejoin="round" />
  </svg>;
}

/* «Аврора»: как виджет «Аккумуляторы» в iOS — кольцо заряда со значком внутри (молния — от сети, заряжается), под ним проценты и на сколько хватит */
function AuRing({ f, color, size = 72, children }) {
  const r = 42, c = 2 * Math.PI * r, k = Math.max(0, Math.min(1, f || 0));
  return <span className="au-ring" style={{ width: size, height: size }}>
    <svg viewBox="0 0 100 100" width={size} height={size}>
      <circle cx="50" cy="50" r={r} fill="none" className="au-ring-track" strokeWidth="9" />
      <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${c * k} ${c}`} transform="rotate(-90 50 50)" className="au-ring-fill" />
    </svg><span className="au-ring-in">{children}</span></span>;
}
const upsRingColor = u => ({ red: 'var(--red)', orange: 'var(--orange)' })[upsTone(u)] || 'var(--green)';
function AuUps({ list }) {
  const { openDevice } = useApp();
  const one = list.length === 1;
  return <div className={'au-bat' + (one ? ' one' : '')}>{list.slice(0, 4).map(d => { const u = d.state.ups, f = u.charge != null ? u.charge / 100 : 1;
    const feeds = [...(u.connected || [])].sort((a, b) => b.w - a.w);
    return <button key={d.id} type="button" className="au-bat-i" onClick={() => openDevice(d)}>
      <span className="au-bat-ring"><AuRing f={f} color={upsRingColor(u)} size={one ? 92 : 70}><Icon name="ups" size={one ? 30 : 24} />
        {!u.onBattery ? <i className="au-bat-bolt"><Icon name="bolt" size={11} stroke={2.6} /></i> : null}</AuRing>
        <b className="au-bat-pct">{u.charge != null ? Math.round(u.charge) + '%' : '—'}</b></span>
      {one ? <span className="au-bat-info">
        <span className="au-bat-name ellipsis">{nameNoFlag(d.name)}</span>
        <span className="au-bat-big">{u.runtimeEstimated ? '≈ ' : ''}{fmtMinShort(u.runtimeMin)}</span>
        <span className="au-bat-sub">{u.onBattery ? 'от батареи — столько ещё продержится' : 'хватит при отключении света'}</span>
        {u.loadPct != null ? <span className="au-bat-load"><span>Нагрузка {u.loadW} Вт · {u.loadPct}%</span><i><b style={{ width: Math.min(100, u.loadPct) + '%', background: u.loadPct > 85 ? 'var(--red)' : u.loadPct > 70 ? 'var(--orange)' : 'var(--accent)' }} /></i></span> : null}
        {feeds.length ? <span className="au-bat-feeds ellipsis">Питает: {feeds.slice(0, 4).map(c => nameNoFlag(c.name)).join(', ')}{feeds.length > 4 ? ' и ещё ' + (feeds.length - 4) : ''}</span> : null}
      </span> : <span className="au-bat-cap"><span className="ellipsis">{nameNoFlag(d.name)}</span><small>{u.runtimeEstimated ? '≈ ' : ''}{fmtMinShort(u.runtimeMin)}</small></span>}
    </button>; })}</div>;
}
/* «Аврора», квадраты: батарея — кольцом (как iOS), шкаф — шкаф со скруглёнными юнитами, занятые — цветом системы */
function AuMiniRack({ data }) {
  const r = (data.racks || [])[0]; const total = r ? r.totalU || 12 : 12, used = new Set();
  if (r) (r.units || []).forEach(u => { for (let k = 0; k < (u.uSize || 1); k++) used.add((u.uStart || 1) + k); });
  const n = Math.min(total, 14), gap = 2.2, h = (84 - (n - 1) * gap) / n;
  return <svg viewBox="0 0 70 100" className="mini-svg au-mrack">
    <rect x="9" y="3" width="52" height="94" rx="9" className="au-mrack-body" />
    {Array.from({ length: n }, (_, i) => <rect key={i} x="16" y={8 + i * (h + gap)} width="38" height={Math.max(1.5, h)} rx={Math.min(3, h / 2)} className={used.has(i + 1) ? 'au-mrack-u on' : 'au-mrack-u'} />)}
  </svg>;
}
const AU_TILE_ART = {
  ups: d => { const u = upsFirst(d); const s = u && u.state.ups; if (!s) return null;
    return <AuRing f={s.charge != null ? s.charge / 100 : 1} color={upsRingColor(s)} size={84}><Icon name="ups" size={28} />{!s.onBattery ? <i className="au-bat-bolt"><Icon name="bolt" size={11} stroke={2.6} /></i> : null}</AuRing>; },
  rack: d => <AuMiniRack data={d} />,
  frank: () => <div className="mini-frank au"><AuEye size={92} tight /></div>,
};

/* «Аврора», квадраты целиком (iOS + UniFi): ИБП — как «Аккумуляторы» iOS, Советы — как стопка уведомлений, Новые — как «Клиенты» UniFi.
   Вернул null — рисуется обычный квадрат. */
const auUpsCol = u => u.lowBattery || (u.charge != null && u.charge < 20) ? 'var(--red)' : u.onBattery ? (u.charge != null && u.charge < 40 ? 'var(--orange)' : 'var(--text)') : '#34c759';
const auPct = u => (u.charge != null ? Math.round(u.charge) : null);
/* батарейка как в правом верхнем углу iPhone: корпус, носик, заливка по заряду, число внутри, молния — от сети */
function AuBattery({ u, w = 132 }) {
  const p = auPct(u), f = p != null ? Math.max(.04, p / 100) : 1, col = auUpsCol(u), txt = p != null ? String(p) : '';
  const fw = 94 * f;
  return <svg viewBox="0 0 120 54" width={w} className="au-batt">
    <rect x="2" y="2" width="104" height="50" rx="15" className="au-batt-body" />
    <path d="M110 19 a5 5 0 0 1 5 5 v6 a5 5 0 0 1 -5 5 z" className="au-batt-nub" />
    <clipPath id={'abc' + w}><rect x="7" y="7" width="94" height="40" rx="10.5" /></clipPath>
    <g clipPath={`url(#abc${w})`}><rect x="7" y="7" width={fw} height="40" fill={col} className="au-batt-fill" /></g>
    {txt ? <text x={u.onBattery ? 54 : 49} y="36.5" textAnchor="middle" className="au-batt-t" style={{ fill: f > .55 ? (col === 'var(--text)' ? 'var(--card-solid)' : '#fff') : 'var(--text)' }}>{txt}</text> : null}
    {!u.onBattery ? <path d={txt ? 'M78 14 L70 29 H76 L73 40 L83 24 H77 Z' : 'M58 11 L47 29 H55 L51 43 L64 23 H56 Z'} className="au-batt-bolt"
      style={{ fill: f > .7 ? (col === 'var(--text)' ? 'var(--card-solid)' : '#fff') : 'var(--text)' }} /> : null}
  </svg>;
}
function AuUpsTile({ data }) {
  const l = [...upsList(data)].sort((a, b) => (a.state.ups.runtimeMin == null ? 1e9 : a.state.ups.runtimeMin) - (b.state.ups.runtimeMin == null ? 1e9 : b.state.ups.runtimeMin)).slice(0, 3);
  if (l.length === 1) { const d = l[0], u = d.state.ups;
    return <>
      <span className="auw-head"><span className="auw-app"><Icon name="ups" size={15} stroke={2.2} /></span><b>{nameNoFlag(d.name)}</b></span>
      <span className="auw-batt1"><AuBattery u={u} /></span>
      <span className="auw-big sm">{u.runtimeEstimated ? '≈ ' : ''}{fmtMinShort(u.runtimeMin)}</span>
      <span className="auw-sub ellipsis">{u.onBattery ? 'от батареи — продержится' : u.loadW != null ? `от сети · ${u.loadW} Вт` : 'от сети'}</span>
    </>; }
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="ups" size={15} stroke={2.2} /></span><b>ИБП</b></span>
    <span className="auw-batts">{l.map(d => { const u = d.state.ups;
      return <span key={d.id} className="auw-bi"><AuBattery u={u} w={58} /><span className="ellipsis">{nameNoFlag(d.name)}</span><b>{fmtMinShort(u.runtimeMin)}</b></span>; })}</span>
  </>;
}
function AuAdviceTile({ data }) {
  const a = data.advice || {}, it = a.items || [], x = it[0], k = x ? ADVICE_KIND[x.kind] || ADVICE_KIND.idea : null;
  return <>
    <span className="auw-head"><span className="auw-app"><AuEye size={17} /></span><b>Frank</b>{it.length ? <i className="auw-badge">{it.length}</i> : null}</span>
    {x ? <span className={'auw-stack n' + Math.min(3, it.length)}>
      <span className="auw-note"><span className="auw-note-k" style={{ color: k[1] }}><Icon name={k[0]} size={11} stroke={2.6} />{k[2]}</span>
        <b className="auw-note-t">{x.title}</b></span></span>
      : <span className="auw-empty"><span className="auw-ok"><Icon name="check" size={20} stroke={2.8} /></span>{a.running ? 'Изучаю сеть…' : 'Всё прочитано'}</span>}
    <span className="auw-sub ellipsis">{a.last ? fmt.ago(a.last, data.now) : 'советы раз в ' + (a.days || 3) + ' дн.'}</span>
  </>;
}
/* «Сводка» — лента уведомлений как на iPhone: новая карточка опускается сверху, прежние уходят вниз стопкой, карточка на карточку.
   Сначала то, что сейчас не в сети / с предупреждением, потом последние события */
const AU_EV = { offline: ['Нет связи', '#ff3b30', 'power'], warning: ['Внимание', '#ff9500', 'alert'], online: ['Снова в сети', '#34c759', 'check'], info: ['Событие', 'var(--accent)', 'bell'] };
function AuStatsTile({ data }) {
  const w = data.devices.filter(x => !x.healthSkip), on = w.filter(x => (x.state || {}).status === 'online').length;
  const bad = w.filter(x => ['offline', 'warning'].includes((x.state || {}).status)).sort((a, b) => (a.state.status === 'offline' ? 0 : 1) - (b.state.status === 'offline' ? 0 : 1));
  const clients = data.devices.reduce((a, d) => a + ((d.state && d.state.clients) || []).length, 0);
  const items = [...bad.map(x => ({ e: AU_EV[x.state.status], t: nameNoFlag(x.name), s: 'сейчас' })),
    ...[...(data.events || [])].sort((a, b) => (b.t || 0) - (a.t || 0)).slice(0, 8).map(e => ({ e: AU_EV[e.level] || AU_EV.info, t: `${nameNoFlag(e.name || '')}${e.text ? ': ' + e.text : ''}`, s: e.t ? fmt.ago(e.t, data.now) : '' }))];
  const n = items.length;
  const [k, setK] = useState(() => Math.min(2, Math.max(0, n - 1)));
  useEffect(() => {
    if (n < 2 || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
    const t = setInterval(() => { if (!document.hidden) setK(v => v + 1); }, 3400); return () => clearInterval(t);
  }, [n > 1]);
  const stack = [0, 1, 2].map(i => k - i).filter(s => s >= 0 && k - s < Math.min(3, n));
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="pulse" size={15} stroke={2.2} /></span><b>Сводка</b>{bad.length ? <i className="auw-badge">{bad.length}</i> : null}</span>
    {n ? <span className="auw-feed">{stack.map((s, i) => { const it = items[s % n];
      return <span key={s} className={'auw-note auw-fi' + (i === 0 && s > 2 ? ' drop' : '') + (i ? ' back' : '')} style={{ '--i': i, zIndex: 3 - i }}>
        <span className="auw-note-k" style={{ color: it.e[1] }}><Icon name={it.e[2]} size={11} stroke={2.6} />{it.e[0]}<em>{it.s}</em></span>
        <b className="auw-note-t">{it.t}</b></span>; })}</span>
      : <span className="auw-empty"><span className="auw-ok"><Icon name="check" size={20} stroke={2.8} /></span>Всё в сети</span>}
    <span className="auw-sub ellipsis">{on} из {w.length} в сети{clients ? ` · ${clients} ${ruPlural(clients, 'клиент', 'клиента', 'клиентов')}` : ''}</span>
  </>;
}
/* «Состояние сети» — стена (как в «Витрине»), но по-эпловски: скруглённые кирпичи с объёмом, по ним бежит блик и «дыхание»,
   при падении здоровья кирпичи выпадают и падают вниз; под стеной — здоровье и защита */
function AuWallTile({ data }) {
  const hs = data.health ? data.health.score : null, ss = data.security ? data.security.score : null;
  const s = hs == null ? 100 : hs, tone = hs == null ? 'var(--text3)' : s >= 80 ? 'var(--accent)' : s >= 30 ? `color-mix(in srgb, var(--accent) ${Math.round(35 + (s - 30) * .9)}%, #8e8e93)` : '#8e8e93';
  const nGone = s >= 80 ? 0 : Math.round((80 - s) / 80 * FW_BRICKS.length * .62) + 1;
  const gone = new Set(FW_ORDER.slice(0, nGone).filter(i => i < FW_BRICKS.length));
  const W = FW_COLS * (FW_BW + FW_G) - FW_G, H = FW_ROWS * (FW_BH + FW_G) - FW_G;
  const col = v => (v == null ? 'var(--text3)' : v >= 80 ? 'var(--accent)' : v >= 50 ? 'color-mix(in srgb, var(--accent) 55%, #8e8e93)' : '#8e8e93');
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="shield" size={15} stroke={2.2} /></span><b>Состояние сети</b></span>
    <span className="auw-wall">
      <svg viewBox={`-3 -3 ${W + 6} ${H + 9}`} className={'au-wall' + (s < 30 ? ' broken' : '')} style={{ '--fw': tone }}>
        <defs>
          <linearGradient id="awb" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" stopOpacity=".38" /><stop offset=".45" stopColor="#fff" stopOpacity="0" /><stop offset="1" stopColor="#000" stopOpacity=".18" /></linearGradient>
          <linearGradient id="aws" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#fff" stopOpacity="0" /><stop offset=".5" stopColor="#fff" stopOpacity=".55" /><stop offset="1" stopColor="#fff" stopOpacity="0" /></linearGradient>
          <clipPath id="awc">{FW_BRICKS.map((b, i) => gone.has(i) ? null : <rect key={i} x={b.x} y={b.y} width={b.w} height={FW_BH} rx="2.4" />)}</clipPath>
        </defs>
        {FW_BRICKS.map((b, i) => gone.has(i) ? <rect key={'g' + i} x={b.x + .5} y={b.y + .5} width={b.w - 1} height={FW_BH - 1} rx="2.2" className="aw-gap" />
          : <g key={i} className="aw-b" style={{ '--d': i * 28 + 'ms', '--c': (b.x / W).toFixed(2) }}>
            <rect x={b.x} y={b.y} width={b.w} height={FW_BH} rx="2.4" className="aw-fill" />
            <rect x={b.x} y={b.y} width={b.w} height={FW_BH} rx="2.4" fill="url(#awb)" /></g>)}
        <g clipPath="url(#awc)"><rect x="-30" y="-5" width="22" height={H + 10} fill="url(#aws)" className="aw-shine" transform="skewX(-18)" /></g>
        {[...gone].slice(0, 5).map((i, k) => { const b = FW_BRICKS[i];
          return <rect key={'f' + i} x={b.x} y={b.y} width={Math.min(b.w, 14)} height={FW_BH - 1} rx="2.2" className="aw-fall" style={{ '--d': 400 + k * 260 + 'ms', '--r': ((k * 47) % 70 - 35) + 'deg', '--y': (H + 2 - b.y) + 'px' }} />; })}
        {s < 30 ? <path d={`M${W * .42} -1 L${W * .5} ${H * .3} L${W * .38} ${H * .55} L${W * .56} ${H * .8} L${W * .48} ${H}`} className="aw-crack" /> : null}
      </svg>
    </span>
    <span className="auw-scores">
      <span><b style={{ color: col(hs) }}>{hs == null ? '—' : hs}</b>сеть</span>
      <span><b style={{ color: col(ss) }}>{ss == null ? '—' : ss}</b>защита</span>
    </span>
  </>;
}
/* «Новые в сети»: витрина сама листает устройства — iPhone (экран цветом системы), Android, Surface (серый, синий экран, знак Windows-окна), MacBook (серый экран, яблоко) */
const AU_APPLE = 'M0 -3.6 C-2.6 -5.6 -7.6 -4.6 -7.6 0.6 C-7.6 5 -4.8 9 -2.9 9 C-1.7 9 -1.1 8.3 0 8.3 C1.1 8.3 1.7 9 2.9 9 C4.8 9 7.6 5 7.6 0.6 C7.6 -4.6 2.6 -5.6 0 -3.6 Z M0.4 -4.9 C0.4 -7.4 2.3 -9.2 4 -9.3 C4 -7.2 2.4 -5 0.4 -4.9 Z';
function AuDevShow() {
  const laptop = (id, scr, logo) => <>
    <rect x="21" y="7" width="78" height="51" rx="3.6" className="ads-lid" />
    <rect x="22.6" y="8.6" width="74.8" height="47.8" rx="2.2" fill={`url(#${scr})`} />
    {logo}
    <path d="M13 59.2 H107 V60.4 a2.6 2.6 0 0 1 -2.6 2.6 H15.6 a2.6 2.6 0 0 1 -2.6 -2.6 Z" className="ads-base" />
    <rect x="52" y="59.2" width="16" height="1.4" rx=".7" className="ads-notch" /></>;
  return <svg viewBox="0 0 120 70" className="au-show">
    <defs>
      <radialGradient id="adi" cx=".5" cy=".38" r=".75"><stop offset="0" style={{ stopColor: 'color-mix(in srgb, var(--accent) 55%, #fff)' }} /><stop offset=".55" style={{ stopColor: 'var(--accent)' }} />
        <stop offset="1" style={{ stopColor: 'color-mix(in srgb, var(--accent) 45%, #000)' }} /></radialGradient>
      <linearGradient id="ads2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#30d158" /><stop offset="1" stopColor="#0a84ff" /></linearGradient>
      <radialGradient id="adw" cx=".5" cy=".55" r=".8"><stop offset="0" stopColor="#7cc4ff" /><stop offset=".45" stopColor="#1677e8" /><stop offset="1" stopColor="#062a6b" /></radialGradient>
      <radialGradient id="adm" cx=".5" cy=".5" r=".8"><stop offset="0" stopColor="#8e8e93" /><stop offset=".6" stopColor="#48484a" /><stop offset="1" stopColor="#1c1c1e" /></radialGradient>
    </defs>
    <g className="ads ads-a">{/* iPhone */}
      <rect x="45" y="2" width="31" height="66" rx="9" className="ads-frame" /><rect x="47.4" y="4.4" width="26.2" height="61.2" rx="7" fill="url(#adi)" />
      <rect x="55" y="7.4" width="11" height="3.6" rx="1.8" fill="#000" />
      <rect x="51.5" y="20" width="18" height="5.2" rx="2.6" fill="#fff" opacity=".9" /><rect x="54.5" y="27.5" width="12" height="2" rx="1" fill="#fff" opacity=".55" />
      <rect x="53" y="60" width="15" height="1.6" rx=".8" fill="#fff" opacity=".7" /></g>
    <g className="ads ads-b">{/* Android */}
      <rect x="44" y="2" width="33" height="66" rx="5.5" className="ads-frame" /><rect x="46.3" y="4.3" width="28.4" height="61.4" rx="3.8" fill="url(#ads2)" />
      <circle cx="60.5" cy="8.5" r="1.9" fill="#000" /><rect x="50" y="55" width="21" height="6" rx="3" fill="#fff" opacity=".28" />
      <rect x="50" y="17" width="9" height="9" rx="4.5" fill="#fff" opacity=".35" /><rect x="62" y="17" width="9" height="9" rx="4.5" fill="#fff" opacity=".35" />
      <rect x="50" y="30" width="9" height="9" rx="4.5" fill="#fff" opacity=".35" /><rect x="62" y="30" width="9" height="9" rx="4.5" fill="#fff" opacity=".35" /></g>
    <g className="ads ads-c">{/* Surface */}
      {laptop('c', 'adw', <g transform="translate(60 32.5)">
        <rect x="-6.6" y="-6.6" width="6.2" height="6.2" fill="#f25022" /><rect x=".4" y="-6.6" width="6.2" height="6.2" fill="#7fba00" />
        <rect x="-6.6" y=".4" width="6.2" height="6.2" fill="#00a4ef" /><rect x=".4" y=".4" width="6.2" height="6.2" fill="#ffb900" /></g>)}</g>
    <g className="ads ads-d">{/* MacBook */}
      {laptop('d', 'adm', <path d={AU_APPLE} transform="translate(60 32.5) scale(1.05)" fill="#f2f2f7" opacity=".92" />)}</g>
  </svg>;
}
function AuNewTile({ data }) {
  const all = data.newDevices || [], ask = all.filter(r => r.decision === 'ask');
  const n = ask.length || all.length;
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="wifi" size={15} stroke={2.2} /></span><b>Новые в сети</b></span>
    <span className="auw-show"><AuDevShow /></span>
    <span className="auw-foot">
      <span className="auw-big sm">{n}<small>{ask.length ? 'ждут' : 'за неделю'}</small></span>
      <span className={'auw-pill ' + (ask.length ? 'warn' : 'ok')}>{ask.length ? <><i />решить</> : <><Icon name="check" size={11} stroke={3} />свои</>}</span>
    </span>
  </>;
}
/* «Заметка» — листок бумаги, как в «Заметках» iOS: линовка и загнутый уголок, только не жёлтый, а в цвете системы. Заголовок — первая строка */
function AuNoteTile({ w }) {
  const lines = ((w.opts || {}).text || '').split('\n').map(s => s.trim()).filter(Boolean);
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="edit" size={14} stroke={2.2} /></span><b>Заметка</b></span>
    <span className={'auw-paper' + (lines.length ? '' : ' empty')}>
      {lines.length ? lines.slice(0, 5).map((l, i) => i ? <span key={i} className="ellipsis">{l}</span> : <b key={i} className="ellipsis">{l}</b>) : <span>Пустая заметка</span>}
    </span>
  </>;
}
/* «Оплата серверов» квадратом: листок календаря с днём оплаты, сколько осталось, кто и сколько.
   Серверов несколько — они сами сменяют друг друга: прежний уходит вверх и тает, следующий поднимается снизу; точки в шапке показывают, который сейчас */
const AU_MON = ['ЯНВ', 'ФЕВ', 'МАР', 'АПР', 'МАЙ', 'ИЮН', 'ИЮЛ', 'АВГ', 'СЕН', 'ОКТ', 'НОЯ', 'ДЕК'];
function AuPayTile({ data }) {
  const all = payDevices(data), cnt = all.length;
  const [k, setK] = useState(0);
  useEffect(() => {
    if (cnt < 2 || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
    const t = setInterval(() => { if (!document.hidden) setK(v => v + 1); }, 4600); return () => clearInterval(t);
  }, [cnt > 1]);
  if (!cnt) return null;
  const slide = (s, cls) => { const l = all[s % cnt], n = payLeft(l.pay), m = /^(\d{4})-(\d\d)-(\d\d)/.exec(l.pay.due) || [];
    return <span key={s} className={'auw-slide ' + cls}>
      <span className="auw-pay">
        <span className={'auw-cal' + (n < 0 ? ' late' : n <= 3 ? ' soon' : '')}><i>{AU_MON[+m[2] - 1] || ''}</i><b>{+m[3] || '—'}</b></span>
        <span className="auw-when">{n < 0 ? <>−{-n}<small>дн.</small></> : n === 0 ? 'сегодня' : n === 1 ? 'завтра' : <>{n}<small>дн.</small></>}</span>
      </span>
      <span className="auw-sub ellipsis">{[nameNoFlag(l.name), payMoney(l.pay)].filter(Boolean).join(' · ')}</span>
    </span>; };
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="card" size={14} stroke={2.2} /></span><b>Оплата</b>
      {cnt > 1 ? <span className="auw-dots">{all.slice(0, 6).map((x, i) => <i key={i} className={i === k % Math.min(cnt, 6) ? 'on' : ''} />)}</span> : null}</span>
    <span className="auw-roll">{k > 0 && cnt > 1 ? slide(k - 1, 'out') : null}{slide(k, k > 0 ? 'in' : 'first')}</span>
  </>;
}
/* «Клиенты VPN» как «Новые в сети»: люди кружками внахлёст (кто сейчас подключён), крупно — сколько онлайн, пилюля — сколько ещё выдержит сервер.
   Имён клиентов Rack Live не собирает, поэтому кружки — условные портреты в оттенках цвета системы */
function AuFace({ i }) {
  return <svg viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="15.5" r="6.6" fill="#fff" opacity=".96" />
    <path d="M6.5 40 C6.5 29.5 12.5 25 20 25 C27.5 25 33.5 29.5 33.5 40 Z" fill="#fff" opacity=".96" /></svg>;
}
function AuVpnTile({ data }) {
  const l = vpnList(data), sys = (data.vpnLoad || {}).system;
  const on = sys ? sys.online || 0 : l.reduce((a, x) => a + (x.r.online || 0), 0);
  const cl = sys ? sys.clients : l.reduce((a, x) => a + (x.r.clients || 0), 0) || null;
  const k = sys ? sys.k : (l.some(x => x.r.k != null) ? l.reduce((a, x) => a + (x.r.k || 0), 0) : null);
  const faces = on > 4 ? 3 : on, rest = on - faces;
  return <>
    <span className="auw-head"><span className="auw-app"><Icon name="shield" size={15} stroke={2.2} /></span><b>Клиенты VPN</b></span>
    <span className={'auw-people' + (on ? '' : ' none')}>
      {on ? <>{Array.from({ length: faces }, (x, i) => <span key={i} className={'auw-face f' + i} style={{ '--i': i }}><AuFace i={i} /></span>)}
        {rest > 0 ? <span className="auw-face more" style={{ '--i': faces }}>+{rest > 99 ? '99' : rest}</span> : null}
        <i className="auw-live" /></>
        : [0, 1, 2].map(i => <span key={i} className="auw-face off" style={{ '--i': i }}><AuFace i={i} /></span>)}
    </span>
    <span className="auw-foot">
      <span className="auw-big sm">{on}<small>онлайн</small></span>
      {k != null ? <span className={'auw-pill ' + (k < 5 ? 'warn' : 'ok')}>{k < 5 ? <i /> : null}ещё {vpnN(k).replace('≈ ', '')}</span>
        : cl ? <span className="auw-pill dim">из {cl}</span> : null}
    </span>
  </>;
}
const AU_TILE = { ups: d => (upsList(d).length ? <AuUpsTile data={d} /> : null), advice: d => (d.advice ? <AuAdviceTile data={d} /> : null), newdev: d => <AuNewTile data={d} />,
  stats: d => <AuStatsTile data={d} />, state: d => <AuWallTile data={d} />, note: (d, w) => <AuNoteTile w={w} />, pay: d => (payDevices(d).length ? <AuPayTile data={d} /> : null),
  vpn: d => (vpnList(d).length ? <AuVpnTile data={d} /> : null) };

function UpsWidget() {
  const { data, openDevice, setTab } = useApp();
  const list = upsList(data);
  if (isTestLook() && list.length) return <UpsInstr list={list} />;
  if (isAurora() && list.length) return <Card title="ИБП"><AuUps list={list} /></Card>;
  if (!list.length) return <Card title="ИБП"><div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>ИБП ещё не добавлен. Добавьте его в «Устройства» (тип «ИБП») или юнитом в шкаф — здесь появится, на сколько хватит батареи.</div>
    <div style={{ marginTop: 10 }}><Btn size="sm" onClick={() => setTab('devices')}>К устройствам</Btn></div></Card>;
  return <div className="upsw-list">{list.map(d => { const u = d.state.ups; const tone = upsTone(u);
    const feeds = [...u.connected].sort((a, b) => b.w - a.w); const shown = feeds.slice(0, 4);
    return <div key={d.id} className={'card upsw ups-' + tone} onClick={() => openDevice(d)}>
      <div className="row" style={{ gap: 8 }}><KindIcon kind="ups" name={nameNoFlag(d.name)} size={28} round={8} /><b className="ellipsis grow" style={{ fontSize: 15 }}>{nameNoFlag(d.name)}</b>
        <span className={'badge ' + (tone === 'green' ? 'online' : tone === 'red' ? 'offline' : 'warning')}>{u.onBattery ? 'От батареи' : u.estimated ? 'Расчёт' : 'От сети'}</span></div>
      <div className="upsw-main"><BatteryArt u={u} />
        <div style={{ minWidth: 0 }}><div className="ups-big">{u.runtimeEstimated ? '≈ ' : ''}{fmtMinShort(u.runtimeMin)}</div>
          <div className="dim" style={{ fontSize: 12.5 }}>хватит при отключении света{u.charge != null ? ` · заряд ${Math.round(u.charge)}%` : ''}</div></div></div>
      <div className="dim3" style={{ fontSize: 11.5, margin: '2px 0 4px' }}>Нагрузка {u.loadW} Вт{u.nominalW ? ` из ${Math.round(u.nominalW)} Вт · ${u.loadPct}%` : ''}</div>
      {u.loadPct != null ? <Bar value={u.loadPct} warnAt={70} badAt={85} /> : null}
      {shown.length ? <div className="upsw-feeds">{shown.map((c, i) => <span key={i} className="upsw-chip" title={nameNoFlag(c.name)}>
        <Icon name={c.kind === 'pdu' ? 'bolt' : c.kind || 'other'} size={13} /><span className="ellipsis">{nameNoFlag(c.name)}</span><b>{c.w} Вт</b></span>)}
        {feeds.length > shown.length ? <span className="upsw-chip more">+{feeds.length - shown.length}</span> : null}</div> : <div className="dim3" style={{ fontSize: 12, marginTop: 8 }}>Что подключено — не указано: откройте ИБП и заполните</div>}
      {u.supply ? <div className="dim3" style={{ fontSize: 11.5, marginTop: 8 }}>Питается от: {u.supply.name}{u.supply.outlet ? `, розетка ${u.supply.outlet}` : ''}</div> : null}
    </div>; })}</div>;
}


/* «Оплата серверов»: the servers with a payment reminder, the nearest date first; «Оплатил» moves the date to the next period */
const payDevices = d => d.devices.filter(x => x.pay && x.pay.on && x.pay.due && payLeft(x.pay) != null).sort((a, b) => payLeft(a.pay) - payLeft(b.pay));
function PayWidget() {
  const { data, admin, openDevice, setTab, refresh } = useApp(); const toast = useToast(); const [busy, setBusy] = useState('');
  const list = payDevices(data);
  if (!list.length) return <Card title="Оплата серверов"><div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Напоминаний нет. Откройте VPS в «Устройствах» → «Оплата и напоминание»: выберите дату, сумму и сайт, куда платить, — Rack Live напомнит заранее, в том числе в Telegram.</div>
    <div style={{ marginTop: 10 }}><Btn size="sm" onClick={() => setTab('devices')}>К устройствам</Btn></div></Card>;
  const paid = async d => { setBusy(d.id); await payPaid(d.id, toast, refresh); setBusy(''); };
  return <Card title="Оплата серверов">
    <div className="pay-list">{list.map(d => { const n = payLeft(d.pay), tone = payTone(n);
      return <div key={d.id} className={'pay-row pay-' + tone}>               {/* one line: who · when, date, sum · «Оплатить» · a round tick */}
        <button type="button" className="pay-main" onClick={() => openDevice(d)}>
          <KindIcon kind={d.kind || 'server'} name={d.name} size={30} round={9} />
          <span className="pay-txt"><b className="ellipsis">{nameNoFlag(d.name)}</b>
            <small className="ellipsis"><em className="pay-when">{payWhen(n)}</em>{[payDate(d.pay), payMoney(d.pay)].filter(Boolean).map(x => ' · ' + x).join('')}</small></span></button>
        <span className="pay-acts">
          {d.pay.url ? <a className="btn sm pay-go" href={d.pay.url} target="_blank" rel="noopener noreferrer" title="Открыть сайт оплаты">Оплатить</a> : null}
          {admin ? <Btn size="sm" icon="check" className="pay-done" busy={busy === d.id} onClick={() => paid(d)} title="Оплатил(а): дата сдвинется на следующий период" /> : null}</span>
      </div>; })}</div>
  </Card>;
}

/* «Клиенты VPN»: the servers with the counting switched on; the main server's total on top */
const vpnList = d => Object.entries((d.vpnLoad || {}).devices || {}).map(([id, r]) => ({ id, r, dev: d.devices.find(x => x.id === id) })).filter(x => x.dev);
function VpnWidget() {
  const { data, openDevice, setTab } = useApp(); const list = vpnList(data); const sys = (data.vpnLoad || {}).system;
  if (!list.length) return <Card title="Клиенты VPN"><div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Подсчёт не включён. Откройте VPS в «Устройствах» → «Клиенты VPN» и включите: Rack Live покажет, сколько у вас клиентов и сколько ещё выдержит сервер.</div>
    <div style={{ marginTop: 10 }}><Btn size="sm" onClick={() => setTab('devices')}>К устройствам</Btn></div></Card>;
  return <Card title="Клиенты VPN">
    {sys ? <div className="stats" style={{ marginBottom: 10 }}><Stat k="Онлайн" v={sys.online} /><Stat k="Клиентов" v={sys.clients == null ? '—' : sys.clients} /><Stat k="Ещё выдержит" v={vpnN(sys.k)} /></div> : null}
    <div className="pay-list">{list.map(({ id, r, dev }) => <div key={id} className="vpn-row">
      <button type="button" className="pay-main" onClick={() => openDevice(dev)}>
        <KindIcon kind={dev.kind || 'server'} name={dev.name} size={30} round={9} />
        <span style={{ minWidth: 0, textAlign: 'left' }}><b className="ellipsis" style={{ display: 'block' }}>{nameNoFlag(dev.name)}{r.main ? ' · главный' : ''}</b>
          <span className="dim3" style={{ fontSize: 12 }}>{r.detected ? `онлайн ${r.online == null ? '—' : r.online}${r.clients != null ? ' из ' + r.clients : ''}` : 'VPN не найден'}</span></span></button>
      <span className={'badge ' + (r.k == null ? '' : r.k < 5 ? 'offline' : r.k < 20 ? 'warning' : 'online')}>{r.k == null ? 'нет оценки' : 'ещё ' + vpnN(r.k)}</span>
    </div>)}</div>
  </Card>;
}

/* the catalogue — iOS-style sizes: S = a square tile (1 of 4 columns; 1 of 2 on a phone — two in a row),
   M = half the width (whole width on a phone), L = the whole width. sizes: which ones a widget allows.
   tile(data) → the square form: a big value and a line; go → where a tap on the tile leads (else the whole widget opens). */
const newLive = d => (d.newDevices || []).filter(r => findClient(d, r.mac));      // the same list the «Новые в сети» window shows
const avgUptime = d => { const k = (d.uptime || []).filter(u => u.pct != null); return k.length ? k.reduce((a, u) => a + u.pct, 0) / k.length : null; };
const ALL = ['S', 'M', 'L'];
const WIDGETS = {
  rack: { title: 'Шкафы и места', icon: 'rack', color: '#5e5ce6', size: 'M', sizes: ['S', 'M'], once: true, desc: 'Серверный шкаф, щитки и комнаты с оборудованием; квадратом — кнопка, открывает сам шкаф',
    flat: true, render: () => <RackView />, tile: d => ({ v: (d.racks || []).length || '', s: 'шкафы и места' }) },
  stats: { title: 'Сводка', icon: 'pulse', color: '#0a84ff', size: 'M', sizes: ALL, once: true, desc: 'Устройства в сети, проблемы, клиенты, PoE', render: () => <StatsWidget />,
    tile: d => ({ v: `${d.devices.filter(x => !x.healthSkip && (x.state || {}).status === 'online').length}/${d.devices.filter(x => !x.healthSkip).length}`, s: 'устройств в сети' }) },
  state: { title: 'Состояние сети', icon: 'shield', color: '#30d158', size: 'M', sizes: ALL, once: true, desc: 'Здоровье и безопасность сети', render: () => <StateCard />,
    tile: d => ({ v: `${d.health ? d.health.score : '—'} · ${d.security ? d.security.score : '—'}`, s: 'здоровье · защита', bad: d.security && d.security.counts.bad }) },
  internet: { title: 'Интернет', icon: 'globe', color: '#64d2ff', size: 'M', sizes: ALL, once: true, desc: 'Скорость интернета по расписанию', render: () => <InternetCard />,
    tile: d => { const l = ((d.inet || {}).items || []).filter(x => x.source === 'racklive' && x.down != null).slice(-1)[0];
      return { v: l ? Math.round(l.down) + '↓' : '—', s: l ? `${Math.round(l.up)}↑ Мбит/с` : 'замеров нет' }; } },
  ups: { title: 'ИБП', icon: 'ups', color: '#f5b800', size: 'M', sizes: ALL, list: true, once: true, desc: 'На сколько хватит батареи, нагрузка и что питается от ИБП', render: () => <UpsWidget />,
    tile: d => { const u = upsFirst(d); const s = u && u.state.ups;
      return s ? { v: fmtMinShort(s.runtimeMin), s: `${s.loadW} Вт${s.loadPct != null ? ' · ' + s.loadPct + '%' : ''}`, bad: upsTone(s) !== 'green', tone: upsTone(s) === 'green' ? undefined : upsTone(s) === 'red' ? 'red' : 'yellow' }
        : { v: '', s: 'добавить ИБП' }; },
    go: ctx => { const u = upsFirst(ctx.data); if (u) ctx.openDevice(u); else ctx.setTab('devices'); } },
  uptime: { title: 'Доступность', icon: 'pulse', color: '#34c759', size: 'M', sizes: ALL, once: true, desc: 'Кто пропадал за 30 дней', render: () => <UptimeCard />,
    tile: d => { const a = avgUptime(d); return { v: a == null ? '—' : pctText(a), s: 'за 30 дней' }; } },
  newdev: { title: 'Новые в сети', icon: 'plus', color: '#bf5af2', size: 'M', sizes: ALL, once: true, desc: 'Незнакомые устройства за неделю', render: () => isTestLook() ? <NewDevInstr /> : <NewDevicesCard />,
    tile: d => { const n = newLive(d).filter(x => x.decision === 'ask').length; return { v: n, s: n ? 'ждут решения' : 'все свои', bad: n > 0 }; } },
  speed: { title: 'Тест скорости', icon: 'gauge', color: '#30d158', size: 'S', sizes: ALL, once: true, desc: 'Последний замер и кнопка «Начать»', render: () => <SpeedWidget />,
    tile: d => { const l = (d.speedtests || []).filter(t => t.kind !== 'iperf').slice(-1)[0]; return { v: l ? mbpsText(l.down) + '↓' : '—', s: 'нажмите — тест' }; },
    go: ctx => ctx.openSpeed() },
  frank: { title: 'Frank', icon: 'eye', color: '#636366', size: 'M', sizes: ALL, once: true, desc: 'Задать вопрос помощнику прямо с главной', flat: true, render: () => <FrankWidget />,
    tile: () => ({ v: '', s: 'спросить Frank' }), go: ctx => ctx.askAi('') },
  advice: { title: 'Советы Frank', icon: 'eye', color: '#bf5af2', size: 'M', sizes: ALL, list: true, once: true, desc: 'Раз в несколько дней Frank советует, что добавить и что улучшить',
    render: () => <AdviceWidget />, tile: d => { const n = ((d.advice || {}).items || []).length; return { v: n || '', s: n ? ruPlural(n, 'совет', 'совета', 'советов') + ' от Frank' : 'советов нет', bad: n > 0 }; } },
  pay: { title: 'Оплата серверов', icon: 'card', color: '#ff9f0a', size: 'M', sizes: ALL, list: true, once: true, desc: 'Когда платить за VPS и хостинг: дата, сумма, кнопка «Оплатить» и «Оплатил»',
    render: () => <PayWidget />,
    tile: d => { const l = payDevices(d)[0]; if (!l) return { v: '', s: 'добавить напоминание' }; const n = payLeft(l.pay);
      return { v: n < 0 ? '−' + -n + ' дн.' : n === 0 ? 'сегодня' : n + ' дн.', s: nameNoFlag(l.name), bad: n <= 3, tone: n < 0 ? 'red' : n <= 3 ? 'yellow' : undefined }; },
    go: ctx => { const l = payDevices(ctx.data)[0]; if (l) ctx.openDevice(l); else ctx.setTab('devices'); } },
  vpn: { title: 'Клиенты VPN', icon: 'shield', color: '#5e5ce6', size: 'M', sizes: ALL, list: true, once: true, desc: 'Сколько клиентов на VPN-серверах и сколько ещё выдержат',
    render: () => <VpnWidget />,
    tile: d => { const sys = (d.vpnLoad || {}).system; const l = vpnList(d); if (!l.length) return { v: '', s: 'включить подсчёт' };
      const k = sys ? sys.k : l.reduce((a, x) => a + (x.r.k || 0), 0); const on = sys ? sys.online : l.reduce((a, x) => a + (x.r.online || 0), 0);
      return { v: k ? vpnN(k).replace('≈ ', '') : on, s: k ? 'ещё выдержит' : 'онлайн', bad: !!k && k < 5 }; },
    go: ctx => { const l = vpnList(ctx.data); const m = l.find(x => x.r.main) || l[0]; if (m) ctx.openDevice(m.dev); else ctx.setTab('devices'); } },
  note: { title: 'Заметка', icon: 'edit', color: '#ffd60a', size: 'S', sizes: ALL, list: true, desc: 'Свой текст: телефоны, пароль от гостевой сети…',
    render: (w, edit, onOpts) => <NoteWidget w={w} edit={edit} onOpts={onOpts} />, tile: (d, w) => ({ v: '', s: ((w.opts || {}).text || 'пусто').split('\n')[0] }) },
};
const DASH_DEFAULT = ['rack', 'stats', 'state', 'internet', 'uptime'].map(type => ({ id: type, type, size: WIDGETS[type].size }));
// layouts saved before sizes existed: {w, h, compact} → a size
const sizeOf = w => { const d = WIDGETS[w.type]; let s = w.size || (w.compact ? 'S' : (w.w || 2) >= 4 ? 'L' : 'M');
  return d.sizes.includes(s) ? s : d.sizes.includes('M') ? 'M' : d.sizes[d.sizes.length - 1]; };
const spanOf = (size, cols) => cols === 2 ? (size === 'S' ? 1 : 2) : size === 'S' ? 1 : size === 'M' ? 2 : 4;
const LONG_PRESS = 350;
/* отклик под пальцем: Android — vibrate; iPhone (Safari 18+, и в PWA) не знает vibrate, но щёлкает «тактильно» при нажатии на переключатель <input switch> — им и пользуемся */
function haptic(ms = 14) {
  try {
    if (navigator.vibrate && navigator.vibrate(ms)) return;
    const l = document.createElement('label'), i = document.createElement('input');
    i.type = 'checkbox'; i.setAttribute('switch', ''); l.appendChild(i); l.style.cssText = 'position:fixed;left:-99px;top:0;opacity:0;pointer-events:none';
    document.body.appendChild(l); l.click(); setTimeout(() => l.remove(), 50);
  } catch (e) { /* без отклика */ }
}
/* как на iPhone: подержать палец на виджете — отклик, и главная переходит в расстановку (двигать, менять размер, добавлять) */
function holdToArrange(e, onHold) {
  if (!e.touches || e.touches.length > 1 || e.target.closest('input, textarea, select, [contenteditable]')) return;
  const t0 = e.touches[0], x0 = t0.clientX, y0 = t0.clientY;
  const done = () => { clearTimeout(timer); document.removeEventListener('touchmove', mv); document.removeEventListener('touchend', done); document.removeEventListener('touchcancel', done); };
  const mv = ev => { const t = ev.touches[0]; if (t && Math.hypot(t.clientX - x0, t.clientY - y0) > 10) done(); };
  const timer = setTimeout(() => { done(); onHold();
    const eat = ev => { ev.stopPropagation(); ev.preventDefault(); };              // палец отпустили — это не «нажатие» на виджет
    window.addEventListener('click', eat, { capture: true, once: true }); setTimeout(() => window.removeEventListener('click', eat, true), 900); }, 480);
  document.addEventListener('touchmove', mv, { passive: true }); document.addEventListener('touchend', done); document.addEventListener('touchcancel', done);
}

function useCols(ref) {                  // → [columns, width of one column]
  const [st, setSt] = useState([4, 0]);
  useLayoutEffect(() => {                  // measured before the first paint — squares never flash at a wrong height
    const el = ref.current; if (!el) return;
    const read = () => { const c = el.clientWidth >= 680 ? 4 : 2; const w = (el.clientWidth - (c - 1) * DASH_GAP) / c;
      setSt(s => s[0] === c && Math.abs(s[1] - w) < .5 ? s : [c, w]); };
    read(); const ro = new ResizeObserver(read); ro.observe(el); return () => ro.disconnect();
  }, []);
  return st;
}

function Dashboard() {
  const ctx = useApp(); const { data, admin, edit, arrange } = ctx; const toast = useToast();
  const saved = ((data.dashboard || {}).widgets || []).filter(w => WIDGETS[w.type]);
  const norm = l => l.map(w => ({ ...w, size: sizeOf(w) }));
  const [list, setList] = useState(norm(saved.length ? saved : DASH_DEFAULT));
  const [drag, setDrag] = useState(null);
  const [adding, setAdding] = useState(false);
  const [full, setFull] = useState(() => { const t = new URLSearchParams(location.search).get('wfull'); return t && WIDGETS[t] ? { id: t, type: t, size: 'M', opts: {} } : null; });
  const gridRef = useRef(null); const els = useRef({}); const rects = useRef({}); const flip = useRef(false);
  const follow = useRef(null);                       // while moving: re-pin the lifted widget under the finger after each re-layout
  const [cols, colW] = useCols(gridRef);
  const savedKey = JSON.stringify(saved);
  useEffect(() => { if (!drag && saved.length) setList(norm(saved)); }, [savedKey]);
  useEffect(() => { if (!edit) ctx.setArrange(false); }, [edit]);
  const save = async next => {
    setList(next);
    try { await api('/api/dashboard', { method: 'PUT', body: { widgets: next } }); } catch (e) { toast(e.message, true); }
  };

  // FLIP after a move / resize / removal: everything glides to its new place
  useLayoutEffect(() => {
    Object.entries(els.current).forEach(([id, el]) => {
      if (!el) return;
      if (id === drag) { if (follow.current) follow.current(); return; }      // the lifted one follows the finger, not FLIP
      const r = el.getBoundingClientRect(), p = rects.current[id];
      if (flip.current && p && (Math.abs(p.left - r.left) > 1 || Math.abs(p.top - r.top) > 1)) {
        el.style.transition = 'none'; el.style.transform = `translate(${p.left - r.left}px, ${p.top - r.top}px)`;
        void el.offsetWidth;                     // apply the inverse now, then glide to zero (no waiting for a frame)
        el.style.transition = 'transform .32s cubic-bezier(.2,.9,.3,1)'; el.style.transform = '';
      }
      rects.current[id] = { left: r.left, top: r.top };
    });
  });
  useEffect(() => { const t = setInterval(() => Object.entries(els.current).forEach(([id, el]) => { if (el && !el.style.transform) rects.current[id] = el.getBoundingClientRect(); }), 400);
    return () => clearInterval(t); }, []);
  const settle = () => setTimeout(() => { flip.current = false; }, 500);

  // moving: the mouse picks a widget up at once; a finger — after a long press, so an ordinary swipe still scrolls the page
  const pickUp = (w, x0, y0, isTouch) => {
    setDrag(w.id); flip.current = true; let cur = list, last = '';
    if (isTouch) haptic(12);
    // the widget rides under the finger: translate = finger − grab point − where the grid put it now
    const el = els.current[w.id]; const r0 = el.getBoundingClientRect(); const gx = x0 - r0.left, gy = y0 - r0.top;
    let tx = 0, ty = 0, px = x0, py = y0;
    const pin = () => { const r = el.getBoundingClientRect(); const lx = r.left - tx, ly = r.top - ty;
      tx = px - gx - lx; ty = py - gy - ly; el.style.transition = 'none'; el.style.transform = `translate(${tx}px, ${ty}px)`; };
    follow.current = pin;
    const over = (x, y) => {
      px = x; py = y; pin();
      // the lifted widget's CENTRE decides: once it reaches the middle of another widget, they trade places
      const me = el.getBoundingClientRect(); const cx = me.left + me.width / 2, cy = me.top + me.height / 2;
      const tid = Object.keys(els.current).find(id => { const e2 = els.current[id]; if (id === w.id || !e2) return false;
        const r = e2.querySelector('.wg-in').getBoundingClientRect(); return cx >= r.left && cx <= r.right && cy >= r.top && cy <= r.bottom; });
      if (!tid) { last = ''; return; }
      if (tid === last) return; last = tid;                // one trade per widget entered — no flip-flopping
      const iD = cur.findIndex(x2 => x2.id === w.id), iT = cur.findIndex(x2 => x2.id === tid);
      const rest = cur.filter(x2 => x2.id !== w.id); let i = rest.findIndex(x2 => x2.id === tid); if (iT > iD) i++;
      cur = [...rest.slice(0, i), cur.find(x2 => x2.id === w.id), ...rest.slice(i)]; setList(cur);
    };
    const drop = () => { follow.current = null;
      const r = el.getBoundingClientRect(); rects.current[w.id] = { left: r.left - tx, top: r.top - ty };   // its slot, not the finger: no second glide
      el.style.transition = 'transform .3s cubic-bezier(.2,.9,.3,1)'; el.style.transform = '';     // settles into its new slot
      setDrag(null); save(cur); settle(); };
    return { over, drop };
  };
  const startMove = (w, e) => {
    if (e.target.closest('.wg-x, .wg-size-btn, .wg-size-menu')) return;
    if (e.pointerType === 'mouse') {
      if (e.button > 0) return;
      e.preventDefault(); const g = pickUp(w, e.clientX, e.clientY, false);
      const move = ev => g.over(ev.clientX, ev.clientY);
      const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); g.drop(); };
      window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
    }
  };
  const startTouch = (w, e) => {
    if (e.target.closest('.wg-x, .wg-size-btn, .wg-size-menu') || e.touches.length > 1) return;
    const t0 = e.touches[0], x0 = t0.clientX, y0 = t0.clientY; let g = null, gone = false;
    const timer = setTimeout(() => { if (!gone) g = pickUp(w, x0, y0, true); }, LONG_PRESS);
    const move = ev => {
      const t = ev.touches[0]; if (!t) return;
      if (!g) { if (Math.hypot(t.clientX - x0, t.clientY - y0) > 10) { gone = true; clearTimeout(timer); end(); } return; }     // a swipe: let it scroll
      ev.preventDefault(); g.over(t.clientX, t.clientY);
    };
    const end = () => { clearTimeout(timer); document.removeEventListener('touchmove', move); document.removeEventListener('touchend', fin); document.removeEventListener('touchcancel', fin); };
    const fin = () => { end(); if (g) g.drop(); };
    document.addEventListener('touchmove', move, { passive: false }); document.addEventListener('touchend', fin); document.addEventListener('touchcancel', fin);
  };
  // size by a button (a small menu under the widget's corner): the widget changes once, the others glide
  const setSize = (w, size) => { if (size === w.size) return; flip.current = true; save(list.map(x => x.id === w.id ? { ...x, size } : x)); settle(); };
  const remove = w => { flip.current = true; save(list.filter(x => x.id !== w.id)); settle(); };
  const rename = w => { const t = prompt('Название виджета', w.title || WIDGETS[w.type].title); if (t != null) save(list.map(x => x.id === w.id ? { ...x, title: t.trim() } : x)); };
  const add = type => { const d = WIDGETS[type]; const id = type + (d.once ? '' : Date.now().toString(36));
    flip.current = true; save([...list, { id, type, size: d.size, title: '', opts: {} }]); settle(); setAdding(false);
    setTimeout(() => { const el = els.current[id]; el && el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 150); };
  const tap = w => { const d = WIDGETS[w.type]; if (d.go) d.go(ctx); else setFull(w); };

  const arranging = edit && admin && arrange;
  // «Аврора»: вместо кнопок сверху — пустая прозрачная плитка «+» последней в сетке (всегда под виджетами); появляется и уходит плавно
  const confirm = useConfirm();
  const [plus, setPlus] = useState(false);                // false | 'in' | 'out'
  useEffect(() => {
    if (arranging && isAurora()) { setPlus('in'); return; }
    setPlus(p => (p ? 'out' : false)); const t = setTimeout(() => setPlus(false), 280); return () => clearTimeout(t);
  }, [arranging]);
  const reset = useRef(null);
  reset.current = async () => {
    if (!(await confirm('Вернуть главную как была изначально? Ваша расстановка виджетов пропадёт.', { title: 'Как было', ok: 'Вернуть' }))) return;
    flip.current = true; save(DASH_DEFAULT); settle(); };
  useEffect(() => { const h = () => reset.current(); window.addEventListener('rl-dash-reset', h); return () => window.removeEventListener('rl-dash-reset', h); }, []);
  return <>
    {arranging ? <div className="dash-bar">
      <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>Расстановка виджетов</b>
        <div className="dim" style={{ fontSize: 12.5 }}>Долгое нажатие — поднять и перенести (мышью — сразу). Кнопка в углу виджета — размер: квадрат, половина, во всю ширину.</div></div>
      <Btn size="sm" onClick={() => { flip.current = true; save(DASH_DEFAULT); settle(); }}>Как было</Btn><Btn size="sm" kind="primary" icon="plus" onClick={() => setAdding(true)}>Виджет</Btn>
      {ctx.setMode ? <Btn size="sm" kind="primary" onClick={() => { ctx.setArrange(false); ctx.setMode('view'); }}>Готово</Btn> : null}
    </div> : null}
    <div className={'dash' + (arranging ? ' arranging' : '')} ref={gridRef} style={{ '--cols': cols }}>
      {list.map(w => <DashItem key={w.id} w={w} cols={cols} colW={colW} edit={edit && admin} arranging={arranging} lifted={drag === w.id} elRef={el => { els.current[w.id] = el; }} onMove={e => startMove(w, e)} onTouch={e => startTouch(w, e)} onSize={size => setSize(w, size)}
        onRemove={() => remove(w)} onRename={() => rename(w)} onTap={() => tap(w)}
        onHold={admin && !arranging && ctx.setMode ? () => { haptic(); ctx.setMode('edit'); ctx.setArrange(true); } : null}
        onOpts={o => save(list.map(x => x.id === w.id ? { ...x, opts: { ...(x.opts || {}), ...o } } : x))} />)}
      {plus ? <div className={'wg size-S wg-add ' + plus} style={{ gridColumn: 'span 1', gridRow: `span ${Math.max(1, Math.ceil(((colW || 150) + DASH_GAP + 24) / DASH_ROW))}` }}>
        <button type="button" title="Добавить виджет" aria-label="Добавить виджет" style={{ height: colW || 150 }} onClick={() => plus === 'in' && setAdding(true)}>
          <span><Icon name="plus" size={30} stroke={2.2} /></span></button>
        <div className="wg-label">Добавить</div></div> : null}
    </div>
    {adding ? <Modal title="Добавить виджет" onClose={() => setAdding(false)} icon={<Icon name="plus" size={20} color="var(--accent)" />}>
      <div className="wg-pick">{Object.entries(WIDGETS).map(([type, d]) => { const has = d.once && list.some(x => x.type === type);
        return <button key={type} type="button" className="wg-opt" disabled={has} onClick={() => add(type)}>
          <span className="wg-opt-ic" style={{ background: d.color }}><Icon name={d.icon} size={18} color="#fff" /></span>
          <span style={{ minWidth: 0 }}><b>{d.title}</b><small>{has ? 'уже на главной' : d.desc}</small></span></button>; })}</div>
    </Modal> : null}
    {full ? <Modal title={full.title || WIDGETS[full.type].title} wide onClose={() => setFull(null)}
      icon={<span className="wg-tile-ic" style={{ background: WIDGETS[full.type].color, width: 28, height: 28 }}><Icon name={WIDGETS[full.type].icon} size={15} color="#fff" /></span>}>
      <div className="wg-full">{(() => { const cur = list.find(x => x.id === full.id) || full;       // the live copy, so what was just typed stays on screen
        return WIDGETS[cur.type].render(cur, edit && admin, o => save(list.map(x => x.id === cur.id ? { ...x, opts: { ...(x.opts || {}), ...o } } : x))); })()}</div>
    </Modal> : null}
  </>;
}

function DashItem({ w, cols, colW, edit, arranging, lifted, elRef, onMove, onTouch, onSize, onRemove, onRename, onTap, onOpts, onHold }) {
  const { data } = useApp();
  const d = WIDGETS[w.type]; const inner = useRef(null); const [hIn, setHIn] = useState(160);
  const [menu, setMenu] = useState(false);
  useEffect(() => { if (!arranging) setMenu(false); }, [arranging]);
  useEffect(() => { if (!menu) return; const close = e => { if (!e.target.closest('.wg-size-menu, .wg-size-btn')) setMenu(false); };
    document.addEventListener('pointerdown', close); return () => document.removeEventListener('pointerdown', close); }, [menu]);
  const size = w.size;
  useLayoutEffect(() => {                  // measured before the first paint, then kept in sync — no first-frame overlap
    const el = inner.current; if (!el) return;
    setHIn(el.offsetHeight);
    const ro = new ResizeObserver(() => setHIn(el.offsetHeight)); ro.observe(el); return () => ro.disconnect();
  }, [size]);
  const hh = size === 'S' && colW ? colW : hIn;          // a square is as tall as a column is wide — no need to measure
  const rows = Math.max(1, Math.ceil((hh + DASH_GAP + (arranging ? 24 : 0)) / DASH_ROW));
  const span = spanOf(size, cols);
  const name = w.title || d.title;
  let body;
  const auT = size === 'S' && isAurora() && !THEME.tileArt[w.type] && AU_TILE[w.type] ? AU_TILE[w.type](data, w) : null;
  if (size === 'S' && isTestLook()) body = <TestTile w={w} d={d} name={name} data={data} onTap={onTap} arranging={arranging} />;      // «Test»: strict mini-instruments
  else if (auT) body = <button type="button" className={'wg-tile au-w au-w-' + w.type} onClick={arranging ? undefined : onTap}>{auT}</button>;
  else if (size === 'S') {
    const t = d.tile ? d.tile(data, w) : { v: '', s: '' };
    const col = THEME.tileColors[w.type] || d.color;                       // a custom look may recolour a tile ...
    const art = THEME.tileArt[w.type] ? <img className="tile-img" src={THEME.tileArt[w.type]} alt="" draggable="false" />
      : isAurora() && AU_TILE_ART[w.type] ? AU_TILE_ART[w.type](data, w) : TILE_ART[w.type] ? TILE_ART[w.type](data, w) : null;      // ... and bring its own picture instead of the drawn one
    const showV = t.v !== '' && t.v != null && !(art && TILE_NO_VALUE.has(w.type));
    body = <button type="button" className={'wg-tile t-' + w.type + (THEME.tileArt[w.type] ? ' has-art' : '') + (THEME.tileColors[w.type] ? ' has-color' : '')} onClick={arranging ? undefined : onTap}>
      <span className="wg-tile-top"><span className="wg-tile-ic" style={{ background: `var(--tile-ic-bg, ${col})` }}><Icon name={d.icon} size={14} color="#fff" stroke={2.2} style={{ stroke: 'var(--tile-ic-fg, #fff)' }} /></span>
        <span className="wg-tile-name ellipsis">{name}</span></span>
      <span className="wg-tile-art">{art}</span>
      <span className="wg-tile-big">{w.type === 'rack' && document.documentElement.getAttribute('data-skin') === 'net' ? <MiniRack /> : <Icon name={d.icon} size={46} stroke={1.5} />}</span>        {/* «Графит»: a big outline icon instead of the picture */}
      {showV ? <span className="wg-tile-v" style={{ color: t.bad ? 'var(--orange)' : undefined }}>{t.v}</span>
        : t.v !== '' && t.v != null ? <span className="wg-tile-v gv" style={{ color: t.bad ? 'var(--orange)' : undefined }}>{t.v}</span> : null}
      <span className="wg-tile-s ellipsis">{t.s}</span>
    </button>;
  } else {
    const content = d.render(w, edit && !arranging, onOpts);
    if (content == null && !arranging) return null;
    body = content == null ? <div className="dim3" style={{ fontSize: 12.5, padding: 6 }}>Пока нет данных для «{name}»</div> : content;
  }
  const view = size === 'L' && d.h;          // map / plan: a fixed height, the content fills it
  const tone = size === 'S' && d.tile ? (d.tile(data, w) || {}).tone : null;
  return <div className={'wg size-' + size + ' t-' + w.type + (d.flat ? ' flat' : '') + (tone ? ' tone-' + tone : '') + (view ? ' view' : '') + (d.list ? ' wg-list' : '') + (lifted ? ' lifted' : '') + (arranging ? ' arranging' : '')}
    data-wid={w.id} ref={elRef} onTouchStart={onHold ? e => holdToArrange(e, onHold) : undefined} style={{ gridColumn: `span ${span}`, gridRow: `span ${rows}`, '--tc': THEME.tileColors[w.type] || d.color }}>
    <div className="wg-in" ref={inner} style={view ? { height: d.h } : null}>
      <div className="wg-body">{body}</div>
      {arranging ? <div className="wg-cover" onPointerDown={onMove} onTouchStart={onTouch} onDoubleClick={onRename} onContextMenu={e => e.preventDefault()} /> : null}
    </div>
    {arranging ? <>
      <button type="button" className="wg-x" title="Убрать с главной" onPointerDown={e => e.stopPropagation()} onTouchStart={e => e.stopPropagation()} onClick={onRemove}><Icon name="minus" size={16} stroke={3} /></button>
      {d.sizes.length > 1 ? <button type="button" className={'wg-size-btn' + (menu ? ' on' : '')} title="Размер" onPointerDown={e => e.stopPropagation()}
        onTouchStart={e => e.stopPropagation()} onClick={() => setMenu(!menu)}><Icon name="resize" size={15} stroke={2.4} /></button> : null}
      {menu ? <div className="wg-size-menu" onPointerDown={e => e.stopPropagation()} onTouchStart={e => e.stopPropagation()}>
        {[['S', 'Квадрат'], ['M', cols === 2 ? 'Широкий' : 'Половина'], ['L', 'Во всю ширину']].filter(([k]) => !(cols === 2 && k === 'L')).map(([k, label]) =>
          <button key={k} type="button" className={'wg-size-opt' + (size === k ? ' on' : '')} disabled={!d.sizes.includes(k) && !(cols === 2 && k === 'M' && d.sizes.includes('L'))}
            onClick={() => { setMenu(false); onSize(cols === 2 && k === 'M' && !d.sizes.includes('M') ? 'L' : k); }}>
            <span className={'sz-ic sz-' + k} />{label}</button>)}
      </div> : null}
      <div className="wg-label ellipsis">{name}</div>
    </> : null}
  </div>;
}

/* ───────── square tiles: a small live picture for each widget (iOS small-widget style) ───────── */
const ST_COLOR = s => s === 'online' ? 'var(--green)' : s === 'warning' ? 'var(--orange)' : s === 'offline' ? 'var(--red)' : 'var(--text3)';

function MiniRing({ value, max = 100, color, label, sub, size = 100 }) {
  const r = 40, c = 2 * Math.PI * r, f = Math.max(0, Math.min(1, (value || 0) / (max || 1)));
  return <svg viewBox="0 0 100 100" width={size} height={size} className="mini-svg">
    <circle cx="50" cy="50" r={r} fill="none" stroke="var(--fill2)" strokeWidth="10" />
    <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${c * f} ${c}`} transform="rotate(-90 50 50)" />
    <text x="50" y={sub ? 52 : 58} textAnchor="middle" className="mini-num" style={{ fontSize: label.length > 4 ? 19 : 24 }}>{label}</text>
    {sub ? <text x="50" y="67" textAnchor="middle" className="mini-sub">{sub}</text> : null}
  </svg>;
}

function MiniGauge({ value }) {
  const max = [100, 500, 1000, 2500].find(m => (value || 0) <= m) || 2500;
  const f = Math.min(1, (value || 0) / max), a = Math.PI * (1 - f), col = value ? speedLevel(value)[1] : 'var(--text3)';
  const x = 50 + 38 * Math.cos(a), y = 54 - 38 * Math.sin(a);
  return <svg viewBox="0 0 100 62" className="mini-svg wide">
    <path d="M12 54 A38 38 0 0 1 88 54" fill="none" stroke="var(--fill2)" strokeWidth="9" strokeLinecap="round" />
    {f > .01 ? <path d={`M12 54 A38 38 0 0 1 ${x.toFixed(1)} ${y.toFixed(1)}`} fill="none" stroke={col} strokeWidth="9" strokeLinecap="round" /> : null}
    <line x1="50" y1="54" x2={50 + 27 * Math.cos(a)} y2={54 - 27 * Math.sin(a)} stroke="var(--text)" strokeWidth="3.5" strokeLinecap="round" />
    <circle cx="50" cy="54" r="5" fill="var(--text)" />
  </svg>;
}

function MiniSpark({ points, color }) {
  const vs = points.filter(v => v != null); if (vs.length < 2) return <div className="mini-empty">нет замеров</div>;
  const mx = Math.max(...vs) * 1.1 || 1, step = 100 / (vs.length - 1);
  const pts = vs.map((v, i) => `${(i * step).toFixed(1)},${(48 - v / mx * 44).toFixed(1)}`);
  return <svg viewBox="0 0 100 50" preserveAspectRatio="none" className="mini-svg wide fill">
    <defs><linearGradient id="spk" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".45" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
    <polygon points={`0,50 ${pts.join(' ')} 100,50`} fill="url(#spk)" />
    <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
  </svg>;
}

function MiniBars({ days }) {
  const list = days.slice(-30);
  return <div className="mini-bars">{list.map((p, i) => <i key={i} style={{ background: pctColor(p), height: p == null ? '25%' : Math.max(30, 100 - (100 - p) * 8) + '%' }} />)}</div>;
}

function MiniTopo({ data }) {        // the «star» scheme from the network map: a hub in the middle, devices on the rays — all blue (an offline one turns red)
  const nodes = ((data.topology || {}).nodes || []).filter(n => n.deviceId && n.kind !== 'router').slice(0, 6);
  const count = Math.max(nodes.length, 5);
  const pts = Array.from({ length: count }, (_, i) => { const a = -Math.PI / 2 + i * 2 * Math.PI / count;
    return [50 + 35 * Math.cos(a), 50 + 35 * Math.sin(a), nodes[i]]; });
  const col = n => (n && n.status === 'offline' ? 'var(--red)' : '#0a84ff');
  return <svg viewBox="0 0 100 100" className="mini-svg">
    <defs><radialGradient id="mtg" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#0a84ff" stopOpacity=".32" /><stop offset="1" stopColor="#0a84ff" stopOpacity="0" /></radialGradient></defs>
    <circle cx="50" cy="50" r="48" fill="url(#mtg)" />
    <circle cx="50" cy="50" r="35" fill="none" stroke="#0a84ff" strokeOpacity=".28" strokeWidth="1.6" strokeDasharray="2.5 4.5" />
    {pts.map(([x, y, n], i) => <line key={'l' + i} x1="50" y1="50" x2={x} y2={y} stroke={col(n)} strokeWidth="3.4" strokeLinecap="round" opacity=".6" />)}
    {pts.map(([x, y, n], i) => <g key={i}><circle cx={x} cy={y} r="10" fill={col(n)} opacity=".2" /><circle cx={x} cy={y} r="6.5" fill={col(n)} /><circle cx={x} cy={y} r="2.4" fill="#fff" opacity=".9" /></g>)}
    <circle cx="50" cy="50" r="16" fill="#0a84ff" /><circle cx="50" cy="50" r="16" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="2" />
    <circle cx="50" cy="50" r="7" fill="none" stroke="#fff" strokeWidth="3" /><circle cx="50" cy="50" r="2.2" fill="#fff" />
  </svg>;
}

function MiniPlan({ data }) {         // a floor plan like a drawing: walls, doors, windows, furniture and a wall being drawn with a pencil
  const tests = (data.speedtests || []).filter(t => t.where).length;
  const net = document.documentElement.getAttribute('data-skin') === 'net';
  const line = net ? 'var(--accent)' : '#ff9f0a';           // «Контроллер»: the blueprint itself drawn in blue instead of orange
  return <svg viewBox="0 0 100 100" className="mini-svg">
    <defs>
      <radialGradient id="mpw" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#30d158" stopOpacity=".55" /><stop offset="1" stopColor="#30d158" stopOpacity="0" /></radialGradient>
      <pattern id="mpg" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".9" fill={line} opacity=".3" /></pattern>
    </defs>
    <rect x="3" y="3" width="94" height="94" rx="9" fill="url(#mpg)" />
    <rect x="12" y="13" width="76" height="72" fill={line} opacity=".12" />
    <circle cx="72" cy="68" r={tests ? 24 : 17} fill="url(#mpw)" />
    {/* furniture: a bed, a table */}
    <rect x="17" y="18" width="22" height="15" rx="3" fill={line} opacity=".38" /><rect x="17" y="18" width="7" height="15" rx="3" fill={line} opacity=".55" />
    <circle cx="71" cy="31" r="7.5" fill="none" stroke={line} strokeWidth="2" opacity=".6" />
    {/* outer walls, then the partitions with a doorway */}
    <path d="M12 13 H88 V85 H12 Z" fill="none" stroke={line} strokeWidth="5" strokeLinejoin="round" />
    <path d="M54 13 V52 M12 52 H40 M54 52 H88" fill="none" stroke={line} strokeWidth="3.4" strokeLinecap="round" />
    <path d="M40 52 V38.5 A13.5 13.5 0 0 1 53.5 52" fill="none" stroke={line} strokeWidth="1.3" opacity=".75" />
    {/* windows */}
    <path d="M24 13 H38 M66 13 H80" stroke="#fff" strokeWidth="2.4" opacity=".9" /><path d="M88 62 V76" stroke="#fff" strokeWidth="2.4" opacity=".9" />
    {/* a new wall being drawn: dashed, handles at the ends, a pencil */}
    <path d="M26 52 V74" stroke="#0a84ff" strokeWidth="2.4" strokeDasharray="3 3.4" strokeLinecap="round" />
    <circle cx="26" cy="52" r="3.2" fill="#fff" stroke="#0a84ff" strokeWidth="1.8" /><circle cx="26" cy="74" r="3.2" fill="#fff" stroke="#0a84ff" strokeWidth="1.8" />
    <g transform="translate(33 80) rotate(38)"><rect x="-3" y="-17" width="6" height="15" rx="1.4" fill="#fff" stroke={line} strokeWidth="1.2" />
      <path d="M-3 -2 L3 -2 L0 5 Z" fill={net ? 'var(--accent)' : '#ffd60a'} stroke={line} strokeWidth="1" strokeLinejoin="round" /></g>
  </svg>;
}

function MiniWeb() {        // «Контроллер»: a green spiderweb filling the whole tile, the device caught off to one side of it (not dead centre)
  const a = [0, 36, 72, 108, 144, 180, 216, 252, 288, 324].map(deg => deg * Math.PI / 180);
  const pt = (r, ang) => [50 + r * Math.sin(ang), 46 - r * Math.cos(ang)];
  const ring = r => a.map(ang => pt(r, ang));
  const poly = r => ring(r).map(p => p.join(',')).join(' ');
  const [dx, dy] = pt(40, 72 * Math.PI / 180);
  return <svg viewBox="0 0 100 100" className="mini-svg">
    <g stroke="#30d158" strokeWidth="1.5" fill="none" opacity=".85" strokeLinejoin="round">
      {a.map((ang, i) => { const [x, y] = pt(40, ang); return <line key={i} x1="50" y1="46" x2={x} y2={y} />; })}
      <polygon points={poly(13)} /><polygon points={poly(26)} /><polygon points={poly(40)} />
    </g>
    <g transform={`translate(${dx} ${dy})`}>
      <rect x="-11" y="-8" width="22" height="16" rx="5" fill="#ff453a" />
      <circle cx="-4.5" cy="0" r="1.8" fill="#fff" /><circle cx="1.5" cy="0" r="1.8" fill="#fff" /><circle cx="7.5" cy="0" r="1.8" fill="#fff" />
    </g>
  </svg>;
}

function MiniGears() {        // «Контроллер»: two overlapping gears (like the picture sent), flat outline in our colours
  return <svg viewBox="0 0 100 100" className="mini-svg">
    <g transform="translate(36 36) rotate(-10) scale(2.55) translate(-12 -12)" fill="none" stroke="#0066ff" strokeWidth="1.7" strokeLinejoin="round" strokeLinecap="round">
      <path d={ICON_PATHS.settings} />
    </g>
    <g transform="translate(70 70) rotate(14) scale(1.65) translate(-12 -12)" fill="none" stroke="#8e8e93" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
      <path d={ICON_PATHS.settings} />
    </g>
  </svg>;
}

function MiniRack() {        // «Контроллер»: the same outline rack glyph, but its 4 LED dots are real circles so CSS can blink them one by one
  return <svg viewBox="0 0 24 24" className="mini-svg" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 2h14v20H5zM5 7h14M5 12h14M5 17h14" />
    <circle cx="8" cy="4.5" r=".9" fill="currentColor" stroke="none" /><circle cx="8" cy="9.5" r=".9" fill="currentColor" stroke="none" />
    <circle cx="8" cy="14.5" r=".9" fill="currentColor" stroke="none" /><circle cx="8" cy="19.5" r=".9" fill="currentColor" stroke="none" />
  </svg>;
}

function MiniKinds({ devices }) {       // device icons, each tinted by its status
  const more = devices.length > 6; const list = devices.slice(0, more ? 5 : 6);     // two rows of three
  return <div className="mini-kinds">{list.map(d => { const c = ST_COLOR((d.state || {}).status);
    return <span key={d.id} style={{ background: `color-mix(in srgb, ${c} 22%, transparent)`, color: c }} title={nameNoFlag(d.name)}><Icon name={d.kind} size={18} stroke={2.2} /></span>; })}
    {more ? <span className="more">+{devices.length - 5}</span> : null}</div>;
}

function MiniDots({ devices }) {
  return <div className="mini-dots">{devices.slice(0, 24).map(d => <i key={d.id} style={{ background: ST_COLOR((d.state || {}).status) }} title={nameNoFlag(d.name)} />)}</div>;
}

const TILE_ART = {
  stats: d => { const w = d.devices.filter(x => !x.healthSkip), on = w.filter(x => (x.state || {}).status === 'online').length;          // «без слежки» не считаются
    return <MiniRing value={on} max={w.length} color={on === w.length ? 'var(--green)' : 'var(--orange)'} label={`${on}/${w.length}`} />; },
  problems: d => { const t = probTone(d);         // drawn in currentColor = the state colour (soft gradient behind, see .tone-*)
    return t === 'green' ? <svg viewBox="0 0 100 100" className="mini-svg"><circle cx="50" cy="50" r="40" fill="currentColor" opacity=".16" />
        <circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="5" />
        <path d="M31 52 L45 66 L70 37" fill="none" stroke="currentColor" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" /></svg>
      : t === 'yellow' ? <svg viewBox="0 0 100 92" className="mini-svg"><path d="M50 8 L93 84 H7 Z" fill="currentColor" fillOpacity=".16" stroke="currentColor" strokeWidth="6" strokeLinejoin="round" />
        <path d="M50 36 V58" stroke="currentColor" strokeWidth="8" strokeLinecap="round" /><circle cx="50" cy="71" r="4.5" fill="currentColor" /></svg>
      : <svg viewBox="0 0 100 100" className="mini-svg"><circle cx="50" cy="50" r="40" fill="currentColor" fillOpacity=".16" stroke="currentColor" strokeWidth="6" />
        <path d="M50 28 V56" stroke="currentColor" strokeWidth="9" strokeLinecap="round" /><circle cx="50" cy="71" r="5.5" fill="currentColor" /></svg>; },
  state: d => <div className="mini-pair">
    {d.health ? <MiniRing value={d.health.score} color={d.health.score >= 80 ? 'var(--green)' : d.health.score >= 50 ? 'var(--orange)' : 'var(--red)'} label={String(d.health.score)} sub="сеть" /> : null}
    {d.security ? <MiniRing value={d.security.score} color={d.security.score >= 80 ? 'var(--green)' : d.security.score >= 50 ? 'var(--orange)' : 'var(--red)'} label={String(d.security.score)} sub="защита" /> : null}</div>,
  internet: d => <MiniSpark points={((d.inet || {}).items || []).filter(x => x.source === 'racklive').slice(-24).map(x => x.down)} color="#0a84ff" />,
  uptime: d => <MiniBars days={(() => { const all = (d.uptime || []).filter(u => u.kind !== 'ap'); if (!all.length) return [];
    return all[0].days.map((_, i) => { const v = all.map(u => u.days[i]).filter(x => x != null); return v.length ? Math.min(...v) : null; }); })()} />,
  speed: d => { const l = (d.speedtests || []).filter(t => t.kind !== 'iperf').slice(-1)[0]; return <MiniGauge value={l ? l.down : 0} />; },
  newdev: d => { if (document.documentElement.getAttribute('data-skin') === 'net') return <MiniWeb />;
    const fresh = (d.newDevices || []).filter(x => !x.trusted);
    return <div className="mini-faces">{fresh.slice(0, 4).map((x, i) => <span key={i} style={{ background: ['#bf5af2', '#0a84ff', '#ff9f0a', '#30d158'][i] }}>
      <Icon name={x.random ? 'phone' : 'other'} size={16} color="#fff" /></span>)}{fresh.length > 4 ? <span className="more">+{fresh.length - 4}</span> : null}
      {!fresh.length ? <span style={{ background: 'var(--green)' }}><Icon name="check" size={18} color="#fff" stroke={3} /></span> : null}</div>; },
  ups: d => { const u = upsFirst(d); return <BatteryArt u={u ? u.state.ups : null} vertical />; },
  map: d => <MiniTopo data={d} />,
  plan: d => <MiniPlan data={d} />,
  devices: d => <MiniKinds devices={d.devices} />,
  events: d => <div className="mini-events">{(d.events || []).slice(0, 3).map((e, i) => <div key={i}><i style={{ background: e.level === 'info' ? 'var(--accent)' : ST_COLOR(e.level) }} />
    <span className="ellipsis">{nameNoFlag(e.name)}: {e.text}</span></div>)}</div>,
  frank: () => <div className="mini-frank"><FrankEye size={120} round={0} /></div>,
  advice: d => <div className="mini-events">{((d.advice || {}).items || []).slice(0, 3).map((x, i) => <div key={i}><i style={{ background: (ADVICE_KIND[x.kind] || ADVICE_KIND.idea)[1] }} />
    <span className="ellipsis">{x.title}</span></div>)}</div>,
  shortcuts: d => document.documentElement.getAttribute('data-skin') === 'net' ? <MiniGears /> : <div className="mini-grid4">{SET_SECTIONS.filter(x => !x.need || d[x.need]).slice(0, 4).map(x =>
    <span key={x.id} style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>)}</div>,
  note: (d, w) => <div className="mini-note">{((w.opts || {}).text || 'Пустая заметка').split('\n').slice(0, 4).map((l, i) => <div key={i} className="ellipsis">{l || ' '}</div>)}</div>,
};
const probTone = d => { const st = d.devices.map(x => (x.state || {}).status);
  return st.includes('offline') ? 'red' : st.includes('warning') ? 'yellow' : 'green'; };
const TILE_NO_VALUE = new Set(['stats', 'problems', 'state', 'map', 'plan', 'events', 'frank', 'shortcuts', 'note']);   // the picture already says it
