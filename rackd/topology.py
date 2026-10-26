"""Builds the network graph (nodes + edges) from the latest device states.

Each node is attached to at most one parent (it's a tree rooted at "Интернет"),
plus any manual links the user drew in edit mode.
"""
import ipaddress
import re

ROUTER_DRIVERS = ('keenetic', 'openwrt', 'demo_router')
SWITCH_DRIVERS = ('tplink_jetstream', 'snmp', 'demo_switch')
# how the internet reaches the router: map.wan = {via: auto|direct|ont|modem, unit, name}
WAN_VIA = {'ont': ('PON-терминал', 'оптика'), 'modem': ('Модем', 'линия провайдера')}
ONT_RE = re.compile(r'(^|[^a-z])(g?e?x?pon|ont|onu)([^a-z]|$)|оптич\w*\s+терминал|терминал', re.I)
MODEM_RE = re.compile(r'модем|modem|lte|dsl|docsis', re.I)


def unit_devices(u):
    """devices of a rack unit: a shelf may hold up to 5 (deviceIds), any other unit — one (deviceId)"""
    ids = [x for x in (u.get('deviceIds') or []) if x][:5]
    return ids or ([u['deviceId']] if u.get('deviceId') else [])


def wan_unit(units, wan):
    """the rack unit that is the ONT / modem: chosen by the user, else type «Модем / ONT», else guessed by its name"""
    wan = wan or {}
    if wan.get('unit') == 'none':                  # «не в шкафу» — the box is drawn above the rack
        return None
    picked = wan.get('unit') and next((u for u in units if u.get('id') == wan['unit']), None)
    if picked:
        return picked
    # nothing chosen, or the chosen unit was removed (its rack deleted): look for the ONT again
    cands = [u for u in units if u.get('type') not in ('cross', 'patch', 'router', 'switch') and (u.get('side') or 'front') == 'front']
    return next((u for u in cands if u.get('type') == 'modem'), None) \
        or next((u for u in cands if ONT_RE.search(u.get('name') or '') or MODEM_RE.search(u.get('name') or '')), None)


def _is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def ont_links(unit):
    """LAN sockets of an ONT / modem wired to a device port (the ONT editor): [(device id, port | None)], PON (socket 1) skipped"""
    pm = (unit or {}).get('portmap') or {}
    out = []
    for n in sorted((pm.get('ports') or {}), key=lambda k: int(k) if str(k).isdigit() else 0):
        m = pm['ports'][n] or {}
        if str(n) == '1' or not m.get('dev') or str(m['dev']).startswith('u:'):
            continue
        out.append((m['dev'], str(m.get('port') or '').strip() or None))
    return out


def _addrs(d, st):
    """MACs and IPs a router is known by (to spot it among another router's clients)"""
    s = (st or {}).get('summary') or {}
    macs = {x.lower() for x in [s.get('mac'), d.get('mac')] + list(s.get('macs') or []) if x}
    host = (d.get('host') or '').split('//')[-1].split('/')[0].split(':')[0]
    ips = {x for x in (s.get('ip'), host) if x and _is_ip(x)}
    return macs, ips


def pick_main(routers, states, wan_cfg, ont_routers=()):
    """The router the internet comes into. In order: chosen by hand (map.wan.main) → wired to the ONT's LAN socket →
    a local router that is NOT a client of another one (OpenWrt behind Keenetic shows up in its client list) → Keenetic first."""
    if not routers:
        return None, 'нет роутеров'
    by = {d['id']: d for d in routers}
    m = (wan_cfg or {}).get('main')
    if m in by:
        return by[m], 'выбран вручную'
    for rid in ont_routers:
        if rid in by:
            return by[rid], 'подключён к ONT'
    local = [d for d in routers if d.get('location') != 'remote'] or routers
    behind = set()
    for d in local:
        cl = (states.get(d['id']) or {}).get('clients') or []
        cmacs = {(c.get('mac') or '').lower() for c in cl}
        cips = {c.get('ip') for c in cl}
        for o in local:
            if o is d:
                continue
            macs, ips = _addrs(o, states.get(o['id']))
            if macs & cmacs or ips & cips:
                behind.add(o['id'])
    cands = [d for d in local if d['id'] not in behind] or local
    pick = next((d for d in cands if d.get('driver') in ('keenetic', 'demo_router')), cands[0])
    return pick, ('единственный' if len(routers) == 1 else 'остальные подключены через него' if behind else 'первый в списке')


