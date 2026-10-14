"""The Telegram bot side of Rack Live: long-polls getUpdates (no public address needed) to
  • link a Telegram account to Rack Live (logged-in admin → «Привязать Telegram» → Start in the bot);
  • log in to the web panel with Telegram (login page → bot asks «это вы?» → yes → the browser is in);
  • answer /start with the user's Telegram ID and how to connect.
Codes are random, single-use and expire in 10 minutes; a login must be confirmed by the same allowed account.
"""
import html, json, os, re, secrets, threading, time, traceback, urllib.error, urllib.request

from . import alerts, assistant

CODE_TTL = 600
FRANK_IDLE = 3 * 3600          # a question after 3 h of silence starts a new conversation with Frank
TG_MAX = 3900                  # Telegram message limit is 4096


def tg_html(md):
    """Frank's short Markdown → Telegram HTML (bold, code, lists, headings)."""
    s = html.escape(md or '', quote=False)
    s = re.sub(r'```[a-zA-Z]*\n?(.*?)```', lambda m: '<pre>' + m.group(1).strip('\n') + '</pre>', s, flags=re.S)
    s = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?m)^#{1,6}\s*(.+)$', r'<b>\1</b>', s)
    s = re.sub(r'(?m)^(\s*)[-*]\s+', r'\1• ', s)
    return s


def split_text(s, n=TG_MAX):
    parts = []
    while len(s) > n:
        cut = s.rfind('\n\n', 0, n)
        cut = cut if cut > n // 3 else s.rfind('\n', 0, n)
        cut = cut if cut > n // 3 else n
        parts.append(s[:cut].rstrip())
        s = s[cut:].lstrip()
    return parts + ([s] if s else [])


