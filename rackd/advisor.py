"""Советы Frank: every few days Frank reviews the network like an experienced administrator and writes down what he would add, what he does not like
and what he would change in your place. The result lives in data/advice.json and in the «Советы Frank» widget on the home page.

It is the same assistant (assistant.ask, read-only tools, your own key). No actions, nothing is changed. Frank must answer with a JSON list, which is parsed
strictly; answers that are not JSON are kept as an error, never shown half-broken. Tips you dismissed or marked as done are not repeated."""
import json, re, secrets, threading, time

from . import assistant

DEFAULT = {'on': True, 'days': 3, 'telegram': False}
FIRST_DELAY = 600                 # seconds after the start before the first review (the devices must have been polled)
MANUAL_COOLDOWN = 1800            # «Обновить сейчас» at most once per half hour
KINDS = ('add', 'dislike', 'idea')

PROMPT = """Сделай регулярную ревизию моей сети как опытный сетевой администратор и дай мне советы.
Посмотри данные инструментами (начни с network_overview, потом network_health, security_findings, availability, speed_tests, events, topology — сколько нужно).
Затем верни ТОЛЬКО JSON — массив из 5–7 объектов, без текста до и после, без ```:
[{"kind": "add" | "dislike" | "idea", "title": "...", "text": "...", "prio": 1 | 2 | 3, "ask": "..."}]
- kind «add» — что ДОБАВИТЬ в сеть (оборудование, защита, резервирование, мониторинг); «dislike» — что тебе НЕ НРАВИТСЯ в сети сейчас; «idea» — какие доработки
  и новшества ты внедрил бы на моём месте (в сети или в самом Rack Live). Раздели советы примерно поровну между тремя видами.
- title — до 60 символов, по-русски, суть или действие («Поставить ИБП на коммутатор»).
- text — 1–3 предложения простыми словами: что именно, почему это важно и с чего начать (где в Rack Live или на устройстве).
- prio — 1 важно сейчас, 2 стоит сделать, 3 на будущее.
- ask — короткий вопрос тебе (Frank), чтобы я мог продолжить разговор («Как включить защиту от петель?»).
Только по реальным данным: названия устройств, номера портов, цифры. Ничего не выдумывай; если всё хорошо — предлагай развитие.
Уже было, не повторяй: {old}
Я отклонил или сделал: {closed}"""

SAMPLE = [  # shown in the demo (no key there)
    {'kind': 'add', 'prio': 1, 'title': 'Подключить ИБП к коммутатору ядра', 'ask': 'Как подключить ИБП и на сколько хватит батареи?',
     'text': 'Коммутатор — единая точка отказа: при его сбое пропадут 18 из 21 устройств. ИБП даст время, чтобы всё выключилось штатно.'},
    {'kind': 'dislike', 'prio': 1, 'title': 'Порт 11: кабель с ошибками', 'ask': 'Что делать с ошибками на порту 11?',
     'text': 'Порт 11 за сутки набрал больше 3 000 ошибок CRC — кабель плохо обжат или перегнут. Откройте карточку порта и нажмите «Проверить кабель».'},
    {'kind': 'idea', 'prio': 2, 'title': 'Включить защиту от петель', 'ask': 'Расскажи про защиту от петель и как её включить',
     'text': 'Один случайно воткнутый кабель — и сеть встанет. Коммутатор умеет сам отключать такой порт; это включается одной кнопкой в его карточке.'},
    {'kind': 'add', 'prio': 2, 'title': 'Второй канал интернета', 'ask': 'Какой запасной интернет лучше поставить?',
     'text': 'Сейчас интернет идёт только через один кабель провайдера. USB-модем с SIM на гостевом роутере уже есть — его можно сделать резервным каналом.'},
    {'kind': 'idea', 'prio': 3, 'title': 'Отдельная сеть для гостей', 'ask': 'Как разделить гостей и домашние устройства?',
     'text': 'Гостевой Wi-Fi в отдельной сети (VLAN) не даст чужим телефонам видеть ваш NAS и камеры.'},
]


def _norm(s):
    return re.sub(r'[^a-zа-я0-9]+', ' ', str(s or '').lower()).strip()


def parse(text):
    """Frank's answer → list of tips; raises ValueError when it is not the JSON list that was asked for"""
    t = (text or '').strip()
    a, b = t.find('['), t.rfind(']')
    if a < 0 or b <= a:
        raise ValueError('Frank ответил не списком')
    try:
        raw = json.loads(t[a:b + 1])
    except ValueError:
        raise ValueError('Frank ответил не в том формате')
    out = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict) or not str(x.get('title') or '').strip() or not str(x.get('text') or '').strip():
            continue
        kind = x.get('kind') if x.get('kind') in KINDS else 'idea'
        try:
            prio = max(1, min(3, int(x.get('prio') or 2)))
        except (TypeError, ValueError):
            prio = 2
        out.append({'kind': kind, 'prio': prio, 'title': str(x['title']).strip()[:80], 'text': str(x['text']).strip()[:600],
                    'ask': str(x.get('ask') or '').strip()[:200]})
    if not out:
        raise ValueError('в ответе Frank нет ни одного совета')
    return out[:8]


