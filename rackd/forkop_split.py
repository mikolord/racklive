"""Forkop «Раздельный VPN»: one pasted thing (an AmneziaWG / WireGuard .conf, VLESS-style links or a subscription URL) becomes the same
setup as on the Cudy «Андрей город VPN»: Russian sites go straight (list ru_only + .ru .su .рф), everything else of the router's network
goes through the VPN. Two Forkop sections (rl_ru, rl_vpn) and their children in /etc/config/forkop.

Before writing, the old file is copied to /root/forkop.rl-<time>.bak (the newest three stay); if Forkop does not come up with the new
setup, the copy is put back and Forkop restarted, so the router keeps the internet it had. Keys are never printed back."""
import ipaddress, re, shlex
from urllib.parse import unquote, urlsplit

LINK_SCHEMES = ('vless', 'vmess', 'trojan', 'ss', 'hysteria2', 'hy2', 'tuic', 'anytls', 'socks', 'socks5')
# AmneziaWG fields Forkop knows (singbox/amnezia.uc); they live in the tunnel as amnezia_<key>
AWG_KEYS = ('jc', 'jmin', 'jmax', 's1', 's2', 's3', 's4', 'h1', 'h2', 'h3', 'h4', 'i1', 'i2', 'i3', 'i4', 'i5',
            'header_protection_key', 'content_padding_addition', 'rekey_after_time', 'rekey_timeout', 'reject_after_time',
            'keepalive_timeout', 'max_handshake_attempts', 'random_trailers', 'disable_cookies')
AWG_FLAGS = ('random_trailers', 'disable_cookies')
# present only in AmneziaWG (both sides must match): their presence makes the tunnel «amneziawg», not plain WireGuard
AWG_TWO_SIDED = ('s1', 's2', 's3', 's4', 'h1', 'h2', 'h3', 'h4', 'header_protection_key')
OURS = ('rl_ru', 'rl_vpn')
CHILD_TYPES = ('tunnel', 'connection_link', 'subscription_url', 'section_interface', 'urltest', 'fallback_group', 'fallback_level')


class SplitError(ValueError):
    pass


def _snake(k):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', k.strip()).lower()


def _name(s, fallback):
    s = re.sub(r'[^\w .\-()]+', ' ', s or '', flags=re.U)            # Forkop: no «/», emoji dropped
    s = re.sub(r'\s+', ' ', s).strip(' .-')[:32]
    return s or fallback


def parse_conf(text):
    """An AmneziaWG or WireGuard client .conf → tunnel + peer (Forkop's option names). Raises SplitError."""
    sec, iface, peers, comment = None, {}, [], ''
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            comment = comment or line.lstrip('#').strip()
            continue
        m = re.match(r'^\[(\w+)\]$', line)
        if m:
            sec = m.group(1).lower()
            if sec == 'peer':
                peers.append({})
            continue
        if '=' not in line or sec not in ('interface', 'peer'):
            continue
        k, v = line.split('=', 1)
        (iface if sec == 'interface' else peers[-1])[_snake(k)] = v.strip()
    if not iface.get('private_key'):
        raise SplitError('в конфиге нет PrivateKey в разделе [Interface]')
    if len(peers) != 1:
        raise SplitError('в конфиге должен быть ровно один раздел [Peer]' if peers else 'в конфиге нет раздела [Peer]')
    peer = peers[0]
    if not peer.get('public_key') or not peer.get('endpoint'):
        raise SplitError('в разделе [Peer] нет PublicKey или Endpoint')
    m = re.match(r'^\[?([^\]]+?)\]?:(\d{1,5})$', peer['endpoint'])
    if not m:
        raise SplitError(f"не понял адрес сервера «{peer['endpoint']}» (нужно host:port)")
    addrs, skipped6 = [], False
    for a in re.split(r'[,\s]+', iface.get('address', '')):
        if not a:
            continue
        try:
            n = ipaddress.ip_interface(a)
        except ValueError:
            raise SplitError(f'не понял адрес в туннеле «{a}»')
        if n.version == 6:
            skipped6 = True                           # Forkop's section routes IPv4 (the LAN is IPv4); IPv6 in the tunnel would only confuse it
            continue
        addrs.append(str(n))
    if not addrs:
        raise SplitError('в конфиге нет IPv4-адреса (Address) в разделе [Interface]')
    amn = {}
    for k in AWG_KEYS:
        if iface.get(k, '') != '':
            v = iface[k]
            if k in AWG_FLAGS:
                v = '1' if v.lower() in ('1', 'on', 'true', 'yes') else '0'
            amn[k] = v
    kind = 'amneziawg' if any(k in amn for k in AWG_TWO_SIDED) else 'wireguard'
    allowed = [a for a in re.split(r'[,\s]+', peer.get('allowed_ips', '0.0.0.0/0')) if a and ':' not in a] or ['0.0.0.0/0']
    tunnel = {'kind': kind, 'address': addrs, 'private_key': iface['private_key']}
    if iface.get('mtu', '').isdigit():
        tunnel['mtu'] = iface['mtu']
    tunnel.update({'amnezia_' + k: v for k, v in amn.items()})
    peer_out = {'address': m.group(1), 'port': m.group(2), 'public_key': peer['public_key'], 'allowed_ips': allowed}
    if peer.get('preshared_key'):
        peer_out['pre_shared_key'] = peer['preshared_key']
    if peer.get('persistent_keepalive', '').isdigit():
        peer_out['persistent_keepalive_interval'] = peer['persistent_keepalive']
    return {'type': 'tunnel', 'kind': kind, 'name': _name(comment,'AWG' if kind == 'amneziawg' else 'WireGuard'), 'raw': text.strip(),
            'tunnel': tunnel, 'peer': peer_out, 'server': f"{m.group(1)}:{m.group(2)}", 'address': ', '.join(addrs), 'mtu': tunnel.get('mtu', ''),
            'psk': 'pre_shared_key' in peer_out, 'ipv6Skipped': skipped6, 'dns': iface.get('dns', ''), 'awgFields': len(amn)}


