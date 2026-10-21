/* «Карточки» — a separate installable app (/cards): point the camera at a QR sticker (the same RL:<id> code the port scanner reads) and the device's card opens:
   a pretty, read-only page built from the rack (what it is, where it stands, what it is plugged into, live state, ports, notes). Things that are not in the rack get a
   hand-made card (Settings → «Мои карточки»), which is stored on the server (cfg.cards). Every device, rack unit and hand-made card has its own printable sticker. */
const CARD_KINDS = [['router', 'Роутер'], ['switch', 'Коммутатор'], ['server', 'Сервер'], ['nas', 'NAS'], ['ap', 'Точка доступа'], ['camera', 'Камера'], ['nvr', 'Видеорегистратор'], ['ups', 'ИБП'],
  ['pc', 'Компьютер'], ['laptop', 'Ноутбук'], ['phone', 'Телефон'], ['tv', 'Телевизор'], ['printer', 'Принтер'], ['iot', 'Умное устройство'], ['modem', 'Модем'], ['web', 'Сервис'], ['other', 'Другое']];
const UNIT_KIND = { patch: 'patch', cross: 'cross', pdu: 'pdu', modem: 'modem', router: 'router', switch: 'switch', server: 'server', nas: 'nas', nvr: 'nvr', ups: 'ups' };
const UNIT_TEXT = { patch: 'Патч-панель', cross: 'Оптический кросс', pdu: 'Блок розеток', shelf: 'Полка', organizer: 'Кабельный органайзер', modem: 'Модем / ONT', ups: 'ИБП', server: 'Сервер', nas: 'NAS', router: 'Роутер', switch: 'Коммутатор', nvr: 'Видеорегистратор', other: 'Оборудование' };
const CARD_RECENT = 'rl_cards_recent';

/* the colour of a card follows the brand: Keenetic blue, MikroTik and UPS red, OpenWrt yellow with green; the rest by the kind of device. → [main, second] */
function cardColors(e) {
  const d = e.device || {}, st = d.state || {}, txt = [e.name, e.model, e.card && e.card.vendor, e.card && e.card.model, (st.summary || {}).model].join(' ');
  if (/openwrt/i.test(d.driver || '') || /openwrt/i.test(txt)) return ['#ffd60a', '#30d158'];
  if (/mikrotik|routerboard|микротик/i.test(txt)) return ['#ff453a', '#ff453a'];
  if (d.driver === 'keenetic' || /keenetic|netcraze|кинетик/i.test(txt)) return ['#0a84ff', '#0a84ff'];
  if (e.kind === 'ups' || st.ups) return ['#ff453a', '#ff453a'];
  const k = kindColor(e.kind); return [k, k];
}

/* what a QR sticker says: «RL:<id>» (the same code the port scanner reads); a link with ?card=<id> or ?d=<id> works too */
function parseCardCode(s) { const m = String(s || '').match(/^RL:([\w-]{3,40})$/) || String(s || '').match(/[?&](?:card|d)=([\w-]{3,40})/); return m ? m[1] : null; }
function qrSvgOf(text) {
  if (typeof qrcode !== 'function') return '';
  try { if (qrcode.stringToBytesFuncs && qrcode.stringToBytesFuncs['UTF-8']) qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8'];
    const q = qrcode(0, 'M'); q.addData(text); q.make(); return q.createSvgTag({ cellSize: 6, margin: 0, scalable: true }); } catch (e) { return ''; }
}

function placeText(rack, unit) {
  if (!rack) return '';
  const k = rack.kind || 'rack';
  if (k === 'box') return 'Щиток «' + rack.name + '»';
  if (k === 'place') return 'Комната «' + rack.name + '»';
  return rack.name + (unit && unit.uStart ? ' · U' + unit.uStart + (unit.uSize > 1 ? '–' + (unit.uStart + unit.uSize - 1) : '') : '');
}
/* every thing that can have a card: devices (from the rack and outside it), rack units without a device (patch panel, ONT…), hand-made cards */
function cardList(data) {
  const out = [], placed = {};
  (data.racks || []).forEach(r => (r.units || []).forEach(u => [u.deviceId, ...(u.deviceIds || [])].filter(Boolean).forEach(id => { if (!placed[id]) placed[id] = { rack: r, unit: u }; })));
  (data.devices || []).forEach(d => {
    const drv = (data.drivers || []).find(x => x.id === d.driver), pl = placed[d.id], s = (d.state && d.state.summary) || {};
    out.push({ id: d.id, src: 'device', name: d.name, kind: d.kind || (drv && drv.kind) || 'other', device: d, drv, rack: pl && pl.rack, unit: pl && pl.unit,
      place: pl ? placeText(pl.rack, pl.unit) : '', group: pl ? pl.rack.name : d.location === 'remote' ? 'Удалённые' : 'Вне шкафа', sub: s.ip || '', model: s.model || '', status: d.state && d.state.status });
  });
  (data.racks || []).forEach(r => (r.units || []).forEach(u => {
    if (u.deviceId || (u.deviceIds || []).length || u.type === 'blank') return;
    out.push({ id: u.id, src: 'unit', name: u.name || UNIT_TEXT[u.type] || 'Оборудование', kind: UNIT_KIND[u.type] || 'other', unit: u, rack: r, place: placeText(r, u), group: r.name, sub: UNIT_TEXT[u.type] || '', model: '' });
  }));
  (data.cards || []).filter(c => !c.of).forEach(c => out.push({ id: c.id, src: 'manual', name: c.name, kind: c.kind || 'other', card: c, place: c.location || '', group: 'Мои карточки', sub: [c.vendor, c.model].filter(Boolean).join(' ') || c.ip || '', model: c.model || '' }));
  return out;
}
/* what the device is plugged into (from the network map): neighbour, its port and ours, speed */
function cardLinks(data, e) {
  const me = e.src === 'device' ? 'd:' + e.id : e.src === 'unit' ? 'u:' + e.id : null;
  if (!me || !data.topology) return [];
  const nodes = {}; (data.topology.nodes || []).forEach(n => { nodes[n.id] = n; });
  return (data.topology.edges || []).filter(x => x.source === me || x.target === me).map(x => {
    const out = x.source === me, o = nodes[out ? x.target : x.source];
    return { id: x.id, name: o ? o.label : '', kind: (o && o.kind) || 'other', mine: out ? x.sourcePort : x.targetPort, theirs: out ? x.targetPort : x.sourcePort, speed: x.speed, type: x.kind, label: x.label,
      open: o && /^[du]:/.test(o.id) ? o.id.slice(2) : null };
  }).filter(l => l.name && l.type !== 'extra');
}

/* ───────── scanner ───────── */
function CardScanner({ onFound, onClose, items, paused }) {
  const vref = useRef(null); const [err, setErr] = useState(''); const stop = useRef(false); stop.current = !!paused;
  useEffect(() => {
    let dead = false, stream = null, timer = null; const work = document.createElement('canvas'), ctx = work.getContext('2d', { willReadFrequently: true });
    const fake = new URLSearchParams(location.search).get('fakescan');          // for tests: «found» a code without a camera
    if (fake) { timer = setTimeout(() => onFound(fake), 400); return () => clearTimeout(timer); }
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { setErr('https'); return; }
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
        if (dead) { stream.getTracks().forEach(t => t.stop()); return; }
        const v = vref.current; v.srcObject = stream; await v.play();
        const tick = () => {
          if (dead) return;
          if (stop.current) { timer = setTimeout(tick, 200); return; }
          if (v.videoWidth && window.jsQR) {
            const k = Math.min(1, 800 / v.videoWidth); work.width = Math.round(v.videoWidth * k); work.height = Math.round(v.videoHeight * k);
            ctx.drawImage(v, 0, 0, work.width, work.height);
            const im = ctx.getImageData(0, 0, work.width, work.height), code = window.jsQR(im.data, work.width, work.height, { inversionAttempts: 'dontInvert' });
            const id = code && parseCardCode(code.data);
            if (id) { try { navigator.vibrate && navigator.vibrate(30); } catch (e) { } onFound(id); }
          }
          timer = setTimeout(tick, 110);
        };
        tick();
      } catch (e) { setErr(e && e.name === 'NotAllowedError' ? 'denied' : 'fail'); }
    })();
    return () => { dead = true; clearTimeout(timer); if (stream) stream.getTracks().forEach(t => t.stop()); };
  }, []);
  return <div className="cd-cam">
    <video ref={vref} playsInline muted autoPlay />
    {onClose ? <div className="cd-cam-top"><button type="button" className="cd-pill" onClick={onClose}><Icon name="x" size={16} />Закрыть</button></div> : null}
    {!err ? <><div className="cd-frame"><i /><i /><i /><i /></div><div className="cd-cam-hint">Наведите камеру на QR-наклейку устройства</div></>
      : <div className="cd-cam-err"><b>{err === 'https' ? 'Камера работает только по https' : err === 'denied' ? 'Нет доступа к камере' : 'Не удалось включить камеру'}</b>
        <p>{err === 'https' ? 'Откройте приложение по защищённому адресу (https://…), а не по домашнему http://IP.'
          : err === 'denied' ? 'Разрешите камеру для этого сайта: на iPhone — Настройки → Safari → Камера, либо «аА» в адресной строке → Настройки веб-сайта.' : 'Проверьте, что камеру не занимает другое приложение.'}</p>
        <button type="button" className="cd-pill solid" onClick={() => location.reload()}>Повторить</button></div>}
  </div>;
}

/* ───────── the card ───────── */
function Fact({ k, v, mono, copy }) {
  const toast = useToast();
  if (v == null || v === '') return null;
  return <div className={'cd-fact' + (copy ? ' tap' : '')} onClick={copy ? () => toast(copyText(String(v)) ? 'Скопировано' : 'Не получилось скопировать', false) : undefined}>
    <div className="k">{k}</div><div className={'v' + (mono ? ' mono' : '')}>{v}</div></div>;
}

