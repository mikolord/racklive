"""Self-update: safe unpacking, the import check before replacing, swap + .prev, rollback by hand and by boot_guard, nothing happens for a git checkout. Run: python tools/update_test.py"""
import io, json, os, shutil, sys, tarfile, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)) if os.path.isfile(globals().get('__file__', '')) else '/app/tools'      # run on the NAS: docker exec -i racklive python - < tools/update_test.py
SRC = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, SRC)
from rackd import updater as U

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


class Store:
    def __init__(self):
        self.cfg, self.events = {}, []

    def add_event(self, *a):
        self.events.append(a)

    def save(self):
        pass

    def save_runtime(self):
        pass


class App:
    def __init__(self):
        self.store = Store()
        self.tgbot = type('T', (), {'notice': lambda s, t: None})()


def copy_code(dst, version=None, break_it=False, mismatch=False):
    for p in ('rackd',):
        shutil.copytree(os.path.join(SRC, p), os.path.join(dst, p), ignore=shutil.ignore_patterns('__pycache__'))
    os.makedirs(os.path.join(dst, 'web'), exist_ok=True)
    open(os.path.join(dst, 'web', 'index.html'), 'w').write('<html>' + (version or 'old') + '</html>')
    if version:
        f = os.path.join(dst, 'rackd', 'server.py')
        s = open(f, encoding='utf-8').read()
        import re
        s = re.sub(r"VERSION = '[^']+'", f"VERSION = '{'0.0.1' if mismatch else version}'", s, count=1)
        if break_it:
            s += '\nthis is not python (\n'
        open(f, 'w', encoding='utf-8').write(s)


def make_tar(version, **kw):
    with tempfile.TemporaryDirectory() as td:
        top = os.path.join(td, f'racklive-{version}')
        os.makedirs(top)
        copy_code(top, version, **kw)
        os.makedirs(os.path.join(top, 'docs'))
        open(os.path.join(top, 'docs', 'x.txt'), 'w').write('not taken')
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as t:
            t.add(top, f'racklive-{version}')
            evil = tarfile.TarInfo(f'racklive-{version}/rackd/../../escaped.txt'); evil.size = 4
            t.addfile(evil, io.BytesIO(b'evil'))
            link = tarfile.TarInfo(f'racklive-{version}/rackd/link'); link.type = tarfile.SYMTYPE; link.linkname = '/etc/passwd'
            t.addfile(link)
        return buf.getvalue()


def setup_root():
    root = tempfile.mkdtemp()
    data = tempfile.mkdtemp()
    copy_code(root)
    U.ROOT = root
    os.environ['RL_DATA'] = data
    return root, data


restarts = []
U._restart = lambda: restarts.append(1)


def wait(u, secs=60):
    t = time.time()
    while time.time() - t < secs:
        if not u.job.get('running'):
            return
        time.sleep(.2)


# tags
ok('метки версий', U.TAG_RE.match('v2.6.1') and not U.TAG_RE.match('main') and not U.TAG_RE.match('v2.6') and not U.TAG_RE.match('v2.6.1; rm -rf'))
ok('сравнение версий', U.vtuple('2.10.0') > U.vtuple('2.9.9') and U.vtuple('2.6.0') == (2, 6, 0))

# success
root, data = setup_root()
u = U.Updater(App(), '0.0.0')
good = make_tar('9.9.9')
U._get = lambda url, timeout=15, limit=0: good
ok('можно обновлять обычную копию', u.can_apply()[0], u.can_apply())
u.apply('v9.9.9')
wait(u)
ok('обновление без ошибок', u.job.get('error') is None and u.job.get('done'), u.job)
ok('новый код на месте, старый сохранён в .prev', 'VERSION = \'9.9.9\'' in open(os.path.join(root, 'rackd', 'server.py'), encoding='utf-8').read()
   and '<html>old</html>' in open(os.path.join(root, '.prev', 'web', 'index.html')).read())
time.sleep(2.2)                                  # the restart comes 1.5 s after the files are in place (the page gets its last answer)
ok('перезапуск запрошен', len(restarts) == 1)
ok('состояние pending', U.load_state(data).get('status') == 'pending' and U.load_state(data).get('to') == '9.9.9')
ok('чужое из архива не взято (docs, выход за папку, ссылки)', not os.path.exists(os.path.join(root, 'docs')) and not os.path.exists(os.path.join(os.path.dirname(root), 'escaped.txt'))
   and not os.path.exists(os.path.join(root, 'rackd', 'link')))
