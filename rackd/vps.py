"""VPS plugins (driver «Сервер / VPS по SSH»): 3x-ui and Remnawave panels.

Optional domain → nginx with a stub site + Let's Encrypt (certbot, auto-renew) in front of the panel;
optional inbounds → VLESS TCP+TLS (8443) and VLESS XHTTP+TLS (2053) on the domain's certificate + a test user.
Everything runs as root over SSH, in stages (each stage = one SSH call), so the UI can show progress.
"""
import json, re, secrets, shlex, string

CATALOG = [
    {'id': '3xui', 'drivers': ['ssh'], 'title': '3x-ui', 'icon': 'shield', 'kind': 'panel',
     'description': 'Веб-панель Xray: пользователи, инбаунды, трафик. С доменом — за nginx с сайтом-заглушкой и сертификатом.',
     'author': 'MHSanaei', 'home': 'https://github.com/MHSanaei/3x-ui', 'needsDomain': False},
    {'id': 'remnawave', 'drivers': ['ssh'], 'title': 'Remnawave', 'icon': 'shield', 'kind': 'panel',
     'description': 'Панель Remnawave (подписки, сквады, ноды) и нода на этом же сервере. Нужен домен.',
     'author': 'remnawave', 'home': 'https://docs.rw', 'needsDomain': True},
]
TCP_PORT, XHTTP_PORT, NODE_PORT = 8443, 2053, 2222

STATUS = r'''. /etc/os-release 2>/dev/null; echo "@@os $PRETTY_NAME"; echo "@@id $ID"; echo "@@uid $(id -u)"
echo "@@mem $(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)"
echo "@@ip $( (curl -s4 --max-time 6 https://api.ipify.org || wget -qO- -T 6 https://api.ipify.org) 2>/dev/null)"
[ -x /usr/local/x-ui/x-ui ] && echo "@@xui $(/usr/local/x-ui/x-ui -v 2>/dev/null | head -1)"
[ -f /opt/remnawave/docker-compose.yml ] && echo "@@rw $(docker inspect -f '{{.State.Status}}' remnawave 2>/dev/null || echo stopped)"
for p in 80 443 %d %d %d; do l=$(ss -ltnpH 2>/dev/null | awk -v p=":$p" '$4 ~ p"$"' | head -1); [ -n "$l" ] && echo "@@port $p $(echo "$l" | grep -o '(("[^"]*' | head -1 | tr -d '(\"')"; done
command -v docker >/dev/null 2>&1 && echo "@@docker"
echo @@end
''' % (TCP_PORT, XHTTP_PORT, NODE_PORT)


def parse_status(out):
    s = {'ports': {}, 'docker': False}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k == '@@port':
            p, _, who = v.partition(' ')
            s['ports'][int(p)] = who.strip() or '?'
        elif k == '@@docker':
            s['docker'] = True
        elif k.startswith('@@') and k != '@@end':
            s[k[2:]] = v.strip()
    return s


def rnd(n, alphabet=string.ascii_letters + string.digits):
    return ''.join(secrets.choice(alphabet) for _ in range(n))


def strong_password(n=32):
    """letters + digits with every class present (Remnawave checks complexity)."""
    while True:
        p = rnd(n)
        if any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p):
            return p


DOMAIN_RE = re.compile(r'^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$')


def clean_domain(d):
    d = re.sub(r'^\w+://', '', (d or '').strip().lower()).split('/')[0].split(':')[0].rstrip('.')
    if d and not d.isascii():
        d = d.encode('idna').decode()
    return d if DOMAIN_RE.match(d) else ''


def dns_script(domain):
    return f'getent ahostsv4 {shlex.quote(domain)} 2>/dev/null | awk \'{{print "@@a "$1}}\' | sort -u; echo @@end'


PREP = r'''export DEBIAN_FRONTEND=noninteractive
. /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo "@@fail поддерживаются Ubuntu и Debian (у вас $PRETTY_NAME)"; exit 0;; esac
[ "$(id -u)" = 0 ] || { echo "@@fail нужен вход под root"; exit 0; }
'''

