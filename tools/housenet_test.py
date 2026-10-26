"""«Сеть дома»: карта сети, суженная до устройств и шкафов одного дома, — те самые функции scopeData / houseScope из web/src, прогнанные в Node на настоящих данных демо-приложения.
Run: python tools/housenet_test.py   (prints ВСЁ OK; skipped without Node)"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
node = shutil.which('node')
if not node:
    print('нет Node — проверка «Сети дома» пропущена\n\nВСЁ OK')
    sys.exit(0)
rd = lambda n: open(os.path.join(ROOT, 'web', 'src', n), encoding='utf-8').read()
rack, mapsrc, plan = rd('30_rack.jsx'), rd('40_map.jsx'), rd('47_plan.jsx')
unit = re.search(r'^const SHELF_MAX = .*$', rack, re.M).group(0) + '\n' + re.search(r'^const unitDevIds = .*$', rack, re.M).group(0) + '\n'
scope = mapsrc[mapsrc.index('function scopeData('):mapsrc.index('function MapView(')]
hs = plan[plan.index('function houseScope('):plan.index('/* Wi-Fi coverage')]

APP = 8941
data = tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(APP), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
app = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else f'   [{extra}]'))
    if not ok:
        bad.append(name)


try:
    st = None
    for _ in range(60):
        try:
            st = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{APP}/api/state', timeout=10).read()); break
        except Exception:
            time.sleep(.5)
    js = unit + scope + hs + '''
const data = JSON.parse(process.env.STATE);
const topo = data.topology, ids = new Set(topo.nodes.map(n => n.id));
const out = [];
const t = (name, ok, extra) => out.push([name, !!ok, extra === undefined ? '' : String(extra)]);
const par = {}; topo.edges.filter(e => !e.extra && !e.manual).forEach(e => { par[e.target] = e.source; });
const depth = id => { let n = 0; while (par[id] && n < 50) { id = par[id]; n++; } return n; };
// leaf device with the longest chain to the internet
const dev = topo.nodes.filter(n => String(n.id).startsWith('d:') && depth(n.id) >= 2).sort((a, b) => depth(b.id) - depth(a.id))[0];
t('в демо есть устройство с цепочкой до роутера', !!dev, dev && dev.id);
const one = scopeData(data, { devices: new Set([dev.id.slice(2)]), racks: new Set() });
const keep = new Set(one.topology.nodes.map(n => n.id));
t('узлы дома — часть общей карты', [...keep].every(id => ids.has(id)));
t('устройство дома на месте', keep.has(dev.id));
let up = dev.id, chain = true; while (par[up]) { up = par[up]; if (!keep.has(up)) chain = false; }
t('вся цепочка вверх до роутера и интернета сохранена', chain && keep.has(up), up);
t('чужих устройств нет: карта дома меньше общей', keep.size < ids.size && keep.size >= 3, keep.size + ' из ' + ids.size);
t('связи только между оставшимися узлами', one.topology.edges.every(e => keep.has(e.source) && keep.has(e.target)));
t('шкафы без выбранных — не попадают', one.racks.length === 0);
const rk = data.racks.find(r => (r.kind || 'rack') === 'rack' && r.units.some(u => unitDevIds(u).length));
const two = scopeData(data, { devices: new Set(), racks: new Set([rk.id]) });
const k2 = new Set(two.topology.nodes.map(n => n.id));
const inRack = rk.units.flatMap(u => unitDevIds(u)).filter(id => ids.has('d:' + id));
t('шкаф дома: все устройства шкафа на карте дома', inRack.length > 0 && inRack.every(id => k2.has('d:' + id)), inRack.length);
t('шкаф дома: в данных остаётся только он', two.racks.length === 1 && two.racks[0].id === rk.id);
const none = scopeData(data, { devices: new Set(), racks: new Set() });
t('пустой дом — пустая карта (без падений)', none.topology.nodes.length === 0 && none.topology.edges.length === 0);
// houseScope: what stands on the floors
const b = { id: 'b1', name: 'Дом', floors: [{ items: [{ kind: 'device', ref: 'x1' }, { kind: 'place', ref: 'r1' }, { kind: 'label', text: 'подпись' }] }, { items: [{ kind: 'device', ref: 'x2' }] }] };
const s = houseScope(b, data, () => 1, () => 2);
t('houseScope собирает устройства и шкафы со всех этажей', s.seed.devices.size === 2 && s.seed.devices.has('x1') && s.seed.devices.has('x2') && s.seed.racks.size === 1 && s.seed.racks.has('r1'));
t('houseScope: ключ меняется, когда в доме поставили устройство', houseScope({ ...b, floors: [...b.floors, { items: [{ kind: 'device', ref: 'x3' }] }] }, data, () => 1, () => 2).key !== s.key);
console.log(JSON.stringify(out));
'''
    p = subprocess.run([node, '-e', js], capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, STATE=json.dumps(st)), timeout=60)
    if p.returncode:
        check('скрипт Node отработал', False, p.stderr[-400:])
    else:
        for name, ok, extra in json.loads(p.stdout.strip().splitlines()[-1]):
            check(name, ok, extra)
finally:
    app.terminate()
    try:
        app.wait(timeout=10)
    except Exception:
        app.kill()
    shutil.rmtree(data, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
sys.exit(1 if bad else 0)
