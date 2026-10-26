"""Frank as an agent: what is allowed, the file tools and the shell, the three modes (ask / edits / full) through a real demo server and a fake model.
Run: python tools/frank_agent_test.py (prints ВСЁ OK)"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import frank_agent as A  # noqa: E402

bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)[:300]))
    if not ok:
        bad.append(name)


# ── rules ──
d = tempfile.mkdtemp()
open(os.path.join(d, 'config.json'), 'w').write('{"secret": 1}')
cls = lambda cmd: A.classify(d, 'shell', {'command': cmd})[0]
check('чтение: ls, cat, grep | wc — сразу', all(cls(c) == 'read' for c in ('ls -la', 'cat notes.txt', 'grep -rn TODO . | wc -l', 'git status', 'df -h')))
check('grep reboot по логу — это чтение, не перезагрузка', cls('grep reboot /var/log/messages') == 'read')
check('изменения — команда', all(cls(c) == 'command' for c in ('echo hi > a.txt', 'pip install requests', 'apk add curl', 'python3 script.py', 'mkdir x')))
check('разрушительное — никогда', all(cls(c) == 'deny' for c in ('rm -rf /', 'rm -rf ~', 'sudo reboot', 'shutdown -h now', 'mkfs.ext4 /dev/sda1', 'dd if=/dev/zero of=/dev/sda',
                                                                  'passwd root', 'useradd x', ':(){ :|:& };:')))
check('данные Rack Live — никогда', all(cls(c) == 'deny' for c in ('cat /data/config.json', 'cat ../../config.json', f'cat {d}/config.json', 'ls /data')))
check('своя папка frank в данных — можно', cls(f'ls {os.path.join(d, "frank")}') == 'read' and cls('ls /data/frank/work') == 'read')
check('путь к данным Rack Live через ../ — отказ', A.classify(d, 'write_file', {'path': '../../config.json'})[0] == 'deny'
      and A.run(d, 'read_file', {'path': '../../config.json'}).startswith('отказано'))
check('программу Rack Live менять нельзя, читать можно', A.classify(d, 'write_file', {'path': os.path.join(A.CODE, 'rackd', 'x.py')})[0] == 'deny'
      and A.classify(d, 'read_file', {'path': os.path.join(A.CODE, 'README.md')})[0] == 'read')
check('режимы: ask спрашивает про правки и команды, edits — только про команды, full — ни о чём',
      A.needs_ok('ask', 'edit') and A.needs_ok('ask', 'command') and not A.needs_ok('ask', 'read') and not A.needs_ok('edits', 'edit') and A.needs_ok('edits', 'command')
      and not A.needs_ok('full', 'command'))

# ── tools ──
r = A.run(d, 'write_file', {'path': 'proj/app.py', 'content': 'print("hi")\nx = 1\nx = 1\n'})
check('write_file создаёт папки и файл', 'создан' in r and os.path.isfile(os.path.join(A.work(d), 'proj', 'app.py')), r)
r = A.run(d, 'read_file', {'path': 'proj/app.py'})
check('read_file — с номерами строк', '     1\tprint("hi")' in r, r)
check('edit_file: неоднозначный фрагмент — ошибка', 'встречается 2 раз' in A.run(d, 'edit_file', {'path': 'proj/app.py', 'old_string': 'x = 1', 'new_string': 'x = 2'}))
check('edit_file: нет фрагмента — ошибка', 'нет' in A.run(d, 'edit_file', {'path': 'proj/app.py', 'old_string': 'zzz', 'new_string': 'y'}))
r = A.run(d, 'edit_file', {'path': 'proj/app.py', 'old_string': 'x = 1', 'new_string': 'x = 2', 'replace_all': True})
check('edit_file: replace_all', 'заменено 2' in r and open(os.path.join(A.work(d), 'proj', 'app.py')).read().count('x = 2') == 2, r)
check('list_dir и find_files', 'proj/' in A.run(d, 'list_dir', {}) and 'app.py' in A.run(d, 'find_files', {'pattern': '*.py'}))
check('search_text', 'app.py:1:' in A.run(d, 'search_text', {'pattern': 'print'}).replace('\\', '/'))
r = A.run(d, 'shell', {'command': 'echo привет-агент'})
check('shell выполняется в рабочей папке, есть код выхода', 'код выхода 0' in r and 'привет-агент' in r, r)
r = A.run(d, 'shell', {'command': 'echo %RL_PORT% $RL_PORT', 'timeout': 10})
check('переменные RL_* панели не видны команде', '9' not in r.split('\n', 1)[1] if os.environ.get('RL_PORT') else True, r)
shutil.rmtree(d, ignore_errors=True)

# ── through the server with a fake model ──
plan = {}          # the user's question → the tool call the fake model makes
results = []       # what came back to the model from tools


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        msgs = body.get('messages') or []
        last = msgs[-1]
        usage = {'prompt_tokens': 500, 'completion_tokens': 10}
        if last['role'] == 'tool':
            results.append(last['content'])
            msg = {'role': 'assistant', 'content': 'Готово.'}
        else:
            q = last['content'] if isinstance(last['content'], str) else ''
            call = next((v for k, v in plan.items() if k in q), None)
            msg = {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': call[0], 'arguments': json.dumps(call[1], ensure_ascii=False)}}]} if call \
                else {'role': 'assistant', 'content': 'Ок.'}
        self.tools = [t['function']['name'] for t in body.get('tools') or []]
        Fake.last_tools = self.tools
        Fake.last_system = msgs[0]['content'] if msgs and msgs[0]['role'] == 'system' else ''
        out = json.dumps({'choices': [{'message': msg}], 'usage': usage}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out)


fake = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
port, data = 9975, tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port}'
work = os.path.join(data, 'frank', 'work')


def api(path, body=None, method=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method=method or ('POST' if body is not None else 'GET'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b'{}')


def say(text, chat=None):
    r = api('/api/ai/ask', {'chat': chat, 'text': text})
    for _ in range(200):
        j = api('/api/ai/job', {'job': r['job']})
        if j.get('done'):
            return r['chat'], j
        time.sleep(.2)
    raise SystemExit('the job did not finish')


def last_props(cid):
    return [p for m in api('/api/ai/chats/' + cid)['messages'] for p in m.get('proposals') or []]


try:
    for _ in range(40):
        try:
            api('/api/state'); break
        except Exception:
            time.sleep(.5)
    fake_base = f'http://127.0.0.1:{fake.server_address[1]}/v1'
    api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': fake_base, 'model': 'fake', 'key': 'k'}, 'PUT')
    say('Привет')
    check('агент выключен — инструментов файлов нет', 'shell' not in Fake.last_tools and 'Тебя зовут Frank. Ты — помощник внутри Rack Live' in Fake.last_system)

    api('/api/ai', {'agent': True, 'agentMode': 'ask'}, 'PUT')
    st = api('/api/state')['ai']
    check('агент включается, режим и машина видны', st['agent'] and st['agentMode'] == 'ask' and st['agentWhere'])
    plan['СОЗДАЙ'] = ('write_file', {'path': 'hello.txt', 'content': 'привет'})
    cid, _ = say('СОЗДАЙ файл')
    check('универсальный режим: инструкция и инструменты агента', 'shell' in Fake.last_tools and 'личный ИИ-агент' in Fake.last_system and work in Fake.last_system, Fake.last_system[:200])
    pr = last_props(cid)
    check('режим «спрашивать»: запись файла — карточка, файла ещё нет', pr and pr[-1]['action'] == 'agent' and pr[-1]['status'] == 'pending' and not os.path.exists(os.path.join(work, 'hello.txt')), pr)
    r = api('/api/ai/act', {'chat': cid, 'proposal': pr[-1]['id'], 'run': True})
    check('нажатие «Выполнить» создаёт файл', r['proposal']['status'] == 'done' and open(os.path.join(work, 'hello.txt'), encoding='utf-8').read() == 'привет', r['proposal'])
    plan['ПРОЧИТАЙ'] = ('read_file', {'path': 'hello.txt'})
    say('ПРОЧИТАЙ файл', cid)
    check('чтение в режиме «спрашивать» — сразу', results and 'привет' in results[-1], results[-1:])

    api('/api/ai', {'agentMode': 'edits'}, 'PUT')
    plan['ДОПИШИ'] = ('edit_file', {'path': 'hello.txt', 'old_string': 'привет', 'new_string': 'привет, мир'})
    say('ДОПИШИ мир', cid)
    check('режим «правки сам»: файл меняется сразу', open(os.path.join(work, 'hello.txt'), encoding='utf-8').read() == 'привет, мир')
    plan['ЗАПУСТИ'] = ('shell', {'command': 'echo done > out.txt'})
    say('ЗАПУСТИ команду', cid)
    pr = last_props(cid)
    check('режим «правки сам»: команда с изменением — карточка', pr[-1]['status'] == 'pending' and 'echo done' in pr[-1]['pre'] and not os.path.exists(os.path.join(work, 'out.txt')), pr[-1])

    api('/api/ai', {'agentMode': 'full'}, 'PUT')
    plan['ВЫПОЛНИ'] = ('shell', {'command': 'echo full > full.txt'})
    say('ВЫПОЛНИ сразу', cid)
    check('полный доступ: команда выполняется сразу', os.path.exists(os.path.join(work, 'full.txt')) and 'код выхода 0' in results[-1], results[-1:])
    plan['СЕКРЕТ'] = ('shell', {'command': 'cat /data/config.json'})
    say('СЕКРЕТ покажи', cid)
    check('полный доступ: данные Rack Live всё равно закрыты', 'данных Rack Live' in results[-1], results[-1:])
    plan['СНЕСИ'] = ('shell', {'command': 'rm -rf /'})
    say('СНЕСИ всё', cid)
    check('полный доступ: разрушительное всё равно запрещено', 'никогда' in results[-1], results[-1:])
    ev = api('/api/state')['events']
    check('изменения агента — в журнале событий', any(e.get('name') == 'Frank' and 'Команда: echo full' in e.get('text', '') for e in ev) and any('по кнопке' in e.get('text', '') for e in ev), [e.get('text') for e in ev[:5]])
    msgs = api('/api/ai/chats/' + cid)['messages']
    check('в ответе виден список того, что Frank выполнил', any(o.get('device') == 'Рабочая машина' for m in msgs for o in m.get('ops') or []))
finally:
    srv.terminate()
    try:
        srv.wait(10)
    except Exception:
        srv.kill()
    fake.shutdown()
    shutil.rmtree(data, ignore_errors=True)

print('\nВСЁ OK' if not bad else '\nОШИБКИ: ' + '; '.join(bad))
sys.exit(1 if bad else 0)
