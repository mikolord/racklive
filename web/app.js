/* ── 00_core.jsx ── */
/* Core: API client, formatting helpers, icons. Files in src/ are concatenated in name order. */
const {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  createContext,
  useContext,
  Fragment
} = React;
async function api(path, opts = {}) {
  const init = {
    method: opts.method || 'GET',
    headers: {},
    credentials: 'same-origin'
  };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  const r = await fetch(path, init);
  let data = null;
  try {
    data = await r.json();
  } catch (e) {/* empty body */}
  if (!r.ok) {
    const err = new Error(data && data.error || 'Ошибка ' + r.status);
    err.status = r.status;
    throw err;
  }
  return data;
}
const fmt = {
  uptime(s) {
    if (s == null || isNaN(s)) return '—';
    s = Math.floor(s);
    const d = Math.floor(s / 86400),
      h = Math.floor(s % 86400 / 3600),
      m = Math.floor(s % 3600 / 60);
    if (d) return `${d} д ${h} ч`;
    if (h) return `${h} ч ${m} мин`;
    return `${m} мин`;
  },
  ago(t, now) {
    if (!t) return 'никогда';
    const s = Math.max(0, Math.round((now || Date.now() / 1000) - t));
    if (s < 10) return 'только что';
    if (s < 60) return `${s} с назад`;
    if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
    if (s < 86400) return `${Math.floor(s / 3600)} ч назад`;
    return new Date(t * 1000).toLocaleDateString('ru-RU');
  },
  time(t) {
    return t ? new Date(t * 1000).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }) : '—';
  },
  speed(m) {
    if (!m) return '—';
    if (m >= 1000) return m / 1000 + ' Гбит';
    return m + ' Мбит';
  },
  speedShort(m) {
    if (!m) return '';
    if (m >= 1000) return m / 1000 + 'G';
    return m + 'M';
  },
  bytes(b) {
    if (b == null) return '—';
    const u = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
    let i = 0;
    b = +b;
    while (b >= 1000 && i < u.length - 1) {
      b /= 1000;
      i++;
    }
    return (b >= 100 ? b.toFixed(0) : b.toFixed(1)) + ' ' + u[i];
  },
  gb(g) {
    return g >= 1000 ? (g / 1000).toFixed(1) + ' ТБ' : g + ' ГБ';
  },
  pct(v) {
    return v == null ? '—' : Math.round(v) + '%';
  },
  bps(v) {
    if (v == null) return '—';
    if (v < 1000) return Math.round(v) + ' бит/с';
    if (v < 1e6) return (v / 1e3).toFixed(v < 1e4 ? 1 : 0) + ' Кбит/с';
    if (v < 1e9) return (v / 1e6).toFixed(v < 1e7 ? 1 : 0) + ' Мбит/с';
    return (v / 1e9).toFixed(2) + ' Гбит/с';
  }
};
const speedClass = p => !p || !p.link ? '' : p.speed >= 1000 ? 'g' : p.speed >= 100 ? 'y' : 'o';
const speedColor = (s, kind) => {
  if (kind === 'wifi') return 'var(--accent)';
  if (kind === 'wan' || kind === 'remote') return 'var(--purple)';
  if (kind === 'mesh') return 'var(--teal)';
  if (kind === 'manual' || kind === 'lan') return 'var(--text3)';
  if (!s) return 'var(--text3)';
  return s >= 1000 ? 'var(--green)' : s >= 100 ? 'var(--yellow)' : 'var(--orange)';
};
const STATUS_TEXT = {
  online: 'В сети',
  warning: 'Внимание',
  offline: 'Нет связи',
  unknown: 'Ожидание'
};
const KIND_TEXT = {
  router: 'Маршрутизатор',
  switch: 'Коммутатор',
  server: 'Сервер',
  nas: 'NAS',
  ap: 'Точка доступа',
  camera: 'Камера',
  phone: 'Телефон',
  tablet: 'Планшет',
  tv: 'Телевизор',
  laptop: 'Ноутбук',
  pc: 'Компьютер',
  printer: 'Принтер',
  speaker: 'Колонка',
  iot: 'Умное устройство',
  internet: 'Интернет',
  web: 'Сайт',
  other: 'Другое',
  ups: 'ИБП',
  patch: 'Патч-панель',
  cross: 'Оптический кросс',
  pdu: 'Блок розеток',
  shelf: 'Полка',
  blank: 'Заглушка',
  organizer: 'Органайзер',
  nvr: 'Видеорегистратор',
  modem: 'Модем / ONT'
};
const UNIT_TYPES = ['router', 'switch', 'server', 'nas', 'nvr', 'ups', 'patch', 'cross', 'pdu', 'shelf', 'organizer', 'modem', 'blank', 'other'];
const PASSIVE = ['patch', 'cross', 'pdu', 'shelf', 'organizer', 'blank'];
const DEVICE_KINDS = ['router', 'switch', 'server', 'nas', 'ap', 'camera', 'nvr', 'ups', 'pc', 'laptop', 'phone', 'tv', 'printer', 'iot', 'web', 'modem', 'other'];

/* Icons: 24x24 stroke paths (SF Symbols-like). */
const ICON_PATHS = {
  router: 'M3 14h18v5H3zM7 16.5h.01M10 16.5h.01M8 10a6 6 0 0 1 8 0M5.5 7.5a10 10 0 0 1 13 0M12 14v-2',
  switch: 'M2 8h20v8H2zM5 11h2v2H5zM9 11h2v2H9zM13 11h2v2h-2zM17 11h2v2h-2z',
  server: 'M3 4h18v6H3zM3 14h18v6H3zM7 7h.01M7 17h.01M11 7h6M11 17h6',
  nas: 'M5 3h14v18H5zM8 7h8M8 11h8M9 17h.01M12 17h.01M15 17h.01',
  ap: 'M12 20h.01M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 14 0M1.5 9.5a15 15 0 0 1 21 0',
  camera: 'M3 7h13v10H3zM16 10l5-3v10l-5-3M7 12h.01',
  nvr: 'M2 6h20v12H2zM6 10h4v4H6zM14 10h4M14 14h4',
  phone: 'M7 2h10v20H7zM11 18h2',
  tablet: 'M4 3h16v18H4zM11 18h2',
  tv: 'M3 5h18v12H3zM8 21h8M12 17v4',
  laptop: 'M5 5h14v10H5zM2 19h20',
  pc: 'M3 4h18v12H3zM8 20h8M12 16v4',
  printer: 'M6 9V3h12v6M6 18H4v-7h16v7h-2M6 14h12v7H6z',
  speaker: 'M7 3h10v18H7zM12 15a3 3 0 1 0 0-.01M12 7h.01',
  iot: 'M9 9h6v6H9zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3M5 5h14v14H5z',
  internet: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20',
  web: 'M3 4h18v16H3zM3 9h18M7 6.5h.01M10 6.5h.01',
  ups: 'M4 5h16v14H4zM13 8l-3 4h4l-3 4',
  patch: 'M2 9h20v6H2zM5 11h2v2H5zM9 11h2v2H9zM13 11h2v2h-2zM17 11h2v2h-2z',
  cross: 'M2 9h20v6H2zM6 12h.01M10 12h.01M14 12h.01M18 12h.01',
  pdu: 'M2 9h20v6H2zM6 11v2M8 11v2M12 11v2M14 11v2M18 11v2',
  shelf: 'M3 15h18M5 15v4M19 15v4M7 15v-5h6v5',
  organizer: 'M2 10h20v4H2zM6 10v4M10 10v4M14 10v4M18 10v4',
  blank: 'M3 10h18v4H3z',
  modem: 'M4 13h16v6H4zM8 16h.01M12 13l-2-7M12 13l2-7',
  other: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 8v5M12 16h.01',
  edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  plus: 'M12 5v14M5 12h14',
  x: 'M6 6l12 12M18 6L6 18',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14M20 20l-4-4',
  settings: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  rack: 'M5 2h14v20H5zM5 7h14M5 12h14M5 17h14M8 4.5h.01M8 9.5h.01M8 14.5h.01M8 19.5h.01',
  map: 'M5 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4M19 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4M12 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4M6.5 7.5l4.5 8M17.5 7.5l-4.5 8M7 6h10',
  list: 'M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01',
  bell: 'M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  bolt: 'M13 2L4 14h7l-1 8 9-12h-7z',
  refresh: 'M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5',
  power: 'M12 2v10M5.6 6.6a9 9 0 1 0 12.8 0',
  link: 'M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1',
  fit: 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5',
  lock: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4',
  logout: 'M15 4h4v16h-4M10 17l5-5-5-5M15 12H3',
  sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z',
  chevron: 'M9 6l6 6-6 6',
  download: 'M12 3v12M7 10l5 5 5-5M4 21h16',
  upload: 'M12 21V9M7 14l5-5 5 5M4 3h16',
  check: 'M5 12l5 5 9-11',
  wifi: 'M12 20h.01M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 14 0',
  globe: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20',
  pulse: 'M2 12h4l3-8 4 16 3-8h6',
  cable: 'M4 4h5v5H4zM6.5 9v4a4 4 0 0 0 4 4h3a4 4 0 0 1 4 4M5.5 4V2M7.5 4V2',
  alert: 'M12 3L2 20h20zM12 10v4M12 17h.01',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  toggle: 'M7 7h10a5 5 0 0 1 0 10H7A5 5 0 0 1 7 7M7 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6'
};
function Icon({
  name,
  size = 18,
  color = 'currentColor',
  stroke = 1.8,
  style
}) {
  const d = ICON_PATHS[name] || ICON_PATHS.other;
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: color,
    strokeWidth: stroke,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: style
  }, d.split('M').filter(Boolean).map((p, i) => /*#__PURE__*/React.createElement("path", {
    key: i,
    d: 'M' + p
  })));
}
const KIND_COLOR = {
  router: '#0a84ff',
  switch: '#30d158',
  server: '#5e5ce6',
  nas: '#64d2ff',
  ap: '#40c8e0',
  camera: '#ff453a',
  nvr: '#ff375f',
  phone: '#8e8e93',
  tablet: '#8e8e93',
  tv: '#bf5af2',
  laptop: '#8e8e93',
  pc: '#ac8e68',
  printer: '#8e8e93',
  speaker: '#ff9f0a',
  iot: '#ffd60a',
  internet: '#bf5af2',
  web: '#5e5ce6',
  ups: '#ff9f0a',
  patch: '#8e8e93',
  cross: '#64d2ff',
  pdu: '#ff9f0a',
  modem: '#bf5af2',
  other: '#8e8e93'
};
function KindIcon({
  kind,
  size = 36,
  round = 10
}) {
  const c = KIND_COLOR[kind] || KIND_COLOR.other;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: size,
      height: size,
      borderRadius: round,
      display: 'grid',
      placeItems: 'center',
      flexShrink: 0,
      background: `color-mix(in srgb, ${c} 16%, transparent)`
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: kind,
    size: size * .54,
    color: c
  }));
}
const ToastCtx = createContext(() => {});
const useToast = () => useContext(ToastCtx);
function ToastHost({
  children
}) {
  const [items, setItems] = useState([]);
  const push = useCallback((text, err) => {
    const id = Math.random();
    setItems(x => [...x, {
      id,
      text,
      err
    }]);
    setTimeout(() => setItems(x => x.filter(i => i.id !== id)), err ? 5000 : 2600);
  }, []);
  return /*#__PURE__*/React.createElement(ToastCtx.Provider, {
    value: push
  }, children, /*#__PURE__*/React.createElement("div", {
    className: "toast-wrap"
  }, items.map(i => /*#__PURE__*/React.createElement("div", {
    key: i.id,
    className: 'toast' + (i.err ? ' err' : '')
  }, /*#__PURE__*/React.createElement(Icon, {
    name: i.err ? 'x' : 'check',
    size: 16
  }), i.text))));
}
const AppCtx = createContext(null);
const useApp = () => useContext(AppCtx);

/* ── 10_ui.jsx ── */
/* UI kit */
function Btn({
  children,
  kind = '',
  size = '',
  icon,
  busy,
  onClick,
  disabled,
  title,
  type = 'button',
  style
}) {
  const [self, setSelf] = useState(false);
  const click = async e => {
    if (!onClick) return;
    const r = onClick(e);
    if (r && r.then) {
      setSelf(true);
      try {
        await r;
      } finally {
        setSelf(false);
      }
    }
  };
  const cls = ['btn', kind, size, busy || self ? 'busy' : '', !children && icon ? 'icon' : ''].join(' ');
  return /*#__PURE__*/React.createElement("button", {
    type: type,
    className: cls,
    onClick: click,
    disabled: disabled,
    title: title,
    style: style
  }, icon && !(busy || self) ? /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: size === 'sm' ? 15 : 17
  }) : null, children);
}
function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
  icon
}) {
  useEffect(() => {
    const h = e => e.key === 'Escape' && onClose && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return /*#__PURE__*/React.createElement("div", {
    className: "overlay",
    onMouseDown: e => e.target === e.currentTarget && onClose && onClose()
  }, /*#__PURE__*/React.createElement("div", {
    className: 'modal' + (wide ? ' wide' : '')
  }, /*#__PURE__*/React.createElement("div", {
    className: "modal-head"
  }, icon, /*#__PURE__*/React.createElement("h3", null, title), onClose ? /*#__PURE__*/React.createElement(Btn, {
    icon: "x",
    size: "sm",
    onClick: onClose
  }) : null), /*#__PURE__*/React.createElement("div", {
    className: "modal-body"
  }, children), footer ? /*#__PURE__*/React.createElement("div", {
    className: "modal-foot"
  }, footer) : null));
}
function Sheet({
  onClose,
  head,
  tabs,
  tab,
  setTab,
  children
}) {
  useEffect(() => {
    const h = e => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return /*#__PURE__*/React.createElement("div", {
    className: "overlay",
    onMouseDown: e => e.target === e.currentTarget && onClose()
  }, /*#__PURE__*/React.createElement("div", {
    className: "sheet"
  }, /*#__PURE__*/React.createElement("div", {
    className: "sheet-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, head), /*#__PURE__*/React.createElement(Btn, {
    icon: "x",
    size: "sm",
    onClick: onClose
  })), tabs && tabs.length > 1 ? /*#__PURE__*/React.createElement("div", {
    className: "sheet-tabs"
  }, tabs.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    className: tab === t.id ? 'on' : '',
    onClick: () => setTab(t.id)
  }, t.label))) : /*#__PURE__*/React.createElement("div", {
    style: {
      height: 12,
      borderBottom: '.5px solid var(--line)'
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "sheet-body"
  }, children)));
}
function Field({
  label,
  hint,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "field"
  }, label ? /*#__PURE__*/React.createElement("label", null, label) : null, children, hint ? /*#__PURE__*/React.createElement("div", {
    className: "hint"
  }, hint) : null);
}
function Switch({
  on,
  onChange,
  disabled
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: 'switch' + (on ? ' on' : ''),
    onClick: () => !disabled && onChange(!on),
    "aria-pressed": on
  });
}
function Seg({
  value,
  options,
  onChange,
  className = ''
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: 'seg ' + className
  }, options.map(o => /*#__PURE__*/React.createElement("button", {
    key: o.value,
    className: (value === o.value ? 'on ' : '') + (o.cls || ''),
    onClick: () => onChange(o.value),
    title: o.label
  }, o.icon ? /*#__PURE__*/React.createElement(Icon, {
    name: o.icon,
    size: 14
  }) : null, /*#__PURE__*/React.createElement("span", {
    className: o.icon ? 'seg-label' : ''
  }, o.label))));
}
function StatusBadge({
  status,
  text
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: 'badge ' + (status || '')
  }, /*#__PURE__*/React.createElement("span", {
    className: 'dot ' + (status || '')
  }), text || STATUS_TEXT[status] || status);
}
function Sparkline({
  points,
  field,
  color = 'var(--accent)'
}) {
  const vals = (points || []).map(p => p[field]).filter(v => typeof v === 'number');
  if (vals.length < 3) return null;
  const max = Math.max(...vals, 1),
    min = Math.min(...vals, 0),
    w = 120,
    h = 34;
  const d = vals.map((v, i) => `${i ? 'L' : 'M'}${i / (vals.length - 1) * w},${h - 3 - (v - min) / (max - min || 1) * (h - 8)}`).join(' ');
  return /*#__PURE__*/React.createElement("svg", {
    className: "spark",
    viewBox: `0 0 ${w} ${h}`,
    preserveAspectRatio: "none"
  }, /*#__PURE__*/React.createElement("path", {
    d: d + ` L${w},${h} L0,${h} Z`,
    fill: color,
    opacity: ".15"
  }), /*#__PURE__*/React.createElement("path", {
    d: d,
    fill: "none",
    stroke: color,
    strokeWidth: "1.5"
  }));
}
function Stat({
  k,
  v,
  unit,
  level,
  spark,
  sparkField,
  color
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: 'stat ' + (level === 'warn' ? 'warn' : level === 'bad' ? 'bad' : '')
  }, spark ? /*#__PURE__*/React.createElement(Sparkline, {
    points: spark,
    field: sparkField,
    color: color
  }) : null, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "k"
  }, k), /*#__PURE__*/React.createElement("div", {
    className: "v"
  }, v == null || v === '' ? '—' : v, unit ? /*#__PURE__*/React.createElement("small", null, unit) : null)));
}
function Bar({
  value,
  warnAt = 80,
  badAt = 92
}) {
  const v = Math.max(0, Math.min(100, value || 0));
  return /*#__PURE__*/React.createElement("div", {
    className: 'bar ' + (v >= badAt ? 'bad' : v >= warnAt ? 'warn' : '')
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: v + '%'
    }
  }));
}
function KV({
  rows
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "kv"
  }, rows.map(([k, v], i) => /*#__PURE__*/React.createElement(Fragment, {
    key: i
  }, /*#__PURE__*/React.createElement("div", null, k), /*#__PURE__*/React.createElement("div", null, v == null || v === '' ? '—' : v))));
}
function Card({
  title,
  right,
  children,
  pad = true,
  className = '',
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: 'card ' + (pad ? 'pad ' : '') + className,
    style: style
  }, title ? /*#__PURE__*/React.createElement("div", {
    className: "card-title"
  }, /*#__PURE__*/React.createElement("span", {
    className: "grow"
  }, title), right) : null, children);
}
function SearchBox({
  value,
  onChange,
  placeholder = 'Поиск'
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "search"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 15
  }), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: value,
    placeholder: placeholder,
    onChange: e => onChange(e.target.value)
  }));
}

