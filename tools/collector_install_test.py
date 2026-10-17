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
dev2 = {'id': 'mini', 'name': 'ReckController', 'driver': 'ssh', 'host': '192.168.1.21'}
n0 = len(app.sites.items)
b2 = server.App.collector_prepare(app, dev2, {'plugin': 'rcos', 'server': '', 'name': 'ReckController', 'tz': 'Europe/Moscow', 'ap': True}, 'install')
c2 = b2['_collector']
ok('без отправки данных: площадка не создаётся, сборщик на машине выключен', len(app.sites.items) == n0 and c2['siteId'] is None and c2['cfg']['collector'] == {'enabled': False, 'level': 'view'} and c2['cfg']['settings']['devMode'] is True, c2['cfg']['collector'])
ok('без отправки данных: ключ на скачивание одноразовый, адрес для скачивания найден сам', c2['token'] in app.pack_tokens and re.match(r'^http://[\d.]+:\d+$', c2['pack']), c2['pack'])
ok('ReckController OS: пароль точки придуман, если не задан', len(b2['_rcos']['password']) >= 8 and b2['_rcos']['ssid'] == 'ReckController')
b3 = server.App.collector_prepare(app, dev2, {'plugin': 'rcos', 'server': 'https://racklive.example.com', 'name': 'Сбойная'}, 'install')
b4 = server.App.collector_prepare(app, dev2, {'plugin': 'rcos', 'server': 'https://racklive.example.com', 'name': 'Сбойная'}, 'install')
ok('повтор после сбоя: площадка, которая ещё ни разу не отвечала, переиспользуется', b3['_collector']['siteId'] == b4['_collector']['siteId'] and sum(1 for s in app.sites.items if s['name'] == 'Сбойная') == 1)
class _NoReach(SSHHost):
    def __init__(self):
        self.ran = []

    def _run(self, cfg, script, timeout=30, remote='sh -s'):
        self.ran.append(script)
        return '@@fail машина не достаёт до этой панели\n'


fr0 = _NoReach()
try:
    fr0.plugin({'host': 'h'}, 'rcos', 'install', dict(b2, _progress=lambda s: None))
    ok('нет связи с панелью: остановка до любых изменений на машине', False)
except DriverError:
    ok('нет связи с панелью: остановка до любых изменений на машине', len(fr0.ran) == 1 and '/api/state' in fr0.ran[0] and 'timedatectl' not in fr0.ran[0])
syntax('проверка связи', ci.reach_script('http://192.168.1.3:9998'))
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

# ReckController OS: time zone → Wi-Fi drivers → our access point → the collector (whose config remembers the point) → the marker
from rackd import hostops
import base64


def wifi_reply(ifaces=True, default='enp2s0', ap=True):
    return ((f'@@nm active\n@@if wlp3s0|aa:bb:cc:dd:ee:ff|iwlwifi|up\n' if ifaces else '@@nm none\n') + f'@@apmodes {2 if ap else 0}\n@@iw 1\n@@pci 8086 24fb 0000:03:00.0\n@@defdev {default}\n'
            '@@route 192.168.1.0/24 enp2s0\n@@end\n')


class FakeR(SSHHost):
    def __init__(self, **kw):
        self.ran, self.kw = [], kw

    def _run(self, cfg, script, timeout=30, remote='sh -s'):
        self.ran.append(script)
        if script is hostops.WIFI_STATUS:
            return wifi_reply(**self.kw)
        if script is ci.STATUS:
            return '@@id debian\n@@end\n'
        return '@@created 1\n@@ver 2.9.0\n@@ip 192.168.1.50\n@@ok\n'


def rc_params(**over):
    cfg = ci.make_config('Мини-ПК', URL, TOKEN, 'pw-Secret-123', 'view', False, dev=True)
    p = {'_collector': {'url': URL, 'token': TOKEN, 'cfg': cfg, 'port': 9998, 'password': 'pw-Secret-123', 'siteId': 's1', 'siteName': 'Мини-ПК', 'level': 'view', 'insecure': False},
         '_rcos': dict({'tz': 'Europe/Moscow', 'ap': True, 'band': 'bg', 'ssid': 'ReckController', 'password': 'wifi-pass-12', 'address': ''}, **over), '_progress': lambda s: None}
    return p


