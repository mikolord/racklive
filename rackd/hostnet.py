"""Network of the machine Rack Live itself runs on (Settings → «Сеть»).

Reading: what the panel sees locally (interfaces, addresses, gateway, DNS) plus — when this machine is also added as a device with SSH (Synology, OpenWrt, a Linux server) — the real
configuration of each interface: DHCP or a fixed address.
Changing (DHCP ⇄ fixed address) is offered only where it can be done safely: Synology (synonet), OpenWrt (uci), Linux with NetworkManager (nmcli). Everywhere else the form is closed
and the reason is shown. Every change has a safety net: before it a copy of the old settings is saved on the machine and a timer is started there that puts them back after 150 s,
unless you press «Подтвердить» (from the NEW address) — so a typo in the address does not leave the machine unreachable."""
import ipaddress, json, os, re, shlex, socket, time

ROLLBACK_SECONDS = 150
HOST_DRIVERS = ('synology', 'openwrt', 'ssh', 'keenetic')

# ───────── reading ─────────
READ_SYNO = r'''export PATH=$PATH:/usr/syno/bin:/usr/syno/sbin
synonet --show 2>/dev/null | grep -v "Failed to read"'''
READ_OWRT = r'''uci -q show network 2>/dev/null; echo "@@resolv"; cat /tmp/resolv.conf.d/resolv.conf.auto /etc/resolv.conf 2>/dev/null | grep nameserver | head -4'''
READ_LINUX = r'''echo "@@os"; ( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" ) || uname -sr
echo "@@mgr"
if command -v nmcli >/dev/null 2>&1 && nmcli -t general status >/dev/null 2>&1; then echo networkmanager
elif ls /etc/netplan/*.yaml >/dev/null 2>&1; then echo netplan
elif [ -f /etc/network/interfaces ]; then echo ifupdown
elif command -v networkctl >/dev/null 2>&1; then echo networkd
else echo unknown; fi
echo "@@nm"; nmcli -t -f NAME,DEVICE,TYPE con show --active 2>/dev/null | grep -v ":lo:" | while IFS= read -r l; do n=$(echo "$l" | cut -d: -f1); echo "== $l"; nmcli -t -f ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns con show "$n" 2>/dev/null; done
echo "@@addr"; ip -o -4 addr show 2>/dev/null
echo "@@route"; ip route 2>/dev/null | head -5
echo "@@resolv"; grep nameserver /etc/resolv.conf 2>/dev/null | head -4'''


def mask_to_prefix(m):
    m = str(m or '').strip()
    if m.isdigit():
        return int(m)
    try:
        return ipaddress.ip_network('0.0.0.0/' + m).prefixlen
    except ValueError:
        return None


def prefix_to_mask(p):
    return str(ipaddress.ip_network('0.0.0.0/%d' % int(p)).netmask)


def parse_synonet(text):
    out, cur = [], None
    for l in text.splitlines():
        l = l.strip()
        if l.startswith('Network interface:'):
            cur = {'name': l.split(':', 1)[1].strip(), 'mode': 'static', 'ip': '', 'mask': '', 'gateway': '', 'dns': '', 'mtu': None}
            out.append(cur)
        elif cur:
            if l in ('DHCP', 'Manual IP'):
                cur['mode'] = 'dhcp' if l == 'DHCP' else 'static'
            elif l.startswith('IP:'):
                cur['ip'] = l.split(':', 1)[1].strip()
            elif l.startswith('Mask:'):
                cur['mask'] = l.split(':', 1)[1].strip()
            elif l.startswith('Gateway:'):
                cur['gateway'] = l.split(':', 1)[1].strip()
            elif l.startswith('DNS:'):
                cur['dns'] = l.split(':', 1)[1].strip()
            elif l.startswith('MTU Setting:'):
                cur['mtu'] = int(re.sub(r'\D', '', l) or 0) or None
    return [i for i in out if i['ip'] or i['mode'] == 'dhcp']


