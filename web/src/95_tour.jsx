/* Приветственное обучение: the first time (and from Настройки → Основные) Frank walks a new person through the main things.
   The page goes dark with a gradient, only the highlighted element can be pressed, Frank flies to it and points at it with his hand.
   «Пропустить» is always there. Targets are found by data-tour="…" marks put on the real buttons (see 90_app.jsx, 50_devices.jsx, 60_settings.jsx). */
const TOUR_EYE = 'M3 20C8 11 14 7.5 20 7.5S32 11 37 20C32 29 26 32.5 20 32.5S8 29 3 20Z';

/* a cartoon glove, palm at (0,0), fingers toward +x */
function TourHand({ kind }) {
  const f = { fill: '#fff', stroke: '#a9b1c6', strokeWidth: .9 };
  if (kind === 'wave') return <g>
    {[-62, -30, 2, 34].map(a => <rect key={a} x="1" y="-1.9" width={a === 2 ? 11.5 : 10} height="3.8" rx="1.9" transform={`rotate(${a})`} {...f} />)}
    <ellipse cx="-1" cy="0" rx="7" ry="6.4" {...f} /><ellipse cx="-2" cy="-6.6" rx="3.8" ry="2.5" transform="rotate(-18 -2 -6.6)" {...f} /></g>;
  if (kind === 'thumb') return <g>
    <rect x="-2.3" y="-13.5" width="4.8" height="10" rx="2.4" {...f} />
    <ellipse cx="0" cy="0" rx="7.4" ry="6.6" {...f} />
    <path d="M-3 3.4H5M-3 0.2H5" stroke="#a9b1c6" strokeWidth=".8" strokeLinecap="round" /></g>;
  return <g>                                       {/* pointing: the index finger is out, the rest curled */}
    <rect x="3" y="-2.5" width="12.5" height="4.6" rx="2.3" {...f} />
    <ellipse cx="-1" cy="0.4" rx="7" ry="6.4" {...f} />
    <ellipse cx="-2" cy="-6.3" rx="3.7" ry="2.4" transform="rotate(-22 -2 -6.3)" {...f} />
    <ellipse cx="3.6" cy="4.8" rx="3.1" ry="2.2" {...f} /><ellipse cx="0" cy="6.2" rx="3" ry="2.1" {...f} /></g>;
}

