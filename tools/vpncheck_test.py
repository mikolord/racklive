"""«Проверка VPN»: links are parsed, secrets stay out of the report, a VPN on our own path is reported, and a verdict matches what was measured. No network."""
import base64, json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from rackd import vpncheck as vc

FAILS = 0
def check(name, ok, info=''):
    global FAILS
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok else f'  {info}'))
    FAILS += 0 if ok else 1

UID = '11111111-2222-4333-8444-555555555555'
PW = 'sup3r-s3cret-pass'
VLESS = f'vless://{UID}@203.0.113.10:443?type=tcp&security=reality&pbk=PUBKEYPUBKEY&sid=abcd&sni=www.example.com&fp=chrome&flow=xtls-rprx-vision#Germany'
XHTTP = f'vless://{UID}@203.0.113.11:8443?type=xhttp&security=tls&sni=cdn.example.com&host=cdn.example.com&path=%2Fx#Xhttp'
VMESS = 'vmess://' + base64.b64encode(json.dumps({'add': '203.0.113.12', 'port': 443, 'id': UID, 'net': 'ws', 'tls': 'tls', 'host': 'a.example.com', 'path': '/w', 'ps': 'VM'}).encode()).decode()
TROJAN = f'trojan://{PW}@203.0.113.13:443?sni=t.example.com#Tr'
SS = 'ss://' + base64.b64encode(f'aes-256-gcm:{PW}'.encode()).decode() + '@203.0.113.14:8388#Shadow'
SOCKS = f'socks://user:{PW}@203.0.113.15:1080#So'
HY = f'hysteria2://{PW}@203.0.113.16:443?sni=h.example.com#Hy'
WG = f'''[Interface]
PrivateKey = {PW}
Address = 10.0.0.2/32
Jc = 4
[Peer]
PublicKey = abc
Endpoint = 203.0.113.17:51820
'''

