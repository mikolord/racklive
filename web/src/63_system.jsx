/* Settings → «Сеть» (the network of the machine Rack Live runs on) and «Терминал» (a real shell on that machine).
   Backend: rackd/hostnet.py (/api/network*), rackd/terminal.py (/api/term/*). */
window.__rlScripts = window.__rlScripts || {};
const loadScript = src => (window.__rlScripts[src] = window.__rlScripts[src] || new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = () => no(new Error('не загрузился ' + src)); document.head.appendChild(s); }));
const maskText = m => { try { const p = Number(String(m).split('.').reduce((a, o) => a + (+o).toString(2).replace(/0/g, '').length, 0)); return String(m).includes('.') ? p : m; } catch (e) { return m; } };

function NetworkCard() {
  const { data } = useApp(); const toast = useToast();
  const [r, setR] = useState(null); const [err, setErr] = useState(''); const [edit, setEdit] = useState(null); const [left, setLeft] = useState(0);
  const load = async () => { try { setR(await api('/api/network')); setErr(''); } catch (e) { setErr(e.message); } };
  useEffect(() => { load(); }, []);
  const pend = r && r.pending;
  useEffect(() => { if (!pend) { setLeft(0); return; } const tick = () => setLeft(Math.max(0, Math.round(pend.deadline - Date.now() / 1000))); tick(); const t = setInterval(tick, 1000); return () => clearInterval(t); }, [pend && pend.deadline]);
  useEffect(() => { if (pend && left === 0) { const t = setTimeout(load, 4000); return () => clearTimeout(t); } }, [left, !!pend]);
  const act = async (what, msg) => { try { await api('/api/network/' + what, { method: 'POST', body: {} }); toast(msg); load(); } catch (e) { toast(e.message, true); } };
  if (!r && !err) return <Card title="Сеть"><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Читаю настройки сети…</div></Card>;
  if (err) return <Card title="Сеть"><div className="cam-warn">Не удалось прочитать сеть: {err}<div className="row" style={{ marginTop: 8 }}><Btn size="sm" icon="refresh" onClick={load}>Повторить</Btn></div></div></Card>;
  const h = r.host, p = r.panel; const here = location.hostname;
  const sameNet = h && h.interfaces ? h.interfaces.filter(i => i.ip && i.mask).reduce((m, i) => { const k = i.ip.split('.').slice(0, 3).join('.'); m[k] = (m[k] || 0) + 1; return m; }, {}) : {};
  const multi = Object.entries(sameNet).filter(([, n]) => n > 1);
  return <>
    {pend ? <div className="cam-warn" style={{ marginBottom: 12 }}>
      <b>Сетевое изменение применено, но не подтверждено.</b> Если не нажать «Подтвердить», через <b>{Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}</b> всё вернётся как было.
      {pend.newIp ? <> Откройте Rack Live по новому адресу: <b className="mono">http://{pend.newIp}{location.port ? ':' + location.port : ''}</b> и нажмите «Подтвердить» там.</> : pend.mode === 'dhcp' ? ' Адрес мог измениться — найдите устройство в списке клиентов роутера, откройте Rack Live по нему и подтвердите.' : null}
      <div className="row" style={{ gap: 8, marginTop: 8 }}><Btn kind="primary" onClick={() => act('confirm', 'Подтверждено')}>Подтвердить</Btn><Btn onClick={() => act('revert', 'Возвращаю прежние настройки…')}>Вернуть как было</Btn></div></div> : null}
    <Card title="Где работает Rack Live">
      <div className="kv"><span>Адреса этой машины</span><b className="mono">{(p.ips || []).join(', ') || '—'}</b></div>
      <div className="kv"><span>Вы открыли панель по адресу</span><b className="mono">{here}</b></div>
      <div className="kv"><span>Шлюз по умолчанию</span><b className="mono">{p.gateway || '—'}{p.gatewayIf ? ' (' + p.gatewayIf + ')' : ''}</b></div>
      <div className="kv"><span>DNS</span><b className="mono">{(p.dns || []).join(', ') || '—'}</b></div>
      {h && h.device ? <div className="kv"><span>Эта машина в Rack Live</span><b>{h.device.name}{h.os ? ' · ' + h.os : ''}</b></div> : null}
      <div className="dk-h" style={{ marginTop: 12 }}>Сетевые карты</div>
      <div className="list">{(p.interfaces || []).map(i => <div className="li" key={i.name}><span className={'dot ' + (i.state === 'up' ? 'online' : 'offline')} />
        <div className="grow" style={{ minWidth: 0 }}><b>{i.name}</b> <span className="dim3 mono" style={{ fontSize: 12 }}>{i.mac}</span>
          <div className="dim mono" style={{ fontSize: 12.5 }}>{(i.ips || []).map(x => x.ip + '/' + x.prefix).join(', ') || 'без адреса'}</div></div>
        <span className="dim" style={{ fontSize: 12.5 }}>{i.speed ? fmt.speed(i.speed) : ''}{i.mtu ? ' · MTU ' + i.mtu : ''}</span></div>)}</div>
      {!(p.interfaces || []).length ? <div className="dim" style={{ fontSize: 13 }}>Сетевые карты не определились (панель запущена в «закрытой» сети Docker?).</div> : null}
    </Card>
    <Card title="Настройка адреса">
      {!h.supported && !(h.interfaces || []).length ? <div className="cam-warn">{h.why}</div> : null}
      {(h.interfaces || []).length ? <div className="list">{h.interfaces.map(i => <div className="li" key={i.name}>
        <span className={'badge ' + (i.mode === 'dhcp' ? '' : 'online')}>{i.mode === 'dhcp' ? 'DHCP' : i.mode === 'static' ? 'постоянный' : '?'}</span>
        <div className="grow" style={{ minWidth: 0 }}><b>{i.name}</b>{i.ip === here ? <span className="found-type" style={{ marginLeft: 6 }}>вы подключены сюда</span> : i.panel ? <span className="found-type" style={{ marginLeft: 6, opacity: .7 }}>адрес этой машины</span> : null}
          <div className="dim mono" style={{ fontSize: 12.5 }}>{i.ip ? i.ip + (i.mask ? ' / ' + maskText(i.mask) : '') : '—'}{i.gateway ? ' · шлюз ' + i.gateway : ''}{i.dns ? ' · DNS ' + i.dns : ''}</div></div>
        {h.supported && !pend ? <Btn size="sm" onClick={() => setEdit(i)}>Изменить</Btn> : null}</div>)}</div> : null}
      {h.why && (h.interfaces || []).length ? <div className="dim" style={{ fontSize: 12.5, marginTop: 8, lineHeight: 1.45 }}>{h.why}</div> : null}
      {multi.length ? <div className="cam-warn" style={{ marginTop: 10 }}>Несколько сетевых карт этой машины находятся в одной сети ({multi.map(([k, n]) => k + '.x — ' + n + ' шт.').join('; ')}). Так бывает, но ответы иногда уходят «не тем» путём, а роутер видит одну машину под несколькими адресами. Если это не нужно, оставьте включённой одну карту.</div> : null}
      {h.supported ? <div className="dim3" style={{ fontSize: 12, marginTop: 10, lineHeight: 1.5 }}>Меняется настройка самой машины, где работает Rack Live. Перед изменением Rack Live сохраняет прежние настройки на ней и ставит таймер: не подтвердили за 2,5 минуты — всё вернётся.</div> : null}
    </Card>
    {edit ? <NetworkEdit iface={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); load(); }} /> : null}
  </>;
}

