/* UI kit */
function Btn({ children, kind = '', size = '', icon, busy, onClick, disabled, title, type = 'button', style }) {
  const [self, setSelf] = useState(false);
  const click = async (e) => {
    if (!onClick) return;
    const r = onClick(e);
    if (r && r.then) { setSelf(true); try { await r; } finally { setSelf(false); } }
  };
  const cls = ['btn', kind, size, (busy || self) ? 'busy' : '', !children && icon ? 'icon' : ''].join(' ');
  return <button type={type} className={cls} onClick={click} disabled={disabled} title={title} style={style}>
    {icon && !(busy || self) ? <Icon name={icon} size={size === 'sm' ? 15 : 17} /> : null}{children}</button>;
}

/* while a modal / sheet is open the page behind must not scroll (on the phone a swipe used to fall through to it) */
let openOverlays = 0;
function useLockPage() {
  useEffect(() => {
    openOverlays++; document.documentElement.classList.add('modal-open');
    return () => { if (--openOverlays <= 0) { openOverlays = 0; document.documentElement.classList.remove('modal-open'); } };
  }, []);
}

function Modal({ title, onClose, children, footer, wide, icon }) {
  useLockPage();
  useEffect(() => {
    const h = e => e.key === 'Escape' && onClose && onClose();
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return <div className="overlay" onMouseDown={e => e.target === e.currentTarget && onClose && onClose()}>
    <div className={'modal' + (wide ? ' wide' : '')}>
      <div className="modal-head">{icon}<h3>{title}</h3>{onClose ? <Btn icon="x" size="sm" onClick={onClose} /> : null}</div>
      <div className="modal-body">{children}</div>
      {footer ? <div className="modal-foot">{footer}</div> : null}
    </div>
  </div>;
}

function Sheet({ onClose, head, tabs, tab, setTab, children }) {
  useLockPage();
  useEffect(() => {
    const h = e => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h);
  }, [onClose]);
  return <div className="overlay" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <div className="sheet">
      <div className="sheet-head">
        <div className="row" style={{ alignItems: 'flex-start' }}><div className="grow">{head}</div><Btn icon="x" size="sm" onClick={onClose} /></div>
        {tabs && tabs.length > 1 ? <div className="sheet-tabs">{tabs.map(t => <button key={t.id} className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>{t.label}</button>)}</div> : <div style={{ height: 12, borderBottom: '.5px solid var(--line)' }} />}
      </div>
      <div className="sheet-body">{children}</div>
    </div>
  </div>;
}

function Field({ label, hint, children }) {
  return <div className="field">{label ? <label>{label}</label> : null}{children}{hint ? <div className="hint">{hint}</div> : null}</div>;
}
function Switch({ on, onChange, disabled }) {
  return <button type="button" className={'switch' + (on ? ' on' : '')} onClick={() => !disabled && onChange(!on)} aria-pressed={on} />;
}
function Seg({ value, options, onChange, className = '' }) {
  return <div className={'seg ' + className}>{options.map(o => <button key={o.value} className={(value === o.value ? 'on ' : '') + (o.cls || '')}
    onClick={() => onChange(o.value)} title={o.label}>{o.icon ? <Icon name={o.icon} size={14} /> : null}<span className={o.icon ? 'seg-label' : ''}>{o.label}</span></button>)}</div>;
}
function StatusBadge({ status, text }) {
  return <span className={'badge ' + (status || '')}><span className={'dot ' + (status || '')} />{text || STATUS_TEXT[status] || status}</span>;
}

function Sparkline({ points, field, color = 'var(--accent)' }) {
  const vals = (points || []).map(p => p[field]).filter(v => typeof v === 'number');
  if (vals.length < 3) return null;
  const max = Math.max(...vals, 1), min = Math.min(...vals, 0), w = 120, h = 34;
  const d = vals.map((v, i) => `${i ? 'L' : 'M'}${(i / (vals.length - 1)) * w},${h - 3 - ((v - min) / (max - min || 1)) * (h - 8)}`).join(' ');
  return <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
    <path d={d + ` L${w},${h} L0,${h} Z`} fill={color} opacity=".15" /><path d={d} fill="none" stroke={color} strokeWidth="1.5" /></svg>;
}
function Stat({ k, v, unit, level, spark, sparkField, color }) {
  return <div className={'stat ' + (level === 'warn' ? 'warn' : level === 'bad' ? 'bad' : '')}>
    {spark ? <Sparkline points={spark} field={sparkField} color={color} /> : null}
    <div style={{ position: 'relative' }}><div className="k">{k}</div><div className="v">{v == null || v === '' ? '—' : v}{unit ? <small>{unit}</small> : null}</div></div>
  </div>;
}
function Bar({ value, warnAt = 80, badAt = 92 }) {
  const v = Math.max(0, Math.min(100, value || 0));
  return <div className={'bar ' + (v >= badAt ? 'bad' : v >= warnAt ? 'warn' : '')}><i style={{ width: v + '%' }} /></div>;
}
function KV({ rows }) {
  return <div className="kv">{rows.map(([k, v], i) => <Fragment key={i}><div>{k}</div><div>{v == null || v === '' ? '—' : v}</div></Fragment>)}</div>;
}
function Card({ title, right, children, pad = true, className = '', style }) {
  return <div className={'card ' + (pad ? 'pad ' : '') + className} style={style}>
    {title ? <div className="card-title"><span className="grow">{title}</span>{right}</div> : null}{children}</div>;
}
function SearchBox({ value, onChange, placeholder = 'Поиск' }) {
  return <div className="search"><Icon name="search" size={15} /><input className="input" value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)} /></div>;
}

