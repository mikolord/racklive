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
function cordRoute(a, b, organizers, lane, k = 1) {
  const lo = Math.min(a.y, b.y), hi = Math.max(a.y, b.y);
  const between = organizers.filter(o => o.y > lo + 2 * k && o.y < hi - 2 * k);
  if (organizers.length) {
    const candidates = between.length ? between : organizers;
    const near = p => candidates.reduce((best, o) => Math.abs(o.y - p.y) < Math.abs(best.y - p.y) ? o : best);
    const oa = near(a), ob = near(b);
    const into = (p, o) => {
      // Terminate at the organizer's lip: its whole face stays above the cable,
      // including the transparent click target, without covering the panel itself.
      const edgeY = o.top == null ? o.y : p.y < o.y ? o.top : o.top + o.height;
      const edgeX = o.x == null ? p.x : lane > o.x + o.width / 2 ? o.x + o.width : o.x;
      const direction = Math.sign(edgeY - p.y), span = Math.abs(edgeY - p.y);
      if (Math.abs(p.y - o.y) <= 80 * k) {
        const bow = Math.sign(lane - p.x) * Math.min(8 * k, span * .2);
        const x = o.x == null ? p.x + bow : Math.max(o.x + 2 * k, Math.min(o.x + o.width - 2 * k, p.x + bow));
        return `M${p.x},${p.y}C${p.x},${p.y + direction * span * .4} ${x},${edgeY - direction * span * .3} ${x},${edgeY}`;
      }
      const lead = Math.sign(o.y - p.y) * 24 * k;
      return roundedCord([[p.x, p.y], [p.x, p.y + lead], [lane, p.y + lead], [lane, o.y], [edgeX, o.y]], 22 * k);
    };
    const paths = [into(a, oa), into(b, ob)];
    if (oa !== ob) paths.push(roundedCord([[lane, oa.y], [lane, ob.y]], 22 * k));
    return paths.filter(Boolean);
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
      const lane = cordLane(w, i, (a.x + b.x) / 2 > w / 2, scale);
      const paths = cordRoute(a, b, organizers, lane, scale), title = cordEndLabel(c.a, rack, data) + ' ↔ ' + cordEndLabel(c.b, rack, data);
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
