/* Settings → «Бэкапы»: every backup made from the device cards in one place — config versions of routers / switches (rackd/backups.py)
   and whole-server snapshots of VPS (rackd/snapshots.py). Tap a device → its history (the same BackupsTab as in the card). */
function BackupsCenter() {
  const { data, refresh, openDevice } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [b, setB] = useState(null);
  const [q, setQ] = useState('');
  const [runAll, setRunAll] = useState(null);              // 'n / m' while saving everything
  // a device's history opens in its own card (the «Конфигурация» tab) — the usual window with «back», also in the installed app
  const open = d => { const dev = (data.devices || []).find(x => x.id === d.id); if (dev) openDevice(dev, 'config'); };
  const setEvery = async h => { try { await api('/api/settings', { method: 'PUT', body: { backupEvery: h } }); setB(x => ({ ...x, everyH: h })); refresh();
    toast(h ? 'Автоматические бэкапы: ' + EVERY_TEXT[h] : 'Бэкапы только вручную'); } catch (e) { toast(e.message, true); } };
  const setKeep = async k => {
    if (k && k < b.keepDays || k && !b.keepDays) {
      if (!(await confirm(`Удалить версии старше ${KEEP_TEXT[k]}? Самая новая версия каждого устройства останется. Вернуть удалённые будет нельзя.`, { title: 'Бэкапы', ok: 'Удалить старые', danger: true }))) return;
    }
    try { await api('/api/settings', { method: 'PUT', body: { backupKeepDays: k } }); toast(k ? 'Версии хранятся ' + { 7: 'неделю', 30: 'месяц', 90: '3 месяца' }[k] : 'Старые версии больше не удаляются'); load(); }
    catch (e) { toast(e.message, true); } };
  const load = async () => { try { setB(await api('/api/backups')); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); }, []);
  if (!b) return <Card title="Бэкапы"><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю…</div></Card>;
  const ql = q.trim().toLowerCase();
  const hit = (...xs) => !ql || xs.some(x => (x || '').toLowerCase().includes(ql));
  const devs = b.devices.filter(d => hit(d.name, d.host, d.driverTitle)).sort((x, y) => ((y.last || {}).t || 0) - ((x.last || {}).t || 0) || x.name.localeCompare(y.name));
  const snaps = b.snapshots.filter(m => hit(m.deviceName, m.host, m.hostname, m.os));
  const vers = b.devices.reduce((s, d) => s + d.count, 0);
  const snapBytes = b.snapshots.reduce((s, m) => s + (m.size || 0), 0);
  const saveAll = async () => {
    const list = b.devices.filter(d => d.can && d.online);
    if (!list.length) return toast('Нет устройств на связи, с которых можно снять копию', true);
    let done = 0, changed = 0, fail = 0;
    for (const d of list) {
      setRunAll(`${done + 1} из ${list.length}`);
      try { const r = await api(`/api/backups/${d.id}/run`, { method: 'POST', body: {} }); if (r && r.changed) changed++; } catch (e) { fail++; }
      done++;
    }
    setRunAll(null); load(); refresh();
    toast(`Проверено устройств: ${list.length}` + (changed ? `, новых версий: ${changed}` : ', изменений нет') + (fail ? `, не получилось: ${fail}` : ''), !!fail);
  };
  const delSnap = async m => {
    if (!(await confirm(`Удалить слепок «${m.deviceName}» от ${fmt.time(m.t)} (${snapSize(m.size)})? Восстановить из него будет уже нельзя.`, { title: 'Слепок сервера', ok: 'Удалить', danger: true }))) return;
    try { await api(`/api/snapshots/${m.id}`, { method: 'DELETE' }); toast('Слепок удалён'); load(); } catch (e) { toast(e.message, true); }
  };
  return <>
    <Card title="Бэкапы" right={<Btn size="sm" icon="download" busy={!!runAll} disabled={!!runAll} onClick={saveAll}>{runAll ? 'Сохраняю ' + runAll : 'Сохранить все сейчас'}</Btn>}>
      <div className="col" style={{ gap: 10 }}>
        <div className="vault-stats">
          <div><b>{b.devices.filter(d => d.count).length}</b><span>устройств с копиями</span></div>
          <div><b>{vers}</b><span>версий конфигураций · {snapSize(b.configBytes)}</span></div>
          <div><b>{b.snapshots.length}</b><span>слепков серверов · {snapSize(snapBytes)}</span></div>
          <div><b>{snapSize(b.storeFree)}</b><span>свободно на Rack Live</span></div>
        </div>
        <Field label="Автоматически сохранять конфигурации">
          <Seg value={b.everyH} onChange={setEvery} options={[{ value: 6, label: '6 ч' }, { value: 24, label: 'Сутки' }, { value: 168, label: 'Неделя' }, { value: 0, label: 'Вручную' }]} /></Field>
        <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.5 }}>{b.everyH ? `Rack Live ${EVERY_TEXT[b.everyH]} проверяет роутеры и коммутаторы и сохраняет новую версию, только если настройки изменились.`
          : 'Сам Rack Live ничего не сохраняет — только по кнопке «Сохранить все сейчас» или «Сохранить сейчас» в карточке устройства.'}</div>
        <Field label="Удалять старые версии">
          <Seg value={b.keepDays} onChange={setKeep} options={[{ value: 7, label: 'Неделя' }, { value: 30, label: 'Месяц' }, { value: 90, label: '3 месяца' }, { value: 0, label: 'Никогда' }]} /></Field>
        <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.5 }}>{b.keepDays ? `Версии старше ${KEEP_TEXT[b.keepDays]} удаляются сами. ` : ''}Самая новая версия каждого устройства остаётся всегда, сколько бы ей ни было.
          {' '}Больше {b.keep} версий на устройство не хранится. Слепки серверов не удаляются сами — только вручную.</div>
        <div className="vault-search"><Icon name="search" size={16} color="var(--text3)" /><input className="input" placeholder="Поиск по названию или адресу" value={q} onChange={e => setQ(e.target.value)} /></div>
      </div>
    </Card>
    <Card title={'Конфигурации устройств' + (devs.length ? ' · ' + devs.length : '')} pad={false}>
      {!devs.length ? <div className="dim3" style={{ padding: 16, fontSize: 13 }}>{ql ? 'Ничего не найдено' : 'Нет устройств, у которых Rack Live умеет сохранять конфигурацию (роутеры Keenetic, OpenWrt, коммутаторы TP-Link).'}</div>
        : <div className="vault-list">{devs.map(d => <button type="button" key={d.id} className="vault-row" onClick={() => open(d)}>
          <KindIcon kind={d.kind} name={d.name} size={34} round={9} />
          <div className="grow vault-main"><div className="vault-name">{nameNoFlag(d.name)}</div>
            <div className="vault-sub">{d.count ? <>{d.count} {plural(d.count, 'версия', 'версии', 'версий')} · последняя {fmt.ago(d.last.t, data.now)}</> : <span>копий ещё нет{d.online ? '' : ' · не на связи'}</span>}</div></div>
          <span className="vault-tag">{d.driverTitle}</span>
          <Icon name="chevron" size={15} color="var(--text3)" stroke={2.4} /></button>)}</div>}
    </Card>
    <Card title={'Слепки серверов' + (snaps.length ? ' · ' + snaps.length : '')} pad={false}>
      {!snaps.length ? <div className="dim3" style={{ padding: 16, fontSize: 13, lineHeight: 1.5 }}>{ql ? 'Ничего не найдено' : 'Слепков пока нет. Откройте карточку VPS → «Плагины» → «Слепок сервера» → «Снять слепок».'}</div>
        : <div className="vault-list">{snaps.map(m => <div key={m.id} className="vault-row">
          <KindIcon kind="server" name={m.deviceName} size={34} round={9} />
          <div className="grow vault-main"><div className="vault-name">{nameNoFlag(m.deviceName || m.hostname || 'Сервер')}</div>
            <div className="vault-sub">{fmt.time(m.t)} · {snapSize(m.size)} · {m.os}{m.note ? ' · ' + m.note : ''}</div></div>
          {inHomeApp() ? null : <a className="btn sm icon" href={`/api/snapshots/${m.id}/file`} download title="Скачать слепок (весь сервер, вместе с паролями — храните надёжно)"><Icon name="download" size={15} /></a>}
          <Btn size="sm" kind="danger" icon="trash" title="Удалить слепок" onClick={() => delSnap(m)} /></div>)}</div>}
    </Card>
  </>;
}
const EVERY_TEXT = { 6: 'каждые 6 часов', 24: 'раз в сутки', 168: 'раз в неделю' };
const KEEP_TEXT = { 7: 'недели', 30: 'месяца', 90: '3 месяцев' };

