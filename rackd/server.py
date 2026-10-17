"""HTTP API, static files and the background poller."""
import concurrent.futures, gzip, json, mimetypes, os, queue, re, secrets, select, signal, socket, threading, time, traceback, urllib.parse, urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import cameras, hostnet, hostops, terminal, plugins as plugins_mod, vps as vps_mod, agents as agents_mod, collector_install as cinstall, community, updater, sites as sites_mod, collector as collector_mod, sitelink, scenes as scenes_mod, sandbox as sandbox_mod, themes, netscan, advisor, alerts, analysis, assistant, auth, backups, detect, extscan, inet, loops, mfa, newdev, power, routers, security, speedtest, tgbot, topology, uptime
from .drivers import REGISTRY, load_all
from .store import Store
from .util import DriverError

VERSION = '2.10.1'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.environ.get('RL_WEB', os.path.join(ROOT, 'web'))
DATA = os.environ.get('RL_DATA', os.path.join(ROOT, 'data'))
DEMO = os.environ.get('RL_DEMO', '').lower() in ('1', 'true', 'yes')     # demo office, no login, nothing real is touched
SYS_EVENTS = ('Страница', 'Обучение', 'Rack Live')                       # names of the technical events shown in «События → Системные»


def log(*a):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


def lan_url_toward(host):
    """this panel's own address as another machine of the home network sees it (the source address of a route to it) — e.g. http://192.168.1.3:9998"""
    h = re.sub(r'^\w+://|[:/].*$', '', str(host or '')) or '192.168.1.1'
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((h, 9))
        ip = s.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        s.close()
    return f"http://{ip}:{os.environ.get('RL_PORT', '8080')}"


def port_errors(p):
    """Total error counter of a port: received errors (CRC/FCS are part of them) + transmit errors; None if not reported."""
    i, c, o = p.get('inErrors'), p.get('crc'), p.get('outErrors')
    if i is None and c is None:
        return None
    return max(i or 0, c or 0) + (o or 0)