def _wan_box(wan_cfg, units, nodes, add, wan_port):
    """→ (node id, label for the provider line) when the internet comes through an ONT / modem; None = straight into the router"""
    wan_cfg = wan_cfg or {}
    via = wan_cfg.get('via') or 'auto'
    if via == 'direct':
        return None
    u = wan_unit(units, wan_cfg)
    if via == 'auto':
        if not u:
            return None
        via = 'modem' if u.get('type') != 'modem' and MODEM_RE.search(u.get('name') or '') and not ONT_RE.search(u.get('name') or '') else 'ont'
    title, line = WAN_VIA.get(via, WAN_VIA['ont'])
    # the box is up when the router's WAN port has a link (its own status if a device is bound to the unit)
    link = (wan_port or {}).get('link')
    status = 'online' if link else 'offline' if link is False else 'unknown'
    if u and u.get('deviceId') and 'd:' + u['deviceId'] in nodes:
        nid = 'd:' + u['deviceId']
        nodes[nid]['wan'] = True
    elif u:
        nid = add({'id': 'u:' + u['id'], 'label': wan_cfg.get('name') or u.get('name') or title, 'sub': title, 'kind': 'modem', 'status': status,
                   'rackUnit': u['id'], 'rackId': u.get('rackId'), 'wan': True})
    else:
        nid = add({'id': 'wan:box', 'label': wan_cfg.get('name') or title, 'sub': 'у провайдера' if via == 'ont' else '', 'kind': 'modem',
                   'status': status, 'wan': True})
    pm = (u or {}).get('portmap') or {}
    return nid, pm.get('provider') or wan_cfg.get('line') or line


