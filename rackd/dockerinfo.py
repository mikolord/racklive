"""Docker containers in detail (Synology and servers over SSH): what runs, since when, on which address and port, which image, how much it eats.

One POSIX script is run on the host (through sudo where Docker needs root):
  docker ps -a / docker inspect  → image, state, health, start time, restarts, restart policy, networks and their addresses, published ports, mounts, labels;
  docker stats --no-stream       → CPU, memory, network and disk traffic, processes;
  ss -ltnp                       → what each container really listens on (the only way to see ports of containers in «host» network mode).
Environment variables of containers are NOT read (they hold passwords)."""
import json, re, time

SCRIPT = r'''
export PATH=$PATH:/usr/local/bin:/usr/syno/bin:/usr/syno/sbin
D="docker"
$D version >/dev/null 2>&1 || D="sudo -n docker"
echo @@ver; $D version --format '{{.Server.Version}}' 2>&1 | head -2
echo @@ps; IDS=$($D ps -aq --no-trunc 2>/dev/null)
echo @@stats; $D stats --no-stream --no-trunc --format '{{json .}}' 2>/dev/null
echo @@inspect; [ -n "$IDS" ] && $D inspect $IDS 2>/dev/null
if command -v ss >/dev/null 2>&1; then LISTEN=$(ss -ltnpH 2>/dev/null || ss -ltnp 2>/dev/null | tail -n +2); else LISTEN=$(netstat -ltnp 2>/dev/null | tail -n +3); fi
echo @@listen; echo "$LISTEN"
echo @@cg; for p in $( (echo "$LISTEN" | grep -o 'pid=[0-9]*' | cut -d= -f2; echo "$LISTEN" | grep -o ' [0-9]*/[^ ]*' | cut -d/ -f1 | tr -d ' ') | sort -u); do echo "$p $(grep -o '[0-9a-f]\{64\}' /proc/$p/cgroup 2>/dev/null | head -1)"; done
echo @@end
'''

# what well-known images are, in one line (the container's own image label wins; the owner can also write a note)
KNOWN = [
    ('postgres', 'База данных PostgreSQL'), ('mariadb', 'База данных MariaDB (MySQL)'), ('mysql', 'База данных MySQL'), ('mongo', 'База данных MongoDB'),
    ('redis', 'Хранилище в памяти Redis (кеш и очереди)'), ('valkey', 'Хранилище в памяти Valkey (кеш и очереди)'), ('memcached', 'Кеш Memcached'),
    ('nginx', 'Веб-сервер / обратный прокси nginx'), ('traefik', 'Обратный прокси Traefik'), ('caddy', 'Веб-сервер Caddy'), ('haproxy', 'Балансировщик HAProxy'),
    ('homeassistant', 'Home Assistant — умный дом'), ('zigbee2mqtt', 'Мост Zigbee ↔ MQTT'), ('mosquitto', 'MQTT-брокер Mosquitto'), ('eclipse-mosquitto', 'MQTT-брокер Mosquitto'),
    ('frigate', 'Frigate — видеонаблюдение с распознаванием'), ('immich-server', 'Immich — фото и видео (сервер)'), ('immich-machine-learning', 'Immich — распознавание лиц и объектов'),
    ('immich', 'Immich — фото и видео'), ('portainer', 'Portainer — управление Docker'), ('watchtower', 'Автообновление контейнеров'), ('pihole', 'Pi-hole — блокировка рекламы (DNS)'),
    ('adguard', 'AdGuard Home — блокировка рекламы (DNS)'), ('jellyfin', 'Jellyfin — медиасервер'), ('plex', 'Plex — медиасервер'), ('nextcloud', 'Nextcloud — своё облако'),
    ('grafana', 'Grafana — графики и дашборды'), ('prometheus', 'Prometheus — сбор метрик'), ('influxdb', 'InfluxDB — база временных рядов'), ('vaultwarden', 'Vaultwarden — менеджер паролей'),
    ('uptime-kuma', 'Uptime Kuma — проверка доступности сайтов'), ('gitea', 'Gitea — свой Git-сервер'), ('minio', 'MinIO — S3-хранилище'), ('syncthing', 'Syncthing — синхронизация файлов'),
    ('qbittorrent', 'qBittorrent — торрент-клиент'), ('transmission', 'Transmission — торрент-клиент'), ('sonarr', 'Sonarr — сериалы'), ('radarr', 'Radarr — фильмы'),
    ('netbootxyz', 'netboot.xyz — загрузка и установка ОС по сети (PXE)'), ('netboot', 'Загрузка и установка ОС по сети (PXE)'), ('dnsmasq', 'dnsmasq — DHCP/DNS/PXE'),
    ('docker-proxy', 'Прокси для доступа к Docker'), ('amnezia', 'AmneziaWG / VPN'), ('wireguard', 'WireGuard — VPN'), ('openvpn', 'OpenVPN — VPN'), ('xray', 'Xray — прокси'),
    ('rack-live', 'Rack Live — эта панель'), ('racklive', 'Rack Live — эта панель'), ('node', 'Приложение на Node.js'), ('python', 'Приложение на Python'), ('php', 'Приложение на PHP'),
    ('alpine', 'Минимальный Linux Alpine'), ('ubuntu', 'Linux Ubuntu'), ('debian', 'Linux Debian'), ('busybox', 'Минимальный набор утилит BusyBox'),
]