function NetworkEdit({ iface, onClose, onDone }) {
  const toast = useToast();
  const [mode, setMode] = useState(iface.mode === 'dhcp' ? 'dhcp' : 'static');
  const [ip, setIp] = useState(iface.ip || ''); const [mask, setMask] = useState(iface.mask || '255.255.255.0'); const [gw, setGw] = useState(iface.gateway || ''); const [dns, setDns] = useState(iface.dns || '');
  const [word, setWord] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('');
  const changing = mode === 'dhcp' ? iface.mode !== 'dhcp' : (ip !== iface.ip || mask !== iface.mask || gw !== iface.gateway || dns !== iface.dns || iface.mode === 'dhcp');
  const go = async () => {
    setBusy(true); setErr('');
    try { const r = await api('/api/network/apply', { method: 'POST', body: { iface: iface.name, mode, ip, mask, gateway: gw, dns, confirm: word } });
      toast('Применяю… подтвердите за ' + Math.round(r.seconds / 60 * 10) / 10 + ' мин'); onDone(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  return <Modal title={'Сеть · ' + iface.name} onClose={onClose} icon={<Icon name="globe" size={20} color="var(--accent)" />}>
    <div className="cam-warn"><b>Осторожно.</b> Это сеть самой машины, где работает Rack Live{iface.ip === location.hostname ? ' — и именно по этому адресу вы сейчас сюда подключены' : ''}. После изменения адреса панель, NAS и всё, что к нему обращается по старому адресу
      (Home Assistant, Surveillance Station / DS cam, закладки, проброс портов и правила на роутере, домены), перестанет работать, пока вы не обновите адрес. Связь с панелью на время пропадёт.</div>
    <Seg value={mode} onChange={setMode} options={[{ value: 'dhcp', label: 'DHCP (от роутера)' }, { value: 'static', label: 'Постоянный адрес' }]} />
    {mode === 'static' ? <div className="col" style={{ gap: 8 }}>
      <div className="row wrap" style={{ gap: 8 }}>
        <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Адрес</span><input className="input mono" value={ip} onChange={e => setIp(e.target.value)} /></label>
        <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Маска</span><input className="input mono" value={mask} onChange={e => setMask(e.target.value)} /></label></div>
      <div className="row wrap" style={{ gap: 8 }}>
        <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>Шлюз (роутер)</span><input className="input mono" value={gw} onChange={e => setGw(e.target.value)} /></label>
        <label className="col grow" style={{ gap: 3, minWidth: 150 }}><span className="dim3" style={{ fontSize: 11.5 }}>DNS (через пробел)</span><input className="input mono" value={dns} onChange={e => setDns(e.target.value)} /></label></div>
    </div> : <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Машина будет брать адрес у роутера. Чтобы он не менялся, закрепите его за этой машиной в роутере (по MAC-адресу). Новый адрес может отличаться от нынешнего.</div>}
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Как это защищено: перед изменением прежние настройки сохраняются на машине, и запускается таймер на 2,5 минуты. Если вы не нажмёте «Подтвердить» (после смены нужно открыть Rack Live по новому адресу), всё вернётся как было.</div>
    <label className="col" style={{ gap: 3 }}><span className="dim3" style={{ fontSize: 12 }}>Чтобы продолжить, впишите слово <b>ИЗМЕНИТЬ</b></span><input className="input" value={word} onChange={e => setWord(e.target.value)} autoComplete="off" /></label>
    {err ? <div className="cam-err">{err}</div> : null}
    <div className="row" style={{ gap: 8 }}><Btn kind="primary" disabled={busy || !changing || word.trim().toUpperCase() !== 'ИЗМЕНИТЬ'} onClick={go}>{busy ? 'Применяю…' : 'Применить'}</Btn><Btn onClick={onClose}>Отмена</Btn></div>
  </Modal>;
}

/* ───────── terminal ───────── */
const TERM_KEYS = [['Esc', '\x1b'], ['Tab', '\t'], ['Ctrl', 'CTRL'], ['↑', '\x1b[A'], ['↓', '\x1b[B'], ['←', '\x1b[D'], ['→', '\x1b[C'], ['|', '|'], ['/', '/'], ['-', '-'], ['~', '~'], ['Ctrl+C', '\x03'], ['Ctrl+D', '\x04']];
const isPhone = () => /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
/* ssh:// is what Termius registers on a phone. If the page is still in front after a moment, nothing took the link → the terminal here */
function openInTermius(dev, fallback) {
  let left = false; const mark = () => { left = true; };
  document.addEventListener('visibilitychange', mark, { once: true }); window.addEventListener('pagehide', mark, { once: true });
  location.href = `ssh://${encodeURIComponent(dev.user || 'root')}@${dev.host}:${dev.port || 22}`;
  setTimeout(() => { document.removeEventListener('visibilitychange', mark); if (!left && !document.hidden) fallback(); }, 1600);
}
function TerminalCard() {
  const toast = useToast();
  const [info, setInfo] = useState(null); const [err, setErr] = useState(''); const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('term') === '1');
  useEffect(() => { api('/api/term/info').then(setInfo).catch(e => setErr(e.message)); }, []);
  if (err) return <Card title="Терминал"><div className="cam-warn">{err}</div></Card>;
  if (!info) return <Card title="Терминал"><div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Проверяю…</div></Card>;
  return <Card title="Терминал">
    {info.ok ? <>
      <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Настоящая командная строка машины, где работает Rack Live: <b>{info.device.name}</b> ({info.device.user}@{info.device.host}). Вход — тем же SSH-логином, что уже сохранён для этого устройства, новый пароль вводить не нужно.
        Вы получаете те же права, что у этого пользователя — будьте внимательны с командами. Каждое открытие записывается в «События».</div>
      {!open ? <div className="row" style={{ marginTop: 10, gap: 8, flexWrap: 'wrap' }}>
        <Btn kind="primary" icon="terminal" onClick={() => (isPhone() ? openInTermius(info.device, () => setOpen(true)) : setOpen(true))}>{isPhone() ? 'Открыть (Termius или здесь)' : 'Открыть терминал'}</Btn>
        {isPhone() ? <Btn onClick={() => setOpen(true)}>Только здесь</Btn> : <Btn onClick={() => openInTermius(info.device, () => { })}>В Termius / SSH-программе</Btn>}
        {isInstalled() ? <Btn onClick={() => { const u = location.origin + '/terminal'; copyText(u); toast('Ссылка скопирована. Откройте её в Safari / Chrome и добавьте на экран «Домой»: из установленного приложения установить другое нельзя'); }}>Скопировать ссылку для установки</Btn>
          : <a className="btn" href="/terminal" target="_blank" rel="noreferrer">Как приложение (PWA)</a>}
      </div> : <TerminalView onClose={() => setOpen(false)} />}
      {!open ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 8 }}>«Termius / SSH-программа» открывает ссылку ssh://{info.device.user}@{info.device.host}:{info.device.port} в программе, которая её обслуживает (Termius на телефоне и на компьютере, PuTTY и др. при настройке). Пароль она спросит сама: Rack Live не кладёт его в ссылку.
        «Как приложение» открывает отдельный полноэкранный терминал, который можно установить на экран «Домой» и на рабочий стол, как Frank. Установить: Настройки → Приложения.</div> : null}
    </> : <div className="cam-warn">{info.why || 'Терминал здесь недоступен.'}</div>}
  </Card>;
}

