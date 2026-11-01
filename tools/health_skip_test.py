"""«Не следить за здоровьем»: a device (or every remote one) can be left out of the network health, the availability list and the problem counters
while it stays on the map and in the lists. Starts Rack Live in the demo mode on a temp data dir and checks the API round-trips."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        fails.append(name)


def main():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    data = tempfile.mkdtemp(prefix='rl-hs-')
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
        time.sleep(4)
        st = api('/api/state')
        n0 = st['health']['stats']['devices']
        up0 = {u['dev'] for u in st['uptime']}
        check('nobody is skipped at the start', not any(d.get('healthSkip') for d in st['devices']))
        local = next(d for d in st['devices'] if d.get('location') != 'remote' and d['id'] in up0 and d.get('driver') not in ('demo_router', 'demo_switch'))
        remote = [d for d in st['devices'] if d.get('location') == 'remote']
        check('the demo has remote devices', len(remote) >= 1, str(len(remote)))

        # one device switched off
        api(f"/api/devices/{local['id']}", {'noHealth': True}, 'PUT')
        st = api('/api/state')
        d = next(x for x in st['devices'] if x['id'] == local['id'])
        check('the device is flagged and stays in the list', d.get('healthSkip') is True and d.get('noHealth') is True)
        check('it is gone from the availability list', local['id'] not in {u['dev'] for u in st['uptime']})
        check('the network health is still computed', st['health'] is not None and st['health']['stats']['devices'] <= n0, str(st['health'] and st['health']['stats']))
        check('the map still shows it', any(n.get('id') == local['id'] or local['name'] in json.dumps(n, ensure_ascii=False) for n in st['topology']['nodes']))
        api(f"/api/devices/{local['id']}", {'noHealth': False}, 'PUT')
        st = api('/api/state')
        check('switched back on: counted again', not next(x for x in st['devices'] if x['id'] == local['id']).get('healthSkip') and local['id'] in {u['dev'] for u in st['uptime']})

        # one device of a remote site: its id has a dash («s<site>-<key>») — «Не следить за этим устройством» used to answer «не найдено»
        r0 = next((x for x in remote if '-' in x['id']), remote[0])
        check('a remote-site device id has a dash', '-' in r0['id'], r0['id'])
        api(f"/api/devices/{r0['id']}", {'noHealth': True}, 'PUT')
        st = api('/api/state')
        check('a remote-site device can be switched off by itself', next(x for x in st['devices'] if x['id'] == r0['id']).get('noHealth') is True)
        check('and it is gone from the availability list', r0['id'] not in {u['dev'] for u in st['uptime']})
        api(f"/api/devices/{r0['id']}", {'noHealth': False}, 'PUT')

        # every remote device at once
        api('/api/settings', {'skipRemoteHealth': True}, 'PUT')
        st = api('/api/state')
        rem = [x for x in st['devices'] if x.get('location') == 'remote']
        check('the global switch flags every remote device', rem and all(x.get('healthSkip') for x in rem), str([x['name'] for x in rem if not x.get('healthSkip')]))
        check('local devices are not touched by it', not any(x.get('healthSkip') for x in st['devices'] if x.get('location') != 'remote'))
        check('remote devices are gone from the availability list', not ({x['id'] for x in rem} & {u['dev'] for u in st['uptime']}))
        check('the health survives', st['health'] is not None and st['health']['stats']['devices'] > 0)
        check('the setting is kept', st['settings'].get('skipRemoteHealth') is True)
        api('/api/settings', {'skipRemoteHealth': False}, 'PUT')
        st = api('/api/state')
        check('and switched off again', not any(x.get('healthSkip') for x in st['devices']))
        err = ''
        srv.terminate()
        try:
            err = srv.stderr.read(4000).decode(errors='replace')
        except Exception:
            pass
        check('no traceback in the server log', 'Traceback' not in err, err[-600:])
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        shutil.rmtree(data, ignore_errors=True)
    print('\nВСЁ OK' if not fails else '\nПРОВАЛЫ: ' + ', '.join(fails))
    sys.exit(1 if fails else 0)


main()