/* a ring gauge: value 0–100, big text inside */
function Ring({ value, color, big, small, size = 124 }) {
  const r = 52, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value || 0));
  return <div className="cd-ring" style={{ width: size, height: size }}>
    <svg viewBox="0 0 120 120"><circle cx="60" cy="60" r={r} fill="none" stroke="var(--fill2)" strokeWidth="11" />
      <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round" strokeDasharray={`${c * v / 100} ${c}`} transform="rotate(-90 60 60)" style={{ transition: 'stroke-dasharray .6s' }} /></svg>
    <div className="cd-ring-in"><b>{big}</b><small>{small}</small></div></div>;
}
/* one-series area chart of a day: min / max / now and the time axis */
function DayChart({ points, field, unit, color = 'var(--accent)' }) {
  const [hover, setHover] = useState(null);
  const pts = (points || []).filter(p => typeof p[field] === 'number');
  if (pts.length < 3) return <div className="dim3" style={{ fontSize: 13, padding: '14px 0', textAlign: 'center' }}>График появится через несколько минут: данные копятся с каждым опросом.</div>;
  const W = 600, H = 150, t0 = pts[0].t, t1 = pts[pts.length - 1].t, vals = pts.map(p => p[field]);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max((hi - lo) * 0.15, hi * 0.05, 1), a = Math.max(0, lo - pad), b = hi + pad;
  const X = t => 4 + (t - t0) / Math.max(1, t1 - t0) * (W - 8), Y = v => H - 16 - (v - a) / (b - a) * (H - 30);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p[field]).toFixed(1)}`).join(' ');
  const hp = hover != null ? pts[hover] : pts[pts.length - 1];
  const onMove = e => { const r = e.currentTarget.getBoundingClientRect(), t = t0 + (e.clientX - r.left) / r.width * (t1 - t0); let best = 0; pts.forEach((p, i) => { if (Math.abs(p.t - t) < Math.abs(pts[best].t - t)) best = i; }); setHover(best); };
  const hm = t => new Date(t * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  return <div>
    <div className="row between" style={{ fontSize: 13, marginBottom: 4 }}><span><b style={{ fontSize: 20 }}>{Math.round(hp[field])}</b> <span className="dim">{unit}</span></span>
      <span className="dim3">{hover != null ? hm(hp.t) : `за сутки: от ${Math.round(lo)} до ${Math.round(hi)} ${unit}`}</span></div>
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      {[.25, .5, .75].map(f => <line key={f} x1={0} x2={W} y1={Y(a + (b - a) * f)} y2={Y(a + (b - a) * f)} stroke="var(--line)" />)}
      <path d={line + ` L${X(t1)},${H - 16} L${X(t0)},${H - 16} Z`} fill={color} opacity=".16" /><path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      {hover != null ? <line x1={X(hp.t)} x2={X(hp.t)} y1={0} y2={H - 16} stroke="var(--text3)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" /> : null}</svg>
    <div className="row between dim3 mono" style={{ fontSize: 10.5, marginTop: 2 }}>{[0, .25, .5, .75, 1].map((f, i) => <span key={i}>{hm(t0 + (t1 - t0) * f)}</span>)}</div></div>;
}

/* an UPS: how long it will last, load, charge, consumption through the day, what is plugged in */
function CardUps({ device }) {
  const ups = device.state.ups, hist = useHistory(device.id, true);
  const chargeCol = ups.charge == null ? 'var(--text3)' : ups.charge > 50 ? 'var(--green)' : ups.charge > 20 ? 'var(--orange)' : 'var(--red)';
  const pct = ups.loadPct != null ? ups.loadPct : (ups.nominalW ? Math.round(ups.loadW * 100 / ups.nominalW) : null);
  const loadCol = pct == null ? 'var(--accent)' : pct > 85 ? 'var(--red)' : pct > 70 ? 'var(--orange)' : 'var(--tc, var(--accent))';
  const conn = [...(ups.connected || [])].sort((a, b) => b.w - a.w), top = Math.max(1, ...conn.map(c => c.w));
  return <>
    <Card className="cd-ups">
      <div className="cd-ups-time"><div className="big">{ups.runtimeEstimated ? '≈ ' : ''}{ups.runtimeMin != null ? fmtMin(ups.runtimeMin) : '—'}</div>
        <div className="dim">хватит при отключении света{ups.onBattery ? ' · сейчас работает от батареи' : ''}</div></div>
      <div className="cd-rings">
        <Ring value={pct == null ? 0 : pct} color={loadCol} big={ups.loadW != null ? ups.loadW + ' Вт' : '—'} small={pct != null ? `нагрузка ${pct}%` : 'нагрузка'} />
        <Ring value={ups.charge == null ? 0 : ups.charge} color={chargeCol} big={ups.charge != null ? Math.round(ups.charge) + '%' : '—'} small={ups.charging ? 'заряжается' : 'заряд'} />
      </div>
      {ups.lowBattery || ups.replace ? <div className="badge offline" style={{ marginTop: 10 }}>{ups.replace ? 'Пора менять аккумулятор' : 'Батарея почти разряжена'}</div> : null}
      {ups.estimated ? <div className="dim3" style={{ fontSize: 12, marginTop: 10 }}>Время и нагрузка рассчитаны по подключённым устройствам, кабеля данных нет.</div> : null}
    </Card>
    <Card title="Потребление за сутки"><DayChart points={hist} field="w" unit="Вт" color="var(--orange)" /></Card>
    {ups.runtimeMin ? <Card title="Как будет садиться батарея"><UpsCurve min={ups.runtimeMin} charge={ups.charge} /></Card> : null}
    {conn.length ? <Card title={`Что подключено · ${conn.length}`}><div className="list">{conn.map((c, i) => <div className="li" key={c.id || c.unit || i} style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
      <div className="row" style={{ gap: 10 }}><KindIcon kind={c.kind || 'other'} size={30} round={8} /><div className="grow ellipsis" style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</div><b className="mono" style={{ fontSize: 13 }}>{c.w} Вт</b></div>
      <div className="bar"><i style={{ width: Math.max(4, c.w * 100 / top) + '%', background: 'var(--orange)' }} /></div></div>)}</div></Card> : null}
  </>;
}

/* ───────── «Витрина»: the device stands up in 3D (no photo) or its own photo with invisible port buttons ───────── */
const clampN = (v, a, b) => Math.max(a, Math.min(b, v));
function cardEntry(data, e) { const cards = data.cards || []; return e.src === 'manual' ? (e.card || {}) : (cards.find(c => c.of === e.id) || {}); }
function photoUrl(id, entry) { return entry && entry.photo ? `/api/cards/photo/${encodeURIComponent(id)}?v=${entry.photo}` : null; }

/* ───────── 3D model of a device (rackd/models.py format): the user's own, or one made from the device's ports ───────── */
function faceItem(it, fw, fh, i, x) {
  const { px, C, byN, ledOf, sel, onPick, dead } = x, pct = (v, of) => (v / of * 100) + '%';
    const pos = { left: pct(it.x, fw), top: pct(it.y, fh) };
    if (it.type === 'port') {
      const st = { ...pos, width: pct(it.w, fw), height: pct(it.h, fh), '--led': it.n ? ledOf(it.n) : 'transparent', background: C.port };
      return it.n && !dead && byN(it.n) ? <button key={i} type="button" className={'m3-port ' + it.kind + (sel === it.n ? ' sel' : '')} style={{ ...st, '--i': it.n }} aria-label={'Порт ' + it.n} onClick={() => onPick(it.n)} />
        : <span key={i} className={'m3-port dead ' + it.kind} style={st} />;
    }
    if (it.type === 'led') { const p = it.link ? byN(it.link) : null, on = it.link ? !!(p && p.link) : it.on !== false, c = it.color || C.led || 'var(--s3-led)';
      return <i key={i} className={'m3-led' + (on ? ' on' : '')} style={{ left: pct(it.x - it.r, fw), top: pct(it.y - it.r, fh), width: px(it.r * 2), height: px(it.r * 2), '--c': c }} />; }
    if (it.type === 'text') return <span key={i} className="m3-text" style={{ ...pos, fontSize: px(it.size), fontWeight: it.weight, color: it.color || C.text, transform: it.align === 'center' ? 'translateX(-50%)' : it.align === 'right' ? 'translateX(-100%)' : null }}>{it.text}</span>;
    if (it.type === 'rect') return <span key={i} className="m3-rect" style={{ ...pos, width: pct(it.w, fw), height: pct(it.h, fh), background: it.color, borderRadius: px(it.radius || 0) }} />;
    if (it.type === 'circle') return <span key={i} className="m3-circle" style={{ left: pct(it.x - it.r, fw), top: pct(it.y - it.r, fh), width: px(it.r * 2), height: px(it.r * 2), background: it.color }} />;
    if (it.type === 'vent') { const step = (it.dir === 'v' ? px(it.w) : px(it.h)) / (it.slots * 2);
      return <span key={i} className="m3-vent" style={{ ...pos, width: pct(it.w, fw), height: pct(it.h, fh), backgroundImage: `repeating-linear-gradient(${it.dir === 'v' ? 90 : 180}deg, var(--m3-slot) 0 ${step}px, transparent ${step}px ${step * 2}px)` }} />; }
    return null;
  }

const RJ = { w: 15, h: 13, gap: 3 };                     // a real RJ45 socket, mm: every port is this size
function autoModel(ports, name) {
  const rj = ports.filter(p => p.kind !== 'sfp'), sfp = ports.filter(p => p.kind === 'sfp');
  const rows = rj.length > 8 ? 2 : 1, cols = Math.max(1, Math.ceil(rj.length / rows)), scol = Math.ceil(sfp.length / 2);
  const pad = 10, brandW = 64, portsW = cols * RJ.w + (cols - 1) * RJ.gap, sfpW = scol ? scol * RJ.w + (scol - 1) * RJ.gap : 0;
  const blockH = n => n * RJ.h + (n - 1) * RJ.gap;
  const h = Math.max(blockH(rows), sfp.length > 1 ? blockH(2) : 0) + 18;
  const w = pad + brandW + portsW + (scol ? 12 + sfpW : 0) + 14 + pad;
  const d = Math.round(rj.length + sfp.length <= 10 ? w * .72 : Math.max(w * .5, 120));
  const words = String(name || '').trim().split(/\s+/).filter(Boolean), items = [];
  items.push({ type: 'text', x: pad, y: h / 2 - 5, text: (words[0] || 'Switch').slice(0, 16), size: 4.4, weight: 700 });
  if (words.length > 1) items.push({ type: 'text', x: pad, y: h / 2 + 1, text: words.slice(1).join(' ').slice(0, 24), size: 3, weight: 400 });
  const x0 = pad + brandW, y0 = (h - blockH(rows)) / 2;
  rj.forEach((p, k) => { const c = rows === 2 ? Math.floor(k / 2) : k, r = rows === 2 ? k % 2 : 0;
    items.push({ type: 'port', n: p.n, kind: 'rj45', x: x0 + c * (RJ.w + RJ.gap), y: y0 + r * (RJ.h + RJ.gap), w: RJ.w, h: RJ.h }); });
  const xs = x0 + portsW + 12, ys = (h - blockH(Math.min(2, sfp.length))) / 2;
  sfp.forEach((p, k) => items.push({ type: 'port', n: p.n, kind: 'sfp', x: xs + Math.floor(k / 2) * (RJ.w + RJ.gap), y: ys + (k % 2) * (RJ.h + RJ.gap), w: RJ.w, h: RJ.h }));
  [-5.5, 0, 5.5].forEach(dy => items.push({ type: 'led', x: w - pad - 3, y: h / 2 + dy, r: 1.2, on: true }));
  return { format: 'racklive-model', version: 1, name: name || 'Устройство', size: { w, h, d },
    faces: { front: { items }, top: { items: [{ type: 'vent', x: w * .12, y: d * .18, w: w * .76, h: d * .42, slots: 16 }] } }, parts: [], view: { rx: -13, ry: -20 } };
}

const FACE_DEF = {                                       // face → [width, height, transform] from the box size in px
  front: (w, h, d) => [w, h, `translateZ(${d / 2}px)`], back: (w, h, d) => [w, h, `rotateY(180deg) translateZ(${d / 2}px)`],
  top: (w, h, d) => [w, d, `rotateX(90deg) translateZ(${h / 2}px)`], bottom: (w, h, d) => [w, d, `rotateX(-90deg) translateZ(${h / 2}px)`],
  left: (w, h, d) => [d, h, `rotateY(-90deg) translateZ(${w / 2}px)`], right: (w, h, d) => [d, h, `rotateY(90deg) translateZ(${w / 2}px)`] };
const FACE_COLOR = { front: 'front', back: 'back', top: 'top', bottom: 'back', left: 'side', right: 'side' };
const FACE_VAR = { front: 'var(--s3-front)', back: 'var(--s3-back)', top: 'var(--s3-top)', bottom: 'var(--s3-back)', left: 'var(--s3-side)', right: 'var(--s3-side)' };

/* the smart zoom («Test»): the rectangle the user drew in the port editor, or else the block of ports with a margin → {face, x, y, w, h} mm */
function zoomZone(model, manual, marks, zoom) {
  if (zoom && zoom.face) return zoom;
  const box = (face, list) => { if (!list.length) return null; const x0 = Math.min(...list.map(p => p.x)), y0 = Math.min(...list.map(p => p.y)), x1 = Math.max(...list.map(p => p.x + p.w)), y1 = Math.max(...list.map(p => p.y + p.h)), m = 6;
    return { face, x: x0 - m, y: y0 - m, w: x1 - x0 + 2 * m, h: y1 - y0 + 2 * m }; };
  if (manual && (marks || []).length) { const f = marks[0].face; return box(f, marks.filter(m => m.face === f).map(m => ({ x: m.x - m.w / 2, y: m.y - m.h / 2, w: m.w, h: m.h }))); }
  for (const f of ['front', 'back']) { const it = ((model.faces[f] || {}).items || []).filter(i => i.type === 'port'); if (it.length) return box(f, it); }
  return null;
}
function Model3D({ model, ports, sel, onPick, view, onSaveView, manual, marks, zoom }) {
  const stage = useRef(null), drag = useRef(null);
  const [sw, setSw] = useState(320); const [risen, setRisen] = useState(false);
  const rest = view || model.view || { rx: -13, ry: -20 };
  const [rot, setRot] = useState(rest);
  const [zoomed, setZoomedS] = useState(false); const setZoomed = v => { zoomedRef.current = v; setZoomedS(v); }; const zz = isTestLook() ? zoomZone(model, manual, marks, zoom) : null;
  useEffect(() => { if (zz && new URLSearchParams(location.search).get('zoomports') === '1') { setZoomed(true); setRisen(true); setRot({ rx: 0, ry: zz.face === 'back' ? 180 : 0 }); } }, []);      // for tests
  const zoomedRef = useRef(false);
  useEffect(() => { if (!zoomedRef.current) setRot(rest); }, [rest.rx, rest.ry, model.name, model.size.w, model.size.h]);
  useEffect(() => { const tm = setTimeout(() => setRisen(true), 1800); return () => clearTimeout(tm); }, []);      // the rise is over even if animationend never came
  useLayoutEffect(() => { const f = () => stage.current && setSw(stage.current.clientWidth); f(); const ro = new ResizeObserver(f); ro.observe(stage.current); return () => ro.disconnect(); }, []);
  const S = model.size;
  // the whole thing, antennas and stands too, must fit at any angle: the turning width is the diagonal of the footprint
  const ext = (model.parts || []).reduce((a, p) => ({ lo: Math.min(a.lo, p.y - p.h / 2), hi: Math.max(a.hi, p.y + p.h / 2), sx: Math.max(a.sx, Math.abs(p.x) + p.w / 2), sz: Math.max(a.sz, Math.abs(p.z) + p.d / 2) }),
    { lo: -S.h / 2, hi: S.h / 2, sx: S.w / 2, sz: S.d / 2 });
  const k = Math.min((sw - 40) / (2 * Math.hypot(ext.sx, ext.sz)), 190 / (ext.hi - ext.lo + ext.sz * .5), 2.4), px = v => v * k;
  const stageH = clampN((ext.hi - ext.lo) * k + ext.sz * k * .6 + 70, 170, 330), lift = (ext.lo + ext.hi) / 2 * k;
  const W = px(S.w), H = px(S.h), D = px(S.d);
  // zoomed: face-on, scaled so the zone fills the stage, its centre moved to the middle
  const Z = zoomed && zz ? Math.min((sw - 36) / (zz.w * k), 300 / (zz.h * k), 9) : 1;
  const zx = zz ? (zz.x + zz.w / 2 - S.w / 2) * (zz.face === 'back' ? -1 : 1) * k : 0, zy = zz ? (zz.y + zz.h / 2 - S.h / 2) * k : 0;
  const zH = zoomed && zz ? clampN(zz.h * k * Z + 90, 170, 400) : null;
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const C = (model.color && (model.color[dark ? 'dark' : 'light'] || model.color.light || model.color.dark)) || {};
  const byN = n => (ports || []).find(p => p.n === n);
  const ledOf = n => { const p = byN(n); return !p || !p.link ? 'transparent' : p.speed >= 1000 ? (C.led || 'var(--s3-led)') : 'var(--s3-led2)'; };
  const down = ev => { if (zoomed || ev.target.closest('.m3-port, .m3-tools')) return; drag.current = { x: ev.clientX, y: ev.clientY, rx: rot.rx, ry: rot.ry }; try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch (x) { } setRisen(true); };
  const move = ev => { const g = drag.current; if (!g) return; let ry = g.ry + (ev.clientX - g.x) * .5; ry = ((ry + 540) % 360) - 180;
    setRot({ rx: clampN(g.rx - (ev.clientY - g.y) * .35, -80, 80), ry, drag: true }); };
  const up = () => { if (!drag.current) return; drag.current = null; setRot(r => ({ rx: Math.round(r.rx), ry: Math.round(r.ry) })); };
  const moved = Math.abs(rot.rx - rest.rx) > 1 || Math.abs(rot.ry - rest.ry) > 1;
  const pct = (v, of) => (v / of * 100) + '%';
  const ctx = { px, C, byN, ledOf, sel, onPick, dead: !!manual };
  const item = (it, fw, fh, i) => faceItem(it, fw, fh, i, ctx);
  const face = (f, w, h, d, items, color, cls = '') => { const [fw, fh, tf] = FACE_DEF[f](w, h, d);
    return <div key={f} className={'m3-f m3-' + f + ' ' + cls} style={{ width: fw, height: fh, transform: `translate(-50%, -50%) ${tf}`, background: color }}>{items}</div>; };
  const fill = f => (model.faces[f] && model.faces[f].color) || C[FACE_COLOR[f]] || C.body || FACE_VAR[f];
  return <div className={'s3-stage m3-stage' + (zoomed ? ' zoomed' : '')} ref={stage} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} style={{ height: zH || stageH, perspective: zoomed ? Math.round(1000 * Z * 6) + 'px' : undefined, perspectiveOrigin: zoomed ? '50% 50%' : undefined }}>
    <div className="s3-floor" style={{ top: `calc(50% - ${zoomed ? 0 : lift}px)` }}><div className="s3-zoom" style={{ transform: zoomed ? `scale(${Z}) translate(${-zx}px, ${-zy}px)` : 'none' }}><div className="s3-float">
      <div className="s3-shadow" style={{ '--w': W + 'px', '--h': H + 'px', '--d': D + 'px' }} />
      <div className={'s3-box' + (risen ? '' : ' rise') + (rot.drag ? ' drag' : '')} onAnimationEnd={ev => { if (ev.animationName === 's3rise') setRisen(true); }}
        style={{ '--rx': rot.rx + 'deg', '--ry': rot.ry + 'deg' }}>
        {Object.keys(FACE_DEF).map(f => { const fw = FACE_DEF[f](S.w, S.h, S.d); return face(f, W, H, D, [...((model.faces[f] || {}).items || []).map((it, i) => item(it, fw[0], fw[1], i)),
          ...(manual ? (marks || []).filter(m => m.face === f).map((m, i) => <button key={'mk' + i} type="button" className={'m3-mark' + (sel === m.n ? ' sel' : '')} aria-label={'Порт ' + m.n} onClick={() => onPick(m.n)}
            style={{ left: pct(m.x - m.w / 2, fw[0]), top: pct(m.y - m.h / 2, fw[1]), width: pct(m.w, fw[0]), height: pct(m.h, fw[1]), '--led': ledOf(m.n), '--i': m.n }} />) : [])], fill(f)); })}
        {(model.parts || []).map((p, i) => <div key={'p' + i} className="m3-part" style={{ transform: `translate3d(${px(p.x)}px, ${px(p.y)}px, ${px(p.z)}px) rotateX(${p.rx || 0}deg) rotateZ(${p.rz || 0}deg)` }}>
          {Object.keys(FACE_DEF).map(f => face(f, px(p.w), px(p.h), px(p.d), null, p.color || C.body || FACE_VAR[f]))}</div>)}
      </div>
    </div></div></div>
    <div className="m3-tools">
      {zz ? <button type="button" className={'m3-tool zoom' + (zoomed ? ' pri' : '')} title={zoomed ? 'Отдалить' : 'Приблизить порты'} onClick={() => { const on = !zoomed; setZoomed(on); setRisen(true); setRot(on ? { rx: 0, ry: zz.face === 'back' ? 180 : 0 } : rest); }}>
        <Icon name={zoomed ? 'x' : 'search'} size={15} />{zoomed ? 'Отдалить' : 'Порты крупно'}</button> : null}
      {!zoomed && moved ? <button type="button" className="m3-tool" title="Вернуть положение" onClick={() => setRot(rest)}><Icon name="refresh" size={15} /></button> : null}
      {!zoomed && moved && onSaveView ? <button type="button" className="m3-tool pri" onClick={() => onSaveView({ rx: Math.round(rot.rx), ry: Math.round(rot.ry) })}><Icon name="pin" size={14} />Зафиксировать</button> : null}
    </div>
    <div className="s3-hint">{zoomed ? 'Нажмите на порт' : 'Потяните, чтобы повернуть'}</div>
  </div>;
}

/* ───────── «Отмечу сам»: the ports are marked by hand on the faces of a model (its own sockets have no numbers, or they are ignored) ───────── */
/* marks with a finger: the nearest mark within ~1 cm is grabbed (so a new one is not added by mistake next to it);
   on an empty place a new mark follows the finger and is placed where the finger is lifted. spots = [{x, y, r}] in px of the box (null = not on this view). */
function usePlacer(box, opt) {
  const o = useRef(opt); o.current = opt;
  const g = useRef(null); const [lp, setLp] = useState(null); const [ghost, setGhost] = useState(null);
  const at = ev => { const r = box.current.getBoundingClientRect(); return { px: clampN(ev.clientX - r.left, 0, r.width), py: clampN(ev.clientY - r.top, 0, r.height), w: r.width, h: r.height, cx: ev.clientX, cy: ev.clientY }; };
  const down = ev => {
    const p = at(ev); let best = -1, bd = 1e9;
    (o.current.spots || []).forEach((s, i) => { if (!s) return; const d = Math.hypot(s.x - p.px, s.y - p.py), lim = Math.max(30, s.r + 16); if (d < lim && d < bd) { bd = d; best = i; } });
    try { box.current.setPointerCapture(ev.pointerId); } catch (x) { }
    if (best >= 0) { const s = o.current.spots[best]; g.current = { i: best, dx: s.x - p.px, dy: s.y - p.py, sx: ev.clientX, sy: ev.clientY, moved: false }; o.current.onPick(best); }
    else { g.current = { i: -1 }; setGhost(p); }
    setLp(p); ev.preventDefault();
  };
  const move = ev => { const s = g.current; if (!s) return; const p = at(ev); setLp(p);
    if (s.i >= 0) { if (Math.hypot(ev.clientX - s.sx, ev.clientY - s.sy) > 3) s.moved = true; if (s.moved) o.current.onDrag(s.i, { px: clampN(p.px + s.dx, 0, p.w), py: clampN(p.py + s.dy, 0, p.h), w: p.w, h: p.h }); }
    else setGhost(p); };
  const up = ev => { const s = g.current; g.current = null; setLp(null); setGhost(null); if (s && s.i < 0 && ev && ev.clientX != null) o.current.onNew(at(ev)); };
  const cancel = () => { g.current = null; setLp(null); setGhost(null); };
  return { handlers: { onPointerDown: down, onPointerMove: move, onPointerUp: up, onPointerCancel: cancel }, lp, ghost };
}
/* a round magnifier above the finger: what is under it, 2.6× bigger, with a sight in the middle */
function Loupe({ lp, w, h, children }) {
  if (!lp) return null;
  const Z = 2.6, R = 66, top = lp.cy > 210 ? lp.cy - 178 : lp.cy + 48;
  return ReactDOM.createPortal(<div className="lp" style={{ left: clampN(lp.cx - R, 4, window.innerWidth - 2 * R - 4), top }}>
    <div className="lp-in" style={{ width: w, height: h, transform: `translate(${R - lp.px * Z}px, ${R - lp.py * Z}px) scale(${Z})` }}>{children}</div><i className="lp-x" /></div>, document.body);
}

/* «Область приближения»: a rectangle drawn with a finger over the face / photo → {x, y, w, h} in px of the box */
function useZoneDraw(box, onDone) {
  const g = useRef(null); const [draft, setDraft] = useState(null);
  const at = ev => { const r = box.current.getBoundingClientRect(); return { x: clampN(ev.clientX - r.left, 0, r.width), y: clampN(ev.clientY - r.top, 0, r.height), W: r.width, H: r.height }; };
  const rect = (a, b) => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y), W: a.W, H: a.H });
  return { draft, handlers: {
    onPointerDown: ev => { g.current = at(ev); try { box.current.setPointerCapture(ev.pointerId); } catch (x) { } setDraft(rect(g.current, g.current)); ev.preventDefault(); },
    onPointerMove: ev => { if (g.current) setDraft(rect(g.current, at(ev))); },
    onPointerUp: ev => { if (!g.current) return; const r = rect(g.current, at(ev)); g.current = null; setDraft(null); if (r.w > 12 && r.h > 8) onDone(r); },
    onPointerCancel: () => { g.current = null; setDraft(null); } } };
}
/* only in «Test»: the zone the «Порты крупно» button flies to */
function ZoneBar({ zone, zmode, setZmode, onReset }) {
  if (!isTestLook()) return null;
  return <div className="zn-bar"><div className="grow" style={{ minWidth: 0 }}><b>Область приближения</b>
    <small>{zmode ? 'Обведите пальцем прямоугольник вокруг портов' : zone ? 'задана вручную — кнопка «Порты крупно» приблизит её' : 'не задана — приближается весь блок портов'}</small></div>
    <Btn size="sm" kind={zmode ? 'primary' : undefined} icon="search" onClick={() => setZmode(!zmode)}>{zmode ? 'Отмена' : zone ? 'Изменить' : 'Задать'}</Btn>
    {zone && !zmode ? <Btn size="sm" onClick={onReset}>Авто</Btn> : null}</div>;
}
const ZoneBox = ({ r, draft }) => r ? <span className={'zn-box' + (draft ? ' draft' : '')} style={{ left: r.left, top: r.top, width: r.width, height: r.height }}><i>{draft ? '' : 'приближение'}</i></span> : null;

const FACE_NAME = { front: 'Перед', back: 'Зад', top: 'Верх', bottom: 'Низ', left: 'Слева', right: 'Справа' };
function MarkEditor({ item, model, ent, onClose }) {
  const { data } = useApp(); const toast = useToast(); const save = useCardsSave();
  const cards = data.cards || [], ports = item.device ? ((item.device.state || {}).ports || []) : [];
  const [face, setFace] = useState(() => { const v = (ent && ent.view) || model.view || { ry: -20 }; return Math.abs(v.ry) > 90 ? 'back' : 'front'; });
  const [marks, setMarks] = useState(() => (ent && ent.mports) || []);
  const [zone, setZone] = useState(() => (ent && ent.zoom) || null); const [zmode, setZmode] = useState(false);
  const [cur, setCur] = useState(null); const [size, setSize] = useState(15); const [busy, setBusy] = useState(false); const [cw, setCw] = useState(600);
  const box = useRef(null), wrap = useRef(null), drag = useRef(null);
  useLayoutEffect(() => { const f = () => wrap.current && setCw(wrap.current.clientWidth - 24); f(); const ro = new ResizeObserver(f); ro.observe(wrap.current); return () => ro.disconnect(); }, []);
  const S = model.size, [fw, fh] = FACE_DEF[face](S.w, S.h, S.d), k = Math.min(cw / fw, 340 / fh, 6), px = v => v * k;
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const C = (model.color && (model.color[dark ? 'dark' : 'light'] || model.color.light || model.color.dark)) || {};
  const fill = (model.faces[face] && model.faces[face].color) || C[FACE_COLOR[face]] || C.body || FACE_VAR[face];
  const ctx = { px, C, byN: () => null, ledOf: () => 'transparent', sel: null, onPick: () => { }, dead: true };
  const label = n => { const p = ports.find(x => x.n === n); return p ? (p.label || (p.peers && p.peers[0] && p.peers[0].name) || '') : ''; };
  const nextN = () => { const used = new Set(marks.map(m => m.n)); const pool = ports.length ? ports.map(p => p.n) : Array.from({ length: 64 }, (_, i) => i + 1); return pool.find(n => !used.has(n)) || Math.max(0, ...marks.map(m => m.n)) + 1; };
  const r1 = v => Math.round(v * 10) / 10;
  const pl = usePlacer(box, {
    spots: marks.map(x => (x.face === face ? { x: px(x.x), y: px(x.y), r: px(Math.max(x.w, x.h)) / 2 } : null)),
    onPick: i => setCur(i),
    onDrag: (i, p) => setMarks(a => a.map((x, j) => (j === i ? { ...x, x: r1(p.px / k), y: r1(p.py / k) } : x))),
    onNew: p => { setMarks(a => [...a, { face, n: nextN(), x: r1(p.px / k), y: r1(p.py / k), w: size, h: r1(size * 13 / 15) }]); setCur(marks.length); } });
  const resize = v => { setSize(v); setMarks(m => m.map(x => x.face === face ? { ...x, w: v, h: Math.round(v * 13 / 15 * 10) / 10 } : x)); };
  const zd = useZoneDraw(box, r => { setZone({ face, x: r1(r.x / k), y: r1(r.y / k), w: r1(r.w / k), h: r1(r.h / k) }); setZmode(false); });
  const doSave = async () => { setBusy(true); const rec = { ...(ent || { of: item.id, name: item.name, kind: item.kind }), portsMode: 'manual', mports: marks }; if (zone) rec.zoom = zone; else delete rec.zoom;
    const ok = await save(ent ? cards.map(c => c === ent ? rec : c) : [...cards, rec]); setBusy(false); if (ok) { toast('Порты на модели сохранены'); onClose(); } };
  const box2 = (x, i, cls) => <span key={i} className={'pe-spot ' + cls} style={{ left: ((x.x - x.w / 2) / fw * 100) + '%', top: ((x.y - x.h / 2) / fh * 100) + '%', width: (x.w / fw * 100) + '%', height: (x.h / fh * 100) + '%' }}>{x.n ? <span>{x.n}</span> : null}</span>;
  const content = <>{((model.faces[face] || {}).items || []).map((it, i) => faceItem(it, fw, fh, i, ctx))}
    {marks.map((x, i) => (x.face !== face ? null : box2(x, i, cur === i ? 'on' : '')))}
    {pl.ghost ? box2({ x: pl.ghost.px / k, y: pl.ghost.py / k, w: size, h: size * 13 / 15 }, 'g', 'ghost') : null}</>;
  const m = cur != null ? marks[cur] : null;
  return <Modal title={'Порты на модели · ' + item.name} onClose={onClose} wide footer={<><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" busy={busy} onClick={doSave}>Сохранить</Btn></>}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 10 }}>Выберите грань, коснитесь разъёма и ведите палец: над ним появится лупа, метка встанет там, где отпустите. Готовую метку можно взять пальцем рядом с ней и перетащить; касание выбирает её номер.
      В карточке метки станут невидимыми кнопками поверх модели.</div>
    <Seg value={face} onChange={f => { setFace(f); setCur(null); }} options={Object.keys(FACE_DEF).map(f => { const n = marks.filter(x => x.face === f).length; return { value: f, label: FACE_NAME[f] + (n ? ' · ' + n : '') }; })} />
    <div className="m3-flat-stage" ref={wrap}>
      <div ref={box} className={'m3-face-flat m3-stage' + (zmode ? ' zoning' : '')} style={{ width: px(fw), height: px(fh), background: fill }} {...(zmode ? zd.handlers : pl.handlers)}>{content}
        {zone && zone.face === face ? <ZoneBox r={{ left: px(zone.x), top: px(zone.y), width: px(zone.w), height: px(zone.h) }} /> : null}
        {zd.draft ? <ZoneBox draft r={{ left: zd.draft.x, top: zd.draft.y, width: zd.draft.w, height: zd.draft.h }} /> : null}</div>
      <Loupe lp={pl.lp} w={px(fw)} h={px(fh)}><div className="m3-stage" style={{ position: 'relative', width: px(fw), height: px(fh), background: fill }}>{content}</div></Loupe>
    </div>
    <div className="pe-bar">
      <label className="row" style={{ gap: 10, fontSize: 13 }}><span className="dim" style={{ whiteSpace: 'nowrap' }}>Размер меток, мм</span>
        <input type="range" min="4" max="40" step="0.5" value={size} onChange={ev => resize(+ev.target.value)} style={{ flex: 1, accentColor: 'var(--accent)' }} /><b className="mono" style={{ width: 34, textAlign: 'right' }}>{size}</b></label>
      {m ? <div className="pe-sel"><b>Метка</b>
        {ports.length ? <select className="input" value={m.n} onChange={ev => setMarks(a => a.map((x, j) => j === cur ? { ...x, n: +ev.target.value } : x))}>
          {ports.map(p => <option key={p.n} value={p.n}>Порт {p.n}{label(p.n) ? ' · ' + label(p.n) : ''}{marks.some((x, j) => j !== cur && x.n === p.n) ? ' (уже отмечен)' : ''}</option>)}</select>
          : <input className="input" type="number" min="1" max="256" value={m.n} onChange={ev => setMarks(a => a.map((x, j) => j === cur ? { ...x, n: +ev.target.value || 1 } : x))} style={{ width: 90 }} />}
        <Btn size="sm" kind="danger" onClick={() => { setMarks(a => a.filter((_, j) => j !== cur)); setCur(null); }}>Убрать</Btn></div>
        : <div className="dim3" style={{ fontSize: 12.5 }}>Отмечено портов: {marks.length}{ports.length ? ' из ' + ports.length : ''}</div>}
      {marks.length ? <div><Btn size="sm" onClick={() => { setMarks([]); setCur(null); }}>Убрать все метки</Btn></div> : null}
      <ZoneBar zone={zone} zmode={zmode} setZmode={setZmode} onReset={() => setZone(null)} />
    </div>
  </Modal>;
}

/* ───────── Rack Live → «Сканер» → «Вид»: 3D model or photo of a card ───────── */
function ModelPane({ item }) {
  const { data } = useApp(); const toast = useToast(); const confirm = useConfirm(); const save = useCardsSave();
  const cards = data.cards || [], lib = data.models || [];
  const ent = item.src === 'manual' ? cards.find(c => c.id === item.id) : cards.find(c => c.of === item.id);
  const ports = item.device ? ((item.device.state || {}).ports || []) : [];
  const cur = ent && ent.model && lib.find(m => m.id === ent.model) ? ent.model : 'auto';
  const [add, setAdd] = useState(false); const [text, setText] = useState(''); const [check, setCheck] = useState(null); const [busy, setBusy] = useState(false); const [guide, setGuide] = useState(null); const [gfree, setGfree] = useState(false);
  const [marking, setMarking] = useState(false);
  useEffect(() => { if (new URLSearchParams(location.search).get('marks') === '1') setMarking(true); }, []);      // ?marks=1 — opened after the window, so it lies on top
  const manual = !!(ent && ent.portsMode === 'manual');
  const fileRef = useRef(null);
  const saveEntry = patch => { const rec = { ...(ent || { of: item.id, name: item.name, kind: item.kind }), ...patch }; Object.keys(rec).forEach(k => rec[k] == null && delete rec[k]);
    return save(ent ? cards.map(c => c === ent ? rec : c) : [...cards, rec]); };
  const pick = async id => { if (await saveEntry({ model: id === 'auto' ? null : id, view: null })) toast(id === 'auto' ? 'Модель: автоматически' : 'Модель выбрана'); };
  const doCheck = async () => { setBusy(true); try { setCheck(await api('/api/models', { method: 'POST', body: { model: text, dry: true } })); } catch (x) { setCheck({ ok: false, errors: [x.message] }); } finally { setBusy(false); } };
  const doAdd = async () => { setBusy(true); try { const r = await api('/api/models', { method: 'POST', body: { model: text } });
    if (!r.ok) { setCheck(r); return; } await saveEntry({ model: r.id, view: null }); toast('Модель добавлена в библиотеку и выбрана'); setAdd(false); setText(''); setCheck(null); } catch (x) { toast(x.message, true); } finally { setBusy(false); } };
  const del = async m => { if (!(await confirm(`Удалить модель «${m.name}» из библиотеки? Карточки с ней снова станут автоматическими.`, { title: 'Удалить модель', ok: 'Удалить', danger: true }))) return;
    try { await api('/api/models/' + m.id, { method: 'DELETE' }); await save(cards.map(c => c.model === m.id ? (({ model, view, ...r }) => r)(c) : c)); } catch (x) { toast(x.message, true); } };
  const openGuide = async (free = gfree) => { setGfree(free); try { const r = await fetch('/api/models/guide.txt' + (free ? '?free=1' : ''), { credentials: 'same-origin', headers: ssGet('rl_tok') ? { 'X-RL-Session': ssGet('rl_tok') } : {} }); setGuide(await r.text()); } catch (x) { toast(x.message, true); } };
  const preview = cur === 'auto' ? (ports.length ? autoModel(ports, (item.device.state.summary || {}).model || item.name) : null) : lib.find(m => m.id === cur).model;
  const portsOf = m => ((m.faces && Object.values(m.faces)) || []).reduce((a, f) => a + (f.items || []).filter(x => x.type === 'port').length, 0);
  return <div className="col" style={{ gap: 10 }}>
    <div className="m3-preview">{preview ? <Model3D model={preview} ports={ports} sel={null} onPick={() => { }} view={ent && ent.view} manual={cur !== 'auto' && manual} marks={ent && ent.mports} /> : <div className="dim" style={{ padding: 30, textAlign: 'center', fontSize: 13 }}>Без модели карточка показывает значок типа устройства.</div>}</div>
    <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px' }}>Модель</div>
    <button type="button" className={'plug-row' + (cur === 'auto' ? ' on' : '')} onClick={() => pick('auto')}><span className="ico-circle"><Icon name={cur === 'auto' ? 'check' : 'box'} size={16} /></span>
      <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>Автоматически</b><small>{ports.length ? `из портов Rack Live: ${ports.length}, все одного размера` : 'значок типа устройства'}</small></span></button>
    {lib.map(m => <div key={m.id} className={'plug-row' + (cur === m.id ? ' on' : '')} style={{ cursor: 'pointer' }} onClick={() => pick(m.id)}>
      <span className="ico-circle"><Icon name={cur === m.id ? 'check' : 'box'} size={16} /></span>
      <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{m.name}</b><small>{m.model.size.w}×{m.model.size.h}×{m.model.size.d} мм · портов {portsOf(m.model)}</small></span>
      <Btn size="sm" icon="trash" title="Удалить из библиотеки" onClick={ev => { ev.stopPropagation(); del(m); }} /></div>)}
    {cur !== 'auto' ? <>
      <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px', marginTop: 4 }}>Порты</div>
      <Seg value={manual ? 'manual' : 'model'} onChange={v => saveEntry({ portsMode: v === 'manual' ? 'manual' : null })} options={[{ value: 'model', label: 'Из модели' }, { value: 'manual', label: 'Отмечу сам' }]} />
      {manual ? <button type="button" className="plug-row" onClick={() => setMarking(true)}><span className="ico-circle"><Icon name="cursor" size={16} /></span>
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>Отметить порты на модели</b><small>{(ent && ent.mports || []).length ? `отмечено ${ent.mports.length}${ports.length ? ' из ' + ports.length : ''}` : 'ещё не отмечены: нажмите и отметьте разъёмы на гранях'}</small></span><Icon name="chevron" size={14} /></button>
        : <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.45 }}>Номера портов берутся из модели (их проставила нейросеть). Чтобы модель была просто картинкой, а порты вы отметили сами, выберите «Отмечу сам».</div>}
    </> : null}
    {marking && cur !== 'auto' ? <MarkEditor item={item} model={preview} ent={ent} onClose={() => setMarking(false)} /> : null}
    {!add ? <div className="row wrap" style={{ gap: 8 }}><Btn size="sm" kind="primary" icon="plus" onClick={() => setAdd(true)}>Добавить свою модель</Btn><Btn size="sm" icon="sparkle" onClick={() => openGuide(false)}>Инструкция для нейросети</Btn></div>
      : <div className="m3-add">
        <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Отправьте нейросети (ChatGPT, Claude, Gemini) «Инструкцию для нейросети» и фото устройства спереди и сзади. Она пришлёт JSON-модель: вставьте её сюда или загрузите файлом.</div>
        <textarea className="input mono" rows={7} value={text} onChange={ev => { setText(ev.target.value); setCheck(null); }} placeholder='{"format": "racklive-model", "version": 1, …}' />
        <input ref={fileRef} type="file" accept=".json,application/json,text/plain" hidden onChange={async ev => { const f = ev.target.files[0]; if (f) { setText(await f.text()); setCheck(null); } ev.target.value = ''; }} />
        {check && !check.ok ? <div className="cam-warn"><b>Модель не подходит:</b><ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{check.errors.map((e, i) => <li key={i} className="mono" style={{ fontSize: 12 }}>{e}</li>)}</ul>
          <Btn size="sm" icon="copy" style={{ marginTop: 8 }} onClick={() => toast(copyText('Исправь ошибки в модели и пришли её целиком заново:\n' + check.errors.join('\n')) ? 'Ошибки скопированы — отправьте их нейросети' : 'Не получилось скопировать', false)}>Скопировать ошибки для нейросети</Btn></div> : null}
        {check && check.ok ? <div className="m3-preview"><Model3D model={check.model} ports={ports} sel={null} onPick={() => { }} /></div> : null}
        <div className="row wrap" style={{ gap: 8 }}>
          <Btn size="sm" icon="upload" onClick={() => fileRef.current.click()}>Файл .json</Btn>
          <Btn size="sm" busy={busy} disabled={!text.trim()} onClick={doCheck}>Проверить</Btn>
          <Btn size="sm" kind="primary" busy={busy} disabled={!(check && check.ok)} onClick={doAdd}>Сохранить и выбрать</Btn>
          <Btn size="sm" onClick={() => { setAdd(false); setText(''); setCheck(null); }}>Отмена</Btn>
          <Btn size="sm" icon="sparkle" onClick={() => openGuide(false)}>Инструкция</Btn></div>
      </div>}
    {guide ? <Modal title="Инструкция для нейросети" onClose={() => setGuide(null)} wide
      footer={<><Btn onClick={() => setGuide(null)}>Закрыть</Btn><Btn kind="primary" icon="copy" onClick={() => toast(copyText(guide) ? 'Инструкция скопирована — вставьте её в чат нейросети вместе с фото' : 'Не получилось скопировать — выделите текст вручную', false)}>Скопировать</Btn></>}>
      <Seg value={gfree ? 'free' : 'model'} onChange={v => openGuide(v === 'free')} options={[{ value: 'model', label: 'Порты из модели' }, { value: 'free', label: 'Порты отмечу сам' }]} />
      <div className="dim" style={{ fontSize: 13, margin: '8px 0' }}>{gfree ? 'Нейросеть нарисует модель без номеров портов — можно что-то необычное. Порты потом отметите сами: «Вид» → «Порты» → «Отмечу сам».'
        : 'Нейросеть сама проставит номера портов.'} Скопируйте и отправьте ей вместе с фото устройства (спереди и сзади) и его названием.</div>
      <pre className="m3-guide">{guide}</pre></Modal> : null}
  </div>;
}

function AppearanceModal({ item, onClose }) {
  const [tab, setTab] = useState(() => new URLSearchParams(location.search).get('look') === 'photo' ? 'photo' : 'model');
  return <Modal title={'Вид · ' + item.name} onClose={onClose} wide>
    <Seg value={tab} onChange={setTab} options={[{ value: 'model', label: '3D-модель' }, { value: 'photo', label: 'Фото' }]} />
    <div style={{ marginTop: 12 }}>{tab === 'model' ? <ModelPane item={item} /> : <PhotoEditor item={item} onClose={onClose} pane />}</div>
    <div className="dim3" style={{ fontSize: 12, marginTop: 12 }}>Если загружено фото, карточка показывает его; иначе — выбранную 3D-модель.</div>
  </Modal>;
}

function PhotoPorts({ url, spots, sel, onPick, zoom }) {
  const [zoomed, setZoomed] = useState(() => new URLSearchParams(location.search).get('zoomports') === '1');
  const zz = !isTestLook() ? null : zoom || (spots.length ? (() => { const x0 = Math.min(...spots.map(s => s.x - s.w / 2)), y0 = Math.min(...spots.map(s => s.y - s.h / 2)), x1 = Math.max(...spots.map(s => s.x + s.w / 2)), y1 = Math.max(...spots.map(s => s.y + s.h / 2)), m = .03;
    return { x: Math.max(0, x0 - m), y: Math.max(0, y0 - m), w: Math.min(1, x1 - x0 + 2 * m), h: Math.min(1, y1 - y0 + 2 * m) }; })() : null);
  const Z = zz ? clampN(Math.min(1 / zz.w, 1 / zz.h), 1, 6) : 1;
  return <div className={'ph-stage' + (zoomed ? ' zoomed' : '')}>
    {zz ? <div className="m3-tools"><button type="button" className={'m3-tool zoom' + (zoomed ? ' pri' : '')} onClick={() => setZoomed(!zoomed)}><Icon name={zoomed ? 'x' : 'search'} size={15} />{zoomed ? 'Отдалить' : 'Порты крупно'}</button></div> : null}
    <div className="ph-wrap" style={{ transform: zoomed && zz ? `scale(${Z}) translate(${(.5 - zz.x - zz.w / 2) * 100}%, ${(.5 - zz.y - zz.h / 2) * 100}%)` : 'none' }}>
    <img src={url} alt="" draggable="false" />
    {spots.map(s => <button key={s.n + ':' + s.x} type="button" className={'ph-spot' + (sel === s.n ? ' sel' : '')} aria-label={'Порт ' + s.n} onClick={() => onPick(s.n)}
      style={{ left: (s.x - s.w / 2) * 100 + '%', top: (s.y - s.h / 2) * 100 + '%', width: s.w * 100 + '%', height: s.h * 100 + '%' }} />)}
  </div></div>;
}

function PortPop({ device, n, ports }) {
  const { data } = useApp();
  if (n == null) return <div className="vt-pop empty"><span className="n">—</span><b>Нажмите на порт</b><small>номер, что подключено, скорость</small></div>;
  const p = (ports || []).find(x => x.n === n);
  if (!p) return <div className="vt-pop"><span className="n">{n}</span><b>Порт {n}</b><small>нет данных о порте</small></div>;
  const name = p.label || (p.peers && p.peers[0] && p.peers[0].name) || (p.kind === 'sfp' ? 'SFP, свободен' : p.link ? 'Без подписи' : 'Свободен');
  const patch = device ? patchesFor(data, device.id, p.n)[0] : null;
  return <div className="vt-pop" key={n}><span className={'n' + (p.link ? ' on' : '')}>{n}</span><b>{name}</b>
    <small>{[p.disabled ? 'выключен' : p.link ? (p.speed >= 1000 ? (p.speed / 1000) + ' Гбит/с' : p.speed + ' Мбит/с') : 'нет линка', p.poeW ? 'PoE ' + p.poeW + ' Вт' : '', patch ? patch.unit.name + ', порт ' + patch.n : ''].filter(Boolean).join(' · ')}</small></div>;
}

function CardPage({ e }) {
  const { data, admin } = useApp(); const toast = useToast(); const save = useCardsSave();
  const [color, color2] = cardColors(e), st = (e.device && e.device.state) || {}, s = st.summary || {};
  const kindText = (CARD_KINDS.find(k => k[0] === e.kind) || [0, KIND_TEXT[e.kind] || UNIT_TEXT[(e.unit || {}).type] || ''])[1];
  const ent = cardEntry(data, e), c = e.card || {};
  const purl = photoUrl(e.id, ent), spots = ent.spots || [];
  const ports = e.src === 'device' ? st.ports || [] : [];
  const [sel, setSel] = useState(() => +new URLSearchParams(location.search).get('port') || null);
  const pick = n => setSel(sel === n ? null : n);
  const hasPorts = ports.length > 0, hasMap = e.src === 'unit' && e.unit.portmap, isUps = e.src === 'device' && st.ups;
  const rows = e.src === 'manual' ? [['Производитель', c.vendor], ['Модель', c.model], ['IP-адрес', c.ip], ['MAC', c.mac], ['Серийный номер', c.serial], ['Где находится', c.location], ...(c.rows || []).map(r => [r.k || '—', r.v])]
    : (ent.rows || []).map(r => [r.k || '—', r.v]);
  const shown = rows.filter(r => r[1]);
  const note = e.src === 'manual' ? c.notes : (ent.notes || (e.unit && e.unit.notes) || (e.device && e.device.notes) || '');
  const up = ports.filter(p => p.link).length, poe = ports.reduce((a, p) => a + (p.poeW || 0), 0);
  const own = ent.model && (data.models || []).find(m => m.id === ent.model);
  const auto = useMemo(() => (ports.length ? autoModel(ports, s.model || e.name) : null), [ports.length, s.model, e.name]);
  const mdl = own ? own.model : auto;
  const saveView = async v => {                                   // «Зафиксировать»: the card opens at this angle next time
    const cards = data.cards || [], cur = e.src === 'manual' ? cards.find(c => c.id === e.id) : cards.find(c => c.of === e.id);
    const rec = { ...(cur || { of: e.id, name: e.name, kind: e.kind }), view: v };
    if (await save(cur ? cards.map(c => c === cur ? rec : c) : [...cards, rec])) toast('Положение сохранено: карточка будет открываться так');
  };
  return <div className="vt" style={{ '--tc': color, '--tc2': color2 }}>
    <div className="vt-head">
      <div className="vt-k">{[kindText, e.place].filter(Boolean).join(' · ')}</div>
      <h3>{e.name}</h3>
      <div className="vt-m">{[e.model || s.model, s.ip].filter(Boolean).join(' · ')}</div>
      {e.src === 'device' ? <div className={'vt-state ' + (st.status || '')}><i />{STATUS_TEXT[st.status] || 'Ожидание'}</div> : null}
    </div>
    {purl ? <PhotoPorts url={purl} spots={spots} sel={sel} onPick={pick} zoom={ent.pzoom} />
      : mdl ? <Model3D model={mdl} ports={ports} sel={sel} onPick={pick} view={ent.view} onSaveView={admin ? saveView : null} manual={own && ent.portsMode === 'manual'} marks={ent.mports} zoom={ent.zoom} />
      : !isUps && !hasMap ? <div className="vt-ico"><Icon name={e.kind} size={46} stroke={1.5} /></div> : null}
    {hasPorts ? <div className="vt-facts"><div><b>{up}/{ports.length}</b><span>Линк</span></div><div><b>{poe ? Math.round(poe) + ' Вт' : '—'}</b><span>PoE</span></div>
      <div><b>{s.uptime != null ? fmt.uptime(s.uptime) : '—'}</b><span>Работает</span></div></div> : null}
    {hasPorts || spots.length || (own && ports.length) ? <PortPop device={e.device} n={sel} ports={ports} /> : null}
    {hasMap ? <Card title="Порты"><PortMapView unit={e.unit} compact /></Card> : null}
    {isUps ? <CardUps device={e.device} /> : null}
    {shown.length ? <Card title={hasPorts || isUps ? 'Дополнительно' : 'Сведения'}><div className="cd-rows">{shown.map(([k, v], i) => <div className="cd-r" key={i}><span>{k}</span><b>{v}</b></div>)}</div></Card> : null}
    {note ? <Card title="Заметки"><div style={{ whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.5 }}>{note}</div></Card> : null}
  </div>;
}

/* ───────── Rack Live → «Сканер» → «Фото»: a picture of the device and its ports marked on it by hand ───────── */
async function shrinkImage(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => bad(new Error('не получилось открыть картинку')); i.src = url; });
    const k = Math.min(1, 1800 / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    const png = /png|webp/.test(file.type);                     // a cut-out on a transparent background stays transparent
    return await new Promise(ok => c.toBlob(ok, png ? 'image/png' : 'image/jpeg', .9));
  } finally { URL.revokeObjectURL(url); }
}

function PhotoEditor({ item, onClose, pane }) {
  const { data, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm(); const save = useCardsSave();
  const cards = data.cards || [];
  const entry = item.src === 'manual' ? cards.find(c => c.id === item.id) : cards.find(c => c.of === item.id);
  const url = photoUrl(item.id, entry);
  const ports = item.device ? ((item.device.state || {}).ports || []) : [];
  const [spots, setSpots] = useState(() => (entry && entry.spots) || []);
  const [zone, setZone] = useState(() => (entry && entry.pzoom) || null); const [zmode, setZmode] = useState(false);
  const [cur, setCur] = useState(null); const [busy, setBusy] = useState(false); const [aspect, setAspect] = useState(1);
  const [size, setSize] = useState(() => (entry && entry.spots && entry.spots[0] ? Math.round(entry.spots[0].w * 1000) / 10 : 4));
  const fileRef = useRef(null), wrap = useRef(null), drag = useRef(null);
  useEffect(() => { setSpots((entry && entry.spots) || []); }, [entry && entry.photo]);
  const label = n => { const p = ports.find(x => x.n === n); return p ? (p.label || (p.peers && p.peers[0] && p.peers[0].name) || '') : ''; };
  const nextN = () => { const used = new Set(spots.map(s => s.n)); const pool = ports.length ? ports.map(p => p.n) : Array.from({ length: 64 }, (_, i) => i + 1); return pool.find(n => !used.has(n)) || Math.max(0, ...spots.map(s => s.n)) + 1; };
  const rel = ev => { const r = wrap.current.getBoundingClientRect(); return { x: clampN((ev.clientX - r.left) / r.width, 0, 1), y: clampN((ev.clientY - r.top) / r.height, 0, 1) }; };
  const upload = async f => {
    if (!f) return; setBusy(true);
    try {
      const blob = await shrinkImage(f);
      const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': blob.type }, body: blob };
      const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
      const j = await (await fetch('/api/cards/photo/' + encodeURIComponent(item.id), init)).json();
      if (!j.ok) throw new Error(j.error || 'не получилось загрузить');
      await refresh(); toast('Фото загружено. Теперь нажмите на каждый порт на фото.');
    } catch (x) { toast(x.message, true); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const removePhoto = async () => {
    if (!(await confirm('Убрать фото? Метки портов тоже пропадут, карточка снова покажет 3D-модель.', { title: 'Убрать фото', ok: 'Убрать', danger: true }))) return;
    const init = { method: 'DELETE', credentials: 'same-origin', headers: {} }; const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
    try { await fetch('/api/cards/photo/' + encodeURIComponent(item.id), init); await refresh(); setSpots([]); setCur(null); } catch (x) { toast(x.message, true); }
  };
  const bw = wrap.current ? wrap.current.clientWidth : 0, bh = wrap.current ? wrap.current.clientHeight : 0;
  const pl = usePlacer(wrap, {
    spots: spots.map(x => ({ x: x.x * bw, y: x.y * bh, r: x.w * bw / 2 })),
    onPick: i => setCur(i),
    onDrag: (i, p) => setSpots(a => a.map((x, j) => (j === i ? { ...x, x: p.px / p.w, y: p.py / p.h } : x))),
    onNew: p => { setSpots(a => [...a, { n: nextN(), x: p.px / p.w, y: p.py / p.h, w: size / 100, h: size / 100 * aspect }]); setCur(spots.length); } });
  const resize = v => { setSize(v); setSpots(s => s.map(x => ({ ...x, w: v / 100, h: v / 100 * aspect }))); };
  const zd = useZoneDraw(wrap, r => { const q = v => Math.round(v * 1e4) / 1e4; setZone({ x: q(r.x / r.W), y: q(r.y / r.H), w: q(r.w / r.W), h: q(r.h / r.H) }); setZmode(false); });
  const doSave = async () => { if (!entry) return; setBusy(true); const ok = await save(cards.map(c => c.id === entry.id ? (({ pzoom, ...rest }) => zone ? { ...rest, spots, pzoom: zone } : { ...rest, spots })(c) : c)); setBusy(false); if (ok) { toast('Порты на фото сохранены'); onClose(); } };
  const pbox = (x, i, cls) => <span key={i} className={'pe-spot ' + cls} style={{ left: (x.x - x.w / 2) * 100 + '%', top: (x.y - x.h / 2) * 100 + '%', width: x.w * 100 + '%', height: x.h * 100 + '%' }}>{x.n ? <span>{x.n}</span> : null}</span>;
  const pspots = <>{spots.map((x, i) => pbox(x, i, cur === i ? 'on' : ''))}{pl.ghost && bw ? pbox({ x: pl.ghost.px / bw, y: pl.ghost.py / bh, w: size / 100, h: size / 100 * aspect }, 'g', 'ghost') : null}</>;
  const s = cur != null ? spots[cur] : null;
  const actions = <><Btn onClick={onClose}>Отмена</Btn>{url ? <Btn kind="primary" busy={busy} onClick={doSave}>Сохранить</Btn> : null}</>;
  const body = <>
    <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/*" hidden onChange={ev => upload(ev.target.files[0])} />
    {!url ? <button type="button" className="pe-drop" onClick={() => fileRef.current.click()} disabled={busy}>
      <Icon name="camera" size={30} /><b>{busy ? 'Загружаю…' : 'Выбрать фото'}</b>
      <small>PNG (лучше вырезанное, на прозрачном фоне) или JPEG. Без фото карточка показывает 3D-модель.</small></button>
      : <>
        <div className="dim" style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 10 }}>Коснитесь фото там, где порт, и ведите палец: над ним появится лупа, метка встанет там, где отпустите. Готовую метку можно взять пальцем рядом с ней и перетащить; касание выбирает её номер. В карточке метки будут невидимыми кнопками.</div>
        <div className="pe-stage"><div className={'pe-wrap' + (zmode ? ' zoning' : '')} ref={wrap} {...(zmode ? zd.handlers : pl.handlers)}>
          {zone ? <ZoneBox r={{ left: zone.x * 100 + '%', top: zone.y * 100 + '%', width: zone.w * 100 + '%', height: zone.h * 100 + '%' }} /> : null}
          {zd.draft ? <ZoneBox draft r={{ left: zd.draft.x, top: zd.draft.y, width: zd.draft.w, height: zd.draft.h }} /> : null}
          <img src={url} alt="" draggable="false" onLoad={ev => setAspect(ev.target.naturalWidth / ev.target.naturalHeight)} />{pspots}
        </div></div>
        <Loupe lp={pl.lp} w={bw} h={bh}><div style={{ position: 'relative', width: bw, height: bh }}><img src={url} alt="" draggable="false" style={{ display: 'block', width: '100%', height: '100%' }} />{pspots}</div></Loupe>
        <div className="pe-bar">
          <label className="row" style={{ gap: 10, fontSize: 13 }}><span className="dim" style={{ whiteSpace: 'nowrap' }}>Размер меток</span>
            <input type="range" min="1.5" max="12" step="0.25" value={size} onChange={ev => resize(+ev.target.value)} style={{ flex: 1, accentColor: 'var(--accent)' }} /></label>
          {s ? <div className="pe-sel"><b>Метка</b>
            {ports.length ? <select className="input" value={s.n} onChange={ev => setSpots(a => a.map((x, j) => j === cur ? { ...x, n: +ev.target.value } : x))}>
              {ports.map(p => <option key={p.n} value={p.n}>Порт {p.n}{label(p.n) ? ' · ' + label(p.n) : ''}{spots.some((x, j) => j !== cur && x.n === p.n) ? ' (уже отмечен)' : ''}</option>)}</select>
              : <input className="input" type="number" min="1" max="256" value={s.n} onChange={ev => setSpots(a => a.map((x, j) => j === cur ? { ...x, n: +ev.target.value || 1 } : x))} style={{ width: 90 }} />}
            <Btn size="sm" kind="danger" onClick={() => { setSpots(a => a.filter((_, j) => j !== cur)); setCur(null); }}>Убрать</Btn></div>
            : <div className="dim3" style={{ fontSize: 12.5 }}>Отмечено портов: {spots.length}{ports.length ? ' из ' + ports.length : ''}</div>}
          <div className="row wrap" style={{ gap: 8 }}><Btn size="sm" icon="camera" busy={busy} onClick={() => fileRef.current.click()}>Заменить фото</Btn>
            {spots.length ? <Btn size="sm" onClick={() => { setSpots([]); setCur(null); }}>Убрать все метки</Btn> : null}
            <Btn size="sm" kind="danger" onClick={removePhoto}>Убрать фото</Btn></div>
          <ZoneBar zone={zone} zmode={zmode} setZmode={setZmode} onReset={() => setZone(null)} />
        </div>
      </>}
  </>;
  if (pane) return <>{body}{url ? <div className="row" style={{ gap: 8, marginTop: 12, justifyContent: 'flex-end' }}>{actions}</div> : null}</>;
  return <Modal title={'Фото и порты · ' + item.name} onClose={onClose} wide footer={actions}>{body}  </Modal>;
}

/* ───────── hand-made cards: editor ───────── */
function CardEditor({ card, onClose, onSave, onDelete, extend }) {
  const [f, setF] = useState(() => ({ id: '', name: '', kind: 'other', vendor: '', model: '', ip: '', mac: '', serial: '', location: '', notes: '', rows: [], ...card }));
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const setRow = (i, k, v) => setF(x => ({ ...x, rows: x.rows.map((r, j) => j === i ? { ...r, [k]: v } : r) }));
  const inp = (k, label, ph, extra = {}) => <Field label={label}><input className="input" value={f[k] || ''} placeholder={ph} onChange={ev => set(k, ev.target.value)} {...extra} /></Field>;
  return <Modal title={extend ? 'Дополнить: ' + extend : card && card.id ? 'Карточка: ' + card.name : 'Новая карточка'} onClose={onClose}
    footer={<><Btn onClick={onClose}>Отмена</Btn>{card && card.id ? <Btn kind="danger" onClick={() => onDelete(card)}>Удалить</Btn> : null}
      <Btn kind="primary" busy={busy} disabled={!f.name.trim() && !extend} onClick={async () => { setBusy(true); const ok = await onSave(f); setBusy(false); if (ok) onClose(); }}>Сохранить</Btn></>}>
    <div className="col" style={{ gap: 12 }}>
      {extend ? <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>То, что есть у устройства в Rack Live, показывается само. Здесь только ваши добавки: они появятся в его карточке.</div> : <>
      {inp('name', 'Название', 'Например: Принтер в бухгалтерии')}
      <Field label="Что это"><select className="input" value={f.kind} onChange={ev => set('kind', ev.target.value)}>{CARD_KINDS.map(k => <option key={k[0]} value={k[0]}>{k[1]}</option>)}</select></Field>
      <div className="row" style={{ gap: 10 }}><div className="grow">{inp('vendor', 'Производитель', 'HP')}</div><div className="grow">{inp('model', 'Модель', 'LaserJet 1020')}</div></div>
      <div className="row" style={{ gap: 10 }}><div className="grow">{inp('ip', 'IP-адрес', '192.168.1.50')}</div><div className="grow">{inp('mac', 'MAC', 'aa:bb:cc:dd:ee:ff')}</div></div>
      {inp('serial', 'Серийный номер', '')}
      {inp('location', 'Где находится', 'Кабинет 12, у окна')}</>}
      <Field label="Свои строки" hint="Любые факты: дата покупки, гарантия, логин администратора, расходники…">
        <div className="col" style={{ gap: 8 }}>{f.rows.map((r, i) => <div className="row" key={i} style={{ gap: 8 }}>
          <input className="input" style={{ flex: '0 0 38%' }} value={r.k} placeholder="Название" onChange={ev => setRow(i, 'k', ev.target.value)} />
          <input className="input grow" value={r.v} placeholder="Значение" onChange={ev => setRow(i, 'v', ev.target.value)} />
          <Btn size="sm" icon="x" onClick={() => setF(x => ({ ...x, rows: x.rows.filter((_, j) => j !== i) }))} /></div>)}
          <div><Btn size="sm" icon="plus" onClick={() => setF(x => ({ ...x, rows: [...x.rows, { k: '', v: '' }] }))}>Добавить строку</Btn></div></div></Field>
      <Field label="Заметки"><textarea className="input" rows={4} value={f.notes} onChange={ev => set('notes', ev.target.value)} placeholder="Что важно знать об этом устройстве" /></Field>
    </div>
  </Modal>;
}

/* ───────── stickers: print ───────── */
/* a sticker as a PNG: the code at its real size (the pixel density is written into the file, so a print app keeps the millimetres) with the name under it */
const CRC_T = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(u8) { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC_T[(c ^ u8[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
function pngWithDpm(bytes, dpm) {                       // adds the pHYs chunk (pixels per metre) right after IHDR
  const chunk = new Uint8Array(21), dv = new DataView(chunk.buffer);
  dv.setUint32(0, 9); chunk.set([0x70, 0x48, 0x59, 0x73], 4); dv.setUint32(8, dpm); dv.setUint32(12, dpm); chunk[16] = 1; dv.setUint32(17, crc32(chunk.subarray(4, 17)));
  const out = new Uint8Array(bytes.length + 21); out.set(bytes.subarray(0, 33)); out.set(chunk, 33); out.set(bytes.subarray(33), 54); return out;
}
async function stickerFile(e, mm) {
  if (typeof qrcode !== 'function') throw new Error('нет библиотеки QR');
  const q = qrcode(0, 'M'); q.addData('RL:' + e.id); q.make();
  const n = q.getModuleCount(), mod = Math.max(4, Math.round(24 * mm / n)), qs = mod * n, ppm = qs / mm, pad = Math.round(3 * ppm);
  const c = document.createElement('canvas'), g = c.getContext('2d'), fs = Math.round(2.4 * ppm);
  g.font = `600 ${fs}px -apple-system, "Segoe UI", Arial, sans-serif`;
  const words = String(e.name || '').split(/\s+/), lines = []; let cur = '';
  words.forEach(w => { const tryL = cur ? cur + ' ' + w : w; if (g.measureText(tryL).width > qs + pad && cur) { lines.push(cur); cur = w; } else cur = tryL; });
  if (cur) lines.push(cur);
  const shown = lines.slice(0, 2).map((l, i, a) => i === 1 && lines.length > 2 ? l.slice(0, Math.max(1, l.length - 1)) + '…' : l);
  c.width = qs + 2 * pad; c.height = pad + qs + Math.round(fs * .5) + shown.length * Math.round(fs * 1.25) + pad;
  g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.fillStyle = '#000';
  for (let r = 0; r < n; r++) for (let k = 0; k < n; k++) if (q.isDark(r, k)) g.fillRect(pad + k * mod, pad + r * mod, mod, mod);
  g.font = `600 ${fs}px -apple-system, "Segoe UI", Arial, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'top';
  shown.forEach((l, i) => g.fillText(l, c.width / 2, pad + qs + Math.round(fs * .5) + i * Math.round(fs * 1.25)));
  const blob = await new Promise(res => c.toBlob(res, 'image/png'));
  const buf = pngWithDpm(new Uint8Array(await blob.arrayBuffer()), Math.round(ppm * 1000));
  return new File([buf], `RL-${e.id}-${mm}mm.png`, { type: 'image/png' });
}
/* «Сохранить / поделиться»: the pictures are made first (a share must start right from a tap), then «Поделиться» opens the system sheet — «Сохранить изображение» puts them into Photos */
function StickerFiles({ items, mm, onClose }) {
  const toast = useToast(); const [files, setFiles] = useState(null); const [err, setErr] = useState('');
  useEffect(() => { let dead = false; Promise.all(items.map(e => stickerFile(e, mm))).then(f => { if (!dead) setFiles(f); }).catch(x => !dead && setErr(String(x.message || x))); return () => { dead = true; }; }, []);
  const urls = useMemo(() => (files || []).map(f => URL.createObjectURL(f)), [files]);
  useEffect(() => () => urls.forEach(u => URL.revokeObjectURL(u)), [urls]);
  const canShare = files && navigator.canShare && navigator.canShare({ files });
  const share = async () => { try { await navigator.share({ files, title: 'Наклейки Rack Live' }); } catch (x) { if (x && x.name !== 'AbortError') toast('Не получилось открыть «Поделиться». Нажмите «Скачать».', true); } };
  const download = () => files.forEach((f, i) => setTimeout(() => { const a = document.createElement('a'); a.href = urls[i]; a.download = f.name; document.body.appendChild(a); a.click(); a.remove(); }, i * 250));
  return <Modal title={items.length === 1 ? 'Наклейка: ' + items[0].name : `Наклейки · ${items.length}`} onClose={onClose}
    footer={<><Btn onClick={onClose}>Закрыть</Btn>{files ? <Btn onClick={download} icon="download">Скачать</Btn> : null}{canShare ? <Btn kind="primary" icon="share" onClick={share}>Поделиться</Btn> : null}</>}>
    {err ? <div className="cam-warn">Не удалось сделать картинку: {err}</div> : !files ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Готовлю…</div>
      : <><div className="cd-stk-grid">{files.map((f, i) => <div className="cd-stk" key={f.name}><img className="cd-stk-img" src={urls[i]} alt={f.name} /><small className="mono">{f.name}</small></div>)}</div>
        <div className="dim" style={{ fontSize: 13, lineHeight: 1.5, marginTop: 12 }}>{canShare ? '«Поделиться» → «Сохранить изображение» кладёт наклейку в «Фото» (или отправьте в «Файлы», AirDrop, принтер). ' : 'Нажмите «Скачать» (на iPhone: нажмите и удерживайте картинку → «Сохранить в Фото»). '}
          Размер зашит в файл: код {mm} мм. Печатайте в масштабе 100%, а не «по размеру листа».</div></>}
  </Modal>;
}

