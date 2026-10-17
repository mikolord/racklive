"""Scenes: a made-up network as DATA — devices, cables, Wi-Fi, racks, houses with floors and rooms — for the DEMO mode (and nothing else).

A scene never runs anything: it is checked against a strict schema (known kinds, limits, every reference must resolve) and turned into the simulated devices of rackd/drivers/demo.py.
It is shown in an isolated demo copy of Rack Live (rackd/sandbox.py) that has no connection to the real installation, its devices or its data.
SCENE_API is a contract: change nothing in the format without raising it."""
import hashlib, ipaddress, json, math, random, re, secrets, time

SCENE_API = 1
PLUGIN_API = 1                     # a scene is a package of the same family as plugins and tools (plugin.json, kind: "scene")
LIMITS = {'devices': 400, 'links': 900, 'wifi': 600, 'racks': 40, 'units': 120, 'buildings': 20, 'floors': 14, 'rooms': 80, 'items': 300, 'walls': 200, 'poles': 30, 'vlans': 12}
KINDS = {'router', 'switch', 'server', 'nas', 'ap', 'camera', 'nvr', 'phone', 'tablet', 'tv', 'laptop', 'pc', 'printer', 'speaker', 'iot', 'web', 'ups', 'modem', 'other'}
UNIT_TYPES = {'router', 'switch', 'server', 'nas', 'patch', 'cross', 'organizer', 'shelf', 'ups', 'pdu', 'modem', 'nvr', 'other'}
KEY_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,23}$')
ID_RE = re.compile(r'^[a-z][a-z0-9_-]{0,23}$')
COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
SPEEDS = (10, 100, 1000, 2500, 5000, 10000)


def mac_of(key):
    h = hashlib.md5(str(key).encode()).hexdigest()
    return 'aa:' + ':'.join(h[i:i + 2] for i in range(0, 10, 2))


def _txt(v, n):
    return re.sub(r'\s+', ' ', str(v if v is not None else '')).strip()[:n]