v = vc.parse_link(VLESS)
check('VLESS: type, transport, security', (v['proto'], v['kind'], v['net'], v['security'], v['port']) == ('VLESS', 'прокси', 'tcp', 'reality', 443), v)
check('VLESS: the core gets the id', v['outbound']['settings']['vnext'][0]['users'][0]['id'] == UID)
check('a name with spaces and Cyrillic does not break a link', vc.parse_link(VLESS.replace('#Germany', '#🇩🇪 Германия через CDN'))['name'] == '🇩🇪 Германия через CDN')
m = vc.parse_link(VMESS)
check('VMess: parsed from base64', (m['proto'], m['net'], m['security'], m['host']) == ('VMess', 'ws', 'tls', '203.0.113.12') and m['outbound']['protocol'] == 'vmess', m)
t = vc.parse_link(TROJAN)
check('Trojan: TLS by default', (t['proto'], t['security']) == ('Trojan', 'tls') and t['outbound']['settings']['servers'][0]['password'] == PW, t)
s = vc.parse_link(SS)
check('Shadowsocks: method and password', s['outbound']['settings']['servers'][0]['method'] == 'aes-256-gcm' and s['outbound']['settings']['servers'][0]['password'] == PW, s)
legacy = vc.parse_link('ss://' + base64.b64encode(f'aes-128-gcm:{PW}@203.0.113.14:8388'.encode()).decode())
check('Shadowsocks: the old all-in-base64 form', (legacy['host'], legacy['port']) == ('203.0.113.14', 8388))
check('SOCKS: a login goes to the core', vc.parse_link(SOCKS)['outbound']['settings']['servers'][0]['users'][0]['pass'] == PW)
h = vc.parse_link(HY)
check('Hysteria2: known type, no tunnel promised', h['proto'] == 'Hysteria2' and h['outbound'] is None and h['kind'] == 'прокси на UDP')
w = vc.parse_wg(WG)
check('AmneziaWG told from WireGuard by its fields', w['proto'] == 'AmneziaWG' and w['kind'] == 'VPN' and (w['host'], w['port']) == ('203.0.113.17', 51820), w)
check('plain WireGuard', vc.parse_wg(WG.replace('Jc = 4\n', ''))['proto'] == 'WireGuard')
V = lambda **k: vc.awg_version({a.lower(): str(b) for a, b in k.items()})
check('AWG version: plain WireGuard, even with default H', V(H1=1, H2=2, H3=3, H4=4, Jc=0, S1=0) is None and V() is None)
check('AWG version: 1.0', V(Jc=4, Jmin=40, Jmax=70, S1=30, S2=40, H1=11, H2=22, H3=33, H4=44) == '1.0')
check('AWG version: 1.5 has I1 on top', V(Jc=4, S1=30, S2=40, H1=11, I1='<r 160>') == '1.5')
check('AWG version: 2.0 by S3/S4', V(Jc=5, S1=137, S2=101, S3=43, S4=14, H1=341116479, I1='<r 160>') == '2.0')
check('AWG version: 2.0 by H ranges', V(Jc=5, H1='100-200') == '2.0')
check('AWG version: 3.x', V(Jc=4, S3=46, S4=17, H1=1, H2=2, H3=3, H4=4, HeaderProtectionKey='x', ContentPaddingAddition='18-31') == '3.x')
check('AWG version: «false» switches are not 3.x', V(Jc=5, S3=4, RandomTrailers='false', DisableCookies='false') == '2.0')
hk = vc.parse_wg(WG.replace('Jc = 4\n', f'Jc = 4\nS3 = 40\nHeaderProtectionKey = {PW}x\nI1 = <r 10>\nS1 = 30\nS2 = 86\n'))
check('AWG: version, mimicry and a size clash are reported, keys are secrets', hk['awg']['version'] == '3.x' and hk['awg']['mimicry'] and hk['awg']['sizeClash'] and PW + 'x' in hk['secrets'], hk['awg'])
import zlib
inner = json.dumps({'containers': [{'awg': {'last_config': json.dumps({'config': WG})}}], 'description': 'Мой AWG'}).encode()
blob = base64.urlsafe_b64encode(len(inner).to_bytes(4, 'big') + zlib.compress(inner)).decode().rstrip('=')
am = vc.parse_amnezia('vpn://' + blob)
check('vpn:// from the Amnezia app: found inside, with a name', am['name'] == 'Мой AWG' and am['awg']['version'] == '1.0' and am['host'] == '203.0.113.17', am)
for bad in ('vpn://!!!', 'vpn://' + base64.urlsafe_b64encode(b'\0\0\0\2' + zlib.compress(b'{}')).decode()):
    try:
        vc.parse_amnezia(bad)
        check('vpn://: a useless link is refused', False)
    except ValueError:
        check('vpn://: a useless link is refused', True)
D = lambda **k: vc.classify_decoy(k)
GOOD_ = {'proto': 'VLESS', 'security': 'reality', 'net': 'tcp', 'flow': 'xtls-rprx-vision', 'advice': [], 'decoy': {'kind': 'site', 'text': 't'}, 'route': {'state': 'direct'}}
check('decoy: a real page', D(status=200, title='Блог', body='x' * 600)['kind'] == 'site')
check('decoy: Reality with a genuine certificate borrows the site', vc.classify_decoy({'status': 200, 'title': 'Android', 'body': 'x' * 600}, True, True)['kind'] == 'borrowed')
check('decoy: the real site\'s own 404 behind Reality is not «no decoy»', (lambda r: r['kind'] == 'borrowed_error' and r['state'] == 'ok')(vc.classify_decoy({'status': 404, 'body': 'x'}, True, True)))
check('decoy: Reality without a genuine certificate gets no credit', vc.classify_decoy({'status': 404, 'body': 'x'}, True, False)['kind'] == 'error')
check('decoy: a small page with a name is a simple stub', D(status=200, title='origin.example', body='<title>origin.example</title>')['kind'] == 'stub')
check('verdict: the core refusing a link is not called a dead server', vc.verdict({'tunnel': {'state': 'config', 'note': 'Ядро не приняло.'}, 'block': {'state': 'ok'}}, 'direct')[0] == 'unknown')
check('score: the core refusing a link limits by 5, not by a dead tunnel', vc.score({**GOOD_, 'tunnel': {'state': 'config'}}, 'direct')['value'] == 5)
check('decoy: a panel is bad', D(status=200, title='3x-ui login', body='x' * 600)['state'] == 'bad')
check('decoy: panel found in the page body', D(status=200, title='Login', body='<script src=x-ui.js>' + 'x' * 600)['kind'] == 'panel')
check('decoy: default page is not a site', D(status=200, title='Welcome to nginx!', body='x' * 600)['kind'] == 'default')
check('decoy: bare error', D(status=404, server='nginx')['kind'] == 'error')
check('decoy: redirect', D(status=301, location='https://x.example/')['kind'] == 'redirect')
check('decoy: a nearly empty page', D(status=200, body='ok')['kind'] == 'empty')
check('decoy: no answer', D(status=None, error='нет ответа')['kind'] == 'silent')
check('decoy: the page itself is not kept', 'body' not in D(status=200, title='T', body='y' * 600))
GOOD = {'proto': 'VLESS', 'security': 'reality', 'net': 'tcp', 'flow': 'xtls-rprx-vision', 'advice': [], 'decoy': {'kind': 'site', 'text': 't'}, 'route': {'state': 'direct'},
        'tunnel': {'state': 'ok', 'okCount': 5, 'tries': 5, 'down': 100}}