function StickersCard({ items, onPrint }) {
  const [pick, setPick] = useState({}); const [mm, setMm] = useState(() => +lsGet('rl_cards_mm', 25)); const [q, setQ] = useState('');
  const shown = items.filter(e => !q || (e.name + ' ' + e.place + ' ' + e.sub).toLowerCase().includes(q.toLowerCase()));
  const chosen = items.filter(e => pick[e.id]);
  return <Card title="Наклейки с QR-кодами">
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 10 }}>Отметьте устройства, выберите размер: получатся картинки, которые можно сохранить в «Фото» или отправить на печать. Клейте на ровное место на корпусе. Код читается и в «Карточках», и в «Сканере портов», поэтому для коммутатора, который уже наклеен, ничего перепечатывать не нужно.</div>
    <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
      <Field label="Размер кода, мм"><select className="input" value={mm} onChange={ev => { setMm(+ev.target.value); lsSet('rl_cards_mm', ev.target.value); }}>{[18, 20, 25, 30, 40].map(n => <option key={n} value={n}>{n} мм</option>)}</select></Field>
      <div className="grow" />
      <Btn size="sm" onClick={() => setPick(Object.fromEntries(items.map(e => [e.id, true])))}>Выбрать все</Btn><Btn size="sm" onClick={() => setPick({})}>Снять выбор</Btn></div>
    {items.length > 8 ? <SearchBox value={q} onChange={setQ} placeholder="Найти устройство" /> : null}
    <div className="list cd-pick" style={{ marginTop: 8 }}>{shown.map(e => <label className="li" key={e.id} style={{ cursor: 'pointer' }}>
      <input type="checkbox" checked={!!pick[e.id]} onChange={ev => setPick(p => ({ ...p, [e.id]: ev.target.checked }))} />
      <KindIcon kind={e.kind} size={30} round={8} /><div className="grow" style={{ minWidth: 0 }}><div className="ellipsis" style={{ fontWeight: 600, fontSize: 14 }}>{e.name}</div>
        <div className="dim ellipsis" style={{ fontSize: 12 }}>{[e.place || e.group, e.sub].filter(Boolean).join(' · ')}</div></div></label>)}</div>
    <div style={{ marginTop: 12 }}><Btn kind="primary" icon="download" disabled={!chosen.length} onClick={() => onPrint(chosen, mm)}>Сохранить / поделиться · {chosen.length}</Btn></div>
    <div className="dim3" style={{ fontSize: 12, marginTop: 8 }}>В окне печати поставьте «Масштаб 100%», а не «по размеру страницы».</div>
  </Card>;
}