STUB_HTML = ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>Скоро открытие</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;font:16px -apple-system,'
             'Segoe UI,Roboto,sans-serif;background:#0b0b0f;color:#e5e5ea}div{text-align:center}h1{font-weight:650;margin:0 0 8px}'
             'p{color:#8e8e93;margin:0}</style><div><h1>Сайт в разработке</h1><p>Скоро здесь будет что-то интересное.</p></div></html>')


def stage_cert(domain):
    """nginx + stub site + certbot (webroot) + renewal hook. Leaves an HTTP-only site; the HTTPS one is written per panel."""
    d = shlex.quote(domain)
    return PREP + f'''apt-get update -q >/dev/null 2>&1
apt-get install -y -q nginx certbot curl openssl python3 >/dev/null 2>&1 || {{ echo "@@fail не удалось установить nginx и certbot (apt)"; exit 0; }}
mkdir -p /var/www/rl-stub
cat > /var/www/rl-stub/index.html <<'RLHTML'
{STUB_HTML}
RLHTML
cat > /etc/nginx/sites-available/rl-site.conf <<RLNGX
server {{
    listen 80; listen [::]:80;
    server_name {domain};
    root /var/www/rl-stub;
    location /.well-known/acme-challenge/ {{ root /var/www/rl-stub; }}
    location / {{ try_files /index.html =404; }}
}}
RLNGX
ln -sf /etc/nginx/sites-available/rl-site.conf /etc/nginx/sites-enabled/rl-site.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t 2>&1 | tail -2 && systemctl enable --now nginx >/dev/null 2>&1 && systemctl reload nginx
command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active" && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
if [ ! -f /etc/letsencrypt/live/{domain}/fullchain.pem ]; then
  certbot certonly --webroot -w /var/www/rl-stub -d {d} --non-interactive --agree-tos --register-unsafely-without-email 2>&1 | tail -4 || true
  [ -f /etc/letsencrypt/live/{domain}/fullchain.pem ] || certbot certonly --webroot -w /var/www/rl-stub -d {d} --non-interactive --agree-tos -m admin@{domain} 2>&1 | tail -4
fi
[ -f /etc/letsencrypt/live/{domain}/fullchain.pem ] || {{ echo "@@fail Let's Encrypt не выдал сертификат — проверьте, что порт 80 открыт и домен смотрит на этот сервер"; exit 0; }}
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/racklive.sh <<'RLHOOK'
#!/bin/sh
systemctl reload nginx
systemctl restart x-ui 2>/dev/null
docker restart remnanode >/dev/null 2>&1
exit 0
RLHOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/racklive.sh
systemctl enable --now certbot.timer >/dev/null 2>&1
echo "сертификат: $(openssl x509 -enddate -noout -in /etc/letsencrypt/live/{domain}/fullchain.pem)"
echo "автопродление: $(systemctl is-enabled certbot.timer 2>/dev/null || echo cron)"
echo @@ok
'''


def https_site(domain, body):
    """Final nginx site: 80 → https (ACME path kept), 443 with the certificate and the given locations."""
    return f'''cat > /etc/nginx/sites-available/rl-site.conf <<'RLNGX'
server {{
    listen 80; listen [::]:80;
    server_name {domain};
    location /.well-known/acme-challenge/ {{ root /var/www/rl-stub; }}
    location / {{ return 301 https://$host$request_uri; }}
}}
server {{
    listen 443 ssl; listen [::]:443 ssl;
    http2 on;
    server_name {domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:rlssl:10m;
    root /var/www/rl-stub;
{body}
}}
RLNGX
if ! nginx -t >/dev/null 2>&1; then          # nginx < 1.25 has no «http2 on;»
  sed -i 's/^    http2 on;$//; s/listen 443 ssl;/listen 443 ssl http2;/' /etc/nginx/sites-available/rl-site.conf
fi
nginx -t 2>&1 | tail -1
nginx -t >/dev/null 2>&1 || {{ echo "@@fail nginx не принял настройки сайта"; exit 0; }}
systemctl reload nginx
'''


PROXY_HEADERS = '''        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";'''


