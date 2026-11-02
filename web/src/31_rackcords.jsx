/* Physical patch cords: only explicit port-to-port wiring, never inferred network edges. */
const CORD_COLORS = ['#58a6ff', '#49d895', '#ffd35c', '#f38d65', '#bc96ff', '#f2f5f8', '#f471a1', '#55d6dc'];
const cordEndKey = e => JSON.stringify([e.unit, e.device || '', String(e.port)]);
const cordKey = (a, b) => [cordEndKey(a), cordEndKey(b)].sort().join('|');
function rackCords(rack, data) {
  const units = rack.units || [], out = [], seen = new Set();
  const normalize = e => { const u = units.find(u => u.id === e.unit); return u ? { unit: u.id, port: String(e.port), ...(u.portmap ? {} : (e.device || unitDevIds(u)[0]) ? { device: e.device || unitDevIds(u)[0] } : {}) } : null; };
  const add = (a, b, manual) => {
    a = normalize(a); b = normalize(b);
    if (!a || !b || !a.port || !b.port || cordEndKey(a) === cordEndKey(b)) return;
    const key = cordKey(a, b); if (seen.has(key)) return; seen.add(key);
    out.push({ a, b, key, manual, color: /^#[0-9a-f]{6}$/i.test((rack.cordColors || {})[key] || '') ? rack.cordColors[key] : CORD_COLORS[out.length % CORD_COLORS.length] });
  };
  units.forEach(u => Object.entries((u.portmap || {}).ports || {}).forEach(([port, m]) => {
    if (!m || !m.dev || m.port == null || String(m.port) === '') return;
    const target = String(m.dev).startsWith('u:') ? units.find(v => v.id === String(m.dev).slice(2)) : units.find(v => unitDevIds(v).includes(m.dev));
    if (target) add({ unit: u.id, port }, { unit: target.id, port: m.port, ...(String(m.dev).startsWith('u:') ? {} : { device: m.dev }) }, false);
  }));
  (rack.patchCords || []).forEach(c => { if (c && c.a && c.b) add(c.a, c.b, true); });
  return out;
}
function cordEndLabel(e, rack, data) {
  const u = rack.units.find(x => x.id === e.unit), d = e.device && data.devices.find(x => x.id === e.device);
  return `${d ? d.name : u ? u.name : 'Устройство'} · ${u && u.type === 'modem' ? portName(u, e.port) : 'порт ' + e.port}`;
}
function rackCordPorts(rack, data, unit, device, ports) {
  const list = [...(ports || [])]; if (unit.portmap) return list;
  const known = new Set(list.map(p => String(p.n)));
  rackCords(rack, data).forEach(c => [c.a, c.b].forEach(e => {
    if (e.unit === unit.id && (e.device || '') === (device || '') && !known.has(String(e.port))) {
      known.add(String(e.port)); list.push({ n: e.port, link: false, cls: 'cord-unreported' });
    }
  }));
  return list;
}
function roundedCord(points, radius = 8) {
  const p = points.filter((v, i) => !i || v[0] !== points[i - 1][0] || v[1] !== points[i - 1][1]);
  if (p.length < 2) return '';
  let path = `M${p[0][0]},${p[0][1]}`;
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1], b = p[i], c = p[i + 1], ab = Math.hypot(b[0] - a[0], b[1] - a[1]), bc = Math.hypot(c[0] - b[0], c[1] - b[1]);
    const r = Math.min(radius, ab / 2, bc / 2);
    const start = [b[0] + (a[0] - b[0]) * r / ab, b[1] + (a[1] - b[1]) * r / ab];
    const end = [b[0] + (c[0] - b[0]) * r / bc, b[1] + (c[1] - b[1]) * r / bc];
    const bend = .55228475;
    path += `L${start[0]},${start[1]}C${start[0] + (b[0] - start[0]) * bend},${start[1] + (b[1] - start[1]) * bend} ${end[0] + (b[0] - end[0]) * bend},${end[1] + (b[1] - end[1]) * bend} ${end[0]},${end[1]}`;
  }
  return path + `L${p[p.length - 1][0]},${p[p.length - 1][1]}`;
}
function cordRoute(a, b, organizers, lane, k = 1, slot = 0) {
  const lo = Math.min(a.y, b.y), hi = Math.max(a.y, b.y);
  if (organizers.length) {
    // Like a real rack: each end drops into the organizer next to its port (above or below),
    // runs inside it to the side, and organizers are joined by one continuous run down the
    // vertical cable channel beside the rails. Nothing is left floating on its own.
    const near = p => organizers.reduce((best, o) => Math.abs(o.y - p.y) < Math.abs(best.y - p.y) ? o : best);
    let oa = near(a), ob = near(b);
    // same organizer reachable by both ends without a long detour → keep the cord inside it
    const shared = organizers.filter(o => o.y > lo - 80 * k && o.y < hi + 80 * k && Math.abs(o.y - a.y) <= 80 * k && Math.abs(o.y - b.y) <= 80 * k);
    if (oa !== ob && shared.length) oa = ob = shared.reduce((best, o) => Math.abs(o.y - (a.y + b.y) / 2) < Math.abs(best.y - (a.y + b.y) / 2) ? o : best);
    const right = lane > (oa.x + oa.width / 2);
    const sideX = o => right ? o.x + o.width : o.x;
    const runY = o => o.y + (slot % 5 - 2) * 1.6 * k;           // parallel cords don't sit on one line
    const into = (p, o) => {
      const far = Math.abs(p.y - o.y) > 80 * k;
      if (far) {                                                  // no organizer close by: straight down/up the channel
        const lead = Math.sign(o.y - p.y) * 14 * k;
        return { path: [[p.x, p.y], [p.x, p.y + lead], [lane, p.y + lead]], viaLane: true };
      }
      // Drop into the organizer's lip: its face stays above the cable, so the cord disappears into it.
      const edgeY = p.y < o.y ? o.top : o.top + o.height;
      const direction = Math.sign(edgeY - p.y) || 1, span = Math.abs(edgeY - p.y);
      const bow = Math.sign(lane - p.x) * Math.min(8 * k, span * .2);
      const x = Math.max(o.x + 2 * k, Math.min(o.x + o.width - 2 * k, p.x + bow));
      return { d: `M${p.x},${p.y}C${p.x},${p.y + direction * span * .4} ${x},${edgeY - direction * span * .3} ${x},${edgeY}`, viaLane: false };
    };
    const ea = into(a, oa), eb = into(b, ob), paths = [];
    if (ea.d) paths.push(ea.d); if (eb.d) paths.push(eb.d);
    if (oa === ob && !ea.viaLane && !eb.viaLane) return paths;      // both ends in one organizer: hidden inside it
    // the visible run: (organizer side | far port) → channel → (organizer side | far port)
    const startPts = ea.viaLane ? ea.path : [[sideX(oa), runY(oa)], [lane, runY(oa)]];
    const endPts = eb.viaLane ? [...eb.path].reverse() : [[lane, runY(ob)], [sideX(ob), runY(ob)]];
    paths.push(roundedCord([...startPts, ...endPts], 10 * k));
    return paths;
  }
  const direction = b.y >= a.y ? 1 : -1, turn = Math.min(24 * k, Math.abs(b.y - a.y) / 3 || 24 * k);
  return [roundedCord([[a.x, a.y], [a.x, a.y + direction * turn], [lane, a.y + direction * turn], [lane, b.y - direction * turn], [b.x, b.y - direction * turn], [b.x, b.y]], 22 * k)];
}
function cordOrganizerBoxes(rack, side, width, scale, mode) {
  return rack.units.filter(u => u.type === 'organizer' && (u.side || 'front') === side).map(u => {
    const x = mode === '3d' ? (width - R3.PANEL * scale) / 2 : 29;
    const top = mode === '3d' ? (R3.TOP + (u.uStart - 1) * R3.U + .75) * scale : 8 + (u.uStart - 1) * U_PX;
    const height = mode === '3d' ? (u.uSize * R3.U - 1.5) * scale : u.uSize * U_PX - 4;
    return { x, top, width: width - 2 * x, height, y: top + height / 2 };
  });
}
function cordLane(width, index, right, scale = 1) {
  const inset = (8 + index % 5 * 1.8) * scale;
  return right ? width - inset : inset;
}
function RackCordOverlay({ root, rack, data, side, enabled, width, height, scale = 1, mode = 'flat', onPick }) {
  const [layout, setLayout] = useState({ points: {}, width: 0, height: 0 });
  const cords = rackCords(rack, data);
  useLayoutEffect(() => {
    if (!enabled) return;
    let ro;
    const frame = requestAnimationFrame(() => {
    const el = root.current; if (!el) return;
    const measure = () => {
      const points = {}, w = width || el.clientWidth, h = height || el.offsetHeight;
      const offset = (node, stop) => { let x = 0, y = 0; for (let n = node; n && n !== stop; n = n.offsetParent) { x += n.offsetLeft; y += n.offsetTop; } return { x, y }; };
      for (const c of cords) for (const end of [c.a, c.b]) {
        const unit = rack.units.find(u => u.id === end.unit); if (!unit || (unit.side || 'front') !== side) continue;
        const node = [...el.querySelectorAll('[data-cord-unit]')].find(n => n.getAttribute('data-cord-unit') === end.unit); if (!node) continue;
        const device = end.device && [...node.querySelectorAll('[data-cord-device]')].find(n => n.getAttribute('data-cord-device') === end.device);
        const port = [...(device || node).querySelectorAll('[data-cord-port]')].find(n => n.getAttribute('data-cord-port') === String(end.port)); if (!port) continue;
        const p = offset(port, mode === '3d' ? node : el);
        points[cordEndKey(end)] = mode === '3d' ? { x: (w - R3.PANEL * scale) / 2 + p.x + port.offsetWidth / 2, y: R3.TOP * scale + (unit.uStart - 1) * R3.U * scale + p.y + port.offsetHeight / 2 }
          : { x: p.x + port.offsetWidth / 2, y: p.y + port.offsetHeight / 2 };
      }
      setLayout({ points, width: w, height: h });
    };
    measure(); ro = new ResizeObserver(measure); ro.observe(el);
    });
    return () => { cancelAnimationFrame(frame); if (ro) ro.disconnect(); };
  }, [root, enabled, rack, data.devices, side, width, height, scale, mode]);
  if (!enabled || !layout.width) return null;
  const w = layout.width, h = layout.height;
  const organizers = cordOrganizerBoxes(rack, side, w, scale, mode);
  return <svg className="rack-cords" viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-label="Патч-корды шкафа">
    {cords.map((c, i) => {
      const a = layout.points[cordEndKey(c.a)], b = layout.points[cordEndKey(c.b)]; if (!a || !b) return null;
      const right = (a.x + b.x) / 2 > w / 2, o0 = organizers[0];
      // with organizers the channel hugs their side (inside the rails), otherwise the old outer lane
      const lane = o0 ? (right ? o0.x + o0.width + (5 + i % 5 * 2.2) * scale : o0.x - (5 + i % 5 * 2.2) * scale) : cordLane(w, i, right, scale);
      const paths = cordRoute(a, b, organizers, lane, scale, i), title = cordEndLabel(c.a, rack, data) + ' ↔ ' + cordEndLabel(c.b, rack, data);
      return <g key={c.key} className="rack-cord" style={{ '--cord': c.color }}>
        <title>{title}</title>
        {paths.map((d, j) => <g key={j}><path d={d} className="cord-shadow" strokeWidth={6 * scale} /><path d={d} className="cord-body" strokeWidth={3.8 * scale} /><path d={d} className="cord-light" strokeWidth={.9 * scale} />
          {onPick ? <path d={d} className="cord-hit" strokeWidth={Math.max(12, 16 * scale)} onPointerDown={e => e.stopPropagation()} onClick={e => { e.stopPropagation(); onPick(c.key); }} /> : null}</g>)}
        {[a, b].map((p, j) => <g key={j}><rect x={p.x - 3 * scale} y={p.y - 2 * scale} width={6 * scale} height={7 * scale} rx={1.5 * scale} fill={c.color} stroke="#17202a" strokeWidth={scale} /><path d={`M${p.x - 1.5 * scale},${p.y}h${3 * scale}`} stroke="#fff" strokeOpacity=".5" strokeWidth={scale} /></g>)}
      </g>;
    })}
  </svg>;
}