def parse_uci(text):
    ifs, dns_auto = {}, []
    part = text.split('@@resolv')
    for l in part[0].splitlines():
        m = re.match(r"network\.(\w+)=interface$", l.strip())
        if m:
            ifs.setdefault(m.group(1), {})
            continue
        m = re.match(r"network\.(\w+)\.(\w+)=(.*)$", l.strip())
        if m and m.group(1) in ifs:
            ifs[m.group(1)][m.group(2)] = m.group(3).strip("'")
    for l in (part[1] if len(part) > 1 else '').splitlines():
        if 'nameserver' in l:
            dns_auto.append(l.split()[-1])
    out = []
    for n, v in ifs.items():
        if n in ('loopback', 'wan6') or v.get('proto') in ('none', 'dhcpv6', None) and not v.get('ipaddr'):
            continue
        ip = (v.get('ipaddr') or '').split('/')[0]
        mask = v.get('netmask') or (prefix_to_mask(v['ipaddr'].split('/')[1]) if '/' in (v.get('ipaddr') or '') else '')
        out.append({'name': n, 'mode': 'dhcp' if v.get('proto') == 'dhcp' else 'static', 'ip': ip, 'mask': mask, 'gateway': v.get('gateway', ''), 'dns': v.get('dns', '') or ' '.join(dns_auto[:2]), 'device': v.get('device') or v.get('ifname') or ''})
    return out


def parse_linux(text):
    sec, cur = {}, None
    for l in text.splitlines():
        if l.startswith('@@'):
            cur = l[2:].strip(); sec[cur] = []
        elif cur:
            sec[cur].append(l)
    mgr = (sec.get('mgr') or ['unknown'])[0].strip()
    nm, conn = [], None
    for l in sec.get('nm', []):
        if l.startswith('== '):
            p = l[3:].replace('\\:', '\x00').split(':')
            conn = {'name': p[0].replace('\x00', ':'), 'device': p[1] if len(p) > 1 else '', 'method': '', 'addresses': '', 'gateway': '', 'dns': ''}
            nm.append(conn)
        elif conn and ':' in l:
            k, v = l.split(':', 1)
            conn[k.split('.')[-1]] = v.strip()
    addrs = {}
    for l in sec.get('addr', []):
        m = re.match(r'\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)', l)
        if m and m.group(1) != 'lo':
            addrs.setdefault(m.group(1), []).append((m.group(2), int(m.group(3))))
    gw = next((l.split()[2] for l in sec.get('route', []) if l.startswith('default') and len(l.split()) > 2), '')
    dns = [l.split()[1] for l in sec.get('resolv', []) if len(l.split()) > 1]
    out = []
    for c in nm:
        a = addrs.get(c['device']) or []
        ip, pfx = (a[0] if a else ('', 24))
        out.append({'name': c['device'] or c['name'], 'conn': c['name'], 'mode': 'dhcp' if c['method'] == 'auto' else 'static', 'ip': ip, 'mask': prefix_to_mask(pfx) if ip else '', 'gateway': gw if c['device'] and a else '', 'dns': c['dns'] or ' '.join(dns[:2]),
                    'rawAddresses': c['addresses'], 'rawGateway': c['gateway'], 'rawDns': c['dns'], 'rawMethod': c['method']})
    if not out:
        for dev, a in addrs.items():
            out.append({'name': dev, 'conn': '', 'mode': 'unknown', 'ip': a[0][0], 'mask': prefix_to_mask(a[0][1]), 'gateway': gw, 'dns': ' '.join(dns[:2])})
    return {'manager': mgr, 'os': (sec.get('os') or [''])[0].strip(), 'interfaces': out}


