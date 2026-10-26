/* ───────── Карта сети → узел → «Иконка»: the icon of a device or client, chosen by hand (rackd/icons.py) ─────────
   data.icons = {map node id: 'std:<name>' | 'up:<id>'}; data.iconLib = the uploaded pictures. No choice = the icon of the kind, as before. */
const iconUrl = id => '/api/icons/file/' + id;
const isUpIcon = spec => typeof spec === 'string' && spec.startsWith('up:');
function NodeGlyph({ spec, kind, size = 18, color = 'currentColor', svg }) {
  if (isUpIcon(spec)) {
    const u = iconUrl(spec.slice(3));
    return svg ? <image href={u} width={size} height={size} preserveAspectRatio="xMidYMid meet" />
      : <img src={u} width={size} height={size} alt="" draggable="false" style={{ display: 'block', objectFit: 'contain' }} />;
  }
  return <Icon name={typeof spec === 'string' && spec.startsWith('std:') ? spec.slice(4) : kind} size={size} color={color} />;
}

function IconPicker({ nodeKey, kind, title, onClose }) {
  const { data, refresh } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const cur = (data.icons || {})[nodeKey] || '';
  const lib = data.iconLib || [];
  const [q, setQ] = useState(''); const [busy, setBusy] = useState(false); const file = useRef(null);
  const headers = () => { const h = {}; const tok = ssGet('rl_tok'); if (tok) h['X-RL-Session'] = tok; return h; };
  const set = async icon => {
    setBusy(true);
    try { await api('/api/icons/set', { method: 'PUT', body: { key: nodeKey, icon } }); await refresh(); onClose(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const upload = async f => {
    if (!f) return; setBusy(true);
    try {
      const j = await (await fetch('/api/icons', { method: 'POST', credentials: 'same-origin', headers: { ...headers(), 'X-Icon-Name': encodeURIComponent(f.name) }, body: f })).json();
      if (!j.ok) throw new Error(j.error || 'не получилось загрузить');
      await api('/api/icons/set', { method: 'PUT', body: { key: nodeKey, icon: 'up:' + j.icon.id } }); await refresh(); onClose();
    } catch (e) { toast(e.message, true); } finally { setBusy(false); if (file.current) file.current.value = ''; }
  };
  const del = async e => {
    if (!(await confirm(`Удалить иконку «${e.name}»? Устройства, которые её использовали, вернутся к обычной.`, { title: 'Удалить иконку', ok: 'Удалить', danger: true }))) return;
    try { await fetch('/api/icons/' + e.id, { method: 'DELETE', credentials: 'same-origin', headers: headers() }); await refresh(); } catch (x) { toast(x.message, true); }
  };
  const shown = ICON_PACK.filter(([n, l]) => !q || (n + ' ' + l).toLowerCase().includes(q.toLowerCase()));
  const tile = (key, label, glyph, on, onClick, extra) => <div className={'ip-tile' + (on ? ' on' : '')} key={key}>
    <button type="button" className="ip-btn" disabled={busy} onClick={onClick} title={label}>{glyph}<span className="ip-cap">{label}</span></button>{extra}</div>;
  return <Modal title={'Иконка: ' + (title || '')} onClose={onClose} wide
    footer={<><Btn onClick={onClose}>Закрыть</Btn>{cur ? <Btn onClick={() => set('')}>Вернуть обычную</Btn> : null}</>}>
    <div className="row" style={{ gap: 8, marginBottom: 10 }}><div className="grow"><SearchBox value={q} onChange={setQ} placeholder="Найти иконку" /></div>
      <Btn icon="upload" disabled={busy} onClick={() => file.current && file.current.click()}>Загрузить</Btn>
      <input ref={file} type="file" accept=".svg,.png,.webp,image/svg+xml,image/png,image/webp" style={{ display: 'none' }} onChange={e => upload(e.target.files[0])} /></div>
    <div className="ip-grid">
      {!q ? tile('auto', 'Обычная', <Icon name={kind} size={26} />, !cur, () => set('')) : null}
      {shown.map(([n, l]) => tile(n, l, <Icon name={n} size={26} />, cur === 'std:' + n, () => set('std:' + n)))}
    </div>
    {lib.length && !q ? <><div className="card-title" style={{ margin: '14px 0 8px' }}>Свои иконки</div>
      <div className="ip-grid">{lib.map(e => tile('u' + e.id, e.name, <img src={iconUrl(e.id)} width={26} height={26} alt="" draggable="false" style={{ objectFit: 'contain' }} />, cur === 'up:' + e.id, () => set('up:' + e.id),
        <button type="button" className="ip-del" title="Удалить из библиотеки" onClick={() => del(e)}><Icon name="x" size={12} /></button>))}</div></> : null}
    <div className="dim3" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.5 }}>Свои иконки: SVG, PNG или WebP до 100 КБ, лучше квадратные. Одну загруженную иконку можно выбрать для любого устройства.</div>
  </Modal>;
}
