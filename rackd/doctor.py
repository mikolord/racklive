"""«Сетевой доктор»: a checkup of ONE chosen device from the user's own list.

Three sources, each honest about what it could see:
  inside  a read-only script over SSH: what listens and which program, SSH settings, fail2ban and the like, firewall, updates, accounts, failed logins, Docker
  ports   Rack Live knocks on the device's TCP ports (never on routers and switches: a burst to closed ports makes them shut Rack Live out for ~15 min, see netscan.infra_ips)
  audit   what security.audit already knows about the device (forwards, remote access, default passwords, firmware), with its own fix buttons

The script changes nothing and never prints password hashes. The only change the doctor can make is installing fail2ban, on a press with a confirmation.
"""
import concurrent.futures, ipaddress, re, secrets, shlex, socket, threading, time

from . import extscan, netscan, security
from .util import DriverError

KNOCK_EXTRA = [81, 2222, 2375, 2376, 5984, 8000, 8006, 8081, 8888, 9000, 9090, 9200, 10000, 11211, 1433]
RISKY = {**security.RISKY_PORTS, **{
    2375: ('bad', 'Docker API без шифрования', 'кто подключится, получит полный контроль над сервером'),
    9200: ('bad', 'Elasticsearch', 'база данных не должна быть видна из интернета'),
    11211: ('bad', 'Memcached', 'кэш без пароля, его используют для атак на других'),
    5984: ('bad', 'CouchDB', 'база данных не должна быть видна из интернета'),
    1433: ('bad', 'MS SQL', 'база данных не должна быть видна из интернета'),
    10000: ('warn', 'Webmin', 'панель управления сервером открыта в интернет'),
    8006: ('warn', 'Proxmox', 'панель гипервизора открыта в интернет'),
}}
ROUTER_DRIVERS = ('keenetic', 'openwrt', 'demo_router', 'demo_openwrt')
NO_KNOCK_KINDS = ('router', 'switch', 'ap')
NO_KNOCK_DRIVERS = ROUTER_DRIVERS + ('tplink_jetstream', 'unmanaged', 'remote_web', 'demo_switch', 'site_node', 'ups')
INSIDE_DRIVERS = ('ssh', 'openwrt', 'synology', 'keenetic', 'demo_server')
COST = security.LEVEL_COST

# Read-only. Every section starts with @@name; a missing tool leaves its section empty, and the analysis says «не удалось проверить», not «всё хорошо».
SCRIPT = r'''export LC_ALL=C PATH="$PATH:/sbin:/usr/sbin:/usr/local/sbin:/usr/local/bin:/opt/bin:/opt/sbin:/usr/syno/bin:/usr/syno/sbin"
have(){ command -v "$1" >/dev/null 2>&1; }
T=""; have timeout && T="timeout 25"
echo @@id; id -u
echo @@os
[ -f /etc/os-release ] && . /etc/os-release && echo "id $ID" && echo "like $ID_LIKE" && echo "name $PRETTY_NAME"
[ -f /etc/VERSION ] && echo "syno $(grep -E '^productversion' /etc/VERSION | cut -d'"' -f2)"
[ -f /etc/openwrt_release ] && echo "openwrt yes"
[ -d /opt/etc/init.d ] && [ ! -f /etc/os-release ] && echo "entware yes"
echo "kernel $(uname -sr)"
echo @@listen
L=""; if have ss; then L=$(ss -H -tulnp 2>/dev/null); elif have netstat; then L=$(netstat -tulnp 2>/dev/null | grep -E '^(tcp|udp)'); fi
if [ -n "$L" ]; then echo "$L"; else
  # no ss, no netstat (some Entware on a Keenetic): the kernel's own tables are always there, without the program names
  for f in tcp tcp6; do [ -r /proc/net/$f ] && awk -v p="${f%6}" '$4=="0A"{print "proc " p " " $2}' /proc/net/$f; done
  for f in udp udp6; do [ -r /proc/net/$f ] && awk -v p="${f%6}" 'NR>1 && $3 ~ /:0000$/{print "proc " p " " $2}' /proc/net/$f; done
fi
echo @@sshd
if have sshd; then $T sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|permitemptypasswords|pubkeyauthentication|maxauthtries) '; fi
pidof dropbear >/dev/null 2>&1 && echo "dropbear yes"
echo @@guard
if have fail2ban-client; then echo installed
  if $T fail2ban-client ping 2>/dev/null | grep -qi pong; then echo running
    J=$($T fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr -d ' ' | tr ',' ' ')
    for j in $J; do S=$($T fail2ban-client status "$j" 2>/dev/null); echo "jail $j $(echo "$S" | sed -n 's/.*Currently banned:[[:space:]]*//p') $(echo "$S" | sed -n 's/.*Total banned:[[:space:]]*//p')"; done
  fi
fi
pidof crowdsec >/dev/null 2>&1 && echo "other CrowdSec"
pidof sshguard >/dev/null 2>&1 && echo "other SSHGuard"
echo @@fw
if have ufw; then $T ufw status 2>/dev/null | head -n 1 | sed 's/^Status: /ufw /'; fi
if have firewall-cmd; then echo "firewalld $($T firewall-cmd --state 2>/dev/null)"; fi
if have nft; then echo "nft_drop $($T nft list ruleset 2>/dev/null | grep -cE 'hook input.*policy drop')"; fi
if have iptables; then echo "ipt_policy $($T iptables -S INPUT 2>/dev/null | sed -n 's/^-P INPUT //p')"; echo "ipt_block $($T iptables -S INPUT 2>/dev/null | grep -vE 'f2b|DOCKER' | grep -cE -- '-j (DROP|REJECT)')"; fi
echo @@updates
if have apt-get; then
  O=$($T apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null | grep '^Inst')
  echo "pending $(echo "$O" | grep -c '^Inst')"; echo "security $(echo "$O" | grep -ci 'security')"
  echo "lists_fresh $(find /var/lib/apt/lists -maxdepth 1 -type f -mtime -7 2>/dev/null | wc -l)"
  dpkg -s unattended-upgrades 2>/dev/null | grep -q '^Status: install ok' && apt-config dump 2>/dev/null | grep -q 'Unattended-Upgrade "1"' && echo "auto yes" || echo "auto no"
elif have dnf; then
  echo "pending $($T dnf -q --cacheonly check-update 2>/dev/null | grep -c '\.')"; echo "security $($T dnf -q --cacheonly updateinfo list security 2>/dev/null | wc -l)"
  systemctl is-enabled dnf-automatic.timer 2>/dev/null | grep -q enabled && echo "auto yes" || echo "auto no"
elif have apk && [ ! -f /etc/openwrt_release ]; then echo "pending $($T apk -u list 2>/dev/null | wc -l)"; fi
[ -f /var/run/reboot-required ] && echo "reboot yes"
echo @@accounts
awk -F: '$3==0{print "uid0 " $1}' /etc/passwd 2>/dev/null
[ -r /etc/shadow ] && echo "shadow_read yes" && awk -F: '$2==""{print "emptypw " $1}' /etc/shadow 2>/dev/null
[ -f /etc/shadow ] && echo "shadow_mode $(stat -c '%a' /etc/shadow 2>/dev/null)"
grep -rhE '^[^#]*NOPASSWD' /etc/sudoers /etc/sudoers.d 2>/dev/null | awk '{print "nopasswd " $1}' | sort -u | head -n 10
echo @@auth
if have journalctl; then N=$($T journalctl -q --no-pager --since "24 hours ago" -t sshd -t sshd-session 2>/dev/null | grep -cE 'Failed password|Invalid user'); echo "fails $N"
elif [ -r /var/log/auth.log ]; then echo "fails $(tail -n 20000 /var/log/auth.log | grep -cE 'Failed password|Invalid user')"
elif have logread; then echo "fails $(logread 2>/dev/null | grep -ciE 'bad password|login attempt')"; fi
echo @@docker
if have docker; then $T docker ps --format '{{.Names}}|{{.Ports}}' 2>/dev/null | cut -c1-300 | head -n 60
  P=$($T docker ps -q 2>/dev/null); [ -n "$P" ] && $T docker inspect --format 'priv {{.Name}} {{.HostConfig.Privileged}}' $P 2>/dev/null | grep ' true$' | head -n 20; fi
echo @@end
'''

