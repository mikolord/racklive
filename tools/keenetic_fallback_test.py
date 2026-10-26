"""Keenetic with KeeneticOS 5.2: the API sign-in is refused → the driver asks the router from the inside over SSH (Entware).
No router needed: the HTTP side and the SSH side are replaced. Run: python tools/keenetic_fallback_test.py (prints ВСЁ OK)"""
import hashlib, os, sys, time, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd.drivers import keenetic as K  # noqa: E402
from rackd.util import DriverError  # noqa: E402

bad = []


def check(name, ok):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        bad.append(name)


class Resp:
    def __init__(self, code, headers=None, body=b''):
        self.status = self.code = code
        self.headers = headers or {}
        self._b = body

    def read(self):
        return self._b


class Fake(K.Keenetic):
    """the router refuses the login (401), SSH answers like curl on 127.0.0.1:79 would"""
    def __init__(self):
        self.scripts = []

    def _ssh(self, cfg, script, timeout=30, params=None):
        self.scripts.append(script)
        return '{"ok": true}' if 'show/version' in script else '[{"parse": {"status": {}}}]'


cfg = {'host': '192.168.1.1', 'username': 'admin', 'password': 'pw1', 'entwarePassword': 'ent'}
real_open = K.urllib.request.OpenerDirector.open
logins = []


def fake_open(self, req, timeout=None):
    if req.data is not None:
        logins.append(req.full_url)
    raise urllib.error.HTTPError(req.full_url, 401, 'no', {'X-NDM-Realm': 'Netcraze Ultra', 'X-NDM-Challenge': 'abc'}, None)


K.urllib.request.OpenerDirector.open = fake_open
try:
    d = Fake()
    get, cli = d._session(cfg)
    check('вход по API отклонён → запасной путь вместо ошибки', callable(get) and callable(cli) and len(logins) == 1)
    r = get('/rci/show/version')
    check('GET идёт на 127.0.0.1:79 внутри роутера', r == {'ok': True} and "curl -s -m 40 'http://127.0.0.1:79/rci/show/version'" in d.scripts[-1])
    r = cli(['show version', 'system configuration save'])
    s = d.scripts[-1]
    check('команды уходят одним POST /rci/ со списком parse', "http://127.0.0.1:79/rci/'" in s and '"parse": "show version"' in s and '"parse": "system configuration save"' in s and '--data-binary @-' in s)
    d._session(cfg)
    d._session(cfg)
    check('повторные опросы не ломятся в API снова (иначе роутер закроет доступ)', len(logins) == 1)
    try:
        get('/rci/x; reboot')
        check('в адрес нельзя подсунуть команду', False)
    except DriverError:
        check('в адрес нельзя подсунуть команду', True)
    cfg2 = dict(cfg, password='pw2')
    cfg2.pop('entwarePassword')
    try:
        d._session(cfg2)
        check('без SSH-пароля остаётся прежняя ошибка', False)
    except DriverError as e:
        check('без SSH-пароля остаётся прежняя ошибка', 'неверный логин или пароль' in str(e))
finally:
    K.urllib.request.OpenerDirector.open = real_open

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
