/* «Живая карта (3D)»: спутник с наклоном и вращением, а на нём ВАШИ обведённые дома объёмными (высота — по числу этажей, цвет — по состоянию устройств внутри),
   магистрали и столбы. Открывается только по кнопке: библиотека MapLibre (1 МБ, ~270 КБ по сети, в кэше браузера на год) и плитки карты грузятся в этот момент,
   при закрытии карта целиком выгружается из памяти — обычный «План» остаётся лёгким. Положение домов на земле берётся из фонов с координатами (worldToGeo). */
const LIVE_VER = '5.24.0';
const LIVE_COLOR = { online: '#30d158', warning: '#ff9f0a', offline: '#ff453a', '': '#8e8e93' };
const LIVE_TILES = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
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

/* spec = { center: [lon, lat], houses: [{ id, name, ring: [[lon, lat]…], center: {lon, lat}, floors, devs, status }], poles: [{ id, name, lon, lat }], links: [{ coords: [[lon, lat], [lon, lat]] }] } */
function LiveMap3D({ spec, onClose, onOpen }) {
  const box = useRef(null); const mapRef = useRef(null);
  const [err, setErr] = useState(''); const [ready, setReady] = useState(false); const [sel, setSel] = useState(null); const [flat, setFlat] = useState(false);
  useEffect(() => {
    let dead = false, map = null; const marks = [];
    loadMapLibre().then(ml => {
      if (dead) return;
      try {
        map = new ml.Map({ container: box.current, center: spec.center, zoom: 17, pitch: 58, bearing: -25, maxPitch: 78, renderWorldCopies: false, fadeDuration: 0,
          style: { version: 8, sources: { sat: { type: 'raster', tiles: [LIVE_TILES], tileSize: 256, maxzoom: 19, attribution: ESRI_ATTR } }, layers: [{ id: 'sat', type: 'raster', source: 'sat' }] } });
      } catch (e) { setErr('Эта карта рисуется видеокартой (WebGL), а в вашем браузере она недоступна.'); return; }
      mapRef.current = map;
      map.addControl(new ml.NavigationControl({ visualizePitch: true }), 'top-right');
      map.on('error', e => { if (/WebGL|context/i.test(String((e && e.error && e.error.message) || e))) setErr('Эта карта рисуется видеокартой (WebGL), а в вашем браузере она недоступна.'); });
      map.on('load', () => {
        map.addSource('houses', { type: 'geojson', data: { type: 'FeatureCollection', features: spec.houses.map(h => ({ type: 'Feature', properties: { id: h.id, color: LIVE_COLOR[h.status] || LIVE_COLOR[''], h: h.floors * 3 + 0.5 },
          geometry: { type: 'Polygon', coordinates: [[...h.ring, h.ring[0]]] } })) } });
        map.addSource('links', { type: 'geojson', data: { type: 'FeatureCollection', features: spec.links.map(l => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: l.coords } })) } });
        map.addLayer({ id: 'links', type: 'line', source: 'links', paint: { 'line-color': '#0a84ff', 'line-width': 3, 'line-dasharray': [2, 1.5] } });
        map.addLayer({ id: 'houses-3d', type: 'fill-extrusion', source: 'houses', paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': .88 } });
        map.on('click', 'houses-3d', e => { const f = e.features && e.features[0]; if (f) setSel(f.properties.id); });
        map.on('mouseenter', 'houses-3d', () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', 'houses-3d', () => { map.getCanvas().style.cursor = ''; });
        spec.houses.forEach(h => { const el = document.createElement('div'); el.className = 'live-label'; el.textContent = h.name; el.onclick = () => setSel(h.id);
          marks.push(new ml.Marker({ element: el, anchor: 'bottom' }).setLngLat([h.center.lon, h.center.lat]).addTo(map)); });
        spec.poles.forEach(p => { const el = document.createElement('div'); el.className = 'live-pole'; el.title = p.name;
          marks.push(new ml.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map)); });
        const pts = spec.houses.flatMap(h => h.ring).concat(spec.poles.map(p => [p.lon, p.lat]));
        if (pts.length) { const b = new ml.LngLatBounds(pts[0], pts[0]); pts.forEach(p => b.extend(p)); map.fitBounds(b, { padding: 90, maxZoom: 19, pitch: 58, bearing: -25, duration: 0 }); }
        setReady(true);

      });
    }).catch(e => { if (!dead) setErr(e.message); });
    return () => { dead = true; marks.forEach(m => m.remove()); if (map) { try { map.remove(); } catch (e) { } } mapRef.current = null; };     // карта выгружается целиком
  }, []);
  const tilt = f => { setFlat(f); if (mapRef.current) mapRef.current.easeTo({ pitch: f ? 0 : 58, bearing: f ? 0 : -25, duration: 600 }); };
  const h = sel ? spec.houses.find(x => x.id === sel) : null;
  return <div className="live-overlay">
    <div className="live-head"><Icon name="map" size={18} /><b className="grow">Живая карта · 3D</b>
      <Btn size="sm" onClick={() => tilt(!flat)}>{flat ? 'Наклонить' : 'Вид сверху'}</Btn>
      <Btn size="sm" icon="x" onClick={onClose}>Закрыть</Btn></div>
    <div className="live-map" ref={box} data-ready={ready ? '1' : ''} data-layers={ready && mapRef.current ? ['houses-3d', 'links'].filter(i => mapRef.current.getLayer(i)).join(',') : ''}>
      {!ready && !err ? <div className="live-msg">Загружаю карту…</div> : null}
      {err ? <div className="live-msg err">{err}</div> : null}

      {ready && !spec.houses.length ? <div className="live-msg hint">Обведите дома на плане («Обвести дом») — они появятся здесь объёмными.</div> : null}
      {h ? <div className="live-card"><div className="grow" style={{ minWidth: 0 }}><b>{h.name}</b>
        <div className="dim3" style={{ fontSize: 12.5 }}>{h.floors} эт. · {h.devs} устр.</div></div>
        <Btn size="sm" kind="primary" icon="home" onClick={() => onOpen(h.id)}>Открыть</Btn><Btn size="sm" icon="x" onClick={() => setSel(null)} /></div> : null}
    </div>
  </div>;
}
