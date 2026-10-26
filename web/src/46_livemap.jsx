/* «Живая карта (3D)» — холст «Плана» на весь экран: схема района (OpenStreetMap, OpenFreeMap) или спутник с наклоном и вращением, а на нём ВАШИ дома объёмно
   (высота — по числу этажей или своя, цвет — свой или по состоянию устройств внутри), магистрали и столбы. Библиотека MapLibre (1 МБ, ~270 КБ по сети, в кэше браузера на год)
   и плитки грузятся только когда карта открыта; при закрытии карта целиком выгружается из памяти. Положение домов на земле берётся из фона с координатами или из выбранного
   места (plan.geo) — см. geoRef / worldToGeo. Все кнопки карты лежат в общем выезжающем меню (38_workmenu.jsx, WorkSlot), внизу — панель действий выбранного дома. */
const LIVE_VER = '5.24.0';
const LIVE_COLOR = { online: '#30d158', warning: '#ff9f0a', offline: '#ff453a', '': '#8e8e93' };
const LIVE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
/* Схема в стиле Google/Apple: векторные плитки OpenStreetMap (OpenFreeMap, без ключа), стиль «positron» перекрашивается под тему приложения (data-theme на <html>):
   светлая — серые дома и сине-серые дороги, тёмная — те же тона в темноте. Дома OSM объёмные, номера домов видны с 17-го масштаба. Спутник Esri — второй режим. */
const LIVE_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
const LIVE_SCHEME = {
  light: { bg: '#f6f6f6', bld: '#e4e4e8', road: '#aab6c8', edge: '#9eabbf', water: '#cfdcea', park: '#ecefea', text: '#5d6b82', halo: '#f6f6f6', num: '#7a8696' },
  dark: { bg: '#1b1c20', bld: '#2c2e35', road: '#3f4859', edge: '#363e4c', water: '#1e2b39', park: '#1f231f', text: '#97a3b8', halo: '#1b1c20', num: '#7f8aa0' } };
let liveSchemeCache = null;
const liveDark = () => document.documentElement.getAttribute('data-theme') === 'dark';
function paintScheme(st, P, lite) {
  st.layers.forEach(l => {
    const p = l.paint = l.paint || {}, id = l.id;
    if (l.type === 'background') p['background-color'] = P.bg;
    else if (id === 'building' && lite) { l.minzoom = 14; l.paint = { 'fill-color': P.bld, 'fill-outline-color': P.edge }; }       // «лёгкий» вид: здания района плоские — на телефоне карта двигается заметно плавнее
    else if (id === 'building') { l.type = 'fill-extrusion'; l.minzoom = 14; l.paint = { 'fill-extrusion-color': P.bld, 'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 5], 'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0], 'fill-extrusion-opacity': .95 }; }
    else if (id === 'park' || /^landcover_(wood|grass)/.test(id)) p['fill-color'] = P.park;
    else if (id === 'landuse_residential') p['fill-color'] = P.bg;
    else if (id === 'water') p['fill-color'] = P.water;
    else if (id === 'waterway') p['line-color'] = P.water;
    else if (l.type === 'line' && /^(highway|tunnel)/.test(id)) { p['line-color'] = /casing|path/.test(id) ? P.edge : P.road; p['line-opacity'] = 1; }
    else if (l.type === 'symbol' && !/shield/.test(id)) {
      p['text-color'] = P.text; p['text-halo-color'] = P.halo; p['text-halo-width'] = 1.5;
      if (l.layout && l.layout['text-field']) l.layout['text-field'] = ['coalesce', ['get', 'name'], ['get', 'name_en']];       // названия по-русски, как на местности
    }
  });
  st.layers.push({ id: 'housenumber', type: 'symbol', source: 'openmaptiles', 'source-layer': 'housenumber', minzoom: 17,
    layout: { 'text-field': ['get', 'housenumber'], 'text-font': ['Noto Sans Regular'], 'text-size': 11 }, paint: { 'text-color': P.num, 'text-halo-color': P.halo, 'text-halo-width': 1.2 } });
}
const liveHexOk = v => typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v);
const housesData = spec => ({ type: 'FeatureCollection', features: spec.houses.map(h => { const c = liveHexOk(h.color) ? h.color : (LIVE_COLOR[h.status] || LIVE_COLOR['']);
  return { type: 'Feature', properties: { id: h.id, color: c, edge: liveHexOk(h.edge) ? h.edge : c, glow: h.hl ? 1 : 0, h: h.height > 0 ? h.height : h.floors * 3 + 0.5 },
    geometry: { type: 'Polygon', coordinates: [[...h.ring, h.ring[0]]] } }; }) });
const linksData = spec => ({ type: 'FeatureCollection', features: spec.links.map(l => ({ type: 'Feature', properties: { id: l.id || '' }, geometry: { type: 'LineString', coordinates: l.coords } })) });
const draftData = pts => ({ type: 'FeatureCollection', features: [
  ...(pts.length >= 3 ? [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] } }] : []),
  ...(pts.length >= 2 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: pts } }] : []),
  ...pts.map((p, i) => ({ type: 'Feature', properties: { first: i === 0 && pts.length >= 3 }, geometry: { type: 'Point', coordinates: p } }))] });
