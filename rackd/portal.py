"""Плагин «Гостевой Wi-Fi с порталом» для OpenWrt: профиль сети, скрипты для роутера, библиотека шаблонов страницы входа.

Роль «Главный роутер» (gateway): интернет приходит в WAN, у роутера две сети — основная (LAN) и гостевая со своим DHCP
и межсетевым экраном (гостям только интернет). Страницу входа рисует OpenNDS по шаблону из Rack Live (theme_rl.sh).
Для каждого LAN-порта выбирается, что он отдаёт: основную сеть, гостевую, обе (транк для точек доступа: основная без метки,
гостевая с меткой VLAN) или ничего. Всё, что создаёт плагин, — секции uci с префиксом rl_; перед изменением сохраняется
копия настроек и заводится таймер отката: если Rack Live не подтвердит, что роутер снова на связи, он сам вернёт всё как было."""
import base64
import hashlib
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import tarfile
import time
import zipfile

ASSETS = os.path.join(os.path.dirname(__file__), 'portal_assets')
ROLLBACK_SEC = 360                       # сколько роутер ждёт подтверждения, прежде чем сам вернёт прежние настройки
CONFIGS = ('network', 'wireless', 'dhcp', 'firewall', 'opennds')
PORT_ROLES = ('main', 'guest', 'trunk', 'off')
PORT_TEXT = {'main': 'основная сеть', 'guest': 'гостевая (портал)', 'trunk': 'обе сети (для точек доступа)', 'off': 'выключен'}

DEFAULTS = {'role': 'gateway', 'mainWifi': True, 'mainSsid': '', 'mainKey': '', 'guestSsid': 'Guest', 'guestKey': '', 'bands': ['2g', '5g'],
            'lan': '192.168.10.1/24', 'guest': '10.20.0.1/22', 'vlan': 10, 'portal': True, 'login': 'click', 'password': '',
            'hours': 24, 'down': 0, 'up': 0, 'name': 'Гостевой Wi-Fi', 'rules': '', 'after': 'https://ya.ru', 'template': 'default', 'ports': {},
            'mgmtWan': True, 'country': 'RU', 'smsHost': '', 'smsUser': 'root', 'smsPort': 22, 'smsPass': '', 'smsReady': False, 'smsInfo': ''}
SECRET = ('mainKey', 'guestKey', 'password', 'smsPass')

# роутер после перезапуска сети «отзывается» сюда: token → {'t', 'wan', 'lan'}; токены ждущих — PENDING
HELLO, PENDING = {}, {}


def new_token():
    for k in [k for k, t in PENDING.items() if time.time() - t > 3600]:
        PENDING.pop(k, None); HELLO.pop(k, None)
    tok = secrets.token_urlsafe(18)
    PENDING[tok] = time.time()
    return tok


def hello(tok, wan, lan):
    if tok not in PENDING:
        return False
    ip = lambda v: str(ipaddress.ip_address(v)) if v else ''
    try:
        HELLO[tok] = {'t': time.time(), 'wan': ip(wan), 'lan': ip(lan)}
    except ValueError:
        return False
    return True


# ───────── профиль ─────────
def _ssid(v, what):
    v = str(v or '').strip()
    if not v or len(v.encode()) > 32:
        raise ValueError(f'{what}: название сети от 1 до 32 символов')
    if re.search(r"[\x00-\x1f'\\]", v):
        raise ValueError(f'{what}: в названии сети нельзя кавычку \' и обратную косую черту')
    return v


def _key(v, what, need):
    v = str(v or '')
    if not v and not need:
        return ''
    if not 8 <= len(v) <= 63 or re.search(r"[\x00-\x1f'\\]", v):
        raise ValueError(f'{what}: пароль Wi-Fi от 8 до 63 символов, без кавычки \' и обратной косой черты')
    return v


def _net(v, what, lo, hi):
    try:
        n = ipaddress.ip_interface(str(v or '').strip())
    except ValueError:
        raise ValueError(f'{what}: адрес вида 192.168.10.1/24')
    if n.version != 4 or not n.ip.is_private or not lo <= n.network.prefixlen <= hi:
        raise ValueError(f'{what}: частная сеть IPv4 с маской от /{lo} до /{hi}')
    if n.ip in (n.network.network_address, n.network.broadcast_address):
        raise ValueError(f'{what}: адрес роутера не может быть адресом сети или широковещательным')
    return n


def validate(p, hw, strict_sms=False):
    """профиль от интерфейса + что есть на роутере (порты, радио, WAN) → чистый профиль или ValueError с понятной причиной"""
    p = dict(DEFAULTS, **{k: v for k, v in (p or {}).items() if k in DEFAULTS})
    out = {'role': 'gateway'}
    out['mainWifi'] = p['mainWifi'] is not False        # без основной Wi-Fi: на роутере только гостевая сеть (Wi-Fi раздают другие точки)
    if out['mainWifi']:
        out['mainSsid'] = _ssid(p['mainSsid'], 'Основная Wi-Fi')
        out['mainKey'] = _key(p['mainKey'], 'Основная Wi-Fi', True)
    else:
        out['mainSsid'], out['mainKey'] = str(p['mainSsid'] or ''), str(p['mainKey'] or '')
    out['guestSsid'] = _ssid(p['guestSsid'], 'Гостевая Wi-Fi')
    out['guestKey'] = _key(p['guestKey'], 'Гостевая Wi-Fi', False)
    if out['mainWifi'] and out['guestSsid'] == out['mainSsid']:
        raise ValueError('У основной и гостевой Wi-Fi должны быть разные названия')
    have = [r['band'] for r in hw.get('radios', [])]
    out['bands'] = [b for b in ('2g', '5g') if b in (p['bands'] or []) and b in have]
    if not out['bands']:
        raise ValueError('Выберите хотя бы один диапазон Wi-Fi, который есть у роутера')
    lan, guest = _net(p['lan'], 'Основная сеть', 16, 29), _net(p['guest'], 'Гостевая сеть', 16, 28)
    if lan.network.overlaps(guest.network):
        raise ValueError('Основная и гостевая сети пересекаются — выберите разные')
    wan = hw.get('wanip')
    if wan:
        w = ipaddress.ip_interface(wan).network
        for n, what in ((lan, 'Основная'), (guest, 'Гостевая')):
            if n.network.overlaps(w):
                raise ValueError(f'{what} сеть пересекается с сетью на WAN ({w}) — роутер не поймёт, куда слать. Выберите другую, например 192.168.10.1/24')
    out['lan'], out['guest'] = str(lan), str(guest)
    try:
        out['vlan'] = int(p['vlan'])
    except (TypeError, ValueError):
        out['vlan'] = 0
    if not 2 <= out['vlan'] <= 4094:
        raise ValueError('Номер VLAN гостевой сети: от 2 до 4094')
    out['portal'] = bool(p['portal'])
    out['login'] = p['login'] if p['login'] in ('click', 'password', 'sms') else 'click'
    out['password'] = str(p['password'] or '')
    if out['login'] == 'password' and not 4 <= len(out['password']) <= 63:
        raise ValueError('Пароль для входа на портал: от 4 до 63 символов')
    if out['login'] != 'password':
        out['password'] = ''
    out.update(_sms(p, out['login'] == 'sms' and strict_sms))      # the SIM router is asked for only when it is being prepared: the main router is set up first
    for k, lo, hi, what in (('hours', 1, 720, 'Сколько часов действует вход'), ('down', 0, 1000, 'Скорость гостя, загрузка'), ('up', 0, 1000, 'Скорость гостя, отдача')):
        try:
            out[k] = int(p[k])
        except (TypeError, ValueError):
            out[k] = -1
        if not lo <= out[k] <= hi:
            raise ValueError(f'{what}: число от {lo} до {hi}')
    out['name'] = re.sub(r'\s+', ' ', str(p['name'] or '')).strip()[:40] or DEFAULTS['name']
    out['rules'] = str(p['rules'] or '').strip()[:4000]
    after = str(p.get('after', DEFAULTS['after']) or '').strip()[:300]
    if after and not re.fullmatch(r'https?://[^\s"\'<>]+', after):
        raise ValueError('Куда отправить после входа: адрес сайта вида https://ya.ru (или пусто — туда, куда гость шёл сам)')
    out['after'] = after
    out['template'] = str(p['template'] or 'default')
    out['mgmtWan'] = bool(p['mgmtWan'])
    out['country'] = p['country'] if re.fullmatch(r'[A-Z]{2}', str(p['country'] or '')) else 'RU'
    ports, given = {}, p['ports'] or {}
    for name in hw.get('lan', []):
        r = given.get(name, 'main')
        ports[name] = r if r in PORT_ROLES else 'main'
    mg = hw.get('mgmt')
    if mg and ports.get(mg) in ('guest', 'off'):
        raise ValueError(f'Порт {mg.upper()} — тот, через который Rack Live сейчас управляет роутером. Его нельзя делать гостевым или выключать: '
                         'управление пропадёт. Подключите Rack Live в другой порт или оставьте этому порту основную сеть.')
    if not any(r in ('main', 'trunk') for r in ports.values()) and ports:
        raise ValueError('Хотя бы один порт должен отдавать основную сеть — иначе к роутеру не подключиться проводом')
    out['ports'] = ports
    return out


