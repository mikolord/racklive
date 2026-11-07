"""«Сетевой доктор»: parsing real command output and what the analysis concludes. Run: python tools/doctor_test.py (prints ВСЁ OK)"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import doctor as D  # noqa: E402

fails = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)[:400]))
    if not ok:
        fails.append(name)


# ── parsers ──
ss = ['tcp LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))', 'tcp LISTEN 0 4096 [::]:22 [::]:* users:(("sshd",pid=1,fd=4))',
      'tcp LISTEN 0 80 127.0.0.1:3306 0.0.0.0:* users:(("mariadbd",pid=2,fd=20))', 'udp UNCONN 0 0 127.0.0.53%lo:53 0.0.0.0:* users:(("systemd-resolve",pid=3,fd=13))',
      'tcp LISTEN 0 10 192.168.1.3:5000 0.0.0.0:*', 'tcp LISTEN 0 4096 *:443 *:* users:(("nginx",pid=4,fd=6))']
r = {(x['proto'], x['port']): x for x in D.parse_listen(ss)}
check('ss: v4 and v6 of a port are one row, the process is known', sum(1 for k in r if k[1] == 22) == 1 and r[('tcp', 22)]['proc'] == 'sshd' and r[('tcp', 22)]['exposure'] == 'all')
check('ss: loopback, LAN and «*» are told apart', r[('tcp', 3306)]['exposure'] == 'local' and r[('tcp', 5000)]['exposure'] == 'lan' and r[('tcp', 443)]['exposure'] == 'all' and r[('udp', 53)]['exposure'] == 'local', r)
ns = D.parse_listen(['tcp        0      0 0.0.0.0:222             0.0.0.0:*               LISTEN      941/dropbear', 'udp        0      0 0.0.0.0:1900            0.0.0.0:*                           77/upnpd', 'tcp 0 0 :::80 :::* LISTEN 5/lighttpd'])
n = {x['port']: x for x in ns}
check('busybox netstat is understood too', n[222]['proc'] == 'dropbear' and n[1900]['proto'] == 'udp' and n[80]['exposure'] == 'all', ns)
shadow = [l for l in D.SCRIPT.splitlines() if '/etc/shadow' in l]
check('secret-free: the script never prints password hashes', shadow and not any(re.search(r'print[^}]*\$2|cat /etc/shadow|grep [^|]*/etc/shadow', l) for l in shadow) and any("'$2==\"\"{print \"emptypw \" $1}'" in l for l in shadow), shadow)
check('the check script changes nothing', not re.search(r'\b(apt-get (install|update|upgrade)|systemctl (start|stop|restart|enable)|ufw (enable|deny|allow)|rm |chmod |> */etc)', D.SCRIPT))
check('host name from any form of address', D.hostname({'host': 'https://192.168.1.3:5001'}) == '192.168.1.3' and D.hostname({'host': '1.2.3.4'}) == '1.2.3.4' and D.hostname({'host': None}) == '')
check('private = not exposed, public or a domain = exposed', not D.is_public('192.168.1.3') and D.is_public('8.8.8.8') and D.is_public('a.example.com') and not D.is_public(''))

# ── a bad public server ──
VPS = {'id': 'v', 'driver': 'ssh', 'kind': 'server', 'host': '8.8.8.8', 'password': 'x'}
a = D.analyze(VPS, D.sections(D.DEMO_OUT), [22, 443, 6379])
ids = {f['id'].split(':', 2)[2]: f for f in a['findings']}
ch = {c['id']: c for c in a['checks']}
check('redis seen from outside is critical', ids['port:6379']['level'] == 'bad', ids.keys())
check('no fail2ban + password + 1342 failed logins is critical, with a fix button', ids['guard:none']['level'] == 'bad' and ids['guard:none']['fix']['id'] == 'fail2ban' and '1342' in ids['guard:none']['text'])
check('SSH by password warns that Rack Live itself logs in by password', 'Rack Live' in ids['ssh:password']['how'] and ids['ssh:password']['level'] == 'warn')
check('no firewall: the commands allow SSH before enabling', ids['fw:none']['cmd'].index('ufw allow 22/tcp') < ids['fw:none']['cmd'].index('ufw enable') and '6379' not in ids['fw:none']['cmd'], ids['fw:none']['cmd'])
check('security updates, auto updates, reboot', ids['upd:security']['level'] == 'warn' and 'upd:auto' in ids and 'upd:reboot' in ids)
check('the ordinary open port 443 does not raise an alarm', ids['public']['level'] == 'info' and '443' in ids['public']['text'])
check('a port listening only on loopback is not a finding', 'port:3306' not in ids)
sc = D.rank(a['findings'])
check('the score falls and the order is bad → warn → info', sc['score'] < 60 and sc['findings'][0]['level'] == 'bad' and sc['findings'][-1]['level'] == 'info', sc['score'])
check('«это нормально» takes a finding out of the score', D.rank(a['findings'], [ids['port:6379']['id']])['score'] == sc['score'] + 20)

# ── a clean server ──
GOOD = '''@@id
0
@@os
id ubuntu
name Ubuntu 24.04
@@listen
tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=1,fd=3))
@@sshd
port 22
permitrootlogin prohibit-password
passwordauthentication no
permitemptypasswords no
@@guard
installed
running
jail sshd 3 120
@@fw
ufw active
@@updates
pending 0
security 0
lists_fresh 5
auto yes
@@accounts
uid0 root
shadow_read yes
shadow_mode 640
@@auth
fails 40
@@docker
@@end
'''
g = D.analyze(VPS, D.sections(GOOD), [22])
check('a clean server: no findings, everything checked', not g['findings'] and all(c['state'] == 'ok' for c in g['checks']), [(f['id']) for f in g['findings']] or g['checks'])
check('fail2ban: bans are reported', '3' in next(c for c in g['checks'] if c['id'] == 'guard')['note'] and '120' in next(c for c in g['checks'] if c['id'] == 'guard')['note'])
x = D.analyze(VPS, D.sections(GOOD.replace('jail sshd 3 120\n', '')), [22])
check('fail2ban running without an SSH jail is not fine', any(f['id'].endswith('guard:jail') for f in x['findings']))
x = D.analyze(VPS, D.sections(GOOD.replace('running\njail sshd 3 120\n', '')), [22])
check('fail2ban installed but stopped is a problem on a public server', next(c for c in x['checks'] if c['id'] == 'guard')['state'] == 'bad')
x = D.analyze(VPS, D.sections(GOOD.replace('installed\nrunning\njail sshd 3 120\n', 'other CrowdSec\n')), [22])
check('CrowdSec counts as protection', next(c for c in x['checks'] if c['id'] == 'guard')['state'] == 'ok' and not any('guard' in f['id'] for f in x['findings']))

# ── honesty: what could not be seen is not green ──
x = D.analyze(VPS, {}, [443])
check('no way inside: everything inside is «не проверено», not ok', all(c['state'] == 'unknown' for c in x['checks'] if c['id'] != 'ports'), x['checks'])
x = D.analyze({'id': 'p', 'driver': 'ping', 'host': '192.168.1.50'}, {}, None)
check('neither inside nor knocked: ports are «не проверено» too', all(c['state'] == 'unknown' for c in x['checks']), x['checks'])
noroot = GOOD.replace('@@id\n0', '@@id\n1000').replace('shadow_read yes\nshadow_mode 640\n', '').replace('ufw active\n', '').replace('port 22\npermitrootlogin prohibit-password\npasswordauthentication no\npermitemptypasswords no\n', '').replace('installed\nrunning\njail sshd 3 120\n', '')
x = D.analyze(VPS, D.sections(noroot), [22])
c = {y['id']: y['state'] for y in x['checks']}
check('without root the unreadable parts are not reported as fine', c['fw'] == 'unknown' and c['accounts'] == 'unknown' and c['ssh'] == 'unknown' and any(f['id'].endswith('noroot') for f in x['findings']), c)

# ── other devices ──
LAN = dict(VPS, host='192.168.1.20', id='l')
x = D.analyze(LAN, D.sections(D.DEMO_OUT), [22, 443, 6379])
lv = {f['id'].split(':', 2)[2]: f['level'] for f in x['findings']}
check('in the local network the same server is calmer', lv['port:6379'] == 'info' and lv['guard:none'] == 'info' and 'fw:none' not in lv, lv)
RT = {'id': 'r', 'driver': 'openwrt', 'kind': 'router', 'host': '192.168.8.10', 'password': 'x'}
x = D.analyze(RT, D.sections('@@id\n0\n@@os\nopenwrt yes\n@@listen\ntcp 0 0 0.0.0.0:22 0.0.0.0:* LISTEN 9/dropbear\n@@sshd\ndropbear yes\n@@guard\n@@fw\n@@updates\n@@accounts\nuid0 root\nshadow_read yes\nemptypw daemon\n@@auth\n@@docker\n@@end\n'), None)
c = {y['id']: y['state'] for y in x['checks']}
check('a router is not told to install fail2ban and ufw', c['guard'] == 'na' and c['fw'] == 'na' and c['ssh'] == 'na' and not any('guard' in f['id'] or 'fw:' in f['id'] or 'acc:empty' in f['id'] for f in x['findings']), (c, [f['id'] for f in x['findings']]))
SY = {'id': 's', 'driver': 'synology', 'kind': 'nas', 'host': 'https://192.168.1.3:5001', 'password': 'x'}
x = D.analyze(SY, D.sections('@@id\n0\n@@os\nsyno 7.2\n@@listen\n@@sshd\n@@guard\n@@fw\n@@updates\n@@accounts\nuid0 root\nshadow_read yes\n@@auth\n@@docker\n@@end\n'), None)
c = {y['id']: y['state'] for y in x['checks']}
check('Synology: its own auto block is not claimed as checked, no fail2ban button', c['guard'] == 'unknown' and not any((f.get('fix') or {}).get('id') == 'fail2ban' for f in x['findings']) and x['facts']['os'] == 'DSM 7.2', (c, x['facts']))
ufw_docker = GOOD.replace('@@docker\n', '@@docker\nweb|0.0.0.0:8080->80/tcp, [::]:8080->80/tcp\npriv /box true\n')
x = D.analyze(VPS, D.sections(ufw_docker), [22, 8080])
ii = [f['id'].split(':', 2)[2] for f in x['findings']]
check('Docker publishing past ufw and privileged containers are noticed', 'docker:ufw' in ii and 'docker:priv' in ii and '8080' in next(f for f in x['findings'] if f['id'].endswith('docker:ufw'))['text'], ii)
x = D.analyze(VPS, D.sections(GOOD.replace('uid0 root\n', 'uid0 root\nuid0 toor\nemptypw bob\n').replace('shadow_mode 640', 'shadow_mode 644')), [22])
ii = {f['id'].split(':', 2)[2]: f['level'] for f in x['findings']}
check('a second UID 0, empty passwords and a readable shadow are critical', ii.get('acc:uid0') == ii.get('acc:empty') == ii.get('acc:shadow') == 'bad', ii)

many = [f'udp UNCONN 0 0 0.0.0.0:{p} 0.0.0.0:* users:(("xray",pid=9,fd=1))' for p in range(33000, 33300)]
x = D.analyze(VPS, D.sections('@@id\n0\n@@listen\n' + '\n'.join(many) + '\n@@end\n'), [])
check('hundreds of short-lived UDP ports of one program become one row', len(x['ports']) == 1 and x['ports'][0]['count'] == 300, len(x['ports']))
x = D.analyze(SY, D.sections('@@id\n0\n@@listen\ntcp LISTEN 0 1 0.0.0.0:23 0.0.0.0:* users:(("inetd",pid=1,fd=1))\n@@end\n'), None)
check('telnet on a NAS in the local network is worth fixing', next(f for f in x['findings'] if f['id'].endswith('port:23'))['level'] == 'warn')
x = D.analyze(RT, D.sections('@@id\n0\n@@listen\ntcp LISTEN 0 1 0.0.0.0:23 0.0.0.0:*\n@@accounts\n@@end\n'), None)
check('telnet on a router in the local network is only a note, its accounts do not apply', next(f for f in x['findings'] if f['id'].endswith('port:23'))['level'] == 'info' and next(c for c in x['checks'] if c['id'] == 'accounts')['state'] == 'na')

# ── no ss, no netstat: the kernel's tables ──
pr = {(r['proto'], r['port']): r for r in D.parse_listen(['proc tcp 00000000:00DE', 'proc tcp 0100007F:0CEA', 'proc tcp 0101A8C0:0050', 'proc tcp 00000000000000000000000000000000:0539',
                                                          'proc tcp 00000000000000000000000001000000:1F90', 'proc udp 00000000:076C', 'proc tcp bad:zz'])}
check('/proc/net: port and address are decoded, all / loopback / LAN are told apart', pr[('tcp', 222)]['exposure'] == 'all' and pr[('tcp', 3306)]['exposure'] == 'local' and pr[('tcp', 80)]['exposure'] == 'lan' and pr[('tcp', 80)]['addr'] == '192.168.1.1', pr)
check('/proc/net: IPv6 too, UDP too, garbage is skipped', pr[('tcp', 1337)]['exposure'] == 'all' and pr[('tcp', 8080)]['exposure'] == 'local' and ('udp', 1900) in pr and len(pr) == 6, pr)
check('the script falls back to /proc/net when ss and netstat give nothing', '/proc/net/$f' in D.SCRIPT and '"proc "' in D.SCRIPT)
x = D.analyze(VPS, D.sections('@@id\n0\n@@listen\n@@end\n'), [22])
check('an empty list of ports is «не проверено», never «всё в порядке»', next(c for c in x['checks'] if c['id'] == 'ports')['state'] == 'unknown')

# ── what a router opens to the internet ──
ST = {'security': {'forwards': [{'proto': 'tcpudp', 'port': '2070', 'target': '00:aa', 'name': 'Diagrams'}, {'proto': 'tcpudp', 'port': '2071', 'target': '00:aa', 'name': 'W'},
                                {'proto': 'udp', 'port': '500', 'target': '00:aa', 'name': 'U'}, {'proto': 'tcp', 'port': '8000-8002', 'target': '00:bb', 'name': ''}],
                   'remote': {'http': {'port': 80, 'sslPort': 443, 'level': 'public'}}}}
ro = {r['port']: r for r in D.outside_rows(ST, {'open': [80, 2070, 8001, 777], 'checked': [80, 443, 777, 2070, 2071, 8000, 8001, 8002]}, {'00:aa': {'name': 'Synology'}})}
check('a forward that answers, and its device by name', ro['2070']['answers'] is True and ro['2070']['target'] == 'Synology' and ro['2070']['proto'] == 'tcp+udp', ro['2070'])
check('a forward that does not answer is shown as such', ro['2071']['answers'] is False)
check('a UDP forward is «не проверено», not closed', ro['500']['answers'] is None)
check('a range counts when any of its ports answers', ro['8000-8002']['answers'] is True)
check('the router\'s own service is named, an unknown port stays unknown', ro['80']['name'] == 'веб-интерфейс роутера' and not ro['777']['forward'] and ro['777']['name'] == '', (ro['80'], ro['777']))
check('order is by port number', [r['port'] for r in D.outside_rows(ST, {'open': [80], 'checked': [80]})][0] == '80')
check('Entware\'s SSH is named', next(r for r in D.outside_rows(ST, {'open': [222], 'checked': [222]}) if r['port'] == '222')['name'] == 'SSH в Entware')
ro = D.outside_rows(ST, None)
check('no outside check: forwards are listed as «не проверено», never as closed', all(r['answers'] is None for r in ro) and len(ro) == 4, ro)
check('a range of ports is limited', len(D._ports_of('1-65535')) == 64 and D._ports_of('x') == [] and D._ports_of('22') == [22])


class FakeExt:
    def __init__(s, vps=True): s.vps = vps; s.calls = 0
    def scanner(s): return {'name': 'VPS', 'driver': 'fake'} if s.vps else None
    def public_ip(s): s.calls += 1; return '198.51.100.7'


class FakeStore:
    cfg = {'devices': []}
    def _load(s, a, b): return b


class FakeApp:
    store = FakeStore()
    def __init__(s, states, ext): s.states, s.extscan = states, ext


K = {'id': 'k', 'driver': 'keenetic', 'host': '192.168.1.1', 'kind': 'router'}
d_ = D.Doctor(FakeApp({'k': {'ports': [{'kind': 'wan', 'ip': '192.168.0.2'}, {'kind': 'wan', 'ip': '198.51.100.9'}]}}, FakeExt()))
check('a router\'s own WAN address is used, not somebody else\'s', d_.outside_address(K) == '198.51.100.9')
d_ = D.Doctor(FakeApp({}, FakeExt()))
check('the home router without a WAN address falls back to the home address', d_.outside_address(K) == '198.51.100.7')
check('a remote router by its public name', d_.outside_address({'id': 'r', 'driver': 'keenetic', 'host': 'https://a.example.net'}) == 'a.example.net')
check('a router behind another router has no address of its own, a server is not asked', d_.outside_address(RT) is None and d_.outside_address(VPS) is None)
d_ = D.Doctor(FakeApp({}, FakeExt(vps=False)))
r_ = d_.check_outside(K, {}, lambda x: None)
check('without a VPS it says so instead of pretending', 'внешнего сервера' in r_['error'] and r_['open'] == [])

# ── «Полная проверка» ──
check('full scan: the result is read', D.parse_full('@@open 22,80,9901\n@@end\n') == [22, 80, 9901] and D.parse_full('@@open \n@@end\n') == [])
for bad, word in (('@@open 22\n', 'конца'), ('', 'конца'), ('@@fail на сервере нет python3\n', 'python3')):
    try:
        D.parse_full(bad); check(f'full scan: an interrupted run is an error ({word})', False)
    except D.DriverError as e:
        check(f'full scan: an interrupted run is an error ({word})', word in str(e), str(e))
check('full scan: every port, nothing is written on the VPS', 'range(1, 65536)' in D.FULL_SCAN and '__IP__' in D.FULL_SCAN and not re.search(r'>\s*/|open\(', D.FULL_SCAN.replace('open_connection(', '').replace('>/dev/null', '')))
import socket as _s  # noqa: E402
ls = _s.socket(); ls.bind(('127.0.0.1', 0)); ls.listen(5); lp = ls.getsockname()[1]
check('full scan from Rack Live really finds an open port', lp in D.knock_all('127.0.0.1', conc=500, timeout=.5), lp)
ls.close()


class FE2(FakeExt):
    def __init__(s, me=None): FakeExt.__init__(s); s.me = me
    def scanner(s): return s.me


other = {'id': 'o', 'driver': 'ssh', 'enabled': True, 'location': 'remote', 'name': 'Other'}
FakeStore.cfg = {'devices': [VPS, other]}
d_ = D.Doctor(FakeApp({}, FE2(dict(VPS))))
check('a server is never scanned from itself', d_.vps_for(VPS)['id'] == 'o')
FakeStore.cfg = {'devices': [VPS]}
d_ = D.Doctor(FakeApp({}, FE2(dict(VPS))))
check('no other VPS: none is pretended', d_.vps_for(VPS) is None)
FakeStore.cfg = {'devices': [K, other]}
d_ = D.Doctor(FakeApp({}, FE2(other)))
check('the home router can be fully checked through a VPS', d_.fullable(K) is True)
d_ = D.Doctor(FakeApp({}, FE2(None)))
FakeStore.cfg = {'devices': [K]}
check('without a VPS a router cannot, and nobody knocks on it from Rack Live', d_.fullable(K) is False)
try:
    d_.start('k', None, True); check('a full check that is not available is refused', False)
except (ValueError, Exception) as e:
    check('a full check that is not available is refused', 'недоступна' in str(e) or 'не найдено' in str(e), str(e))
FakeStore.cfg = {'devices': []}

# ── fail2ban install script ──
check('fail2ban: Rack Live is never banned and the real SSH port is used', 'ignoreip' in D.FIX_FAIL2BAN and '$ME' in D.FIX_FAIL2BAN and 'port = $P' in D.FIX_FAIL2BAN)
check('sudo: the password is not on a command line of its own', "sudo -S" in D.Doctor._as_root('x', 'p w') and "'p w'" in D.Doctor._as_root('x', 'p w'))

print('\nВСЁ OK' if not fails else f'\nОШИБОК: {fails}')
sys.exit(1 if fails else 0)