def open_ports(*ports):
    return 'command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active" && { ' + \
        ' '.join(f'ufw allow {p}/tcp >/dev/null;' for p in ports) + ' }\n'


# ───────── 3x-ui ─────────
def xui_install(domain, user, password, port, path):
    env = {'XUI_NONINTERACTIVE': '1', 'XUI_USERNAME': user, 'XUI_PASSWORD': password, 'XUI_PANEL_PORT': str(port),
           'XUI_WEB_BASE_PATH': path, 'XUI_SSL_MODE': 'none' if domain else 'ip'}
    exports = ' '.join(f'{k}={shlex.quote(v)}' for k, v in env.items())
    s = PREP + f'''apt-get update -q >/dev/null 2>&1; apt-get install -y -q curl ca-certificates python3 >/dev/null 2>&1
curl -fsSL https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh -o /tmp/rl-xui.sh || {{ echo "@@fail не удалось скачать установщик 3x-ui"; exit 0; }}
env {exports} bash /tmp/rl-xui.sh </dev/null 2>&1 | sed 's/\\x1b\\[[0-9;]*m//g' | grep -v '^$' | tail -25
rm -f /tmp/rl-xui.sh
[ -x /usr/local/x-ui/x-ui ] || {{ echo "@@fail 3x-ui не установился"; exit 0; }}
'''
    if domain:      # behind nginx: the panel listens on localhost only
        s += '/usr/local/x-ui/x-ui setting -listenIP 127.0.0.1 >/dev/null 2>&1; systemctl restart x-ui\n'
        s += https_site(domain, f'''    location / {{ try_files /index.html =404; }}
    location /{path}/ {{
        proxy_pass http://127.0.0.1:{port};
{PROXY_HEADERS}
    }}''')
    else:
        s += open_ports(80, port)                   # 80: Let's Encrypt IP certificate validation
    s += 'sleep 3; systemctl is-active x-ui >/dev/null && echo @@ok || echo "@@fail служба x-ui не запустилась"\n'
    s += '[ -f /etc/x-ui/install-result.env ] && grep -E "^XUI_ACCESS_URL=" /etc/x-ui/install-result.env | sed "s/^/@@url /"\n'
    return s


# python steps print «@@fail …» on any error (stderr is not always captured by the SSH transport)
PY_GUARD = "import sys\nsys.excepthook = lambda t, v, tb: print('@@fail внутренняя ошибка: %s: %s' % (t.__name__, v), flush=True)\n"


