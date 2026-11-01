"""«Создать модель» (/modeler) в настоящем интерфейсе: демо-сервер с ПОДМЕНЁННЫМ GitHub, Chrome headless: фото → убрать фон → порты (касание + лупа) → приближение →
описание → «Опубликовать» → на сервере в «репозиторий» легли model.json, фото и index.json.
Run: python tools/modeler_test.py   (prints ВСЁ OK; без Chrome пропускается)"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER = next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '/usr/bin/chromium', '/usr/bin/google-chrome') if os.path.isfile(p)), None)
if not BROWSER:
    print('нет Chrome — проверка пропущена\n\nВСЁ OK'); sys.exit(0)

LAUNCH = r'''
import base64, json, runpy, sys
sys.path.insert(0, sys.argv[1]); DUMP = sys.argv[2]
from rackd import modelstore as M
FILES = {}
def fake_api(self, method, path, body=None, auth=True):
    pre = '/repos/' + M.REPO + '/contents/'
    if path.startswith(pre):
        name = path[len(pre):]
        if method == 'GET':
            if name not in FILES: raise M.StoreError('GitHub ответил 404')
            return {'sha': 's' + str(len(FILES[name])), 'content': base64.b64encode(FILES[name]).decode()}
        FILES[name] = base64.b64decode(body['content'])
        json.dump({k: len(v) for k, v in FILES.items()}, open(DUMP, 'w'))
        json.dump({k: v.decode('utf-8') for k, v in FILES.items() if k.endswith('.json')}, open(DUMP + '.text', 'w'))
        return {}
    if path == '/repos/' + M.REPO: return {'permissions': {'push': True}}
    if path == '/user': return {'login': 'mikolord'}
    return {}
M.Store._api = fake_api
sys.argv = ['rackd']
runpy.run_module('rackd', run_name='__main__')
'''

TEST = r'''<pre id="res">RUNNING</pre>
<script>
const out = [], t = (n, ok, x) => out.push([n, !!ok, x === undefined ? '' : String(x)]), sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  try {
    await sleep(1500);
    const W = window, D = document, E = W.__ed, S = E.S;
    t('страница «Создать модель» открылась', !!E && D.title === 'Создать модель', D.title);
    const c = D.createElement('canvas'); c.width = 1000; c.height = 220; const x = c.getContext('2d');
    x.fillStyle = '#fff'; x.fillRect(0, 0, 1000, 220); x.fillStyle = '#3c4046'; x.fillRect(60, 40, 880, 140); x.fillStyle = '#111'; for (let i = 0; i < 8; i++) x.fillRect(120 + i * 70, 90, 40, 40);
    const done = new Promise(res => { const o = W.render; W.render = (...a) => { o(...a); if (S.px) res(); }; });
    S.orig = c; S.bgOn = true; S.crop = true; E.process(); const errs = []; W.addEventListener('error', e => errs.push(e.message)); W.addEventListener('unhandledrejection', e => errs.push(String(e.reason)));
    for (let i = 0; i < 3000 && !(S.px && S.photoFile); i++) await sleep(100);
    t('фото обработано, фон убран', !!S.photoFile && S.px && S.px.borderClear >= .97, JSON.stringify(S.px) + ' ' + errs.join('|') + ' work=' + !!S.work);
    S.tab = 1; E.render(); await sleep(100);
    const ov = D.getElementById('ov'), r = ov.getBoundingClientRect();
    const fire = (type, fx, fy) => ov.dispatchEvent(new W.PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, clientX: r.left + fx * r.width, clientY: r.top + fy * r.height }));
    const place = (fx, fy) => { fire('pointerdown', fx, fy); fire('pointermove', fx, fy); fire('pointerup', fx, fy); };
    place(.2, .5); place(.35, .5); place(.5, .5);
    t('три порта поставлены касанием', S.spots.length === 3 && S.spots.map(s => s.n).join() === '1,2,3', JSON.stringify(S.spots.map(s => s.n)));
    S.zoom = { x: .1, y: .3, w: .6, h: .4 };
    S.vendor = 'Demo Co'; S.model = 'T8'; S.kind0 = 'switch'; S.rights = true; S.tab = 4; E.render(); await sleep(150);
    t('кнопка «Опубликовать» доступна', !D.getElementById('pub').disabled, JSON.stringify(E.checkState(S, S.px).filter(q => q.level === 'bad')));
    D.getElementById('pub').click();
    for (let i = 0; i < 3000 && !S.pubMsg; i++) await sleep(100);
    t('сообщение об успехе', S.pubOk === true && /Опубликовано/.test(S.pubMsg), S.pubMsg);
  } catch (e) { t('исключение', false, e.stack || e); }
  document.getElementById('res').textContent = 'RESULT' + JSON.stringify(out) + 'END';
})();
</script>'''


def main():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    tmp = tempfile.mkdtemp(prefix='rl-md-')
    web = os.path.join(tmp, 'web'); shutil.copytree(os.path.join(ROOT, 'web'), web, ignore=shutil.ignore_patterns('node_modules', 'src'))
    data = os.path.join(tmp, 'data'); os.makedirs(data)
    dump = os.path.join(tmp, 'repo.json'); launch = os.path.join(tmp, 'launch.py'); open(launch, 'w', encoding='utf-8').write(LAUNCH)
    page = open(os.path.join(web, 'modeler.html'), encoding='utf-8').read()
    open(os.path.join(web, '_t.html'), 'w', encoding='utf-8').write(page.replace('</body>', TEST + '</body>'))
    env = dict(os.environ, RL_DEMO='1', RL_DATA=data, RL_WEB=web, RL_PORT=str(port), PYTHONIOENCODING='utf-8')
    srv = subprocess.Popen([sys.executable, launch, ROOT, dump], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}'
    bad = []
    try:
        for _ in range(60):
            try:
                json.loads(urllib.request.urlopen(base + '/api/state', timeout=5).read()); break
            except OSError:
                time.sleep(.3)
        else:
            raise SystemExit('сервер не запустился: ' + srv.stderr.read(2000).decode(errors='replace'))
        urllib.request.urlopen(urllib.request.Request(base + '/api/models/store/token', data=json.dumps({'token': 'github_pat_' + 'B' * 40}).encode(), method='PUT', headers={'Content-Type': 'application/json'}), timeout=10).read()
        for page in ('/modeler', '/modeler-manifest.json', '/modeler-icon.svg', '/modeler-icon-192.png', '/modeler-apple-touch-icon.png'):
            r0 = urllib.request.urlopen(base + page, timeout=10)
            ok = r0.status == 200 and (page != '/modeler' or 'Создать модель' in r0.read().decode('utf-8'))       # not the SPA fallback (index.html)
            print(('  ok   ' if ok else '  FAIL ') + 'отдаётся ' + page)
            if not ok: bad.append(page)
        r = subprocess.run([BROWSER, '--headless=new', '--disable-gpu', '--window-size=900,1100', '--virtual-time-budget=400000', '--dump-dom', base + '/_t.html'],
                           capture_output=True, text=True, encoding='utf-8', timeout=180)
        m = re.search(r'RESULT(\[.*?\])END', r.stdout, re.S)
        if not m:
            print('нет результата:', r.stdout[-500:], r.stderr[-300:]); sys.exit(1)
        for name, ok, extra in json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')):
            print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + extra))
            if not ok: bad.append(name)
        files = json.load(open(dump)) if os.path.isfile(dump) else {}
        texts = json.load(open(dump + '.text', encoding='utf-8')) if os.path.isfile(dump + '.text') else {}
        mp = 'models/demo-co/demo-co-t8/model.json'
        card = json.loads(texts.get(mp, '{}')) if mp in texts else {}
        ok = mp in files and any(k.startswith('models/demo-co/demo-co-t8/photo.') for k in files) and 'index.json' in files
        print(('  ok   ' if ok else '  FAIL ') + 'в каталог легли model.json, фото и index.json ' + ('' if ok else str(list(files))))
        if not ok: bad.append('файлы каталога')
        ok = [p['n'] for p in card.get('spots', [])] == [1, 2, 3] and card.get('pzoom', {}).get('w') == .6 and card.get('vendor') == 'Demo Co'
        print(('  ok   ' if ok else '  FAIL ') + 'в model.json порты, приближение и название ' + ('' if ok else json.dumps(card, ensure_ascii=False)[:300]))
        if not ok: bad.append('model.json')
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except Exception:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n' + ('ВСЁ OK' if not bad else 'ОШИБКИ: ' + ', '.join(bad)))
    sys.exit(1 if bad else 0)


main()