check('score: everything good is 10', vc.score(GOOD, 'direct')['value'] == 10, vc.score(GOOD, 'direct'))
check('score: a dead tunnel is 3 at most', vc.score({**GOOD, 'tunnel': {'state': 'fail'}}, 'direct')['value'] <= 3)
check('score: frozen after kilobytes is 4 at most', vc.score({**GOOD, 'tunnel': {**GOOD['tunnel'], 'freeze': True, 'stalled': True}}, 'direct')['value'] <= 4)
check('score: without a tunnel test, 5 at most, and it says why', (lambda s: s['value'] <= 5 and s['limits'])(vc.score({'proto': 'AmneziaWG', 'awg': {'version': '3.x'}, 'net': 'udp', 'security': 'none', 'advice': [], 'tunnel': {'state': 'skip'}}, 'direct')))
check('score: not surely through the provider is 7 at most', vc.score({**GOOD, 'route': {'state': 'vpn'}}, 'direct')['value'] <= 7 and vc.score({**GOOD, 'route': {'state': 'unknown'}}, 'mixed')['value'] <= 7)
check('score: the server having seen the provider lifts the limit', vc.score(GOOD, 'mixed')['value'] == 10)
check('score: newer AWG scores higher', vc.score({'proto': 'AmneziaWG', 'awg': {'version': '3.x'}, 'net': 'udp', 'security': 'none', 'advice': [], 'tunnel': {}}, 'direct')['value'] > vc.score({'proto': 'AmneziaWG', 'awg': {'version': '1.0'}, 'net': 'udp', 'security': 'none', 'advice': [], 'tunnel': {}}, 'direct')['value'])
check('score: no encryption scores low', vc.score({**GOOD, 'security': 'none'}, 'direct')['parts'][3]['got'] == 0)
check('score: a panel in the open costs the decoy part', next(p for p in vc.score({**GOOD, 'decoy': {'kind': 'panel', 'text': 't'}}, 'direct')['parts'] if p['label'] == 'Сайт-заглушка')['got'] == 0)
check('score: half steps, between 0 and 10', all(0 <= vc.score({**GOOD, 'tunnel': {**GOOD['tunnel'], 'down': d}}, 'direct')['value'] * 2 % 1 == 0 for d in (0, 6, 50)))
for bad in ('http://x', 'vless://nope', 'trojan://a@h', 'ss://!!!', 'vmess://!!!'):
    try:
        vc.parse_link(bad)
        check('a broken link is refused: ' + bad, False)
    except ValueError as e:
        check('a broken link is refused, with a reason: ' + bad.split(':')[0], bool(str(e)))

