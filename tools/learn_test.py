"""«Обучение» (rackd/learn.py): встроенная Академия, безопасная выдача файлов, прогресс, каталог и скачивание модулей (GitHub заменён заглушкой)."""
import hashlib, json, os, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import learn  # noqa: E402

bad = 0


def check(name, ok):
    global bad
    print(('ok   ' if ok else 'FAIL ') + name)
    bad += 0 if ok else 1


def sha(b):
    return hashlib.sha256(b).hexdigest()


FILES = {'index.html': b'<!doctype html><title>t</title><script src="game.js"></script>', 'game.js': b'RLLearn.load();', 'img/a.svg': b'<svg xmlns="http://www.w3.org/2000/svg"/>'}


def make_index(files=FILES, version='1.0.0', extra=None):
    e = {'id': 'demo-game', 'title': 'Демо-игра', 'description': 'Проверка', 'version': version, 'author': 'Rack Live', 'tag': 'game',
         'files': [{'name': n, 'size': len(b), 'sha256': sha(b)} for n, b in files.items()]}
    e.update(extra or {})
    return {'format': 'racklive-learning', 'version': 1, 'modules': [e]}


def stub(index, files, tampered=None):
    """GitHub stand-in: the index and the module files"""
    def fake_get(url, limit, timeout=20):
        if url.split('?')[0] == learn.INDEX_URL:
            return json.dumps(index).encode()
        name = url.split('/modules/demo-game/')[1]
        if tampered and name == tampered:
            return b'X' * len(files[name])
        return files[name]
    learn._get = fake_get
    return fake_get