# ───────── the plan of a change (commands to apply, and to put everything back) ─────────
def check_change(ch, ifaces):
    """→ (clean change dict, error). Validates what the user typed."""
    mode = ch.get('mode')
    cur = next((i for i in ifaces if i['name'] == ch.get('iface')), None)
    if not cur:
        return None, 'такого сетевого интерфейса нет'
    if mode == 'dhcp':
        return {'iface': cur['name'], 'mode': 'dhcp', 'cur': cur}, None
    if mode != 'static':
        return None, 'выберите DHCP или постоянный адрес'
    try:
        ip = ipaddress.ip_address(str(ch.get('ip') or '').strip())
    except ValueError:
        return None, 'адрес записан неверно (нужно вида 192.168.1.10)'
    pfx = mask_to_prefix(ch.get('mask'))
    if ip.version != 4 or pfx is None or not 8 <= pfx <= 30:
        return None, 'маска неверная: например 255.255.255.0 или 24'
    net = ipaddress.ip_network(f'{ip}/{pfx}', strict=False)
    if ip in (net.network_address, net.broadcast_address):
        return None, 'этот адрес — адрес сети или широковещательный, его нельзя назначить устройству'
    if ip.is_loopback or ip.is_multicast or ip.is_link_local:
        return None, 'этот адрес не подходит'
    gw = str(ch.get('gateway') or '').strip()
    if gw:
        try:
            g = ipaddress.ip_address(gw)
        except ValueError:
            return None, 'шлюз записан неверно'
        if g not in net:
            return None, f'шлюз {gw} не из той же сети, что адрес {ip}/{pfx}'
        if g == ip:
            return None, 'шлюз не может совпадать с адресом устройства'
    dns = [x for x in re.split(r'[,\s]+', str(ch.get('dns') or '')) if x]
    for x in dns:
        try:
            ipaddress.ip_address(x)
        except ValueError:
            return None, f'DNS «{x}» записан неверно'
    return {'iface': cur['name'], 'mode': 'static', 'ip': str(ip), 'prefix': pfx, 'mask': prefix_to_mask(pfx), 'gateway': gw, 'dns': dns[:2], 'cur': cur}, None


def commands(method, ch):
    """(apply, revert, backup) shell snippets for a method. `ch['cur']` is the old state — it builds the revert."""
    cur, q = ch['cur'], shlex.quote
    if method == 'synology':
        def setter(c):
            if c['mode'] == 'dhcp':
                return f"synonet --dhcp {q(c['name'])}"
            s = f"synonet --manual {q(c['name'])} {q(c['ip'])} {q(c['mask'])}"
            if c.get('gateway'):
                s += f"; synonet --set_gateway {q(c['gateway'])}"
            if c.get('dns'):
                s += f"; synonet --set_dns {q(c['dns'].split()[0])}"
            return s
        new = dict(ch, name=ch['iface'], dns=' '.join(ch.get('dns') or [])) if ch['mode'] == 'static' else dict(ch, name=ch['iface'])
        pre = 'export PATH=$PATH:/usr/syno/bin:/usr/syno/sbin\n'
        return pre + setter(new), pre + setter(cur), ''
    if method == 'openwrt':
        n = q(ch['iface'])
        if ch['mode'] == 'dhcp':
            ap = (f"uci set network.{n}.proto=dhcp; uci -q delete network.{n}.ipaddr; uci -q delete network.{n}.netmask; uci -q delete network.{n}.gateway; uci -q delete network.{n}.dns; uci commit network")
        else:
            ap = (f"uci set network.{n}.proto=static; uci set network.{n}.ipaddr={q(ch['ip'])}; uci set network.{n}.netmask={q(ch['mask'])}; "
                  + (f"uci set network.{n}.gateway={q(ch['gateway'])}; " if ch['gateway'] else f"uci -q delete network.{n}.gateway; ")
                  + f"uci -q delete network.{n}.dns; " + ''.join(f"uci add_list network.{n}.dns={q(d)}; " for d in ch['dns']) + "uci commit network")
        ap += '; /etc/init.d/network reload'
        return ap, 'cp /tmp/rl-network.bak /etc/config/network; /etc/init.d/network reload', 'cp /etc/config/network /tmp/rl-network.bak'
    if method == 'networkmanager':
        conn = q(cur.get('conn') or ch['iface'])
        if ch['mode'] == 'dhcp':
            ap = f'nmcli con mod {conn} ipv4.method auto ipv4.addresses "" ipv4.gateway "" ipv4.dns ""; nmcli con up {conn}'
        else:
            ap = (f"nmcli con mod {conn} ipv4.method manual ipv4.addresses {q(ch['ip'] + '/' + str(ch['prefix']))} ipv4.gateway {q(ch['gateway'])} ipv4.dns {q(' '.join(ch['dns']))}; nmcli con up {conn}")
        old = cur.get('rawMethod') or 'auto'
        rv = (f"nmcli con mod {conn} ipv4.method {q(old)} ipv4.addresses {q(cur.get('rawAddresses') or '')} ipv4.gateway {q(cur.get('rawGateway') or '')} ipv4.dns {q(cur.get('rawDns') or '')}; nmcli con up {conn}")
        return ap, rv, ''
    raise ValueError('этот способ не поддерживается')


