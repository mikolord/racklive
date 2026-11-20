/* Network map: the rack in the middle, cables from its units to everything else. */
const M = { NW: 196, NH: 46, CW: 196, CH: 46, COL: 130, GAP: 12, RW: 310, RU: 38, MT: 150, MTH: 48 };     // MT×MTH: a box tile

function layoutMap(data, collapsed, remoteOpen = true) {
  const topo = data.topology || { nodes: [], edges: [] };
  const nodes = {}; topo.nodes.forEach(n => nodes[n.id] = { ...n });
  const tree = topo.edges.filter(e => !e.extra && !e.manual && nodes[e.source] && nodes[e.target]).map(e => ({ ...e }));
  const parentEdge = {}; const kids = {};
  tree.forEach(e => { parentEdge[e.target] = e; (kids[e.source] = kids[e.source] || []).push(e); });

  // racks and boxes stacked on the left, each in its own frame; rooms have no frame — their devices are ordinary nodes (a star, like UniFi)
  const racks = data.racks || [];
  const rackMeta = {}; let ry = 0;
  const pos = {}; const rackNode = {};
  const nidOf = (u, did) => did ? 'd:' + did : 'u:' + u.id;          // u: — a unit without a device still on the map (the ONT)
  const rooms = [];                                                  // rooms: no frame — kept for «Шкафы и места» (highlight their devices)
  // a device linked in several places is drawn where it is listed first (racks before boxes); elsewhere it is a dimmed copy
  racks.forEach(r => {
    const kind = r.kind || 'rack';
    if (kind === 'place') {                                          // a room: no box; its devices get a room tag and are laid out like the rest
      const ids = [];
      r.units.forEach(u => unitDevIds(u).forEach(did => { if (nodes['d:' + did]) { ids.push('d:' + did); if (!nodes['d:' + did].room) nodes['d:' + did].room = r.name; } }));
      rooms.push({ id: r.id, name: r.name, ids, units: r.units.length });
      return;
    }
    if (kind === 'rack') {
      const h = r.totalU * M.RU;
      rackMeta[r.id] = { id: r.id, name: r.name, kind, isRack: true, total: r.totalU, rows: r.totalU, y: ry, w: M.RW, h, units: r.units };
      r.units.forEach(u => {
        if ((u.side || 'front') === 'back') return;                 // back-side units aren't drawn on the map
        const ids = unitDevIds(u); const list = ids.length ? ids : [null];
        const cw = (M.RW - (list.length - 1) * 4) / list.length;      // a shelf with several devices: one cell each
        list.forEach((did, k) => { const nid = nidOf(u, did); if (!nodes[nid] || rackNode[nid]) return;
          rackNode[nid] = { ...u, rackId: r.id };
          pos[nid] = { x: k * (cw + 4), y: ry + (u.uStart - 1) * M.RU, w: cw, h: u.uSize * M.RU - 4, rack: true, rackId: r.id }; });
      });
      ry += h + 92; return;
    }
    // a box (щиток): tiles where they stand in «Размещение» (its grid scaled down), the frame as big as they need
    const tiles = []; let auto = 0;
    r.units.forEach(u => { const ids = unitDevIds(u); (ids.length ? ids : [null]).forEach(did => {
      const nid = nidOf(u, did);                                   // every tile, linked or not — as in «Размещение»
      let c, rw;
      if (typeof u.x === 'number' && typeof u.y === 'number' && ids.length <= 1) { c = Math.round(u.x / 226); rw = Math.round(u.y / 76); }
      else { c = auto % 2; rw = 100 + Math.floor(auto / 2); auto++; }
      tiles.push({ u, nid: nodes[nid] ? nid : null, c, r: rw }); }); });
    if (!tiles.length) return;                                       // an empty box: nothing to draw on the map
    const rowsUsed = [...new Set(tiles.map(t => t.r))].sort((a, b) => a - b);      // pack: no empty rows between
    tiles.forEach(t => { t.r = rowsUsed.indexOf(t.r); });
    const cols = Math.max(1, ...tiles.map(t => t.c + 1)), rows = Math.max(1, rowsUsed.length);
    const w = Math.max(M.MT * 2 + 10, cols * (M.MT + 10) - 10), h = rows * (M.MTH + 10) - 10;
    tiles.forEach(t => { t.x = t.c * (M.MT + 10); t.y = t.r * (M.MTH + 10);
      if (t.nid && rackNode[t.nid]) { t.dup = true; return; }                       // already drawn in another place
      if (t.nid) { rackNode[t.nid] = { ...t.u, rackId: r.id }; pos[t.nid] = { x: t.x, y: ry + t.y, w: M.MT, h: M.MTH, rack: true, rackId: r.id, tile: true }; } });
    rackMeta[r.id] = { id: r.id, name: r.name, kind, isRack: false, total: 0, rows, y: ry, w, h, tiles, units: r.units };
    ry += h + 92;
  });
  const stackH = Math.max(0, ry - 92);
  const frameW = Math.max(M.RW, ...Object.values(rackMeta).map(m => m.w));
  const hasRack = Object.keys(rackNode).length > 0;

  // a remote device (a router on another site) keeps who is connected to it to itself until it is tapped; the nodes go away entirely, so every map view gets the same picture
  const hiddenClients = {};                                          // client id → { node, parent }: «Найти устройство» opens the right device
  Object.values(nodes).filter(n => n.remote).forEach(n => {
    const es = kids[n.id] || [];
    const leaves = es.filter(e => nodes[e.target] && nodes[e.target].client && !nodes[e.target].phantom && !kids[e.target] && !rackNode[e.target]);
    if (!leaves.length) return;
    n.remoteClients = leaves.length;
    n.remoteOpen = remoteOpen === true || !!remoteOpen[n.id];
    if (n.remoteOpen) { if (remoteOpen !== true) leaves.forEach((e, i) => { nodes[e.target].remoteOf = n.id; nodes[e.target].remoteIdx = i; }); return; }   // remoteOf: the card flies out of its device (an animation)
    leaves.forEach(e => { hiddenClients[e.target] = { node: nodes[e.target], parent: n.id }; delete nodes[e.target]; delete parentEdge[e.target]; });
    kids[n.id] = es.filter(e => !leaves.includes(e));
  });

  // collapse big groups of Wi-Fi leaf clients
  const groups = {}; const hiddenIds = new Set();
  Object.entries(kids).forEach(([pid, es]) => {
    const wifiLeaves = es.filter(e => e.kind === 'wifi' && !kids[e.target]);
    if (wifiLeaves.length > 3 && collapsed[pid] !== false) {
      const gid = 'g:' + pid;
      groups[gid] = { id: gid, label: `${wifiLeaves.length} устройств по Wi-Fi`, members: wifiLeaves.map(e => nodes[e.target]), kind: 'group', parent: pid };
      wifiLeaves.forEach(e => { e.hidden = true; hiddenIds.add(e.target); });
      kids[pid] = es.filter(e => !e.hidden).concat([{ id: 'ge:' + pid, source: pid, target: gid, kind: 'wifi', group: true }]);
    }
  });
  Object.values(groups).forEach(g => { nodes[g.id] = g; });

  // columns: BFS from the rack (or from the internet's direct children when there is no rack)
  const inet = nodes['inet'];
  let roots = hasRack ? Object.keys(rackNode) : (kids['inet'] || []).filter(e => e.kind !== 'remote').map(e => e.target);
  if (!roots.length) roots = Object.keys(nodes).filter(id => !parentEdge[id] && id !== 'inet');
  const col = {}; const queue = [];
  roots.forEach(r => { col[r] = 0; queue.push(r); });
  while (queue.length) {
    const id = queue.shift();
    (kids[id] || []).filter(e => !e.hidden).forEach(e => { if (col[e.target] == null && !rackNode[e.target]) { col[e.target] = col[id] + 1; queue.push(e.target); } });
  }
  const colX = c => hasRack ? frameW + M.COL + (c - 1) * (M.NW + M.COL) : c * (M.NW + M.COL);
  const sizeOf = id => { const n = nodes[id]; return n.kind === 'group' || n.client ? [M.CW, M.CH] : [M.NW, M.NH]; };
  if (!hasRack) roots.forEach((r, i) => { const [w, h] = sizeOf(r); pos[r] = { x: 0, y: i * (h + 40), w, h }; });
  const maxCol = Math.max(0, ...Object.values(col));
  for (let c = 1; c <= maxCol; c++) {
    const ids = Object.keys(col).filter(id => col[id] === c);
    const pyOf = id => { const pe = parentEdge[id] || Object.values(kids).flat().find(e => e.target === id); const p = pe && pos[pe.source]; return p ? p.y + p.h / 2 : 0; };
    const byParent = {};
    ids.forEach(id => { const pe = parentEdge[id] || Object.values(kids).flat().find(e => e.target === id); (byParent[pe ? pe.source : '_'] = byParent[pe ? pe.source : '_'] || []).push({ id, port: pe ? (pe.sourcePort || 999) : 999 }); });
    let cursor = -Infinity;
    Object.entries(byParent).sort((a, b) => pyOf(a[1][0].id) - pyOf(b[1][0].id)).forEach(([pid, list]) => {
      list.sort((a, b) => a.port - b.port || String(nodes[a.id].label).localeCompare(String(nodes[b.id].label)));
      const heights = list.map(x => sizeOf(x.id)[1]);
      const groupH = heights.reduce((a, h) => a + h + M.GAP, -M.GAP);
      const p = pos[pid]; const center = p ? p.y + p.h / 2 : 0;
      let y = Math.max(cursor, center - groupH / 2);
      list.forEach((x, i) => { const [w, h] = sizeOf(x.id); pos[x.id] = { x: colX(c), y, w, h }; y += h + M.GAP; });
      cursor = y + M.GAP * 2;
    });
  }
  // internet + remote devices on top; an ONT / modem that isn't in a rack sits between the internet and the rack
  const box = hasRack && nodes['wan:box'] && !pos['wan:box'];
  const topY = (hasRack ? -170 : Math.min(0, ...Object.values(pos).map(p => p.y)) - 170) - (box ? M.NH + 70 : 0);
  const fw0 = (Object.values(rackMeta)[0] || {}).w || M.RW;
  if (inet) pos['inet'] = { x: (hasRack ? fw0 / 2 : M.NW / 2) - M.NW / 2, y: topY, w: M.NW, h: M.NH };
  if (box) { pos['wan:box'] = { x: fw0 / 2 - M.NW / 2, y: topY + M.NH + 70, w: M.NW, h: M.NH }; col['wan:box'] = -1; }
  const remotes = (kids['inet'] || []).filter(e => e.kind === 'remote').map(e => e.target);
  // remote devices (a VPS, a router on another site) go to the left of the internet node, in a column going up: each one has its own line from the internet.
  // In one row the lines ran along it behind the neighbours' cards and looked like a chain «internet → one → another → …»
  remotes.forEach((id, i) => { pos[id] = { x: (pos.inet ? pos.inet.x : 0) - (M.NW + 90), y: topY - i * (M.NH + 28), w: M.NW, h: M.NH }; col[id] = -1; });
  // the clients of an opened remote device: next to it on the left. The devices go up in a column, so each next list stays above the previous one
  let aboveY = Infinity;
  remotes.forEach(id => {
    const list = (kids[id] || []).filter(e => !e.hidden && nodes[e.target] && (nodes[e.target].client || nodes[e.target].kind === 'group') && !rackNode[e.target] && !kids[e.target]).map(e => e.target);
    if (!list.length) return;
    const h = list.length * (M.CH + M.GAP) - M.GAP, p = pos[id];
    const y = Math.min(p.y + p.h / 2 - h / 2, aboveY - h - M.GAP * 2);
    list.forEach((c, i) => { pos[c] = { x: p.x - (M.CW + 90), y: y + i * (M.CH + M.GAP), w: M.CW, h: M.CH }; col[c] = -2; });
    aboveY = y;
  });
  // nodes never reached (shouldn't happen) go to a bottom row
  let stray = 0; Object.keys(nodes).forEach(id => { if (!pos[id] && !hiddenIds.has(id)) {
    const [w, h] = sizeOf(id); pos[id] = { x: colX(1) + stray * (w + 20), y: stackH + 80, w, h }; stray++; } });
  // user overrides (edit mode drag)
  Object.entries(data.map.positions || {}).forEach(([id, [x, y]]) => { if (pos[id] && !pos[id].rack) Object.assign(pos[id], { x, y }); });
  const edges = [...Object.values(kids).flat().filter(e => !e.hidden), ...topo.edges.filter(e => (e.extra || e.manual) && pos[e.source] && pos[e.target])];
  return { nodes, pos, edges, groups, hasRack, rackNode, racks: Object.values(rackMeta), rooms, hiddenClients };
}

/* Live Wi-Fi associations, keyed by the actual client identity; never infer a
   transition from the absence of an AP in a temporary/offline poll. */
function mapIsWifiClient(n) {
  return !!n && !n.phantom && !n.rackUnit && (n.client || ['phone', 'tablet', 'pc', 'laptop', 'iot', 'tv', 'speaker', 'other'].includes(n.kind));
}
function mapWifiParents(data) {
  const t = data.topology || { nodes: [], edges: [] }, nodes = Object.fromEntries(t.nodes.map(n => [n.id, n]));
  const out = {};
  t.edges.forEach(e => { if (e.kind === 'wifi' && !e.extra && !e.manual && mapIsWifiClient(nodes[e.target]) && nodes[e.source]) out[e.target] = e.source; });
  return out;
}

