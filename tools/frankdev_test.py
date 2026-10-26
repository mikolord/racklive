"""«Полный доступ» Frank: his own project of Rack Live (rackd/frankdev.py) and the link back to the running panel.
Checks: the folder and its rules, making the project (clone → fallback copy), build/test refusals, deployment guards, rollback of the panel,
the tool and the system prompt through a real demo server with a fake model, and that nothing changes when the switch is off.
Run: python tools/frankdev_test.py (prints ВСЁ OK). The real deployment (copying into the panel and restarting) is checked on Linux/NAS:
tools/frankdev_deploy_test.py — it must not run on a working panel."""
import http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import frankdev as D      # noqa: E402
from rackd import frank_agent as A   # noqa: E402
from rackd import updater            # noqa: E402

bad = []
DATA = tempfile.mkdtemp(prefix='frankdev-unit-')


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)[:300]))
    if not ok:
        bad.append(name)


def raises(fn, part=''):
    try:
        fn()
    except Exception as e:
        return part in str(e)
    return False


# ── где проект и что о нём известно без него ──
check('проект лежит в папке Frank (там ему можно писать)', D.path(DATA) == os.path.join(DATA, 'frank', 'project')
      and D.path(DATA).startswith(A.work(DATA)[:-5]))
st = D.status(DATA, ROOT, fresh=True)
check('проекта нет: status честно говорит об этом и выкладка запрещена', st['exists'] is False and st['canDeploy'] is False and 'проекта ещё нет' in st['why'], st)
check('в демо проект не создаётся', raises(lambda: D.seed(DATA, ROOT, demo=True), 'демо'))
check('в демо выкладка запрещена', raises(lambda: D.deploy(DATA, ROOT, demo=True), 'демо'))
check('сборка и тесты без проекта — понятная ошибка', raises(lambda: D.build(DATA), 'проекта нет') and raises(lambda: D.test(DATA), 'проекта нет'))

# ── создание проекта: git недоступен → копия работающего кода ──
D.REPO = 'file:///' + os.path.join(DATA, 'нет-такого-репозитория')
D.CLONE_TIMEOUT = 60
note = D.seed(DATA, ROOT, progress=lambda s: None)
p = D.path(DATA)
check('проект создан копией кода, когда git недоступен', os.path.isdir(os.path.join(p, 'rackd')) and os.path.isdir(os.path.join(p, 'web'))
      and 'копия работающего кода' in note, note[:200])
check('источник и версия проекта известны', D.state(DATA).get('source') == 'copy' and D.version(p) == D.version(ROOT) != '', (D.state(DATA).get('source'), D.version(p)))
check('в копии нет данных панели (пароли устройств)', not os.path.exists(os.path.join(p, 'data')) and not os.path.exists(os.path.join(p, 'data', 'config.json')))
st = D.status(DATA, ROOT, fresh=True)
check('status после создания: exists, версия, без git', st['exists'] and st['version'] and st['git'] is None, st)
check('без build.py сборка объясняет почему', raises(lambda: D.build(DATA), 'build.py'))
check('без tools/smoke.py тест объясняет почему', raises(lambda: D.test(DATA), 'smoke.py'))
check('повторно создать проект нельзя', raises(lambda: D.seed(DATA, ROOT), 'уже есть'))

# ── выкладка: чего она не делает ни при каких условиях ──
if os.name != 'posix':
    check('выкладка на Windows отказывает с объяснением', raises(lambda: D.deploy(DATA, ROOT), 'Linux'))
fake = tempfile.mkdtemp()
os.makedirs(os.path.join(fake, '.git'))
check('рабочую копию из git панель не перезаписывает', raises(lambda: D.deploy(DATA, fake), 'рабочая копия') or os.name != 'posix')
shutil.rmtree(fake, ignore_errors=True)

# ── проверка кода перед заменой ──
broken = tempfile.mkdtemp()
os.makedirs(os.path.join(broken, 'rackd'))
with open(os.path.join(broken, 'rackd', '__init__.py'), 'w') as f:
    f.write('')
with open(os.path.join(broken, 'rackd', 'server.py'), 'w', encoding='utf-8') as f:
    f.write("raise SystemExit('сломано')\n")
code, out = D._import_check(broken)
check('сломанный код не проходит проверку запуска', code != 0, out)
os.makedirs(os.path.join(broken, 'web'))
code2, out2 = D._import_check(p)
check('целый код проекта проходит проверку и называет версию', code2 == 0 and D.version(p) in out2, out2)
shutil.rmtree(broken, ignore_errors=True)

# ── замена кода панели (_swap: половина deploy, без перезапуска) ──
data3 = tempfile.mkdtemp(prefix='frankdev-swap-')
D.seed(data3, ROOT, progress=lambda s: None)          # проект = копия кода (git в тесте недоступен)
root2 = tempfile.mkdtemp(prefix='frankdev-panel-')
for part in ('rackd', 'web'):
    os.makedirs(os.path.join(root2, part))
    open(os.path.join(root2, part, 'old.txt'), 'w').write('старый код')
