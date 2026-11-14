"""«Пароли» (rackd/vault.py): entries, edit, JSON / CSV export and import back. Run: python tools/vault_test.py → GOOD"""
import copy, csv, io, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import vault


class Drv:
    def __init__(self, id_, title, fields=()):
        self.id, self.title, self.kind, self.fields = id_, title, 'router', list(fields)


REG = {'openwrt': Drv('openwrt', 'OpenWrt'), 'keenetic': Drv('keenetic', 'Keenetic', [{'name': 'entwarePassword', 'label': 'Entware: пароль', 'secret': True}]),
       'ssh': Drv('ssh', 'Сервер (SSH)'), 'ping': Drv('ping', 'Пинг')}
DEVS = [
    {'id': 'd1', 'name': 'Роутер дом', 'driver': 'keenetic', 'host': '192.0.2.1', 'username': 'admin', 'password': 'p,"1', 'entwarePassword': 'ent'},
    {'id': 'd2', 'name': '🇩🇪 VPS', 'driver': 'ssh', 'host': '203.0.113.5', 'username': 'root', 'privateKey': '-----BEGIN KEY-----\nabc\n-----END KEY-----\n',
     'panelInfo': {'3xui': {'url': 'https://203.0.113.5:2222/x', 'user': 'u', 'password': 'pp'}}},
    {'id': 'd3', 'name': 'Пинг', 'driver': 'ping', 'host': '192.0.2.9'},
    {'id': 'd4', 'name': 'Openwrt', 'driver': 'openwrt', 'host': '192.0.2.4', 'webUrl': 'http://192.0.2.4', 'username': 'root', 'password': 'w'},
]
ok = True


def check(cond, what):
    global ok
    if not cond:
        ok = False
        print('FAIL', what)


es = vault.entries(DEVS, REG)
check([e['id'] for e in es] == ['d4', 'd1', 'd2'], 'only devices with secrets, sorted by name: ' + str([e['id'] for e in es]))
d1 = next(e for e in es if e['id'] == 'd1')
check({f['key'] for f in d1['fields']} == {'username', 'password', 'entwarePassword'}, 'd1 fields')
check(next(f for f in d1['fields'] if f['key'] == 'entwarePassword')['label'] == 'Entware: пароль', 'label from the driver')
d2 = next(e for e in es if e['id'] == 'd2')
check(d2['panels'] and d2['panels'][0]['password'] == 'pp', 'panel credentials listed')

# edit: change, remove, ignore unknown / agent token
d = copy.deepcopy(DEVS[0])
ch = vault.update(d, {'password': 'new', 'entwarePassword': '', 'agentToken': 'x', 'host': 'evil', 'username': 'admin'})
check(sorted(ch) == ['entwarePassword', 'password'] and d['password'] == 'new' and 'entwarePassword' not in d and d['host'] == '192.0.2.1' and 'agentToken' not in d, 'update ' + str(ch))

# JSON round trip into devices with the secrets removed
js = vault.export_json(DEVS, REG)
bare = [{k: v for k, v in x.items() if k not in vault.SECRET_FIELDS + ('username',)} for x in copy.deepcopy(DEVS)]
r = vault.apply_import(bare, vault.parse(js))
check(bare[0]['password'] == 'p,"1' and bare[0]['entwarePassword'] == 'ent' and bare[1]['privateKey'].startswith('-----BEGIN'), 'json import restores secrets')
check(len(r['updated']) == 3 and not r['unmatched'], 'json import result ' + str(r))

# CSV: iOS-style header, quoting, marks; round trip
cs = vault.export_csv(DEVS, REG)
rows = list(csv.reader(io.StringIO(cs)))
check(rows[0] == ['Title', 'URL', 'Username', 'Password', 'Notes', 'OTPAuth'], 'csv header')
check(any(r_[3] == 'p,"1' and r_[1] == 'http://192.0.2.1' for r_ in rows), 'csv quoting / url')
check(any('панель' in r_[0] for r_ in rows), 'panel row')
bare = [{k: v for k, v in x.items() if k not in vault.SECRET_FIELDS + ('username',)} for x in copy.deepcopy(DEVS)]
r = vault.apply_import(bare, vault.parse('﻿' + cs))
check(bare[0]['password'] == 'p,"1' and bare[0]['username'] == 'admin' and bare[0]['entwarePassword'] == 'ent', 'csv import d1 ' + str(bare[0]))
check(bare[1]['privateKey'].endswith('-----END KEY-----\n') and bare[3]['password'] == 'w', 'csv import key / d4')
check(bare[1].get('panelInfo', {}).get('3xui', {}).get('password') == 'pp', 'panel untouched')

# foreign CSV (Chrome): matched by address, unknown rows reported, never creates devices
foreign = 'name,url,username,password,note\nX,https://192.0.2.4/cgi-bin/luci,root,zz,\nY,https://198.51.100.7,a,b,\n'
devs = copy.deepcopy(DEVS)
r = vault.apply_import(devs, vault.parse(foreign))
check(devs[3]['password'] == 'zz' and r['unmatched'] == ['Y'] and len(devs) == 4, 'foreign csv ' + str(r))

# a full Rack Live backup is accepted too
full = json.dumps({'version': 2, 'devices': [{'id': 'd4', 'driver': 'openwrt', 'password': 'from-backup'}]})
devs = copy.deepcopy(DEVS)
vault.apply_import(devs, vault.parse(full))
check(devs[3]['password'] == 'from-backup', 'full backup import')

for bad in ('', 'hello', '{"a":1}', 'a,b\n1,2\n'):
    try:
        vault.parse(bad)
        check(False, 'bad file accepted: ' + repr(bad))
    except ValueError:
        pass

t = vault.Tickets()
k = t.new()
check(t.ok(k) and not t.ok('nope'), 'ticket')
t.t[k] = time.time() - 1
check(not t.ok(k), 'ticket expires')

print('GOOD' if ok else 'BAD')
sys.exit(0 if ok else 1)
