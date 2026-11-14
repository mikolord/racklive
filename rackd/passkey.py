"""Вход по Face ID / Touch ID / Windows Hello — ключи входа (WebAuthn, passkeys), only the Python standard library.

The face (or finger) never reaches Rack Live: the phone checks it itself and then signs our one-time challenge with a key that lives
in its secure chip. Rack Live keeps only the public half of that key and checks the signature (ECDSA P-256 «ES256» or RSA «RS256»).
A photo can't pass, and a copy of config.json can't sign in. Keys are bound to the address (rpId = the domain the page is opened on);
browsers allow them only on https (or localhost), never on a bare IP.

cfg['passkeys'] = {'login': bool, 'vault': bool, 'keys': [{id, name, rpId, kty, alg, x, y | n, e, created, last, count}]}
— never in a backup file, never replaced by a restore (store.NEVER_EXPORTED / KEPT_ON_IMPORT).
"""
import base64, hashlib, json, re, secrets, threading, time, urllib.parse

CHALLENGE_TTL = 180
MAX_KEYS = 30


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def unb64u(s):
    if not isinstance(s, str) or len(s) > 20000 or not re.fullmatch(r'[A-Za-z0-9_\-]*={0,2}', s):
        raise ValueError('повреждённые данные ключа')
    s = s.rstrip('=')
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


# ── CBOR (RFC 8949): only what WebAuthn uses — definite lengths ──
def cbor(data, i=0):
    if i >= len(data):
        raise ValueError('CBOR: неожиданный конец')
    ib = data[i]
    mt, ai = ib >> 5, ib & 31
    i += 1
    if ai < 24:
        val = ai
    elif ai in (24, 25, 26, 27):
        n = 1 << (ai - 24)
        if i + n > len(data):
            raise ValueError('CBOR: неожиданный конец')
        val = int.from_bytes(data[i:i + n], 'big')
        i += n
    else:
        raise ValueError('CBOR: неподдерживаемая длина')
    if mt == 0:
        return val, i
    if mt == 1:
        return -1 - val, i
    if mt in (2, 3):
        if i + val > len(data):
            raise ValueError('CBOR: неожиданный конец')
        b = data[i:i + val]
        return (bytes(b) if mt == 2 else b.decode('utf-8')), i + val
    if mt == 4:
        out = []
        for _ in range(val):
            v, i = cbor(data, i)
            out.append(v)
        return out, i
    if mt == 5:
        out = {}
        for _ in range(val):
            k, i = cbor(data, i)
            v, i = cbor(data, i)
            out[k] = v
        return out, i
    if mt == 6:                                  # a tag: the value under it
        return cbor(data, i)
    if mt == 7:
        return {20: False, 21: True, 22: None}.get(ai, None), i
    raise ValueError('CBOR: неизвестный тип')


# ── P-256 ──
P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
A = P - 3
B = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296, 0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)


def _on_curve(pt):
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


# Jacobian coordinates: no inverse per step
def _jdbl(p):
    x, y, z = p
    if not y or not z:
        return (0, 1, 0)
    yy = y * y % P
    s = 4 * x * yy % P
    zz = z * z % P
    m = 3 * (x - zz) * (x + zz) % P
    x3 = (m * m - 2 * s) % P
    return (x3, (m * (s - x3) - 8 * yy * yy) % P, 2 * y * z % P)


def _jadd(p, q):
    if not p[2]:
        return q
    if not q[2]:
        return p
    x1, y1, z1 = p
    x2, y2, z2 = q
    z1z1, z2z2 = z1 * z1 % P, z2 * z2 % P
    u1, u2 = x1 * z2z2 % P, x2 * z1z1 % P
    s1, s2 = y1 * z2 * z2z2 % P, y2 * z1 * z1z1 % P
    if u1 == u2:
        return _jdbl(p) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % P, (s2 - s1) % P
    hh = h * h % P
    hhh = h * hh % P
    v = u1 * hh % P
    x3 = (r * r - hhh - 2 * v) % P
    return (x3, (r * (v - x3) - s1 * hhh) % P, h * z1 * z2 % P)


def _mul2(u1, p1, u2, p2):
    """u1·p1 + u2·p2 (Shamir's trick) → affine or None"""
    j1, j2 = (p1[0], p1[1], 1), (p2[0], p2[1], 1)
    j12 = _jadd(j1, j2)
    r = (0, 1, 0)
    for bit in range(max(u1.bit_length(), u2.bit_length()) - 1, -1, -1):
        r = _jdbl(r)
        b1, b2 = (u1 >> bit) & 1, (u2 >> bit) & 1
        if b1 and b2:
            r = _jadd(r, j12)
        elif b1:
            r = _jadd(r, j1)
        elif b2:
            r = _jadd(r, j2)
    if not r[2]:
        return None
    zi = pow(r[2], -1, P)
    return (r[0] * zi * zi % P, r[1] * zi * zi * zi % P)