function plural(n, one, few, many) { const a = Math.abs(n) % 100, b = a % 10; return a > 10 && a < 20 ? many : b > 1 && b < 5 ? few : b === 1 ? one : many; }

/* Settings → «Пароли»: like the Passwords app on iOS — locked until the administrator password is typed again,
   then every login / password / key from the device cards: search, show, copy, change, export (JSON / CSV) and import. */
async function vaultFile(path, body, name) {
  const tok = ssGet('rl_tok');
  const r = await fetch(path, { method: 'POST', credentials: 'same-origin', headers: Object.assign({ 'Content-Type': 'application/json' }, tok ? { 'X-RL-Session': tok } : {}), body: JSON.stringify(body) });
  if (!r.ok) { let m = 'не получилось'; try { m = (await r.json()).error || m; } catch (e) { } const err = new Error(m); err.status = r.status; throw err; }
  await saveBlob(await r.blob(), name);
}

/* Saving a file. In the app installed on the iPhone home screen a plain download opens the file over the whole app with no way back —
   there the system share sheet is used instead («Сохранить в Файлы», AirDrop, Telegram…). In a browser it is a normal download. */
const inHomeApp = () => { try { return matchMedia('(display-mode: standalone)').matches || navigator.standalone === true; } catch (e) { return false; } };
async function saveBlob(blob, name) {
  if (inHomeApp() && navigator.share && window.File) {
    const file = new File([blob], name, { type: blob.type || 'application/octet-stream' });
    if (!navigator.canShare || navigator.canShare({ files: [file] })) {
      try { await navigator.share({ files: [file], title: name }); return; }
      catch (e) { if (e && e.name === 'AbortError') return; }      // closed by the person — nothing else to do
    }
  }
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}
/* a GET file of Rack Live (with the session) → saveBlob; the name comes from the server's Content-Disposition */
async function downloadFile(url, fallback) {
  const tok = ssGet('rl_tok');
  const r = await fetch(url, { credentials: 'same-origin', headers: tok ? { 'X-RL-Session': tok } : {} });
  if (!r.ok) { let m = 'не получилось скачать'; try { m = (await r.json()).error || m; } catch (e) { } throw new Error(m); }
  const cd = r.headers.get('Content-Disposition') || '';
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd) || /filename="([^"]+)"/i.exec(cd);
  let name = fallback || 'file';
  try { if (m) name = decodeURIComponent(m[1]); } catch (e) { }
  await saveBlob(await r.blob(), name);
}

