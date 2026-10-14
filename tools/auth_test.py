"""Sign-in, second factor and devices: a real server (not the demo) on a temporary folder, plus the pieces that need no network
(sessions with a fake clock, e-mail / SMS / Telegram codes with fake senders).  Run: python tools/auth_test.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import auth, mfa  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


class Client:
    """a browser: keeps its own cookies"""
    def __init__(self, base, ua='Mozilla/5.0 (iPhone; CPU iPhone OS 17) AppleWebKit Safari', ip=None):
        self.base, self.ua, self.cookies, self.ip = base, ua, {}, ip

    def call(self, path, body=None, method='POST'):
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode() if method != 'GET' else None, method=method,
                                     headers=dict({'Content-Type': 'application/json', 'User-Agent': self.ua,
                                                   'Cookie': '; '.join(f'{k}={v}' for k, v in self.cookies.items())},
                                                  **({'X-Forwarded-For': self.ip} if self.ip else {})))
        try:
            r = urllib.request.urlopen(req, timeout=20)
        except urllib.error.HTTPError as e:
            r = e
        for c in r.headers.get_all('Set-Cookie') or []:
            k, _, rest = c.partition('=')
            v = rest.split(';')[0]
            if v:
                self.cookies[k] = v
            else:
                self.cookies.pop(k, None)
        raw = r.read()
        return r.status if hasattr(r, 'status') else r.code, (json.loads(raw) if raw else {})

    def authed(self):
        return self.call('/api/state', method='GET')[1].get('authed')


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def sessions_unit():
    d = tempfile.mkdtemp(prefix='rl-sess-')
    clock = [1_000_000.0]
    real = time.time
    time.time = lambda: clock[0]
    try:
        s = auth.Sessions(d, policy=lambda: {'idleMin': 60, 'sessionDays': 30, 'trustDays': 90})
        tok, dtok, new, dev = s.create('1.1.1.1', 'Mozilla/5.0 (Windows NT 10) Edg/120', remember=True)
        check('session: new device is recorded', new and s.valid(tok) and s.devices(tok)[0]['name'] == 'Windows · Edge')
        check('remembered device is trusted for the second factor', bool(s.trusted_device(dtok)))
        tok2, dtok2, _, dev2 = s.create('2.2.2.2', 'Mozilla/5.0 (iPhone) Safari', remember=False)
        check('not remembered: valid now', s.valid(tok2))
        clock[0] += 50 * 60
        check('not remembered: still valid 50 min later (activity slides it)', s.valid(tok2))
        clock[0] += 50 * 60
        check('not remembered: 50 more minutes of activity keep sliding', s.valid(tok2))
        clock[0] += 61 * 60
        check('not remembered: ends after 60 minutes of silence', not s.valid(tok2))
        check('remembered device is still in', s.valid(tok))
        check('not remembered device does not skip the second factor', s.trusted_device(dtok2) is None)
        tok3, _, _, dev3 = s.create('3.3.3.3', 'Mozilla/5.0 (Android) Chrome', remember=False)
        for _ in range(14):
            clock[0] += 55 * 60
            s.valid(tok3)
        check('not remembered: never lives past 12 hours, even when used', not s.valid(tok3))
        clock[0] += 31 * 86400
        check('remembered device: session ends after 30 days of silence', not s.valid(tok))
        check('remembered device: still skips the second factor (90 days)', bool(s.trusted_device(dtok)))
        clock[0] += 61 * 86400
        check('remembered device: trust ends after 90 days', s.trusted_device(dtok) is None)
        a, da, _, dev_a = s.create('4.4.4.4', 'Mozilla/5.0 (Macintosh) Chrome', remember=True)
        b, db, _, dev_b = s.create('5.5.5.5', 'Mozilla/5.0 (Linux) Firefox', remember=True)
        s.set_trusted(dev_b, False)
        check('un-remember: the device no longer skips the second factor', s.trusted_device(db) is None and s.valid(b))
        s.revoke(dev_b)
        check('revoke: its session is gone', not s.valid(b))
        c, dc, _, dev_c = s.create('6.6.6.6', 'Mozilla/5.0 (iPhone) Safari', remember=True)
        s.revoke_others(dev_a)
        check('sign out everywhere except this one', s.valid(a) and not s.valid(c) and len(s.devices(a)) == 1)
        check('a revoked device loses its trust', s.trusted_device(dc) is None)
        old = tempfile.mkdtemp(prefix='rl-old-')
        json.dump({'oldtoken123': clock[0] + 5 * 86400}, open(os.path.join(old, 'sessions.json'), 'w'))
        s3 = auth.Sessions(old)
        check('an old-format session is carried over, remembered, still valid', s3.valid('oldtoken123') and s3.devices('oldtoken123')[0]['name'] == 'Прежний вход')
        s3.valid('oldtoken123', '192.168.1.50', 'Mozilla/5.0 (Windows NT 10.0) Chrome/120')
        dv = s3.devices('oldtoken123')[0]
        check('...and it gets its real name and address on the first request', dv['name'] == 'Windows · Chrome' and dv['ip'] == '192.168.1.50')
        shutil.rmtree(old, ignore_errors=True)
        s2 = auth.Sessions(d)
        check('sessions survive a restart (stored as hashes)', s2.valid(a) and a not in open(s2.path).read())
    finally:
        time.time = real
        shutil.rmtree(d, ignore_errors=True)


class FakeTg:
    def __init__(self):
        self.asked, self.status = [], 'asked'
        self.username = 'bot'

    def ready(self):
        return True

    def tg(self):
        return {'enabled': True, 'token': 't', 'chat': '111', 'allowed': '111'}

    def ask_mfa(self, ip, ua):
        self.asked.append((ip, ua))
        return 'tgcode'

    def check(self, code):
        return {'status': self.status, 'kind': 'mfa'} if code == 'tgcode' else None

    def consume(self, code):
        pass


class FakeStore:
    def __init__(self):
        self.cfg = {'devices': [{'id': 'o1', 'driver': 'openwrt', 'name': 'OpenWrt'}], 'settings': {'title': 'Test'},
                    'notify': {'email': {'host': 'smtp.test', 'to': 'x@y.z'}}}
        self.saves = 0

    def save(self):
        self.saves += 1


def mfa_unit():
    app = type('A', (), {})()
    app.store, app.tgbot = FakeStore(), FakeTg()
    m = mfa.Mfa(app)
    sent = []
    m._send_mail = lambda to, subj, text: sent.append(('mail', to, text))
    m._send_sms = lambda s, text: sent.append(('sms', s['phone'], text))
    # e-mail
    code_mail = None
    hint = m.target_begin('email', 'me@example.com')
    check('e-mail setup sends a code, address masked', hint == 'm***@example.com' and sent[-1][0] == 'mail')
    code_mail = sent[-1][2].split('Код подтверждения: ')[1][:6]
    try:
        m.target_confirm('email', '000000'); check('e-mail setup refuses a wrong code', False)
    except ValueError:
        check('e-mail setup refuses a wrong code', True)
    codes = m.target_confirm('email', code_mail)
    check('e-mail confirmed: protection is on, recovery codes issued once', m.enabled() and len(codes) == 8 and m.cfg()['recovery'] and codes[0] not in str(m.cfg()))
    # SMS
    m.target_begin('sms', '+7 (988) 123-45-67', 'o1')
    check('sms setup goes through the OpenWrt modem', sent[-1][0] == 'sms' and sent[-1][1] == '+79881234567')
    code_sms = sent[-1][2].split(' ')[0]
    check('sms confirmed', m.target_confirm('sms', code_sms) is None and (m.cfg()['sms'] or {}).get('on'))
    check('methods offered at sign-in', [x['id'] for x in m.methods()] == ['telegram'] and False or {'email', 'sms', 'recovery'} <= {x['id'] for x in m.methods()})
    m.cfg()['telegram'] = True
    check('telegram offered too', 'telegram' in [x['id'] for x in m.methods()])
    # a sign-in without the password: only a code to the mailbox / phone, and it is rationed
    check('login without password is offered for e-mail and SMS', m.login_methods() == ['email', 'sms'])
    tp, hint = m.start_primary('6.6.6.6', 'Mozilla/5.0 (Windows) Edg', 'email')
    pcode = sent[-1][2].split('Код входа: ')[1][:6]
    check('login without password: a code goes to the mailbox', sent[-1][0] == 'mail' and hint.startswith('код отправлен'))
    try:
        m.start_primary('6.6.6.6', '', 'email'); check('a second request within 20 s is refused', False)
    except ValueError:
        check('a second request within 20 s is refused', True)
    try:
        m.verify(tp, 'recovery', codes[1]); check('a recovery code alone cannot sign in without a password', False)
    except ValueError:
        check('a recovery code alone cannot sign in without a password', True)
    check('the mailbox code signs in', m.verify(tp, 'email', pcode) is True)
    m.pstarts['email'] = [time.time() - 30] * 4
    try:
        m.start_primary('6.6.6.6', '', 'email'); check('four requests in ten minutes is the limit', False)
    except ValueError:
        check('four requests in ten minutes is the limit', True)
    sec = mfa.new_secret()
    m.cfg()['totp'] = {'on': True, 'secret': sec, 'last': 0}
    check('the app code is offered for login without a password too', m.login_methods() == ['totp', 'email', 'sms'])
    ta, hint_a = m.start_primary('5.5.5.5', 'Mozilla/5.0 (Windows) Chrome', 'totp')
    check('app code: no message is sent, the sign-in just waits for the digits', sent[-1][0] != 'totp' and 'приложения' in hint_a)
    check('a wrong app code is refused', m.verify(ta, 'totp', '000000') is False or mfa.totp_now(sec) == '000000')
    check('the right app code signs in without a password', m.verify(ta, 'totp', mfa.totp_now(sec)) is True)
    m.cfg()['loginByCode'] = False
    check('the switch turns login without password off', m.login_methods() == [])
    m.cfg()['loginByCode'] = True
    m.pstarts.clear()
    # a sign-in
    t = m.begin('9.9.9.9', 'Mozilla/5.0 (Windows) Chrome')
    m.send(t, 'email')
    code = sent[-1][2].split('Код входа: ')[1][:6]
    try:
        m.send(t, 'email'); check('a second «send» within 30 s is refused', False)
    except ValueError:
        check('a second «send» within 30 s is refused', True)
    check('a wrong e-mail code is refused', m.verify(t, 'email', '123456') is False or code == '123456')
    check('the right e-mail code passes', m.verify(t, 'email', code) is True)
    m.send(t, 'sms')
    check('sms code is sent for sign-in', sent[-1][0] == 'sms')
    check('the sms code passes', m.verify(t, 'sms', sent[-1][2].split(' ')[0]) is True)
    m.send(t, 'telegram')
    check('telegram: the question goes to the bot', app.tgbot.asked and m.poll_telegram(t) == 'wait')
    app.tgbot.status = 'ok'
    check('telegram: «да» in the bot lets the sign-in through', m.poll_telegram(t) == 'ok')
    app.tgbot.status = 'denied'
    check('telegram: «нет» refuses', m.poll_telegram(t) == 'denied')
    t2 = m.begin('8.8.8.8', '')
    dropped = False
    for _ in range(6):
        try:
            m.verify(t2, 'email', '000000')
        except ValueError:
            dropped = True
            break
    check('five wrong codes end the sign-in', dropped)
    try:
        m.verify(t2, 'email', '1'); check('the ended sign-in is gone', False)
    except ValueError:
        check('the ended sign-in is gone', True)
    # recovery codes are one-time
    t3 = m.begin('7.7.7.7', '')
    rc = codes[0]
    check('a recovery code works once', m.verify(t3, 'recovery', rc) is True and m.verify(t3, 'recovery', rc) is False)
    # removing the last methods switches the protection off by itself
    m.cfg()['telegram'] = False
    m.remove('totp'); m.remove('email'); m.remove('sms')
    check('no method left → protection is off by itself', not m.enabled() and not m.cfg()['recovery'])


def totp_unit():
    s = mfa.new_secret()
    check('TOTP: RFC 6238 test vector', mfa._hotp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', 1) == '287082')
    now = 1_700_000_000
    code = mfa.totp_now(s, now)
    step = mfa.totp_check(s, code, 0, now)
    check('TOTP: the current code passes', step is not None)
    check('TOTP: the same code cannot be used twice', mfa.totp_check(s, code, step, now) is None)
    check('TOTP: one step of clock drift is allowed', mfa.totp_check(s, mfa.totp_now(s, now - 30), 0, now) is not None)
    check('TOTP: three steps of drift are not', mfa.totp_check(s, mfa.totp_now(s, now - 120), 0, now) is None)


def server_flow():
    data = tempfile.mkdtemp(prefix='rl-auth-')
    port = free_port()
    env = dict(os.environ, RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), RL_PORT=str(port), PYTHONIOENCODING='utf-8')
    env.pop('RL_DEMO', None)
    srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + '/api/state', timeout=1)
                break
            except Exception:
                time.sleep(.2)
        phone = Client(base)
        st, _ = phone.call('/api/setup', {'password': 'correct-horse'})
        check('setup: password set, signed in, device cookie issued', st == 200 and phone.authed() and 'rl_dev' in phone.cookies)
        check('a brand-new installation: the welcome tour is due', phone.call('/api/state', method='GET')[1]['settings'].get('tourDone') is False)
        phone.call('/api/tour')
        check('...and once it is done or skipped it is not due again', phone.call('/api/state', method='GET')[1]['settings'].get('tourDone') is True)
        check('a wrong password is refused', Client(base).call('/api/login', {'password': 'nope-nope-1'})[0] == 401)
        browser = next((b for b in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
                                    r'C:\Program Files\Google\Chrome\Application\chrome.exe') if os.path.exists(b)), shutil.which('chromium') or shutil.which('google-chrome'))
        if browser:
            out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--virtual-time-budget=5000', '--dump-dom', base + '/?mfapreview=1'],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60).stdout
            check('login screen: the second step renders', 'Подтвердите вход' in out and 'mfa-tile' in out and 'otp-box' in out and 'rl-crash' not in out and 'data-js-error="' not in out)
        st, r = Client(base).call('/api/login', {'password': 'correct-horse'})
        check('without the second factor a sign-in is a plain session', st == 200 and r.get('ok') and not r.get('mfa'))
        # TOTP
        st, r = phone.call('/api/mfa/totp/start')
        secret = r['secret']
        check('TOTP: secret and otpauth link are given', st == 200 and r['uri'].startswith('otpauth://totp/'))
        check('TOTP: a wrong code is refused', phone.call('/api/mfa/totp/confirm', {'code': '000000'})[0] == 400)
        st, r = phone.call('/api/mfa/totp/confirm', {'code': mfa.totp_now(secret)})
        recovery = r.get('recovery') or []
        check('TOTP confirmed: protection on, eight recovery codes', st == 200 and len(recovery) == 8)
        st, r = phone.call('/api/mfa/status')
        check('status shows protection on and hides the secret', r.get('enabled') and r.get('totp') and secret not in json.dumps(r))
        # a new device
        laptop = Client(base, 'Mozilla/5.0 (Windows NT 10.0) Edg/120')
        st, r = laptop.call('/api/login', {'password': 'correct-horse'})
        check('new device: password is not enough', st == 200 and r.get('mfa') and r.get('ticket') and not laptop.authed())
        ticket = r['ticket']
        check('new device: TOTP and recovery are offered', {'totp', 'recovery'} <= {m['id'] for m in r['methods']})
        check('new device: a wrong code is refused', laptop.call('/api/login/mfa/verify', {'ticket': ticket, 'method': 'totp', 'code': '111111'})[0] == 401)
        code = mfa.totp_now(secret, time.time() + 30)          # the code that confirmed the setup is spent — the next one is the first to sign in
        st, r = laptop.call('/api/login/mfa/verify', {'ticket': ticket, 'method': 'totp', 'code': code, 'remember': True})
        check('new device: the right code signs in', st == 200 and r.get('ok') and laptop.authed())
        check('the device list shows the laptop and the phone, the current one first', (lambda d: len(d) >= 2 and d[0]['current'] and d[0]['name'] == 'Windows · Edge')(laptop.call('/api/sessions/list')[1]['devices']))
        # the same code a second time (replay) from yet another device
        other = Client(base, 'Mozilla/5.0 (Android) Chrome')
        t2 = other.call('/api/login', {'password': 'correct-horse'})[1]['ticket']
        check('a used TOTP code cannot be replayed', other.call('/api/login/mfa/verify', {'ticket': t2, 'method': 'totp', 'code': code})[0] == 401)
        # remembered device skips the second factor
        laptop.cookies.pop('rl_session')
        st, r = laptop.call('/api/login', {'password': 'correct-horse'})
        check('a remembered device signs in with the password alone', st == 200 and r.get('ok') and not r.get('mfa') and laptop.authed())
        # a recovery code works once
        t3 = other.call('/api/login', {'password': 'correct-horse'})[1]['ticket']
        st, r = other.call('/api/login/mfa/verify', {'ticket': t3, 'method': 'recovery', 'code': recovery[0], 'remember': False})
        check('a recovery code signs in', st == 200 and other.authed())
        t4 = Client(base).call('/api/login', {'password': 'correct-horse'})[1]['ticket']
        check('...and only once', Client(base).call('/api/login/mfa/verify', {'ticket': t4, 'method': 'recovery', 'code': recovery[0]})[0] in (401, 400))
        # devices: un-remember → next sign-in needs the second factor again
        devs = phone.call('/api/sessions/list')[1]['devices']
        lap = next(d for d in devs if 'Edge' in (d['name'] or ''))
        check('the not remembered device is marked so', next(d for d in devs if 'Chrome' in (d['name'] or '')).get('trusted') is False)
        phone.call('/api/sessions/trust', {'id': lap['id'], 'trusted': False})
        laptop.cookies.pop('rl_session')
        st, r = laptop.call('/api/login', {'password': 'correct-horse'})
        check('after «don\'t remember» the second factor is asked again', r.get('mfa') is True)
        # revoke
        st, r = phone.call('/api/sessions/revoke', {'id': lap['id']})
        check('revoke: the device is gone from the list', all(d['id'] != lap['id'] for d in phone.call('/api/sessions/list')[1]['devices']))
        st, r = phone.call('/api/sessions/others')
        check('sign out everywhere except this one', st == 200 and phone.authed() and not other.authed() and len(phone.call('/api/sessions/list')[1]['devices']) == 1)
        # brute force: the password and the codes share one counter
        brute = Client(base, ip='10.9.9.9')                  # its own address: the lock-out must not catch the other clients
        tk = brute.call('/api/login', {'password': 'correct-horse'})[1]['ticket']
        codes = [brute.call('/api/login/mfa/verify', {'ticket': tk, 'method': 'totp', 'code': f'{i:06d}'})[0] for i in range(7)]
        check('guessing codes is stopped', 429 in codes or 400 in codes[4:], codes)
        # switching it off needs the password
        check('switching protection off needs the password', phone.call('/api/mfa/enable', {'enabled': False})[0] == 403)
        st, _ = phone.call('/api/mfa/enable', {'enabled': False, 'password': 'correct-horse'})
        check('...and then it does', st == 200 and not phone.call('/api/mfa/status')[1]['enabled'])
        st, r = Client(base).call('/api/login', {'password': 'correct-horse'})
        check('with protection off a sign-in is a plain session again', st == 200 and not r.get('mfa'))
        # password change signs everybody else out
        extra = Client(base)
        extra.call('/api/login', {'password': 'correct-horse'})
        st, _ = phone.call('/api/settings', {'oldPassword': 'correct-horse', 'newPassword': 'new-password-9'}, 'PUT')
        check('changing the password signs the other devices out', st == 200 and phone.authed() and not extra.authed())
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
        shutil.rmtree(data, ignore_errors=True)


if __name__ == '__main__':
    print('sessions'); sessions_unit()
    print('totp'); totp_unit()
    print('e-mail / SMS / Telegram'); mfa_unit()
    print('server'); server_flow()
    print('\nВСЁ OK' if not FAILS else f'\nПРОВАЛЕНО: {len(FAILS)}: {FAILS}')
    sys.exit(1 if FAILS else 0)