lev = lambda link: {a['level'] for a in vc.advice(vc.parse_link(link))}
check('advice: a clean Reality has nothing bad', not ({'bad', 'warn'} & lev(VLESS)), vc.advice(v))
check('advice: Reality without vision is noticed', 'warn' in lev(VLESS.replace('&flow=xtls-rprx-vision', '')))
check('advice: no TLS is bad', 'bad' in lev(f'vless://{UID}@203.0.113.10:80?type=tcp'))
check('advice: plain WireGuard is bad', any(a['level'] == 'bad' for a in vc.advice(vc.parse_wg(WG.replace('Jc = 4\n', '')))))
check('advice: UDP is warned about', 'warn' in lev(HY))

R, N = {'reached': True}, {'reached': False}
check('path: closed address', vc.classify({'ok': False}, None, None, None, R)[0] == 'bad')
check('path: no internet says nothing about the server', vc.classify({'ok': False}, None, None, None, N)[0] == 'unknown')
check('path: SNI block seen on a clean address', 'SNI' in vc.classify({'ok': True}, N, None, N, R)[1])
check('path: SNI block seen on the same server', 'SNI' in vc.classify({'ok': True}, N, R, R, R)[1])
check('path: TLS dead with any name is not called SNI', 'SNI' not in vc.classify({'ok': True}, N, N, R, R)[1])
check('path: TLS answered', vc.classify({'ok': True}, R, None, None, None)[0] == 'ok')

OK = {'state': 'ok', 'freeze': False, 'stalled': False}
check('verdict: works, directly', vc.verdict({'tunnel': OK, 'block': {'state': 'ok'}}, 'direct')[0] == 'ok')
check('verdict: through another VPN is never green', vc.verdict({'tunnel': OK, 'block': {'state': 'ok'}}, 'vpn')[0] == 'warn')
check('verdict: freeze after kilobytes', vc.verdict({'tunnel': {**OK, 'freeze': True, 'stalled': True, 'stallAt': 16384}, 'block': {'state': 'ok'}}, 'direct')[0] == 'bad')
check('verdict: server answers but the tunnel fails', 'ссылка устарела' in vc.verdict({'tunnel': {'state': 'fail'}, 'block': {'state': 'ok'}}, 'direct')[1])
check('verdict: skipped tunnel is not green', vc.verdict({'tunnel': {'state': 'skip', 'note': 'x.'}, 'block': {'state': 'ok'}}, 'direct')[0] == 'unknown')
check('CDN: Cloudflare by range and others by owner', vc.cdn_of('104.16.1.1') == 'Cloudflare' and vc.cdn_of('203.0.113.1', 'Fastly, Inc.') == 'Fastly' and vc.cdn_of('203.0.113.1', 'Hetzner') is None)
check('CDN: Reality SNI is a disguise, not a CDN of ours', [n for _, n in vc.VpnCheck.names_of(None, v)] == ['203.0.113.10'])
check('CDN: names of a TLS link and one given by hand', [n for _, n in vc.VpnCheck.names_of(None, vc.parse_link(XHTTP), 'own.example.com')] == ['203.0.113.11', 'cdn.example.com', 'own.example.com'])


class Store:
    def __init__(self, cfg): self.cfg, self.saved = cfg, {}
    def _load(self, a, b): return b
    def _dump(self, a, b): self.saved[a] = b
class App: pass
def make(probe, devices=(), states=None):
    a = App(); a.store = Store({'devices': list(devices)}); a.states = states or {}
    return vc.VpnCheck(a, probe)

class P(vc.DemoProbe):
    me = '198.51.100.7'
    def my_ip(self, proxy=None): return '203.0.113.10' if proxy else self.me
class Foreign(P):
    me = '192.0.2.50'

check('path: a Russian provider is direct', make(P()).path()['state'] == 'direct')
check('path: abroad is a VPN', make(Foreign()).path()['state'] == 'vpn')
class Mixed(P):
    def exits(self): return [('api.ipify.org', '192.0.2.50'), ('ifconfig.me', '198.51.100.7'), ('icanhazip.com', '192.0.2.50')]
