"""Clients of a remote device: hidden on the map until the device is tapped (layoutMap in web/src/40_map.jsx, run in Node).   python tools/map_remote_test.py"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'web', 'src', '40_map.jsx'), encoding='utf-8').read()
m = re.search(r'^const M = .*?$', src, re.M)
a = src.index('function layoutMap('); b = src.index('/* other ways to see the same network')
js = m.group(0) + '\nconst unitDevIds = u => u.devices || [];\n' + src[a:b] + r'''
const client = (id, label) => ({ id, label, sub: '10.0.0.' + id.length, kind: 'other', client: true });
const data = (over = {}) => ({ map: { positions: {} }, racks: [], topology: {
  nodes: [{ id: 'inet', label: 'Интернет', kind: 'internet' }, { id: 'd:main', label: 'Дом', kind: 'router' }, client('h:home', 'Дома'),
    { id: 'd:r1', label: 'Город', kind: 'router', remote: true }, client('h:a', 'Телефон'), client('h:b', 'Ноутбук'),
    { id: 'd:r2', label: 'Дача', kind: 'router', remote: true }, client('h:c', 'Камера'),
    { id: 'd:vps', label: 'VPS', kind: 'server', remote: true }],
  edges: [{ id: '1', source: 'inet', target: 'd:main', kind: 'wan' }, { id: '2', source: 'd:main', target: 'h:home', kind: 'lan' },
    { id: '3', source: 'inet', target: 'd:r1', kind: 'remote' }, { id: '4', source: 'd:r1', target: 'h:a', kind: 'lan' }, { id: '5', source: 'd:r1', target: 'h:b', kind: 'wifi' },
    { id: '6', source: 'inet', target: 'd:r2', kind: 'remote' }, { id: '7', source: 'd:r2', target: 'h:c', kind: 'lan' }, { id: '8', source: 'inet', target: 'd:vps', kind: 'remote' }, ...(over.edges || [])] } });
let bad = 0; const check = (name, ok) => { console.log((ok ? 'OK   ' : 'FAIL ') + name); if (!ok) bad++; };
const L = layoutMap(data(), {}, {});
check('closed: clients of remote devices are not on the map', !L.nodes['h:a'] && !L.pos['h:a'] && !L.nodes['h:b'] && !L.nodes['h:c']);
check('closed: no wires to them', !L.edges.some(e => ['h:a', 'h:b', 'h:c'].includes(e.target)));
check('closed: no stray cards', Object.keys(L.pos).every(id => L.nodes[id]));
check('closed: the home client stays', !!L.pos['h:home']);
check('closed: the device says how many', L.nodes['d:r1'].remoteClients === 2 && L.nodes['d:r1'].remoteOpen === false);
check('a remote device with nobody has no counter', !L.nodes['d:vps'].remoteClients);
check('search knows the hidden ones', L.hiddenClients['h:a'].parent === 'd:r1' && L.hiddenClients['h:c'].parent === 'd:r2');
const O = layoutMap(data(), {}, { 'd:r1': true });
check('opened: its clients appear', !!O.pos['h:a'] && !!O.pos['h:b']);
check('opened: with wires', O.edges.some(e => e.source === 'd:r1' && e.target === 'h:a'));
check('opened: on the left of the device', O.pos['h:a'].x + O.pos['h:a'].w < O.pos['d:r1'].x);
check('opened: the other device stays closed', !O.nodes['h:c']);
check('opened: the clients know their device (they fly out of it)', O.nodes['h:a'].remoteOf === 'd:r1' && O.nodes['h:b'].remoteIdx === 1 && !O.nodes['h:home'].remoteOf);
const A = layoutMap(data(), {}, { 'd:r1': true, 'd:r2': true });
const over = (p, q) => p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h;
const ids = Object.keys(A.pos);
check('both opened: no card lies on another', !ids.some((x, i) => ids.slice(i + 1).some(y => over(A.pos[x], A.pos[y]))));
const S = layoutMap(data(), {}, true);
check('the map of one house shows everything', !!S.pos['h:a'] && !!S.pos['h:c'] && !Object.keys(S.hiddenClients).length && !S.nodes['h:a'].remoteOf);
const D = data({ edges: [{ id: '9', source: 'h:a', target: 'd:sw', kind: 'lan' }] }); D.topology.nodes.push({ id: 'd:sw', label: 'Свитч', kind: 'switch' });
const N = layoutMap(D, {}, {});
check('a client that a device hangs from stays visible', !!N.nodes['h:a'] && N.nodes['d:r1'].remoteClients === 1 && !N.nodes['h:b']);
console.log(bad ? 'BAD' : 'GOOD');
'''
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(js)
try:
    r = subprocess.run(['node', f.name], capture_output=True, text=True, encoding='utf-8', timeout=30)
finally:
    os.remove(f.name)
print(r.stdout + r.stderr)
sys.exit(0 if r.stdout.strip().endswith('GOOD') else 1)
