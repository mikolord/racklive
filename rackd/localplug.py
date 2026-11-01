"""Local plugins: the owner's OWN code that runs inside Rack Live and changes it (new pages and API routes, background jobs, scripts in the interface).

Unlike community plugins (rackd/community.py: data, never code) and container apps (rackd/capps.py: a separate container), a local plugin is Python that runs in the Rack Live
process with all of its rights. There is no sandbox, so the safety is in WHO and HOW, not in what the code does:
  · only the administrator uploads one (a .zip), by hand; it never comes from a catalog and never from GitHub; it is stored OFF;
  · turning it on is a separate step that names the exact code (sha256 of every file); changed code is switched off again until it is confirmed anew;
  · a plugin that fails while loading is switched off; if the process died while one was loading, it is switched off at the next start (marker file);
  · one global switch (file data/local-plugins/OFF or RL_NO_LOCAL_PLUGINS=1) starts Rack Live without any of them;
  · every plugin has its own data folder and its own API routes /api/x/<id>/… (administrator only).

plugin.json: {"local_api": 1, "id": "my-plugin", "title": "…", "description": "…", "version": "1.0", "author": "…"}
main.py (optional): def register(api): …   api.route(method, path, fn) · api.every(seconds, fn) · api.event(level, text) · api.log(text) · api.devices() · api.data_dir
ui.js (optional): loaded into the Rack Live page for the administrator;  panel.html (optional): its own page, opened from «Инструменты → Локальные плагины»."""
import hashlib, importlib.util, io, json, os, re, shutil, sys, threading, time, traceback, zipfile

