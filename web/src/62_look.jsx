/* Настройки → Оформление: the look of the interface. Three built-in looks — «Контроллер» (the default, blue accent, flat UniFi-style icons), «Rack Live» (the original, glass/iOS)
   and «Графит» (flat, black, thin outlines, green accent) — and CUSTOM looks: a .zip with plain data (colours, texts, icons, css, pictures) that the administrator uploads
   («Добавить своё»); Rack Live checks it (rackd/themes.py) and keeps the verdict up to date after every update. An accent colour and the light / dark theme work with all of them.
   The choice is kept per device in localStorage (rl_skin = net | classic | graphite | <id of a custom look>, default net, rl_theme_meta, rl_accent, rl_theme); the page applies it before the first paint (index.html). */
const SKINS = [
  { id: 'net', name: 'Контроллер', text: 'Яркий синий акцент как у сетевых контроллеров, без оранжевого (жёлтый вместо него) и фиолетового, плоские иконки без картинок на плитках. Основное оформление.', rows: ['Сводка', 'Роутер'] },
  { id: 'classic', name: 'Rack Live', text: 'Стекло, мягкие градиенты и синий акцент — как в iOS.', rows: ['Сводка', 'Роутер'] },
  { id: 'graphite', name: 'Графит', text: 'Чёрный фон, плоские серые карточки, тонкие рамки, зелёный акцент — без размытия и теней.', rows: ['Сводка', 'Роутер'] },
];
const ACCENTS = [['', 'По умолчанию у оформления', null], ['blue', 'Синий', '#0a84ff'], ['green', 'Зелёный', '#30b455'], ['purple', 'Фиолетовый', '#a259e6'],
  ['orange', 'Оранжевый', '#f5870a'], ['red', 'Красный', '#f2453d'], ['teal', 'Бирюзовый', '#20b4cc'], ['pink', 'Розовый', '#ee3d73']];

const BUILTIN_SKINS = ['classic', 'graphite', 'net'];
const getSkin = () => lsGet('rl_skin', 'net') || 'net';
const getAccent = () => { const a = lsGet('rl_accent', ''); return ACCENTS.some(x => x[0] === a) ? a : ''; };
const themeMeta = () => { try { return JSON.parse(lsGet('rl_theme_meta', '') || 'null'); } catch (e) { return null; } };
function applyLook(skin, accent) {                              // built-in looks only (a custom look needs its css: a page reload does it, see pickCustom)
  const h = document.documentElement;
  if (skin && skin !== 'classic') h.setAttribute('data-skin', skin); else h.removeAttribute('data-skin');
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
    if (customNow) { location.reload(); return; }                    // leaving a custom look: its texts and icons are in memory — a clean start
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
    try { await api('/api/themes/' + t.id, { method: 'DELETE' }); if (skin === t.id) { pickBuiltin('net'); return; } reload(); } catch (e) { toast(e.message, true); }
  };
  const customs = (list && list.themes) || [];
  const card = (id, name, text, ok = true, base = 'classic', meta = null) => <div key={id} className={'look-skin' + (skin === id ? ' on' : '') + (ok ? '' : ' off')} role="button" tabIndex={0}
    onClick={() => ok && (meta ? pickCustom(meta) : pickBuiltin(id))}>
    <div className="look-prev" data-skin={meta ? (base === 'graphite' ? 'graphite' : 'classic') : id} data-theme-id={meta ? id : undefined} data-theme={th} data-accent={accent || undefined}>
      {meta && meta.preview ? <img src={meta.preview} alt="" style={{ width: '100%', borderRadius: 8, display: 'block' }} /> : <>
        <div className="lp-card"><i /><span>Сводка</span><small>10/11</small></div><div className="lp-ok">Всё работает</div><span className="lp-btn">Кнопка</span></>}
    </div>
    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><b>{name}</b>{skin === id ? <span className="badge online">выбрано</span> : null}{!ok ? <span className="badge offline">не подходит</span> : null}</div>
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
