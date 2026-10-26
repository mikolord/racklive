/* «План»: фон из карты и контуры домов.
   Спутниковый снимок собирается В БРАУЗЕРЕ один раз (плитки карты → один холст → один JPEG ~150–300 КБ) и загружается на Rack Live одним файлом;
   дальше все (в том числе гости, которым план открыт) получают только этот файл, он кэшируется на год. Сервер картинки не разбирает и карты не трогает.
   Масштаб снимка известен точно (метров на пиксель по широте и зум-уровню), поэтому в плане 10 единиц = 1 метр. */
const PPM = 10;                                                    // единиц плана в метре
const ESRI_ATTR = 'Снимок: Esri, Maxar, Earthstar Geographics';
const esriUrl = (z, x, y) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
const mercatorPx = (lat, lon, z) => { const s = 256 * 2 ** z, sin = Math.sin(lat * Math.PI / 180);
  return { x: (lon + 180) / 360 * s, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * s }; };
const mPerPx = (lat, z) => 156543.03392 * Math.cos(lat * Math.PI / 180) / 2 ** z;
const snapO = v => Math.round(v / 10) * 10;                        // углы контура — через 1 метр

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
  return r.plan;
}

/* ----- окно «Фон плана» ----- */
function PlanBgModal({ plan, center, onClose, onMove }) {
  const { savePlan, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const bg = plan.bg;
  const [tab, setTab] = useState('sat');
  const [q, setQ] = useState(''); const [found, setFound] = useState(null); const [pick, setPick] = useState(0);
  const [z, setZ] = useState(18); const [S, setS] = useState(1024);
  const [prev, setPrev] = useState(null);                              // { url, blob, kind, w, h, lat, lon, z }
  const [busy, setBusy] = useState(''); const [wm, setWm] = useState('100');
  const [op, setOp] = useState(bg ? bg.op : .85); const timer = useRef(null);
  const fileRef = useRef(null);
  useEffect(() => () => { if (prev && prev.url) URL.revokeObjectURL(prev.url); }, [prev]);
  const place = (w, h) => ({ x: Math.round(center.x - w / 2), y: Math.round(center.y - h / 2), w: Math.round(w), h: Math.round(h) });
  const find = async () => {
    if (!q.trim()) return;
    setBusy('find'); setFound(null); setPrev(null);
    try { const r = await geocode(q.trim()); setFound(r); setPick(0); if (!r.length) toast('Такой адрес не нашёлся — добавьте город или введите координаты', true); }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const lat = found && found[pick] ? found[pick].lat : null, lon = found && found[pick] ? found[pick].lon : null;
  const mpp = lat != null ? mPerPx(lat, z) : null;
  const show = async () => {
    setBusy('show');
    try { const cv = await buildSnapshot(lat, lon, z, S); const blob = await canvasBlob(cv);
      setPrev({ url: URL.createObjectURL(blob), blob, kind: 'sat', lat, lon, z, size: blob.size, ...place(S * mpp * PPM, S * mpp * PPM) }); }
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
      if (prev.kind === 'sat') meta = { x: prev.x, y: prev.y, w: prev.w, h: prev.h, op: .85, attr: ESRI_ATTR, lat: prev.lat.toFixed(6), lon: prev.lon.toFixed(6), z: prev.z };
      else { const w = Math.max(5, +wm || 100) * PPM; meta = { ...place(w, w * prev.ratio), op: .85, attr: '' }; }
      await uploadBg(prev.blob, meta); await refresh(); toast('Фон поставлен'); onClose();
    } catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const setOpacity = v => { setOp(v); clearTimeout(timer.current); timer.current = setTimeout(() => savePlan({ ...plan, bg: { ...plan.bg, op: v } }), 400); };
  const removeBg = async () => {
    if (!(await confirm('Убрать фон с плана? Дома, контуры и магистрали останутся.', { danger: true, ok: 'Убрать фон' }))) return;
    try { await api('/api/plan/bg', { method: 'DELETE' }); await refresh(); onClose(); } catch (e) { toast(e.message, true); }
  };
  const kb = prev ? Math.round(prev.size / 1024) : 0;
  return <Modal title="Фон плана" onClose={onClose} wide
    footer={<><div className="grow" /><Btn onClick={onClose}>Закрыть</Btn>
      {prev ? <Btn kind="primary" icon="check" busy={busy === 'apply'} disabled={!!busy && busy !== 'apply'} onClick={apply}>{bg ? 'Заменить фон' : 'Поставить фон'}</Btn> : null}</>}>
    {bg ? <div className="card pad" style={{ marginBottom: 12 }}>
      <div className="row wrap" style={{ gap: 10, alignItems: 'center' }}>
        <b style={{ fontSize: 14 }}>Фон стоит</b>
        <span className="dim" style={{ fontSize: 13 }}>{bg.lat != null ? `снимок ${bg.lat.toFixed(4)}, ${bg.lon.toFixed(4)}` : 'свой файл'} · ≈ {Math.round(bg.w / PPM)}×{Math.round(bg.h / PPM)} м</span>
        <div className="grow" />
        <Btn size="sm" icon="resize" onClick={onMove}>Подвинуть</Btn><Btn size="sm" kind="danger" icon="trash" onClick={removeBg}>Убрать фон</Btn></div>
      <Field label={`Яркость фона: ${Math.round(op * 100)}%`} hint="Если подписи плохо читаются — сделайте фон бледнее.">
        <input type="range" min=".2" max="1" step=".05" value={op} onChange={e => setOpacity(+e.target.value)} style={{ width: '100%' }} /></Field>
    </div> : null}
    <Seg value={tab} onChange={v => { setTab(v); setPrev(null); }} options={[{ value: 'sat', label: 'Со спутника по адресу' }, { value: 'file', label: 'Свой файл' }]} />
    {tab === 'sat' ? <>
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end', marginTop: 10 }}>
        <div className="grow" style={{ minWidth: 220 }}><Field label="Адрес участка или координаты" hint="Например: «Краснодар, ул. Красная 10» или «55.7558, 37.6173»">
          <input className="input" value={q} placeholder="город, улица, дом" onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') find(); }} /></Field></div>
        <Btn busy={busy === 'find'} disabled={!q.trim() || (!!busy && busy !== 'find')} onClick={find}>Найти</Btn></div>
      {found && found.length ? <div className="list" style={{ marginTop: 8 }}>{found.map((f, i) => <div key={i} className="li" style={{ cursor: 'pointer', fontSize: 13 }} onClick={() => { setPick(i); setPrev(null); }}>
        <input type="radio" checked={pick === i} readOnly /><span className="grow" style={{ marginLeft: 8 }}>{f.name}</span></div>)}</div> : null}
      {lat != null ? <div className="row wrap" style={{ gap: 12, marginTop: 10, alignItems: 'flex-end' }}>
        <Field label="Подробность"><select className="select" value={z} onChange={e => { setZ(+e.target.value); setPrev(null); }}>
          <option value={17}>участок целиком (дальше)</option><option value={18}>дом и двор (рекомендую)</option><option value={19}>очень подробно (ближе)</option></select></Field>
        <Field label="Размер снимка"><select className="select" value={S} onChange={e => { setS(+e.target.value); setPrev(null); }}>
          <option value={768}>маленький</option><option value={1024}>средний</option><option value={1536}>большой</option></select></Field>
        <div className="dim" style={{ fontSize: 13, paddingBottom: 10 }}>≈ {Math.round(S * mpp)}×{Math.round(S * mpp)} м, ~{Math.ceil(Math.pow(Math.ceil(S / 256) + 1, 2))} плиток карты</div>
        <Btn kind="primary" busy={busy === 'show'} disabled={!!busy && busy !== 'show'} onClick={show}>Показать снимок</Btn></div> : null}
      <div className="dim" style={{ fontSize: 12.5, marginTop: 8, lineHeight: 1.5 }}>Снимок берётся с карты Esri один раз и сохраняется у вас как одна картинка (до 300 КБ) — Rack Live потом не ходит в интернет за картой, и план открывается быстро.
        Адрес участка при этом уходит сервисам поиска и карты. Если вместо дома видна серая заглушка «нет данных», выберите «дальше».</div>
    </> : <>
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end', marginTop: 10 }}>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={e => pickFile(e.target.files[0])} />
        <Btn icon="upload" busy={busy === 'file'} onClick={() => fileRef.current.click()}>Выбрать картинку</Btn>
        <Field label="Ширина снимка на местности, м" hint="Сколько метров от левого края картинки до правого — по ней считается масштаб (и площадь домов).">
          <input className="input mono" value={wm} onChange={e => setWm(e.target.value)} style={{ width: 110 }} /></Field></div>
      <div className="dim" style={{ fontSize: 12.5, marginTop: 8 }}>Подойдёт скриншот со спутника, фото с дрона или план участка. Большие картинки сожмутся до 2000 пикселей.</div>
    </>}
    {prev ? <div style={{ marginTop: 12 }}>
      <img src={prev.url} alt="" style={{ maxWidth: '100%', maxHeight: 340, borderRadius: 10, display: 'block' }} />
      <div className="dim" style={{ fontSize: 12.5, marginTop: 6 }}>{kb} КБ{prev.kind === 'sat' ? ' · ' + ESRI_ATTR : ''} — так фон ляжет под план.</div></div> : null}
  </Modal>;
}
