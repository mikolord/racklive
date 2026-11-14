/* «Face ID»: sign-in and «Пароли» with the phone's own Face ID / Touch ID / Windows Hello — keys of entry (WebAuthn passkeys, rackd/passkey.py).
   The face never leaves the phone: it unlocks a key in the phone's secure chip, and that key signs Rack Live's one-time question. */
const pkB64 = buf => { const b = new Uint8Array(buf); let s = ''; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); };
const pkBuf = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; const b = atob(s), u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u.buffer; };
const pkSupported = () => !!(window.PublicKeyCredential && window.isSecureContext && navigator.credentials);
const pkIsIp = () => /^[\d.]+$|^\[?[0-9a-f:]+\]?$/i.test(location.hostname) && location.hostname !== 'localhost';
const pkDeviceName = () => { const u = navigator.userAgent; return /iPhone/.test(u) ? 'iPhone' : /iPad/.test(u) ? 'iPad' : /Android/.test(u) ? 'Android' : /Mac/.test(u) ? 'Mac' : /Windows/.test(u) ? 'Компьютер Windows' : 'Устройство'; };
const pkLabel = () => /iPhone|iPad/.test(navigator.userAgent) ? 'Face ID' : /Mac/.test(navigator.userAgent) ? 'Touch ID' : /Windows/.test(navigator.userAgent) ? 'Windows Hello' : 'отпечаток / лицо';
function pkError(e) {
  if (e && e.name === 'NotAllowedError') return 'Отменено или время вышло';
  if (e && e.name === 'InvalidStateError') return 'Это устройство уже добавлено';
  if (e && e.name === 'SecurityError') return 'Face ID работает только по доменному адресу Rack Live через https';
  return (e && e.message) || 'не получилось';
}

/* Face ID → the signed answer for /api/passkey/login or /api/vault/unlock */
async function passkeyAssert(purpose) {
  const r = await api('/api/passkey/challenge', { method: 'POST', body: { purpose, rpId: location.hostname } });
  const o = r.publicKey;
  const cred = await navigator.credentials.get({ publicKey: { challenge: pkBuf(o.challenge), rpId: o.rpId, userVerification: 'required', timeout: o.timeout,
    allowCredentials: (o.allowCredentials || []).map(c => ({ type: 'public-key', id: pkBuf(c.id) })) } });
  if (!cred) throw new Error('Отменено');
  const a = cred.response;
  return { id: pkB64(cred.rawId), clientDataJSON: pkB64(a.clientDataJSON), authenticatorData: pkB64(a.authenticatorData), signature: pkB64(a.signature),
    userHandle: a.userHandle ? pkB64(a.userHandle) : null };
}

/* the button on the sign-in screen */
function PasskeyLoginBtn({ remember, onDone, onErr }) {
  const [busy, setBusy] = useState(false);
  if (!pkSupported()) return null;
  const go = async () => {
    onErr(''); setBusy(true);
    try { const credential = await passkeyAssert('login'); await api('/api/passkey/login', { method: 'POST', body: { credential, remember } }); onDone(); }
    catch (e) { onErr(pkError(e)); } finally { setBusy(false); }
  };
  return <button type="button" className={'btn primary faceid-btn' + (busy ? ' busy' : '')} disabled={busy} onClick={go}>
    <FaceIdGlyph size={22} />Войти с {pkLabel()}</button>;
}

function FaceIdGlyph({ size = 20, color = 'currentColor' }) {      // the familiar «face in a frame» sign, drawn in lines
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3" />
    <path d="M9 9v1.5M15 9v1.5M12 9v4.2l-1 .8M9.2 16.2c1.6 1.2 4 1.2 5.6 0" /></svg>;
}

