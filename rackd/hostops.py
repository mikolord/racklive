"""«Режим разработчика»: system operations of the machine THIS Rack Live runs on — time zone, system packages and Docker, Wi-Fi (drivers, connecting to a network,
its own access point). Meant for a Linux box with systemd and apt (Debian, Ubuntu, Raspberry Pi OS) — a mini PC used as a portable network-diagnostics controller («ReckController OS»).

Where the commands run: right here when this process is root on a real Linux machine (the collector installed by the «ReckController OS» plugin runs exactly so),
otherwise over SSH on the server that is added as a device with this machine's address (driver «Сервер / VPS по SSH»). Docker on a NAS cannot touch its host this way: the
panel then says so in plain words instead of pretending.

Wi-Fi is done with NetworkManager: on a minimal Debian the cable stays under ifupdown (NetworkManager leaves it alone), so installing it cannot cut the SSH session.
Networks and the access point are written as keyfiles (/etc/NetworkManager/system-connections/*.nmconnection, mode 600), so a password never appears in a command line."""
import base64, hashlib, ipaddress, json, os, re, shlex, subprocess, sys, threading, time, uuid

HOTSPOT = 'rl-hotspot'
CLIENT_PREFIX = 'rl-wifi-'
DEFAULT_SSID = 'ReckController'
DEFAULT_ADDRESS = '10.77.0.1/24'                 # a rarely used private network: it must not collide with the networks of the people we visit
KEYFILES = '/etc/NetworkManager/system-connections'
IFACE_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,15}$')
TZ_RE = re.compile(r'^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+){0,2}$')

# vendor id (PCI / USB) → Debian firmware package
FIRMWARE = {'8086': 'firmware-iwlwifi', '10ec': 'firmware-realtek', '0bda': 'firmware-realtek', '168c': 'firmware-atheros', '0cf3': 'firmware-atheros', '14e4': 'firmware-brcm80211',
            '14c3': 'firmware-mediatek', '0e8d': 'firmware-mediatek', '148f': 'firmware-misc-nonfree', '1814': 'firmware-misc-nonfree', '11ab': 'firmware-libertas', '1b4b': 'firmware-libertas'}
VENDOR = {'8086': 'Intel', '10ec': 'Realtek', '0bda': 'Realtek', '168c': 'Qualcomm Atheros', '0cf3': 'Qualcomm Atheros', '14e4': 'Broadcom', '14c3': 'MediaTek', '0e8d': 'MediaTek',
          '148f': 'Ralink / MediaTek', '1814': 'Ralink / MediaTek', '11ab': 'Marvell', '1b4b': 'Marvell'}
USB_WIFI_VENDORS = ('0bda', '148f', '0cf3', '0e8d', '2357', '7392', '0846', '2001', '13b1', '050d', '0b05', '2019')


# ───────── scripts (all print @@ lines; secrets never in argument lists) ─────────
STATUS = r'''. /etc/os-release 2>/dev/null; echo "@@os $PRETTY_NAME"; echo "@@id $ID"; echo "@@like $ID_LIKE"; echo "@@kernel $(uname -r)"; echo "@@arch $(uname -m)"
echo "@@uid $(id -u)"
[ -d /run/systemd/system ] && echo "@@systemd"
command -v apt-get >/dev/null 2>&1 && echo "@@apt"
echo "@@tz $(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null)"
echo "@@now $(date '+%Y-%m-%d %H:%M:%S')"
echo "@@ntp $(timedatectl show -p NTPSynchronized --value 2>/dev/null)"
echo "@@uptime $(cut -d. -f1 /proc/uptime)"
[ -f /var/run/reboot-required ] && echo "@@reboot"
if command -v apt-get >/dev/null 2>&1; then
  echo "@@upgradable $(apt list --upgradable 2>/dev/null | grep -c upgradable)"
  echo "@@aptage $(stat -c %Y /var/lib/apt/periodic/update-success-stamp 2>/dev/null || stat -c %Y /var/lib/apt/lists 2>/dev/null)"
fi
command -v docker >/dev/null 2>&1 && echo "@@docker $(docker --version 2>/dev/null | sed 's/Docker version //;s/,.*//')"
dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /^(docker\.io|docker-ce|docker-ce-cli|containerd|containerd\.io|docker-compose-plugin|docker-compose|docker-buildx-plugin)$/ {print "@@dpkg "$2" "$3}'
echo @@end
'''

