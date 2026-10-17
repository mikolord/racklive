/* Tools → «Демо-сцены и планы»: a scene is a made-up (or designed) network as data (rackd/scenes.py). Two things can be done with it:
   • look at it in an isolated demo copy of Rack Live (nothing of the real installation is involved);
   • apply its LAYOUT (houses, floors, rooms, racks) to the real plan — after a preview, with a copy saved first, and an undo. */
function SceneStats({ s }) {
  return <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>{[['устройств', s.devices], ['зданий', s.buildings], ['этажей', s.floors], ['комнат', s.rooms], ['шкафов', s.racks]].filter(x => x[1]).map(([l, n]) =>
    <span key={l} className="badge">{n} {l}</span>)}</div>;
}

function ScenesTool({ onBack }) {
  const toast = useToast(); const confirm = useConfirm(); const { refresh } = useApp();
  const [info, setInfo] = useState(null); const [busy, setBusy] = useState(''); const [apply, setApply] = useState(null); const [mgr, setMgr] = useState(false);
  const load = async () => { try { setInfo(await api('/api/scenes')); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t); }, []);
  if (!info) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загрузка…</div>;
  const sb = info.sandbox || {};
  const url = sb.running ? `${location.protocol === 'https:' ? 'http:' : location.protocol}//${location.hostname}:${sb.port}/#map` : '';
  const start = async s => { setBusy(s.id); try { const r = await api('/api/scenes/demo', { method: 'POST', body: { id: s.id } }); setInfo(i => ({ ...i, sandbox: r.sandbox })); } catch (e) { toast(e.message, true); } finally { setBusy(''); } };
  const stop = async () => { try { await api('/api/scenes/demo', { method: 'DELETE', body: {} }); load(); } catch (e) { toast(e.message, true); } };
  const undo = async b => {
    if (!(await confirm(`Вернуть план и шкафы, как они были до применения сцены «${b.scene || 'без названия'}» (${new Date(b.t * 1000).toLocaleString('ru-RU')})? То, что вы поменяли после этого на плане и в шкафах, пропадёт.`, { title: 'Вернуть как было', ok: 'Вернуть', danger: true }))) return;
    try { await api('/api/scenes/undo', { method: 'POST', body: { backup: b.id } }); toast('Возвращено'); refresh(); load(); } catch (e) { toast(e.message, true); }
  };
  const all = [...info.builtin, ...info.mine.map(m => ({ id: m.id, title: m.title, description: m.description, stats: m.stats, mine: true, source: m.source, author: m.author }))];
  return <>
    <button type="button" className="link-btn" onClick={onBack} style={{ marginBottom: 8 }}>‹ Все инструменты</button>
    <Hint id="scenes">Сцена — это описание сети: устройства, кабели, шкафы, дома с этажами и комнатами. Её можно посмотреть в отдельной демо-копии (ваши настоящие устройства и пароли там не участвуют) или перенести на свой план: так можно быстро нарисовать дом или офис по описанию. Сцены для вас может составить нейросеть по инструкции из кнопки «Как написать сцену».</Hint>
    {sb.running ? <div className="card" style={{ marginBottom: 10, borderColor: 'var(--accent)' }}><div className="row wrap" style={{ gap: 10, alignItems: 'center' }}>
      <span className="spin-dot" /><div className="grow" style={{ minWidth: 0 }}><b>Демо «{sb.title}» запущено</b>
        <div className="dim" style={{ fontSize: 12.5 }}>Отдельная копия на порту {sb.port}, осталось ~{Math.ceil(sb.left / 60)} мин, потом остановится сама. {location.protocol === 'https:' ? 'Открывается по домашнему адресу (http), вне дома не заработает.' : ''}</div></div>
      <a className="btn primary" href={url} target="_blank" rel="noreferrer"><Icon name="link" size={16} />Открыть демо</a><Btn onClick={stop}>Остановить</Btn></div></div> : null}
    <div className="plug-grid">{all.map(s => <div key={s.id} className="card tool-card" style={{ display: 'block' }}>
      <div className="row" style={{ gap: 8 }}><b className="grow">{s.title}</b><span className="badge">{s.builtin ? 'встроенная' : s.source === 'community' ? 'сообщество' : 'своя'}</span></div>
      <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.45, marginTop: 4 }}>{s.description}</div>
      <SceneStats s={s.stats} />
      <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
        <Btn size="sm" kind="primary" icon="play" busy={busy === s.id} disabled={!!busy} onClick={() => start(s)}>Посмотреть в демо</Btn>
        <Btn size="sm" onClick={() => setApply(s)}>Применить к моему плану…</Btn>
        {s.mine ? <Btn size="sm" kind="danger" icon="trash" onClick={async () => { if (await confirm(`Убрать сцену «${s.title}» из Rack Live?`, { danger: true, ok: 'Убрать' })) { await api('/api/community/' + s.id, { method: 'DELETE', body: {} }); load(); } }} /> : null}
      </div></div>)}
      <button type="button" className="card tool-card soon" onClick={() => setMgr(true)}><div className="tool-ic" style={{ background: 'var(--fill)' }}><Icon name="plus" size={22} /></div>
        <div className="grow" style={{ textAlign: 'left' }}><b>Загрузить свою сцену (.zip)</b><div className="dim" style={{ fontSize: 12.5, lineHeight: 1.4, marginTop: 3 }}>Её можно составить с помощью нейросети: скачайте инструкцию ниже и отдайте ей вместе с описанием.</div></div></button>
    </div>
    <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
      <a className="btn" href="/api/community/guide.txt?kind=scene" download>Как написать сцену (инструкция для нейросети)</a>
      <a className="btn" href="/api/community/template.zip?kind=scene" download>Пример сцены (.zip)</a></div>
    {info.backups.length ? <Card title="Копии плана перед применением сцен" style={{ marginTop: 14 }}>
      <div className="dim3" style={{ fontSize: 12.5, marginBottom: 6 }}>Перед каждым применением Rack Live сохраняет прежние план и шкафы. Последние 12 хранятся здесь.</div>
      <div className="list">{info.backups.map(b => <div className="li" key={b.id} style={{ alignItems: 'center' }}><div className="grow" style={{ minWidth: 0 }}><b>{new Date(b.t * 1000).toLocaleString('ru-RU')}</b>
        <div className="dim" style={{ fontSize: 12.5 }}>перед сценой «{b.scene || '—'}» · {b.mode === 'replace' ? 'замена' : 'добавление'} · было зданий: {b.buildings}, шкафов: {b.racks}</div></div>
        <Btn size="sm" onClick={() => undo(b)}>Вернуть как было</Btn></div>)}</div></Card> : null}
    {apply ? <ApplyScene scene={apply} onClose={() => { setApply(null); load(); }} /> : null}
    {mgr ? <CommunityManager onClose={() => { setMgr(false); load(); }} /> : null}
  </>;
}