def xui_inbounds(domain, user, password, port, path, xpath):
    """Runs python3 on the server: login to the panel on localhost, add two VLESS inbounds with a test client each."""
    cfg = repr({'base': f'http://127.0.0.1:{port}/{path}', 'user': user, 'password': password, 'domain': domain,
                      'tcp': TCP_PORT, 'xh': XHTTP_PORT, 'xpath': xpath})
    return open_ports(TCP_PORT, XHTTP_PORT) + "python3 - <<'RLPY'\n" + f'CFG = {cfg}\n' + PY_GUARD + r'''
import http.cookiejar, json, urllib.parse, urllib.request, uuid, secrets
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(path, data=None, form=False):
    body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(CFG['base'] + path, data=body, headers={'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json'})
    return json.loads(op.open(r, timeout=30).read() or b'{}')
if not req('/login', {'username': CFG['user'], 'password': CFG['password']}, form=True).get('success'):
    print('@@fail не удалось войти в панель 3x-ui'); raise SystemExit
d = CFG['domain']
cert = [{'certificateFile': f'/etc/letsencrypt/live/{d}/fullchain.pem', 'keyFile': f'/etc/letsencrypt/live/{d}/privkey.pem',
         'ocspStapling': 3600, 'oneTimeLoading': False, 'usage': 'encipherment', 'buildChain': False}]
tls = {'serverName': d, 'minVersion': '1.2', 'maxVersion': '1.3', 'cipherSuites': '', 'rejectUnknownSni': False, 'certificates': cert,
       'alpn': ['h2', 'http/1.1'], 'settings': {'allowInsecure': False, 'fingerprint': 'chrome'}}
sniff = json.dumps({'enabled': True, 'destOverride': ['http', 'tls', 'quic'], 'metadataOnly': False, 'routeOnly': False})
sub = secrets.token_hex(8)
def client(email, flow):
    return {'id': str(uuid.uuid4()), 'flow': flow, 'email': email, 'limitIp': 0, 'totalGB': 0, 'expiryTime': 0, 'enable': True,
            'tgId': '', 'subId': sub, 'comment': 'Rack Live test', 'reset': 0}
links = []
for remark, port, net, extra, flow in (('VLESS TCP TLS', CFG['tcp'], 'tcp', {'tcpSettings': {'acceptProxyProtocol': False, 'header': {'type': 'none'}}}, 'xtls-rprx-vision'),
                                       ('VLESS XHTTP TLS', CFG['xh'], 'xhttp', {'xhttpSettings': {'path': CFG['xpath'], 'host': '', 'headers': {}, 'mode': 'auto',
                                        'xPaddingBytes': '100-1000', 'scMaxBufferedPosts': 30, 'scMaxEachPostBytes': '1000000', 'noSSEHeader': False}}, '')):
    c = client('test-' + net + '-' + secrets.token_hex(2), flow)
    stream = dict({'network': net, 'security': 'tls', 'externalProxy': [], 'tlsSettings': tls}, **extra)
    body = {'up': 0, 'down': 0, 'total': 0, 'remark': remark, 'enable': True, 'expiryTime': 0, 'listen': '', 'port': port, 'protocol': 'vless',
            'settings': json.dumps({'clients': [c], 'decryption': 'none', 'fallbacks': []}), 'streamSettings': json.dumps(stream), 'sniffing': sniff}
    r = req('/panel/api/inbounds/add', body)
    if not r.get('success'):
        print('@@fail инбаунд «%s»: %s' % (remark, r.get('msg'))); raise SystemExit
    q = {'type': net, 'security': 'tls', 'sni': d, 'fp': 'chrome', 'alpn': 'h2,http/1.1'}
    if flow: q['flow'] = flow
    if net == 'xhttp': q.update(path=CFG['xpath'], mode='auto')
    link = 'vless://%s@%s:%d?%s#%s' % (c['id'], d, port, urllib.parse.urlencode(q, safe=',/'), urllib.parse.quote('RL-' + net.upper()))
    print('@@link ' + json.dumps({'name': remark, 'url': link}))
print('@@ok')
RLPY
'''


def xui_remove():
    return PREP + '''systemctl stop x-ui 2>/dev/null; systemctl disable x-ui 2>/dev/null
rm -rf /usr/local/x-ui /etc/x-ui /etc/systemd/system/x-ui.service /usr/bin/x-ui /var/log/x-ui; systemctl daemon-reload
rm -f /etc/nginx/sites-enabled/rl-site.conf /etc/nginx/sites-available/rl-site.conf; systemctl reload nginx 2>/dev/null
echo @@ok
'''