WIFI_STATUS = r'''echo "@@nm $(command -v nmcli >/dev/null 2>&1 && systemctl is-active NetworkManager 2>/dev/null || echo none)"
for p in /sys/class/net/*; do n=${p##*/}; [ -d "$p/wireless" ] || [ -d "$p/phy80211" ] || continue
  echo "@@if $n|$(cat $p/address 2>/dev/null)|$(basename "$(readlink -f $p/device/driver 2>/dev/null)")|$(cat $p/operstate 2>/dev/null)"
done
echo "@@apmodes $(iw list 2>/dev/null | grep -c '\* AP$')"
echo "@@iw $(command -v iw >/dev/null 2>&1 && echo 1 || echo 0)"
echo "@@blocked $(rfkill list wifi 2>/dev/null | grep -c 'Soft blocked: yes')"
for d in /sys/bus/pci/devices/*; do c=$(cat $d/class 2>/dev/null); case $c in 0x0280*) echo "@@pci $(cat $d/vendor | sed 's/0x//') $(cat $d/device | sed 's/0x//') ${d##*/}";; esac; done
for d in /sys/bus/usb/devices/*; do [ -f $d/idVendor ] && echo "@@usb $(cat $d/idVendor) $(cat $d/idProduct) $(cat $d/product 2>/dev/null)"; done
lspci -nn 2>/dev/null | grep -iE 'network|wireless|802\.11' | sed 's/^/@@pcitext /'
echo "@@defdev $(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')"
ip -4 route show 2>/dev/null | awk '$1 ~ /\// {print "@@route "$1" "$3}'
if command -v nmcli >/dev/null 2>&1; then
  nmcli -t -f NAME,TYPE,DEVICE,STATE connection show 2>/dev/null | sed 's/^/@@con /'
  for f in ''' + KEYFILES + r'''/*.nmconnection; do [ -f "$f" ] || continue; grep -q '^type=wifi' "$f" || continue
    echo "@@prof $(basename "$f" .nmconnection)|$(grep -m1 '^mode=' "$f" | cut -d= -f2)|$(grep -m1 '^ssid=' "$f" | cut -d= -f2-)|$(grep -m1 '^address1=' "$f" | cut -d= -f2-)|$(grep -m1 '^interface-name=' "$f" | cut -d= -f2-)"
  done
fi
for i in $(ls /sys/class/net 2>/dev/null); do [ -d /sys/class/net/$i/wireless ] || continue
  echo "@@ip $i $(ip -4 -o addr show dev $i 2>/dev/null | awk '{print $4; exit}')"
  echo "@@stations $i $(iw dev $i station dump 2>/dev/null | grep -c '^Station')"
done
echo @@end
'''


def parse_status(out):
    s = {'dpkg': []}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k == '@@dpkg':
            n, _, ver = v.partition(' ')
            s['dpkg'].append({'name': n, 'version': ver.strip()})
        elif k.startswith('@@') and k != '@@end':
            s[k[2:]] = v.strip()
    return s


def _ssid_text(raw):
    """a keyfile ssid is a string or a list of byte values «65;66;»"""
    raw = (raw or '').strip()
    if re.fullmatch(r'(\d{1,3};)+', raw):
        try:
            return bytes(int(x) for x in raw.strip(';').split(';')).decode('utf-8', 'replace')
        except ValueError:
            return raw
    return raw


