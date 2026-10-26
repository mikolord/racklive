/* «План»: фоны из карты (до 6: обзор района + подробные куски там, где дома) и контуры домов.
   Спутниковый снимок собирается В БРАУЗЕРЕ один раз (плитки карты → один холст → один JPEG) и загружается на Rack Live одним файлом;
   дальше все (в том числе гости, которым план открыт) получают только этот файл, он кэшируется на год. Сервер картинки не разбирает и карты не трогает.
   Масштаб снимка известен точно (метров на пиксель по широте и зум-уровню), поэтому в плане 10 единиц = 1 метр; несколько снимков совмещаются по координатам. */
const PPM = 10;                                                    // единиц плана в метре
const MAX_SIDE = 2048;                                             // самый большой снимок в точках (файл ≈ 0,4–1,5 МБ)
const RADII = [[100, '100 м'], [300, '300 м'], [500, '500 м'], [1000, '1 км'], [2000, '2 км'], [5000, '5 км'], [10000, '10 км'], [20000, '20 км']];
const ESRI_ATTR = 'Снимок: Esri, Maxar, Earthstar Geographics';
const esriUrl = (z, x, y) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
const MERC_R = 20037508.342789244, MERC_PX0 = 156543.03392;        // полуокружность Земли в «меркаторских» метрах; метров на пиксель на зуме 0
const mercatorPx = (lat, lon, z) => { const s = 256 * 2 ** z, sin = Math.sin(lat * Math.PI / 180);
  return { x: (lon + 180) / 360 * s, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * s }; };
const mPerPx = (lat, z) => MERC_PX0 * Math.cos(lat * Math.PI / 180) / 2 ** z;       // метров НА МЕСТНОСТИ на пиксель
const mercM = (lat, lon) => ({ x: lon * MERC_R / 180, y: Math.log(Math.tan((90 + lat) * Math.PI / 360)) * MERC_R / Math.PI });
const fromMercM = (x, y) => ({ lon: x / MERC_R * 180, lat: Math.atan(Math.exp(y / MERC_R * Math.PI)) * 360 / Math.PI - 90 });
const snapO = v => Math.round(v / 10) * 10;                        // углы контура — через 1 метр

/* радиус участка → какой зум и какого размера снимок: самый подробный, который влезает в MAX_SIDE */
function snapPlan(lat, R) {
  const side = 2 * R;
  for (let z = 19; z >= 8; z--) { const S = Math.ceil(side / mPerPx(lat, z)); if (S <= MAX_SIDE) return { z, S: Math.max(256, Math.ceil(S / 8) * 8) }; }
  return { z: 8, S: MAX_SIDE };
}
/* где на плане лежит снимок (центр lat/lon, S точек, зум z): относительно уже стоящего фона-образца ref {x,y,w,h,lat,lon}, иначе вокруг точки free.
   Один коэффициент для всего плана (широта образца), поэтому обзор и подробные снимки совпадают без швов. */
function snapPlace(lat, lon, S, z, ref, free) {
  const k = Math.cos((ref ? ref.lat : lat) * Math.PI / 180), side = S * (MERC_PX0 / 2 ** z) * k * PPM;
  let cx, cy;
  if (ref) { const m = mercM(lat, lon), m0 = mercM(ref.lat, ref.lon); cx = ref.x + ref.w / 2 + (m.x - m0.x) * k * PPM; cy = ref.y + ref.h / 2 - (m.y - m0.y) * k * PPM; }
  else { cx = free.x; cy = free.y; }
  return { x: Math.round(cx - side / 2), y: Math.round(cy - side / 2), w: Math.round(side), h: Math.round(side) };
}
/* точка плана → широта/долгота (по фону-образцу): нужна «живой карте» */
function worldToGeo(wx, wy, ref) {
  const k = Math.cos(ref.lat * Math.PI / 180), m0 = mercM(ref.lat, ref.lon);
  return fromMercM(m0.x + (wx - (ref.x + ref.w / 2)) / (k * PPM), m0.y - (wy - (ref.y + ref.h / 2)) / (k * PPM));
}
const geoRef = bgs => (bgs || []).filter(b => b.lat != null && b.lon != null).sort((a, b) => b.w - a.w)[0] || null;      // самый большой фон с координатами

/* ----- геометрия контуров ----- */
function polyBox(pts) { const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  return { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) }; }
function polyCenter(pts) {                                         // центр тяжести площади; у вырожденного контура — середина рамки
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < pts.length; i++) { const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length], f = x0 * y1 - x1 * y0; a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f; }
  if (Math.abs(a) < 1e-6) { const b = polyBox(pts); return { x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2 }; }
  return { x: cx / (3 * a), y: cy / (3 * a) };
}
function polyArea(pts) { let a = 0; for (let i = 0; i < pts.length; i++) { const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length]; a += x0 * y1 - x1 * y0; } return Math.abs(a) / 2; }
function inPoly(p, pts) { let c = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > p.y) !== (yj > p.y) && p.x < (xj - xi) * (p.y - yi) / (yj - yi) + xi) c = !c; }
  return c; }
