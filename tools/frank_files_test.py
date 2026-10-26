"""Frank: photos and files in a question, a model that takes no pictures, the memory FRANK.md and the «remember» tool.
A fake OpenAI-compatible model is started here; Rack Live (demo copy) is pointed at it. Run: python tools/frank_files_test.py (prints ВСЁ OK)"""
import http.server, json, os, shutil, struct, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)[:300]))
    if not ok:
        bad.append(name)


def png(w=4, h=4):
    raw = b''.join(b'\x00' + b'\xff\x00\x00' * w for _ in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


seen = []
mode = {'vision': True}


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        msgs = body.get('messages') or []
        seen.append(body)
        has_pic = any(isinstance(m.get('content'), list) and any(p.get('type') == 'image_url' for p in m['content']) for m in msgs)
        if has_pic and not mode['vision']:
            return self.reply(400, {'error': {'message': 'image input is not supported by this model'}})
        last = msgs[-1]
        text = last['content'] if isinstance(last.get('content'), str) else ' '.join(p.get('text', '') for p in last.get('content') or [] if p.get('type') == 'text')
        usage = {'prompt_tokens': 900, 'completion_tokens': 20}
        if last['role'] == 'user' and 'ЗАПОМНИ' in text.upper() and 'tools' in body:
            req = 'запомни, что я люблю короткие ответы' if 'люблю короткие' in text else 'что-то другое'
            call = {'id': 'call1', 'type': 'function', 'function': {'name': 'remember', 'arguments': json.dumps({'text': 'Пользователь любит короткие ответы', 'request': req}, ensure_ascii=False)}}
            return self.reply(200, {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [call]}}], 'usage': usage})
        return self.reply(200, {'choices': [{'message': {'role': 'assistant', 'content': 'Готово, посмотрел.'}}], 'usage': usage})


fake = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
port, data = 9976, tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{port}'


