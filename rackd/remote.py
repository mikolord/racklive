"""«Удалённый доступ» (WireGuard): a router that is set up here and then taken to another place keeps a tunnel to a WireGuard server of the owner
(«the hub»: his router's WireGuard server — Keenetic now — or, later, one built into Rack Live). Through it Rack Live manages the router exactly as if it
stood next to it: the same driver, plugins, backups, terminal.

The tunnel carries management ONLY:
  · the router routes into it just the hub's tunnel network and the address of the machine Rack Live runs on — no default route, the internet of that place
    stays with its own provider;
  · the router's own clients (LAN, Wi-Fi, guests) have no way into the tunnel: its firewall zone has no forwarding to or from any other zone;
  · from the tunnel only SSH, the web interface and ping reach the router itself;
  · on the hub the router is allowed exactly one address (/32), so it cannot use the owner's internet either.
The router dials out and keeps the tunnel up (keepalive 25 s), so the remote place needs no white address and no port forwarding."""
import ipaddress, re, socket, time

from . import plugins

STATUS = r'''command -v wg >/dev/null 2>&1 && echo "@@wg 1"
echo "@@rel $(. /etc/openwrt_release 2>/dev/null; echo $DISTRIB_RELEASE)"
echo "@@free $(df -k /overlay 2>/dev/null | awk 'NR==2{print $4}')"
if [ "$(uci -q get network.rl_wg)" = interface ]; then
  echo "@@ip $(uci -q get network.rl_wg.addresses | cut -d/ -f1)"
  echo "@@ep $(uci -q get network.rl_wgpeer.endpoint_host):$(uci -q get network.rl_wgpeer.endpoint_port)"
  echo "@@dom $(uci -q get network.rl_wg.rl_domain)"
  echo "@@hub $(uci -q get network.rl_wgpeer.public_key)"
  echo "@@allowed $(uci -q get network.rl_wgpeer.allowed_ips)"
  if command -v wg >/dev/null 2>&1; then
    echo "@@hs $(wg show rl_wg latest-handshakes 2>/dev/null | awk '{print $2}' | head -1)"
    echo "@@tr $(wg show rl_wg transfer 2>/dev/null | awk '{print $2, $3}' | head -1)"
  fi
fi
[ -s /etc/rl-wg/pub ] && echo "@@mypub $(cat /etc/rl-wg/pub)"
echo "@@now $(date +%s)"
echo @@end
'''

PREPARE = plugins.OWRT_PKG + r'''if ! command -v wg >/dev/null 2>&1 || [ ! -e /lib/netifd/proto/wireguard.sh ]; then
  echo "Ставлю WireGuard (kmod-wireguard, wireguard-tools)…"
  pupd >/dev/null 2>&1
  padd kmod-wireguard wireguard-tools 2>&1 | tail -5
fi
command -v wg >/dev/null 2>&1 || { echo "@@fail не удалось поставить WireGuard (kmod-wireguard, wireguard-tools) — нет интернета или места"; exit 0; }
mkdir -p /etc/rl-wg && chmod 700 /etc/rl-wg
umask 077
[ -s /etc/rl-wg/key ] || wg genkey > /etc/rl-wg/key
wg pubkey < /etc/rl-wg/key > /etc/rl-wg/pub
[ -s /etc/rl-wg/psk ] || wg genpsk > /etc/rl-wg/psk
echo "@@pub $(cat /etc/rl-wg/pub)"
echo "@@psk $(cat /etc/rl-wg/psk)"
'''

