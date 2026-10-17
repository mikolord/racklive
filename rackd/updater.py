"""Updates from GitHub (Settings → «О программе»): tagged releases only (v1.2.3), never the unreviewed main branch.

How it updates itself: the release archive is downloaded from codeload.github.com, only rackd/ and web/ are taken out of it (safe unpacking), the new code is import-checked in a
separate process BEFORE anything is replaced, the old code is kept in .prev/, the new one is swapped in and the process restarts itself (os.execv — works the same in Docker with a
restart policy, on a router with Entware, on a plain Linux). If the new version does not come up healthy (crashes at start three times in a row) the old code is put back by itself
(boot_guard, called before anything else is imported). «Откатить» in the UI does the same by hand.  Not for a git checkout (a developer's copy) and not in demo.
What it cannot change: the Docker image itself (system packages) — rebuild the image for that, the page says so."""
import json, os, re, shutil, subprocess, sys, tarfile, tempfile, threading, time, urllib.request

REPO = 'mikolord/racklive'
API = f'https://api.github.com/repos/{REPO}'
TAG_RE = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')
MAX_TAR = 40 * 1024 * 1024
MAX_UNPACKED = 120 * 1024 * 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = ('rackd', 'web')
MAX_BOOT_TRIES = 3


def vtuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', str(v))[:3]) or (0,)


def _data_dir():
    return os.environ.get('RL_DATA', os.path.join(ROOT, 'data'))


def _state_path(data=None):
    return os.path.join(data or _data_dir(), 'update_state.json')


