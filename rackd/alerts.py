"""Notifications: rules evaluated over the live device states, sent to Telegram / e-mail / a webhook.

A problem must hold for its rule's delay before it is sent (no flapping), a recovery message follows when it clears,
everything that fires in one evaluation goes out as one message, and active alerts survive a restart (no re-send).
"""
import base64, copy, hashlib, hmac, json, smtplib, ssl, threading, time, urllib.request
from urllib.parse import parse_qsl, urlencode
from email.mime.text import MIMEText

DEFAULT_NOTIFY = {
    # webapp: public https address of Rack Live → bot menu button + «Открыть» under alerts; allowed: who may log in from Telegram
    'telegram': {'enabled': False, 'token': '', 'chat': '', 'api': '', 'webapp': '', 'allowed': '', 'linked': [], 'avatarSent': ''},
    'email': {'enabled': False, 'host': '', 'port': '587', 'user': '', 'password': '', 'from': '', 'to': '', 'tls': True},
    'webhook': {'enabled': False, 'url': ''},
    'url': '',
    'rules': {
        'offline': {'on': True, 'minutes': 2},
        'warning': {'on': False, 'minutes': 5},
        'disk': {'on': True, 'pct': 90},
        'temp': {'on': True, 'c': 70, 'disk': 55},
        'cpu': {'on': False, 'pct': 90, 'minutes': 10},
        'ups': {'on': True},
        'cert': {'on': True, 'days': 14},
        'vpn': {'on': True, 'minutes': 3},
        'speed': {'on': True, 'minutes': 5},
        'errors': {'on': True, 'count': 50},
        'security': {'on': True},
    },
}
SECRETS = (('telegram', 'token'), ('email', 'password'))


def merged(cfg_notify):
    """Defaults + saved values, so new rules appear for old configs."""
    n = copy.deepcopy(DEFAULT_NOTIFY)
    for k, v in (cfg_notify or {}).items():
        if isinstance(v, dict) and isinstance(n.get(k), dict):
            for kk, vv in v.items():
                if isinstance(vv, dict) and isinstance(n[k].get(kk), dict):
                    n[k][kk].update(vv)
                else:
                    n[k][kk] = vv
        else:
            n[k] = v
    return n


def public(cfg_notify):
    """Settings for the browser: secrets replaced by a flag."""
    n = merged(cfg_notify)
    for ch, key in SECRETS:
        n[ch][key + 'Set'] = bool(n[ch].get(key))
        n[ch][key] = ''
    return n


def tg_allowed(tg):
    """Telegram accounts allowed into the mini app: the explicit list, else the personal chat ids alerts go to."""
    src = tg.get('allowed') or tg.get('chat') or ''
    return {x.strip() for x in str(src).split(',') if x.strip() and not x.strip().startswith('-')}


def verify_webapp(cfg_notify, init_data, max_age=86400):
    """Check Telegram mini-app launch data (HMAC with the bot token) → (user, '') or (None, why)."""
    tg = merged(cfg_notify)['telegram']
    if not tg.get('enabled') or not tg.get('token'):
        return None, 'вход через Telegram не настроен (Настройки → Уведомления → Telegram)'
    pairs = dict(parse_qsl(init_data or '', keep_blank_values=True))
    sign = pairs.pop('hash', None)
    if not sign:
        return None, 'нет подписи Telegram — откройте панель кнопкой в боте'
    check = '\n'.join(f'{k}={v}' for k, v in sorted(pairs.items()))
    secret = hmac.new(b'WebAppData', tg['token'].encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), sign):
        return None, 'подпись Telegram не сошлась (другой бот или токен изменён)'
    try:
        if time.time() - int(pairs.get('auth_date') or 0) > max_age:
            return None, 'данные входа устарели — закройте и откройте панель заново'
        user = json.loads(pairs.get('user') or '{}')
    except ValueError:
        return None, 'не удалось прочитать данные Telegram'
    if str(user.get('id')) not in tg_allowed(tg):
        return None, f"аккаунт Telegram {user.get('id')} не в списке разрешённых"
    return user, ''


