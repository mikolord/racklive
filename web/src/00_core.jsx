/* Core: API client, formatting helpers, icons. Files in src/ are concatenated in name order. */
const { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback, createContext, useContext, Fragment } = React;

/* Telegram mini app: Telegram puts signed launch data into the URL hash — grab it before the app uses the hash for tabs */
const ssGet = k => { try { return sessionStorage.getItem(k); } catch (e) { return null; } };
const ssSet = (k, v) => { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (e) { } };
const TG = (() => {
  const h = new URLSearchParams(location.hash.slice(1));
  let data = h.get('tgWebAppData'), theme = null;
  if (data) {
    try { theme = JSON.parse(h.get('tgWebAppThemeParams') || 'null'); } catch (e) { }
    ssSet('rl_tg', data); ssSet('rl_tg_theme', JSON.stringify(theme));
    history.replaceState(null, '', location.pathname + location.search);
  } else { data = ssGet('rl_tg'); try { theme = JSON.parse(ssGet('rl_tg_theme') || 'null'); } catch (e) { } }
  if (!data) return null;
  const bg = (theme && theme.bg_color) || '';
  const dark = bg ? (parseInt(bg.slice(1, 3), 16) * .3 + parseInt(bg.slice(3, 5), 16) * .59 + parseInt(bg.slice(5, 7), 16) * .11) < 128 : null;
  const s = document.createElement('script');                  // official helper: full-height, «ready», native back gesture
  s.src = 'https://telegram.org/js/telegram-web-app.js';
  s.onload = () => { try { Telegram.WebApp.ready(); Telegram.WebApp.expand(); } catch (e) { } };
  document.head.appendChild(s);
  return { initData: data, scheme: dark == null ? null : dark ? 'dark' : 'light' };
})();

/* diagnostics of the page itself (reloads, JS errors, lost connection, going to the background): kept in this browser and sent to the journal
   («События» → «Страница») with the next successful request — so a phone that «jerks» tells why, even when it could not reach the server at that moment */
const DIAG_KEY = 'rl_diag';
function diag(text) { try { const a = JSON.parse(localStorage.getItem(DIAG_KEY) || '[]'); a.push({ t: Date.now(), s: String(text).slice(0, 120) }); localStorage.setItem(DIAG_KEY, JSON.stringify(a.slice(-24))); } catch (e) { } }
async function diagFlush() {
  try {
    const a = JSON.parse(localStorage.getItem(DIAG_KEY) || '[]'); if (!a.length) return;
    localStorage.setItem(DIAG_KEY, '[]');
    // the journal gets only what looks wrong: a JS error, a lost connection, or the page loading anew several times in a minute (a reload loop);
    // an ordinary launch or switching apps is not written down
    const loads = a.filter(x => /^загружена/.test(x.s)).map(x => x.t);
    const loop = loads.length >= 3 && loads[loads.length - 1] - loads[0] < 60000;
    if (!a.some(x => /^(ошибка|связь)/.test(x.s)) && !loop) return;
    const hm = t => new Date(t).toTimeString().slice(0, 8);
    await api('/api/tour/log', { method: 'POST', body: { text: 'страница: ' + a.map(x => hm(x.t) + ' ' + x.s).join(' · ') } });
  } catch (e) { }
}
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {}, credentials: 'same-origin' };
  const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
  if (opts.body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opts.body); }
  const r = await fetch(path, init);
  let data = null;
  try { data = await r.json(); } catch (e) { /* empty body */ }
  if (!r.ok) { const err = new Error((data && data.error) || ('Ошибка ' + r.status)); err.status = r.status; throw err; }
  return data;
}