/* ───────── Rack Live → Settings → Apps → «Сканер»: every card in one place — fill in, create, get the sticker again ───────── */
function useCardsSave() {
  const { refresh } = useApp(); const toast = useToast();
  return async list => { try { await api('/api/cards', { method: 'PUT', body: { cards: list } }); await refresh(); return true; } catch (e) { toast(e.message, true); return false; } };
}

function QrModal({ e, onClose, onPrint }) {
  const toast = useToast(); const [mm, setMm] = useState(() => +lsGet('rl_cards_mm', 25));
  return <Modal title={e.name} onClose={onClose} footer={<><Btn onClick={onClose}>Закрыть</Btn><Btn kind="primary" icon="download" onClick={() => onPrint([e], mm)}>Сохранить / поделиться</Btn></>}>
    <div className="col" style={{ alignItems: 'center', gap: 12 }}>
      <div style={{ background: '#fff', padding: 14, borderRadius: 18, lineHeight: 0 }}><QrCode text={'RL:' + e.id} size={230} /></div>
      <div className="mono" style={{ fontSize: 15, fontWeight: 650 }}>RL:{e.id}</div>
      <div className="dim" style={{ fontSize: 13, textAlign: 'center', lineHeight: 1.5 }}>Код у карточки всегда один: если наклейка потерялась или выцвела, сохраните её картинку и распечатайте снова. Тот же код читает и «Сканер портов».</div>
      <Field label="Размер кода на бумаге"><select className="input" value={mm} onChange={ev => { setMm(+ev.target.value); lsSet('rl_cards_mm', ev.target.value); }}>{[18, 20, 25, 30, 40].map(n => <option key={n} value={n}>{n} мм</option>)}</select></Field>
      <Btn size="sm" icon="copy" onClick={() => toast(copyText('RL:' + e.id) ? 'Код скопирован' : 'Не получилось скопировать', false)}>Скопировать код</Btn>
    </div>
  </Modal>;
}

