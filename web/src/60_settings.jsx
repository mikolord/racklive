/* Settings, events, login and first-run setup */
const RULES = [
  ['offline', 'Устройство пропало', 'нет связи дольше', [['minutes', 'мин']]],
  ['ups', 'ИБП', 'перешёл на батарею, разряжается, просит замену батареи', []],
  ['speed', 'Упала скорость порта', '1 Гбит → 100 Мбит дольше (обычно кабель)', [['minutes', 'мин']]],
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

function SettingsView() {
  const { data, refresh, logout } = useApp(); const toast = useToast();
  const [s, setS] = useState({ ...data.settings });
  const [pw, setPw] = useState({ old: '', n1: '', n2: '' });
  const fileRef = useRef(null);
  const set = (k, v) => setS(x => ({ ...x, [k]: v }));
  const save = async () => { try { await api('/api/settings', { method: 'PUT', body: { title: s.title, poll: +s.poll, publicView: s.publicView, showClients: s.showClients, hints: s.hints !== false, vlans: s.vlans } }); toast('Сохранено'); refresh(); } catch (e) { toast(e.message, true); } };
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
  return <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', alignItems: 'start' }}>
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
    </Card>
    {data.notify ? <NotifyCard /> : null}
    <Card title="Пароль администратора">
      <div className="col" style={{ gap: 12 }}>
        <input className="input" type="password" placeholder="Текущий пароль" value={pw.old} onChange={e => setPw({ ...pw, old: e.target.value })} />
        <input className="input" type="password" placeholder="Новый пароль (от 8 символов)" value={pw.n1} onChange={e => setPw({ ...pw, n1: e.target.value })} />
        <input className="input" type="password" placeholder="Повторите новый пароль" value={pw.n2} onChange={e => setPw({ ...pw, n2: e.target.value })} />
        <Btn onClick={changePw} disabled={!pw.old || pw.n1.length < 8}>Сменить пароль</Btn>
      </div>
    </Card>
    <Card title="Резервная копия и импорт">
      <div className="col" style={{ gap: 12 }}>
        <div className="dim" style={{ fontSize: 13.5 }}>Копия содержит устройства (с паролями), схему шкафа, карту и настройки. Храните её в надёжном месте.</div>
        <a className="btn" href="/api/export"><Icon name="download" size={17} />Скачать резервную копию</a>
        <Btn icon="upload" onClick={() => fileRef.current.click()}>Восстановить или импортировать…</Btn>
        <div className="dim3" style={{ fontSize: 12.5 }}>Подходит резервная копия Rack Live или файл server-rack.html / JSON из старого «Конструктора шкафа»</div>
        <input ref={fileRef} type="file" accept=".json,.html,application/json,text/html" style={{ display: 'none' }} onChange={importFile} />
      </div>
    </Card>
    <Card title="О программе"><KV rows={[['Версия', 'Rack Live ' + data.version], ['Драйверы', data.drivers.length], ['Устройств', data.devices.length]]} />
      <Btn style={{ marginTop: 12 }} icon="logout" onClick={logout}>Выйти</Btn></Card>
  </div>;
}

function EventsView() {
  const { data } = useApp(); const [flt, setFlt] = useState('');
  const ev = data.events.filter(e => !flt || e.level === flt);
  return <><div className="row wrap" style={{ marginBottom: 14 }}>{[['', 'Все'], ['offline', 'Сбои'], ['online', 'Восстановления'], ['warning', 'Предупреждения'], ['info', 'Действия']].map(([k, l]) =>
    <button key={k} className={'chip' + (flt === k ? ' on' : '')} onClick={() => setFlt(k)}>{l}</button>)}</div>
    <EventsList events={ev} /></>;
}

function AuthScreen({ setup, title, onDone, note, tgLogin }) {
  const [tgMode, setTgMode] = useState(false);
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [t, setT] = useState(title || 'Серверный шкаф');
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false);
  const submit = async e => {
    e.preventDefault(); setErr('');
    if (setup && pw !== pw2) return setErr('Пароли не совпадают');
    setBusy(true);
    try { await api(setup ? '/api/setup' : '/api/login', { method: 'POST', body: { password: pw, title: t } }); onDone(); }
    catch (er) { setErr(er.message); } finally { setBusy(false); }
  };
  return <div className="auth"><div className="app-bg" /><form className="card" onSubmit={submit}>
    <div className="brand-logo" style={{ width: 64, height: 64, borderRadius: 18, margin: '0 auto' }}><Icon name="rack" size={34} color="#fff" /></div>
    <h1>{setup ? 'Добро пожаловать' : (title || 'Rack Live')}</h1>
    <div className="dim">{setup ? 'Задайте название и пароль администратора — с ним можно будет добавлять устройства и управлять ими.' : 'Войдите, чтобы продолжить'}</div>
    {note ? <div className="badge offline" style={{ whiteSpace: 'normal', lineHeight: 1.4, padding: '8px 12px', borderRadius: 12 }}>{note}</div> : null}
    <div className="col">
      {setup ? <Field label="Название"><input className="input" value={t} onChange={e => setT(e.target.value)} /></Field> : null}
      <Field label="Пароль"><input className="input" type="password" autoFocus value={pw} onChange={e => setPw(e.target.value)} placeholder={setup ? 'Не короче 8 символов' : ''} /></Field>
      {setup ? <Field label="Ещё раз"><input className="input" type="password" value={pw2} onChange={e => setPw2(e.target.value)} /></Field> : null}
      {err ? <div style={{ color: 'var(--red)', fontSize: 14 }}>{err}</div> : null}
      <button className={'btn primary' + (busy ? ' busy' : '')} type="submit" style={{ padding: 13, marginTop: 4 }}>{setup ? 'Начать' : 'Войти'}</button>
      {!setup && tgLogin ? (tgMode ? <TgFlow kind="login" onOk={() => onDone()} onClose={() => setTgMode(false)} />
        : <><div className="or-line"><span>или</span></div>
          <button type="button" className="btn tg-btn" style={{ padding: 13 }} onClick={() => setTgMode(true)}><Icon name="send" size={17} />Войти через Telegram</button></>) : null}
    </div>
  </form></div>;
}
