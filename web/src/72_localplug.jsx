/* ───────── «Локальные плагины»: собственный код владельца, который работает внутри Rack Live и меняет его (rackd/localplug.py) ─────────
   Загружается вручную .zip, лежит выключенным; включение — отдельный шаг после просмотра кода. Backend: /api/localplug*, /api/x/<id>/… */
function LocalPlugDetail({ p, killed, onBack, onChanged }) {
  const toast = useToast(); const confirm = useConfirm();
  const [file, setFile] = useState(''); const [text, setText] = useState(''); const [busy, setBusy] = useState('');
  const open = async n => { setFile(n); setText('Загружаю…'); try { setText((await api('/api/localplug/code?id=' + encodeURIComponent(p.id) + '&file=' + encodeURIComponent(n))).text); } catch (x) { setText(x.message); } };
  const act = async (path, body, ok) => { setBusy(path); try { const r = await api('/api/localplug/' + path, { method: 'POST', body }); toast(ok || r.note || 'Готово'); await onChanged(); } catch (x) { toast(x.message, true); } finally { setBusy(''); } };
  const enable = async () => {
    if (await confirm(`Включить «${p.title}»?\n\nЭто программа, которая будет работать внутри Rack Live с теми же правами: видеть ваши устройства и данные, менять настройки, ходить в сеть. Включайте только код, который вы написали или прочитали.\n\nКод (отпечаток): ${p.digest.slice(0, 16)}\nФайлы: ${p.files.join(', ')}\n\nЕсли плагин упадёт при запуске, он выключится сам.`, { title: 'Включить локальный плагин', ok: 'Включить', danger: true }))
      act('enable', { id: p.id, digest: p.digest }, 'Плагин включён');
  };
  const remove = async () => { if (await confirm(`Удалить «${p.title}»? Его код будет стёрт. Его данные останутся, пока вы не удалите и их.`, { title: 'Удалить плагин', ok: 'Удалить', danger: true })) { await act('remove', { id: p.id, wipe: false }, 'Удалено'); onBack(); } };
  return <div className="col" style={{ gap: 12 }}>
    <button type="button" className="link-btn" style={{ alignSelf: 'flex-start' }} onClick={onBack}>← К списку плагинов</button>
    <div><b style={{ fontSize: 17 }}>{p.title}</b> <span className={'st-badge ' + (p.live ? 'ok' : p.error ? 'bad' : 'wait')}>{p.live ? 'работает' : p.error ? 'ошибка' : p.changed ? 'код изменился' : 'выключен'}</span>
      <div className="dim" style={{ fontSize: 12.5 }}>версия {p.version}{p.author ? ' · ' + p.author : ''} · код {p.digest.slice(0, 12)}</div></div>
    <div style={{ fontSize: 14, lineHeight: 1.5 }}>{p.description}</div>
    {p.error ? <div className="cam-warn" style={{ whiteSpace: 'pre-wrap', fontSize: 12.5 }}>{p.error}</div> : null}
    {p.changed ? <div className="cam-warn">Код плагина изменился с момента включения. Он выключен, пока вы не посмотрите и не включите его заново.</div> : null}
    <div className="row wrap" style={{ gap: 8 }}>
      {p.live ? <Btn busy={busy === 'disable'} disabled={!!busy} onClick={() => act('disable', { id: p.id })}>Выключить</Btn>
        : <Btn kind="primary" busy={busy === 'enable'} disabled={!!busy || killed} onClick={enable}>Включить…</Btn>}
      {p.live && p.has_panel ? <a className="btn primary" href={`/api/x/${p.id}/files/panel.html`} target="_blank" rel="noopener noreferrer">Открыть панель</a> : null}
      <Btn kind="danger" disabled={!!busy} onClick={remove}>Удалить</Btn></div>
    {p.live && p.has_ui ? <div className="dim" style={{ fontSize: 12.5 }}>Скрипт интерфейса (ui.js) подключается при загрузке страницы: обновите страницу.</div> : null}
    <b style={{ fontSize: 14 }}>Код плагина (прочитайте перед включением)</b>
    <div className="row wrap" style={{ gap: 6 }}>{p.files.map(n => <button key={n} type="button" className={'chip' + (n === file ? ' on' : '')} onClick={() => open(n)}>{n}</button>)}</div>
    {file ? <pre className="m3-guide" style={{ maxHeight: 360, whiteSpace: 'pre-wrap' }}>{text}</pre> : <div className="dim" style={{ fontSize: 12.5 }}>Выберите файл, чтобы посмотреть его.</div>}
    {p.log && p.log.length ? <><b style={{ fontSize: 14 }}>Журнал плагина</b><pre className="m3-guide" style={{ maxHeight: 180, whiteSpace: 'pre-wrap' }}>{p.log.join('\n')}</pre></> : null}
  </div>;
}

