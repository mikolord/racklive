"""Network scan: «what is on my network?» — for an administrator who has just installed Rack Live and has an empty list.

It only KNOCKS: a TCP connect (no login, nothing is changed, no passwords) in three steps:
  1. who is alive — a connection attempt makes the kernel ask «who has this address?» (ARP); the answers are read from the ARP table
     (that also gives the MAC), plus anyone who answered the connect directly;
  2. which well-known ports are open on the live ones (web, ssh, telnet, smb, rdp, rtsp, printers, NAS, Home Assistant, Proxmox …);
  3. what Rack Live can watch there — the same fingerprints as «Определить автоматически» (detect.py), only on the interesting hosts.
Only private networks up to /22 (1022 addresses) are scanned. The result is kept in data/netscan.json."""
import concurrent.futures, ipaddress, re, socket, threading, time

from . import detect, routers
from .drivers import REGISTRY

PORTS = (22, 23, 53, 80, 139, 443, 445, 554, 631, 1883, 3389, 3493, 5000, 5001, 8000, 8006, 8080, 8123, 9100, 37777)
SMART = {22, 23, 80, 443, 5000, 5001, 8006, 8123, 3493, 8080}        # worth the detect.py fingerprints
MAX_HOSTS = 1022
# a few OUI prefixes that are certain (the rest is shown by name / banner)
OUI = {'b8:27:eb': 'Raspberry Pi', 'dc:a6:32': 'Raspberry Pi', 'e4:5f:01': 'Raspberry Pi', 'd8:3a:dd': 'Raspberry Pi', '28:cd:c1': 'Raspberry Pi',
       '2c:cf:67': 'Raspberry Pi', '00:11:32': 'Synology', '90:09:d0': 'Synology', '80:af:ca': 'Cudy', '50:ff:20': 'Keenetic'}
KIND_TEXT = {'camera': 'Камера или видеорегистратор', 'printer': 'Принтер', 'pc': 'Компьютер', 'other': 'Устройство в сети'}
SAMPLE = [  # shown in the demo
    {'ip': '10.0.0.1', 'mac': 'aa:00:00:00:00:01', 'name': 'router.lan', 'vendor': 'Keenetic', 'ports': [53, 80, 443], 'driver': 'keenetic', 'score': 95, 'kind': 'router', 'what': 'Роутер Keenetic / Netcraze'},
    {'ip': '10.0.0.2', 'mac': 'aa:00:00:00:00:02', 'name': 'switch-core', 'vendor': '', 'ports': [22, 23, 80], 'driver': 'tplink_jetstream', 'score': 85, 'kind': 'switch', 'what': 'Коммутатор TP-Link JetStream'},
    {'ip': '10.0.0.3', 'mac': 'aa:00:00:00:00:03', 'name': 'nas', 'vendor': 'Synology', 'ports': [22, 80, 445, 5000, 5001], 'driver': 'synology', 'score': 95, 'kind': 'nas', 'what': 'Synology DiskStation'},
    {'ip': '10.0.0.6', 'mac': 'aa:00:00:00:00:06', 'name': 'homeassistant', 'vendor': '', 'ports': [8123], 'driver': 'homeassistant', 'score': 90, 'kind': 'server', 'what': 'Home Assistant'},
    {'ip': '10.0.0.30', 'mac': 'aa:00:00:00:00:30', 'name': 'proxmox', 'vendor': '', 'ports': [22, 8006], 'driver': 'proxmox', 'score': 90, 'kind': 'server', 'what': 'Proxmox VE'},
    {'ip': '10.0.0.21', 'mac': 'aa:00:00:00:00:21', 'name': '', 'vendor': '', 'ports': [80, 554, 37777], 'driver': None, 'score': 0, 'kind': 'camera', 'what': 'Камера или видеорегистратор'},
    {'ip': '10.0.0.22', 'mac': 'aa:00:00:00:00:22', 'name': '', 'vendor': '', 'ports': [80, 554, 37777], 'driver': None, 'score': 0, 'kind': 'camera', 'what': 'Камера или видеорегистратор'},
    {'ip': '10.0.0.40', 'mac': 'aa:00:00:00:00:40', 'name': 'office-printer', 'vendor': '', 'ports': [80, 631, 9100], 'driver': None, 'score': 0, 'kind': 'printer', 'what': 'Принтер'},
    {'ip': '10.0.0.41', 'mac': 'aa:00:00:00:00:41', 'name': 'PC-Accounting', 'vendor': '', 'ports': [135, 445, 3389], 'driver': 'ping', 'score': 30, 'kind': 'pc', 'what': 'Компьютер с Windows'},
    {'ip': '10.0.0.77', 'mac': 'aa:00:00:00:00:77', 'name': '', 'vendor': '', 'ports': [], 'driver': None, 'score': 0, 'kind': 'other', 'what': 'Устройство в сети (портов не открыто — телефон, умная техника)'},
]