const fmt = {
  uptime(s) {
    if (s == null || isNaN(s)) return '—';
    s = Math.floor(s); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    if (d) return `${d} д ${h} ч`; if (h) return `${h} ч ${m} мин`; return `${m} мин`;
  },
  ago(t, now) {
    if (!t) return 'никогда';
    const s = Math.max(0, Math.round((now || Date.now() / 1000) - t));
    if (s < 10) return 'только что'; if (s < 60) return `${s} с назад`; if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
    if (s < 86400) return `${Math.floor(s / 3600)} ч назад`; return new Date(t * 1000).toLocaleDateString('ru-RU');
  },
  time(t) { return t ? new Date(t * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'; },
  speed(m) { if (!m) return '—'; if (m >= 1000) return (m / 1000) + ' Гбит'; return m + ' Мбит'; },
  speedShort(m) { if (!m) return ''; if (m >= 1000) return (m / 1000) + 'G'; return m + 'M'; },
  bytes(b) {
    if (b == null) return '—'; const u = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']; let i = 0; b = +b;
    while (b >= 1000 && i < u.length - 1) { b /= 1000; i++; } return (b >= 100 ? b.toFixed(0) : b.toFixed(1)) + ' ' + u[i];
  },
  gb(g) { return g >= 1000 ? (g / 1000).toFixed(1) + ' ТБ' : g + ' ГБ'; },
  pct(v) { return v == null ? '—' : Math.round(v) + '%'; },
  bps(v) {
    if (v == null) return '—'; if (v < 1000) return Math.round(v) + ' бит/с';
    if (v < 1e6) return (v / 1e3).toFixed(v < 1e4 ? 1 : 0) + ' Кбит/с'; if (v < 1e9) return (v / 1e6).toFixed(v < 1e7 ? 1 : 0) + ' Мбит/с';
    return (v / 1e9).toFixed(2) + ' Гбит/с';
  },
};

const speedClass = (p) => !p || !p.link ? '' : (p.speed >= 1000 ? 'g' : p.speed >= 100 ? 'y' : 'o');
const speedColor = (s, kind) => {
  if (kind === 'wifi') return 'var(--accent)'; if (kind === 'wan' || kind === 'isp' || kind === 'remote') return 'var(--purple)';
  if (kind === 'mesh') return 'var(--teal)'; if (kind === 'manual' || kind === 'lan') return 'var(--text3)';
  if (!s) return 'var(--text3)'; return s >= 1000 ? 'var(--green)' : s >= 100 ? 'var(--yellow)' : 'var(--orange)';
};
const STATUS_TEXT = { online: 'В сети', warning: 'Внимание', offline: 'Нет связи', unknown: 'Ожидание' };
const KIND_TEXT = { router: 'Маршрутизатор', switch: 'Коммутатор', server: 'Сервер', nas: 'NAS', ap: 'Точка доступа', camera: 'Камера', phone: 'Телефон',
  tablet: 'Планшет', tv: 'Телевизор', laptop: 'Ноутбук', pc: 'Компьютер', printer: 'Принтер', speaker: 'Колонка', iot: 'Умное устройство',
  internet: 'Интернет', web: 'Сайт', other: 'Другое', ups: 'ИБП', patch: 'Патч-панель', cross: 'Оптический кросс', pdu: 'Блок розеток',
  shelf: 'Полка', blank: 'Заглушка', organizer: 'Органайзер', nvr: 'Видеорегистратор', modem: 'Модем / ONT' };
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
  edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4', eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  plus: 'M12 5v14M5 12h14', x: 'M6 6l12 12M18 6L6 18', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14M20 20l-4-4', settings: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  rack: 'M5 2h14v20H5zM5 7h14M5 12h14M5 17h14M8 4.5h.01M8 9.5h.01M8 14.5h.01M8 19.5h.01',
  map: 'M5 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4M19 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4M12 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4M6.5 7.5l4.5 8M17.5 7.5l-4.5 8M7 6h10',
  list: 'M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01', bell: 'M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  bolt: 'M13 2L4 14h7l-1 8 9-12h-7z', swap: 'M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7', mail: 'M3 6h18v12H3zM3 7l9 7 9-7', key: 'M21 2l-2 2M11.4 11.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zM11.4 11.6L15.5 7.5M15.5 7.5l3 3L22 7l-3-3M15.5 7.5L19 4', sms: 'M4 5h16v11H10l-5 4v-4H4z', play: 'M7 4.5l12 7.5-12 7.5z', refresh: 'M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5', power: 'M12 2v10M5.6 6.6a9 9 0 1 0 12.8 0',
  link: 'M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1', fit: 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5',
  lock: 'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4', logout: 'M15 4h4v16h-4M10 17l5-5-5-5M15 12H3', sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z', chevron: 'M9 6l6 6-6 6', download: 'M12 3v12M7 10l5 5 5-5M4 21h16', upload: 'M12 21V9M7 14l5-5 5 5M4 3h16',
  check: 'M5 12l5 5 9-11', sort: 'M4 7h16M7 12h10M10 17h4', clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2', minus: 'M5 12h14', grip: 'M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01', resize: 'M21 13l-8 8M21 6L6 21',
  plan: 'M3 4h18v16H3zM3 12h7M10 4v4M14 12v8M14 15h7', terminal: 'M4 5h16v14H4zM8 10l3 2-3 2M13 15h3', wifi: 'M12 20h.01M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 14 0', globe: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20',
  box: 'M4 7h16v13H4zM4 7l2-4h12l2 4M9 11h6', wrench: 'M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z', home: 'M4 11l8-7 8 7M6 10v10h12V10M10 20v-6h4v6',
  pole: 'M12 2v20M7 6h10M8.5 10h7M9 22h6', send: 'M22 2L11 13M22 2l-7 20-4-9-9-4z',
  wall: 'M3 5h18v14H3zM3 9.5h18M3 14.5h18M8 5v4.5M14 5v4.5M11 9.5V14.5M5 14.5V19M17 14.5V19',
  eraser: 'M4 15l7-7 6 6-5 5H8zM20 20H9', cursor: 'M5 3l6 16 2-7 7-2z', tag: 'M4 4h8l8 8-8 8-8-8zM8 8h.01', tree: 'M12 2a6 6 0 0 1 4 10l-1 1v3h-6v-3l-1-1A6 6 0 0 1 12 2M12 15v7',
  shield: 'M12 2l8 3v6c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V5z', globe2: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20',
  pulse: 'M2 12h4l3-8 4 16 3-8h6', cable: 'M4 4h5v5H4zM6.5 9v4a4 4 0 0 0 4 4h3a4 4 0 0 1 4 4M5.5 4V2M7.5 4V2', alert: 'M12 3L2 20h20zM12 10v4M12 17h.01',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1', menu: 'M4 7h16M4 12h16M4 17h9', more: 'M6 12h.01M12 12h.01M18 12h.01', share: 'M12 15V3M8 7l4-4 4 4M7 10H5v11h14V10h-2', chevronLeft: 'M15 6l-6 6 6 6', arrowUp: 'M12 19V5M6 11l6-6 6 6', mic: 'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21', sparkle: 'M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9zM18.5 14.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z', gauge: 'M3.5 17a9 9 0 1 1 17 0M12 14l4.5-5M12 14h.01', bulb: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3', pin: 'M12 22s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12M12 7a3 3 0 1 0 0 6 3 3 0 0 0 0-6', toggle: 'M7 7h10a5 5 0 0 1 0 10H7A5 5 0 0 1 7 7M7 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
};
/* a custom look (Настройки → Оформление → «Добавить своё», rackd/themes.py) is plain data: texts, icons, colours of kinds — read once at start (90_app.jsx), nothing else is run */
const THEME = { id: null, strings: {}, icons: {}, kindColors: {}, appIcons: {}, frankAvatar: null, tileArt: {}, tileColors: {} };
/* every text a look may replace goes through T(ключ, текст по умолчанию): the default stays in the code, the build (build.py) lists these calls in theme-defaults.json */
const T = (key, def) => { const v = THEME.strings[key]; return typeof v === 'string' && v !== '' ? v : def; };
/* the app icons (Rack Live / Frank / speed test) — same files as on the home screen; ?v= busts the old cached ones */
const APP_ICONS = { rack: '/icon.svg?v=27', frank: '/frank-icon.svg?v=27', speed: '/speed-icon.svg?v=27', terminal: '/terminal-icon.svg?v=27' };
const APP_ICONS_G = { rack: '/icon-graphite.svg?v=1', frank: '/frank-icon-graphite.svg?v=1', speed: '/speed-icon-graphite.svg?v=1', terminal: '/terminal-icon.svg?v=27' };
const APP_ICONS_N = { rack: '/icon-net.svg?v=1', frank: '/frank-icon-net.svg?v=1', speed: '/speed-icon-net.svg?v=1', terminal: '/terminal-icon.svg?v=27' };
function AppIcon({ app = 'rack', size = 30, radius, style }) {
  const st = { borderRadius: radius != null ? radius : Math.round(size * .225), flexShrink: 0, ...style };
  if (THEME.appIcons[app]) return <img src={THEME.appIcons[app]} width={size} height={size} alt="" draggable="false" style={{ display: 'block', ...st }} />;      // the custom look brings its own
  // every app icon has flat outline twins for the «Графит» and «Контроллер» looks (css shows the right one, so the original look is untouched)
  return <><img src={APP_ICONS[app]} width={size} height={size} alt="" draggable="false" className="app-ic-c" style={{ display: 'block', ...st }} />
    <img src={APP_ICONS_G[app]} width={size} height={size} alt="" draggable="false" className="app-ic-g" style={st} />
    <img src={APP_ICONS_N[app]} width={size} height={size} alt="" draggable="false" className="app-ic-n" style={st} /></>;
}
function Icon({ name, size = 18, color = 'currentColor', stroke = 1.8, style }) {
  const d = THEME.icons[name] || ICON_PATHS[name] || ICON_PATHS.other;
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style}>
    {d.split('M').filter(Boolean).map((p, i) => <path key={i} d={'M' + p} />)}
  </svg>;
}
const KIND_COLOR = { router: '#0a84ff', switch: '#30d158', server: '#5e5ce6', nas: '#64d2ff', ap: '#40c8e0', camera: '#ff453a', nvr: '#ff375f', phone: '#8e8e93',
  tablet: '#8e8e93', tv: '#bf5af2', laptop: '#8e8e93', pc: '#ac8e68', printer: '#8e8e93', speaker: '#ff9f0a', iot: '#ffd60a', internet: '#bf5af2', web: '#5e5ce6',
  ups: '#ff9f0a', patch: '#8e8e93', cross: '#64d2ff', pdu: '#ff9f0a', modem: '#bf5af2', other: '#8e8e93' };
