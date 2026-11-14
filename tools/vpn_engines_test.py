"""«Раздельный VPN» for Tachyon / Podkop / Forkop: option checks and the scripts written (both modes, links / subscription / tunnel).
python tools/vpn_engines_test.py   (keys in tests are fake)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import forkop_split as fs, vpn_engines as ve

BAD = []
def U(s):
    return s.replace("'", '')


def ok(name, cond):
    print(('OK   ' if cond else 'FAIL ') + name)
    if not cond:
        BAD.append(name)

AWG = """# Test NL
[Interface]
PrivateKey = cHJpdmF0ZWtleXByaXZhdGVrZXlwcml2YXRla2V5MDA=
Address = 10.8.0.2/32
Jc = 4
Jmin = 40
Jmax = 70
S1 = 10
H1 = 1
[Peer]
PublicKey = cHVibGlja2V5cHVibGlja2V5cHVibGlja2V5cHViMDA=
Endpoint = 203.0.113.7:51820
AllowedIPs = 0.0.0.0/0
"""
LINKS = "vless://11111111-2222-3333-4444-555555555555@203.0.113.8:443?security=reality#NL\nvless://11111111-2222-3333-4444-555555555556@203.0.113.9:443#DE"
tun, links, sub = fs.parse(AWG), fs.parse(LINKS), fs.parse('https://sub.example.com/abc')

m, l, d = ve.check_opts('sites', ['russia_inside', 'youtube', 'meta', 'nope'], 'chatgpt.com https://openai.com/x *.claude.ai', 'podkop')
ok('podkop drops youtube with russia_inside, unknown list gone', l == ['russia_inside', 'meta'])
ok('domains cleaned', d == ['chatgpt.com', 'openai.com', 'claude.ai'])
ok('tachyon keeps youtube', ve.check_opts('sites', ['russia_inside', 'youtube'], '', 'tachyon')[1] == ['russia_inside', 'youtube'])
try:
    ve.check_opts('sites', [], '', 'tachyon'); ok('sites needs something', False)
except fs.SplitError:
    ok('sites needs something', True)
try:
    ve.check_opts('sites', ['youtube'], 'bad_domain!', 'tachyon'); ok('bad domain refused', False)
except fs.SplitError:
    ok('bad domain refused', True)
ok('cyrillic domain → punycode', ve.check_opts('sites', [], 'пример.рф', 'tachyon')[2] == ['xn--e1afmkfd.xn--p1ai'])

scripts = {}
for eng in ('tachyon', 'podkop'):
    f = ve.tachyon_script if eng == 'tachyon' else ve.podkop_script
    for mode in ('split', 'sites'):
        for name, p in (('tunnel', tun), ('links', links), ('sub', sub)):
            if eng == 'podkop' and name == 'sub':
                continue
            s = f(p, '192.168.1.0/24' if mode == 'split' else '', True, mode, ['russia_inside', 'telegram'], ['chatgpt.com'], True)
            scripts[f'{eng}-{mode}-{name}'] = s
            ok(f'{eng} {mode} {name}: no key printed', 'echo' not in ''.join(x for x in s.splitlines() if 'cHJpdmF0' in x or '11111111' in x))
            ok(f'{eng} {mode} {name}: restore on failure', '@@restored' in s and 'cp "$B" /etc/config/' + eng in s)
            if mode == 'split':
                ok(f'{eng} {mode} {name}: Russia straight', 'rl_ru' in s and 'fully_routed_ips="$NET"' in s)
            else:
                ok(f'{eng} {mode} {name}: lists + domains', 'community_lists=russia_inside' in U(s) and 'user_domains=chatgpt.com' in U(s) and f'uci set {eng}.rl_ru=' not in s)
for eng in ('forkop',):
    for mode in ('split', 'sites'):
        s = fs.script(links, '192.168.1.0/24', True, mode, ['russia_inside'], ['chatgpt.com'])
        scripts[f'forkop-{mode}'] = s
        ok(f'forkop {mode}', ("rl_ru" in s) == (mode == 'split') or mode == 'sites' and "uci set forkop.rl_ru=" not in s)

t = U(scripts['tachyon-sites-links'])
ok('tachyon: urltest for several links', 'urltest_enabled=1' in t and t.count('selector_proxy_links') == 2)
ok('tachyon: awg as json config', '"config": "# Test NL' in scripts['tachyon-split-tunnel'] or '\\"config\\"' in scripts['tachyon-split-tunnel'] or '"config":' in scripts['tachyon-split-tunnel'])
ok('tachyon: subscription child', 'rl_vpn_sub=subscription_url' in U(scripts['tachyon-split-sub']))
p = U(scripts['podkop-split-links'])
ok('podkop: urltest links', 'proxy_config_type=urltest' in p and p.count('urltest_proxy_links') == 2)
ok('podkop: exclusion first', 'rl_ru.connection_type=exclusion' in p and 'uci reorder podkop.rl_ru=1' in p)
pt = U(scripts['podkop-sites-tunnel'])
ok('podkop: awg interface', 'network.rl_awg.proto=amneziawg' in pt and 'awg_jc=4' in pt and 'route_allowed_ips=0' in pt and 'main.interface=rl_awg' in pt)
ok('podkop: tunnel restores network too', 'cp "$B.network" /etc/config/network' in pt)
one = U(ve.podkop_script(fs.parse(LINKS.splitlines()[0]), '', True, 'sites', ['youtube'], [], True))
ok('podkop: one link → url', 'proxy_config_type=url' in one and 'proxy_string=' in one)

st = ve.parse_status('podkop', '@@lan 192.168.1.0/24\n@@sec section rl_ru 1- |exclusion|\n@@sec section main 1- |proxy|\n@@sec section other - |proxy|x\n@@run\n@@end')
ok('status: ours, applied, running', st['applied'] and st['running'] and [s['ours'] for s in st['sections']] == [True, True, False] and st['sections'][0]['action'] == 'bypass')

if len(sys.argv) > 1:                                   # write the scripts out for `sh -n` on a router
    for k, s in scripts.items():
        open(os.path.join(sys.argv[1], k + '.sh'), 'w', encoding='utf-8', newline='\n').write(s)
print('GOOD' if not BAD else 'BAD: ' + ', '.join(BAD))
