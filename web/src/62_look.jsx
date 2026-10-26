/* Настройки → Оформление: the look of the interface. Four built-in looks (the ids are kept for the saved choices, the names are what the person sees):
   «Витрина» = id test (the default since 2.16.1: the strict instrument-panel language, black aluminium in the dark theme, white in the light one, hairlines, mono labels),
   «Лазурь» = net (blue accent, flat UniFi-style icons), «Стекло» = classic (the original, glass/iOS) and «Графит» = graphite (flat, black, thin outlines, green accent),
   each with a cover (ThemeCover) — and CUSTOM looks: a .zip with plain data (colours, texts, icons, css, pictures) that the administrator uploads
   («Добавить своё»); Rack Live checks it (rackd/themes.py) and keeps the verdict up to date after every update. An accent colour and the light / dark theme work with all of them.
   The choice is kept per device in localStorage (rl_skin = test | net | classic | graphite | <id of a custom look>, default test, rl_theme_meta, rl_accent, rl_theme);
   the page applies it before the first paint (index.html). */
const SKINS = [
  { id: 'test', name: 'Витрина', text: 'Строгий стиль приборной панели: в тёмной теме чёрный алюминий, в светлой белый, тонкие линии вместо теней, моно-подписи, монохромные иконки, приборы вместо кругов. Основное оформление.', rows: ['Сводка', 'Роутер'] },
  { id: 'net', name: 'Лазурь', text: 'Яркий синий акцент как у сетевых контроллеров, без оранжевого (жёлтый вместо него) и фиолетового, плоские иконки без картинок на плитках.', rows: ['Сводка', 'Роутер'] },
  { id: 'classic', name: 'Стекло', text: 'Прозрачные карточки, мягкие градиенты и синий акцент — как в iOS. Первое оформление Rack Live.', rows: ['Сводка', 'Роутер'] },
  { id: 'graphite', name: 'Графит', text: 'Чёрный фон, плоские серые карточки, тонкие рамки, зелёный акцент — без размытия и теней.', rows: ['Сводка', 'Роутер'] },
];
const ACCENTS = [['', 'По умолчанию у оформления', null], ['blue', 'Синий', '#0a84ff'], ['green', 'Зелёный', '#30b455'], ['purple', 'Фиолетовый', '#a259e6'],
  ['orange', 'Оранжевый', '#f5870a'], ['red', 'Красный', '#f2453d'], ['teal', 'Бирюзовый', '#20b4cc'], ['pink', 'Розовый', '#ee3d73']];

const BUILTIN_SKINS = ['classic', 'graphite', 'net', 'test'];
const DEFAULT_SKIN = 'test';                                    // the flagship look: shown on a fresh device and after a custom look goes away
const getSkin = () => lsGet('rl_skin', DEFAULT_SKIN) || DEFAULT_SKIN;
const getAccent = () => { const a = lsGet('rl_accent', ''); return ACCENTS.some(x => x[0] === a) ? a : ''; };
const themeMeta = () => { try { return JSON.parse(lsGet('rl_theme_meta', '') || 'null'); } catch (e) { return null; } };
function applyLook(skin, accent) {                              // built-in looks only (a custom look needs its css: a page reload does it, see pickCustom)
  const h = document.documentElement;
  if (skin && skin !== 'classic') h.setAttribute('data-skin', skin === 'test' ? 'net' : skin); else h.removeAttribute('data-skin');
  if (skin === 'test') h.setAttribute('data-look', 'test'); else h.removeAttribute('data-look');      // «Test» = «Контроллер» + the «Витрина» look
  h.removeAttribute('data-theme-id');
  if (accent) h.setAttribute('data-accent', accent); else h.removeAttribute('data-accent');
  const fav = document.querySelector('link[rel~="icon"]'); if (fav) fav.setAttribute('href', skin === 'graphite' ? 'icon-graphite.svg?v=1' : 'icon.svg?v=27');
}
const skinName = () => { const s = getSkin(); const b = SKINS.find(x => x.id === s); if (b) return b.name; const m = themeMeta(); return m && m.id === s ? m.name : s; };