def _sms(p, need):
    """the router with the SIM card that sends the codes: its address (seen from the portal router), SSH login and port"""
    host = str(p.get('smsHost') or '').strip()
    user = str(p.get('smsUser') or 'root').strip() or 'root'
    try:
        port = int(22 if p.get('smsPort') in (None, '') else p['smsPort'])
    except (TypeError, ValueError):
        port = 0
    if need:
        try:
            ok = ipaddress.ip_address(host).is_private
        except ValueError:
            ok = bool(re.fullmatch(r'[A-Za-z0-9]([A-Za-z0-9.-]{0,60}[A-Za-z0-9])?', host))
        if not host or not ok:
            raise ValueError('Роутер с SIM: адрес вида 192.168.10.2 (так его видит главный роутер)')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,32}', user):
            raise ValueError('Роутер с SIM: логин из латинских букв и цифр, обычно root')
        if not 1 <= port <= 65535:
            raise ValueError('Роутер с SIM: порт SSH от 1 до 65535')
    return {'smsHost': host, 'smsUser': user, 'smsPort': port if 1 <= port <= 65535 else 22, 'smsPass': str(p.get('smsPass') or ''),
            'smsReady': bool(p.get('smsReady')), 'smsInfo': str(p.get('smsInfo') or '')[:300]}


def public(p):
    """профиль для интерфейса: пароли не уходят, только «задан / нет»"""
    if not p:
        return None
    return dict({k: v for k, v in p.items() if k not in SECRET}, **{k + 'Set': bool(p.get(k)) for k in SECRET})


def merge_secrets(new, old):
    """пустое поле пароля в форме = оставить прежний"""
    new = dict(new or {})
    for k in SECRET:
        if not new.get(k) and (old or {}).get(k):
            new[k] = old[k]
    return new


# ───────── что есть на роутере ─────────
STATUS = r'''echo "@@model $(jsonfilter -i /etc/board.json -e '@.model.name' 2>/dev/null)"
. /etc/openwrt_release 2>/dev/null; echo "@@rel $DISTRIB_RELEASE"
command -v apk >/dev/null 2>&1 && echo "@@pm apk" || echo "@@pm opkg"
echo "@@free $(df -k /overlay 2>/dev/null | awk 'NR==2{print $4}')"
echo "@@lan $(jsonfilter -i /etc/board.json -e '@.network.lan.ports[*]' 2>/dev/null | tr '\n' ' ')"
W=$(jsonfilter -i /etc/board.json -e '@.network.wan.device' 2>/dev/null); echo "@@wan $W"
for p in $(jsonfilter -i /etc/board.json -e '@.network.lan.ports[*]' 2>/dev/null) $W; do echo "@@link $p $(cat /sys/class/net/$p/carrier 2>/dev/null || echo 0) $(cat /sys/class/net/$p/speed 2>/dev/null || echo -1)"; done
for r in $(uci -q show wireless | sed -n "s/^wireless\.\([^.=]*\)=wifi-device$/\1/p"); do echo "@@radio $r $(uci -q get wireless.$r.band)"; done
V=$( (apk list --installed 2>/dev/null | grep -o '^opennds-[0-9][^ ]*' | sed 's/^opennds-//') || true); [ -z "$V" ] && V=$(opkg list-installed 2>/dev/null | awk '$1=="opennds"{print $3}'); echo "@@nds ${V:--} $(uci -q get opennds.@opennds[0].enabled || echo 0) $(pidof opennds >/dev/null && echo 1 || echo 0)"
[ -f /etc/rl-portal/profile.json ] && echo "@@profile $(cat /etc/rl-portal/profile.json)"
if uci -q show network | grep -q '=switch_vlan'; then
  echo "@@swconfig 1"
  i=0
  for SW in $(uci -q show network | sed -n "s/^network\.@switch\[[0-9]*\]\.name='\(.*\)'$/\1/p"); do
    ETH=$(jsonfilter -i /etc/board.json -e "@.switch.$SW.ports[@.device].device" 2>/dev/null | head -1)
    CPU=$(jsonfilter -i /etc/board.json -e "@.switch.$SW.ports[@.device].num" 2>/dev/null | head -1)
    VID=$(jsonfilter -i /etc/board.json -e "@.switch.$SW.roles[@.role='lan'].device" 2>/dev/null | head -1 | sed 's/.*\.//')
    for n in $(jsonfilter -i /etc/board.json -e "@.switch.$SW.ports[@.role='lan'].num" 2>/dev/null); do
      L=$(swconfig dev $SW port $n get link 2>/dev/null); U=down; case "$L" in *link:up*) U=up;; esac
      echo "@@swp s${i}p${n} $SW $n ${CPU:-0} ${ETH:-eth$i} ${VID:-1} $U $(echo "$L" | sed -n 's/.*speed:\([0-9]*\).*/\1/p' | grep . || echo 0)"
    done
    i=$((i+1))
  done
fi
[ ! -f /etc/rl-portal/profile.json ] && [ "$(uci -q get opennds.@opennds[0].enabled)" = 1 ] && echo "@@foreign $(uci -q get opennds.@opennds[0].gatewayname | tr -d '|')|$(basename "$(uci -q get opennds.@opennds[0].themespec_path)" 2>/dev/null)|$(uci -q get opennds.@opennds[0].sessiontimeout)"
command -v ndsctl >/dev/null 2>&1 && echo "@@clients $(ndsctl json 2>/dev/null | grep -c '"mac"')"
echo "@@wanip $(ip -4 -o addr show dev $(uci -q get network.wan.device || echo $W) 2>/dev/null | awk '{print $4}' | head -1)"
echo "@@lanip $(uci -q get network.lan.ipaddr)"
echo "@@wanmac $(cat /sys/class/net/$W/address 2>/dev/null)"
C=${SSH_CONNECTION%% *}
if [ -n "$C" ]; then
  echo "@@via $(ip route get $C 2>/dev/null | sed -n 's/.* dev \([^ ]*\).*/\1/p' | head -1)"
  M=$(ip neigh show $C 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="lladdr") print $(i+1)}' | head -1)
  N=$( [ -n "$M" ] && brctl showmacs br-lan 2>/dev/null | awk -v m="$M" '$2==m{print $1; exit}')
  [ -n "$N" ] && for f in /sys/class/net/*/brport/port_no; do [ "$(( $(cat $f) ))" = "$N" ] && echo "@@mgmt $(echo $f | cut -d/ -f5)"; done
fi
grep -q "^root::" /etc/shadow 2>/dev/null && echo "@@nopass"
[ -f /tmp/rl-rollback.pid ] && echo "@@rollback 1"
echo "@@end"
'''


