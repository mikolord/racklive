"""Plugin «Сборщик площадки» (driver «Сервер / VPS по SSH»): puts a whole Rack Live in «collector» mode (rackd/collector.py) on a server or a mini PC over SSH.

What happens (everything as root, in stages, so the UI can show progress):
  1. this Rack Live creates a site (rackd/sites.py) and a one-time admin password for the new installation;
  2. the server downloads THIS Rack Live's own code (GET /api/site/pack, authorised by the site key — no GitHub needed, the same version on both sides);
  3. it is unpacked into /opt/racklive, a config with the site key is written to /var/lib/racklive, a systemd service «racklive» is started;
  4. the new installation scans ITS network and reports here; it is also an ordinary Rack Live (its own panel on the chosen port).
Nothing is installed from the Internet except the system packages python3 / openssh-client / ping / curl (apt)."""
import base64, hashlib, io, json, os, re, shlex, tarfile, threading

from . import auth

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = ('rackd', 'web')
APP_DIR, DATA_DIR, UNIT = '/opt/racklive', '/var/lib/racklive', 'racklive'
DEFAULT_PORT = 9998
LEVELS = ('view', 'actions', 'terminal')

CARD = {'id': 'collector', 'drivers': ['ssh'], 'title': 'Сборщик площадки (Rack Live)', 'icon': 'server', 'kind': 'collector',
        'description': 'Ставит на сервер или мини-ПК полный Rack Live в режиме сборщика: он сам сканирует свою сеть, настраивает камеры и присылает всё на эту панель. Открывать порты не нужно.',
        'author': 'Rack Live', 'home': 'https://github.com/mikolord/racklive'}

STATUS = r'''. /etc/os-release 2>/dev/null; echo "@@os $PRETTY_NAME"; echo "@@id $ID"; echo "@@uid $(id -u)"; echo "@@arch $(uname -m)"
echo "@@mem $(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)"
echo "@@free $(df -Pm /opt 2>/dev/null | awk 'NR==2{print $4}')"
[ -d /run/systemd/system ] && echo "@@systemd"
command -v python3 >/dev/null 2>&1 && echo "@@python $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
command -v apt-get >/dev/null 2>&1 && echo "@@apt"
[ -f /opt/racklive/rackd/server.py ] && echo "@@ver $(sed -n "s/^VERSION = '\(.*\)'.*/\1/p" /opt/racklive/rackd/server.py | head -1)"
echo "@@active $(systemctl is-active racklive 2>/dev/null)"
echo "@@ip $(hostname -I 2>/dev/null | awk '{print $1}')"
echo "@@host $(hostname)"
echo @@end
'''


def parse_status(out):
    s = {}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k.startswith('@@') and k != '@@end':
            s[k[2:]] = v.strip()
    return s


# ───────── the code of this installation, packed for the new one ─────────
_lock, _cache = threading.Lock(), {'sig': None, 'data': b''}


def _files():
    out = []
    for part in PARTS:
        for base, dirs, names in os.walk(os.path.join(ROOT, part)):
            dirs[:] = sorted(d for d in dirs if d not in ('__pycache__', 'node_modules', '.git'))
            for n in sorted(names):
                if n.endswith(('.pyc', '.map')) or n in ('package-lock.json', 'package.json'):
                    continue
                out.append(os.path.join(base, n))
    return out


def pack():
    """tar.gz with rackd/ and web/ of the running code (cached until a file changes)"""
    files = _files()
    sig = hashlib.sha1('|'.join(f'{p}:{os.path.getmtime(p)}:{os.path.getsize(p)}' for p in files).encode()).hexdigest()
    with _lock:
        if _cache['sig'] != sig:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode='w:gz', compresslevel=6) as tf:
                for p in files:
                    ti = tf.gettarinfo(p, arcname=os.path.relpath(p, ROOT).replace(os.sep, '/'))
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = 'root'
                    ti.mode = 0o755 if p.endswith('.py') else 0o644
                    with open(p, 'rb') as f:
                        tf.addfile(ti, f)
            _cache.update(sig=sig, data=buf.getvalue())
        return _cache['data']


# ───────── the config of the new installation ─────────
def clean_url(u):
    u = (u or '').strip().rstrip('/')
    if not re.match(r'^https?://[^\s/]+(/[^\s]*)?$', u):
        raise ValueError('адрес главной панели вида https://racklive.example.com или http://192.168.1.3:9998')
    return u


def make_config(name, url, token, password, level, insecure):
    """what is written to /var/lib/racklive/config.json of the new installation: the admin password (hash only), the title and the site key"""
    if level not in LEVELS:
        raise ValueError('уровень управления: view, actions или terminal')
    return {'settings': {'title': name}, 'auth': auth.hash_password(password),
            'collector': {'url': url, 'token': token, 'enabled': True, 'level': level, 'insecure': bool(insecure)}}


