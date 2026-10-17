"""«Collector» mode: THIS Rack Live stands in a remote place (an office, a dacha) and reports to the main Rack Live (rackd/sites.py).

It watches its own network as usual (drivers, scans, plugins) and every minute sends the main one the list of its devices with their latest state: names, kinds, status,
CPU / memory, disks, ports without the connected-MAC lists, services. Never passwords, keys or other secrets. One outgoing HTTPS request — nothing has to be opened at this place.

Control (optional, off by default): when the owner of THIS installation allows it, the collector also keeps an outgoing WebSocket to the main one (rackd/sitelink.py) and, on its
requests, shows the full state of a device, presses a driver button or opens a terminal on a device — with this installation's own drivers and saved logins, so no password ever
travels. Levels: look / actions / terminal. Every use is written to this installation's journal."""
import base64, json, queue, select, ssl, threading, time, urllib.error, urllib.request

from . import sites as sites_mod, sitelink, terminal

ALLOWED = sites_mod.KEEP
LEVELS = {'off': 0, 'view': 1, 'actions': 2, 'terminal': 3}
LEVEL_TEXT = {'off': 'выключено', 'view': 'смотреть', 'actions': 'смотреть и нажимать кнопки устройств', 'terminal': 'смотреть, нажимать кнопки и открывать терминал'}
MAX_JSON = 700_000


