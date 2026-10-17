"""Remote sites (the «Zabbix proxy» idea): a second Rack Live in «collector» mode (rackd/collector.py) stands in another place — an office, a dacha, a relative's flat —
watches that network on its own, and PUSHES what it sees to this one over one outgoing HTTPS connection. No white IP, no port forwarding, no VPN is needed at the remote place.

Here, in the centre: a site has a name and a secret key; what the collector sends becomes ordinary devices of type «site_node» (marked with the site's name, drawn as remote
devices on the map, counted by the health check and the alerts). Nothing from the remote place can reach into this installation: the key only lets it deliver data."""
import base64, json, re, secrets, time

MAX_DEVICES = 200
KEEP = ('summary', 'metrics', 'storage', 'services', 'sections', 'ports')
KINDS = {'router', 'switch', 'nas', 'server', 'camera', 'ap', 'phone', 'pc', 'printer', 'ups', 'other', 'tv', 'iot', 'nvr', 'vps', 'speaker', 'modem'}


def decode_key(key):
    """«RL1.<base64url(json {u: address, t: token})>» → (address, token); ValueError when it is not a site key"""
    try:
        raw = str(key or '').strip()
        if not raw.startswith('RL1.'):
            raise ValueError
        b = raw[4:].replace('-', '+').replace('_', '/')
        j = json.loads(base64.b64decode(b + '=' * (-len(b) % 4)).decode('utf-8'))
        u, t = str(j['u']).rstrip('/'), str(j['t'])
        if not re.match(r'^https?://[^\s/]+', u) or not re.match(r'^[A-Za-z0-9_\-]{16,80}$', t):
            raise ValueError
        return u, t
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('это не ключ площадки: скопируйте его целиком из «Инструменты → Удалённые площадки» на главной установке')


def encode_key(url, token):
    return 'RL1.' + base64.urlsafe_b64encode(json.dumps({'u': url, 't': token}, separators=(',', ':')).encode()).decode().rstrip('=')