def check_cidr(text):
    """→ (network, error)"""
    try:
        net = ipaddress.ip_network((text or '').strip(), strict=False)
    except ValueError:
        return None, 'не похоже на сеть — напишите, например, 192.168.1.0/24'
    if net.version != 4 or not net.is_private or net.is_loopback or net.is_link_local:
        return None, 'сканируются только домашние сети (192.168.x.x, 10.x.x.x, 172.16–31.x.x)'
    if net.num_addresses - 2 > MAX_HOSTS:
        return None, f'сеть слишком большая: не больше /22 ({MAX_HOSTS} адресов)'
    return net, None


def arp_table():
    """{ip: mac} of the neighbours that answered (Linux /proc/net/arp; empty elsewhere)"""
    out = {}
    try:
        with open('/proc/net/arp') as f:
            next(f, None)
            for line in f:
                p = line.split()
                if len(p) >= 4 and p[2] == '0x2' and p[3] != '00:00:00:00:00:00':
                    out[p[0]] = p[3].lower()
    except OSError:
        pass
    return out


def local_ips():
    """IPv4 addresses of this machine (Linux /proc/net/fib_trie) — they answer without ARP and must not be taken for other devices"""
    out, last = set(), None
    try:
        with open('/proc/net/fib_trie') as f:
            for line in f:
                m = re.search(r'\|--\s+(\d+\.\d+\.\d+\.\d+)', line)
                if m:
                    last = m.group(1)
                elif '/32 host LOCAL' in line and last:
                    out.add(last)
    except OSError:
        pass
    return out


def infra_ips(app):
    """addresses a scan must not knock on: the routers' own addresses (every network's gateway), the default gateway, the routers / switches already added, this machine.
    A router takes a burst of connections to its own closed ports for a port scan and shuts its web interface to the scanner for ~15 minutes — Rack Live then «loses» it."""
    out = set(local_ips())
    for st in list(app.states.values()):
        for n in st.get('networks') or []:
            if n.get('ip'):
                out.add(n['ip'])
    for d in app.store.cfg['devices']:
        h = re.sub(r'^\w+://|[:/].*$', '', d.get('host') or '')
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', h) and (d.get('kind') in ('router', 'switch', 'ap') or d.get('driver') in ('keenetic', 'openwrt', 'tplink_jetstream', 'unmanaged')):
            out.add(h)
    try:
        with open('/proc/net/route') as f:
            next(f, None)
            for line in f:
                p = line.split()
                if len(p) > 3 and p[1] == '00000000' and int(p[3], 16) & 2:
                    out.add(socket.inet_ntoa(bytes.fromhex(p[2])[::-1]))
    except (OSError, ValueError):
        pass
    return out


def touch(ip, timeout=.35):
    """a connect attempt: True = answered (open or refused — the host is there), False = silence"""
    try:
        with socket.create_connection((ip, 80), timeout):
            return True
    except ConnectionRefusedError:
        return True
    except OSError:
        return False


