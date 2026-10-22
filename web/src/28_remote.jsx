/* «Удалённый доступ (WireGuard)» (OpenWrt, rackd/remote.py): the router keeps a tunnel to the owner's WireGuard server, so Rack Live manages it
   wherever it is taken. Only management goes through the tunnel: the internet of that place stays with its own provider. */
function RemotePlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm();
  const t = p.tunnel || {}; const info = p.info || {};
  const hubs = (p.hubs || []).filter(h => !h.error);
  const broken = (p.hubs || []).filter(h => h.error);
  const [hub, setHub] = useState(info.hub || (hubs[0] || {}).id || '');
  const [extra, setExtra] = useState((info.extra || []).join(', '));
  const [use, setUse] = useState(true);
  const [busy, setBusy] = useState(''); const [stage, setStage] = useState(''); const [result, setResult] = useState(null);
  const [again, setAgain] = useState(false);
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: 'remote', ...body } });
  const pollJob = async id => {
    for (let i = 0; i < 160; i++) {
      await new Promise(r => setTimeout(r, 2500));
      let j; try { j = await call({ op: 'job', job: id }); } catch (e) { continue; }
      if (j.stage) setStage(j.stage);
      if (j.done) return j.error ? { ok: false, error: j.error } : { ...(j.result || {}), ok: (j.result || {}).ok !== false };
    }
    return { ok: false, error: 'настройка заняла слишком долго — проверьте роутер' };
  };
  const h = hubs.find(x => x.id === hub);
  const viaTunnel = p.info && p.host === info.ip;

  const connect = async () => {
    if (!h) return;
    if (!(await confirm(`Rack Live поставит на роутер WireGuard и подключит его к «${h.deviceName} · ${h.name}»: на нём появится новое подключение «${device.name}», `
      + `остальные подключения не трогаются. На роутере добавится только туннель — сеть, Wi-Fi и интернет клиентов не меняются. Продолжить?`, { title: 'Подключить к центру', ok: 'Подключить' }))) return;
    setBusy('install'); setResult(null); setStage('Начинаю…');
    try {
      let r = await call({ op: 'install', hub, use, extra: extra.split(/[\s,;]+/).filter(Boolean) });
      if (r.job) r = await pollJob(r.job);
      setResult(r); toast(r.message || r.error || '', !r.ok); setAgain(false); reload();
    } catch (e) { setResult({ error: e.message }); toast(e.message, true); }
    finally { setBusy(''); setStage(''); }
  };
  const disconnect = async () => {
    if (!(await confirm('Отключить удалённый доступ? Туннель удалится с роутера, а подключение — из центра. Если роутер уже стоит у клиента, '
      + 'Rack Live потеряет с ним связь, пока вы не подключите его снова на месте.', { title: 'Отключить удалённый доступ', ok: 'Отключить', danger: true }))) return;
    setBusy('remove'); setResult(null); setStage('Отключаю…');
    try { let r = await call({ op: 'remove' }); if (r.job) r = await pollJob(r.job); setResult(r); toast(r.message || r.error || '', !r.ok); reload(); }
    catch (e) { toast(e.message, true); }
    finally { setBusy(''); setStage(''); }
  };
  const address = async to => {
    setBusy('addr');
    try { const r = await call({ op: 'address', to }); toast(r.message); reload(); } catch (e) { toast(e.message, true); }
    finally { setBusy(''); }
  };

  const form = <>
    {hubs.length ? <Field label="Центр — WireGuard-сервер, к которому роутер будет подключаться">
      <select className="input" value={hub} onChange={e => setHub(e.target.value)}>
        {hubs.map(x => <option key={x.id} value={x.id}>{x.deviceName} · {x.name} ({x.net}, занято адресов: {x.used})</option>)}</select></Field>
      : <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Центра пока нет. Нужен WireGuard-сервер: добавьте в Rack Live роутер Keenetic / Netcraze, на котором включён
        WireGuard-сервер («Другие подключения» → WireGuard, режим сервера), и откройте эту вкладку снова.</div>}
    {broken.map(x => <div key={x.id} className="dim3" style={{ fontSize: 12.5 }}>«{x.deviceName}»: {x.error}</div>)}
    {h ? <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Роутер будет звонить на {h.reach}:{h.port}{h.wan && h.domain ? ` (сейчас это ${h.wan})` : ''}. Этот порт (UDP)
      должен быть доступен из интернета — у WireGuard-сервера роутера так и есть.</div> : null}
    <Field label="Кто ещё может заходить на роутер через туннель (необязательно)" hint="Rack Live добавится сам. Сюда — например, ваш компьютер (192.168.1.10), чтобы открывать веб-интерфейс роутера напрямую. Только частные адреса.">
      <input className="input mono" value={extra} placeholder="192.168.1.10" onChange={e => setExtra(e.target.value)} /></Field>
    <label className="row" style={{ gap: 10, alignItems: 'center', fontSize: 13.5 }}><Switch on={use} onChange={setUse} />
      <span>Сразу работать с роутером через туннель (его адрес в Rack Live заменится адресом в туннеле)</span></label>
    <div className="row wrap" style={{ gap: 8 }}>
      <Btn kind="primary" icon="globe2" busy={busy === 'install'} disabled={!h || !!busy} onClick={connect}>{p.installed ? 'Подключить заново' : 'Подключить'}</Btn>
      {p.installed ? <Btn onClick={() => setAgain(false)} disabled={!!busy}>Отмена</Btn> : null}
    </div>
  </>;

  return <>
    <RemoteGuide installed={p.installed} />
    <Checks checks={p.checks || []} />
    {p.installed ? <div className="pt-live">
      <div className="row" style={{ gap: 12, alignItems: 'center' }}>
        <span className={'dot ' + (t.up ? 'online' : 'offline')} />
        <div className="grow" style={{ minWidth: 0 }}><b>{t.up ? 'Туннель на связи' : 'Нет связи с центром'}</b>
          <div className="dim3" style={{ fontSize: 12.5 }}>адрес в туннеле <span className="mono">{t.ip}</span>{info.hubName ? ` · центр «${info.hubName}»` : ''}
            {t.ago != null ? ` · последний обмен ${t.ago < 60 ? t.ago + ' с' : Math.round(t.ago / 60) + ' мин'} назад` : ''}
            {t.rx != null ? ` · получено ${fmt.bytes(t.rx)}, отправлено ${fmt.bytes(t.tx)}` : ''}</div></div>
      </div>
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 8 }}>Rack Live работает с роутером по адресу <span className="mono">{p.host}</span>
        {viaTunnel ? ' — через туннель.' : ' — напрямую, не через туннель.'}</div>
      <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
        {info.ip && !viaTunnel ? <Btn icon="globe2" busy={busy === 'addr'} disabled={!!busy} onClick={() => address('tunnel')}>Работать через туннель</Btn> : null}
        {viaTunnel && p.hostLocal ? <Btn busy={busy === 'addr'} disabled={!!busy} onClick={() => address('local')}>Вернуть местный адрес {p.hostLocal}</Btn> : null}
        {!again ? <Btn disabled={!!busy} onClick={() => setAgain(true)}>Подключить заново</Btn> : null}
        <Btn kind="danger" icon="trash" busy={busy === 'remove'} disabled={!!busy} onClick={disconnect}>Отключить</Btn>
      </div>
    </div> : null}
    {!p.installed || again ? <div className="stack" style={{ gap: 12 }}>{form}</div> : null}
    {stage ? <div className="dim row" style={{ gap: 8, fontSize: 12.5 }}><span className="spin-dot" />{stage}</div> : null}
    {result ? <PluginResult r={{ ...result, up: result.ok, kept: true }} /> : null}
  </>;
}

