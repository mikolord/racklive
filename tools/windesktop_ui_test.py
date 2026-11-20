"""Desktop plugin and viewer errors at phone width, in an isolated demo."""
import runpy
from pathlib import Path

harness = runpy.run_path(str(Path(__file__).with_name('brands_ui_test.py')), run_name='desktop_ui_harness')
harness['main'].__globals__['PAGE'] = r'''<!doctype html><meta charset="utf-8">
<iframe id="f" style="border:0;width:390px;height:844px"></iframe><pre id="result"></pre><script>
localStorage.setItem('rl_skin','aurora');localStorage.setItem('rl_theme','light');
const f=document.querySelector('iframe'),wait=ms=>new Promise(r=>setTimeout(r,ms)),checks=[];
const ck=(n,v)=>checks.push([n,!!v]);
async function run(){
 const res=await fetch('/api/devices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'/windows Test desktop',driver:'windows',host:'desktop.invalid',enabled:true})});
 const saved=await res.json();if(!res.ok)throw new Error('fixture device not saved');
 const state=await(await fetch('/api/state')).json(),dev=state.devices.find(d=>d.driver==='windows');
 if(!dev)throw new Error('fixture device not found');
 f.src='/?skin=aurora&device='+encodeURIComponent(dev.id)+'&tab=plugins&plugin=desktop#devices';
 for(let i=0;i<150&&!f.contentDocument?.body.textContent.includes('В демо установка');i++)await wait(100);
 let d=f.contentDocument;
 ck('desktop plugin renders',d.body.textContent.includes('Рабочий стол Windows'));
 ck('demo cannot install software',[...d.querySelectorAll('button')].some(b=>b.textContent.includes('Установить')&&b.disabled));
 ck('explains audio and files limit',d.body.textContent.includes('Передача файлов и звук'));
 ck('KeenDNS inspection disabled in demo',[...d.querySelectorAll('button')].some(b=>b.textContent.includes('Проверить KeenDNS')&&b.disabled));
 ck('KeenDNS setup disabled in demo',[...d.querySelectorAll('button')].some(b=>b.textContent.includes('Настроить автоматически')&&b.disabled));
 ck('standalone PC app preparation disabled in demo',[...d.querySelectorAll('button')].some(b=>b.textContent.includes('Установить рабочий стол отдельно')&&b.disabled));
 const w=f.contentWindow;
 const brandIcons=await w.desktopAppIcons({id:'fixture',kind:'pc'},{icons:{}},'/windows Fixture');
 const customIcons=await w.desktopAppIcons({id:'fixture',kind:'pc'},{icons:{'d:fixture':'std:laptop'}},'Fixture');
 const pic=new w.Image();pic.src='data:image/png;base64,'+brandIcons['512'];await pic.decode();
 ck('PWA icons use map brand and custom choice',pic.naturalWidth===512&&pic.naturalHeight===512&&brandIcons['192']!==customIcons['192']);
 const guide=[...d.querySelectorAll('details')].find(x=>x.textContent.includes('Как подключаться из дома'));guide.open=true;
 ck('unknown IP explains provider and private VPN',guide.textContent.includes('CGNAT')&&guide.textContent.includes('провайдера')&&guide.textContent.includes('Tailscale')&&!!guide.querySelector('textarea'));
 const scenario=guide.querySelector('select');scenario.value='public';scenario.dispatchEvent(new f.contentWindow.Event('change',{bubbles:true}));await wait(100);
 ck('other routers get HTTPS and WebSocket steps',guide.textContent.includes('TCP 443')&&guide.textContent.includes('WebSocket')&&guide.textContent.includes('Origin'));
 ck('proxy sample has copy action',guide.textContent.includes('Скопировать')&&guide.querySelector('textarea')?.value.includes('proxy_set_header Host $http_host'));
 scenario.value='private';scenario.dispatchEvent(new f.contentWindow.Event('change',{bubbles:true}));await wait(100);
 ck('CGNAT guide does not require public ports',guide.textContent.includes('Телефон')||guide.textContent.includes('телефоне'));
 ck('phone plugin fits viewport',d.documentElement.scrollWidth<=390);
 ck('no interface crash',!d.querySelector('.rl-crash'));
 f.src='/desktop.html';
 for(let i=0;i<150&&!f.contentDocument?.querySelector('#status')?.textContent.includes('Не подключено');i++)await wait(100);
 d=f.contentDocument;
 ck('viewer explains missing PC',d.querySelector('#message')?.textContent.includes('Открой рабочий стол из плагина'));
 ck('viewer keeps controls disabled before connecting',[...d.querySelectorAll('.rd-control')].every(b=>b.disabled));
 ck('phone viewer fits viewport',d.documentElement.scrollWidth<=390);
 document.querySelector('#result').textContent=JSON.stringify(checks);
}
run().catch(e=>document.querySelector('#result').textContent=JSON.stringify([['runtime: '+e,false]]));
</script>'''

if __name__ == '__main__':
    raise SystemExit(harness['main']())
