"""Small helpers shared by the server and the drivers (standard library only)."""
import json, re, socket, ssl, time, urllib.error, urllib.parse, urllib.request

NOSSL = ssl.create_default_context()
NOSSL.check_hostname = False
NOSSL.verify_mode = ssl.CERT_NONE


class DriverError(Exception):
    """Raised by drivers with a message that is safe to show to the user."""


def http_json(url, data=None, headers=None, method=None, timeout=20, insecure=True, opener=None):
    body = None
    hdrs = dict(headers or {})
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode()
            hdrs.setdefault('Content-Type', 'application/json')
        elif isinstance(data, str):
            body = data.encode()
        else:
            body = data
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    if opener:
        resp = opener.open(req, timeout=timeout)
    else:
        resp = urllib.request.urlopen(req, timeout=timeout, context=NOSSL if insecure else None)
    raw = resp.read()
    return json.loads(raw) if raw else None


def tcp_check(host, port, timeout=3.0):
    t = time.time()
    try:
        with socket.create_connection((host, int(port)), timeout):
            return round((time.time() - t) * 1000, 1)
    except OSError:
        return None


PROMPT = re.compile(rb'(?:[>#]\s*|(?:User ?[Nn]ame|[Ll]ogin|User|Password)\s*:\s*)$')


def telnet_session(host, user, password, commands, wait=1.0, port=23):
    """Log in over telnet (TP-Link/D-Link style prompts) and return {command: output}.
    Each command waits for the next prompt ('#', '>' or a login prompt) instead of a fixed delay,
    so outputs never get mixed up and short commands take a fraction of a second."""
    s = socket.create_connection((host, port), 10)

    def read(max_wait):
        buf = b''
        deadline = time.time() + max_wait
        s.settimeout(0.25)
        while time.time() < deadline:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                if PROMPT.search(buf.rstrip(b'\x00')):
                    break
                continue
            if not chunk:
                break
            out, i = bytearray(), 0
            while i < len(chunk):
                if chunk[i] == 255 and i + 2 < len(chunk):      # IAC negotiation: refuse everything
                    if chunk[i + 1] in (251, 252, 253, 254):
                        s.send(bytes([255, 252 if chunk[i + 1] in (253, 254) else 254, chunk[i + 2]]))
                    i += 3
                    continue
                out.append(chunk[i])
                i += 1
            buf += bytes(out)
            if b'More' in buf[-80:] or b'any key' in buf[-80:]:
                s.send(b' ')
                deadline += 2
        return buf.decode(errors='replace')

    try:
        read(5)
        result = {}
        for c in [user, password] + list(commands):
            s.send((c + '\r\n').encode())
            result[c] = read(max(8, wait * 10) if c.startswith('show') else max(5, wait * 5))
        if 'incorrect' in (result.get(password, '') + result.get(user, '')).lower():
            raise DriverError('неверный логин или пароль')
        return result
    finally:
        s.close()


def parse_ranges(spec):
    out = []
    for part in str(spec).split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            if a.isdigit() and b.isdigit():
                out += list(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def uptime_seconds(v):
    """Accepts seconds, "H:M:S" (Synology) or "N day - H hour - M min - S sec" (TP-Link)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v)
    m = re.match(r'(\d+) day - (\d+) hour - (\d+) min - (\d+) sec', s)
    if m:
        d, h, mi, se = map(int, m.groups())
        return d * 86400 + h * 3600 + mi * 60 + se
    if ':' in s:
        p = [int(x) for x in s.split(':')] + [0, 0]
        return p[0] * 3600 + p[1] * 60 + p[2]
    try:
        return int(float(s))
    except ValueError:
        return None


def guess_kind(name):
    n = (name or '').lower()
    rules = ((('cam', 'камер', 'ipc'), 'camera'), (('ap_', 'orbiter', 'точка', 'access point', 'unifi'), 'ap'),
             (('iphone', 'phone', 'android', 'infinix', 'redmi', 'samsung', 'galaxy', 'pixel', 'xiaomi'), 'phone'),
             (('ipad', 'tablet', 'планшет', 'tab'), 'tablet'), (('tv', 'телевиз', 'bravia'), 'tv'),
             (('nas', 'synology', 'qnap', 'nass'), 'nas'), (('macbook', 'laptop', 'ноут', 'notebook'), 'laptop'),
             (('pc', 'desktop', 'компьютер', 'imac'), 'pc'), (('printer', 'принтер', 'mfp'), 'printer'),
             (('алиса', 'yandex', 'станция', 'echo', 'homepod', 'speaker'), 'speaker'),
             (('homeassist', 'server', 'proxmox', 'esxi'), 'server'), (('switch', 'jetstream', 'коммутатор'), 'switch'),
             (('router', 'cudy', 'wr1300', 'openwrt', 'keenetic', 'mikrotik', 'ab_'), 'router'),
             (('стирал', 'кондиц', 'пылесос', 'lwip', 'esp', 'tuya', 'розетк', 'реле'), 'iot'))
    for keys, kind in rules:
        if any(k in n for k in keys):
            return kind
    return 'other'