def parse_wifi(out):
    """→ {nm, interfaces [{name, mac, driver, state, ip, stations}], apCapable, routes, defaultDev, chips, profiles [{id, mode, ssid, address, iface, active}], hotspot {on, ...}}"""
    r = {'interfaces': [], 'routes': [], 'chips': [], 'profiles': [], 'usb': [], 'active': {}}
    ips, stations = {}, {}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        v = v.strip()
        if k == '@@nm':
            r['nm'] = v
        elif k == '@@if':
            n, mac, drv, st = (v.split('|') + ['', '', '', ''])[:4]
            r['interfaces'].append({'name': n, 'mac': mac, 'driver': drv, 'state': st})
        elif k == '@@apmodes':
            r['apCapable'] = (int(v) if v.isdigit() else 0) > 0
        elif k == '@@iw':
            r['iw'] = v == '1'
        elif k == '@@blocked':
            r['blocked'] = (int(v) if v.isdigit() else 0) > 0
        elif k == '@@pci':
            p = v.split()
            if len(p) >= 2:
                r['chips'].append({'bus': 'pci', 'vendor': p[0].lower(), 'device': p[1].lower()})
        elif k == '@@usb':
            p = v.split(None, 2)
            if len(p) >= 2 and p[0].lower() in USB_WIFI_VENDORS and re.search(r'wireless|wlan|wi-?fi|802\.11|adapter|network', p[2] if len(p) > 2 else '', re.I):
                r['chips'].append({'bus': 'usb', 'vendor': p[0].lower(), 'device': p[1].lower(), 'name': p[2] if len(p) > 2 else ''})
        elif k == '@@pcitext':
            r['usb'].append(v[:160])
        elif k == '@@defdev':
            r['defaultDev'] = v
        elif k == '@@route':
            p = v.split()
            r['routes'].append({'net': p[0], 'dev': p[1] if len(p) > 1 else ''})
        elif k == '@@con':
            p = re.split(r'(?<!\\):', v)
            if len(p) >= 4 and p[3] == 'activated':
                r['active'][p[0].replace('\\:', ':')] = p[2]
        elif k == '@@ip':
            p = v.split()
            ips[p[0]] = p[1] if len(p) > 1 else ''
        elif k == '@@stations':
            p = v.split()
            stations[p[0]] = int(p[1]) if len(p) > 1 and p[1].isdigit() else 0
        elif k == '@@prof':
            pid, mode, ssid, addr, ifc = (v.split('|') + ['', '', '', '', ''])[:5]
            r['profiles'].append({'id': pid, 'mode': mode or 'infrastructure', 'ssid': _ssid_text(ssid), 'address': addr, 'iface': ifc, 'active': pid in r['active'],
                                  'device': r['active'].get(pid, '')})
    for i in r['interfaces']:
        i['ip'], i['stations'] = ips.get(i['name'], ''), stations.get(i['name'], 0)
    hs = next((p for p in r['profiles'] if p['id'] == HOTSPOT), None)
    r['hotspot'] = {'exists': bool(hs), 'on': bool(hs and hs['active']), 'ssid': hs['ssid'] if hs else '', 'address': hs['address'] if hs else '', 'iface': (hs['device'] or hs['iface']) if hs else ''}
    r['profiles'] = [p for p in r['profiles'] if p['id'] != HOTSPOT]
    for c in r['chips']:
        c['vendorName'] = VENDOR.get(c['vendor'], c['vendor'])
        c['package'] = FIRMWARE.get(c['vendor'])
    return r


def parse_scan(out):
    """nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY,CHAN → [{ssid, signal, security, channel, current}] sorted by signal, one entry per name"""
    nets = {}
    for l in out.splitlines():
        p = [x.replace('\\:', ':').replace('\\\\', '\\') for x in re.split(r'(?<!\\):', l)]
        if len(p) < 5 or not p[1].strip():
            continue
        cur, ssid, sig, sec, ch = p[0].strip() == '*', p[1], int(p[2]) if p[2].isdigit() else 0, p[3].strip(), p[4].strip()
        n = nets.get(ssid)
        if not n or sig > n['signal']:
            nets[ssid] = {'ssid': ssid, 'signal': sig, 'security': sec if sec != '--' else '', 'channel': ch, 'current': cur or bool(n and n['current'])}
        elif cur:
            n['current'] = True
    return sorted(nets.values(), key=lambda x: (not x['current'], -x['signal']))


# ───────── checks of what the person typed ─────────
def check_iface(name):
    name = str(name or '').strip()
    if not IFACE_RE.match(name):
        raise ValueError('название адаптера: латинские буквы и цифры, например wlan0')
    return name


def check_ssid(s):
    s = str(s or '')
    if not 1 <= len(s.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in s):
        raise ValueError('название сети: от 1 до 32 байт, без управляющих символов')
    return s


def check_psk(p, allow_empty=False):
    p = str(p or '')
    if allow_empty and not p:
        return ''
    if not 8 <= len(p) <= 63 or any(ord(c) < 32 or ord(c) > 126 for c in p) or p != p.strip():
        raise ValueError('пароль Wi-Fi: от 8 до 63 символов, латиница, цифры и знаки, без пробела по краям')
    return p


def check_tz(tz):
    tz = str(tz or '').strip()
    if not TZ_RE.match(tz):
        raise ValueError('часовой пояс вида Europe/Moscow')
    return tz