# ───────── Remnawave ─────────
def rw_install(domain, key):
    """Docker + panel (official compose/.env) + nginx in front (cookie-guarded: stub without the secret link) + node."""
    d = domain
    return PREP + f'''command -v docker >/dev/null 2>&1 || {{ curl -fsSL https://get.docker.com | sh >/dev/null 2>&1 || {{ echo "@@fail не удалось установить Docker"; exit 0; }}; }}
mkdir -p /opt/remnawave && cd /opt/remnawave
if [ ! -f .env ]; then
  curl -fsSL -o docker-compose.yml https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/docker-compose-prod.yml || {{ echo "@@fail не удалось скачать docker-compose.yml Remnawave"; exit 0; }}
  curl -fsSL -o .env https://raw.githubusercontent.com/remnawave/backend/refs/heads/main/.env.sample || {{ echo "@@fail не удалось скачать .env Remnawave"; exit 0; }}
  sed -i "s/^APP_SECRET=.*/APP_SECRET=$(openssl rand -hex 64)/" .env
  sed -i "s/^METRICS_PASS=.*/METRICS_PASS=$(openssl rand -hex 64)/" .env
  sed -i "s/^WEBHOOK_SECRET_HEADER=.*/WEBHOOK_SECRET_HEADER=$(openssl rand -hex 64)/" .env
  pw=$(openssl rand -hex 24) && sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$pw/" .env && sed -i "s|^\\(DATABASE_URL=\\"postgresql://postgres:\\)[^\\@]*\\(@.*\\)|\\1$pw\\2|" .env
  sed -i "s|^PANEL_DOMAIN=.*|PANEL_DOMAIN={d}|; s|^FRONT_END_DOMAIN=.*|FRONT_END_DOMAIN={d}|; s|^SUB_PUBLIC_DOMAIN=.*|SUB_PUBLIC_DOMAIN={d}/api/sub|" .env
fi
docker compose pull -q 2>&1 | tail -3; docker compose up -d 2>&1 | tail -5
''' + https_site(d, f'''    location /api/sub/ {{
        proxy_pass http://127.0.0.1:3000;
{PROXY_HEADERS}
    }}
    location / {{
        if ($arg_rlkey = "{key}") {{ add_header Set-Cookie "rl_key={key}; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax" always; return 302 /; }}
        if ($http_cookie !~ "rl_key={key}") {{ return 404; }}
        proxy_pass http://127.0.0.1:3000;
{PROXY_HEADERS}
    }}
    error_page 404 = @stub;
    location @stub {{ try_files /index.html =404; }}''') + '''for i in $(seq 1 60); do curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3001/health 2>/dev/null | grep -q 200 && break; sleep 5; done
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3001/health | grep -q 200 && echo @@ok || { docker compose logs --tail 15 remnawave 2>&1; echo "@@fail панель Remnawave не запустилась за 5 минут"; }
'''


