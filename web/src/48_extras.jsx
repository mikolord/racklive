/* Internet speed on a schedule · config backups with diff · new devices in the network */
const INET_COLORS = ['#0a84ff', '#30d158', '#ff9f0a', '#bf5af2', '#ff375f', '#64d2ff'];

function InetChart({ items, sources, field = 'down', tariff }) {
  const [hover, setHover] = useState(null);
  const pts = items.filter(x => x[field] != null);
  if (pts.length < 2) return <div className="dim3" style={{ fontSize: 13, padding: '14px 0', textAlign: 'center' }}>График появится после нескольких замеров</div>;
  const W = 640, H = 170, t0 = Math.min(...pts.map(p => p.t)), t1 = Math.max(...pts.map(p => p.t));
  const max = Math.max(tariff || 0, ...pts.map(p => p[field])) * 1.08 || 1;
  const X = t => 4 + (t - t0) / Math.max(1, t1 - t0) * (W - 8), Y = v => H - 16 - v / max * (H - 24);
  const hp = hover;
  const onMove = e => { const r = e.currentTarget.getBoundingClientRect(); const t = t0 + (e.clientX - r.left) / r.width * (t1 - t0);
    let best = pts[0]; pts.forEach(p => { if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p; }); setHover(best); };
  return <div>
    <svg className="chart" style={{ height: 170 }} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      {tariff ? <><line x1={0} x2={W} y1={Y(tariff)} y2={Y(tariff)} stroke="var(--text3)" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" /></> : null}
      {sources.map((s, i) => { const sp = pts.filter(p => p.source === s.id).sort((a, b) => a.t - b.t); if (sp.length < 2) return null;
        return <path key={s.id} d={sp.map((p, k) => `${k ? 'L' : 'M'}${X(p.t).toFixed(1)},${Y(p[field]).toFixed(1)}`).join(' ')} fill="none"
          stroke={INET_COLORS[i % INET_COLORS.length]} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />; })}
      {hp ? <line x1={X(hp.t)} x2={X(hp.t)} y1={0} y2={H - 16} stroke="var(--text3)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" /> : null}
    </svg>
    <div className="row wrap" style={{ gap: '4px 14px', fontSize: 12.5, marginTop: 4 }}>
      {sources.map((s, i) => <span key={s.id} className="row" style={{ gap: 6 }}><i style={{ width: 10, height: 3, borderRadius: 2, background: INET_COLORS[i % INET_COLORS.length] }} />{s.label}</span>)}
      {tariff ? <span className="dim3">- - тариф {tariff} Мбит/с</span> : null}
      <span className="grow" />
      {hp ? <span className="dim">{fmt.time(hp.t)} · {hp.label}: <b>{hp[field]}</b> Мбит/с</span> : null}
    </div>
  </div>;
}

function InternetCard() {
  const { data } = useApp();
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('inet') === '1');
  const n = data.inet; if (!n) return null;
  const main = n.items.filter(x => x.source === 'racklive');
  const last = main[main.length - 1];
  const tariff = +n.cfg.tariff || 0;
  const low = last && tariff && last.down != null && last.down < tariff * .5;
  return <>
    <Card title="Интернет" right={<Btn size="sm" onClick={() => setOpen(true)}>Подробнее</Btn>}>
      <div className="row" style={{ gap: 14, cursor: 'pointer', alignItems: 'flex-end' }} onClick={() => setOpen(true)}>
        {last && last.down != null ? <>
          <div><div className="inet-big" style={{ color: low ? 'var(--orange)' : undefined }}>{Math.round(last.down)}<small> ↓</small></div><div className="dim3" style={{ fontSize: 11.5 }}>Мбит/с загрузка</div></div>
          <div><div className="inet-big">{Math.round(last.up)}<small> ↑</small></div><div className="dim3" style={{ fontSize: 11.5 }}>отдача</div></div>
          <div><div className="inet-big">{last.ping != null ? last.ping : '—'}</div><div className="dim3" style={{ fontSize: 11.5 }}>пинг, мс</div></div>
          <div className="grow" />
          <div className="dim3" style={{ fontSize: 11.5, textAlign: 'right' }}>{fmt.ago(last.t, data.now)}{tariff ? <div>тариф {tariff}</div> : null}</div>
        </> : <div className="dim" style={{ fontSize: 13 }}>{n.running ? 'Идёт первый замер…' : last && last.error ? 'Замер не удался: ' + last.error : 'Замеров ещё не было — нажмите «Подробнее» → «Замерить сейчас»'}</div>}
      </div>
      {main.length > 2 ? <div style={{ marginTop: 8 }}><Sparkline points={main} field="down" color={low ? 'var(--orange)' : 'var(--accent)'} /></div> : null}
    </Card>
    {open ? <Modal title="Скорость интернета" wide onClose={() => setOpen(false)} icon={<Icon name="globe" size={20} color="var(--accent)" />}><InternetBody n={n} /></Modal> : null}
  </>;
}