def parse_links(text):
    """VLESS / VMess / Trojan / Shadowsocks / Hysteria2 / TUIC / AnyTLS / SOCKS links, one per line → [{uri, name, scheme, host}]."""
    out, seen = [], set()
    for line in text.split():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        scheme = line.split('://', 1)[0].lower() if '://' in line else ''
        if scheme not in LINK_SCHEMES:
            raise SplitError(f'«{line[:40]}…» — не ссылка на сервер (поддерживаются {", ".join(s for s in LINK_SCHEMES if s not in ("hy2", "socks5"))})')
        frag = unquote(line.split('#', 1)[1]) if '#' in line else ''
        try:
            host = urlsplit(line).hostname or ''
        except ValueError:
            host = ''
        name = _name(frag, f'Сервер {len(out) + 1}')
        base, k = name, 2
        while name.lower() in seen:                    # Forkop wants unique names
            name, k = f'{base[:28]} {k}', k + 1
        seen.add(name.lower())
        out.append({'uri': line, 'name': name, 'scheme': 'vmess' if scheme == 'vmess' else scheme, 'host': host})
    if not out:
        raise SplitError('ссылок не найдено')
    return out


def parse(text):
    """Whatever was pasted → {'type': 'tunnel'|'links'|'subscription', ...}. Raises SplitError with a human reason."""
    text = (text or '').replace('\r', '').strip()
    if not text:
        raise SplitError('вставьте конфиг AmneziaWG / WireGuard, ссылки на серверы или ссылку на подписку')
    if len(text) > 200000:
        raise SplitError('слишком длинный текст')
    if re.search(r'^\s*\[Interface\]', text, re.M | re.I):
        return parse_conf(text)
    one = text.split()
    if len(one) == 1 and re.match(r'^https?://', one[0], re.I):
        u = one[0]
        try:
            host = urlsplit(u).hostname
        except ValueError:
            host = None
        if not host:
            raise SplitError('не понял адрес подписки')
        return {'type': 'subscription', 'url': u, 'host': host, 'name': _name(host, 'Подписка')}
    links = parse_links(text)
    return {'type': 'links', 'links': links, 'count': len(links)}


def public(p):
    """What the page may see: no private key, no link with its UUID / password."""
    if p['type'] == 'tunnel':
        return {k: p[k] for k in ('type', 'kind', 'name', 'server', 'address', 'mtu', 'psk', 'ipv6Skipped', 'dns', 'awgFields')}
    if p['type'] == 'links':
        return {'type': 'links', 'count': p['count'], 'links': [{'name': l['name'], 'scheme': l['scheme'], 'host': l['host']} for l in p['links']]}
    return {'type': 'subscription', 'host': p['host'], 'name': p['name']}


