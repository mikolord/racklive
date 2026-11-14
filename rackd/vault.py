"""«Пароли» (Settings → Пароли): every login, password and key typed into the device cards, in one place — like the Passwords app on iOS.

Opening it needs the administrator password typed again; that gives a short ticket (in memory only, a few minutes, renewed while in use).
With the ticket: the list (values included), a change of one device's logins/passwords, export (JSON of Rack Live — full, re-importable —
or CSV in the Title,URL,Username,Password,Notes form that iOS / Chrome / 1Password / Bitwarden understand) and import of such a file.
Import never creates devices: it only fills logins / passwords of devices that already exist (matched by the id mark, then by address).
"""
import csv, io, json, re, secrets, threading, time, urllib.parse

TTL = 300                                    # seconds a ticket lives without use
TRIES = 10                                   # wrong administrator passwords in a row before «Пароли» waits LOCK seconds (own count, not the sign-in's)
LOCK = 300

# device fields that hold a secret value shown here (panelInfo / portal are structures, handled apart or not at all)
SECRET_FIELDS = ('password', 'webPassword', 'entwarePassword', 'privateKey', 'token', 'tokenSecret', 'agentToken')
USER_FIELDS = ('username', 'webUser', 'entwareUser', 'tokenId', 'user', 'login')
LABELS = {'username': 'Логин', 'password': 'Пароль', 'webUser': 'Логин веб-интерфейса', 'webPassword': 'Пароль веб-интерфейса',
          'entwareUser': 'Entware: логин', 'entwarePassword': 'Entware: пароль', 'privateKey': 'SSH-ключ', 'token': 'Токен',
          'tokenId': 'ID токена', 'tokenSecret': 'Секрет токена', 'agentToken': 'Токен агента', 'user': 'Логин', 'login': 'Логин'}
EDITABLE = set(SECRET_FIELDS + USER_FIELDS) - {'agentToken'}       # the agent token is made by Rack Live itself
# which user field goes with which secret (for CSV rows and the «login + password» pairs on screen)
PAIRS = (('username', 'password'), ('webUser', 'webPassword'), ('entwareUser', 'entwarePassword'), ('tokenId', 'tokenSecret'))
MARK = re.compile(r'\[rl:([\w.\-]+):(\w+)(?::(\w+))?\]')


class Tickets:
    def __init__(self):
        self.t = {}
        self.fails = {}                         # ip → (wrong passwords in a row, time of the last one)
        self.lock = threading.Lock()

    def throttled(self, ip):
        n, t = self.fails.get(ip, (0, 0))
        return n >= TRIES and time.time() - t < LOCK

    def fail(self, ip):
        """→ how many tries are left (0 = locked now)"""
        now = time.time()
        with self.lock:
            n, t = self.fails.get(ip, (0, 0))
            n = n + 1 if now - t < LOCK else 1
            self.fails[ip] = (n, now)
            if len(self.fails) > 500:
                self.fails = {k: v for k, v in self.fails.items() if now - v[1] < LOCK}
            return max(0, TRIES - n)

    def good(self, ip):
        self.fails.pop(ip, None)

    def new(self):
        k = secrets.token_urlsafe(24)
        with self.lock:
            self.t = {x: e for x, e in self.t.items() if e > time.time()}
            self.t[k] = time.time() + TTL
        return k

    def ok(self, k):
        with self.lock:
            e = self.t.get(k or '')
            if not e or e < time.time():
                self.t.pop(k or '', None)
                return False
            self.t[k] = time.time() + TTL                   # in use → lives on
            return True

    def drop(self, k):
        with self.lock:
            self.t.pop(k or '', None)


def _labels(drv):
    out = dict(LABELS)
    for f in getattr(drv, 'fields', None) or []:
        if isinstance(f, dict) and f.get('name') and f.get('label'):
            out[f['name']] = f['label']
    return out


def web_url(d):
    h = (d.get('webUrl') or d.get('host') or '').strip()
    if not h:
        return ''
    return h.rstrip('/') if '://' in h else ''