/* Frank the eye with arms: `refs` is filled so the animation loop can aim the arm and the pupil without re-rendering */
function FrankHero({ size = 84, still, mode = 'point', refs }) {
  const id = React.useId().replace(/:/g, ''); const r = refs || {};
  return <div className={'tour-frank' + (still ? ' still' : '')} style={{ width: size, height: size }}>
    <svg viewBox="0 0 100 100" width={size} height={size} style={{ overflow: 'visible' }}>
      <defs>
        <radialGradient id={'tfi' + id} cx=".38" cy=".32" r=".75"><stop offset="0" style={{ stopColor: 'var(--frank-iris-0, #8fd0ff)' }} /><stop offset=".5" style={{ stopColor: 'var(--frank-iris-1, #0a84ff)' }} /><stop offset="1" style={{ stopColor: 'var(--frank-iris-2, #0a3a96)' }} /></radialGradient>
        <radialGradient id={'tfg' + id} cx=".5" cy=".5" r=".5"><stop offset="0" style={{ stopColor: 'var(--frank-glow, #0a84ff)' }} stopOpacity=".45" /><stop offset="1" style={{ stopColor: 'var(--frank-glow, #0a84ff)' }} stopOpacity="0" /></radialGradient>
        <clipPath id={'tfc' + id}><path d={TOUR_EYE} /></clipPath>
      </defs>
      <g className="tf-bob">
        <circle cx="50" cy="52" r="58" fill={`url(#tfg${id})`} />
        <g className="tf-arm-b"><path d="M26 60Q8 64 9 84" stroke="#d5dbea" strokeWidth="3.6" fill="none" strokeLinecap="round" />
          <g transform="translate(9 85) rotate(90) scale(1)"><TourHand kind="idle" /></g></g>
        <g ref={e => { r.arm = e; }} transform="translate(50 52) rotate(-42)">
          <g className={mode === 'wave' ? 'tf-wave' : ''}>
            <path ref={e => { r.armPath = e; }} d="M0 0Q26 -7 46 0" stroke="#d5dbea" strokeWidth="3.6" fill="none" strokeLinecap="round" />
            <g ref={e => { r.hand = e; }} transform="translate(50 0)"><g transform="scale(1.15)"><TourHand kind={mode} /></g></g></g></g>
        {THEME.frankAvatar ? <image href={THEME.frankAvatar} x="8" y="10" width="84" height="84" preserveAspectRatio="xMidYMid meet" /> : <g transform="translate(50 52) scale(2.3) translate(-20 -20)">
          <path d={TOUR_EYE} style={{ fill: 'var(--frank-sclera, #f7f9ff)' }} />
          <g clipPath={`url(#tfc${id})`}>
            <g ref={e => { r.look = e; }}><circle cx="20" cy="20" r="8.6" fill={`url(#tfi${id})`} /><circle cx="20" cy="20" r="3.8" style={{ fill: 'var(--frank-pupil, #081020)' }} /><circle cx="22.6" cy="17.4" r="1.6" fill="#fff" /></g>
            <path className="tf-lid" d="M-2 5H42V34H-2Z" style={{ fill: 'var(--frank-lid, #2c2e3c)' }} /></g>
          <path d={TOUR_EYE} fill="none" stroke="#081020" strokeOpacity=".45" strokeWidth=".7" />
          <path d="M8.5 5.6Q20 3.6 31.5 8" stroke="#e4e9ff" strokeWidth="2.4" fill="none" strokeLinecap="round" /></g>}
      </g>
    </svg></div>;
}

const FAST = new URLSearchParams(location.search).get('tourfast') === '1';      // no animation: for screenshots and tests
const gotoTab = id => `[data-tour="tab-${id}"]`;
const TOUR_STEPS = [
  { id: 'hi', hand: 'wave', big: true, title: 'Привет! Я Frank', next: 'Начать',
    text: 'Покажу главное за минуту: как добавить устройства, где карта и настройки. Пока идёт обучение, нажимать можно только подсвеченное — так не потеряетесь. Передумаете — «Пропустить» всегда рядом.' },
  { id: 'devices', t: [gotoTab('tools')], click: true, title: 'Начнём с устройств',
    text: 'Устройство — это роутер, коммутатор, NAS, сервер: всё, с чего Rack Live собирает данные. Они лежат в «Инструментах» (там же плагины и поиск камер). Нажмите «Инструменты».' },
  { id: 'add', t: ['[data-tour="add-dev"]'], click: true, title: 'Добавим первое', text: 'Нажмите «Добавить».' },
  { id: 'detect', t: ['[data-tour="detect-box"]'], inert: true, title: 'Проще всего — по адресу',
    text: 'Впишите адрес устройства, например IP роутера (192.168.1.1), и нажмите «Определить». Rack Live сам поймёт, что это, и подскажет, что делать дальше.' },
  { id: 'catalog', t: ['[data-tour="dev-cat"]'], inert: true, title: 'Или выберите тип вручную', after: () => { const x = document.querySelector('.overlay .modal-head .btn'); x && x.click(); },
    text: 'У каждого типа написано, что он умеет и что нужно подготовить на самом устройстве — включить SNMP, создать пароль приложения и так далее.' },
  { id: 'map', t: [gotoTab('map')], click: true, title: 'Карта сети',
    text: 'Здесь вся сеть одной схемой: что к чему подключено, какой кабель, какая скорость. Карту можно двигать и приближать. Нажмите «Карта».' },
  { id: 'home', t: [gotoTab('rack')], click: true, title: 'Главная', text: 'А это ваша главная: виджеты — шкаф, состояние сети, интернет, ИБП. Вернёмся сюда.' },
  { id: 'edit', t: ['[data-tour="edit-toggle"]', '[data-tour="hdr-more"]'], inert: true, title: 'Редактирование',
    text: 'Тут включается режим редактирования: расставлять виджеты, рисовать шкаф и план, добавлять оборудование. Обычно он выключен, чтобы ничего не сдвинуть случайно. (На телефоне — в меню «⋯».)' },
  { id: 'settings', t: [gotoTab('settings')], click: true, title: 'Настройки', text: 'Уведомления в Telegram, приложения на телефон, защита входа. Нажмите «Настройки».' },
  { id: 'access', t: ['[data-tour="set-access"]'], click: true, title: 'Защита входа',
    text: 'Загляните в «Доступ» и включите двухфакторную защиту — особенно если Rack Live открыт из интернета. Нажмите «Доступ».' },
  { id: 'frank', t: ['[data-tour="frank-btn"]', '[data-tour="hdr-more"]'], inert: true, title: 'А это я 👁',
    text: 'Нажмите на мой глаз в любой момент — отвечу на вопрос о вашей сети: «Всё ли в порядке?», «Почему тормозит Wi-Fi?». Нужен ключ ИИ: Настройки → Frank.' },
  { id: 'end', hand: 'thumb', big: true, title: 'Вот и всё!', next: 'Поехали',
    text: 'Начните с «Инструменты → Устройства → Добавить». Если что-то забудете — я в шапке, а обучение можно повторить: Настройки → Основные → «Показать обучение».' },
];

