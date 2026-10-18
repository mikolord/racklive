"""Persistent state: data/config.json (settings, devices, rack, map), events and metric history."""
import copy, json, os, secrets, threading, time

DEFAULT_VLANS = [
    {'vid': 1, 'name': 'Основная', 'color': '#0A84FF'},
]

DEFAULT = {
    'version': 2,
    'settings': {'title': 'Серверный шкаф', 'poll': 60, 'publicView': False, 'showClients': True, 'hints': True, 'vlans': DEFAULT_VLANS},
    'auth': None,
    'devices': [],
    'racks': [{'id': 'rack0', 'name': 'Серверный шкаф', 'totalU': 18, 'units': []}],
    'map': {'positions': {}, 'links': [], 'collapsed': {}},
    # floor plan: buildings → floors (incl. outdoor "yard") with walls, rooms and placed items; links = backbone between buildings
    'plan': {'buildings': [], 'links': [], 'poles': []},
}

SECRET_KEYS = ('password', 'token', 'agentToken', 'privateKey', 'entwarePassword', 'panelInfo', 'webPassword', 'tokenSecret')
NEVER_EXPORTED = ('auth', 'mfa')          # the administrator password and the second factor stay with the installation: a backup file never carries them
KEPT_ON_IMPORT = ('auth', 'mfa', 'notify')   # …and restoring a file never replaces them (nor the notification channels)


def _service_secrets(c):
    """(container, key) of every secret that is not a device field"""
    n = c.get('notify') or {}
    out = [((n.get('telegram') or {}), 'token'), ((n.get('email') or {}), 'password'), ((c.get('ai') or {}), 'key'), ((c.get('collector') or {}), 'token'),
           (((c.get('dev') or {}).get('ap') or {}), 'password')]
    out += [(s, 'token') for s in c.get('sites') or [] if isinstance(s, dict)]
    return out


def backup_of(cfg, with_secrets=False):
    """the backup file: never the sign-in; without passwords and keys unless asked (and the password was typed again)"""
    c = copy.deepcopy(cfg)
    for k in NEVER_EXPORTED:
        c.pop(k, None)
    if not with_secrets:
        for d in c.get('devices') or []:
            for k in SECRET_KEYS:
                d.pop(k, None)
        for box, k in _service_secrets(c):
            box.pop(k, None)
    c['backupSecrets'] = bool(with_secrets)
    return c


