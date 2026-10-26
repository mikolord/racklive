"""The picture under the «План» and the outlines of houses: file checks, numbers clamped, the whole way through a real server (demo copy).
Run: python tools/planmap_test.py   (prints ВСЁ OK)"""
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
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40
WEBP = b'RIFF\x00\x00\x00\x00WEBPVP8 ' + b'\x00' * 20

# --- the file
check('jpg, png и webp узнаются по первым байтам', planmap.kind_of(JPG) == 'jpg' and planmap.kind_of(PNG) == 'png' and planmap.kind_of(WEBP) == 'webp')
check('html и svg под видом картинки отклоняются', planmap.kind_of(b'<html><script>alert(1)</script></html>') is None and planmap.kind_of(b'<svg onload=alert(1)></svg>') is None)
tmp = tempfile.mkdtemp()
ext, err = planmap.save(tmp, JPG)
check('картинка сохраняется одним файлом', ext == 'jpg' and not err and os.path.isfile(os.path.join(tmp, 'plan', 'bg.jpg')))
ext, err = planmap.save(tmp, PNG)
check('новая картинка заменяет старую (остаётся один файл)', ext == 'png' and sorted(os.listdir(os.path.join(tmp, 'plan'))) == ['bg.png'])
check('слишком большая и пустая отклоняются', planmap.save(tmp, JPG + b'0' * 3_000_000)[0] is None and planmap.save(tmp, b'')[0] is None and planmap.save(tmp, b'GIF89a')[0] is None)
check('файл на месте после отказов', planmap.path_of(tmp).endswith('bg.png'))
planmap.remove(tmp)
check('удаление убирает файл', planmap.path_of(tmp) is None)
shutil.rmtree(tmp, ignore_errors=True)

# --- the record
ok = planmap.make_bg({'x': '10', 'y': -20, 'w': 3500, 'h': 3500, 'op': .8, 'attr': 'Imagery © Esri', 'lat': '55.75', 'lon': 37.6, 'z': 18}, 'jpg')
check('запись фона из данных браузера', ok and ok['ext'] == 'jpg' and ok['w'] == 3500 and ok['op'] == .8 and ok['lat'] == 55.75 and ok['z'] == 18 and ok['v'] > 1_700_000_000)
check('без размера или с мусором — отказ', planmap.make_bg({'x': 0, 'y': 0}, 'jpg') is None and planmap.make_bg({'x': 'abc', 'y': 0, 'w': 100, 'h': 100}, 'jpg') is None
      and planmap.make_bg({'x': float('nan'), 'y': 0, 'w': 100, 'h': 100}, 'jpg') is None and planmap.make_bg({'x': True, 'y': 0, 'w': 100, 'h': 100}, 'jpg') is None)
check('числа зажаты в разумные пределы', planmap.make_bg({'x': 9e9, 'y': 0, 'w': 1e12, 'h': 1, 'op': 5}, 'jpg')['w'] == planmap.LIMIT)
check('подпись обрезается', len(planmap.make_bg({'x': 0, 'y': 0, 'w': 100, 'h': 100, 'attr': 'я' * 500}, 'jpg')['attr']) == 120)
old = dict(ok)
mv = planmap.clean_bg({'x': 55, 'op': .4, 'ext': 'exe', 'v': 1, 'attr': 'чужое', 'w': 'abc'}, old)
check('двигать и менять прозрачность можно, подменить файл и версию нельзя', mv['x'] == 55 and mv['op'] == .4 and mv['ext'] == 'jpg' and mv['v'] == old['v'] and mv['attr'] == old['attr'] and mv['w'] == 3500)
check('без фона на сервере записи нет', planmap.clean_bg({'x': 1}, None) is None and planmap.clean_bg({'x': 1}, {}) is None)

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
    plan0 = st.get('plan') or {}
    check('в начале фона нет', 'bg' not in plan0)
    q = urllib.parse.urlencode({'x': 100, 'y': 50, 'w': 3500, 'h': 3500, 'op': .8, 'attr': 'Imagery © Esri, Maxar', 'lat': 55.75, 'lon': 37.6, 'z': 18})
    c, h, r = call('/api/plan/bg?' + q, 'POST', JPG, {'Content-Type': 'image/jpeg'})
    check('фон загружается', c == 200 and r.get('ok') and r['plan']['bg']['ext'] == 'jpg' and r['plan']['bg']['w'] == 3500)
    c, h, b = call('/api/plan/bg', raw=True)
    check('фон отдаётся как есть', c == 200 and b == JPG and h.get('Content-Type') == 'image/jpeg')
    check('и браузер держит его год', 'max-age=31536000' in h.get('Cache-Control', '') and 'immutable' in h.get('Cache-Control', '') and h.get('X-Content-Type-Options') == 'nosniff')
    plan = call('/api/state')[2]['plan']
    check('фон виден всем в состоянии плана', plan['bg']['ext'] == 'jpg' and plan['bg']['attr'].startswith('Imagery') and plan['bg']['v'] > 0)
    c, h, r = call('/api/plan/bg?' + q, 'POST', '<html>не картинка</html>'.encode(), {'Content-Type': 'image/jpeg'})
    check('не картинка отклоняется, прежний фон на месте', not (c == 200 and r.get('ok')) and call('/api/plan/bg', raw=True)[2] == JPG)
    c, h, r = call('/api/plan/bg?x=0&y=0', 'POST', JPG, {'Content-Type': 'image/jpeg'})
    check('без размера отказ', not (c == 200 and r.get('ok')))
    # the plan is saved by the browser: it may move the picture, but not replace it
    v_before = plan['bg']['v']
    plan['bg'].update({'x': 300, 'op': .5, 'ext': 'exe', 'v': 1})
    plan['buildings'] = [{'id': 'b1', 'name': 'Дом', 'x': 0, 'y': 0, 'floors': [], 'outline': sq}, {'id': 'b2', 'name': 'Плохой', 'floors': [], 'outline': [[0, 0], [1, 1]]}]
    c, h, r = put_plan(plan)
    after = call('/api/state')[2]['plan']
    check('план сохраняется, фон двигается', c == 200 and after['bg']['x'] == 300 and after['bg']['op'] == .5)
    check('но файл и версию подменить нельзя', after['bg']['ext'] == 'jpg' and after['bg']['v'] == v_before)
    bd = {b['id']: b for b in after['buildings']}
    check('контур дома сохраняется, негодный выбрасывается', bd['b1']['outline'] == sq and 'outline' not in bd['b2'])
    c, h, r = call('/api/plan/bg', 'DELETE')
    check('фон удаляется', c == 200 and 'bg' not in r['plan'] and call('/api/plan/bg', raw=True)[0] == 404)
    plan['bg'] = {'x': 1, 'y': 1, 'w': 500, 'h': 500, 'ext': 'jpg', 'v': 5}
    put_plan(plan)
    check('после удаления фон не воскресает из старой вкладки', 'bg' not in call('/api/state')[2]['plan'])
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
