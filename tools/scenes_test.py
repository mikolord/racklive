"""Scenes (kind: scene): the schema, the built-in scenes, the example in the guide, applying to a real plan (add / replace / undo), the demo copy.  Run: python tools/scenes_test.py"""
import io, json, os, re, subprocess, sys, tempfile, time, urllib.request, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)) if os.path.isfile(globals().get('__file__', '')) else '/app/tools', '..'))
from rackd import scenes, community as C
from rackd.store import Store

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


def pack(obj):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('plugin.json', json.dumps(obj, ensure_ascii=False))
    return b.getvalue()


# built-in scenes and the starter pass
for name, fn in (('campus', scenes.campus), ('starter', scenes.starter)):
    e, w, c = scenes.validate(fn())
    ok(f'встроенная сцена «{name}» проходит проверку', not e and c, e)
e, w, campus = scenes.validate(scenes.campus())
st = scenes.stats(campus)
ok('«Кампус» большой: >100 устройств, 3+ здания, 8+ этажей, 30+ комнат', st['devices'] > 100 and st['buildings'] >= 3 and st['floors'] >= 8 and st['rooms'] >= 30, st)

# the example inside the guide is a valid scene
g = scenes.guide_text()
ex = g[g.index('{\n  "plugin_api"'):g.index('ПРАВИЛА (проверка')]
ex = re.sub(r'//[^\n]*', '', ex)
try:
    e, w, c = scenes.validate(json.loads(ex))
    ok('пример из инструкции — настоящая рабочая сцена', not e, e)
except ValueError as ex_:
    ok('пример из инструкции — настоящая рабочая сцена', False, ex_)
ok('в инструкции есть ссылка на репозиторий', 'github.com/mikolord/racklive' in g)

# bad scenes are refused with a reason
base = scenes.starter()
bad = {
    'повтор key': dict(base, devices=base['devices'] + [dict(base['devices'][0])]),
    'неизвестный kind': dict(base, devices=[dict(base['devices'][0], kind='spaceship')] + base['devices'][1:]),
    'кабель к несуществующему': dict(base, links=[{'from': 'rt', 'port': 1, 'to': 'nope'}]),
    'порта нет у устройства': dict(base, links=[{'from': 'rt', 'port': 99, 'to': 'sw'}]),
    'порт занят дважды': dict(base, links=[{'from': 'sw', 'port': 1, 'to': 'ap1'}, {'from': 'sw', 'port': 1, 'to': 'ap2'}]),
    'wifi к не-точке': dict(base, wifi=[{'ap': 'nas', 'name': 'x'}]),
    'юнит вылез из стойки': dict(base, racks=[{'id': 'r', 'kind': 'rack', 'totalU': 2, 'units': [{'name': 'a', 'type': 'nas', 'uStart': 2, 'uSize': 3}]}]),
    'плохой ip': dict(base, devices=[dict(base['devices'][0], ip='999.1.1.1')] + base['devices'][1:]),
    'устройств нет': dict(base, devices=[]),
}
for name, sc in bad.items():
    e, w, c = scenes.validate(sc)
    ok('отклонено: ' + name, bool(e) and c is None, e)
e, w, c = scenes.validate(dict(base, plan={'buildings': [{'id': 'b', 'name': 'B', 'x': 0, 'y': 0, 'floors': [{'id': 'f', 'name': 'F', 'items': [{'kind': 'device', 'ref': 'ghost', 'x': 1, 'y': 1}]}]}]}))
ok('элемент плана с несуществующим устройством отклонён', bool(e))
big = dict(base, devices=[{'key': f'd{i}', 'name': 'x', 'kind': 'pc'} for i in range(500)])
ok('больше 400 устройств отклонено', bool(scenes.validate(big)[0]))
hostile = dict(base, title='<script>alert(1)</script>', devices=[dict(base['devices'][0], name='<img src=x onerror=alert(1)>' * 5)] + base['devices'][1:])
e, w, c = scenes.validate(hostile)
ok('имена остаются текстом, обрезаются по длине', not e and len(c['devices'][0]['name']) <= 60)

# as a package of the community family
f, err = C.read_zip(pack(scenes.starter()))
er, w, m = C.check(f)
ok('сцена принимается как пакет сообщества (kind: scene)', not er and m['kind'] == 'scene' and m['risk'] == 'low' and m['stats']['devices'] == 10, er)
er, w, m = C.check(C.read_zip(pack(dict(scenes.starter(), plugin_api=2)))[0])
ok('чужая версия формата отклонена', bool(er))
with tempfile.TemporaryDirectory() as td:
    com = C.Community(td)
    rep = com.install_zip(pack(scenes.starter()))
    ok('сцена устанавливается и попадает в список сцен', rep['ok'] and [x['id'] for x in com.scenes()] == ['my-home'] and not com.tools() and not com.for_device({'driver': 'ssh'}), rep)

