"""Power chain: mains → (outlet block) → UPS → (outlet block) → devices.

One «row of load» describes what sits in an outlet — in an outlet block (unit type pdu: unit.power.ports) and in a UPS socket
(device ups: loads). A row is one of
  dev   — a device from the list,
  unit  — a unit of the rack without a device (ONT, PoE injector…),
  pdu   — another outlet block plugged in here (its whole load counts),
  label — a free line the user named («Камеры»),
plus the draw as v (volts) × a (amps) or w (watts). Without own numbers a device is estimated by its type (PoE, disks…).
A UPS says which block feeds it: powerFrom (unit id) + powerFromOutlet. A block can never be fed by something it feeds itself.
"""
UPS_IDLE_W = 5                                       # the UPS itself, besides what it feeds


def num(v):
    try:
        return float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def spec_w(spec):
    """watts of {v, a, w}: w wins, else volts × amps"""
    spec = spec or {}
    w = num(spec.get('w'))
    if w:
        return w
    v, a = num(spec.get('v')), num(spec.get('a'))
    return v * a if v and a else 0


def spec_text(spec):
    spec = spec or {}
    v, a, w = num(spec.get('v')), num(spec.get('a')), num(spec.get('w'))
    if v and a and not w:
        return f'{v:g} В × {a:g} А'
    return f'{w:g} Вт' if w else ''


class Net:
    """what the calculation needs: units by id, devices by id, latest states"""
    def __init__(self, racks, devices, states):
        self.units = {u['id']: dict(u, rackName=r.get('name')) for r in racks or [] for u in r.get('units') or []}
        self.devices = {d['id']: d for d in devices or []}
        self.states = states or {}

    def pdus(self):
        return {i: u for i, u in self.units.items() if u.get('type') == 'pdu'}


REMOTE_UPS = 'ИБП стоит рядом с оборудованием, поэтому не может быть удалённым устройством — выберите «Локальное».'


def is_remote(d):
    return (d or {}).get('location') == 'remote'


def plugged_where(devices, racks, did):
    """where a device is plugged in: [«ИБП X», «блок розеток Y»] — used to refuse making it remote"""
    out = []
    for d in devices or []:
        if d.get('driver') == 'ups' and any(isinstance(r, dict) and r.get('dev') == did for r in d.get('loads') or []):
            out.append(f"ИБП «{d.get('name')}»")
    for r in racks or []:
        for u in r.get('units') or []:
            if u.get('type') == 'pdu' and any((p or {}).get('dev') == did for p in ((u.get('power') or {}).get('ports') or {}).values()):
                out.append(f"блок розеток «{u.get('name')}»")
    return out


def placed_where(racks, did):
    """places (rack / box / room) whose units hold this device: [«шкаф X»] — a remote device is never placed in one"""
    return [f"«{r.get('name')}»" for r in racks or []
            if any(did in ([x for x in (u.get('deviceIds') or []) if x] or [u.get('deviceId')]) for u in r.get('units') or [])]


def remote_placed(racks, devices):
    """→ (device name, place name) of the first remote device found in a place, or None"""
    remote = {d['id']: d.get('name') for d in devices or [] if is_remote(d)}
    for r in racks or []:
        for u in r.get('units') or []:
            for i in [x for x in (u.get('deviceIds') or []) if x] or [u.get('deviceId')]:
                if i in remote:
                    return remote[i], r.get('name')
    return None


def downstream(net, pdu_ids):
    """every outlet block reachable from these ones through the outlets (themselves included)"""
    out, todo = set(), list(pdu_ids)
    while todo:
        i = todo.pop()
        if i in out or i not in net.units:
            continue
        out.add(i)
        for p in ((net.units[i].get('power') or {}).get('ports') or {}).values():
            if (p or {}).get('pdu'):
                todo.append(p['pdu'])
    return out


def ups_down(net, d):
    """outlet blocks below a UPS (plugged into its sockets, and what is plugged into those)"""
    rows = [r for r in d.get('loads') or [] if isinstance(r, dict) and r.get('pdu')]
    return downstream(net, [r['pdu'] for r in rows])


def ups_input_w(net, d):
    """what a UPS takes from its supplier: its load, over the efficiency, plus its own idle draw"""
    u = (net.states.get(d['id']) or {}).get('ups') or {}
    load = u.get('loadW')
    if load is None:
        return 0
    eff = (u.get('efficiency') or 85) / 100
    return round(load / max(.4, eff) + UPS_IDLE_W)


