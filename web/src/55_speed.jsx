/* Speed test: browser ⇄ Rack Live (Wi-Fi coverage), results history, iperf3 results from devices */
const SPEED = { secs: 8, warm: 1.5, streams: 4, chunk: 25 << 20, upBlob: 8 };
const speedHeaders = () => { const t = ssGet('rl_tok'); return t ? { 'X-RL-Session': t } : {}; };
const SPEED_LEVELS = [[200, '#30d158', 'Отлично'], [50, '#ffd60a', 'Хорошо'], [15, '#ff9f0a', 'Средне'], [0, '#ff453a', 'Плохо']];
const speedLevel = mbps => SPEED_LEVELS.find(l => (mbps || 0) >= l[0]) || SPEED_LEVELS[3];
const mbpsText = v => v == null ? '—' : v >= 100 ? String(Math.round(v)) : v.toFixed(1);

async function measurePing(n = 12) {
  const times = [];
  for (let i = 0; i < n; i++) {
    const t = performance.now();
    const r = await fetch('/api/speedtest/ping?r=' + Math.random(), { cache: 'no-store', headers: speedHeaders() });
    if (!r.ok) throw new Error(r.status === 401 ? 'нужен вход' : 'сервер не ответил');
    await r.text(); times.push(performance.now() - t);
  }
  const s = times.slice(2).sort((a, b) => a - b);               // the first requests also open the connection
  const jit = times.slice(2).reduce((a, v, i, arr) => i ? a + Math.abs(v - arr[i - 1]) : 0, 0) / Math.max(1, times.length - 3);
  return { ping: Math.round(s[Math.floor(s.length / 2)] * 10) / 10, jitter: Math.round(jit * 10) / 10 };
}

/* Bytes are counted continuously; speed = bytes after the warm-up / time after the warm-up (TCP slow start excluded). */
function runPhase(kind, onTick) {
  return new Promise((resolve, reject) => {
    let bytes = 0, stop = false, base = null, failed = null;
    const t0 = performance.now(), ctrl = new AbortController(), xhrs = [];
    const speed = () => { const t = (performance.now() - t0) / 1000;
      if (t < SPEED.warm || !base) return bytes * 8 / Math.max(.2, t) / 1e6;
      return (bytes - base.b) * 8 / Math.max(.2, t - base.t) / 1e6; };
    const down = async () => {
      while (!stop) {
        const r = await fetch(`/api/speedtest/down?bytes=${SPEED.chunk}&r=${Math.random()}`, { cache: 'no-store', headers: speedHeaders(), signal: ctrl.signal });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'ошибка ' + r.status);
        const rd = r.body.getReader();
        for (;;) { const { done, value } = await rd.read(); if (done) break; bytes += value.length; if (stop) { rd.cancel().catch(() => {}); break; } }
      }
    };
    let blob = null;
    if (kind === 'up') { const mb = new Uint8Array(1 << 20); for (let i = 0; i < mb.length; i += 65536) crypto.getRandomValues(mb.subarray(i, i + 65536));
      blob = new Blob(Array(SPEED.upBlob).fill(mb)); }
    const up = () => new Promise(res => {
      if (stop) return res();
      const x = new XMLHttpRequest(); xhrs.push(x); let last = 0;
      x.upload.onprogress = e => { bytes += e.loaded - last; last = e.loaded; };
      x.onload = () => { if (x.status >= 400) failed = failed || (x.status === 429 ? 'сейчас идёт другой тест' : 'ошибка ' + x.status); res(); };
      x.onerror = x.onabort = () => res();
      x.open('POST', '/api/speedtest/up?r=' + Math.random());
      Object.entries(speedHeaders()).forEach(([k, v]) => x.setRequestHeader(k, v));
      x.send(blob);
    }).then(() => !stop && !failed && up());
    const finish = () => { if (stop) return; stop = true; clearInterval(timer); ctrl.abort(); xhrs.forEach(x => { try { x.abort(); } catch (e) { } });
      failed ? reject(new Error(failed)) : resolve(Math.round(speed() * 10) / 10); };
    const timer = setInterval(() => {
      const t = (performance.now() - t0) / 1000;
      if (t >= SPEED.warm && !base) base = { b: bytes, t };
      onTick(speed(), Math.min(1, t / SPEED.secs));
      if (t >= SPEED.secs || failed) finish();
    }, 150);
    for (let i = 0; i < SPEED.streams; i++) (kind === 'down' ? down() : up()).catch(e => { if (!stop && e.name !== 'AbortError') { failed = e.message; finish(); } });
  });
}

