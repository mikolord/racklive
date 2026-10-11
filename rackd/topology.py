"""Builds the network graph (nodes + edges) from the latest device states.

Each node is attached to at most one parent (it's a tree rooted at "Интернет"),
plus any manual links the user drew in edit mode.
"""
import ipaddress

ROUTER_DRIVERS = ('keenetic', 'openwrt')
SWITCH_DRIVERS = ('tplink_jetstream',)


def _is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def build(devices, states, rack_units, manual_links, show_clients=True, drivers=None):
    nodes, edges, attached = {}, [], set()
    unit_by_dev = {u['deviceId']: u for u in rack_units if u.get('deviceId')}

    def add(n):
        nodes.setdefault(n['id'], n)
        return n['id']

    def edge(a, b, extra_ok=False, **kw):
        if not a or not b or a == b:
            return False
        if b in attached:
            if extra_ok and not any({e['source'], e['target']} == {a, b} for e in edges):
                edges.append(dict(id=f'{a}>{b}', source=a, target=b, extra=True, **kw))
            return False
        attached.add(b)
        edges.append(dict(id=f'{a}>{b}', source=a, target=b, **kw))
        return True

    mac_idx, ip_idx, ap_node = {}, {}, {}
    active = [d for d in devices if d.get('enabled', True)]
    for d in active:
        st = states.get(d['id']) or {}
        s = st.get('summary') or {}
        drv_kind = getattr((drivers or {}).get(d.get('driver')), 'kind', 'other')
        nid = add({'id': 'd:' + d['id'], 'label': d.get('name') or d.get('host'), 'sub': s.get('ip') or d.get('host', ''),
                   'kind': d.get('kind') or drv_kind, 'status': st.get('status', 'unknown'), 'deviceId': d['id'],
                   'rackUnit': (unit_by_dev.get(d['id']) or {}).get('id'), 'remote': d.get('location') == 'remote',
                   'model': s.get('model')})
        for mac in [s.get('mac'), d.get('mac')] + list(s.get('macs') or []):
            if mac:
                mac_idx[mac.lower()] = nid
        host = (d.get('host') or '').split('//')[-1].split('/')[0].split(':')[0]
        for ip in (s.get('ip'), host):
            if ip and _is_ip(ip):
                ip_idx[ip] = nid
    for d in active:
        st = states.get(d['id']) or {}
        for ch in st.get('children') or []:
            key = ch.get('key') or ch.get('mac')
            existing = mac_idx.get((ch.get('mac') or '').lower()) or ip_idx.get(ch.get('ip'))
            if existing:
                ap_node[key] = existing
                continue
            cid = add({'id': f"c:{d['id']}:{key}", 'label': ch.get('name') or 'Точка доступа', 'sub': ch.get('ip') or '',
                       'kind': ch.get('kind') or 'ap', 'status': ch.get('status') or 'online', 'childOf': d['id'], 'childKey': key,
                       'model': ch.get('model'), 'clients': ch.get('clients')})
            ap_node[key] = cid
            if ch.get('mac'):
                mac_idx[ch['mac'].lower()] = cid
            if ch.get('ip'):
                ip_idx[ch['ip']] = cid

    clients = {}
    for d in active:
        for c in (states.get(d['id']) or {}).get('clients') or []:
            if c.get('mac'):
                clients.setdefault(c['mac'].lower(), dict(c, src=d['id']))

    def node_for_mac(mac, fallback_label=None):
        mac = (mac or '').lower()
        if mac in mac_idx:
            return mac_idx[mac]
        c = clients.get(mac)
        if c and c.get('ip') in ip_idx:
            return ip_idx[c['ip']]
        if not show_clients:
            return None
        if c:
            return add({'id': 'h:' + mac, 'label': c.get('name') or mac, 'sub': c.get('ip') or '', 'kind': c.get('kind') or 'other',
                        'status': 'online', 'client': True, 'segment': c.get('segment'), 'mac': mac})
        return add({'id': 'h:' + mac, 'label': fallback_label or mac, 'sub': '', 'kind': 'other', 'status': 'unknown', 'client': True, 'mac': mac})

    routers = [d for d in active if d.get('driver') in ROUTER_DRIVERS and (states.get(d['id']) or {}).get('ports')]
    main = next((d for d in routers if d.get('driver') == 'keenetic'), routers[0] if routers else None)
    main_id = 'd:' + main['id'] if main else None
    main_ports = (states.get(main['id']) or {}).get('ports', []) if main else []
    inet = None

    def internet():
        nonlocal inet
        if not inet:
            inet = add({'id': 'inet', 'label': 'Интернет', 'sub': '', 'kind': 'internet', 'status': 'online'})
        return inet

    wan = next((p for p in main_ports if p.get('kind') == 'wan'), None)
    if main:
        edge(internet(), main_id, targetPort=wan['n'] if wan else None, speed=(wan or {}).get('speed'), kind='wan',
             label=(wan or {}).get('ip') or '')
        attached.add(internet())

    router_uplink_port = None
    for d in active:
        if d.get('driver') not in SWITCH_DRIVERS:
            continue
        st = states.get(d['id']) or {}
        ports = [p for p in st.get('ports') or [] if p.get('link')]
        if not ports:
            continue
        sid = 'd:' + d['id']
        router_mac = ((states.get(main['id']) or {}).get('summary') or {}).get('mac', '').lower() if main else ''
        protected = [int(x) for x in str(d.get('protectedPorts') or '').replace(' ', '').split(',') if x.isdigit()]
        up = next((p for p in ports if router_mac and any(x['mac'].lower() == router_mac for x in p.get('peers') or [])), None) \
            or next((p for p in ports if p['n'] in protected), None) \
            or next((p for p in ports if 'uplink' in (p.get('label') or '').lower()), None)
        if not up:
            up = max(ports, key=lambda p: len(p.get('peers') or []))
            if len(up.get('peers') or []) < 4:
                up = None
        if up and main:
            rp = next((p for p in main_ports if p.get('vlansT') and p.get('link')), None) or \
                 next((p for p in main_ports if p.get('link') and p.get('kind') != 'wan'), None)
            router_uplink_port = rp['n'] if rp else None
            edge(main_id, sid, sourcePort=router_uplink_port, targetPort=up['n'], speed=up.get('speed'), kind='wire',
                 vlans=sorted(set((up.get('vlansU') or []) + (up.get('vlansT') or []))))
        for p in ports:
            if p is up:
                continue
            peers = p.get('peers') or []
            if not peers:
                continue
            managed = [mac_idx[x['mac'].lower()] for x in peers if x['mac'].lower() in mac_idx]
            if managed:
                targets = managed[:1]
            elif len(peers) <= 3:
                targets = [node_for_mac(x['mac'], p.get('label')) for x in peers]
            else:
                targets = [add({'id': f"x:{d['id']}:{p['n']}", 'label': p.get('label') or f'{len(peers)} устройств', 'sub': f'{len(peers)} MAC',
                                'kind': 'switch', 'status': 'online', 'client': True})]
            for t in targets:
                edge(sid, t, extra_ok=bool(managed), sourcePort=p['n'], speed=p.get('speed'), kind='wire', poeW=p.get('poeW') or 0,
                     vlans=sorted(set((p.get('vlansU') or []) + (p.get('vlansT') or []))), label=p.get('label') or '')

    if main:
        for c in (states.get(main['id']) or {}).get('clients') or []:
            port = str(c.get('port') or '')
            if c.get('ap') or not port.isdigit() or int(port) == router_uplink_port:
                continue
            nid = node_for_mac(c.get('mac'))
            mp = next((p for p in main_ports if str(p['n']) == port), {})
            edge(main_id, nid, extra_ok=bool(nid and nid.startswith('d:')), sourcePort=int(port), speed=mp.get('speed'), kind='wire')
    for key, cid in ap_node.items():
        if cid not in attached and main:
            edge(main_id, cid, kind='mesh')
    for mac, c in clients.items():
        ap = c.get('ap')
        if not ap:
            continue
        parent = ap_node.get(ap) or (('d:' + c['src']) if ap == 'self' else None)
        nid = node_for_mac(mac)
        if parent and nid:
            edge(parent, nid, kind='wifi', speed=c.get('rate'), rssi=c.get('rssi'), band=c.get('band'))

    for nid, n in list(nodes.items()):
        if nid in attached or nid == inet:
            continue
        if n.get('remote'):
            edge(internet(), nid, kind='remote')
        elif n.get('deviceId'):
            c = next((c for c in clients.values() if c.get('ip') == n.get('sub')), None)
            parent = ('d:' + c['src']) if c else (main_id or internet())
            edge(parent, nid, kind='lan' if parent != inet else 'remote')
        elif n.get('client') and main:
            edge(main_id, nid, kind='lan')

    for l in manual_links or []:
        a, b = l.get('source'), l.get('target')
        if a in nodes and b in nodes:
            edges.append({'id': l.get('id') or f'm:{a}>{b}', 'source': a, 'target': b, 'kind': 'manual', 'label': l.get('label', ''),
                          'sourcePort': l.get('sourcePort'), 'targetPort': l.get('targetPort'), 'manual': True})
    return {'nodes': list(nodes.values()), 'edges': edges}