def restored(cur, data):
    """a backup file → the new config. Checked first; the sign-in, the second factor and the notification channels stay as they are now;
    a password or key the file does not carry (a backup without secrets) is kept from the current config. Raises ValueError."""
    if not isinstance(data, dict) or data.get('version') != 2 or not isinstance(data.get('devices'), list):
        raise ValueError('это не резервная копия Rack Live')
    for d in data['devices']:
        if not isinstance(d, dict) or not isinstance(d.get('id'), str) or not isinstance(d.get('driver'), str):
            raise ValueError('в резервной копии повреждён список устройств')
    for k, typ in (('racks', list), ('settings', dict), ('map', dict), ('plan', dict), ('sites', list)):
        if k in data and not isinstance(data[k], typ):
            raise ValueError(f'в резервной копии повреждён раздел «{k}»')
    new = copy.deepcopy(data)
    new.pop('backupSecrets', None)
    for k in KEPT_ON_IMPORT:
        if k in cur:
            new[k] = copy.deepcopy(cur[k])
        else:
            new.pop(k, None)
    old = {d['id']: d for d in cur.get('devices') or [] if isinstance(d, dict) and d.get('id')}
    for d in new['devices']:
        for k in SECRET_KEYS:
            if not d.get(k) and (old.get(d['id']) or {}).get(k):
                d[k] = copy.deepcopy(old[d['id']][k])
    for path in (('ai', 'key'), ('collector', 'token'), ('dev', 'ap', 'password')):
        src, dst = cur, new
        for p in path[:-1]:
            src, dst = (src.get(p) or {}), dst.get(p)
            if not isinstance(dst, dict):
                break
        else:
            if not dst.get(path[-1]) and src.get(path[-1]):
                dst[path[-1]] = src[path[-1]]
    cur_sites = {s.get('id'): s for s in cur.get('sites') or [] if isinstance(s, dict)}
    for s in new.get('sites') or []:
        if isinstance(s, dict) and not s.get('token') and (cur_sites.get(s.get('id')) or {}).get('token'):
            s['token'] = cur_sites[s['id']]['token']
    return new


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
            if 'racks' not in loaded:                      # migrate the old single-rack config
                r = loaded.pop('rack', None) or {'totalU': 18, 'units': []}
                loaded['racks'] = [{'id': 'rack0', 'name': loaded.get('settings', {}).get('title') or 'Серверный шкаф',
                                    'totalU': int(r.get('totalU') or 18), 'units': r.get('units') or []}]
            loaded.pop('rack', None)
            for k, v in DEFAULT.items():
                loaded.setdefault(k, copy.deepcopy(v))
            for k, v in DEFAULT['settings'].items():
                loaded['settings'].setdefault(k, copy.deepcopy(v))
            self.cfg = loaded
        self.events = self._load('events.json', [])
        self.history = self._load('history.json', {})
        self.cable = self._load('cable.json', {})          # {device_id: {port: last cable test}}

    def set_cable(self, did, port, res):
        with self.lock:
            self.cable.setdefault(did, {})[str(port)] = res
            self._dump('cable.json', self.cable)
            self.bump()

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

    rev = 0                                                  # bumped on every change; the server caches its view by it

    def bump(self):
        self.rev += 1

    def save(self):
        with self.lock:
            self._dump('config.json', self.cfg)
            self.bump()

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
            for r in self.cfg['racks']:
                for u in r['units']:
                    if u.get('deviceIds'):
                        u['deviceIds'] = [x for x in u['deviceIds'] if x != did]
                        u['deviceId'] = (u['deviceIds'] or [None])[0]
                    if u.get('deviceId') == did:
                        u['deviceId'] = None
            self.save()
            if self.cable.pop(did, None) is not None:
                self._dump('cable.json', self.cable)

    # ── events / history ──
    def add_event(self, device_id, name, level, text):
        with self.lock:
            self.events.append({'t': time.time(), 'device': device_id, 'name': name, 'level': level, 'text': text})
            self.events = self.events[-500:]
            self.bump()
            try:
                self._dump('events.json', self.events)
            except OSError:
                pass

    def add_point(self, key, point, avg=False, sums=()):
        """~5-minute buckets for 24 hours. avg=True averages samples inside a bucket (traffic), else keeps the last.
        Fields in `sums` (error increments) are added up inside a bucket instead."""
        with self.lock:
            h = self.history.setdefault(key, [])
            if h and point['t'] - h[-1].get('t0', h[-1]['t']) < 290:
                if avg:
                    n = h[-1].get('n', 1)
                    for k, v in point.items():
                        if k in sums:
                            h[-1][k] = h[-1].get(k, 0) + v
                        elif k != 't' and isinstance(v, (int, float)):
                            h[-1][k] = round((h[-1].get(k, v) * n + v) / (n + 1))
                    h[-1]['n'] = n + 1
                    h[-1]['t'] = point['t']
                else:
                    h[-1] = dict(point, t0=h[-1].get('t0', h[-1]['t']))
            else:
                h.append(dict(point, t0=point['t']))
            del h[:-288]

    def all_units(self):
        """Every unit across all racks, each tagged with its rack id (for topology / the map)."""
        return [dict(u, rackId=r['id']) for r in self.cfg['racks'] for u in r['units']]

    # ── import of the old rack-constructor format ──
    @staticmethod
    def import_old_rack(old):
        units = []
        for u in old.get('units', []):
            units.append({'id': u.get('id') or 'u' + secrets.token_hex(3), 'name': u.get('name', ''), 'type': u.get('type', 'other'),
                          'uSize': int(u.get('uSize') or 1), 'uStart': int(u.get('uStart') or 1), 'side': u.get('side') or 'front',
                          'color': u.get('color') or '#0A84FF', 'deviceId': None, 'notes': u.get('config') if isinstance(u.get('config'), str) else '',
                          'webUrl': u.get('webUrl') or ''})
        return {'id': 'rack0', 'name': old.get('name') or 'Серверный шкаф', 'totalU': int(old.get('totalU') or 18), 'units': units}
