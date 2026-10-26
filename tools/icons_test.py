"""Icons of devices: file checks, the library, the choice per node, and the whole way through a real server (demo copy).
Run: python tools/icons_test.py   (prints ВСЁ OK)"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import icons  # noqa: E402

bad = []


def check(name, ok):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        bad.append(name)


GOOD_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z" fill="none" stroke="#000"/></svg>'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40

# --- file checks
check('svg проходит', icons.kind_of(GOOD_SVG) == 'svg' and not icons.check_svg(GOOD_SVG))
check('png и webp узнаются по первым байтам', icons.kind_of(PNG) == 'png' and icons.kind_of(b'RIFF\x00\x00\x00\x00WEBPVP8 ') == 'webp')
check('html под видом картинки отклоняется', icons.kind_of(b'<html><script>alert(1)</script></html>') is None)
for label, evil in [('script', b'<svg><script>alert(1)</script></svg>'), ('onload', b'<svg onload="alert(1)"></svg>'), ('foreignObject', b'<svg><foreignObject></foreignObject></svg>'),
                    ('внешняя ссылка', b'<svg><image href="http://evil.example/x.png"/></svg>'), ('xlink', b'<svg><use xlink:href="https://evil.example/a.svg#b"/></svg>'),
                    ('javascript:', b'<svg><a href="javascript:alert(1)"/></svg>'), ('url()', b'<svg><rect fill="url(http://evil.example/x)"/></svg>'), ('entity', b'<!DOCTYPE svg [<!ENTITY x "y">]><svg/>')]:
    check('svg с %s отклоняется' % label, bool(icons.check_svg(evil)) or icons.kind_of(evil) is None)
check('ссылка на фрагмент (#id) допустима', not icons.check_svg(b'<svg><defs><g id="a"/></defs><use href="#a"/></svg>'))

# --- library + choice
tmp = tempfile.mkdtemp()
cfg = {}
e, err = icons.add(cfg, tmp, 'мой.svg', GOOD_SVG)
check('иконка добавляется, имя без расширения', e and e['name'] == 'мой' and os.path.isfile(os.path.join(tmp, 'icons', e['id'] + '.svg')))
check('слишком большой файл отклоняется', icons.add(cfg, tmp, 'x', b'x' * 200000)[0] is None)
check('выбор чужого id отклоняется', icons.choose(cfg, 'd:abc', 'up:00000000') != '')
check('выбор своей иконки', icons.choose(cfg, 'd:abc', 'up:' + e['id']) == '' and cfg['icons']['d:abc'] == 'up:' + e['id'])
check('выбор из набора', icons.choose(cfg, 'h:aa:bb', 'std:fridge') == '' and cfg['icons']['h:aa:bb'] == 'std:fridge')
check('мусор вместо иконки отклоняется', icons.choose(cfg, 'd:abc', '../../etc') != '' and icons.choose(cfg, 'd:abc', 'std:../x') != '' and icons.choose(cfg, '../x', 'std:fan') != '')
check('удаление из библиотеки снимает выбор', icons.remove(cfg, tmp, e['id']) and 'd:abc' not in cfg['icons'] and cfg['icons']['h:aa:bb'] == 'std:fridge' and not os.listdir(os.path.join(tmp, 'icons')))
check('пустое значение возвращает обычную', icons.choose(cfg, 'h:aa:bb', '') == '' and 'h:aa:bb' not in cfg['icons'])
shutil.rmtree(tmp, ignore_errors=True)

# --- through a real server (demo copy: no sign-in)
port = 9979
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


try:
    for _ in range(40):
        try:
            call('/api/state'); break
        except Exception:
            time.sleep(.5)
    s, _, j = call('/api/icons', 'POST', GOOD_SVG, {'X-Icon-Name': urllib.parse.quote('Мой роутер.svg')})
    check('сервер: загрузка svg', s == 200 and j.get('ok') and j['icon']['name'] == 'Мой роутер')
    iid = j['icon']['id']
    s, h, b = call('/api/icons/file/' + iid, raw=True)
    check('сервер: файл отдаётся с песочницей и типом svg', s == 200 and b == GOOD_SVG and h.get('Content-Type') == 'image/svg+xml' and 'sandbox' in h.get('Content-Security-Policy', ''))
    s, _, j = call('/api/icons', 'POST', b'<svg><script>1</script></svg>', {'X-Icon-Name': 'x'})
    check('сервер: svg со скриптом не принят', not j.get('ok'))
    st = call('/api/state')[2]
    node = next(n['id'] for n in st['topology']['nodes'] if n['id'].startswith('d:'))
    cli = next((n['id'] for n in st['topology']['nodes'] if n['id'].startswith('h:')), None)
    s, _, j = call('/api/icons/set', 'PUT', json.dumps({'key': node, 'icon': 'up:' + iid}).encode(), {'Content-Type': 'application/json'})
    check('сервер: выбор иконки для устройства', s == 200 and j['icons'].get(node) == 'up:' + iid)
    if cli:
        s, _, j = call('/api/icons/set', 'PUT', json.dumps({'key': cli, 'icon': 'std:fridge'}).encode(), {'Content-Type': 'application/json'})
        check('сервер: выбор иконки для клиента (телефон, камера…)', s == 200 and j['icons'].get(cli) == 'std:fridge')
    st = call('/api/state')[2]
    check('сервер: выбор и библиотека есть в состоянии', st['icons'].get(node) == 'up:' + iid and any(x['id'] == iid for x in st['iconLib']))
    s, _, j = call('/api/icons/' + iid, 'DELETE')
    st = call('/api/state')[2]
    check('сервер: удаление снимает выбор', s == 200 and node not in st['icons'] and not st['iconLib'] and call('/api/icons/file/' + iid, raw=True)[0] == 404)
    s, _, j = call('/api/icons', 'POST', b'', {'X-Icon-Name': 'x'})
    check('сервер: пустой файл не принят', not j.get('ok'))
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
    shutil.rmtree(data, ignore_errors=True)

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