LOCAL_API = 1
ID_RE = re.compile(r'^[a-z][a-z0-9-]{2,30}$')
EXT = {'.json', '.py', '.js', '.html', '.css', '.md', '.txt', '.svg', '.png'}
MAX_ZIP, MAX_UNPACKED, MAX_FILES = 1024 * 1024, 3 * 1024 * 1024, 60
TOP = {'local_api', 'id', 'title', 'description', 'version', 'author'}
SECRET_KEY = re.compile(r'(?i)pass|token|secret|key|cookie|community')
MIME = {'.js': 'application/javascript; charset=utf-8', '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
        '.svg': 'image/svg+xml', '.png': 'image/png', '.md': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.py': 'text/plain; charset=utf-8'}
WARNING = ('Локальный плагин — это программа, которая работает внутри Rack Live с теми же правами: она видит ваши устройства и данные, может менять настройки и отправлять '
           'данные в сеть. Включайте только свой код или код, который вы прочитали. Если после включения Rack Live ведёт себя странно, остановите его и создайте файл OFF '
           'в папке data/local-plugins: он запустится без плагинов.')


def digest_of(files):
    h = hashlib.sha256()
    for n in sorted(files):
        h.update(n.encode() + b'\0' + hashlib.sha256(files[n]).digest())
    return h.hexdigest()


def read_zip(blob):
    """→ ({path: bytes}, error)"""
    if len(blob) > MAX_ZIP:
        return None, f'архив больше {MAX_ZIP // 1024} КБ'
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return None, 'это не zip-архив'
    infos = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/') and not os.path.basename(i.filename).startswith('.')]
    if len(infos) > MAX_FILES:
        return None, f'в архиве больше {MAX_FILES} файлов'
    names = [i.filename.replace('\\', '/') for i in infos]
    top = ''
    if 'plugin.json' not in names:
        c = {n.split('/')[0] for n in names if '/' in n}
        if len(c) == 1 and f'{next(iter(c))}/plugin.json' in names:
            top = next(iter(c)) + '/'
    files, total = {}, 0
    for i, n in zip(infos, names):
        rel = n[len(top):] if top and n.startswith(top) else n
        if rel.startswith('/') or '..' in rel.split('/') or ':' in rel or not rel:
            return None, f'недопустимый путь в архиве: «{n}»'
        if os.path.splitext(rel)[1].lower() not in EXT:
            return None, f'тип файла не разрешён: «{rel}» (можно: {", ".join(sorted(EXT))})'
        total += i.file_size
        if total > MAX_UNPACKED:
            return None, 'архив слишком большой после распаковки'
        files[rel] = z.read(i)
    return files, None


def check(files):
    """→ (errors, manifest | None)"""
    if 'plugin.json' not in files:
        return ['в архиве нет plugin.json'], None
    try:
        m = json.loads(files['plugin.json'].decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        return [f'plugin.json: не читается ({e})'], None
    if not isinstance(m, dict):
        return ['plugin.json должен быть объектом'], None
    errors = [f'неизвестное поле «{k}»' for k in m if k not in TOP]
    if m.get('local_api') != LOCAL_API:
        errors.append(f'local_api должен быть {LOCAL_API}')
    if not ID_RE.match(str(m.get('id') or '')):
        errors.append('id: 3–31 символов, латиница в нижнем регистре, цифры и дефис, начинается с буквы')
    t = str(m.get('title') or '').strip()
    if not t or len(t) > 60:
        errors.append('title: нужно название до 60 символов')
    d = str(m.get('description') or '').strip()
    if not d or len(d) > 400:
        errors.append('description: нужно описание до 400 символов')
    if not re.match(r'^[\w.\-+]{1,40}$', str(m.get('version') or '')):
        errors.append('version: например 1.0.0')
    if not any(n in files for n in ('main.py', 'ui.js', 'panel.html')):
        errors.append('в плагине должен быть хотя бы один из файлов main.py, ui.js, panel.html')
    if 'main.py' in files:
        try:
            compile(files['main.py'], 'main.py', 'exec')
        except SyntaxError as e:
            errors.append(f'main.py: синтаксическая ошибка, строка {e.lineno}: {e.msg}')
        if not re.search(r'(?m)^def register\(', files['main.py'].decode('utf-8', 'replace')):
            errors.append('main.py: нужна функция register(api)')
    if errors:
        return errors, None
    return [], {'id': m['id'], 'title': t, 'description': d, 'version': str(m['version']), 'author': str(m.get('author') or '')[:60]}


def guide_text():
    """the instruction a person pastes into an AI assistant so that it writes a safe, working local plugin"""
    return f'''ИНСТРУКЦИЯ ДЛЯ ИИ: как написать локальный плагин для Rack Live (local_api {LOCAL_API})

Rack Live — программа для наблюдения за домашней или офисной сетью (Python, стандартная библиотека, без сторонних пакетов). Локальный плагин — это маленькая программа,
которая работает ВНУТРИ Rack Live с теми же правами. Песочницы нет, поэтому любая ошибка в плагине может сломать Rack Live. Пиши аккуратно и просто.

ЧТО НУЖНО СДЕЛАТЬ
Собрать архив .zip с такими файлами (нужен plugin.json и хотя бы один из main.py, ui.js, panel.html):
  plugin.json  {{"local_api": {LOCAL_API}, "id": "my-plugin", "title": "Название", "description": "Что делает, до 400 символов", "version": "1.0.0", "author": "Имя"}}
               id: латиница в нижнем регистре, цифры, дефис; 3–31 символ; начинается с буквы. Других полей в plugin.json быть не должно.
  main.py      серверная часть (Python 3). Обязательна функция  def register(api):  — она вызывается один раз при включении.
  ui.js        (необязательно) скрипт, который грузится в страницу Rack Live.
  panel.html   (необязательно) своя страница плагина; открывается кнопкой из карточки плагина.
Разрешённые типы файлов: .json .py .js .html .css .md .txt .svg .png. До 60 файлов, архив до 1 МБ. Подпапки можно.

ЧТО ДАЁТ api (больше ничего не предполагай)
  api.route(method, path, fn)  — адрес /api/x/<id>/<path>. fn(req) возвращает dict (это JSON), либо (код, dict), либо (код, bytes, content_type).
                                 req.method, req.path, req.query (dict строк), req.body (bytes), req.json() (dict).
                                 Адреса доступны только вошедшему администратору.
  api.every(seconds, fn)       — фоновая задача (не чаще раза в 5 секунд). Перехватывай ошибки внутри; исключение выключит плагин целиком.
  api.event(level, text)       — запись в журнал событий Rack Live; level: info / warning / error.
  api.log(text)                — запись в журнал самого плагина (виден в его карточке).
  api.devices()                — копия списка устройств (словари); пароли и токены заменены на ***.
  api.data_dir                 — папка плагина для его данных. Пиши ТОЛЬКО туда.
  api.id, api.version          — id плагина и версия Rack Live.

ПРАВИЛА (обязательно)
1. Только стандартная библиотека Python. Никаких pip install.
2. Не читай и не изменяй файлы Rack Live и чужие папки; пиши данные только в api.data_dir.
3. Не подменяй функции Rack Live (никакого monkeypatch), не лезь в его внутренние объекты: пользуйся только api.
4. Не запускай внешние программы и командную строку (subprocess, os.system), если об этом прямо не просили. Если просили, объясни пользователю, что именно запускается.
5. Не отправляй данные наружу (интернет), если об этом прямо не просили. Если просили, скажи, куда и какие данные уходят.
6. Не выводи в ответах и журналах пароли, ключи и токены.
7. В register(api) делай только регистрацию: быстро, без долгих действий и без бесконечных циклов. Долгое — в api.every или в обработчиках.
8. Каждый обработчик быстрый (до секунды-двух), без блокирующих ожиданий. Ошибки обрабатывай и возвращай понятный ответ, например (400, {{"error": "…"}}).
9. Ничего не выполняй при импорте файла, кроме объявлений. Все побочные действия — внутри register и обработчиков.
10. ui.js: не ломай страницу. Оборачивай код в (function () {{ … }})(); и в try/catch. Свои элементы добавляй, чужие не удаляй. Данные бери через fetch('/api/x/<id>/…').
11. panel.html: один самодостаточный файл (стили и скрипт внутри), обращается к API плагина через fetch('/api/x/<id>/…').
12. Не используй eval/exec, не загружай код из интернета.

КАК ОТВЕТИТЬ ПОЛЬЗОВАТЕЛЮ
1. Сначала коротко, простыми словами: что будет делать плагин, какие данные он видит, куда пишет, ходит ли в сеть, запускает ли программы.
2. Затем отдай файлы целиком (plugin.json, main.py, …) и скажи, как собрать из них .zip (файлы лежат в корне архива).
3. В конце напомни: загрузить архив в Rack Live → Инструменты → Локальные плагины; плагин сначала выключен; перед включением нужно прочитать код.

ЕСЛИ ПОЛЬЗОВАТЕЛЬ ПРОСИТ ПРОВЕРИТЬ ЧУЖОЙ ПЛАГИН
Прочитай каждый файл и перечисли по пунктам: что читает, что пишет и куда, какие сетевые адреса и команды использует, нет ли подмены функций, eval/exec,
скрытых или закодированных строк. Скажи прямо, безопасно ли включать, и что именно вызывает сомнения.

ПРИМЕР main.py
def register(api):
    def hello(req):
        return {{"hello": "мир", "devices": len(api.devices())}}
    api.route("GET", "hello", hello)
    api.every(3600, lambda: api.log("прошёл час"))
'''


TEMPLATE_MAIN = '''def register(api):
    """Вызывается один раз при включении плагина. Здесь только регистрация."""
    def hello(req):
        return {"hello": "мир", "devices": len(api.devices()), "rack_live": api.version}

    api.route("GET", "hello", hello)                      # /api/x/<id>/hello
    api.every(3600, lambda: api.log("прошёл час"))        # фоновая задача раз в час
    api.log("плагин запущен")
'''

TEMPLATE_PANEL = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Мой плагин</title>
<body style="font:16px system-ui;padding:16px"><h3>Мой плагин</h3><pre id="o">загружаю…</pre>
<script>fetch('/api/x/my-plugin/hello').then(r => r.json()).then(j => { document.getElementById('o').textContent = JSON.stringify(j, null, 1); })
  .catch(e => { document.getElementById('o').textContent = 'ошибка: ' + e; });</script>
'''


def template_zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('plugin.json', json.dumps({'local_api': LOCAL_API, 'id': 'my-plugin', 'title': 'Мой плагин', 'description': 'Пример: один адрес и одна фоновая задача',
                                              'version': '1.0.0', 'author': ''}, ensure_ascii=False, indent=1))
        z.writestr('main.py', TEMPLATE_MAIN)
        z.writestr('panel.html', TEMPLATE_PANEL)
        z.writestr('README.md', 'Шаблон локального плагина Rack Live. Замените id в plugin.json и в panel.html, допишите код и загрузите архив: Инструменты → Локальные плагины.\n')
    return b.getvalue()


class Request:
    """what a route handler gets"""
    def __init__(self, method, path, query, raw):
        self.method, self.path, self.query, self.body = method, path, query, raw

    def json(self):
        try:
            return json.loads(self.body) if self.body else {}
        except ValueError:
            return {}


class PluginAPI:
    def __init__(self, host, pid):
        self._h, self.id = host, pid
        self.data_dir = os.path.join(host.dir, pid, 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.version = host.version

    def log(self, text):
        self._h.log(self.id, str(text))

    def route(self, method, path, fn):
        """GET/POST/… /api/x/<id>/<path>; fn(req) → dict | (code, dict) | (code, bytes, content_type)"""
        self._h.routes[(self.id, method.upper(), '/' + path.strip('/'))] = fn

    def every(self, seconds, fn):
        seconds = max(5, float(seconds))
        pid, host = self.id, self._h

        def loop():
            while True:
                time.sleep(seconds)
                if not host.is_on(pid):
                    return
                try:
                    fn()
                except Exception:
                    host.fail(pid, 'фоновая задача: ' + traceback.format_exc(limit=3))
        threading.Thread(target=loop, daemon=True, name='lp-' + pid).start()

    def event(self, level, text):
        self._h.add_event(self.id, level if level in ('info', 'warning', 'error') else 'info', str(text)[:300])

    def devices(self):
        """a copy of the device list without passwords / tokens / keys"""
        def scrub(v):
            if isinstance(v, dict):
                return {k: ('***' if SECRET_KEY.search(k) and isinstance(x, str) and x else scrub(x)) for k, x in v.items()}
            if isinstance(v, list):
                return [scrub(x) for x in v]
            return v
        return scrub(json.loads(json.dumps(self._h.get_devices(), default=str)))


class Local:
    def __init__(self, data_dir, get_devices=None, add_event=None, version=''):
        self.dir = os.path.join(data_dir, 'local-plugins')
        os.makedirs(self.dir, exist_ok=True)
        self.get_devices, self._add_event, self.version = get_devices or (lambda: []), add_event or (lambda *a: None), version
        self.lock = threading.Lock()
        self.routes, self.live, self.errors, self.logs = {}, set(), {}, {}
        self.state = self._read_state()

    # ── state ──
    def _sp(self):
        return os.path.join(self.dir, 'state.json')

    def _read_state(self):
        try:
            with open(self._sp(), encoding='utf-8') as f:
                s = json.load(f)
            return s if isinstance(s, dict) and isinstance(s.get('enabled'), dict) else {'enabled': {}}
        except (OSError, ValueError):
            return {'enabled': {}}

    def _save(self):
        tmp = self._sp() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._sp())

    def killed(self):
        return bool(os.environ.get('RL_NO_LOCAL_PLUGINS')) or os.path.exists(os.path.join(self.dir, 'OFF'))

    def is_on(self, pid):
        return pid in self.live

    def log(self, pid, text):
        self.logs.setdefault(pid, []).append(f'{time.strftime("%H:%M:%S")} {text[:300]}')
        del self.logs[pid][:-50]

    def add_event(self, pid, level, text):
        self._add_event(f'Плагин {pid}', level, text)

    def fail(self, pid, why):
        """switch a plugin off and remember why"""
        with self.lock:
            self.live.discard(pid)
            self.state['enabled'].pop(pid, None)
            self.errors[pid] = why[-600:]
            for k in [k for k in self.routes if k[0] == pid]:
                del self.routes[k]
            self._save()
        self.add_event(pid, 'error', 'плагин выключен из-за ошибки: ' + why.strip().splitlines()[-1][:200])

    # ── files ──
    def _pdir(self, pid):
        return os.path.join(self.dir, pid, 'code')

    def files(self, pid):
        root = self._pdir(pid)
        out = {}
        if not ID_RE.match(pid or '') or not os.path.isdir(root):
            return out
        for dp, dirs, fs in os.walk(root):
            dirs[:] = [d for d in dirs if d != '__pycache__']              # Python's own cache is not part of the plugin (it would change the fingerprint after the first run)
            for n in fs:
                p = os.path.join(dp, n)
                with open(p, 'rb') as f:
                    out[os.path.relpath(p, root).replace(os.sep, '/')] = f.read()
        return out

    def get(self, pid):
        fs = self.files(pid)
        if 'plugin.json' not in fs:
            return None
        errors, m = check(fs)
        return None if errors else dict(m, digest=digest_of(fs), files=sorted(fs), has_main='main.py' in fs, has_ui='ui.js' in fs, has_panel='panel.html' in fs)

    def list(self):
        out = []
        for pid in sorted(os.listdir(self.dir)):
            m = self.get(pid) if ID_RE.match(pid) and os.path.isdir(os.path.join(self.dir, pid)) else None
            if m:
                out.append(self.public(m))
        return out

    def public(self, m):
        pid = m['id']
        return dict(m, enabled=self.state['enabled'].get(pid) == m['digest'], live=pid in self.live, changed=pid in self.state['enabled'] and self.state['enabled'][pid] != m['digest'],
                    error=self.errors.get(pid, ''), log=self.logs.get(pid, [])[-20:])

    def install_zip(self, blob):
        files, e = read_zip(blob)
        if e:
            return {'ok': False, 'errors': [e]}
        errors, m = check(files)
        if errors:
            return {'ok': False, 'errors': errors}
        pid = m['id']
        if self.state['enabled'].get(pid):
            return {'ok': False, 'errors': ['плагин сейчас включён: сначала выключите его, потом загрузите новую версию']}
        root = os.path.join(self.dir, pid)
        with self.lock:
            shutil.rmtree(os.path.join(root, 'code'), ignore_errors=True)
            for n, b in files.items():
                p = os.path.join(root, 'code', *n.split('/'))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'wb') as f:
                    f.write(b)
            self.errors.pop(pid, None)
        return {'ok': True, 'errors': [], 'plugin': self.public(self.get(pid)), 'warning': WARNING}

    def remove(self, pid, wipe=False):
        if not ID_RE.match(pid or ''):
            return
        self.disable(pid)
        shutil.rmtree(os.path.join(self.dir, pid, 'code'), ignore_errors=True)
        if wipe:
            shutil.rmtree(os.path.join(self.dir, pid), ignore_errors=True)

    # ── on / off ──
    def enable(self, pid, dig):
        """the administrator confirmed this exact code (`dig`)"""
        if self.killed():
            raise ValueError('локальные плагины выключены целиком (файл OFF в data/local-plugins или RL_NO_LOCAL_PLUGINS)')
        m = self.get(pid)
        if not m:
            raise ValueError('плагин не найден')
        if dig != m['digest']:
            raise ValueError('код плагина изменился после того, как вы его просмотрели. Откройте плагин заново и проверьте')
        self.state['enabled'][pid] = m['digest']
        self._save()
        self._load(pid, m)
        if pid in self.errors and pid not in self.live:
            raise RuntimeError(self.errors[pid].strip().splitlines()[-1])
        self.add_event(pid, 'warning', 'локальный плагин включён администратором')
        return self.public(self.get(pid))

    def disable(self, pid):
        with self.lock:
            self.state['enabled'].pop(pid, None)
            self.live.discard(pid)
            for k in [k for k in self.routes if k[0] == pid]:
                del self.routes[k]
            self._save()

    def _load(self, pid, m):
        marker = os.path.join(self.dir, pid, 'loading')
        if os.path.exists(marker):
            os.remove(marker)                              # reported once; a new confirmation tries again
            return self.fail(pid, 'при прошлом запуске Rack Live не загрузился с этим плагином: он выключен')
        self.errors.pop(pid, None)
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        open(marker, 'w').close()
        try:
            if m['has_main']:
                path = os.path.join(self._pdir(pid), 'main.py')
                spec = importlib.util.spec_from_file_location('rlplug_' + pid.replace('-', '_'), path)
                mod = importlib.util.module_from_spec(spec)
                sys.path.insert(0, self._pdir(pid))
                nobc, sys.dont_write_bytecode = sys.dont_write_bytecode, True
                try:
                    spec.loader.exec_module(mod)
                    self.live.add(pid)                     # before register(): its timers start checking right away
                    mod.register(PluginAPI(self, pid))
                finally:
                    sys.dont_write_bytecode = nobc
                    try:
                        sys.path.remove(self._pdir(pid))
                    except ValueError:
                        pass
            else:
                self.live.add(pid)
        except BaseException:
            self.fail(pid, traceback.format_exc(limit=4))
        finally:
            try:
                os.remove(marker)
            except OSError:
                pass

    def load_all(self):
        """at start: every enabled plugin whose code is exactly what was confirmed"""
        if self.killed():
            return
        for pid, dig in list(self.state['enabled'].items()):
            m = self.get(pid)
            if not m or m['digest'] != dig:
                self.state['enabled'].pop(pid, None)
                self.errors[pid] = 'код изменился с момента включения: плагин выключен до нового подтверждения'
                continue
            self._load(pid, m)
        self._save()

    # ── what the server serves ──
    def scripts(self):
        """URLs of ui.js of every live plugin"""
        return [f'/api/x/{pid}/files/ui.js?v={self.state["enabled"][pid][:8]}' for pid in sorted(self.live) if 'ui.js' in self.files(pid) and pid in self.state['enabled']]

    def file(self, pid, name):
        """→ (bytes, content_type) | None; only declared file types, only of a live plugin"""
        if pid not in self.live or '..' in name or name.startswith('/') or os.path.splitext(name)[1].lower() not in EXT:
            return None
        b = self.files(pid).get(name)
        return None if b is None else (b, MIME.get(os.path.splitext(name)[1].lower(), 'application/octet-stream'))

    def call(self, pid, method, path, query, raw):
        """→ (code, obj | bytes, content_type | None); a failing handler is counted, not fatal"""
        fn = self.routes.get((pid, method, '/' + path.strip('/')))
        if pid not in self.live or fn is None:
            return 404, {'error': 'нет такого маршрута у плагина'}, None
        try:
            r = fn(Request(method, path, query, raw))
        except Exception:
            self.log(pid, 'ошибка в обработчике ' + path + ': ' + traceback.format_exc(limit=2).strip().splitlines()[-1])
            return 500, {'error': 'ошибка в плагине (подробности в его журнале)'}, None
        if isinstance(r, tuple):
            if len(r) == 3 and isinstance(r[1], (bytes, bytearray)):
                return int(r[0]), bytes(r[1]), str(r[2])
            return int(r[0]), r[1], None
        return 200, r if r is not None else {'ok': True}, None