function InternetBody({ n }) {
  const { data, refresh } = useApp(); const toast = useToast();
  const [c, setC] = useState(() => JSON.parse(JSON.stringify(n.cfg)));
  const [field, setField] = useState('down');
  const [days, setDays] = useState(7);
  const set = (k, v) => setC(x => ({ ...x, [k]: v }));
  const save = async () => { try { await api('/api/inet', { method: 'PUT', body: c }); toast('Сохранено'); refresh(); } catch (e) { toast(e.message, true); } };
  const run = async () => { try { await save(); await api('/api/inet/run', { method: 'POST', body: {} }); toast('Замер начат — займёт около минуты'); setTimeout(refresh, 2000); } catch (e) { toast(e.message, true); } };
  useEffect(() => { if (!n.running) return; const t = setInterval(refresh, 5000); return () => clearInterval(t); }, [n.running]);
  const cut = data.now - days * 86400;
  const items = n.items.filter(x => x.t >= cut);
  const sources = [...new Map(items.map(x => [x.source, { id: x.source, label: x.label }])).values()];
  const lastBy = sources.map(s => [...n.items].reverse().find(x => x.source === s.id));
  const routers = data.devices.filter(d => { const drv = data.drivers.find(x => x.id === d.driver); return drv && drv.inetTest && d.kind === 'router' && (d.state || {}).vpn; });
  const servers = data.devices.filter(d => d.driver === 'ssh' || d.driver === 'demo_server');
  const tunnels = d => [{ id: 'isp', name: 'Провайдер (напрямую)' }, ...((d.state || {}).vpn || []).filter(t => t.role === 'client' && t.kind === 'wireguard')];
  const chan = (did, id) => (c.channels[did] || []).includes(id);
  const toggleChan = (did, id) => set('channels', { ...c.channels, [did]: chan(did, id) ? c.channels[did].filter(x => x !== id) : [...(c.channels[did] || []), id] });
  return <>
    <Hint id="inet">Rack Live сам замеряет скорость интернета по расписанию и строит график. Видно, проседает ли провайдер вечером, — с этими цифрами удобно разговаривать с поддержкой.
      Через роутер Keenetic с Entware можно мерить отдельно каждый VPN-туннель.</Hint>
    <div className="row wrap" style={{ gap: 8 }}>
      <Seg value={field} onChange={setField} options={[{ value: 'down', label: 'Загрузка' }, { value: 'up', label: 'Отдача' }, { value: 'ping', label: 'Пинг' }]} />
      <Seg value={days} onChange={setDays} options={[{ value: 1, label: 'Сутки' }, { value: 7, label: 'Неделя' }, { value: 30, label: 'Месяц' }]} />
      <div className="grow" />
      <Btn kind="primary" icon="refresh" busy={n.running} onClick={run}>{n.running ? 'Идёт замер…' : 'Замерить сейчас'}</Btn>
    </div>
    <InetChart items={items} sources={sources} field={field} tariff={field === 'down' ? +c.tariff || 0 : 0} />
    {lastBy.length ? <div className="list">{lastBy.map((x, i) => x ? <div className="li" key={x.source}>
      <i style={{ width: 10, height: 10, borderRadius: 3, background: INET_COLORS[i % INET_COLORS.length], flexShrink: 0 }} />
      <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>{x.label}</b>
        <div className="dim ellipsis" style={{ fontSize: 12 }}>{fmt.time(x.t)}{x.server ? ' · ' + x.server : ''}{x.isp ? ' · ' + x.isp : ''}{x.ip ? ' · IP ' + x.ip : ''}{x.note ? ' · ' + x.note : ''}</div></div>
      {x.error ? <span className="badge offline" title={x.error}>ошибка</span> : <b className="mono" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>↓{Math.round(x.down)} ↑{Math.round(x.up)}{x.ping != null ? ` · ${x.ping} мс` : ''}</b>}
    </div> : null)}</div> : null}
    <div className="awg-form">
      <div className="card-title">Расписание</div>
      <div className="row wrap" style={{ gap: 12, alignItems: 'flex-end' }}>
        <label className="row" style={{ gap: 8 }}><Switch on={!!c.enabled} onChange={v => set('enabled', v)} /><span>Замерять автоматически</span></label>
        <Field label="Каждые"><select className="select" value={c.hours} onChange={e => set('hours', +e.target.value)}>
          {[1, 2, 4, 6, 12, 24].map(h => <option key={h} value={h}>{h} ч</option>)}</select></Field>
        <Field label="Тариф, Мбит/с" hint="Для линии на графике и уведомления о просадке"><input className="input" style={{ width: 120 }} value={c.tariff || ''} placeholder="1000"
          onChange={e => set('tariff', +e.target.value.replace(/\D/g, '') || 0)} /></Field>
        <Field label="Сервер замера"><select className="select" value={c.server === 'ookla' ? 'auto' : c.server} onChange={e => set('server', e.target.value)}>
          <option value="auto">Авто: Speedtest (Ookla), если доступен, иначе Cloudflare</option><option value="cloudflare">Только Cloudflare</option></select></Field>
      </div>
      <div className="dim3" style={{ fontSize: 12, lineHeight: 1.45 }}>Speedtest от Ookla меряет до ближайшего к провайдеру сервера (условия использования Ookla{n.ookla ? '' : '; утилиты в этой установке нет'}).
        В России он заблокирован — тогда замер идёт через Cloudflare, а его в России замедляют: <b>отдача и пинг могут быть занижены</b>, загрузка обычно близка к реальной.
        Через VPN-туннели Cloudflare меряет честно. Каждый замер — до 1 ГБ трафика на гигабитном тарифе.</div>
      {routers.map(d => <div key={d.id}>
        <div style={{ fontWeight: 600, fontSize: 13.5, margin: '4px 0' }}>Каналы роутера «{d.name}» {!d.entwarePasswordSet ? <span className="dim3" style={{ fontWeight: 400 }}>— нужен доступ к Entware (плагин «Entware»)</span> : null}</div>
        <div className="row wrap" style={{ gap: 6 }}>{tunnels(d).map(t => <button key={t.id} type="button" className={'chip' + (chan(d.id, t.id) ? ' on' : '')}
          disabled={!d.entwarePasswordSet} onClick={() => toggleChan(d.id, t.id)}><Icon name={t.id === 'isp' ? 'globe' : 'shield'} size={13} />{t.name}</button>)}</div></div>)}
      {servers.length ? <div><div style={{ fontWeight: 600, fontSize: 13.5, margin: '4px 0' }}>Интернет серверов</div>
        <div className="row wrap" style={{ gap: 6 }}>{servers.map(d => <button key={d.id} type="button" className={'chip' + ((c.servers || []).includes(d.id) ? ' on' : '')}
          onClick={() => set('servers', (c.servers || []).includes(d.id) ? c.servers.filter(x => x !== d.id) : [...(c.servers || []), d.id])}><Icon name="server" size={13} />{d.name}</button>)}</div></div> : null}
      <Btn onClick={save}>Сохранить</Btn>
    </div>
  </>;
}

