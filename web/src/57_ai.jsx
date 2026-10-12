/* AI assistant: chat panel (questions about the network, the model reads live data through read-only tools) + settings card */
const AI_SUGGEST = ['Всё ли в порядке с сетью?', 'Почему может тормозить интернет?', 'Что исправить в безопасности в первую очередь?',
  'Какие устройства чаще всего пропадают?', 'У кого из клиентов слабый Wi-Fi?'];

/* Frank's avatar: an eye that blinks and glances around. While he works the mood shows how hard the question is:
   1 — calm (blue, looks around), 2 — straining (yellow, squints), 3 — heavy (red, frowns, glows and trembles). */
const EYE = 'M3 20C8 11 14 7.5 20 7.5S32 11 37 20C32 29 26 32.5 20 32.5S8 29 3 20Z';
function FrankEye({ size = 34, busy, mood, round }) {
  const id = React.useId().replace(/:/g, '');
  const m = mood != null ? mood : busy ? 1 : 0;
  return <div className={'frank m' + m + (m ? ' busy' : '')} style={{ width: size, height: size, borderRadius: round != null ? round : size * .32 }}>
    <svg viewBox="0 0 40 40" width={size * .8} height={size * .8}>
      <defs>
        <clipPath id={'fe' + id}><path d={EYE} /></clipPath>
        <radialGradient id={'fi' + id} cx=".4" cy=".35" r=".7"><stop className="s0" offset="0" /><stop className="s1" offset=".55" /><stop className="s2" offset="1" /></radialGradient>
      </defs>
      <g className="frank-body">
        <g className="frank-eye">
          <path d={EYE} fill="#f4f6ff" />
          <g clipPath={`url(#fe${id})`}>
            <g className="frank-iris">
              <circle cx="20" cy="20" r="8.6" fill={`url(#fi${id})`} />
              <g className="frank-pupil"><circle cx="20" cy="20" r="3.8" fill="#081020" /><circle cx="22.6" cy="17.4" r="1.6" fill="#fff" /></g>
            </g>
            <g className="frank-lid"><path d="M-2 -8H42V17L-2 10Z" fill="#2c2e3c" /><path d="M-2 10L42 17" stroke="#081020" strokeWidth="1.6" /></g>
          </g>
          <path d={EYE} fill="none" stroke="#081020" strokeOpacity=".35" strokeWidth="1.2" />
        </g>
        <path className="frank-brow" d="M7 3.5Q20 4.5 33 10" fill="none" strokeWidth="3.2" strokeLinecap="round" />
      </g>
    </svg></div>;
}
/* how hard the current question is, from what Frank has done so far */
const frankMood = busy => {
  if (!busy) return 0;
  const n = new Set(busy.tools || []).size, s = (Date.now() - (busy.t0 || Date.now())) / 1000;
  return n >= 5 || s > 30 ? 3 : n >= 2 || s > 10 ? 2 : 1;
};

