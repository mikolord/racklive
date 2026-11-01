"""«Обучение»: интерактивные учебные модули (уроки, игры, тренажёры) — встроенные и скачанные из публичного каталога владельца.

Модуль — это папка с index.html и своими файлами (html, css, js, json, картинки). Он показывается в изолированном окне (iframe + CSP sandbox, без доступа
к Rack Live, без сети): единственное, что он умеет, — сохранить и прочитать СВОЙ прогресс через мост (bridge.js → postMessage → этот модуль).
Встроенные модули лежат в rackd/learn_builtin/<id>/ и есть всегда. Остальные — в каталоге GitHub (REPO, index.json); пользователь видит список
и скачивает нужное в data/learning/modules/<id>/. Выкладывает в каталог только владелец Rack Live; загрузки чужих модулей здесь нет."""
import hashlib, html, json, mimetypes, os, re, shutil, threading, time, urllib.error, urllib.request

REPO = 'mikolord/racklive-learning'
RAW = f'https://raw.githubusercontent.com/{REPO}/main/'
INDEX_URL = RAW + 'index.json'
UA = 'RackLive-learning'
BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'learn_builtin')
ID_RE = re.compile(r'^[a-z][a-z0-9-]{2,40}$')
NAME_RE = re.compile(r'^[A-Za-z0-9._-]{1,80}(/[A-Za-z0-9._-]{1,80}){0,3}$')
SHA_RE = re.compile(r'^[0-9a-f]{64}$')
EXTS = ('.html', '.css', '.js', '.json', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.txt', '.md', '.woff2')
MAX_INDEX, MAX_FILE, MAX_TOTAL, MAX_FILES, MAX_PROGRESS = 400_000, 3_000_000, 12_000_000, 80, 65_536
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
TAGS = ('course', 'game', 'manual', 'trainer')
MIME = {'.js': 'application/javascript', '.json': 'application/json', '.md': 'text/plain', '.woff2': 'font/woff2'}
LEGACY_PROGRESS = {'net-academy': ('local-plugins', 'net-academy', 'data', 'progress.json')}      # the Academy used to be a local plugin: its progress moves over once


class LearnError(Exception):
    pass


def _text(v, n):
    if not isinstance(v, str) or CTRL.search(v):
        return ''
    return v.strip()[:n]


def _get(url, limit, timeout=20):
    if not url.startswith('https://raw.githubusercontent.com/' + REPO + '/'):
        raise LearnError('адрес не из каталога обучения')
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise LearnError(f'GitHub ответил {e.code}')
    except Exception as e:
        raise LearnError(f'нет связи с GitHub ({type(e).__name__})')
    if len(data) > limit:
        raise LearnError('файл слишком большой')
    return data


def clean_meta(raw, mid=None):
    """module.json / запись index.json → безопасное описание модуля или LearnError"""
    if not isinstance(raw, dict):
        raise LearnError('описание модуля не читается')
    i = str(raw.get('id') or mid or '')
    if not ID_RE.match(i) or (mid and i != mid):
        raise LearnError('неверный id модуля')
    title = _text(raw.get('title'), 80)
    if not title:
        raise LearnError('у модуля нет названия')
    ver = _text(str(raw.get('version') or '1'), 20) or '1'
    tag = raw.get('tag') if raw.get('tag') in TAGS else 'course'
    return {'id': i, 'title': title, 'description': _text(raw.get('description'), 300), 'version': ver, 'author': _text(raw.get('author'), 60), 'tag': tag,
            'icon': raw['icon'] if isinstance(raw.get('icon'), str) and _safe_rel(raw['icon']) == raw['icon'] and raw['icon'].lower().endswith(('.svg', '.png', '.webp')) else ''}


def _safe_rel(rel):
    rel = (rel or '').replace('\\', '/').lstrip('/') or 'index.html'
    if not NAME_RE.match(rel) or not rel.lower().endswith(EXTS) or any(p in ('.', '..') or p.startswith('.') for p in rel.split('/')):
        return None
    return rel


def _vtuple(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r'[.\-]', str(v or '0')))[:6]


