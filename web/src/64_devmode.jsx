/* «Режим разработчика»: the system of the machine Rack Live runs on — Settings → «Система» (time zone, updates, Docker, reboot) and «Сеть → Wi-Fi» (drivers, connecting, our own access point).
   Backend: rackd/hostops.py, /api/dev/* (admin only, and only while Settings → Основные → «Режим разработчика» is on). */
function useHostJob(onDone) {
  const toast = useToast();
  const [job, setJob] = useState(null); const [now, setNow] = useState(Date.now());
  const start = async (op, body = {}) => {
    try {
      const r = await api('/api/dev/op', { method: 'POST', body: { op, ...body } });
      if (r.job) setJob({ id: r.job, stage: 'Запуск…', done: false, t: Date.now() / 1000 }); else { toast(r.message || 'Готово'); if (onDone) onDone(r); }
      return r;
    } catch (e) { toast(e.message, true); return null; }
  };
  useEffect(() => {
    if (!job || job.done) return;
    const t = setInterval(async () => { setNow(Date.now());
      try { const j = await api('/api/dev/job', { method: 'POST', body: { job: job.id } }); setJob(x => ({ ...x, ...j }));
        if (j.done) { toast(j.error ? 'Не получилось: ' + j.error : (j.result && j.result.message) || 'Готово', !!j.error); if (onDone) onDone(j.result || null); } } catch (e) { }
    }, 2000);
    return () => clearInterval(t);
  }, [job && job.id, job && job.done]);
  return { job, now, start, running: !!job && !job.done };
}
function HostJobBar({ h }) {
  if (!h.job) return null;
  if (!h.job.done) return <div className="job"><span className="spin-dot" /><div className="grow"><b>{h.job.stage}</b>
    <div className="dim3" style={{ fontSize: 12 }}>{h.job.op} · идёт {Math.max(0, Math.round(h.now / 1000 - h.job.t))} с · окно можно закрыть, работа продолжится</div></div></div>;
  return h.job.error ? <div className="cam-err">{h.job.error}</div> : <div className="plugin-result"><Icon name="check" size={16} /> {(h.job.result && h.job.result.message) || 'Готово'}</div>;
}
function WordConfirm({ title, text, word, ok, onGo, onClose }) {
  const [w, setW] = useState('');
  return <Modal title={title} onClose={onClose}>
    <div className="cam-warn">{text}</div>
    <label className="col" style={{ gap: 3 }}><span className="dim3" style={{ fontSize: 12 }}>Чтобы продолжить, впишите слово <b>{word}</b></span>
      <input className="input" value={w} onChange={e => setW(e.target.value)} autoComplete="off" /></label>
    <div className="row" style={{ gap: 8 }}><Btn kind="danger" disabled={w.trim().toUpperCase() !== word} onClick={() => onGo(w.trim())}>{ok}</Btn><Btn onClick={onClose}>Отмена</Btn></div>
  </Modal>;
}

