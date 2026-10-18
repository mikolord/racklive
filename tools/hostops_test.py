"""«Режим разработчика»: every script is valid shell, parsers on realistic output, the checks of typed values, keyfiles (a password never in plain text in a script), where the commands run.
Run: python tools/hostops_test.py"""
import base64, os, re, shutil, subprocess, sys, tempfile, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import hostops as h

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
    ok('sh -n: ' + name, r.returncode == 0, r.stderr)


PSK = 'Secret-pass_123'
for name, sc in (('status', h.STATUS), ('wifi status', h.WIFI_STATUS), ('ntp', h.NTP_SCRIPT), ('zones', h.ZONES_SCRIPT), ('check', h.CHECK_SCRIPT), ('upgrade', h.UPGRADE_SCRIPT),
                 ('docker', h.DOCKER_SCRIPT), ('reboot', h.REBOOT_SCRIPT), ('ap off', h.AP_OFF_SCRIPT), ('ap forget', h.AP_FORGET_SCRIPT), ('timezone', h.tz_script('Europe/Moscow')),
                 ('scan', h.scan_script('wlan0')), ('forget', h.forget_script('rl-wifi-Office-1a2f')), ('drivers', h.drivers_script(['firmware-iwlwifi', 'linux-firmware'])),
                 ('ap on', h.ap_on_script('wlp3s0', 'ReckController', PSK, '10.77.0.1/24')), ('connect', h.connect_script('wlp3s0', 'Дом "5G"', PSK)), ('connect open', h.connect_script('wlan0', 'Cafe', ''))):
    syntax(name, sc)

# parsers
st = h.parse_status('@@os Debian GNU/Linux 13 (trixie)\n@@id debian\n@@uid 0\n@@systemd\n@@apt\n@@tz Europe/Moscow\n@@now 2026-10-17 22:10:00\n@@ntp yes\n@@uptime 4200\n@@reboot\n@@upgradable 7\n@@docker 27.5.1\n'
                    '@@dpkg docker.io 27.5.1+dfsg4-1\n@@dpkg containerd 1.7.24\n@@end\n')
ok('статус: система, пояс, обновления, Docker', st['id'] == 'debian' and st['tz'] == 'Europe/Moscow' and st['upgradable'] == '7' and 'reboot' in st and [d['name'] for d in st['dpkg']] == ['docker.io', 'containerd'], st)

SSID_BYTES = ';'.join(str(b) for b in 'ReckController'.encode()) + ';'
W = ('@@nm active\n@@if wlp3s0|00:11:22:33:44:55|iwlwifi|up\n@@apmodes 2\n@@iw 1\n@@blocked 0\n@@pci 8086 24fb 0000:03:00.0\n@@usb 0bda 8176 802.11n WLAN Adapter\n@@usb 1d6b 0002 xHCI Host Controller\n'
     '@@pcitext 03:00.0 Network controller [0280]: Intel Corporation Wireless 3168 [8086:24fb]\n@@defdev enp2s0\n@@route 192.168.1.0/24 enp2s0\n@@route 10.77.0.0/24 wlp3s0\n'
     '@@con Wired connection 1:802-3-ethernet:enp2s0:activated\n@@con rl-hotspot:802-11-wireless:wlp3s0:activated\n'
     f'@@prof rl-hotspot|ap|{SSID_BYTES}|10.77.0.1/24|wlp3s0\n@@prof rl-wifi-Office-1a2f|infrastructure|Office||wlp3s0\n@@ip wlp3s0 10.77.0.1/24\n@@stations wlp3s0 2\n@@end\n')