function ScannerMenu() {
  const { data } = useApp(); const confirm = useConfirm(); const save = useCardsSave();
  const items = useMemo(() => cardList(data), [data]), cards = data.cards || [];
  const qs = new URLSearchParams(location.search);
  const [list, setList] = useState(() => qs.get('cl') === '1'); const [q, setQ] = useState('');
  const [edit, setEdit] = useState(() => qs.get('newcard') === '1' ? { item: null, card: {} } : null); const [qr, setQr] = useState(null); const [photo, setPhoto] = useState(() => { const id = qs.get('photo'); return (id && cardList(data).find(i => i.id === id)) || null; });
  const [print, setPrint] = useState(() => { const id = qs.get('sticker'), x = id && cardList(data).find(i => i.id === id); return x ? { list: [x], mm: 25 } : null; }); const [stk, setStk] = useState(false);
  const ext = id => cards.find(c => c.of === id);
  const shown = items.filter(x => !q || [x.name, x.place, x.sub, x.group].join(' ').toLowerCase().includes(q.toLowerCase()));
  const startPrint = (l, mm) => { setQr(null); setStk(false); setPrint({ list: l, mm: mm || +lsGet('rl_cards_mm', 25) }); };
  const begin = x => setEdit({ item: x, card: x.src === 'manual' ? x.card : ext(x.id) || { of: x.id, name: x.name, kind: x.kind } });
  const row = (icon, title, sub, onClick) => <button type="button" className="plug-row" onClick={onClick}><span className="ico-circle"><Icon name={icon} size={16} /></span>
    <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b>{title}</b><small>{sub}</small></span><Icon name="chevron" size={14} /></button>;
  return <>
    <div className="dim3" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '.3px', margin: '6px 0 2px' }}>Карточки</div>
    {row('list', 'Карточки устройств · ' + items.length, 'дополнить, получить QR, посмотреть', () => setList(true))}
    {row('plus', 'Создать карточку', 'для того, чего нет в шкафу: принтер, телевизор, чужой роутер', () => setEdit({ item: null, card: {} }))}
    {row('download', 'Наклейки', 'сохранить QR-коды в «Фото» или отправить на печать', () => setStk(true))}
    {list ? <Modal title="Карточки устройств" onClose={() => setList(false)} wide>
      <div className="dim" style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 10 }}>Порты, нагрузка ИБП и состояние берутся из Rack Live сами. «Вид» — 3D-модель устройства (своя, от нейросети, или автоматическая по портам) либо фото с отмеченными портами. «Дополнить» добавляет свои строки и заметку; «QR» показывает наклейку и сохраняет её картинку; «Открыть» показывает карточку так, как её видит приложение.</div>
      <div style={{ marginBottom: 10 }}><SearchBox value={q} onChange={setQ} placeholder="Найти устройство" /></div>
      <div className="plug-list" style={{ border: 0, margin: 0, padding: 0 }}>{shown.map(x => <div className="plug-row" key={x.src + x.id} style={{ cursor: 'default', flexWrap: 'wrap' }}>
        <KindIcon kind={x.kind} size={32} round={9} />
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{x.name}</b>
          <small className="ellipsis" style={{ display: 'block' }}>{[x.place || x.group, x.sub].filter(Boolean).join(' · ')}</small></span>
        <span className="row" style={{ gap: 6, flexShrink: 0 }}>
          <Btn size="sm" icon="box" onClick={() => setPhoto(x)} title="3D-модель или фото">Вид</Btn>
          <Btn size="sm" icon="tag" onClick={() => setQr(x)} title="QR-наклейка">QR</Btn>
          <Btn size="sm" icon="edit" onClick={() => begin(x)}>{x.src === 'manual' ? 'Изменить' : 'Дополнить'}</Btn>
          <a className="btn sm" href={'/cards?card=' + encodeURIComponent(x.id)} target="_blank" rel="noreferrer">Открыть</a></span></div>)}
        {!shown.length ? <div className="empty">Ничего не найдено</div> : null}</div>
    </Modal> : null}
    {edit ? <CardEditor extend={edit.item && edit.item.src !== 'manual' ? edit.item.name : null} card={edit.card} onClose={() => setEdit(null)}
      onSave={async f => { const it = edit.item, rec = it && it.src !== 'manual' ? { ...f, of: it.id, name: it.name, kind: it.kind } : f; return save(f.id ? cards.map(c => c.id === f.id ? rec : c) : [...cards, rec]); }}
      onDelete={async c => { const word = edit.item && edit.item.src !== 'manual' ? 'Убрать добавленные данные' : `Удалить карточку «${c.name}»? Её наклейка перестанет работать`; if (await confirm(word + '?', { title: 'Подтвердите', ok: 'Да', danger: true })) { if (await save(cards.filter(x => x.id !== c.id))) setEdit(null); } }} /> : null}
    {qr ? <QrModal e={qr} onClose={() => setQr(null)} onPrint={startPrint} /> : null}
    {photo ? <AppearanceModal item={photo} onClose={() => setPhoto(null)} /> : null}
    {stk ? <Modal title="Наклейки" onClose={() => setStk(false)} wide><StickersCard items={items} onPrint={startPrint} /></Modal> : null}
    {print ? <StickerFiles items={print.list} mm={print.mm} onClose={() => setPrint(null)} /> : null}
  </>;
}

