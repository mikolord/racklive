"""Routers among the clients: subscribers', relatives', guest routers that sit behind the main one.

A client looks like a router by its own name (hostname: Cudy WR3000E, Keenetic, TP-Link Archer…) or by the maker of its
network card (MAC prefix). Such candidates get a quick look at their web page (http/https, no login, nothing changed):
does the settings page open from here, is it a Keenetic that could be fully managed. The admin then adds it with one
press (link + login + password in the card) — Rack Live never logs into someone else's router by itself.
Results live in data/routers.json; the check runs at most every 6 hours and on demand.
"""
import concurrent.futures, re, ssl, threading, time, urllib.error, urllib.request

EVERY = 6 * 3600

NAME_RE = re.compile(r'(?i)(cudy|\bwr\d{3,4}[a-z]?\b|\bx\d{1,2}\b|keenetic|netcraze|\bkn-\d|tp-?link|archer|\bdeco\b|mercusys|tl-wr|xiaomi|redmi|mi-?router|'
                     r'\bax\d{3,4}\b|\basus\b|rt-a[cx]|zyxel|mikrotik|routerboard|\bhap\b|huawei|\bws\d{4}\b|tenda|netis|d-?link|\bdir-\d|openwrt|'
                     r'gl[-.]?inet|\bgl-|router|роутер|маршрутизатор)')
NOT_ROUTER = re.compile(r'(?i)jetstream|switch|коммутатор|\btl-sg|\bt\d{4}g|\bsg\d{3,4}|\bcamera|камер|printer|принтер')
# makers that (almost) only make routers / Wi-Fi gear — a MAC prefix alone is enough to have a look.
# Only prefixes confirmed on real hardware; names and the settings page catch the rest.
OUI = {'80:af:ca': 'Cudy', '50:ff:20': 'Keenetic'}
VENDOR_RE = [('Cudy', r'cudy|\bwr\d{3,4}'), ('Keenetic', r'keenetic|netcraze|\bkn-\d'), ('TP-Link', r'tp-?link|archer|deco|tl-wr'),
             ('Mercusys', r'mercusys'), ('Xiaomi', r'xiaomi|redmi|mi-?router'), ('ASUS', r'asus|rt-a[cx]'), ('Zyxel', r'zyxel'),
             ('MikroTik', r'mikrotik|routerboard|routeros|webfig'), ('Huawei', r'huawei'), ('Tenda', r'tenda'), ('Netis', r'netis'),
             ('D-Link', r'd-?link|\bdir-\d'), ('OpenWrt', r'openwrt|luci'), ('GL.iNet', r'gl[-.]?inet')]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def _norm(mac):
    """One device often has several MACs (VLAN / guest interfaces): the «locally administered» bit flipped (d4→d2, 50→52)
    or the last byte a bit off (…:37 and …:34). Compare the 1st byte by its high half only, the last one with a tolerance."""
    try:
        b = [int(x, 16) for x in mac.lower().split(':')]
        return (b[0] & 0xF0,) + tuple(b[1:5]), b[5]          # the low bits of the 1st byte vary per interface
    except (ValueError, IndexError):
        return None, None


def related(mac, macs):
    head, last = _norm(mac)
    if head is None:
        return False
    return any(h == head and abs(l - last) <= 8 for h, l in (_norm(m) for m in macs) if h is not None)


def vendor_of(*texts):
    t = ' '.join(x for x in texts if x)
    return next((v for v, rx in VENDOR_RE if re.search(rx, t, re.I)), None)


def probe(ip):
    """Does the router's settings page open from here? → {ok, url, title, keenetic}"""
    for url in (f'http://{ip}', f'https://{ip}'):
        try:
            try:
                r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'RackLive-routers'}), timeout=4, context=CTX)
            except urllib.error.HTTPError as e:
                r = e
            body = r.read(40000).decode('utf-8', 'replace')
            title = re.search(r'<title[^>]*>([^<]{1,80})', body, re.I)
            res = {'ok': True, 'url': url, 'title': title.group(1).strip() if title else '', 'code': getattr(r, 'status', getattr(r, 'code', 0)),
                   'vendor': vendor_of(title.group(1) if title else '', body[:4000])}
            try:
                a = urllib.request.urlopen(urllib.request.Request(url + '/auth', headers={'User-Agent': 'RackLive-routers'}), timeout=4, context=CTX)
                realm = a.headers.get('X-NDM-Realm')
            except urllib.error.HTTPError as e:
                realm = e.headers.get('X-NDM-Realm')
            except Exception:
                realm = None
            if realm:
                res.update(keenetic=True, vendor='Keenetic', model=realm)
            return res
        except Exception:
            continue
    return {'ok': False}


QUICK_PORTS = (22, 23, 135, 445, 3389, 3493, 5000, 5001, 8006, 8123)
TYPE_TEXT = {'nas': 'NAS', 'ha': 'Home Assistant', 'proxmox': 'Proxmox', 'server': 'Сервер (SSH)', 'switch': 'Коммутатор',
             'pc': 'Компьютер с Windows', 'ups': 'ИБП', 'router': 'Роутер'}


