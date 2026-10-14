/* Sign-in security: the second step on the login screen, and Настройки → Доступ (methods, devices, how long sessions live) */
const MFA_ICON = { totp: 'key', telegram: 'send', email: 'mail', sms: 'sms', recovery: 'lock' };
const MIN_TEXT = m => (m >= 60 ? `${m / 60} ч` : `${m} мин`);

const MFA_STYLE = { totp: ['Приложение', '#0a84ff'], telegram: ['Telegram', '#29a9eb'], email: ['Почта', '#ff9f0a'], sms: ['SMS', '#30d158'], recovery: ['Запасной код', '#8e8e93'] };

/* six boxes for a code (one invisible input underneath keeps paste, autofill and the phone keyboard working) */
function OtpBoxes({ value, onChange, onFull, length = 6 }) {
  const ref = useRef(null); const digits = (value || '').replace(/\D/g, '').slice(0, length);
  useEffect(() => { ref.current && ref.current.focus(); }, []);
  const set = v => { const d = v.replace(/\D/g, '').slice(0, length); onChange(d); if (d.length === length && onFull) onFull(d); };
  return <div className="otp" onClick={() => ref.current && ref.current.focus()}>
    {Array.from({ length }, (_, i) => <div key={i} className={'otp-box' + (i === digits.length ? ' cur' : '') + (digits[i] ? ' fill' : '')}>{digits[i] || ''}</div>)}
    <input ref={ref} className="otp-in" value={digits} inputMode="numeric" autoComplete="one-time-code" maxLength={length + 4} aria-label="Код" onChange={e => set(e.target.value)} />
  </div>;
}