def validate(sc):
    """→ (errors, warnings, clean scene or None). Nothing is trusted: every value is re-built from the checked pieces."""
    errors, warnings = [], []
    if not isinstance(sc, dict):
        return ['сцена должна быть объектом'], [], None
    devs_in = sc.get('devices')
    if not isinstance(devs_in, list) or not devs_in:
        return ['devices: нужен непустой список устройств'], [], None
    if len(devs_in) > LIMITS['devices']:
        return [f'devices: не больше {LIMITS["devices"]}'], [], None
    clean = {'settings': {}, 'devices': [], 'links': [], 'wifi': [], 'racks': [], 'plan': {'poles': [], 'links': [], 'buildings': []}}
    st = sc.get('settings') or {}
    clean['settings']['title'] = _txt(st.get('title'), 60)
    vl = []
    for v in (st.get('vlans') or [])[:LIMITS['vlans']]:
        if isinstance(v, dict) and isinstance(v.get('vid'), int) and 1 <= v['vid'] <= 4094:
            vl.append({'vid': v['vid'], 'name': _txt(v.get('name'), 30) or f"VLAN {v['vid']}", 'color': v['color'] if COLOR_RE.match(str(v.get('color') or '')) else '#0A84FF'})
    clean['settings']['vlans'] = vl
    keys = {}
    for i, d in enumerate(devs_in):
        where = f'devices[{i + 1}]'
        if not isinstance(d, dict) or not KEY_RE.match(str(d.get('key') or '')):
            errors.append(f'{where}: key — латиница нижнего регистра, цифры, - и _ (до 24 знаков)')
            continue
        if d['key'] in keys:
            errors.append(f'{where}: key «{d["key"]}» повторяется')
            continue
        kind = d.get('kind')
        if kind not in KINDS:
            errors.append(f'{where}: kind — один из ' + ', '.join(sorted(KINDS)))
            continue
        ip = str(d.get('ip') or '')
        if ip:
            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                errors.append(f'{where}: ip «{ip}» — неверный адрес')
                ip = ''
        ports = d.get('ports', 0)
        if not isinstance(ports, int) or not 0 <= ports <= 96:
            errors.append(f'{where}: ports — число от 0 до 96')
            ports = 0
        cl = d.get('clients', 0)
        if not isinstance(cl, int) or not 0 <= cl <= 300:
            errors.append(f'{where}: clients — число от 0 до 300')
            cl = 0
        wanp = d.get('wan')
        if wanp is not None and (not isinstance(wanp, int) or not 1 <= wanp <= ports):
            errors.append(f'{where}: wan — номер порта этого устройства')
            wanp = None
        status = d.get('status', 'online')
        if status not in ('online', 'warning', 'offline'):
            errors.append(f'{where}: status — online, warning или offline')
            status = 'online'
        keys[d['key']] = {'key': d['key'], 'name': _txt(d.get('name'), 60) or d['key'], 'kind': kind, 'ip': ip, 'ports': ports, 'clients': cl, 'status': status,
                          'vendor': _txt(d.get('vendor'), 40), 'model': _txt(d.get('model'), 40), 'vlan': _txt(d.get('vlan'), 30), 'remote': bool(d.get('remote')), 'site': _txt(d.get('site'), 40), 'wan': wanp}
    clean['devices'] = list(keys.values())
    used = set()
    for i, l in enumerate(sc.get('links') or []):
        where = f'links[{i + 1}]'
        if len(clean['links']) >= LIMITS['links']:
            errors.append(f'links: не больше {LIMITS["links"]}')
            break
        if not isinstance(l, dict) or l.get('from') not in keys or l.get('to') not in keys:
            errors.append(f'{where}: from и to — ключи устройств из devices')
            continue
        a, b = keys[l['from']], keys[l['to']]
        p = l.get('port')
        if not isinstance(p, int) or not 1 <= p <= a['ports']:
            errors.append(f'{where}: port — номер порта устройства «{a["key"]}» (у него портов: {a["ports"]})')
            continue
        if (a['key'], p) in used:
            errors.append(f'{where}: порт {p} устройства «{a["key"]}» уже занят')
            continue
        used.add((a['key'], p))
        tp = l.get('toPort')
        if tp is not None and (not isinstance(tp, int) or not 1 <= tp <= b['ports'] or (b['key'], tp) in used):
            errors.append(f'{where}: toPort — свободный порт устройства «{b["key"]}»')
            tp = None
        if tp:
            used.add((b['key'], tp))
        sp = l.get('speed', 1000)
        clean['links'].append({'from': a['key'], 'port': p, 'to': b['key'], 'toPort': tp, 'speed': sp if sp in SPEEDS else 1000,
                               'poe': max(0, min(120, float(l.get('poe') or 0))) if isinstance(l.get('poe'), (int, float)) else 0, 'uplink': bool(l.get('uplink')), 'wan': bool(l.get('wan')),
                               'vlan': l.get('vlan') if isinstance(l.get('vlan'), int) and 1 <= l['vlan'] <= 4094 else 1})
    for i, w in enumerate(sc.get('wifi') or []):
        where = f'wifi[{i + 1}]'
        if len(clean['wifi']) >= LIMITS['wifi']:
            errors.append(f'wifi: не больше {LIMITS["wifi"]}')
            break
        if not isinstance(w, dict) or w.get('ap') not in keys or keys[w['ap']]['kind'] not in ('ap', 'router'):
            errors.append(f'{where}: ap — ключ устройства вида ap или router')
            continue
        dev = w.get('device')
        if dev is not None and dev not in keys:
            errors.append(f'{where}: device — ключ устройства из devices')
            continue
        if dev is None and not _txt(w.get('name'), 40):
            errors.append(f'{where}: нужно name или device')
            continue
        rssi = w.get('rssi')
        clean['wifi'].append({'ap': w['ap'], 'device': dev, 'name': _txt(w.get('name'), 40), 'kind': w.get('kind') if w.get('kind') in KINDS else 'phone',
                              'rssi': rssi if isinstance(rssi, int) and -100 <= rssi <= -20 else -58, 'band': '2.4 ГГц' if str(w.get('band') or '').startswith('2') else '5 ГГц'})
    rack_ids = set()
    for i, r in enumerate(sc.get('racks') or []):
        where = f'racks[{i + 1}]'
        if len(clean['racks']) >= LIMITS['racks']:
            errors.append(f'racks: не больше {LIMITS["racks"]}')
            break
        if not isinstance(r, dict) or not ID_RE.match(str(r.get('id') or '')) or r['id'] in rack_ids:
            errors.append(f'{where}: id — латиница, без повторов')
            continue
        rack_ids.add(r['id'])
        kind = r.get('kind') if r.get('kind') in ('rack', 'box', 'place') else 'rack'
        total = r.get('totalU') if isinstance(r.get('totalU'), int) and 1 <= r['totalU'] <= 60 else 12
        units = []
        for j, u in enumerate((r.get('units') or [])[:LIMITS['units']]):
            if not isinstance(u, dict):
                continue
            ty = u.get('type') if u.get('type') in UNIT_TYPES else 'other'
            if u.get('device') is not None and u['device'] not in keys:
                errors.append(f'{where}.units[{j + 1}]: device — ключ устройства из devices')
                continue
            us, sz = u.get('uStart') if isinstance(u.get('uStart'), int) else j + 1, u.get('uSize') if isinstance(u.get('uSize'), int) and 1 <= u['uSize'] <= 8 else 1
            if kind == 'rack' and not (1 <= us and us + sz - 1 <= total):
                errors.append(f'{where}.units[{j + 1}]: юнит вылезает за стойку (uStart {us}, uSize {sz}, всего {total} U)')
                continue
            units.append({'name': _txt(u.get('name'), 40) or ty, 'type': ty, 'uStart': us, 'uSize': sz, 'device': u.get('device'), 'color': u['color'] if COLOR_RE.match(str(u.get('color') or '')) else '#8e8e93'})
        clean['racks'].append({'id': r['id'], 'name': _txt(r.get('name'), 40) or r['id'], 'kind': kind, 'totalU': total, 'units': units})
    plan = sc.get('plan') or {}
    nodes = set()
    num = lambda v, lo=-2000, hi=6000: v if isinstance(v, (int, float)) and lo <= v <= hi else None
    for i, p in enumerate((plan.get('poles') or [])[:LIMITS['poles']]):
        if isinstance(p, dict) and ID_RE.match(str(p.get('id') or '')) and num(p.get('x')) is not None and num(p.get('y')) is not None:
            clean['plan']['poles'].append({'id': p['id'], 'name': _txt(p.get('name'), 40), 'x': p['x'], 'y': p['y']})
            nodes.add(p['id'])
    for bi, b in enumerate((plan.get('buildings') or [])[:LIMITS['buildings']]):
        where = f'plan.buildings[{bi + 1}]'
        if not isinstance(b, dict) or not ID_RE.match(str(b.get('id') or '')) or b['id'] in nodes or num(b.get('x')) is None or num(b.get('y')) is None:
            errors.append(f'{where}: id (латиница, без повторов), x, y')
            continue
        nodes.add(b['id'])
        floors = []
        for fi, f in enumerate((b.get('floors') or [])[:LIMITS['floors']]):
            fw = f'{where}.floors[{fi + 1}]'
            if not isinstance(f, dict) or not ID_RE.match(str(f.get('id') or '')):
                errors.append(f'{fw}: id — латиница')
                continue
            rooms = []
            for r in (f.get('rooms') or [])[:LIMITS['rooms']]:
                if isinstance(r, dict) and all(num(r.get(k), -2000, 6000) is not None for k in ('x', 'y')) and all(num(r.get(k), 10, 3000) is not None for k in ('w', 'h')):
                    rooms.append({'x': r['x'], 'y': r['y'], 'w': r['w'], 'h': r['h'], 'text': _txt(r.get('text'), 40), 'color': r['color'] if COLOR_RE.match(str(r.get('color') or '')) else '#0a84ff'})
            walls = [{'x1': w['x1'], 'y1': w['y1'], 'x2': w['x2'], 'y2': w['y2']} for w in (f.get('walls') or [])[:LIMITS['walls']]
                     if isinstance(w, dict) and all(num(w.get(k)) is not None for k in ('x1', 'y1', 'x2', 'y2'))]
            items = []
            for it in (f.get('items') or [])[:LIMITS['items']]:
                if not isinstance(it, dict) or num(it.get('x')) is None or num(it.get('y')) is None:
                    continue
                k = it.get('kind')
                if k == 'device' and it.get('ref') in keys:
                    items.append({'kind': 'device', 'ref': it['ref'], 'x': it['x'], 'y': it['y']})
                elif k == 'place' and it.get('ref') in rack_ids:
                    items.append({'kind': 'place', 'ref': it['ref'], 'x': it['x'], 'y': it['y']})
                elif k == 'label' and _txt(it.get('text'), 40):
                    items.append({'kind': 'label', 'text': _txt(it['text'], 40), 'x': it['x'], 'y': it['y']})
                else:
                    errors.append(f'{fw}: элемент плана {k!r} ссылается на {it.get("ref")!r}, которого нет (device — ключ устройства, place — id шкафа)')
            floors.append({'id': f['id'], 'name': _txt(f.get('name'), 30) or f['id'], 'outdoor': bool(f.get('outdoor')), 'rooms': rooms, 'walls': walls, 'items': items})
        clean['plan']['buildings'].append({'id': b['id'], 'name': _txt(b.get('name'), 40) or b['id'], 'x': b['x'], 'y': b['y'], 'floors': floors})
    for l in (plan.get('links') or [])[:60]:
        if isinstance(l, dict) and l.get('from') in nodes and l.get('to') in nodes:
            clean['plan']['links'].append({'from': l['from'], 'to': l['to'], 'label': _txt(l.get('label'), 40)})
    if not any(d['kind'] == 'router' for d in clean['devices']):
        warnings.append('в сцене нет роутера: карта не покажет «Интернет» и связи')
    if not clean['plan']['buildings']:
        warnings.append('нет plan.buildings: вкладка «План» будет пустой')
    return errors, warnings, (None if errors else clean)