def install_script(url, token, cfg, port, insecure=False):
    """the whole installation as one shell script (secrets stay in shell variables and the environment, not in argument lists)"""
    cfg_b64 = base64.b64encode(json.dumps(cfg, ensure_ascii=False).encode()).decode()
    port = int(port)
    return f'''export DEBIAN_FRONTEND=noninteractive
RL_URL={shlex.quote(url)}; RL_TOKEN={shlex.quote(token)}; RL_CFG={shlex.quote(cfg_b64)}; RL_PORT={port}; RL_INSECURE={1 if insecure else 0}
fail() {{ echo "@@fail $1"; exit 0; }}
[ "$(id -u)" = 0 ] || fail "нужен вход под root"
[ -d /run/systemd/system ] || fail "нужна система с systemd (Debian, Ubuntu, Raspberry Pi OS)"
if command -v apt-get >/dev/null 2>&1; then
  echo "— пакеты: python3, openssh-client, ping, curl"
  apt-get update -qq </dev/null >/dev/null 2>&1 || true
  apt-get install -y -qq python3 openssh-client iputils-ping curl ca-certificates tzdata </dev/null >/dev/null 2>&1 || fail "не удалось поставить пакеты через apt: проверьте интернет на сервере"
else
  for c in python3 ssh ping curl; do command -v $c >/dev/null 2>&1 || fail "не хватает программы $c — поставьте её вручную"; done
fi
PY=$(command -v python3)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
echo "— скачиваю Rack Live с главной панели"
RL_URL="$RL_URL" RL_TOKEN="$RL_TOKEN" RL_INSECURE="$RL_INSECURE" $PY - "$T/pack.tgz" <<'PYEOF' 2>"$T/err" || fail "не удалось скачать с главной панели $RL_URL: $(tail -1 "$T/err")"
import os, ssl, sys, urllib.error, urllib.request
req = urllib.request.Request(os.environ['RL_URL'].rstrip('/') + '/api/site/pack', headers={{'Authorization': 'Bearer ' + os.environ['RL_TOKEN'], 'User-Agent': 'racklive-installer'}})
ctx = ssl._create_unverified_context() if os.environ.get('RL_INSECURE') == '1' else None
try:
    data = urllib.request.urlopen(req, timeout=180, context=ctx).read()
except urllib.error.HTTPError as e:
    sys.exit('главная панель ответила ошибкой %s' % e.code)
except Exception as e:
    sys.exit('нет связи (%s)' % type(e).__name__)
if len(data) < 100000:
    sys.exit('получен слишком маленький файл')
open(sys.argv[1], 'wb').write(data)
PYEOF
mkdir -p "$T/new" && tar -xzf "$T/pack.tgz" -C "$T/new" </dev/null 2>/dev/null || fail "архив повреждён"
[ -f "$T/new/rackd/server.py" ] && [ -f "$T/new/web/index.html" ] || fail "в архиве нет rackd или web"
echo "— проверяю, что код запускается"
VER=$(cd "$T/new" && PYTHONDONTWRITEBYTECODE=1 RL_DATA="$T/data" $PY -c 'import rackd.server as s; print(s.VERSION)' 2>"$T/err") || fail "код не запускается: $(tail -1 "$T/err")"
echo "— устанавливаю версию $VER в {APP_DIR}"
systemctl stop {UNIT} </dev/null >/dev/null 2>&1 || true
rm -rf {APP_DIR}.prev; [ -d {APP_DIR} ] && mv {APP_DIR} {APP_DIR}.prev
mkdir -p {APP_DIR} {DATA_DIR}; chmod 700 {DATA_DIR}
mv "$T/new/rackd" "$T/new/web" {APP_DIR}/
echo "— записываю настройки и ключ площадки"
RL_CFG="$RL_CFG" $PY - <<'PYEOF' || fail "не удалось записать настройки"
import base64, json, os
p = '{DATA_DIR}/config.json'
new = json.loads(base64.b64decode(os.environ['RL_CFG']))
try:
    cur = json.load(open(p, encoding='utf-8'))
except Exception:
    cur = None
if cur is None:
    print('@@created 1')
    cur = new
else:                                  # a repeat install keeps the administrator and everything else: only the site key is renewed
    cur['collector'] = new['collector']
json.dump(cur, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
os.chmod(p, 0o600)
PYEOF
cat > /etc/systemd/system/{UNIT}.service <<EOF
[Unit]
Description=Rack Live (collector)
After=network-online.target
Wants=network-online.target
[Service]
Environment=RL_DATA={DATA_DIR} RL_WEB={APP_DIR}/web RL_PORT=$RL_PORT PYTHONUNBUFFERED=1
WorkingDirectory={APP_DIR}
ExecStart=$PY -m rackd
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
command -v ufw >/dev/null 2>&1 && ufw status </dev/null 2>/dev/null | grep -q '^Status: active' && ufw allow "$RL_PORT/tcp" </dev/null >/dev/null 2>&1
systemctl daemon-reload </dev/null; systemctl enable {UNIT} </dev/null >/dev/null 2>&1; systemctl restart {UNIT} </dev/null
echo "— жду запуска"
i=0; while [ $i -lt 45 ]; do $PY -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$RL_PORT/api/state', timeout=2)" >/dev/null 2>&1 && break; i=$((i+1)); sleep 1; done
[ $i -lt 45 ] && echo "@@up 1" || fail "Rack Live не запустился: $(journalctl -u {UNIT} -n 4 --no-pager </dev/null 2>/dev/null | tail -2 | tr '\\n' ' ')"
echo "@@ver $VER"
echo "@@ip $(hostname -I 2>/dev/null | awk '{{print $1}}')"
echo @@ok
'''


def remove_script(purge=False):
    return f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужен вход под root"; exit 0; }}
systemctl disable --now {UNIT} </dev/null >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{UNIT}.service; systemctl daemon-reload </dev/null
rm -rf {APP_DIR} {APP_DIR}.prev{f' {DATA_DIR}' if purge else ''}
echo "— служба и программа удалены{'' if purge else '; данные остались в ' + DATA_DIR}"
echo @@ok
'''