function placeStableMap(L0, data, dragPos, style, stable, groupOrder) {
    if (style !== 'columns') return L0;
    const pos = Object.fromEntries(Object.entries(L0.pos).map(([id, p]) => [id, { ...p }]));
    const parent = {}; L0.edges.filter(e => !e.extra && !e.manual).forEach(e => { parent[e.target] = e.source; });
    const old = stable, pinned = data.map.positions || {}, wifi = mapWifiParents(data);
    old.wifiSeen = old.wifiSeen || {}; old.autoWifi = old.autoWifi || {}; old.autoGroups = old.autoGroups || {}; old.groupOptOut = old.groupOptOut || {};
    let groups = { ...old.autoGroups, ...(data.map.wifiGroups || {}) };
    const beforeWifi = { ...old.wifiSeen }, moved = new Set(), routes = [];
    Object.entries(wifi).forEach(([id, pid]) => {
      let before = old.wifiSeen[id];
      // Migration for old hand-placed clients without an association snapshot:
      // only infer their old AP when the saved card is clearly closer to another AP.
      if (!before && pinned[id] && pos[id] && pos[pid]) {
        const card = pos[id], apPos = p => { const a = pos[p], g = groups[p]; return a && { x: a.x + (g?.dx ?? a.w + 70), y: a.y + (g?.dy ?? 0) }; };
        const distance = p => { const q = apPos(p); return q ? Math.hypot(card.x - q.x, card.y - q.y) : Infinity; };
        const candidates = Object.values(L0.nodes).filter(n => n.kind === 'ap' && pos[n.id]).map(n => n.id);
        const closest = candidates.sort((a, b) => distance(a) - distance(b))[0];
        const nearPeer = closest && Object.entries(wifi).some(([other, p]) => other !== id && p === closest && pos[other] &&
          Math.abs(pos[other].x - card.x) < 32 && Math.abs(pos[other].y - card.y) < (card.h + M.GAP) * 3);
        if (nearPeer && closest !== pid && distance(pid) > distance(closest) * 1.6 + 100) before = closest;
      }
      if (!beforeWifi[id]) beforeWifi[id] = before || pid;
      if (before && before !== pid) { old.autoWifi[id] = true; moved.add(id); routes.push({ id, before, after: pid }); }
      old.wifiSeen[id] = pid;
    });
    Object.entries(pos).forEach(([id, p]) => {
      const prev = old.pos[id], auto = !!old.autoWifi[id];
      if (!p.rack && prev && (!pinned[id] || auto) && !moved.has(id) && (!L0.nodes[id]?.phantom || old.parents[id] === parent[id])) { p.x = prev.x; p.y = prev.y; }
    });
    Object.entries(dragPos).forEach(([id, [x, y]]) => { if (pos[id] && !old.autoWifi[id]) Object.assign(pos[id], { x, y }); });
    // When a real roaming event is observed, preserve a clearly aligned client
    // column as an automatic group. This closes the vacated slot and lets later
    // arrivals join without requiring the person to configure each AP manually.
    const makeAutoGroup = (pid, source) => {
      if (!pos[pid] || groups[pid] || old.groupOptOut[pid]) return;
      const ids = Object.keys({ ...beforeWifi, ...wifi }).filter(id => source ? beforeWifi[id] === pid : wifi[id] === pid && !moved.has(id));
      const ap = pos[pid], expectedX = ap.x + ap.w + 70;
      // Automatically generated coordinates may still belong to the AP's old
      // layout column; only trust them if they are actually near the moved AP.
      // Deliberately pinned cards remain valid anchors wherever the user put them.
      const pts = ids.map(id => ({ id, p: old.pos[id] || pos[id] })).filter(x => x.p &&
        (source || pinned[x.id] || Math.abs(x.p.x - expectedX) < 200)).map(x => x.p);
      if (source && pts.length < 2) return;
      if (pts.length > 1 && Math.max(...pts.map(p => p.x)) - Math.min(...pts.map(p => p.x)) > 32) return;
      pts.sort((a, b) => a.y - b.y || a.x - b.x);
      const first = pts[0];
      old.autoGroups[pid] = { dx: first ? first.x - ap.x : ap.w + 70, dy: first ? first.y - ap.y : ap.h + M.GAP };
      groups[pid] = old.autoGroups[pid];
    };
    routes.forEach(r => { makeAutoGroup(r.before, true); makeAutoGroup(r.after, false); });
    // Only newcomers and confirmed roaming clients move to make room.
    const needsAuto = id => !!old.autoWifi[id] && (!old.pos[id] || moved.has(id));
    const isMovedFake = id => L0.nodes[id]?.phantom && old.parents[id] !== parent[id];
    const fixed = Object.entries(pos).filter(([id, p]) => p.rack || (!needsAuto(id) && (pinned[id] || old.pos[id]) && !isMovedFake(id)));
    const frames = (L0.racks || []).map(r => ({ x: -14, y: r.y - 46, w: r.w + 28, h: r.h + 60 }));
    const occupied = [...fixed.map(([, p]) => p), ...frames];
    const overlaps = (p, q) => p.x < q.x + q.w + 12 && p.x + p.w + 12 > q.x && p.y < q.y + q.h + 12 && p.y + p.h + 12 > q.y;
    Object.entries(pos).filter(([id, p]) => !p.rack && (needsAuto(id) || (!pinned[id] && (!old.pos[id] || isMovedFake(id))))).forEach(([id, p]) => {
      const pid = wifi[id] || parent[id], ap = pos[pid];
      if ((L0.nodes[id]?.phantom || needsAuto(id)) && ap) {
        const peers = L0.edges.filter(e => e.kind === 'wifi' && e.source === pid && e.target !== id && (mapIsWifiClient(L0.nodes[e.target]) || L0.nodes[e.target]?.phantom) && pos[e.target] && !needsAuto(e.target)).map(e => pos[e.target]);
        if (peers.length && !L0.nodes[id]?.phantom) {
          const nearest = peers.sort((a, b) => Math.hypot(a.x - ap.x, a.y - ap.y) - Math.hypot(b.x - ap.x, b.y - ap.y))[0];
          const column = peers.filter(q => Math.abs(q.x - nearest.x) < 24); p.x = nearest.x; p.y = Math.max(...column.map(q => q.y + q.h)) + M.GAP;
        } else { p.x = ap.x + ap.w + 70; p.y = ap.y; }
      }
      let steps = 0; while (occupied.some(q => overlaps(p, q)) && steps++ < 500) p.y += M.NH + M.GAP;
      occupied.push(p);
    });
    const groupedIds = new Set(L0.edges.filter(e => e.kind === 'wifi' && groups[e.source] && (mapIsWifiClient(L0.nodes[e.target]) || L0.nodes[e.target]?.phantom) && pos[e.target] && !pos[e.target].rack).map(e => e.target));
    const blockers = [...Object.entries(pos).filter(([id]) => !groupedIds.has(id)).map(([, p]) => p), ...frames];
    Object.entries(groups).forEach(([pid, anchor]) => {
      const p = pos[pid]; if (!p || !anchor || typeof anchor.dx !== 'number' || typeof anchor.dy !== 'number') return;
      const ids = L0.edges.filter(e => e.kind === 'wifi' && e.source === pid && groupedIds.has(e.target)).map(e => e.target);
      const prev = groupOrder[pid] || [], order = [...prev.filter(id => ids.includes(id)), ...ids.filter(id => !prev.includes(id)).sort((a, b) => pos[a].y - pos[b].y || pos[a].x - pos[b].x || String(a).localeCompare(String(b)))];
      groupOrder[pid] = order;
      let y = p.y + anchor.dy;
      order.forEach(id => {
        const q = pos[id]; q.x = p.x + anchor.dx; q.y = y;
        let steps = 0; while (blockers.some(b => overlaps(q, b)) && steps++ < 500) q.y += M.NH + M.GAP;
        blockers.push(q); y = q.y + q.h + M.GAP;
      });
    });
    stable.pos = Object.fromEntries(Object.entries(pos).map(([id, p]) => [id, { ...p }])); stable.parents = parent;
    return { ...L0, pos };
}

/* other ways to see the same network (the choice is kept in this browser): a classic top-down tree, rings around the internet / main router, and columns by network.
   They use the same nodes and wires as the default scheme; only the places differ (no rack frames, and dragging cards is for the default scheme). */
const MAP_STYLES = [['columns', 'Схема со шкафом'], ['tree', 'Дерево сверху вниз'], ['radial', 'Кольца вокруг роутера'], ['groups', 'Столбцы по сетям']];

function layoutAlt(data, style, collapsed, remoteOpen) {
  const base = layoutMap(data, collapsed, remoteOpen);
  const nodes = base.nodes;
  const CWA = M.CW + 44;                                              // cards of these views are wider than in the default scheme: long names fit
  const sizeOf = () => [CWA, M.NH];
  const tree = base.edges.filter(e => !e.extra && !e.manual && nodes[e.source] && nodes[e.target]);
  const kids = {}, hasParent = new Set();
  tree.forEach(e => { if (hasParent.has(e.target)) return; hasParent.add(e.target); (kids[e.source] = kids[e.source] || []).push(e.target); });
  const byLabel = (a, b) => String(nodes[a].label).localeCompare(String(nodes[b].label), 'ru');
  Object.values(kids).forEach(l => l.sort((a, b) => (nodes[a].client ? 1 : 0) - (nodes[b].client ? 1 : 0) || byLabel(a, b)));
  const roots = Object.keys(nodes).filter(id => !hasParent.has(id)).sort((a, b) => (a === 'inet' ? -1 : b === 'inet' ? 1 : 0) || (kids[b] || []).length - (kids[a] || []).length);
  const pos = {}; let headers = [];
  if (style === 'tree') {
    const GX = 26, DOWN = 74;
    const cols = n => Math.min(5, Math.max(1, Math.ceil(Math.sqrt(n))));
    const split = id => { const ks = kids[id] || []; return [ks.filter(k => (kids[k] || []).length), ks.filter(k => !(kids[k] || []).length)]; };
    const W = {}, KW = {};
    const measure = id => {
      const [br, lv] = split(id); const bw = br.reduce((s, k) => s + measure(k) + GX, -GX);
      const lw = lv.length ? cols(lv.length) * (CWA + GX) - GX : 0;
      KW[id] = (br.length ? bw : 0) + (br.length && lv.length ? GX * 2 : 0) + lw;
      return W[id] = Math.max(sizeOf(id)[0], KW[id]);
    };
    const place = (id, x0, y) => {
      const [w, h] = sizeOf(id); pos[id] = { x: x0 + (W[id] - w) / 2, y, w, h };
      const [br, lv] = split(id); let x = x0 + (W[id] - KW[id]) / 2; const y2 = y + h + DOWN;
      br.forEach(k => { place(k, x, y2); x += W[k] + GX; });
      if (lv.length) { if (br.length) x += GX; const c = cols(lv.length); lv.forEach((k, i) => { pos[k] = { x: x + (i % c) * (CWA + GX), y: y2 + Math.floor(i / c) * (M.CH + 14), w: CWA, h: M.CH }; }); }
    };
    roots.slice(1).forEach(r => { (kids[roots[0]] = kids[roots[0]] || []).push(r); });          // everything not tied to the top (remote devices …) hangs under it, as a tidy block
    measure(roots[0]); place(roots[0], 0, 0);
  } else if (style === 'radial') {
    const top = roots[0]; roots.slice(1).forEach(r => { (kids[top] = kids[top] || []).push(r); });
    const lc = {}, depth = { [top]: 0 };
    const count = id => lc[id] = (kids[id] || []).length ? (kids[id] || []).reduce((s, k) => { depth[k] = depth[id] + 1; return s + count(k); }, 0) : 1;
    count(top);
    const perDepth = {}; Object.entries(depth).forEach(([id, d]) => { perDepth[d] = (perDepth[d] || 0) + 1; });
    const R = { 0: 0 }; Object.keys(perDepth).map(Number).sort((a, b) => a - b).forEach(d => { if (d) R[d] = Math.max(R[d - 1] + 270, perDepth[d] * (CWA + 26) / (2 * Math.PI)); });
    const put = (id, a0, a1) => {
      const [w, h] = sizeOf(id); const a = (a0 + a1) / 2, r = R[depth[id]] || 0;
      pos[id] = { x: r * Math.cos(a) - w / 2, y: r * Math.sin(a) - h / 2, w, h };
      let s = a0; (kids[id] || []).forEach(k => { const span = (a1 - a0) * lc[k] / lc[id]; put(k, s, s + span); s += span; });
    };
    put(top, -Math.PI / 2, 3 * Math.PI / 2);
  } else {                                                          // groups: the equipment in the first column, then one column per network
    const isInfra = id => !nodes[id].client && nodes[id].kind !== 'group';
    const infra = Object.keys(nodes).filter(isInfra).sort((a, b) => (a === 'inet' ? -1 : b === 'inet' ? 1 : 0) || byLabel(a, b));
    infra.forEach((id, i) => { const [w, h] = sizeOf(id); pos[id] = { x: 0, y: i * (h + M.GAP), w, h }; });
    headers.push({ x: 0, y: -44, w: M.NW, label: 'Оборудование', count: infra.length });
    const segs = {};
    Object.keys(nodes).filter(id => !isInfra(id)).forEach(id => { const s = (nodes[id].segment || (nodes[id].kind === 'group' ? 'Wi-Fi' : 'Без сети')); (segs[s] = segs[s] || []).push(id); });
    let x = M.NW + 90;
    Object.entries(segs).sort((a, b) => b[1].length - a[1].length).forEach(([name, ids]) => {
      ids.sort(byLabel); const per = 14, nc = Math.ceil(ids.length / per);
      ids.forEach((id, i) => { pos[id] = { x: x + Math.floor(i / per) * (CWA + 20), y: (i % per) * (M.CH + 12), w: CWA, h: M.CH }; });
      headers.push({ x, y: -44, w: nc * (CWA + 20) - 20, label: name, count: ids.length }); x += nc * (CWA + 20) + 50;
    });
  }
  Object.keys(nodes).forEach(id => { if (!pos[id]) { const [w, h] = sizeOf(id); pos[id] = { x: 0, y: 2000, w, h }; } });
  const edges = base.edges.filter(e => pos[e.source] && pos[e.target] && (style !== 'groups' || (!nodes[e.source].client && !nodes[e.target].client && nodes[e.target].kind !== 'group')));
  return { nodes, pos, edges, groups: base.groups, hasRack: false, rackNode: {}, racks: [], rooms: base.rooms, style, headers, hiddenClients: base.hiddenClients };
}

/* Orthogonal routing: choose facing card edges and search straight corridors around
   the other cards and rack frames. It is recalculated as cards move. */
