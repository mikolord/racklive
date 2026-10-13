/* «Главная»: a grid of widgets. In edit mode — drag by the handle to move (others glide out of the way),
   pull the corner to resize (width snaps to columns, height is free), «+ Виджет» adds, × removes.
   The layout lives on the server (data.dashboard) — the same on every device; phones show one column. */
const DASH_ROW = 8, DASH_GAP = 14;

function StatsWidget() {
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

function ProblemsWidget() {
  const { data, openDevice } = useApp();
  const problems = data.devices.filter(d => ['offline', 'warning'].includes(d.state && d.state.status));
  if (!problems.length) return <Card><div className="row"><span className="dot online" /><b>Всё работает</b><span className="dim">— все устройства на связи</span></div></Card>;
  return <Card title="Требуют внимания"><div className="list">{problems.map(d => <div className="li" key={d.id} style={{ cursor: 'pointer' }} onClick={() => openDevice(d)}>
    <KindIcon kind={d.kind} size={34} /><div className="grow"><div style={{ fontWeight: 600 }}>{d.name}</div>
      <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{d.state.error || (d.state.metrics || []).filter(m => m.level).map(m => `${m.label}: ${m.value}`).join(', ') || STATUS_TEXT[d.state.status]}</div></div>
    <StatusBadge status={d.state.status} /></div>)}</div></Card>;
}

function DevicesWidget() {
  const { data, openDevice } = useApp();
  return <Card title={`Устройства · ${data.devices.length}`}><div className="list">{data.devices.map(d => <div className="li" key={d.id} style={{ cursor: 'pointer' }} onClick={() => openDevice(d)}>
    <KindIcon kind={d.kind} size={30} /><div className="grow" style={{ minWidth: 0 }}><div className="ellipsis" style={{ fontWeight: 600, fontSize: 14 }}>{d.name}</div>
      <div className="dim ellipsis" style={{ fontSize: 12 }}>{deviceLine(d)}</div></div>
    <span className={'dot ' + ((d.state || {}).status || 'unknown')} /></div>)}</div></Card>;
}

function EventsWidget() {
  const { data, setTab } = useApp();
  return <Card title="События" right={<Btn size="sm" onClick={() => setTab('events')}>Все</Btn>}>
    <EventsList events={data.events.slice(0, 8)} bare /></Card>;
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

function ShortcutsWidget() {
  const { data, admin, setTab } = useApp();
  if (!admin) return null;
  const secs = SET_SECTIONS.filter(x => !x.need || data[x.need]);
  return <Card title="Настройки"><div className="shortcuts">{secs.map(x => <button key={x.id} type="button" className="shortcut"
    onClick={() => { lsSet('rl_set_sec', x.id); setTab('settings'); }}>
    {x.id === 'frank' ? <AppIcon app="frank" size={30} radius={8} /> : x.id === 'about' ? <AppIcon size={30} radius={8} />
      : <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>}
    <span className="ellipsis">{x.label}</span></button>)}</div></Card>;
}

function NoteWidget({ w, edit, onOpts }) {
  const text = (w.opts || {}).text || '';
  return <Card title={w.title || 'Заметка'}>
    {edit ? <textarea className="input" rows={4} defaultValue={text} placeholder="Что угодно: пароль от гостевого Wi-Fi, телефон провайдера, что купить…"
      onBlur={e => e.target.value !== text && onOpts({ text: e.target.value })} style={{ width: '100%', resize: 'vertical' }} />
      : <div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.5 }}>{text || <span className="dim3">Пусто — включите «Редактирование», чтобы написать.</span>}</div>}
  </Card>;
}

function ViewWidget({ which }) {
  const { setTab } = useApp();
  return <div className="wg-view">
    <div className="wg-view-head"><b>{which === 'map' ? 'Карта сети' : 'План'}</b><Btn size="sm" onClick={() => setTab(which)}>Открыть</Btn></div>
    <div className="wg-view-body">{which === 'map' ? <MapView /> : <PlanView />}</div>
  </div>;
}

