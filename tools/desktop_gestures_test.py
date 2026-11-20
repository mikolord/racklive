"""Browser tests of the real viewer input code with an isolated fake RFB transport."""
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
harness = runpy.run_path(str(Path(__file__).with_name('brands_ui_test.py')), run_name='desktop_input_harness')
STUB = r'''
window.records={mouse:[],keys:[],clipboard:[],fetches:[]};
if(new URLSearchParams(location.search).has('installfixture'))window.RL_DESKTOP_APP={device:'fixture',name:'Fixture',base:'/desktop-app/'+('a'.repeat(32))+'/',installing:true};
window.fetch=async url=>{records.fetches.push(String(url));return {ok:true,json:async()=>({ok:true,ticket:'test-only',password:'test-only',name:'Fixture'})};};
Object.defineProperty(document.documentElement,'requestFullscreen',{value:undefined,configurable:true});
class RFB extends EventTarget {
 static messages={pointerEvent:(sock,x,y,mask)=>records.mouse.push({x,y,mask})};
 constructor(target){super();this._sock={};this._clipboardServerCapabilitiesFormats={};this._screen=document.createElement('div');this._screen.style.cssText='display:flex;width:100%;height:100%;overflow:auto';const c=document.createElement('canvas');c.width=1920;c.height=1080;c.style.cssText='margin:auto;flex-shrink:0';this._display={set scale(value){c.style.width=c.width*value+'px';c.style.height=c.height*value+'px';}};this._screen.append(c);target.append(this._screen);queueMicrotask(()=>this.dispatchEvent(new Event('connect')));}
 sendKey(key,code,down){records.keys.push({key,code,down});}
 clipboardPasteFrom(text){records.clipboard.push(text);}
 focus(){} blur(){} disconnect(){const e=new Event('disconnect');e.detail={clean:true};this.dispatchEvent(e);}
}
'''
harness['main'].__globals__['PAGE'] = r'''<!doctype html><meta charset="utf-8">
<iframe id="f" style="border:0;width:390px;height:844px"></iframe><pre id="result"></pre><script>
const f=document.querySelector('iframe'),wait=ms=>new Promise(r=>setTimeout(r,ms)),checks=[];
const ck=(n,v)=>checks.push([n,!!v]);
async function run(){
 await fetch('/api/devices',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'/windows Fixture',driver:'windows',host:'desktop.invalid',enabled:true})});
 const inventory=await(await fetch('/api/state')).json(),fixtureDevice=inventory.devices.find(x=>x.driver==='windows');
 f.src='/_desktop_input_fixture.html?device='+encodeURIComponent(fixtureDevice.id);
 for(let i=0;i<100&&!f.contentWindow.records;i++)await wait(100);
 const w=f.contentWindow,d=f.contentDocument,$=id=>d.getElementById(id),r=w.records;
 for(let i=0;i<50&&$('status').textContent!=='Подключено';i++)await wait(100);
 await wait(100);const canvas=d.querySelector('canvas');
 const finger=(x,y,id=1)=>({clientX:x,clientY:y,identifier:id});
 function touch(type,points){const e=new w.Event(type,{bubbles:true,cancelable:true});Object.defineProperty(e,'touches',{value:points});canvas.dispatchEvent(e);}
 const reset=()=>{r.mouse.length=0;r.keys.length=0;};
 $('input-mode').value='trackpad';$('input-mode').dispatchEvent(new w.Event('change'));
 ck('connected controls enabled',!$('left').disabled);
 reset();touch('touchstart',[finger(70,90)]);touch('touchmove',[finger(110,100)]);touch('touchend',[]);
 ck('trackpad moves without click',r.mouse.length>0&&r.mouse.every(e=>e.mask===0));
 const last=r.mouse.at(-1);reset();touch('touchstart',[finger(170,140)]);touch('touchend',[]);
 ck('trackpad tap clicks cursor position',r.mouse.length===2&&r.mouse[0].mask===1&&r.mouse[1].mask===0&&r.mouse[0].x===last.x);
 await wait(360);reset();touch('touchstart',[finger(70,90)]);await wait(700);touch('touchend',[]);
 ck('long hold right clicks without left click',r.mouse.map(e=>e.mask).join(',')==='4,0');
 reset();touch('touchstart',[finger(70,90)]);await wait(200);ck('hold has visible progress',!$('hold-feedback').hidden);const ptr=d.querySelector('.rd-pointer').getBoundingClientRect(),h=$('hold-feedback');ck('trackpad hold anchors at cursor not finger',Math.abs(parseFloat(h.style.left)-(ptr.left+ptr.width/2))<2&&Math.abs(parseFloat(h.style.left)-70)>5);ck('hold overlay translucent and hollow',Number(w.getComputedStyle(h).opacity)<.8&&w.getComputedStyle(h.querySelector('circle')).fill==='none');await wait(250);ck('hold arms faster with ready feedback',$('hold-feedback').classList.contains('ready'));touch('touchmove',[finger(120,100)]);const movedPtr=d.querySelector('.rd-pointer').getBoundingClientRect();ck('held ring follows dragged cursor',Math.abs(parseFloat(h.style.left)-(movedPtr.left+movedPtr.width/2))<2);touch('touchend',[]);ck('hold feedback clears on release',$('hold-feedback').hidden);
 ck('hold and move drags with automatic release',r.mouse[0]?.mask===1&&r.mouse.at(-1)?.mask===0&&!r.mouse.some(e=>e.mask===4));
 reset();touch('touchstart',[finger(70,90)]);touch('touchend',[]);touch('touchstart',[finger(70,90)]);await wait(700);touch('touchmove',[finger(120,100)]);touch('touchend',[]);
 ck('double tap hold starts drag not right click',r.mouse.map(e=>e.mask).join(',').startsWith('1,0,1,')&&r.mouse.at(-1)?.mask===0&&!r.mouse.some(e=>e.mask===4));
 reset();touch('touchstart',[finger(70,90),finger(100,90,2)]);touch('touchmove',[finger(70,140),finger(100,140,2)]);touch('touchend',[]);
 ck('two finger scroll sends wheel only',r.mouse.some(e=>e.mask===8)&&r.mouse.every(e=>[0,8,16,32,64].includes(e.mask)));
 reset();touch('touchstart',[finger(70,90),finger(100,90,2)]);touch('touchend',[]);
 ck('two finger tap right clicks',r.mouse.map(e=>e.mask).join(',')==='4,0');
 reset();$('drag').click();touch('touchstart',[finger(70,90)]);touch('touchmove',[finger(100,100)]);touch('touchend',[]);$('drag').click();
 ck('drag keeps left held then releases',r.mouse[0]?.mask===1&&r.mouse.at(-1)?.mask===0&&r.mouse.slice(0,-1).every(e=>e.mask===1));
 reset();$('drag').click();$('view').checked=true;$('view').dispatchEvent(new w.Event('change'));
 ck('view only releases held button',r.mouse.map(e=>e.mask).join(',')==='1,0'&&$('drag').getAttribute('aria-pressed')==='false');
 reset();touch('touchstart',[finger(70,90)]);touch('touchend',[]);
 ck('view only blocks touch and text',r.mouse.length===0&&$('type').disabled);
 $('view').checked=false;$('view').dispatchEvent(new w.Event('change'));
 reset();$('drag').click();touch('touchstart',[finger(70,90)]);touch('touchcancel',[]);
 ck('cancel releases held left button',r.mouse.at(-1)?.mask===0&&$('drag').getAttribute('aria-pressed')==='false');
 $('input-mode').value='direct';$('input-mode').dispatchEvent(new w.Event('change'));
 reset();const rect=canvas.getBoundingClientRect();touch('touchstart',[finger(rect.left+rect.width/4,rect.top+rect.height/2)]);touch('touchend',[]);
 ck('direct touch maps CSS pixels to framebuffer',r.mouse.at(-2)?.x===480&&r.mouse.at(-2)?.y===540&&r.mouse.at(-2)?.mask===1);
 $('full').click();await wait(50);
 ck('fullscreen fallback remains usable',!$('full').disabled&&d.body.classList.contains('rd-immersive')&&w.getComputedStyle($('tools')).display!=='none');
 ck('fullscreen starts with collapsed dock',d.body.classList.contains('rd-dock-hidden')&&$('dock-handle').getAttribute('aria-expanded')==='false');$('dock-handle').click();
 ck('subtle arrow opens and closes dock',!d.body.classList.contains('rd-dock-hidden')&&$('dock-handle').getAttribute('aria-expanded')==='true');$('dock-handle').click();ck('dock can be collapsed again',d.body.classList.contains('rd-dock-hidden'));$('dock-handle').click();
 $('tools').click();ck('floating menu restores tools',d.body.classList.contains('rd-tools'));
 $('full').click();ck('fullscreen exits',!d.body.classList.contains('rd-immersive'));
 reset();$('text').click();ck('floating text opens a paste-friendly draft',!$('live').checked&&!$('popup').hidden);$('live').checked=false;$('live').dispatchEvent(new w.Event('change'));$('buffer').value='Я\nA';$('type').click();
 ck('Unicode and Enter typed as keysyms',r.keys.map(e=>e.key).join(',')===[0x0100042f,0xff0d,65].join(','));
 ck('text is cleared after sending',$('buffer').value==='');
 reset();$('live').checked=true;$('live').dispatchEvent(new w.Event('change'));$('buffer').value='\u200bя';$('buffer').dispatchEvent(new w.InputEvent('input',{inputType:'insertText',data:'я'}));
 $('buffer').value='';$('buffer').dispatchEvent(new w.InputEvent('input',{inputType:'deleteContentBackward'}));
 ck('live Unicode and backspace work',r.keys.length===2&&r.keys[0].key===0x0100044f&&r.keys[1].key===0xff08);
 $('live').checked=false;$('live').dispatchEvent(new w.Event('change'));$('buffer').value='Привет';$('paste').click();
 ck('legacy clipboard does not corrupt Cyrillic',r.clipboard.length===0&&$('text-status').textContent.includes('Unicode'));
 reset();$('live').checked=true;$('live').dispatchEvent(new w.Event('change'));const pasteEvent=new w.Event('paste',{bubbles:true,cancelable:true});Object.defineProperty(pasteEvent,'clipboardData',{value:{getData:()=> 'Текст из iPhone'}});$('buffer').dispatchEvent(pasteEvent);
 ck('native phone paste becomes draft without remote typing',!$('live').checked&&$('buffer').value==='Текст из iPhone'&&r.keys.length===0);
 Object.defineProperty(w.navigator,'clipboard',{value:{readText:async()=> ' вставка',writeText:async()=>{}},configurable:true});$('phone-paste').click();await wait(50);ck('phone clipboard button inserts text',$('buffer').value.includes('вставка'));
 w.navigator.clipboard.readText=async()=>{throw new Error('denied');};$('phone-paste').click();await wait(50);ck('denied clipboard offers native paste',$('text-status').textContent.includes('Удержи палец'));
 $('close').click();$('help').click();ck('iPhone fullscreen instructions available',!$('help-popup').hidden&&$('help-popup').textContent.includes('На экран'));
 $('help-close').click();$('tools').click();$('screen-tab').click();
 ck('settings have compact tabs',!$('pane-screen').hidden&&$('pane-mouse').hidden&&$('screen-tab').getAttribute('aria-selected')==='true');
 reset();$('keys-tab').click();d.querySelector('[data-shortcut="0"]').click();ck('Win R sends and releases Windows modifier',r.keys.length===3&&r.keys[0].key===0xffeb&&r.keys[0].down===true&&r.keys[1].key===0x72&&r.keys[2].down===false);
 $('cursor-size').value='40';$('cursor-size').dispatchEvent(new w.Event('input'));$('cursor-shape').value='cross';$('cursor-shape').dispatchEvent(new w.Event('input'));$('cursor-color').value='#ff3300';$('cursor-color').dispatchEvent(new w.Event('input'));
 ck('cursor style controls apply and persist',d.querySelector('.rd-pointer').style.getPropertyValue('--cursor-size')==='40px'&&d.querySelector('.rd-pointer svg').innerHTML.includes('#ff3300')&&JSON.parse(w.localStorage.getItem('rl-desktop-cursor')).shape==='cross');
 $('cursor-shape').value='mac';$('cursor-shape').dispatchEvent(new w.Event('input'));ck('macOS arrow has dark body and white border',d.querySelector('.rd-pointer svg').innerHTML.includes('fill="#111"')&&d.querySelector('.rd-pointer svg').innerHTML.includes('stroke="white"'));
 $('cursor-shape').value='hand';$('cursor-shape').dispatchEvent(new w.Event('input'));ck('hand cursor is selectable and persists',d.querySelector('.rd-pointer svg').innerHTML.includes('fill="#fff"')&&JSON.parse(w.localStorage.getItem('rl-desktop-cursor')).shape==='hand');
 $('fit').value='stretch';$('fit').dispatchEvent(new w.Event('change'));await wait(50);
 let bounds=canvas.getBoundingClientRect(),area=$('screen').getBoundingClientRect();
 ck('stretch fills both viewport dimensions',Math.abs(bounds.width-area.width)<1&&Math.abs(bounds.height-area.height)<1);
 $('scale').click();$('zoom').value='3';$('zoom').dispatchEvent(new w.Event('input'));await wait(50);
 ck('zoom slider enlarges image',canvas.getBoundingClientRect().width>area.width*2.9);
 $('settings-close').click();$('input-mode').value='trackpad';$('input-mode').dispatchEvent(new w.Event('change'));
 const scroll=canvas.parentElement;
 touch('touchstart',[finger(60,90)]);touch('touchmove',[finger(1500,90)]);touch('touchend',[]);
 ck('zoomed view follows cursor right',scroll.scrollLeft>100);
 $('follow').checked=false;const heldScroll=scroll.scrollLeft;
 touch('touchstart',[finger(200,90)]);touch('touchmove',[finger(50,90)]);touch('touchend',[]);
 ck('follow can be disabled',Math.abs(scroll.scrollLeft-heldScroll)<1);$('follow').checked=true;
 $('scale').click();reset();touch('touchstart',[finger(100,100),finger(200,100,2)]);touch('touchmove',[finger(50,100),finger(250,100,2)]);touch('touchend',[]);
 ck('pinch zoom does not click or scroll Windows',$('zoom-value').textContent==='200%'&&r.mouse.length===0);
 $('scale').click();$('speed').value='.25';$('speed').dispatchEvent(new w.Event('input'));reset();touch('touchstart',[finger(100,100)]);touch('touchmove',[finger(80,100)]);touch('touchend',[]);const slow=r.mouse.at(-1).x;
 $('speed').value='3';$('speed').dispatchEvent(new w.Event('input'));reset();touch('touchstart',[finger(100,100)]);touch('touchmove',[finger(80,100)]);touch('touchend',[]);const fast=r.mouse.at(-1).x;
 ck('speed slider changes pointer travel',slow-fast>100&&$('speed-value').textContent==='3.00×');
 $('full').click();$('dock-handle').click();ck('text button available after opening immersive dock',!d.body.classList.contains('rd-dock-hidden')&&w.getComputedStyle($('text')).display!=='none');$('full').click();
 ck('phone viewer has no horizontal overflow',d.documentElement.scrollWidth<=390);
 ck('exit button sits in dock',!!$('desktop-dock').querySelector('#exit'));
 $('full').click();$('stop').click();await wait(50);ck('reconnect is visible centrally even in fullscreen',!$('connection-card').hidden&&!$('connect').disabled&&$('connect').closest('#connection-card')!==null);$('connect').click();await wait(100);ck('central reconnect opens a new session',$('status').textContent==='Подключено'&&$('connection-card').hidden);$('full').click();
 Object.defineProperty(w.navigator,'standalone',{value:true,configurable:true});w.RL_DESKTOP_APP={device:'fixture',base:'/desktop-app/fixture/'};w.close=()=>{w.exitAttempted=true;};$('exit').click();await wait(350);
 ck('installed app exit disconnects and attempts close',w.exitAttempted&&$('status').textContent!=='Подключено');
 ck('blocked close has an honest idle screen',!$('exit-popup').hidden&&$('exit-popup').textContent.includes('Сеанс завершён'));
 $('resume').click();await wait(100);ck('idle screen can reconnect',$('status').textContent==='Подключено');
 Object.defineProperty(w.navigator,'standalone',{value:false,configurable:true});delete w.RL_DESKTOP_APP;$('exit').click();for(let i=0;i<50&&!f.contentWindow.location.search.includes('plugin=desktop');i++)await wait(100);
 for(let i=0;i<100&&!f.contentDocument.body.textContent.includes('Рабочий стол Windows');i++)await wait(100);
 ck('browser exit returns to device plugin',f.contentWindow.location.search.includes('device='+fixtureDevice.id)&&f.contentWindow.location.search.includes('plugin=desktop')&&f.contentDocument.body.textContent.includes('Рабочий стол Windows'));
 f.src='/_desktop_input_fixture.html?installfixture=1';for(let i=0;i<100&&!f.contentWindow.RL_DESKTOP_APP?.installing;i++)await wait(100);await wait(100);
 const installWindow=f.contentWindow,installDoc=f.contentDocument;
 ck('install page offers a copyable external link',!installDoc.getElementById('install-popup').hidden&&installDoc.getElementById('install-link').value.includes('/desktop-install/')&&!installDoc.getElementById('copy-install').disabled);
 ck('install page never auto-connects Windows',!installWindow.records.fetches.some(x=>x.includes('/api/desktop/open'))&&installDoc.getElementById('status').textContent==='Готово к установке');
 document.querySelector('#result').textContent=JSON.stringify(checks);
}
run().catch(e=>document.querySelector('#result').textContent=JSON.stringify([['runtime: '+e,false]]));
</script>'''


if __name__ == '__main__':
    fixture = ROOT / 'web/_desktop_input_fixture.html'
    source = (ROOT / 'web/desktop.html').read_text(encoding='utf-8')
    fixture.write_text(source.replace("import RFB from '/vendor/novnc/core/rfb.js';", STUB), encoding='utf-8')
    try:
        raise SystemExit(harness['main']())
    finally:
        fixture.unlink(missing_ok=True)
