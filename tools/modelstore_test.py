"""«Магазин моделей»: разбор каталога, строгая проверка скачанного, применение к карточке, модерация заявок (GitHub подменён заглушкой — без сети).
Run: python tools/modelstore_test.py   (prints ВСЁ OK)"""
import base64, json, os, shutil, sys, tempfile, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import modelstore, models, server

BAD, N = [], 0


def check(name, ok, extra=''):
    global N
    N += 1
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)))
    if not ok:
        BAD.append(name)


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
CARD = {'format': 'racklive-card', 'version': 1, 'id': 'demo-sw', 'vendor': 'Demo', 'model': 'SW-8', 'kind': 'switch', 'title': 'Demo SW-8',
        'photo': {'file': 'photo.png', 'license': 'own', 'author': 'Я'},
        'spots': [{'n': 1, 'x': .2, 'y': .5, 'w': .04, 'h': .3, 'kind': 'sfp', 'label': 'WAN'}, {'n': 1, 'x': .3, 'y': .5, 'w': .04, 'h': .3},
                  {'n': 2, 'x': 2, 'y': .5, 'w': .04, 'h': .3}, {'n': 3, 'x': .4, 'y': .5, 'w': .9, 'h': .3}, {'n': 4, 'x': .5, 'y': .5, 'w': .04, 'h': .3, 'label': 'a\x00b'}],
        'pzoom': {'x': .1, 'y': .2, 'w': .5, 'h': .6}, 'model3d': 'model3d.json'}
M3D = json.dumps(models.free_example())
INDEX = {'format': 'racklive-models-index', 'version': 1, 'count': 3, 'models': [
    {'id': 'demo-sw', 'path': 'models/demo/demo-sw', 'vendor': 'Demo', 'model': 'SW-8', 'title': 'Demo SW-8', 'kind': 'switch', 'ports': 2, 'photo': 'photo.png', 'model3d': True, 'license': 'own', 'author': 'Я', 'notes': ''},
    {'id': '../evil', 'path': 'models/demo/x', 'vendor': 'x', 'model': 'x', 'kind': 'switch'},
    {'id': 'bad-kind', 'path': 'models/demo/bad-kind', 'vendor': 'x', 'model': 'x', 'kind': 'toaster'}]}
FILES = {modelstore.INDEX_URL: json.dumps(INDEX).encode(), modelstore.RAW + 'models/demo/demo-sw/model.json': json.dumps(CARD).encode(),
         modelstore.RAW + 'models/demo/demo-sw/photo.png': PNG, modelstore.RAW + 'models/demo/demo-sw/model3d.json': M3D.encode()}
CALLS = []


def fake_get(url, limit, headers=None, timeout=15):
    CALLS.append(url)
    url = url.split('?')[0]
    if url not in FILES:
        raise modelstore.StoreError('GitHub ответил 404')
    if len(FILES[url]) > limit:
        raise modelstore.StoreError('файл слишком большой')
    return FILES[url]