/* the login screen after a right password: pick how to prove it is you, then the code */
function MfaStep({ ticket, methods, onDone, onBack, already, hint0 }) {
  const first = (methods.find(m => m.id !== 'recovery') || methods[0]).id;       // already: the code was sent when the sign-in began (without a password)
  const [method, setMethod] = useState(first); const [code, setCode] = useState(''); const [remember, setRemember] = useState(true);
  const [err, setErr] = useState(''); const [info, setInfo] = useState(already ? hint0 || '' : ''); const [busy, setBusy] = useState(false); const [wait, setWait] = useState(already ? 20 : 0);
  const sentFor = useRef(already ? first : '');
  const dead = m => /заново|устарел/.test(m || '');
  const send = async (m, again) => {
    setErr(''); setBusy(true);
    try { const r = await api('/api/login/mfa/send', { method: 'POST', body: { ticket, method: m } }); setInfo(r.hint); setWait(30); }
    catch (e) { setErr(e.message); if (dead(e.message)) setTimeout(onBack, 1500); if (again) sentFor.current = ''; }
    finally { setBusy(false); }
  };
  useEffect(() => {                                       // e-mail, SMS and Telegram start on their own when picked
    setCode(''); setErr(''); if (!(already && method === first)) setInfo('');
    if (['email', 'sms', 'telegram'].includes(method) && sentFor.current !== method) { sentFor.current = method; send(method, true); }
  }, [method]);
  useEffect(() => { if (wait <= 0) return; const t = setTimeout(() => setWait(wait - 1), 1000); return () => clearTimeout(t); }, [wait]);
  useEffect(() => {                                       // Telegram: ask the server until «Да» is pressed in the bot
    if (method !== 'telegram') return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api('/api/login/mfa/poll', { method: 'POST', body: { ticket, remember } });
        if (stop) return;
        if (r.status === 'ok') return onDone();
        if (r.status === 'denied') return setErr('Вход отклонён в Telegram. Если это были не вы — смените пароль.');
        if (r.status === 'expired') return setErr('Время вышло — выберите способ ещё раз.');
      } catch (e) { if (!stop) { setErr(e.message); if (dead(e.message)) setTimeout(onBack, 1500); } return; }
      if (!stop) setTimeout(tick, 2000);
    };
    const t = setTimeout(tick, 2500);
    return () => { stop = true; clearTimeout(t); };
  }, [method, remember]);
  const verify = async c => {
    if (!String(c || '').trim() || busy) return; setErr(''); setBusy(true);
    try { await api('/api/login/mfa/verify', { method: 'POST', body: { ticket, method, code: c, remember } }); onDone(); }
    catch (er) { setErr(er.message); setCode(''); if (dead(er.message)) setTimeout(onBack, 1500); } finally { setBusy(false); }
  };
  const submit = e => { e.preventDefault(); verify(code); };
  const numeric = method !== 'recovery' && method !== 'telegram';
  const title = { totp: 'Код из приложения', email: 'Код из письма', sms: 'Код из SMS', recovery: 'Запасной код' }[method];
  const hintOf = { totp: 'Шесть цифр, меняются каждые 30 секунд', recovery: 'Одноразовый код из списка, который вы сохранили. Использованный повторно не сработает.' }[method] || info;
  return <form className="col mfa-step" onSubmit={submit} style={{ gap: 14 }}>
    {methods.length > 1 ? <div className="mfa-tiles">{methods.map(m => { const [short, col] = MFA_STYLE[m.id] || [m.label, '#8e8e93'];
      return <button type="button" key={m.id} className={'mfa-tile' + (m.id === method ? ' on' : '')} onClick={() => setMethod(m.id)}>
        <span className="mi" style={{ background: col }}><Icon name={MFA_ICON[m.id]} size={18} color="#fff" stroke={2} /></span>
        <span style={{ minWidth: 0 }}><b>{short}</b><small className="ellipsis">{m.hint || ''}</small></span></button>; })}</div> : null}
    {method === 'telegram' ? <div className="mfa-wait"><div className="mfa-spin" /><div><b>Откройте Telegram</b><div className="dim" style={{ fontSize: 13 }}>Бот прислал вопрос — нажмите «Да, это я». Страница откроется сама.</div></div></div>
      : <div className="col" style={{ gap: 10, alignItems: 'center' }}>
        <div style={{ fontWeight: 650, fontSize: 15 }}>{title}</div>
        {numeric ? <OtpBoxes key={method} value={code} onChange={setCode} onFull={verify} />
          : <input className="input mono" autoFocus autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value)} placeholder="xxxxx-xxxxx" maxLength={14}
              style={{ fontSize: 20, letterSpacing: 3, textAlign: 'center', width: '100%' }} />}
        {hintOf ? <div className="dim3" style={{ fontSize: 12.5, textAlign: 'center', lineHeight: 1.4 }}>{hintOf}</div> : null}</div>}
    {err ? <div className="mfa-err">{err}</div> : null}
    <label className="mfa-remember"><Switch on={remember} onChange={setRemember} />
      <span style={{ fontSize: 13.5, minWidth: 0 }}>Запомнить это устройство<span className="dim3" style={{ display: 'block', fontSize: 12, lineHeight: 1.35 }}>Не спрашивать код при следующих входах с него. На чужом компьютере — выключите.</span></span></label>
    {method !== 'telegram' ? <button className={'btn primary' + (busy ? ' busy' : '')} type="submit" style={{ padding: 14, fontSize: 16 }} disabled={numeric ? code.replace(/\D/g, '').length < 6 : !code.trim()}>Войти</button> : null}
    <div className="col" style={{ gap: 2, alignItems: 'center' }}>
      {['email', 'sms'].includes(method) ? <button type="button" className="linkbtn" disabled={wait > 0 || busy} onClick={() => send(method, false)}>{wait > 0 ? `Отправить код ещё раз — через ${wait} с` : 'Отправить код ещё раз'}</button> : null}
      <button type="button" className="linkbtn" onClick={onBack}>{already ? '‹ Назад ко входу' : '‹ Назад, ввести пароль заново'}</button></div>
  </form>;
}