class Learn:
    def __init__(self, data_dir):
        self.data = data_dir
        self.dir = os.path.join(data_dir, 'learning')
        self.mods = os.path.join(self.dir, 'modules')
        self.prog = os.path.join(self.dir, 'progress')
        self.lock = threading.Lock()
        self._index = (0, None)

    # ── what is on this installation ──
    def _read_meta(self, folder, mid):
        try:
            with open(os.path.join(folder, 'module.json'), encoding='utf-8') as f:
                m = clean_meta(json.load(f), mid)
        except (OSError, ValueError, LearnError):
            return None
        if not os.path.isfile(os.path.join(folder, 'index.html')):
            return None
        return m

    def list(self):
        out = []
        for base, builtin in ((BUILTIN_DIR, True), (self.mods, False)):
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for n in names:
                if not ID_RE.match(n) or (not builtin and any(x['id'] == n for x in out)):
                    continue
                m = self._read_meta(os.path.join(base, n), n)
                if m:
                    m['builtin'] = builtin
                    out.append(m)
        return out

    def get(self, mid):
        return next((m for m in self.list() if m['id'] == mid), None)

    def _folder(self, mid):
        m = self.get(mid) if ID_RE.match(str(mid or '')) else None
        if not m:
            return None
        return os.path.join(BUILTIN_DIR if m['builtin'] else self.mods, mid)

    def file(self, mid, rel):
        """→ (bytes, content-type) | None. Only inside the module's own folder and only the allowed kinds of files."""
        folder = self._folder(mid)
        rel = _safe_rel(rel)
        if not folder or not rel:
            return None
        full = os.path.normpath(os.path.join(folder, *rel.split('/')))
        if not full.startswith(os.path.normpath(folder) + os.sep) or not os.path.isfile(full):
            return None
        ext = os.path.splitext(full)[1].lower()
        ctype = MIME.get(ext) or mimetypes.guess_type(full)[0] or 'application/octet-stream'
        with open(full, 'rb') as f:
            return f.read(), ctype + ('; charset=utf-8' if ctype.startswith(('text', 'application/javascript', 'application/json')) else '')

    # ── a module as its own installable app: /learn/<id> (a page that holds the sandboxed module) + a manifest ──
    def manifest(self, mid):
        m = self.get(mid)
        if not m:
            return None
        icons = []
        for s in (192, 512):                         # browsers install from PNG; a module may ship icon-192.png / icon-512.png / icon-180.png (the Apple one) next to its SVG
            if self.file(mid, f'icon-{s}.png'):
                icons.append({'src': f"/api/learn/f/{mid}/icon-{s}.png?v={m['version']}", 'sizes': f'{s}x{s}', 'type': 'image/png', 'purpose': 'any'})
        if m['icon'] and not icons:
            ext = m['icon'].rsplit('.', 1)[-1].lower()
            icons = [{'src': f"/api/learn/f/{mid}/{m['icon']}?v={m['version']}", 'sizes': 'any' if ext == 'svg' else '512x512',
                      'type': {'svg': 'image/svg+xml', 'png': 'image/png', 'webp': 'image/webp'}.get(ext, 'image/png'), 'purpose': 'any'}]
        return {'id': f'/learn/{mid}', 'name': m['title'], 'short_name': m['title'][:12], 'description': m['description'], 'start_url': f'/learn/{mid}',
                'scope': f'/learn/{mid}', 'display': 'standalone', 'background_color': '#090c10', 'theme_color': '#090c10', 'icons': icons}

    def page(self, mid):
        """the standalone page of a module: its own title, icon and manifest (so it installs like an app); inside — the module in its sandbox and the progress bridge"""
        m = self.get(mid)
        if not m:
            return None
        e = html.escape
        icon = f"/api/learn/f/{mid}/{m['icon']}?v={m['version']}" if m['icon'] else '/icon.svg'
        apple = f"/api/learn/f/{mid}/icon-180.png?v={m['version']}" if self.file(mid, 'icon-180.png') else icon
        return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#090c10"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{e(m['title'][:12])}">
