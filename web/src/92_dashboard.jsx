/* «Главная»: a grid of widgets. In edit mode — drag by the handle to move (others glide out of the way),
   pull the corner to resize (width snaps to columns, height is free), «+ Виджет» adds, × removes.
   The layout lives on the server (data.dashboard) — the same on every device; phones show one column. */
const DASH_ROW = 8, DASH_GAP = 14;

function StatsWidget() {
  if (isTestLook()) return <StatsInstr />;
  const { data } = useApp(); const devices = data.devices;
  const problems = devices.filter(d => ['offline', 'warning'].includes(d.state && d.state.status));
  const clients = devices.reduce((a, d) => a + ((d.state && d.state.clients) || []).length, 0);
  const poe = devices.flatMap(d => (d.state && d.state.ports) || []).reduce((a, p) => a + (p.poeW || 0), 0);
  return <div className="stats">
    <Stat k="Устройства" v={`${devices.filter(d => d.state && d.state.status === 'online').length}/${devices.length}`} />
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
  return <Card title={<span className="row" style={{ gap: 8 }}><AppIcon app="frank" size={20} radius={6} />Спросить Frank</span>}>
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

function UpsWidget() {
  const { data, openDevice, setTab } = useApp();
  const list = upsList(data);
  if (isTestLook() && list.length) return <UpsInstr list={list} />;
  if (!list.length) return <Card title="ИБП"><div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>ИБП ещё не добавлен. Добавьте его в «Устройства» (тип «ИБП») или юнитом в шкаф — здесь появится, на сколько хватит батареи.</div>
    <div style={{ marginTop: 10 }}><Btn size="sm" onClick={() => setTab('devices')}>К устройствам</Btn></div></Card>;
  return <div className="upsw-list">{list.map(d => { const u = d.state.ups; const tone = upsTone(u);
    const feeds = [...u.connected].sort((a, b) => b.w - a.w); const shown = feeds.slice(0, 4);
    return <div key={d.id} className={'card upsw ups-' + tone} onClick={() => openDevice(d)}>
      <div className="row" style={{ gap: 8 }}><KindIcon kind="ups" size={28} round={8} /><b className="ellipsis grow" style={{ fontSize: 15 }}>{d.name}</b>
        <span className={'badge ' + (tone === 'green' ? 'online' : tone === 'red' ? 'offline' : 'warning')}>{u.onBattery ? 'От батареи' : u.estimated ? 'Расчёт' : 'От сети'}</span></div>
      <div className="upsw-main"><BatteryArt u={u} />
        <div style={{ minWidth: 0 }}><div className="ups-big">{u.runtimeEstimated ? '≈ ' : ''}{fmtMinShort(u.runtimeMin)}</div>
          <div className="dim" style={{ fontSize: 12.5 }}>хватит при отключении света{u.charge != null ? ` · заряд ${Math.round(u.charge)}%` : ''}</div></div></div>
      <div className="dim3" style={{ fontSize: 11.5, margin: '2px 0 4px' }}>Нагрузка {u.loadW} Вт{u.nominalW ? ` из ${Math.round(u.nominalW)} Вт · ${u.loadPct}%` : ''}</div>
      {u.loadPct != null ? <Bar value={u.loadPct} warnAt={70} badAt={85} /> : null}
      {shown.length ? <div className="upsw-feeds">{shown.map((c, i) => <span key={i} className="upsw-chip" title={c.name}>
        <Icon name={c.kind === 'pdu' ? 'bolt' : c.kind || 'other'} size={13} /><span className="ellipsis">{c.name}</span><b>{c.w} Вт</b></span>)}
        {feeds.length > shown.length ? <span className="upsw-chip more">+{feeds.length - shown.length}</span> : null}</div> : <div className="dim3" style={{ fontSize: 12, marginTop: 8 }}>Что подключено — не указано: откройте ИБП и заполните</div>}
      {u.supply ? <div className="dim3" style={{ fontSize: 11.5, marginTop: 8 }}>Питается от: {u.supply.name}{u.supply.outlet ? `, розетка ${u.supply.outlet}` : ''}</div> : null}
    </div>; })}</div>;
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
    tile: d => ({ v: `${d.devices.filter(x => (x.state || {}).status === 'online').length}/${d.devices.length}`, s: 'устройств в сети' }) },
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
  note: { title: 'Заметка', icon: 'edit', color: '#ffd60a', size: 'S', sizes: ALL, list: true, desc: 'Свой текст: телефоны, пароль от гостевой сети…',
    render: (w, edit, onOpts) => <NoteWidget w={w} edit={edit} onOpts={onOpts} />, tile: (d, w) => ({ v: '', s: ((w.opts || {}).text || 'пусто').split('\n')[0] }) },
};
const DASH_DEFAULT = ['rack', 'stats', 'state', 'internet', 'uptime'].map(type => ({ id: type, type, size: WIDGETS[type].size }));
// layouts saved before sizes existed: {w, h, compact} → a size
const sizeOf = w => { const d = WIDGETS[w.type]; let s = w.size || (w.compact ? 'S' : (w.w || 2) >= 4 ? 'L' : 'M');
  return d.sizes.includes(s) ? s : d.sizes.includes('M') ? 'M' : d.sizes[d.sizes.length - 1]; };