def _num(s):
    m = re.search(r'[\d.]+', str(s or ''))
    return float(m.group(0)) if m else None


_UNITS = {'b': 1, 'kb': 1e3, 'mb': 1e6, 'gb': 1e9, 'tb': 1e12, 'kib': 1024, 'mib': 1024 ** 2, 'gib': 1024 ** 3, 'tib': 1024 ** 4}


def _bytes(s):
    m = re.match(r'\s*([\d.]+)\s*([a-zA-Z]*)', str(s or ''))
    return int(float(m.group(1)) * _UNITS.get(m.group(2).lower() or 'b', 1)) if m else None


def _ts(s):
    """docker timestamps: 2026-10-11T12:21:29.123456789Z → epoch (0001-01-01… = never)"""
    m = re.match(r'(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)', str(s or ''))
    if not m or m.group(1) == '0001':
        return 0
    import calendar
    return calendar.timegm(tuple(int(x) for x in m.groups()) + (0, 0, 0))


GENERIC = ('alpine', 'ubuntu', 'debian', 'busybox', 'python', 'node', 'php')


def describe(image, labels, note='', name=''):
    """→ (text, where from): your note, then what the image / container name says, then the image's own label (often inherited from a base image, so it comes later), then a generic base"""
    if note:
        return note, 'ваша заметка'
    base = re.sub(r'^.*/', '', str(image or '')).split(':')[0].lower()
    for key, text in KNOWN:
        if key not in GENERIC and (key in base or key in str(name or '').lower()):
            return text, 'по названию'
    for k in ('org.opencontainers.image.description', 'org.label-schema.description', 'org.opencontainers.image.title', 'description'):
        v = (labels or {}).get(k)
        if v:
            return str(v)[:200], 'из описания образа'
    for key, text in KNOWN:
        if key in GENERIC and key in base:
            return text, 'по названию образа'
    return '', ''


