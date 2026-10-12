"""New devices in the network: every MAC seen in the routers' client lists and the switches' MAC tables is remembered;
a MAC never seen before is reported (event + notification). The first 10 minutes after a router/switch is first polled
are silent — that is learning its current clients, not news.
"""
import threading, time

LEARN = 600


def random_mac(mac):
    """Locally administered MAC (2nd hex digit 2/6/A/E): phones and laptops use them for privacy."""
    try:
        return int(mac.split(':')[0], 16) & 2 == 2
    except (ValueError, IndexError):
        return False


class NewDevices:
    def __init__(self, store):
        self.store = store
        saved = store._load('known.json', {})
        self.known = saved.get('macs', {})                 # mac -> {first, last, name, ip, via}
        self.sources = saved.get('sources', {})            # device id -> first time it reported clients
        self.recent = saved.get('recent', [])              # [{t, mac, name, ip, segment, via, random}]
        self.trusted = set(saved.get('trusted', []))
        self.lock, self.dirty, self.last_save = threading.Lock(), False, 0

    def _save(self, force=False):
        if self.dirty and (force or time.time() - self.last_save > 300):
            self.store._dump('known.json', {'macs': self.known, 'sources': self.sources, 'recent': self.recent[-300:],
                                            'trusted': sorted(self.trusted)})
            self.dirty, self.last_save = False, time.time()

    def scan(self, devices, states):
        """→ list of new devices found in this pass (already recorded)."""
        now, new = time.time(), []
        names = {d['id']: d.get('name') for d in devices}
        with self.lock:
            for did, st in states.items():
                if st.get('status') == 'offline' or did not in names:
                    continue
                seen = [(c.get('mac'), c.get('ip'), c.get('name'), c.get('segment')) for c in st.get('clients') or []]
                for p in st.get('ports') or []:
                    if p.get('kind') != 'wan' and len(p.get('peers') or []) <= 3:      # skip uplinks
                        seen += [(x.get('mac'), None, None, f"порт {p.get('n')}") for x in p.get('peers') or []]
                if not seen:
                    continue
                first = self.sources.setdefault(did, now)
                if first == now:
                    self.dirty = True
                learning = now - first < LEARN
                for mac, ip, name, seg in seen:
                    mac = (mac or '').lower()
                    if len(mac) != 17:
                        continue
                    k = self.known.get(mac)
                    if k:
                        if now - k.get('last', 0) > 300 or (name and not k.get('name')) or (ip and k.get('ip') != ip):
                            k.update(last=int(now), **{x: v for x, v in (('name', name), ('ip', ip)) if v})
                            self.dirty = True
                        continue
                    self.known[mac] = {'first': int(now), 'last': int(now), 'name': name or '', 'ip': ip or '', 'via': names[did]}
                    self.dirty = True
                    if not learning:
                        rec = {'t': int(now), 'mac': mac, 'name': name or '', 'ip': ip or '', 'segment': seg or '', 'via': names[did],
                               'random': random_mac(mac)}
                        self.recent.append(rec)
                        new.append(rec)
            # names/IPs often arrive a poll later: fill them into recent records
            for r in self.recent[-50:]:
                k = self.known.get(r['mac']) or {}
                if not r.get('name') and k.get('name'):
                    r['name'] = k['name']
                if not r.get('ip') and k.get('ip'):
                    r['ip'] = k['ip']
            self._save(force=bool(new))
        return new

    def trust(self, mac, on=True):
        with self.lock:
            (self.trusted.add if on else self.trusted.discard)(mac.lower())
            self.dirty = True
            self._save(force=True)

    def public(self, days=7):
        cut = time.time() - days * 86400
        return [dict(r, trusted=r['mac'] in self.trusted) for r in self.recent if r['t'] >= cut][::-1]


def describe(r):
    who = r.get('name') or ('телефон или ноутбук со случайным MAC' if r.get('random') else 'без имени')
    where = ', '.join(x for x in (r.get('ip'), r.get('segment'), f"через {r['via']}" if r.get('via') else '') if x)
    return f"🆕 Новое устройство в сети: {who} ({r['mac']}{', ' + where if where else ''})"