def entry(d, drv):
    lab = _labels(drv)
    fields = []
    for k in USER_FIELDS + SECRET_FIELDS:
        v = d.get(k)
        if isinstance(v, (str, int)) and str(v) != '':
            fields.append({'key': k, 'label': lab.get(k) or k, 'value': str(v), 'secret': k in SECRET_FIELDS, 'editable': k in EDITABLE,
                           'multiline': k == 'privateKey'})
    panels = []
    for pid, info in (d.get('panelInfo') or {}).items():
        if isinstance(info, dict) and (info.get('user') or info.get('password')):
            panels.append({'id': pid, 'url': info.get('url') or '', 'user': info.get('user') or '', 'password': info.get('password') or ''})
    return {'id': d['id'], 'name': d.get('name') or d.get('host') or d['id'], 'kind': d.get('kind') or getattr(drv, 'kind', 'other'),
            'driver': d.get('driver'), 'driverTitle': getattr(drv, 'title', '') or d.get('driver') or '', 'host': d.get('host') or '',
            'sshPort': d.get('sshPort') or d.get('port') or '', 'url': web_url(d) or d.get('webUrl') or '', 'fields': fields, 'panels': panels}


def entries(devices, registry):
    out = [entry(d, registry.get(d.get('driver'))) for d in devices if isinstance(d, dict) and d.get('id')]
    return sorted([e for e in out if e['fields'] or e['panels']], key=lambda e: e['name'].lower())


def update(d, fields):
    """one device's logins / passwords → the changed keys. Empty value = remove that field."""
    changed = []
    for k, v in (fields or {}).items():
        if k not in EDITABLE or not isinstance(v, (str, int, type(None))):
            continue
        v = '' if v is None else str(v)
        if k != 'privateKey':
            v = v.strip()
        if len(v) > 20000:
            raise ValueError('слишком длинное значение')
        if (d.get(k) or '') == v:
            continue
        if v:
            d[k] = v
        else:
            d.pop(k, None)
        changed.append(k)
    return changed


# ── export ──
def export_json(devices, registry):
    items = []
    for e in entries(devices, registry):
        items.append({'id': e['id'], 'name': e['name'], 'driver': e['driver'], 'host': e['host'], 'url': e['url'],
                      'fields': {f['key']: f['value'] for f in e['fields']}, 'panels': e['panels']})
    return json.dumps({'format': 'racklive-passwords', 'version': 1, 'exported': int(time.time()), 'items': items}, ensure_ascii=False, indent=1)


def _row_url(e, user_key):
    if e['url']:
        return e['url']
    if not e['host']:
        return ''
    if user_key == 'entwareUser':
        return 'ssh://' + e['host']
    return ('ssh://' if e['driver'] in ('ssh', 'linux', 'openwrt') and user_key == 'username' else 'http://') + e['host']


def export_csv(devices, registry):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\r\n')
    w.writerow(['Title', 'URL', 'Username', 'Password', 'Notes', 'OTPAuth'])
    for e in entries(devices, registry):
        vals = {f['key']: f['value'] for f in e['fields']}
        used = set()
        for uk, pk in PAIRS:
            if vals.get(pk) or (vals.get(uk) and pk not in vals and uk != 'username'):
                lab = {'password': '', 'webPassword': ' (веб)', 'entwarePassword': ' (Entware)', 'tokenSecret': ' (токен)'}[pk]
                w.writerow([e['name'] + lab, _row_url(e, uk), vals.get(uk, ''), vals.get(pk, ''), f'Rack Live [rl:{e["id"]}:{pk}:{uk}]', ''])
                used.update((uk, pk))
        if vals.get('username') and 'username' not in used:
            w.writerow([e['name'], _row_url(e, 'username'), vals['username'], '', f'Rack Live [rl:{e["id"]}:password:username]', ''])
        for k in ('privateKey', 'token', 'agentToken'):
            if vals.get(k) and k not in used:
                w.writerow([e['name'] + ' — ' + LABELS[k], _row_url(e, 'username'), vals.get('username', ''), vals[k], f'Rack Live [rl:{e["id"]}:{k}]', ''])
        for p in e['panels']:
            w.writerow([f"{e['name']} — панель {p['id']}", p['url'], p['user'], p['password'], 'Rack Live (панель на сервере, только для справки)', ''])
    return buf.getvalue()