def stats(clean):
    return {'devices': len(clean['devices']), 'links': len(clean['links']), 'racks': len(clean['racks']), 'buildings': len(clean['plan']['buildings']),
            'floors': sum(len(b['floors']) for b in clean['plan']['buildings']), 'rooms': sum(len(f['rooms']) for b in clean['plan']['buildings'] for f in b['floors'])}


def seed(store, clean):
    """a CHECKED scene → simulated devices, racks, the plan and a day of history in an (empty) demo config"""
    cfg = store.cfg
    cfg['devices'], did = [], {}
    DRV = {'router': 'demo_sim_router', 'switch': 'demo_sim_switch'}
    by = {d['key']: d for d in clean['devices']}
    for d in clean['devices']:
        did[d['key']] = 'sc-' + d['key']
        cfg['devices'].append({'id': did[d['key']], 'enabled': True, 'location': 'remote' if d['remote'] else 'local', 'name': d['name'], 'driver': DRV.get(d['kind'], 'demo_sim'), 'kind': d['kind'],
                               'host': d['ip'], 'simMac': mac_of(d['key']), 'simSeed': d['key'], 'simPorts': d['ports'], 'simClients': d['clients'], 'simStatus': d['status'], 'simWan': d['wan'],
                               'simVendor': d['vendor'], 'simModel': d['model'], 'simVlan': d['vlan'], 'simLinks': [], 'simWifi': [], **({'site': d['site']} if d['site'] else {})})
    dev = {d['id']: d for d in cfg['devices']}
    for l in clean['links']:
        a, b = dev[did[l['from']]], dev[did[l['to']]]
        a['simLinks'].append({'port': l['port'], 'mac': mac_of(l['to']), 'name': by[l['to']]['name'], 'speed': l['speed'], 'poeW': l['poe'], 'uplink': l['uplink'], 'wan': l['wan'], 'vlan': l['vlan']})
        if l['toPort'] or (l['uplink'] and b['simPorts']):
            tp = l['toPort'] or b['simPorts']
            if not any(x['port'] == tp for x in b['simLinks']):
                b['simLinks'].append({'port': tp, 'mac': mac_of(l['from']), 'name': by[l['from']]['name'], 'speed': l['speed'], 'poeW': 0, 'uplink': True, 'vlan': l['vlan']})
    for w in clean['wifi']:
        ap = dev[did[w['ap']]]
        if w['device']:
            o = by[w['device']]
            ap['simWifi'].append({'mac': mac_of(w['device']), 'ip': o['ip'], 'name': o['name'], 'kind': o['kind'], 'rssi': w['rssi'], 'band': w['band']})
        else:
            ap['simWifi'].append({'mac': mac_of('wifi:' + w['ap'] + w['name']), 'ip': '', 'name': w['name'], 'kind': w['kind'], 'rssi': w['rssi'], 'band': w['band']})
    cfg['racks'] = []
    for r in clean['racks']:
        units = []
        for k, u in enumerate(r['units']):
            units.append({'id': f"u-{r['id']}-{k}", 'side': 'front', 'notes': '', 'name': u['name'], 'type': u['type'], 'uStart': u['uStart'], 'uSize': u['uSize'], 'color': u['color'],
                          'deviceId': did.get(u['device']) if u['device'] else None})
        cfg['racks'].append({'id': r['id'], 'name': r['name'], 'totalU': r['totalU'], 'kind': r['kind'], 'units': units})
    ctr = [0]

    def nid(p):
        ctr[0] += 1
        return f'{p}{ctr[0]}'
    plan = {'poles': clean['plan']['poles'], 'links': [dict(l, id=nid('l')) for l in clean['plan']['links']], 'buildings': []}
    for b in clean['plan']['buildings']:
        fl = []
        for f in b['floors']:
            fl.append({'id': f['id'], 'name': f['name'], **({'outdoor': True} if f['outdoor'] else {}), 'rooms': [dict(r, id=nid('r')) for r in f['rooms']], 'walls': f['walls'],
                       'items': [dict({'id': nid('i'), 'kind': it['kind'], 'x': it['x'], 'y': it['y']}, **({'ref': did[it['ref']]} if it['kind'] == 'device' else {'ref': it['ref']} if it['kind'] == 'place' else {'text': it['text']})) for it in f['items']]})
        plan['buildings'].append({'id': b['id'], 'name': b['name'], 'x': b['x'], 'y': b['y'], 'floors': fl})
    cfg['plan'] = plan
    cfg['settings'].update(title=clean['settings'].get('title') or 'Демо-сцена', publicView=True, **({'vlans': clean['settings']['vlans']} if clean['settings'].get('vlans') else {}))
    now = int(time.time())
    for d in cfg['devices'][:80]:
        r = random.Random(d['id'])
        ph = r.random() * 6.28
        for i in range(288):
            tt = now - (287 - i) * 300
            store.history.setdefault(d['id'], []).append({'t': tt, 't0': tt, 'cpu': round(8 + 22 * max(.05, (math.sin(tt / 86400 * 6.28 + ph) + 1) / 2) + r.uniform(0, 3)), 'mem': 40 + r.randint(-3, 3), 'temp': 42 + r.randint(0, 6)})
    store.add_event(None, 'Демо', 'info', f"демо-сцена «{cfg['settings']['title']}»: устройств {len(cfg['devices'])}")
    store.save()
    store.save_runtime()
    return stats(clean)


