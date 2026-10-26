"""Frank's own project: a separate copy of Rack Live that he works in, and the link between that copy and the running panel.

Why it exists: with the «полный доступ» switch on (cfg.ai.full) Frank stops being a helper inside the panel and becomes an agent like Claude Code /
opencode — but he still must not rewrite the code of the panel that is running at this very moment, file by file, with no way back. So:

  · `seed()` makes the project: a git clone of the Rack Live repository (with build.py, tools/, tests), or — when there is no network — a copy of the
    code that is running right now, marked as such;
  · Frank edits and builds and tests INSIDE the project (his own folder, data/frank/project — see frank_agent.resolve, it is his and therefore writable);
  · `deploy()` is the link back: the new code is import-checked in a separate process, the current code is moved to .prev/, the project's rackd/ and web/
    are copied in, the state is written as «pending» and the process restarts itself. updater.boot_guard() then rolls the panel back by itself if the new
    code cannot start three times in a row — the same protection the ordinary updater uses. «Откатить» is the manual version of that.

What the project never contains: the panel's data (device passwords, the admin, history). It is code only, and `deploy()` copies only rackd/ and web/.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from . import updater

REPO = 'https://github.com/mikolord/racklive'
PARTS = ('rackd', 'web')                         # the only things a live panel is made of (web/ has the built app.js)
SKIP = {'__pycache__', '.git', 'node_modules', '.prev', '.failed', '.update', '.idea', '.vscode'}
LIMIT_TEXT = 14000
CLONE_TIMEOUT = 240
MAX_FILES = 20000
CACHE_TTL = 15
_CACHE = {}


class DevError(Exception):
    pass


def path(data_dir):
    return os.path.join(data_dir, 'frank', 'project')


def panel_root():
    """the folder the running panel's code lives in (what deploy() replaces)"""
    return updater.ROOT


def _state_path(data_dir):
    return os.path.join(data_dir, 'frank', 'project.json')


def state(data_dir):
    try:
        with open(_state_path(data_dir), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def set_state(data_dir, **kw):
    st = dict(state(data_dir), **kw)
    os.makedirs(os.path.dirname(_state_path(data_dir)), exist_ok=True)
    tmp = _state_path(data_dir) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, _state_path(data_dir))
    _CACHE.clear()
    return st


def _cut(s, n=LIMIT_TEXT):
    s = str(s or '')
    return s if len(s) <= n else s[:n] + f'\n…(обрезано, всего {len(s)} символов)'