/* config history of a router / switch */
function BackupsTab({ device }) {
  const { data, refresh } = useApp(); const toast = useToast();
  const [vers, setVers] = useState(null);
  const [sel, setSel] = useState(null);
  const [diff, setDiff] = useState(null);
  const load = async () => { try { const r = await api(`/api/backups/${device.id}`); setVers(r.versions); if (r.versions.length && !sel) setSel(r.versions[0].t); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); }, [device.id]);
  useEffect(() => { if (!sel) return; setDiff(null); api(`/api/backups/${device.id}/${sel}`).then(r => setDiff(r.diff)).catch(e => toast(e.message, true)); }, [sel]);
  const now = async () => { try { const r = await api(`/api/backups/${device.id}/run`, { method: 'POST', body: {} }); toast(r.message); setSel(null); load(); refresh(); } catch (e) { toast(e.message, true); } };
  if (!vers) return <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю историю…</div>;
  return <>
    <Hint id="backups">Rack Live раз в 6 часов сохраняет конфигурацию устройства, если она изменилась, и показывает, что именно поменялось. Если что-то сломалось после правки настроек —
      здесь видно, какие строки менялись, и можно скачать прошлую версию. Пароли и ключи в сравнении скрыты.</Hint>
    <div className="row wrap"><Btn icon="download" kind="primary" onClick={now}>Сохранить сейчас</Btn>
      <span className="dim3" style={{ fontSize: 12.5 }}>{vers.length ? `версий: ${vers.length} · проверено ${fmt.ago(vers[0].checked || vers[0].t, data.now)}` : 'копий ещё нет'}</span>
      {sel && diff && diff.length > 0 && (vers.find(v => v.t === sel) || {}).first === false ? <AskAi label="Что изменилось?" q={`Объясни простыми словами, что изменилось в конфигурации устройства «${device.name}» (id ${device.id}) в версии ${sel} от ${fmt.time(sel)}: что включили или выключили и не опасно ли это.`} /> : null}</div>
    {vers.length ? <div className="backup-grid">
      <div className="list backup-list">{vers.map(v => <div role="button" tabIndex={0} key={v.t} className={'li backup-v' + (sel === v.t ? ' on' : '')} onClick={() => setSel(v.t)}>
        <div className="grow" style={{ textAlign: 'left' }}><b style={{ fontSize: 13.5 }}>{fmt.time(v.t)}</b>
          <div className="dim" style={{ fontSize: 12 }}>{v.first ? `первая копия · ${v.lines} строк` : <><span style={{ color: 'var(--green)' }}>+{v.added}</span> <span style={{ color: 'var(--red)' }}>−{v.removed}</span></>}</div></div>
        <a className="btn sm icon" href={`/api/backups/${device.id}/${v.t}?raw=1`} onClick={e => e.stopPropagation()} title="Скачать эту версию"><Icon name="download" size={15} /></a>
      </div>)}</div>
      <div className="diff mono">{diff == null ? <span className="dim">…</span> : !diff.length ? <span className="dim">Нет отличий</span>
        : diff.map((l, i) => <div key={i} className={l[0] === '+' ? 'add' : l[0] === '-' ? 'del' : l.startsWith('@@') ? 'hunk' : ''}>{l || ' '}</div>)}</div>
    </div> : null}
  </>;
}

