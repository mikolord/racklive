"""«Проверка VPN»: does a VPN or proxy work from THIS network, right now, and what about its setup makes it easy to spot.
It cannot prove resistance to a DPI box: the verdict is about this provider at this moment, and what was not checked is said so.
Links are secrets. They live only in memory during a check: never saved, never logged, and the report has no identifier, password or key."""
import base64, ipaddress, json, os, re, shutil, socket, ssl, statistics, subprocess, secrets, threading, time, urllib.parse, zlib
from . import keenetic_vless as kv
from .doctor import hostname as doctor_hostname

MAX_LINKS = 15
DOWN_URL = 'https://speed.cloudflare.com/__down?bytes=%d'
UP_URL = 'https://speed.cloudflare.com/__up'
PROBE_URL = 'https://www.gstatic.com/generate_204'
IP_URL = 'https://api.ipify.org'
EXIT_URLS = (IP_URL, 'https://ifconfig.me/ip', 'https://icanhazip.com', 'https://checkip.amazonaws.com')
FREEZE_MIN, FREEZE_MAX = 8 * 1024, 64 * 1024      # a connection that stops here looks like the known «freezes after the first kilobytes»
CLOUDFLARE = [ipaddress.ip_network(n) for n in ('173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18', '190.93.240.0/20',
                                                '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13', '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22')]
CDN_ORGS = (('cloudflare', 'Cloudflare'), ('fastly', 'Fastly'), ('akamai', 'Akamai'), ('cloudfront', 'CloudFront'), ('gcore', 'Gcore'), ('g-core', 'Gcore'), ('bunny', 'Bunny'),
            ('datacamp', 'Bunny'), ('edgecenter', 'EdgeCenter'), ('cdnvideo', 'CDNvideo'), ('ngenix', 'NGENIX'), ('stackpath', 'StackPath'), ('cachefly', 'CacheFly'))
SUB_UA = 'v2rayN/7.0'


def is_ip(h):
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _b64(s):
    s = s.strip().replace('-', '+').replace('_', '/')
    return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8')


def _stream_of(q, host, port):
    """Transport and security of a non-VLESS link: the same code as VLESS, so a link means the same thing everywhere."""
    net = q.get('type', 'tcp').lower()
    if net not in kv.NETS:
        raise ValueError(f'транспорт «{net}» Rack Live проверить не умеет')
    sec = q.get('security', 'none').lower()
    if sec not in ('none', 'tls', 'reality'):
        raise ValueError(f'защита «{sec}» Rack Live проверить не умеет')
    v = {'id': '', 'host': host, 'port': port, 'net': kv.NETS[net], 'security': sec, 'q': q}
    return kv.xray_outbound(v)['streamSettings'], kv.NETS[net], sec


def _common(proto, kind, host, port, net, sec, q, name, secret_values, outbound=None):
    return {'proto': proto, 'kind': kind, 'host': host, 'port': port, 'net': 'tcp' if net == 'raw' else net, 'security': sec, 'q': q, 'name': (name or '')[:60],
            'outbound': outbound, 'secrets': [x for x in secret_values if x]}


def parse_link(link):
    """One link → what the check needs. ValueError with a readable reason; the reason never quotes the link."""
    link = link.strip()
    head, hash_, frag = link.partition('#')         # a name after # often has raw spaces; it is only a label and must not make the link invalid
    link = head + hash_ + urllib.parse.quote(frag, safe='%')
    scheme = link.split('://', 1)[0].lower() if '://' in link else ''
    if scheme == 'vless':
        v = kv.parse_vless(link)
        return _common('VLESS', 'прокси', v['host'], v['port'], v['net'], v['security'], v['q'], v['name'], [v['id'], v['q'].get('pbk'), v['q'].get('sid')], kv.xray_outbound(v))
    if scheme == 'vmess':
        try:
            j = json.loads(_b64(link[8:].split('#')[0]))
            host, port = str(j['add']), int(j['port'])
        except (ValueError, KeyError, TypeError):
            raise ValueError('не получилось разобрать ссылку vmess')
        q = {'type': j.get('net') or 'tcp', 'security': j.get('tls') or 'none', 'sni': j.get('sni') or '', 'host': j.get('host') or '', 'path': j.get('path') or '',
             'alpn': j.get('alpn') or '', 'fp': j.get('fp') or '', 'headerType': j.get('type') or ''}
        if q['type'] == 'grpc':
            q['serviceName'] = q['path']
        q = {k: v for k, v in q.items() if v}
        stream, net, sec = _stream_of(q, host, port)
        out = {'tag': 'proxy', 'protocol': 'vmess', 'settings': {'vnext': [{'address': host, 'port': port, 'users': [{'id': str(j.get('id') or ''), 'security': j.get('scy') or 'auto'}]}]}, 'streamSettings': stream}
        return _common('VMess', 'прокси', host, port, net, sec, q, str(j.get('ps') or ''), [str(j.get('id') or '')], out)
    if scheme in ('trojan', 'ss', 'socks', 'socks5', 'hysteria2', 'hy2', 'tuic'):
        u = urllib.parse.urlsplit(link)
        name = urllib.parse.unquote(u.fragment or '')
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        user, host = urllib.parse.unquote(u.username or ''), u.hostname
        try:
            port = u.port
        except ValueError:
            raise ValueError('в ссылке неправильный порт')
        if scheme == 'ss':
            pw = u.password
            if '@' not in u.netloc:                 # ss://base64(method:password@host:port)
                try:
                    m = re.match(r'^(.+?):(.*)@(.+):(\d+)$', _b64(u.netloc))
                except ValueError:
                    m = None
                if not m:
                    raise ValueError('не получилось разобрать ссылку ss')
                user, pw, host, port = m.group(1), m.group(2), m.group(3), int(m.group(4))
            elif pw is None:                        # ss://base64(method:password)@host:port
                try:
                    user, _, pw = _b64(user).partition(':')
                except ValueError:
                    raise ValueError('не получилось разобрать ссылку ss')
            if not host or not port:
                raise ValueError('в ссылке нет адреса или порта сервера')
            out = {'tag': 'proxy', 'protocol': 'shadowsocks', 'settings': {'servers': [{'address': host, 'port': port, 'method': user, 'password': urllib.parse.unquote(pw or '')}]}}
            return _common('Shadowsocks', 'прокси', host, port, 'raw', 'none', q, name, [pw], out)
        if not host or not port:
            raise ValueError('в ссылке нет адреса или порта сервера')
        if scheme == 'trojan':
            q.setdefault('security', 'tls')
            stream, net, sec = _stream_of(q, host, port)
            out = {'tag': 'proxy', 'protocol': 'trojan', 'settings': {'servers': [{'address': host, 'port': port, 'password': user}]}, 'streamSettings': stream}
            return _common('Trojan', 'прокси', host, port, net, sec, q, name, [user], out)
        if scheme in ('socks', 'socks5'):
            pw = urllib.parse.unquote(u.password or '')
            if user and not pw:
                try:
                    user, _, pw = _b64(user).partition(':')
                except ValueError:
                    pass
            srv = {'address': host, 'port': port}
            if user:
                srv['users'] = [{'user': user, 'pass': pw}]
            return _common('SOCKS', 'прокси', host, port, 'raw', 'none', q, name, [user, pw], {'tag': 'proxy', 'protocol': 'socks', 'settings': {'servers': [srv]}})
        proto = 'TUIC' if scheme == 'tuic' else 'Hysteria2'
        return _common(proto, 'прокси на UDP', host, port, 'udp', 'tls', q, name, [user, u.password])
    raise ValueError('этот тип ссылки не поддерживается: нужен vless, vmess, trojan, ss, socks, hysteria2, tuic или настройки WireGuard')


