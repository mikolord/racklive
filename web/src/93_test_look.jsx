/* «Test» look (Настройки → Оформление → Test): the side menu instead of the dock and the top tabs, widgets as instruments of a front panel
   (dials with needles, segment readouts, LED rows that light up one by one), and Frank as a 3D lens whose pupil follows the finger / pointer. */

/* ───────── the side menu ───────── */
function SideNav({ tabs, cur, setTab, problems, admin, edit, mode, setMode, arrange, setArrange, theme, setTheme, onFrank, onSpeed, onRefresh, onLogin, onLogout, onClose, title, live, stale }) {
  const [dx, setDx] = useState(0); const [out, setOut] = useState(false); const g = useRef(null);
  const shut = () => { setOut(true); setTimeout(onClose, 220); };
  useEffect(() => { const h = e => e.key === 'Escape' && shut(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);
  useLockPage();
  const down = ev => { if (ev.target.closest('button, input, .seg')) return; g.current = { x: ev.clientX }; try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch (x) { } };
  const move = ev => { if (g.current) setDx(Math.min(0, ev.clientX - g.current.x)); };
  const up = () => { if (!g.current) return; g.current = null; if (dx < -80) shut(); else setDx(0); };
  const go = fn => () => { shut(); fn(); };
  return ReactDOM.createPortal(<div className={'tl-nav-wrap' + (out ? ' out' : '')} onClick={e => e.target === e.currentTarget && shut()}>
    <aside className={'tl-nav' + (out ? ' out' : '')} style={dx ? { transform: `translateX(${dx}px)`, transition: 'none' } : null} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      <div className="tl-nav-head">
        <AppIcon size={34} radius={8} />
        <div className="grow" style={{ minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{title}</b><div className={'live' + (stale ? ' stale' : '')}><i />{live}</div></div>
        <button type="button" className="tl-x" aria-label="Закрыть меню" onClick={shut}><Icon name="x" size={16} /></button>
      </div>
      <div className="tl-nav-k">Разделы</div>
      <nav className="tl-nav-list">{tabs.map((t, i) => <button type="button" key={t.id} data-tour={'tab-' + t.id} className={'tl-nav-item' + (cur === t.id ? ' on' : '')} style={{ '--i': i }} onClick={go(() => setTab(t.id))}>
        <i className="tl-led" /><Icon name={t.icon} size={18} /><span className="grow">{t.label}</span>
        {t.id === 'events' && problems ? <span className="tl-count">{problems > 99 ? '99+' : problems}</span> : null}<Icon name="chevron" size={14} /></button>)}</nav>
      <div className="grow" />
      {admin ? <>
        <div className="tl-nav-k">Режим</div>
        <div className="tl-nav-pad" data-tour="edit-toggle"><Seg className="edit" value={mode} onChange={setMode} options={[{ value: 'view', label: 'Просмотр', icon: 'eye' }, { value: 'edit', label: 'Правка', icon: 'edit', cls: 'editing' }]} /></div>
        {edit && arrange != null ? <div className="tl-nav-row"><Icon name="list" size={18} /><span className="grow">Расстановка виджетов</span><Switch on={arrange} onChange={setArrange} /></div> : null}
      </> : null}
      <div className="tl-nav-k">Приборы</div>
      <div className="tl-nav-tools">
        {admin ? <button type="button" onClick={go(onFrank)}><FrankEye size={30} /><span>Frank</span></button> : null}
        <button type="button" onClick={go(onSpeed)}><Icon name="gauge" size={22} /><span>Скорость</span></button>
        <button type="button" onClick={() => setTheme(theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto')}><Icon name={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'eye'} size={22} />
          <span>{({ auto: 'Тема: авто', dark: 'Тёмная', light: 'Светлая' })[theme]}</span></button>
        <button type="button" onClick={go(onRefresh)}><Icon name="refresh" size={22} /><span>Обновить</span></button>
      </div>
      <div className="tl-nav-foot">{admin ? <button type="button" className="btn sm" onClick={go(onLogout)}><Icon name="logout" size={15} />Выйти</button>
        : <button type="button" className="btn sm primary" onClick={go(onLogin)}><Icon name="lock" size={15} />Войти</button>}<span className="dim3 mono" style={{ fontSize: 10.5 }}>RACK LIVE</span></div>
    </aside>
  </div>, document.body);
}

/* ───────── instruments, second take: a technical sheet — no panels, hairlines, thin big numbers, linear scales ───────── */
/* a number that counts up from zero when it appears */
function useCount(target, ms = 800) {        // counts up from zero the first time, later glides from the old value to the new one (no jump to 0 on every refresh)
  const [v, setV] = useState(0); const cur = useRef(0);
  useEffect(() => {
    if (typeof target !== 'number' || !isFinite(target)) { setV(target); return; }
    let raf = 0; const t0 = performance.now(), from = typeof cur.current === 'number' ? cur.current : 0;
    const step = t => { const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3), x = from + (target - from) * e; cur.current = x; setV(x); if (k < 1) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step); return () => cancelAnimationFrame(raf);
  }, [target]);
  return v;
}
function Num({ v, digits = 0 }) { const x = useCount(typeof v === 'number' ? v : NaN); return <>{typeof v === 'number' ? x.toFixed(digits) : v}</>; }

/* a ruler: ticks every 5 %, a filled hairline up to the value, a marker, thin zone lines under it */
function Scale({ value, max = 100, zones, marks, tone }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setOn(true), 60); return () => clearTimeout(t); }, []);
  const f = Math.max(0, Math.min(1, (value || 0) / max));
  return <div className="sc">
    <div className="sc-ticks">{Array.from({ length: 21 }, (_, i) => <i key={i} className={i % 10 === 0 ? 'b' : i % 2 === 0 ? 'm' : ''} style={{ left: i * 5 + '%' }} />)}</div>
    <div className="sc-line"><i style={{ width: (on ? f * 100 : 0) + '%', background: tone || undefined }} /></div>
    <div className="sc-mark" style={{ left: (on ? f * 100 : 0) + '%', background: tone || undefined, boxShadow: tone ? `0 0 6px ${tone}` : undefined }} />
    {zones ? <div className="sc-zones">{zones.map((z, i) => <i key={i} style={{ left: z[0] * 100 + '%', width: (z[1] - z[0]) * 100 + '%', background: z[2] }} />)}</div> : null}
    {marks ? <div className="sc-marks">{marks.map((m, i) => <span key={i} style={{ left: m[0] * 100 + '%' }}>{m[1]}</span>)}</div> : null}
  </div>;
}
const ZONES = [[0, .5, 'var(--red)'], [.5, .8, 'var(--orange)'], [.8, 1, 'var(--accent)']];
const scoreTone = s => (s == null ? null : s >= 80 ? 'var(--accent)' : s >= 50 ? 'var(--orange)' : 'var(--red)');

/* «Сводка»: four readings in a row, split by hairlines */
function StatsInstr() {
  const { data } = useApp(); const devices = data.devices;
  const on = devices.filter(d => d.state && d.state.status === 'online').length;
  const problems = devices.filter(d => ['offline', 'warning'].includes(d.state && d.state.status)).length;
  const clients = devices.reduce((a, d) => a + ((d.state && d.state.clients) || []).length, 0);
  const poe = devices.flatMap(d => (d.state && d.state.ports) || []).reduce((a, p) => a + (p.poeW || 0), 0);
  const cell = (k, v, sub, frac, warn, digits) => <div className={'sp-cell' + (warn ? ' warn' : '')}>
    <div className="sp-k">{k}</div><div className="sp-v"><Num v={v} digits={digits} />{sub ? <small>{sub}</small> : null}</div>
    <div className="sp-line"><i style={{ width: Math.max(0, Math.min(1, frac)) * 100 + '%' }} /></div></div>;
  return <div className="sp-row with-lamp">
    <div className="sp-lamp"><PilotLamp data={data} /></div>
    {cell('Устройства', on, '/' + devices.length, devices.length ? on / devices.length : 0)}
    {cell('Проблемы', problems, '', devices.length ? problems / devices.length : 0, problems > 0)}
    {cell('Клиенты', clients, '', Math.min(1, clients / 100))}
    {cell('PoE', +poe.toFixed(1), ' Вт', Math.min(1, poe / 370), false, 1)}
  </div>;
}

/* «Устройства»: a sheet — status, name, address */

/* the whole network's 30 days: each day = the worst device that day */
function uptimeDays(list) {
  const n = Math.max(0, ...list.map(u => (u.days || []).length));
  return Array.from({ length: n }, (_, i) => { const v = list.map(u => (u.days || [])[i]).filter(x => x != null); return v.length ? Math.min(...v) : null; });
}
/* «Доступность»: 30 thin day strokes — only a day with an outage is coloured */
function DayTicks({ days }) {
  days = [...Array(Math.max(0, 30 - days.length)).fill(null), ...days].slice(-30);        // always 30 strokes, the oldest on the left
  return <div className="dk">{days.map((p, i) => <i key={i} style={{ '--i': i, background: p == null ? 'var(--fill2)' : p >= 99.9 ? 'var(--green)' : p >= 99 ? 'var(--orange)' : 'var(--red)', height: p == null ? '35%' : '100%' }}
    title={p == null ? 'нет данных' : pctText(p)} />)}</div>;
}

/* a score reading for «Состояние сети»: label, the big number, the ruler */
function ScoreReading({ k, score, title, warn }) {
  const tone = scoreTone(score);
  return <div className="sr"><div className="sp-k">{k}<i className="sr-led" style={{ background: tone, boxShadow: `0 0 6px ${tone}` }} /></div>
    <div className="sr-v" style={{ color: score >= 80 ? undefined : tone }}><Num v={score} /><small>/100</small></div>
    <Scale value={score} zones={ZONES} tone={tone} />
    <div className={'sr-t ellipsis' + (warn ? ' warn' : '')}>{title}</div></div>;
}

/* ───────── Frank: a lens mark — a thin ring with aperture ticks, the pupil follows the finger, a status LED in the corner ───────── */

/* ───────── «Test» small widgets (squares): a label, a strict mini-instrument drawn in hairlines, the reading in thin numerals ───────── */
const TT_STATUS = s => (s === 'online' ? 'var(--green)' : s === 'warning' ? 'var(--orange)' : s === 'offline' ? 'var(--red)' : 'var(--fill2)');
function TtRule({ f, color }) {                  // a short ruler: ticks, a line up to the value, a marker
  f = Math.max(0, Math.min(1, f || 0));
  return <svg className="tt-svg" viewBox="0 0 100 22" preserveAspectRatio="none">
    {Array.from({ length: 11 }, (_, i) => <line key={i} x1={i * 10} x2={i * 10} y1="0" y2={i % 5 === 0 ? 7 : 4} className="tt-tk" />)}
    <line x1="0" x2="100" y1="13" y2="13" className="tt-base" />
    <line x1="0" x2={f * 100} y1="13" y2="13" className="tt-fill" style={color ? { stroke: color } : null} />
    <line x1={f * 100} x2={f * 100} y1="6" y2="20" className="tt-mark" />
  </svg>;
}
function TtDots({ items, cols = 8 }) {           // a matrix of status dots
  return <div className="tt-dots" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>{items.slice(0, cols * 4).map((c, i) => <i key={i} style={{ background: c, boxShadow: c && c !== 'var(--fill2)' && c !== 'var(--green)' ? `0 0 5px ${c}` : 'none' }} />)}</div>;
}
const TT_ART = {
  rack: d => { const r = (d.racks || [])[0]; if (!r) return null; const total = r.totalU || 12, used = new Set();
    (r.units || []).forEach(u => { for (let k = 0; k < (u.uSize || 1); k++) used.add((u.uStart || 1) + k); });
    const n = Math.min(total, 18);
    return <svg className="tt-svg tall" viewBox="0 0 60 100"><rect x="6" y="2" width="48" height="96" className="tt-frame" />
      {Array.from({ length: n }, (_, i) => { const u = n - i, y = 6 + i * (88 / n), h = 88 / n - 1.6;
        return <rect key={i} x="11" y={y} width="38" height={Math.max(1, h)} className={used.has(u) ? 'tt-unit on' : 'tt-unit'} />; })}</svg>; },
  stats: d => <div className="tt-lamp-wrap"><PilotLamp data={d} /></div>,
  state: d => <div className="tt-fw"><FirewallMark score={d.health ? d.health.score : null} /></div>,
  internet: d => { const pts = ((d.inet || {}).items || []).filter(x => x.source === 'racklive' && x.down != null).slice(-24).map(x => x.down); if (pts.length < 2) return null;
    const mx = Math.max(...pts, 1), mn = Math.min(...pts), y = v => 26 - (v - mn) / (mx - mn || 1) * 22;
    return <svg className="tt-svg" viewBox="0 0 100 30" preserveAspectRatio="none"><line x1="0" x2="100" y1="29" y2="29" className="tt-base" />
      <polyline points={pts.map((v, i) => `${i / (pts.length - 1) * 100},${y(v)}`).join(' ')} className="tt-line" /></svg>; },
  uptime: d => { const list = (d.uptime || []).filter(u => u.kind !== 'ap'); const days = [...Array(30).fill(null), ...uptimeDays(list)].slice(-30);
    return <div className="tt-days">{days.map((p, i) => <i key={i} style={{ background: p == null ? 'var(--fill2)' : p >= 99.9 ? 'var(--green)' : p >= 99 ? 'var(--orange)' : 'var(--red)', height: p == null ? '40%' : '100%' }} />)}</div>; },
  ups: d => { const u = upsFirst(d); const s = u && u.state.ups; if (!s) return null; const f = s.charge != null ? s.charge / 100 : Math.min(1, (s.runtimeMin || 0) / 120);
    return <svg className="tt-svg" viewBox="0 0 100 30"><rect x="1" y="4" width="90" height="22" className="tt-frame" /><rect x="91" y="11" width="6" height="8" className="tt-frame" />
      {Array.from({ length: 10 }, (_, i) => <rect key={i} x={5 + i * 8.5} y="8" width="6.5" height="14" className={i < Math.round(f * 10) ? 'tt-unit on' : 'tt-unit'} />)}</svg>; },
  newdev: d => { const all = newLive(d).slice(0, 10);
    return <svg className="tt-svg tt-glyph tt-radar" viewBox="0 0 80 80"><circle cx="40" cy="40" r="37" className="tt-frame" /><circle cx="40" cy="40" r="25" className="tt-base" fill="none" /><circle cx="40" cy="40" r="13" className="tt-base" fill="none" />
      <path d="M3 40 H77 M40 3 V77" className="tt-base" />
      <g className="tt-sweep-g"><path d="M40 40 L40 3 A37 37 0 0 1 66.2 13.8 Z" className="tt-sweep-fan" /><line x1="40" y1="40" x2="40" y2="3" className="tt-sweep" /></g>
      <circle cx="40" cy="40" r="2" style={{ fill: 'var(--text)' }} />
      {all.map((x, i) => { const a = (i * 137) % 360 * Math.PI / 180, r = 12 + (i * 7) % 22, cx = 40 + r * Math.sin(a), cy = 40 - r * Math.cos(a);
        return <g key={i} className="tt-blip" style={{ animationDelay: (i * .7) % 4 + 's' }}><circle cx={cx} cy={cy} r="6" className="tt-blip-ring" /><circle cx={cx} cy={cy} r="2.6" className="tt-blip-dot" /></g>; })}</svg>; },
  advice: d => <div className="tt-rows">{((d.advice || {}).items || []).slice(0, 3).map((x, i) => <div key={i}><i className="tt-bdot" /><span className="ellipsis">{x.title}</span></div>)}</div>,
  speed: d => { const l = (d.speedtests || []).filter(t => t.kind !== 'iperf').slice(-1)[0]; return <TtRule f={l ? Math.min(1, l.down / 1000) : 0} />; },
  frank: () => <div className="tt-center tt-frank"><FrankEye size={86} round={0} /></div>,
  note: (d, w) => <div className="tt-note">{((w.opts || {}).text || 'Пустая заметка').split('\n').slice(0, 4).map((l, i) => <div key={i} className="ellipsis">{l || ' '}</div>)}</div>,
};
const TT_NO_VALUE = new Set(['advice', 'frank', 'note']);
function TestTile({ w, d, name, data, onTap, arranging }) {
  const t = d.tile ? d.tile(data, w) || {} : {};
  const art = TT_ART[w.type] ? TT_ART[w.type](data, w) : null;
  const led = t.tone === 'red' || t.bad ? 'var(--red)' : t.tone === 'yellow' ? 'var(--orange)' : null;
  const showV = t.v !== '' && t.v != null && !TT_NO_VALUE.has(w.type);
  return <button type="button" className={'tt t-' + w.type} onClick={arranging ? undefined : onTap}>
    <span className="tt-top"><span className="tt-k ellipsis">{name}</span>{led ? <i className="tt-led" style={{ background: led, boxShadow: `0 0 6px ${led}` }} /> : null}</span>
    <span className="tt-art">{art || <Icon name={d.icon} size={30} stroke={1.2} />}</span>
    {showV ? <span className={'tt-v' + (t.bad ? ' warn' : '')}>{t.v}</span> : null}
    <span className="tt-s ellipsis">{t.s}</span>
  </button>;
}

/* ───────── passive rack units in 3D: a patch panel, an optical cross, a PON terminal (ONT) — built from their port map ───────── */
function unitPorts(data, unit) {
  const pm = unit.portmap || {}; const modem = unit.type === 'modem';
  return Array.from({ length: pm.count || 0 }, (_, i) => { const n = i + 1, live = portLive(data, unit, n), m = (pm.ports || {})[n] || {};
    return { n, kind: unit.type === 'cross' ? 'sfp' : 'rj45', link: !!(live && live.link), speed: live ? live.speed || 1000 : 0, label: m.label || (modem ? portName(unit, n) : ''), peers: [] }; });
}
function unitModel(unit) {
  const pm = unit.portmap || {}, N = pm.count || 0, type = unit.type, items = [], back = [];
  const M = (name, size, faces, view) => ({ format: 'racklive-model', version: 1, name, size, faces, parts: [], view: view || { rx: -14, ry: -18 } });
  if (type === 'modem') {                                                    // a PON terminal: LEDs on the front, sockets at the back
    const w = Math.max(170, 40 + N * 21), h = 30, d = 130;
    items.push({ type: 'text', x: 12, y: 11, text: (unit.name || 'ONT').slice(0, 14).toUpperCase(), size: 4, weight: 700 });
    ['PWR', 'PON', 'LOS', 'LAN'].forEach((l, i) => { const x = w - 70 + i * 15; items.push({ type: 'led', x, y: 12, r: 1.4, on: l !== 'LOS' }, { type: 'text', x: x - 4, y: 17, text: l, size: 2.2, weight: 500 }); });
    let x = 14;
    for (let n = 1; n <= N; n++) { const pon = n === 1;
      back.push({ type: 'port', n, kind: pon ? 'other' : 'rj45', x, y: pon ? 10 : 8.5, w: pon ? 11 : 15, h: pon ? 10 : 13 },
        { type: 'text', x: x + (pon ? 5.5 : 7.5), y: 24, text: pon ? 'PON' : 'LAN' + (n - 1), size: 2.4, weight: 600, align: 'center' });
      x += pon ? 20 : 19; }
    back.push({ type: 'port', kind: 'power', x: w - 22, y: 10, w: 9, h: 9 });
    return M(unit.name || 'ONT', { w, h, d }, { front: { items }, back: { items: back }, top: { items: [{ type: 'vent', x: w * .15, y: d * .2, w: w * .7, h: d * .4, slots: 14 }] } }, { rx: -16, ry: 158 });
  }
  const cross = type === 'cross', rows = N > (cross ? 16 : 24) ? 2 : 1, per = Math.ceil(N / rows);
  const PW = cross ? 12 : 14.5, PH = cross ? 9 : 12.5, PITCH = cross ? 15 : 16.5, GROUP = cross ? 4 : 6, GG = 6;
  const groups = Math.ceil(per / GROUP), rowW = per * PITCH - (PITCH - PW) + (groups - 1) * GG;
  const w = 440, h = rows === 2 ? 88 : 44, d = cross ? 200 : 100, x0 = (w - rowW) / 2;
  const rowY = r => (rows === 2 ? (r ? h / 2 + 8 : h / 2 - PH - 6) : (h - PH) / 2 + 3);
  for (let n = 1; n <= N; n++) { const r = Math.floor((n - 1) / per), c = (n - 1) % per, x = x0 + c * PITCH + Math.floor(c / GROUP) * GG, y = rowY(r);
    items.push({ type: 'text', x: x + PW / 2, y: y - 5, text: String(n), size: 2.6, weight: 600, align: 'center' });
    items.push({ type: 'port', n, kind: cross ? 'sfp' : 'rj45', x, y, w: PW, h: PH });
    const col = cross && ((pm.ports || {})[n] || {}).color ? fiberHex(pm.ports[n].color) : null;
    if (col) items.push({ type: 'rect', x, y: y + PH + 1.2, w: PW, h: 1.8, color: col }); }
  [9, w - 9].forEach(x => items.push({ type: 'circle', x, y: h / 2, r: 2.6 }));             // the rack screws
  items.push({ type: 'text', x: 18, y: 6, text: cross ? 'FIBER · ' + (pm.connector || 'SC') : 'PATCH · CAT6', size: 2.6, weight: 600 });
  return M(unit.name || (cross ? 'Оптический кросс' : 'Патч-панель'), { w, h, d }, { front: { items } }, { rx: -12, ry: -16 });
}
function UnitModel({ unit, sel, onPick }) {
  const { data } = useApp();
  const ent = (data.cards || []).find(c => c.of === unit.id) || {};
  const own = ent.model && (data.models || []).find(m => m.id === ent.model);
  const ports = useMemo(() => unitPorts(data, unit), [data, unit]);
  const auto = useMemo(() => unitModel(unit), [unit.id, unit.type, (unit.portmap || {}).count, JSON.stringify((unit.portmap || {}).ports || {})]);
  const purl = photoUrl(unit.id, ent);
  return <div className="vt-inline unit3d">{purl ? <PhotoPorts url={purl} spots={ent.spots || []} sel={sel} onPick={onPick} />
    : <Model3D model={own ? own.model : auto} ports={ports} sel={sel} onPick={onPick} view={ent.view} manual={!!own && ent.portsMode === 'manual'} marks={ent.mports} />}</div>;
}

/* ───────── a firewall: a brick wall that is whole while the network is healthy and loses bricks as the health score drops; below 30 it is red and cracked ───────── */
const FW_ROWS = 5, FW_COLS = 4, FW_BW = 18, FW_BH = 9, FW_G = 2;
const FW_BRICKS = (() => { const b = [];
  for (let r = 0; r < FW_ROWS; r++) { const off = r % 2 ? -FW_BW / 2 : 0;
    for (let c = 0; c <= FW_COLS; c++) { let x = off + c * (FW_BW + FW_G), w = FW_BW; if (x < 0) { w += x; x = 0; } const R = FW_COLS * (FW_BW + FW_G) - FW_G; if (x + w > R) w = R - x; if (w > 2) b.push({ x, y: r * (FW_BH + FW_G), w }); } }
  return b; })();
const FW_ORDER = [2, 7, 0, 11, 5, 14, 9, 3, 16, 12, 1, 18, 6, 10, 15, 4, 13, 8, 17, 19, 20, 21, 22];      // which brick falls next: from the top, scattered
function FirewallMark({ score }) {
  const s = score == null ? 100 : score, tone = score == null ? 'var(--text3)' : s >= 80 ? 'var(--accent)' : s >= 30 ? 'var(--orange)' : 'var(--red)';
  const n = s >= 80 ? 0 : Math.round((80 - s) / 80 * FW_BRICKS.length * .62) + 1;
  const gone = new Set(FW_ORDER.slice(0, n).filter(i => i < FW_BRICKS.length));
  const W = FW_COLS * (FW_BW + FW_G) - FW_G, H = FW_ROWS * (FW_BH + FW_G) - FW_G;
  return <svg className={'fw' + (s < 30 ? ' broken' : '')} viewBox={`-6 -6 ${W + 12} ${H + 22}`} style={{ '--fw': tone }}>
    {FW_BRICKS.map((b, i) => gone.has(i) ? <rect key={i} x={b.x} y={b.y} width={b.w} height={FW_BH} className="fw-gap" />
      : <rect key={i} x={b.x} y={b.y} width={b.w} height={FW_BH} className="fw-b" style={{ animationDelay: i * 30 + 'ms' }} />)}
    {s < 30 ? <path d={`M${W * .42} -4 L${W * .5} ${H * .3} L${W * .38} ${H * .55} L${W * .56} ${H * .8} L${W * .48} ${H + 2}`} className="fw-crack" /> : null}
    {[...gone].slice(0, 6).map((i, k) => <rect key={'d' + i} x={6 + k * 11 + (k % 2) * 3} y={H + 6 + (k % 2) * 3} width={7} height={4} className="fw-debris" transform={`rotate(${(k * 37) % 50 - 25} ${10 + k * 11} ${H + 8})`} />)}
  </svg>;
}

/* ───────── ИБП as an instrument: the runtime in thin numerals, a segmented battery, the load on a ruler, what it feeds as a spec list ───────── */
function UpsInstr({ list }) {
  const { openDevice } = useApp();
  return <div className="ui-list">{list.map(d => { const u = d.state.ups, tone = upsTone(u), col = tone === 'green' ? 'var(--accent)' : tone === 'red' ? 'var(--red)' : 'var(--orange)';
    const f = u.charge != null ? u.charge / 100 : 1, feeds = [...(u.connected || [])].sort((a, b) => b.w - a.w);
    return <div key={d.id} className="ui" onClick={() => openDevice(d)}>
      <div className="ui-head"><span className="sp-k">{d.name}</span><span className="ui-st" style={{ color: col }}><i style={{ background: col, boxShadow: `0 0 6px ${col}` }} />{u.onBattery ? 'от батареи' : u.estimated ? 'расчёт' : 'от сети'}</span></div>
      <div className="ui-main">
        <div><div className="sr-v"><Num v={u.runtimeMin || 0} /><small> мин</small></div><div className="sr-t">хватит при отключении света</div></div>
        <div className="ui-bat" title={u.charge != null ? 'заряд ' + Math.round(u.charge) + '%' : 'расчёт'}>{Array.from({ length: 10 }, (_, i) => <i key={i} className={i < Math.round(f * 10) ? 'on' : ''} style={i < Math.round(f * 10) ? { background: col } : null} />)}<b /></div>
      </div>
      <div className="sp-k" style={{ marginTop: 14 }}>Нагрузка · {u.loadW} Вт{u.nominalW ? ` из ${Math.round(u.nominalW)}` : ''}</div>
      {u.loadPct != null ? <Scale value={u.loadPct} zones={[[0, .7, 'var(--accent)'], [.7, .85, 'var(--orange)'], [.85, 1, 'var(--red)']]} tone={u.loadPct > 85 ? 'var(--red)' : u.loadPct > 70 ? 'var(--orange)' : null} /> : null}
      {feeds.length ? <div className="ui-feeds">{feeds.map((c, i) => <div key={i}><span className="ellipsis">{c.name}</span><i /><b>{c.w} Вт</b></div>)}</div> : null}
      {u.supply ? <div className="sr-t" style={{ marginTop: 8 }}>питается от: {u.supply.name}{u.supply.outlet ? `, розетка ${u.supply.outlet}` : ''}</div> : null}
    </div>; })}</div>;
}

/* «Новые в сети» opened: a big radar and the list as a sheet */
function NewDevInstr() {
  const { data } = useApp();
  const all = newLive(data), ask = all.filter(x => x.decision === 'ask');
  return <div className="nd-instr">
    <div className="nd-radar">{TT_ART.newdev(data)}</div>
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="sp-k">Новые за неделю · сейчас в сети</div>
      <div className="sr-v"><Num v={all.length} /><small>{ask.length ? ` · ждут решения: ${ask.length}` : ' · все свои'}</small></div>
      <div className="dt" style={{ marginTop: 10 }}>{all.slice(0, 8).map((r, i) => <div key={r.mac + i} className="dt-row" style={{ '--i': i, cursor: 'default' }}>
        <i className="tt-bdot dt-dot" /><span className="dt-n ellipsis">{r.name || (r.random ? 'Телефон или ноутбук' : 'Без имени')}</span><span className="dt-a ellipsis">{r.ip || r.mac}</span></div>)}</div>
      <div style={{ marginTop: 12 }}><NewDevicesCard /></div>
    </div>
  </div>;
}

/* ───────── «Сводка» as a pilot lamp: a bezel with a glowing lens; the colour says how the network is ───────── */
function PilotLamp({ data }) {           // an ordinary light bulb drawn in hairlines: the filament glows in the network's colour
  const ds = data.devices || [], off = ds.filter(x => (x.state || {}).status === 'offline').length, warn = ds.filter(x => (x.state || {}).status === 'warning').length;
  const tone = off ? 'var(--red)' : warn ? 'var(--orange)' : 'var(--accent)', word = off ? 'нет связи: ' + off : warn ? 'внимание: ' + warn : 'всё в сети';
  return <div className={'plamp' + (off ? ' bad' : '')} style={{ '--lc': tone }} title={word}>
    <svg className="bulb" viewBox="0 0 60 80">
      <circle cx="30" cy="27" r="24" className="bulb-glow" />
      <path d="M30 4 C17 4 8 13.5 8 25.5 C8 34 12.5 39.5 17 44.5 C19.5 47.3 21 50.5 21 54 V57 H39 V54 C39 50.5 40.5 47.3 43 44.5 C47.5 39.5 52 34 52 25.5 C52 13.5 43 4 30 4 Z" className="bulb-glass" />
      <path d="M24 56 V40 L21.5 31 M36 56 V40 L38.5 31" className="bulb-wire" />
      <path d="M21.5 31 Q24 26 26.5 31 Q29 26 31.5 31 Q34 26 36.5 31 L38.5 31" className="bulb-fil" />
      <path d="M21 60 H39 M22 64.5 H38 M23 69 H37" className="bulb-base" /><path d="M26 73 H34" className="bulb-base" />
      <path d="M16 20 Q18 12 25 9" className="bulb-hl" />
    </svg>
    <span className="plamp-w">{word}</span>
  </div>;
}

/* ───────── the rack in 3D: a 19″ cabinet (sides, roof, plinth, rails with U marks) and every unit as a box with its real front ───────── */
const R3 = { W: 600, D: 640, U: 44.45, TOP: 70, BOT: 90, PANEL: 482.6, EAR: 16 };
const R3_DEPTH = { switch: 260, router: 230, patch: 110, cross: 250, server: 580, nas: 430, ups: 470, pdu: 70, shelf: 420, organizer: 80, blank: 24, modem: 190, nvr: 360, other: 320 };
function R3Face({ w, h, tf, cls, style, children, onClick, title }) {
  return <div className={'r3f ' + (cls || '')} title={title} onClick={onClick} style={{ width: w, height: h, transform: tf, ...style }}>{children}</div>;
}
/* a box centred at (x, y, z) px, size (w, h, d) px; front = HTML of the front panel */
function R3Box({ x, y, z, w, h, d, front, cls = '', onClick, title, flip }) {
  const T = (tx, ty, tz, r) => `translate3d(${tx}px, ${ty}px, ${tz}px)${r ? ' ' + r : ''}`;
  const fr = flip ? T(x + w / 2, y - h / 2, z - d / 2, 'rotateY(180deg)') : T(x - w / 2, y - h / 2, z + d / 2);
  const bk = flip ? T(x - w / 2, y - h / 2, z + d / 2) : T(x + w / 2, y - h / 2, z - d / 2, 'rotateY(180deg)');
  return <>
    <R3Face w={w} h={h} tf={fr} cls={cls + ' front'} onClick={onClick} title={title}>{front}</R3Face>
    <R3Face w={w} h={h} tf={bk} cls={cls + ' back'} />
    <R3Face w={d} h={h} tf={T(x + w / 2, y - h / 2, z + d / 2, 'rotateY(90deg)')} cls={cls + ' side'} />
    <R3Face w={d} h={h} tf={T(x - w / 2, y - h / 2, z - d / 2, 'rotateY(-90deg)')} cls={cls + ' side'} />
    <R3Face w={w} h={d} tf={T(x - w / 2, y - h / 2, z - d / 2, 'rotateX(90deg)')} cls={cls + ' top'} />
    <R3Face w={w} h={d} tf={T(x - w / 2, y + h / 2, z + d / 2, 'rotateX(-90deg)')} cls={cls + ' bottom'} />
  </>;
}
function R3Front({ unit, dev, data }) {
  const many = unitDevIds(unit);
  const st = dev && dev.state ? dev.state.status : null;
  const pm = pmLeds(data, unit), ports = pm || (dev && dev.state && dev.state.ports) || [], sock = socketLeds(unit, dev);
  const leds = (sock || ports).filter(p => p.kind !== 'sfp').slice(0, unit.uSize > 1 ? 48 : 24);
  return <div className={'r3u' + (unit.type === 'blank' ? ' blank' : '')}>
    <i className="r3-ear l" /><i className="r3-ear r" />
    {unit.type === 'blank' ? null : <>
      <div className="r3u-id">{st ? <i className={'r3u-led ' + st} /> : null}<span className="ellipsis">{many.length > 1 ? many.map(id => (data.devices.find(x => x.id === id) || {}).name).filter(Boolean).join(' · ') : unit.name}</span></div>
      {leds.length >= (pm || sock ? 1 : 4) ? <Leds ports={leds} min={1} round={!!sock} /> : <div className="r3u-vent" />}
    </>}
  </div>;
}
function Rack3D({ rack, devById, side, onUnit }) {
  const { data } = useApp();
  const wrap = useRef(null); const [cw, setCw] = useState(640);
  useLayoutEffect(() => { const el = wrap.current; if (!el) return; const r = () => setCw(el.clientWidth); r(); const ro = new ResizeObserver(r); ro.observe(el); return () => ro.disconnect(); }, []);
  const [rot, setRot] = useState({ x: -10, y: side === 'back' ? 156 : -24 });
  useEffect(() => { setRot(r => ({ ...r, y: side === 'back' ? 156 : -24 })); }, [side]);
  const g = useRef(null); const moved = useRef(false);
  const down = e => { if (e.button > 0) return; g.current = { x: e.clientX, y: e.clientY, r: rot }; moved.current = false; };
  const move = e => { const s = g.current; if (!s) return; const dx = e.clientX - s.x, dy = e.clientY - s.y;
    if (!moved.current && Math.hypot(dx, dy) < 6) return; moved.current = true; try { e.currentTarget.setPointerCapture(e.pointerId); } catch (x) { }
    setRot({ y: s.r.y + dx * .45, x: Math.max(-40, Math.min(25, s.r.x - dy * .3)) }); };
  const up = () => { g.current = null; setTimeout(() => { moved.current = false; }, 0); };
  const k = Math.max(.42, Math.min(.95, (cw - 30) / (R3.W * 1.5)));
  const total = rack.totalU, W = R3.W * k, D = R3.D * k, uh = R3.U * k, inner = total * uh, H = (R3.TOP + R3.BOT) * k + inner;
  const top = -H / 2 + R3.TOP * k;
  const hasBack = rack.units.some(u => (u.side || 'front') === 'back');                                      // y of U1's top edge (U1 is the top unit)
  const shell = 'r3-shell';
  const P = (x, y, z, r) => `translate3d(${x}px, ${y}px, ${z}px)${r ? ' ' + r : ''}`;
  const rails = Array.from({ length: total }, (_, i) => <span key={i} style={{ height: uh }}>{i + 1}</span>);
  const unitBox = u => { const dev = devById[u.deviceId]; const h = u.uSize * uh - 1.5 * k, y = top + (u.uStart - 1) * uh + u.uSize * uh / 2;
    const dd = Math.min(R3.D - 90, R3_DEPTH[u.type] || R3_DEPTH[(dev && dev.kind) || 'other'] || 300) * k, back = (u.side || 'front') === 'back';
    const zf = D / 2 - 26 * k, z = back ? -zf + dd / 2 : zf - dd / 2;
    const open = () => { if (!moved.current) onUnit(u); };
    return <R3Box key={u.id} x={0} y={y} z={z} w={R3.PANEL * k} h={h} d={dd} flip={back} cls={'r3-unit' + (dev ? '' : ' plain')} onClick={open} title={u.name}
      front={<R3Front unit={u} dev={dev} data={data} />} />; };
  return <div className="r3-wrap" ref={wrap} style={{ '--k': k, height: H + 90 }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
    onDoubleClick={() => setRot({ x: -10, y: side === 'back' ? 156 : -24 })}>
    <div className="r3-stage"><div className="r3-obj" style={{ transform: `rotateX(${rot.x}deg) rotateY(${rot.y}deg)` }}>
      {/* the cabinet: outer skin and the inner walls you see through the open front */}
      <R3Face w={D} h={H} tf={P(W / 2, -H / 2, D / 2, 'rotateY(90deg)')} cls={shell + ' side'} />
      <R3Face w={D} h={H} tf={P(-W / 2, -H / 2, -D / 2, 'rotateY(-90deg)')} cls={shell + ' side'} />
      <R3Face w={D} h={H} tf={P(W / 2 - 3, -H / 2, -D / 2, 'rotateY(-90deg)')} cls={shell + ' inside'} />
      <R3Face w={D} h={H} tf={P(-W / 2 + 3, -H / 2, D / 2, 'rotateY(90deg)')} cls={shell + ' inside'} />
      {hasBack ? <>
        <R3Face w={(W - R3.PANEL * k) / 2} h={inner} tf={P(W / 2, top, -D / 2 - .5, 'rotateY(180deg)')} cls={shell + ' bezel stile'}><div className="r3-rail">{rails}</div></R3Face>
        <R3Face w={(W - R3.PANEL * k) / 2} h={inner} tf={P(-R3.PANEL * k / 2, top, -D / 2 - .5, 'rotateY(180deg)')} cls={shell + ' bezel stile r'}><div className="r3-rail">{rails}</div></R3Face>
        <R3Face w={W} h={R3.BOT * k} tf={P(W / 2, H / 2 - R3.BOT * k, -D / 2 - .5, 'rotateY(180deg)')} cls={shell + ' bezel plinth'}><i className="r3-grille" /></R3Face>
      </> : <R3Face w={W} h={H} tf={P(W / 2, -H / 2, -D / 2, 'rotateY(180deg)')} cls={shell + ' rear'} />}
      <R3Face w={W} h={H} tf={P(-W / 2, -H / 2, -D / 2 + 3)} cls={shell + ' inside wall'} />
      <R3Face w={W} h={D} tf={P(-W / 2, -H / 2, -D / 2, 'rotateX(90deg)')} cls={shell + ' roof'}><i className="r3-vents" /></R3Face>
      <R3Face w={W} h={D} tf={P(-W / 2, H / 2, D / 2, 'rotateX(-90deg)')} cls={shell + ' floor'} />
      <R3Face w={W} h={D} tf={P(-W / 2, -H / 2 + R3.TOP * k, D / 2, 'rotateX(-90deg)')} cls={shell + ' inside ceil'} />
      <R3Face w={W} h={D} tf={P(-W / 2, H / 2 - R3.BOT * k, -D / 2, 'rotateX(90deg)')} cls={shell + ' inside base'} />
      {/* the front frame: stiles, the head with the name, the plinth with feet */}
      <R3Face w={W} h={R3.TOP * k} tf={P(-W / 2, -H / 2, D / 2)} cls={shell + ' bezel head'}><span className="r3-name">{rack.name}</span><i className="r3-pwr" /></R3Face>
      <R3Face w={W} h={R3.BOT * k} tf={P(-W / 2, H / 2 - R3.BOT * k, D / 2)} cls={shell + ' bezel plinth'}><i className="r3-grille" /></R3Face>
      <R3Face w={(W - R3.PANEL * k) / 2} h={inner} tf={P(-W / 2, top, D / 2)} cls={shell + ' bezel stile'}><div className="r3-rail">{rails}</div></R3Face>
      <R3Face w={(W - R3.PANEL * k) / 2} h={inner} tf={P(R3.PANEL * k / 2, top, D / 2)} cls={shell + ' bezel stile r'}><div className="r3-rail">{rails}</div></R3Face>
      {/* the rear frame */}
      <R3Face w={W} h={R3.TOP * k} tf={P(W / 2, -H / 2, -D / 2 - .5, 'rotateY(180deg)')} cls={shell + ' bezel head'}><span className="r3-name">{rack.name} · тыл</span></R3Face>
      {rack.units.map(unitBox)}
    </div></div>
    <div className="r3-hint">потяните, чтобы повернуть · двойное нажатие — как было</div>
  </div>;
}