def parse_status(out):
    hw = {'model': '', 'rel': '', 'pm': 'opkg', 'free': 0, 'lan': [], 'wan': '', 'links': {}, 'radios': [], 'nds': None, 'ndsEnabled': False,
          'ndsRunning': False, 'profile': None, 'foreign': None, 'swconfig': False, 'swports': {}, 'clients': None, 'wanip': '', 'lanip': '', 'via': '', 'mgmt': '', 'rollback': False, 'wanmac': '', 'nopass': False}
    for line in out.splitlines():
        if not line.startswith('@@'):
            continue
        k, _, v = line[2:].partition(' ')
        v = v.strip()
        if k in ('model', 'rel', 'pm', 'wan', 'wanip', 'lanip', 'via', 'mgmt', 'wanmac'):
            hw[k] = v
        elif k == 'free':
            hw['free'] = int(v) if v.isdigit() else 0
        elif k == 'lan':
            hw['lan'] = v.split()
        elif k == 'link':
            a = v.split()
            if len(a) >= 3:
                hw['links'][a[0]] = {'up': a[1] == '1', 'speed': int(a[2]) if a[2].lstrip('-').isdigit() and int(a[2]) > 0 else None}
        elif k == 'radio':
            a = v.split()
            if len(a) == 2 and a[1] in ('2g', '5g', '6g'):
                hw['radios'].append({'name': a[0], 'band': a[1]})
        elif k == 'nds':
            a = v.split()
            hw['nds'] = a[0] if a and a[0] != '-' else None
            hw['ndsEnabled'] = len(a) > 1 and a[1] == '1'
            hw['ndsRunning'] = len(a) > 2 and a[2] == '1'
        elif k == 'profile':
            try:
                hw['profile'] = json.loads(v)
            except ValueError:
                pass
        elif k == 'swconfig':                   # старый коммутатор (swconfig, switch_vlan, как MikroTik RB2011): VLAN настраиваются иначе, чем в DSA (bridge-vlan)
            hw['swconfig'] = True
        elif k == 'swp':                        # порт s<коммутатор>p<номер> <switch> <номер> <порт CPU> <eth CPU> <vlan LAN> <up|down> <скорость>
            a = v.split()
            if len(a) >= 8 and a[2].isdigit() and a[3].isdigit() and a[5].isdigit():
                hw['swports'][a[0]] = {'switch': a[1], 'num': int(a[2]), 'cpu': int(a[3]), 'eth': a[4], 'vid': int(a[5]), 'up': a[6] == 'up',
                                       'speed': int(a[7]) if a[7].isdigit() and int(a[7]) > 0 else None}
        elif k == 'foreign':                    # OpenNDS включён, а нашего профиля нет: портал настроен вручную (имя | файл темы | минут сессии)
            name, theme, mins = (v.split('|') + ['', '', ''])[:3]
            hw['foreign'] = {'name': name.strip() or 'без имени', 'theme': theme.strip(), 'hours': round(int(mins) / 60, 1) if mins.strip().isdigit() else None}
        elif k == 'clients':
            hw['clients'] = int(v) if v.isdigit() else None
        elif k == 'rollback':
            hw['rollback'] = True
        elif k == 'nopass':
            hw['nopass'] = True
    if hw['wanip'] and '/' not in hw['wanip']:
        hw['wanip'] = ''
    if hw['swconfig'] and hw['swports']:        # порты у такого роутера — гнёзда коммутатора, а не имена из board.json
        hw['lan'] = list(hw['swports'])
        for n, sp in hw['swports'].items():
            hw['links'][n] = {'up': sp['up'], 'speed': sp['speed']}
    return hw


# ───────── шаблоны страницы входа ─────────
ALLOWED = re.compile(r'\.(html?|css|js|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|txt|json)$', re.I)
MAX_BYTES, MAX_FILES = 3 * 1024 * 1024, 80
SAMPLE = {'name': 'Гостевой Wi-Fi', 'hours': '24', 'error': '',
          'form': '<form class="rl-form" onsubmit="return false"><label class="rl-terms"><input type="checkbox" checked> Принимаю <a href="#rl-rules">правила пользования</a></label>'
                  '<button class="rl-btn" type="button">Подключиться</button></form>',
          'rules': '<div id="rl-rules" class="rl-rules">Пример правил: не нарушать законы, не мешать другим гостям.</div>', 'continue': '#'}


