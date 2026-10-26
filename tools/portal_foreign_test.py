"""A captive portal set up by hand (OpenNDS on, no Rack Live profile): it is found and shown, and the plugin refuses to install over it."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import portal
from rackd.drivers.openwrt import OpenWrt
from rackd.util import DriverError

ok = True


def check(name, cond):
    global ok
    print(('  ok   ' if cond else '  FAIL ') + name)
    ok = ok and bool(cond)


# what the status script printed on the real router with a hand-made portal («Mira», own theme, 24 h)
MANUAL = '''@@model MikroTik RouterBOARD 2011UiAS-2HnD
@@rel 25.12.1
@@pm apk
@@free 61000
@@lan lan1 lan2 lan3 lan4
@@wan eth0.2
@@radio radio0 2g
@@nds 10.3.1-r1 1 1
@@foreign Mira|theme_mira.sh|1440
@@clients 3
@@wanip 192.168.8.10/24
@@lanip 192.168.88.1
@@end
'''
OURS = MANUAL.replace('@@foreign Mira|theme_mira.sh|1440\n', '@@profile {"role": "gateway", "portal": true, "guestSsid": "Guest", "mainSsid": "Home"}\n')

hw = portal.parse_status(MANUAL)
check('найден ручной портал', hw['foreign'] == {'name': 'Mira', 'theme': 'theme_mira.sh', 'hours': 24.0})
check('профиля Rack Live нет', hw['profile'] is None)
check('наш портал не считается ручным', portal.parse_status(OURS)['foreign'] is None and portal.parse_status(OURS)['profile'] is not None)
check('нет портала — нет и ручного', portal.parse_status(MANUAL.replace('@@foreign Mira|theme_mira.sh|1440\n', '').replace('@@nds 10.3.1-r1 1 1', '@@nds - 0 0'))['foreign'] is None)
check('название с пробелами и без темы', portal.parse_status('@@foreign Гостевой Wi-Fi||\n')['foreign'] == {'name': 'Гостевой Wi-Fi', 'theme': '', 'hours': None})
check('скрипт ищет ручной портал только без профиля', '@@foreign' in portal.STATUS and '[ ! -f /etc/rl-portal/profile.json ]' in portal.STATUS)

card = OpenWrt._portal_card(hw)
check('карточка: не установлен нами', card['installed'] is False)
check('карточка: описание найденного', card['foreign']['name'] == 'Mira' and 'настроенный вручную' in card['status'] and 'гостей: 3' in card['status'])
check('карточка: установка заблокирована проверкой', any(not c['ok'] and not c.get('optional') for c in card['checks']))
check('карточка нашего портала без foreign', 'foreign' not in OpenWrt._portal_card(portal.parse_status(OURS)))

# the install button is refused on the server too, and nothing is written to the router
sent = []
drv = OpenWrt()
drv._ssh = lambda cfg, script, timeout=30: (sent.append(script), MANUAL)[1]
try:
    drv._portal({'host': '192.168.8.10', 'username': 'root', 'password': 'x'}, 'install', {'profile': {}})
    check('установка поверх ручного портала отказана', False)
except DriverError as e:
    check('установка поверх ручного портала отказана', 'настроенный вручную' in str(e))
check('на роутер ничего не записано (только чтение статуса)', len(sent) == 1 and sent[0] == portal.STATUS)

# the old switch (swconfig) of the MikroTik RB2011: ports come from board.json/swconfig, the plugin builds the guest VLAN itself
SW = '''@@swconfig 1
@@swp s0p2 switch0 2 0 eth0 1 up 1000
@@swp s0p3 switch0 3 0 eth0 1 down 0
@@swp s0p4 switch0 4 0 eth0 1 down 0
@@swp s0p5 switch0 5 0 eth0 1 down 0
@@swp s0p6 switch0 6 0 eth0 1 up 1000
@@swp s1p1 switch1 1 0 eth1 1 down 0
@@swp s1p2 switch1 2 0 eth1 1 down 0
'''
OLD_SWITCH = MANUAL.replace('@@foreign Mira|theme_mira.sh|1440\n', SW).replace('@@nds 10.3.1-r1 1 1', '@@nds - 0 0').replace('@@wan eth0.2', '@@wan eth0.2\n@@via eth0.2')
hw2 = portal.parse_status(OLD_SWITCH)
check('старый коммутатор распознан', hw2['swconfig'] is True and hw2['foreign'] is None and portal.parse_status(OURS)['swconfig'] is False)
check('порты — гнёзда коммутатора', hw2['lan'] == ['s0p2', 's0p3', 's0p4', 's0p5', 's0p6', 's1p1', 's1p2'] and hw2['swports']['s0p2']['eth'] == 'eth0' and hw2['swports']['s0p2']['cpu'] == 0)
check('связь по портам видна', hw2['links']['s0p2'] == {'up': True, 'speed': 1000} and hw2['links']['s0p3']['up'] is False)
check('скрипт ищет switch_vlan и порты', '=switch_vlan' in portal.STATUS and '@@swp' in portal.STATUS)
card2 = OpenWrt._portal_card(hw2)
check('карточка: установка разрешена (все проверки пройдены)', all(c['ok'] or c.get('optional') for c in card2['checks']))
check('карточка: про коммутатор сказано, мешающих проверок нет', any('Старый коммутатор' in c['label'] and c['ok'] for c in card2['checks']) and not any('заходит на роутер через' in c['label'] for c in card2['checks']))
card3 = OpenWrt._portal_card(portal.parse_status(OLD_SWITCH.replace('@@via eth0.2', '@@via br-lan')))
check('карточка: через LAN управлять нельзя', any('заходит на роутер через' in c['label'] and not c['ok'] for c in card3['checks']))

HWF = dict(hw2, radios=[{'name': 'radio0', 'band': '2g'}], wan='eth0.2', wanip='192.168.8.10/24')
PROF = portal.validate(dict(mainSsid='Mira-Router', mainKey='long-enough-key', guestSsid='Mira Guest', login='click', vlan=10,
                            ports={'s0p2': 'guest'}), HWF)
check('профиль принят, порт s0p2 гостевой', PROF['ports']['s0p2'] == 'guest' and PROF['ports']['s0p3'] == 'main' and PROF['ports']['s1p1'] == 'main')
S = portal.apply_script(PROF, HWF, 'AAAA', 'http://192.168.1.3:9998', 'tok')
check('swconfig: гостевой VLAN на switch0 (порт 2 без тега + CPU с тегом)', "uci set network.rl_vg_switch0=switch_vlan" in S and "network.rl_vg_switch0.vlan=10" in S and "network.rl_vg_switch0.ports='2 0t'" in S)
check('swconfig: у switch1 гостевого VLAN нет', 'rl_vg_switch1' not in S)
check('swconfig: основной VLAN без гостевого порта', "ports='3 4 5 6 0t'" in S and "ports='1 2 0t'" in S)
check('swconfig: гостевой мост br-guest из eth0.10', "network.rl_brg.name=br-guest" in S and "add_list network.rl_brg.ports='eth0.10'" in S)
check('swconfig: гостевая сеть и портал на br-guest', 'network.rl_guest.device=br-guest' in S and 'gatewayinterface=br-guest' in S and 'network.lan.device=br-lan;' in S)
check('swconfig: нет DSA-команд', 'bridge-vlan' not in S and 'br-lan.1' not in S)
check('swconfig: WAN-VLAN (vlan 2) не трогаем', "= \"2\"" not in S and 'eth0.2' not in S.split('Записываю настройки сети', 1)[1].split('uci set network.wan.device', 1)[0])
check('откат и проверка работают для обоих типов', 'rl-rollback.sh' in S and 'network.rl_guest.device' in portal.VERIFY and 'rl_vg.vlan' not in portal.VERIFY)

# the same profile on a router with the modern bridge (DSA) is built as before
HWD = dict(HWF, swconfig=False, swports={}, lan=['lan1', 'lan2', 'lan3', 'lan4'])
PD = portal.validate(dict(mainSsid='Home', mainKey='long-enough-key', guestSsid='Guest', login='click', vlan=10, ports={'lan4': 'guest'}), HWD)
SD = portal.apply_script(PD, HWD, 'AAAA', 'http://192.168.1.3:9998', 'tok')
check('DSA: всё как раньше (bridge-vlan, br-lan.1, br-lan.10)', 'bridge-vlan' in SD and 'network.lan.device=br-lan.1;' in SD and 'network.rl_guest.device=br-lan.10' in SD and 'gatewayinterface=br-lan.10' in SD and 'br-guest' not in SD)

# one network only: no main Wi-Fi on the router, the guest network is called Mira_5/1 (the same name the Keenetic access points broadcast)
PN = portal.validate(dict(mainWifi=False, guestSsid='Mira_5/1', login='click', vlan=10, guest='192.168.88.1/24', ports={'s0p2': 'guest'}), HWF)
check('без основной Wi-Fi: профиль принят без её названия и пароля', PN['mainWifi'] is False and PN['guestSsid'] == 'Mira_5/1' and PN['guest'] == '192.168.88.1/24')
SN = portal.apply_script(PN, HWF, 'AAAA', 'http://192.168.1.3:9998', 'tok')
check('без основной Wi-Fi: основная сеть Wi-Fi не создаётся', 'rl_main_' not in SN and 'rl_guest_2g.ssid=' in SN and "ssid='Mira_5/1'" in SN)
check('без основной Wi-Fi: гостевая в гостевой сети', 'rl_guest_2g.network=rl_guest' in SN and 'rl_guest_2g.encryption=none' in SN)
check('с основной Wi-Fi: как раньше', 'rl_main_2g' in S and PROF['mainWifi'] is True)
try:
    portal.validate(dict(mainWifi=True, mainSsid='', guestSsid='Guest', ports={'s0p2': 'guest'}), HWF); check('основная Wi-Fi включена — название обязательно', False)
except ValueError:
    check('основная Wi-Fi включена — название обязательно', True)

# login on a slow router (MikroTik, 26.10.2026): the page goes first, the sign-in a moment later; repeats are not signed in again;
# a fast binauth instead of the stock binauth_log.sh; never «continue» to the portal itself or to a phone's internet check
T = portal.theme_script()
check('тема: сначала страница, вход в фоне', '( sleep 1; auth_log;' in T and T.index('( sleep 1; auth_log;') < T.index('rl_page done.html\n}'))
check('тема: повторный запрос не входит заново', '/tmp/rl-auth' in T and '-lt 120' in T)
check('тема: кнопка показывает нажатие и не жмётся дважды', 'data-sent' in T and 'Подключаем…' in T)
check('тема: после входа не на служебные адреса', '*status.client*|*:2050*|*captive.apple.com*' in T)
check('быстрый binauth при установке и при смене входа', portal.BINAUTH in S and 'binauth_rl.sh' in S and portal.BINAUTH in portal.login_script(PN))

# shell syntax of the whole script (if a POSIX shell is around)
import shutil, subprocess, tempfile
sh = shutil.which('sh') or next((p for p in (r'C:\Users\Admin\network-tools\bin\git\usr\bin\sh.exe', r'C:\Program Files\Git\usr\bin\sh.exe') if os.path.exists(p)), None)
if sh:
    for name, script in (('swconfig', S), ('swconfig без основной Wi-Fi', SN), ('DSA', SD), ('тема входа', T), ('смена входа', portal.login_script(PN))):
        with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False, newline='\n', encoding='utf-8') as tf:
            tf.write(script)
        r = subprocess.run([sh, '-n', tf.name], capture_output=True, text=True)
        os.unlink(tf.name)
        check('синтаксис скрипта установки (' + name + ')', r.returncode == 0)
        if r.returncode:
            print(r.stderr[:400])

print('\nВСЁ OK' if ok else '\nЕСТЬ ОШИБКИ')
sys.exit(0 if ok else 1)