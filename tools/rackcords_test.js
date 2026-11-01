const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(require('path').join(__dirname, '../web/src/31_rackcords.jsx'), 'utf8').split('function RackCordOverlay')[0];
vm.runInNewContext(source + `
const rack = {units:[{id:'p',type:'patch',portmap:{ports:{2:{dev:'switch',port:'14'}}}}, {id:'s',deviceId:'switch'}, {id:'r',deviceId:'router'}]};
const data={devices:[]};
let links=rackCords(rack,data);
assert.strictEqual(links.length,1);
assert.strictEqual(links[0].a.port,'2');
assert.strictEqual(links[0].b.port,'14');
assert.strictEqual(links[0].b.unit,'s');
rack.patchCords=[{a:links[0].b,b:links[0].a}];
assert.strictEqual(rackCords(rack,data).length,1,'Reciprocal links must not be drawn twice');
rack.patchCords.push({a:{unit:'r',device:'router',port:'1'},b:{unit:'s',device:'switch',port:'12'}});
links=rackCords(rack,data);
assert.strictEqual(links.length,2);
const ports=rackCordPorts(rack,data,rack.units[1],'switch',[]);
assert(ports.some(p=>p.n==='14') && ports.some(p=>p.n==='12'),'Configured ports survive missing monitoring data');
const fixture={units:[{id:'org',type:'organizer',uStart:3,uSize:2},{id:'rear',type:'organizer',uStart:7,uSize:1,side:'back'}]};
const boxes=cordOrganizerBoxes(fixture,'front',570,1,'flat');
assert.strictEqual(boxes.length,1);
assert.strictEqual(boxes[0].top,100);
assert.strictEqual(boxes[0].height,88,'Occlude the entire organizer, including multi-U units');
const hidden=cordRoute({x:470,y:80},{x:500,y:240},boxes,562,1);
assert(hidden[0].includes('C') && hidden[0].endsWith('474,100'),'The curved upper cable disappears at the top lip');
assert(hidden[1].endsWith('L541,144'),'The side cable disappears at the side lip');
for(let i=0;i<20;i++) {
  assert(cordLane(570,i,true)>570-29,'Flat side bundle stays outside device faces');
  assert(cordLane(300,i,true,.5)>(300+482.6*.5)/2,'3D side bundle stays outside device faces');
}
for(const organizers of [[],[{y:80}],[{y:120}],[{y:35},{y:90}]]) {
  const paths=cordRoute({x:60,y:20},{x:85,y:100},organizers,110,.8);
  assert(paths.length && paths.every(p=>!p.includes('NaN')));
  if(organizers.length) assert(paths.length>=2,'The organizer hides the middle of the cord');
}
`, {assert, unitDevIds:u=>u.deviceIds || (u.deviceId?[u.deviceId]:[]), portName:(u,n)=>String(n), R3:{PANEL:482.6,TOP:70,U:44.45}, U_PX:46});
console.log('Patch-cord endpoints and organizer routes OK');
