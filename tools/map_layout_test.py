"""Stable placement, grouped Wi-Fi clients, and dynamic cables in the real map code."""
import os, re, subprocess, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = open(os.path.join(ROOT, 'web', 'src', '40_map.jsx'), encoding='utf-8').read()
constants = re.search(r'^const M = .*?$', s, re.M).group(0)
layout = s[s.index('function layoutMap('):s.index('/* other ways to see the same network')]
edge = s[s.index('function mapOrthogonal('):s.index('function MapNode(')]
js = constants + "\nconst unitDevIds = u => u.deviceIds?.length ? u.deviceIds : u.deviceId ? [u.deviceId] : [];\n" + layout + edge + r"""
const check=(name,ok)=>{console.log((ok?'OK   ':'FAIL ')+name);if(!ok)process.exitCode=1};
const node=(id,kind='other',client=false)=>({id,label:id,kind,client});
const state={pos:{},parents:{}}, order={};
const map={positions:{'d:a':[0,0],'d:b':[700,0]},wifiGroups:{'d:a':{dx:260,dy:0},'d:b':{dx:260,dy:0}}};
const data={map,racks:[],topology:{nodes:[node('d:a','ap'),node('d:b','ap'),node('h:one','other',true)],edges:[{id:'e1',source:'d:a',target:'h:one',kind:'wifi'}]}};
const calc=()=>placeStableMap(layoutMap(data, {'d:a':false,'d:b':false},true),data,{},'columns',state,order);
let a=calc();const first={...a.pos['h:one']};const origA={...a.pos['d:a']};
data.topology.nodes.push(node('h:two','other',true));data.topology.edges.push({id:'e2',source:'d:a',target:'h:two',kind:'wifi'});
let b=calc();check('existing card stays and new grouped client is below',b.pos['h:one'].x===first.x && b.pos['h:one'].y===first.y && b.pos['h:two'].y>=first.y+first.h);
check('manually positioned parent stays',b.pos['d:a'].x===origA.x && b.pos['d:a'].y===origA.y);
data.topology.edges[0].source='d:b';let c=calc();check('client moves to new group',c.pos['h:one'].x>c.pos['d:b'].x);check('old group closes gap',c.pos['h:two'].y===c.pos['d:a'].y);
data.topology.nodes.push(node('h:three','other',true));data.topology.edges.push({id:'e3',source:'d:a',target:'h:three',kind:'wifi'});let d=calc();check('new client does not cover previous',d.pos['h:three'].y>=d.pos['h:two'].y+d.pos['h:two'].h);
const s2={pos:{},parents:{}}, o2={};
const ungrouped={map:{positions:{'d:a':[0,0],'h:fixed':[326,0]}},racks:[],topology:{nodes:[node('d:a','ap'),node('h:fixed','other',true)],edges:[{id:'q',source:'d:a',target:'h:fixed',kind:'wifi'}]}};
let u=placeStableMap(layoutMap(ungrouped,{},true),ungrouped,{},'columns',s2,o2);let fixedY=u.pos['h:fixed'].y;
ungrouped.topology.nodes.push(node('h:new','other',true));ungrouped.topology.edges.push({id:'q2',source:'d:a',target:'h:new',kind:'wifi'});
u=placeStableMap(layoutMap(ungrouped,{},true),ungrouped,{},'columns',s2,o2);const f=u.pos['h:fixed'], nn=u.pos['h:new'];
check('new ungrouped card avoids saved position without moving it',f.y===fixedY && !(nn.x < f.x+f.w && nn.x+nn.w>f.x && nn.y<f.y+f.h && nn.y+nn.h>f.y));
const e={source:'a',target:'b',kind:'wire'}, L={pos:{a:{x:300,y:0,w:196,h:46},b:{x:0,y:0,w:196,h:46}},nodes:{},racks:[]};
check('straight wire follows endpoints',/^M300,23 L196,23$/.test(edgePath(e,L,'straight').d));
check('curved wire exits left and reaches facing edge',/^M300,23 C/.test(edgePath(e,L,'curved').d) && edgePath(e,L,'curved').d.endsWith('196,23'));
const O={pos:{a:{x:0,y:0,w:100,h:50},b:{x:600,y:0,w:100,h:50},block:{x:250,y:-40,w:100,h:130}},nodes:{},racks:[]};
let ortho=edgePath({source:'a',target:'b'},O,'orthogonal');let pts=[...ortho.d.matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)].map(m=>({x:+m[1],y:+m[2]}));
const crosses=(p,q,r)=>p.x===q.x ? p.x>r.x && p.x<r.x+r.w && Math.max(Math.min(p.y,q.y),r.y)<Math.min(Math.max(p.y,q.y),r.y+r.h) : p.y>r.y && p.y<r.y+r.h && Math.max(Math.min(p.x,q.x),r.x)<Math.min(Math.max(p.x,q.x),r.x+r.w);
check('orthogonal wire has no diagonal segments',pts.length>=2&&pts.slice(1).every((p,i)=>p.x===pts[i].x||p.y===pts[i].y));
check('orthogonal wire avoids blocking card',pts.slice(1).every((p,i)=>!crosses(pts[i],p,O.pos.block)));
O.pos.b.x=-400;let moved=edgePath({source:'a',target:'b'},O,'orthogonal');check('orthogonal wire follows moved endpoints',moved.d!==ortho.d);
const rem=data.topology.nodes;data.map.positions['d:a']=[-700,-250];data.topology.nodes.push({...node('test:new','other',true),phantom:true});data.topology.edges.push({id:'fake',source:'d:a',target:'test:new',kind:'wifi'});delete data.map.wifiGroups['d:a'];const q=calc();check('test client uses manually placed AP position',q.pos['test:new'].x>=q.pos['d:a'].x+q.pos['d:a'].w);
// Real (non-phantom) Wi-Fi devices keep the user's initial anchors but follow an observed AP change.
const realMap={positions:{'d:r1':[0,0],'d:r2':[800,0],'h:phone':[266,0],'h:fixed':[266,100]},wifiGroups:{}};
const realData={map:realMap,racks:[],topology:{nodes:[node('d:r1','ap'),node('d:r2','ap'),node('h:phone','phone',true),node('h:fixed','other',true)],edges:[{id:'p',source:'d:r1',target:'h:phone',kind:'wifi'},{id:'f',source:'d:r1',target:'h:fixed',kind:'wifi'}]}};
const rs={pos:{},parents:{}}, ro={}, realCalc=()=>placeStableMap(layoutMap(realData,{'d:r1':false,'d:r2':false},true),realData,{'h:phone':[266,0]},'columns',rs,ro);
let r1=realCalc();check('initial manually placed real phone stays put',r1.pos['h:phone'].x===266);
realData.topology.edges[0].source='d:r2';let r2=realCalc();check('real pinned phone follows changed AP',r2.pos['h:phone'].x>=r2.pos['d:r2'].x+r2.pos['d:r2'].w);
check('roaming preserves other pinned cards and saved coordinates',r2.pos['h:fixed'].x===266 && realMap.positions['h:phone'][0]===266);
check('aligned old group closes the departed phone gap automatically',r2.pos['h:fixed'].y===0 && !!rs.autoGroups['d:r1']);
let r3=realCalc();check('old drag position cannot pull roaming client back',r3.pos['h:phone'].x===r2.pos['h:phone'].x);
const recovered={pos:{},parents:{},wifiSeen:{...rs.wifiSeen},autoWifi:{...rs.autoWifi},autoGroups:{...rs.autoGroups}};
let r4=placeStableMap(layoutMap(realData,{'d:r1':false,'d:r2':false},true),realData,{},'columns',recovered,{});check('roaming survives a browser reload',r4.pos['h:phone'].x>=r4.pos['d:r2'].x+r4.pos['d:r2'].w);check('automatic grouping survives reload',r4.pos['h:fixed'].y===0 && !!recovered.autoGroups['d:r1']);
realData.topology.edges=realData.topology.edges.filter(e=>e.id!=='p');placeStableMap(layoutMap(realData,{'d:r1':false,'d:r2':false},true),realData,{},'columns',recovered,{});check('missing association does not erase last AP',recovered.wifiSeen['h:phone']==='d:r2');
const opt={pos:{},parents:{},groupOptOut:{'d:r1':true}}, optData=JSON.parse(JSON.stringify(realData));optData.topology.edges=[{id:'p',source:'d:r1',target:'h:phone',kind:'wifi'},{id:'f',source:'d:r1',target:'h:fixed',kind:'wifi'}];
const optCalc=()=>placeStableMap(layoutMap(optData,{'d:r1':false,'d:r2':false},true),optData,{},'columns',opt,{});optCalc();optData.topology.edges[0].source='d:r2';let optResult=optCalc();check('explicitly disabled grouping stays disabled',!opt.autoGroups['d:r1'] && optResult.pos['h:fixed'].y===100);
const legacy={map:{positions:{'d:r1':[0,0],'d:r2':[800,0],'h:phone':[266,0],'h:peer':[266,58]}},racks:[],topology:{nodes:[node('d:r1','ap'),node('d:r2','ap'),node('h:phone','phone',true),node('h:peer','phone',true)],edges:[{id:'l1',source:'d:r2',target:'h:phone',kind:'wifi'},{id:'l2',source:'d:r1',target:'h:peer',kind:'wifi'}]}};
const ls={pos:{},parents:{}}, ll=placeStableMap(layoutMap(legacy,{'d:r1':false,'d:r2':false},true),legacy,{},'columns',ls,{});check('legacy stale pin migrates only with clear old-AP neighbour',ll.pos['h:phone'].x>=ll.pos['d:r2'].x+ll.pos['d:r2'].w && ls.autoWifi['h:phone']);check('legacy old column closes the gap',ll.pos['h:peer'].y===0);
const lone=JSON.parse(JSON.stringify(legacy));lone.topology.nodes=lone.topology.nodes.filter(n=>n.id!=='h:peer');lone.topology.edges=lone.topology.edges.filter(e=>e.id!=='l2');const loneState={pos:{},parents:{}}, loneOut=placeStableMap(layoutMap(lone,{'d:r1':false,'d:r2':false},true),lone,{},'columns',loneState,{});check('ambiguous legacy pin is left unchanged',loneOut.pos['h:phone'].x===266 && !loneState.autoWifi['h:phone']);
const managed={map:{positions:{'d:r1':[0,0],'d:r2':[800,0],'d:phone':[266,0]}},racks:[],topology:{nodes:[node('d:r1','ap'),node('d:r2','ap'),node('d:phone','phone',false)],edges:[{id:'m',source:'d:r1',target:'d:phone',kind:'wifi'}]}};
const ms={pos:{},parents:{}}, mc=()=>placeStableMap(layoutMap(managed,{'d:r1':false,'d:r2':false},true),managed,{},'columns',ms,{});mc();managed.topology.edges[0].source='d:r2';const mm=mc();check('a separately configured phone also follows Wi-Fi',mm.pos['d:phone'].x>=mm.pos['d:r2'].x+mm.pos['d:r2'].w);
const remoteData={map:{positions:{}},racks:[],topology:{nodes:[node('inet','internet'),{...node('d:remote','ap'),remote:true},{...node('test:r','other',true),phantom:true}],edges:[{id:'r',source:'inet',target:'d:remote',kind:'remote'},{id:'rf',source:'d:remote',target:'test:r',kind:'wifi'}]}};
const remoteLayout=layoutMap(remoteData,{'d:remote':false},{});check('test clients visible even if remote point is closed',!!remoteLayout.pos['test:r'] && !!remoteLayout.nodes['test:r']);
check('regular cards have same size',M.NW===M.CW && M.NH===M.CH);
"""
with tempfile.NamedTemporaryFile('w',encoding='utf-8',suffix='.js',delete=False) as f:
    f.write(js);name=f.name
try:
    result=subprocess.run(['node',name],check=False)
    raise SystemExit(result.returncode)
finally:
    os.unlink(name)