/* Hints for newcomers: on unless switched off in Settings; each can be dismissed in this browser («Понятно») */
const HINTS_KEY = 'rl_hints_hidden';
const hiddenHints = () => { try { return JSON.parse(localStorage.getItem(HINTS_KEY) || '[]'); } catch (e) { return []; } };
const setHiddenHints = list => { try { list.length ? localStorage.setItem(HINTS_KEY, JSON.stringify(list)) : localStorage.removeItem(HINTS_KEY); } catch (e) { } };
function Hint({ id, title, children, style }) {
  const { data } = useApp();
  const [hidden, setHidden] = useState(() => hiddenHints().includes(id));
  if (hidden || (data.settings || {}).hints === false) return null;
  return <div className="hint-box" style={style}>
    <div className="hint-ico"><Icon name="bulb" size={17} /></div>
    <div className="grow">{title ? <b>{title}</b> : null}<div>{children}</div></div>
    <button type="button" className="hint-close" onClick={() => { setHiddenHints([...new Set([...hiddenHints(), id])]); setHidden(true); }}>Понятно</button>
  </div>;
}

/* copy to the clipboard; on plain http (no Clipboard API) a hidden textarea + execCommand — it must run inside the tap, so no await before it */
function copyText(text) {
  try { if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text); return true; } } catch (e) { }
  const ta = document.createElement('textarea');
  ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px';
  document.body.appendChild(ta); ta.focus(); ta.select(); ta.setSelectionRange(0, text.length);
  let ok = false; try { ok = document.execCommand('copy'); } catch (e) { }
  ta.remove(); return ok;
}

/* Promise-based confirm dialog */
const ConfirmCtx = createContext(null);
function ConfirmHost({ children }) {
  const [q, setQ] = useState(null);
  const ask = useCallback((text, opts = {}) => new Promise(res => setQ({ text, opts, res })), []);
  const done = v => { q.res(v); setQ(null); };
  return <ConfirmCtx.Provider value={ask}>{children}
    {q ? <Modal title={q.opts.title || 'Подтвердите'} onClose={() => done(false)}
      footer={<><Btn onClick={() => done(false)}>Отмена</Btn><Btn kind={q.opts.danger ? 'danger' : 'primary'} onClick={() => done(true)}>{q.opts.ok || 'Продолжить'}</Btn></>}>
      <div style={{ fontSize: 15, lineHeight: 1.45 }}>{q.text}</div></Modal> : null}
  </ConfirmCtx.Provider>;
}
const useConfirm = () => useContext(ConfirmCtx);