function Gauge({ value, phase, progress }) {
  const max = [100, 500, 1000, 2500, 10000].find(m => (value || 0) <= m) || 10000;      // the scale grows with the speed
  const f = Math.min(1, (value || 0) / max), a = Math.PI * (1 - f);
  const R = 80, cx = 100, cy = 92, x = cx + R * Math.cos(a), y = cy - R * Math.sin(a);
  const col = phase ? speedLevel(value)[1] : 'var(--text3)';
  return <div className="gauge">
    <svg viewBox="0 0 200 110">
      <path d={`M${cx - R},${cy} A${R},${R} 0 0 1 ${cx + R},${cy}`} fill="none" stroke="var(--fill2)" strokeWidth="12" strokeLinecap="round" />
      {f > 0 ? <path d={`M${cx - R},${cy} A${R},${R} 0 0 1 ${x.toFixed(1)},${y.toFixed(1)}`} fill="none" stroke={col} strokeWidth="12" strokeLinecap="round" /> : null}
      <text x={cx - R} y={cy + 16} textAnchor="middle" className="gauge-tick">0</text>
      <text x={cx + R} y={cy + 16} textAnchor="middle" className="gauge-tick">{max}</text>
    </svg>
    <div className="gauge-val"><b>{phase ? mbpsText(value) : '—'}</b><span>Мбит/с</span></div>
    <div className="gauge-phase">{phase || ' '}</div>
    {progress != null ? <div className="gauge-bar"><i style={{ width: progress * 100 + '%' }} /></div> : null}
  </div>;
}

/* what the result means, in plain words */
function speedVerdict(r, who) {
  const lines = [], [, , grade] = speedLevel(r.down);
  lines.push({ Отлично: 'Отлично — хватит на всё: 4K, большие файлы, несколько устройств сразу.', Хорошо: 'Хорошо — видео в 4K, звонки и игры без проблем.',
    Средне: 'Средне — видео в HD и звонки работают, большие файлы качаются медленно.', Плохо: 'Плохо — здесь слабое покрытие. Поставьте точку доступа ближе или добавьте ещё одну.' }[grade]);
  if (who && who.wifi) {
    if (who.rssi && who.rssi <= -72) lines.push(`Сигнал слабый (${who.rssi} дБм): между вами и точкой «${who.apName}» стены или большое расстояние.`);
    if ((who.band || '').startsWith('2.4') && r.down < 100) lines.push('Телефон подключён на 2.4 ГГц — он дальнобойнее, но медленнее. Ближе к точке телефон обычно сам переходит на 5 ГГц.');
    if (who.rate && r.down) lines.push(`Скорость соединения с точкой — ${who.rate} Мбит/с, реально получилось ${Math.round(r.down / who.rate * 100)}%. Для Wi-Fi нормально 40–70%.`);
  }
  if (who && who.wired && r.down < 300) lines.push(`Подключение по кабелю, а скорость ниже ожидаемой: проверьте кабель на порту ${who.port} «${who.switch}».`);
  if (r.ping > 30) lines.push(`Задержка ${r.ping} мс — высокая для домашней сети (норма до 10 мс по кабелю и до 20–30 мс по Wi-Fi). Возможны помехи или перегруженный канал.`);
  return lines;
}

