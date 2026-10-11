"""Single administrator password (PBKDF2) + cookie sessions + login rate limit."""
import hashlib, hmac, json, os, secrets, threading, time

ITER = 200_000
SESSION_DAYS = 30


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), ITER).hex()
    return {'salt': salt, 'hash': h, 'iter': ITER}


def check_password(rec, pw):
    if not rec:
        return False
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), rec['salt'].encode(), rec.get('iter', ITER)).hex()
    return hmac.compare_digest(h, rec['hash'])


class Sessions:
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, 'sessions.json')
        self.lock = threading.Lock()
        self.fails = {}
        try:
            with open(self.path) as f:
                self.s = json.load(f)
        except Exception:
            self.s = {}

    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.s, f)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def create(self):
        tok = secrets.token_urlsafe(32)
        with self.lock:
            now = time.time()
            self.s = {k: v for k, v in self.s.items() if v > now}
            self.s[tok] = now + SESSION_DAYS * 86400
            self._save()
        return tok

    def valid(self, tok):
        return bool(tok) and self.s.get(tok, 0) > time.time()

    def drop(self, tok):
        with self.lock:
            self.s.pop(tok, None)
            self._save()

    def drop_all(self):
        with self.lock:
            self.s = {}
            self._save()

    def throttled(self, ip):
        n, t = self.fails.get(ip, (0, 0))
        return n >= 5 and time.time() - t < 300

    def fail(self, ip):
        n, t = self.fails.get(ip, (0, 0))
        self.fails[ip] = (n + 1 if time.time() - t < 300 else 1, time.time())

    def ok(self, ip):
        self.fails.pop(ip, None)
