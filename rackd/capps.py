"""Container apps: other people's programs for Rack Live as DATA (an app.json), never as code that runs inside Rack Live.

An app is described, not programmed: which container image (pinned by its sha256 digest), which ports, which named volumes, which settings the administrator is asked for,
and how its interface is opened. Rack Live turns the description into a docker compose file, shows the administrator EXACTLY what will run and what it is allowed to do, and only
after the administrator confirmed it (the confirmation carries the description's digest) starts it on one chosen device (a server over SSH, or a Synology NAS).

Safety rules (a violation refuses the app, whatever it declares):
  · the image is pinned by digest (`name@sha256:…`) and comes from a known registry — a pinned image cannot be swapped after the administrator has looked at it;
  · no privileged mode, no host network / pid / ipc, no docker.sock, no system folders, no unconfined security options, only a short list of Linux capabilities and devices;
  · a memory limit is required (a runaway app must not take the whole NAS down); a port below 1024 is allowed but raises the risk level; Rack Live never forwards a port to the
    internet — opening one is the owner's decision on the router (the page says so in plain words);
  · only named volumes live under Rack Live's control; a folder of the host can be mounted only when the administrator picks it at installation (a `path` field), read-only by default;
  · unknown fields are refused, so a new capability can never slip in unnoticed.
A risk level (low / medium / high) is computed and shown with the permissions in plain words.  APP_API is a contract: change nothing in the format without raising it.

app.json (everything in one file, plus optional README.md / icon.svg|png in the archive):
  {"app_api": 1, "id": "uptime-kuma", "title": "…", "description": "…", "version": "1.23.16", "home": "https://…", "license": "MIT", "author": "…",
   "targets": ["ssh", "synology"],
   "fields": [{"id": "tz", "label": "Часовой пояс", "type": "text", "default": "Europe/Moscow"}, {"id": "music", "label": "Папка с музыкой", "type": "path"}],
   "services": {"app": {"image": "louislam/uptime-kuma@sha256:<64 hex>", "memory": "512m", "cpus": 1,
                        "ports": [{"container": 3001, "host": 3001, "label": "Веб-интерфейс", "web": true}],
                        "volumes": [{"name": "data", "path": "/app/data"}, {"field": "music", "path": "/music", "ro": true}],
                        "env": {"TZ": "${RL_P_TZ}"}, "command": ["…"], "depends_on": ["db"], "caps": ["NET_RAW"], "devices": ["/dev/net/tun"]}},
   "ui": {"mode": "link", "service": "app", "port": 3001, "path": "/", "title": "Открыть Uptime Kuma"}}
ui.mode: «link» — a button opens the app's own address in a new tab (the default; works for every app), «embed» — the interface is shown inside Rack Live (only for apps that allow being
framed), «none» — a background service without an interface (Rack Live shows its state and the address to connect to)."""
import base64, hashlib, json, os, re, shlex, shutil, threading, time

APP_API = 1
ID_RE = re.compile(r'^[a-z][a-z0-9-]{2,30}$')
SVC_RE = re.compile(r'^[a-z][a-z0-9_-]{0,23}$')
FIELD_ID = re.compile(r'^[a-z][a-z0-9_]{0,23}$')
VOL_RE = re.compile(r'^[a-z][a-z0-9_-]{0,23}$')
ENV_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
REF_RE = re.compile(r'\$\{RL_P_([A-Z0-9_]+)\}')
MEM_RE = re.compile(r'^(\d{1,5})([mg])$')
REGISTRIES = ('docker.io', 'ghcr.io', 'lscr.io', 'quay.io', 'mcr.microsoft.com')
IMAGE_RE = re.compile(r'^(?:(?P<reg>[a-z0-9\-]+(?:\.[a-z0-9\-]+)+(?::\d+)?|[a-z0-9.\-]+:\d+)/)?(?P<name>[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*)@sha256:(?P<dig>[0-9a-f]{64})$')
CAPS = {'NET_BIND_SERVICE': 'low', 'CHOWN': 'low', 'SETUID': 'low', 'SETGID': 'low', 'DAC_OVERRIDE': 'low', 'FOWNER': 'low', 'NET_RAW': 'medium', 'NET_ADMIN': 'high'}
DEVICES = {'/dev/net/tun': 'high', '/dev/dri': 'medium'}
CAP_RU = {'NET_BIND_SERVICE': 'открывать порты ниже 1024 внутри контейнера', 'CHOWN': 'менять владельца своих файлов', 'SETUID': 'менять пользователя внутри контейнера',
          'SETGID': 'менять группу внутри контейнера', 'DAC_OVERRIDE': 'обходить права доступа к файлам внутри контейнера', 'FOWNER': 'менять права своих файлов внутри контейнера', 'NET_RAW': 'отправлять сырые сетевые пакеты (ping, сканирование)', 'NET_ADMIN': 'управлять сетью устройства: интерфейсами, маршрутами, правилами'}
