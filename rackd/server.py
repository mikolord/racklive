"""HTTP API, static files and the background poller."""
import concurrent.futures, json, mimetypes, os, re, secrets, signal, threading, time, traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import analysis, auth, topology
from .drivers import REGISTRY, load_all
from .store import Store
from .util import DriverError

VERSION = '2.0.0'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.environ.get('RL_WEB', os.path.join(ROOT, 'web'))
DATA = os.environ.get('RL_DATA', os.path.join(ROOT, 'data'))
DEMO = os.environ.get('RL_DEMO', '').lower() in ('1', 'true', 'yes')     # demo office, no login, nothing real is touched


def log(*a):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


class App:
    def __init__(self):
        load_all()
        self.store = Store(DATA)
        self.sessions = auth.Sessions(DATA)
        self.states = {}
        self.running = set()
        self.last_start = {}
        self.lock = threading.RLock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

    # ───────── polling ─────────
    def poll_device(self, d):
        drv = REGISTRY.get(d.get('driver'))
        t = time.time()
        try:
            st = drv.poll(d)
            st['error'] = None
        except DriverError as e:
            st = {'status': 'offline', 'error': str(e)}
        except Exception as e:
            st = {'status': 'offline', 'error': f'{type(e).__name__}: {e}'}
            if os.environ.get('RL_DEBUG'):
                traceback.print_exc()
        st['updated'] = time.time()
        st['durationMs'] = round((time.time() - t) * 1000)
        self.apply_state(d, st)
        return st

    def apply_state(self, d, st):
        with self.lock:
            old = self.states.get(d['id']) or {}
            if st.get('status') == 'offline' and old.get('status') not in (None, 'offline') and old.get('summary'):
                keep = {k: old[k] for k in ('summary', 'ports', 'children', 'storage', 'sections') if k in old}
                st = dict(keep, **st)              # keep the last known data, but show the device as offline
            # per-port throughput from octet counters
            dt = (st.get('updated') or 0) - (old.get('updated') or 0)
            if st.get('status') != 'offline' and 0 < dt < 3600:
                oldp = {p.get('n'): p for p in old.get('ports') or []}
                for p in st.get('ports') or []:
                    o = oldp.get(p.get('n'))
                    if o and p.get('rxBytes') is not None and o.get('rxBytes') is not None and p.get('txBytes') is not None and o.get('txBytes') is not None:
                        drx, dtx = p['rxBytes'] - o['rxBytes'], p['txBytes'] - o['txBytes']
                        if drx >= 0 and dtx >= 0:
                            p['rxBps'], p['txBps'] = round(drx * 8 / dt), round(dtx * 8 / dt)
                            self.store.add_point(f"{d['id']}:p{p['n']}", {'t': int(st['updated']), 'rx': p['rxBps'], 'tx': p['txBps']}, avg=True)
            self.states[d['id']] = st
            prev, cur = old.get('status'), st.get('status')
            if prev is None and cur == 'offline':
                self.store.add_event(d['id'], d.get('name'), 'offline', 'нет связи' + (f": {st.get('error')}" if st.get('error') else ''))
            if prev and prev != cur:
                text = {'offline': 'нет связи' + (f": {st.get('error')}" if st.get('error') else ''), 'online': 'снова в сети',
                        'warning': 'требует внимания'}.get(cur, cur)
                self.store.add_event(d['id'], d.get('name'), cur, text)
            s = st.get('summary') or {}
            point = {'t': int(st['updated'])}
            for k in ('cpu', 'mem', 'temp'):
                if isinstance(s.get(k), (int, float)):
                    point[k] = s[k]
            for m in st.get('metrics') or []:
                if m.get('label') in ('Задержка', 'PoE') and isinstance(m.get('value'), (int, float)):
                    point['ms' if m['label'] == 'Задержка' else 'poe'] = m['value']
            if len(point) > 1:
                self.store.add_point(d['id'], point)

    def poller(self):
        last_save = time.time()
        while True:
            try:
                now = time.time()
                every = max(15, int(self.store.cfg['settings'].get('poll') or 60))
                for d in list(self.store.cfg['devices']):
                    if not d.get('enabled', True):
                        continue
                    drv = REGISTRY.get(d.get('driver'))
                    if not drv:
                        continue
                    if getattr(drv, 'push', False):
                        st = self.states.get(d['id'])
                        stale = float(d.get('staleMinutes') or 5) * 60
                        if st and st.get('status') != 'offline' and now - st.get('updated', 0) > stale:
                            self.apply_state(d, dict(st, status='offline', error='агент давно не присылал данные', updated=st.get('updated')))
                        elif not st:
                            self.states[d['id']] = {'status': 'offline', 'error': 'агент ещё не подключался', 'updated': None}
                        continue
                    if d['id'] in self.running or now - self.last_start.get(d['id'], 0) < every:
                        continue
                    self.last_start[d['id']] = now
                    self.running.add(d['id'])
                    fut = self.pool.submit(self.poll_device, d)
                    fut.add_done_callback(lambda f, i=d['id']: self.running.discard(i))
                if now - last_save > 600:
                    self.store.save_runtime()
                    last_save = now
            except Exception:
                traceback.print_exc()
            time.sleep(3)

    # ───────── view model ─────────
    def peer_index(self):
        idx = {}
        for did, st in self.states.items():
            for c in st.get('clients') or []:
                if c.get('mac'):
                    idx.setdefault(c['mac'].lower(), {'name': c.get('name'), 'ip': c.get('ip'), 'kind': c.get('kind'), 'segment': c.get('segment')})
        for d in self.store.cfg['devices']:
            st = self.states.get(d['id']) or {}
            mac = ((st.get('summary') or {}).get('mac') or d.get('mac') or '').lower()
            if mac:
                idx[mac] = {'name': d.get('name'), 'ip': (st.get('summary') or {}).get('ip'), 'kind': d.get('kind'), 'deviceId': d['id']}
            for ch in st.get('children') or []:
                if ch.get('mac'):
                    idx.setdefault(ch['mac'].lower(), {'name': ch.get('name'), 'ip': ch.get('ip'), 'kind': 'ap'})
        return idx

    def view(self, authed):
        cfg = self.store.cfg
        idx = self.peer_index()
        devices = []
        for d in cfg['devices']:
            st = json.loads(json.dumps(self.states.get(d['id']) or {'status': 'unknown'}))
            tests = self.store.cable.get(d['id']) or {}
            for p in st.get('ports') or []:
                if str(p.get('n')) in tests:
                    p['cable'] = tests[str(p['n'])]
                for peer in p.get('peers') or []:
                    peer.update({k: v for k, v in (idx.get(peer['mac'].lower()) or {}).items() if v})
            pd = self.store.public_device(d) if authed else {k: d.get(k) for k in ('id', 'name', 'driver', 'kind', 'location', 'site', 'notes', 'enabled', 'host')}
            if not authed:
                pd['host'] = ''
            pd['state'] = st
            devices.append(pd)
        units = self.store.all_units()
        topo = topology.build(cfg['devices'], self.states, units, cfg['map'].get('links'),
                              cfg['settings'].get('showClients', True), REGISTRY)
        try:
            # analysis always sees the clients, even when the map hides them
            full = topo if cfg['settings'].get('showClients', True) else topology.build(
                cfg['devices'], self.states, units, cfg['map'].get('links'), True, REGISTRY)
            health = analysis.analyze(full, cfg['devices'], self.states, self.store.cable)
        except Exception:
            traceback.print_exc()
            health = None
        return {'health': health, 'version': VERSION, 'authed': authed, 'setupNeeded': not cfg.get('auth'), 'demo': DEMO,
                'settings': cfg['settings'], 'drivers': [drv.schema() for drv in REGISTRY.values()],
                'devices': devices, 'racks': cfg['racks'], 'map': cfg['map'], 'plan': cfg.get('plan', {'buildings': [], 'links': []}), 'topology': topo,
                'events': self.store.events[-60:][::-1], 'now': time.time()}


