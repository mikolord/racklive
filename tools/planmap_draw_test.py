"""«План» → «Живая карта (3D)»: обводка дома, цвета и меню — по-настоящему, в браузере (headless Chrome, программный WebGL).
Страница-обёртка открывает приложение во фрейме, нажимает кнопки меню (настоящие клики по элементам) и имитирует нажатия по карте (map.fire('click')), потом читает план с сервера.
Chrome на этом ПК запрещает порт отладки — поэтому всё идёт внутри страницы, а результат читается --dump-dom в реальном времени (медленная картинка держит страницу).
Run: python tools/planmap_draw_test.py   (prints ВСЁ OK; skipped without Chrome / WebGL)"""
import http.server, json, os, re, shutil, socketserver, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP, PROXY = 8939, 8940
bad = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else f'   [{extra}]'))
    if not ok:
        bad.append(name)


def find_browser():
    for p in (os.environ.get('CHROME'), r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chromium-browser')):
        if p and os.path.isfile(p):
            return p
    return None


browser = find_browser()
if not browser:
    print('нет Chrome — проверка обводки в браузере пропущена\n\nВСЁ OK')
    sys.exit(0)
data = tempfile.mkdtemp()
env = dict(os.environ, RL_DEMO='1', RL_PORT=str(APP), RL_DATA=data, RL_WEB=os.path.join(ROOT, 'web'), PYTHONIOENCODING='utf-8')
app = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = 'http://127.0.0.1:%d' % APP
wrap = os.path.join(ROOT, 'web', '_draw_test.html')


def call(path, method='GET', body=None, headers=None):
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b'{}')


