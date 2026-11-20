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
    <div className="ai-ctx-row"><span>Контекст · {ctx.exact ? '' : '≈'}{tokK(ctx.used)} из {ctx.windowSource === 'estimate' ? '≈' : ''}{Number(ctx.window).toLocaleString('ru-RU')} ({Math.round(ctx.pct)}%){ctx.squeezed ? ' · сжат' : ''}</span>
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
/* «Аврора»: Frank — линия, как остальные кнопки, но живая: зрачок цвета системы оглядывается, глаз моргает; пока Frank думает — зрачок «дышит» */
function AuEye({ size = 22, busy, tight }) {         // tight: the frame hugs the eye (a big picture in a widget), size = its width
  const delay = React.useMemo(() => -(Math.random() * 9).toFixed(2) + 's', []);          // every eye on the screen looks around in its own rhythm
  return <svg className={'au-eye' + (busy ? ' busy' : '')} viewBox={tight ? '1 3.6 22 16.8' : '0 0 24 24'} width={size} height={tight ? Math.round(size * 16.8 / 22) : size} style={{ '--ae-d': delay }} aria-hidden="true">
    <g className="ae-lid">
      <path d="M2.2 12C4.9 7.3 8.3 5 12 5s7.1 2.3 9.8 7c-2.7 4.7-6.1 7-9.8 7s-7.1-2.3-9.8-7Z" fill="none" stroke="currentColor" strokeWidth={size > 40 ? 1.3 : 1.7} strokeLinejoin="round" />
      <g className="ae-look"><circle cx="12" cy="12" r="3.5" className="ae-pupil" /><circle cx="13.25" cy="10.75" r=".95" fill="#fff" opacity=".9" /></g>
    </g>
  </svg>;
}
function FrankEye({ size = 34, busy, mood, round }) {
  const id = React.useId().replace(/:/g, '');
  const m = mood != null ? mood : busy ? 1 : 0;
  if (!THEME.frankAvatar && isAurora()) return <span className="frank-mono" style={{ width: size, height: size, display: 'inline-grid', placeItems: 'center', flex: 'none' }}><AuEye size={Math.max(14, Math.round(size * (size > 40 ? .86 : .8)))} busy={m > 0} /></span>;      // «Аврора»: the living line eye at every size
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
function FrankMenu({ onClose, mode, onConfigure }) {
  const { refresh, data } = useApp(); const toast = useToast(); const ai = data.ai || {};
  const [m, setM] = useState(null); const [err, setErr] = useState(''); const [saving, setSaving] = useState(''); const [section, setSection] = useState('home');
  useEffect(() => { if (ai.ready) api('/api/ai/models', { method: 'POST', body: {} }).then(setM).catch(e => setErr(e.message));
    const h = e => e.key === 'Escape' && onClose(); window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h); }, [mode]);
  const save = async (part, id) => { setSaving(id); try { await api('/api/ai', { method: 'PUT', body: part }); await refresh(); onClose(); } catch (e) { toast(e.message, true); } finally { setSaving(''); } };
  return <div className="fr-menu-wrap" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="fr-menu">
    {mode === 'provider' && section === 'home' ? <>
      <div className="fr-eye-head"><div><b>Frank</b><span>Провайдер, лимиты и настройки</span></div><button type="button" className="btn sm" onClick={onClose}>Готово</button></div>
      <button type="button" className="fr-eye-action" onClick={() => setSection('providers')}><span><b>Провайдер</b><small>{ai.title || 'Выбрать сервис'}</small></span><Icon name="chevron" size={17} /></button>
      <div className="fr-eye-limits"><div className="fr-eye-label">Лимиты и баланс</div>
        {!ai.ready ? <div className="fr-eye-note">Подключи провайдера, чтобы увидеть его данные.</div> : ai.preset === 'mozg' ? <><div className="fr-eye-note">Mozg не передаёт остаток кредитов через API. Посмотри его в профиле Mozg.</div><a className="fr-eye-link" href="https://ru.app.mozg.world/" target="_blank" rel="noreferrer">Открыть Mozg ↗</a></> : !m && !err ? <div className="fr-eye-note">Загружаю данные…</div> : m && m.balance ? <><div className="fr-eye-amount">{money(m.balance)}</div><div className="fr-eye-note">Баланс {ai.title} по данным сервиса</div></>
          : ['deepseek','openrouter'].includes(ai.preset) ? <div className="fr-eye-note">Не удалось получить баланс {ai.title}. Попробуй открыть меню позже.</div>
          : <div className="fr-eye-note">Этот сервис не сообщает баланс Frank.</div>}
        <div className="fr-eye-stats"><span>Вопросы Frank сегодня</span><b>{(m?.today || ai.today || {}).q || 0}{ai.limit ? ' / ' + ai.limit : ' · без лимита'}</b></div>
        {ai.limit ? <div className="fr-eye-caption">Осталось вопросов сегодня: {Math.max(0, ai.limit - Number((m?.today || ai.today || {}).q || 0))}</div> : null}
        {m?.month ? <div className="fr-eye-stats"><span>Токены за месяц</span><b>{Number((m.month.in || 0) + (m.month.out || 0)).toLocaleString('ru-RU')}</b></div> : null}
        <div className="fr-eye-caption">Вопросы и токены считаются во Frank по всем провайдерам. Это не остаток подписки.</div>
      </div>
      <button type="button" className="fr-eye-action" onClick={() => onConfigure(ai.preset)}><span><b>Настройки Frank</b><small>Доступ, ключи и параметры</small></span><Icon name="chevron" size={17} /></button>
    </> : <>
    <div className="fr-menu-title">{mode === 'provider' ? 'Провайдер' : 'Модель'}</div>
    {mode === 'provider' ? <>
      <button type="button" className="fr-eye-back" onClick={() => setSection('home')}>‹ Назад</button>
      {(ai.presets || []).map(p => { const ready = (ai.configuredPresets || []).includes(p.id) || p.noKey;
        return <button key={p.id} type="button" className={'fr-model-opt' + (p.id === ai.preset ? ' on' : '')} disabled={!!saving}
          onClick={() => p.id === ai.preset ? onClose() : ready ? save({ preset: p.id }, p.id) : onConfigure(p.id)}>
          <span className="fr-radio">{saving === p.id ? <span className="spin-dot" /> : p.id === ai.preset ? <Icon name="check" size={14} /> : null}</span>
          <span className="grow"><b>{p.title}</b><small>{ready ? 'Настроен' : 'Добавить ключ'}</small></span></button>; })}
    </> : !m ? <div className="dim" style={{padding:12}}>{err || 'Загружаю модели…'}</div> : <>
      <div className="fr-models">{m.models.map(x => <button key={x.id} type="button" className={'fr-model-opt' + (x.id === m.model ? ' on' : '')} disabled={!!saving}
        onClick={() => x.id === m.model ? onClose() : save({ model: x.id, effort: '' }, x.id)}>
        <span className="fr-radio">{saving === x.id ? <span className="spin-dot" /> : x.id === m.model ? <Icon name="check" size={14} /> : null}</span>
        <span className="grow"><b>{x.name}</b><small>{x.desc || x.id}{x.vision ? ' · видит изображения' : ''}</small></span></button>)}</div>
      {(() => { const current = m.models.find(x => x.id === m.model); return current && current.efforts && current.efforts.length ? <><div className="fr-menu-title">Глубина ответа</div><Seg value={m.effort || ''} onChange={v => save({effort:v}, 'effort')} options={EFFORTS.filter(([v]) => !v || current.efforts.includes(v)).map(([value,label]) => ({value,label}))} /></> : null; })()}
      <div className="dim3" style={{padding:12,fontSize:12}}>Список зависит от выбранного провайдера и ключа.</div>
    </>}
    </>}
  </div></div>;
}

