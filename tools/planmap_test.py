"""The pictures under the «План» and the outlines of houses: file checks, numbers clamped, several pictures, the move from the single picture of 2.28.0,
the whole way through a real server (demo copy). Run: python tools/planmap_test.py   (prints ВСЁ OK)"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import planmap  # noqa: E402

bad = []


def check(name, ok):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        bad.append(name)


JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 200
JPG2 = b'\xff\xd8\xff\xe1' + b'\x01' * 300
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40
WEBP = b'RIFF\x00\x00\x00\x00WEBPVP8 ' + b'\x00' * 20

# --- the file
check('jpg, png и webp узнаются по первым байтам', planmap.kind_of(JPG) == 'jpg' and planmap.kind_of(PNG) == 'png' and planmap.kind_of(WEBP) == 'webp')
check('html и svg под видом картинки отклоняются', planmap.kind_of(b'<html><script>alert(1)</script></html>') is None and planmap.kind_of(b'<svg onload=alert(1)></svg>') is None)
tmp = tempfile.mkdtemp()
ext, err = planmap.save(tmp, 'g1a2b3', JPG)
check('картинка сохраняется одним файлом с номером', ext == 'jpg' and not err and os.path.isfile(os.path.join(tmp, 'plan', 'bg-g1a2b3.jpg')))
planmap.save(tmp, 'g4c5d6', JPG2)
check('вторая картинка лежит рядом, первая цела', sorted(os.listdir(os.path.join(tmp, 'plan'))) == ['bg-g1a2b3.jpg', 'bg-g4c5d6.jpg'])
ext, err = planmap.save(tmp, 'g1a2b3', PNG)
check('замена по тому же номеру оставляет один файл', ext == 'png' and sorted(os.listdir(os.path.join(tmp, 'plan'))) == ['bg-g1a2b3.png', 'bg-g4c5d6.jpg'])
check('слишком большая, пустая и чужой формат отклоняются', planmap.save(tmp, 'g1a2b3', JPG + b'0' * 3_000_000)[0] is None and planmap.save(tmp, 'g1a2b3', b'')[0] is None and planmap.save(tmp, 'g1a2b3', b'GIF89a')[0] is None)
check('номер из путей и странных знаков не принимается', planmap.save(tmp, '../x', JPG)[0] is None and planmap.save(tmp, 'a/b', JPG)[0] is None and planmap.path_of(tmp, '../../etc') is None and planmap.save(tmp, 'AB', JPG)[0] is None)
check('файл найден по номеру', planmap.path_of(tmp, 'g4c5d6').endswith('bg-g4c5d6.jpg') and planmap.path_of(tmp, 'nope00') is None)
planmap.remove(tmp, 'g4c5d6')
check('удаление убирает только свой файл', planmap.path_of(tmp, 'g4c5d6') is None and planmap.path_of(tmp, 'g1a2b3') is not None)
shutil.rmtree(tmp, ignore_errors=True)

# --- the record
meta = {'x': '10', 'y': -20, 'w': 3500, 'h': 3500, 'op': .8, 'attr': 'Imagery © Esri', 'lat': '55.75', 'lon': 37.6, 'z': 18, 'r': 300, 'name': '  Участок   ближе '}
ok = planmap.make_bg(meta, 'jpg', 'g1a2b3')
check('запись фона из данных браузера', ok and ok['id'] == 'g1a2b3' and ok['ext'] == 'jpg' and ok['w'] == 3500 and ok['op'] == .8 and ok['lat'] == 55.75 and ok['z'] == 18 and ok['r'] == 300 and ok['v'] > 1_700_000_000)
check('название приводится в порядок', ok['name'] == 'Участок ближе')
check('без размера или с мусором — отказ', planmap.make_bg({'x': 0, 'y': 0}, 'jpg', 'g1a2b3') is None and planmap.make_bg({'x': 'abc', 'y': 0, 'w': 100, 'h': 100}, 'jpg', 'g1a2b3') is None
      and planmap.make_bg({'x': float('nan'), 'y': 0, 'w': 100, 'h': 100}, 'jpg', 'g1a2b3') is None and planmap.make_bg({'x': True, 'y': 0, 'w': 100, 'h': 100}, 'jpg', 'g1a2b3') is None)
check('числа зажаты в разумные пределы', planmap.make_bg({'x': 9e9, 'y': 0, 'w': 1e12, 'h': 1, 'op': 5}, 'jpg', 'g1a2b3')['w'] == planmap.LIMIT)
check('большой обзор на 20 км (200 000 единиц) помещается', planmap.make_bg({'x': -100000, 'y': -100000, 'w': 200000, 'h': 200000}, 'jpg', 'g1a2b3')['w'] == 200000)
check('подпись обрезается', len(planmap.make_bg({'x': 0, 'y': 0, 'w': 100, 'h': 100, 'attr': 'я' * 500}, 'jpg', 'g1a2b3')['attr']) == 120)

# --- what the browser may change
a = planmap.make_bg(dict(meta, name='Обзор'), 'jpg', 'g1a2b3'); b = planmap.make_bg(dict(meta, name='Двор'), 'png', 'g4c5d6')
mv = planmap.clean_bgs([{'id': 'g1a2b3', 'x': 55, 'op': .4, 'ext': 'exe', 'v': 1, 'attr': 'чужое', 'w': 'abc', 'name': ' Новое  имя '}, {'id': 'gnew000', 'ext': 'jpg', 'x': 1, 'y': 1, 'w': 500, 'h': 500}], [a, b])
check('двигать, менять яркость и имя можно', mv[0]['x'] == 55 and mv[0]['op'] == .4 and mv[0]['name'] == 'Новое имя' and mv[0]['w'] == 3500)
check('подменить файл, версию, подпись нельзя', mv[0]['ext'] == 'jpg' and mv[0]['v'] == a['v'] and mv[0]['attr'] == a['attr'])
check('чужой номер из браузера не добавляет фон', [x['id'] for x in mv] == ['g1a2b3', 'g4c5d6'])
check('фон, которого нет в присланном, не пропадает', len(planmap.clean_bgs([], [a, b])) == 2 and len(planmap.clean_bgs(None, [a, b])) == 2)
check('без фонов на сервере записей нет', planmap.clean_bgs([{'id': 'g1a2b3', 'x': 1}], None) == [] and planmap.clean_bgs([{'id': 'g1a2b3'}], [{'id': '../x', 'ext': 'jpg'}, {'id': 'g1a2b3', 'ext': 'exe'}]) == [])

# --- the move from the single picture of 2.28.0
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'plan'))
open(os.path.join(tmp, 'plan', 'bg.jpg'), 'wb').write(JPG)
cfg = {'plan': {'buildings': [{'id': 'b1'}], 'links': [], 'poles': [], 'bg': {'v': 1793035524, 'ext': 'jpg', 'x': -2221.0, 'y': -2993.0, 'w': 4442.0, 'h': 4442.0, 'op': 0.5, 'attr': 'Снимок: Esri', 'lat': 55.755826, 'lon': 37.617299, 'z': 18}}}
check('старый фон переносится в список', planmap.migrate(cfg, tmp) is True and 'bg' not in cfg['plan'] and len(cfg['plan']['bgs']) == 1)
e = cfg['plan']['bgs'][0]
check('все его данные целы (место, яркость, координаты)', e['x'] == -2221.0 and e['w'] == 4442.0 and e['op'] == .5 and e['lat'] == 55.755826 and e['lon'] == 37.617299 and e['z'] == 18 and e['name'] == 'Фон')
check('файл переименован под новый номер', planmap.path_of(tmp, e['id']) is not None and not os.path.exists(os.path.join(tmp, 'plan', 'bg.jpg')) and open(planmap.path_of(tmp, e['id']), 'rb').read() == JPG)
check('второй раз ничего не меняется', planmap.migrate(cfg, tmp) is False and len(cfg['plan']['bgs']) == 1)
check('дома не тронуты', cfg['plan']['buildings'] == [{'id': 'b1'}])
cfg2 = {'plan': {'buildings': [], 'bg': {'v': 1, 'ext': 'jpg', 'x': 0, 'y': 0, 'w': 100, 'h': 100}}}
shutil.rmtree(os.path.join(tmp, 'plan'))
check('запись без файла не плодит пустых фонов', planmap.migrate(cfg2, tmp) is True and 'bg' not in cfg2['plan'] and not cfg2['plan'].get('bgs'))
check('без плана и без фона — ничего', planmap.migrate({}, tmp) is False and planmap.migrate({'plan': {'buildings': []}}, tmp) is False)
shutil.rmtree(tmp, ignore_errors=True)

# --- outlines
sq = [[0, 0], [100, 0], [100, 80], [0, 80]]
check('контур принимается', planmap.clean_outline(sq) == sq)
check('меньше трёх точек, мусор, слишком много — отказ', planmap.clean_outline(sq[:2]) is None and planmap.clean_outline('abc') is None and planmap.clean_outline([[0, 0], [1, 'x'], [2, 2]]) is None
      and planmap.clean_outline([[0, 0, 0], [1, 1], [2, 2]]) is None and planmap.clean_outline([[i, i] for i in range(121)]) is None)
bs = planmap.clean_buildings([{'id': 'a', 'outline': sq, 'floors': []}, {'id': 'b', 'outline': [[0, 0]], 'floors': []}, {'id': 'c', 'floors': []}, 'мусор'])
check('в домах остаются только годные контуры', bs[0]['outline'] == sq and 'outline' not in bs[1] and bs[1]['id'] == 'b' and 'outline' not in bs[2] and bs[3] == 'мусор')

# --- through a real server (demo copy: no sign-in)
port = 9978
data = tempfile.mkdtemp()
# a config from 2.28.0: the single picture is already there, the server must carry it over at start
os.makedirs(os.path.join(data, 'plan'))
open(os.path.join(data, 'plan', 'bg.png'), 'wb').write(PNG)
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = 'http://127.0.0.1:%d' % port


def call(path, method='GET', body=None, headers=None, raw=False):
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read()
            return r.status, dict(r.headers), (b if raw else json.loads(b or b'{}'))
    except urllib.error.HTTPError as ex:
        b = ex.read()
        try:
            return ex.code, dict(ex.headers), (b if raw else json.loads(b or b'{}'))
        except ValueError:
            return ex.code, dict(ex.headers), b


def put_plan(plan):
    return call('/api/plan', 'PUT', json.dumps(plan).encode(), {'Content-Type': 'application/json'})


try:
    for _ in range(40):
        try:
            call('/api/state'); break
        except Exception:
            time.sleep(.5)
    st = call('/api/state')[2]
    check('в начале фонов нет', not (st.get('plan') or {}).get('bgs') and 'bg' not in (st.get('plan') or {}))
    p0 = dict(st.get('plan') or {'buildings': [], 'links': [], 'poles': []})
    put_plan(dict(p0, geo={'lat': 55.7558, 'lon': 37.6173}))
    check('выбранное на карте место (plan.geo) сохраняется', (call('/api/state')[2].get('plan') or {}).get('geo') == {'lat': 55.7558, 'lon': 37.6173})
    put_plan(dict(p0, geo={'lat': 'x', 'lon': 1}))
    check('неверное место не сохраняется', 'geo' not in (call('/api/state')[2].get('plan') or {}))
    put_plan(dict(p0, geo={'lat': 999, 'lon': 37.6173}))
    check('широта вне диапазона обрезается', (call('/api/state')[2].get('plan') or {}).get('geo') == {'lat': 85.0, 'lon': 37.6173})
    put_plan(p0)
    fl = [{'id': 'f1', 'name': '1 этаж', 'walls': [], 'rooms': [], 'items': []}]
    put_plan(dict(p0, buildings=[{'id': 'bc1', 'name': 'Цветной', 'floors': fl, 'color': '#FF8800', 'edge': 'red', 'hl': True, 'height': 999},
                                 {'id': 'bc2', 'name': 'Обычный', 'floors': fl, 'color': '', 'hl': 'yes', 'height': 0}]))
    got = {x['id']: x for x in (call('/api/state')[2].get('plan') or {}).get('buildings', [])}
    check('цвет дома: только #rrggbb (чужое отбрасывается), подсветка — только true', got['bc1'].get('color') == '#FF8800' and 'edge' not in got['bc1'] and got['bc1'].get('hl') is True
          and 'color' not in got['bc2'] and 'hl' not in got['bc2'])
    check('высота дома: не больше 300 м, ноль — «по этажам» (поля нет)', got['bc1'].get('height') == 300 and 'height' not in got['bc2'])
    put_plan(p0)
    put_plan(dict(p0, nodes=[{'id': 'nd1', 'name': 'Ввод', 'x': 100, 'y': 200, 'ref': {'kind': 'place', 'id': 'rack0'}}, {'id': 'nd2', 'name': 'Плохой', 'x': 'x', 'y': 1}, {'id': 'BAD ID', 'name': 'x', 'x': 1, 'y': 1},
                                {'id': 'nd3', 'name': 'Без привязки', 'x': 5, 'y': 6, 'ref': {'kind': 'hack', 'id': 'x'}}]))
    nd = {x['id']: x for x in (call('/api/state')[2].get('plan') or {}).get('nodes', [])}
    check('узлы плана: сохраняются, привязка к шкафу цела, мусор отбрасывается', set(nd) == {'nd1', 'nd3'} and nd['nd1'].get('ref') == {'kind': 'place', 'id': 'rack0'} and 'ref' not in nd['nd3'])
    put_plan(p0)
    check('узлы убираются вместе с планом без них', 'nodes' not in (call('/api/state')[2].get('plan') or {}))
    q = lambda **k: urllib.parse.urlencode(dict({'x': 100, 'y': 50, 'w': 3500, 'h': 3500, 'op': .8, 'attr': 'Imagery © Esri, Maxar', 'lat': 55.75, 'lon': 37.6, 'z': 18, 'r': 300, 'name': 'Двор'}, **k))
    c, h, r = call('/api/plan/bg?' + q(name='Обзор', w=60000, h=60000, x=-30000, y=-30000, z=14, r=3000), 'POST', JPG, {'Content-Type': 'image/jpeg'})
    id1 = r.get('id')
    check('первый (обзорный) фон загружается', c == 200 and r.get('ok') and id1 and len(r['plan']['bgs']) == 1 and r['plan']['bgs'][0]['w'] == 60000)
    c, h, r = call('/api/plan/bg?' + q(), 'POST', JPG2, {'Content-Type': 'image/jpeg'})
    id2 = r.get('id')
    check('второй (подробный) фон ложится рядом', c == 200 and id2 and id2 != id1 and [b['name'] for b in r['plan']['bgs']] == ['Обзор', 'Двор'])
    c, h, b = call('/api/plan/bg/' + id2, raw=True)
    check('каждый отдаётся своей картинкой', c == 200 and b == JPG2 and call('/api/plan/bg/' + id1, raw=True)[2] == JPG)
    check('и браузер держит их год', 'max-age=31536000' in h.get('Cache-Control', '') and 'immutable' in h.get('Cache-Control', '') and h.get('X-Content-Type-Options') == 'nosniff' and h.get('Content-Type') == 'image/jpeg')
    check('чужой номер — 404', call('/api/plan/bg/nope000', raw=True)[0] == 404 and call('/api/plan/bg/..%2f..%2fetc', raw=True)[0] in (400, 404))
    plan = call('/api/state')[2]['plan']
    check('фоны видны всем в состоянии плана', [b['id'] for b in plan['bgs']] == [id1, id2] and plan['bgs'][1]['attr'].startswith('Imagery') and plan['bgs'][1]['r'] == 300)
    c, h, r = call('/api/plan/bg?' + q(), 'POST', '<html>не картинка</html>'.encode(), {'Content-Type': 'image/jpeg'})
    check('не картинка отклоняется, фонов столько же', not (c == 200 and r.get('ok')) and len(call('/api/state')[2]['plan']['bgs']) == 2)
    c, h, r = call('/api/plan/bg?x=0&y=0', 'POST', JPG, {'Content-Type': 'image/jpeg'})
    check('без размера отказ', not (c == 200 and r.get('ok')))
    ids = [id1, id2]
    for i in range(planmap.MAX_BGS - 2):
        c, h, r = call('/api/plan/bg?' + q(name=f'Ещё {i}'), 'POST', PNG, {'Content-Type': 'image/png'})
        ids.append(r.get('id'))
    c, h, r = call('/api/plan/bg?' + q(), 'POST', JPG, {'Content-Type': 'image/jpeg'})
    check('больше шести фонов не бывает', len(ids) == planmap.MAX_BGS and not (c == 200 and r.get('ok')) and len(call('/api/state')[2]['plan']['bgs']) == planmap.MAX_BGS)
    for i in ids[2:]:
        call('/api/plan/bg/' + i, 'DELETE')
    # the plan is saved by the browser: it may move and dim a picture, but not replace or add one
    plan = call('/api/state')[2]['plan']
    v_before = {b['id']: b['v'] for b in plan['bgs']}
    plan['bgs'][1].update({'x': 300, 'op': .5, 'ext': 'exe', 'v': 1, 'name': 'Мой двор'})
    plan['bgs'].append({'id': 'gevil01', 'ext': 'jpg', 'x': 0, 'y': 0, 'w': 100, 'h': 100})
    plan['buildings'] = [{'id': 'b1', 'name': 'Дом', 'x': 0, 'y': 0, 'floors': [], 'outline': sq}, {'id': 'b2', 'name': 'Плохой', 'floors': [], 'outline': [[0, 0], [1, 1]]}]
    c, h, r = put_plan(plan)
    after = call('/api/state')[2]['plan']
    bd = {b['id']: b for b in after['bgs']}
    check('план сохраняется, фон двигается и переименовывается', c == 200 and bd[id2]['x'] == 300 and bd[id2]['op'] == .5 and bd[id2]['name'] == 'Мой двор')
    check('но файл и версию подменить нельзя, чужой фон не добавить', bd[id2]['ext'] == 'jpg' and bd[id2]['v'] == v_before[id2] and 'gevil01' not in bd and len(bd) == 2)
    byb = {b['id']: b for b in after['buildings']}
    check('контур дома сохраняется, негодный выбрасывается', byb['b1']['outline'] == sq and 'outline' not in byb['b2'])
    plan['bgs'] = []                                         # an old tab that does not know about the pictures
    put_plan(plan)
    check('вкладка без фонов их не стирает', len(call('/api/state')[2]['plan']['bgs']) == 2)
    c, h, r = call('/api/plan/bg/' + id1, 'DELETE')
    check('один фон удаляется, второй остаётся', c == 200 and [b['id'] for b in r['plan']['bgs']] == [id2] and call('/api/plan/bg/' + id1, raw=True)[0] == 404 and call('/api/plan/bg/' + id2, raw=True)[0] == 200)
    plan = call('/api/state')[2]['plan']
    plan['bgs'].append({'id': id1, 'ext': 'jpg', 'x': 1, 'y': 1, 'w': 500, 'h': 500})
    put_plan(plan)
    check('удалённый фон не воскресает из старой вкладки', [b['id'] for b in call('/api/state')[2]['plan']['bgs']] == [id2])
    c, h, r = call('/api/plan/bg/' + id2, 'DELETE')
    check('последний удалён: поля фонов в плане нет', c == 200 and 'bgs' not in r['plan'] and 'bgs' not in call('/api/state')[2]['plan'])
    check('дома при этом целы', len(call('/api/state')[2]['plan']['buildings']) == 2)
finally:
    srv.terminate()
    try:
        srv.wait(timeout=10)
    except Exception:
        srv.kill()
    shutil.rmtree(data, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
sys.exit(1 if bad else 0)
