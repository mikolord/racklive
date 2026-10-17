/* Settings → «О программе» → updates: newest release on GitHub, one-button update (rackd/updater.py), rollback, and an optional night-time automatic update. */
function UpdateCard() {
  const { data } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [u, setU] = useState(null); const [busy, setBusy] = useState(false); const [back, setBack] = useState(null);     // back: waiting for the server to come up with the new version
  const load = async () => { try { setU(await api('/api/update')); } catch (e) { } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (!u || !u.job || !u.job.running) return; const t = setInterval(load, 1500); return () => clearInterval(t); }, [u && u.job && u.job.running]);
  useEffect(() => {                               // the server restarts itself: wait until it answers again, then reload the page
    if (!back) return;
    let n = 0; const t = setInterval(async () => {
      n++; try { const r = await fetch('/api/state', { cache: 'no-store' }); const j = await r.json(); if (j.version && j.version !== back) { clearInterval(t); location.reload(); } } catch (e) { }
      if (n > 90) { clearInterval(t); setBack(null); toast('Сервер долго не отвечает — проверьте, запустился ли он', true); }
    }, 2000);
    return () => clearInterval(t);
  }, [back]);
  useEffect(() => { if (u && u.job && u.job.done && !back) setBack(u.current); }, [u && u.job && u.job.done]);
  const call = async (path, body, method = 'POST') => { setBusy(true); try { setU(await api(path, { method, body: body || {} })); } catch (e) { toast(e.message, true); } finally { setBusy(false); } };
  if (!u) return null;
  const when = u.checked ? fmt.ago(u.checked, data.now) : 'ещё не проверяли';
  const running = u.job && u.job.running;
  const doUpdate = async () => {
    if (!(await confirm(`Обновить Rack Live ${u.current} → ${u.latest}?\n\nПрограмма скачает новую версию с GitHub, проверит её, заменит свои файлы и перезапустится (около 10–20 секунд страница не будет отвечать). Ваши устройства, пароли и настройки не затрагиваются. Старая версия сохраняется: если новая не запустится, вернётся сама, а вручную можно откатиться кнопкой «Откатить».`, { title: 'Обновление', ok: 'Обновить' }))) return;
    call('/api/update/apply', { tag: u.tag });
  };
  const rb = async () => { if (await confirm('Вернуть предыдущую версию? Программа перезапустится.', { title: 'Откат', ok: 'Откатить', danger: true })) { call('/api/update/rollback'); setBack(u.current); } };
  const MODES = [['notify', 'Только сообщать'], ['auto', 'Обновлять ночью'], ['off', 'Не проверять']];
  return <Card title="Обновления" style={{ marginTop: 10 }}>
    <div className="row" style={{ gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
      {u.newer ? <span className="badge warning">доступна {u.latest}</span> : u.latest ? <span className="badge online"><Icon name="check" size={11} />у вас последняя версия</span> : <span className="badge">версия не определена</span>}
      <span className="dim" style={{ fontSize: 12.5 }}>сейчас {u.current} · проверено {when}</span>
      <div className="grow" />
      <Btn size="sm" icon="refresh" busy={busy && !running} disabled={running} onClick={() => call('/api/update/check')}>Проверить</Btn>
    </div>
    {u.error ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>{u.error}</div> : null}
    {u.newer && u.notes ? <div className="plugin-result" style={{ marginTop: 10, whiteSpace: 'pre-wrap', fontSize: 12.5, lineHeight: 1.5 }}><b>Что нового в {u.latest}</b>{'\n'}{u.notes}</div> : null}
    {u.state && u.state.status === 'rolled_back' ? <div className="err-note"><b>Предыдущее обновление откатилось.</b> {u.state.error}</div> : null}
    {u.state && u.state.status === 'pending' ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>Версия {u.state.to} только что установлена и проверяется: если за минуту после запуска всё в порядке, она закрепится.</div> : null}
    {running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>{u.job.stage}</b><div className="dim3" style={{ fontSize: 12 }}>не закрывайте страницу — она сама обновится</div></div></div> : null}
    {back && !running ? <div className="job"><span className="spin-dot" /><div className="grow"><b>Перезапуск…</b><div className="dim3" style={{ fontSize: 12 }}>как только сервер ответит с новой версией, страница обновится сама</div></div></div> : null}
    {u.job && u.job.error ? <div className="err-note">{u.job.error}</div> : null}
    {!u.canApply ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 8, lineHeight: 1.5 }}>Обновить отсюда нельзя: {u.why}.
      Вручную: <span className="mono">git pull &amp;&amp; docker compose up -d --build</span> (Docker) или <span className="mono">sh install.sh update</span> (роутер).</div> : null}
    <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
      {u.newer && u.canApply ? <Btn kind="primary" icon="download" disabled={running || !!back || busy} onClick={doUpdate}>Обновить до {u.latest}</Btn> : null}
      {u.canRollback ? <Btn icon="refresh" disabled={running || !!back || busy} onClick={rb}>Откатить на предыдущую</Btn> : null}
    </div>
    <div className="card-title" style={{ marginTop: 14 }}>Автоматически</div>
    <Seg value={u.mode} onChange={m => call('/api/update/settings', { mode: m }, 'PUT')} options={MODES.map(([value, label]) => ({ value, label }))} />
    <div className="dim3" style={{ fontSize: 12.5, marginTop: 6, lineHeight: 1.5 }}>{u.mode === 'auto' ? 'Rack Live раз в несколько часов смотрит, нет ли нового выпуска, и ставит его сам ночью (с 3 до 5 часов), если он выходит как отдельная версия. Об этом придёт сообщение в «События» и в Telegram. Версии, которые не запустились, повторно не ставятся.'
      : u.mode === 'notify' ? 'Rack Live сам смотрит, вышла ли новая версия, и сообщает об этом в «События» и в Telegram. Ставите вы — кнопкой выше.' : 'Программа не обращается к GitHub за новыми версиями. Проверить можно кнопкой.'}
      {' '}Ставятся только выпуски с меткой версии (v2.6.1 и т. п.), а не черновой код.</div>
  </Card>;
}