def check_net(net):
    if not net:
        return ''
    try:
        n = ipaddress.ip_network(str(net).strip(), strict=False)
    except ValueError:
        raise SplitError(f'не понял сеть «{net}» (нужно, например, 192.168.1.0/24)')
    if n.version != 4 or n.prefixlen < 8:
        raise SplitError('нужна IPv4-сеть не шире /8')
    return str(n)


q = shlex.quote

STATUS = r"""
[ -x /usr/bin/forkop ] || { echo "@@nofk"; echo "@@end"; exit 0; }
. /lib/functions/network.sh 2>/dev/null; network_get_subnet S lan 2>/dev/null
if [ -n "$S" ]; then eval "$(ipcalc.sh "$S" 2>/dev/null)"; echo "@@lan $NETWORK/$PREFIX"; fi
uci -q show forkop | grep -E '^forkop\.[^.]+=(section|tunnel|connection_link|subscription_url)$' | while IFS== read -r k t; do
  s=${k#forkop.}; echo "@@sec $t $s $(uci -q get forkop.$s.section) |$(uci -q get forkop.$s.action)|$(uci -q get forkop.$s.name)"; done
forkop get_status 2>/dev/null | grep -q '"running": 1' && echo "@@run"
echo "@@end"
"""


def parse_status(out):
    st = {'forkop': '@@nofk' not in out, 'lan': '', 'running': '@@run' in out, 'sections': [], 'children': []}
    for line in out.splitlines():
        if line.startswith('@@lan '):
            st['lan'] = line[6:].strip()
        elif line.startswith('@@sec '):
            m = re.match(r'@@sec (\S+) (\S+) (\S*) \|([^|]*)\|(.*)$', line)
            if not m:
                continue
            t, s, parent, action, name = m.groups()
            if t == 'section':
                st['sections'].append({'id': s, 'action': action, 'name': name or s, 'ours': s in OURS})
            else:
                st['children'].append({'id': s, 'type': t, 'section': parent, 'name': name})
    st['applied'] = any(x['id'] == 'rl_vpn' for x in st['sections'])
    return st


