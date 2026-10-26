/* «Карта сети» и «План»: холст занимает весь экран между шапкой и нижней панелью, а все кнопки собраны в одно выезжающее меню.
   Кнопка меню стоит в правом верхнем углу (на месте Frank, который теперь внутри меню). Разделы меню собирают сами окна: «Карта сети», «План», «Живая карта 3D».
   Окно «Живая карта» не вложено в меню, поэтому его разделы попадают в панель через общую шину workBus (WorkSlot — как порталь в панель). */
const workBus = { host: null, close: () => { }, subs: new Set(), set(host, close) { this.host = host; this.close = close; this.subs.forEach(f => f()); } };
function useWorkHost() {
  const [, tick] = useState(0);
  useEffect(() => { const f = () => tick(n => n + 1); workBus.subs.add(f); return () => { workBus.subs.delete(f); }; }, []);
  return workBus.host;
}
/* раздел меню из другого места дерева (например, из «Живой карты») */
function WorkSlot({ children }) { const host = useWorkHost(); return host ? ReactDOM.createPortal(children, host) : null; }
function WorkSec({ title, children }) { return <div className="wm-sec">{title ? <div className="wm-sec-t">{title}</div> : null}{children}</div>; }
/* строка-кнопка: значок, название, пояснение; on — включено (подсвечено); keep — меню остаётся открытым после нажатия */
function WorkItem({ icon, label, sub, on, danger, keep, disabled, right, onClick }) {
  return <button type="button" disabled={disabled} className={'wm-item' + (on ? ' on' : '') + (danger ? ' danger' : '')}
    onClick={() => { if (onClick) onClick(); if (!keep) workBus.close(); }}>
    {icon ? <Icon name={icon} size={19} /> : <span style={{ width: 19 }} />}
    <span className="wm-lbl"><span>{label}</span>{sub ? <small>{sub}</small> : null}</span>
    {right}{on ? <Icon name="check" size={16} /> : null}</button>;
}
function WorkSwitch({ icon, label, on, onChange }) {
  return <div className="wm-item sw"><Icon name={icon} size={19} /><span className="wm-lbl"><span>{label}</span></span><Switch on={on} onChange={onChange} /></div>;
}
/* выбор из нескольких: плитки в ряд */
function WorkChoice({ value, options, onChange, keep }) {
  return <div className="wm-choice">{options.map(o => <button key={o.value} type="button" className={value === o.value ? 'on' : ''}
    onClick={() => { onChange(o.value); if (!keep) workBus.close(); }}>{o.icon ? <Icon name={o.icon} size={17} /> : null}<span>{o.label}</span></button>)}</div>;
}
/* набор цветов: нажатие выбирает; '' — «по умолчанию» (авто) */
const WORK_COLORS = ['#0a84ff', '#30d158', '#ff9f0a', '#ff453a', '#bf5af2', '#64d2ff', '#ffd60a', '#ff6482', '#ac8e68', '#8e8e93', '#ffffff', '#1c1c1e'];
function WorkColors({ value, onChange, autoLabel = 'Авто' }) {
  return <div className="wm-colors">
    <button type="button" className={'auto' + (!value ? ' on' : '')} onClick={() => onChange('')} title={autoLabel}>{autoLabel}</button>
    {WORK_COLORS.map(c => <button key={c} type="button" className={value === c ? 'on' : ''} style={{ background: c }} onClick={() => onChange(c)} aria-label={c} />)}</div>;
}

/* title — заголовок панели; children — разделы этого окна. Внизу всегда: переключатель «Карта сети / План», «Редактирование», Frank. */
function WorkMenu({ title, children }) {
  const { admin, mode, setMode, mapView, setMapView, openFrank, refresh } = useApp();
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('wm') === '1');       // ?wm=1 — меню сразу открыто (для проверок)
  const close = () => setOpen(false);
  useEffect(() => { const h = e => e.key === 'Escape' && setOpen(false); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);
  const hostRef = useCallback(el => { workBus.set(el, () => setOpen(false)); }, []);          // ссылка постоянная: иначе панель на каждом рисовании теряла бы разделы «Живой карты»
  return <>
    {ReactDOM.createPortal(<button type="button" className={'wm-fab' + (open ? ' on' : '') + (mode === 'edit' && admin ? ' edit' : '')} data-tour="work-menu" title="Инструменты" aria-label="Меню инструментов" onClick={() => setOpen(!open)}>
      <Icon name={open ? 'x' : 'sliders'} size={22} stroke={2.2} /></button>, document.body)}
    {open ? ReactDOM.createPortal(<div className="wm-wrap" onClick={e => e.target === e.currentTarget && close()}>
      <div className="wm-panel">
        <div className="wm-head"><b className="grow">{title}</b></div>
        <div className="wm-body">
          <WorkSec><WorkChoice value={mapView} onChange={setMapView} options={[{ value: 'map', label: 'Карта сети', icon: 'map' }, { value: 'plan', label: 'План', icon: 'plan' }]} /></WorkSec>
          {children}
          <div ref={hostRef} className="wm-slots" />
          {admin ? <WorkSec title="Общее">
            <WorkSwitch icon="edit" label="Редактирование" on={mode === 'edit'} onChange={v => setMode(v ? 'edit' : 'view')} />
            <WorkItem icon="sparkle" label="Frank — помощник" onClick={openFrank} />
            <WorkItem icon="refresh" label="Обновить данные" onClick={refresh} />
          </WorkSec> : null}
        </div>
      </div>
    </div>, document.body) : null}
  </>;
}