DEV_RU = {'/dev/net/tun': 'создавать VPN-туннели (устройство /dev/net/tun)', '/dev/dri': 'использовать видеокарту (/dev/dri)'}
FORMATS = {'host': r'^[A-Za-z0-9.\-]{1,253}$', 'port': r'^\d{1,5}$', 'domain': r'^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$', 'word': r'^[\w.\-]{1,60}$', 'path': r'^/[\w./\-]{0,200}$'}
# host folders a `path` field may never point at (also checked again at installation)
SYSTEM_PATHS = ('/', '/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64', '/var', '/boot', '/root', '/proc', '/sys', '/dev', '/run', '/volume1/@docker', '/var/run', '/opt')
MAX_SERVICES, MAX_PORTS, MAX_VOLUMES, MAX_ENV, MAX_FIELDS = 5, 8, 8, 30, 12
TOP = {'app_api', 'id', 'title', 'description', 'version', 'home', 'license', 'author', 'targets', 'fields', 'services', 'ui'}
SVC_KEYS = {'image', 'memory', 'cpus', 'ports', 'volumes', 'env', 'command', 'depends_on', 'caps', 'devices', 'user'}
PORT_KEYS = {'container', 'host', 'proto', 'label', 'web', 'fixed'}
VOL_KEYS = {'name', 'field', 'path', 'ro'}
UI_KEYS = {'mode', 'service', 'port', 'path', 'title', 'scheme'}
FIELD_KEYS = {'id', 'label', 'type', 'default', 'options', 'required', 'hint', 'format', 'min', 'max'}
TARGETS = {'ssh': ('ssh', 'demo_server'), 'synology': ('synology',)}
EXPOSE_NOTE = ('Приложение доступно только в вашей домашней сети. Чтобы открыть порт из интернета, зайдите на роутер и пробросьте нужный порт на адрес устройства, где оно запущено. '
               'Rack Live этого не делает и не может сделать за вас: это решение владельца сети.')
LEVEL = {'low': 0, 'medium': 1, 'high': 2}
EXAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capps_examples')


