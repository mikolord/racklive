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
      <span className="dim3" style={{ fontSize: 12.5 }}>{vers.length ? `версий: ${vers.length} · проверено ${fmt.ago(vers[0].checked || vers[0].t, data.now)}` : 'копий ещё нет'}</span></div>
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

/* devices that showed up in the network recently */
function NewDevicesCard() {
  const { data, refresh } = useApp(); const toast = useToast();
  const list = data.newDevices || [];
  const fresh = list.filter(r => !r.trusted);
  const trust = async (r, on) => { try { await api('/api/newdev/trust', { method: 'POST', body: { mac: r.mac, on } }); refresh(); } catch (e) { toast(e.message, true); } };
  return <Card title={`Новые устройства в сети · за неделю${fresh.length ? ' · ' + fresh.length : ''}`}>
    {!list.length ? <div className="dim3" style={{ fontSize: 13 }}>За неделю новых устройств не появлялось. Когда подключится незнакомое — придёт уведомление.</div>
      : <div className="list">{list.map(r => <div className="li" key={r.mac + r.t} style={{ opacity: r.trusted ? .55 : 1 }}>
        <KindIcon kind={r.random ? 'phone' : 'other'} size={32} round={9} />
        <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>{r.name || (r.random ? 'Телефон или ноутбук (случайный MAC)' : 'Без имени')}</b>
          <div className="dim mono ellipsis" style={{ fontSize: 12 }}>{[r.ip, r.mac, r.segment, r.via && 'через ' + r.via].filter(Boolean).join(' · ')}</div>
          <div className="dim3" style={{ fontSize: 11.5 }}>появилось {fmt.ago(r.t, data.now)}</div></div>
        <Btn size="sm" onClick={() => trust(r, !r.trusted)}>{r.trusted ? 'Вернуть' : 'Это моё'}</Btn></div>)}</div>}
  </Card>;
}
