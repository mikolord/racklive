"""The control channel between a main Rack Live and a site collector (rackd/sites.py, rackd/collector.py).

The COLLECTOR dials out (WebSocket over the same HTTPS address it already reports to), so nothing is opened at the remote place. Over this one connection the main installation
can ask the collector to do things with ITS OWN drivers and ITS OWN saved passwords: read a device's full state, press a driver button, open a terminal on a device.
Passwords never travel; the owner of the collector chooses what is allowed (off / look / actions / terminal) and every use is written to both journals.

Messages are JSON text frames:   centre → site:  {t:'req', id, op, args}  ·  {t:'term_open', s, dev, cols, rows}  ·  {t:'term', s, d: base64}  ·  {t:'term_resize', s, cols, rows}  ·  {t:'term_close', s}  ·  {t:'pong'}
                                 site → centre:  {t:'hello', version, level}  ·  {t:'res', id, result | error}  ·  {t:'term', s, d: base64}  ·  {t:'termx', s, why}  ·  {t:'ping'}"""
import base64, hashlib, json, os, queue, select, socket, ssl, struct, threading, time, urllib.parse

from . import terminal

HELLO_WAIT = 90          # the centre drops a link that was silent this long (the site pings every 25 s)


def client_frame(payload, opcode=1):
    """a client → server WebSocket frame (RFC 6455: client frames must be masked)"""
    n = len(payload)
    head = bytes([0x80 | opcode])
    mask = os.urandom(4)
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack('>H', n)
    else:
        head += bytes([0x80 | 127]) + struct.pack('>Q', n)
    if n:
        masked = (int.from_bytes(payload, 'big') ^ int.from_bytes((mask * (n // 4 + 1))[:n], 'big')).to_bytes(n, 'big')
    else:
        masked = b''
    return head + mask + masked


def connect(url, token, insecure=False, timeout=20):
    """open the WebSocket to <url>/api/site/link with the site key → (socket, bytes that came after the handshake)"""
    u = urllib.parse.urlparse(url)
    tls = u.scheme == 'https'
    host, port = u.hostname, u.port or (443 if tls else 80)
    s = socket.create_connection((host, port), timeout)
    if tls:
        ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    path = (u.path.rstrip('/') or '') + '/api/site/link'
    s.sendall((f'GET {path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n'
               f'Authorization: Bearer {token}\r\nUser-Agent: RackLive-collector\r\n\r\n').encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = s.recv(4096)
        if not chunk or len(buf) > 16384:
            raise ConnectionError('главная установка закрыла соединение')
        buf += chunk
    head, _, rest = buf.partition(b'\r\n\r\n')
    status = head.split(b'\r\n')[0].decode('latin-1')
    if ' 101 ' not in status + ' ':
        raise ConnectionError('ключ отклонён' if ' 401 ' in status else f'главная установка ответила: {status[:60]}')
    if terminal.accept_key(key) not in head.decode('latin-1'):
        raise ConnectionError('ответ главной установки не похож на WebSocket')
    s.settimeout(None)
    return s, rest


class Link:
    """the centre's end of one site's channel (lives in the handler thread of the connection)"""
    def __init__(self, conn, site):
        self.conn, self.site = conn, site
        self.out = queue.Queue()
        self.pending, self.streams = {}, {}
        self.caps = {}
        self.last = time.time()
        self.dead = False
        self.n = 0
        self.lock = threading.Lock()

    def send(self, obj):
        if not self.dead:
            self.out.put(json.dumps(obj, ensure_ascii=False).encode())

    def request(self, op, args=None, timeout=25):
        with self.lock:
            self.n += 1
            rid = self.n
        ev = threading.Event()
        self.pending[rid] = [ev, None]
        self.send({'t': 'req', 'id': rid, 'op': op, 'args': args or {}})
        if not ev.wait(timeout):
            self.pending.pop(rid, None)
            raise TimeoutError('площадка не ответила вовремя')
        res = self.pending.pop(rid)[1] or {}
        if res.get('error'):
            raise RuntimeError(res['error'])
        return res.get('result')

    def open_stream(self, dev, cols, rows):
        sid = os.urandom(4).hex()
        q = queue.Queue()
        self.streams[sid] = q
        self.send({'t': 'term_open', 's': sid, 'dev': dev, 'cols': cols, 'rows': rows})
        return sid, q

    def close_stream(self, sid):
        self.streams.pop(sid, None)
        self.send({'t': 'term_close', 's': sid})

    def _handle(self, m):
        t = m.get('t')
        if t == 'hello':
            self.caps = {'level': m.get('level'), 'version': m.get('version')}
        elif t == 'ping':
            self.send({'t': 'pong'})
        elif t == 'res':
            p = self.pending.get(m.get('id'))
            if p:
                p[1] = m
                p[0].set()
        elif t in ('term', 'termx'):
            q = self.streams.get(m.get('s'))
            if q:
                q.put(m)

    def run(self):
        """until the site hangs up, goes silent or the centre drops it"""
        rd = terminal.Reader()
        conn = self.conn
        conn.settimeout(None)
        try:
            while not self.dead:
                try:
                    while True:
                        conn.sendall(terminal.frame(self.out.get_nowait(), 1))
                except queue.Empty:
                    pass
                r, _, _ = select.select([conn], [], [], 0.25)
                if r:
                    data = conn.recv(65536)
                    if not data:
                        break
                    for op, payload in rd.feed(data):
                        if op == 8:
                            return
                        if op == 9:
                            conn.sendall(terminal.frame(payload, 10))
                        elif op in (1, 2):
                            self.last = time.time()
                            try:
                                self._handle(json.loads(payload))
                            except ValueError:
                                pass
                if time.time() - self.last > HELLO_WAIT:
                    break
        except (OSError, ValueError):
            pass
        finally:
            self.dead = True
            for p in list(self.pending.values()):
                p[1] = {'error': 'канал с площадкой закрыт'}
                p[0].set()
            for q in list(self.streams.values()):
                q.put({'t': 'termx', 'why': 'канал с площадкой закрыт'})