class NetScan:
    def __init__(self, app, demo=False):
        self.app, self.store, self.demo = app, app.store, demo
        self.lock = threading.Lock()
        self.s = self.store._load('netscan.json', {})
        self.s.update(running=False)
        self.s.setdefault('items', [])
        self.cancel = False

    # ── where to look ──
    def subnets(self):
        """suggested networks: the one this machine is in, the ones of added devices, the ones the routers report"""
        out, seen = [], set()

        def add(cidr, label):
            net, err = check_cidr(cidr)
            if net and str(net) not in seen:
                seen.add(str(net)); out.append({'cidr': str(net), 'label': label})
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1)); mine = s.getsockname()[0]; s.close()
            add(mine + '/24', 'сеть, где стоит Rack Live')
        except OSError:
            pass
        for d in self.store.cfg['devices']:
            h = re.sub(r'^\w+://|[:/].*$', '', d.get('host') or '')
            if re.match(r'^\d+\.\d+\.\d+\.\d+$', h):
                add(h + '/24', 'сеть устройства «%s»' % (d.get('name') or h))
        for st in self.app.states.values():
            for n in st.get('networks') or []:
                if n.get('ip') and n.get('mask'):
                    try:
                        add(str(ipaddress.ip_interface(f"{n['ip']}/{n['mask']}").network), 'сеть «%s»' % (n.get('name') or n.get('alias') or 'роутера'))
                    except ValueError:
                        pass
        if not out:
            out.append({'cidr': '192.168.1.0/24', 'label': 'типичная домашняя сеть'})
        return out

    def public(self):
        s = self.s
        return {'running': s.get('running', False), 'phase': s.get('phase'), 'done': s.get('done', 0), 'total': s.get('total', 0), 'cidr': s.get('cidr'),
                'started': s.get('started'), 'finished': s.get('finished'), 'error': s.get('error'), 'items': s.get('items', []), 'subnets': self.subnets(),
                'arp': s.get('arp', True), 'skipped': s.get('skipped') or []}

    # ── run ──
    def start(self, arg):
        """→ (started, error). `arg`: a network, several (list / text), or empty = every network Rack Live knows about"""
        from . import cameras
        nets, err = cameras.parse_targets(arg, self.subnets())
        if err:
            return False, err
        with self.lock:
            if self.s.get('running'):
                return False, 'сканирование уже идёт'
            self.cancel = False
            self.s.update(running=True, phase='ping', done=0, total=sum(n.num_addresses - 2 for n in nets), cidr=', '.join(str(n) for n in nets), started=int(time.time()), finished=None, error=None, items=[], arp=True)
        self.store.bump()
        threading.Thread(target=self.run_demo if self.demo else self.run, args=(nets,), daemon=True).start()
        return True, None

    def stop(self):
        self.cancel = True

    def _set(self, **kw):
        with self.lock:
            self.s.update(kw)
        self.store.bump()

    def _finish(self, error=None):
        self.s.update(running=False, phase=None, finished=int(time.time()), error=error)
        self.store._dump('netscan.json', {k: self.s.get(k) for k in ('cidr', 'started', 'finished', 'items', 'error', 'total')})
        self.store.bump()

    def run_demo(self, nets):
        try:
            steps = 24
            for i in range(steps):
                if self.cancel:
                    break
                time.sleep(.12)
                self._set(done=int(self.s['total'] * (i + 1) / steps), phase='ping' if i < 10 else 'ports' if i < 18 else 'detect')
            known = self.app.routers.known()[1] if hasattr(self.app, 'routers') else set()
            self.s['items'] = [dict(x, added=x['ip'] in known) for x in SAMPLE]
            self._finish()
        except Exception as e:
            self._finish(str(e))

    def run(self, nets):
        try:
            skip = infra_ips(self.app)
            hosts = [str(h) for n in nets for h in n.hosts() if str(h) not in skip]
            self.s['skipped'] = sorted(skip & {str(h) for n in nets for h in n.hosts()})
            # 1. who is alive
            alive = {}
            with concurrent.futures.ThreadPoolExecutor(128) as pool:
                for i, (ip, ok) in enumerate(zip(hosts, pool.map(touch, hosts))):
                    if ok:
                        alive[ip] = ''
                    if i % 8 == 0:
                        self._set(done=i)
                    if self.cancel:
                        return self._finish('остановлено')
            time.sleep(.6)
            hostset = set(hosts)
            arp = arp_table()
            have_arp = bool(arp) or not alive
            for ip, mac in arp.items():
                if ip in hostset:
                    alive[ip] = mac
            self.s['arp'] = have_arp
            self._set(phase='ports', done=0, total=len(alive))
            # 2. ports of the live ones
            ports = {ip: [] for ip in alive}
            tasks = [(ip, p) for ip in alive for p in PORTS]
            done = [0]

            def probe(t):
                ip, p = t
                ok = detect._open(ip, p, .6)
                done[0] += 1
                return ip, p, ok
            with concurrent.futures.ThreadPoolExecutor(160) as pool:
                for ip, p, ok in pool.map(probe, tasks):
                    if ok:
                        ports[ip].append(p)
                    if self.cancel:
                        return self._finish('остановлено')
                    if done[0] % 40 == 0:
                        self._set(done=min(len(alive), done[0] // len(PORTS)))
            # names the routers already know
            known_macs, known_ips = self.app.routers.known()
            mine = local_ips()
            names = {}
            for st in self.app.states.values():
                for c in st.get('clients') or []:
                    if c.get('ip'):
                        names[c['ip']] = c.get('name') or c.get('hostname') or ''
            items = {}
            for ip in sorted(alive, key=lambda x: ipaddress.ip_address(x)):
                mac = alive[ip]
                items[ip] = {'ip': ip, 'mac': mac, 'name': names.get(ip, ''), 'vendor': OUI.get(mac[:8], '') or routers.vendor_of(names.get(ip)) or '', 'ports': sorted(ports[ip]),
                             'driver': None, 'score': 0, 'kind': self._guess(ports[ip]), 'what': '', 'self': ip in mine, 'added': ip in known_ips or routers.related(mac, known_macs) if mac else ip in known_ips}
            with self.lock:
                self.s['items'] = list(items.values())
            # 3. what Rack Live can watch there
            self._set(phase='detect', done=0, total=len(items))
            smart = [ip for ip in items if SMART & set(items[ip]['ports']) and not items[ip]['added']]       # the machine Rack Live runs on too: a router / NAS is worth watching
            self._set(total=len(smart) or 1)
            with concurrent.futures.ThreadPoolExecutor(6) as pool:
                futs = {pool.submit(detect.detect, ip): ip for ip in smart}
                n = 0
                for f in concurrent.futures.as_completed(futs):
                    ip = futs[f]; n += 1
                    try:
                        best = next((r for r in f.result(timeout=40) if r['driver'] not in ('ping',) and r['score'] >= 60), None)
                    except Exception:
                        best = None
                    if best:
                        drv = REGISTRY.get(best['driver'])
                        items[ip].update(driver=best['driver'], score=best['score'], what=best.get('what') or '', mode=best.get('mode'), host=best.get('host') or ip,
                                         kind=best.get('kind') or getattr(drv, 'kind', None) or items[ip]['kind'])
                    self._set(done=n)
                    if self.cancel:
                        return self._finish('остановлено')
            for it in items.values():
                if it['self'] and it['driver']:
                    it['what'] += ' · здесь работает Rack Live'
                elif it['self']:
                    it.update(kind='server', what='Это устройство, на котором работает Rack Live')
                elif not it['what']:
                    private = bool(it['mac']) and int(it['mac'][:2], 16) & 2
                    it['what'] = ('Телефон или ноутбук (адрес устройства случайный)' if private and not it['ports']
                                  else KIND_TEXT.get(it['kind'], 'Устройство в сети') + ('' if it['ports'] else ' (портов не открыто — телефон, умная техника)'))
                name = it['name'] or self._rdns(it['ip'])
                it['name'] = '' if (name == it['ip'] or re.match(r'[0-9a-f]{16,}', name or '')) else name
            items = self._merge(items)
            with self.lock:
                self.s['items'] = list(items.values())
            self._finish()
        except Exception as e:
            self._finish(f'{type(e).__name__}: {e}')

    @staticmethod
    def _merge(items):
        """one device with several addresses (a mesh point on several networks, a NAS with extra IPs): one row, the others in `also`"""
        by, out = {}, []
        mine = [it for it in items.values() if it.get('self')]
        if mine:                                                   # all the addresses of the machine Rack Live runs on: one row, the recognised one first
            best = max(mine, key=lambda i: (bool(i['driver']), len(i['ports'])))
            best['also'] = [i['ip'] for i in mine if i is not best]
            out.append(best)
        for it in items.values():
            mac = it['mac']
            if it.get('self'):
                continue
            if mac and mac in by:
                keep = by[mac]
                if len(it['ports']) > len(keep['ports']) or (it['driver'] and not keep['driver']):
                    out[out.index(keep)] = it                      # the richer row wins; the poorer address goes to `also`
                    by[mac] = it
                    it['also'] = keep.get('also', []) + [keep['ip']]
                else:
                    keep.setdefault('also', []).append(it['ip'])
                continue
            if mac:
                by[mac] = it
            out.append(it)
        return {i['ip']: i for i in out}

    @staticmethod
    def _guess(ports):
        p = set(ports)
        if p & {554, 8000, 37777}:
            return 'camera'
        if p & {9100, 631}:
            return 'printer'
        if p & {3389, 445, 139} and not p & {5000, 5001, 22}:
            return 'pc'
        return 'other'

    @staticmethod
    def _rdns(ip):
        try:
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                return pool.submit(lambda: socket.gethostbyaddr(ip)[0]).result(timeout=1.5)
        except Exception:
            return ''