AWG_NOTES = {'1.0': 'Старая версия: меняет только начало соединения, и его признаки уже известны.',
             '1.5': 'Версия 1.0 плюс имитация других протоколов в начале соединения (параметры I1–I5).',
             '2.0': 'Добавлены случайные размеры и заголовки пакетов (S3, S4, диапазоны H), защищено рукопожатие.',
             '3.x': 'Защищён и уже идущий туннель: заголовки шифруются, пакеты дополняются, таймеры случайные. 3.0 и 3.1 по настройкам не различить, нужна версия 3.x на обоих концах.'}
AWG_MASK = {'1.0': 1, '1.5': 1.5, '2.0': 2, '3.x': 2.5}


def awg_version(conf):
    """Which AmneziaWG a config needs, by the parameters it uses (Amnezia's own version table). None: this is plain WireGuard. `conf` has lower-case keys."""
    on = lambda k: str(conf.get(k) or '').lower() not in ('', '0', 'false', 'no', 'off')
    if any(on(k) for k in ('headerprotectionkey', 'contentpaddingaddition', 'randomtrailers', 'disablecookies', 'rekeyaftertime', 'rekeytimeout', 'rejectaftertime', 'keepalivetimeout', 'maxhandshakeattempts')):
        return '3.x'
    heads = [str(conf.get(k) or '') for k in ('h1', 'h2', 'h3', 'h4')]
    if on('s3') or on('s4') or any('-' in h for h in heads):
        return '2.0'
    if any(on(f'i{n}') for n in range(1, 6)):
        return '1.5'
    if any(on(k) for k in ('jc', 'jmin', 'jmax', 's1', 's2')) or any(h and h != str(n + 1) for n, h in enumerate(heads)):
        return '1.0'
    return None


def parse_wg(text):
    """A WireGuard or AmneziaWG config. The keys are read past: only the endpoint and the type stay."""
    sec, f = {}, ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            f = line.strip('[]').lower()
        elif '=' in line and f:
            k, _, val = line.partition('=')
            sec[f + '.' + k.strip().lower()] = val.strip()
    ep = sec.get('peer.endpoint') or ''
    m = re.match(r'^\[?([^\]]+?)\]?:(\d+)$', ep)
    if not m:
        raise ValueError('в настройках WireGuard нет адреса сервера (Endpoint)')
    conf = {k.split('.', 1)[1]: v for k, v in sec.items() if k.startswith('interface.')}
    version = awg_version(conf)
    it = _common('AmneziaWG' if version else 'WireGuard', 'VPN', m.group(1), int(m.group(2)), 'udp', 'none', {}, f'AmneziaWG {version}' if version else 'WireGuard',
                 [conf.get('privatekey'), conf.get('headerprotectionkey'), sec.get('peer.presharedkey')])
    if version:
        size = lambda k: int(conf[k]) if str(conf.get(k) or '').isdigit() else None
        it['awg'] = {'version': version, 'note': AWG_NOTES[version], 'mimicry': bool(conf.get('i1')),
                     'sizeClash': size('s1') is not None and size('s2') is not None and size('s1') + 56 == size('s2')}
    return it


def parse_amnezia(link):
    """A vpn:// link from the Amnezia app: compressed JSON with a WireGuard-style config somewhere inside, sometimes as JSON within JSON."""
    try:
        s = link.strip()[6:].replace('-', '+').replace('_', '/')
        data = zlib.decompress(base64.b64decode(s + '=' * (-len(s) % 4))[4:])
        root = json.loads(data.decode('utf-8'))
    except (ValueError, zlib.error):
        raise ValueError('не получилось разобрать ссылку vpn://')

    def find(o):
        if isinstance(o, dict):
            o = list(o.values())
        if isinstance(o, list):
            return next((r for r in map(find, o) if r), None)
        if isinstance(o, str):
            if o.lstrip().startswith('{'):      # first: JSON within JSON also contains the words, but on one escaped line
                try:
                    return find(json.loads(o))
                except ValueError:
                    return None
            if '[Interface]' in o:
                return o
        return None
    conf = find(root)
    if not conf:
        raise ValueError('в ссылке vpn:// нет настроек AmneziaWG или WireGuard, а другие её виды Rack Live не разбирает')
    it = parse_wg(conf)
    if isinstance(root, dict) and root.get('description'):
        it['name'] = str(root['description'])[:60]
    return it


def advice(it):
    """What in the setup makes it easier to spot. These are rules of thumb, shown as such."""
    out, q, sec = [], it['q'], it['security']
    add = lambda level, text: out.append({'level': level, 'text': text})
    if it['proto'] == 'WireGuard':
        add('bad', 'Обычный WireGuard легко определить по первым пакетам. Если есть выбор, лучше AmneziaWG или VLESS.')
    elif it['proto'] == 'AmneziaWG':
        version = (it.get('awg') or {}).get('version')
        if version in ('1.0', '1.5'):
            add('warn', f'AmneziaWG {version} устарела. Если сервер и приложения позволяют, лучше перейти на 2.0 или 3.x.')
        if (it.get('awg') or {}).get('sizeClash'):
            add('warn', 'S1 + 56 = S2: пакеты рукопожатия получаются одного размера, такие настройки считаются неправильными.')
        add('info', 'AmneziaWG идёт по UDP, а UDP до зарубежных адресов бывает ограничен.')
    elif it['proto'] in ('Hysteria2', 'TUIC'):
        add('warn', 'Протокол идёт поверх UDP (QUIC). Его до зарубежных адресов часто замедляют или режут.')
    elif it['proto'] == 'SOCKS':
        add('bad', 'SOCKS ничего не шифрует и не маскирует: содержимое видно по пути.')
    elif it['proto'] == 'Shadowsocks':
        add('warn', 'Shadowsocks без маскировки под сайт: случайный на вид поток данных вызывает подозрение.')
    elif sec == 'none':
        add('bad', 'Соединение без TLS и Reality: протокол виден прямо в трафике.')
    if sec == 'reality' and it['net'] == 'tcp' and q.get('flow') != 'xtls-rprx-vision':
        add('warn', 'Reality по TCP без flow=xtls-rprx-vision: шифрование внутри шифрования легче заметить по размерам пакетов.')
    if sec in ('tls', 'reality'):
        sni = q.get('sni') or (it['host'] if not is_ip(it['host']) else '')
        if not sni:
            add('warn', 'Нет имени сайта (SNI): обычный браузер так почти не подключается.')
        elif is_ip(sni):
            add('warn', 'В SNI указан IP-адрес: обычный браузер так не делает.')
        if q.get('fp') in ('', None):
            add('info', 'Отпечаток TLS (fp) в ссылке не указан. Rack Live проверяет с chrome, а приложение может выбрать другой.')
        if q.get('allowInsecure') == '1' or q.get('insecure') == '1':
            add('warn', 'Проверка сертификата выключена. К ТСПУ это не относится, но так соединение можно подменить.')
        if it['port'] not in (443, 8443):
            add('info', f'Порт {it["port"]}: TLS обычно идёт на 443, другой порт выделяется в потоке.')
    return out