function ApplyScene({ scene, onClose }) {
  const { refresh } = useApp(); const toast = useToast(); const confirm = useConfirm(); const { data } = useApp();
  const [pv, setPv] = useState(null); const [map, setMap] = useState({}); const [mode, setMode] = useState('add'); const [busy, setBusy] = useState(false); const [done, setDone] = useState(null);
  useEffect(() => { api('/api/scenes/preview', { method: 'POST', body: { id: scene.id } }).then(r => { setPv(r); setMap(Object.fromEntries(r.devices.map(d => [d.key, d.suggest || '']))); }).catch(e => { toast(e.message, true); onClose(); }); }, []);
  const real = data.devices.filter(d => d.driver !== 'site_node');
  if (!pv) return <Modal title="Применить сцену" onClose={onClose}><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Смотрю сцену…</div></Modal>;
  const chosen = Object.values(map).filter(Boolean); const dup = chosen.length !== new Set(chosen).size;
  const tied = chosen.length;
  const go = async () => {
    const warn = mode === 'replace' ? `Заменить ваши текущие план (зданий: ${(data.plan.buildings || []).length}) и шкафы (${(data.racks || []).length}) сценой «${pv.title}»?` : `Добавить сцену «${pv.title}» к вашему плану и шкафам?`;
    if (!(await confirm(`${warn}\n\nТронутся только план помещений и шкафы / щитки. Устройства, пароли и настройки не меняются. Перед применением Rack Live сохранит прежнее — вернуть можно кнопкой «Вернуть как было».`, { title: 'Применить сцену', ok: mode === 'replace' ? 'Заменить' : 'Добавить', danger: mode === 'replace' }))) return;
    setBusy(true);
    try { const r = await api('/api/scenes/apply', { method: 'POST', body: { id: scene.id, mode, mapping: Object.fromEntries(Object.entries(map).filter(([, v]) => v)) } }); setDone(r); refresh(); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const undo = async () => { try { await api('/api/scenes/undo', { method: 'POST', body: { backup: done.backup } }); toast('Возвращено, как было'); refresh(); onClose(); } catch (e) { toast(e.message, true); } };
  if (done) return <Modal title="Сцена применена" onClose={onClose} footer={<><Btn onClick={undo}>Вернуть как было</Btn><div className="grow" /><Btn kind="primary" onClick={onClose}>Готово</Btn></>}>
    <div className="plugin-result"><Icon name="check" size={16} /> Добавлено зданий: <b>{done.buildings}</b>, шкафов и мест: <b>{done.racks}</b>, привязано устройств: <b>{done.tied}</b>{done.dropped ? `; мест устройств без пары: ${done.dropped} (они на плане не появились)` : ''}.</div>
    <div className="dim" style={{ fontSize: 13, marginTop: 8 }}>Откройте «Карта → План» и «Главная → шкаф». Если что-то не так, «Вернуть как было» восстановит прежний план и шкафы.</div></Modal>;
  return <Modal title={`Применить «${pv.title}»`} wide onClose={onClose}
    footer={<><Btn onClick={onClose}>Отмена</Btn><div className="grow" /><Btn kind="primary" busy={busy} disabled={dup} onClick={go}>{mode === 'replace' ? 'Заменить план и шкафы' : 'Добавить к плану'}</Btn></>}>
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>В сцене: зданий {pv.stats.buildings}, этажей {pv.stats.floors}, комнат {pv.stats.rooms}, шкафов {pv.stats.racks}. Выдуманные устройства из сцены в вашу установку <b>не попадают</b>: на плане и в шкафах появятся только места. Если место должно быть занято вашим настоящим устройством, привяжите его ниже.</div>
    <Field label="Как применить">
      <Seg value={mode} onChange={setMode} options={[{ value: 'add', label: 'Добавить к моему плану' }, { value: 'replace', label: 'Заменить мой план и шкафы' }]} /></Field>
    {mode === 'replace' ? <div className="err-note" style={{ marginTop: 0 }}><b>Заменить</b> удалит ваши текущие здания{pv.hasPlan ? '' : ' (их нет)'} и шкафы{pv.hasRacks ? '' : ' (их нет)'} и поставит вместо них сцену. Копия сохранится, и вернуть можно кнопкой.</div> : null}
    {pv.devices.length ? <>
      <div className="card-title" style={{ marginTop: 10 }}>Какие ваши устройства поставить на их места ({tied} из {pv.devices.length})</div>
      <div className="list" style={{ maxHeight: 320, overflow: 'auto' }}>{pv.devices.map(d => <div className="li" key={d.key} style={{ alignItems: 'center', gap: 8 }}>
        <KindIcon kind={d.kind === 'web' ? 'other' : d.kind} size={26} round={8} /><div className="grow" style={{ minWidth: 0 }}><div className="ellipsis">{d.name}</div><div className="dim3 mono" style={{ fontSize: 11.5 }}>{d.ip || d.kind}</div></div>
        <select className="input" style={{ maxWidth: 220 }} value={map[d.key] || ''} onChange={e => setMap({ ...map, [d.key]: e.target.value })}>
          <option value="">— не привязывать —</option>{real.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></div>)}</div>
      {dup ? <div className="err-note">Одно и то же устройство выбрано для двух мест. Оставьте его только у одного.</div> : null}</> : null}
  </Modal>;
}