const kmText = m => m >= 1000 ? `${+(m / 1000).toFixed(1)} км` : `${Math.round(m)} м`;

/* ----- снимок: адрес → координаты → плитки → один JPEG ----- */
async function geocode(text) {
  const m = text.match(/^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/);                    // «55.7558, 37.6173» — координаты как есть
  if (m) return [{ name: `${m[1]}, ${m[2]}`, lat: +m[1], lon: +m[2] }];
  const r = await fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&accept-language=ru&q=' + encodeURIComponent(text));
  if (!r.ok) throw new Error('поиск адреса сейчас недоступен — введите координаты вида 55.7558, 37.6173');
  return (await r.json()).map(x => ({ name: x.display_name, lat: +x.lat, lon: +x.lon }));
}
const loadTile = (z, x, y) => new Promise((ok, no) => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => ok(im);
  im.onerror = () => no(new Error('карта не отдала снимок — нет интернета или сервис недоступен')); im.src = esriUrl(z, x, y); });
async function buildSnapshot(lat, lon, z, S) {
  const c = mercatorPx(lat, lon, z), left = c.x - S / 2, top = c.y - S / 2, n = 2 ** z;
  const cv = document.createElement('canvas'); cv.width = cv.height = S; const g = cv.getContext('2d'), jobs = [];
  for (let ty = Math.floor(top / 256); ty <= Math.floor((top + S - 1) / 256); ty++)
    for (let tx = Math.floor(left / 256); tx <= Math.floor((left + S - 1) / 256); tx++) if (ty >= 0 && ty < n) jobs.push([tx, ty]);
  for (let i = 0; i < jobs.length; i += 6)                           // по шесть плиток за раз: карту не нагружаем
    await Promise.all(jobs.slice(i, i + 6).map(([tx, ty]) => loadTile(z, ((tx % n) + n) % n, ty).then(im => g.drawImage(im, Math.round(tx * 256 - left), Math.round(ty * 256 - top)))));
  return cv;
}
const canvasBlob = (cv, q = .82) => new Promise((ok, no) => cv.toBlob(b => b ? ok(b) : no(new Error('не удалось сохранить снимок')), 'image/jpeg', q));
async function fileToBlob(file) {                                  // свой файл: не больше 2000 пикселей по большой стороне, JPEG
  const bmp = await createImageBitmap(file), k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
  const cv = document.createElement('canvas'); cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
  cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
  return { blob: await canvasBlob(cv, .85), ratio: cv.height / cv.width };
}
async function uploadBg(blob, meta) {
  const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': blob.type || 'image/jpeg' }, body: blob };
  const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
  const qs = Object.entries(meta).filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  const r = await (await fetch('/api/plan/bg?' + qs, init)).json();
  if (!r.ok) throw new Error(r.error || 'сервер не принял фон');
  return r;
}