def check_zip(data):
    """.zip шаблона → {путь: байты} или ValueError. index.html обязателен и должен содержать {{form}}."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError('это не .zip-архив')
    items = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/') and not i.filename.split('/')[-1].startswith('.')]
    if not items:
        raise ValueError('архив пустой')
    if len(items) > MAX_FILES:
        raise ValueError(f'слишком много файлов: {len(items)} (можно до {MAX_FILES})')
    names = [i.filename.replace('\\', '/') for i in items]
    tops = {n.split('/')[0] for n in names}
    strip = len(tops) == 1 and all('/' in n for n in names)            # всё в одной папке → эту папку отбрасываем
    files, total = {}, 0
    for i, n in zip(items, names):
        path = n.split('/', 1)[1] if strip else n
        parts = path.split('/')
        if not path or path.startswith('/') or any(x in ('', '.', '..') for x in parts) or len(parts) > 3:
            raise ValueError(f'недопустимый путь в архиве: {n}')
        if not re.fullmatch(r'[A-Za-z0-9._/-]+', path):
            raise ValueError(f'имя файла только латиницей, цифрами, «.», «-» и «_»: {path}')
        if not ALLOWED.search(path):
            raise ValueError(f'такой тип файла нельзя: {path} (можно html, css, js, картинки, шрифты)')
        total += i.file_size
        if total > MAX_BYTES:
            raise ValueError('шаблон больше 3 МБ — уменьшите картинки')
        files[path] = z.read(i)
    if 'index.html' not in files:
        raise ValueError('в шаблоне нет index.html (главная страница входа)')
    if b'{{form}}' not in files['index.html']:
        raise ValueError('в index.html нет метки {{form}} — на её место встанет кнопка «Подключиться»')
    return files


def default_files():
    base = os.path.join(ASSETS, 'default')
    return {n: open(os.path.join(base, n), 'rb').read() for n in sorted(os.listdir(base))}


def fill(text, values):
    for k, v in values.items():
        text = text.replace('{{' + k + '}}', v)
    return text


class Templates:
    """библиотека шаблонов в data/portal/templates/<id>/ (+ meta.json); «default» — встроенный, удалить нельзя"""

    def __init__(self, data_dir):
        self.dir = os.path.join(data_dir, 'portal', 'templates')

    def list(self):
        out = [{'id': 'default', 'name': 'Стандартный (Rack Live)', 'builtin': True}]
        if os.path.isdir(self.dir):
            for tid in sorted(os.listdir(self.dir)):
                try:
                    out.append(dict(json.load(open(os.path.join(self.dir, tid, 'meta.json'), encoding='utf-8')), id=tid))
                except (OSError, ValueError):
                    continue
        return out

    def add(self, name, data):
        files = check_zip(data)
        tid = 't' + secrets.token_hex(4)
        d = os.path.join(self.dir, tid)
        for path, b in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, 'f', path)), exist_ok=True)
            with open(os.path.join(d, 'f', path), 'wb') as f:
                f.write(b)
        meta = {'name': re.sub(r'\s+', ' ', str(name or '')).strip()[:60] or 'Мой шаблон', 't': int(time.time()), 'files': len(files),
                'bytes': sum(len(b) for b in files.values()), 'done': 'done.html' in files}
        with open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)
        return dict(meta, id=tid)

    def delete(self, tid):
        if tid == 'default' or not re.fullmatch(r't[0-9a-f]{8}', tid or ''):
            raise ValueError('этот шаблон удалить нельзя')
        shutil.rmtree(os.path.join(self.dir, tid), ignore_errors=True)

    def files(self, tid):
        if tid == 'default':
            return default_files()
        if not re.fullmatch(r't[0-9a-f]{8}', tid or ''):
            raise ValueError('нет такого шаблона')
        root = os.path.join(self.dir, tid, 'f')
        if not os.path.isdir(root):
            raise ValueError('нет такого шаблона')
        out = {}
        for dp, _, fs in os.walk(root):
            for n in fs:
                full = os.path.join(dp, n)
                out[os.path.relpath(full, root).replace('\\', '/')] = open(full, 'rb').read()
        return out

    def file(self, tid, path):
        f = self.files(tid)
        if path not in f:
            raise ValueError('нет такого файла')
        return f[path]

    def preview(self, tid, page='index.html', name=None):
        f = self.files(tid)
        page = page if page in f else 'index.html'
        html = f[page].decode('utf-8', 'replace')
        return fill(html, dict(SAMPLE, name=name or SAMPLE['name'], assets=f'/api/portal/templates/{tid}/f'))


def files_b64(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for path, b in sorted(files.items()):
            ti = tarfile.TarInfo(path); ti.size = len(b); ti.mode = 0o644; ti.mtime = int(time.time())
            t.addfile(ti, io.BytesIO(b))
    return base64.b64encode(buf.getvalue()).decode()


# ───────── скрипты для роутера ─────────
def _q(v):
    return "'" + str(v).replace("'", "'\\''") + "'"


def _html(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def portal_conf(p):
    """/etc/rl-portal/conf — что читает тема OpenNDS при каждом заходе гостя"""
    rules = '<div id="rl-rules" class="rl-rules">' + _html(p['rules']).replace('\n', '<br>') + '</div>' if p['rules'] else ''
    vals = {'RL_LOGIN': p['login'], 'RL_PASSHASH': hashlib.sha256(p['password'].encode()).hexdigest() if p['password'] else '',
            'RL_MIN': p['hours'] * 60, 'RL_UP': p['up'] * 1000, 'RL_DOWN': p['down'] * 1000, 'RL_name': _html(p['name']),
            'RL_hours': str(p['hours']), 'RL_rules': rules, 'RL_terms': '1' if p['rules'] else '', 'RL_after': _html(p.get('after', DEFAULTS['after']) or '')}
    vals.update({'RL_SMSHOST': p.get('smsHost', ''), 'RL_SMSPORT': p.get('smsPort', 22), 'RL_SMSUSER': p.get('smsUser', 'root'), 'RL_SMSTAIL': sms_tail(p)})
    return ''.join(f'{k}={_q(v)}\n' for k, v in vals.items())


def sms_tail(p):
    """the SMS is «<code> — код для входа в Wi-Fi «name»»: the code is added by the router, this is the rest, as UCS2 hex"""
    text = f" — код для входа в Wi-Fi «{p.get('name') or DEFAULTS['name']}»"
    return ''.join('%04X' % ord(c) for c in text)


def router_profile(p):
    """what is written on the router: no SIM-router password (it is needed once, to prepare that router)"""
    return json.dumps({k: v for k, v in p.items() if k != 'smsPass'}, ensure_ascii=False)


def push_files_script(b64):
    """шаблон → /etc/opennds/htdocs/rl/ (раскодирует ucode: base64 в OpenWrt нет)"""
    return f"""mkdir -p /tmp/rl-tpl && cat > /tmp/rl-tpl/t.b64 <<'RLEOF'
{b64}
RLEOF
ucode -e 'import * as fs from "fs"; fs.writefile("/tmp/rl-tpl/t.tgz", b64dec(trim(fs.readfile("/tmp/rl-tpl/t.b64"))));' || {{ echo "@@fail не удалось распаковать шаблон на роутере"; exit 0; }}
rm -rf /tmp/rl-tpl/x && mkdir -p /tmp/rl-tpl/x && tar xzf /tmp/rl-tpl/t.tgz -C /tmp/rl-tpl/x || {{ echo "@@fail архив шаблона повреждён"; exit 0; }}
[ -f /tmp/rl-tpl/x/index.html ] || {{ echo "@@fail в шаблоне нет index.html"; exit 0; }}
mkdir -p /etc/opennds/htdocs && rm -rf /etc/opennds/htdocs/rl && mv /tmp/rl-tpl/x /etc/opennds/htdocs/rl && rm -rf /tmp/rl-tpl
echo "@@tpl ok"
"""


def theme_script():
    return open(os.path.join(ASSETS, 'theme_rl.sh'), encoding='utf-8').read()


def _hosts(net):
    n = ipaddress.ip_interface(net).network
    return max(4, n.num_addresses - 2)


def check_root_pass(v):
    v = str(v or '')
    if not 8 <= len(v) <= 64 or re.search(r'[\x00-\x1f]', v):
        raise ValueError('Пароль администратора роутера: от 8 до 64 символов')
    return v


def _swconfig_net(p, hw):
    """Сеть для роутеров со старым коммутатором (swconfig, switch_vlan — например MikroTik RB2011), где нет bridge-vlan.
    Основная сеть остаётся на br-lan (VLAN 1 коммутатора), гостевая — отдельный VLAN коммутатора и свой мост br-guest.
    Порты: main — только VLAN 1; guest — только гостевой VLAN; trunk — VLAN 1 без тега и гостевой с тегом; off — ни в одном.
    VLAN с WAN и всё, чего нет в списке портов, не трогаем: управление по WAN от перенастройки не зависит."""
    v, roles, sp = p['vlan'], p['ports'], hw['swports']
    by = {}
    for name, role in roles.items():
        if name in sp:
            by.setdefault(sp[name]['switch'], []).append((role, sp[name]))
    out = [r'''for x in $(uci -q show network | sed -n "s/^network\.\(rl_[^.=]*\)=\(switch_vlan\|device\)$/\1/p"); do uci delete network.$x; done
''']
    guest_eth = []
    for sw in sorted(by):
        items = by[sw]
        cpu, eth, vid = items[0][1]['cpu'], items[0][1]['eth'], items[0][1]['vid']
        main = [str(i['num']) for r, i in items if r in ('main', 'trunk')]
        guest = [str(i['num']) for r, i in items if r == 'guest'] + [f"{i['num']}t" for r, i in items if r == 'trunk']
        out.append(f'''for s in $(uci -q show network | sed -n "s/^network\\.\\(@switch_vlan\\[[0-9]*\\]\\)\\.device='{sw}'$/\\1/p"); do [ "$(uci -q get network.$s.vlan)" = "{vid}" ] && uci set network.$s.ports={_q(' '.join(main + [f'{cpu}t']))}; done
''')
        if guest:
            out.append(f"uci set network.rl_vg_{sw}=switch_vlan; uci set network.rl_vg_{sw}.device={sw}; uci set network.rl_vg_{sw}.vlan={v}; "
                       f"uci set network.rl_vg_{sw}.ports={_q(' '.join(guest + [f'{cpu}t']))}\n")
            guest_eth.append(f'{eth}.{v}')
    out.append('uci set network.rl_brg=device; uci set network.rl_brg.name=br-guest; uci set network.rl_brg.type=bridge\n')
    out += [f'uci add_list network.rl_brg.ports={_q(e)}\n' for e in guest_eth]
    return ''.join(out)


def apply_script(p, hw, b64, hello_url, token, root_pass=''):
    """полная настройка роли «Главный роутер»: пакеты и файлы — сразу; сеть — фоном после ответа, с таймером отката"""
    lan, guest = ipaddress.ip_interface(p['lan']), ipaddress.ip_interface(p['guest'])
    v, ports = p['vlan'], p['ports']
    main_ports = [f'{n}:u*' for n, r in ports.items() if r in ('main', 'trunk')]
    guest_ports = [f'{n}:u*' for n, r in ports.items() if r == 'guest'] + [f'{n}:t' for n, r in ports.items() if r == 'trunk']
    br_ports = [n for n, r in ports.items() if r != 'off']
    radios = {r['band']: r['name'] for r in hw['radios']}
    g_start, g_limit = 10, max(8, _hosts(p['guest']) - 20)
    lh = _hosts(p['lan']); l_start, l_limit = (100, 150) if lh >= 254 else (max(2, lh // 3), max(2, lh - lh // 3 - 1))
    s = [r'''PM=opkg; command -v apk >/dev/null 2>&1 && PM=apk
have() { if [ $PM = apk ]; then apk list --installed 2>/dev/null | grep -q "^$1-[0-9]"; else opkg list-installed 2>/dev/null | grep -q "^$1 "; fi; }
B=/etc/rl-portal
mkdir -p $B/bak-orig $B/bak-last
if [ ! -f $B/bak-orig/.done ]; then for f in ''' + ' '.join(CONFIGS) + r'''; do [ -f /etc/config/$f ] && cp /etc/config/$f $B/bak-orig/; done; touch $B/bak-orig/.done; fi
rm -f $B/bak-last/*; for f in ''' + ' '.join(CONFIGS) + r'''; do [ -f /etc/config/$f ] && cp /etc/config/$f $B/bak-last/; done
[ -x /etc/init.d/opennds ] && /etc/init.d/opennds stop >/dev/null 2>&1
rm -f /tmp/rl-restart.done /tmp/rl-portal-error
mkdir -p /usr/lib/opennds /etc/opennds/htdocs
echo "@@step Копирую шаблон страницы входа"
''', push_files_script(b64),
         "cat > /usr/lib/opennds/theme_rl.sh <<'RLEOF'\n" + theme_script() + "\nRLEOF\nchmod 644 /usr/lib/opennds/theme_rl.sh\n",
         "cat > $B/conf <<'RLEOF'\n" + portal_conf(p) + "RLEOF\n",
         "cat > $B/profile.json <<'RLEOF'\n" + router_profile(p) + "\nRLEOF\nchmod 600 $B/profile.json $B/conf\n" + (SMS_KEY if p.get("login") == "sms" else ""),
         # откат: если Rack Live не подтвердит связь — вернуть прежние настройки
         r'''cat > /tmp/rl-rollback.sh <<'RLEOF'
[ -f /tmp/rl-rollback.sh ] || exit 0
for f in ''' + ' '.join(CONFIGS) + r'''; do if [ -f /etc/rl-portal/bak-last/$f ]; then cp /etc/rl-portal/bak-last/$f /etc/config/$f; fi; done
logger -t rack-live "портал: Rack Live не подтвердил связь — возвращаю прежние настройки"
/etc/init.d/opennds stop; /etc/init.d/network restart; sleep 5; wifi reload; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart
[ "$(uci -q get opennds.@opennds[0].enabled)" = 1 ] && /etc/init.d/opennds start
rm -f /tmp/rl-rollback.sh /tmp/rl-rollback.pid
RLEOF
[ -f /tmp/rl-rollback.pid ] && kill $(cat /tmp/rl-rollback.pid) 2>/dev/null
setsid sh -c "sleep ''' + str(ROLLBACK_SEC) + r'''; sh /tmp/rl-rollback.sh" </dev/null >/dev/null 2>&1 &
echo $! > /tmp/rl-rollback.pid
echo "@@step Записываю настройки сети"
''' + (f"printf '%s\\n%s\\n' {_q(root_pass)} {_q(root_pass)} | passwd root >/dev/null 2>&1 && echo '@@rootpass ok'\n" if root_pass else '')]
    if hw.get('swconfig'):
        s.append(_swconfig_net(p, hw))
        lan_dev, guest_dev = 'br-lan', 'br-guest'
    else:
        s.append(r'''BR=$(for s in $(uci -q show network | sed -n "s/^network\.\([^.=]*\)=device$/\1/p"); do [ "$(uci -q get network.$s.name)" = br-lan ] && echo $s; done | head -1)
[ -z "$BR" ] && { BR=rl_br; uci set network.rl_br=device; uci set network.rl_br.name=br-lan; uci set network.rl_br.type=bridge; }
uci -q delete network.$BR.ports
''')
        s += [f'uci add_list network.$BR.ports={_q(n)}\n' for n in br_ports]
        s.append(f'''for x in $(uci -q show network | sed -n "s/^network\\.\\(rl_[^.=]*\\)=bridge-vlan$/\\1/p"); do uci delete network.$x; done
uci set network.rl_v1=bridge-vlan; uci set network.rl_v1.device=br-lan; uci set network.rl_v1.vlan=1
uci set network.rl_vg=bridge-vlan; uci set network.rl_vg.device=br-lan; uci set network.rl_vg.vlan={v}
''')
        s += [f'uci add_list network.rl_v1.ports={_q(x)}\n' for x in main_ports]
        s += [f'uci add_list network.rl_vg.ports={_q(x)}\n' for x in guest_ports]
        lan_dev, guest_dev = 'br-lan.1', f'br-lan.{v}'
    s.append(f'''uci set network.lan.device={lan_dev}; uci set network.lan.proto=static; uci set network.lan.ipaddr={_q(str(lan))}
uci -q delete network.lan.netmask; uci -q delete network.lan.gateway; uci -q delete network.lan.dns
uci set network.rl_guest=interface; uci set network.rl_guest.proto=static; uci set network.rl_guest.device={guest_dev}; uci set network.rl_guest.ipaddr={_q(str(guest))}
uci set network.wan.device={_q(hw['wan'] or 'wan')}; uci set network.wan.proto=dhcp
uci -q delete dhcp.lan.ignore; uci set dhcp.lan.interface=lan; uci set dhcp.lan.start={l_start}; uci set dhcp.lan.limit={l_limit}; uci set dhcp.lan.leasetime=12h
uci set dhcp.lan.dhcpv4=server; uci set dhcp.lan.dhcpv6=server; uci set dhcp.lan.ra=server
uci set dhcp.rl_guest=dhcp; uci set dhcp.rl_guest.interface=rl_guest; uci set dhcp.rl_guest.start={g_start}; uci set dhcp.rl_guest.limit={g_limit}
uci set dhcp.rl_guest.leasetime=2h; uci set dhcp.rl_guest.dhcpv4=server; uci -q delete dhcp.rl_guest.ignore
for x in $(uci -q show firewall | sed -n "s/^firewall\\.\\(rl_[^.=]*\\)=.*/\\1/p"); do uci delete firewall.$x; done
uci set firewall.rl_zone=zone; uci set firewall.rl_zone.name=rlguest; uci add_list firewall.rl_zone.network=rl_guest
uci set firewall.rl_zone.input=REJECT; uci set firewall.rl_zone.output=ACCEPT; uci set firewall.rl_zone.forward=REJECT
uci set firewall.rl_fwd=forwarding; uci set firewall.rl_fwd.src=rlguest; uci set firewall.rl_fwd.dest=wan
uci set firewall.rl_dns=rule; uci set firewall.rl_dns.name='Гости: DNS'; uci set firewall.rl_dns.src=rlguest; uci set firewall.rl_dns.dest_port=53; uci set firewall.rl_dns.target=ACCEPT
uci set firewall.rl_dhcp=rule; uci set firewall.rl_dhcp.name='Гости: DHCP'; uci set firewall.rl_dhcp.src=rlguest; uci set firewall.rl_dhcp.proto=udp; uci set firewall.rl_dhcp.dest_port='67-68'; uci set firewall.rl_dhcp.target=ACCEPT
uci set firewall.rl_nds=rule; uci set firewall.rl_nds.name='Гости: страница входа'; uci set firewall.rl_nds.src=rlguest; uci set firewall.rl_nds.proto=tcp; uci set firewall.rl_nds.dest_port=2050; uci set firewall.rl_nds.target=ACCEPT
''')
    if p['mgmtWan']:
        s.append('''uci set firewall.rl_mgmt=rule; uci set firewall.rl_mgmt.name='Rack Live: управление из частной сети за WAN'; uci set firewall.rl_mgmt.src=wan
uci set firewall.rl_mgmt.proto=tcp; uci set firewall.rl_mgmt.dest_port='22 80 443'; uci set firewall.rl_mgmt.family=ipv4; uci set firewall.rl_mgmt.target=ACCEPT
uci add_list firewall.rl_mgmt.src_ip=10.0.0.0/8; uci add_list firewall.rl_mgmt.src_ip=172.16.0.0/12; uci add_list firewall.rl_mgmt.src_ip=192.168.0.0/16
''')
    s.append('for x in $(uci -q show wireless | sed -n "s/^wireless\\.\\(rl_[^.=]*\\)=wifi-iface$/\\1/p"); do uci delete wireless.$x; done\n')
    for band in p['bands']:
        r = radios[band]
        enc_main = f"uci set wireless.rl_main_{band}.encryption=sae-mixed; uci set wireless.rl_main_{band}.key={_q(p['mainKey'])}"
        enc_g = (f"uci set wireless.rl_guest_{band}.encryption=sae-mixed; uci set wireless.rl_guest_{band}.key={_q(p['guestKey'])}" if p['guestKey']
                 else f"uci set wireless.rl_guest_{band}.encryption=none")
        main_lines = (f'''uci set wireless.rl_main_{band}=wifi-iface; uci set wireless.rl_main_{band}.device={r}; uci set wireless.rl_main_{band}.mode=ap; uci set wireless.rl_main_{band}.network=lan; uci set wireless.rl_main_{band}.ssid={_q(p['mainSsid'])}
{enc_main}
''' if p.get('mainWifi', True) else '')
        s.append(f'''uci set wireless.{r}.disabled=0; uci set wireless.{r}.country={p['country']}
{main_lines}uci set wireless.rl_guest_{band}=wifi-iface; uci set wireless.rl_guest_{band}.device={r}; uci set wireless.rl_guest_{band}.mode=ap; uci set wireless.rl_guest_{band}.network=rl_guest; uci set wireless.rl_guest_{band}.ssid={_q(p['guestSsid'])}
uci set wireless.rl_guest_{band}.isolate=1
{enc_g}
''')
    s.append(f'''uci commit network; uci commit dhcp; uci commit firewall; uci commit wireless
echo "@@step Перезапускаю сеть"
cat > /tmp/rl-restart.sh <<'RLEOF'
sleep 3
/etc/init.d/network restart; sleep 8; wifi reload; sleep 4
/etc/init.d/dnsmasq restart; /etc/init.d/firewall restart
# OpenNDS: installed only now — before the restart the router may have had no internet (its LAN overlapped the WAN)
PM=opkg; command -v apk >/dev/null 2>&1 && PM=apk
have() {{ if [ $PM = apk ]; then apk list --installed 2>/dev/null | grep -q "^$1-[0-9]"; else opkg list-installed 2>/dev/null | grep -q "^$1 "; fi; }}
n=0; while ! have opennds && [ $n -lt 6 ]; do
  if [ $PM = apk ]; then apk update >/dev/null 2>&1; apk add opennds; else opkg update >/dev/null 2>&1; opkg install opennds; fi
  n=$((n+1)); have opennds || sleep 10
done
if have opennds; then
  uci -q get opennds.@opennds[0] >/dev/null || uci add opennds opennds >/dev/null
  uci set opennds.@opennds[0].enabled={1 if p['portal'] else 0}; uci set opennds.@opennds[0].gatewayinterface={guest_dev}
  uci set opennds.@opennds[0].gatewayname={_q(p['name'])}; uci set opennds.@opennds[0].login_option_enabled=3
  uci set opennds.@opennds[0].themespec_path=/usr/lib/opennds/theme_rl.sh; uci set opennds.@opennds[0].sessiontimeout={p['hours'] * 60}
  uci set opennds.@opennds[0].preauthidletimeout=15; uci set opennds.@opennds[0].authidletimeout={p['hours'] * 60}
  uci commit opennds
  if [ "$(uci -q get opennds.@opennds[0].enabled)" = 1 ]; then /etc/init.d/opennds enable; /etc/init.d/opennds restart; else /etc/init.d/opennds stop; /etc/init.d/opennds disable; fi
else
  echo "OpenNDS не установился" > /tmp/rl-portal-error
fi
n=0; while [ "$(uci -q get opennds.@opennds[0].enabled)" = 1 ] && ! pidof opennds >/dev/null && [ $n -lt 15 ]; do sleep 2; n=$((n+1)); done
touch /tmp/rl-restart.done
i=0; while [ $i -lt 30 ]; do
  W=$(ip -4 -o addr show dev $(uci -q get network.wan.device) 2>/dev/null | awk '{{print $4}}' | cut -d/ -f1 | head -1)
  wget -q -T 5 -O /dev/null "{hello_url}/api/portal/hello?k={token}&wan=$W&lan={lan.ip}" 2>/dev/null && break
  i=$((i+1)); sleep 6
done
RLEOF
setsid sh /tmp/rl-restart.sh </dev/null >/tmp/rl-restart.log 2>&1 &
echo "@@scheduled"
''')
    return ''.join(s)


# чужой DHCP-сервер в основной сети: значит, в LAN-порт воткнут провод от другого роутера — наш DHCP начнёт раздавать адреса чужой сети
FOREIGN_DHCP = 'udhcpc -i br-lan -n -q -t 2 -T 2 -s /bin/true >/dev/null 2>&1 && echo "@@foreign" || echo "@@clean"\n'

def prepare_wan_script(new_lan):
    """open management from behind WAN and move the LAN out of the network the cable comes from: after the cable moves to WAN
    the router gets an address in that same network there — with the LAN still in it the answers would go out of the empty LAN ports"""
    return PREPARE_WAN + f'''uci set network.lan.ipaddr={_q(new_lan)}; uci -q delete network.lan.netmask; uci -q delete network.lan.gateway; uci -q delete network.lan.dns
uci set dhcp.lan.ignore=1; uci commit network; uci commit dhcp
echo "@@lan {new_lan}"
setsid sh -c 'sleep 4; /etc/init.d/network restart; sleep 6; /etc/init.d/firewall reload' </dev/null >/dev/null 2>&1 &
'''


def free_lan(current):
    """a LAN for the router that does not overlap the network it is in now (that network will be on its WAN)"""
    try:
        cur = ipaddress.ip_interface(current).network
    except ValueError:
        cur = None
    for c in ('192.168.10.1/24', '192.168.20.1/24', '172.16.10.1/24', '10.10.10.1/24'):
        if not cur or not ipaddress.ip_interface(c).network.overlaps(cur):
            return c
    return '10.10.10.1/24'


PREPARE_WAN = r'''uci -q delete firewall.rl_mgmt
uci set firewall.rl_mgmt=rule; uci set firewall.rl_mgmt.name='Rack Live: управление из частной сети за WAN'; uci set firewall.rl_mgmt.src=wan
uci set firewall.rl_mgmt.proto=tcp; uci set firewall.rl_mgmt.dest_port='22 80 443'; uci set firewall.rl_mgmt.family=ipv4; uci set firewall.rl_mgmt.target=ACCEPT
uci add_list firewall.rl_mgmt.src_ip=10.0.0.0/8; uci add_list firewall.rl_mgmt.src_ip=172.16.0.0/12; uci add_list firewall.rl_mgmt.src_ip=192.168.0.0/16
uci set network.wan.proto=dhcp; uci commit firewall; uci commit network
/etc/init.d/firewall reload >/dev/null 2>&1
W=$(uci -q get network.wan.device || jsonfilter -i /etc/board.json -e '@.network.wan.device'); echo "@@wanmac $(cat /sys/class/net/$W/address 2>/dev/null)"
'''

CONFIRM = r'''[ -f /tmp/rl-rollback.pid ] && kill $(cat /tmp/rl-rollback.pid) 2>/dev/null
rm -f /tmp/rl-rollback.sh /tmp/rl-rollback.pid
echo "@@confirmed"
'''

VERIFY = r'''[ -f /tmp/rl-restart.done ] && echo "@@done 1"
[ -f /tmp/rl-portal-error ] && echo "@@err $(cat /tmp/rl-portal-error)"
echo "@@g $(ip -4 -o addr show dev $(uci -q get network.rl_guest.device) 2>/dev/null | awk '{print $4}' | head -1)"
echo "@@w $(ubus call network.wireless status 2>/dev/null | grep -c '"ifname"')"
echo "@@n $(pidof opennds >/dev/null && echo 1 || echo 0)"
echo "@@d $(pidof dnsmasq >/dev/null && echo 1 || echo 0)"
'''


def toggle_script(on):
    return (f"uci set opennds.@opennds[0].enabled={1 if on else 0}; uci commit opennds\n"
            + ("/etc/init.d/opennds enable; /etc/init.d/opennds restart\n" if on else "/etc/init.d/opennds stop; /etc/init.d/opennds disable\n")
            + "sleep 2; echo \"@@nds $(pidof opennds >/dev/null && echo 1 || echo 0)\"\n"
            + "[ -f /etc/rl-portal/profile.json ] && sed -i 's/\"portal\": *[a-z]*/\"portal\": " + ('true' if on else 'false') + "/' /etc/rl-portal/profile.json\n")


# the key this router signs in to the SIM router with (it can only send SMS there: the key is bound to a forced command)
SMS_KEY = r'''mkdir -p /etc/rl-portal
[ -f /etc/rl-portal/sms_rsa ] || dropbearkey -t rsa -s 2048 -f /etc/rl-portal/sms_rsa >/dev/null 2>&1
chmod 600 /etc/rl-portal/sms_rsa 2>/dev/null
echo "@@smspub $(dropbearkey -y -f /etc/rl-portal/sms_rsa 2>/dev/null | grep '^ssh-')"
'''


def phone(v):
    """a phone number as the guest types it → +79001234567 (or ValueError)"""
    d = re.sub(r'\D', '', str(v or ''))
    if len(d) == 11 and d[0] == '8':
        d = '7' + d[1:]
    elif len(d) == 10 and d[0] == '9':
        d = '7' + d
    if not 11 <= len(d) <= 15:
        raise ValueError('Номер телефона вида +7 900 123-45-67')
    return '+' + d


def _asset(name):
    return open(os.path.join(ASSETS, name), encoding='utf-8').read().replace('\r\n', '\n')


def sms_setup_script(p):
    """runs on the PORTAL router: signs in to the SIM router by password (the password goes through the environment, once), puts the sender on it
    and binds the portal router's key to it. The SIM router gets internet through the portal router only to install one small package (stty)."""
    return f'''B=/etc/rl-portal; mkdir -p $B
command -v dbclient >/dev/null 2>&1 || {{ echo "@@fail на этом роутере нет dbclient (нужен SSH-клиент dropbear)"; exit 0; }}
[ -f $B/sms_rsa ] || dropbearkey -t rsa -s 2048 -f $B/sms_rsa >/dev/null 2>&1
PUB=$(dropbearkey -y -f $B/sms_rsa 2>/dev/null | grep '^ssh-'); [ -n "$PUB" ] || {{ echo "@@fail не получилось создать ключ"; exit 0; }}
H={_q(p['smsHost'])}
export DROPBEAR_PASSWORD={_q(p['smsPass'])}
G="dbclient -y -y -p {int(p['smsPort'])} {p['smsUser']}@$H"
MYIP=$(ip -4 route get $H 2>/dev/null | sed -n 's/.* src \\([0-9.]*\\).*/\\1/p' | head -1)
echo "@@step Захожу на роутер с SIM"
$G 'echo rl-ok' </dev/null 2>/dev/null | grep -q rl-ok || {{ echo "@@fail не получилось зайти на $H: проверьте адрес, логин и пароль, и что провод от него в LAN главного роутера"; exit 0; }}
$G 'cat > /tmp/rl-gw.sh' <<'RLGW'
{_asset('sms_gw.sh')}
RLGW
$G 'cat > /tmp/rl-sms.new' <<'RLSMS'
{_asset('rl-sms')}
RLSMS
echo "$PUB" | $G 'cat > /tmp/rl-pub'
if [ "$($G 'command -v stty >/dev/null 2>&1 && echo y' </dev/null 2>/dev/null)" != y ]; then
  echo "@@step Настраиваю выход роутера с SIM в интернет через этот роутер"
  $G "sh /tmp/rl-gw.sh net $MYIP" </dev/null 2>/dev/null
  n=0; while [ $n -lt 40 ]; do sleep 3; $G 'ping -c1 -W2 downloads.openwrt.org >/dev/null 2>&1 && echo y' </dev/null 2>/dev/null | grep -q y && break; n=$((n+1)); done
fi
$G 'sh /tmp/rl-gw.sh sms' </dev/null 2>&1 | grep '^@@'
echo "@@step Проверяю связь по ключу"
dbclient -y -y -i $B/sms_rsa -p {int(p['smsPort'])} {p['smsUser']}@$H status </dev/null 2>/dev/null | sed 's/^/@@gw /'
'''