with open(os.path.join(root2, 'rackd', 'server.py'), 'w', encoding='utf-8') as f:
    f.write("VERSION = '1.9.9'\n")
old_v, new_v = D._swap(data3, root2)
check('_swap: версии до и после известны, старый код в .prev',
      old_v == '1.9.9' and new_v == D.version(ROOT) and os.path.exists(os.path.join(root2, '.prev', 'rackd', 'old.txt'))
      and os.path.exists(os.path.join(root2, 'rackd', 'server.py')) and not os.path.exists(os.path.join(root2, 'rackd', 'old.txt')), (old_v, new_v))
check('_swap: в панель попал именно код проекта',
      open(os.path.join(root2, 'rackd', 'server.py'), encoding='utf-8').read() == open(os.path.join(D.path(data3), 'rackd', 'server.py'), encoding='utf-8').read())
broken_proj = tempfile.mkdtemp(prefix='frankdev-broken-')
os.makedirs(os.path.join(broken_proj, 'frank', 'project', 'rackd'))
os.makedirs(os.path.join(broken_proj, 'frank', 'project', 'web'))
open(os.path.join(broken_proj, 'frank', 'project', 'rackd', '__init__.py'), 'w').write('')
with open(os.path.join(broken_proj, 'frank', 'project', 'rackd', 'server.py'), 'w', encoding='utf-8') as f:
    f.write("raise SystemExit('так не работает')\n")
before = open(os.path.join(root2, 'rackd', 'server.py'), encoding='utf-8').read()
check('_swap: сломанный код не трогает панель', raises(lambda: D._swap(broken_proj, root2), 'не запускается')
      and open(os.path.join(root2, 'rackd', 'server.py'), encoding='utf-8').read() == before)
for x in (data3, root2, broken_proj):
    shutil.rmtree(x, ignore_errors=True)

# ── «фронт не собран» — только когда исходники правда новее (свежий клон — не повод) ──
data4 = tempfile.mkdtemp(prefix='frankdev-stale-')
proj4 = os.path.join(data4, 'frank', 'project')
os.makedirs(os.path.join(proj4, 'rackd'))
os.makedirs(os.path.join(proj4, 'web', 'src'))
with open(os.path.join(proj4, 'rackd', 'server.py'), 'w', encoding='utf-8') as f:
    f.write("VERSION = '3.3.3'\n")
now = time.time()
open(os.path.join(proj4, 'web', 'app.js'), 'w').write('// built')
open(os.path.join(proj4, 'web', 'src', 'x.jsx'), 'w').write('// src')
os.utime(os.path.join(proj4, 'web', 'app.js'), (now, now))
os.utime(os.path.join(proj4, 'web', 'src', 'x.jsx'), (now + 30, now + 30))       # свежий клон: разница в секунды
check('свежий клон не считается «не собран»', D.status(data4, ROOT, fresh=True)['build']['stale'] is False)
os.utime(os.path.join(proj4, 'web', 'src', 'x.jsx'), (now + 300, now + 300))     # правка через пять минут
check('правка после сборки — «фронт не собран»', D.status(data4, ROOT, fresh=True)['build']['stale'] is True)
shutil.rmtree(data4, ignore_errors=True)

# ── откат панели: прежний код возвращается ──
panel = tempfile.mkdtemp()
for part in ('rackd', 'web'):
    os.makedirs(os.path.join(panel, part))
    open(os.path.join(panel, part, 'now.txt'), 'w').write('new')
    os.makedirs(os.path.join(panel, '.prev', part), exist_ok=True)
    open(os.path.join(panel, '.prev', part, 'old.txt'), 'w').write('old')
# откат в конце запускает перезапуск панели отдельным потоком — в тесте он должен ничего не делать
# (иначе os.execv запустит этот же тест заново: так он и зацикливался)
updater._restart = lambda: None
text = D.rollback(panel, DATA)
check('откат вернул прежний код панели', 'перезапускается' in text and os.path.exists(os.path.join(panel, 'rackd', 'old.txt'))
      and not os.path.exists(os.path.join(panel, 'rackd', 'now.txt')), os.listdir(os.path.join(panel, 'rackd')))
check('откат без .prev — понятная ошибка', raises(lambda: D.rollback(tempfile.mkdtemp()), 'нечего'))
time.sleep(1.5)          # поток перезапуска отработал и ничего не сделал
shutil.rmtree(panel, ignore_errors=True)

# ── что модель знает о проекте ──
g = D.guide(DATA, ROOT)
check('инструкция модели: где проект, чем собирать и выкладывать', D.path(DATA) in g and 'deploy' in g and 'build' in g, g[:300])
shutil.rmtree(DATA, ignore_errors=True)
check('без проекта инструкция предлагает его создать', 'создаст' in D.guide(tempfile.mkdtemp(), ROOT))

