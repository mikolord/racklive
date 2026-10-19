/* Settings, events, login and first-run setup */
const RULES = [
  ['offline', 'Устройство пропало', 'нет связи дольше', [['minutes', 'мин']]],
  ['ups', 'ИБП', 'перешёл на батарею, разряжается, просит замену батареи', []],
  ['speed', 'Упала скорость порта', '1 Гбит → 100 Мбит дольше (обычно кабель)', [['minutes', 'мин']]],
  ['loop', 'Петля в сети', 'похоже, кабель замкнул сеть: коммутатор нашёл петлю, штурм широковещательных кадров, «прыгающие» устройства', []],
  ['errors', 'Ошибки на порту', 'повреждённых кадров (CRC) за час больше', [['count', 'шт']]],
  ['security', 'Безопасность', 'появилась критичная проблема: открытый опасный порт, пароль по умолчанию…', []],
  ['newdev', 'Новое устройство в сети', 'подключилось устройство, которого раньше не было', []],
  ['config', 'Изменилась конфигурация', 'роутера или коммутатора (по бэкапам)', []],
  ['inet', 'Медленный интернет', 'два замера подряд ниже, % от тарифа', [['pct', '%']]],
  ['disk', 'Заканчивается место', 'том заполнен на', [['pct', '%']]],
  ['temp', 'Перегрев', 'устройство, °C · диск, °C', [['c', '°C'], ['disk', '°C']]],
  ['vpn', 'VPN не работает', 'маршрутный туннель не поднят дольше', [['minutes', 'мин']]],
  ['cert', 'Сертификат сайта', 'истекает меньше чем через', [['days', 'дн.']]],
  ['cpu', 'Процессор загружен', 'больше чем на … дольше …', [['pct', '%'], ['minutes', 'мин']]],
  ['warning', 'Любое «требует внимания»', 'статус «внимание» дольше', [['minutes', 'мин']]],
];
/* Telegram confirm flow for login (from the login page) and linking (from settings) */
function TgFlow({ kind, onOk, onClose }) {
  const [st, setSt] = useState({ phase: 'start' });           // start | wait | denied | expired | error
  useEffect(() => {
    let alive = true, timer = null;
    api(kind === 'link' ? '/api/tglink/start' : '/api/tgauth/start', { method: 'POST', body: {} }).then(r => {
      if (!alive) return; setSt({ phase: 'wait', url: r.url, code: r.code });
      try { window.open(r.url, '_blank'); } catch (e) { }
      const poll = async () => {
        try {
          const p = await api('/api/tgauth/poll', { method: 'POST', body: { code: r.code } });
          if (!alive) return;
          if (p.status === 'ok') { if (p.token) ssSet('rl_tok', p.token); onOk(p); return; }
          if (p.status === 'denied' || p.status === 'expired') { setSt(s => ({ ...s, phase: p.status })); return; }
          if (p.status === 'asked') setSt(s => ({ ...s, asked: true }));
        } catch (e) { }
        timer = setTimeout(poll, 2000);
      };
      timer = setTimeout(poll, 1500);
    }).catch(e => alive && setSt({ phase: 'error', msg: e.message }));
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  return <div className="tg-flow">
    {st.phase === 'start' ? <div className="dim">Готовлю ссылку…</div> : null}
    {st.phase === 'wait' ? <>
      <div style={{ fontWeight: 650 }}>{kind === 'link' ? 'Откройте бота и нажмите «Start» — аккаунт привяжется сам'
        : st.asked ? 'Бот спросил «Это вы?» — нажмите «Да, войти»' : 'Откройте бота и нажмите «Start», затем подтвердите вход'}</div>
      <a className="btn primary tg-btn" href={st.url} target="_blank" rel="noreferrer"><Icon name="send" size={17} />Открыть Telegram</a>
      <div className="dim3 row" style={{ gap: 8, fontSize: 12.5 }}><span className="spin-dot" />жду подтверждения… ссылка действует 10 минут</div></> : null}
    {st.phase === 'denied' ? <div style={{ color: 'var(--red)' }}>Вход отклонён или аккаунт не привязан — подробности бот написал в Telegram.</div> : null}
    {st.phase === 'expired' ? <div style={{ color: 'var(--red)' }}>Время вышло — попробуйте ещё раз.</div> : null}
    {st.phase === 'error' ? <div style={{ color: 'var(--red)' }}>{st.msg}</div> : null}
    {onClose ? <button type="button" className="btn" onClick={onClose}>Отмена</button> : null}
  </div>;
}

function NotifyCard() {
  const { data, refresh } = useApp(); const toast = useToast();
  const [n, setN] = useState(() => JSON.parse(JSON.stringify(data.notify)));
  const [res, setRes] = useState(null);
  const [linking, setLinking] = useState(false);
  const bot = data.tgBot || {};
  const syncTg = t => setN(x => ({ ...x, telegram: { ...x.telegram, chat: t.chat, allowed: t.allowed, linked: t.linked, enabled: true } }));
  const unlink = async id => { try { const r = await api('/api/tglink/remove', { method: 'POST', body: { id } }); syncTg(r.telegram); toast('Аккаунт отвязан'); refresh(); } catch (e) { toast(e.message, true); } };
  const sendAvatar = async () => { try { await api('/api/tgbot/avatar', { method: 'POST', body: {} }); toast('Картинка отправлена в Telegram — перешлите её @BotFather'); } catch (e) { toast(e.message, true); } };
  const ch = (c, k, v) => setN(x => ({ ...x, [c]: { ...x[c], [k]: v } }));
  const rule = (r, k, v) => setN(x => ({ ...x, rules: { ...x.rules, [r]: { ...x.rules[r], [k]: v } } }));
  const save = async () => { try { const r = await api('/api/notify', { method: 'PUT', body: n });
    toast(r.menu === 'ok' ? (n.telegram.webapp ? 'Сохранено. У бота появилась кнопка «Rack Live»' : 'Сохранено') : r.menu ? 'Сохранено, но кнопка в боте: ' + r.menu : 'Уведомления сохранены', r.menu && r.menu !== 'ok');
    refresh(); } catch (e) { toast(e.message, true); } };
  const test = async () => { setRes(null); try { const r = await api('/api/notify/test', { method: 'POST', body: n }); setRes(r.results); } catch (e) { toast(e.message, true); } };
  const st = data.notifyStatus || {};
  // plain render helpers (not components): a component defined here would remount its inputs on every keystroke
  const chan = (id, title, children) => <div className="notify-ch">
    <div className="row"><Switch on={!!n[id].enabled} onChange={v => ch(id, 'enabled', v)} /><b className="grow">{title}</b>
      {st[id] ? <span className={'badge ' + (st[id].result === 'ok' ? 'online' : 'offline')}>{st[id].result === 'ok' ? 'отправлено ' + fmt.ago(st[id].t, data.now) : 'ошибка'}</span> : null}</div>
    {n[id].enabled ? <div className="col" style={{ gap: 10, marginTop: 10 }}>{children}</div> : null}</div>;
  const inp = (c, k, label, extra = {}) => <Field label={label} hint={extra.hint}>
    <input className="input" type={extra.secret ? 'password' : 'text'} value={n[c][k] || ''} placeholder={extra.secret && n[c][k + 'Set'] ? '•••••••• (не менять)' : extra.ph || ''}
      onChange={e => ch(c, k, e.target.value)} autoComplete="off" /></Field>;
  return <Card title="Уведомления" style={{ gridColumn: '1 / -1' }}>
    <div className="notify-grid">
      <div className="col" style={{ gap: 10 }}>
        <div className="card-title">Куда отправлять</div>
        {chan('telegram', 'Telegram', <>
          <details className="guide"><summary>Как подключить — по шагам</summary><ol>
            <li>В Telegram откройте <b>@BotFather</b> → <code>/newbot</code> → придумайте имя → он пришлёт <b>токен</b> вида <code>123456:ABC…</code>. Вставьте его ниже и нажмите <b>«Сохранить»</b>.</li>
            <li>Нажмите <b>«Привязать Telegram»</b> → откроется ваш бот → <b>Start</b>. Готово: ID впишется сам, уведомления пойдут вам, а на странице входа появится «Войти через Telegram».</li>
            <li>Нажмите <b>«Отправить тест»</b> — в боте должно прийти сообщение.</li>
            <li>Аватарка боту: после привязки бот сам пришлёт картинку (повторно — кнопка <b>«Аватар для бота»</b>). Перешлите её <b>@BotFather</b> после команды <code>/setuserpic</code> и выбора бота.</li>
          </ol></details>
          {inp('telegram', 'token', 'Токен бота', { secret: true, hint: 'От @BotFather' })}
          <div className="tg-linked">
            <div className="row"><b className="grow" style={{ fontSize: 14 }}>Привязанные аккаунты</b>
              {bot.username ? <span className="badge online">бот @{bot.username}</span> : null}</div>
            {(n.telegram.linked || []).map(l => <div className="li" key={l.id}><div className="ico-circle"><Icon name="send" size={16} /></div>
              <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>{l.name || l.id}</b><div className="dim" style={{ fontSize: 12 }}>{l.username ? '@' + l.username + ' · ' : ''}ID {l.id}</div></div>
              <Btn size="sm" onClick={() => unlink(l.id)}>Отвязать</Btn></div>)}
            {linking ? <TgFlow kind="link" onClose={() => setLinking(false)}
              onOk={p => { setLinking(false); syncTg(p.telegram); toast('Telegram привязан: ' + ((p.user && p.user.first_name) || '')); refresh(); }} />
              : !n.telegram.tokenSet ? <div className="dim3" style={{ fontSize: 12.5 }}>Вставьте токен и нажмите «Сохранить» — появится кнопка привязки.</div>
              : bot.error ? <div style={{ color: 'var(--red)', fontSize: 13 }}>Бот: {bot.error}</div>
              : !bot.username ? <div className="dim3" style={{ fontSize: 12.5 }}>Подключаюсь к боту… (до 15 секунд после сохранения)</div>
              : <div className="row wrap"><Btn icon="send" kind="primary" onClick={() => setLinking(true)}>Привязать Telegram</Btn>
                {(n.telegram.linked || []).length ? <Btn icon="send" onClick={sendAvatar} title="Бот пришлёт картинку и инструкцию, как поставить её через @BotFather">Аватар для бота</Btn>
                  : <a className="btn" href="/icon-512.png" download="rack-live-bot.png"><Icon name="download" size={16} />Аватар для бота</a>}</div>}
          </div>
          {inp('telegram', 'chat', 'Chat ID (заполняется привязкой)', { ph: '123456789', hint: 'Можно вручную: ваш ID (бот пришлёт его на /start) или ID группы, начинается с минуса. Несколько — через запятую' })}
          <details className="guide"><summary>Открывать Rack Live прямо в Telegram (мини-приложение)</summary>
            <div>У бота появится кнопка <b>«Rack Live»</b>, а под каждым уведомлением — <b>«Открыть»</b>. Вход — по вашему аккаунту Telegram, без пароля.</div>
            <div style={{ marginTop: 6 }}><b>Нужно одно:</b> адрес Rack Live в интернете по <b>https://</b> (Telegram по-другому не открывает). Как его получить:</div>
            <ul>
              <li><b>Keenetic / Netcraze:</b> веб-интерфейс роутера → «Сетевые правила» → <b>«Доменное имя»</b> (KeenDNS) → «Добавить» веб-приложение → адрес <code>IP-сервера</code> и порт Rack Live (например 8080) → доступ «из интернета». Получите адрес вида <code>https://rack.ваше-имя.keenetic.link</code> — сертификат роутер выдаст сам.</li>
              <li><b>Synology:</b> Панель управления → Портал входа → Дополнительно → <b>Обратный прокси</b>: <code>https://rack.ваш-домен</code> → <code>http://localhost:8080</code>; сертификат — Безопасность → Сертификат → Let's Encrypt. На роутере пробросьте порт 443 на NAS.</li>
              <li><b>Без белого IP:</b> Cloudflare Tunnel или любой другой обратный прокси с HTTPS.</li>
            </ul>
            <div>Вставьте адрес ниже и нажмите «Сохранить». Панель станет видна из интернета, но войти смогут только разрешённые аккаунты Telegram или по паролю; «Просмотр без пароля» в этом случае лучше выключить.</div></details>
          {inp('telegram', 'webapp', 'Адрес Rack Live в интернете (для мини-приложения)', { ph: 'https://rack.ваш-домен', hint: 'Необязательно. Только https://' })}
          {n.telegram.webapp ? inp('telegram', 'allowed', 'Кто может входить из Telegram', { ph: 'пусто = те же ID, что в «Chat ID»', hint: 'ID аккаунтов через запятую' }) : null}
          {inp('telegram', 'api', 'Адрес API (необязательно)', { ph: 'https://api.telegram.org', hint: 'Если api.telegram.org недоступен — адрес прокси/зеркала' })}
        </>)}
        {chan('email', 'Почта', <>
          <div className="row" style={{ alignItems: 'flex-start' }}>{inp('email', 'host', 'SMTP-сервер', { ph: 'smtp.yandex.ru' })}<div style={{ width: 90 }}>{inp('email', 'port', 'Порт', { ph: '587' })}</div></div>
          {inp('email', 'user', 'Логин')}{inp('email', 'password', 'Пароль приложения', { secret: true })}
          {inp('email', 'from', 'От кого', { ph: 'как логин' })}{inp('email', 'to', 'Кому', { ph: 'you@mail.ru, ещё@...' })}
        </>)}
        {chan('webhook', 'Webhook (ntfy, Home Assistant, свой сервис)', <>
          {inp('webhook', 'url', 'Адрес', { ph: 'https://ntfy.sh/моя-тема', hint: 'ntfy — простой текст; остальным уходит JSON {title, text, items}' })}
        </>)}
        <Field label="Ссылка на Rack Live в сообщении (необязательно)"><input className="input" value={n.url || ''} placeholder="http://192.168.1.3:9998" onChange={e => setN(x => ({ ...x, url: e.target.value }))} /></Field>
      </div>
      <div className="col" style={{ gap: 8 }}>
        <div className="card-title">О чём сообщать</div>
        {RULES.map(([id, title, desc, nums]) => { const r = n.rules[id] || {};
          return <div key={id} className="notify-rule"><Switch on={!!r.on} onChange={v => rule(id, 'on', v)} />
            <div className="grow" style={{ minWidth: 0 }}><b style={{ fontSize: 14 }}>{title}</b><div className="dim" style={{ fontSize: 12 }}>{desc}</div></div>
            {nums.map(([k, u]) => <label key={k} className="row" style={{ gap: 4 }}><input className="input" style={{ width: 58, height: 32, padding: '4px 8px' }} value={r[k] ?? ''}
              onChange={e => rule(id, k, +e.target.value || 0)} disabled={!r.on} /><span className="dim3" style={{ fontSize: 12 }}>{u}</span></label>)}</div>; })}
        <div className="dim3" style={{ fontSize: 12, lineHeight: 1.45 }}>Когда проблема уходит, придёт «восстановилось» с длительностью. Несколько событий за раз — одним сообщением.
          Отключить уведомления для отдельного устройства можно в его настройках.</div>
      </div>
    </div>
    <div className="row wrap" style={{ marginTop: 14 }}>
      <Btn onClick={test} icon="bell">Отправить тест</Btn>
      {res ? Object.entries(res).map(([k, v]) => <span key={k} className={'badge ' + (v === 'ok' ? 'online' : 'offline')}>{k}: {v === 'ok' ? 'дошло' : v}</span>) : null}
      <div className="grow" /><Btn kind="primary" onClick={save}>Сохранить</Btn>
    </div>
  </Card>;
}

/* settings sections, like the Settings app: a list on the left (chips on the phone), one section on the right; state = a short live status */
const SET_SECTIONS = [
  { id: 'general', label: 'Основные', icon: 'settings', color: '#8e8e93', desc: 'Название, опрос данных, подсказки, VLAN', state: d => d.settings.title },
  { id: 'look', label: 'Оформление', icon: 'sun', color: '#af52de', desc: 'Стиль интерфейса, цвет акцента, тема', state: () => skinName() },
  { id: 'notify', label: 'Уведомления', icon: 'bell', color: '#ff3b30', need: 'notify', desc: 'Telegram, почта, webhook — и о чём сообщать',
    state: d => { const ch = [['telegram', 'Telegram'], ['email', 'почта'], ['webhook', 'webhook']].filter(([k]) => (d.notify[k] || {}).enabled).map(x => x[1]);
      return ch.length ? ch.join(', ') : 'каналы не настроены'; } },
  { id: 'frank', label: 'Frank', icon: 'eye', color: '#5856d6', need: 'ai', desc: 'Помощник (ИИ): сервис, ключ, лимиты',
    state: d => d.ai.ready ? 'включён · ' + d.ai.title.split(' ')[0] : d.ai.keySet ? 'выключен' : 'не настроен' },
  { id: 'apps', label: 'Приложения', icon: 'phone', color: '#007aff', desc: 'Frank и тест скорости на экран телефона, доменное имя',
    state: d => (d.apps || {}).url ? d.apps.url.replace(/^https:\/\//, '') : 'установка на телефон' },
  { id: 'network', label: 'Сеть', icon: 'globe', color: '#30b0c7', desc: 'Сеть машины, где работает Rack Live: адреса, DHCP или постоянный адрес', state: () => location.hostname },
  { id: 'system', label: 'Система', icon: 'server', color: '#636366', need: 'devMode', desc: 'Режим разработчика: время, обновления, Docker, перезагрузка машины', state: () => 'режим разработчика' },
  { id: 'terminal', label: 'Терминал', icon: 'terminal', color: '#3a3a3c', desc: 'Командная строка машины, где работает Rack Live' , state: () => '' },
  { id: 'access', label: 'Доступ', icon: 'lock', color: '#34c759', desc: 'Пароль, второй фактор, устройства с доступом' },
  { id: 'backup', label: 'Резервная копия', icon: 'download', color: '#ff9500', desc: 'Скачать все настройки или восстановить из файла' },
  { id: 'about', label: 'О программе', icon: 'other', color: '#8e8e93', desc: 'Версия и ссылки', state: d => 'Rack Live ' + d.version },
];

function useMedia(q) {
  const [m, setM] = useState(() => !!(window.matchMedia && matchMedia(q).matches));
  useEffect(() => { if (!window.matchMedia) return; const mq = matchMedia(q), h = () => setM(mq.matches); h(); mq.addEventListener('change', h); return () => mq.removeEventListener('change', h); }, [q]);
  return m;
}

/* the phone list: grouped cells like iOS Settings — a coloured icon, the name, a short status, a chevron */
const IOS_GROUPS = [['general', 'look', 'notify', 'frank', 'apps', 'network', 'system', 'terminal'], ['access', 'backup'], ['about']];
function IosSettingsList({ secs, data, onPick }) {
  return <div className="ios-list">{IOS_GROUPS.map((g, gi) => { const items = g.map(id => secs.find(x => x.id === id)).filter(Boolean); if (!items.length) return null;
    return <div className="ios-group" key={gi}>{items.map(x => <button type="button" key={x.id} className="ios-cell" data-tour={'set-' + x.id} onClick={() => onPick(x.id)}>
      <span className="ios-ico">{document.documentElement.getAttribute('data-skin') === 'net' ? <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={18} color="#fff" stroke={2} /></span>
        : x.id === 'frank' ? <AppIcon app="frank" size={32} radius={8} /> : x.id === 'about' ? <AppIcon size={32} radius={8} /> : <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={18} color="#fff" stroke={2} /></span>}</span>
      <span className="ios-label">{x.label}</span><span className="ios-val">{x.state ? x.state(data) : ''}</span>
      <Icon name="chevron" size={15} color="var(--text3)" stroke={2.4} /></button>)}</div>; })}</div>;
}

function SettingsView() {
  const { data, refresh, logout, startTour } = useApp(); const toast = useToast();
  const [s, setS] = useState({ ...data.settings });
  const [pw, setPw] = useState({ old: '', n1: '', n2: '' });
  const fileRef = useRef(null);
  const set = (k, v) => setS(x => ({ ...x, [k]: v }));
  const save = async () => { try { await api('/api/settings', { method: 'PUT', body: { title: s.title, poll: +s.poll, publicView: s.publicView, showClients: s.showClients, hints: s.hints !== false, vlans: s.vlans } }); toast('Сохранено'); refresh(); } catch (e) { toast(e.message, true); } };
  const [fullBk, setFullBk] = useState(false); const [bkPw, setBkPw] = useState('');
  const downloadFull = async () => {                        // the full backup is a POST with the password typed again; the answer is a file
    try {
      const tok = ssGet('rl_tok');
      const r = await fetch('/api/export', { method: 'POST', credentials: 'same-origin', headers: Object.assign({ 'Content-Type': 'application/json' }, tok ? { 'X-RL-Session': tok } : {}), body: JSON.stringify({ password: bkPw }) });
      if (!r.ok) { let m = 'не получилось'; try { m = (await r.json()).error || m; } catch (e) { } throw new Error(m); }
      const a = document.createElement('a'); a.href = URL.createObjectURL(await r.blob()); a.download = 'racklive-backup-full.json';
      document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
      setBkPw(''); setFullBk(false); toast('Полная копия скачана');
    } catch (e) { toast(e.message, true); }
  };
  const toggleDev = async v => { try { await api('/api/settings', { method: 'PUT', body: { devMode: v } }); toast(v ? 'Режим разработчика включён: появились «Система» и Wi-Fi в «Сеть»' : 'Режим разработчика выключен'); refresh(); } catch (e) { toast(e.message, true); } };
  const [hiddenN, setHiddenN] = useState(() => hiddenHints().length);
  const [vlanOpen, setVlanOpen] = useState(() => lsGet('rl_vlan_open', '') === '1');      // collapsed by default
  const toggleVlan = v => { setVlanOpen(v); lsSet('rl_vlan_open', v ? '1' : ''); };
  const changePw = async () => {
    if (pw.n1 !== pw.n2) return toast('Пароли не совпадают', true);
    try { await api('/api/settings', { method: 'PUT', body: { oldPassword: pw.old, newPassword: pw.n1 } }); toast('Пароль изменён'); setPw({ old: '', n1: '', n2: '' }); } catch (e) { toast(e.message, true); }
  };
  const importFile = async e => {
    const file = e.target.files[0]; if (!file) return; const text = await file.text(); let obj = null;
    try { obj = JSON.parse(text); } catch (_) { const m = text.match(/window\.__SAVED__=(\{[\s\S]*?\});(?=<)/); if (m) obj = JSON.parse(m[1]); }
    if (!obj) return toast('Не удалось прочитать файл', true);
    try { await api('/api/import', { method: 'POST', body: { data: obj } }); toast(obj.version === 2 ? 'Резервная копия восстановлена' : 'Схема шкафа импортирована'); refresh(); } catch (er) { toast(er.message, true); }
    e.target.value = '';
  };
  const vl = s.vlans || [];
  const [sec, setSec] = useState(() => { const q = new URLSearchParams(location.search).get('section'); return SET_SECTIONS.some(x => x.id === q) ? q : lsGet('rl_set_sec', 'general'); });
  // a phone works like iOS Settings: a list of sections, a tap opens one (with «‹ Настройки» to come back); a computer keeps the two columns
  const phone = useMedia('(max-width: 900px)');
  const [open, setOpen] = useState(() => { const q = new URLSearchParams(location.search).get('section'); return SET_SECTIONS.some(x => x.id === q) ? q : null; });
  const pick = id => {
    if (phone) { setOpen(id); try { history.pushState({ rlset: id }, ''); } catch (e) { } window.scrollTo({ top: 0 }); return; }
    setSec(id); lsSet('rl_set_sec', id); window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const back = () => { if (history.state && history.state.rlset) history.back(); else setOpen(null); window.scrollTo({ top: 0 }); };
  useEffect(() => { const h = e => pick(e.detail); window.addEventListener('rl-section', h); return () => window.removeEventListener('rl-section', h); }, [phone]);     // a window elsewhere sends the person to a section
  useEffect(() => { const h = e => setOpen(e.state && e.state.rlset ? e.state.rlset : null); window.addEventListener('popstate', h); return () => window.removeEventListener('popstate', h); }, []);   // the system «back» closes a section
  const secs = SET_SECTIONS.filter(x => !x.need || data[x.need]);
  const cur = secs.find(x => x.id === (phone ? open : sec)) || secs[0];
  const listMode = phone && !open;                          // the list of sections (the cards below are kept, just hidden)
  useEffect(() => {                                         // inside a section the big «Настройки» title and the hint above are not needed (css: html.set-detail)
    document.documentElement.classList.toggle('set-detail', !!(phone && open));
    return () => document.documentElement.classList.remove('set-detail');
  }, [phone, open]);
  useEffect(() => { const el = document.querySelector('.set-item.on'); if (el && innerWidth <= 900) el.scrollIntoView({ inline: 'center', block: 'nearest' }); }, [cur.id]);
  return <div className={'set-layout' + (phone ? ' ios' : '')}>
    {listMode ? <IosSettingsList secs={secs} data={data} onPick={pick} /> : null}
    {!phone ? <nav className="set-nav">{secs.map(x => <button key={x.id} type="button" data-tour={'set-' + x.id} className={'set-item' + (x.id === cur.id ? ' on' : '')} onClick={() => pick(x.id)}>
      {document.documentElement.getAttribute('data-skin') === 'net' ? <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>
        : x.id === 'frank' ? <AppIcon app="frank" size={30} radius={8} /> : x.id === 'about' ? <AppIcon size={30} radius={8} /> : <span className="set-ic" style={{ background: x.color }}><Icon name={x.icon} size={16} color="#fff" stroke={2} /></span>}
      <span className="set-txt"><b>{x.label}</b><small>{x.state ? x.state(data) : x.desc}</small></span>
      <Icon name="chevron" size={14} color="var(--text3)" /></button>)}</nav> : null}
    <div className={'set-body' + (listMode ? ' ios-hidden' : phone ? ' ios-push' : '')} key={phone ? 'p' + cur.id : 'd'}>
    {phone ? <div className="ios-nav"><button type="button" className="ios-back" onClick={back}><Icon name="chevron" size={20} stroke={2.6} style={{ transform: 'rotate(180deg)' }} />Настройки</button><b className="ios-title">{cur.label}</b><span /></div>
      : <div className="set-head"><b>{cur.label}</b><span>{cur.desc}</span></div>}
    {cur.id === 'look' ? <LookCard /> : null}
    {cur.id === 'general' ? <>
    <Card title="Общие">
      <div className="col" style={{ gap: 14 }}>
        <Field label="Название"><input className="input" value={s.title} onChange={e => set('title', e.target.value)} /></Field>
        <Field label="Интервал опроса" hint="Как часто собирать данные с устройств"><select className="select" value={s.poll} onChange={e => set('poll', +e.target.value)}>
          {[15, 30, 60, 120, 300].map(n => <option key={n} value={n}>{n < 60 ? n + ' секунд' : n / 60 + ' мин'}</option>)}</select></Field>
        <div className="row"><Switch on={!!s.publicView} onChange={v => set('publicView', v)} /><div className="grow"><div>Просмотр без пароля</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Схему и статусы видно всем, кто откроет адрес. Управление — только после входа.</div></div></div>
        <div className="row"><Switch on={s.showClients !== false} onChange={v => set('showClients', v)} /><div className="grow"><div>Клиенты на карте</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Показывать телефоны, камеры и другие устройства, а не только оборудование</div></div></div>
        <div className="row"><Switch on={s.hints !== false} onChange={v => set('hints', v)} /><div className="grow"><div>Подсказки</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Короткие пояснения на каждой вкладке и в карточках — для тех, кто открыл Rack Live впервые. Действует для всех, кто открывает панель.</div>
          {hiddenN ? <button type="button" className="linkbtn" onClick={() => { setHiddenHints([]); setHiddenN(0); toast('Скрытые подсказки снова видны'); }}>
            Вернуть скрытые подсказки ({hiddenN}) — в этом браузере</button> : null}</div></div>
        <Btn kind="primary" onClick={save}>Сохранить</Btn>
      </div>
    </Card>
    <Card title="Режим разработчика">
      <div className="row"><Switch on={!!data.devMode} onChange={toggleDev} /><div className="grow"><div>Режим разработчика</div>
        <div className="dim3" style={{ fontSize: 12.5, lineHeight: 1.45 }}>Открывает раздел «Система» (часовой пояс, обновление пакетов и Docker, перезагрузка) и вкладку Wi-Fi в «Сеть»: драйверы, подключение к сети и своя точка доступа с постоянным адресом.
          Всё это меняет настоящую систему машины, где работает Rack Live, — включайте, если он стоит на мини-ПК с Linux (Debian, Ubuntu, Raspberry Pi OS), например как «ReckController OS». Включается сразу, сохранять не нужно.</div></div></div>
    </Card>
    <Card title="Приветственное обучение">
      <div className="row" style={{ gap: 14, alignItems: 'center' }}>
        <div className="tour-card-eye"><FrankHero size={64} still /></div>
        <div className="grow" style={{ minWidth: 0 }}><div className="dim" style={{ fontSize: 13.5, lineHeight: 1.45 }}>Frank проведёт по главному: как добавить устройство, где карта и настройки. Показывается один раз при первом входе — здесь его можно запустить снова, например чтобы показать коллеге.</div>
          <Btn style={{ marginTop: 10 }} icon="play" onClick={startTour}>Показать обучение</Btn></div></div>
    </Card>
    <Card title={<button type="button" className="card-toggle" onClick={() => toggleVlan(!vlanOpen)}>
        <Icon name="chevron" size={15} style={{ transform: vlanOpen ? 'rotate(90deg)' : 'none', transition: 'transform .2s' }} />VLAN · {vl.length}</button>}
      right={vlanOpen ? <Btn size="sm" icon="plus" onClick={() => set('vlans', [...vl, { vid: (vl.length ? Math.max(...vl.map(v => +v.vid)) + 1 : 1), name: '', color: '#8e8e93' }])} /> : null}>
      {!vlanOpen ? <div className="legend" style={{ cursor: 'pointer' }} onClick={() => toggleVlan(true)}>
        {vl.map((v, i) => <span key={i}><i style={{ background: v.color }} />{v.name || 'VLAN ' + v.vid}</span>)}
        {!vl.length ? <span>Названия и цвета VLAN для портов и карты</span> : null}</div> : <>
      <div className="dim" style={{ fontSize: 13, marginBottom: 10 }}>Только подписи и цвета для портов и карты — сами VLAN настраиваются на роутере и коммутаторе</div>
      <div className="col">{vl.map((v, i) => <div className="row" key={i}>
        <input className="input mono" style={{ width: 70 }} value={v.vid} onChange={e => set('vlans', vl.map((x, j) => j === i ? { ...x, vid: +e.target.value || '' } : x))} />
        <input className="input" value={v.name} placeholder="Название" onChange={e => set('vlans', vl.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
        <input type="color" value={v.color} onChange={e => set('vlans', vl.map((x, j) => j === i ? { ...x, color: e.target.value } : x))} style={{ width: 40, height: 38, border: 0, background: 'none', padding: 0 }} />
        <Btn size="sm" icon="trash" onClick={() => set('vlans', vl.filter((_, j) => j !== i))} /></div>)}</div>
      <Btn style={{ marginTop: 12 }} onClick={save}>Сохранить VLAN</Btn></>}
    </Card></> : null}
    {cur.id === 'notify' ? <NotifyCard /> : null}
    {cur.id === 'frank' ? <AiCard /> : null}
    {cur.id === 'apps' ? <AppsCard /> : null}
    {cur.id === 'access' ? <>
    <Card title="Пароль администратора">
      <div className="col" style={{ gap: 12 }}>
        <input className="input" type="password" placeholder="Текущий пароль" value={pw.old} onChange={e => setPw({ ...pw, old: e.target.value })} />
        <input className="input" type="password" placeholder="Новый пароль (от 8 символов)" value={pw.n1} onChange={e => setPw({ ...pw, n1: e.target.value })} />
        <input className="input" type="password" placeholder="Повторите новый пароль" value={pw.n2} onChange={e => setPw({ ...pw, n2: e.target.value })} />
        <Btn onClick={changePw} disabled={!pw.old || pw.n1.length < 8}>Сменить пароль</Btn>
      </div>
    </Card>
    <MfaCard />
    <DevicesCard />
    <SessionPolicyCard />
    <Card title="Сеанс"><div className="dim" style={{ fontSize: 13.5, marginBottom: 12 }}>Выйти из Rack Live в этом браузере. Вход — по паролю (и второму фактору) или через Telegram.</div>
      <Btn icon="logout" onClick={logout}>Выйти</Btn></Card></> : null}
    {cur.id === 'network' ? <NetworkTabs /> : null}
    {cur.id === 'system' ? <DevSystem /> : null}
    {cur.id === 'terminal' ? <TerminalCard /> : null}
    {cur.id === 'backup' ? <Card title="Резервная копия и импорт">
      <div className="col" style={{ gap: 12 }}>
        <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Копия содержит устройства, схему шкафа, карту и настройки. Пароля администратора и второго фактора в ней нет никогда, а пароли устройств и ключи сервисов — только в полной копии.</div>
        <a className="btn" href="/api/export"><Icon name="download" size={17} />Скачать резервную копию</a>
        <div className="row" style={{ alignItems: 'flex-start' }}><Switch on={fullBk} onChange={setFullBk} /><div className="grow"><div>Полная копия — с паролями устройств</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Нужна, чтобы перенести Rack Live на другую машину со всеми доступами. Такой файл — ключи от всех ваших устройств: храните его надёжно.</div></div></div>
        {fullBk ? <div className="row" style={{ gap: 8 }}><input className="input grow" type="password" placeholder="Пароль администратора" value={bkPw} onChange={e => setBkPw(e.target.value)} />
          <Btn kind="primary" icon="download" disabled={!bkPw} onClick={downloadFull}>Скачать полную</Btn></div> : null}
        <Btn icon="upload" onClick={() => fileRef.current.click()}>Восстановить или импортировать…</Btn>
        <div className="dim3" style={{ fontSize: 12.5 }}>Подходит резервная копия Rack Live или файл server-rack.html / JSON из старого «Конструктора шкафа»</div>
        <input ref={fileRef} type="file" accept=".json,.html,application/json,text/html" style={{ display: 'none' }} onChange={importFile} />
      </div>
    </Card> : null}
    {cur.id === 'about' ? <Card title="О программе">
      <div className="row" style={{ gap: 14, marginBottom: 12 }}><AppIcon size={56} radius={13} />
        <div><div style={{ fontSize: 17, fontWeight: 700 }}>Rack Live</div><div className="dim" style={{ fontSize: 13 }}>версия {data.version}</div></div></div>
      <div className="row" style={{ gap: 10, marginBottom: 12 }}><AppIcon app="frank" size={36} radius={9} /><AppIcon app="speed" size={36} radius={9} />
        <span className="dim" style={{ fontSize: 13 }}>Frank и Тест скорости — отдельные приложения, раздел «Приложения»</span></div>
      <KV rows={[['Версия', 'Rack Live ' + data.version], ['Драйверы', data.drivers.length], ['Устройств', data.devices.length]]} />
      <div className="dim3" style={{ fontSize: 12.5, marginTop: 12 }}>Исходный код и инструкции: <a href="https://github.com/mikolord/racklive" target="_blank" rel="noreferrer">github.com/mikolord/racklive</a></div></Card> : null}
    {cur.id === 'about' && data.authed !== false ? <UpdateCard /> : null}
    </div>
  </div>;
}

/* «События → Системные»: the technical journal (page loads and errors of this phone / browser, the welcome tour, server starts) and one button that copies it
   all as plain text — to be sent to whoever helps (the report starts with the version, the time and what this device is) */
function SystemEvents() {
  const { data, admin } = useApp(); const toast = useToast();
  const list = (data.sysEvents || []).slice().reverse();                      // oldest first in the report
  const report = () => {
    const pend = (() => { try { return JSON.parse(localStorage.getItem('rl_diag') || '[]'); } catch (e) { return []; } })();
    const t = x => new Date(x * 1000).toLocaleString('ru-RU');
    const head = [`Rack Live ${data.version} · отчёт ${new Date().toLocaleString('ru-RU')}`,
      `Устройство: ${/iPhone|iPad|iPod/.test(navigator.userAgent) ? 'iPhone/iPad' : 'компьютер/другое'}${navigator.standalone ? ' (приложение «Домой»)' : ''} · экран ${innerWidth}×${innerHeight}`,
      `Адрес: ${location.origin} · оформление: ${lsGet('rl_skin', 'net')} · User-Agent: ${navigator.userAgent}`];
    const body = list.map(e => `${t(e.t)} [${e.name}] ${e.text}`);
    const tail = pend.length ? ['', 'Ещё не отправлено с этого устройства:', ...pend.map(x => `${new Date(x.t).toLocaleTimeString('ru-RU')} ${x.s}`)] : [];
    return [...head, '', `Системные события (${list.length}):`, ...(body.length ? body : ['— пока пусто']), ...tail].join('\n');
  };
  const copy = () => { if (copyText(report())) toast('Скопировано — вставьте в сообщение'); else toast('Не получилось скопировать — выделите текст ниже вручную', true); };
  return <>
    <Card title="Системные события" right={<Btn kind="primary" size="sm" icon="copy" onClick={copy}>Скопировать всё</Btn>}>
      <div className="dim" style={{ fontSize: 13, lineHeight: 1.5 }}>Технический журнал: как ведёт себя страница на этом устройстве (перезагрузки, ошибки, потеря связи), обучение и запуски сервера.
        Если что-то работает не так — нажмите «Скопировать всё» и отправьте текст тому, кто помогает: в нём уже есть версия, время и сведения об устройстве.</div>
    </Card>
    {list.length ? <Card><div className="sys-log mono">{list.slice().reverse().map((e, i) => <div key={i} className="sys-line"><span className="dim3">{fmt.time(e.t)}</span> <b>{e.name}</b> {e.text}</div>)}</div></Card>
      : <div className="empty">Системных событий пока нет — это хорошо.</div>}
  </>;
}

function EventsView() {
  const { data } = useApp(); const [flt, setFlt] = useState(() => new URLSearchParams(location.search).get('sys') === '1' ? 'sys' : '');
  const ev = data.events.filter(e => !flt || e.level === flt);
  const cnt = k => k === '' ? data.events.length : data.events.filter(e => e.level === k).length;
  return <><div style={{ marginBottom: 14 }}><PickMenu value={flt} onChange={setFlt} title="Какие события показать" head="Показать"
    options={[['', 'Все события', cnt('')], ['offline', 'Сбои', cnt('offline')], ['online', 'Восстановления', cnt('online')], ['warning', 'Предупреждения', cnt('warning')], ['info', 'Действия', cnt('info')], ...(data.sysEvents ? [['sys', 'Системные', null]] : [])]} /></div>
    {flt === 'sys' ? <SystemEvents /> : <EventsList events={ev} />}</>;
}

const LOGIN_ALT = { totp: ['Приложение', 'код из приложения', '#0a84ff', 'key'], email: ['Почта', 'код на почту', '#ff9f0a', 'mail'], sms: ['SMS', 'код по SMS', '#30d158', 'sms'] };
function AuthScreen({ setup, title, onDone, note, tgLogin: tgReal, codeLogin: codeReal }) {
  const peek = new URLSearchParams(location.search).get('mfapreview') === 'login';       // ?mfapreview=login — only the looks of the buttons
  const tgLogin = tgReal || (peek ? { bot: 'bot' } : null), codeLogin = (codeReal && codeReal.length ? codeReal : null) || (peek ? ['totp', 'email', 'sms'] : []);
  const [tgMode, setTgMode] = useState(false);
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [t, setT] = useState(title || 'Серверный шкаф');
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false);
  const [remember, setRemember] = useState(true);     // after a right password the second step (rackd/mfa.py); ?mfapreview=1 shows only its looks, with no real ticket
  const [mfa, setMfa] = useState(() => new URLSearchParams(location.search).get('mfapreview') === '1' && !setup
    ? { ticket: 'preview', methods: [{ id: 'totp', label: 'Код из приложения' }, { id: 'telegram', label: 'Подтвердить в Telegram' }, { id: 'email', label: 'Код на почту', hint: 'm***@example.com' }, { id: 'recovery', label: 'Запасной код', hint: 'осталось 8' }] } : null);
  const submit = async e => {
    e.preventDefault(); setErr('');
    if (setup && pw !== pw2) return setErr('Пароли не совпадают');
    setBusy(true);
    try {
      const r = await api(setup ? '/api/setup' : '/api/login', { method: 'POST', body: { password: pw, title: t, remember } });
      if (r && r.mfa) { setMfa(r); setPw(''); } else onDone();
    }
    catch (er) { setErr(er.message); } finally { setBusy(false); }
  };
  const startCode = async m => {                      // a sign-in without the password: the code goes to the mailbox / phone first
    setErr(''); setBusy(true);
    try { const r = await api('/api/login/code/start', { method: 'POST', body: { method: m } }); setMfa({ ticket: r.ticket, primary: true, hint: r.hint, methods: [{ id: m, label: LOGIN_ALT[m][1] }] }); }
    catch (er) { setErr(er.message); } finally { setBusy(false); }
  };
  if (mfa) return <div className="auth"><div className="app-bg" /><div className="card">
    <AppIcon size={64} radius={16} style={{ margin: '0 auto', boxShadow: '0 8px 24px rgba(0,60,200,.3)' }} />
    <h1>{mfa.primary ? 'Вход по коду' : 'Подтвердите вход'}</h1>
    <div className="dim">{mfa.primary ? mfa.hint : 'Пароль верный. Теперь докажите, что это вы.'}</div>
    <MfaStep ticket={mfa.ticket} methods={mfa.methods} onDone={onDone} onBack={() => setMfa(null)} already={!!mfa.primary} hint0={mfa.hint} /></div></div>;
  return <div className="auth"><div className="app-bg" /><form className="card" onSubmit={submit}>
    <AppIcon size={64} radius={16} style={{ margin: '0 auto', boxShadow: '0 8px 24px rgba(0,60,200,.3)' }} />
    <h1>{setup ? T('auth.welcome', 'Добро пожаловать') : (title || T('app.name', 'Rack Live'))}</h1>
    <div className="dim">{setup ? T('auth.setup', 'Задайте название и пароль администратора — с ним можно будет добавлять устройства и управлять ими.') : T('auth.login', 'Войдите, чтобы продолжить')}</div>
    {note ? <div className="badge offline" style={{ whiteSpace: 'normal', lineHeight: 1.4, padding: '8px 12px', borderRadius: 12 }}>{note}</div> : null}
    <div className="col">
      {setup ? <Field label="Название"><input className="input" value={t} onChange={e => setT(e.target.value)} /></Field> : null}
      <Field label="Пароль"><input className="input" type="password" autoFocus value={pw} onChange={e => setPw(e.target.value)} placeholder={setup ? 'Не короче 8 символов' : ''} /></Field>
      {setup ? <Field label="Ещё раз"><input className="input" type="password" value={pw2} onChange={e => setPw2(e.target.value)} /></Field> : null}
      {err ? <div style={{ color: 'var(--red)', fontSize: 14 }}>{err}</div> : null}
      {!setup ? <label className="mfa-remember"><Switch on={remember} onChange={setRemember} />
        <span style={{ fontSize: 13.5, minWidth: 0 }}>Запомнить это устройство<span className="dim3" style={{ display: 'block', fontSize: 12, lineHeight: 1.35 }}>Выключите на чужом компьютере — вход закончится сам.</span></span></label> : null}
      <button className={'btn primary' + (busy ? ' busy' : '')} type="submit" style={{ padding: 13, marginTop: 4 }}>{setup ? T('auth.start', 'Начать') : T('auth.signin', 'Войти')}</button>
      {!setup && (tgLogin || (codeLogin || []).length) ? (tgMode ? <TgFlow kind="login" onOk={() => onDone()} onClose={() => setTgMode(false)} />
        : <><div className="or-line"><span>или войти без пароля</span></div>
          <div className="login-alts">
            {[...(codeLogin || []).filter(m => m === 'totp'), tgLogin ? 'tg' : null, ...(codeLogin || []).filter(m => m !== 'totp')].filter(m => m === 'tg' || LOGIN_ALT[m]).map(m => m === 'tg'
              ? <button type="button" key="tg" className="login-alt" onClick={() => setTgMode(true)}><span className="mi" style={{ background: '#29a9eb' }}><Icon name="send" size={18} color="#fff" stroke={2} /></span>
                <span><b>Telegram</b><small>подтвердить в боте</small></span></button>
              : <button type="button" key={m} className="login-alt" disabled={busy} onClick={() => startCode(m)}>
                <span className="mi" style={{ background: LOGIN_ALT[m][2] }}><Icon name={LOGIN_ALT[m][3]} size={18} color="#fff" stroke={2} /></span>
                <span><b>{LOGIN_ALT[m][0]}</b><small>{LOGIN_ALT[m][1]}</small></span></button>)}
          </div></>) : null}
    </div>
  </form></div>;
}