/* Settings → «Система» */
function DevSystem() {
  const { data } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [st, setSt] = useState(null); const [err, setErr] = useState('');
  const [zones, setZones] = useState([]); const [tz, setTz] = useState('');
  const [chk, setChk] = useState(null); const [rb, setRb] = useState(false); const [busy, setBusy] = useState('');
  const load = async () => { try { const r = await api('/api/dev/status'); setSt(r); setTz(t => t || r.tz || ''); setErr(''); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, []);
  const h = useHostJob(res => { if (res && res.packages) setChk(res); load(); });
  const quick = async (op, body, key) => {
    setBusy(key || op);
    try { const r = await api('/api/dev/op', { method: 'POST', body: { op, ...body } }); toast(r.message || 'Готово'); await load(); }
    catch (e) { toast(e.message, true); } finally { setBusy(''); }
  };
  const loadZones = async () => { if (zones.length) return; try { const r = await api('/api/dev/zones'); setZones(r.zones || []); } catch (e) { } };
  if (err) return <Card title="Система"><div className="cam-warn">{err}</div><div className="row" style={{ marginTop: 8 }}><Btn size="sm" icon="refresh" onClick={load}>Повторить</Btn></div></Card>;
  if (!st) return <Card title="Система"><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Читаю систему машины…</div></Card>;
  if (!st.ok) return <Card title="Система"><div className="cam-warn">{st.why}</div></Card>;
  const dk = st.docker || {};
  const hostDev = (data.devices || []).find(d => d.local) || (data.devices || []).find(d => d.driver === 'ssh' && ['127.0.0.1', location.hostname].includes(String(d.host || '').replace(/[:/].*$/, '')));
  return <>
    <Hint id="devsys">Это настоящая система машины, где работает Rack Live. Перед обновлениями и перезагрузкой Rack Live просит подтверждение; долгие операции идут в фоне, окно можно закрыть.</Hint>
    {!st.supported ? <div className="cam-warn" style={{ marginBottom: 12 }}>{st.why}</div> : null}
    <HostJobBar h={h} />
    <Card title="Система">
      <KV rows={[['ОС', st.os], ['Ядро', st.kernel ? st.kernel + (st.arch ? ' · ' + st.arch : '') : null], ['Работает без перезагрузки', fmt.uptime(st.uptime)], ['Где выполняются команды', st.mode === 'local' ? 'на этой машине (Rack Live работает от root)' : st.mode === 'ssh' ? 'по SSH на этой машине' : 'демо']]} />
    </Card>
    <Card title="Время и часовой пояс">
      <KV rows={[['Сейчас на машине', st.now], ['Часовой пояс', st.tz], ['Автосинхронизация времени', st.ntp ? 'включена' : 'выключена']]} />
      <Field label="Часовой пояс" hint="Например Europe/Moscow, Asia/Tbilisi, Europe/Kaliningrad. Начните печатать — появятся подсказки.">
        <div className="row" style={{ gap: 8 }}>
          <input className="input mono grow" list="rl-zones" value={tz} onFocus={loadZones} onChange={e => setTz(e.target.value)} placeholder="Europe/Moscow" />
          <datalist id="rl-zones">{zones.map(z => <option key={z} value={z} />)}</datalist>
          <Btn kind="primary" busy={busy === 'timezone'} disabled={!st.supported || !tz.trim() || tz.trim() === st.tz} onClick={() => quick('timezone', { tz: tz.trim() })}>Применить</Btn></div></Field>
      {!st.ntp ? <Btn style={{ marginTop: 10 }} busy={busy === 'ntp'} disabled={!st.supported} onClick={() => quick('ntp', {})}>Включить автосинхронизацию времени</Btn> : null}
    </Card>
    <Card title="Обновления системы">
      <KV rows={[['Можно обновить', st.upgradable == null ? '—' : st.upgradable + ' пакетов' + (st.aptAge ? ' · список от ' + fmt.ago(st.aptAge, data.now) : '')], ['Нужна перезагрузка', st.reboot ? 'да' : 'нет']]} />
      {st.reboot ? <div className="cam-warn" style={{ marginTop: 8 }}>Часть обновлений вступит в силу только после перезагрузки (например, новое ядро).</div> : null}
      {chk && chk.packages && chk.packages.length ? <div className="dim mono" style={{ fontSize: 12, marginTop: 8, lineHeight: 1.6 }}>{chk.packages.join(' · ')}{chk.count > chk.packages.length ? ' …' : ''}</div> : null}
      <div className="row wrap" style={{ gap: 8, marginTop: 10 }}>
        <Btn icon="refresh" disabled={!st.supported || h.running} onClick={() => h.start('check')}>Проверить обновления</Btn>
        <Btn kind="primary" icon="download" disabled={!st.supported || h.running} onClick={async () => { if (await confirm('Обновить установленные пакеты системы (apt upgrade)? Новые программы не добавляются и не удаляются, конфигурационные файлы остаются прежними. Займёт несколько минут; Rack Live продолжит работать.', { title: 'Обновление системы', ok: 'Обновить' })) h.start('upgrade'); }}>Обновить систему</Btn>
        <Btn kind="danger" icon="power" disabled={!st.supported || h.running} onClick={() => setRb(true)}>Перезагрузить машину</Btn></div>
    </Card>
    <Card title="Docker">
      <KV rows={[['Версия', dk.version || 'не установлен'], ['Пакеты', (dk.packages || []).map(p => p.name + ' ' + p.version).join(' · ') || null]]} />
      <Btn style={{ marginTop: 10 }} icon="download" disabled={!st.supported || h.running} onClick={async () => { if (await confirm(dk.version ? 'Обновить Docker и связанные пакеты (containerd, compose) до последних версий из репозитория системы? Контейнеры на время обновления могут перезапуститься.' : 'Docker не установлен. Поставить docker.io из репозитория системы?', { title: 'Docker', ok: dk.version ? 'Обновить' : 'Установить' })) h.start('docker'); }}>{dk.version ? 'Обновить Docker' : 'Установить Docker'}</Btn>
    </Card>
    {hostDev ? <><div className="card-title" style={{ margin: '18px 4px 8px' }}>Плагины этой машины</div>
      <PluginsTab device={hostDev} /></> : null}
    {rb ? <WordConfirm title="Перезагрузка машины" word="ПЕРЕЗАГРУЗИТЬ" ok="Перезагрузить" onClose={() => setRb(false)}
      text="Машина перезагрузится через 3 секунды. Панель, терминал и всё, что подключено по Wi-Fi-точке этой машины, на 1–2 минуты пропадёт, потом вернётся само."
      onGo={w => { setRb(false); quick('reboot', { confirm: w }); }} /> : null}
  </>;
}

/* Settings → «Сеть»: with the developer mode on there are two tabs, «Сеть» and «Wi-Fi» */
function NetworkTabs() {
  const { data } = useApp();
  const [tab, setTab] = useState(() => { const q = new URLSearchParams(location.search).get('nettab'); return q === 'wifi' ? 'wifi' : lsGet('rl_net_tab', 'net'); });
  if (!data.devMode) return <NetworkCard />;
  const pick = v => { setTab(v); lsSet('rl_net_tab', v); };
  return <>
    <Seg value={tab} onChange={pick} options={[{ value: 'net', label: 'Сеть' }, { value: 'wifi', label: 'Wi-Fi', icon: 'wifi' }]} />
    <div style={{ height: 12 }} />
    {tab === 'wifi' ? <WifiCard /> : <NetworkCard />}
  </>;
}

/* Settings → «Сеть» → «Wi-Fi» */
const wifiEsc = s => String(s).replace(/([\\;,:"])/g, '\\$1');
function WifiCard() {
  const toast = useToast(); const confirm = useConfirm();
  const [w, setW] = useState(null); const [err, setErr] = useState('');
  const [ifc, setIfc] = useState(''); const [ssid, setSsid] = useState(''); const [pw, setPw] = useState(''); const [addr, setAddr] = useState(''); const [band, setBand] = useState('bg'); const [force, setForce] = useState(false);
  const [editAp, setEditAp] = useState(false);
  const [cIf, setCIf] = useState(''); const [nets, setNets] = useState(null); const [scanning, setScanning] = useState(false); const [pick, setPick] = useState(''); const [cpw, setCpw] = useState(''); const [manual, setManual] = useState(false); const [showPw, setShowPw] = useState(false);
  const load = async () => { try { setW(await api('/api/dev/wifi')); setErr(''); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, []);
  const h = useHostJob(() => load());
  const names = w && w.ok ? w.interfaces.map(i => i.name) : [];
  useEffect(() => {                                         // fill the forms once the adapters are known
    if (!w || !w.ok) return;
    const ap = w.apConfig || {};
    setIfc(x => x || (w.hotspot && w.hotspot.iface) || ap.iface || names[0] || ''); setCIf(x => x || names[names.length > 1 ? 1 : 0] || '');
    setSsid(x => x || ap.ssid || 'ReckController'); setPw(x => x || ap.password || ''); setAddr(x => x || ap.address || w.suggestAddress || '');
  }, [w && w.ok && names.join()]);
  const scan = async () => {
    setScanning(true); setNets(null); setPick('');
    try { const r = await api('/api/dev/op', { method: 'POST', body: { op: 'scan', iface: cIf } }); setNets(r.networks || []); }
    catch (e) { toast(e.message, true); setNets([]); } finally { setScanning(false); }
  };
  const quick = async (op, body, msg) => { const r = await h.start(op, body); if (r && !r.job) load(); };
  if (err) return <Card title="Wi-Fi"><div className="cam-warn">{err}</div><div className="row" style={{ marginTop: 8 }}><Btn size="sm" icon="refresh" onClick={load}>Повторить</Btn></div></Card>;
  if (!w) return <Card title="Wi-Fi"><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Читаю Wi-Fi машины…</div></Card>;
  if (!w.ok) return <Card title="Wi-Fi"><div className="cam-warn">{w.why}</div></Card>;
  const ready = w.nm === 'active' && names.length > 0;
  const hs = w.hotspot || {}; const ap = w.apConfig || {};
  const defOnIfc = w.defaultDev && w.defaultDev === ifc;
  const defOnC = w.defaultDev && w.defaultDev === cIf;
  const url = hs.on && hs.address ? `http://${hs.address.split('/')[0]}:${w.port}` : '';
  const viaAp = hs.on && hs.address && location.hostname === hs.address.split('/')[0];          // this very page came through our access point
  const editing = !hs.on || editAp;
  const join = hs.on && ap.ssid && ap.password ? `WIFI:T:WPA;S:${wifiEsc(ap.ssid)};P:${wifiEsc(ap.password)};;` : '';
  const chipText = (w.chips || []).map(c => c.vendorName + (c.name ? ' ' + c.name : '')).join(', ');
  const sel = nets && nets.find(n => n.ssid === pick);
  const setupDrivers = async () => { if (await confirm(`Rack Live установит NetworkManager и всё для Wi-Fi${w.chips && w.chips.length ? ' и прошивку для вашего адаптера (' + chipText + ')' : ''}. На Debian при необходимости подключит раздел non-free-firmware (копии файлов с .rl-bak). Кабельная сеть и этот сеанс не затрагиваются. Нужен интернет, займёт 2–5 минут.`, { title: 'Драйверы Wi-Fi', ok: 'Поставить' })) h.start('drivers'); };
  return <>
    <HostJobBar h={h} />
    {!ready ? <Card title="Подготовка">
      <div className="col" style={{ gap: 8 }}>
        <div className="checks">
          <div className={'check ' + (names.length ? 'ok' : 'no')}><span className="check-ico"><Icon name={names.length ? 'check' : 'x'} size={13} stroke={2.4} /></span><span className="grow">{names.length ? 'Wi-Fi-адаптер виден: ' + names.join(', ') : 'Wi-Fi-адаптер не виден системе' + (chipText ? ' (найден чип: ' + chipText + ' — нужна прошивка)' : '')}</span></div>
          <div className={'check ' + (w.nm === 'active' ? 'ok' : 'no')}><span className="check-ico"><Icon name={w.nm === 'active' ? 'check' : 'x'} size={13} stroke={2.4} /></span><span className="grow">NetworkManager {w.nm === 'active' ? 'работает' : 'не установлен или не запущен'}</span></div>
          {w.blocked ? <div className="check no"><span className="check-ico"><Icon name="x" size={13} stroke={2.4} /></span><span className="grow">Wi-Fi выключен программно (rfkill) — установка включит его</span></div> : null}
        </div>
        <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Для любого Debian, Ubuntu или Raspberry Pi OS: Rack Live ставит NetworkManager, инструменты Wi-Fi и прошивки под ваш адаптер. USB-ключи на нестандартных чипах (некоторые Realtek) могут потребовать драйвера, которых нет в репозитории, — тогда выбирайте ключ с чипом Intel, Atheros или MediaTek.</div>
        <Btn kind="primary" icon="download" disabled={h.running} onClick={setupDrivers}>Поставить драйверы и NetworkManager</Btn>
      </div></Card> : null}
    {ready ? <Card title="Адаптеры" right={<Btn size="sm" icon="refresh" onClick={load} />}>
      <div className="list">{w.interfaces.map(i => <div className="li" key={i.name} style={{ alignItems: 'center' }}><div className="grow"><b className="mono">{i.name}</b>
        <div className="dim3" style={{ fontSize: 12 }}>{i.driver || 'драйвер не определён'} · {i.mac}{i.ip ? ' · ' + i.ip : ''}{i.stations ? ' · подключено устройств: ' + i.stations : ''}</div></div>
        <span className={'badge ' + (i.state === 'up' ? 'online' : '')}>{i.state === 'up' ? 'работает' : i.state || '—'}</span></div>)}</div>
      {w.iw && !w.apCapable ? <div className="cam-warn" style={{ marginTop: 8 }}>Этот адаптер не умеет работать точкой доступа. Подключаться к чужим сетям он сможет; для своей точки нужен USB-ключ с поддержкой режима AP.</div> : null}
      {names.length > 1 ? null : <div className="dim3" style={{ fontSize: 12.5, marginTop: 8 }}>Адаптер один: он может либо раздавать свою точку, либо подключаться к чужой сети — не то и другое сразу. Для обоих сразу нужен второй адаптер (например, USB-ключ).</div>}
    </Card> : null}
    {ready ? <Card title="Своя Wi-Fi-точка">
      <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Машина раздаёт собственную сеть с постоянным адресом: подключитесь к ней с телефона и откройте панель — адрес не зависит от сетей клиентов. Телефон выходит в интернет через кабель машины.</div>
      {hs.on ? <div className="plugin-result" style={{ marginTop: 10 }}>
        <div className="row" style={{ gap: 8, alignItems: 'flex-start', marginBottom: 8 }}><Icon name="check" size={18} /><b className="grow">Точка «{hs.ssid}» работает</b></div>
        <div className="row wrap" style={{ gap: 14, alignItems: 'flex-start' }}>
          <div className="col grow" style={{ gap: 6, minWidth: 220 }}>
            <CopyRow k="Сеть" v={hs.ssid} mono={false} />
            {ap.password ? <CopyRow k="Пароль" v={ap.password} /> : null}
            <div className="copy-row"><span className="dim">Панель</span><a className="grow ellipsis" href={url}>{url}</a></div>
            <div className="dim3" style={{ fontSize: 12.5 }}>На телефоне: «Настройки → Wi-Fi» → сеть «{hs.ssid}» → пароль → откройте {url.replace('http://', '')} в браузере.</div></div>
          {join ? <div className="col" style={{ alignItems: 'center', gap: 4 }}><QrCode text={join} size={140} /><span className="dim3" style={{ fontSize: 11.5 }}>QR: подключиться к сети</span></div> : null}
        </div></div> : hs.exists ? <div className="dim" style={{ marginTop: 10 }}>Точка настроена («{hs.ssid}»), но сейчас выключена.</div> : null}
      {!editing ? <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
        <Btn kind="primary" icon="edit" disabled={h.running} onClick={() => { setSsid(hs.ssid || ap.ssid || ssid); setPw(ap.password || ''); setEditAp(true); }}>Изменить название или пароль</Btn>
        <Btn disabled={h.running} onClick={async () => { if (await confirm(viaAp ? 'Вы сейчас подключены через эту точку: после выключения телефон потеряет связь с машиной, и эта страница перестанет открываться. Выключить?' : 'Выключить точку? Устройства, подключённые к ней (например, телефон), потеряют связь с машиной.', { title: 'Wi-Fi-точка', ok: 'Выключить', danger: true })) quick('ap_off', {}); }}>Выключить</Btn>
      </div> : null}
      {editing ? <div className="awg-form" style={{ marginTop: 12 }}>
        {hs.on && viaAp ? <div className="cam-warn">Вы подключены через эту точку. После «Применить» она перезапустится с новыми настройками: телефон отключится на несколько секунд — подключитесь к сети «{ssid.trim() || hs.ssid}» {pw && pw !== ap.password ? 'с новым паролем' : 'заново'}. Адрес панели останется {url.replace('http://', '')}.</div> : null}
        <div className="row wrap" style={{ gap: 8 }}>
          <Field label="Адаптер"><select className="input" value={ifc} onChange={e => setIfc(e.target.value)}>{names.map(n => <option key={n} value={n}>{n}</option>)}</select></Field>
          <Field label="Название сети"><input className="input" value={ssid} onChange={e => setSsid(e.target.value)} /></Field></div>
        <Field label="Пароль Wi-Fi" hint="От 8 символов. Пусто — Rack Live придумает сам и покажет здесь.">
          <div className="row" style={{ gap: 8 }}><input className="input mono grow" type={showPw ? 'text' : 'password'} value={pw} placeholder={ap.password ? '' : 'придумается сам'} onChange={e => setPw(e.target.value)} />
            <Btn size="sm" icon="eye" onClick={() => setShowPw(!showPw)} /></div></Field>
        <div className="row wrap" style={{ gap: 8 }}>
          <Field label="Адрес панели в этой сети" hint={`Свободная частная сеть, чтобы не пересекаться с сетями клиентов. Предложено: ${w.suggestAddress}`}><input className="input mono" value={addr} onChange={e => setAddr(e.target.value)} /></Field>
          <Field label="Диапазон"><select className="input" value={band} onChange={e => setBand(e.target.value)}><option value="bg">2,4 ГГц — подойдёт всем адаптерам</option><option value="a">5 ГГц — если адаптер умеет</option></select></Field></div>
        {defOnIfc ? <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={force} onChange={setForce} /><div className="grow"><div>Я понимаю, что связь может пропасть</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Через адаптер {ifc} сейчас идёт связь этой машины с сетью. Если превратить его в точку, эта панель и SSH исчезнут, пока не подключён кабель.</div></div></div> : null}
        <div className="row wrap" style={{ gap: 8 }}>
          <Btn kind="primary" icon="wifi" disabled={h.running || !ifc || !ssid.trim() || (pw && pw.length < 8) || (defOnIfc && !force)} onClick={() => { h.start('ap_on', { iface: ifc, ssid: ssid.trim(), password: pw, address: addr.trim(), band, force }); setEditAp(false); }}>{hs.on ? 'Применить' : 'Включить точку'}</Btn>
          {hs.on ? <Btn disabled={h.running} onClick={() => setEditAp(false)}>Отмена</Btn> : null}
          {hs.exists && !hs.on ? <Btn kind="danger" icon="trash" disabled={h.running} onClick={async () => { if (await confirm('Удалить настройки точки вместе с паролем?', { title: 'Wi-Fi-точка', ok: 'Удалить', danger: true })) quick('ap_forget', {}); }}>Удалить настройки</Btn> : null}</div>
        {pw && pw.length < 8 ? <div className="dim3" style={{ fontSize: 12.5, color: 'var(--red)' }}>Пароль Wi-Fi — от 8 символов.</div> : null}
      </div> : null}</Card> : null}
    {ready ? <Card title="Подключение к Wi-Fi">
      <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Машина подключается к чужой сети как обычное устройство — когда нет кабеля. Если адаптер один, его точка на время выключится.</div>
      {(w.profiles || []).length ? <><div className="card-title" style={{ marginTop: 12 }}>Сохранённые сети</div>
        <div className="list">{w.profiles.map(p => <div className="li" key={p.id} style={{ alignItems: 'center' }}><div className="grow"><b>{p.ssid || p.id}</b><div className="dim3" style={{ fontSize: 12 }}>{p.active ? 'подключена · ' + p.device : 'не подключена'}</div></div>
          <Btn size="sm" icon="trash" disabled={h.running} onClick={async () => { if (await confirm(`Забыть сеть «${p.ssid || p.id}»?`, { title: 'Wi-Fi', ok: 'Забыть', danger: true })) quick('forget', { profile: p.id }); }} /></div>)}</div></> : null}
      <div className="awg-form" style={{ marginTop: 12 }}>
        <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
          <Field label="Адаптер"><select className="input" value={cIf} onChange={e => { setCIf(e.target.value); setNets(null); }}>{names.map(n => <option key={n} value={n}>{n}</option>)}</select></Field>
          <Btn icon="search" busy={scanning} disabled={h.running || !cIf} onClick={scan}>Искать сети</Btn></div>
        {nets ? (nets.length ? <div className="list">{nets.map(n => <button type="button" key={n.ssid} className={'li wifi-net' + (pick === n.ssid ? ' on' : '')} onClick={() => { setPick(n.ssid); setManual(false); }} style={{ alignItems: 'center', textAlign: 'left' }}>
          <Icon name="wifi" size={16} /><div className="grow"><b>{n.ssid}</b>{n.current ? <span className="badge online" style={{ marginLeft: 6 }}>подключена</span> : null}<div className="dim3" style={{ fontSize: 12 }}>{n.security || 'открытая'} · канал {n.channel}</div></div>
          <span className="dim mono" style={{ fontSize: 12 }}>{n.signal}%</span></button>)}</div> : <div className="dim3">Сетей не найдено.</div>) : null}
        <div className="row" style={{ gap: 8, alignItems: 'center' }}><Switch on={manual} onChange={v => { setManual(v); if (v) setPick(''); }} /><span className="dim" style={{ fontSize: 13 }}>Скрытая сеть: ввести название вручную</span></div>
        {manual ? <Field label="Название сети"><input className="input" value={pick} onChange={e => setPick(e.target.value)} /></Field> : null}
        {(pick || manual) && (manual || (sel && sel.security)) ? <Field label={'Пароль сети «' + pick + '»'}><input className="input mono" type="password" value={cpw} onChange={e => setCpw(e.target.value)} /></Field> : null}
        {defOnC ? <div className="cam-warn">Через адаптер {cIf} сейчас идёт связь машины. Подключение к другой сети его перенастроит — эта панель может пропасть. Лучше подключите кабель.</div> : null}
        {viaAp && hs.iface === cIf ? <div className="cam-warn">Вы подключены через точку этой машины на том же адаптере {cIf}. Если подключить его к другой сети, точка выключится и телефон потеряет связь с панелью. Для того и другого сразу нужен второй Wi-Fi-адаптер.</div> : null}
        <Btn kind="primary" icon="wifi" disabled={h.running || !pick || !cIf} onClick={async () => {
          if (defOnC && !(await confirm(`Адаптер ${cIf} сейчас — единственный канал связи. Подключиться всё равно?`, { title: 'Wi-Fi', ok: 'Подключиться', danger: true }))) return;
          const cut = viaAp && hs.iface === cIf;
          if (cut && !(await confirm(`Точка «${hs.ssid}» выключится, телефон потеряет связь с машиной, и эта страница перестанет открываться. Вернуть точку можно будет с кабеля или после перезагрузки. Подключиться всё равно?`, { title: 'Wi-Fi', ok: 'Подключиться', danger: true }))) return;
          h.start('connect', { iface: cIf, ssid: pick, password: cpw, hidden: manual, force: defOnC || cut }); setCpw('');
        }}>Подключиться</Btn>
      </div></Card> : null}
  </>;
}