/* the tour in progress is remembered («step|time»): if the page blinks (reloads, is rebuilt) the tour comes back by itself where it was, for half an hour */
const tourSaved = () => String(lsGet('rl_tour_step', '')).split('|');
const tourResume = () => { const v = tourSaved(); return v[0] !== '' && Date.now() - (+v[1] || 0) < 30 * 60 * 1000; };

function Tour({ onDone }) {
  // the step is remembered (a page reload — iOS likes to unload pages — continues the tour instead of starting it over or losing it)
  const [i, setI] = useState(() => { const q = new URLSearchParams(location.search).get('tourstep'); const n = q != null ? +q : (tourResume() ? +tourSaved()[0] : 0); return n >= 0 && n < TOUR_STEPS.length ? n : 0; });
  const iRef = useRef(i); iRef.current = i;
  const el = useRef({}), fr = useRef({});                                   // DOM nodes and Frank's moving parts, both written to every frame
  const S = useRef({ stepAt: Date.now(), tgt: null, chk: 0, hole: null, card: null, scrolled: false, lost: false });
  const step = TOUR_STEPS[i];
  const [lost, setLost] = useState(false);                                  // the highlighted thing is not on the screen: the tour waits for «Дальше», it never skips on its own
  const lostRef = useRef(setLost); lostRef.current = setLost;
  const log = text => { try { const p = api('/api/tour/log', { method: 'POST', body: { text } }); if (p && p.catch) p.catch(() => { }); } catch (e) { } };   // a line in «События»: why the tour stopped
  const logRef = useRef(log); logRef.current = log;
  const finish = () => { lsSet('rl_tour_step', ''); onDone(); };
  const quit = why => { log(`${why}: шаг ${iRef.current + 1} из ${TOUR_STEPS.length} «${TOUR_STEPS[iRef.current].title || ''}»`); finish(); };
  const quitRef = useRef(quit); quitRef.current = quit;
  const go = d => {
    const n = iRef.current + d, cur = TOUR_STEPS[iRef.current];
    S.current.pass = true;                                                      // Frank's own clicks (closing a window) are not blocked
    try { if (cur.after) cur.after(); const m = document.querySelector('.hdr-menu-wrap'); if (m) m.click(); } catch (e) { }      // an open phone menu «⋯» must never stay over the next step
    S.current.pass = false;
    if (n >= TOUR_STEPS.length) return finish();
    if (n < 0) return;
    iRef.current = n; setI(n); lsSet('rl_tour_step', n + '|' + Date.now());
  };
  const goRef = useRef(go); goRef.current = go;

  useEffect(() => {                                                          // the person presses the highlighted thing → next step once the page has reacted
    // only the highlighted element can be pressed — also while the highlight is still gliding there and other buttons pass under it
    const shield = e => {
      const s = S.current; if (s.pass || (e.target.closest && e.target.closest('.tour-layer'))) return false;
      if (!TOUR_STEPS[iRef.current].inert && s.si === iRef.current && s.tgt && s.tgt.contains(e.target)) return false;      // (a step that has just changed has no target until the next frame — nothing is pressable;
      // an «inert» step only points at the thing: pressing it would open a menu or switch a mode in the middle of the tour)
      e.stopPropagation(); e.preventDefault(); return true;
    };
    const h = e => {
      if (shield(e)) return;
      const st = TOUR_STEPS[iRef.current], s = S.current;
      if (st.click && s.tgt && s.tgt.contains(e.target) && !s.advancing) { s.advancing = true; setTimeout(() => goRef.current(1), st.delay || 420); }      // once, even on a double click
    };
    const k = e => { if (e.key === 'Escape') quitRef.current('закрыто клавишей Esc'); };
    logRef.current(`начато · ${/iPhone|iPad/.test(navigator.userAgent) ? 'iPhone/iPad' : 'компьютер'}${navigator.standalone ? ' (приложение)' : ''} · экран ${innerWidth}×${innerHeight} · шаг ${iRef.current + 1}`);
    document.addEventListener('click', h, true); document.addEventListener('pointerdown', shield, true); document.addEventListener('mousedown', shield, true);
    window.addEventListener('keydown', k);
    document.documentElement.classList.add('tour-on');
    return () => { document.removeEventListener('click', h, true); document.removeEventListener('pointerdown', shield, true); document.removeEventListener('mousedown', shield, true);
      window.removeEventListener('keydown', k); document.documentElement.classList.remove('tour-on'); };
  }, []);

  useEffect(() => {
    let raf; const quick = FAST || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
    const pick = sels => { for (const sel of sels || []) for (const n of document.querySelectorAll(sel)) { if (n.closest('.tour-layer')) continue; const b = n.getBoundingClientRect(); if (b.width > 2 && b.height > 2) return n; } return null; };
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    const frame = t => {
      raf = requestAnimationFrame(frame);
      const st = TOUR_STEPS[iRef.current], s = S.current, e = el.current, vw = innerWidth, vh = innerHeight;
      if (!e.card) return;
      if (s.si !== iRef.current) { Object.assign(s, { si: iRef.current, tgt: null, chk: 0, scrolled: false, lost: false, advancing: false, stepAt: Date.now(), tries: 0, offAt: 0 }); lostRef.current(false); }      // a new step: forget the old target at once
      if (st.t) { if (!s.tgt || !document.contains(s.tgt) || t - s.chk > 200) { s.tgt = pick(st.t); s.chk = t; } } else s.tgt = null;
      // that button is not on this screen: do NOT skip (a skipped step breaks the next ones and the whole tour falls apart) — say so, write it to the journal, let the person press «Дальше»
      const lose = why => { if (s.lost) return; s.lost = true; lostRef.current(true); logRef.current(`${why}: шаг ${iRef.current + 1} «${st.title || ''}» · экран ${vw}×${vh}`); };
      if (st.t && !s.tgt && Date.now() - s.stepAt > 6000) lose('элемент не найден на экране');
      if (s.tgt) {                                          // bring the target into view — down the page AND along a row of chips that scrolls sideways (settings on a phone)
        const b = s.tgt.getBoundingClientRect(), offV = b.top < 70 || b.bottom > vh - 90, offH = b.left < 8 || b.right > vw - 8;
        if (!offV && !offH) s.offAt = 0;
        else if (!s.offAt) s.offAt = t;
        if ((offV || offH) && (!s.scrolled || (t - s.offAt > 700 && s.tries < 3))) {      // once at once, then up to three more times if it is still out of sight
          if (s.scrolled) { s.tries++; s.offAt = t; }
          s.scrolled = true;
          s.tgt.scrollIntoView({ block: offV ? 'center' : 'nearest', inline: offH ? 'center' : 'nearest', behavior: FAST ? 'auto' : 'smooth' });
        }
        if ((offV || offH) && s.scrolled && s.tries >= 3 && t - s.offAt > 900) lose('элемент вне экрана, не прокручивается');      // the page would not scroll to it (it happens in Safari)
      }
      // the hole around the target (a point in the middle of the screen when there is no target) glides toward where the element is now
      let T = { x: vw / 2, y: vh / 2, w: 0, h: 0 };
      if (s.tgt) { const b = s.tgt.getBoundingClientRect(), p = st.pad != null ? st.pad : 8; T = { x: b.left - p, y: b.top - p, w: b.width + p * 2, h: b.height + p * 2 }; }
      const H = s.hole || (s.hole = { x: vw / 2, y: vh / 2, w: 0, h: 0 }), k = quick ? 1 : .2;
      ['x', 'y', 'w', 'h'].forEach(q => { H[q] += (T[q] - H[q]) * k; if (Math.abs(T[q] - H[q]) < .4) H[q] = T[q]; });
      const rx = Math.max(0, Math.min(16, H.w / 2, H.h / 2));
      e.mask.setAttribute('x', H.x); e.mask.setAttribute('y', H.y); e.mask.setAttribute('width', H.w); e.mask.setAttribute('height', H.h); e.mask.setAttribute('rx', rx);
      Object.assign(e.ring.style, { display: s.tgt ? 'block' : 'none', left: H.x + 'px', top: H.y + 'px', width: H.w + 'px', height: H.h + 'px', borderRadius: rx + 'px' });
      const box = (n, x, y, w, h) => Object.assign(n.style, { left: x + 'px', top: y + 'px', width: Math.max(0, w) + 'px', height: Math.max(0, h) + 'px' });
      box(e.bT, 0, 0, vw, H.y); box(e.bB, 0, H.y + H.h, vw, vh - H.y - H.h); box(e.bL, 0, H.y, H.x, H.h); box(e.bR, H.x + H.w, H.y, vw - H.x - H.w, H.h);
      // Frank's card goes below the target (above if there is no room, beside it if it is tall), or to the middle of the screen
      const cw = e.card.offsetWidth, ch = e.card.offsetHeight, fsz = st.big ? 112 : 84;
      let tx = (vw - cw) / 2, ty = (vh - ch) / 2;
      if (s.tgt) {
        const below = T.y + T.h + 24, above = T.y - ch - 24; tx = T.x + T.w / 2 - cw / 2;
        if (below + ch <= vh - 12) ty = below; else if (above >= 12) ty = above;
        else { ty = clamp(T.y + T.h / 2 - ch / 2, 12, vh - ch - 12); tx = T.x + T.w / 2 > vw / 2 ? T.x - cw - 20 : T.x + T.w + 20; }
        tx = clamp(tx, 12, Math.max(12, vw - cw - 12));
      }
      const C = s.card || (s.card = { x: tx, y: vh + 40 });
      C.x += (tx - C.x) * (quick ? 1 : .15); C.y += (ty - C.y) * (quick ? 1 : .15);
      e.card.style.transform = `translate3d(${C.x}px,${C.y}px,0)`;
      // the arm reaches for the nearest point of the highlighted thing, the pupil looks there too
      const f = fr.current; if (!f.arm) return;
      const fx = C.x + fsz / 2, fy = C.y + fsz / 2;
      if (s.tgt) {
        const px = clamp(fx, H.x, H.x + H.w), py = clamp(fy, H.y, H.y + H.h); let dx = px - fx, dy = py - fy; const d = Math.hypot(dx, dy) || 1;
        const u = clamp(d / fsz * 100 - 12, 54, 330), deg = Math.atan2(dy, dx) * 180 / Math.PI;
        f.arm.setAttribute('transform', `translate(50 52) rotate(${deg.toFixed(1)})`); f.armPath.setAttribute('d', `M0 0Q${(u / 2).toFixed(1)} -8 ${(u - 4).toFixed(1)} 0`); f.hand.setAttribute('transform', `translate(${u.toFixed(1)} 0)`);
        f.look.setAttribute('transform', `translate(${(dx / d * 2.6).toFixed(2)} ${(dy / d * 2.2).toFixed(2)})`);
      } else {
        f.arm.setAttribute('transform', 'translate(50 52) rotate(-44)'); f.armPath.setAttribute('d', 'M0 0Q26 -7 46 0'); f.hand.setAttribute('transform', 'translate(50 0)'); f.look.setAttribute('transform', 'translate(0 0)');
      }
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  const fsz = step.big ? 112 : 84, last = i === TOUR_STEPS.length - 1;
  const put = k => n => { el.current[k] = n; };
  return ReactDOM.createPortal(<div className={'tour-layer' + (FAST ? ' tour-fast' : '')}>
    <svg className="tour-dim" width="100%" height="100%">
      <defs>
        <linearGradient id="tourG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#070b22" stopOpacity=".88" /><stop offset=".55" stopColor="#0e0a28" stopOpacity=".86" /><stop offset="1" stopColor="#05121c" stopOpacity=".9" /></linearGradient>
        <radialGradient id="tourB" cx=".12" cy=".08" r=".75"><stop offset="0" stopColor="#0a84ff" stopOpacity=".42" /><stop offset="1" stopColor="#0a84ff" stopOpacity="0" /></radialGradient>
        <radialGradient id="tourP" cx=".92" cy=".95" r=".7"><stop offset="0" stopColor="#bf5af2" stopOpacity=".34" /><stop offset="1" stopColor="#bf5af2" stopOpacity="0" /></radialGradient>
        <mask id="tourM"><rect width="100%" height="100%" fill="#fff" /><rect ref={put('mask')} fill="#000" /></mask>
      </defs>
      <g mask="url(#tourM)"><rect width="100%" height="100%" fill="url(#tourG)" /><rect width="100%" height="100%" fill="url(#tourB)" /><rect width="100%" height="100%" fill="url(#tourP)" /></g>
    </svg>
    {['bT', 'bB', 'bL', 'bR'].map(k => <div key={k} ref={put(k)} className="tour-block" />)}
    <div ref={put('ring')} className="tour-ring" />
    <button type="button" className="tour-skip" onClick={() => quit('пропущено кнопкой «Пропустить обучение»')}>{T('tour.skipAll', 'Пропустить обучение')}<Icon name="x" size={14} stroke={2.4} /></button>
    <div ref={put('card')} className={'tour-card' + (step.t ? '' : ' center') + (step.big ? ' big' : '')}>
      <div className="tour-frank-wrap" style={{ width: fsz, height: fsz }}><FrankHero size={fsz} mode={step.hand || 'point'} refs={fr.current} /></div>
      <div className="tour-bubble" key={i}>
        {step.title ? <b className="tour-title">{T(`tour.${step.id}.title`, step.title)}</b> : null}
        <div className="tour-text">{T(`tour.${step.id}.text`, step.text)}</div>
        {step.click && !lost ? <div className="tour-hint"><i />{T('tour.press', 'Нажмите на подсвеченное')}</div> : null}
        {step.click && lost ? <div className="tour-hint" style={{ color: 'var(--orange)' }}>{T('tour.lost', 'Не вижу эту кнопку на экране — можно перейти дальше.')}</div> : null}
        <div className="tour-actions">
          <div className="tour-dots">{TOUR_STEPS.map((_, k) => <i key={k} className={k === i ? 'on' : k < i ? 'done' : ''} />)}</div>
          <div className="grow" />
          {!last && (!step.click || lost) ? <button type="button" className="tour-link" onClick={() => quit('пропущено кнопкой «Пропустить»')}>{T('tour.skip', 'Пропустить')}</button> : null}
          {!step.click || lost ? <button type="button" className="tour-next" onClick={() => go(1)}>{step.next ? T(`tour.${step.id}.next`, step.next) : T('tour.next', 'Дальше')}</button> : null}
        </div>
      </div>
    </div>
  </div>, document.body);
}