def parse(out, host_ip='', notes=None):
    """script output → {'docker': {...}, 'containers': [...]}"""
    sec, cur = {}, None
    for l in out.splitlines():
        if l.startswith('@@'):
            cur = l[2:].strip(); sec[cur] = []
        elif cur:
            sec[cur].append(l)
    ver = ' '.join(sec.get('ver', [])).strip()
    if not ver or 'ermission' in ver or 'not found' in ver or 'Cannot connect' in ver:
        return {'docker': None, 'error': ('Docker недоступен: ' + ver[:160]) if ver else 'Docker не найден на этом устройстве', 'containers': []}
    stats = {}
    for l in sec.get('stats', []):
        try:
            j = json.loads(l)
        except ValueError:
            continue
        mem = str(j.get('MemUsage') or '').split('/')
        net = str(j.get('NetIO') or '').split('/')
        blk = str(j.get('BlockIO') or '').split('/')
        stats[j.get('ID') or j.get('Container') or j.get('Name')] = {
            'name': j.get('Name'), 'cpu': _num(j.get('CPUPerc')), 'mem': _bytes(mem[0]) if mem else None, 'memLimit': _bytes(mem[1]) if len(mem) > 1 else None, 'memPct': _num(j.get('MemPerc')),
            'netRx': _bytes(net[0]) if net else None, 'netTx': _bytes(net[1]) if len(net) > 1 else None, 'blkR': _bytes(blk[0]) if blk else None, 'blkW': _bytes(blk[1]) if len(blk) > 1 else None,
            'pids': int(_num(j.get('PIDs')) or 0)}
    try:
        info = json.loads('\n'.join(sec.get('inspect', [])) or '[]')
    except ValueError:
        info = []
    # which listening ports belong to which container (works for containers in «host» network mode too)
    cg = {}
    for l in sec.get('cg', []):
        p = l.split()
        if len(p) >= 2:
            cg[p[0]] = p[1]
    listens = {}
    for l in sec.get('listen', []):
        m = re.search(r'(\S+):(\d+)\s+\S+\s*(?:users:\(\("([^"]*)",pid=(\d+))?', l)          # ss
        n = re.search(r'(\S+):(\d+)\s+\S+\s+LISTEN\s+(\d+)/(\S+)', l)                           # netstat (Synology has no ss)
        if n:
            m = type('M', (), {'group': lambda self, i, v=(None, n.group(1), n.group(2), n.group(4), n.group(3)): v[i]})()
        if m:
            cid = cg.get(m.group(4) or '')
            if cid:
                listens.setdefault(cid, []).append({'addr': m.group(1).strip('[]'), 'port': int(m.group(2)), 'proc': m.group(3) or ''})
    now = time.time()
    out_list = []
    for c in info:
        cid = c.get('Id') or ''
        cfg, st, hc, ns = c.get('Config') or {}, c.get('State') or {}, c.get('HostConfig') or {}, c.get('NetworkSettings') or {}
        name = (c.get('Name') or '').lstrip('/')
        labels = cfg.get('Labels') or {}
        s = stats.get(cid) or stats.get(cid[:12]) or next((v for v in stats.values() if v.get('name') == name), {}) or {}
        state = st.get('Status') or ('running' if st.get('Running') else 'exited')
        started = _ts(st.get('StartedAt'))
        ports = []
        for key, binds in (ns.get('Ports') or {}).items():
            port, _, proto = key.partition('/')
            if binds:
                for b in binds:
                    hip = b.get('HostIp') or ''
                    ports.append({'host': host_ip if hip in ('', '0.0.0.0', '::') else hip, 'hostPort': int(b.get('HostPort') or 0), 'port': int(port), 'proto': proto or 'tcp', 'published': True})
            else:
                ports.append({'host': '', 'hostPort': 0, 'port': int(port), 'proto': proto or 'tcp', 'published': False})
        seen = set()
        ports = [p for p in ports if (p['hostPort'], p['port'], p['proto']) not in seen and not seen.add((p['hostPort'], p['port'], p['proto']))]
        netmode = hc.get('NetworkMode') or ''
        nets = [{'name': n, 'ip': (v or {}).get('IPAddress') or '', 'gateway': (v or {}).get('Gateway') or ''} for n, v in (ns.get('Networks') or {}).items() if netmode != 'host']
        text, src = describe(cfg.get('Image'), labels, (notes or {}).get(name, ''), name)
        image = cfg.get('Image') or ''
        out_list.append({
            'id': cid[:12], 'name': name, 'image': image, 'state': state, 'running': bool(st.get('Running')), 'health': (st.get('Health') or {}).get('Status') or '',
            'startedAt': started if st.get('Running') else 0, 'uptime': int(now - started) if st.get('Running') and started else 0,
            'finishedAt': _ts(st.get('FinishedAt')) if not st.get('Running') else 0, 'exitCode': st.get('ExitCode') if not st.get('Running') else None,
            'oom': bool(st.get('OOMKilled')), 'restarts': c.get('RestartCount') or 0, 'restartPolicy': (hc.get('RestartPolicy') or {}).get('Name') or 'no',
            'networkMode': netmode, 'hostNetwork': netmode == 'host', 'networks': nets, 'ports': ports,
            'listening': sorted(listens.get(cid, []), key=lambda x: x['port']),
            'mounts': [{'src': m.get('Source') or m.get('Name') or '', 'dst': m.get('Destination') or '', 'rw': bool(m.get('RW', True)), 'type': m.get('Type') or ''} for m in (c.get('Mounts') or [])][:10],
            'project': labels.get('com.docker.compose.project') or '', 'service': labels.get('com.docker.compose.service') or '',
            'description': text, 'descriptionFrom': src, 'created': _ts(c.get('Created')), 'memLimitSet': hc.get('Memory') or 0,
            'cpu': s.get('cpu'), 'mem': s.get('mem'), 'memLimit': s.get('memLimit'), 'memPct': s.get('memPct'), 'netRx': s.get('netRx'), 'netTx': s.get('netTx'),
            'blkR': s.get('blkR'), 'blkW': s.get('blkW'), 'pids': s.get('pids'),
        })
    out_list.sort(key=lambda x: (not x['running'], -(x['cpu'] or 0), x['name']))
    run = [c for c in out_list if c['running']]
    return {'docker': {'version': ver.split()[0], 'total': len(out_list), 'running': len(run), 'cpu': round(sum(c['cpu'] or 0 for c in run), 1), 'mem': sum(c['mem'] or 0 for c in run)},
            'containers': out_list}