function mapOrthogonal(e, L) {
  const a = L.pos[e.source], b = L.pos[e.target]; if (!a || !b) return null;
  const pad = 9, obstacles = Object.entries(L.pos).filter(([id]) => id !== e.source && id !== e.target).map(([, p]) =>
    ({ l: p.x - pad, r: p.x + p.w + pad, t: p.y - pad, b: p.y + p.h + pad }));
  (L.racks || []).filter(r => r.id !== a.rackId && r.id !== b.rackId).forEach(r => obstacles.push({ l: -23, r: r.w + 23, t: r.y - 55, b: r.y + r.h + 23 }));
  const blocked = (p, q, o) => p.x === q.x ? p.x > o.l && p.x < o.r && Math.max(Math.min(p.y, q.y), o.t) < Math.min(Math.max(p.y, q.y), o.b)
    : p.y === q.y ? p.y > o.t && p.y < o.b && Math.max(Math.min(p.x, q.x), o.l) < Math.min(Math.max(p.x, q.x), o.r) : true;
  const clean = pts => pts.filter((p, i) => !i || p.x !== pts[i - 1].x || p.y !== pts[i - 1].y);
  const port = (p, side) => side === 'left' ? { x: p.x, y: p.y + p.h / 2, dx: -1, dy: 0 }
    : side === 'right' ? { x: p.x + p.w, y: p.y + p.h / 2, dx: 1, dy: 0 }
    : side === 'top' ? { x: p.x + p.w / 2, y: p.y, dx: 0, dy: -1 }
    : { x: p.x + p.w / 2, y: p.y + p.h, dx: 0, dy: 1 };
  const ac = { x: a.x + a.w / 2, y: a.y + a.h / 2 }, bc = { x: b.x + b.w / 2, y: b.y + b.h / 2 };
  const sidesA = a.rack ? [bc.x < ac.x ? 'left' : 'right', bc.x < ac.x ? 'right' : 'left']
    : [bc.x < ac.x ? 'left' : 'right', bc.y < ac.y ? 'top' : 'bottom'];
  const sidesB = b.rack ? [ac.x < bc.x ? 'left' : 'right', ac.x < bc.x ? 'right' : 'left']
    : [ac.x < bc.x ? 'left' : 'right', ac.y < bc.y ? 'top' : 'bottom'];
  let best = null, fallback = null;
  const finish = result => { const pts = result.pts, mid = pts[Math.floor((pts.length - 1) / 2)], near = pts[Math.max(0, pts.length - 2)];
    return { d: pts.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' '), lx: near.x, ly: near.y, mx: mid.x, my: mid.y,
      inside: !!(a.rack && b.rack), cross: !!(a.rack && b.rack && a.rackId !== b.rackId) }; };
  const sourceBox = { l: a.x, r: a.x + a.w, t: a.y, b: a.y + a.h }, targetBox = { l: b.x, r: b.x + b.w, t: b.y, b: b.y + b.h };
  const nearOptimal = () => best && best.score <= Math.abs(ac.x - bc.x) + Math.abs(ac.y - bc.y) + 160;
  const consider = raw => {
    const pts = clean(raw); let collisions = 0, length = 0;
    for (let i = 1; i < pts.length; i++) { const p = pts[i - 1], q = pts[i]; length += Math.abs(p.x - q.x) + Math.abs(p.y - q.y); for (const o of obstacles) if (blocked(p, q, o)) collisions++;
      if (i > 1 && blocked(p, q, sourceBox)) collisions++; if (i < pts.length - 1 && blocked(p, q, targetBox)) collisions++; }
    const score = length + pts.length * 14;
    if (!collisions && (!best || score < best.score)) best = { pts, score };
    if (!fallback || collisions < fallback.collisions || (collisions === fallback.collisions && score < fallback.score)) fallback = { pts, score, collisions };
  };
  const endpoints = [];
  for (const sa of sidesA) for (const sb of sidesB) {
    const p = port(a, sa), q = port(b, sb), start = { x: p.x + p.dx * 16, y: p.y + p.dy * 16 }, end = { x: q.x + q.dx * 16, y: q.y + q.dy * 16 };
    const nearby = obstacles.slice().sort((u, v) => {
      const dist = o => Math.max(0, o.l - Math.max(start.x, end.x), Math.min(start.x, end.x) - o.r) + Math.max(0, o.t - Math.max(start.y, end.y), Math.min(start.y, end.y) - o.b);
      return dist(u) - dist(v);
    }).slice(0, 12);
    const xs = [...new Set([(start.x + end.x) / 2, ...nearby.flatMap(o => [o.l - 3, o.r + 3]), Math.min(start.x, end.x, ...obstacles.map(o => o.l)) - 20, Math.max(start.x, end.x, ...obstacles.map(o => o.r)) + 20])];
    const ys = [...new Set([(start.y + end.y) / 2, ...nearby.flatMap(o => [o.t - 3, o.b + 3]), Math.min(start.y, end.y, ...obstacles.map(o => o.t)) - 20, Math.max(start.y, end.y, ...obstacles.map(o => o.b)) + 20])];
    const head = { x: p.x, y: p.y }, tail = { x: q.x, y: q.y };
    consider([head, start, { x: end.x, y: start.y }, end, tail]); if (nearOptimal()) return finish(best);
    consider([head, start, { x: start.x, y: end.y }, end, tail]); if (nearOptimal()) return finish(best);
    for (const x of xs) { consider([head, start, { x, y: start.y }, { x, y: end.y }, end, tail]); if (nearOptimal()) return finish(best); }
    for (const y of ys) { consider([head, start, { x: start.x, y }, { x: end.x, y }, end, tail]); if (nearOptimal()) return finish(best); }
    endpoints.push({ head, tail, start, end, xs, ys });
  }
  // More crowded layouts sometimes need two corridors, not one.
  if (!best) for (const z of endpoints) for (const x of z.xs.slice(0, 12)) for (const y of z.ys.slice(0, 12)) {
    consider([z.head, z.start, { x, y: z.start.y }, { x, y }, { x: z.end.x, y }, z.end, z.tail]);
    consider([z.head, z.start, { x: z.start.x, y }, { x, y }, { x, y: z.end.y }, z.end, z.tail]);
  }
  return finish(best || fallback);
}

function edgePath(e, L, wireStyle = 'curved') {
  const a = L.pos[e.source], b = L.pos[e.target];
  if (!a || !b) return null;
  if (wireStyle === 'orthogonal') return mapOrthogonal(e, L);
  if (wireStyle === 'straight' && !(a.rack && b.rack) && !((e.source === 'inet' || (L.nodes[e.source] || {}).wan) && b.rack && !a.rack)) {
    const acx = a.x + a.w / 2, acy = a.y + a.h / 2, bcx = b.x + b.w / 2, bcy = b.y + b.h / 2;
    const horizontal = a.rack || b.rack || Math.abs(bcx - acx) >= Math.abs(bcy - acy);
    const sx = horizontal ? (bcx >= acx ? a.x + a.w : a.x) : acx;
    const sy = horizontal ? acy : (bcy >= acy ? a.y + a.h : a.y);
    const tx = horizontal ? (bcx >= acx ? b.x : b.x + b.w) : bcx;
    const ty = horizontal ? bcy : (bcy >= acy ? b.y : b.y + b.h);
    return { d: `M${sx},${sy} L${tx},${ty}`, lx: sx * .35 + tx * .65, ly: sy * .35 + ty * .65, mx: (sx + tx) / 2, my: (sy + ty) / 2 };
  }
  if (L.style === 'tree') {                                           // from the bottom of the parent to the top of the child
    const ax = a.x + a.w / 2, ay = a.y + a.h, bx = b.x + b.w / 2, by = b.y, my = (ay + by) / 2;
    if (by > ay + 4) return { d: `M${ax},${ay} C${ax},${my} ${bx},${my} ${bx},${by}`, lx: bx, ly: by - 18, mx: bx, my };
    const ay2 = a.y + a.h / 2, by2 = b.y + b.h / 2;                    // side by side / the other way round: connect the sides
    const sx = b.x > a.x ? a.x + a.w : a.x, tx = b.x > a.x ? b.x : b.x + b.w;
    return { d: `M${sx},${ay2} C${(sx + tx) / 2},${ay2} ${(sx + tx) / 2},${by2} ${tx},${by2}`, lx: tx, ly: by2, mx: (sx + tx) / 2, my: (ay2 + by2) / 2 };
  }
  if (L.style === 'radial') {                                          // straight spokes between centres, the cards sit on top
    const ax = a.x + a.w / 2, ay = a.y + a.h / 2, bx = b.x + b.w / 2, by = b.y + b.h / 2;
    return { d: `M${ax},${ay} L${bx},${by}`, lx: ax + (bx - ax) * .66, ly: ay + (by - ay) * .66, mx: (ax + bx) / 2, my: (ay + by) / 2 };
  }
  if (a.rack && b.rack) {            // both in a rack: patch cable (same rack) or backbone (between racks)
    const y1 = a.y + a.h / 2, y2 = b.y + b.h / 2, cross = a.rackId !== b.rackId;
    const d = cross ? 80 + Math.min(130, Math.abs(y2 - y1) * .12) : 26 + Math.min(70, Math.abs(y2 - y1) * .18);
    const mx = Math.min(a.x, b.x) - d;                       // out of the frame on the left and back in
    return { d: `M${a.x},${y1} C${mx},${y1} ${mx},${y2} ${b.x},${y2}`, lx: mx + 8, ly: (y1 + y2) / 2, inside: true, cross };
  }
  if (!a.rack && !b.rack && b.y >= a.y + a.h && b.x < a.x + a.w && b.x + b.w > a.x) {   // straight down (internet → ONT above the rack)
    const x = (Math.max(a.x, b.x) + Math.min(a.x + a.w, b.x + b.w)) / 2, y1 = a.y + a.h, y2 = b.y;
    return { d: `M${x},${y1} L${x},${y2}`, lx: x + 34, ly: (y1 + y2) / 2 + 4 };
  }
  if ((e.source === 'inet' || (L.nodes[e.source] || {}).wan) && b.rack && !a.rack) {
    const sx = a.x + a.w / 2, sy = a.y + a.h, ty = b.y + b.h / 2, tx = (L.racks.find(r => r.id === b.rackId) || {}).w || b.x + b.w;
    const lane = tx + 34;                                                     // run down a lane beside the rack, not across its face
    if (ty - sy > 160) {
      const y1 = sy + 60;
      return { d: `M${sx},${sy} C${sx},${y1 - 10} ${lane},${sy + 10} ${lane},${y1 + 30} L${lane},${ty - 22} Q${lane},${ty} ${tx + 2},${ty}`,
        lx: lane + 26, ly: y1 + 40 };
    }
    return { d: `M${sx},${sy} C${sx},${sy + 60} ${tx + 70},${ty - 40} ${tx + 2},${ty}`, lx: tx + 34, ly: (sy + ty) / 2 };
  }
  if (e.source === 'inet' && b.x + b.w <= a.x) {      // remote device to the left of the internet node
    const sx = a.x, sy = a.y + a.h / 2, tx = b.x + b.w, ty = b.y + b.h / 2;
    return { d: `M${sx},${sy} C${sx - 60},${sy} ${tx + 60},${ty} ${tx},${ty}`, lx: (sx + tx) / 2, ly: (sy + ty) / 2 - 8 };
  }
  if (e.source === 'inet') {
    const sx = a.x + a.w, sy = a.y + a.h / 2, tx = b.x, ty = b.y + b.h / 2;
    if (Math.abs(sy - ty) < 4) return { d: `M${sx},${sy} L${tx},${ty}`, lx: (sx + tx) / 2, ly: sy - 8 };
    return { d: `M${a.x + a.w / 2},${a.y + a.h} C${a.x + a.w / 2},${ty} ${tx - 60},${ty} ${tx},${ty}`, lx: tx - 40, ly: ty - 8 };
  }
  const sx = a.x + a.w, sy = a.y + a.h / 2, tx = b.x, ty = b.y + b.h / 2;
  if (tx < sx) {                     // choose facing edges when the target is moved left
    if (b.x + b.w <= a.x) {
      const from = a.x, to = b.x + b.w, dx = Math.max(25, (from - to) * .45);
      return { d: `M${from},${sy} C${from - dx},${sy} ${to + dx},${ty} ${to},${ty}`, lx: to + 22, ly: ty, mx: (from + to) / 2, my: (sy + ty) / 2 };
    }
    const ax = a.x + a.w / 2, bx = b.x + b.w / 2, down = b.y >= a.y;
    const ay = down ? a.y + a.h : a.y, by = down ? b.y : b.y + b.h, mid = (ay + by) / 2;
    return { d: `M${ax},${ay} C${ax},${mid} ${bx},${mid} ${bx},${by}`, lx: (ax + bx) / 2, ly: mid };
  }
  const dx = Math.max(50, (tx - sx) * .5);
  return { d: `M${sx},${sy} C${sx + dx},${sy} ${tx - dx},${ty} ${tx},${ty}`, lx: tx - 22, ly: ty, mx: (sx + tx) / 2, my: (sy + ty) / 2 };
}

function MapNode({ n, p, sel, dim, mark, phase, onDown, onClick, onDoubleClick }) {
  const { data } = useApp(); const spec = (data.icons || {})[n.id];            // the icon chosen by hand («Иконка» in the node card), if any
  const small = n.kind === 'group' || n.client;
  const iconKind = n.kind === 'group' ? 'wifi' : n.kind;
  const c = kindColor(iconKind);
  const is = small ? 28 : 34;
  const pw = n.remoteClients ? 24 + String(n.remoteClients).length * 7 : 0;            // the pill «‹ 3» of a remote device
  const room = p.w - (is + 18) - 24, capL = Math.max(8, Math.floor(room / 7.4)), capS = Math.max(10, Math.floor(room / 6.2)) - (n.remoteClients ? Math.ceil((pw - 6) / 6.2) : 0);      // characters that fit the card (the other map views have wider cards)
  const nm = (data.labels || {})[n.id] || n.label;       // подпись, заданная вручную на карте; иначе имя из сети
  const cc = flagOf(nm);            // a name starting with «🇩🇪 …» or «/abh …»: the picture of the flag instead of the icon, the name without the prefix
  const [badFlag, setBadFlag] = useState('');
  const brand = tagBrand(nm) || (!spec ? brandOf(nm, n.kind, n.mac || (String(n.id).startsWith('h:') ? String(n.id).slice(2) : '')) : ''), B = brand && BRANDS[brand];            // the maker's logo (01_brands.jsx) when the name says whose device it is
  const role = B ? tagRole(nm) : '';            // «/ap/keenetic …»: логотип Keenetic со значком AP
  const flag = cc && badFlag !== cc, label = nameNoFlag(nm, n.kind), clipId = 'fc-' + String(n.id).replace(/[^\w-]/g, '_');
  return <g className={'node' + (small ? ' client' : '') + (n.kind === 'group' ? ' group' : '') + (sel ? ' sel' : '') + (dim ? ' dim-out' : '')}
    transform={`translate(${p.x},${p.y})`} onPointerDown={onDown} onClick={onClick} onDoubleClick={onDoubleClick}>
    {mark ? <rect className="spof-mark" x={-5} y={-5} width={p.w + 10} height={p.h + 10} rx={small ? 16 : 19} /> : null}
    <title>{[label, n.sub, n.remoteClients ? (n.remoteOpen ? 'нажмите — скрыть подключённых' : 'нажмите — показать подключённых') + ', дважды — открыть карточку' : ''].filter(Boolean).join(' · ')}</title>
    <g className={phase ? 'pop-' + phase : undefined} style={phase === 'in' ? { animationDelay: Math.min(8, n.remoteIdx || 0) * 45 + 'ms' } : undefined}>
    <rect className="box" width={p.w} height={p.h} rx={small ? 12 : 15} />
    {n.room ? <g transform="translate(10,-9)"><rect width={Math.min(p.w - 20, 14 + n.room.length * 6.4)} height={15} rx={7.5} className="room-tag" />
      <text x={7} y={11} className="room-tag-t">{trunc(n.room, Math.floor((p.w - 34) / 6.4))}</text></g> : null}
    {flag ? <g>
      <clipPath id={clipId}><rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} /></clipPath>
      <image href={'/flags/' + cc + '.svg'} x={9} y={(p.h - is) / 2} width={is} height={is} preserveAspectRatio="xMidYMid slice" clipPath={`url(#${clipId})`} onError={() => setBadFlag(cc)} />
      <rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} fill="none" stroke="var(--text)" strokeOpacity=".16" /></g>
    : B ? <g>
      <rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} fill={B.c} />
      {B.d ? <path d={B.d} fill={B.i} transform={`translate(${9 + is * .2},${(p.h - is) / 2 + is * .2}) scale(${is * .6 / 24})`} />
        : <text x={9 + is / 2} y={p.h / 2} textAnchor="middle" dominantBaseline="central" fill={B.i} fontSize={brandTextSize(B.t) * is} fontWeight="800" style={{ letterSpacing: '-.02em' }}>{B.t}</text>}
      <rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} fill="none" stroke="var(--text)" strokeOpacity=".16" />
      {role ? <g transform={`translate(${9 + is - Math.max(16, 7 + role.length * 6) + 5},${(p.h - is) / 2 + is - 9})`}>
        <rect width={Math.max(16, 7 + role.length * 6)} height={13} rx={6.5} fill="var(--card-solid, #fff)" stroke={B.c} strokeWidth="1.2" />
        <text x={Math.max(16, 7 + role.length * 6) / 2} y={9.6} textAnchor="middle" fontSize="8.5" fontWeight="800" fill={B.c}>{role}</text></g> : null}</g>
    : <>
      <rect x={9} y={(p.h - is) / 2} width={is} height={is} rx={9} fill={c} opacity=".16" />
      {isUpIcon(spec) ? <g transform={`translate(${9 + is * .12},${(p.h - is) / 2 + is * .12})`}><NodeGlyph svg spec={spec} kind={iconKind} size={is * .76} color={c} /></g>
        : <g transform={`translate(${9 + is * .2},${(p.h - is) / 2 + is * .2})`}><NodeGlyph svg spec={spec} kind={iconKind} size={is * .6} color={c} /></g>}</>}
    <text className="lbl" x={is + 18} y={n.sub || n.kind === 'group' ? p.h / 2 - 3 : p.h / 2 + 4}>{trunc(label, capL)}</text>
    {n.kind === 'group' ? <text className="sub" x={is + 18} y={p.h / 2 + 12}>нажмите, чтобы раскрыть</text>
      : n.sub ? <text className="sub" x={is + 18} y={p.h / 2 + 13}>{trunc(n.sub, capS)}</text> : null}
    {n.remoteClients ? <g className={'rc-pill' + (n.remoteOpen ? ' open' : '')} transform={`translate(${p.w - pw - 8},${p.h - 22})`}>
      <rect width={pw} height={16} rx={8} />
      <g transform="translate(9.5,8)"><path className="rc-chev" d="M1.6,-3.6 L-2.2,0 L1.6,3.6" /></g>
      <text x={pw - 7} y={11.8} textAnchor="end">{n.remoteClients}</text></g> : null}
    {n.status && n.kind !== 'group' ? <circle cx={p.w - 13} cy={13} r={4.5} fill={n.status === 'online' ? 'var(--green)' : n.status === 'warning' ? 'var(--orange)' : n.status === 'offline' ? 'var(--red)' : 'var(--text3)'} /> : null}
    </g>
  </g>;
}
const trunc = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