def _run(args, cwd, timeout=180, env=None):
    """→ (code, output); 124 = не уложилось, 127 = нет программы"""
    e = dict(os.environ)
    for k in [k for k in e if k.startswith('RL_')]:      # the panel's own settings stay out of the project's commands
        e.pop(k)
    e.update(env or {})
    e['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        r = subprocess.run(args, cwd=cwd, env=e, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return r.returncode, (r.stdout or b'').decode('utf-8', 'replace')
    except FileNotFoundError:
        return 127, f'нет программы {args[0]}'
    except subprocess.TimeoutExpired:
        return 124, f'не уложилось в {timeout} с и было остановлено'
    except OSError as e2:
        return 1, f'ошибка: {e2}'


def version(project=None):
    """the version this code calls itself"""
    try:
        with open(os.path.join(project or '', 'rackd', 'server.py'), encoding='utf-8') as f:
            m = re.search(r"^VERSION\s*=\s*'([^']+)'", f.read(), re.M)
        return m.group(1) if m else ''
    except OSError:
        return ''


def _newest(folder, exts):
    t = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if exts and not f.endswith(exts):
                continue
            try:
                t = max(t, os.path.getmtime(os.path.join(root, f)))
            except OSError:
                pass
    return t


def exists(data_dir):
    p = path(data_dir)
    return all(os.path.isdir(os.path.join(p, x)) for x in PARTS)


def status(data_dir, root=None, demo=False, fresh=False):
    """what the settings card and the model see; cached for a few seconds (a git call is cheap but the view is built on every poll)"""
    key = (os.path.realpath(data_dir), os.path.realpath(root or updater.ROOT), bool(demo))
    hit = _CACHE.get(key)
    if hit and not fresh and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    out = _status(data_dir, root, demo)
    _CACHE[key] = (time.time(), out)
    return out


def _status(data_dir, root=None, demo=False):
    p = path(data_dir)
    st = state(data_dir)
    ok = exists(data_dir)
    out = {'path': p, 'exists': ok, 'source': st.get('source'), 'created': st.get('created'),
           'lastDeploy': st.get('lastDeploy'), 'lastBuild': st.get('lastBuild'), 'lastTest': st.get('lastTest'),
           'version': version(p) if ok else '', 'runningVersion': None, 'build': None, 'canDeploy': False, 'why': '', 'git': None}
    if not ok:
        out['why'] = 'проекта ещё нет'
        return out
    # git: is it a clone, what branch, what is changed right now
    code, text = _run(['git', '-C', p, 'rev-parse', '--abbrev-ref', 'HEAD'], p, timeout=20)
    if code == 0:
        _, short = _run(['git', '-C', p, 'log', '-1', '--format=%h %s'], p, timeout=20)
        _, dirty = _run(['git', '-C', p, 'status', '--short'], p, timeout=30)
        out['git'] = {'branch': text.strip(), 'head': short.strip()[:120], 'changes': len([l for l in dirty.splitlines() if l.strip()])}
    src = _newest(os.path.join(p, 'web', 'src'), ('.jsx',)) if os.path.isdir(os.path.join(p, 'web', 'src')) else 0
    built = os.path.getmtime(os.path.join(p, 'web', 'app.js')) if os.path.isfile(os.path.join(p, 'web', 'app.js')) else 0
    out['build'] = {'built': bool(built), 'stale': bool(src and built and built < src), 'at': int(built) if built else None}
    root = root or updater.ROOT
    why = []
    if demo:
        why.append('в демо-режиме выкладка отключена')
    if os.name != 'posix':
        why.append('выкладка изнутри работает на Linux (NAS, Docker, роутер)')
    if os.path.exists(os.path.join(root, '.git')):
        why.append('это рабочая копия из git — её правят и собирают вручную')
    if not all(os.access(os.path.join(root, x), os.W_OK) for x in PARTS):
        why.append('у панели нет права записи в свою папку')
    if not os.path.isfile(os.path.join(p, 'build.py')) and out['build'] and out['build']['stale']:
        why.append('исходники новее собранного app.js, а build.py в проекте нет — не пересобрать')
    out['canDeploy'] = not why
    out['why'] = '; '.join(why)
    try:
        with open(os.path.join(root, 'rackd', 'server.py'), encoding='utf-8') as f:
            m = re.search(r"^VERSION\s*=\s*'([^']+)'", f.read(), re.M)
        out['runningVersion'] = m.group(1) if m else ''
    except OSError:
        pass
    return out


# ───────── making the project ─────────
def seed(data_dir, root, demo=False, progress=lambda s: None):
    """clone the repository (build.py, tools, tests) — or, without network, copy the code that runs now; → text for the person"""
    if demo:
        raise DevError('в демо-режиме проект не создаётся')
    p = path(data_dir)
    if exists(data_dir):
        raise DevError('проект уже есть: ' + p)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.isdir(p) and os.listdir(p):
        raise DevError('папка проекта не пустая: ' + p)
    progress('Клонирую Rack Live с GitHub…')
    code, text = _run(['git', 'clone', '--depth', '1', REPO, p], os.path.dirname(p), timeout=CLONE_TIMEOUT)
    source = 'git'
    if code != 0 or not exists(data_dir):
        progress('GitHub недоступен — копирую работающий код панели…')
        shutil.rmtree(p, ignore_errors=True)
        os.makedirs(p)
        for part in PARTS:
            src = os.path.join(root, part)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(p, part), ignore=shutil.ignore_patterns(*SKIP, '*.pyc'))
        source = 'copy'
        if not exists(data_dir):
            raise DevError('не удалось ни склонировать репозиторий, ни скопировать код панели: ' + _cut(text, 400))
    set_state(data_dir, source=source, created=int(time.time()), cloneLog=_cut(text, 600) if source == 'copy' else '')
    note = ('Проект — клон https://github.com/mikolord/racklive (есть build.py, tools/, тесты).' if source == 'git'
            else 'Проект — копия работающего кода (GitHub был недоступен): build.py и тестов в нём нет, сборку фронта здесь не сделать.')
    return note + '\nПапка: ' + p


# ───────── building and testing inside the project ─────────
def build(data_dir, progress=lambda s: None):
    p = path(data_dir)
    if not exists(data_dir):
        raise DevError('проекта нет — сначала создайте его')
    if not os.path.isfile(os.path.join(p, 'build.py')):
        raise DevError('в проекте нет build.py (он сделан копией кода без сети) — соберите app.js на машине с исходниками и положите в проект')
    progress('Собираю фронт (babel)…')
    code, text = _run([sys.executable, 'build.py'], p, timeout=600)
    ok = code == 0 and 'ok:' in text
    set_state(data_dir, lastBuild={'t': int(time.time()), 'ok': ok, 'out': _cut(text, 1500)})
    if not ok:
        raise DevError('сборка не прошла (код ' + str(code) + '):\n' + _cut(text, 2000))
    return _cut(text, 2000)


def test(data_dir, progress=lambda s: None):
    p = path(data_dir)
    if not exists(data_dir):
        raise DevError('проекта нет — сначала создайте его')
    sm = os.path.join(p, 'tools', 'smoke.py')
    if not os.path.isfile(sm):
        raise DevError('в проекте нет tools/smoke.py (он сделан копией кода без сети)')
    progress('Прогоняю smoke-тест…')
    code, text = _run([sys.executable, os.path.join('tools', 'smoke.py')], p, timeout=1500)
    ok = 'ВСЁ OK' in text
    set_state(data_dir, lastTest={'t': int(time.time()), 'ok': ok})
    tail = '\n'.join(text.strip().splitlines()[-25:])
    if not ok:
        raise DevError('smoke нашёл ошибки:\n' + _cut(tail, 2500))
    return 'smoke: ВСЁ OK\n' + _cut(tail, 1500)