def sms_send_script(p, number, text):
    """one real SMS from the portal router through the SIM router (a test, with the key the guests' codes go with)"""
    hexs = ''.join('%04X' % ord(c) for c in text)
    return (f"dbclient -y -y -i /etc/rl-portal/sms_rsa -p {int(p['smsPort'])} {p['smsUser']}@{p['smsHost']} 'send {number} {hexs}' </dev/null 2>&1 | head -5\n")


def login_script(p):
    """only the guest login (button / password, hours, speed, name, rules, where to go after) — the network is not touched, nothing restarts"""
    return ("cat > /usr/lib/opennds/theme_rl.sh <<'RLTHEME'\n" + theme_script().rstrip('\n') + "\nRLTHEME\nchmod 755 /usr/lib/opennds/theme_rl.sh\n"
            + "cat > /etc/rl-portal/conf <<'RLEOF'\n" + portal_conf(p) + "RLEOF\n"
            + "cat > /etc/rl-portal/profile.json <<'RLEOF'\n" + router_profile(p) + "\nRLEOF\nchmod 600 /etc/rl-portal/profile.json /etc/rl-portal/conf\n"
            + (SMS_KEY if p.get('login') == 'sms' else '')
            + f"uci set opennds.@opennds[0].sessiontimeout={p['hours'] * 60}; uci set opennds.@opennds[0].authidletimeout={p['hours'] * 60}; uci commit opennds\n"
            + "echo @@ok\n")