const MAP_GRID = 20;
/* «Сеть дома»: та же карта сети, но только то, что стоит в доме — его устройства и шкафы, их клиенты (на один-два шага вниз) и вся цепочка вверх до роутера и интернета.
   seed = { devices: Set(id устройств), racks: Set(id шкафов/мест) }; расположение берётся из общей схемы, поэтому узлы стоят там же, где на «Карте сети». */
function scopeData(data, seed) {
  const topo = data.topology || { nodes: [], edges: [] };
  const racks = (data.racks || []).filter(r => seed.racks.has(r.id));
  const devIds = new Set(seed.devices);
  racks.forEach(r => (r.units || []).forEach(u => unitDevIds(u).forEach(id => devIds.add(id))));
  const keep = new Set();
  topo.nodes.forEach(n => { if (String(n.id).startsWith('d:') && devIds.has(String(n.id).slice(2))) keep.add(n.id); });
  racks.forEach(r => (r.units || []).forEach(u => { if (!unitDevIds(u).length) keep.add('u:' + u.id); }));
  const tree = topo.edges.filter(e => !e.extra && !e.manual), par = {};
  tree.forEach(e => { par[e.target] = e.source; });
  let down = new Set(keep);
  for (let depth = 0; depth < 2; depth++) {                                    // клиенты и подключённое ниже: два шага
    const nxt = new Set(); tree.forEach(e => { if (down.has(e.source) && !keep.has(e.target)) { keep.add(e.target); nxt.add(e.target); } }); down = nxt; }
  [...keep].forEach(id => { let p = par[id], n = 0; while (p && n++ < 40) { keep.add(p); p = par[p]; } });             // вверх — до роутера и интернета
  const edges = topo.edges.filter(e => keep.has(e.source) && keep.has(e.target));
  return { ...data, topology: { ...topo, nodes: topo.nodes.filter(n => keep.has(n.id)), edges }, racks };
}

/* Local view omits remote branches before layout, including their clients and rack slots. */
function localMapData(data) {
  const topo = data.topology || { nodes: [], edges: [] };
  const hidden = new Set(topo.nodes.filter(n => n.remote).map(n => n.id));
  let changed = true;
  while (changed) {
    changed = false;
    topo.edges.forEach(e => { if (!e.extra && !e.manual && hidden.has(e.source) && e.target !== 'inet' && !hidden.has(e.target)) { hidden.add(e.target); changed = true; } });
  }
  const racks = (data.racks || []).map(r => ({ ...r, units: r.units.filter(u => { const ids = unitDevIds(u); return !ids.length || ids.some(id => !hidden.has('d:' + id)); }).map(u => ({ ...u,
    deviceIds: u.deviceIds?.filter(id => !hidden.has('d:' + id)), deviceId: hidden.has('d:' + u.deviceId) ? null : u.deviceId })) }));
  return { ...data, racks: racks.filter((r, i) => r.units.length || !data.racks[i].units.length), topology: { ...topo,
    nodes: topo.nodes.filter(n => !hidden.has(n.id)), edges: topo.edges.filter(e => !hidden.has(e.source) && !hidden.has(e.target)) } };
}