class App:
    def __init__(self):
        load_all()
        self.store = Store(DATA)
        s = self.store.cfg['settings']
        if 'tourDone' not in s:                    # Frank's welcome tour: only for a brand-new installation (no administrator yet); never for one that already works
            s['tourDone'] = bool(self.store.cfg.get('auth')) or DEMO
        self.sessions = auth.Sessions(DATA, policy=lambda: self.mfa.policy())
        self.states = {}
        self.running = set()
        self.last_start = {}
        self.retried = set()
        self.fails = {}                # device id → polls in a row that got no answer (one lost reply is not an outage)
        self._view_cache = {}
        self.alerter = alerts.Alerter(self.store)
        self.speed = speedtest.SpeedTests(self.store)
        self.jobs = {}
        self.inet = inet.InetSpeed(self)
        self.backups = backups.Backups(self.store)
        self.newdev = newdev.NewDevices(self.store)
        self.extscan = extscan.ExtScan(self)
        self.alerter.inet = self.inet
        self.backup_busy = False
        self.tgbot = tgbot.TgBot(self)
        self.mfa = mfa.Mfa(self)
        self.ai = assistant.Assistant(self)
        self.routers = routers.RouterScan(self)
        self.uptime = uptime.Uptime(self.store)
        self.loops = loops.LoopWatch(self.store)
        self.advisor = advisor.Advisor(self, DEMO)
        self.netscan = netscan.NetScan(self, DEMO)
        self.cameras = cameras.Cameras(self, DEMO)
        self.hostnet = hostnet.HostNet(self, DEMO)
        self.host = hostops.Host(self, DEMO)
        self.themes = themes.Themes(DATA, WEB, VERSION)
        self.community = community.Community(DATA)
        self.updater = updater.Updater(self, VERSION, DEMO)
        self.sites = sites_mod.Sites(self)
        self.sandbox = sandbox_mod.Sandbox(ROOT)
        self.collector = collector_mod.Collector(self, VERSION)
        for tid, name, why in self.themes.recheck():         # after an update: a look that no longer fits is switched off at once, the journal says why
            self.store.add_event(None, 'Оформление', 'warning', f'оформление «{name}» отключено — не подходит к этой версии Rack Live: {"; ".join(why)[:300]}')
        self.lock = threading.RLock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self.started = time.time()

    # ───────── polling ─────────
    def poll_device(self, d):
        drv = REGISTRY.get(d.get('driver'))
        t = time.time()
        try:
            # drivers like the UPS look at other devices' live data (PoE watts, disks)
            st = drv.poll(dict(d, _ctx={'states': self.states, 'devices': self.store.cfg['devices'], 'racks': self.store.cfg['racks']}) if getattr(drv, 'wants_ctx', False) else d)
            st['error'] = None
            if st.pop('_retry', False) and d['id'] not in self.retried:
                self.retried.add(d['id'])
                threading.Timer(12, lambda: self.poll_device(d)).start()
        except DriverError as e:
            st = {'status': 'offline', 'error': str(e)}
        except Exception as e:
            st = {'status': 'offline', 'error': f'{type(e).__name__}: {e}'}
            if os.environ.get('RL_DEBUG'):
                traceback.print_exc()
        st['updated'] = time.time()
        st['durationMs'] = round((time.time() - t) * 1000)
        if st.get('status') == 'offline':
            st = self._judge_silence(d, st)
            if st is None:                                 # not yet: keep what was known, the next poll decides
                return self.states.get(d['id']) or {}
        else:
            self.fails.pop(d['id'], None)
        self.apply_state(d, st)
        return st

    def smart_seen(self, d, res):
        """a disk that got worse since the last look → one line in «События» (the verdicts are remembered in data/smart.json)"""
        try:
            memo = self.store._load('smart.json', {})
            mine = memo.setdefault(d['id'], {})
            rank = {'good': 0, 'unknown': 1, 'warn': 2, 'bad': 3}
            for k in res.get('disks') or []:
                key = (k.get('serial') or k['dev'])
                was = mine.get(key)
                if k['verdict'] in ('warn', 'bad') and (was is None or rank[k['verdict']] > rank.get(was, 0)):
                    self.store.add_event(d['id'], d.get('name'), 'warning' if k['verdict'] == 'warn' else 'offline',
                                         f"диск {k['dev']} ({k['model'] or '?'}): " + ('внимание' if k['verdict'] == 'warn' else 'плохое состояние') + ' — ' + (k['reasons'][0] if k['reasons'] else ''))
                mine[key] = k['verdict']
            self.store._dump('smart.json', memo)
        except Exception:
            traceback.print_exc()

    @staticmethod
    def _alive(d):
        """does the device answer on any usual port at all? (a refused connection is an answer too)"""
        host = re.sub(r'^\w+://|[:/].*$', '', str(d.get('host') or ''))
        if not host:
            return False
        for p in (80, 443, 22, 222, 23, 53, 8080, 5000, 8123):
            try:
                with socket.create_connection((host, p), 1.2):
                    return True
            except ConnectionRefusedError:
                return True
            except OSError:
                continue
        return False

    def _judge_silence(self, d, st):
        """A poll got no answer. Three things keep the panel honest:
        1. one lost reply is not an outage — the status flips only after 3 polls in a row (a wrong password is judged at once);
        2. a device that still answers on other ports is NOT «нет связи»: it is on, but does not let Rack Live in (a router may block an address for some minutes after a port scan) → «требует внимания» with the reason;
        3. only a device that is silent everywhere is shown as offline."""
        err = st.get('error') or ''
        n = self.fails[d['id']] = self.fails.get(d['id'], 0) + 1
        transient = not re.search(r'логин|парол|auth|401|403|не Keenetic|не отвечает по http|облак', err, re.I)
        old = self.states.get(d['id']) or {}
        if transient and n < 3 and old.get('status') in ('online', 'warning'):
            return None
        if transient and self._alive(d):
            short = re.sub(r'<urlopen error (.*)>', r'\1', err)[:90]
            st = dict(st, status='warning', stale=True,
                      error='устройство включено и отвечает, но не принимает запросы Rack Live (' + short + '). Обычно это временно: роутер может на несколько минут закрыть доступ с адреса Rack Live после большого сканирования сети.')
        return st

    BUILTIN_SCENES = {'builtin:campus': scenes_mod.campus, 'builtin:starter': scenes_mod.starter}

    def scene_clean(self, sid):
        """a scene by id (built-in or installed) → (title, checked scene, reference for the demo copy)"""
        if sid in self.BUILTIN_SCENES:
            sc = self.BUILTIN_SCENES[sid]()
            errs, _, clean = scenes_mod.validate(sc)
            if errs:
                raise ValueError('; '.join(errs[:2]))
            return sc.get('title'), clean, sid
        m = self.community.get(str(sid or ''))
        if not m or m.get('kind') != 'scene' or not m.get('scene'):
            raise ValueError('такой сцены нет')
        return m['title'], m['scene'], None

    def scenes_list(self):
        out = []
        for sid, fn in self.BUILTIN_SCENES.items():
            sc = fn()
            out.append({'id': sid, 'title': sc['title'], 'description': sc['description'], 'builtin': True, 'stats': scenes_mod.stats(scenes_mod.validate(sc)[2])})
        return out

    def apply_state(self, d, st):
        with self.lock:
            old = self.states.get(d['id']) or {}
            if (st.get('status') == 'offline' or st.get('stale')) and old.get('status') not in (None, 'offline') and old.get('summary'):
                keep = {k: old[k] for k in ('summary', 'ports', 'children', 'storage', 'sections') if k in old}
                st = dict(keep, **st)              # keep the last known data, but show the device as offline
            # per-port throughput from octet counters, error counters → errors in the last hour / day
            dt = (st.get('updated') or 0) - (old.get('updated') or 0)
            fresh = st.get('status') != 'offline' and 0 < dt < 3600
            oldp = {p.get('n'): p for p in old.get('ports') or []}
            for p in (st.get('ports') or []) if st.get('status') != 'offline' else []:
                o = oldp.get(p.get('n')) or {}
                key, point = f"{d['id']}:p{p['n']}", {'t': int(st['updated'])}
                if fresh and all(x.get(k) is not None for x in (p, o) for k in ('rxBytes', 'txBytes')):
                    drx, dtx = p['rxBytes'] - o['rxBytes'], p['txBytes'] - o['txBytes']
                    if drx >= 0 and dtx >= 0:
                        p['rxBps'], p['txBps'] = round(drx * 8 / dt), round(dtx * 8 / dt)
                        point.update(rx=p['rxBps'], tx=p['txBps'])
                if fresh and p.get('bcastPkts') is not None and o.get('bcastPkts') is not None and p['bcastPkts'] >= o['bcastPkts']:
                    p['bcastPps'] = round((p['bcastPkts'] - o['bcastPkts']) / dt)         # broadcast + multicast frames per second: a loop makes it explode
                e, eo = port_errors(p), port_errors(o)
                if fresh and e is not None and eo is not None and e >= eo:     # e < eo: counters reset (reboot)
                    point['err'] = e - eo
                if len(point) > 1:
                    self.store.add_point(key, point, avg=True, sums=('err',))
                if e is not None:
                    h = self.store.history.get(key) or []
                    p['errHour'] = sum(x.get('err', 0) for x in h if x['t'] >= st['updated'] - 3600)
                    p['errDay'] = sum(x.get('err', 0) for x in h)
            try:
                wifi = {(c.get('mac') or '').lower() for s in self.states.values() for c in s.get('clients') or []
                        if c.get('ap') or c.get('rssi') is not None or c.get('wifi')}      # Wi-Fi devices walk between access points: not a loop sign
                self.loops.observe(d, st, wifi)            # signs of a network loop (adds st['loops'], writes the journal)
            except Exception:
                traceback.print_exc()
            self.states[d['id']] = st
            self.store.bump()
            try:
                self.uptime.from_state(d, st, st.get('updated') or time.time())
            except Exception:
                traceback.print_exc()
            prev, cur = old.get('status'), st.get('status')
            if prev is None and cur == 'offline':
                self.store.add_event(d['id'], d.get('name'), 'offline', 'нет связи' + (f": {st.get('error')}" if st.get('error') else ''))
            if prev and prev != cur:
                text = {'offline': 'нет связи' + (f": {st.get('error')}" if st.get('error') else ''), 'online': 'снова в сети',
                        'warning': ('не пускает Rack Live: ' + (st.get('error') or '')[:150]) if st.get('stale') else 'требует внимания'}.get(cur, cur)
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

    def run_action(self, d, action_id, params):
        """A driver action (device card buttons and actions confirmed in Frank's chat) → the API answer."""
        st, did = self.store, d['id']
        drv = REGISTRY.get(d.get('driver'))
        try:
            msg = drv.action(d, action_id, params)
        except Exception as e:
            st.add_event(did, d.get('name'), 'warning', f"действие не выполнено: {e}")
            raise
        act = next((a for a in drv.actions if a['id'] == action_id), {})
        if isinstance(msg, dict):
            # measurements (cable test): keep the result next to the port, nothing to re-poll
            res = msg
            if res.get('cable') is not None:
                st.set_cable(did, res.get('port'), res['cable'])
            if res.get('speedtest'):                # iperf3: kept with the browser tests
                res['speedtest'] = self.speed.add(dict(res['speedtest'], kind='iperf', device=did, deviceName=d.get('name')))
            level = 'info' if res.get('speedtest') else {'ok': 'info', 'empty': 'info'}.get((res.get('cable') or {}).get('verdict'), 'warning')
            st.add_event(did, d.get('name'), level, res.get('message', ''))
            return {'ok': True, 'message': res.get('message'), 'cable': res.get('cable'), 'port': res.get('port'), 'speedtest': res.get('speedtest')}
        if act.get('instant'):
            # quick actions (switches): re-read the device right away and hand the fresh state back
            if act.get('scope') != 'entity':
                st.add_event(did, d.get('name'), 'info', f"{msg}")
            state = self.poll_device(d)
            return {'ok': True, 'message': msg, 'state': json.loads(json.dumps(state))}
        st.add_event(did, d.get('name'), 'info', f"{msg}")
        threading.Thread(target=lambda: (time.sleep(3), self.poll_device(d)), daemon=True).start()
        return {'ok': True, 'message': msg}

    def take_backup(self, d, force=False):
        """Save the device config if it changed; an event + a notification when it did (not for the very first copy)."""
        drv = REGISTRY.get(d.get('driver'))
        v, msg = self.backups.take(d, drv, force)
        if v:
            self.store.add_event(d['id'], d.get('name'), 'info' if v['first'] else 'warning', msg)
            if not v['first'] and self.alerter.cfg()['rules'].get('config', {}).get('on'):
                threading.Thread(target=self.alerter.send, args=([f"⚙️ {d.get('name')}: {msg}"], None, d['id']), daemon=True).start()
        return v, msg

    def background(self):
        """Scheduled jobs riding on the poller: internet speed, outside port check, config backups, new devices."""
        if time.time() - self.started < 90:                  # let every device be polled first
            return
        if self.inet.due():
            self.inet.start()
        if self.extscan.due():
            self.extscan.start()
        if self.routers.due():
            self.routers.run()
        if time.time() - self.started > advisor.FIRST_DELAY and self.advisor.due():     # Frank's review every few days
            self.advisor.start()
        if not self.backup_busy:
            d = next((d for d in self.store.cfg['devices'] if d.get('enabled', True) and hasattr(REGISTRY.get(d.get('driver')), 'backup')
                      and (self.states.get(d['id']) or {}).get('status') == 'online' and self.backups.due(d['id'])), None)
            if d:
                self.backup_busy = True

                def job():
                    try:
                        self.take_backup(d)
                    except Exception as e:
                        log('backup', d.get('name'), e)
                    finally:
                        self.backup_busy = False
                self.pool.submit(job)
        new, anomalies = self.newdev.scan(self.store.cfg['devices'], self.states)
        lines = []
        for r in new:                               # what to do depends on the network's role (newdev.py)
            role = self.newdev.role_of(r); dec = newdev.decide(r, role)
            if dec == 'quiet':
                continue
            text = newdev.describe(r, role)
            self.store.add_event(None, 'Новое устройство', 'warning' if dec == 'ask' else 'info',
                                 text[2:].strip() if dec == 'ask' else f"своё устройство подключилось: {r.get('name') or r['mac']} ({r.get('segment')})")
            if dec == 'ask':
                lines.append(text)
        for a in anomalies:
            self.store.add_event(None, 'Гостевая сеть', 'warning', a[2:].strip())
        lines += anomalies
        if lines and self.alerter.cfg()['rules'].get('newdev', {}).get('on'):
            threading.Thread(target=self.alerter.send, args=(lines[:10] + ([f'…и ещё {len(lines) - 10}'] if len(lines) > 10 else []),), daemon=True).start()

    def poller(self):
        last_save = last_alert = time.time()
        while True:
            if time.time() - last_alert >= 10:
                last_alert = time.time()
                try:
                    self.alerter.evaluate(list(self.store.cfg['devices']), self.states)
                except Exception:
                    traceback.print_exc()
                try:
                    self.background()
                except Exception:
                    traceback.print_exc()
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

    # ───────── background plugin jobs (panel installs take minutes) ─────────
    def start_plugin_job(self, d, drv, pid, op, body):
        job = {'id': secrets.token_hex(6), 'device': d['id'], 'plugin': pid, 'op': op, 't': time.time(), 'stage': 'Подключаюсь к серверу…', 'done': False}
        self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v['t'] < 6 * 3600}
        self.jobs[job['id']] = job

        def run():
            try:
                res = drv.plugin(d, pid, op, dict(body, _progress=lambda s: job.update(stage=s)))
                if res.get('info'):                                     # panel credentials: kept on the device (a secret field)
                    d.setdefault('panelInfo', {})[pid] = res['info']
                if res.get('removed'):
                    (d.get('panelInfo') or {}).pop(pid, None)
                if res.get('removeSite') and self.sites.get(res['removeSite']):         # «Сборщик площадки» removed: its site goes too, if the administrator asked
                    self.sites.remove(res['removeSite'])
                self.store.save()
                self.store.add_event(d['id'], d.get('name'), 'info', res.get('message') or f'{pid}: {op}')
                job['result'] = res
            except Exception as e:
                job['error'] = str(e)
                self.store.add_event(d['id'], d.get('name'), 'warning', f'плагин {pid}: {e}')
            finally:
                job['done'], job['dur'] = True, round(time.time() - job['t'])
        threading.Thread(target=run, daemon=True).start()
        self.store.add_event(d['id'], d.get('name'), 'info', f"плагин {pid}: {'установка' if op == 'install' else 'удаление'} начата")
        return job

    def collector_prepare(self, d, body, op):
        """plugin «Сборщик площадки»: before the SSH job starts — the site (reused on a repeat install), the address the new installation will call,
        its one-time admin password and config. → body for the driver (it only runs the script and never sees anything it did not get here)."""
        pid = 'rcos' if body.get('plugin') == 'rcos' else 'collector'
        info = (d.get('panelInfo') or {}).get(pid) or {}
        if op == 'remove':
            site = self.sites.get(info.get('siteId') or '')
            return dict(body, _site=site['id'] if site and body.get('removeSite') else None)
        # two addresses: where the new installation DOWNLOADS the code (this panel's home address as seen from that machine — found here, nothing to type)
        # and where it REPORTS from wherever it is taken (a domain; empty = it works on its own, reporting can be switched on later on its own panel)
        apps_url = (self.store.cfg.get('apps') or {}).get('url') or ''
        report = cinstall.clean_url(body['server']) if body.get('server') else ('' if 'server' in body else (cinstall.clean_url(apps_url) if apps_url else ''))
        pack = lan_url_toward(d.get('host'))
        try:
            port = int(body.get('port') or cinstall.DEFAULT_PORT)
        except (TypeError, ValueError):
            port = 0
        if not 1024 <= port <= 65535:
            raise ValueError('порт панели на сервере: число от 1024 до 65535')
        name = re.sub(r'\s+', ' ', str(body.get('name') or d.get('name') or 'Новая площадка')).strip()[:40] or 'Новая площадка'
        site = None
        if report:
            site = self.sites.get(info.get('siteId') or '') or next((s for s in self.sites.items if s['name'].lower() == name.lower() and not s.get('last')), None)   # one left by a failed try is reused
            if not site:
                site = self.sites.create(name)
                self.store.add_event(d['id'], d.get('name'), 'info', f"плагин {pid}: создана площадка «{site['name']}»")
            token = site['token']
        else:                                              # no site: a one-hour key that only lets the machine download the code
            token = secrets.token_urlsafe(24)
            self.pack_tokens = {k: v for k, v in (getattr(self, 'pack_tokens', None) or {}).items() if v > time.time()}
            self.pack_tokens[token] = time.time() + 3600
        pw = secrets.token_urlsafe(12)
        level = str(body.get('level') or 'view')
        cfg = cinstall.make_config(site['name'] if site else name, report, token if site else '', pw, level, bool(body.get('insecure')), dev=pid == 'rcos', enabled=bool(site))
        out = dict(body, _collector={'url': report, 'pack': pack, 'token': token, 'cfg': cfg, 'port': port, 'password': pw, 'siteId': site['id'] if site else None,
                                     'siteName': site['name'] if site else None, 'level': level, 'insecure': bool(body.get('insecure'))})
        if pid == 'rcos':                                  # ReckController OS: time zone, our own access point (the password is made here and shown once the install is done)
            ap = body.get('ap') is not False
            out['_rcos'] = {'tz': hostops.check_tz(body['tz']) if body.get('tz') else '', 'ap': ap, 'band': 'a' if body.get('band') == 'a' else 'bg',
                            'ssid': hostops.check_ssid(body.get('ssid') or hostops.DEFAULT_SSID) if ap else '',
                            'password': hostops.check_psk(body.get('apPassword') or ''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(10))) if ap else '',
                            'address': hostops.check_address(body['address']) if body.get('address') else ''}
        return out

    # ───────── «Режим разработчика» (rackd/hostops.py): the system of the machine Rack Live runs on ─────────
    def start_host_job(self, title, fn):
        """one long operation on the machine at a time (apt does not like two); progress is polled with /api/dev/job"""
        with self.lock:
            cur = next((j for j in self.jobs.values() if j.get('device') == '*' and not j['done']), None)
            if cur:
                raise ValueError(f"сейчас уже идёт: «{cur['op']}» — дождитесь окончания")
            job = {'id': secrets.token_hex(6), 'device': '*', 'plugin': 'host', 'op': title, 't': time.time(), 'stage': 'Запуск…', 'done': False}
            self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v['t'] < 6 * 3600}
            self.jobs[job['id']] = job

        def run():
            try:
                job['result'] = fn(lambda s: job.update(stage=s))
                self.store.add_event(None, 'Режим разработчика', 'info', f'{title}: готово')
            except Exception as e:
                job['error'] = str(e)
                self.store.add_event(None, 'Режим разработчика', 'warning', f'{title}: {e}'[:300])
            finally:
                job['done'], job['dur'] = True, round(time.time() - job['t'])
        threading.Thread(target=run, daemon=True).start()
        return job

    def _host_exec(self, script, timeout, progress=None):
        out = self.host.run(script, timeout, on_line=(lambda l: progress(l[:140]) if progress and l and not l.startswith('@@') else None))
        ok, why, lines = hostops._result(out)
        if not ok:
            raise RuntimeError(why or 'команда не подтвердила выполнение')
        return out, lines

    def _wifi_guard(self, iface, force):
        """an adapter that carries the machine's own connection must not be reconfigured by mistake: the panel (and SSH) would vanish with it"""
        w = self.host.wifi()
        if not w.get('ok'):
            raise ValueError(w.get('why') or 'не удалось прочитать Wi-Fi')
        names = [i['name'] for i in w['interfaces']]
        if iface not in names:
            raise ValueError(f'адаптера {iface} нет' + (f'; есть: {", ".join(names)}' if names else ': Wi-Fi-адаптер не найден — сначала «Поставить драйверы»'))
        if w.get('defaultDev') == iface and not force:
            raise ValueError('Через этот адаптер идёт связь машины с сетью: если его перенастроить, пропадёт и эта панель. Подключите кабель (Ethernet) или подтвердите, что понимаете риск.')
        return w

    def dev_op(self, body):
        """one operation of «Режим разработчика». Quick ones answer at once, long ones return {'job': id}. Raises ValueError (a readable reason) or PermissionError."""
        if not self.store.cfg['settings'].get('devMode'):
            raise PermissionError('включите «Режим разработчика» в Настройки → Основные')
        op = str(body.get('op') or '')
        kind, why = self.host.target()
        if kind is None:
            raise ValueError(why)
        demo = kind == 'demo'
        ev = lambda text, lvl='info': self.store.add_event(None, 'Режим разработчика', lvl, text)

        def job(title, fn):
            if demo:
                def sim(progress):
                    for s in ('Проверяю', 'Выполняю', 'Заканчиваю'):
                        progress(s + ' (демо)')
                        time.sleep(.5)
                    return {'ok': True, 'message': title + ' — готово (демо)', 'count': 7, 'packages': ['curl', 'openssl', 'tzdata'], 'reboot': False}
                return {'ok': True, 'job': self.start_host_job(title, sim)['id']}
            return {'ok': True, 'job': self.start_host_job(title, fn)['id']}

        if op == 'timezone':
            tz = hostops.check_tz(body.get('tz'))
            if demo:
                return {'ok': True, 'message': f'Часовой пояс: {tz} (демо)', 'tz': tz}
            _, lines = self._host_exec(hostops.tz_script(tz), 30)
            ev(f'часовой пояс машины: {tz}')
            return {'ok': True, 'message': lines[-1] if lines else f'Часовой пояс: {tz}', 'tz': tz}
        if op == 'ntp':
            if demo:
                return {'ok': True, 'message': 'Автосинхронизация времени включена (демо)'}
            _, lines = self._host_exec(hostops.NTP_SCRIPT, 30)
            return {'ok': True, 'message': lines[-1] if lines else 'Готово'}
        if op == 'check':
            def run(progress):
                out, _ = self._host_exec(hostops.CHECK_SCRIPT, 300, progress)
                m = hostops.parse_marks(out)
                n = int(m.get('count') or 0)
                return {'ok': True, 'count': n, 'packages': m['pkgs'], 'message': f'Можно обновить пакетов: {n}' if n else 'Всё свежее: обновлять нечего'}
            return job('Проверка обновлений', run)
        if op == 'upgrade':
            def run(progress):
                out, lines = self._host_exec(hostops.UPGRADE_SCRIPT, 3600, progress)
                m = hostops.parse_marks(out)
                return {'ok': True, 'reboot': 'reboot' in m, 'left': int(m.get('left') or 0), 'message': 'Система обновлена' + ('; нужна перезагрузка' if 'reboot' in m else '')}
            return job('Обновление системы', run)
        if op == 'docker':
            def run(progress):
                out, _ = self._host_exec(hostops.DOCKER_SCRIPT, 1800, progress)
                m = hostops.parse_marks(out)
                return {'ok': True, 'version': m.get('docker'), 'message': f"Docker: версия {m.get('docker')}"}
            return job('Docker', run)
        if op == 'reboot':
            if str(body.get('confirm') or '').strip().upper() != 'ПЕРЕЗАГРУЗИТЬ':
                raise ValueError('чтобы продолжить, впишите слово ПЕРЕЗАГРУЗИТЬ')
            if demo:
                return {'ok': True, 'message': 'Перезагрузка (демо): ничего не произошло'}
            ev('перезагрузка машины по просьбе администратора', 'warning')
            self._host_exec(hostops.REBOOT_SCRIPT, 20)
            return {'ok': True, 'message': 'Машина перезагружается: панель вернётся через 1–2 минуты'}
        if op == 'drivers':
            def run(progress):
                w, s = self.host.wifi(), self.host.status()
                pk = hostops.firmware_packages(w.get('chips') or [], s.get('id') or 'debian')
                self._host_exec(hostops.drivers_script(pk), 1500, progress)
                w2 = self.host.wifi()
                names = [i['name'] for i in w2.get('interfaces', [])]
                return {'ok': True, 'interfaces': names, 'message': 'NetworkManager и прошивки установлены. ' + (f'Wi-Fi-адаптер: {", ".join(names)}' if names else 'Wi-Fi-адаптер пока не виден — возможно, нужна перезагрузка.')}
            return job('Драйверы Wi-Fi и NetworkManager', run)
        if op == 'scan':
            iface = hostops.check_iface(body.get('iface'))
            if demo:
                return {'ok': True, 'networks': hostops.DEMO_NETS}
            out = self.host.run(hostops.scan_script(iface), 60)
            text = '\n'.join(l[6:] for l in out.splitlines() if l.startswith('@@net '))
            nets = hostops.parse_scan(text)
            if not nets and re.search(r'error|ошибк', text, re.I):
                raise ValueError(text.strip().splitlines()[0][:200])
            return {'ok': True, 'networks': nets}
        if op == 'connect':
            iface, ssid = hostops.check_iface(body.get('iface')), hostops.check_ssid(body.get('ssid'))
            psk = hostops.check_psk(body.get('password'), allow_empty=True)
            if not demo:
                self._wifi_guard(iface, bool(body.get('force')))

            def run(progress):
                out, lines = self._host_exec(hostops.connect_script(iface, ssid, psk, bool(body.get('hidden'))), 150, progress)
                ip = hostops.parse_marks(out).get('ip', '')
                ev(f'машина подключена к Wi-Fi «{ssid}»: {ip}')
                return {'ok': True, 'ip': ip, 'message': f'Подключено к «{ssid}»' + (f', адрес {ip}' if ip else '')}
            return job('Подключение к Wi-Fi', run)
        if op == 'forget':
            if demo:
                return {'ok': True, 'message': 'Сеть забыта (демо)'}
            self._host_exec(hostops.forget_script(body.get('profile')), 30)
            return {'ok': True, 'message': 'Сохранённая сеть удалена'}
        if op == 'ap_on':
            iface, ssid = hostops.check_iface(body.get('iface')), hostops.check_ssid(body.get('ssid') or hostops.DEFAULT_SSID)
            psk = hostops.check_psk(body.get('password') or ''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(10)))
            band = 'a' if body.get('band') == 'a' else 'bg'
            if demo:
                address = hostops.check_address(body.get('address') or hostops.DEFAULT_ADDRESS)
            else:
                w = self._wifi_guard(iface, bool(body.get('force')))
                address = hostops.check_address(body.get('address') or w['suggestAddress'], hostops.nets_of(w['routes'], iface))
                if not w.get('apCapable') and 'iw' in w and w['iw']:
                    raise ValueError('Этот Wi-Fi-адаптер не умеет работать точкой доступа (нет режима AP). Нужен другой адаптер, например USB-ключ с поддержкой AP.')

            def run(progress):
                out, _ = self._host_exec(hostops.ap_on_script(iface, ssid, psk, address, band), 120, progress)
                ip = hostops.parse_marks(out).get('ip', address)
                self.store.cfg.setdefault('dev', {})['ap'] = {'iface': iface, 'ssid': ssid, 'password': psk, 'address': address, 'band': band}
                self.store.save()
                ev(f'включена Wi-Fi-точка «{ssid}» ({address})')
                host = ip.split('/')[0]
                port = os.environ.get('RL_PORT', '8080')
                return {'ok': True, 'ssid': ssid, 'password': psk, 'address': address, 'url': f'http://{host}:{port}', 'message': f'Точка «{ssid}» работает. С телефона: http://{host}:{port}'}
            return job('Wi-Fi-точка', run)
        if op in ('ap_off', 'ap_forget'):
            if demo:
                return {'ok': True, 'message': 'Точка выключена (демо)'}
            _, lines = self._host_exec(hostops.AP_OFF_SCRIPT if op == 'ap_off' else hostops.AP_FORGET_SCRIPT, 40)
            if op == 'ap_forget':
                (self.store.cfg.get('dev') or {}).pop('ap', None)
                self.store.save()
            ev('Wi-Fi-точка выключена' if op == 'ap_off' else 'настройки Wi-Fi-точки удалены')
            return {'ok': True, 'message': lines[-1] if lines else 'Готово'}
        raise ValueError('неизвестная операция')

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
        """Built once per data change (topology + analysis are not free) and shared by every open window."""
        key = (bool(authed), self.store.rev, len(self.states))
        hit = self._view_cache.get(bool(authed))
        if not hit or hit[0] != key:
            hit = (key, self._view(authed))
            self._view_cache[bool(authed)] = hit
        return dict(hit[1], now=time.time())

    def _view(self, authed):
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
                              cfg['settings'].get('showClients', True), REGISTRY, cfg['map'].get('wan'))
        try:
            # analysis always sees the clients, even when the map hides them
            full = topo if cfg['settings'].get('showClients', True) else topology.build(
                cfg['devices'], self.states, units, cfg['map'].get('links'), True, REGISTRY, cfg['map'].get('wan'))
            health = analysis.analyze(full, cfg['devices'], self.states, self.store.cable)
        except Exception:
            traceback.print_exc()
            health = None
        try:                                                # security findings name ports and devices — only for the admin
            sec = security.audit(cfg['devices'], self.states, idx, (cfg.get('security') or {}).get('ignored'), self.extscan.last) if authed else None
        except Exception:
            traceback.print_exc()
            sec = None
        admin_extra = {'sysEvents': [e for e in self.store.events if e.get('name') in SYS_EVENTS][-120:][::-1],        # «События → Системные»: the technical journal (page, tour, starts)
                       'ai': self.ai.public(), 'advice': self.advisor.public(), 'apps': cfg.get('apps') or {}, 'routerScan': self.routers.public(), 'inet': self.inet.public(), 'extscan': self.extscan.public(), 'newDevices': self.newdev.public(), 'networks': self.newdev.networks(cfg['devices'], self.states),
                       'backups': {did: v[-1:] + [{'count': len(v)}] for did, v in self.backups.index.items()}} if authed else {}
        return {**admin_extra, 'notify': alerts.public(cfg.get('notify')) if authed else None, 'security': sec,
                'notifyStatus': self.alerter.status if authed else None,
                'tgBot': {'username': self.tgbot.username, 'error': self.tgbot.error} if authed else None,
                'tgLogin': self.tgbot.login_available(), 'loginCodes': self.mfa.login_methods(),
                'health': health, 'version': VERSION, 'authed': authed, 'setupNeeded': not cfg.get('auth'), 'demo': DEMO, 'devMode': bool(authed and cfg['settings'].get('devMode')),
                'settings': cfg['settings'], 'drivers': [drv.schema() for drv in REGISTRY.values()],
                'devices': devices, 'racks': power.annotate(cfg['racks'], cfg['devices'], self.states), 'map': cfg['map'], 'dashboard': cfg.get('dashboard'), 'plan': cfg.get('plan', {'buildings': [], 'links': []}), 'topology': topo,
                'speedtests': self.speed.public(), 'uptime': self.uptime.public(cfg['devices']),
                'events': self.store.events[-60:][::-1], 'now': time.time()}