def check_address(addr, routes=()):
    """the access point's own address «10.77.0.1/24»: private, a /16–/29 network, and no overlap with any network the machine already lives in (or the AP would cut it off)"""
    try:
        ifc = ipaddress.ip_interface(str(addr or '').strip())
    except ValueError:
        raise ValueError('адрес точки вида 10.77.0.1/24')
    if ifc.version != 4 or not ifc.ip.is_private or not 16 <= ifc.network.prefixlen <= 29:
        raise ValueError('адрес точки — частная сеть IPv4 с маской от /16 до /29, например 10.77.0.1/24')
    if ifc.ip == ifc.network.network_address or ifc.ip == ifc.network.broadcast_address:
        raise ValueError('адрес точки не может быть адресом самой сети или широковещательным')
    for r in routes:
        try:
            if ipaddress.ip_network(r, strict=False).overlaps(ifc.network):
                raise ValueError(f'сеть {ifc.network} пересекается с уже существующей {r}: выберите другой адрес (например 10.78.0.1/24)')
        except ValueError as e:
            if 'пересекается' in str(e):
                raise
    return f'{ifc.ip}/{ifc.network.prefixlen}'


def nets_of(routes, skip_dev=None):
    """networks the machine already lives in (a route of the adapter being reconfigured does not count: its own old network may be reused)"""
    return [r['net'] for r in routes if isinstance(r, dict) and r.get('dev') != skip_dev] + [r for r in routes if isinstance(r, str)]


def suggest_address(routes=()):
    """a free private network for the access point: 10.77.0.1/24, else the next ones"""
    for n in range(77, 120):
        a = f'10.{n}.0.1/24'
        try:
            return check_address(a, routes)
        except ValueError:
            continue
    return DEFAULT_ADDRESS


# ───────── keyfiles ─────────
def _bytes_list(s):
    return ';'.join(str(b) for b in s.encode('utf-8')) + ';'


def _esc(v):
    return v.replace('\\', '\\\\')


def hotspot_keyfile(iface, ssid, psk, address, band='bg'):
    return (f'[connection]\nid={HOTSPOT}\nuuid={uuid.uuid4()}\ntype=wifi\ninterface-name={iface}\nautoconnect=true\nautoconnect-priority=50\n\n'
            f'[wifi]\nmode=ap\nssid={_bytes_list(ssid)}\nband={"a" if band == "a" else "bg"}\n\n'
            f'[wifi-security]\nkey-mgmt=wpa-psk\npsk={_esc(psk)}\n\n'
            f'[ipv4]\nmethod=shared\naddress1={address}\n\n[ipv6]\nmethod=ignore\n')


def client_profile_id(ssid):
    slug = re.sub(r'[^A-Za-z0-9]+', '-', ssid).strip('-')[:24] or 'net'
    return CLIENT_PREFIX + slug + '-' + hashlib.sha1(ssid.encode('utf-8')).hexdigest()[:4]


def client_keyfile(pid, iface, ssid, psk, hidden=False):
    sec = f'[wifi-security]\nkey-mgmt=wpa-psk\npsk={_esc(psk)}\n\n' if psk else ''
    return (f'[connection]\nid={pid}\nuuid={uuid.uuid4()}\ntype=wifi\ninterface-name={iface}\nautoconnect=true\n\n'
            f'[wifi]\nmode=infrastructure\nssid={_bytes_list(ssid)}\n{"hidden=true" + chr(10) if hidden else ""}\n{sec}[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n')


def _put_file(path, text):
    b = base64.b64encode(text.encode('utf-8')).decode()
    return f'umask 077; printf %s {shlex.quote(b)} | base64 -d > {shlex.quote(path)} && chmod 600 {shlex.quote(path)}'


# ───────── scripts that change things ─────────
def tz_script(tz):
    tz = check_tz(tz)
    return f'''TZ_NEW={shlex.quote(tz)}
[ "$(id -u)" = 0 ] || {{ echo "@@fail нужны права root"; exit 0; }}
[ -f "/usr/share/zoneinfo/$TZ_NEW" ] || {{ echo "@@fail такого часового пояса нет: $TZ_NEW"; exit 0; }}
timedatectl set-timezone "$TZ_NEW" </dev/null 2>&1 || {{ echo "@@fail не удалось сменить часовой пояс"; exit 0; }}
echo "— часовой пояс: $TZ_NEW, сейчас $(date '+%H:%M')"
echo @@ok
'''


NTP_SCRIPT = '''[ "$(id -u)" = 0 ] || { echo "@@fail нужны права root"; exit 0; }
timedatectl set-ntp true </dev/null 2>&1 || { echo "@@fail не удалось включить синхронизацию времени (нет systemd-timesyncd или chrony?)"; exit 0; }
echo "— автосинхронизация времени включена"
echo @@ok
'''

ZONES_SCRIPT = 'timedatectl list-timezones 2>/dev/null | head -700\n'