/* e-mail is not set up yet: what to fill in, for the common providers, and a jump to the place where it is filled */
function MailNeeded({ onClose }) {
  const go = () => { lsSet('rl_set_sec', 'notify'); window.dispatchEvent(new CustomEvent('rl-section', { detail: 'notify' })); onClose(); };
  const rows = [['Яндекс', 'smtp.yandex.ru', '465', 'Пароль приложения: id.yandex.ru → Безопасность → Пароли приложений. В почте разрешите доступ почтовых программ.'],
    ['Mail.ru', 'smtp.mail.ru', '465', 'Пароль для внешнего приложения: Настройки → Пароли для внешних приложений.'],
    ['Gmail', 'smtp.gmail.com', '587', 'Нужна двухэтапная проверка, затем пароль приложения: myaccount.google.com/apppasswords.']];
  return <Modal title="Сначала подключите почту" onClose={onClose} footer={<><div className="grow" /><Btn onClick={onClose}>Позже</Btn><Btn kind="primary" onClick={go}>Открыть «Уведомления → Почта»</Btn></>}>
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Rack Live отправляет письма через вашу почту (SMTP). Один раз укажите сервер, логин и <b>пароль приложения</b> — не обычный пароль от почты. Это же письмо-канал используют уведомления о сбоях.</div>
    <div className="col" style={{ gap: 8 }}>{rows.map(r => <div className="mfa-row" key={r[0]} style={{ alignItems: 'flex-start' }}>
      <div style={{ minWidth: 0 }}><b>{r[0]}</b> <span className="mono dim" style={{ fontSize: 12.5 }}>{r[1]} · порт {r[2]}</span><div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.4, marginTop: 2 }}>{r[3]}</div></div></div>)}</div>
    <div className="dim3" style={{ fontSize: 12.5 }}>Порт 465 — SSL, 587 — STARTTLS: Rack Live выбирает сам. В поле «Кому» напишите свой адрес, потом вернитесь сюда.</div>
  </Modal>;
}

/* the list of one-time recovery codes: shown once, copy or download */
function RecoveryCodes({ codes, onClose }) {
  const toast = useToast(); const text = codes.map(c => c.slice(0, 5) + '-' + c.slice(5)).join('\n');
  const save = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([`Rack Live — запасные коды входа\nКаждый работает один раз.\n\n${text}\n`], { type: 'text/plain' })); a.download = 'racklive-recovery-codes.txt'; a.click(); };
  return <Modal title="Запасные коды" onClose={onClose} footer={<Btn kind="primary" onClick={onClose}>Я сохранил</Btn>}>
    <div className="warn-box"><Icon name="alert" size={16} /><div>Сохраните их сейчас — <b>больше они не покажутся</b>. Если потеряете телефон, войти можно будет только с таким кодом. Каждый работает один раз.</div></div>
    <div className="rc-grid">{codes.map(c => <code key={c}>{c.slice(0, 5)}-{c.slice(5)}</code>)}</div>
    <div className="row" style={{ gap: 8 }}><Btn icon="copy" onClick={() => { copyText(text) ? toast('Скопировано') : toast('Не получилось скопировать', true); }}>Скопировать</Btn><Btn icon="download" onClick={save}>Скачать файл</Btn></div>
  </Modal>;
}

function PasswordAsk({ title, text, ok, onDone, onClose }) {
  const [pw, setPw] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const go = async e => { e && e.preventDefault(); setBusy(true); setErr(''); try { await onDone(pw); } catch (er) { setErr(er.message); } finally { setBusy(false); } };
  return <Modal title={title} onClose={onClose} footer={<><div className="grow" /><Btn onClick={onClose}>Отмена</Btn><Btn kind="danger" busy={busy} onClick={go}>{ok}</Btn></>}>
    <form onSubmit={go} className="col"><div className="dim" style={{ fontSize: 13.5 }}>{text}</div>
      <input className="input" type="password" autoFocus placeholder="Пароль администратора" value={pw} onChange={e => setPw(e.target.value)} />
      {err ? <div style={{ color: 'var(--red)', fontSize: 13.5 }}>{err}</div> : null}</form></Modal>;
}

