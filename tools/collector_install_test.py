"""Plugin «Сборщик площадки»: scripts are valid shell, status parsing, the packed code, the config written on the new machine (first install and repeat), the site made before the job,
the whole flow against a fake SSH, secrets stay out of the log. Run: python tools/collector_install_test.py"""
import io, json, os, re, shutil, subprocess, sys, tarfile, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import collector_install as ci, sites as sites_mod, auth
from rackd.drivers.sshhost import SSHHost
from rackd.store import Store
from rackd.util import DriverError

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


BASH = shutil.which('bash') or next((p for p in (r'C:\Users\Admin\network-tools\bin\git\usr\bin\bash.exe', r'C:\Users\Admin\network-tools\bin\git\usr\bin\sh.exe', r'C:\Program Files\Git\bin\bash.exe') if os.path.exists(p)), None)


def syntax(name, script):
    if not BASH:
        print('  skip ' + name + ' (нет bash)')
        return
    f = tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False, encoding='utf-8', newline='\n')
    f.write(script)
    f.close()
    r = subprocess.run([BASH, '-n', f.name], capture_output=True, text=True)
    os.remove(f.name)
    ok('bash -n: ' + name, r.returncode == 0, r.stderr)


TOKEN, URL = 'abcdefghijklmnop1234567890', 'https://racklive.example.com'
cfg = ci.make_config('Квартира', URL, TOKEN, 'pw-Secret-123', 'actions', False)
script = ci.install_script(URL, TOKEN, cfg, 9998)
syntax('status', ci.STATUS)
syntax('install', script)
syntax('install (самоподписанный)', ci.install_script(URL, TOKEN, cfg, 9999, True))
syntax('remove', ci.remove_script())
syntax('remove + данные', ci.remove_script(True))
ok('скрипт не пишет пароль открытым текстом', 'pw-Secret-123' not in script)
ok('ключ площадки только в переменной, не в аргументах curl/wget', script.count(TOKEN) == 1 and 'curl' not in script.split('RL_TOKEN=')[1].split('\n')[0])
ok('читающие stdin команды закрыты от скрипта', '</dev/null' in script and 'apt-get install -y -qq python3 openssh-client iputils-ping curl ca-certificates tzdata </dev/null' in script)

# status
s = ci.parse_status('@@os Debian GNU/Linux 13 (trixie)\n@@uid 0\n@@mem 3800\n@@free 51000\n@@systemd\n@@python 3.13\n@@apt\n@@ver 2.9.0\n@@active active\n@@ip 192.168.1.50\n@@end\n')
ok('статус: система, память, systemd, apt', s['os'].startswith('Debian') and s['mem'] == '3800' and 'systemd' in s and 'apt' in s and s['ver'] == '2.9.0' and s['active'] == 'active', s)

# address of the main panel
for good in ('https://racklive.example.com', 'http://192.168.1.3:9998/', 'https://a.b.c:8443'):
    try:
        ok('адрес принят: ' + good, ci.clean_url(good) == good.rstrip('/'))
    except ValueError:
        ok('адрес принят: ' + good, False)
for bad in ('', 'racklive.example.com', 'ftp://x.y', 'https://', 'https://a b', 'javascript:alert(1)', 'https://x.y;rm -rf /'):
    try:
        ci.clean_url(bad)
        ok('адрес отклонён: ' + repr(bad), False)
    except ValueError:
        ok('адрес отклонён: ' + repr(bad), True)

# config
ok('конфиг: пароль только хэшем, ключ и название на месте', cfg['auth'].get('hash') and 'pw-Secret-123' not in json.dumps(cfg) and cfg['collector']['token'] == TOKEN
   and cfg['collector']['level'] == 'actions' and cfg['collector']['enabled'] and cfg['settings']['title'] == 'Квартира' and auth.check_password(cfg['auth'], 'pw-Secret-123'))