/* the installable «Терминал» app (/terminal): the same on a phone and a computer — pick a device, get its shell */
function TerminalApp() {
  const { logout } = useApp();
  const [info, setInfo] = useState(null); const [err, setErr] = useState('');
  const [sel, setSel] = useState(() => lsGet('rl_term_dev', ''));
  const [on, setOn] = useState(false); const [k, setK] = useState(0);
  useEffect(() => { api('/api/term/info').then(r => { setInfo(r); }).catch(e => setErr(e.message)); }, []);
  const devs = info ? info.devices || [] : [];
  const dev = devs.find(d => d.id === sel) || devs[0];
  useEffect(() => { if (dev && !on && lsGet('rl_term_auto', '1') === '1') setOn(true); }, [dev && dev.id]);
  const pick = id => { setSel(id); lsSet('rl_term_dev', id); setOn(true); setK(x => x + 1); };
  return <div className="term-app">
    <div className="term-app-top">
      <AppIcon app="terminal" size={30} radius={8} />
      <b>Терминал</b>
      <div className="grow" />
      {devs.length ? <select className="input" style={{ maxWidth: 240 }} value={dev ? dev.id : ''} onChange={e => pick(e.target.value)}>
        {devs.map(d => <option key={d.id} value={d.id}>{d.name} · {d.user}@{d.host}</option>)}</select> : null}
      {dev ? <Btn size="sm" onClick={() => openInTermius(dev, () => { })}>Termius</Btn> : null}
      <Btn size="sm" onClick={logout}>Выйти</Btn>
    </div>
    <InstallBanner app="terminal" name="Терминал" />
    {err ? <div className="cam-err">{err}</div> : !info ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Проверяю…</div>
      : !info.supported ? <div className="cam-warn">{info.why || 'Терминал на этом сервере недоступен: он работает на Linux, Synology, OpenWrt и Entware (не на Windows и не в демо).'}</div>
      : !dev ? <div className="cam-warn">Нет устройств, к которым можно открыть терминал. Добавьте в Rack Live сервер, NAS Synology, OpenWrt или компьютер Windows с SSH и сохранённым логином.</div>
      : on ? <TerminalView key={dev.id + ':' + k} extra={'&device=' + encodeURIComponent(dev.id)} onClose={() => setOn(false)} />
        : <div className="row" style={{ gap: 8, marginTop: 10 }}><Btn kind="primary" icon="terminal" onClick={() => setOn(true)}>Подключиться к «{dev.name}»</Btn></div>}
  </div>;
}