# every minute: when the tunnel is silent, the hub's public address (re-resolved by its domain — the owner's white address may change; A records only:
# KeenDNS IPv6 goes through a cloud that does not carry UDP) and its home address (the router is still on the owner's desk, where the public one does
# not loop back) are tried in turn
WATCH = r'''#!/bin/sh
# Rack Live: keeps the management tunnel pointed at the hub
[ "$(uci -q get network.rl_wg)" = interface ] || exit 0
HS=$(wg show rl_wg latest-handshakes 2>/dev/null | awk '{print $2}' | head -1)
NOW=$(date +%s)
[ -n "$HS" ] && [ "$HS" -gt 0 ] && [ $((NOW - HS)) -lt 150 ] && exit 0
UP=$(cat /tmp/rl-wg-up 2>/dev/null || echo 0); [ $((NOW - UP)) -lt 150 ] && exit 0
PUB=$(uci -q get network.rl_wg.rl_public); ALT=$(uci -q get network.rl_wg.rl_alt); D=$(uci -q get network.rl_wg.rl_domain)
if [ -n "$D" ]; then
  IP=$(nslookup "$D" 2>/dev/null | awk '/^Name:/{n=1} n && /^Address/{print $NF}' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
  [ -n "$IP" ] && [ "$IP" != "$PUB" ] && { PUB=$IP; uci set network.rl_wg.rl_public="$IP"; }
fi
CUR=$(uci -q get network.rl_wgpeer.endpoint_host)
NEXT=$PUB; [ "$CUR" = "$PUB" ] && [ -n "$ALT" ] && NEXT=$ALT
[ -n "$NEXT" ] || exit 0
uci set network.rl_wgpeer.endpoint_host="$NEXT"; uci commit network
wg set rl_wg peer "$(uci -q get network.rl_wgpeer.public_key)" endpoint "$NEXT:$(uci -q get network.rl_wgpeer.endpoint_port)"
echo "$NOW" > /tmp/rl-wg-up
logger -t rl-wg "нет связи с центром, пробую $NEXT"
'''

REMOVE = r'''cat > /tmp/rl-wg-off.sh <<'RLOFF'
sleep 3
uci -q delete network.rl_wg; uci -q delete network.rl_wgpeer; uci -q delete network.rl_wgrule; uci commit network
uci -q delete firewall.rl_wgz; uci -q delete firewall.rl_wgmgmt; uci -q delete firewall.rl_wgping; uci commit firewall
sed -i '/rl-wg-watch/d' /etc/crontabs/root 2>/dev/null; /etc/init.d/cron restart >/dev/null 2>&1
rm -f /usr/bin/rl-wg-watch; rm -rf /etc/rl-wg
/etc/init.d/network reload; /etc/init.d/firewall reload >/dev/null 2>&1
RLOFF
setsid sh /tmp/rl-wg-off.sh </dev/null >/dev/null 2>&1 &
echo @@ok
'''