function WhoLine({ who }) {
  if (!who) return <div className="dim3" style={{ fontSize: 13 }}>Определяю подключение…</div>;
  if (who.wifi) return <div className="who"><Icon name="wifi" size={16} /><span>Wi-Fi · <b>{who.apName}</b>{who.band ? ' · ' + who.band : ''}
    {who.rssi ? <span style={{ color: who.rssi > -65 ? 'var(--green)' : who.rssi > -75 ? 'var(--orange)' : 'var(--red)' }}> · {who.rssi} дБм</span> : null}
    {who.rate ? ` · соединение ${who.rate} Мбит/с` : ''}</span></div>;
  if (who.wired) return <div className="who"><Icon name="cable" size={16} /><span>Кабель · <b>{who.switch}</b>, порт {who.port}{who.linkSpeed ? ' · ' + fmt.speed(who.linkSpeed) : ''}</span></div>;
  if (who.proxy) return <div className="who"><Icon name="globe" size={16} /><span>Открыто через доменное имя — запросы идут через роутер, поэтому точку доступа
    и сигнал Rack Live не видит. Для точного замера Wi-Fi дома откройте тест по домашнему адресу.</span></div>;
  if (who.nat) return <div className="who warn"><Icon name="alert" size={16} /><span>Сервер видит не ваш адрес, а адрес Docker ({who.ip}) — точку доступа определить нельзя.
    Запустите контейнер с <code>network_mode: host</code> (см. README).</span></div>;
  return <div className="who"><Icon name="other" size={16} /><span>Устройство {who.ip} не найдено в списках роутера — точку доступа определить не удалось.</span></div>;
}

