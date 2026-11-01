"""«Приложения» в настоящем интерфейсе (демо-сервер, Chrome headless): Инструменты → Приложения → готовый пример → «Добавить» → карточка (разрешения, риск, compose) →
выбор устройства → «Установить» (в демо-режиме запуск запрещён — сообщение об этом) → «Убрать описание».
Run: python tools/capps_ui_test.py   (prints ВСЁ OK; без Chrome пропускается)"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSER = next((p for p in (r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '/usr/bin/chromium', '/usr/bin/google-chrome') if os.path.isfile(p)), None)
if not BROWSER:
    print('нет Chrome — проверка пропущена\n\nВСЁ OK'); sys.exit(0)

WRAP = r'''<!doctype html><meta charset="utf-8"><body style="margin:0"><pre id="res">RUNNING</pre>
<iframe id="app" src="/?tsec=apps#tools" style="width:1100px;height:1000px;border:0"></iframe>
<script>
const out = [], t = (n, ok, x) => out.push([n, !!ok, x === undefined ? '' : String(x)]), sleep = ms => new Promise(r => setTimeout(r, ms));
const fr = document.getElementById('app'); const D = () => fr.contentDocument;
const until = async (f, ms = 15000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { const v = f(); if (v) return v; } catch (e) { } await sleep(150); } return null; };
const byText = (sel, txt) => [...D().querySelectorAll(sel)].find(e => e.textContent.includes(txt));
(async () => {
  try {
    await sleep(2500);
    const addBtn = await until(() => { const row = byText('.plug-row', 'UniFi Network Application'); return row && [...row.querySelectorAll('button')].find(b => b.textContent.trim() === 'Добавить'); });
    t('готовые примеры показаны (UniFi) с кнопкой «Добавить»', !!addBtn);
    addBtn.click();
    const row = await until(() => { const r = [...D().querySelectorAll('button.plug-row')].find(e => e.textContent.includes('UniFi Network Application')); return r; });
    t('после «Добавить» UniFi появился в «Моих приложениях»', !!row);
    row.click();
    t('карточка: разрешения словами и закрепление образов', !!(await until(() => byText('li', 'принимает подключения'))) && D().body.textContent.includes('Что приложению разрешено'));
    t('карточка: про проброс порта на роутере', D().body.textContent.includes('пробросьте нужный порт'));
    byText('button', 'Что будет запущено').click(); await sleep(300);
    t('compose показывается и содержит предел памяти', !!byText('pre', 'mem_limit: 1536m'));
    t('поле пароля базы данных есть', !!D().querySelector('input[type=password]'));
    const sel = await until(() => D().querySelector('select.input')); t('выбор устройства есть (демо-сервер)', !!sel && sel.options.length > 0);
    const inst = await until(() => byText('button', 'Установить на устройство')); t('кнопка «Установить на устройство» есть', !!inst);
    t('порты можно менять: поля портов есть, «менять нельзя» у служебных', D().body.textContent.includes('Порты на устройстве') && D().querySelectorAll('input[type=number]').length >= 4 && [...D().querySelectorAll('input[type=number]')].filter(i => i.disabled).length === 2);
    const pw = D().querySelector('input[type=password]'); const s = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(pw), 'value').set; s.call(pw, 'secret-pass-1'); pw.dispatchEvent(new Event('input', { bubbles: true }));
    inst.click(); await sleep(500);
    const ok = [...D().querySelectorAll('button')].filter(b => b.textContent.trim() === 'Установить'); t('перед установкой спрашивает подтверждение с правами', ok.length >= 1 && D().body.textContent.includes('Подтвердите установку'), ok.length);
    ok[ok.length - 1].click();
    t('в демо-режиме запуск отклонён понятным сообщением', !!(await until(() => D().body.textContent.includes('в демо-режиме приложения не запускаются'))), 'warn=' + [...D().querySelectorAll('.cam-warn,.toast,[role=dialog]')].map(x => x.textContent.slice(0, 120)).join(' || ') + ' dlg=' + D().body.textContent.includes('Подтвердите установку') + ' btns=' + [...D().querySelectorAll('button')].map(b => b.textContent.trim().slice(0, 20)).join('|'));
    byText('button', 'Убрать описание из Rack Live').click(); await sleep(500);
    const rm = [...D().querySelectorAll('button')].filter(b => b.textContent.trim() === 'Убрать'); rm[rm.length - 1].click();
    t('описание убирается, возврат к списку', !!(await until(() => !byText('button.plug-row', 'UniFi Network Application') && byText('b', 'Мои приложения'))));
    t('нет ошибок JavaScript в интерфейсе', !D().documentElement.outerHTML.includes('data-js-error="'));
  } catch (e) { t('исключение', false, e.stack || e); }
  document.getElementById('res').textContent = 'RESULT' + JSON.stringify(out) + 'END';
})();
</script>'''


def main():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    tmp = tempfile.mkdtemp(prefix='rl-ca-')
    web = os.path.join(tmp, 'web'); shutil.copytree(os.path.join(ROOT, 'web'), web, ignore=shutil.ignore_patterns('node_modules', 'src'))
    data = os.path.join(tmp, 'data'); os.makedirs(data)
    open(os.path.join(web, '_t.html'), 'w', encoding='utf-8').write(WRAP)
    env = dict(os.environ, RL_DEMO='1', RL_DATA=data, RL_WEB=web, RL_PORT=str(port), PYTHONIOENCODING='utf-8')
    srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
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
        time.sleep(3)
        r = subprocess.run([BROWSER, '--headless=new', '--disable-gpu', '--window-size=1100,1100', '--virtual-time-budget=90000', '--dump-dom', base + '/_t.html'], capture_output=True, text=True, encoding='utf-8', timeout=240)
        m = re.search(r'RESULT(\[.*?\])END', r.stdout, re.S)
        if not m:
            print('нет результата:', r.stdout[-500:], r.stderr[-300:]); sys.exit(1)
        for name, ok, extra in json.loads(m.group(1).replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')):
            print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + extra))
            if not ok:
                bad.append(name)
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