def _q(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


TABLE = 3141          # the tunnel's own routing table: only what the router answers FROM its tunnel address goes there


def apply_script(ip, hub_pub, ep_ip, port, domain, allowed, alt=''):
    """the tunnel interface, its peer (the hub), a closed firewall zone and the watchdog. LAN, WAN and Wi-Fi are not touched."""
    for v in (hub_pub,):
        if not re.match(r'^[A-Za-z0-9+/]{42,44}=?$', v):
            raise ValueError('неверный ключ центра')
    ipaddress.ip_address(ip)
    ipaddress.ip_address(ep_ip)
    if alt:
        ipaddress.ip_address(alt)
    nets = [str(ipaddress.ip_network(a, strict=False)) for a in allowed]
    lines = ['set -e', 'K=$(cat /etc/rl-wg/key); P=$(cat /etc/rl-wg/psk)',
             'uci -q delete network.rl_wg || true', 'uci -q delete network.rl_wgpeer || true',
             'uci set network.rl_wg=interface', 'uci set network.rl_wg.proto=wireguard', 'uci set network.rl_wg.private_key="$K"',
             f'uci add_list network.rl_wg.addresses={_q(ip + "/32")}', f'uci set network.rl_wg.rl_domain={_q(domain or "")}',
             f'uci set network.rl_wg.rl_public={_q(ep_ip)}', f'uci set network.rl_wg.rl_alt={_q(alt or "")}', f'uci set network.rl_wg.ip4table={TABLE}',
             # start with the home address when the router sits right behind the hub (its gateway IS the hub): the public one does not loop back from inside
             f"EP={_q(ep_ip)}; GW=$(ip -4 route show default | awk '{{print $3; exit}}'); [ -n {_q(alt or '')} ] && [ \"$GW\" = {_q(alt or '-')} ] && EP={_q(alt or '')}",
             'uci -q delete network.rl_wgrule || true',             # (older version) — with ip4table the network service adds «from <tunnel address> lookup TABLE» itself
             'uci set network.rl_wgpeer=wireguard_rl_wg', "uci set network.rl_wgpeer.description='Rack Live'",
             f'uci set network.rl_wgpeer.public_key={_q(hub_pub)}', 'uci set network.rl_wgpeer.preshared_key="$P"',
             'uci set network.rl_wgpeer.endpoint_host="$EP"', f'uci set network.rl_wgpeer.endpoint_port={int(port)}',
             'uci set network.rl_wgpeer.persistent_keepalive=25', 'uci set network.rl_wgpeer.route_allowed_ips=1']
    lines += [f'uci add_list network.rl_wgpeer.allowed_ips={_q(n)}' for n in nets]
    lines += ['uci commit network',
              'for s in rl_wgz rl_wgmgmt rl_wgping; do uci -q delete firewall.$s || true; done',
              # the zone has NO forwardings: nobody from the router's networks reaches the tunnel, nothing from the tunnel reaches its networks
              "uci set firewall.rl_wgz=zone; uci set firewall.rl_wgz.name=rlwg; uci add_list firewall.rl_wgz.network=rl_wg",
              "uci set firewall.rl_wgz.input=REJECT; uci set firewall.rl_wgz.output=ACCEPT; uci set firewall.rl_wgz.forward=REJECT",
              "uci set firewall.rl_wgmgmt=rule; uci set firewall.rl_wgmgmt.name='Rack Live: управление через туннель'; uci set firewall.rl_wgmgmt.src=rlwg",
              "uci set firewall.rl_wgmgmt.proto=tcp; uci set firewall.rl_wgmgmt.dest_port='22 80 443'; uci set firewall.rl_wgmgmt.target=ACCEPT",
              "uci set firewall.rl_wgping=rule; uci set firewall.rl_wgping.name='Rack Live: ping через туннель'; uci set firewall.rl_wgping.src=rlwg",
              "uci set firewall.rl_wgping.proto=icmp; uci set firewall.rl_wgping.icmp_type=echo-request; uci set firewall.rl_wgping.target=ACCEPT",
              'uci commit firewall',
              "cat > /usr/bin/rl-wg-watch <<'RLWATCH'", WATCH.rstrip('\n'), 'RLWATCH', 'chmod 755 /usr/bin/rl-wg-watch',
              "sed -i '/rl-wg-watch/d' /etc/crontabs/root 2>/dev/null; echo '* * * * * /usr/bin/rl-wg-watch' >> /etc/crontabs/root",
              '/etc/init.d/cron enable >/dev/null 2>&1 || true', '/etc/init.d/cron restart >/dev/null 2>&1 || true',
              'set +e', 'date +%s > /tmp/rl-wg-up', '/etc/init.d/network reload', 'sleep 3', 'ifup rl_wg', 'sleep 2',
              # WireGuard was just installed: the network service learns a new connection type only when it starts — restart it once (Wi-Fi blinks for a few seconds)
              'if ifstatus rl_wg 2>/dev/null | grep -q \'"proto": "none"\'; then echo "@@restart"; setsid sh -c "sleep 1; /etc/init.d/network restart" </dev/null >/dev/null 2>&1 & sleep 25; fi',
              '/etc/init.d/firewall reload >/dev/null 2>&1',
              'HS=0; i=0',
              'while [ $i -lt 15 ]; do HS=$(wg show rl_wg latest-handshakes 2>/dev/null | awk \'{print $2}\' | head -1); [ "${HS:-0}" -gt 0 ] && break; i=$((i+1)); sleep 2; done',
              'echo "@@hs ${HS:-0}"', 'echo @@done']
    return '\n'.join(lines) + '\n'


def parse(out):
    s = {'wg': False, 'rel': '', 'free': None, 'ip': None, 'ep': None, 'domain': None, 'hub': None, 'allowed': [], 'hs': None, 'rx': None, 'tx': None,
         'pub': None, 'now': None}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        v = v.strip()
        if k == '@@wg':
            s['wg'] = True
        elif k == '@@rel':
            s['rel'] = v
        elif k == '@@free' and v.isdigit():
            s['free'] = int(v)
        elif k == '@@ip' and v:
            s['ip'] = v
        elif k == '@@ep' and v != ':':
            s['ep'] = v
        elif k == '@@dom' and v:
            s['domain'] = v
        elif k == '@@hub' and v:
            s['hub'] = v
        elif k == '@@allowed' and v:
            s['allowed'] = v.split()
        elif k == '@@hs' and v.isdigit():
            s['hs'] = int(v)
        elif k == '@@tr':
            p = v.split()
            if len(p) == 2 and all(x.isdigit() for x in p):
                s['rx'], s['tx'] = int(p[0]), int(p[1])
        elif k == '@@mypub' and v:
            s['pub'] = v
        elif k == '@@now' and v.isdigit():
            s['now'] = int(v)
    s['installed'] = bool(s['ip'])
    s['ago'] = s['now'] - s['hs'] if s['hs'] and s['now'] else None
    s['up'] = s['ago'] is not None and s['ago'] < 180
    return s


def pick_ip(net, used, keep=None):
    """a free address of the hub's tunnel network; the one the router had stays if it is still free"""
    n = ipaddress.ip_network(net, strict=False)
    used = {str(x) for x in used}
    if keep and ipaddress.ip_address(keep) in n and keep not in used:
        return keep
    for h in n.hosts():
        if str(h) not in used and int(h) - int(n.network_address) >= 2:
            return str(h)
    raise ValueError(f'в сети туннеля {net} не осталось свободных адресов')


def source_ip(toward):
    """the address this machine uses to reach the hub — the router has to route its answers there"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((toward, 9))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def allowed_for(net, src, extra=()):
    """what the router routes into the tunnel: the hub's network, this machine (if it is outside it), and addresses the owner added himself"""
    n = ipaddress.ip_network(net, strict=False)
    out = [str(n)]
    if src and ipaddress.ip_address(src) not in n:
        out.append(src + '/32')
    for x in extra:
        x = str(x).strip()
        if not x:
            continue
        try:
            e = ipaddress.ip_network(x, strict=False)
        except ValueError:
            raise ValueError(f'«{x}» — не адрес и не сеть')
        if not e.is_private or e.prefixlen < 16:
            raise ValueError(f'«{x}»: можно только частные адреса и сети не больше /16 — иначе в туннель уйдёт интернет')
        if str(e) not in out:
            out.append(str(e))
    return out


def slug(name):
    t = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
         'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ы': 'y', 'э': 'e', 'ю': 'yu', 'я': 'ya'}
    s = ''.join(t.get(c, c) for c in str(name or '').lower())
    return ('RL-' + re.sub(r'[^a-z0-9]+', '-', s).strip('-'))[:30] or 'RL-router'


