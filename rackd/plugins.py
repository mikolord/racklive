"""Device plugins: guides and one-click installers that run on a device (Keenetic first).

A plugin is described here (what it is, for which drivers); the device driver implements
`plugins(cfg)` → status of each plugin and `plugin(cfg, plugin_id, op, params)` → {ok, log, ...}.
Shared helpers: the AmneziaWG/WireGuard .conf parser and the domain-list parser.
"""
import ipaddress, re

# AmneziaWG 3.x (защита заголовков): поля сверх 2.0 (S3/S4/I1-5). Встречаются у некоторых платных провайдеров,
# в официальных open-source amneziawg-tools/amneziawg-go их нет — такие строки роутер и ReckController не применяют.
AWG3_KEYS = ('headerprotectionkey', 'contentpaddingaddition', 'rekeyaftertime', 'rekeytimeout',
             'rejectaftertime', 'keepalivetimeout', 'maxhandshakeattempts', 'randomtrailers', 'disablecookies')

DNS_PRESETS = [
    {'id': 'cloudflare', 'label': 'Cloudflare', 'ip': '1.1.1.1'},
    {'id': 'quad9', 'label': 'Quad9', 'ip': '9.9.9.9'},
    {'id': 'google', 'label': 'Google', 'ip': '8.8.8.8'},
    {'id': 'adguard', 'label': 'AdGuard DNS', 'ip': '94.140.14.14'},
]

CATALOG = [
    {'id': 'entware', 'drivers': ['keenetic'], 'title': 'Entware (OPKG)', 'icon': 'box', 'kind': 'guide',
     'description': 'Репозиторий пакетов Linux на роутере. Нужен для HydraRoute Neo, AWG Manager и других дополнений. '
                    'Ставится вручную по инструкции — Rack Live проверит каждый шаг.'},
    {'id': 'awg', 'drivers': ['keenetic'], 'title': 'AWG native', 'icon': 'shield', 'kind': 'form',
     'description': 'Подключение AmneziaWG из файла .conf средствами самого роутера — без Entware. '
                    'По желанию сразу направит выбранные сайты через туннель.'},
    {'id': 'hydraroute', 'drivers': ['keenetic'], 'title': 'HydraRoute Neo', 'icon': 'globe2', 'kind': 'installer',
     'description': 'Удобная маршрутизация по доменам через туннели: списки сайтов, веб-панель. Нужен Entware.',
     'author': 'Ground-Zerro', 'home': 'https://github.com/Ground-Zerro/HydraRoute/tree/main/Neo'},
    {'id': 'awgmanager', 'drivers': ['keenetic'], 'title': 'AWG Manager', 'icon': 'shield', 'kind': 'installer',
     'description': 'Веб-панель для управления туннелями AmneziaWG на роутере (серверы, клиенты, подписки). Нужен Entware.',
     'author': 'hoaxisr', 'home': 'https://github.com/hoaxisr/awg-manager'},
]

