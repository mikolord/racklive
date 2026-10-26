"""«Потребление» (Настройки → О программе): the counters, the folder breakdown and the API on a real demo server. Run: python tools/usage_test.py (prints ВСЁ OK)"""
import json, os, shutil, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import usage  # noqa: E402

bad = []


def check(name, ok):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        bad.append(name)


rss, peak = usage.rss_bytes()
check('память процесса читается', isinstance(rss, int) and 5_000_000 < rss < 8_000_000_000)

d = tempfile.mkdtemp()
try:
    for name, size in (('config.json', 1000), ('config.bak.json', 500), ('history.json', 3000), ('ai_chats.json', 700), ('mystery.bin', 90)):
        open(os.path.join(d, name), 'wb').write(b'x' * size)
    os.makedirs(os.path.join(d, 'backups', 'd1')); open(os.path.join(d, 'backups', 'd1', 'a.txt'), 'wb').write(b'y' * 2000)
    os.makedirs(os.path.join(d, 'icons')); open(os.path.join(d, 'icons', 'a.svg'), 'wb').write(b'z' * 300)
    u = usage.Usage(d, [os.path.join(ROOT, 'rackd')])
    u.sample()
    p = u.public({'today': {'q': 1, 'in': 2, 'out': 3}})
    by = {i['id']: i['bytes'] for i in p['disk']['items']}
    check('папка данных разложена по группам', by == {'history': 3000, 'config': 1500, 'backups': 2000, 'frank': 700, 'media': 300, 'other': 90})
    check('сумма сходится', p['disk']['data'] == sum(by.values()) == 7590)
    check('есть свободное место и размер программы', p['disk']['free'] and p['disk']['total'] and p['disk']['code'] > 10_000)
    check('процессор в процентах, без отрицательных', p['cpu']['avg'] >= 0 and p['cpu']['cores'] >= 1 and (p['cpu']['now'] is None or p['cpu']['now'] >= 0))
    check('потоки и время работы', p['threads'] >= 1 and p['uptime'] >= 0 and p['frank']['today']['q'] == 1)
    u.sample()
    check('точка истории раз в минуту, чаще не пишется', len(u.samples) == 1)
    u.samples[-1]['t'] -= 120; u.sample()
    check('вторая точка через минуту', len(u.samples) == 2)
    u.samples[0]['t'] -= 400                                # an old point: the history chart needs two neighbours
    p2 = u.public()
    check('история отдаёт память и процессор', len(p2['history']) == 1 and 'cpu' in p2['history'][0])
finally:
    shutil.rmtree(d, ignore_errors=True)

port, data = 9978, tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state', timeout=5).read(); break
        except Exception:
            time.sleep(.5)
    j = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/usage', timeout=10).read())
    check('сервер: /api/usage отдаёт всё нужное', all(k in j for k in ('cpu', 'mem', 'disk', 'threads', 'uptime', 'history', 'frank')) and j['mem']['rss'] and j['disk']['data'] > 0)
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
    shutil.rmtree(data, ignore_errors=True)

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