/* Promise-based confirm dialog */
const ConfirmCtx = createContext(null);
function ConfirmHost({
  children
}) {
  const [q, setQ] = useState(null);
  const ask = useCallback((text, opts = {}) => new Promise(res => setQ({
    text,
    opts,
    res
  })), []);
  const done = v => {
    q.res(v);
    setQ(null);
  };
  return /*#__PURE__*/React.createElement(ConfirmCtx.Provider, {
    value: ask
  }, children, q ? /*#__PURE__*/React.createElement(Modal, {
    title: q.opts.title || 'Подтвердите',
    onClose: () => done(false),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Btn, {
      onClick: () => done(false)
    }, "\u041E\u0442\u043C\u0435\u043D\u0430"), /*#__PURE__*/React.createElement(Btn, {
      kind: q.opts.danger ? 'danger' : 'primary',
      onClick: () => done(true)
    }, q.opts.ok || 'Продолжить'))
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      lineHeight: 1.45
    }
  }, q.text)) : null);
}
const useConfirm = () => useContext(ConfirmCtx);
function useHistory(deviceId, enabled, port) {
  const [h, setH] = useState(null);
  useEffect(() => {
    if (!enabled || !deviceId) return;
    let alive = true;
    setH(null);
    const load = () => api('/api/history/' + deviceId + (port ? '?port=' + port : '')).then(x => alive && setH(x)).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [deviceId, enabled, port]);
  return h;
}

/* Two-series area chart for 24h traffic (bits/s) */
function TrafficChart({
  points
}) {
  const [hover, setHover] = useState(null);
  const pts = (points || []).filter(p => p.rx != null);
  if (pts.length < 2) return /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 13,
      padding: '18px 0',
      textAlign: 'center'
    }
  }, "\u0413\u0440\u0430\u0444\u0438\u043A \u043F\u043E\u044F\u0432\u0438\u0442\u0441\u044F \u0447\u0435\u0440\u0435\u0437 \u043D\u0435\u0441\u043A\u043E\u043B\u044C\u043A\u043E \u043C\u0438\u043D\u0443\u0442 \u2014 \u0434\u0430\u043D\u043D\u044B\u0435 \u043A\u043E\u043F\u044F\u0442\u0441\u044F \u0441 \u043A\u0430\u0436\u0434\u044B\u043C \u043E\u043F\u0440\u043E\u0441\u043E\u043C");
  const W = 600,
    H = 150,
    pad = 4,
    t0 = pts[0].t,
    t1 = pts[pts.length - 1].t;
  const max = Math.max(1000, ...pts.map(p => Math.max(p.rx, p.tx))) * 1.1;
  const X = t => pad + (t - t0) / Math.max(1, t1 - t0) * (W - pad * 2),
    Y = v => H - 18 - v / max * (H - 30);
  const line = k => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p[k]).toFixed(1)}`).join(' ');
  const area = k => line(k) + ` L${X(t1)},${H - 18} L${X(t0)},${H - 18} Z`;
  const hp = hover != null ? pts[hover] : pts[pts.length - 1];
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = t0 + (e.clientX - r.left) / r.width * (t1 - t0);
    let best = 0;
    pts.forEach((p, i) => {
      if (Math.abs(p.t - t) < Math.abs(pts[best].t - t)) best = i;
    });
    setHover(best);
  };
  const ticks = [0, .25, .5, .75, 1].map(f => t0 + (t1 - t0) * f);
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "row wrap",
    style: {
      gap: '4px 16px',
      fontSize: 13,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 6,
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: 10,
      height: 10,
      borderRadius: 3,
      background: 'var(--accent)'
    }
  }), "\u041A \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0443 ", /*#__PURE__*/React.createElement("b", null, fmt.bps(hp.tx))), /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 6,
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: 10,
      height: 10,
      borderRadius: 3,
      background: 'var(--green)'
    }
  }), "\u041E\u0442 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 ", /*#__PURE__*/React.createElement("b", null, fmt.bps(hp.rx))), /*#__PURE__*/React.createElement("span", {
    className: "grow"
  }), /*#__PURE__*/React.createElement("span", {
    className: "dim3",
    style: {
      whiteSpace: 'nowrap'
    }
  }, new Date(hp.t * 1000).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit'
  }))), /*#__PURE__*/React.createElement("svg", {
    className: "chart",
    viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: "none",
    onPointerMove: onMove,
    onPointerLeave: () => setHover(null)
  }, [.25, .5, .75].map(f => /*#__PURE__*/React.createElement("line", {
    key: f,
    x1: 0,
    x2: W,
    y1: Y(max / 1.1 * f),
    y2: Y(max / 1.1 * f),
    stroke: "var(--line)"
  })), /*#__PURE__*/React.createElement("path", {
    d: area('tx'),
    fill: "var(--accent)",
    opacity: ".18"
  }), /*#__PURE__*/React.createElement("path", {
    d: line('tx'),
    fill: "none",
    stroke: "var(--accent)",
    strokeWidth: "1.6",
    vectorEffect: "non-scaling-stroke"
  }), /*#__PURE__*/React.createElement("path", {
    d: area('rx'),
    fill: "var(--green)",
    opacity: ".15"
  }), /*#__PURE__*/React.createElement("path", {
    d: line('rx'),
    fill: "none",
    stroke: "var(--green)",
    strokeWidth: "1.6",
    vectorEffect: "non-scaling-stroke"
  }), hover != null ? /*#__PURE__*/React.createElement("line", {
    x1: X(hp.t),
    x2: X(hp.t),
    y1: 0,
    y2: H - 18,
    stroke: "var(--text3)",
    strokeDasharray: "3 3",
    vectorEffect: "non-scaling-stroke"
  }) : null), /*#__PURE__*/React.createElement("div", {
    className: "row between dim3 mono",
    style: {
      fontSize: 10.5,
      marginTop: 2
    }
  }, ticks.map((t, i) => /*#__PURE__*/React.createElement("span", {
    key: i
  }, new Date(t * 1000).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit'
  })))), /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 11.5,
      marginTop: 4
    }
  }, "\u041F\u0438\u043A \u0437\u0430 \u043F\u0435\u0440\u0438\u043E\u0434: ", fmt.bps(max / 1.1)));
}

/* ── 20_device.jsx ── */
/* Device detail sheet */
function useAction() {
  const {
    refresh,
    applyState
  } = useApp();
  const toast = useToast();
  const confirm = useConfirm();
  return async (device, action, params = {}) => {
    const text = (action.confirm || '').replace('{port}', params.port).replace('{name}', params.name || '');
    if (text && !(await confirm(text, {
      title: action.label,
      ok: action.label,
      danger: true
    }))) return false;
    if (!action.instant) toast(`${action.label}${params.port ? ' · порт ' + params.port : ''}: выполняю…`);
    try {
      const r = await api(`/api/devices/${device.id}/action`, {
        method: 'POST',
        body: {
          action: action.id,
          params
        }
      });
      if (r.state) applyState(device.id, r.state); // instant actions return the fresh device state
      if (!action.instant) toast('✓ ' + (r.message || 'Готово'));
      refresh();
      if (!action.instant && !r.cable) {
        setTimeout(refresh, 8000);
        setTimeout(refresh, 25000);
        setTimeout(refresh, 50000);
      }
      return r;
    } catch (e) {
      toast(e.message, true);
      return false;
    }
  };
}
function DeviceHead({
  device,
  drv
}) {
  const st = device.state || {};
  const s = st.summary || {};
  return /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: device.kind || drv?.kind,
    size: 46,
    round: 13
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 20,
      fontWeight: 700,
      letterSpacing: -.4
    },
    className: "ellipsis"
  }, device.name), /*#__PURE__*/React.createElement("div", {
    className: "row wrap",
    style: {
      gap: 6,
      marginTop: 3
    }
  }, /*#__PURE__*/React.createElement(StatusBadge, {
    status: st.status
  }), device.location === 'remote' ? /*#__PURE__*/React.createElement("span", {
    className: "badge info"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "globe",
    size: 12
  }), "\u0423\u0434\u0430\u043B\u0451\u043D\u043D\u043E\u0435") : null, /*#__PURE__*/React.createElement("span", {
    className: "dim",
    style: {
      fontSize: 13
    }
  }, [s.model, s.ip].filter(Boolean).join(' · ')))));
}
function DeviceSheet({
  device,
  onClose,
  initialTab,
  initialPort
}) {
  const {
    data,
    admin,
    openEditor
  } = useApp();
  const drv = data.drivers.find(d => d.id === device.driver);
  const st = device.state || {};
  const tabs = [{
    id: 'overview',
    label: 'Обзор'
  }];
  if ((st.ports || []).length) tabs.push({
    id: 'ports',
    label: `Порты · ${(st.ports || []).filter(p => p.link).length}/${st.ports.length}`
  });
  if ((st.children || []).length) tabs.push({
    id: 'children',
    label: `Точки · ${st.children.length}`
  });
  if ((st.clients || []).length) tabs.push({
    id: 'clients',
    label: `Клиенты · ${st.clients.length}`
  });
  if (st.storage) tabs.push({
    id: 'storage',
    label: 'Хранилище'
  });
  if ((st.services || []).length || (st.entities || []).length) tabs.push({
    id: 'services',
    label: st.entities ? 'Управление' : `Сервисы · ${st.services.length}`
  });
  const [tab, setTab] = useState(initialTab && tabs.find(t => t.id === initialTab) ? initialTab : 'overview');
  return /*#__PURE__*/React.createElement(Sheet, {
    onClose: onClose,
    tab: tab,
    setTab: setTab,
    tabs: tabs,
    head: /*#__PURE__*/React.createElement("div", {
      className: "col",
      style: {
        gap: 10
      }
    }, /*#__PURE__*/React.createElement(DeviceHead, {
      device: device,
      drv: drv
    }), admin ? /*#__PURE__*/React.createElement("div", {
      className: "row"
    }, /*#__PURE__*/React.createElement(Btn, {
      size: "sm",
      icon: "edit",
      onClick: () => {
        onClose();
        openEditor(device);
      }
    }, "\u041D\u0430\u0441\u0442\u0440\u043E\u0438\u0442\u044C"), /*#__PURE__*/React.createElement(PollNow, {
      device: device
    })) : null)
  }, tab === 'overview' ? /*#__PURE__*/React.createElement(Overview, {
    device: device,
    drv: drv
  }) : null, tab === 'ports' ? /*#__PURE__*/React.createElement(PortsTab, {
    device: device,
    drv: drv,
    initialPort: initialPort
  }) : null, tab === 'children' ? /*#__PURE__*/React.createElement(ChildrenTab, {
    device: device,
    drv: drv
  }) : null, tab === 'clients' ? /*#__PURE__*/React.createElement(ClientsTab, {
    clients: st.clients,
    children: st.children
  }) : null, tab === 'storage' ? /*#__PURE__*/React.createElement(StorageTab, {
    storage: st.storage
  }) : null, tab === 'services' ? /*#__PURE__*/React.createElement(ServicesTab, {
    device: device,
    drv: drv
  }) : null);
}
function PollNow({
  device
}) {
  const {
    refresh
  } = useApp();
  const toast = useToast();
  return /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "refresh",
    onClick: async () => {
      try {
        const r = await api(`/api/devices/${device.id}/poll`, {
          method: 'POST'
        });
        toast(r.state.error ? 'Ошибка: ' + r.state.error : 'Данные обновлены', !!r.state.error);
        refresh();
      } catch (e) {
        toast(e.message, true);
      }
    }
  }, "\u041E\u0431\u043D\u043E\u0432\u0438\u0442\u044C");
}
function Overview({
  device,
  drv
}) {
  const {
    admin,
    data
  } = useApp();
  const st = device.state || {};
  const s = st.summary || {};
  const hist = useHistory(device.id, true);
  const runAction = useAction();
  const stats = [];
  if (s.cpu != null) stats.push(/*#__PURE__*/React.createElement(Stat, {
    key: "cpu",
    k: "\u041F\u0440\u043E\u0446\u0435\u0441\u0441\u043E\u0440",
    v: Math.round(s.cpu),
    unit: "%",
    level: s.cpu > 85 ? 'warn' : '',
    spark: hist,
    sparkField: "cpu"
  }));
  if (s.mem != null) stats.push(/*#__PURE__*/React.createElement(Stat, {
    key: "mem",
    k: "\u041F\u0430\u043C\u044F\u0442\u044C",
    v: Math.round(s.mem),
    unit: "%",
    level: s.mem > 90 ? 'warn' : '',
    spark: hist,
    sparkField: "mem",
    color: "var(--purple)"
  }));
  if (s.temp != null) stats.push(/*#__PURE__*/React.createElement(Stat, {
    key: "temp",
    k: "\u0422\u0435\u043C\u043F\u0435\u0440\u0430\u0442\u0443\u0440\u0430",
    v: s.temp,
    unit: "\xB0C",
    level: s.temp > 65 ? 'warn' : '',
    spark: hist,
    sparkField: "temp",
    color: "var(--orange)"
  }));
  if (s.uptime != null) stats.push(/*#__PURE__*/React.createElement(Stat, {
    key: "up",
    k: "\u0410\u043F\u0442\u0430\u0439\u043C",
    v: fmt.uptime(s.uptime)
  }));
  (st.metrics || []).forEach((m, i) => stats.push(/*#__PURE__*/React.createElement(Stat, {
    key: 'm' + i,
    k: m.label,
    v: m.value,
    unit: m.unit,
    level: m.level,
    spark: m.label === 'Задержка' || m.label === 'PoE' ? hist : null,
    sparkField: m.label === 'Задержка' ? 'ms' : 'poe',
    color: "var(--green)"
  })));
  const devActions = (drv?.actions || []).filter(a => a.scope === 'device');
  return /*#__PURE__*/React.createElement(React.Fragment, null, st.error ? /*#__PURE__*/React.createElement("div", {
    className: "card pad",
    style: {
      borderColor: 'var(--red)',
      color: 'var(--red)'
    }
  }, /*#__PURE__*/React.createElement("b", null, "\u041D\u0435\u0442 \u0441\u0432\u044F\u0437\u0438:"), " ", st.error, st.updated && st.summary ? /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13,
      marginTop: 4
    }
  }, "\u041F\u043E\u043A\u0430\u0437\u0430\u043D\u044B \u043F\u043E\u0441\u043B\u0435\u0434\u043D\u0438\u0435 \u0438\u0437\u0432\u0435\u0441\u0442\u043D\u044B\u0435 \u0434\u0430\u043D\u043D\u044B\u0435") : null) : null, stats.length ? /*#__PURE__*/React.createElement("div", {
    className: "stats"
  }, stats) : null, /*#__PURE__*/React.createElement(Card, {
    title: "\u0421\u0432\u0435\u0434\u0435\u043D\u0438\u044F"
  }, /*#__PURE__*/React.createElement(KV, {
    rows: [['Модель', s.model], ['Прошивка', s.fw], ['IP-адрес', s.ip ? /*#__PURE__*/React.createElement("span", {
      className: "mono"
    }, s.ip) : null], ['MAC', s.mac ? /*#__PURE__*/React.createElement("span", {
      className: "mono"
    }, s.mac) : null], ['Тип подключения', drv?.title], ['Обновлено', st.updated ? `${fmt.ago(st.updated, data.now)} · ${st.durationMs} мс` : 'ещё не опрашивалось'], ...(device.site ? [['Площадка', device.site]] : [])]
  })), (st.sections || []).filter(x => x.rows && x.rows.length).map((sec, i) => /*#__PURE__*/React.createElement(Card, {
    key: i,
    title: sec.title
  }, /*#__PURE__*/React.createElement(KV, {
    rows: sec.rows
  }))), device.notes ? /*#__PURE__*/React.createElement(Card, {
    title: "\u0417\u0430\u043C\u0435\u0442\u043A\u0438"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      whiteSpace: 'pre-wrap',
      fontSize: 14
    }
  }, device.notes)) : null, admin && devActions.length ? /*#__PURE__*/React.createElement(Card, {
    title: "\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u044F"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row wrap"
  }, devActions.map(a => /*#__PURE__*/React.createElement(Btn, {
    key: a.id,
    kind: "danger",
    icon: "power",
    onClick: () => runAction(device, a)
  }, a.label)))) : null, /*#__PURE__*/React.createElement(EventsList, {
    events: data.events.filter(e => e.device === device.id).slice(0, 8),
    compact: true
  }));
}
function vlanColor(vid, vlans) {
  const v = (vlans || []).find(x => +x.vid === +vid);
  return v ? v.color : 'var(--text3)';
}
function vlanName(vid, vlans) {
  const v = (vlans || []).find(x => +x.vid === +vid);
  return v ? v.name : 'VLAN ' + vid;
}
function Faceplate({
  ports,
  sel,
  onSel,
  vlans
}) {
  const rj = ports.filter(p => p.kind !== 'sfp'),
    sfp = ports.filter(p => p.kind === 'sfp');
  const two = rj.length > 8;
  const P = p => /*#__PURE__*/React.createElement("div", {
    key: p.n,
    className: ['port', speedClass(p), p.kind, p.disabled ? 'dis' : '', sel === p.n ? 'sel' : ''].join(' '),
    onClick: () => onSel(p.n),
    title: `${p.n}: ${p.label || ''} ${p.link ? fmt.speedShort(p.speed) : 'нет линка'}`
  }, p.n, p.poeW > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "poe"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "bolt",
    size: 9,
    color: "#000",
    stroke: 2.4
  })) : null, p.link ? /*#__PURE__*/React.createElement("span", {
    className: "vl"
  }, [...(p.vlansU || []), ...(p.vlansT || [])].slice(0, 4).map((v, i) => /*#__PURE__*/React.createElement("b", {
    key: i,
    style: {
      background: vlanColor(v, vlans)
    }
  }))) : null);
  return /*#__PURE__*/React.createElement("div", {
    className: "faceplate"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 14,
      alignItems: 'flex-end'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: 'ports' + (two ? '' : ' one')
  }, rj.map(P)), sfp.length ? /*#__PURE__*/React.createElement("div", {
    className: "ports",
    style: {
      gridTemplateRows: 'repeat(2, auto)'
    }
  }, sfp.map(P)) : null));
}

/* Cable test: four twisted pairs drawn to scale, with the fault position marked */
const PAIR_COLOR = {
  A: '#ff9f0a',
  B: '#30d158',
  C: '#0a84ff',
  D: '#a2845e'
};
const CABLE_ST = {
  normal: ['норма', 'online'],
  open: ['обрыв', 'offline'],
  short: ['замыкание', 'offline'],
  impedance: ['плохое сопротивление', 'warning'],
  crosstalk: ['наводки', 'warning'],
  unknown: ['не измерено', '']
};
const CABLE_VERDICT = {
  ok: ['var(--green)', 'check'],
  warn: ['var(--orange)', 'alert'],
  bad: ['var(--red)', 'alert'],
  empty: ['var(--text2)', 'cable'],
  unknown: ['var(--text2)', 'other']
};
function CableResult({
  c,
  now
}) {
  const far = Math.max(c.length || 0, ...c.pairs.map(p => p.len || 0));
  const scale = Math.max(10, Math.ceil(far * 1.15 / 5) * 5);
  const [col, icon] = CABLE_VERDICT[c.verdict] || CABLE_VERDICT.unknown;
  return /*#__PURE__*/React.createElement("div", {
    className: "cable"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 8,
      fontWeight: 650,
      color: col,
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 17
  }), /*#__PURE__*/React.createElement("span", null, c.text)), /*#__PURE__*/React.createElement("div", {
    className: "cable-pairs"
  }, c.pairs.map(p => {
    const [t, s] = CABLE_ST[p.status] || [p.status, ''];
    const ok = p.status === 'normal';
    const pos = p.len != null ? Math.min(100, p.len / scale * 100) : null;
    const w = ok ? pos != null ? pos : 100 : pos || 0;
    return /*#__PURE__*/React.createElement("div", {
      key: p.pair,
      className: "cable-pair"
    }, /*#__PURE__*/React.createElement("div", {
      className: "cp-name"
    }, /*#__PURE__*/React.createElement("b", null, p.pair), /*#__PURE__*/React.createElement("span", {
      className: "mono"
    }, p.pins)), /*#__PURE__*/React.createElement("div", {
      className: "cp-wire"
    }, /*#__PURE__*/React.createElement("i", {
      className: ok ? '' : 'broken',
      style: {
        width: Math.max(w, 1.5) + '%',
        '--c': PAIR_COLOR[p.pair]
      }
    }), !ok && p.status !== 'unknown' ? /*#__PURE__*/React.createElement("span", {
      className: 'cp-x ' + s,
      style: {
        left: w + '%'
      }
    }) : null), /*#__PURE__*/React.createElement("div", {
      className: "cp-st"
    }, /*#__PURE__*/React.createElement("span", {
      className: 'dot ' + s
    }), t, p.len != null ? /*#__PURE__*/React.createElement("span", {
      className: "dim3"
    }, " \xB7 ", p.len, " \u043C") : null));
  }), /*#__PURE__*/React.createElement("div", {
    className: "cable-pair cp-ruler"
  }, /*#__PURE__*/React.createElement("div", null), /*#__PURE__*/React.createElement("div", {
    className: "row between mono"
  }, /*#__PURE__*/React.createElement("span", null, "\u043A\u043E\u043C\u043C\u0443\u0442\u0430\u0442\u043E\u0440"), /*#__PURE__*/React.createElement("span", null, Math.round(scale / 2), " \u043C"), /*#__PURE__*/React.createElement("span", null, scale, " \u043C")), /*#__PURE__*/React.createElement("div", null))), (c.details || []).length ? /*#__PURE__*/React.createElement("ul", {
    className: "cable-details"
  }, c.details.map((d, i) => /*#__PURE__*/React.createElement("li", {
    key: i
  }, d))) : null, c.hint ? /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13
    }
  }, c.hint) : null, /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 11.5
    }
  }, "\u0418\u0437\u043C\u0435\u0440\u0435\u043D\u043E ", fmt.ago(c.t, now), c.link ? ` · линк ${fmt.speedShort(c.speed)}` : '', " \xB7 \u0442\u043E\u0447\u043D\u043E\u0441\u0442\u044C \xB15\u201310 \u043C"));
}
function PortsTab({
  device,
  drv,
  initialPort
}) {
  const {
    data,
    admin
  } = useApp();
  const ports = device.state.ports || [];
  const vlans = data.settings.vlans || [];
  const [sel, setSel] = useState(initialPort || (ports.find(p => p.link) || ports[0] || {}).n);
  const p = ports.find(x => x.n === sel);
  const runAction = useAction();
  const hasTraffic = ports.some(x => x.rxBytes != null);
  const [restarted, setRestarted] = useState({}); // port -> timestamp of a successful restart
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick(x => x + 1), 5000);
    return () => clearInterval(t);
  }, []);
  const rebooting = n => {
    const ts = restarted[n];
    if (!ts) return false;
    const age = Date.now() - ts;
    const port = ports.find(x => x.n === n);
    return age < 150000 && !(port && port.link && age > 30000);
  };
  const doPortAction = async (a, n) => {
    if (await runAction(device, a, {
      port: n
    })) setRestarted(r => ({
      ...r,
      [n]: Date.now()
    }));
  };
  const [cableRes, setCableRes] = useState({}); // port -> fresh test result (until the next refresh brings it)
  const [testing, setTesting] = useState(null);
  const doCableTest = async (a, n) => {
    setTesting(n);
    try {
      const r = await runAction(device, a, {
        port: n
      });
      if (r && r.cable) setCableRes(c => ({
        ...c,
        [n]: r.cable
      }));
    } finally {
      setTesting(null);
    }
  };
  const traffic = useHistory(device.id, hasTraffic && p && p.rxBytes != null, sel);
  const allPortActions = (drv?.actions || []).filter(a => a.scope === 'port' && (!a.needs || a.needs === 'poe' && p && p.poe));
  const portActions = allPortActions.filter(a => a.kind !== 'cable'),
    cableAction = allPortActions.find(a => a.kind === 'cable');
  const cab = p ? cableRes[p.n] && (!p.cable || cableRes[p.n].t >= p.cable.t) ? cableRes[p.n] : p.cable : null;
  const slow = p && p.link && p.kind !== 'sfp' && p.speed > 0 && p.speed < 1000 && ports.some(x => x.speed >= 1000);
  const used = [...new Set(ports.flatMap(x => [...(x.vlansU || []), ...(x.vlansT || [])]))].sort((a, b) => a - b);
  const totalPoe = ports.reduce((a, x) => a + (x.poeW || 0), 0);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Faceplate, {
    ports: ports,
    sel: sel,
    onSel: setSel,
    vlans: vlans
  }), /*#__PURE__*/React.createElement("div", {
    className: "legend"
  }, /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: 'var(--green)'
    }
  }), "1 \u0413\u0431\u0438\u0442+"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: '#ffd60a'
    }
  }), "100 \u041C\u0431\u0438\u0442"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: '#ff9f0a'
    }
  }), "10 \u041C\u0431\u0438\u0442"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: '#48484a'
    }
  }), "\u043D\u0435\u0442 \u043B\u0438\u043D\u043A\u0430"), totalPoe ? /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement(Icon, {
    name: "bolt",
    size: 13,
    color: "#ffd60a"
  }), "PoE ", totalPoe.toFixed(1), " \u0412\u0442") : null, used.map(v => /*#__PURE__*/React.createElement("span", {
    key: v
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      background: vlanColor(v, vlans)
    }
  }), vlanName(v, vlans)))), p ? /*#__PURE__*/React.createElement(Card, {
    title: `Порт ${p.n}${p.label ? ' · ' + p.label : ''}`,
    right: rebooting(p.n) ? /*#__PURE__*/React.createElement("span", {
      className: "badge warning"
    }, /*#__PURE__*/React.createElement("span", {
      className: "spin-dot"
    }), "\u041F\u0435\u0440\u0435\u0437\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u0442\u0441\u044F\u2026") : /*#__PURE__*/React.createElement(StatusBadge, {
      status: p.disabled ? 'offline' : p.link ? 'online' : '',
      text: p.disabled ? 'Выключен' : p.link ? 'Линк' : 'Нет линка'
    })
  }, /*#__PURE__*/React.createElement(KV, {
    rows: [['Скорость', p.link ? fmt.speed(p.speed) : '—'], ...(p.poe ? [['PoE', p.poeW ? `${p.poeW} Вт` : 'нет потребителя']] : []), ['VLAN (untagged)', (p.vlansU || []).map(v => vlanName(v, vlans)).join(', ')], ['VLAN (tagged)', (p.vlansT || []).map(v => vlanName(v, vlans)).join(', ')], ...(p.ip ? [['IP', p.ip]] : []), ['Интерфейс', p.name], ...(p.lldp ? [['Сосед (LLDP)', p.lldp]] : []), ...(p.rxBytes != null ? [['Всего передано', `↓ ${fmt.bytes(p.txBytes)} · ↑ ${fmt.bytes(p.rxBytes)}`]] : [])]
  }), p.rxBytes != null ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title",
    style: {
      marginBottom: 8
    }
  }, "\u0422\u0440\u0430\u0444\u0438\u043A \u0437\u0430 \u0441\u0443\u0442\u043A\u0438"), /*#__PURE__*/React.createElement(TrafficChart, {
    points: traffic
  })) : null, (p.peers || []).length ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title",
    style: {
      marginBottom: 4
    }
  }, "\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u043E (", p.peers.length, ")"), /*#__PURE__*/React.createElement("div", {
    className: "list"
  }, p.peers.slice(0, 40).map(x => /*#__PURE__*/React.createElement("div", {
    className: "li",
    key: x.mac
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: x.kind || 'other',
    size: 30,
    round: 8
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ellipsis",
    style: {
      fontWeight: 600,
      fontSize: 14
    }
  }, x.name || 'Неизвестное устройство'), /*#__PURE__*/React.createElement("div", {
    className: "dim mono",
    style: {
      fontSize: 12
    }
  }, [x.ip, x.mac].filter(Boolean).join(' · '))), x.vlan ? /*#__PURE__*/React.createElement("span", {
    className: "badge",
    style: {
      color: vlanColor(x.vlan, vlans)
    }
  }, vlanName(x.vlan, vlans)) : null)))) : null, cab || slow || admin && cableAction && p.kind !== 'sfp' ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "card-title",
    style: {
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "grow"
  }, "\u041A\u0430\u0431\u0435\u043B\u044C"), admin && cableAction && p.kind !== 'sfp' ? /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "cable",
    busy: testing === p.n,
    onClick: () => doCableTest(cableAction, p.n)
  }, testing === p.n ? 'Измеряю…' : cab ? 'Проверить снова' : cableAction.label) : null), cab ? /*#__PURE__*/React.createElement(CableResult, {
    c: cab,
    now: data.now
  }) : slow ? /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13
    }
  }, "\u041F\u043E\u0440\u0442 \u0440\u0430\u0431\u043E\u0442\u0430\u0435\u0442 \u043D\u0430 ", fmt.speed(p.speed), ". \u0415\u0441\u043B\u0438 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E \u0433\u0438\u0433\u0430\u0431\u0438\u0442\u043D\u043E\u0435 \u2014 \u0441\u043A\u043E\u0440\u0435\u0435 \u0432\u0441\u0435\u0433\u043E \u0432 \u043A\u0430\u0431\u0435\u043B\u0435 \u0440\u0430\u0431\u043E\u0442\u0430\u044E\u0442 \u043D\u0435 \u0432\u0441\u0435 \u043F\u0430\u0440\u044B. ", admin && cableAction ? 'Нажмите «Проверить кабель».' : '') : /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 13
    }
  }, "\u041A\u043E\u043C\u043C\u0443\u0442\u0430\u0442\u043E\u0440 \u0438\u0437\u043C\u0435\u0440\u0438\u0442 \u0434\u043B\u0438\u043D\u0443 \u043A\u0430\u0431\u0435\u043B\u044F \u0438 \u043F\u0440\u043E\u0432\u0435\u0440\u0438\u0442 \u043A\u0430\u0436\u0434\u0443\u044E \u0438\u0437 4 \u043F\u0430\u0440 \u2014 \u0432\u0438\u0434\u043D\u043E \u043E\u0431\u0440\u044B\u0432, \u0437\u0430\u043C\u044B\u043A\u0430\u043D\u0438\u0435 \u0438 \u043F\u043B\u043E\u0445\u043E\u0439 \u043E\u0431\u0436\u0438\u043C.")) : null, admin && portActions.length ? /*#__PURE__*/React.createElement("div", {
    className: "row wrap",
    style: {
      marginTop: 14
    }
  }, portActions.map(a => /*#__PURE__*/React.createElement(Btn, {
    key: a.id,
    kind: "danger",
    size: "sm",
    icon: a.id === 'poe_cycle' ? 'bolt' : 'refresh',
    onClick: () => doPortAction(a, p.n)
  }, a.label))) : null, admin && portActions.length ? /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 12,
      marginTop: 8
    }
  }, "\u041F\u0435\u0440\u0435\u0437\u0430\u043F\u0443\u0441\u043A PoE \u0437\u0430\u043D\u0438\u043C\u0430\u0435\u0442 ~20 \u0441\u0435\u043A\u0443\u043D\u0434, \u0437\u0430\u0442\u0435\u043C \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0443 \u043D\u0443\u0436\u043D\u043E 1\u20132 \u043C\u0438\u043D\u0443\u0442\u044B, \u0447\u0442\u043E\u0431\u044B \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C\u0441\u044F.") : null) : null, /*#__PURE__*/React.createElement(Card, {
    title: "\u0412\u0441\u0435 \u043F\u043E\u0440\u0442\u044B",
    pad: false
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      overflowX: 'auto'
    }
  }, /*#__PURE__*/React.createElement("table", {
    className: "table"
  }, /*#__PURE__*/React.createElement("thead", null, /*#__PURE__*/React.createElement("tr", null, /*#__PURE__*/React.createElement("th", null, "#"), /*#__PURE__*/React.createElement("th", null, "\u041F\u043E\u0434\u043F\u0438\u0441\u044C"), /*#__PURE__*/React.createElement("th", null, "\u041B\u0438\u043D\u043A"), hasTraffic ? /*#__PURE__*/React.createElement("th", null, "\u0422\u0440\u0430\u0444\u0438\u043A \u2193/\u2191") : null, /*#__PURE__*/React.createElement("th", null, "PoE"), /*#__PURE__*/React.createElement("th", null, "VLAN"), /*#__PURE__*/React.createElement("th", null, "\u0423\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430"))), /*#__PURE__*/React.createElement("tbody", null, ports.map(x => /*#__PURE__*/React.createElement("tr", {
    key: x.n,
    onClick: () => setSel(x.n),
    style: {
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("td", {
    className: "mono"
  }, x.n), /*#__PURE__*/React.createElement("td", null, x.label, x.cable && ['warn', 'bad'].includes(x.cable.verdict) ? /*#__PURE__*/React.createElement("span", {
    title: x.cable.text,
    style: {
      marginLeft: 6,
      color: 'var(--orange)'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 13
  })) : null), /*#__PURE__*/React.createElement("td", null, x.link ? /*#__PURE__*/React.createElement("span", {
    className: "row",
    style: {
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: 'dot ' + (x.speed >= 1000 ? 'online' : 'warning')
  }), fmt.speedShort(x.speed)) : /*#__PURE__*/React.createElement("span", {
    className: "dim3"
  }, "\u2014")), hasTraffic ? /*#__PURE__*/React.createElement("td", {
    className: "mono",
    style: {
      fontSize: 12,
      whiteSpace: 'nowrap'
    }
  }, x.txBps != null ? `${fmt.bps(x.txBps)} / ${fmt.bps(x.rxBps)}` : '') : null, /*#__PURE__*/React.createElement("td", null, x.poeW ? x.poeW + ' Вт' : ''), /*#__PURE__*/React.createElement("td", null, [...(x.vlansU || []), ...(x.vlansT || []).map(v => v + 't')].join(', ')), /*#__PURE__*/React.createElement("td", {
    className: "ellipsis",
    style: {
      maxWidth: 200
    }
  }, (x.peers || []).length > 2 ? `${x.peers.length} устр.` : (x.peers || []).map(y => y.name || y.mac).join(', ')))))))));
}
function ChildrenTab({
  device,
  drv
}) {
  const {
    admin
  } = useApp();
  const runAction = useAction();
  const act = (drv?.actions || []).find(a => a.scope === 'child');
  return /*#__PURE__*/React.createElement("div", {
    className: "col",
    style: {
      gap: 10
    }
  }, device.state.children.map(c => /*#__PURE__*/React.createElement(Card, {
    key: c.key
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: "ap",
    size: 40
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700
    }
  }, c.name), /*#__PURE__*/React.createElement("div", {
    className: "dim mono",
    style: {
      fontSize: 12.5
    }
  }, c.model, " \xB7 ", c.ip)), /*#__PURE__*/React.createElement(StatusBadge, {
    status: c.status
  })), /*#__PURE__*/React.createElement("div", {
    className: "stats",
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement(Stat, {
    k: "\u041A\u043B\u0438\u0435\u043D\u0442\u044B",
    v: c.clients
  }), /*#__PURE__*/React.createElement(Stat, {
    k: "\u0410\u043F\u0442\u0430\u0439\u043C",
    v: fmt.uptime(c.uptime)
  }), /*#__PURE__*/React.createElement(Stat, {
    k: "Uplink",
    v: c.uplink ? fmt.speedShort(+c.uplink) : '—',
    level: +c.uplink && +c.uplink < 1000 ? 'warn' : ''
  }), /*#__PURE__*/React.createElement(Stat, {
    k: "\u041F\u0440\u043E\u0448\u0438\u0432\u043A\u0430",
    v: c.fw
  })), c.fwUpdate ? /*#__PURE__*/React.createElement("div", {
    className: "badge info",
    style: {
      marginTop: 10
    }
  }, "\u0414\u043E\u0441\u0442\u0443\u043F\u043D\u043E \u043E\u0431\u043D\u043E\u0432\u043B\u0435\u043D\u0438\u0435 \u043F\u0440\u043E\u0448\u0438\u0432\u043A\u0438") : null, admin && act ? /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    kind: "danger",
    icon: "power",
    onClick: () => runAction(device, act, {
      ip: c.ip
    })
  }, act.label)) : null)));
}
function ClientsTab({
  clients,
  children
}) {
  const [q, setQ] = useState('');
  const [seg, setSeg] = useState('');
  const apName = k => k === 'self' ? 'Роутер' : ((children || []).find(c => c.key === k) || {}).name || '';
  const segs = [...new Set(clients.map(c => c.segment || '—'))];
  const list = clients.filter(c => (!seg || (c.segment || '—') === seg) && (!q || [c.name, c.ip, c.mac].join(' ').toLowerCase().includes(q.toLowerCase()))).sort((a, b) => (a.segment || '').localeCompare(b.segment || '') || (a.name || '').localeCompare(b.name || ''));
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(SearchBox, {
    value: q,
    onChange: setQ,
    placeholder: "\u0418\u043C\u044F, IP \u0438\u043B\u0438 MAC"
  }), /*#__PURE__*/React.createElement("div", {
    className: "row wrap"
  }, /*#__PURE__*/React.createElement("button", {
    className: 'chip' + (!seg ? ' on' : ''),
    onClick: () => setSeg('')
  }, "\u0412\u0441\u0435 \xB7 ", clients.length), segs.map(s => /*#__PURE__*/React.createElement("button", {
    key: s,
    className: 'chip' + (seg === s ? ' on' : ''),
    onClick: () => setSeg(s)
  }, s, " \xB7 ", clients.filter(c => (c.segment || '—') === s).length))), /*#__PURE__*/React.createElement(Card, {
    pad: false
  }, /*#__PURE__*/React.createElement("div", {
    className: "list",
    style: {
      padding: '0 14px'
    }
  }, list.map(c => /*#__PURE__*/React.createElement("div", {
    className: "li",
    key: c.mac
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: c.kind,
    size: 34,
    round: 9
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "ellipsis",
    style: {
      fontWeight: 600,
      fontSize: 14
    }
  }, c.name || c.mac), /*#__PURE__*/React.createElement("div", {
    className: "dim mono ellipsis",
    style: {
      fontSize: 12
    }
  }, c.ip, " \xB7 ", c.mac)), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right',
      fontSize: 12
    },
    className: "dim"
  }, c.ap ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 4,
      justifyContent: 'flex-end'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "wifi",
    size: 13
  }), apName(c.ap), " ", c.band) : /*#__PURE__*/React.createElement("div", null, c.port ? 'порт ' + c.port : 'кабель'), c.rssi ? /*#__PURE__*/React.createElement("div", {
    style: {
      color: c.rssi > -65 ? 'var(--green)' : c.rssi > -75 ? 'var(--orange)' : 'var(--red)'
    }
  }, c.rssi, " \u0434\u0411\u043C", c.rate ? ' · ' + c.rate + ' Мбит' : '') : /*#__PURE__*/React.createElement("div", null, c.segment)))), !list.length ? /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, "\u041D\u0438\u0447\u0435\u0433\u043E \u043D\u0435 \u043D\u0430\u0439\u0434\u0435\u043D\u043E") : null)));
}
function StorageTab({
  storage
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, (storage.volumes || []).map(v => {
    const pct = v.total ? v.used * 100 / v.total : 0;
    return /*#__PURE__*/React.createElement(Card, {
      key: v.name,
      title: v.name,
      right: /*#__PURE__*/React.createElement(StatusBadge, {
        status: v.status === 'normal' ? 'online' : 'warning',
        text: v.status
      })
    }, /*#__PURE__*/React.createElement(Bar, {
      value: pct
    }), /*#__PURE__*/React.createElement("div", {
      className: "row between dim",
      style: {
        fontSize: 13,
        marginTop: 8
      }
    }, /*#__PURE__*/React.createElement("span", null, "\u0417\u0430\u043D\u044F\u0442\u043E ", fmt.bytes(v.used)), /*#__PURE__*/React.createElement("span", null, Math.round(pct), "%"), /*#__PURE__*/React.createElement("span", null, "\u0412\u0441\u0435\u0433\u043E ", fmt.bytes(v.total))));
  }), /*#__PURE__*/React.createElement(Card, {
    title: "\u0414\u0438\u0441\u043A\u0438"
  }, /*#__PURE__*/React.createElement("div", {
    className: "list"
  }, (storage.disks || []).map(d => /*#__PURE__*/React.createElement("div", {
    className: "li",
    key: d.name
  }, /*#__PURE__*/React.createElement("div", {
    className: "ico-circle"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "nas",
    size: 18
  })), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600
    }
  }, d.name, " ", /*#__PURE__*/React.createElement("span", {
    className: "badge",
    style: {
      marginLeft: 4
    }
  }, (d.kind || '').toUpperCase())), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 12.5
    }
  }, d.model, " \xB7 ", fmt.gb(d.sizeGB))), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600,
      color: d.temp > 50 ? 'var(--orange)' : ''
    }
  }, d.temp != null ? d.temp + '°C' : ''), /*#__PURE__*/React.createElement(StatusBadge, {
    status: d.status === 'normal' ? 'online' : d.status === 'not_use' ? '' : 'warning',
    text: d.status === 'not_use' ? 'не используется' : d.status
  })))))));
}
function ServicesTab({
  device,
  drv
}) {
  const {
    admin
  } = useApp();
  const runAction = useAction();
  const st = device.state;
  const [q, setQ] = useState('');
  const [pending, setPending] = useState({}); // entity -> state shown until the server confirms
  const restart = (drv?.actions || []).find(a => a.scope === 'service');
  const toggle = (drv?.actions || []).find(a => a.scope === 'entity');
  useEffect(() => {
    // drop optimistic values once real data agrees
    setPending(p => {
      const n = {
        ...p
      };
      (st.entities || []).forEach(e => {
        if (n[e.id] === e.state) delete n[e.id];
      });
      return n;
    });
  }, [st.entities]);
  const flip = async e => {
    const target = (pending[e.id] || e.state) === 'on' ? 'off' : 'on';
    setPending(p => ({
      ...p,
      [e.id]: target
    }));
    const ok = await runAction(device, toggle, {
      entity: e.id
    });
    if (!ok) setPending(p => {
      const n = {
        ...p
      };
      delete n[e.id];
      return n;
    });else setTimeout(() => setPending(p => {
      const n = {
        ...p
      };
      delete n[e.id];
      return n;
    }), 8000);
  };
  if (st.entities) return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(SearchBox, {
    value: q,
    onChange: setQ
  }), /*#__PURE__*/React.createElement(Card, {
    pad: false
  }, /*#__PURE__*/React.createElement("div", {
    className: "list",
    style: {
      padding: '0 14px'
    }
  }, st.entities.filter(e => !q || e.name.toLowerCase().includes(q.toLowerCase())).map(e => {
    const cur = pending[e.id] || e.state;
    return /*#__PURE__*/React.createElement("div", {
      className: "li",
      key: e.id
    }, /*#__PURE__*/React.createElement("div", {
      className: "ico-circle"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: e.id.startsWith('light') ? 'sun' : 'toggle',
      size: 18,
      color: cur === 'on' ? 'var(--orange)' : undefined
    })), /*#__PURE__*/React.createElement("div", {
      className: "grow"
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontWeight: 600,
        fontSize: 14
      }
    }, e.name), /*#__PURE__*/React.createElement("div", {
      className: "dim mono",
      style: {
        fontSize: 12
      }
    }, e.id)), admin && toggle ? /*#__PURE__*/React.createElement(Switch, {
      on: cur === 'on',
      disabled: e.state === 'unavailable',
      onChange: () => flip(e)
    }) : /*#__PURE__*/React.createElement("span", {
      className: "badge"
    }, e.state));
  }))));
  return /*#__PURE__*/React.createElement(Card, {
    pad: false
  }, /*#__PURE__*/React.createElement("div", {
    className: "list",
    style: {
      padding: '0 14px'
    }
  }, (st.services || []).map(s => {
    const ok = /running|up/i.test(s.state || '');
    return /*#__PURE__*/React.createElement("div", {
      className: "li",
      key: s.name
    }, /*#__PURE__*/React.createElement("span", {
      className: 'dot ' + (ok ? 'online' : 'offline')
    }), /*#__PURE__*/React.createElement("div", {
      className: "grow",
      style: {
        fontWeight: 600,
        fontSize: 14
      }
    }, s.name), /*#__PURE__*/React.createElement("span", {
      className: "dim",
      style: {
        fontSize: 13
      }
    }, s.state), admin && restart ? /*#__PURE__*/React.createElement(Btn, {
      size: "sm",
      icon: "refresh",
      onClick: () => runAction(device, restart, {
        name: s.name
      }),
      title: "\u041F\u0435\u0440\u0435\u0437\u0430\u043F\u0443\u0441\u0442\u0438\u0442\u044C"
    }) : null);
  })));
}
function EventsList({
  events,
  compact
}) {
  const {
    data
  } = useApp();
  if (!events.length) return compact ? null : /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, "\u0421\u043E\u0431\u044B\u0442\u0438\u0439 \u043F\u043E\u043A\u0430 \u043D\u0435\u0442");
  return /*#__PURE__*/React.createElement(Card, {
    title: compact ? 'Последние события' : null
  }, events.map((e, i) => /*#__PURE__*/React.createElement("div", {
    className: "ev",
    key: i
  }, /*#__PURE__*/React.createElement("span", {
    className: 'dot ' + (e.level === 'info' ? '' : e.level),
    style: {
      marginTop: 6,
      background: e.level === 'info' ? 'var(--accent)' : undefined
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14
    }
  }, /*#__PURE__*/React.createElement("b", null, e.name), " \u2014 ", e.text), /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 12
    }
  }, fmt.time(e.t), " \xB7 ", fmt.ago(e.t, data.now))))));
}

/* ── 30_rack.jsx ── */
/* Rack view */
const U_PX = 46;
const UNIT_COLORS = ['#0a84ff', '#30d158', '#bf5af2', '#ff9f0a', '#ff453a', '#64d2ff', '#5e5ce6', '#ffd60a', '#8e8e93'];
function deviceLine(dev) {
  if (!dev) return '';
  const st = dev.state || {};
  const s = st.summary || {};
  if (st.status === 'offline') return st.error ? 'Нет связи · ' + st.error : 'Нет связи';
  const parts = [];
  const ports = st.ports || [];
  if (ports.length > 6) {
    parts.push(`${ports.filter(p => p.link).length}/${ports.length} портов`);
    const poe = ports.reduce((a, p) => a + (p.poeW || 0), 0);
    if (poe) parts.push(`PoE ${poe.toFixed(0)} Вт`);
  }
  if ((st.clients || []).length) parts.push(`${st.clients.length} клиентов`);
  if ((st.children || []).length) parts.push(`${st.children.length} точки`);
  if (s.cpu != null) parts.push(`CPU ${Math.round(s.cpu)}%`);
  if (s.temp != null) parts.push(`${s.temp}°C`);
  const vol = st.storage && (st.storage.volumes || [])[0];
  if (vol && vol.total) parts.push(`том ${Math.round(vol.used * 100 / vol.total)}%`);
  (st.metrics || []).slice(0, 2).forEach(m => {
    if (!parts.length || m.label === 'Недоступно') parts.push(`${m.label}: ${m.value}${m.unit ? ' ' + m.unit : ''}`);
  });
  if (!parts.length && s.fw) parts.push(s.fw);
  return parts.join(' · ');
}
function Leds({
  ports
}) {
  if (!ports || ports.length < 4) return null;
  const list = ports.filter(p => p.kind !== 'sfp').slice(0, 48);
  return /*#__PURE__*/React.createElement("div", {
    className: "leds",
    style: {
      gridTemplateRows: list.length > 8 ? 'repeat(2, 7px)' : '7px'
    }
  }, list.map(p => /*#__PURE__*/React.createElement("i", {
    key: p.n,
    className: p.disabled ? 'off' : speedClass(p)
  })));
}
function RackUnit({
  unit,
  dev,
  edit,
  onClick,
  onPointerDown,
  dragging,
  top
}) {
  const kind = PASSIVE.includes(unit.type) ? unit.type : dev && dev.kind || unit.type;
  const st = dev && dev.state ? dev.state.status : null;
  const h = unit.uSize * U_PX - 4;
  return /*#__PURE__*/React.createElement("div", {
    className: ['unit', PASSIVE.includes(unit.type) ? 'passive' : '', unit.type === 'blank' ? 'blank' : '', dragging ? 'dragging' : ''].join(' '),
    style: {
      top: top + 2,
      height: h,
      cursor: edit ? 'grab' : 'pointer'
    },
    onClick: onClick,
    onPointerDown: onPointerDown
  }, /*#__PURE__*/React.createElement("div", {
    className: "strip",
    style: {
      background: unit.color || '#0a84ff'
    }
  }), unit.type !== 'blank' ? /*#__PURE__*/React.createElement("div", {
    className: "uicon"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: kind,
    size: 16,
    color: "#f5f5f7"
  })) : null, /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 7
    }
  }, st ? /*#__PURE__*/React.createElement("span", {
    className: 'dot ' + st
  }) : null, /*#__PURE__*/React.createElement("span", {
    className: "uname ellipsis"
  }, unit.name)), h > 30 ? /*#__PURE__*/React.createElement("div", {
    className: "umeta ellipsis"
  }, dev ? deviceLine(dev) : (KIND_TEXT[unit.type] || '') + (unit.uSize > 1 ? ` · ${unit.uSize}U` : '')) : null), /*#__PURE__*/React.createElement(Leds, {
    ports: dev && dev.state && dev.state.ports
  }));
}
function RackView() {
  const {
    data,
    edit,
    saveRack,
    openDevice
  } = useApp();
  const [side, setSide] = useState('front');
  const [editing, setEditing] = useState(null); // unit being edited / created
  const [info, setInfo] = useState(null);
  const [drag, setDrag] = useState(null); // {id, slot}
  const slotsRef = useRef(null);
  const toast = useToast();
  const rack = data.rack;
  const total = rack.totalU;
  const minU = Math.max(1, ...rack.units.map(u => u.uStart + u.uSize - 1));
  const units = rack.units.filter(u => (u.side || 'front') === side);
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const occupied = exceptId => {
    const o = new Array(total + 2).fill(null);
    units.forEach(u => {
      if (u.id !== exceptId) for (let i = u.uStart; i < u.uStart + u.uSize; i++) o[i] = u.id;
    });
    return o;
  };
  const fits = (u, start, exceptId) => {
    if (start < 1 || start + u.uSize - 1 > total) return false;
    const o = occupied(exceptId);
    for (let i = start; i < start + u.uSize; i++) if (o[i]) return false;
    return true;
  };
  const startDrag = (u, e) => {
    if (!edit) return;
    e.preventDefault();
    const rect = slotsRef.current.getBoundingClientRect();
    const offset = Math.floor((e.clientY - rect.top) / U_PX) + 1 - u.uStart;
    let moved = false;
    const move = ev => {
      moved = true;
      const slot = Math.floor((ev.clientY - rect.top) / U_PX) + 1 - offset;
      setDrag({
        id: u.id,
        slot
      });
    };
    const up = ev => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      const slot = Math.floor((ev.clientY - rect.top) / U_PX) + 1 - offset;
      setDrag(null);
      if (!moved) {
        setEditing(u);
        return;
      }
      if (slot !== u.uStart && fits(u, slot, u.id)) saveRack({
        ...rack,
        units: rack.units.map(x => x.id === u.id ? {
          ...x,
          uStart: slot
        } : x)
      });
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  const occ = occupied();
  const dragUnit = drag && units.find(u => u.id === drag.id);
  const dropOk = dragUnit && fits(dragUnit, drag.slot, drag.id);
  const devices = data.devices;
  const problems = devices.filter(d => ['offline', 'warning'].includes(d.state && d.state.status));
  const allPorts = devices.flatMap(d => d.state && d.state.ports || []);
  const clients = devices.reduce((a, d) => a + (d.state && d.state.clients || []).length, 0);
  const poe = allPorts.reduce((a, p) => a + (p.poeW || 0), 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "rack-layout"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "rack"
  }, /*#__PURE__*/React.createElement("div", {
    className: "rack-top"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "title"
  }, data.settings.title), /*#__PURE__*/React.createElement("div", {
    className: "meta"
  }, total, "U \xB7 \u0437\u0430\u043D\u044F\u0442\u043E ", occ.filter(Boolean).length, "U \xB7 ", side === 'front' ? 'вид спереди' : 'вид сзади')), /*#__PURE__*/React.createElement(Seg, {
    value: side,
    onChange: setSide,
    options: [{
      value: 'front',
      label: 'Фронт'
    }, {
      value: 'back',
      label: 'Тыл'
    }]
  })), /*#__PURE__*/React.createElement("div", {
    className: "rack-body",
    style: {
      '--u': U_PX + 'px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "rack-rail"
  }, Array.from({
    length: total
  }, (_, i) => /*#__PURE__*/React.createElement("div", {
    key: i
  }, i + 1))), /*#__PURE__*/React.createElement("div", {
    className: "rack-slots",
    ref: slotsRef
  }, Array.from({
    length: total
  }, (_, i) => {
    const n = i + 1;
    const inDrop = dragUnit && n >= drag.slot && n < drag.slot + dragUnit.uSize;
    return /*#__PURE__*/React.createElement("div", {
      key: n,
      className: 'rack-slot' + (inDrop && dropOk ? ' drop' : '') + (edit && !occ[n] ? ' addable' : ''),
      onClick: () => edit && !occ[n] && setEditing({
        id: null,
        name: '',
        type: 'switch',
        uSize: 1,
        uStart: n,
        side,
        color: '#0a84ff',
        deviceId: null,
        notes: ''
      })
    });
  }), units.map(u => /*#__PURE__*/React.createElement(RackUnit, {
    key: u.id,
    unit: u,
    dev: devById[u.deviceId],
    edit: edit,
    top: (u.uStart - 1) * U_PX,
    dragging: drag && drag.id === u.id,
    onPointerDown: e => startDrag(u, e),
    onClick: () => {
      if (edit) return;
      const d = devById[u.deviceId];
      d ? openDevice(d) : setInfo(u);
    }
  }))), /*#__PURE__*/React.createElement("div", {
    className: "rack-rail"
  }, Array.from({
    length: total
  }, (_, i) => /*#__PURE__*/React.createElement("div", {
    key: i
  }, i + 1))))), edit ? /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement(Btn, {
    kind: "primary",
    icon: "plus",
    onClick: () => {
      const free = occ.findIndex((x, i) => i > 0 && i <= total && !x);
      setEditing({
        id: null,
        name: '',
        type: 'switch',
        uSize: 1,
        uStart: free > 0 ? free : 1,
        side,
        color: '#0a84ff',
        deviceId: null,
        notes: ''
      });
    }
  }, "\u042E\u043D\u0438\u0442"), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }), /*#__PURE__*/React.createElement("span", {
    className: "dim",
    style: {
      fontSize: 13
    }
  }, "\u0412\u044B\u0441\u043E\u0442\u0430", minU > 1 ? ` (занято до U${minU})` : ''), /*#__PURE__*/React.createElement("select", {
    className: "select",
    style: {
      width: 96
    },
    value: total,
    onChange: e => {
      const n = +e.target.value;
      if (n < minU) {
        toast(`Нельзя меньше ${minU}U — внизу стоит оборудование. Сначала переместите его выше.`, true);
        return;
      }
      saveRack({
        ...rack,
        totalU: n
      });
    }
  }, [...new Set([6, 9, 12, 15, 18, 20, 22, 24, 27, 32, 36, 42, 45, 47, total])].sort((a, b) => a - b).map(n => /*#__PURE__*/React.createElement("option", {
    key: n,
    value: n,
    disabled: n < minU
  }, n, "U", n < minU ? ' — мало' : '')))) : /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 12.5,
      marginTop: 10,
      textAlign: 'center'
    }
  }, "\u041D\u0430\u0436\u043C\u0438\u0442\u0435 \u043D\u0430 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E, \u0447\u0442\u043E\u0431\u044B \u043E\u0442\u043A\u0440\u044B\u0442\u044C \u043F\u043E\u0434\u0440\u043E\u0431\u043D\u043E\u0441\u0442\u0438")), /*#__PURE__*/React.createElement("div", {
    className: "side-stack"
  }, /*#__PURE__*/React.createElement("div", {
    className: "stats"
  }, /*#__PURE__*/React.createElement(Stat, {
    k: "\u0423\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430",
    v: `${devices.filter(d => d.state && d.state.status === 'online').length}/${devices.length}`
  }), /*#__PURE__*/React.createElement(Stat, {
    k: "\u041F\u0440\u043E\u0431\u043B\u0435\u043C\u044B",
    v: problems.length,
    level: problems.length ? 'warn' : ''
  }), /*#__PURE__*/React.createElement(Stat, {
    k: "\u041A\u043B\u0438\u0435\u043D\u0442\u044B",
    v: clients
  }), /*#__PURE__*/React.createElement(Stat, {
    k: "PoE",
    v: poe ? poe.toFixed(1) : 0,
    unit: "\u0412\u0442"
  })), problems.length ? /*#__PURE__*/React.createElement(Card, {
    title: "\u0422\u0440\u0435\u0431\u0443\u044E\u0442 \u0432\u043D\u0438\u043C\u0430\u043D\u0438\u044F"
  }, /*#__PURE__*/React.createElement("div", {
    className: "list"
  }, problems.map(d => /*#__PURE__*/React.createElement("div", {
    className: "li",
    key: d.id,
    style: {
      cursor: 'pointer'
    },
    onClick: () => openDevice(d)
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: d.kind,
    size: 34
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 600
    }
  }, d.name), /*#__PURE__*/React.createElement("div", {
    className: "dim ellipsis",
    style: {
      fontSize: 12.5
    }
  }, d.state.error || (d.state.metrics || []).filter(m => m.level).map(m => `${m.label}: ${m.value}`).join(', ') || STATUS_TEXT[d.state.status])), /*#__PURE__*/React.createElement(StatusBadge, {
    status: d.state.status
  }))))) : /*#__PURE__*/React.createElement(Card, null, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "dot online"
  }), /*#__PURE__*/React.createElement("b", null, "\u0412\u0441\u0451 \u0440\u0430\u0431\u043E\u0442\u0430\u0435\u0442"), /*#__PURE__*/React.createElement("span", {
    className: "dim"
  }, "\u2014 \u0432\u0441\u0435 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 \u043D\u0430 \u0441\u0432\u044F\u0437\u0438"))), /*#__PURE__*/React.createElement(HealthCard, null), /*#__PURE__*/React.createElement(Card, {
    title: "\u0423\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 \u0432 \u0448\u043A\u0430\u0444\u0443"
  }, /*#__PURE__*/React.createElement("div", {
    className: "list"
  }, rack.units.filter(u => u.deviceId && devById[u.deviceId]).sort((a, b) => a.uStart - b.uStart).map(u => {
    const d = devById[u.deviceId];
    return /*#__PURE__*/React.createElement("div", {
      className: "li",
      key: u.id,
      style: {
        cursor: 'pointer'
      },
      onClick: () => openDevice(d)
    }, /*#__PURE__*/React.createElement(KindIcon, {
      kind: d.kind,
      size: 34
    }), /*#__PURE__*/React.createElement("div", {
      className: "grow",
      style: {
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "row",
      style: {
        gap: 6
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontWeight: 600
      }
    }, d.name), /*#__PURE__*/React.createElement("span", {
      className: "dim3 mono",
      style: {
        fontSize: 11
      }
    }, "U", u.uStart)), /*#__PURE__*/React.createElement("div", {
      className: "dim ellipsis",
      style: {
        fontSize: 12.5
      }
    }, deviceLine(d))), /*#__PURE__*/React.createElement(Icon, {
      name: "chevron",
      size: 16,
      color: "var(--text3)"
    }));
  }))), /*#__PURE__*/React.createElement(EventsList, {
    events: data.events.slice(0, 6),
    compact: true
  })), editing ? /*#__PURE__*/React.createElement(UnitEditor, {
    unit: editing,
    onClose: () => setEditing(null),
    fits: fits
  }) : null, info ? /*#__PURE__*/React.createElement(Modal, {
    title: info.name,
    onClose: () => setInfo(null),
    icon: /*#__PURE__*/React.createElement(KindIcon, {
      kind: info.type
    })
  }, /*#__PURE__*/React.createElement(KV, {
    rows: [['Тип', KIND_TEXT[info.type]], ['Позиция', `U${info.uStart}${info.uSize > 1 ? '–' + (info.uStart + info.uSize - 1) : ''}`], ['Сторона', info.side === 'back' ? 'Тыл' : 'Фронт']]
  }), info.notes ? /*#__PURE__*/React.createElement("div", {
    style: {
      whiteSpace: 'pre-wrap',
      fontSize: 14
    },
    className: "card pad"
  }, info.notes) : null, info.webUrl ? /*#__PURE__*/React.createElement("a", {
    className: "btn",
    href: info.webUrl,
    target: "_blank",
    rel: "noreferrer"
  }, "\u041E\u0442\u043A\u0440\u044B\u0442\u044C \u0432\u0435\u0431-\u0438\u043D\u0442\u0435\u0440\u0444\u0435\u0439\u0441") : null) : null);
}
function UnitEditor({
  unit,
  onClose,
  fits
}) {
  const {
    data,
    saveRack
  } = useApp();
  const confirm = useConfirm();
  const [f, setF] = useState({
    ...unit
  });
  const set = (k, v) => setF(x => ({
    ...x,
    [k]: v
  }));
  const ok = fits(f, +f.uStart, unit.id);
  const save = () => {
    const u = {
      ...f,
      uStart: +f.uStart,
      uSize: +f.uSize,
      name: f.name.trim() || (f.deviceId ? (data.devices.find(d => d.id === f.deviceId) || {}).name : KIND_TEXT[f.type])
    };
    const units = unit.id ? data.rack.units.map(x => x.id === unit.id ? u : x) : [...data.rack.units, {
      ...u,
      id: 'u' + Date.now().toString(36)
    }];
    saveRack({
      ...data.rack,
      units
    });
    onClose();
  };
  const del = async () => {
    if (await confirm(`Убрать «${unit.name}» из шкафа?`, {
      danger: true,
      ok: 'Убрать'
    })) {
      saveRack({
        ...data.rack,
        units: data.rack.units.filter(x => x.id !== unit.id)
      });
      onClose();
    }
  };
  return /*#__PURE__*/React.createElement(Modal, {
    title: unit.id ? 'Юнит' : 'Новый юнит',
    onClose: onClose,
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, unit.id ? /*#__PURE__*/React.createElement(Btn, {
      kind: "danger",
      icon: "trash",
      onClick: del
    }, "\u0423\u0431\u0440\u0430\u0442\u044C") : null, /*#__PURE__*/React.createElement("div", {
      className: "grow"
    }), /*#__PURE__*/React.createElement(Btn, {
      onClick: onClose
    }, "\u041E\u0442\u043C\u0435\u043D\u0430"), /*#__PURE__*/React.createElement(Btn, {
      kind: "primary",
      onClick: save,
      disabled: !ok
    }, "\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C"))
  }, /*#__PURE__*/React.createElement(Field, {
    label: "\u0421\u0432\u044F\u0437\u0430\u043D\u043D\u043E\u0435 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E",
    hint: "\u0416\u0438\u0432\u044B\u0435 \u0434\u0430\u043D\u043D\u044B\u0435 \u044D\u0442\u043E\u0433\u043E \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 \u0431\u0443\u0434\u0443\u0442 \u043F\u043E\u043A\u0430\u0437\u0430\u043D\u044B \u043D\u0430 \u044E\u043D\u0438\u0442\u0435"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: f.deviceId || '',
    onChange: e => {
      const d = data.devices.find(x => x.id === e.target.value);
      setF(x => ({
        ...x,
        deviceId: e.target.value || null,
        name: x.name || (d ? d.name : ''),
        type: d && UNIT_TYPES.includes(d.kind) ? d.kind : x.type
      }));
    }
  }, /*#__PURE__*/React.createElement("option", {
    value: ""
  }, "\u2014 \u043D\u0435 \u0441\u0432\u044F\u0437\u0430\u043D (\u043F\u0430\u0441\u0441\u0438\u0432\u043D\u043E\u0435 \u043E\u0431\u043E\u0440\u0443\u0434\u043E\u0432\u0430\u043D\u0438\u0435) \u2014"), data.devices.map(d => /*#__PURE__*/React.createElement("option", {
    key: d.id,
    value: d.id
  }, d.name)))), /*#__PURE__*/React.createElement(Field, {
    label: "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.name,
    onChange: e => set('name', e.target.value),
    placeholder: "\u041D\u0430\u043F\u0440\u0438\u043C\u0435\u0440, \u041A\u043E\u043C\u043C\u0443\u0442\u0430\u0442\u043E\u0440 \u044F\u0434\u0440\u0430"
  })), /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement(Field, {
    label: "\u0422\u0438\u043F"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: f.type,
    onChange: e => set('type', e.target.value)
  }, UNIT_TYPES.map(t => /*#__PURE__*/React.createElement("option", {
    key: t,
    value: t
  }, KIND_TEXT[t])))), /*#__PURE__*/React.createElement(Field, {
    label: "\u0412\u044B\u0441\u043E\u0442\u0430"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: f.uSize,
    onChange: e => set('uSize', +e.target.value)
  }, [1, 2, 3, 4, 5, 6, 8, 10].map(n => /*#__PURE__*/React.createElement("option", {
    key: n,
    value: n
  }, n, "U")))), /*#__PURE__*/React.createElement(Field, {
    label: "\u041F\u043E\u0437\u0438\u0446\u0438\u044F"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: f.uStart,
    onChange: e => set('uStart', +e.target.value)
  }, Array.from({
    length: data.rack.totalU
  }, (_, i) => /*#__PURE__*/React.createElement("option", {
    key: i,
    value: i + 1
  }, "U", i + 1))))), !ok ? /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--red)',
      fontSize: 13
    }
  }, "\u041D\u0430 \u044D\u0442\u043E\u043C \u043C\u0435\u0441\u0442\u0435 \u043D\u0435 \u0445\u0432\u0430\u0442\u0430\u0435\u0442 \u0441\u0432\u043E\u0431\u043E\u0434\u043D\u044B\u0445 \u044E\u043D\u0438\u0442\u043E\u0432") : null, /*#__PURE__*/React.createElement(Field, {
    label: "\u0421\u0442\u043E\u0440\u043E\u043D\u0430"
  }, /*#__PURE__*/React.createElement(Seg, {
    value: f.side || 'front',
    onChange: v => set('side', v),
    options: [{
      value: 'front',
      label: 'Фронт'
    }, {
      value: 'back',
      label: 'Тыл'
    }]
  })), /*#__PURE__*/React.createElement(Field, {
    label: "\u0426\u0432\u0435\u0442"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, UNIT_COLORS.map(c => /*#__PURE__*/React.createElement("button", {
    key: c,
    onClick: () => set('color', c),
    style: {
      width: 28,
      height: 28,
      borderRadius: 8,
      border: f.color === c ? '3px solid var(--text)' : '0',
      background: c,
      cursor: 'pointer'
    }
  })))), /*#__PURE__*/React.createElement(Field, {
    label: "\u0421\u0441\u044B\u043B\u043A\u0430 \u043D\u0430 \u0432\u0435\u0431-\u0438\u043D\u0442\u0435\u0440\u0444\u0435\u0439\u0441"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.webUrl || '',
    onChange: e => set('webUrl', e.target.value),
    placeholder: "http://192.168.1.1"
  })), /*#__PURE__*/React.createElement(Field, {
    label: "\u0417\u0430\u043C\u0435\u0442\u043A\u0438"
  }, /*#__PURE__*/React.createElement("textarea", {
    className: "textarea",
    value: f.notes || '',
    onChange: e => set('notes', e.target.value)
  })));
}

/* ── 40_map.jsx ── */
/* Network map: the rack in the middle, cables from its units to everything else. */
const M = {
  NW: 214,
  NH: 56,
  CW: 196,
  CH: 46,
  COL: 130,
  GAP: 12,
  RW: 310,
  RU: 38
};
function layoutMap(data, collapsed) {
  const topo = data.topology || {
    nodes: [],
    edges: []
  };
  const nodes = {};
  topo.nodes.forEach(n => nodes[n.id] = {
    ...n
  });
  const tree = topo.edges.filter(e => !e.extra && !e.manual && nodes[e.source] && nodes[e.target]).map(e => ({
    ...e
  }));
  const parentEdge = {};
  const kids = {};
  tree.forEach(e => {
    parentEdge[e.target] = e;
    (kids[e.source] = kids[e.source] || []).push(e);
  });

  // rack units shown on the map (front + back, linked ones get live data)
  const units = [...data.rack.units].sort((a, b) => (a.side === 'back') - (b.side === 'back') || a.uStart - b.uStart);
  const rackNode = {};
  units.forEach(u => {
    if (u.deviceId && nodes['d:' + u.deviceId]) rackNode['d:' + u.deviceId] = u;
  });
  const hasRack = Object.keys(rackNode).length > 0;
  const pos = {};
  const total = data.rack.totalU;
  Object.entries(rackNode).forEach(([id, u]) => {
    const y = (u.uStart - 1) * M.RU + (u.side === 'back' ? 0 : 0);
    pos[id] = {
      x: 0,
      y,
      w: M.RW,
      h: u.uSize * M.RU - 4,
      rack: true
    };
  });

  // collapse big groups of Wi-Fi leaf clients
  const groups = {};
  const hiddenIds = new Set();
  Object.entries(kids).forEach(([pid, es]) => {
    const wifiLeaves = es.filter(e => e.kind === 'wifi' && !kids[e.target]);
    if (wifiLeaves.length > 3 && collapsed[pid] !== false) {
      const gid = 'g:' + pid;
      groups[gid] = {
        id: gid,
        label: `${wifiLeaves.length} устройств по Wi-Fi`,
        members: wifiLeaves.map(e => nodes[e.target]),
        kind: 'group',
        parent: pid
      };
      wifiLeaves.forEach(e => {
        e.hidden = true;
        hiddenIds.add(e.target);
      });
      kids[pid] = es.filter(e => !e.hidden).concat([{
        id: 'ge:' + pid,
        source: pid,
        target: gid,
        kind: 'wifi',
        group: true
      }]);
    }
  });
  Object.values(groups).forEach(g => {
    nodes[g.id] = g;
  });

  // columns: BFS from the rack (or from the internet's direct children when there is no rack)
  const inet = nodes['inet'];
  let roots = hasRack ? Object.keys(rackNode) : (kids['inet'] || []).filter(e => e.kind !== 'remote').map(e => e.target);
  if (!roots.length) roots = Object.keys(nodes).filter(id => !parentEdge[id] && id !== 'inet');
  const col = {};
  const queue = [];
  roots.forEach(r => {
    col[r] = 0;
    queue.push(r);
  });
  while (queue.length) {
    const id = queue.shift();
    (kids[id] || []).filter(e => !e.hidden).forEach(e => {
      if (col[e.target] == null && !rackNode[e.target]) {
        col[e.target] = col[id] + 1;
        queue.push(e.target);
      }
    });
  }
  const colX = c => hasRack ? M.RW + M.COL + (c - 1) * (M.NW + M.COL) : c * (M.NW + M.COL);
  const sizeOf = id => {
    const n = nodes[id];
    return n.kind === 'group' || n.client ? [M.CW, M.CH] : [M.NW, M.NH];
  };
  if (!hasRack) roots.forEach((r, i) => {
    const [w, h] = sizeOf(r);
    pos[r] = {
      x: 0,
      y: i * (h + 40),
      w,
      h
    };
  });
  const maxCol = Math.max(0, ...Object.values(col));
  for (let c = 1; c <= maxCol; c++) {
    const ids = Object.keys(col).filter(id => col[id] === c);
    const pyOf = id => {
      const pe = parentEdge[id] || Object.values(kids).flat().find(e => e.target === id);
      const p = pe && pos[pe.source];
      return p ? p.y + p.h / 2 : 0;
    };
    const byParent = {};
    ids.forEach(id => {
      const pe = parentEdge[id] || Object.values(kids).flat().find(e => e.target === id);
      (byParent[pe ? pe.source : '_'] = byParent[pe ? pe.source : '_'] || []).push({
        id,
        port: pe ? pe.sourcePort || 999 : 999
      });
    });
    let cursor = -Infinity;
    Object.entries(byParent).sort((a, b) => pyOf(a[1][0].id) - pyOf(b[1][0].id)).forEach(([pid, list]) => {
      list.sort((a, b) => a.port - b.port || String(nodes[a.id].label).localeCompare(String(nodes[b.id].label)));
      const heights = list.map(x => sizeOf(x.id)[1]);
      const groupH = heights.reduce((a, h) => a + h + M.GAP, -M.GAP);
      const p = pos[pid];
      const center = p ? p.y + p.h / 2 : 0;
      let y = Math.max(cursor, center - groupH / 2);
      list.forEach((x, i) => {
        const [w, h] = sizeOf(x.id);
        pos[x.id] = {
          x: colX(c),
          y,
          w,
          h
        };
        y += h + M.GAP;
      });
      cursor = y + M.GAP * 2;
    });
  }
  // internet + remote devices on top
  const topY = hasRack ? -170 : Math.min(0, ...Object.values(pos).map(p => p.y)) - 170;
  if (inet) pos['inet'] = {
    x: (hasRack ? M.RW / 2 : M.NW / 2) - M.NW / 2,
    y: topY,
    w: M.NW,
    h: M.NH
  };
  const remotes = (kids['inet'] || []).filter(e => e.kind === 'remote').map(e => e.target);
  // remote devices go to the left of the internet node, so they never collide with the columns on the right
  remotes.forEach((id, i) => {
    pos[id] = {
      x: (pos.inet ? pos.inet.x : 0) - (M.NW + 50) * (i + 1),
      y: topY,
      w: M.NW,
      h: M.NH
    };
    col[id] = -1;
  });
  // nodes never reached (shouldn't happen) go to a bottom row
  let stray = 0;
  Object.keys(nodes).forEach(id => {
    if (!pos[id] && !hiddenIds.has(id)) {
      const [w, h] = sizeOf(id);
      pos[id] = {
        x: colX(1) + stray * (w + 20),
        y: total * M.RU + 80,
        w,
        h
      };
      stray++;
    }
  });
  // user overrides (edit mode drag)
  Object.entries(data.map.positions || {}).forEach(([id, [x, y]]) => {
    if (pos[id] && !pos[id].rack) Object.assign(pos[id], {
      x,
      y
    });
  });
  const edges = [...Object.values(kids).flat().filter(e => !e.hidden), ...topo.edges.filter(e => (e.extra || e.manual) && pos[e.source] && pos[e.target])];
  return {
    nodes,
    pos,
    edges,
    groups,
    hasRack,
    units,
    rackNode
  };
}
function edgePath(e, L) {
  const a = L.pos[e.source],
    b = L.pos[e.target];
  if (!a || !b) return null;
  if (a.rack && b.rack) {
    // patch cable inside the rack: loop on the left side
    const y1 = a.y + a.h / 2,
      y2 = b.y + b.h / 2,
      d = 26 + Math.min(70, Math.abs(y2 - y1) * .18);
    return {
      d: `M0,${y1} C${-d},${y1} ${-d},${y2} 0,${y2}`,
      lx: -d * .75,
      ly: (y1 + y2) / 2,
      inside: true
    };
  }
  if (e.source === 'inet' && b.rack) {
    const sx = a.x + a.w / 2,
      sy = a.y + a.h,
      ty = b.y + b.h / 2,
      tx = M.RW;
    return {
      d: `M${sx},${sy} C${sx},${sy + 60} ${tx + 70},${ty - 40} ${tx + 2},${ty}`,
      lx: tx + 34,
      ly: (sy + ty) / 2
    };
  }
  if (e.source === 'inet' && b.x + b.w <= a.x) {
    // remote device to the left of the internet node
    const sx = a.x,
      sy = a.y + a.h / 2,
      tx = b.x + b.w,
      ty = b.y + b.h / 2;
    return {
      d: `M${sx},${sy} C${sx - 30},${sy} ${tx + 30},${ty} ${tx},${ty}`,
      lx: (sx + tx) / 2,
      ly: sy - 8
    };
  }
  if (e.source === 'inet') {
    const sx = a.x + a.w,
      sy = a.y + a.h / 2,
      tx = b.x,
      ty = b.y + b.h / 2;
    if (Math.abs(sy - ty) < 4) return {
      d: `M${sx},${sy} L${tx},${ty}`,
      lx: (sx + tx) / 2,
      ly: sy - 8
    };
    return {
      d: `M${a.x + a.w / 2},${a.y + a.h} C${a.x + a.w / 2},${ty} ${tx - 60},${ty} ${tx},${ty}`,
      lx: tx - 40,
      ly: ty - 8
    };
  }
  const sx = a.x + a.w,
    sy = a.y + a.h / 2,
    tx = b.x,
    ty = b.y + b.h / 2;
  if (tx < sx) {
    // target to the left (user moved it): connect centres
    const ax = a.x + a.w / 2,
      bx = b.x + b.w / 2;
    return {
      d: `M${ax},${a.y + a.h} C${ax},${ty} ${bx},${a.y + a.h} ${bx},${b.y}`,
      lx: (ax + bx) / 2,
      ly: (sy + ty) / 2
    };
  }
  const dx = Math.max(50, (tx - sx) * .5);
  return {
    d: `M${sx},${sy} C${sx + dx},${sy} ${tx - dx},${ty} ${tx},${ty}`,
    lx: tx - 22,
    ly: ty,
    mx: (sx + tx) / 2,
    my: (sy + ty) / 2
  };
}
function MapNode({
  n,
  p,
  sel,
  dim,
  mark,
  onDown,
  onClick
}) {
  const small = n.kind === 'group' || n.client;
  const iconKind = n.kind === 'group' ? 'wifi' : n.kind;
  const c = KIND_COLOR[iconKind] || KIND_COLOR.other;
  const is = small ? 28 : 34;
  return /*#__PURE__*/React.createElement("g", {
    className: 'node' + (small ? ' client' : '') + (n.kind === 'group' ? ' group' : '') + (sel ? ' sel' : '') + (dim ? ' dim-out' : ''),
    transform: `translate(${p.x},${p.y})`,
    onPointerDown: onDown,
    onClick: onClick
  }, mark ? /*#__PURE__*/React.createElement("rect", {
    className: "spof-mark",
    x: -5,
    y: -5,
    width: p.w + 10,
    height: p.h + 10,
    rx: small ? 16 : 19
  }) : null, /*#__PURE__*/React.createElement("rect", {
    className: "box",
    width: p.w,
    height: p.h,
    rx: small ? 12 : 15
  }), /*#__PURE__*/React.createElement("rect", {
    x: 9,
    y: (p.h - is) / 2,
    width: is,
    height: is,
    rx: 9,
    fill: c,
    opacity: ".16"
  }), /*#__PURE__*/React.createElement("g", {
    transform: `translate(${9 + is * .2},${(p.h - is) / 2 + is * .2})`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: iconKind,
    size: is * .6,
    color: c
  })), /*#__PURE__*/React.createElement("text", {
    className: "lbl",
    x: is + 18,
    y: n.sub || n.kind === 'group' ? p.h / 2 - 3 : p.h / 2 + 4
  }, trunc(n.label, small ? 19 : 22)), n.kind === 'group' ? /*#__PURE__*/React.createElement("text", {
    className: "sub",
    x: is + 18,
    y: p.h / 2 + 12
  }, "\u043D\u0430\u0436\u043C\u0438\u0442\u0435, \u0447\u0442\u043E\u0431\u044B \u0440\u0430\u0441\u043A\u0440\u044B\u0442\u044C") : n.sub ? /*#__PURE__*/React.createElement("text", {
    className: "sub",
    x: is + 18,
    y: p.h / 2 + 13
  }, trunc(n.sub, 24)) : null, n.status && n.kind !== 'group' ? /*#__PURE__*/React.createElement("circle", {
    cx: p.w - 13,
    cy: 13,
    r: 4.5,
    fill: n.status === 'online' ? 'var(--green)' : n.status === 'warning' ? 'var(--orange)' : n.status === 'offline' ? 'var(--red)' : 'var(--text3)'
  }) : null);
}
const trunc = (s, n) => {
  s = String(s || '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
};
function MapView() {
  const {
    data,
    edit,
    openDevice,
    saveMap
  } = useApp();
  const toast = useToast();
  const confirm = useConfirm();
  const [collapsed, setCollapsed] = useState(data.map.collapsed || {});
  const [view, setView] = useState(null); // {x, y, k}
  const [sel, setSel] = useState(null);
  const [linking, setLinking] = useState(null); // null | 'pick' | nodeId
  const [q, setQ] = useState('');
  const [dragPos, setDragPos] = useState({});
  const [healthOpen, setHealthOpen] = useState(() => lsGet('rl_health', '') === '1' || new URLSearchParams(location.search).has('analysis'));
  useEffect(() => {
    lsSet('rl_health', healthOpen ? '1' : '');
  }, [healthOpen]);
  const spofSet = healthOpen && data.health ? new Set(data.health.spof.filter(s => s.affected >= 3).map(s => s.id)) : null;
  const openCheck = useCheckOpener();
  const wrap = useRef(null);
  const L = useMemo(() => {
    const l = layoutMap(data, collapsed);
    Object.entries(dragPos).forEach(([id, [x, y]]) => {
      if (l.pos[id]) Object.assign(l.pos[id], {
        x,
        y
      });
    });
    return l;
  }, [data, collapsed, dragPos]);
  const bbox = () => {
    const ps = Object.values(L.pos);
    if (!ps.length) return {
      x: 0,
      y: 0,
      w: 100,
      h: 100
    };
    const x1 = Math.min(-110, ...ps.map(p => p.x)) - 20,
      y1 = Math.min(-60, ...ps.map(p => p.y)) - 20;
    const x2 = Math.max(...ps.map(p => p.x + p.w)) + 20,
      y2 = Math.max(data.rack.totalU * M.RU, ...ps.map(p => p.y + p.h)) + 30;
    return {
      x: x1,
      y: y1,
      w: x2 - x1,
      h: y2 - y1
    };
  };
  const fit = () => {
    const el = wrap.current;
    if (!el) return;
    const b = bbox();
    const off = healthOpen && el.clientWidth > 760 ? 424 : 0; // keep the map clear of the analysis panel
    const W = el.clientWidth - off,
      H = el.clientHeight;
    const k = Math.min(1.2, Math.max(.2, Math.min(W / (b.w + 60), H / (b.h + 60))));
    setView({
      k,
      x: off + (W - b.w * k) / 2 - b.x * k,
      y: (H - b.h * k) / 2 - b.y * k
    });
  };
  useEffect(() => {
    if (!view) fit();
  }, [L]);
  useEffect(() => {
    if (view) fit();
  }, [healthOpen]);

  // pan / zoom / pinch. The gesture baseline is re-captured whenever the number of fingers changes,
  // so lifting one finger after a pinch no longer snaps the map back.
  const ptrs = useRef({});
  const panRef = useRef(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const clampK = k => Math.min(4, Math.max(.12, k));
  const baseline = () => {
    const pts = Object.values(ptrs.current);
    const v = {
      ...viewRef.current
    };
    if (!pts.length) return null;
    if (pts.length >= 2) {
      const r = wrap.current.getBoundingClientRect();
      return {
        pinch: true,
        dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1,
        cx: (pts[0].x + pts[1].x) / 2 - r.left,
        cy: (pts[0].y + pts[1].y) / 2 - r.top,
        v
      };
    }
    return {
      pinch: false,
      sx: pts[0].x,
      sy: pts[0].y,
      v
    };
  };
  const onBgDown = e => {
    if (e.target.closest('.node, .rackbox .u, .edge-hit')) return;
    ptrs.current[e.pointerId] = {
      x: e.clientX,
      y: e.clientY
    };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch (_) {}
    panRef.current = baseline();
    if (Object.keys(ptrs.current).length === 1) setSel(null);
  };
  const onBgMove = e => {
    if (!ptrs.current[e.pointerId] || !panRef.current) return;
    e.preventDefault();
    ptrs.current[e.pointerId] = {
      x: e.clientX,
      y: e.clientY
    };
    const pts = Object.values(ptrs.current);
    const b = panRef.current;
    if (b.pinch && pts.length >= 2) {
      const r = wrap.current.getBoundingClientRect();
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const cx = (pts[0].x + pts[1].x) / 2 - r.left,
        cy = (pts[0].y + pts[1].y) / 2 - r.top;
      const k = clampK(b.v.k * dist / b.dist);
      setView({
        k,
        x: cx - (b.cx - b.v.x) * k / b.v.k,
        y: cy - (b.cy - b.v.y) * k / b.v.k
      });
    } else if (!b.pinch) setView({
      ...b.v,
      x: b.v.x + e.clientX - b.sx,
      y: b.v.y + e.clientY - b.sy
    });
  };
  const onBgUp = e => {
    delete ptrs.current[e.pointerId];
    panRef.current = baseline();
  };
  const zoomAt = (factor, cx, cy) => setView(v => {
    const W = wrap.current.clientWidth,
      H = wrap.current.clientHeight;
    cx = cx == null ? W / 2 : cx;
    cy = cy == null ? H / 2 : cy;
    const k = clampK(v.k * factor);
    return {
      k,
      x: cx - (cx - v.x) * k / v.k,
      y: cy - (cy - v.y) * k / v.k
    };
  });
  const onWheel = e => {
    e.preventDefault();
    const r = wrap.current.getBoundingClientRect();
    zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? .01 : .0025)), e.clientX - r.left, e.clientY - r.top);
  };
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const stop = ev => ev.preventDefault(); // block Safari page zoom gestures on the map
    el.addEventListener('wheel', onWheel, {
      passive: false
    });
    el.addEventListener('gesturestart', stop);
    el.addEventListener('gesturechange', stop);
    el.addEventListener('touchmove', stop, {
      passive: false
    });
    return () => {
      el.removeEventListener('wheel', onWheel);
      el.removeEventListener('gesturestart', stop);
      el.removeEventListener('gesturechange', stop);
      el.removeEventListener('touchmove', stop);
    };
  }, [wrap.current, !!view]);

  // node drag in edit mode
  const nodeDown = (id, e) => {
    if (!edit || L.pos[id].rack || linking) return;
    e.stopPropagation();
    const p0 = {
      ...L.pos[id]
    };
    const sx = e.clientX,
      sy = e.clientY;
    let moved = false;
    const move = ev => {
      moved = true;
      setDragPos(d => ({
        ...d,
        [id]: [Math.round(p0.x + (ev.clientX - sx) / view.k), Math.round(p0.y + (ev.clientY - sy) / view.k)]
      }));
    };
    const up = ev => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      if (moved) {
        const np = [Math.round(p0.x + (ev.clientX - sx) / view.k), Math.round(p0.y + (ev.clientY - sy) / view.k)];
        saveMap({
          positions: {
            ...(data.map.positions || {}),
            [id]: np
          }
        });
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  const nodeClick = async id => {
    const n = L.nodes[id];
    if (linking) {
      if (linking === 'pick') {
        setLinking(id);
        toast('Теперь выберите второе устройство');
        return;
      }
      if (linking !== id) {
        const label = prompt('Подпись для связи (необязательно), например «Оптика 1 Гбит»', '') || '';
        await saveMap({
          links: [...(data.map.links || []), {
            id: 'm' + Date.now().toString(36),
            source: linking,
            target: id,
            label
          }]
        });
        toast('Связь добавлена');
      }
      setLinking(null);
      return;
    }
    if (n.kind === 'group') {
      const nc = {
        ...collapsed,
        [n.parent]: false
      };
      setCollapsed(nc);
      setView(null);
      if (edit) saveMap({
        collapsed: nc
      });
      return;
    }
    setSel(id);
  };
  const edgeClick = async e => {
    if (!edit || !e.manual) return;
    if (await confirm('Удалить эту связь?', {
      danger: true,
      ok: 'Удалить'
    })) saveMap({
      links: (data.map.links || []).filter(l => l.id !== e.id && `m:${l.source}>${l.target}` !== e.id)
    });
  };

  // highlight path to the root for the selected node
  const pathSet = useMemo(() => {
    if (!sel) return null;
    const s = new Set([sel]);
    let cur = sel,
      guard = 0;
    while (guard++ < 30) {
      const pe = L.edges.find(e => e.target === cur && !e.extra && !e.manual);
      if (!pe) break;
      s.add(pe.id);
      s.add(pe.source);
      cur = pe.source;
    }
    L.edges.filter(e => e.source === sel).forEach(e => {
      s.add(e.id);
      s.add(e.target);
    });
    return s;
  }, [sel, L]);
  const searchHit = q ? Object.values(L.nodes).filter(n => [n.label, n.sub].join(' ').toLowerCase().includes(q.toLowerCase())).map(n => n.id) : [];
  useEffect(() => {
    if (searchHit.length === 1 && wrap.current) {
      const p = L.pos[searchHit[0]];
      if (!p) return;
      const W = wrap.current.clientWidth,
        H = wrap.current.clientHeight;
      setSel(searchHit[0]);
      setView(v => ({
        k: Math.max(v.k, .9),
        x: W / 2 - (p.x + p.w / 2) * Math.max(v.k, .9),
        y: H / 2 - (p.y + p.h / 2) * Math.max(v.k, .9)
      }));
    }
  }, [q]);
  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  const selNode = sel && L.nodes[sel];
  const anyCollapsedOpen = Object.values(collapsed).some(v => v === false);
  if (!view) return /*#__PURE__*/React.createElement("div", {
    className: "map-wrap",
    ref: wrap
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "map-wrap",
    ref: wrap
  }, /*#__PURE__*/React.createElement("div", {
    className: "map-tools"
  }, /*#__PURE__*/React.createElement("div", {
    className: "map-panel",
    style: {
      width: 230
    }
  }, /*#__PURE__*/React.createElement(SearchBox, {
    value: q,
    onChange: setQ,
    placeholder: "\u041D\u0430\u0439\u0442\u0438 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E"
  })), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }), /*#__PURE__*/React.createElement("div", {
    className: "map-panel"
  }, data.health ? /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "pulse",
    kind: healthOpen ? 'primary' : '',
    onClick: () => setHealthOpen(!healthOpen),
    title: "\u0410\u043D\u0430\u043B\u0438\u0437 \u0441\u0435\u0442\u0438"
  }, "\u0410\u043D\u0430\u043B\u0438\u0437") : null, /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "fit",
    onClick: fit,
    title: "\u041F\u043E\u043A\u0430\u0437\u0430\u0442\u044C \u0432\u0441\u0451"
  }), /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "wifi",
    onClick: () => {
      const nc = {};
      if (!anyCollapsedOpen) Object.keys(L.groups).forEach(g => nc[g.slice(2)] = false);
      setCollapsed(nc);
      setView(null);
    },
    title: anyCollapsedOpen ? 'Свернуть Wi-Fi-клиентов' : 'Показать всех Wi-Fi-клиентов'
  }), edit ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "link",
    kind: linking ? 'primary' : '',
    onClick: () => setLinking(linking ? null : 'pick')
  }, linking ? 'Отмена' : 'Связь'), /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "refresh",
    onClick: async () => {
      if (await confirm('Сбросить ручное расположение узлов?')) {
        setDragPos({});
        saveMap({
          positions: {}
        });
      }
    },
    title: "\u0421\u0431\u0440\u043E\u0441\u0438\u0442\u044C \u0440\u0430\u0441\u043A\u043B\u0430\u0434\u043A\u0443"
  })) : null)), linking ? /*#__PURE__*/React.createElement("div", {
    className: "toast",
    style: {
      position: 'absolute',
      top: 64,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 3
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "link",
    size: 15
  }), linking === 'pick' ? 'Выберите первое устройство' : 'Выберите второе устройство') : null, /*#__PURE__*/React.createElement("svg", {
    onPointerDown: onBgDown,
    onPointerMove: onBgMove,
    onPointerUp: onBgUp,
    onPointerCancel: onBgUp,
    className: panRef.current ? 'panning' : ''
  }, /*#__PURE__*/React.createElement("g", {
    transform: `translate(${view.x},${view.y}) scale(${view.k})`
  }, L.hasRack ? /*#__PURE__*/React.createElement(RackBox, {
    L: L,
    data: data,
    devById: devById,
    dimSet: pathSet,
    markSet: spofSet,
    onOpen: d => openDevice(d),
    total: data.rack.totalU
  }) : null, L.edges.map(e => {
    const g = edgePath(e, L);
    if (!g) return null;
    const col = speedColor(e.speed, e.kind);
    const dim = pathSet && !pathSet.has(e.id) ? ' dim-out' : '';
    return /*#__PURE__*/React.createElement("g", {
      key: e.id,
      className: dim
    }, /*#__PURE__*/React.createElement("path", {
      className: 'edge' + (e.kind === 'wifi' || e.kind === 'mesh' ? ' wifi' : '') + (e.kind === 'remote' || e.extra || e.kind === 'lan' ? ' dashed' : ''),
      d: g.d,
      stroke: col,
      opacity: e.extra ? .55 : 1
    }), (e.kind === 'wan' || e.kind === 'wire' && e.speed >= 1000) && !e.extra ? /*#__PURE__*/React.createElement("path", {
      className: "edge flow",
      d: g.d,
      stroke: "#fff",
      opacity: ".5"
    }) : null, e.manual ? /*#__PURE__*/React.createElement("path", {
      className: "edge-hit",
      d: g.d,
      onClick: () => edgeClick(e)
    }) : null, e.sourcePort && !g.inside ? /*#__PURE__*/React.createElement("g", {
      className: "port-pill",
      transform: `translate(${g.lx - 14},${g.ly - 9})`
    }, /*#__PURE__*/React.createElement("rect", {
      width: "28",
      height: "18",
      rx: "9"
    }), /*#__PURE__*/React.createElement("text", {
      x: "14",
      y: "12.5",
      textAnchor: "middle"
    }, e.sourcePort)) : null, e.poeW > 0 && g.mx ? /*#__PURE__*/React.createElement("g", {
      transform: `translate(${g.lx - 14 - 50},${g.ly - 9})`
    }, /*#__PURE__*/React.createElement("rect", {
      width: "44",
      height: "18",
      rx: "9",
      fill: "#ffd60a"
    }), /*#__PURE__*/React.createElement("text", {
      x: "22",
      y: "12.5",
      textAnchor: "middle",
      fontSize: "10",
      fontWeight: "700",
      fill: "#000"
    }, "\u26A1", e.poeW, "W")) : null, e.label && (e.manual || e.kind === 'wan') ? /*#__PURE__*/React.createElement("text", {
      x: g.lx,
      y: g.ly - 14,
      fontSize: "11",
      fill: "var(--text2)",
      textAnchor: "middle"
    }, e.label) : null);
  }), Object.values(L.nodes).map(n => {
    const p = L.pos[n.id];
    if (!p || p.rack) return null;
    return /*#__PURE__*/React.createElement(MapNode, {
      key: n.id,
      n: n,
      p: p,
      sel: sel === n.id || searchHit.includes(n.id) || linking === n.id,
      dim: pathSet && !pathSet.has(n.id),
      mark: spofSet && spofSet.has(n.id),
      onDown: e => nodeDown(n.id, e),
      onClick: () => nodeClick(n.id)
    });
  }))), /*#__PURE__*/React.createElement("div", {
    className: "map-legend legend"
  }, /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: 'var(--green)'
    }
  }), "1 \u0413\u0431\u0438\u0442"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: 'var(--yellow)'
    }
  }), "100 \u041C\u0431\u0438\u0442"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: 'var(--accent)'
    }
  }), "Wi-Fi"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: 'var(--teal)'
    }
  }), "Mesh"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("i", {
    style: {
      background: 'var(--purple)'
    }
  }), "\u0418\u043D\u0442\u0435\u0440\u043D\u0435\u0442"), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("b", {
    style: {
      color: '#ffd60a'
    }
  }, "\u26A1"), "PoE")), /*#__PURE__*/React.createElement("div", {
    className: "zoom-btns"
  }, /*#__PURE__*/React.createElement("button", {
    className: "btn",
    onClick: () => zoomAt(1.35)
  }, "+"), /*#__PURE__*/React.createElement("button", {
    className: "btn",
    onClick: () => zoomAt(1 / 1.35)
  }, "\u2212")), healthOpen && data.health ? /*#__PURE__*/React.createElement("div", {
    className: "card pad fade-in health-panel"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      marginBottom: 4
    }
  }, /*#__PURE__*/React.createElement("b", {
    className: "grow",
    style: {
      fontSize: 16
    }
  }, "\u0410\u043D\u0430\u043B\u0438\u0437 \u0441\u0435\u0442\u0438"), /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "x",
    onClick: () => setHealthOpen(false)
  })), /*#__PURE__*/React.createElement(HealthBody, {
    h: data.health,
    onCheck: c => {
      if (c.nodeId && L.nodes[c.nodeId] && !c.port) {
        setSel(c.nodeId);
        if (innerWidth < 760) setHealthOpen(false);
      } else openCheck(c);
    },
    onNode: id => {
      if (L.nodes[id]) {
        setSel(id);
        if (innerWidth < 760) setHealthOpen(false);
      }
    }
  })) : null, selNode ? /*#__PURE__*/React.createElement(NodeInfo, {
    n: selNode,
    L: L,
    data: data,
    devById: devById,
    onOpen: openDevice,
    onClose: () => setSel(null)
  }) : null);
}
function RackBox({
  L,
  data,
  devById,
  dimSet,
  markSet,
  onOpen,
  total
}) {
  const h = total * M.RU;
  return /*#__PURE__*/React.createElement("g", {
    className: "rackbox"
  }, /*#__PURE__*/React.createElement("rect", {
    className: "frame",
    x: -14,
    y: -46,
    width: M.RW + 28,
    height: h + 60,
    rx: 16
  }), /*#__PURE__*/React.createElement("text", {
    x: 0,
    y: -22,
    fontSize: "14",
    fontWeight: "700"
  }, data.settings.title), /*#__PURE__*/React.createElement("text", {
    x: M.RW,
    y: -22,
    fontSize: "11",
    textAnchor: "end",
    className: "usub"
  }, total, "U"), Array.from({
    length: total
  }, (_, i) => /*#__PURE__*/React.createElement("text", {
    key: i,
    x: -7,
    y: i * M.RU + M.RU / 2 + 3,
    fontSize: "8",
    textAnchor: "middle",
    className: "usub"
  }, i + 1)), L.units.filter(u => (u.side || 'front') === 'front').map(u => {
    const d = devById[u.deviceId];
    const st = d && d.state;
    const y = (u.uStart - 1) * M.RU;
    const hh = u.uSize * M.RU - 4;
    const dim = dimSet && !(d && dimSet.has('d:' + d.id));
    const kind = PASSIVE.includes(u.type) ? u.type : d && d.kind || u.type;
    return /*#__PURE__*/React.createElement("g", {
      key: u.id,
      className: 'u' + (dim ? ' dim-out' : ''),
      style: {
        cursor: d ? 'pointer' : 'default'
      },
      onClick: () => d && onOpen(d)
    }, /*#__PURE__*/React.createElement("rect", {
      x: 0,
      y: y,
      width: M.RW,
      height: hh,
      rx: 6
    }), d && markSet && markSet.has('d:' + d.id) ? /*#__PURE__*/React.createElement("rect", {
      className: "spof-mark",
      x: -3,
      y: y - 3,
      width: M.RW + 6,
      height: hh + 6,
      rx: 8
    }) : null, /*#__PURE__*/React.createElement("rect", {
      x: 0,
      y: y,
      width: 4,
      height: hh,
      rx: 2,
      fill: u.color || '#0a84ff',
      stroke: "none"
    }), /*#__PURE__*/React.createElement("g", {
      transform: `translate(12,${y + hh / 2 - 9})`
    }, /*#__PURE__*/React.createElement(Icon, {
      name: kind,
      size: 18,
      color: "#f5f5f7"
    })), /*#__PURE__*/React.createElement("text", {
      x: 38,
      y: y + (hh > 30 ? hh / 2 - 2 : hh / 2 + 4),
      fontSize: "12.5",
      fontWeight: "600"
    }, trunc(u.name, 30)), hh > 30 ? /*#__PURE__*/React.createElement("text", {
      x: 38,
      y: y + hh / 2 + 12,
      className: "usub"
    }, trunc(d ? deviceLine(d) : KIND_TEXT[u.type], 40)) : null, st ? /*#__PURE__*/React.createElement("circle", {
      cx: M.RW - 12,
      cy: y + 11,
      r: 4,
      fill: st.status === 'online' ? 'var(--green)' : st.status === 'warning' ? 'var(--orange)' : 'var(--red)'
    }) : null, st && (st.ports || []).length > 4 ? /*#__PURE__*/React.createElement("g", {
      transform: `translate(${M.RW - 14 - Math.ceil(Math.min(st.ports.length, 28) / 2) * 7},${y + hh - 17})`
    }, st.ports.slice(0, 28).map((p, i) => /*#__PURE__*/React.createElement("rect", {
      key: i,
      x: Math.floor(i / 2) * 7,
      y: i % 2 * 7,
      width: 5,
      height: 5,
      rx: 1,
      fill: !p.link ? '#3a3a3c' : p.speed >= 1000 ? '#30d158' : p.speed >= 100 ? '#ffd60a' : '#ff9f0a',
      stroke: "none"
    }))) : null);
  }));
}
function NodeInfo({
  n,
  L,
  data,
  devById,
  onOpen,
  onClose
}) {
  const pe = L.edges.find(e => e.target === n.id && !e.extra);
  const parent = pe && L.nodes[pe.source];
  const dev = n.deviceId && devById[n.deviceId];
  const client = n.mac && data.devices.flatMap(d => d.state && d.state.clients || []).find(c => (c.mac || '').toLowerCase() === n.mac);
  const conn = pe ? pe.kind === 'wifi' ? `Wi-Fi · ${parent ? parent.label : ''}${pe.band ? ' · ' + pe.band : ''}${pe.rssi ? ' · ' + pe.rssi + ' дБм' : ''}` : pe.kind === 'mesh' ? 'Mesh (беспроводной)' : pe.kind === 'remote' ? 'Через интернет' : `${parent ? parent.label : ''}${pe.sourcePort ? ', порт ' + pe.sourcePort : ''}${pe.speed ? ' · ' + fmt.speed(pe.speed) : ''}` : '';
  return /*#__PURE__*/React.createElement("div", {
    className: "card pad fade-in node-info"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: n.kind,
    size: 40
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700
    },
    className: "ellipsis"
  }, n.label), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 12.5
    }
  }, KIND_TEXT[n.kind] || '', n.model ? ' · ' + n.model : '')), /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "x",
    onClick: onClose
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement(KV, {
    rows: [['IP', n.sub ? /*#__PURE__*/React.createElement("span", {
      className: "mono"
    }, n.sub) : null], ...(n.mac ? [['MAC', /*#__PURE__*/React.createElement("span", {
      className: "mono"
    }, n.mac)]] : []), ...(client && client.segment ? [['Сеть', client.segment]] : []), ['Подключение', conn], ...(pe && pe.poeW ? [['PoE', pe.poeW + ' Вт']] : []), ...(dev ? [['Состояние', STATUS_TEXT[(dev.state || {}).status]]] : [])]
  })), dev ? /*#__PURE__*/React.createElement(Btn, {
    kind: "primary",
    style: {
      width: '100%',
      marginTop: 12
    },
    onClick: () => onOpen(dev)
  }, "\u041F\u043E\u0434\u0440\u043E\u0431\u043D\u0435\u0435") : null, !dev && pe && pe.sourcePort && parent && parent.deviceId ? /*#__PURE__*/React.createElement(Btn, {
    style: {
      width: '100%',
      marginTop: 12
    },
    onClick: () => onOpen(devById[parent.deviceId], 'ports', pe.sourcePort)
  }, "\u041F\u043E\u0440\u0442 ", pe.sourcePort, " \u043D\u0430 ", parent.label) : null);
}

/* ── 45_health.jsx ── */
/* Network health: topology type, single points of failure, findings */
const ruPlural = (n, one, few, many) => {
  const a = n % 10,
    b = n % 100;
  return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
};
const TOPO_PICS = {
  single: {
    n: [[30, 22], [10, 8], [50, 8], [10, 36], [50, 36]],
    e: [[0, 1], [0, 2], [0, 3], [0, 4]]
  },
  star: {
    n: [[30, 22], [30, 4], [48, 12], [48, 32], [30, 40], [12, 32], [12, 12]],
    e: [[0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [0, 6]]
  },
  tree: {
    n: [[30, 5], [16, 21], [44, 21], [7, 38], [23, 38], [37, 38], [53, 38]],
    e: [[0, 1], [0, 2], [1, 3], [1, 4], [2, 5], [2, 6]]
  },
  chain: {
    n: [[6, 16], [22, 16], [38, 16], [54, 16], [6, 36], [22, 36], [38, 36], [54, 36]],
    e: [[0, 1], [1, 2], [2, 3], [0, 4], [1, 5], [2, 6], [3, 7]]
  },
  ring: {
    n: [[30, 4], [49, 17], [42, 39], [18, 39], [11, 17]],
    e: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]]
  },
  mesh: {
    n: [[30, 4], [49, 17], [42, 39], [18, 39], [11, 17]],
    e: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0], [0, 2], [0, 3], [1, 3], [1, 4], [2, 4]]
  }
};
function TopoPic({
  id,
  on
}) {
  const p = TOPO_PICS[id];
  const c = on ? 'var(--accent)' : 'var(--text3)';
  return /*#__PURE__*/React.createElement("svg", {
    width: "60",
    height: "44",
    viewBox: "0 0 60 44"
  }, p.e.map(([a, b], i) => /*#__PURE__*/React.createElement("line", {
    key: i,
    x1: p.n[a][0],
    y1: p.n[a][1],
    x2: p.n[b][0],
    y2: p.n[b][1],
    stroke: c,
    strokeWidth: "1.4",
    opacity: ".7"
  })), p.n.map(([x, y], i) => /*#__PURE__*/React.createElement("circle", {
    key: i,
    cx: x,
    cy: y,
    r: i === 0 && id !== 'ring' && id !== 'mesh' && id !== 'chain' ? 4.5 : 3.2,
    fill: c
  })));
}
function ScoreRing({
  score,
  size = 76
}) {
  const r = size / 2 - 6,
    L = 2 * Math.PI * r;
  const col = score >= 85 ? 'var(--green)' : score >= 60 ? 'var(--orange)' : 'var(--red)';
  return /*#__PURE__*/React.createElement("div", {
    className: "score-ring",
    style: {
      width: size,
      height: size
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size
  }, /*#__PURE__*/React.createElement("circle", {
    cx: size / 2,
    cy: size / 2,
    r: r,
    stroke: "var(--line)",
    strokeWidth: "7",
    fill: "none"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: size / 2,
    cy: size / 2,
    r: r,
    stroke: col,
    strokeWidth: "7",
    fill: "none",
    strokeLinecap: "round",
    strokeDasharray: `${L * score / 100} ${L}`,
    transform: `rotate(-90 ${size / 2} ${size / 2})`,
    style: {
      transition: 'stroke-dasharray .8s'
    }
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", {
    style: {
      fontSize: size * .3
    }
  }, score), /*#__PURE__*/React.createElement("small", null, "\u0438\u0437 100")));
}
const CHECK_LOOK = {
  bad: ['var(--red)', 'alert'],
  warn: ['var(--orange)', 'alert'],
  info: ['var(--accent)', 'other'],
  ok: ['var(--green)', 'check']
};
function CheckItem({
  c,
  onClick
}) {
  const [col, icon] = CHECK_LOOK[c.level] || CHECK_LOOK.info;
  const clickable = onClick && (c.deviceId || c.nodeId);
  return /*#__PURE__*/React.createElement("div", {
    className: 'li check-item' + (clickable ? ' click' : ''),
    onClick: () => clickable && onClick(c)
  }, /*#__PURE__*/React.createElement("div", {
    className: "check-ic",
    style: {
      color: col,
      background: `color-mix(in srgb, ${col} 14%, transparent)`
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: icon,
    size: 16
  })), /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 650,
      fontSize: 14
    }
  }, c.title), c.text ? /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 12.8,
      lineHeight: 1.4,
      marginTop: 2
    }
  }, c.text) : null), clickable ? /*#__PURE__*/React.createElement(Icon, {
    name: "chevron",
    size: 15,
    color: "var(--text3)"
  }) : null);
}
function HealthBody({
  h,
  onCheck,
  onNode
}) {
  const [types, setTypes] = useState(false);
  const t = h.type;
  const st = h.stats;
  return /*#__PURE__*/React.createElement("div", {
    className: "health"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 16,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: h.score
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 11.5,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '.4px'
    }
  }, "\u0422\u043E\u043F\u043E\u043B\u043E\u0433\u0438\u044F"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 18,
      fontWeight: 750,
      letterSpacing: '-.3px',
      lineHeight: 1.2
    }
  }, t.name), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13,
      marginTop: 3
    }
  }, t.what)), /*#__PURE__*/React.createElement(TopoPic, {
    id: t.id,
    on: true
  })), /*#__PURE__*/React.createElement("div", {
    className: "row wrap",
    style: {
      gap: 6
    }
  }, [`${st.devices} ${ruPlural(st.devices, 'устройство', 'устройства', 'устройств')}`, `${st.levels} ${ruPlural(st.levels, 'уровень', 'уровня', 'уровней')}`, ...(st.switches ? [`коммутаторов: ${st.switches}`] : []), ...t.traits].map((x, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: "chip",
    style: {
      cursor: 'default'
    }
  }, x))), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13,
      lineHeight: 1.45
    }
  }, t.note), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card-title",
    style: {
      marginBottom: 6
    }
  }, "\u0417\u0430\u043C\u0435\u0447\u0430\u043D\u0438\u044F"), /*#__PURE__*/React.createElement("div", {
    className: "list"
  }, h.checks.map((c, i) => /*#__PURE__*/React.createElement(CheckItem, {
    key: i,
    c: c,
    onClick: onCheck
  })))), h.spof.length ? /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    className: "card-title",
    style: {
      marginBottom: 8
    }
  }, "\u0427\u0442\u043E \u0431\u0443\u0434\u0435\u0442, \u0435\u0441\u043B\u0438 \u0443\u0437\u0435\u043B \u043E\u0442\u043A\u0430\u0436\u0435\u0442"), /*#__PURE__*/React.createElement("div", {
    className: "spof"
  }, h.spof.map(s => /*#__PURE__*/React.createElement("div", {
    key: s.id,
    className: 'spof-row' + (onNode ? ' click' : ''),
    onClick: () => onNode && onNode(s.id)
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: s.kind,
    size: 28,
    round: 8
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "row between",
    style: {
      fontSize: 13.5
    }
  }, /*#__PURE__*/React.createElement("b", {
    className: "ellipsis"
  }, s.label), /*#__PURE__*/React.createElement("span", {
    className: "mono dim"
  }, "\u2212", s.affected)), /*#__PURE__*/React.createElement("div", {
    className: "spof-bar"
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: Math.max(3, s.affected / Math.max(1, st.devices) * 100) + '%'
    }
  })), s.what ? /*#__PURE__*/React.createElement("div", {
    className: "dim3 ellipsis",
    style: {
      fontSize: 11.5,
      marginTop: 3
    }
  }, s.what) : null))))) : null, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("button", {
    className: "link-btn",
    onClick: () => setTypes(!types)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "chevron",
    size: 13,
    style: {
      transform: types ? 'rotate(90deg)' : ''
    }
  }), "\u041A\u0430\u043A\u0438\u0435 \u0431\u044B\u0432\u0430\u044E\u0442 \u0442\u043E\u043F\u043E\u043B\u043E\u0433\u0438\u0438"), types ? /*#__PURE__*/React.createElement("div", {
    className: "topo-types"
  }, t.all.map(x => /*#__PURE__*/React.createElement("div", {
    key: x.id,
    className: 'topo-type' + (x.id === t.id ? ' on' : '')
  }, /*#__PURE__*/React.createElement(TopoPic, {
    id: x.id,
    on: x.id === t.id
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, x.name, x.id === t.id ? ' · у вас' : ''), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 12.3,
      lineHeight: 1.4
    }
  }, x.what, " ", x.note)))), /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 12
    }
  }, "\u0428\u0438\u043D\u0430 (\u0432\u0441\u0435 \u043D\u0430 \u043E\u0434\u043D\u043E\u043C \u043A\u0430\u0431\u0435\u043B\u0435) \u2014 \u0443\u0441\u0442\u0430\u0440\u0435\u0432\u0448\u0430\u044F \u0441\u0445\u0435\u043C\u0430 \u0438\u0437 \u0432\u0440\u0435\u043C\u0451\u043D \u043A\u043E\u0430\u043A\u0441\u0438\u0430\u043B\u0430, \u0432 Ethernet \u0443\u0436\u0435 \u043D\u0435 \u0432\u0441\u0442\u0440\u0435\u0447\u0430\u0435\u0442\u0441\u044F. \u0412 \u0436\u0438\u0437\u043D\u0438 \u0441\u0435\u0442\u0438 \u043F\u043E\u0447\u0442\u0438 \u0432\u0441\u0435\u0433\u0434\u0430 \u0433\u0438\u0431\u0440\u0438\u0434\u043D\u044B\u0435: \u043D\u0430\u043F\u0440\u0438\u043C\u0435\u0440, \u0434\u0435\u0440\u0435\u0432\u043E \u0438\u0437 \u043A\u0430\u0431\u0435\u043B\u0435\u0439 + \u0431\u0435\u0441\u043F\u0440\u043E\u0432\u043E\u0434\u043D\u043E\u0439 mesh.")) : null));
}
function useCheckOpener() {
  const {
    data,
    openDevice
  } = useApp();
  return c => {
    const d = c.deviceId && data.devices.find(x => x.id === c.deviceId);
    if (d) openDevice(d, c.port ? 'ports' : undefined, c.port);
  };
}
function HealthCard() {
  const {
    data
  } = useApp();
  const [open, setOpen] = useState(false);
  const openCheck = useCheckOpener();
  const h = data.health;
  if (!h) return null;
  const top = h.checks.filter(c => c.level !== 'ok').slice(0, 2);
  const nWarn = h.checks.filter(c => c.level === 'bad' || c.level === 'warn').length;
  const n10 = nWarn % 10,
    n100 = nWarn % 100;
  const warnText = !nWarn ? 'Серьёзных замечаний нет' : `${nWarn} ${n10 === 1 && n100 !== 11 ? 'замечание требует' : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? 'замечания требуют' : 'замечаний требуют'} внимания`;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(Card, {
    title: "\u0417\u0434\u043E\u0440\u043E\u0432\u044C\u0435 \u0441\u0435\u0442\u0438",
    right: /*#__PURE__*/React.createElement(Btn, {
      size: "sm",
      onClick: () => setOpen(true)
    }, "\u041F\u043E\u0434\u0440\u043E\u0431\u043D\u0435\u0435")
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      gap: 14,
      cursor: 'pointer'
    },
    onClick: () => setOpen(true)
  }, /*#__PURE__*/React.createElement(ScoreRing, {
    score: h.score,
    size: 58
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow",
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontWeight: 700
    }
  }, h.type.name), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 12.5
    }
  }, warnText))), top.length ? /*#__PURE__*/React.createElement("div", {
    className: "list",
    style: {
      marginTop: 8
    }
  }, top.map((c, i) => /*#__PURE__*/React.createElement(CheckItem, {
    key: i,
    c: {
      ...c,
      text: ''
    },
    onClick: openCheck
  }))) : null), open ? /*#__PURE__*/React.createElement(Modal, {
    title: "\u0417\u0434\u043E\u0440\u043E\u0432\u044C\u0435 \u0441\u0435\u0442\u0438",
    wide: true,
    onClose: () => setOpen(false)
  }, /*#__PURE__*/React.createElement(HealthBody, {
    h: h,
    onCheck: c => {
      setOpen(false);
      openCheck(c);
    }
  })) : null);
}

/* ── 50_devices.jsx ── */
/* Devices list and the add / edit wizard */
function DevicesView() {
  const {
    data,
    admin,
    edit,
    openDevice,
    openEditor
  } = useApp();
  const [flt, setFlt] = useState('all');
  const [q, setQ] = useState('');
  const drvTitle = id => (data.drivers.find(d => d.id === id) || {}).title || id;
  const list = data.devices.filter(d => {
    const s = (d.state || {}).status;
    if (flt === 'problems' && !['offline', 'warning'].includes(s)) return false;
    if (flt === 'remote' && d.location !== 'remote') return false;
    if (flt === 'local' && d.location === 'remote') return false;
    return !q || [d.name, d.host, (d.state && d.state.summary || {}).ip, d.site].join(' ').toLowerCase().includes(q.toLowerCase());
  });
  const sites = [...new Set(data.devices.map(d => d.site).filter(Boolean))];
  const counts = {
    all: data.devices.length,
    problems: data.devices.filter(d => ['offline', 'warning'].includes((d.state || {}).status)).length,
    local: data.devices.filter(d => d.location !== 'remote').length,
    remote: data.devices.filter(d => d.location === 'remote').length
  };
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "row wrap",
    style: {
      marginBottom: 14
    }
  }, [['all', 'Все'], ['problems', 'Проблемы'], ['local', 'Локальные'], ['remote', 'Удалённые']].map(([k, l]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: 'chip' + (flt === k ? ' on' : ''),
    onClick: () => setFlt(k)
  }, l, " \xB7 ", counts[k])), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      width: 240
    }
  }, /*#__PURE__*/React.createElement(SearchBox, {
    value: q,
    onChange: setQ
  })), admin ? /*#__PURE__*/React.createElement(Btn, {
    kind: "primary",
    icon: "plus",
    onClick: () => openEditor(null)
  }, "\u0414\u043E\u0431\u0430\u0432\u0438\u0442\u044C") : null), !data.devices.length ? /*#__PURE__*/React.createElement(Card, null, /*#__PURE__*/React.createElement("div", {
    className: "empty",
    style: {
      padding: 50
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 40,
      marginBottom: 10
    }
  }, "\uD83D\uDEF0\uFE0F"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 17,
      fontWeight: 600,
      color: 'var(--text)'
    }
  }, "\u041F\u043E\u043A\u0430 \u043D\u0435\u0442 \u043D\u0438 \u043E\u0434\u043D\u043E\u0433\u043E \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430"), /*#__PURE__*/React.createElement("div", {
    style: {
      margin: '6px 0 16px'
    }
  }, "\u0414\u043E\u0431\u0430\u0432\u044C\u0442\u0435 \u0440\u043E\u0443\u0442\u0435\u0440, \u043A\u043E\u043C\u043C\u0443\u0442\u0430\u0442\u043E\u0440, NAS \u0438\u043B\u0438 \u043B\u044E\u0431\u043E\u0439 \u0441\u0435\u0440\u0432\u0435\u0440 \u2014 \u0434\u0430\u043D\u043D\u044B\u0435 \u043D\u0430\u0447\u043D\u0443\u0442 \u0441\u043E\u0431\u0438\u0440\u0430\u0442\u044C\u0441\u044F \u0430\u0432\u0442\u043E\u043C\u0430\u0442\u0438\u0447\u0435\u0441\u043A\u0438."), admin ? /*#__PURE__*/React.createElement(Btn, {
    kind: "primary",
    icon: "plus",
    onClick: () => openEditor(null)
  }, "\u0414\u043E\u0431\u0430\u0432\u0438\u0442\u044C \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E") : null)) : null, (sites.length ? [...sites, ''] : ['']).map(site => {
    const items = list.filter(d => (d.site || '') === site);
    if (!items.length) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: site || '_',
      style: {
        marginBottom: 20
      }
    }, sites.length ? /*#__PURE__*/React.createElement("div", {
      className: "card-title",
      style: {
        margin: '4px 2px 10px'
      }
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "globe",
      size: 14
    }), site || 'Локальная сеть') : null, /*#__PURE__*/React.createElement("div", {
      className: "grid cards"
    }, items.map(d => {
      const st = d.state || {};
      const s = st.summary || {};
      return /*#__PURE__*/React.createElement("div", {
        key: d.id,
        className: "card dev-card fade-in",
        onClick: () => openDevice(d)
      }, /*#__PURE__*/React.createElement("div", {
        className: "row"
      }, /*#__PURE__*/React.createElement(KindIcon, {
        kind: d.kind,
        size: 42,
        round: 12
      }), /*#__PURE__*/React.createElement("div", {
        className: "grow",
        style: {
          minWidth: 0
        }
      }, /*#__PURE__*/React.createElement("div", {
        style: {
          fontWeight: 700,
          fontSize: 15.5
        },
        className: "ellipsis"
      }, d.name), /*#__PURE__*/React.createElement("div", {
        className: "dim ellipsis",
        style: {
          fontSize: 12.5
        }
      }, drvTitle(d.driver), s.ip ? ' · ' + s.ip : '')), /*#__PURE__*/React.createElement(StatusBadge, {
        status: st.status
      })), /*#__PURE__*/React.createElement("div", {
        className: "dim ellipsis",
        style: {
          fontSize: 13,
          marginTop: 10,
          minHeight: 18
        }
      }, deviceLine(d) || s.model || ''), /*#__PURE__*/React.createElement("div", {
        className: "row between dim3",
        style: {
          fontSize: 12,
          marginTop: 6
        }
      }, /*#__PURE__*/React.createElement("span", null, d.location === 'remote' ? 'Удалённое' : 'Локальное', d.enabled === false ? ' · выключено' : ''), /*#__PURE__*/React.createElement("span", null, st.updated ? fmt.ago(st.updated, data.now) : '')));
    })));
  }));
}
function DeviceEditor({
  device,
  onClose
}) {
  const {
    data,
    refresh
  } = useApp();
  const toast = useToast();
  const confirm = useConfirm();
  const [drvId, setDrvId] = useState(device ? device.driver : null);
  const drv = data.drivers.find(d => d.id === drvId);
  const [f, setF] = useState(() => device ? {
    ...device
  } : {
    name: '',
    location: 'local',
    site: '',
    notes: '',
    enabled: true
  });
  const [test, setTest] = useState(null);
  const [token, setToken] = useState(null);
  const set = (k, v) => setF(x => ({
    ...x,
    [k]: v
  }));
  useEffect(() => {
    if (drv && !device) {
      setF(x => {
        const n = {
          ...x,
          kind: x.kind || drv.kind
        };
        drv.fields.forEach(fl => {
          if (fl.default && !n[fl.name]) n[fl.name] = fl.default;
        });
        return n;
      });
    }
  }, [drvId]);
  if (!drvId) return /*#__PURE__*/React.createElement(Modal, {
    title: "\u041D\u043E\u0432\u043E\u0435 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E",
    wide: true,
    onClose: onClose
  }, /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 14
    }
  }, "\u041A\u0430\u043A \u043F\u043E\u0434\u043A\u043B\u044E\u0447\u0438\u0442\u044C\u0441\u044F \u043A \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0443?"), /*#__PURE__*/React.createElement("div", {
    className: "driver-pick"
  }, data.drivers.filter(d => !d.hidden).map(d => /*#__PURE__*/React.createElement("button", {
    key: d.id,
    onClick: () => setDrvId(d.id)
  }, /*#__PURE__*/React.createElement(KindIcon, {
    kind: d.kind,
    size: 38
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("b", null, d.title), /*#__PURE__*/React.createElement("small", null, d.description))))));
  const payload = () => {
    const p = {
      ...f,
      driver: drvId
    };
    delete p.state;
    Object.keys(p).filter(k => k.endsWith('Set')).forEach(k => delete p[k]);
    return p;
  };
  const doTest = async () => {
    setTest({
      busy: true
    });
    try {
      const r = await api('/api/test', {
        method: 'POST',
        body: payload()
      });
      setTest(r);
    } catch (e) {
      setTest({
        ok: false,
        error: e.message
      });
    }
  };
  const save = async () => {
    const missing = drv.fields.filter(fl => fl.required && !f[fl.name] && !(device && device[fl.name + 'Set']));
    if (!f.name.trim()) return toast('Укажите название', true);
    if (missing.length) return toast('Заполните: ' + missing.map(m => m.label).join(', '), true);
    try {
      const r = device ? await api('/api/devices/' + device.id, {
        method: 'PUT',
        body: payload()
      }) : await api('/api/devices', {
        method: 'POST',
        body: payload()
      });
      refresh();
      if (r.agentToken) {
        setToken({
          token: r.agentToken,
          id: r.device.id
        });
        return;
      }
      toast(device ? 'Сохранено' : 'Устройство добавлено');
      onClose();
    } catch (e) {
      toast(e.message, true);
    }
  };
  const del = async () => {
    if (!(await confirm(`Удалить «${device.name}»? История и связи на карте будут удалены.`, {
      danger: true,
      ok: 'Удалить'
    }))) return;
    await api('/api/devices/' + device.id, {
      method: 'DELETE'
    });
    refresh();
    toast('Удалено');
    onClose();
  };
  if (token) return /*#__PURE__*/React.createElement(AgentInstall, {
    token: token.token,
    onClose: onClose
  });
  return /*#__PURE__*/React.createElement(Modal, {
    title: device ? 'Настройки устройства' : drv.title,
    wide: true,
    onClose: onClose,
    icon: /*#__PURE__*/React.createElement(KindIcon, {
      kind: f.kind || drv.kind
    }),
    footer: /*#__PURE__*/React.createElement(React.Fragment, null, device ? /*#__PURE__*/React.createElement(Btn, {
      kind: "danger",
      icon: "trash",
      onClick: del
    }, "\u0423\u0434\u0430\u043B\u0438\u0442\u044C") : /*#__PURE__*/React.createElement(Btn, {
      onClick: () => setDrvId(null)
    }, "\u041D\u0430\u0437\u0430\u0434"), /*#__PURE__*/React.createElement("div", {
      className: "grow"
    }), drvId !== 'agent' ? /*#__PURE__*/React.createElement(Btn, {
      onClick: doTest,
      busy: test && test.busy
    }, "\u041F\u0440\u043E\u0432\u0435\u0440\u0438\u0442\u044C") : null, /*#__PURE__*/React.createElement(Btn, {
      kind: "primary",
      onClick: save
    }, "\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C"))
  }, drv.description ? /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13.5
    }
  }, drv.description) : null, /*#__PURE__*/React.createElement("div", {
    className: "grid",
    style: {
      gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))'
    }
  }, /*#__PURE__*/React.createElement(Field, {
    label: "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.name,
    onChange: e => set('name', e.target.value),
    placeholder: "\u041D\u0430\u043F\u0440\u0438\u043C\u0435\u0440, \u0420\u043E\u0443\u0442\u0435\u0440 \u0434\u043E\u043C\u0430"
  })), /*#__PURE__*/React.createElement(Field, {
    label: "\u0422\u0438\u043F (\u0438\u043A\u043E\u043D\u043A\u0430)"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: f.kind || drv.kind,
    onChange: e => set('kind', e.target.value)
  }, DEVICE_KINDS.map(k => /*#__PURE__*/React.createElement("option", {
    key: k,
    value: k
  }, KIND_TEXT[k])))), drv.fields.map(fl => /*#__PURE__*/React.createElement(Field, {
    key: fl.name,
    label: fl.label,
    hint: fl.hint
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: fl.type === 'password' ? 'password' : 'text',
    value: f[fl.name] || '',
    onChange: e => set(fl.name, e.target.value),
    placeholder: fl.secret && device && device[fl.name + 'Set'] ? '•••••••• (не менять)' : fl.placeholder || '',
    autoComplete: "off"
  }))), /*#__PURE__*/React.createElement(Field, {
    label: "\u0420\u0430\u0441\u043F\u043E\u043B\u043E\u0436\u0435\u043D\u0438\u0435"
  }, /*#__PURE__*/React.createElement(Seg, {
    value: f.location || 'local',
    onChange: v => set('location', v),
    options: [{
      value: 'local',
      label: 'Локальное'
    }, {
      value: 'remote',
      label: 'Удалённое'
    }]
  })), /*#__PURE__*/React.createElement(Field, {
    label: "\u041F\u043B\u043E\u0449\u0430\u0434\u043A\u0430 / \u043E\u0431\u044A\u0435\u043A\u0442",
    hint: "\u041D\u0430\u043F\u0440\u0438\u043C\u0435\u0440 \xAB\u0414\u0430\u0447\u0430\xBB \u0438\u043B\u0438 \xAB\u041E\u0444\u0438\u0441\xBB \u2014 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 \u0433\u0440\u0443\u043F\u043F\u0438\u0440\u0443\u044E\u0442\u0441\u044F \u043F\u043E \u043F\u043B\u043E\u0449\u0430\u0434\u043A\u0430\u043C"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: f.site || '',
    onChange: e => set('site', e.target.value)
  }))), /*#__PURE__*/React.createElement(Field, {
    label: "\u0417\u0430\u043C\u0435\u0442\u043A\u0438"
  }, /*#__PURE__*/React.createElement("textarea", {
    className: "textarea",
    value: f.notes || '',
    onChange: e => set('notes', e.target.value)
  })), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Switch, {
    on: f.enabled !== false,
    onChange: v => set('enabled', v)
  }), /*#__PURE__*/React.createElement("span", null, "\u041E\u043F\u0440\u0430\u0448\u0438\u0432\u0430\u0442\u044C \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u043E")), device && drvId === 'agent' ? /*#__PURE__*/React.createElement(AgentInstallInline, {
    device: device
  }) : null, test && !test.busy ? /*#__PURE__*/React.createElement("div", {
    className: "card pad",
    style: {
      borderColor: test.ok ? 'var(--green)' : 'var(--red)'
    }
  }, test.ok ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      color: 'var(--green)',
      fontWeight: 700
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check"
  }), "\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435 \u0440\u0430\u0431\u043E\u0442\u0430\u0435\u0442"), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13.5,
      marginTop: 6
    }
  }, [test.summary.model, test.summary.fw, test.summary.ip].filter(Boolean).join(' · '), test.ports ? ` · портов: ${test.ports}` : '', test.clients ? ` · клиентов: ${test.clients}` : '')) : /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--red)'
    }
  }, /*#__PURE__*/React.createElement("b", null, "\u041D\u0435 \u043F\u043E\u043B\u0443\u0447\u0438\u043B\u043E\u0441\u044C:"), " ", test.error)) : null);
}
function agentCommand(token) {
  const base = location.origin;
  return `curl -fsSL ${base}/agent.py -o /opt/racklive-agent.py\npython3 /opt/racklive-agent.py --server ${base} --token ${token} --install`;
}
function AgentInstall({
  token,
  onClose
}) {
  return /*#__PURE__*/React.createElement(Modal, {
    title: "\u0423\u0441\u0442\u0430\u043D\u043E\u0432\u043A\u0430 \u0430\u0433\u0435\u043D\u0442\u0430",
    onClose: onClose,
    footer: /*#__PURE__*/React.createElement(Btn, {
      kind: "primary",
      onClick: onClose
    }, "\u0413\u043E\u0442\u043E\u0432\u043E")
  }, /*#__PURE__*/React.createElement("div", null, "\u0412\u044B\u043F\u043E\u043B\u043D\u0438\u0442\u0435 \u043D\u0430 \u0443\u0434\u0430\u043B\u0451\u043D\u043D\u043E\u043C \u0441\u0435\u0440\u0432\u0435\u0440\u0435 (Linux, \u043D\u0443\u0436\u0435\u043D Python 3). \u0410\u0433\u0435\u043D\u0442 \u0431\u0443\u0434\u0435\u0442 \u043A\u0430\u0436\u0434\u044B\u0435 60 \u0441\u0435\u043A\u0443\u043D\u0434 \u043E\u0442\u043F\u0440\u0430\u0432\u043B\u044F\u0442\u044C \u0434\u0430\u043D\u043D\u044B\u0435 \u2014 \u043E\u0442\u043A\u0440\u044B\u0432\u0430\u0442\u044C \u043F\u043E\u0440\u0442\u044B \u043D\u0430 \u0441\u0435\u0440\u0432\u0435\u0440\u0435 \u043D\u0435 \u043D\u0443\u0436\u043D\u043E."), /*#__PURE__*/React.createElement("div", {
    className: "code"
  }, agentCommand(token)), /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13
    }
  }, "\u0421\u0435\u0440\u0432\u0435\u0440 Rack Live \u0434\u043E\u043B\u0436\u0435\u043D \u0431\u044B\u0442\u044C \u0434\u043E\u0441\u0442\u0443\u043F\u0435\u043D \u0441 \u0443\u0434\u0430\u043B\u0451\u043D\u043D\u043E\u0439 \u043C\u0430\u0448\u0438\u043D\u044B \u043F\u043E \u044D\u0442\u043E\u043C\u0443 \u0430\u0434\u0440\u0435\u0441\u0443. \u0415\u0441\u043B\u0438 \u0430\u0434\u0440\u0435\u0441 \u0432\u043D\u0443\u0442\u0440\u0435\u043D\u043D\u0438\u0439 \u2014 \u0443\u043A\u0430\u0436\u0438\u0442\u0435 \u0432\u043D\u0435\u0448\u043D\u0438\u0439 \u0434\u043E\u043C\u0435\u043D \u0432 \u043A\u043E\u043C\u0430\u043D\u0434\u0435."));
}
function AgentInstallInline({
  device
}) {
  const [tok, setTok] = useState(null);
  return /*#__PURE__*/React.createElement(Card, {
    title: "\u0410\u0433\u0435\u043D\u0442"
  }, tok ? /*#__PURE__*/React.createElement("div", {
    className: "code"
  }, agentCommand(tok)) : /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    onClick: async () => setTok((await api(`/api/devices/${device.id}/token`, {
      method: 'POST'
    })).agentToken)
  }, "\u041F\u043E\u043A\u0430\u0437\u0430\u0442\u044C \u043A\u043E\u043C\u0430\u043D\u0434\u0443 \u0443\u0441\u0442\u0430\u043D\u043E\u0432\u043A\u0438"));
}

/* ── 60_settings.jsx ── */
/* Settings, events, login and first-run setup */
function SettingsView() {
  const {
    data,
    refresh,
    logout
  } = useApp();
  const toast = useToast();
  const [s, setS] = useState({
    ...data.settings
  });
  const [pw, setPw] = useState({
    old: '',
    n1: '',
    n2: ''
  });
  const fileRef = useRef(null);
  const set = (k, v) => setS(x => ({
    ...x,
    [k]: v
  }));
  const save = async () => {
    try {
      await api('/api/settings', {
        method: 'PUT',
        body: {
          title: s.title,
          poll: +s.poll,
          publicView: s.publicView,
          showClients: s.showClients,
          vlans: s.vlans
        }
      });
      toast('Сохранено');
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
  };
  const changePw = async () => {
    if (pw.n1 !== pw.n2) return toast('Пароли не совпадают', true);
    try {
      await api('/api/settings', {
        method: 'PUT',
        body: {
          oldPassword: pw.old,
          newPassword: pw.n1
        }
      });
      toast('Пароль изменён');
      setPw({
        old: '',
        n1: '',
        n2: ''
      });
    } catch (e) {
      toast(e.message, true);
    }
  };
  const importFile = async e => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    let obj = null;
    try {
      obj = JSON.parse(text);
    } catch (_) {
      const m = text.match(/window\.__SAVED__=(\{[\s\S]*?\});(?=<)/);
      if (m) obj = JSON.parse(m[1]);
    }
    if (!obj) return toast('Не удалось прочитать файл', true);
    try {
      await api('/api/import', {
        method: 'POST',
        body: {
          data: obj
        }
      });
      toast(obj.version === 2 ? 'Резервная копия восстановлена' : 'Схема шкафа импортирована');
      refresh();
    } catch (er) {
      toast(er.message, true);
    }
    e.target.value = '';
  };
  const vl = s.vlans || [];
  return /*#__PURE__*/React.createElement("div", {
    className: "grid",
    style: {
      gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement(Card, {
    title: "\u041E\u0431\u0449\u0438\u0435"
  }, /*#__PURE__*/React.createElement("div", {
    className: "col",
    style: {
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(Field, {
    label: "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: s.title,
    onChange: e => set('title', e.target.value)
  })), /*#__PURE__*/React.createElement(Field, {
    label: "\u0418\u043D\u0442\u0435\u0440\u0432\u0430\u043B \u043E\u043F\u0440\u043E\u0441\u0430",
    hint: "\u041A\u0430\u043A \u0447\u0430\u0441\u0442\u043E \u0441\u043E\u0431\u0438\u0440\u0430\u0442\u044C \u0434\u0430\u043D\u043D\u044B\u0435 \u0441 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: s.poll,
    onChange: e => set('poll', +e.target.value)
  }, [15, 30, 60, 120, 300].map(n => /*#__PURE__*/React.createElement("option", {
    key: n,
    value: n
  }, n < 60 ? n + ' секунд' : n / 60 + ' мин')))), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Switch, {
    on: !!s.publicView,
    onChange: v => set('publicView', v)
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", null, "\u041F\u0440\u043E\u0441\u043C\u043E\u0442\u0440 \u0431\u0435\u0437 \u043F\u0430\u0440\u043E\u043B\u044F"), /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 12.5
    }
  }, "\u0421\u0445\u0435\u043C\u0443 \u0438 \u0441\u0442\u0430\u0442\u0443\u0441\u044B \u0432\u0438\u0434\u043D\u043E \u0432\u0441\u0435\u043C, \u043A\u0442\u043E \u043E\u0442\u043A\u0440\u043E\u0435\u0442 \u0430\u0434\u0440\u0435\u0441. \u0423\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u0435 \u2014 \u0442\u043E\u043B\u044C\u043A\u043E \u043F\u043E\u0441\u043B\u0435 \u0432\u0445\u043E\u0434\u0430."))), /*#__PURE__*/React.createElement("div", {
    className: "row"
  }, /*#__PURE__*/React.createElement(Switch, {
    on: s.showClients !== false,
    onChange: v => set('showClients', v)
  }), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", null, "\u041A\u043B\u0438\u0435\u043D\u0442\u044B \u043D\u0430 \u043A\u0430\u0440\u0442\u0435"), /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 12.5
    }
  }, "\u041F\u043E\u043A\u0430\u0437\u044B\u0432\u0430\u0442\u044C \u0442\u0435\u043B\u0435\u0444\u043E\u043D\u044B, \u043A\u0430\u043C\u0435\u0440\u044B \u0438 \u0434\u0440\u0443\u0433\u0438\u0435 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430, \u0430 \u043D\u0435 \u0442\u043E\u043B\u044C\u043A\u043E \u043E\u0431\u043E\u0440\u0443\u0434\u043E\u0432\u0430\u043D\u0438\u0435"))), /*#__PURE__*/React.createElement(Btn, {
    kind: "primary",
    onClick: save
  }, "\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C"))), /*#__PURE__*/React.createElement(Card, {
    title: "VLAN",
    right: /*#__PURE__*/React.createElement(Btn, {
      size: "sm",
      icon: "plus",
      onClick: () => set('vlans', [...vl, {
        vid: vl.length ? Math.max(...vl.map(v => +v.vid)) + 1 : 1,
        name: '',
        color: '#8e8e93'
      }])
    })
  }, /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13,
      marginBottom: 10
    }
  }, "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u044F \u0438 \u0446\u0432\u0435\u0442\u0430 VLAN \u0434\u043B\u044F \u043F\u043E\u0440\u0442\u043E\u0432 \u0438 \u043A\u0430\u0440\u0442\u044B"), /*#__PURE__*/React.createElement("div", {
    className: "col"
  }, vl.map((v, i) => /*#__PURE__*/React.createElement("div", {
    className: "row",
    key: i
  }, /*#__PURE__*/React.createElement("input", {
    className: "input mono",
    style: {
      width: 70
    },
    value: v.vid,
    onChange: e => set('vlans', vl.map((x, j) => j === i ? {
      ...x,
      vid: +e.target.value || ''
    } : x))
  }), /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: v.name,
    placeholder: "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435",
    onChange: e => set('vlans', vl.map((x, j) => j === i ? {
      ...x,
      name: e.target.value
    } : x))
  }), /*#__PURE__*/React.createElement("input", {
    type: "color",
    value: v.color,
    onChange: e => set('vlans', vl.map((x, j) => j === i ? {
      ...x,
      color: e.target.value
    } : x)),
    style: {
      width: 40,
      height: 38,
      border: 0,
      background: 'none',
      padding: 0
    }
  }), /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "trash",
    onClick: () => set('vlans', vl.filter((_, j) => j !== i))
  })))), /*#__PURE__*/React.createElement(Btn, {
    style: {
      marginTop: 12
    },
    onClick: save
  }, "\u0421\u043E\u0445\u0440\u0430\u043D\u0438\u0442\u044C VLAN")), /*#__PURE__*/React.createElement(Card, {
    title: "\u041F\u0430\u0440\u043E\u043B\u044C \u0430\u0434\u043C\u0438\u043D\u0438\u0441\u0442\u0440\u0430\u0442\u043E\u0440\u0430"
  }, /*#__PURE__*/React.createElement("div", {
    className: "col",
    style: {
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    placeholder: "\u0422\u0435\u043A\u0443\u0449\u0438\u0439 \u043F\u0430\u0440\u043E\u043B\u044C",
    value: pw.old,
    onChange: e => setPw({
      ...pw,
      old: e.target.value
    })
  }), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    placeholder: "\u041D\u043E\u0432\u044B\u0439 \u043F\u0430\u0440\u043E\u043B\u044C (\u043E\u0442 8 \u0441\u0438\u043C\u0432\u043E\u043B\u043E\u0432)",
    value: pw.n1,
    onChange: e => setPw({
      ...pw,
      n1: e.target.value
    })
  }), /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    placeholder: "\u041F\u043E\u0432\u0442\u043E\u0440\u0438\u0442\u0435 \u043D\u043E\u0432\u044B\u0439 \u043F\u0430\u0440\u043E\u043B\u044C",
    value: pw.n2,
    onChange: e => setPw({
      ...pw,
      n2: e.target.value
    })
  }), /*#__PURE__*/React.createElement(Btn, {
    onClick: changePw,
    disabled: !pw.old || pw.n1.length < 8
  }, "\u0421\u043C\u0435\u043D\u0438\u0442\u044C \u043F\u0430\u0440\u043E\u043B\u044C"))), /*#__PURE__*/React.createElement(Card, {
    title: "\u0420\u0435\u0437\u0435\u0440\u0432\u043D\u0430\u044F \u043A\u043E\u043F\u0438\u044F \u0438 \u0438\u043C\u043F\u043E\u0440\u0442"
  }, /*#__PURE__*/React.createElement("div", {
    className: "col",
    style: {
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "dim",
    style: {
      fontSize: 13.5
    }
  }, "\u041A\u043E\u043F\u0438\u044F \u0441\u043E\u0434\u0435\u0440\u0436\u0438\u0442 \u0443\u0441\u0442\u0440\u043E\u0439\u0441\u0442\u0432\u0430 (\u0441 \u043F\u0430\u0440\u043E\u043B\u044F\u043C\u0438), \u0441\u0445\u0435\u043C\u0443 \u0448\u043A\u0430\u0444\u0430, \u043A\u0430\u0440\u0442\u0443 \u0438 \u043D\u0430\u0441\u0442\u0440\u043E\u0439\u043A\u0438. \u0425\u0440\u0430\u043D\u0438\u0442\u0435 \u0435\u0451 \u0432 \u043D\u0430\u0434\u0451\u0436\u043D\u043E\u043C \u043C\u0435\u0441\u0442\u0435."), /*#__PURE__*/React.createElement("a", {
    className: "btn",
    href: "/api/export"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 17
  }), "\u0421\u043A\u0430\u0447\u0430\u0442\u044C \u0440\u0435\u0437\u0435\u0440\u0432\u043D\u0443\u044E \u043A\u043E\u043F\u0438\u044E"), /*#__PURE__*/React.createElement(Btn, {
    icon: "upload",
    onClick: () => fileRef.current.click()
  }, "\u0412\u043E\u0441\u0441\u0442\u0430\u043D\u043E\u0432\u0438\u0442\u044C \u0438\u043B\u0438 \u0438\u043C\u043F\u043E\u0440\u0442\u0438\u0440\u043E\u0432\u0430\u0442\u044C\u2026"), /*#__PURE__*/React.createElement("div", {
    className: "dim3",
    style: {
      fontSize: 12.5
    }
  }, "\u041F\u043E\u0434\u0445\u043E\u0434\u0438\u0442 \u0440\u0435\u0437\u0435\u0440\u0432\u043D\u0430\u044F \u043A\u043E\u043F\u0438\u044F Rack Live \u0438\u043B\u0438 \u0444\u0430\u0439\u043B server-rack.html / JSON \u0438\u0437 \u0441\u0442\u0430\u0440\u043E\u0433\u043E \xAB\u041A\u043E\u043D\u0441\u0442\u0440\u0443\u043A\u0442\u043E\u0440\u0430 \u0448\u043A\u0430\u0444\u0430\xBB"), /*#__PURE__*/React.createElement("input", {
    ref: fileRef,
    type: "file",
    accept: ".json,.html,application/json,text/html",
    style: {
      display: 'none'
    },
    onChange: importFile
  }))), /*#__PURE__*/React.createElement(Card, {
    title: "\u041E \u043F\u0440\u043E\u0433\u0440\u0430\u043C\u043C\u0435"
  }, /*#__PURE__*/React.createElement(KV, {
    rows: [['Версия', 'Rack Live ' + data.version], ['Драйверы', data.drivers.length], ['Устройств', data.devices.length]]
  }), /*#__PURE__*/React.createElement(Btn, {
    style: {
      marginTop: 12
    },
    icon: "logout",
    onClick: logout
  }, "\u0412\u044B\u0439\u0442\u0438")));
}
function EventsView() {
  const {
    data
  } = useApp();
  const [flt, setFlt] = useState('');
  const ev = data.events.filter(e => !flt || e.level === flt);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "row wrap",
    style: {
      marginBottom: 14
    }
  }, [['', 'Все'], ['offline', 'Сбои'], ['online', 'Восстановления'], ['warning', 'Предупреждения'], ['info', 'Действия']].map(([k, l]) => /*#__PURE__*/React.createElement("button", {
    key: k,
    className: 'chip' + (flt === k ? ' on' : ''),
    onClick: () => setFlt(k)
  }, l))), /*#__PURE__*/React.createElement(EventsList, {
    events: ev
  }));
}
function AuthScreen({
  setup,
  title,
  onDone
}) {
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [t, setT] = useState(title || 'Серверный шкаф');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async e => {
    e.preventDefault();
    setErr('');
    if (setup && pw !== pw2) return setErr('Пароли не совпадают');
    setBusy(true);
    try {
      await api(setup ? '/api/setup' : '/api/login', {
        method: 'POST',
        body: {
          password: pw,
          title: t
        }
      });
      onDone();
    } catch (er) {
      setErr(er.message);
    } finally {
      setBusy(false);
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "auth"
  }, /*#__PURE__*/React.createElement("div", {
    className: "app-bg"
  }), /*#__PURE__*/React.createElement("form", {
    className: "card",
    onSubmit: submit
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand-logo",
    style: {
      width: 64,
      height: 64,
      borderRadius: 18,
      margin: '0 auto'
    }
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "rack",
    size: 34,
    color: "#fff"
  })), /*#__PURE__*/React.createElement("h1", null, setup ? 'Добро пожаловать' : title || 'Rack Live'), /*#__PURE__*/React.createElement("div", {
    className: "dim"
  }, setup ? 'Задайте название и пароль администратора — с ним можно будет добавлять устройства и управлять ими.' : 'Войдите, чтобы продолжить'), /*#__PURE__*/React.createElement("div", {
    className: "col"
  }, setup ? /*#__PURE__*/React.createElement(Field, {
    label: "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    value: t,
    onChange: e => setT(e.target.value)
  })) : null, /*#__PURE__*/React.createElement(Field, {
    label: "\u041F\u0430\u0440\u043E\u043B\u044C"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    autoFocus: true,
    value: pw,
    onChange: e => setPw(e.target.value),
    placeholder: setup ? 'Не короче 8 символов' : ''
  })), setup ? /*#__PURE__*/React.createElement(Field, {
    label: "\u0415\u0449\u0451 \u0440\u0430\u0437"
  }, /*#__PURE__*/React.createElement("input", {
    className: "input",
    type: "password",
    value: pw2,
    onChange: e => setPw2(e.target.value)
  })) : null, err ? /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--red)',
      fontSize: 14
    }
  }, err) : null, /*#__PURE__*/React.createElement("button", {
    className: 'btn primary' + (busy ? ' busy' : ''),
    type: "submit",
    style: {
      padding: 13,
      marginTop: 4
    }
  }, setup ? 'Начать' : 'Войти'))));
}

/* ── 90_app.jsx ── */
/* App shell */
const TABS = [{
  id: 'rack',
  label: 'Шкаф',
  icon: 'rack'
}, {
  id: 'map',
  label: 'Карта сети',
  icon: 'map'
}, {
  id: 'devices',
  label: 'Устройства',
  icon: 'list'
}, {
  id: 'events',
  label: 'События',
  icon: 'bell'
}, {
  id: 'settings',
  label: 'Настройки',
  icon: 'settings',
  admin: true
}];
const lsGet = (k, d) => {
  try {
    return localStorage.getItem(k) || d;
  } catch (e) {
    return d;
  }
};
const lsSet = (k, v) => {
  try {
    localStorage.setItem(k, v);
  } catch (e) {}
};
function useTheme() {
  const [pref, setPref] = useState(lsGet('rl_theme', 'auto'));
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const t = pref === 'auto' ? mq.matches ? 'dark' : 'light' : pref;
      document.documentElement.setAttribute('data-theme', t);
      document.querySelectorAll('meta[name=theme-color]').forEach(m => {
        if (pref === 'auto') {
          m.setAttribute('media', m === document.querySelectorAll('meta[name=theme-color]')[0] ? '(prefers-color-scheme: light)' : '(prefers-color-scheme: dark)');
          m.setAttribute('content', m.getAttribute('media').includes('light') ? '#f2f2f7' : '#000000');
        } else {
          m.removeAttribute('media');
          m.setAttribute('content', t === 'dark' ? '#000000' : '#f2f2f7');
        }
      });
    };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [pref]);
  return [pref, p => {
    setPref(p);
    lsSet('rl_theme', p);
  }];
}
function App() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [tab, setTab] = useState(() => location.hash.slice(1) || lsGet('rl_tab', 'rack'));
  const [mode, setMode] = useState('view');
  const [sheet, setSheet] = useState(null);
  const [editor, setEditor] = useState(undefined);
  const [login, setLogin] = useState(false);
  const [theme, setTheme] = useTheme();
  const toast = useToast();
  const refresh = useCallback(async () => {
    try {
      const d = await api('/api/state');
      setData(d);
      setErr(null);
    } catch (e) {
      setErr(e.message);
    }
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);
  const scrollerRef = useRef(null);
  useEffect(() => {
    location.hash = tab;
    lsSet('rl_tab', tab);
    window.scrollTo(0, 0);
  }, [tab]);
  // deep link: ?device=<id>&tab=ports&port=9 opens the device sheet
  const deep = useRef(new URLSearchParams(location.search));
  useEffect(() => {
    const p = deep.current;
    if (!data || !data.devices || !p.get('device')) return;
    const d = data.devices.find(x => x.id === p.get('device') || x.name === p.get('device'));
    if (d) setSheet({
      id: d.id,
      tab: p.get('tab'),
      port: p.get('port') ? +p.get('port') : null
    });
    deep.current = new URLSearchParams();
  }, [data]);
  useEffect(() => {
    if (data && data.settings && data.settings.title) document.title = data.settings.title + ' · Rack Live';
  }, [data && data.settings && data.settings.title]);
  if (!data) return /*#__PURE__*/React.createElement("div", {
    className: "auth"
  }, /*#__PURE__*/React.createElement("div", {
    className: "app-bg"
  }), err ? /*#__PURE__*/React.createElement("div", {
    className: "card pad"
  }, "\u0421\u0435\u0440\u0432\u0435\u0440 \u043D\u0435\u0434\u043E\u0441\u0442\u0443\u043F\u0435\u043D: ", err, /*#__PURE__*/React.createElement("br", null), /*#__PURE__*/React.createElement(Btn, {
    style: {
      marginTop: 12
    },
    onClick: refresh
  }, "\u041F\u043E\u0432\u0442\u043E\u0440\u0438\u0442\u044C")) : /*#__PURE__*/React.createElement("div", {
    className: "dim"
  }, "\u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430\u2026"));
  if (data.setupNeeded) return /*#__PURE__*/React.createElement(AuthScreen, {
    setup: true,
    title: data.settings && data.settings.title,
    onDone: refresh
  });
  if (data.needLogin && !data.devices || login) return /*#__PURE__*/React.createElement(AuthScreen, {
    title: data.settings && data.settings.title,
    onDone: () => {
      setLogin(false);
      refresh();
    }
  });
  const admin = !!data.authed;
  const edit = admin && mode === 'edit';
  const saveRack = async rack => {
    setData(d => ({
      ...d,
      rack
    }));
    try {
      await api('/api/rack', {
        method: 'PUT',
        body: rack
      });
    } catch (e) {
      toast(e.message, true);
      refresh();
    }
  };
  const saveMap = async part => {
    setData(d => ({
      ...d,
      map: {
        ...d.map,
        ...part
      }
    }));
    try {
      await api('/api/map', {
        method: 'PUT',
        body: part
      });
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
  };
  const logout = async () => {
    await api('/api/logout', {
      method: 'POST'
    });
    setMode('view');
    refresh();
  };
  const applyState = (id, state) => setData(d => ({
    ...d,
    devices: d.devices.map(x => x.id === id ? {
      ...x,
      state
    } : x)
  }));
  const ctx = {
    data,
    admin,
    edit,
    refresh,
    saveRack,
    saveMap,
    logout,
    applyState,
    openDevice: (d, t, port) => d && setSheet({
      id: d.id,
      tab: t,
      port
    }),
    openEditor: d => setEditor(d)
  };
  const sheetDev = sheet && data.devices.find(d => d.id === sheet.id);
  const newest = Math.max(0, ...data.devices.map(d => d.state && d.state.updated || 0));
  const stale = data.devices.length && data.now - newest > Math.max(180, (data.settings.poll || 60) * 3);
  const problems = data.devices.filter(d => ['offline', 'warning'].includes((d.state || {}).status)).length;
  const tabs = TABS.filter(t => !t.admin || admin);
  const cur = tabs.find(t => t.id === tab) ? tab : 'rack';
  const subtitle = {
    rack: `${data.rack.units.length} юнитов · ${data.devices.filter(d => (d.state || {}).status === 'online').length} из ${data.devices.length} устройств в сети`,
    map: 'Как всё соединено: шкаф, кабели, точки доступа и клиенты',
    devices: 'Всё, что собирает данные: локальные и удалённые устройства',
    events: 'Сбои, восстановления и действия администратора',
    settings: 'Название, доступ, VLAN и резервные копии'
  }[cur];
  return /*#__PURE__*/React.createElement(AppCtx.Provider, {
    value: ctx
  }, /*#__PURE__*/React.createElement("div", {
    className: "app-bg"
  }), /*#__PURE__*/React.createElement("header", {
    className: "topbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand"
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand-logo"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "rack",
    size: 19,
    color: "#fff"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "brand-title ellipsis"
  }, data.settings.title), /*#__PURE__*/React.createElement("div", {
    className: 'live' + (stale ? ' stale' : '')
  }, /*#__PURE__*/React.createElement("i", null), stale ? 'нет свежих данных' : 'live · ' + fmt.ago(newest, data.now)))), /*#__PURE__*/React.createElement("nav", {
    className: "tabs"
  }, tabs.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    className: 'tab' + (cur === t.id ? ' on' : ''),
    onClick: () => setTab(t.id)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: t.icon,
    size: 15
  }), t.label, t.id === 'events' && problems ? /*#__PURE__*/React.createElement("span", {
    className: "count"
  }, problems) : null))), /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }), admin ? /*#__PURE__*/React.createElement(Seg, {
    className: "edit",
    value: mode,
    onChange: setMode,
    options: [{
      value: 'view',
      label: 'Просмотр',
      icon: 'eye'
    }, {
      value: 'edit',
      label: 'Редактирование',
      icon: 'edit',
      cls: 'editing'
    }]
  }) : /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: "lock",
    onClick: () => setLogin(true)
  }, "\u0412\u043E\u0439\u0442\u0438"), /*#__PURE__*/React.createElement(Btn, {
    size: "sm",
    icon: theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'eye',
    title: 'Тема: ' + {
      auto: 'как в системе',
      dark: 'тёмная',
      light: 'светлая'
    }[theme],
    onClick: () => setTheme(theme === 'auto' ? 'dark' : theme === 'dark' ? 'light' : 'auto')
  })), /*#__PURE__*/React.createElement("main", {
    className: "page"
  }, /*#__PURE__*/React.createElement("div", {
    className: "row",
    style: {
      alignItems: 'flex-end',
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "grow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "page-title"
  }, tabs.find(t => t.id === cur).label), /*#__PURE__*/React.createElement("div", {
    className: "page-sub",
    style: {
      marginBottom: 0
    }
  }, subtitle)), edit ? /*#__PURE__*/React.createElement("span", {
    className: "badge warning"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "edit",
    size: 12
  }), "\u0420\u0435\u0436\u0438\u043C \u0440\u0435\u0434\u0430\u043A\u0442\u0438\u0440\u043E\u0432\u0430\u043D\u0438\u044F") : null), cur === 'rack' ? /*#__PURE__*/React.createElement(RackView, null) : null, cur === 'map' ? /*#__PURE__*/React.createElement(MapView, null) : null, cur === 'devices' ? /*#__PURE__*/React.createElement(DevicesView, null) : null, cur === 'events' ? /*#__PURE__*/React.createElement(EventsView, null) : null, cur === 'settings' && admin ? /*#__PURE__*/React.createElement(SettingsView, null) : null), /*#__PURE__*/React.createElement("nav", {
    className: "bottombar"
  }, tabs.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    className: cur === t.id ? 'on' : '',
    onClick: () => setTab(t.id)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: t.icon,
    size: 24
  }), t.id === 'map' ? 'Карта' : t.label, t.id === 'events' && problems ? /*#__PURE__*/React.createElement("span", {
    className: "count"
  }, problems) : null))), sheetDev ? /*#__PURE__*/React.createElement(DeviceSheet, {
    key: sheetDev.id,
    device: sheetDev,
    initialTab: sheet.tab,
    initialPort: sheet.port,
    onClose: () => setSheet(null)
  }) : null, editor !== undefined ? /*#__PURE__*/React.createElement(DeviceEditor, {
    device: editor,
    onClose: () => setEditor(undefined)
  }) : null);
}
ReactDOM.createRoot(document.getElementById('root')).render(/*#__PURE__*/React.createElement(ToastHost, null, /*#__PURE__*/React.createElement(ConfirmHost, null, /*#__PURE__*/React.createElement(App, null))));