# One-click installers: run over SSH inside Entware. Commands are the authors' official ones (see `home`);
# the script is downloaded to a file first (an empty download must not "succeed"), and runs with stdin closed
# so an interactive question can't swallow the rest of our script.
INSTALLERS = {
    'hydraroute': {
        'packages': ('hrneo', 'hrweb'), 'port': 2000, 'login': 'логин и пароль от роутера',
        'install': '''opkg update >/dev/null 2>&1
opkg install curl 2>&1 | tail -1
curl -fsSL "https://git.zerrolabs.org/Ground-Zerro/release/pages/keenetic/install-neo.sh" -o "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" || \\
  curl -fsSL "https://ground-zerro.github.io/release/keenetic/install-neo.sh" -o "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}"
[ -s "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" ] || { echo "@@fail не удалось скачать установщик HydraRoute Neo"; exit 0; }
sh "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" </dev/null 2>&1 | tail -40
rm -f "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}"''',
        'remove': 'neo stop 2>/dev/null; opkg remove hrweb hrneo 2>&1 | tail -5',
    },
    'awgmanager': {
        'packages': ('awg-manager',), 'port': 2222, 'login': 'учётная запись из первого входа в панель',
        'install': '''opkg update >/dev/null 2>&1
opkg install curl 2>&1 | tail -1
curl -fsSL https://raw.githubusercontent.com/hoaxisr/awg-manager/develop/scripts/install.sh -o "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" || \\
  curl -fsSL https://repo.hoaxisr.ru/install.sh -o "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}"
[ -s "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" ] || { echo "@@fail не удалось скачать установщик AWG Manager"; exit 0; }
sh "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" </dev/null 2>&1 | tail -40
rm -f "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}"''',
        'remove': 'opkg remove awg-manager 2>&1 | tail -5; rm -rf /opt/etc/awg-manager /opt/etc/awg-manager.pre-restore-*',
    },
}
# ───────── OpenWrt (over SSH; apk on 25.x, opkg before) ─────────
CATALOG += [
    {'id': 'forkop', 'drivers': ['openwrt'], 'title': 'Forkop', 'icon': 'globe2', 'kind': 'installer',
     'description': 'Маршрутизация сайтов через прокси/VPN на sing-box: форк Podkop с sing-box extended (XHTTP) и подписками. Настройка — в LuCI.',
     'author': 'ushan0v', 'home': 'https://github.com/ushan0v/forkop'},
    {'id': 'podkop', 'drivers': ['openwrt'], 'title': 'Podkop', 'icon': 'globe2', 'kind': 'installer',
     'description': 'Оригинальный Podkop: маршрутизация списков сайтов через прокси/VPN на sing-box. Настройка — в LuCI.',
     'author': 'itdoginfo', 'home': 'https://github.com/itdoginfo/podkop'},
    {'id': 'modem', 'drivers': ['openwrt'], 'title': 'USB-модем', 'icon': 'modem', 'kind': 'modem',
     'description': 'Драйверы для 4G/LTE-модемов. Rack Live посмотрит, что воткнуто, и подскажет вариант; не подошёл — удалите и поставьте другой.'},
]

OWRT_PKG = r'''PM=opkg; command -v apk >/dev/null 2>&1 && PM=apk
pv() { if [ $PM = apk ]; then apk list --installed 2>/dev/null | grep -o "^$1-[0-9][^ ]*" | head -1 | sed "s/^$1-//"; else opkg list-installed 2>/dev/null | awk -v p="$1" '$1==p{print $3}'; fi; }
padd() { if [ $PM = apk ]; then apk add "$@"; else opkg install "$@"; fi; }
pdel() { for p in "$@"; do [ -n "$(pv $p)" ] && { if [ $PM = apk ]; then apk del "$p"; else opkg remove "$p"; fi; }; done; }
pupd() { if [ $PM = apk ]; then apk update; else opkg update; fi; }
'''

# modem driver sets: profile → packages; `key` package tells the profile is installed; `drivers` = USB drivers that suggest it
MODEM_PROFILES = [
    {'id': 'hilink', 'title': 'Модем как сетевая карта (HiLink / RNDIS / NCM)',
     'note': 'Большинство современных USB-модемов (Huawei E3372h, ZTE MF8xx и т. п.): у модема свой веб-интерфейс, роутер видит его как сетевую карту.',
     'packages': ['kmod-usb-net-rndis', 'kmod-usb-net-cdc-ether', 'kmod-usb-net-cdc-ncm', 'kmod-usb-net-huawei-cdc-ncm', 'usb-modeswitch'],
     'key': 'kmod-usb-net-cdc-ether', 'drivers': ['rndis_host', 'cdc_ether', 'cdc_ncm', 'huawei_cdc_ncm'],
     'after': 'LuCI → Сеть → Интерфейсы → «Добавить»: протокол DHCP-клиент, устройство usb0 (или eth1), зона wan.'},
    {'id': 'mm', 'title': 'QMI / MBIM через ModemManager',
     'note': 'Модемы и M.2-модули в «модемном» режиме (Quectel, Sierra, Fibocom, Huawei в stick-режиме): ModemManager сам договаривается с модемом.',
     'packages': ['modemmanager', 'luci-proto-modemmanager', 'kmod-usb-net-qmi-wwan', 'kmod-usb-net-cdc-mbim', 'kmod-usb-serial-option', 'usb-modeswitch'],
     'key': 'modemmanager', 'drivers': ['qmi_wwan', 'cdc_mbim'], 'conflicts': ['qmi'],
     'after': 'LuCI → Сеть → Интерфейсы → «Добавить»: протокол ModemManager, выберите модем, укажите APN оператора.'},
    {'id': 'qmi', 'title': 'QMI напрямую (uqmi) — легче ModemManager',
     'note': 'Для QMI-модемов на роутерах с малой памятью: без ModemManager, только драйвер и uqmi.',
     'packages': ['uqmi', 'luci-proto-qmi', 'kmod-usb-net-qmi-wwan', 'kmod-usb-serial-option', 'usb-modeswitch'],
     'key': 'uqmi', 'drivers': ['qmi_wwan'], 'conflicts': ['mm'],
     'after': 'LuCI → Сеть → Интерфейсы → «Добавить»: протокол QMI Cellular, устройство /dev/cdc-wdm0, APN оператора.'},
    {'id': 'ppp', 'title': 'Старые 3G-модемы (PPP через последовательный порт)',
     'note': 'Модемы, которые видны только как /dev/ttyUSB*: старые 3G-свистки, часть недорогих 4G.',
     'packages': ['comgt', 'luci-proto-3g', 'kmod-usb-serial-option', 'kmod-usb-serial-wwan', 'usb-modeswitch'],
     'key': 'comgt', 'drivers': [],
     'after': 'LuCI → Сеть → Интерфейсы → «Добавить»: протокол UMTS/GPRS/EV-DO, устройство /dev/ttyUSB0 (или следующее), APN оператора.'},
]