function MapView({ scope }) {
  const { data: dataAll, edit, openDevice, saveMap } = useApp();
  const [showRemote, setShowRemote] = useState(false);
  const [allWifi, setAllWifi] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testParent, setTestParent] = useState('');
  const [testPick, setTestPick] = useState('all');
  const [testClients, setTestClients] = useState([]);
  const testSeq = useRef(0);
  const testFocus = useRef(null);
  useEffect(() => { if (!edit) { setTestClients([]); setTestPick('all'); setTestOpen(false); testFocus.current = null; } }, [edit]);
  const data = useMemo(() => {
    const base = scope ? scopeData(dataAll, scope.seed) : showRemote ? dataAll : localMapData(dataAll);
    if (!testClients.length) return base;
    const t = base.topology || { nodes: [], edges: [] }, valid = new Set(t.nodes.map(n => n.id));
    const fakes = testClients.filter(c => valid.has(c.parent));
    return { ...base, topology: { ...t, nodes: [...t.nodes, ...fakes.map(c => ({ id: c.id, label: c.label, sub: 'тестовый клиент', kind: 'other', status: 'online', client: true, phantom: true }))],
      edges: [...t.edges, ...fakes.map(c => ({ id: 'test-edge:' + c.id, source: c.parent, target: c.id, kind: 'wifi', phantom: true }))] } };
  }, [dataAll, scope && scope.key, showRemote, testClients]);
  const toast = useToast(); const confirm = useConfirm();
  const [collapsed, setCollapsed] = useState(data.map.collapsed || {});
  const [remoteOpenIds, setRemoteOpenIds] = useState({});  // the remote devices showing who is connected to them; closed again after a reload
  const [closingIds, setClosingIds] = useState({});        // just closed: their clients are still drawn for a moment, flying back into the device
  const remoteOpen = useMemo(() => scope ? true : { ...remoteOpenIds, ...closingIds }, [scope, remoteOpenIds, closingIds]);   // the map of one house is about that place: everything is shown
  const openIdsRef = useRef(remoteOpenIds); openIdsRef.current = remoteOpenIds;
  const revealRef = useRef(null);                          // the device just opened: the map glides so its clients are on the screen
  const [view, setView] = useState(null);                 // {x, y, k}
  const [sel, setSel] = useState(null);
  /* одно касание устройства только выделяет его (путь до интернета подсвечен), карточка внизу открывается вторым касанием того же устройства:
     раньше карточка выскакивала от любого случайного касания при перемещении по карте и закрывала её */
  const [info, setInfo] = useState(null);
  const openInfo = id => { setSel(id); setInfo(id); };
  useEffect(() => { if (info && info !== sel) setInfo(null); }, [sel]);
  const [linking, setLinking] = useState(null);           // null | 'pick' | nodeId
  const [q, setQ] = useState('');
  const [dragPos, setDragPos] = useState({});
  const [guides, setGuides] = useState(null);             // {x, y}: alignment lines shown while a card is dragged
  const [healthOpen, setHealthOpen] = useState(() => lsGet('rl_health', '') === '1' || new URLSearchParams(location.search).has('analysis'));
  useEffect(() => { lsSet('rl_health', healthOpen ? '1' : ''); }, [healthOpen]);
  const spofSet = healthOpen && data.health ? new Set(data.health.spof.filter(s => s.affected >= 3).map(s => s.id)) : null;
  const openCheck = useCheckOpener();
  const wrap = useRef(null); useFillScreen(wrap);
  const [wireStyle, setWireStyle] = useState(() => { const v = lsGet('rl_map_wire_style', 'curved'); return ['curved', 'straight', 'orthogonal'].includes(v) ? v : 'curved'; });
  const [style, setStyle] = useState(() => { const v = new URLSearchParams(location.search).get('mapstyle') || lsGet('rl_map_style', 'columns'); return MAP_STYLES.some(x => x[0] === v) ? v : 'columns'; });
  const stableRef = useRef(null);
  if (!stableRef.current) {
    let saved = {}; try { saved = JSON.parse(lsGet('rl_map_wifi_roaming_v1', '{}')); } catch (_) { /* first visit */ }
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) saved = {};
    stableRef.current = { pos: {}, parents: {}, wifiSeen: saved.seen && typeof saved.seen === 'object' ? saved.seen : {},
      autoWifi: saved.auto && typeof saved.auto === 'object' ? saved.auto : {}, autoGroups: saved.groups && typeof saved.groups === 'object' ? saved.groups : {},
      groupOptOut: saved.optOut && typeof saved.optOut === 'object' ? saved.optOut : {}, autoOpen: {}, autoSuppress: false };
  }
  const groupOrderRef = useRef({});
  const wifiCollapsed = useMemo(() => {
    const out = allWifi ? Object.fromEntries((data.topology?.edges || []).filter(e => e.kind === 'wifi').map(e => [e.source, false])) : { ...collapsed };
    const associations = mapWifiParents(data), memory = stableRef.current;
    Object.entries(associations).forEach(([id, pid]) => {
      if (memory.wifiSeen[id] && memory.wifiSeen[id] !== pid) { memory.autoOpen[pid] = true; memory.autoOpen[memory.wifiSeen[id]] = true; memory.autoSuppress = false; }
      if (memory.autoWifi[id]) memory.autoOpen[pid] = true;
    });
    if (!memory.autoSuppress) {
      Object.keys(memory.autoOpen).forEach(id => { out[id] = false; });
      Object.keys({ ...memory.autoGroups, ...(data.map.wifiGroups || {}) }).forEach(id => { out[id] = false; });
    }
    testClients.forEach(c => { out[c.parent] = false; });
    return out;
  }, [data, collapsed, allWifi, testClients]);
  const L0 = useMemo(() => style !== 'columns' ? layoutAlt(data, style, wifiCollapsed, remoteOpen) : layoutMap(data, wifiCollapsed, remoteOpen), [data, wifiCollapsed, style, remoteOpen]);       // раскладка считается один раз, а не на каждое движение карточки
  const L = useMemo(() => placeStableMap(L0, data, dragPos, style, stableRef.current, groupOrderRef.current), [L0, dragPos, style, data.map]);

  const lastWifiSaved = useRef('');
  useEffect(() => {
    const memory = stableRef.current, raw = JSON.stringify({ seen: memory.wifiSeen || {}, auto: memory.autoWifi || {}, groups: memory.autoGroups || {}, optOut: memory.groupOptOut || {} });
    if (raw !== lastWifiSaved.current) { lsSet('rl_map_wifi_roaming_v1', raw); lastWifiSaved.current = raw; }
  }, [L]);

  const edgeGeometry = useMemo(() => new Map(L.edges.map(e => [e.id, edgePath(e, L, wireStyle)])), [L, wireStyle]);

  const bbox = () => {
    const ps = Object.values(L.pos); if (!ps.length) return { x: 0, y: 0, w: 100, h: 100 };
    const rackBottom = Math.max(0, ...(L.racks || []).map(r => r.y + (r.h || 0)));   // include empty racks
    const x1 = Math.min(L.style ? Infinity : -110, ...ps.map(p => p.x)) - 20, y1 = Math.min(L.style ? (L.headers && L.headers.length ? -44 : Infinity) : -60, ...ps.map(p => p.y)) - 20;
    const x2 = Math.max(...ps.map(p => p.x + p.w)) + 20, y2 = Math.max(rackBottom, ...ps.map(p => p.y + p.h)) + 30;
    return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
  };
  const fit = () => {
    const el = wrap.current; if (!el) return; const b = bbox();
    const off = healthOpen && el.clientWidth > 760 ? 424 : 0;      // keep the map clear of the analysis panel
    const W = el.clientWidth - off, H = el.clientHeight;
    const k = Math.min(1.2, Math.max(.2, Math.min(W / (b.w + 60), H / (b.h + 60))));
    setView({ k, x: off + (W - b.w * k) / 2 - b.x * k, y: (H - b.h * k) / 2 - b.y * k });
  };
  useEffect(() => { if (!view) fit(); }, [L]);
  useEffect(() => { if (view) fit(); }, [healthOpen]);
  const [focus, setFocus] = useState(null);               // a room picked in «Шкафы и места»: its devices lit up
  const focusRoom = rm => {
    const ps = rm.ids.map(id => L.pos[id]).filter(Boolean);
    if (!ps.length) { toast(rm.units ? `В «${rm.name}» нет устройств, которые можно показать: они не привязаны или уже стоят в шкафу` : `«${rm.name}» пока пустая — добавьте оборудование на «Главной»`, true); return; }
    const el = wrap.current; const W = el.clientWidth, H = el.clientHeight;
    const x1 = Math.min(...ps.map(p => p.x)), y1 = Math.min(...ps.map(p => p.y)), x2 = Math.max(...ps.map(p => p.x + p.w)), y2 = Math.max(...ps.map(p => p.y + p.h));
    const k = Math.min(1.1, Math.max(.3, Math.min((W - 120) / (x2 - x1 + 1), (H - 160) / (y2 - y1 + 1))));
    setView({ k, x: W / 2 - (x1 + x2) / 2 * k, y: H / 2 - (y1 + y2) / 2 * k }); setSel(null); setFocus(new Set(rm.ids));
  };
  const focusRack = rk => {                                 // centre the map on one rack (quick jump when there are many)
    const el = wrap.current; if (!el) return; const W = el.clientWidth, H = el.clientHeight; const rh = rk.h || rk.rows * M.RU;
    const k = Math.min(1.15, Math.max(.3, (H - 130) / (rh + 110)));
    setView({ k, x: W * 0.36 - ((rk.w || M.RW) / 2) * k, y: H / 2 - (rk.y + rh / 2) * k }); setSel(null);
  };

  // pan / zoom / pinch. The gesture baseline is re-captured whenever the number of fingers changes,
  // so lifting one finger after a pinch no longer snaps the map back.
  const ptrs = useRef({}); const panRef = useRef(null); const viewRef = useRef(view); viewRef.current = view;
  const clampK = k => Math.min(4, Math.max(.12, k));
  /* пока карту двигают или масштабируют двумя пальцами, перерисовывается только преобразование слоя (по кадру), а React-состояние обновляется один раз — когда отпустили:
     раньше каждое движение пальца заново строило все карточки и линии */
  const gRef = useRef(null); const liveV = useRef(null); const rafRef = useRef(0);
  const applyView = nv => {
    liveV.current = nv;
    if (wrap.current) wrap.current.classList.add('moving');
    if (!rafRef.current) rafRef.current = requestAnimationFrame(() => { rafRef.current = 0; const v = liveV.current; if (!v) return;
      const tr = `translate(${v.x},${v.y}) scale(${v.k})`;
      if (gRef.current) gRef.current.setAttribute('transform', tr);
      const gp = document.getElementById('mapgrid'); if (gp) gp.setAttribute('patternTransform', tr); });
  };
  const animRef = useRef(0); const animV = useRef(null);
  const stopGlide = () => { if (!animRef.current) return; cancelAnimationFrame(animRef.current); animRef.current = 0; if (animV.current) { viewRef.current = animV.current; setView(animV.current); } };   // a finger on the map stops the glide where it is
  const glideTo = to => {                                   // a smooth move of the map (only the layer's transform per frame, the state once at the end)
    const from = viewRef.current; cancelAnimationFrame(animRef.current);
    if (!from || matchMedia('(prefers-reduced-motion: reduce)').matches) { setView(to); return; }
    const t0 = performance.now(), dur = 380;
    const step = now => { const t = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - t, 3);
      const v = { k: from.k + (to.k - from.k) * e, x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e };
      const tr = `translate(${v.x},${v.y}) scale(${v.k})`; animV.current = v;
      if (gRef.current) gRef.current.setAttribute('transform', tr);
      const gp = document.getElementById('mapgrid'); if (gp) gp.setAttribute('patternTransform', tr);
      if (t < 1) animRef.current = requestAnimationFrame(step); else { animRef.current = 0; setView(to); } };
    animRef.current = requestAnimationFrame(step);
  };
  const toggleRemote = id => {
    if (openIdsRef.current[id]) {
      setRemoteOpenIds(o => { const c = { ...o }; delete c[id]; return c; });
      setClosingIds(c => ({ ...c, [id]: true }));
      setTimeout(() => setClosingIds(c => { const x = { ...c }; delete x[id]; return x; }), 260);
    } else {
      setRemoteOpenIds(o => ({ ...o, [id]: true })); revealRef.current = id;
      if (!lsGet('rl_remote_hint', '')) { lsSet('rl_remote_hint', '1'); toast('Дважды нажмите на устройство, чтобы открыть его карточку'); }
    }
  };
  useEffect(() => {                                         // after opening: if its clients went past the edge, glide so the device and its clients are in sight
    const id = revealRef.current; revealRef.current = null; const el = wrap.current; const v = viewRef.current;
    if (!id || !el || !v) return;
    const ps = Object.values(L.nodes).filter(n => n.id === id || n.remoteOf === id).map(n => L.pos[n.id]).filter(Boolean); if (ps.length < 2) return;
    const W = el.clientWidth, H = el.clientHeight, pad = 36, top = 70;
    const x1 = Math.min(...ps.map(p => p.x)), y1 = Math.min(...ps.map(p => p.y)), x2 = Math.max(...ps.map(p => p.x + p.w)), y2 = Math.max(...ps.map(p => p.y + p.h));
    let k = v.k, x = v.x, y = v.y;
    const kFit = Math.min((W - 2 * pad) / (x2 - x1), (H - top - pad) / (y2 - y1));
    if (kFit < k) { k = Math.max(.2, kFit); x = W / 2 - (x1 + x2) / 2 * k; y = top + (H - top - pad) / 2 - (y1 + y2) / 2 * k; }
    else {
      const sx1 = x1 * k + x, sx2 = x2 * k + x, sy1 = y1 * k + y, sy2 = y2 * k + y;
      if (sx1 < pad) x += pad - sx1; else if (sx2 > W - pad) x -= sx2 - (W - pad);
      if (sy1 < top) y += top - sy1; else if (sy2 > H - pad) y -= sy2 - (H - pad);
    }
    if (Math.abs(x - v.x) > 1 || Math.abs(y - v.y) > 1 || Math.abs(k - v.k) > .001) glideTo({ k, x, y });
  }, [L]);
  useEffect(() => {
    const pid = testFocus.current, el = wrap.current, v = viewRef.current;
    if (!pid || !el || !v) return;
    const clients = testClients.filter(c => c.parent === pid).map(c => L.pos[c.id]).filter(Boolean);
    const parent = L.pos[pid]; if (!clients.length || !parent) return;
    testFocus.current = null;
    const points = [parent, ...clients], x1 = Math.min(...points.map(p => p.x)), x2 = Math.max(...points.map(p => p.x + p.w));
    const y1 = Math.min(...points.map(p => p.y)), y2 = Math.max(...points.map(p => p.y + p.h));
    const W = el.clientWidth, H = el.clientHeight, k = Math.min(v.k, Math.max(.2, Math.min((W - 50) / (x2 - x1 + 1), (H - 70) / (y2 - y1 + 1))));
    glideTo({ k, x: W / 2 - (x1 + x2) / 2 * k, y: H / 2 - (y1 + y2) / 2 * k });
  }, [L, testClients]);
  // viewRef is set at once: the next wheel / finger event may come before React re-renders, and then it must not start from the old view (that was the jump back)
  const commitView = () => { if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; } if (liveV.current) { viewRef.current = liveV.current; setView(liveV.current); liveV.current = null; } if (wrap.current) wrap.current.classList.remove('moving'); };
  const baseline = () => {
    stopGlide(); const pts = Object.values(ptrs.current); const v = { ...(liveV.current || viewRef.current) };
    if (!pts.length) return null;
    if (pts.length >= 2) { const r = wrap.current.getBoundingClientRect();
      return { pinch: true, dist: Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) || 1, cx: (pts[0].x + pts[1].x) / 2 - r.left, cy: (pts[0].y + pts[1].y) / 2 - r.top, v }; }
    return { pinch: false, sx: pts[0].x, sy: pts[0].y, v };
  };
  const panMoved = useRef(false);
  const bgTap = useRef(false);                              // одно касание пустого места: выделение снимается только когда палец отпустили, не сдвинув карту
  const onBgDown = e => {
    const onItem = !!e.target.closest('.node, .rackbox .u, .edge-hit');
    if (e.button > 0) return;                                                // right / middle button: not a pan (the context menu swallowed the release and the map then followed the mouse)
    if (onItem && (edit || linking)) return;                                 // in the edit mode a card is dragged by itself
    if (e.pointerType === 'mouse') Object.keys(ptrs.current).forEach(id => { delete ptrs.current[id]; });   // there is one mouse: an old press whose release was lost is not a «second finger» (that was a pinch to a random place)
    if (!Object.keys(ptrs.current).length) panMoved.current = false;
    ptrs.current[e.pointerId] = { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, item: onItem };
    if (!onItem) try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) { }      // on a card: captured only once it moves, or the tap would not reach the card
    panRef.current = baseline();
    /* раньше выделение снималось уже на нажатии: стоило начать двигать карту, как выделенное устройство пропадало,
       и вся карта перерисовывалась под пальцем. Теперь его снимает только короткое касание пустого места */
    bgTap.current = Object.keys(ptrs.current).length === 1 && !onItem;
  };
  const onBgMove = e => {
    const p0 = ptrs.current[e.pointerId];
    if (!p0 || !panRef.current) return;
    if (e.pointerType === 'mouse' && e.buttons === 0) { onBgUp(e); return; }       // the button was let go outside the map: the pan is over
    if (!panMoved.current) {
      if (Math.hypot(e.clientX - p0.sx, e.clientY - p0.sy) < 4) return;       // a tap's tiny wobble is not a pan
      panMoved.current = true;
      Object.keys(ptrs.current).forEach(id => { try { e.currentTarget.setPointerCapture(+id); } catch (_) { } });
    }
    e.preventDefault();
    ptrs.current[e.pointerId] = { ...p0, x: e.clientX, y: e.clientY };
    const pts = Object.values(ptrs.current); const b = panRef.current;
    if (b.pinch && pts.length >= 2) {
      const r = wrap.current.getBoundingClientRect();
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const cx = (pts[0].x + pts[1].x) / 2 - r.left, cy = (pts[0].y + pts[1].y) / 2 - r.top;
      const k = clampK(b.v.k * dist / b.dist);
      applyView({ k, x: cx - (b.cx - b.v.x) * k / b.v.k, y: cy - (b.cy - b.v.y) * k / b.v.k });
    } else if (!b.pinch) applyView({ ...b.v, x: b.v.x + e.clientX - b.sx, y: b.v.y + e.clientY - b.sy });
  };
  /* палец, начавший движение на устройстве, карта забирает себе (setPointerCapture), и устройство получает lostpointercapture — оно всплывает к карте.
     Раньше карта принимала его за «палец отпущен», и движение обрывалось; теперь в разметке слушается только своё событие карты */
  const onBgUp = e => { if (!ptrs.current[e.pointerId]) return; delete ptrs.current[e.pointerId]; if (!Object.keys(ptrs.current).length) { if (panMoved.current) dragEnd.current = Date.now(); else if (bgTap.current && e.type !== 'lostpointercapture') { setSel(null); setFocus(null); } bgTap.current = false; commitView(); panRef.current = null; return; } bgTap.current = false; panRef.current = baseline(); };
  const upRef = useRef(null); upRef.current = onBgUp;
  useEffect(() => {                                         // a release anywhere ends the gesture (over a panel, outside the window, after a card opened)
    const up = e => upRef.current && upRef.current(e);
    const gone = () => { if (!Object.keys(ptrs.current).length) return; Object.keys(ptrs.current).forEach(id => { delete ptrs.current[id]; }); upRef.current && upRef.current({ pointerId: -1 }); commitView(); panRef.current = null; };
    window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up); window.addEventListener('blur', gone);
    return () => { window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up); window.removeEventListener('blur', gone); };
  }, []);
  /* the list of devices changes on its own (a phone joins Wi-Fi, a device goes offline, a client list opens): the cards move inside the layer.
     The view is moved by the same step, so the card in the middle of the screen stays where it was — before, the whole map seemed to jump somewhere */
  const prevPos = useRef(null);                            // where the cards were drawn last time (with a card being dragged in the edit mode)
  useLayoutEffect(() => {
    const pp = prevPos.current, np = L.pos;
    const el = wrap.current, v = liveV.current || viewRef.current;
    if (!pp || pp === np || !el || !v || animRef.current) return;
    const cx = (el.clientWidth / 2 - v.x) / v.k, cy = (el.clientHeight / 2 - v.y) / v.k;
    let id = revealRef.current && pp[revealRef.current] && np[revealRef.current] ? revealRef.current : null;
    if (!id) { let bd = Infinity; for (const k in np) { const a = pp[k]; if (!a) continue; const d = Math.hypot(a.x + a.w / 2 - cx, a.y + a.h / 2 - cy); if (d < bd) { bd = d; id = k; } } }
    if (!id) return;
    const dx = (np[id].x - pp[id].x) * v.k, dy = (np[id].y - pp[id].y) * v.k;
    if (Math.abs(dx) < .5 && Math.abs(dy) < .5) return;
    const nv = { ...v, x: v.x - dx, y: v.y - dy };
    if (liveV.current) {                                    // a gesture is going on: move it along, it goes on from the new place
      liveV.current = nv; const tr = `translate(${nv.x},${nv.y}) scale(${nv.k})`;
      if (gRef.current) gRef.current.setAttribute('transform', tr);
      const gp = document.getElementById('mapgrid'); if (gp) gp.setAttribute('patternTransform', tr);
      if (panRef.current) panRef.current = baseline();
    } else { viewRef.current = nv; setView(nv); }
  }, [L0]);
  useLayoutEffect(() => { prevPos.current = L.pos; });
  const wheelT = useRef(0);
  const zoomAt = (factor, cx, cy) => setView(v => {
    const W = wrap.current.clientWidth, H = wrap.current.clientHeight; cx = cx == null ? W / 2 : cx; cy = cy == null ? H / 2 : cy;
    const k = clampK(v.k * factor); return { k, x: cx - (cx - v.x) * k / v.k, y: cy - (cy - v.y) * k / v.k };
  });
  // panels over the map (analysis, node info, rack list) scroll on their own — gestures there are not map gestures
  const inPanel = e => e.target && e.target.closest && e.target.closest('.health-panel, .node-info, .rack-jump');
  const onWheel = e => {
    if (inPanel(e)) return;
    e.preventDefault(); stopGlide(); const r = wrap.current.getBoundingClientRect(), cx = e.clientX - r.left, cy = e.clientY - r.top;
    // the wheel / trackpad sends dozens of events a second: only the layer's transform per frame, the state once the wheel stops
    const v = liveV.current || viewRef.current; if (!v) return;
    const px = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1, dx = e.deltaX * px, dy = e.deltaY * px;
    // a trackpad's two-finger swipe moves the map (small, smooth, often sideways deltas); a pinch (ctrl) and a mouse wheel's notches zoom
    const pad = !e.ctrlKey && e.deltaMode === 0 && (dx !== 0 || Math.abs(dy) < 50 || !Number.isInteger(dy));
    if (pad) applyView({ ...v, x: v.x - dx, y: v.y - dy });
    else { const k = clampK(v.k * Math.exp(-Math.max(-300, Math.min(300, dy)) * (e.ctrlKey ? .01 : .0022)));
      applyView({ k, x: cx - (cx - v.x) * k / v.k, y: cy - (cy - v.y) * k / v.k }); }
    clearTimeout(wheelT.current); wheelT.current = setTimeout(() => { if (!panRef.current) commitView(); }, 220);
  };
  const gest = useRef(null);                                // Safari on a Mac: the trackpad pinch comes as gesture events, not ctrl+wheel
  const onGesture = ev => {
    if (inPanel(ev)) return; ev.preventDefault();
    if (Object.keys(ptrs.current).length) return;           // on a phone the fingers are already handled as pointers
    const r = wrap.current.getBoundingClientRect(), cx = ev.clientX - r.left, cy = ev.clientY - r.top;
    if (ev.type === 'gesturestart') { stopGlide(); gest.current = { ...(liveV.current || viewRef.current) }; return; }
    const b = gest.current; if (!b) return;
    if (ev.type === 'gestureend') { gest.current = null; commitView(); return; }
    const k = clampK(b.k * ev.scale); applyView({ k, x: cx - (cx - b.x) * k / b.k, y: cy - (cy - b.y) * k / b.k });
  };
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const stop = ev => { if (!inPanel(ev)) ev.preventDefault(); };     // block page scroll / zoom on the map
    el.addEventListener('wheel', onWheel, { passive: false });
    ['gesturestart', 'gesturechange', 'gestureend'].forEach(t => el.addEventListener(t, onGesture));
    el.addEventListener('touchmove', stop, { passive: false });
    return () => { el.removeEventListener('wheel', onWheel); ['gesturestart', 'gesturechange', 'gestureend'].forEach(t => el.removeEventListener(t, onGesture)); el.removeEventListener('touchmove', stop); };
  }, [wrap.current, !!view]);

  // node drag in edit mode
  const dragEnd = useRef(0), ptr = useRef('');            // when the last drag ended / which pointer was used (mouse | touch | pen)
  const nodeDown = (id, e) => {
    ptr.current = e.pointerType || '';
    if (!edit || L.nodes[id]?.phantom || L.pos[id].rack || linking || L.style) return;
    if (L.edges.some(e => e.target === id && e.kind === 'wifi' && (data.map.wifiGroups?.[e.source] || stableRef.current.autoGroups?.[e.source]))) { toast('Чтобы переместить клиента, сначала отключи группировку этой точки'); return; }            // cards are dragged in the default scheme only
    e.stopPropagation(); const p0 = { ...L.pos[id] }; const sx = e.clientX, sy = e.clientY; let moved = false;
    // magnet: a card sticks to the grid and to the edges / centres of its neighbours (same idea as the tiles in «Размещение»)
    const others = Object.entries(L.pos).filter(([oid, o]) => oid !== id && !o.rack && L.nodes[oid]).map(([, o]) => o);
    const at = ev => {
      const x = p0.x + (ev.clientX - sx) / view.k, y = p0.y + (ev.clientY - sy) / view.k, T = 9 / view.k;
      let nx = Math.round(x / MAP_GRID) * MAP_GRID, ny = Math.round(y / MAP_GRID) * MAP_GRID, gx = null, gy = null, bx = T, by = T;
      others.forEach(o => {
        [o.x, o.x + o.w - p0.w, o.x + (o.w - p0.w) / 2, o.x + o.w + MAP_GRID, o.x - p0.w - MAP_GRID].forEach(c => { if (Math.abs(x - c) < bx) { bx = Math.abs(x - c); nx = Math.round(c); gx = c === o.x ? o.x : c === o.x + o.w - p0.w ? o.x + o.w : c === o.x + (o.w - p0.w) / 2 ? o.x + o.w / 2 : null; } });
        [o.y, o.y + o.h - p0.h, o.y + (o.h - p0.h) / 2, o.y + o.h + MAP_GRID, o.y - p0.h - MAP_GRID].forEach(c => { if (Math.abs(y - c) < by) { by = Math.abs(y - c); ny = Math.round(c); gy = c === o.y ? o.y : c === o.y + o.h - p0.h ? o.y + o.h : c === o.y + (o.h - p0.h) / 2 ? o.y + o.h / 2 : null; } });
      });
      return { np: [nx, ny], gx, gy };
    };
    let raf = 0, lastEv = null;
    const move = ev => {
      if (!moved) { // A deliberate drag establishes a new position for the present AP.
        if (stableRef.current.autoWifi?.[id]) delete stableRef.current.autoWifi[id];
        const currentAP = mapWifiParents(data)[id]; if (currentAP) stableRef.current.wifiSeen[id] = currentAP;
      }
      moved = true; lastEv = ev; if (raf) return;
      raf = requestAnimationFrame(() => { raf = 0; const r = at(lastEv); setDragPos(d => ({ ...d, [id]: r.np })); setGuides({ x: r.gx, y: r.gy }); }); };
    const up = ev => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); cancelAnimationFrame(raf); setGuides(null);
      if (moved) dragEnd.current = Date.now();
      if (moved) saveMap({ positions: { ...(data.map.positions || {}), [id]: at(ev).np } });
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  };
  const tapRef = useRef(null);
  const popOf = id => { const n = L.nodes[id]; const r = n && n.remoteOf; return r ? (closingIds[r] && !remoteOpenIds[r] ? 'out' : 'in') : ''; };   // a client of a remote device: flying out of it or back in
  const nodeClick = async (id) => {
    const n = L.nodes[id];
    if (n?.phantom) { setTestPick(id); setTestOpen(true); return; }
    if (linking) {
      if (linking === 'pick') { setLinking(id); toast('Теперь выберите второе устройство'); return; }
      if (linking !== id) {
        const label = prompt('Подпись для связи (необязательно), например «Оптика 1 Гбит»', '') || '';
        await saveMap({ links: [...(data.map.links || []), { id: 'm' + Date.now().toString(36), source: linking, target: id, label }] });
        toast('Связь добавлена');
      }
      setLinking(null); return;
    }
    if (Date.now() - dragEnd.current < 350) return;                     // the click that ends a pan / drag is not a tap
    if (n.kind === 'group') { const nc = { ...collapsed, [n.parent]: false }; setCollapsed(nc); setView(null); if (edit) saveMap({ collapsed: nc }); return; }
    if (n.remoteClients && !scope) {                                    // a remote device: one tap shows / hides who is connected, two taps open its card
      const last = tapRef.current;
      if (last && last.id === id && Date.now() - last.t < 320) { clearTimeout(last.timer); tapRef.current = null; openInfo(id); return; }
      if (last) clearTimeout(last.timer);
      tapRef.current = { id, t: Date.now(), timer: setTimeout(() => { tapRef.current = null; toggleRemote(id); }, 240) };
      return;
    }
    if (edit && ptr.current === 'mouse') return;                        // on a computer in edit mode the card opens on double click (single click = grab)
    if (sel === id) { setInfo(id); return; }                            // второе касание уже выделенного — открыть карточку
    setSel(id);
    if (!lsGet('rl_map_tap_hint', '')) { lsSet('rl_map_tap_hint', '1'); toast('Нажмите ещё раз, чтобы открыть карточку'); }
  };
  const nodeDbl = id => { if (L.nodes[id] && L.nodes[id].remoteClients && !scope) return; if (edit && ptr.current === 'mouse' && L.nodes[id] && L.nodes[id].kind !== 'group' && !linking) openInfo(id); };
  const edgeClick = async (e) => {
    if (!edit || !e.manual) return;
    if (await confirm('Удалить эту связь?', { danger: true, ok: 'Удалить' })) saveMap({ links: (data.map.links || []).filter(l => l.id !== e.id && `m:${l.source}>${l.target}` !== e.id) });
  };

  // highlight path to the root for the selected node
  const pathSet = useMemo(() => {
    if (!sel) return focus; const s = new Set([sel]); let cur = sel, guard = 0;
    while (guard++ < 30) { const pe = L.edges.find(e => e.target === cur && !e.extra && !e.manual); if (!pe) break; s.add(pe.id); s.add(pe.source); cur = pe.source; }
    L.edges.filter(e => e.source === sel).forEach(e => { s.add(e.id); s.add(e.target); });
    return s;
  }, [sel, L, focus]);
  const searchHit = q ? Object.values(L.nodes).filter(n => [n.label, (data.labels || {})[n.id], n.sub].join(' ').toLowerCase().includes(q.toLowerCase())).map(n => n.id) : [];
  useEffect(() => {                       // a search that finds a client hidden behind a remote device opens that device
    const s = q.trim().toLowerCase(); if (s.length < 2) return;
    const want = Object.values(L.hiddenClients || {}).filter(h => [h.node.label, h.node.sub].join(' ').toLowerCase().includes(s)).map(h => h.parent);
    if (want.length) { setRemoteOpenIds(o => ({ ...o, ...Object.fromEntries(want.map(i => [i, true])) })); setView(null); }
  }, [q]);
  useEffect(() => {
    if (searchHit.length === 1 && wrap.current) { const p = L.pos[searchHit[0]]; if (!p) return; const W = wrap.current.clientWidth, H = wrap.current.clientHeight;
      openInfo(searchHit[0]); setView(v => ({ k: Math.max(v.k, .9), x: W / 2 - (p.x + p.w / 2) * Math.max(v.k, .9), y: H / 2 - (p.y + p.h / 2) * Math.max(v.k, .9) })); }
  }, [q]);

  const devById = Object.fromEntries(data.devices.map(d => [d.id, d]));
  useEffect(() => {                       // ?mapnode=<part of a name>: open that node's card (for links and tests)
    const q = (new URLSearchParams(location.search).get('mapnode') || '').toLowerCase(); if (!q) return;
    const id = Object.keys(L.nodes).find(k => String(L.nodes[k].label || '').toLowerCase().includes(q)); if (id) { openInfo(id); if (L.nodes[id].remoteClients) { setRemoteOpenIds({ [id]: true }); setView(null); } }
  }, []);
  const selNode = info && info === sel && L.nodes[info];
  const [findOpen, setFindOpen] = useState(false);
  const [racksOpen, setRacksOpen] = useState(false);
  const anyCollapsedOpen = allWifi || Object.values(collapsed).some(v => v === false) || (!stableRef.current.autoSuppress && (Object.keys(stableRef.current.autoOpen).length > 0 || Object.keys(stableRef.current.autoGroups).length > 0 || Object.keys(data.map.wifiGroups || {}).length > 0));
  const toggleWifi = () => { stableRef.current.autoSuppress = anyCollapsedOpen; if (anyCollapsedOpen) stableRef.current.autoOpen = {}; setAllWifi(!anyCollapsedOpen); setCollapsed({}); setView(null); };
  const toggleDevices = () => { setShowRemote(v => !v); setRemoteOpenIds({}); setClosingIds({}); setSel(null); setInfo(null); setView(null); };
  /* «Сделать снимок»: вся карта (не только видимая часть) картинкой PNG — как скриншот на iPhone: вспышка, миниатюра в углу, по нажатию сохранить */
  const [shot, setShot] = useState(null);                  // {url, blob, name}
  const snap = async () => {
    const svg = wrap.current && wrap.current.querySelector(':scope > svg'); if (!svg || !gRef.current) return;
    try {
      const b = bbox(), pad = 40, vw = b.w + pad * 2, vh = b.h + pad * 2;
      const scale = Math.max(.5, Math.min(2.5, Math.sqrt(15e6 / (vw * vh))));   // iPhone не рисует холст больше ~16 млн точек
      const src = [svg, ...svg.querySelectorAll('*')], clone = svg.cloneNode(true), dst = [clone, ...clone.querySelectorAll('*')];
      const PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'font-family', 'font-size',
        'font-weight', 'letter-spacing', 'text-anchor', 'dominant-baseline', 'paint-order', 'visibility', 'display'];
      src.forEach((el, i) => { const d = dst[i]; if (!d) return; const cs = getComputedStyle(el);
        d.setAttribute('style', PROPS.map(k => { const v = cs.getPropertyValue(k); return v ? k + ':' + v : ''; }).filter(Boolean).join(';')); d.removeAttribute('class'); });
      const gi = src.indexOf(gRef.current); if (gi >= 0) dst[gi].removeAttribute('transform');
      [...clone.querySelectorAll('rect[fill="url(#mapgrid)"], title')].forEach(e => e.remove());
      clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg'); clone.setAttribute('viewBox', `${b.x - pad} ${b.y - pad} ${vw} ${vh}`);
      clone.setAttribute('width', Math.round(vw * scale)); clone.setAttribute('height', Math.round(vh * scale)); clone.removeAttribute('style');
      const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bg.setAttribute('x', b.x - pad); bg.setAttribute('y', b.y - pad); bg.setAttribute('width', vw); bg.setAttribute('height', vh);
      bg.setAttribute('fill', getComputedStyle(document.body).backgroundColor || '#f2f2f7'); clone.insertBefore(bg, clone.firstChild);
      await Promise.all([...clone.querySelectorAll('image')].map(async im => {          // флаги и свои иконки — внутрь картинки, иначе холст их не нарисует
        const h = im.getAttribute('href'); if (!h || h.startsWith('data:')) return;
        try { const bl = await (await fetch(h, { credentials: 'same-origin' })).blob();
          im.setAttribute('href', await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(bl); })); } catch (_) { im.remove(); }
      }));
      const svgUrl = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }));
      const img = new Image(); await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; img.src = svgUrl; });
      const cv = document.createElement('canvas'); cv.width = Math.round(vw * scale); cv.height = Math.round(vh * scale);
      cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); URL.revokeObjectURL(svgUrl);
      const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
      const d = new Date(), z = n => String(n).padStart(2, '0');
      const name = `karta-seti-${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}_${z(d.getHours())}-${z(d.getMinutes())}.png`;
      if (shot) URL.revokeObjectURL(shot.url);
      setShot({ url: URL.createObjectURL(blob), blob, name, t: Date.now() });
    } catch (e) { toast('Не получилось сделать снимок: ' + (e && e.message || e), true); }
  };
  const saveShot = async () => {
    if (!shot) return;
    const file = new File([shot.blob], shot.name, { type: 'image/png' });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {      // iPhone: «Сохранить изображение» в Фото
      try { await navigator.share({ files: [file], title: 'Карта сети' }); return; } catch (e) { if (e && e.name === 'AbortError') return; }
    }
    const a = document.createElement('a'); a.href = shot.url; a.download = shot.name; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(shot.url); setShot(null);                       // после скачивания миниатюру убираем
  };
  useEffect(() => { if (!shot) return; const t = setTimeout(() => setShot(s => s && s.t === shot.t ? { ...s, idle: true } : s), 6000); return () => clearTimeout(t); }, [shot && shot.t]);
  const wifiParents = Object.values(L.nodes).filter(n => !n.phantom && n.kind !== 'group' && (n.kind === 'ap' || n.kind === 'router' || L.edges.some(e => e.kind === 'wifi' && e.source === n.id)))
    .sort((a, b) => String(a.label).localeCompare(String(b.label), 'ru'));
  const selectedParent = wifiParents.some(n => n.id === testParent) ? testParent : (wifiParents[0]?.id || '');
  const toggleWifiGroup = () => {
    const p = L.pos[selectedParent]; if (!p) return;
    const groups = { ...(data.map.wifiGroups || {}) };
    if (groups[selectedParent] || stableRef.current.autoGroups[selectedParent]) {
      delete groups[selectedParent]; delete stableRef.current.autoGroups[selectedParent]; stableRef.current.groupOptOut[selectedParent] = true;
    } else {
      delete stableRef.current.groupOptOut[selectedParent];
      const children = L.edges.filter(e => e.kind === 'wifi' && e.source === selectedParent && !L.nodes[e.target]?.phantom && L.nodes[e.target]?.client && L.pos[e.target]).map(e => L.pos[e.target]).sort((a, b) => a.y - b.y || a.x - b.x);
      const first = children[0]; groups[selectedParent] = { dx: first ? first.x - p.x : p.w + 80, dy: first ? first.y - p.y : p.h + 20 };
    }
    saveMap({ wifiGroups: groups });
  };
  const addTestClients = count => {
    if (!selectedParent) return;
    testFocus.current = selectedParent;
    setTestClients(cs => [...cs, ...Array.from({ length: Math.min(count, Math.max(0, 50 - cs.length)) }, () => {
      const n = ++testSeq.current; return { id: 'test:phantom:' + n, label: 'Тестовый клиент ' + n, parent: selectedParent };
    })]);
  };
  if (!view) return <div className="map-wrap" ref={wrap} />;
  const tv = liveV.current || (animRef.current && animV.current) || view;      // the view the layer is really at (a gesture or a glide may be running)
  return <div className={'map-wrap' + (scope ? ' scoped' : '')} ref={wrap}>
    <WorkMenu title={scope ? 'Сеть дома' : 'Карта сети'}>
      <WorkSec title="Найти и перейти">
        <WorkItem icon="search" label="Найти устройство" onClick={() => { setFindOpen(true); setRacksOpen(false); }} />
        {((L.racks || []).length + (L.rooms || []).length) > 1 ? <WorkItem icon="rack" label="Шкафы и места" on={racksOpen} onClick={() => setRacksOpen(!racksOpen)} /> : null}
        <WorkItem icon="fit" label="Показать всё" onClick={fit} />
        <WorkItem icon="camera" label="Сделать снимок" sub="вся карта картинкой" onClick={snap} />
      </WorkSec>
      <WorkSec title="Вид">
        <WorkChoice value={style} keep options={MAP_STYLES.map(([value, label]) => ({ value, label }))} onChange={v => { setStyle(v); lsSet('rl_map_style', v); setView(null); setSel(null); }} />
        <WorkChoice value={wireStyle} keep options={[{ value: 'curved', label: 'Плавные линии' }, { value: 'straight', label: 'Прямые линии' }, { value: 'orthogonal', label: 'Прямые углы' }]} onChange={v => { setWireStyle(v); lsSet('rl_map_wire_style', v); }} />
        {data.health ? <WorkItem icon="pulse" label="Анализ сети" sub="узкие места и советы" on={healthOpen} onClick={() => setHealthOpen(!healthOpen)} /> : null}
      </WorkSec>
      {edit ? <WorkSec title="Правка">
        <WorkItem icon="plus" label="Группы и тест клиентов" on={testOpen} onClick={() => setTestOpen(!testOpen)} />
        <WorkItem icon="link" label={linking ? 'Отменить связь' : 'Провести связь'} on={!!linking} onClick={() => setLinking(linking ? null : 'pick')} />
        <WorkItem icon="refresh" label="Сбросить расположение узлов" onClick={async () => { if (await confirm('Сбросить ручное расположение узлов?')) { setDragPos({}); saveMap({ positions: {} }); } }} />
      </WorkSec> : null}
    </WorkMenu>
    {edit && testOpen ? <div className="map-panel" style={{ position: 'absolute', zIndex: 5, top: 110, right: 16, width: 'min(330px, calc(100% - 32px))', padding: 14, display: 'flex', flexDirection: 'column', maxHeight: 'calc(100% - 125px)', overflow: 'auto' }}>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}><b>Группы и тест клиентов</b><Btn size="sm" title="Закрыть панель" onClick={() => setTestOpen(false)}>Закрыть</Btn></div>
      <div className="dim" style={{ fontSize: 12, marginBottom: 5 }}>Точка доступа или роутер</div>
      <select className="input" value={selectedParent} onChange={e => setTestParent(e.target.value)} style={{ width: '100%' }}>
        {!wifiParents.length ? <option value="">Нет доступных точек</option> : null}
        {wifiParents.map(n => <option key={n.id} value={n.id}>{nameNoTag(n.label)}</option>)}
      </select>
      <Btn size="sm" style={{ width: '100%', marginTop: 8 }} disabled={!selectedParent || style !== 'columns'} onClick={toggleWifiGroup}>{(data.map.wifiGroups?.[selectedParent] || stableRef.current.autoGroups?.[selectedParent]) ? 'Отключить группировку' : 'Собрать клиентов у точки'}</Btn>
      {style !== 'columns' ? <div className="dim" style={{ fontSize: 12 }}>Группировка доступна в виде «Схема со шкафом».</div> : null}
      <div className="dim" style={{ fontSize: 12, margin: '12px 0 6px' }}>Тестовые клиенты существуют только в этой вкладке.</div>
      <div className="row" style={{ gap: 6 }}><Btn size="sm" disabled={!selectedParent} onClick={() => addTestClients(1)}>+ 1</Btn><Btn size="sm" disabled={!selectedParent} onClick={() => addTestClients(5)}>+ 5</Btn><Btn size="sm" disabled={!testClients.length} onClick={() => { setTestClients([]); setTestPick('all'); }}>Очистить</Btn></div>
      {testClients.length ? <><select className="input" value={testPick} onChange={e => setTestPick(e.target.value)} style={{ width: '100%', marginTop: 8 }}><option value="all">Все тестовые клиенты</option>{testClients.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
        <Btn size="sm" style={{ width: '100%', marginTop: 6 }} disabled={!selectedParent} onClick={() => { testFocus.current = selectedParent; setTestClients(cs => cs.map(c => testPick === 'all' || c.id === testPick ? { ...c, parent: selectedParent } : c)); }}>Переключить на выбранную точку</Btn></> : null}
    </div> : null}
    {findOpen || q ? <div className="map-tools"><div className="map-panel map-find">
      <div className="map-search"><SearchBox value={q} onChange={setQ} placeholder="Найти устройство" autoFocus /></div>
      <Btn size="sm" icon="x" title="Закрыть поиск" onClick={() => { setQ(''); setFindOpen(false); }} /></div></div> : null}
    {scope && !Object.keys(L.nodes).length ? <div className="live-msg hint plan-ovl">В этом доме пока нет устройств. Откройте дом и поставьте на этажи оборудование и шкафы — они появятся здесь вместе с цепочкой до роутера и интернета.</div> : null}
    {scope ? <AuBack fn={scope.back} label={scope.backLabel || 'К дому'} /> : null}
    {scope ? <div className="plan-ctx plan-ovl"><Btn size="sm" icon="chevronLeft" className="au-inpage-back" onClick={scope.back}>{scope.backLabel || 'К дому'}</Btn><b className="ellipsis">Сеть дома · {scope.title}</b>
      {scope.openHouse ? <Btn size="sm" icon="home" onClick={scope.openHouse}>Дом</Btn> : null}</div> : null}
    {racksOpen && ((L.racks || []).length + (L.rooms || []).length) > 1 ? <div className="map-panel rack-jump">
      <span className="rack-jump-title">Шкафы и места</span>
      {L.racks.map(rk => <button key={rk.id} className="rack-jump-btn" onClick={() => { focusRack(rk); setRacksOpen(false); }} title={`Показать «${rk.name}»`}>
        <Icon name="rack" size={13} /><span className="ellipsis">{rk.name}</span></button>)}
      {(L.rooms || []).map(rm => <button key={rm.id} className="rack-jump-btn" onClick={() => { focusRoom(rm); setRacksOpen(false); }} title={`Показать устройства «${rm.name}»`}>
        <Icon name="home" size={13} /><span className="ellipsis">{rm.name}</span></button>)}
      <button className="rack-jump-btn" onClick={() => { fit(); setFocus(null); setRacksOpen(false); }}><Icon name="fit" size={13} />Все</button>
    </div> : null}
    {linking ? <div className="toast" style={{ position: 'absolute', top: 64, left: '50%', transform: 'translateX(-50%)', zIndex: 3 }}>
      <Icon name="link" size={15} />{linking === 'pick' ? 'Выберите первое устройство' : 'Выберите второе устройство'}</div> : null}
    <svg onPointerDown={onBgDown} onPointerMove={onBgMove} onPointerUp={onBgUp} onPointerCancel={onBgUp} onLostPointerCapture={e => { if (e.target === e.currentTarget) onBgUp(e); }} className={panRef.current ? 'panning' : ''}>
      {edit ? <><defs><pattern id="mapgrid" width={MAP_GRID} height={MAP_GRID} patternUnits="userSpaceOnUse" patternTransform={`translate(${tv.x},${tv.y}) scale(${tv.k})`}><circle cx="1" cy="1" r="1" fill="var(--text3)" opacity=".35" /></pattern></defs>
        <rect width="100%" height="100%" fill="url(#mapgrid)" pointerEvents="none" /></> : null}
      <g ref={gRef} transform={`translate(${tv.x},${tv.y}) scale(${tv.k})`}>
        {L.hasRack ? <RackBox L={L} data={data} devById={devById} dimSet={pathSet} markSet={spofSet} onOpen={d => openDevice(d)} onSel={openInfo} /> : null}
        {(L.headers || []).map(h => <g key={h.label} pointerEvents="none"><text x={h.x + 4} y={h.y + 16} fontSize="15" fontWeight="700" fill="var(--text)">{trunc(h.label, 28)}</text>
          <text x={h.x + 4} y={h.y + 34} fontSize="11.5" fill="var(--text3)">{h.count} {ruPlural(h.count, 'устройство', 'устройства', 'устройств')}</text><rect x={h.x} y={h.y + 40} width={h.w} height={2} rx={1} fill="var(--accent)" opacity=".5" /></g>)}
        {L.edges.map(e => { const g = edgeGeometry.get(e.id); if (!g) return null; const col = speedColor(e.speed, e.kind);
          const dim = pathSet && !pathSet.has(e.id) ? ' dim-out' : ''; const pop = popOf(e.target);
          return <g key={e.id} className={dim + (pop ? ' edge-' + pop : '')}>
            <path className={'edge' + (e.speed >= 1000 && e.kind !== 'wifi' && e.kind !== 'mesh' ? ' fast' : e.speed > 0 && e.speed < 1000 ? ' slow' : '') + (e.kind === 'wifi' || e.kind === 'mesh' ? ' wifi' : '') + (e.kind === 'remote' || e.extra || e.kind === 'lan' ? ' dashed' : '') + (e.kind === 'isp' ? ' isp' : '')} d={g.d} stroke={col} opacity={e.extra ? .55 : 1} />
            {(e.kind === 'wan' || e.kind === 'isp' || (e.kind === 'wire' && e.speed >= 1000)) && !e.extra ? <path className="edge flow" d={g.d} stroke="#fff" opacity=".5" /> : null}
            {e.manual ? <path className="edge-hit" d={g.d} onClick={() => edgeClick(e)} /> : null}
          </g>; })}
        {/* labels in their own layer: above every wire, with the watts lifted over the line so it stays readable */}
        {L.edges.map(e => { const g = edgeGeometry.get(e.id); if (!g) return null;
          const dim = pathSet && !pathSet.has(e.id) ? ' dim-out' : ''; const pop = popOf(e.target);
          return <g key={'l' + e.id} className={dim + (pop ? ' edge-' + pop : '')} pointerEvents="none">
            {e.sourcePort && !g.inside ? <g className="port-pill" transform={`translate(${g.lx - 14},${g.ly - 9})`}><rect width="28" height="18" rx="9" /><text x="14" y="12.5" textAnchor="middle">{e.sourcePort}</text></g> : null}
            {g.cross ? <g className="map-cross" transform={`translate(${g.lx},${g.ly})`}><rect x={-52} y={-10} width={104} height={20} rx={10} fill="var(--accent)" opacity=".92" />
              <text x={0} y={4} textAnchor="middle" fontSize="11" fontWeight="600" fill="#fff">между шкафами{e.sourcePort ? ' · ' + e.sourcePort : ''}</text></g> : null}
            {e.poeW > 0 && g.mx ? <g className="map-poe" transform={`translate(${g.lx - 14 - 50},${g.ly - 24})`}><rect width="44" height="18" rx="9" fill="#ffd60a" stroke="var(--bg)" strokeWidth="2" /><text x="22" y="12.5" textAnchor="middle" fontSize="10" fontWeight="700" fill="#000">⚡{e.poeW}W</text></g> : null}
            {(e.label && (e.manual || e.kind === 'wan' || e.kind === 'isp')) ? <text x={g.lx} y={g.ly - 14} fontSize="11" fill="var(--text2)" textAnchor="middle" stroke="var(--bg)" strokeWidth="3" paintOrder="stroke">{e.label}</text> : null}
          </g>; })}
        {guides ? <g pointerEvents="none" stroke="var(--accent)" strokeWidth={1 / view.k} strokeDasharray={`${4 / view.k} ${4 / view.k}`} opacity=".7">
          {guides.x != null ? <line x1={guides.x} x2={guides.x} y1={-4000} y2={5000} /> : null}
          {guides.y != null ? <line y1={guides.y} y2={guides.y} x1={-4000} x2={5000} /> : null}</g> : null}
        {Object.values(L.nodes).map(n => { const p = L.pos[n.id]; if (!p || p.rack) return null;
          return <MapNode key={n.id} n={n} p={p} sel={sel === n.id || searchHit.includes(n.id) || linking === n.id} dim={pathSet && !pathSet.has(n.id)} mark={spofSet && spofSet.has(n.id)} phase={popOf(n.id)}
            onDown={e => nodeDown(n.id, e)} onClick={() => nodeClick(n.id)} onDoubleClick={() => nodeDbl(n.id)} />; })}
      </g>
    </svg>
    <div className="map-legend legend">
      <span><i style={{ background: 'var(--green)' }} />1 Гбит</span><span><i style={{ background: 'var(--yellow)' }} />100 Мбит</span>
      <span><i style={{ background: 'var(--accent)' }} />Wi-Fi</span><span><i style={{ background: 'var(--teal)' }} />Mesh</span><span><i style={{ background: 'var(--purple)' }} />Интернет</span>
      <span><b style={{ color: '#ffd60a' }}>⚡</b>PoE</span></div>
    <div className="zoom-btns">
      <button type="button" className={'btn' + (anyCollapsedOpen ? ' primary' : '')} aria-pressed={anyCollapsedOpen} title={anyCollapsedOpen ? 'Свернуть Wi-Fi-клиентов' : 'Показать всех Wi-Fi-клиентов'} aria-label={anyCollapsedOpen ? 'Свернуть Wi-Fi-клиентов' : 'Показать всех Wi-Fi-клиентов'} onClick={toggleWifi}><Icon name="wifi" size={19} /></button>
      {!scope ? <button type="button" className={'btn' + (showRemote ? ' primary' : '')} aria-pressed={showRemote} title={showRemote ? 'Показать только локальные устройства' : 'Показать все устройства, включая удалённые'} aria-label={showRemote ? 'Показать только локальные устройства' : 'Показать все устройства, включая удалённые'} onClick={toggleDevices}><Icon name="list" size={19} /></button> : null}
      <WorkEditBtn /><button className="btn" aria-label="Увеличить" onClick={() => zoomAt(1.35)}>+</button><button className="btn" aria-label="Уменьшить" onClick={() => zoomAt(1 / 1.35)}>−</button></div>
    {healthOpen && data.health ? <div className="card pad fade-in health-panel">
      <div className="row" style={{ marginBottom: 4 }}><b className="grow" style={{ fontSize: 16 }}>Анализ сети</b><Btn size="sm" icon="x" onClick={() => setHealthOpen(false)} /></div>
      <HealthBody h={data.health} onCheck={c => { if (c.nodeId && L.nodes[c.nodeId] && !c.port) { openInfo(c.nodeId); if (innerWidth < 760) setHealthOpen(false); } else openCheck(c); }}
        onNode={id => { if (L.nodes[id]) { openInfo(id); if (innerWidth < 760) setHealthOpen(false); } }} />
    </div> : null}
    {shot ? <MapShot key={shot.t} shot={shot} onSave={saveShot} onClose={() => { URL.revokeObjectURL(shot.url); setShot(null); }} /> : null}
    {selNode ? <NodeInfo n={selNode} L={L} data={data} devById={devById} onOpen={openDevice} onClose={() => setInfo(null)} /> : null}
  </div>;
}