# ── через сервер с поддельной моделью ──
plan, results = {}, []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        msgs = body.get('messages') or []
        last = msgs[-1]
        if last['role'] == 'tool':
            results.append(last['content'])
            msg = {'role': 'assistant', 'content': 'Готово.'}
        else:
            q = last['content'] if isinstance(last['content'], str) else ''
            call = next((v for k, v in plan.items() if k in q), None)
            msg = ({'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'c1', 'type': 'function',
                                                                      'function': {'name': call[0], 'arguments': json.dumps(call[1], ensure_ascii=False)}}]} if call
                   else {'role': 'assistant', 'content': 'Ок.'})
        Fake.last_tools = [t['function']['name'] for t in body.get('tools') or []]
        Fake.last_system = next((m['content'] for m in msgs if m.get('role') == 'system'), '')
        out = json.dumps({'choices': [{'message': msg}], 'usage': {'prompt_tokens': 500, 'completion_tokens': 10}}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(out)))
        self.end_headers(); self.wfile.write(out)


fake = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
_s = socket.socket(); _s.bind(('127.0.0.1', 0)); port = _s.getsockname()[1]; _s.close()   # a free port: a forgotten server from an old run must not answer instead of ours
data2 = tempfile.mkdtemp(prefix='frankdev-srv-')
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data2, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port}'
print('  · папки теста:', DATA, '|', data2)


def api(path, body=None, method=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method=method or ('POST' if body is not None else 'GET'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:                 # 400 = a refusal with a reason (the panel answers so for admin mistakes)
        return json.loads(e.read() or b'{}')


def say(text, chat=None):
    r = api('/api/ai/ask', {'chat': chat, 'text': text})
    if 'job' not in r:
        raise SystemExit('вопрос не принят: ' + json.dumps(r, ensure_ascii=False))
    for _ in range(300):
        j = api('/api/ai/job', {'job': r['job']})
        if j.get('done'):
            return r['chat'], j
        time.sleep(.2)
    raise SystemExit('задача не закончилась')


def last_props(cid):
    return [x for m in api('/api/ai/chats/' + cid)['messages'] for x in m.get('proposals') or []]


try:
    for _ in range(40):
        try:
            api('/api/state')
            break
        except Exception:
            time.sleep(.5)
    api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': f'http://127.0.0.1:{fake.server_address[1]}/v1', 'model': 'fake', 'key': 'k'}, 'PUT')
    api('/api/ai', {'agent': True, 'agentMode': 'ask'}, 'PUT')
    say('Привет')
    check('без «полного доступа» инструмента проекта нет', 'project' not in Fake.last_tools, Fake.last_tools)
    check('без «полного доступа» API проекта отказывает', 'полный доступ выключен' in json.dumps(api('/api/ai/project', {'op': 'status'}), ensure_ascii=False))

    api('/api/ai', {'full': True, 'agentMode': 'ask'}, 'PUT')
    st = api('/api/state')['ai']
    check('галочка «полный доступ» сохраняется и включает агента', st['full'] is True and st['agent'] is True, st)
    check('карточка настроек получает состояние проекта', isinstance(st.get('project'), dict) and st['project']['exists'] is False, st.get('project'))
    say('Привет ещё раз')
    check('в полном доступе есть инструмент проекта и его инструкция',
          'project' in Fake.last_tools and 'ПОЛНЫЙ ДОСТУП' in Fake.last_system and 'frank/project' in Fake.last_system.replace('\\', '/'), Fake.last_system[-400:])
    plan['СОСТОЯНИЕ'] = ('project', {'op': 'status'})
    say('СОСТОЯНИЕ проекта', None)
    check('project status отдаёт состояние проекта', results and '"exists"' in results[-1], results[-1:])
    plan['СДЕЛАЙ'] = ('project', {'op': 'seed'})
    say('СДЕЛАЙ проект', None)
    check('в демо проект не создаётся (и это видно модели)', 'демо' in results[-1], results[-1:])
    plan['ВЫЛОЖИ'] = ('project', {'op': 'deploy'})
    say('ВЫЛОЖИ в панель', None)
    check('в демо выкладка отказывает', 'демо' in results[-1], results[-1:])
    plan['ПОЛОЖИ'] = ('write_file', {'path': 'full.txt', 'content': 'без карточек'})
    cid3, _ = say('ПОЛОЖИ файл', None)
    check('полный доступ: файл пишется сразу, без карточки',
          os.path.isfile(os.path.join(A.work(data2), 'full.txt')) and not [x for x in last_props(cid3) if x.get('status') == 'pending'], last_props(cid3))
    job = api('/api/ai/project', {'op': 'seed'})
    check('кнопка проекта создаёт фоновую задачу', 'job' in job, job)
    for _ in range(60):
        j = api('/api/dev/job', {'job': job['job']})
        if j.get('done'):
            break
        time.sleep(.2)
    check('задача создания проекта в демо завершается ошибкой с причиной', bool(j.get('error')) and 'демо' in j.get('error', ''), j)
    check('действия проекта — в журнале событий', any(e.get('name') == 'Frank' for e in api('/api/state')['events']))
    api('/api/ai', {'full': False, 'agentMode': 'ask'}, 'PUT')
    say('Привет в третий раз')
    check('после выключения галочки всё как прежде: инструмента проекта нет', 'project' not in Fake.last_tools)
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
    fake.shutdown()
    shutil.rmtree(data2, ignore_errors=True)

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
