"""The Telegram bot side of Rack Live: long-polls getUpdates (no public address needed) to
  • link a Telegram account to Rack Live (logged-in admin → «Привязать Telegram» → Start in the bot);
  • log in to the web panel with Telegram (login page → bot asks «это вы?» → yes → the browser is in);
  • answer /start with the user's Telegram ID and how to connect.
Codes are random, single-use and expire in 10 minutes; a login must be confirmed by the same allowed account.
"""
import re, secrets, threading, time, traceback

from . import alerts

CODE_TTL = 600


class TgBot:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.codes = {}                  # code -> {kind, t, ip, ua, status: wait|asked|ok|denied, user, msg}
        self.lock = threading.Lock()
        self.offset, self.username, self.token_seen, self.error = 0, None, None, None
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
                        self.call('setMyCommands', {'commands': [{'command': 'start', 'description': 'Мой ID и как подключиться'}]})
                        self.call('setMyShortDescription', {'short_description': f'Rack Live «{title}»: уведомления о сети и вход в панель'[:120]})
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
            m = re.match(r'(ok|no):(\w+)$', data)
            verdict = 'Код устарел'
            if m:
                with self.lock:
                    c = self.codes.get(m.group(2))
                    if c and c['status'] == 'asked' and c['user'] and c['user']['id'] == user.get('id') and time.time() - c['t'] < CODE_TTL:
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
        if not chat or not text.startswith('/start'):
            if chat and msg.get('chat', {}).get('type') == 'private':
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
        self.say(chat, f'👋 Это бот Rack Live «{title}».\nВаш Telegram ID: {user.get("id")}\n\n'
                       'Чтобы получать уведомления и входить без пароля: войдите в Rack Live → Настройки → Уведомления → «Привязать Telegram».')