/* app with codes: a QR, then one code to prove it works */
function TotpSetup({ onClose, onDone }) {
  const toast = useToast(); const [k, setK] = useState(null); const [code, setCode] = useState(''); const [busy, setBusy] = useState(false);
  useEffect(() => { api('/api/mfa/totp/start', { method: 'POST' }).then(setK).catch(e => { toast(e.message, true); onClose(); }); }, []);
  const go = async e => { e.preventDefault(); setBusy(true); try { const r = await api('/api/mfa/totp/confirm', { method: 'POST', body: { code } }); onDone(r.recovery); } catch (er) { toast(er.message, true); } finally { setBusy(false); } };
  return <Modal title="Приложение с кодами" onClose={onClose}>
    <ol className="steps"><li>Установите на телефон приложение: Google Authenticator, Яндекс Ключ, Microsoft Authenticator, 1Password или Aegis.</li>
      <li>Нажмите в нём «+» и наведите камеру на код ниже. Не получается — введите ключ вручную.</li>
      <li>Введите шесть цифр, которые покажет приложение.</li></ol>
    {k ? <div className="row wrap" style={{ gap: 16, alignItems: 'center', justifyContent: 'center' }}>
      <QrCode text={k.uri} size={190} />
      <div className="col" style={{ gap: 6, minWidth: 0 }}><div className="dim3" style={{ fontSize: 12 }}>Ключ вручную</div>
        <code className="mono" style={{ wordBreak: 'break-all', fontSize: 14 }}>{k.secret.match(/.{1,4}/g).join(' ')}</code>
        <Btn size="sm" icon="copy" onClick={() => copyText(k.secret) && toast('Скопировано')}>Скопировать ключ</Btn></div></div> : <div className="dim">Готовлю код…</div>}
    <form onSubmit={go} className="col" style={{ gap: 12, alignItems: 'center' }}>
      <OtpBoxes value={code} onChange={setCode} />
      <Btn kind="primary" busy={busy} onClick={go} disabled={code.replace(/\D/g, '').length !== 6}>Подтвердить</Btn></form>
  </Modal>;
}

/* e-mail / SMS: type the address or number, get a code there, type it back — so a typo cannot lock you out */
function TargetSetup({ method, routers, onClose, onDone }) {
  const toast = useToast(); const sms = method === 'sms';
  const [target, setTarget] = useState(''); const [dev, setDev] = useState((routers[0] || {}).id || ''); const [sent, setSent] = useState(''); const [code, setCode] = useState(''); const [busy, setBusy] = useState(false);
  const start = async () => { setBusy(true); try { const r = await api('/api/mfa/target/start', { method: 'POST', body: { method, target, device: dev } }); setSent(r.to); } catch (e) { toast(e.message, true); } finally { setBusy(false); } };
  const confirm = async e => { e.preventDefault(); setBusy(true); try { const r = await api('/api/mfa/target/confirm', { method: 'POST', body: { method, code } }); onDone(r.recovery); } catch (er) { toast(er.message, true); } finally { setBusy(false); } };
  return <Modal title={sms ? 'Код по SMS' : 'Код на почту'} onClose={onClose}>
    <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.45 }}>{sms ? 'SMS уйдёт через USB-модем на вашем роутере OpenWrt (тот же, с которого рассылаются коды портала Wi-Fi). Если модем или роутер не работают, этот способ недоступен — держите включённым ещё один.'
      : 'Письмо уйдёт через почту из «Уведомления → Почта». Письма иногда идут с задержкой — держите включённым ещё один способ.'}</div>
    {sms && !routers.length ? <div className="warn-box"><Icon name="alert" size={16} /><div>Нужен роутер OpenWrt с модемом, добавленный в «Устройства».</div></div> : <>
      {sms ? <Field label="Через какой роутер"><select className="select" value={dev} onChange={e => setDev(e.target.value)}>{routers.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field> : null}
      <Field label={sms ? 'Ваш телефон' : 'Ваша почта'}><div className="row" style={{ gap: 8 }}>
        <input className="input grow" value={target} placeholder={sms ? '+79881234567' : 'me@example.com'} inputMode={sms ? 'tel' : 'email'} onChange={e => { setTarget(e.target.value); setSent(''); }} />
        <Btn onClick={start} busy={busy && !sent} disabled={!target.trim()}>{sent ? 'Ещё раз' : 'Отправить код'}</Btn></div></Field>
      {sent ? <form onSubmit={confirm} className="col"><div className="dim" style={{ fontSize: 13 }}>Код отправлен: {sent}</div>
        <div className="col" style={{ gap: 12, alignItems: 'center' }}><OtpBoxes value={code} onChange={setCode} />
          <Btn kind="primary" busy={busy} onClick={confirm} disabled={code.replace(/\D/g, '').length !== 6}>Подтвердить</Btn></div></form> : null}</>}
  </Modal>;
}