class Sites:
    def __init__(self, app):
        self.app = app
        self.links = {}                      # site id → rackd.sitelink.Link: the open control channel of that site

    @property
    def items(self):
        return self.app.store.cfg.setdefault('sites', [])

    def _devices(self, sid):
        return [d for d in self.app.store.cfg['devices'] if d.get('siteId') == sid]

    def public(self):
        out = []
        now = time.time()
        for s in self.items:
            ds = self._devices(s['id'])
            st = [(self.app.states.get(d['id']) or {}).get('status') for d in ds]
            out.append({'id': s['id'], 'name': s['name'], 'created': s.get('created'), 'last': s.get('last'), 'version': s.get('version'), 'ip': s.get('ip'),
                        'devices': len(ds), 'online': sum(1 for x in st if x in ('online', 'warning')), 'alive': bool(s.get('last')) and now - s['last'] < 300,
                        'link': bool(self.links.get(s['id']) and not self.links[s['id']].dead), 'level': (self.links.get(s['id']).caps.get('level') if self.links.get(s['id']) and not self.links[s['id']].dead else None)})
        return out

    def link(self, sid):
        l = self.links.get(sid)
        return l if l and not l.dead else None

    def rpc(self, sid, op, args):
        l = self.link(sid)
        if not l:
            raise RuntimeError('канал с площадкой не подключён: на площадке управление выключено или нет связи')
        return l.request(op, args)

    def create(self, name):
        name = re.sub(r'\s+', ' ', str(name or '')).strip()[:40]
        if not name:
            raise ValueError('назовите площадку')
        if any(s['name'].lower() == name.lower() for s in self.items):
            raise ValueError('площадка с таким названием уже есть')
        s = {'id': secrets.token_hex(3), 'name': name, 'token': secrets.token_urlsafe(24), 'created': int(time.time())}
        self.items.append(s)
        self.app.store.save()
        return s

    def get(self, sid):
        return next((s for s in self.items if s['id'] == sid), None)

    def remove(self, sid):
        s = self.get(sid)
        if not s:
            raise ValueError('нет такой площадки')
        for d in self._devices(sid):
            self.app.store.delete_device(d['id'])
            self.app.states.pop(d['id'], None)
        self.app.store.cfg['sites'] = [x for x in self.items if x['id'] != sid]
        self.app.store.save()
        self.app.store.add_event(None, 'Площадки', 'info', f"площадка «{s['name']}» удалена вместе с её устройствами")

    def ingest(self, token, body, ip):
        """what a collector sent → the site's devices. Returns the answer for the collector. Raises PermissionError (bad key) / ValueError (bad data)."""
        site = next((s for s in self.items if token and secrets.compare_digest(s['token'], token)), None)
        if not site:
            raise PermissionError('неверный ключ площадки')
        return self.apply(site, body, ip)

    def apply(self, site, body, ip):
        devs = body.get('devices')
        if not isinstance(devs, list) or len(devs) > MAX_DEVICES:
            raise ValueError(f'нужен список устройств, не больше {MAX_DEVICES}')
        st = self.app.store
        keys, now = set(), time.time()
        for it in devs:
            if not isinstance(it, dict) or not isinstance(it.get('state'), dict):
                continue
            key = re.sub(r'[^A-Za-z0-9_.\-]', '', str(it.get('key') or '')).strip('.')[:40]
            if not key:
                continue
            keys.add(key)
            did = f"s{site['id']}-{key}"
            kind = it.get('kind') if it.get('kind') in KINDS else 'other'
            name = re.sub(r'\s+', ' ', str(it.get('name') or key)).strip()[:60]
            d = st.device(did)
            if not d:
                d = {'id': did, 'driver': 'site_node', 'enabled': True, 'location': 'remote', 'staleMinutes': 6}
                with st.lock:
                    st.cfg['devices'].append(d)
            d.update(name=name, kind=kind, siteId=site['id'], siteName=site['name'], siteKey=key, origDriver=str(it.get('driver') or '')[:30],
                     notes=f"Площадка «{site['name']}»", host='')
            src = it['state']
            state = {k: src[k] for k in KEEP if k in src}
            if isinstance(src.get('clientsCount'), int):
                state.setdefault('sections', []).append({'title': 'Сеть площадки', 'rows': [['Клиентов', src['clientsCount']]]})
            smry = dict(state.get('summary') or {})
            for k in ('mac', 'macs'):
                smry.pop(k, None)
            # the remote LAN has its own 192.168.x.x: such an address must never be taken for an address of THIS network (map, «found in the network», clients)
            smry['ip'] = f"{site['name']} · {smry['ip']}" if smry.get('ip') else site['name']
            state['summary'] = smry
            state['ports'] = [dict(p, peers=[]) for p in (state.get('ports') or []) if isinstance(p, dict)][:64]
            state.update(status=src.get('status') if src.get('status') in ('online', 'offline', 'warning') else 'online', error=src.get('error') if isinstance(src.get('error'), str) else None,
                         updated=now, durationMs=0)
            self.app.apply_state(d, state)
        for d in self._devices(site['id']):                 # a device that is gone from the remote place is gone here too
            if d.get('siteKey') not in keys:
                st.delete_device(d['id'])
                self.app.states.pop(d['id'], None)
        site.update(last=int(now), version=str(body.get('version') or '')[:20], ip=ip, count=len(keys))
        st.save()
        return {'ok': True, 'poll': int(st.cfg['settings'].get('poll') or 60), 'devices': len(keys)}

    def demo_seed(self):
        """the demo office has one remote site with three devices, so the pages have something to show"""
        if self.items:
            return
        s = {'id': 'demo1', 'name': 'Склад (филиал)', 'token': secrets.token_urlsafe(24), 'created': int(time.time()) - 86400 * 20}
        self.items.append(s)
        self.apply(s, {'version': 'demo', 'devices': [
            {'key': 'rt', 'name': 'Роутер склада', 'driver': 'keenetic', 'kind': 'router', 'state': {'status': 'online', 'summary': {'ip': '192.168.1.1', 'cpu': 12, 'mem': 41, 'uptime': 9 * 86400, 'model': 'Keenetic Viva'}, 'clientsCount': 14}},
            {'key': 'cam', 'name': 'Камера склада', 'driver': 'ping', 'kind': 'camera', 'state': {'status': 'online', 'summary': {'ip': '192.168.1.50'}}},
            {'key': 'nas', 'name': 'Сервер склада', 'driver': 'ssh', 'kind': 'server', 'state': {'status': 'warning', 'summary': {'ip': '192.168.1.10', 'cpu': 64, 'mem': 93, 'uptime': 31 * 86400},
                                                                                              'storage': {'volumes': [{'name': '/', 'status': 'normal', 'used': 460e9, 'total': 500e9}], 'disks': []}}}]}, '203.0.113.7')