function PasswordsCard() {
  const toast = useToast();
  const [ticket, setTicket] = useState(null);
  const [items, setItems] = useState([]);
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(null);                   // id of the entry shown
  const [exp, setExp] = useState(false);
  const [imp, setImp] = useState(null);                     // the result of the last import
  const fileRef = useRef(null);
  const tRef = useRef(null); tRef.current = ticket;
  const [pkOn, setPkOn] = useState(false);                  // «Открывать «Пароли» по Face ID» is on and this address has a key
  useEffect(() => { if (!pkSupported()) return; api('/api/passkey/status', { method: 'POST', body: {} })
    .then(s => setPkOn(!!(s.vault && s.keys.some(k => k.rpId === location.hostname)))).catch(() => { }); }, []);
  const unlockFace = async () => {
    setBusy(true);
    try { const passkey = await passkeyAssert('vault'); const r = await api('/api/vault/unlock', { method: 'POST', body: { passkey } }); setTicket(r.ticket); setItems(r.items); }
    catch (e) { toast(pkError(e), true); } finally { setBusy(false); }
  };
  useEffect(() => () => { if (tRef.current) api('/api/vault/lock', { method: 'POST', body: { ticket: tRef.current } }).catch(() => { }); }, []);   // leaving the section locks it
  const lock = () => { if (ticket) api('/api/vault/lock', { method: 'POST', body: { ticket } }).catch(() => { }); setTicket(null); setItems([]); setOpen(null); setExp(false); setImp(null); };
  const closed = e => { if (e && e.status === 423) { setTicket(null); setItems([]); setOpen(null); setExp(false); toast('Раздел закрылся сам — введите пароль ещё раз', true); return true; } return false; };
  const unlock = async e => {
    if (e) e.preventDefault();
    setBusy(true);
    try { const r = await api('/api/vault/unlock', { method: 'POST', body: { password: pw } }); setTicket(r.ticket); setItems(r.items); setPw(''); }
    catch (e) { toast(e.message, true); } finally { setBusy(false); }
  };
  const call = async (path, body, method = 'POST') => { try { return await api(path, { method, body: { ...body, ticket } }); } catch (e) { if (!closed(e)) toast(e.message, true); return null; } };
  const doExport = async fmt_ => {
    try { await vaultFile('/api/vault/export', { ticket, format: fmt_ }, 'racklive-passwords.' + fmt_); toast('Файл с паролями скачан'); setExp(false); }
    catch (e) { if (!closed(e)) toast(e.message, true); }
  };
  const importFile = async e => {
    const f = e.target.files[0]; e.target.value = ''; if (!f) return;
    if (f.size > 5e6) return toast('Файл больше 5 МБ', true);
    const r = await call('/api/vault/import', { text: await f.text() });
    if (r) { setItems(r.items); setImp(r); toast(r.updated.length ? `Обновлено устройств: ${r.updated.length}` : 'Ничего не изменилось', !r.updated.length && r.unmatched.length > 0); }
  };

  if (!ticket) return <Card title="Пароли"><form className="vault-lock" onSubmit={unlock}>
    <div className="vault-lock-ic"><Icon name="lock" size={30} color="#fff" stroke={2} /></div>
    <div className="vault-lock-t">Пароли защищены</div>
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5, maxWidth: 380, textAlign: 'center' }}>Здесь логины, пароли и ключи всех устройств, которые вы вводили в карточках. Чтобы открыть, {pkOn ? 'подтвердите ' + pkLabel() + ' или введите' : 'введите'} пароль администратора Rack Live.</div>
    {pkOn ? <><button type="button" className={'btn primary faceid-btn' + (busy ? ' busy' : '')} disabled={busy} onClick={unlockFace} style={{ maxWidth: 320, width: '100%' }}>
      <FaceIdGlyph size={22} />Открыть с {pkLabel()}</button><div className="dim3" style={{ fontSize: 12 }}>или паролем</div></> : null}
    <input className="input" type="password" autoComplete="current-password" placeholder="Пароль администратора" value={pw} onChange={e => setPw(e.target.value)} style={{ maxWidth: 320 }} />
    <Btn kind="primary" type="submit" icon="lock" busy={busy} disabled={!pw || busy}>Открыть</Btn>
    <div className="dim3" style={{ fontSize: 12 }}>Раздел закроется сам через 5 минут без действий или когда вы уйдёте из него.</div>
  </form></Card>;

  const ql = q.trim().toLowerCase();
  const list = items.filter(e => !ql || [e.name, e.host, e.url, e.driverTitle, ...e.fields.filter(f => !f.secret).map(f => f.value), ...e.panels.map(p => p.user)].some(x => (x || '').toLowerCase().includes(ql)));
  const cur = open && items.find(e => e.id === open);
  return <>
    <Card title={'Пароли · ' + items.length} right={<div className="row" style={{ gap: 6 }}>
      <Btn size="sm" icon="download" onClick={() => setExp(true)}>Экспорт</Btn>
      <Btn size="sm" icon="upload" onClick={() => fileRef.current.click()}>Импорт</Btn>
      <Btn size="sm" icon="lock" title="Закрыть раздел" onClick={lock} /></div>}>
      <div className="vault-search"><Icon name="search" size={16} color="var(--text3)" /><input className="input" placeholder="Поиск" value={q} onChange={e => setQ(e.target.value)} /></div>
      <input ref={fileRef} type="file" accept=".json,.csv,application/json,text/csv" style={{ display: 'none' }} onChange={importFile} />
      {imp ? <div className="vault-imp">
        <b>Импорт:</b> обновлено устройств {imp.updated.length}, полей {imp.fields}.
        {imp.unmatched.length ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 4 }}>Не нашлось среди устройств ({imp.unmatched.length}): {imp.unmatched.slice(0, 12).join(', ')}{imp.unmatched.length > 12 ? '…' : ''}. Новые устройства импорт не создаёт — сначала добавьте их.</div> : null}
        <button type="button" className="vault-x" onClick={() => setImp(null)} title="Скрыть"><Icon name="x" size={14} /></button></div> : null}
    </Card>
    <Card pad={false}>
      {!list.length ? <div className="dim3" style={{ padding: 16, fontSize: 13 }}>{ql ? 'Ничего не найдено' : 'Паролей пока нет — они появятся, когда вы заполните логин и пароль в карточке устройства.'}</div>
        : <div className="vault-list">{list.map(e => { const u = e.fields.find(f => !f.secret); const n = e.fields.filter(f => f.secret).length + e.panels.length;
          return <button type="button" key={e.id} className="vault-row" onClick={() => setOpen(e.id)}>
            <KindIcon kind={e.kind} name={e.name} size={34} round={9} />
            <div className="grow vault-main"><div className="vault-name">{nameNoFlag(e.name)}</div>
              <div className="vault-sub">{u ? u.value : e.host || e.driverTitle}{e.host && u ? ' · ' + e.host : ''}</div></div>
            {n > 1 ? <span className="vault-tag">{n} {plural(n, 'пароль', 'пароля', 'паролей')}</span> : null}
            <Icon name="chevron" size={15} color="var(--text3)" stroke={2.4} /></button>; })}</div>}
    </Card>
    {cur ? <VaultItem e={cur} ticket={ticket} onClose={() => setOpen(null)} onSaved={it => setItems(xs => xs.map(x => x.id === it.id ? it : x))} closed={closed} /> : null}
    {exp ? <Modal title="Экспорт паролей" icon={<Icon name="download" size={20} />} onClose={() => setExp(false)}>
      <div className="col" style={{ gap: 12 }}>
        <div className="vault-warn"><Icon name="shield" size={18} /><span>В файле будут все пароли и ключи открытым текстом. Храните его надёжно и удалите, когда он станет не нужен.</span></div>
        <button type="button" className="vault-opt" onClick={() => doExport('json')}><Icon name="file" size={22} /><div className="grow"><b>JSON для Rack Live</b>
          <div className="dim3">Все поля, включая SSH-ключи и токены. Можно импортировать обратно в Rack Live — на этой или другой машине.</div></div></button>
        <button type="button" className="vault-opt" onClick={() => doExport('csv')}><Icon name="list" size={22} /><div className="grow"><b>CSV для других менеджеров паролей</b>
          <div className="dim3">Формат «Title, URL, Username, Password, Notes»: понимают «Пароли» на iPhone и Mac, Chrome, 1Password, Bitwarden. Тоже импортируется обратно в Rack Live.</div></div></button>
      </div></Modal> : null}
  </>;
}

