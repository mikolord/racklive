"""A router in lockout is silent: Rack Live must not wait out timeouts on it, and it must not hold up the plugins of other devices. No network."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from rackd import remote
from rackd.drivers import load_all, REGISTRY
from rackd.drivers import keenetic as kn
load_all()

FAILS = 0
def check(name, ok, info=''):
    global FAILS
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok else f'  {info}'))
    FAILS += 0 if ok else 1

drv = REGISTRY['keenetic']
calls = {'web': 0, 'local': 0}
real_reach, real_local = kn.web_reachable, drv._local_rci
kn.web_reachable = lambda base: (calls.__setitem__('web', calls['web'] + 1), False)[1]
type(drv)._local_rci = lambda self, cfg: (calls.__setitem__('local', calls['local'] + 1), ('get', 'cli'))[1]
cfg = {'host': '192.0.2.1', 'username': 'admin', 'password': 'x', 'entwarePassword': 'y'}
t = time.time()
got = drv._session(cfg)
check('silent web with Entware: straight to Entware, no long wait', got == ('get', 'cli') and calls == {'web': 2, 'local': 1} and time.time() - t < 1, calls)
drv._session(cfg)
check('the next request does not even knock for a while', calls == {'web': 2, 'local': 2}, calls)
kn.NO_WEB['192.0.2.1'] = time.time() - 1
drv._session(cfg)
check('after a while the web is tried again', calls['web'] == 4, calls)
kn.NO_WEB.clear()
try:
    drv._session({'host': '192.0.2.2', 'username': 'admin', 'password': 'x'})
    check('without Entware the error is immediate and explains', False)
except kn.DriverError as e:
    check('without Entware the error is immediate and explains', '15 минут' in str(e), e)
check('nothing is remembered for a router without Entware', '192.0.2.2' not in kn.NO_WEB)
kn.web_reachable = real_reach
s = __import__('socket').socket(); s.bind(('127.0.0.1', 0)); s.listen(1); port = s.getsockname()[1]
check('reachability: an open port', kn.web_reachable(f'http://127.0.0.1:{port}'))
s.close()
check('reachability: a closed port', not kn.web_reachable(f'http://127.0.0.1:{port}'))

class S: pass
app = S(); app.store = S()
app.store.cfg = {'devices': [{'id': 'slow', 'name': 'Медленный', 'driver': 'keenetic'}, {'id': 'bad', 'name': 'С ошибкой', 'driver': 'keenetic'}, {'id': 'ok', 'name': 'Рабочий', 'driver': 'keenetic'},
                             {'id': 'off', 'name': 'Выключен', 'driver': 'keenetic', 'enabled': False}]}
def hubs(self, k):
    if k['id'] == 'slow':
        time.sleep(30)
    if k['id'] == 'bad':
        raise RuntimeError('сломан')
    return [{'iface': 'Wireguard0', 'used': [1], 'peers': [], 'domain': 'x', 'wan': 'y', 'name': 'WG'}]
type(drv).wg_hubs = hubs
remote.HUBS_WAIT = .5
t = time.time()
out = remote.hubs(app)
check('a slow router does not hold up the card', time.time() - t < 2, time.time() - t)
check('each router has its own line, in order', [x['device'] for x in out] == ['slow', 'bad', 'ok'], out)
check('a slow one and a broken one say so', 'вовремя' in out[0]['error'] and 'сломан' in out[1]['error'])
check('the working one is usable', out[2]['id'] == 'ok:Wireguard0' and out[2]['used'] == 1, out[2])

al = remote.allowed_for('172.16.6.0/24', '192.168.1.3')
check('the home network may reach the router, so the web interface opens from a computer too', al == ['172.16.6.0/24', '192.168.1.0/24'], al)
check('a public source stays one address', remote.allowed_for('172.16.6.0/24', '8.8.8.8') == ['172.16.6.0/24', '8.8.8.8/32'])     # documentation addresses count as private in Python
check('a source inside the tunnel adds nothing', remote.allowed_for('172.16.6.0/24', '172.16.6.5') == ['172.16.6.0/24'])
script = remote.apply_script('172.16.6.13', 'A' * 43 + '=', '203.0.113.5', 41495, 'x.test', al)
check('the web interface is open through the tunnel', "dest_port='22 80 443'" in script)
check('no forwarding between the tunnel and its networks', 'firewall.rl_wgz.forward=REJECT' in script and 'forwarding' not in script.replace('NO forwardings', ''))
check('home routes stay in the tunnel\'s own table', f'ip4table={remote.TABLE}' in script)

print('\nВСЁ OK' if not FAILS else f'\nОШИБОК: {FAILS}')
sys.exit(1 if FAILS else 0)
