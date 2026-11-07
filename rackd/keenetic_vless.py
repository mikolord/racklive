"""VLESS on a Keenetic from a pasted link: XKeen (Xray, proxy for the devices of one policy) or AWG Manager (sing-box, a connection in the router's list).
The link itself is never stored and never goes to a log: Rack Live shows only the address, the transport and the security."""
import json, re, secrets, urllib.parse

UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
NETS = {'tcp': 'raw', 'raw': 'raw', 'ws': 'ws', 'grpc': 'grpc', 'xhttp': 'xhttp', 'splithttp': 'xhttp', 'httpupgrade': 'httpupgrade'}
PRIVATE = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '169.254.0.0/16', 'fc00::/7', 'fe80::/10']
TEST_PORT = 18899
XKEEN_URL = 'https://github.com/jameszeroX/XKeen/releases/latest/download/xkeen.tar.gz'
AWG_API = 'http://127.0.0.1:2222/api'


def parse_vless(link):
    """→ the parts of a vless:// link; ValueError with a readable reason."""
    link = (link or '').strip()
    if not link.lower().startswith('vless://'):
        raise ValueError('нужна ссылка, начинающаяся с vless://')
    if re.search(r'\s', link):
        raise ValueError('вставьте одну ссылку, без пробелов и переводов строки')
    try:
        u = urllib.parse.urlsplit(link)
        host, port = u.hostname, u.port
    except ValueError:
        raise ValueError('не получилось разобрать ссылку: проверьте адрес и порт')
    uid = urllib.parse.unquote(u.username or '')
    if not UUID_RE.match(uid):
        raise ValueError('в ссылке нет правильного идентификатора пользователя (UUID)')
    if not host or not port:
        raise ValueError('в ссылке нет адреса или порта сервера')
    q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
    net, sec = q.get('type', 'tcp').lower(), q.get('security', 'none').lower()
    if net not in NETS:
        raise ValueError(f'транспорт «{net}» не поддерживается: нужен tcp, xhttp, ws, grpc или httpupgrade')
    if sec not in ('none', 'tls', 'reality'):
        raise ValueError(f'защита «{sec}» не поддерживается: нужна tls, reality или без неё')
    if sec == 'reality' and not q.get('pbk'):
        raise ValueError('для Reality в ссылке нужен публичный ключ (pbk)')
    return {'id': uid, 'host': host, 'port': port, 'net': NETS[net], 'security': sec, 'q': q, 'name': urllib.parse.unquote(u.fragment or '')[:60], 'link': link}


def summary(v):
    """What may be shown and logged: no identifier, no keys."""
    return {'host': v['host'], 'port': v['port'], 'net': 'tcp' if v['net'] == 'raw' else v['net'], 'security': v['security'], 'name': v['name']}


def xray_outbound(v, tag='proxy'):
    q, net, sec = v['q'], v['net'], v['security']
    stream = {'network': net, 'security': sec}
    alpn = [a for a in q.get('alpn', '').split(',') if a]
    if sec == 'tls':
        t = {'serverName': q.get('sni') or q.get('host') or v['host'], 'fingerprint': q.get('fp') or 'chrome'}
        if alpn:
            t['alpn'] = alpn
        if q.get('pcs'):
            t['pinnedPeerCertSha256'] = q['pcs']
        elif q.get('allowInsecure') == '1' or q.get('insecure') == '1':
            t['allowInsecure'] = True
        stream['tlsSettings'] = t
    elif sec == 'reality':
        stream['realitySettings'] = {'serverName': q.get('sni') or v['host'], 'fingerprint': q.get('fp') or 'chrome', 'publicKey': q['pbk'],
                                     'shortId': q.get('sid', ''), 'spiderX': q.get('spx', '')}
    path = q.get('path') or '/'
    if net == 'xhttp':
        x = {'path': path, 'mode': q.get('mode') or 'auto'}
        if q.get('host'):
            x['host'] = q['host']
        if q.get('extra'):
            try:
                x['extra'] = json.loads(q['extra'])
            except ValueError:
                raise ValueError('поле extra в ссылке — не JSON')
        stream['xhttpSettings'] = x
    elif net in ('ws', 'httpupgrade'):
        s = {'path': path}
        if q.get('host'):
            s['host'] = q['host']
        stream['wsSettings' if net == 'ws' else 'httpupgradeSettings'] = s
    elif net == 'grpc':
        stream['grpcSettings'] = {'serviceName': q.get('serviceName') or q.get('path') or '', 'multiMode': q.get('mode') == 'multi'}
    elif q.get('headerType') == 'http':
        stream['rawSettings'] = {'header': {'type': 'http', 'request': {'path': [path], 'headers': {'Host': [q['host']] if q.get('host') else []}}}}
    user = {'id': v['id'], 'encryption': q.get('encryption') or 'none'}
    if q.get('flow'):
        user['flow'] = q['flow']
    return {'tag': tag, 'protocol': 'vless', 'settings': {'vnext': [{'address': v['host'], 'port': v['port'], 'users': [user]}]}, 'streamSettings': stream}