/* Settings → «Face ID» */
function FaceIdCard() {
  const { data } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const [s, setS] = useState(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState(pkDeviceName());
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const load = async () => { try { setS(await api('/api/passkey/status', { method: 'POST', body: {} })); } catch (e) { toast(e.message, true); } };
  useEffect(() => { load(); }, []);
  const appUrl = (data.apps || {}).url || '';
  const here = location.hostname;
  if (!s) return <Card title="Face ID"><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю…</div></Card>;
  const can = pkSupported() && !pkIsIp();
  const mine = s.keys.filter(k => k.rpId === here);
  const other = s.keys.filter(k => k.rpId !== here);
  const add = async e => {
    if (e) e.preventDefault();
    setBusy(true);
    try {
      const r = await api('/api/passkey/register/options', { method: 'POST', body: { password: pw, rpId: here } });
      const o = r.publicKey;
      const cred = await navigator.credentials.create({ publicKey: { ...o, challenge: pkBuf(o.challenge), user: { ...o.user, id: pkBuf(o.user.id) },
        excludeCredentials: (o.excludeCredentials || []).map(c => ({ type: 'public-key', id: pkBuf(c.id) })) } });
      if (!cred) throw new Error('Отменено');
      const st = await api('/api/passkey/register', { method: 'POST', body: { name, credential: { id: pkB64(cred.rawId), clientDataJSON: pkB64(cred.response.clientDataJSON),
        attestationObject: pkB64(cred.response.attestationObject) } } });
      setS(st); setAdding(false); setPw('');
      if (!st.login && !st.vault) {                          // the first device: switch both on right away
        const on = await api('/api/passkey/settings', { method: 'PUT', body: { login: true, vault: true } }); setS(on);
        toast('Готово: вход и «Пароли» теперь открываются по ' + pkLabel());
      } else toast('Устройство «' + name + '» добавлено');
    } catch (er) { toast(pkError(er), true); } finally { setBusy(false); }
  };
  const flag = async (k, v) => { try { setS(await api('/api/passkey/settings', { method: 'PUT', body: { [k]: v } })); } catch (e) { toast(e.message, true); } };
  const del = async k => {
    if (!(await confirm(`Убрать «${k.name}» из входа по Face ID? С этого устройства войти по лицу будет нельзя (паролем — можно). Ключ в самом телефоне останется — его можно удалить в «Пароли» iPhone.`, { title: 'Face ID', ok: 'Убрать', danger: true }))) return;
    try { setS(await api(`/api/passkey/key/${k.id}`, { method: 'DELETE' })); toast('Убрано'); } catch (e) { toast(e.message, true); }
  };
  const row = k => <div key={k.id} className="vault-row">
    <span className="faceid-ic"><FaceIdGlyph size={20} color="#fff" /></span>
    <div className="grow vault-main"><div className="vault-name">{k.name}</div>
      <div className="vault-sub">{k.rpId} · добавлено {new Date(k.created * 1000).toLocaleDateString('ru-RU')} · {k.last ? 'входил ' + fmt.ago(k.last, data.now) : 'ещё не входил'}</div></div>
    <Btn size="sm" kind="danger" icon="trash" title="Убрать" onClick={() => del(k)} /></div>;
  return <>
    <Card title="Face ID">
      <div className="col" style={{ gap: 12 }}>
        <div className="row" style={{ gap: 14, alignItems: 'flex-start' }}><span className="faceid-ic big"><FaceIdGlyph size={30} color="#fff" /></span>
          <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Вход в Rack Live и открытие «Паролей» по лицу или отпечатку — через Face ID самого iPhone (на Mac — Touch ID, на Windows — Windows Hello).
            Ничего скачивать не нужно: лицо проверяет телефон, а Rack Live получает только подпись. Фотографией не обмануть.</div></div>
        {!can ? <div className="vault-warn"><Icon name="shield" size={18} /><span>{pkIsIp() ? 'Сейчас Rack Live открыт по IP-адресу — так Face ID не работает (это правило браузеров).' : 'Этот браузер не умеет ключи входа.'}
          {appUrl ? <> Откройте Rack Live по адресу <a href={appUrl + '/?section=faceid#settings'}>{appUrl.replace(/^https:\/\//, '')}</a> и добавьте устройство там.</> : ' Нужен доменный адрес через https: Настройки → Приложения → доменное имя.'}</span></div> : null}
        {s.keys.length ? <>
          <div className="row"><Switch on={s.login} onChange={v => flag('login', v)} /><div className="grow"><div>Вход в Rack Live по Face ID</div>
            <div className="dim3" style={{ fontSize: 12.5 }}>На экране входа появится кнопка «Войти с Face ID». Вход паролем остаётся.</div></div></div>
          <div className="row"><Switch on={s.vault} onChange={v => flag('vault', v)} /><div className="grow"><div>Открывать «Пароли» по Face ID</div>
            <div className="dim3" style={{ fontSize: 12.5 }}>Вместо повторного ввода пароля администратора.</div></div></div></> : null}
      </div>
    </Card>
    <Card title={'Устройства' + (s.keys.length ? ' · ' + s.keys.length : '')} pad={false}>
      {!s.keys.length ? <div className="dim3" style={{ padding: 16, fontSize: 13, lineHeight: 1.5 }}>Пока ни одного. Добавьте это устройство — iPhone спросит Face ID, и всё.</div>
        : <div className="vault-list">{mine.map(row)}{other.length ? <><div className="faceid-sub">Для других адресов Rack Live</div>{other.map(row)}</> : null}</div>}
      {can ? <div style={{ padding: 14 }}>{adding ? <form className="col" style={{ gap: 10 }} onSubmit={add}>
        <Field label="Название устройства"><input className="input" value={name} onChange={e => setName(e.target.value)} maxLength={60} /></Field>
        <Field label="Пароль администратора"><input className="input" type="password" autoComplete="current-password" value={pw} onChange={e => setPw(e.target.value)} autoFocus /></Field>
        <div className="row" style={{ gap: 8 }}><Btn onClick={() => { setAdding(false); setPw(''); }}>Отмена</Btn>
          <Btn kind="primary" type="submit" busy={busy} disabled={!pw || !name.trim() || busy}>Добавить — спросит {pkLabel()}</Btn></div></form>
        : <Btn kind="primary" icon="plus" onClick={() => setAdding(true)}>Добавить это устройство</Btn>}</div> : null}
    </Card>
    <Card title="Несколько лиц">
      <div className="dim" style={{ fontSize: 13, lineHeight: 1.55 }}>
        Каждый человек добавляет своё устройство: открывает Rack Live на своём iPhone (войдя паролем) и жмёт «Добавить это устройство». Устройств может быть сколько угодно, любое можно убрать.
        <br /><br />Второе лицо на <b>одном</b> iPhone добавляется в самом телефоне: Настройки → Face ID и код-пароль → «Настроить альтернативный внешний вид». Тогда Rack Live откроется по любому из двух лиц.
        <br /><br />Ключ сохраняется в Связке ключей iCloud — на iPad и Mac с тем же Apple ID он тоже работает.</div>
    </Card>
  </>;
}
