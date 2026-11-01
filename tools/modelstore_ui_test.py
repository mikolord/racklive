"""«Магазин моделей» в настоящем интерфейсе: демо-сервер с ПОДМЕНЁННЫМ каталогом и GitHub (без сети), Chrome headless кликает:
вкладка «Из магазина» → поиск → модель → «Применить» → карточка получила фото и порты; «Модерация» → токен → заявка → предпросмотр → «Принять».
Run: python tools/modelstore_ui_test.py   (prints ВСЁ OK; без Chrome пропускается)"""
import base64, json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER = next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '/usr/bin/chromium', '/usr/bin/google-chrome') if os.path.isfile(p)), None)
if not BROWSER:
    print('нет Chrome — проверка пропущена\n\nВСЁ OK'); sys.exit(0)

LAUNCH = r'''
import json, re, runpy, sys, base64
sys.path.insert(0, sys.argv[1]); MARK = sys.argv[2]
from rackd import modelstore as M, models
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
CARD = {'format': 'racklive-card', 'version': 1, 'id': 'demo-sw', 'vendor': 'Demo', 'model': 'SW-8', 'kind': 'switch', 'title': 'Demo SW-8',
        'photo': {'file': 'photo.png', 'license': 'own', 'author': 'Я'},
        'spots': [{'n': 1, 'x': .2, 'y': .5, 'w': .04, 'h': .3}, {'n': 2, 'x': .3, 'y': .5, 'w': .04, 'h': .3}], 'pzoom': {'x': .1, 'y': .2, 'w': .5, 'h': .6}}
INDEX = {'models': [{'id': 'demo-sw', 'path': 'models/demo/demo-sw', 'vendor': 'Demo', 'model': 'SW-8', 'title': 'Demo SW-8', 'kind': 'switch', 'ports': 2, 'photo': 'photo.png', 'model3d': False, 'license': 'own', 'author': 'Я', 'notes': ''},
                    {'id': 'zy-other', 'path': 'models/zyxel/zy-other', 'vendor': 'Zyxel', 'model': 'GS1900', 'title': 'Zyxel GS1900', 'kind': 'switch', 'ports': 24, 'photo': None, 'model3d': False}]}
FILES = {M.INDEX_URL: json.dumps(INDEX).encode(), M.RAW + 'models/demo/demo-sw/model.json': json.dumps(CARD).encode(), M.RAW + 'models/demo/demo-sw/photo.png': PNG}
SHA = 'a' * 40
for f, b in (('model.json', json.dumps(CARD).encode()), ('photo.png', PNG)):
    FILES['https://raw.githubusercontent.com/' + M.REPO + '/' + SHA + '/models/demo/demo-sw/' + f] = b
def fake_get(url, limit, headers=None, timeout=15):
    url = url.split('?')[0]
    if url not in FILES: raise M.StoreError('GitHub ответил 404')
    return FILES[url]
M._get = fake_get
PULL = {'number': 7, 'state': 'open', 'title': 'Модель: Demo SW-8', 'body': 'Заявка #3\n\nCloses #3', 'user': {'login': 'github-actions[bot]'}, 'created_at': '2026-10-27', 'head': {'sha': SHA, 'repo': {'full_name': M.REPO}}}
def fake_api(self, method, path, body=None, auth=True):
    if path.startswith('/repos/' + M.REPO + '/pulls?state=open'): return [PULL] if PULL['state'] == 'open' else []
    m = re.match(r'^/repos/' + re.escape(M.REPO) + r'/pulls/7(/files.*|/merge)?$', path)
    if m:
        if m.group(1) and m.group(1).startswith('/files'): return [{'filename': 'models/demo/demo-sw/model.json'}, {'filename': 'models/demo/demo-sw/photo.png'}]
        if m.group(1) == '/merge': PULL['state'] = 'merged'; open(MARK, 'w').write('merged'); return {'merged': True}
        return PULL
    if path.endswith('/status'): return {'state': 'success', 'statuses': [{'state': 'success'}]}
    if path.endswith('/check-runs'): return {'check_runs': []}
    if path == '/repos/' + M.REPO: return {'permissions': {'push': True}}
    if path == '/user': return {'login': 'mikolord'}
    return {}
M.Store._api = fake_api
sys.argv = ['rackd']
runpy.run_module('rackd', run_name='__main__')
'''