const spanOf = (size, cols) => cols === 2 ? (size === 'S' ? 1 : 2) : size === 'S' ? 1 : size === 'M' ? 2 : 4;
const LONG_PRESS = 350;

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
    if (isTouch && navigator.vibrate) navigator.vibrate(12);
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
  return <>
    {arranging ? <div className="dash-bar">
      <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>Расстановка виджетов</b>
        <div className="dim" style={{ fontSize: 12.5 }}>Долгое нажатие — поднять и перенести (мышью — сразу). Кнопка в углу виджета — размер: квадрат, половина, во всю ширину.</div></div>
      <Btn size="sm" onClick={() => { flip.current = true; save(DASH_DEFAULT); settle(); }}>Как было</Btn><Btn size="sm" kind="primary" icon="plus" onClick={() => setAdding(true)}>Виджет</Btn>
    </div> : null}
    <div className={'dash' + (arranging ? ' arranging' : '')} ref={gridRef} style={{ '--cols': cols }}>
      {list.map(w => <DashItem key={w.id} w={w} cols={cols} colW={colW} edit={edit && admin} arranging={arranging} lifted={drag === w.id} elRef={el => { els.current[w.id] = el; }} onMove={e => startMove(w, e)} onTouch={e => startTouch(w, e)} onSize={size => setSize(w, size)}
        onRemove={() => remove(w)} onRename={() => rename(w)} onTap={() => tap(w)}
        onOpts={o => save(list.map(x => x.id === w.id ? { ...x, opts: { ...(x.opts || {}), ...o } } : x))} />)}
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

function DashItem({ w, cols, colW, edit, arranging, lifted, elRef, onMove, onTouch, onSize, onRemove, onRename, onTap, onOpts }) {
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
  if (size === 'S' && isTestLook()) body = <TestTile w={w} d={d} name={name} data={data} onTap={onTap} arranging={arranging} />;      // «Test»: strict mini-instruments
  else if (size === 'S') {
    const t = d.tile ? d.tile(data, w) : { v: '', s: '' };
    const col = THEME.tileColors[w.type] || d.color;                       // a custom look may recolour a tile ...
    const art = THEME.tileArt[w.type] ? <img className="tile-img" src={THEME.tileArt[w.type]} alt="" draggable="false" /> : TILE_ART[w.type] ? TILE_ART[w.type](data, w) : null;      // ... and bring its own picture instead of the drawn one
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
    data-wid={w.id} ref={elRef} style={{ gridColumn: `span ${span}`, gridRow: `span ${rows}`, '--tc': THEME.tileColors[w.type] || d.color }}>
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
    return <span key={d.id} style={{ background: `color-mix(in srgb, ${c} 22%, transparent)`, color: c }} title={d.name}><Icon name={d.kind} size={18} stroke={2.2} /></span>; })}
    {more ? <span className="more">+{devices.length - 5}</span> : null}</div>;
}

function MiniDots({ devices }) {
  return <div className="mini-dots">{devices.slice(0, 24).map(d => <i key={d.id} style={{ background: ST_COLOR((d.state || {}).status) }} title={d.name} />)}</div>;
}

const TILE_ART = {
  stats: d => { const on = d.devices.filter(x => (x.state || {}).status === 'online').length;
    return <MiniRing value={on} max={d.devices.length} color={on === d.devices.length ? 'var(--green)' : 'var(--orange)'} label={`${on}/${d.devices.length}`} />; },
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
    <span className="ellipsis">{e.name}: {e.text}</span></div>)}</div>,
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
