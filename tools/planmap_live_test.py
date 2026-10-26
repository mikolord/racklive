"""«План» → «Живая карта (3D)»: the library is served compressed and cached for a year; the map opens in a real browser (headless Chrome with software WebGL),
the 3D layers and the labels of the houses are there. Skipped without Chrome. Run: python tools/planmap_live_test.py   (prints ВСЁ OK)
Chrome's debugging port is not used (some machines forbid it): the page is held open by one slow picture and its DOM is read at the end."""
import gzip, http.server, json, os, re, shutil, socketserver, struct, subprocess, sys, tempfile, threading, time, urllib.request, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSERS = [r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
browser = next((b for b in BROWSERS if os.path.exists(b)), shutil.which('chromium') or shutil.which('google-chrome'))
bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)[:200]))
    if not ok:
        bad.append(name)


APP, PROXY = 9977, 9976
data = tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(APP), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
app = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = 'http://127.0.0.1:%d' % APP


def png(w, h):
    rows = [b'\x00' + bytes((90, 130, 80)) * w for _ in range(h)]
    ch = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(b''.join(rows))) + ch(b'IEND', b'')


def call(path, method='GET', body=None, headers=None):
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b'{}')


class P(http.server.BaseHTTPRequestHandler):
    """in front of the app: it adds one slow picture to the page, so the browser waits (and the map has time to start) before it reads the page"""
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path
        if p.startswith('/slow.gif'):
            time.sleep(16)
            b, ct = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;', 'image/gif'
        else:
            try:
                with urllib.request.urlopen(urllib.request.Request(base + p, headers={'Accept-Encoding': 'identity'}), timeout=60) as r:
                    b, ct = r.read(), r.headers.get('Content-Type', 'application/octet-stream')
            except urllib.error.HTTPError as e:
                b, ct = e.read(), e.headers.get('Content-Type', 'text/plain')
            if p.split('?')[0] in ('/', '/index.html'):
                b = b.replace(b'</body>', b'<img src="/slow.gif" width="1" height="1" style="position:fixed;left:-9px"></body>')
        try:
            self.send_response(200); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        except (ConnectionError, OSError):                        # the browser has already left (it read the page and closed)
            pass


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


proxy = None
try:
    for _ in range(60):
        try:
            call('/api/state'); break
        except Exception:
            time.sleep(.5)
    # --- the library: compressed, cached for a year, only when asked for with its version
    ver = re.search(r"LIVE_VER = '([^']+)'", open(os.path.join(ROOT, 'web', 'src', '46_livemap.jsx'), encoding='utf-8').read()).group(1)
    req = urllib.request.Request(f'{base}/vendor/maplibre-gl.js?v={ver}', headers={'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=30) as r:
        body, h = r.read(), dict(r.headers)
    check('библиотека 3D лежит в vendor, версия в адресе совпадает с build.py', os.path.isfile(os.path.join(ROOT, 'web', 'vendor', 'maplibre-gl.js')) and f"MAPLIBRE = '{ver}'" in open(os.path.join(ROOT, 'build.py'), encoding='utf-8').read())
    check('отдаётся сжатой (около четверти размера)', h.get('Content-Encoding') == 'gzip' and len(body) < 0.4 * len(gzip.decompress(body)) and len(gzip.decompress(body)) > 500_000, (len(body), h.get('Content-Encoding')))
    check('и кэшируется браузером на год', 'max-age=31536000' in h.get('Cache-Control', '') and 'immutable' in h.get('Cache-Control', ''), h.get('Cache-Control'))
    with urllib.request.urlopen(urllib.request.Request(f'{base}/vendor/maplibre-gl.js?v={ver}', headers={'Accept-Encoding': 'gzip'}), timeout=30) as r2:
        check('повторный запрос — тот же сжатый файл (не пересжимается)', r2.read() == body)
    with urllib.request.urlopen(f'{base}/app.js', timeout=30) as r3:
        check('app.js по-прежнему без вечного кэша (обновляется с версией)', 'immutable' not in r3.headers.get('Cache-Control', ''))
    appjs = urllib.request.urlopen(f'{base}/app.js?x=1', timeout=30).read()
    check('карта подгружается лениво: библиотека в app.js не вшита', b'MapLibre GL JS' not in appjs and b'maplibregl.Map=' not in appjs and len(appjs) < 2_500_000, len(appjs))

    if not browser:
        print('нет Chrome — проверка карты в браузере пропущена')
    else:
        call('/api/plan/bg?x=-6000&y=-6000&w=12000&h=12000&op=0.9&name=Obzor&lat=55.7&lon=37.6&z=13&r=10000', 'POST', png(64, 64), {'Content-Type': 'image/png'})
        plan = call('/api/state')['plan']
        sq = lambda x, y, w, h: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        fl = lambda i: [{'id': 'f' + str(i), 'name': '1', 'walls': [], 'rooms': [], 'items': []}]
        plan['buildings'] = [{'id': 'bA', 'name': 'Главный дом', 'x': 900, 'y': 700, 'floors': fl(1) + fl(2), 'outline': sq(900, 700, 500, 300)},
                             {'id': 'bB', 'name': 'Гараж', 'x': 1700, 'y': 780, 'floors': fl(3), 'outline': sq(1700, 780, 380, 300)},
                             {'id': 'bC', 'name': 'Без контура', 'x': 100, 'y': 100, 'floors': fl(4)}]
        plan['links'] = [{'id': 'l1', 'from': 'bA', 'to': 'bB', 'label': 'x'}]
        call('/api/plan', 'PUT', json.dumps(plan).encode(), {'Content-Type': 'application/json'})
        proxy = S(('127.0.0.1', PROXY), P)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        gl = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
        out = subprocess.run([browser, '--headless=new', '--hide-scrollbars', '--window-size=1280,800', *gl, '--dump-dom', f'http://127.0.0.1:{PROXY}/?live=1#plan'],
                             capture_output=True, timeout=240, text=True, encoding='utf-8').stdout
        if 'live-root' not in out:
            print('браузер не открыл страницу (запрещено политикой или не запустился) — проверка карты пропущена')
        else:
            check('карта открывается по ?live=1: холст на весь экран и кнопка меню', 'live-map' in out and 'wm-fab' in out and 'page-full' in out)
            check('карта загрузилась (WebGL работает)', 'data-ready="1"' in out and 'live-msg err' not in out, re.findall(r'live-msg[^>]*>[^<]*', out)[:2])
            check('слои 3D и магистралей добавлены', 'data-layers="houses-3d,links"' in out, re.findall(r'data-layers="[^"]*"', out))
            labels = re.findall(r'class="live-label[^"]*"[^>]*>([^<]*)<', out)
            check('подписи есть у домов с контуром', sorted(labels) == ['Гараж', 'Главный дом'], labels)
            check('дом без контура на 3D-карте не рисуется (у него нет места на земле)', 'Без контура' not in labels)
finally:
    if proxy:
        proxy.shutdown()
    app.terminate()
    try:
        app.wait(timeout=10)
    except Exception:
        app.kill()
    shutil.rmtree(data, ignore_errors=True)

print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
sys.exit(1 if bad else 0)