/* routers among the clients (subscribers, relatives, guests): add one with a press → link + login + password in its card */
const FOUND_KIND = { router: 'router', nas: 'nas', ha: 'server', proxmox: 'server', server: 'server', switch: 'switch', pc: 'pc', ups: 'ups' };
const FOUND_TEXT = { router: 'роутер', nas: 'NAS', ha: 'Home Assistant', proxmox: 'Proxmox', server: 'сервер', switch: 'коммутатор', pc: 'Windows', ups: 'ИБП' };
function RoutersCard() {
  const { data, refresh, newDevice } = useApp(); const toast = useToast();
  const rs = data.routerScan || {}; const list = rs.list || [];
  const [help, setHelp] = useState(null);
  useEffect(() => { if (!rs.running) return; const t = setInterval(refresh, 3000); return () => clearInterval(t); }, [rs.running]);
  const scan = async () => { try { await api('/api/routers/scan', { method: 'POST', body: {} }); toast('Ищу устройства в сети…'); setTimeout(refresh, 800); } catch (e) { toast(e.message, true); } };
  const dismiss = async (r, on) => { try { await api('/api/routers/dismiss', { method: 'POST', body: { mac: r.mac, on } }); refresh(); } catch (e) { toast(e.message, true); } };
  const add = r => {
    const w = r.web || {};
    if ((r.type || 'router') !== 'router') {
      newDevice({ driver: r.driver, kind: FOUND_KIND[r.type] || 'other', name: r.name,
        fields: { host: r.hostPreset || r.ip, location: 'local', site: '', ...(r.webUrl ? { webUrl: r.webUrl } : {}), ...(r.mode ? { mode: r.mode } : {}),
          notes: [r.what, r.hostname && r.hostname !== r.name ? r.hostname : ''].filter(Boolean).join(' · ') } });
      return;
    }
    newDevice({ driver: w.keenetic ? 'keenetic' : 'remote_web', kind: 'router', name: r.name,
      fields: { host: w.url || 'http://' + r.ip, location: 'local', username: 'admin', site: '',
        notes: [r.vendor, r.hostname, r.model].filter(Boolean).join(' · ') + (r.segment ? ` · сегмент ${r.segment}` : '') } });
  };
  return <Card title={`Найдено в сети${list.length ? ' · ' + list.filter(r => !r.dismissed).length : ''}`}
    right={<Btn size="sm" icon="refresh" busy={rs.running} onClick={scan}>{rs.running ? 'Ищу…' : 'Проверить'}</Btn>}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.45, marginBottom: 10 }}>Устройства вашей сети, за которыми Rack Live может следить, но их ещё нет в списке:
      роутеры абонентов и гостей, NAS, Home Assistant, Proxmox, серверы с SSH, управляемые коммутаторы, компьютеры с Windows. Rack Live только смотрит,
      какие порты открыты, — никуда не входит; пароль при добавлении вписываете вы.</div>
    {!list.length ? <div className="dim3" style={{ fontSize: 13 }}>{rs.last ? 'Новых устройств среди клиентов не найдено.' : 'Ещё не искал — нажмите «Проверить».'}</div>
      : <div className="list">{list.map(r => { const w = r.web || {};
        return <div className="li router-row" key={r.mac} style={{ opacity: r.dismissed ? .5 : 1 }}>
          <KindIcon kind={FOUND_KIND[r.type || 'router'] || 'other'} size={34} round={10} />
          <div className="grow" style={{ minWidth: 0 }}>
            <div className="row" style={{ gap: 6 }}><b style={{ fontSize: 14 }} className="ellipsis">{r.name}</b><span className="found-type">{FOUND_TEXT[r.type || 'router']}</span></div>
            <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{(r.type || 'router') !== 'router' ? r.what
              : [r.vendor, r.hostname && r.hostname !== r.name ? r.hostname : '', r.model].filter(Boolean).join(' · ') || 'роутер'}</div>
            <div className="dim3 mono ellipsis" style={{ fontSize: 11.5 }}>{[r.ip, r.segment, r.via && 'через ' + r.via].filter(Boolean).join(' · ')}</div>
            {(r.type || 'router') !== 'router' ? null : w.ok ? <div className="router-st ok"><Icon name="check" size={13} />{w.keenetic ? 'Keenetic отвечает — можно будет управлять' : 'Страница настроек открывается'}</div>
              : r.checked ? <div className="router-st warn"><Icon name="lock" size={13} />Вход в настройки закрыт с вашей стороны
                <button type="button" className="link-btn" onClick={() => setHelp(help === r.mac ? null : r.mac)}>{help === r.mac ? 'скрыть' : 'почему?'}</button></div> : null}
            {help === r.mac && !w.ok ? <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.45, marginTop: 4 }}>Для этого роутера ваша сеть — это «интернет», а заходить
              в настройки из интернета по умолчанию запрещено. Если нужно — у абонента в настройках роутера разрешите доступ к веб-интерфейсу со стороны WAN,
              лучше только с адресов вашей сети{r.ip ? ` (${r.ip.split('.').slice(0, 3).join('.')}.0/24)` : ''}. Ссылку и пароль можно сохранить и сейчас.</div> : null}
          </div>
          <div className="col" style={{ gap: 6, alignItems: 'stretch' }}>
            {!r.dismissed ? <Btn size="sm" kind="primary" icon="plus" onClick={() => add(r)}>Добавить</Btn> : null}
            <Btn size="sm" onClick={() => dismiss(r, !r.dismissed)}>{r.dismissed ? 'Вернуть' : 'Скрыть'}</Btn>
          </div>
        </div>; })}</div>}
    {rs.last ? <div className="dim3" style={{ fontSize: 11.5, marginTop: 8 }}>Проверено {fmt.ago(rs.last, data.now)} · Rack Live смотрит раз в 6 часов</div> : null}
  </Card>;
}