def build(devices, states, rack_units, manual_links, show_clients=True, drivers=None, wan_cfg=None):
    nodes, edges, attached = {}, [], set()
    unit_by_dev = {}                               # each unit carries rackId; a shelf holds up to 5 devices side by side
    for u in rack_units:
        ids = unit_devices(u)
        for i, did in enumerate(ids):
            unit_by_dev[did] = dict(u, slot=i, slots=len(ids))

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
                   'rackUnit': (unit_by_dev.get(d['id']) or {}).get('id'), 'rackId': (unit_by_dev.get(d['id']) or {}).get('rackId'),
                   'remote': d.get('location') == 'remote', 'room': d.get('siteName'),
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
                       'model': ch.get('model'), 'clients': ch.get('clients'), 'backhaul': ch.get('backhaul'), 'uplinkSpeed': ch.get('uplink')})
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
    via = (wan_cfg or {}).get('via') or 'auto'
    ont = wan_unit(rack_units, wan_cfg) if via != 'direct' else None
    ont_to = ont_links(ont)                         # ONT LAN sockets → router ports (may feed several routers)
    main, why = pick_main(routers, states, wan_cfg, [d for d, _ in ont_to])
    main_id = 'd:' + main['id'] if main else None
    main_ports = (states.get(main['id']) or {}).get('ports', []) if main else []
    inet = None

    def internet():
        nonlocal inet
        if not inet:
            inet = add({'id': 'inet', 'label': 'Интернет', 'sub': '', 'kind': 'internet', 'status': 'online'})
        return inet

    def port_of(dev_id, n):
        return next((p for p in (states.get(dev_id) or {}).get('ports') or [] if n and str(p.get('n')) == str(n)), None)

    # the router's port the ONT is plugged into (from the ONT editor), else its WAN port
    main_link = next((n for d, n in ont_to if main and d == main['id']), None)
    wan = port_of(main['id'], main_link) if main and main_link else next((p for p in main_ports if p.get('kind') == 'wan'), None)
    if main:
        nodes[main_id]['main'] = why
        box = _wan_box(wan_cfg, rack_units, nodes, add, wan)
        wan_kw = dict(targetPort=(wan or {}).get('n') or (int(main_link) if main_link and main_link.isdigit() else None),
                      speed=(wan or {}).get('speed'), kind='wan', label=(wan or {}).get('ip') or '')
        if box:                                    # internet → ONT / modem (provider line) → cable → router WAN port
            edge(internet(), box[0], kind='isp', label=box[1])
            edge(box[0], main_id, **wan_kw)
            for did, n in ont_to:                  # other routers on other LAN sockets of the same ONT
                if did != main['id'] and 'd:' + did in nodes:
                    p = port_of(did, n)
                    edge(box[0], 'd:' + did, extra_ok=True, kind='wan', targetPort=(p or {}).get('n') or (int(n) if n and n.isdigit() else None),
                         speed=(p or {}).get('speed'))
        else:
            edge(internet(), main_id, **wan_kw)
        attached.add(internet())

    # «Удалённые» устройства (VPS, роутер на другой площадке) — всегда прямо от «Интернета». Первыми, до всех остальных связей: иначе устройство,
    # чей адрес совпал с адресом клиента домашней сети (удалённый роутер, который пока стоит дома), цепляется как клиент и тянет за собой цепочку.
    for nid, n in list(nodes.items()):
        if n.get('remote') and nid != main_id:
            edge(internet(), nid, kind='remote')

    # unmanaged switches (rackd/drivers/unmanaged.py): «plugged into device X, port N» — what that port sees hangs on them
    um = {(d['uplinkDevice'], str(d.get('uplinkPort') or '').strip()): 'd:' + d['id'] for d in active
          if d.get('driver') == 'unmanaged' and d.get('uplinkDevice') and str(d.get('uplinkPort') or '').strip()}

    def via_unmanaged(owner_id, port, nid_from, speed, peer_targets):
        """→ True when port `port` of `owner_id` leads into an unmanaged switch: cable to it, the devices behind on it"""
        u = um.get((owner_id, str(port)))
        if not u or u not in nodes:
            return False
        edge(nid_from, u, sourcePort=int(port) if str(port).isdigit() else None, speed=speed, kind='wire')
        for t in peer_targets:
            if t and t != u:
                edge(u, t, extra_ok=bool(t.startswith('d:')), kind='wire')
        return True

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
            if (d['id'], str(p['n'])) in um:
                via_unmanaged(d['id'], p['n'], sid, p.get('speed'), [mac_idx.get(x['mac'].lower()) or node_for_mac(x['mac']) for x in peers])
                continue
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
            if via_unmanaged(main['id'], port, main_id, mp.get('speed'), [nid]):
                continue
            edge(main_id, nid, extra_ok=bool(nid and nid.startswith('d:')), sourcePort=int(port), speed=mp.get('speed'), kind='wire')
    for key, cid in ap_node.items():
        if cid not in attached and main:
            n = nodes.get(cid) or {}
            if n.get('backhaul') == 'wire':                  # cabled to the router (Ethernet backhaul) — the switch port just isn't known
                sp = n.get('uplinkSpeed')
                edge(main_id, cid, kind='wire', speed=int(sp) if str(sp or '').isdigit() else None, label='кабель')
            else:
                edge(main_id, cid, kind='mesh')
    for mac, c in clients.items():
        ap = c.get('ap')
        if not ap:
            continue
        parent = ap_node.get(ap) or (('d:' + c['src']) if ap == 'self' else None)
        nid = node_for_mac(mac)
        if parent and nid:
            edge(parent, nid, kind='wifi', speed=c.get('rate'), rssi=c.get('rssi'), band=c.get('band'))

    # clients that ONLY a secondary router knows — an OpenWrt with a captive portal (its DHCP leases): no Wi-Fi point, no switch port is reported for them.
    # They hang under that router (up to 20; the rest is one «ещё N» card), so the guest network is on the map too
    if show_clients:
        for d in active:
            rid = 'd:' + d['id']
            if d.get('driver') not in ROUTER_DRIVERS or (main and d['id'] == main['id']) or rid not in nodes:
                continue
            own = {}
            for c in (states.get(d['id']) or {}).get('clients') or []:      # this router's own list, not the merged one: the main router may list the same MAC without a place to draw it
                if c.get('mac'):
                    own.setdefault(c['mac'].lower(), dict(c, src=d['id']))
            lst = [(m, c) for m, c in own.items() if m not in mac_idx and 'h:' + m not in nodes and c.get('online', True) is not False]
            for m, c in lst:
                clients.setdefault(m, c)                                      # node_for_mac reads the merged index
            lst.sort(key=lambda x: (str(x[1].get('segment') or ''), str(x[1].get('name') or x[1].get('ip') or '')))
            for m, c in lst[:20]:
                nid = node_for_mac(m)
                if nid:
                    edge(rid, nid, kind='lan', label=c.get('segment') or '')
            if len(lst) > 20:
                gid = add({'id': f'x:{d["id"]}:leases', 'label': f'ещё {len(lst) - 20} устройств', 'sub': 'сеть этого роутера', 'kind': 'other', 'status': 'online', 'client': True})
                edge(rid, gid, kind='lan')

    for nid, n in list(nodes.items()):
        if nid in attached or nid == inet:
            continue
        if n.get('remote'):
            edge(internet(), nid, kind='remote')
        elif n.get('deviceId'):
            ud = next((d for d in active if d['id'] == n['deviceId'] and d.get('driver') == 'unmanaged' and d.get('uplinkDevice')), None)
            if ud and 'd:' + ud['uplinkDevice'] in nodes:                 # an unmanaged switch on a port nobody reports: still under its uplink
                edge('d:' + ud['uplinkDevice'], nid, kind='wire', sourcePort=int(ud['uplinkPort']) if str(ud.get('uplinkPort') or '').isdigit() else None)
                continue
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