function TerminalView({ onClose, extra = '', ssh = null, sshCmd = '' }) {            // extra: '&device=<id>&run=agent-setup' — a server added as a device; ssh: {user, host, port} for «Termius»
  const box = useRef(null); const ws = useRef(null); const term = useRef(null); const ctrl = useRef(false);
  const [state, setState] = useState('connecting'); const [ctrlOn, setCtrlOn] = useState(false); const [size, setSize] = useState(() => +lsGet('rl_term_font', 13)); const [again, setAgain] = useState(0); const [msg, setMsg] = useState('');
  useEffect(() => {
    let dead = false, ro = null;
    (async () => {
      try {
        if (!document.getElementById('xterm-css')) { const l = document.createElement('link'); l.id = 'xterm-css'; l.rel = 'stylesheet'; l.href = '/vendor/xterm.css'; document.head.appendChild(l); }
        await loadScript('/vendor/xterm.js'); await loadScript('/vendor/xterm-addon-fit.js');
      } catch (e) { setState('closed'); setMsg(e.message); return; }
      if (dead) return;
      const t = new window.Terminal({ cursorBlink: true, fontSize: size, fontFamily: 'ui-monospace, Menlo, Consolas, monospace', theme: { background: '#0b0f14', foreground: '#d6deeb', cursor: '#7fd1ff' }, scrollback: 5000, convertEol: false });
      const fit = new window.FitAddon.FitAddon(); t.loadAddon(fit); t.open(box.current); try { fit.fit(); } catch (e) { }
      term.current = t;
      const tok = ssGet('rl_tok');
      const sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/term/ws?cols=${t.cols}&rows=${t.rows}${tok ? '&tok=' + encodeURIComponent(tok) : ''}${extra}`);
      sock.binaryType = 'arraybuffer'; ws.current = sock;
      const enc = new TextEncoder();
      sock.onopen = () => { setState('open'); t.focus(); };
      sock.onmessage = e => t.write(new Uint8Array(e.data));
      sock.onclose = () => { setState('closed'); t.write('\r\n\x1b[90m[соединение закрыто]\x1b[0m\r\n'); };
      sock.onerror = () => { setState('closed'); setMsg('не удалось подключиться (нужен вход администратора и SSH к этой машине)'); };
      t.onData(d => { if (sock.readyState !== 1) return; if (ctrl.current && d.length === 1) { d = String.fromCharCode(d.toUpperCase().charCodeAt(0) & 31); ctrl.current = false; setCtrlOn(false); } sock.send(enc.encode(d)); });
      const resize = () => { try { fit.fit(); if (sock.readyState === 1) sock.send(JSON.stringify({ resize: [t.cols, t.rows] })); } catch (e) { } };
      ro = new ResizeObserver(resize); ro.observe(box.current);
    })();
    return () => { dead = true; if (ro) ro.disconnect(); try { ws.current && ws.current.close(); } catch (e) { } try { term.current && term.current.dispose(); } catch (e) { } };
  }, [again]);
  useEffect(() => { if (term.current) { term.current.options.fontSize = size; lsSet('rl_term_font', String(size)); try { window.dispatchEvent(new Event('resize')); } catch (e) { } } }, [size]);
  const send = s => { if (s === 'CTRL') { ctrl.current = !ctrl.current; setCtrlOn(ctrl.current); } else if (ws.current && ws.current.readyState === 1) ws.current.send(new TextEncoder().encode(s)); if (term.current) term.current.focus(); };
  // «select text»: xterm draws on its own and a finger cannot select it, so the screen + scrollback is shown as ordinary text that the system's own selection (handles, menu) works on
  const [pick, setPick] = useState(null);
  const startPick = () => {
    const t = term.current; if (!t) return;
    const b = t.buffer.active; const out = [];
    for (let y = Math.max(0, b.length - 1500); y < b.length; y++) {
      const l = b.getLine(y); if (!l) continue;
      const txt = l.translateToString(true);
      if (l.isWrapped && out.length) out[out.length - 1] += txt; else out.push(txt);
    }
    while (out.length && !out[out.length - 1].trim()) out.pop();
    setPick(out.join('\n'));
  };
  useEffect(() => { if (pick != null) { const el = document.querySelector('.term-pick'); if (el) el.scrollTop = el.scrollHeight; } }, [pick]);
  // «paste»: xterm on a phone has no paste, and on http:// the page may not read the clipboard — then a plain field takes the system paste (long press → «Вставить»)
  const toast = useToast();
  const [paste, setPaste] = useState(null); const [pasteEnter, setPasteEnter] = useState(true);
  const sendText = (s, enter) => { if (!ws.current || ws.current.readyState !== 1) { toast('Терминал не подключён', true); return false; } ws.current.send(new TextEncoder().encode(s.replace(/\r?\n/g, '\r') + (enter ? '\r' : ''))); if (term.current) term.current.focus(); return true; };
  const doPaste = async () => {
    try { if (window.isSecureContext && navigator.clipboard && navigator.clipboard.readText) { const t = await navigator.clipboard.readText(); if (t) { sendText(t, false); return; } } } catch (e) { }
    setPaste('');
  };
  const termius = () => { if (sshCmd) { copyText(sshCmd); toast('Команда скопирована: вставьте её в Termius после входа'); } openInTermius(ssh, () => { }); };
  return <div style={{ marginTop: 10 }}>
    <div className="term-keys top">{TERM_KEYS.map(([l, v]) => <button type="button" key={l} className={'btn sm' + (v === 'CTRL' && ctrlOn ? ' primary' : '')} onClick={() => send(v)}>{l}</button>)}</div>
    <div className="term-bar"><span className={'dot ' + (state === 'open' ? 'online' : state === 'closed' ? 'offline' : '')} /><span className="dim" style={{ fontSize: 12.5 }}>{state === 'open' ? 'подключено' : state === 'closed' ? 'отключено' : 'подключаюсь…'}</span>
      <div className="grow" />
      <Btn size="sm" onClick={() => setSize(s => Math.max(9, s - 1))}>A−</Btn><Btn size="sm" onClick={() => setSize(s => Math.min(24, s + 1))}>A+</Btn>
      <Btn size="sm" kind={pick != null ? 'primary' : undefined} onClick={() => (pick != null ? setPick(null) : startPick())}>{pick != null ? 'Готово' : 'Выделить текст'}</Btn>
      <Btn size="sm" onClick={() => { const t = term.current && term.current.getSelection(); if (t) { copyText(t); } }}>Копировать</Btn>
      <Btn size="sm" kind={paste != null ? 'primary' : undefined} onClick={() => (paste != null ? setPaste(null) : doPaste())}>Вставить</Btn>
      {ssh ? <Btn size="sm" onClick={termius}>Termius</Btn> : null}
      {state === 'closed' ? <Btn size="sm" kind="primary" icon="refresh" onClick={() => { setState('connecting'); setMsg(''); setAgain(a => a + 1); }}>Заново</Btn> : null}
      <Btn size="sm" onClick={onClose}>Закрыть</Btn></div>
    {paste != null ? <div className="term-paste">
      <textarea className="input mono" rows={3} autoFocus value={paste} onChange={e => setPaste(e.target.value)} placeholder="Нажмите и удерживайте здесь → «Вставить» (или наберите текст)" autoCapitalize="off" autoCorrect="off" spellCheck={false} />
      <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
        <label className="row" style={{ gap: 6, fontSize: 13 }}><input type="checkbox" checked={pasteEnter} onChange={e => setPasteEnter(e.target.checked)} />и нажать Enter</label>
        <div className="grow" />
        <Btn size="sm" onClick={() => setPaste(null)}>Отмена</Btn>
        <Btn size="sm" kind="primary" disabled={!paste} onClick={() => { if (sendText(paste, pasteEnter)) setPaste(null); }}>Отправить в терминал</Btn></div>
    </div> : null}
    <div className="term-wrap">
      <div className="term-box" ref={box} />
      {pick != null ? <div className="term-pick-wrap">
        <pre className="term-pick mono" style={{ fontSize: size }}>{pick || '(пусто)'}</pre>
        <div className="term-pick-bar"><span className="dim3" style={{ fontSize: 12 }}>Выделите пальцем или мышью нужные строки · это обычный текст</span><div className="grow" />
          <Btn size="sm" onClick={() => { copyText(pick); }}>Копировать всё</Btn><Btn size="sm" kind="primary" onClick={() => setPick(null)}>Готово</Btn></div>
      </div> : null}
    </div>
    {msg ? <div className="cam-err" style={{ marginTop: 8 }}>{msg}</div> : null}
  </div>;
}