def classify(tcp, tls, same_neutral, clean_sni, clean_plain):
    """Where the path breaks, from what got an answer. «Похоже»: the same picture can have an innocent cause, so it never says «blocked» as a fact."""
    if not tcp.get('ok'):
        if clean_plain and not clean_plain.get('reached'):
            return 'unknown', 'Отсюда не открывается и контрольный адрес, похоже, нет интернета. Про этот сервер вывода нет.'
        return 'bad', 'Адрес не принимает соединение: сервер выключен, порт закрыт или адрес блокируют по пути.'
    if tls is None:
        return 'ok', 'Соединение с сервером устанавливается.'
    if tls.get('reached'):
        return 'ok', 'Соединение и начало TLS проходят.'
    if clean_sni and not clean_sni.get('reached') and clean_plain and clean_plain.get('reached'):
        return 'bad', 'Похоже на блокировку по имени сайта (SNI): с этим именем не отвечает даже чистый контрольный адрес.'
    if same_neutral and same_neutral.get('reached'):
        return 'bad', 'Похоже на блокировку по имени сайта (SNI): с другим именем этот же сервер отвечает.'
    if same_neutral and not same_neutral.get('reached'):
        return 'bad', 'Порт открыт, а TLS не проходит ни с каким именем: сервис не работает или этот адрес режут по пути.'
    return 'bad', 'Порт открыт, а TLS не проходит.'


def cdn_of(ip, org=''):
    try:
        a = ipaddress.ip_address(ip)
        if any(a in n for n in CLOUDFLARE):
            return 'Cloudflare'
    except ValueError:
        pass
    low = (org or '').lower()
    return next((n for k, n in CDN_ORGS if k in low), None)


def verdict(item, path_state):
    t, block = item.get('tunnel') or {}, item.get('block') or {}
    if t.get('state') == 'ok':
        if t.get('freeze'):
            return 'bad', f'Туннель поднимается, но данные встают после {t["stallAt"] // 1024} КБ. Похоже на обрыв по объёму, с которым VPN на сайтах виснет.'
        if t.get('stalled'):
            return 'warn', 'Туннель работает, но загрузка останавливалась.'
        route = (item.get('route') or {}).get('state')      # what the server itself saw beats the general picture
        way = route if route in ('direct', 'vpn') else path_state
        if way == 'vpn':
            return 'warn', 'Работает, но проверка шла через другой VPN. Про провайдера это ничего не говорит.'
        if way == 'direct':
            return 'ok', 'Работает отсюда напрямую через провайдера, прямо сейчас.'
        if way == 'mixed':
            return 'warn', 'Работает, но роутер отправляет часть адресов через VPN, а путь к этому серверу проверить не удалось.'
        return 'warn', 'Работает, но неясно, шла ли проверка напрямую.'
    if t.get('state') == 'fail':
        if block.get('state') == 'ok':
            return 'bad', 'Сервер отвечает, а туннель не поднялся: ссылка устарела, ключ отключён или соединение режут уже после начала.'
        return block.get('state') or 'bad', block.get('text') or 'Туннель не поднялся.'
    if block.get('state') in ('bad', 'unknown'):
        return block['state'], block['text']
    if t.get('state') == 'config':
        return 'unknown', t.get('note')
    return 'unknown', (t.get('note') or 'Туннель не проверен.') + ' Проверен только путь до сервера.'


PANEL_RE = re.compile(r'3x-ui|x-ui|marzban|marzneshin|remnawave|hiddify|v2board|xboard|sui panel', re.I)
DEFAULT_RE = re.compile(r'welcome to nginx|apache2 [\w ]*default page|it works!|test page for|default web page|caddy works|welcome to openresty', re.I)
DECOY_POINTS = {'site': 1, 'borrowed': 1, 'borrowed_error': .75, 'stub': .75, 'redirect': .5, 'error': .25, 'empty': .25, 'default': .25, 'silent': 0, 'panel': 0}


def classify_decoy(peek, reality=False, trusted=None):
    """What a stranger sees when opening the server like a website. A bare error or a panel tells a prober what this is; a normal site does not.
    Reality has no site of its own: it passes a stranger through to the real one named in SNI, so even that site's own 404 is the disguise working, when the certificate is genuine."""
    out = {'status': peek.get('status'), 'server': peek.get('server'), 'title': peek.get('title')}
    status, body = peek.get('status'), peek.get('body') or ''
    text = ' '.join(str(x) for x in (peek.get('title'), peek.get('server'), body[:20000]) if x)
    if not status:
        return {**out, 'kind': 'silent', 'state': 'warn', 'text': f'На запрос как от браузера сайта нет: {peek.get("error") or "сервер молчит или рвёт соединение"}.'}
    if reality and trusted and not PANEL_RE.search(text):
        if status < 400:
            return {**out, 'kind': 'borrowed', 'state': 'ok', 'text': 'Reality показывает чужому настоящий сайт, сертификат настоящий. Своя заглушка здесь не нужна.'}
        return {**out, 'kind': 'borrowed_error', 'state': 'ok', 'text': f'Reality показывает чужому настоящий сайт с настоящим сертификатом, но его главная страница отвечает ошибкой {status}. Выглядит правдоподобно, сайт с обычной страницей был бы лучше.'}
    if PANEL_RE.search(text):
        return {**out, 'kind': 'panel', 'state': 'bad', 'text': 'Чужому видна панель управления VPN. Это прямо говорит, что здесь за сервер: её лучше закрыть.'}
    if DEFAULT_RE.search(text):
        return {**out, 'kind': 'default', 'state': 'warn', 'text': 'Страница по умолчанию от веб-сервера: сайта как такового нет.'}
    if 300 <= status < 400:
        return {**out, 'kind': 'redirect', 'state': 'ok', 'location': peek.get('location'), 'text': f'Перенаправляет на {peek.get("location") or "другой адрес"}.'}
    if 200 <= status < 300:
        name = f' «{peek["title"]}»' if peek.get('title') else ''
        if len(body) >= 400:
            return {**out, 'kind': 'site', 'state': 'ok', 'text': f'Есть сайт-заглушка{name}: чужой увидит обычную страницу.'}
        if peek.get('title'):
            return {**out, 'kind': 'stub', 'state': 'ok', 'text': f'Есть простая страница-заглушка{name}. Настоящий сайт с содержимым выглядел бы убедительнее.'}
        return {**out, 'kind': 'empty', 'state': 'warn', 'text': 'Отвечает почти пустой страницей без названия: на сайт не похоже.'}
    return {**out, 'kind': 'error', 'state': 'warn', 'text': f'Сайта-заглушки нет: чужому отвечает ошибкой {status}.'}