function VaultSecret({ f, shown, onShow }) {
  const toast = useToast();
  const copy = () => { if (copyText(f.value)) toast('Скопировано: ' + f.label.toLowerCase()); else toast('Не удалось скопировать', true); };
  return <div className="vault-field">
    <div className="vault-k">{f.label}</div>
    <div className="row" style={{ gap: 6, alignItems: 'flex-start' }}>
      {f.multiline && shown ? <pre className="vault-v mono grow vault-pre">{f.value}</pre>
        : <div className={'vault-v grow' + (f.secret ? ' mono' : '')}>{f.secret && !shown ? '••••••••••••' : f.multiline ? f.value.split('\n')[0] + ' …' : f.value}</div>}
      {f.secret ? <Btn size="sm" icon="eye" title={shown ? 'Скрыть' : 'Показать'} onClick={onShow} /> : null}
      <Btn size="sm" icon="copy" title="Скопировать" onClick={copy} /></div></div>;
}

function VaultItem({ e, ticket, onClose, onSaved, closed }) {
  const toast = useToast(); const confirm = useConfirm();
  const [shown, setShown] = useState({});
  const [edit, setEdit] = useState(null);                   // {key: value} while editing
  const [busy, setBusy] = useState(false);
  const flip = k => setShown(s => ({ ...s, [k]: !s[k] }));
  const startEdit = () => {
    const v = {}; e.fields.filter(f => f.editable).forEach(f => { v[f.key] = f.value; });
    if (!('username' in v) && !e.fields.some(f => !f.secret)) v.username = '';
    if (!e.fields.some(f => f.secret && f.editable)) v.password = '';
    setEdit(v);
  };
  const save = async () => {
    const removed = Object.keys(edit).filter(k => !edit[k] && e.fields.some(f => f.key === k));
    if (removed.length && !(await confirm(`Удалить из карточки: ${removed.map(k => (e.fields.find(f => f.key === k) || {}).label || k).join(', ')}? Rack Live перестанет входить на устройство с этими данными.`, { title: 'Пароли', ok: 'Удалить', danger: true }))) return;
    setBusy(true);
    try { const r = await api(`/api/vault/item/${e.id}`, { method: 'PUT', body: { ticket, fields: edit } }); onSaved(r.item); setEdit(null); setShown({}); toast(r.changed.length ? 'Сохранено' : 'Ничего не изменилось'); }
    catch (er) { if (!closed(er)) toast(er.message, true); } finally { setBusy(false); }
  };
  const labelOf = k => (e.fields.find(f => f.key === k) || {}).label || { username: 'Логин', password: 'Пароль' }[k] || k;
  return <Modal title={nameNoFlag(e.name)} icon={<KindIcon kind={e.kind} name={e.name} size={28} round={7} />} onClose={onClose}
    footer={edit ? <><Btn onClick={() => setEdit(null)}>Отмена</Btn><Btn kind="primary" icon="check" busy={busy} disabled={busy} onClick={save}>Сохранить</Btn></>
      : <Btn icon="edit" onClick={startEdit}>Изменить</Btn>}>
    <div className="col" style={{ gap: 4 }}>
      <div className="dim3" style={{ fontSize: 12.5, marginBottom: 6 }}>{e.driverTitle}{e.host ? ' · ' + e.host : ''}{e.sshPort ? ' · порт ' + e.sshPort : ''}
        {e.url ? <> · <a href={e.url} target="_blank" rel="noreferrer">открыть</a></> : null}</div>
      {edit ? Object.keys(edit).map(k => <Field key={k} label={labelOf(k)}>{k === 'privateKey'
        ? <textarea className="input mono" rows={6} value={edit[k]} onChange={ev => setEdit(x => ({ ...x, [k]: ev.target.value }))} spellCheck={false} />
        : <input className="input" type="text" autoComplete="off" spellCheck={false} value={edit[k]} onChange={ev => setEdit(x => ({ ...x, [k]: ev.target.value }))} />}</Field>)
        : <div className="vault-group">{e.fields.map(f => <VaultSecret key={f.key} f={f} shown={!!shown[f.key]} onShow={() => flip(f.key)} />)}</div>}
      {edit ? <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.45 }}>Здесь меняется только то, с чем Rack Live входит на устройство. Пароль на самом устройстве это не меняет. Пустое поле — удалить значение.</div> : null}
      {!edit && e.panels.length ? <>
        <div className="card-title" style={{ marginTop: 12 }}>Панели, установленные Rack Live</div>
        {e.panels.map(p => <div className="vault-group" key={p.id}>
          {p.url ? <div className="vault-field"><div className="vault-k">Панель {p.id}</div><a className="vault-v ellipsis" href={p.url} target="_blank" rel="noreferrer">{p.url}</a></div> : null}
          {p.user ? <VaultSecret f={{ key: p.id + 'u', label: 'Логин', value: p.user }} /> : null}
          {p.password ? <VaultSecret f={{ key: p.id + 'p', label: 'Пароль', value: p.password, secret: true }} shown={!!shown[p.id + 'p']} onShow={() => flip(p.id + 'p')} /> : null}
        </div>)}
        <div className="dim3" style={{ fontSize: 12 }}>Это пароли, которые Rack Live задал при установке панели. Если вы меняли их в самой панели, здесь они устарели.</div></> : null}
    </div></Modal>;
}
