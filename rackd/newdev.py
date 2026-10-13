"""New devices in the network: every MAC seen in the routers' client lists and the switches' MAC tables is remembered;
a MAC never seen before is recorded. The first 10 minutes after a router/switch is first polled are silent — that is
learning its current clients, not news.

What a new device means depends on the network it joined (cfg.netroles, «<router id>:<network id>» → role, set by the user):
  main         the home network — registered on the router = «mine», silently; not registered → a question to the admin
  subscribers  tenants' network — «a new subscriber, do you know?» (needs a confirmation)
  iot, cameras smart home / cameras — needs a confirmation
  guest        guests — silent; only an anomaly (a flood of new devices) is reported
  service      technical links (VPN bridge, OpenWrt WAN…) — silent
A network without a role yet behaves like before: every new device is a question.
"""
import threading, time

LEARN = 600
ROLES = {'main': 'Основная', 'subscribers': 'Абоненты', 'guest': 'Гостевая', 'iot': 'Умный дом', 'cameras': 'Камеры', 'service': 'Служебная'}
ANOMALY = 12            # new devices in a guest network within an hour


def random_mac(mac):
    """Locally administered MAC (2nd hex digit 2/6/A/E): phones and laptops use them for privacy."""
    try:
        return int(mac.split(':')[0], 16) & 2 == 2
    except (ValueError, IndexError):
        return False


def decide(rec, role):
    """→ mine | ask | quiet"""
    if role == 'main':
        return 'mine' if rec.get('registered') else 'ask'
    if role in ('guest', 'service'):
        return 'quiet'
    return 'ask'