class TgBot:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.codes = {}                  # code -> {kind, t, ip, ua, status: wait|asked|ok|denied, user, msg}
        self.lock = threading.Lock()
        self.offset, self.username, self.token_seen, self.error = 0, None, None, None
        self.fchats = self.store._load('tg_frank.json', {})     # Telegram user id → {chat: Frank chat id, t}
        threading.Thread(target=self.loop, daemon=True).start()

    # ── config helpers ──
    def tg(self):
        return alerts.merged(self.store.cfg.get('notify'))['telegram']

    def ready(self):
        t = self.tg()
        return bool(t.get('enabled') and t.get('token'))

    def login_available(self):
        t = self.tg()
        return {'bot': self.username} if self.ready() and self.username and alerts.tg_allowed(t) else None

    def call(self, method, payload, timeout=15):
        t = self.tg()
        req_cfg = {'token': t['token'], 'api': t.get('api')}
        return alerts.Alerter.tg_call(req_cfg, method, payload, timeout=timeout)

    # ── codes (used by the web API) ──
    def new_code(self, kind, ip='', ua=''):
        if not self.ready() or not self.username:
            raise ValueError('Telegram-бот ещё не подключён: сохраните токен в Настройки → Уведомления → Telegram')
        code = re.sub(r'[^A-Za-z0-9]', '', secrets.token_urlsafe(24))[:22]
        with self.lock:
            now = time.time()
            for k in [k for k, v in self.codes.items() if now - v['t'] > CODE_TTL]:
                del self.codes[k]
            if sum(1 for v in self.codes.values() if v['ip'] == ip) > 10:
                raise ValueError('слишком много попыток, подождите несколько минут')
            self.codes[code] = {'kind': kind, 't': now, 'ip': ip, 'ua': ua, 'status': 'wait', 'user': None}
        return code, f'https://t.me/{self.username}?start={kind}_{code}'

    def check(self, code):
        with self.lock:
            c = self.codes.get(code)
            if not c or time.time() - c['t'] > CODE_TTL:
                return None
            return dict(c)

    def consume(self, code):
        with self.lock:
            return self.codes.pop(code, None)

    def ask_mfa(self, ip, ua):
        """second factor: a sign-in whose password was right waits for «да» — the question goes to every allowed account"""
        if not self.ready() or not self.username:
            raise ValueError('Telegram-бот ещё не подключён')
        ids = sorted(alerts.tg_allowed(self.tg()))
        if not ids:
            raise ValueError('нет привязанных аккаунтов Telegram')
        code = re.sub(r'[^A-Za-z0-9]', '', secrets.token_urlsafe(24))[:22]
        with self.lock:
            now = time.time()
            for k in [k for k, v in self.codes.items() if now - v['t'] > CODE_TTL]:
                del self.codes[k]
            self.codes[code] = {'kind': 'mfa', 't': now, 'ip': ip, 'ua': ua, 'status': 'asked', 'user': None, 'ids': ids}
        title = self.store.cfg['settings'].get('title') or 'Rack Live'
        sent = 0
        for i in ids:
            try:
                self.say(i, f'🔐 Вход в Rack Live «{title}» с адреса {ip}' + (f' ({ua})' if ua else '') + '.\nПароль уже введён. Это вы?',
                         [[{'text': '✅ Да, это я', 'callback_data': f'ok:{code}'}, {'text': '🚫 Нет', 'callback_data': f'no:{code}'}]])
                sent += 1
            except ValueError:
                pass
        if not sent:
            raise ValueError('бот не смог написать — откройте его в Telegram и нажмите /start')
        return code

    def notice(self, text):
        """a plain message to every allowed account (a new device signed in…)"""
        if self.ready():
            for i in alerts.tg_allowed(self.tg()):
                try:
                    self.say(i, text)
                except ValueError:
                    pass

    # ── linked accounts ──
    def _ids(self, s):
        return [x.strip() for x in str(s or '').split(',') if x.strip()]

    def link_user(self, user):
        n = alerts.merged(self.store.cfg.get('notify'))
        t, uid = n['telegram'], str(user['id'])
        chats = self._ids(t.get('chat'))
        allowed = self._ids(t.get('allowed')) or [x for x in chats if not x.startswith('-')]   # keep the implicit list explicit
        if uid not in chats:
            chats.append(uid)
        if uid not in allowed:
            allowed.append(uid)
        linked = [x for x in t.get('linked') or [] if str(x.get('id')) != uid]
        linked.append({'id': user['id'], 'name': ' '.join(x for x in (user.get('first_name'), user.get('last_name')) if x),
                       'username': user.get('username') or '', 't': int(time.time())})
        t.update(chat=', '.join(chats), allowed=', '.join(allowed), linked=linked, enabled=True)
        self.store.cfg['notify'] = n
        self.store.save()

    def unlink(self, uid):
        n = alerts.merged(self.store.cfg.get('notify'))
        t, uid = n['telegram'], str(uid)
        t['chat'] = ', '.join(x for x in self._ids(t.get('chat')) if x != uid)
        t['allowed'] = ', '.join(x for x in self._ids(t.get('allowed')) if x != uid)
        t['linked'] = [x for x in t.get('linked') or [] if str(x.get('id')) != uid]
        self.store.cfg['notify'] = n
        self.store.save()

    # ── polling ──
    def loop(self):
        while True:
            try:
                if not self.ready():
                    self.username = None
                    time.sleep(10)
                    continue
                token = self.tg()['token']
                if token != self.token_seen:                       # new bot: who am I, commands, description
                    me = self.call('getMe', {}).get('result') or {}
                    self.username, self.token_seen, self.offset = me.get('username'), token, 0
                    try:
                        title = self.store.cfg['settings'].get('title') or 'Rack Live'
                        self.call('setMyCommands', {'commands': [{'command': 'new', 'description': 'Новый разговор с Frank'},
                                                                 {'command': 'start', 'description': 'Мой ID и как подключиться'}]})
                        self.call('setMyShortDescription', {'short_description': f'Rack Live «{title}»: уведомления, вход в панель и вопросы Frank'[:120]})
                    except ValueError:
                        pass
                r = self.call('getUpdates', {'offset': self.offset, 'timeout': 25, 'allowed_updates': ['message', 'callback_query']}, timeout=40)
                self.error = None
                for u in r.get('result') or []:
                    self.offset = u['update_id'] + 1
                    try:
                        self.handle(u)
                    except Exception:
                        traceback.print_exc()
            except ValueError as e:
                self.error = str(e)
                if 'Conflict' in self.error or '409' in self.error:
                    self.error = 'у бота включён webhook или его опрашивает другая программа — Rack Live не получает сообщения'
                time.sleep(15)
            except Exception:
                traceback.print_exc()
                time.sleep(15)

    def send_avatar(self, chats):
        """The bot's picture as a photo with instructions: forward it to @BotFather (/setuserpic) — the Bot API can't set it itself."""
        web = os.environ.get('RL_WEB', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web'))
        with open(os.path.join(web, 'icon-512.png'), 'rb') as f:
            img = f.read()
        t = self.tg()
        api = (t.get('api') or 'https://api.telegram.org').rstrip('/')
        caption = (f'🖼 Аватар для бота @{self.username}\n\nКак поставить:\n1. Откройте @BotFather\n2. Отправьте /setuserpic\n'
                   f'3. Выберите @{self.username}\n4. Перешлите ему эту картинку')
        for chat in chats:
            b = '----rl' + secrets.token_hex(8)
            body = b''.join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in (('chat_id', chat), ('caption', caption)))
            body += (f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="rack-live-bot.png"\r\n'
                     'Content-Type: image/png\r\n\r\n').encode() + img + f'\r\n--{b}--\r\n'.encode()
            req = urllib.request.Request(f"{api}/bot{t['token']}/sendPhoto", data=body, headers={'Content-Type': f'multipart/form-data; boundary={b}'})
            try:
                urllib.request.urlopen(req, timeout=30).read()
            except urllib.error.HTTPError as e:
                raise ValueError('Telegram не принял картинку: ' + (json.loads(e.read() or b'{}').get('description') or f'HTTP {e.code}'))
            except urllib.error.URLError as e:
                raise ValueError(f'Telegram недоступен ({e.reason})')

    def avatar_once(self, chat):
        """After the first link of each bot: send the avatar once (remembered per bot username)."""
        n = alerts.merged(self.store.cfg.get('notify'))
        if n['telegram'].get('avatarSent') == self.username:
            return
        try:
            self.send_avatar([chat])
        except (ValueError, OSError):
            traceback.print_exc()
            return
        n['telegram']['avatarSent'] = self.username
        self.store.cfg['notify'] = n
        self.store.save()

    # ── Frank in the bot: only linked (allowed) accounts, only in a private chat ──
    def _ai_cfg(self):
        return assistant.public(self.store.cfg.get('ai') or {})

    def frank_ok(self, user):
        c = self._ai_cfg()
        return str(user.get('id')) in alerts.tg_allowed(self.tg()) and c['ready'] and c.get('telegram', True)

    def frank_why(self, user):
        """why a linked account can't ask Frank here (None = not linked, answer as usual)"""
        if str(user.get('id')) not in alerts.tg_allowed(self.tg()):
            return None
        c = self._ai_cfg()
        if not c['ready']:
            return '👁 Frank пока не настроен или выключен: Rack Live → Настройки → Frank (нужен ключ API и тумблер «Включить Frank»).'
        if not c.get('telegram', True):
            return '👁 Вопросы Frank в Telegram выключены: Rack Live → Настройки → Frank → «Отвечать в Telegram».'
        return None

    def _edit(self, chat, mid, text, html_mode=False, buttons=None):
        p = {'chat_id': chat, 'message_id': mid, 'text': text, 'disable_web_page_preview': True}
        if html_mode:
            p['parse_mode'] = 'HTML'
        if buttons is not None:
            p['reply_markup'] = {'inline_keyboard': buttons}
        try:
            self.call('editMessageText', p)
            return True
        except ValueError as e:
            return 'not modified' in str(e)

    def _send_rich(self, chat, md, buttons=None):
        """Markdown answer → one or more messages (HTML, plain text if Telegram rejects the markup); buttons on the last"""
        parts, n = split_text(md), TG_MAX
        while any(len(tg_html(x)) > 4000 for x in parts) and n > 500:      # escaping makes the HTML longer than the text
            n = int(n * .75)
            parts = split_text(md, n)
        for i, part in enumerate(parts):
            p = {'chat_id': chat, 'text': tg_html(part), 'parse_mode': 'HTML', 'disable_web_page_preview': True}
            if buttons and i == len(parts) - 1:
                p['reply_markup'] = {'inline_keyboard': buttons}
            try:
                self.call('sendMessage', p)
            except ValueError:
                p.pop('parse_mode'); p['text'] = part
                self.call('sendMessage', p)

    def frank(self, chat, user, text):
        ai, uid = self.app.ai, str(user['id'])
        cur = self.fchats.get(uid) or {}
        cid = cur.get('chat') if time.time() - cur.get('t', 0) < FRANK_IDLE and ai.chat(cur.get('chat')) else None
        try:
            self.call('sendChatAction', {'chat_id': chat, 'action': 'typing'})
        except ValueError:
            pass
        try:
            job = ai.start(cid, text, src='telegram')
        except assistant.AiError as e:
            self.say(chat, '⚠️ ' + str(e))
            return
        self.fchats[uid] = {'chat': job['chat'], 't': time.time()}
        self.store._dump('tg_frank.json', self.fchats)
        try:
            mid = (self.say(chat, '👁 Думаю…').get('result') or {}).get('message_id')
        except ValueError:
            mid = None
        stage, typed = '', 0
        while not job['done'] and time.time() - job['t'] < 300:
            time.sleep(1.5)
            if time.time() - typed > 4.5:
                typed = time.time()
                try:
                    self.call('sendChatAction', {'chat_id': chat, 'action': 'typing'})
                except ValueError:
                    pass
            if mid and job['stage'] != stage:
                stage = job['stage']
                self._edit(chat, mid, '👁 ' + stage)
        if mid:
            try:
                self.call('deleteMessage', {'chat_id': chat, 'message_id': mid})
            except ValueError:
                pass
        if not job['done']:
            self.say(chat, '⌛ Frank думает слишком долго — ответ появится в приложении Frank, когда будет готов.')
            return
        if job.get('error'):
            self.say(chat, '⚠️ ' + job['error'])
            return
        self._send_rich(chat, job.get('text') or '…')
        ch = ai.chat(job['chat']) or {}
        last = next((m for m in reversed(ch.get('messages') or []) if m['role'] == 'assistant'), {})
        changed = [o for o in last.get('ops') or [] if o.get('kind') != 'read']
        if changed:
            self.say(chat, '⚙️ Frank выполнил:\n' + '\n'.join(
                f"{'✅' if o.get('ok') else '❌'} {o.get('device')}: {(o.get('command') or o.get('label') or '').splitlines()[0][:80]}" for o in changed[:15]))
        for p in [p for p in last.get('proposals') or [] if p['status'] == 'pending']:
            body = f"🛠 Предлагаю: {p['label']}\n{p['deviceName']}" + (f"\n\n{p['text']}" if p.get('text') else '') + \
                   (f"\n\nЗачем: {p['reason']}" if p.get('reason') else '')
            self.say(chat, body, [[{'text': '▶️ Выполнить', 'callback_data': f"fa:{job['chat']}:{p['id']}"},
                                   {'text': 'Не надо', 'callback_data': f"fn:{job['chat']}:{p['id']}"}]])

    def frank_act(self, q, user, cid, pid, run):
        msg = q.get('message') or {}
        chat, mid = (msg.get('chat') or {}).get('id'), msg.get('message_id')
        if str(user.get('id')) not in alerts.tg_allowed(self.tg()):
            self.call('answerCallbackQuery', {'callback_query_id': q['id'], 'text': 'Этот аккаунт не привязан к Rack Live'})
            return
        try:
            self.call('answerCallbackQuery', {'callback_query_id': q['id'], 'text': 'Выполняю…' if run else 'Хорошо, не буду'})
        except ValueError:
            pass
        head = (msg.get('text') or '').split('\n')[0].replace('🛠 Предлагаю: ', '')
        if run and chat and mid:
            self._edit(chat, mid, f'⏳ Выполняю: {head}', buttons=[])
        try:
            p = self.app.ai.act(cid, pid, run)
            text = (f"✅ {p['label']} — {p.get('result') or 'готово'}" if p['status'] == 'done' else
                    f"❌ {p['label']}: {p.get('result')}" if p['status'] == 'error' else f"✖️ Не стал: {p['label']}")
        except assistant.AiError as e:
            text = f'ℹ️ {head}: {e}'
        if chat and mid:
            self._edit(chat, mid, text, buttons=[])

    def say(self, chat, text, buttons=None):
        p = {'chat_id': chat, 'text': text, 'disable_web_page_preview': True}
        if buttons:
            p['reply_markup'] = {'inline_keyboard': buttons}
        return self.call('sendMessage', p)

    def handle(self, u):
        title = self.store.cfg['settings'].get('title') or 'Rack Live'
        if u.get('callback_query'):
            q = u['callback_query']
            data, user = q.get('data') or '', q.get('from') or {}
            fm = re.match(r'f(a|n):(\w+):(\w+)$', data)
            if fm:                                            # «Выполнить / Не надо» under an action Frank proposed
                threading.Thread(target=self.frank_act, args=(q, user, fm.group(2), fm.group(3), fm.group(1) == 'a'), daemon=True).start()
                return
            m = re.match(r'(ok|no):(\w+)$', data)
            verdict = 'Код устарел'
            if m:
                with self.lock:
                    c = self.codes.get(m.group(2))
                    mine = c and ((c['user'] and c['user']['id'] == user.get('id')) or (c['kind'] == 'mfa' and str(user.get('id')) in c.get('ids', [])))
                    if c and c['status'] == 'asked' and mine and time.time() - c['t'] < CODE_TTL:
                        c['user'] = user
                        c['status'] = 'ok' if m.group(1) == 'ok' else 'denied'
                        verdict = '✅ Вход подтверждён — можно вернуться в браузер' if m.group(1) == 'ok' else '🚫 Вход отклонён'
            self.call('answerCallbackQuery', {'callback_query_id': q['id'], 'text': verdict[:190]})
            if q.get('message'):
                try:
                    self.call('editMessageText', {'chat_id': q['message']['chat']['id'], 'message_id': q['message']['message_id'], 'text': verdict})
                except ValueError:
                    pass
            if verdict.startswith('🚫'):
                self.store.add_event(None, 'Вход', 'warning', f'вход через Telegram отклонён владельцем аккаунта {user.get("id")}')
            return
        msg = u.get('message') or {}
        text, user, chat = (msg.get('text') or '').strip(), msg.get('from') or {}, (msg.get('chat') or {}).get('id')
        private = (msg.get('chat') or {}).get('type') == 'private'
        if chat and private and (text == '/new' or (text and not text.startswith('/'))) and self.frank_ok(user):
            if text == '/new':
                self.fchats.pop(str(user['id']), None)
                self.store._dump('tg_frank.json', self.fchats)
                self.say(chat, '👁 Новый разговор. Спрашивайте — например: «Всё ли в порядке с сетью?»')
                return
            threading.Thread(target=self.frank, args=(chat, user, text), daemon=True).start()
            return
        if not chat or not text.startswith('/start'):
            if chat and private:
                if self.frank_why(user):
                    self.say(chat, self.frank_why(user))
                    return
                self.say(chat, f'Я бот Rack Live «{title}». Ваш Telegram ID: {user.get("id")}. Отправьте /start, чтобы узнать, как подключиться.')
            return
        arg = text.split(maxsplit=1)[1] if ' ' in text else ''
        m = re.match(r'(link|login)_(\w+)$', arg)
        c = self.check(m.group(2)) if m else None
        if m and c and c['kind'] == m.group(1):
            if c['kind'] == 'link':
                self.link_user(user)
                with self.lock:
                    if m.group(2) in self.codes:
                        self.codes[m.group(2)].update(status='ok', user=user)
                self.store.add_event(None, 'Telegram', 'info', f'привязан аккаунт {user.get("first_name", "")} (id {user.get("id")})')
                self.say(chat, f'✅ Telegram привязан к Rack Live «{title}».\nСюда будут приходить уведомления, а войти в панель можно кнопкой «Войти через Telegram».')
                self.avatar_once(chat)
                return
            if str(user.get('id')) not in alerts.tg_allowed(self.tg()):
                with self.lock:
                    if m.group(2) in self.codes:
                        self.codes[m.group(2)]['status'] = 'denied'
                self.store.add_event(None, 'Вход', 'warning', f'вход через Telegram: аккаунт {user.get("id")} не привязан')
                self.say(chat, f'⛔ Ваш аккаунт (ID {user.get("id")}) не привязан к Rack Live «{title}».\n'
                               'Войдите в панель по паролю и нажмите «Привязать Telegram» в Настройки → Уведомления.')
                return
            with self.lock:
                if m.group(2) in self.codes:
                    self.codes[m.group(2)].update(status='asked', user=user)
            where = f"с адреса {c['ip']}" + (f" ({c['ua']})" if c.get('ua') else '')
            self.say(chat, f'🔐 Вход в Rack Live «{title}» {where}.\nЭто вы?',
                     [[{'text': '✅ Да, войти', 'callback_data': f'ok:{m.group(2)}'}, {'text': '🚫 Нет', 'callback_data': f'no:{m.group(2)}'}]])
            return
        if m:
            self.say(chat, 'Ссылка устарела — нажмите кнопку в Rack Live ещё раз.')
            return
        if str(user.get('id')) in alerts.tg_allowed(self.tg()):
            self.say(chat, f'👋 Это бот Rack Live «{title}». Ваш аккаунт привязан: сюда приходят уведомления.\n\n' +
                     ('👁 Напишите вопрос о сети — ответит Frank. Например: «Всё ли в порядке?» или «Почему тормозит Wi-Fi на кухне?»\n'
                      '/new — начать новый разговор.' if self.frank_ok(user) else (self.frank_why(user) or '')))
            return
        self.say(chat, f'👋 Это бот Rack Live «{title}».\nВаш Telegram ID: {user.get("id")}\n\n'
                       'Чтобы получать уведомления и входить без пароля: войдите в Rack Live → Настройки → Уведомления → «Привязать Telegram».')
