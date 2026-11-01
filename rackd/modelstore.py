"""«Магазин моделей»: готовые карточки устройств (фото на прозрачном фоне + размеченные порты + границы приближения, по желанию 3D-модель)
из публичного репозитория GitHub (REPO). Это ДАННЫЕ: ничего из каталога не запускается, каждая модель проходит строгую проверку ещё раз здесь.

Также «Модерация» для владельца каталога: открытые заявки (pull request'ы), предпросмотр, «Принять» (merge, только при зелёной проверке) и «Отклонить».
Токен GitHub (fine-grained, один репозиторий, pull requests + contents) владелец вводит сам; он хранится в data/modelstore.json (0600) и никуда не отдаётся."""
import base64, json, os, re, threading, time, urllib.error, urllib.request

from . import models as models_mod

REPO = 'mikolord/racklive-models'
RAW = f'https://raw.githubusercontent.com/{REPO}/main/'
INDEX_URL = RAW + 'index.json'
API = 'https://api.github.com'
UA = 'RackLive-models'
MAX_INDEX, MAX_JSON, MAX_PHOTO = 400_000, 120_000, 1_000_000
KINDS = ('router', 'switch', 'server', 'nas', 'ap', 'camera', 'nvr', 'ups', 'pc', 'modem', 'other')
PORT_KINDS = ('rj45', 'sfp', 'usb', 'power', 'console', 'other')
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{2,60}$')
VENDOR_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,40}$')
FULL_RE = re.compile(r'^[\w.-]{1,40}/[\w.-]{1,100}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')
LICENSES = ('own', 'CC0-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'permission')
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


class StoreError(Exception):
    pass


def _get(url, limit, headers=None, timeout=15):
    if not re.match(r'^https://(raw\.githubusercontent\.com|api\.github\.com)/', url):
        raise StoreError('адрес не из GitHub')
    req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise StoreError(f'GitHub ответил {e.code}')
    except Exception as e:
        raise StoreError(f'нет связи с GitHub ({type(e).__name__})')
    if len(data) > limit:
        raise StoreError('файл слишком большой')
    return data


def _text(v, maxlen):
    if not isinstance(v, str) or CTRL.search(v):
        return ''
    return v.strip()[:maxlen]


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def check_photo(blob):
    """→ extension or raises: настоящий PNG / WebP не больше MAX_PHOTO (полную проверку — прозрачность, размеры — делает каталог при приёме)"""
    if len(blob) > MAX_PHOTO:
        raise StoreError('фото больше 1 МБ')
    if blob[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if blob[:4] == b'RIFF' and blob[8:12] == b'WEBP':
        return 'webp'
    raise StoreError('фото не PNG и не WebP')


def clean_card(raw):
    """model.json каталога → {'meta', 'spots', 'pzoom', 'photo': file|None, 'model3d': bool}. Лишнее отбрасывается, числа в диапазонах, иначе StoreError."""
    if not isinstance(raw, dict) or raw.get('format') != 'racklive-card' or raw.get('version') != 1:
        raise StoreError('это не карточка формата racklive-card')
    if raw.get('kind') not in KINDS:
        raise StoreError('неизвестный тип устройства')
    meta = {'vendor': _text(raw.get('vendor'), 40), 'model': _text(raw.get('model'), 60), 'kind': raw['kind'], 'title': _text(raw.get('title'), 100), 'notes': _text(raw.get('notes'), 300)}
    if not meta['vendor'] or not meta['model']:
        raise StoreError('нет производителя или модели')
    meta['title'] = meta['title'] or (meta['vendor'] + ' ' + meta['model'])
    out = {'meta': meta, 'spots': [], 'pzoom': None, 'photo': None, 'model3d': False, 'license': None, 'author': ''}
    ph = raw.get('photo')
    if isinstance(ph, dict):
        if ph.get('file') in ('photo.webp', 'photo.png'):
            out['photo'] = ph['file']
        out['license'] = ph.get('license') if ph.get('license') in LICENSES else None
        out['author'] = _text(ph.get('author'), 80)
    seen = set()
    for s in (raw.get('spots') or [])[:200]:
        if not isinstance(s, dict) or not isinstance(s.get('n'), int) or isinstance(s.get('n'), bool) or not 1 <= s['n'] <= 256 or s['n'] in seen:
            continue
        if not (_num(s.get('x'), 0, 1) and _num(s.get('y'), 0, 1) and _num(s.get('w'), .002, .6) and _num(s.get('h'), .002, .6)):
            continue
        seen.add(s['n'])
        out['spots'].append({'n': s['n'], 'x': round(float(s['x']), 4), 'y': round(float(s['y']), 4), 'w': round(float(s['w']), 4), 'h': round(float(s['h']), 4),
                             'kind': s['kind'] if s.get('kind') in PORT_KINDS else 'rj45', 'label': _text(s.get('label'), 24)})
    z = raw.get('pzoom')
    if isinstance(z, dict) and all(_num(z.get(k), 0, 1) for k in ('x', 'y')) and all(_num(z.get(k), .02, 1) for k in ('w', 'h')) and z['x'] + z['w'] <= 1.0001 and z['y'] + z['h'] <= 1.0001:
        out['pzoom'] = {k: round(float(z[k]), 4) for k in ('x', 'y', 'w', 'h')}
    out['model3d'] = raw.get('model3d') == 'model3d.json'
    return out


class Store:
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, 'modelstore.json')
        self.lock = threading.Lock()
        self._index = (0, None)
        self._photos = {}                                           # id → (time, bytes, ext): a small cache for pictures in the list
        try:
            with open(self.path, encoding='utf-8') as f:
                self.cfg = json.load(f)
        except (OSError, ValueError):
            self.cfg = {}

    # ── the public catalog ──
    def index(self, force=False):
        t, cached = self._index
        if cached is not None and not force and time.time() - t < 120:
            return cached
        try:
            data = json.loads(_get(INDEX_URL + '?t=' + str(int(time.time()) // (1 if force else 30)), MAX_INDEX).decode('utf-8'))       # a changing query: raw.githubusercontent.com keeps files in its cache for ~5 min
            items = []
            for p in data.get('models', []):
                if not isinstance(p, dict) or not ID_RE.match(str(p.get('id') or '')):
                    continue
                m = re.match(r'^models/([a-z0-9-]{2,41})/' + re.escape(p['id']) + '$', str(p.get('path') or ''))
                if not m or p.get('kind') not in KINDS:
                    continue
                items.append({'id': p['id'], 'path': p['path'], 'vendor': _text(p.get('vendor'), 40), 'model': _text(p.get('model'), 60), 'title': _text(p.get('title'), 100),
                              'kind': p['kind'], 'ports': int(p['ports']) if isinstance(p.get('ports'), int) else 0, 'photo': p.get('photo') if p.get('photo') in ('photo.webp', 'photo.png') else None,
                              'model3d': bool(p.get('model3d')), 'license': p.get('license') if p.get('license') in LICENSES else None, 'author': _text(p.get('author'), 80), 'notes': _text(p.get('notes'), 300)})
            res = {'ok': True, 'models': items[:2000], 'repo': REPO}
        except StoreError as e:
            res = {'ok': False, 'models': [], 'repo': REPO, 'error': 'каталог сейчас недоступен: ' + str(e)}
        except (ValueError, UnicodeDecodeError):
            res = {'ok': False, 'models': [], 'repo': REPO, 'error': 'каталог повреждён (index.json не читается)'}
        self._index = (time.time(), res)
        return res

    def entry(self, mid):
        return next((m for m in self.index()['models'] if m['id'] == mid), None)

    def _bundle_at(self, base):
        """base = адрес папки модели (…/models/<производитель>/<id>/) → {'card', 'photo': (bytes, ext)|None, 'model3d': dict|None}"""
        card = clean_card(json.loads(_get(base + 'model.json', MAX_JSON).decode('utf-8')))
        photo = None
        if card['photo']:
            blob = _get(base + card['photo'], MAX_PHOTO)
            photo = (blob, check_photo(blob))
        m3 = None
        if card['model3d']:
            m3, errs = models_mod.validate(_get(base + 'model3d.json', models_mod.MAX_BYTES).decode('utf-8'))
            if errs:
                raise StoreError('3D-модель не прошла проверку: ' + '; '.join(errs[:2]))
        if not photo and not m3:
            raise StoreError('в модели нет ни фото, ни 3D')
        return {'card': card, 'photo': photo, 'model3d': m3}

    def bundle(self, mid):
        it = self.entry(mid)
        if not it:
            raise StoreError('такой модели нет в каталоге')
        try:
            return self._bundle_at(RAW + it['path'] + '/')
        except (ValueError, UnicodeDecodeError):
            raise StoreError('файлы модели повреждены')

    def photo(self, mid):
        """картинка для списка (с небольшим кэшем) → (bytes, 'image/…') или None"""
        hit = self._photos.get(mid)
        if hit and time.time() - hit[0] < 3600:
            return hit[1], hit[2]
        it = self.entry(mid)
        if not it or not it['photo']:
            return None
        blob = _get(RAW + it['path'] + '/' + it['photo'], MAX_PHOTO)
        ext = check_photo(blob)
        if len(self._photos) > 60:
            self._photos.pop(next(iter(self._photos)))
        self._photos[mid] = (time.time(), blob, 'image/' + ext)
        return blob, 'image/' + ext

    # ── moderation (the owner's token) ──
    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.cfg, f)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def token_info(self):
        return {'has': bool(self.cfg.get('token')), 'login': self.cfg.get('login') or '', 'repo': REPO}

    def _api(self, method, path, body=None, auth=True):
        h = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': UA}
        if auth:
            if not self.cfg.get('token'):
                raise StoreError('сначала введите токен GitHub')
            h['Authorization'] = 'Bearer ' + self.cfg['token']
        data = json.dumps(body).encode() if body is not None else None
        if data:
            h['Content-Type'] = 'application/json'
        req = urllib.request.Request(API + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read(2_000_000)
        except urllib.error.HTTPError as e:
            msg = ''
            try:
                msg = json.loads(e.read(20000).decode('utf-8')).get('message', '')
            except Exception:
                pass
            if e.code == 401:
                raise StoreError('GitHub не принял токен (неверный или истёк)')
            if e.code == 403 and 'rate limit' in msg.lower():
                raise StoreError('GitHub ограничил число запросов, повторите позже')
            if e.code in (403, 404):
                raise StoreError('у токена нет доступа к репозиторию ' + REPO + ' (нужны права: Pull requests и Contents — чтение и запись)')
            raise StoreError(f'GitHub ответил {e.code}: {msg[:150]}')
        except Exception as e:
            raise StoreError(f'нет связи с GitHub ({type(e).__name__})')
        return json.loads(raw.decode('utf-8')) if raw else {}

    def set_token(self, token):
        token = (token or '').strip()
        if not re.match(r'^[A-Za-z0-9_]{20,255}$', token):
            raise StoreError('это не похоже на токен GitHub (буквы, цифры и «_», 20+ символов)')
        old = self.cfg.get('token')
        self.cfg['token'] = token
        try:
            repo = self._api('GET', f'/repos/{REPO}')
            perms = repo.get('permissions') or {}
            if not (perms.get('push') or perms.get('admin') or perms.get('maintain')):
                raise StoreError('токен видит репозиторий, но не может в него писать (нужны права на pull requests и contents)')
            who = ''
            try:
                who = self._api('GET', '/user').get('login') or ''
            except StoreError:
                pass                                              # fine-grained tokens may not read /user
        except StoreError:
            if old:
                self.cfg['token'] = old
            else:
                self.cfg.pop('token', None)
            raise
        self.cfg['login'] = who
        self._save()
        return self.token_info()

    def clear_token(self):
        self.cfg.pop('token', None); self.cfg.pop('login', None)
        self._save()

    # ── publishing the owner's own model straight into the catalog (no request, no bot) ──
    def _put(self, path, data, message):
        """create or replace one file of the repository; → None"""
        sha = None
        try:
            sha = self._api('GET', f'/repos/{REPO}/contents/{path}').get('sha')
        except StoreError as e:
            if 'ответил 404' not in str(e) and 'нет доступа' not in str(e):
                raise
        body = {'message': message, 'content': base64.b64encode(data).decode()}
        if sha:
            body['sha'] = sha
        self._api('PUT', f'/repos/{REPO}/contents/{path}', body)

    def publish(self, vendor, model, kind, photo, spots, pzoom, m3, license='own', author='', title='', notes='', source='', vdir=None, mid=None):
        """photo = (bytes, 'png'|'webp') or None; spots = [{n,x,y,w,h}]; m3 = a cleaned 3D model dict or None → {'id', 'path'}"""
        if not self.cfg.get('token'):
            raise StoreError('сначала введите токен GitHub (Магазин → Модерация)')
        slug = lambda s: re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')[:40]
        vendor, model = _text(vendor, 40), _text(model, 60)
        vdir, mid = (vdir if vdir and VENDOR_RE.match(str(vdir)) else slug(vendor)), (mid if mid and ID_RE.match(str(mid)) else '-'.join(x for x in (slug(vendor), slug(model)) if x))
        if not vendor or not model or not VENDOR_RE.match(vdir) or not ID_RE.match(mid):
            raise StoreError('производитель и модель нужны латиницей и цифрами (например TP-Link и T2600G-28MPS)')
        if kind not in KINDS:
            raise StoreError('неизвестный тип устройства')
        if license not in LICENSES:
            raise StoreError('неизвестная лицензия')
        if not photo and not m3:
            raise StoreError('нечего публиковать: нет ни фото, ни 3D-модели')
        card = {'format': 'racklive-card', 'version': 1, 'id': mid, 'vendor': vendor, 'model': model, 'kind': kind}
        if _text(title, 100):
            card['title'] = _text(title, 100)
        if _text(notes, 300):
            card['notes'] = _text(notes, 300)
        files = []
        if photo:
            blob, ext = photo
            check_photo(blob)
            card['photo'] = {'file': 'photo.' + ext, 'license': license, 'author': _text(author, 80)}
            if _text(source, 300):
                card['photo']['source'] = _text(source, 300)
            files.append(('photo.' + ext, blob))
            clean = []
            for s in spots:
                if isinstance(s, dict) and all(k in s for k in ('n', 'x', 'y', 'w', 'h')):
                    c = {k: s[k] for k in ('n', 'x', 'y', 'w', 'h')}
                    if s.get('kind') in PORT_KINDS and s['kind'] != 'rj45':
                        c['kind'] = s['kind']
                    if _text(s.get('label'), 24):
                        c['label'] = _text(s['label'], 24)
                    clean.append(c)
            if clean:
                card['spots'] = sorted(clean, key=lambda s: s['n'])
            if pzoom:
                card['pzoom'] = {k: pzoom[k] for k in ('x', 'y', 'w', 'h')}
        if m3:
            card['model3d'] = 'model3d.json'
            files.append(('model3d.json', json.dumps(m3, ensure_ascii=False).encode('utf-8')))
        files.append(('model.json', json.dumps(card, ensure_ascii=False, indent=1).encode('utf-8') + b'\n'))
        base = f'models/{vdir}/{mid}'
        for name, data in files:
            self._put(f'{base}/{name}', data, f'Модель: {vendor} {model}')
        entry = {'id': mid, 'path': base, 'vendor': vendor, 'model': model, 'title': card.get('title') or f'{vendor} {model}', 'kind': kind,
                 'ports': len(card.get('spots') or []), 'photo': card.get('photo', {}).get('file'), 'model3d': bool(m3), 'license': license if photo else None,
                 'author': _text(author, 80), 'notes': card.get('notes', '')}
        try:
            cur = self._api('GET', f'/repos/{REPO}/contents/index.json')
            idx = json.loads(base64.b64decode(cur['content']).decode('utf-8'))
        except (StoreError, ValueError, KeyError):
            idx = {'format': 'racklive-models-index', 'version': 1, 'models': []}
        items = [m for m in idx.get('models', []) if isinstance(m, dict) and m.get('id') != mid] + [entry]
        items.sort(key=lambda x: (str(x.get('vendor')).lower(), str(x.get('model')).lower()))
        idx.update({'count': len(items), 'models': items})
        self._put('index.json', (json.dumps(idx, ensure_ascii=False, indent=1) + '\n').encode('utf-8'), f'Каталог: {vendor} {model}')
        self._index = (0, None)
        return {'id': mid, 'path': base}

    def _green(self, sha):
        """зелёная ли проверка у коммита: все статусы и проверки Actions успешны, и хотя бы один сигнал есть"""
        st = self._api('GET', f'/repos/{REPO}/commits/{sha}/status')
        runs = self._api('GET', f'/repos/{REPO}/commits/{sha}/check-runs').get('check_runs', [])
        statuses = st.get('statuses') or []
        bad = [s for s in statuses if s.get('state') != 'success'] + [r for r in runs if r.get('conclusion') != 'success']
        if not statuses and not runs:
            return 'none'
        return 'red' if any(s.get('state') in ('failure', 'error') for s in statuses) or any(r.get('conclusion') in ('failure', 'cancelled', 'timed_out', 'action_required') for r in runs) else ('wait' if bad else 'green')

    def pulls(self):
        out = []
        for p in self._api('GET', f'/repos/{REPO}/pulls?state=open&per_page=30'):
            sha = (p.get('head') or {}).get('sha') or ''
            try:
                check = self._green(sha) if SHA_RE.match(sha) else 'none'
            except StoreError:
                check = 'none'
            out.append({'n': p['number'], 'title': _text(p.get('title'), 120), 'user': _text((p.get('user') or {}).get('login'), 40), 'created': p.get('created_at'), 'check': check,
                        'bot': _text((p.get('user') or {}).get('login'), 40).endswith('[bot]') or _text((p.get('user') or {}).get('login'), 40) == 'github-actions'})
        return out

    def _pull(self, n):
        n = int(n)
        p = self._api('GET', f'/repos/{REPO}/pulls/{n}')
        if p.get('state') != 'open':
            raise StoreError('заявка уже закрыта')
        return p

    def preview(self, n):
        p = self._pull(n)
        head = p.get('head') or {}
        full, sha = ((head.get('repo') or {}).get('full_name') or ''), head.get('sha') or ''
        if not FULL_RE.match(full) or not SHA_RE.match(sha):
            raise StoreError('не удалось определить ветку заявки')
        files = self._api('GET', f'/repos/{REPO}/pulls/{int(n)}/files?per_page=100')
        names = [f.get('filename') or '' for f in files]
        outside = [x for x in names if not x.startswith('models/')]
        dirs = {m.group(1) for x in names for m in [re.match(r'^(models/[a-z0-9-]+/[a-z0-9-]+)/', x)] if m}
        if len(dirs) != 1:
            raise StoreError('в заявке должна быть ровно одна модель' + (f' (сейчас {len(dirs)})' if dirs else ''))
        base = f'https://raw.githubusercontent.com/{full}/{sha}/{next(iter(dirs))}/'
        try:
            b = self._bundle_at(base)
        except (ValueError, UnicodeDecodeError):
            raise StoreError('файлы модели повреждены')
        return {'n': int(n), 'title': _text(p.get('title'), 120), 'user': _text((p.get('user') or {}).get('login'), 40), 'body': _text(p.get('body'), 1500),
                'check': self._green(sha), 'outside': outside[:10], 'card': b['card'], 'photo': ('data:image/%s;base64,%s' % (b['photo'][1], base64.b64encode(b['photo'][0]).decode())) if b['photo'] else None,
                'has3d': bool(b['model3d'])}

    def merge(self, n):
        p = self._pull(n)
        sha = (p.get('head') or {}).get('sha') or ''
        if not SHA_RE.match(sha):
            raise StoreError('не удалось определить коммит заявки')
        g = self._green(sha)
        if g != 'green':
            raise StoreError({'red': 'автопроверка не пройдена — принимать нельзя', 'wait': 'проверка ещё идёт — подождите', 'none': 'у заявки нет результата проверки'}[g])
        files = [f.get('filename') or '' for f in self._api('GET', f'/repos/{REPO}/pulls/{int(n)}/files?per_page=100')]
        if any(not x.startswith('models/') for x in files):
            raise StoreError('заявка меняет файлы вне models/ — принимайте её на GitHub вручную')
        self._api('PUT', f'/repos/{REPO}/pulls/{int(n)}/merge', {'merge_method': 'squash', 'sha': sha})
        self._index = (0, None)
        return {'ok': True}

    def close(self, n, comment=''):
        p = self._pull(n)
        comment = (comment or '').strip()[:1000]
        issue = re.search(r'Closes #(\d+)', p.get('body') or '')
        if comment:
            self._api('POST', f'/repos/{REPO}/issues/{int(n)}/comments', {'body': comment})
            if issue:
                self._api('POST', f'/repos/{REPO}/issues/{int(issue.group(1))}/comments', {'body': 'Заявка отклонена: ' + comment})
        self._api('PATCH', f'/repos/{REPO}/pulls/{int(n)}', {'state': 'closed'})
        if issue:
            try:
                self._api('PATCH', f'/repos/{REPO}/issues/{int(issue.group(1))}', {'state': 'closed', 'state_reason': 'not_planned'})
            except StoreError:
                pass
        return {'ok': True}
