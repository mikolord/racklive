"""Keenetic / Netcraze routers via the RCI HTTP API (KeeneticOS 3.x–5.x)."""
import codecs, hashlib, http.cookiejar, ipaddress, json, re, secrets, ssl, time, urllib.error, urllib.request

from . import Driver, FIELD_HOST, FIELD_PASS, FIELD_USER
from .. import plugins
from ..util import DriverError, uptime_seconds, guess_kind


BAD_LOGIN = {}              # sha256(address, login, password) → time of the last rejected login


class Keenetic(Driver):
    id = 'keenetic'
    title = 'Keenetic / Netcraze'
    kind = 'router'
    description = 'Роутер: порты, VLAN, клиенты по сегментам, mesh-точки и их Wi-Fi-клиенты.'
    fields = [dict(FIELD_HOST, hint='Локально — IP (192.168.1.1). Удалённо через домен — только прямой доступ: '
                   'https://дом.рф:ПОРТ (проброшенный порт роутера). Облачный KeenDNS не подойдёт.'),
              dict(FIELD_USER, default='admin'), FIELD_PASS]
    actions = [{'id': 'reboot', 'label': 'Перезагрузить роутер', 'scope': 'device', 'confirm': 'Интернет пропадёт на 2–3 минуты. Перезагрузить?'},
               {'id': 'reboot_child', 'label': 'Перезагрузить точку', 'scope': 'child', 'confirm': 'Wi-Fi этой точки пропадёт на пару минут. Перезагрузить?'},
               {'id': 'sec_fix', 'label': 'Исправить', 'scope': 'security'}]

    def _session(self, cfg, host=None):
        jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()                 # remote routers often have a self-signed / KeenDNS cert
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=ctx))
        h = (host or cfg['host']).strip().rstrip('/')
        base = h if '://' in h else 'http://' + h          # allow "https://dom.ru:8080" for remote access

        def req(path, data=None):
            r = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                       headers={'Content-Type': 'application/json'})
            try:
                return op.open(r, timeout=25)
            except urllib.error.HTTPError as e:
                return e

        r = req('/auth')
        realm, ch = r.headers.get('X-NDM-Realm'), r.headers.get('X-NDM-Challenge')
        if not realm:
            if base.startswith('http://'):                 # KeenDNS / proxy usually answers only over HTTPS
                raise DriverError('RCI не отвечает по http. Если это удалённый роутер через домен — укажите адрес с https:// '
                                  'и портом проброса, например https://дом.рф:8080')
            raise DriverError('это не Keenetic, либо доступ к роутеру идёт через облако KeenDNS (оно пускает только браузер). '
                              'Нужен прямой доступ: проброшенный порт на роутере или KeenDNS в режиме «прямой доступ».')
        user = cfg.get('username') or 'admin'
        # after a wrong password wait 30 min (or until the password is changed): polling every minute would get our IP locked out
        bad_key = hashlib.sha256(f"{base}\0{user}\0{cfg.get('password', '')}".encode()).hexdigest()
        if time.time() - BAD_LOGIN.get(bad_key, 0) < 1800:
            raise DriverError('неверный логин или пароль — следующая попытка через ' +
                              f"{int((1800 - (time.time() - BAD_LOGIN[bad_key])) / 60) + 1} мин (или сразу после смены пароля), чтобы роутер не заблокировал адрес")
        md5 = hashlib.md5(f"{user}:{realm}:{cfg.get('password', '')}".encode()).hexdigest()
        a = req('/auth', {'login': user, 'password': hashlib.sha256((ch + md5).encode()).hexdigest()})
        if getattr(a, 'status', getattr(a, 'code', 0)) != 200:
            BAD_LOGIN[bad_key] = time.time()
            raise DriverError('неверный логин или пароль')
        BAD_LOGIN.pop(bad_key, None)
        get = lambda p: json.loads(req(p).read() or b'{}')
        cli = lambda cmds: json.loads(req('/rci/', [{'parse': c} for c in cmds]).read())
        return get, cli

    _VPN_KIND = {'Wireguard': 'wireguard', 'OpenVPN': 'openvpn', 'L2TP': 'l2tp', 'PPTP': 'pptp',
                 'SSTP': 'sstp', 'IPsecVpn': 'ipsec', 'IPsec': 'ipsec', 'IKE': 'ipsec'}

    def _vpn(self, get, rc):
        """VPN tunnels from the interface list; WireGuard allow-ips come from running-config."""
        allow = {}                                          # peer public-key -> subnet (ip/mask)
        cur = None
        for l in rc:
            m = re.match(r'\s*wireguard peer (\S+)', l)
            if m:
                cur = m.group(1)
            a = re.match(r'\s*allow-ips (\S+) (\S+)', l)
            if a and cur:
                pref = sum(bin(int(o)).count('1') for o in a.group(2).split('.'))
                allow[cur] = a.group(1) if pref == 32 else f'{a.group(1)}/{pref}'
        try:
            ifs = get('/rci/show/interface')
        except Exception:
            return []
        now = time.time()
        hs = lambda v: None if not v or v >= 2147483647 else int(now - v)
        out = []
        for name, v in (ifs.items() if isinstance(ifs, dict) else []):
            kind = self._VPN_KIND.get(v.get('type'))
            if not kind:
                continue
            up = v.get('connected') == 'yes' or v.get('state') == 'up'
            t = {'id': name, 'name': v.get('description') or name, 'kind': kind, 'up': up, 'address': v.get('address'),
                 'routing': False, 'peers': [], 'endpoint': None, 'rx': None, 'tx': None, 'handshake': None, 'role': 'client'}
            wg = v.get('wireguard') or {}
            peers = wg.get('peer') or []
            t['listenPort'] = wg.get('listen-port')
            server = 'server-owned' in wg or (kind == 'wireguard' and not v.get('global') and len(peers) > 1)
            t['routing'] = not server and (bool(v.get('global')) or bool(v.get('defaultgw')))
            if kind == 'wireguard' and server:
                t['role'] = 'server'
                for p in peers:
                    ep = p.get('remote-endpoint-address')
                    t['peers'].append({'name': p.get('description') or (p.get('public-key') or '')[:8], 'online': p.get('online'),
                                       'endpoint': f"{ep}:{p.get('remote-port')}" if ep and ep != '0.0.0.0' else None,
                                       'subnet': allow.get(p.get('public-key')), 'handshake': hs(p.get('last-handshake')),
                                       'rx': p.get('rxbytes'), 'tx': p.get('txbytes')})
                t['rx'] = sum(p.get('rxbytes') or 0 for p in peers)
                t['tx'] = sum(p.get('txbytes') or 0 for p in peers)
            elif peers:                                     # client tunnel = one peer (the server we dial)
                p = peers[0]
                ep = p.get('remote-endpoint-address')
                t.update(endpoint=f"{ep}:{p.get('remote-port')}" if ep and ep != '0.0.0.0' else None,
                         rx=p.get('rxbytes'), tx=p.get('txbytes'), handshake=hs(p.get('last-handshake')),
                         up=up and bool(p.get('online')))
            out.append(t)
        out.sort(key=lambda t: (t['role'] != 'server', not t['up'], t['name']))
        return out

    def poll(self, cfg):
        get, cli = self._session(cfg)
        rc = cli(['show running-config'])[0]['parse']['message']
        pcfg, cur, cur_b, segs, seg_vlan = {}, None, None, {}, {}
        seg_net, seg_name, statics, policies, cur_pol = {}, {}, {}, {}, None
        for l in rc:
            m = re.match(r'ip dhcp host ([0-9a-f:]{17}) (\d+\.\d+\.\d+\.\d+)$', l)
            if m:
                statics[m.group(1)] = m.group(2)
            if not l.startswith(' '):
                mp = re.match(r'ip policy (\S+)$', l)
                cur_pol = mp.group(1) if mp else None
                if cur_pol:
                    policies[cur_pol] = cur_pol
                m = re.match(r'interface (X?GigabitEthernet\d/\d+)$', l)
                cur = m.group(1) if m else None
                mb = re.match(r'interface (Bridge\d+)$', l)
                cur_b = mb.group(1) if mb else None
                if cur:
                    pcfg[cur] = {'desc': '', 'mode': 'access', 'access': None, 'trunk': []}
                continue
            s = l.strip()
            if cur:
                if s.startswith('description'):
                    pcfg[cur]['desc'] = s.split(' ', 1)[1].strip('"')
                elif s == 'switchport mode trunk':
                    pcfg[cur]['mode'] = 'trunk'
                elif s.startswith('switchport access vlan'):
                    pcfg[cur]['access'] = int(s.split()[-1])
                elif s.startswith('switchport trunk vlan'):
                    pcfg[cur]['trunk'].append(int(s.split()[-1]))
            elif cur_pol and s.startswith('description'):
                d = s.split(' ', 1)[1].strip('"')
                policies[cur_pol] = codecs.escape_decode(d.encode())[0].decode('utf-8', 'ignore') if '\\x' in d else d
            elif cur_b:
                ma = re.match(r'ip address (\d+\.\d+\.\d+\.\d+) (\d+\.\d+\.\d+\.\d+)$', s)
                if ma:
                    seg_net[cur_b] = (ma.group(1), ma.group(2))
                if s.startswith('rename '):
                    seg_name[cur_b] = s.split(' ', 1)[1].strip('"')
                if s.startswith('description'):
                    d = s.split(' ', 1)[1].strip('"')
                    segs[cur_b] = codecs.escape_decode(d.encode())[0].decode('utf-8', 'ignore') if '\\x' in d else d
                m = re.match(r'include GigabitEthernet\d/Vlan(\d+)', s)
                if m:
                    seg_vlan[cur_b] = int(m.group(1))

        ports = []
        for gi in ('GigabitEthernet0', 'GigabitEthernet1'):
            try:
                lan = get('/rci/show/interface/' + gi).get('port', {})
            except Exception:
                lan = {}
            if not isinstance(lan, dict) or 'id' in lan:      # single-port interfaces (WAN / internal) are handled below
                continue
            for label, p in sorted(lan.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 99):
                c = pcfg.get(p.get('id'), {})
                up = p.get('link') == 'up'
                ports.append({'n': int(label) if str(label).isdigit() else label, 'name': p.get('id'), 'kind': 'rj45', 'link': up,
                              'speed': int(p.get('speed') or 0) if up else 0, 'poeW': 0,
                              'vlansU': [c['access']] if c.get('access') else [1],
                              'vlansT': c.get('trunk', []) if c.get('mode') == 'trunk' else [],
                              'label': c.get('desc', ''), 'peers': []})
        wan_ip = None
        for wi in ('XGigabitEthernet0', 'GigabitEthernet1'):
            try:
                w = get('/rci/show/interface/' + wi)
            except Exception:
                continue
            wp = w.get('port') if isinstance(w.get('port'), dict) else None
            if wp and 'id' in wp:
                up = wp.get('link') == 'up'
                wan_ip = w.get('address')
                ports.append({'n': int(wp.get('label') or len(ports) + 1), 'name': wp.get('id'), 'kind': 'wan', 'link': up,
                              'speed': int(wp.get('speed') or 0) if up else 0, 'poeW': 0, 'vlansU': [], 'vlansT': [],
                              'label': 'WAN ' + (w.get('description') or ''), 'peers': [], 'ip': wan_ip})
                break

        mws = get('/rci/show/mws/member')
        children = []
        for m in (mws if isinstance(mws, list) else []):
            children.append({'key': m.get('cid'), 'name': m.get('known-host') or m.get('model'), 'kind': 'ap', 'model': m.get('model'),
                             'ip': m.get('ip'), 'mac': m.get('mac'), 'status': 'online' if m.get('cloud-agent-state') or m.get('ip') else 'offline',
                             'clients': m.get('associations', 0), 'uptime': uptime_seconds((m.get('system') or {}).get('uptime')),
                             'uplink': (m.get('backhaul') or {}).get('speed'), 'fw': m.get('fw'),
                             # how the point reaches the router: a cable (Ethernet backhaul) or over the air
                             'backhaul': ('wire' if re.match(r'(Gigabit|Fast)?Ethernet', str((m.get('backhaul') or {}).get('uplink') or ''))
                                          else 'wifi' if (m.get('backhaul') or {}).get('uplink') else None),
                             'fwUpdate': bool(m.get('fw-update-available')) and m.get('fw-available') != m.get('fw')})

        clients = []
        for h in get('/rci/show/ip/hotspot').get('host', []):
            if not h.get('active'):
                continue
            iface = h.get('interface') or {}
            seg = iface.get('description') or iface.get('id') if isinstance(iface, dict) else iface
            mws_i = h.get('mws') or {}
            ap = mws_i.get('cid') or ('self' if h.get('ap') or h.get('ssid') else None)
            ts = h.get('traffic-shape') or {}
            clients.append({'mac': h.get('mac'), 'ip': h.get('ip'), 'name': h.get('name') or h.get('hostname') or '', 'hostname': h.get('hostname') or '',
                            'segment': seg, 'segId': iface.get('id') if isinstance(iface, dict) else None, 'registered': bool(h.get('registered')),
                            'access': h.get('access') or 'permit', 'policy': h.get('policy') or '', 'staticIp': statics.get((h.get('mac') or '').lower()),
                            'limit': round(max(ts.get('rx') or 0, ts.get('tx') or 0) / 1000) or 0, 'connected': h.get('uptime'),
                            'firstSeen': h.get('first-seen'),          # seconds since the router first saw this MAC
                            'ap': ap, 'rssi': mws_i.get('rssi') or h.get('rssi'), 'rate': mws_i.get('txrate') or h.get('txrate'),
                            'band': '5 ГГц' if 'WifiMaster1' in (mws_i.get('ap') or h.get('ap') or '') else ('2.4 ГГц' if ap else ''),
                            'port': h.get('port'), 'online': True, 'kind': guess_kind(h.get('name') or h.get('hostname')),
                            'rx': h.get('rxbytes'), 'tx': h.get('txbytes')})

        ver, sysi = get('/rci/show/version'), get('/rci/show/system')
        mem = (sysi.get('memory') or '0/1').split('/')
        lanmac = (get('/rci/show/interface/Bridge0') or {}).get('mac')
        by_seg = {}
        for c in clients:
            by_seg[c['segment'] or '—'] = by_seg.get(c['segment'] or '—', 0) + 1
        try:
            nd = get('/rci/show/ndns')
            ddns = f"{nd.get('name')}.{nd.get('domain')}" if nd.get('name') else ''
        except Exception:
            ddns = ''
        sections = [{'title': 'Сегменты', 'rows': [[k, f'{v} устр.'] for k, v in sorted(by_seg.items(), key=lambda kv: -kv[1])]},
                    {'title': 'Интернет', 'rows': [['WAN IP', wan_ip or '—'], ['KeenDNS', ddns or '—']]}]
        sec = self._security(rc, cli, cfg)
        return {'status': 'online', 'security': sec,
                'summary': {'model': ver.get('model'), 'fw': ver.get('title'), 'uptime': uptime_seconds(sysi.get('uptime')),
                            'cpu': sysi.get('cpuload'), 'mem': round(int(mem[0]) * 100 / max(1, int(mem[1]))),
                            'ip': cfg['host'], 'mac': lanmac},
                'ports': ports, 'clients': clients, 'children': children, 'sections': sections, 'vpn': self._vpn(get, rc),
                # the router's networks (for «which network is which») and its connection policies (for a client's «policy»)
                'networks': [{'id': b, 'name': segs.get(b) or seg_name.get(b) or b, 'alias': seg_name.get(b, ''), 'vlan': seg_vlan.get(b),
                              'ip': seg_net[b][0], 'mask': seg_net[b][1]} for b in sorted(seg_net, key=lambda x: int(x[6:] or 0))],
                'policies': [{'id': k, 'name': v} for k, v in policies.items()]}

    # ───────── one client: name (registration), static IP, speed limit, policy / block — all on the router ─────────
    def client(self, cfg, mac, want):
        """want: {name, ip ('' = no static), limit (Mbit/s, 0 = none), policy ('' default | PolicyN | 'deny'), forget: bool}
        → list of what was done. Syntax checked on a real Keenetic 5.1 (known host / ip dhcp host / ip traffic-shape host / ip hotspot host)."""
        mac = str(mac or '').lower()
        if not re.match(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$', mac):
            raise DriverError('неверный MAC-адрес')
        get, cli = self._session(cfg)
        host = next((h for h in get('/rci/show/ip/hotspot').get('host', []) if (h.get('mac') or '').lower() == mac), {}) or {}
        cmds, done = [], []
        if want.get('forget'):
            cmds += [f'no ip traffic-shape host {mac}', f'no ip hotspot host {mac} policy', f'ip hotspot host {mac} permit',
                     f'no ip dhcp host {mac}', f'no known host {mac}']
            done.append('регистрация снята, настройки клиента удалены')
        else:
            if 'name' in want:
                name = re.sub(r'["\\\n\r]', '', str(want.get('name') or '')).strip()[:64]
                if not name:
                    raise DriverError('укажите имя устройства')
                cmds.append(f'known host "{name}" {mac}')
                done.append(f'имя «{name}»' + ('' if host.get('registered') else ', устройство зарегистрировано'))
            registered = host.get('registered') or 'name' in want
            if 'ip' in want:
                ip = str(want.get('ip') or '').strip()
                if ip:
                    if not re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                        raise DriverError('неверный IP-адрес')
                    # only an address of the client's own network: not another subnet, not the router, not .0 / .255
                    seg = (host.get('interface') or {}).get('id') if isinstance(host.get('interface'), dict) else None
                    bi = get('/rci/show/interface/' + seg) if seg else {}
                    if bi.get('address') and bi.get('mask'):
                        import ipaddress
                        net = ipaddress.ip_network(f"{bi['address']}/{bi['mask']}", strict=False)
                        a = ipaddress.ip_address(ip)
                        if a not in net:
                            raise DriverError(f'адрес {ip} не из сети этого устройства ({net}) — укажите адрес вида {str(net.network_address)[:-1]}…')
                        if a in (net.network_address, net.broadcast_address) or ip == bi['address']:
                            raise DriverError(f'{ip} — служебный адрес сети или адрес роутера, выберите другой')
                    busy = next((h for h in get('/rci/show/ip/hotspot').get('host', []) if h.get('ip') == ip and (h.get('mac') or '').lower() != mac), None)
                    if busy:
                        raise DriverError(f'адрес {ip} уже занят ({busy.get("name") or busy.get("mac")})')
                    cmds.append(f'ip dhcp host {mac} {ip}')
                    done.append(f'постоянный адрес {ip}')
                else:
                    cmds.append(f'no ip dhcp host {mac}')
                    done.append('постоянный адрес снят')
            if 'limit' in want:
                mbit = float(want.get('limit') or 0)
                if mbit > 0:
                    if not registered:
                        raise DriverError('ограничить скорость можно только зарегистрированному устройству — задайте ему имя')
                    cmds.append(f'ip traffic-shape host {mac} rate {int(mbit * 1024)}')
                    done.append(f'скорость до {mbit:g} Мбит/с')
                else:
                    cmds.append(f'no ip traffic-shape host {mac}')
                    done.append('без ограничения скорости')
            if 'policy' in want:
                pol = str(want.get('policy') or '')
                if pol == 'deny':
                    cmds += [f'ip hotspot host {mac} deny']
                    done.append('доступ в интернет запрещён')
                elif pol:
                    if not re.match(r'^[\w-]{1,32}$', pol):
                        raise DriverError('неверная политика')
                    cmds += [f'ip hotspot host {mac} permit', f'ip hotspot host {mac} policy {pol}']
                    done.append(f'политика {pol}')
                else:
                    cmds += [f'ip hotspot host {mac} permit', f'no ip hotspot host {mac} policy']
                    done.append('политика по умолчанию')
        if not cmds:
            return []
        res = cli(cmds + ['system configuration save'])
        for c, r in zip(cmds, res):
            for st in ((r or {}).get('parse') or {}).get('status') or []:
                if st.get('status') == 'error' and 'no rate limit exists' not in str(st.get('message')) and 'not applicable' not in str(st.get('message')):
                    raise DriverError(f'роутер не принял «{c}»: {st.get("message")}')
        return done

    shell = 'CLI Keenetic (как в веб-CLI): show …, interface …, ip …; несколько команд — каждая с новой строки; сохранить: system configuration save'

    def command(self, cfg, cmd):
        """Frank with full access (gated in rackd/assistant.py): CLI lines through RCI parse → readable text"""
        _, cli = self._session(cfg)
        cmds = [c.strip() for c in cmd.split('\n') if c.strip()]
        out = []
        for c, r in zip(cmds, cli(cmds)):
            p = (r or {}).get('parse', r)
            msgs = []
            if isinstance(p, dict):
                for st in p.get('status') or []:
                    msgs.append(f"{st.get('status')}: {st.get('message')}")
                if isinstance(p.get('message'), list):
                    msgs.append('\n'.join(p['message']))
                rest = {k: v for k, v in p.items() if k not in ('status', 'message', 'prompt')}
                if rest:
                    msgs.append(json.dumps(rest, ensure_ascii=False, indent=1))
            else:
                msgs.append(str(p))
            out.append(f'> {c}\n' + ('\n'.join(msgs) or 'ok'))
        return '\n\n'.join(out)

    def backup(self, cfg):
        """running-config as text — what rackd/backups.py versions."""
        _, cli = self._session(cfg)
        return '\n'.join(self._rc(cli)) + '\n'

    # ───────── internet speed through a channel (rackd/inet.py) ─────────
    def inet_test(self, cfg, iface):
        """iface: 'isp' (the default route) or 'WireguardN' — curl in Entware bound to the tunnel (WireguardN = nwgN in Linux)."""
        from .. import inet
        if not cfg.get('entwarePassword'):
            raise DriverError('для замера по каналам нужен доступ к Entware (плагин «Entware» → SSH)')
        m = re.match(r'Wireguard(\d+)$', iface or '')
        if iface not in ('isp', None) and not m:
            raise DriverError(f'канал {iface}: поддерживаются только WireGuard/AmneziaWG')
        iface_k = f'nwg{m.group(1)}' if m else ''
        return inet.parse_curl(self._ssh(cfg, f'IFACE="{iface_k}"\nBIN=/opt/bin\n' + inet.CURL_TEST, 180))

    # ───────── security facts for the advisor (rackd/security.py) ─────────
    _updates = {}                                           # host -> (checked_at, info); the update check goes online, so 6 h cache

    def _security(self, rc, cli, cfg):
        forwards, remote, cur = [], {}, None
        for l in rc:
            m = re.match(r'ip static (tcp|udp|tcpudp) (\S+) (\d+(?:-\d+)?) (\S+)(?: (\d+(?:-\d+)?))?(?: !(.*))?$', l)
            if m:
                forwards.append({'proto': m.group(1), 'iface': m.group(2), 'port': m.group(3), 'target': m.group(4),
                                 'toPort': m.group(5) or m.group(3), 'name': (m.group(6) or '').strip(),
                                 'rule': l.split(' !', 1)[0][len('ip static '):]})
                continue
            if not l.startswith(' '):
                cur = {'ip http': 'http', 'ip telnet': 'telnet', 'ip ssh': 'ssh'}.get(l.strip())
                m = re.match(r'ip http (port|ssl port) (\d+)', l)
                if m:
                    remote.setdefault('http', {})['sslPort' if 'ssl' in m.group(1) else 'port'] = int(m.group(2))
                if l.startswith('ip http security-level '):
                    remote.setdefault('http', {})['level'] = l.split()[-1]
                if cur:
                    remote.setdefault(cur, {})
                continue
            s = l.strip()
            if cur and s.startswith('security-level '):
                remote[cur]['level'] = s.split()[-1]
            elif cur and s.startswith('port '):
                remote[cur]['port'] = int(s.split()[-1])
        services = {l.split()[1] for l in rc if l.startswith('service ')}
        for k in ('telnet', 'ssh', 'http'):
            if k in remote:
                remote[k]['on'] = k in services
        host = cfg['host']
        t, upd = self._updates.get(host, (0, None))
        if time.time() - t > 6 * 3600:
            try:
                r = cli(['components check-update'])[0]['parse']
                upd = {'available': bool(r.get('update-available')), 'title': r.get('title'), 'channel': r.get('sandbox')}
            except Exception:
                upd = None
            self._updates[host] = (time.time(), upd)
        return {'forwards': forwards, 'remote': remote, 'upnp': 'upnp' in services, 'update': upd}

    def _sec_fix(self, cfg, params):
        """Safe one-click fixes: remove a port forward, close telnet/SSH of the router to the internet."""
        get, cli = self._session(cfg)
        log, kind = [], params.get('kind')
        if kind == 'forward':
            rule = str(params.get('rule') or '')
            rc = self._rc(cli)
            if not any(l.split(' !', 1)[0] == 'ip static ' + rule for l in rc):
                raise DriverError('такого проброса уже нет')
            self._run(cli, ['no ip static ' + rule, 'system configuration save'], log)
            return f"Проброс {params.get('label') or rule} закрыт"
        if kind == 'remote' and params.get('service') in ('telnet', 'ssh'):
            self._run(cli, [f"ip {params['service']} security-level private", 'system configuration save'], log)
            return f"{'Telnet' if params['service'] == 'telnet' else 'SSH'} роутера теперь доступен только из домашней сети"
        raise DriverError('это нельзя исправить автоматически')

    # ───────── domain name for Rack Live itself (KeenDNS reverse proxy: https with the router's certificate) ─────────
    def keendns(self, cfg, op, params):
        """op 'status' → what exists; 'create' {ip, port, public, name} → a proxy rule <name>.<keendns>; 'remove' {name}.
        An existing rule that already points to the same host and port is reused instead of making a second one."""
        get, cli = self._session(cfg)
        nd = get('/rci/show/ndns') or {}
        name, dom = nd.get('name') or nd.get('booked'), nd.get('domain')
        prox = get('/rci/ip/http/proxy') or {}
        prox = prox if isinstance(prox, dict) else {}
        ip, port = str(params.get('ip') or ''), str(params.get('port') or '')
        hosts = (get('/rci/show/ip/hotspot') or {}).get('host') or []
        mac = next((h.get('mac') for h in hosts if ip and h.get('ip') == ip), None)

        def target(p):
            u = (p or {}).get('upstream') or {}
            return str(u.get('upstream') or ''), str(u.get('port') or '')
        match = next((n for n, p in prox.items() if target(p)[1] == port and target(p)[0] in {ip, mac} - {''}
                      and ((p or {}).get('domain') or {}).get('ndns')), None)
        url = lambda n: f'https://{n}.{name}.{dom}'
        res = {'ndns': bool(name and dom), 'keendns': f'{name}.{dom}' if name and dom else None, 'access': nd.get('access'), 'proxy': match,
               'url': url(match) if match else None, 'mac': mac,
               'public': bool((((prox.get(match) or {}).get('security-level')) or {}).get('public')) if match else None}
        if op == 'status':
            return res
        if not res['ndns']:
            raise DriverError('на роутере ещё нет доменного имени KeenDNS: веб-интерфейс роутера → «Доменное имя» → получите имя (бесплатно), потом повторите')
        log, lvl = [], 'public' if params.get('public') else 'private'
        if op == 'create':
            if not (mac or ip) or not port:
                raise DriverError('не удалось определить адрес Rack Live в сети')
            n = match
            if n:                                           # already there: only the access level may change
                self._run(cli, [f'ip http proxy {n} security-level {lvl}', 'system configuration save'], log)
            else:
                want = re.sub(r'[^a-z0-9]', '', str(params.get('name') or 'racklive').lower())[:20] or 'racklive'
                n, k = want, 2
                while n in prox:
                    n, k = f'{want}{k}', k + 1
                p = f'ip http proxy {n}'
                try:
                    self._run(cli, [p, f'{p} upstream http {mac or ip} {port}', f'{p} domain ndns', f'{p} ssl redirect',
                                    f'{p} security-level {lvl}'], log)
                except DriverError:
                    cli([f'no {p}'])                        # half-made rule: roll back
                    raise
                self._run(cli, ['system configuration save'], log)
            return dict(res, proxy=n, url=url(n), public=lvl == 'public', created=not match)
        if op == 'remove':
            n = str(params.get('name') or '')
            if n not in prox:
                return dict(res, proxy=None, url=None)
            self._run(cli, [f'no ip http proxy {n}', 'system configuration save'], log)
            return dict(res, proxy=None, url=None)
        raise DriverError('неизвестная операция')

    # ───────── plugins ─────────
    def _rc(self, cli):
        return cli(['show running-config'])[0]['parse']['message']

    @staticmethod
    def _run(cli, cmds, log):
        """Run CLI commands one batch; every result goes to the log, the first error stops with a readable message."""
        hide = lambda c: re.sub(r'(private-key|preshared-key) \S+', r'\1 •••', c)
        out = cli(cmds)
        for c, o in zip(cmds, out):
            st = (o.get('parse') or {}).get('status') or []
            err = next((s for s in st if s.get('status') == 'error'), None)
            log.append({'cmd': hide(c), 'ok': not err, 'msg': '; '.join(s.get('message', '') for s in st)[:200]})
            if err:
                raise DriverError(f"роутер не выполнил «{hide(c)[:80]}»: {err.get('message')}")
        return out

    def plugins(self, cfg):
        get, cli = self._session(cfg)
        v = get('/rci/show/version')
        comps = set(((v.get('ndw') or {}).get('components') or '').split(','))
        rc = self._rc(cli)
        disk = next((l.split(' ', 2)[2] for l in rc if l.startswith('opkg disk ')), None)
        entware = disk is not None and any(l.startswith('opkg initrc') for l in rc)
        wg, cur = [], None
        for l in rc:
            m = re.match(r'interface (Wireguard\d+)$', l)
            if m:
                cur = {'iface': m.group(1), 'name': m.group(1)}
                wg.append(cur)
            elif not l.startswith(' '):
                cur = None
            elif cur and l.strip().startswith('description '):
                d = l.strip()[12:].strip('"')                # the router keeps non-ASCII as \xd0\xbf…
                cur['name'] = codecs.escape_decode(d.encode())[0].decode('utf-8', 'ignore') if '\\x' in d else d
        mine = {t.get('iface'): t for t in cfg.get('rlTunnels') or []}
        groups = {}
        for l in rc:
            m = re.match(r'\s+route object-group (rl_\w+) (Wireguard\d+)', l)
            if m:
                groups.setdefault(m.group(2), []).append(m.group(1))
        tunnels = [dict(t, managed=t['iface'] in mine, groups=len(groups.get(t['iface'], [])),
                        domains=(mine.get(t['iface']) or {}).get('domains', 0)) for t in wg]
        arch = v.get('arch') or ''
        ssh, pkgs = {'set': bool(cfg.get('entwarePassword')), 'port': cfg.get('entwarePort') or 222, 'user': cfg.get('entwareUser') or 'root'}, None
        if ssh['set'] and entware:
            try:
                pkgs = plugins.parse_pkgs(self._ssh(cfg, plugins.PKG_CHECK, 20))
                ssh['ok'] = True
            except DriverError as e:
                ssh['error'] = str(e)
        netf = any('netfilter' in c or 'xtables' in c for c in comps)
        host = self._hostname(cfg)
        out = []
        for p in plugins.for_driver(self.id):
            if p['id'] in plugins.INSTALLERS:
                inst = plugins.INSTALLERS[p['id']]
                p['ssh'], p['url'], p['login'] = ssh, f"http://{host}:{inst['port']}", inst['login']
                if pkgs is not None:
                    p['installed'] = inst['packages'][0] in pkgs
                    p['version'] = pkgs.get(inst['packages'][0])
            if p['id'] == 'entware':
                p['checks'] = [{'label': 'Компонент «Поддержка открытых пакетов» (OPKG)', 'ok': 'opkg' in comps},
                               {'label': 'Компонент «Модули ядра подсистемы Netfilter» (нужен HydraRoute)', 'ok': 'opkg-kmod-netfilter' in comps, 'optional': True},
                               {'label': 'Выбран накопитель для Entware', 'ok': disk is not None, 'hint': disk or ''},
                               {'label': 'Entware установлен', 'ok': entware}]
                p['installed'] = entware
                p['arch'], p['installer'] = arch, next((u for a, u in plugins.ENTWARE_INSTALLER.items() if arch.startswith(a)), '')
            elif p['id'] == 'awg':
                p['checks'] = [{'label': 'Компонент «WireGuard VPN»', 'ok': 'wireguard' in comps}]
                p['installed'] = any(t['managed'] for t in tunnels)
                p['tunnels'] = tunnels
                p['fw'] = v.get('title')
            elif p['id'] == 'hydraroute':
                fw = ([int(x) for x in re.findall(r'\d+', v.get('title') or '0')[:3]] + [0, 0, 0])[:3]
                p['checks'] = [{'label': f"Прошивка новее 4.3.6 (у вас {v.get('title')})", 'ok': fw > [4, 3, 6]},
                               {'label': 'Entware установлен', 'ok': entware},
                               {'label': 'Компонент «Модули ядра Netfilter» / «Xtables-addons»', 'ok': netf},
                               {'label': 'Rack Live может зайти в Entware по SSH', 'ok': bool(ssh.get('ok'))}]
                if pkgs is None:
                    p['installed'] = any(l.startswith('ip policy HydraRoute') for l in rc)
            elif p['id'] == 'awgmanager':
                p['checks'] = [{'label': 'Entware установлен', 'ok': entware},
                               {'label': 'Компонент «WireGuard VPN»', 'ok': 'wireguard' in comps},
                               {'label': 'Rack Live может зайти в Entware по SSH', 'ok': bool(ssh.get('ok'))}]
                if pkgs is None:
                    p['installed'] = None                   # unknown until SSH works
            out.append(p)
        return {'model': v.get('model'), 'fw': v.get('title'), 'arch': arch, 'plugins': out}

    # ── Entware over SSH (installers) ──
    @staticmethod
    def _hostname(cfg):
        return re.sub(r'^\w+://', '', cfg['host'].strip()).split('/')[0].split(':')[0]

    def _ssh_cfg(self, cfg, params=None):
        p = params or {}
        pw = p.get('password') or cfg.get('entwarePassword')
        if not pw:
            raise DriverError('укажите пароль SSH от Entware (пользователь root, порт 222)')
        return {'host': self._hostname(cfg), 'sshPort': p.get('port') or cfg.get('entwarePort') or 222,
                'username': p.get('user') or cfg.get('entwareUser') or 'root', 'password': pw}

    def _ssh(self, cfg, script, timeout=30, params=None):
        from .sshhost import SSHHost
        return SSHHost()._run(self._ssh_cfg(cfg, params), script, timeout=timeout)

    def _installer(self, cfg, pid, op, params, get, cli):
        inst, meta = plugins.INSTALLERS[pid], next(p for p in plugins.CATALOG if p['id'] == pid)
        host = self._hostname(cfg)
        if op == 'ssh':                                     # check and remember the Entware login
            out = self._ssh(cfg, 'echo @@ok; uname -m', 20, params)
            if '@@ok' not in out:
                raise DriverError('Entware ответил не так, как ожидалось')
            s = self._ssh_cfg(cfg, params)
            return {'ok': True, 'message': f"SSH в Entware работает ({out.split('@@ok', 1)[1].strip()})",
                    'sshSave': {'entwarePort': int(s['sshPort']), 'entwareUser': s['username'], 'entwarePassword': s['password']}}
        if op not in ('install', 'remove'):
            raise DriverError('неизвестное действие')
        log = []
        if op == 'install':                                 # prerequisites, the same the card shows
            v = get('/rci/show/version')
            comps = set(((v.get('ndw') or {}).get('components') or '').split(','))
            if 'opkg' not in comps:
                raise DriverError('нет компонента OPKG — сначала установите Entware (плагин «Entware»)')
            if pid == 'hydraroute':
                fw = [int(x) for x in re.findall(r'\d+', v.get('title') or '0')[:3]] + [0, 0, 0]
                if fw[:3] <= [4, 3, 6]:
                    raise DriverError(f"HydraRoute Neo нужна прошивка новее 4.3.6 (у вас {v.get('title')})")
                if not any('netfilter' in c or 'xtables' in c for c in comps):
                    raise DriverError('нет компонента «Модули ядра подсистемы Netfilter» / «Xtables-addons» — добавьте его в «Изменить набор компонентов»')
            if pid == 'awgmanager' and 'wireguard' not in comps:
                raise DriverError('нет компонента «WireGuard VPN» — добавьте его в «Изменить набор компонентов»')
        out = self._ssh(cfg, inst[op] + '\n' + plugins.PKG_CHECK, timeout=900)
        body = out.split('@@pkgs', 1)[0]
        log = [{'cmd': l[:200], 'ok': '@@fail' not in l and not re.search(r'\berror\b|ошибка', l, re.I), 'msg': ''}
               for l in body.splitlines() if l.strip()][-60:]
        if '@@fail' in body:
            raise DriverError(body.split('@@fail', 1)[1].splitlines()[0].strip())
        pkgs = plugins.parse_pkgs(out)
        main = inst['packages'][0]
        url = f"http://{host}:{inst['port']}"
        if op == 'install':
            if main not in pkgs:
                return {'ok': False, 'log': log, 'error': f"{meta['title']} не установился — посмотрите журнал ниже",
                        'message': f"{meta['title']} не установился"}
            return {'ok': True, 'log': log, 'version': pkgs[main], 'url': url,
                    'message': f"{meta['title']} {pkgs[main]} установлен. Панель: {url} — вход: {inst['login']}"}
        if main in pkgs:
            raise DriverError(f"{meta['title']} не удалился: {body.strip().splitlines()[-1] if body.strip() else 'нет ответа'}")
        return {'ok': True, 'log': log, 'message': f"{meta['title']} удалён"}

    def plugin(self, cfg, pid, op, params):
        get, cli = self._session(cfg)
        if pid in plugins.INSTALLERS:
            return self._installer(cfg, pid, op, params, get, cli)
        if pid != 'awg':
            raise DriverError('этот плагин пока в разработке')
        if op == 'preview':
            c = plugins.parse_conf(params.get('conf'))
            doms, skipped = plugins.parse_domains(params.get('domains') or '')
            return {'ok': True, 'preview': plugins.conf_preview(c), 'domains': len(doms), 'skipped': skipped[:20]}
        if op == 'component':
            log = []
            self._run(cli, ['components install wireguard', 'components commit'], log)
            return {'ok': True, 'log': log, 'message': 'Компонент WireGuard устанавливается — роутер скачает его и перезагрузится (2–5 минут)'}
        if op == 'remove':
            iface = str(params.get('iface') or '')
            if iface not in {t.get('iface') for t in cfg.get('rlTunnels') or []}:
                raise DriverError('удалить можно только подключение, созданное Rack Live')
            log = []
            self._unroute(cli, iface, log)
            self._run(cli, [f'no interface {iface}', 'system configuration save'], log)
            return {'ok': True, 'log': log, 'removed': iface, 'message': f'Подключение {iface} удалено'}
        if op == 'domains':
            iface = str(params.get('iface') or '')
            if iface not in {t.get('iface') for t in cfg.get('rlTunnels') or []}:
                raise DriverError('списки сайтов меняются только у подключений, созданных Rack Live')
            doms, skipped = plugins.parse_domains(params.get('domains') or '')
            log = []
            # new lists first (new names), then the old ones go — the router deletes routes asynchronously by rule number,
            # so removing first and re-adding under the same name could lose the new route
            new = self._route(cli, iface, params.get('name') or iface, doms, log) if doms else []
            self._unroute(cli, iface, log, keep=new)
            if new:
                self._ensure_routes(cli, iface, new, log)
            self._run(cli, ['system configuration save'], log)
            return {'ok': True, 'log': log, 'iface': iface, 'domains': len(doms), 'skipped': skipped[:20],
                    'message': f'Через {iface} теперь идут {len(doms)} сайтов и подсетей' if doms else f'Маршрутизация через {iface} выключена'}
        if op != 'install':
            raise DriverError('неизвестное действие')
        c = plugins.parse_conf(params.get('conf'))
        doms, skipped = plugins.parse_domains(params.get('domains') or '') if params.get('routing') else ([], [])
        if params.get('routing') and not doms:
            raise DriverError('включена маршрутизация, но список сайтов пуст — вставьте домены или выключите маршрутизацию')
        rc = self._rc(cli)
        used = {int(m.group(1)) for l in rc for m in [re.match(r'interface Wireguard(\d+)$', l)] if m}
        iface = f'Wireguard{next(i for i in range(0, 64) if i not in used)}'
        name = re.sub(r'["\\]', '', str(params.get('name') or 'AmneziaWG'))[:40] or 'AmneziaWG'
        q = lambda s: '"' + str(s).replace('"', '') + '"'
        a, p = c['awg'], c['peer']
        log = []
        try:
            self._run(cli, [f'interface {iface}', f'interface {iface} description {q(name)}', f'interface {iface} security-level public',
                            f"interface {iface} ip address {c['address']} {c['mask']}", f"interface {iface} ip mtu {c['mtu']}",
                            f'interface {iface} ip tcp adjust-mss pmtu', f"interface {iface} wireguard private-key {c['privateKey']}"], log)
            if c['isAwg']:
                base = f"interface {iface} wireguard asc {a['jc']} {a['jmin']} {a['jmax']} {a['s1']} {a['s2']} {a['h1']} {a['h2']} {a['h3']} {a['h4']}"
                try:
                    self._run(cli, [base + f" {a['s3']} {a['s4']} " + ' '.join(q(a[k]) for k in ('i1', 'i2', 'i3', 'i4', 'i5'))], log)
                except DriverError:
                    if c['awg2']:
                        raise DriverError('прошивка роутера не поддерживает AmneziaWG 2.0 — обновите KeeneticOS или возьмите конфиг AWG 1.0')
                    log.pop()
                    self._run(cli, [base], log)                 # older firmware: AWG 1.0 form only
            peer = f"interface {iface} wireguard peer {p['publicKey']}"
            cmds = [peer, f"{peer} endpoint {p['endpoint']}", f"{peer} keepalive-interval {p['keepalive']}"]
            for net in p['allowed']:
                n = ipaddress.ip_network(net, strict=False)
                cmds.append(f'{peer} allow-ips {n.network_address} {n.netmask if n.version == 4 else n.prefixlen}')
            if p['psk']:
                cmds.append(f"{peer} preshared-key {p['psk']}")
            cmds += [f'{peer} connect', f'interface {iface} up']
            self._run(cli, cmds, log)
            if doms:
                self._route(cli, iface, name, doms, log)
            self._run(cli, ['system configuration save'], log)
        except Exception:
            try:                                            # leave nothing half-made behind
                self._unroute(cli, iface, [])
                cli([f'no interface {iface}'])
            except Exception:
                pass
            raise
        state = self._handshake(get, iface)
        msg = f'Подключение «{name}» ({iface}) создано' + (', сервер ответил — туннель работает' if state else
                                                            ', но сервер пока не ответил: проверьте конфиг и что сервер доступен')
        msg += f'. Через туннель идут {len(doms)} сайтов и подсетей.' if doms else '. Трафик в туннель сам не идёт — направьте нужные сайты (например, HydraRoute Neo).'
        return {'ok': True, 'log': log, 'iface': iface, 'name': name, 'domains': len(doms), 'skipped': skipped[:20], 'up': state, 'message': msg}

    def _route(self, cli, iface, name, doms, log):
        """Sites → fqdn groups of ≤300 (the router's limit) → DNS-based route through the tunnel."""
        q = lambda s: '"' + str(s).replace('"', '') + '"'
        chunks = [doms[i:i + 290] for i in range(0, len(doms), 290)]
        tag, names = secrets.token_hex(2), []
        for k, part in enumerate(chunks, 1):
            g = f'rl_{iface.lower()}_{tag}{k}'
            names.append(g)
            self._run(cli, [f'object-group fqdn {g}', f'object-group fqdn {g} description {q(f"{name} · Rack Live {k}/{len(chunks)}")}']
                      + [f'object-group fqdn {g} include {d}' for d in part] + [f'dns-proxy route object-group {g} {iface} auto'], log)
            log[:] = [x for x in log if not x['cmd'].startswith(f'object-group fqdn {g} include')] + \
                [{'cmd': f'object-group fqdn {g}: +{len(part)} сайтов', 'ok': True, 'msg': ''}]
        self._ensure_routes(cli, iface, names, log)
        return names

    def _ensure_routes(self, cli, iface, names, log):
        """The router applies route changes asynchronously: check that every route is really there, re-add if not."""
        for _ in range(4):
            time.sleep(1)
            have = {m.group(1) for l in self._rc(cli) for m in [re.match(rf'\s+route object-group (\S+) {iface}\b', l)] if m}
            missing = [g for g in names if g not in have]
            if not missing:
                return
            self._run(cli, [f'dns-proxy route object-group {g} {iface} auto' for g in missing], log)
        raise DriverError('роутер не сохранил маршрут для списка сайтов — попробуйте ещё раз')

    def _unroute(self, cli, iface, log, keep=()):
        """Remove this tunnel's DNS routes and Rack Live's site lists for it (also half-made ones after a failure)."""
        rc, pre = self._rc(cli), f'rl_{iface.lower()}_'
        routes = [m.group(1) for l in rc for m in [re.match(rf'\s+route object-group ({pre}\w+) {iface}\b', l)] if m and m.group(1) not in keep]
        groups = [l.split()[2] for l in rc if l.startswith(f'object-group fqdn {pre}') and l.split()[2] not in keep]
        cmds = [f'no dns-proxy route object-group {g} {iface}' for g in routes] + [f'no object-group fqdn {g}' for g in groups]
        if cmds:
            self._run(cli, cmds, log)

    def _handshake(self, get, iface, wait=12):
        t = time.time()
        while time.time() - t < wait:
            time.sleep(2)
            try:
                peers = ((get(f'/rci/show/interface/{iface}') or {}).get('wireguard') or {}).get('peer') or []
                if any(p.get('online') or (p.get('last-handshake') or 2147483647) < 2147483647 for p in peers):
                    return True
            except Exception:
                pass
        return False

    def action(self, cfg, action_id, params):
        if action_id == 'sec_fix':
            return self._sec_fix(cfg, params)
        if action_id == 'reboot':
            _, cli = self._session(cfg)
            cli(['system configuration save', 'system reboot'])
            return 'Роутер перезагружается'
        if action_id == 'reboot_child':
            ip = params.get('ip')
            if not ip:
                raise DriverError('не указан адрес точки')
            _, cli = self._session(cfg, host=ip)
            cli(['system reboot'])
            return 'Точка перезагружается'
        return super().action(cfg, action_id, params)
