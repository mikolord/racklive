"""Локальные плагины (rackd/localplug.py): загрузка, проверка, включение по отпечатку, маршруты, аварийные выключатели.
Run: python tools/localplug_test.py   (prints ВСЁ OK)"""
import io, json, os, shutil, sys, tempfile, time, zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import localplug

N, BAD = 0, []


def check(name, ok, extra=''):
    global N
    N += 1
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)[:300]))
    if not ok:
        BAD.append(name)


def zipped(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for n, t in files.items():
            z.writestr(n, t)
    return b.getvalue()


def manifest(**kw):
    return json.dumps(dict({'local_api': 1, 'id': 'my-plugin', 'title': 'Мой плагин', 'description': 'Проверка', 'version': '1.0.0'}, **kw))


MAIN = '''
import threading
ticks = []
def register(api):
    api.route('GET', 'hello', lambda req: {'hello': 'мир', 'q': req.query, 'n': len(api.devices())})
    api.route('POST', 'echo', lambda req: (201, req.json()))
    api.route('GET', 'boom', lambda req: 1 / 0)
    api.route('GET', 'raw', lambda req: (200, b'abc', 'text/plain'))
    api.every(5, lambda: ticks.append(1))
    api.log('готово')
    api.event('info', 'привет')
'''

tmp = tempfile.mkdtemp(prefix='rl-lp-')
events = []
devs = [{'id': 'a', 'name': 'NAS', 'password': 'secret1', 'ssh_key': 'KEY', 'host': '1.2.3.4', 'nested': {'token': 'tt', 'ok': 1}}]
try:
    L = localplug.Local(tmp, lambda: devs, lambda *a: events.append(a), '9.9')
    good = {'plugin.json': manifest(), 'main.py': MAIN, 'ui.js': 'window.x=1', 'panel.html': '<p>hi</p>'}
    rep = L.install_zip(zipped(good))
    check('хороший плагин принимается и лежит выключенным', rep['ok'] and not rep['plugin']['enabled'] and not rep['plugin']['live'], rep)
    m = L.get('my-plugin')
    check('есть отпечаток и список файлов', len(m['digest']) == 64 and 'main.py' in m['files'] and m['has_ui'] and m['has_panel'])
    check('выключенный плагин не отвечает', L.call('my-plugin', 'GET', 'hello', {}, b'')[0] == 404 and L.scripts() == [] and L.file('my-plugin', 'ui.js') is None)

    for name, files, word in [
        ('без plugin.json', {'main.py': MAIN}, 'plugin.json'),
        ('лишнее поле', {'plugin.json': manifest(evil=1), 'main.py': MAIN}, 'неизвестное'),
        ('плохой id', {'plugin.json': manifest(id='Bad_ID'), 'main.py': MAIN}, 'id'),
        ('синтаксическая ошибка', {'plugin.json': manifest(), 'main.py': 'def register(api:\n'}, 'синтакс'),
        ('нет register', {'plugin.json': manifest(), 'main.py': 'x = 1\n'}, 'register'),
        ('пустой плагин', {'plugin.json': manifest()}, 'хотя бы один'),
        ('чужое расширение', {'plugin.json': manifest(), 'main.py': MAIN, 'x.exe': 'MZ'}, 'не разрешён'),
        ('путь наружу', {'plugin.json': manifest(), 'main.py': MAIN, '../x.py': 'x'}, 'недопустимый путь')]:
        r = L.install_zip(zipped(files))
        check('отклоняется: ' + name, not r['ok'] and any(word in e for e in r['errors']), r)
    check('не zip отклоняется', not L.install_zip(b'not a zip')['ok'])

    # --- включение ---
    try:
        L.enable('my-plugin', 'wrong')
        check('чужой отпечаток отклоняется', False)
    except ValueError as e:
        check('чужой отпечаток отклоняется', 'изменился' in str(e))
    p = L.enable('my-plugin', m['digest'])
    check('включён с верным отпечатком', p['live'] and p['enabled'], p)
    c, o, _ = L.call('my-plugin', 'GET', 'hello', {'a': '1'}, b'')
    check('маршрут отвечает', c == 200 and o['hello'] == 'мир' and o['q'] == {'a': '1'} and o['n'] == 1, o)
    c, o, _ = L.call('my-plugin', 'POST', 'echo', {}, b'{"x": 5}')
    check('POST: код и тело ответа', c == 201 and o == {'x': 5}, (c, o))
    c, o, ct = L.call('my-plugin', 'GET', 'raw', {}, b'')
    check('ответ байтами с типом', c == 200 and o == b'abc' and ct == 'text/plain')
    c, o, _ = L.call('my-plugin', 'GET', 'boom', {}, b'')
    check('ошибка в обработчике: 500, плагин остаётся включённым', c == 500 and L.is_on('my-plugin') and any('ZeroDivision' in l for l in L.logs['my-plugin']), (c, o, L.logs))
    check('журнал плагина и событие', any('готово' in l for l in L.logs['my-plugin']) and any('привет' in e[2] for e in events), events)
    check('устройства без паролей, токенов и ключей', (lambda d: d['password'] == '***' and d['ssh_key'] == '***' and d['nested']['token'] == '***' and d['host'] == '1.2.3.4' and d['nested']['ok'] == 1)(
        __import__('rackd.localplug', fromlist=['x']).PluginAPI(L, 'my-plugin').devices()[0]))
    check('ui.js и файлы отдаются только у включённого', len(L.scripts()) == 1 and L.scripts()[0].startswith('/api/x/my-plugin/files/ui.js') and L.file('my-plugin', 'panel.html')[1].startswith('text/html'))
    check('чужие/опасные имена файлов не отдаются', L.file('my-plugin', '../state.json') is None and L.file('my-plugin', 'main.pyc') is None and L.file('my-plugin', 'nope.js') is None)
    r = L.install_zip(zipped(good))
    check('включённый плагин нельзя перезаписать', not r['ok'] and 'включён' in r['errors'][0])

    # --- выключение ---
    L.disable('my-plugin')
    check('выключен: маршруты и ui.js исчезли', L.call('my-plugin', 'GET', 'hello', {}, b'')[0] == 404 and L.scripts() == [] and not L.get('my-plugin') is None)

    # --- запуск: подтверждённый код грузится, изменённый нет ---
    L.enable('my-plugin', m['digest'])
    L2 = localplug.Local(tmp, lambda: devs, lambda *a: events.append(a), '9.9')
    L2.load_all()
    check('после перезапуска подтверждённый плагин поднимается сам', L2.is_on('my-plugin') and L2.call('my-plugin', 'GET', 'hello', {}, b'')[0] == 200)
    with open(os.path.join(tmp, 'local-plugins', 'my-plugin', 'code', 'main.py'), 'a', encoding='utf-8') as f:
        f.write('\n# изменено\n')
    L3 = localplug.Local(tmp, lambda: devs, lambda *a: events.append(a), '9.9')
    L3.load_all()
    check('изменённый код при запуске не включается', not L3.is_on('my-plugin') and 'изменился' in L3.errors.get('my-plugin', '') and L3.public(L3.get('my-plugin'))['enabled'] is False)

    # --- сбой при загрузке ---
    bad = {'plugin.json': manifest(id='bad-plugin'), 'main.py': 'def register(api):\n    raise RuntimeError("не загрузился")\n'}
    L.install_zip(zipped(bad))
    try:
        L.enable('bad-plugin', L.get('bad-plugin')['digest'])
        check('упавший при загрузке выключается и сообщает причину', False)
    except RuntimeError as e:
        check('упавший при загрузке выключается и сообщает причину', 'не загрузился' in str(e) and not L.is_on('bad-plugin') and 'bad-plugin' not in L.state['enabled'])
    # процесс умер во время загрузки: маркер остался
    L.install_zip(zipped(dict(bad, **{'main.py': MAIN, 'plugin.json': manifest(id='crash-plugin')})))
    mk = os.path.join(tmp, 'local-plugins', 'crash-plugin')
    os.makedirs(mk, exist_ok=True)
    open(os.path.join(mk, 'loading'), 'w').close()
    try:
        L.enable('crash-plugin', L.get('crash-plugin')['digest'])
    except RuntimeError:
        pass
    check('маркер незавершённой загрузки: плагин выключен', not L.is_on('crash-plugin') and 'прошлом запуске' in L.errors.get('crash-plugin', ''))

    # --- аварийный выключатель ---
    open(os.path.join(tmp, 'local-plugins', 'OFF'), 'w').close()
    L4 = localplug.Local(tmp, lambda: devs, lambda *a: events.append(a), '9.9')
    L4.load_all()
    check('файл OFF: ничего не загружается', L4.killed() and not L4.live)
    try:
        L4.enable('my-plugin', m['digest'])
        check('файл OFF: включить нельзя', False)
    except ValueError as e:
        check('файл OFF: включить нельзя', 'выключены целиком' in str(e))
    os.remove(os.path.join(tmp, 'local-plugins', 'OFF'))

    # --- инструкция для ИИ и шаблон ---
    g = localplug.guide_text()
    check('инструкция для ИИ описывает весь api и правила', all(w in g for w in ('api.route', 'api.every', 'api.event', 'api.devices', 'api.data_dir', 'monkeypatch', 'subprocess', 'ПРАВИЛА')))
    L.disable('my-plugin')
    rt = L.install_zip(localplug.template_zip())
    check('шаблон проходит проверку и включается', rt['ok'] and L.enable('my-plugin', L.get('my-plugin')['digest'])['live'], rt)
    check('маршрут шаблона отвечает', L.call('my-plugin', 'GET', 'hello', {}, b'')[1].get('rack_live') == '9.9')
    L.disable('my-plugin')

    # --- удаление ---
    L.remove('my-plugin')
    check('удаление стирает код, данные остаются', L.get('my-plugin') is None and os.path.isdir(os.path.join(tmp, 'local-plugins', 'my-plugin', 'data')))
    L.remove('my-plugin', wipe=True)
    check('удаление с данными стирает всё', not os.path.exists(os.path.join(tmp, 'local-plugins', 'my-plugin')))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)) + f'  (проверок: {N})')
sys.exit(1 if BAD else 0)