def demo(host_ip, notes=None):
    """invented containers for the demo office"""
    now = int(time.time())
    def c(name, image, cpu, mem, ports=(), up=3 * 86400, project='', state='running', net='bridge', ip='172.18.0.2', host=False, listening=(), mounts=(), restarts=0, policy='unless-stopped', labels=None, rx=2e6, tx=1e6):
        text, src = describe(image, labels or {}, (notes or {}).get(name, ''), name)
        run = state == 'running'
        return {'id': ('%012x' % (abs(hash(name)) % 16 ** 12)), 'name': name, 'image': image, 'state': state, 'running': run, 'health': 'healthy' if run and cpu > 1 else '', 'startedAt': now - up if run else 0,
                'uptime': up if run else 0, 'finishedAt': 0 if run else now - 7200, 'exitCode': None if run else 137, 'oom': False, 'restarts': restarts, 'restartPolicy': policy, 'networkMode': 'host' if host else net,
                'hostNetwork': host, 'networks': [] if host else [{'name': net, 'ip': ip, 'gateway': ip.rsplit('.', 1)[0] + '.1'}],
                'ports': [{'host': host_ip, 'hostPort': a, 'port': b, 'proto': 'tcp', 'published': True} for a, b in ports], 'listening': [{'addr': '0.0.0.0', 'port': p, 'proc': 'app'} for p in listening],
                'mounts': [{'src': s, 'dst': t, 'rw': True, 'type': 'bind'} for s, t in mounts], 'project': project, 'service': name.split('_')[-1] if project else '', 'description': text, 'descriptionFrom': src,
                'created': now - up - 3600, 'memLimitSet': 0, 'cpu': cpu if run else None, 'mem': int(mem * 1048576) if run else None, 'memLimit': 8 * 1024 ** 3 if run else None,
                'memPct': round(mem / 81.92, 2) if run else None, 'netRx': int(rx) if run else None, 'netTx': int(tx) if run else None, 'blkR': 5_200_000 if run else None, 'blkW': 31_000_000 if run else None, 'pids': 12 if run else None}
    items = [
        c('racklive', 'racklive:2', 3.4, 118, host=True, listening=[9998], up=2 * 3600, mounts=[('/volume1/docker/racklive/data', '/data')], policy='always'),
        c('immich_server', 'ghcr.io/immich-app/immich-server:release', 6.1, 940, ports=[(2283, 2283)], project='immich', ip='172.19.0.4', mounts=[('/volume1/photo', '/usr/src/app/upload')], up=9 * 86400),
        c('immich_postgres', 'tensorchord/pgvecto-rs:pg14', 1.2, 310, project='immich', ip='172.19.0.2', up=9 * 86400),
        c('immich_redis', 'redis:6.2-alpine', 0.3, 12, project='immich', ip='172.19.0.3', up=9 * 86400),
        c('frigate', 'ghcr.io/blakeblackshear/frigate:stable', 22.5, 1480, ports=[(5000, 5000), (8554, 8554)], ip='172.17.0.2', mounts=[('/volume1/surveillance', '/media/frigate')], up=4 * 86400, restarts=1),
        c('portainer', 'portainer/portainer-ce:latest', 0.1, 38, ports=[(9000, 9000)], ip='172.17.0.3', up=21 * 86400),
        c('amnezia_panel', 'amnezia/panel:latest', 0.0, 24, ports=[(8080, 80)], ip='172.17.0.4', up=21 * 86400),
        c('old-test', 'nginx:1.25', 0, 0, state='exited', up=0),
    ]
    run = [x for x in items if x['running']]
    return {'docker': {'version': '24.0.2', 'total': len(items), 'running': len(run), 'cpu': round(sum(x['cpu'] or 0 for x in run), 1), 'mem': sum(x['mem'] or 0 for x in run)}, 'containers': items}