# ───────── orchestration (two devices at once: the router and the hub) ─────────
def hubs(app):
    """every WireGuard server Rack Live can use as a hub: Keenetic devices with a WireGuard server"""
    from .drivers import REGISTRY
    out = []
    for k in app.store.cfg['devices']:
        if k.get('driver') != 'keenetic' or not k.get('enabled', True):
            continue
        try:
            for h in REGISTRY['keenetic'].wg_hubs(k):
                out.append(dict(h, id=f"{k['id']}:{h['iface']}", device=k['id'], deviceName=k.get('name') or 'Keenetic', kind='keenetic', used=len(h['used']),
                                peers=len(h['peers']), reach=h['domain'] or h['wan']))
        except Exception as e:
            out.append({'id': f"{k['id']}:", 'device': k['id'], 'deviceName': k.get('name') or 'Keenetic', 'kind': 'keenetic', 'error': str(e)[:160]})
    return out


def _hub(app, hub_id):
    from .drivers import REGISTRY
    did, _, iface = str(hub_id or '').partition(':')
    k = app.store.device(did)
    if not k or k.get('driver') != 'keenetic':
        raise ValueError('центр не найден — выберите его заново')
    h = next((x for x in REGISTRY['keenetic'].wg_hubs(k) if x['iface'] == iface), None)
    if not h:
        raise ValueError(f'на «{k.get("name")}» нет WireGuard-сервера {iface}')
    return k, h


def _resolve4(name):
    try:
        return next(a[4][0] for a in socket.getaddrinfo(name, None, socket.AF_INET))
    except (OSError, StopIteration):
        return None


