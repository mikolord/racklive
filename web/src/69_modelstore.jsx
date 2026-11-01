/* ───────── «Магазин моделей»: готовые карточки устройств из публичного каталога GitHub (фото с размеченными портами, границы приближения, 3D) ───────── */
const STORE_KIND = { router: 'Роутер', switch: 'Коммутатор', server: 'Сервер', nas: 'NAS', ap: 'Точка доступа', camera: 'Камера', nvr: 'Регистратор', ups: 'ИБП', pc: 'Компьютер', modem: 'Модем', other: 'Другое' };
const STORE_LIC = { own: 'своё фото', 'CC0-1.0': 'CC0', 'CC-BY-4.0': 'CC BY', 'CC-BY-SA-4.0': 'CC BY-SA', permission: 'с разрешения' };
const STORE_REPO = 'mikolord/racklive-models';

function StorePane({ item, onClose }) {
  const { refresh } = useApp(); const toast = useToast();
  const [idx, setIdx] = useState(null); const [q, setQ] = useState(''); const [sel, setSel] = useState(null); const [det, setDet] = useState(null);
  const [busy, setBusy] = useState(false); const [mod, setMod] = useState(false);
  const devPorts = item.device ? ((item.device.state || {}).ports || []).length : 0;
  const load = async force => { setIdx(null); try { setIdx(await api('/api/models/store/index' + (force ? '?refresh=1' : ''))); } catch (x) { setIdx({ ok: false, models: [], error: x.message }); } };
  useEffect(() => { load(false); }, []);
  const open = async m => { setSel(m); setDet(null); try { setDet(await api('/api/models/store/model/' + m.id)); } catch (x) { setDet({ ok: false, error: x.message }); } };
  const apply = async () => {
    setBusy(true);
    try { const r = await api('/api/models/store/apply', { method: 'POST', body: { id: sel.id, card: item.id } }); if (!r.ok) throw new Error(r.error || 'не получилось применить'); await refresh(); toast('Модель применена к карточке'); onClose(); }
    catch (x) { toast(x.message, true); } finally { setBusy(false); }
  };
  if (mod) return <ModerationPane onBack={() => { setMod(false); load(true); }} />;
  if (sel) {
    const c = det && det.ok ? det.card : null;
    return <div className="col" style={{ gap: 10 }}>
      <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={() => { setSel(null); setDet(null); }}>← Назад к списку</button>
      <div><b style={{ fontSize: 16 }}>{sel.title}</b><div className="dim" style={{ fontSize: 12.5 }}>{STORE_KIND[sel.kind] || sel.kind} · портов {sel.ports}{sel.model3d ? ' · есть 3D' : ''}{sel.license ? ' · фото: ' + (STORE_LIC[sel.license] || sel.license) + (sel.author ? ', ' + sel.author : '') : ''}</div></div>
      {!det ? <div className="dim" style={{ padding: 20, textAlign: 'center' }}>Загружаю…</div>
        : !det.ok ? <div className="cam-warn">{det.error}</div>
        : <>
          {det.has_photo ? <div className="m3-preview"><PhotoPorts url={'/api/models/store/photo/' + sel.id} spots={c.spots} sel={null} onPick={() => { }} zoom={c.pzoom} /></div> : null}
          {det.model3d ? <div className="m3-preview"><Model3D model={det.model3d} ports={[]} sel={null} onPick={() => { }} /></div> : null}
          {sel.notes ? <div className="dim" style={{ fontSize: 13 }}>{sel.notes}</div> : null}
          {devPorts && sel.ports && devPorts !== sel.ports ? <div className="cam-warn">У вашего устройства {devPorts} портов, а в модели отмечено {sel.ports}. Возможно, это другая ревизия или модификация — проверьте после применения.</div> : null}
          <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Модель заменит фото, отметки портов и границы приближения этой карточки{det.model3d ? ', а 3D-модель добавится в вашу библиотеку и будет выбрана' : ''}.</div>
          <div className="row wrap" style={{ gap: 8 }}><Btn kind="primary" icon="download" busy={busy} onClick={apply}>Применить к этой карточке</Btn><Btn onClick={() => { setSel(null); setDet(null); }}>Отмена</Btn></div></>}
    </div>;
  }
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const list = idx && idx.ok ? idx.models.filter(m => terms.every(t => (m.vendor + ' ' + m.model + ' ' + m.title + ' ' + (STORE_KIND[m.kind] || '')).toLowerCase().includes(t))) : [];
  return <div className="col" style={{ gap: 10 }}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Готовые карточки устройств из общего каталога: фото с размеченными портами и границами приближения. Найдите своё устройство и примените одной кнопкой — размечать вручную не нужно.</div>
    <input className="input" placeholder="Поиск: производитель или модель" value={q} onChange={ev => setQ(ev.target.value)} />
    {!idx ? <div className="dim" style={{ padding: 20, textAlign: 'center' }}>Загружаю каталог…</div>
      : !idx.ok ? <div className="cam-warn">{idx.error || 'каталог недоступен'}<div style={{ marginTop: 6 }}><Btn size="sm" onClick={() => load(true)}>Повторить</Btn></div></div>
      : !idx.models.length ? <div className="dim" style={{ padding: 20, textAlign: 'center', fontSize: 13 }}>В каталоге пока нет моделей. Свою модель можно сделать в приложении «Создать модель» (Настройки → Приложения).</div>
      : !list.length ? <div className="dim" style={{ padding: 20, textAlign: 'center', fontSize: 13 }}>Ничего не найдено. Вашей модели может не быть в каталоге — свою можно сделать в приложении «Создать модель» (Настройки → Приложения).</div>
      : list.map(m => <button key={m.id} type="button" className="plug-row" onClick={() => open(m)}>
        <span className="st-thumb">{m.photo ? <img src={'/api/models/store/photo/' + m.id} alt="" loading="lazy" draggable="false" /> : <Icon name="box" size={18} />}</span>
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{m.title}</b>
          <small>{STORE_KIND[m.kind] || m.kind} · портов {m.ports}{m.model3d ? ' · 3D' : ''}</small></span><Icon name="chevron" size={14} /></button>)}
    <div className="row wrap" style={{ gap: 8 }}>
      <Btn size="sm" icon="refresh" onClick={() => load(true)}>Обновить</Btn>
      <Btn size="sm" icon="shield" onClick={() => setMod(true)}>Модерация</Btn></div>
  </div>;
}

