/* «Гостевой Wi-Fi с порталом» (OpenWrt, rackd/portal.py): the network profile of the router, what every port gives,
   the guest login and the design of the guest page — a library of templates, switched with one button. */
const PORT_ROLE_OPTS = [['main', 'Основная'], ['guest', 'Гостевая'], ['trunk', 'Обе (для точек)'], ['off', 'Выключен']];
const BAND_TEXT = { '2g': '2,4 ГГц', '5g': '5 ГГц', '6g': '6 ГГц' };

function PortalPlugin({ p, device, reload }) {
  const toast = useToast(); const confirm = useConfirm();
  const hw = p.hw || {};
  const base = p.saved || p.routerProfile || p.defaults || {};
  const [f, setF] = useState(() => ({ ...base, mainKey: '', guestKey: '', password: '', smsPass: '', ports: { ...(base.ports || {}) } }));
  const [smsTo, setSmsTo] = useState('');
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  const [tpls, setTpls] = useState(p.templates || [{ id: 'default', name: 'Стандартный (Rack Live)', builtin: true }]);
  const [busy, setBusy] = useState(''); const [stage, setStage] = useState(''); const [result, setResult] = useState(null);
  const [sel, setSel] = useState(null);      // null — обычный вид; список id — режим «выбрать шаблоны для удаления»
  const [upName, setUpName] = useState(''); const fileRef = useRef(null); const [rootPass, setRootPass] = useState('');
  const [show, setShow] = useState(() => new URLSearchParams(location.search).get('psec') || (p.installed ? '' : 'net'));      // ?psec=ports|login|tpl|adv — for tests
  const call = body => api(`/api/devices/${device.id}/plugins`, { method: 'POST', body: { plugin: 'portal', ...body } });
  const pollJob = async id => {
    for (let i = 0; i < 200; i++) {
      await new Promise(r => setTimeout(r, 2500));
      let j; try { j = await call({ op: 'job', job: id }); } catch (e) { continue; }
      if (j.stage) setStage(j.stage);
      if (j.done) return j.error ? { ok: false, error: j.error } : { ...(j.result || {}), ok: (j.result || {}).ok !== false };
    }
    return { ok: false, error: 'настройка заняла слишком долго — проверьте роутер' };
  };
  const smsBlock = () => <div className="stack" style={{ gap: 10 }}>
    <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Гость вводит номер телефона и получает код в СМС. Код отправляет второй роутер, в котором стоит SIM-карта: подключите его LAN-порт в LAN-порт этого роутера
      (не в гостевой порт). Этому роутеру нужен только адрес и пароль того; ключ для отправки СМС создаётся сам.</div>
    <details className="guide"><summary>Как подготовить роутер с SIM-картой</summary>
      <ol className="steps" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
        <li><b>SIM-карта.</b> Вставьте её в роутер при выключенном питании. Уберите запрос PIN-кода (вставьте SIM в телефон → «Блокировка SIM» → выключить PIN). На счету должны быть деньги, а отправка СМС с неё — работать (проверьте с телефона). Мобильный интернет не нужен.</li>
        <li><b>Сброс.</b> Если роутер уже настраивали, сбросьте его до заводских настроек. Нужна чистая OpenWrt с модемом, который видится как порты <code>/dev/ttyUSB*</code> (обычные USB- и встроенные LTE-модемы). Модемы, работающие как сетевая карта (HiLink), СМС по AT-командам не отдают.</li>
        <li><b>Подключение к ПК.</b> Кабель из компьютера в LAN-порт роутера с SIM, адрес в браузере — <code>192.168.1.1</code> (у OpenWrt по умолчанию). Wi-Fi ему не нужен.</li>
        <li><b>Пароль.</b> System → Administration → задайте пароль root. SSH на OpenWrt включён сам. Запомните пароль — его надо будет вписать ниже.</li>
        <li><b>Адрес.</b> Network → Interfaces → lan → Edit. Протокол «Static address», IPv4 address <code>192.168.10.2/24</code> (в одной сети с этим роутером, по умолчанию он <code>192.168.10.1</code>). Поле «IPv4 gateway» и DNS <b>оставьте пустыми</b> — Rack Live пропишет их сам. На вкладке «DHCP Server» поставьте галочку «Ignore interface» (иначе роутер с SIM начнёт раздавать адреса чужой сети).</li>
        <li><b>Применить.</b> «Save» → «Save &amp; Apply». Страница отвалится — так и должно быть (роутер переехал на новый адрес). Если LuCI предложит «Apply unchecked», нажмите.</li>
        <li><b>Провод.</b> Из LAN-порта роутера с SIM — в LAN-порт <b>этого</b> роутера (не в гостевой порт и не в WAN).</li>
        <li><b>Здесь.</b> Впишите адрес <code>192.168.10.2</code>, логин <code>root</code> и пароль, нажмите «Подготовить роутер с SIM» и дождитесь галочки (1–2 минуты). Потом — «Отправить тестовую СМС» на свой номер и «Сохранить вход гостей».</li>
      </ol>
      <div className="dim3" style={{ fontSize: 12.5 }}>Rack Live сам поставит на роутер с SIM программу отправки СМС и разрешит этому роутеру только отправлять СМС (ограниченный ключ) — управлять роутером с SIM через него нельзя. Пароль от роутера с SIM нужен один раз и нигде не хранится на роутерах.</div>
    </details>
    <div className="pt-grid">
      <Field label="Роутер с SIM — адрес (так его видит этот роутер)"><input className="input mono" value={f.smsHost || ''} placeholder="192.168.10.2" onChange={e => set('smsHost', e.target.value)} /></Field>
      <Field label="Логин"><input className="input mono" value={f.smsUser || 'root'} onChange={e => set('smsUser', e.target.value)} /></Field>
      <Field label="Пароль роутера с SIM (нужен один раз, не хранится на роутерах)"><input className="input" type="password" value={f.smsPass || ''} placeholder={base.smsPassSet ? 'не менять' : 'пароль root'} onChange={e => set('smsPass', e.target.value)} /></Field>
    </div>
    {p.installed ? <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
      <Btn icon="check" busy={busy === 'sms_setup'} disabled={working || !f.smsHost || (!f.smsPass && !base.smsPassSet)} onClick={smsSetup}>{base.smsReady ? 'Подготовить заново' : 'Подготовить роутер с SIM'}</Btn>
      {base.smsReady ? <span className="dim3" style={{ fontSize: 12.5 }}>✔ готов: {base.smsInfo}</span> : null}
    </div> : <div className="dim3" style={{ fontSize: 12.5 }}>Роутер с SIM подготавливается после настройки этого роутера (кнопка появится здесь).</div>}
    {p.installed && base.smsReady ? <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
      <input className="input mono" style={{ maxWidth: 220 }} value={smsTo} placeholder="+7 900 123-45-67" onChange={e => setSmsTo(e.target.value)} />
      <Btn busy={busy === 'sms_test'} disabled={working || !smsTo} onClick={() => quick({ op: 'sms_test', phone: smsTo }, 'Отправлено')}>Отправить тестовую СМС</Btn>
    </div> : null}
  </div>;
  const portRole = n => (f.ports || {})[n] || 'main';
  const profile = () => ({ ...f, ports: Object.fromEntries((hw.lan || []).map(n => [n, portRole(n)])) });

  const apply = async () => {
    const lanIp = (f.lan || '').split('/')[0];
    const ok = await confirm(`Rack Live настроит роутер: ${f.mainWifi === false ? 'без основной Wi-Fi' : `основная Wi-Fi «${f.mainSsid || '—'}»`}, гостевая «${f.guestSsid}»${f.portal ? ' со страницей входа' : ''}, `
      + `основная сеть ${f.lan}, гостевая ${f.guest}. Роутер перезапустит сеть — на 1–2 минуты связь с ним пропадёт, а устройства в его сети получат новые адреса. `
      + `Если Rack Live не сможет снова зайти на роутер, через 4 минуты он сам вернёт прежние настройки. После настройки роутер будет на ${lanIp} (из его сети)`
      + `${f.mgmtWan ? ' и по адресу WAN (из сети, к которой он подключён)' : ''}. Продолжить?`, { title: 'Настроить роутер', ok: 'Настроить' });
    if (!ok) return;
    setBusy('install'); setResult(null); setStage('Отправляю настройки…');
    try {
      let r = await call({ op: 'install', profile: profile(), rootPass });
      if (r.job) r = await pollJob(r.job);
      setResult({ ...r, up: r.ok, kept: true }); toast(r.message || r.error || '', !r.ok); reload();
    } catch (e) { setResult({ error: e.message }); toast(e.message, true); }
    finally { setBusy(''); setStage(''); }
  };
  const quick = async (body, label) => {
    setBusy(body.op); setResult(null);
    try { const r = await call(body); toast(r.message || r.error || label, !r.ok); setResult({ ...r, up: r.ok, kept: true }); reload(); }
    catch (e) { toast(e.message, true); }
    finally { setBusy(''); }
  };
  const smsSetup = async () => {
    if (!(await confirm(`Rack Live зайдёт на роутер с SIM-картой (${f.smsHost}) и подготовит его: поставит программу отправки СМС и разрешит этому роутеру только отправлять СМС (больше ничего). `
      + 'Чтобы поставить один маленький пакет, роутер с SIM на время выйдет в интернет через этот роутер; мобильный интернет SIM-карты не нужен и не тратится. Продолжить?', { title: 'Подготовить роутер с SIM', ok: 'Подготовить' }))) return;
    setBusy('sms_setup'); setResult(null); setStage('Готовлю роутер с SIM…');
    try {
      let r = await call({ op: 'sms_setup', profile: profile() });
      if (r.job) r = await pollJob(r.job);
      setResult({ ...r, up: r.ok, kept: true }); toast(r.message || r.error || '', !r.ok); set('smsPass', ''); reload();
    } catch (e) { setResult({ error: e.message }); toast(e.message, true); }
    finally { setBusy(''); setStage(''); }
  };
  const remove = async () => {
    if (!(await confirm('Удалить портал полностью? Rack Live вернёт роутеру настройки, которые были перед установкой портала: сеть и адрес, Wi-Fi, DHCP, межсетевой экран. '
      + 'Гостевая сеть, страница входа, OpenNDS и шаблоны будут удалены. Пароль администратора роутера останется новым (ради безопасности). '
      + 'Роутер перезапустит сеть и вернётся на свой прежний адрес — связь с ним пропадёт на минуту. Продолжить?', { title: 'Удалить портал полностью', ok: 'Удалить', danger: true }))) return;
    setBusy('remove'); setResult(null); setStage('Возвращаю исходные настройки…');
    try { let r = await call({ op: 'remove' }); if (r.job) r = await pollJob(r.job); setResult({ ...r, up: r.ok, kept: true }); toast(r.message || r.error || '', !r.ok); reload(); }
    catch (e) { toast(e.message, true); }
    finally { setBusy(''); setStage(''); }
  };
  const upload = async file => {
    if (!file) return;
    setBusy('upload');
    try {
      const init = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/zip' }, body: file };
      const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
      const r = await (await fetch('/api/portal/templates?name=' + encodeURIComponent(upName || file.name.replace(/\.zip$/i, '')), init)).json();
      if (!r.ok) throw new Error(r.error || 'шаблон не подошёл');
      setTpls(r.templates); set('template', r.template.id); setUpName(''); toast('Шаблон загружен и выбран');
    } catch (e) { toast(e.message, true); }
    finally { setBusy(''); if (fileRef.current) fileRef.current.value = ''; }
  };
  const delTpl = async t => {
    if (!(await confirm(`Удалить шаблон «${t.name}» из библиотеки?`, { title: 'Удалить шаблон', ok: 'Удалить', danger: true }))) return;
    try { const r = await api('/api/portal/templates/' + t.id, { method: 'DELETE' }); setTpls(r.templates); if (f.template === t.id) set('template', 'default'); }
    catch (e) { toast(e.message, true); }
  };
  // шаблон, который нельзя удалить пачкой: встроенный и тот, что сейчас стоит на роутере
  const keepTpl = t => !!t.builtin || (p.installed && savedTpl === t.id);
  const togSel = t => { if (!keepTpl(t)) setSel(s => (s || []).includes(t.id) ? s.filter(x => x !== t.id) : [...(s || []), t.id]); };
  const delMany = async () => {
    const ids = (sel || []).filter(id => { const t = tpls.find(x => x.id === id); return t && !keepTpl(t); });
    if (!ids.length) return;
    if (!(await confirm(`Удалить выбранные шаблоны из библиотеки: ${ids.length} шт.? Вернуть их можно только загрузив .zip заново. На роутере ничего не меняется.`, { title: 'Удалить шаблоны', ok: `Удалить (${ids.length})`, danger: true }))) return;
    setBusy('delmany');
    let list = tpls, done = 0;
    try {
      for (const id of ids) { const r = await api('/api/portal/templates/' + id, { method: 'DELETE' }); list = r.templates; done++; }
      toast(`Удалено шаблонов: ${done}`);
    } catch (e) { toast(`Удалено ${done} из ${ids.length}: ${e.message}`, true); }
    setTpls(list); if (!list.some(t => t.id === f.template)) set('template', 'default');
    setSel(null); setBusy('');
  };

  const sec =(id, title, sub, body) => <div className={'pt-sec' + (show === id ? ' open' : '')}>
    <button type="button" className="pt-sec-h" onClick={() => setShow(show === id ? '' : id)}><b>{title}</b><span className="dim3">{sub}</span><Icon name="chevron" size={14} /></button>
    {show === id ? <div className="pt-sec-b">{body}</div> : null}</div>;
  const savedTpl = (p.saved || p.routerProfile || {}).template || 'default';
  const working = !!busy;

  if (p.foreign) return <ForeignPortal p={p} hw={hw} />;
  return <>
    <PortalGuide installed={p.installed} />
    {!p.installed ? <WanPrep p={p} call={call} reload={reload} /> : null}
    <Checks checks={p.checks || []} />
    {p.installed ? <div className="pt-live">
      <div className="row" style={{ gap: 12, alignItems: 'center' }}>
        <div className="grow" style={{ minWidth: 0 }}><b>Captive-портал</b>
          <div className="dim3" style={{ fontSize: 12.5 }}>{p.status || ''}{(p.saved || p.routerProfile) ? ` · гостевая «${(p.saved || p.routerProfile).guestSsid}», основная «${(p.saved || p.routerProfile).mainSsid}»` : ''}</div></div>
        <Switch on={!!hw.ndsRunning || (busy === 'toggle' ? !f.portal : false)} onChange={on => { set('portal', on); quick({ op: 'toggle', on }, on ? 'Портал включён' : 'Портал выключен'); }} />
      </div>
      <div className="dim3" style={{ fontSize: 12 }}>Выключите — гостевая Wi-Fi останется, но без страницы входа. Включите — гости снова начнут со страницы.</div>
    </div> : null}

    {sec('net', 'Сеть и Wi-Fi', f.mainWifi === false ? `«${f.guestSsid}»` : `«${f.mainSsid || '—'}» · «${f.guestSsid}»`, <>
      <div className="row" style={{ gap: 10, alignItems: 'center' }}><Switch on={f.mainWifi !== false} onChange={v => set('mainWifi', v)} />
        <div className="grow"><b style={{ fontSize: 13.5 }}>Основная Wi-Fi роутера</b>
          <div className="dim3" style={{ fontSize: 12 }}>Выключите, если Wi-Fi раздают другие точки (например, Keenetic), а к роутеру приходит только кабель: тогда у роутера будет одна гостевая сеть.</div></div></div>
      <div className="pt-grid">
        {f.mainWifi === false ? null : <Field label="Основная Wi-Fi: название"><input className="input" value={f.mainSsid} placeholder="например, Office" onChange={e => set('mainSsid', e.target.value)} /></Field>}
        {f.mainWifi === false ? null : <Field label="Основная Wi-Fi: пароль"><input className="input" type="password" value={f.mainKey} placeholder={base.mainKeySet ? 'не менять' : 'от 8 символов'} onChange={e => set('mainKey', e.target.value)} /></Field>}
        <Field label="Гостевая Wi-Fi: название"><input className="input" value={f.guestSsid} onChange={e => set('guestSsid', e.target.value)} /></Field>
        <Field label="Гостевая Wi-Fi: пароль (обычно без)"><input className="input" type="password" value={f.guestKey} placeholder={base.guestKeySet ? 'не менять' : 'без пароля — вход через страницу'} onChange={e => set('guestKey', e.target.value)} /></Field>
      </div>
      <div className="row wrap" style={{ gap: 6 }}><span className="dim" style={{ fontSize: 13 }}>Диапазоны:</span>
        {(hw.radios || []).map(r => { const on = (f.bands || []).includes(r.band);
          return <button key={r.band} type="button" className={'chip' + (on ? ' on' : '')} onClick={() => set('bands', on ? f.bands.filter(b => b !== r.band) : [...(f.bands || []), r.band])}>{BAND_TEXT[r.band] || r.band}</button>; })}</div>
      <div className="pt-grid">
        <Field label="Основная сеть (адрес роутера)"><input className="input mono" value={f.lan} onChange={e => set('lan', e.target.value)} /></Field>
        <Field label="Гостевая сеть (адрес роутера)"><input className="input mono" value={f.guest} onChange={e => set('guest', e.target.value)} /></Field>
        <Field label="VLAN гостевой сети (для точек доступа)"><input className="input mono" value={f.vlan} onChange={e => set('vlan', e.target.value)} /></Field>
      </div>
      <div className="dim3" style={{ fontSize: 12 }}>Гостевая сеть /22 — до 1000 гостей. Основная и гостевая не должны пересекаться с сетью, из которой приходит интернет{hw.wanip ? ` (сейчас на WAN ${hw.wanip})` : ''}.</div>
    </>)}

    {sec('ports', 'Порты', (hw.lan || []).map(n => `${n.toUpperCase()}: ${PORT_ROLE_OPTS.find(o => o[0] === portRole(n))[1].toLowerCase()}`).join(' · '), <>
      <div className="pt-ports">
        {hw.wan ? <div className="pt-port wan"><i className={'pt-led' + ((hw.links || {})[hw.wan] || {}).up ? ' on' : ''} /><b>WAN</b><span>интернет</span></div> : null}
        {(hw.lan || []).map(n => { const l = (hw.links || {})[n] || {}, mg = hw.mgmt === n;
          return <div key={n} className={'pt-port r-' + portRole(n)}>
            <i className={'pt-led' + (l.up ? ' on' : '')} /><b>{n.toUpperCase()}</b>
            <select className="select" value={portRole(n)} onChange={e => setF(x => ({ ...x, ports: { ...(x.ports || {}), [n]: e.target.value } }))}>
              {PORT_ROLE_OPTS.map(([v, t]) => <option key={v} value={v} disabled={mg && (v === 'guest' || v === 'off')}>{t}</option>)}</select>
            {mg ? <span className="pt-mg">здесь Rack Live</span> : l.up ? <span>{l.speed ? l.speed + ' Мбит/с' : 'есть линк'}</span> : <span className="dim3">пусто</span>}
          </div>; })}
      </div>
      <div className="dim3" style={{ fontSize: 12, lineHeight: 1.45 }}><b>Основная</b> — компьютеры и принтеры офиса. <b>Гостевая</b> — сразу гостевая сеть со страницей входа (например, телевизор в холле).
        <b> Обе</b> — провод к точке доступа: основная сеть идёт без метки, гостевая с меткой VLAN {f.vlan}. <b>Выключен</b> — порт ничего не отдаёт.</div>
    </>)}

    {sec('login', 'Вход гостей', `${f.login === 'password' ? 'по паролю' : f.login === 'sms' ? 'по СМС' : 'кнопкой'} · ${f.hours} ч${f.down ? ` · ${f.down} Мбит/с` : ''}`, <>
      <div className="row" style={{ gap: 10, alignItems: 'center' }}><Switch on={!!f.portal} onChange={v => set('portal', v)} /><span>Страница входа (captive-портал)</span></div>
      <Seg value={f.login} onChange={v => set('login', v)} options={[{ value: 'click', label: 'Кнопка «Подключиться»' }, { value: 'password', label: 'Общий пароль' }, { value: 'sms', label: 'По СМС' }]} />
      {f.login === 'sms' ? smsBlock() : null}
      <div className="pt-grid">
        {f.login === 'password' ? <Field label="Пароль для входа"><input className="input" value={f.password} placeholder={base.passwordSet ? 'не менять' : 'например, кофе2026'} onChange={e => set('password', e.target.value)} /></Field> : null}
        <Field label="Название на странице"><input className="input" value={f.name} onChange={e => set('name', e.target.value)} /></Field>
        <Field label="Вход действует, часов (гость не вводит заново, даже если долго не пользовался сетью)"><input className="input mono" value={f.hours} onChange={e => set('hours', e.target.value)} /></Field>
        <Field label="Куда отправить гостя после входа" hint="Пусто — туда, куда гость шёл сам (часто это служебная страница проверки интернета телефона, например OpenDNS или Apple).">
          <input className="input mono" value={f.after == null ? 'https://ya.ru' : f.after} placeholder="https://ya.ru" onChange={e => set('after', e.target.value)} /></Field>
        {p.installed ? <div><Btn icon="check" busy={busy === 'login'} disabled={working} onClick={() => quick({ op: 'login', profile: profile() }, 'Сохранено')}>Сохранить вход гостей (без перезапуска сети)</Btn></div> : null}
        <Field label="Скорость гостя: загрузка, Мбит/с (0 — без ограничения)"><input className="input mono" value={f.down} onChange={e => set('down', e.target.value)} /></Field>
        <Field label="Скорость гостя: отдача, Мбит/с"><input className="input mono" value={f.up} onChange={e => set('up', e.target.value)} /></Field>
      </div>
      <Field label="Правила пользования (необязательно — если заполнить, гость ставит галочку «Принимаю»)"><textarea className="input" rows={3} value={f.rules} onChange={e => set('rules', e.target.value)} /></Field>
    </>)}

    {sec('tpl', 'Шаблон страницы', (tpls.find(t => t.id === f.template) || {}).name || 'Стандартный', <>
      {tpls.some(t => !keepTpl(t)) ? <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
        {sel === null ? <Btn icon="trash" disabled={working} onClick={() => setSel([])}>Выбрать для удаления</Btn> : <>
          <b style={{ fontSize: 13 }}>Выбрано: {sel.length} из {tpls.filter(t => !keepTpl(t)).length}</b>
          <Btn disabled={working} onClick={() => setSel(tpls.filter(t => !keepTpl(t)).map(t => t.id))}>Отметить все{p.installed ? ', кроме используемого' : ''}</Btn>
          <Btn disabled={working || !sel.length} onClick={() => setSel([])}>Снять выбор</Btn>
          <Btn kind="danger" icon="trash" busy={busy === 'delmany'} disabled={working || !sel.length} onClick={delMany}>Удалить выбранные ({sel.length})</Btn>
          <Btn disabled={working} onClick={() => setSel(null)}>Готово</Btn></>}
      </div> : null}
      <div className="pt-tpls">{tpls.map(t => <div key={t.id} className={'pt-tpl' + (sel === null && f.template === t.id ? ' on' : '') + (sel && sel.includes(t.id) ? ' on' : '')} style={sel && keepTpl(t) ? { opacity: .5 } : null} onClick={() => sel === null ? set('template', t.id) : togSel(t)}>
        <div className="pt-thumb"><iframe title={t.name} src={`/api/portal/templates/${t.id}/preview`} loading="lazy" tabIndex={-1} /></div>
        <div className="row" style={{ gap: 6, alignItems: 'center' }}>{sel !== null && !keepTpl(t) ? <input type="checkbox" checked={sel.includes(t.id)} onChange={() => togSel(t)} onClick={e => e.stopPropagation()} /> : null}<b className="grow ellipsis">{t.name}</b>
          <a className="icon-link" href={`/api/portal/templates/${t.id}/preview`} target="_blank" rel="noreferrer" title="Открыть" onClick={e => e.stopPropagation()}><Icon name="external" size={14} /></a>
          {!t.builtin ? <button type="button" className="icon-link" title="Удалить" onClick={e => { e.stopPropagation(); delTpl(t); }}><Icon name="trash" size={14} /></button> : null}</div>
        {savedTpl === t.id && p.installed ? <span className="dim3" style={{ fontSize: 11.5 }}>сейчас на роутере</span> : null}
      </div>)}</div>
      <div className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }}>
        <div className="grow" style={{ minWidth: 180 }}><Field label="Свой шаблон: название"><input className="input" value={upName} placeholder="например, Кофейня" onChange={e => setUpName(e.target.value)} /></Field></div>
        <input ref={fileRef} type="file" accept=".zip,application/zip" hidden onChange={e => upload(e.target.files[0])} />
        <Btn icon="upload" busy={busy === 'upload'} disabled={working} onClick={() => fileRef.current.click()}>Загрузить .zip</Btn>
        {p.installed && f.template !== savedTpl ? <Btn kind="primary" icon="check" busy={busy === 'template'} disabled={working} onClick={() => quick({ op: 'template', template: f.template }, 'Шаблон заменён')}>Поставить на роутер</Btn> : null}
      </div>
      <details className="guide"><summary>Как сделать свой шаблон</summary>
        <div style={{ fontSize: 13, lineHeight: 1.55 }}>Архив .zip с файлом <code>index.html</code> (страница входа) и, по желанию, <code>done.html</code> (после входа), <code>style.css</code>, картинками и шрифтами — до 3 МБ. Картинки лучше в <code>png</code>, <code>jpg</code> или <code>svg</code>: роутер (OpenNDS) не отдаёт <code>.webp</code> как картинку, и она не покажется. Если картинок много, можно вшить их прямо в <code>index.html</code> (data:) — страницу любого размера Rack Live разрешит сам.
          В <code>index.html</code> обязательно поставьте метку <code>{'{{form}}'}</code> — на её место Rack Live вставит кнопку «Подключиться» (и поле пароля, и галочку правил, если они включены).
          Другие метки: <code>{'{{name}}'}</code> — название, <code>{'{{hours}}'}</code> — сколько часов действует вход, <code>{'{{error}}'}</code> — сообщение об ошибке, <code>{'{{rules}}'}</code> — правила,
          <code>{'{{assets}}'}</code> — путь к вашим файлам (<code>{'<link rel="stylesheet" href="{{assets}}/style.css">'}</code>), <code>{'{{continue}}'}</code> — куда гость шёл (для кнопки в done.html).
          Классы кнопки и полей: <code>rl-form</code>, <code>rl-btn</code>, <code>rl-field</code>, <code>rl-terms</code>, <code>rl-error</code>, <code>rl-rules</code>, <code>rl-note</code>. При входе по СМС форма сама показывает «Отправляем СМС…» и ставит на форму класс <code>rl-loading</code> — по нему можно нарисовать свою анимацию загрузки (например, <code>.rl-loading .rl-btn::before</code>). Окно входа на iPhone — урезанный браузер: сложный JavaScript там может не работать.</div></details>
    </>)}

    {hw.nopass ? <div className="plugin-result warn"><b>У роутера нет пароля администратора.</b> Задайте его в «Дополнительно» — без пароля в роутер может зайти любой. Rack Live запомнит его сам.</div> : null}
    {sec('adv', 'Дополнительно', [hw.nopass ? (rootPass ? 'пароль роутера задан' : 'нужен пароль роутера') : '', f.mgmtWan ? 'управление со стороны WAN' : ''].filter(Boolean).join(' · '), <>
      <Field label={hw.nopass ? 'Пароль администратора роутера (root) — обязательно' : 'Сменить пароль администратора роутера (необязательно)'}>
        <input className="input" type="password" value={rootPass} placeholder="от 8 символов" onChange={e => setRootPass(e.target.value)} /></Field>
      <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}><Switch on={!!f.mgmtWan} onChange={v => set('mgmtWan', v)} />
        <div className="grow"><div>Управлять роутером со стороны WAN</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Пускает SSH и веб-интерфейс только с частных адресов (10.x, 172.16–31.x, 192.168.x) за WAN-портом. Нужно, если Rack Live стоит в сети, из которой роутер получает интернет
            (например, при настройке на столе). Из интернета так не зайти.</div></div></div>
    </>)}

    <div className="row wrap" style={{ marginTop: 6 }}>
      <Btn kind="primary" icon={p.installed ? 'refresh' : 'wifi'} busy={busy === 'install'} disabled={working || !(p.checks || []).filter(c => !c.optional).every(c => c.ok) || (hw.nopass && rootPass.length < 8)} onClick={apply}>
        {busy === 'install' ? 'Настраиваю…' : p.installed ? 'Применить изменения' : 'Настроить роутер'}</Btn>
      {p.installed ? <Btn kind="danger" icon="trash" busy={busy === 'remove'} disabled={working} onClick={remove}>Удалить портал полностью</Btn> : null}
    </div>
    {stage ? <div className="dim row" style={{ gap: 8, fontSize: 12.5 }}><span className="spin-dot" />{stage}</div> : null}
    {result ? <PluginResult r={result} /> : null}
  </>;
}

