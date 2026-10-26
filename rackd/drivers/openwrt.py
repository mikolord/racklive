"""OpenWrt via ubus JSON-RPC (uhttpd-mod-ubus / LuCI); plugins (Forkop, Podkop, modem drivers) over SSH."""
import re
import time

from . import Driver, FIELD_HOST, FIELD_PASS, FIELD_USER
from .. import plugins, portal, remote
from ..util import DriverError, http_json


# captive portals and the like manage clients themselves: with any of these on the router, Rack Live does not touch clients
SPECIAL = {'opennds': 'captive-портал OpenNDS', 'nodogsplash': 'captive-портал Nodogsplash', 'chilli': 'CoovaChilli (hotspot)',
           'coova-chilli': 'CoovaChilli (hotspot)', 'wifidog': 'WiFiDog (hotspot)', 'uspot': 'uspot (captive-портал)'}
SPECIAL_SCRIPT = r"""for s in opennds nodogsplash chilli coova-chilli wifidog uspot; do [ -x /etc/init.d/$s ] && echo "@@special $s"; done
[ -x /etc/init.d/dnsmasq ] || echo "@@special nodnsmasq"
"""


def _in_net(ip, n):
    import ipaddress
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(f"{n['ip']}/{n['mask']}", strict=False)
    except (ValueError, TypeError, KeyError):
        return False


LOGIN_KEYS = ('login', 'password', 'hours', 'down', 'up', 'name', 'rules', 'after', 'smsHost', 'smsUser', 'smsPort', 'smsPass')      # what «guest login» may change