/* at start: a custom look's texts, icons and colours of kinds are read (they live in a global, so the page is rendered after this); a look that was switched off
   (it no longer fits after an update) sends the person back to the built-in look, once, with the reason */
async function loadTheme() {
  const id = getSkin(); if (BUILTIN_SKINS.includes(id)) return;
  try {
    const r = await fetch(`/themes/${id}/data.json`, { cache: 'no-cache' }); const d = await r.json();
    if (d.off) throw new Error('off');
    Object.assign(THEME, { id, strings: d.strings || {}, icons: d.icons || {}, kindColors: d.kindColors || {}, appIcons: d.appIcons || {}, frankAvatar: d.frankAvatar || null, tileArt: d.tileArt || {}, tileColors: d.tileColors || {} });
  } catch (e) {
    const m = themeMeta(); lsSet('rl_skin', 'classic'); lsSet('rl_theme_meta', ''); THEME.offNote = (m && m.name) || id;
    const h = document.documentElement; h.removeAttribute('data-theme-id'); h.removeAttribute('data-skin');      // back to the original look
    const l = document.getElementById('rl-theme-css'); if (l) l.remove();
  }
}

function useAllThemesCss() {                                       // the previews of custom looks need their css: all of them are scoped, so loading them together is harmless
  useEffect(() => { if (document.getElementById('rl-themes-all')) return; const l = document.createElement('link'); l.id = 'rl-themes-all'; l.rel = 'stylesheet'; l.href = '/themes/all.css?v=' + Date.now(); document.head.appendChild(l); }, []);
}

function ThemeReport({ rep, onClose }) {
  return <Modal title={rep.ok ? 'Оформление добавлено' : 'Оформление не принято'} onClose={onClose} icon={<Icon name={rep.ok ? 'check' : 'alert'} size={20} color={rep.ok ? 'var(--green)' : 'var(--red)'} />}>
    {rep.ok ? <div style={{ fontSize: 14 }}>«{rep.name}» установлено. Выберите его в списке.</div>
      : <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Архив не прошёл проверку: он не подходит к этой версии Rack Live или нарушает правила безопасности. Исправьте пункты ниже и загрузите снова.</div>}
    {rep.errors && rep.errors.length ? <><div className="card-title" style={{ margin: '8px 0 0', color: 'var(--red)' }}><Icon name="alert" size={14} />Ошибки · {rep.errors.length}</div>
      <div className="list">{rep.errors.map((e, i) => <div className="li" key={i} style={{ fontSize: 13, lineHeight: 1.45 }}>{e}</div>)}</div></> : null}
    {rep.warnings && rep.warnings.length ? <><div className="card-title" style={{ margin: '8px 0 0', color: 'var(--orange)' }}><Icon name="bulb" size={14} />Замечания · {rep.warnings.length}</div>
      <div className="list">{rep.warnings.map((e, i) => <div className="li" key={i} style={{ fontSize: 13, lineHeight: 1.45 }}>{e}</div>)}</div>
      <div className="dim3" style={{ fontSize: 12 }}>Замечания не мешают: часть настроек будет проигнорирована или может перестать действовать после обновления.</div></> : null}
    <div className="row" style={{ justifyContent: 'flex-end' }}><Btn kind="primary" onClick={onClose}>Понятно</Btn></div>
  </Modal>;
}

/* The covers of the built-in looks: a small poster for each, drawn in its own language (fixed colours — a cover is a picture, it does not follow the light / dark theme).
   Витрина — an aluminium rack with hairlines and a gauge; Лазурь — a bright blue network of nodes; Стекло — frosted glass cards on soft colour; Графит — a flat dark card with a green line. */