vps2 = {'id': 'v', 'name': 'GE', 'driver': 'ssh', 'location': 'remote', 'host': '192.0.2.50'}
got = make(Mixed(), [vps2]).path()
check('path: some addresses through a VPN are called out by name', got['state'] == 'mixed' and got['via'] == 'GE' and got['routed'] == ['api.ipify.org', 'icanhazip.com'] and got['ip'] == '198.51.100.7', got)
check('verdict: mixed routing is not green', vc.verdict({'tunnel': OK, 'block': {'state': 'ok'}}, 'mixed')[0] == 'warn')
check('verdict: unclear path is not green', vc.verdict({'tunnel': OK, 'block': {'state': 'ok'}}, 'unknown')[0] == 'warn')
check('verdict: the server saw the provider, mixed or not', vc.verdict({'tunnel': OK, 'block': {'state': 'ok'}, 'route': {'state': 'direct'}}, 'mixed')[0] == 'ok')
check('verdict: the server saw another VPS, whatever the general picture', vc.verdict({'tunnel': OK, 'block': {'state': 'ok'}, 'route': {'state': 'vpn'}}, 'direct')[0] == 'warn')
class Peers(Mixed):
    answer = ([], '5000')
    def server_peers(self, d, ip, port): return self.answer
vps3 = {'id': 't', 'name': 'NL', 'driver': 'ssh', 'location': 'remote', 'host': '192.0.2.60'}
def route(answer):
    pr = Peers(); pr.answer = answer
    x = make(pr, [vps2, vps3]); x.path()
    return x.route_to('192.0.2.60', 443)
check('route: our connection seen from the provider', route(([('198.51.100.7', '5000')], '5000'))['state'] == 'direct')
got = route(([('192.0.2.50', '5000')], '5000'))
check('route: our connection seen from another VPS', got['state'] == 'vpn' and got['via'] == 'GE', got)
check('route: the exact port wins over another home device', route(([('198.51.100.7', '7777'), ('192.0.2.50', '5000')], '5000'))['state'] == 'vpn')
check('route: nobody recognised stays unknown', route(([('203.0.113.99', '1')], '5000'))['state'] == 'unknown')
check('route: the server could not be asked', route((None, None))['state'] == 'unknown')
check('route: a server that is not ours is not guessed', make(Peers()).route_to('192.0.2.60', 443)['state'] == 'unknown')
class CfVpn(Mixed):
    def cf_seen(self, connect_ip=None): return '192.0.2.50'
xc = make(CfVpn(), [vps2]); xc.path()
check('CDN: a measurement that went through our VPS is marked', xc.seen_by_cloudflare() == 'vpn')
class CfDirect(Mixed):
    def cf_seen(self, connect_ip=None): return '198.51.100.7'
xc = make(CfDirect(), [vps2]); xc.path()
check('CDN: a direct measurement is marked', xc.seen_by_cloudflare() == 'direct')
srv = {'id': 'a', 'name': 'VPS', 'driver': 'ssh', 'location': 'remote', 'host': '198.51.100.7'}
got = make(P(), [srv]).path()
check('path: exit equal to our own VPS is a VPN, even with a Russian address', got['state'] == 'vpn' and got['via'] == 'VPS', got)
rt = {'id': 'r', 'name': 'R', 'driver': 'keenetic'}
got = make(Foreign(), [rt], {'r': {'ports': [{'kind': 'wan', 'ip': '192.0.2.50'}]}}).path()
check('path: exit equal to the router\'s WAN is direct, wherever it is', got['state'] == 'direct', got)
class Dead(P):
    def my_ip(self, proxy=None): return None
check('path: no answer is not called direct', make(Dead()).path()['state'] == 'unknown')

c = make(P())
items, errors = c.expand('\n'.join((VLESS, XHTTP, VMESS, TROJAN, SS, SOCKS, HY, 'мусор')))
check('expand: every line, and one readable error', len(items) == 7 and len(errors) == 1 and 'Строка 8' in errors[0], errors)
check('expand: WireGuard is one block', [x['proto'] for x in c.expand(WG)[0]] == ['AmneziaWG'])
try:
    c.expand('   ')
    check('expand: empty refused', False)