# fail2ban for SSH. Rack Live's own address is never banned, the real SSH port is taken from sshd. Debian 12+ keeps no auth.log: there it reads the journal.
FIX_FAIL2BAN = r'''export LC_ALL=C DEBIAN_FRONTEND=noninteractive PATH="$PATH:/sbin:/usr/sbin:/usr/local/sbin"
have(){ command -v "$1" >/dev/null 2>&1; }
ME="${SSH_CLIENT%% *}"; [ -n "$RL_ME" ] && ME="$RL_ME"
if have apt-get; then apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq fail2ban python3-systemd >/tmp/rl-f2b.log 2>&1
elif have dnf; then dnf install -y -q epel-release >/dev/null 2>&1; dnf install -y -q fail2ban >/tmp/rl-f2b.log 2>&1
else echo "@@fail на этой системе Rack Live не умеет ставить пакеты: поставьте fail2ban вручную"; exit 0; fi
have fail2ban-client || { tail -n 3 /tmp/rl-f2b.log | cut -c1-180; echo "@@fail пакет fail2ban не установился"; exit 0; }
P=$(sshd -T 2>/dev/null | sed -n 's/^port //p' | head -n 1); [ -n "$P" ] || P=22
B=auto; if have journalctl && [ -d /run/systemd/system ] && [ ! -s /var/log/auth.log ] && [ ! -s /var/log/secure ]; then B=systemd; fi
mkdir -p /etc/fail2ban/jail.d
cat > /etc/fail2ban/jail.d/rl-sshd.local <<EOF
# made by Rack Live («Сетевой доктор»)
[sshd]
enabled = true
port = $P
backend = $B
maxretry = 5
findtime = 10m
bantime = 1h
ignoreip = 127.0.0.1/8 ::1 $ME
EOF
if [ -d /run/systemd/system ]; then systemctl enable fail2ban >/dev/null 2>&1; systemctl restart fail2ban >/dev/null 2>&1; else service fail2ban restart >/dev/null 2>&1; fi
i=0; while [ $i -lt 15 ]; do fail2ban-client ping 2>/dev/null | grep -qi pong && break; sleep 1; i=$((i+1)); done
if fail2ban-client status sshd >/dev/null 2>&1; then echo "@@me $ME"; echo @@ok; else fail2ban-client -t 2>&1 | tail -n 2 | cut -c1-180; echo "@@fail fail2ban установился, но защита SSH не запустилась"; fi
rm -f /tmp/rl-f2b.log
'''

DEMO_OUT = '''@@id
0
@@os
id debian
like
name Debian GNU/Linux 12 (bookworm)
kernel Linux 6.1.0-demo
@@listen
tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=512,fd=3))
tcp LISTEN 0 511 0.0.0.0:443 0.0.0.0:* users:(("nginx",pid=700,fd=6))
tcp LISTEN 0 511 0.0.0.0:6379 0.0.0.0:* users:(("redis-server",pid=801,fd=6))
tcp LISTEN 0 80 127.0.0.1:3306 0.0.0.0:* users:(("mariadbd",pid=900,fd=20))
udp UNCONN 0 0 0.0.0.0:51820 0.0.0.0:*
@@sshd
port 22
permitrootlogin yes
passwordauthentication yes
permitemptypasswords no
pubkeyauthentication yes
maxauthtries 6
@@guard
@@fw
ufw inactive
ipt_policy ACCEPT
ipt_block 0
@@updates
pending 14
security 5
lists_fresh 8
auto no
reboot yes
@@accounts
uid0 root
shadow_read yes
shadow_mode 640
@@auth
fails 1342
@@docker
@@end
'''


def hostname(d):
    h = re.sub(r'^\w+://', '', str(d.get('host') or '').strip()).split('/')[0]
    return h.rsplit(':', 1)[0] if h.count(':') == 1 else h