def row_item(net, r, outlet, seen):
    """→ item {outlet, kind, name, w, src, …} for one row of load, or None when the row is empty"""
    from .drivers.ups import device_draw
    own = spec_w(r)
    if r.get('pdu') and r['pdu'] in net.units:
        if r['pdu'] in seen:
            return None
        sub = load(net, r['pdu'], seen)
        return {'outlet': outlet, 'kind': 'pdu', 'name': net.units[r['pdu']].get('name') or 'Блок розеток', 'unit': r['pdu'], 'w': sub['w'],
                'src': f"блок розеток · занято {len(sub['items'])}", 'children': sub['items']}
    if r.get('unit') in net.units:
        u = net.units[r['unit']]
        spec = r if own else (u.get('pwr') or {})
        w = spec_w(spec)
        return {'outlet': outlet, 'kind': u.get('type') or 'other', 'name': u.get('name'), 'unit': u['id'], 'w': round(w),
                'src': spec_text(spec) or 'потребление не указано', 'missing': not w}
    if r.get('dev') in net.devices and not is_remote(net.devices[r['dev']]):          # a remote device is never on a local socket
        d = net.devices[r['dev']]
        if d.get('driver') == 'ups':
            w, src = ups_input_w(net, d), 'ИБП: нагрузка + собственное потребление'
        elif own:
            w, src = own, spec_text(r) or 'указано вручную'
        else:
            w, src = device_draw(d, net.states.get(d['id']))
        return {'outlet': outlet, 'kind': d.get('kind') or 'other', 'name': d.get('name'), 'id': d['id'], 'w': round(w), 'src': src,
                'status': (net.states.get(d['id']) or {}).get('status')}
    if r.get('label') or own:
        return {'outlet': outlet, 'kind': 'other', 'name': r.get('label') or 'Нагрузка', 'w': round(own), 'src': spec_text(r) or 'указано вручную',
                'missing': not own}
    return None


def load(net, uid, seen=None):
    """→ {w, items: [...]} — everything plugged into outlet block `uid`"""
    seen = set(seen or ()) | {uid}
    unit = net.units.get(uid) or {}
    ports = (unit.get('power') or {}).get('ports') or {}
    items, listed = [], set()
    for n in sorted(ports, key=lambda k: int(k) if str(k).isdigit() else 0):
        it = row_item(net, ports[n] or {}, str(n), seen)
        if it:
            items.append(it)
            listed.add(it.get('id') or it.get('unit'))
    # plugged in from the other side: a UPS that says «I am fed from this block, outlet N» (never one this block feeds itself)
    for d in net.devices.values():
        if d.get('driver') == 'ups' and d.get('powerFrom') == uid and d['id'] not in listed and uid not in ups_down(net, d):
            items.append({'outlet': str(d.get('powerFromOutlet') or ''), 'kind': 'ups', 'name': d.get('name'), 'id': d['id'], 'w': ups_input_w(net, d),
                          'src': 'ИБП: нагрузка + собственное потребление', 'status': (net.states.get(d['id']) or {}).get('status')})
    return {'w': round(sum(i['w'] for i in items)), 'items': items}


def feeders(net, uid):
    """who feeds outlet block `uid`: [{kind: 'ups'|'pdu', name, outlet}] (found on the supplier's side)"""
    out = []
    for d in net.devices.values():
        if d.get('driver') != 'ups':
            continue
        for r in d.get('loads') or []:
            if isinstance(r, dict) and r.get('pdu') == uid:
                out.append({'kind': 'ups', 'name': d.get('name'), 'id': d['id'], 'outlet': str(r.get('outlet') or '')})
    for pid, u in net.pdus().items():
        for n, p in ((u.get('power') or {}).get('ports') or {}).items():
            if (p or {}).get('pdu') == uid:
                out.append({'kind': 'pdu', 'name': u.get('name'), 'unit': pid, 'outlet': str(n)})
    return out


def annotate(racks, devices, states):
    """racks for the interface: every outlet block gets .powerLoad {w, items, feeders}"""
    net = Net(racks, devices, states)
    out = []
    for r in racks or []:
        units = []
        for u in r.get('units') or []:
            if u.get('type') == 'pdu':
                u = dict(u, powerLoad=dict(load(net, u['id']), feeders=feeders(net, u['id'])))
            units.append(u)
        out.append(dict(r, units=units))
    return out
