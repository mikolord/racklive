"""Локальные плагины через настоящий HTTP-сервер (демо-режим с RL_E2E): загрузка → просмотр кода → включение → маршрут → ui.js → выключение.
Run: python tools/localplug_http_test.py"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N, BAD = 0, []


def check(name, ok, extra=''):
    global N
    N += 1
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)[:300]))
    if not ok:
        BAD.append(name)


def main():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    tmp = tempfile.mkdtemp(prefix='rl-lph-')
    env = dict(os.environ, RL_DEMO='1', RL_E2E='1', RL_DATA=tmp, RL_PORT=str(port), PYTHONIOENCODING='utf-8')
    srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    B = f'http://127.0.0.1:{port}'

    def call(path, data=None, method=None, ctype='application/json'):
        if data is not None and not isinstance(data, bytes):
            data = json.dumps(data).encode()
        r = urllib.request.Request(B + path, data=data, method=method, headers={'Content-Type': ctype})
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                return x.status, x.read(), x.headers.get('Content-Type', '')
        except urllib.error.HTTPError as e:
            return e.code, e.read(), ''

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(B + '/api/state', timeout=5).read(); break
            except OSError:
                time.sleep(.3)
        else:
            raise SystemExit('сервер не запустился: ' + srv.stderr.read(2000).decode(errors='replace'))
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('plugin.json', json.dumps({'local_api': 1, 'id': 'hello-plug', 'title': 'Привет', 'description': 'Проверка', 'version': '1.0'}))
            z.writestr('main.py', "def register(api):\n    api.route('GET', 'hi', lambda req: {'hi': api.id, 'v': api.version})\n")
            z.writestr('ui.js', 'window.__hello = 1;')
        c, body, _ = call('/api/localplug')
        check('список пуст, предупреждение показано', c == 200 and json.loads(body)['plugins'] == [] and 'с теми же правами' in json.loads(body)['warning'])
        c, body, _ = call('/api/localplug/upload', b.getvalue(), ctype='application/zip')
        rep = json.loads(body)
        check('загрузка: принят и выключен', c == 200 and rep['ok'] and not rep['plugin']['live'], rep)
        dig = rep['plugin']['digest']
        c, body, _ = call('/api/x/hello-plug/hi')
        check('выключенный плагин: маршрута нет', c == 404)
        c, body, _ = call('/api/localplug/code?id=hello-plug&file=main.py')
        check('код можно посмотреть', c == 200 and 'def register' in json.loads(body)['text'])
        c, body, _ = call('/api/localplug/enable', {'id': 'hello-plug', 'digest': 'x' * 64})
        check('чужой отпечаток: отказ', c == 400, body)
        c, body, _ = call('/api/localplug/enable', {'id': 'hello-plug', 'digest': dig})
        check('включение с верным отпечатком', c == 200 and json.loads(body)['plugin']['live'], body)
        c, body, _ = call('/api/x/hello-plug/hi')
        check('маршрут плагина отвечает через сервер', c == 200 and json.loads(body)['hi'] == 'hello-plug', body)
        c, body, _ = call('/api/x/_scripts')
        check('ui.js в списке скриптов страницы', c == 200 and json.loads(body)['scripts'][0].startswith('/api/x/hello-plug/files/ui.js'), body)
        c, body, ct = call(json.loads(body)['scripts'][0])
        check('ui.js отдаётся как javascript', c == 200 and b'__hello' in body and 'javascript' in ct, (c, ct))
        c, body, ct = call('/api/x/hello-plug/files/main.py')
        check('.py отдаётся только как простой текст, не как страница', c == 200 and ct.startswith('text/plain'), ct)
        c, body, _ = call('/api/localplug/disable', {'id': 'hello-plug'})
        c2, _, _ = call('/api/x/hello-plug/hi')
        check('выключение: маршрут пропал', c == 200 and c2 == 404)
        c, body, _ = call('/api/localplug/remove', {'id': 'hello-plug', 'wipe': True})
        c2, body2, _ = call('/api/localplug')
        check('удаление', c == 200 and json.loads(body2)['plugins'] == [])
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)) + f'  (проверок: {N})')
    sys.exit(1 if BAD else 0)


main()