def xkeen_configs(v):
    """04_outbounds / 05_routing: everything XKeen catches goes to the server, except local addresses."""
    outbounds = {'outbounds': [xray_outbound(v), {'tag': 'direct', 'protocol': 'freedom'}, {'tag': 'block', 'protocol': 'blackhole'}]}
    routing = {'routing': {'domainStrategy': 'AsIs', 'rules': [{'ip': PRIVATE, 'outboundTag': 'direct'},
                                                               {'inboundTag': ['redirect', 'tproxy', 'force-proxy-redirect', 'force-proxy-tproxy'], 'outboundTag': 'proxy'}]}}
    return outbounds, routing


def test_config(v):
    return {'log': {'loglevel': 'warning'}, 'inbounds': [{'listen': '127.0.0.1', 'port': TEST_PORT, 'protocol': 'http'}], 'outbounds': [xray_outbound(v)]}


def _heredoc(path, obj):
    tag = 'RLEOF' + secrets.token_hex(6)
    return f"cat > {path} <<'{tag}'\n{json.dumps(obj, ensure_ascii=False, indent=1)}\n{tag}\n"


STATUS = r'''[ -x /opt/sbin/xkeen ] && echo "@@xkeen $(/opt/sbin/xkeen -v 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | grep -Eo '[0-9]+(\.[0-9]+)+' | head -n 1)"
[ -x /opt/sbin/xray ] && echo "@@xray $(/opt/sbin/xray version 2>/dev/null | head -n 1 | cut -d' ' -f2)"
[ -x /opt/sbin/mihomo ] && echo @@mihomo
pidof xray >/dev/null 2>&1 && echo @@running
pidof mihomo >/dev/null 2>&1 && echo @@mihomo_on
grep -q '"outboundTag": "proxy"' /opt/etc/xray/configs/05_routing.json 2>/dev/null && echo @@mine
grep -qsE '"protocol": *"(vless|vmess|trojan|shadowsocks|socks|hysteria)"' /opt/etc/xray/configs/*.json && echo @@conf
opkg list-installed 2>/dev/null | grep -q '^awg-manager ' && echo @@awgm
echo "@@free $(df -k /opt 2>/dev/null | awk 'NR==2{print $4}')"
echo @@end
'''


def _xkeen_run(args, wait=150):
    """XKeen may start the core with its own stdout, so a pipe here («| tail») stays open as long as the proxy runs and SSH never ends:
    the proxy is up while Rack Live reports a timeout. Output goes to a file instead, and the wait has a limit."""
    return f'''XKEEN_FOREGROUND=1 /opt/sbin/xkeen {args} </dev/null >/tmp/rl-xk.log 2>&1 &
P=$!; i=0; while kill -0 $P 2>/dev/null && [ $i -lt {wait} ]; do sleep 1; i=$((i+1)); done
sed 's/\\x1b\\[[0-9;]*[A-Za-z]//g' /tmp/rl-xk.log | grep -v '^ *$' | tail -n 25
kill -0 $P 2>/dev/null || rm -f /tmp/rl-xk.log
'''


def parse_status(out):
    s = {}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k.startswith('@@') and k != '@@end':
            s[k[2:]] = v.strip() or True
    return s