/* the catalogue — iOS-style sizes: S = a square tile (1 of 4 columns; 1 of 2 on a phone — two in a row),
   M = half the width (whole width on a phone), L = the whole width. sizes: which ones a widget allows.
   tile(data) → the square form: a big value and a line; go → where a tap on the tile leads (else the whole widget opens). */
const avgUptime = d => { const k = (d.uptime || []).filter(u => u.pct != null); return k.length ? k.reduce((a, u) => a + u.pct, 0) / k.length : null; };
const ALL = ['S', 'M', 'L'];
const WIDGETS = {
  rack: { title: 'Шкафы и места', icon: 'rack', color: '#5e5ce6', size: 'M', sizes: ['M'], once: true, desc: 'Серверный шкаф, щитки и комнаты с оборудованием',
    render: () => <RackView /> },
  stats: { title: 'Сводка', icon: 'pulse', color: '#0a84ff', size: 'M', sizes: ALL, once: true, desc: 'Устройства в сети, проблемы, клиенты, PoE', render: () => <StatsWidget />,
    tile: d => ({ v: `${d.devices.filter(x => (x.state || {}).status === 'online').length}/${d.devices.length}`, s: 'устройств в сети' }) },
  problems: { title: 'Требуют внимания', icon: 'alert', color: '#ff9f0a', size: 'M', sizes: ALL, list: true, once: true, desc: 'Что сейчас не в сети или с предупреждением', render: () => <ProblemsWidget />,
    tile: d => { const n = d.devices.filter(x => ['offline', 'warning'].includes((x.state || {}).status)).length; const t = probTone(d);
      return { v: n || '', s: t === 'red' ? `${n} ${ruPlural(n, 'проблема', 'проблемы', 'проблем')} — нет связи` : t === 'yellow' ? `${n} — требует внимания` : 'всё работает', tone: t }; } },
  state: { title: 'Состояние сети', icon: 'shield', color: '#30d158', size: 'M', sizes: ALL, once: true, desc: 'Здоровье и безопасность сети', render: () => <StateCard />,
    tile: d => ({ v: `${d.health ? d.health.score : '—'} · ${d.security ? d.security.score : '—'}`, s: 'здоровье · защита', bad: d.security && d.security.counts.bad }) },
  internet: { title: 'Интернет', icon: 'globe', color: '#64d2ff', size: 'M', sizes: ALL, once: true, desc: 'Скорость интернета по расписанию', render: () => <InternetCard />,
    tile: d => { const l = ((d.inet || {}).items || []).filter(x => x.source === 'racklive' && x.down != null).slice(-1)[0];
      return { v: l ? Math.round(l.down) + '↓' : '—', s: l ? `${Math.round(l.up)}↑ Мбит/с` : 'замеров нет' }; } },
  uptime: { title: 'Доступность', icon: 'pulse', color: '#34c759', size: 'M', sizes: ALL, once: true, desc: 'Кто пропадал за 30 дней', render: () => <UptimeCard />,
    tile: d => { const a = avgUptime(d); return { v: a == null ? '—' : pctText(a), s: 'за 30 дней' }; } },
  newdev: { title: 'Новые в сети', icon: 'plus', color: '#bf5af2', size: 'M', sizes: ALL, once: true, desc: 'Незнакомые устройства за неделю', render: () => <NewDevicesCard />,
    tile: d => { const n = (d.newDevices || []).filter(x => !x.trusted).length; return { v: n, s: n ? 'незнакомых' : 'все свои', bad: n > 0 }; } },
  map: { title: 'Карта сети', icon: 'map', color: '#0a84ff', size: 'L', sizes: ['S', 'L'], h: 520, once: true, desc: 'Живая карта: двигается и приближается; квадратом — кнопка',
    render: () => <ViewWidget which="map" />, tile: () => ({ v: '', s: 'открыть карту' }), go: ctx => ctx.setTab('map') },
  plan: { title: 'План', icon: 'plan', color: '#ff9f0a', size: 'L', sizes: ['S', 'L'], h: 460, once: true, desc: 'Дома, этажи и покрытие Wi-Fi; квадратом — кнопка',
    render: () => <ViewWidget which="plan" />, tile: d => ({ v: ((d.plan || {}).buildings || []).length || '', s: 'открыть план' }), go: ctx => ctx.setTab('plan') },
  devices: { title: 'Устройства', icon: 'list', color: '#8e8e93', size: 'M', sizes: ALL, list: true, once: true, desc: 'Все устройства со статусом', render: () => <DevicesWidget />,
    tile: d => ({ v: d.devices.length, s: 'устройств' }), go: ctx => ctx.setTab('devices') },
  events: { title: 'События', icon: 'bell', color: '#ff375f', size: 'M', sizes: ALL, list: true, once: true, desc: 'Последние сбои, восстановления, действия', render: () => <EventsWidget />,
    tile: d => { const e = (d.events || [])[0]; return { v: (d.events || []).length, s: e ? 'открыть журнал' : 'событий нет' }; }, go: ctx => ctx.setTab('events') },
  speed: { title: 'Тест скорости', icon: 'gauge', color: '#30d158', size: 'S', sizes: ALL, once: true, desc: 'Последний замер и кнопка «Начать»', render: () => <SpeedWidget />,
    tile: d => { const l = (d.speedtests || []).filter(t => t.kind !== 'iperf').slice(-1)[0]; return { v: l ? mbpsText(l.down) + '↓' : '—', s: 'нажмите — тест' }; },
    go: ctx => ctx.openSpeed() },
  frank: { title: 'Frank', icon: 'eye', color: '#636366', size: 'M', sizes: ALL, once: true, desc: 'Задать вопрос помощнику прямо с главной', render: () => <FrankWidget />,
    tile: () => ({ v: '', s: 'спросить Frank' }), go: ctx => ctx.askAi('') },
  shortcuts: { title: 'Настройки', icon: 'settings', color: '#8e8e93', size: 'M', sizes: ALL, once: true, desc: 'Быстрый переход в разделы настроек', render: () => <ShortcutsWidget />,
    tile: () => ({ v: '', s: 'открыть' }), go: ctx => ctx.setTab('settings') },
  note: { title: 'Заметка', icon: 'edit', color: '#ffd60a', size: 'S', sizes: ALL, list: true, desc: 'Свой текст: телефоны, пароль от гостевой сети…',
    render: (w, edit, onOpts) => <NoteWidget w={w} edit={edit} onOpts={onOpts} />, tile: (d, w) => ({ v: '', s: ((w.opts || {}).text || 'пусто').split('\n')[0] }) },
};
const DASH_DEFAULT = ['rack', 'stats', 'problems', 'state', 'internet', 'uptime'].map(type => ({ id: type, type, size: WIDGETS[type].size }));
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
  const ctx = useApp(); const { data, admin, edit } = ctx; const toast = useToast();
  const saved = ((data.dashboard || {}).widgets || []).filter(w => WIDGETS[w.type]);
  const norm = l => l.map(w => ({ ...w, size: sizeOf(w) }));
  const [list, setList] = useState(norm(saved.length ? saved : DASH_DEFAULT));
  const [drag, setDrag] = useState(null);
  const [adding, setAdding] = useState(false);
  const [arrange, setArrange] = useState(() => new URLSearchParams(location.search).get('arrange') === '1');
  const [full, setFull] = useState(null);
  const gridRef = useRef(null); const els = useRef({}); const rects = useRef({}); const flip = useRef(false);
  const follow = useRef(null);                       // while moving: re-pin the lifted widget under the finger after each re-layout
  const [cols, colW] = useCols(gridRef);
  const savedKey = JSON.stringify(saved);
  useEffect(() => { if (!drag && saved.length) setList(norm(saved)); }, [savedKey]);
  useEffect(() => { if (!edit) setArrange(false); }, [edit]);
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
    {edit && admin ? <div className="dash-bar">
      <Switch on={arrange} onChange={setArrange} /><div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>Расстановка виджетов</b>
        <div className="dim" style={{ fontSize: 12.5 }}>{arrange ? 'Долгое нажатие — поднять и перенести (мышью — сразу). Кнопка в углу виджета — размер: квадрат, половина, во всю ширину.' : 'Включите, чтобы двигать, менять размер, добавлять и убирать виджеты.'}</div></div>
      {arrange ? <><Btn size="sm" onClick={() => { flip.current = true; save(DASH_DEFAULT); settle(); }}>Как было</Btn><Btn size="sm" kind="primary" icon="plus" onClick={() => setAdding(true)}>Виджет</Btn></> : null}
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
      <div className="wg-full">{WIDGETS[full.type].render(full, edit && admin, () => {})}</div>
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
  useEffect(() => {
    const el = inner.current; if (!el) return;
    const ro = new ResizeObserver(() => setHIn(el.offsetHeight)); ro.observe(el); return () => ro.disconnect();
  }, [size]);
  const hh = size === 'S' && colW ? colW : hIn;          // a square is as tall as a column is wide — no need to measure
  const rows = Math.max(1, Math.ceil((hh + DASH_GAP + (arranging ? 24 : 0)) / DASH_ROW));
  const span = spanOf(size, cols);
  const name = w.title || d.title;
  let body;
  if (size === 'S') {
    const t = d.tile ? d.tile(data, w) : { v: '', s: '' };
    const art = TILE_ART[w.type] ? TILE_ART[w.type](data, w) : null;
    const showV = t.v !== '' && t.v != null && !(art && TILE_NO_VALUE.has(w.type));
    body = <button type="button" className={'wg-tile t-' + w.type} onClick={arranging ? undefined : onTap}>
      <span className="wg-tile-top"><span className="wg-tile-ic" style={{ background: d.color }}><Icon name={d.icon} size={14} color="#fff" stroke={2.2} /></span>
        <span className="wg-tile-name ellipsis">{name}</span></span>
      <span className="wg-tile-art">{art}</span>
      {showV ? <span className="wg-tile-v" style={{ color: t.bad ? 'var(--orange)' : undefined }}>{t.v}</span> : null}
      <span className="wg-tile-s ellipsis">{t.s}</span>
    </button>;
  } else {
    const content = d.render(w, edit && !arranging, onOpts);
    if (content == null && !arranging) return null;
    body = content == null ? <div className="dim3" style={{ fontSize: 12.5, padding: 6 }}>Пока нет данных для «{name}»</div> : content;
  }
  const view = size === 'L' && d.h;          // map / plan: a fixed height, the content fills it
  const tone = size === 'S' && d.tile ? (d.tile(data, w) || {}).tone : null;
  return <div className={'wg size-' + size + (tone ? ' tone-' + tone : '') + (view ? ' view' : '') + (d.list ? ' wg-list' : '') + (lifted ? ' lifted' : '') + (arranging ? ' arranging' : '')}
    data-wid={w.id} ref={elRef} style={{ gridColumn: `span ${span}`, gridRow: `span ${rows}`, '--tc': d.color }}>
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

function MiniTopo({ data }) {        // a flat hub-and-spoke: the router in the middle, devices around, coloured by status
  const nodes = ((data.topology || {}).nodes || []).filter(n => n.deviceId && n.kind !== 'router').slice(0, 6);
  const router = ((data.topology || {}).nodes || []).find(n => n.kind === 'router' && n.deviceId);
  const pts = nodes.map((n, i) => { const a = -Math.PI / 2 + i * 2 * Math.PI / Math.max(1, nodes.length); return [50 + 36 * Math.cos(a), 50 + 36 * Math.sin(a), n]; });
  return <svg viewBox="0 0 100 100" className="mini-svg">
    <circle cx="50" cy="50" r="36" fill="none" stroke="var(--fill2)" strokeWidth="2" strokeDasharray="3 5" />
    {pts.map(([x, y, n]) => <line key={'l' + n.id} x1="50" y1="50" x2={x} y2={y} stroke={ST_COLOR(n.status)} strokeWidth="4" strokeLinecap="round" opacity=".55" />)}
    {pts.map(([x, y, n]) => <circle key={n.id} cx={x} cy={y} r="9" fill={ST_COLOR(n.status)} />)}
    <circle cx="50" cy="50" r="15" fill="#0a84ff" /><circle cx="50" cy="50" r="15" fill="none" stroke={router ? ST_COLOR(router.status) : '#fff'} strokeWidth="3" opacity=".9" />
    <circle cx="50" cy="50" r="6" fill="none" stroke="#fff" strokeWidth="3" /><circle cx="50" cy="50" r="2" fill="#fff" />
  </svg>;
}

function MiniPlan({ data }) {         // flat rooms (like the Home app) with a Wi-Fi glow
  const tests = (data.speedtests || []).filter(t => t.where).length;
  return <svg viewBox="0 0 100 100" className="mini-svg">
    <defs><radialGradient id="mpw" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#30d158" stopOpacity=".75" /><stop offset="1" stopColor="#30d158" stopOpacity="0" /></radialGradient></defs>
    <rect x="8" y="10" width="50" height="44" rx="10" fill="#ff9f0a" opacity=".85" />
    <rect x="62" y="10" width="30" height="44" rx="10" fill="#ff9f0a" opacity=".5" />
    <rect x="8" y="58" width="34" height="32" rx="10" fill="#ff9f0a" opacity=".38" />
    <rect x="46" y="58" width="46" height="32" rx="10" fill="#ff9f0a" opacity=".65" />
    <circle cx="44" cy="52" r={tests ? 26 : 20} fill="url(#mpw)" />
    <circle cx="44" cy="52" r="6" fill="#fff" /><circle cx="44" cy="52" r="3" fill="#30d158" />
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
  newdev: d => { const fresh = (d.newDevices || []).filter(x => !x.trusted);
    return <div className="mini-faces">{fresh.slice(0, 4).map((x, i) => <span key={i} style={{ background: ['#bf5af2', '#0a84ff', '#ff9f0a', '#30d158'][i] }}>
      <Icon name={x.random ? 'phone' : 'other'} size={16} color="#fff" /></span>)}{fresh.length > 4 ? <span className="more">+{fresh.length - 4}</span> : null}
      {!fresh.length ? <span style={{ background: 'var(--green)' }}><Icon name="check" size={18} color="#fff" stroke={3} /></span> : null}</div>; },
  map: d => <MiniTopo data={d} />,
  plan: d => <MiniPlan data={d} />,
  devices: d => <MiniKinds devices={d.devices} />,
  events: d => <div className="mini-events">{(d.events || []).slice(0, 3).map((e, i) => <div key={i}><i style={{ background: e.level === 'info' ? 'var(--accent)' : ST_COLOR(e.level) }} />
    <span className="ellipsis">{e.name}: {e.text}</span></div>)}</div>,
  frank: () => <div className="mini-frank"><FrankEye size={120} round={0} /></div>,
  shortcuts: d => <div className="mini-grid4">{SET_SECTIONS.filter(x => !x.need || d[x.need]).slice(0, 4).map(x =>
    <span key={x.id} style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>)}</div>,
  note: (d, w) => <div className="mini-note">{((w.opts || {}).text || 'Пустая заметка').split('\n').slice(0, 4).map((l, i) => <div key={i} className="ellipsis">{l || ' '}</div>)}</div>,
};
const probTone = d => { const st = d.devices.map(x => (x.state || {}).status);
  return st.includes('offline') ? 'red' : st.includes('warning') ? 'yellow' : 'green'; };
const TILE_NO_VALUE = new Set(['stats', 'problems', 'state', 'map', 'plan', 'events', 'frank', 'shortcuts', 'note']);   // the picture already says it