APP = None

# where a device's own web interface lives when no explicit address is set
WEB_PORTS = {'synology': ('http', 5000), 'homeassistant': ('http', 8123)}


def web_access(d):
    """{url, username, password} for the «Веб-интерфейс» block of a device card."""
    host = (d.get('webUrl') or '').strip() or (d.get('host') or '').strip()
    url = ''
    if host:
        if '://' in host:
            url = host.rstrip('/')
        elif d.get('driver') in WEB_PORTS and ':' not in host:
            proto, port = WEB_PORTS[d['driver']]
            url = f'{proto}://{host}:{port}'
        elif d.get('driver') not in ('ping', 'agent', 'ups', 'snmp'):
            url = 'http://' + host
    return {'url': url, 'username': d.get('webUser') or d.get('username') or '',
            'password': d.get('webPassword') or (d.get('password') if d.get('driver') in ('remote_web', 'keenetic', 'openwrt', 'tplink_jetstream', 'synology') else '') or ''}


class Handler(BaseHTTPRequestHandler):
    server_version = 'RackLive/' + VERSION

    def log_message(self, fmt, *a):
        if os.environ.get('RL_DEBUG'):
            super().log_message(fmt, *a)

    # ── helpers ──
    def client_ip(self):
        return (self.headers.get('X-Forwarded-For') or self.client_address[0]).split(',')[0].strip()

    def token(self):
        # cookie for the browser; header for the Telegram mini app (Telegram Web runs it in an iframe, where cookies are often blocked)
        if self.headers.get('X-RL-Session'):
            return self.headers['X-RL-Session']
        c = SimpleCookie(self.headers.get('Cookie') or '')
        return c['rl_session'].value if 'rl_session' in c else None

    def authed(self):
        return DEMO or APP.sessions.valid(self.token(), self.client_ip(), self.headers.get('User-Agent') or '')

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 5_000_000:
            raise ValueError('слишком большой запрос')
        raw = self.rfile.read(n) if n else b''
        return json.loads(raw) if raw else {}

    def gz(self, b):
        """gzip text bodies for clients that accept it — the state JSON and app.js shrink ~5x (matters on phones)"""
        if len(b) > 1400 and 'gzip' in (self.headers.get('Accept-Encoding') or ''):
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Vary', 'Accept-Encoding')
            return gzip.compress(b, 5)
        return b

    def send(self, obj, code=200, headers=None):
        b = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        b = self.gz(b)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            for x in (v if isinstance(v, list) else [v]):          # Set-Cookie may come twice (session + device)
                self.send_header(k, x)
        self.end_headers()
        self.wfile.write(b)

    def err(self, msg, code=400):
        self.send({'error': msg}, code)

    def cookie(self, tok, max_age):
        secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
        return f'rl_session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{secure}'

    def dev_token(self):
        c = SimpleCookie(self.headers.get('Cookie') or '')
        return c['rl_dev'].value if 'rl_dev' in c else None

    def dev_cookie(self, tok):
        secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
        return f'rl_dev={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={365 * 86400}{secure}'

    def signed_in(self, via, remember=True, extra=None):
        """a person is in: a device record, a session, both cookies; a new device is told to the owner in Telegram"""
        ip, ua = self.client_ip(), self.headers.get('User-Agent') or ''
        tok, dtok, new, did = APP.sessions.create(ip, ua, remember, self.dev_token(), via)
        if new and via in ('password', 'mfa'):
            name = auth.device_name(ua)
            APP.store.add_event(None, 'Вход', 'info', f'новое устройство: {name} ({ip})')
            threading.Thread(target=APP.tgbot.notice, args=(f'👤 Новое устройство вошло в Rack Live: {name}, адрес {ip}.\nНе вы? Настройки → Доступ → отключите устройство и смените пароль.',), daemon=True).start()
        max_age = int(APP.sessions.p('sessionDays', auth.SESSION_DAYS) * 86400) if remember else auth.ABS_HOURS * 3600
        out = dict({'ok': True}, **(extra or {}))
        if extra and 'token' in extra:
            out['token'] = tok
        return self.send(out, headers={'Set-Cookie': [self.cookie(tok, max_age), self.dev_cookie(dtok)]})

    def can_view(self):
        cfg = APP.store.cfg
        return self.authed() or bool(cfg.get('auth') and cfg['settings'].get('publicView'))

    def query(self):
        return dict(x.split('=', 1) for x in self.path.split('?', 1)[1].split('&') if '=' in x) if '?' in self.path else {}

    # ── speed test streams (no gzip, no JSON) ──
    def speed_down(self):
        n = self.query().get('bytes', '')
        n = max(1, min(speedtest.MAX_BYTES, int(n) if n.isdigit() else 25 << 20))
        if not APP.speed.slots.acquire(blocking=False):
            return self.err('сейчас идёт другой тест скорости — попробуйте через минуту', 429)
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(n))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            chunk, left = memoryview(speedtest.CHUNK), n
            while left > 0:
                k = min(left, len(chunk))
                self.wfile.write(chunk[:k])
                left -= k
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass                                            # the page stops a stream when its time is up
        finally:
            APP.speed.slots.release()

    def speed_up(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > speedtest.MAX_BYTES:
            return self.err('слишком большой блок', 413)
        if not APP.speed.slots.acquire(blocking=False):
            return self.err('сейчас идёт другой тест скорости — попробуйте через минуту', 429)
        t, left = time.time(), n
        try:
            while left > 0:
                b = self.rfile.read(min(left, 1 << 20))
                if not b:
                    break
                left -= len(b)
        finally:
            APP.speed.slots.release()
        return self.send({'bytes': n - left, 'ms': round((time.time() - t) * 1000)})

    # ── «apps on the phone»: an https address for installing Frank / speed test, made on the Keenetic if there is one ──
    def own_address(self, router_host):
        """Where the router should send the domain's traffic: the address the admin opened Rack Live by (it reaches us),
        else the local IP this host uses towards the router + our port."""
        host = (self.headers.get('Host') or '').strip()
        h, _, p = host.rpartition(':') if host.count(':') == 1 else (host, '', '')
        # through the router's own proxy the Host is rewritten to our bare IP without the port: then it is our listening port
        via_router = self.client_ip() == re.sub(r'^\w+://|[:/].*$', '', router_host or '')
        try:
            import ipaddress
            if ipaddress.ip_address(h).is_private:
                return h, int(p or (os.environ.get('RL_PORT', '8080') if via_router else 80))
        except ValueError:
            pass
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((re.sub(r'^\w+://|[:/].*$', '', router_host) or '192.168.1.1', 80))
            return s.getsockname()[0], int(os.environ.get('RL_PORT', '8080'))
        finally:
            s.close()

    def apps(self, body):
        st = APP.store
        cur = st.cfg.setdefault('apps', {})
        op = body.get('op') or 'status'
        routers = [d for d in st.cfg['devices'] if d.get('driver') == 'keenetic' and d.get('enabled', True)]
        d = next((x for x in routers if x['id'] == body.get('device')), None) or next(
            (x for x in routers if (APP.states.get(x['id']) or {}).get('status') != 'offline'), None) or (routers[0] if routers else None)
        if op == 'set':                                      # an address made by hand (any reverse proxy with https)
            url = str(body.get('url') or '').strip().rstrip('/')
            if url and not url.startswith('https://'):
                return self.err('нужен адрес, начинающийся с https:// — иначе телефон не даст микрофон и установку на Android')
            st.cfg['apps'] = {'url': url} if url else {}
            st.save()
            return self.send({'ok': True, 'apps': st.cfg['apps']})
        if not d:
            return self.send({'ok': True, 'apps': cur, 'router': None})
        drv = REGISTRY['keenetic']
        ip, port = self.own_address(d.get('host') or '')
        try:
            if op == 'status':
                r = drv.keendns(d, 'status', {'ip': ip, 'port': port})
            elif op == 'create':
                # never point the router at a wrong place: the target must answer as this very Rack Live
                try:
                    probe = json.loads(urllib.request.urlopen(f'http://{ip}:{port}/api/state', timeout=4).read())
                    if probe.get('version') != VERSION:
                        raise ValueError('не Rack Live')
                except Exception:
                    return self.send({'ok': False, 'error': f'не удалось проверить, что Rack Live отвечает на {ip}:{port} — откройте настройки по домашнему адресу '
                                      f'(http://IP:порт) и повторите', 'apps': cur, 'router': {'id': d['id'], 'name': d.get('name')}})
                r = drv.keendns(d, 'create', {'ip': ip, 'port': port, 'public': bool(body.get('public')), 'name': body.get('name') or 'racklive'})
                st.cfg['apps'] = {'url': r['url'], 'device': d['id'], 'proxy': r['proxy'], 'public': r['public'],
                                  'created': bool(r.get('created') or cur.get('created') and cur.get('proxy') == r['proxy'])}
                st.save()
                st.add_event(d['id'], d.get('name'), 'info', f"доменное имя Rack Live: {r['url']} ({'из интернета' if r['public'] else 'только из домашней сети'})")
            elif op == 'remove':
                if cur.get('created') and cur.get('proxy') and cur.get('device') == d['id']:
                    r = drv.keendns(d, 'remove', {'name': cur['proxy']})
                    st.add_event(d['id'], d.get('name'), 'info', f"доменное имя Rack Live удалено: {cur.get('url')}")
                else:
                    r = {}
                st.cfg['apps'] = {}
                st.save()
            else:
                return self.err('неизвестная операция')
        except DriverError as e:
            return self.send({'ok': False, 'error': str(e), 'apps': st.cfg.get('apps') or {}, 'router': {'id': d['id'], 'name': d.get('name')}})
        return self.send({'ok': True, 'apps': st.cfg.get('apps') or {}, 'router': dict(r, id=d['id'], name=d.get('name'), target=f'{ip}:{port}')})

    def terminal(self):
        """WebSocket → a shell on the machine Rack Live runs on (rackd/terminal.py). Admin only, same-site only."""
        q = self.query()
        if q.get('tok') and not self.headers.get('X-RL-Session'):          # the Telegram mini app keeps the session in a header-less iframe
            self.headers['X-RL-Session'] = q['tok']
        if not self.need_admin():
            return
        origin = self.headers.get('Origin')
        if origin and urllib.parse.urlparse(origin).netloc != (self.headers.get('Host') or ''):
            return self.err('запрос с чужого сайта', 403)
        if 'websocket' not in (self.headers.get('Upgrade') or '').lower() or not self.headers.get('Sec-WebSocket-Key'):
            return self.err('это адрес для WebSocket', 400)
        if q.get('site'):                                  # a terminal on a device of a remote site: through that site's collector
            return self.site_terminal(q)
        if DEMO or not terminal.supported():
            return self.err('терминал здесь недоступен', 400)
        if q.get('device'):                               # a server added as a device (plugin «ИИ-агенты»: sign-in, look at a chat)
            dev = next((x for x in APP.store.cfg['devices'] if x['id'] == q['device']), None)
            d, cfg, why = APP.hostnet.ssh_target(dev) if dev else (None, None, 'устройство не найдено')
        else:
            d, cfg, why = APP.hostnet.terminal_target()
        if not d:
            return self.err(why, 400)
        if len(terminal.KEYS) >= terminal.MAX_SESSIONS:
            return self.err('открыто слишком много терминалов (не больше %d)' % terminal.MAX_SESSIONS, 429)
        remote, run = None, q.get('run')
        if run == 'agent-setup':
            remote = 'bash -lc \'$HOME/.racklive-agents/racklive-agent setup; echo; echo "Можно закрыть окно."; exec bash -l\''
        elif run == 'agent-attach' and re.match(r'^rl-[\w.\-]{1,40}$', q.get('session') or ''):
            remote = f"bash -lc 'tmux attach -t {q['session']} || $HOME/.racklive-agents/racklive-agent list; exec bash -l'"
        elif run:
            return self.err('неизвестная команда терминала', 400)
        from .drivers.sshhost import SSHHost
        try:
            args, env, keyfile = SSHHost().interactive_args(cfg, remote)
        except DriverError as e:
            return self.err(str(e), 400)
        cols, rows = int(q.get('cols') or 100), int(q.get('rows') or 30)
        self.send_response(101)
        self.send_header('Upgrade', 'websocket')
        self.send_header('Connection', 'Upgrade')
        self.send_header('Sec-WebSocket-Accept', terminal.accept_key(self.headers['Sec-WebSocket-Key']))
        self.end_headers()
        self.close_connection = True
        ip = self.client_ip()
        APP.store.add_event(None, 'Терминал', 'warning', f"открыт терминал на «{d.get('name')}» ({cfg['username']}@{cfg['host']}) с адреса {ip}")
        why, secs = 'закрыт', 0
        try:
            why, secs = terminal.run(self.connection, args, env, max(20, min(cols, 400)), max(5, min(rows, 150)), None)
        except Exception as e:
            why = f'ошибка: {type(e).__name__}'
        finally:
            if keyfile:
                try:
                    os.remove(keyfile)
                except OSError:
                    pass
        APP.store.add_event(None, 'Терминал', 'info', f"терминал на «{d.get('name')}» {why} (длился {secs // 60} мин {secs % 60} с)")

    def _upgrade(self):
        self.send_response(101)
        self.send_header('Upgrade', 'websocket')
        self.send_header('Connection', 'Upgrade')
        self.send_header('Sec-WebSocket-Accept', terminal.accept_key(self.headers['Sec-WebSocket-Key']))
        self.end_headers()
        self.close_connection = True

    def site_link(self):
        """WebSocket from a site collector: it stays open, the centre sends requests through it (rackd/sitelink.py)"""
        tok = (self.headers.get('Authorization') or '').replace('Bearer ', '').strip()
        site = next((s for s in APP.sites.items if tok and secrets.compare_digest(s['token'], tok)), None)
        if not site:
            return self.err('неверный ключ площадки', 401)
        if 'websocket' not in (self.headers.get('Upgrade') or '').lower() or not self.headers.get('Sec-WebSocket-Key'):
            return self.err('это адрес для WebSocket', 400)
        self._upgrade()
        link = sitelink.Link(self.connection, site)
        old = APP.sites.links.get(site['id'])
        if old:
            old.dead = True
        APP.sites.links[site['id']] = link
        APP.store.add_event(None, 'Площадки', 'info', f"канал управления с площадкой «{site['name']}» открыт")
        try:
            link.run()
        finally:
            link.dead = True
            if APP.sites.links.get(site['id']) is link:
                APP.sites.links.pop(site['id'], None)
                APP.store.add_event(None, 'Площадки', 'info', f"канал управления с площадкой «{site['name']}» закрыт")

    def site_terminal(self, q):
        """browser ⇄ this server ⇄ the site's collector ⇄ ssh on a device there (the administrator is already checked by terminal())"""
        link = APP.sites.link(q.get('site'))
        if not link:
            return self.err('канал с площадкой не подключён', 400)
        if link.caps.get('level') != 'terminal':
            return self.err('владелец площадки не разрешил терминал', 403)
        key = re.sub(r'[^A-Za-z0-9_.\-]', '', q.get('device') or '')
        cols, rows = int(q.get('cols') or 100), int(q.get('rows') or 30)
        sid, qs = link.open_stream(key, max(20, min(cols, 400)), max(5, min(rows, 150)))
        self._upgrade()
        conn, rd = self.connection, terminal.Reader()
        APP.store.add_event(None, 'Терминал', 'warning', f"открыт терминал на устройстве площадки «{link.site['name']}» с адреса {self.client_ip()}")
        last = started = time.time()
        why = 'закрыт'
        try:
            while True:
                try:
                    while True:
                        m = qs.get_nowait()
                        if m.get('t') == 'termx':
                            conn.sendall(terminal.frame(('\r\n\x1b[33m[' + (m.get('why') or 'сеанс завершён') + ']\x1b[0m\r\n').encode(), 2))
                            why = m.get('why') or 'завершён'
                            return
                        conn.sendall(terminal.frame(__import__('base64').b64decode(m.get('d') or ''), 2))
                except queue.Empty:
                    pass
                if link.dead:
                    why = 'канал закрыт'
                    return
                if time.time() - last > terminal.IDLE or time.time() - started > terminal.MAX:
                    conn.sendall(terminal.frame('\r\n\x1b[33m[Сеанс закрыт по времени]\x1b[0m\r\n'.encode(), 2))
                    why = 'закрыт по времени'
                    return
                r, _, _ = select.select([conn], [], [], 0.2)
                if not r:
                    continue
                data = conn.recv(65536)
                if not data:
                    return
                for op, payload in rd.feed(data):
                    if op == 8:
                        return
                    if op == 9:
                        conn.sendall(terminal.frame(payload, 10))
                    elif op in (1, 2):
                        if op == 1 and payload[:1] == b'{':
                            try:
                                msg = json.loads(payload)
                                if 'resize' in msg:
                                    link.send({'t': 'term_resize', 's': sid, 'cols': int(msg['resize'][0]), 'rows': int(msg['resize'][1])})
                                continue
                            except (ValueError, KeyError, TypeError):
                                pass
                        last = time.time()
                        link.send({'t': 'term', 's': sid, 'd': __import__('base64').b64encode(payload).decode()})
        except (OSError, ValueError):
            pass
        finally:
            link.close_stream(sid)
            APP.store.add_event(None, 'Терминал', 'info', f"терминал на устройстве площадки «{link.site['name']}» {why}")

    def need_admin(self):
        if not self.authed():
            self.err('нужен вход администратора', 401)
            return False
        return True

    # ── static ──
    def static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        if path.rstrip('/') in ('/frank', '/speed', '/terminal'):          # separate installable apps (own manifest and icon): Frank, speed test, terminal
            path = path.rstrip('/') + '.html'
        full = os.path.normpath(os.path.join(WEB, path.lstrip('/')))
        if not full.startswith(os.path.normpath(WEB)) or not os.path.isfile(full):
            full = os.path.join(WEB, 'index.html')          # SPA fallback
        ctype = mimetypes.guess_type(full)[0] or 'application/octet-stream'
        if full.endswith('.js'):
            ctype = 'application/javascript'
        with open(full, 'rb') as f:
            b = f.read()
        self.send_response(200)
        texty = ctype.startswith(('text', 'application/javascript', 'application/json', 'image/svg'))
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith(('text', 'application/javascript', 'application/json')) else ''))
        if texty:
            b = self.gz(b)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-cache' if full.endswith(('.html', '.js', '.css')) else 'max-age=86400')
        self.send_header('X-Content-Type-Options', 'nosniff')
        # framing: only ourselves and Telegram Web (mini app); X-Frame-Options can't express that, CSP can
        self.send_header('Content-Security-Policy', "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org")
        self.end_headers()
        self.wfile.write(b)

    def theme_file(self, path):
        """/themes/all.css · /themes/<id>/theme.css · /themes/<id>/data.json · /themes/<id>/<file> · /manifest.json?skin=<id>"""
        T = APP.themes
        hdr = {'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"}
        if path in ('/manifest.json', '/frank-manifest.json', '/speed-manifest.json'):      # an installable app's manifest with this look's icons (each of the three apps has its own)
            tid = self.query().get('skin') or ''
            with open(os.path.join(WEB, path.lstrip('/')), encoding='utf-8') as f:
                man = json.load(f)
            d = T.data(tid) or {}
            pw = d.get({'/manifest.json': 'pwa', '/frank-manifest.json': 'pwaFrank', '/speed-manifest.json': 'pwaSpeed'}[path]) or {}
            if pw.get('icon192') and pw.get('icon512'):
                man['icons'] = [{'src': pw['icon192'], 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'}, {'src': pw['icon512'], 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'}]
            return self.send_raw(json.dumps(man, ensure_ascii=False).encode(), 'application/manifest+json; charset=utf-8', {'Cache-Control': 'no-cache'})
        if path == '/themes/all.css':
            return self.send_raw(T.all_css().encode(), 'text/css; charset=utf-8', hdr)
        m = re.match(r'^/themes/([a-z][a-z0-9-]{2,31})/(.+)$', path)
        if not m:
            return self.err('не найдено', 404)
        tid, rel = m.group(1), urllib.parse.unquote(m.group(2))
        if rel == 'theme.css':
            return self.send_raw(T.css(tid).encode(), 'text/css; charset=utf-8', hdr)
        if rel == 'data.json':
            d = T.data(tid)
            return self.send_raw(json.dumps(d or {'off': True}, ensure_ascii=False).encode(), 'application/json; charset=utf-8', hdr)
        a = T.asset(tid, rel)
        if not a:
            return self.err('не найдено', 404)
        return self.send_raw(a[0], a[1], hdr)

    def send_raw(self, b, ctype, headers=None):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        if ctype.startswith(('text', 'application/json', 'application/manifest', 'image/svg')):
            b = self.gz(b)
        self.send_header('Content-Length', str(len(b)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    # ── routes ──
    def do_GET(self):
        path = self.path.split('?')[0]
        try:
            if path == '/api/term/ws':
                return self.terminal()
            if path == '/api/site/link':                   # the control channel of a site collector (key auth; the collector dials out)
                return self.site_link()
            if path == '/api/site/pack':                   # a collector being installed over SSH (plugin «Сборщик площадки») downloads this installation's own code; the site key is the pass
                tok = (self.headers.get('Authorization') or '').replace('Bearer ', '').strip()
                one_time = (getattr(APP, 'pack_tokens', None) or {}).get(tok, 0) > time.time()          # «ReckController OS» without reporting: a one-hour download key
                if not tok or not (one_time or any(secrets.compare_digest(s['token'], tok) for s in APP.sites.items)):
                    return self.err('неверный ключ площадки', 401)
                b = cinstall.pack()
                self.send_response(200)
                self.send_header('Content-Type', 'application/gzip')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if path == '/api/term/info':                   # Settings → «Терминал»: which machine, and whether it can be opened
                if not self.need_admin():
                    return
                d, cfg, why = APP.hostnet.terminal_target() if terminal.supported() else (None, None, 'Терминал работает только на Linux / Synology / OpenWrt / Entware (не на Windows).')
                if d is None and DEMO:
                    why = 'В демо-режиме терминал отключён: он открывает настоящую командную строку.'
                devs = []                                   # every device we can sign in to over SSH (the «Терминал» app lets you pick any of them)
                if terminal.supported() and not DEMO:
                    for x in APP.store.cfg['devices']:
                        xd, xc, _ = APP.hostnet.ssh_target(x)
                        if xd:
                            devs.append({'id': x['id'], 'name': x.get('name'), 'driver': x.get('driver'), 'user': xc.get('username'), 'host': xc.get('host'), 'port': xc.get('sshPort') or 22})
                return self.send({'ok': bool(d) and not DEMO, 'why': why if (not d or DEMO) else '', 'device': {'id': d['id'], 'name': d.get('name'), 'driver': d.get('driver'), 'user': cfg.get('username'), 'host': cfg.get('host'), 'port': cfg.get('sshPort') or 22} if d else None,
                                  'devices': devs, 'supported': terminal.supported() and not DEMO, 'sessions': len(terminal.KEYS)})
            if path == '/api/state':
                a = self.authed()
                cfg = APP.store.cfg
                if not a and (not cfg.get('auth') or not cfg['settings'].get('publicView')):
                    return self.send({'authed': False, 'setupNeeded': not cfg.get('auth'), 'needLogin': bool(cfg.get('auth')),
                                      'settings': {'title': cfg['settings'].get('title')}, 'version': VERSION,
                                      'tgLogin': APP.tgbot.login_available(), 'loginCodes': APP.mfa.login_methods()})
                return self.send(APP.view(a))
            if path.startswith('/api/speedtest/'):
                if not self.can_view():
                    return self.err('нужен вход', 401)
                if path == '/api/speedtest/down':
                    return self.speed_down()
                if path == '/api/speedtest/ping':
                    return self.send({'t': time.time()})
                if path == '/api/speedtest/who':
                    ip = self.client_ip()
                    return self.send(speedtest.who(APP.store.cfg['devices'], APP.states, ip))
            m = re.match(r'/api/history/(\w+)$', path)
            if m:
                if not self.authed() and not APP.store.cfg['settings'].get('publicView'):
                    return self.err('нужен вход', 401)
                q = self.query()
                key = m.group(1) + (f":p{int(q['port'])}" if q.get('port', '').isdigit() else '')
                return self.send(APP.store.history.get(key, []))
            if path.startswith('/themes/') or (path in ('/manifest.json', '/frank-manifest.json', '/speed-manifest.json') and self.query().get('skin')):      # custom looks: files are public (the sign-in screen needs them), nothing secret inside
                return self.theme_file(path)
            if path == '/api/themes':                       # the list with the verdict «fits / does not fit» (admin only)
                if not self.need_admin():
                    return
                return self.send({'themes': APP.themes.list(), 'api': themes.THEME_API, 'version': VERSION})
            if path in ('/api/themes/template.zip', '/api/themes/guide.txt'):      # for authors: a starter look and the instruction (a text to hand to a neural network)
                if not self.need_admin():
                    return
                zip_ = path.endswith('.zip')
                b = APP.themes.template_zip() if zip_ else APP.themes.guide_text().encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip' if zip_ else 'text/plain; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="' + ('racklive-look-template.zip' if zip_ else 'racklive-look-guide.txt') + '"')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if path == '/api/network':                      # Settings → «Сеть»: the network of the machine Rack Live runs on
                if not self.need_admin():
                    return
                return self.send(APP.hostnet.view())
            if path in ('/api/dev/status', '/api/dev/wifi', '/api/dev/zones'):        # «Режим разработчика»: the system of the machine (admin only, and only when the mode is on)
                if not self.need_admin():
                    return
                if not APP.store.cfg['settings'].get('devMode'):
                    return self.err('включите «Режим разработчика» в Настройки → Основные', 403)
                try:
                    if path == '/api/dev/zones':
                        return self.send({'ok': True, 'zones': APP.host.zones()})
                    res = APP.host.status() if path == '/api/dev/status' else APP.host.wifi()
                    if path == '/api/dev/wifi' and res.get('ok'):
                        res['apConfig'] = (APP.store.cfg.get('dev') or {}).get('ap')    # the password of OUR access point: the administrator types it on the phone
                        res['port'] = os.environ.get('RL_PORT', '8080')
                    return self.send(res)
                except Exception as e:
                    return self.err(str(e), 502)
            if path == '/api/cameras/recorders':           # Synology Surveillance Station and the like: recorders that live on added devices
                if not self.need_admin():
                    return
                return self.send({'recorders': APP.cameras.recorders()})
            if path == '/api/cameras':                      # tool «Камеры»: progress and what was found
                if not self.need_admin():
                    return
                return self.send(APP.cameras.public())
            m = re.match(r'^/api/cameras/bulk/(j[0-9a-f]{8})$', path)
            if m:
                if not self.need_admin():
                    return
                return self.send(APP.cameras.jobs.get(m.group(1)) or {'finished': True, 'results': [], 'total': 0, 'done': 0})
            if path == '/api/plugins/catalog':              # tab «Инструменты → Плагины»: every plugin Rack Live knows, by device type
                if not self.need_admin():
                    return
                comm = [{'id': 'x-' + m['id'], 'drivers': [community.TARGETS[t][0] for t in m['targets']], 'title': m['title'], 'icon': m.get('icon') or 'box', 'kind': 'community',
                         'description': m['description'], 'author': m.get('author'), 'home': m.get('home')} for m in APP.community.list() if (m.get('kind') or 'plugin') == 'plugin']
                return self.send({'plugins': [{k: p.get(k) for k in ('id', 'drivers', 'title', 'icon', 'kind', 'description', 'author', 'home')} for p in plugins_mod.CATALOG + vps_mod.CATALOG + agents_mod.CATALOG + [cinstall.RCOS_CARD, cinstall.CARD]] + comm})
            if path == '/api/sites':                        # Инструменты → Удалённые площадки: the sites that report here, agents, and this installation's own collector mode
                if not self.need_admin():
                    return
                ag = [{'id': d['id'], 'name': d.get('name'), 'status': (APP.states.get(d['id']) or {}).get('status'), 'updated': (APP.states.get(d['id']) or {}).get('updated'),
                       'ip': ((APP.states.get(d['id']) or {}).get('summary') or {}).get('ip')} for d in APP.store.cfg['devices'] if d.get('driver') == 'agent']
                return self.send({'sites': APP.sites.public(), 'agents': ag, 'collector': APP.collector.public(), 'demo': DEMO})
            if path == '/api/scenes':                       # Инструменты → Демо-сцены и планы: built-in and installed scenes, the running demo copy, copies for undo (admin only)
                if not self.need_admin():
                    return
                return self.send({'builtin': APP.scenes_list(), 'mine': [APP.community.public(m) for m in APP.community.scenes()], 'sandbox': APP.sandbox.status(),
                                  'backups': scenes_mod.backups(APP.store), 'demo': DEMO})
            if path == '/api/update':                       # Settings → «О программе»: current / newest version, how it can be updated (admin only)
                if not self.need_admin():
                    return
                return self.send(APP.updater.info())
            if path == '/api/community':                    # installed community plugins (admin only)
                if not self.need_admin():
                    return
                return self.send({'plugins': [APP.community.public(m) for m in APP.community.list()], 'api': community.PLUGIN_API})
            if path == '/api/community/index':              # the community catalog (a separate GitHub repository)
                if not self.need_admin():
                    return
                return self.send(dict(APP.community.index(force=self.query().get('refresh') == '1'), installed={m['id']: m['version'] for m in APP.community.list()}))
            if path in ('/api/community/template.zip', '/api/community/guide.txt'):
                if not self.need_admin():
                    return
                zip_ = path.endswith('.zip')
                tool = self.query().get('kind') == 'tool'
                scene = self.query().get('kind') == 'scene'
                b = community.template_zip('scene' if scene else 'tool' if tool else 'plugin') if zip_ else (scenes_mod.guide_text() if self.query().get('kind') == 'scene' else community.guide_text()).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip' if zip_ else 'text/plain; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="' + (('racklive-scene-template.zip' if scene else 'racklive-tool-template.zip' if tool else 'racklive-plugin-template.zip') if zip_ else ('racklive-scene-guide.txt' if scene else 'racklive-plugin-guide.txt')) + '"')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            m = re.match(r'^/api/community/([a-z][a-z0-9-]{2,30})$', path)
            if m and self.command == 'GET':                  # the exact commands, for the «what will run» preview
                if not self.need_admin():
                    return
                det = APP.community.detail(m.group(1))
                return self.send(det) if det else self.err('плагин не найден', 404)
            if path == '/api/netscan':                      # «Сканировать сеть»: progress and what was found (admin only)
                if not self.need_admin():
                    return
                return self.send(APP.netscan.public())
            m = re.match(r'/api/backups/(\w+)(?:/(\d+))?$', path)
            if m:                                           # versions list · diff · raw file (admin only: configs hold secrets)
                if not self.need_admin():
                    return
                did, t, q = m.group(1), m.group(2), self.query()
                if not t:
                    return self.send({'versions': (APP.backups.index.get(did) or [])[::-1]})
                if q.get('raw'):
                    d = APP.store.device(did) or {}
                    b = APP.backups.read(did, t).encode()
                    name = re.sub(r'[^\w.-]', '_', f"{d.get('name') or did}-{time.strftime('%Y%m%d-%H%M', time.localtime(int(t)))}.txt")
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Disposition', f"attachment; filename=\"config.txt\"; filename*=UTF-8''{urllib.parse.quote(name)}")
                    self.send_header('Content-Length', str(len(b)))
                    self.end_headers()
                    return self.wfile.write(b)
                return self.send({'diff': APP.backups.diff(did, t, q.get('prev'))})
            m = re.match(r'/api/ai/chats(?:/(\w+))?$', path)
            if m:                                           # saved conversations with Frank (admin only: they quote the network)
                if not self.need_admin():
                    return
                if not m.group(1):
                    return self.send({'chats': APP.ai.chat_list()})
                c = APP.ai.chat_view(m.group(1))
                return self.send(c) if c else self.err('разговор не найден', 404)
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
            if path == '/api/speedtest/up' and method == 'POST':     # raw bytes, read before any JSON parsing
                if not self.can_view():
                    return self.err('нужен вход', 401)
                return self.speed_up()
            if path == '/api/themes/upload' and method == 'POST':    # a .zip with a custom look: raw bytes (admin), checked and installed only if it fits
                if not self.need_admin():
                    return
                n = int(self.headers.get('Content-Length') or 0)
                if n <= 0 or n > themes.MAX_ZIP:
                    return self.err(f'архив должен быть не больше {themes.MAX_ZIP // 1024 // 1024} МБ', 413)
                rep = APP.themes.install(self.rfile.read(n))
                if rep['ok']:
                    st.add_event(None, 'Оформление', 'info', f"добавлено оформление «{rep.get('name')}»" + (f" ({len(rep['warnings'])} замечаний)" if rep['warnings'] else ''))
                return self.send(rep)
            if path == '/api/community/upload' and method == 'POST':     # a plugin .zip (raw bytes): checked; accepted only if nothing in it is forbidden or undeclared
                if not self.need_admin():
                    return
                n = int(self.headers.get('Content-Length') or 0)
                if n <= 0 or n > community.MAX_ZIP:
                    return self.err(f'архив должен быть не больше {community.MAX_ZIP // 1024} КБ', 413)
                rep = APP.community.install_zip(self.rfile.read(n), 'own')
                if rep['ok']:
                    p = rep['plugin']
                    st.add_event(None, 'Плагины', 'warning', f"загружен свой плагин «{p['title']}» {p['version']} (риск: {p['risk']})")
                return self.send(rep)
            m = re.match(r'^/api/community/([a-z][a-z0-9-]{2,30})$', path)
            if m and method == 'DELETE':
                if not self.need_admin():
                    return
                APP.community.remove(m.group(1))
                st.add_event(None, 'Плагины', 'info', f'плагин сообщества «{m.group(1)}» удалён из Rack Live')
                return self.send({'ok': True})
            m = re.match(r'^/api/themes/([a-z][a-z0-9-]{2,31})$', path)
            if m and method == 'DELETE':
                if not self.need_admin():
                    return
                APP.themes.remove(m.group(1))
                st.add_event(None, 'Оформление', 'info', f'оформление «{m.group(1)}» удалено')
                return self.send({'ok': True})
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
                return self.signed_in('setup')
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
                remember = body.get('remember') is not False
                if APP.mfa.enabled() and not APP.sessions.trusted_device(self.dev_token()):
                    # the password is right, but this device is not remembered: one more proof is needed before a session exists
                    ticket = APP.mfa.begin(ip, self.headers.get('User-Agent') or '')
                    st.add_event(None, 'Вход', 'info', f'пароль принят с адреса {ip}, ждём второй фактор')
                    return self.send({'ok': False, 'mfa': True, 'ticket': ticket, 'methods': APP.mfa.methods()})
                st.add_event(None, 'Вход', 'info', f'администратор вошёл с адреса {ip}')
                return self.signed_in('password', remember)
            if path == '/api/login/code/start' and method == 'POST':
                # a sign-in without the password: a code goes to the connected mailbox / phone
                ip = self.client_ip()
                if APP.sessions.throttled(ip):
                    return self.err('слишком много попыток, подождите 5 минут', 429)
                try:
                    ticket, hint = APP.mfa.start_primary(ip, self.headers.get('User-Agent') or '', body.get('method'))
                except ValueError as e:
                    return self.err(str(e), 400)
                st.add_event(None, 'Вход', 'info', f"начат вход без пароля: {({'totp': 'код из приложения', 'email': 'код на почту', 'sms': 'код по SMS'}).get(body.get('method'), '?')} (адрес {ip})")
                return self.send({'ok': True, 'ticket': ticket, 'hint': hint})
            if path == '/api/login/mfa/send' and method == 'POST':
                ip = self.client_ip()
                if APP.sessions.throttled(ip):
                    return self.err('слишком много попыток, подождите 5 минут', 429)
                try:
                    return self.send({'ok': True, 'hint': APP.mfa.send(body.get('ticket'), body.get('method'))})
                except ValueError as e:
                    return self.err(str(e), 400)
            if path == '/api/login/mfa/verify' and method == 'POST':
                ip = self.client_ip()
                if APP.sessions.throttled(ip):
                    return self.err('слишком много попыток, подождите 5 минут', 429)
                method_id = body.get('method')
                try:
                    good = APP.mfa.verify(body.get('ticket'), method_id, body.get('code'))
                except ValueError as e:
                    APP.sessions.fail(ip)
                    return self.err(str(e), 400)
                if not good:
                    APP.sessions.fail(ip)
                    st.add_event(None, 'Вход', 'warning', f'неверный код второго фактора с адреса {ip}')
                    time.sleep(0.7)
                    return self.err('неверный код', 401)
                APP.mfa.finish(body.get('ticket'))
                APP.sessions.ok(ip)
                st.add_event(None, 'Вход', 'info', f'администратор вошёл с адреса {ip} (второй фактор: {mfa.LABELS.get(method_id, method_id).lower()})')
                if method_id == 'recovery':
                    threading.Thread(target=APP.tgbot.notice, args=('⚠️ Вход в Rack Live по запасному коду. Если это не вы — смените пароль.',), daemon=True).start()
                return self.signed_in('mfa', body.get('remember') is not False)
            if path == '/api/login/mfa/poll' and method == 'POST':
                try:
                    status = APP.mfa.poll_telegram(body.get('ticket'))
                except ValueError as e:
                    return self.err(str(e), 400)
                if status == 'denied':
                    APP.mfa.finish(body.get('ticket'))
                    st.add_event(None, 'Вход', 'warning', 'вход отклонён в Telegram')
                    return self.send({'status': 'denied'})
                if status != 'ok':
                    return self.send({'status': status})
                APP.mfa.finish(body.get('ticket'))
                st.add_event(None, 'Вход', 'info', f'администратор вошёл с адреса {self.client_ip()} (подтверждение в Telegram)')
                return self.signed_in('mfa', body.get('remember') is not False, {'status': 'ok'})
            if path == '/api/tglogin' and method == 'POST':
                # Telegram mini app: the launch data is signed with the bot token → no password needed for allowed accounts
                ip = self.client_ip()
                if APP.sessions.throttled(ip):
                    return self.err('слишком много попыток, подождите 5 минут', 429)
                user, why = alerts.verify_webapp(st.cfg.get('notify'), body.get('initData') or '')
                if not user:
                    APP.sessions.fail(ip)
                    st.add_event(None, 'Вход', 'warning', f'вход через Telegram отклонён: {why}')
                    return self.err(why, 403)
                APP.sessions.ok(ip)
                who = ' '.join(x for x in (user.get('first_name'), user.get('last_name')) if x) or str(user.get('id'))
                st.add_event(None, 'Вход', 'info', f'вход через Telegram: {who} (id {user.get("id")})')
                return self.signed_in('telegram', True, {'token': True})
            if path == '/api/tgauth/start' and method == 'POST':
                # «Войти через Telegram» on the login page: a one-time code → the bot asks «это вы?»
                ua = self.headers.get('User-Agent') or ''
                short = next((b for b in ('Edg', 'YaBrowser', 'Firefox', 'Chrome', 'Safari') if b in ua), 'браузер')
                short = {'Edg': 'Edge', 'YaBrowser': 'Яндекс Браузер'}.get(short, short) + next((f', {o}' for o in ('iPhone', 'Android', 'Windows', 'Mac', 'Linux') if o in ua), '')
                try:
                    code, url = APP.tgbot.new_code('login', self.client_ip(), short)
                except ValueError as e:
                    return self.err(str(e), 400)
                return self.send({'ok': True, 'code': code, 'url': url})
            if path == '/api/tgauth/poll' and method == 'POST':
                code = str(body.get('code') or '')
                c = APP.tgbot.check(code)
                if not c:
                    return self.send({'status': 'expired'})
                if c['status'] == 'ok' and c['kind'] == 'login':
                    APP.tgbot.consume(code)
                    u = c['user'] or {}
                    st.add_event(None, 'Вход', 'info', f"вход через Telegram: {u.get('first_name', '')} (id {u.get('id')}) с адреса {c['ip']}")
                    return self.signed_in('telegram', True, {'status': 'ok', 'token': True})
                if c['status'] == 'ok' and c['kind'] == 'link':
                    APP.tgbot.consume(code)
                    return self.send({'status': 'ok', 'user': c['user'], 'telegram': alerts.public(st.cfg.get('notify'))['telegram']})
                return self.send({'status': c['status']})
            if path == '/api/logout' and method == 'POST':
                APP.sessions.drop(self.token())
                return self.send({'ok': True}, headers={'Set-Cookie': self.cookie('', 0)})
            # ── agent push (token auth, no session) ──
            if path == '/api/site' and method == 'POST':               # a collector of a remote site delivers its devices (key auth, no session)
                tok = (self.headers.get('Authorization') or '').replace('Bearer ', '').strip()
                try:
                    return self.send(APP.sites.ingest(tok, body, self.client_ip()))
                except PermissionError as e:
                    return self.err(str(e), 401)
                except ValueError as e:
                    return self.err(str(e), 400)
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
                for k in ('title', 'poll', 'publicView', 'showClients', 'hints', 'vlans', 'devMode'):
                    if k in body:
                        s[k] = body[k]
                if body.get('newPassword'):
                    if not auth.check_password(st.cfg['auth'], body.get('oldPassword') or ''):
                        return self.err('текущий пароль неверный', 403)
                    if len(body['newPassword']) < 8:
                        return self.err('новый пароль должен быть не короче 8 символов')
                    st.cfg['auth'] = auth.hash_password(body['newPassword'])
                    APP.sessions.drop_all()                 # everyone else is signed out and forgotten — they sign in with the new password
                    st.save()
                    return self.signed_in('password', True)
                st.save()
                return self.send({'ok': True})
            if path.startswith('/api/advice/'):                  # Советы Frank
                act = path[len('/api/advice/'):]
                if act == 'refresh' and method == 'POST':
                    ok, why = APP.advisor.start(manual=True)
                    return self.send({'ok': True, 'started': ok, 'why': why})
                if act == 'close' and method == 'POST':
                    APP.advisor.close(str(body.get('id')), bool(body.get('done')))
                    return self.send({'ok': True})
                if act == 'settings' and method == 'PUT':
                    try:
                        APP.advisor.set_cfg(body)
                    except (TypeError, ValueError) as e:
                        return self.err(str(e), 400)
                    return self.send({'ok': True})
                return self.err('не найдено', 404)
            if path == '/api/tour/log' and method == 'POST':          # why the welcome tour started / stopped (shows up in «События»)
                if not self.need_admin():
                    return
                text = re.sub(r'\s+', ' ', str(body.get('text') or ''))[:700]
                if text:
                    st.add_event(None, 'Страница' if text.startswith('страница') else 'Обучение', 'info', text)
                return self.send({'ok': True})
            if path == '/api/tour' and method == 'POST':
                st.cfg['settings']['tourDone'] = True
                st.save()
                return self.send({'ok': True})
            # ── two-factor and devices (Настройки → Доступ) ──
            if path.startswith('/api/mfa/') and method == 'POST':
                act = path[len('/api/mfa/'):]
                pw_ok = lambda: auth.check_password(st.cfg.get('auth'), body.get('password') or '')
                try:
                    if act == 'status':
                        return self.send({'ok': True, **APP.mfa.status(bool(APP.tgbot.ready() and APP.tgbot.username)),
                                          'telegramLinked': len(alerts.tg_allowed(APP.tgbot.tg())),
                                          'routers': [{'id': d['id'], 'name': d.get('name')} for d in st.cfg['devices'] if d.get('driver') == 'openwrt'],
                                          'mailReady': bool(alerts.merged(st.cfg.get('notify'))['email'].get('host'))})
                    if act == 'totp/start':
                        return self.send({'ok': True, **APP.mfa.totp_begin()})
                    if act == 'totp/confirm':
                        codes = APP.mfa.totp_confirm(body.get('code'))
                        st.add_event(None, 'Защита', 'info', 'включён второй фактор: приложение с кодами')
                        return self.send({'ok': True, 'recovery': codes})
                    if act == 'target/start':
                        return self.send({'ok': True, 'to': APP.mfa.target_begin(body.get('method'), body.get('target'), body.get('device'))})
                    if act == 'target/confirm':
                        codes = APP.mfa.target_confirm(body.get('method'), body.get('code'))
                        st.add_event(None, 'Защита', 'info', f"включён второй фактор: {body.get('method')}")
                        return self.send({'ok': True, 'recovery': codes})
                    if act == 'telegram':
                        if body.get('on') and not (APP.tgbot.ready() and alerts.tg_allowed(APP.tgbot.tg())):
                            return self.err('сначала привяжите Telegram: Настройки → Уведомления')
                        c = APP.mfa.cfg()
                        c['telegram'] = bool(body.get('on'))
                        if c['telegram']:
                            c['enabled'] = True
                            if not c.get('recovery'):
                                plain, c['recovery'] = mfa.new_recovery()
                                st.save()
                                return self.send({'ok': True, 'recovery': plain})
                        else:
                            APP.mfa.remove('telegram')
                        st.save()
                        return self.send({'ok': True})
                    if act == 'remove':
                        if not pw_ok():
                            return self.err('неверный пароль', 403)
                        APP.mfa.remove(body.get('method'))
                        st.add_event(None, 'Защита', 'warning', f"выключен способ второго фактора: {body.get('method')}")
                        return self.send({'ok': True})
                    if act == 'enable':
                        c = APP.mfa.cfg()
                        if body.get('enabled'):
                            if not APP.mfa.methods(False):
                                return self.err('сначала подключите хотя бы один способ')
                            c['enabled'] = True
                        else:
                            if not pw_ok():
                                return self.err('введите пароль, чтобы выключить защиту', 403)
                            c['enabled'] = False
                            st.add_event(None, 'Защита', 'warning', 'двухфакторная защита выключена')
                        st.save()
                        return self.send({'ok': True})
                    if act == 'recovery':
                        if not pw_ok():
                            return self.err('неверный пароль', 403)
                        return self.send({'ok': True, 'recovery': APP.mfa.recovery_new()})
                    if act == 'loginbycode':
                        APP.mfa.cfg()['loginByCode'] = bool(body.get('on'))
                        st.save()
                        st.add_event(None, 'Защита', 'info', 'вход без пароля по коду ' + ('разрешён' if body.get('on') else 'запрещён'))
                        return self.send({'ok': True})
                    if act == 'policy':
                        p = APP.mfa.cfg()['policy']
                        for k, lo, hi in (('idleMin', 5, 1440), ('trustDays', 1, 365), ('sessionDays', 1, 365)):
                            if k in body:
                                p[k] = max(lo, min(hi, int(body[k])))
                        st.save()
                        return self.send({'ok': True})
                except (ValueError, TypeError) as e:
                    return self.err(str(e), 400)
                return self.err('не найдено', 404)
            if path.startswith('/api/sessions/') and method == 'POST':
                act = path[len('/api/sessions/'):]
                cur = APP.sessions.device_of(self.token())
                if act == 'list':
                    return self.send({'ok': True, 'devices': APP.sessions.devices(self.token())})
                if act == 'revoke':
                    APP.sessions.revoke(str(body.get('id')))
                    st.add_event(None, 'Защита', 'info', 'устройство отключено от Rack Live')
                    return self.send({'ok': True, 'self': str(body.get('id')) == cur})
                if act == 'others':
                    APP.sessions.revoke_others(cur)
                    st.add_event(None, 'Защита', 'info', 'все остальные устройства отключены')
                    return self.send({'ok': True})
                if act == 'trust':
                    return self.send({'ok': APP.sessions.set_trusted(str(body.get('id')), bool(body.get('trusted')))})
                return self.err('не найдено', 404)
            if path == '/api/racks' and method == 'PUT':
                racks = body.get('racks')
                if not isinstance(racks, list) or not racks:
                    return self.err('неверные данные')
                bad = power.remote_placed(racks, st.cfg['devices'])
                if bad:
                    return self.err(f"«{bad[0]}» — удалённое устройство, его нельзя поставить в «{bad[1]}». Удалённые живут только в списке устройств.")
                out = []
                for r in racks:
                    units = r.get('units') if isinstance(r.get('units'), list) else []
                    for u in units:                             # a shelf: up to 5 devices; deviceId stays the first one for older code
                        if isinstance(u, dict):
                            u.pop('powerLoad', None)            # computed for the interface (rackd/power.py), never stored
                        if isinstance(u, dict) and isinstance(u.get('deviceIds'), list):
                            u['deviceIds'] = [str(x) for x in u['deviceIds'] if x][:5]
                            u['deviceId'] = u['deviceIds'][0] if u['deviceIds'] else None
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
            if path.startswith(('/api/sites', '/api/collector')) and method in ('POST', 'PUT', 'DELETE'):         # Инструменты → Удалённые площадки (admin only)
                if not self.need_admin():
                    return
                try:
                    m = re.match(r'^/api/sites/(\w+)(/token|/rpc)?$', path)
                    if path == '/api/sites' and method == 'POST':
                        s = APP.sites.create(body.get('name'))
                        st.add_event(None, 'Площадки', 'info', f"добавлена площадка «{s['name']}»")
                        return self.send({'ok': True, 'id': s['id'], 'name': s['name'], 'token': s['token']})
                    if m and m.group(2) == '/rpc' and method == 'POST':             # ask the site's collector to do something with its own devices
                        site, op = APP.sites.get(m.group(1)), str(body.get('op') or '')
                        if not site or op not in ('state', 'action'):
                            return self.err('неверный запрос', 400)
                        args = {k: body.get(k) for k in ('key', 'action', 'params') if k in body}
                        try:
                            res = APP.sites.rpc(site['id'], op, args)
                        except (RuntimeError, TimeoutError) as e:
                            return self.err(str(e), 502)
                        if op == 'action':
                            st.add_event(None, 'Площадки', 'warning', f"на площадке «{site['name']}» выполнено действие «{args.get('action')}»: {(res or {}).get('message') or ''}"[:300])
                        return self.send({'ok': True, 'result': res})
                    if m and m.group(2) == '/token' and method == 'POST':
                        s = APP.sites.get(m.group(1))
                        return self.send({'ok': True, 'name': s['name'], 'token': s['token']}) if s else self.err('нет такой площадки', 404)
                    if m and not m.group(2) and method == 'DELETE':
                        APP.sites.remove(m.group(1))
                        return self.send({'ok': True})
                    if path == '/api/collector' and method == 'PUT':
                        APP.collector.configure(body.get('key') or None, body.get('enabled'), body.get('insecure'), body.get('level'))
                        return self.send(dict(APP.collector.public(), ok=True))
                    if path == '/api/collector/push' and method == 'POST':
                        try:
                            APP.collector.push()
                        except (RuntimeError, ValueError) as e:
                            APP.collector.status['error'] = str(e)
                            return self.err(str(e), 502)
                        return self.send(dict(APP.collector.public(), ok=True))
                except ValueError as e:
                    return self.err(str(e), 400)
                return self.err('не найдено', 404)
            if path.startswith('/api/update/') and method in ('POST', 'PUT'):
                if not self.need_admin():
                    return
                u = APP.updater
                try:
                    if path == '/api/update/check':
                        u.latest(force=True)
                    elif path == '/api/update/apply':
                        lat = u.latest()
                        if not lat or lat.get('tag') != body.get('tag'):
                            return self.err('эта версия больше не последняя — обновите страницу')
                        st.add_event(None, 'Обновление', 'warning', f"администратор запустил обновление до {lat['version']}")
                        u.apply(lat['tag'])
                    elif path == '/api/update/rollback':
                        u.rollback()
                    elif path == '/api/update/settings':
                        u.set_mode(str(body.get('mode') or ''))
                    else:
                        return self.err('не найдено', 404)
                except ValueError as e:
                    return self.err(str(e), 400)
                return self.send(dict(u.info(), ok=True))
            if path.startswith('/api/scenes/') and method in ('POST', 'DELETE'):         # demo copy · preview · apply to my plan · undo (admin only; nothing here in the demo itself)
                if not self.need_admin():
                    return
                if DEMO:
                    return self.err('в демо-режиме сцены не применяются', 400)
                try:
                    if path == '/api/scenes/demo' and method == 'DELETE':
                        APP.sandbox.stop()
                        return self.send({'ok': True, 'sandbox': APP.sandbox.status()})
                    if path == '/api/scenes/demo' and method == 'POST':
                        title, clean, ref = APP.scene_clean(str(body.get('id') or ''))
                        try:
                            res = APP.sandbox.start(ref, None if ref else clean, title)
                        except RuntimeError as e:
                            return self.err(str(e), 502)
                        st.add_event(None, 'Сцены', 'info', f'запущена демо-копия со сценой «{title}»')
                        return self.send({'ok': True, 'sandbox': res})
                    if path == '/api/scenes/preview' and method == 'POST':
                        title, clean, _ = APP.scene_clean(str(body.get('id') or ''))
                        real = [d for d in st.cfg['devices'] if d.get('driver') not in ('site_node',)]
                        return self.send(dict(scenes_mod.preview(clean, real), title=title, hasPlan=bool(st.cfg.get('plan', {}).get('buildings')), hasRacks=bool(st.cfg.get('racks'))))
                    if path == '/api/scenes/apply' and method == 'POST':
                        title, clean, _ = APP.scene_clean(str(body.get('id') or ''))
                        return self.send(dict(scenes_mod.apply_real(st, clean, body.get('mapping') or {}, str(body.get('mode') or '')), ok=True))
                    if path == '/api/scenes/undo' and method == 'POST':
                        scenes_mod.undo(st, body.get('backup'))
                        return self.send({'ok': True})
                except ValueError as e:
                    return self.err(str(e), 400)
                return self.err('не найдено', 404)
            if path == '/api/community/install' and method == 'POST':     # from the community catalog: the archive must match the sha256 in the index
                if not self.need_admin():
                    return
                rep = APP.community.install_from_index(str(body.get('id') or ''))
                if rep['ok']:
                    p = rep['plugin']
                    st.add_event(None, 'Плагины', 'info', f"из каталога сообщества: «{p['title']}» {p['version']} (риск: {p['risk']})")
                return self.send(rep)
            if path == '/api/dashboard' and method == 'PUT':     # «Главная»: widgets, their order and sizes
                ws = body.get('widgets')
                if not isinstance(ws, list) or len(ws) > 60:
                    return self.err('неверный список виджетов')
                clean = []
                for w in ws:
                    if isinstance(w, dict) and re.match(r'^[a-z]{2,20}$', str(w.get('type') or '')):
                        clean.append({'id': str(w.get('id') or '')[:24], 'type': w['type'], 'w': max(1, min(4, int(w.get('w') or 1))),
                                      'h': max(0, min(2000, int(w.get('h') or 0))), 'compact': bool(w.get('compact')), 'size': w.get('size') if w.get('size') in ('S', 'M', 'L') else None, 'title': str(w.get('title') or '')[:60],
                                      'opts': w.get('opts') if isinstance(w.get('opts'), dict) and len(json.dumps(w.get('opts'), ensure_ascii=False)) < 20000 else {}})
                st.cfg['dashboard'] = {'widgets': clean}
                st.save()
                return self.send({'ok': True})
            if path == '/api/map' and method == 'PUT':
                for k in ('positions', 'links', 'collapsed', 'wan'):
                    if k in body:
                        st.cfg['map'][k] = body[k]
                st.save()
                return self.send({'ok': True})
            if path == '/api/tglink/start' and method == 'POST':
                try:
                    code, url = APP.tgbot.new_code('link', self.client_ip())
                except ValueError as e:
                    return self.err(str(e), 400)
                return self.send({'ok': True, 'code': code, 'url': url})
            if path == '/api/tgbot/avatar' and method == 'POST':
                ids = [str(x.get('id')) for x in alerts.merged(st.cfg.get('notify'))['telegram'].get('linked') or []]
                if not APP.tgbot.username or not ids:
                    return self.err('сначала привяжите Telegram — картинка придёт в бота')
                try:
                    APP.tgbot.send_avatar(ids)
                except (ValueError, OSError) as e:
                    return self.err(str(e))
                return self.send({'ok': True, 'sent': len(ids)})
            if path == '/api/tglink/remove' and method == 'POST':
                APP.tgbot.unlink(body.get('id'))
                st.add_event(None, 'Telegram', 'info', f"отвязан аккаунт {body.get('id')}")
                return self.send({'ok': True, 'telegram': alerts.public(st.cfg.get('notify'))['telegram']})
            if path in ('/api/notify', '/api/notify/test') and method in ('PUT', 'POST'):
                # empty secret fields in the form mean "keep the saved one"
                cur = alerts.merged(st.cfg.get('notify'))
                new = alerts.merged(body)
                for ch, key in alerts.SECRETS:
                    if not (body.get(ch) or {}).get(key):
                        new[ch][key] = cur[ch][key]
                    new[ch].pop(key + 'Set', None)
                new['telegram']['linked'] = cur['telegram'].get('linked') or []      # changed only by link / unlink
                new['telegram']['avatarSent'] = cur['telegram'].get('avatarSent') or ''
                menu = APP.alerter.setup_menu(new)                   # bot menu button → mini app (None if Telegram is off)
                if path == '/api/notify/test':
                    res = APP.alerter.send(['✅ Проверка уведомлений Rack Live — если вы это видите, всё настроено.'], cfg=new) or {}
                    if menu:
                        res['кнопка в боте'] = menu
                    return self.send({'ok': True, 'results': res or {'—': 'не включён ни один канал'}})
                st.cfg['notify'] = new
                st.save()
                return self.send({'ok': True, 'menu': menu})
            if path == '/api/plan' and method == 'PUT':
                b = body.get('buildings')
                if not isinstance(b, list):
                    return self.err('неверные данные')
                st.cfg['plan'] = {'buildings': b, 'links': body.get('links') if isinstance(body.get('links'), list) else [],
                                  'poles': body.get('poles') if isinstance(body.get('poles'), list) else []}
                st.save()
                return self.send({'ok': True})
            if path == '/api/speedtest' and method == 'POST':
                num = lambda k: round(float(body[k]), 2) if isinstance(body.get(k), (int, float)) else None
                rec = {'kind': 'browser', 'down': num('down'), 'up': num('up'), 'ping': num('ping'), 'jitter': num('jitter'),
                       'note': str(body.get('note') or '')[:80], 'where': body.get('where') if isinstance(body.get('where'), dict) else None,
                       'client': speedtest.who(st.cfg['devices'], APP.states, self.client_ip())}
                return self.send({'ok': True, 'test': APP.speed.add(rec)})
            m = re.match(r'/api/speedtest/(\w+)$', path)
            if m and method == 'PUT':
                r = APP.speed.update(m.group(1), body)
                return self.send({'ok': True, 'test': r}) if r else self.err('замер не найден', 404)
            if m and method == 'DELETE':
                APP.speed.delete(m.group(1))
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
                if body.get('driver') == 'ups' and body.get('location') == 'remote':
                    return self.err(power.REMOTE_UPS)
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
                    if body.get('location') == 'remote':             # a remote device has no business with a local UPS / outlet block
                        if d.get('driver') == 'ups':
                            return self.err(power.REMOTE_UPS)
                        where = power.plugged_where(st.cfg['devices'], st.cfg['racks'], did)
                        if where:
                            return self.err(f"Удалённое устройство не может питаться от местного ИБП / блока розеток. Сейчас оно подключено: {', '.join(where)}. Уберите его оттуда и повторите.")
                        placed = power.placed_where(st.cfg['racks'], did)
                        if placed:
                            return self.err(f"Удалённое устройство не ставится в шкаф, щиток или комнату — оно живёт только в списке устройств. Сейчас оно стоит в: {', '.join(placed)}. Уберите его оттуда и повторите.")
                    d = st.upsert_device(body, did)
                    APP.last_start.pop(did, None)
                    return self.send({'ok': True, 'device': st.public_device(d)})
                if sub is None and method == 'DELETE':
                    st.add_event(None, d.get('name'), 'info', 'устройство удалено')
                    st.delete_device(did)
                    APP.backups.forget(did)
                    APP.uptime.forget(did)
                    APP.states.pop(did, None)
                    return self.send({'ok': True})
                if sub == 'poll' and method == 'POST':
                    return self.send({'ok': True, 'state': APP.poll_device(d)})
                if sub == 'disks' and method == 'POST':               # S.M.A.R.T. of the disks (the device card, tab «Диски»)
                    drv = REGISTRY.get(d.get('driver'))
                    if not hasattr(drv, 'disks'):
                        return self.err('у этого устройства нет сведений о дисках')
                    try:
                        if body.get('op') == 'test':
                            kind = 'long' if body.get('kind') == 'long' else 'short'
                            res = drv.disk_test(d, str(body.get('disk') or ''), kind)
                            st.add_event(did, d.get('name'), 'info', f"запущен {'расширенный' if kind == 'long' else 'быстрый'} тест диска {body.get('disk')}")
                            return self.send({'ok': True, 'message': res})
                        res = drv.disks(d)
                        APP.smart_seen(d, res)
                        return self.send(dict(res, ok=True, now=time.time()))
                    except DriverError as e:
                        return self.err(str(e), 502)
                if sub == 'containers' and method == 'POST':           # Docker in detail (the device card, tab «Сервисы»)
                    drv = REGISTRY.get(d.get('driver'))
                    if not hasattr(drv, 'containers'):
                        return self.err('у этого устройства нет сведений о контейнерах')
                    if body.get('op') == 'note':                        # the owner's own one-line description of a container
                        name = str(body.get('name') or '')
                        if not re.match(r'^[\w.-]{1,80}$', name):
                            return self.err('неверное имя контейнера')
                        notes = d.setdefault('dockerNotes', {})
                        text = str(body.get('text') or '').strip()[:200]
                        notes[name] = text
                        if not text:
                            notes.pop(name, None)
                        st.save()
                        return self.send({'ok': True})
                    try:
                        return self.send(dict(drv.containers(d, d.get('dockerNotes') or {}), ok=True, now=time.time()))
                    except DriverError as e:
                        return self.err(str(e), 502)
                if sub == 'plugins' and method == 'POST':
                    drv = REGISTRY.get(d.get('driver'))
                    comm = APP.community.target_of(d.get('driver')) is not None and hasattr(drv, 'command')
                    if not hasattr(drv, 'plugins') and not comm:
                        return self.err('у этого устройства нет плагинов')
                    if body.get('op') == 'status':
                        res = dict(drv.plugins(d), ok=True) if hasattr(drv, 'plugins') else {'ok': True, 'plugins': []}
                        for card in res['plugins']:
                            if card.get('id') in ('collector', 'rcos'):         # what the card needs from this installation: the address to call, the site and its live state
                                ci = (d.get('panelInfo') or {}).get(card['id']) or {}
                                card['serverUrl'] = (st.cfg.get('apps') or {}).get('url') or ''
                                card['info'] = ci or None
                                card['site'] = next((s for s in APP.sites.public() if s['id'] == ci.get('siteId')), None)
                        if comm:                                 # community plugins (rackd/community.py): their status is read by their own read-only script
                            res['plugins'] = res['plugins'] + APP.community.cards(d, drv)
                        return self.send(res)
                    pid, op = str(body.get('plugin') or ''), str(body.get('op') or '')
                    if op == 'job':                             # progress of a background install
                        j = APP.jobs.get(str(body.get('job') or ''))
                        return self.send({k: v for k, v in j.items() if k != 'device'} if j and j['device'] == did else {'done': True, 'error': 'задача не найдена'})
                    if pid.startswith('x-'):                    # a community plugin: only install / remove, as a background job, after the administrator confirmed the exact commands (digest)
                        if not comm or op not in ('install', 'remove', 'run'):
                            return self.err('неверный запрос плагина')
                        if DEMO:
                            return self.err('в демо-режиме плагины сообщества не запускаются', 400)
                        APP.store.add_event(did, d.get('name'), 'warning', f'{"инструмент" if op == "run" else "плагин"} сообщества {pid[2:]}: ' + {'install': 'установка', 'remove': 'удаление', 'run': 'запуск'}[op] + ' подтверждены администратором')
                        return self.send({'ok': True, 'job': APP.start_plugin_job(d, community.Shim(APP.community, drv), pid, op, body)['id']})
                    if pid in ('collector', 'rcos') and op in ('install', 'remove'):
                        try:
                            body = APP.collector_prepare(d, body, op)
                        except ValueError as e:
                            return self.err(str(e))
                    if op in getattr(drv, 'async_ops', ()):
                        return self.send({'ok': True, 'job': APP.start_plugin_job(d, drv, pid, op, body)['id']})
                    try:
                        res = drv.plugin(d, pid, op, body)
                    except ValueError as e:                     # bad .conf / domains: a readable reason
                        return self.err(str(e))
                    except DriverError as e:
                        if op not in ('preview',):
                            st.add_event(did, d.get('name'), 'warning', f'плагин {pid}: {e}')
                        raise
                    if res.get('sshSave'):                      # Entware login checked → keep it (password is a secret)
                        d.update(res.pop('sshSave'))
                        st.save()
                        return self.send(res)
                    if pid != 'awg':
                        if op in ('install', 'remove') and res.get('ok'):
                            st.add_event(did, d.get('name'), 'info', res.get('message'))
                        elif op == 'install':
                            st.add_event(did, d.get('name'), 'warning', res.get('message'))
                        return self.send(res)
                    tun = [t for t in d.get('rlTunnels') or [] if t.get('iface') != res.get('iface') and t.get('iface') != res.get('removed')]
                    if op == 'install':
                        d['rlTunnels'] = tun + [{'iface': res['iface'], 'name': res['name'], 'domains': res['domains'], 't': int(time.time())}]
                    elif op == 'domains':
                        old = next((t for t in d.get('rlTunnels') or [] if t.get('iface') == res['iface']), {})
                        d['rlTunnels'] = tun + [dict(old, domains=res['domains'])]
                    elif op == 'remove':
                        d['rlTunnels'] = tun
                    if op in ('install', 'domains', 'remove', 'component'):
                        st.save()
                        st.add_event(did, d.get('name'), 'info', res.get('message') or f'плагин {pid}: {op}')
                        APP.last_start.pop(did, None)               # re-poll soon: the VPN tab shows the new tunnel
                    return self.send(res)
                if sub == 'creds' and method == 'POST':
                    # web panel link + login for the device card («Открыть», «Скопировать») — admin only, never part of /api/state
                    return self.send({'ok': True, **web_access(d)})
                if sub == 'token' and method == 'POST':
                    return self.send({'ok': True, 'agentToken': d.get('agentToken')})
                if sub == 'action' and method == 'POST':
                    return self.send(APP.run_action(d, body.get('action'), body.get('params') or {}))
            if path in ('/api/ai', '/api/ai/test') and method in ('PUT', 'POST'):
                cur =assistant.merged(st.cfg.get('ai'))
                new = assistant.merged(dict(cur, **{k: v for k, v in body.items() if k in assistant.DEFAULT and k != 'key'}))
                # empty key = keep the saved one, but only for the same provider (a DeepSeek key must not go to another service)
                new['key'] = str(body.get('key') or '').strip() or (cur['key'] if new['preset'] == cur['preset'] else '')
                new['limit'] = max(0, int(new.get('limit') or 0))
                if path == '/api/ai/test':
                    try:
                        return self.send({'ok': True, 'answer': assistant.ping(new)[:200]})
                    except assistant.AiError as e:
                        return self.send({'ok': False, 'error': str(e)})
                st.cfg['ai'] = new
                st.save()
                return self.send({'ok': True})
            if path == '/api/ai/ask' and method == 'POST':
                try:
                    job = APP.ai.start(body.get('chat') or None, body.get('text'))
                except assistant.AiError as e:
                    return self.err(str(e))
                return self.send({'ok': True, 'job': job['id'], 'chat': job['chat']})
            m = re.match(r'/api/ai/chats/(\w+)$', path)
            if m and method == 'DELETE':
                APP.ai.delete_chat(m.group(1))
                return self.send({'ok': True})
            if m and method == 'PUT':
                return self.send({'ok': bool(APP.ai.rename_chat(m.group(1), body.get('title')))})
            if path == '/api/ai/models' and method == 'POST':
                try:
                    return self.send(dict(APP.ai.models(), ok=True))
                except assistant.AiError as e:
                    return self.err(str(e))
            if path == '/api/ai/act' and method == 'POST':     # run / drop an action Frank proposed — only by this press
                try:
                    p = APP.ai.act(str(body.get('chat') or ''), str(body.get('proposal') or ''), bool(body.get('run')))
                except assistant.AiError as e:
                    return self.err(str(e))
                return self.send({'ok': True, 'proposal': p, 'chat': APP.ai.chat_view(str(body.get('chat') or ''))})
            if path == '/api/ai/job' and method == 'POST':
                j = APP.ai.jobs.get(str(body.get('job') or ''))
                return self.send(j or {'done': True, 'error': 'вопрос не найден — задайте его ещё раз'})
            if path in ('/api/dev/op', '/api/dev/job') and method == 'POST':
                if not self.need_admin():
                    return
                if path == '/api/dev/job':
                    j = APP.jobs.get(str(body.get('job') or ''))
                    return self.send({k: v for k, v in j.items() if k != 'device'} if j and j.get('device') == '*' else {'done': True, 'error': 'задача не найдена'})
                try:
                    return self.send(APP.dev_op(body))
                except PermissionError as e:
                    return self.err(str(e), 403)
                except ValueError as e:
                    return self.err(str(e), 400)
                except Exception as e:
                    return self.err(str(e), 502)
            if path in ('/api/network/apply', '/api/network/confirm', '/api/network/revert') and method == 'POST':
                if not self.need_admin():
                    return
                try:
                    return self.send({'apply': lambda: APP.hostnet.apply(body), 'confirm': APP.hostnet.confirm, 'revert': APP.hostnet.revert}[path.rsplit('/', 1)[1]]())
                except ValueError as e:
                    return self.err(str(e), 400)
            if path == '/api/cameras/creds' and method == 'POST':        # the list of camera passwords (they never come back to the browser)
                if not self.need_admin():
                    return
                try:
                    return self.send({'ok': True, 'id': APP.cameras.add_cred(body.get('user'), body.get('password'), str(body.get('label') or '')), 'creds': APP.cameras.creds_public()})
                except cameras.CamError as e:
                    return self.err(str(e), 400)
            m = re.match(r'^/api/cameras/creds/(c[0-9a-f]{8})$', path)
            if m and method == 'DELETE':
                if not self.need_admin():
                    return
                APP.cameras.del_cred(m.group(1))
                return self.send({'ok': True, 'creds': APP.cameras.creds_public()})
            if path == '/api/cameras/bulk' and method == 'POST':        # one action on several cameras: a background job
                if not self.need_admin():
                    return
                try:
                    return self.send({'ok': True, 'job': APP.cameras.bulk_start(body)})
                except cameras.CamError as e:
                    return self.err(str(e), 400)
            if path in ('/api/cameras/start', '/api/cameras/stop', '/api/cameras/probe', '/api/cameras/op') and method == 'POST':
                if not self.need_admin():
                    return
                try:
                    if path.endswith('stop'):
                        APP.cameras.stop()
                        return self.send({'ok': True})
                    if path.endswith('start'):
                        ok, err = APP.cameras.start(body.get('cidrs') or body.get('cidr') or '')
                        return self.send({'ok': True}) if ok else self.err(err or 'не удалось начать', 400)
                    if path.endswith('probe'):
                        return self.send({'ok': True, 'item': APP.cameras.probe_one(body.get('ip'))})
                    return self.send(APP.cameras.op(body))
                except cameras.CamError as e:
                    return self.err(str(e), 400)
            if path in ('/api/netscan/start', '/api/netscan/stop') and method == 'POST':
                if not self.need_admin():
                    return
                if path.endswith('stop'):
                    APP.netscan.stop()
                    return self.send({'ok': True})
                ok, err = APP.netscan.start(body.get('cidrs') or body.get('cidr') or '')
                return self.send({'ok': ok, 'error': err}) if ok else self.err(err or 'не удалось начать', 400)
            if path == '/api/routers/scan' and method == 'POST':
                return self.send({'ok': True, 'started': APP.routers.run()})
            if path == '/api/routers/dismiss' and method == 'POST':
                APP.routers.dismiss(str(body.get('mac') or ''), bool(body.get('on', True)))
                return self.send({'ok': True})
            if path == '/api/apps' and method == 'POST':
                return self.apps(body)
            if path == '/api/inet' and method == 'PUT':
                c = st.cfg.setdefault('inet', {})
                for k in ('enabled', 'hours', 'tariff', 'server', 'channels', 'servers'):
                    if k in body:
                        c[k] = body[k]
                st.save()
                return self.send({'ok': True})
            if path == '/api/inet/run' and method == 'POST':
                return self.send({'ok': True, 'started': APP.inet.start()})
            if path == '/api/extscan' and method == 'PUT':
                c = st.cfg.setdefault('extscan', {})
                for k in ('enabled', 'device'):
                    if k in body:
                        c[k] = body[k]
                st.save()
                return self.send({'ok': True})
            if path == '/api/extscan/run' and method == 'POST':
                if not APP.extscan.scanner():
                    return self.err('нет внешнего сервера: добавьте любой VPS как «Сервер / VPS по SSH»')
                return self.send({'ok': True, 'started': APP.extscan.start()})
            if path == '/api/netroles' and method == 'PUT':         # «this network is the main one / guests / …»
                key, role = str(body.get('key') or ''), body.get('role')
                if not re.match(r'^\w+:\w+$', key) or (role and role not in newdev.ROLES):
                    return self.err('неверная сеть или роль')
                roles = st.cfg.setdefault('netroles', {})
                if role:
                    roles[key] = role
                else:
                    roles.pop(key, None)
                st.save()
                return self.send({'ok': True})
            if path == '/api/clients' and method == 'POST':          # a client on the router: name, static IP, speed limit, policy
                d = st.device(str(body.get('router') or ''))
                drv = d and REGISTRY.get(d.get('driver'))
                if not drv or not getattr(drv, 'client', None):
                    return self.err('этот роутер не умеет настраивать клиентов')
                if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', str(body.get('mac') or '').lower()):
                    return self.err('неверный MAC-адрес')
                mg = (APP.states.get(d['id']) or {}).get('clientMgmt')
                if mg and not mg.get('ok'):
                    return self.err('настройки клиентов на этом роутере отключены: ' + mg.get('reason', ''))
                want = {k: body[k] for k in ('name', 'ip', 'limit', 'policy', 'forget') if k in body}
                try:
                    done = drv.client(d, str(body.get('mac') or ''), want)
                except DriverError as e:
                    return self.err(str(e))
                if done:
                    st.add_event(d['id'], d.get('name'), 'info', f"клиент {body.get('label') or body.get('mac')}: " + ', '.join(done))
                state = APP.poll_device(d)
                return self.send({'ok': True, 'done': done, 'state': json.loads(json.dumps(state))})
            if path == '/api/newdev/trust' and method == 'POST':
                APP.newdev.trust(str(body.get('mac') or ''), bool(body.get('on', True)))
                st.bump()
                return self.send({'ok': True})
            m = re.match(r'/api/backups/(\w+)/run$', path)
            if m and method == 'POST':
                d = st.device(m.group(1))
                if not d or not hasattr(REGISTRY.get(d.get('driver')), 'backup'):
                    return self.err('у этого устройства нет бэкапа конфигурации')
                v, msg = APP.take_backup(d, force=True)
                return self.send({'ok': True, 'changed': bool(v), 'message': msg})
            if path == '/api/security/ignore' and method == 'POST':
                sec = st.cfg.setdefault('security', {})
                ign = [x for x in sec.get('ignored') or [] if x != body.get('id')]
                if body.get('ignore'):
                    ign.append(str(body.get('id')))
                sec['ignored'] = ign
                st.save()
                return self.send({'ok': True})
            if path == '/api/detect' and method == 'POST':
                return self.send({'ok': True, 'found': detect.detect(body.get('host'))})
            if path == '/api/ups/find' and method == 'POST':
                # smart UPS: NUT servers (UPS on USB to a NAS / server) and network cards (UPS-MIB) among our devices and the routers' clients
                hosts = [d.get('host') for d in st.cfg['devices'] if d.get('location') != 'remote']
                hosts += [c.get('ip') for s in list(APP.states.values()) for c in (s or {}).get('clients') or []]
                if body.get('host'):
                    hosts.insert(0, body['host'])
                from .drivers import ups as ups_drv
                return self.send({'ok': True, 'found': ups_drv.find(hosts)})
            if path == '/api/test' and method == 'POST':
                drv = REGISTRY.get(body.get('driver'))
                if not drv:
                    return self.err('неизвестный тип')
                cfg = dict(body)
                if body.get('id'):
                    old = st.device(body['id']) or {}
                    for k in ('password', 'token', 'privateKey', 'tokenSecret'):
                        if not cfg.get(k):
                            cfg[k] = old.get(k)
                try:
                    if getattr(drv, 'wants_ctx', False):
                        cfg['_ctx'] = {'states': APP.states, 'devices': st.cfg['devices'], 'racks': st.cfg['racks']}
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
        scene_src = os.environ.get('RL_SCENE')          # a demo copy started by the sandbox (rackd/sandbox.py) shows a made-up network from a scene instead of the demo office
        if scene_src:
            from . import scenes
            sc = {'builtin:campus': scenes.campus, 'builtin:starter': scenes.starter}.get(scene_src)
            sc = sc() if sc else json.load(open(scene_src, encoding='utf-8'))
            errs, _, clean = scenes.validate(sc)
            if errs:
                raise SystemExit('сцена не подходит: ' + '; '.join(errs[:3]))
            scenes.seed(APP.store, clean)
        else:
            demo.seed(APP.store)
        APP.speed.items = APP.store._load('speedtests.json', [])
        APP.inet.items = APP.store._load('inetspeed.json', [])
        APP.inet.last_run = max([x['t'] for x in APP.inet.items] or [0])
        APP.newdev = newdev.NewDevices(APP.store)
        if not APP.uptime.data:
            APP.uptime.seed_demo(APP.store.cfg['devices'])
        APP.store.cfg['auth'] = APP.store.cfg.get('auth') or {'demo': True}
        if not scene_src:
            APP.sites.demo_seed()
        log('DEMO mode: made-up office network, login disabled')
    threading.Thread(target=APP.poller, daemon=True).start()
    if not DEMO or os.environ.get('RL_E2E'):
        threading.Thread(target=APP.collector.loop, daemon=True).start()
        threading.Thread(target=APP.collector.link_loop, daemon=True).start()        # «collector» mode: reports this installation to a main one (Инструменты → Удалённые площадки)
        threading.Thread(target=APP.updater.loop, daemon=True).start()          # looks for a new release now and then (Settings → О программе)
    port = int(os.environ.get('RL_PORT', '8080'))
    log(f'Rack Live {VERSION}: http://0.0.0.0:{port}  data={DATA}  drivers={", ".join(REGISTRY)}')
    APP.store.add_event(None, 'Rack Live', 'info', f'сервер запущен (версия {VERSION})')

    def stop(*_):
        APP.sandbox.stop()
        APP.store.save_runtime()
        os._exit(0)
    signal.signal(signal.SIGTERM, stop)
    srv = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    finally:
        APP.store.save_runtime()