# Not the author's install.sh: it ends with an interactive «xkeen -i». The same steps, then the documented «-i auto». Without policy XKeen would catch ALL clients,
# so the driver makes the policy first; this script does not start the proxy (nor does «-i auto» on a stopped proxy).
XKEEN_INSTALL = f'''opkg update >/dev/null 2>&1
opkg install curl tar >/dev/null 2>&1
cd /tmp || exit 0
rm -f rl-xkeen.tar.gz
curl -fsSL --connect-timeout 15 -m 180 -o rl-xkeen.tar.gz {XKEEN_URL} || \\
  curl -fsSL --connect-timeout 15 -m 180 -o rl-xkeen.tar.gz https://gh-proxy.com/{XKEEN_URL}
[ -s rl-xkeen.tar.gz ] || {{ echo "@@fail не удалось скачать XKeen с GitHub"; exit 0; }}
S=/opt/sbin/.rl-xkeen.$$; rm -rf "$S"; mkdir -p "$S"
tar -xzf rl-xkeen.tar.gz -C "$S"; rm -f rl-xkeen.tar.gz
[ -f "$S/xkeen" ] && [ -d "$S/_xkeen" ] || {{ rm -rf "$S"; echo "@@fail архив XKeen повреждён"; exit 0; }}
chmod +x "$S/xkeen"; rm -rf /opt/sbin/.xkeen; mv "$S/_xkeen" /opt/sbin/.xkeen; mv "$S/xkeen" /opt/sbin/xkeen; rm -rf "$S"
{_xkeen_run('-i auto cores=xray geo=off geoipset=off cron=off autostart=on', 800)}[ -x /opt/sbin/xray ] || {{ echo "@@fail XKeen установился, а ядро Xray — нет (см. журнал)"; exit 0; }}
echo @@ok
'''


def key_test(v):
    """A separate Xray on localhost, nothing else is touched: a dead key must not break what works."""
    return _heredoc('/tmp/rl-vless-test.json', test_config(v)) + f'''/opt/sbin/xray run -c /tmp/rl-vless-test.json >/tmp/rl-vless-test.log 2>&1 &
P=$!; sleep 3
C=$(curl -s -m 20 -o /dev/null -w '%{{http_code}}' -x http://127.0.0.1:{TEST_PORT} https://www.gstatic.com/generate_204)
kill $P 2>/dev/null
rm -f /tmp/rl-vless-test.json
if [ "$C" = 204 ]; then echo @@ok; else
  grep -aE 'failed|error|Failed' /tmp/rl-vless-test.log | tail -n 2 | sed -E 's/[0-9a-fA-F]{{8}}-[0-9a-fA-F-]{{27}}/UUID/g' | cut -c1-180
  echo "@@fail сервер не отвечает по этому ключу (код проверки $C) — настройки роутера не менялись"
fi
rm -f /tmp/rl-vless-test.log
'''


def xkeen_apply(v):
    out, rt = xkeen_configs(v)
    D = '/opt/etc/xray/configs'
    return f'''mkdir -p {D}
for f in 04_outbounds 05_routing; do [ -f {D}/$f.json ] && [ ! -f {D}/$f.json.rl-bak ] && cp {D}/$f.json {D}/$f.json.rl-bak; done
''' + _heredoc(f'{D}/04_outbounds.json', out) + _heredoc(f'{D}/05_routing.json', rt) + f'''chmod 600 {D}/04_outbounds.json
if ! /opt/sbin/xray run -test -confdir {D} >/tmp/rl-x.log 2>&1; then
  tail -n 3 /tmp/rl-x.log | sed -E 's/[0-9a-fA-F]{{8}}-[0-9a-fA-F-]{{27}}/UUID/g' | cut -c1-180; rm -f /tmp/rl-x.log
  for f in 04_outbounds 05_routing; do [ -f {D}/$f.json.rl-bak ] && cp {D}/$f.json.rl-bak {D}/$f.json; done
  echo "@@fail Xray не принял настройки, прежние возвращены"; exit 0
fi
rm -f /tmp/rl-x.log
{_xkeen_run('-restart')}sleep 3
pidof xray >/dev/null 2>&1 || {{ echo "@@fail XKeen не запустился (см. журнал)"; exit 0; }}
echo @@ok
'''


XKEEN_CONTROL = {'start': _xkeen_run('-start', 90) + 'sleep 2; pidof xray mihomo >/dev/null && echo @@ok || echo "@@fail XKeen не запустился"\n',
                 'stop': _xkeen_run('-stop', 90) + 'sleep 2; pidof xray mihomo >/dev/null && echo "@@fail XKeen не остановился" || echo @@ok\n'}

# «xkeen -remove» asks questions, so the same steps by hand. The firewall rules go with -stop.
XKEEN_REMOVE = '''[ -x /opt/sbin/xkeen ] && XKEEN_FOREGROUND=1 /opt/sbin/xkeen -stop </dev/null >/dev/null 2>&1
sleep 2
for f in /opt/etc/init.d/*xkeen*; do [ -f "$f" ] && "$f" stop >/dev/null 2>&1; rm -f "$f"; done
opkg remove xkeen xray_s mihomo_s yq_s 2>&1 | tail -n 3
rm -rf /opt/sbin/xkeen /opt/sbin/.xkeen /opt/sbin/xray /opt/sbin/mihomo /opt/etc/xkeen /opt/etc/xray /opt/etc/mihomo /opt/var/log/xkeen /opt/var/log/xray
pidof xray >/dev/null 2>&1 && echo "@@fail Xray всё ещё работает" || echo @@ok
'''