def _import_check(project):
    """the new code must at least import and read its own version — in a separate process, before anything is replaced"""
    with __import__('tempfile').TemporaryDirectory() as td:
        return _run([sys.executable, '-c', 'import rackd.server as s; print(s.VERSION)'], project, timeout=120,
                    env={'PYTHONPATH': project, 'RL_DATA': td, 'RL_WEB': os.path.join(project, 'web')})


# ───────── the link back into the running panel ─────────
def deploy(data_dir, root, demo=False, progress=lambda s: None):
    """replace the panel's code with the project's, keep the old one in .prev, restart; boot_guard rolls back if it cannot start"""
    if demo:
        raise DevError('в демо-режиме выкладка отключена')
    if os.name != 'posix':
        raise DevError('выкладка изнутри работает на Linux (NAS, Docker, роутер)')
    if os.path.exists(os.path.join(root, '.git')):
        raise DevError('это рабочая копия из git: её собирают и обновляют вручную, изнутри не перезаписываю')
    p = path(data_dir)
    if not exists(data_dir):
        raise DevError('проекта нет — сначала создайте его')
    if not all(os.access(os.path.join(root, x), os.W_OK) for x in PARTS):
        raise DevError('у панели нет права записи в свою папку')
    progress('Проверяю, что новый код запускается…')
    code, text = _import_check(p)
    if code != 0:
        raise DevError('новый код не запускается, ничего не меняю:\n' + _cut(text.strip()[-1500:], 1500))
    new_version = text.strip().splitlines()[-1] if text.strip() else version(p)
    progress('Сохраняю текущий код в .prev…')
    prev = os.path.join(root, '.prev')
    shutil.rmtree(prev, ignore_errors=True)
    os.makedirs(prev, exist_ok=True)
    moved = []
    try:
        for part in PARTS:
            cur = os.path.join(root, part)
            if os.path.isdir(cur):
                shutil.move(cur, os.path.join(prev, part))
                moved.append(part)
        progress('Копирую код проекта в панель…')
        for part in PARTS:
            shutil.copytree(os.path.join(p, part), os.path.join(root, part), ignore=shutil.ignore_patterns(*SKIP, '*.pyc'))
    except Exception as e:
        for part in moved:                              # half way: put the old code back
            cur = os.path.join(root, part)
            if not os.path.isdir(cur):
                shutil.move(os.path.join(prev, part), cur)
        raise DevError(f'не удалось заменить файлы ({type(e).__name__}: {e}) — всё оставлено как было')
    updater.save_state({'status': 'pending', 'from': state(data_dir).get('lastDeploy', {}).get('version') or '', 'to': new_version,
                        'attempts': 0, 't': int(time.time()), 'auto': False, 'frank': True})
    set_state(data_dir, lastDeploy={'t': int(time.time()), 'version': new_version, 'ok': True})
    progress('Перезапускаю панель…')
    time.sleep(1.0)
    threading.Thread(target=updater._restart, daemon=True).start()
    return f'выложено: панель перезапускается на коде проекта (версия {new_version}). Если не поднимется — вернётся прежний код сам.'


def rollback(root, data_dir=None):
    """put the saved previous code back (manual version of boot_guard)"""
    if not updater.put_back(root, None, 'откат вручную (проект Frank)'):
        raise DevError('предыдущего кода нет — откатывать нечего')
    threading.Thread(target=lambda: (time.sleep(1.0), updater._restart()), daemon=True).start()
    if data_dir:
        set_state(data_dir, lastDeploy=dict(state(data_dir).get('lastDeploy') or {}, rolledBack=int(time.time())))
    return 'возвращаю прежний код, панель перезапускается'


def guide(data_dir, root=None):
    """what the model is told about the project"""
    st = status(data_dir, root)
    if not st['exists']:
        return f"Своего проекта ещё нет. Инструмент project (op='seed') создаст отдельную копию Rack Live в {st['path']} — там есть build.py и тесты."
    lines = [f"Твой проект: {st['path']} (версия {st['version'] or '?'}" + (f", git {st['git']['branch']} @ {st['git']['head']}" if st.get('git') else ', копия кода без git') + ').',
             'Правь код прямо в проекте (это твоя папка), собирай project op=build, проверяй project op=test, а чтобы панель начала работать на этом коде — project op=deploy (старый код уходит в .prev, панель перезапускается, при сбое вернётся сама).',
             'Работающую панель иначе не трогай: ни файлы в её папке, ни данные (пароли устройств, вход). Выкладывать код в GitHub и на другие машины — не твоё дело, это решает человек.']
    if not st['canDeploy']:
        lines.append('Выкладка сейчас недоступна: ' + st['why'] + '.')
    return '\n'.join(lines)