WRAP = r'''<!doctype html><meta charset="utf-8"><body style="margin:0"><pre id="res">RUNNING</pre>
<iframe id="app" src="@URL@" style="width:1100px;height:900px;border:0"></iframe>
<script>
const out = [], t = (n, ok, x) => out.push([n, !!ok, x === undefined ? '' : String(x)]), sleep = ms => new Promise(r => setTimeout(r, ms));
const fr = document.getElementById('app'); const D = () => fr.contentDocument;
const until = async (f, ms = 12000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { const v = f(); if (v) return v; } catch (e) { } await sleep(150); } return null; };
const byText = (sel, txt) => [...D().querySelectorAll(sel)].find(e => e.textContent.includes(txt));
const setVal = (el, v) => { const s = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
(async () => {
  try {
    await sleep(2500);
    const row = await until(() => byText('.plug-row', 'Demo SW-8'));
    t('каталог: модель из магазина в списке', !!row);
    t('каталог: поиск есть, вторая модель тоже', !!D().querySelector('input[placeholder^="Поиск"]') && !!byText('.plug-row', 'Zyxel GS1900'));
    setVal(D().querySelector('input[placeholder^="Поиск"]'), 'zyxel'); await sleep(200);
    t('поиск отфильтровал список', !byText('.plug-row', 'Demo SW-8') && !!byText('.plug-row', 'Zyxel GS1900'));
    setVal(D().querySelector('input[placeholder^="Поиск"]'), 'demo'); await sleep(200);
    byText('.plug-row', 'Demo SW-8').click();
    t('подробности: фото с метками портов', !!(await until(() => D().querySelectorAll('.ph-spot').length === 2)), D().querySelectorAll('.ph-spot').length);
    const ap = await until(() => byText('button', 'Применить к этой карточке')); t('кнопка «Применить» есть', !!ap);
    ap.click(); await sleep(2500);
    const st = await (await fetch('/api/state')).json();
    const ent = st.cards.find(c => c.photo && c.spots && c.spots.length === 2);
    t('карточка получила фото, 2 порта и зону приближения', !!ent && ent.pzoom && ent.pzoom.w === .5, JSON.stringify(ent && ent.spots));
    // модерация (окно закрылось после применения — открываем заново)
    fr.src = fr.src.replace('look=store', 'look=store&again=1'); await sleep(3500);
    const mb = await until(() => byText('button', 'Модерация')); t('кнопка «Модерация» есть', !!mb); mb.click();
    const inp = await until(() => D().querySelector('input[placeholder="github_pat_…"]')); t('без токена просит токен', !!inp);
    setVal(inp, 'github_pat_' + 'B'.repeat(40)); await sleep(100); byText('button', 'Сохранить токен').click();
    const rowp = await until(() => byText('.plug-row', '#7')); t('с токеном видна заявка #7 от бота с зелёной проверкой', !!rowp && rowp.textContent.includes('проверка пройдена'), rowp && rowp.textContent);
    rowp.click();
    t('предпросмотр заявки: фото с метками, кнопка «Принять» доступна', !!(await until(() => D().querySelectorAll('.ph-spot').length === 2)) && !byText('button', 'Принять').disabled);
    byText('button', 'Принять').click();
    await sleep(500);
    const allAccept = [...D().querySelectorAll('button')].filter(b => b.textContent.trim() === 'Принять');
    t('перед принятием спрашивает подтверждение (второе «Принять» в окне)', allAccept.length >= 2, allAccept.length);
    (allAccept[allAccept.length - 1]).click(); await sleep(2000);
    t('заявка исчезла из списка', !(byText('.plug-row', '#7')));
    t('нет ошибок JavaScript в интерфейсе', !D().documentElement.outerHTML.includes('data-js-error="'));
  } catch (e) { t('исключение', false, e.stack || e); }
  document.getElementById('res').textContent = 'RESULT' + JSON.stringify(out) + 'END';
})();
</script>'''


def main():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    tmp = tempfile.mkdtemp(prefix='rl-ms-')
    web = os.path.join(tmp, 'web'); shutil.copytree(os.path.join(ROOT, 'web'), web, ignore=shutil.ignore_patterns('node_modules', 'src'))
    data = os.path.join(tmp, 'data'); os.makedirs(data)
    mark = os.path.join(tmp, 'merged.flag'); launch = os.path.join(tmp, 'launch.py'); open(launch, 'w', encoding='utf-8').write(LAUNCH)
    env = dict(os.environ, RL_DEMO='1', RL_DATA=data, RL_WEB=web, RL_PORT=str(port), PYTHONIOENCODING='utf-8')
    srv = subprocess.Popen([sys.executable, launch, ROOT, mark], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}'
    bad = []
    try:
        for _ in range(60):
            try:
                st = json.loads(urllib.request.urlopen(base + '/api/state', timeout=5).read()); break
            except OSError:
                time.sleep(.3)
        else:
            raise SystemExit('сервер не запустился: ' + srv.stderr.read(2000).decode(errors='replace'))
        time.sleep(3)
        dev = next(d for d in st['devices'] if (d.get('state') or {}).get('ports'))
        open(os.path.join(web, '_t.html'), 'w', encoding='utf-8').write(WRAP.replace('@URL@', f'/?section=apps&app=cards&look=store&photo={dev["id"]}#settings'))
        r = subprocess.run([BROWSER, '--headless=new', '--disable-gpu', '--window-size=1100,1000', '--virtual-time-budget=60000', '--dump-dom', base + '/_t.html'],
                           capture_output=True, text=True, encoding='utf-8', timeout=180)
        m = re.search(r'RESULT(\[.*?\])END', r.stdout, re.S)
        if not m:
            print('нет результата:', r.stdout[-500:], r.stderr[-300:]); sys.exit(1)
        res = json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>'))
        for name, ok, extra in res:
            print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + extra))
            if not ok:
                bad.append(name)
        if '--shot' in sys.argv:                                      # a picture of the store tab with the fake catalog
            subprocess.run([BROWSER, '--headless=new', '--disable-gpu', '--window-size=560,900', '--virtual-time-budget=12000', '--screenshot=' + sys.argv[sys.argv.index('--shot') + 1],
                            base + f'/?section=apps&app=cards&look=store&photo={dev["id"]}#settings'], capture_output=True, timeout=120)
        merged = os.path.isfile(mark)
        print(('  ok   ' if merged else '  FAIL ') + 'на стороне сервера вызван merge заявки')
        if not merged:
            bad.append('merge')
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