def classify(ip):
    """Not a router by name: which open ports does it have → what Rack Live can watch on it (None = a phone / IoT, skip).
    Quick TCP connects first, then the matching harmless fingerprint from detect.py."""
    from . import detect
    with concurrent.futures.ThreadPoolExecutor(len(QUICK_PORTS)) as pool:
        opened = {p for p, ok in zip(QUICK_PORTS, pool.map(lambda p: detect._open(ip, p, .8), QUICK_PORTS)) if ok}
    if not opened:
        return None
    tries = []
    if opened & {5000, 5001}:
        tries.append(('nas', detect.p_synology))
    if 8123 in opened:
        tries.append(('ha', detect.p_homeassistant))
    if 8006 in opened:
        tries.append(('proxmox', detect.p_proxmox))
    if 3493 in opened:
        tries.append(('ups', detect.p_nut))
    if opened & {22, 23}:
        tries += [('switch', detect.p_snmp), ('switch', detect.p_telnet), ('server', detect.p_ssh)]
    if 3389 in opened or {135, 445} <= opened:
        tries.append(('pc', detect.p_windows))
    for typ, fn in tries:
        try:
            r = fn(ip)
        except Exception:
            r = None
        if r:
            if typ == 'switch' and r['driver'] not in ('tplink_jetstream', 'snmp'):
                continue
            return dict(r, type=typ)
    return None


class RouterScan:
    def __init__(self, app):
        self.app = app
        saved = app.store._load('routers.json', {})
        self.found = saved.get('found', {})              # mac -> record
        self.dismissed = set(saved.get('dismissed', []))
        self.last = saved.get('last', 0)
        self.running = False
        self.lock = threading.Lock()

    def _save(self):
        self.app.store._dump('routers.json', {'found': self.found, 'dismissed': sorted(self.dismissed), 'last': self.last})
        self.app.store.bump()

    def due(self):
        return not self.running and time.time() - self.last >= EVERY

    def known(self):
        """MACs / IPs already in Rack Live (devices, their mesh points) — not offered again."""
        macs, ips = set(), set()
        for d in self.app.store.cfg['devices']:
            st = self.app.states.get(d['id']) or {}
            s = st.get('summary') or {}
            macs |= {x.lower() for x in (s.get('mac'), d.get('mac')) if x}
            host = re.sub(r'^\w+://|[:/].*$', '', d.get('host') or d.get('webUrl') or '')
            ips |= {x for x in (s.get('ip'), host) if x}
            for ch in st.get('children') or []:
                macs |= {ch['mac'].lower()} if ch.get('mac') else set()
                ips |= {ch['ip']} if ch.get('ip') else set()
        return macs, ips

    def candidates(self):
        names = {d['id']: d.get('name') for d in self.app.store.cfg['devices']}
        macs, ips = self.known()
        out = {}
        for did, st in list(self.app.states.items()):
            for c in st.get('clients') or []:
                mac = (c.get('mac') or '').lower()
                if len(mac) != 17 or c.get('ip') in ips or not c.get('ip') or related(mac, macs):
                    continue
                host = c.get('hostname') or ''
                label = f"{c.get('name') or ''} {host}"
                why = None if NOT_ROUTER.search(label) else 'name' if NAME_RE.search(label) else 'mac' if mac[:8] in OUI else None
                if not why and int(mac[:2], 16) & 2:
                    continue              # random (private) MAC: a phone or a laptop on Wi-Fi — not a server
                out[mac] = {'mac': mac, 'ip': c['ip'], 'name': c.get('name') or host or mac, 'hostname': host, 'segment': c.get('segment') or '',
                            'via': names.get(did), 'port': c.get('port'), 'vendor': vendor_of(c.get('name'), host) or OUI.get(mac[:8]), 'why': why,
                            'type': 'router' if why else None}
        return out

    def run(self):
        if self.running:
            return False
        self.running = True

        def job():
            try:
                cand = self.candidates()
                look = lambda r: probe(r['ip']) if r['type'] == 'router' else classify(r['ip'])
                with concurrent.futures.ThreadPoolExecutor(8) as pool:
                    webs = dict(zip(cand, pool.map(look, cand.values())))
                now = int(time.time())
                with self.lock:
                    for mac, r in cand.items():
                        w = webs.get(mac) or {}
                        old = self.found.get(mac) or {}
                        if r['type'] != 'router':           # a server / NAS / switch / PC: keep only what was recognised
                            if not w:
                                if old.get('type') not in (None, 'router'):
                                    old['checked'] = now
                                continue
                            self.found[mac] = dict(r, type=w['type'], driver=w['driver'], what=w['what'], hostPreset=w.get('host'),
                                                   webUrl=w.get('webUrl'), mode=w.get('mode'), first=old.get('first') or now, checked=now)
                            continue
                        # the name / MAC are surer than the page (Cudy firmware is OpenWrt inside); a Keenetic login realm is surest of all
                        vendor = 'Keenetic' if w.get('keenetic') else r['vendor'] or w.get('vendor')
                        self.found[mac] = dict(r, type='router', web=w, vendor=vendor, model=w.get('model') or old.get('model'),
                                               first=old.get('first') or now, checked=now)
                    for mac in list(self.found):          # gone for a month → forget
                        if mac not in cand and now - self.found[mac].get('checked', 0) > 30 * 86400:
                            self.found.pop(mac)
                    self.last = now
                    self._save()
            finally:
                self.running = False
        threading.Thread(target=job, daemon=True).start()
        return True

    def dismiss(self, mac, on=True):
        with self.lock:
            (self.dismissed.add if on else self.dismissed.discard)(mac.lower())
            self._save()

    def public(self):
        macs, ips = self.known()
        rows = [dict(r, dismissed=r['mac'] in self.dismissed) for r in self.found.values() if r.get('ip') not in ips and not related(r['mac'], macs)]
        return {'list': sorted(rows, key=lambda r: (r['dismissed'], r['name'].lower())), 'last': self.last, 'running': self.running}