function MfaCard() {
  const toast = useToast(); const [s, setS] = useState(null); const [dlg, setDlg] = useState(null); const [codes, setCodes] = useState(null);
  const load = async () => { try { setS(await api('/api/mfa/status', { method: 'POST' })); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); }, [new URLSearchParams(location.search).get('section')]);
  useEffect(() => { const d = new URLSearchParams(location.search).get('mfa'); if (d) setDlg(d); }, []);
  if (!s) return <Card title="Двухфакторная защита"><div className="dim">Загружаю…</div></Card>;
  const done = r => { setDlg(null); if (r) setCodes(r); load(); toast('Способ подключён'); };
  const method = (m, icon, title, text, on, btn) => <div className="mfa-row" key={m}>
    <span className="set-ic" style={{ background: on ? 'var(--green)' : 'var(--text3)', width: 34, height: 34 }}><Icon name={icon} size={17} color="#fff" /></span>
    <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14.5 }}>{title}</b><div className="dim ellipsis" style={{ fontSize: 12.5 }}>{text}</div></div>{btn}</div>;
  const remove = m => setDlg({ remove: m });
  const connected = (m, label, extra) => <Btn size="sm" onClick={() => remove(m)}>{extra || 'Отключить'}</Btn>;
  return <Card title="Двухфакторная защита" right={<span className={'badge ' + (s.enabled ? 'online' : 'warning')}>{s.enabled ? 'Включена' : 'Выключена'}</span>}>
    <Hint id="mfa-what" title="Зачем это нужно">Даже если кто-то узнает пароль, без вашего телефона он не войдёт. Новое устройство после пароля просит ещё код. Устройство, которое вы запомнили, входит без кода — а отключённое снова будет просить код.</Hint>
    <div className="col" style={{ gap: 10 }}>
      {method('totp', 'key', 'Приложение с кодами', s.totp ? 'подключено — Google Authenticator, Яндекс Ключ…' : 'самый надёжный: работает без интернета и SMS', s.totp,
        s.totp ? connected('totp') : <Btn size="sm" kind="primary" onClick={() => setDlg('totp')}>Подключить</Btn>)}
      {method('telegram', 'send', 'Подтверждение в Telegram', s.telegram.on ? 'бот спросит «это вы?» — нажмёте «Да»' : s.telegram.available && s.telegramLinked ? `бот спросит «это вы?» · привязано аккаунтов: ${s.telegramLinked}` : 'сначала привяжите Telegram: Настройки → Уведомления', s.telegram.on,
        s.telegram.on ? connected('telegram') : <Btn size="sm" kind="primary" disabled={!(s.telegram.available && s.telegramLinked)} onClick={async () => { try { const r = await api('/api/mfa/telegram', { method: 'POST', body: { on: true } }); if (r.recovery) setCodes(r.recovery); load(); } catch (e) { toast(e.message, true); } }}>Включить</Btn>)}
      {method('email', 'mail', 'Код на почту', s.email.on ? 'на ' + s.email.to : s.mailReady ? 'письмо с шестью цифрами' : 'сначала настройте почту: Уведомления → Почта', s.email.on,
        s.email.on ? connected('email') : <Btn size="sm" kind="primary" onClick={() => setDlg(s.mailReady ? 'email' : 'mailneed')}>{s.mailReady ? 'Подключить' : 'Как настроить'}</Btn>)}
      {method('sms', 'sms', 'Код по SMS', s.sms.on ? 'на ' + s.sms.phone + ' через модем роутера' : s.routers.length ? 'через USB-модем на роутере OpenWrt' : 'нужен роутер OpenWrt с модемом', s.sms.on,
        s.sms.on ? connected('sms') : <Btn size="sm" kind="primary" disabled={!s.routers.length} onClick={() => setDlg('sms')}>Подключить</Btn>)}
    </div>
    <div className="row between" style={{ marginTop: 14, gap: 10, flexWrap: 'wrap' }}>
      <div style={{ fontSize: 13.5 }}><b>Запасные коды</b><div className="dim" style={{ fontSize: 12.5 }}>{s.recovery ? `осталось ${s.recovery} — на случай потери телефона` : 'появятся при подключении первого способа'}</div></div>
      <Btn size="sm" disabled={!s.recovery} onClick={() => setDlg({ regen: true })}>Выпустить новые</Btn></div>
    {s.email.on || s.sms.on ? <div className="row" style={{ marginTop: 14, gap: 10 }}><Switch on={s.loginByCode} onChange={async v => { try { await api('/api/mfa/loginbycode', { method: 'POST', body: { on: v } }); load(); } catch (e) { toast(e.message, true); } }} />
      <div className="grow"><div>Вход без пароля — по коду на почту или в SMS</div><div className="dim3" style={{ fontSize: 12.5 }}>Кнопки появятся на экране входа рядом с Telegram. Надёжность такого входа равна защите вашей почты и телефона.</div></div></div> : null}
    <div className="row" style={{ marginTop: 14, gap: 10 }}><Switch on={s.enabled} onChange={async v => { if (v) { try { await api('/api/mfa/enable', { method: 'POST', body: { enabled: true } }); load(); } catch (e) { toast(e.message, true); } } else setDlg({ off: true }); }} />
      <div className="grow"><div>Требовать второй фактор при входе</div><div className="dim3" style={{ fontSize: 12.5 }}>Выключить можно только с паролем</div></div></div>
    {dlg === 'mailneed' ? <MailNeeded onClose={() => setDlg(null)} /> : null}
    {dlg === 'totp' ? <TotpSetup onClose={() => setDlg(null)} onDone={done} /> : null}
    {dlg === 'email' || dlg === 'sms' ? <TargetSetup method={dlg} routers={s.routers} onClose={() => setDlg(null)} onDone={done} /> : null}
    {dlg && dlg.remove ? <PasswordAsk title="Отключить способ" text="Введите пароль. Если это последний способ, защита выключится." ok="Отключить" onClose={() => setDlg(null)}
      onDone={async pw => { await api('/api/mfa/remove', { method: 'POST', body: { method: dlg.remove, password: pw } }); setDlg(null); load(); toast('Отключено'); }} /> : null}
    {dlg && dlg.off ? <PasswordAsk title="Выключить защиту" text="Без второго фактора войти можно будет по одному паролю." ok="Выключить" onClose={() => setDlg(null)}
      onDone={async pw => { await api('/api/mfa/enable', { method: 'POST', body: { enabled: false, password: pw } }); setDlg(null); load(); toast('Защита выключена'); }} /> : null}
    {dlg && dlg.regen ? <PasswordAsk title="Новые запасные коды" text="Старые перестанут работать. Введите пароль." ok="Выпустить" onClose={() => setDlg(null)}
      onDone={async pw => { const r = await api('/api/mfa/recovery', { method: 'POST', body: { password: pw } }); setDlg(null); setCodes(r.recovery); load(); }} /> : null}
    {codes ? <RecoveryCodes codes={codes} onClose={() => setCodes(null)} /> : null}
  </Card>;
}

