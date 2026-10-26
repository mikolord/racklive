"""Мини-браузер Frank с руками: вход в панели, клики, ввод — через chromedriver по протоколу W3C WebDriver.

Зачем отдельно от frankbrowser.py: тот делает «быстрый снимок» анонимным Chromium (пустой профиль, только открыть и посмотреть). Здесь — настоящая
сессия браузера, в которой можно войти в веб-интерфейс (форма логина), нажать, напечатать, выполнить небольшой скрипт и снять снимок. Всё это нужно,
когда человек говорит «войди и покажи»: сам Frank пароля не ищет, он получает данные от человека и передаёт их браузеру.

Устройство: общение с chromedriver обычным HTTP + JSON (никаких сторонних библиотек), по одной сессии на разговор, сессия живёт, пока её не закроют
или пока не истечёт простой (IDLE). Скриншоты складываются туда же, где снимки мини-браузера (data/frank/shots), и отдаются человеку в ответе.

Правила безопасности задаются выше (в Frank): какие сайты можно, когда входить. Здесь — только механизм, плюс лимиты времени и размеров.
"""
import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import frankbrowser

BINARIES = ('chromedriver', '/usr/bin/chromedriver', '/usr/lib/chromium/chromedriver')
BROWSERS = ('chromium', 'chromium-browser', 'google-chrome')
IDLE = 900                     # секунд без обращения — сессия закрывается
MAX_SHOTS = 3                  # снимков за один ответ
ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'
try:                                                          # тесты: порт уже запущенного (поддельного) chromedriver
    FORCE_PORT = int(os.environ.get('RL_WD_PORT') or 0) or None
except ValueError:
    FORCE_PORT = None
SESSIONS = {}
LOCK = threading.Lock()


class WdError(Exception):
    pass


def driver_binary():
    for b in BINARIES:
        p = b if os.path.isabs(b) else shutil.which(b)
        if p and os.path.exists(p):
            return p
    return None


def browser_binary():
    return next((p for b in BROWSERS for p in [shutil.which(b)] if p), None)


def available():
    return bool(FORCE_PORT) or bool(driver_binary() and browser_binary())


def where():
    d, b = driver_binary(), browser_binary()
    if not d or not b:
        return ''
    try:
        v = subprocess.run([d, '--version'], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        v = d
    return f'{v.splitlines()[0] if v else d} · {b}'[:120]


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Session:
    def __init__(self, proc, port, sid):
        self.proc, self.port, self.sid, self.t = proc, port, sid, time.time()

    def call(self, method, path, body=None, timeout=120):
        url = f'http://127.0.0.1:{self.port}{path}'
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read() or b'{}')
            except ValueError:
                j = {}
            j.setdefault('value', {})
            j['value'].setdefault('message', f'HTTP {e.code}')
            return j
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            raise WdError(f'браузер не отвечает: {e}')

    def value(self, method, path, body=None, timeout=120, what='действие'):
        r = self.call(method, path, body, timeout)
        v = r.get('value')
        if isinstance(v, dict) and v.get('error'):
            raise WdError(f'{what}: {v.get("message") or v.get("error")}'[:300])
        return v

    def close(self):
        try:
            self.call('DELETE', f'/session/{self.sid}', timeout=20)
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _start(key):
    drv = driver_binary()
    br = browser_binary()
    if not FORCE_PORT and (not drv or not br):
        raise WdError('в этой установке нет браузера с управлением (chromedriver). Он ставится в образ Docker при сборке')
    port = FORCE_PORT or _free_port()
    proc = None
    if not FORCE_PORT:
        try:
            proc = subprocess.Popen([drv, f'--port={port}', '--log-path=/tmp/chromedriver.log'], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=(os.name == 'posix'))
        except OSError as e:
            raise WdError(f'не удалось запустить chromedriver: {e}')
        for _ in range(100):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/status', timeout=2) as r:
                    if json.loads(r.read() or b'{}').get('value', {}).get('ready'):
                        break
            except Exception:
                time.sleep(.2)
        else:
            proc.terminate()
            raise WdError('chromedriver не запустился — посмотрите журнал в /tmp/chromedriver.log')
    s = Session(proc, port, '')
    cap = {'capabilities': {'alwaysMatch': {'browserName': 'chrome', 'goog:chromeOptions': {
        'binary': br, 'args': ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--hide-scrollbars',
                               '--mute-audio', '--disable-background-networking', '--window-size=1280,900']}}}}
    v = s.value('POST', '/session', cap, timeout=180, what='не удалось открыть браузер')
    s.sid = (v or {}).get('sessionId') or ''
    if not s.sid:
        raise WdError('браузер не создал сессию')
    return s


