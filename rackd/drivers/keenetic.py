"""Keenetic / Netcraze routers via the RCI HTTP API (KeeneticOS 3.x–5.x)."""
import codecs, hashlib, http.cookiejar, json, re, time, urllib.error, urllib.request

from . import Driver, FIELD_HOST, FIELD_PASS, FIELD_USER
from ..util import DriverError, uptime_seconds, guess_kind


class Keenetic(Driver):
    id = 'keenetic'
    title = 'Keenetic / Netcraze'
    kind = 'router'
    description = 'Роутер: порты, VLAN, клиенты по сегментам, mesh-точки и их Wi-Fi-клиенты.'
    fields = [FIELD_HOST, dict(FIELD_USER, default='admin'), FIELD_PASS]
    actions = [{'id': 'reboot', 'label': 'Перезагрузить роутер', 'scope': 'device', 'confirm': 'Интернет пропадёт на 2–3 минуты. Перезагрузить?'},
               {'id': 'reboot_child', 'label': 'Перезагрузить точку', 'scope': 'child', 'confirm': 'Wi-Fi этой точки пропадёт на пару минут. Перезагрузить?'}]

    def _session(self, cfg, host=None):
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        base = 'http://' + (host or cfg['host'])

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
            raise DriverError('это не Keenetic или RCI недоступен')
        user = cfg.get('username') or 'admin'
        md5 = hashlib.md5(f"{user}:{realm}:{cfg.get('password', '')}".encode()).hexdigest()
        a = req('/auth', {'login': user, 'password': hashlib.sha256((ch + md5).encode()).hexdigest()})
        if getattr(a, 'status', getattr(a, 'code', 0)) != 200:
            raise DriverError('неверный логин или пароль')
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
        for l in rc:
            if not l.startswith(' '):
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
            elif cur_b:
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
                             'fwUpdate': bool(m.get('fw-update-available')) and m.get('fw-available') != m.get('fw')})

        clients = []
        for h in get('/rci/show/ip/hotspot').get('host', []):
            if not h.get('active'):
                continue
            iface = h.get('interface') or {}
            seg = iface.get('description') or iface.get('id') if isinstance(iface, dict) else iface
            mws_i = h.get('mws') or {}
            ap = mws_i.get('cid') or ('self' if h.get('ap') or h.get('ssid') else None)
            clients.append({'mac': h.get('mac'), 'ip': h.get('ip'), 'name': h.get('name') or h.get('hostname') or '',
                            'segment': seg, 'ap': ap, 'rssi': mws_i.get('rssi') or h.get('rssi'), 'rate': mws_i.get('txrate') or h.get('txrate'),
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
        return {'status': 'online',
                'summary': {'model': ver.get('model'), 'fw': ver.get('title'), 'uptime': uptime_seconds(sysi.get('uptime')),
                            'cpu': sysi.get('cpuload'), 'mem': round(int(mem[0]) * 100 / max(1, int(mem[1]))),
                            'ip': cfg['host'], 'mac': lanmac},
                'ports': ports, 'clients': clients, 'children': children, 'sections': sections, 'vpn': self._vpn(get, rc)}

    def action(self, cfg, action_id, params):
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
