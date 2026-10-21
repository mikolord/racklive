/* Network health: topology type, single points of failure, findings */
const ruPlural = (n, one, few, many) => { const a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many; };
const TOPO_PICS = {
  single: { n: [[30, 22], [10, 8], [50, 8], [10, 36], [50, 36]], e: [[0, 1], [0, 2], [0, 3], [0, 4]] },
  star: { n: [[30, 22], [30, 4], [48, 12], [48, 32], [30, 40], [12, 32], [12, 12]], e: [[0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [0, 6]] },
  tree: { n: [[30, 5], [16, 21], [44, 21], [7, 38], [23, 38], [37, 38], [53, 38]], e: [[0, 1], [0, 2], [1, 3], [1, 4], [2, 5], [2, 6]] },
  chain: { n: [[6, 16], [22, 16], [38, 16], [54, 16], [6, 36], [22, 36], [38, 36], [54, 36]], e: [[0, 1], [1, 2], [2, 3], [0, 4], [1, 5], [2, 6], [3, 7]] },
  ring: { n: [[30, 4], [49, 17], [42, 39], [18, 39], [11, 17]], e: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]] },
  mesh: { n: [[30, 4], [49, 17], [42, 39], [18, 39], [11, 17]], e: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0], [0, 2], [0, 3], [1, 3], [1, 4], [2, 4]] },
};
function TopoPic({ id, on }) {
  const p = TOPO_PICS[id]; const c = on ? 'var(--accent)' : 'var(--text3)';
  return <svg width="60" height="44" viewBox="0 0 60 44">{p.e.map(([a, b], i) => <line key={i} x1={p.n[a][0]} y1={p.n[a][1]} x2={p.n[b][0]} y2={p.n[b][1]} stroke={c} strokeWidth="1.4" opacity=".7" />)}
    {p.n.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i === 0 && id !== 'ring' && id !== 'mesh' && id !== 'chain' ? 4.5 : 3.2} fill={c} />)}</svg>;
}

