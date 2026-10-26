/* Settings → «О программе» → «Потребление»: what Rack Live itself costs — processor, memory, disk (rackd/usage.py). Only this program, not the whole NAS. */
function UsageChart({ points, field, fmtVal, color }) {
  const W = 300, H = 56, pad = 3;
  const v = points.map(p => p[field]).filter(x => x != null);
  if (v.length < 2) return <div className="dim3" style={{ fontSize: 12, height: H, display: 'grid', placeItems: 'center' }}>График появится через пару минут</div>;
  const hi = Math.max(...v) * 1.15 || 1, n = points.length;
  const xy = points.map((p, i) => [pad + (W - 2 * pad) * (n === 1 ? 0 : i / (n - 1)), H - pad - (H - 2 * pad) * ((p[field] || 0) / hi)]);
  const line = xy.map(([x, y], i) => (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)).join('');
  return <div><svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ display: 'block' }}>
    <path d={line + `L${xy[xy.length - 1][0]} ${H - pad}L${xy[0][0]} ${H - pad}Z`} fill={color} opacity=".12" />
    <path d={line} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" /></svg>
    <div className="row between dim3" style={{ fontSize: 11, marginTop: 2 }}><span>{Math.round(points.length)} мин назад</span><span>до {fmtVal(Math.max(...v))}</span><span>сейчас</span></div></div>;
}

function UsageCard() {
  const [u, setU] = useState(null); const [err, setErr] = useState('');
  useEffect(() => {
    let dead = false;
    const load = () => api('/api/usage').then(j => { if (!dead) { setU(j); setErr(''); } }).catch(e => { if (!dead) setErr(e.message); });
    load(); const t = setInterval(load, 10000);
    return () => { dead = true; clearInterval(t); };
  }, []);
  if (!u) return <Card title="Потребление">{err ? <div className="cam-warn">{err}</div> : <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Считаю…</div>}</Card>;
  const { cpu, mem, disk } = u, fr = u.frank;
  const cpuText = cpu.now != null ? cpu.now.toFixed(1).replace('.', ',') + ' %' : cpu.avg.toFixed(1).replace('.', ',') + ' %';
  const tok = n => n >= 1e6 ? (n / 1e6).toFixed(1).replace('.', ',') + ' млн' : n >= 1e3 ? Math.round(n / 1e3) + ' тыс.' : String(n || 0);
  const maxItem = Math.max(1, ...disk.items.map(i => i.bytes));
  const usedPct = disk.total ? disk.data / disk.total * 100 : null;
  return <Card title="Потребление">
    <div className="us-tiles">
      <div><b>{fmt.bytes(mem.rss)}</b><span>память</span><small>{mem.peak ? 'пик ' + fmt.bytes(mem.peak) : ' '}</small></div>
      <div><b>{cpuText}</b><span>процессор</span><small>в среднем {cpu.avg.toFixed(1).replace('.', ',')} %</small></div>
      <div><b>{fmt.bytes(disk.data)}</b><span>данные на диске</span><small>программа {fmt.bytes(disk.code)}</small></div>
      <div><b>{fmt.uptime(u.uptime)}</b><span>работает</span><small>{u.threads} потоков</small></div>
    </div>
    <div className="us-charts">
      <div><div className="card-title" style={{ margin: '12px 0 4px' }}>Память</div><UsageChart points={u.history} field="rss" fmtVal={fmt.bytes} color="var(--accent)" /></div>
      <div><div className="card-title" style={{ margin: '12px 0 4px' }}>Процессор</div><UsageChart points={u.history} field="cpu" fmtVal={v => v.toFixed(1).replace('.', ',') + ' %'} color="var(--accent)" /></div>
    </div>
    <div className="card-title" style={{ margin: '14px 0 6px' }}>Что занимает место</div>
    <div className="us-rows">{disk.items.map(i => <div key={i.id}>
      <div className="row between" style={{ fontSize: 13 }}><span>{i.label}</span><b className="mono">{fmt.bytes(i.bytes)}</b></div>
      <div className="bar"><i style={{ width: Math.max(2, i.bytes / maxItem * 100) + '%' }} /></div></div>)}</div>
    <KV rows={[...(mem.container != null ? [['Весь контейнер в памяти', fmt.bytes(mem.container) + (mem.limit ? ' из ' + fmt.bytes(mem.limit) : ' (лимита нет)')]] : []),
      ['Свободно на диске', disk.free != null ? fmt.bytes(disk.free) + (disk.total ? ' из ' + fmt.bytes(disk.total) : '') : '—'],
      ['Процессор за всё время', cpu.seconds >= 3600 ? (cpu.seconds / 3600).toFixed(1).replace('.', ',') + ' ч' : Math.round(cpu.seconds / 60) + ' мин'],
      ...(fr && fr.today ? [['Frank сегодня', fr.today.q ? `${fr.today.q} вопр. · ${tok(fr.today.in + fr.today.out)} токенов` : 'не спрашивали']] : []),
      ...(fr && fr.month && fr.month.q ? [['Frank за месяц', `${fr.month.q} вопр. · ${tok(fr.month.in + fr.month.out)} токенов`]] : [])]} />
    <div className="dim3" style={{ fontSize: 12, marginTop: 10, lineHeight: 1.5 }}>Здесь только то, что берёт сама Rack Live: процессор в процентах от одного ядра (100 % = ядро занято целиком), память процесса и папка с данными{usedPct != null && usedPct < 0.1 ? ' (на диске это доли процента)' : ''}. Обновляется каждые 10 секунд.</div>
  </Card>;
}