except ValueError:
    check('expand: empty refused', True)
many, err = c.expand('\n'.join([VLESS] * 30))
check('expand: the number of links is limited', len(many) == vc.MAX_LINKS and err, len(many))

class Sub(P):
    def fetch(self, url, **kw):
        return {'ok': True, 'status': 200, 'body': base64.b64encode((VLESS + '\n' + TROJAN).encode()), 'error': None, 'bytes': 1, 'sent': 0, 'stalled': False, 'seconds': 1, 'ms': 1}
sc = make(Sub())
got, _ = sc.expand('https://sub.example.com/token')
check('subscription in base64 is opened', [x['proto'] for x in got] == ['VLESS', 'Trojan'], got)

done = []
items, errors = c.expand('\n'.join((VLESS, XHTTP, VMESS, TROJAN, SS, SOCKS, HY)) + '\n')
items.append(vc.parse_wg(WG))
rep = c.run(items, errors, done.append, 'cdn.example.com')
text = json.dumps(rep, ensure_ascii=False)
check('report: one row per link', len(rep['items']) == 8 and rep['path']['state'] == 'direct', len(rep['items']))
for name, secret in (('UUID', UID), ('password', PW), ('Reality key', 'PUBKEYPUBKEY'), ('short id', '"abcd"')):
    check(f'report: no {name}', secret not in text)
check('report: no link at all', 'vless://' not in text and 'trojan://' not in text and 'outbound' not in text)
check('progress never shows a secret', not any(UID in x or PW in x for x in done))
r0 = rep['items'][0]
check('report: protocol, ping, speed, exit are there', r0['proto'] == 'VLESS' and r0['ping']['avg'] and r0['tunnel']['down'] and r0['tunnel']['exit'] and r0['verdict']['state'] == 'ok', r0)
check('report: UDP protocol does not pretend', next(x for x in rep['items'] if x['proto'] == 'Hysteria2')['verdict']['state'] == 'unknown')
row = next(x for x in rep['items'] if x['name'] == 'Xhttp')['cdns']
check('report: a CDN domain is measured and its tunnel tried', row and row[0]['cdn'] == 'Cloudflare' and row[0]['volume']['ok'] and row[0]['tunnel']['state'] == 'ok', row)

class Boom(P):
    def tunnel(self, it, on_up=None, host=None): raise RuntimeError('failed for ' + UID)
rep2 = make(Boom()).run(c.expand(VLESS + '\n' + TROJAN)[0], [], lambda x: None)
check('one broken check keeps the others and hides the secret', len(rep2['items']) == 2 and UID not in json.dumps(rep2) and rep2['items'][0]['verdict']['state'] == 'unknown', rep2['items'][0])
check('scrub removes given secrets and any UUID', 'X' not in vc.scrub('X ' + UID, {'secrets': ['X']}) and UID not in vc.scrub(UID, {}))
try:
    c.start(VLESS, 'bad domain; rm')
    check('a strange CDN name is refused', False)
except ValueError:
    check('a strange CDN name is refused', True)

j = c.start(VLESS)
import time
for _ in range(50):
    if j['done']: break
    time.sleep(.1)
check('job finishes and saves a report without secrets', j['done'] and not j.get('error') and UID not in json.dumps(c.store.saved.get('vpncheck.json')) and c.public()['report'], j)

src = open(os.path.join(os.path.dirname(__file__), '..', 'rackd', 'vpncheck.py'), encoding='utf-8').read()
check('secrets are never written to a file', 'stdin:' in src and 'NamedTemporaryFile' not in src)
docker = open(os.path.join(os.path.dirname(__file__), '..', 'Dockerfile'), encoding='utf-8').read()
check('the Xray core is pinned by version and checksum', 'v26.10.21' in docker and 'sha256sum -c' in docker)

print('\nВСЁ OK' if not FAILS else f'\nОШИБОК: {FAILS}')
sys.exit(1 if FAILS else 0)
