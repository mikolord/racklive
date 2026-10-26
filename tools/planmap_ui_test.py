"""«План»: the outline tool in a real browser (headless Chrome driven over its debugging port): tap the corners of a house, close the outline, drag a corner,
remove a corner, switch the picture on. Skipped when there is no Chrome. Run: python tools/planmap_ui_test.py   (prints ВСЁ OK)"""
import base64, json, os, shutil, socket, struct, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSERS = [r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
browser = next((b for b in BROWSERS if os.path.exists(b)), shutil.which('chromium') or shutil.which('google-chrome'))
if not browser:
    print('нет Chrome — проверка в браузере пропущена\n\nВСЁ OK')
    sys.exit(0)

bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)[:200]))
    if not ok:
        bad.append(name)


class WS:
    """the smallest WebSocket client that speaks to the Chrome debugging port (text frames only)"""

    def __init__(self, url):
        hp, path = url[5:].split('/', 1)
        host, port = hp.split(':')
        self.s = socket.create_connection((host, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(('GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (path, hp, key)).encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            buf += self.s.recv(4096)
        self.rest = buf.split(b'\r\n\r\n', 1)[1]
        self.n = 0

    def _read(self, k):
        while len(self.rest) < k:
            c = self.s.recv(65536)
            if not c:
                raise EOFError('соединение закрыто')
            self.rest += c
        out, self.rest = self.rest[:k], self.rest[k:]
        return out

    def send(self, obj):
        d = json.dumps(obj).encode()
        mask = os.urandom(4)
        h = bytes([0x81])
        if len(d) < 126:
            h += bytes([0x80 | len(d)])
        elif len(d) < 65536:
            h += bytes([0x80 | 126]) + struct.pack('>H', len(d))
        else:
            h += bytes([0x80 | 127]) + struct.pack('>Q', len(d))
        self.s.sendall(h + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(d)))

    def recv(self):
        msg = b''
        while True:
            b0, b1 = self._read(2)
            ln = b1 & 0x7f
            if ln == 126:
                ln = struct.unpack('>H', self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack('>Q', self._read(8))[0]
            payload = self._read(ln)
            op = b0 & 0x0f
            if op == 8:
                raise EOFError('закрыто')
            if op in (1, 0):
                msg += payload
                if b0 & 0x80:
                    return json.loads(msg)

    def call(self, method, **params):
        self.n += 1
        i = self.n
        self.send({'id': i, 'method': method, 'params': params})
        while True:
            m = self.recv()
            if m.get('id') == i:
                if 'error' in m:
                    raise RuntimeError(m['error'])
                return m.get('result', {})


port, cdp = 18996, 9334
data, prof = tempfile.mkdtemp(), tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(port), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = 'http://127.0.0.1:%d' % port
ch = None


def api(path):
    with urllib.request.urlopen(base + path, timeout=20) as r:
        return json.loads(r.read())


try:
    for _ in range(60):
        try:
            api('/api/state'); break
        except Exception:
            time.sleep(.5)
    ch = subprocess.Popen([browser, '--headless=new', '--disable-gpu', '--no-first-run', f'--remote-debugging-port={cdp}', f'--user-data-dir={prof}',
                           '--window-size=1280,1000', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tabs = None
    for _ in range(60):
        try:
            tabs = json.loads(urllib.request.urlopen(f'http://127.0.0.1:{cdp}/json/list', timeout=3).read()); break
        except Exception:
            time.sleep(.5)
    if not tabs:                                             # some machines forbid the debugging port by policy («disallowed by the system admin»): not worked around
        print('браузер не открыл порт отладки (запрещён политикой или не запустился) — проверка в браузере пропущена')
        print('\nВСЁ OK')
        sys.exit(0)
    ws = WS(next(t for t in tabs if t['type'] == 'page')['webSocketDebuggerUrl'])
    ev = lambda js: ws.call('Runtime.evaluate', expression=js, returnByValue=True, awaitPromise=True).get('result', {}).get('value')
    ws.call('Page.enable')
    ws.call('Page.navigate', url=base + '/?mode=edit#plan')
    for _ in range(60):
        if ev("!!document.querySelector('.plan-canvas')"):
            break
        time.sleep(.5)
    time.sleep(1)
    ev("window.prompt = () => 'Новый дом'; window.confirm = () => true; true")
    mouse = lambda t, x, y, **k: ws.call('Input.dispatchMouseEvent', type=t, x=x, y=y, button='left', clickCount=1, **k)

    def click(x, y):
        mouse('mouseMoved', x, y); mouse('mousePressed', x, y); mouse('mouseReleased', x, y); time.sleep(.25)

    def drag(x0, y0, x1, y1):
        mouse('mouseMoved', x0, y0); mouse('mousePressed', x0, y0, buttons=1)
        for i in range(1, 9):
            mouse('mouseMoved', x0 + (x1 - x0) * i / 8, y0 + (y1 - y0) * i / 8, buttons=1)
        mouse('mouseReleased', x1, y1); time.sleep(.5)

    rect = lambda sel: ev("(()=>{const e=document.querySelector(%s);if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()" % json.dumps(sel))
    btn = lambda text: ev("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim().startsWith(%s));if(!b)return null;const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()" % json.dumps(text))
    count = lambda sel: ev("document.querySelectorAll(%s).length" % json.dumps(sel))

    check('в режиме правки есть инструмент «Обвести дом»', bool(btn('Обвести дом')))
    check('и кнопка фона', bool(btn('Фон')))
    n0 = len(api('/api/state')['plan']['buildings'])
    # zoom out a few times: the corners are placed on an empty part of the canvas
    for _ in range(3):
        z = ev("(()=>{const b=[...document.querySelectorAll('.zoom-btns button')].find(x=>x.textContent.trim()==='−');const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        click(z['x'], z['y'])
    c = rect('.plan-canvas')
    p = btn('Обвести дом'); click(p['x'], p['y'])
    pts = [(c['x'] + 70, c['y'] + 70), (c['x'] + 200, c['y'] + 70), (c['x'] + 200, c['y'] + 160), (c['x'] + 70, c['y'] + 160)]
    for x, y in pts:
        click(x, y)
    check('углы ставятся (черновик виден)', count('.plan-draft .plan-vtx') == 4, count('.plan-draft .plan-vtx'))
    click(*pts[0])                                           # tap the first corner: closes the outline
    time.sleep(1.2)
    b1 = api('/api/state')['plan']['buildings']
    new = [b for b in b1 if b.get('outline')]
    check('контур замкнулся, дом создан', len(b1) == n0 + 1 and len(new) == 1 and new[0]['name'] == 'Новый дом' and len(new[0]['outline']) == 4, [b.get('name') for b in b1])
    o = new[0]['outline'] if new else []
    wid = (max(q[0] for q in o) - min(q[0] for q in o)) if o else 0
    check('углы привязаны к метру (кратны 10)', bool(o) and all(q[0] % 10 == 0 and q[1] % 10 == 0 for q in o))
    check('контур нарисован, у дома есть этаж', count('.plan-outlined') == 1 and bool(new) and len(new[0]['floors']) == 1)
    check('после замыкания включён обычный режим, у контура видны углы', count('.plan-vtxs .plan-vtx:not(.ghost)') == 4 and count('.plan-vtxs .plan-vtx.ghost') == 4)
    # drag a corner
    v = ev("(()=>{const e=document.querySelectorAll('.plan-vtxs .plan-vtx:not(.ghost)')[2];const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    drag(v['x'], v['y'], v['x'] + 60, v['y'] + 40)
    o2 = [b for b in api('/api/state')['plan']['buildings'] if b.get('outline')][0]['outline']
    check('угол можно перетащить, остальные на месте', o2[2] != o[2] and o2[0] == o[0] and o2[1] == o[1] and o2[3] == o[3], (o, o2))
    # a corner in the middle of a side
    m = ev("(()=>{const e=document.querySelectorAll('.plan-vtxs .plan-vtx.ghost')[0];const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    mouse('mouseMoved', m['x'], m['y']); mouse('mousePressed', m['x'], m['y']); mouse('mouseReleased', m['x'], m['y']); time.sleep(.8)
    o3 = [b for b in api('/api/state')['plan']['buildings'] if b.get('outline')][0]['outline']
    check('«+» на стороне добавляет угол', len(o3) == 5, len(o3))
    rm = btn('Убрать угол')
    check('выбранный угол можно убрать кнопкой', bool(rm))
    if rm:
        click(rm['x'], rm['y']); time.sleep(.8)
        o4 = [b for b in api('/api/state')['plan']['buildings'] if b.get('outline')][0]['outline']
        check('угол убран', len(o4) == 4, len(o4))
    # the whole house is dragged
    cc = ev("(()=>{const e=document.querySelector('.plan-outlined .plan-outline');const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    before = [b for b in api('/api/state')['plan']['buildings'] if b.get('outline')][0]['outline']
    drag(cc['x'], cc['y'], cc['x'] + 80, cc['y'] + 30)
    after = [b for b in api('/api/state')['plan']['buildings'] if b.get('outline')][0]['outline']
    dx = after[0][0] - before[0][0]
    check('дом целиком тащится, форма сохраняется', dx > 0 and all(a[0] - b[0] == dx and a[1] - b[1] == after[0][1] - before[0][1] for a, b in zip(after, before)), (before, after))
    # 2 corners are not a house; Esc-like reset
    p = btn('Обвести дом'); click(p['x'], p['y']); click(c['x'] + 400, c['y'] + 70); click(c['x'] + 500, c['y'] + 70)
    check('два угла — ещё не дом: «Готово» не появляется', count('.plan-draft .plan-vtx') == 2 and not btn('Готово'))
    rs = btn('Сбросить'); click(rs['x'], rs['y'])
    check('«Сбросить» очищает черновик', count('.plan-draft .plan-vtx') == 0 and len([b for b in api('/api/state')['plan']['buildings'] if b.get('outline')]) == 1)
    errs = ev("window.__errs || 0")
    check('в консоли страницы нет ошибок скриптов', not errs)
finally:
    for pr in (ch, srv):
        if pr:
            pr.terminate()
            try:
                pr.wait(timeout=10)
            except Exception:
                pr.kill()
    shutil.rmtree(data, ignore_errors=True)
    shutil.rmtree(prof, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
sys.exit(1 if bad else 0)