def fmt_min(sec):
    m = int(sec // 60)
    return f'{m // 60} ч {m % 60} мин' if m >= 60 else f'{max(1, m)} мин'


class Alerter:
    def __init__(self, store):
        self.store = store
        saved = store._load('alerts.json', {})
        self.active = saved.get('active', {})      # key -> {since, sent, text, dev}
        self.base = saved.get('base', {})          # "dev:port" -> best link speed seen
        self.status = {}                           # channel -> last result
        self.started = time.time()
        self.lock = threading.Lock()
        self.base_dirty = False

    def cfg(self):
        return merged(self.store.cfg.get('notify'))

    def _persist(self):
        self.store._dump('alerts.json', {'active': self.active, 'base': self.base})

    # ── rules → current problems {key: (hold_seconds, text_on, text_off, device_id)} ──
    def conditions(self, devices, states):
        r = self.cfg()['rules']
        out = {}
        for d in devices:
            if not d.get('enabled', True) or d.get('notify') is False:
                continue
            st = states.get(d['id']) or {}
            if not st.get('updated'):
                continue
            name, did = d.get('name') or d.get('host'), d['id']
            s = st.get('summary') or {}
            if r['offline']['on'] and st.get('status') == 'offline':
                out[f'{did}:offline'] = (r['offline']['minutes'] * 60, f'🔴 {name}: нет связи' + (f" — {st['error']}" if st.get('error') else ''),
                                         f'🟢 {name}: снова в сети', did)
                continue                                     # nothing else is meaningful while it is unreachable
            if r['warning']['on'] and st.get('status') == 'warning':
                why = ', '.join(f"{m['label']}: {m['value']}{(' ' + m['unit']) if m.get('unit') else ''}" for m in st.get('metrics') or [] if m.get('level'))
                out[f'{did}:warning'] = (r['warning']['minutes'] * 60, f'🟠 {name}: требует внимания' + (f' — {why}' if why else ''),
                                         f'🟢 {name}: снова в норме', did)
            if r['disk']['on']:
                for v in (st.get('storage') or {}).get('volumes') or []:
                    if v.get('total') and v['used'] / v['total'] * 100 >= r['disk']['pct']:
                        out[f"{did}:disk:{v['name']}"] = (60, f"💾 {name}: том {v['name']} заполнен на {round(v['used'] / v['total'] * 100)}%",
                                                          f"✅ {name}: на томе {v['name']} снова есть место", did)
            if r['temp']['on']:
                if isinstance(s.get('temp'), (int, float)) and s['temp'] >= r['temp']['c']:
                    out[f'{did}:temp'] = (180, f"🌡 {name}: температура {s['temp']} °C", f'✅ {name}: температура в норме', did)
                for dk in (st.get('storage') or {}).get('disks') or []:
                    if isinstance(dk.get('temp'), (int, float)) and dk['temp'] >= r['temp']['disk']:
                        out[f"{did}:dtemp:{dk.get('name')}"] = (300, f"🌡 {name}: диск {dk.get('name')} нагрелся до {dk['temp']} °C",
                                                                f"✅ {name}: диск {dk.get('name')} остыл", did)
            if r['cpu']['on'] and isinstance(s.get('cpu'), (int, float)) and s['cpu'] >= r['cpu']['pct']:
                out[f'{did}:cpu'] = (r['cpu']['minutes'] * 60, f"⚙️ {name}: процессор загружен на {round(s['cpu'])}%", f'✅ {name}: нагрузка процессора спала', did)
            u = st.get('ups')
            if r['ups']['on'] and u:
                if u.get('onBattery'):
                    left = f", хватит примерно на {u['runtimeMin']} мин" if u.get('runtimeMin') else ''
                    out[f'{did}:ups:bat'] = (0, f'🔋 {name}: пропало питание, ИБП работает от батареи{left}', f'🔌 {name}: питание восстановлено', did)
                if u.get('lowBattery'):
                    out[f'{did}:ups:low'] = (0, f'🪫 {name}: батарея ИБП почти разряжена!', f'✅ {name}: батарея ИБП больше не на исходе', did)
                if u.get('replace'):
                    out[f'{did}:ups:replace'] = (0, f'🔧 {name}: ИБП просит заменить аккумулятор', f'✅ {name}: аккумулятор ИБП в порядке', did)
            if r['cert']['on']:
                for m in st.get('metrics') or []:
                    if m.get('label') == 'Сертификат' and isinstance(m.get('value'), (int, float)) and m['value'] <= r['cert']['days']:
                        out[f'{did}:cert'] = (0, f"🔐 {name}: сертификат истекает через {m['value']} дн.", f'✅ {name}: сертификат обновлён', did)
            if r['vpn']['on']:
                for t in st.get('vpn') or []:
                    if t.get('role') == 'client' and t.get('routing') and not t.get('up'):
                        out[f"{did}:vpn:{t['id']}"] = (r['vpn']['minutes'] * 60, f"🛡 {name}: VPN «{t['name']}» не поднят — трафик идёт в обход",
                                                       f"✅ {name}: VPN «{t['name']}» снова работает", did)
            if r['errors']['on']:
                for p in st.get('ports') or []:
                    if (p.get('errHour') or 0) >= max(1, r['errors']['count']):
                        lbl = f" ({p['label']})" if p.get('label') else ''
                        out[f"{did}:err:{p['n']}"] = (0, f"⚠️ {name}: порт {p['n']}{lbl} — {p['errHour']} ошибок передачи за час. "
                                                          f"Обычно это кабель, разъём или помехи — проверьте кабель",
                                                       f"✅ {name}: порт {p['n']}{lbl} — ошибки прекратились", did)
            if r['speed']['on']:
                for p in st.get('ports') or []:
                    if not p.get('link') or not p.get('speed') or p.get('kind') == 'wan':
                        continue
                    k, key = f"{did}:{p['n']}", f"{did}:speed:{p['n']}"
                    best = self.base.get(k, 0)
                    old = self.active.get(key)
                    if old and time.time() - old['since'] > 86400:   # a slower device on this port for a day = the new normal
                        self.base[k], old['silent'] = p['speed'], True
                        self.base_dirty = True
                        continue
                    if p['speed'] > best:
                        self.base[k] = p['speed']
                        self.base_dirty = True
                    elif best >= 1000 and p['speed'] < best:
                        lbl = f" ({p['label']})" if p.get('label') else ''
                        out[f"{did}:speed:{p['n']}"] = (r['speed']['minutes'] * 60,
                                                        f"🐢 {name}: порт {p['n']}{lbl} работает на {p['speed']} Мбит/с вместо {best} — проверьте кабель и разъёмы",
                                                        f"✅ {name}: порт {p['n']}{lbl} снова на {best} Мбит/с", did)
        return out

    def security_conditions(self, devices, states):
        """Critical security findings (an open telnet, a dangerous forwarded port…) — once when they appear."""
        from . import security
        if not self.cfg()['rules']['security']['on']:
            return {}
        res = security.audit(devices, states, None, (self.store.cfg.get('security') or {}).get('ignored'))
        return {f"sec:{f['id']}": (0, f"🛡 Безопасность: {f['title']}", f"✅ Исправлено: {f['title']}", f.get('deviceId'))
                for f in res['findings'] if f['level'] == 'bad'}

    def evaluate(self, devices, states):
        if time.time() - self.started < 60:                  # let every device be polled once after a start
            return
        with self.lock:
            now, msgs, devs, changed = time.time(), [], [], False
            self.base_dirty = False
            cur = self.conditions(devices, states)
            try:
                cur.update(self.security_conditions(devices, states))
            except Exception:
                pass
            changed = self.base_dirty
            for key, (hold, on, off, did) in cur.items():
                a = self.active.get(key)
                if not a:
                    self.active[key] = a = {'since': now, 'sent': False, 'off': off, 'dev': did}
                    changed = True
                a['off'] = off
                if not a['sent'] and now - a['since'] >= hold:
                    a['sent'], a['text'] = True, on
                    msgs.append(on)
                    devs.append(did)
                    changed = True
            for key in [k for k in self.active if k not in cur]:
                a = self.active.pop(key)
                changed = True
                if a.get('sent') and not a.get('silent'):
                    msgs.append(a.get('off', '✅ проблема ушла') + f" (длилось {fmt_min(now - a['since'])})")
                    devs.append(a.get('dev'))
            if changed:
                self._persist()
        if msgs:
            threading.Thread(target=self.send, args=(msgs, None, devs[0] if len(set(devs)) == 1 else None), daemon=True).start()

    # ── channels ──
    def send(self, lines, cfg=None, dev=None):
        c = cfg or self.cfg()
        site = self.store.cfg['settings'].get('title') or 'Rack Live'
        text = f'{site}\n' + '\n'.join(lines) + (f"\n\n{c['url']}" if c.get('url') else '')
        results = {}
        for ch, fn in (('telegram', self._telegram), ('email', self._email), ('webhook', self._webhook)):
            if not c[ch].get('enabled'):
                continue
            try:
                fn(c[ch], text, site, lines, dev)
                results[ch] = 'ok'
            except Exception as e:
                results[ch] = f'ошибка: {e}'
            self.status[ch] = {'t': time.time(), 'result': results[ch]}
        if any(v != 'ok' for v in results.values()):
            self.store.add_event(None, 'Уведомления', 'warning', '; '.join(f'{k}: {v}' for k, v in results.items() if v != 'ok'))
        return results

    @staticmethod
    def tg_call(c, method, payload, timeout=15):
        api = (c.get('api') or 'https://api.telegram.org').rstrip('/')
        req = urllib.request.Request(f"{api}/bot{c['token']}/{method}", data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read() or b'{}')
        except urllib.error.HTTPError as e:
            detail = json.loads(e.read() or b'{}').get('description', '')
            raise ValueError({401: 'неверный токен бота', 404: 'неверный токен бота',
                              400: f'Telegram отклонил запрос: {detail}'}.get(e.code, f'HTTP {e.code} {detail}'))
        except urllib.error.URLError as e:
            raise ValueError(f'Telegram недоступен ({e.reason}) — можно указать адрес прокси API')

    def setup_menu(self, cfg=None):
        """Bot menu button → the mini app (or back to the plain menu when no address is set)."""
        c = (cfg or self.cfg())['telegram']
        if not c.get('enabled') or not c.get('token'):
            return None
        url = (c.get('webapp') or '').strip()
        if url and not url.startswith('https://'):
            return 'адрес панели должен начинаться с https:// — Telegram открывает мини-приложения только по HTTPS'
        try:
            self.tg_call(c, 'setChatMenuButton', {'menu_button': {'type': 'web_app', 'text': 'Rack Live', 'web_app': {'url': url}}
                                                   if url else {'type': 'default'}})
            return 'ok'
        except ValueError as e:
            return str(e)

    def _telegram(self, c, text, site, lines, dev=None):
        if not c.get('token') or not c.get('chat'):
            raise ValueError('не указан токен бота или chat id')
        url = (c.get('webapp') or '').strip()
        for chat in [x.strip() for x in str(c['chat']).split(',') if x.strip()]:
            payload = {'chat_id': chat, 'text': text, 'disable_web_page_preview': True}
            if url.startswith('https://'):
                link = url + ('&' if '?' in url else '?') + urlencode({'device': dev}) if dev else url
                # mini-app buttons work only in private chats; groups get a normal link
                btn = {'text': 'Открыть Rack Live', 'url': link} if chat.startswith('-') else {'text': 'Открыть Rack Live', 'web_app': {'url': link}}
                payload['reply_markup'] = {'inline_keyboard': [[btn]]}
            try:
                self.tg_call(c, 'sendMessage', payload)
            except ValueError as e:
                msg = str(e)
                if 'chat not found' in msg or 'Bad Request' in msg:
                    msg = f'chat id {chat} не подходит — напишите своему боту /start и проверьте ID'
                raise ValueError(msg)

    def _email(self, c, text, site, lines, dev=None):
        if not c.get('host') or not c.get('to'):
            raise ValueError('не указан SMTP-сервер или получатель')
        msg = MIMEText(text, 'plain', 'utf-8')
        msg['Subject'] = f'{site}: ' + lines[0][:120]
        msg['From'] = c.get('from') or c.get('user') or 'racklive@localhost'
        msg['To'] = c['to']
        port = int(c.get('port') or 587)
        ctx = ssl.create_default_context()
        s = smtplib.SMTP_SSL(c['host'], port, timeout=20, context=ctx) if port == 465 else smtplib.SMTP(c['host'], port, timeout=20)
        try:
            if port != 465 and c.get('tls', True):
                s.starttls(context=ctx)
            if c.get('user'):
                s.login(c['user'], c.get('password') or '')
            s.sendmail(msg['From'], [x.strip() for x in c['to'].split(',')], msg.as_string())
        finally:
            s.quit()

    def _webhook(self, c, text, site, lines, dev=None):
        if not c.get('url'):
            raise ValueError('не указан адрес')
        url = c['url']
        if 'ntfy' in url:                                    # ntfy.sh and self-hosted ntfy take a plain body
            title = '=?UTF-8?B?' + base64.b64encode(site.encode()).decode() + '?='    # RFC 2047 — headers must be ASCII
            req = urllib.request.Request(url, data=text.encode(), headers={'Title': title})
        else:
            req = urllib.request.Request(url, data=json.dumps({'title': site, 'text': text, 'items': lines}, ensure_ascii=False).encode(),
                                         headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=15).read()