def apply_script(method, ch):
    """one shell script: save the old state, start the timer that restores it, then apply in the background so the SSH session ends before the address changes"""
    ap, rv, backup = commands(method, ch)
    return f'''set -e
rm -f /tmp/rl-net-revert.pid
{backup}
cat > /tmp/rl-net-revert.sh <<'RLEOF'
{rv}
rm -f /tmp/rl-net-revert.sh /tmp/rl-net-revert.pid
RLEOF
cat > /tmp/rl-net-apply.sh <<'RLEOF'
{ap}
RLEOF
nohup sh -c 'sleep {ROLLBACK_SECONDS}; [ -f /tmp/rl-net-revert.sh ] && sh /tmp/rl-net-revert.sh' >/dev/null 2>&1 &
echo $! > /tmp/rl-net-revert.pid
nohup sh -c 'sleep 2; sh /tmp/rl-net-apply.sh; rm -f /tmp/rl-net-apply.sh' >/dev/null 2>&1 &
echo started
'''


CONFIRM_SCRIPT = '[ -f /tmp/rl-net-revert.pid ] && kill $(cat /tmp/rl-net-revert.pid) 2>/dev/null; rm -f /tmp/rl-net-revert.sh /tmp/rl-net-revert.pid /tmp/rl-network.bak; echo confirmed'
REVERT_NOW_SCRIPT = '[ -f /tmp/rl-net-revert.pid ] && kill $(cat /tmp/rl-net-revert.pid) 2>/dev/null; [ -f /tmp/rl-net-revert.sh ] && (nohup sh /tmp/rl-net-revert.sh >/dev/null 2>&1 &); echo reverting'


# ───────── what the panel sees locally ─────────
def local_view():
    """interfaces, addresses, gateway and DNS as seen from inside the process (with `--network host` that is the machine itself)"""
    ifs = {}
    try:
        for n in sorted(os.listdir('/sys/class/net')):
            if n == 'lo' or n.startswith(('veth', 'docker', 'br-')):
                continue
            def rd(f, n=n):
                try:
                    with open(f'/sys/class/net/{n}/{f}') as fh:
                        return fh.read().strip()
                except OSError:
                    return ''
            sp = rd('speed')
            ifs[n] = {'name': n, 'mac': rd('address'), 'state': rd('operstate') or 'unknown', 'speed': int(sp) if sp.lstrip('-').isdigit() and int(sp) > 0 else None, 'mtu': int(rd('mtu') or 0) or None, 'ips': []}
    except OSError:
        pass
    try:
        import subprocess
        txt = subprocess.run(['ip', '-o', '-4', 'addr', 'show'], capture_output=True, text=True, timeout=5).stdout
        for l in txt.splitlines():
            m = re.match(r'\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)', l)
            if m and m.group(1) in ifs:
                ifs[m.group(1)]['ips'].append({'ip': m.group(2), 'prefix': int(m.group(3))})
    except Exception:
        pass
    gw, gwif = '', ''
    try:
        with open('/proc/net/route') as f:
            next(f, None)
            for line in f:
                p = line.split()
                if len(p) > 3 and p[1] == '00000000' and int(p[3], 16) & 2:
                    gw, gwif = socket.inet_ntoa(bytes.fromhex(p[2])[::-1]), p[0]
                    break
    except (OSError, ValueError):
        pass
    dns = []
    try:
        with open('/etc/resolv.conf') as f:
            dns = [l.split()[1] for l in f if l.startswith('nameserver') and len(l.split()) > 1]
    except OSError:
        pass
    return {'interfaces': [i for i in ifs.values() if i['ips'] or i['state'] == 'up'], 'gateway': gw, 'gatewayIf': gwif, 'dns': dns[:3]}