function RackCordSettings({ rack, onClose }) {
  const { data, edit, saveRack } = useApp();
  const [colors, setColors] = useState({ ...(rack.cordColors || {}) });
  const colorsRef = useRef(colors);
  const setColor = (key, value) => {
    if (!/^#[0-9a-f]{6}$/i.test(value)) return;
    colorsRef.current = { ...colorsRef.current, [key]: value.toLowerCase() };
    setColors(colorsRef.current);
  };
  const cords = rackCords({ ...rack, cordColors: colors }, data);
  if (!edit || !data.authed) return null;
  const save = async () => {
    const latest = data.racks.find(r => r.id === rack.id) || rack;
    await saveRack({ ...latest, cordColors: colorsRef.current });
    onClose();
  };
  return <Modal title="Цвета патч-кордов" onClose={onClose} wide icon={<Icon name="link" />}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Выберите цвет для каждого корда. Соединения берутся из уже указанных связей портов.</div>
    {!cords.length ? <div className="cord-empty">Пока нет настроенных соединений между портами этого шкафа.</div> : <div className="cord-list">{cords.map(c => <div key={c.key} className="cord-row">
      <span className="cord-swatch" style={{ background: c.color }} /><div className="grow" style={{ minWidth: 0 }}><b>{cordEndLabel(c.a, rack, data)}</b><small>↔ {cordEndLabel(c.b, rack, data)}</small><div className="cord-palette">{CORD_COLORS.map(color => <button key={color} type="button" aria-label={cordEndLabel(c.a, rack, data) + ': цвет ' + color} title={color} className={c.color === color ? 'on' : ''} style={{ '--swatch': color }} onClick={() => setColor(c.key, color)} />)}</div></div>
      <input type="color" aria-label={'Цвет: ' + cordEndLabel(c.a, rack, data)} value={c.color} onInput={e => setColor(c.key, e.currentTarget.value)} onChange={e => setColor(c.key, e.currentTarget.value)} />
    </div>)}</div>}
    <div className="row" style={{ justifyContent: 'flex-end', marginTop: 18 }}><Btn onClick={onClose}>Отмена</Btn><Btn kind="primary" onClick={save}>Сохранить</Btn></div>
  </Modal>;
}