with tempfile.TemporaryDirectory() as tmp:
    L = learn.Learn(tmp)

    # ── the Academy is built in ──
    mods = L.list()
    a = next((m for m in mods if m['id'] == 'net-academy'), None)
    check('Академия встроена и найдена', bool(a) and a['builtin'] and a['title'] == 'Академия сетей')
    got = L.file('net-academy', '')
    check('index.html отдаётся по умолчанию', bool(got) and b'RLLearn' not in got[0] and got[1].startswith('text/html'))
    check('скрипт Академии ходит через мост, а не напрямую в API', b'RLLearn.load' in L.file('net-academy', 'academy.js')[0] and b'fetch(' not in L.file('net-academy', 'academy.js')[0])
    check('в index.html нет ссылок на старый плагин и установки', b'api/x/' not in got[0] and b'class="install"' not in got[0])
    check('мост подключён', b'/api/learn/bridge.js' in got[0] and b'postMessage' in L.bridge())
    for bad_rel in ('../learn.py', '..\\learn.py', 'a/../../server.py', '.hidden.js', 'module.py', 'x.exe', '/etc/passwd', 'academy.js/../../../x.js'):
        check('путь запрещён: ' + bad_rel, L.file('net-academy', bad_rel) is None)
    check('чужой id не открывается', L.file('no-such', 'index.html') is None and L.file('../x', 'index.html') is None)
    check('js отдаётся как javascript', L.file('net-academy', 'academy.js')[1].startswith('application/javascript'))

    # ── each module is its own installable page ──
    pg = L.page('net-academy'); man = L.manifest('net-academy')
    check('у модуля своя страница с манифестом и значком', bool(pg) and '/api/learn/manifest/net-academy.json' in pg and 'rel="apple-touch-icon"' in pg and 'sandbox="allow-scripts' in pg)
    check('страница модуля ставится как приложение', man['start_url'] == '/learn/net-academy' and man['scope'] == '/learn/net-academy' and man['display'] == 'standalone' and man['icons'] and man['icons'][0]['src'].startswith('/api/learn/f/net-academy/icon-192.png'))
    check('значки для установки — PNG 192/512, для iPhone 180', [i['sizes'] for i in man['icons']] == ['192x192', '512x512'] and all(i['type'] == 'image/png' for i in man['icons']) and '/icon-180.png' in pg)
    check('в странице есть кнопка «назад» для открытия из Rack Live', 'id="back"' in pg and 'back=1' in pg)
    check('страницы нет у чужого модуля', L.page('no-such') is None and L.manifest('no-such') is None)

    # ── progress ──
    check('прогресс пуст', L.progress('net-academy') == {})
    r = L.save_progress('net-academy', {'done': ['v0-needs']})
    check('прогресс сохраняется', r == {'done': ['v0-needs']} and L.progress('net-academy') == {'done': ['v0-needs']})
    r = L.save_progress('net-academy', {'done': ['v0-roles']})
    check('отметки только пополняются (две вкладки не затирают друг друга)', r['done'] == ['v0-needs', 'v0-roles'])
    for payload in ('строка', {'done': 'x'}, {'done': [1]}, {'done': ['x' * 81]}, {'big': 'z' * 70_000}):
        try:
            L.save_progress('net-academy', payload)
            check('плохой прогресс отклонён: ' + str(payload)[:20], False)
        except learn.LearnError:
            check('плохой прогресс отклонён: ' + str(payload)[:20], True)
    try:
        L.save_progress('nope-nope', {})
        check('прогресс чужому модулю отклонён', False)
    except learn.LearnError:
        check('прогресс чужому модулю отклонён', True)

    # ── the old local plugin's progress moves over once ──
    with tempfile.TemporaryDirectory() as t2:
        os.makedirs(os.path.join(t2, 'local-plugins', 'net-academy', 'data'))
        with open(os.path.join(t2, 'local-plugins', 'net-academy', 'data', 'progress.json'), 'w', encoding='utf-8') as f:
            json.dump({'done': ['v0-names', 'v1-lesson1']}, f)
        L2 = learn.Learn(t2)
        check('прогресс старого плагина подхвачен', L2.progress('net-academy') == {'done': ['v0-names', 'v1-lesson1']})
        L2.save_progress('net-academy', {'done': ['v2-lesson1']})
        check('после сохранения старый и новый вместе', L2.progress('net-academy')['done'] == ['v0-names', 'v1-lesson1', 'v2-lesson1'])

    # ── the catalog ──
    stub(make_index(), FILES)
    cat = L.catalog(True)
    check('каталог читается', cat['ok'] and len(cat['modules']) == 1 and cat['modules'][0]['tag'] == 'game')
    cv = L.catalog_view(True)['modules'][0]
    check('в каталоге: не скачан', cv['installed'] is None and not cv['update'] and not cv['builtin'])

    broken = make_index()
    broken['modules'][0]['files'][0]['sha256'] = 'abc'
    stub(broken, FILES)
    check('запись с неверной контрольной суммой пропущена', L.catalog(True)['modules'] == [])
    noindex = make_index({'game.js': b'x'})
    stub(noindex, {'game.js': b'x'})
    check('модуль без index.html пропущен', L.catalog(True)['modules'] == [])
    evil = make_index({'index.html': b'x', '../evil.js': b'y'})
    stub(evil, {'index.html': b'x', '../evil.js': b'y'})
    check('файл с путём наверх пропущен', L.catalog(True)['modules'] == [])
    exe = make_index({'index.html': b'x', 'run.exe': b'y'})
    stub(exe, {'index.html': b'x', 'run.exe': b'y'})
    check('файл запрещённого типа пропущен', L.catalog(True)['modules'] == [])
    big = make_index(extra={'files': [{'name': 'index.html', 'size': learn.MAX_FILE + 1, 'sha256': sha(b'a')}]})
    stub(big, {})
    check('слишком большой файл пропущен', L.catalog(True)['modules'] == [])

    def broken_net(url, limit, timeout=20):
        raise learn.LearnError('GitHub ответил 404')
    learn._get = broken_net
    cat = L.catalog(True)
    check('каталог недоступен — понятная ошибка, не падение', not cat['ok'] and 'недоступен' in cat['error'])

    # ── install / update / remove ──
    fake = stub(make_index(), FILES)
    meta = L.install('demo-game', fetch=fake)
    check('модуль скачан', meta['id'] == 'demo-game' and L.get('demo-game')['builtin'] is False)
    check('файлы на месте и выдаются', L.file('demo-game', '')[0] == FILES['index.html'] and L.file('demo-game', 'img/a.svg')[0] == FILES['img/a.svg'])
    check('в каталоге: скачан', L.catalog_view(True)['modules'][0]['installed'] == '1.0.0')
    stub(make_index(version='1.1.0'), FILES)
    check('новая версия видна как обновление', L.catalog_view(True)['modules'][0]['update'] is True)
    meta = L.install('demo-game', fetch=learn._get)
    check('обновление поставилось', L.get('demo-game')['version'] == '1.1.0' and not os.path.exists(os.path.join(tmp, 'learning', 'modules', '.demo-game.old')))

    fake = stub(make_index(version='1.2.0'), FILES, tampered='game.js')
    try:
        L.install('demo-game', fetch=fake)
        check('подменённый файл отклонён', False)
    except learn.LearnError as e:
        check('подменённый файл отклонён', 'не совпал' in str(e))
    check('при ошибке прежняя версия цела, мусора нет', L.get('demo-game')['version'] == '1.1.0' and L.file('demo-game', 'game.js')[0] == FILES['game.js']
          and not [n for n in os.listdir(os.path.join(tmp, 'learning', 'modules')) if n.startswith('.')])
    try:
        L.install('net-academy')
        check('встроенный модуль не перезаписать', False)
    except learn.LearnError:
        check('встроенный модуль не перезаписать', True)
    try:
        L.remove('net-academy')
        check('встроенный модуль не удалить', False)
    except learn.LearnError:
        check('встроенный модуль не удалить', True)
    L.save_progress('demo-game', {'done': ['a']})
    L.remove('demo-game')
    check('модуль удалён, прогресс остался', L.get('demo-game') is None and os.path.exists(L._ppath('demo-game')))
    L.remove('demo-game', wipe=True)
    check('удаление с прогрессом', not os.path.exists(L._ppath('demo-game')))

print('\nВСЁ OK' if not bad else f'\nпровалов: {bad}')
sys.exit(1 if bad else 0)
