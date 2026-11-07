"""Link parser, Xray configs and the safety of the XKeen scenario. No router needed: the driver runs against stubs."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import keenetic_vless as kv
from rackd.drivers import keenetic
from rackd.util import DriverError

fails = 0
def check(name, ok, extra=''):
    global fails
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else f'  {extra}'))
    fails += 0 if ok else 1

U = '1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed'
XH = f'vless://{U}@203.0.113.5:2053?type=xhttp&encryption=none&security=tls&sni=203.0.113.5&fp=chrome&alpn=h2,http/1.1&path=/assets/v/abc/api&mode=auto#RL-XHTTP'
RE = f'vless://{U}@vpn.example.com:443?type=tcp&security=reality&pbk=PUBKEY&sid=ab12&sni=www.example.org&fp=chrome&flow=xtls-rprx-vision#%D0%93%D0%B5%D1%80'
v = kv.parse_vless(XH); o = kv.xray_outbound(v)
check('xhttp+tls: address, port, user', o['settings']['vnext'][0]['address'] == '203.0.113.5' and o['settings']['vnext'][0]['port'] == 2053 and o['settings']['vnext'][0]['users'][0]['id'] == U)
check('xhttp+tls: stream', o['streamSettings']['network'] == 'xhttp' and o['streamSettings']['xhttpSettings']['path'] == '/assets/v/abc/api' and o['streamSettings']['tlsSettings']['alpn'] == ['h2', 'http/1.1'])
r = kv.parse_vless(RE); o = kv.xray_outbound(r)
check('reality+vision', o['streamSettings']['network'] == 'raw' and o['streamSettings']['realitySettings']['publicKey'] == 'PUBKEY' and o['settings']['vnext'][0]['users'][0]['flow'] == 'xtls-rprx-vision' and r['name'] == 'Гер')
s = kv.xray_outbound(kv.parse_vless(XH.replace('#', '&allowInsecure=1&pcs=abcd#')))['streamSettings']['tlsSettings']
check('self-signed: the pinned hash wins', s.get('pinnedPeerCertSha256') == 'abcd' and 'allowInsecure' not in s)
for bad, why in (('http://x', 'not vless'), (f'vless://notuuid@h:1', 'uuid'), (f'vless://{U}@h', 'no port'), (f'vless://{U}@h:1?type=kcp', 'transport'),
                 (f'vless://{U}@h:1?security=reality', 'reality without pbk'), (f'{XH}\n{RE}', 'two links')):
    try:
        kv.parse_vless(bad); check('refused: ' + why, False)
    except ValueError:
        check('refused: ' + why, True)
sm = json.dumps(kv.summary(v))
check('summary has no secret', U not in sm and 'pbk' not in sm)
check('mask hides link and UUID', U not in kv.mask(f'x {XH} y {U}') and 'vless://…' in kv.mask(XH))

out, rt = kv.xkeen_configs(r)
check('routing: local direct, the rest to the server', rt['routing']['rules'][0]['outboundTag'] == 'direct' and '192.168.0.0/16' in rt['routing']['rules'][0]['ip'] and rt['routing']['rules'][1]['outboundTag'] == 'proxy')
check('routing: tags exist in the XKeen inbounds', set(rt['routing']['rules'][1]['inboundTag']) == {'redirect', 'tproxy', 'force-proxy-redirect', 'force-proxy-tproxy'})
check('routing: no geo files needed (geo=off)', 'geoip:' not in json.dumps(rt) and 'geosite:' not in json.dumps(rt))
check('install does not start the proxy and asks nothing', '-i auto cores=xray' in kv.XKEEN_INSTALL and '</dev/null' in kv.XKEEN_INSTALL and '-start' not in kv.XKEEN_INSTALL and '-restart' not in kv.XKEEN_INSTALL)
check('key test does not touch the XKeen configs', '/opt/etc/xray' not in kv.key_test(v) and 'xkeen' not in kv.key_test(v))
ap = kv.xkeen_apply(v)
check('apply tests the config before the restart and rolls back', ap.index('run -test') < ap.index('-restart') and '.rl-bak' in ap)
check('remove asks nothing', '-remove' not in kv.XKEEN_REMOVE)

# driver: the order. The policy MUST exist before XKeen can start, a dead key must stop before the configs
class K(keenetic.Keenetic):
    def __init__(s, policies=None, wan=True, key_ok=True, make_policy=True):
        s.calls, s.pol, s.wan, s.key_ok, s.make = [], dict(policies or {}), wan, key_ok, make_policy
    def _session(s, cfg, host=None):
        return s.get, s.cli
    def get(s, p):
        return {'/rci/show/ip/policy': s.pol, '/rci/show/interface': {'ISP': {'defaultgw': s.wan}}, '/rci/show/ip/hotspot': {'host': []}}.get(p, {})
    def cli(s, cmds):
        s.calls.extend(cmds)
        for c in cmds:
            m = re.match(r'ip policy (\S+) description (\S+)', c)
            if m and s.make:
                s.pol[m.group(1)] = {'description': m.group(2)}
        return [{'parse': {'status': []}} for _ in cmds]
    def _ssh(s, cfg, script, timeout=30, params=None):
        name = 'status' if script == kv.STATUS else 'install' if '-i auto' in script else 'keytest' if 'rl-vless-test' in script else 'apply' if 'xkeen -restart' in script else 'remove' if 'opkg remove xkeen' in script else 'other'
        s.calls.append('ssh:' + name)
        if name == 'status':
            return '@@end' if 'ssh:install' not in s.calls else '@@xkeen 2.1\n@@xray 26\n@@end'
        if name == 'keytest':
            return '@@ok' if s.key_ok else '@@fail сервер не отвечает'
        return '@@ok'

cfg = {'host': '192.0.2.1', 'entwarePassword': 'x'}
k = K(); res = k.plugin(cfg, 'xkeen', 'vless_setup', {'link': XH})
c = k.calls
pos = lambda x: next((i for i, y in enumerate(c) if y == x or y.startswith(x)), 999)
check('order: policy → install → key test → apply', pos('ip policy Policy0 description xkeen') < pos('ssh:install') < pos('ssh:keytest') < pos('ssh:apply'), c)
check('policy lets the devices out to the internet', 'ip policy Policy0 permit global ISP' in c and 'system configuration save' in c, c)
check('the link is not in the log', U not in json.dumps(res), res.get('log'))

k = K(key_ok=False)
try:
    k.plugin(cfg, 'xkeen', 'vless_setup', {'link': XH}); check('dead key stops before the configs', False)
except DriverError:
    check('dead key stops before the configs', 'ssh:apply' not in k.calls, k.calls)
k = K(wan=False)
try:
    k.plugin(cfg, 'xkeen', 'vless_setup', {'link': XH}); check('no WAN found: nothing is installed', False)
except DriverError:
    check('no WAN found: nothing is installed', 'ssh:install' not in k.calls, k.calls)
k = K(make_policy=False)
try:
    k.plugin(cfg, 'xkeen', 'vless_setup', {'link': XH}); check('policy not created: nothing is installed or started', False)
except DriverError:
    check('policy not created: nothing is installed or started', 'ssh:install' not in k.calls and 'ssh:apply' not in k.calls, k.calls)
k = K(policies={'Policy3': {'description': 'XKeen'}})
k.plugin(cfg, 'xkeen', 'vless_setup', {'link': XH})
check('existing policy is reused', not any(x.startswith('ip policy') for x in k.calls), k.calls)
k = K()
try:
    k.plugin(cfg, 'xkeen', 'start', {}); check('start without a policy is refused', False)
except DriverError as e:
    check('start without a policy is refused', 'политики xkeen' in str(e), str(e))

# XKeen leaves its core holding stdout: no pipe may hang on it, or SSH waits for ever while the proxy is up
for name, sc in (('install', kv.XKEEN_INSTALL), ('apply', ap), ('start', kv.XKEEN_CONTROL['start']), ('stop', kv.XKEEN_CONTROL['stop'])):
    check(f'{name}: XKeen output goes to a file, not a pipe', not re.search(r'/opt/sbin/xkeen [^\n]*\|', sc) and '>/tmp/rl-xk.log' in sc, sc[:200])

# XKeen on Mihomo: the key is not replaced, nothing changes
class KM(K):
    def _ssh(s, cfg, script, timeout=30, params=None):
        s.calls.append('ssh')
        return '@@xkeen 2.1\n@@mihomo\n@@mihomo_on\n@@end'
k = KM()
try:
    k.plugin(cfg, 'xkeen', 'vless_setup', {'link': XH}); check('mihomo: setup refused', False)
except DriverError as e:
    check('mihomo: setup refused before any change', 'Mihomo' in str(e) and not any(x.startswith('ip policy') for x in k.calls), k.calls)

# Entware access: another address and port, a bad port, the host is not saved when it is the router's own
b = keenetic.Keenetic()
s_ = b._ssh_cfg({'host': 'https://r.example:8443/', 'entwarePassword': 'x', 'entwareHost': '203.0.113.9', 'entwarePort': '2222'})
check('ssh: saved address and port are used', s_['host'] == '203.0.113.9' and s_['sshPort'] == 2222, s_)
s_ = b._ssh_cfg({'host': 'https://r.example:8443/', 'entwareHost': '203.0.113.9', 'entwarePassword': 'x'}, {'host': ''})
check('ssh: an empty address means the router itself', s_['host'] == 'r.example' and s_['sshPort'] == 222, s_)
try:
    b._ssh_cfg({'host': 'r', 'entwarePassword': 'x', 'entwarePort': 'abc'}); check('ssh: bad port refused', False)
except DriverError:
    check('ssh: bad port refused', True)

# status without Entware access: «unknown», never «not installed»
class KS(K):
    def __init__(s, pol=None, procs=()):
        K.__init__(s, policies=pol); s.procs = procs
    def _rc(s, cli):
        return ['opkg disk abc:/', 'opkg initrc /opt/etc/init.d/rc.unslung']
    def get(s, p):
        if p == '/rci/show/processes':
            return {'process': [{'comm': c} for c in s.procs]}
        if p == '/rci/show/version':
            return {'arch': 'mips', 'title': '5.1', 'model': 'Viva', 'ndw': {'components': 'opkg'}}
        return K.get(s, p)
xk = lambda r: next(p for p in r['plugins'] if p['id'] == 'xkeen')
no = {'host': 'r.example'}
x = xk(KS().plugins(no))
check('no access, no traces: status unknown', x['installed'] is None and not x['detected'], x['installed'])
x = xk(KS(pol={'Policy0': {'description': 'XKeen'}}).plugins(no))
check('no access, policy found: unknown, with the hint', x['installed'] is None and 'политика' in x['detected'], x.get('detected'))
x = xk(KS(procs=('xray',)).plugins(no))
check('no access, xray running: installed', x['installed'] is True and x['running'] is True, x)
r_ = KS().plugins(no)
check('the access block is reported once for the router', r_['entwareAccess']['entware'] is True and r_['entwareAccess']['defaultHost'] == 'r.example' and r_['entwareAccess']['set'] is False, r_['entwareAccess'])
print('ВСЁ OK' if not fails else f'ОШИБОК: {fails}')
sys.exit(1 if fails else 0)