class OpenWrt(Driver):
    id = 'openwrt'
    title = 'OpenWrt'
    kind = 'router'
    description = 'Модель, прошивка, аптайм, память, интерфейсы и их адреса, DHCP-клиенты.'
    fields = [FIELD_HOST, dict(FIELD_USER, default='root'), FIELD_PASS,
              {'name': 'sshPort', 'label': 'Порт SSH (для плагинов)', 'type': 'text', 'default': '22',
               'hint': 'Плагины (Forkop, Podkop, драйверы модемов) ставятся по SSH с тем же логином и паролем'}]
    actions = [{'id': 'reboot', 'label': 'Перезагрузить', 'scope': 'device', 'confirm': 'Перезагрузить OpenWrt?'}]

    def _rpc(self, cfg):
        host = cfg['host'].rstrip('/')
        url = (host if host.startswith('http') else 'http://' + host) + '/ubus'

        def call(sid, obj, method, args=None):
            r = http_json(url, data={'jsonrpc': '2.0', 'id': 1, 'method': 'call', 'params': [sid, obj, method, args or {}]}, timeout=15)
            if 'error' in r:
                return None
            res = r.get('result') or [1]
            return res[1] if len(res) > 1 else {}
        sid = (call('0' * 32, 'session', 'login', {'username': cfg.get('username') or 'root', 'password': cfg.get('password', '')}) or {}).get('ubus_rpc_session')
        if not sid:
            raise DriverError('неверный логин/пароль или ubus недоступен')
        return lambda obj, method, args=None: call(sid, obj, method, args)

    def poll(self, cfg):
        call = self._rpc(cfg)
        board, info = call('system', 'board') or {}, call('system', 'info') or {}
        ifs = {i['interface']: i for i in (call('network.interface', 'dump') or {}).get('interface', [])}
        dev = call('network.device', 'status') or {}
        leases = (call('luci-rpc', 'getDHCPLeases') or {}).get('dhcp_leases', [])
        mem = info.get('memory', {})
        ip = lambda i: ', '.join(a['address'] for a in i.get('ipv4-address', [])) or '—'
        hw = self._hw_ports(cfg)                     # real sockets via swconfig (SSH); None = not available
        ports, usb = ((hw['ports'] or []), hw['usb']) if hw else ([], [])
        if hw and hw['ports'] is None:
            hw = dict(hw, ports=[])
            hw_sw = False
        else:
            hw_sw = bool(hw)
        wan_v = {int(str(v.get('l3_device')).rsplit('.', 1)[1]) for k, v in ifs.items()
                 if k.startswith('wan') and re.match(r'.+\.\d+$', str(v.get('l3_device') or ''))}
        for p in ports:
            if set(p.get('vlansU') or []) & wan_v:
                p.update(kind='wan', label='WAN')
        if not hw_sw:
            for name, d in sorted(dev.items()):
                if '.' in name or not (name.startswith('eth') or name.startswith('lan') or name.startswith('wan')):
                    continue
                sp = int(''.join(c for c in str(d.get('speed') or '') if c.isdigit()) or 0)
                if d.get('carrier') and sp not in (10, 100, 1000, 2500, 5000, 10000):
                    usb.append({'name': name, 'speed': sp})   # e.g. a USB LTE modem reporting «150» — not an Ethernet socket
                    continue
                ports.append({'n': len(ports) + 1, 'name': name, 'kind': 'wan' if name.startswith('wan') else 'rj45', 'link': bool(d.get('carrier')),
                              'speed': sp if d.get('carrier') else 0, 'label': '', 'vlansU': [], 'vlansT': [], 'peers': []})
        nets = self._networks(ifs)
        hosts, blocks = (hw or {}).get('hosts', {}), (hw or {}).get('blocks', set())
        clients = []
        for l in leases:
            mac = (l.get('macaddr') or '').lower(); h = hosts.get(mac) or {}
            net = next((n for n in nets if _in_net(l.get('ipaddr'), n)), None)
            clients.append({'mac': mac, 'ip': l.get('ipaddr'), 'name': h.get('label') or h.get('name') or l.get('hostname') or '', 'hostname': l.get('hostname') or '',
                            'segment': net['name'] if net else 'LAN', 'segId': net['id'] if net else None, 'registered': bool(h),
                            'staticIp': h.get('ip'), 'access': 'deny' if mac in blocks else 'permit', 'policy': '', 'limit': 0,
                            'online': True, 'kind': 'phone'})
        special = (hw or {}).get('special') or []
        mgmt = ({'ok': False, 'reason': 'нет доступа по SSH — Rack Live не может проверить роутер и менять настройки клиентов'} if not hw else
                {'ok': False, 'reason': f"на роутере работает {', '.join(special)} — он сам управляет доступом клиентов; чтобы ничего не сломать, "
                                        'настройки клиентов из Rack Live на этом роутере отключены'} if special else {'ok': True})
        load = info.get('load') or [0]
        return {'status': 'online',
                'summary': {'model': board.get('model'), 'fw': (board.get('release') or {}).get('description'), 'uptime': info.get('uptime'),
                            'mem': round(100 - (mem.get('free', 0) + mem.get('buffered', 0)) * 100 / max(1, mem.get('total', 1))),
                            'cpu': round(load[0] / 65536 * 100), 'ip': cfg['host'],
                            'macs': sorted({(d.get('macaddr') or '').lower() for d in dev.values() if d.get('macaddr')})},
                'ports': ports, 'clients': clients, 'networks': nets, 'policies': [],
                'clientMgmt': mgmt, 'clientCaps': {'limit': False, 'policy': False, 'deny': True},
                'sections': [{'title': 'Интерфейсы', 'rows': [[k, f"{'▲' if v.get('up') else '▽'} {ip(v)} · {v.get('l3_device') or ''}"]
                                                              for k, v in sorted(ifs.items()) if k != 'loopback']}] +
                            ([{'title': 'USB', 'rows': [[u['name'], 'USB-модем / сетевой адаптер' + (f" · заявлено до {u['speed']} Мбит/с" if u.get('speed') else '')]
                                                        for u in usb]}] if usb else [])}

    @staticmethod
    def _networks(ifs):
        import ipaddress
        out = []
        for k, v in sorted(ifs.items()):
            a = (v.get('ipv4-address') or [{}])[0]
            if k == 'loopback' or k.startswith('wan') or not a.get('address'):
                continue
            if any(r.get('target') == '0.0.0.0' and not r.get('mask') for r in v.get('route') or []):
                continue                             # the uplink (a USB modem, a second WAN) — not a network of clients
            mask = str(ipaddress.ip_network(f"0.0.0.0/{a.get('mask', 24)}").netmask)
            out.append({'id': k, 'name': k, 'alias': v.get('l3_device') or '', 'vlan': None, 'ip': a['address'], 'mask': mask})
        return out

    @staticmethod
    def _parse_extra(out):
        special, hosts, sect, blocks = [], {}, {}, set()
        for l in out.split('\n'):
            l = l.strip()
            if l.startswith('@@special '):
                k = l.split()[1]
                special.append('dnsmasq не установлен (DHCP через другой сервер)' if k == 'nodnsmasq' else SPECIAL.get(k, k))
            elif l.startswith('@@dh '):
                m = re.match(r"@@dh dhcp\.([^.=]+)\.(mac|ip|name|rl_label)='?([^']*)'?$", l)
                if m:
                    sect.setdefault(m.group(1), {})[m.group(2)] = m.group(3)
            elif l.startswith('@@fw '):
                m = re.match(r"@@fw firewall\.rl_block_[^.]+\.src_mac='?([0-9A-Fa-f:]{17})'?", l)
                if m:
                    blocks.add(m.group(1).lower())
        for v in sect.values():
            for mac in (v.get('mac') or '').lower().split():
                hosts[mac] = {'name': v.get('name', ''), 'label': v.get('rl_label', ''), 'ip': v.get('ip')}
        return {'special': sorted(set(special)), 'hosts': hosts, 'blocks': blocks}

    # ───────── one client: name (a DHCP host entry), permanent IP, block — only on a router without a captive portal ─────────
    def client(self, cfg, mac, want):
        mac = str(mac or '').lower()
        if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
            raise DriverError('неверный MAC-адрес')
        special = self._parse_extra(self._ssh(cfg, SPECIAL_SCRIPT, timeout=20))['special']
        if special:
            raise DriverError(f"на роутере {', '.join(special)} — настройки клиентов из Rack Live отключены, чтобы ничего не сломать")
        if 'limit' in want and float(want.get('limit') or 0) > 0:
            raise DriverError('ограничение скорости на OpenWrt пока не поддерживается')
        if want.get('policy') not in (None, '', 'deny'):
            raise DriverError('политики маршрутизации на OpenWrt пока не поддерживаются — только «по умолчанию» или «запретить интернет»')
        q = lambda v: re.sub(r"[^\w .,:@()+-]", '', str(v or ''), flags=re.U)[:64]       # nothing that could break the quoting
        tag = mac.replace(':', '')
        find = f"S=$(uci -q show dhcp | grep -i \"\\.mac='{mac}'\" | head -n1 | cut -d. -f2)\n"
        lines, done = [find], []
        if want.get('forget'):
            lines += ['[ -n "$S" ] && uci delete dhcp.$S', f'uci -q delete firewall.rl_block_{tag}', 'uci commit dhcp', 'uci commit firewall',
                      '/etc/init.d/dnsmasq reload', '/etc/init.d/firewall reload']
            done.append('запись клиента и блокировка удалены')
        else:
            dhcp = False
            if 'name' in want or want.get('ip'):
                lines += ['[ -z "$S" ] && S=$(uci add dhcp host) && uci set dhcp.$S.mac=' + f"'{mac}'"]
            if 'name' in want:
                label = q(want.get('name')).strip()
                if not label:
                    raise DriverError('укажите имя устройства')
                host = re.sub(r'-+', '-', re.sub(r'[^a-z0-9-]', '-', _translit(label).lower())).strip('-')[:40] or 'host-' + tag[-6:]
                lines += [f"uci set dhcp.$S.name='{host}'", f"uci set dhcp.$S.rl_label='{label}'"]
                done.append(f'имя «{label}»'); dhcp = True
            if 'ip' in want:
                ip = str(want.get('ip') or '').strip()
                if ip:
                    if not re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                        raise DriverError('неверный IP-адрес')
                    lines.append(f"uci set dhcp.$S.ip='{ip}'"); done.append(f'постоянный адрес {ip}')
                else:
                    lines.append('[ -n "$S" ] && uci -q delete dhcp.$S.ip'); done.append('постоянный адрес снят')
                dhcp = True
            if dhcp:
                lines += ['uci commit dhcp', '/etc/init.d/dnsmasq reload']
            if 'policy' in want:
                if want['policy'] == 'deny':
                    lines += ["Z=$(uci show firewall | grep \"\\.masq='1'\" | head -n1 | cut -d. -f2); ZN=$(uci -q get firewall.$Z.name); [ -z \"$ZN\" ] && ZN=wan",
                              f'uci set firewall.rl_block_{tag}=rule', f"uci set firewall.rl_block_{tag}.name='Rack Live: no internet {mac}'",
                              f"uci set firewall.rl_block_{tag}.src='*'", f"uci set firewall.rl_block_{tag}.src_mac='{mac}'",
                              f'uci set firewall.rl_block_{tag}.dest="$ZN"', f"uci set firewall.rl_block_{tag}.target='REJECT'"]
                    done.append('доступ в интернет запрещён')
                else:
                    lines.append(f'uci -q delete firewall.rl_block_{tag}'); done.append('доступ в интернет по умолчанию')
                lines += ['uci commit firewall', '/etc/init.d/firewall reload >/dev/null 2>&1']
        out = self._ssh(cfg, '\n'.join(lines) + '\necho @@ok\n', timeout=60)
        if '@@ok' not in out:
            raise DriverError('роутер не подтвердил изменения: ' + out.strip()[-200:])
        return done

    # ───────── physical ports: swconfig switch chips (ath79 / ramips boards like the MikroTik RB2011) ─────────
    _hw_fail = {}                                  # host → time of the last failed SSH (back off 10 min)
    HW_SCRIPT = r'''for i in /sys/class/net/*; do n=${i##*/}; u=$(readlink -f $i/device 2>/dev/null | grep -c usb); echo "@@if $n $u $(cat $i/speed 2>/dev/null)"; done
for s in $(swconfig list 2>/dev/null | awk '{print $2}'); do echo "@@sw $s"; swconfig dev $s show 2>/dev/null; done
''' + SPECIAL_SCRIPT + r'''uci -q show dhcp | grep -E "^dhcp\.[^.]+(=host|\.(mac|ip|name|rl_label)=)" | sed 's/^/@@dh /'
uci -q show firewall | grep -E "^firewall\.rl_block_[^.]+(=|\.src_mac=)" | sed 's/^/@@fw /'
'''

    def _hw_ports(self, cfg):
        host = self._hostname(cfg)
        if time.time() - self._hw_fail.get(host, 0) < 600:
            return None
        try:
            out = self._ssh(cfg, self.HW_SCRIPT, timeout=20)
        except Exception:
            self._hw_fail[host] = time.time()
            return None
        usb, switches, sw, port, vlan = [], [], None, None, None
        for l in out.split('\n'):
            s = l.strip()
            if s.startswith('@@if '):
                f = s.split()
                if len(f) >= 3 and f[2] == '1' and not '.' in f[1]:
                    usb.append({'name': f[1], 'speed': int(f[3]) if len(f) > 3 and f[3].isdigit() else 0})
            elif s.startswith('@@sw '):
                sw = {'name': s[5:], 'ports': {}, 'vlans': {}}
                switches.append(sw)
                port = vlan = None
            elif sw is None:
                continue
            elif re.match(r'Port (\d+): MAC ([0-9a-f:]{17})', s):
                m = re.match(r'Port (\d+): MAC ([0-9a-f:]{17})', s)
                sw['ports'].setdefault(int(m.group(1)), {'peers': []})['peers'].append({'mac': m.group(2)})
            elif re.match(r'Port (\d+):$', s):
                port, vlan = int(s[5:-1]), None
                sw['ports'].setdefault(port, {'peers': []})
            elif re.match(r'VLAN (\d+):$', s):
                vlan, port = int(s[5:-1]), None
            elif s.startswith('link:') and port is not None:
                m = re.search(r'link:(up|down)(?:\s+speed:(\d+))?', s)
                sw['ports'][port].update(link=bool(m and m.group(1) == 'up'), speed=int(m.group(2)) if m and m.group(2) else 0)
            elif s.startswith('vid:') and vlan is not None:
                sw['vlans'][vlan] = {'vid': int(s[4:].strip() or vlan), 'members': []}
            elif s.startswith('ports:') and vlan is not None:
                sw['vlans'].setdefault(vlan, {'vid': vlan, 'members': []})['members'] = s[6:].split()
        extra = self._parse_extra(out)
        if not switches:
            return dict(extra, ports=None, usb=usb)
        ports = []
        for sw in switches:
            tagged = {int(m[:-1]) for v in sw['vlans'].values() for m in v['members'] if m.endswith('t')}
            cpu = tagged | {0} | ({6} if max(sw['ports'] or [0]) == 6 else set())     # CPU links: tagged trunk, port 0, ar83xx port 6
            for n in sorted(sw['ports']):
                if n in cpu or 'link' not in sw['ports'][n]:
                    continue
                p = sw['ports'][n]
                vu = sorted(v['vid'] for v in sw['vlans'].values() if str(n) in v['members'])
                vt = sorted(v['vid'] for v in sw['vlans'].values() if f'{n}t' in v['members'])
                ports.append({'n': len(ports) + 1, 'name': f"{sw['name']} · порт {n}", 'kind': 'rj45', 'link': p['link'],
                              'speed': p['speed'] if p['link'] else 0, 'label': '', 'vlansU': vu, 'vlansT': vt,
                              'peers': p['peers'] if p['link'] else []})
        return dict(extra, ports=ports, usb=usb)

    def action(self, cfg, action_id, params):
        if action_id == 'reboot':
            self._rpc(cfg)('system', 'reboot')
            return 'OpenWrt перезагружается'
        return super().action(cfg, action_id, params)

    # ───────── plugins (SSH: same root login as the web interface) ─────────
    @staticmethod
    def _hostname(cfg):
        return re.sub(r'^\w+://', '', cfg['host'].strip()).split('/')[0].split(':')[0]

    shell = 'shell OpenWrt по SSH (ash, root): uci show/set/commit, ubus call, logread, /etc/init.d/…, apk/opkg'

    def command(self, cfg, cmd):
        return self._ssh(cfg, '{\n' + cmd + '\n} 2>&1\n', timeout=120)

    def _ssh(self, cfg, script, timeout=30):
        from .sshhost import SSHHost
        return SSHHost()._run({'host': self._hostname(cfg), 'sshPort': cfg.get('sshPort') or 22, 'username': cfg.get('username') or 'root',
                               'password': cfg.get('password') or ''}, script, timeout=timeout)

    def inet_test(self, cfg, iface=None):
        from .. import inet
        return inet.parse_curl(self._ssh(cfg, 'IFACE=""\nBIN=/tmp/rl-bin\n' + inet.CURL_TEST, 180))

    def backup(self, cfg):
        """Full UCI configuration (all /etc/config files) — the text that is versioned."""
        out = self._ssh(cfg, 'uci export 2>/dev/null; echo @@end', 40)
        if '@@end' not in out:
            raise DriverError('OpenWrt не отдал конфигурацию')
        return out.split('@@end')[0]

    def _state(self, cfg):
        out = self._ssh(cfg, plugins.OWRT_STATUS, 30)
        if '@@end' not in out:
            raise DriverError('OpenWrt ответил не полностью')
        return plugins.parse_owrt(out)

    def plugins(self, cfg):
        st = self._state(cfg)
        major = int((re.findall(r'\d+', st['rel']) or ['0'])[0])
        free_mb = (st['free'] or 0) // 1024
        host, out = self._hostname(cfg), []
        for p in plugins.for_driver(self.id):
            p['pm'], p['fw'] = st['pm'], st['rel']
            if p['id'] in plugins.OWRT_INSTALLERS:
                inst = plugins.OWRT_INSTALLERS[p['id']]
                other, min_rel = inst['conflict'], inst.get('minRel', 24)
                p['installed'] = inst['packages'][0] in st['pkgs']
                p['version'] = st['pkgs'].get(inst['packages'][0])
                p['url'], p['login'] = f"http://{host}/cgi-bin/luci/{inst['luci']}", 'логин и пароль от OpenWrt (LuCI)'
                p['ssh'] = {'ok': True, 'native': True}
                p['checks'] = [{'label': f"OpenWrt {min_rel}.{'05' if min_rel == 23 else '10'} или новее (у вас {st['rel'] or '?'})", 'ok': major >= min_rel},
                               {'label': f"Свободно на флеше от {inst['freeMB']} МБ (сейчас {free_mb} МБ)", 'ok': p['installed'] or free_mb >= inst['freeMB']}]
                if other:
                    p['checks'].append({'label': f"Не установлен {other.capitalize()} — они конфликтуют", 'ok': other not in st['pkgs']})
                replaced = [x.capitalize() for x in inst.get('replaces', ()) if x in st['pkgs']]
                if replaced and not p['installed']:
                    p['warning'] = f"На роутере стоит {' и '.join(replaced)}: установщик {p['title']} удалит {'его' if len(replaced) == 1 else 'их'} " \
                                   f"(файлы настроек останутся в /etc/config, но сайты и подписки придётся занести в {p['title']} заново)."
                elif 'https-dns-proxy' in st['pkgs'] and not p['installed'] and other:
                    p['warning'] = 'Установщик удалит конфликтующий пакет https-dns-proxy (DNS через HTTPS).'
                if p['id'] == 'tachyon':
                    p['options'] = [{'id': 'core', 'label': 'Родное ядро tachyon-core (Rust) вместо sing-box', 'on': False,
                                     'hint': 'Свой движок Tachyon. Если не уверены — оставьте выключенным: тогда ставится обычный sing-box, его можно сменить позже в LuCI.'}]
                if p['id'] == 'forkop':
                    p['singbox'] = st['sb']
                    p['options'] = [{'id': 'extended', 'label': 'sing-box extended — поддержка XHTTP', 'on': True,
                                     'hint': 'Без него XHTTP-ссылки не заработают. Обычный sing-box легче.'}]
            elif p['id'] == 'modem':
                sug = plugins.modem_suggest(st)
                p['usb'], p['drivers'], p['devs'], p['suggest'] = st['usb'], st['drv'], st['dev'], sug
                p['profiles'] = [dict(m, installed=m['key'] in st['pkgs'], suggested=m['id'] == sug) for m in plugins.MODEM_PROFILES]
                p['installed'] = any(m['installed'] for m in p['profiles'])
                p['checks'] = [{'label': 'Модем подключён к USB' + (f": {st['usb'][0]}" if st['usb'] else ''), 'ok': bool(st['usb'])}]
            elif p['id'] == 'portal':
                hw = portal.parse_status(self._ssh(cfg, portal.STATUS, 40))
                p.update(self._portal_card(hw, st))
            elif p['id'] == 'remote':
                p.update(self._remote_card(remote.parse(self._ssh(cfg, remote.STATUS, 30))))
            elif p['id'] == 'meshnode':
                ms = plugins.parse_meshnode(self._ssh(cfg, plugins.MESHNODE_STATUS, 30))
                free_mb = (ms['free'] or 0) // 1024
                p['installed'] = ms['svc'] and ms['run']
                p['member'] = ms['member']
                p['ssids'] = ms['ssid']
                space_ok = p['installed'] or ms['py'] or free_mb >= 10          # Python уже стоит → место под него не нужно
                p['checks'] = [{'label': f"Есть Wi-Fi (точек радио: {ms['wifi']})", 'ok': ms['wifi'] > 0},
                               {'label': 'Python 3 ' + ('установлен' if ms['py'] else 'поставится сам (~10 МБ)'), 'ok': ms['py'] or free_mb >= 10},
                               {'label': ('Python уже стоит — место не нужно' if ms['py'] else f"Свободно на флеше ≥ 10 МБ (сейчас {free_mb} МБ)"), 'ok': space_ok},
                               {'label': 'Поддержка WPA3 (wpad с SAE — доставится при необходимости)', 'ok': True}]
                if ms['svc']:
                    p['status'] = ('работает, принят в Mesh' if ms['member'] else 'запущен, ждёт приёмки в приложении Keenetic') if ms['run'] else 'установлен, но не запущен'
            out.append(p)
        return {'fw': st['rel'], 'pm': st['pm'], 'plugins': out}

    # ───────── «Удалённый доступ» (rackd/remote.py) ─────────
    @staticmethod
    def _remote_card(rs):
        free_mb = (rs['free'] or 0) // 1024
        major = int((re.findall(r'\d+', rs['rel'] or '') or ['0'])[0])
        card = {'installed': rs['installed'], 'tunnel': rs}
        card['checks'] = [{'label': f"OpenWrt 22.03 или новее (у вас {rs['rel'] or '?'})", 'ok': major >= 22},
                          {'label': 'WireGuard ' + ('уже установлен' if rs['wg'] else f'поставится сам (~1 МБ, свободно {free_mb} МБ)'), 'ok': rs['wg'] or free_mb >= 1}]
        if rs['installed']:
            card['status'] = (f"на связи · {rs['ip']}" if rs['up'] else f"нет связи с центром · {rs['ip']}")
        return card

    # ───────── «Гостевой Wi-Fi с порталом» (rackd/portal.py) ─────────
    @staticmethod
    def _portal_card(hw, st=None):
        major = int((re.findall(r'\d+', hw['rel'] or '') or ['0'])[0])
        free_mb = (hw['free'] or 0) // 1024
        prof = hw['profile']
        card = {'installed': bool(prof), 'hw': {k: hw[k] for k in ('model', 'lan', 'wan', 'links', 'radios', 'mgmt', 'via', 'wanip', 'lanip', 'clients', 'nds', 'ndsEnabled', 'ndsRunning', 'rollback', 'nopass', 'foreign')},
                'routerProfile': portal.public(prof), 'portText': portal.PORT_TEXT, 'defaults': portal.public(portal.DEFAULTS)}
        card['checks'] = [{'label': f"OpenWrt 23.05 или новее (у вас {hw['rel'] or '?'})", 'ok': major >= 23},
                          {'label': f"Есть Wi-Fi (радио: {', '.join(r['band'].replace('g', ' ГГц').replace('2 ', '2,4 ') for r in hw['radios']) or 'нет'})", 'ok': bool(hw['radios'])},
                          {'label': 'OpenNDS ' + (f"установлен ({hw['nds']})" if hw['nds'] else f"поставится сам (нужно ~2 МБ, свободно {free_mb} МБ)"), 'ok': bool(hw['nds']) or free_mb >= 2},
                          {'label': 'Кабель провайдера в WAN-порту' + (f" ({hw['wanip']})" if hw['wanip'] else ''), 'ok': bool((hw['links'].get(hw['wan']) or {}).get('up')), 'optional': True,
                           'hint': 'без него гости не получат интернет' if not (hw['links'].get(hw['wan']) or {}).get('up') else ''}]
        if hw.get('swconfig') and not prof:
            card['checks'].append({'label': 'Старый коммутатор (swconfig, как у MikroTik RB2011): гостевая сеть настроится отдельным VLAN коммутатора и своим мостом', 'ok': True})
            if hw.get('via') and hw['via'] != hw.get('wan'):
                card['checks'].append({'label': f"Rack Live заходит на роутер через {hw['via']}, а не через WAN ({hw.get('wan')}): на этой модели порты делятся по VLAN, и связь могла бы оборваться. Подключите роутер к сети через порт WAN", 'ok': False})
        fg = None if prof else hw.get('foreign')
        if fg:                                  # портал уже стоит, но не нашим плагином: показываем его и не даём плагину его перенастроить
            card['foreign'] = fg
            card['status'] = f"найден портал «{fg['name']}», настроенный вручную · " + ('работает' if hw['ndsRunning'] else 'выключен') \
                             + (f" · гостей: {hw['clients']}" if hw['clients'] is not None and hw['ndsRunning'] else '')
            card['checks'].append({'label': 'На роутере уже работает портал, настроенный вручную — плагин его не заменяет и сеть не трогает', 'ok': False})
        if prof:
            card['status'] = ('портал работает' if hw['ndsRunning'] else 'портал выключен') + (f" · гостей: {hw['clients']}" if hw['clients'] is not None and hw['ndsRunning'] else '')
        return card

    def _portal(self, cfg, op, params):
        import ipaddress
        prog = params.get('_progress') or (lambda s: None)
        status = lambda c: portal.parse_status(self._ssh(c, portal.STATUS, 40))
        fail = lambda out: re.search(r'@@fail (.+)', out)
        if op == 'status':
            return dict(self._portal_card(status(cfg)), ok=True)
        if op == 'install':
            prog('Проверяю роутер…')
            hw = status(cfg)
            if hw.get('swconfig') and hw.get('via') and hw['via'] != hw.get('wan'):
                raise DriverError(f"Rack Live заходит на роутер через {hw['via']}, а не через WAN ({hw.get('wan')}). У роутера со старым коммутатором (swconfig) порты делятся по VLAN, "
                                  'и при перенастройке связь могла бы оборваться. Подключите роутер к сети через порт WAN — ничего не изменено.')
            if hw.get('swconfig') and not hw['swports']:
                raise DriverError('не удалось определить порты старого коммутатора (swconfig) — ничего не изменено.')
            if hw['foreign'] and not hw['profile']:
                raise DriverError(f"на роутере уже работает портал «{hw['foreign']['name']}», настроенный вручную. Установка плагина перенастроила бы сеть, Wi-Fi, DHCP и "
                                  'межсетевой экран и заменила бы его, поэтому она отключена — ничего не изменено.')
            prof = portal.validate(portal.merge_secrets(params.get('profile'), params.get('_old') or hw['profile']), hw)      # «не менять» = keep what Rack Live or the router itself has
            root_pass = str(params.get('rootPass') or '')
            if hw['nopass'] and not root_pass:
                raise DriverError('у роутера нет пароля администратора (root) — задайте его в разделе «Дополнительно»: роутер отдаётся клиенту, без пароля в него может зайти любой')
            if root_pass:
                root_pass = portal.check_root_pass(root_pass)
            hello = params['_hello']
            if not hw['profile'] and '@@foreign' in self._ssh(cfg, portal.FOREIGN_DHCP, 30):
                raise DriverError('в основной сети роутера уже есть другой DHCP-сервер (другой роутер): похоже, кабель от вашей сети воткнут в LAN-порт. '
                                  'Если настроить сейчас, роутер начнёт раздавать адреса чужой сети. Переткните этот кабель в порт WAN и попробуйте снова.')
            prog('Ставлю OpenNDS, копирую шаблон, записываю настройки…')
            out = self._ssh(cfg, portal.apply_script(prof, hw, params['_files'], hello['url'], hello['token'], root_pass), timeout=600)
            if fail(out):
                raise DriverError(fail(out).group(1).strip())
            if '@@scheduled' not in out:
                raise DriverError('роутер не подтвердил запуск настройки — ничего не применено, через 4 минуты он сам вернёт прежнее')
            prog('Роутер перезапускает сеть — жду, пока он снова выйдет на связь (до 4 минут)…')
            old, lan_ip = self._hostname(cfg), str(ipaddress.ip_interface(prof['lan']).ip)
            deadline = time.time() + portal.ROLLBACK_SEC - 30
            time.sleep(15)
            while time.time() < deadline:
                h = portal.HELLO.get(hello['token']) or {}
                try:                                                         # by the WAN MAC in the lists of the main router
                    found = params['_find'](hw['wanmac']) if params.get('_find') and hw['wanmac'] else None
                except Exception:
                    found = None
                for host in dict.fromkeys(x for x in (h.get('wan'), found, lan_ip, old) if x):
                    login = dict(cfg, host=host, password=root_pass or cfg.get('password') or '')
                    try:
                        if '@@done' not in self._ssh(login, portal.VERIFY, timeout=15):      # reachable, but still installing OpenNDS — wait
                            prog('Роутер снова на связи, заканчивает установку OpenNDS…')
                            break
                        out = self._ssh(login, portal.CONFIRM + portal.VERIFY + portal.STATUS, timeout=20)
                    except DriverError:
                        continue
                    if '@@confirmed' not in out:
                        continue
                    v = dict(re.findall(r'@@([gwnd]) (\S*)', out))
                    after = portal.parse_status(out)
                    problems = [t for k, t in (('g', 'у гостевой сети нет адреса'), ('n', 'OpenNDS не запустился')) if (k == 'g' and not v.get('g')) or (k == 'n' and prof['portal'] and v.get('n') != '1')]
                    if '@@err' in out:
                        problems.insert(0, 'OpenNDS не установился (нет интернета на WAN?) — гостевая Wi-Fi работает без страницы входа; нажмите «Применить изменения», когда интернет появится')
                    if not v.get('w') or v.get('w') == '0':
                        problems.append('Wi-Fi не поднялся')
                    via = 'по WAN' if host in (h.get('wan'), found) and host != old else 'в основной сети' if host == lan_ip and host != old else 'по прежнему адресу'
                    msg = (f"Роутер настроен: основная Wi-Fi «{prof['mainSsid']}», гостевая «{prof['guestSsid']}» "
                           f"{'с порталом' if prof['portal'] else 'без портала'}. Rack Live теперь заходит на него {via}: {host}.")
                    if problems:
                        msg += ' Но: ' + '; '.join(problems) + '.'
                    return {'ok': True, 'message': msg, 'problems': problems, 'host': host, 'card': self._portal_card(after),
                            'deviceUpdate': dict({'host': host, 'portal': prof}, **({'password': root_pass} if root_pass else {}))}
                time.sleep(5)
            raise DriverError(f'роутер не вышел на связь. Через пару минут он сам вернёт прежние настройки и снова будет доступен по адресу {old}.')
        if op == 'prepare_wan':                                  # Rack Live is in the network above this router's WAN (a bench): open management there first
            hw = status(cfg)
            new_lan = portal.free_lan(hw['lanip'])
            out = self._ssh(cfg, portal.prepare_wan_script(new_lan), timeout=40)
            mac = (re.search(r'@@wanmac (\S+)', out) or [None, ''])[1]
            if not mac:
                raise DriverError('не удалось подготовить роутер')
            return {'ok': True, 'wanmac': mac, 'lan': new_lan, 'deviceUpdate': {'portalWanMac': mac},
                    'message': f'Готово: управление со стороны WAN открыто (только для частных адресов), а LAN роутера переведён в {new_lan}, чтобы не пересекаться с вашей сетью. '
                               'Через несколько секунд Rack Live потеряет роутер — так и должно быть. Переткните кабель вашей сети из LAN-порта в WAN, подождите полминуты и нажмите «Найти роутер».'}
        if op == 'toggle':
            on = bool(params.get('on'))
            out = self._ssh(cfg, portal.toggle_script(on), timeout=60)
            running = '@@nds 1' in out
            saved = dict(params.get('_old') or status(cfg)['profile'] or {}, portal=on)
            if on and not running:
                return {'ok': False, 'error': 'OpenNDS не запустился — посмотрите журнал роутера', 'deviceUpdate': {'portal': saved}}
            return {'ok': True, 'message': 'Портал включён: гости сначала видят страницу входа' if on else 'Портал выключен: гостевая Wi-Fi работает без страницы входа',
                    'deviceUpdate': {'portal': saved}}
        if op == 'login':                               # the guest login only: no network restart, guests already in stay in
            hw = status(cfg)
            old = params.get('_old') or hw['profile'] or {}
            if not old:
                raise DriverError('сначала настройте роутер')
            new = {k: v for k, v in (params.get('profile') or {}).items() if k in LOGIN_KEYS}
            prof = portal.validate(portal.merge_secrets(dict(old, **new), old), hw)
            if prof['login'] == 'sms' and not prof['smsReady']:
                raise DriverError('Вход по СМС: сначала подготовьте роутер с SIM (кнопка «Подготовить роутер с SIM»)')
            if '@@ok' not in self._ssh(cfg, portal.login_script(prof), timeout=60):
                raise DriverError('настройки входа не записались')
            return {'ok': True, 'message': 'Вход гостей обновлён — действует для новых входов, сеть не перезапускалась', 'deviceUpdate': {'portal': prof}}
        if op == 'sms_setup':                           # prepare the router with the SIM card (through this router) and write the SMS login
            hw = status(cfg)
            old = params.get('_old') or hw['profile'] or {}
            if not old:
                raise DriverError('сначала настройте роутер')
            new = {k: v for k, v in (params.get('profile') or {}).items() if k in LOGIN_KEYS}
            prof = portal.validate(portal.merge_secrets(dict(old, **dict(new, login='sms')), old), hw, strict_sms=True)
            if not prof['smsPass']:
                raise DriverError('введите пароль роутера с SIM')
            prog('Записываю вход по СМС на роутер…')
            if '@@ok' not in self._ssh(cfg, portal.login_script(prof), timeout=60):
                raise DriverError('настройки входа не записались')
            prog('Готовлю роутер с SIM (пакеты ставятся минуту-две)…')
            out = self._ssh(cfg, portal.sms_setup_script(prof), timeout=900)
            if fail(out):
                raise DriverError(fail(out).group(1).strip())
            gw = '\n'.join(re.findall(r'@@gw (.*)', out))
            if '+CPIN: READY' not in gw:
                raise DriverError('Связь с роутером с SIM есть, но SIM-карта не готова: ' + (re.findall(r'\+CP[A-Z]+:.*|\+CME ERROR.*', gw) or ['модем не ответил'])[0])
            sig = (re.findall(r'\+CSQ: (\d+)', gw) or ['?'])[0]
            prof['smsReady'] = True
            port = (re.findall(r'@@port (\S+)', out) or ['?'])[0]
            prof['smsInfo'] = f'{port} · SIM готова · сигнал {sig}/31'
            self._ssh(cfg, portal.login_script(prof), timeout=60)
            return {'ok': True, 'message': f"Роутер с SIM готов: {prof['smsInfo']}. Отправьте тестовую СМС, чтобы проверить весь путь.", 'deviceUpdate': {'portal': prof}}
        if op == 'sms_test':
            old = params.get('_old') or status(cfg)['profile'] or {}
            if not old.get('smsReady'):
                raise DriverError('сначала подготовьте роутер с SIM')
            try:
                num = portal.phone(params.get('phone'))
            except ValueError as e:
                raise DriverError(str(e))
            out = self._ssh(cfg, portal.sms_send_script(old, num, 'Rack Live: проверка СМС — портал отправляет коды правильно'), timeout=90)
            if '@@sent' not in out:
                raise DriverError('СМС не ушла: ' + ((fail(out).group(1).strip() if fail(out) else out.strip()) or 'нет ответа от роутера с SIM')[:200])
            return {'ok': True, 'message': f'Тестовая СМС отправлена на {num}'}
        if op == 'template':
            old = params.get('_old') or status(cfg)['profile'] or {}
            if not old:
                raise DriverError('сначала настройте роутер')
            prof = dict(old, template=str(params.get('template') or 'default'))
            out = self._ssh(cfg, portal.template_script(params['_files'], prof), timeout=120)
            if fail(out) or '@@tpl ok' not in out:
                raise DriverError(fail(out).group(1).strip() if fail(out) else 'шаблон не записался')
            return {'ok': True, 'message': 'Шаблон страницы входа заменён — гости увидят его при следующем заходе', 'deviceUpdate': {'portal': prof}}
        if op == 'remove':
            prog('Возвращаю роутеру исходные настройки…')
            out = self._ssh(cfg, portal.REMOVE, timeout=60)
            if fail(out):
                raise DriverError(fail(out).group(1).strip())
            old_lan = (re.search(r'@@oldlan (\S+)', out) or [None, ''])[1].split('/')[0]
            prog('Роутер перезапускает сеть…')
            time.sleep(25)
            for host in dict.fromkeys(x for x in (old_lan, self._hostname(cfg)) if x):
                for _ in range(8):
                    try:
                        self._ssh(dict(cfg, host=host), 'echo ok', timeout=10)
                        return {'ok': True, 'message': f'Портал удалён полностью: OpenNDS, тема и шаблон стёрты, сеть, Wi-Fi, DHCP и межсетевой экран — как до установки. Адрес роутера: {host}.',
                                'deviceUpdate': {'host': host, 'portal': None}}
                    except DriverError:
                        time.sleep(5)
            return {'ok': True, 'message': f"Портал удалён, настройки роутера — как до установки. Rack Live пока не видит роутер: он вернулся на прежний адрес {old_lan or '—'} в своей сети (LAN). Подключитесь к его LAN-порту или Wi-Fi и поправьте адрес устройства в Rack Live.",
                    'deviceUpdate': {'host': old_lan or self._hostname(cfg), 'portal': None}}
        raise DriverError('неизвестное действие')

    def plugin(self, cfg, pid, op, params):
        clean = lambda s: re.sub(r'\x1b\[[0-9;]*m', '', s)
        to_log = lambda body: [{'cmd': l[:200], 'ok': '@@fail' not in l and not re.search(r'\berror\b|failed|ошибка', l, re.I), 'msg': ''}
                               for l in clean(body).splitlines() if l.strip() and not l.startswith('@@')][-60:]
        if pid in plugins.OWRT_INSTALLERS:
            inst, meta = plugins.OWRT_INSTALLERS[pid], next(p for p in plugins.CATALOG if p['id'] == pid)
            st = self._state(cfg)
            if op == 'install':
                if inst['conflict'] and inst['conflict'] in st['pkgs']:
                    raise DriverError(f"сначала удалите {inst['conflict'].capitalize()} — два менеджера маршрутизации конфликтуют")
                min_rel = inst.get('minRel', 24)
                if int((re.findall(r'\d+', st['rel']) or ['0'])[0]) < min_rel:
                    raise DriverError(f"{meta['title']} нужен OpenWrt {min_rel}.{'05' if min_rel == 23 else '10'} или новее (у вас {st['rel']})")
                free_mb = (st['free'] or 0) // 1024
                if pid not in st['pkgs'] and free_mb < inst['freeMB']:
                    raise DriverError(f"мало места на флеше: {free_mb} МБ, нужно от {inst['freeMB']} МБ")
                env = f"RL_EXT={1 if params.get('extended', True) else 0}\nRL_CORE={1 if params.get('core') else 0}\n"
                out = self._ssh(cfg, env + inst['install'] + plugins.OWRT_STATUS, timeout=1200)
            elif op == 'remove':
                out = self._ssh(cfg, inst['remove'] + '\n' + plugins.OWRT_STATUS, timeout=300)
            else:
                raise DriverError('неизвестное действие')
            body, after = out.split('@@rel', 1)[0], plugins.parse_owrt(out)
            if '@@fail' in body:
                raise DriverError(clean(body).split('@@fail', 1)[1].splitlines()[0].strip())
            main, log = inst['packages'][0], to_log(body)
            if op == 'remove':
                if main in after['pkgs']:
                    raise DriverError(f"{meta['title']} не удалился — см. журнал")
                return {'ok': True, 'log': log, 'message': f"{meta['title']} удалён (sing-box и настройки оставлены)"}
            if main not in after['pkgs']:
                return {'ok': False, 'log': log, 'error': f"{meta['title']} не установился — посмотрите журнал ниже", 'message': f"{meta['title']} не установился"}
            url = f"http://{self._hostname(cfg)}/cgi-bin/luci/{inst['luci']}"
            sb = f" · {after['sb'].replace('sing-box version ', 'sing-box ')}" if after['sb'] else ''
            return {'ok': True, 'log': log, 'version': after['pkgs'][main], 'url': url,
                    'message': f"{meta['title']} {after['pkgs'][main]} установлен{sb}. Настройка: LuCI → Службы → {meta['title']} ({url})"}
        if pid == 'modem':
            prof = next((m for m in plugins.MODEM_PROFILES if m['id'] == params.get('profile')), None)
            if not prof or op not in ('install', 'remove'):
                raise DriverError('неизвестный вариант модема')
            st = self._state(cfg)
            others = [m for m in plugins.MODEM_PROFILES if m['id'] != prof['id'] and m['key'] in st['pkgs']]
            if op == 'install':
                clash = [m['title'] for m in others if m['id'] in prof.get('conflicts', [])]
                if clash:
                    raise DriverError(f"сначала удалите вариант «{clash[0]}» — они мешают друг другу")
                script = plugins.OWRT_PKG + 'pupd >/dev/null 2>&1\npadd ' + ' '.join(prof['packages']) + ' 2>&1 | tail -15\n'
            else:                                       # keep packages that another installed variant still needs
                keep = {x for m in others for x in m['packages']}
                script = plugins.OWRT_PKG + 'pdel ' + ' '.join(x for x in prof['packages'] if x not in keep) + ' 2>&1 | tail -15\n'
            out = self._ssh(cfg, script + plugins.OWRT_STATUS, timeout=600)
            after = plugins.parse_owrt(out)
            log = to_log(out.split('@@rel', 1)[0])
            ok = (prof['key'] in after['pkgs']) == (op == 'install')
            if not ok:
                return {'ok': False, 'log': log, 'error': 'не получилось — посмотрите журнал ниже', 'message': f"«{prof['title']}»: не получилось"}
            if op == 'remove':
                return {'ok': True, 'log': log, 'message': f"Вариант «{prof['title']}» удалён — можно поставить другой"}
            return {'ok': True, 'log': log, 'message': f"Установлено: {prof['title']}. Дальше: {prof['after']} Если модем не заработал — "
                                                         'удалите этот вариант и попробуйте другой (иногда нужно переподключить модем).'}
        if pid == 'portal':
            return self._portal(cfg, op, params)
        if pid == 'remote':
            prog = params.get('_progress') or (lambda s: None)
            if op == 'status':
                return dict(self._remote_card(remote.parse(self._ssh(cfg, remote.STATUS, 30))), ok=True)
            if op == 'install':
                return remote.connect(params['_app'], cfg, self, params, prog)
            if op == 'remove':
                return remote.disconnect(params['_app'], cfg, self, params, prog)
            raise DriverError('неизвестное действие')
        if pid == 'meshnode':
            if op == 'suggest_ip':
                out = self._ssh(cfg, plugins.MESHNODE_FREEIP, 40)
                ip = (re.search(r'@@freeip (\S+)', out) or [None, ''])[1]
                gw = (re.search(r'@@gw (\S+)', out) or [None, ''])[1]
                return {'ip': ip, 'gw': gw}
            if op == 'install':
                ms = plugins.parse_meshnode(self._ssh(cfg, plugins.MESHNODE_STATUS, 30))
                if ms['wifi'] < 1:
                    raise DriverError('на этом роутере нет Wi-Fi (mac80211) — он не может быть точкой доступа')
                free_mb = (ms['free'] or 0) // 1024
                if not ms['py'] and free_mb < 10:
                    raise DriverError(f"мало места на флеше: {free_mb} МБ — не хватит для Python (нужно ~10 МБ)")
                dumb = (params.get('dumbIp') or '').strip()
                gw = (params.get('gw') or '').strip()
                if dumb and not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', dumb):
                    raise DriverError('неверный адрес для режима точки доступа')
                prog = params.get('_progress') or (lambda s: None)
                prog('Ставлю пакеты и службу на роутер… (1–3 минуты)')
                out = self._ssh(cfg, plugins.meshnode_install_script(dumb, gw) + plugins.MESHNODE_STATUS, timeout=900)
                body = out.split('@@rel', 1)[0]
                if '@@fail' in body:
                    raise DriverError(clean(body).split('@@fail', 1)[1].splitlines()[0].strip())
                after = plugins.parse_meshnode(out)
                log = to_log(body)
                if not (after['svc'] and after['run']):
                    return {'ok': False, 'log': log, 'error': 'служба не запустилась — посмотрите журнал ниже', 'message': 'Узел не запустился'}
                return {'ok': True, 'log': log,
                        'message': 'Готово: роутер стал точкой Keenetic и запущен. Теперь откройте приложение Keenetic '
                                   '(или веб-интерфейс) → раздел Wi-Fi-системы и примите новую точку — как при обычном добавлении в Mesh. '
                                   'После приёмки он сам получит настройки Wi-Fi контроллера.'}
            if op == 'remove':
                out = self._ssh(cfg, plugins.meshnode_remove_script() + plugins.MESHNODE_STATUS, timeout=300)
                after = plugins.parse_meshnode(out)
                log = to_log(out.split('@@rel', 1)[0])
                if after['svc']:
                    return {'ok': False, 'log': log, 'error': 'служба осталась — см. журнал', 'message': 'Не удалось убрать'}
                return {'ok': True, 'log': log,
                        'message': 'Готово: наша служба Mesh убрана, роутеру возвращён его собственный Wi-Fi. '
                                   'Адрес, root-пароль и остальные настройки роутера сохранены — он остаётся на связи. '
                                   'В приложении Keenetic эту точку (станет офлайн) удалите вручную.'}
            if op == 'factory':
                delay = 20
                out = self._ssh(cfg, plugins.meshnode_reset_script(delay), timeout=30)
                if '@@fail' in out:
                    raise DriverError(clean(out).split('@@fail', 1)[1].splitlines()[0].strip())
                if '@@scheduled' not in out:
                    raise DriverError('не удалось запустить сброс роутера')
                return {'ok': True, 'reset': True, 'delay': delay,
                        'message': f'Полный сброс запущен. Через {delay} с роутер сотрёт ВСЕ настройки и перезагрузится в чистый OpenWrt '
                                   '(адрес станет 192.168.1.1). Когда отсчёт закончится — выньте кабель из коммутатора, '
                                   'чтобы он не поднялся на 192.168.1.1 в вашей сети.'}
            raise DriverError('неизвестное действие')
        raise DriverError('неизвестный плагин')


_TR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя', ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u',
                                                   'f', 'h', 'ts', 'ch', 'sh', 'sch', '', 'y', '', 'e', 'yu', 'ya']))


def _translit(s):
    """a DNS-valid host name for dnsmasq from «Айфон Миши» → aifon-mishi (the original goes to rl_label)"""
    return ''.join(_TR.get(c, _TR.get(c.lower(), c)) for c in s)