APP = None


class Handler(BaseHTTPRequestHandler):
    server_version = 'RackLive/' + VERSION

    def log_message(self, fmt, *a):
        if os.environ.get('RL_DEBUG'):
            super().log_message(fmt, *a)

    # ── helpers ──
    def client_ip(self):
        return (self.headers.get('X-Forwarded-For') or self.client_address[0]).split(',')[0].strip()

    def token(self):
        c = SimpleCookie(self.headers.get('Cookie') or '')
        return c['rl_session'].value if 'rl_session' in c else None

    def authed(self):
        return DEMO or APP.sessions.valid(self.token())

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 5_000_000:
            raise ValueError('слишком большой запрос')
        raw = self.rfile.read(n) if n else b''
        return json.loads(raw) if raw else {}

    def send(self, obj, code=200, headers=None):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def err(self, msg, code=400):
        self.send({'error': msg}, code)

    def cookie(self, tok, max_age):
        secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
        return f'rl_session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}'

    def need_admin(self):
        if not self.authed():
            self.err('нужен вход администратора', 401)
            return False
        return True

    # ── static ──
    def static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        full = os.path.normpath(os.path.join(WEB, path.lstrip('/')))
        if not full.startswith(os.path.normpath(WEB)) or not os.path.isfile(full):
            full = os.path.join(WEB, 'index.html')          # SPA fallback
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if full.endswith('.js'):
            ctype = 'application/javascript'
        with open(full, 'rb') as f:
            b = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith(('text', 'application/javascript', 'application/json')) else ''))
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-cache' if full.endswith(('.html', '.js', '.css')) else 'max-age=86400')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.end_headers()
        self.wfile.write(b)

    # ── routes ──
    def do_GET(self):
        path = self.path.split('?')[0]
        try:
            if path == '/api/state':
                a = self.authed()
                cfg = APP.store.cfg
                if not a and (not cfg.get('auth') or not cfg['settings'].get('publicView')):
                    return self.send({'authed': False, 'setupNeeded': not cfg.get('auth'), 'needLogin': bool(cfg.get('auth')),
                                      'settings': {'title': cfg['settings'].get('title')}, 'version': VERSION})
                return self.send(APP.view(a))
            m = re.match(r'/api/history/(\w+)$', path)
            if m:
                if not self.authed() and not APP.store.cfg['settings'].get('publicView'):
                    return self.err('нужен вход', 401)
                q = dict(x.split('=', 1) for x in self.path.split('?', 1)[1].split('&') if '=' in x) if '?' in self.path else {}
                key = m.group(1) + (f":p{int(q['port'])}" if q.get('port', '').isdigit() else '')
                return self.send(APP.store.history.get(key, []))
            if path == '/api/export':
                if not self.need_admin():
                    return
                b = json.dumps(APP.store.cfg, ensure_ascii=False, indent=1).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="racklive-backup.json"')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if path.startswith('/api/'):
                return self.err('не найдено', 404)
            return self.static(path)
        except Exception as e:
            traceback.print_exc()
            return self.err(str(e), 500)

    def do_POST(self):
        self.route('POST')

    def do_PUT(self):
        self.route('PUT')

    def do_DELETE(self):
        self.route('DELETE')

    def route(self, method):
        path = self.path.split('?')[0]
        st = APP.store
        try:
            body = self.body()
            # ── auth ──
            if path == '/api/setup' and method == 'POST':
                if st.cfg.get('auth'):
                    return self.err('уже настроено', 403)
                pw = body.get('password') or ''
                if len(pw) < 8:
                    return self.err('пароль должен быть не короче 8 символов')
                st.cfg['auth'] = auth.hash_password(pw)
                if body.get('title'):
                    st.cfg['settings']['title'] = body['title'][:80]
                st.save()
                tok = APP.sessions.create()
                return self.send({'ok': True}, headers={'Set-Cookie': self.cookie(tok, auth.SESSION_DAYS * 86400)})
            if path == '/api/login' and method == 'POST':
                ip = self.client_ip()
                if APP.sessions.throttled(ip):
                    return self.err('слишком много попыток, подождите 5 минут', 429)
                if not auth.check_password(st.cfg.get('auth'), body.get('password') or ''):
                    APP.sessions.fail(ip)
                    st.add_event(None, 'Вход', 'warning', f'неверный пароль с адреса {ip}')
                    time.sleep(1)
                    return self.err('неверный пароль', 401)
                APP.sessions.ok(ip)
                st.add_event(None, 'Вход', 'info', f'администратор вошёл с адреса {ip}')
                tok = APP.sessions.create()
                return self.send({'ok': True}, headers={'Set-Cookie': self.cookie(tok, auth.SESSION_DAYS * 86400)})
            if path == '/api/logout' and method == 'POST':
                APP.sessions.drop(self.token())
                return self.send({'ok': True}, headers={'Set-Cookie': self.cookie('', 0)})
            # ── agent push (token auth, no session) ──
            if path == '/api/agent' and method == 'POST':
                tok = (self.headers.get('Authorization') or '').replace('Bearer ', '').strip()
                d = next((x for x in st.cfg['devices'] if tok and x.get('agentToken') == tok), None)
                if not d:
                    return self.err('неверный токен агента', 401)
                state = {k: body[k] for k in ('summary', 'metrics', 'storage', 'services', 'sections', 'ports') if k in body}
                state.update(status=body.get('status') or 'online', error=None, updated=time.time(), durationMs=0)
                state.setdefault('summary', {})['ip'] = state['summary'].get('ip') or self.client_ip()
                APP.apply_state(d, state)
                return self.send({'ok': True, 'poll': int(st.cfg['settings'].get('poll') or 60)})

            if not self.need_admin():
                return
            # ── admin API ──
            if path == '/api/settings' and method == 'PUT':
                s = st.cfg['settings']
                for k in ('title', 'poll', 'publicView', 'showClients', 'vlans'):
                    if k in body:
                        s[k] = body[k]
                if body.get('newPassword'):
                    if not auth.check_password(st.cfg['auth'], body.get('oldPassword') or ''):
                        return self.err('текущий пароль неверный', 403)
                    if len(body['newPassword']) < 8:
                        return self.err('новый пароль должен быть не короче 8 символов')
                    st.cfg['auth'] = auth.hash_password(body['newPassword'])
                    APP.sessions.drop_all()
                    tok = APP.sessions.create()
                    st.save()
                    return self.send({'ok': True}, headers={'Set-Cookie': self.cookie(tok, auth.SESSION_DAYS * 86400)})
                st.save()
                return self.send({'ok': True})
            if path == '/api/racks' and method == 'PUT':
                racks = body.get('racks')
                if not isinstance(racks, list) or not racks:
                    return self.err('неверные данные')
                out = []
                for r in racks:
                    units = r.get('units') if isinstance(r.get('units'), list) else []
                    kind = r.get('kind') if r.get('kind') in ('rack', 'box', 'place') else 'rack'
                    total = max(1, min(60, int(r.get('totalU') or 18)))
                    if kind == 'rack':                          # only a real rack has a fixed U height to respect
                        need = max([int(u.get('uStart') or 1) + int(u.get('uSize') or 1) - 1 for u in units] + [1])
                        if total < need:
                            return self.err(f"«{r.get('name') or 'Шкаф'}»: шкаф меньше занятого места — оборудование стоит до U{need}")
                    out.append({'id': r.get('id') or 'rack' + secrets.token_hex(3), 'name': (r.get('name') or 'Место').strip()[:40],
                                'kind': kind, 'totalU': total, 'units': units})
                st.cfg['racks'] = out
                st.save()
                return self.send({'ok': True})
            if path == '/api/map' and method == 'PUT':
                for k in ('positions', 'links', 'collapsed'):
                    if k in body:
                        st.cfg['map'][k] = body[k]
                st.save()
                return self.send({'ok': True})
            if path == '/api/plan' and method == 'PUT':
                b = body.get('buildings')
                if not isinstance(b, list):
                    return self.err('неверные данные')
                st.cfg['plan'] = {'buildings': b, 'links': body.get('links') if isinstance(body.get('links'), list) else []}
                st.save()
                return self.send({'ok': True})
            if path == '/api/import' and method == 'POST':
                data = body.get('data') or {}
                if data.get('version') == 2 and 'devices' in data:     # full backup
                    keep_auth = st.cfg.get('auth')
                    st.cfg = data
                    st.cfg['auth'] = keep_auth
                else:
                    st.cfg['racks'] = [st.import_old_rack(data)]
                st.save()
                return self.send({'ok': True})
            if path == '/api/devices' and method == 'POST':
                if body.get('driver') not in REGISTRY:
                    return self.err('неизвестный тип устройства')
                d = st.upsert_device(body)
                APP.last_start.pop(d['id'], None)
                st.add_event(d['id'], d.get('name'), 'info', 'устройство добавлено')
                return self.send({'ok': True, 'device': st.public_device(d), 'agentToken': d.get('agentToken')})
            m = re.match(r'/api/devices/(\w+)(?:/(\w+))?$', path)
            if m:
                did, sub = m.group(1), m.group(2)
                d = st.device(did)
                if not d:
                    return self.err('устройство не найдено', 404)
                if sub is None and method == 'PUT':
                    d = st.upsert_device(body, did)
                    APP.last_start.pop(did, None)
                    return self.send({'ok': True, 'device': st.public_device(d)})
                if sub is None and method == 'DELETE':
                    st.add_event(None, d.get('name'), 'info', 'устройство удалено')
                    st.delete_device(did)
                    APP.states.pop(did, None)
                    return self.send({'ok': True})
                if sub == 'poll' and method == 'POST':
                    return self.send({'ok': True, 'state': APP.poll_device(d)})
                if sub == 'token' and method == 'POST':
                    return self.send({'ok': True, 'agentToken': d.get('agentToken')})
                if sub == 'action' and method == 'POST':
                    drv = REGISTRY.get(d.get('driver'))
                    try:
                        msg = drv.action(d, body.get('action'), body.get('params') or {})
                    except Exception as e:
                        st.add_event(did, d.get('name'), 'warning', f"действие не выполнено: {e}")
                        raise
                    act = next((a for a in drv.actions if a['id'] == body.get('action')), {})
                    if isinstance(msg, dict):
                        # measurements (cable test): keep the result next to the port, nothing to re-poll
                        res = msg
                        if res.get('cable') is not None:
                            st.set_cable(did, res.get('port'), res['cable'])
                        level = {'ok': 'info', 'empty': 'info'}.get((res.get('cable') or {}).get('verdict'), 'warning')
                        st.add_event(did, d.get('name'), level, res.get('message', ''))
                        return self.send({'ok': True, 'message': res.get('message'), 'cable': res.get('cable'), 'port': res.get('port')})
                    if act.get('instant'):
                        # quick actions (switches): re-read the device right away and hand the fresh state back
                        if act.get('scope') != 'entity':
                            st.add_event(did, d.get('name'), 'info', f"{msg}")
                        state = APP.poll_device(d)
                        return self.send({'ok': True, 'message': msg, 'state': json.loads(json.dumps(state))})
                    st.add_event(did, d.get('name'), 'info', f"{msg}")
                    threading.Thread(target=lambda: (time.sleep(3), APP.poll_device(d)), daemon=True).start()
                    return self.send({'ok': True, 'message': msg})
            if path == '/api/test' and method == 'POST':
                drv = REGISTRY.get(body.get('driver'))
                if not drv:
                    return self.err('неизвестный тип')
                cfg = dict(body)
                if body.get('id'):
                    old = st.device(body['id']) or {}
                    for k in ('password', 'token'):
                        if not cfg.get(k):
                            cfg[k] = old.get(k)
                try:
                    res = drv.poll(cfg)
                    s = res.get('summary') or {}
                    return self.send({'ok': True, 'summary': s, 'ports': len(res.get('ports') or []), 'clients': len(res.get('clients') or [])})
                except Exception as e:
                    return self.send({'ok': False, 'error': str(e)})
            return self.err('не найдено', 404)
        except DriverError as e:
            return self.err(str(e), 400)
        except NotImplementedError as e:
            return self.err(str(e) or 'не поддерживается', 400)
        except Exception as e:
            traceback.print_exc()
            return self.err(f'{type(e).__name__}: {e}', 500)


def main():
    global APP
    APP = App()
    if DEMO:
        from .drivers import demo
        demo.seed(APP.store)
        APP.store.cfg['auth'] = APP.store.cfg.get('auth') or {'demo': True}
        log('DEMO mode: made-up office network, login disabled')
    threading.Thread(target=APP.poller, daemon=True).start()
    port = int(os.environ.get('RL_PORT', '8080'))
    log(f'Rack Live {VERSION}: http://0.0.0.0:{port}  data={DATA}  drivers={", ".join(REGISTRY)}')
    APP.store.add_event(None, 'Rack Live', 'info', f'сервер запущен (версия {VERSION})')

    def stop(*_):
        APP.store.save_runtime()
        os._exit(0)
    signal.signal(signal.SIGTERM, stop)
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    finally:
        APP.store.save_runtime()