OWRT_STATUS = OWRT_PKG + r'''. /etc/openwrt_release 2>/dev/null; echo "@@rel $DISTRIB_RELEASE"; echo "@@pm $PM"
echo "@@free $(df /overlay 2>/dev/null | awk 'NR==2{print $4}')"
echo "@@sb $(sing-box version 2>/dev/null | head -1)"
for p in forkop luci-app-forkop podkop luci-app-podkop sing-box sing-box-extended https-dns-proxy %s; do v=$(pv $p); [ -n "$v" ] && echo "@@pkg $p $v"; done
for d in /sys/bus/usb/devices/*; do [ -f $d/idVendor ] && [ "$(cat $d/bDeviceClass)" != "09" ] && echo "@@usb $(cat $d/idVendor):$(cat $d/idProduct) $(cat $d/manufacturer 2>/dev/null) $(cat $d/product 2>/dev/null)"; done
for d in rndis_host cdc_ether cdc_ncm huawei_cdc_ncm qmi_wwan cdc_mbim option; do ls /sys/bus/usb/drivers/$d 2>/dev/null | grep -q ':' && echo "@@drv $d"; done
for f in /dev/ttyUSB* /dev/cdc-wdm*; do [ -e "$f" ] && echo "@@dev $f"; done
echo @@end
''' % ' '.join(sorted({p['key'] for p in MODEM_PROFILES}))


def parse_owrt(out):
    s = {'pkgs': {}, 'usb': [], 'drv': [], 'dev': [], 'rel': '', 'pm': 'opkg', 'free': None, 'sb': ''}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k == '@@pkg':
            n, _, ver = v.partition(' ')
            s['pkgs'][n] = ver
        elif k in ('@@usb', '@@drv', '@@dev'):
            s[k[2:]].append(v.strip())
        elif k == '@@free':
            s['free'] = int(v) if v.strip().isdigit() else None
        elif k in ('@@rel', '@@pm', '@@sb'):
            s[k[2:]] = v.strip()
    return s