def is_public(host):
    """A public IP or a domain = reachable from outside; a private address = the local network."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return not host.endswith(('.local', '.lan', '.home'))


def sections(out):
    res, cur = {}, None
    for l in (out or '').splitlines():
        if l.startswith('@@'):
            cur = l[2:].strip()
            res.setdefault(cur, [])
        elif cur is not None and l.strip():
            res[cur].append(l.strip())
    return res


def kv(lines):
    res = {}
    for l in lines:
        k, _, v = l.partition(' ')
        res[k.lower()] = v.strip()
    return res


def _exposure(addr):
    a = addr.strip('[]').split('%')[0]
    if a in ('*', '', '0.0.0.0', '::'):
        return 'all'
    try:
        ip = ipaddress.ip_address(a)
    except ValueError:
        return 'all'
    if ip.is_loopback:
        return 'local'
    return 'lan' if ip.is_private or ip.is_link_local else 'all'


def parse_listen(lines):
    """`ss -H -tulnp` or `netstat -tulnp` → [{proto, port, exposure, addr, proc}], one row per port with the widest exposure."""
    order, rows = {'all': 0, 'lan': 1, 'local': 2}, {}
    for l in lines:
        p = l.split()
        if p and p[0] == 'proc' and len(p) == 3:          # /proc/net/*: «ADDR:PORT» in hex, the address in the kernel's byte order
            hx, _, ph = p[2].partition(':')
            try:
                port = int(ph, 16)
                ad = bytes.fromhex(hx)
                ip = '.'.join(str(b) for b in ad[::-1]) if len(ad) == 4 else str(ipaddress.ip_address(b''.join(ad[i:i + 4][::-1] for i in range(0, 16, 4))))
            except (ValueError, IndexError):
                continue
            exp = _exposure(ip)
            key = (p[1], port)
            if key not in rows or order[exp] < order[rows[key]['exposure']]:
                rows[key] = {'proto': p[1], 'port': port, 'exposure': exp, 'addr': ip, 'proc': ''}
            continue
        if len(p) < 4 or not p[0].startswith(('tcp', 'udp')):
            continue
        is_ss = not p[1].isdigit()
        local = p[4] if is_ss and len(p) > 4 else p[3]
        addr, _, port = local.rpartition(':')
        if not port.isdigit():
            continue
        proc = ''
        m = re.search(r'users:\(\("([^"]+)"', l) or re.search(r'\s\d+/(\S+)\s*$', l)
        if m:
            proc = m.group(1)
        proto, exp = p[0][:3], _exposure(addr)
        key = (proto, int(port))
        if key not in rows or order[exp] < order[rows[key]['exposure']]:
            rows[key] = {'proto': proto, 'port': int(port), 'exposure': exp, 'addr': addr, 'proc': proc or (rows.get(key) or {}).get('proc', '')}
    return sorted(rows.values(), key=lambda r: (r['proto'], r['port']))


def knock(host, ports, timeout=1.5):
    def one(p):
        try:
            with socket.create_connection((host, p), timeout):
                return p
        except OSError:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        return sorted(p for p in ex.map(one, sorted(set(ports))) if p)


def _fold_udp(ports):
    """A proxy (Xray and the like) holds hundreds of short-lived high UDP ports: one row per program instead of a page of numbers."""
    groups, out = {}, []
    for r in ports:
        if r['proto'] == 'udp' and r['port'] >= 32768:
            groups.setdefault((r['proc'], r['exposure']), []).append(r)
        else:
            out.append(r)
    for rows in groups.values():
        out.extend(rows if len(rows) < 4 else [dict(rows[0], port=f"{rows[0]['port']}–{rows[-1]['port']}", count=len(rows))])
    return out


def _int(v, d=0):
    try:
        return int(str(v).split()[0])
    except (ValueError, IndexError, AttributeError):
        return d


def analyze(d, s, opened=None, exposed=None):
    """d = the device, s = parsed sections (or {}), opened = TCP ports that answered Rack Live (None = not knocked).
    → {checks, findings, ports, facts}. A check's state: ok / warn / bad / unknown (could not look) / na (does not apply)."""
    did = d.get('id')
    exposed = is_public(hostname(d)) if exposed is None else exposed
    router = d.get('driver') in ROUTER_DRIVERS or d.get('kind') in NO_KNOCK_KINDS
    synology = d.get('driver') == 'synology'
    has_inside = '@end' in s or 'end' in s
    root = (s.get('id') or ['?'])[0] == '0'
    found, checks = [], []

    def add(key, level, title, text, how='', cmd='', fix=None):
        found.append({'id': f'doc:{did}:{key}', 'level': level, 'title': title, 'text': text, 'how': how, 'cmd': cmd, 'fix': fix, 'deviceId': did, 'doctor': True})

    def check(cid, label, state, note=''):
        checks.append({'id': cid, 'label': label, 'state': state, 'note': note})

    osi, fw, upd, acc, guard = kv(s.get('os') or []), kv(s.get('fw') or []), kv(s.get('updates') or []), s.get('accounts') or [], s.get('guard') or []
    sshd, auth = kv(s.get('sshd') or []), kv(s.get('auth') or [])
    fails = _int(auth.get('fails'), None) if 'fails' in auth else None
    listen = parse_listen(s.get('listen') or [])

    # ── ports ──
    ports = [dict(r, opened=(opened is not None and r['proto'] == 'tcp' and r['port'] in opened)) for r in listen]
    for p in (opened or []):
        if not any(r['proto'] == 'tcp' and r['port'] == p for r in ports):
            ports.append({'proto': 'tcp', 'port': p, 'exposure': 'all', 'addr': '', 'proc': '', 'opened': True})
    ports.sort(key=lambda r: (r['proto'], r['port']))
    ports = _fold_udp(ports)
    ssh_port = _int(sshd.get('port'), 22)
    tcp_all = [r for r in ports if r['proto'] == 'tcp' and r['exposure'] == 'all']
    other_public = []
    ufw_on = fw.get('ufw') == 'active'
    for r in tcp_all:
        p = r['port']
        visible = r.get('opened') if opened is not None else None      # True = answered, False = listens but does not answer, None = not knocked
        if p == ssh_port or (visible is False):
            continue
        risk = RISKY.get(p)
        who = f" ({r['proc']})" if r['proc'] else ''
        if exposed and visible:
            if risk and p not in (80, 22):
                lvl, what, why = risk
                add(f'port:{p}', lvl, f'Порт {p} виден из интернета · {what}{who}', f'{what}: {why}. Rack Live достучался до этого порта.',
                    'Если сервис нужен только вам, закройте порт файрволом или привяжите сервис к 127.0.0.1, а доступ делайте через VPN.', f'ufw deny {p}/tcp' if ufw_on else '')
            elif p != 80:
                other_public.append(f"{p}{who}")
        elif exposed and visible is None and risk and p not in (80, 22):
            add(f'port:{p}', 'warn', f'Порт {p} слушает на всех адресах · {risk[1]}{who}', f'{risk[1]}: {risk[2]}. Снаружи порт не проверялся.', 'Проверьте, закрыт ли он файрволом.')
        elif not exposed and risk and risk[0] == 'bad':
            add(f'port:{p}', 'warn' if p in (21, 23) and not router else 'info', f'Порт {p} открыт в локальной сети · {risk[1]}{who}', f'{risk[1]}: {risk[2]}. Из вашей сети он доступен, снаружи только через проброс на роутере.',
                'Если сервис не нужен другим устройствам, отключите его или привяжите к 127.0.0.1.')
    if other_public:
        add('public', 'info', f'Из интернета отвечает ещё {len(other_public)} ' + ('порт' if len(other_public) == 1 else 'порта' if len(other_public) < 5 else 'портов'),
            'Это могут быть нужные вам сервисы (сайт, панель, VPN): ' + ', '.join(other_public[:15]) + '. Каждый открытый сервис надо обновлять и защищать паролем.', 'Всё, что вам не нужно, лучше закрыть.')
    if not s and opened is None:
        check('ports', 'Открытые порты', 'unknown', 'нет доступа внутрь, а стучаться на это устройство нельзя')
    elif not has_inside:
        bad_port = any(f['id'].startswith(f'doc:{did}:port:') and f['level'] != 'info' for f in found)
        where = 'из интернета' if exposed else 'в локальной сети'
        check('ports', 'Открытые порты', 'bad' if bad_port else 'ok', f"{where} отвечает: {', '.join(map(str, opened))}" if opened else 'из проверенных портов ни один не отвечает')
    elif not listen:
        check('ports', 'Открытые порты', 'unknown', 'список портов на устройстве прочитать не удалось' + (f", отвечают Rack Live: {len(opened)}" if opened is not None else ''))
    else:
        bad_port = any(f['id'].startswith(f'doc:{did}:port:') and f['level'] != 'info' for f in found)
        n_all = len(tcp_all)
        check('ports', 'Открытые порты', 'bad' if bad_port else 'ok', f'слушают на всех адресах: {n_all}' + (f", отвечают Rack Live: {len(opened)}" if opened is not None else ''))

    # ── SSH ──
    login = bool(sshd.get('permitrootlogin') or sshd.get('passwordauthentication'))
    if not has_inside:
        check('ssh', 'Вход по SSH', 'unknown', 'нет доступа внутрь')
    elif router:
        check('ssh', 'Вход по SSH', 'na', 'на роутере смотрите «Удалённый доступ» в замечаниях')
    elif not login:
        check('ssh', 'Вход по SSH', 'ok' if 'dropbear' not in sshd and not any(r['port'] == ssh_port and r['proto'] == 'tcp' for r in listen) else 'unknown',
              'SSH-сервер не найден' if not listen else 'настройки sshd прочитать не удалось' + ('' if root else ' (нужны права root)'))
    else:
        pw_on = sshd.get('passwordauthentication') == 'yes'
        root_pw = sshd.get('permitrootlogin') == 'yes' and pw_on
        lvl = 'warn' if exposed else 'info'
        if sshd.get('permitemptypasswords') == 'yes':
            add('ssh:empty', 'bad', 'SSH разрешает вход с пустым паролем', 'Любая учётная запись без пароля доступна всем, кто дотянется до порта.', 'В /etc/ssh/sshd_config поставьте PermitEmptyPasswords no и перезапустите sshd.')
        if pw_on:
            uses_pw = not d.get('privateKey')
            add('ssh:password', lvl, 'SSH принимает вход по паролю' + (', в том числе для root' if root_pw else ''),
                'Пароли можно подбирать' + (' из интернета постоянно' if exposed else '') + '. Вход по ключу подобрать невозможно.',
                ('Сначала добавьте SSH-ключ в настройки этого устройства в Rack Live: сейчас он сам входит сюда по паролю и без ключа потеряет доступ. ' if uses_pw else '') +
                'Проверьте вход по ключу в отдельном окне и только потом выключайте пароль. Старое окно не закрывайте, пока не убедитесь.',
                "printf 'PasswordAuthentication no\\n' > /etc/ssh/sshd_config.d/00-rl.conf\nsshd -t && systemctl reload ssh sshd 2>/dev/null")
        check('ssh', 'Вход по SSH', 'bad' if sshd.get('permitemptypasswords') == 'yes' else ('warn' if pw_on and exposed else 'ok'),
              ('по паролю' if pw_on else 'только по ключу') + (f", порт {ssh_port}" if ssh_port != 22 else ''))

    # ── brute force protection ──
    f2b = {'installed': 'installed' in guard, 'running': 'running' in guard, 'jails': {}, 'other': [l[6:] for l in guard if l.startswith('other ')]}
    for l in guard:
        if l.startswith('jail '):
            x = l.split()
            f2b['jails'][x[1]] = {'banned': _int(x[2] if len(x) > 2 else 0), 'total': _int(x[3] if len(x) > 3 else 0)}
    can_fix = d.get('driver') in ('ssh', 'demo_server') and root and (osi.get('id') in ('debian', 'ubuntu', 'rocky', 'almalinux', 'centos', 'rhel', 'fedora') or 'debian' in osi.get('like', '') or 'rhel' in osi.get('like', ''))
    fix = {'kind': 'doctor', 'id': 'fail2ban', 'label': 'Установить fail2ban', 'confirm': 'Установить fail2ban и включить защиту SSH: 5 неудачных входов за 10 минут — бан адреса на час. Адрес Rack Live в бан не попадёт. Продолжить?'} if can_fix else None
    jail = next((j for j in f2b['jails'] if 'ssh' in j), None)
    if not has_inside:
        check('guard', 'fail2ban / защита от перебора', 'unknown', 'нет доступа внутрь')
    elif router:
        check('guard', 'fail2ban / защита от перебора', 'na', 'на роутерах обычно не ставят, важнее закрыть управление из интернета')
    elif synology:
        check('guard', 'fail2ban / защита от перебора', 'unknown', 'у DSM своя «Автоблокировка»: проверьте её вручную')
        add('guard:syno', 'info', 'Проверьте автоблокировку DSM', 'На Synology вместо fail2ban работает своя автоблокировка. Rack Live пока не читает её настройку, поэтому не утверждает, что она включена.',
            'DSM → Панель управления → Безопасность → Учётная запись → «Включить автоблокировку».')
    elif f2b['other']:
        check('guard', 'fail2ban / защита от перебора', 'ok', 'работает ' + ', '.join(f2b['other']))
    elif f2b['running'] and jail:
        j = f2b['jails'][jail]
        check('guard', 'fail2ban / защита от перебора', 'ok', f"работает, сейчас в бане {j['banned']}, всего банов {j['total']}")
    elif f2b['running']:
        check('guard', 'fail2ban / защита от перебора', 'warn', 'работает, но SSH не защищён')
        add('guard:jail', 'warn', 'fail2ban работает, но не защищает SSH', 'Нет активного правила (jail) для sshd, поэтому подбор пароля не блокируется.', 'Кнопка включит правило для SSH.', fix=fix)
    elif f2b['installed']:
        state = 'bad' if exposed else 'warn'
        check('guard', 'fail2ban / защита от перебора', state, 'установлен, но не запущен' + ('' if root else ' или не хватает прав, чтобы это проверить'))
        if root:
            add('guard:stopped', state if exposed else 'info', 'fail2ban установлен, но не работает', 'Подбор пароля сейчас никто не блокирует.', 'Кнопка настроит правило для SSH и запустит службу.', fix=fix)
    elif not (login or 'dropbear' in sshd):
        check('guard', 'fail2ban / защита от перебора', 'na', 'SSH-сервер не найден')
    else:
        pw_on = sshd.get('passwordauthentication') == 'yes'
        lvl = ('bad' if pw_on and (fails or 0) >= 100 else 'warn') if exposed else 'info'
        check('guard', 'fail2ban / защита от перебора', lvl if lvl != 'info' else 'warn', 'не установлен')
        add('guard:none', lvl, 'Нет fail2ban: подбор пароля к SSH никто не блокирует',
            (f'За последние сутки неудачных входов: {fails}. ' if fails else '') + ('Сервер виден из интернета, боты перебирают пароли постоянно.' if exposed else 'Устройство в локальной сети, риск ниже, но вирус на любом компьютере может подбирать пароль.'),
            'fail2ban банит адрес после нескольких неудачных входов.' + ('' if fix else ' Поставьте его вручную: здесь Rack Live не может сделать это сам.'), fix=fix)

    # ── firewall ──
    active = ufw_on or fw.get('firewalld') == 'running' or _int(fw.get('nft_drop')) > 0 or fw.get('ipt_policy') in ('DROP', 'REJECT') or _int(fw.get('ipt_block')) > 0
    docker_lines = [l for l in s.get('docker') or [] if '|' in l]
    published = sorted({int(m) for l in docker_lines for m in re.findall(r'(?:0\.0\.0\.0|\[::\]|:::):(\d+)->', l)})
    if not has_inside:
        check('fw', 'Файрвол', 'unknown', 'нет доступа внутрь')
    elif router:
        check('fw', 'Файрвол', 'na', 'встроен в роутер, смотрите пробросы в замечаниях')
    elif synology:
        check('fw', 'Файрвол', 'ok' if active else 'unknown', 'есть правила блокировки' if active else 'правил не видно, настройка в DSM → Безопасность → Брандмауэр')
    elif not fw or (not root and not active and 'ufw' not in fw):
        check('fw', 'Файрвол', 'unknown', 'прочитать не удалось' + ('' if root else ' (нужны права root)'))
    elif active:
        check('fw', 'Файрвол', 'ok', 'ufw' if ufw_on else 'firewalld' if fw.get('firewalld') == 'running' else 'есть правила блокировки')
    else:
        check('fw', 'Файрвол', 'warn' if exposed else 'ok', 'не настроен' + ('' if exposed else ', для локальной сети допустимо'))
        if exposed:
            keep = sorted({ssh_port} | {r['port'] for r in tcp_all if r.get('opened') and r['port'] != ssh_port and (RISKY.get(r['port']) or ('info',))[0] != 'bad'})
            add('fw:none', 'warn', 'Файрвол не настроен', 'Любой сервис, который начнёт слушать порт, сразу виден всему интернету.',
                'Сначала разрешите SSH и нужные порты, иначе потеряете доступ. Список ниже составлен по портам, которые сейчас отвечают: проверьте его и добавьте порты UDP (например, для VPN).',
                '\n'.join(f'ufw allow {p}/tcp' for p in keep) + '\nufw enable')
    if published and ufw_on:
        add('docker:ufw', 'warn', 'Docker обходит ufw', f"Контейнеры опубликовали порты {', '.join(map(str, published[:15]))} напрямую: правила ufw на них не действуют.",
            'Публикуйте порты как 127.0.0.1:порт:порт и ставьте перед ними обратный прокси либо добавляйте правила в цепочку DOCKER-USER.')
    priv = [l.split()[1].lstrip('/') for l in s.get('docker') or [] if l.startswith('priv ')]
    if priv:
        add('docker:priv', 'info', f"Привилегированные контейнеры: {', '.join(priv[:8])}", 'Такой контейнер при взломе получает полный доступ к системе.', 'Если контейнеру это не нужно, уберите --privileged.')

    # ── updates ──
    if not has_inside:
        check('updates', 'Обновления', 'unknown', 'нет доступа внутрь')
    elif 'pending' not in upd:
        check('updates', 'Обновления', 'na' if router or synology else 'unknown', 'обновляется через свою панель' if router or synology else 'менеджер пакетов не распознан')
    else:
        pend, secu = _int(upd.get('pending')), _int(upd.get('security'))
        stale = 'lists_fresh' in upd and _int(upd.get('lists_fresh')) == 0
        note = ' Список пакетов не обновлялся больше недели, настоящая цифра может быть выше.' if stale else ''
        cmd = 'apt-get update && apt-get upgrade -y' if 'lists_fresh' in upd else 'dnf upgrade -y' if 'auto' in upd else 'apk upgrade'
        if secu:
            add('upd:security', 'warn', f'Не установлены обновления безопасности: {secu}', 'Через них закрывают известные уязвимости.' + note, 'Установите обновления. Сервисы могут ненадолго перезапуститься.', cmd)
        elif pend:
            add('upd:pending', 'info', f'Доступны обновления: {pend}', 'Среди них нет отмеченных как обновления безопасности.' + note, '', cmd)
        check('updates', 'Обновления', 'warn' if secu else 'ok', f'безопасности: {secu}, всего: {pend}' + (', данные могут быть старыми' if stale else ''))
        if upd.get('auto') == 'no':
            add('upd:auto', 'info', 'Автообновления безопасности выключены', 'Сервер ждёт, пока кто-нибудь обновит его вручную.', '',
                'apt-get install -y unattended-upgrades\ndpkg-reconfigure -f noninteractive unattended-upgrades' if 'lists_fresh' in upd else 'dnf install -y dnf-automatic\nsystemctl enable --now dnf-automatic.timer')
        if upd.get('reboot') == 'yes':
            add('upd:reboot', 'info', 'Сервер просит перезагрузку', 'Часть обновлений, например ядро, заработает только после неё.', 'Перезагрузите, когда это будет удобно.')

    # ── accounts ──
    if not has_inside:
        check('accounts', 'Учётные записи', 'unknown', 'нет доступа внутрь')
    else:
        extra = [l[5:] for l in acc if l.startswith('uid0 ') and l[5:] != 'root']
        empty = [l[8:] for l in acc if l.startswith('emptypw ')]
        nop = [l[9:] for l in acc if l.startswith('nopasswd ')]
        mode = kv(acc).get('shadow_mode')
        if extra:
            add('acc:uid0', 'bad', f"Кроме root права администратора у: {', '.join(extra)}", 'Вторая учётная запись с UID 0 бывает следом взлома. Если вы её не создавали, разберитесь срочно.', 'Проверьте, кто и когда её создал.')
        if empty and not router:
            add('acc:empty', 'bad', f"Учётные записи без пароля: {', '.join(empty[:8])}", 'В них можно войти без пароля, если вход разрешён.', 'Задайте пароль или заблокируйте запись.', f'passwd -l {empty[0]}')
        if mode and _int(mode) % 10 != 0:
            add('acc:shadow', 'bad', f'Файл паролей /etc/shadow доступен всем (права {mode})', 'Любой пользователь может прочитать хэши паролей и подобрать их.', '', 'chmod 640 /etc/shadow')
        if nop and not router:
            add('acc:nopasswd', 'info', 'sudo без пароля: ' + ', '.join(nop[:8]), 'Если эта учётная запись будет взломана, злоумышленник сразу получит root.', 'Оставляйте так только для служебных записей.')
        can = 'shadow_read' in kv(acc)
        if router and not can:
            check('accounts', 'Учётные записи', 'na', 'у роутера свои пользователи, в Entware их не видно')
        else:
            check('accounts', 'Учётные записи', 'bad' if extra or (empty and not router) or (mode and _int(mode) % 10 != 0) else ('ok' if can else 'unknown'), '' if can else 'без root видна только часть')

    if has_inside and not root:
        add('noroot', 'info', 'Проверка прошла без прав root', 'Часть данных прочитать не удалось: такие пункты отмечены как «не проверено».', 'Для полной проверки нужен вход под root или sudo с паролем.')
    facts = {'os': osi.get('name') or (('DSM ' + osi['syno']) if osi.get('syno') else 'OpenWrt' if osi.get('openwrt') else 'Entware' if osi.get('entware') else ''),
             'kernel': osi.get('kernel') or '', 'root': root if has_inside else None, 'fails24h': fails, 'exposed': exposed}
    return {'checks': checks, 'findings': found, 'ports': ports, 'facts': facts}