function LocalPlugTool() {
  const toast = useToast(); const fileRef = useRef(null);
  const [data, setData] = useState(null); const [cur, setCur] = useState(null); const [rep, setRep] = useState(null); const [busy, setBusy] = useState(false); const [guide, setGuide] = useState('');
  const load = async () => { try { setData(await api('/api/localplug')); } catch (x) { setData({ plugins: [], error: x.message }); } };
  useEffect(() => { load(); }, []);
  const upload = async f => {
    if (!f) return; setBusy(true); setRep(null);
    try {
      const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: f };
      const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
      const r = await fetch('/api/localplug/upload', init); const j = await r.json();
      if (!r.ok && !j.errors) throw new Error(j.error || 'ошибка ' + r.status);
      setRep(j); if (j.ok) { toast('Загружен (выключен)'); await load(); setCur(j.plugin.id); }
    } catch (x) { toast(x.message, true); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  if (!data) return <div className="dim" style={{ padding: 20, textAlign: 'center' }}>Загружаю…</div>;
  const p = cur && data.plugins.find(x => x.id === cur);
  if (p) return <LocalPlugDetail p={p} killed={data.killed} onBack={() => setCur(null)} onChanged={load} />;
  return <div className="col" style={{ gap: 14 }}>
    <div className="cam-warn" style={{ lineHeight: 1.5 }}>{data.warning}</div>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.55 }}>Это ваши собственные дополнения для самого Rack Live: свои страницы и команды сервера, фоновые задачи, скрипты в интерфейсе. Они не попадают в каталог и на GitHub: загружаются только вами, вручную, и лежат выключенными, пока вы не прочитаете код и не включите.</div>
    {data.error ? <div className="cam-warn">{data.error}</div> : null}
    {data.killed ? <div className="cam-warn">Локальные плагины выключены целиком (файл OFF в папке data/local-plugins или переменная RL_NO_LOCAL_PLUGINS). Включить их нельзя, пока это не снято.</div> : null}
    {data.demo ? <div className="cam-warn">В демо-режиме плагины не загружаются.</div> : null}
    <b style={{ fontSize: 15 }}>Мои локальные плагины</b>
    {!data.plugins.length ? <div className="dim" style={{ fontSize: 13 }}>Пока нет ни одного.</div>
      : data.plugins.map(x => <button key={x.id} type="button" className="plug-row" onClick={() => setCur(x.id)}>
        <span className="ico-circle"><Icon name="box" size={16} /></span>
        <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{x.title}</b>
          <small><span className={'st-badge ' + (x.live ? 'ok' : x.error ? 'bad' : 'wait')}>{x.live ? 'работает' : x.error ? 'ошибка' : x.changed ? 'код изменился' : 'выключен'}</span> версия {x.version}</small></span><Icon name="chevron" size={14} /></button>)}
    <b style={{ fontSize: 15 }}>Загрузить плагин</b>
    <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Архив .zip с plugin.json и файлами main.py (функция register(api)), ui.js, panel.html. Описание формата: docs/LOCAL_PLUGINS.md.</div>
    <b style={{ fontSize: 15 }}>Написать с помощью ИИ</b>
    <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Скопируйте инструкцию и отдайте её любому ИИ вместе с описанием того, что нужно: он напишет плагин по правилам Rack Live (только свои данные, без лишних прав, без подмены кода) и объяснит, что плагин делает. Тем же ИИ можно проверить чужой плагин перед включением.</div>
    <div className="row wrap" style={{ gap: 8 }}>
      <Btn onClick={async () => { try { const r = await fetch('/api/localplug/guide.txt', { credentials: 'same-origin', headers: ssGet('rl_tok') ? { 'X-RL-Session': ssGet('rl_tok') } : {} }); const t = await r.text(); try { await navigator.clipboard.writeText(t); toast('Инструкция скопирована'); } catch (e) { setGuide(t); } } catch (x) { toast(x.message, true); } }}>Скопировать инструкцию для ИИ</Btn>
      <Btn onClick={async () => { try { const tok = ssGet('rl_tok'); const r = await fetch('/api/localplug/template.zip', { credentials: 'same-origin', headers: tok ? { 'X-RL-Session': tok } : {} }); const u = URL.createObjectURL(await r.blob()); const a = document.createElement('a'); a.href = u; a.download = 'local-plugin-template.zip'; a.click(); setTimeout(() => URL.revokeObjectURL(u), 4000); } catch (x) { toast(x.message, true); } }}>Скачать шаблон .zip</Btn></div>
    {guide ? <textarea className="input mono" rows={8} readOnly value={guide} onFocus={ev => ev.target.select()} /> : null}
    <div><input ref={fileRef} type="file" accept=".zip,application/zip" style={{ display: 'none' }} onChange={ev => upload(ev.target.files[0])} />
      <Btn kind="primary" busy={busy} disabled={busy || data.demo} onClick={() => fileRef.current && fileRef.current.click()}>Выбрать .zip…</Btn></div>
    {rep && rep.errors && rep.errors.length ? <div className="cam-warn"><ul style={{ margin: 0, paddingLeft: 18 }}>{rep.errors.map((e, i) => <li key={i}>{e}</li>)}</ul></div> : null}
  </div>;
}