try:
    ci.make_config('x', URL, TOKEN, 'pw', 'root', False)
    ok('неизвестный уровень отклонён', False)
except ValueError:
    ok('неизвестный уровень отклонён', True)

# the packed code
raw = ci.pack()
tf = tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz')
names = tf.getnames()
ok('в архиве код и интерфейс', 'rackd/server.py' in names and 'rackd/collector.py' in names and 'web/index.html' in names and 'web/app.js' in names and 'web/agent.py' in names, len(names))
ok('нет мусора и чужих данных', not any('__pycache__' in n or 'node_modules' in n or n.endswith(('.pyc', '.map', 'package-lock.json')) or n.startswith(('data', 'tools')) for n in names))
ok('нет ни одного пути наружу', not any(n.startswith('/') or '..' in n.split('/') for n in names))
ok('архив небольшой (до 8 МБ) и кешируется', 100_000 < len(raw) < 8_000_000 and ci.pack() is raw, len(raw))

# what the script writes into config.json on the new machine: first install, then a repeat one that keeps the administrator
m = re.search(r"<<'PYEOF' \|\| fail \"не удалось записать настройки\"\n(.*?)\nPYEOF", script, re.S)
ok('в скрипте есть запись настроек', bool(m))
if m:
    td = tempfile.mkdtemp()
    code = m.group(1).replace('/var/lib/racklive', td.replace('\\', '/'))
    env = dict(os.environ, RL_CFG=__import__('base64').b64encode(json.dumps(cfg).encode()).decode(), PYTHONIOENCODING='utf-8')
    r = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True, env=env)
    saved = json.load(open(os.path.join(td, 'config.json'), encoding='utf-8'))
    ok('первая установка: администратор и ключ записаны, сообщено о создании', '@@created 1' in r.stdout and saved['auth'] == cfg['auth'] and saved['collector']['token'] == TOKEN, r.stderr)
    saved['auth'] = auth.hash_password('changed-by-owner')
    saved['devices'] = [{'id': 'mine'}]
    json.dump(saved, open(os.path.join(td, 'config.json'), 'w', encoding='utf-8'))
    cfg2 = ci.make_config('Квартира', URL, 'zzzzzzzzzzzzzzzzzzzzzz', 'new-pass', 'view', False)
    env['RL_CFG'] = __import__('base64').b64encode(json.dumps(cfg2).encode()).decode()
    r = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True, env=env)
    again = json.load(open(os.path.join(td, 'config.json'), encoding='utf-8'))
    ok('повторная установка: администратор и устройства остались, ключ обновлён', '@@created' not in r.stdout and auth.check_password(again['auth'], 'changed-by-owner')
       and again['devices'] == [{'id': 'mine'}] and again['collector']['token'] == 'zzzzzzzzzzzzzzzzzzzzzz' and again['collector']['level'] == 'view', r.stderr)

# the site made before the job (App.collector_prepare on a bare object: it only needs the store and the sites)
from rackd import server


class App:
    pass


app = App()
app.store = Store(tempfile.mkdtemp())
app.sites = sites_mod.Sites(app)
app.store.cfg['apps'] = {'url': 'https://racklive.example.com'}
dev = {'id': 'vps1', 'name': 'Мини-ПК', 'driver': 'ssh'}
app.store.cfg['devices'].append(dev)
body = server.App.collector_prepare(app, dev, {'name': 'Квартира Ивановых', 'port': 9998, 'level': 'terminal'}, 'install')
c = body['_collector']
site = app.sites.get(c['siteId'])
ok('площадка создана, адрес взят из «Приложений»', site and site['name'] == 'Квартира Ивановых' and c['url'] == 'https://racklive.example.com' and c['token'] == site['token'], c)
ok('конфиг нового сборщика содержит ключ этой площадки', c['cfg']['collector']['token'] == site['token'] and c['cfg']['collector']['level'] == 'terminal' and auth.check_password(c['cfg']['auth'], c['password']))
dev['panelInfo'] = {'collector': {'siteId': site['id']}}
again = server.App.collector_prepare(app, dev, {'name': 'другое имя'}, 'install')
ok('повторная установка не плодит площадки', len(app.sites.items) == 1 and again['_collector']['siteId'] == site['id'])
for bad in ({'server': 'nope'}, {'port': 80}, {'port': 'abc'}, {'level': 'root'}):
    try:
        server.App.collector_prepare(app, dev, bad, 'install')
        ok('отклонено: ' + str(bad), False)
    except ValueError:
        ok('отклонено: ' + str(bad), True)