/* step by step: before the setup, how to check it, what «Удалить полностью» does */
// Портал уже стоит на роутере, но настроен вручную (нет профиля Rack Live): показываем, что нашли, и ничего не предлагаем перенастраивать.
function ForeignPortal({ p, hw }) {
  const f = p.foreign || {};
  const rows = [['Название', '«' + f.name + '»'], ['Файл страницы входа', f.theme || '—'], ['Сессия гостя', f.hours ? f.hours + ' ч' : '—'],
    ['OpenNDS', (hw.nds ? hw.nds + ' · ' : '') + (hw.ndsRunning ? 'работает' : 'выключен')], ['Гостей сейчас', hw.clients == null ? '—' : hw.clients]];
  return <div className="pt-live">
    <div className="row" style={{ gap: 12, alignItems: 'center' }}><Icon name="wifi" size={18} />
      <div className="grow" style={{ minWidth: 0 }}><b>Captive-портал найден</b><div className="dim3" style={{ fontSize: 12.5 }}>{p.status || ''}</div></div></div>
    <div className="list" style={{ marginTop: 8 }}>{rows.map(([k, v]) => <div className="li" key={k} style={{ fontSize: 13 }}><span className="dim3">{k}</span><span className="grow" /><b>{v}</b></div>)}</div>
    <div className="dim3" style={{ fontSize: 12.5, marginTop: 8, lineHeight: 1.5 }}>Портал настроен вручную, не этим плагином. Rack Live его видит и ничего на нём не меняет.
      Установка плагина здесь отключена: она перенастроила бы сеть, Wi-Fi, DHCP и межсетевой экран роутера и заменила бы ваш портал своим.</div>
  </div>;
}