w = h.parse_wifi(W)
ok('Wi-Fi: адаптер, драйвер, адрес, подключённые', w['interfaces'] == [{'name': 'wlp3s0', 'mac': '00:11:22:33:44:55', 'driver': 'iwlwifi', 'state': 'up', 'ip': '10.77.0.1/24', 'stations': 2}], w['interfaces'])
ok('Wi-Fi: точка включена, название раскодировано из байтов, адрес', w['hotspot']['on'] and w['hotspot']['ssid'] == 'ReckController' and w['hotspot']['address'] == '10.77.0.1/24' and w['hotspot']['iface'] == 'wlp3s0', w['hotspot'])
ok('Wi-Fi: сохранённая сеть в списке, точка в нём не дублируется', [p['id'] for p in w['profiles']] == ['rl-wifi-Office-1a2f'] and not w['profiles'][0]['active'], w['profiles'])
ok('Wi-Fi: чипы (Intel по PCI, Realtek-ключ по USB; шины и хабы не берём) и их прошивки', [(c['vendorName'], c['package']) for c in w['chips']] == [('Intel', 'firmware-iwlwifi'), ('Realtek', 'firmware-realtek')], w['chips'])
ok('Wi-Fi: AP поддерживается, маршруты с адаптерами, маршрут по умолчанию', w['apCapable'] and w['routes'][1] == {'net': '10.77.0.0/24', 'dev': 'wlp3s0'} and w['defaultDev'] == 'enp2s0')

nets = h.parse_scan('*:Office:78:WPA2:6\n :Guest\\:5G:52:WPA2 WPA3:36\n:Cafe:31:--:1\n:Office:40:WPA2:11\n::99::1\n')
ok('поиск сетей: текущая первой, дубли по названию схлопнуты, \\: разобрано, открытая без защиты',
   [n['ssid'] for n in nets] == ['Office', 'Guest:5G', 'Cafe'] and nets[0]['current'] and nets[0]['signal'] == 78 and nets[2]['security'] == '' and nets[1]['security'] == 'WPA2 WPA3', nets)

# typed values
for good in ('wlan0', 'wlp3s0', 'wlx00e04c'):
    try:
        ok('адаптер принят: ' + good, h.check_iface(good) == good)
    except ValueError:
        ok('адаптер принят: ' + good, False)
for bad in ('', 'wlan0; reboot', '../x', 'a b', 'x' * 16, '$(id)'):
    try:
        h.check_iface(bad); ok('адаптер отклонён: ' + repr(bad), False)
    except ValueError:
        ok('адаптер отклонён: ' + repr(bad), True)
for bad in ('', 'x' * 33, 'a\nb'):
    try:
        h.check_ssid(bad); ok('название сети отклонено: ' + repr(bad[:12]), False)
    except ValueError:
        ok('название сети отклонено: ' + repr(bad[:12]), True)
ok('название по-русски принято', h.check_ssid('Дом 5G') == 'Дом 5G')
for bad in ('short', 'x' * 64, ' leading-space1', 'trailing-space1 ', 'tab\tpassword', 'пароль-кириллица'):
    try:
        h.check_psk(bad); ok('пароль Wi-Fi отклонён: ' + repr(bad[:14]), False)
    except ValueError:
        ok('пароль Wi-Fi отклонён: ' + repr(bad[:14]), True)
ok('пустой пароль для открытой сети разрешён только по просьбе', h.check_psk('', allow_empty=True) == '')
for bad in ('', '../../etc/passwd', 'Europe/Moscow; id', 'Europe/Mo scow'):
    try:
        h.check_tz(bad); ok('часовой пояс отклонён: ' + repr(bad), False)
    except ValueError:
        ok('часовой пояс отклонён: ' + repr(bad), True)
ok('часовые пояса принимаются', all(h.check_tz(z) == z for z in ('Europe/Moscow', 'Asia/Tbilisi', 'America/Argentina/Buenos_Aires', 'UTC', 'Etc/GMT+3')))

ok('адрес точки принят и нормализован', h.check_address('10.77.0.1/24') == '10.77.0.1/24' and h.check_address(' 192.168.50.1/24 ') == '192.168.50.1/24')
for bad, routes in (('10.77.0.1/24', ['10.77.0.0/24']), ('192.168.1.1/24', ['192.168.1.0/24']), ('10.0.0.1/24', ['10.0.0.0/8']), ('8.8.8.1/24', []), ('10.77.0.0/24', []),
                    ('10.77.0.255/24', []), ('10.77.0.1/31', []), ('10.0.0.1/8', []), ('nonsense', []), ('fe80::1/64', [])):
    try:
        h.check_address(bad, routes); ok('адрес точки отклонён: ' + bad + (' при ' + routes[0] if routes else ''), False)
    except ValueError:
        ok('адрес точки отклонён: ' + bad + (' при ' + routes[0] if routes else ''), True)