function RemoteGuide({ installed }) {
  return <details className="guide" open={!installed}><summary>Как это работает и что идёт через туннель</summary>
    <ol className="steps" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
      <li><b>Подключите роутер, пока он у вас.</b> Выберите центр — ваш WireGuard-сервер — и нажмите «Подключить». Rack Live поставит на роутер WireGuard (~1 МБ),
        создаст ключи, добавит роутеру подключение в центре и проверит связь.</li>
      <li><b>Отвезите роутер на место.</b> Ему нужен только интернет в WAN-порту: он сам «позвонит» в центр и будет держать связь. Белый адрес и проброс портов у клиента не нужны.</li>
      <li><b>Управляйте как обычно.</b> Rack Live работает с роутером по адресу в туннеле: плагины, портал и шаблоны, порты, бэкапы, терминал — всё как рядом.</li>
    </ol>
    <div style={{ fontSize: 13.5, lineHeight: 1.55 }}><b>Через туннель идёт только управление:</b>
      <ul className="steps" style={{ margin: '6px 0 0' }}>
        <li>в туннель роутер отправляет только адреса центра и Rack Live — интернет клиента идёт через его провайдера, не через вас;</li>
        <li>клиенты роутера (основная и гостевая сеть, Wi-Fi) в туннель не попадают вообще — их туда не пускает межсетевой экран роутера;</li>
        <li>из туннеля на роутер открыты только SSH, веб-интерфейс и ping; сеть клиента за роутером из туннеля не видна;</li>
        <li>в центре роутеру разрешён ровно один адрес, поэтому вашим интернетом он пользоваться не может.</li>
      </ul></div>
    <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>Если у центра сменится внешний адрес, роутер сам найдёт новый по домену (проверка раз в 2 минуты, когда нет связи).</div>
  </details>;
}