function ScoreRing({ score, size = 76 }) {
  const r = size / 2 - 6, L = 2 * Math.PI * r; const col = isTestLook() ? scoreTone(score) : score >= 85 ? 'var(--green)' : score >= 60 ? 'var(--orange)' : 'var(--red)';
  return <div className="score-ring" style={{ width: size, height: size }}>
    <svg width={size} height={size}><circle cx={size / 2} cy={size / 2} r={r} stroke="var(--line)" strokeWidth="7" fill="none" />
      <circle cx={size / 2} cy={size / 2} r={r} stroke={col} strokeWidth="7" fill="none" strokeLinecap="round" strokeDasharray={`${L * score / 100} ${L}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: 'stroke-dasharray .8s' }} /></svg>
    <div><b style={{ fontSize: size * .3 }}>{score}</b><small>из 100</small></div></div>;
}

const CHECK_LOOK = { bad: ['var(--red)', 'alert'], warn: ['var(--orange)', 'alert'], info: ['var(--accent)', 'other'], ok: ['var(--green)', 'check'] };
function CheckItem({ c, onClick }) {
  const [col, icon] = CHECK_LOOK[c.level] || CHECK_LOOK.info;
  const clickable = onClick && (c.deviceId || c.nodeId);
  return <div className={'li check-item' + (clickable ? ' click' : '')} onClick={() => clickable && onClick(c)}>
    <div className="check-ic" style={{ color: col, background: `color-mix(in srgb, ${col} 14%, transparent)` }}><Icon name={icon} size={16} /></div>
    <div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 650, fontSize: 14 }}>{c.title}</div>
      {c.text ? <div className="dim" style={{ fontSize: 12.8, lineHeight: 1.4, marginTop: 2 }}>{c.text}</div> : null}</div>
    {clickable ? <Icon name="chevron" size={15} color="var(--text3)" /> : null}</div>;
}

function HealthBody({ h, onCheck, onNode }) {
  const [types, setTypes] = useState(false);
  const t = h.type; const st = h.stats;
  return <div className="health">
    <div className="row" style={{ gap: 16, alignItems: 'center' }}>
      <ScoreRing score={h.score} />
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="dim3" style={{ fontSize: 11.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.4px' }}>Топология</div>
        <div style={{ fontSize: 18, fontWeight: 750, letterSpacing: '-.3px', lineHeight: 1.2 }}>{t.name}</div>
        <div className="dim" style={{ fontSize: 13, marginTop: 3 }}>{t.what}</div>
      </div>
      <TopoPic id={t.id} on />
    </div>
    <div className="row wrap" style={{ gap: 6 }}>
      {[`${st.devices} ${ruPlural(st.devices, 'устройство', 'устройства', 'устройств')}`, `${st.levels} ${ruPlural(st.levels, 'уровень', 'уровня', 'уровней')}`,
        ...(st.switches ? [`коммутаторов: ${st.switches}`] : []), ...t.traits]
        .map((x, i) => <span key={i} className="chip" style={{ cursor: 'default' }}>{x}</span>)}
    </div>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>{t.note}</div>

    <div>
      <div className="row" style={{ marginBottom: 6 }}><div className="card-title grow" style={{ margin: 0 }}>Замечания</div>
        <AskAi label="Разобрать" q="Разбери замечания по здоровью сети: что из этого действительно важно, чем грозит и что сделать — по шагам." /></div>
      <div className="list">{h.checks.map((c, i) => <CheckItem key={i} c={c} onClick={onCheck} />)}</div>
    </div>

    {h.spof.length ? <div>
      <div className="card-title" style={{ marginBottom: 8 }}>Что будет, если узел откажет</div>
      <div className="spof">{h.spof.map(s => <div key={s.id} className={'spof-row' + (onNode ? ' click' : '')} onClick={() => onNode && onNode(s.id)}>
        <KindIcon kind={s.kind} size={28} round={8} />
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row between" style={{ fontSize: 13.5 }}><b className="ellipsis">{s.label}</b><span className="mono dim">−{s.affected}</span></div>
          <div className="spof-bar"><i style={{ width: Math.max(3, s.affected / Math.max(1, st.devices) * 100) + '%' }} /></div>
          {s.what ? <div className="dim3 ellipsis" style={{ fontSize: 11.5, marginTop: 3 }}>{s.what}</div> : null}
        </div></div>)}</div>
    </div> : null}

    <div>
      <button className="link-btn" onClick={() => setTypes(!types)}><Icon name="chevron" size={13} style={{ transform: types ? 'rotate(90deg)' : '' }} />Какие бывают топологии</button>
      {types ? <div className="topo-types">{t.all.map(x => <div key={x.id} className={'topo-type' + (x.id === t.id ? ' on' : '')}>
        <TopoPic id={x.id} on={x.id === t.id} /><div><b>{x.name}{x.id === t.id ? ' · у вас' : ''}</b><div className="dim" style={{ fontSize: 12.3, lineHeight: 1.4 }}>{x.what} {x.note}</div></div>
      </div>)}<div className="dim3" style={{ fontSize: 12 }}>Шина (все на одном кабеле) — устаревшая схема из времён коаксиала, в Ethernet уже не встречается. В жизни сети почти всегда гибридные: например, дерево из кабелей + беспроводной mesh.</div></div> : null}
    </div>
  </div>;
}

function useCheckOpener() {
  const { data, openDevice } = useApp();
  return c => { const d = c.deviceId && data.devices.find(x => x.id === c.deviceId); if (d) openDevice(d, c.port ? 'ports' : undefined, c.port); };
}

function HealthCard() {
  const { data } = useApp(); const [open, setOpen] = useState(false); const openCheck = useCheckOpener();
  const h = data.health; if (!h) return null;
  const top = h.checks.filter(c => c.level !== 'ok').slice(0, 2);
  const nWarn = h.checks.filter(c => c.level === 'bad' || c.level === 'warn').length;
  const n10 = nWarn % 10, n100 = nWarn % 100;
  const warnText = !nWarn ? 'Серьёзных замечаний нет' : `${nWarn} ${n10 === 1 && n100 !== 11 ? 'замечание требует' : n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14) ? 'замечания требуют' : 'замечаний требуют'} внимания`;
  return <>
    <Card title="Здоровье сети" right={<Btn size="sm" onClick={() => setOpen(true)}>Подробнее</Btn>}>
      <div className="row" style={{ gap: 14, cursor: 'pointer' }} onClick={() => setOpen(true)}>
        <ScoreRing score={h.score} size={58} />
        <div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 700 }}>{h.type.name}</div>
          <div className="dim" style={{ fontSize: 12.5 }}>{warnText}</div></div>
      </div>
      {top.length ? <div className="list" style={{ marginTop: 8 }}>{top.map((c, i) => <CheckItem key={i} c={{ ...c, text: '' }} onClick={openCheck} />)}</div> : null}
    </Card>
    {open ? <Modal title="Здоровье сети" wide onClose={() => setOpen(false)}><HealthBody h={h} onCheck={c => { setOpen(false); openCheck(c); }} /></Modal> : null}
  </>;
}