ok('удаление: площадка уходит только по просьбе', server.App.collector_prepare(app, dev, {}, 'remove')['_site'] is None and server.App.collector_prepare(app, dev, {'removeSite': True}, 'remove')['_site'] == site['id'])


# the whole flow against a fake SSH
class Fake(SSHHost):
    def __init__(self, reply):
        self.reply, self.ran = reply, []

    def _run(self, cfg, script, timeout=30, remote='sh -s'):
        self.ran.append(script)
        return self.reply


good = Fake('— пакеты: python3\n— скачиваю\n@@created 1\n@@up 1\n@@ver 2.9.0\n@@ip 192.168.1.50\n@@ok\n')
res = good.plugin({'host': '192.168.1.50'}, 'collector', 'install', dict(body, _progress=lambda s: None))
info = res['info']
ok('установка: панель, пароль, площадка, версия', res['ok'] and info['url'] == 'http://192.168.1.50:9998' and info['password'] == c['password'] and info['siteId'] == site['id'] and info['version'] == '2.9.0', res)
ok('в журнале нет ни пароля, ни ключа', 'pw' not in json.dumps(res['log']) and c['password'] not in json.dumps(res['log']) and c['token'] not in json.dumps(res['log']))
res = Fake('@@ver 2.9.0\n@@ip 192.168.1.50\n@@ok\n').plugin({'host': 'h', 'panelInfo': {'collector': {'password': 'old-one'}}}, 'collector', 'install', dict(body, _progress=lambda s: None))
ok('повторная установка: прежний пароль администратора сохранён', res['info']['password'] == 'old-one', res['info'])
for bad_reply in ('@@fail нужен вход под root\n', '— пакеты\n@@fail не удалось скачать с главной панели\n', 'ничего\n'):
    try:
        Fake(bad_reply).plugin({'host': 'h'}, 'collector', 'install', dict(body, _progress=lambda s: None))
        ok('ошибка сервера понятна: ' + bad_reply[:25].strip(), False)
    except DriverError as e:
        ok('ошибка сервера понятна: ' + bad_reply[:25].strip(), len(str(e)) > 5, e)
try:
    Fake('@@ok').plugin({'host': 'h'}, 'collector', 'install', {'_progress': lambda s: None})
    ok('без подготовки установка отказывает', False)
except DriverError:
    ok('без подготовки установка отказывает', True)
rm = Fake('— служба удалена\n@@ok\n').plugin({'host': 'h'}, 'collector', 'remove', {'_site': 'abc123', '_progress': lambda s: None})
ok('удаление: сообщает, какую площадку убрать', rm['removed'] == 'collector' and rm['removeSite'] == 'abc123')

card = Fake('@@os Debian GNU/Linux 13\n@@uid 0\n@@mem 3800\n@@free 51000\n@@systemd\n@@python 3.13\n@@apt\n@@end\n')._collector_card({})
ok('карточка: проверки зелёные, не установлено', card['id'] == 'collector' and not card['installed'] and all(x['ok'] for x in card['checks']) and card['defaultPort'] == 9998, card)
card = Fake('@@os Alpine\n@@uid 1000\n@@mem 200\n@@free 10\n@@end\n')._collector_card({})
ok('карточка: не root, мало памяти, нет systemd — красные пункты', [x['ok'] for x in card['checks'][:4]] == [False, False, False, False], card['checks'])

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
