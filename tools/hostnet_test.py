#!/usr/bin/env python3
"""Network of the panel's own machine: parsers (real Synology output), validation, the generated scripts (checked with `sh -n`).
    python tools/hostnet_test.py"""
import os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import hostnet as H  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


SYNO = '''System network interface list: 

Host Name: Nass 
Network interface: ovs_eth0 
DHCP 
IP: 192.168.1.3 
Mask: 255.255.255.0 
Gateway: 192.168.1.1 
DNS: 192.168.1.1 
MTU Setting: 1500 

Host Name: Nass 
Network interface: ovs_eth1 
Manual IP 
IP: 192.168.1.86 
Mask: 255.255.255.0 
Gateway: 192.168.1.1 
DNS: 192.168.1.1 
MTU Setting: 1500 

Host Name: Nass 
Network interface: ovs_eth4 
'''
s = H.parse_synonet(SYNO)
check('Synology: two interfaces, DHCP and fixed, with mask, gateway, DNS', len(s) == 2 and s[0]['mode'] == 'dhcp' and s[0]['ip'] == '192.168.1.3' and s[1]['mode'] == 'static' and s[1]['gateway'] == '192.168.1.1' and s[1]['mtu'] == 1500, s)
UCI = '''network.loopback=interface
network.loopback.proto='static'
network.loopback.ipaddr='127.0.0.1'
network.lan=interface
network.lan.proto='static'
network.lan.ipaddr='192.168.88.1'
network.lan.netmask='255.255.255.0'
network.lan.device='br-lan'
network.wan=interface
network.wan.proto='dhcp'
network.wan.device='eth1'
network.wan6=interface
network.wan6.proto='dhcpv6'
@@resolv
nameserver 192.168.8.1
'''
u = H.parse_uci(UCI)
check('OpenWrt: lan fixed, wan DHCP, loopback and wan6 are not listed', [(i['name'], i['mode']) for i in u] == [('lan', 'static'), ('wan', 'dhcp')], u)
LIN = '''@@os
Ubuntu 24.04 LTS
@@mgr
networkmanager
@@nm
== Wired connection 1:eth0:802-3-ethernet
ipv4.method:manual
ipv4.addresses:192.168.1.50/24
ipv4.gateway:192.168.1.1
ipv4.dns:1.1.1.1
@@addr
2: eth0    inet 192.168.1.50/24 brd 192.168.1.255 scope global eth0
@@route
default via 192.168.1.1 dev eth0
@@resolv
nameserver 1.1.1.1
'''
l = H.parse_linux(LIN)
check('Linux with NetworkManager: connection, mode, address', l['manager'] == 'networkmanager' and l['interfaces'][0]['conn'] == 'Wired connection 1' and l['interfaces'][0]['mode'] == 'static' and l['interfaces'][0]['ip'] == '192.168.1.50' and l['interfaces'][0]['gateway'] == '192.168.1.1', l)
check('masks: /24 ↔ 255.255.255.0', H.mask_to_prefix('24') == 24 and H.mask_to_prefix('255.255.255.0') == 24 and H.prefix_to_mask(16) == '255.255.0.0' and H.mask_to_prefix('255.0.255.0') is None)

cur = s[1]
def chk(**k):
    return H.check_change(dict({'iface': 'ovs_eth1', 'mode': 'static', 'ip': '192.168.1.90', 'mask': '24', 'gateway': '192.168.1.1', 'dns': '1.1.1.1 8.8.8.8'}, **k), s)