function CardSheet({ onClose, children }) {
  const [dy, setDy] = useState(0); const [out, setOut] = useState(false); const g = useRef(null);
  const shut = () => { setOut(true); setTimeout(onClose, 260); };
  const down = ev => { g.current = { y: ev.clientY }; try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch (x) { } };
  const move = ev => { if (g.current) setDy(Math.max(0, ev.clientY - g.current.y)); };
  const up = () => { if (!g.current) return; g.current = null; if (dy > 110) shut(); else setDy(0); };
  return <>
    <div className={'cd-dim' + (out ? ' out' : '')} onClick={shut} />
    <div className={'cd-sheet2' + (out ? ' out' : '')} style={dy ? { transform: `translateY(${dy}px)`, transition: 'none' } : null} role="dialog" aria-label="Карточка устройства">
      <div className="cd-sheet-top" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}><i className="cd-grab" />
        <button type="button" className="cd-x" aria-label="Закрыть" onPointerDown={ev => ev.stopPropagation()} onClick={shut}><Icon name="x" size={16} /></button></div>
      <div className="cd-sheet-body">{children}</div>
    </div>
  </>;
}

/* ───────── the app itself (/cards): the camera, nothing else. A QR in the frame → the card slides up, it can only be closed ───────── */
function CardsApp() {
  const { data } = useApp(); const toast = useToast();
  const items = useMemo(() => cardList(data), [data]);
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('card') || null);          // ?card=<id>: straight to a card (tests)
  const last = useRef({ id: '', t: 0 }), warned = useRef({ id: '', t: 0 });
  const e = open ? items.find(x => x.id === open) : null;
  const found = id => {
    const now = Date.now();
    if (id === last.current.id && now - last.current.t < 3000) return;                       // the sticker that was just closed is still in the frame
    if (items.some(x => x.id === id)) { setOpen(id); return; }
    if (!(id === warned.current.id && now - warned.current.t < 4000)) { warned.current = { id, t: now }; toast('Эта наклейка не из вашего Rack Live или карточку удалили', true); }
  };
  const close = () => { last.current = { id: open, t: Date.now() }; setOpen(null); };
  useEffect(() => { if (open && !e && items.length) close(); }, [items.length]);
  return <div className="cards-app cd-app">
    <CardScanner paused={!!open} onFound={found} items={items} />
    {open && e ? <CardSheet key={open} onClose={close}><CardPage e={e} /></CardSheet> : null}
  </div>;
}