_APT = 'export DEBIAN_FRONTEND=noninteractive\nAPT="apt-get -y -o DPkg::Lock::Timeout=180 -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef"\n'
_ROOT_APT = ('[ "$(id -u)" = 0 ] || { echo "@@fail нужны права root"; exit 0; }\n'
             'command -v apt-get >/dev/null 2>&1 || { echo "@@fail нужны Debian, Ubuntu или другая система с apt"; exit 0; }\n')

CHECK_SCRIPT = _APT + _ROOT_APT + '''echo "— обновляю список пакетов"
$APT update </dev/null 2>&1 | tail -3 || true
echo "@@count $(apt list --upgradable 2>/dev/null | grep -c upgradable)"
apt list --upgradable 2>/dev/null | grep upgradable | head -80 | sed 's/^/@@pkg /'
echo @@ok
'''

UPGRADE_SCRIPT = _APT + _ROOT_APT + '''echo "— обновляю список пакетов"
$APT update </dev/null 2>&1 | tail -2
echo "— обновляю установленные пакеты (это может занять несколько минут)"
$APT upgrade </dev/null 2>&1 | grep -E '^(Setting up|Unpacking|Preparing|Err|E:)' | tail -60 || true
$APT autoremove </dev/null >/dev/null 2>&1 || true
[ -f /var/run/reboot-required ] && echo "@@reboot"
echo "@@left $(apt list --upgradable 2>/dev/null | grep -c upgradable)"
echo @@ok
'''

DOCKER_SCRIPT = _APT + _ROOT_APT + '''$APT update </dev/null >/dev/null 2>&1
PK=$(dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /^(docker\\.io|docker-ce|docker-ce-cli|containerd|containerd\\.io|docker-compose-plugin|docker-buildx-plugin)$/ {print $2}' | tr '\\n' ' ')
if [ -z "$PK" ]; then
  echo "— Docker не установлен: ставлю docker.io из репозитория системы"
  $APT install docker.io </dev/null 2>&1 | grep -E '^(Setting up|Err|E:)' | tail -8
  systemctl enable --now docker </dev/null >/dev/null 2>&1 || true
else
  echo "— обновляю: $PK"
  $APT install --only-upgrade $PK </dev/null 2>&1 | grep -E '^(Setting up|Err|E:|.*already the newest)' | tail -12
fi
command -v docker >/dev/null 2>&1 || { echo "@@fail Docker не появился: проверьте интернет и репозитории"; exit 0; }
echo "@@docker $(docker --version | sed 's/Docker version //;s/,.*//')"
echo @@ok
'''

REBOOT_SCRIPT = '[ "$(id -u)" = 0 ] || { echo "@@fail нужны права root"; exit 0; }\n(sleep 3; reboot) </dev/null >/dev/null 2>&1 &\necho "— перезагрузка через 3 секунды"\necho @@ok\n'


def firmware_packages(chips, os_id='debian'):
    """what a Wi-Fi chip needs: Debian — a firmware package per vendor (needs «non-free-firmware»), Ubuntu and relatives — linux-firmware (it has everything)"""
    if os_id in ('ubuntu', 'linuxmint', 'pop', 'raspbian') or (os_id and os_id not in ('debian',)):
        return ['linux-firmware']
    out = []
    for c in chips:
        p = FIRMWARE.get(c.get('vendor'))
        if p and p not in out:
            out.append(p)
    return out or ['firmware-iwlwifi', 'firmware-realtek', 'firmware-atheros', 'firmware-mediatek', 'firmware-misc-nonfree']


def drivers_script(packages):
    """Wi-Fi base: firmware for the chip, NetworkManager (+ what the shared access point needs), the radio switched on and the driver reloaded"""
    pk = ' '.join(shlex.quote(p) for p in packages if re.match(r'^[a-z0-9][a-z0-9.+\-]+$', p))
    return _APT + _ROOT_APT + f'''. /etc/os-release 2>/dev/null
if [ "$ID" = debian ] && ! grep -rqs 'non-free-firmware' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null; then
  echo "— подключаю раздел non-free-firmware (прошивки для Wi-Fi), копии файлов с .rl-bak"
  for f in /etc/apt/sources.list.d/*.sources; do
    [ -f "$f" ] && grep -q '^Types:' "$f" && grep -qE 'debian\\.org|mirror' "$f" && {{ cp -a "$f" "$f.rl-bak"; sed -i '/^Components:/ s/$/ non-free-firmware/' "$f"; }}
  done
  if [ -f /etc/apt/sources.list ]; then cp -a /etc/apt/sources.list /etc/apt/sources.list.rl-bak; sed -i -E '/^deb (http|https):/ s/ main( |$)/ main non-free-firmware\\1/' /etc/apt/sources.list; fi
fi
echo "— обновляю список пакетов"
$APT update </dev/null 2>&1 | tail -2
echo "— ставлю NetworkManager, Wi-Fi-инструменты и прошивки: {pk}"
$APT install network-manager wpasupplicant iw rfkill wireless-regdb dnsmasq-base iptables nftables {pk} </dev/null 2>&1 | grep -E '^(Setting up|Err|E:)' | tail -20
command -v nmcli >/dev/null 2>&1 || {{ echo "@@fail NetworkManager не установился: проверьте интернет и репозитории"; exit 0; }}
systemctl enable --now NetworkManager </dev/null >/dev/null 2>&1
rfkill unblock wifi 2>/dev/null
echo "— готово: перезагрузка может понадобиться, если адаптер появится не сразу"
echo @@ok
'''