def rank(findings, ignored=()):
    ign, order = set(ignored or ()), {'bad': 0, 'warn': 1, 'info': 2}
    active = sorted([f for f in findings if f['id'] not in ign], key=lambda f: (order[f['level']], f['title']))
    return {'findings': active, 'ignored': [f for f in findings if f['id'] in ign], 'score': max(0, 100 - sum(COST[f['level']] for f in active)),
            'counts': {k: sum(1 for f in active if f['level'] == k) for k in order}}


# «Полная проверка»: every TCP port, run on the user's own VPS. Nothing is written there: the program comes on stdin.
FULL_SCAN = r"""command -v python3 >/dev/null 2>&1 || { echo "@@fail на сервере нет python3"; exit 0; }
ulimit -n 4096 2>/dev/null
python3 - <<'RLPY'
import asyncio
IP = __IP__
async def one(p, sem, out):
    async with sem:
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection(IP, p), 2.0)
            out.append(p)
            w.close()
        except Exception:
            pass
async def main():
    sem, out = asyncio.Semaphore(400), []
    await asyncio.gather(*(one(p, sem, out) for p in range(1, 65536)))
    print("@@open " + ",".join(map(str, sorted(out))))
    print("@@end")
asyncio.run(main())
RLPY
"""


def parse_full(out):
    """The output of FULL_SCAN → the open ports. An interrupted scan is an error, not «nothing is open»."""
    if '@@fail ' in out:
        raise DriverError(out.split('@@fail ', 1)[1].splitlines()[0].strip())
    if '@@end' not in out:
        raise DriverError('полная проверка не дошла до конца')
    m = re.search(r'^@@open (.*)$', out, re.M)
    return sorted({int(x) for x in (m.group(1).split(',') if m else []) if x.strip().isdigit()})