class NewDevices:
    def __init__(self, store):
        self.store = store
        saved = store._load('known.json', {})
        self.known = saved.get('macs', {})                 # mac -> {first, last, name, ip, via}
        self.sources = saved.get('sources', {})            # device id -> first time it reported clients
        self.recent = saved.get('recent', [])              # [{t, mac, name, ip, segment, segId, router, via, random, registered}]
        self.trusted = set(saved.get('trusted', []))
        self.anomaly_t = saved.get('anomalyT', {})         # network key -> last anomaly alert
        self.lock, self.dirty, self.last_save = threading.Lock(), False, 0

    def roles(self):
        return self.store.cfg.get('netroles') or {}

    def role_of(self, rec):
        return self.roles().get(f"{rec.get('router')}:{rec.get('segId')}") if rec.get('segId') else None

    def _save(self, force=False):
        if self.dirty and (force or time.time() - self.last_save > 300):
            self.store._dump('known.json', {'macs': self.known, 'sources': self.sources, 'recent': self.recent[-300:],
                                            'trusted': sorted(self.trusted), 'anomalyT': self.anomaly_t})
            self.dirty, self.last_save = False, time.time()

    def scan(self, devices, states):
        """→ (new devices found in this pass, anomaly texts)"""
        now, new, anomalies = time.time(), [], []
        names = {d['id']: d.get('name') for d in devices}
        with self.lock:
            live = {}                                       # mac -> the router's current view (registration can change later)
            for did, st in states.items():
                if st.get('status') == 'offline' or did not in names:
                    continue
                seen = [dict(mac=c.get('mac'), ip=c.get('ip'), name=c.get('name'), seg=c.get('segment'), segId=c.get('segId'),
                             registered=c.get('registered')) for c in st.get('clients') or []]
                for c in seen:
                    if c['mac']:
                        live[c['mac'].lower()] = (did, c)
                for p in st.get('ports') or []:
                    if p.get('kind') != 'wan' and len(p.get('peers') or []) <= 3:      # skip uplinks
                        seen += [dict(mac=x.get('mac'), seg=f"порт {p.get('n')}") for x in p.get('peers') or []]
                if not seen:
                    continue
                first = self.sources.setdefault(did, now)
                if first == now:
                    self.dirty = True
                learning = now - first < LEARN
                for c in seen:
                    mac = (c.get('mac') or '').lower()
                    if len(mac) != 17:
                        continue
                    k = self.known.get(mac)
                    if k:
                        if now - k.get('last', 0) > 300 or (c.get('name') and not k.get('name')) or (c.get('ip') and k.get('ip') != c.get('ip')):
                            k.update(last=int(now), **{x: c[x] for x in ('name', 'ip') if c.get(x)})
                            self.dirty = True
                        continue
                    self.known[mac] = {'first': int(now), 'last': int(now), 'name': c.get('name') or '', 'ip': c.get('ip') or '', 'via': names[did]}
                    self.dirty = True
                    if not learning:
                        rec = {'t': int(now), 'mac': mac, 'name': c.get('name') or '', 'ip': c.get('ip') or '', 'segment': c.get('seg') or '',
                               'segId': c.get('segId'), 'router': did if c.get('segId') else None, 'via': names[did],
                               'random': random_mac(mac), 'registered': bool(c.get('registered'))}
                        self.recent.append(rec)
                        new.append(rec)
            # later polls: names / IPs arrive, the device gets registered on the router
            for r in self.recent[-80:]:
                k = self.known.get(r['mac']) or {}
                if not r.get('name') and k.get('name'):
                    r['name'] = k['name']
                if not r.get('ip') and k.get('ip'):
                    r['ip'] = k['ip']
                lv = live.get(r['mac'])
                if lv and bool(lv[1].get('registered')) != bool(r.get('registered')):
                    r['registered'] = bool(lv[1].get('registered')); self.dirty = True
                if lv and lv[1].get('segId') and not r.get('segId'):        # records made before networks had ids
                    r.update(segId=lv[1]['segId'], router=lv[0]); self.dirty = True
            # a guest network flooded with new devices — somebody is hammering it
            roles = self.roles()
            for key, role in roles.items():
                if role != 'guest':
                    continue
                router, seg = key.split(':', 1)
                n = sum(1 for r in self.recent if r.get('router') == router and r.get('segId') == seg and now - r['t'] < 3600)
                if n >= ANOMALY and now - self.anomaly_t.get(key, 0) > 3600:
                    self.anomaly_t[key] = now; self.dirty = True
                    net = next((r.get('segment') for r in self.recent[::-1] if r.get('router') == router and r.get('segId') == seg), seg)
                    anomalies.append(f'⚠️ Гостевая сеть «{net}»: {n} новых устройств за час — похоже, кто-то перебирает подключения')
            self._save(force=bool(new or anomalies))
        return new, anomalies

    def trust(self, mac, on=True):
        with self.lock:
            (self.trusted.add if on else self.trusted.discard)(mac.lower())
            self.dirty = True
            self._save(force=True)

    def public(self, days=7):
        cut = time.time() - days * 86400
        out = []
        for r in self.recent[::-1]:
            if r['t'] < cut:
                continue
            role = self.role_of(r)
            out.append(dict(r, trusted=r['mac'] in self.trusted, role=role, decision='ok' if r['mac'] in self.trusted else decide(r, role)))
        return out

    def networks(self, devices, states):
        """the routers' networks with their roles — for «which network is which»"""
        out, roles = [], self.roles()
        for d in devices:
            st = states.get(d['id']) or {}
            counts = {}
            for c in st.get('clients') or []:
                if c.get('segId'):
                    counts[c['segId']] = counts.get(c['segId'], 0) + 1
            for n in st.get('networks') or []:
                key = f"{d['id']}:{n['id']}"
                out.append(dict(n, key=key, router=d['id'], routerName=d.get('name'), role=roles.get(key), clients=counts.get(n['id'], 0)))
        return out


def describe(r, role=None):
    who = r.get('name') or ('телефон или ноутбук со случайным MAC' if r.get('random') else 'без имени')
    where = ', '.join(x for x in (r.get('ip'), r.get('segment'), f"через {r['via']}" if r.get('via') else '') if x)
    head = {'subscribers': '🆕 Новый абонент?', 'iot': '🆕 Новое умное устройство', 'cameras': '🆕 Новое устройство в сети камер',
            'main': '🆕 Незарегистрированное устройство в основной сети'}.get(role, '🆕 Новое устройство в сети')
    return f"{head}: {who} ({r['mac']}{', ' + where if where else ''})"
