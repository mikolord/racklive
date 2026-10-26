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
