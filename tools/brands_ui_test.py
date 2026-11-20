"""Exercise the slash catalogue in the real device editor at phone width (no debug port)."""
from pathlib import Path
import html
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', '/usr/bin/chromium']
PAGE = r'''<!doctype html><meta charset="utf-8">
<iframe id="f" style="border:0;width:390px;height:844px"></iframe><pre id="result"></pre><script>
localStorage.setItem('rl_skin','aurora');localStorage.setItem('rl_theme','light');
const f=document.querySelector('iframe'),wait=ms=>new Promise(r=>setTimeout(r,ms)),checks=[];
const ck=(n,v)=>checks.push([n,!!v]);
const write=(el,v)=>{const w=f.contentWindow;Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(el,v);el.dispatchEvent(new w.Event('input',{bubbles:true}));};
f.src='/?skin=aurora&editdev=DEVICE#devices';
async function run(){
  for(let i=0;i<150&&!f.contentDocument?.querySelector('.tag-catalog-btn');i++)await wait(100);
  const d=f.contentDocument,w=f.contentWindow;
  write(d.querySelector('.name-input input'),'Розетка у окна');await wait(100);
  d.querySelector('.tag-catalog-btn').click();await wait(200);
  ck('catalogue opens with every tag',d.querySelectorAll('.tag-catalog-item').length>100);
  d.querySelector('.tag-catalog input').dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await wait(200);
  ck('Escape closes only the catalogue',!d.querySelector('.tag-catalog')&&!!d.querySelector('.name-input'));
  d.querySelector('.tag-catalog-btn').click();await wait(200);
  [...d.querySelectorAll('.tag-catalog-roles button')].find(b=>b.textContent.includes('/iot')).click();await wait(100);
  write(d.querySelector('.tag-catalog input'),'/toya');await wait(100);
  ck('alias search finds Tuya',d.querySelectorAll('.tag-catalog-item').length===1&&d.querySelector('.tag-catalog-item').textContent.includes('Tuya'));
  ck('brand preview has IOT badge',d.querySelector('.tag-catalog-item .kind-brand-role')?.textContent==='IOT');
  d.querySelector('.tag-catalog-item').click();await wait(200);
  ck('selection preserves the device name',d.querySelector('.name-input input').value==='/iot/tuya Розетка у окна');
  ck('selection returns to editor',!d.querySelector('.tag-catalog')&&!!d.querySelector('.name-input'));
  write(d.querySelector('.name-input input'),'/');d.querySelector('.name-input input').focus();await wait(150);
  ck('slash suggests IOT role',[...d.querySelectorAll('.tag-role-chip')].some(b=>b.textContent==='IOT'));
  ck('suggestions offer the full catalogue',!!d.querySelector('.tag-suggest-head button'));
  d.querySelector('.tag-catalog-btn').click();await wait(200);
  write(d.querySelector('.tag-catalog input'),'/rcos');await wait(100);
  ck('RCOS alias finds ReckController',d.querySelectorAll('.tag-catalog-item').length===1&&d.querySelector('.tag-catalog-item').textContent.includes('ReckController'));
  d.querySelector('.tag-catalog-item').click();await wait(200);
  ck('controller selection inserts its slash tag',d.querySelector('.name-input input').value.startsWith('/reckcontroller '));
  d.querySelector('.tag-catalog-btn').click();await wait(200);
  const r=d.querySelector('.tag-catalog').closest('.modal').getBoundingClientRect();
  ck('catalogue fits phone viewport',r.left>=0&&r.right<=390&&r.top>=0);
  ck('no interface crash',!d.querySelector('.rl-crash')&&!d.documentElement.hasAttribute('data-js-error'));
  document.querySelector('#result').textContent=JSON.stringify(checks);
}
run().catch(e=>document.querySelector('#result').textContent=JSON.stringify([['runtime: '+e,false]]));
</script>'''


def main():
    browser = next((p for p in BROWSERS if Path(p).is_file()), None)
    if not browser:
        print('SKIP: no Chromium browser')
        return 0
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='rl-tags-ui-') as tmp:
        env = dict(os.environ, RL_DEMO='1', RL_DATA=tmp, RL_PORT=str(port), PYTHONIOENCODING='utf-8')
        srv = subprocess.Popen([sys.executable, '-m', 'rackd'], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = ROOT / 'web/_brands_ui_check.html'
        try:
            base = f'http://127.0.0.1:{port}'
            for _ in range(60):
                try:
                    state = json.load(urllib.request.urlopen(base + '/api/state', timeout=3))
                    break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError('demo did not start')
            device = next(d['id'] for d in state['devices'] if d['driver'] == 'demo_router')
            page.write_text(PAGE.replace('DEVICE', device), encoding='utf-8')
            result = subprocess.run([browser, '--headless=new', '--disable-gpu', '--window-size=900,950',
                                     '--virtual-time-budget=18000', '--dump-dom', base + '/' + page.name],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
            match = re.search(r'<pre id="result">(.*?)</pre>', result.stdout, re.S)
            checks = json.loads(html.unescape(match.group(1))) if match and match.group(1) else [['no browser result', False]]
            for name, passed in checks:
                print(('OK   ' if passed else 'FAIL ') + name)
            good = bool(checks) and all(passed for _, passed in checks)
            print('GOOD' if good else 'BAD')
            return 0 if good else 1
        finally:
            page.unlink(missing_ok=True)
            srv.terminate()
            try:
                srv.wait(10)
            except subprocess.TimeoutExpired:
                srv.kill()
                srv.wait()


if __name__ == '__main__':
    raise SystemExit(main())