ok('подбор свободной сети: первая свободная, занятые обходит', h.suggest_address([]) == '10.77.0.1/24' and h.suggest_address(['10.77.0.0/24']) == '10.78.0.1/24' and h.suggest_address(['10.0.0.0/8']) == h.DEFAULT_ADDRESS)
ok('собственная сеть адаптера не мешает перенастроить точку', h.nets_of([{'net': '10.77.0.0/24', 'dev': 'wlp3s0'}, {'net': '192.168.1.0/24', 'dev': 'enp2s0'}], 'wlp3s0') == ['192.168.1.0/24'])

# firmware
ok('Debian: прошивка под чип', h.firmware_packages([{'vendor': '8086'}], 'debian') == ['firmware-iwlwifi'] and h.firmware_packages([{'vendor': '8086'}, {'vendor': '0bda'}, {'vendor': '10ec'}], 'debian') == ['firmware-iwlwifi', 'firmware-realtek'])
ok('Ubuntu и родственные: linux-firmware', h.firmware_packages([{'vendor': '8086'}], 'ubuntu') == ['linux-firmware'] and h.firmware_packages([], 'raspbian') == ['linux-firmware'])
ok('Debian без опознанного чипа: набор на все случаи', 'firmware-iwlwifi' in h.firmware_packages([], 'debian') and len(h.firmware_packages([], 'debian')) >= 4)
ok('в установку не попадает чужое имя пакета', 'bad;id' not in h.drivers_script(['firmware-iwlwifi', 'bad;id', 'x y']))

# keyfiles: secrets only inside the base64 body, never in plain text
for name, script in (('точка', h.ap_on_script('wlp3s0', 'ReckController', PSK, '10.77.0.1/24')), ('клиент', h.connect_script('wlp3s0', 'Дом "5G"', PSK))):
    ok(f'{name}: пароль не лежит в тексте скрипта', PSK not in script)
    m = re.search(r"printf %s '?([A-Za-z0-9+/=]+)'? \| base64 -d", script)
    kf = base64.b64decode(m.group(1)).decode() if m else ''
    ok(f'{name}: keyfile раскодируется и содержит пароль', f'psk={PSK}' in kf, kf)
ap = base64.b64decode(re.search(r"printf %s '?([A-Za-z0-9+/=]+)'?", h.ap_on_script('wlp3s0', 'ReckController', PSK, '10.77.0.1/24')).group(1)).decode()
ok('keyfile точки: режим AP, раздача адресов, адрес, название байтами, автозапуск', 'mode=ap' in ap and 'method=shared' in ap and 'address1=10.77.0.1/24' in ap and f'ssid={SSID_BYTES}' in ap and 'autoconnect=true' in ap and 'key-mgmt=wpa-psk' in ap, ap)
ok('keyfile: обратная косая в пароле экранирована', 'psk=ab\\\\cd-12345' in h.hotspot_keyfile('wlan0', 'X', 'ab\\cd-12345', '10.77.0.1/24'))
cl = base64.b64decode(re.search(r"printf %s '?([A-Za-z0-9+/=]+)'?", h.connect_script('wlan0', 'Cafe', '')).group(1)).decode()
ok('keyfile открытой сети: без блока безопасности', 'wifi-security' not in cl and 'mode=infrastructure' in cl, cl)
ok('кириллица в названии сети идёт байтами UTF-8', 'ssid=' + ';'.join(str(b) for b in 'Дом'.encode()) + ';' in h.client_keyfile('x', 'wlan0', 'Дом', PSK))
ok('профиль сети: имя стабильно между запусками и без чужих символов', h.client_profile_id('Дом 5G') == h.client_profile_id('Дом 5G') and re.match(r'^rl-wifi-[A-Za-z0-9\-]+$', h.client_profile_id('Дом "5G";')))
for bad in ('', 'a;b', 'x y', h.HOTSPOT, '../x'):
    try:
        h.forget_script(bad); ok('забыть сеть: отклонено ' + repr(bad), False)
    except ValueError:
        ok('забыть сеть: отклонено ' + repr(bad), True)

