"""Single administrator password (PBKDF2), devices + cookie sessions, login rate limit.

A device is a browser / phone that signed in. It is either remembered (the session lives SESSION_DAYS, slides with use, and the device
skips the second factor for TRUST_DAYS) or not remembered (the session ends after IDLE_MIN of silence or ABS_HOURS in total, and the next
sign-in asks for the second factor again). Revoking a device deletes its sessions and its trust — it can only come back with password +
second factor. Tokens are stored only as hashes."""
import hashlib, hmac, json, os, secrets, threading, time

ITER = 200_000
SESSION_DAYS = 30           # remembered device: idle limit of a session
TRUST_DAYS = 90             # remembered device: how long it may skip the second factor
IDLE_MIN = 60               # not remembered: session ends after this many minutes of silence
ABS_HOURS = 12              # ...and never lives longer than this
SAVE_EVERY = 60             # write sessions.json at most this often when only «last seen» changed


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), ITER).hex()
    return {'salt': salt, 'hash': h, 'iter': ITER}


def check_password(rec, pw):
    if not rec:
        return False
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), rec['salt'].encode(), rec.get('iter', ITER)).hex()
    return hmac.compare_digest(h, rec['hash'])


def device_name(ua):
    """«iPhone · Safari» from a User-Agent"""
    ua = ua or ''
    os_ = next((n for k, n in (('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Android', 'Android'), ('CrOS', 'Chromebook'), ('Windows', 'Windows'),
                               ('Macintosh', 'Mac'), ('Mac OS X', 'Mac'), ('Linux', 'Linux')) if k in ua), '')
    br = next((n for k, n in (('Telegram', 'Telegram'), ('YaBrowser', 'Яндекс Браузер'), ('Edg', 'Edge'), ('OPR', 'Opera'), ('FxiOS', 'Firefox'), ('Firefox', 'Firefox'),
                              ('CriOS', 'Chrome'), ('Chrome', 'Chrome'), ('Safari', 'Safari')) if k in ua), '')
    return ' · '.join(x for x in (os_, br) if x) or 'Неизвестное устройство'


def _h(tok):
    return hashlib.sha256((tok or '').encode()).hexdigest()