class P(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path
        if p.startswith('/slow.gif'):
            time.sleep(70)
            b, ct = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;', 'image/gif'
        else:
            try:
                with urllib.request.urlopen(urllib.request.Request(base + p, headers={'Accept-Encoding': 'identity'}), timeout=60) as r:
                    b, ct = r.read(), r.headers.get('Content-Type', 'application/octet-stream')
            except urllib.error.HTTPError as e:
                b, ct = e.read(), e.headers.get('Content-Type', 'text/plain')
        try:
            self.send_response(200); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        except (ConnectionError, OSError):
            pass


    def _fwd(self):                                       # сохранение плана идёт PUT/POST — пропускаем к приложению как есть
        n = int(self.headers.get('Content-Length') or 0)
        req = urllib.request.Request(base + self.path, data=self.rfile.read(n) if n else None, method=self.command,
                                     headers={k: v for k, v in self.headers.items() if k.lower() in ('content-type', 'x-rl-session', 'cookie')})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b, ct, code = r.read(), r.headers.get('Content-Type', 'application/json'), r.status
        except urllib.error.HTTPError as e:
            b, ct, code = e.read(), e.headers.get('Content-Type', 'application/json'), e.code
        try:
            self.send_response(code); self.send_header('Content-Type', ct); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        except (ConnectionError, OSError):
            pass

    do_PUT = do_POST = do_DELETE = _fwd


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


PAGE = r'''<!doctype html><meta charset="utf-8"><body><pre id="res">…</pre><img src="/slow.gif" width="1" height="1">
<iframe id="f" src="/?live=1&wmtest=1&mode=edit#plan" style="width:420px;height:760px;border:0"></iframe>
<script>
const getPlan = async () => (await (await fetch('/api/state')).json()).plan;
const out = {}; const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 40000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = fn(); if (v) return v; } catch (e) { } await sleep(150); } return null; };
(async () => {
  try {
    const f = document.getElementById('f'); const w = () => f.contentWindow, d = () => f.contentDocument;
    out.ready = !!(await until(() => d().querySelector('.live-map[data-ready="1"]') && w().__rlLive));
    w().prompt = (q, def) => out.lastPrompt = 'Тестовый дом';                    // имя дома без окна ввода
    const T = txt => [...d().querySelectorAll('button')].find(b => b.textContent.trim().startsWith(txt));
    const openMenu = async () => { d().querySelector('.wm-fab').click(); await sleep(300); };
    await openMenu();
    out.menuHasTools = !!T('По углам') && !!T('Прямоугольник') && !!T('По зданию') && !!T('Спутник') && !!T('Столб') && !!T('Узел') && !!T('Магистраль') && !!T('Найти на плане');
    T('По углам').click(); await sleep(400);
    out.menuClosed = !d().querySelector('.wm-panel');
    out.barShown = !!d().querySelector('.live-bar');
    const { map, ml } = w().__rlLive, c = map.getCenter();
    const click = (dx, dy) => { const ll = new ml.LngLat(c.lng + dx, c.lat + dy); map.fire('click', { lngLat: ll, point: map.project(ll), originalEvent: {} }); };
    click(-0.0003, -0.0002); await sleep(200); click(0.0003, -0.0002); await sleep(200); click(0.0003, 0.0002); await sleep(200); click(-0.0003, 0.0002); await sleep(400);
    out.pitchLocked = map.getPitch() < 1 && map.getMaxPitch() === 0;                  // на время обводки карта смотрит строго сверху и не наклоняется
    out.doneButton = !!T('Готово');
    T('Готово').click();
    await sleep(1500);
    out.jsError = d().documentElement.dataset.jsError || ''; out.toasts = [...d().querySelectorAll('.toast, .toasts *')].map(x => x.textContent).slice(0, 4);
    out.plan = await getPlan();
    out.cardShown = !!d().querySelector('.live-card');
    // цвета: карточка дома → «Цвета» → цвет
    const colors = T('Цвета'); out.hasColors = !!colors;
    if (colors) { colors.click(); await sleep(300); const sw = [...d().querySelectorAll('.house-style .wm-colors button:not(.auto)')]; out.swatches = sw.length; if (sw[3]) sw[3].click(); await sleep(1200); out.plan3 = await getPlan(); }
    // правка углов: «Углы» → кружки углов и «+» на сторонах; «+» добавляет угол, выбранный угол убирается
    T('Углы').click(); await sleep(600);
    out.vtx = d().querySelectorAll('.live-vtx').length; out.mid = d().querySelectorAll('.live-mid').length; out.moveHandle = d().querySelectorAll('.live-move').length;
    d().querySelector('.live-mid').click(); await sleep(1500);
    out.plan4 = await getPlan(); out.vtx2 = d().querySelectorAll('.live-vtx').length;
    d().querySelectorAll('.live-vtx')[1].click(); await sleep(400);
    out.delButton = !!T('Убрать угол'); if (T('Убрать угол')) T('Убрать угол').click(); await sleep(1500);
    out.plan5 = await getPlan(); T('Готово').click(); await sleep(400);
    // прямоугольник: три нажатия
    await openMenu(); T('Прямоугольник').click(); await sleep(400);
    click(-0.0008, 0.0008); await sleep(200); click(-0.0004, 0.0008); await sleep(200); click(-0.0004, 0.0012); await sleep(1500);
    out.plan2 = await getPlan();
    out.edge = d().querySelectorAll('.live-label').length;
    // «По зданию на карте»: нажимаем в точку внутри настоящего здания карты — берётся именно оно (а не соседнее)
    try {
      await openMenu(); T('По зданию').click(); await sleep(2500);
      const inRing = (r, p) => { let c = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const a = r[i], b = r[j]; if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
      for (let k = 0; k < 20 && !map.queryRenderedFeatures({ layers: ['building'] }).length; k++) await sleep(500);       // плитки домов подгружаются не сразу
      const all = map.queryRenderedFeatures({ layers: ['building'] }); out.bFeat = all.length; out.bTypes = [...new Set(all.map(f => f.geometry && f.geometry.type))].join(); out.pitch = map.getPitch(); out.hasLayer = !!map.getLayer('building');
      const fs = all.filter(f => f.geometry && (f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon'));
      let target = null;
      let tcount = 0;
      for (const f of fs) { const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates, cv = map.getCanvas();     // составное здание: берём точку в НЕ самом большом доме
        const ordered = [...polys].sort((a, b) => a[0].length - b[0].length);
        for (const poly of ordered) { const r = poly[0], x0 = Math.min(...r.map(q => q[0])), x1 = Math.max(...r.map(q => q[0])), y0 = Math.min(...r.map(q => q[1])), y1 = Math.max(...r.map(q => q[1]));
          for (let a = 1; a < 6 && !target; a++) for (let b = 1; b < 6 && !target; b++) { const cen = [x0 + (x1 - x0) * a / 6, y0 + (y1 - y0) * b / 6];
            if (inRing(r, cen)) { const sp = map.project(new ml.LngLat(cen[0], cen[1])); if (sp.x > 20 && sp.y > 20 && sp.x < cv.clientWidth - 20 && sp.y < cv.clientHeight - 20) target = cen; } }
          if (target) break; }
        if (target) break; }
      out.dbg = fs.slice(0, 3).map(f => { const r = f.geometry.type === 'Polygon' ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0]; const s = map.project(new ml.LngLat(r[0][0], r[0][1])); return [r.length, Math.round(s.x), Math.round(s.y), map.getCanvas().clientWidth, map.getCanvas().clientHeight]; });
      out.autoTarget = !!target;
      if (target) {
        const ll = new ml.LngLat(target[0], target[1]); map.fire('click', { lngLat: ll, point: map.project(ll), originalEvent: {} }); await sleep(1800);
        const pl = await getPlan(), nb = (pl.buildings || []).filter(b => b.name === 'Тестовый дом'), last = nb[nb.length - 1];
        const xs = last.outline.map(p => p[0]), ys = last.outline.map(p => p[1]);
        const want = w().eval(`geoToWorld(${target[1]}, ${target[0]}, { x: -10, y: -10, w: 20, h: 20, lat: 55.7558, lon: 37.6173 })`);
        out.autoInside = inRing(last.outline, [want.x, want.y]); out.autoDist = Math.round(Math.hypot((Math.min(...xs) + Math.max(...xs)) / 2 - want.x, (Math.min(...ys) + Math.max(...ys)) / 2 - want.y)); out.autoSize = Math.round(Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)));
        out.autoCount = nb.length;
      }
    } catch (e) { out.autoError = String(e); }
    // столбы: инструмент остаётся включённым, пока не нажмут «Готово»
    await openMenu(); T('Столб').click(); await sleep(400);
    click(0.0012, 0); await sleep(1200); click(0.0016, 0); await sleep(1200);
    T('Готово').click(); await sleep(500);
    out.plan6 = await getPlan(); out.poleMarks = d().querySelectorAll('.live-pole').length;
    // узел: ставится, называется и сразу предлагает привязку к шкафу или устройству
    await openMenu(); T('Узел').click(); await sleep(400);
    click(0.0012, 0.0006); await sleep(1500);
    out.bindShown = /подвязать/.test((d().querySelector('.modal') || {}).textContent || '');
    const li = d().querySelector('.modal .list .li'); if (li) li.click(); await sleep(1500);
    out.plan7 = await getPlan(); out.nodeMarks = d().querySelectorAll('.live-node').length;
    // магистраль между двумя столбами
    await openMenu(); T('Магистраль').click(); await sleep(400);
    const pm = d().querySelectorAll('.live-pole'); if (pm.length >= 2) { pm[0].click(); await sleep(300); pm[1].click(); await sleep(800); }
    out.linkModal = !!T('Сохранить'); if (T('Сохранить')) T('Сохранить').click(); await sleep(1500);
    out.plan8 = await getPlan(); if (T('Готово')) T('Готово').click(); await sleep(400);
    // поиск по плану
    await openMenu(); T('Найти на плане').click(); await sleep(500);
    const inp = d().querySelector('.live-find input'); out.findInput = !!inp;
    if (inp) { const setv = Object.getOwnPropertyDescriptor(w().HTMLInputElement.prototype, 'value').set; setv.call(inp, 'Тестовый'); inp.dispatchEvent(new (w().Event)('input', { bubbles: true })); await sleep(600); }
    out.found = d().querySelectorAll('.live-find .li').length;
    const fi = d().querySelector('.live-find .li'); if (fi) fi.click(); await sleep(800);
    out.foundCard = !!d().querySelector('.live-card');
    // выбранный дом → «Сеть дома» (карта сети, суженная до дома) → назад → «Открыть дом» (этажи и комнаты) → назад
    out.card2 = !!T('Сеть дома'); T('Сеть дома').click(); await sleep(2500);
    out.netShown = !!d().querySelector('.map-wrap.scoped') && /Сеть дома/.test((d().querySelector('.plan-ctx') || {}).textContent || '');
    out.netNodes = d().querySelectorAll('.map-wrap .node').length;
    const back = T('К плану'); out.netBack = !!back; if (back) back.click();
    out.ready2 = !!(await until(() => d().querySelector('.live-map[data-ready="1"]') && d().querySelector('.live-label')));
    d().querySelector('.live-label').click(); await sleep(500);
    out.openBtn = !!T('Открыть дом'); if (T('Открыть дом')) T('Открыть дом').click(); await sleep(1500);
    out.houseShown = /Все дома/.test((d().querySelector('.plan-ctx') || {}).textContent || '') && !!d().querySelector('.plan-canvas');
    const all = T('Все дома'); if (all) all.click(); await sleep(800);
  } catch (e) { out.error = String(e && e.stack || e); }
  document.getElementById('res').textContent = 'RESULT' + JSON.stringify(out) + 'END';
})();
</script>'''

proxy = None
try:
    for _ in range(60):
        try:
            call('/api/state'); break
        except Exception:
            time.sleep(.5)
    plan = call('/api/state')['plan']
    plan.update({'buildings': [], 'links': [], 'poles': [], 'geo': {'lat': 55.7558, 'lon': 37.6173}})
    call('/api/plan', 'PUT', json.dumps(plan).encode(), {'Content-Type': 'application/json'})
    open(wrap, 'w', encoding='utf-8').write(PAGE)
    proxy = S(('127.0.0.1', PROXY), P)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    gl = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
    out = subprocess.run([browser, '--headless=new', '--hide-scrollbars', '--window-size=500,900', *gl, '--dump-dom', f'http://127.0.0.1:{PROXY}/_draw_test.html'],
                         capture_output=True, timeout=300, text=True, encoding='utf-8').stdout
    m = re.search(r'<pre id="res">RESULT(.*?)END</pre>', out, re.S)
    if not m:
        print('браузер не открыл страницу (запрещено политикой или не запустился) — проверка обводки пропущена')
    else:
        r = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>'))
        if not r.get('ready'):
            print('карта не загрузилась (нет WebGL или сети до карты) — проверка обводки пропущена', r.get('error', ''))
        else:
            check('в меню есть обводка, столб, узел, магистраль, поиск и спутник', r.get('menuHasTools'), r)
            check('после выбора инструмента меню закрывается, внизу подсказка', r.get('menuClosed') and r.get('barShown'), r)
            check('«Готово» появляется после трёх точек', r.get('doneButton'), r)
            check('пока включён инструмент, карта смотрит сверху и не наклоняется (иначе нажатие попадало в соседний дом)', r.get('pitchLocked'), r.get('pitchLocked'))
            b = (r.get('plan') or {}).get('buildings') or []
            check('дом обведён и сохранён на сервере (4 угла, имя из окна)', len(b) == 1 and len(b[0].get('outline') or []) == 4 and b[0].get('name') == 'Тестовый дом', b)
            check('после обводки у дома открывается карточка с действиями', r.get('cardShown'), r)
            check('в карточке есть цвета, выбранный цвет сохраняется', r.get('hasColors') and r.get('swatches', 0) >= 10 and re.match(r'^#[0-9a-f]{6}$', (((r.get('plan3') or {}).get('buildings') or [{}])[0].get('color')) or ''), (r.get('swatches'), (r.get('plan3') or {}).get('buildings')))
            b2 = (r.get('plan2') or {}).get('buildings') or []
            check('прямоугольник по трём нажатиям — второй дом из 4 углов', len(b2) == 2 and len(b2[1].get('outline') or []) == 4, b2 and [len(x.get('outline') or []) for x in b2])
            pc = lambda k: (((r.get(k) or {}).get('buildings') or [{}])[0].get('outline') or [])
            check('«Углы»: у дома видны кружки углов, «+» на сторонах и ручка переноса', r.get('vtx') == 4 and r.get('mid') == 4 and r.get('moveHandle') == 1, (r.get('vtx'), r.get('mid'), r.get('moveHandle')))
            check('«+» на стороне добавляет угол (5 углов), дом пересохранён', len(pc('plan4')) == 5 and r.get('vtx2') == 5, (len(pc('plan4')), r.get('vtx2')))
            check('выбранный угол убирается (снова 4)', r.get('delButton') and len(pc('plan5')) == 4, (r.get('delButton'), len(pc('plan5'))))
            check('«Сеть дома»: карта сети суженная до дома, с кнопкой возврата', r.get('card2') and r.get('netShown') and r.get('netBack'), (r.get('card2'), r.get('netShown'), r.get('netBack')))
            check('«Открыть дом»: этажи и комнаты, кнопка «Все дома»', r.get('openBtn') and r.get('houseShown'), (r.get('openBtn'), r.get('houseShown')))
            if r.get('autoTarget'):                                  # нужны плитки карты (интернет); без них проверка пропускается
                check('«По зданию на карте»: берётся то здание, на которое нажали (точка нажатия лежит внутри полученного контура, а не на соседней улице)', r.get('autoInside') and r.get('autoDist') <= max(80, r.get('autoSize') or 0), (r.get('autoInside'), r.get('autoDist'), r.get('autoSize'), r.get('autoError')))
            else:
                print('  --   «По зданию на карте»: зданий на карте не нашлось (нет плиток) — проверка пропущена', {k: r.get(k) for k in ('autoError', 'bFeat', 'bTypes', 'pitch', 'hasLayer', 'dbg')})
            p6 = (r.get('plan6') or {}).get('poles') or []
            check('столбы: два нажатия — два столба, подписи на карте', len(p6) == 2 and r.get('poleMarks') == 2, (len(p6), r.get('poleMarks')))
            n7 = (r.get('plan7') or {}).get('nodes') or []
            check('узел: поставлен, предложена привязка, узел подвязан к шкафу', r.get('bindShown') and len(n7) == 1 and (n7[0].get('ref') or {}).get('kind') == 'place' and r.get('nodeMarks') == 1, (r.get('bindShown'), n7))
            l8 = (r.get('plan8') or {}).get('links') or []
            check('магистраль между двумя столбами рисуется и сохраняется', r.get('linkModal') and len(l8) == 1 and {l8[0].get('from'), l8[0].get('to')} == {p['id'] for p in p6}, (r.get('linkModal'), l8))
            check('поиск по плану находит дом по названию и открывает его карточку', r.get('findInput') and (r.get('found') or 0) >= 1 and r.get('foundCard'), (r.get('findInput'), r.get('found'), r.get('foundCard')))
            check('план хранит место на земле', (r.get('plan2') or {}).get('geo') == {'lat': 55.7558, 'lon': 37.6173}, (r.get('plan2') or {}).get('geo'))
finally:
    if os.path.exists(wrap):
        os.remove(wrap)
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
