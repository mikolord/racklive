"""Persistent state: data/config.json (settings, devices, rack, map), events and metric history."""
import copy, json, os, secrets, threading, time

DEFAULT_VLANS = [
    {'vid': 1, 'name': 'Основная', 'color': '#0A84FF'},
]

DEFAULT = {
    'version': 2,
    'settings': {'title': 'Серверный шкаф', 'poll': 60, 'publicView': False, 'showClients': True, 'vlans': DEFAULT_VLANS},
    'auth': None,
    'devices': [],
    'rack': {'totalU': 18, 'units': []},
    'map': {'positions': {}, 'links': [], 'collapsed': {}},
}

SECRET_KEYS = ('password', 'token', 'agentToken')


class Store:
    def __init__(self, data_dir):
        self.dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, 'config.json')
        self.lock = threading.RLock()
        self.cfg = copy.deepcopy(DEFAULT)
        if os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as f:
                loaded = json.load(f)
            for k, v in DEFAULT.items():
                loaded.setdefault(k, copy.deepcopy(v))
            for k, v in DEFAULT['settings'].items():
                loaded['settings'].setdefault(k, copy.deepcopy(v))
            self.cfg = loaded
        self.events = self._load('events.json', [])
        self.history = self._load('history.json', {})

    def _load(self, name, default):
        p = os.path.join(self.dir, name)
        try:
            with open(p, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default

    def _dump(self, name, obj):
        p = os.path.join(self.dir, name)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1 if name == 'config.json' else None)
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass

    def save(self):
        with self.lock:
            self._dump('config.json', self.cfg)

    def save_runtime(self):
        with self.lock:
            self._dump('events.json', self.events[-500:])
            self._dump('history.json', self.history)

    # ── devices ──
    def device(self, did):
        return next((d for d in self.cfg['devices'] if d['id'] == did), None)

    def public_device(self, d):
        out = {k: v for k, v in d.items() if k not in SECRET_KEYS}
        for k in SECRET_KEYS:
            if d.get(k):
                out[k + 'Set'] = True
        return out

    def upsert_device(self, data, did=None):
        with self.lock:
            if did:
                d = self.device(did)
                if not d:
                    raise KeyError(did)
                for k, v in data.items():
                    if k in SECRET_KEYS and (v is None or v == ''):
                        continue                    # empty secret field = keep the old value
                    if k not in ('id',):
                        d[k] = v
            else:
                d = dict(data)
                d['id'] = 'd' + secrets.token_hex(4)
                d.setdefault('enabled', True)
                if d.get('driver') == 'agent':
                    d['agentToken'] = secrets.token_urlsafe(24)
                self.cfg['devices'].append(d)
            self.save()
            return d

    def delete_device(self, did):
        with self.lock:
            self.cfg['devices'] = [d for d in self.cfg['devices'] if d['id'] != did]
            for u in self.cfg['rack']['units']:
                if u.get('deviceId') == did:
                    u['deviceId'] = None
            self.save()

    # ── events / history ──
    def add_event(self, device_id, name, level, text):
        with self.lock:
            self.events.append({'t': time.time(), 'device': device_id, 'name': name, 'level': level, 'text': text})
            self.events = self.events[-500:]
            try:
                self._dump('events.json', self.events)
            except OSError:
                pass

    def add_point(self, key, point, avg=False):
        """~5-minute buckets for 24 hours. avg=True averages samples inside a bucket (traffic), else keeps the last."""
        with self.lock:
            h = self.history.setdefault(key, [])
            if h and point['t'] - h[-1].get('t0', h[-1]['t']) < 290:
                if avg:
                    n = h[-1].get('n', 1)
                    for k, v in point.items():
                        if k != 't' and isinstance(v, (int, float)):
                            h[-1][k] = round((h[-1].get(k, v) * n + v) / (n + 1))
                    h[-1]['n'] = n + 1
                    h[-1]['t'] = point['t']
                else:
                    h[-1] = dict(point, t0=h[-1].get('t0', h[-1]['t']))
            else:
                h.append(dict(point, t0=point['t']))
            del h[:-288]

    # ── import of the old rack-constructor format ──
    @staticmethod
    def import_old_rack(old):
        units = []
        for u in old.get('units', []):
            units.append({'id': u.get('id') or 'u' + secrets.token_hex(3), 'name': u.get('name', ''), 'type': u.get('type', 'other'),
                          'uSize': int(u.get('uSize') or 1), 'uStart': int(u.get('uStart') or 1), 'side': u.get('side') or 'front',
                          'color': u.get('color') or '#0A84FF', 'deviceId': None, 'notes': u.get('config') if isinstance(u.get('config'), str) else '',
                          'webUrl': u.get('webUrl') or ''})
        return {'totalU': int(old.get('totalU') or 18), 'units': units}