def digest(m):
    """a fingerprint of everything that will run: the page shows it, and the start must carry the same one"""
    keys = ('id', 'version', 'targets', 'fields', 'services', 'ui')
    return hashlib.sha256(json.dumps({k: m.get(k) for k in keys}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _q(v):
    return json.dumps(v, ensure_ascii=False)                  # JSON strings are valid YAML scalars


def compose(m):
    """the docker compose file that the administrator is shown (and later run): project rl-<id>, only what was declared"""
    pid = 'rl-' + m['id']
    out = [f'name: {pid}', 'services:']
    named = []
    for sn, s in m['services'].items():
        out.append(f'  {sn}:')
        out.append(f'    image: {_q(s["image"])}')
        out.append('    restart: unless-stopped')
        out.append(f'    mem_limit: {s["memory"]}')
        out.append('    cap_drop: [ALL]')
        if s['caps']:
            out.append('    cap_add: [' + ', '.join(s['caps']) + ']')
        out.append('    security_opt: ["no-new-privileges:true"]')
        if s.get('user'):
            out.append(f'    user: {_q(s["user"])}')
        if s['devices']:
            out.append('    devices:')
            out += [f'      - {_q(d + ":" + d)}' for d in s['devices']]
        if s['ports']:
            out.append('    ports:')
            out += [f'      - {_q("%d:%d/%s" % (p["host"], p["container"], p["proto"]))}' for p in s['ports']]
        if s['volumes']:
            out.append('    volumes:')
            for v in s['volumes']:
                if v.get('name'):
                    named.append(v['name'])
                    out.append(f'      - {_q(v["name"] + ":" + v["path"])}')
                else:
                    out.append(f'      - {_q("${RL_P_" + v["field"].upper() + "}:" + v["path"] + (":ro" if v["ro"] else ""))}')
        if s['env']:
            out.append('    environment:')
            out += [f'      {k}: {_q(v)}' for k, v in s['env'].items()]
        if s['command']:
            out.append('    command: [' + ', '.join(_q(c) for c in s['command']) + ']')
        if s['depends_on']:
            out.append('    depends_on: [' + ', '.join(s['depends_on']) + ']')
        out.append('    labels:')
        out.append(f'      racklive.app: {_q(m["id"])}')
    if named:
        out.append('volumes:')
        out += [f'  {n}: {{}}' for n in dict.fromkeys(named)]
    return '\n'.join(out) + '\n'


def port_key(sn, p):
    return f'{sn}:{p["container"]}/{p["proto"]}'


def apply_ports(m, chosen):
    """the manifest with the administrator's own host ports ({"app:8443/tcp": 9443}); ValueError says why not. The compose file is rebuilt, so what is shown is what runs."""
    chosen = chosen or {}
    if not isinstance(chosen, dict):
        raise ValueError('порты: неверный формат')
    m = json.loads(json.dumps(m))
    known = {port_key(sn, p): p for sn, s in m['services'].items() for p in s['ports']}
    for k in chosen:
        if k not in known:
            raise ValueError(f'порт «{k}» не найден в описании приложения')
    used = {}
    for k, p in known.items():
        v = chosen.get(k, p['host'])
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValueError(f'порт «{p["label"] or k}»: нужно число')
        if not 1 <= v <= 65535:
            raise ValueError(f'порт «{p["label"] or k}»: от 1 до 65535')
        if v != p['host'] and p.get('fixed'):
            raise ValueError(f'порт «{p["label"] or k}» менять нельзя: без него приложение не заработает')
        if (v, p['proto']) in used:
            raise ValueError(f'порт {v}/{p["proto"]} выбран дважды')
        used[(v, p['proto'])] = k
        p['host'] = v
    m['compose'] = compose(m)
    return m


def check(files):
    """→ (errors, warnings, manifest | None). `files` = {path: bytes}. The manifest comes back normalised, with risk, permissions in words, the compose file and a digest."""
    errors, warnings = [], []
    if 'app.json' not in files:
        return ['в архиве нет app.json'], [], None
    try:
        raw = json.loads(files['app.json'].decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as e:
        return [f'app.json: не читается ({e})'], [], None
    if not isinstance(raw, dict):
        return ['app.json должен быть объектом'], [], None
    for k in raw:
        if k not in TOP:
            errors.append(f'неизвестное поле «{k}» (ничего лишнего: так новая возможность не проскочит незамеченной)')
    if raw.get('app_api') != APP_API:
        errors.append(f'app_api должен быть {APP_API} (у этой версии Rack Live именно такой формат)')
    aid = str(raw.get('id') or '')
    if not ID_RE.match(aid):
        errors.append('id: 3–31 символов, латиница в нижнем регистре, цифры и дефис, начинается с буквы')
    title = str(raw.get('title') or '').strip()
    if not title or len(title) > 60:
        errors.append('title: нужно название до 60 символов')
    desc = str(raw.get('description') or '').strip()
    if not desc or len(desc) > 400:
        errors.append('description: нужно описание до 400 символов')
    if not re.match(r'^[\w.\-+]{1,40}$', str(raw.get('version') or '')):
        errors.append('version: версия приложения, например 1.23.16')
    home = str(raw.get('home') or '')
    if home and not re.match(r'^https://[^\s]+$', home):
        errors.append('home: только https-ссылка')
    lic = str(raw.get('license') or '')
    if lic and not re.match(r'^[\w.\-+ ]{1,40}$', lic):
        errors.append('license: короткое название лицензии, например MIT')
    targets = raw.get('targets')
    if not isinstance(targets, list) or not targets or any(t not in TARGETS for t in targets):
        errors.append('targets: список из ' + ', '.join(TARGETS) + ' (где приложение можно запускать; на устройстве должен быть Docker)')
        targets = []

    fields, seen = [], set()
    rf = raw.get('fields') or []
    if not isinstance(rf, list) or len(rf) > MAX_FIELDS:
        errors.append(f'fields: список, не больше {MAX_FIELDS}')
        rf = []
    for f in rf:
        if not isinstance(f, dict) or not FIELD_ID.match(str(f.get('id') or '')) or f['id'] in seen:
            errors.append('поле формы: id латиницей (a-z, 0-9, _), без повторов')
            continue
        for k in f:
            if k not in FIELD_KEYS:
                errors.append(f'поле {f["id"]}: неизвестное свойство «{k}»')
        seen.add(f['id'])
        t = f.get('type', 'text')
        if t not in ('text', 'password', 'number', 'select', 'switch', 'path'):
            errors.append(f'поле {f["id"]}: тип text / password / number / select / switch / path')
            continue
        if f.get('format') and f['format'] not in FORMATS:
            errors.append(f'поле {f["id"]}: format — один из ' + ', '.join(FORMATS))
        if t == 'select' and not (isinstance(f.get('options'), list) and f['options'] and all(isinstance(o, list) and len(o) == 2 for o in f['options'])):
            errors.append(f'поле {f["id"]}: для select нужен options [[значение, подпись], …]')
        if t == 'path' and f.get('default') and (not isinstance(f['default'], str) or _system_path(f['default'])):
            errors.append(f'поле {f["id"]}: папка по умолчанию не может быть системной')
        fields.append({k: f.get(k) for k in ('id', 'label', 'type', 'default', 'options', 'required', 'hint', 'format', 'min', 'max') if f.get(k) is not None} | {'type': t})
    ftype = {f['id']: f['type'] for f in fields}

    services = {}
    rs = raw.get('services')
    if not isinstance(rs, dict) or not rs or len(rs) > MAX_SERVICES:
        errors.append(f'services: от 1 до {MAX_SERVICES} контейнеров, {{"имя": {{…}}}}')
        rs = {}
    risk, perms = 'low', []

    def bump(level, text):
        nonlocal risk
        if LEVEL[level] > LEVEL[risk]:
            risk = level
        if text not in perms:
            perms.append(text)

    used_host = {}
    web_ports = {}
    for sn, s in rs.items():
        w = f'services.{sn}'
        if not SVC_RE.match(str(sn)) or not isinstance(s, dict):
            errors.append(f'{w}: имя контейнера a-z, 0-9, _ и -, и объект с описанием')
            continue
        for k in s:
            if k not in SVC_KEYS:
                errors.append(f'{w}: «{k}» не разрешено' + (' (привилегированный режим, сеть и процессы устройства приложениям недоступны)' if k in ('privileged', 'network_mode', 'pid', 'ipc', 'cap_add', 'security_opt', 'sysctls', 'userns_mode') else ''))
        img = str(s.get('image') or '')
        mi = IMAGE_RE.match(img)
        if not mi:
            errors.append(f'{w}.image: образ должен быть закреплён по хешу: «имя@sha256:<64 символа>» (так его нельзя подменить после проверки)')
        else:
            reg = mi.group('reg') or 'docker.io'
            if reg not in REGISTRIES:
                errors.append(f'{w}.image: реестр «{reg}» не разрешён (можно: {", ".join(REGISTRIES)})')
        mem = str(s.get('memory') or '')
        mm = MEM_RE.match(mem)
        if not mm or not (32 <= int(mm.group(1)) * (1024 if mm.group(2) == 'g' else 1) <= 4096):
            errors.append(f'{w}.memory: обязателен предел памяти от 32m до 4g, например "512m" (приложение не должно съесть всё устройство)')
        cpus = s.get('cpus', 1)
        if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or not 0.1 <= cpus <= 4:
            errors.append(f'{w}.cpus: число от 0.1 до 4')
            cpus = 1
        ports = []
        rp = s.get('ports') or []
        if not isinstance(rp, list) or len(rp) > MAX_PORTS:
            errors.append(f'{w}.ports: список, не больше {MAX_PORTS}')
            rp = []
        for p in rp:
            if not isinstance(p, dict) or any(k not in PORT_KEYS for k in p):
                errors.append(f'{w}.ports: {{"container": 3001, "host": 3001, "label": "…", "web": true}}')
                continue
            c, h, pr = p.get('container'), p.get('host', p.get('container')), p.get('proto', 'tcp')
            if not all(isinstance(x, int) and not isinstance(x, bool) for x in (c, h)) or not (1 <= c <= 65535) or not (1 <= h <= 65535) or pr not in ('tcp', 'udp'):
                errors.append(f'{w}.ports: container и host 1–65535, proto tcp или udp')
                continue
            if (h, pr) in used_host:
                errors.append(f'{w}.ports: порт {h}/{pr} уже занят в этом приложении')
                continue
            used_host[(h, pr)] = sn
            label = str(p.get('label') or '')[:60]
            ports.append({'container': c, 'host': h, 'proto': pr, 'label': label, 'web': bool(p.get('web')), 'fixed': bool(p.get('fixed'))})
            if p.get('web') and pr == 'tcp':
                web_ports[(sn, h)] = label
        if ports:
            bump('low', 'принимает подключения в вашей сети на портах: ' + ', '.join(f'{p["host"]}/{p["proto"]}' for p in ports))
            low = [f'{p["host"]}/{p["proto"]}' for p in ports if p['host'] < 1024]
            if low:
                bump('medium', 'занимает системные порты устройства (ниже 1024): ' + ', '.join(low) + ' — например DNS (53) или веб (80, 443). Если порт занят другой службой, приложение не запустится')
        vols = []
        rv = s.get('volumes') or []
        if not isinstance(rv, list) or len(rv) > MAX_VOLUMES:
            errors.append(f'{w}.volumes: список, не больше {MAX_VOLUMES}')
            rv = []
        for v in rv:
            if not isinstance(v, dict) or any(k not in VOL_KEYS for k in v) or bool(v.get('name')) == bool(v.get('field')):
                errors.append(f'{w}.volumes: нужен либо "name" (том приложения), либо "field" (папка, которую выберет администратор), плюс "path"')
                continue
            path = v.get('path')
            if not isinstance(path, str) or not re.match(r'^/[\w./\-]{0,200}$', path) or '..' in path or re.match(r'^/(proc|sys|dev|var/run|run)(/|$)', path) or 'docker.sock' in path:
                errors.append(f'{w}.volumes: path — абсолютный путь внутри контейнера, не системный и без «..»')
                continue
            if v.get('name'):
                if not VOL_RE.match(str(v['name'])):
                    errors.append(f'{w}.volumes: имя тома a-z, 0-9, _ и -')
                    continue
                vols.append({'name': v['name'], 'path': path})
            else:
                if ftype.get(v['field']) != 'path':
                    errors.append(f'{w}.volumes: поле «{v["field"]}» должно быть объявлено в fields с type "path"')
                    continue
                ro = v.get('ro', True)
                vols.append({'field': v['field'], 'path': path, 'ro': bool(ro)})
                bump('medium' if ro else 'high', ('читает' if ro else 'читает и ПИШЕТ в') + f' папку устройства, которую вы выберете при установке (поле «{v["field"]}»)')
        env = {}
        re_ = s.get('env') or {}
        if not isinstance(re_, dict) or len(re_) > MAX_ENV:
            errors.append(f'{w}.env: объект «имя: значение», не больше {MAX_ENV}')
            re_ = {}
        for k, v in re_.items():
            if not ENV_KEY.match(str(k)) or not isinstance(v, str) or len(v) > 500 or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', v):
                errors.append(f'{w}.env: «{k}» — имя переменной и текстовое значение до 500 символов')
                continue
            for ref in REF_RE.findall(v):
                if ref.lower() not in ftype:
                    errors.append(f'{w}.env.{k}: ссылка ${{RL_P_{ref}}} на несуществующее поле «{ref.lower()}»')
            if re.search(r'\$(?!\{RL_P_[A-Z0-9_]+\})', v):
                errors.append(f'{w}.env.{k}: значение может содержать «$» только в виде ${{RL_P_ПОЛЕ}}')
                continue
            env[k] = v
        cmd = s.get('command') or []
        if not isinstance(cmd, list) or len(cmd) > 30 or any(not isinstance(c, str) or len(c) > 300 or '$' in c for c in cmd):
            errors.append(f'{w}.command: список строк до 300 символов, без «$»')
            cmd = []
        caps = s.get('caps') or []
        if not isinstance(caps, list) or any(c not in CAPS for c in caps):
            errors.append(f'{w}.caps: можно только ' + ', '.join(CAPS))
            caps = []
        for c in caps:
            bump(CAPS[c], 'просит право: ' + CAP_RU[c])
        devs = s.get('devices') or []
        if not isinstance(devs, list) or any(d not in DEVICES for d in devs):
            errors.append(f'{w}.devices: можно только ' + ', '.join(DEVICES))
            devs = []
        for d in devs:
            bump(DEVICES[d], 'просит доступ к устройству: ' + DEV_RU[d])
        dep = s.get('depends_on') or []
        if not isinstance(dep, list) or any(d not in rs or d == sn for d in dep):
            errors.append(f'{w}.depends_on: имена других контейнеров этого приложения')
            dep = []
        user = s.get('user')
        if user is not None and not re.match(r'^\d{1,5}(:\d{1,5})?$', str(user)):
            errors.append(f'{w}.user: числовой «uid» или «uid:gid»')
            user = None
        if isinstance(img, str) and mi:
            services[sn] = {'image': img, 'memory': mem, 'cpus': cpus, 'ports': ports, 'volumes': vols, 'env': env, 'command': cmd, 'depends_on': dep, 'caps': caps, 'devices': devs, 'user': user}
    if len(used_host) > 6:
        bump('medium', 'занимает много портов в вашей сети')
    if any(s['memory'].endswith('g') and int(s['memory'][:-1]) >= 2 for s in services.values()):
        bump('medium', 'может занимать более 2 ГБ памяти')

    ui = raw.get('ui') or {'mode': 'none'}
    if not isinstance(ui, dict) or any(k not in UI_KEYS for k in ui) or ui.get('mode', 'link') not in ('link', 'embed', 'none'):
        errors.append('ui: {"mode": "link" | "embed" | "none", "service": …, "port": …, "path": "/", "title": …}')
        ui = {'mode': 'none'}
    else:
        ui = dict(ui, mode=ui.get('mode', 'link'))
        if ui['mode'] != 'none':
            key = (ui.get('service'), ui.get('port'))
            if key not in web_ports:
                errors.append('ui: service и port должны совпадать с портом, помеченным "web": true')
            if not re.match(r'^/[\w./\-?=&%]{0,200}$', str(ui.get('path') or '/')):
                errors.append('ui.path: путь от корня, например "/" или "/admin"')
            ui['path'] = str(ui.get('path') or '/')
            if ui.get('scheme', 'http') not in ('http', 'https'):
                errors.append('ui.scheme: http или https (по какому адресу открывается интерфейс)')
            ui['scheme'] = ui.get('scheme', 'http')
            ui['title'] = str(ui.get('title') or ('Открыть ' + title))[:60]
            if ui['mode'] == 'embed':
                warnings.append('ui.mode "embed": многие приложения запрещают показ внутри чужой страницы — если оно не откроется, используйте "link"')
    if not any(p['web'] for s in services.values() for p in s['ports']) and ui['mode'] != 'none':
        errors.append('ui: нет порта с "web": true')

    for sn in services:                                           # a cycle in depends_on would make compose refuse the whole file
        seen_d, todo = set(), list(services[sn]['depends_on'])
        while todo:
            d = todo.pop()
            if d == sn:
                errors.append(f'services.{sn}: depends_on зациклен')
                break
            if d not in seen_d and d in services:
                seen_d.add(d)
                todo += services[d]['depends_on']
    for k in files:
        if not re.match(r'^[\w./\-]{1,100}$', k) or k.startswith('/') or '..' in k:
            errors.append(f'файл «{k}» в архиве: недопустимое имя')
    if errors:
        return errors, warnings, None
    m = {'app_api': APP_API, 'id': aid, 'title': title, 'description': desc, 'version': str(raw['version']), 'home': home, 'license': lic, 'author': str(raw.get('author') or '')[:80],
         'targets': targets, 'fields': fields, 'services': services, 'ui': ui}
    m['digest'] = digest(m)
    m['risk'] = risk
    m['permissions'] = perms or ['ничего лишнего: только свои порты и тома']
    m['compose'] = compose(m)
    m['expose_note'] = EXPOSE_NOTE
    return errors, warnings, m


def _system_path(p):
    p = '/' + '/'.join(x for x in str(p).split('/') if x)
    return any(p == s or (s != '/' and p.startswith(s + '/')) for s in SYSTEM_PATHS) or '..' in p


# ───────── on a device: install / start / stop / remove, and what is running ─────────
def clean_values(m, vals):
    """the form → {RL_P_ID: str}; raises ValueError with a readable reason. The values end up in a .env file on the device, so quotes and line breaks are refused."""
    out, vals = {}, vals or {}
    for f in m['fields']:
        v = vals.get(f['id'], f.get('default'))
        t, name = f.get('type', 'text'), f.get('label') or f['id']
        if t == 'switch':
            v = '1' if v in (True, 1, '1', 'true') else '0'
        else:
            v = '' if v is None else str(v)
            if not v and f.get('required'):
                raise ValueError(f'заполните поле «{name}»')
            if len(v) > 200 or re.search(r"[\x00-\x1f\x7f'\\]", v):
                raise ValueError(f'поле «{name}»: недопустимое значение (кавычки, обратная косая черта и переводы строк не разрешены)')
            if v and t == 'number':
                if not re.match(r'^-?\d{1,12}(\.\d+)?$', v):
                    raise ValueError(f'поле «{name}»: нужно число')
                if f.get('min') is not None and float(v) < float(f['min']) or f.get('max') is not None and float(v) > float(f['max']):
                    raise ValueError(f'поле «{name}»: вне допустимых границ')
            if v and t == 'select' and v not in [str(o[0]) for o in f['options']]:
                raise ValueError(f'поле «{name}»: выберите из списка')
            if v and f.get('format') and not re.match(FORMATS[f['format']], v):
                raise ValueError(f'поле «{name}»: неверный формат ({f["format"]})')
            if v and t == 'path' and (not re.match(r'^/[\w./\- ]{1,200}$', v) or _system_path(v)):
                raise ValueError(f'поле «{name}»: нужна обычная папка (не системная), например /volume1/music')
        out['RL_P_' + f['id'].upper()] = v
    return out


PRELUDE = r'''
command -v docker >/dev/null 2>&1 || { echo "@@fail На устройстве не найден Docker"; exit 0; }
docker compose version >/dev/null 2>&1 || { echo "@@fail У Docker на устройстве нет модуля compose (нужен Docker Compose v2)"; exit 0; }
if [ -n "$RL_APPS_BASE" ]; then B="$RL_APPS_BASE"; elif [ -d /volume1 ]; then B=/volume1/docker/racklive-apps; else B=/opt/racklive-apps; fi
mkdir -p "$B/@ID@" 2>/dev/null || { B="$HOME/racklive-apps"; mkdir -p "$B/@ID@" || { echo "@@fail Не удалось создать папку приложения на устройстве"; exit 0; }; }
D="$B/@ID@"; P=rl-@ID@
C() { docker compose -p "$P" -f "$D/compose.yml" --env-file "$D/.env" "$@"; }
LIST() { docker ps -a --filter "label=racklive.app=@ID@" --format '@@c {{.Names}}|{{.State}}|{{.Status}}|{{.Ports}}'; }
LISTEN() { cat /proc/net/$1 /proc/net/${1}6 2>/dev/null | awk -v pr=$1 '$1 ~ /:$/ && ($4=="0A" || pr=="udp") {n=split($2,a,":"); print a[n]}' | sort -u | while read h; do printf '%d\n' "0x$h"; done; }
'''


def _pre(m):
    return PRELUDE.replace('@ID@', m['id'])


def script_install(m, vals):
    env = ''.join(f"{k}='{v}'\n" for k, v in vals.items())
    ports = ' '.join(f'{p["host"]}/{p["proto"]}' for s in m['services'].values() for p in s['ports'])
    return _pre(m) + f'''
if ! docker ps -a --filter "label=racklive.app={m['id']}" -q | grep -q .; then
  for pp in {ports}; do
    n=${{pp%/*}}; pr=${{pp#*/}}
    if LISTEN $pr | grep -qx "$n"; then echo "@@fail Порт $n/$pr на устройстве уже занят другой программой. Выберите другой порт и повторите"; exit 0; fi
  done
fi
printf %s {shlex.quote(base64.b64encode(m['compose'].encode()).decode())} | base64 -d > "$D/compose.yml" || {{ echo "@@fail Не удалось записать файл compose"; exit 0; }}
umask 077
printf %s {shlex.quote(base64.b64encode(env.encode()).decode())} | base64 -d > "$D/.env"
chmod 600 "$D/.env" 2>/dev/null
echo "Скачиваю образы и запускаю (это может занять несколько минут)…"
C up -d --remove-orphans 2>&1 | tail -30
sleep 3
LIST
'''


def script_op(m, op, keep_data=True):
    if op == 'start':
        body = 'C start 2>&1 | tail -10'
    elif op == 'stop':
        body = 'C stop 2>&1 | tail -10'
    elif op == 'restart':
        body = 'C restart 2>&1 | tail -10'
    elif op == 'remove':
        flags = '' if keep_data else ' -v --rmi all'
        body = (f'C down{flags} 2>&1 | tail -20\n'
                'case "$D" in */racklive-apps/*) rm -rf "$D";; esac\necho "@@removed 1"')
    else:
        raise ValueError('неизвестное действие')
    return _pre(m) + f'''
[ -f "$D/compose.yml" ] || {{ echo "@@fail На устройстве нет этого приложения"; exit 0; }}
{body}
sleep 1
LIST
'''


def script_ports(m):
    """what listens on the device right now (from /proc, so it works without ss/netstat) and which containers publish which ports"""
    return _pre(m) + '''
if docker ps -a --filter "label=racklive.app=@ID@" -q 2>/dev/null | grep -q .; then echo "@@installed 1"; exit 0; fi
for pr in tcp udp; do echo "@@listen $pr $(LISTEN $pr | tr '\\n' ' ')"; done
docker ps --format '@@d {{.Names}}|{{.Ports}}' 2>/dev/null
'''.replace('@ID@', m['id'])


PUB = re.compile(r'(?:[\d.]*|\[?[0-9a-f:]*\]?):(\d+)(?:-(\d+))?->(\d+)(?:-\d+)?/(tcp|udp)')


def parse_ports(out, wanted):
    """script output + [(host, proto, label)] → {installed, ports: [{host, proto, busy, by, free}]}; `free` = the nearest free port above, to offer"""
    if '@@installed' in out:
        return {'installed': True, 'ports': []}
    listen = {'tcp': set(), 'udp': set()}
    by = {}
    for l in out.splitlines():
        if l.startswith('@@listen '):
            p = l.split()
            if len(p) >= 2 and p[1] in listen:
                listen[p[1]] |= {int(x) for x in p[2:] if x.isdigit()}
        elif l.startswith('@@d '):
            name, _, ports = l[4:].partition('|')
            for a, b, _c, pr in PUB.findall(ports):
                for n in range(int(a), int(b or a) + 1):
                    by[(n, pr)] = name[:40]
    taken = {(h, pr) for h, pr, _ in wanted}
    res = []
    for h, pr, _ in wanted:
        busy = h in listen[pr] or (h, pr) in by
        free = None
        if busy:
            free = next((n for n in range(h + 1, min(h + 200, 65535) + 1) if n not in listen[pr] and (n, pr) not in by and (n, pr) not in taken), None)
        res.append({'host': h, 'proto': pr, 'busy': busy, 'by': by.get((h, pr)) or '', 'free': free})
    return {'installed': False, 'ports': res}


SCRIPT_STATES = r'''
command -v docker >/dev/null 2>&1 || { echo "@@nodocker 1"; exit 0; }
docker ps -a --filter "label=racklive.app" --format '@@c {{.Label "racklive.app"}}|{{.Names}}|{{.State}}|{{.Status}}|{{.Ports}}'
'''


def parse_states(out):
    """script output → {app_id: {state, containers: [{name, state, status}]}}"""
    res, nodocker = {}, False
    for l in out.splitlines():
        if l.startswith('@@nodocker'):
            nodocker = True
        if not l.startswith('@@c '):
            continue
        parts = l[4:].split('|')
        if len(parts) < 4 or not ID_RE.match(parts[0]):
            continue
        a = res.setdefault(parts[0], {'containers': [], 'ports': []})
        a['containers'].append({'name': parts[1][:60], 'state': parts[2][:20], 'status': parts[3][:60]})
        for h, _b, c, pr in PUB.findall(parts[4] if len(parts) > 4 else ''):      # the ports the app really got (the administrator may have changed them)
            q = {'host': int(h), 'container': int(c), 'proto': pr}
            if q not in a['ports']:
                a['ports'].append(q)
    for a in res.values():
        st = {c['state'] for c in a['containers']}
        a['state'] = 'running' if st == {'running'} else 'stopped' if st <= {'exited', 'created', 'dead'} else 'partial'
    if nodocker:
        res['_nodocker'] = True
    return res


def parse_list(out, pid):
    """the LIST lines of one app (@@c name|state|status|ports)"""
    cs = []
    for l in out.splitlines():
        if l.startswith('@@c '):
            p = l[4:].split('|')
            if len(p) >= 3:
                cs.append({'name': p[0][:60], 'state': p[1][:20], 'status': p[2][:60]})
    st = {c['state'] for c in cs}
    return {'containers': cs, 'state': 'none' if not cs else 'running' if st == {'running'} else 'stopped' if st <= {'exited', 'created', 'dead'} else 'partial'}


class Apps:
    """installed app DESCRIPTIONS (data/capps/<id>.json); what runs on which device is read from Docker itself (the racklive.app label), not remembered here"""
    def __init__(self, data_dir):
        self.dir = os.path.join(data_dir, 'capps')
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()

    def _path(self, pid):
        return os.path.join(self.dir, pid + '.json')

    def get(self, pid):
        if not ID_RE.match(pid or ''):
            return None
        try:
            with open(self._path(pid), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def list(self):
        return [m for m in (self.get(n[:-5]) for n in sorted(os.listdir(self.dir)) if n.endswith('.json')) if m]

    @staticmethod
    def public(m):
        return {k: m.get(k) for k in ('id', 'title', 'description', 'version', 'author', 'home', 'license', 'targets', 'fields', 'risk', 'permissions', 'digest', 'ui', 'compose', 'expose_note', 'added')} \
            | {'ports': [{'service': sn, 'key': port_key(sn, p), **p} for sn, s in m['services'].items() for p in s['ports']]} \
            | {'ui': Apps._ui(m)}

    @staticmethod
    def _ui(m):
        """ui + `cport`: the container side of the web port, so the real (possibly changed) host port can be found among the running ports"""
        u = dict(m.get('ui') or {})
        s = m['services'].get(u.get('service')) or {}
        u['cport'] = next((p['container'] for p in s.get('ports', []) if p['host'] == u.get('port') and p['proto'] == 'tcp'), u.get('port'))
        return u

    def add(self, text):
        errors, warnings, m = check({'app.json': str(text or '').encode('utf-8')})
        if errors:
            return {'ok': False, 'errors': errors, 'warnings': warnings}
        m['added'] = int(time.time())
        with self.lock:
            tmp = self._path(m['id']) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(m, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._path(m['id']))
        return {'ok': True, 'errors': [], 'warnings': warnings, 'app': self.public(m)}

    def remove(self, pid):
        if ID_RE.match(pid or ''):
            try:
                os.remove(self._path(pid))
            except OSError:
                pass

    @staticmethod
    def target_of(driver):
        return next((t for t, names in TARGETS.items() if driver in names), None)

    def devices_for(self, m, devices):
        names = {n for t in m['targets'] for n in TARGETS[t]}
        return [d for d in devices if d.get('driver') in names and d.get('enabled', True)]

    @staticmethod
    def states(d, drv):
        out = drv.command(d, SCRIPT_STATES)
        res = parse_states(out)
        if not res and out.strip() and '@@' not in out:                   # Docker answered with an error (no permission, a broken template …), not with an empty list
            raise RuntimeError(out.strip().splitlines()[0][:160])
        return res

    def check_ports(self, d, drv, pid, chosen):
        """before installing: are the chosen host ports free on the device? → {installed, ports: [{key, label, host, proto, fixed, busy, by, free}]}"""
        m = self.get(pid)
        if not m or self.target_of(d.get('driver')) not in m['targets']:
            raise ValueError('приложение не подходит для этого устройства')
        m2 = apply_ports(m, chosen)
        rows = [(port_key(sn, p), p) for sn, s in m2['services'].items() for p in s['ports']]
        rep = parse_ports(drv.command(d, script_ports(m)), [(p['host'], p['proto'], k) for k, p in rows])
        if not rep['installed'] and len(rep['ports']) != len(rows):
            raise RuntimeError('не удалось проверить порты на устройстве')
        for (k, p), r in zip(rows, rep['ports']):
            r.update(key=k, label=p['label'], fixed=p.get('fixed', False), container=p['container'])
        return rep

    def run(self, d, drv, pid, op, params):
        """install / start / stop / restart / remove on one device; → {ok, log, message, state}. The caller (server) has checked the administrator; the digest is checked here."""
        m = self.get(pid)
        if not m or self.target_of(d.get('driver')) not in m['targets']:
            raise ValueError('приложение не подходит для этого устройства')
        if op not in ('install', 'start', 'stop', 'restart', 'remove'):
            raise ValueError('неизвестное действие')
        if op == 'install' and params.get('digest') != m['digest']:
            raise ValueError('описание приложения изменилось после того, как вы его просмотрели. Откройте приложение заново и проверьте')
        progress = params.get('_progress') or (lambda s: None)
        if op == 'install':
            script = script_install(apply_ports(m, params.get('ports')), clean_values(m, params.get('values')))
        else:
            script = script_op(m, op, bool(params.get('keep_data', True)))
        secrets_ = [v for f in m['fields'] if f.get('type') == 'password' for v in [str((params.get('values') or {}).get(f['id']) or '')] if v]
        progress({'install': 'Скачиваю образы и запускаю…', 'start': 'Запускаю…', 'stop': 'Останавливаю…', 'restart': 'Перезапускаю…', 'remove': 'Удаляю…'}[op])
        out = drv.command(d, script)
        body = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', out)
        for sec in secrets_:
            body = body.replace(sec, '***')
        if '@@fail' in body:
            raise RuntimeError(body.split('@@fail', 1)[1].splitlines()[0].strip())
        st = parse_list(body, pid)
        log = [{'cmd': l[:220], 'ok': True, 'msg': ''} for l in body.splitlines() if l.strip() and not l.startswith('@@')][:60]
        removed = '@@removed' in body
        if op == 'install' and st['state'] not in ('running', 'partial'):
            raise RuntimeError('приложение не запустилось: ' + ' | '.join(l[:160] for l in body.splitlines() if l.strip() and not l.startswith('@@'))[-300:])
        words = {'install': 'установлено и запущено', 'start': 'запущено', 'stop': 'остановлено', 'restart': 'перезапущено', 'remove': 'удалено'}
        return {'ok': True, 'log': log, 'state': 'none' if removed else st['state'], 'containers': st['containers'], 'message': f"{m['title']}: {words[op]}"}


class Shim:
    """what start_plugin_job expects of a driver: .plugin(cfg, pid, op, params) — here it runs a container app"""
    def __init__(self, apps, drv):
        self.apps, self.drv = apps, drv
        self.async_ops = ('install', 'start', 'stop', 'restart', 'remove')

    def plugin(self, cfg, pid, op, params):
        try:
            return self.apps.run(cfg, self.drv, pid, op, params)
        except ValueError as e:
            raise RuntimeError(str(e))
