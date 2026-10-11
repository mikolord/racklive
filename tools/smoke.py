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
                 'Юнит ИБП — правка': f'?mode=edit&editunit={units["ups"]}#rack', 'Светлая тема': '?theme=light#plan'}
        for name, q in pages.items():
            out = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=1300,900', '--virtual-time-budget=6000',
                                  '--dump-dom', base + '/' + q], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90).stdout
            err = ''
            if 'data-js-error="' in out:
                err = out.split('data-js-error="', 1)[1].split('"', 1)[0]
            check(name, 'page-title' in out and 'rl-crash' not in out and not err, err or ('пустая страница' if 'page-title' not in out else ''))
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
