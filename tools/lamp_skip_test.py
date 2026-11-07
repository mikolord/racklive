"""«Следить за здоровьем» выключено → устройство не видит лампочка «Сводки» и не считают счётчики «N из M устройств в сети».
Поднимает демо, смотрит DOM главной (--dump-dom), отмечает проблемные демо-устройства «без слежки» и смотрит снова.   python tools/lamp_skip_test.py"""
import os, re, sys, json, socket, subprocess, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSERS = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe', '/usr/bin/chromium', '/usr/bin/google-chrome']
BROWSER = next((b for b in BROWSERS if os.path.exists(b)), None)
ok = True


def check(name, cond, extra=''):
    global ok
    print(('OK   ' if cond else 'FAIL ') + name + (' — ' + str(extra) if extra and not cond else ''))
    ok = ok and bool(cond)


if not BROWSER:
    print('нет браузера — тест пропущен'); sys.exit(0)
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
data = tempfile.mkdtemp(prefix='rl-lamp-')
env = dict(os.environ, RL_DEMO='1', RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), RL_PORT=str(port), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port}'


def call(path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, method='PUT' if body is not None else 'GET',
                                 headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def home():
    r = subprocess.run([BROWSER, '--headless=new', '--disable-gpu', '--window-size=1500,900', '--virtual-time-budget=9000', '--dump-dom', base + '/#rack'],
                       capture_output=True, text=True, encoding='utf-8', timeout=120)
    lamp = re.search(r'class="plamp[^"]*"[^>]*title="([^"]*)"', r.stdout)
    sub = re.search(r'(\d+) из (\d+) устройств в сети', r.stdout)
    return (lamp.group(1) if lamp else None), (tuple(map(int, sub.groups())) if sub else None)


try:
    for _ in range(80):
        try: call('/api/state'); break
        except OSError: time.sleep(.3)
    time.sleep(6)
    bad = [d for d in call('/api/state')['devices'] if (d.get('state') or {}).get('status') in ('offline', 'warning')]
    check('в демо есть проблемное устройство', bad, 'нечем проверять')
    lamp0, cnt0 = home()
    check('до: лампочка видит проблему', lamp0 and lamp0 != 'всё в сети', lamp0)
    for d in bad:
        call('/api/devices/' + d['id'], {'noHealth': True})
    time.sleep(1)
    lamp1, cnt1 = home()
    check('после «не следить»: лампочка спокойна', lamp1 == 'всё в сети', lamp1)
    check('счётчик «N из M» не считает устройство без слежки', cnt0 and cnt1 and cnt1[1] == cnt0[1] - len(bad), (cnt0, cnt1))
finally:
    srv.terminate()
print('\nВСЁ OK' if ok else '\nЕСТЬ ОШИБКИ')
sys.exit(0 if ok else 1)