/* «Контроллер»: a small, coordinated palette instead of the original rainbow — blue for infrastructure, teal/cyan next to it (nas/ap keep their own, already close),
   green only for the switch, yellow for power/sound, red only for cameras (kept, it is the one colour that must still stand out), grey for plain client devices */
const KIND_COLOR_NET = { tv: 'var(--accent)', internet: 'var(--accent)', modem: 'var(--accent)', server: 'var(--accent)', web: 'var(--accent)',
  speaker: 'var(--orange)', ups: 'var(--orange)', pdu: 'var(--orange)', pc: 'var(--text3)' };
function kindColor(kind) {
  const k = kind || 'other';
  if (THEME.kindColors[k]) return THEME.kindColors[k];
  if (document.documentElement.getAttribute('data-skin') === 'net' && KIND_COLOR_NET[k]) return KIND_COLOR_NET[k];
  return KIND_COLOR[k] || KIND_COLOR.other;
}
function KindIcon({ kind, size = 36, round = 10 }) {
  const c = kindColor(kind);
  return <div className="kind-ic" style={{ width: size, height: size, borderRadius: round, display: 'grid', placeItems: 'center', flexShrink: 0,
    background: `color-mix(in srgb, ${c} 16%, transparent)` }}><Icon name={kind} size={size * .54} color={c} /></div>;
}

const ToastCtx = createContext(() => {});
const useToast = () => useContext(ToastCtx);
function ToastHost({ children }) {
  const [items, setItems] = useState([]);
  const push = useCallback((text, err) => {
    const id = Math.random(); setItems(x => [...x, { id, text, err }]);
    setTimeout(() => setItems(x => x.filter(i => i.id !== id)), err ? 5000 : 2600);
  }, []);
  return <ToastCtx.Provider value={push}>{children}
    <div className="toast-wrap">{items.map(i => <div key={i.id} className={'toast' + (i.err ? ' err' : '')}>
      <Icon name={i.err ? 'x' : 'check'} size={16} />{i.text}</div>)}</div>
  </ToastCtx.Provider>;
}

const AppCtx = createContext(null);
const useApp = () => useContext(AppCtx);
