/* ───────── «Обучение»: интерактивные уроки и игры (rackd/learn.py) ─────────
   «Академия сетей» встроена; остальное лежит в публичном каталоге на GitHub — видно список, нужное скачивается. Модуль показывается в изолированном окне
   (iframe sandbox + CSP без сети) и умеет только сохранять свой прогресс через мост postMessage. У каждого модуля своя страница /learn/<id>, которую можно
   открыть отдельно и поставить как приложение (PWA). Backend: /api/learn*, /api/learn/f/<id>/…, /learn/<id> */
const LEARN_TAGS = { course: 'курс', game: 'игра', manual: 'мануал', trainer: 'тренажёр' };
const fmtKB = n => n >= 1e6 ? (n / 1e6).toFixed(1) + ' МБ' : Math.max(1, Math.round(n / 1e3)) + ' КБ';

function LearnTool() {
  const toast = useToast(); const confirm = useConfirm();
  const [data, setData] = useState(null); const [cat, setCat] = useState(null); const [busy, setBusy] = useState('');
  const load = async () => { try { setData(await api('/api/learn')); } catch (x) { setData({ modules: [], error: x.message }); } };
  const loadCat = async force => { setCat(null); try { setCat(await api('/api/learn/catalog' + (force ? '?force=1' : ''))); } catch (x) { setCat({ ok: false, modules: [], error: x.message }); } };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (data && data.canManage && !cat) loadCat(false); }, [data && data.canManage]);
  const get = async m => {
    setBusy(m.id);
    try { await api('/api/learn/install', { method: 'POST', body: { id: m.id } }); toast(m.update ? 'Обновлено' : 'Скачано'); await load(); await loadCat(true); }
    catch (x) { toast(x.message, true); } finally { setBusy(''); }
  };
  const remove = async m => {
    if (!await confirm(`Удалить «${m.title}»? Ваш прогресс сохранится: при повторном скачивании он вернётся.`, { title: 'Удалить модуль', ok: 'Удалить', danger: true })) return;
    setBusy(m.id);
    try { await api('/api/learn/remove', { method: 'POST', body: { id: m.id } }); toast('Удалено'); await load(); await loadCat(true); }
    catch (x) { toast(x.message, true); } finally { setBusy(''); }
  };
  if (!data) return <div className="dim" style={{ padding: 20, textAlign: 'center' }}>Загружаю…</div>;
  const avail = cat && cat.ok ? cat.modules.filter(m => !m.builtin && (!m.installed || m.update)) : [];
  const upd = {}; (cat && cat.ok ? cat.modules : []).forEach(m => { if (m.update) upd[m.id] = true; });
  return <div className="col" style={{ gap: 14 }}>
    <div className="dim" style={{ fontSize: 13, lineHeight: 1.55 }}>Интерактивные уроки и игры про сети: теория, практика и проверка. Каждый модуль открывается на своей странице — её можно поставить на телефон или компьютер как отдельное приложение. Прогресс хранится в Rack Live.</div>
    {data.error ? <div className="cam-warn">{data.error}</div> : null}
    <b style={{ fontSize: 15 }}>Мои модули</b>
    {!data.modules.length ? <div className="dim" style={{ fontSize: 13 }}>Пока ничего нет.</div>
      : data.modules.map(m => <div key={m.id} className="plug-row" style={{ cursor: 'default' }}>
        <a className="row grow" style={{ gap: 12, textAlign: 'left', color: 'inherit', minWidth: 0, textDecoration: 'none' }} href={'/learn/' + m.id + '?back=1'}>
          <span className="ico-circle"><Icon name="bulb" size={16} /></span>
          <span className="grow" style={{ minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{m.title}</b>
            <small>{LEARN_TAGS[m.tag] || 'курс'} · версия {m.version}{m.builtin ? ' · встроено' : ''}{upd[m.id] ? ' · есть обновление' : ''}</small>
            {m.description ? <small className="dim" style={{ display: 'block', marginTop: 2 }}>{m.description}</small> : null}</span></a>
        {!m.builtin && data.canManage ? <Btn disabled={!!busy} busy={busy === m.id} onClick={() => remove(m)}>Удалить</Btn> : null}
        <a className="btn primary" href={'/learn/' + m.id + '?back=1'}>Открыть</a></div>)}
    {data.canManage ? <>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}><b style={{ fontSize: 15 }}>Каталог</b><span className="grow" />
        <Btn disabled={!cat} onClick={() => loadCat(true)}>Обновить список</Btn></div>
      <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>Новые материалы публикуются на GitHub ({data.repo}). Здесь видно, что доступно: скачайте нужное — оно появится в «Моих модулях». Скачивается только содержимое модуля; он работает в изолированном окне и ничего не может в самом Rack Live.</div>
      {!cat ? <div className="dim" style={{ fontSize: 13 }}>Проверяю каталог…</div>
        : !cat.ok ? <div className="cam-warn">{cat.error || 'Каталог сейчас недоступен.'}</div>
        : !avail.length ? <div className="dim" style={{ fontSize: 13 }}>{cat.modules.length ? 'Всё из каталога уже скачано, обновлений нет.' : 'В каталоге пока ничего нет — загляните позже.'}</div>
        : avail.map(m => <div key={m.id} className="plug-row" style={{ cursor: 'default' }}>
          <span className="ico-circle"><Icon name="bulb" size={16} /></span>
          <span className="grow" style={{ minWidth: 0 }}><b className="ellipsis" style={{ display: 'block' }}>{m.title}{m.new ? <span className="badge" style={{ marginLeft: 6 }}>новое</span> : null}</b>
            <small>{LEARN_TAGS[m.tag] || 'курс'} · версия {m.version} · {fmtKB(m.size)}{m.author ? ' · ' + m.author : ''}</small>
            {m.description ? <small className="dim" style={{ display: 'block', marginTop: 2 }}>{m.description}</small> : null}</span>
          <Btn kind="primary" disabled={!!busy} busy={busy === m.id} onClick={() => get(m)}>{m.update ? 'Обновить' : 'Скачать'}</Btn></div>)}
    </> : null}
  </div>;
}
