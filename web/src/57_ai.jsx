/* AI assistant: chat panel (questions about the network, the model reads live data through read-only tools) + settings card */
const AI_SUGGEST = ['Всё ли в порядке с сетью?', 'Почему может тормозить интернет?', 'Что исправить в безопасности в первую очередь?',
  'Какие устройства чаще всего пропадают?', 'У кого из клиентов слабый Wi-Fi?'];
/* «/» commands in the input (the server handles them: rackd/assistant.py COMMANDS) */
const AI_CMDS = [['/compact', 'Сжать разговор, освободить место'], ['/clear', 'Новый чистый разговор'], ['/context', 'Сколько места занято и чем'],
  ['/memory', 'Память Frank: показать или «/memory текст» — дописать'], ['/help', 'Список команд']];
const AI_CMD_RE = /^\/(clear|new|compact|context|memory|help)(\s|$)/i;
const aiFileUrl = id => '/api/ai/files/' + id;

/* files and photos for the next question: uploaded at once (photos made smaller first, like in «Сканер»), sent as ids with the question */
async function uploadAiFile(f) {
  let body = f;                                              // a photo (also HEIC from an iPhone) becomes a smaller JPEG / PNG the model can read; if the browser can't open it, it goes as is
  if (/^image\//.test(f.type) && !/gif|svg/.test(f.type)) { try { body = await shrinkImage(f); } catch (e) { body = f; } }
  const init = { method: 'POST', credentials: 'same-origin', headers: { 'X-File-Name': encodeURIComponent(f.name || 'фото.jpg') }, body };
  const tok = ssGet('rl_tok'); if (tok) init.headers['X-RL-Session'] = tok;
  const j = await (await fetch('/api/ai/files', init)).json();
  if (!j.ok) throw new Error(j.error || 'не получилось загрузить');
  return j.file;
}
function AttachChips({ files, onRemove }) {
  if (!files.length) return null;
  return <div className="ai-att">{files.map((f, i) => <div key={f.id || f.tmp} className={'ai-att-chip' + (f.busy ? ' busy' : '')}>
    {f.kind === 'image' && (f.local || f.id) ? <img src={f.local || aiFileUrl(f.id)} alt="" /> : <span className="ai-att-ic"><Icon name="file" size={16} /></span>}
    <span className="ai-att-name">{f.busy ? 'Загружаю…' : f.name}</span>
    <button type="button" title="Убрать" onClick={() => onRemove(i)}><Icon name="x" size={12} /></button></div>)}</div>;
}
/* what was attached to a question in the chat */
function MsgFiles({ files }) {
  return <div className="ai-msg-files">{files.map(f => f.kind === 'image'
    ? <a key={f.id} href={aiFileUrl(f.id)} target="_blank" rel="noreferrer"><img src={aiFileUrl(f.id)} alt={f.name} loading="lazy" /></a>
    : <a key={f.id} className="ai-file" href={aiFileUrl(f.id)} download={f.name}><Icon name="file" size={14} />{f.name}<small>{fmt.bytes(f.size)}</small></a>)}</div>;
}

/* FRANK.md — Frank's memory, like CLAUDE.md: the person's rules and notes, read in every chat */
function MemoryEditor({ onClose }) {
  const toast = useToast();
  const [text, setText] = useState(null); const [max, setMax] = useState(20000); const [busy, setBusy] = useState(false);
  useEffect(() => { api('/api/ai/memory').then(j => { setText(j.text || ''); setMax(j.max || 20000); }).catch(e => { toast(e.message, true); setText(''); }); }, []);
  const save = async () => { setBusy(true); try { await api('/api/ai/memory', { method: 'PUT', body: { text } }); toast('Память сохранена'); onClose(); } catch (e) { toast(e.message, true); } finally { setBusy(false); } };
  return <Modal title="Память Frank · FRANK.md" onClose={onClose} wide footer={<><Btn onClick={onClose}>Закрыть</Btn><Btn kind="primary" busy={busy} disabled={text == null || text.length > max} onClick={save}>Сохранить</Btn></>}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.5, marginBottom: 8 }}>Всё, что здесь написано, Frank читает в каждом разговоре — как CLAUDE.md у Claude Code. Пишите правила и факты:
      «Отвечай кратко», «NAS стоит в кладовке, роутер — в коридоре», «Порт 24 коммутатора не трогать». Frank сам дописывает сюда то, что вы просите запомнить (или команда <code>/memory текст</code>).</div>
    {text == null ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю…</div>
      : <textarea className="input mono ai-mem" value={text} onChange={e => setText(e.target.value)} placeholder={'- Отвечай кратко\n- Роутер Keenetic в коридоре, коммутатор в шкафу'} />}
    {text != null ? <div className="dim3" style={{ fontSize: 12, marginTop: 6, color: text.length > max ? 'var(--red)' : null }}>{text.length} из {max} символов</div> : null}
  </Modal>;
}
const tokK = n => n >= 1e6 ? (n / 1e6).toFixed(1).replace('.', ',') + ' млн' : n >= 1000 ? (n / 1000).toFixed(n >= 1e4 ? 0 : 1).replace('.', ',') + ' тыс.' : String(n);