def ap_on_script(iface, ssid, psk, address, band='bg'):
    iface, ssid, psk = check_iface(iface), check_ssid(ssid), check_psk(psk)
    kf = hotspot_keyfile(iface, ssid, psk, address, band)
    path = f'{KEYFILES}/{HOTSPOT}.nmconnection'
    return f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужны права root"; exit 0; }}
command -v nmcli >/dev/null 2>&1 || {{ echo "@@fail NetworkManager не установлен: сначала «Поставить драйверы и NetworkManager»"; exit 0; }}
mkdir -p {KEYFILES}
{_put_file(path, kf)} || {{ echo "@@fail не удалось записать настройки точки"; exit 0; }}
nmcli connection reload </dev/null 2>&1
nmcli device set {shlex.quote(iface)} managed yes </dev/null >/dev/null 2>&1
nmcli device disconnect {shlex.quote(iface)} </dev/null >/dev/null 2>&1
echo "— запускаю точку «{ssid.replace(chr(34), '').replace('$', '').replace(chr(96), '')}»"
timeout 60 nmcli connection up id {HOTSPOT} </dev/null 2>&1 | tail -2
sleep 2
nmcli -t -f NAME,STATE connection show --active </dev/null 2>/dev/null | grep -q '^{HOTSPOT}:activated' || {{ echo "@@fail точка не запустилась: адаптер может не поддерживать режим точки доступа (см. журнал: journalctl -u NetworkManager -n 20)"; exit 0; }}
echo "@@ip $(ip -4 -o addr show dev {shlex.quote(iface)} | awk '{{print $4; exit}}')"
echo @@ok
'''


AP_OFF_SCRIPT = f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужны права root"; exit 0; }}
nmcli connection down id {HOTSPOT} </dev/null >/dev/null 2>&1
nmcli connection modify id {HOTSPOT} connection.autoconnect no </dev/null >/dev/null 2>&1
echo "— точка выключена и не включится сама после перезагрузки"
echo @@ok
'''

AP_FORGET_SCRIPT = f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужны права root"; exit 0; }}
nmcli connection delete id {HOTSPOT} </dev/null >/dev/null 2>&1
rm -f {KEYFILES}/{HOTSPOT}.nmconnection
nmcli connection reload </dev/null >/dev/null 2>&1
echo "— настройки точки удалены"
echo @@ok
'''


def scan_script(iface):
    iface = check_iface(iface)
    return f'''command -v nmcli >/dev/null 2>&1 || {{ echo "@@fail NetworkManager не установлен"; exit 0; }}
nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY,CHAN device wifi list ifname {shlex.quote(iface)} --rescan yes </dev/null 2>&1 | sed 's/^/@@net /'
echo @@end
'''


def connect_script(iface, ssid, psk, hidden=False):
    iface, ssid, psk = check_iface(iface), check_ssid(ssid), check_psk(psk, allow_empty=True)
    pid = client_profile_id(ssid)
    path = f'{KEYFILES}/{pid}.nmconnection'
    return f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужны права root"; exit 0; }}
command -v nmcli >/dev/null 2>&1 || {{ echo "@@fail NetworkManager не установлен: сначала «Поставить драйверы и NetworkManager»"; exit 0; }}
nmcli -t -f NAME,STATE connection show --active </dev/null 2>/dev/null | grep -q '^{HOTSPOT}:activated' && nmcli connection down id {HOTSPOT} </dev/null >/dev/null 2>&1
mkdir -p {KEYFILES}
{_put_file(path, client_keyfile(pid, iface, ssid, psk, hidden))} || {{ echo "@@fail не удалось записать настройки сети"; exit 0; }}
nmcli connection reload </dev/null 2>&1
nmcli device set {shlex.quote(iface)} managed yes </dev/null >/dev/null 2>&1
echo "— подключаюсь"
timeout 60 nmcli connection up id {shlex.quote(pid)} </dev/null 2>&1 | tail -2
sleep 3
nmcli -t -f NAME,STATE connection show --active </dev/null 2>/dev/null | grep -q '^{pid}:activated' || {{ echo "@@fail не подключилось: неверный пароль или сеть вне зоны (профиль сохранён, его можно удалить)"; nmcli connection delete id {shlex.quote(pid)} </dev/null >/dev/null 2>&1; exit 0; }}
echo "@@ip $(ip -4 -o addr show dev {shlex.quote(iface)} | awk '{{print $4; exit}}')"
echo @@ok
'''


