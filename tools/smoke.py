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

        # ── «Сканировать сеть» ──
        sys.path.insert(0, ROOT)
        from rackd import netscan as nsc
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
        check('openwrt plugins: status', [p['id'] for p in OP({'op': 'status'})['plugins']] == ['forkop', 'podkop', 'modem'])
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
        check('vps plugins: status', [p['id'] for p in VP({'op': 'status'})['plugins']] == ['3xui', 'remnawave'])
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
        # security advisor: findings, a fix, «это нормально»
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
                 'События': '#events', 'Настройки': '#settings', 'Щиток': '?place=rack1#rack', 'Правка размещения': '?mode=edit#rack',
                 'Роутер · VPN': f'?device={dev["demo_router"]}&tab=vpn', 'Коммутатор · порт': f'?device={dev["demo_switch"]}&tab=ports&port=12',
                 'ИБП': f'?device={dev["ups"]}', 'NAS': f'?device={dev["demo_nas"]}', 'Патч-панель': f'?unit={units["patch"]}#rack',
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
                 'Устройства — удалённые': '#devices', 'Доступ — вход и устройства': '?section=access#settings',
                 'Доступ — подключение приложения': '?section=access&mfa=totp#settings',
                 'Новое устройство — группы': '?add=1#devices', 'Новое устройство — роутеры': '?add=1&addgrp=router#devices',
                 'VPS · 3x-ui': f'?device={dev["demo_server"]}&tab=plugins&plugin=3xui',
                 'VPS · Remnawave': f'?device={dev["demo_server"]}&tab=plugins&plugin=remnawave',
                 'Безопасность': '?security=1#rack', 'Интернет': '?inet=1#rack',
                 'Роутер · конфигурация': f'?device={dev["demo_router"]}&tab=config', 'Устройства · новые': '#devices',
                 'Помощник — не настроен': '?ai=1#rack', 'Помощник — настроен': '?ai=1#rack',
                 'Устройства · роутеры в сети': '?routers=1#devices', 'Настройки · Frank': '?section=frank#settings', 'Настройки · Приложения': '?section=apps#settings', 'Настройки · Уведомления': '?section=notify#settings',
                 'Доступность': '?uptime=1#rack', 'Карта — ONT': '#map',
                 'Новый юнит — что ставим': '?mode=edit&editunit=new#rack', 'Переезд места': '?mode=edit&move=1#rack',
                 'Карта — правка (магнит)': '?mode=edit#map',
                 'Блок розеток — нагрузка': '?unit=upduA#rack', 'Блок розеток — розетки': '?mode=edit&editunit=upduA&pw=1#rack',
                 'ИБП — форма': f'?editdev={dev["ups"]}',
                 'Proxmox · виртуалки': f'?device={dev["demo_proxmox"]}&tab=vms', 'ИБП · кривая': f'?device={dev["ups"]}',
                 'ONT — настройка': f'?mode=edit&editunit={units["modem"]}#rack', 'Кросс — живые порты': f'?unit={units["cross"]}#rack'}
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
                check('виджет ИБП: широкий и квадрат', 'upsw-bat' in out and 't-ups' in out and 'хватит при отключении света' in out)
            if name == 'Блок розеток — нагрузка':
                check('розетки блока и ИБП кружками на шкафу', 'leds round' in out and '<i class="r">' in out)
            if name == 'План — дом':
                check('покрытие Wi-Fi на плане', 'cov-pin' in out)
            if name == 'Тест скорости':
                check('окно теста скорости', 'gauge' in out)
            if name == 'Настройки':
                check('настройки разбиты на разделы', out.count('set-item') >= 6 and 'set-head' in out)
            if name == 'Устройства · роутеры в сети':
                check('карточка «Роутеры в сети»', 'router-row' in out and 'Гостевой домик' in out)
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
            if name == 'Настройки — оформление':
                check('раздел «Оформление»: стили, акцент, тема', 'Стиль интерфейса' in out and 'Графит' in out and 'Цвет акцента' in out and 'Светлая и тёмная тема' in out)
            if name == 'Главная — стиль «Графит»':
                check('стиль «Графит» включается атрибутами на <html>', 'data-skin="graphite"' in out and 'data-accent="green"' in out)
            if name == 'Устройства — удалённые':
                check('вкладки Все / Локальные / Удалённые', all(x in out for x in ('Все · ', 'Локальные · ', 'Удалённые · ')))
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
                check('порт кросса светится через ONT', 'pm-port g' in out)
            if name == 'Переезд места':
                check('окно «Переезд»', 'Переезд' in out and out.count('place-opt') == 2)
            if name == 'Доступность':
                check('доступность за 30 дней', 'up-bars' in out and 'сбо' in out)
            if name == 'Карта — ONT':
                check('интернет через ONT на карте', 'edge isp' in out)
            if name == 'Настройки · Frank':
                check('карточка помощника в настройках', 'ai-settings' in out)
            if name == 'Настройки · Приложения':
                check('карточка «Приложения на телефон»', 'Приложения на телефон' in out and 'app-row' in out)
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
