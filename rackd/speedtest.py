"""Speed tests: from the browser to Rack Live (Wi-Fi coverage) and iperf3 between Rack Live and a device.

The browser test needs no app: the page downloads incompressible bytes from /api/speedtest/down and uploads
to /api/speedtest/up. Who is testing (which access point, band, signal) is looked up by the client's IP
in the routers' client lists — that only works when the container sees real addresses (network_mode: host).
"""
import ipaddress, json, os, re, secrets, shutil, subprocess, threading, time

CHUNK = os.urandom(1 << 20)          # random → gzip / Wi-Fi compression can't cheat
MAX_BYTES = 256 << 20                # one download/upload request is capped
KEEP = 300


class SpeedTests:
    def __init__(self, store):
        self.store = store
        self.items = store._load('speedtests.json', [])
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(8)    # parallel streams of one test (the page opens 4)

    def _save(self):
        self.store._dump('speedtests.json', self.items[-KEEP:])
        self.store.bump()

    def add(self, rec):
        rec = dict(rec, id='s' + secrets.token_hex(4), t=rec.get('t') or time.time())
        with self.lock:
            self.items.append(rec)
            self.items = self.items[-KEEP:]
            self._save()
        return rec

    def update(self, sid, fields):
        with self.lock:
            r = next((x for x in self.items if x['id'] == sid), None)
            if not r:
                return None
            for k in ('where', 'note'):
                if k in fields:
                    r[k] = fields[k]
            self._save()
            return r

    def delete(self, sid):
        with self.lock:
            self.items = [x for x in self.items if x['id'] != sid]
            self._save()

    def public(self):
        return self.items[-KEEP:]


def docker_gateway(ip):
    """172.17.0.1-like addresses: the container sits behind Docker NAT and never sees who connects."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a in ipaddress.ip_network('172.16.0.0/12') and str(a).endswith('.1')


def who(devices, states, ip):
    """Find the connecting browser in the routers' client lists: access point, band, signal, or the switch port."""
    info = {'ip': ip}
    if not ip:
        return info
    # opened through the router's domain name (KeenDNS proxy): every request comes from the router itself, the phone is not visible
    if any(d.get('driver') == 'keenetic' and re.sub(r'^\w+://|[:/].*$', '', d.get('host') or '') == ip for d in devices):
        return dict(info, proxy=True)
    by_id = {d['id']: d for d in devices}
    for did, st in states.items():
        for c in st.get('clients') or []:
            if c.get('ip') != ip:
                continue
            info.update({k: c.get(k) for k in ('name', 'mac', 'segment', 'rssi', 'rate', 'band') if c.get(k) not in (None, '')})
            ap = c.get('ap')
            if ap:
                info['wifi'] = True
                router = (by_id.get(did) or {}).get('name') or 'Роутер'
                info['apName'] = router if ap == 'self' else next((ch.get('name') for ch in st.get('children') or [] if ch.get('key') == ap), ap)
            break
        if 'mac' in info:
            break
    mac = (info.get('mac') or '').lower()
    if mac and not info.get('wifi'):
        for did, st in states.items():
            for p in st.get('ports') or []:
                if p.get('kind') == 'wan' or len(p.get('peers') or []) > 3:      # skip uplinks: everybody is behind them
                    continue
                if any((x.get('mac') or '').lower() == mac for x in p.get('peers') or []):
                    info.update(wired=True, switch=(by_id.get(did) or {}).get('name'), port=p.get('n'), linkSpeed=p.get('speed'))
                    break
            if info.get('wired'):
                break
    if 'mac' not in info and docker_gateway(ip):
        info['nat'] = True
    return info


# ───────── iperf3 (Rack Live ⇄ a device reachable over SSH) ─────────
def iperf_client(host, port, reverse, seconds=5):
    exe = shutil.which('iperf3')
    if not exe:
        raise RuntimeError('в Rack Live нет iperf3 (он есть в Docker-образе; при запуске из исходников установите iperf3)')
    args = [exe, '-c', host, '-p', str(port), '-t', str(seconds), '-J', '-P', '2'] + (['-R'] if reverse else [])
    r = subprocess.run(args, capture_output=True, text=True, timeout=seconds + 25)
    try:
        j = json.loads(r.stdout or '{}')
    except ValueError:
        j = {}
    if j.get('error') or r.returncode:
        raise RuntimeError(j.get('error') or (r.stderr or '').strip()[:200] or f'iperf3: код {r.returncode}')
    end = j.get('end') or {}
    recv = (end.get('sum_received') or {}).get('bits_per_second')
    sent = end.get('sum_sent') or {}
    return {'bps': round(recv or sent.get('bits_per_second') or 0), 'retr': sent.get('retransmits')}