function useHistory(deviceId, enabled, port) {
  const [h, setH] = useState(null);
  useEffect(() => {
    if (!enabled || !deviceId) return;
    let alive = true; setH(null);
    const load = () => api('/api/history/' + deviceId + (port ? '?port=' + port : '')).then(x => alive && setH(x)).catch(() => {});
    load(); const t = setInterval(load, 60000); return () => { alive = false; clearInterval(t); };
  }, [deviceId, enabled, port]);
  return h;
}

/* Two-series area chart for 24h traffic (bits/s) */
function TrafficChart({ points }) {
  const [hover, setHover] = useState(null);
  const pts = (points || []).filter(p => p.rx != null);
  if (pts.length < 2) return <div className="dim3" style={{ fontSize: 13, padding: '18px 0', textAlign: 'center' }}>График появится через несколько минут — данные копятся с каждым опросом</div>;
  const W = 600, H = 150, pad = 4, t0 = pts[0].t, t1 = pts[pts.length - 1].t;
  const max = Math.max(1000, ...pts.map(p => Math.max(p.rx, p.tx))) * 1.1;
  const X = t => pad + (t - t0) / Math.max(1, t1 - t0) * (W - pad * 2), Y = v => H - 18 - v / max * (H - 30);
  const line = k => pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p[k]).toFixed(1)}`).join(' ');
  const area = k => line(k) + ` L${X(t1)},${H - 18} L${X(t0)},${H - 18} Z`;
  const hp = hover != null ? pts[hover] : pts[pts.length - 1];
  const onMove = e => { const r = e.currentTarget.getBoundingClientRect(); const t = t0 + (e.clientX - r.left) / r.width * (t1 - t0);
    let best = 0; pts.forEach((p, i) => { if (Math.abs(p.t - t) < Math.abs(pts[best].t - t)) best = i; }); setHover(best); };
  const ticks = [0, .25, .5, .75, 1].map(f => t0 + (t1 - t0) * f);
  return <div>
    <div className="row wrap" style={{ gap: '4px 16px', fontSize: 13, marginBottom: 6 }}>
      <span className="row" style={{ gap: 6, whiteSpace: 'nowrap' }}><i style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--accent)' }} />К устройству <b>{fmt.bps(hp.tx)}</b></span>
      <span className="row" style={{ gap: 6, whiteSpace: 'nowrap' }}><i style={{ width: 10, height: 10, borderRadius: 3, background: 'var(--green)' }} />От устройства <b>{fmt.bps(hp.rx)}</b></span>
      <span className="grow" /><span className="dim3" style={{ whiteSpace: 'nowrap' }}>{new Date(hp.t * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>
    </div>
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      {[.25, .5, .75].map(f => <line key={f} x1={0} x2={W} y1={Y(max / 1.1 * f)} y2={Y(max / 1.1 * f)} stroke="var(--line)" />)}
      <path d={area('tx')} fill="var(--accent)" opacity=".18" /><path d={line('tx')} fill="none" stroke="var(--accent)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
      <path d={area('rx')} fill="var(--green)" opacity=".15" /><path d={line('rx')} fill="none" stroke="var(--green)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
      {hover != null ? <line x1={X(hp.t)} x2={X(hp.t)} y1={0} y2={H - 18} stroke="var(--text3)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" /> : null}
    </svg>
    <div className="row between dim3 mono" style={{ fontSize: 10.5, marginTop: 2 }}>{ticks.map((t, i) => <span key={i}>{new Date(t * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</span>)}</div>
    <div className="dim3" style={{ fontSize: 11.5, marginTop: 4 }}>Пик за период: {fmt.bps(max / 1.1)}</div>
  </div>;
}
