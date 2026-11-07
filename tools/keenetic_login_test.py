"""Keenetic sign-in: Argon2id by the RFC 9106 vector, and the x-ndw4 / old login against a small fake router (server side written from the same formulas)."""
import base64, hashlib, hmac, http.server, json, os, secrets, socket, sys, threading, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd.argon2id import argon2id
from rackd.drivers import keenetic
from rackd.util import DriverError

fails = 0
def check(name, ok, extra=''):
    global fails
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else f'  {extra}'))
    fails += 0 if ok else 1

tag = argon2id(b'\x01' * 32, b'\x02' * 16, 3, 32, 32, parallelism=4, secret=b'\x03' * 8, data=b'\x04' * 12)
check('Argon2id: the test vector of RFC 9106', tag.hex() == '0d640df58d78766c08c037a34a8b53c9d01ef0452d75b65eb52520e96b01e659', tag.hex())
check('Argon2id: lane count 1, the parameters of the router', len(argon2id('пароль', b'\x07' * 16, 2, 8, 64)) == 64)
try:
    argon2id('x', b'\x07' * 16, 3, 1024 * 1024, 64); check('Argon2id: huge parameters are refused', False)
except ValueError:
    check('Argon2id: huge parameters are refused', True)

USER, PASS = 'admin', 'Правильный-пароль1'
SALT = base64.b64encode(b'\x09' * 16).decode()
hm = lambda k, m: hmac.new(k, m.encode() if isinstance(m, str) else m, hashlib.sha3_512).digest()
xor = lambda a, b: bytes(x ^ y for x, y in zip(a, b))
KEY = argon2id(PASS, b'\x09' * 16, 2, 8, 64)
CK, SK = hm(KEY, 'NDW4 Interactive Client Key'), hm(KEY, 'NDW4 Interactive Server Key')
ST = hashlib.sha3_512(CK).digest()


class Router(http.server.BaseHTTPRequestHandler):
    mode, sessions, state, logins = 'ndw4', set(), {}, []
    def log_message(self, *a): pass
    def reply(self, code, headers=None, body=b'{}'):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def authed(self):
        return any(c.strip() in self.sessions for c in (self.headers.get('Cookie') or '').split(';'))
    def challenge(self, method=None):
        h = {'X-NDM-Realm': 'Fake', 'X-NDM-Challenge': 'CHALLENGE', 'Set-Cookie': 'sid=%s; Path=/; Max-Age=20' % secrets.token_hex(6),
             'WWW-Authenticate': method or 'x-ndw2-interactive realm="Fake" challenge="CHALLENGE"'}
        return h
    def do_GET(self):
        if self.path == '/auth':
            return self.reply(200) if self.authed() else self.reply(401, self.challenge())
        self.reply(200 if self.authed() else 401, body=json.dumps({'release': 'fake'}).encode())
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        ck = next((c.strip() for c in (self.headers.get('Cookie') or '').split(';') if c.strip().startswith('sid=')), 'sid=none')
        if 'password' in d:
            self.logins.append('old')
            md5 = hashlib.md5(f"{USER}:Fake:{PASS}".encode()).hexdigest()
            if self.mode == 'old' and d['password'] == hashlib.sha256(('CHALLENGE' + md5).encode()).hexdigest():
                self.sessions.add(ck); return self.reply(200)
            return self.reply(401, self.challenge('x-ndw4-interactive endpoint="/auth"' if self.mode == 'ndw4' else None))
        data = lambda o: {'X-NDM-Data': base64.b64encode(json.dumps(o).encode()).decode()}
        if self.mode == 'old':                 # old firmware does not know this request: an ordinary refusal, no parameters
            return self.reply(401, self.challenge())
        if 'signature-proof' in d:
            m = self.state['msg'] + ';signature4=' + self.state['sig']
            ok = xor(CK, hm(ST, m)) == base64.b64decode(d['signature-proof'])
            if ok:
                self.sessions.add(ck)
            return self.reply(200 if ok else 403)
        if 'proof' in d:
            m = self.state['msg']
            if xor(CK, hm(ST, m)) != base64.b64decode(d['proof']):
                return self.reply(403)
            self.state['sig'] = base64.b64encode(hm(self.state.get('sk', SK), m)).decode()
            return self.reply(401, data({'signature': self.state['sig']}))
        n2 = base64.b64encode(secrets.token_bytes(32)).decode()
        self.state['msg'] = f"login1={d['login']},nonce1={d['nonce']};iter2=2,memcost2=8,nonce2={n2},salt2={SALT};login3={d['login']},nonce3={n2}"
        self.logins.append('ndw4')
        return self.reply(401, data({'salt': SALT, 'nonce': n2, 'iter': 2, 'memcost': 8}))


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Router)
threading.Thread(target=srv.serve_forever, daemon=True).start()
host = f'127.0.0.1:{srv.server_address[1]}'
def reset(mode):
    Router.mode = mode; Router.sessions = set(); Router.state = {}; Router.logins = []
    keenetic.SESSIONS.clear(); keenetic.BAD_LOGIN.clear(); keenetic.BASES.clear()
K = keenetic.Keenetic()
cfg = lambda **k: dict({'host': host, 'username': USER, 'password': PASS}, **k)

reset('ndw4')
get, cli = K._session(cfg())
check('x-ndw4: the right password signs in', get('/rci/show/version').get('release') == 'fake' and 'ndw4' in Router.logins, Router.logins)
check('x-ndw4: no failed old login before it', 'old' not in Router.logins, Router.logins)
n = len(Router.logins); K._session(cfg())
check('x-ndw4: the session is kept, no second login', len(Router.logins) == n, Router.logins)

reset('ndw4')
try:
    K._session(cfg(password='неверный')); check('x-ndw4: a wrong password is refused', False)
except DriverError as e:
    check('x-ndw4: a wrong password is refused', 'неверный логин или пароль' in str(e), str(e))
n = len(Router.logins)
try:
    K._session(cfg(password='неверный'))
except DriverError as e:
    check('x-ndw4: no new attempts after a refusal', 'следующая попытка' in str(e) and len(Router.logins) == n, str(e))

reset('ndw4'); Router.state = {'sk': b'\x00' * 64}
try:
    K._session(cfg()); check('x-ndw4: a server that does not know the password is not trusted', False)
except DriverError:
    check('x-ndw4: a server that does not know the password is not trusted', True)

reset('old')
get, cli = K._session(cfg())
check('old login still works on old firmware', get('/rci/show/version').get('release') == 'fake' and 'ndw4' not in Router.logins, Router.logins)

s = socket.socket(); s.bind(('127.0.0.1', 0)); closed = s.getsockname()[1]; s.close()
reset('old')
try:
    K._session(cfg(host=f'127.0.0.1:{closed}')); check('closed port: a clear message', False)
except DriverError as e:
    check('closed port: a clear message', 'не удалось подключиться' in str(e) and 'Пользователи и доступ' in str(e) and '15 минут' in str(e), str(e))
reset('old')
K._local_rci = lambda c: ('через Entware', c)
check('no answer + Entware configured: the inside path is used', K._session(cfg(host=f'127.0.0.1:{closed}', entwarePassword='x'))[0] == 'через Entware')
del K._local_rci
reset('old')
check('bare address tries http first and remembers it', K._session(cfg()) and keenetic.BASES.get(host) == 'http://' + host, keenetic.BASES)
srv.shutdown()
print('ВСЁ OK' if not fails else f'ОШИБОК: {fails}')
sys.exit(1 if fails else 0)