def rw_setup(domain, admin, password, inbounds, xpath):
    """python3 on the server: first admin → keygen → (profile with our inbounds) → node container → node → hosts → squad → test user."""
    cfg = repr({'domain': domain, 'admin': admin, 'password': password, 'inbounds': inbounds, 'xpath': xpath,
                      'tcp': TCP_PORT, 'xh': XHTTP_PORT, 'nodePort': NODE_PORT})
    return (open_ports(TCP_PORT, XHTTP_PORT) if inbounds else '') + "python3 - <<'RLPY'\n" + f'CFG = {cfg}\n' + PY_GUARD + r'''
import json, subprocess, time, urllib.request, urllib.error, datetime
d = CFG['domain']
H = {'Content-Type': 'application/json', 'Host': d, 'X-Forwarded-For': '127.0.0.1', 'X-Forwarded-Proto': 'https'}
def api(method, path, data=None):
    r = urllib.request.Request('http://127.0.0.1:3000/api' + path, data=json.dumps(data).encode() if data is not None else None, headers=H, method=method)
    try:
        return json.loads(urllib.request.urlopen(r, timeout=30).read() or b'{}').get('response')
    except urllib.error.HTTPError as e:
        print('@@fail Remnawave API %s %s: %s' % (method, path, e.read()[:300].decode('utf-8', 'replace')), flush=True)
        raise SystemExit(0)
tok = api('POST', '/auth/register', {'username': CFG['admin'], 'password': CFG['password']})['accessToken']
H['Authorization'] = 'Bearer ' + tok
print('администратор создан')
pub = api('GET', '/keygen')['pubKey']
cert = [{'certificateFile': '/etc/letsencrypt/live/%s/fullchain.pem' % d, 'keyFile': '/etc/letsencrypt/live/%s/privkey.pem' % d}]
tls = {'serverName': d, 'alpn': ['h2', 'http/1.1'], 'certificates': cert}
if CFG['inbounds']:
    xray = {'log': {'loglevel': 'warning'},
            'inbounds': [{'tag': 'VLESS_TCP_TLS', 'listen': '0.0.0.0', 'port': CFG['tcp'], 'protocol': 'vless', 'settings': {'clients': [], 'decryption': 'none'},
                          'sniffing': {'enabled': True, 'destOverride': ['http', 'tls', 'quic']},
                          'streamSettings': {'network': 'tcp', 'security': 'tls', 'tlsSettings': tls}},
                         {'tag': 'VLESS_XHTTP_TLS', 'listen': '0.0.0.0', 'port': CFG['xh'], 'protocol': 'vless', 'settings': {'clients': [], 'decryption': 'none'},
                          'sniffing': {'enabled': True, 'destOverride': ['http', 'tls', 'quic']},
                          'streamSettings': {'network': 'xhttp', 'security': 'tls', 'tlsSettings': tls, 'xhttpSettings': {'path': CFG['xpath'], 'mode': 'auto'}}}],
            'outbounds': [{'protocol': 'freedom', 'tag': 'DIRECT'}, {'protocol': 'blackhole', 'tag': 'BLOCK'}],
            'routing': {'rules': [{'ip': ['geoip:private'], 'outboundTag': 'BLOCK'}]}}
    prof = api('POST', '/config-profiles', {'name': 'RackLive', 'config': xray})
else:
    profs = api('GET', '/config-profiles')
    prof = (profs.get('configProfiles') if isinstance(profs, dict) else profs)[0]
ins = api('GET', '/config-profiles/%s/inbounds' % prof['uuid'])
ins = ins.get('inbounds') if isinstance(ins, dict) else ins
print('профиль: %s, инбаундов: %d' % (prof.get('name'), len(ins)))
compose = """services:
  remnanode:
    container_name: remnanode
    hostname: remnanode
    image: remnawave/node:latest
    network_mode: host
    restart: always
    environment:
      - NODE_PORT=%d
      - SECRET_KEY=%s
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro
""" % (CFG['nodePort'], pub)
subprocess.run('mkdir -p /opt/remnanode', shell=True)
open('/opt/remnanode/docker-compose.yml', 'w').write(compose)
subprocess.run('cd /opt/remnanode && docker compose up -d 2>&1 | tail -3', shell=True)
gw = subprocess.run("docker network inspect remnawave-network -f '{{(index .IPAM.Config 0).Gateway}}'", shell=True, capture_output=True, text=True).stdout.strip() or '172.17.0.1'
node = api('POST', '/nodes', {'name': 'Этот сервер', 'address': gw, 'port': CFG['nodePort'], 'countryCode': 'XX',
                             'configProfile': {'activeConfigProfileUuid': prof['uuid'], 'activeInbounds': [i['uuid'] for i in ins]}})
print('нода подключена (%s:%d)' % (gw, CFG['nodePort']))
for i in ins:
    xh = i.get('tag') == 'VLESS_XHTTP_TLS'
    api('POST', '/hosts', {'inbound': {'configProfileUuid': prof['uuid'], 'configProfileInboundUuid': i['uuid']}, 'remark': i.get('tag'),
                           'address': d, 'port': i.get('port') or (CFG['xh'] if xh else CFG['tcp']), 'sni': d, **({'path': CFG['xpath']} if xh else {})})
squads = api('GET', '/internal-squads')
squads = squads.get('internalSquads') if isinstance(squads, dict) else squads
if squads:
    sq = squads[0]['uuid']
    api('PATCH', '/internal-squads', {'uuid': sq, 'inbounds': [i['uuid'] for i in ins]})
else:
    sq = api('POST', '/internal-squads', {'name': 'Default', 'inbounds': [i['uuid'] for i in ins]})['uuid']
if CFG['inbounds']:
    exp = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    u = api('POST', '/users', {'username': 'test_racklive', 'expireAt': exp, 'activeInternalSquads': [sq]})
    print('@@link ' + json.dumps({'name': 'Подписка тестового пользователя (30 дней)', 'url': u.get('subscriptionUrl')}))
print('@@ok')
RLPY
'''


def rw_remove():
    return PREP + '''cd /opt/remnanode 2>/dev/null && docker compose down 2>&1 | tail -2
cd /opt/remnawave 2>/dev/null && docker compose down -v 2>&1 | tail -3
rm -rf /opt/remnawave /opt/remnanode
rm -f /etc/nginx/sites-enabled/rl-site.conf /etc/nginx/sites-available/rl-site.conf; systemctl reload nginx 2>/dev/null
echo @@ok
'''