def script(p, net='', replace_all=True, mode='split', lists=(), domains=()):
    """The shell script that writes the setup and starts Forkop, putting the old file back if it does not come up.
    mode 'split': Russia straight + the router's network through the VPN; 'sites': only the ticked lists and domains through the VPN."""
    net = check_net(net)
    L = ['B=/root/forkop.rl-$(date +%Y%m%d-%H%M%S).bak', 'cp /etc/config/forkop "$B" || { echo "@@fail не удалось сохранить копию /etc/config/forkop"; exit 0; }',
         'ls -1t /root/forkop.rl-*.bak 2>/dev/null | tail -n +4 | xargs -r rm -f', 'echo "@@bak $B"']
    if mode != 'split':
        pass
    elif net:
        L.append(f'NET={q(net)}')
    else:
        L += ['. /lib/functions/network.sh; network_get_subnet S lan', 'eval "$(ipcalc.sh "$S" 2>/dev/null)"', 'NET="${NETWORK:-}/${PREFIX:-}"',
              '[ "$NET" = "/" ] && { echo "@@fail не определил сеть роутера (lan) — укажите её вручную"; exit 0; }']
    if mode == 'split':
        L.append('echo "@@net $NET"')
    # what goes: our sections and their children (or every routing section, when asked to replace), never the settings or servers
    types = '|'.join(('section',) + CHILD_TYPES + ('tunnel_peer',))
    L.append(f"""uci -q show forkop | sed -n -E 's/^forkop\\.([^.=]+)=({types})$/\\1 \\2/p' > /tmp/rl-fk.items""")
    if replace_all:
        L.append('while read -r s t; do uci -q delete forkop.$s; done < /tmp/rl-fk.items')
    else:
        L.append("""while read -r s t; do case "$t" in section) case "$s" in rl_ru|rl_vpn) uci -q delete forkop.$s;; esac;;
  tunnel_peer) case "$(uci -q get forkop.$s.tunnel)" in rl_vpn_*) uci -q delete forkop.$s;; esac;;
  *) case "$(uci -q get forkop.$s.section)" in rl_ru|rl_vpn) uci -q delete forkop.$s;; esac;; esac; done < /tmp/rl-fk.items""")
    L.append('rm -f /tmp/rl-fk.items')
    S = lambda path, v: L.append(f'uci set forkop.{path}={q(str(v))}')
    A = lambda path, v: L.append(f'uci add_list forkop.{path}={q(str(v))}')
    if mode == 'split':
        S('rl_ru', 'section'); S('rl_ru.name', 'Россия напрямую'); S('rl_ru.action', 'bypass'); S('rl_ru.destinations', 'ru,su,xn--p1ai'); A('rl_ru.community_lists', 'ru_only')
    S('rl_vpn', 'section'); S('rl_vpn.name', 'Зарубеж через VPN' if mode == 'split' else 'Через VPN'); S('rl_vpn.action', 'connection')
    if mode == 'split':
        L.append('uci add_list forkop.rl_vpn.fully_routed_ips="$NET"')
    else:
        for x in lists:
            A('rl_vpn.community_lists', x)
        for d in domains:
            A('rl_vpn.user_domains', d)
    if p['type'] == 'tunnel':
        S('rl_vpn_tun', 'tunnel'); S('rl_vpn_tun.section', 'rl_vpn'); S('rl_vpn_tun.name', p['name'])
        for k, v in p['tunnel'].items():
            for x in (v if isinstance(v, list) else [v]):
                (A if isinstance(v, list) else S)(f'rl_vpn_tun.{k}', x)
        S('rl_vpn_peer', 'tunnel_peer'); S('rl_vpn_peer.tunnel', 'rl_vpn_tun')
        for k, v in p['peer'].items():
            for x in (v if isinstance(v, list) else [v]):
                (A if isinstance(v, list) else S)(f'rl_vpn_peer.{k}', x)
    elif p['type'] == 'links':
        for i, l in enumerate(p['links']):
            s = f'rl_vpn_l{i + 1}'
            S(s, 'connection_link'); S(f'{s}.section', 'rl_vpn'); S(f'{s}.name', l['name']); S(f'{s}.uri', l['uri']); S(f'{s}.order', i)
    else:
        S('rl_vpn_sub', 'subscription_url'); S('rl_vpn_sub.section', 'rl_vpn'); S('rl_vpn_sub.name', p['name']); S('rl_vpn_sub.url', p['url'])
        S('rl_vpn_sub.subscription_update_enabled', '1')
    L += (['uci reorder forkop.rl_ru=1', 'uci reorder forkop.rl_vpn=2'] if mode == 'split' else ['uci reorder forkop.rl_vpn=1']) + ['uci commit forkop',
          '/etc/init.d/forkop enable 2>/dev/null',
          '/etc/init.d/forkop restart > /tmp/rl-fk.log 2>&1',
          'ok=0; for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 2; forkop get_status 2>/dev/null | grep -q \'"running": 1\' && { ok=1; break; }; done',
          'if [ $ok = 1 ]; then sleep 3; forkop get_status 2>/dev/null | grep -q \'"running": 1\' || ok=0; fi',
          'if [ $ok = 1 ]; then echo "@@ok"; else',
          '  echo "@@why $(grep -v -i -E "key|uuid|password" /tmp/rl-fk.log | tail -n 4 | tr "\\n" " " | cut -c1-400)"',
          '  echo "@@why2 $(logread 2>/dev/null | grep -i -E "forkop|sing-box" | grep -v -i -E "key|uuid|password" | tail -n 3 | tr "\\n" " " | cut -c1-400)"',
          '  cp "$B" /etc/config/forkop; /etc/init.d/forkop restart >/dev/null 2>&1; echo "@@restored"; fi',
          'rm -f /tmp/rl-fk.log']
    return '\n'.join(L) + '\n'


def result(out):
    """Script output → {'ok', 'net', 'backup', 'why'}."""
    g = lambda tag: (re.search(r'^@@' + tag + r' ?(.*)$', out, re.M) or [None, ''])[1].strip()
    if '@@fail' in out:
        return {'ok': False, 'why': g('fail'), 'restored': False}
    why = ' '.join(x for x in (g('why'), g('why2')) if x)
    return {'ok': '@@ok' in out, 'net': g('net'), 'backup': g('bak'), 'why': why, 'restored': '@@restored' in out}
