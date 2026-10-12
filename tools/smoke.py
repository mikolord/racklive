#!/usr/bin/env python3
"""Smoke test: starts Rack Live in demo mode on a temp data dir, checks the API round-trips and
opens every tab / sheet / editor in a headless browser, failing on any interface error.

    python tools/smoke.py            # needs a Chromium-based browser for the UI part (Edge / Chrome), skipped otherwise
"""
import gzip, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request

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
        found = api('/api/detect', {'host': f'127.0.0.1:{port}'}, 'POST')['found']
        check('detect: answers with a ranked list', found and found[-1]['driver'] == 'ping', json.dumps(found, ensure_ascii=False)[:200])
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
                 'VPS · 3x-ui': f'?device={dev["demo_server"]}&tab=plugins&plugin=3xui',
                 'VPS · Remnawave': f'?device={dev["demo_server"]}&tab=plugins&plugin=remnawave',
                 'Безопасность': '?security=1#rack'}
        for name, q in pages.items():
            out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=1300,900', '--virtual-time-budget=6000',
                                  '--dump-dom', base + '/' + q], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
            err = ''
            if 'data-js-error="' in out:
                err = out.split('data-js-error="', 1)[1].split('"', 1)[0]
            check(name, 'page-title' in out and 'rl-crash' not in out and not err, err or ('пустая страница' if 'page-title' not in out else ''))
            if name == 'Размещение':
                check('подсказка на вкладке', 'hint-box' in out)
            if name == 'План — дом':
                check('покрытие Wi-Fi на плане', 'cov-pin' in out)
            if name == 'Тест скорости':
                check('окно теста скорости', 'gauge' in out)
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
