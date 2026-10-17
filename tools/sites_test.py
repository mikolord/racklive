"""Remote sites: key format, ingest rules (what is kept, what is thrown away, nothing from the remote LAN can be taken for an address here), the collector payload. Run: python tools/sites_test.py"""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import sites, collector
from rackd.store import Store

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


class App:
    def __init__(self, td):
        self.store = Store(td)
        self.states = {}
        self.applied = []

    def apply_state(self, d, st):
        self.states[d['id']] = st
        self.applied.append(d['id'])


td = tempfile.mkdtemp()
app = App(td)
S = sites.Sites(app)

# key
k = sites.encode_key('https://rack.example.com', 'abcdefghijklmnop12345')
ok('ключ площадки: туда и обратно', sites.decode_key(k) == ('https://rack.example.com', 'abcdefghijklmnop12345'), k)
for bad in ('', 'RL1.', 'RL1.@@@', 'abc', 'RL1.' + sites.base64.urlsafe_b64encode(b'{"u":"ftp://x","t":"abcdefghijklmnop12345"}').decode(), 'RL1.' + sites.base64.urlsafe_b64encode(b'{"u":"https://x","t":"short"}').decode()):
    try:
        sites.decode_key(bad); ok('чужой ключ отклонён: ' + bad[:20], False)
    except ValueError:
        ok('чужой ключ отклонён: ' + bad[:20], True)

s = S.create('Дача')
ok('площадка создана, ключ есть', s['token'] and len(s['token']) >= 24)
try:
    S.create('дача'); ok('повтор названия отклонён', False)
except ValueError:
    ok('повтор названия отклонён', True)

body = {'version': '2.6.1', 'devices': [
    {'key': 'r1', 'name': 'Роутер дачи', 'driver': 'keenetic', 'kind': 'router', 'state': {'status': 'online', 'summary': {'ip': '192.168.1.1', 'mac': 'aa:bb:cc:dd:ee:ff', 'macs': ['aa:bb:cc:dd:ee:01'], 'cpu': 9},
        'clients': [{'mac': 'x'}], 'children': [{'mac': 'y'}], 'password': 'SECRET', 'clientsCount': 7,
        'ports': [{'n': 1, 'link': True, 'peers': [{'mac': 'aa:aa:aa:aa:aa:aa'}]}]}},
    {'key': '../../evil', 'name': 'Камера', 'driver': 'ping', 'kind': 'weird-kind', 'state': {'status': 'online', 'summary': {}}},
    {'name': 'без ключа', 'state': {}},
    {'key': 'bad', 'state': 'not a dict'}]}
try:
    S.ingest('wrong-token', body, '1.2.3.4'); ok('чужой ключ не принят', False)
except PermissionError:
    ok('чужой ключ не принят', True)
try:
    S.ingest('', body, '1.2.3.4'); ok('пустой ключ не принят', False)
except PermissionError:
    ok('пустой ключ не принят', True)
res = S.ingest(s['token'], body, '1.2.3.4')
devs = {d['siteKey']: d for d in app.store.cfg['devices'] if d.get('siteId') == s['id']}
ok('создано два устройства (без ключа и не-словарь пропущены)', set(devs) == {'r1', 'evil'} and res['devices'] == 2, list(devs))
r1 = devs['r1']; st = app.states[r1['id']]
ok('тип драйвера site_node, удалённое, с названием площадки', r1['driver'] == 'site_node' and r1['location'] == 'remote' and r1['siteName'] == 'Дача' and r1['host'] == '')
ok('чужого адреса нет: IP площадки не похож на IP этой сети', 'Дача' in st['summary']['ip'] and not st['summary']['ip'].startswith('192.'), st['summary'])
ok('MAC площадки выброшены', 'mac' not in st['summary'] and 'macs' not in st['summary'])
ok('клиенты, дочерние точки и лишние поля выброшены', 'clients' not in st and 'children' not in st and 'password' not in st and 'SECRET' not in json.dumps(st))
ok('число клиентов осталось в разделах', any(r == ['Клиентов', 7] for sec in st['sections'] for r in sec['rows']))
ok('у портов нет списков MAC', st['ports'][0]['peers'] == [])
ok('неизвестный вид заменён на other, ключ очищен', devs['evil']['kind'] == 'other' and '/' not in devs['evil']['siteKey'])
pub = S.public()[0]
ok('в списке: устройств 2, на связи, без ключа', pub['devices'] == 2 and pub['alive'] and 'token' not in pub, pub)

# a device gone from the remote place is gone here
S.ingest(s['token'], {'devices': [body['devices'][0]]}, '1.2.3.4')
ok('исчезнувшее устройство убрано', len([d for d in app.store.cfg['devices'] if d.get('siteId') == s['id']]) == 1)
try:
    S.ingest(s['token'], {'devices': 'no'}, '1.2.3.4'); ok('плохой список отклонён', False)
except ValueError:
    ok('плохой список отклонён', True)
try:
    S.ingest(s['token'], {'devices': [{'key': f'k{i}', 'state': {}} for i in range(300)]}, '1.2.3.4'); ok('больше 200 устройств отклонено', False)
except ValueError:
    ok('больше 200 устройств отклонено', True)

# the collector builds its payload from OWN devices, never from other sites, never with secrets
app2 = App(tempfile.mkdtemp())
app2.store.cfg['devices'] = [{'id': 'a', 'name': 'Роутер', 'driver': 'keenetic', 'kind': 'router', 'password': 'p-secret', 'enabled': True},
                             {'id': 'b', 'name': 'Чужое', 'driver': 'site_node', 'enabled': True}, {'id': 'c', 'name': 'Выключено', 'driver': 'ping', 'enabled': False}, {'id': 'd', 'name': 'Не опрошено', 'driver': 'ping'}]
app2.states = {'a': {'status': 'online', 'summary': {'ip': '10.0.0.1'}, 'clients': [1, 2, 3], 'token': 'nope', 'ports': []}, 'b': {'status': 'online'}, 'c': {'status': 'online'}}
c = collector.Collector(app2, '2.6.1')
pl = c.payload()
ok('сборщик отправляет только свои включённые и опрошенные', [x['key'] for x in pl['devices']] == ['a'], pl)
ok('в отправке нет паролей и клиентов, есть их число', 'p-secret' not in json.dumps(pl) and 'nope' not in json.dumps(pl) and pl['devices'][0]['state']['clientsCount'] == 3)
try:
    c.configure('garbage', True); ok('сборщик не принимает чужой ключ', False)
except ValueError:
    ok('сборщик не принимает чужой ключ', True)
c.configure(k, True, False)
ok('ключ сохранён, в публичных данных его нет', c.cfg()['url'] == 'https://rack.example.com' and 'token' not in json.dumps(c.public()) and c.public()['keySet'])
try:
    c2 = collector.Collector(App(tempfile.mkdtemp())); c2.configure(None, True); ok('включить без ключа нельзя', False)
except ValueError:
    ok('включить без ключа нельзя', True)

# removing a site removes its devices
S.remove(s['id'])
ok('площадка удалена вместе с устройствами', not S.items and not [d for d in app.store.cfg['devices'] if d.get('siteId')])

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