OWRT_INSTALLERS = {
    'forkop': {'packages': ('forkop', 'luci-app-forkop'), 'conflict': 'podkop', 'freeMB': 15, 'luci': 'admin/services/forkop',
               'install': OWRT_PKG + '''pupd >/dev/null 2>&1
wget -qO "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" https://raw.githubusercontent.com/ushan0v/forkop/main/install.sh 2>/dev/null
[ -s "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" ] || wget -qO "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" https://forkop.sourceforge.io/install.sh 2>/dev/null
[ -s "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" ] || { echo "@@fail не удалось скачать установщик Forkop"; exit 0; }
sh "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" </dev/null 2>&1 | tail -40
rm -f "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}"
if [ "$RL_EXT" = 1 ] && [ -x /usr/bin/forkop ]; then echo "→ sing-box extended (XHTTP)"; /usr/bin/forkop component_action sing_box install_extended </dev/null 2>&1 | tail -5; fi
''',
               'remove': OWRT_PKG + 'service forkop stop 2>/dev/null; pdel luci-i18n-forkop-ru luci-app-forkop forkop 2>&1 | tail -8'},
    'podkop': {'packages': ('podkop', 'luci-app-podkop'), 'conflict': 'forkop', 'freeMB': 25, 'luci': 'admin/services/podkop',
               # the official installer asks y/n questions in a loop (language, conflicting https-dns-proxy) — answer «y» to all
               'install': OWRT_PKG + '''pupd >/dev/null 2>&1
wget -qO "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" https://raw.githubusercontent.com/itdoginfo/podkop/refs/heads/main/install.sh 2>/dev/null
[ -s "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" ] || { echo "@@fail не удалось скачать установщик Podkop"; exit 0; }
T=""; command -v timeout >/dev/null 2>&1 && T="timeout 900"
(while :; do echo y; done) | $T sh "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}" 2>&1 | tail -40
rm -f "${RLI:=$(mktemp /tmp/rl-inst.XXXXXX)}"
''',
               'remove': OWRT_PKG + 'service podkop stop 2>/dev/null; pdel luci-i18n-podkop-ru luci-app-podkop podkop 2>&1 | tail -8'},
}


def modem_suggest(st):
    """Which profile fits the plugged-in modem (by bound USB drivers / device nodes)."""
    drv = set(st['drv'])
    if drv & {'qmi_wwan', 'cdc_mbim'}:
        return 'mm'
    if drv & {'rndis_host', 'cdc_ether', 'cdc_ncm', 'huawei_cdc_ncm'}:
        return 'hilink'
    if any(d.startswith('/dev/ttyUSB') for d in st['dev']):
        return 'ppp'
    return None


PKG_CHECK = 'echo @@pkgs; opkg list-installed 2>/dev/null | grep -E "^(hrneo|hrweb|awg-manager) "; echo @@arch; uname -m; echo @@end'


def parse_pkgs(out):
    """`opkg list-installed` lines → {package: version}."""
    sec = out.split('@@pkgs', 1)[-1].split('@@arch', 1)[0]
    return {m.group(1): m.group(2) for m in re.finditer(r'^(\S+) - (\S+)', sec, re.M)}

ENTWARE_INSTALLER = {
    'aarch64': 'https://bin.entware.net/aarch64-k3.10/installer/aarch64-installer.tar.gz',
    'mipsel': 'https://bin.entware.net/mipselsf-k3.4/installer/mipsel-installer.tar.gz',
    'mips': 'https://bin.entware.net/mipssf-k3.4/installer/mips-installer.tar.gz',
}


def for_driver(driver_id):
    return [dict(p) for p in CATALOG if driver_id in p['drivers']]


