"""Forkop «Раздельный VPN»: parsing of a pasted AWG / WireGuard config, links and a subscription, and the script it writes.   python tools/forkop_split_test.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import forkop_split as fs

bad = 0
def check(name, ok):
    global bad
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok:
        bad += 1

PK, PUB, HPK = 'A' * 43 + '=', 'B' * 43 + '=', 'C' * 43 + '='
AWG3 = f"""[Interface]
PrivateKey = {PK}
Address = 10.20.3.2/32, fd00::2/128
DNS = 8.8.8.8
MTU = 1340
Jc = 4
Jmin = 63
Jmax = 115
S1 = 61
S2 = 35
H1 = 1
H2 = 2
H3 = 3
H4 = 4
HeaderProtectionKey = {HPK}
ContentPaddingAddition = 18-31
RandomTrailers = on
DisableCookies = on

# 🇳🇱 AWG Нидерланды/1
[Peer]
PublicKey = {PUB}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = awg.example.org:8443
PersistentKeepalive = 25
"""
p = fs.parse(AWG3)
check('AWG 3 config → an amneziawg tunnel', p['type'] == 'tunnel' and p['kind'] == 'amneziawg')
t, pe = p['tunnel'], p['peer']
check('AWG fields in Forkop names (amnezia_*), flags as 1', t['amnezia_jc'] == '4' and t['amnezia_header_protection_key'] == HPK
      and t['amnezia_content_padding_addition'] == '18-31' and t['amnezia_random_trailers'] == '1' and t['amnezia_disable_cookies'] == '1')
check('IPv4 address only, IPv6 skipped', t['address'] == ['10.20.3.2/32'] and p['ipv6Skipped'])
check('peer: host, port, key, keepalive, IPv4 allowed', pe == {'address': 'awg.example.org', 'port': '8443', 'public_key': PUB, 'allowed_ips': ['0.0.0.0/0'], 'persistent_keepalive_interval': '25'})
check('name from the comment, no «/» and no emoji', '/' not in p['name'] and p['name'].startswith('AWG Нидерланды'))
pub = fs.public(p)
check('the page never sees a key', PK not in str(pub) and HPK not in str(pub) and PUB not in str(pub))
wg = fs.parse(f"[Interface]\nPrivateKey = {PK}\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = {PUB}\nPresharedKey = {HPK}\nEndpoint = [2001:db8::1]:51820\n")
check('plain WireGuard (no S/H fields) → wireguard, PSK kept, IPv6 endpoint', wg['kind'] == 'wireguard' and wg['peer']['pre_shared_key'] == HPK and wg['peer']['address'] == '2001:db8::1')
for txt, why in ((f"[Interface]\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = {PUB}\nEndpoint = a:1\n", 'PrivateKey'), (f"[Interface]\nPrivateKey = {PK}\nAddress = 10.0.0.2/32\n", '[Peer]'),
                 ('hello world', 'не ссылка'), ('', 'вставьте')):
    try:
        fs.parse(txt); check('refused: ' + why, False)
    except fs.SplitError as e:
        check('refused with a reason: ' + why, why in str(e))
L = fs.parse('vless://11111111-2222-3333-4444-555555555555@nl.example.org:443?security=reality&type=tcp#NL%20%F0%9F%87%B3%F0%9F%87%B1\n'
             'trojan://secret@de.example.org:443#NL\nhysteria2://pw@fi.example.org:8443')
check('links: three, names from the fragment, unique, default name', L['type'] == 'links' and [x['name'] for x in L['links']] == ['NL', 'NL 2', 'Сервер 3'])
check('links: the page sees host and scheme, not the UUID / password', '1111' not in str(fs.public(L)) and 'secret' not in str(fs.public(L)) and 'nl.example.org' in str(fs.public(L)))
S = fs.parse('https://sub.example.org/api/sub/abc')
check('one https address → a subscription', S['type'] == 'subscription' and S['host'] == 'sub.example.org')
check('network check', fs.check_net('192.168.22.7/24') == '192.168.22.0/24' and fs.check_net('') == '')
try:
    fs.check_net('fd00::/64'); check('IPv6 network refused', False)
except fs.SplitError:
    check('IPv6 network refused', True)
sc = fs.script(p, '')
check('script: backup first, rollback when Forkop does not come up', sc.index('cp /etc/config/forkop "$B"') < sc.index('uci set') and 'cp "$B" /etc/config/forkop' in sc and '@@restored' in sc)
check('script: Russia straight (ru_only + .ru .su .рф) before the VPN section, which takes the whole LAN',
      "rl_ru.action=bypass" in sc and "community_lists=ru_only" in sc and "rl_ru.destinations=ru,su,xn--p1ai" in sc and 'uci reorder forkop.rl_ru=1' in sc
      and 'fully_routed_ips="$NET"' in sc and 'network_get_subnet S lan' in sc)
check('script: the tunnel and the peer tied together', 'rl_vpn_tun.section=rl_vpn' in sc and 'rl_vpn_peer.tunnel=rl_vpn_tun' in sc and 'rl_vpn_tun.kind=amneziawg' in sc)
check('script: values quoted (a «\'» in a name cannot break out)', "'\"'\"'" in fs.script(dict(p, name="A'B"), '10.0.0.0/24') and "NET=10.0.0.0/24" in fs.script(p, '10.0.0.0/24'))
check('script: links and subscription', 'rl_vpn_l3=connection_link' in fs.script(L) and 'rl_vpn_sub.url=' in fs.script(S))
keep = fs.script(p, '', replace_all=False)
check('script: «keep the other sections» deletes only ours', 'rl_ru|rl_vpn) uci -q delete' in keep and 'do uci -q delete forkop.$s; done' not in keep)
check('script: never prints a key', '@@why' in sc and 'grep -v -i -E "key|uuid|password"' in sc)
r = fs.result('@@bak /root/forkop.rl-1.bak\n@@net 192.168.22.0/24\n@@ok\n')
check('result: ok, network, backup', r['ok'] and r['net'] == '192.168.22.0/24' and r['backup'] == '/root/forkop.rl-1.bak')
r = fs.result('@@bak /root/x\n@@net n\n@@why boom\n@@why2 \n@@restored\n')
check('result: failed and restored', not r['ok'] and r['restored'] and r['why'] == 'boom')
st = fs.parse_status('@@lan 192.168.22.0/24\n@@sec section russia_direct  |bypass|Россия напрямую\n@@sec section rl_ru  |bypass|Россия напрямую\n'
                     '@@sec section rl_vpn  |connection|Зарубеж через VPN\n@@sec tunnel awg_nl abroad_awg ||AWG NL\n@@run\n@@end\n')
check('status: sections, ours marked, applied, running', st['lan'] == '192.168.22.0/24' and st['applied'] and st['running']
      and [s['ours'] for s in st['sections']] == [False, True, True] and st['children'][0]['section'] == 'abroad_awg')
print('BAD' if bad else 'GOOD')
sys.exit(1 if bad else 0)