class Collector:
    def __init__(self, app, version=''):
        self.app, self.version = app, version
        self.status = {'last': None, 'error': None, 'devices': 0}
        self.link = {'connected': False, 'error': None, 'since': None}
        self.wake = threading.Event()
        self.sessions = {}

    def cfg(self):
        return self.app.store.cfg.get('collector') or {}

    def level(self):
        lv = self.cfg().get('level')
        return lv if lv in LEVELS else 'off'

    def public(self):
        c = self.cfg()
        return {'enabled': bool(c.get('enabled')), 'server': c.get('url') or '', 'keySet': bool(c.get('token')), 'insecure': bool(c.get('insecure')), 'level': self.level(), **self.status,
                'link': dict(self.link)}

    def configure(self, key=None, enabled=None, insecure=None, level=None):
        c = dict(self.cfg())
        if key:
            c['url'], c['token'] = sites_mod.decode_key(key)
        if enabled is not None:
            c['enabled'] = bool(enabled)
        if insecure is not None:
            c['insecure'] = bool(insecure)
        if level is not None:
            if level not in LEVELS:
                raise ValueError('уровень: off, view, actions или terminal')
            c['level'] = level
            self.app.store.add_event(None, 'Площадки', 'warning' if level != 'off' else 'info', f"управление с главной установки: {LEVEL_TEXT[level]}")
        if c.get('enabled') and not c.get('token'):
            raise ValueError('сначала вставьте ключ площадки')
        self.app.store.cfg['collector'] = c
        self.app.store.save()
        self.wake.set()

    def payload(self):
        items = []
        for d in self.app.store.cfg['devices']:
            if not d.get('enabled', True) or d.get('driver') in ('site_node',):      # what came from other sites is not sent on (no loops)
                continue
            st = self.app.states.get(d['id'])
            if not st or st.get('status') is None:
                continue
            state = {k: st[k] for k in ALLOWED if k in st}
            state['status'], state['error'] = st.get('status'), st.get('error')
            state['clientsCount'] = len(st.get('clients') or [])
            from .drivers import REGISTRY
            drv = REGISTRY.get(d.get('driver'))
            items.append({'key': d['id'], 'name': d.get('name') or d['id'], 'driver': d.get('driver'), 'kind': d.get('kind') or getattr(drv, 'kind', 'other'), 'state': state})
        return {'version': self.version, 'devices': items[:sites_mod.MAX_DEVICES]}

    def push(self):
        c = self.cfg()
        if not c.get('token'):
            raise ValueError('ключ площадки не задан')
        body = json.dumps(self.payload(), ensure_ascii=False).encode()
        req = urllib.request.Request(c['url'] + '/api/site', data=body, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + c['token']})
        ctx = ssl._create_unverified_context() if c.get('insecure') else None
        try:
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                ans = json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            raise RuntimeError('главная установка отклонила ключ (площадка удалена или ключ другой)' if e.code == 401 else f'главная установка ответила ошибкой {e.code}')
        except Exception as e:
            raise RuntimeError(f'не удалось связаться с главной установкой ({type(e).__name__})')
        self.status.update(last=int(time.time()), error=None, devices=ans.get('devices', 0))
        return ans

    def loop(self):
        time.sleep(30)
        while True:
            wait = 60
            try:
                if self.cfg().get('enabled') and self.cfg().get('token'):
                    try:
                        wait = max(30, int(self.push().get('poll') or 60))
                    except Exception as e:
                        self.status['error'] = str(e)
                        wait = 60
            except Exception:
                pass
            self.wake.wait(wait)
            self.wake.clear()

    # ───────── the control channel ─────────
    def _want_link(self):
        c = self.cfg()
        return bool(c.get('enabled') and c.get('token') and self.level() != 'off')

    def link_loop(self):
        """keep the channel up while the owner allows control; try again with growing pauses"""
        time.sleep(35)
        pause = 5
        while True:
            if not self._want_link():
                self.link.update(connected=False, since=None)
                self.wake.wait(10)
                continue
            began = time.time()
            try:
                self._run_link()
                self.link['error'] = None
            except Exception as e:
                self.link['error'] = str(e)[:140] or type(e).__name__
            self.link.update(connected=False, since=None)
            pause = 5 if time.time() - began > 120 else min(60, pause * 2)       # a link that lived a while starts over quickly, one that cannot connect backs off
            self.wake.wait(pause)

    def _run_link(self):
        c = self.cfg()
        s, rest = sitelink.connect(c['url'], c['token'], c.get('insecure'))
        out, rd = queue.Queue(), terminal.Reader()

        def send(obj):
            out.put(json.dumps(obj, ensure_ascii=False).encode())
        self.link.update(connected=True, since=int(time.time()), error=None)
        send({'t': 'hello', 'version': self.version, 'level': self.level()})
        last_rx = last_ping = time.time()
        pending = [rest] if rest else []
        try:
            while True:
                try:
                    while True:
                        s.sendall(sitelink.client_frame(out.get_nowait(), 1))
                except queue.Empty:
                    pass
                if not self._want_link():
                    return
                if pending:
                    chunk = pending.pop()
                else:
                    r, _, _ = select.select([s], [], [], 0.25)
                    chunk = s.recv(65536) if r else None
                    if r and not chunk:
                        raise ConnectionError('главная установка закрыла соединение')
                for op, payload in (rd.feed(chunk) if chunk else []):
                    last_rx = time.time()
                    if op == 8:
                        return
                    if op == 9:
                        s.sendall(sitelink.client_frame(payload, 10))
                    elif op in (1, 2):
                        try:
                            self._handle(json.loads(payload), send)
                        except ValueError:
                            pass
                now = time.time()
                if now - last_ping > 25:
                    send({'t': 'ping'})
                    last_ping = now
                if now - last_rx > 80:
                    raise ConnectionError('главная установка не отвечает')
        finally:
            for p in list(self.sessions.values()):
                p.close('канал закрыт')
            self.sessions.clear()
            try:
                s.close()
            except OSError:
                pass

    def _handle(self, m, send):
        t = m.get('t')
        if t == 'req':
            def work():
                try:
                    send({'t': 'res', 'id': m.get('id'), 'result': self._op(m.get('op'), m.get('args') or {})})
                except Exception as e:
                    send({'t': 'res', 'id': m.get('id'), 'error': str(e)[:300] or type(e).__name__})
            threading.Thread(target=work, daemon=True).start()
        elif t == 'term_open':
            self._term_open(m, send)
        elif t == 'term':
            p = self.sessions.get(m.get('s'))
            if p:
                try:
                    p.write(base64.b64decode(m.get('d') or ''))
                except ValueError:
                    pass
        elif t == 'term_resize':
            p = self.sessions.get(m.get('s'))
            if p:
                p.resize(int(m.get('cols') or 80), int(m.get('rows') or 24))
        elif t == 'term_close':
            p = self.sessions.pop(m.get('s'), None)
            if p:
                p.close('закрыт')

    def _dev(self, key):
        d = next((x for x in self.app.store.cfg['devices'] if x['id'] == str(key) and x.get('driver') != 'site_node'), None)
        if not d:
            raise RuntimeError('такого устройства на площадке нет')
        return d

    def _need(self, level):
        if LEVELS[self.level()] < LEVELS[level]:
            raise RuntimeError(f"владелец площадки разрешил только: {LEVEL_TEXT[self.level()]}")

    def _op(self, op, a):
        from .drivers import REGISTRY
        if op == 'state':
            self._need('view')
            d = self._dev(a.get('key'))
            st = dict(self.app.states.get(d['id']) or {})
            for k in ('security', 'loops'):
                st.pop(k, None)
            drv = REGISTRY.get(d.get('driver'))
            acts = [{k: x.get(k) for k in ('id', 'label', 'scope', 'confirm', 'kind', 'fields') if x.get(k) is not None} for x in (getattr(drv, 'actions', None) or []) if x.get('scope') != 'security']
            term = False
            if LEVELS[self.level()] >= 3 and terminal.supported():
                try:
                    term = bool(self.app.hostnet.ssh_target(d)[0])
                except Exception:
                    term = False
            res = {'device': {'name': d.get('name'), 'kind': d.get('kind'), 'driver': d.get('driver'), 'title': getattr(drv, 'title', '')}, 'state': st, 'actions': acts if LEVELS[self.level()] >= 2 else [],
                   'terminal': term, 'level': self.level()}
            if len(json.dumps(res, ensure_ascii=False, default=str)) > MAX_JSON:           # one frame must stay below the reader's limit: the long client list goes first
                st['clients'] = (st.get('clients') or [])[:150]
                st.pop('children', None)
            return json.loads(json.dumps(res, ensure_ascii=False, default=str))
        if op == 'action':
            self._need('actions')
            d = self._dev(a.get('key'))
            drv = REGISTRY.get(d.get('driver'))
            act = next((x for x in (getattr(drv, 'actions', None) or []) if x['id'] == a.get('action') and x.get('scope') != 'security'), None)
            if not act:
                raise RuntimeError('такого действия у устройства нет')
            self.app.store.add_event(d['id'], d.get('name'), 'warning', f"по запросу главной установки: «{act.get('label') or act['id']}»")
            res = self.app.run_action(d, act['id'], a.get('params') or {})
            return {k: res[k] for k in ('ok', 'message', 'cable', 'port') if k in res}
        raise RuntimeError('неизвестная команда')

    def _term_open(self, m, send):
        sid = str(m.get('s') or '')[:16]

        def fail(why):
            send({'t': 'termx', 's': sid, 'why': why})
        try:
            self._need('terminal')
            if not terminal.supported():
                return fail('на этой установке терминал недоступен (нужен Linux)')
            if len(terminal.KEYS) >= terminal.MAX_SESSIONS:
                return fail('слишком много открытых терминалов')
            d = self._dev(m.get('dev'))
            target, cfg, why = self.app.hostnet.ssh_target(d)
            if not target:
                return fail(why or 'к этому устройству нельзя открыть терминал')
            from .drivers.sshhost import SSHHost
            args, env, keyfile = SSHHost().interactive_args(cfg)
        except Exception as e:
            return fail(str(e)[:160])
        self.app.store.add_event(None, 'Терминал', 'warning', f"главная установка открыла терминал на «{d.get('name')}» ({cfg['username']}@{cfg['host']})")

        def done(why):
            self.sessions.pop(sid, None)
            send({'t': 'termx', 's': sid, 'why': why})
            if keyfile:
                try:
                    import os
                    os.remove(keyfile)
                except OSError:
                    pass
            self.app.store.add_event(None, 'Терминал', 'info', f"терминал главной установки на «{d.get('name')}» {why}")
        try:
            self.sessions[sid] = terminal.Pty(args, env, max(20, min(int(m.get('cols') or 100), 400)), max(5, min(int(m.get('rows') or 30), 150)),
                                              lambda b: send({'t': 'term', 's': sid, 'd': base64.b64encode(b).decode()}), done)
        except Exception as e:
            fail(str(e)[:160])
