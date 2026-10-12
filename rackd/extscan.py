"""Outside port check: a server outside the home network (any device «Сервер / VPS по SSH») knocks on the home
public IP — which TCP ports really answer from the internet. The result feeds the security advisor.
"""
import threading, time, urllib.request

COMMON = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 1723, 1900, 3306, 3389, 5000, 5001, 5432, 5900, 6379, 8080, 8123, 8443, 9998, 27017]
EVERY = 24 * 3600


class ExtScan:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.last = self.store._load('extscan.json', {})       # {t, ip, via, viaName, checked, open, error}
        self.running = False

    def cfg(self):
        return dict({'enabled': True, 'device': None}, **(self.store.cfg.get('extscan') or {}))

    def scanner(self):
        """The chosen SSH server, else the first remote one."""
        devs = [d for d in self.store.cfg['devices'] if d.get('driver') in ('ssh', 'demo_server') and d.get('enabled', True)]
        want = self.cfg().get('device')
        return next((d for d in devs if d['id'] == want), None) or next((d for d in devs if d.get('location') == 'remote'), None)

    def public_ip(self):
        for st in self.app.states.values():
            for p in st.get('ports') or []:
                if p.get('kind') == 'wan' and p.get('ip') and not p['ip'].startswith(('10.', '192.168.', '172.', '100.')):
                    return p['ip']
        try:
            return urllib.request.urlopen('https://api.ipify.org', timeout=6).read().decode().strip()
        except Exception:
            return None

    def ports(self):
        """Common ports + everything the routers forward or expose."""
        ps = set(COMMON)
        for st in self.app.states.values():
            sec = st.get('security') or {}
            for f in sec.get('forwards') or []:
                try:
                    ps.add(int(str(f['port']).split('-')[0]))
                except ValueError:
                    pass
            for r in (sec.get('remote') or {}).values():
                for k in ('port', 'sslPort'):
                    if r.get(k):
                        ps.add(int(r[k]))
        return sorted(ps)

    def due(self):
        return self.cfg()['enabled'] and not self.running and time.time() - (self.last.get('t') or 0) >= EVERY and self.scanner()

    def start(self):
        if self.running:
            return False
        self.running = True
        self.store.bump()
        threading.Thread(target=self.run, daemon=True).start()
        return True

    def run(self):
        from .drivers import REGISTRY
        try:
            d, ip = self.scanner(), self.public_ip()
            rec = {'t': int(time.time()), 'ip': ip, 'via': d and d['id'], 'viaName': d and d.get('name'), 'checked': self.ports(), 'open': []}
            if not d:
                rec['error'] = 'нет внешнего сервера: добавьте любой VPS как «Сервер / VPS по SSH»'
            elif not ip:
                rec['error'] = 'не удалось узнать внешний IP'
            else:
                try:
                    rec['open'] = REGISTRY[d['driver']].port_scan(d, ip, rec['checked'])
                except Exception as e:
                    rec['error'] = str(e)
            self.last = rec
            self.store._dump('extscan.json', rec)
            self.store.bump()
            if not rec.get('error'):
                self.store.add_event(None, 'Проверка снаружи', 'info', f"с {rec['viaName']}: из {len(rec['checked'])} портов открыто {len(rec['open'])}"
                                     + (f" ({', '.join(map(str, rec['open']))})" if rec['open'] else ''))
        finally:
            self.running = False
            self.store.bump()

    def public(self):
        d = self.scanner()
        return dict(self.last, running=self.running, scanner=d and {'id': d['id'], 'name': d.get('name')}, cfg=self.cfg())
