/* Настройки → Оформление: the look of the interface. «Rack Live» (the original, the default) or «Графит» (flat, black, thin outlines, green accent),
   plus an accent colour and the light / dark theme. Kept per device in localStorage (rl_skin, rl_accent, rl_theme); the page applies them before the first paint (index.html). */
const SKINS = [
  { id: 'classic', name: 'Rack Live', text: 'Стекло, мягкие градиенты и синий акцент — как в iOS. Основное оформление.', rows: ['Сводка', 'Роутер'] },
  { id: 'graphite', name: 'Графит', text: 'Чёрный фон, плоские серые карточки, тонкие рамки, зелёный акцент — без размытия и теней.', rows: ['Сводка', 'Роутер'] },
];
const ACCENTS = [['', 'По умолчанию у оформления', null], ['blue', 'Синий', '#0a84ff'], ['green', 'Зелёный', '#30b455'], ['purple', 'Фиолетовый', '#a259e6'],
  ['orange', 'Оранжевый', '#f5870a'], ['red', 'Красный', '#f2453d'], ['teal', 'Бирюзовый', '#20b4cc'], ['pink', 'Розовый', '#ee3d73']];

const getSkin = () => { const k = lsGet('rl_skin', 'classic'); return SKINS.some(x => x.id === k) ? k : 'classic'; };
const getAccent = () => { const a = lsGet('rl_accent', ''); return ACCENTS.some(x => x[0] === a) ? a : ''; };
function applyLook(skin, accent) {
  const h = document.documentElement;
  if (skin && skin !== 'classic') h.setAttribute('data-skin', skin); else h.removeAttribute('data-skin');
  if (accent) h.setAttribute('data-accent', accent); else h.removeAttribute('data-accent');
  const fav = document.querySelector('link[rel~="icon"]'); if (fav) fav.setAttribute('href', skin === 'graphite' ? 'icon-graphite.svg?v=1' : 'icon.svg?v=27');
}
const skinName = () => (SKINS.find(x => x.id === getSkin()) || SKINS[0]).name;

function LookCard() {
  const [skin, setSkin] = useState(getSkin); const [accent, setAccent] = useState(getAccent);
  const { theme, setTheme } = useApp();
  const pickSkin = id => { setSkin(id); lsSet('rl_skin', id); applyLook(id, accent); };
  const pickAccent = a => { setAccent(a); lsSet('rl_accent', a); applyLook(skin, a); };
  const th = document.documentElement.getAttribute('data-theme') || 'dark';
  return <>
    <Card title="Стиль интерфейса">
      <div className="look-skins">{SKINS.map(x => <button type="button" key={x.id} className={'look-skin' + (skin === x.id ? ' on' : '')} onClick={() => pickSkin(x.id)}>
        <div className="look-prev" data-skin={x.id} data-theme={th} data-accent={accent || undefined}>
          <div className="lp-card"><i /><span>{x.rows[0]}</span><small>10/11</small></div>
          <div className="lp-ok">Всё работает</div>
          <span className="lp-btn">Кнопка</span>
        </div>
        <div><b>{x.name}</b>{skin === x.id ? <span className="badge online" style={{ marginLeft: 8 }}>выбрано</span> : null}</div>
        <small>{x.text}</small></button>)}</div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Оформление запоминается на этом устройстве: на телефоне и на компьютере можно выбрать разное. Приложения Frank и «Тест скорости» подхватывают его тоже.</div>
    </Card>
    <Card title="Цвет акцента">
      <div className="look-accents">{ACCENTS.map(([id, name, col]) => <button type="button" key={id || 'def'} title={name} aria-label={name}
        className={'look-dot' + (accent === id ? ' on' : '') + (col ? '' : ' def')} style={col ? { background: col } : null} onClick={() => pickAccent(id)} />)}</div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 10 }}>Цвет кнопок, выбранных вкладок и переключателей. Цвета статусов (в сети, ошибка) не меняются.</div>
    </Card>
    <Card title="Светлая и тёмная тема">
      <Seg value={theme} onChange={setTheme} options={[{ value: 'auto', label: 'Как в системе' }, { value: 'dark', label: 'Тёмная' }, { value: 'light', label: 'Светлая' }]} />
    </Card>
  </>;
}