def _awg_auth(user, password):
    """The panel may be open or closed: if closed, the Entware login (allowed by its API) gives a session cookie."""
    body = json.dumps({'login': user, 'password': password, 'method': 'entware'})
    tag = 'RLEOF' + secrets.token_hex(6)
    return f'''J=/tmp/rl-awg.$$; A={AWG_API}
curl -s -m 8 -c $J -b $J $A/auth/status | grep -q '"authenticated":true' || \\
  curl -s -m 15 -c $J -b $J -H 'Content-Type: application/json' --data-binary @- $A/auth/login >/dev/null <<'{tag}'
{body}
{tag}
curl -s -m 8 -c $J -b $J $A/auth/status | grep -q '"authenticated":true' || {{ rm -f $J; echo "@@fail панель AWG Manager не пустила: нужен вход в её настройках или более сложный пароль Entware"; exit 0; }}
'''


def awg_add(v, user, password):
    """Installs sing-box in AWG Manager if needed, adds the link as a tunnel, tests it. Traffic does not change: the connection is only added to the router's list."""
    tag = 'RLEOF' + secrets.token_hex(6)
    return _awg_auth(user, password) + f'''C="curl -s -m 30 -c $J -b $J"
if ! $C $A/singbox/status | grep -q '"installed":true'; then
  echo "ставлю sing-box"
  curl -s -m 280 -c $J -b $J -X POST $A/singbox/install | cut -c1-200; echo
  i=0; while [ $i -lt 24 ] && ! $C $A/singbox/status | grep -q '"installed":true'; do sleep 5; i=$((i+1)); done
  $C $A/singbox/status | grep -q '"installed":true' || {{ rm -f $J; echo "@@fail AWG Manager не установил sing-box"; exit 0; }}
fi
$C -H 'Content-Type: application/json' -d '{{"enabled":true}}' $A/singbox/ndms-proxy >/dev/null
echo "@@before $($C $A/singbox/tunnels)"
R=$($C -w '\\n%{{http_code}}' -H 'Content-Type: application/json' --data-binary @- $A/singbox/tunnels <<'{tag}'
{json.dumps({'links': v['link']}, ensure_ascii=False)}
{tag}
)
echo "@@code $(echo "$R" | tail -n 1)"
echo "@@resp $(echo "$R" | sed '$d' | head -c 600)"
echo "@@after $($C $A/singbox/tunnels)"
rm -f $J
'''


def awg_probe(tag_, user, password):
    q = urllib.parse.quote(tag_, safe='')
    return _awg_auth(user, password) + f'''echo "@@probe $(curl -s -m 25 -c $J -b $J "$A/singbox/tunnels/test/connectivity?tag={q}" | head -c 300)"
rm -f $J
'''


def awg_delete(tag_, user, password):
    q = urllib.parse.quote(tag_, safe='')
    return _awg_auth(user, password) + f'''echo "@@code $(curl -s -m 30 -c $J -b $J -o /dev/null -w '%{{http_code}}' -X DELETE "$A/singbox/tunnels?tag={q}")"
rm -f $J
'''


def awg_list(user, password):
    return _awg_auth(user, password) + '''echo "@@list $(curl -s -m 15 -c $J -b $J $A/singbox/tunnels)"
rm -f $J
'''


def tunnels_of(text):
    """Tag and safe fields of AWG Manager tunnels from its JSON answer."""
    try:
        d = json.loads(text)
    except ValueError:
        return []
    d = d.get('data', d) if isinstance(d, dict) else d
    if isinstance(d, dict):
        d = d.get('tunnels') or []
    out = []
    for t in d if isinstance(d, list) else []:
        if isinstance(t, dict) and t.get('tag'):
            out.append({'tag': t['tag'], 'name': t.get('name') or t['tag'], 'type': t.get('type') or t.get('protocol') or '',
                        'server': t.get('server') or t.get('address') or '', 'port': t.get('port') or t.get('listenPort') or ''})
    return out


def mask(text):
    """Nothing secret in logs and error messages, whatever a tool printed."""
    text = re.sub(r'vless://\S+', 'vless://…', str(text))
    return re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', 'UUID', text)