function ThemeCover({ id }) {
  const p = 'tc-' + id;
  let body;
  if (id === 'test') {
    const units = [['PATCH · CAT6', 8, false], ['KEENETIC', 5, true], ['NAS DS918+', 4, true], ['POE · 24', 11, true]];
    body = <>
      <defs><linearGradient id={p + 'g'} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1f2226" /><stop offset="1" stopColor="#07080a" /></linearGradient></defs>
      <rect width="320" height="132" fill={`url(#${p}g)`} />
      <path d={Array.from({ length: 9 }, (_, i) => `M0 ${(i + 1) * 14}H320`).join('') + Array.from({ length: 20 }, (_, i) => `M${(i + 1) * 16} 0V132`).join('')} stroke="#fff" strokeOpacity=".035" />
      <rect x="20" y="14" width="124" height="104" rx="3" fill="#0b0c0e" stroke="#fff" strokeOpacity=".2" />
      {units.map(([n, k, led], i) => <g key={n} transform={`translate(26 ${20 + i * 24})`}>
        <rect width="112" height="19" rx="2" fill="#26292e" stroke="#fff" strokeOpacity=".12" />
        {led ? <circle cx="7" cy="9.5" r="1.8" fill="#3d8bff" /> : <circle cx="7" cy="9.5" r="1.8" fill="#4a4d52" />}
        <text x="14" y="12.5" fontSize="6" fill="#aab0b8" fontFamily="ui-monospace,Menlo,Consolas,monospace" letterSpacing=".4">{n}</text>
        {Array.from({ length: k }, (_, j) => <rect key={j} x={107 - (k - j) * 5} y="6.5" width="3.6" height="6" rx=".7" fill="#050607" stroke="#fff" strokeOpacity=".25" strokeWidth=".5" />)}</g>)}
      <text x="170" y="30" fontSize="7" fill="#8d939b" fontFamily="ui-monospace,Menlo,Consolas,monospace" letterSpacing="1.6">RACK LIVE · 12 U</text>
      <text x="168" y="78" fontSize="44" fontWeight="200" fill="#eceef1" fontFamily="ui-monospace,Menlo,Consolas,monospace">10<tspan fontSize="16" fill="#8d939b">/11</tspan></text>
      <text x="170" y="95" fontSize="7" fill="#8d939b" fontFamily="ui-monospace,Menlo,Consolas,monospace" letterSpacing="1.6">В СЕТИ</text>
      <rect x="170" y="104" width="130" height="1" fill="#fff" fillOpacity=".25" /><rect x="170" y="103" width="94" height="3" fill="#3d8bff" />
      {Array.from({ length: 14 }, (_, i) => <rect key={i} x={170 + i * 9.3} y="107" width=".6" height="3" fill="#fff" fillOpacity=".3" />)}</>;
  } else if (id === 'net') {
    const nodes = [[60, 34], [92, 104], [236, 28], [268, 96], [200, 112], [30, 80]];
    body = <>
      <defs><linearGradient id={p + 'g'} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#2b9bff" /><stop offset="1" stopColor="#0a3cae" /></linearGradient>
        <radialGradient id={p + 'r'} cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="#fff" stopOpacity=".35" /><stop offset="1" stopColor="#fff" stopOpacity="0" /></radialGradient></defs>
      <rect width="320" height="132" fill={`url(#${p}g)`} />
      <circle cx="160" cy="66" r="80" fill={`url(#${p}r)`} />
      {[44, 66, 90].map(r => <circle key={r} cx="160" cy="66" r={r} fill="none" stroke="#fff" strokeOpacity=".1" />)}
      {nodes.map(([x, y], i) => <line key={i} x1="160" y1="66" x2={x} y2={y} stroke="#fff" strokeOpacity=".6" strokeWidth="1.6" />)}
      {nodes.map(([x, y], i) => <g key={i}><circle cx={x} cy={y} r="9.5" fill="#fff" /><circle cx={x} cy={y} r="3.4" fill="#1b6fe0" /></g>)}
      <circle cx="160" cy="66" r="19" fill="#fff" /><circle cx="160" cy="66" r="19" fill="none" stroke="#fff" strokeOpacity=".4" strokeWidth="5" />
      <path d="M150 70h20v6h-20zM153 67.5a10 10 0 0 1 14 0M156 64.5a6 6 0 0 1 8 0" fill="none" stroke="#1b6fe0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></>;
  } else if (id === 'classic') {
    body = <>
      <defs><linearGradient id={p + 'g'} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6b5cf0" /><stop offset=".55" stopColor="#1f8bff" /><stop offset="1" stopColor="#35d4c2" /></linearGradient>
        <filter id={p + 'b'} x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14" /></filter></defs>
      <rect width="320" height="132" fill={`url(#${p}g)`} />
      <g filter={`url(#${p}b)`}><circle cx="52" cy="108" r="34" fill="#ff5fa2" opacity=".8" /><circle cx="270" cy="22" r="32" fill="#ffb347" opacity=".75" /><circle cx="170" cy="120" r="28" fill="#7cf0d8" opacity=".6" /></g>
      <g><rect x="26" y="20" width="156" height="66" rx="15" fill="#fff" fillOpacity=".2" stroke="#fff" strokeOpacity=".5" />
        <circle cx="52" cy="46" r="13" fill="#fff" fillOpacity=".9" /><path d="M46 46l4 4 8-9" fill="none" stroke="#1f8bff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="74" y="36" width="70" height="8" rx="4" fill="#fff" fillOpacity=".85" /><rect x="74" y="52" width="48" height="6" rx="3" fill="#fff" fillOpacity=".5" /></g>
      <g><rect x="110" y="62" width="184" height="54" rx="15" fill="#fff" fillOpacity=".24" stroke="#fff" strokeOpacity=".55" />
        <rect x="128" y="76" width="64" height="8" rx="4" fill="#fff" fillOpacity=".85" /><rect x="128" y="92" width="92" height="6" rx="3" fill="#fff" fillOpacity=".5" />
        <rect x="236" y="78" width="40" height="24" rx="12" fill="#34c759" /><circle cx="264" cy="90" r="9" fill="#fff" /></g></>;
  } else {
    const pts = [[30, 92], [62, 80], [94, 86], [126, 62], [158, 70], [190, 48], [222, 56], [254, 36], [286, 42]];
    const line = pts.map(([x, y], i) => (i ? 'L' : 'M') + x + ' ' + y).join('');
    body = <>
      <rect width="320" height="132" fill="#0d0e0f" />
      <rect x="14.5" y="14.5" width="291" height="103" rx="8" fill="#161719" stroke="#2c2e31" />
      <text x="28" y="34" fontSize="7" fill="#8d939b" fontFamily="ui-monospace,Menlo,Consolas,monospace" letterSpacing="1.6">СВОДКА</text>
      <circle cx="290" cy="30" r="3" fill="#30b455" /><circle cx="278" cy="30" r="3" fill="#30b455" /><circle cx="266" cy="30" r="3" fill="#4a4d52" />
      <path d={line + 'L286 104L30 104Z'} fill="#30b455" fillOpacity=".12" />
      <path d={line} fill="none" stroke="#30b455" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx="286" cy="42" r="3.6" fill="#0d0e0f" stroke="#30b455" strokeWidth="1.8" />
      {[0, 1, 2, 3].map(i => <path key={i} d={`M28 ${104 - i * 20}H292`} stroke="#fff" strokeOpacity=".05" />)}
      <text x="28" y="60" fontSize="22" fontWeight="600" fill="#ececec" fontFamily="-apple-system,Segoe UI,Roboto,sans-serif">10/11</text></>;
  }
  return <svg viewBox="0 0 320 132" width="100%" style={{ display: 'block' }} aria-hidden="true">{body}</svg>;
}