function PortalGuide({ installed }) {
  return <>
    <details className="guide" open={!installed}><summary>Пошагово: как подготовить и подключить роутер</summary>
      <ol className="steps" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
        <li><b>OpenWrt на роутере.</b> Нужна OpenWrt 23.05 или новее и Wi-Fi. Свежая OpenWrt открывается по адресу <code>192.168.1.1</code>, логин <code>root</code>, пароля нет.</li>
        <li><b>Как подключить, чтобы Rack Live его видел.</b> Проще всего — ноутбук или ReckController кабелем в LAN-порт роутера: роутер сам выдаст ему адрес, Rack Live откроет <code>192.168.1.1</code>.
          Если Rack Live стоит в вашей сети (NAS, сервер), а роутер готовите на столе — сначала в веб-интерфейсе роутера (LuCI):
          <i> Сеть → Интерфейсы → LAN</i>: адрес — свободный в вашей сети (например, <code>192.168.1.70</code>), шлюз и DNS — адрес вашего роутера;
          вкладка «DHCP-сервер» → включите «Игнорировать интерфейс» (иначе роутер начнёт раздавать адреса вашей сети). Сохраните и подключите кабель вашей сети в LAN-порт.</li>
        <li><b>Добавьте роутер в Rack Live:</b> «Устройства» → «Добавить» → OpenWrt, адрес роутера, логин <code>root</code>, пароль (если не задан — оставьте пустым).</li>
        <li><b>Интернет — в WAN.</b> Кабель провайдера (или от другого роутера) — в порт WAN. Если оставить его в LAN-порту, роутер начнёт раздавать адреса чужой сети — Rack Live это проверит и не даст настроить.</li>
        <li><b>Заполните разделы ниже:</b> названия и пароли Wi-Fi, адреса сетей, что отдаёт каждый порт, способ входа гостей, время входа и скорость, шаблон страницы.
          Если у роутера нет пароля администратора — задайте его в «Дополнительно».</li>
        <li><b>«Настроить роутер».</b> Роутер перезапустит сеть, связь пропадёт на 1–2 минуты. Если Rack Live не сможет снова зайти на роутер, через 6 минут роутер сам вернёт прежние настройки.</li>
        <li><b>После настройки</b> Rack Live заходит на роутер по его новому адресу в основной сети (или со стороны WAN, если включено в «Дополнительно») и сам записывает этот адрес в устройство.</li>
      </ol></details>
    {installed ? <details className="guide"><summary>Как проверить, что всё работает</summary>
      <ol className="steps" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
        <li>С телефона подключитесь к <b>гостевой Wi-Fi</b> — должна сама открыться страница входа. Нажмите «Подключиться» — появится «Вы в сети», интернет заработает.</li>
        <li>Подключитесь к <b>основной Wi-Fi</b> с паролем — интернет сразу, без страницы.</li>
        <li>Гость не видит компьютеры основной сети и других гостей — так и задумано.</li>
        <li>Если страница не открылась сама — откройте в браузере любой сайт по <code>http://</code> (например, http://neverssl.com).</li>
      </ol></details> : null}
    {installed ? <details className="guide"><summary>Что делает «Удалить портал полностью»</summary>
      <div style={{ fontSize: 13.5, lineHeight: 1.55 }}>Возвращает настройки, снятые перед первой установкой портала: сеть и адрес роутера, Wi-Fi, DHCP, межсетевой экран.
        Удаляет OpenNDS, тему и шаблон страницы, гостевую сеть и все наши настройки (с приставкой <code>rl_</code>). Пароль администратора остаётся новым — ради безопасности.
        Роутер вернётся на свой прежний адрес в LAN: если Rack Live подключён со стороны WAN, он потеряет роутер — подключитесь к LAN-порту и поправьте адрес устройства.</div></details> : null}
  </>;
}