async function liveStyle(mode, spec, draft, selId, lite) {
  let st;
  if (mode === 'scheme') {
    if (!liveSchemeCache) { const r = await fetch(LIVE_STYLE_URL); if (!r.ok) throw new Error('схема недоступна'); liveSchemeCache = await r.json(); }
    st = JSON.parse(JSON.stringify(liveSchemeCache)); paintScheme(st, LIVE_SCHEME[liveDark() ? 'dark' : 'light'], lite);
  } else st = { version: 8, sources: { sat: { type: 'raster', tiles: [LIVE_TILES], tileSize: 256, maxzoom: 19, attribution: ESRI_ATTR } }, layers: [{ id: 'sat', type: 'raster', source: 'sat' }] };
  st.sources.houses = { type: 'geojson', data: housesData(spec) };
  st.sources.links = { type: 'geojson', data: linksData(spec) };
  st.sources.draft = { type: 'geojson', data: draftData(draft) };
  st.layers.push({ id: 'links', type: 'line', source: 'links', paint: { 'line-color': '#0a84ff', 'line-width': 3, 'line-dasharray': [2, 1.5] } });
  st.layers.push({ id: 'links-hit', type: 'line', source: 'links', paint: { 'line-color': '#0a84ff', 'line-width': 22, 'line-opacity': 0 } });          // широкая невидимая линия: в магистраль легко попасть пальцем
  st.layers.push({ id: 'houses-3d', type: 'fill-extrusion', source: 'houses', paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': .9 } });
  st.layers.push({ id: 'houses-glow', type: 'line', source: 'houses', filter: ['==', ['get', 'glow'], 1], layout: { 'line-join': 'round' }, paint: { 'line-color': ['get', 'edge'], 'line-width': 12, 'line-blur': 7, 'line-opacity': .75 } });
  st.layers.push({ id: 'houses-edge', type: 'line', source: 'houses', layout: { 'line-join': 'round' }, paint: { 'line-color': ['get', 'edge'], 'line-width': 2.5 } });
  st.layers.push({ id: 'house-sel', type: 'line', source: 'houses', filter: ['==', ['get', 'id'], selId || ''], layout: { 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 5, 'line-opacity': .95 } });
  st.layers.push({ id: 'draft-fill', type: 'fill', source: 'draft', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#0a84ff', 'fill-opacity': .28 } });
  st.layers.push({ id: 'draft-line', type: 'line', source: 'draft', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': '#0a84ff', 'line-width': 3 } });
  st.layers.push({ id: 'draft-pts', type: 'circle', source: 'draft', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': ['case', ['get', 'first'], 9, 5.5], 'circle-color': '#fff', 'circle-stroke-color': '#0a84ff', 'circle-stroke-width': 2.5 } });
  return st;
}
let mapLibreLoading = null;
function loadMapLibre() {
  if (window.maplibregl) return Promise.resolve(window.maplibregl);
  if (mapLibreLoading) return mapLibreLoading;
  mapLibreLoading = new Promise((ok, no) => {
    const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = `/vendor/maplibre-gl.css?v=${LIVE_VER}`; document.head.appendChild(css);
    const s = document.createElement('script'); s.src = `/vendor/maplibre-gl.js?v=${LIVE_VER}`;
    s.onload = () => window.maplibregl ? ok(window.maplibregl) : (mapLibreLoading = null, no(new Error('библиотека 3D-карты не запустилась')));
    s.onerror = () => { mapLibreLoading = null; no(new Error('не удалось загрузить библиотеку 3D-карты')); };
    document.head.appendChild(s);
  });
  return mapLibreLoading;
}

/* ----- геометрия обводки (в метрах Меркатора; точки — [lon, lat]) ----- */
const llM = p => mercM(p[1], p[0]);
const mLL = (x, y) => { const g = fromMercM(x, y); return [+g.lon.toFixed(7), +g.lat.toFixed(7)]; };
/* прямоугольник по трём нажатиям: две точки — одна сторона, третья задаёт ширину (на любую сторону от неё) */
function rectFrom3(p) {
  const a = llM(p[0]), b = llM(p[1]), c = llM(p[2]), dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1, nx = -dy / len, ny = dx / len;
  const off = (c.x - a.x) * nx + (c.y - a.y) * ny;
  return [p[0], p[1], mLL(b.x + nx * off, b.y + ny * off), mLL(a.x + nx * off, a.y + ny * off)];
}
/* кольцо здания из карты → список углов: без замыкающего повтора, не более 120 точек */
function ringFromFeature(f, lngLat) {
  const g = f.geometry; let rings = g.type === 'Polygon' ? [g.coordinates[0]] : g.type === 'MultiPolygon' ? g.coordinates.map(c => c[0]) : [];
  if (!rings.length) return null;
  /* здание из плиток карты часто приходит «составным» (MultiPolygon): в нём несколько домов подряд. Нужен тот контур, внутри которого нажали, а не самый большой из всех */
  const area = r => Math.abs(r.reduce((s, q, i) => { const n = r[(i + 1) % r.length]; return s + q[0] * n[1] - n[0] * q[1]; }, 0));
  const here = lngLat ? rings.filter(r => ringHas(r, [lngLat.lng, lngLat.lat])) : [];
  let r = (here.length ? here : rings).sort((x, y) => area(y) - area(x))[0].map(q => [+q[0].toFixed(7), +q[1].toFixed(7)]);
  if (r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1]) r = r.slice(0, -1);
  while (r.length > 120) r = r.filter((_, i) => i % 2 === 0);
  return r.length >= 3 ? r : null;
}
const LIVE_TOOLS = { auto: 'Нажмите на здание на карте — оно станет вашим домом', poly: 'Нажимайте по углам дома — по кругу', rect: 'Нажмите два угла одной стороны, потом третье нажатие задаёт ширину',
  pole: 'Нажмите на карту, куда поставить столб (можно несколько, потом «Готово»)', node: 'Нажмите на карту, куда поставить узел (потом его можно привязать к шкафу или устройству)',
  link: 'Нажмите на первый дом, столб или узел магистрали, потом на второй' };
const ringHas = (r, p) => { let c = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const [xi, yi] = r[i], [xj, yj] = r[j];
  if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c; } return c; };
/* из нескольких найденных под пальцем фигур — та, что лежит на земле ровно под точкой нажатия (при наклоне карты первой часто идёт соседняя, «стоящая сзади») */
function featHere(fs, lngLat, near) {
  if (!fs.length) return null; const p = [lngLat.lng, lngLat.lat];
  const has = f => { const g = f.geometry; if (!g) return false; const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : []; return polys.some(c => ringHas(c[0], p)); };
  const hit = fs.find(has); if (hit || !near) return hit || null;
  const cen = featCen;
  return [...fs].sort((a, b) => Math.hypot(cen(a)[0] - p[0], cen(a)[1] - p[1]) - Math.hypot(cen(b)[0] - p[0], cen(b)[1] - p[1]))[0];     // ближайший к точке на земле
}
const featCen = f => { const g = f.geometry, r = g.type === 'Polygon' ? g.coordinates[0] : g.coordinates[0][0]; return [r.reduce((s, q) => s + q[0], 0) / r.length, r.reduce((s, q) => s + q[1], 0) / r.length]; };
/* нажали на крышу при наклонённой карте: точка на земле под пальцем лежит ЗА домом (у высокого — на соседней улице), поэтому из найденных берём тот, чьё основание на экране ближе всего к пальцу */
function featScreen(fs, map, pt) {
  if (fs.length <= 1) return fs[0] || null;
  const d = f => { const s = map.project(featCen(f)); return Math.hypot(s.x - pt.x, s.y - pt.y); };
  return [...fs].sort((a, b) => d(a) - d(b))[0];
}

/* spec = { center: [lon, lat], houses: [{ id, name, ring: [[lon, lat]…], center: {lon, lat}, floors, devs, status, color, edge, hl, height }], poles: [{ id, name, lon, lat }], links: [{ coords: [[lon, lat], [lon, lat]] }] } */
function LiveMap3D({ spec, edit, sel, onSel, onAddHouse, onEditRing, onStyle, onRename, onDelete, onOpen, onNet, onAddPole, onAddNode, onMovePoint, onLinkPick, linkFrom, onEditLink,
  onRenamePoint, onDeletePoint, onBindNode, onOpenRef, noOutline }) {
  const toast = useToast();
  const box = useRef(null); const mapRef = useRef(null); const marksRef = useRef([]); const vtxRef = useRef([]);
  const [err, setErr] = useState(''); const [ready, setReady] = useState(false); const [flat, setFlat] = useState(false);
  const [mode, setMode] = useState(lsGet('rl_live_mode', '') === 'sat' ? 'sat' : 'scheme'); const modeRef = useRef(mode); modeRef.current = mode;
  const [tool, setTool] = useState(null); const [draft, setDraft] = useState([]);                  // «Обвести дом»: инструмент и углы [lon, lat]
  const [vedit, setVedit] = useState(false); const [selV, setSelV] = useState(null);                // правка углов выбранного дома
  const [styleOpen, setStyleOpen] = useState(false);
  const R = useRef({}); R.current = { spec, sel, tool, draft, onSel, onAddHouse, onEditRing, edit, vedit, onAddPole, onAddNode, onMovePoint, onLinkPick, onEditLink, linkFrom };     // свежие значения для обработчиков карты
  const finishWith = ring => {
    const n = spec.houses.length, name = ((typeof prompt === 'function' ? prompt('Название дома', `Дом ${n + 1}`) : '') || '').trim() || `Дом ${n + 1}`;
    if (onAddHouse(ring, name) !== false) { setDraft([]); setTool(null); }
  };
  const finishRef = useRef(null); finishRef.current = finishWith;
  const [lite, setLite] = useState(() => { const v = lsGet('rl_live_lite', ''); return v ? v === '1' : (window.matchMedia && matchMedia('(max-width: 760px)').matches); });       // на телефоне здания района по умолчанию плоские
  const liteRef = useRef(lite); liteRef.current = lite;
  const restyle = () => { const map = mapRef.current; if (!map) return; liveStyle(modeRef.current, R.current.spec, R.current.draft, R.current.sel, liteRef.current).then(st => { if (mapRef.current === map) map.setStyle(st, { diff: false }); })
    .catch(() => { if (modeRef.current === 'scheme') { setMode('sat'); modeRef.current = 'sat'; restyle(); } }); };      // схема недоступна (нет сети до OpenFreeMap) — спутник
  useEffect(() => {
    let dead = false, map = null, themeWatch = null;
    loadMapLibre().then(async ml => {
      let style; try { style = await liveStyle(modeRef.current, R.current.spec, [], R.current.sel, liteRef.current); } catch (e) { modeRef.current = 'sat'; setMode('sat'); style = await liveStyle('sat', R.current.spec, [], R.current.sel, liteRef.current); }
      if (dead) return;
      try {
        map = new ml.Map({ container: box.current, center: R.current.spec.center, zoom: 17, pitch: 58, bearing: -25, maxPitch: 78, renderWorldCopies: false, fadeDuration: 0, style,
          pixelRatio: Math.min(window.devicePixelRatio || 1, 2) });                 // на экранах 3× карта рисовалась в 9 раз большем числе точек — хватает и двойной плотности
      } catch (e) { setErr('Эта карта рисуется видеокартой (WebGL), а в вашем браузере она недоступна.'); return; }
      themeWatch = new MutationObserver(() => { if (modeRef.current === 'scheme') restyle(); });       // тема приложения сменилась — схема перекрашивается
      themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
      mapRef.current = map;
      if (/[?&]wmtest=1/.test(location.search)) window.__rlLive = { map, ml };        // только для проверки в tools/planmap_draw_test.py: нажатия по карте имитируются
      map.addControl(new ml.NavigationControl({ visualizePitch: true }), 'top-left');
      map.on('error', e => { if (/WebGL|context/i.test(String((e && e.error && e.error.message) || e))) setErr('Эта карта рисуется видеокартой (WebGL), а в вашем браузере она недоступна.'); });
      map.on('load', () => {
        map.on('click', e => {
          const r = R.current, pt = [+e.lngLat.lng.toFixed(7), +e.lngLat.lat.toFixed(7)];
          const query = layer => { try { return map.queryRenderedFeatures(e.point, { layers: [layer] }); } catch (x) { return []; } };
          const houseAt = () => { const fs = query('houses-3d'), f = fs.length <= 1 ? fs[0] : map.getPitch() > 6 ? featScreen(fs, map, e.point) : featHere(fs, e.lngLat, true); return f ? f.properties.id : null; };
          if (!r.tool) {                                                         // обычный режим: нажали на дом — выбран, на магистраль — её окно, на пустое — выбор снят
            if (r.vedit) return;
            const hid = houseAt();
            if (hid) { r.onSel(hid); return; }
            let lf = []; try { lf = map.queryRenderedFeatures([[e.point.x - 12, e.point.y - 12], [e.point.x + 12, e.point.y + 12]], { layers: ['links-hit'] }); } catch (x) { }
            if (lf.length && lf[0].properties.id && r.edit) { r.onEditLink(lf[0].properties.id); return; }
            r.onSel(null); return; }
          if (r.tool === 'auto') {
            const f = featHere(query('building'), e.lngLat);                      // здание, лежащее на земле ровно под точкой нажатия (карта при этом смотрит сверху)
            const ring = f ? ringFromFeature(f, e.lngLat) : null;
            if (!ring) { toast(modeRef.current === 'scheme' ? 'Здесь нет здания на карте — нажмите точно на дом или выберите «По углам»' : 'Подбор здания работает на схеме: переключите карту на «Схема»', true); return; }
            finishRef.current(ring); return; }
          if (r.tool === 'pole') { r.onAddPole(pt[0], pt[1]); return; }
          if (r.tool === 'node') { r.onAddNode(pt[0], pt[1]); return; }
          if (r.tool === 'link') { const hid = houseAt(); if (hid) r.onLinkPick(hid); return; }
          const d = r.draft;
          if (r.tool === 'poly') {
            if (d.length >= 3) { const a = map.project(d[0]); if (Math.hypot(a.x - e.point.x, a.y - e.point.y) <= 16) { finishRef.current(d); return; } }
            setDraft([...d, pt]); return; }
          if (r.tool === 'rect') { const nd = [...d, pt]; if (nd.length >= 3) finishRef.current(rectFrom3(nd)); else setDraft(nd); }
        });
        const sp = R.current.spec, pts = sp.houses.flatMap(h => h.ring).concat(sp.poles.map(p => [p.lon, p.lat]));
        if (pts.length) { const b = new ml.LngLatBounds(pts[0], pts[0]); pts.forEach(p => b.extend(p)); map.fitBounds(b, { padding: 90, maxZoom: 19, pitch: 58, bearing: -25, duration: 0 }); }
        setReady(true);
      });
    }).catch(e => { if (!dead) setErr(e.message); });
    return () => { dead = true; if (themeWatch) themeWatch.disconnect(); marksRef.current.forEach(m => m.remove()); vtxRef.current.forEach(m => m.remove()); marksRef.current = []; vtxRef.current = [];
      if (map) { try { map.remove(); } catch (e) { } } mapRef.current = null; };     // карта выгружается целиком
  }, []);
  /* дома, связи, подписи и набросок обновляются на лету (дом обвели, перекрасили или переименовали — карту не перезапускаем) */
  const specKey = JSON.stringify([spec.houses, spec.poles, spec.nodes, spec.links]);
  useEffect(() => {
    const map = mapRef.current, ml = window.maplibregl; if (!ready || !map || !ml) return;
    try { const set = (id, data) => { const s = map.getSource(id); if (s) s.setData(data); };
      set('houses', housesData(spec)); set('links', linksData(spec)); set('draft', draftData(draft)); } catch (e) { }
    marksRef.current.forEach(m => m.remove()); marksRef.current = [];
    spec.houses.forEach(h => { const el = document.createElement('div'); el.className = 'live-label' + (sel === h.id ? ' sel' : ''); el.textContent = h.name;
      el.addEventListener('click', ev => { ev.stopPropagation(); if (!R.current.tool && !R.current.vedit) R.current.onSel(h.id); });
      marksRef.current.push(new ml.Marker({ element: el, anchor: 'bottom' }).setLngLat([h.center.lon, h.center.lat]).addTo(map)); });
    /* столбы и узлы: нажатие — выбрать (при «Магистрали» — выбрать конец), в правке можно перетащить */
    const point = (p, kind) => { const el = document.createElement('div');
      el.className = (kind === 'pole' ? 'live-pole' : 'live-node ' + (p.status || 'none')) + (sel === p.id || R.current.linkFrom === p.id ? ' sel' : ''); el.title = p.name;
      if (kind === 'node') el.innerHTML = '<i></i><span>' + String(p.name).replace(/[<>&]/g, '') + '</span>';
      el.addEventListener('click', ev => { ev.stopPropagation(); const r = R.current; if (r.tool === 'link') r.onLinkPick(p.id); else if (!r.tool && !r.vedit) r.onSel(p.id); });
      const m = new ml.Marker({ element: el, draggable: !!R.current.edit && !R.current.tool }).setLngLat([p.lon, p.lat]).addTo(map);
      m.on('dragend', () => { const g = m.getLngLat(); R.current.onMovePoint(kind, p.id, +g.lng.toFixed(7), +g.lat.toFixed(7)); });
      marksRef.current.push(m); };
    spec.poles.forEach(p => point(p, 'pole')); (spec.nodes || []).forEach(p => point(p, 'node'));
  }, [ready, specKey, draft, sel, tool, edit, linkFrom]);
  useEffect(() => { const map = mapRef.current; if (ready && map) { try { map.setFilter('house-sel', ['==', ['get', 'id'], sel || '']); } catch (e) { } } }, [ready, sel]);
  useEffect(() => { const map = mapRef.current; if (ready && map) map.getCanvas().style.cursor = tool ? 'crosshair' : ''; }, [ready, tool]);
  /* пока включён инструмент, карта смотрит строго сверху и не наклоняется (жестом двумя пальцами тоже): при наклоне крыша дома и земля под ней не совпадают, и нажатие попадало в соседний дом */
  useEffect(() => {
    const map = mapRef.current; if (!ready || !map) return;
    if (!tool) { try { map.setMaxPitch(78); } catch (e) { } return; }
    const lock = () => { try { map.setMaxPitch(0); } catch (e) { } };
    if (map.getPitch() > 1) { map.once('moveend', lock); map.easeTo({ pitch: 0, duration: 450 }); } else lock();
  }, [ready, tool]);
  /* правка углов выбранного дома: углы тянутся, кружок «+» на стороне добавляет угол, большой кружок в середине двигает дом целиком */
  const selHouse = sel ? spec.houses.find(x => x.id === sel) : null;
  useEffect(() => {
    vtxRef.current.forEach(m => m.remove()); vtxRef.current = [];
    const map = mapRef.current, ml = window.maplibregl;
    if (!ready || !map || !ml || !vedit || !selHouse) return;
    const ring = selHouse.ring, n = ring.length, id = selHouse.id, add = m => vtxRef.current.push(m);
    ring.forEach((q, i) => { const el = document.createElement('div'); el.className = 'live-vtx' + (selV === i ? ' sel' : '');
      el.addEventListener('click', ev => { ev.stopPropagation(); setSelV(i); });
      const m = new ml.Marker({ element: el, draggable: true }).setLngLat(q).addTo(map);
      m.on('dragend', () => { const g = m.getLngLat(); R.current.onEditRing(id, ring.map((p, k) => k === i ? [+g.lng.toFixed(7), +g.lat.toFixed(7)] : p)); setSelV(i); });
      add(m); });
    ring.forEach((q, i) => { const o = ring[(i + 1) % n], el = document.createElement('div'); el.className = 'live-mid'; el.textContent = '+';
      el.addEventListener('click', ev => { ev.stopPropagation(); if (n >= 120) { toast('Больше углов нельзя', true); return; }
        R.current.onEditRing(id, [...ring.slice(0, i + 1), [+((q[0] + o[0]) / 2).toFixed(7), +((q[1] + o[1]) / 2).toFixed(7)], ...ring.slice(i + 1)]); setSelV(i + 1); });
      add(new ml.Marker({ element: el }).setLngLat([(q[0] + o[0]) / 2, (q[1] + o[1]) / 2]).addTo(map)); });
    const c = selHouse.center, el = document.createElement('div'); el.className = 'live-move'; el.title = 'Двигать дом целиком'; el.textContent = '✥';
    const mv = new ml.Marker({ element: el, draggable: true }).setLngLat([c.lon, c.lat]).addTo(map);
    mv.on('dragend', () => { const g = mv.getLngLat(), dx = g.lng - c.lon, dy = g.lat - c.lat; R.current.onEditRing(id, ring.map(p => [+(p[0] + dx).toFixed(7), +(p[1] + dy).toFixed(7)])); });
    add(mv);
  }, [ready, vedit, specKey, sel, selV]);
  useEffect(() => { if (!selHouse) { setVedit(false); setSelV(null); setStyleOpen(false); } }, [selHouse]);

  const tilt = f => { setFlat(f); if (mapRef.current) mapRef.current.easeTo({ pitch: f ? 0 : 58, bearing: f ? 0 : -25, duration: 600 }); };
  const swap = m => { lsSet('rl_live_mode', m); modeRef.current = m; setMode(m); restyle(); };
  const fitAll = () => { const map = mapRef.current, ml = window.maplibregl; if (!map || !ml) return;
    const pts = spec.houses.flatMap(h => h.ring).concat(spec.poles.map(p => [p.lon, p.lat]), (spec.nodes || []).map(p => [p.lon, p.lat]));
    if (!pts.length) { map.easeTo({ center: spec.center, zoom: 17, duration: 600 }); return; }
    const b = new ml.LngLatBounds(pts[0], pts[0]); pts.forEach(p => b.extend(p)); map.fitBounds(b, { padding: 90, maxZoom: 19, duration: 600 }); };
  const pick = t => {
    if (!edit) { toast('Включите «Редактирование» в меню, чтобы рисовать на карте', true); return; }
    onSel(null); setVedit(false); setDraft([]); onLinkPick(null); setTool(t === tool ? null : t); if (t !== tool) setFlat(true); };
  const stopTool = () => { setTool(null); setDraft([]); onLinkPick(null); };
  const [findOpen, setFindOpen] = useState(false); const [fq, setFq] = useState('');                        // поиск по плану
  const found = fq.trim() ? (spec.search || []).filter(x => String(x.hay || x.name).toLowerCase().includes(fq.trim().toLowerCase())).slice(0, 8) : [];
  const goTo = x => { const map = mapRef.current; if (map) map.easeTo({ center: [x.lon, x.lat], zoom: Math.max(map.getZoom(), 18.5), duration: 700 }); onSel(x.id); setFindOpen(false); setFq(''); };
  const nameOf = id =>([...spec.houses, ...spec.poles, ...(spec.nodes || [])].find(x => x.id === id) || {}).name || '';
  const selPoint = sel ? (spec.poles.find(x => x.id === sel) ? { ...spec.poles.find(x => x.id === sel), kind: 'pole' } : (spec.nodes || []).find(x => x.id === sel) ? { ...(spec.nodes || []).find(x => x.id === sel), kind: 'node' } : null) : null;
  const delCorner = () => { if (!selHouse || selV == null) return; if (selHouse.ring.length <= 3) { toast('У дома должно остаться хотя бы три угла', true); return; }
    onEditRing(selHouse.id, selHouse.ring.filter((_, k) => k !== selV)); setSelV(null); };

  return <div className="live-root">
    <WorkSlot>
      <WorkSec title="Карта">
        <WorkItem icon="search" label="Найти на плане" sub="дом, столб, узел, устройство, шкаф" onClick={() => { setFindOpen(true); setFq(''); }} />
        <WorkChoice keep value={mode} options={[{ value: 'scheme', label: 'Схема', icon: 'map' }, { value: 'sat', label: 'Спутник', icon: 'globe' }]} onChange={swap} />
        <WorkItem icon="fit" label="Показать все дома" onClick={fitAll} />
        <WorkItem icon="eye" label={flat ? 'Наклонить карту (3D)' : 'Вид сверху'} onClick={() => tilt(!flat)} />
        {mode === 'scheme' ? <WorkSwitch icon="home" label="Объёмные здания района" on={!lite} onChange={v => { lsSet('rl_live_lite', v ? '0' : '1'); liteRef.current = !v; setLite(!v); restyle(); }} /> : null}
      </WorkSec>
      {edit ? <WorkSec title="Обвести дом">
        <WorkItem icon="home" label="По зданию на карте" sub="одно нажатие по зданию" on={tool === 'auto'} onClick={() => pick('auto')} />
        <WorkItem icon="edit" label="По углам" sub="нажимайте углы по кругу" on={tool === 'poly'} onClick={() => pick('poly')} />
        <WorkItem icon="plan" label="Прямоугольник" sub="две точки стороны и ширина" on={tool === 'rect'} onClick={() => pick('rect')} />
      </WorkSec> : null}
      {edit ? <WorkSec title="Сеть участка">
        <WorkItem icon="link" label="Магистраль" sub="между домами, столбами и узлами" on={tool === 'link'} onClick={() => pick('link')} />
        <WorkItem icon="pole" label="Столб" sub="нажмите на карту — поставить" on={tool === 'pole'} onClick={() => pick('pole')} />
        <WorkItem icon="rack" label="Узел" sub="можно привязать к шкафу или устройству" on={tool === 'node'} onClick={() => pick('node')} />
      </WorkSec> : null}
      {(noOutline || []).length ? <WorkSec title="Дома без контура на карте">
        {noOutline.map(b => <WorkItem key={b.id} icon="home" label={b.name} sub="открыть этажи и комнаты" onClick={() => onOpen(b.id)} />)}
      </WorkSec> : null}
      {edit && selHouse ? <WorkSec title={'Дом «' + selHouse.name + '»'}>
        <WorkItem icon="cursor" label="Править углы и двигать" on={vedit} onClick={() => { setVedit(!vedit); setTool(null); setDraft([]); setSelV(null); }} />
        <WorkItem icon="tag" label="Цвета и высота" onClick={() => setStyleOpen(true)} />
        <WorkItem icon="edit" label="Переименовать" onClick={() => onRename(selHouse.id)} />
        <WorkItem icon="trash" danger label="Удалить дом" onClick={() => onDelete(selHouse.id)} />
      </WorkSec> : null}
    </WorkSlot>
    <div className="live-map" ref={box} data-ready={ready ? '1' : ''} data-layers={ready && mapRef.current ? ['houses-3d', 'links'].filter(i => mapRef.current.getLayer(i)).join(',') : ''}>
      {findOpen ? <div className="live-find"><div className="row" style={{ gap: 6 }}><div className="grow"><SearchBox value={fq} onChange={setFq} placeholder="Найти на плане" autoFocus /></div>
        <Btn size="sm" icon="x" title="Закрыть поиск" onClick={() => { setFindOpen(false); setFq(''); }} /></div>
        {found.length ? <div className="list">{found.map((x, i) => <div key={x.kind + x.id + i} className="li" style={{ cursor: 'pointer' }} onClick={() => goTo(x)}>
          <Icon name={x.kind === 'house' ? 'home' : x.kind === 'pole' ? 'pole' : x.kind === 'rack' ? 'rack' : x.kind === 'node' ? 'rack' : 'server'} size={16} />
          <span className="grow ellipsis" style={{ marginLeft: 8 }}>{x.name}</span><span className="dim" style={{ fontSize: 12 }}>{x.sub}</span></div>)}</div>
          : fq.trim() ? <div className="dim" style={{ fontSize: 13, padding: '8px 4px' }}>Ничего не найдено</div> : null}</div> : null}
      {!ready && !err ? <div className="live-msg">Загружаю карту…</div> : null}
      {err ? <div className="live-msg err">{err}</div> : null}
      {ready && !tool && !vedit && !spec.houses.length ? <div className="live-msg hint">{edit ? 'Откройте меню справа вверху → «Обвести дом»: нажмите на здание на карте или отметьте его углы.' : 'Домов пока нет. Включите «Редактирование» в меню — тогда можно обвести дом на карте.'}</div> : null}
      {tool ? <div className="live-bar"><div className="live-bar-t">{tool === 'link' && linkFrom ? `От «${nameOf(linkFrom)}» — нажмите на второй дом, столб или узел` : LIVE_TOOLS[tool]}{draft.length ? ` · точек: ${draft.length}` : ''}</div>
        <div className="live-bar-b">{tool === 'poly' && draft.length >= 3 ? <Btn size="sm" kind="primary" icon="check" onClick={() => finishWith(draft)}>Готово</Btn> : null}
          {draft.length ? <Btn size="sm" onClick={() => setDraft(draft.slice(0, -1))}>Убрать точку</Btn> : null}
          {['pole', 'node', 'link'].includes(tool) ? <Btn size="sm" kind="primary" icon="check" onClick={stopTool}>Готово</Btn> : <Btn size="sm" onClick={stopTool}>Отмена</Btn>}</div></div>
        : vedit && selHouse ? <div className="live-bar"><div className="live-bar-t">Тяните белые кружки — углы, «+» добавляет угол, ✥ двигает дом целиком</div>
          <div className="live-bar-b">{selV != null ? <Btn size="sm" icon="minus" onClick={delCorner}>Убрать угол</Btn> : null}<Btn size="sm" kind="primary" icon="check" onClick={() => { setVedit(false); setSelV(null); }}>Готово</Btn></div></div>
        : selHouse ? <div className="live-card">
          <div className="row" style={{ gap: 8, alignItems: 'center' }}><div className="grow" style={{ minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{selHouse.name}</b>
            <div className="dim3" style={{ fontSize: 12.5 }}>{selHouse.floors} эт. · {selHouse.devs} устр.</div></div>
            <Btn size="sm" icon="x" onClick={() => onSel(null)} /></div>
          <div className="row" style={{ gap: 8, marginTop: 8 }}>
            <Btn size="sm" kind="primary" icon="home" style={{ flex: 1 }} onClick={() => onOpen(selHouse.id)}>Открыть дом</Btn>
            <Btn size="sm" icon="map" style={{ flex: 1 }} onClick={() => onNet(selHouse.id)}>Сеть дома</Btn></div>
          {edit ? <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
            <Btn size="sm" icon="tag" onClick={() => setStyleOpen(!styleOpen)}>Цвета</Btn>
            <Btn size="sm" icon="cursor" onClick={() => { setVedit(true); setSelV(null); }}>Углы</Btn>
            <Btn size="sm" icon="edit" onClick={() => onRename(selHouse.id)}>Название</Btn>
            <Btn size="sm" kind="danger" icon="trash" onClick={() => onDelete(selHouse.id)} /></div> : null}
          {edit && styleOpen ? <HouseStyle h={selHouse} onChange={p => onStyle(selHouse.id, p)} /> : null}
        </div> : selPoint ? <div className="live-card">
          <div className="row" style={{ gap: 8, alignItems: 'center' }}><div className="grow" style={{ minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{selPoint.name}</b>
            <div className="dim3" style={{ fontSize: 12.5 }}>{selPoint.kind === 'pole' ? 'Столб' : selPoint.refName ? `Узел · ${selPoint.refKind === 'place' ? 'шкаф' : 'устройство'}: ${selPoint.refName}` : 'Узел · не привязан'}</div></div>
            <Btn size="sm" icon="x" onClick={() => onSel(null)} /></div>
          <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
            {selPoint.kind === 'node' && selPoint.refName ? <Btn size="sm" kind="primary" icon={selPoint.refKind === 'place' ? 'rack' : 'server'} onClick={() => onOpenRef(selPoint.id)}>Открыть</Btn> : null}
            {edit && selPoint.kind === 'node' ? <Btn size="sm" icon="link" onClick={() => onBindNode(selPoint.id)}>{selPoint.refName ? 'Другой шкаф…' : 'Привязать к шкафу…'}</Btn> : null}
            {edit ? <Btn size="sm" icon="edit" onClick={() => onRenamePoint(selPoint.id)}>Название</Btn> : null}
            {edit ? <Btn size="sm" kind="danger" icon="trash" onClick={() => onDeletePoint(selPoint.id)} /> : null}</div>
          {edit ? <div className="dim3" style={{ fontSize: 12, marginTop: 6 }}>Перетащите {selPoint.kind === 'pole' ? 'столб' : 'узел'} на карте, чтобы переставить.</div> : null}
        </div> : null}
    </div>
  </div>;
}

/* цвета дома: заливка, контур, подсветка, высота — применяются сразу */
function HouseStyle({ h, onChange }) {
  return <div className="house-style">
    <div className="wm-sec-t">Цвет дома</div><WorkColors value={h.color || ''} autoLabel="По устройствам" onChange={v => onChange({ color: v })} />
    <div className="wm-sec-t">Цвет контура</div><WorkColors value={h.edge || ''} autoLabel="Как у дома" onChange={v => onChange({ edge: v })} />
    <div className="row" style={{ gap: 10, alignItems: 'center', padding: '6px 8px' }}><span className="grow" style={{ fontSize: 14 }}>Подсветка контура</span><Switch on={!!h.hl} onChange={v => onChange({ hl: v })} /></div>
    <div className="row" style={{ gap: 8, alignItems: 'center', padding: '4px 8px' }}><span className="grow" style={{ fontSize: 14 }}>Высота, м <span className="dim">{h.height > 0 ? '' : '(по этажам)'}</span></span>
      <Btn size="sm" icon="minus" onClick={() => onChange({ height: Math.max(3, (h.height > 0 ? h.height : h.floors * 3 + 0.5) - 3) })} />
      <b style={{ minWidth: 34, textAlign: 'center' }}>{Math.round(h.height > 0 ? h.height : h.floors * 3 + 0.5)}</b>
      <Btn size="sm" icon="plus" onClick={() => onChange({ height: Math.min(300, (h.height > 0 ? h.height : h.floors * 3 + 0.5) + 3) })} />
      {h.height > 0 ? <Btn size="sm" onClick={() => onChange({ height: 0 })}>По этажам</Btn> : null}</div>
  </div>;
}