def knock_all(host, conc=200, timeout=1.5):
    """Every TCP port from this machine (no VPS to do it). Fewer at a time: Rack Live also runs on small routers with few open files allowed."""
    import asyncio

    async def one(p, sem, out):
        async with sem:
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection(host, p), timeout)
                out.append(p)
                w.close()
            except Exception:
                pass

    async def main():
        sem, out = asyncio.Semaphore(conc), []
        await asyncio.gather(*(one(p, sem, out) for p in range(1, 65536)))
        return sorted(out)
    return asyncio.run(main())


def _ports_of(spec, limit=64):
    """«2070» or «8000-8010» → the ports to knock on."""
    m = re.match(r'^(\d+)(?:-(\d+))?$', str(spec))
    if not m:
        return []
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return list(range(a, min(b, a + limit - 1) + 1))


def outside_rows(st, ext, idx=None, entware=222):
    """What a router opens to the internet: its forwards and whatever answered from outside, one row per port. answers: True / False / None (not checked, e.g. UDP)."""
    sec, idx = (st or {}).get('security') or {}, idx or {}
    opened, checked = set((ext or {}).get('open') or []), set((ext or {}).get('checked') or [])
    rows, seen = [], set()
    for f in sec.get('forwards') or []:
        ps = _ports_of(f.get('port'))
        tcp = f.get('proto') != 'udp' and any(p in checked for p in ps)
        target = (idx.get(str(f.get('target') or '').lower()) or {}).get('name') or f.get('target')
        rows.append({'port': str(f.get('port')), 'proto': str(f.get('proto') or 'tcp').replace('tcpudp', 'tcp+udp'), 'name': f.get('name') or '', 'target': target, 'forward': True,
                     'answers': any(p in opened for p in ps) if tcp else None})
        seen.update(ps)
    own = {}
    for what, r in (('веб-интерфейс роутера', (sec.get('remote') or {}).get('http') or {}), ('SSH роутера', (sec.get('remote') or {}).get('ssh') or {}), ('Telnet роутера', (sec.get('remote') or {}).get('telnet') or {})):
        for k in ('port', 'sslPort'):
            if r.get(k):
                own[int(r[k])] = what
    for p in sorted(opened - seen):
        rows.append({'port': str(p), 'proto': 'tcp', 'name': own.get(p) or ('SSH в Entware' if p == entware else '') or (RISKY.get(p) or ('', '', ''))[1], 'target': '', 'forward': False, 'answers': True})
    return sorted(rows, key=lambda r: _int(str(r['port']).split('-')[0]))