# ── import ──
def _host_of(u):
    u = (u or '').strip()
    if not u:
        return ''
    if '://' not in u:
        u = 'x://' + u
    try:
        return (urllib.parse.urlsplit(u).hostname or '').lower()
    except ValueError:
        return ''


def parse(text):
    """a file → [{'id'?, 'host'?, 'name'?, 'fields': {key: value}}]. Raises ValueError."""
    text = (text or '').lstrip('\ufeff')
    if not text.strip():
        raise ValueError('файл пустой')
    if text.lstrip()[:1] in '{[':
        try:
            data = json.loads(text)
        except ValueError:
            raise ValueError('это не JSON')
        if isinstance(data, dict) and data.get('format') == 'racklive-passwords':
            return [{'id': i.get('id'), 'host': _host_of(i.get('host') or i.get('url')), 'name': i.get('name') or '',
                     'fields': {k: v for k, v in (i.get('fields') or {}).items() if k in EDITABLE and isinstance(v, str)}}
                    for i in data.get('items') or [] if isinstance(i, dict)]
        if isinstance(data, dict) and data.get('version') == 2 and isinstance(data.get('devices'), list):      # a full backup of Rack Live
            return [{'id': d.get('id'), 'host': _host_of(d.get('host')), 'name': d.get('name') or '',
                     'fields': {k: v for k, v in d.items() if k in EDITABLE and isinstance(v, str) and v}}
                    for d in data['devices'] if isinstance(d, dict)]
        raise ValueError('JSON не похож на пароли Rack Live')
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError('файл пустой')
    head = [h.strip().lower() for h in rows[0]]
    col = lambda *names: next((head.index(n) for n in names if n in head), None)
    ci, cu, cn, cp, cnote = col('title', 'name'), col('url', 'login_uri', 'website'), col('username', 'login_username', 'login'), \
        col('password', 'login_password'), col('notes', 'note', 'extra')
    if cp is None:
        raise ValueError('в CSV нет колонки Password')
    out = []
    for r in rows[1:]:
        g = lambda i: (r[i] if i is not None and i < len(r) else '').strip() if i != cp else (r[i] if i is not None and i < len(r) else '')
        note = g(cnote)
        m = MARK.search(note)
        if m:
            pk, uk = m.group(2), m.group(3)
            f = {}
            if pk in EDITABLE and g(cp):
                f[pk] = g(cp)
            if uk and uk in EDITABLE and g(cn):
                f[uk] = g(cn)
            out.append({'id': m.group(1), 'host': _host_of(g(cu)), 'name': g(ci), 'fields': f})
        elif 'панель на сервере' in note:
            continue
        else:
            f = {}
            if g(cp):
                f['password'] = g(cp)
            if g(cn):
                f['username'] = g(cn)
            out.append({'id': None, 'host': _host_of(g(cu)), 'name': g(ci), 'fields': f})
    return out


def apply_import(devices, items):
    """fills existing devices → {'updated': [names], 'unmatched': [names], 'fields': n}"""
    by_id = {d['id']: d for d in devices if isinstance(d, dict) and d.get('id')}
    by_host = {}
    for d in devices:
        h = _host_of(d.get('host'))
        if h:
            by_host.setdefault(h, []).append(d)
    by_name = {}
    for d in devices:
        if d.get('name'):
            by_name.setdefault(d['name'].strip().lower(), []).append(d)
    updated, unmatched, n = [], [], 0
    for it in items:
        if not it.get('fields'):
            continue
        d = by_id.get(it.get('id') or '')
        if not d and it.get('host') and len(by_host.get(it['host'], [])) == 1:
            d = by_host[it['host']][0]
        if not d and it.get('name') and len(by_name.get(it['name'].strip().lower(), [])) == 1:
            d = by_name[it['name'].strip().lower()][0]
        if not d:
            unmatched.append(it.get('name') or it.get('host') or '?')
            continue
        ch = update(d, it['fields'])
        if ch:
            n += len(ch)
            nm = d.get('name') or d['id']
            if nm not in updated:
                updated.append(nm)
    return {'updated': updated, 'unmatched': unmatched, 'fields': n}