def load_state(data=None):
    try:
        with open(_state_path(data), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st, data=None):
    try:
        os.makedirs(data or _data_dir(), exist_ok=True)
        with open(_state_path(data), 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
    except OSError:
        pass


def _restart():
    """start again from scratch with the code now on disk (sockets are not inherited: Python opens them non-inheritable)"""
    try:
        args = list(getattr(sys, 'orig_argv', None) or [sys.executable, '-m', 'rackd'])
        os.execv(sys.executable, [sys.executable] + args[1:])
    except OSError:
        os._exit(3)                       # the supervisor (Docker restart policy, init script / cron) starts it again


def put_back(root=ROOT, data=None, why=''):
    """swap the saved previous code back; → True when done"""
    prev, failed = os.path.join(root, '.prev'), os.path.join(root, '.failed')
    if not all(os.path.isdir(os.path.join(prev, p)) for p in PARTS):
        return False
    shutil.rmtree(failed, ignore_errors=True)
    os.makedirs(failed, exist_ok=True)
    for p in PARTS:
        cur = os.path.join(root, p)
        if os.path.isdir(cur):
            shutil.move(cur, os.path.join(failed, p))
        shutil.move(os.path.join(prev, p), cur)
    st = load_state(data)
    save_state(dict(st, status='rolled_back', error=why, t=int(time.time()), attempts=0), data)
    return True


def boot_guard(root=ROOT):
    """called first thing at start-up: a freshly installed version that cannot start is rolled back after MAX_BOOT_TRIES attempts"""
    data = _data_dir()
    st = load_state(data)
    if st.get('status') != 'pending':
        return
    st['attempts'] = int(st.get('attempts') or 0) + 1
    save_state(st, data)
    if st['attempts'] >= MAX_BOOT_TRIES and put_back(root, data, f"версия {st.get('to')} не запускалась ({st['attempts']} попытки подряд) — возвращена {st.get('from')}"):
        _restart()


def mark_ok():
    st = load_state()
    if st.get('status') == 'pending':
        save_state(dict(st, status='ok', attempts=0, t=int(time.time())))


def _get(url, timeout=15, limit=2_000_000):
    req = urllib.request.Request(url, headers={'User-Agent': 'RackLive-updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit + 1)


class Updater:
    def __init__(self, app, version, demo=False):
        self.app, self.version, self.demo = app, version, demo
        self.job = {'running': False}
        self.lock = threading.Lock()
        self.last_check_error = ''

    # ── settings ──
    def mode(self):
        return (self.app.store.cfg.get('update') or {}).get('mode') or 'notify'

    def set_mode(self, mode):
        if mode not in ('off', 'notify', 'auto'):
            raise ValueError('режим: off, notify или auto')
        self.app.store.cfg['update'] = dict(self.app.store.cfg.get('update') or {}, mode=mode)
        self.app.store.save()

    def can_apply(self):
        """→ (bool, reason): is it safe to replace the code of this copy"""
        if self.demo:
            return False, 'в демо-режиме обновление отключено'
        if os.name != 'posix':
            return False, 'обновление изнутри работает на Linux (Docker, NAS, роутер); на Windows обновите вручную'
        if os.path.exists(os.path.join(ROOT, '.git')):
            return False, 'это рабочая копия из git — обновляйте её командой git pull'
        if not all(os.access(os.path.join(ROOT, p), os.W_OK) for p in PARTS) or not os.access(ROOT, os.W_OK):
            return False, 'у программы нет права записи в свою папку'
        return True, ''

    # ── what is the newest release ──
    def latest(self, force=False):
        cache = (self.app.store.cfg.get('update') or {}).get('latest') or {}
        if cache and not force and time.time() - cache.get('checked', 0) < 6 * 3600:
            return cache
        try:
            tags = json.loads(_get(API + '/tags?per_page=50'))
            best = max((t['name'] for t in tags if TAG_RE.match(t.get('name', ''))), key=vtuple, default=None)
            if not best:
                raise ValueError('в репозитории нет релизов')
            notes = ''
            try:
                msg = json.loads(_get(API + '/commits/' + best)).get('commit', {}).get('message', '')
                notes = '\n'.join(l for l in msg.splitlines() if not l.startswith(('Co-Authored-By', 'Claude-Session')))[:2000].strip()
            except Exception:
                pass
            cache = {'tag': best, 'version': best[1:], 'notes': notes, 'checked': int(time.time())}
            self.last_check_error = ''
        except Exception as e:
            self.last_check_error = 'не удалось связаться с GitHub' + ('' if isinstance(e, ValueError) else f' ({type(e).__name__})')
            return cache or {}
        u = dict(self.app.store.cfg.get('update') or {})
        announced = u.get('announced')
        u['latest'] = cache
        if vtuple(cache['version']) > vtuple(self.version) and announced != cache['version']:
            u['announced'] = cache['version']
            self.app.store.cfg['update'] = u
            self.app.store.add_event(None, 'Обновление', 'info', f"вышла версия {cache['version']} (у вас {self.version})")
            if u.get('mode', 'notify') != 'off':
                try:
                    threading.Thread(target=self.app.tgbot.notice, args=(f"⬆️ Вышла новая версия Rack Live {cache['version']} (у вас {self.version}). Настройки → О программе → «Обновить».",), daemon=True).start()
                except Exception:
                    pass
        self.app.store.cfg['update'] = u
        self.app.store.save()
        return cache

    def info(self):
        lat = (self.app.store.cfg.get('update') or {}).get('latest') or {}
        ok, why = self.can_apply()
        st = load_state()
        prev = os.path.join(ROOT, '.prev')
        return {'current': self.version, 'latest': lat.get('version'), 'tag': lat.get('tag'), 'notes': lat.get('notes'), 'checked': lat.get('checked'),
                'newer': bool(lat.get('version')) and vtuple(lat['version']) > vtuple(self.version), 'mode': self.mode(), 'canApply': ok, 'why': why,
                'error': self.last_check_error, 'state': {k: st.get(k) for k in ('status', 'from', 'to', 'error', 't')} if st else None,
                'canRollback': all(os.path.isdir(os.path.join(prev, p)) for p in PARTS) and ok, 'job': dict(self.job)}

    # ── install ──
    def _stage(self, text):
        self.job.update(stage=text)

    def apply(self, tag, auto=False):
        ok, why = self.can_apply()
        if not ok:
            raise ValueError(why)
        if not TAG_RE.match(tag or ''):
            raise ValueError('неверная метка версии')
        with self.lock:
            if self.job.get('running'):
                raise ValueError('обновление уже идёт')
            self.job = {'running': True, 'stage': 'Начинаю', 'tag': tag, 'error': None, 't': time.time()}
        threading.Thread(target=self._run, args=(tag, auto), daemon=True).start()

    def _fail(self, text):
        self.job.update(running=False, error=text, stage='Не получилось')
        self.app.store.add_event(None, 'Обновление', 'warning', f'обновление не удалось: {text}')

    def _run(self, tag, auto):
        stage_dir = os.path.join(ROOT, '.update')
        try:
            shutil.rmtree(stage_dir, ignore_errors=True)
            os.makedirs(stage_dir)
            self._stage(f'Скачиваю версию {tag[1:]}')
            blob = _get(f'https://codeload.github.com/{REPO}/tar.gz/refs/tags/{tag}', timeout=60, limit=MAX_TAR)
            if len(blob) > MAX_TAR:
                return self._fail('архив слишком большой')
            self._stage('Распаковываю и проверяю')
            tmp = os.path.join(stage_dir, 'a.tar.gz')
            with open(tmp, 'wb') as f:
                f.write(blob)
            new = os.path.join(stage_dir, 'new')
            total = 0
            with tarfile.open(tmp, 'r:gz') as t:
                members = t.getmembers()
                top = members[0].name.split('/')[0] if members else ''
                for m in members:
                    rel = m.name[len(top) + 1:] if m.name.startswith(top + '/') else ''
                    first = rel.split('/')[0]
                    if first not in PARTS or '..' in rel.split('/') or rel.startswith('/') or '__pycache__' in rel or 'node_modules' in rel:
                        continue
                    if not (m.isfile() or m.isdir()):
                        continue                              # no links, devices …
                    total += m.size
                    if total > MAX_UNPACKED:
                        return self._fail('архив слишком большой после распаковки')
                    dst = os.path.join(new, rel)
                    if m.isdir():
                        os.makedirs(dst, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        with open(dst, 'wb') as out:
                            out.write(t.extractfile(m).read())
            os.remove(tmp)
            if not all(os.path.isdir(os.path.join(new, p)) for p in PARTS):
                return self._fail('в архиве нет rackd или web')
            # the new code must at least import and report the version it claims — checked in a separate process, nothing is replaced yet
            with tempfile.TemporaryDirectory() as td:
                r = subprocess.run([sys.executable, '-c', 'import rackd.server as s; print(s.VERSION)'], cwd=new, capture_output=True, text=True, timeout=90,
                                   env=dict(os.environ, PYTHONPATH=new, RL_DATA=td, RL_WEB=os.path.join(new, 'web'), PYTHONDONTWRITEBYTECODE='1'))
            if r.returncode != 0 or r.stdout.strip() != tag[1:]:
                return self._fail('новая версия не проходит проверку запуска: ' + ((r.stderr or r.stdout).strip().splitlines() or ['пустой ответ'])[-1][:200])
            self._stage('Заменяю файлы')
            prev = os.path.join(ROOT, '.prev')
            shutil.rmtree(prev, ignore_errors=True)
            os.makedirs(prev)
            moved = []
            try:
                for p in PARTS:
                    shutil.move(os.path.join(ROOT, p), os.path.join(prev, p))
                    moved.append(p)
                for p in PARTS:
                    shutil.move(os.path.join(new, p), os.path.join(ROOT, p))
            except Exception as e:                           # half way: put everything back
                for p in PARTS:
                    cur = os.path.join(ROOT, p)
                    if p in moved and not os.path.isdir(cur):
                        shutil.move(os.path.join(prev, p), cur)
                return self._fail(f'не удалось заменить файлы ({type(e).__name__}) — всё оставлено как было')
            shutil.rmtree(stage_dir, ignore_errors=True)
            save_state({'status': 'pending', 'from': self.version, 'to': tag[1:], 'attempts': 0, 't': int(time.time()), 'auto': auto})
            self.app.store.add_event(None, 'Обновление', 'info', f"{'автоматически ' if auto else ''}установлена версия {tag[1:]} (была {self.version}), перезапуск")
            self._stage('Перезапускаюсь')
            self.job.update(running=False, done=True)
            time.sleep(1.5)
            try:
                self.app.store.save_runtime()
            except Exception:
                pass
            _restart()
        except Exception as e:
            shutil.rmtree(stage_dir, ignore_errors=True)
            self._fail(f'{type(e).__name__}: {str(e)[:160]}')

    def rollback(self):
        ok, why = self.can_apply()
        if not ok:
            raise ValueError(why)
        if not put_back(ROOT, None, 'откат вручную'):
            raise ValueError('предыдущей версии нет')
        self.app.store.add_event(None, 'Обновление', 'warning', 'выполнен откат на предыдущую версию, перезапуск')
        threading.Thread(target=lambda: (time.sleep(1.5), self.app.store.save_runtime(), _restart()), daemon=True).start()

    # ── background: look for a release now and then, install it at night if the owner allowed it ──
    def loop(self):
        threading.Timer(45, mark_ok).start()                 # still alive 45 seconds after start → this version is good
        time.sleep(90)
        while True:
            try:
                if self.mode() != 'off':
                    lat = self.latest()
                    st = load_state()
                    if (self.mode() == 'auto' and lat and vtuple(lat.get('version')) > vtuple(self.version) and self.can_apply()[0]
                            and 3 <= time.localtime().tm_hour < 5 and not self.job.get('running')
                            and not (st.get('status') in ('rolled_back', 'failed') and st.get('to') == lat['version'])
                            and time.time() - (st.get('t') or 0) > 20 * 3600):
                        self.apply(lat['tag'], auto=True)
            except Exception:
                pass
            time.sleep(1800)