ok('событие записано', any('9.9.9' in str(e) for e in u.app.store.events))

# boot guard: two failed starts are tolerated, the third rolls back
restarts.clear()
U.boot_guard(root); U.boot_guard(root)
ok('две неудачные попытки не откатывают', U.load_state(data)['status'] == 'pending' and not restarts)
U.boot_guard(root)
ok('третья — откат на прежний код', 'VERSION = \'9.9.9\'' not in open(os.path.join(root, 'rackd', 'server.py'), encoding='utf-8').read() and U.load_state(data)['status'] == 'rolled_back' and len(restarts) == 1, U.load_state(data))
ok('в состоянии причина', 'не запускалась' in (U.load_state(data).get('error') or ''))

# healthy start: marked ok, no rollback later
root, data = setup_root()
u = U.Updater(App(), '0.0.0'); U._get = lambda url, timeout=15, limit=0: good
u.apply('v9.9.9'); wait(u)
U.mark_ok()
ok('здоровый запуск закрепляется', U.load_state(data)['status'] == 'ok')
restarts.clear(); U.boot_guard(root); U.boot_guard(root); U.boot_guard(root)
ok('после закрепления откатов нет', not restarts and 'VERSION = \'9.9.9\'' in open(os.path.join(root, 'rackd', 'server.py'), encoding='utf-8').read())

# manual rollback
u.rollback()
ok('ручной откат вернул старый код', '<html>old</html>' in open(os.path.join(root, 'web', 'index.html')).read())

# a broken new version never replaces anything
for name, kw in (('с синтаксической ошибкой', {'break_it': True}), ('с чужой версией внутри', {'mismatch': True})):
    root, data = setup_root()
    u = U.Updater(App(), '0.0.0'); bad = make_tar('9.9.8', **kw); U._get = lambda url, timeout=15, limit=0, b=bad: b
    before = open(os.path.join(root, 'web', 'index.html')).read()
    u.apply('v9.9.8'); wait(u)
    ok(f'версия {name}: не установлена, всё как было', u.job.get('error') and open(os.path.join(root, 'web', 'index.html')).read() == before and not os.path.exists(os.path.join(root, '.prev')), u.job)

# not for a git checkout, not for a bad tag
root, data = setup_root()
os.makedirs(os.path.join(root, '.git'))
u = U.Updater(App(), '0.0.0')
ok('рабочая копия из git не обновляется', not u.can_apply()[0] and 'git' in u.can_apply()[1])
shutil.rmtree(os.path.join(root, '.git'))
try:
    u.apply('main'); ok('плохая метка отклонена', False)
except ValueError:
    ok('плохая метка отклонена', True)
try:
    U.Updater(App(), '0', demo=True).apply('v1.0.0'); ok('в демо не обновляется', False)
except ValueError:
    ok('в демо не обновляется', True)

# newest release from a tags list
app = App()
u = U.Updater(app, '2.6.0')
tags = json.dumps([{'name': 'v2.5.0'}, {'name': 'v2.10.0'}, {'name': 'nightly'}, {'name': 'v2.9.1'}]).encode()
U._get = lambda url, timeout=15, limit=0: tags if url.endswith('per_page=50') else json.dumps({'commit': {'message': 'Версия 2.10.0\n\n- новое\n\nCo-Authored-By: x\nClaude-Session: y'}}).encode()
lat = u.latest(force=True)
ok('последняя версия — максимум по числам, не по тексту', lat['tag'] == 'v2.10.0', lat)
ok('заметки без служебных строк', 'Co-Authored' not in lat['notes'] and 'новое' in lat['notes'])
ok('о новой версии записано в события', any('2.10.0' in str(e) for e in app.store.events))
info = u.info()
ok('сведения: есть новее', info['newer'] and info['latest'] == '2.10.0')
u.set_mode('auto'); ok('режим сохраняется', u.mode() == 'auto')
try:
    u.set_mode('whatever'); ok('плохой режим отклонён', False)
except ValueError:
    ok('плохой режим отклонён', True)
def boom(*a, **k):
    raise OSError('no net')
U._get = boom
u2 = U.Updater(App(), '2.6.0')
ok('без сети — понятная ошибка, не падение', u2.latest(force=True) == {} and 'GitHub' in u2.last_check_error)

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