class Doctor:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.reports = self.store._load('doctor.json', {})
        self.jobs, self.lock = {}, threading.Lock()

    def device(self, did):
        return next((d for d in self.store.cfg['devices'] if d['id'] == did), None)

    def can_knock(self, d):
        if d.get('driver') in NO_KNOCK_DRIVERS or d.get('kind') in NO_KNOCK_KINDS or not hostname(d):
            return False
        return hostname(d) not in netscan.infra_ips(self.app)

    def access(self, d):
        """How deep the doctor can look at this device: inside / ports / audit (with why, for the page)."""
        drv = d.get('driver')
        if drv == 'keenetic':
            if d.get('entwarePassword'):
                return 'inside', 'через SSH в Entware'
            return 'audit', 'только настройки роутера: для проверки изнутри укажите доступ к Entware (вкладка «Плагины»)'
        if drv in INSIDE_DRIVERS:
            return 'inside', 'по SSH'
        if self.can_knock(d):
            return 'ports', 'только порты снаружи: входа внутрь у Rack Live нет'
        return 'audit', 'только то, что Rack Live уже знает об устройстве'

    def inside(self, d, timeout=150):
        from .drivers import REGISTRY
        drv, body = REGISTRY[d['driver']], SCRIPT
        if d['driver'].startswith('demo_'):
            return DEMO_OUT
        if d['driver'] == 'keenetic':
            return drv._ssh(d, body, timeout)
        if d['driver'] == 'openwrt':
            return drv._ssh(d, body, timeout)
        if d['driver'] == 'synology':
            return drv.command(d, body)                 # it already runs through sudo
        return drv._run(d, self._as_root(body, d.get('password')), timeout=timeout)

    @staticmethod
    def _as_root(body, pw):
        """A non-root login: the same script through sudo, when the login's password fits. The password goes to sudo on stdin, never to the command line."""
        tag = 'RLEOF' + secrets.token_hex(6)
        q = shlex.quote(pw or '')
        return f'''F=$(mktemp /tmp/rl-doc.XXXXXX) || exit 0
cat > "$F" <<'{tag}'
{body}
{tag}
if [ "$(id -u)" != 0 ] && printf '%s\\n' {q} | sudo -S -p '' true 2>/dev/null; then printf '%s\\n' {q} | sudo -S -p '' sh "$F"; else sh "$F" </dev/null; fi
rm -f "$F"
'''

    def outside_address(self, d):
        """A router's address as the internet sees it: its own WAN, else a public host, else (the home router) the home address. None = it has no address of its own outside."""
        if d.get('driver') not in ROUTER_DRIVERS:
            return None
        for p in (self.app.states.get(d['id']) or {}).get('ports') or []:
            if p.get('kind') == 'wan' and p.get('ip') and not p['ip'].startswith(('10.', '192.168.', '172.', '100.')):
                return p['ip']
        h = hostname(d)
        if is_public(h):
            return h
        return self.app.extscan.public_ip() if d.get('driver') in ('keenetic', 'demo_router') else None

    def vps_for(self, d):
        """A VPS to knock from, but never the device itself: from inside it would see its own closed ports open."""
        vps = self.app.extscan.scanner()
        if vps and vps.get('id') != d.get('id'):
            return vps
        return next((x for x in self.store.cfg['devices'] if x.get('driver') in ('ssh', 'demo_server') and x.get('enabled', True) and x.get('location') == 'remote' and x.get('id') != d.get('id')), None)

    def fullable(self, d):
        """Can every port be checked? No network here: the list of devices must stay fast."""
        if d.get('driver') in ROUTER_DRIVERS:
            return bool(self.vps_for(d)) and (d.get('driver') in ('keenetic', 'demo_router') or is_public(hostname(d)))
        return self.can_knock(d)

    def full_open(self, d, addr, progress, vps=None):
        """All 65535 TCP ports of `addr` → (open ports, who checked). From a VPS when the address is public; otherwise from Rack Live itself, only where it may knock."""
        from .drivers import REGISTRY
        if d['driver'].startswith('demo_'):
            time.sleep(.5)
            return [22, 443, 6379, 8443], 'демо'
        if not re.match(r'^[\w.\-]+$', addr or ''):
            raise DriverError('непонятный адрес устройства')
        vps = vps or (self.vps_for(d) if is_public(addr) else None)
        if vps:
            progress(f"Проверяю все 65535 портов с «{vps.get('name')}», обычно около 5 минут…")
            return parse_full(REGISTRY[vps['driver']]._run(vps, FULL_SCAN.replace('__IP__', repr(addr)), 480)), vps.get('name')
        if not self.can_knock(d):
            raise DriverError('нет внешнего сервера для полной проверки')
        progress('Проверяю все 65535 портов из Rack Live, обычно до 8 минут…')
        return knock_all(addr), 'Rack Live'

    def check_outside(self, d, s, progress, full=False):
        """A fresh knock from the user's own VPS on what the router could open: the common ports, its forwards and everything it listens on.
        A burst from that VPS can only make the router shut out the VPS, not Rack Live (see netscan.infra_ips)."""
        from .drivers import REGISTRY
        addr = self.outside_address(d)
        if not addr:
            return None
        vps = self.app.extscan.scanner()
        rec = {'t': int(time.time()), 'via': vps and vps.get('name'), 'open': [], 'checked': []}
        if not vps:
            rec['error'] = 'нет внешнего сервера: добавьте любой VPS как «Сервер / VPS по SSH»'
            return rec
        if not re.match(r'^[\w.\-]+$', addr):
            rec['error'] = 'непонятный внешний адрес роутера'
            return rec
        sec = (self.app.states.get(d['id']) or {}).get('security') or {}
        ports = set(extscan.COMMON) | set(KNOCK_EXTRA) | {r['port'] for r in parse_listen(s.get('listen') or []) if r['proto'] == 'tcp' and r['exposure'] != 'local'}
        for f in sec.get('forwards') or []:
            ports.update(_ports_of(f.get('port')))
        for r in (sec.get('remote') or {}).values():
            ports.update(int(r[k]) for k in ('port', 'sslPort') if r.get(k))
        ports.add(_int(d.get('entwarePort'), 222))            # Entware's SSH: it listens whether or not the list of ports could be read
        rec['checked'] = sorted(ports)
        progress(f"Проверяю снаружи с «{vps.get('name')}»…")
        try:
            rec['open'] = REGISTRY[vps['driver']].port_scan(vps, addr, rec['checked'])
        except Exception as e:
            rec['error'] = f'проверка снаружи не удалась: {e}'
        if full and not rec.get('error'):
            try:                                              # both results together: under such a load a port can miss its 2 seconds
                got, _ = self.full_open(d, addr, progress, vps)
                rec['open'], rec['checked'], rec['full'] = sorted(set(rec['open']) | set(got)), list(range(1, 65536)), True
            except Exception as e:
                rec['fullError'] = str(e)
        return rec

    def run_check(self, d, progress=lambda s: None, full=False):
        rep = {'device': d['id'], 't': int(time.time()), 'errors': []}
        kind, why = self.access(d)
        rep['access'], rep['accessNote'] = kind, why
        s = {}
        if kind == 'inside':
            progress('Захожу на устройство и читаю настройки…')
            try:
                s = sections(self.inside(d))
            except DriverError as e:
                rep['errors'].append(f'Не удалось зайти на устройство: {e}')
            if not ('end' in s):
                if s:
                    rep['errors'].append('Проверка на устройстве не дошла до конца: показано только то, что успели прочитать.')
                rep['access'], rep['accessNote'] = ('ports', 'внутрь зайти не удалось, проверены только порты снаружи') if self.can_knock(d) else ('audit', 'внутрь зайти не удалось')
        opened = None
        if self.can_knock(d):
            progress('Стучусь на порты…')
            lst = parse_listen(s.get('listen') or [])
            ports = set(extscan.COMMON) | set(KNOCK_EXTRA) | {r['port'] for r in lst if r['proto'] == 'tcp' and r['exposure'] != 'local'}
            rep['knocked'] = len(ports)
            opened = [22, 443, 6379] if d['driver'].startswith('demo_') else knock(hostname(d), ports)
            if full:
                try:
                    got, via = self.full_open(d, hostname(d), progress)
                    opened = sorted(set(opened) | set(got))
                    rep['knocked'], rep['fullVia'] = 65535, via
                except Exception as e:
                    rep['errors'].append(f'Полная проверка портов не удалась: {e}. Показан обычный список.')
        elif full and d.get('driver') not in ROUTER_DRIVERS:
            rep['errors'].append('Полная проверка для этого устройства недоступна: стучаться на него нельзя.')
        rep.update(analyze(d, s, opened, True if d['driver'] == 'demo_server' else None))      # the demo server plays a rented VPS
        progress('Собираю советы…')
        out = self.check_outside(d, s, progress, full)
        ext = out if out and not out.get('error') else None      # never the old daily result: a port closed since then would still be reported as open
        try:
            idx = self.app.peer_index()
        except Exception:
            idx = None
        aud = security.audit([d], self.app.states, idx, (), ext)
        rep['findings'] = rep['findings'] + [dict(f) for f in aud['findings']]
        if out is not None:
            rows = outside_rows(self.app.states.get(d['id']), ext, idx, _int(d.get('entwarePort'), 222))
            rep['outside'] = {'rows': rows, 't': out['t'], 'via': out.get('via'), 'checked': len(out['checked']), 'error': out.get('error'), 'full': bool(out.get('full')), 'fullError': out.get('fullError')}
            c = next(x for x in rep['checks'] if x['id'] == 'ports')
            live = [r['port'] for r in rows if r['answers']]
            if out.get('error') and not rows:
                c.update(state='unknown', note=out['error'])
            elif rows:
                c.update(state='bad' if any(f['level'] == 'bad' and ':' in f['id'] and f['id'].split(':')[0] in ('fwd', 'ext') for f in aud['findings']) else 'warn',
                         note=(f"снаружи отвечают: {', '.join(live)}" if live else 'пробросы есть, снаружи не отвечают') + (' (снаружи не проверено)' if out.get('error') else ''))
            else:
                c.update(state='ok', note=f"снаружи ничего не отвечает, проверено портов: {len(out['checked'])}")
        rep['nothing'] = rep['access'] == 'audit' and not aud['findings'] and not s
        return rep

    def start(self, did, fix=None, full=False):
        d = self.device(did)
        if not d:
            raise ValueError('устройство не найдено')
        if full and not self.fullable(d):
            raise ValueError('полная проверка для этого устройства недоступна')
        with self.lock:
            cur = next((j for j in self.jobs.values() if j['device'] == did and not j['done']), None)
            if cur:
                return cur
            job = {'id': secrets.token_hex(6), 'device': did, 'fix': fix, 'full': bool(full), 't': time.time(), 'stage': 'Запуск…', 'done': False}
            self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v['t'] < 3600}
            self.jobs[job['id']] = job

        def run():
            try:
                if fix:
                    job['message'] = self._fix(d, fix, lambda x: job.update(stage=x))
                rep = self.run_check(d, lambda x: job.update(stage=x), bool(full))
                self.reports[did] = rep
                self.store._dump('doctor.json', self.reports)
            except Exception as e:
                job['error'] = str(e)
            finally:
                job['done'] = True
        threading.Thread(target=run, daemon=True).start()
        return job

    def _fix(self, d, fix, progress):
        if fix != 'fail2ban':
            raise DriverError('неизвестное исправление')
        last = self.reports.get(d['id']) or {}
        if not any((f.get('fix') or {}).get('id') == fix for f in last.get('findings') or []):
            raise DriverError('сначала запустите проверку: последняя проверка не предлагала это исправление')
        progress('Ставлю fail2ban (обычно до 5 минут)…')
        if d['driver'].startswith('demo_'):
            time.sleep(.5)
            self.store.add_event(d['id'], d.get('name'), 'info', 'Сетевой доктор: fail2ban установлен (демо)')
            return 'fail2ban установлен (демо)'
        from .drivers import REGISTRY
        out = REGISTRY[d['driver']]._run(d, self._as_root(FIX_FAIL2BAN, d.get('password')), timeout=400)
        if '@@ok' not in out:
            why = next((l[7:] for l in out.splitlines() if l.startswith('@@fail ')), 'установка не завершилась')
            self.store.add_event(d['id'], d.get('name'), 'warning', f'Сетевой доктор: {why}')
            raise DriverError(why)
        self.store.add_event(d['id'], d.get('name'), 'info', 'Сетевой доктор: установлен fail2ban, защита SSH включена')
        return 'fail2ban работает, защита SSH включена'

    def view(self, did):
        rep = self.reports.get(did)
        if not rep:
            return None
        ign = (self.store.cfg.get('security') or {}).get('ignored') or ()
        return dict(rep, **rank(rep.get('findings') or [], ign))

    def public(self):
        out = []
        for d in self.store.cfg['devices']:
            if d.get('enabled') is False or d.get('driver') in ('site_node',):
                continue
            kind, why = self.access(d)
            v = self.view(d['id'])
            busy = next((j['id'] for j in self.jobs.values() if j['device'] == d['id'] and not j['done']), None)
            out.append({'id': d['id'], 'name': d.get('name') or d.get('host'), 'kind': d.get('kind'), 'driver': d.get('driver'), 'access': kind, 'accessNote': why, 'job': busy, 'fullable': self.fullable(d),
                        'last': v and {'t': v['t'], 'score': v['score'], 'counts': v['counts']}})
        return {'devices': out}