ok, err = chk()
check('a correct fixed address is accepted', ok and not err and ok['prefix'] == 24 and ok['dns'] == ['1.1.1.1', '8.8.8.8'], (ok, err))
for k, why in ((dict(ip='192.168.1.0'), 'the network address'), (dict(ip='192.168.1.255'), 'the broadcast address'), (dict(ip='abc'), 'nonsense address'), (dict(mask='255.0.255.0'), 'a broken mask'),
               (dict(gateway='10.9.9.1'), 'a gateway from another network'), (dict(gateway='192.168.1.90'), 'the gateway equal to the address'), (dict(dns='x'), 'a bad DNS'), (dict(ip='127.0.0.1'), 'loopback'),
               (dict(iface='nope'), 'an unknown interface'), (dict(mode='x'), 'an unknown mode')):
    check('refused: ' + why, chk(**k)[1])
check('DHCP needs only the interface', H.check_change({'iface': 'ovs_eth1', 'mode': 'dhcp'}, s)[0]['mode'] == 'dhcp')

for method, ifs, iface in (('synology', s, 'ovs_eth1'), ('openwrt', u, 'lan')):
    for body in ({'mode': 'static', 'ip': '192.168.1.90', 'mask': '24', 'gateway': '192.168.1.1', 'dns': '1.1.1.1'}, {'mode': 'dhcp'}):
        ch, err = H.check_change(dict(body, iface=iface), ifs)
        script = H.apply_script(method, ch)
        f = tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False, encoding='utf-8'); f.write(script); f.close()
        r = subprocess.run(['sh', '-n', f.name], capture_output=True, text=True) if shutil.which('sh') else None
        os.unlink(f.name)
        check(f'{method}/{body["mode"]}: the script is valid shell', r is None or r.returncode == 0, r and r.stderr)
        check(f'{method}/{body["mode"]}: it saves a way back and a timer before the change', 'rl-net-revert.sh' in script and f'sleep {H.ROLLBACK_SECONDS}' in script and script.index('rl-net-revert') < script.index('rl-net-apply.sh; rm'))
ch, _ = H.check_change({'iface': 'ovs_eth1', 'mode': 'static', 'ip': '192.168.1.90', 'mask': '24', 'gateway': '192.168.1.1', 'dns': '1.1.1.1'}, s)
ap, rv, _ = H.commands('synology', ch)
check('Synology: new settings and the old ones as the way back', 'synonet --manual ovs_eth1 192.168.1.90 255.255.255.0' in ap and 'synonet --manual ovs_eth1 192.168.1.86 255.255.255.0' in rv, (ap, rv))
ch, _ = H.check_change({'iface': 'ovs_eth0', 'mode': 'static', 'ip': '192.168.1.99', 'mask': '24', 'gateway': '192.168.1.1', 'dns': ''}, s)
check('Synology: an interface that was on DHCP goes back to DHCP', 'synonet --dhcp ovs_eth0' in H.commands('synology', ch)[1])
nmc = l['interfaces'][0]
ch, _ = H.check_change({'iface': 'eth0', 'mode': 'dhcp'}, l['interfaces'])
ap, rv, _ = H.commands('networkmanager', ch)
check('NetworkManager: DHCP on, the old fixed address is the way back', 'ipv4.method auto' in ap and "ipv4.addresses 192.168.1.50/24" in rv and "'Wired connection 1'" in ap, (ap, rv))
try:
    H.commands('netplan', ch); check('unsupported managers are refused', False)
except ValueError:
    check('unsupported managers are refused', True)
for sc in (H.CONFIRM_SCRIPT, H.REVERT_NOW_SCRIPT, H.READ_SYNO, H.READ_OWRT, H.READ_LINUX):
    f = tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False, encoding='utf-8'); f.write(sc); f.close()
    r = subprocess.run(['sh', '-n', f.name], capture_output=True, text=True) if shutil.which('sh') else None
    os.unlink(f.name)
    check('read / confirm script is valid shell: ' + sc.strip().split('\n')[0][:40], r is None or r.returncode == 0, r and r.stderr)
lv = H.local_view()
check('the local view is a dict with interfaces, gateway and DNS', set(lv) >= {'interfaces', 'gateway', 'dns'})
print('\n' + ('ВСЁ OK' if not FAILS else 'ЕСТЬ ОШИБКИ: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