def api(path, body=None, method=None, raw=None, headers=None):
    req = urllib.request.Request(base + path, data=raw if raw is not None else None if body is None else json.dumps(body).encode(),
                                 method=method or ('POST' if body is not None or raw is not None else 'GET'), headers={'Content-Type': 'application/json', **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
        return json.loads(b or b'{}') if 'json' in (r.headers.get('Content-Type') or '') else (b, dict(r.headers))


def upload(name, blob):
    return api('/api/ai/files', raw=blob, headers={'X-File-Name': urllib.parse.quote(name), 'Content-Type': 'application/octet-stream'})


def say(text, chat=None, files=None):
    r = api('/api/ai/ask', {'chat': chat, 'text': text, 'files': files or []})
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
    api('/api/ai', {'enabled': True, 'preset': 'custom', 'base': f'http://127.0.0.1:{fake.server_address[1]}/v1', 'model': 'fake', 'key': 'k', 'window': 128000}, 'PUT')

    # ── files ──
    im = upload('кухня.png', png())
    tx = upload('router.conf', 'interface Bridge0\n description "Домашняя сеть"\n'.encode())
    bn = upload('dump.bin', bytes(range(256)) * 4)
    check('загрузка: фото, текст и двоичный файл узнаются по содержимому', im['file']['kind'] == 'image' and tx['file']['kind'] == 'text' and bn['file']['kind'] == 'other', [im, tx, bn])
    b, h = api('/api/ai/files/' + tx['file']['id'])
    check('файл отдаётся как скачивание, не как страница', b.startswith(b'interface') and 'attachment' in h.get('Content-Disposition', '') and 'sandbox' in h.get('Content-Security-Policy', ''))

    cid, j = say('Что на фото и в конфиге?', files=[im['file']['id'], tx['file']['id'], bn['file']['id']])
    req = seen[-1]
    um = [m for m in req['messages'] if m['role'] == 'user'][-1]
    parts = um['content'] if isinstance(um['content'], list) else []
    txt = ' '.join(p.get('text', '') for p in parts if p.get('type') == 'text')
    check('фото ушло модели картинкой', any(p.get('type') == 'image_url' and p['image_url']['url'].startswith('data:image/png;base64,') for p in parts), um)
    check('текст файла — прямо в вопросе', 'Bridge0' in txt and '[Файл «router.conf»]' in txt, txt[:300])
    check('про двоичный файл — только имя', 'dump.bin' in txt and 'открыть его ты пока не можешь' in txt)
    ch = api('/api/ai/chats/' + cid)
    um2 = [m for m in ch['messages'] if m['role'] == 'user'][-1]
    check('в разговоре у вопроса записаны вложения', len(um2.get('files') or []) == 3 and ch['ctx']['used'] > 0)

    _, j = say('Только фото, без текста?', cid, files=[upload('a.png', png())['file']['id']])
    _, j = say('', cid, files=[upload('b.png', png())['file']['id']])
    ch = api('/api/ai/chats/' + cid)
    check('вопрос без текста с фото — «Посмотри фото.»', [m for m in ch['messages'] if m['role'] == 'user'][-1]['text'] == 'Посмотри фото.')
    pics = sum(1 for m in seen[-1]['messages'] if isinstance(m.get('content'), list) and any(p.get('type') == 'image_url' for p in m['content']))
    check('старые фото не пересылаются каждый раз (только два последних вопроса с фото)', pics == 2, pics)

    mode['vision'] = False
    _, j = say('А теперь?', cid, files=[upload('c.png', png())['file']['id']])
    ch = api('/api/ai/chats/' + cid)
    last = [m for m in ch['messages'] if m['role'] == 'assistant'][-1]
    check('модель без картинок: вопрос повторён без фото, ответ есть и честно сказано', not last.get('err') and 'не принимает фото' in last['text'], last)
    mode['vision'] = True

    # ── memory ──
    api('/api/ai/memory', {'text': '- Роутер Keenetic стоит в коридоре'}, 'PUT')
    check('память читается', api('/api/ai/memory')['text'].startswith('- Роутер'))
    say('Где роутер?', cid)
    sysm = seen[-1]['messages'][0]['content']
    check('память попадает в инструкцию Frank', 'FRANK.md' in sysm and 'в коридоре' in sysm)
    cid2, _ = say('Запомни, что я люблю короткие ответы')
    check('«запомни» с дословной просьбой — записано сразу', 'короткие ответы' in api('/api/ai/memory')['text'])
    api('/api/ai/memory', {'text': ''}, 'PUT')
    _, _ = say('ЗАПОМНИ вот это', cid2)
    ch = api('/api/ai/chats/' + cid2)
    props = [p for m in ch['messages'] for p in m.get('proposals') or [] if p.get('action') == 'memory']
    check('без дословной просьбы — карточка «Запомнить», в память ничего не записано', props and props[-1]['status'] == 'pending' and not api('/api/ai/memory')['text'].strip(), props)
    r = api('/api/ai/act', {'chat': cid2, 'proposal': props[-1]['id'], 'run': True})
    check('нажатие «Выполнить» записывает в память', r['proposal']['status'] == 'done' and 'короткие ответы' in api('/api/ai/memory')['text'], r['proposal'])
    _, j = say('/memory отвечай по-русски', cid2)
    check('/memory текст — дописывает', 'по-русски' in api('/api/ai/memory')['text'] and j['text'].startswith('Запомнил'))
    _, j = say('/memory', cid2)
    check('/memory — показывает память', 'FRANK.md' in j['text'] and 'по-русски' in j['text'])
    try:
        api('/api/ai/memory', {'text': 'x' * 30000}, 'PUT')
        check('слишком длинная память не принимается', False)
    except urllib.error.HTTPError as e:
        check('слишком длинная память не принимается', e.code == 400)

    # ── deleting a chat removes its files ──
    api('/api/ai/chats/' + cid, None, 'DELETE')
    try:
        api('/api/ai/files/' + im['file']['id'])
        check('удаление разговора удаляет его файлы', False)
    except urllib.error.HTTPError as e:
        check('удаление разговора удаляет его файлы', e.code == 404)
    try:
        api('/api/ai/ask', {'chat': None, 'text': 'x', 'files': ['0123456789abcdef']})
        check('чужой или удалённый id вложения — ошибка', False)
    except urllib.error.HTTPError as e:
        check('чужой или удалённый id вложения — ошибка', e.code == 400)
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
