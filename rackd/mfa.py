"""Second factor for signing in: password → one more proof.

Methods: totp (code from an authenticator app, RFC 6238), telegram (the bot asks «это вы?»), email (6 digits by mail),
sms (6 digits through the USB modem on an OpenWrt router), recovery (one-time codes, for a lost phone).
A device that was remembered skips the second factor (see auth.py). Everything pending lives in memory for a few minutes."""
import base64, hashlib, hmac, re, secrets, shlex, struct, threading, time

from . import alerts, auth

CODE_TTL = 300              # an e-mail / SMS code lives 5 minutes
TICKET_TTL = 600            # a started sign-in (password already accepted) lives 10 minutes
COOLDOWN = 30               # seconds between two «send the code» for one sign-in
MAX_TRIES = 5               # wrong codes before the sign-in is dropped
LABELS = {'totp': 'Код из приложения', 'telegram': 'Подтвердить в Telegram', 'email': 'Код на почту', 'sms': 'Код по SMS', 'recovery': 'Запасной код'}


# ── TOTP (RFC 6238: HMAC-SHA1, 30 s, 6 digits) ──
def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def _hotp(secret, counter):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8), casefold=True)
    h = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    o = h[-1] & 15
    return f'{(struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1_000_000:06d}'


def totp_now(secret, t=None):
    return _hotp(secret, int((t or time.time()) // 30))


def totp_check(secret, code, last=0, t=None):
    """→ the matching 30-second step (±1 for clock drift) or None; a step already used once is refused (no replay)"""
    code = re.sub(r'\s', '', code or '')
    if not re.fullmatch(r'\d{6}', code):
        return None
    now = int((t or time.time()) // 30)
    for step in (now, now - 1, now + 1):
        if step > last and hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


def otpauth_uri(secret, account, issuer):
    from urllib.parse import quote
    return f'otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30'


# ── recovery codes ──
def new_recovery(n=8):
    plain = [''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(10)) for _ in range(n)]
    return plain, [hashlib.sha256(c.encode()).hexdigest() for c in plain]


def _rc(code):
    return hashlib.sha256(re.sub(r'[\s-]', '', (code or '').lower()).encode()).hexdigest()


def mask_mail(a):
    u, _, d = (a or '').partition('@')
    return (u[:1] + '***' + ('@' + d if d else '')) if u else ''


def mask_phone(p):
    p = re.sub(r'[^\d+]', '', p or '')
    return (p[:2] + ' *** ' + p[-4:]) if len(p) > 6 else p


def clean_phone(p):
    p = re.sub(r'[^\d+]', '', p or '')
    return p if re.fullmatch(r'\+?\d{10,15}', p) else ''


class Mfa:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.lock = threading.Lock()
        self.tickets = {}              # sign-in in progress: ticket -> {ip, ua, t, tries, sent: {method: {h, exp, t, n}}, tg}
        self.setup = {}                # settings: pending e-mail / SMS confirmation and the new TOTP secret
        self.pstarts = {}              # method -> times a code was sent for a sign-in without password

    # ── config ──
    def cfg(self):
        c = self.store.cfg.setdefault('mfa', {})
        c.setdefault('enabled', False)
        c.setdefault('policy', {'idleMin': auth.IDLE_MIN, 'trustDays': auth.TRUST_DAYS, 'sessionDays': auth.SESSION_DAYS})
        return c

    def policy(self):
        return self.cfg()['policy']

    def _site(self):
        return self.store.cfg['settings'].get('title') or 'Rack Live'

    def methods(self, with_recovery=True):
        """what can be used right now: [{id, label, hint}]"""
        c, out = self.cfg(), []
        if (c.get('totp') or {}).get('on'):
            out.append({'id': 'totp', 'label': LABELS['totp'], 'hint': 'шесть цифр из приложения'})
        tg = self.app.tgbot
        if c.get('telegram') and tg.ready() and tg.username and alerts.tg_allowed(tg.tg()):
            out.append({'id': 'telegram', 'label': LABELS['telegram'], 'hint': 'нажмите «Да» в боте'})
        n = alerts.merged(self.store.cfg.get('notify'))['email']
        if (c.get('email') or {}).get('on') and n.get('host'):
            out.append({'id': 'email', 'label': LABELS['email'], 'hint': mask_mail(c['email'].get('to'))})
        if (c.get('sms') or {}).get('on') and self._sms_device(c['sms']):
            out.append({'id': 'sms', 'label': LABELS['sms'], 'hint': mask_phone(c['sms'].get('phone'))})
        if with_recovery and out and c.get('recovery'):
            out.append({'id': 'recovery', 'label': LABELS['recovery'], 'hint': f"осталось {len(c['recovery'])}"})
        return out

    def enabled(self):
        return bool(self.cfg().get('enabled') and self.methods(False))

    def _sms_device(self, s):
        return next((d for d in self.store.cfg['devices'] if d['id'] == s.get('device') and d.get('driver') == 'openwrt'), None)

    # ── sign-in ──
    def begin(self, ip, ua, primary=False):
        """primary: signing in WITHOUT the password, by an app code or a code to the mailbox / phone — a recovery code alone may not finish such a sign-in"""
        t = secrets.token_urlsafe(24)
        now = time.time()
        with self.lock:
            for k in [k for k, v in self.tickets.items() if now - v['t'] > TICKET_TTL]:
                del self.tickets[k]
            self.tickets[t] = {'ip': ip, 'ua': ua, 't': now, 'tries': 0, 'sent': {}, 'tg': None, 'primary': primary}
        return t

    def login_methods(self):
        """ways to sign in without the password (shown on the login screen): a code to the connected mailbox / phone"""
        c = self.cfg()
        if c.get('loginByCode', True) is False:
            return []
        return [m['id'] for m in self.methods(False) if m['id'] in ('totp', 'email', 'sms')]

    def start_primary(self, ip, ua, method):
        """a code is sent to the owner on request of anyone who opens the page — so it is rationed: one per 20 s, four per 10 minutes per method.
        The app code needs nothing sent: the sign-in just waits for the six digits (wrong guesses count against the address as usual)."""
        if method not in self.login_methods():
            raise ValueError('этот способ входа не включён')
        if method == 'totp':
            return self.begin(ip, ua, primary=True), 'введите шесть цифр из приложения'
        now = time.time()
        with self.lock:
            q = self.pstarts.setdefault(method, [])
            q[:] = [x for x in q if now - x < 600]
            if q and now - q[-1] < 20:
                raise ValueError(f'код уже отправлен — повторить можно через {int(20 - (now - q[-1])) + 1} с')
            if len(q) >= 4:
                raise ValueError('слишком много запросов кода — подождите несколько минут')
            q.append(now)
        ticket = self.begin(ip, ua, primary=True)
        return ticket, self.send(ticket, method)

    def _ticket(self, t):
        v = self.tickets.get(t)
        if not v or time.time() - v['t'] > TICKET_TTL:
            raise ValueError('вход устарел — введите пароль заново')
        return v

    def send(self, ticket, method):
        """e-mail / SMS: a code; Telegram: a question in the bot. → hint for the screen"""
        with self.lock:
            v = self._ticket(ticket)
            if method not in [m['id'] for m in self.methods()] or method not in ('email', 'sms', 'telegram'):
                raise ValueError('этот способ не включён')
            last = v['sent'].get(method)
            if last and time.time() - last['t'] < COOLDOWN:
                raise ValueError(f'повторить можно через {int(COOLDOWN - (time.time() - last["t"])) + 1} с')
            if last and last['n'] >= 5:
                raise ValueError('слишком много отправок — войдите заново')
            n = (last['n'] + 1) if last else 1
            if method == 'telegram':
                v['tg'] = self.app.tgbot.ask_mfa(v['ip'], auth.device_name(v['ua']))
                v['sent'][method] = {'t': time.time(), 'n': n}
                return 'вопрос отправлен в Telegram'
            code = f'{secrets.randbelow(1_000_000):06d}'
            v['sent'][method] = {'h': hashlib.sha256(code.encode()).hexdigest(), 'exp': time.time() + CODE_TTL, 't': time.time(), 'n': n}
            where = f"{v['ip']} ({auth.device_name(v['ua'])})"
        c = self.cfg()
        if method == 'email':
            self._send_mail(c['email']['to'], f'{self._site()}: код входа', f'Код входа: {code}\nДействует 5 минут.\n\nВход с адреса {where}. Если это не вы — смените пароль в Rack Live.')
            return 'код отправлен на ' + mask_mail(c['email']['to'])
        self._send_sms(c['sms'], f'{code} — код для входа в {self._site()}')
        return 'код отправлен на ' + mask_phone(c['sms']['phone'])

    def verify(self, ticket, method, code):
        """True / False; five wrong answers end this sign-in"""
        with self.lock:
            v = self._ticket(ticket)
            ok = False
            if v.get('primary') and method not in ('totp', 'email', 'sms'):  # no password was given: a recovery code alone is not enough
                raise ValueError('этот способ не подходит для входа без пароля')
            if method == 'totp':
                t = self.cfg().get('totp') or {}
                if t.get('on'):
                    step = totp_check(t['secret'], code, t.get('last', 0))
                    if step:
                        t['last'] = step
                        self.store.save()
                        ok = True
            elif method == 'recovery':
                r = self.cfg().get('recovery') or []
                h = _rc(code)
                if h in r:
                    r.remove(h)
                    self.store.save()
                    ok = True
            elif method in ('email', 'sms'):
                s = v['sent'].get(method)
                ok = bool(s and time.time() < s['exp'] and hmac.compare_digest(s['h'], hashlib.sha256(re.sub(r'\s', '', code or '').encode()).hexdigest()))
            else:
                raise ValueError('неизвестный способ')
            if not ok:
                v['tries'] += 1
                if v['tries'] >= MAX_TRIES:
                    del self.tickets[ticket]
                    raise ValueError('слишком много неверных кодов — введите пароль заново')
            return ok

    def poll_telegram(self, ticket):
        with self.lock:
            v = self._ticket(ticket)
            code = v.get('tg')
        c = self.app.tgbot.check(code) if code else None
        if not c:
            return 'expired'
        return {'ok': 'ok', 'denied': 'denied'}.get(c['status'], 'wait')

    def finish(self, ticket):
        with self.lock:
            v = self.tickets.pop(ticket, None)
            if v and v.get('tg'):
                self.app.tgbot.consume(v['tg'])
        return v

    # ── senders ──
    def _send_mail(self, to, subject, text):
        n = alerts.merged(self.store.cfg.get('notify'))['email']
        from email.mime.text import MIMEText
        import smtplib, ssl
        if not n.get('host'):
            raise ValueError('почта не настроена: Настройки → Уведомления → Почта')
        msg = MIMEText(text, 'plain', 'utf-8')
        msg['Subject'], msg['From'], msg['To'] = subject, n.get('from') or n.get('user') or 'racklive@localhost', to
        port = int(n.get('port') or 587)
        ctx = ssl.create_default_context()
        s = smtplib.SMTP_SSL(n['host'], port, timeout=20, context=ctx) if port == 465 else smtplib.SMTP(n['host'], port, timeout=20)
        try:
            if port != 465 and n.get('tls', True):
                s.starttls(context=ctx)
            if n.get('user'):
                s.login(n['user'], n.get('password') or '')
            s.sendmail(msg['From'], [to], msg.as_string())
        except (smtplib.SMTPException, OSError) as e:
            raise ValueError(f'почта не отправилась: {e}')
        finally:
            try:
                s.quit()
            except Exception:
                pass

    def _send_sms(self, s, text):
        """through the modem of an OpenWrt router: /usr/bin/zte-sms-send <number> <text>"""
        from .drivers import REGISTRY
        d, phone = self._sms_device(s), clean_phone(s.get('phone'))
        if not d or not phone:
            raise ValueError('SMS не настроены')
        try:
            out = REGISTRY['openwrt'].command(d, f'/usr/bin/zte-sms-send {shlex.quote(phone)} {shlex.quote(text)}')
        except Exception as e:
            raise ValueError(f'SMS не отправились: {e}')
        if re.search(r'not found|No such file|error|ошиб', out or '', re.I):
            raise ValueError('модем не принял SMS: ' + (out or '').strip()[:120])

    # ── setup (admin) ──
    def totp_begin(self):
        s = new_secret()
        with self.lock:
            self.setup['totp'] = {'secret': s, 't': time.time()}
        return {'secret': s, 'uri': otpauth_uri(s, 'admin', self._site())}

    def totp_confirm(self, code):
        with self.lock:
            p = self.setup.get('totp')
            if not p or time.time() - p['t'] > 900:
                raise ValueError('начните заново')
            step = totp_check(p['secret'], code)
            if not step:
                raise ValueError('код не подошёл — проверьте время на телефоне и введите свежий код')
            c = self.cfg()
            c['totp'] = {'on': True, 'secret': p['secret'], 'last': step}
            self.setup.pop('totp', None)
            plain = None
            if not c.get('recovery'):
                plain, c['recovery'] = new_recovery()
            c['enabled'] = True
            self.store.save()
        return plain

    def target_begin(self, method, target, device=None):
        if method == 'email':
            target = (target or '').strip()
            if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', target):
                raise ValueError('введите адрес почты')
        elif method == 'sms':
            target = clean_phone(target)
            if not target:
                raise ValueError('телефон в формате +79881234567')
            if not next((d for d in self.store.cfg['devices'] if d['id'] == device and d.get('driver') == 'openwrt'), None):
                raise ValueError('выберите роутер OpenWrt с модемом')
        else:
            raise ValueError('неизвестный способ')
        code = f'{secrets.randbelow(1_000_000):06d}'
        with self.lock:
            self.setup[method] = {'target': target, 'device': device, 'h': hashlib.sha256(code.encode()).hexdigest(), 'exp': time.time() + CODE_TTL, 'tries': 0}
        if method == 'email':
            self._send_mail(target, f'{self._site()}: подтверждение почты', f'Код подтверждения: {code}\nДействует 5 минут.')
        else:
            self._send_sms({'device': device, 'phone': target}, f'{code} — код подтверждения {self._site()}')
        return mask_mail(target) if method == 'email' else mask_phone(target)

    def target_confirm(self, method, code):
        with self.lock:
            p = self.setup.get(method)
            if not p or time.time() > p['exp']:
                raise ValueError('код устарел — отправьте новый')
            p['tries'] += 1
            if p['tries'] > MAX_TRIES:
                self.setup.pop(method, None)
                raise ValueError('слишком много попыток — отправьте новый код')
            if not hmac.compare_digest(p['h'], hashlib.sha256(re.sub(r'\s', '', code or '').encode()).hexdigest()):
                raise ValueError('код не подошёл')
            c = self.cfg()
            c[method] = {'on': True, 'to' if method == 'email' else 'phone': p['target'], **({'device': p['device']} if method == 'sms' else {})}
            self.setup.pop(method, None)
            if not c.get('recovery'):
                plain, c['recovery'] = new_recovery()
            else:
                plain = None
            c['enabled'] = True
            self.store.save()
        return plain

    def remove(self, method):
        c = self.cfg()
        if method in ('totp', 'email', 'sms'):
            c.pop(method, None)
        elif method == 'telegram':
            c['telegram'] = False
        if not self.methods(False):                  # nothing left to prove it with → the protection switches off by itself
            c['enabled'] = False
            c['recovery'] = []
        self.store.save()

    def recovery_new(self):
        plain, c = new_recovery(), self.cfg()
        c['recovery'] = plain[1]
        self.store.save()
        return plain[0]

    def status(self, tg_ready):
        c = self.cfg()
        return {'enabled': bool(c.get('enabled') and self.methods(False)), 'recovery': len(c.get('recovery') or []), 'loginByCode': c.get('loginByCode', True) is not False,
                'totp': bool((c.get('totp') or {}).get('on')),
                'telegram': {'on': bool(c.get('telegram')), 'available': tg_ready},
                'email': {'on': bool((c.get('email') or {}).get('on')), 'to': mask_mail((c.get('email') or {}).get('to'))},
                'sms': {'on': bool((c.get('sms') or {}).get('on')), 'phone': mask_phone((c.get('sms') or {}).get('phone')), 'device': (c.get('sms') or {}).get('device')},
                'policy': c['policy']}
