"""Мини-браузер Frank (rackd/frankbrowser.py): адреса, имена снимков, отсутствие браузера, работа с поддельным Chromium, чистка старых снимков,
и то, что инструмент и картинки появляются только когда они включены (через демо-сервер).
Настоящий Chromium проверяется на NAS (tools/frankbrowser_live.py) — здесь его может не быть.
Run: python tools/frankbrowser_test.py (prints ВСЁ OK)"""
import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import frankbrowser as B  # noqa: E402

bad = []
DATA = tempfile.mkdtemp(prefix='fbrowser-')


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)[:300]))
    if not ok:
        bad.append(name)


def raises(fn, part=''):
    try:
        fn()
    except Exception as e:
        return part in str(e)
    return False


# ── адреса ──
check('адрес без схемы получает http://', B.check_url('191.101.1.5:8080') == 'http://191.101.1.5:8080')
check('https сохраняется', B.check_url('https://example.com/x?y=1') == 'https://example.com/x?y=1')
check('пустой и мусор — отказ', raises(lambda: B.check_url(''), 'пустой') and raises(lambda: B.check_url('   '), 'пустой'))
check('file://, javascript:, data: запрещены',
      all(raises(lambda u=u: B.check_url(u), 'только http и https') for u in ('file:///etc/passwd', 'javascript:alert(1)', 'data:text/html,<b>x</b>', 'view-source:http://x')))
check('слишком длинный — отказ', raises(lambda: B.check_url('http://x/' + 'a' * 2500), 'длинный'))

# ── имена снимков ──
good = f'{int(time.time())}-0123abcd.png'
check('своё имя снимка принимается (файла нет — None)', B.shot_file(DATA, good) is None)
check('чужие имена и пути — отказ', all(raises(lambda n=n: B.shot_file(DATA, n)) for n in
      ('../../config.json', '/etc/passwd', 'shot.png', '0123abcd.png', f'{int(time.time())}-0123abcd.png/../x', '../' + good)))

# ── браузера нет ──
saved_force, B.FORCE = B.FORCE, None
saved_bin = B.BINARIES
B.BINARIES = ('нет-такого-браузера-в-мире',)
check('без Chromium — понятное объяснение, а не падение', B.binary() is None and raises(lambda: B.open_page(DATA, 'http://example.com'), 'нет браузера'))
B.BINARIES = saved_bin
B.FORCE = saved_force

# ── поддельный Chromium ──
fake = os.path.join(tempfile.mkdtemp(prefix='fbrowser-fake-'), 'fake_chromium.py')
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
with open(fake, 'w', encoding='utf-8') as f:
    f.write('''import sys
args = sys.argv[1:]
shot = [a.split("=", 1)[1] for a in args if a.startswith("--screenshot=")]
if shot:
    open(shot[0], "wb").write(base64_data + b"\\0" * 2000)
if "--dump-dom" in args:
    print("<html><head><title>Тестовая страница</title></head><body><h1>Привет</h1><p>Проверка мини-браузера</p>"
          "<script>var secret = 1;</script></body></html>")
'''.replace('base64_data', repr(PNG)))
B.FORCE = [sys.executable, fake]
try:
    res = B.open_page(DATA, 'example.com', size='S', wait=1000, timeout=60)
    shot_path = os.path.join(B.shots_dir(DATA), res['shot'])
    check('страница открывается: заголовок и текст прочитаны', res['ok'] and res['title'] == 'Тестовая страница' and 'Привет' in res['text'], res)
    check('скрипты в тексте не показываются', 'secret' not in res['text'])
    check('снимок сохранён и он наш', os.path.isfile(shot_path) and os.path.getsize(shot_path) > 1000 and B.shot_file(DATA, res['shot']) == shot_path)
    check('размер S — как с телефона', res['size'] == '390×844', res['size'])
    check('адрес без схемы открылся как http', res['url'] == 'http://example.com', res['url'])

    # старые снимки уходят: остаётся не больше SHOTS_KEEP
    d = B.shots_dir(DATA)
    for i in range(B.SHOTS_KEEP + 12):
        p = os.path.join(d, f'{1700000000 + i}-{i:08x}.png')
        open(p, 'wb').write(PNG)
        os.utime(p, (1700000000 + i, 1700000000 + i))
    B.prune(DATA)
    left = [f for f in os.listdir(d) if B.SHOT_NAME.match(f)]
    check('старые снимки удаляются (остаётся не больше лимита)', len(left) <= B.SHOTS_KEEP, len(left))

    # браузер не сделал снимок — понятная ошибка
    dead = os.path.join(tempfile.mkdtemp(prefix='fbrowser-dead-'), 'dead.py')
    with open(dead, 'w', encoding='utf-8') as f:
        f.write('import sys; print("ERR_CONNECTION_REFUSED", file=sys.stderr); sys.exit(1)\n')
    B.FORCE = [sys.executable, dead]
    check('если страница не открылась — ошибка с причиной', raises(lambda: B.open_page(DATA, 'http://nope.invalid'), 'скриншот не получился'))