/* the test itself — shared by the modal inside Rack Live and the separate /speed app */
function useSpeedTest(autoRun) {
  const { data, admin, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [who, setWho] = useState(null);
  const [run, setRun] = useState(null);                   // {phase, value, progress}
  const [res, setRes] = useState(null);
  const [saved, setSaved] = useState(null);
  const [note, setNote] = useState('');
  const alive = useRef(true);
  useEffect(() => { api('/api/speedtest/who').then(setWho).catch(() => setWho({})); return () => { alive.current = false; }; }, []);
  const start = async () => {
    setRes(null); setSaved(null);
    try {
      setRun({ phase: 'Задержка', value: 0, progress: null });
      const p = await measurePing();
      setRun({ phase: 'Загрузка ↓', value: 0, progress: 0 });
      const down = await runPhase('down', (v, pr) => alive.current && setRun({ phase: 'Загрузка ↓', value: v, progress: pr }));
      setRun({ phase: 'Отдача ↑', value: 0, progress: 0 });
      const up = await runPhase('up', (v, pr) => alive.current && setRun({ phase: 'Отдача ↑', value: v, progress: pr }));
      const r = { down, up, ...p };
      if (!alive.current) return;
      setRun(null); setRes(r);
      if (admin) { const s = await api('/api/speedtest', { method: 'POST', body: { ...r, note } }); setSaved(s.test); refresh(); }
    } catch (e) { setRun(null); toast('Тест не удался: ' + e.message, true); }
  };
  const saveNote = async () => { if (!saved) return; try { await api('/api/speedtest/' + saved.id, { method: 'PUT', body: { note } }); toast('Сохранено'); refresh(); } catch (e) { toast(e.message, true); } };
  const del = async t => { if (!(await confirm('Удалить этот замер?', { danger: true, ok: 'Удалить' }))) return;
    try { await api('/api/speedtest/' + t.id, { method: 'DELETE' }); refresh(); } catch (e) { toast(e.message, true); } };
  useEffect(() => { if (autoRun) start(); }, []);          // ?speedtest=run — e.g. a home-screen shortcut
  return { data, admin, who, run, res, saved, note, setNote, start, saveNote, del,
    hasPlan: ((data.plan || {}).buildings || []).length > 0, list: (data.speedtests || []).slice().reverse() };
}

function SpeedTestModal({ onClose, autoRun }) {
  const { pinSpeedTest } = useApp();
  const s = useSpeedTest(autoRun); const { data, admin, who, run, res, saved, note, setNote, start, saveNote, del, hasPlan, list } = s;
  return <Modal title="Тест скорости" onClose={onClose} icon={<Icon name="gauge" size={20} color="var(--accent)" />}>
    <Hint id="speed-intro">Тест меряет скорость между этим устройством и сервером Rack Live — то есть вашу домашнюю сеть и Wi-Fi, а не интернет.
      Пройдитесь по дому и сделайте тест в каждой комнате — на «Плане» получится карта покрытия Wi-Fi.</Hint>
    <WhoLine who={who} />
    <Gauge value={run ? run.value : res ? res.down : 0} phase={run ? run.phase : res ? 'Загрузка ↓' : ''} progress={run ? run.progress : null} />
    {res ? <>
      <div className="stats">
        <Stat k="Загрузка ↓" v={mbpsText(res.down)} unit="Мбит/с" /><Stat k="Отдача ↑" v={mbpsText(res.up)} unit="Мбит/с" />
        <Stat k="Задержка" v={res.ping} unit="мс" /><Stat k="Джиттер" v={res.jitter} unit="мс" /></div>
      <div className="speed-verdict" style={{ borderColor: speedLevel(res.down)[1] }}>{speedVerdict(res, who).map((l, i) => <div key={i}>{l}</div>)}</div>
      {saved ? <div className="row wrap" style={{ gap: 8 }}>
        <input className="input grow" style={{ minWidth: 160 }} value={note} placeholder="Где вы? Например: кухня, у окна" onChange={e => setNote(e.target.value)} onBlur={saveNote} />
        {hasPlan ? <Btn icon="pin" kind="primary" onClick={() => { onClose(); pinSpeedTest(saved.id); }}>Отметить на плане</Btn> : null}
      </div> : !admin ? <div className="dim3" style={{ fontSize: 12.5 }}>Результат не сохранён: сохранять замеры может только администратор (войдите).</div> : null}
    </> : null}
    <Btn kind="primary" busy={!!run} onClick={start} style={{ padding: 13 }}>{run ? 'Идёт тест…' : res ? 'Повторить тест' : 'Начать тест'}</Btn>
    {list.length ? <div>
      <div className="card-title" style={{ margin: '6px 0 4px' }}>Замеры · {list.length}</div>
      <div className="list">{list.slice(0, 30).map(t => <SpeedRow key={t.id} t={t} now={data.now} onDelete={admin ? () => del(t) : null} />)}</div>
    </div> : null}
  </Modal>;
}

/* /speed — the speed test as a separate app: same floating chrome as Frank (glass circles on top, a capsule at the bottom) */
function SpeedApp() {
  const s = useSpeedTest(new URLSearchParams(location.search).get('run') === '1');
  const { data, admin, who, run, res, saved, note, setNote, start, saveNote, del, list } = s;
  const [view, setView] = useState('test');                 // 'test' | 'list'
  const last = list.find(t => t.kind !== 'iperf');
  const col = run ? speedLevel(run.value)[1] : res ? speedLevel(res.down)[1] : 'var(--text3)';
  const sub = !who ? 'определяю подключение…' : who.proxy ? 'через доменное имя' : who.wifi ? `Wi-Fi · ${who.apName}${who.band ? ' · ' + who.band : ''}` : who.wired ? `кабель · порт ${who.port}` : 'домашняя сеть';
  return <div className="frank-app"><div className="ai-panel standalone speed-app">
    <div className="fr-blur" />
    <div className="fr-top">
      <div className="fr-side"><button type="button" className="fr-circle" title={view === 'list' ? 'К тесту' : 'Все замеры'} onClick={() => setView(view === 'list' ? 'test' : 'list')}>
        <Icon name={view === 'list' ? 'chevronLeft' : 'menu'} size={22} stroke={2} /></button></div>
      <div className="fr-title"><b>{view === 'list' ? 'Замеры' : 'Тест скорости'}</b><span>{view === 'list' ? `всего ${list.length}` : sub}</span></div>
      <div className="fr-side r"><div className={'fr-circle sp-ind' + (run ? ' on' : '')} style={{ color: col }} title={run ? run.phase : 'Тест скорости'}><Icon name="gauge" size={22} stroke={2.2} /></div></div>
    </div>
    <div className="ai-list sp-body">
      <InstallBanner app="speed" name="Тест скорости" />
      {view === 'list' ? (list.length ? <div className="list sp-glass">{list.slice(0, 100).map(t => <SpeedRow key={t.id} t={t} now={data.now} onDelete={admin ? () => del(t) : null} />)}</div>
        : <div className="ai-empty"><div className="dim">Замеров пока нет — сделайте первый тест.</div></div>) : <>
        <div className="sp-who"><WhoLine who={who} /></div>
        <Gauge value={run ? run.value : res ? res.down : 0} phase={run ? run.phase : res ? 'Загрузка ↓' : ''} progress={run ? run.progress : null} />
        {res ? <>
          <div className="stats">
            <Stat k="Загрузка ↓" v={mbpsText(res.down)} unit="Мбит/с" /><Stat k="Отдача ↑" v={mbpsText(res.up)} unit="Мбит/с" />
            <Stat k="Задержка" v={res.ping} unit="мс" /><Stat k="Джиттер" v={res.jitter} unit="мс" /></div>
          <div className="speed-verdict" style={{ borderColor: speedLevel(res.down)[1] }}>{speedVerdict(res, who).map((l, i) => <div key={i}>{l}</div>)}</div>
          {saved ? <input className="input sp-note" value={note} placeholder="Где вы? Например: кухня, у окна" onChange={e => setNote(e.target.value)} onBlur={saveNote} />
            : !admin ? <div className="dim3" style={{ fontSize: 12.5, textAlign: 'center' }}>Результат не сохранён: сохранять замеры может только администратор.</div> : null}
        </> : !run ? <div className="dim" style={{ fontSize: 14, lineHeight: 1.5, textAlign: 'center', maxWidth: 380, margin: '0 auto' }}>
          Тест меряет скорость между телефоном и Rack Live — то есть вашу домашнюю сеть и Wi-Fi, а не интернет. Сделайте тест в каждой комнате — получится карта покрытия.
          {last ? <div className="dim3" style={{ marginTop: 10, fontSize: 13 }}>Прошлый замер: ↓ {mbpsText(last.down)} · ↑ {mbpsText(last.up)} Мбит/с · {fmt.ago(last.t, data.now)}</div> : null}</div> : null}
      </>}
    </div>
    {view === 'test' ? <div className="fr-dock sp-dock">
      <button type="button" className={'sp-start' + (run ? ' busy' : '')} onClick={() => !run && start()} disabled={!!run}>
        {run ? <><span className="spin-dot" />{run.phase}{run.progress != null ? ' · ' + Math.round(run.progress * 100) + '%' : ''}</> : res ? 'Повторить тест' : 'Начать тест'}</button>
    </div> : null}
  </div></div>;
}

function SpeedRow({ t, now, onDelete }) {
  const c = t.client || {}, iperf = t.kind === 'iperf';
  const col = speedLevel(t.down)[1];
  const place = iperf ? `iperf3 · ${t.deviceName || t.host}` : [t.note, c.wifi ? `${c.apName}${c.band ? ', ' + c.band : ''}${c.rssi ? ', ' + c.rssi + ' дБм' : ''}` : c.wired ? `кабель, порт ${c.port}` : ''].filter(Boolean).join(' · ');
  return <div className="li">
    <div className="speed-dot" style={{ background: col }}><Icon name={iperf ? 'server' : c.wifi ? 'wifi' : 'gauge'} size={14} color="#fff" /></div>
    <div className="grow" style={{ minWidth: 0 }}>
      <div className="ellipsis" style={{ fontSize: 14, fontWeight: 600 }}>{iperf ? `от устр. ${mbpsText(t.down)} · к устр. ${mbpsText(t.up)} Мбит/с` : `↓ ${mbpsText(t.down)} · ↑ ${mbpsText(t.up)} Мбит/с`}
        {t.ping != null ? <span className="dim" style={{ fontWeight: 400 }}> · {t.ping} мс</span> : null}</div>
      <div className="dim ellipsis" style={{ fontSize: 12 }}>{fmt.time(t.t)}{c.name ? ' · ' + c.name : ''}{place ? ' · ' + place : ''}{t.where ? ' · 📍' : ''}</div>
    </div>
    {onDelete ? <Btn size="sm" icon="trash" onClick={onDelete} title="Удалить" /> : null}
  </div>;
}

/* device card: iperf3 action + its last results */
function SpeedCard({ device, action }) {
  const { data, admin } = useApp(); const runAction = useAction();
  const mine = (data.speedtests || []).filter(t => t.device === device.id).slice(-5).reverse();
  if (!admin && !mine.length) return null;
  return <Card title="Скорость сети до устройства" right={admin ? <Btn size="sm" icon="gauge" onClick={() => runAction(device, action)}>Измерить</Btn> : null}>
    {mine.length ? <div className="list">{mine.map(t => <SpeedRow key={t.id} t={t} now={data.now} />)}</div>
      : <div className="dim3" style={{ fontSize: 13, lineHeight: 1.45 }}>iperf3 измерит реальную скорость между Rack Live и этим устройством в обе стороны.
        Это покажет узкое место в проводной сети или канал до удалённого сервера. На устройстве нужен пакет iperf3.</div>}
  </Card>;
}