class Advisor:
    def __init__(self, app, demo=False):
        self.app, self.store, self.demo = app, app.store, demo
        self.d = self.store._load('advice.json', {})              # {items: [...], last, raw, error, closed: [titles]}
        self.d.setdefault('items', [])
        self.d.setdefault('closed', [])
        self.running = False
        if demo and not self.d['items']:
            now = time.time()
            self.d.update(items=[dict(x, id='demo' + str(i), state='new', t=now) for i, x in enumerate(SAMPLE)], last=now - 86400)

    # ── settings ──
    def cfg(self):
        return dict(DEFAULT, **(self.store.cfg.get('advisor') or {}))

    def set_cfg(self, body):
        c = dict(self.store.cfg.get('advisor') or {})
        if 'on' in body:
            c['on'] = bool(body['on'])
        if 'telegram' in body:
            c['telegram'] = bool(body['telegram'])
        if 'days' in body:
            c['days'] = max(1, min(30, int(body['days'])))
        self.store.cfg['advisor'] = c
        self.store.save()

    def ready(self):
        return bool(assistant.public(self.store.cfg.get('ai') or {})['ready'])

    # ── schedule ──
    def due(self):
        c = self.cfg()
        if self.demo or not c['on'] or self.running or not self.ready():
            return False
        return time.time() - (self.d.get('last') or 0) >= c['days'] * 86400

    def start(self, manual=False):
        """→ (started, why-not)"""
        if self.running:
            return False, 'Frank уже готовит советы'
        if not self.ready():
            return False, 'Frank не настроен или выключен — Настройки → Frank'
        if manual and time.time() - (self.d.get('last') or 0) < MANUAL_COOLDOWN and self.d.get('items') and not self.d.get('error'):
            return False, 'Советы только что обновлялись — следующий раз можно через полчаса'
        self.running = True
        self.d['error'] = None
        self.store.bump()
        threading.Thread(target=self.run, daemon=True).start()
        return True, ''

    def run(self):
        try:
            old = [x['title'] for x in self.d['items'][-12:]]
            closed = self.d['closed'][-20:]
            prompt = PROMPT.replace('{old}', '; '.join(old) or 'ничего').replace('{closed}', '; '.join(closed) or 'ничего')
            c = dict(self.store.cfg.get('ai') or {}, actions=False, admin=False)          # read only, no actions
            res = assistant.ask(self.app, c, [{'role': 'user', 'text': prompt}])
            self.app.ai._count(res['usage'])
            tips = parse(res['text'])
            skip = {_norm(t) for t in closed}
            now = time.time()
            fresh = [dict(x, id=secrets.token_hex(4), state='new', t=now) for x in tips if _norm(x['title']) not in skip]
            keep = [x for x in self.d['items'] if x.get('state') == 'new' and now - x['t'] < 14 * 86400]     # old unread tips fade after two weeks
            self.d.update(items=(fresh + keep)[-30:], last=now, error=None, raw='')
            self.store.add_event(None, 'Frank', 'info', f'подготовил советы по сети ({len(fresh)})')
            if self.cfg().get('telegram') and fresh:
                self.app.tgbot.notice('👁 Frank подготовил советы по вашей сети:\n' + '\n'.join('• ' + x['title'] for x in sorted(fresh, key=lambda x: x['prio'])[:4]))
        except Exception as e:
            self.d['error'] = str(e) if isinstance(e, (assistant.AiError, ValueError)) else f'{type(e).__name__}: {e}'
            self.d['last'] = time.time() - (self.cfg()['days'] * 86400 - 6 * 3600)           # a failed try repeats in about six hours, not in the next ten seconds
        finally:
            self.running = False
            self.store._dump('advice.json', self.d)
            self.store.bump()

    # ── what the widget sees ──
    def public(self):
        c = self.cfg()
        items = sorted((x for x in self.d['items'] if x.get('state') == 'new'), key=lambda x: (x['prio'], -x['t']))
        last = self.d.get('last') or 0
        return {'items': [{k: x[k] for k in ('id', 'kind', 'prio', 'title', 'text', 'ask', 't')} for x in items[:12]], 'last': last or None,
                'next': (last + c['days'] * 86400) if last else None, 'running': self.running, 'error': self.d.get('error'),
                'on': c['on'], 'days': c['days'], 'telegram': c['telegram'], 'ready': self.ready() or self.demo}

    def close(self, tid, done=False):
        for x in self.d['items']:
            if x['id'] == tid and x.get('state') == 'new':
                x['state'] = 'done' if done else 'dismissed'
                self.d['closed'] = (self.d['closed'] + [x['title']])[-60:]
                break
        self.store._dump('advice.json', self.d)
        self.store.bump()
