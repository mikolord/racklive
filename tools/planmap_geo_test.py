"""«План»: geometry of the house outlines and the scale of a map snapshot — the very functions of web/src/46_planbg.jsx, run in Node.
Run: python tools/planmap_geo_test.py   (prints ВСЁ OK; skipped without Node)"""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
node = shutil.which('node')
if not node:
    print('нет Node — проверка геометрии пропущена\n\nВСЁ OK')
    sys.exit(0)
src = open(os.path.join(ROOT, 'web', 'src', '46_planbg.jsx'), encoding='utf-8').read()
geo = src[src.index('const PPM'):src.index('/* ----- снимок')]            # constants + geometry (no JSX, no browser)
js = geo + r'''
const out = [];
const t = (name, ok, extra) => out.push([name, !!ok, extra === undefined ? '' : String(extra)]);
const near = (a, b, e = 1e-6) => Math.abs(a - b) <= e;
const sq = [[0, 0], [100, 0], [100, 80], [0, 80]];
const L = [[0, 0], [100, 0], [100, 40], [40, 40], [40, 100], [0, 100]];           // an L-shaped house
t('площадь прямоугольника', near(polyArea(sq), 8000));
t('площадь Г-образного дома', near(polyArea(L), 100 * 40 + 40 * 60), polyArea(L));
t('площадь не зависит от направления обхода', near(polyArea(sq.slice().reverse()), 8000));
t('площадь в метрах: 12×10 м = 120 м²', near(polyArea([[0, 0], [120, 0], [120, 100], [0, 100]]) / (PPM * PPM), 120));
t('центр прямоугольника', near(polyCenter(sq).x, 50) && near(polyCenter(sq).y, 40));
const cl = polyCenter(L);
t('центр Г-образного — внутри дома', inPoly(cl, L), JSON.stringify(cl));
t('вырожденный контур: середина рамки, без NaN', (c => isFinite(c.x) && isFinite(c.y) && near(c.x, 50))(polyCenter([[0, 0], [100, 0], [50, 0]])));
t('рамка', JSON.stringify(polyBox(L)) === JSON.stringify({ x0: 0, y0: 0, x1: 100, y1: 100 }));
t('внутри / снаружи прямоугольника', inPoly({ x: 50, y: 40 }, sq) && !inPoly({ x: 150, y: 40 }, sq) && !inPoly({ x: 50, y: -1 }, sq));
t('вырез Г-образного: внутри угла — снаружи', !inPoly({ x: 70, y: 70 }, L) && inPoly({ x: 20, y: 70 }, L) && inPoly({ x: 70, y: 20 }, L));
t('привязка угла к метру', snapO(14) === 10 && snapO(16) === 20 && snapO(-4) === 0 && snapO(-6) === -10);
// the scale of a map snapshot (Web Mercator, 256 px tiles)
t('метров на пиксель на экваторе, зум 0', near(mPerPx(0, 0), 156543.03392, 1e-3));
t('каждый зум вдвое подробнее', near(mPerPx(55, 18) * 2, mPerPx(55, 17), 1e-9));
t('на широте 60° пиксель вдвое короче', near(mPerPx(60, 10) * 2, mPerPx(0, 10), 1e-3));
const o = mercatorPx(0, 0, 1), m = mercatorPx(55.7558, 37.6173, 10);
t('центр карты: (0,0) на зуме 1 — это (256,256)', near(o.x, 256) && near(o.y, 256, 1e-6));
t('Москва: плитка 10-го зума 619/320', Math.floor(m.x / 256) === 619 && Math.floor(m.y / 256) === 320, `${Math.floor(m.x / 256)}/${Math.floor(m.y / 256)}`);
t('север выше: чем севернее, тем меньше y', mercatorPx(56, 37, 12).y < mercatorPx(55, 37, 12).y);
const mp = mPerPx(55.75, 18), side = 1024 * mp;
t('снимок 1024 px на зуме 18 у Москвы ≈ 350 м', side > 340 && side < 360, side);
t('в единицах плана это ≈ 3500 (10 единиц = 1 м)', near(side * PPM, 3500, 120), side * PPM);
// radius → zoom and size of the snapshot
const lat0 = 55.7558, lon0 = 37.6173;
let prevZ = 99, sizesOk = true, mono = true;
for (const R of [50, 100, 300, 500, 1000, 2000, 5000, 10000, 20000]) { const p = snapPlan(lat0, R);
  if (p.S > MAX_SIDE || p.S < 256) sizesOk = false; if (p.z > prevZ) mono = false; prevZ = p.z; }
t('для любого радиуса 50 м…20 км снимок от 256 до 2048 точек', sizesOk);
t('чем больше радиус, тем дальше зум (не ближе)', mono);
t('радиус 100 м: самый подробный зум 19', snapPlan(lat0, 100).z === 19, JSON.stringify(snapPlan(lat0, 100)));
t('радиус 10 км: зум 12–13, снимок почти во весь предел', (p => p.z >= 12 && p.z <= 13 && p.S > 1000)(snapPlan(lat0, 10000)), JSON.stringify(snapPlan(lat0, 10000)));
t('радиус 20 км помещается', snapPlan(lat0, 20000).S <= 2048 && snapPlan(lat0, 20000).z >= 11);
t('снимок реально покрывает диаметр (метров на точку × размер ≥ 2R)', [100, 500, 5000, 20000].every(R => { const p = snapPlan(lat0, R); return p.S * mPerPx(lat0, p.z) >= 2 * R * 0.999; }));
// the overview and a detailed snapshot lie exactly over each other (same coefficient for the whole plan)
const ov = snapPlace(lat0, lon0, snapPlan(lat0, 10000).S, snapPlan(lat0, 10000).z, null, { x: 0, y: 0 });
t('первый снимок центрируется на заданной точке', Math.abs(ov.x + ov.w / 2) <= 1 && Math.abs(ov.y + ov.h / 2) <= 1, JSON.stringify(ov));
t('его размер в единицах плана = диаметр в метрах × 10', (d => Math.abs(d - 20000 * PPM) / (20000 * PPM) < 0.05)(ov.w), ov.w);
const refBg = { x: ov.x, y: ov.y, w: ov.w, h: ov.h, lat: lat0, lon: lon0 };
const kk = Math.cos(lat0 * Math.PI / 180), m0 = mercM(lat0, lon0);
const east = 500, north = 300;                                                       // метров на местности
const g = fromMercM(m0.x + east / kk, m0.y + north / kk);
const sp = snapPlan(g.lat, 300), dt = snapPlace(g.lat, g.lon, sp.S, sp.z, refBg, null);
const dc = { x: dt.x + dt.w / 2, y: dt.y + dt.h / 2 };
t('подробный фон ложится на 500 м восточнее и 300 м севернее центра обзора', Math.abs(dc.x - east * PPM) <= 3 && Math.abs(dc.y + north * PPM) <= 3, JSON.stringify(dc));
t('его размер совпадает с масштабом обзора (метров на точку)', Math.abs(dt.w / sp.S - (ov.w / snapPlan(lat0, 10000).S) * (156543.03392 / 2 ** sp.z) / (156543.03392 / 2 ** snapPlan(lat0, 10000).z)) < 0.05, dt.w / sp.S);
const back = worldToGeo(dc.x, dc.y, refBg);
t('обратный перевод: точка плана → широта и долгота', Math.abs(back.lat - g.lat) < 1e-5 && Math.abs(back.lon - g.lon) < 1e-5, JSON.stringify(back));
t('обратный перевод центра обзора', (b => Math.abs(b.lat - lat0) < 1e-6 && Math.abs(b.lon - lon0) < 1e-6)(worldToGeo(ov.x + ov.w / 2, ov.y + ov.h / 2, refBg)));
t('север — вверх: меньший y на плане = больше широта', worldToGeo(0, -1000, refBg).lat > worldToGeo(0, 1000, refBg).lat);
t('перевод туда и обратно (план → земля → план) совпадает', (w => Math.abs(w.x - 1234) < 1e-3 && Math.abs(w.y + 567) < 1e-3)((g => geoToWorld(g.lat, g.lon, refBg))(worldToGeo(1234, -567, refBg))));
t('место без фона (plan.geo): точка плана (0, 0) лежит на этих координатах', (g => Math.abs(g.lat - 55.7558) < 1e-6 && Math.abs(g.lon - 37.6173) < 1e-6)(worldToGeo(0, 0, geoRef([], { lat: 55.7558, lon: 37.6173 }))));
t('фон с координатами главнее выбранного места', geoRef([{ w: 100, lat: 1, lon: 2 }], { lat: 9, lon: 9 }).lat === 1 && geoRef([], {}) === null);
t('образец — самый большой фон с координатами, свой файл не считается', geoRef([{ w: 100, lat: 1, lon: 2 }, { w: 900, lat: 3, lon: 4 }, { w: 5000 }]).lat === 3 && geoRef([{ w: 5 }]) === null && geoRef([]) === null);
t('подписи расстояний', kmText(300) === '300 м' && kmText(1500) === '1.5 км' && kmText(20000) === '20 км' && kmText(999) === '999 м');
console.log(JSON.stringify(out));
'''
tmp = os.path.join(tempfile.mkdtemp(), 'geo.js')
open(tmp, 'w', encoding='utf-8').write(js)
r = subprocess.run([node, tmp], capture_output=True, text=True, encoding='utf-8', timeout=60)
bad = []
if r.returncode:
    print('Node упал:', r.stderr[:500]); bad.append('node')
else:
    for name, ok, extra in json.loads(r.stdout.strip().splitlines()[-1]):
        print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + extra))
        if not ok:
            bad.append(name)
shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
sys.exit(1 if bad else 0)
