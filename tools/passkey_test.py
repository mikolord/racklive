"""Face ID / passkeys (rackd/passkey.py): signatures checked against the `cryptography` package (pip install cryptography),
and a whole register → sign-in round with a simulated phone. Run: python tools/passkey_test.py → GOOD"""
import hashlib, json, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import passkey as pk

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
except ImportError:
    print('нужен пакет cryptography для теста (pip install cryptography)')
    sys.exit(1)

ok = True


def check(c, what):
    global ok
    if not c:
        ok = False
        print('FAIL', what)


# ── raw signatures ──
for i in range(25):
    k = ec.generate_private_key(ec.SECP256R1())
    nums = k.public_key().public_numbers()
    x, y = nums.x.to_bytes(32, 'big'), nums.y.to_bytes(32, 'big')
    msg = os.urandom(50 + i)
    sig = k.sign(msg, ec.ECDSA(hashes.SHA256()))
    check(pk.verify_es256(x, y, msg, sig), 'es256 good %d' % i)
    check(not pk.verify_es256(x, y, msg + b'x', sig), 'es256 other message')
    bad = bytearray(sig); bad[-3] ^= 1
    check(not pk.verify_es256(x, y, msg, bytes(bad)), 'es256 broken signature')
check(not pk.verify_es256(b'\x01' * 32, b'\x02' * 32, b'm', sig), 'point not on curve')
check(not pk.verify_es256(x, y, msg, b'\x30\x00'), 'empty DER')

rk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
rn = rk.public_key().public_numbers()
n_b, e_b = rn.n.to_bytes(256, 'big'), rn.e.to_bytes(3, 'big')
rs = rk.sign(b'hello', padding.PKCS1v15(), hashes.SHA256())
check(pk.verify_rs256(n_b, e_b, b'hello', rs), 'rs256 good')
check(not pk.verify_rs256(n_b, e_b, b'hellO', rs), 'rs256 other message')


# ── CBOR encoder for the simulated phone ──
def enc(v):
    def head(mt, n):
        if n < 24: return bytes([mt << 5 | n])
        for ai, fmt in ((24, '>B'), (25, '>H'), (26, '>I'), (27, '>Q')):
            if n < 1 << (8 * struct.calcsize(fmt)): return bytes([mt << 5 | ai]) + struct.pack(fmt, n)
    if isinstance(v, bool): return bytes([0xf5 if v else 0xf4])
    if isinstance(v, int): return head(0, v) if v >= 0 else head(1, -1 - v)
    if isinstance(v, bytes): return head(2, len(v)) + v
    if isinstance(v, str): b = v.encode(); return head(3, len(b)) + b
    if isinstance(v, list): return head(4, len(v)) + b''.join(enc(x) for x in v)
    if isinstance(v, dict): return head(5, len(v)) + b''.join(enc(a) + enc(b) for a, b in v.items())
    raise TypeError(v)


check(pk.cbor(enc({1: 2, 3: -7, -1: 1, 'a': [b'xy', 'z', -300]}))[0] == {1: 2, 3: -7, -1: 1, 'a': [b'xy', 'z', -300]}, 'cbor round trip')


class Phone:
    def __init__(self, rp, origin):
        self.k = ec.generate_private_key(ec.SECP256R1()); self.rp, self.origin = rp, origin
        self.cid = os.urandom(16); self.count = 0

    def create(self, challenge, flags=0x45):
        n = self.k.public_key().public_numbers()
        cose = enc({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, 'big'), -3: n.y.to_bytes(32, 'big')})
        ad = hashlib.sha256(self.rp.encode()).digest() + bytes([flags]) + struct.pack('>I', self.count) + b'\0' * 16 + struct.pack('>H', len(self.cid)) + self.cid + cose
        cd = json.dumps({'type': 'webauthn.create', 'challenge': challenge, 'origin': self.origin}).encode()
        return {'id': pk.b64u(self.cid), 'clientDataJSON': pk.b64u(cd), 'attestationObject': pk.b64u(enc({'fmt': 'none', 'attStmt': {}, 'authData': ad}))}

    def get(self, challenge, flags=0x05, origin=None, count_step=0):
        self.count += count_step
        ad = hashlib.sha256(self.rp.encode()).digest() + bytes([flags]) + struct.pack('>I', self.count)
        cd = json.dumps({'type': 'webauthn.get', 'challenge': challenge, 'origin': origin or self.origin}).encode()
        sig = self.k.sign(ad + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {'id': pk.b64u(self.cid), 'clientDataJSON': pk.b64u(cd), 'authenticatorData': pk.b64u(ad), 'signature': pk.b64u(sig)}


RP = 'racklive.example.net'
ch = pk.Challenges()
phone = Phone(RP, 'https://' + RP)
keys = []
rec = pk.register(phone.create(ch.new('register', RP)), ch, keys, 'iPhone')
keys.append(rec)
check(rec['rpId'] == RP and rec['kty'] == 'EC2' and rec['name'] == 'iPhone', 'registered')


def fails(fn, what):
    try:
        fn()
        check(False, what + ' — accepted')
    except ValueError:
        pass


c1 = ch.new('register', RP)
fails(lambda: pk.register(phone.create(c1), ch, keys, 'x'), 'same key twice')
c = ch.new('get', RP)
k = pk.assert_ok(phone.get(c), ch, keys)
check(k is rec and rec['last'] > 0, 'sign-in')
fails(lambda: pk.assert_ok(phone.get(c), ch, keys), 'challenge reused')
fails(lambda: pk.assert_ok(phone.get('made-up'), ch, keys), 'unknown challenge')
c = ch.new('register', RP)
fails(lambda: pk.assert_ok(phone.get(c), ch, keys), 'register challenge used to sign in')
c = ch.new('get', RP)
fails(lambda: pk.assert_ok(phone.get(c, origin='https://evil.example.org'), ch, keys), 'other origin')
c = ch.new('get', RP)
fails(lambda: pk.assert_ok(phone.get(c, flags=0x01), ch, keys), 'no user verification')
other = Phone(RP, 'https://' + RP)
c = ch.new('get', RP)
a = other.get(c); a['id'] = rec['id']
fails(lambda: pk.assert_ok(a, ch, keys), 'signed by another key')
c = ch.new('get', RP)
fails(lambda: pk.assert_ok(Phone(RP, 'https://' + RP).get(c), ch, keys), 'unknown key')
# counter: grows → fine; goes back → copy
c = ch.new('get', RP); pk.assert_ok(phone.get(c, count_step=5), ch, keys)
c = ch.new('get', RP); phone.count = 3
fails(lambda: pk.assert_ok(phone.get(c), ch, keys), 'counter went back')
# http is refused except localhost
cl = pk.Challenges(); lp = Phone('localhost', 'http://localhost:8080')
check(pk.register(lp.create(cl.new('register', 'localhost')), cl, [], 'pc')['rpId'] == 'localhost', 'localhost over http')
hp = Phone(RP, 'http://' + RP)
c = ch.new('register', RP)
fails(lambda: pk.register(hp.create(c), ch, [], 'x'), 'plain http')
check(pk.valid_rp('Racklive.Example.net') == 'racklive.example.net' and not pk.valid_rp('192.168.1.3') and not pk.valid_rp('a b'), 'rpId check')
check(set(pk.public(keys)[0]) == {'id', 'name', 'rpId', 'created', 'last'}, 'public view has no key material')

print('GOOD' if ok else 'BAD')
sys.exit(0 if ok else 1)