# results of scripts
ok('результат: успех', h._result('— шаг\n@@ok\n') == (True, '', ['— шаг']))
ok('результат: отказ с причиной', h._result('— шаг\n@@fail нужны права root\n') == (False, 'нужны права root', ['— шаг']))
ok('результат: без подтверждения — неуспех', h._result('что-то\n')[0] is False)
m = h.parse_marks('@@count 3\n@@pkg curl/stable 8.1 amd64 [upgradable from: 8.0]\n@@pkg tzdata/stable 2025b all [upgradable from: 2025a]\n@@reboot\n@@ok\n')
ok('метки: число, имена пакетов, перезагрузка', m['count'] == '3' and m['pkgs'] == ['curl', 'tzdata'] and 'reboot' in m, m)

# where commands run
class FakeNet:
    def __init__(self, dev):
        self.dev = dev

    def find_host(self):
        return self.dev


app = types.SimpleNamespace(hostnet=FakeNet({'id': 'x', 'driver': 'ssh', 'name': 'Мини-ПК'}))
kind, d = h.Host(app).target()
ok('Rack Live не root на Linux (здесь Windows): команды идут по SSH на найденное устройство', kind == 'ssh' and d['id'] == 'x', (kind, d))
kind, why = h.Host(types.SimpleNamespace(hostnet=FakeNet({'id': 's', 'driver': 'synology', 'name': 'NAS'}))).target()
ok('на NAS (Synology) система не трогается и сказано почему', kind is None and 'NAS' in why and 'Debian' in why, why)
kind, why = h.Host(types.SimpleNamespace(hostnet=FakeNet(None))).target()
ok('машина не добавлена — подсказка, что сделать', kind is None and 'ReckController OS' in why, why)
ok('демо: ничего настоящего', h.Host(app, demo=True).target()[0] == 'demo' and h.Host(app, demo=True).status()['mode'] == 'demo' and h.Host(app, demo=True).wifi()['hotspot']['on'])
ok('локальный запуск возможен только на Linux под root без контейнера', h.local_ok() is False or sys.platform.startswith('linux'))

# VPN (AmneziaWG)
AWG = ('[Interface]\nPrivateKey = PRIVATE-KEY-XYZ\nAddress = 10.8.0.2/32\nDNS = 1.1.1.1\nJc = 4\nJmin = 40\nJmax = 70\nS1 = 0\nS2 = 0\nH1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n'
       '[Peer]\nPublicKey = PUB\nEndpoint = 203.0.113.10:51820\nAllowedIPs = 0.0.0.0/0\n')
for name, sc in (('vpn status', h.AWG_STATUS), ('vpn install', h.awg_install_script()), ('vpn conf', h.awg_conf_script(AWG)), ('vpn conf без DNS', h.awg_conf_script(AWG, False)),
                 ('vpn on', h.AWG_ON_SCRIPT), ('vpn off', h.AWG_OFF_SCRIPT), ('vpn forget', h.AWG_FORGET_SCRIPT)):
    syntax(name, sc)
ok('VPN: приватный ключ не лежит в тексте скрипта', 'PRIVATE-KEY-XYZ' not in h.awg_conf_script(AWG))
ok('VPN: DNS из конфига убирается по просьбе', 'DNS' not in h.awg_conf_text(AWG, False)[0] and 'DNS' in h.awg_conf_text(AWG)[0])
ok('VPN: для DNS ставится openresolv только когда нужен', 'openresolv' in h.awg_conf_script(AWG) and 'openresolv' not in h.awg_conf_script(AWG, False))
for bad in ('', 'просто текст', '[Interface]\nAddress = 10.0.0.2/32\n[Peer]\nEndpoint = 1.2.3.4:1\n'):
    try:
        h.awg_conf_text(bad); ok('VPN: неправильный конфиг отклонён: ' + repr(bad[:20]), False)
    except ValueError:
        ok('VPN: неправильный конфиг отклонён: ' + repr(bad[:20]), True)