real_get = modelstore._get
modelstore._get = fake_get
tmp = tempfile.mkdtemp()
try:
    s = modelstore.Store(tmp)
    idx = s.index()
    check('каталог: берутся только правильные записи', idx['ok'] and [m['id'] for m in idx['models']] == ['demo-sw'], idx)
    check('каталог кэшируется (второй вызов без сети)', (lambda n: (s.index(), len(CALLS) == n)[1])(len(CALLS)))
    b = s.bundle('demo-sw')
    sp = b['card']['spots']
    check('модель: дубли, выход за кадр, большие рамки и мусор в тексте отброшены', [x['n'] for x in sp] == [1, 4] and sp[0]['kind'] == 'sfp' and sp[1]['label'] == '', sp)
    check('модель: фото и 3D скачаны и проверены', b['photo'][1] == 'png' and b['model3d'] and b['model3d']['format'] == 'racklive-model')
    check('модель: приближение сохранено', b['card']['pzoom'] == {'x': .1, 'y': .2, 'w': .5, 'h': .6})
    try:
        s.bundle('нет-такой'); ok = False
    except modelstore.StoreError:
        ok = True
    check('неизвестная модель — ошибка', ok)
    FILES[modelstore.RAW + 'models/demo/demo-sw/photo.png'] = b'GIF89a' + b'x' * 50
    s._photos.clear()
    try:
        s.bundle('demo-sw'); ok = False
    except modelstore.StoreError as e:
        ok = 'не PNG' in str(e)
    check('чужой файл вместо фото отклоняется', ok)
    FILES[modelstore.RAW + 'models/demo/demo-sw/photo.png'] = PNG
    bad3 = json.loads(M3D); bad3['size']['w'] = 99999
    FILES[modelstore.RAW + 'models/demo/demo-sw/model3d.json'] = json.dumps(bad3).encode()
    try:
        s.bundle('demo-sw'); ok = False
    except modelstore.StoreError as e:
        ok = '3D' in str(e)
    check('испорченная 3D-модель отклоняется', ok)
    FILES[modelstore.RAW + 'models/demo/demo-sw/model3d.json'] = M3D.encode()
    check('адрес не из GitHub не открывается', (lambda: (lambda r: r)(True))() and not any('evil' in u for u in CALLS))
    try:
        real_get('https://evil.example/x', 10); ok = False
    except modelstore.StoreError:
        ok = True
    check('загрузчик отказывает адресам не из GitHub', ok)
    ph = s.photo('demo-sw')
    check('картинка для списка', ph and ph[1] == 'image/png' and ph[0] == PNG)

    # применение к карточке
    d = os.path.join(tmp, 'data'); os.makedirs(d)
    server.DATA = d
    server.APP = types.SimpleNamespace(models=models.Library(d))
    saved = []
    st = types.SimpleNamespace(cfg={'devices': [{'id': 'dev1', 'name': 'Коммутатор', 'kind': 'switch'}], 'racks': [], 'cards': []}, save=lambda: saved.append(1))
    r = server.store_apply(st, 'dev1', s.bundle('demo-sw'))
    ent = next((c for c in st.cfg['cards'] if c.get('of') == 'dev1'), {})
    check('применение: фото, порты, приближение и 3D попали в карточку', r['ok'] and ent.get('photo') and ent.get('photoType') == 'png' and [x['n'] for x in ent['spots']] == [1, 4]
          and ent.get('pzoom', {}).get('w') == .5 and ent.get('model') in [m['id'] for m in server.APP.models.public()], ent)
    check('применение: фото лежит в data/cardphotos', os.path.isfile(os.path.join(d, 'cardphotos', 'dev1.png')))
    check('применение: у точек остались только n, x, y, w, h', set(ent['spots'][0]) == {'n', 'x', 'y', 'w', 'h'})
    r2 = server.store_apply(st, 'нет-такого', s.bundle('demo-sw'))
    check('применение к несуществующей карточке отказывает', not r2['ok'])
    only3 = {'card': {**b['card'], 'photo': None, 'spots': [], 'pzoom': None}, 'photo': None, 'model3d': b['model3d']}
    st2 = types.SimpleNamespace(cfg={'devices': [{'id': 'dev2', 'name': 'Роутер', 'kind': 'router'}], 'racks': [], 'cards': []}, save=lambda: None)
    r3 = server.store_apply(st2, 'dev2', only3)
    check('применение только 3D-модели создаёт запись карточки', r3['ok'] and st2.cfg['cards'][0].get('model') and not st2.cfg['cards'][0].get('photo'))

    # модерация: GitHub-заглушка
    PULLS = {7: {'number': 7, 'state': 'open', 'title': 'Модель: Demo', 'body': 'Заявка #3\n\nCloses #3', 'user': {'login': 'github-actions[bot]'}, 'created_at': '2026-10-27',
                 'head': {'sha': 'a' * 40, 'repo': {'full_name': modelstore.REPO}}},
             8: {'number': 8, 'state': 'open', 'title': 'Чужое', 'body': '', 'user': {'login': 'someone'}, 'created_at': '2026-10-27', 'head': {'sha': 'b' * 40, 'repo': {'full_name': 'someone/fork'}}}}
    STATE = {'a' * 40: ('success', []), 'b' * 40: ('failure', [])}
    FILESOF = {7: ['models/demo/demo-sw/model.json', 'models/demo/demo-sw/photo.png'], 8: ['models/demo/demo-sw/model.json', 'tools/validate.py']}
    LOG = []

    def fake_api(self, method, path, body=None, auth=True):
        LOG.append((method, path, body))
        if path.startswith(f'/repos/{modelstore.REPO}/pulls?state=open'):
            return list(PULLS.values())
        import re
        m = re.match(rf'^/repos/{modelstore.REPO}/pulls/(\d+)(/files.*|/merge)?$', path)
        if m:
            n = int(m.group(1))
            if m.group(2) and m.group(2).startswith('/files'):
                return [{'filename': f} for f in FILESOF[n]]
            if method == 'PATCH':
                PULLS[n]['state'] = 'closed'; return {}
            if m.group(2) == '/merge':
                PULLS[n]['state'] = 'merged'; return {'merged': True}
            return PULLS[n]
        m = re.match(rf'^/repos/{modelstore.REPO}/commits/(\w+)/status$', path)
        if m:
            stt, _ = STATE[m.group(1)]
            return {'state': stt, 'statuses': [{'state': stt}]}
        if re.match(rf'^/repos/{modelstore.REPO}/commits/\w+/check-runs$', path):
            return {'check_runs': []}
        if path == f'/repos/{modelstore.REPO}':
            return {'permissions': {'push': True}}
        if path == '/user':
            return {'login': 'mikolord'}
        return {}
    modelstore.Store._api = fake_api
    try:
        s.set_token('short'); ok = False
    except modelstore.StoreError:
        ok = True
    check('токен: явный мусор отклоняется до запроса', ok and not s.token_info()['has'])
    info = s.set_token('github_pat_' + 'A' * 40)
    check('токен: принят, владелец определён, файл настроек создан', info['has'] and info['login'] == 'mikolord' and os.path.isfile(s.path))
    check('токен нигде не отдаётся наружу', 'github_pat_' not in json.dumps(s.token_info()) and 'github_pat_' not in json.dumps(s.pulls()))
    pl = {p['n']: p for p in s.pulls()}
    check('заявки: зелёная от бота и красная от человека различаются', pl[7]['check'] == 'green' and pl[7]['bot'] and pl[8]['check'] == 'red' and not pl[8]['bot'], pl)
    FILES['https://raw.githubusercontent.com/' + modelstore.REPO + '/' + 'a' * 40 + '/models/demo/demo-sw/model.json'] = json.dumps(CARD).encode()
    FILES['https://raw.githubusercontent.com/' + modelstore.REPO + '/' + 'a' * 40 + '/models/demo/demo-sw/photo.png'] = PNG
    FILES['https://raw.githubusercontent.com/' + modelstore.REPO + '/' + 'a' * 40 + '/models/demo/demo-sw/model3d.json'] = M3D.encode()
    pv = s.preview(7)
    check('предпросмотр заявки: порты, фото-картинка, статус', pv['card']['spots'] and pv['photo'].startswith('data:image/png;base64,') and pv['check'] == 'green' and pv['has3d'], list(pv))
    try:
        s.merge(8); ok = False
    except modelstore.StoreError as e:
        ok = 'не пройдена' in str(e)
    check('красную заявку принять нельзя', ok and PULLS[8]['state'] == 'open')
    s.merge(7)
    check('зелёная заявка принимается (squash с проверкой sha)', PULLS[7]['state'] == 'merged' and any(m == 'PUT' and p.endswith('/merge') and b.get('sha') == 'a' * 40 and b.get('merge_method') == 'squash' for m, p, b in LOG))
    PULLS[7]['state'] = 'open'; STATE['a' * 40] = ('success', []); FILESOF[7] = ['models/demo/demo-sw/model.json', '.github/workflows/x.yml']
    try:
        s.merge(7); ok = False
    except modelstore.StoreError as e:
        ok = 'вне models' in str(e)
    check('заявку с файлами вне models/ принимать из приложения нельзя', ok)
    PULLS[7]['state'] = 'open'; LOG.clear()
    s.close(7, 'Фото не прозрачное')
    check('отклонение: комментарий в заявку и в исходную Issue, заявка и Issue закрыты',
          sum(1 for m, p, b in LOG if m == 'POST' and 'comments' in p) == 2 and any(m == 'PATCH' and p.endswith('/pulls/7') and b['state'] == 'closed' for m, p, b in LOG)
          and any(m == 'PATCH' and p.endswith('/issues/3') for m, p, b in LOG))
    try:
        s.close(7); ok = False
    except modelstore.StoreError as e:
        ok = 'уже закрыта' in str(e)
    check('закрытую заявку повторно не обработать', ok)
    # публикация своей модели напрямую в каталог
    REPO_FILES = {}
    def pub_api(self, method, path, body=None, auth=True):
        pre = f'/repos/{modelstore.REPO}/contents/'
        if path.startswith(pre):
            name = path[len(pre):]
            if method == 'GET':
                if name not in REPO_FILES:
                    raise modelstore.StoreError('GitHub ответил 404')
                return {'sha': 's' + str(len(REPO_FILES[name])), 'content': base64.b64encode(REPO_FILES[name]).decode()}
            REPO_FILES[name] = base64.b64decode(body['content']); return {}
        return fake_api(self, method, path, body, auth)
    modelstore.Store._api = pub_api
    s.set_token('github_pat_' + 'A' * 40)
    spots = [{'n': 2, 'x': .4, 'y': .5, 'w': .05, 'h': .1, 'extra': 1}, {'n': 1, 'x': .2, 'y': .5, 'w': .05, 'h': .1}]
    r = s.publish('Keenetic', 'KN-1810', 'router', (PNG, 'png'), spots, {'x': .1, 'y': .2, 'w': .5, 'h': .6, 'z': 1}, None, 'own', '', '', '')
    card = json.loads(REPO_FILES['models/keenetic/keenetic-kn-1810/model.json']); idx = json.loads(REPO_FILES['index.json'])
    check('публикация: файлы модели и index.json записаны', r['id'] == 'keenetic-kn-1810' and 'models/keenetic/keenetic-kn-1810/photo.png' in REPO_FILES and idx['count'] == 1)
    check('публикация: порты по номерам, лишние поля убраны, приближение на месте', [p['n'] for p in card['spots']] == [1, 2] and 'extra' not in card['spots'][1] and card['pzoom'] == {'x': .1, 'y': .2, 'w': .5, 'h': .6})
    check('публикация: в индексе число портов и фото', idx['models'][0]['ports'] == 2 and idx['models'][0]['photo'] == 'photo.png')
    s.publish('Keenetic', 'KN-1810', 'router', (PNG, 'png'), spots[:1], None, None, 'own', '', '', '')
    idx = json.loads(REPO_FILES['index.json'])
    check('повторная публикация заменяет запись, а не дублирует', idx['count'] == 1 and idx['models'][0]['ports'] == 1)
    for bad_args in (('Кинетик', 'КН', 'router', (PNG, 'png')), ('A', 'B', 'toaster', (PNG, 'png')), ('A', 'Bcd', 'router', (b'GIF89a', 'png'))):
        try:
            s.publish(*bad_args, [], None, None); ok = False
        except modelstore.StoreError:
            ok = True
        if not ok:
            break
    check('публикация: кириллица, неверный тип и не-картинка отклоняются', ok)
    s.clear_token()
    s.clear_token()
    try:
        s.publish('Keenetic', 'KN-1810', 'router', (PNG, 'png'), [], None, None); ok = False
    except modelstore.StoreError as e:
        ok = 'токен' in str(e)
    check('без токена публикация невозможна', ok)
    check('токен удаляется', not s.token_info()['has'])
    mode = oct(os.stat(s.path).st_mode & 0o777) if os.name != 'nt' else '0o600'
    check('файл с токеном доступен только владельцу', mode == '0o600', mode)
finally:
    modelstore._get = real_get
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)) + f'  (проверок: {N})')
sys.exit(1 if BAD else 0)