/* ----- окно «Фон плана» ----- */
function PlanBgModal({ plan, center, onClose, onMove }) {
  const { savePlan, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const bgs = plan.bgs || [];
  const [tab, setTab] = useState('sat');
  const [q, setQ] = useState(''); const [found, setFound] = useState(null); const [pick, setPick] = useState(0);
  const [R, setR] = useState(300); const [custom, setCustom] = useState('');
  const [prev, setPrev] = useState(null);                              // { url, blob, kind, ..., size }
  const [busy, setBusy] = useState(''); const [wm, setWm] = useState('100');
  const [ops, setOps] = useState({}); const timers = useRef({});
  const fileRef = useRef(null);
  useEffect(() => () => { if (prev && prev.url) URL.revokeObjectURL(prev.url); }, [prev]);
  const ref = geoRef(bgs);
  const find = async () => {
    if (!q.trim()) return;
    setBusy('find'); setFound(null); setPrev(null);
    try { const r = await geocode(q.trim()); setFound(r); setPick(0); if (!r.length) toast('Такой адрес не нашёлся — добавьте город или введите координаты', true); }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const lat = found && found[pick] ? found[pick].lat : null, lon = found && found[pick] ? found[pick].lon : null;
  const rad = Math.max(50, Math.min(20000, +custom > 0 ? +custom : R));
  const sp = lat != null ? snapPlan(lat, rad) : null;
  const tiles = sp ? (Math.ceil(sp.S / 256) + 1) ** 2 : 0;
  const name = `${rad >= 3000 ? 'Обзор' : 'Подробно'} · ${kmText(rad)}`;
  const show = async () => {
    setBusy('show');
    try { const cv = await buildSnapshot(lat, lon, sp.z, sp.S), blob = await canvasBlob(cv, sp.S > 1600 ? .74 : .82);
      setPrev({ url: URL.createObjectURL(blob), blob, kind: 'sat', lat, lon, z: sp.z, S: sp.S, r: Math.round(rad), size: blob.size, ...snapPlace(lat, lon, sp.S, sp.z, ref, center) }); }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const pickFile = async f => {
    if (!f) return; setBusy('file');
    try { const { blob, ratio } = await fileToBlob(f); setPrev({ url: URL.createObjectURL(blob), blob, kind: 'file', ratio, size: blob.size }); }
    catch (e) { toast('Не удалось прочитать картинку: ' + e.message, true); } finally { setBusy(''); if (fileRef.current) fileRef.current.value = ''; }
  };
  const apply = async () => {
    setBusy('apply');
    try {
      let meta;
      if (prev.kind === 'sat') meta = { x: prev.x, y: prev.y, w: prev.w, h: prev.h, op: ref ? .9 : .85, attr: ESRI_ATTR, lat: prev.lat.toFixed(6), lon: prev.lon.toFixed(6), z: prev.z, r: prev.r, name };
      else { const w = Math.max(5, +wm || 100) * PPM, h = w * prev.ratio; meta = { x: Math.round(center.x - w / 2), y: Math.round(center.y - h / 2), w: Math.round(w), h: Math.round(h), op: .85, attr: '', name: 'Свой файл' }; }
      await uploadBg(prev.blob, meta); await refresh(); toast('Фон добавлен'); onClose();
    } catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const setOpacity = (id, v) => { setOps(o => ({ ...o, [id]: v })); clearTimeout(timers.current[id]);
    timers.current[id] = setTimeout(() => savePlan({ ...plan, bgs: bgs.map(b => b.id === id ? { ...b, op: v } : b) }), 400); };
  const removeBg = async b => {
    if (!(await confirm(`Убрать фон «${b.name || 'без названия'}»? Дома, контуры и магистрали останутся.`, { danger: true, ok: 'Убрать фон' }))) return;
    try { await api('/api/plan/bg/' + b.id, { method: 'DELETE' }); await refresh(); if (bgs.length < 2) onClose(); } catch (e) { toast(e.message, true); }
  };
  const kb = prev ? Math.round(prev.size / 1024) : 0;
  const full = bgs.length >= 6;
  return <Modal title="Фон плана" onClose={onClose} wide
    footer={<><div className="grow" /><Btn onClick={onClose}>Закрыть</Btn>
      {prev && !full ? <Btn kind="primary" icon="check" busy={busy === 'apply'} disabled={!!busy && busy !== 'apply'} onClick={apply}>Добавить фон</Btn> : null}</>}>
    {bgs.length ? <div className="card pad" style={{ marginBottom: 12 }}>
      <b style={{ fontSize: 14 }}>Фоны на плане · {bgs.length} из 6</b>
      <div className="dim" style={{ fontSize: 12.5, margin: '2px 0 8px' }}>Большие лежат внизу, подробные — поверх них. Обзор района и подробные кусочки там, где стоят дома, совмещаются по координатам сами.</div>
      {[...bgs].sort((a, b) => b.w - a.w).map(b => { const op = ops[b.id] != null ? ops[b.id] : b.op;
        return <div key={b.id} style={{ padding: '8px 0', borderTop: '1px solid var(--line)' }}>
          <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
            <b style={{ fontSize: 13.5 }}>{b.name || 'Фон'}</b>
            <span className="dim" style={{ fontSize: 12.5 }}>≈ {kmText(b.w / PPM)} × {kmText(b.h / PPM)}{b.lat != null ? ` · ${b.lat.toFixed(4)}, ${b.lon.toFixed(4)}` : ' · свой файл'}</span>
            <div className="grow" />
            <Btn size="sm" icon="resize" onClick={() => onMove(b.id)}>Подвинуть</Btn><Btn size="sm" kind="danger" icon="trash" onClick={() => removeBg(b)}>Убрать</Btn></div>
          <div className="row" style={{ gap: 8, alignItems: 'center', marginTop: 4 }}><span className="dim" style={{ fontSize: 12.5, width: 118 }}>Яркость {Math.round(op * 100)}%</span>
            <input type="range" min=".2" max="1" step=".05" value={op} onChange={e => setOpacity(b.id, +e.target.value)} style={{ flex: 1 }} /></div></div>; })}
    </div> : null}
    {full ? <div className="err-note">Фонов уже 6 — уберите ненужный, чтобы добавить новый.</div> : <>
    <b style={{ fontSize: 14 }}>{bgs.length ? 'Добавить фон' : 'Поставить фон'}</b>
    <Seg value={tab} onChange={v => { setTab(v); setPrev(null); }} options={[{ value: 'sat', label: 'Со спутника по адресу' }, { value: 'file', label: 'Свой файл' }]} />
    {tab === 'sat' ? <>
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end', marginTop: 10 }}>
        <div className="grow" style={{ minWidth: 220 }}><Field label="Адрес участка или координаты" hint="Например: «Краснодар, ул. Красная 10» или «55.7558, 37.6173»">
          <input className="input" value={q} placeholder="город, улица, дом" onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') find(); }} /></Field></div>
        <Btn busy={busy === 'find'} disabled={!q.trim() || (!!busy && busy !== 'find')} onClick={find}>Найти</Btn></div>
      {found && found.length ? <div className="list" style={{ marginTop: 8 }}>{found.map((f, i) => <div key={i} className="li" style={{ cursor: 'pointer', fontSize: 13 }} onClick={() => { setPick(i); setPrev(null); }}>
        <input type="radio" checked={pick === i} readOnly /><span className="grow" style={{ marginLeft: 8 }}>{f.name}</span></div>)}</div> : null}
      {lat != null ? <>
        <Field label="Радиус вокруг этого места" hint="Больше радиус — больше территория, но грубее картинка. Для района — «5–10 км», для участка и дома — «100–500 м».">
          <div className="row wrap" style={{ gap: 6 }}>{RADII.map(([m, t]) => <button key={m} type="button" className={'chip' + (!custom && R === m ? ' on' : '')} onClick={() => { setR(m); setCustom(''); setPrev(null); }}>{t}</button>)}
            <input className="input mono" style={{ width: 130 }} value={custom} placeholder="свой, метров" onChange={e => { setCustom(e.target.value.replace(/[^\d]/g, '')); setPrev(null); }} /></div></Field>
        <div className="row wrap" style={{ gap: 12, marginTop: 6, alignItems: 'center' }}>
          <div className="dim" style={{ fontSize: 13 }}>Снимок {kmText(2 * rad)} × {kmText(2 * rad)}: ≈ {mPerPx(lat, sp.z) < 1 ? Math.round(mPerPx(lat, sp.z) * 100) + ' см' : mPerPx(lat, sp.z).toFixed(1) + ' м'} на точку, {sp.S}×{sp.S} точек, ~{tiles} плиток карты</div>
          <div className="grow" />
          <Btn kind="primary" busy={busy === 'show'} disabled={!!busy && busy !== 'show'} onClick={show}>Показать снимок</Btn></div>
        {rad > 1500 ? <div className="dim" style={{ fontSize: 12.5, marginTop: 4 }}>Это обзорный снимок: дома на нём будут пятнами. Для подробностей потом добавьте ещё один фон на 100–500 м у нужного дома — он ляжет поверх точно по координатам.</div> : null}
      </> : null}
      <div className="dim" style={{ fontSize: 12.5, marginTop: 8, lineHeight: 1.5 }}>Снимок берётся с карты Esri один раз и сохраняется у вас как одна картинка (до 1,5 МБ) — Rack Live потом не ходит в интернет за картой, и план открывается быстро.
        Адрес участка при этом уходит сервисам поиска и карты. Если вместо дома видна серая заглушка «нет данных», выберите радиус побольше.</div>
    </> : <>
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end', marginTop: 10 }}>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={e => pickFile(e.target.files[0])} />
        <Btn icon="upload" busy={busy === 'file'} onClick={() => fileRef.current.click()}>Выбрать картинку</Btn>
        <Field label="Ширина снимка на местности, м" hint="Сколько метров от левого края картинки до правого — по ней считается масштаб (и площадь домов).">
          <input className="input mono" value={wm} onChange={e => setWm(e.target.value)} style={{ width: 110 }} /></Field></div>
      <div className="dim" style={{ fontSize: 12.5, marginTop: 8 }}>Подойдёт скриншот со спутника, фото с дрона или план участка. Большие картинки сожмутся до 2000 пикселей. Такой фон без координат: подвиньте его вручную, чтобы совместить с домами.</div>
    </>}
    {prev ? <div style={{ marginTop: 12 }}>
      <img src={prev.url} alt="" style={{ maxWidth: '100%', maxHeight: 340, borderRadius: 10, display: 'block' }} />
      <div className="dim" style={{ fontSize: 12.5, marginTop: 6 }}>{kb} КБ{prev.kind === 'sat' ? ' · ' + ESRI_ATTR : ''} — так фон ляжет под план{ref && prev.kind === 'sat' ? ' (по координатам, поверх обзора)' : ''}.</div></div> : null}
    </>}
  </Modal>;
}