def session(key='default', width=None, height=None):
    """the browser session of this conversation (started on first use)"""
    with LOCK:
        for k in [k for k, s in SESSIONS.items() if time.time() - s.t > IDLE]:
            SESSIONS.pop(k).close()
        s = SESSIONS.get(key)
        if s and s.proc and s.proc.poll() is not None:
            SESSIONS.pop(key, None)
            s = None
        if not s:
            s = SESSIONS[key] = _start(key)
    s.t = time.time()
    return s


def stop(key='default'):
    with LOCK:
        s = SESSIONS.pop(key, None)
    if s:
        s.close()
        return True
    return False


def stop_all():
    with LOCK:
        keys = list(SESSIONS)
    for k in keys:
        stop(k)


# ───────── действия ─────────
def goto(key, url, timeout=60):
    s = session(key)
    url = frankbrowser.check_url(url)
    s.value('POST', f'/session/{s.sid}/url', {'url': url}, timeout=timeout, what='страница не открылась')
    return url


def current_url(key):
    s = session(key)
    return s.value('GET', f'/session/{s.sid}/url') or ''


def title(key):
    s = session(key)
    return s.value('GET', f'/session/{s.sid}/title') or ''


def source(key):
    return session(key).value('GET', f'/session/{session(key).sid}/source') or ''

def _sel(sel):
    """css | xpath=… | text=… → (using, value)"""
    sel = str(sel or '').strip()
    if sel.lower().startswith('xpath='):
        return 'xpath', sel[6:]
    if sel.lower().startswith('text='):
        return 'text', sel[5:]
    return 'css selector', sel


def _element(key, sel):
    s = session(key)
    using, value = _sel(sel)
    if using == 'text':
        return s.value('POST', f'/session/{s.sid}/element', {'using': 'link text', 'value': value}, what='элемент не найден')
    v = s.call('POST', f'/session/{s.sid}/element', {'using': using, 'value': value})
    val = v.get('value')
    if isinstance(val, dict):
        return val.get(ELEMENT) or val.get('ELEMENT')
    return None


def find(key, sel):
    return _element(key, sel)


def click(key, sel):
    s = session(key)
    e = _element(key, sel)
    if not e:
        raise WdError(f'не нашёл элемент «{sel}»')
    s.value('POST', f'/session/{s.sid}/element/{e}/click', {}, what='нажать не получилось')
    return True


def send_keys(key, sel, text, clear=False):
    s = session(key)
    e = _element(key, sel)
    if not e:
        raise WdError(f'не нашёл поле «{sel}»')
    if clear:
        s.call('DELETE', f'/session/{s.sid}/element/{e}/clear')
    s.value('POST', f'/session/{s.sid}/element/{e}/value', {'text': text, 'value': list(str(text))}, what='не удалось напечатать')
    return True


PRESS = {'enter': '\ue007', 'tab': '\ue004', 'escape': '\ue00c', 'space': ' '}


def press(key, name='enter', sel=None):
    """a single key: enter — как будто нажали в поле (в конец или в найденное поле)"""
    s = session(key)
    ch = PRESS.get(str(name or 'enter').lower(), '\ue007')
    try:
        if sel:
            send_keys(key, sel, ch)
        else:
            s.value('POST', f'/session/{s.sid}/actions', {'actions': [{'type': 'key', 'id': 'kb', 'actions': [
                {'type': 'keyDown', 'value': ch}, {'type': 'keyUp', 'value': ch}]}]}, what='нажать клавишу не получилось')
    except WdError:
        raise
    return True


