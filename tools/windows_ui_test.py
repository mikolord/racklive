"""Windows setup: short steps and exact command copying in the real device form."""
import runpy
from pathlib import Path

# Reuse the isolated demo/browser lifecycle; no real computer or clipboard is changed.
harness = runpy.run_path(str(Path(__file__).with_name('brands_ui_test.py')), run_name='windows_guide_harness')
harness['main'].__globals__['PAGE'] = r'''<!doctype html><meta charset="utf-8">
<iframe id="f" style="border:0;width:390px;height:844px"></iframe><pre id="result"></pre><script>
localStorage.setItem('rl_skin','aurora');localStorage.setItem('rl_theme','light');
const f=document.querySelector('iframe'),wait=ms=>new Promise(r=>setTimeout(r,ms)),checks=[];
const ck=(name,value)=>checks.push([name,!!value]);f.src='/?skin=aurora&add=1&addgrp=other#devices';
async function run(){
  for(let i=0;i<150&&!f.contentDocument?.querySelector('.dev-cat-item');i++)await wait(100);
  const d=f.contentDocument,w=f.contentWindow;
  [...d.querySelectorAll('.dev-cat-item')].find(b=>b.textContent.includes('Windows')).click();await wait(200);
  const guide=d.querySelector('.device-setup');ck('Windows guide renders',!!guide);
  ck('three short main steps',guide.querySelector(':scope > .device-setup-steps').children.length===3);
  ck('key instructions are collapsed',!guide.querySelector('details').open);
  const first=guide.querySelector('.codebox'),text=first.querySelector('.code').textContent;
  ck('command fixes Public firewall profile, limits to LAN',text.includes('-Profile Any')&&text.includes('-RemoteAddress LocalSubnet'));
  let copied='';Object.defineProperty(w.navigator,'clipboard',{value:undefined,configurable:true});
  d.execCommand=action=>{if(action==='copy'){copied=[...d.querySelectorAll('textarea')].at(-1).value;return true}return false};
  first.querySelector('button').click();await wait(100);
  ck('copy button copies the entire exact script',copied===text&&first.textContent.includes('Скопировано'));
  guide.querySelector('details summary').click();await wait(100);
  ck('key method expands with commands',guide.querySelector('details').open&&guide.querySelector('details').querySelectorAll('.codebox').length===2);
  ck('explains password versus PIN',guide.textContent.includes('PIN Windows Hello'));
  const modal=guide.closest('.modal'),body=modal.querySelector('.modal-body'),r=modal.getBoundingClientRect();
  ck('phone layout fits without horizontal overflow',r.left>=0&&r.right<=390&&body.scrollWidth<=body.clientWidth+1);
  ck('no interface crash',!d.querySelector('.rl-crash')&&!d.documentElement.hasAttribute('data-js-error'));
  document.querySelector('#result').textContent=JSON.stringify(checks);
}
run().catch(e=>document.querySelector('#result').textContent=JSON.stringify([['runtime: '+e,false]]));
</script>'''

if __name__ == '__main__':
    raise SystemExit(harness['main']())
