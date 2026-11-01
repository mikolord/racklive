/* Measured radio map. Interpolate only within a surveyed triangle in the same room;
   never infer an AP's range from throughput, or extrapolate beyond the samples. */
function coverageValue(t, metric) {
  const c = t.client || {}, v = metric === 'signal' ? c.rssi : t.down;
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  if (metric === 'signal') return c.wifi && v >= -120 && v < 0 && c.signalFresh !== false ? v : null;
  return v >= 0 ? v : null;
}
function coverageGroup(t) {
  const c = t.client || {};
  return JSON.stringify([c.apId || c.apName || '', c.band || '', !!c.wired]);
}
function coverageGroupLabel(t) {
  const c = t.client || {};
  return [c.apName || (c.wired ? 'Кабель' : 'Точка доступа не определена'), c.band, c.apName && !c.apId ? 'старые замеры' : ''].filter(Boolean).join(' · ');
}
function coverageScale(mesh, metric) {
  const values=mesh.samples.map(p=>p.v).filter(Number.isFinite);
  const best=values.length ? Math.max(...values) : null;
  return {best,metric};
}
function coverageRatio(v, scale) {
  if(v==null || scale.best==null) return null;
  return Math.max(0,Math.min(1,scale.metric==='signal' ? 1-(scale.best-v)/30 : scale.best>0 ? v/scale.best : 0));
}
function coverageColor(v, scale) {
    const k=coverageRatio(v,scale); if(k==null)return [142,142,147];
    const a=k<.5?[255,69,58]:[255,214,10], b=k<.5?[255,214,10]:[48,209,88], t=k<.5?k*2:(k-.5)*2;
    return a.map((c,i)=>Math.round(c+(b[i]-c)*t));
}
const coverageCross = (a,b,p) => (b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x);
function coverageWeights(p,a,b,c) {
  const den=coverageCross(a,b,c);
  if (Math.abs(den)<1e-7) return null;
  const u=coverageCross(b,c,p)/den, v=coverageCross(c,a,p)/den, w=1-u-v;
  return u>=-1e-7 && v>=-1e-7 && w>=-1e-7 ? [u,v,w] : null;
}
function coverageSegmentsCross(a,b,c,d) {
  // Contact counts as a barrier too: no interpolated colour leaks through a wall endpoint.
  if (Math.max(a.x,b.x)<Math.min(c.x,d.x)-1e-7 || Math.max(c.x,d.x)<Math.min(a.x,b.x)-1e-7 ||
      Math.max(a.y,b.y)<Math.min(c.y,d.y)-1e-7 || Math.max(c.y,d.y)<Math.min(a.y,b.y)-1e-7) return false;
  return coverageCross(a,b,c)*coverageCross(a,b,d)<=1e-7 && coverageCross(c,d,a)*coverageCross(c,d,b)<=1e-7;
}
function coverageRoom(p, rooms) {
  return rooms.findIndex(r => p.x>=r.x && p.x<=r.x+r.w && p.y>=r.y && p.y<=r.y+r.h);
}
function coverageTriangulate(samples) {
  if (samples.length<3) return [];
  // Bowyer-Watson in normalized coordinates; duplicate positions are removed by the caller.
  const x=Math.min(...samples.map(p=>p.x)), y=Math.min(...samples.map(p=>p.y));
  const span=Math.max(...samples.map(p=>Math.max(p.x-x,p.y-y)),1);
  const pts=samples.map(p=>({x:(p.x-x)/span,y:(p.y-y)/span}));
  const n=pts.length; pts.push({x:-20,y:-20},{x:21,y:-20},{x:.5,y:21});
  const circle = ids => {
    const [a,b,c]=ids.map(i=>pts[i]), d=2*coverageCross(a,b,c);
    if (Math.abs(d)<1e-12) return null;
    const aa=a.x*a.x+a.y*a.y, bb=b.x*b.x+b.y*b.y, cc=c.x*c.x+c.y*c.y;
    const cx=(aa*(b.y-c.y)+bb*(c.y-a.y)+cc*(a.y-b.y))/d;
    const cy=(aa*(c.x-b.x)+bb*(a.x-c.x)+cc*(b.x-a.x))/d;
    return {ids,x:cx,y:cy,r:(cx-a.x)**2+(cy-a.y)**2};
  };
  let tris=[circle([n,n+1,n+2])];
  for (let i=0;i<n;i++) {
    const p=pts[i], edges=new Map(), keep=[];
    tris.forEach(t=>{
      if ((p.x-t.x)**2+(p.y-t.y)**2 > t.r+1e-10) { keep.push(t); return; }
      t.ids.forEach((a,j)=>{ const b=t.ids[(j+1)%3], key=a<b?a+':'+b:b+':'+a;
        if (edges.has(key)) edges.delete(key); else edges.set(key,[a,b]); });
    });
    edges.forEach(([a,b])=>{const t=circle([a,b,i]);if(t)keep.push(t)}); tris=keep;
  }
  return tris.filter(t=>t.ids.every(i=>i<n)).map(t=>t.ids.map(i=>samples[i]));
}
function coverageMesh(tests, metric, floor) {
  const latest=new Map();
  [...tests].sort((a,b)=>(b.t||0)-(a.t||0)).forEach(t=>{
    const v=coverageValue(t,metric), p=t.where;
    if (v==null || !p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) return;
    const key=p.x+':'+p.y; if (!latest.has(key)) latest.set(key,{x:p.x,y:p.y,v});
  });
  const samples=[...latest.values()], rooms=floor.rooms||[], walls=(floor.walls||[]).filter(w=>[w.x1,w.y1,w.x2,w.y2].every(Number.isFinite));
  const groups=new Map(); samples.forEach(p=>{const key=coverageRoom(p,rooms);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(p)});
  const triangles=[];
  groups.forEach((points,room)=>coverageTriangulate(points).forEach(tri=>{
    const barriers=[...walls.map(w=>[{x:w.x1,y:w.y1},{x:w.x2,y:w.y2}])];
    // Outside samples cannot paint through a room, even when no explicit wall was drawn.
    if(room<0) rooms.forEach(r=>{const q=[{x:r.x,y:r.y},{x:r.x+r.w,y:r.y},{x:r.x+r.w,y:r.y+r.h},{x:r.x,y:r.y+r.h}];q.forEach((p,i)=>barriers.push([p,q[(i+1)%4]]))});
    if(barriers.some(([p,q])=>coverageWeights(p,...tri) || coverageWeights(q,...tri) || tri.some((a,i)=>coverageSegmentsCross(a,tri[(i+1)%3],p,q)))) return;
    triangles.push(tri);
  }));
  return {samples,triangles};
}
function coverageRaster(mesh, metric) {
  if(!mesh.triangles.length) return null;
  const pts=mesh.triangles.flat(), x=Math.min(...pts.map(p=>p.x)), y=Math.min(...pts.map(p=>p.y));
  const w=Math.max(...pts.map(p=>p.x))-x, h=Math.max(...pts.map(p=>p.y))-y;
  if(!w || !h) return null;
  const step=Math.max(w,h)/160, width=Math.max(1,Math.ceil(w/step)), height=Math.max(1,Math.ceil(h/step));
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const ctx=canvas.getContext('2d');if(!ctx)return null;
  const img=ctx.createImageData(width,height), scale=coverageScale(mesh,metric);
  mesh.triangles.forEach(tri=>{
    const left=Math.max(0,Math.floor((Math.min(...tri.map(p=>p.x))-x)/step)), right=Math.min(width-1,Math.ceil((Math.max(...tri.map(p=>p.x))-x)/step));
    const top=Math.max(0,Math.floor((Math.min(...tri.map(p=>p.y))-y)/step)), bottom=Math.min(height-1,Math.ceil((Math.max(...tri.map(p=>p.y))-y)/step));
    for(let iy=top;iy<=bottom;iy++)for(let ix=left;ix<=right;ix++){
      const weights=coverageWeights({x:x+(ix+.5)*step,y:y+(iy+.5)*step},...tri);if(!weights)continue;
      const rgb=coverageColor(weights.reduce((v,k,i)=>v+k*tri[i].v,0),scale), index=(iy*width+ix)*4;
      rgb.forEach((c,j)=>img.data[index+j]=c);img.data[index+3]=185;
    }
  });
  ctx.putImageData(img,0,0);
  return {x,y,w:width*step,h:height*step,url:canvas.toDataURL('image/png')};
}