/* the owner of the catalog: requests (pull requests) with a preview; «Принять» only while the automatic check is green */
function ModerationPane({ onBack }) {
  const toast = useToast(); const confirm = useConfirm();
  const [tok, setTok] = useState(null); const [text, setText] = useState(''); const [list, setList] = useState(null); const [err, setErr] = useState('');
  const [pv, setPv] = useState(null); const [cur, setCur] = useState(null); const [comment, setComment] = useState(''); const [busy, setBusy] = useState(false);
  const loadList = async () => { setList(null); setErr(''); try { const r = await api('/api/models/store/pulls'); if (!r.ok) throw new Error(r.error); setList(r.pulls); } catch (x) { setErr(x.message); setList([]); } };
  const loadTok = async () => { try { const t = await api('/api/models/store/token'); setTok(t); if (t.has) loadList(); } catch (x) { setErr(x.message); setTok({ has: false }); } };
  useEffect(() => { loadTok(); }, []);
  const saveTok = async () => { setBusy(true); setErr(''); try { const r = await api('/api/models/store/token', { method: 'PUT', body: { token: text } }); if (!r.ok) throw new Error(r.error); setText(''); setTok(r); toast('Токен сохранён'); loadList(); } catch (x) { setErr(x.message); } finally { setBusy(false); } };
  const dropTok = async () => { if (!(await confirm('Удалить токен GitHub из Rack Live? Принимать заявки из приложения станет нельзя (на сам токен это не влияет — его можно отозвать на GitHub).', { title: 'Удалить токен', ok: 'Удалить', danger: true }))) return; try { setTok(await api('/api/models/store/token', { method: 'DELETE' })); setList(null); setPv(null); } catch (x) { toast(x.message, true); } };
  const open = async p => { setCur(p); setPv(null); setComment(''); try { const r = await api('/api/models/store/pulls/' + p.n); setPv(r.ok ? r : { ok: false, error: r.error }); } catch (x) { setPv({ ok: false, error: x.message }); } };
  const act = async what => {
    if (what === 'merge' && !(await confirm(`Принять заявку #${cur.n}? Модель сразу появится в каталоге у всех.`, { title: 'Принять модель', ok: 'Принять' }))) return;
    setBusy(true);
    try { const r = await api(`/api/models/store/pulls/${cur.n}/${what}`, { method: 'POST', body: { comment } }); if (r.ok === false) throw new Error(r.error); toast(what === 'merge' ? 'Заявка принята' : 'Заявка отклонена'); setCur(null); setPv(null); loadList(); }
    catch (x) { toast(x.message, true); } finally { setBusy(false); }
  };
  const BADGE = { green: ['✓ проверка пройдена', 'ok'], red: ['✗ проверка не пройдена', 'bad'], wait: ['… проверка идёт', 'wait'], none: ['нет результата проверки', 'wait'] };
  return <div className="col" style={{ gap: 10 }}>
    <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={cur ? () => { setCur(null); setPv(null); } : onBack}>← {cur ? 'К заявкам' : 'К каталогу'}</button>
    <div><b style={{ fontSize: 16 }}>Модерация каталога</b><div className="dim" style={{ fontSize: 12.5 }}>репозиторий {STORE_REPO}</div></div>
    {err ? <div className="cam-warn">{err}</div> : null}
    {!tok ? <div className="dim">Загружаю…</div> : !tok.has ? <div className="col" style={{ gap: 8 }}>
      <div className="dim" style={{ fontSize: 13, lineHeight: 1.55 }}>Чтобы принимать заявки здесь, нужен токен GitHub с доступом только к репозиторию каталога. Создайте его на GitHub: Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate. Repository access: Only select repositories → {STORE_REPO}. Permissions: Pull requests — Read and write, Contents — Read and write, Issues — Read and write, Commit statuses — Read-only. Скопируйте токен и вставьте ниже. Он хранится только на вашем сервере.</div>
      <input className="input mono" type="password" autoComplete="off" placeholder="github_pat_…" value={text} onChange={ev => setText(ev.target.value)} />
      <div><Btn kind="primary" busy={busy} disabled={!text.trim()} onClick={saveTok}>Сохранить токен</Btn></div></div>
      : !cur ? <>
        <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}><span className="dim" style={{ fontSize: 12.5 }}>Токен сохранён{tok.login ? ' · ' + tok.login : ''}</span><Btn size="sm" onClick={loadList}>Обновить</Btn><Btn size="sm" kind="danger" onClick={dropTok}>Удалить токен</Btn></div>
        {!list ? <div className="dim" style={{ padding: 16, textAlign: 'center' }}>Загружаю заявки…</div> : !list.length ? <div className="dim" style={{ padding: 16, textAlign: 'center', fontSize: 13 }}>Открытых заявок нет.</div>
          : list.map(p => <button key={p.n} type="button" className="plug-row" onClick={() => open(p)}><span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>#{p.n} · {p.title}</b>
            <small>{p.user}{p.bot ? ' (бот)' : ''} · <span className={'st-badge ' + BADGE[p.check][1]}>{BADGE[p.check][0]}</span></small></span><Icon name="chevron" size={14} /></button>)}</>
      : <>
        {!pv ? <div className="dim" style={{ padding: 16, textAlign: 'center' }}>Загружаю заявку…</div> : !pv.ok ? <div className="cam-warn">{pv.error}</div> : <>
          <div><b>{pv.card.meta.title}</b><div className="dim" style={{ fontSize: 12.5 }}>{STORE_KIND[pv.card.meta.kind]} · портов {pv.card.spots.length}{pv.has3d ? ' · есть 3D' : ''}{pv.card.license ? ' · фото: ' + (STORE_LIC[pv.card.license] || pv.card.license) + (pv.card.author ? ', ' + pv.card.author : '') : ''} · от {pv.user}</div></div>
          <div><span className={'st-badge ' + BADGE[pv.check][1]}>{BADGE[pv.check][0]}</span></div>
          {pv.outside && pv.outside.length ? <div className="cam-warn">Заявка меняет файлы вне models/: {pv.outside.join(', ')}. Принимать её нужно на GitHub вручную.</div> : null}
          {pv.photo ? <div className="m3-preview"><PhotoPorts url={pv.photo} spots={pv.card.spots} sel={null} onPick={() => { }} zoom={pv.card.pzoom} /></div> : null}
          {pv.body ? <pre className="m3-guide" style={{ maxHeight: 140 }}>{pv.body}</pre> : null}
          <div className="dim" style={{ fontSize: 12.5 }}>Проверьте: фон прозрачный, порты стоят на разъёмах, номера верные, у фото есть права. Фото в каталоге показывается именно так.</div>
          <textarea className="input" rows={2} placeholder="Комментарий автору при отклонении (что исправить)" value={comment} onChange={ev => setComment(ev.target.value)} />
          <div className="row wrap" style={{ gap: 8 }}>
            <Btn kind="primary" busy={busy} disabled={pv.check !== 'green' || !!(pv.outside && pv.outside.length)} onClick={() => act('merge')}>Принять</Btn>
            <Btn kind="danger" busy={busy} onClick={() => act('close')}>Отклонить</Btn>
            <a className="btn sm" href={`https://github.com/${STORE_REPO}/pull/${cur.n}`} target="_blank" rel="noopener noreferrer">Открыть на GitHub</a></div></>}</>}
  </div>;
}