/* tiny Markdown → React (no innerHTML): **bold**, `code`, lists, headings, code blocks */
function aiInline(s, key) {
  const out = []; const re = /(\*\*[^*]+\*\*|`[^`]+`)/g; let last = 0, m, i = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    out.push(m[0][0] === '`' ? <code key={key + '-' + i++}>{m[0].slice(1, -1)}</code> : <b key={key + '-' + i++}>{m[0].slice(2, -2)}</b>);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}
function AiText({ text }) {
  const blocks = []; const lines = String(text || '').replace(/\r/g, '').split('\n'); let list = null, code = null;
  const flush = () => { if (list) { blocks.push(list.ordered ? <ol key={blocks.length}>{list.items}</ol> : <ul key={blocks.length}>{list.items}</ul>); list = null; } };
  lines.forEach((l, n) => {
    if (l.trim().startsWith('```')) { if (code) { blocks.push(<pre key={blocks.length}>{code.join('\n')}</pre>); code = null; } else { flush(); code = []; } return; }
    if (code) { code.push(l); return; }
    const li = l.match(/^\s*(?:([-*•])|(\d+)[.)])\s+(.*)$/);
    if (li) { const ordered = !!li[2]; if (!list || list.ordered !== ordered) { flush(); list = { ordered, items: [] }; }
      list.items.push(<li key={n}>{aiInline(li[3], n)}</li>); return; }
    flush();
    const h = l.match(/^#{1,4}\s+(.*)$/);
    if (h) blocks.push(<div key={n} className="ai-h">{aiInline(h[1], n)}</div>);
    else if (l.trim()) blocks.push(<p key={n}>{aiInline(l, n)}</p>);
  });
  if (code) blocks.push(<pre key={blocks.length}>{code.join('\n')}</pre>);
  flush();
  return <div className="ai-text">{blocks}</div>;
}

/* an action Frank proposed: runs only when the admin presses «Выполнить» */
function ProposalCard({ p, onAct }) {
  const [busy, setBusy] = useState(false);
  const go = async run => { setBusy(true); try { await onAct(p, run); } finally { setBusy(false); } };
  const st = busy && p.status === 'pending' ? 'running' : p.status;
  return <div className={'ai-prop ' + st}>
    <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
      <div className="ai-prop-ic"><Icon name={st === 'done' ? 'check' : st === 'error' ? 'alert' : st === 'cancelled' ? 'x' : 'bolt'} size={16} /></div>
      <div className="grow" style={{ minWidth: 0 }}>
        <b>{p.label}</b><div className="dim3" style={{ fontSize: 12 }}>{p.deviceName}</div>
        {p.text && st === 'pending' ? <div className="ai-prop-text">{p.text}</div> : null}
        {p.reason && st === 'pending' ? <div className="dim" style={{ fontSize: 12.5, marginTop: 4 }}>Зачем: {p.reason}</div> : null}
        {st === 'done' || st === 'error' ? <div className="ai-prop-text">{st === 'done' ? '✓ ' : ''}{p.result}</div> : null}
        {st === 'cancelled' ? <div className="dim3" style={{ fontSize: 12.5, marginTop: 4 }}>Не выполнялось</div> : null}
      </div>
    </div>
    {st === 'pending' || st === 'running' ? <div className="row" style={{ gap: 8, marginTop: 10 }}>
      <button type="button" className="btn primary sm" disabled={st === 'running'} onClick={() => go(true)}>{st === 'running' ? <><span className="spin-dot" />Выполняю…</> : 'Выполнить'}</button>
      <button type="button" className="btn sm" disabled={st === 'running'} onClick={() => go(false)}>Не надо</button>
    </div> : null}
  </div>;
}

/* menu behind the eye in the Frank app: balance, model, how deep to think */
const EFFORTS = [['', 'Обычно'], ['low', 'Быстро'], ['high', 'Вдумчиво'], ['max', 'Максимум']];
const money = b => b ? (b.currency === 'USD' ? '$' + b.amount.toFixed(2) : b.amount.toFixed(2) + ' ' + b.currency) : null;
function FrankMenu({ onClose }) {
  const { refresh } = useApp(); const toast = useToast();
  const [m, setM] = useState(null); const [err, setErr] = useState(null); const [saving, setSaving] = useState(null);
  const load = () => api('/api/ai/models', { method: 'POST', body: {} }).then(setM).catch(e => setErr(e.message));
  useEffect(() => { load(); const h = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, []);
  const save = async (part, what) => {
    setSaving(what);
    try { await api('/api/ai', { method: 'PUT', body: part }); setM(x => ({ ...x, ...part })); refresh(); }
    catch (e) { toast(e.message, true); } finally { setSaving(null); }
  };
  const cur = m && (m.models.find(x => x.id === m.model) || {});
  const t = (m && m.today) || {}, mo = (m && m.month) || {};
  return <div className="fr-menu-wrap" onMouseDown={e => e.target === e.currentTarget && onClose()}>
    <div className="fr-menu">
      {!m ? <div className="dim row" style={{ gap: 8, padding: 8 }}>{err || <><span className="spin-dot" />Спрашиваю у {'сервиса'}…</>}</div> : <>
        <div className="fr-bal">
          {m.balance ? <><b>{money(m.balance)}</b><span>на балансе {m.title.split(' ')[0]}</span></>
            : <><b>{t.q || 0}</b><span>{ruPlural(t.q || 0, 'вопрос', 'вопроса', 'вопросов')} сегодня · {m.title.split(' ')[0]} не сообщает баланс</span></>}
          <div className="dim3" style={{ fontSize: 12, marginTop: 4 }}>Сегодня {t.q || 0} · за месяц {mo.q || 0} {ruPlural(mo.q || 0, 'вопрос', 'вопроса', 'вопросов')}, ≈{Math.round(((mo.in || 0) + (mo.out || 0)) / 1000)}k токенов</div>
        </div>
        <div className="fr-menu-title">Модель</div>
        <div className="fr-models">{m.models.map(x => <button key={x.id} type="button" className={'fr-model-opt' + (x.id === m.model ? ' on' : '')}
          onClick={() => x.id !== m.model && save({ model: x.id, effort: '' }, x.id)}>
          <span className="fr-radio">{saving === x.id ? <span className="spin-dot" /> : x.id === m.model ? <Icon name="check" size={14} stroke={2.6} /> : null}</span>
          <span className="grow" style={{ minWidth: 0 }}><b>{x.name}</b>{x.desc ? <small>{x.desc}</small> : <small className="mono">{x.id}</small>}</span>
        </button>)}</div>
        {cur && cur.efforts && cur.efforts.length ? <>
          <div className="fr-menu-title">Как глубоко думать</div>
          <Seg value={m.effort || ''} onChange={v => save({ effort: v }, 'effort')} options={EFFORTS.filter(([v]) => !v || cur.efforts.includes(v)).map(([value, label]) => ({ value, label }))} />
          <div className="dim3" style={{ fontSize: 12, lineHeight: 1.4 }}>Глубже — точнее на сложных вопросах, но дольше и дороже. «Обычно» — как задумал сервис.</div>
        </> : null}
      </>}
    </div>
  </div>;
}

const SPEECH = window.isSecureContext ? (window.SpeechRecognition || window.webkitSpeechRecognition || null) : null;
const CUR_KEY = 'rl_ai_cur';                                   // the open conversation, per browser
const dayLabel = t => { const d = new Date(t * 1000), now = new Date(), y = new Date(now - 864e5);
  const hm = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return 'сегодня, ' + hm;
  if (d.toDateString() === y.toDateString()) return 'вчера, ' + hm;
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' }) + ', ' + hm; };

function AiPanel({ initial, onClose, standalone }) {
  const { data, setTab } = useApp(); const toast = useToast(); const confirm = useConfirm();
  const ai = data.ai || {};
  const [view, setView] = useState('chat');                 // 'chat' | 'list'
  const [cid, setCid] = useState(() => initial ? null : lsGet(CUR_KEY, '') || null);
  const [msgs, setMsgs] = useState([]);
  const [chats, setChats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(null);                   // {stage, tools} while Frank works on this chat
  const alive = useRef(true), listRef = useRef(null), asked = useRef(false), cur = useRef(cid), polling = useRef(null);
  cur.current = cid;
  useEffect(() => () => { alive.current = false; }, []);
  useEffect(() => { lsSet(CUR_KEY, cid || ''); }, [cid]);
  useEffect(() => { const el = listRef.current; if (el && view === 'chat') el.scrollTop = el.scrollHeight; }, [msgs, busy, view]);
  useEffect(() => { if (!onClose) return; const h = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, [onClose]);

  // follow a running answer; when done, reload the chat (the server already saved the answer)
  const follow = async (job, chatId) => {
    if (polling.current === job) return; polling.current = job;
    let j = {};
    try {
      while (alive.current && !j.done) {
        await new Promise(res => setTimeout(res, 1200));
        j = await api('/api/ai/job', { method: 'POST', body: { job } });
        if (alive.current && cur.current === chatId) setBusy(b => ({ t0: (b && b.t0) || j.t * 1000 || Date.now(), stage: j.stage, tools: j.tools || [] }));
      }
    } catch (e) { }
    if (polling.current === job) polling.current = null;
    if (alive.current && cur.current === chatId) { setBusy(null); open(chatId, true); }
  };
  const open = async (id, quiet) => {
    setView('chat'); setCid(id); if (!quiet) { setBusy(null); setLoading(true); }
    if (!id) { setMsgs([]); setLoading(false); return; }
    try {
      const c = await api('/api/ai/chats/' + id);
      if (!alive.current || cur.current !== id) return;
      setMsgs(c.messages);
      if (c.job) { setBusy(b => b || { stage: 'Думаю…', tools: [], t0: Date.now() }); follow(c.job, id); }
    } catch (e) { if (e.status === 404) { setCid(null); setMsgs([]); } else toast(e.message, true); }
    finally { if (alive.current) setLoading(false); }
  };
  const loadList = async () => { try { const r = await api('/api/ai/chats'); alive.current && setChats(r.chats); } catch (e) { toast(e.message, true); } };
  const send = async text => {
    text = (text || '').trim(); if (!text || busy || !ai.ready) return;
    const id = cur.current;
    setMsgs(m => [...m, { role: 'user', text, t: Date.now() / 1000 }]); setQ(''); setBusy({ stage: 'Думаю…', tools: [], t0: Date.now() });
    try {
      const r = await api('/api/ai/ask', { method: 'POST', body: { chat: id, text } });
      if (!alive.current) return;
      if (cur.current === id) { cur.current = r.chat; setCid(r.chat); }
      follow(r.job, r.chat);
    } catch (e) { setBusy(null); setMsgs(m => [...m, { role: 'assistant', text: e.message, err: true }]); }
  };
  useEffect(() => {
    if (initial && ai.ready && !asked.current) { asked.current = true; send(initial); }
    else if (cid && ai.ready) open(cid);
  }, []);
  const del = async c => {
    if (!(await confirm(`Удалить разговор «${c.title}»? Восстановить его будет нельзя.`, { title: 'Удалить разговор', ok: 'Удалить', danger: true }))) return;
    try { await api('/api/ai/chats/' + c.id, { method: 'DELETE' }); setChats(x => x.filter(y => y.id !== c.id)); if (c.id === cid) { setCid(null); setMsgs([]); setBusy(null); } }
    catch (e) { toast(e.message, true); }
  };
  const key = e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(q); } };
  const today = ai.today || {};
  const title = view === 'list' ? 'Разговоры' : 'Frank';
  // voice input: the browser's own speech recognition (Safari/Chrome; needs https — on a plain http address the button is hidden)
  const [quick, setQuick] = useState(false);
  const [menu, setMenu] = useState(() => !!standalone && new URLSearchParams(location.search).get('menu') === '1');
  const act = async (p, run) => {
    try { const r = await api('/api/ai/act', { method: 'POST', body: { chat: cid, proposal: p.id, run } }); if (r.chat) setMsgs(r.chat.messages);
      if (run) toast(r.proposal.status === 'done' ? '✓ ' + r.proposal.result : r.proposal.result, r.proposal.status !== 'done'); }
    catch (e) { toast(e.message, true); open(cid, true); }
  };
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const toggleMic = () => {
    if (listening && recRef.current) { recRef.current.stop(); return; }
    try {
      const r = new SPEECH(); const base = q.trim();
      r.lang = 'ru-RU'; r.interimResults = true; r.continuous = false;
      r.onresult = e => { let t = ''; for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript; setQ((base ? base + ' ' : '') + t); };
      r.onend = () => setListening(false);
      r.onerror = e => { setListening(false); if (e.error === 'not-allowed' || e.error === 'service-not-allowed') toast('Нет доступа к микрофону — разрешите его в настройках браузера', true); };
      r.start(); recRef.current = r; setListening(true); setQuick(false);
    } catch (e) { setListening(false); toast('Голосовой ввод недоступен: ' + e.message, true); }
  };
  useEffect(() => () => { try { recRef.current && recRef.current.abort(); } catch (e) { } }, []);
  const toggleList = () => { if (view === 'list') setView('chat'); else { setView('list'); setChats(null); loadList(); } };
  const sub = ai.ready ? `${ai.title} · ${ai.effModel}` : 'не настроен';
  return <div className={standalone ? 'frank-app' : 'overlay ai-overlay'} onMouseDown={e => onClose && e.target === e.currentTarget && onClose()}>
    <div className={'ai-panel' + (standalone ? ' standalone' : '')}>
      {standalone ? <div className="fr-blur" /> : null}
      {standalone ? <div className="fr-top">
        <div className="fr-side">{ai.ready ? <button type="button" className="fr-circle" title={view === 'list' ? 'К разговору' : 'Все разговоры'} onClick={toggleList}>
          <Icon name={view === 'list' ? 'chevronLeft' : 'menu'} size={22} stroke={2} /></button> : null}</div>
        <div className="fr-title"><b>{title}</b><span>{sub}</span></div>
        <div className="fr-side r">
          <button type="button" className="fr-circle eye" title={busy ? busy.stage : 'Модель и баланс'} onClick={() => ai.ready && setMenu(true)}><FrankEye size={46} mood={frankMood(busy)} round={23} /></button>
          {ai.ready ? <button type="button" className="fr-circle" title="Новый разговор" onClick={() => open(null)}><Icon name="plus" size={22} stroke={2} /></button> : null}
        </div>
      </div> : <div className="ai-head">
        <FrankEye size={36} mood={frankMood(busy)} />
        <div className="grow" style={{ minWidth: 0 }}><b>{title}</b>
          <div className="dim3 ellipsis" style={{ fontSize: 12 }}>{ai.ready ? `${ai.title} · ${ai.effModel}${today.q ? ` · сегодня ${today.q} ${ruPlural(today.q, 'вопрос', 'вопроса', 'вопросов')}` : ''}` : 'не настроен'}</div></div>
        {ai.ready ? <>
          <Btn size="sm" icon="list" title="Все разговоры" onClick={() => { if (view === 'list') setView('chat'); else { setView('list'); setChats(null); loadList(); } }} />
          <Btn size="sm" icon="plus" title="Новый разговор" onClick={() => open(null)} />
        </> : null}
        <Btn size="sm" icon="x" onClick={onClose} />
      </div>}
      {view === 'list' ? <div className="ai-list">
        {chats == null ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю…</div>
          : !chats.length ? <div className="ai-empty"><FrankEye size={56} /><div className="dim">Разговоров пока нет — задайте Frank первый вопрос.</div>
            <Btn kind="primary" icon="plus" onClick={() => open(null)}>Новый разговор</Btn></div>
          : <div className="list">{chats.map(c => <div key={c.id} role="button" tabIndex={0} className={'li ai-chat-item' + (c.id === cid ? ' on' : '')} onClick={() => open(c.id)}>
            <div className="grow" style={{ minWidth: 0 }}><b className="ellipsis" style={{ display: 'block', fontSize: 14 }}>{c.title}</b>
              <div className="dim3" style={{ fontSize: 12 }}>{dayLabel(c.updated)} · {c.count} {ruPlural(c.count, 'сообщение', 'сообщения', 'сообщений')}{c.busy ? ' · Frank отвечает…' : ''}</div></div>
            <button type="button" className="btn sm icon" title="Удалить разговор" onClick={e => { e.stopPropagation(); del(c); }}><Icon name="trash" size={15} /></button>
          </div>)}</div>}
        {chats && chats.length ? <div className="dim3" style={{ fontSize: 12, textAlign: 'center', marginTop: 8 }}>Разговоры хранятся в Rack Live, пока вы их не удалите — видны с любого устройства.</div> : null}
      </div> : <div className="ai-list" ref={listRef}>
        {standalone ? <InstallBanner app="frank" name="Frank" /> : null}
        {!ai.ready ? <div className="ai-empty">
          <FrankEye size={68} />
          <b style={{ fontSize: 17 }}>{ai.keySet && !ai.enabled ? 'Frank выключен' : 'Frank ещё не настроен'}</b>
          <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>{ai.keySet && !ai.enabled
            ? 'Ключ уже сохранён — осталось включить переключатель «Включить Frank» в настройках и нажать «Сохранить».'
            : 'Frank отвечает на вопросы о вашей сети простыми словами: сам смотрит устройства, порты, Wi-Fi, журнал и безопасность. ' +
              'Нужен ключ API одного из сервисов: DeepSeek, Claude, ChatGPT — или своя модель в Ollama.'}</div>
          {standalone ? <div className="dim3" style={{ fontSize: 12.5 }}>Настраивается в Rack Live: Настройки → Frank</div> : <Btn kind="primary" icon="settings" onClick={() => { lsSet('rl_set_sec', 'frank'); onClose(); setTab('settings'); }}>Открыть настройки</Btn>}
        </div> : loading ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю разговор…</div>
        : !msgs.length ? <div className="ai-empty">
          <FrankEye size={68} />
          <b style={{ fontSize: 17 }}>Привет, я Frank</b>
          <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Я слежу за вашей сетью. Спросите что угодно — сам посмотрю данные Rack Live и отвечу простыми словами. В сети я ничего не меняю, только подсказываю.</div>
          <div className="ai-suggest">{AI_SUGGEST.map(s => <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          {standalone ? <div className="dim3" style={{ fontSize: 11.5, lineHeight: 1.4, maxWidth: 340 }}>Данные сети уходят в {ai.title}; пароли и ключи не передаются. Frank может ошибаться — проверяйте важное.</div> : null}
        </div> : msgs.map((m, i) => m.role === 'event' ? null : <div key={i} className={'ai-msg ' + m.role + (m.err ? ' err' : '')}>
          {m.role === 'user' ? <div className="ai-bubble">{m.text}</div> : <div className="ai-bubble">
            {m.err ? <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}><Icon name="alert" size={16} color="var(--red)" /><span>{m.text}</span></div> : <AiText text={m.text} />}
            {m.tools && m.tools.length ? <div className="ai-tools">{[...new Set(m.tools)].map(t => <span key={t}><Icon name="eye" size={11} />{t}</span>)}</div> : null}
            {(m.proposals || []).map(p => <ProposalCard key={p.id} p={p} onAct={act} />)}
          </div>}
        </div>)}
        {busy && view === 'chat' ? <div className="ai-msg assistant"><div className="ai-bubble ai-busy"><span className="spin-dot" />{busy.stage}
          {busy.tools.length ? <div className="ai-tools">{[...new Set(busy.tools)].map(t => <span key={t}><Icon name="check" size={11} />{t}</span>)}</div> : null}</div></div> : null}
      </div>}
      {menu ? <FrankMenu onClose={() => setMenu(false)} /> : null}
      {ai.ready && view === 'chat' && standalone ? <div className="fr-dock">
        {quick ? <div className="fr-quick">{AI_SUGGEST.map(s => <button key={s} type="button" onClick={() => { setQuick(false); send(s); }}>{s}</button>)}</div> : null}
        <textarea rows={1} value={q} placeholder={busy ? busy.stage : listening ? 'Говорите…' : 'Спросите Frank о сети'} onChange={e => setQ(e.target.value)} onKeyDown={key}
          disabled={!!busy} onFocus={() => setQuick(false)} />
        <div className="fr-dock-row">
          <button type="button" className={'fr-dbtn' + (quick ? ' on' : '')} title="Быстрые вопросы" onClick={() => setQuick(!quick)} disabled={!!busy}><Icon name="plus" size={22} stroke={2} /></button>
          <div className="fr-model"><b>{ai.title.split(' ')[0]}</b><span>{ai.effModel}</span></div>
          <div className="grow" />
          {SPEECH ? <button type="button" className={'fr-dbtn' + (listening ? ' rec' : '')} title="Сказать голосом" onClick={toggleMic} disabled={!!busy}><Icon name="mic" size={21} stroke={2} /></button> : null}
          <button type="button" className={'fr-send' + (q.trim() && !busy ? ' on' : '')} disabled={!q.trim() || !!busy} onClick={() => send(q)} title="Отправить">
            {busy ? <span className="spin-dot" /> : <Icon name="arrowUp" size={21} stroke={2.4} />}</button>
        </div>
      </div> : null}
      {ai.ready && view === 'chat' && !standalone ? <div className="ai-foot">
        <textarea className="input" rows={1} value={q} placeholder="Спросить Frank…" onChange={e => setQ(e.target.value)} onKeyDown={key} disabled={!!busy} />
        <Btn kind="primary" icon="send" busy={!!busy} disabled={!q.trim()} onClick={() => send(q)} />
      </div> : null}
      {ai.ready && view === 'chat' && !standalone ? <div className="ai-note">Данные сети уходят в {ai.title}; пароли и ключи не передаются. Frank может ошибаться — проверяйте важное.</div> : null}
    </div>
  </div>;
}

/* «Спросить Frank» — shown next to findings, diffs and the like when the assistant is set up */
function AskAi({ q, label = 'Спросить Frank', size = 'sm' }) {
  const { data, askAi } = useApp();
  if (!data.ai || !data.ai.ready || !askAi) return null;
  return <button type="button" className={'btn ' + size + ' frank-ask'} onClick={() => askAi(q)}><FrankEye size={18} round={6} />{label}</button>;
}

function AiCard() {
  const { data, refresh } = useApp(); const toast = useToast();
  const ai = data.ai;
  const [s, setS] = useState(() => ({ enabled: ai.enabled, preset: ai.preset, base: ai.base, model: ai.model, proxy: ai.proxy, limit: ai.limit, key: '', actions: ai.actions !== false }));
  const [res, setRes] = useState(null);
  const p = ai.presets.find(x => x.id === s.preset) || ai.presets[0];
  const set = (k, v) => setS(x => ({ ...x, [k]: v }));
  const pick = id => { setS(x => ({ ...x, preset: id, base: '', model: '', key: '' })); setRes(null); };
  const keySaved = ai.keySet && s.preset === ai.preset;
  const save = async () => { try { await api('/api/ai', { method: 'PUT', body: s }); toast('Сохранено'); setS(x => ({ ...x, key: '' })); refresh(); } catch (e) { toast(e.message, true); } };
  const test = async () => { setRes(null); try { const r = await api('/api/ai/test', { method: 'POST', body: s }); setRes(r); } catch (e) { setRes({ ok: false, error: e.message }); } };
  const t = ai.today || {};
  return <Card title={<span id="ai-settings" className="row" style={{ gap: 8 }}><FrankEye size={22} round={7} />Frank — помощник (ИИ)</span>} style={{ gridColumn: '1 / -1' }}>
    <div className="notify-grid">
      <div className="col" style={{ gap: 12 }}>
        <div className="row"><Switch on={!!s.enabled} onChange={v => set('enabled', v)} /><div className="grow"><div>Включить Frank</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Кнопка с глазом вверху: вопросы о сети простыми словами.</div></div></div>
        <div className="row"><Switch on={!!s.actions} onChange={v => set('actions', v)} /><div className="grow"><div>Frank может предлагать действия</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Перезапуск PoE или порта, проверка кабеля, перезагрузка точки, выключатели Home Assistant, исправления безопасности. Сам Frank ничего не делает: под ответом появится карточка, и действие выполнится только после вашей кнопки «Выполнить».</div></div></div>
        <Field label="Сервис">
          <div className="row wrap" style={{ gap: 6 }}>{ai.presets.map(x => <button key={x.id} type="button" className={'chip' + (s.preset === x.id ? ' on' : '')} onClick={() => pick(x.id)}>{x.title}</button>)}</div></Field>
        {!p.noKey ? <Field label="Ключ API" hint={p.keyUrl ? <>Получить: <a href={p.keyUrl} target="_blank" rel="noreferrer">{p.keyUrl.replace(/^https:\/\//, '')}</a></> : null}>
          <input className="input" type="password" autoComplete="off" value={s.key} placeholder={keySaved ? '•••••••• (не менять)' : 'sk-…'} onChange={e => set('key', e.target.value)} /></Field> : null}
        <Field label="Модель" hint={s.preset === 'claude' ? 'По умолчанию самая умная; дешевле — claude-sonnet-5-5 или claude-haiku-5-5' : s.preset === 'ollama' ? 'Модель с поддержкой инструментов (tools): qwen2.5, llama3.1 и т.п.' : 'Пусто — модель по умолчанию'}>
          <input className="input mono" value={s.model} placeholder={p.model || 'имя модели'} onChange={e => set('model', e.target.value)} /></Field>
        <details className="guide"><summary>Дополнительно: адрес API, прокси, лимит</summary>
          <div className="col" style={{ gap: 10, marginTop: 8 }}>
            <Field label="Адрес API" hint="Пусто — адрес сервиса по умолчанию. Для Ollama: http://IP-компьютера:11434/v1"><input className="input mono" value={s.base} placeholder={p.base || 'https://…/v1'} onChange={e => set('base', e.target.value)} /></Field>
            <Field label="Прокси (необязательно)" hint="Если сервис недоступен из вашей страны: http://адрес:порт. Или пустите его домен через VPN на роутере"><input className="input mono" value={s.proxy} placeholder="http://192.168.1.1:3128" onChange={e => set('proxy', e.target.value)} /></Field>
            <Field label="Вопросов в день, не больше" hint="Защита от случайных трат. 0 — без лимита"><input className="input" style={{ width: 100 }} value={s.limit} onChange={e => set('limit', +e.target.value || 0)} /></Field>
          </div></details>
        <div className="row wrap">
          <Btn onClick={test} icon="check">Проверить</Btn>
          {res ? <span className={'badge ' + (res.ok ? 'online' : 'offline')} style={{ whiteSpace: 'normal' }}>{res.ok ? 'работает: «' + res.answer + '»' : res.error}</span> : null}
          <div className="grow" /><Btn kind="primary" onClick={save}>Сохранить</Btn></div>
      </div>
      <div className="col" style={{ gap: 10 }}>
        <details className="guide" open={!ai.keySet}><summary>Где взять ключ — по шагам</summary><ol>
          <li><b>DeepSeek</b> (дёшево, работает из России): <a href="https://platform.deepseek.com" target="_blank" rel="noreferrer">platform.deepseek.com</a> → вход по почте →
            <b> Top up</b> (пополнить пару долларов) → <b>API Keys</b> → <b>Create new API key</b> → скопируйте ключ <code>sk-…</code> сюда.</li>
          <li><b>Claude</b>: <a href="https://console.anthropic.com" target="_blank" rel="noreferrer">console.anthropic.com</a> → Billing (пополнить) → API Keys → Create Key.
            Из России API недоступен — пустите <code>api.anthropic.com</code> через VPN на роутере или укажите прокси.</li>
          <li><b>ChatGPT</b>: <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com</a> → Billing → API keys. Ограничения по стране — как у Claude.</li>
          <li><b>Ollama</b> — бесплатно и без отправки данных наружу: модель работает на вашем компьютере (нужна хорошая видеокарта или много памяти).</li>
        </ol></details>
        <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
          <b>Что уходит в сервис:</b> вопрос и данные, которые Frank посмотрел: имена и статусы устройств, порты, клиенты (имена, IP, MAC), журнал, замечания.
          Пароли, ключи, токены и SNMP-community вырезаются до отправки. Ответы стоят денег у провайдера: обычно доли цента (DeepSeek) — несколько центов (Claude, ChatGPT) за вопрос.</div>
        <div className="frank-install">
          <AppIcon app="frank" size={40} radius={10} />
          <div className="grow" style={{ fontSize: 12.5, lineHeight: 1.45 }}><b style={{ fontSize: 13.5 }}>Frank отдельным приложением</b><br />
            Отдельный значок с глазом на экране телефона — чат с Frank сразу на весь экран. Установка с QR-кодом — в разделе <b>«Приложения»</b>.</div>
        </div>
        {t.q ? <div className="dim3" style={{ fontSize: 12.5 }}>Сегодня: {t.q} {ruPlural(t.q, 'вопрос', 'вопроса', 'вопросов')}, токенов {Math.round((t.in || 0) / 1000)}k на входе / {Math.round((t.out || 0) / 1000)}k на выходе</div> : null}
      </div>
    </div>
  </Card>;
}
