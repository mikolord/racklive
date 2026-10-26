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

print('\nВСЁ OK' if ok else '\nЕСТЬ ОШИБКИ')
sys.exit(0 if ok else 1)