def connect(app, d, drv, body, prog):
    from .drivers import REGISTRY
    from .util import DriverError
    k, h = _hub(app, body.get('hub'))
    if not h.get('up'):
        raise DriverError(f"WireGuard-сервер «{h['name']}» выключен — включите его на роутере")
    old = d.get('remote') or {}
    prog('Ставлю WireGuard на роутер и создаю ключи…')
    out = drv._ssh(d, PREPARE, 300)
    fail = re.search(r'@@fail (.+)', out)
    if fail:
        raise DriverError(fail.group(1))
    pub = (re.search(r'@@pub (\S+)', out) or [None, ''])[1]
    psk = (re.search(r'@@psk (\S+)', out) or [None, ''])[1]
    if not pub or not psk:
        raise DriverError('роутер не создал ключи WireGuard')
    mine = (h.get('owner') or {}).get(pub) or (old.get('ip') if old.get('hub') == body.get('hub') and old.get('pub') == pub else None)
    ip = pick_ip(h['net'], [x for x in h['used'] if x != mine], mine)          # a router that is already a peer keeps its address
    src = source_ip(h['ip'])
    allowed = allowed_for(h['net'], src, body.get('extra') or [])
    domain = h['domain'] if body.get('endpoint', 'auto') == 'auto' else str(body.get('endpoint')).strip()
    ep = h['wan'] if domain == h['domain'] and h['wan'] else (_resolve4(domain) if domain else h['wan'])
    if not ep:
        raise DriverError('не удалось узнать внешний адрес центра — укажите его вручную')
    prog(f"Добавляю подключение на «{k.get('name')}»…")
    if old.get('pub') and old.get('pub') != pub and old.get('hub') == body.get('hub'):
        REGISTRY['keenetic'].wg_peer(k, h['iface'], 'remove', old['pub'])
    REGISTRY['keenetic'].wg_peer(k, h['iface'], 'add', pub, psk, ip, slug(d.get('name')))
    prog('Настраиваю туннель на роутере…')
    alt = re.sub(r'^\w+://|[:/].*$', '', k.get('host') or '')
    try:
        alt = alt if ipaddress.ip_address(alt).is_private else ''
    except ValueError:
        alt = ''
    out = drv._ssh(d, apply_script(ip, h['pub'], ep, h['port'], domain, allowed, alt), 150)
    if '@@done' not in out:
        raise DriverError('роутер не закончил настройку: ' + (out.strip().splitlines() or ['нет ответа'])[-1][:160])
    hs = int((re.search(r'@@hs (\d+)', out) or [None, '0'])[1])
    info = {'hub': body.get('hub'), 'hubName': f"{k.get('name')} · {h['name']}", 'iface': h['iface'], 'ip': ip, 'pub': pub, 'endpoint': f"{domain or ep}:{h['port']}",
            'allowed': allowed, 'extra': [x for x in body.get('extra') or [] if str(x).strip()]}
    upd = {'remote': info}
    reach = False
    if '@@restart' in out:
        prog('Сеть роутера перезапустилась — жду туннель…')
        for _ in range(12):
            time.sleep(5)
            try:
                rs = parse(drv._ssh(d, STATUS, 20))
                if rs['hs']:
                    hs = rs['hs']
                    break
            except Exception:
                pass
    if hs:
        prog(f'Проверяю связь через туннель ({ip})…')
        for _ in range(6):
            try:
                if '@@ok' in drv._ssh(dict(d, host=ip), 'echo @@ok', 15):
                    reach = True
                    break
            except Exception:
                pass
            time.sleep(5)
    if reach and body.get('use', True):
        upd['hostLocal'] = old.get('hostLocal') or d.get('hostLocal') or d.get('host')
        upd['host'] = ip
    msg = (f'Готово: роутер подключён к «{info["hubName"]}», адрес в туннеле {ip}. ' +
           ('Rack Live теперь работает с ним через туннель — роутер можно увозить: он сам выйдет на связь из любого интернета.' if reach and body.get('use', True) else
            'Туннель работает, Rack Live пока ходит на роутер по местному адресу.' if reach else
            'Туннель поднялся, но Rack Live не достучался до роутера через него — адрес оставлен прежним. ' if hs else
            'Роутер ещё не связался с центром (нет рукопожатия) — проверьте, что порт центра доступен из интернета. '))
    return {'ok': bool(hs), 'message': msg, 'deviceUpdate': upd, 'reach': reach, 'handshake': bool(hs)}


def disconnect(app, d, drv, body, prog):
    from .drivers import REGISTRY
    info = d.get('remote') or {}
    log = []
    if info.get('hub') and info.get('pub'):
        prog('Убираю подключение из центра…')
        try:
            k, h = _hub(app, info['hub'])
            REGISTRY['keenetic'].wg_peer(k, h['iface'], 'remove', info['pub'])
        except Exception as e:
            log.append(f'центр: {e}')
    prog('Убираю туннель с роутера…')
    local = d.get('hostLocal')
    try:
        drv._ssh(d, REMOVE, 30)
    except Exception as e:
        log.append(f'роутер: {e}')
    upd = {'remote': None, 'hostLocal': None}
    if local and d.get('host') == info.get('ip'):
        upd['host'] = local
    return {'ok': True, 'deviceUpdate': upd, 'message': 'Удалённый доступ отключён: туннель и подключение в центре удалены.' +
            (f' Rack Live снова ходит на роутер по адресу {local} — если роутер уже не рядом, связи с ним не будет.' if upd.get('host') else '') +
            (' Замечания: ' + '; '.join(log) if log else '')}