/* messages written while Frank was busy: they leave one by one; each can be taken back */
function QueueList({ items, onDrop }) {
  if (!items.length) return null;
  return <div className="ai-queue" style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '4px 12px' }}>
    <div className="dim3" style={{ fontSize: 11.5 }}>В очереди ({items.length}) — уйдут по одному, когда Frank закончит</div>
    {items.map((it, i) => <div key={i} className="row" style={{ gap: 6, fontSize: 13 }}>
      <span className="dim3">{i + 1}.</span><span className="grow ellipsis">{it.text}</span>
      <button type="button" className="btn sm icon" title="Убрать из очереди" onClick={() => onDrop(i)}><Icon name="x" size={13} /></button></div>)}
  </div>;
}

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
  const alive = useRef(true), listRef = useRef(null), asked = useRef(false), cur = useRef(cid), polling = useRef(null), dockRef = useRef(null);
  const [dockH, setDockH] = useState(124);                  // the input capsule floats over the messages: they get as much room under them as it takes now
  const [queue, setQueue] = useState([]);                   // what the person wrote while Frank was busy: goes out one by one, as each answer ends
  const queueRef = useRef([]), drain = useRef(null);
  const setQ2 = f => { queueRef.current = f(queueRef.current); setQueue(queueRef.current); };
  cur.current = cid;
  useEffect(() => () => { alive.current = false; }, []);
  useEffect(() => { lsSet(CUR_KEY, cid || ''); }, [cid]);
  useEffect(() => { const el = listRef.current; if (el && view === 'chat') el.scrollTop = el.scrollHeight; }, [msgs, busy, view, dockH]);
  useEffect(() => {
    const el = dockRef.current; if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => setDockH(Math.ceil(el.getBoundingClientRect().height)));
    ro.observe(el); setDockH(Math.ceil(el.getBoundingClientRect().height));
    return () => ro.disconnect();
  }, [ai.ready, view, standalone]);
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
    if (alive.current && cur.current === chatId) {
      await open(chatId, true);                              // the answer and its cards (confirm / refuse buttons) are saved on the server: take them
      if (alive.current && cur.current === chatId) setBusy(null);
      if (alive.current && cur.current === chatId && drain.current) drain.current();
    }
  };
  const open = async (id, quiet) => {
    if (!quiet) setQ2(() => []);
    setView('chat'); setCid(id); if (!quiet) { setBusy(null); setLoading(true); }
    if (!id) { setMsgs([]); setCtx(null); setLoading(false); return null; }
    try {
      const c = await api('/api/ai/chats/' + id);
      if (!alive.current || cur.current !== id) return null;
      setMsgs(c.messages); setCtx(c.ctx || null);
      if (c.job) { setBusy(b => b || { stage: 'Думаю…', tools: [], t0: Date.now() }); follow(c.job, id); }
      return c;
    } catch (e) { if (e.status === 404) { setCid(null); setMsgs([]); } else toast(e.message, true); }
    finally { if (alive.current) setLoading(false); }
  };
  const loadList = async () => { try { const r = await api('/api/ai/chats'); alive.current && setChats(r.chats); } catch (e) { toast(e.message, true); } };
  const send = async text => {
    text = (text || '').trim();
    const cmd = (text.match(AI_CMD_RE) || [])[1];            // a command is not a question: no bubble, the result comes back as a note in the chat
    const files = cmd ? [] : att.filter(f => f.id);
    if ((!text && !files.length) || !ai.ready) return;
    if (att.some(f => f.busy)) { toast('Подождите, файл ещё загружается', true); return; }
    if (busy) {                                              // Frank is working: the question waits in the queue and goes out when he finishes
      if (cmd) { toast('Команды работают, когда Frank свободен', true); return; }
      if (queueRef.current.length >= 10) { toast('В очереди уже 10 сообщений', true); return; }
      setQ2(x => [...x, { text, files: files.map(f => ({ id: f.id, name: f.name, kind: f.kind, size: f.size })) }]);
      att.forEach(f => f.local && URL.revokeObjectURL(f.local)); setAtt([]); setQ('');
      return;
    }
    await sendNow(text, files);
  };
  const stop = async () => {
    const job = polling.current; if (!job) return;
    setBusy(b => b && { ...b, stage: 'Останавливаю…' });
    try { await api('/api/ai/stop', { method: 'POST', body: { job } }); } catch (e) { toast(e.message, true); }
  };
  drain.current = () => { const nx = queueRef.current[0]; if (!nx) return; setQ2(x => x.slice(1)); sendNow(nx.text, nx.files); };
  const sendNow = async (text, files) => {
    const cmd = (text.match(AI_CMD_RE) || [])[1];
    const id = cur.current;
    if (cmd && /^(clear|new)$/i.test(cmd)) { setMsgs([]); setCtx(null); }
    else if (!cmd) setMsgs(m => [...m, { role: 'user', text: text || (files.every(f => f.kind === 'image') ? 'Посмотри фото.' : 'Посмотри файл.'), t: Date.now() / 1000, files: files.map(f => ({ id: f.id, name: f.name, kind: f.kind, size: f.size })) }]);
    if (!cmd) { att.forEach(f => f.local && URL.revokeObjectURL(f.local)); setAtt([]); }
    if (text === q.trim()) setQ('');
    setBusy({ stage: cmd ? (/compact/i.test(cmd) ? 'Сжимаю разговор…' : '…') : 'Думаю…', tools: [], t0: Date.now() });
    try {
      const r = await api('/api/ai/ask', { method: 'POST', body: { chat: id, text, files: files.map(f => f.id) } });
      if (!alive.current) return;
      if (cur.current === id) { cur.current = r.chat; setCid(r.chat); }
      follow(r.job, r.chat);
    } catch (e) {
      setBusy(null); setMsgs(m => [...m, { role: 'assistant', text: e.message, err: true }]);
      if (queueRef.current.length) setTimeout(() => drain.current && drain.current(), 300);      // do not leave the rest of the queue hanging
    }
  };
  useEffect(() => {
    if (initial && ai.ready && !asked.current) { asked.current = true; send(initial); }
    else if (cid && ai.ready) open(cid);
  }, []);
  const del = async c => {
    if (!(await confirm(`Удалить разговор «${String(c.title).slice(0, 48)}»? Восстановить его будет нельзя.`, { title: 'Удалить разговор', ok: 'Удалить', danger: true }))) return;
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
  const title = view === 'list' ? 'Разговоры' : T('frank.name', 'Frank');
  const [quick, setQuick] = useState(false);
  const [menu, setMenu] = useState(() => !!standalone && new URLSearchParams(location.search).get('menu') === '1' ? 'provider' : '');
  const [frSettings, setFrSettings] = useState('');
  const act = async (p, run) => {
    try { const r = await api('/api/ai/act', { method: 'POST', body: { chat: cid, proposal: p.id, run } }); if (r.chat) { setMsgs(r.chat.messages); setCtx(r.chat.ctx || null); }
      if (run) toast(r.proposal.status === 'done' ? '✓ ' + r.proposal.result : r.proposal.result, r.proposal.status !== 'done'); }
    catch (e) { toast(e.message, true); open(cid, true); }
  };
  const toggleList = () => { if (view === 'list') setView('chat'); else { setView('list'); setChats(null); loadList(); } };
  const sub = ai.ready ? `${ai.title} · ${ai.effModel}${ai.agent ? ' · агент: ' + ((AGENT_MODES.find(x => x[0] === ai.agentMode) || AGENT_MODES[0])[1]).toLowerCase() : ''}` : 'не настроен';
  // Frank внутри Rack Live выглядит так же, как отдельное приложение /frank: стеклянные круги сверху, плавающая капсула ввода внизу.
  // Отличия (класс inapp): есть кнопка «Закрыть», на телефоне окно во весь экран, на компьютере — скруглённая панель справа
  return <div className={standalone ? 'frank-app' : 'overlay ai-overlay'} onMouseDown={e => onClose && e.target === e.currentTarget && onClose()}>
    <div className={'ai-panel standalone' + (standalone ? '' : ' inapp')}>
      <div className="fr-blur" />
      <div className="fr-top">
        <div className="fr-side">
          {standalone ? null : <button type="button" className="fr-circle" title="Закрыть" aria-label="Закрыть" onClick={onClose}><Icon name="x" size={21} stroke={2.2} /></button>}
          {ai.ready ? <button type="button" className="fr-circle" title={view === 'list' ? 'К разговору' : 'Все разговоры'} onClick={toggleList}>
            <Icon name={view === 'list' ? 'chevronLeft' : 'menu'} size={22} stroke={2} /></button> : null}</div>
        <div className="fr-title"><b>{title}</b><span>{sub}</span></div>
        <div className="fr-side r">
          <button type="button" className="fr-circle eye" title={busy ? busy.stage : 'Провайдер и настройки'} onClick={() => !busy && setMenu('provider')}><FrankEye size={46} mood={frankMood(busy)} round={23} /></button>
          {ai.ready && view !== 'list' && cid && msgs.length ? <button type="button" className="fr-circle" title="Удалить разговор" aria-label="Удалить разговор" onClick={() => del({ id: cid, title: (chats && (chats.find(y => y.id === cid) || {}).title) || (msgs.find(m => m.role === 'user') || {}).text || 'этот разговор' })}><Icon name="trash" size={20} stroke={2} /></button> : null}
          {ai.ready ? <button type="button" className="fr-circle" title="Новый разговор" onClick={() => open(null)}><Icon name="plus" size={22} stroke={2} /></button> : null}
        </div>
      </div>
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
      </div> : <div className="ai-list" ref={listRef} style={{ '--fr-dock-h': dockH + 'px' }}>
        {standalone ? <InstallBanner app="frank" name="Frank" /> : null}
        {!ai.ready ? <div className="ai-empty">
          <FrankEye size={68} />
          <b style={{ fontSize: 17 }}>{ai.keySet && !ai.enabled ? 'Frank выключен' : 'Frank ещё не настроен'}</b>
          <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>{ai.keySet && !ai.enabled
            ? 'Ключ уже сохранён — осталось включить переключатель «Включить Frank» в настройках и нажать «Сохранить».'
            : 'Frank отвечает на вопросы о вашей сети простыми словами: сам смотрит устройства, порты, Wi-Fi, журнал и безопасность. ' +
              'Нужен ключ API одного из сервисов: DeepSeek, Claude, ChatGPT — или своя модель в Ollama.'}</div>
          <Btn kind="primary" icon="settings" onClick={() => setFrSettings(ai.preset || 'deepseek')}>Открыть настройки</Btn>
        </div> : loading ? <div className="dim row" style={{ gap: 8 }}><span className="spin-dot" />Загружаю разговор…</div>
        : !msgs.length ? <div className="ai-empty">
          <FrankEye size={68} />
          <b style={{ fontSize: 17 }}>Привет, я Frank</b>
          <div className="dim" style={{ fontSize: 13.5, lineHeight: 1.5 }}>Я слежу за вашей сетью. Спросите что угодно — сам посмотрю данные Rack Live и отвечу простыми словами. Можно прислать фото или файл (скрепка внизу), попросить «запомни…», а «/» покажет команды.</div>
          <div className="ai-suggest">{AI_SUGGEST.map(s => <button key={s} type="button" className="chip" onClick={() => send(s)}>{s}</button>)}</div>
          <div className="dim3" style={{ fontSize: 11.5, lineHeight: 1.4, maxWidth: 340 }}>Данные сети уходят в {ai.title}; пароли и ключи не передаются. Frank может ошибаться — проверяйте важное.</div>
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
      {menu ? <FrankMenu mode={menu} onClose={() => setMenu('')} onConfigure={id => { setMenu(''); setFrSettings(id || ai.preset); }} /> : null}
      {frSettings ? <div className="fr-settings-overlay" onMouseDown={e => e.target === e.currentTarget && setFrSettings('')}><div className="fr-settings-sheet"><div className="fr-settings-head"><b>Настройки Frank</b><button className="btn sm" onClick={() => setFrSettings('')}>Готово</button></div><AiCard initialPreset={frSettings} compact /></div></div> : null}
      {ai.ready && view === 'chat' ? <div className="fr-dock" ref={dockRef}>
        {quick ? <div className="fr-quick">{AI_SUGGEST.map(s => <button key={s} type="button" onClick={() => { setQuick(false); send(s); }}>{s}</button>)}</div> : null}
        <CmdHint q={q} onPick={c => setQ(c + ' ')} />
        <CtxMeter ctx={ctx} busy={busy} onCompact={() => send('/compact')} />
        <AttachChips files={att} onRemove={dropAtt} />
        <QueueList items={queue} onDrop={i => setQ2(x => x.filter((_, k) => k !== i))} />
        <textarea rows={1} value={q} placeholder={busy ? 'Frank работает — напишите, встанет в очередь' : 'Спросите Frank о сети или введите /'} onChange={e => setQ(e.target.value)} onKeyDown={key}
          onFocus={() => setQuick(false)} onPaste={onPaste} />
        <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
        <div className="fr-dock-row">
          <button type="button" className={'fr-dbtn' + (quick ? ' on' : '')} title="Быстрые вопросы" onClick={() => setQuick(!quick)} disabled={!!busy}><Icon name="plus" size={22} stroke={2} /></button>
          <button type="button" className="fr-dbtn" title="Прикрепить фото или файл" onClick={() => fileRef.current && fileRef.current.click()}><Icon name="clip" size={20} stroke={2} /></button>
          <button type="button" className="fr-model" disabled={!!busy} onClick={() => setMenu('model')} title="Выбрать модель"><b>{ai.title.split(' ')[0]}</b><span>{ai.effModel}</span><Icon name="chevron" size={14} style={{ transform: 'rotate(90deg)' }} /></button>
          <div className="grow" />
          {busy && !(q.trim() || att.length) ? <button type="button" className="fr-send on stop" onClick={stop} title="Остановить Frank"><Icon name="x" size={21} stroke={2.4} /></button>
            : <button type="button" className={'fr-send' + ((q.trim() || att.length) ? ' on' : '')} disabled={!q.trim() && !att.length} onClick={() => send(q)} title={busy ? 'Поставить в очередь' : 'Отправить'}>
              <Icon name={busy ? 'plus' : 'arrowUp'} size={21} stroke={2.4} /></button>}
        </div>
      </div> : null}
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
function AiCard({ initialPreset, compact = false }) {
  const { data, refresh } = useApp(); const toast = useToast();
  const ai = data.ai;
  const [s, setS] = useState(() => ({ enabled: ai.enabled, preset: ai.preset, base: ai.base, model: ai.model, proxy: ai.proxy, limit: ai.limit, key: '', actions: ai.actions !== false, telegram: ai.telegram !== false, admin: !!ai.admin,
    window: ai.window || 0, autoCompact: ai.autoCompact !== false, agent: !!ai.agent, agentMode: ai.agentMode || 'ask', full: !!ai.full, browser: ai.browser !== false }));
  const [res, setRes] = useState(null); const [mem, setMem] = useState(() => new URLSearchParams(location.search).get('memory') === '1');
  useEffect(() => { if (initialPreset && initialPreset !== ai.preset) setS(x => ({ ...x, preset: initialPreset, base: '', model: '', key: '' })); }, [initialPreset]);
  const p = ai.presets.find(x => x.id === s.preset) || ai.presets[0];
  const set = (k, v) => setS(x => ({ ...x, [k]: v }));
  const pick = id => { setS(x => ({ ...x, preset: id, base: '', model: '', key: '' })); setRes(null); };
  const keySaved = (ai.configuredPresets || []).includes(s.preset) || (ai.keySet && s.preset === ai.preset);
  const save = async () => { try { await api('/api/ai', { method: 'PUT', body: s }); toast('Сохранено'); setS(x => ({ ...x, key: '' })); refresh(); } catch (e) { toast(e.message, true); } };
  const test = async () => { setRes(null); try { const r = await api('/api/ai/test', { method: 'POST', body: s }); setRes(r); } catch (e) { setRes({ ok: false, error: e.message }); } };
  const t = ai.today || {};
  return <Card title={<span id="ai-settings" className="row" style={{ gap: 8 }}><FrankEye size={22} round={7} />Frank — помощник (ИИ)</span>} style={{ gridColumn: '1 / -1' }}>
    <div className="notify-grid">
      <div className="col" style={{ gap: 12 }}>
        <div className="row"><Switch on={!!s.enabled} onChange={v => set('enabled', v)} /><div className="grow"><div>Включить Frank</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Кнопка с глазом вверху: вопросы о сети простыми словами.</div></div></div>
        <div className="fr-access"><div style={{fontWeight:600,marginBottom:8}}>Доступ Frank</div>
          <Seg value={s.full ? 'full' : 'normal'} onChange={v => setS(x => ({ ...x, actions: true, admin: v === 'full', agent: true, agentMode: v === 'full' ? 'full' : 'ask', full: v === 'full', browser: true }))}
            options={[{value:'normal',label:'Обычный'},{value:'full',label:'Полный'}]} />
          <div className="dim3" style={{fontSize:12.5,marginTop:8,lineHeight:1.5}}>{s.full ? 'Frank работает с устройствами, файлами и экраном по твоей просьбе. Некоторые опасные действия требуют подтверждения; запрещённые действия остаются недоступны.' : 'Frank смотрит данные и предлагает изменения карточкой для подтверждения.'}</div></div>
        <div className="row"><Switch on={!!s.telegram} onChange={v => set('telegram', v)} /><div className="grow"><div>Отвечать в Telegram</div><div className="dim3" style={{fontSize:12.5}}>Только привязанным аккаунтам.</div></div></div>
        {s.full && ai.full ? <ProjectCard ai={ai} /> : null}
        <div className="row"><span className="ico-circle"><Icon name="brain" size={16} /></span><div className="grow"><div>Память Frank (FRANK.md)</div>
          <div className="dim3" style={{ fontSize: 12.5 }}>Ваши правила и заметки, которые Frank читает в каждом разговоре — как CLAUDE.md у Claude Code. Попросите «запомни…» в разговоре или впишите сами.</div></div>
          <Btn size="sm" onClick={() => setMem(true)}>Открыть</Btn></div>
        {mem ? <MemoryEditor onClose={() => setMem(false)} /> : null}
        <AdviceSettings ai={ai} />
        <Field label="Сервис">
          <div className="row wrap" style={{ gap: 6 }}>{ai.presets.map(x => <button key={x.id} type="button" className={'chip' + (s.preset === x.id ? ' on' : '')} onClick={() => pick(x.id)}>{x.title}</button>)}</div></Field>
        {!p.noKey ? <Field label="Ключ API" hint={p.keyUrl ? <>Получить: <a href={p.keyUrl} target="_blank" rel="noreferrer">{p.keyUrl.replace(/^https:\/\//, '')}</a></> : null}>
          <input className="input" type="password" autoComplete="off" value={s.key} placeholder={keySaved ? '•••••••• (не менять)' : 'sk-…'} onChange={e => set('key', e.target.value)} /></Field> : null}
        <Field label="Модель" hint={s.preset === 'claude' ? 'По умолчанию самая умная; дешевле — claude-sonnet-5-5 или claude-haiku-5-5' : s.preset === 'mozg' ? 'Для управления рабочим столом выберите модель с поддержкой изображений; список зависит от вашей подписки.' : s.preset === 'ollama' ? 'Модель с поддержкой инструментов (tools): qwen2.5, llama3.1 и т.п.' : 'Пусто — модель по умолчанию'}>
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
          <li><b>Mozg AI</b>: в приложении откройте профиль → «API-ключи» → «Создать ключ». Нужна подписка с доступом к API; вставьте ключ сюда, нажмите «Проверить», затем «Сохранить». Для рабочего стола выбирайте модель с поддержкой изображений, например Mozg Black Standard.</li>
          <li><b>Ollama</b> — бесплатно и без отправки данных наружу: модель работает на вашем компьютере (нужна хорошая видеокарта или много памяти).</li>
        </ol></details>
        <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
          <b>Что уходит в сервис:</b> вопрос и данные, которые Frank посмотрел: имена и статусы устройств, порты, клиенты (имена, IP, MAC), журнал, замечания.
          Пароли, ключи, токены и SNMP-community из данных устройств вырезаются до отправки; на снимках экрана видимый текст не скрывается. Ответы стоят денег у провайдера: обычно доли цента (DeepSeek) — несколько центов (Claude, ChatGPT) за вопрос.</div>
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