/* devices that showed up in the network recently — sorted by what the network's role says to do with them */
function NewDevicesCard() {
  const { data, refresh } = useApp(); const toast = useToast();
  const list = (data.newDevices || []).filter(r => findClient(data, r.mac));      // only what is in the network right now
  const ask = list.filter(r => r.decision === 'ask');
  const todoNets = (data.networks || []).filter(n => !n.role).length;
  const trust = async (r, on) => { try { await api('/api/newdev/trust', { method: 'POST', body: { mac: r.mac, on } }); refresh(); } catch (e) { toast(e.message, true); } };
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('newdev') === '1');
  const [edit, setEdit] = useState(null);             // mac → ClientEditor
  const [quietOpen, setQuietOpen] = useState(false);
  const groups = [['ask', 'Нужно ваше решение'], ['mine', 'Ваши устройства (зарегистрированы на роутере)'], ['ok', 'Подтверждённые'], ['quiet', 'Гостевые и служебные сети']];
  const row = r => { const role = roleOf(r.role); const live = findClient(data, r.mac);
    return <div className="li" key={r.mac + r.t} style={{ opacity: r.decision === 'ok' ? .6 : 1 }}>
      <KindIcon kind={r.random ? 'phone' : 'other'} size={32} round={9} />
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 6 }}><b className="ellipsis" style={{ fontSize: 14 }}>{(live && live.client.name) || r.name || (r.random ? 'Телефон или ноутбук' : 'Без имени')}</b>
          {role ? <span className="role-badge" style={{ background: role.color }}>{role.label}</span> : r.segment ? <span className="role-badge none">{r.segment}</span> : null}
          {r.random && (!live || macChanges(live.client)) ? <span className="role-badge none" title="Частный (случайный) MAC-адрес — может меняться">частный MAC</span> : null}</div>
        <div className="dim mono ellipsis" style={{ fontSize: 12 }}>{[r.ip, r.mac, r.via && 'через ' + r.via].filter(Boolean).join(' · ')}</div>
        <div className="dim3" style={{ fontSize: 11.5 }}>появилось {fmt.ago(r.t, data.now)}</div>
        {live ? <PendingIp c={live.client} /> : null}</div>
      <div className="col" style={{ gap: 6, alignItems: 'stretch' }}>
        {r.decision === 'ask' ? <Btn size="sm" kind="primary" onClick={() => trust(r, true)}>{r.role === 'subscribers' ? 'Я в курсе' : 'Это моё'}</Btn> : null}
        {r.decision === 'ok' ? <Btn size="sm" onClick={() => trust(r, false)}>Вернуть</Btn> : null}
        {live && r.router ? <Btn size="sm" icon="settings" onClick={() => setEdit(r.mac)}>Настроить</Btn> : null}
      </div></div>; };
  return <>
    <button type="button" className="card newdev-row" onClick={() => setOpen(true)}>
      <div className="newdev-ic"><Icon name="plus" size={18} />{ask.length ? <span className="count">{ask.length}</span> : null}</div>
      <div className="grow" style={{ minWidth: 0, textAlign: 'left' }}>
        <b style={{ fontSize: 14.5 }}>Новые в сети · за неделю: {list.length}</b>
        <div className="dim ellipsis" style={{ fontSize: 12.5 }}>{todoNets ? `отметьте сети (${todoNets}) — Rack Live поймёт, о чём спрашивать` : ask.length
          ? `ждут решения ${ask.length}: ` + ask.slice(0, 3).map(r => r.name || (r.random ? 'телефон/ноутбук' : r.mac)).join(', ') + (ask.length > 3 ? '…' : '')
          : list.length ? 'всё разобрано' : 'новых устройств не появлялось'}</div>
      </div>
      <Icon name="chevron" size={16} color="var(--text3)" />
    </button>
    {open ? <Modal title="Новые устройства в сети" wide onClose={() => setOpen(false)} icon={<Icon name="plus" size={20} color="var(--accent)" />}>
      <NetworkRoles />
      {!list.length ? <div className="dim3" style={{ fontSize: 13 }}>За неделю новых устройств не появлялось.</div>
        : groups.map(([g, title]) => { const items = list.filter(r => r.decision === g); if (!items.length) return null;
          const folded = g === 'quiet' && !quietOpen;
          return <div key={g}><div className="card-title" style={{ margin: '6px 0 2px', cursor: g === 'quiet' ? 'pointer' : 'default' }} onClick={() => g === 'quiet' && setQuietOpen(!quietOpen)}>
            {title} · {items.length}{g === 'quiet' ? (quietOpen ? ' ▴' : ' ▾') : ''}</div>
            {folded ? null : <div className="list">{items.map(row)}</div>}</div>; })}
      {edit ? <ClientEditor mac={edit} onClose={() => setEdit(null)} /> : null}
    </Modal> : null}
  </>;
}