def forget_script(profile):
    profile = str(profile or '')
    if not re.match(r'^[A-Za-z0-9_.\-]{1,60}$', profile) or profile == HOTSPOT:
        raise ValueError('неверное имя сохранённой сети')
    return f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужны права root"; exit 0; }}
nmcli connection delete id {shlex.quote(profile)} </dev/null 2>&1 | tail -1
echo @@ok
'''


# ───────── running ─────────
def local_ok():
    """the commands can run right here: a real Linux machine, root, systemd — not a container"""
    return (sys.platform.startswith('linux') and hasattr(os, 'geteuid') and os.geteuid() == 0 and os.path.isdir('/run/systemd/system')
            and not os.path.exists('/.dockerenv') and not os.path.exists('/run/.containerenv'))


def run_local(script, timeout=60, on_line=None):
    p = subprocess.Popen(['sh', '-s'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, lines = [], []
    timer = threading.Timer(timeout, p.kill)
    timer.start()
    try:
        p.stdin.write(script)
        p.stdin.close()
        for l in p.stdout:
            lines.append(l)
            if on_line:
                on_line(l.rstrip())
        p.wait()
    finally:
        timer.cancel()
    if p.returncode and p.returncode < 0:
        raise RuntimeError('команда не уложилась во время и остановлена')
    return ''.join(lines)


class Host:
    """runs the scripts above on «this machine»; see the module text for where that is"""

    def __init__(self, app, demo=False):
        self.app, self.demo = app, demo
        self.lock = threading.Lock()

    def target(self):
        """→ ('local', None) | ('ssh', device) | (None, reason)"""
        if self.demo:
            return 'demo', None
        if local_ok():
            return 'local', None
        d = self.app.hostnet.find_host()
        if d and d.get('driver') == 'ssh':
            return 'ssh', d
        if d:
            return None, f'Rack Live работает на «{d.get("name")}» ({d.get("driver")}): режим разработчика рассчитан на Linux с apt (Debian, Ubuntu, Raspberry Pi OS) и не меняет систему NAS, роутера и Docker-контейнера.'
        return None, ('Rack Live работает в контейнере или не от root, поэтому системой этой машины он управлять не может. Поставьте его как службу (плагин «ReckController OS» или «Сборщик площадки») '
                      'либо добавьте эту машину в «Устройства» как «Сервер / VPS по SSH» с логином root.')

    def run(self, script, timeout=60, on_line=None):
        kind, d = self.target()
        if kind == 'local':
            return run_local(script, timeout, on_line)
        if kind == 'ssh':
            from .drivers import REGISTRY
            _, cfg, why = self.app.hostnet.ssh_target(d)
            if not cfg:
                raise RuntimeError(why or 'нет входа по SSH')
            out = REGISTRY['ssh']._run(cfg, script, timeout=timeout)
            if on_line:
                for l in out.splitlines():
                    on_line(l)
            return out
        raise RuntimeError(d)

    # ── reading ──
    def status(self):
        kind, why = self.target()
        if kind is None:
            return {'ok': False, 'why': why}
        if kind == 'demo':
            return demo_status()
        try:
            s = parse_status(self.run(STATUS, 40))
        except Exception as e:
            return {'ok': False, 'why': f'не удалось прочитать систему: {e}'}
        ok = 'apt' in s and 'systemd' in s and s.get('uid') == '0'
        res = {'ok': True, 'mode': kind, 'supported': ok, 'os': s.get('os'), 'id': s.get('id'), 'kernel': s.get('kernel'), 'arch': s.get('arch'), 'tz': s.get('tz'), 'now': s.get('now'),
               'ntp': s.get('ntp') == 'yes', 'uptime': int(s.get('uptime') or 0), 'reboot': 'reboot' in s,
               'upgradable': int(s['upgradable']) if (s.get('upgradable') or '').isdigit() else None, 'aptAge': int(s['aptage']) if (s.get('aptage') or '').isdigit() else None,
               'docker': {'version': s.get('docker') or None, 'packages': s['dpkg']}}
        if not ok:
            res['why'] = ('Нужны Linux с systemd и apt (Debian, Ubuntu, Raspberry Pi OS) и права root: '
                          + ', '.join(x for x, f in (('нет apt', 'apt' not in s), ('нет systemd', 'systemd' not in s), ('вход не под root', s.get('uid') != '0')) if f))
        return res

    def wifi(self):
        kind, why = self.target()
        if kind is None:
            return {'ok': False, 'why': why}
        if kind == 'demo':
            return demo_wifi()
        try:
            w = parse_wifi(self.run(WIFI_STATUS, 40))
        except Exception as e:
            return {'ok': False, 'why': f'не удалось прочитать Wi-Fi: {e}'}
        w['ok'] = True
        w['mode'] = kind
        w['suggestAddress'] = suggest_address(nets_of(w['routes'], (w.get('hotspot') or {}).get('iface')))
        return w

    def zones(self):
        kind, _ = self.target()
        if kind == 'demo':
            return ['Europe/Moscow', 'Europe/Kaliningrad', 'Europe/Samara', 'Asia/Yekaterinburg', 'Asia/Tbilisi', 'UTC']
        return [z for z in self.run(ZONES_SCRIPT, 20).splitlines() if TZ_RE.match(z.strip())]


def _result(out):
    """→ (ok, message, lines): the @@ok / @@fail convention of every script above"""
    lines = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith('@@')]
    if '@@fail' in out:
        return False, out.split('@@fail', 1)[1].splitlines()[0].strip(), lines
    return '@@ok' in out, '', lines


def parse_marks(out):
    m = {}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k.startswith('@@') and k not in ('@@ok', '@@end', '@@fail', '@@pkg'):
            m[k[2:]] = v.strip()
    m['pkgs'] = [l[6:].split('/')[0] for l in out.splitlines() if l.startswith('@@pkg ')]
    return m


# ───────── demo (no real machine is touched) ─────────
def demo_status():
    return {'ok': True, 'mode': 'demo', 'supported': True, 'os': 'Debian GNU/Linux 13 (trixie)', 'id': 'debian', 'kernel': '6.12.48', 'arch': 'x86_64', 'tz': 'Europe/Moscow',
            'now': time.strftime('%Y-%m-%d %H:%M:%S'), 'ntp': True, 'uptime': 3 * 86400 + 5000, 'reboot': False, 'upgradable': 7, 'aptAge': int(time.time()) - 3600,
            'docker': {'version': '27.5.1', 'packages': [{'name': 'docker.io', 'version': '27.5.1+dfsg4-1'}, {'name': 'containerd', 'version': '1.7.24'}]}}


def demo_wifi():
    return {'ok': True, 'mode': 'demo', 'nm': 'active', 'iw': True, 'apCapable': True, 'blocked': False, 'defaultDev': 'enp2s0', 'routes': [{'net': '192.168.1.0/24', 'dev': 'enp2s0'}], 'suggestAddress': DEFAULT_ADDRESS,
            'interfaces': [{'name': 'wlp3s0', 'mac': '00:11:22:33:44:55', 'driver': 'iwlwifi', 'state': 'up', 'ip': '10.77.0.1/24', 'stations': 1}],
            'chips': [{'bus': 'pci', 'vendor': '8086', 'device': '24fb', 'vendorName': 'Intel', 'package': 'firmware-iwlwifi'}],
            'profiles': [{'id': 'rl-wifi-Office-1a2', 'mode': 'infrastructure', 'ssid': 'Office', 'address': '', 'iface': 'wlp3s0', 'active': False, 'device': ''}],
            'hotspot': {'exists': True, 'on': True, 'ssid': DEFAULT_SSID, 'address': DEFAULT_ADDRESS, 'iface': 'wlp3s0'}, 'usb': []}


DEMO_NETS = [{'ssid': 'Office', 'signal': 78, 'security': 'WPA2', 'channel': '6', 'current': False}, {'ssid': 'Guest-5G', 'signal': 52, 'security': 'WPA2', 'channel': '36', 'current': False},
             {'ssid': 'Cafe', 'signal': 31, 'security': '', 'channel': '1', 'current': False}]