finally:
    B.FORCE = saved_force
    shutil.rmtree(os.path.dirname(fake), ignore_errors=True)

# ── инструмент и картинки в живом демо-сервере ──
import http.server, threading, urllib.request, urllib.error  # noqa: E402

plan, results = {}, []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        msgs = body.get('messages') or []
        last = msgs[-1]
        if last['role'] == 'tool':
            results.append(last['content'])
            msg = {'role': 'assistant', 'content': 'Готово.'}
        else:
            q = last['content'] if isinstance(last['content'], str) else ''
            call = next((v for k, v in plan.items() if k in q), None)
            msg = ({'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'c1', 'type': 'function',
                                                                      'function': {'name': call[0], 'arguments': json.dumps(call[1], ensure_ascii=False)}}]}
                   if call else {'role': 'assistant', 'content': 'Ок.'})
        Fake.last_tools = [t['function']['name'] for t in body.get('tools') or []]
        out = json.dumps({'choices': [{'message': msg}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 5}}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(out)))
        self.end_headers(); self.wfile.write(out)


model = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=model.serve_forever, daemon=True).start()
srv_data = tempfile.mkdtemp(prefix='fbrowser-srv-')
port = 0
import socket  # noqa: E402
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=srv_data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port}'


def api(path, body=None, method=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method=method or ('POST' if body is not None else 'GET'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b'{}')
        except ValueError:
            return {'status': e.code}


def say(text):
    r = api('/api/ai/ask', {'chat': None, 'text': text})
    for _ in range(200):
        j = api('/api/ai/job', {'job': r['job']})
        if j.get('done'):
            return r['chat'], j
        time.sleep(.2)
    raise SystemExit('задача не завершилась')


try:
    for _ in range(40):
        try:
            api('/api/state')
            break
        except Exception:
            time.sleep(.5)
    api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': f'http://127.0.0.1:{model.server_address[1]}/v1', 'model': 'fake', 'key': 'k'}, 'PUT')
    say('Привет')
    check('без агента мини-браузера в инструментах нет', 'browse' not in Fake.last_tools, Fake.last_tools)
    api('/api/ai', {'agent': True, 'browser': True}, 'PUT')
    say('Привет ещё раз')
    check('с агентом и включённым браузером инструмент browse есть', 'browse' in Fake.last_tools, Fake.last_tools)
    api('/api/ai', {'browser': False}, 'PUT')
    say('И ещё раз')
    check('тумблер браузера выключает инструмент', 'browse' not in Fake.last_tools)
    api('/api/ai', {'browser': True}, 'PUT')
    st = api('/api/state')['ai']
    check('состояние знает про браузер', 'browserReady' in st and st['browser'] is True, {k: st.get(k) for k in ('browser', 'browserReady')})
    plan['ОТКРОЙ'] = ('browse', {'url': 'file:///etc/passwd'})
    say('ОТКРОЙ файл')
    check('запрещённый адрес объясняется модели', any('только http и https' in r for r in results), results[-2:])
    chk = api('/api/ai/shot/1700000000-deadbeef.png')
    check('чужой снимок не отдаётся', 'error' in chk or chk.get('status') in (400, 404), chk)
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
    model.shutdown()
    shutil.rmtree(srv_data, ignore_errors=True)
    shutil.rmtree(DATA, ignore_errors=True)

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