# ───────── AmneziaWG / WireGuard config ─────────
def parse_conf(text):
    """→ {iface:{...}, peer:{...}} with AWG obfuscation parameters; raises ValueError with a readable reason."""
    sec, cur = {'interface': {}, 'peer': {}}, None
    for raw in (text or '').splitlines():
        line = raw.split('#', 1)[0].strip() if not raw.strip().lower().startswith(('i1', 'i2', 'i3', 'i4', 'i5')) else raw.strip()
        if not line:
            continue
        m = re.match(r'\[(\w+)\]$', line)
        if m:
            cur = m.group(1).lower()
            if cur == 'peer' and sec['peer']:
                raise ValueError('в файле несколько серверов [Peer] — поддерживается один')
            continue
        if '=' in line and cur in sec:
            k, v = line.split('=', 1)
            sec[cur][k.strip().lower()] = v.strip()
    i, p = sec['interface'], sec['peer']
    if not i.get('privatekey') or not p.get('publickey') or not p.get('endpoint'):
        raise ValueError('это не конфиг WireGuard/AmneziaWG: нет PrivateKey, PublicKey или Endpoint')
    v4 = [a.strip() for a in i.get('address', '').split(',') if a.strip() and ':' not in a]
    if not v4:
        raise ValueError('в конфиге нет IPv4-адреса (Address)')
    addr = ipaddress.ip_interface(v4[0] if '/' in v4[0] else v4[0] + '/32')
    num = lambda k, d=0: int(i[k]) if re.fullmatch(r'\d+', i.get(k, '')) else d
    hval = lambda k: i.get(k, '').replace(' ', '') or '0'
    awg = {k: num(k) for k in ('jc', 'jmin', 'jmax', 's1', 's2', 's3', 's4')}
    awg.update({k: hval(k) for k in ('h1', 'h2', 'h3', 'h4')})
    awg.update({k: i.get(k, '') for k in ('i1', 'i2', 'i3', 'i4', 'i5')})
    is_awg = any(awg[k] for k in ('jc', 's1', 's2')) or any(awg[k] not in ('0', '1', '2', '3', '4') for k in ('h1', 'h2', 'h3', 'h4'))
    awg3 = any(k in i for k in AWG3_KEYS)
    allowed = [a.strip() for a in p.get('allowedips', '0.0.0.0/0').split(',') if a.strip()]
    host, _, port = p['endpoint'].rpartition(':')
    if not host or not port.isdigit():
        raise ValueError(f"не понял адрес сервера Endpoint = {p['endpoint']}")
    return {'privateKey': i['privatekey'], 'address': str(addr.ip), 'mask': str(addr.netmask), 'mtu': num('mtu', 1280) or 1280,
            'dns': i.get('dns', ''), 'awg': awg, 'isAwg': is_awg, 'awg3': awg3,
            'awg2': bool(awg['s3'] or awg['s4'] or any(awg[k] for k in ('i1', 'i2', 'i3', 'i4', 'i5'))
                         or any('-' in awg[k] for k in ('h1', 'h2', 'h3', 'h4'))),
            'peer': {'publicKey': p['publickey'], 'psk': p.get('presharedkey', ''), 'endpoint': f'{host.strip("[]")}:{port}',
                     'allowed': allowed, 'keepalive': int(p['persistentkeepalive']) if p.get('persistentkeepalive', '').isdigit() else 25},
            'ipv6': [a for a in i.get('address', '').split(',') if ':' in a]}


def conf_preview(c):
    """What the user sees before anything is created (no keys)."""
    full = any(a in ('0.0.0.0/0', '::/0') for a in c['peer']['allowed'])
    return {'server': c['peer']['endpoint'], 'address': c['address'], 'mtu': c['mtu'], 'dns': c['dns'],
            'type': 'AmneziaWG 3.x' if c.get('awg3') else 'AmneziaWG 2.0' if c['awg2'] else 'AmneziaWG' if c['isAwg'] else 'WireGuard',
            'fullTunnel': full, 'awg3': bool(c.get('awg3')),
            'allowed': c['peer']['allowed'][:8], 'psk': bool(c['peer']['psk']), 'ipv6Skipped': bool(c['ipv6'])}


# ───────── domains pasted by the user ─────────
def parse_domains(text):
    """Domains, IPs and subnets from free text (one per line, commas, URLs) → (items, skipped)."""
    items, skipped, seen = [], [], set()
    for tok in re.split(r'[\s,;]+', text or ''):
        t = tok.strip().strip('"\'').lower()
        if not t or t.startswith('#'):
            continue
        t = re.sub(r'^[a-z]+://', '', t).split('/', 1)[0] if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', t) else t
        t = t.split(':', 1)[0] if not re.match(r'^\d+\.\d+\.\d+\.\d+/\d+$', t) else t
        t = t.lstrip('*.').rstrip('.')
        ok = False
        try:
            ipaddress.ip_network(t, strict=False)
            ok = '.' in t
        except ValueError:
            ok = bool(re.fullmatch(r'(?:[a-z0-9а-яё](?:[a-z0-9а-яё-]{0,61}[a-z0-9а-яё])?\.)*[a-z0-9а-яё-]{1,63}', t)) and len(t) <= 253
        if ok and not t.isascii():
            try:
                t = t.encode('idna').decode()                   # дуэт-абх.рф → xn--...; the router wants punycode
            except UnicodeError:
                ok = False
        if not ok:
            skipped.append(tok)
        elif t not in seen:
            seen.add(t)
            items.append(t)
    return items, skipped