class Sessions:
    def __init__(self, data_dir, policy=None):
        self.path = os.path.join(data_dir, 'sessions.json')
        self.lock = threading.RLock()
        self.fails = {}
        self.policy = policy or (lambda: {})
        self.saved = 0
        self.d = {'v': 2, 'devices': {}, 'sessions': {}}
        try:
            with open(self.path) as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        if raw.get('v') == 2:
            self.d = raw
        else:                                       # older file: {token: expiry}; those people were signed in for 30 days — keep them as remembered devices
            now = time.time()
            for tok, exp in raw.items():
                if isinstance(exp, (int, float)) and exp > now:
                    did = secrets.token_hex(6)
                    self.d['devices'][did] = {'id': did, 'name': 'Прежний вход', 'ua': '', 'ip': '', 'created': now, 'last': now, 'trusted': True,
                                              'trust_until': now + TRUST_DAYS * 86400, 'dtok': '', 'via': 'password'}
                    self.d['sessions'][_h(tok)] = {'dev': did, 'exp': exp, 'abs': None}
            self._save()
        self._prune()

    # ── policy (Настройки → Доступ) ──
    def p(self, key, default):
        try:
            v = float(self.policy().get(key))
            return v if v > 0 else default
        except (TypeError, ValueError, AttributeError):
            return default

    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.d, f)
        os.replace(tmp, self.path)
        self.saved = time.time()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _prune(self):
        now = time.time()
        with self.lock:
            s = self.d['sessions']
            for k in [k for k, v in s.items() if v['exp'] <= now or (v.get('abs') and v['abs'] <= now)]:
                del s[k]
            live = {v['dev'] for v in s.values()}
            for did in [i for i, v in self.d['devices'].items() if i not in live and not (v.get('trusted') and v.get('trust_until', 0) > now)]:
                del self.d['devices'][did]

    # ── sign in / out ──
    def create(self, ip='', ua='', remember=True, dtok=None, via='password'):
        """→ (session token, device token). A known device (its cookie) keeps its record; otherwise a new one appears."""
        tok, dev_tok = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        now = time.time()
        with self.lock:
            self._prune()
            dev = next((v for v in self.d['devices'].values() if dtok and v.get('dtok') and hmac.compare_digest(v['dtok'], _h(dtok))), None)
            new = dev is None
            if new:
                did = secrets.token_hex(6)
                dev = self.d['devices'][did] = {'id': did, 'created': now}
            dev.update(name=device_name(ua), ua=(ua or '')[:200], ip=ip, last=now, trusted=bool(remember), via=via, dtok=_h(dev_tok),
                       trust_until=now + self.p('trustDays', TRUST_DAYS) * 86400 if remember else 0)
            self.d['sessions'][_h(tok)] = {'dev': dev['id'], 'created': now, 'abs': None if remember else now + ABS_HOURS * 3600,
                                           'exp': now + (self.p('sessionDays', SESSION_DAYS) * 86400 if remember else self.p('idleMin', IDLE_MIN) * 60)}
            self._save()
        return tok, dev_tok, new, dev['id']

    def trusted_device(self, dtok):
        """the remembered device this cookie belongs to (it may skip the second factor), or None"""
        if not dtok:
            return None
        now = time.time()
        with self.lock:
            for v in self.d['devices'].values():
                if v.get('trusted') and v.get('trust_until', 0) > now and v.get('dtok') and hmac.compare_digest(v['dtok'], _h(dtok)):
                    return dict(v)
        return None

    def valid(self, tok, ip='', ua=''):
        if not tok:
            return False
        now = time.time()
        with self.lock:
            s = self.d['sessions'].get(_h(tok))
            if not s or s['exp'] <= now or (s.get('abs') and s['abs'] <= now):
                return False
            dev = self.d['devices'].get(s['dev'])
            if not dev:
                return False
            if ua and (not dev.get('ua') or dev.get('name') == 'Прежний вход'):      # a device carried over from the old sessions file: name it now
                dev.update(name=device_name(ua), ua=ua[:200])
                self.saved = 0
            if ip and dev.get('ip') != ip:
                dev['ip'] = ip
                self.saved = 0 if not dev.get('ip') else self.saved
            window = self.p('sessionDays', SESSION_DAYS) * 86400 if dev.get('trusted') else self.p('idleMin', IDLE_MIN) * 60
            new_exp = min(now + window, s['abs']) if s.get('abs') else now + window
            if new_exp > s['exp'] + 1:                 # sliding: activity pushes the end of the session away
                s['exp'] = new_exp
            if now - dev.get('last', 0) > 30:
                dev['last'] = now
                if now - self.saved > SAVE_EVERY:
                    self._save()
            return True

    def device_of(self, tok):
        with self.lock:
            s = self.d['sessions'].get(_h(tok))
            return s['dev'] if s else None

    def drop(self, tok):
        with self.lock:
            s = self.d['sessions'].pop(_h(tok), None)
            if s:
                dev = self.d['devices'].get(s['dev'])
                if dev and not dev.get('trusted') and not any(v['dev'] == dev['id'] for v in self.d['sessions'].values()):
                    del self.d['devices'][dev['id']]
            self._save()

    def drop_all(self):
        with self.lock:
            self.d = {'v': 2, 'devices': {}, 'sessions': {}}
            self._save()

    # ── the list in Настройки → Доступ ──
    def devices(self, cur_tok):
        cur = self.device_of(cur_tok)
        now = time.time()
        with self.lock:
            self._prune()
            out = []
            for v in self.d['devices'].values():
                ss = [s for s in self.d['sessions'].values() if s['dev'] == v['id']]
                out.append({'id': v['id'], 'name': v.get('name'), 'ip': v.get('ip'), 'created': v.get('created'), 'last': v.get('last'), 'trusted': bool(v.get('trusted')),
                            'trustUntil': v.get('trust_until') if v.get('trusted') else None, 'via': v.get('via'), 'current': v['id'] == cur,
                            'signedIn': bool(ss), 'endsAt': max((s['exp'] for s in ss), default=None)})
            return sorted(out, key=lambda x: (not x['current'], -(x['last'] or 0)))

    def revoke(self, dev_id):
        with self.lock:
            self.d['devices'].pop(dev_id, None)
            self.d['sessions'] = {k: v for k, v in self.d['sessions'].items() if v['dev'] != dev_id}
            self._save()

    def revoke_others(self, keep_dev):
        with self.lock:
            self.d['devices'] = {k: v for k, v in self.d['devices'].items() if k == keep_dev}
            self.d['sessions'] = {k: v for k, v in self.d['sessions'].items() if v['dev'] == keep_dev}
            self._save()

    def set_trusted(self, dev_id, trusted):
        """un-remember: its sessions shrink to the short kind and the next sign-in asks for the second factor"""
        now = time.time()
        with self.lock:
            dev = self.d['devices'].get(dev_id)
            if not dev:
                return False
            dev['trusted'] = bool(trusted)
            dev['trust_until'] = now + self.p('trustDays', TRUST_DAYS) * 86400 if trusted else 0
            for s in self.d['sessions'].values():
                if s['dev'] == dev_id and not trusted:
                    s['abs'] = s.get('abs') or now + ABS_HOURS * 3600
                    s['exp'] = min(s['exp'], now + self.p('idleMin', IDLE_MIN) * 60)
                elif s['dev'] == dev_id:
                    s['abs'] = None
                    s['exp'] = now + self.p('sessionDays', SESSION_DAYS) * 86400
            self._save()
            return True

    # ── brute force: shared by the password and every second-factor attempt ──
    def throttled(self, ip):
        n, t = self.fails.get(ip, (0, 0))
        return n >= 5 and time.time() - t < 300

    def fail(self, ip):
        n, t = self.fails.get(ip, (0, 0))
        self.fails[ip] = (n + 1 if time.time() - t < 300 else 1, time.time())

    def ok(self, ip):
        self.fails.pop(ip, None)
