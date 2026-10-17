"""Community plugins: other people's plugins as DATA (a manifest + shell scripts), never as code that runs inside Rack Live.

A plugin is a .zip: plugin.json (+ scripts/*.sh, README.md, icon.svg|png). It cannot touch Rack Live itself — it is only a recipe of shell steps that Rack Live runs on one
chosen device (SSH server / OpenWrt / Synology) after the administrator has read the commands and confirmed. Before it is accepted, every script is checked:
forbidden things (disk wiping, users / passwords / SSH keys, shutdown, reverse shells, secrets leaving the device …) refuse the plugin; everything it does must be DECLARED
(permissions, hosts it downloads from) or it is refused; a risk level (low / medium / high) is computed and shown.  PLUGIN_API is a contract: change nothing in the format without raising it.

Run protocol: parameters are passed only as environment variables RL_P_<ID> (quoted, never pasted into the script text); a script reports with lines
  @@installed 0|1   @@version X   @@info Label|value   @@url https://…   @@check ok|no|opt Label   @@fail Reason   (status script)  — and @@fail Reason in any step to stop."""
import hashlib, io, json, os, re, shlex, shutil, threading, time, urllib.request, zipfile

PLUGIN_API = 1
INDEX_URL = 'https://raw.githubusercontent.com/mikolord/racklive-plugins/main/index.json'
CATALOG_HOSTS = ('raw.githubusercontent.com', 'github.com', 'objects.githubusercontent.com')
MAX_ZIP, MAX_UNPACKED, MAX_FILES = 1024 * 1024, 2 * 1024 * 1024, 40
MAX_SCRIPT, MAX_STEPS, MAX_FIELDS = 40 * 1024, 12, 12
EXT = {'.json', '.sh', '.md', '.txt', '.svg', '.png'}
TARGETS = {'ssh': ('ssh', 'demo_server'), 'openwrt': ('openwrt', 'demo_openwrt'), 'synology': ('synology',)}
PERMS = {'network': 'скачивает файлы из интернета', 'packages': 'ставит или удаляет пакеты', 'services': 'управляет службами и расписанием',
         'docker': 'работает с Docker', 'reboot': 'перезагружает устройство'}
ID_RE = re.compile(r'^[a-z][a-z0-9-]{2,30}$')
FIELD_ID = re.compile(r'^[a-z][a-z0-9_]{0,23}$')
FORMATS = {'host': r'^[A-Za-z0-9.\-]{1,253}$', 'port': r'^\d{1,5}$', 'domain': r'^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$', 'word': r'^[\w.\-]{1,60}$',
           'path': r'^/[\w./\-]{0,200}$'}

# (pattern, why) — a plugin containing any of these is refused, whatever it declares
DENY = [
    (r'\bmkfs(\.\w+)?\b|\bwipefs\b|\bfdisk\b|\bparted\b|\bmdadm\b[^\n]*--(create|zero)', 'работа с разделами и дисками (форматирование)'),
    (r'\bdd\b[^\n]*\bof=/dev/|>\s*/dev/(sd|nvme|mmcblk|hd|md)', 'запись прямо на диск'),
    (r'\brm\s+(-[a-zA-Z]+\s+)*-[a-zA-Z]*[rRf][a-zA-Z]*\s+(-[a-zA-Z]+\s+)*(/|/\*|~|~/|\$HOME/?|/volume\d*/?|/etc|/usr|/bin|/sbin|/lib|/var|/boot|/root|/home|/opt|/mnt)(\s|$|;|\||&)', 'рекурсивное удаление системных папок'),
    (r':\s*\(\s*\)\s*\{', 'форк-бомба'),
    (r'\b(passwd|chpasswd|usermod|userdel|useradd|adduser|deluser|visudo|synouser)\b|/etc/(shadow|sudoers|passwd)', 'пользователи, пароли и доступ sudo'),
    (r'authorized_keys|\bid_(rsa|ed25519|ecdsa)\b|\.ssh/|ssh-keygen|dropbear\.key', 'SSH-ключи и доступ по ключам'),
    (r'\b(shutdown|poweroff|halt)\b|\binit\s+[06]\b', 'выключение устройства'),
    (r'iptables\s+(-t\s+\w+\s+)?-F|nft\s+flush|ufw\s+disable|setenforce\s+0', 'отключение межсетевого экрана'),
    (r'/dev/(tcp|udp)/|\bnc(at)?\b[^\n]*\s-[a-z]*e\b|\bsocat\b[^\n]*(exec|system)|\bmkfifo\b[^\n]*\bnc\b', 'обратная оболочка / скрытое подключение'),
    (r'base64\s+(-d|--decode)[^\n]*\|\s*(ba|z|da)?sh\b|\beval\b\s+["\']?\$\(\s*(curl|wget)', 'запуск спрятанного или скачанного кода'),
    (r'\b(env|printenv|set)\b[^\n]*\|\s*(curl|wget|nc)\b|\bcat\b[^\n]*(/etc/passwd|\.env\b|config\.json|secrets?)[^\n]*\|\s*(curl|wget|nc)\b', 'отправка секретов наружу'),
    (r'\bcrontab\s+-r\b|\bhistory\s+-c\b|\bshred\b', 'стирание следов / расписания'),
    (r'chmod\s+(-R\s+)?[0-7]*[67]77\s+/(\s|$)|chown\s+-R\s+\S+\s+/(\s|$)', 'смена прав на всей системе'),
    (r'\bsynopkg\s+(uninstall|stop)\b[^\n]*\b(DSM|ContainerManager|Docker)\b', 'остановка системных пакетов NAS'),
]
NEEDS = [  # (pattern, permission it requires)
    (r'\breboot\b', 'reboot'),
    (r'\b(systemctl|service|rc-service|crontab|synoservice|synopkg)\b|/etc/init\.d/', 'services'),
    (r'\bdocker(-compose)?\b', 'docker'),
    (r'\b(apt(-get)?|apk|opkg|dnf|yum|pacman|pip3?|npm|pnpm|gem)\s+(install|add|remove|del|purge|upgrade|update|-S)\b', 'packages'),
    (r'\b(curl|wget|fetch)\b|\bgit\s+clone\b', 'network'),
]
URL_RE = re.compile(r'https?://([A-Za-z0-9.\-_]+|\$\{?[A-Za-z_]\w*\}?)')
PIPE_SH = re.compile(r'\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da)?sh\b')
REF_RE = re.compile(r'\$\{?RL_P_([A-Z0-9_]+)')


def vtuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', str(v))[:3]) or (0,)


def digest(m):
    """a fingerprint of everything that will run: the page shows it, and the run must carry the same one"""
    h = hashlib.sha256(json.dumps({k: m.get(k) for k in ('id', 'version', 'kind', 'targets', 'fields', 'status', 'install', 'remove', 'run', 'scene')}, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:16]


def _scripts(m):
    out = []
    if m.get('status'):
        out.append(('status', m['status']))
    for sec in ('install', 'remove', 'run'):
        for i, s in enumerate(m.get(sec) or []):
            out.append((f'{sec} {i + 1}', s['script']))
    return out


def check_scene(raw):
    """a SCENE (kind: "scene"): a made-up network as data (rackd/scenes.py). No scripts, nothing to run on a device: only the strict schema of the scene itself"""
    from . import scenes
    errors, warnings = [], []
    if raw.get('plugin_api') != PLUGIN_API:
        errors.append(f'plugin_api должен быть {PLUGIN_API}')
    pid = str(raw.get('id') or '')
    if not ID_RE.match(pid):
        errors.append('id: 3–31 символ, латиница в нижнем регистре, цифры и дефис, начинается с буквы')
    title, desc = str(raw.get('title') or '').strip(), str(raw.get('description') or '').strip()
    if not title or len(title) > 60:
        errors.append('title: нужно название до 60 символов')
    if not desc or len(desc) > 400:
        errors.append('description: нужно описание до 400 символов')
    if not re.match(r'^\d+(\.\d+){0,2}$', str(raw.get('version') or '')):
        errors.append('version: например 1.0.0')
    home = str(raw.get('home') or '')
    if home and not re.match(r'^https://[^\s]+$', home):
        errors.append('home: только https-ссылка')
    errs, warns, clean = scenes.validate(raw)
    errors += errs
    warnings += warns
    m = {'plugin_api': PLUGIN_API, 'kind': 'scene', 'id': pid, 'title': title, 'description': desc, 'version': str(raw.get('version') or ''), 'author': str(raw.get('author') or '')[:60],
         'home': home, 'icon': 'home', 'targets': [], 'permissions': [], 'network': [], 'fields': [], 'status': None, 'install': [], 'remove': [], 'run': [], 'risk': 'low'}
    if clean:
        m['scene'] = clean
        m['stats'] = scenes.stats(clean)
    m['digest'] = digest(m)
    return errors, warnings, m


def check(files):
    """→ (errors, warnings, manifest | None). `files` = {path: bytes}. The manifest comes back resolved (scripts from files inlined) and with risk / perms / digest."""
    errors, warnings = [], []
    if 'plugin.json' not in files:
        return ['в архиве нет plugin.json'], [], None
    try:
        raw = json.loads(files['plugin.json'].decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        return [f'plugin.json: не читается ({e})'], [], None
    if not isinstance(raw, dict):
        return ['plugin.json должен быть объектом'], [], None
    if raw.get('kind') == 'scene':
        return check_scene(raw)
    if raw.get('plugin_api') != PLUGIN_API:
        errors.append(f'plugin_api должен быть {PLUGIN_API} (у этой версии Rack Live именно такой формат)')
    pid = str(raw.get('id') or '')
    if not ID_RE.match(pid):
        errors.append('id: 3–31 символов, латиница в нижнем регистре, цифры и дефис, начинается с буквы')
    title = str(raw.get('title') or '').strip()
    if not title or len(title) > 60:
        errors.append('title: нужно название до 60 символов')
    desc = str(raw.get('description') or '').strip()
    if not desc or len(desc) > 400:
        errors.append('description: нужно описание до 400 символов')
    if not re.match(r'^\d+(\.\d+){0,2}$', str(raw.get('version') or '')):
        errors.append('version: например 1.0.0')
    targets = raw.get('targets')
    if not isinstance(targets, list) or not targets or any(t not in TARGETS for t in targets):
        errors.append('targets: список из ' + ', '.join(TARGETS) + ' (где плагин работает)')
        targets = []
    perms = raw.get('permissions') or []
    if not isinstance(perms, list) or any(p not in PERMS for p in perms):
        errors.append('permissions: можно только ' + ', '.join(PERMS))
        perms = []
    hosts = raw.get('network') or []
    if not isinstance(hosts, list) or any(not isinstance(h, str) or not re.match(r'^[a-z0-9.\-]{3,253}$', h) for h in hosts):
        errors.append('network: список имён серверов, с которых плагин скачивает (например "github.com")')
        hosts = []
    if hosts and 'network' not in perms:
        errors.append('указан network, но в permissions нет "network"')
    home = str(raw.get('home') or '')
    if home and not re.match(r'^https://[^\s]+$', home):
        errors.append('home: только https-ссылка')

    fields = raw.get('fields') or []
    if not isinstance(fields, list) or len(fields) > MAX_FIELDS:
        errors.append(f'fields: список, не больше {MAX_FIELDS}')
        fields = []
    seen = set()
    clean_fields = []
    for f in fields:
        if not isinstance(f, dict) or not FIELD_ID.match(str(f.get('id') or '')) or f['id'] in seen:
            errors.append('поле формы: id латиницей (a-z, 0-9, _), без повторов')
            continue
        seen.add(f['id'])
        t = f.get('type', 'text')
        if t not in ('text', 'password', 'number', 'select', 'switch'):
            errors.append(f'поле {f["id"]}: тип text / password / number / select / switch')
            continue
        if f.get('format') and f['format'] not in FORMATS:
            errors.append(f'поле {f["id"]}: format — один из ' + ', '.join(FORMATS))
        if t == 'select' and not (isinstance(f.get('options'), list) and f['options'] and all(isinstance(o, list) and len(o) == 2 for o in f['options'])):
            errors.append(f'поле {f["id"]}: для select нужен options [[значение, подпись], …]')
        clean_fields.append({k: f.get(k) for k in ('id', 'label', 'type', 'default', 'options', 'required', 'hint', 'format', 'min', 'max') if f.get(k) is not None} | {'type': t})

    def load(entry, where):
        if not isinstance(entry, dict):
            errors.append(f'{where}: ожидался объект {{"title", "script"}}')
            return None
        txt = entry.get('script')
        if entry.get('file'):
            fp = str(entry['file'])
            if fp not in files or not fp.endswith('.sh'):
                errors.append(f'{where}: файл «{fp}» не найден в архиве (нужен .sh)')
                return None
            try:
                txt = files[fp].decode('utf-8')
            except UnicodeDecodeError:
                errors.append(f'{where}: «{fp}» должен быть в UTF-8')
                return None
        if not isinstance(txt, str) or not txt.strip():
            errors.append(f'{where}: пустой скрипт')
            return None
        if len(txt.encode()) > MAX_SCRIPT:
            errors.append(f'{where}: скрипт больше {MAX_SCRIPT // 1024} КБ')
            return None
        return {'title': str(entry.get('title') or where)[:80], 'script': txt.replace('\r\n', '\n')}

    kind = raw.get('kind') or 'plugin'
    if kind not in ('plugin', 'tool'):
        errors.append('kind: plugin (устанавливается на устройство) или tool (запускается по кнопке и показывает результат)')
        kind = 'plugin'
    m = {'plugin_api': PLUGIN_API, 'kind': kind, 'id': pid, 'title': title, 'description': desc, 'version': str(raw.get('version') or ''), 'author': str(raw.get('author') or '')[:60],
         'home': home, 'icon': raw.get('icon') if raw.get('icon') in ('box', 'server', 'shield', 'terminal', 'download', 'globe2', 'router', 'wrench', 'camera', 'refresh') else 'box',
         'targets': targets, 'permissions': perms, 'network': hosts, 'fields': clean_fields, 'status': None, 'install': [], 'remove': [], 'run': []}
    if kind == 'tool' and any(raw.get(x) for x in ('install', 'remove', 'status')):
        errors.append('у инструмента нет install / remove / status: только run (шаги, которые выполняются по кнопке)')
    if kind == 'plugin' and raw.get('run'):
        errors.append('run бывает только у инструмента (kind: "tool"); у плагина — install / remove')
    if kind == 'plugin' and raw.get('status') is not None:
        st = load(raw['status'] if isinstance(raw['status'], dict) else {'script': raw['status']}, 'status')
        m['status'] = st['script'] if st else None
    for sec in (('run',) if kind == 'tool' else ('install', 'remove')):
        steps = raw.get(sec) or []
        if not isinstance(steps, list) or len(steps) > MAX_STEPS:
            errors.append(f'{sec}: список шагов, не больше {MAX_STEPS}')
            continue
        for i, e in enumerate(steps):
            s = load(e, f'{sec}[{i + 1}]')
            if s:
                m[sec].append(s)
    if kind == 'tool' and not m['run']:
        errors.append('run: нужен хотя бы один шаг')
    if kind == 'plugin' and not m['install']:
        errors.append('install: нужен хотя бы один шаг установки')
    if kind == 'plugin' and not m['status']:
        warnings.append('нет status: Rack Live не узнает, установлен ли плагин (добавьте скрипт со строкой @@installed 0|1)')

    risk, field_ids = 'low', {f['id'].upper() for f in clean_fields}
    need_found, pipe = set(), False
    for where, txt in _scripts(m):
        for pat, why in DENY:
            if re.search(pat, txt, re.I):
                errors.append(f'{where}: запрещено — {why}')
        code = '\n'.join(l for l in txt.splitlines() if not l.lstrip().startswith('#'))      # a comment does nothing, but the checks below look at what is executed
        for pat, perm in NEEDS:
            if re.search(pat, code):
                need_found.add(perm)
                if perm not in perms:
                    errors.append(f'{where}: скрипт делает то, что требует permissions "{perm}" ({PERMS[perm]}), но оно не объявлено')
        if PIPE_SH.search(code):
            pipe = True
        for u in URL_RE.findall(code):
            if u.startswith('$'):
                continue
            h = u.lower().rstrip('.')
            if h in ('localhost', '127.0.0.1'):
                continue
            if not any(h == d or h.endswith('.' + d) for d in hosts):
                errors.append(f'{where}: обращение к «{h}», которого нет в списке network')
        if '{{' in txt:
            errors.append(f'{where}: шаблоны {{{{…}}}} не поддерживаются — значения полей берите из переменных $RL_P_<ID>')
        for ref in REF_RE.findall(txt):
            if ref not in field_ids:
                errors.append(f'{where}: используется $RL_P_{ref}, но поля «{ref.lower()}» нет в fields')
        if re.search(r'(curl|wget)[^\n]*(\s-d\b|--data|\s-F\b|\s-T\b|--upload-file|\s-X\s+POST)', txt):
            warnings.append(f'{where}: отправляет данные на сервер — убедитесь, что это нужно')
    for p in perms:
        if p not in need_found and p != 'network':
            warnings.append(f'объявлено "{p}", но скрипты этого не делают')
    if 'reboot' in need_found or pipe:
        risk = 'high'
    elif need_found - {'network'}:
        risk = 'medium'
    elif 'network' in need_found:
        risk = 'low'
    if pipe:
        warnings.append('запускает скрипт, скачанный из интернета (curl | sh): содержимое может измениться в любой момент')
    if 'synology' in targets:
        warnings.append('на Synology команды выполняются от root (sudo)')
    m['risk'], m['digest'] = risk, digest(m)
    if errors:
        return errors, warnings, m
    return [], warnings, m


def read_zip(blob):
    """→ ({path: bytes}, error): safe unpacking, only known file types, no paths outside"""
    if len(blob) > MAX_ZIP:
        return None, f'архив больше {MAX_ZIP // 1024} КБ'
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return None, 'это не zip-архив'
    infos = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/') and not os.path.basename(i.filename).startswith('.')]
    if len(infos) > MAX_FILES:
        return None, f'в архиве больше {MAX_FILES} файлов'
    names = [i.filename.replace('\\', '/') for i in infos]
    top = ''
    if 'plugin.json' not in names:
        c = {n.split('/')[0] for n in names if '/' in n}
        if len(c) == 1 and f'{next(iter(c))}/plugin.json' in names:
            top = next(iter(c)) + '/'
    files, total = {}, 0
    for i, n in zip(infos, names):
        rel = n[len(top):] if top and n.startswith(top) else n
        if rel.startswith('/') or '..' in rel.split('/') or ':' in rel or not rel:
            return None, f'недопустимый путь в архиве: «{n}»'
        if os.path.splitext(rel)[1].lower() not in EXT:
            return None, f'тип файла не разрешён: «{rel}» (можно: {", ".join(sorted(EXT))})'
        total += i.file_size
        if total > MAX_UNPACKED:
            return None, 'архив слишком большой после распаковки'
        files[rel] = z.read(i)
    return files, None


def clean_values(m, vals):
    """the form → {RL_P_ID: str}; raises ValueError with a readable reason"""
    out, vals = {}, vals or {}
    for f in m['fields']:
        v = vals.get(f['id'], f.get('default'))
        t = f.get('type', 'text')
        if t == 'switch':
            v = '1' if v in (True, 1, '1', 'true') else '0'
        else:
            v = '' if v is None else str(v)
            if not v and f.get('required'):
                raise ValueError(f'заполните поле «{f.get("label") or f["id"]}»')
            if len(v) > 200 or re.search(r'[\x00-\x08\x0b-\x1f]', v):
                raise ValueError(f'поле «{f.get("label") or f["id"]}»: недопустимое значение')
            if v and t == 'number':
                if not re.match(r'^-?\d{1,12}(\.\d+)?$', v):
                    raise ValueError(f'поле «{f.get("label") or f["id"]}»: нужно число')
                if f.get('min') is not None and float(v) < float(f['min']) or f.get('max') is not None and float(v) > float(f['max']):
                    raise ValueError(f'поле «{f.get("label") or f["id"]}»: вне допустимых границ')
            if v and t == 'select' and v not in [str(o[0]) for o in f['options']]:
                raise ValueError(f'поле «{f.get("label") or f["id"]}»: выберите из списка')
            if v and f.get('format') and not re.match(FORMATS[f['format']], v):
                raise ValueError(f'поле «{f.get("label") or f["id"]}»: неверный формат ({f["format"]})')
        out['RL_P_' + f['id'].upper()] = v
    return out


def parse_status(out):
    s = {'installed': None, 'version': '', 'info': [], 'checks': [], 'url': '', 'warn': []}
    for l in out.splitlines():
        if not l.startswith('@@'):
            continue
        k, _, v = l[2:].partition(' ')
        v = v.strip()
        if k == 'installed':
            s['installed'] = v == '1'
        elif k == 'version':
            s['version'] = v[:40]
        elif k == 'info' and '|' in v:
            a, _, b = v.partition('|')
            s['info'].append({'label': a.strip()[:40], 'value': b.strip()[:200]})
        elif k == 'url' and re.match(r'^https?://[^\s]+$', v):
            s['url'] = v[:300]
        elif k == 'check':
            st, _, label = v.partition(' ')
            if st in ('ok', 'no', 'opt'):
                s['checks'].append({'ok': st == 'ok', 'optional': st == 'opt', 'label': label.strip()[:120]})
        elif k == 'warn':
            s['warn'].append(v[:200])
    return s


def parse_output(text):
    """what a TOOL printed → {text: [lines], kv: [{label, value}], head: [cols] | None, rows: [[cells]], ok: str | None}"""
    out = {'text': [], 'kv': [], 'head': None, 'rows': [], 'ok': None}
    for l in text.splitlines():
        if l.startswith('@@kv ') and '|' in l:
            a, _, b = l[5:].partition('|')
            if len(out['kv']) < 200:
                out['kv'].append({'label': a.strip()[:60], 'value': b.strip()[:300]})
        elif l.startswith('@@head '):
            out['head'] = [c.strip()[:40] for c in l[7:].split('|')][:12]
        elif l.startswith('@@row '):
            if len(out['rows']) < 300:
                out['rows'].append([c.strip()[:120] for c in l[6:].split('|')][:12])
        elif l.startswith('@@ok'):
            out['ok'] = l[4:].strip()[:200] or None
        elif l.startswith('@@'):
            continue
        elif l.strip() and len(out['text']) < 400:
            out['text'].append(l[:300])
    return out


class Community:
    def __init__(self, data_dir):
        self.dir = os.path.join(data_dir, 'community')
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        self._index = (0, None)

    # ── store ──
    def _path(self, pid):
        return os.path.join(self.dir, pid)

    def get(self, pid):
        try:
            with open(os.path.join(self._path(pid), 'plugin.json'), encoding='utf-8') as f:
                m = json.load(f)
            with open(os.path.join(self._path(pid), 'meta.json'), encoding='utf-8') as f:
                meta = json.load(f)
        except (OSError, ValueError):
            return None
        return dict(m, source=meta.get('source', 'own'), installedAt=meta.get('t'), sha256=meta.get('sha256'))

    def list(self):
        return [m for m in (self.get(n) for n in sorted(os.listdir(self.dir))) if m]

    def public(self, m):
        return {k: m.get(k) for k in ('id', 'title', 'description', 'version', 'author', 'home', 'icon', 'targets', 'permissions', 'network', 'risk', 'digest', 'source', 'installedAt', 'stats')} \
            | {'kind': m.get('kind') or 'plugin', 'fields': m.get('fields', []),
               'steps': {'install': [s['title'] for s in m.get('install', [])], 'remove': [s['title'] for s in m.get('remove', [])], 'run': [s['title'] for s in m.get('run', [])]}}

    def detail(self, pid):
        """for the «what will run» preview: everything, including the scripts"""
        m = self.get(pid)
        if not m:
            return None
        return self.public(m) | {'status': m.get('status'), 'install': m.get('install'), 'remove': m.get('remove'), 'run': m.get('run')}

    def install_zip(self, blob, source='own', expect_sha=None):
        files, err = read_zip(blob)
        if err:
            return {'ok': False, 'errors': [err], 'warnings': []}
        errors, warnings, m = check(files)
        if errors:
            return {'ok': False, 'errors': errors, 'warnings': warnings, 'plugin': self.public(m) if m else None}
        old = self.get(m['id'])
        if old and vtuple(old.get('version')) > vtuple(m['version']):
            return {'ok': False, 'errors': [f'уже установлена более новая версия {old["version"]}'], 'warnings': warnings}
        with self.lock:
            dst = self._path(m['id'])
            shutil.rmtree(dst, ignore_errors=True)
            os.makedirs(dst)
            with open(os.path.join(dst, 'plugin.json'), 'w', encoding='utf-8') as f:
                json.dump(m, f, ensure_ascii=False, indent=1)
            with open(os.path.join(dst, 'meta.json'), 'w', encoding='utf-8') as f:
                json.dump({'source': source, 't': int(time.time()), 'sha256': hashlib.sha256(blob).hexdigest()}, f)
            if 'README.md' in files:
                with open(os.path.join(dst, 'README.md'), 'wb') as f:
                    f.write(files['README.md'][:20000])
        return {'ok': True, 'errors': [], 'warnings': warnings, 'plugin': self.public(self.get(m['id']))}

    def remove(self, pid):
        if ID_RE.match(pid or ''):
            shutil.rmtree(self._path(pid), ignore_errors=True)

    # ── the community catalog (a separate GitHub repository with index.json) ──
    def index(self, url=INDEX_URL, force=False):
        t, cached = self._index
        if cached is not None and not force and time.time() - t < 600:
            return cached
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'RackLive-community'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read(400_000).decode('utf-8'))
            items = [{k: p.get(k) for k in ('id', 'title', 'description', 'author', 'version', 'kind', 'targets', 'risk', 'zip', 'sha256')} for p in data.get('plugins', [])
                     if isinstance(p, dict) and ID_RE.match(str(p.get('id') or '')) and re.match(r'^[0-9a-f]{64}$', str(p.get('sha256') or ''))]
            res = {'ok': True, 'plugins': items[:200]}
        except Exception as e:
            res = {'ok': False, 'plugins': [], 'error': 'каталог сообщества сейчас недоступен' + (f' ({type(e).__name__})' if not isinstance(e, ValueError) else '')}
        self._index = (time.time(), res)
        return res

    def install_from_index(self, pid, url=INDEX_URL):
        item = next((p for p in self.index(url)['plugins'] if p['id'] == pid), None)
        if not item:
            return {'ok': False, 'errors': ['такого плагина нет в каталоге'], 'warnings': []}
        z = str(item.get('zip') or '')
        m = re.match(r'^https://([a-z0-9.\-]+)/', z)
        if not m or m.group(1) not in CATALOG_HOSTS:
            return {'ok': False, 'errors': ['адрес архива должен быть на github.com / raw.githubusercontent.com'], 'warnings': []}
        try:
            req = urllib.request.Request(z, headers={'User-Agent': 'RackLive-community'})
            with urllib.request.urlopen(req, timeout=20) as r:
                blob = r.read(MAX_ZIP + 1)
        except Exception as e:
            return {'ok': False, 'errors': [f'не удалось скачать ({type(e).__name__})'], 'warnings': []}
        if hashlib.sha256(blob).hexdigest() != item['sha256']:
            return {'ok': False, 'errors': ['контрольная сумма не совпала с каталогом — архив изменили'], 'warnings': []}
        return self.install_zip(blob, 'community')

    # ── on a device ──
    @staticmethod
    def target_of(driver):
        return next((t for t, names in TARGETS.items() if driver in names), None)

    def for_device(self, d):
        t = self.target_of(d.get('driver'))
        return [m for m in self.list() if t and t in m['targets'] and (m.get('kind') or 'plugin') == 'plugin'] if t else []

    def tools(self):
        """community TOOLS: they live in Инструменты (a form, one button, a result), not on a device's plugin tab"""
        return [m for m in self.list() if m.get('kind') == 'tool']

    def scenes(self):
        return [m for m in self.list() if m.get('kind') == 'scene']

    def devices_for(self, m, devices):
        names = {n for t in m['targets'] for n in TARGETS[t]}
        return [d for d in devices if d.get('driver') in names and d.get('enabled', True)]

    def card(self, m, st=None):
        c = dict(self.public(m), kind='community', installed=bool(st and st.get('installed')), version=(st or {}).get('version') or None,
                 checks=(st or {}).get('checks') or [], info=(st or {}).get('info') or [], url=(st or {}).get('url') or '', warn=(st or {}).get('warn') or [],
                 statusKnown=st is not None)
        c['id'] = 'x-' + m['id']
        c['pid'] = m['id']
        return c

    def cards(self, d, drv):
        out = []
        for m in self.for_device(d):
            st = None
            if m.get('status'):
                try:
                    st = parse_status(drv.command(d, self._env({}, m) + m['status']))
                except Exception as e:
                    st = {'installed': None, 'checks': [{'ok': False, 'label': f'не удалось проверить: {str(e)[:100]}'}]}
            out.append(self.card(m, st))
        return out

    @staticmethod
    def _env(vals, m):
        # parameters only as quoted environment variables; a status check runs with defaults
        return ''.join(f'export {k}={shlex.quote(v)}\n' for k, v in vals.items())

    def run(self, d, drv, pid, op, params):
        """install / remove, step by step; → {ok, log, message}. The caller (server) has checked the administrator and the digest."""
        m = self.get(pid)
        if not m or self.target_of(d.get('driver')) not in m['targets']:
            raise ValueError('плагин не подходит для этого устройства')
        tool = m.get('kind') == 'tool'
        if op not in (('run',) if tool else ('install', 'remove')):
            raise ValueError('неизвестное действие')
        if params.get('digest') != m['digest']:
            raise ValueError('плагин изменился после того, как вы просмотрели команды. Откройте плагин заново и проверьте')
        steps = m[op]
        if not steps:
            raise ValueError('у плагина нет шагов для этого действия')
        vals = clean_values(m, params.get('values'))
        secrets_ = [vals['RL_P_' + f['id'].upper()] for f in m['fields'] if f.get('type') == 'password' and vals.get('RL_P_' + f['id'].upper())]
        progress = params.get('_progress') or (lambda s: None)
        log, bodies = [], []
        for i, s in enumerate(steps):
            progress(f'{i + 1}/{len(steps)}: {s["title"]}')
            out = drv.command(d, self._env(vals, m) + s['script'])
            body = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', out)
            for sec in secrets_:
                body = body.replace(sec, '***')
            bodies.append(body)
            log.append({'cmd': '— ' + s['title'], 'ok': True, 'msg': ''})
            log.extend([{'cmd': l[:220], 'ok': '@@fail' not in l, 'msg': ''} for l in body.splitlines() if l.strip() and not l.startswith(('@@installed', '@@version', '@@info', '@@check', '@@kv', '@@head', '@@row'))][:80])
            if '@@fail' in body:
                raise RuntimeError(f"{s['title']}: " + body.split('@@fail', 1)[1].splitlines()[0].strip())
        if tool:
            res = parse_output('\n'.join(bodies))
            return {'ok': True, 'log': log, 'output': res, 'message': res.get('ok') or f"{m['title']}: готово"}
        return {'ok': True, 'log': log, 'message': f"{m['title']}: {'установлено' if op == 'install' else 'удалено'}"}


class Shim:
    """what start_plugin_job expects of a driver: .plugin(cfg, pid, op, params) — here it runs a community plugin"""
    def __init__(self, community, drv):
        self.community, self.drv = community, drv
        self.async_ops = ('install', 'remove', 'run')

    def plugin(self, cfg, pid, op, params):
        try:
            return self.community.run(cfg, self.drv, pid[2:], op, params)
        except ValueError as e:
            raise RuntimeError(str(e))


TOOL_TEMPLATE = """#!/bin/sh
# Инструмент «Свободное место»: показывает разделы устройства таблицей. Значения полей приходят переменными RL_P_<ID>.
echo "@@kv Устройство|$(hostname)"
echo "@@kv Время работы|$(uptime | sed 's/^.*up //;s/,.*//')"
echo "@@head Раздел|Размер|Занято|Куда подключён"
df -P -h 2>/dev/null | tail -n +2 | awk -v lim="$RL_P_LIMIT" '{ use=$5; sub(/%/,"",use); if (use+0 >= lim+0) print "@@row "$1"|"$2"|"$5"|"$6 }'
echo "@@ok Показаны разделы, занятые не меньше $RL_P_LIMIT %"
"""


def template_zip(kind='plugin'):
    """a starter plugin, tool or scene for authors (what the «Скачать шаблон» buttons give)"""
    if kind == 'scene':
        from . import scenes
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('plugin.json', json.dumps(scenes.starter(), ensure_ascii=False, indent=1))
            z.writestr('README.md', '# Мой дом\n\nУчебная демо-сцена для Rack Live: двухэтажный дом, роутер, коммутатор, точки, камеры. Замените на свою.\n')
        return buf.getvalue()
    if kind == 'tool':
        manifest = {'plugin_api': PLUGIN_API, 'kind': 'tool', 'id': 'disk-usage', 'title': 'Свободное место', 'version': '1.0.0', 'author': 'Ваше имя', 'icon': 'wrench',
                    'description': 'Учебный инструмент: показывает разделы выбранного устройства, занятые больше заданного процента. Замените на свою задачу.',
                    'targets': ['ssh', 'openwrt', 'synology'], 'permissions': [], 'network': [],
                    'fields': [{'id': 'limit', 'label': 'Показывать разделы, занятые не меньше (%)', 'type': 'number', 'default': 0, 'min': 0, 'max': 100}],
                    'run': [{'title': 'Прочитать разделы', 'file': 'scripts/run.sh'}]}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('plugin.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            z.writestr('scripts/run.sh', TOOL_TEMPLATE)
            z.writestr('README.md', '# Свободное место\n\nУчебный инструмент для Rack Live. Что делает и зачем — опишите здесь.\n')
        return buf.getvalue()
    manifest = {
        'plugin_api': PLUGIN_API, 'id': 'hello-uptime', 'title': 'Привет, аптайм', 'version': '1.0.0', 'author': 'Ваше имя', 'icon': 'box',
        'description': 'Учебный плагин: «устанавливает» файл-заметку на устройство и показывает время работы. Замените на свою задачу.',
        'targets': ['ssh', 'openwrt', 'synology'], 'permissions': [], 'network': [],
        'fields': [{'id': 'note', 'label': 'Текст заметки', 'type': 'text', 'default': 'Привет из Rack Live', 'required': True, 'hint': 'Запишется в /tmp/rl-hello.txt'}],
        'status': {'file': 'scripts/status.sh'},
        'install': [{'title': 'Записать заметку', 'file': 'scripts/install.sh'}],
        'remove': [{'title': 'Удалить заметку', 'script': 'rm -f /tmp/rl-hello.txt\necho "готово"'}],
    }
    status = '#!/bin/sh\nif [ -f /tmp/rl-hello.txt ]; then echo "@@installed 1"; echo "@@info Заметка|$(cat /tmp/rl-hello.txt)"; else echo "@@installed 0"; fi\necho "@@info Время работы|$(uptime | sed \'s/^.*up //;s/,.*//\')"\necho "@@check ok Скрипт выполняется"\n'
    install = '#!/bin/sh\n# значения полей приходят переменными RL_P_<ID> — не вставляйте их в текст скрипта\nprintf \'%s\\n\' "$RL_P_NOTE" > /tmp/rl-hello.txt || { echo "@@fail не удалось записать файл"; exit 0; }\necho "заметка записана"\n'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('plugin.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr('scripts/status.sh', status)
        z.writestr('scripts/install.sh', install)
        z.writestr('README.md', '# Привет, аптайм\n\nУчебный плагин для Rack Live. Что делает и зачем — опишите здесь.\n')
    return buf.getvalue()


def guide_text():
    deny = '\n'.join(f'  - {why}' for _, why in DENY)
    perms = '\n'.join(f'  - {k}: {v}' for k, v in PERMS.items())
    fmts = ', '.join(FORMATS)
    return f'''ИНСТРУКЦИЯ ДЛЯ НЕЙРОСЕТИ: как сделать плагин или инструмент для Rack Live (формат plugin_api = {PLUGIN_API})

ПРОЧИТАЙТЕ СНАЧАЛА: ЧТО ЭТО ЗА ПРОЕКТ И ЧТО ПЛАГИНЫ МОГУТ — А ЧЕГО НЕ МОГУТ

Репозиторий проекта (исходный код, описание, инструкции установки): https://github.com/mikolord/racklive
Если не хватает сведений — откройте его, не гадайте. Правила проверки плагинов и инструментов написаны в файле rackd/community.py (раздел DENY — запреты, NEEDS — что надо объявить), там же формат и пример.

Rack Live — самостоятельно устанавливаемая панель для домашней или небольшой сети (Docker, NAS, роутер): «Главная» из виджетов, шкафы / щитки / комнаты, карта сети и план дома,
устройства (роутеры Keenetic и OpenWrt, коммутаторы, NAS Synology, серверы Linux и Windows, камеры, ИБП …), порты и клиенты, уведомления, помощник Frank. Сама программа написана
на Python (без внешних библиотек) и обычном веб-интерфейсе. Плагины и инструменты НЕ часть этой программы и не меняют её: это безопасные «рецепты».

  • ПЛАГИН (kind: "plugin") — рецепт, который СТАВИТ или НАСТРАИВАЕТ что-то на одном выбранном устройстве: кнопки «Установить» / «Удалить», проверка статуса.
  • ИНСТРУМЕНТ (kind: "tool") — рецепт, который по кнопке «Запустить» выполняется на одном выбранном устройстве и ПОКАЗЫВАЕТ результат (текст, пары «подпись — значение», таблицу).
  Оба — только форма + shell-скрипты. Скрипты выполняются НА УСТРОЙСТВЕ по SSH; Rack Live лишь показывает их вывод.

ЧЕГО ПЛАГИНЫ И ИНСТРУМЕНТЫ НЕ УМЕЮТ (если просят такое — СКАЖИТЕ ЧЕЛОВЕКУ ПРЯМО В НАЧАЛЕ, не обещайте и не делайте «имитацию»):
  – свои страницы, вкладки, виджеты, графики, анимацию, 3D, свой интерфейс. Результат инструмента рисуется только как текст / пары / таблица;
  – менять саму программу: карту, план дома, шкафы и щитки, список устройств, главную страницу, настройки; создавать «виртуальные» устройства, здания, этажи, комнаты;
  – демонстрационные сцены и тестовые наборы устройств (демо-режим встроен в программу, плагином не делается);
  – работать без устройства: код выполняется только на устройстве, выбранном человеком; ни Python, ни JavaScript внутри Rack Live плагин выполнить не может;
  – помнить что-то между запусками внутри Rack Live (можно хранить файлы только на самом устройстве);
  – оформление (цвета, значки, шрифты, картинки плиток, глаз Frank) — это ОТДЕЛЬНАЯ вещь с отдельной инструкцией (Настройки → Оформление → «Добавить своё»), не плагин.
Если задача не укладывается — назовите, что именно из неё невозможно, и предложите ближайшее возможное (например, инструмент, который собирает и показывает таблицу данных с устройства) либо подсказку,
что просить у автора проекта (задача — раздел Issues в репозитории https://github.com/mikolord/racklive). Не пытайтесь обойти проверку: запрещённое отклоняется автоматически.

Задача: по описанию человека собрать .zip с плагином. Плагин — это ДАННЫЕ (описание + shell-скрипты), а не программа внутри Rack Live. Rack Live
запустит скрипты по SSH на ОДНОМ выбранном устройстве после того, как администратор прочитает команды и подтвердит. Проверка при загрузке строгая: что не объявлено — отклоняется.

СОСТАВ АРХИВА (можно в одной папке): plugin.json, scripts/*.sh, README.md, иконка не нужна. Разрешены только файлы: {', '.join(sorted(EXT))}. До {MAX_FILES} файлов, архив до {MAX_ZIP // 1024} КБ.

plugin.json:
{{
  "plugin_api": {PLUGIN_API},
  "id": "my-plugin",                  // 3-31 символ: a-z, 0-9, дефис; начинается с буквы
  "title": "Название до 60 символов", "description": "Что делает, до 400 символов", "version": "1.0.0", "author": "Имя", "home": "https://… (по желанию)",
  "icon": "box",                      // box | server | shield | terminal | download | globe2 | router | wrench | camera | refresh
  "targets": ["ssh"],                 // где работает: ssh (Linux-сервер/VPS), openwrt, synology
  "permissions": ["network", "packages"],   // ОБЯЗАТЕЛЬНО объявить всё, что делают скрипты:
{perms}
  "network": ["github.com"],          // с каких серверов скрипты что-то скачивают (любой другой адрес в скрипте = отказ)
  "fields": [                         // форма для человека; значения придут в скрипт переменными RL_P_<ID заглавными>
    {{"id": "port", "label": "Порт", "type": "number", "default": 8080, "min": 1, "max": 65535, "hint": "…"}},
    {{"id": "host", "label": "Адрес", "type": "text", "format": "host", "required": true}},   // format: {fmts}
    {{"id": "mode", "label": "Режим", "type": "select", "options": [["a","Вариант A"],["b","Вариант B"]], "default": "a"}},
    {{"id": "secret", "label": "Пароль", "type": "password"}}, {{"id": "on", "label": "Включить", "type": "switch", "default": true}}
  ],
  "status":  {{"file": "scripts/status.sh"}},            // или {{"script": "…"}}; только ЧТЕНИЕ, ничего не менять
  "install": [{{"title": "Шаг 1", "file": "scripts/install.sh"}}, {{"title": "Шаг 2", "script": "…"}}],   // до {MAX_STEPS} шагов, по порядку
  "remove":  [{{"title": "Удалить", "script": "…"}}]
}}

ПРАВИЛА ДЛЯ СКРИПТОВ (POSIX sh, работает и на BusyBox/OpenWrt; без bash-специфики):
  1. Значения полей — ТОЛЬКО через переменные "$RL_P_PORT" (в кавычках). Нельзя вставлять их в текст, нельзя использовать {{{{ }}}}.
  2. Вывод — строки-протокол. Статус: "@@installed 1" или 0, "@@version 1.2", "@@info Подпись|значение", "@@url https://…", "@@check ok|no|opt Что проверено", "@@warn текст".
     Ошибка в любом шаге: echo "@@fail причина"; exit 0   — Rack Live остановится и покажет причину.
  3. Каждый шаг должен быть безопасно повторяемым (запустили дважды — ничего не сломалось). Не используйте интерактивные вопросы: всё без ввода (apt-get install -y …).
  4. Пароли и ключи не печатайте в вывод. Время шага ограничено (3–5 минут): долгие задачи запускайте в фоне и проверяйте в status.
  5. На Synology скрипты идут от root через sudo; на OpenWrt — ash; на сервере — под тем пользователем, что указан для SSH.

ЗАПРЕЩЕНО (плагин будет отклонён, объявления не помогают):
{deny}

РИСК считается сам: low (ничего опасного) · medium (пакеты / службы / Docker) · high (перезагрузка или «curl | sh»). Пишите минимально необходимое.

ИНСТРУМЕНТ (kind: "tool") вместо плагина. Если человеку нужна не установка чего-то на устройство, а «кнопка, которая что-то посчитает / проверит и покажет результат», делайте инструмент:
  "kind": "tool" и вместо install / remove / status — "run": [{{"title": "…", "file": "scripts/run.sh"}}]  (один или несколько шагов по порядку).
  Остальное — как у плагина: targets, permissions, network, fields, те же правила и проверка. Инструмент появится в «Инструменты» (а не в «Плагинах»), там выбирают устройство, заполняют поля и нажимают «Запустить».
  Результат рисует Rack Live по строкам вывода:
    "@@kv Подпись|значение"            — строка «подпись — значение» (можно много)
    "@@head Колонка 1|Колонка 2|…"    — заголовок таблицы, затем строки  "@@row яч1|яч2|…"
    обычные строки без @@             — просто текст (журнал, вывод команды)
    "@@ok Итог одной строкой"         — зелёный итог наверху;   "@@fail причина" — ошибка, шаги останавливаются.
  Инструмент ничего не устанавливает: делайте его только читающим, а если он что-то меняет — пишите это в description и объявляйте permissions.

СЦЕНА (kind: "scene") — совсем другое: не рецепт для устройства, а ОПИСАНИЕ ВЫДУМАННОЙ (или спроектированной) СЕТИ: устройства, кабели, Wi-Fi, шкафы, дома с этажами и комнатами. Скриптов в ней НЕТ.
  Нужна, когда просят «большое демо с домами и этажами», «сделай план моего дома», «нарисуй схему сети офиса». Для неё есть отдельная инструкция: «Инструменты → Демо-сцены и планы → Как написать сцену» (файл scene-guide.txt).
  Если человек просит именно это — НЕ делайте плагин: скажите, что нужна сцена, и пользуйтесь той инструкцией.

КАК ПРОВЕРИТЬ: Инструменты → Плагины → «Свои плагины» → «Загрузить .zip». Если отчёт покажет ошибки — исправьте их и соберите архив заново. Готовым плагином или инструментом можно поделиться: приложите .zip к задаче (Issues) в репозитории https://github.com/mikolord/racklive — автор проекта посмотрит и при желании добавит в каталог сообщества.

Плагины и инструменты загружаются одним и тем же окном «Плагины сообщества» (его можно открыть и из «Плагинов», и из «Инструментов»), каждый сам встаёт на своё место.

Когда отдаёте результат человеку: приложите zip, коротко опишите, что плагин делает на устройстве, какие поля заполнить и как его удалить.
'''