/* how full the model's window is: a thin bar, the figures, and «Сжать» when it is getting tight */
function CtxMeter({ ctx, busy, onCompact }) {
  if (!ctx) return null;
  const pct = Math.min(100, ctx.pct), tone = pct >= 85 ? 'var(--red)' : pct >= 60 ? 'var(--orange)' : 'var(--accent)';
  return <div className="ai-ctx" title={`Системная часть ≈${tokK(ctx.parts.system + ctx.parts.tools)}, сводка ≈${tokK(ctx.parts.summary)}, разговор ≈${tokK(ctx.parts.chat)}${ctx.exact ? '' : ' (оценка)'}`}>
    <div className="ai-ctx-bar"><i style={{ width: pct + '%', background: tone }} /></div>
    <div className="ai-ctx-row"><span>Контекст · {ctx.exact ? '' : '≈'}{tokK(ctx.used)} из {tokK(ctx.window)} ({Math.round(ctx.pct)}%){ctx.squeezed ? ' · сжат' : ''}</span>
      {pct >= 60 && !busy ? <button type="button" className="ai-ctx-btn" onClick={onCompact}>Сжать</button> : null}</div>
  </div>;
}

/* the list of commands under the input when it starts with «/» */
function CmdHint({ q, onPick }) {
  if (!q.startsWith('/') || q.includes(' ')) return null;
  const list = AI_CMDS.filter(([c]) => c.startsWith(q.toLowerCase()));
  if (!list.length || (list.length === 1 && list[0][0] === q.toLowerCase())) return null;
  return <div className="ai-cmds">{list.map(([c, d]) => <button key={c} type="button" onClick={() => onPick(c)}><b>{c}</b><span>{d}</span></button>)}</div>;
}

/* Frank's avatar: an eye that blinks and glances around. While he works the mood shows how hard the question is:
   1 — calm (blue, looks around), 2 — straining (yellow, squints), 3 — heavy (red, frowns, glows and trembles). */