def execute(key, script, args=()):
    s = session(key)
    return s.value('POST', f'/session/{s.sid}/execute/sync', {'script': script, 'args': list(args)}, what='скрипт не выполнился')


def screenshot(key, data_dir, name=None):
    """снимок текущего состояния → имя файла в data/frank/shots"""
    s = session(key)
    b64 = s.value('GET', f'/session/{s.sid}/screenshot', timeout=120, what='снимок не получился')
    if not b64:
        raise WdError('браузер не отдал снимок')
    name = name or f'{int(time.time())}-{secrets.token_hex(4)}.png'
    p = os.path.join(frankbrowser.shots_dir(data_dir), name)
    with open(p, 'wb') as f:
        f.write(base64.b64decode(b64))
    frankbrowser.prune(data_dir)
    return name if os.path.getsize(p) > 1000 else None


def text_now(key):
    """заголовок и читаемый текст текущей страницы (тот же разбор, что у мини-браузера)"""
    src = source(key)
    return frankbrowser._text_of(src[:4_000_000])


# ───────── вход в веб-интерфейс ─────────
FIELDS_JS = ("var f={};var t=[],p=[];document.querySelectorAll('input').forEach(function(i){"
             "var v=!!(i.offsetWidth||i.offsetHeight);if(!v)return;var ty=(i.type||'text').toLowerCase();"
             "if(ty==='password')p.push(i);else if(['text','email','tel',''].indexOf(ty)>=0)t.push(i);});"
             "function d(e){return e?(e.name||e.id||''):'';}f.login=d(t[0]);f.password=d(p[0]);"
             "var b=document.querySelector('button[type=submit],input[type=submit]');"
             "f.submit=b?((b.name||b.id)?'#'+(b.id||''):''):'';"
             "if(!f.submit&&b){f.submit='button[type=submit]';}"
             "f.hasPass=p.length>0;f.texts=t.length;f.passwords=p.length;return JSON.stringify(f);")


def form_fields(key):
    """что похоже на форму входа на открытой странице (без знания конкретного интерфейса)"""
    raw = execute(key, FIELDS_JS) or '{}'
    try:
        f = json.loads(raw)
    except ValueError:
        f = {}
    return f


def login(key, url, user, password, user_sel=None, pass_sel=None, submit_sel=None, wait=20):
    """открыть адрес и войти: заполняет поля, нажимает кнопку, ждёт исчезновения формы → {'ok', 'url', 'title', 'how'}"""
    if not str(user or '') or not str(password or ''):
        raise WdError('для входа нужны и логин, и пароль')
    goto(key, url)
    time.sleep(1.0)
    f = form_fields(key)
    u_sel = user_sel or (f.get('login') and ('[name="%s"]' % f['login'])) or 'input[type=text], input[type=email]'
    p_sel = pass_sel or (f.get('password') and ('[name="%s"]' % f['password'])) or 'input[type=password]'
    send_keys(key, u_sel, user, clear=True)
    send_keys(key, p_sel, password, clear=True)
    how = 'form'
    try:
        click(key, submit_sel or 'button[type=submit]')
    except WdError:
        how = 'enter'
        press(key, 'enter', sel=p_sel)
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(1.0)
        try:
            still = form_fields(key).get('hasPass')
        except WdError:
            still = False
        if not still:
            break
    ok = not bool(form_fields(key).get('hasPass'))
    if ok:
        time.sleep(2.5)            # панель Angular/React догружает данные своих карточек уже после входа
    return {'ok': ok, 'url': current_url(key), 'title': title(key), 'how': how,
            'note': '' if ok else 'форма входа всё ещё на странице — возможно, нужен другой селектор или есть второй шаг (код, капча)',
            'fields': {k: f.get(k) for k in ('login', 'password', 'texts', 'passwords')}}