def score(rep, path_state):
    """0–10 from what was measured and how the setup looks. A rule of thumb with the parts shown, never a promise; and what could not be measured limits the result."""
    parts, t, q_adv = [], rep.get('tunnel') or {}, rep.get('advice') or []
    add = lambda label, got, top, note: parts.append({'label': label, 'got': got, 'max': top, 'note': note})
    tested = t.get('state') in ('ok', 'fail')
    if tested:
        got = 0 if t['state'] == 'fail' else 1 if t.get('freeze') else 2 if t.get('stalled') else 4
        add('Работает отсюда', got, 4, 'туннель не поднялся' if not got else 'данные встают на первых килобайтах' if t.get('freeze') else 'загрузка останавливалась' if t.get('stalled') else 'туннель поднялся, данные идут')
        ok, tries = t.get('okCount') or 0, t.get('tries') or 5
        add('Стабильность', round(ok / tries, 2), 1, f'открылось {ok} из {tries}')
        down = t.get('down')
        add('Скорость', 1 if (down or 0) >= 20 else .5 if (down or 0) >= 5 else 0, 1, f'{down} Мбит/с' if down is not None else 'не измерена')
    proto, sec, net = rep.get('proto'), rep.get('security'), rep.get('net')
    if proto == 'AmneziaWG':
        mask = AWG_MASK.get((rep.get('awg') or {}).get('version'), 1)
    elif proto in ('WireGuard', 'SOCKS') or (sec == 'none' and proto != 'Shadowsocks'):
        mask = 0
    elif proto in ('Hysteria2', 'TUIC', 'Shadowsocks'):
        mask = 1
    elif sec == 'reality':
        mask = 3 if rep.get('flow') == 'xtls-rprx-vision' or net != 'tcp' else 2.5
    else:
        mask = 2.5 if net != 'tcp' else 2
    mask = max(0, mask - .25 * sum(1 for a in q_adv if a['level'] == 'warn' and proto not in ('AmneziaWG', 'Hysteria2', 'TUIC', 'Shadowsocks') and 'flow=' not in a['text']))
    add('Маскировка', mask, 3, f'{proto}, {"без шифрования снаружи" if sec == "none" and net != "udp" else sec if net != "udp" else "UDP"}')
    decoy = rep.get('decoy')
    if decoy:
        add('Сайт-заглушка', DECOY_POINTS.get(decoy.get('kind'), 0), 1, decoy.get('text', ''))
    got, top = sum(p['got'] for p in parts), sum(p['max'] for p in parts)
    val = 10 * got / top if top else 0
    limits = []
    if not tested:
        val = min(val, 5)
        limits.append('туннель не проверен, поэтому не выше 5: оценка только по настройкам')
    elif t['state'] == 'fail':
        val = min(val, 3)
        limits.append('туннель не поднялся, поэтому не выше 3')
    elif t.get('freeze'):
        val = min(val, 4)
        limits.append('данные встают на первых килобайтах, поэтому не выше 4')
    way = (rep.get('route') or {}).get('state')
    way = way if way in ('direct', 'vpn') else path_state
    if tested and way != 'direct':
        val = min(val, 7)
        limits.append('проверка шла не точно через провайдера, поэтому не выше 7')
    return {'value': round(val * 2) / 2, 'parts': parts, 'limits': limits}