function LookCard() {
  const [skin, setSkin] = useState(getSkin); const [accent, setAccent] = useState(getAccent);
  const { theme, setTheme, admin } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [list, setList] = useState(null); const [rep, setRep] = useState(null); const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  useAllThemesCss();
  const reload = async () => { try { setList(await api('/api/themes')); } catch (e) { setList({ themes: [], api: 1 }); } };
  useEffect(() => { reload(); }, []);
  const th = document.documentElement.getAttribute('data-theme') || 'dark';
  const customNow = !BUILTIN_SKINS.includes(skin);
  const pickBuiltin = id => {
    lsSet('rl_skin', id); lsSet('rl_theme_meta', ''); setSkin(id);
    if (customNow || id === 'test' || skin === 'test') { applyLook(id, accent); location.reload(); return; }      // leaving a custom look (its texts and icons are in memory) or «Test» (another shell): a clean start
    applyLook(id, accent);
  };
  const pickCustom = async t => {
    try {
      const d = await (await fetch(`/themes/${t.id}/data.json`, { cache: 'no-cache' })).json();
      if (d.off) { toast('Это оформление отключено: ' + ((t.problems || [])[0] || 'не подходит'), true); return reload(); }
      const pw = o => ({ fav: (o || {}).favicon || '', touch: (o || {}).appleTouch || '', pwa: !!((o || {}).icon192 && (o || {}).icon512) });       // home-screen pictures of each of the three apps
      lsSet('rl_skin', t.id); lsSet('rl_theme_meta', JSON.stringify({ id: t.id, name: t.name, base: d.base, ...pw(d.pwa), frank: pw(d.pwaFrank), speed: pw(d.pwaSpeed), rev: d.installed || d.rev }));
      location.reload();
    } catch (e) { toast('Не удалось применить: ' + e.message, true); }
  };
  const pickAccent = a => { setAccent(a); lsSet('rl_accent', a); const h = document.documentElement; if (a) h.setAttribute('data-accent', a); else h.removeAttribute('data-accent'); };
  const [glass, setGlass] = useState(() => lsGet('rl_glass', '1') !== '0');
  const pickGlass = on => { setGlass(on); lsSet('rl_glass', on ? '1' : '0'); const h = document.documentElement; if (on) h.removeAttribute('data-glass'); else h.setAttribute('data-glass', 'off'); };
  const upload = async f => {
    if (!f) return; setBusy(true);
    try {
      const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: f };
      const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
      const r = await fetch('/api/themes/upload', init); const j = await r.json();
      if (!r.ok && !j.errors) throw new Error(j.error || 'ошибка ' + r.status);
      setRep(j); if (j.ok) reload();
    } catch (e) { toast(e.message, true); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const remove = async t => {
    if (!(await confirm(`Удалить оформление «${t.name}»?`, { danger: true, ok: 'Удалить' }))) return;
    try { await api('/api/themes/' + t.id, { method: 'DELETE' }); if (skin === t.id) { pickBuiltin(DEFAULT_SKIN); return; } reload(); } catch (e) { toast(e.message, true); }
  };
  const customs = (list && list.themes) || [];
  const card = (id, name, text, ok = true, base = 'classic', meta = null) => <div key={id} className={'look-skin' + (skin === id ? ' on' : '') + (ok ? '' : ' off')} role="button" tabIndex={0}
    onClick={() => ok && (meta ? pickCustom(meta) : pickBuiltin(id))}>
    {!meta ? <div className="look-cover"><ThemeCover id={id} /></div>
      : <div className="look-prev" data-skin={base === 'graphite' ? 'graphite' : 'classic'} data-theme-id={id} data-theme={th} data-accent={accent || undefined}>
        {meta.preview ? <img src={meta.preview} alt="" style={{ width: '100%', borderRadius: 8, display: 'block' }} /> : <>
          <div className="lp-card"><i /><span>Сводка</span><small>10/11</small></div><div className="lp-ok">Всё работает</div><span className="lp-btn">Кнопка</span></>}
      </div>}
    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><b>{name}</b>{id === DEFAULT_SKIN ? <span className="badge">основное</span> : null}{skin === id ? <span className="badge online">выбрано</span> : null}{!ok ? <span className="badge offline">не подходит</span> : null}</div>
    <small>{text}</small>
    {meta && !ok ? <small style={{ color: 'var(--orange)' }}>{(meta.problems || []).slice(0, 2).join(' · ')}</small> : null}
    {meta ? <div className="row" style={{ gap: 6 }} onClick={e => e.stopPropagation()}>{admin ? <Btn size="sm" onClick={() => remove(meta)}>Удалить</Btn> : null}</div> : null}
  </div>;
  return <>
    <Card title="Стиль интерфейса">
      <div className="look-skins">
        {SKINS.map(x => card(x.id, x.name, x.text))}
        {customs.map(t => card(t.id, t.name, [t.author, t.version && 'v' + t.version, t.description].filter(Boolean).join(' · ') || 'Своё оформление', t.ok, t.base, t))}
      </div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Оформление запоминается на этом устройстве: на телефоне и на компьютере можно выбрать разное. Frank и «Тест скорости» подхватывают его тоже.
        Если оформление стало нечитаемым, откройте адрес панели с добавкой <b>?skin=classic</b> — вернётся стандартное.</div>
    </Card>
    {admin ? <Card title="Своё оформление">
      <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Можно загрузить оформление из файла .zip: цвета, шрифты, иконки, тексты, приветственное обучение, значки приложений. Это только данные (без программ):
        Rack Live проверяет каждый архив и после каждого обновления заново проверяет, подходит ли оформление к новой версии. Неподходящее отключается само, интерфейс возвращается к стандартному.</div>
      <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
        <input ref={fileRef} type="file" accept=".zip,application/zip" style={{ display: 'none' }} onChange={e => upload(e.target.files[0])} />
        <Btn kind="primary" icon="plus" busy={busy} onClick={() => fileRef.current && fileRef.current.click()}>Добавить своё</Btn>
        <a className="btn" href="/api/themes/template.zip" download>Скачать шаблон (.zip)</a>
        <a className="btn" href="/api/themes/guide.txt" download>Инструкция для нейросети (.txt)</a>
      </div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Как сделать своё: скачайте инструкцию и отдайте её нейросети вместе с описанием желаемого вида — она соберёт архив. Версия оформления (api): {list ? list.api : '…'} · Rack Live {list ? list.version : ''}.
        Иконка приложения на экране «Домой» меняется только при новой установке значка.</div>
    </Card> : null}
    {skin === 'net' ? <Card title="Жидкое стекло">
      <div className="row" style={{ gap: 12 }}><div className="grow" style={{ fontSize: 14 }}>Нижняя панель — полупрозрачная, с размытием того, что под ней (как в iOS)</div><Switch on={glass} onChange={pickGlass} /></div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Запоминается на этом устройстве. На слабых телефонах размытие может немного замедлять прокрутку — тогда его можно выключить.</div>
    </Card> : null}
    <Card title="Цвет акцента">
      <div className="look-accents">{ACCENTS.map(([id, name, col]) => <button type="button" key={id || 'def'} title={name} aria-label={name}
        className={'look-dot' + (accent === id ? ' on' : '') + (col ? '' : ' def')} style={col ? { background: col } : null} onClick={() => pickAccent(id)} />)}</div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Цвет кнопок, выбранных вкладок и переключателей. Цвета статусов (в сети, ошибка) не меняются.</div>
    </Card>
    <Card title="Светлая и тёмная тема">
      <Seg value={theme} onChange={setTheme} options={[{ value: 'auto', label: 'Как в системе' }, { value: 'dark', label: 'Тёмная' }, { value: 'light', label: 'Светлая' }]} />
    </Card>
    {rep ? <ThemeReport rep={rep} onClose={() => setRep(null)} /> : null}
  </>;
}
