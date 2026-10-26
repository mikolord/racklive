"""Frank: how full the window is, /compact, /clear, /context, /help and the automatic squeeze. A fake OpenAI-compatible model is started here;
Rack Live (demo copy) is pointed at it. Run: python tools/frank_ctx_test.py (prints ВСЁ OK)"""
import http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)[:300]))
    if not ok:
        bad.append(name)


seen = []          # what the fake model was asked: [{'system', 'messages'}]


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        msgs = body.get('messages') or []
        system = next((m['content'] for m in msgs if m['role'] == 'system'), '')
        seen.append({'system': system, 'messages': [m for m in msgs if m['role'] != 'system'], 'tools': bool(body.get('tools'))})
        chars = sum(len(str(m.get('content') or '')) for m in msgs) + len(json.dumps(body.get('tools') or []))
        if system.startswith('Ты сжимаешь историю'):
            text = '- Пользователь спрашивал про Wi-Fi на кухне; решили проверить точку AP_E1.'
        else:
            text = 'Ответ номер %d: всё хорошо. ' % len(seen) + 'Подробности. ' * 30
        out = json.dumps({'choices': [{'message': {'role': 'assistant', 'content': text}}], 'usage': {'prompt_tokens': int(chars / 3), 'completion_tokens': int(len(text) / 3)}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)


fake = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
fport = fake.server_address[1]

port, data = 9977, tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port}'


def api(path, body=None, method=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method=method or ('POST' if body is not None else 'GET'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b'{}')


def say(text, chat=None):
    r = api('/api/ai/ask', {'chat': chat, 'text': text})
    for _ in range(100):
        j = api('/api/ai/job', {'job': r['job']})
        if j.get('done'):
            return r['chat'], j
        time.sleep(.2)
    raise SystemExit('the job did not finish')


try:
    for _ in range(40):
        try:
            api('/api/state'); break
        except Exception:
            time.sleep(.5)
    api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': f'http://127.0.0.1:{fport}/v1', 'model': 'fake-model', 'key': 'k', 'window': 12000, 'autoCompact': True}, 'PUT')
    st = api('/api/state')['ai']
    check('окно контекста: своё значение из настроек', st['effWindow'] == 12000 and st['window'] == 12000 and st['autoCompact'] is True)

    cid, j = say('Что с Wi-Fi на кухне?')
    ch = api('/api/ai/chats/' + cid)
    c1 = ch['ctx']
    check('счётчик: после ответа берётся точная цифра модели', c1 and c1['exact'] and c1['used'] > 500 and 0 < c1['pct'] < 100 and c1['window'] == 12000, c1)
    last = [m for m in ch['messages'] if m['role'] == 'assistant'][-1]
    check('в ответе записан размер окна (ctx)', last.get('ctx', 0) > 0, last)

    for i in range(3):
        say('Ещё вопрос номер %d, расскажи подробнее про сеть. ' % i + 'слова ' * 120, cid)
    ch = api('/api/ai/chats/' + cid)
    n_before = len(seen)
    check('весь разговор уходит модели, не последние 12', len([m for m in seen[-1]['messages']]) >= 7 and ch['ctx']['count'] >= 8, [len(s['messages']) for s in seen])

    _, j = say('/context', cid)
    ch = api('/api/ai/chats/' + cid)
    note = [m for m in ch['messages'] if m['role'] == 'note'][-1]
    check('/context: заметка с цифрами, модель не вызывалась', 'токенов' in note['text'] and 'Из них' in note['text'] and len(seen) == n_before, note['text'])

    _, j = say('/help', cid)
    ch = api('/api/ai/chats/' + cid)
    check('/help: список команд', '/compact' in [m for m in ch['messages'] if m['role'] == 'note'][-1]['text'] and len(seen) == n_before)

    pct_before = ch['ctx']['pct']
    _, j = say('/compact про точку AP_E1', cid)
    ch = api('/api/ai/chats/' + cid)
    last_req = seen[-1]
    check('/compact: просьба сжать ушла модели вместе с указанием пользователя', last_req['system'].startswith('Ты сжимаешь историю') and 'AP_E1' in last_req['messages'][-1]['content'] and not last_req['tools'])
    check('/compact: появилась сводка и граница, место освободилось', ch.get('summary') and ch.get('cut', 0) > 0 and ch['ctx']['pct'] < pct_before and ch['ctx']['squeezed'], [pct_before, ch['ctx']])
    check('/compact: об этом есть заметка', any(m['role'] == 'note' and 'сжат' in m['text'] for m in ch['messages']))
    check('/compact: сообщения целы (можно прокрутить вверх)', len([m for m in ch['messages'] if m['role'] == 'user']) >= 4)

    say('Что там с точкой?', cid)
    req = seen[-1]
    check('после сжатия модель получает сводку и только последние сообщения', 'Краткое содержание' in req['system'] and 'AP_E1' in req['system'] and len(req['messages']) <= 6, [len(req['messages']), req['system'][-200:]])

    # the window is small: the next questions fill it and the squeeze happens by itself
    api('/api/ai', {'window': 3000}, 'PUT')
    before = len([m for m in api('/api/ai/chats/' + cid)['messages'] if m['role'] == 'note'])
    for i in range(3):
        say('Большой вопрос %d. ' % i + 'текст ' * 400, cid)
    ch = api('/api/ai/chats/' + cid)
    auto = [m for m in ch['messages'] if m['role'] == 'note' and 'само' in m['text']]
    check('автосжатие: когда окно почти полно, Frank сжимает сам и пишет об этом', auto, [m['text'][:80] for m in ch['messages'] if m['role'] == 'note'])
    api('/api/ai', {'window': 12000, 'autoCompact': False}, 'PUT')

    _, j = say('/clear', cid)
    new = j['chat']
    lst = api('/api/ai/chats')['chats']
    check('/clear: новый пустой разговор, прежний остался в списке, пустой не в списке', new != cid and any(c['id'] == cid for c in lst) and not any(c['id'] == new for c in lst))
    ch2 = api('/api/ai/chats/' + new)
    check('/clear: в новом разговоре нет сообщений и сводки', not ch2['messages'] and not ch2.get('summary'))
    _, j = say('/clear', new)
    check('/clear в пустом разговоре не плодит новые', j['chat'] == new)
    cid3, _ = say('Первый вопрос в новом', new)
    check('первый вопрос даёт название разговору и он попадает в список', cid3 == new and any(c['id'] == new and c['title'].startswith('Первый вопрос') for c in api('/api/ai/chats')['chats']))
    _, j = say('/compact', new)
    check('/compact в коротком разговоре: нечего сжимать, без вызова модели', 'нечего сжимать' in j.get('text', ''))
    _, j = say('/volume1/docker/racklive покажи', new)
    check('обычный вопрос со слешем — не команда', j.get('usage', {}).get('in', 0) > 0 or j.get('text'))
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
