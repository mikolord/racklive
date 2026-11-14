"""VPN clients of a VPS (rackd/vpnload.py): parsing the server's answer, the room-left estimate, the main server's total, the script's shape.   python tools/vpnload_test.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import vpnload as V

bad = 0
def check(name, ok):
    global bad
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok:
        bad += 1

NOW = 1_800_000_000
OUT = f'''@@t {NOW}
@@id 0
@@cpu 1000 5000
@@nproc 2
@@mem 2000000 1000000
@@net eth0 1000000 2000000
@@xui 40 38 7
@@wg amnezia-awg wg0 {NOW - 20}
@@wg amnezia-awg wg0 {NOW - 100}
@@wg amnezia-awg wg0 {NOW - 4000}
@@wg amnezia-awg wg0 0
@@wg host-wg wg1 {NOW - 5}
@@gen xray 9
@@gen hysteria 4
@@end
'''
p = V.parse(OUT)
byid = {s['id']: s for s in p['sources']}
check('3x-ui: configured clients and online from its database', byid['3xui']['clients'] == 38 and byid['3xui']['online'] == 7 and p['panel'] == '3x-ui')
check('AmneziaWG: 4 peers, 2 with a fresh handshake', byid['wg:amnezia-awg']['clients'] == 4 and byid['wg:amnezia-awg']['online'] == 2 and byid['wg:amnezia-awg']['label'].startswith('AmneziaWG'))
check('plain WireGuard is named so', byid['wg:host-wg']['label'] == 'WireGuard' and byid['wg:host-wg']['online'] == 1)
check('xray is not counted twice when 3x-ui already has it', 'gen:xray' not in byid)
check('another daemon is counted by its connections', byid['gen:hysteria']['online'] == 4 and byid['gen:hysteria']['clients'] is None)
row = V.sample_of(p)
check('one history row: online 7+2+1+4, clients 38+4+1', row[5] == 14 and row[6] == 43 and row[7] == 50.0 and row[3:5] == [1000000, 2000000])
p2 = V.parse('@@t 5\n@@cpu 1 2\n@@net e 1 1\n@@gen xray 12\n@@end\n')
check('without a panel xray is counted by connections', [s['id'] for s in p2['sources']] == ['gen:xray'] and p2['sources'][0]['online'] == 12)
p3 = V.parse('@@t 5\n@@cpu 1 2\n@@net e 1 1\n@@rwc remnawave-db\n@@rw 30 25\n@@gen xray 6\n@@end\n')
check('Remnawave: users from the panel database, online by xray', p3['panel'] == 'Remnawave' and p3['sources'][0]['clients'] == 25 and p3['sources'][0]['online'] == 6 and len(p3['sources']) == 1)
p4 = V.parse('@@t 5\n@@cpu 1 2\n@@net e 1 1\n@@end\n')
check('nothing recognised: no sources', p4['sources'] == [] and V.sample_of(p4)[5] is None)

# history: 3 days, 5-minute steps; 2 Mbit/s and 1 % of the processor per connected client, a 3 % baseline
def history(days=3, per_mbps=2, per_cpu=1.0, clients=60, base=3.0, step=300):
    rows, rx, tx, busy, tot = [], 0, 0, 0, 0
    t0 = NOW - days * 86400
    for k in range(int(days * 86400 / step) + 1):
        t = t0 + k * step
        on = 5 + (k % 288) * 15 // 288                    # 5 … 20 online during a day
        bps = on * per_mbps * 1e6
        rx += int(bps / 8 * step); tx += int(bps / 8 * step)
        cpu = base + on * per_cpu
        tot += 200 * step; busy += int(cpu / 100 * 200 * step)
        rows.append([t, busy, tot, rx, tx, on, clients, 40.0])
    return rows
H = history()
r = V.analyze(H, {'mbps': 1000, 'margin': 75}, NOW)
check('detected, 3 days, medium confidence', r['detected'] and 2.9 < r['days'] < 3.1 and r['confidence'] == 'mid')
check('the processor is the limit: ~ (75 − 22) / 1 %', r['bottleneck'] == 'cpu' and 45 <= r['k'] <= 60)
check('the channel alone would take far more', r['net']['k'] > 300 and 38 <= r['net']['p95Mbps'] <= 42)
check('new people at the share who are online together', r['users'] and r['users'] > r['k'])
r2 = V.analyze(H, {'mbps': 100, 'margin': 75}, NOW)
check('a slow channel becomes the limit', r2['bottleneck'] == 'net' and r2['k'] < r['k'])
r3 = V.analyze(H, {'mbps': 1000, 'quotaTb': 1, 'margin': 75}, NOW)
check('a monthly traffic limit is counted (out only)', r3['quota'] and r3['quota']['monthTb'] > 0 and 'k' in r3['quota'])
r4 = V.analyze(history(per_cpu=0.0), {'mbps': 0}, NOW)
check('no channel typed and no CPU cost: no number, a hint instead', r4['k'] is None and r4['notes'])
check('too little history: a hint, no number', V.analyze(H[-5:], {'mbps': 1000}, NOW)['k'] is None and V.analyze(H[-5:], {'mbps': 1000}, NOW)['notes'])
rb = [list(x) for x in H]
for x in rb[300:]:
    x[1] = max(0, x[1] - rb[300][1]); x[2] = max(1, x[2] - rb[300][2]); x[3] -= rb[300][3]; x[4] -= rb[300][4]
check('a reboot (the counters restart) does not break the estimate', V.analyze(rb, {'mbps': 1000}, NOW)['k'] is not None)
none = [[x[0], x[1], x[2], x[3], x[4], None, None, 40.0] for x in H]
rn = V.analyze(none, {'mbps': 1000}, NOW)
check('no VPN found: says so', not rn['detected'] and 'Не нашёл VPN' in rn['notes'][0])

# the main server
devs = [{'id': 'a', 'name': 'Главный', 'vpn': {'on': True, 'main': True, 'mbps': 1000, 'margin': 75}},
        {'id': 'b', 'name': 'Узел 2', 'vpn': {'on': True, 'mbps': 100, 'margin': 75}},
        {'id': 'c', 'name': 'Без VPN', 'vpn': {'on': False}}]
hist = {'a': {'s': history(), 'src': [], 'panel': '3x-ui'}, 'b': {'s': history(clients=0), 'src': [], 'panel': None}}
s = V.summary(devs, hist, NOW)
check('only the devices with the switch on are counted', set(s['devices']) == {'a', 'b'})
sy = s['system']
check('main server: nodes, clients of the panel, room in all nodes together', sy and sy['nodes'] == 2 and sy['clients'] == 60 and sy['k'] == s['devices']['a']['k'] + s['devices']['b']['k'])
check('new people for the whole VPN: more than the connections, taken at the peak share', sy['users'] > sy['k'] and sy['users'] < sy['k'] * 60)
check('the weakest node is named', sy['weakest'][0] == 'Узел 2' and sy['weakest'][1] == s['devices']['b']['k'])
check('without a main server there is no total', V.summary([dict(devs[1])], hist, NOW)['system'] is None)

# settings
c = V.clean({'on': True, 'main': True, 'mbps': '1000', 'quotaTb': '7,5', 'margin': 5000, 'quotaMode': 'x'})
check('clean: junk is tamed', c == {'on': True, 'main': True, 'mbps': 1000, 'quotaTb': 0, 'quotaMode': 'out', 'margin': 95})
check('clean: «main» needs the switch', V.clean({'on': False, 'main': True})['main'] is False)

# the script: read-only, no secret leaves the server
sc = V.SCRIPT
check('script never prints a key: WireGuard lines are cut to interface and handshake', "print \"@@wg\", s, $1, $6}" in sc and 'private' not in sc.lower())
check('script is read-only: no restart / write / delete of anything of the VPN', not any(w in sc for w in ('systemctl', 'restart', 'rm -rf', 'DELETE', 'UPDATE ', 'INSERT', ' > /etc', 'x-ui setting')))
check('the database is opened read-only', 'mode=ro' in sc)
print('BAD' if bad else 'GOOD')
sys.exit(1 if bad else 0)