# applying to a REAL plan
with tempfile.TemporaryDirectory() as td:
    store = Store(td)
    store.cfg['devices'] = [{'id': 'dRouter', 'name': 'Роутер', 'driver': 'keenetic', 'host': '192.168.1.1'}, {'id': 'dNas', 'name': 'Хранилище', 'driver': 'synology', 'host': '10.9.9.9'}]
    store.cfg['plan'] = {'buildings': [{'id': 'old', 'name': 'Старый дом', 'x': 0, 'y': 0, 'floors': []}], 'poles': [], 'links': []}
    store.cfg['racks'] = [{'id': 'oldrack', 'name': 'Старый шкаф', 'totalU': 6, 'kind': 'rack', 'units': []}]
    store.cfg['settings']['title'] = 'Моя сеть'
    clean = scenes.validate(scenes.starter())[2]
    pv = scenes.preview(clean, store.cfg['devices'])
    ok('предварительный просмотр: подсказка по адресу и по имени', {d['key']: d['suggest'] for d in pv['devices']}.get('rt') == 'dRouter' and {d['key']: d['suggest'] for d in pv['devices']}.get('nas') == 'dNas', pv['devices'])
    try:
        scenes.apply_real(store, clean, {'rt': 'dRouter', 'nas': 'dRouter'}, 'add'); ok('одно устройство на два места отклонено', False)
    except ValueError:
        ok('одно устройство на два места отклонено', True)
    try:
        scenes.apply_real(store, clean, {}, 'merge'); ok('неизвестный режим отклонён', False)
    except ValueError:
        ok('неизвестный режим отклонён', True)
    before = json.dumps([store.cfg['plan'], store.cfg['racks']], sort_keys=True)
    r = scenes.apply_real(store, clean, {'rt': 'dRouter', 'nas': 'dNas'}, 'add')
    plan = store.cfg['plan']
    ok('«добавить»: старое на месте, новое рядом, id не пересекаются', len(plan['buildings']) == 2 and plan['buildings'][0]['id'] == 'old' and len(store.cfg['racks']) == 2
       and len({b['id'] for b in plan['buildings']}) == 2 and len({x['id'] for x in store.cfg['racks']}) == 2, [b['id'] for b in plan['buildings']])
    items = [it for b in plan['buildings'][1:] for f_ in b['floors'] for it in f_['items']]
    ok('привязанные устройства — настоящие id, непривязанные места убраны', all(it['ref'] in ('dRouter', 'dNas') for it in items if it['kind'] == 'device') and r['dropped'] >= 1, (items, r))
    ok('метка «place» указывает на новый id шкафа', any(it['kind'] == 'place' and it['ref'] in {x['id'] for x in store.cfg['racks']} for it in items))
    ok('устройства, пароли и настройки не тронуты', len(store.cfg['devices']) == 2 and store.cfg['settings']['title'] == 'Моя сеть')
    units = [u for x in store.cfg['racks'][1:] for u in x['units']]
    ok('юниты шкафа получили настоящие устройства', any(u['deviceId'] == 'dRouter' for u in units) and any(u['deviceId'] == 'dNas' for u in units))
    scenes.undo(store, r['backup'])
    ok('«вернуть как было» восстанавливает план и шкафы до последней запятой', json.dumps([store.cfg['plan'], store.cfg['racks']], sort_keys=True) == before)
    r2 = scenes.apply_real(store, clean, {'rt': 'dRouter'}, 'replace')
    ok('«заменить»: прежнего нет, сцена вместо него', [b['id'] for b in store.cfg['plan']['buildings']] == ['house'] and [x['id'] for x in store.cfg['racks']] == ['closet'])
    ok('копии сохраняются, их видно в списке', len(scenes.backups(store)) >= 1 and any(b['id'] == r2['backup'] for b in scenes.backups(store)))
    for bad_id in ('../../etc/passwd', '2026', ''):
        try:
            scenes.undo(store, bad_id); ok(f'плохой номер копии «{bad_id}» отклонён', False)
        except ValueError:
            ok(f'плохой номер копии «{bad_id}» отклонён', True)

# the demo itself: a second copy of the program starts with a scene and answers
if os.environ.get('RL_SKIP_DEMO') != '1':
    from rackd import sandbox
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..') if os.path.isfile(globals().get('__file__', '')) else '/app'
    sb = sandbox.Sandbox(os.path.abspath(root))
    try:
        res = sb.start('builtin:starter', None, 'Мой дом')
        st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{res['port']}/api/state", timeout=10).read())
        ok('демо-копия запускается со сценой и показывает её устройства', res['running'] and len(st['devices']) == 10 and st['settings']['title'] == 'Мой дом · демо', (res, len(st['devices'])))
        ok('в демо-копии нет настоящих данных', not any(d.get('host', '').startswith(('192.168.1.1',)) and d['driver'] not in ('demo_sim', 'demo_sim_router', 'demo_sim_switch') for d in st['devices']))
        sb.stop()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{res['port']}/api/state", timeout=2); alive = True
        except Exception:
            alive = False
        ok('демо-копия останавливается', not alive and not sb.status()['running'])
        try:
            sb.start(None, {'devices': []}, 'x'); ok('плохая сцена не запускает демо', False)
        except RuntimeError:
            ok('плохая сцена не запускает демо', True)
    finally:
        sb.stop()

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
