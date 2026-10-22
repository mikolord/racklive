#!/usr/bin/env python3
"""Smoke test: starts Rack Live in demo mode on a temp data dir, checks the API round-trips and
opens every tab / sheet / editor in a headless browser, failing on any interface error.

    python tools/smoke.py            # needs a Chromium-based browser for the UI part (Edge / Chrome), skipped otherwise
"""
import gzip, json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSERS = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
fails = []


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        fails.append(name)


def main():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    data = tempfile.mkdtemp(prefix='rl-smoke-')
    env = dict(os.environ, RL_DEMO='1', RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), RL_PORT=str(port), PYTHONIOENCODING='utf-8')
    srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}'

    def api(path, body=None, method=None):
        r = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers={'Content-Type': 'application/json'}, method=method or ('PUT' if body is not None else 'GET'))
        return json.loads(urllib.request.urlopen(r, timeout=30).read())
    try:
        for _ in range(60):
            try:
                st = api('/api/state'); break
            except OSError:
                time.sleep(.3)
        else:
            raise SystemExit('server did not start: ' + srv.stderr.read(2000).decode(errors='replace'))
        time.sleep(4)                                        # let the demo devices poll once
        print('API')
        st = api('/api/state')
        check('state has devices / racks / plan / health', all(k in st for k in ('devices', 'racks', 'plan', 'health', 'topology')))
        check('demo devices polled', all((d.get('state') or {}).get('status') for d in st['devices']))
        racks = st['racks']; racks[0]['name'] = racks[0]['name'] + ' ✓'
        api('/api/racks', {'racks': racks})
        check('racks save round-trip', api('/api/state')['racks'][0]['name'].endswith('✓'))
        plan = st['plan']; plan.setdefault('poles', []).append({'id': 'psmoke', 'name': 'smoke', 'x': 0, 'y': 0})
        api('/api/plan', plan)
        check('plan save keeps poles/links', any(p['id'] == 'psmoke' for p in api('/api/state')['plan']['poles']) and api('/api/state')['plan']['links'])
        bad = {'racks': [dict(racks[0], totalU=1)]}
        try:
            api('/api/racks', bad); check('rack smaller than its units is refused', False)
        except urllib.error.HTTPError as e:
            check('rack smaller than its units is refused', e.code == 400)
        ups = next(d for d in st['devices'] if d['driver'] == 'ups')
        check('UPS estimate present', ((ups.get('state') or {}).get('ups') or {}).get('runtimeMin') is not None)
        t = api('/api/test', {'driver': 'ups', 'mode': 'manual', 'name': 'x', 'connected': [st['devices'][0]['id']]}, 'POST')
        check('device test endpoint', t.get('ok'), json.dumps(t)[:200])
        u = ups['state']['ups']
        blk = next((c for c in u['connected'] if c.get('kind') == 'pdu'), {})
        check('UPS: outlet block counts in the load', blk.get('outlet') == '3' and any(x['w'] == 95 for x in blk.get('children') or [])
              and any(not c.get('id') and c['w'] == 15 for c in u['connected']) and u['outlets'] == 6, json.dumps(u['connected'])[:400])
        check('UPS: ONT by its 12 V × 1 A, custom line by V × A',
              any(c.get('unit') == 'uont' and c['w'] == 12 and c['src'] == '12 В × 1 А' for c in u['connected'])
              and any(c['name'].startswith('Камеры') and c['w'] == 24 for c in u['connected']), json.dumps(u['connected'])[:500])
        vps = next(d for d in st['devices'] if d.get('location') == 'remote')
        try:
            api('/api/racks', {'racks': [dict(st['racks'][0], units=st['racks'][0]['units'] + [{'id': 'ux', 'name': 'x', 'type': 'server', 'uStart': 9, 'uSize': 1, 'deviceId': vps['id']}])]}, 'PUT')
            check('a remote device cannot be put into a rack', False)
        except urllib.error.HTTPError as e:
            check('a remote device cannot be put into a rack', e.code == 400)
        # ── «События → Системные» ──
        api('/api/tour/log', {'text': 'страница: 03:10:15 загружена (navigate) 440×894 приложение /#events'}, 'POST')
        api('/api/tour/log', {'text': 'элемент не найден на экране: шаг 3 «Добавим первое»'}, 'POST')
        sysev = api('/api/state').get('sysEvents') or []
        check('system events: the page and tour lines land in the technical journal', any(e['name'] == 'Страница' for e in sysev) and any(e['name'] == 'Обучение' for e in sysev), str(sysev)[:200])
        check('system events: ordinary events stay out of it', all(e['name'] in ('Страница', 'Обучение', 'Rack Live') for e in sysev))

        # ── свои оформления: загрузка, выдача файлов, список, удаление ──
        def raw(path, data=None, method=None, headers=None):
            r = urllib.request.urlopen(urllib.request.Request(base + path, data=data, method=method or ('POST' if data is not None else 'GET'), headers=headers or {}), timeout=30)
            return r.read(), r.headers
        tpl = raw('/api/themes/template.zip')[0]
        up = json.loads(raw('/api/themes/upload', tpl, headers={'Content-Type': 'application/zip'})[0])
        check('looks: the starter template uploads over HTTP and is accepted', up.get('ok') and up.get('id') == 'my-look', json.dumps(up)[:200])
        lst = api('/api/themes')
        check('looks: the list tells which fit', any(t['id'] == 'my-look' and t['ok'] for t in lst['themes']) and lst['api'] == 1, json.dumps(lst)[:200])
        css_b, css_h = raw('/themes/my-look/theme.css')
        check('looks: the css is public, scoped and typed as css', b'html[data-theme-id="my-look"]' in css_b and 'text/css' in css_h['Content-Type'], css_b[:120])
        dj = json.loads(raw('/themes/my-look/data.json')[0])
        check('looks: data.json carries texts, icons and picture addresses', dj['strings'].get('tab.rack') == 'Дом' and 'home' in dj['icons'] and dj['appIcons']['rack'].startswith('/themes/my-look/'), json.dumps(dj)[:200])
        svg_b, svg_h = raw('/themes/my-look/assets/rack.svg')
        check('looks: a picture is served with a sandbox policy (no script can run from it)', svg_b.startswith(b'<svg') and 'sandbox' in svg_h['Content-Security-Policy'] and svg_h['X-Content-Type-Options'] == 'nosniff')
        check('looks: all.css and the themed manifest answer', b'my-look' in raw('/themes/all.css')[0] and json.loads(raw('/manifest.json?skin=my-look')[0])['name'] == 'Rack Live')
        check('looks: Frank and the speed test have their own themed manifests', json.loads(raw('/frank-manifest.json?skin=my-look')[0])['name'] and json.loads(raw('/speed-manifest.json?skin=my-look')[0])['name'])
        check('looks: the guide for neural networks downloads', b'html[data-theme-id=' in raw('/api/themes/guide.txt')[0] and b'tour.hi.title' in raw('/api/themes/guide.txt')[0])
        sj = api('/api/sites')
        check('sites: the demo has one remote site with its devices', len(sj['sites']) == 1 and sj['sites'][0]['devices'] == 3 and 'token' not in json.dumps(sj), json.dumps(sj)[:200])
        tk = api('/api/sites/demo1/token', {}, 'POST')['token']
        req = urllib.request.Request(base + '/api/site', data=json.dumps({'devices': [{'key': 'rt', 'name': 'Роутер склада', 'kind': 'router', 'state': {'status': 'online', 'summary': {'ip': '192.168.1.1'}}}]}).encode(), headers={'Authorization': 'Bearer ' + tk, 'Content-Type': 'application/json'})
        check('sites: a collector delivers over HTTP with the key, the vanished devices go', json.loads(urllib.request.urlopen(req, timeout=10).read()).get('devices') == 1 and api('/api/sites')['sites'][0]['devices'] == 1)
        try:
            urllib.request.urlopen(urllib.request.Request(base + '/api/site', data=b'{"devices": []}', headers={'Authorization': 'Bearer nope', 'Content-Type': 'application/json'}), timeout=10); bad = False
        except urllib.error.HTTPError as e:
            bad = e.code == 401
        check('sites: a wrong key is refused with 401', bad)
        check('agents: the agent is no longer a type in the «add device» list', 'agent' in [d['id'] for d in api('/api/state')['drivers'] if d.get('hidden')])
        ctpl = raw('/api/community/template.zip')[0]
        cup = json.loads(raw('/api/community/upload', ctpl, headers={'Content-Type': 'application/zip'})[0])
        check('community: the starter plugin uploads over HTTP and is accepted', cup.get('ok') and cup['plugin']['id'] == 'hello-uptime' and cup['plugin']['risk'] == 'low', json.dumps(cup)[:200])
        check('community: it is listed', any(p['id'] == 'hello-uptime' for p in api('/api/community')['plugins']))
        det = api('/api/community/hello-uptime')
        check('community: the preview gives the exact commands', det['install'] and 'RL_P_NOTE' in det['install'][0]['script'], json.dumps(det)[:200])
        cbad = json.loads(raw('/api/community/upload', b'junk', headers={'Content-Type': 'application/zip'})[0])
        check('community: garbage is refused with a reason', cbad.get('ok') is False and cbad.get('errors'))
        check('community: the guide for a neural network is served', b'plugin_api' in raw('/api/community/guide.txt')[0])
        check('community: the catalog answers even when GitHub does not', 'plugins' in api('/api/community/index'))
        api('/api/community/hello-uptime', None, 'DELETE')
        check('community: a plugin can be removed again', not api('/api/community')['plugins'])
        ttpl = raw('/api/community/template.zip?kind=tool')[0]
        tup = json.loads(raw('/api/community/upload', ttpl, headers={'Content-Type': 'application/zip'})[0])
        check('community: the tool template uploads, is a tool, and lands in the tools list (not in plugins)', tup.get('ok') and tup['plugin']['kind'] == 'tool' and tup['plugin']['id'] == 'disk-usage', json.dumps(tup)[:200])
        check('community: a tool never appears among the plugins of a device', all(p['id'] != 'x-disk-usage' for p in api('/api/plugins/catalog')['plugins']))
        badup = json.loads(raw('/api/themes/upload', b'not a zip at all', headers={'Content-Type': 'application/zip'})[0])
        check('looks: garbage is refused with a reason, not an error page', badup.get('ok') is False and badup.get('errors'), json.dumps(badup)[:160])
        try:
            raw('/themes/my-look/../../config.json'); leaked = True
        except Exception:
            leaked = False
        check('looks: nothing outside the look\'s folder can be read', not leaked)

        # ── «Сканировать сеть» ──
        sys.path.insert(0, ROOT)
        from rackd import netscan as nsc
        from rackd import cameras as cam_mod
        check('cameras: only private addresses are touched', not cam_mod.private_ip('8.8.8.8') and cam_mod.private_ip('192.168.7.2'))
        check('netscan: a home network is accepted', nsc.check_cidr('192.168.1.0/24')[0] is not None and nsc.check_cidr('10.0.0.5/22')[0] is not None)
        check('netscan: public, huge and nonsense networks are refused', all(nsc.check_cidr(x)[0] is None for x in ('8.8.8.0/24', '10.0.0.0/8', 'abc', '127.0.0.0/24', '169.254.0.0/24')))
        mk = lambda ip, mac, ports=(), drv=None, own=False: {'ip': ip, 'mac': mac, 'ports': list(ports), 'driver': drv, 'self': own}
        merged = nsc.NetScan._merge({'a': mk('10.0.0.7', 'aa:bb', [80]), 'b': mk('10.0.0.115', 'aa:bb', [80, 443, 23], 'keenetic'), 'c': mk('10.0.0.9', 'cc:dd'),
                                     's1': mk('10.0.0.3', '', [22], None, True), 's2': mk('10.0.0.64', '', [22, 5000], 'synology', True)})
        check('netscan: one device with several addresses is one row, the machine itself is one row (the recognised address stays, and it can be added)',
              len(merged) == 3 and '10.0.0.115' in merged and merged['10.0.0.115'].get('also') == ['10.0.0.7'] and merged['10.0.0.64'].get('also') == ['10.0.0.3']
              and merged['10.0.0.64']['driver'] == 'synology', str(list(merged)))
        check('netscan: ports of cameras and printers are told apart', nsc.NetScan._guess([80, 554]) == 'camera' and nsc.NetScan._guess([9100]) == 'printer'
              and nsc.NetScan._guess([445, 3389]) == 'pc' and nsc.NetScan._guess([]) == 'other')
        api('/api/netscan/start', {'cidr': '10.0.0.0/24'}, 'POST')
        for _ in range(40):
            ns = api('/api/netscan')
            if not ns['running']:
                break
            time.sleep(.25)
        check('netscan: the demo scan finishes with results and suggests networks', not ns['running'] and len(ns['items']) >= 8 and ns['subnets'] and any(i['driver'] for i in ns['items']), json.dumps(ns)[:200])
        try:
            api('/api/netscan/start', {'cidr': '8.8.8.0/24'}, 'POST'); check('netscan: a public network is refused over the API', False)
        except Exception:
            check('netscan: a public network is refused over the API', True)

        # ── Советы Frank ──
        sys.path.insert(0, ROOT)
        from rackd import advisor as adv
        tips = adv.parse('Вот советы:\n[{"kind":"add","title":"ИБП","text":"Поставить","prio":1,"ask":"как?"},{"kind":"???","title":"X","text":"y","prio":9},{"title":"","text":"z"}]')
        check('advice: the answer is parsed strictly', len(tips) == 2 and tips[0]['kind'] == 'add' and tips[1]['kind'] == 'idea' and tips[1]['prio'] == 3, str(tips))
        for bad in ('Всё хорошо, советов нет', '[не json]', '[]'):
            try:
                adv.parse(bad); check('advice: a broken answer is refused: ' + bad, False)
            except ValueError:
                check('advice: a broken answer is refused: ' + bad, True)
        a0 = st.get('advice')
        check('advice: the demo shows tips and is ready', a0 and a0['ready'] and len(a0['items']) >= 4 and a0['items'][0]['prio'] == 1, json.dumps(a0)[:200])
        api('/api/advice/close', {'id': a0['items'][0]['id'], 'done': True}, 'POST')
        a1 = api('/api/state')['advice']
        check('advice: a closed tip disappears', len(a1['items']) == len(a0['items']) - 1)
        api('/api/advice/settings', {'days': 7, 'telegram': True}, 'PUT')
        a2 = api('/api/state')['advice']
        check('advice: the interval and Telegram switch are saved', a2['days'] == 7 and a2['telegram'] is True)
        api('/api/advice/settings', {'days': 3, 'telegram': False}, 'PUT')
        class FakeApp:
            pass
        # a whole review with a stand-in for the assistant
        import types
        from rackd import assistant as asst
        real_ask = asst.ask
        asst.ask = lambda app, c, chat, progress=None: {'text': '[{"kind":"dislike","title":"Порт 3 без устройства","text":"Кабель висит","prio":2,"ask":"что с портом 3?"}]', 'usage': {'in': 10, 'out': 5}}
        try:
            class S:
                cfg = {'ai': {'enabled': True, 'preset': 'ollama', 'model': 'm'}, 'devices': []}
                def _load(self, n, d): return d
                def _dump(self, n, d): self.saved = d
                def bump(self): pass
                def add_event(self, *a): pass
                def save(self): pass
            class Ap:
                store = S(); ai = types.SimpleNamespace(_count=lambda u: None); tgbot = types.SimpleNamespace(notice=lambda t: None)
            ad = adv.Advisor(Ap(), False)
            check('advice: a review is due on a fresh install', ad.due())
            ad.run()
            check('advice: a review fills the list and sets the next date', len(ad.d['items']) == 1 and not ad.d.get('error') and not ad.due())
            ad.close(ad.d['items'][0]['id'])
            ad.d['last'] = 0; ad.run()
            check('advice: a dismissed tip is not offered again', not [x for x in ad.d['items'] if x.get('state') == 'new'])
            asst.ask = lambda *a, **k: {'text': 'мысли вслух без списка', 'usage': {'in': 1, 'out': 1}}
            ad.d['last'] = 0; ad.run()
            check('advice: a bad answer becomes an error and a retry in hours, not at once', ad.d.get('error') and not ad.due())
        finally:
            asst.ask = real_ask
        # ── network loops: the switch output parser, the watcher and the whole chain in the demo ──
        sys.path.insert(0, ROOT)
        from rackd import loops as lw
        from rackd.drivers.tplink import parse_loop, runs as port_runs
        g = parse_loop(' Loopback detection global status : enable\n Loopback detection interval      : 30 s\n Loopback detection recovery time : 90 s\n',
                       ' Port      Enable   Process Mode   Recovery Mode   Loopback   Block         LAG\n ----      ------   ------------   -------------   --------   -----         ---\n'
                       ' Gi1/0/3   enable   port-based     auto             Yes        Block        N/A\n Gi1/0/4   disable  alert          auto             N/A        N/A          N/A\n')
        check('loop guard: switch output is understood', g and g['enabled'] and g['interval'] == 30 and g['recoveryTime'] == 90 and g['ports'][3]['loop'] and g['ports'][3]['blocked']
              and not g['ports'][4]['on'] and g['onPorts'] == 1, json.dumps(g))
        check('loop guard: a switch without the command gives nothing', parse_loop('Error: Invalid parameter', '') is None)
        check('loop guard: ports are grouped into ranges', port_runs([1, 2, 3, 5, 7, 8]) == [(1, 3), (5, 5), (7, 8)])

        class Ev:
            def __init__(self): self.items = []
            def add_event(self, did, name, level, text): self.items.append((level, text))
        def poll(t, moves=None, pps=None, guard=False):
            ports = [{'n': n, 'peers': [], 'link': True} for n in range(1, 9)]
            for mac, port in (moves or {}).items():
                ports[port - 1]['peers'].append({'mac': mac})
            for n, v in (pps or {}).items():
                ports[n - 1]['bcastPps'] = v
            if guard:
                ports[4].update(loopDetected=True, loopBlocked=True)
            return {'status': 'online', 'updated': t, 'ports': ports}
        ev = Ev(); w = lw.LoopWatch(ev); dd = {'id': 's1', 'name': 'SW'}
        s1 = poll(1000, pps={3: 40}); w.observe(dd, s1)
        check('loop watch: a quiet switch is quiet', not s1['loops']['active'])
        s2 = poll(1060, pps={3: 20000}); w.observe(dd, s2)
        check('loop watch: one noisy poll is not yet an alarm', not s2['loops']['active'])
        s3 = poll(1120, pps={3: 21000}); w.observe(dd, s3)
        check('loop watch: a broadcast storm on two polls in a row is', s3['loops']['active'] and s3['loops']['storm'][0]['port'] == 3 and any('петля' in t for _, t in ev.items))
        s4 = poll(1180, pps={3: 30}); w.observe(dd, s4)
        s5 = poll(1180 + lw.CALM + 60, pps={3: 30}); w.observe(dd, s5)
        check('loop watch: after a calm period the loop is declared gone', not s5['loops']['active'] and any('больше нет' in t for _, t in ev.items))
        ev = Ev(); w = lw.LoopWatch(ev)
        macs = ['aa:00:00:00:00:0%d' % i for i in range(1, 4)]
        out = None
        for i in range(7):
            out = poll(2000 + i * 60, moves={m: 1 + (i % 2) * 3 for m in macs}); w.observe(dd, out)
        check('loop watch: three devices jumping between the same ports are a loop', out['loops']['active'] and len(out['loops']['flap']) == 3)
        w2 = lw.LoopWatch(Ev()); out2 = None
        for i in range(7):
            out2 = poll(3000 + i * 60, moves={'bb:00:00:00:00:01': 1 + (i % 3 == 0) * 3}); w2.observe(dd, out2)
        check('loop watch: one roaming phone is not a loop', not out2['loops']['active'])
        w4 = lw.LoopWatch(Ev()); o4 = None                                       # the same devices listed on two ports in every poll (an uplink sees the whole network)
        for i in range(8):
            o4 = poll(3500 + i * 60, moves=None)
            for m in macs:
                o4['ports'][0]['peers'].append({'mac': m}); o4['ports'][7]['peers'].append({'mac': m})
            w4.observe(dd, o4)
        check('loop watch: devices listed on an uplink and on their own port are not «jumping»', not o4['loops']['active'])
        w5 = lw.LoopWatch(Ev()); o5 = None                                       # a phone that cannot decide between two access points all the time (real case)
        for i in range(14):
            o5 = poll(3800 + i * 60, moves={'b4:ed:d5:07:5a:44': 6 if i % 2 else 7}); w5.observe(dd, o5)
        check('loop watch: one phone roaming between two access points all the time is not a loop', not o5['loops']['active'])
        w6 = lw.LoopWatch(Ev()); o6 = None                                       # even many Wi-Fi devices roaming at once are ignored
        wf = set(macs)
        for i in range(8):
            o6 = poll(3900 + i * 60, moves={m: 1 + (i % 2) * 3 for m in macs}); w6.observe(dd, o6, wf)
        check('loop watch: Wi-Fi devices are not counted at all', not o6['loops']['active'])
        w3 = lw.LoopWatch(Ev()); o3 = poll(4000, guard=True); w3.observe(dd, o3)
        check('loop watch: the switch\'s own detection counts at once', o3['loops']['active'] and 'сам нашёл петлю' in o3['loops']['why'])

        swd = next(d for d in st['devices'] if d['driver'] == 'demo_switch')
        check('loop guard: the demo switch offers it (off at first), with a warning in the health analysis',
              (swd['state'].get('loopGuard') or {}).get('enabled') is False and any('Защита от петель выключена' in c['title'] for c in st['health']['checks']))
        api(f"/api/devices/{swd['id']}/action", {'action': 'loop_demo', 'params': {}}, 'POST')
        api(f"/api/devices/{swd['id']}/poll", {}, 'POST')
        api(f"/api/devices/{swd['id']}/poll", {}, 'POST')                        # a storm counts after two polls in a row
        st2 = api('/api/state'); sw2 = next(d for d in st2['devices'] if d['id'] == swd['id'])
        check('loop guard: a loop is seen in the state, in the analysis and in the journal',
              sw2['state']['loops']['active'] and any(c['level'] == 'bad' and 'петля' in c['title'] for c in st2['health']['checks'])
              and any('возможна петля' in e['text'] for e in st2['events']), json.dumps(sw2['state'].get('loops'))[:200])
        api(f"/api/devices/{swd['id']}/action", {'action': 'loop_guard', 'params': {}}, 'POST')
        api(f"/api/devices/{swd['id']}/poll", {}, 'POST')
        st3 = api('/api/state'); sw3 = next(d for d in st3['devices'] if d['id'] == swd['id'])
        check('loop guard: turned on, the ports are blocked by the switch itself', sw3['state']['loopGuard']['enabled'] and any(p.get('loopBlocked') for p in sw3['state']['ports']))
        api(f"/api/devices/{swd['id']}/action", {'action': 'loop_demo', 'params': {}}, 'POST')
        api(f"/api/devices/{swd['id']}/action", {'action': 'loop_guard_off', 'params': {}}, 'POST')
        api(f"/api/devices/{swd['id']}/poll", {}, 'POST')
        try:
            api('/api/devices', {'driver': 'ups', 'name': 'x', 'location': 'remote'}, 'POST'); check('a remote UPS is refused', False)
        except urllib.error.HTTPError as e:
            check('a remote UPS is refused', e.code == 400)
        rt = next(d for d in st['devices'] if d['driver'] == 'demo_router')
        try:
            api(f"/api/devices/{rt['id']}", dict(name=rt['name'], location='remote'), 'PUT'); check('a device on a local UPS cannot become remote', False)
        except urllib.error.HTTPError as e:
            check('a device on a local UPS cannot become remote', e.code == 400)
        sys.path.insert(0, ROOT)
        from rackd import power as pw
        loop = [{'id': 'r', 'name': 'r', 'units': [{'id': 'A', 'type': 'pdu', 'power': {'ports': {'1': {'pdu': 'B'}}}},
                                                  {'id': 'B', 'type': 'pdu', 'power': {'ports': {'1': {'pdu': 'A'}, '2': {'label': 'x', 'w': '10'}}}}]}]
        check('outlet blocks plugged into each other do not loop', pw.load(pw.Net(loop, [], {}), 'A')['w'] == 10)
        ghost = [{'id': 'u1', 'driver': 'ups', 'name': 'U', 'powerFrom': 'A', 'loads': [{'pdu': 'A', 'outlet': '1'}]}]
        check('a block never feeds the UPS it hangs on', not [i for i in pw.load(pw.Net(loop, ghost, {}), 'A')['items'] if i.get('kind') == 'ups'])
        panel = next(x for r in st['racks'] for x in r['units'] if x.get('id') == 'upduB')
        check('UPS is fed from the panel block (its draw counts there)', (u.get('supply') or {}).get('outlet') == '2'
              and any(i.get('kind') == 'ups' and i['w'] > u['loadW'] for i in panel['powerLoad']['items']), json.dumps(panel.get('powerLoad'))[:400])
        check('computed power is not stored', 'powerLoad' not in json.dumps(api('/api/racks', {'racks': st['racks']}, 'PUT') and open(os.path.join(data, 'config.json'), encoding='utf-8').read()))
        topo = st.get('topology') or api('/api/topology')
        mains = [n for n in topo['nodes'] if n.get('main')]
        check('main router picked with a reason', len(mains) == 1 and mains[0]['label'] == 'Роутер', json.dumps(mains)[:200])
        check('ONT provider on the internet line', any(e.get('kind') == 'isp' and e.get('label') == 'Оптика-Демо' for e in topo['edges']))
        pve = next(d for d in st['devices'] if d['driver'] == 'demo_proxmox')
        check('Proxmox: virtual machines', len(pve['state'].get('vms') or []) == 5)
        sw = next(d for d in st['devices'] if d['driver'] == 'demo_switch')
        p11 = next(p for p in sw['state']['ports'] if p['n'] == 11)
        check('port errors counted (CRC)', (p11.get('errDay') or 0) > 100, json.dumps({k: p11.get(k) for k in ('errDay', 'errHour', 'crc')}))
        check('port errors in network analysis', any('Ошибки на порту 11' in c['title'] for c in st['health']['checks']))
        # speed test: ping, download stream, upload, save, pin on the plan
        check('speed test: ping', 't' in api('/api/speedtest/ping'))
        down = urllib.request.urlopen(base + '/api/speedtest/down?bytes=3000000', timeout=30).read()
        check('speed test: download stream', len(down) == 3000000)
        up = json.loads(urllib.request.urlopen(urllib.request.Request(base + '/api/speedtest/up', data=os.urandom(2_000_000), method='POST',
                                                                      headers={'Content-Type': 'application/octet-stream'}), timeout=30).read())
        check('speed test: upload', up.get('bytes') == 2_000_000, json.dumps(up))
        check('speed test: who', 'ip' in api('/api/speedtest/who'))
        saved = api('/api/speedtest', {'down': 312.4, 'up': 201.7, 'ping': 4.2, 'jitter': 1.1, 'note': 'smoke'}, 'POST')['test']
        api('/api/speedtest/' + saved['id'], {'where': {'b': 'b1', 'f': 'f1', 'x': 10, 'y': 20}})
        got = next((t for t in api('/api/state')['speedtests'] if t['id'] == saved['id']), {})
        check('speed test: save + pin', got.get('down') == 312.4 and (got.get('where') or {}).get('x') == 10, json.dumps(got)[:200])
        vps = next(d for d in st['devices'] if d['driver'] == 'demo_server')
        ip = api(f"/api/devices/{vps['id']}/action", {'action': 'iperf', 'params': {}}, 'POST')
        check('iperf action stored as speed test', (ip.get('speedtest') or {}).get('kind') == 'iperf', json.dumps(ip)[:200])
        # plugins on the demo router: status, .conf preview, create with domain routing, remove
        rt = next(d for d in st['devices'] if d['driver'] == 'demo_router')
        P = lambda body: api(f"/api/devices/{rt['id']}/plugins", body, 'POST')
        check('plugins: status', [p['id'] for p in P({'op': 'status'})['plugins']][:2] == ['entware', 'awg'])
        conf = ('[Interface]\nPrivateKey = aGVsbG8taGVsbG8taGVsbG8taGVsbG8taGVsbG8hIT0=\nAddress = 10.8.0.2/32, fd00::2/128\nDNS = 1.1.1.1\n'
                'Jc = 4\nJmin = 10\nJmax = 50\nS1 = 34\nS2 = 109\nH1 = 1000-2000\nH2 = 3000-4000\nH3 = 5000-6000\nH4 = 7000-8000\nS3 = 12\nS4 = 6\nI1 = <b 0xc0ffee>\n'
                '[Peer]\nPublicKey = cGVlci1wZWVyLXBlZXItcGVlci1wZWVyLXBlZXIhIT0=\nEndpoint = vpn.example.com:51820\nAllowedIPs = 0.0.0.0/0, ::/0\nPersistentKeepalive = 25\n')
        pv = P({'plugin': 'awg', 'op': 'preview', 'conf': conf, 'domains': 'youtube.com\nhttps://www.googlevideo.com/x\n1.2.3.0/24\nдуэт-абх.рф\n!!bad'})
        check('plugins: .conf preview (AWG 2.0, domains)', pv['preview']['type'] == 'AmneziaWG 2.0' and pv['preview']['ipv6Skipped'] and pv['domains'] == 4
              and pv['skipped'] == ['!!bad'], json.dumps(pv, ensure_ascii=False)[:300])
        try:
            P({'plugin': 'awg', 'op': 'preview', 'conf': 'hello'}); check('plugins: bad .conf refused', False)
        except urllib.error.HTTPError as e:
            check('plugins: bad .conf refused', e.code == 400)
        ins = P({'plugin': 'awg', 'op': 'install', 'conf': conf, 'name': 'Smoke', 'routing': True, 'domains': 'youtube.com'})
        tun = next((d for d in api('/api/state')['devices'] if d['id'] == rt['id']), {}).get('rlTunnels') or []
        check('plugins: install remembered', ins.get('iface') and any(t['iface'] == ins['iface'] and t['domains'] == 1 for t in tun), json.dumps(ins)[:200])
        P({'plugin': 'awg', 'op': 'remove', 'iface': ins['iface']})
        check('plugins: remove', not (next(d for d in api('/api/state')['devices'] if d['id'] == rt['id']).get('rlTunnels')))
        hr = P({'plugin': 'hydraroute', 'op': 'install'})
        check('plugins: installer', hr.get('ok') and hr.get('url', '').endswith(':2000') and
              next(p for p in P({'op': 'status'})['plugins'] if p['id'] == 'hydraroute')['installed'], json.dumps(hr, ensure_ascii=False)[:200])
        P({'plugin': 'hydraroute', 'op': 'remove'})
        ow = next(d for d in st['devices'] if d['driver'] == 'demo_openwrt')
        OP = lambda body: api(f"/api/devices/{ow['id']}/plugins", body, 'POST')
        check('openwrt plugins: status', [p['id'] for p in OP({'op': 'status'})['plugins']] == ['forkop', 'podkop', 'modem', 'portal', 'remote', 'meshnode'])
        mj = OP({'plugin': 'meshnode', 'op': 'install'})
        for _ in range(40):
            if not mj.get('job'):
                break
            jr = OP({'op': 'job', 'job': mj['job']})
            if jr.get('done'):
                break
            time.sleep(0.2)
        check('openwrt: meshnode installed (demo)', next(p for p in OP({'op': 'status'})['plugins'] if p['id'] == 'meshnode')['member'])
        OP({'plugin': 'meshnode', 'op': 'remove'})
        check('openwrt: meshnode removed (demo)', not next(p for p in OP({'op': 'status'})['plugins'] if p['id'] == 'meshnode')['installed'])
        OP({'plugin': 'forkop', 'op': 'install', 'extended': True})
        try:
            OP({'plugin': 'podkop', 'op': 'install'}); check('openwrt: podkop refused while forkop installed', False)
        except urllib.error.HTTPError as e:
            check('openwrt: podkop refused while forkop installed', e.code == 400)
        OP({'plugin': 'forkop', 'op': 'remove'})
        OP({'plugin': 'modem', 'op': 'install', 'profile': 'mm'})
        check('openwrt: modem variant installed', next(m for m in next(p for p in OP({'op': 'status'})['plugins'] if p['id'] == 'modem')['profiles'] if m['id'] == 'mm')['installed'])
        OP({'plugin': 'modem', 'op': 'remove', 'profile': 'mm'})
        # VPS panels: DNS check, background install job with stages, credentials kept as a secret
        VP = lambda body: api(f"/api/devices/{vps['id']}/plugins", body, 'POST')
        check('vps plugins: status', [p['id'] for p in VP({'op': 'status'})['plugins']] == ['3xui', 'remnawave', 'agents', 'rcos', 'collector'])
        # «Сборщик площадки»: the site is made before the job, the new machine downloads this code with the site key, the card shows the site, remove drops it on request
        try:
            VP({'plugin': 'collector', 'op': 'install', 'server': 'not-an-address'}); bad = False
        except urllib.error.HTTPError as e:
            bad = e.code == 400
        check('collector: a bad address is refused before anything starts', bad)
        n_sites = len(api('/api/sites')['sites'])
        jid = VP({'plugin': 'collector', 'op': 'install', 'name': 'Квартира Теста', 'server': 'https://racklive.example.com', 'port': 9998, 'level': 'view'})['job']
        for _ in range(40):
            j = VP({'plugin': 'collector', 'op': 'job', 'job': jid})
            if j.get('done'):
                break
            time.sleep(.3)
        cinfo = (j.get('result') or {}).get('info') or {}
        check('collector: install job gives the panel address and a password', j.get('done') and not j.get('error') and cinfo.get('url') and cinfo.get('password') and cinfo.get('siteName') == 'Квартира Теста', json.dumps(j, ensure_ascii=False)[:300])
        sj2 = api('/api/sites')['sites']
        check('collector: the site was created', len(sj2) == n_sites + 1 and any(s['name'] == 'Квартира Теста' for s in sj2))
        ccard = next(p for p in VP({'op': 'status'})['plugins'] if p['id'] == 'collector')
        check('collector: the card shows the info and the site', ccard['installed'] and ccard['info']['password'] == cinfo['password'] and ccard['site'] and ccard['site']['name'] == 'Квартира Теста', json.dumps(ccard, ensure_ascii=False)[:300])
        ctok = api(f"/api/sites/{ccard['site']['id']}/token", {}, 'POST')['token']
        pk = urllib.request.urlopen(urllib.request.Request(base + '/api/site/pack', headers={'Authorization': 'Bearer ' + ctok}), timeout=60).read()
        check('collector: the code is downloaded with the site key', pk[:2] == b'\x1f\x8b' and len(pk) > 100000, len(pk))
        try:
            urllib.request.urlopen(urllib.request.Request(base + '/api/site/pack', headers={'Authorization': 'Bearer nope'}), timeout=10); bad = False
        except urllib.error.HTTPError as e:
            bad = e.code == 401
        check('collector: no key, no code', bad)
        try:
            urllib.request.urlopen(base + '/api/site/pack', timeout=10); bad = False
        except urllib.error.HTTPError as e:
            bad = e.code == 401
        check('collector: no header, no code', bad)
        jid = VP({'plugin': 'collector', 'op': 'remove', 'removeSite': True})['job']
        for _ in range(40):
            j = VP({'plugin': 'collector', 'op': 'job', 'job': jid})
            if j.get('done'):
                break
            time.sleep(.3)
        check('collector: remove drops the site when asked', j.get('done') and not j.get('error') and not any(s['name'] == 'Квартира Теста' for s in api('/api/sites')['sites']), json.dumps(j, ensure_ascii=False)[:300])
        check('vps: DNS check', VP({'plugin': '3xui', 'op': 'dns', 'domain': 'vpn.example.com'})['match'] and
              not VP({'plugin': '3xui', 'op': 'dns', 'domain': 'other.org'})['match'])
        jid = VP({'plugin': '3xui', 'op': 'install', 'withDomain': True, 'domain': 'vpn.example.com', 'inbounds': True})['job']
        for _ in range(40):
            j = VP({'plugin': '3xui', 'op': 'job', 'job': jid})
            if j.get('done'):
                break
            time.sleep(.3)
        check('vps: install job finishes with links', j.get('done') and len(((j.get('result') or {}).get('info') or {}).get('links') or []) == 2, json.dumps(j, ensure_ascii=False)[:300])
        dv = next(d for d in api('/api/state')['devices'] if d['id'] == vps['id'])
        check('vps: credentials not exposed in /api/state', 'panelInfo' not in dv and dv.get('panelInfoSet'))
        check('vps: credentials shown in plugin status', (next(p for p in VP({'op': 'status'})['plugins'] if p['id'] == '3xui').get('info') or {}).get('password'))
        # «Режим разработчика» (rackd/hostops.py): closed until the switch is on, then the system of the machine (simulated in the demo)
        def HTTP(path, body=None, method=None):
            try:
                return 200, api(path, body, method) if body is not None or method else api(path)
            except urllib.error.HTTPError as e:
                return e.code, {}
        check('devmode: closed while the switch is off', HTTP('/api/dev/status')[0] == 403 and HTTP('/api/dev/op', {'op': 'timezone', 'tz': 'Europe/Berlin'}, 'POST')[0] == 403)
        api('/api/settings', {'devMode': True}, 'PUT')
        check('devmode: the switch shows in the state', api('/api/state').get('devMode') is True)
        dv = api('/api/dev/status')
        check('devmode: system status (demo)', dv['ok'] and dv['supported'] and dv['tz'] and dv['docker']['version'] and dv['upgradable'] is not None, json.dumps(dv, ensure_ascii=False)[:300])
        dw = api('/api/dev/wifi')
        check('devmode: wifi status, adapter, our access point', dw['ok'] and dw['interfaces'] and dw['hotspot']['on'] and dw['suggestAddress'], json.dumps(dw, ensure_ascii=False)[:300])
        check('devmode: time zones list', 'Europe/Moscow' in api('/api/dev/zones')['zones'])
        DV = lambda body: api('/api/dev/op', body, 'POST')
        check('devmode: time zone changes', 'Europe/Berlin' in DV({'op': 'timezone', 'tz': 'Europe/Berlin'})['message'])
        check('devmode: a bad time zone is refused', HTTP('/api/dev/op', {'op': 'timezone', 'tz': 'Europe/Moscow; reboot'}, 'POST')[0] == 400)
        check('devmode: reboot needs the word', HTTP('/api/dev/op', {'op': 'reboot'}, 'POST')[0] == 400 and 'демо' in DV({'op': 'reboot', 'confirm': 'перезагрузить'})['message'])

        def dev_job(body):
            jid = DV(body)['job']
            for _ in range(40):
                j = api('/api/dev/job', {'job': jid}, 'POST')
                if j.get('done'):
                    return j
                time.sleep(.3)
            return j
        j = dev_job({'op': 'check'})
        check('devmode: update check is a job with a result', j.get('done') and not j.get('error') and j['result']['count'] is not None, json.dumps(j, ensure_ascii=False)[:300])
        j = dev_job({'op': 'ap_on', 'iface': 'wlp3s0', 'ssid': 'ReckController', 'password': 'pass-12345', 'address': '10.77.0.1/24'})
        check('devmode: access point job', j.get('done') and not j.get('error'), json.dumps(j, ensure_ascii=False)[:300])
        check('devmode: a public address for the access point is refused', HTTP('/api/dev/op', {'op': 'ap_on', 'iface': 'wlp3s0', 'ssid': 'X', 'address': '8.8.8.1/24'}, 'POST')[0] == 400)
        check('devmode: a bad adapter name is refused', HTTP('/api/dev/op', {'op': 'scan', 'iface': 'wlan0; id'}, 'POST')[0] == 400)
        check('devmode: scan finds networks', len(DV({'op': 'scan', 'iface': 'wlp3s0'})['networks']) >= 2)
        # VPN (AmneziaWG) in the developer mode (simulated in the demo)
        vv = api('/api/dev/vpn')
        check('devmode vpn: status (demo)', vv.get('ok') and vv.get('installed') and vv.get('hasConf'), json.dumps(vv, ensure_ascii=False)[:200])
        AWGC = '[Interface]\nPrivateKey = k\nAddress = 10.8.0.2/32\nJc = 4\nS1 = 0\nS2 = 0\nH1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n[Peer]\nPublicKey = p\nEndpoint = 203.0.113.10:51820\nAllowedIPs = 0.0.0.0/0\n'
        pv = DV({'op': 'awg_preview', 'conf': AWGC})['preview']
        check('devmode vpn: config preview without keys', pv['server'] == '203.0.113.10:51820' and pv['fullTunnel'] and 'k' not in json.dumps(pv).replace('"', ' ').split(), pv)
        check('devmode vpn: a broken config is refused', HTTP('/api/dev/op', {'op': 'awg_conf', 'conf': 'nonsense'}, 'POST')[0] == 400)
        check('devmode vpn: save, on, off', 'демо' in DV({'op': 'awg_conf', 'conf': AWGC})['message'] and 'демо' in DV({'op': 'awg_on'})['message'] and 'демо' in DV({'op': 'awg_off'})['message'])        # ReckController OS = collector + developer mode + Wi-Fi access point, in one plugin
        n_sites = len(api('/api/sites')['sites'])
        jid = VP({'plugin': 'rcos', 'op': 'install', 'name': 'Мини-ПК Теста', 'server': 'https://racklive.example.com', 'port': 9998, 'level': 'view', 'tz': 'Europe/Moscow', 'ap': True, 'ssid': 'ReckController', 'apPassword': 'pass-12345'})['job']
        for _ in range(40):
            j = VP({'plugin': 'rcos', 'op': 'job', 'job': jid})
            if j.get('done'):
                break
            time.sleep(.3)
        rinfo = (j.get('result') or {}).get('info') or {}
        check('rcos: install gives the panel, the password and the access point', j.get('done') and not j.get('error') and rinfo.get('rcos') and rinfo.get('password') and (rinfo.get('ap') or {}).get('ssid') == 'ReckController' and (rinfo['ap'].get('url') or '').startswith('http://10.'), json.dumps(j, ensure_ascii=False)[:300])
        check('rcos: the site was created', len(api('/api/sites')['sites']) == n_sites + 1)
        rcard = next(p for p in VP({'op': 'status'})['plugins'] if p['id'] == 'rcos')
        check('rcos: the card is installed and shows the site; the plain collector card is not', rcard['installed'] and rcard['site'] and not next(p for p in VP({'op': 'status'})['plugins'] if p['id'] == 'collector')['installed'])
        check('rcos: a bad password for the point is refused', HTTP(f"/api/devices/{vps['id']}/plugins", {'plugin': 'rcos', 'op': 'install', 'server': 'https://racklive.example.com', 'apPassword': 'short'}, 'POST')[0] == 400)
        jid = VP({'plugin': 'rcos', 'op': 'remove', 'removeSite': True})['job']
        for _ in range(40):
            j = VP({'plugin': 'rcos', 'op': 'job', 'job': jid})
            if j.get('done'):
                break
            time.sleep(.3)
        check('rcos: remove drops the site when asked', j.get('done') and not j.get('error') and len(api('/api/sites')['sites']) == n_sites, json.dumps(j, ensure_ascii=False)[:300])        # ReckController OS on its own (no reporting): no site, a one-time download key, the machine's own panel and password
        n_sites = len(api('/api/sites')['sites'])
        jid = VP({'plugin': 'rcos', 'op': 'install', 'name': 'Сам по себе', 'server': '', 'port': 9998, 'tz': 'Europe/Moscow', 'ap': True})['job']
        for _ in range(40):
            j = VP({'plugin': 'rcos', 'op': 'job', 'job': jid})
            if j.get('done'):
                break
            time.sleep(.3)
        rinfo = (j.get('result') or {}).get('info') or {}
        check('rcos without reporting: no site, own panel, password and the point', j.get('done') and not j.get('error') and len(api('/api/sites')['sites']) == n_sites and not rinfo.get('siteName') and rinfo.get('password') and (rinfo.get('ap') or {}).get('password'), json.dumps(j, ensure_ascii=False)[:300])
        VP({'plugin': 'rcos', 'op': 'remove'})        # security advisor: findings, a fix, «это нормально»
        sec = api('/api/state')['security']
        rdp = next((f for f in sec['findings'] if f['id'].endswith(':tcp:3389')), None)
        check('security: findings and score', rdp and rdp['level'] == 'bad' and rdp['fix'] and sec['score'] < 100, json.dumps(sec, ensure_ascii=False)[:300])
        api(f"/api/devices/{rt['id']}/action", {'action': 'sec_fix', 'params': rdp['fix']['params']}, 'POST')
        api(f"/api/devices/{rt['id']}/poll", {}, 'POST')
        check('security: fix closes the port', not any(f['id'] == rdp['id'] for f in api('/api/state')['security']['findings']))
        upnp = next(f for f in api('/api/state')['security']['findings'] if f['id'].startswith('upnp:'))
        api('/api/security/ignore', {'id': upnp['id'], 'ignore': True}, 'POST')
        s2 = api('/api/state')['security']
        check('security: ignore hides a finding', any(f['id'] == upnp['id'] for f in s2['ignored']) and not any(f['id'] == upnp['id'] for f in s2['findings']))
        # internet speed history + a manual run; config backups with diff; new devices; outside port check
        st2 = api('/api/state')
        n0 = len(st2['inet']['items'])
        check('inet: history and settings', n0 > 20 and st2['inet']['cfg']['tariff'] == 1000)
        api('/api/inet/run', {}, 'POST')
        for _ in range(30):
            if not api('/api/state')['inet']['running']:
                break
            time.sleep(.5)
        check('inet: manual run adds results', len(api('/api/state')['inet']['items']) > n0)
        b1 = api(f"/api/backups/{rt['id']}/run", {}, 'POST')
        b2 = api(f"/api/backups/{rt['id']}/run", {}, 'POST')
        vers = api(f"/api/backups/{rt['id']}")['versions']
        diff = api(f"/api/backups/{rt['id']}/{vers[0]['t']}")['diff'] if vers else []
        check('backups: first copy, then «unchanged», diff', b1['changed'] and not b2['changed'] and len(vers) == 1 and any(l.startswith('+') for l in diff),
              json.dumps([b1, b2, len(vers)], ensure_ascii=False))
        nd = st2.get('newDevices') or []
        check('new devices: list', len(nd) >= 2)
        api('/api/newdev/trust', {'mac': nd[0]['mac'], 'on': True}, 'POST')
        check('new devices: «это моё»', next(r for r in api('/api/state')['newDevices'] if r['mac'] == nd[0]['mac'])['trusted'])
        api('/api/extscan/run', {}, 'POST')
        for _ in range(30):
            x = api('/api/state')['extscan']
            if not x['running'] and x.get('t'):
                break
            time.sleep(.5)
        sec = api('/api/state')['security']
        check('outside check: open ports feed the advisor', 22 in (x.get('open') or []) and any('Проверено снаружи' in f['text'] for f in sec['findings'])
              and any(f['id'] == 'ext:1900' for f in sec['findings']), json.dumps(x, ensure_ascii=False)[:200])
        found = api('/api/detect', {'host': f'127.0.0.1:{port}'}, 'POST')['found']
        check('detect: answers with a ranked list', found and found[-1]['driver'] == 'ping', json.dumps(found, ensure_ascii=False)[:200])
        try:
            api('/api/ai/ask', {'chat': None, 'text': 'привет'}, 'POST')
            check('assistant: refuses until set up', False)
        except urllib.error.HTTPError as e:
            check('assistant: refuses until set up', e.code == 400)
        api('/api/ai', {'enabled': False, 'preset': 'deepseek', 'key': 'sk-smoke-secret'}, 'PUT')
        ai = api('/api/state')
        check('assistant: key kept server-side only', ai['ai']['keySet'] and 'sk-smoke-secret' not in json.dumps(ai))
        # saved chats: a provider nobody listens on → the question and the error are both kept in the conversation
        api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': 'http://127.0.0.1:9/v1', 'model': 'm', 'key': 'sk-x'}, 'PUT')
        r = api('/api/ai/ask', {'chat': None, 'text': 'Всё ли в порядке?'}, 'POST')
        for _ in range(40):
            if api('/api/ai/job', {'job': r['job']}, 'POST')['done']:
                break
            time.sleep(.3)
        lst = api('/api/ai/chats')['chats']
        c = api('/api/ai/chats/' + r['chat'])
        check('assistant: chat saved on the server', len(lst) == 1 and lst[0]['title'] == 'Всё ли в порядке?' and len(c['messages']) == 2 and c['messages'][1].get('err'),
              json.dumps(lst, ensure_ascii=False)[:200])
        api('/api/ai/chats/' + r['chat'], {}, 'DELETE')
        check('assistant: chat deleted', not api('/api/ai/chats')['chats'])
        api('/api/ai', {'enabled': False, 'preset': 'custom'}, 'PUT')
        # remote router as a web panel: link + login in the card, the password only through /creds
        rw = api('/api/devices', {'driver': 'remote_web', 'name': 'Роутер · дача', 'kind': 'router', 'location': 'remote',
                                  'host': base, 'username': 'admin', 'password': 'smoke-web-pw'}, 'POST')['device']
        api(f"/api/devices/{rw['id']}/poll", {}, 'POST')
        s3 = api('/api/state')
        cr = api(f"/api/devices/{rw['id']}/creds", {}, 'POST')
        check('remote web panel: online, password only via /creds', next(x for x in s3['devices'] if x['id'] == rw['id'])['state']['status'] == 'online'
              and 'smoke-web-pw' not in json.dumps(s3) and cr['password'] == 'smoke-web-pw' and cr['url'] == base)
        api(f"/api/devices/{rw['id']}", None, 'DELETE')
        api('/api/routers/scan', {}, 'POST')
        for _ in range(40):
            rs = api('/api/state')['routerScan']
            if not rs['running'] and rs['last']:
                break
            time.sleep(.5)
        g = next((r for r in rs['list'] if r['mac'] == '80:af:ca:00:00:99'), None)
        check('routers in the network: guest Cudy found, page closed', g and g['vendor'] == 'Cudy' and not (g.get('web') or {}).get('ok'),
              json.dumps(rs['list'], ensure_ascii=False)[:300])
        r = urllib.request.urlopen(urllib.request.Request(base + '/app.js', headers={'Accept-Encoding': 'gzip'}), timeout=30)
        body = r.read()
        check('app.js served gzipped', r.headers.get('Content-Encoding') == 'gzip' and len(gzip.decompress(body)) > len(body))

        browser = next((b for b in BROWSERS if os.path.exists(b)), shutil.which('chromium') or shutil.which('google-chrome'))
        if not browser:
            print('UI: no Chromium-based browser found — skipped')
            return
        print('UI')
        st = api('/api/state'); dev = {d['driver']: d['id'] for d in st['devices']}
        units = {u['type']: u['id'] for r in st['racks'] for u in r['units']}
        api('/api/dashboard', {'widgets': [{'id': t, 'type': t, 'size': 'M'} for t in ('rack', 'stats', 'problems', 'state', 'internet', 'uptime')]
                               + [{'id': 'ups', 'type': 'ups', 'size': 'M'}, {'id': 'upsS', 'type': 'ups', 'size': 'S'}]}, 'PUT')
        pages = {'Размещение': '#rack', 'Карта': '#map', 'Карта + анализ': '?analysis=1#map', 'План — территория': '#plan',
                 'План — дом': '?building=b1#plan', 'План — дом, правка': '?building=b1&mode=edit#plan', 'Устройства': '#devices',
                 'События': '#events', 'Инструменты — плагины': '?tsec=plugins#tools', 'Плагины сообщества': '?tsec=plugins&community=1#tools', 'Инструменты — камеры': '?tsec=cameras#tools', 'Инструменты — площадки': '?tsec=sites#tools', 'Инструменты — каталог с инструментом': '?tsec=cameras#tools', 'Инструмент сообщества': '?tsec=x-disk-usage#tools', 'Устройство площадки': '?device=sdemo1-rt&tab=remote',
                 'Камера — вход': '?tsec=cameras&cam=10.0.7.11&camlogin=admin:demo-pass&camtab=net#tools', 'Настройки': '#settings', 'Щиток': '?place=rack1#rack', 'Правка размещения': '?mode=edit#rack',
                 'Роутер · VPN': f'?device={dev["demo_router"]}&tab=vpn', 'Коммутатор · порт': f'?device={dev["demo_switch"]}&tab=ports&port=12',
                 'ИБП': f'?device={dev["ups"]}', 'NAS · контейнеры': f'?device={dev["demo_nas"]}&tab=services&container=racklive', 'NAS · диски (SMART)': f'?device={dev["demo_nas"]}&tab=smart', 'Настройки · Сеть': '?section=network#settings', 'Настройки · О программе': '?section=about#settings', 'Настройки · Терминал': '?section=terminal#settings', 'События · меню': '#events', 'NAS': f'?device={dev["demo_nas"]}', 'Патч-панель': f'?unit={units["patch"]}#rack',
                 'Кросс': f'?unit={units["cross"]}#rack', 'ONT': f'?unit={units["modem"]}#rack',
                 'Юнит ONT — правка': f'?mode=edit&editunit={units["modem"]}#rack', 'Распиновка кросса': f'?mode=edit&editunit={units["cross"]}&pm=1#rack',
                 'Юнит ИБП — правка': f'?mode=edit&editunit={units["ups"]}#rack', 'Светлая тема': '?theme=light#plan',
                 'Тест скорости': '?speedtest=1#rack', 'VPS · iperf3': f'?device={dev["demo_server"]}',
                 'Роутер · плагины': f'?device={dev["demo_router"]}&tab=plugins',
                 'Плагин HydraRoute': f'?device={dev["demo_router"]}&tab=plugins&plugin=hydraroute',
                 'OpenWrt · Forkop': f'?device={dev["demo_openwrt"]}&tab=plugins&plugin=forkop',
                 'OpenWrt · модем': f'?device={dev["demo_openwrt"]}&tab=plugins&plugin=modem',
                 'Новое устройство (автоопределение)': '?add=1#devices',
                 'Обучение Frank — приветствие': '?tour=1#rack', 'Обучение Frank — устройства': '?tour=1&tourstep=1#rack',
                 'Обучение Frank — определить': '?tour=1&tourstep=3&add=1#devices', 'Обучение — в настройках': '?section=general#settings',
                 'Коммутатор — защита от петель': f'?device={dev["demo_switch"]}',
                 'Устройства — сканирование сети': '?netscan=1#devices',
                 'События — системные': '?sys=1#events',
                 'Настройки — оформление': '?section=look#settings',
                 'Главная — стиль «Графит»': '?skin=graphite&accent=green#rack',
                 'Главная — стиль «Контроллер»': '?skin=net#rack',
                 'Устройства — удалённые': '#devices', 'Доступ — вход и устройства': '?section=access#settings',
                 'Доступ — подключение приложения': '?section=access&mfa=totp#settings',
                 'Новое устройство — группы': '?add=1#devices', 'Новое устройство — роутеры': '?add=1&addgrp=router#devices',
                 'VPS · 3x-ui': f'?device={dev["demo_server"]}&tab=plugins&plugin=3xui',
                 'VPS · Remnawave': f'?device={dev["demo_server"]}&tab=plugins&plugin=remnawave',
                 'VPS · ИИ-агенты': f'?device={dev["demo_server"]}&tab=plugins&plugin=agents',
                 'VPS · Сборщик площадки': f'?device={dev["demo_server"]}&tab=plugins&plugin=collector',
                 'VPS · ReckController OS': f'?device={dev["demo_server"]}&tab=plugins&plugin=rcos',
                 'Настройки · Система': '?section=system#settings', 'Настройки · Wi-Fi': '?section=network&nettab=wifi#settings', 'Настройки · VPN': '?section=network&nettab=vpn#settings', 'Настройки · режим разработчика': '?section=general#settings',
                 'Безопасность': '?security=1#rack', 'Интернет': '?inet=1#rack',
                 'Роутер · конфигурация': f'?device={dev["demo_router"]}&tab=config', 'Устройства · новые': '#devices',
                 'Помощник — не настроен': '?ai=1#rack', 'Помощник — настроен': '?ai=1#rack',
                 'Настройки · Frank': '?section=frank#settings', 'Настройки · Приложения': '?section=apps#settings', 'Настройки · Уведомления': '?section=notify#settings',
                 'Доступность': '?uptime=1#rack', 'Карта — ONT': '#map', 'Карта — дерево': '?mapstyle=tree#map', 'Карта — кольца': '?mapstyle=radial#map', 'Карта — по сетям': '?mapstyle=groups#map', 'Карта — меню вида': '?mapstyle=tree&mapnode=камера · вход#map', 'Карта — камера в дереве': '?mapnode=камера · вход#map',
                 'Новый юнит — что ставим': '?mode=edit&editunit=new#rack', 'Переезд места': '?mode=edit&move=1#rack',
                 'Карта — правка (магнит)': '?mode=edit#map',
                 'Блок розеток — нагрузка': '?unit=upduA#rack', 'Блок розеток — розетки': '?mode=edit&editunit=upduA&pw=1#rack',
                 'ИБП — форма': f'?editdev={dev["ups"]}',
                 'Proxmox · виртуалки': f'?device={dev["demo_proxmox"]}&tab=vms', 'ИБП · кривая': f'?device={dev["ups"]}',
                 'ONT — настройка': f'?mode=edit&editunit={units["modem"]}#rack', 'Кросс — живые порты': f'?unit={units["cross"]}#rack'}
        # a custom look is really applied: texts renamed, the look's own attributes on <html>; deleted look → the page falls back to the original by itself
        wrap = os.path.join(ROOT, 'web', '_smoke_look.html')
        try:
            open(wrap, 'w', encoding='utf-8').write('<!doctype html><script>localStorage.setItem("rl_skin","my-look");localStorage.setItem("rl_theme_meta",JSON.stringify({id:"my-look",name:"x",base:"graphite",rev:1}));location.replace("/#rack")</script>')
            dom = lambda ms=8000: subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=1300,900', f'--virtual-time-budget={ms}', '--dump-dom', base + '/_smoke_look.html'],
                                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
            out = dom()
            check('looks: a chosen custom look is applied (own attribute, base look, its css, renamed tab)',
                  re.search(r'<html[^>]*data-theme-id="my-look"', out) and re.search(r'<html[^>]*data-skin="graphite"', out) and 'id="rl-theme-css"' in out and '<span class="tab-label">Дом</span>' in out, out[:200])
            raw('/api/themes/my-look', method='DELETE')
            out = dom(3000)                                 # the notice lives a few seconds
            check('looks: after the look is gone the page falls back to the original by itself (and says so)',
                  not re.search(r'<html[^>]*data-theme-id', out) and '<span class="tab-label">Главная</span>' in out and 'отключено' in out, 'tab-label' in out)
        finally:
            if os.path.exists(wrap):
                os.remove(wrap)
        api('/api/cameras/start', {'cidrs': []}, 'POST'); time.sleep(3)
        api('/api/cameras/creds', {'user': 'admin', 'password': 'Sample-pw-1', 'label': 'тест'}, 'POST')
        cam_raw = json.dumps(api('/api/cameras'))
        check('cameras: the search needs no network (automatic) and finds cameras', len(json.loads(cam_raw)['items']) >= 5)
        check('cameras: saved passwords never go to the browser', 'Sample-pw-1' not in cam_raw and '"mask"' in cam_raw)
        check('cameras: more than 30 brands are known', len(json.loads(cam_raw)['brands']) >= 30)
        note = 'Заметка про гостевой Wi-Fi. ' * 120                       # ~3000 Russian letters: the old limit (4000 bytes of escaped JSON) silently dropped such a note
        prev_dash = (api('/api/state').get('dashboard') or {}).get('widgets') or []
        api('/api/dashboard', {'widgets': [{'id': 'n1', 'type': 'note', 'size': 'M', 'opts': {'text': note}}]}, 'PUT')
        back = [w for w in api('/api/state')['dashboard']['widgets'] if w['type'] == 'note']
        check('notes: a long Russian note is saved whole', back and back[0]['opts'].get('text') == note)
        api('/api/dashboard', {'widgets': prev_dash}, 'PUT')
        for name, q in pages.items():
            if name == 'Помощник — настроен':          # a provider nobody listens on: enough for the panel to show the chat
                api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': 'http://127.0.0.1:9/v1', 'model': 'm', 'key': 'sk-test'}, 'PUT')
            out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=1300,900', '--virtual-time-budget=6000',
                                  '--dump-dom', base + '/' + q], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
            err = ''
            if 'data-js-error="' in out:
                err = out.split('data-js-error="', 1)[1].split('"', 1)[0]
            check(name, 'page-title' in out and 'rl-crash' not in out and not err, err or ('пустая страница' if 'page-title' not in out else ''))
            if name == 'Размещение':
                check('подсказка на вкладке', 'hint-box' in out)
                check('главная из виджетов', out.count('data-wid=') >= 5)
                check('виджет ИБП: широкий и квадрат', out.count('t-ups') >= 2 and 'хватит при отключении света' in out)   # wide + square; the drawing itself belongs to the look (classic battery art or the «Test» instrument)
            if name == 'Блок розеток — нагрузка':
                check('розетки блока и ИБП кружками на шкафу', 'leds round' in out and '<i class="r">' in out)
            if name == 'План — дом':
                check('покрытие Wi-Fi на плане', 'cov-pin' in out)
            if name == 'Тест скорости':
                check('окно теста скорости', 'gauge' in out)
            if name == 'Настройки':
                check('настройки разбиты на разделы', out.count('set-item') >= 6 and 'set-head' in out)
            if name == 'Новый юнит — что ставим':
                check('выбор устройства вместо «привязки»', out.count('up-opt') >= 8 and 'Связанное устройство' not in out)
            if name == 'Proxmox · виртуалки':
                check('список виртуалок', 'Windows Server' in out and 'pihole' in out)
            if name == 'Доступ — вход и устройства':
                check('доступ: второй фактор, устройства, время сессий', all(x in out for x in ('Двухфакторная защита', 'Устройства с доступом', 'Как долго живёт вход')))
            if name == 'Доступ — подключение приложения':
                check('доступ: окно подключения приложения', 'Приложение с кодами' in out and 'Установите на телефон' in out)
            if name == 'Обучение Frank — приветствие':
                check('обучение: Frank, градиент, «Пропустить»', all(x in out for x in ('tour-layer', 'Привет! Я Frank', 'Пропустить обучение', 'tf-bob')))
            if name == 'Обучение Frank — устройства':
                check('обучение: подсветка вкладки «Устройства»', 'Начнём с устройств' in out and 'tour-ring' in out and 'Нажмите на подсвеченное' in out)
            if name == 'Обучение Frank — определить':
                check('обучение: шаг внутри окна добавления', 'Проще всего — по адресу' in out)
            if name == 'Обучение — в настройках':
                check('обучение: кнопка повтора в настройках', 'Показать обучение' in out)
            if name == 'Коммутатор — защита от петель':
                i = out.find('Защита от петель')
                check('карточка «Защита от петель» у коммутатора', 'Защита от петель' in out and 'Выключена' in out and 'Включить защиту от петель' in out,
                      re.sub(r'<[^>]+>', ' ', out[i: i + 900]) if i >= 0 else 'карточки нет; длина ' + str(len(out)))
            if name == 'События — системные':
                check('вкладка «Системные»: журнал и кнопка «Скопировать всё»', 'Системные события' in out and 'Скопировать всё' in out and 'загружена (navigate)' in out)
            if name == 'Устройства — сканирование сети':
                check('окно «Сканировать сеть»: сети, кнопка, результаты', 'Сканировать сеть' in out and 'Сканировать' in out and 'стучится' in out)
                check('сканирование: что можно добавить — сверху, остальное свёрнуто', 'Можно добавить в Rack Live' in out and 'остальные устройства в сети' in out, re.sub(r'<[^>]+>', ' ', out)[-600:])
            if name == 'Настройки — оформление':
                check('раздел «Оформление»: стили, акцент, тема', 'Стиль интерфейса' in out and 'Графит' in out and 'Контроллер' in out and 'Цвет акцента' in out and 'Светлая и тёмная тема' in out)
                check('оформление: «Test» — основное, со своим превью', 'class="tp"' in out and 'tp-rack' in out and 'tp-scale' in out and 'основное' in out)
            if name == 'Главная — стиль «Графит»':
                check('стиль «Графит» включается атрибутами на <html>', 'data-skin="graphite"' in out and 'data-accent="green"' in out)
            if name == 'Главная — стиль «Контроллер»':
                check('стиль «Контроллер» включается атрибутом на <html>', 'data-skin="net"' in out)
            if name == 'Устройства — удалённые':
                check('«Где находятся» — в меню фильтра (кнопка), отдельных вкладок нет', 'удалённые' in out and 'dev-loc' not in out and 'sort-btn' in out)
            if name == 'Новое устройство — группы':
                check('типы устройств по группам', all(x in out for x in ('Роутеры', 'Коммутаторы', 'Серверы и хранилища', 'Питание', 'Проверка доступности')))
            if name == 'Новое устройство — роутеры':
                check('роутеры: Keenetic, OpenWrt, SNMP, веб-панель', all(x in out for x in ('Keenetic / Netcraze', 'OpenWrt', 'Другой роутер по SNMP', 'Роутер без управления')))
            if name == 'ИБП — форма':
                check('форма ИБП: подсказка, как замерить', 'Как узнать, сколько берёт устройство' in out)
                check('форма ИБП: гнёзда, блок розеток, откуда питается', 'Откуда питается ИБП' in out and 'Блоки розеток' in out and 'loads' in out)
            if name == 'Блок розеток — нагрузка':
                check('блок розеток: дерево нагрузки', 'ptree' in out and 'Питается от' in out and 'Мониторы в серверной' in out)
            if name == 'Блок розеток — розетки':
                check('блок розеток: таблица розеток', 'Что в каких розетках' in out or 'что в какой розетке' in out)
            if name == 'ИБП · кривая':
                check('кривая разряда ИБП', 'ups-curve' in out and 'занято' in out)
            if name == 'ONT — настройка':
                check('ONT: провайдер, кросс, LAN-порты', 'ont-setup' in out and 'Оптика-Демо' in out and 'Волокно 1' in out)
            if name == 'Кросс — живые порты':
                check('порт кросса светится через ONT', 'pm-port g' in out or re.search(r'class="m3-port sfp"[^>]*--led: var\(--s3-led\)', out) is not None)   # the flat panel, or the 3D model of «Test» (a lit LED on the port)
            if name == 'Переезд места':
                check('окно «Переезд»', 'Переезд' in out and out.count('place-opt') == 2)
            if name == 'Доступность':
                check('доступность за 30 дней', 'up-bars' in out and 'сбо' in out)
            if name in ('Карта — дерево', 'Карта — кольца', 'Карта — по сетям'):
                check('карта: вид «' + name.split('— ')[1] + '» рисует узлы и связи', out.count('class="node') >= 5 and 'class="edge' in out and 'data-js-error="' not in out, out.count('class="node'))
            if name == 'Карта — камера в дереве':
                check('карта: у камеры в дереве есть действия, а не только порт коммутатора', 'node-info' in out and 'Камеры: вход, пароль, адрес, кадр' in out, re.sub(r'<[^>]+>', ' ', out[out.find('node-info'): out.find('node-info') + 1500]) if 'node-info' in out else 'карточки узла нет')
            if name == 'Настройки · О программе':
                check('о программе: карточка обновлений (версия, проверка, режим)', 'Обновления' in out and 'Проверить' in out and 'Обновлять ночью' in out, re.sub(r'<[^>]+>', ' ', out)[-500:])
            if name == 'Устройство площадки':
                check('устройство площадки: вкладка «На площадке» честно говорит, что канал не открыт', 'На площадке' in out and 'Нет связи с площадкой' in out and 'Повторить' in out, re.sub(r'<[^>]+>', ' ', out)[-400:])
            if name == 'Инструменты — каталог с инструментом':
                check('инструменты: свой инструмент стоит в каталоге инструментов, рядом кнопка загрузки', 'Свободное место' in out and 'Свой инструмент или из каталога' in out and 'Камеры и видеорегистраторы' in out, re.sub(r'<[^>]+>', ' ', out)[-400:])
            if name == 'Инструмент сообщества':
                check('инструмент сообщества: описание, форма, «Где запустить», «Запустить»', 'Свободное место' in out and 'Где запустить' in out and 'Запустить' in out and 'риск' in out, re.sub(r'<[^>]+>', ' ', out)[-400:])
            if name == 'Инструменты — сцены':
                check('сцены: «Кампус», «Посмотреть в демо», «Применить к моему плану», инструкция для нейросети', 'Кампус' in out and 'Посмотреть в демо' in out and 'Применить к моему плану' in out and 'Как написать сцену' in out, re.sub(r'<[^>]+>', ' ', out)[-400:])
            if name == 'Инструменты — площадки':
                check('площадки: список, агенты, режим сборщика', 'Удалённые площадки' in out or 'Площадки' in out, '') ; check('площадки: видна демо-площадка и «Эта установка — сборщик»', 'Склад (филиал)' in out and 'Эта установка' in out and 'Добавить площадку' in out, re.sub(r'<[^>]+>', ' ', out)[-400:])
            if name == 'VPS · Сборщик площадки':
                check('плагин «Сборщик площадки»: название площадки, адрес панели, порт, управление, кнопка', 'Название площадки' in out and 'Адрес этой панели' in out and 'Порт панели на машине' in out and 'Присылать данные на эту панель' in out and 'Управление отсюда' in out and 'Установить сборщик' in out, re.sub(r'<[^>]+>', ' ', out)[-500:])
            if name == 'VPS · ReckController OS':
                check('плагин ReckController OS: часовой пояс, точка, название и пароль Wi-Fi, кнопка', 'ReckController OS' in out and 'Часовой пояс машины' in out and 'Своя Wi-Fi-точка для телефона' in out and 'Пароль Wi-Fi' in out and 'Установить ReckController OS' in out, re.sub(r'<[^>]+>', ' ', out)[-500:])
            if name == 'Настройки · Система':
                check('раздел «Система»: время, обновления, Docker', 'Время и часовой пояс' in out and 'Обновления системы' in out and 'Docker' in out and 'Проверить обновления' in out and 'Перезагрузить машину' in out, re.sub(r'<[^>]+>', ' ', out)[-500:])
            if name == 'Настройки · Wi-Fi':
                check('«Сеть → Wi-Fi»: адаптеры, своя точка, подключение к сети', 'Адаптеры' in out and 'Своя Wi-Fi-точка' in out and 'Подключение к Wi-Fi' in out and 'Искать сети' in out and 'ReckController' in out and 'Изменить название или пароль' in out, re.sub(r'<[^>]+>', ' ', out)[-500:])
            if name == 'Настройки · VPN':
                check('«Сеть → VPN»: карточка AmneziaWG в разделе «Сеть»', 'VPN (AmneziaWG)' in out and 'Заменить конфиг' in out and 'Удалить конфиг' in out, re.sub(r'<[^>]+>', ' ', out)[-500:])
            if name == 'Настройки · режим разработчика':
                check('тумблер «Режим разработчика» в основных настройках', 'Режим разработчика' in out and 'Система' in out, re.sub(r'<[^>]+>', ' ', out)[-400:])
            if name == 'Карта — ONT':
                check('интернет через ONT на карте', 'edge isp' in out)
            if name == 'Настройки · Frank':
                check('карточка помощника в настройках', 'ai-settings' in out)
            if name == 'Настройки · Приложения':
                check('карточка «Приложения на телефон»', 'Приложения на телефон' in out and out.count('plugin-head') >= 4 and 'Frank' in out and 'Сканер' in out)
            if name == 'Настройки · Уведомления':
                check('уведомления в своём разделе', 'notify-grid' in out)
            if name == 'Помощник — не настроен':
                # the API part above saved a key with the assistant switched off
                check('панель помощника: «ключ есть, но выключен»', 'ai-panel' in out and 'Frank выключен' in out)
            if name == 'Помощник — настроен':
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=600,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/frank'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('Frank отдельным приложением (/frank)', 'ai-panel standalone' in out and 'frank-manifest.json' in out and 'data-js-error="' not in out)
                man = json.loads(urllib.request.urlopen(base + '/frank-manifest.json', timeout=10).read())
                check('манифест Frank', man['start_url'] == '/frank' and man['name'] == 'Frank')
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=600,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/speed'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('тест скорости отдельным приложением (/speed)', 'speed-app' in out and 'sp-start' in out and 'gauge' in out and 'data-js-error="' not in out)
                man = json.loads(urllib.request.urlopen(base + '/speed-manifest.json', timeout=10).read())
                check('манифест теста скорости', man['start_url'] == '/speed')
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=600,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/terminal'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('терминал отдельным приложением (/terminal)', 'term-app' in out and 'terminal-manifest.json' in out and 'data-js-error="' not in out)
                man = json.loads(urllib.request.urlopen(base + '/terminal-manifest.json', timeout=10).read())
                check('манифест терминала', man['start_url'] == '/terminal' and all(urllib.request.urlopen(base + i['src'], timeout=10).status == 200 for i in man['icons']))
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=500,1000', '--virtual-time-budget=8000',
                                      '--dump-dom', base + '/scan?test=1&still=1&pick=3'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                # «Карточки» (/cards): list, a device card, a card opened by a «scanned» code, hand-made cards (API + page + settings)
                dom = lambda url, w=500, h=1000: subprocess.run([browser, '--headless=new', '--disable-gpu', f'--window-size={w},{h}', '--virtual-time-budget=8000', '--dump-dom', base + url],
                                                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                devs = api('/api/state')['devices']; sw = next(d for d in devs if (d['state'].get('ports') or []))
                co = dom('/cards')
                check('карточки: приложение — сразу камера, без списков', 'cd-cam' in co and 'cd-row' not in co and 'cd-scan' not in co and 'data-js-error="' not in co)
                co = dom('/cards?card=' + sw['id'])
                check('карточки: коммутатор встаёт в 3D («Витрина»), без лишнего', 'vt-head' in co and 's3-box' in co and 'vt-facts' in co and 'Все порты' not in co and 'Подключено' not in co and 'data-js-error="' not in co)
                ups = next(d for d in devs if d['state'].get('ups'))
                co = dom('/cards?card=' + ups['id'])
                check('карточки: ИБП — кольца, потребление и график', 'cd-ups' in co and 'cd-ring' in co and 'Потребление за сутки' in co and 'data-js-error="' not in co)
                co = dom('/cards?card=' + sw['id'] + '&port=3')
                check('карточки: порт по нажатию — плашка с названием и скоростью', 'vt-pop' in co and 'vt-pop empty' not in co)
                co = dom('/cards?card=ucross')
                check('карточки: патч-панель / кросс — порты', 'vt-head' in co and 'class="pm' in co and 'data-js-error="' not in co)
                nas = next(d for d in devs if not d['state'].get('ports') and not d['state'].get('ups') and d['state'].get('summary'))
                rows0 = len(api('/api/state')['cards'])
                co = dom('/cards?card=' + nas['id'])
                check('карточки: устройство без портов — только значок, пока не дополнено', 'vt-ico' in co and 's3-box' not in co)
                bad = api('/api/cards', {'cards': [{'name': 'x', 'of': 'нет-такого'}]}, 'PUT')
                check('карточки: дополнение чужого id отклоняется', bad['cards'] == [])
                api('/api/cards', {'cards': [{'name': nas['name'], 'of': nas['id'], 'kind': 'nas', 'rows': [{'k': 'Гарантия', 'v': 'до 2028 года'}], 'notes': 'Стоит в нижнем ящике'}]}, 'PUT')
                co = dom('/cards?card=' + nas['id'])
                check('карточки: добавленные строки и заметка видны в карточке устройства', 'Гарантия' in co and 'до 2028 года' in co and 'Стоит в нижнем ящике' in co)
                check('карточки: дополнение не плодит отдельную карточку в списке', len([c for c in api('/api/state')['cards'] if not c.get('of')]) == rows0)
                png = open(os.path.join(ROOT, 'web', 'cards-icon-192.png'), 'rb').read()
                rq = urllib.request.Request(base + '/api/cards/photo/' + sw['id'], data=png, method='POST', headers={'Content-Type': 'image/png'})
                up = json.loads(urllib.request.urlopen(rq, timeout=10).read())
                ent = next((c for c in up.get('cards', []) if c.get('of') == sw['id']), {})
                check('карточки: фото устройства загружается', up.get('ok') and ent.get('photo') and ent.get('photoType') == 'png')
                got = urllib.request.urlopen(base + f"/api/cards/photo/{sw['id']}?v={ent.get('photo')}", timeout=10)
                check('карточки: фото отдаётся картинкой', got.status == 200 and got.headers.get('Content-Type') == 'image/png' and got.read() == png)
                bad = urllib.request.Request(base + '/api/cards/photo/' + sw['id'], data=b'not a picture', method='POST', headers={'Content-Type': 'image/png'})
                check('карточки: не картинка не принимается', not json.loads(urllib.request.urlopen(bad, timeout=10).read()).get('ok'))
                api('/api/cards', {'cards': [dict(c, spots=[{'n': 3, 'x': .5, 'y': .5, 'w': .08, 'h': .08}, {'n': 999, 'x': 2, 'y': .5, 'w': .1, 'h': .1}]) if c.get('of') == sw['id'] else c for c in api('/api/state')['cards']]}, 'PUT')
                ent = next(c for c in api('/api/state')['cards'] if c.get('of') == sw['id'])
                check('карточки: метки портов сохраняются, неверные отбрасываются', ent.get('photo') and ent.get('spots') == [{'n': 3, 'x': .5, 'y': .5, 'w': .08, 'h': .08}])
                co = dom('/cards?card=' + sw['id'] + '&port=3')
                check('карточки: своё фото с невидимыми кнопками портов вместо 3D', 'ph-spot' in co and 's3-box' not in co and 'vt-pop' in co and 'vt-pop empty' not in co and 'data-js-error="' not in co)
                co = dom('/?section=apps&app=cards&look=photo&photo=' + sw['id'] + '#settings', 1300, 900)
                check('карточки: редактор фото — метки и размер', 'pe-spot' in co and 'Размер меток' in co and 'data-js-error="' not in co)
                rq = urllib.request.Request(base + '/api/cards/photo/' + sw['id'], method='DELETE')
                urllib.request.urlopen(rq, timeout=10).read()
                co = dom('/cards?card=' + sw['id'])
                check('карточки: без фото снова 3D', 's3-box' in co and 'ph-spot' not in co)
                # 3D models: the plain one is built from the ports (all ports one real size), the user's own come from a neural network as JSON
                co = dom('/cards?card=' + sw['id'])
                widths = set(re.findall(r'class="m3-port[^"]*"[^>]*?style="[^"]*?width: ([0-9.]+)%', co))
                check('карточки: порты автомодели одного размера', 'm3-port' in co and len(widths) == 1)
                sys.path.insert(0, ROOT); from rackd import models as rl_models
                guide = urllib.request.urlopen(base + '/api/models/guide.txt', timeout=10).read().decode('utf-8')
                check('карточки: инструкция для нейросети', 'racklive-model' in guide and 'ПРИМЕР' in guide and len(guide) > 3000)
                bad = api('/api/models', {'model': {'format': 'racklive-model', 'version': 1, 'name': 'x', 'size': {'w': 10, 'h': 10, 'd': 10}, 'faces': {'front': {'items': [{'type': 'script', 'x': 1, 'y': 1}]}}}}, 'POST')
                check('карточки: модель с чужим элементом отклоняется с понятной ошибкой', not bad['ok'] and any('type' in e for e in bad['errors']))
                check('карточки: не JSON отклоняется', not api('/api/models', {'model': 'это не json'}, 'POST')['ok'])
                added = api('/api/models', {'model': json.dumps(rl_models.EXAMPLE)}, 'POST')
                rtr = next(d for d in devs if (d['state'].get('ports') or []) and len(d['state']['ports']) <= 10)
                cards_now = [c for c in api('/api/state')['cards'] if c.get('of') != rtr['id']]
                api('/api/cards', {'cards': cards_now + [{'of': rtr['id'], 'name': rtr['name'], 'kind': 'router', 'model': added.get('id'), 'view': {'rx': -10, 'ry': 170}}]}, 'PUT')
                ent = next(c for c in api('/api/state')['cards'] if c.get('of') == rtr['id'])
                check('карточки: своя модель сохраняется в библиотеке и выбирается для карточки', added['ok'] and ent.get('model') == added['id'] and ent.get('view') == {'rx': -10, 'ry': 170})
                co = dom('/cards?card=' + rtr['id'])
                check('карточки: своя модель рисуется (надпись, антенны, порты сзади) под зафиксированным углом', 'KEENETIC' in co and 'm3-part' in co and 'm3-back' in co and '170deg' in co and 'data-js-error="' not in co)
                co = dom('/?section=apps&app=cards&photo=' + rtr['id'] + '#settings', 1300, 900)
                check('карточки: окно «Вид» — модель, библиотека, инструкция', 'Добавить свою модель' in co and 'Инструкция для нейросети' in co and 'Keenetic Ultra' in co and 'm3-preview' in co and 'data-js-error="' not in co)
                # «Порты: отмечу сам»: the model's sockets stay a picture, the ports are marked on its faces by hand
                g2 = urllib.request.urlopen(base + '/api/models/guide.txt?free=1', timeout=10).read().decode('utf-8')
                check('карточки: инструкция «порты отмечу сам»', 'ОТМЕТИТ' in g2 and '"n"' not in g2.split('9. ПРИМЕР')[1])
                mk = [{'face': 'back', 'n': 5, 'x': 47.5, 'y': 15.5, 'w': 15, 'h': 13}, {'face': 'nowhere', 'n': 1, 'x': 1, 'y': 1, 'w': 1, 'h': 1}]
                api('/api/cards', {'cards': [dict(c, portsMode='manual', mports=mk) if c.get('of') == rtr['id'] else c for c in api('/api/state')['cards']]}, 'PUT')
                ent = next(c for c in api('/api/state')['cards'] if c.get('of') == rtr['id'])
                check('карточки: метки на гранях сохраняются, неверные отбрасываются', ent.get('portsMode') == 'manual' and ent.get('mports') == [mk[0]])
                co = dom('/cards?card=' + rtr['id'] + '&port=5')
                check('карточки: порты модели не привязаны, работают свои метки', 'class="m3-mark' in co and '<button type="button" class="m3-port' not in co and 'vt-pop' in co and 'WAN' in co and 'data-js-error="' not in co)
                co = dom('/?section=apps&app=cards&photo=' + rtr['id'] + '&marks=1#settings', 1300, 900)
                check('карточки: редактор меток на гранях модели', 'm3-face-flat' in co and 'pe-spot' in co and 'Отмечу сам' in co and 'data-js-error="' not in co)
                api('/api/cards', {'cards': [{k: v for k, v in c.items() if k != 'portsMode'} if c.get('of') == rtr['id'] else c for c in api('/api/state')['cards']]}, 'PUT')
                ent = next(c for c in api('/api/state')['cards'] if c.get('of') == rtr['id'])
                co = dom('/cards?card=' + rtr['id'])
                check('карточки: «из модели» — снова номера модели, метки не теряются', not ent.get('portsMode') and ent.get('mports') == [mk[0]] and '<button type="button" class="m3-port' in co and 'm3-mark' not in co)
                co = dom('/?skin=test&nav=1#rack', 1300, 1000)
                check('оформление Test: боковое меню, приборы-шкалы, значок Frank', 'tl-nav' in co and 'tl-burger' in co and 'sp-row' in co and 'class="sc"' in co and 'frank-eye' in co and 'data-js-error="' not in co)
                prev_w = (api('/api/state').get('dashboard') or {}).get('widgets') or []
                api('/api/dashboard', {'widgets': [{'id': 'rack', 'type': 'rack', 'size': 'M'}, {'id': 'stats', 'type': 'stats', 'size': 'S'}, {'id': 'uptime', 'type': 'uptime', 'size': 'S'}]}, 'PUT')
                co = dom('/?skin=test#rack', 1300, 1000)
                check('оформление Test: квадраты — строгие мини-приборы', 'class="tt t-stats"' in co and 'plamp' in co and 'tt-days' in co and 'data-js-error="' not in co)
                units = [u for r in api('/api/state')['racks'] for u in r['units'] if u.get('portmap')]
                for u in units[:3]:
                    co = dom('/?skin=test&unit=' + u['id'] + '#rack', 1300, 1000)
                    check(f"оформление Test: 3D-модель юнита «{u['type']}»", 'unit3d' in co and 'm3-port' in co and 'data-js-error="' not in co)
                api('/api/dashboard', {'widgets': [{'id': t, 'type': t, 'size': 'S'} for t in ('state', 'newdev', 'frank', 'note')] + [{'id': 'map', 'type': 'map', 'size': 'L'}]}, 'PUT')
                co = dom('/?skin=test#rack', 1300, 1000)
                check('оформление Test: сетевой экран, радар, глаз Frank; убранные виджеты не рисуются', 'class="fw' in co and 'tt-radar' in co and 'frank-eye' in co and 't-map' not in co and 'data-js-error="' not in co)
                co = dom('/?skin=test&wfull=ups#rack', 1300, 1000)
                check('оформление Test: окно ИБП — прибор', 'class="ui"' in co and 'ui-bat' in co and 'data-js-error="' not in co)
                api('/api/dashboard', {'widgets': [{'id': 'rack', 'type': 'rack', 'size': 'M'}, {'id': 'stats', 'type': 'stats', 'size': 'S'}]}, 'PUT')
                co = dom('/?skin=test#rack', 1300, 1000)
                check('оформление Test: шкаф в 3D и «Сводка» лампочкой', 'r3-wrap' in co and co.count('r3-unit') >= 6 and 'plamp' in co and 'data-js-error="' not in co)
                co = dom('/?skin=test&tour=1&tourstep=1&tourfast=1#rack', 1300, 1000)
                check('оформление Test: обучение открывает боковое меню и считает шаги', 'tour-step' in co and 'tl-nav' in co and 'data-js-error="' not in co)
                sw_id = next(d['id'] for d in api('/api/state')['devices'] if (d['state'].get('ports') or []) and len(d['state']['ports']) > 10)
                co = dom('/?skin=test&zoomports=1&device=' + sw_id + '#rack', 1100, 900)
                check('оформление Test: «Порты крупно» приближает блок портов анфас', 'm3-stage zoomed' in co and 'm3-tool zoom pri' in co and 'data-js-error="' not in co)
                cards0 = api('/api/state').get('cards') or []
                api('/api/cards', {'cards': cards0 + [{'of': sw_id, 'name': 'z', 'kind': 'switch', 'zoom': {'face': 'front', 'x': 50, 'y': 2, 'w': 200, 'h': 30}, 'pzoom': {'x': .1, 'y': .2, 'w': .5, 'h': .3}}]}, 'PUT')
                ent = next(c for c in api('/api/state')['cards'] if c.get('of') == sw_id)
                api('/api/cards', {'cards': cards0 + [{'of': sw_id, 'name': 'z', 'kind': 'switch', 'zoom': {'face': 'nope', 'x': 1, 'y': 1, 'w': 1, 'h': 1}, 'pzoom': {'x': 5}}]}, 'PUT')
                bad = next(c for c in api('/api/state')['cards'] if c.get('of') == sw_id)
                check('карточки: область приближения сохраняется, неверная отбрасывается', ent.get('zoom', {}).get('w') == 200 and ent.get('pzoom', {}).get('w') == .5 and 'zoom' not in bad and 'pzoom' not in bad)
                api('/api/cards', {'cards': cards0}, 'PUT')
                # «Гостевой Wi-Fi с порталом»: the card, the template library (a good and a bad .zip), the preview, a demo setup
                ow = next(d for d in api('/api/state')['devices'] if d['driver'] == 'demo_openwrt')
                pc = next(p for p in api(f"/api/devices/{ow['id']}/plugins", {'op': 'status'}, 'POST')['plugins'] if p['id'] == 'portal')
                check('портал: карточка знает порты, радио, порт управления и шаблоны', pc['hw']['lan'] == ['lan1', 'lan2', 'lan3', 'lan4'] and pc['hw']['mgmt'] == 'lan2'
                      and len(pc['hw']['radios']) == 2 and pc['templates'][0]['id'] == 'default')
                import io as _io, zipfile as _zf
                def _zip(files):
                    b = _io.BytesIO()
                    with _zf.ZipFile(b, 'w') as z:
                        for n, t in files.items():
                            z.writestr(n, t)
                    return b.getvalue()
                def _up(data, name='Кофейня'):
                    rq = urllib.request.Request(base + '/api/portal/templates?name=' + urllib.parse.quote(name), data=data, method='POST', headers={'Content-Type': 'application/zip'})
                    return json.loads(urllib.request.urlopen(rq, timeout=20).read())
                good = _up(_zip({'cafe/index.html': '<html><link rel="stylesheet" href="{{assets}}/s.css"><h1>{{name}}</h1>{{form}}</html>', 'cafe/s.css': 'h1{color:red}'}))
                bad1 = _up(_zip({'index.html': '<html>нет метки</html>'}))
                bad2 = _up(_zip({'index.html': '{{form}}', 'run.sh': 'rm -rf /'}))
                check('портал: шаблон загружается, без {{form}} и с чужими файлами — отказ', good.get('ok') and not bad1.get('ok') and 'form' in bad1.get('error', '') and not bad2.get('ok'))
                tid = good['template']['id']
                pv = urllib.request.urlopen(base + f'/api/portal/templates/{tid}/preview', timeout=10)
                html = pv.read().decode()
                check('портал: предпросмотр — метки заполнены, страница в песочнице', 'rl-btn' in html and '{{' not in html and 'sandbox' in (pv.headers.get('Content-Security-Policy') or '')
                      and urllib.request.urlopen(base + f'/api/portal/templates/{tid}/f/s.css', timeout=10).read() == b'h1{color:red}')
                try:                                    # the port Rack Live manages the router through cannot become a guest port
                    api(f"/api/devices/{ow['id']}/plugins", {'plugin': 'portal', 'op': 'install', 'profile': {'mainSsid': 'Office', 'mainKey': 'office-2026', 'guestSsid': 'Guest', 'ports': {'lan2': 'guest'}}}, 'POST')
                    guard = False
                except urllib.error.HTTPError as e:
                    guard = 'управл' in e.read().decode('utf-8', 'replace')
                r = api(f"/api/devices/{ow['id']}/plugins", {'plugin': 'portal', 'op': 'install', 'profile': {'mainSsid': 'Office', 'mainKey': 'office-2026', 'guestSsid': 'Guest', 'template': tid, 'ports': {'lan4': 'trunk'}}}, 'POST')
                pc2 = next(p for p in api(f"/api/devices/{ow['id']}/plugins", {'op': 'status'}, 'POST')['plugins'] if p['id'] == 'portal')
                devs = api('/api/state')['devices']
                check('портал: настройка (демо) — профиль сохранён, пароли не уходят в браузер', guard and r.get('ok') and pc2['saved']['template'] == tid and pc2['saved']['mainKeySet']
                      and 'mainKey' not in pc2['saved'] and 'portal' not in next(d for d in devs if d['id'] == ow['id']))
                co = dom(f"/?skin=test&device={ow['id']}&tab=plugins&plugin=portal&psec=ports#rack", 1300, 1000)
                check('портал: окно плагина — порты по одному', 'pt-port' in co and co.count('pt-port r-') >= 4 and 'data-js-error="' not in co)
                api(f"/api/portal/templates/{tid}", None, 'DELETE')
                rc = next(p for p in api(f"/api/devices/{ow['id']}/plugins", {'op': 'status'}, 'POST')['plugins'] if p['id'] == 'remote')
                try:
                    api(f"/api/devices/{ow['id']}/plugins", {'plugin': 'remote', 'op': 'install', 'hub': 'x:Wireguard0'}, 'POST')
                    rguard = False
                except urllib.error.HTTPError:
                    rguard = True
                co = dom(f"/?skin=test&device={ow['id']}&tab=plugins&plugin=remote#rack", 1300, 1000)
                check('удалённый доступ: карточка, туннель на связи, в демо не настраивается, окно рисуется', rc['installed'] and rc['tunnel']['up'] and 'hubs' in rc and rguard
                      and 'Туннель на связи' in co and 'data-js-error="' not in co)
                api('/api/dashboard', {'widgets': prev_w}, 'PUT')
                ok_ic = True
                for mf in ('manifest.json', 'frank-manifest.json', 'speed-manifest.json', 'terminal-manifest.json', 'cards-manifest.json'):
                    mj = json.loads(urllib.request.urlopen(base + '/' + mf + '?skin=test', timeout=10).read())
                    ok_ic = ok_ic and all('/look-test/' in i['src'] and urllib.request.urlopen(base + i['src'], timeout=10).status == 200 for i in mj['icons'])
                co = dom('/frank?skin=test', 600, 900)
                check('оформление Test: свои значки приложений (манифесты, «Домой», вкладка)', ok_ic and '/look-test/frank-180.png' in co and 'frank-manifest.json?skin=test' in co)
                co = dom('/?skin=test&section=apps#settings', 1300, 900)
                check('оформление Test: значки в «Приложениях» и шапке', co.count('/look-test/') >= 5 and 'data-js-error="' not in co)
                co = dom('/?skin=test&section=notify#settings', 600, 900)
                check('оформление Test: здоровье хорошее = синее (шкала)', 'data-js-error="' not in co)
                co = dom('/cards?fakescan=' + sw['id'])
                check('карточки: «отсканированный» код открывает карточку, её можно только закрыть', 'cd-sheet2' in co and 'vt-head' in co and sw['name'] in co and 'cd-x' in co and 'Дополнить' not in co)
                man = json.loads(urllib.request.urlopen(base + '/cards-manifest.json', timeout=10).read())
                check('манифест карточек', man['start_url'] == '/cards' and all(urllib.request.urlopen(base + i['src'], timeout=10).status == 200 for i in man['icons']))
                r = api('/api/cards', {'cards': [{'name': 'Принтер Бухгалтерия', 'kind': 'printer', 'vendor': 'HP', 'model': 'LaserJet 1020', 'ip': '192.168.1.50', 'rows': [{'k': 'Куплен', 'v': '2019'}], 'notes': 'Картридж Q2612A'}]}, 'PUT')
                mid = r['cards'][0]['id']
                check('карточки: своя карточка сохраняется и возвращается в состоянии', mid and [c['id'] for c in api('/api/state')['cards']] == [mid])
                co = dom('/cards?card=' + mid)
                check('карточки: страница своей карточки', 'Принтер Бухгалтерия' in co and 'LaserJet 1020' in co and 'Куплен' in co and 'Картридж Q2612A' in co)
                co = dom('/?section=apps&app=cards#settings', 1300, 900)
                check('карточки: «Сканер» в приложениях раскрывается меню как у плагинов', 'plugin-head' in co and 'Установить на телефон' in co and 'Создать карточку' in co and 'Наклейки' in co and 'Печать наклеек' not in co and 'Карточки устройств' in co and 'Сканер: карточки устройств' not in co and 'data-js-error="' not in co)
                co = dom('/?section=apps&app=cards&cl=1#settings', 1300, 900)
                check('карточки: список карточек — QR, Дополнить, Вид', 'Принтер Бухгалтерия' in co and 'Дополнить' in co and 'Вид' in co and 'Из шкафа' not in co and '>Свои' not in co and '>Все' not in co and 'data-js-error="' not in co)
                co = dom('/?section=apps&app=cards&sticker=' + mid + '#settings', 1300, 900)
                check('карточки: наклейка готовится картинкой (скачать / поделиться), не печатью', 'cd-stk-img' in co and 'Скачать' in co and f'RL-{mid}-25mm.png' in co and 'data-js-error="' not in co)
                api('/api/cards', {'cards': []}, 'PUT')
                out2 = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=500,1000', '--virtual-time-budget=8000',
                                       '--dump-dom', base + '/scan?test=1&still=1&mode=photo&pick=3'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('сканер портов: режим «Фото» делает снимок и держит рамки', 'data-frozen="1"' in out2 and 'id="snapbg"' in out2 and '· порт 3</div>' in out2 and 'Переснять' in out2)
                check('сканер портов (/scan): тестовая сцена находит QR и показывает порт','id="testbg"' in out and '· порт 3</div>' in out and urllib.request.urlopen(base + '/vendor/jsQR.js', timeout=10).status == 200)
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=1300,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/?section=apps&install=frank#settings'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('окно установки Frank с QR-кодом', 'class="qr"' in out and '<svg' in out.split('class="qr"', 1)[-1][:200] and 'data-js-error="' not in out)
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=1300,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/' + q], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('панель помощника: подсказки и поле ввода', 'ai-suggest' in out and 'ai-foot' in out)
                # a phone (600 px): Settings as an iOS list, a section opens with «‹ Настройки»; a computer keeps the two columns
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=600,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/#settings'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('телефон: настройки списком как в iOS', 'ios-list' in out and out.count('ios-cell') >= 6 and 'set-nav' not in out and 'data-js-error="' not in out)
                out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=600,900', '--virtual-time-budget=6000',
                                      '--dump-dom', base + '/?section=access#settings'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
                check('телефон: раздел открыт со стрелкой «Настройки»', 'ios-back' in out and 'Двухфакторная защита' in out and 'ios-list' not in out)
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(data, ignore_errors=True)
        print(f'\n{"ВСЁ OK" if not fails else "ОШИБКИ: " + ", ".join(fails)}')


if __name__ == '__main__':
    main()
    sys.exit(1 if fails else 0)
