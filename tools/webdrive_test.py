"""Управление браузером (rackd/webdrive.py): вход в веб-интерфейс, клики, ввод, снимки — на поддельном chromedriver, который говорит по протоколу W3C.
Зачем поддельный: настоящий chromedriver есть только в образе Docker (NAS), а логику надо проверять везде, включая Windows.
Run: python tools/webdrive_test.py (prints ВСЁ OK)"""
import base64
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import webdrive as W  # noqa: E402

bad = []
DATA = tempfile.mkdtemp(prefix='wd-')
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
E = W.ELEMENT


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


LOGIN_HTML = ('<html><head><title>Роутер — Вход</title></head><body>'
              '<input name="login_key" type="text"><input name="password_key" type="password">'
              '<button type="submit">Войти</button></body></html>')
HOME_HTML = '<html><head><title>Панель роутера</title></head><body><h1>Интернет работает</h1><p>Клиентов: 12</p></body></html>'


class Fake:
    """мини-эмуляция chromedriver: помнит сессию, страницу, нажатия"""
    state = {}

    def reset(self):
        Fake.state = {'url': '', 'typed': [], 'clicks': [], 'js': [], 'logged': False, 'sessions': 0, 'no_login': False}

    def logged(self):
        return Fake.state['logged']

    def page(self):
        if Fake.state['url'] in ('', 'about:blank'):
            return '<html><head><title></title></head><body></body></html>'
        return HOME_HTML if Fake.state['logged'] else LOGIN_HTML


FAKES = Fake()


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = self.path
        if p == '/status':
            return self._send({'value': {'ready': True, 'build': {'version': 'fake-1.0'}}})
        if p.endswith('/url'):
            return self._send({'value': FAKES.state['url']})
        if p.endswith('/title'):
            t = 'Панель роутера' if FAKES.logged() else 'Роутер — Вход'
            return self._send({'value': t})
        if p.endswith('/source'):
            return self._send({'value': FAKES.page()})
        if p.endswith('/screenshot'):
            return self._send({'value': base64.b64encode(PNG + b'\0' * 2000).decode()})
        return self._send({'value': {'error': 'unknown'}}, 404)

    def do_DELETE(self):
        if '/session/' in self.path and self.path.endswith('url') is False:
            FAKES.state['logged'] = False
            return self._send({'value': None})
        return self._send({'value': None})

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = json.loads(self.rfile.read(n) or b'{}')
        p = self.path
        if p == '/session':
            Fake.state['sessions'] += 1
            return self._send({'value': {'sessionId': 'S1', 'capabilities': {}}})
        if p.endswith('/url'):
            Fake.state['url'] = body.get('url')
            return self._send({'value': None})
        if p.endswith('/element'):
            val = body.get('value') or ''
            if not val:
                return self._send({'value': {'error': 'no such element', 'message': 'пусто'}})
            if 'login' in val or 'password' in val or val.startswith('input'):
                return self._send({'value': {E: 'e1'}})
            if 'submit' in val or 'button' in val:
                return self._send({'value': {E: 'e2'}})
            return self._send({'value': {E: 'e3'}})
        if p.endswith('/value'):
            FAKES.state['typed'].append(body.get('text'))
            return self._send({'value': None})
        if p.endswith('/click'):
            FAKES.state['clicks'].append(p)
            FAKES.state['logged'] = FAKES.state['logged'] or not FAKES.state['no_login']
            return self._send({'value': None})
        if p.endswith('/actions'):
            FAKES.state['clicks'].append('keys')
            FAKES.state['logged'] = FAKES.state['logged'] or not FAKES.state['no_login']
            return self._send({'value': None})
        if p.endswith('/execute/sync'):
            FAKES.state['js'].append(body.get('script', '')[:40])
            has = not FAKES.logged()
            out = {'login': 'login_key' if has else '', 'password': 'password_key' if has else '', 'hasPass': has,
                   'texts': 1 if has else 0, 'passwords': 1 if has else 0}
            return self._send({'value': json.dumps(out)})
        return self._send({'value': {'error': 'unknown'}}, 404)


FAKES.reset()
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
W.FORCE_PORT = srv.server_address[1]
WD_PORT = W.FORCE_PORT
W.driver_binary = lambda: 'fake-chromedriver'
W.browser_binary = lambda: '/usr/bin/chromium'