/* снимок карты как скриншот на iPhone: белая вспышка, картинка уменьшается в левый нижний угол; нажать — сохранить, крестик — убрать */
function MapShot({ shot, onSave, onClose }) {
  return <>
    <div className="map-shot-flash" aria-hidden="true" />
    <div className={'map-shot' + (shot.idle ? ' idle' : '')} role="dialog" aria-label="Снимок карты">
      <button type="button" className="map-shot-close" onClick={onClose} aria-label="Закрыть снимок"><Icon name="x" size={15} /></button>
      <button type="button" className="map-shot-img" onClick={onSave} title="Сохранить снимок"><img src={shot.url} alt="Снимок карты сети" /></button>
      <button type="button" className="map-shot-save" onClick={onSave}><Icon name="check" size={14} />Сохранить снимок</button>
    </div></>;
}

function RackBox({ L, data, devById, dimSet, markSet, onOpen, onSel }) {
  return <>{L.racks.map(rk => <RackFrame key={rk.id} rk={rk} devById={devById} dimSet={dimSet} markSet={markSet} onOpen={onOpen} nodes={L.nodes} onSel={onSel} />)}</>;
}

function RackFrame({ rk, devById, dimSet, markSet, onOpen, nodes = {}, onSel }) {
  const { data } = useApp(); const chosen = data.icons || {};
  const W = rk.w || M.RW, h = rk.h || rk.rows * M.RU;
  const stCol = st => st === 'online' ? 'var(--green)' : st === 'warning' ? 'var(--orange)' : st === 'unknown' ? 'var(--text3)' : 'var(--red)';
  // one cell: a whole unit, a shelf's slot or a box tile
  const cell = (key, u, did, x, y, w, hh, compact) => {
    const d = did ? devById[did] : null; const un = !d && !did && nodes['u:' + u.id];   // un: ONT / modem without a device
    const st = d ? d.state : un ? { status: un.status } : null;
    const dim = dimSet && !(d ? dimSet.has('d:' + d.id) : un && dimSet.has(un.id));
    const kind = PASSIVE.includes(u.type) ? u.type : (d && d.kind) || u.type;
    const rawName = d && (compact || unitDevIds(u).length > 1) ? d.name : u.name;
    const name = nameNoFlag(rawName), cc = flagOf(rawName) || (d ? flagOf(d.name) : '');            // the prefix may be on the unit or on the device inside it
    return <g key={key} className={'u' + (dim ? ' dim-out' : '')} style={{ cursor: d || un ? 'pointer' : 'default' }} onClick={() => d ? onOpen(d) : un && onSel && onSel(un.id)}>
      <rect x={x} y={y} width={w} height={hh} rx={compact ? 10 : 6} />
      {d && markSet && markSet.has('d:' + d.id) ? <rect className="spof-mark" x={x - 3} y={y - 3} width={w + 6} height={hh + 6} rx={compact ? 12 : 8} /> : null}
      <rect x={x} y={y} width={4} height={hh} rx={2} fill={u.color || '#0a84ff'} stroke="none" />
      {cc ? <image href={'/flags/' + cc + '.svg'} x={x + 12} y={y + hh / 2 - 9} width={18} height={18} preserveAspectRatio="xMidYMid slice" />
        : <g className="u-ic" transform={`translate(${x + 12},${y + hh / 2 - 9})`}><NodeGlyph svg spec={d ? chosen['d:' + d.id] : un ? chosen[un.id] : undefined} kind={kind} size={18} color="currentColor" /></g>}
      <text x={x + 38} y={y + (hh > 30 ? hh / 2 - 2 : hh / 2 + 4)} fontSize="12.5" fontWeight="600">{trunc(name, Math.max(8, Math.floor((w - 50) / 7.2)))}</text>
      {hh > 30 && w > 120 ? <text x={x + 38} y={y + hh / 2 + 12} className="usub">{trunc(d ? deviceLine(d) : KIND_TEXT[u.type], Math.floor((w - 50) / 5.6))}</text> : null}
      {st ? <circle cx={x + w - 11} cy={y + 11} r={4} fill={stCol(st.status)} /> : null}
      {st && !compact && w > 220 && (st.ports || []).length > 4 ? <g transform={`translate(${x + w - 14 - Math.ceil(Math.min(st.ports.length, 28) / 2) * 7},${y + hh - 17})`}>
        {st.ports.slice(0, 28).map((p, i) => <rect key={i} x={Math.floor(i / 2) * 7} y={(i % 2) * 7} width={5} height={5} rx={1}
          fill={!p.link ? '#3a3a3c' : p.speed >= 1000 ? '#30d158' : p.speed >= 100 ? '#ffd60a' : '#ff9f0a'} stroke="none" />)}</g> : null}
    </g>;
  };
  if (!rk.isRack) return <g className="rackbox boxframe" transform={`translate(0,${rk.y})`}>
    <rect className="frame" x={-14} y={-46} width={W + 28} height={h + 60} rx={20} />
    <g className="u-ic" transform="translate(0,-34)"><Icon name="box" size={16} color="currentColor" /></g>
    <text x={22} y={-22} fontSize="14" fontWeight="700">{rk.name}</text>
    <text x={W} y={-22} fontSize="11" textAnchor="end" className="usub">щиток</text>
    {(rk.tiles || []).map((t, i) => t.dup ? <g key={'t' + i} opacity=".4">{cell('t' + i, t.u, t.nid.slice(2), t.x, t.y, M.MT, M.MTH, true)}</g>
      : cell('t' + i, t.u, t.nid && t.nid.startsWith('d:') ? t.nid.slice(2) : null, t.x, t.y, M.MT, M.MTH, true))}
  </g>;
  const rows = rk.units.filter(u => (u.side || 'front') === 'front');
  return <g className="rackbox" transform={`translate(0,${rk.y})`}>
    <rect className="frame" x={-14} y={-46} width={W + 28} height={h + 60} rx={16} />
    <text x={0} y={-22} fontSize="14" fontWeight="700">{rk.name}</text>
    <text x={W} y={-22} fontSize="11" textAnchor="end" className="usub">{rk.total + 'U'}</text>
    {Array.from({ length: rk.total }, (_, i) => <text key={i} x={-7} y={i * M.RU + M.RU / 2 + 3} fontSize="8" textAnchor="middle" className="usub">{i + 1}</text>)}
    {rows.flatMap(u => { const y = (u.uStart - 1) * M.RU, hh = u.uSize * M.RU - 4; const ids = unitDevIds(u);
      if (ids.length <= 1) return [cell(u.id, u, ids[0] || null, 0, y, W, hh, false)];
      const cw = (W - (ids.length - 1) * 4) / ids.length;            // a shelf with several devices
      return ids.map((did, k) => cell(u.id + k, u, did, k * (cw + 4), y, cw, hh, false)); })}
  </g>;
}