# ───────── the built-in big scene and the author's starter ─────────
def campus():
    """«Кампус»: three houses with floors and rooms, a yard, a server room, ~110 devices — made by a few loops, the same way an author could"""
    D, L, W = [], [], []
    add = lambda key, name, kind, ip, **kw: D.append(dict(kw, key=key, name=name, kind=kind, ip=ip))
    link = lambda a, p, b, **kw: L.append(dict(kw, **{'from': a, 'port': p, 'to': b}))
    add('rt', 'Магистральный роутер', 'router', '10.0.0.1', ports=8, clients=0, vendor='Edge', model='ER-8', wan=1)
    add('core', 'Ядро · коммутатор', 'switch', '10.0.0.2', ports=48, vendor='Core', model='C48-PoE')
    link('rt', 2, 'core', speed=10000, uplink=True, toPort=48)
    rooms_by_floor, items_by_floor, rack_units = {}, {}, []
    core_port = [3]
    floors = {'b1': [('f1', '1 этаж'), ('f2', '2 этаж'), ('f3', '3 этаж'), ('f4', '4 этаж')], 'b2': [('f1', '1 этаж'), ('f2', '2 этаж')], 'b3': [('f1', '1 этаж'), ('f2', '2 этаж')]}
    names = {'b1': ['Ресепшн', 'Переговорная', 'Open space А', 'Open space Б', 'Кухня', 'Тех. помещение'], 'b2': ['Приёмка', 'Склад А', 'Склад Б', 'Офис склада'],
             'b3': ['Гостиная', 'Кабинет', 'Спальня', 'Кухня']}
    place = {}                                    # (building, floor) → [(key, room index)]

    def room_of(b, f, key, idx):
        place.setdefault((b, f), []).append((key, idx))

    def floor_block(b, bi, fi, fname, n_pc, n_cam, n_iot, ip3):
        f = fi + 1
        fk = f'f{f}'
        sw = f'{b}f{f}-sw'
        add(sw, f'{["Офис", "Склад", "Дом"][bi]} · {f} эт. · коммутатор', 'switch', f'10.{bi + 1}.{f}.2', ports=24, vendor='Access', model='A24-PoE')
        link('core', core_port[0], sw, speed=1000, uplink=True, toPort=24)
        core_port[0] += 1
        port = [1]
        for a in (1, 2):
            ap = f'{b}f{f}-ap{a}'
            add(ap, f'Точка · {fname} · {a}', 'ap', f'10.{bi + 1}.{f}.{10 + a}', ports=1, clients=7 + a * 2, vendor='Wi-Fi 6', model='AP-AX')
            link(sw, port[0], ap, speed=1000, poe=14.5, toPort=1)
            room_of(b, fk, ap, (a * 2) % len(names[b]))
            port[0] += 1
            for k in range(3):
                W.append({'ap': ap, 'name': f'{["iPhone", "Galaxy", "Pixel"][k]} · {fname} · {a}{k + 1}', 'kind': 'phone', 'rssi': -45 - 6 * k - a, 'band': '5 ГГц' if k != 2 else '2.4 ГГц'})
        for k in range(n_pc):
            key = f'{b}f{f}-pc{k + 1}'
            add(key, f'{["ПК", "Рабочая станция", "Ноутбук"][k % 3]} · {fname} · {k + 1}', ['pc', 'pc', 'laptop'][k % 3], f'10.{bi + 1}.{f}.{30 + k}', vlan='Основная')
            link(sw, port[0], key, speed=1000)
            room_of(b, fk, key, (2 + k) % len(names[b]))
            port[0] += 1
        add(f'{b}f{f}-prn', f'Принтер · {fname}', 'printer', f'10.{bi + 1}.{f}.60', vlan='Основная')
        link(sw, port[0], f'{b}f{f}-prn', speed=100)
        room_of(b, fk, f'{b}f{f}-prn', 4 % len(names[b]))
        port[0] += 1
        for k in range(n_cam):
            key = f'{b}f{f}-cam{k + 1}'
            add(key, f'Камера · {fname} · {k + 1}', 'camera', f'10.{bi + 1}.{f}.{70 + k}', vlan='Камеры', status='warning' if (bi, f, k) == (1, 1, 1) else 'online')
            link(sw, port[0], key, speed=100, poe=6.5, vlan=10)
            room_of(b, fk, key, k % len(names[b]))
            port[0] += 1
        for k in range(n_iot):
            key = f'{b}f{f}-iot{k + 1}'
            add(key, f'{["Термостат", "Хаб освещения", "Датчик двери"][k % 3]} · {fname}', 'iot', f'10.{bi + 1}.{f}.{90 + k}', vlan='IoT')
            link(sw, port[0], key, speed=100, vlan=20)
            room_of(b, fk, key, (1 + k) % len(names[b]))
            port[0] += 1

    for bi, b in enumerate(('b1', 'b2', 'b3')):
        for fi, (fid, fname) in enumerate(floors[b]):
            floor_block(b, bi, fi, fname, (6, 3, 2)[bi] if fi < 4 else 2, (2, 3, 3)[bi], (2, 2, 2)[bi], fi)
    # the server room on the 1st floor of the office
    srv = [('srv-app', 'Сервер приложений', 'server', 10), ('srv-db', 'Сервер БД', 'server', 11), ('srv-vm', 'Виртуализация', 'server', 12), ('nas1', 'Хранилище', 'nas', 13), ('nvr1', 'Видеорегистратор', 'nvr', 14)]
    for k, (key, nm, kd, last) in enumerate(srv):
        add(key, nm, kd, f'10.0.0.{last}', vlan='Серверы', clients=0, **({'status': 'warning'} if key == 'srv-db' else {}))
        link('core', 40 + k, key, speed=10000 if kd == 'server' else 1000)
        room_of('b1', 'f1', key, 5)
    add('ups1', 'ИБП серверной', 'ups', '10.0.0.20')
    link('core', 46, 'ups1', speed=100)
    room_of('b1', 'f1', 'ups1', 5)
    # the yard and the remote cloud
    add('yard-sw', 'Двор · коммутатор', 'switch', '10.9.0.2', ports=8, vendor='Outdoor', model='O8-PoE')
    link('core', 47, 'yard-sw', speed=1000, uplink=True, toPort=8)
    for k in range(4):
        add(f'yard-cam{k + 1}', f'Камера · двор · {k + 1}', 'camera', f'10.9.0.{20 + k}', vlan='Камеры')
        link('yard-sw', k + 1, f'yard-cam{k + 1}', speed=100, poe=7)
    add('vps1', 'VPS · Франкфурт', 'server', '198.51.100.40', remote=True, site='Облако')
    add('vps2', 'VPS · Амстердам', 'server', '198.51.100.41', remote=True, site='Облако')
    add('site', 'Сайт компании', 'web', '203.0.113.10', remote=True, site='Облако')
    # racks
    ru = lambda name, ty, s, z, dev=None, col='#8e8e93': {'name': name, 'type': ty, 'uStart': s, 'uSize': z, 'device': dev, 'color': col}
    racks = [{'id': 'rack0', 'name': 'Серверная · стойка', 'kind': 'rack', 'totalU': 24, 'units': [
        ru('Магистральный роутер', 'router', 1, 1, 'rt', '#0a84ff'), ru('Патч-панель 48', 'patch', 2, 1), ru('Ядро', 'switch', 3, 1, 'core', '#30d158'), ru('Органайзер', 'organizer', 4, 1),
        ru('Сервер приложений', 'server', 5, 2, 'srv-app', '#5e5ce6'), ru('Сервер БД', 'server', 7, 2, 'srv-db', '#5e5ce6'), ru('Виртуализация', 'server', 9, 2, 'srv-vm', '#5e5ce6'),
        ru('Хранилище', 'nas', 11, 2, 'nas1', '#64d2ff'), ru('Видеорегистратор', 'nvr', 13, 1, 'nvr1', '#ff453a'), ru('ИБП', 'ups', 20, 3, 'ups1', '#ff9f0a')]},
        {'id': 'box2', 'name': 'Склад · щиток', 'kind': 'box', 'totalU': 1, 'units': [ru('Коммутатор склада', 'switch', 1, 1, 'b2f1-sw', '#30d158'), ru('Патч-панель', 'patch', 2, 1), ru('PoE-инжектор', 'other', 3, 1)]},
        {'id': 'box3', 'name': 'Дом · щиток', 'kind': 'box', 'totalU': 1, 'units': [ru('Коммутатор дома', 'switch', 1, 1, 'b3f1-sw', '#30d158'), ru('ИБП 650', 'ups', 2, 1)]},
        {'id': 'room1', 'name': 'Переговорная · техника', 'kind': 'place', 'totalU': 1, 'units': [ru('Точка', 'other', 1, 1, 'b1f2-ap1')]}]
    # the plan: three houses, floors, rooms; devices stand in their rooms
    colors = ['#0a84ff', '#30d158', '#bf5af2', '#ff9f0a', '#ff453a', '#64d2ff']
    buildings = []
    for bi, (b, nm, x, y) in enumerate((('b1', 'Главный офис', 40, 40), ('b2', 'Склад', 900, 330), ('b3', 'Дом директора', 40, 560))):
        fl = []
        for fi, (fid, fname) in enumerate(floors[b]):
            nrooms = len(names[b])
            cols = 3 if nrooms > 4 else 2
            rw, rh = (270 if cols == 3 else 300), 210
            rooms = [{'x': (i % cols) * rw, 'y': (i // cols) * rh, 'w': rw, 'h': rh, 'text': names[b][i], 'color': colors[(i + fi) % len(colors)]} for i in range(nrooms)]
            walls = [{'x1': 0, 'y1': 0, 'x2': cols * rw, 'y2': 0}, {'x1': cols * rw, 'y1': 0, 'x2': cols * rw, 'y2': ((nrooms + cols - 1) // cols) * rh},
                     {'x1': cols * rw, 'y1': ((nrooms + cols - 1) // cols) * rh, 'x2': 0, 'y2': ((nrooms + cols - 1) // cols) * rh}, {'x1': 0, 'y1': ((nrooms + cols - 1) // cols) * rh, 'x2': 0, 'y2': 0}]
            items, perroom = [], {}
            for key, idx in place.get((b, fid), []):
                n = perroom.get(idx, 0)
                perroom[idx] = n + 1
                items.append({'kind': 'device', 'ref': key, 'x': (idx % cols) * rw + 34 + (n % 3) * 84, 'y': (idx // cols) * rh + 56 + (n // 3) * 74})
            if (b, fid) == ('b1', 'f1'):
                items.append({'kind': 'place', 'ref': 'rack0', 'x': 5 % cols * rw + 150, 'y': 5 // cols * rh + 120})
            fl.append({'id': fid, 'name': fname, 'rooms': rooms, 'walls': walls, 'items': items})
        buildings.append({'id': b, 'name': nm, 'x': x, 'y': y, 'floors': fl})
    yard = {'id': 'yard', 'name': 'Двор и парковка', 'x': 900, 'y': 40, 'floors': [{'id': 'y1', 'name': 'Двор', 'outdoor': True, 'rooms': [{'x': 0, 'y': 0, 'w': 420, 'h': 240, 'text': 'Парковка', 'color': '#8e8e93'},
             {'x': 420, 'y': 0, 'w': 240, 'h': 240, 'text': 'Въезд', 'color': '#ff9f0a'}], 'walls': [], 'items': [{'kind': 'device', 'ref': f'yard-cam{k + 1}', 'x': 50 + k * 100, 'y': 90} for k in range(4)] + [{'kind': 'device', 'ref': 'yard-sw', 'x': 480, 'y': 150}]}]}
    buildings.append(yard)
    return {'plugin_api': PLUGIN_API, 'kind': 'scene', 'id': 'campus', 'title': 'Кампус: офис, склад и дом', 'version': '1.0.0', 'author': 'Rack Live',
            'description': 'Три здания с этажами и комнатами, двор с камерами, серверная в стойке, около ста десяти устройств с кабелями, PoE и клиентами Wi-Fi.',
            'settings': {'title': 'Кампус · демо', 'vlans': [{'vid': 1, 'name': 'Основная', 'color': '#0A84FF'}, {'vid': 10, 'name': 'Камеры', 'color': '#FF453A'},
                                                          {'vid': 20, 'name': 'IoT', 'color': '#30D158'}, {'vid': 30, 'name': 'Гости', 'color': '#BF5AF2'}]},
            'devices': D, 'links': L, 'wifi': W, 'racks': racks,
            'plan': {'poles': [{'id': 'p1', 'name': 'Столб у дороги', 'x': 700, 'y': 20}], 'buildings': buildings,
                     'links': [{'from': 'b1', 'to': 'b2', 'label': 'Оптика 10 Гбит'}, {'from': 'b1', 'to': 'b3', 'label': 'Оптика 1 Гбит'}, {'from': 'p1', 'to': 'b1', 'label': 'Воздушка от провайдера'}]}}


def starter():
    """the tiny scene given to authors as an example (2 floors, 12 devices)"""
    D = [{'key': 'rt', 'name': 'Роутер', 'kind': 'router', 'ip': '192.168.1.1', 'ports': 5}, {'key': 'sw', 'name': 'Коммутатор', 'kind': 'switch', 'ip': '192.168.1.2', 'ports': 8},
         {'key': 'ap1', 'name': 'Точка · 1 этаж', 'kind': 'ap', 'ip': '192.168.1.11', 'ports': 1}, {'key': 'ap2', 'name': 'Точка · 2 этаж', 'kind': 'ap', 'ip': '192.168.1.12', 'ports': 1},
         {'key': 'nas', 'name': 'Хранилище', 'kind': 'nas', 'ip': '192.168.1.5'}, {'key': 'cam1', 'name': 'Камера · вход', 'kind': 'camera', 'ip': '192.168.1.31'},
         {'key': 'cam2', 'name': 'Камера · двор', 'kind': 'camera', 'ip': '192.168.1.32', 'status': 'warning'}, {'key': 'tv', 'name': 'Телевизор', 'kind': 'tv', 'ip': '192.168.1.41'},
         {'key': 'pc', 'name': 'Компьютер', 'kind': 'pc', 'ip': '192.168.1.42'}, {'key': 'prn', 'name': 'Принтер', 'kind': 'printer', 'ip': '192.168.1.43'}]
    L = [{'from': 'rt', 'port': 2, 'to': 'sw', 'uplink': True, 'toPort': 8, 'speed': 1000}, {'from': 'sw', 'port': 1, 'to': 'ap1', 'poe': 12}, {'from': 'sw', 'port': 2, 'to': 'ap2', 'poe': 12},
         {'from': 'sw', 'port': 3, 'to': 'nas'}, {'from': 'sw', 'port': 4, 'to': 'cam1', 'poe': 6, 'speed': 100}, {'from': 'sw', 'port': 5, 'to': 'cam2', 'poe': 6, 'speed': 100},
         {'from': 'sw', 'port': 6, 'to': 'pc'}, {'from': 'sw', 'port': 7, 'to': 'prn', 'speed': 100}]
    return {'plugin_api': PLUGIN_API, 'kind': 'scene', 'id': 'my-home', 'title': 'Мой дом', 'version': '1.0.0', 'author': 'Ваше имя', 'description': 'Учебная сцена: двухэтажный дом, роутер, коммутатор, две точки, камеры. Замените на свою.',
            'settings': {'title': 'Мой дом · демо'}, 'devices': D, 'links': L, 'wifi': [{'ap': 'ap1', 'name': 'iPhone · Аня', 'kind': 'phone'}, {'ap': 'ap2', 'device': 'tv'}, {'ap': 'ap2', 'name': 'MacBook', 'kind': 'laptop', 'rssi': -61}],
            'racks': [{'id': 'closet', 'name': 'Шкаф в коридоре', 'kind': 'rack', 'totalU': 6, 'units': [{'name': 'Роутер', 'type': 'router', 'uStart': 1, 'uSize': 1, 'device': 'rt'},
                                                                                                    {'name': 'Коммутатор', 'type': 'switch', 'uStart': 2, 'uSize': 1, 'device': 'sw'}, {'name': 'Хранилище', 'type': 'nas', 'uStart': 3, 'uSize': 2, 'device': 'nas'}]}],
            'plan': {'buildings': [{'id': 'house', 'name': 'Дом', 'x': 40, 'y': 40, 'floors': [
                {'id': 'f1', 'name': '1 этаж', 'rooms': [{'x': 0, 'y': 0, 'w': 240, 'h': 180, 'text': 'Гостиная', 'color': '#0a84ff'}, {'x': 240, 'y': 0, 'w': 240, 'h': 180, 'text': 'Кухня', 'color': '#30d158'}],
                 'walls': [], 'items': [{'kind': 'place', 'ref': 'closet', 'x': 380, 'y': 90}, {'kind': 'device', 'ref': 'ap1', 'x': 120, 'y': 60}, {'kind': 'device', 'ref': 'cam1', 'x': 60, 'y': 140}, {'kind': 'device', 'ref': 'tv', 'x': 160, 'y': 130}]},
                {'id': 'f2', 'name': '2 этаж', 'rooms': [{'x': 0, 'y': 0, 'w': 240, 'h': 180, 'text': 'Спальня', 'color': '#bf5af2'}, {'x': 240, 'y': 0, 'w': 240, 'h': 180, 'text': 'Кабинет', 'color': '#ff9f0a'}],
                 'walls': [], 'items': [{'kind': 'device', 'ref': 'ap2', 'x': 120, 'y': 60}, {'kind': 'device', 'ref': 'pc', 'x': 340, 'y': 70}, {'kind': 'device', 'ref': 'prn', 'x': 420, 'y': 70}]}]}]}}


# ───────── applying a scene to the REAL installation: only the layout (plan, racks / boxes / rooms), never devices, logins or settings ─────────
BACKUPS = 'scene-backups'


def referenced(clean):
    """keys of the scene's devices that stand somewhere (on the plan or in a rack) — only they can be tied to a real device"""
    ks = {it['ref'] for b in clean['plan']['buildings'] for f in b['floors'] for it in f['items'] if it['kind'] == 'device'}
    ks |= {u['device'] for r in clean['racks'] for u in r['units'] if u.get('device')}
    return sorted(ks)


def suggest(sd, real):
    """the real device that is most likely this scene device: same address, else same name"""
    for d in real:
        if sd['ip'] and sd['ip'] == (d.get('host') or ''):
            return d['id']
    nm = sd['name'].casefold()
    for d in real:
        if (d.get('name') or '').casefold() == nm:
            return d['id']
    return None


def preview(clean, real):
    by = {d['key']: d for d in clean['devices']}
    items = [dict(key=k, name=by[k]['name'], kind=by[k]['kind'], ip=by[k]['ip'], suggest=suggest(by[k], real)) for k in referenced(clean)]
    st = stats(clean)
    st['placed'] = len(items)
    return {'stats': st, 'devices': items}


def _cut(cfg):
    return {'plan': json.loads(json.dumps(cfg.get('plan') or {'buildings': [], 'links': [], 'poles': []})), 'racks': json.loads(json.dumps(cfg.get('racks') or []))}


def apply_real(store, clean, mapping, mode):
    """mode 'add' appends the scene's houses and racks to the existing ones, 'replace' swaps them. A copy of what was there is saved first (undo). → counts"""
    if mode not in ('add', 'replace'):
        raise ValueError('режим: add или replace')
    real = {d['id'] for d in store.cfg['devices']}
    mp = {k: v for k, v in (mapping or {}).items() if v in real and k in {d['key'] for d in clean['devices']}}
    if len(set(mp.values())) != len(mp):
        raise ValueError('одно и то же устройство выбрано для двух мест на плане')
    now = int(time.time())
    import os
    os.makedirs(os.path.join(store.dir, BACKUPS), exist_ok=True)
    bid = time.strftime('%Y%m%d-%H%M%S', time.localtime(now))
    snap = dict(_cut(store.cfg), t=now, mode=mode, scene=clean['settings'].get('title') or '')
    with open(os.path.join(store.dir, BACKUPS, bid + '.json'), 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False)
    for old in sorted(os.listdir(os.path.join(store.dir, BACKUPS)))[:-12]:           # the last twelve are kept
        try:
            os.remove(os.path.join(store.dir, BACKUPS, old))
        except OSError:
            pass
    taken_b = {b['id'] for b in (store.cfg.get('plan') or {}).get('buildings', [])} | {x['id'] for x in store.cfg.get('racks', [])} | {p['id'] for p in (store.cfg.get('plan') or {}).get('poles', [])}
    pre = '' if mode == 'replace' else 'n' + secrets.token_hex(2) + '-'                # new ids never collide with existing ones
    rid = lambda x: pre + x
    dropped = 0
    # racks
    racks = []
    for r in clean['racks']:
        units = []
        for k, u in enumerate(r['units']):
            dev = mp.get(u['device']) if u.get('device') else None
            units.append({'id': f"u{secrets.token_hex(3)}", 'side': 'front', 'notes': '', 'name': u['name'], 'type': u['type'], 'uStart': u['uStart'], 'uSize': u['uSize'], 'color': u['color'], 'deviceId': dev})
        racks.append({'id': rid(r['id']), 'name': r['name'], 'totalU': r['totalU'], 'kind': r['kind'], 'units': units})
    # plan
    ctr = [0]

    def nid(p):
        ctr[0] += 1
        return p + secrets.token_hex(2) + str(ctr[0])
    rack_ids = {r['id'] for r in clean['racks']}
    buildings = []
    for b in clean['plan']['buildings']:
        fl = []
        for f in b['floors']:
            items = []
            for it in f['items']:
                if it['kind'] == 'device':
                    if it['ref'] in mp:
                        items.append({'id': nid('i'), 'kind': 'device', 'ref': mp[it['ref']], 'x': it['x'], 'y': it['y']})
                    else:
                        dropped += 1
                elif it['kind'] == 'place' and it['ref'] in rack_ids:
                    items.append({'id': nid('i'), 'kind': 'place', 'ref': rid(it['ref']), 'x': it['x'], 'y': it['y']})
                elif it['kind'] == 'label':
                    items.append({'id': nid('i'), 'kind': 'label', 'text': it['text'], 'x': it['x'], 'y': it['y']})
            fl.append({'id': f['id'], 'name': f['name'], **({'outdoor': True} if f['outdoor'] else {}), 'rooms': [dict(r, id=nid('r')) for r in f['rooms']], 'walls': f['walls'], 'items': items})
        buildings.append({'id': rid(b['id']), 'name': b['name'], 'x': b['x'], 'y': b['y'], 'floors': fl})
    poles = [dict(p, id=rid(p['id'])) for p in clean['plan']['poles']]
    plinks = [{'id': nid('l'), 'from': rid(l['from']), 'to': rid(l['to']), 'label': l['label']} for l in clean['plan']['links']]
    cur = store.cfg.get('plan') or {}
    if mode == 'replace':
        store.cfg['plan'] = {'buildings': buildings, 'poles': poles, 'links': plinks}
        store.cfg['racks'] = racks
    else:
        store.cfg['plan'] = {'buildings': (cur.get('buildings') or []) + buildings, 'poles': (cur.get('poles') or []) + poles, 'links': (cur.get('links') or []) + plinks}
        store.cfg['racks'] = (store.cfg.get('racks') or []) + racks
    store.save()
    store.add_event(None, 'Сцены', 'warning', f"применена сцена «{clean['settings'].get('title') or 'без названия'}» ({'добавлена к плану' if mode == 'add' else 'заменила план и шкафы'}), копия прежнего: {bid}")
    return {'backup': bid, 'buildings': len(buildings), 'racks': len(racks), 'tied': len(mp), 'dropped': dropped}


def backups(store):
    import os
    d = os.path.join(store.dir, BACKUPS)
    out = []
    for n in sorted(os.listdir(d), reverse=True) if os.path.isdir(d) else []:
        try:
            with open(os.path.join(d, n), encoding='utf-8') as f:
                j = json.load(f)
            out.append({'id': n[:-5], 't': j.get('t'), 'mode': j.get('mode'), 'scene': j.get('scene'), 'buildings': len((j.get('plan') or {}).get('buildings') or []), 'racks': len(j.get('racks') or [])})
        except (OSError, ValueError):
            pass
    return out


def undo(store, bid):
    import os
    if not re.match(r'^\d{8}-\d{6}$', str(bid or '')):
        raise ValueError('неверная копия')
    p = os.path.join(store.dir, BACKUPS, bid + '.json')
    try:
        with open(p, encoding='utf-8') as f:
            j = json.load(f)
    except (OSError, ValueError):
        raise ValueError('такой копии нет')
    store.cfg['plan'], store.cfg['racks'] = j['plan'], j['racks']
    store.save()
    store.add_event(None, 'Сцены', 'warning', f'план и шкафы возвращены, как были до применения сцены ({bid})')


def guide_text():
    L = ', '.join(sorted(KINDS))
    U = ', '.join(sorted(UNIT_TYPES))
    return f"""ИНСТРУКЦИЯ ДЛЯ НЕЙРОСЕТИ: как сделать «сцену» для Rack Live (kind: "scene", plugin_api = {PLUGIN_API})

Репозиторий проекта (исходный код, описание, инструкции): https://github.com/mikolord/racklive

ЧТО ТАКОЕ СЦЕНА
Сцена — это ОДИН файл-описание (JSON) выдуманной или спроектированной сети: устройства, кабели между ними, Wi-Fi, шкафы / щитки / комнаты с оборудованием, дома с этажами, комнатами и стенами.
Скриптов и кода в сцене НЕТ. Rack Live строго проверяет файл и умеет с ним две вещи:
  1) показать в отдельной ДЕМО-КОПИИ — выдуманные устройства «живут»: нагрузка, температура, порты, клиенты Wi-Fi, статусы; реальные устройства и настройки не затрагиваются;
  2) ПРИМЕНИТЬ К СВОЕМУ ПЛАНУ — перенести только раскладку (дома, этажи, комнаты, стены, шкафы) на настоящую установку, привязав размещённые устройства к настоящим. Перед этим Rack Live
     делает копию того, что было, и позволяет вернуть. Выдуманные устройства в настоящую установку не попадают.
Подходит для просьб: «большое демо с домами и этажами», «нарисуй план моего дома по описанию», «схема сети офиса на 40 устройств», «шкаф с оборудованием».
НЕ подходит для: установки программ на устройства (это плагин), расчётов и отчётов по устройству (это инструмент), оформления цветов и значков (это оформление).

ФАЙЛ plugin.json (в zip один этот файл, можно добавить README.md). Лимиты: архив до 1 МБ, устройств до {LIMITS['devices']}, кабелей до {LIMITS['links']}, шкафов до {LIMITS['racks']}, зданий до {LIMITS['buildings']},
этажей в здании до {LIMITS['floors']}, комнат на этаже до {LIMITS['rooms']}, элементов на этаже до {LIMITS['items']}.
{{
  "plugin_api": {PLUGIN_API}, "kind": "scene", "id": "my-office", "title": "Мой офис", "description": "До 400 знаков о том, что показывает сцена", "version": "1.0.0", "author": "Имя",
  "settings": {{"title": "Заголовок в шапке", "vlans": [{{"vid": 1, "name": "Основная", "color": "#0A84FF"}}, {{"vid": 10, "name": "Камеры", "color": "#FF453A"}}]}},
  "devices": [  // каждому устройству — уникальный key (латиница нижнего регистра, цифры, - и _, до 24 знаков)
    {{"key": "rt", "name": "Роутер", "kind": "router", "ip": "10.0.0.1", "ports": 8, "wan": 1}},
    {{"key": "sw", "name": "Коммутатор", "kind": "switch", "ip": "10.0.0.2", "ports": 24}},
    {{"key": "ap1", "name": "Точка · 1 этаж", "kind": "ap", "ip": "10.0.0.11", "ports": 1, "clients": 8}},
    {{"key": "cam1", "name": "Камера · вход", "kind": "camera", "ip": "10.0.0.31", "status": "warning"}},
    {{"key": "vps", "name": "VPS", "kind": "server", "ip": "198.51.100.40", "remote": true, "site": "Облако"}}
  ],
  "links": [    // кабели: у from нужен порт port (1..ports у from); to — куда подключено; uplink — порт «вверх» у to; toPort — порт на стороне to
    {{"from": "rt", "port": 2, "to": "sw", "toPort": 24, "uplink": true, "speed": 1000}},
    {{"from": "sw", "port": 1, "to": "ap1", "toPort": 1, "poe": 12}},
    {{"from": "sw", "port": 2, "to": "cam1", "speed": 100, "poe": 6}}
  ],
  "wifi": [     // кто подключён по Wi-Fi к точке (ap — устройство вида ap или router)
    {{"ap": "ap1", "name": "iPhone · Аня", "kind": "phone", "rssi": -52, "band": "5 ГГц"}},
    {{"ap": "ap1", "device": "cam1"}}
  ],
  "racks": [    // шкафы (rack, юниты по U), щитки (box) и комнаты/места (place); device — key устройства, стоящего в юните
    {{"id": "rack0", "name": "Серверная", "kind": "rack", "totalU": 12, "units": [
      {{"name": "Роутер", "type": "router", "uStart": 1, "uSize": 1, "device": "rt"}}, {{"name": "Коммутатор", "type": "switch", "uStart": 2, "uSize": 1, "device": "sw"}}]}}
  ],
  "plan": {{
    "buildings": [{{"id": "house", "name": "Дом", "x": 40, "y": 40, "floors": [
      {{"id": "f1", "name": "1 этаж", "rooms": [{{"x": 0, "y": 0, "w": 260, "h": 200, "text": "Гостиная", "color": "#0a84ff"}}],
        "walls": [{{"x1": 0, "y1": 0, "x2": 260, "y2": 0}}],
        "items": [{{"kind": "place", "ref": "rack0", "x": 200, "y": 120}}, {{"kind": "device", "ref": "ap1", "x": 60, "y": 60}}, {{"kind": "label", "text": "Вход", "x": 10, "y": 180}}]}}]}}],
    "poles": [{{"id": "p1", "name": "Столб", "x": 700, "y": 20}}],
    "links": [{{"from": "p1", "to": "house", "label": "Воздушка от провайдера"}}]
  }}
}}

ПРАВИЛА (проверка строгая; при ошибке Rack Live покажет, какая именно строка не подошла):
  • kind устройства — один из: {L}. Роутер нужен хотя бы один (иначе на карте не будет «Интернета»).
  • ports — число портов (0–96). Кабель можно провести только от порта, который есть. Один порт — один кабель. Все ключи в links / wifi / racks / plan должны быть из devices.
  • Иерархия карты строится из кабелей: роутер → коммутатор ядра → коммутаторы этажей (uplink: true) → точки, камеры, компьютеры. Сначала описывайте роутер и ядро, потом остальное.
  • status: online (по умолчанию), warning (требует внимания) или offline (нет связи). remote: true — удалённое устройство (вне здания), site — название площадки.
  • clients у точки (и роутера) — сколько «случайных» клиентов Wi-Fi добавить; wifi — конкретные. speed: 10, 100, 1000, 2500, 5000 или 10000. poe — ватты на порту (0–120).
  • rack: totalU 1–60, юнит {{"type": один из {U}, "uStart", "uSize" 1–8}} и должен помещаться в стойку; box / place — без жёстких U.
  • plan: координаты x, y в пикселях (-2000…6000), комната w и h 10…3000. Здания размещайте так, чтобы они не накладывались (x, y — левый верхний угол карточки на обзоре территории).
    Внутри этажа комнаты складывайте сеткой (например по 260×200), а устройства расставляйте ВНУТРИ комнат с шагом 80–90 px, чтобы подписи не слипались.
  • id шкафов, зданий, этажей, столбов — латиница нижнего регистра, цифры, - и _, без повторов.
  • Цвет только в виде #RRGGBB. Любые лишние поля игнорируются.

ЧТО СДЕЛАТЬ, ЕСЛИ ПРОСЯТ «ОГРОМНОЕ»: используйте циклы в голове, но результат — один обычный JSON без пропусков: сгенерируйте устройства по этажам группами (коммутатор этажа, 2 точки, ПК, принтер, камеры, умные устройства),
свяжите их кабелями с коммутатором этажа, а коммутаторы этажей — с ядром. Для 100+ устройств используйте clients у точек вместо перечисления каждого телефона.

КАК ПРОВЕРИТЬ: Инструменты → Демо-сцены и планы → «Загрузить .zip». Rack Live покажет ошибки (исправьте и соберите заново) или добавит сцену; затем «Посмотреть в демо» или «Применить к моему плану».
Когда отдаёте результат человеку: приложите zip и коротко опишите, что в сцене и как её смотреть.
"""