const EYE = 'M3 20C8 11 14 7.5 20 7.5S32 11 37 20C32 29 26 32.5 20 32.5S8 29 3 20Z';
function FrankEye({ size = 34, busy, mood, round }) {
  const id = React.useId().replace(/:/g, '');
  const m = mood != null ? mood : busy ? 1 : 0;
  if (THEME.frankAvatar) return <div className={'frank m' + m + (m ? ' busy' : '')} style={{ width: size, height: size, borderRadius: round != null ? round : size * .32 }}><img className="frank-img" src={THEME.frankAvatar} alt="" draggable="false" /></div>;      // the look brings its own picture
  return <div className={'frank m' + m + (m ? ' busy' : '')} style={{ width: size, height: size, borderRadius: round != null ? round : size * .32 }}>
    <svg viewBox="0 0 40 40" width={size * .8} height={size * .8}>
      <defs>
        <clipPath id={'fe' + id}><path d={EYE} /></clipPath>
        <radialGradient id={'fi' + id} cx=".4" cy=".35" r=".7"><stop className="s0" offset="0" /><stop className="s1" offset=".55" /><stop className="s2" offset="1" /></radialGradient>
      </defs>
      <g className="frank-body">
        <g className="frank-eye">
          <path d={EYE} style={{ fill: 'var(--frank-sclera, #f4f6ff)' }} />
          <g clipPath={`url(#fe${id})`}>
            <g className="frank-iris">
              <circle cx="20" cy="20" r="8.6" fill={`url(#fi${id})`} />
              <g className="frank-pupil"><circle cx="20" cy="20" r="3.8" style={{ fill: 'var(--frank-pupil, #081020)' }} /><circle cx="22.6" cy="17.4" r="1.6" fill="#fff" /></g>
            </g>
            <g className="frank-lid"><path d="M-2 -8H42V17L-2 10Z" style={{ fill: 'var(--frank-lid, #2c2e3c)' }} /><path d="M-2 10L42 17" stroke="#081020" strokeWidth="1.6" /></g>
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
/* full access: what Frank ran himself in this answer (commands with their output) */
/* скриншоты мини-браузера: Frank открыл страницу — картинка показывается прямо в ответе */
function ShotList({ shots }) {
  if (!shots || !shots.length) return null;
  return <div className="ai-shots">{shots.map(s => <a key={s} href={'/api/ai/shot/' + s} target="_blank" rel="noreferrer" className="ai-shot">
    <img src={'/api/ai/shot/' + s} alt="снимок страницы" loading="lazy" /></a>)}</div>;
}
function OpsList({ ops }) {
  const [open, setOpen] = useState(false);
  const changed = ops.filter(o => o.kind !== 'read').length;
  return <div className="ai-ops">
    <button type="button" className="ai-ops-head" onClick={() => setOpen(!open)}>
      <Icon name="terminal" size={13} />{changed ? `Frank выполнил ${changed} ${ruPlural(changed, 'изменение', 'изменения', 'изменений')}` : 'Frank посмотрел на устройствах'}
      {ops.length - changed ? ` · ${ops.length - changed} просмотр.` : ''}{ops.some(o => !o.ok) ? ' · есть ошибки' : ''}
      <Icon name="chevron" size={12} style={{ transform: open ? 'rotate(90deg)' : 'none', marginLeft: 'auto' }} /></button>
    {open ? ops.map((o, i) => <div key={i} className={'ai-op' + (o.ok ? '' : ' bad')}>
      <div className="dim3" style={{ fontSize: 11.5 }}>{o.device}{o.kind === 'read' ? ' · просмотр' : ' · изменение'}</div>
      <pre className="ai-cmd">{o.command || o.label}</pre>{o.out ? <pre className="ai-cmd out">{o.out}</pre> : null}</div>) : null}
  </div>;
}

function ProposalCard({ p, onAct }) {
  const [busy, setBusy] = useState(false);
  const go = async run => { setBusy(true); try { await onAct(p, run); } finally { setBusy(false); } };
  const st = busy && p.status === 'pending' ? 'running' : p.status;
  return <div className={'ai-prop ' + st}>
    <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
      <div className="ai-prop-ic"><Icon name={st === 'done' ? 'check' : st === 'error' ? 'alert' : st === 'cancelled' ? 'x' : 'bolt'} size={16} /></div>
      <div className="grow" style={{ minWidth: 0 }}>
        <b>{p.command ? 'Команда' : p.label}</b><div className="dim3" style={{ fontSize: 12 }}>{p.deviceName}{p.auto ? ' · Frank выполнил сам по вашей просьбе' : ''}</div>
        {p.command ? <pre className="ai-cmd">{p.command}</pre> : p.pre ? <pre className="ai-cmd">{p.pre}</pre> : p.text && st === 'pending' ? <div className="ai-prop-text">{p.text}</div> : null}
        {p.reason && st === 'pending' ? <div className="dim" style={{ fontSize: 12.5, marginTop: 4 }}>Зачем: {p.reason}</div> : null}
        {st === 'done' || st === 'error' ? (p.command || p.pre ? <pre className="ai-cmd out">{p.result}</pre>
          : <div className="ai-prop-text">{st === 'done' ? '✓ ' : ''}{p.result}</div>) : null}
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
/* the agent's rights (rackd/frank_agent.py MODES) — like the permission modes of Claude Code */
const AGENT_MODES = [['ask', 'Спрашивать', 'Смотрит сам; запись файлов и команды — по кнопке «Выполнить».'],
  ['edits', 'Правки сам', 'Файлы читает и меняет сам; команды, которые что-то меняют, — по кнопке.'],
  ['full', 'Полный доступ', 'Всё выполняет сразу. Никогда: удалять систему, форматировать диски, выключать машину, трогать пароли и данные Rack Live.']];
function FrankMenu({ onClose }) {
  const { refresh, data } = useApp(); const toast = useToast();
  const [m, setM] = useState(null); const [err, setErr] = useState(null); const [saving, setSaving] = useState(null); const [mem, setMem] = useState(false);
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
        {data.ai && data.ai.agent ? <>
          <div className="fr-menu-title">Агент: права</div>
          <Seg value={data.ai.agentMode || 'ask'} onChange={v => save({ agentMode: v }, 'agentMode')} options={AGENT_MODES.map(([value, label]) => ({ value, label }))} />
          <div className="dim3" style={{ fontSize: 12, lineHeight: 1.4 }}>{(AGENT_MODES.find(x => x[0] === (data.ai.agentMode || 'ask')) || [])[2]}</div>
        </> : null}
        <button type="button" className="fr-model-opt" onClick={() => setMem(true)}><span className="fr-radio"><Icon name="brain" size={15} /></span>
          <span className="grow" style={{ minWidth: 0 }}><b>Память Frank</b><small>FRANK.md — правила и заметки, которые Frank читает в каждом разговоре</small></span></button>
      </>}
    </div>
    {mem ? <MemoryEditor onClose={() => setMem(false)} /> : null}
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
  const [cid, setCid] = useState(() => initial ? null : new URLSearchParams(location.search).get('chat') || lsGet(CUR_KEY, '') || null);      // ?chat=<id> opens a given conversation (links, tests)
  const [msgs, setMsgs] = useState([]);
  const [chats, setChats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(null);                   // {stage, tools} while Frank works on this chat
  const [ctx, setCtx] = useState(null);                     // how full the model's window is for the open chat (the server counts it)
  const [att, setAtt] = useState([]);                       // files and photos for the next question
  const fileRef = useRef(null);
  const addFiles = list => {
    for (const f of Array.from(list || []).slice(0, 10)) {
      const tmp = Math.random().toString(36).slice(2), img = /^image\//.test(f.type);
      setAtt(a => [...a, { tmp, name: f.name || 'фото', kind: img ? 'image' : 'file', local: img ? URL.createObjectURL(f) : null, busy: true }]);
      uploadAiFile(f).then(m => setAtt(a => a.map(x => x.tmp === tmp ? { ...m, tmp, local: x.local } : x)))
        .catch(e => { toast(e.message, true); setAtt(a => a.filter(x => x.tmp !== tmp)); });
    }
    if (fileRef.current) fileRef.current.value = '';
  };
  const dropAtt = i => setAtt(a => a.filter((x, k) => { if (k === i && x.local) URL.revokeObjectURL(x.local); return k !== i; }));
  const onPaste = e => { const fs = e.clipboardData && e.clipboardData.files; if (fs && fs.length) { e.preventDefault(); addFiles(fs); } };      // a screenshot pasted with Ctrl+V
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
    if (!id) { setMsgs([]); setCtx(null); setLoading(false); return; }
    try {
      const c = await api('/api/ai/chats/' + id);
      if (!alive.current || cur.current !== id) return;
      setMsgs(c.messages); setCtx(c.ctx || null);
      if (c.job) { setBusy(b => b || { stage: 'Думаю…', tools: [], t0: Date.now() }); follow(c.job, id); }
    } catch (e) { if (e.status === 404) { setCid(null); setMsgs([]); } else toast(e.message, true); }
    finally { if (alive.current) setLoading(false); }
  };
  const loadList = async () => { try { const r = await api('/api/ai/chats'); alive.current && setChats(r.chats); } catch (e) { toast(e.message, true); } };
  const send = async text => {
    text = (text || '').trim();
    const cmd = (text.match(AI_CMD_RE) || [])[1];            // a command is not a question: no bubble, the result comes back as a note in the chat
    const files = cmd ? [] : att.filter(f => f.id);
    if ((!text && !files.length) || busy || !ai.ready) return;
    if (att.some(f => f.busy)) { toast('Подождите, файл ещё загружается', true); return; }
    const id = cur.current;
    if (cmd && /^(clear|new)$/i.test(cmd)) { setMsgs([]); setCtx(null); }
    else if (!cmd) setMsgs(m => [...m, { role: 'user', text: text || (files.every(f => f.kind === 'image') ? 'Посмотри фото.' : 'Посмотри файл.'), t: Date.now() / 1000, files: files.map(f => ({ id: f.id, name: f.name, kind: f.kind, size: f.size })) }]);
    if (!cmd) { att.forEach(f => f.local && URL.revokeObjectURL(f.local)); setAtt([]); }
    setQ(''); setBusy({ stage: cmd ? (/compact/i.test(cmd) ? 'Сжимаю разговор…' : '…') : 'Думаю…', tools: [], t0: Date.now() });
    try {
      const r = await api('/api/ai/ask', { method: 'POST', body: { chat: id, text, files: files.map(f => f.id) } });
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
  const key = e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      const t = q.trim().toLowerCase();                       // «/comp» + Enter = «/compact»
      const hit = t.startsWith('/') && !t.includes(' ') ? AI_CMDS.filter(([c]) => c.startsWith(t)) : [];
      send(hit.length === 1 ? hit[0][0] : q);
    }
  };
  const today = ai.today || {};
  const title = view === 'list' ? 'Разговоры' : T('frank.name', 'Frank');
  // voice input: the browser's own speech recognition (Safari/Chrome; needs https — on a plain http address the button is hidden)
  const [quick, setQuick] = useState(false);
  const [menu, setMenu] = useState(() => !!standalone && new URLSearchParams(location.search).get('menu') === '1');
  const act = async (p, run) => {
    try { const r = await api('/api/ai/act', { method: 'POST', body: { chat: cid, proposal: p.id, run } }); if (r.chat) { setMsgs(r.chat.messages); setCtx(r.chat.ctx || null); }
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
  const sub = ai.ready ? `${ai.title} · ${ai.effModel}${ai.agent ? ' · агент: ' + ((AGENT_MODES.find(x => x[0] === ai.agentMode) || AGENT_MODES[0])[1]).toLowerCase() : ''}` : 'не настроен';
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
              <div className="dim3" style={{ fontSize: 12 }}>{dayLabel(c.updated)} · {c.count} {ruPlural(c.count, 'сообщение', 'сообщения', 'сообщений')}{c.src === 'telegram' ? ' · из Telegram' : ''}{c.busy ? ' · Frank отвечает…' : ''}</div></div>
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
          <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Я слежу за вашей сетью. Спросите что угодно — сам посмотрю данные Rack Live и отвечу простыми словами. Можно прислать фото или файл (скрепка внизу), попросить «запомни…», а «/» покажет команды.</div>
          <div className="ai-suggest">{AI_SUGGEST.map(s => <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          {standalone ? <div className="dim3" style={{ fontSize: 11.5, lineHeight: 1.4, maxWidth: 340 }}>Данные сети уходят в {ai.title}; пароли и ключи не передаются. Frank может ошибаться — проверяйте важное.</div> : null}
        </div> : msgs.map((m, i) => m.role === 'event' ? null : m.role === 'note' ? <div key={i} className="ai-note-line">{m.text}</div> : <div key={i} className={'ai-msg ' + m.role + (m.err ? ' err' : '')}>
          {m.role === 'user' ? <div className="ai-bubble">{m.files && m.files.length ? <MsgFiles files={m.files} /> : null}{m.text}</div> : <div className="ai-bubble">
            {m.err ? <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}><Icon name="alert" size={16} color="var(--red)" /><span>{m.text}</span></div> : <AiText text={m.text} />}
            {m.tools && m.tools.length ? <div className="ai-tools">{[...new Set(m.tools)].map(t => <span key={t}><Icon name="eye" size={11} />{t}</span>)}</div> : null}
            <ShotList shots={m.shots} />
            {m.ops && m.ops.length ? <OpsList ops={m.ops} /> : null}
            {(m.proposals || []).filter(p => !(p.auto && !p.command)).map(p => <ProposalCard key={p.id} p={p} onAct={act} />)}
          </div>}
        </div>)}
        {busy && view === 'chat' ? <div className="ai-msg assistant"><div className="ai-bubble ai-busy"><span className="spin-dot" />{busy.stage}
          {busy.tools.length ? <div className="ai-tools">{[...new Set(busy.tools)].map(t => <span key={t}><Icon name="check" size={11} />{t}</span>)}</div> : null}</div></div> : null}
      </div>}
      {menu ? <FrankMenu onClose={() => setMenu(false)} /> : null}
      {ai.ready && view === 'chat' && standalone ? <div className="fr-dock">
        {quick ? <div className="fr-quick">{AI_SUGGEST.map(s => <button key={s} type="button" onClick={() => { setQuick(false); send(s); }}>{s}</button>)}</div> : null}
        <CmdHint q={q} onPick={c => setQ(c + ' ')} />
        <CtxMeter ctx={ctx} busy={busy} onCompact={() => send('/compact')} />
        <AttachChips files={att} onRemove={dropAtt} />
        <textarea rows={1} value={q} placeholder={busy ? busy.stage : listening ? 'Говорите…' : 'Спросите Frank о сети или введите /'} onChange={e => setQ(e.target.value)} onKeyDown={key}
          disabled={!!busy} onFocus={() => setQuick(false)} onPaste={onPaste} />
        <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
        <div className="fr-dock-row">
          <button type="button" className={'fr-dbtn' + (quick ? ' on' : '')} title="Быстрые вопросы" onClick={() => setQuick(!quick)} disabled={!!busy}><Icon name="plus" size={22} stroke={2} /></button>
          <button type="button" className="fr-dbtn" title="Прикрепить фото или файл" onClick={() => fileRef.current && fileRef.current.click()} disabled={!!busy}><Icon name="clip" size={20} stroke={2} /></button>
          <div className="fr-model"><b>{ai.title.split(' ')[0]}</b><span>{ai.effModel}</span></div>
          <div className="grow" />
          {SPEECH ? <button type="button" className={'fr-dbtn' + (listening ? ' rec' : '')} title="Сказать голосом" onClick={toggleMic} disabled={!!busy}><Icon name="mic" size={21} stroke={2} /></button> : null}
          <button type="button" className={'fr-send' + ((q.trim() || att.length) && !busy ? ' on' : '')} disabled={(!q.trim() && !att.length) || !!busy} onClick={() => send(q)} title="Отправить">
            {busy ? <span className="spin-dot" /> : <Icon name="arrowUp" size={21} stroke={2.4} />}</button>
        </div>
      </div> : null}
      {ai.ready && view === 'chat' && !standalone ? <CtxMeter ctx={ctx} busy={busy} onCompact={() => send('/compact')} /> : null}
      {ai.ready && view === 'chat' && !standalone ? <CmdHint q={q} onPick={c => setQ(c + ' ')} /> : null}
      {ai.ready && view === 'chat' && !standalone ? <AttachChips files={att} onRemove={dropAtt} /> : null}
      {ai.ready && view === 'chat' && !standalone ? <div className="ai-foot">
        <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
        <Btn icon="clip" title="Прикрепить фото или файл" disabled={!!busy} onClick={() => fileRef.current && fileRef.current.click()} />
        <textarea className="input" rows={1} value={q} placeholder="Спросить Frank… (или /)" onChange={e => setQ(e.target.value)} onKeyDown={key} onPaste={onPaste} disabled={!!busy} />
        <Btn kind="primary" icon="send" busy={!!busy} disabled={!q.trim() && !att.length} onClick={() => send(q)} />
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

/* «Советы Frank»: every few days Frank reviews the network and writes what he would add, what he dislikes and what he would change (rackd/advisor.py) */
const ADVICE_KIND = { add: ['plus', 'var(--green)', 'Добавить'], dislike: ['alert', 'var(--orange)', 'Не нравится'], idea: ['eye', 'var(--accent)', 'Идея'] };
const adviceWhen = t => { const d = Math.round((t - Date.now() / 1000) / 86400); return d <= 0 ? 'сегодня' : d === 1 ? 'завтра' : `через ${d} ${ruPlural(d, 'день', 'дня', 'дней')}`; };

function AdviceWidget() {
  const { data, admin, refresh, askAi } = useApp(); const toast = useToast();
  const a = data.advice;
  if (!admin || !a) return <Card title="Советы Frank"><div className="dim" style={{ fontSize: 13 }}>Войдите, чтобы увидеть советы помощника.</div></Card>;
  const close = async (x, done) => { try { await api('/api/advice/close', { method: 'POST', body: { id: x.id, done } }); refresh(); } catch (e) { toast(e.message, true); } };
  const again = async () => { try { const r = await api('/api/advice/refresh', { method: 'POST', body: {} }); if (!r.started) toast(r.why, true); refresh(); } catch (e) { toast(e.message, true); } };
  return <Card title={<span className="row" style={{ gap: 8 }}><FrankEye size={20} round={6} />Советы Frank</span>}
    right={a.ready && a.on ? <Btn size="sm" icon="refresh" disabled={a.running} onClick={again}>{a.running ? 'Думаю…' : 'Обновить'}</Btn> : null}>
    {!a.ready ? <div className="dim" style={{ fontSize: 13 }}>Включите Frank в Настройках — раз в {a.days} {ruPlural(a.days, 'день', 'дня', 'дней')} он будет смотреть вашу сеть и подсказывать, что добавить, что ему не нравится и что бы он изменил.</div>
      : !a.on ? <div className="dim" style={{ fontSize: 13 }}>Советы выключены (Настройки → Frank).</div>
      : <>
        {a.error ? <div className="dim" style={{ fontSize: 12.5, color: 'var(--orange)', marginBottom: 6 }}>Не вышло подготовить советы: {a.error}. Попробую снова позже.</div> : null}
        {!a.items.length ? <div className="dim" style={{ fontSize: 13 }}>{a.running ? 'Frank изучает сеть, это займёт минуту…' : a.last ? 'Новых советов нет — всё прочитано.' : 'Первые советы появятся в ближайшие минуты.'}</div> : null}
        <div className="list advice-list">{a.items.map(x => { const k = ADVICE_KIND[x.kind] || ADVICE_KIND.idea; return <div className="advice" key={x.id}>
          <span className="advice-ic" style={{ color: k[1] }}><Icon name={k[0]} size={16} /></span>
          <div className="grow"><div className="advice-t"><b>{x.title}</b><span className="advice-k" style={{ color: k[1] }}>{k[2]}</span></div>
            <div className="dim" style={{ fontSize: 13, lineHeight: 1.45 }}>{x.text}</div>
            <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>
              {x.ask ? <Btn size="sm" onClick={() => askAi(x.ask)}>Спросить подробнее</Btn> : null}
              <Btn size="sm" onClick={() => close(x, true)}>Сделано</Btn><Btn size="sm" onClick={() => close(x, false)}>Скрыть</Btn></div></div></div>; })}</div>
        {a.last ? <div className="dim3" style={{ fontSize: 11.5, marginTop: 8 }}>Совет от {fmt.ago(a.last, data.now)}{a.next ? ` · следующий ${adviceWhen(a.next)}` : ''}</div> : null}
      </>}
  </Card>;
}

function AdviceSettings({ ai }) {
  const { data, refresh } = useApp(); const toast = useToast();
  const a = data.advice || { on: true, days: 3, telegram: false };
  const save = async part => { try { await api('/api/advice/settings', { method: 'PUT', body: part }); refresh(); } catch (e) { toast(e.message, true); } };
  return <div className="col" style={{ gap: 10 }}>
    <div className="row"><Switch on={!!a.on} onChange={v => save({ on: v })} /><div className="grow"><div>Советы Frank раз в несколько дней</div>
      <div className="dim3" style={{ fontSize: 12.5 }}>Frank сам изучает сеть и пишет, что добавил бы, что ему не нравится и что бы изменил. Виджет «Советы Frank» на главной. Один запрос — как один вопрос.</div></div></div>
    {a.on ? <div className="row wrap" style={{ gap: 8 }}><span className="dim" style={{ fontSize: 13 }}>Как часто:</span>
      {[1, 3, 7, 14].map(n => <button key={n} type="button" className={'chip' + (a.days === n ? ' on' : '')} onClick={() => save({ days: n })}>{n === 1 ? 'каждый день' : `раз в ${n} ${ruPlural(n, 'день', 'дня', 'дней')}`}</button>)}</div> : null}
    {a.on ? <div className="row"><Switch on={!!a.telegram} onChange={v => save({ telegram: v })} /><div className="grow"><div>Присылать в Telegram</div>
      <div className="dim3" style={{ fontSize: 12.5 }}>Короткий список заголовков, когда появились новые советы.</div></div></div> : null}
  </div>;
}

/* «Полный доступ»: Frank как самостоятельный агент со своим проектом Rack Live (rackd/frankdev.py).
   Панель привязана к проекту: правки в проекте → «Собрать» → «Проверить» → «Выложить в панель» (прежний код в .prev, панель перезапускается сама). */
const PROJECT_OPS = [['seed', 'Создать проект', 'plus'], ['build', 'Собрать', 'wrench'], ['test', 'Проверить', 'check'],
  ['deploy', 'Выложить в панель', 'upload'], ['rollback', 'Откатить', 'refresh']];
function useProjectJob(onDone) {
  const toast = useToast();
  const [job, setJob] = useState(null);
  const start = async op => {
    try {
      const r = await api('/api/ai/project', { method: 'POST', body: { op } });
      if (r.job) setJob({ id: r.job, stage: 'Запуск…', done: false }); else { toast('Готово'); if (onDone) onDone(r); }
      return r;
    } catch (e) { toast(e.message, true); return null; }
  };
  useEffect(() => {
    if (!job || job.done) return;
    const t = setInterval(async () => {
      try {
        const j = await api('/api/dev/job', { method: 'POST', body: { job: job.id } });
        setJob(x => ({ ...x, ...j }));
        if (j.done) { toast(j.error ? 'Не получилось: ' + j.error : 'Готово', !!j.error); if (onDone) onDone(); }
      } catch (e) { }
    }, 2000);
    return () => clearInterval(t);
  }, [job && job.id, job && job.done]);
  return { job, start, running: !!job && !job.done };
}
function ProjectCard({ ai }) {
  const { refresh } = useApp(); const confirm = useConfirm();
  const p = ai.project || {};
  const { job, start, running } = useProjectJob(() => refresh());
  const ask = { deploy: 'Выложить код проекта в работающую панель? Прежний код сохранится в .prev, панель перезапустится на несколько секунд.',
    rollback: 'Вернуть прежний код панели и перезапустить её?', seed: 'Создать проект: склонировать Rack Live с GitHub в папку Frank?' };
  const run = async op => {
    if (ask[op] && !(await confirm(ask[op], { danger: op !== 'seed', ok: 'Продолжить' }))) return;
    await start(op);
  };
  return <div className="col" style={{ gap: 8, marginTop: 10, padding: 12, borderRadius: 12, border: '1px solid var(--line2)', background: 'var(--bg2)' }}>
    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><span className="badge">проект Frank</span>
      <b className="mono" style={{ fontSize: 12, overflowWrap: 'anywhere' }}>{p.path || '…'}</b></div>
    <div className="dim3" style={{ fontSize: 12, lineHeight: 1.45 }}>
      {p.exists ? <>версия {p.version || '?'}{p.runningVersion && p.runningVersion !== p.version ? ` · в панели сейчас ${p.runningVersion}` : ' · совпадает с панелью'}
        {p.git ? ` · ${p.git.branch} @ ${p.git.head}${p.git.changes ? `, изменено файлов: ${p.git.changes}` : ', без изменений'}` : ' · без git (копия кода)'}
        {p.build && p.build.stale ? ' · фронт не собран после правок' : ''}
        {p.lastDeploy && p.lastDeploy.t ? ` · выложено ${new Date(p.lastDeploy.t * 1000).toLocaleString('ru-RU')}` : ''}
        {p.lastTest && p.lastTest.t ? ` · тесты ${p.lastTest.ok ? 'прошли' : 'нашли ошибки'}` : ''}</>
        : 'Проекта ещё нет: «Создать проект» склонирует Rack Live с GitHub (с build.py и тестами). Без сети — скопирует работающий код.'}</div>
    {p.exists && !p.canDeploy ? <div style={{ fontSize: 12, color: 'var(--orange)' }}>Выкладка сейчас недоступна: {p.why}</div> : null}
    <div className="row wrap" style={{ gap: 6 }}>
      {PROJECT_OPS.map(([op, label, icon]) => <Btn key={op} size="sm" icon={icon} busy={running && job && job.stage && job.stage === label}
        onClick={() => !running && run(op)}>{label}</Btn>)}
    </div>
    {running ? <div className="row" style={{ gap: 8, fontSize: 12.5 }}><span className="spin-dot" />{(job && job.stage) || 'Работаю…'}</div> : null}
  </div>;
}
function AiCard() {
  const { data, refresh } = useApp(); const toast = useToast();
  const ai = data.ai;
  const [s, setS] = useState(() => ({ enabled: ai.enabled, preset: ai.preset, base: ai.base, model: ai.model, proxy: ai.proxy, limit: ai.limit, key: '', actions: ai.actions !== false, telegram: ai.telegram !== false, admin: !!ai.admin,
    window: ai.window || 0, autoCompact: ai.autoCompact !== false, agent: !!ai.agent, agentMode: ai.agentMode || 'ask', full: !!ai.full, browser: ai.browser !== false }));
  const [res, setRes] = useState(null); const [mem, setMem] = useState(() => new URLSearchParams(location.search).get('memory') === '1');
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
        {s.actions ? <div className={'row' + (s.admin ? ' ai-admin-on' : '')}><Switch on={!!s.admin} onChange={v => set('admin', v)} /><div className="grow"><div>Полный доступ <span className="ai-badge">админ</span></div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Frank сам работает на устройствах через командную строку — Keenetic, OpenWrt, Synology (docker, контейнеры), TP-Link, серверы по SSH:
            настроить роутер, запустить контейнер, посмотреть логи. <b>Смотрит</b> — когда нужно для ответа. <b>Меняет</b> — только то, о чём вы прямо попросили
            (сервер сверяет с вашим сообщением). <b>Опасное</b> (перезагрузка, WAN, VPN, firewall, порты, удаление) — карточкой «Выполнить». Сброс и пароли запрещены.
            Каждая команда — в журнале событий.</div>
          {s.admin ? <div className="ai-admin-warn">Модель может ошибиться в команде и, например, отрезать интернет — исправлять тогда придётся вручную у роутера.
            Для Synology включите SSH (Панель управления → Терминал); вход — тем же пользователем DSM.</div> : null}</div></div> : null}
        <div className="row"><Switch on={!!s.telegram} onChange={v => set('telegram', v)} /><div className="grow"><div>Отвечать в Telegram</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Напишите вопрос боту Rack Live в личку — ответит Frank. Только привязанным аккаунтам (Настройки → Уведомления → «Привязать Telegram»); /new — новый разговор. Разговоры видны и в приложении Frank.</div></div></div>
        <div className={'row' + (s.agent ? ' ai-admin-on' : '')}><Switch on={!!s.agent} onChange={v => set('agent', v)} /><div className="grow"><div>Агент: файлы и команды <span className="ai-badge">как Claude Code</span></div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Frank становится универсальным помощником: читает и пишет файлы, ищет по ним, выполняет команды на машине, где работает Rack Live
            ({ai.agentWhere}). Своя рабочая папка для проектов и скриптов; ваши вложения он тоже может открыть. Не только про сеть — любые задачи.</div>
          {s.agent ? <div style={{ marginTop: 8 }}>{s.full ? null : <Seg value={s.agentMode || 'ask'} onChange={v => set('agentMode', v)} options={AGENT_MODES.map(([value, label]) => ({ value, label }))} />}
            <div className="dim3" style={{ fontSize: 12.5, marginTop: 6 }}>{s.full ? 'Права: полный доступ — все шаги без подтверждения (включается галочкой «Полный доступ» ниже).'
              : ((AGENT_MODES.find(x => x[0] === (s.agentMode || 'ask')) || [])[2] + ' Каждое изменение и команда — в журнале событий.')}</div>
            {!s.full && s.agentMode === 'full' ? <div className="ai-admin-warn">Модель может ошибиться — например, удалить не тот файл в рабочей папке или установить лишнее. Данные и программа Rack Live
              защищены, разрушительные команды запрещены всегда, но остальное Frank делает без вопросов.</div> : null}</div> : null}</div></div>
        {s.agent ? <div className="row"><Switch on={s.browser !== false} onChange={v => set('browser', v)} /><div className="grow"><div>Мини-браузер <span className="ai-badge">скриншоты</span></div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Frank может открыть страницу (роутер, панель, VPS, любой сайт) в headless-браузере, прочитать её и прислать скриншот в
            чат — «покажи, как это выглядит». {ai.browserReady ? <>Браузер есть: <b className="mono">{ai.browserBin}</b>.</> : <b style={{ color: 'var(--orange)' }}>В этой установке браузера нет — он ставится в образ Docker при сборке.</b>}
            Ограничения: http/https, без входа (страница за паролем покажет только форму входа).</div></div></div> : null}
        {s.agent ? <div className={'row' + (s.full ? ' ai-admin-on' : '')}><Switch on={!!s.full} onChange={v => setS(x => ({ ...x, full: v, agent: v ? true : x.agent, agentMode: v ? 'full' : (x.agentMode === 'full' ? 'edits' : x.agentMode) }))} /><div className="grow">
          <div>Полный доступ <span className="ai-badge">как opencode</span></div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Frank становится самостоятельным агентом со своим проектом Rack Live: работает без карточек, правит код проекта, собирает,
            проверяет тестами и по вашей просьбе выкладывает его в панель — панель остаётся связанной с проектом, что в проекте, то и работает.
            По умолчанию выключено: без галочки Frank такой же, как раньше.</div>
          {s.full && !ai.full ? <div className="ai-admin-warn">Сохраните настройки — после этого Frank получит полный доступ и появится карточка проекта.</div> : null}
          {s.full && ai.full ? <div className="ai-admin-warn">Полный доступ разрешает модели менять и саму панель — по вашей просьбе. Прежний код всегда остаётся в .prev: «Откатить» вернёт его,
            и при сбое панель откатится сама. Данные панели (пароли устройств, вход, история) Frank не трогает, разрушительные команды запрещены всегда.</div> : null}
          {ai.full ? <ProjectCard ai={ai} /> : null}</div></div> : null}
        <div className="row"><span className="ico-circle"><Icon name="brain" size={16} /></span><div className="grow"><div>Память Frank (FRANK.md)</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Ваши правила и заметки, которые Frank читает в каждом разговоре — как CLAUDE.md у Claude Code. Попросите «запомни…» в разговоре или впишите сами.</div></div>
          <Btn size="sm" onClick={() => setMem(true)}>Открыть</Btn></div>
        {mem ? <MemoryEditor onClose={() => setMem(false)} /> : null}
        <AdviceSettings ai={ai} />
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
            <Field label="Окно контекста, токенов" hint={`Сколько модель «держит в голове». 0 — по названию модели (сейчас ≈${tokK(ai.effWindow || 0)}). Если у вашей модели другое окно — впишите его, полоса «Контекст» в разговоре станет точнее`}>
              <input className="input mono" style={{ width: 140 }} inputMode="numeric" value={s.window || ''} placeholder="авто" onChange={e => set('window', +e.target.value.replace(/\D/g, '') || 0)} /></Field>
            <div className="row"><Switch on={!!s.autoCompact} onChange={v => set('autoCompact', v)} /><div className="grow"><div>Сжимать разговор само</div>
              <div className="dim3" style={{ fontSize: 12.5 }}>Когда разговор заполнил окно почти целиком, Frank перед ответом превращает старую часть в короткую сводку и пишет об этом в разговоре. Вручную — команда /compact.</div></div></div>
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
