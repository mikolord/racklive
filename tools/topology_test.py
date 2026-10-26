"""The map shows what a secondary router (OpenWrt with a captive portal) knows: its DHCP clients hang under it. Run: python tools/topology_test.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import topology

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


devices = [{'id': 'kn', 'name': 'Keenetic', 'driver': 'keenetic', 'host': '192.168.1.1'}, {'id': 'ow', 'name': 'OpenWrt Captive', 'driver': 'openwrt', 'host': '192.168.8.10'}]
mk = lambda i: {'mac': f'aa:bb:cc:00:00:{i:02x}', 'ip': f'10.255.0.{i}', 'name': f'guest-{i:02d}', 'segment': 'Captive', 'online': True, 'kind': 'phone'}


def states(n_guests, extra_main=()):
    return {'kn': {'status': 'online', 'summary': {'ip': '192.168.1.1', 'macs': ['00:11:22:33:44:55']}, 'ports': [{'n': 1, 'link': True, 'peers': []}, {'n': 3, 'link': True, 'peers': []}], 'clients': list(extra_main)},
            'ow': {'status': 'online', 'summary': {'ip': '192.168.8.10', 'macs': ['00:11:22:33:44:66']}, 'ports': [{'n': 1, 'link': True, 'peers': []}], 'clients': [mk(i) for i in range(1, n_guests + 1)]}}


for n, label in ((3, 'три гостя'), (30, '30 гостей')):
    t = topology.build(devices, states(n), [], [], True, {}, {})
    nodes = {x['id']: x for x in t['nodes']}
    guests = [x for x in t['nodes'] if x.get('client') and str(x.get('label', '')).startswith('guest-')]
    edges = {(e['source'], e['target']) for e in t['edges']}
    ok(f'{label}: клиенты OpenWrt на карте под своим роутером', len(guests) == min(n, 20) and all(('d:ow', g['id']) in edges for g in guests), len(guests))
    if n > 20:
        more = nodes.get('x:ow:leases')
        ok('остальные — одна карточка «ещё N»', more and '10' in more['label'], more)

# a client the main router lists too (without a place to draw it) still appears under the OpenWrt
both = states(2, [dict(mk(1), src='kn')])
t = topology.build(devices, both, [], [], True, {}, {})
ok('клиент, известный обоим роутерам, не теряется', any(x['id'] == 'h:aa:bb:cc:00:00:01' for x in t['nodes']))
# not twice
ok('каждый клиент один раз', len([x for x in t['nodes'] if x['id'] == 'h:aa:bb:cc:00:00:01']) == 1)
# nobody shown when clients are switched off
t = topology.build(devices, states(3), [], [], False, {}, {})
ok('при выключенных клиентах их нет', not [x for x in t['nodes'] if str(x.get('label', '')).startswith('guest-')])

# remote devices (a VPS, a router on another site) hang straight under the internet — each by its own line, never under each other or under a home device
rdev = devices + [
    {'id': 'vps', 'name': 'VPS Германия', 'driver': 'ssh', 'host': '203.0.113.40', 'location': 'remote'},
    {'id': 'rr1', 'name': 'Роутер Виктор', 'driver': 'openwrt', 'host': '192.168.1.53', 'location': 'remote'},     # its address is in the HOME network (still at home before moving)
    {'id': 'rr2', 'name': 'Роутер Кристина', 'driver': 'openwrt', 'host': '172.20.5.1', 'location': 'remote'},
]
st = states(2, [{'mac': 'de:ad:be:ef:00:53', 'ip': '192.168.1.53', 'name': 'Виктор', 'port': '3', 'online': True}])
st['rr1'] = {'status': 'online', 'summary': {'ip': '192.168.1.53', 'mac': 'de:ad:be:ef:00:53'}, 'ports': [{'n': 1, 'link': True, 'peers': []}], 'clients': []}
st['rr2'] = {'status': 'online', 'summary': {'ip': '172.20.5.1'}, 'ports': [{'n': 1, 'link': True, 'peers': []}], 'clients': [mk(40)]}
t = topology.build(rdev, st, [], [], True, {}, {})
parent = {e['target']: e['source'] for e in t['edges'] if not e.get('extra') and not e.get('manual')}
for did in ('vps', 'rr1', 'rr2'):
    ok(f'удалённое {did}: прямо от «Интернета»', parent.get('d:' + did) == 'inet', parent.get('d:' + did))
ok('у «Интернета» нет цепочки: удалённые не висят друг на друге', not any(parent.get('d:' + b) == 'd:' + a for a in ('vps', 'rr1', 'rr2') for b in ('vps', 'rr1', 'rr2')))
ok('клиенты удалённого роутера — под ним', parent.get('h:aa:bb:cc:00:00:28') == 'd:rr2', parent.get('h:aa:bb:cc:00:00:28'))
ok('домашние устройства по-прежнему от главного роутера', parent.get('d:ow') in ('d:kn', None) and parent.get('d:kn') == 'inet', (parent.get('d:ow'), parent.get('d:kn')))

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