def template_script(b64, p):
    return (push_files_script(b64) + "cat > /etc/rl-portal/conf <<'RLEOF'\n" + portal_conf(p) + "RLEOF\n"
            + "cat > /etc/rl-portal/profile.json <<'RLEOF'\n" + router_profile(p) + "\nRLEOF\nchmod 600 /etc/rl-portal/profile.json /etc/rl-portal/conf\n")


REMOVE = r'''B=/etc/rl-portal
[ -f $B/bak-orig/.done ] || { echo "@@fail нет сохранённых исходных настроек — вернуть нечего"; exit 0; }
echo "@@oldlan $(sed -n "/config interface 'lan'/,/^config/s/.*option ipaddr '\([^']*\)'.*/\1/p" $B/bak-orig/network | head -1)"
cat > /tmp/rl-remove.sh <<'RLEOF'
sleep 3
/etc/init.d/opennds stop; /etc/init.d/opennds disable
for f in network wireless dhcp firewall opennds; do if [ -f /etc/rl-portal/bak-orig/$f ]; then cp /etc/rl-portal/bak-orig/$f /etc/config/$f; fi; done
rm -f /usr/lib/opennds/theme_rl.sh; rm -rf /etc/opennds/htdocs/rl /tmp/rl-rollback.sh /tmp/rl-rollback.pid /tmp/rl-restart.* /tmp/rl-portal-error
if command -v apk >/dev/null 2>&1; then apk del opennds >/dev/null 2>&1; else opkg remove --autoremove opennds >/dev/null 2>&1; fi
[ -f /etc/rl-portal/bak-orig/opennds ] || rm -f /etc/config/opennds
rm -rf /etc/rl-portal
/etc/init.d/network restart; sleep 8; wifi reload; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart
RLEOF
setsid sh /tmp/rl-remove.sh </dev/null >/dev/null 2>&1 &
echo "@@scheduled"
'''