def _der_sig(sig):
    """ASN.1 DER ECDSA signature → (r, s)"""
    def ln(i):
        n = sig[i]
        if n < 0x80:
            return n, i + 1
        k = n & 0x7f
        if k < 1 or k > 2:
            raise ValueError
        return int.from_bytes(sig[i + 1:i + 1 + k], 'big'), i + 1 + k
    try:
        if sig[0] != 0x30:
            raise ValueError
        total, i = ln(1)
        if i + total != len(sig):
            raise ValueError
        out = []
        for _ in range(2):
            if sig[i] != 0x02:
                raise ValueError
            n, i = ln(i + 1)
            out.append(int.from_bytes(sig[i:i + n], 'big'))
            i += n
        if i != len(sig):
            raise ValueError
        return out[0], out[1]
    except (IndexError, ValueError):
        raise ValueError('неверная подпись')


def verify_es256(x, y, msg, sig):
    q = (int.from_bytes(x, 'big'), int.from_bytes(y, 'big'))
    if len(x) != 32 or len(y) != 32 or not _on_curve(q):
        return False
    try:
        r, s = _der_sig(sig)
    except ValueError:
        return False
    if not (1 <= r < N and 1 <= s < N):
        return False
    e = int.from_bytes(hashlib.sha256(msg).digest(), 'big')
    w = pow(s, -1, N)
    pt = _mul2(e * w % N, G, r * w % N, q)
    return pt is not None and pt[0] % N == r


SHA256_INFO = bytes.fromhex('3031300d060960864801650304020105000420')


def verify_rs256(n, e, msg, sig):
    n, e = int.from_bytes(n, 'big'), int.from_bytes(e, 'big')
    k = (n.bit_length() + 7) // 8
    if n.bit_length() < 2048 or len(sig) != k:
        return False
    em = pow(int.from_bytes(sig, 'big'), e, n).to_bytes(k, 'big')
    want = b'\x00\x01' + b'\xff' * (k - 3 - len(SHA256_INFO) - 32) + b'\x00' + SHA256_INFO + hashlib.sha256(msg).digest()
    return secrets.compare_digest(em, want)


# ── WebAuthn ──
def parse_auth_data(ad):
    if len(ad) < 37:
        raise ValueError('слишком короткие данные ключа')
    out = {'rpIdHash': ad[:32], 'flags': ad[32], 'count': int.from_bytes(ad[33:37], 'big')}
    if out['flags'] & 0x40:                      # AT: a new credential is inside
        i = 37
        if len(ad) < i + 18:
            raise ValueError('повреждены данные нового ключа')
        ln = int.from_bytes(ad[i + 16:i + 18], 'big')
        cid = ad[i + 18:i + 18 + ln]
        if len(cid) != ln or not ln:
            raise ValueError('повреждены данные нового ключа')
        key, _ = cbor(ad, i + 18 + ln)
        out.update(aaguid=ad[i:i + 16].hex(), credId=cid, cose=key)
    return out


def cose_key(k):
    if not isinstance(k, dict):
        raise ValueError('неизвестный формат ключа')
    kty, alg = k.get(1), k.get(3)
    if kty == 2 and alg == -7 and k.get(-1) == 1 and isinstance(k.get(-2), bytes) and isinstance(k.get(-3), bytes):
        if not _on_curve((int.from_bytes(k[-2], 'big'), int.from_bytes(k[-3], 'big'))):
            raise ValueError('ключ не на кривой P-256')
        return {'kty': 'EC2', 'alg': -7, 'x': b64u(k[-2]), 'y': b64u(k[-3])}
    if kty == 3 and alg == -257 and isinstance(k.get(-1), bytes) and isinstance(k.get(-2), bytes):
        return {'kty': 'RSA', 'alg': -257, 'n': b64u(k[-1]), 'e': b64u(k[-2])}
    raise ValueError('этот тип ключа не поддерживается (нужен ES256 или RS256)')


def check_signature(key, msg, sig):
    if key.get('kty') == 'EC2':
        return verify_es256(unb64u(key['x']), unb64u(key['y']), msg, sig)
    if key.get('kty') == 'RSA':
        return verify_rs256(unb64u(key['n']), unb64u(key['e']), msg, sig)
    return False