v = h.parse_awg('@@awg amneziawg-tools v1.0\n@@quick 1\n@@go 1\n@@conf 1\n@@enabled enabled\n@@active active\n@@up 1\n@@peer PUB\t(none)\t203.0.113.10:51820\t0.0.0.0/0\t1792300000\t1000\t2000\t25\n@@end\n')
ok('VPN: статус — установлен, включён, сервер, связь, трафик', v['installed'] and v['enabled'] and v['active'] and v['impl'] == 'amneziawg-go' and v['peer'] == {'endpoint': '203.0.113.10:51820', 'handshake': 1792300000, 'rx': 1000, 'tx': 2000}, v)
v = h.parse_awg('@@awg \n@@quick \n@@go \n@@enabled disabled\n@@active inactive\n@@end\n')
ok('VPN: не установлен — так и сказано', not v['installed'] and not v['hasConf'] and not v['enabled'] and v['peer'] is None, v)
ok('VPN: служба поднимается после перезагрузки, при ошибке выключается обратно', 'systemctl enable awg-quick@awg0' in h.AWG_ON_SCRIPT and 'systemctl disable awg-quick@awg0' in h.AWG_ON_SCRIPT)
ok('VPN: программы берутся из официальных исходников Amnezia', 'https://github.com/amnezia-vpn/$1' in h.awg_install_script() and 'amneziawg-go' in h.awg_install_script())

# «Эта машина»: Rack Live on a Linux box as root adds that box itself, and its commands run here (no SSH to itself)
from rackd import server
from rackd.store import Store
from rackd.drivers.sshhost import SSHHost
real_ok, real_run = h.local_ok, h.run_local
try:
    h.local_ok = lambda: True
    ran = []
    h.run_local = lambda script, timeout=60, on_line=None: ran.append(script) or '@@ok\n'
    a = types.SimpleNamespace(store=Store(tempfile.mkdtemp()), hostnet=FakeNet(None))
    server.App.ensure_local_device(a)
    devs = a.store.cfg['devices']
    ok('«Эта машина» добавлена сама: сервер по SSH-драйверу, локальный, с именем машины', len(devs) == 1 and devs[0]['local'] and devs[0]['driver'] == 'ssh' and devs[0]['host'] == '127.0.0.1' and devs[0]['name'], devs)
    server.App.ensure_local_device(a)
    ok('второй раз не добавляется', len(a.store.cfg['devices']) == 1)
    b = types.SimpleNamespace(store=Store(tempfile.mkdtemp()), hostnet=FakeNet({'id': 'nas', 'driver': 'ssh'}))
    server.App.ensure_local_device(b)
    ok('если машина уже добавлена по своему адресу — дубля нет', b.store.cfg['devices'] == [])
    out = SSHHost()._run({'host': '127.0.0.1', 'local': True}, 'echo hi\n')
    ok('команды «Этой машины» идут здесь, без SSH', out == '@@ok\n' and ran == ['echo hi\n'])
    args, env, kf = SSHHost().interactive_args({'host': '127.0.0.1', 'local': True})
    ok('терминал «Этой машины» — оболочка здесь, без SSH и без временных файлов', args[-1] == '-l' and 'ssh' not in ' '.join(args) and kf is None, args)
finally:
    h.local_ok, h.run_local = real_ok, real_run
saved_home = os.environ.pop('HOME', None)
try:
    env = h.local_env()
    ok('у локальных команд всегда есть HOME (служба systemd его не даёт) и обычный PATH', env.get('HOME') not in (None, '', '/') and '/usr/local/bin' in env['PATH'].split(':'), (env.get('HOME'), env.get('PATH')))
finally:
    if saved_home is not None:
        os.environ['HOME'] = saved_home
ok('служба сборщика получает HOME', 'HOME=/root' in __import__('rackd.collector_install', fromlist=['x']).install_script('http://x:1', 't' * 20, {'collector': {}}, 9998))
ok('на обычном сервере локальный флаг без root/Linux не срабатывает (идёт SSH)', not h.local_ok() or sys.platform.startswith('linux'))

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