def err_kind(e):
    if isinstance(e, socket.gaierror):
        return 'имя не найдено'
    if isinstance(e, (socket.timeout, TimeoutError)):
        return 'нет ответа'
    if isinstance(e, ConnectionRefusedError):
        return 'порт закрыт'
    if isinstance(e, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
        return 'соединение сброшено'
    if isinstance(e, ssl.SSLError):
        return 'ошибка TLS'
    return 'нет соединения'


class Probe:
    """Everything that touches the network. The demo replaces it, so the report never depends on a real server there."""
    timeout = 6

    def resolve(self, host):
        if is_ip(host):
            return [host]
        try:
            seen = []
            for x in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
                if x[4][0] not in seen:
                    seen.append(x[4][0])
            return sorted(seen, key=lambda a: ':' in a)[:4]
        except OSError:
            return []

    def ping(self, ip):
        try:
            r = subprocess.run(['ping', '-n', '-c', '5', '-i', '0.3', '-W', '2', ip], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return {'loss': None, 'avg': None}
        loss = re.search(r'([\d.]+)% packet loss', r.stdout)
        avg = re.search(r'= [\d.]+/([\d.]+)/', r.stdout)
        return {'loss': float(loss.group(1)) if loss else None, 'avg': round(float(avg.group(1)), 1) if avg else None}

    def tcp(self, ip, port, tries=3):
        times, error = [], None
        for _ in range(tries):
            t = time.time()
            try:
                socket.create_connection((ip, port), self.timeout).close()
                times.append((time.time() - t) * 1000)
            except OSError as e:
                error = err_kind(e)
        return {'ok': bool(times), 'ms': round(statistics.median(times), 1) if times else None, 'tries': tries, 'okCount': len(times), 'error': None if times else error}

    def tls(self, ip, port, sni):
        """`reached`: the other side answered in TLS at all, even with an alert or a foreign certificate. Silence or a reset are the suspicious outcomes."""
        ctx = ssl.create_default_context()
        ctx.set_alpn_protocols(['h2', 'http/1.1'])
        t, out = time.time(), {'sni': sni, 'reached': False}
        try:
            with socket.create_connection((ip, port), self.timeout) as raw:
                try:
                    with ctx.wrap_socket(raw, server_hostname=sni) as s:
                        c = s.getpeercert() or {}
                        issuer = dict(x[0] for x in c.get('issuer', ()) if x)
                        out.update(reached=True, trusted=True, version=s.version(), alpn=s.selected_alpn_protocol(), issuer=issuer.get('organizationName') or issuer.get('commonName'))
                except ssl.SSLCertVerificationError:
                    out.update(reached=True, trusted=False)
                except ssl.SSLError as e:
                    if 'ALERT' in str(e).upper():           # the server replied, it just did not like the name
                        out.update(reached=True, trusted=False, alert=True)
                    else:
                        out['error'] = err_kind(e)
            out['ms'] = round((time.time() - t) * 1000, 1)
        except OSError as e:
            out['error'] = err_kind(e)
        return out

    def peek(self, ip, port, host, use_tls):
        """Open the server the way a browser or a prober would: the main page, no key. Only what it says about itself is kept."""
        out = {'status': None, 'server': None, 'title': None, 'location': None, 'body': '', 'error': None}
        s = None
        try:
            s = socket.create_connection((ip, port), self.timeout)
            s.settimeout(self.timeout)
            if use_tls:
                ctx = ssl.create_default_context()
                ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname=host if not is_ip(host) else None)
            s.sendall(f'GET / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36\r\nAccept: text/html,*/*\r\nConnection: close\r\n\r\n'.encode())
            buf, t0 = b'', time.time()
            while len(buf) < 65536 and time.time() - t0 < self.timeout:
                d = s.recv(16384)
                if not d:
                    break
                buf += d
            head, _, body = buf.partition(b'\r\n\r\n')
            lines = head.decode('latin-1', 'replace').split('\r\n')
            m = re.match(r'HTTP/\d\.?\d? (\d+)', lines[0])
            if m:
                h = {k.strip().lower(): v.strip() for k, _, v in (x.partition(':') for x in lines[1:])}
                text = body.decode('utf-8', 'replace')
                t = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
                out.update(status=int(m.group(1)), server=(h.get('server') or '')[:40] or None, location=(h.get('location') or '')[:120] or None, body=text,
                           title=re.sub(r'\s+', ' ', t.group(1)).strip()[:80] if t else None)
        except (socket.timeout, TimeoutError) as e:
            out['error'] = err_kind(e)
            if s is None:
                return out
        except OSError as e:
            out['error'] = err_kind(e)
        finally:
            if s:
                try:
                    s.close()
                except OSError:
                    pass
        return out

    def _socks(self, s, host, port):
        s.sendall(b'\x05\x01\x00')
        if s.recv(2) != b'\x05\x00':
            raise ConnectionError('socks')
        h = host.encode()
        s.sendall(b'\x05\x01\x00\x03' + bytes([len(h)]) + h + port.to_bytes(2, 'big'))
        r = s.recv(4)
        if len(r) < 4 or r[1] != 0:
            raise ConnectionError('socks')
        size = s.recv(1)[0] if r[3] == 3 else 16 if r[3] == 4 else 4
        s.recv(size + 2)

    def fetch(self, url, proxy=None, connect_ip=None, limit=1 << 20, time_limit=10, stall=6, upload=0, keep=0):
        """A small HTTP client that sees what urllib hides: how many bytes came before the connection went silent."""
        u = urllib.parse.urlsplit(url)
        host, port = u.hostname, u.port or (443 if u.scheme == 'https' else 80)
        out = {'ok': False, 'status': None, 'bytes': 0, 'sent': 0, 'stalled': False, 'seconds': 0, 'error': None, 'ms': None, 'body': b''}
        t0, s = time.time(), None
        try:
            if proxy:
                s = socket.create_connection(('127.0.0.1', proxy), self.timeout + 4)
                s.settimeout(self.timeout + 4)
                self._socks(s, host, port)
            else:
                s = socket.create_connection((connect_ip or host, port), self.timeout + 4)
                s.settimeout(self.timeout + 4)
            if u.scheme == 'https':
                s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
            path = (u.path or '/') + ('?' + u.query if u.query else '')
            head = f'{"POST" if upload else "GET"} {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nAccept: */*\r\nConnection: close\r\n'
            if upload:
                head += f'Content-Type: application/octet-stream\r\nContent-Length: {upload}\r\n'
            s.sendall((head + '\r\n').encode())
            start = time.time()
            if upload:
                chunk, left = os.urandom(65536), upload
                while left > 0 and time.time() - start < time_limit:
                    n = min(left, 65536)
                    s.sendall(chunk[:n])
                    left -= n
                out['sent'] = upload - left
                out['seconds'] = round(time.time() - start, 2)
                if left > 0:                                # time is up: the amount already sent is the measure
                    out.update(ok=True, status=200)
                    return out
            buf, header = b'', True
            sent_at, start, first = start, time.time(), time.time()
            while time.time() - start < time_limit and out['bytes'] < limit:
                s.settimeout(max(.2, min(stall, time_limit - (time.time() - start))))
                try:
                    d = s.recv(65536)
                except (socket.timeout, TimeoutError):
                    if time.time() - start < time_limit - .3:
                        out['stalled'] = True
                    break
                if not d:
                    break
                if out['ms'] is None:
                    out['ms'] = round((time.time() - t0) * 1000, 1)
                    first = time.time()
                if header:
                    buf += d
                    i = buf.find(b'\r\n\r\n')
                    if i < 0:
                        continue
                    m = re.match(rb'HTTP/\d\.?\d? (\d+)', buf)
                    out['status'] = int(m.group(1)) if m else None
                    d, header = buf[i + 4:], False
                    if upload:                      # local buffers swallow data at once: an upload ends when the far side says it got everything
                        out['seconds'] = round(time.time() - sent_at, 2)
                        break
                out['bytes'] += len(d)
                if keep and len(out['body']) < keep:
                    out['body'] += d[:keep - len(out['body'])]
            if not upload:
                out['seconds'] = round(time.time() - first, 2)
            out['ok'] = bool(out['status']) and 200 <= out['status'] < 300
        except OSError as e:
            out['error'] = err_kind(e)
        finally:
            if s:
                try:
                    s.close()
                except OSError:
                    pass
        return out

    def ip_info(self, ip):
        """Who owns an address. Goes to a public lookup service: only the bare address, never a link."""
        r = self.fetch('https://ipwho.is/' + ip, limit=32768, keep=32768, time_limit=8)
        try:
            j = json.loads(r['body'].decode('utf-8', 'replace'))
            if j.get('success'):
                c = j.get('connection') or {}
                return {'country': j.get('country_code'), 'countryName': j.get('country'), 'org': c.get('org') or c.get('isp'), 'isp': c.get('isp'), 'asn': c.get('asn')}
        except ValueError:
            pass
        r = self.fetch('http://ip-api.com/json/' + ip + '?fields=status,countryCode,country,isp,org,as', limit=8192, keep=8192, time_limit=8)
        try:
            j = json.loads(r['body'].decode('utf-8', 'replace'))
            if j.get('status') == 'success':
                return {'country': j.get('countryCode'), 'countryName': j.get('country'), 'org': j.get('org') or j.get('isp'), 'isp': j.get('isp'), 'asn': j.get('as')}
        except ValueError:
            pass
        return {}

    def my_ip(self, proxy=None):
        for url in (IP_URL, 'https://ifconfig.me/ip', 'https://icanhazip.com'):
            r = self.fetch(url, proxy=proxy, limit=256, keep=256, time_limit=10)
            ip = r['body'].decode('ascii', 'replace').strip()
            if r['ok'] and is_ip(ip):
                return ip
        return None

    def exits(self):
        """What several services see. A router with rules per address sends some of them through a VPN and others not, so one answer proves nothing."""
        out = []
        for url in EXIT_URLS:
            r = self.fetch(url, limit=256, keep=256, time_limit=8)
            ip = r['body'].decode('ascii', 'replace').strip()
            if r['ok'] and is_ip(ip):
                out.append((urllib.parse.urlsplit(url).hostname, ip))
        return out

    def cf_seen(self, connect_ip=None):
        """The address Cloudflare sees, on the same edge the measurement used: was that measurement really direct?"""
        r = self.fetch('https://speed.cloudflare.com/cdn-cgi/trace', connect_ip=connect_ip, limit=4096, keep=4096, time_limit=8)
        m = re.search(r'^ip=(\S+)$', r['body'].decode('ascii', 'replace'), re.M)
        return m.group(1) if m else None

    def server_peers(self, d, ip, port):
        """Who the server sees on this port, while one connection of ours is held open → [(ip, port)], our local port. None: could not look."""
        from .drivers import REGISTRY
        try:
            s = socket.create_connection((ip, port), self.timeout)
        except OSError:
            return None, None
        try:
            mine = s.getsockname()[1]
            out = REGISTRY[d['driver']]._run(d, "ss -tnH 2>/dev/null | awk '{print $4, $5}'", timeout=25)
        except Exception:
            return None, None
        finally:
            s.close()
        peers = []
        for line in (out or '').splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0].rsplit(':', 1)[-1] == str(port):
                h, _, p = parts[1].rpartition(':')
                peers.append((h.strip('[]').replace('::ffff:', ''), p))
        return peers, str(mine)

    def measure(self, proxy=None):
        """Latency, download and upload over one path. Download is cut by time, so a slow link gets a fair number and a fast one does not eat the provider's limit."""
        probes = [self.fetch(PROBE_URL, proxy=proxy, limit=1024, time_limit=8, stall=6) for _ in range(5)]
        good = [p['ms'] for p in probes if p['status'] in (200, 204) and p['ms'] is not None]
        d = self.fetch(DOWN_URL % (60 << 20), proxy=proxy, limit=60 << 20, time_limit=10, stall=6)
        up = self.fetch(UP_URL, proxy=proxy, upload=15 << 20, time_limit=8, stall=6)
        freeze = bool(d['stalled'] and FREEZE_MIN <= d['bytes'] <= FREEZE_MAX)
        mbit = lambda b, s: round(b * 8 / s / 1e6, 1) if s and b > 65536 else None
        return {'okCount': len(good), 'tries': len(probes), 'firstMs': good[0] if good else None, 'ms': round(statistics.median(good[1:] or good), 1) if good else None,
                'down': mbit(d['bytes'], d['seconds']) if d['status'] == 200 else None, 'downError': None if d['status'] == 200 else (d['error'] or (f'код {d["status"]}' if d['status'] else 'нет ответа')),
                'up': mbit(up['sent'], up['seconds']) if up['ok'] else None, 'stalled': d['stalled'], 'stallAt': d['bytes'] if d['stalled'] else None, 'freeze': freeze}

    def tunnel(self, it, on_up=None, host=None):
        """A separate Xray bound to localhost for this one check; the config goes on stdin, so no secret reaches the disk."""
        if not it.get('outbound'):
            return {'state': 'skip', 'note': f'{it["proto"]}: туннель этого типа Rack Live не поднимает.'}
        xray = shutil.which('xray') or ('/usr/local/bin/xray' if os.path.exists('/usr/local/bin/xray') else None)
        if not xray:
            return {'state': 'skip', 'note': 'В этой установке нет ядра Xray, настоящий туннель не проверен.'}
        with socket.socket() as sk:
            sk.bind(('127.0.0.1', 0))
            port = sk.getsockname()[1]
        out = json.loads(json.dumps(it['outbound']))
        if host:
            vnext = (out.get('settings') or {}).get('vnext') or (out.get('settings') or {}).get('servers')
            vnext[0]['address'] = host
        cfg = {'log': {'loglevel': 'warning'}, 'inbounds': [{'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'udp': False}}], 'outbounds': [out]}
        p = subprocess.Popen([xray, 'run', '-c', 'stdin:'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            p.stdin.write(json.dumps(cfg).encode())
            p.stdin.close()
            for _ in range(40):
                if p.poll() is not None:
                    said = p.stdout.read().decode('utf-8', 'replace')
                    why = said.rpartition('Failed to start:')[2].strip()[-400:]
                    return {'state': 'config', 'note': 'Ядро Xray не приняло настройки этой ссылки, поэтому про сервер это ничего не говорит.', 'detail': scrub(why, it)}
                try:
                    socket.create_connection(('127.0.0.1', port), .25).close()
                    break
                except OSError:
                    time.sleep(.25)
            m = self.measure(proxy=port)
            if not m['okCount']:
                return {'state': 'fail', 'note': 'Через туннель не открылась проверочная страница.', **m}
            ip = self.my_ip(proxy=port)
            return {'state': 'ok', 'exit': ip, **m}
        finally:
            p.kill()
            p.wait(5)


def scrub(text, it):
    for s in it.get('secrets') or []:
        text = text.replace(s, '***')
    return re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}', '***', text)[:300]


class DemoProbe(Probe):
    """No network in the demo: plausible numbers, so the screen can be seen and tested."""
    def resolve(self, host):
        return ['104.16.1.1'] if 'cdn' in host else ['203.0.113.10'] if not is_ip(host) else [host]

    def ping(self, ip):
        return {'loss': 0.0, 'avg': 42.5}

    def tcp(self, ip, port, tries=3):
        return {'ok': True, 'ms': 44.0, 'tries': tries, 'okCount': tries, 'error': None}

    def tls(self, ip, port, sni):
        return {'sni': sni, 'reached': True, 'trusted': True, 'version': 'TLSv1.3', 'alpn': 'h2', 'issuer': 'Demo CA', 'ms': 96.0}

    def peek(self, ip, port, host, use_tls):
        return {'status': 200, 'server': 'nginx', 'title': 'Демо-сайт', 'location': None, 'body': 'x' * 500, 'error': None}

    def fetch(self, url, **kw):
        return {'ok': True, 'status': 200, 'bytes': kw.get('limit', 0), 'sent': 0, 'stalled': False, 'seconds': 1, 'error': None, 'ms': 50.0, 'body': b''}

    def ip_info(self, ip):
        return {'country': 'RU', 'countryName': 'Россия', 'org': 'Демо-провайдер', 'isp': 'Демо-провайдер', 'asn': 64500} if ip == '198.51.100.7' else \
               {'country': 'US', 'countryName': 'США', 'org': 'Cloudflare, Inc.', 'isp': 'Cloudflare', 'asn': 13335} if ip.startswith('104.') else \
               {'country': 'DE', 'countryName': 'Германия', 'org': 'Демо-хостинг', 'isp': 'Демо-хостинг', 'asn': 64501}

    def my_ip(self, proxy=None):
        return '203.0.113.10' if proxy else '198.51.100.7'

    def exits(self):
        ip = self.my_ip()
        return [('демо', ip)] if ip else []

    def cf_seen(self, connect_ip=None):
        return self.my_ip()

    def server_peers(self, d, ip, port):
        return None, None

    def measure(self, proxy=None):
        return {'okCount': 5, 'tries': 5, 'firstMs': 310.0 if proxy else 60.0, 'ms': 95.0 if proxy else 18.0, 'down': 84.2 if proxy else 480.0, 'downError': None,
                'up': 61.0 if proxy else 240.0, 'stalled': False, 'stallAt': None, 'freeze': False}

    def tunnel(self, it, on_up=None, host=None):
        if not it.get('outbound'):
            return {'state': 'skip', 'note': f'{it["proto"]}: туннель этого типа Rack Live не поднимает.'}
        return {'state': 'ok', 'exit': self.my_ip(proxy=1), **self.measure(proxy=1)}


class VpnCheck:
    def __init__(self, app, probe=None):
        self.app, self.store = app, app.store
        self.probe = probe or (DemoProbe() if os.environ.get('RL_DEMO', '').lower() in ('1', 'true', 'yes') else Probe())
        self.report = self.store._load('vpncheck.json', {})
        self.jobs, self.lock = {}, threading.Lock()

    def expand(self, text):
        """Pasted text → parsed items and readable errors. A subscription address is opened and its links are read the same way."""
        text = (text or '').strip()
        if not text:
            raise ValueError('Вставьте ссылку на подключение')
        if '[interface]' in text.lower():
            return [parse_wg(text)], []
        items, errors = [], []
        for n, line in enumerate(x.strip() for x in text.splitlines()):
            if not line:
                continue
            if re.match(r'^https?://', line, re.I):
                try:
                    links = self._subscription(line)
                except ValueError as e:
                    errors.append(f'Подписка: {e}')
                    continue
            else:
                links = [line]
            for link in links:
                if len(items) >= MAX_LINKS:
                    errors.append(f'Проверены первые {MAX_LINKS} подключений.')
                    return items, errors
                try:
                    items.append(parse_amnezia(link) if link.lower().startswith('vpn://') else parse_link(link))
                except ValueError as e:
                    errors.append(f'Строка {n + 1}: {e}')
        if not items and not errors:
            raise ValueError('Вставьте ссылку на подключение')
        return items, errors

    def _subscription(self, url):
        r = self.probe.fetch(url, limit=1 << 20, keep=1 << 20, time_limit=15, stall=10)
        if not r['ok']:
            raise ValueError(f'не открылась ({r["error"] or "код " + str(r["status"])})')
        body = r['body'].decode('utf-8', 'replace').strip()
        if '://' not in body:
            try:
                body = _b64(re.sub(r'\s', '', body))
            except ValueError:
                raise ValueError('формат не распознан, нужен список ссылок')
        links = [x.strip() for x in body.splitlines() if '://' in x]
        if not links:
            raise ValueError('в ней нет ссылок, которые можно проверить')
        return links

    def path(self):
        """Does Rack Live itself go through a VPN? Otherwise the whole check says nothing about the provider, and that must be said loudly."""
        exits = self.probe.exits()
        if not exits:
            return {'state': 'unknown', 'note': 'Не удалось узнать внешний адрес: возможно, нет интернета.'}
        devices = self.store.cfg.get('devices') or []
        self.vps = {}
        for d in devices:
            if d.get('driver') in ('ssh', 'demo_server') and d.get('location') == 'remote':
                h = doctor_hostname(d)
                for a in (self.probe.resolve(h) if h else []):
                    self.vps[a] = d
        wan = {p['ip'] for d in devices if d.get('location') != 'remote' for p in ((self.app.states.get(d['id']) or {}).get('ports') or []) if p.get('kind') == 'wan' and p.get('ip')}
        kinds, infos = {}, {}
        for ip in dict.fromkeys(ip for _, ip in exits):
            info = infos[ip] = self.probe.ip_info(ip)
            if ip in self.vps:
                kinds[ip] = 'vpn'
            elif ip in wan or info.get('country') == 'RU':
                kinds[ip] = 'direct'
            elif info.get('country'):
                kinds[ip] = 'vpn'
            else:
                kinds[ip] = 'unknown'
        direct = next((ip for _, ip in exits if kinds[ip] == 'direct'), None)
        vpn = next((ip for _, ip in exits if kinds[ip] == 'vpn'), None)
        self.direct_ip = direct
        main = direct or vpn or exits[0][1]
        info = infos[main]
        out = {'ip': main, 'country': info.get('country'), 'countryName': info.get('countryName'), 'isp': info.get('isp') or info.get('org')}
        if vpn:
            who = self.vps[vpn].get('name') if vpn in self.vps else infos[vpn].get('countryName') or infos[vpn].get('org') or vpn
            out['via'] = who
        routed = [name for name, ip in exits if kinds[ip] == 'vpn']
        if direct and vpn:
            return {**out, 'state': 'mixed', 'routed': routed, 'note': f'Обычно напрямую, но часть адресов идёт через VPN «{who}»: {", ".join(routed)}. Похоже на правила маршрутизации на роутере.'}
        if vpn:
            return {**out, 'state': 'vpn', 'note': f'Весь проверенный трафик выходит через «{who}».'}
        if direct:
            return {**out, 'state': 'direct', 'note': f'Все {len(exits)} проверочных сервиса видят адрес провайдера.' if len(exits) > 1 else 'Проверочный сервис видит адрес провайдера.'}
        return {**out, 'state': 'unknown', 'note': 'Не удалось определить, чей это адрес.'}

    def route_to(self, ip, port):
        """The router may send this one address through a VPN, and from here that cannot be seen. If the server is ours, ask it who connected."""
        d = (getattr(self, 'vps', None) or {}).get(ip)
        if not d or not d.get('driver') == 'ssh':
            return {'state': 'unknown', 'note': 'Сервер не из ваших устройств: откуда он видит подключение, узнать нельзя.'}
        peers, mine = self.probe.server_peers(d, ip, port)
        if peers is None:
            return {'state': 'unknown', 'note': 'Не удалось спросить сервер, откуда он видит подключение.'}
        home = getattr(self, 'direct_ip', None)
        known = {a: x.get('name') for a, x in self.vps.items() if a != ip}
        exact = [h for h, p in peers if p == mine]
        for pool, sure in ((exact, True), ([h for h, _ in peers], False)):
            if home and home in pool:
                return {'state': 'direct', 'note': 'Сервер видит подключение с адреса вашего провайдера.'}
            via = next((known[h] for h in pool if h in known), None)
            if via:
                return {'state': 'vpn', 'via': via, 'note': f'Сервер видит подключение с «{via}»: до него трафик идёт через VPN.'}
        return {'state': 'unknown', 'note': 'Среди подключений к серверу нет ни адреса провайдера, ни ваших серверов.'}

    def seen_by_cloudflare(self, connect_ip=None):
        """Direct, or through a VPN? For a measurement of a CDN that answer decides whether it says anything about the provider."""
        ip = self.probe.cf_seen(connect_ip)
        if not ip:
            return None
        return 'direct' if ip == getattr(self, 'direct_ip', None) else 'vpn' if ip in (getattr(self, 'vps', None) or {}) else 'other'

    def names_of(self, it, cdn_name=None):
        """Reality's SNI is someone else's site used as a disguise: a CDN behind it says nothing about this server."""
        names = [('адрес из ссылки', it['host'])]
        own = [] if it['security'] == 'reality' else [('SNI', it['q'].get('sni')), ('Host', it['q'].get('host'))]
        for role, n in own + [('CDN', cdn_name)]:
            if n and not is_ip(n) and all(n != x[1] for x in names):
                names.append((role, n))
        return names

    def check_one(self, it, path_state, progress, cdn_name=None):
        p = self.probe
        label = it['name'] or it['host']
        rep = {k: it[k] for k in ('proto', 'kind', 'host', 'port', 'net', 'security', 'name')}
        rep.update(sni=it['q'].get('sni') or '', flow=it['q'].get('flow') or '', fp=it['q'].get('fp') or '', advice=advice(it), awg=it.get('awg'))
        progress(f'{label}: путь до сервера…')
        ips = p.resolve(it['host'])
        if not ips:
            rep['block'] = {'state': 'bad', 'text': 'Имя сервера не находится через DNS: ошибка в адресе или подмена DNS.'}
            rep['tunnel'] = {'state': 'skip', 'note': 'Без адреса туннель не поднять.'}
            rep['verdict'] = dict(zip(('state', 'text'), verdict(rep, path_state)))
            rep['score'] = score(rep, path_state)
            return rep
        ip = ips[0]
        info = p.ip_info(ip)
        rep.update(ip=ip, country=info.get('country'), countryName=info.get('countryName'), org=info.get('org'), asn=info.get('asn'), cdn=cdn_of(ip, info.get('org')))
        rep['ping'] = p.ping(ip)
        udp = it['net'] == 'udp'
        if not udp:
            rep['route'] = self.route_to(ip, it['port'])
        if udp:
            rep['tcp'] = None
            rep['block'] = {'state': 'unknown', 'text': 'Протокол идёт по UDP: на чужой запрос такой сервер молчит, поэтому снаружи путь до него проверить нельзя.'}
        else:
            rep['tcp'] = p.tcp(ip, it['port'])
            sni = it['q'].get('sni') or (it['host'] if not is_ip(it['host']) else None)
            tls = neutral = clean_sni = clean_plain = None
            if it['security'] in ('tls', 'reality'):
                progress(f'{label}: проверяю TLS и имя сайта…')
                tls = p.tls(ip, it['port'], sni or 'www.example.com')
                if rep['tcp']['ok'] and not tls['reached']:
                    neutral = p.tls(ip, it['port'], 'www.example.com')
                    clean_plain = p.tls('1.1.1.1', 443, 'one.one.one.one')
                    clean_sni = p.tls('1.1.1.1', 443, sni) if sni else None
            if not rep['tcp']['ok']:
                clean_plain = p.tls('1.1.1.1', 443, 'one.one.one.one')
            state, text = classify(rep['tcp'], tls, neutral, clean_sni, clean_plain)
            rep['tls'], rep['block'] = tls, {'state': state, 'text': text}
            if it['proto'] not in ('Shadowsocks', 'SOCKS') and rep['tcp']['ok']:
                progress(f'{label}: смотрю, есть ли сайт-заглушка…')
                use_tls = it['security'] in ('tls', 'reality')
                rep['decoy'] = classify_decoy(p.peek(ip, it['port'], sni or it['host'], use_tls), it['security'] == 'reality', (tls or {}).get('trusted'))
                rep['neighbours'] = []
                for port, nb_tls in ((443, True), (80, False)):
                    if port != it['port']:
                        got = p.peek(ip, port, it['host'] if not is_ip(it['host']) else ip, nb_tls)
                        if got['status']:
                            rep['neighbours'].append({'port': port, **classify_decoy(got)})
        progress(f'{label}: поднимаю туннель, задержка и скорость…')
        t = p.tunnel(it)
        rep['tunnel'] = t
        if t.get('exit'):
            ex = p.ip_info(t['exit']) if t['exit'] != ip else info
            t.update(exitCountry=ex.get('country'), exitCountryName=ex.get('countryName'), exitOrg=ex.get('org'), exitSame=t['exit'] in ips)
        rep['cdns'] = self.check_cdn(it, rep, progress, cdn_name, label)
        rep['verdict'] = dict(zip(('state', 'text'), verdict(rep, path_state)))
        rep['score'] = score(rep, path_state)
        return rep

    def check_cdn(self, it, rep, progress, cdn_name, label):
        """Every name in the link, and the one given by hand: is a CDN behind it, does it answer from here, and does the same key work through it?"""
        p, out = self.probe, []
        for role, name in self.names_of(it, cdn_name):
            ips = p.resolve(name) if name != it['host'] else [rep['ip']]
            if not ips:
                out.append({'name': name, 'role': role, 'cdn': None, 'error': 'имя не находится через DNS'}) if role == 'CDN' else None
                continue
            info = p.ip_info(ips[0]) if name != it['host'] else {'org': rep.get('org')}
            cdn = cdn_of(ips[0], info.get('org'))
            if not cdn and role != 'CDN':
                continue
            row = {'name': name, 'role': role, 'cdn': cdn, 'ip': ips[0]}
            progress(f'{label}: проверяю CDN {cdn or name}…')
            row['tls'] = p.tls(ips[0], it['port'] if it['port'] in (443, 8443, 2053, 2083, 2087, 2096) else 443, name)
            if cdn == 'Cloudflare':
                r = p.fetch(DOWN_URL % (256 << 10), connect_ip=ips[0], limit=256 << 10, time_limit=10, stall=6)
                row['volume'] = {'bytes': r['bytes'], 'ok': r['status'] == 200 and r['bytes'] >= 256 << 10, 'stalled': r['stalled'], 'error': r['error'], 'way': self.seen_by_cloudflare(ips[0])}
            if name != it['host'] and it.get('outbound') and it['net'] != 'tcp' and it['security'] == 'tls':
                row['tunnel'] = p.tunnel(it, host=name)
            out.append(row)
        return out

    def run(self, items, errors, progress, cdn_name=None):
        progress('Проверяю, идёт ли Rack Live через VPN…')
        path = self.path()
        progress('Замеряю обычный интернет для сравнения…')
        base = self.probe.measure()
        r = self.probe.fetch(DOWN_URL % (256 << 10), limit=256 << 10, time_limit=10, stall=6)
        base['cloudflare'] = {'ok': r['status'] == 200 and r['bytes'] >= 256 << 10, 'bytes': r['bytes'], 'stalled': r['stalled'], 'status': r['status'], 'error': r['error'], 'way': self.seen_by_cloudflare()}
        reps = []
        for it in items:
            try:
                reps.append(self.check_one(it, path['state'], progress, cdn_name))
            except Exception as e:      # one broken link must not lose the others; the text of the error may quote the config
                reps.append({k: it[k] for k in ('proto', 'kind', 'host', 'port', 'net', 'security', 'name')} | {'advice': advice(it), 'verdict': {'state': 'unknown', 'text': 'Проверка этого подключения прервалась: ' + scrub(str(e), it)}})
        return {'t': time.time(), 'path': path, 'base': base, 'items': reps, 'errors': errors}

    def start(self, text, cdn_name=None):
        cdn_name = (cdn_name or '').strip().lower()
        if cdn_name and not re.fullmatch(r'[a-z0-9]([a-z0-9.\-]*[a-z0-9])?', cdn_name):
            raise ValueError('Домен CDN указан неправильно: нужно только имя, например cdn.example.com')
        with self.lock:
            cur = next((j for j in self.jobs.values() if not j['done']), None)
        if cur:
            return cur
        items, errors = self.expand(text)
        if not items:
            raise ValueError(' '.join(errors))
        with self.lock:
            job = {'id': secrets.token_hex(6), 't': time.time(), 'stage': 'Запуск…', 'done': False, 'count': len(items)}
            self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v['t'] < 3600}
            self.jobs[job['id']] = job

        def work():
            try:
                self.report = self.run(items, errors, lambda x: job.update(stage=x), cdn_name or None)
                self.store._dump('vpncheck.json', self.report)
            except Exception as e:
                job['error'] = f'Проверка прервалась: {type(e).__name__}'
            finally:
                job['done'] = True
        threading.Thread(target=work, daemon=True).start()
        return job

    def public(self):
        busy = next((j['id'] for j in self.jobs.values() if not j['done']), None)
        return {'report': self.report or None, 'job': busy, 'hasXray': bool(shutil.which('xray') or os.path.exists('/usr/local/bin/xray') or isinstance(self.probe, DemoProbe))}