/* who is signed in: this device first; un-remember (asks to sign in again) or disconnect */
function DevicesCard() {
  const { data, logout } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [list, setList] = useState(null);
  const load = async () => { try { setList((await api('/api/sessions/list', { method: 'POST' })).devices); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
  const call = async (path, body, msg) => { try { const r = await api(path, { method: 'POST', body }); if (msg) toast(msg); if (r.self) return logout(); load(); } catch (e) { toast(e.message, true); } };
  const kind = n => (/iPhone|Android|iPad|Telegram/.test(n || '') ? 'phone' : 'laptop');
  const others = (list || []).filter(d => !d.current).length;
  return <Card title={`Устройства с доступом${list ? ' · ' + list.length : ''}`}
    right={others ? <Btn size="sm" icon="logout" onClick={async () => { if (await confirm(`Отключить ${others} ${ruPlural(others, 'устройство', 'устройства', 'устройств')}? Они выйдут из Rack Live и войдут снова только с паролем и вторым фактором.`, { danger: true, ok: 'Выйти везде, кроме этого' })) call('/api/sessions/others', {}, 'Остальные устройства отключены'); }}>Выйти везде, кроме этого</Btn> : null}>
    <Hint id="dev-what" title="Как это работает">Запомненное устройство остаётся в системе и входит без кода. Выключите «Запомнить» — оно будет просить вход заново (сессия коротко живёт). «Отключить» — устройство сразу выходит и вернуться может только с паролем и вторым фактором.</Hint>
    {!list ? <div className="dim">Загружаю…</div> : !list.length ? <div className="dim" style={{ fontSize: 13.5 }}>Пока никого — вход по ссылке для просмотра или через Telegram-приложение не создаёт записей.</div>
      : <div className="list">{list.map(d => <div className="dev-sess" key={d.id}>
        <KindIcon kind={kind(d.name)} size={38} round={11} />
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 6 }}><b className="ellipsis" style={{ fontSize: 14.5 }}>{d.name}</b>{d.current ? <span className="badge info">Это устройство</span> : null}{!d.signedIn ? <span className="badge">не в системе</span> : null}</div>
          <div className="dim3" style={{ fontSize: 12 }}>{d.ip || '—'} · {d.current ? 'сейчас' : 'был ' + fmt.ago(d.last, data.now)}{d.via === 'telegram' ? ' · через Telegram' : ''}</div>
          <div style={{ fontSize: 12, color: d.trusted ? 'var(--green)' : 'var(--orange)' }}>{d.trusted ? 'Запомнено — входит без кода' : 'Просит вход заново'}{d.signedIn && d.endsAt && !d.trusted ? ' · сессия до ' + new Date(d.endsAt * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : ''}</div></div>
        <div className="col" style={{ gap: 6, alignItems: 'flex-end' }}>
          <label className="row" style={{ gap: 6, fontSize: 12.5, cursor: 'pointer' }}>Запомнить<Switch on={d.trusted} onChange={v => call('/api/sessions/trust', { id: d.id, trusted: v }, v ? 'Устройство запомнено' : 'Теперь будет просить вход заново')} /></label>
          <Btn size="sm" icon="trash" onClick={async () => { if (await confirm(d.current ? 'Это устройство, с которого вы сейчас смотрите. Вы выйдете из Rack Live.' : `Отключить «${d.name}»?`, { danger: true, ok: 'Отключить' })) call('/api/sessions/revoke', { id: d.id }, 'Устройство отключено'); }}>Отключить</Btn></div>
      </div>)}</div>}
  </Card>;
}

/* how long sessions live */
function SessionPolicyCard() {
  const toast = useToast(); const [p, setP] = useState(null);
  useEffect(() => { api('/api/mfa/status', { method: 'POST' }).then(r => setP(r.policy)).catch(() => { }); }, []);
  if (!p) return null;
  const set = async (k, v) => { setP(x => ({ ...x, [k]: v })); try { await api('/api/mfa/policy', { method: 'POST', body: { [k]: v } }); } catch (e) { toast(e.message, true); } };
  const opt = (k, vals, fmtv) => <select className="select" value={p[k]} onChange={e => set(k, +e.target.value)}>{[...new Set([...vals, p[k]])].sort((a, b) => a - b).map(v => <option key={v} value={v}>{fmtv(v)}</option>)}</select>;
  return <Card title="Как долго живёт вход">
    <div className="col" style={{ gap: 14 }}>
      <Field label="Устройство не запомнено — выйти, если им не пользуются" hint="Сессия сама продлевается, пока вы работаете. Дольше 12 часов подряд — в любом случае нужно войти заново.">{opt('idleMin', [15, 30, 60, 120, 240, 720], MIN_TEXT)}</Field>
      <Field label="Запомненное устройство остаётся в системе, если им не пользуются" hint="Пользуетесь — не заканчивается.">{opt('sessionDays', [7, 14, 30, 90], d => d + ' дн.')}</Field>
      <Field label="Не спрашивать второй фактор на запомненном устройстве" hint="После этого срока без входа с него — снова код.">{opt('trustDays', [30, 90, 180], d => d + ' дн.')}</Field>
    </div></Card>;
}