<title>{e(m['title'])}</title>
<link rel="manifest" href="/api/learn/manifest/{mid}.json"><link rel="icon" href="{e(icon)}"><link rel="apple-touch-icon" href="{e(apple)}">
<style>html,body{{margin:0;height:100%;background:#090c10;font-family:system-ui,sans-serif}}body{{display:flex;flex-direction:column}}iframe{{border:0;width:100%;flex:1;min-height:0;display:block}}
#bar{{display:none;align-items:center;gap:10px;flex:none;padding:max(8px,env(safe-area-inset-top)) 12px 8px;background:#0d131a;border-bottom:1px solid #293541;color:#eef5fb;font-size:14px}}#bar.on{{display:flex}}
#bar button{{border:0;background:#17212b;color:#eef5fb;border-radius:12px;padding:9px 14px;font:inherit;font-weight:700;cursor:pointer}}#bar b{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
#msg{{position:fixed;inset:0;display:none;place-items:center;text-align:center;color:#eef5fb;padding:24px;background:#090c10}}#msg.on{{display:grid}}#msg a{{color:#49adff}}
#inst{{position:fixed;left:12px;right:12px;bottom:max(12px,env(safe-area-inset-bottom));max-width:520px;margin:auto;background:#eaf6ff;color:#07131d;border-radius:16px;padding:12px 14px;display:none;align-items:center;gap:10px;font-size:13px;box-shadow:0 10px 40px #0007}}
#inst.on{{display:flex}}#inst button{{border:0;border-radius:10px;padding:8px 12px;font:inherit;font-weight:700;cursor:pointer}}#go{{margin-left:auto;background:#0d6ebc;color:#fff}}#x{{background:none;color:#34444f}}</style></head>
<body>
<div id="bar"><button id="back" type="button">‹ Rack Live</button><b>{e(m['title'])}</b></div>
<iframe id="f" title="{e(m['title'])}" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" src="/api/learn/f/{mid}/index.html?v={e(m['version'])}"></iframe>
<div id="msg"><div><p>Чтобы сохранялся прогресс, войдите в Rack Live.</p><p><a href="/" target="_top">Открыть Rack Live</a></p></div></div>
<div id="inst"><span id="it">Установить «{e(m['title'])}» как приложение?</span><button id="go">Установить</button><button id="x">×</button></div>
<script>
(function(){{
var ID={json.dumps(mid)},f=document.getElementById('f'),dp;
if(/[?&]back=1/.test(location.search)){{document.getElementById('bar').className='on';        // opened from Rack Live: an installed app has no browser «back», so give one
  document.getElementById('back').onclick=function(){{if(history.length>1)history.back();else location.href='/?tsec=learn#tools'}}}}
function tok(){{try{{return sessionStorage.getItem('rl_tok')||''}}catch(e){{return ''}}}}
function call(path,body){{var h={{'Content-Type':'application/json'}},t=tok();if(t)h['X-RL-Session']=t;
  return fetch(path,{{method:body?'POST':'GET',credentials:'same-origin',headers:h,body:body?JSON.stringify(body):undefined}}).then(function(r){{
    if(r.status===401)document.getElementById('msg').className='on';return r.json().then(function(j){{if(!r.ok)throw new Error(j.error||'ошибка');return j}})}})}}
addEventListener('message',function(ev){{var d=ev.data;if(ev.source!==f.contentWindow||!d||d.rl!=='learn')return;
  function reply(ok,data,error){{try{{f.contentWindow.postMessage({{rl:'learn-re',id:d.id,ok:ok,data:data,error:error}},'*')}}catch(e){{}}}}
  var p=d.type==='load'?call('/api/learn/progress?id='+encodeURIComponent(ID)):d.type==='save'?call('/api/learn/progress',{{id:ID,data:d.data}}):null;
  if(p)p.then(function(r){{reply(true,r.progress||{{}})}}).catch(function(x){{reply(false,null,x.message)}})}});
addEventListener('beforeinstallprompt',function(e){{e.preventDefault();dp=e;document.getElementById('inst').className='on'}});
document.getElementById('x').onclick=function(){{document.getElementById('inst').className=''}};
document.getElementById('go').onclick=function(){{if(dp){{dp.prompt();dp=null;document.getElementById('inst').className=''}}else{{document.getElementById('it').textContent=/iPhone|iPad|iPod/.test(navigator.userAgent)?'Safari → Поделиться → На экран «Домой»':'Меню браузера → Установить приложение'}}}};
}})();
</script></body></html>'''

    @staticmethod
    def bridge():
        with open(os.path.join(BUILTIN_DIR, 'bridge.js'), 'rb') as f:
            return f.read()

    # ── progress: one small JSON per module; a list «done» only ever grows (two tabs must not wipe each other) ──
    def _ppath(self, mid):
        return os.path.join(self.prog, mid + '.json')

    def _load(self, mid):
        try:
            with open(self._ppath(mid), encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            pass
        leg = LEGACY_PROGRESS.get(mid)
        if leg:
            try:
                with open(os.path.join(self.data, *leg), encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict) and isinstance(d.get('done'), list):
                    return {'done': [x for x in d['done'] if isinstance(x, str)][:500]}
            except (OSError, ValueError):
                pass
        return {}

    def progress(self, mid):
        if not self.get(mid):
            raise LearnError('нет такого модуля')
        with self.lock:
            return self._load(mid)

    def save_progress(self, mid, data):
        if not self.get(mid):
            raise LearnError('нет такого модуля')
        if not isinstance(data, dict):
            raise LearnError('прогресс должен быть объектом')
        with self.lock:
            old = self._load(mid)
            new = dict(data)
            if 'done' in new or 'done' in old:
                nd = new.get('done', [])
                if not isinstance(nd, list) or any(not isinstance(x, str) or len(x) > 80 for x in nd):
                    raise LearnError('done: список коротких строк')
                merged = list(dict.fromkeys([x for x in old.get('done', []) if isinstance(x, str)] + nd))
                if len(merged) > 500:
                    raise LearnError('слишком много отметок')
                new['done'] = merged
            blob = json.dumps(new, ensure_ascii=False)
            if len(blob.encode('utf-8')) > MAX_PROGRESS:
                raise LearnError('прогресс слишком большой')
            os.makedirs(self.prog, exist_ok=True)
            with open(self._ppath(mid) + '.tmp', 'w', encoding='utf-8') as f:
                f.write(blob)
            os.replace(self._ppath(mid) + '.tmp', self._ppath(mid))
            return new

    # ── the public catalog ──
    def catalog(self, force=False):
        t, cached = self._index
        if cached is not None and not force and time.time() - t < 120:
            return cached
        try:
            data = json.loads(_get(INDEX_URL + '?t=' + str(int(time.time()) // (1 if force else 30)), MAX_INDEX).decode('utf-8'))
            items = []
            for p in (data.get('modules') or [])[:200]:
                try:
                    m = clean_meta(p)
                    files, total = [], 0
                    for f in (p.get('files') or [])[:MAX_FILES]:
                        name, size, sha = f.get('name'), f.get('size'), f.get('sha256')
                        if not (isinstance(name, str) and _safe_rel(name) == name and isinstance(size, int) and 0 < size <= MAX_FILE and isinstance(sha, str) and SHA_RE.match(sha)):
                            raise LearnError('файл в списке модуля неверный')
                        total += size
                        files.append({'name': name, 'size': size, 'sha256': sha})
                    if not any(f['name'] == 'index.html' for f in files) or total > MAX_TOTAL:
                        raise LearnError('нет index.html или модуль слишком большой')
                except (LearnError, AttributeError):
                    continue
                m.update(files=files, size=total, new=bool(p.get('new')))
                items.append(m)
            res = {'ok': True, 'modules': items, 'repo': REPO}
        except LearnError as e:
            res = {'ok': False, 'modules': [], 'repo': REPO, 'error': 'каталог сейчас недоступен: ' + str(e)}
        except (ValueError, UnicodeDecodeError, AttributeError):
            res = {'ok': False, 'modules': [], 'repo': REPO, 'error': 'каталог повреждён (index.json не читается)'}
        self._index = (time.time(), res)
        return res

    def catalog_view(self, force=False):
        """the catalog with what is already here: {installed: version|None, update: bool, builtin: bool}"""
        cat = self.catalog(force)
        have = {m['id']: m for m in self.list()}
        out = []
        for m in cat['modules']:
            h = have.get(m['id'])
            out.append({**{k: m[k] for k in ('id', 'title', 'description', 'version', 'author', 'tag', 'size', 'new')},
                        'builtin': bool(h and h['builtin']), 'installed': h['version'] if h and not h['builtin'] else None,
                        'update': bool(h and not h['builtin'] and _vtuple(m['version']) > _vtuple(h['version']))})
        return {**cat, 'modules': out}

    def install(self, mid, fetch=None):
        """download one module (every file checked against the size and SHA-256 from the index) and swap it in whole; → its description"""
        fetch = fetch or _get
        entry = next((m for m in self.catalog(True)['modules'] if m['id'] == mid), None)
        if not entry:
            raise LearnError('такого модуля нет в каталоге')
        if os.path.isdir(os.path.join(BUILTIN_DIR, mid)):
            raise LearnError('этот модуль уже встроен в Rack Live')
        tmp = os.path.join(self.mods, '.' + mid + '.tmp')
        with self.lock:
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp)
            try:
                for f in entry['files']:
                    blob = fetch(f"{RAW}modules/{mid}/{f['name']}", f['size'])
                    if len(blob) != f['size'] or hashlib.sha256(blob).hexdigest() != f['sha256']:
                        raise LearnError(f"файл {f['name']} не совпал с каталогом (размер или контрольная сумма)")
                    dst = os.path.join(tmp, *f['name'].split('/'))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, 'wb') as fh:
                        fh.write(blob)
                meta = {k: entry[k] for k in ('id', 'title', 'description', 'version', 'author', 'tag', 'icon')}
                with open(os.path.join(tmp, 'module.json'), 'w', encoding='utf-8') as fh:
                    json.dump(meta, fh, ensure_ascii=False)
                final, old = os.path.join(self.mods, mid), os.path.join(self.mods, '.' + mid + '.old')
                shutil.rmtree(old, ignore_errors=True)
                if os.path.isdir(final):
                    os.replace(final, old)
                os.replace(tmp, final)
                shutil.rmtree(old, ignore_errors=True)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
        return meta

    def remove(self, mid, wipe=False):
        if not ID_RE.match(str(mid or '')) or os.path.isdir(os.path.join(BUILTIN_DIR, mid)):
            raise LearnError('встроенный модуль удалить нельзя')
        with self.lock:
            shutil.rmtree(os.path.join(self.mods, mid), ignore_errors=True)
            if wipe:
                try:
                    os.remove(self._ppath(mid))
                except OSError:
                    pass