/* Rack Live is in the network above this router's WAN (a router being prepared on a desk next to the home network):
   1) open management from that side, 2) move the cable from LAN to WAN, 3) find the router by its WAN MAC in the main router's list */
function WanPrep({ p, call, reload }) {
  const toast = useToast(); const { refresh } = useApp();
  const hw = p.hw || {};
  const wanUp = !!((hw.links || {})[hw.wan] || {}).up;
  const [busy, setBusy] = useState(''); const [done, setDone] = useState(false);
  if (wanUp && hw.via === 'wan') return null;                  // already managed through WAN
  const run = async (op, label) => {
    setBusy(op);
    try { const r = await call({ op }); toast(r.message || r.error || label, !r.ok); if (op === 'prepare_wan' && r.ok) setDone(true); if (op === 'locate' && r.ok) { refresh(); reload(); } }
    catch (e) { toast(e.message, true); }
    finally { setBusy(''); }
  };
  return <details className="guide"><summary>Rack Live подключён к роутеру через вашу сеть, а интернет роутеру нужен в WAN</summary>
    <div style={{ fontSize: 13.5, lineHeight: 1.55 }}>Так бывает, когда роутер готовят на столе: Rack Live стоит на NAS или сервере вашей сети, а кабель вашей сети пока в LAN-порту роутера.
      Сразу воткнуть кабель в WAN нельзя — из WAN свежая OpenWrt никого не пускает, и Rack Live потеряет роутер.</div>
    <ol className="steps" style={{ fontSize: 13.5, lineHeight: 1.55 }}>
      <li>Нажмите <b>«Открыть управление со стороны WAN»</b> — Rack Live сам добавит на роутере правило: пускать SSH и веб-интерфейс из частных сетей за WAN-портом (из интернета — нет).
        <details className="guide" style={{ marginTop: 6 }}><summary>Или сделать это вручную в веб-интерфейсе OpenWrt (LuCI)</summary>
          <ol className="steps" style={{ fontSize: 13, lineHeight: 1.55 }}>
            <li>Откройте веб-интерфейс роутера (сейчас он по адресу в вашей сети, например <code>http://192.168.1.70</code>), войдите как <code>root</code>.</li>
            <li><b>Сеть → Межсетевой экран</b> → вкладка <b>«Правила для трафика»</b> → внизу <b>«Добавить»</b>.</li>
            <li><b>Имя</b>: <code>Управление с WAN</code>. <b>Протокол</b>: <code>TCP</code>.</li>
            <li><b>Зона источника</b>: <code>wan</code>. <b>Адрес источника</b>: ваша сеть, например <code>192.168.1.0/24</code> (так никто из интернета не войдёт).</li>
            <li><b>Зона назначения</b>: <code>Устройство (вход)</code> — то есть сам роутер. <b>Порт назначения</b>: <code>22 80 443</code>.</li>
            <li><b>Действие</b>: <code>Принять</code>. «Сохранить», затем вверху <b>«Сохранить и применить»</b>.</li>
            <li>Проверьте, что интерфейс <b>WAN</b> получает адрес автоматически: <b>Сеть → Интерфейсы → WAN</b> → протокол <code>DHCP-клиент</code>.</li>
            <li><b>Сеть → Интерфейсы → LAN</b>: адрес из <b>другой</b> подсети, чем ваша сеть (ваша 192.168.1.x — поставьте <code>192.168.10.1</code>), шлюз и DNS — пусто. «Сохранить и применить» — роутер пропадёт, переткните кабель в WAN.</li>
          </ol>
          <div className="dim3" style={{ fontSize: 12.5 }}>Без этого правила после перестановки кабеля в WAN роутер будет недоступен из вашей сети — тогда зайти на него можно только кабелем в LAN-порт.</div>
        </details></li>
      <li>Заодно Rack Live переведёт LAN роутера в другую подсеть (например <code>192.168.10.1</code>): после перестановки кабеля роутер получит на WAN адрес из вашей сети,
        и LAN не должен с ней совпадать — иначе роутер отвечает не туда и его не видно. Через несколько секунд Rack Live потеряет роутер — так и должно быть.</li>
      <li>Переткните кабель вашей сети <b>из LAN-порта в WAN</b>.</li>
      <li>Через 20–30 секунд нажмите <b>«Найти роутер»</b> — Rack Live найдёт его новый адрес в списке клиентов вашего роутера и запишет сам. Дальше — «Настроить роутер».
        Если правило делали вручную — нажмите «Открыть управление…» всё равно (до перестановки кабеля): Rack Live запомнит MAC порта WAN, по нему и ищет.
        Новый адрес можно посмотреть и самому — в списке клиентов вашего роутера (имя «OpenWrt») — и вписать в «Настроить» → адрес.</li>
    </ol>
    <div className="row wrap" style={{ gap: 8 }}>
      <Btn icon="lock" busy={busy === 'prepare_wan'} disabled={!!busy} onClick={() => run('prepare_wan', 'Готово')}>Открыть управление со стороны WAN</Btn>
      <Btn kind={done ? 'primary' : undefined} icon="search" busy={busy === 'locate'} disabled={!!busy} onClick={() => run('locate', 'Ищу')}>Найти роутер</Btn>
    </div></details>;
}