def valid_rp(rp):
    """a domain name (WebAuthn never allows an IP address)"""
    rp = (rp or '').strip().lower()
    if rp == 'localhost':
        return rp
    if not re.fullmatch(r'(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}', rp):
        return ''
    return rp


def _origin_ok(origin, rp):
    try:
        u = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    host = (u.hostname or '').lower()
    if u.scheme == 'http':
        return host == 'localhost' and rp == 'localhost'
    return u.scheme == 'https' and (host == rp or host.endswith('.' + rp))


class Challenges:
    """one-time challenges in memory: value → (expiry, kind, rpId)"""
    def __init__(self):
        self.c = {}
        self.lock = threading.Lock()

    def new(self, kind, rp):
        ch = b64u(secrets.token_bytes(32))
        with self.lock:
            now = time.time()
            if len(self.c) > 1000:
                self.c = {k: v for k, v in self.c.items() if v[0] > now}
            if len(self.c) > 1000:
                raise ValueError('слишком много запросов, попробуйте через минуту')
            self.c[ch] = (now + CHALLENGE_TTL, kind, rp)
        return ch

    def take(self, ch, kind):
        with self.lock:
            v = self.c.pop(ch or '', None)
        if not v or v[0] < time.time() or v[1] != kind:
            raise ValueError('запрос устарел — попробуйте ещё раз')
        return v[2]


def _client_data(raw_b64, kind, challenges):
    raw = unb64u(raw_b64)
    try:
        cd = json.loads(raw)
    except ValueError:
        raise ValueError('повреждены данные ключа')
    if cd.get('type') != ('webauthn.create' if kind == 'register' else 'webauthn.get'):
        raise ValueError('неверный тип запроса')
    rp = challenges.take(cd.get('challenge'), kind)
    if not _origin_ok(cd.get('origin') or '', rp):
        raise ValueError('ключ создан для другого адреса')
    return raw, rp


def register(body, challenges, keys, name):
    """the answer of navigator.credentials.create() → a key record (raises ValueError)"""
    raw_cd, rp = _client_data(body.get('clientDataJSON'), 'register', challenges)
    att, _ = cbor(unb64u(body.get('attestationObject')))
    if not isinstance(att, dict) or not isinstance(att.get('authData'), bytes):
        raise ValueError('повреждены данные ключа')
    ad = parse_auth_data(att['authData'])
    if ad['rpIdHash'] != hashlib.sha256(rp.encode()).digest():
        raise ValueError('ключ создан для другого адреса')
    if not (ad['flags'] & 0x01) or not (ad['flags'] & 0x04):
        raise ValueError('телефон не подтвердил владельца (Face ID / код)')
    if 'credId' not in ad:
        raise ValueError('в ответе нет нового ключа')
    cid = b64u(ad['credId'])
    if any(k['id'] == cid for k in keys):
        raise ValueError('этот ключ уже добавлен')
    if len(keys) >= MAX_KEYS:
        raise ValueError(f'ключей уже {MAX_KEYS} — удалите ненужные')
    rec = dict(cose_key(ad['cose']), id=cid, name=(name or 'Устройство').strip()[:60], rpId=rp, created=int(time.time()), last=0,
               count=ad['count'], aaguid=ad.get('aaguid', ''))
    return rec


def assert_ok(body, challenges, keys):
    """the answer of navigator.credentials.get() → the key that signed (raises ValueError). Updates last / count."""
    raw_cd, rp = _client_data(body.get('clientDataJSON'), 'get', challenges)
    key = next((k for k in keys if k['id'] == body.get('id')), None)
    if not key:
        raise ValueError('этот ключ не зарегистрирован в Rack Live (или был удалён)')
    if key.get('rpId') != rp:
        raise ValueError('ключ создан для другого адреса Rack Live')
    adb = unb64u(body.get('authenticatorData'))
    ad = parse_auth_data(adb)
    if ad['rpIdHash'] != hashlib.sha256(rp.encode()).digest():
        raise ValueError('ключ создан для другого адреса')
    if not (ad['flags'] & 0x01) or not (ad['flags'] & 0x04):
        raise ValueError('телефон не подтвердил владельца (Face ID / код)')
    if not check_signature(key, adb + hashlib.sha256(raw_cd).digest(), unb64u(body.get('signature'))):
        raise ValueError('подпись не сошлась')
    if ad['count'] and key.get('count') and ad['count'] <= key['count']:
        raise ValueError('ключ похож на копию (счётчик не вырос) — удалите его и добавьте заново')
    key['count'] = ad['count']
    key['last'] = int(time.time())
    return key


def public(keys):
    return [{k: v for k, v in x.items() if k in ('id', 'name', 'rpId', 'created', 'last')} for x in keys]