/* how the internet reaches the router: straight in, or through an ONT (PON) / modem — map.wan */
const WAN_OPTS = [{ value: 'auto', label: 'Авто' }, { value: 'direct', label: 'Напрямую' }, { value: 'ont', label: 'ONT (PON)' }, { value: 'modem', label: 'Модем' }];
function WanSetup({ n, L, data }) {
  const { admin, saveMap } = useApp();
  const wan = data.map.wan || {}; const via = wan.via || 'auto';
  const box = Object.values(L.nodes).find(x => x.wan);
  const wanEdge = L.edges.find(e => e.kind === 'wan');
  const set = patch => saveMap({ wan: { ...wan, ...patch } });
  const units = allUnits(data).filter(u => !['cross', 'patch', 'router', 'switch', 'blank', 'organizer', 'shelf'].includes(u.type) && (u.side || 'front') === 'front');
  const isp = L.edges.find(e => e.kind === 'isp');
  const mainNode = Object.values(L.nodes).find(x => x.main);
  const routers = data.devices.filter(d => ['keenetic', 'openwrt', 'demo_router'].includes(d.driver) && d.enabled !== false);
  const now = box ? `${n.id === 'inet' ? 'Интернет → ' : ''}${box.label} → ${wanEdge && L.nodes[wanEdge.target] ? L.nodes[wanEdge.target].label : 'роутер'}`
    : wanEdge && L.nodes[wanEdge.target] ? `Интернет → ${L.nodes[wanEdge.target].label} (кабель провайдера прямо в роутер)` : '';
  return <div className="wan-setup">
    <div className="dim" style={{ fontSize: 12.5, marginBottom: 6 }}>{now}{wanEdge && wanEdge.targetPort ? ` · порт ${wanEdge.targetPort}` : ''}{wanEdge && wanEdge.label ? ` · ${wanEdge.label}` : ''}
      {isp && isp.label ? <><br />Линия провайдера: {isp.label}</> : null}
      {mainNode ? <><br />Главный роутер: <b>{mainNode.label}</b> — {mainNode.main}</> : null}</div>
    {admin && routers.length > 1 ? <div className="row" style={{ gap: 8, margin: '8px 0 0', alignItems: 'center' }}>
      <span className="dim" style={{ fontSize: 13 }}>Главный роутер</span>
      <select className="select grow" value={wan.main || ''} onChange={e => set({ main: e.target.value || undefined })}>
        <option value="">Определять самому</option>
        {routers.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></div> : null}
    {admin ? <>
      <div className="card-title" style={{ margin: '8px 0 6px' }}>Как приходит интернет</div>
      <Seg value={via} onChange={v => set({ via: v })} options={WAN_OPTS} />
      <div className="dim3" style={{ fontSize: 12, margin: '6px 0 0', lineHeight: 1.4 }}>
        {via === 'auto' ? 'Rack Live сам ищет в шкафу юнит «Модем / ONT» или с «PON», «ONT», «модем» в названии.' : via === 'direct' ? 'Кабель провайдера включён прямо в роутер.'
          : via === 'ont' ? 'Оптика приходит в PON-терминал, от него кабель в роутер.' : 'Линия (DSL, кабельный, LTE) приходит в модем, от него кабель в роутер.'}</div>
      {via !== 'direct' ? <div className="row wrap" style={{ gap: 8, marginTop: 8 }}>
        <select className="select grow" style={{ minWidth: 150 }} value={wan.unit || ''} onChange={e => set({ unit: e.target.value || undefined })}>
          <option value="">Найти в шкафу сам</option>
          <option value="none">Не в шкафу</option>
          {units.map(u => <option key={u.id} value={u.id}>{u.rackName} · {u.name}</option>)}
        </select>
        <input className="input grow" style={{ minWidth: 130 }} defaultValue={wan.line || ''} placeholder={via === 'modem' ? 'Линия: DSL, LTE…' : 'Линия: оптика'}
          onBlur={e => e.target.value.trim() !== (wan.line || '') && set({ line: e.target.value.trim() || undefined })} />
      </div> : null}
    </> : null}
  </div>;
}

function NodeInfo({ n, L, data, devById, onOpen, onClose }) {
  const { admin, refresh } = useApp(); const toast = useToast(); const [pick, setPick] = useState(() => new URLSearchParams(location.search).get('iconpick') === '1');          // the icon picker («Иконка»)
  const curLabel = (data.labels || {})[n.id] || '';            // своя подпись узла (переименование с карты)
  const [ren, setRen] = useState(null);
  const saveLabel = async (val) => {
    try { await api('/api/labels/set', { method: 'PUT', body: { key: n.id, label: val } }); await refresh(); setRen(null); }
    catch (e) { toast(e.message, true); }
  };
  const [edit, setEdit] = useState(null);                     // mac → ClientEditor (a client of a router: name, fixed IP, speed, policy)
  const pe = L.edges.find(e => e.target === n.id && !e.extra);
  const parent = pe && L.nodes[pe.source];
  const dev = n.deviceId && devById[n.deviceId];
  const client = n.mac && data.devices.flatMap(d => (d.state && d.state.clients) || []).find(c => (c.mac || '').toLowerCase() === n.mac);
  const conn = pe ? (pe.kind === 'wifi' ? `Wi-Fi · ${parent ? parent.label : ''}${pe.band ? ' · ' + pe.band : ''}${pe.rssi ? ' · ' + pe.rssi + ' дБм' : ''}`
    : pe.kind === 'mesh' ? 'Mesh (беспроводной)' : pe.kind === 'remote' ? 'Через интернет' : `${parent ? parent.label : ''}${pe.sourcePort ? ', порт ' + pe.sourcePort : ''}${pe.speed ? ' · ' + fmt.speed(pe.speed) : ''}`) : '';
  return <div className="card pad fade-in node-info">
    <div className="row"><KindIcon kind={n.kind} name={curLabel || n.label} icon={(data.icons || {})[n.id]} size={40} /><div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 700 }} className="ellipsis">{nameNoFlag(curLabel || n.label, n.kind)}</div>
      <div className="dim" style={{ fontSize: 12.5 }}>{KIND_TEXT[n.kind] || ''}{n.model ? ' · ' + n.model : ''}</div></div><Btn size="sm" icon="x" onClick={onClose} /></div>
    {admin && n.kind !== 'group' && !String(n.id).startsWith('x:') ? (ren === null
      ? <button type="button" className="ni-rename" onClick={() => setRen(curLabel)}><Icon name="edit" size={13} />{curLabel ? 'Изменить подпись' : 'Переименовать'}</button>
      : <div className="ni-rename-box">
          <NameInput className="input" value={ren} onChange={setRen} placeholder={nameNoFlag(n.label, n.kind)} />
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            <Btn size="sm" kind="primary" onClick={() => saveLabel(ren)}>Сохранить</Btn>
            {curLabel ? <Btn size="sm" onClick={() => saveLabel('')}>Сбросить</Btn> : null}
            <Btn size="sm" onClick={() => setRen(null)}>Отмена</Btn>
          </div>
        </div>) : null}
    <div style={{ marginTop: 10 }}><KV rows={[['IP', n.sub ? <span className="mono">{n.sub}</span> : null], ...(n.mac ? [['MAC', <span className="mono">{n.mac}</span>]] : []),
      ...(client && client.segment ? [['Сеть', client.segment]] : []), ['Подключение', conn], ...(pe && pe.poeW ? [['PoE', pe.poeW + ' Вт']] : []),
      ...(dev ? [['Состояние', STATUS_TEXT[(dev.state || {}).status]]] : [])]} /></div>
    {n.id === 'inet' || n.wan ? <WanSetup n={n} L={L} data={data} /> : null}
    {dev ? <Btn kind="primary" style={{ width: '100%', marginTop: 12 }} onClick={() => onOpen(dev)}>Подробнее</Btn> : null}
    {!dev && pe && pe.sourcePort && parent && parent.deviceId ? <Btn style={{ width: '100%', marginTop: 12 }} onClick={() => onOpen(devById[parent.deviceId], 'ports', pe.sourcePort)}>Порт {pe.sourcePort} на {parent.label}</Btn> : null}
    {!dev && n.mac && findClient(data, n.mac) ? <Btn style={{ width: '100%', marginTop: 8 }} onClick={() => setEdit(n.mac)}>Настройки на роутере</Btn> : null}
    {!dev && /^\d+\.\d+\.\d+\.\d+$/.test(n.sub || '') ? <ClientActions c={{ ip: n.sub, mac: n.mac, kind: n.kind, name: n.label }} onClose={onClose} /> : null}
    {admin && n.kind !== 'group' && !String(n.id).startsWith('x:') ? <Btn size="sm" icon="edit" style={{ width: '100%', marginTop: 8 }} onClick={() => setPick(true)}>Иконка</Btn> : null}
    {pick ? <IconPicker nodeKey={n.id} kind={n.kind} title={nameNoFlag(n.label, n.kind)} onClose={() => setPick(false)} /> : null}
    {edit ? <ClientEditor mac={edit} onClose={() => setEdit(null)} /> : null}
  </div>;
}