fr = FakeR()
res = fr.plugin({'host': '192.168.1.50'}, 'rcos', 'install', rc_params())
joined = '\n'.join(fr.ran)
ok('ReckController OS: готово, есть панель и точка с постоянным адресом', res['ok'] and res['info']['rcos'] and res['info']['ap']['ssid'] == 'ReckController' and res['info']['ap']['url'] == 'http://10.77.0.1:9998' and not res['info']['warnings'], res)
ok('порядок: часовой пояс → драйверы → точка → сборщик → метка', [i for i, k in enumerate(('timedatectl set-timezone', 'network-manager', 'mode=ap' if False else 'rl-hotspot.nmconnection', 'racklive-installer', 'date > /etc/racklive/rcos')) if k in joined] == [0, 1, 2, 3, 4]
   and joined.index('timedatectl set-timezone') < joined.index('network-manager') < joined.index('rl-hotspot.nmconnection') < joined.index('racklive-installer') < joined.index('date > /etc/racklive/rcos'))
inst = next(s for s in fr.ran if 'racklive-installer' in s)
sent = json.loads(base64.b64decode(re.search(r"RL_CFG='?([A-Za-z0-9+/=]+)'?;", inst).group(1)))
ok('в конфиг новой машины ушли режим разработчика и точка (пароль точки там нужен, чтобы показать его в панели)', sent['settings'].get('devMode') is True and sent['dev']['ap']['ssid'] == 'ReckController' and sent['dev']['ap']['address'] == '10.77.0.1/24', sent)
ok('пароль точки не в тексте скриптов', 'wifi-pass-12' not in joined)
ok('прошивка под Intel-чип выбрана', 'firmware-iwlwifi' in joined)

res = FakeR(ifaces=False).plugin({'host': 'h'}, 'rcos', 'install', rc_params())
ok('нет Wi-Fi-адаптера: установка идёт дальше, точки нет, причина названа', res['ok'] and 'ap' not in res['info'] and any('адаптер' in w for w in res['info']['warnings']), res['info'])
res = FakeR(default='wlp3s0').plugin({'host': 'h'}, 'rcos', 'install', rc_params())
ok('связь машины идёт по Wi-Fi: точку не создаём, чтобы не отрезать её', res['ok'] and 'ap' not in res['info'] and any('связь' in w for w in res['info']['warnings']), res['info'])
res = FakeR(ap=False).plugin({'host': 'h'}, 'rcos', 'install', rc_params())
ok('адаптер без режима точки: честное замечание', res['ok'] and 'ap' not in res['info'] and any('AP' in w for w in res['info']['warnings']), res['info'])
res = FakeR().plugin({'host': 'h'}, 'rcos', 'install', rc_params(ap=False, tz=''))
ok('без точки и часового пояса: только драйверы и сборщик', res['ok'] and 'ap' not in res['info'] and not res['info']['warnings'], res['info'])
fr = FakeR()
fr.plugin({'host': 'h'}, 'rcos', 'remove', {'_site': 's1', '_progress': lambda s: None})
ok('удаление ReckController OS: точка, сборщик, метка', '\n'.join(fr.ran).index('rl-hotspot') < '\n'.join(fr.ran).index('systemctl disable') < '\n'.join(fr.ran).index('rm -f /etc/racklive/rcos'))
card = FakeR()._collector_card({}, True, ci.parse_status('@@os Debian\n@@uid 0\n@@mem 3800\n@@free 51000\n@@systemd\n@@python 3.13\n@@apt\n@@ver 2.9.0\n@@rcos 1\n@@wifi wlp3s0\n@@end\n'))
ok('карточка ReckController OS: установлена по метке, Wi-Fi-адаптер виден', card['id'] == 'rcos' and card['installed'] and card['checks'][-1]['ok'], card)
card = FakeR()._collector_card({}, True, ci.parse_status('@@os Debian\n@@uid 0\n@@mem 3800\n@@free 51000\n@@systemd\n@@apt\n@@ver 2.9.0\n@@end\n'))
ok('Rack Live стоит, но не как ReckController OS: карточка «не установлена»', card['id'] == 'rcos' and not card['installed'])

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