try:
    check('сессия открывается и страница грузится', W.goto('main', '192.168.1.1') == 'http://192.168.1.1' and W.current_url('main') == 'http://192.168.1.1')
    check('заголовок читается', W.title('main') == 'Роутер — Вход', W.title('main'))
    f = W.form_fields('main')
    check('поля входа находятся сами (логин, пароль, форма есть)', f.get('login') == 'login_key' and f.get('password') == 'password_key' and f.get('hasPass'), f)
    r = W.login('main', '192.168.1.1', 'admin', 'pw123')
    check('вход: поля заполнены, кнопка нажата, форма ушла', r['ok'] and 'admin' in FAKES.state['typed'] and 'pw123' in FAKES.state['typed']
          and FAKES.state['clicks'] and r['url'] == 'http://192.168.1.1', r)
    check('после входа заголовок и текст — уже панель', 'Панель' in W.title('main'), W.title('main'))
    shot = W.screenshot('main', DATA)
    check('снимок сохраняется файлом в папке снимков', bool(shot) and os.path.isfile(os.path.join(DATA, 'frank', 'shots', shot)), shot)
    check('текст страницы читается тем же разбором, что у мини-браузера', 'Клиентов' in (W.text_now('main')[1] or ''))
    W.click('main', 'button[type=submit]')
    check('клик по кнопке проходит', FAKES.state['clicks'][-1].endswith('/click'))
    W.send_keys('main', 'input[name=login_key]', 'ещё')
    check('ввод текста проходит', FAKES.state['typed'][-1] == 'ещё', FAKES.state['typed'][-3:])
    W.press('main', 'enter')
    check('нажатие клавиши проходит (Enter)', FAKES.state['clicks'][-1] == 'keys')
    out = W.execute('main', 'return document.title')
    check('скрипт на странице выполняется', isinstance(out, str) and bool(out) and bool(FAKES.state['js']), (out, FAKES.state['js'][-1:]))
    check('сессия закрывается', W.stop('main') is True and W.stop('main') is False)

    # вход не удался: форма остаётся на странице → честный ответ с подсказкой
    FAKES.reset()
    FAKES.state['no_login'] = True
    r2 = W.login('main', '192.168.1.1', 'admin', 'неверный', wait=3)
    check('если не пустило — ok=False и подсказка про второй шаг', r2['ok'] is False and 'второй шаг' in r2['note'], r2)
    W.stop('main')

    # нет драйвера — понятная ошибка
    W.FORCE_PORT = None
    W.driver_binary = lambda: None
    W.browser_binary = lambda: None
    check('без chromedriver — понятное объяснение', W.available() is False and raises(lambda: W.session('main'), 'chromedriver'))
finally:
    shutil.rmtree(DATA, ignore_errors=True)          # сам поддельный драйвер гасим в самом конце: он нужен сквозному сценарию

# ── сквозной сценарий: живой демо-сервер + поддельная модель + поддельный chromedriver ──
import http.server as _hs  # noqa: E402

W.FORCE_PORT = WD_PORT
plan, results = {}, []
FAKES.reset()
FAKES.state['url'] = ''


class Model(_hs.BaseHTTPRequestHandler):
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
        Model.last_tools = [t['function']['name'] for t in body.get('tools') or []]
        out = json.dumps({'choices': [{'message': msg}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 5}}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(out)))
        self.end_headers(); self.wfile.write(out)


model = _hs.ThreadingHTTPServer(('127.0.0.1', 0), Model)
threading.Thread(target=model.serve_forever, daemon=True).start()
port2 = 0
_s = socket.socket(); _s.bind(('127.0.0.1', 0)); port2 = _s.getsockname()[1]; _s.close()
data2 = tempfile.mkdtemp(prefix='wd-srv-')
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port2), RL_DATA=data2, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8',
           RL_WD_PORT=str(WD_PORT))
srv2 = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port2}'


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
    for _ in range(300):
        j = api('/api/ai/job', {'job': r['job']})
        if j.get('done'):
            return r['chat'], j
        time.sleep(.2)
    raise SystemExit('задача не завершилась: ' + json.dumps(j, ensure_ascii=False)[:400])


try:
    for _ in range(40):
        try:
            api('/api/state')
            break
        except Exception:
            time.sleep(.5)
    api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': f'http://127.0.0.1:{model.server_address[1]}/v1', 'model': 'fake', 'key': 'k'}, 'PUT')
    api('/api/ai', {'agent': True, 'browser': True}, 'PUT')
    plan['ВОЙДИ'] = ('browse', {'op': 'login', 'url': '192.168.1.1', 'user': 'admin', 'password': 'pw-из-чата'})
    cid, _ = say('ВОЙДИ в роутер admin pw-из-чата')
    res = json.loads(results[-1]) if results and results[-1].startswith('{') else {}
    check('вход через чат: модель передала данные, браузер вошёл', res.get('ok') is True and 'Панель' in json.dumps(res, ensure_ascii=False), res)
    c = api('/api/ai/chats/' + cid)
    shots = [m for m in c['messages'] if m.get('shots')]
    check('снимок входа пришёл в ответ человеку', bool(shots) and shots[-1]['shots'], shots[-1:] if shots else c['messages'][-1])
    plan['НАЖМИ'] = ('browse', {'op': 'click', 'sel': 'button[type=submit]'})
    say('НАЖМИ кнопку')
    check('клик по странице через чат проходит', '"op": "click"' in (results[-1] or ''), results[-1:])
    plan['ЗАКРОЙ'] = ('browse', {'op': 'quit'})
    say('ЗАКРОЙ браузер')
    check('браузер закрывается по просьбе', 'браузер закрыт' in (results[-1] or ''), results[-1:])
finally:
    srv2.terminate()
    try:
        srv2.wait(10)
    except Exception:
        srv2.kill()
    model.shutdown()
    srv.shutdown()
    shutil.rmtree(data2, ignore_errors=True)

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