def demo_view():
    return {'interfaces': [{'name': 'eth0', 'mac': 'aa:bb:cc:00:00:05', 'state': 'up', 'speed': 1000, 'mtu': 1500, 'ips': [{'ip': '10.0.0.5', 'prefix': 24}]}], 'gateway': '10.0.0.1', 'gatewayIf': 'eth0', 'dns': ['10.0.0.1']}


# ───────── the service ─────────
class HostNet:
    def __init__(self, app, demo=False):
        self.app, self.store, self.demo = app, app.store, demo
        self.pending = self.store._load('network_pending.json', {}) or {}

    @staticmethod
    def _ip(host):
        h = re.sub(r'^\w+://|[:/].*$', '', str(host or ''))
        return h if re.match(r'^\d+\.\d+\.\d+\.\d+$', h) else ''

    def own_ips(self):
        from . import netscan
        ips = set(netscan.local_ips())
        for i in local_view()['interfaces']:
            ips |= {x['ip'] for x in i['ips']}
        return ips

    def find_host(self):
        """the added device that is this very machine (its address is one of ours) and can be reached with a command line"""
        if self.demo:
            return next((d for d in self.store.cfg['devices'] if d.get('driver') == 'demo_server'), None)
        own = self.own_ips()
        for d in self.store.cfg['devices']:
            if d.get('driver') in HOST_DRIVERS and self._ip(d.get('host')) in own:
                return d
        return None

    def terminal_target(self):
        """→ (device, ssh config, '') or (None, None, reason): the machine Rack Live runs on and the SSH login stored for it"""
        d = self.find_host()
        if not d:
            return None, None, 'Эта машина не добавлена в Rack Live как устройство с доступом по SSH (NAS Synology, сервер на Linux, OpenWrt, роутер с Entware). Добавьте её в «Устройства» — и терминал станет доступен.'
        return self.ssh_target(d)

    def ssh_target(self, d):
        """→ (device, ssh config, '') for any device we can sign in to over SSH (the host machine or a server added as a device)"""
        drv, host = d.get('driver'), self._ip(d.get('host')) or re.sub(r'^\w+://|[:/].*$', '', d.get('host') or '')
        if drv == 'synology':
            return d, {'host': host, 'sshPort': d.get('sshPort') or 22, 'username': d.get('username') or '', 'password': d.get('password') or ''}, ''
        if drv == 'openwrt':
            return d, {'host': host, 'sshPort': d.get('sshPort') or 22, 'username': d.get('username') or 'root', 'password': d.get('password') or ''}, ''
        if drv in ('ssh', 'windows'):
            return d, {'host': host, 'sshPort': d.get('sshPort') or 22, 'username': d.get('username') or 'root', 'password': d.get('password') or '', 'privateKey': d.get('privateKey') or ''}, ''
        if drv == 'keenetic':
            if not d.get('entwarePassword'):
                return None, None, 'Rack Live стоит на роутере Keenetic: терминал открывается через Entware — введите пароль Entware в плагинах роутера (вкладка «Плагины» → Entware).'
            return d, {'host': host, 'sshPort': d.get('entwarePort') or 222, 'username': d.get('entwareUser') or 'root', 'password': d.get('entwarePassword')}, ''
        return None, None, 'для этого типа устройства терминал не поддерживается'

    def _run(self, d, script):
        from .drivers import REGISTRY
        return REGISTRY[d['driver']].command(d, script)

    def view(self):
        local = demo_view() if self.demo else local_view()
        own = sorted(self.own_ips()) if not self.demo else ['10.0.0.5']
        host = self.find_host()
        out = {'panel': dict(local, ips=own), 'host': None, 'pending': self._pending_public()}
        if not host:
            out['host'] = {'device': None, 'supported': False, 'why': 'Эта машина не добавлена в Rack Live как устройство с доступом по SSH (NAS Synology, сервер, OpenWrt). Добавьте её в «Устройства» — тогда настройки сети можно будет менять отсюда.', 'interfaces': []}
            return out
        d = host
        h = {'device': {'id': d['id'], 'name': d.get('name'), 'driver': d.get('driver')}, 'supported': False, 'why': '', 'interfaces': [], 'method': None, 'os': ''}
        try:
            if self.demo:
                h.update(method='synology', os='Демо', interfaces=[{'name': 'eth0', 'mode': 'static', 'ip': '10.0.0.5', 'mask': '255.255.255.0', 'gateway': '10.0.0.1', 'dns': '10.0.0.1'}])
            elif d['driver'] == 'synology':
                h.update(method='synology', os='Synology DSM', interfaces=parse_synonet(self._run(d, READ_SYNO)))
            elif d['driver'] == 'openwrt':
                h.update(method='openwrt', os='OpenWrt', interfaces=parse_uci(self._run(d, READ_OWRT)))
            elif d['driver'] == 'ssh':
                lin = parse_linux(self._run(d, READ_LINUX))
                h.update(method='networkmanager' if lin['manager'] == 'networkmanager' else lin['manager'], os=lin['os'], interfaces=lin['interfaces'])
            else:
                h.update(method='keenetic', os='Keenetic')
        except Exception as e:
            h['why'] = f'не удалось прочитать настройки по SSH: {e}'
            out['host'] = h
            return out
        m = h['method']
        if m in ('synology', 'openwrt', 'networkmanager'):
            h['supported'] = bool(h['interfaces'])
            h['why'] = '' if h['supported'] else 'интерфейсы не найдены'
        elif m == 'keenetic':
            h['why'] = 'Rack Live стоит на самом роутере: его сеть (LAN) настраивается в веб-интерфейсе роутера — менять её отсюда небезопасно.'
        else:
            h['why'] = {'netplan': 'В этой системе сеть настраивается через netplan, а такие изменения отсюда пока не поддерживаются.', 'ifupdown': 'В этой системе сеть настраивается через /etc/network/interfaces — отсюда не меняется.',
                        'networkd': 'В этой системе сеть настраивается через systemd-networkd — отсюда не меняется.'}.get(m, 'Способ настройки сети этой системы не определён — отсюда не меняется.')
        for i in h['interfaces']:
            i['panel'] = i.get('ip') in own
        out['host'] = h
        return out

    def _pending_public(self):
        p = self.pending
        if not p:
            return None
        if time.time() > p.get('deadline', 0) + 20:
            self.pending = {}
            self.store._dump('network_pending.json', {})
            return None
        return {k: p.get(k) for k in ('t', 'deadline', 'iface', 'mode', 'oldIp', 'newIp', 'deviceName')}

    @staticmethod
    def busy(ip):
        from . import netscan
        import socket as s
        for p in (80, 22, 443, 445, 5000, 8123):
            try:
                with s.create_connection((ip, p), .6):
                    return True
            except ConnectionRefusedError:
                return True
            except OSError:
                pass
        return bool(netscan.arp_table().get(ip))

    def apply(self, body):
        """→ dict; raises ValueError with a readable reason"""
        v = self.view()
        h = v['host']
        if not h or not h.get('supported'):
            raise ValueError((h or {}).get('why') or 'изменение сети здесь недоступно')
        if self.pending and self._pending_public():
            raise ValueError('уже есть неподтверждённое изменение — подтвердите его или верните прежние настройки')
        if str(body.get('confirm') or '').strip().upper() != 'ИЗМЕНИТЬ':
            raise ValueError('для подтверждения впишите слово ИЗМЕНИТЬ')
        ch, err = check_change(body, h['interfaces'])
        if err:
            raise ValueError(err)
        cur = ch['cur']
        if ch['mode'] == 'static' and ch['ip'] != cur.get('ip') and not self.demo and self.busy(ch['ip']):
            raise ValueError(f"адрес {ch['ip']} уже кем-то занят — выберите другой")
        d = self.find_host()
        script = apply_script(h['method'], ch)
        if self.demo:
            res = 'started'
        else:
            res = self._run(d, script)
            if 'started' not in res:
                raise ValueError('не удалось запустить изменение на устройстве: ' + res.strip()[-200:])
        now = time.time()
        self.pending = {'t': now, 'deadline': now + ROLLBACK_SECONDS, 'iface': ch['iface'], 'mode': ch['mode'], 'oldIp': cur.get('ip'), 'newIp': ch.get('ip') or '', 'deviceId': d['id'], 'deviceName': d.get('name'), 'method': h['method']}
        self.store._dump('network_pending.json', self.pending)
        self.store.add_event(None, 'Сеть панели', 'warning', f"запрошено изменение сети ({ch['iface']}: {'DHCP' if ch['mode'] == 'dhcp' else ch['ip']}); если не подтвердить за {ROLLBACK_SECONDS} с — вернётся как было")
        return {'ok': True, 'seconds': ROLLBACK_SECONDS, 'newIp': ch.get('ip') or '', 'mode': ch['mode']}

    def _candidates(self):
        p = self.pending
        d = next((x for x in self.store.cfg['devices'] if x['id'] == p.get('deviceId')), None)
        c = [p.get('newIp'), *sorted(self.own_ips()), self._ip((d or {}).get('host')), p.get('oldIp')]
        return d, [x for i, x in enumerate(c) if x and x not in c[:i]]

    def _on_host(self, script, newip_only=False):
        d, cands = self._candidates()
        if not d:
            raise ValueError('устройство для этой машины не найдено')
        last = None
        for ip in cands:
            dd = dict(d, host=re.sub(r'\d+\.\d+\.\d+\.\d+', ip, d.get('host') or '', count=1)) if re.search(r'\d+\.\d+\.\d+\.\d+', d.get('host') or '') else dict(d, host=ip)
            try:
                return d, ip, self._run(dd, script)
            except Exception as e:
                last = e
        raise ValueError(f'не удалось связаться с устройством по адресам {", ".join(cands)}: {last}')

    def confirm(self):
        if not self._pending_public():
            raise ValueError('нечего подтверждать — изменения нет или время вышло и прежние настройки уже возвращены')
        if self.demo:
            d, ip = next((x for x in self.store.cfg['devices'] if x['id'] == self.pending.get('deviceId')), None), self.pending.get('newIp')
        else:
            d, ip, out = self._on_host(CONFIRM_SCRIPT)
            if 'confirmed' not in out:
                raise ValueError('устройство не подтвердило: ' + out.strip()[-160:])
        p = self.pending
        if d and p.get('newIp') and p.get('oldIp') and p['newIp'] != p['oldIp']:            # the device entry must follow the new address
            with self.store.lock:
                d['host'] = (d.get('host') or '').replace(p['oldIp'], p['newIp'])
                self.store.save()
        self.pending = {}
        self.store._dump('network_pending.json', {})
        self.store.add_event(None, 'Сеть панели', 'info', 'изменение сети подтверждено')
        return {'ok': True}

    def revert(self):
        if not self._pending_public():
            raise ValueError('нечего возвращать')
        if not self.demo:
            self._on_host(REVERT_NOW_SCRIPT)
        self.pending = {}
        self.store._dump('network_pending.json', {})
        self.store.add_event(None, 'Сеть панели', 'warning', 'сетевые настройки возвращены как были')
        return {'ok': True}
