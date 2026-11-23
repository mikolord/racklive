"""«Раздельный VPN» for Tachyon and Podkop (Forkop has its own rackd/forkop_split.py; the pasted thing is parsed there for all three).

Two modes:
  split — Russian sites go straight (.ru .su .рф + the list of Russian services), everything else of the router's network through the VPN;
  sites — only the ticked lists (blocked in Russia, YouTube, Telegram…) and the user's own domains go through the VPN, the rest straight.
Several servers: «auto» for pasted links lets the engine pick the fastest one (urltest) and switch when it falls; for a subscription
«auto» pins the main XHTTP server with the backup one taking over only on failure (priority_failover, see PRIORITY_MAIN/BACKUP).

Before writing, the old config is copied to /root/<engine>.rl-<time>.bak (the newest three stay); if the engine does not come up
with the new setup, the copy is put back and the engine restarted, so the router keeps the internet it had. Keys are never printed back."""
import base64, json, re, urllib.request
from .forkop_split import SplitError, check_net, parse_links, q

# community lists the three engines share (itdoginfo/allow-domains names); Podkop allows russia_inside only with some of them
LISTS = [
    {'id': 'russia_inside', 'label': 'Всё, что заблокировано в России', 'hint': 'общий список заблокированных и замедленных сайтов', 'on': True},
    {'id': 'youtube', 'label': 'YouTube'}, {'id': 'telegram', 'label': 'Telegram'}, {'id': 'discord', 'label': 'Discord'},
    {'id': 'meta', 'label': 'Instagram, Facebook, WhatsApp'}, {'id': 'twitter', 'label': 'X (Twitter)'}, {'id': 'tiktok', 'label': 'TikTok'},
    {'id': 'google_ai', 'label': 'Gemini и Google AI'}, {'id': 'google_play', 'label': 'Google Play'}, {'id': 'cloudflare', 'label': 'Cloudflare'},
    {'id': 'hdrezka', 'label': 'HDRezka'}, {'id': 'roblox', 'label': 'Roblox'},
]
LIST_IDS = {x['id'] for x in LISTS}
PODKOP_WITH_RU = {'russia_inside', 'meta', 'twitter', 'discord', 'telegram', 'cloudflare', 'google_ai', 'google_play', 'hetzner', 'ovh', 'hodca', 'roblox',
                  'digitalocean', 'cloudfront'}
RU_SUFFIX = ('ru', 'su', 'xn--p1ai')
RU_SERVICES = 'russia_outside'                 # Russian services on foreign domains (vk.com, yandex.com…): straight in the split mode
DOMAIN_RE = re.compile(r'^(?=.{1,253}$)(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9])?\.)*[a-z0-9-]{1,63}$')

# The house rule for router subscriptions: ONE main + ONE backup server, both plain XHTTP, failover only when the main one
# dies — never urltest hopping across the whole subscription (CDN/LTE links are already kept out of router subscriptions by the bot).
# Tachyon implements this as section priority_failover + two outbound_group levels; its priority daemon (tachyon_core/priority.uc)
# health-checks the active level and flips the selector only on failure. GOTCHA: include_outbounds matches the server DISPLAY NAME
# (shared by every server of a country), so the single XHTTP server is singled out by include_transports 'xhttp'.
PRIORITY_MAIN = ('rl_main_xhttp', '🇳🇱 Нидерланды', 'Нидерланды XHTTP (основной)')
PRIORITY_BACKUP = ('rl_backup_xhttp', '🇩🇪 Германия', 'Германия XHTTP (запасной)')


def check_opts(mode, lists, domains, engine):
    """→ (mode, lists, domains). Raises SplitError."""
    mode = 'sites' if mode == 'sites' else 'split'
    lists = [x for x in dict.fromkeys(lists or []) if x in LIST_IDS]
    out, bad = [], []
    for d in re.split(r'[\s,;]+', domains if isinstance(domains, str) else '\n'.join(domains or [])):
        d = d.strip().lower().removeprefix('https://').removeprefix('http://').split('/')[0].lstrip('*.').rstrip('.')
        if not d:
            continue
        try:
            d = d.encode('idna').decode('ascii')
        except UnicodeError:
            bad.append(d); continue
        (out if DOMAIN_RE.match(d) else bad).append(d)
    if bad:
        raise SplitError('не понял сайты: ' + ', '.join(bad[:5]))
    out = list(dict.fromkeys(out))[:500]
    if engine == 'podkop' and 'russia_inside' in lists:
        lists = [x for x in lists if x in PODKOP_WITH_RU]      # the rest is inside russia_inside already
    if mode == 'sites' and not lists and not out:
        raise SplitError('отметьте хотя бы один список или впишите свои сайты')
    return mode, lists, out


def fetch_subscription(url):
    """Podkop has no subscriptions: Rack Live reads it once and writes the servers as links (no auto-update)."""
    req = urllib.request.Request(url, headers={'User-Agent': 'v2rayN/7.0', 'Accept': '*/*'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(2_000_000).decode('utf-8', 'replace').strip()
    except Exception as e:
        raise SplitError(f'не получилось скачать подписку: {e}')
    if '://' not in body:
        try:
            body = base64.b64decode(body + '=' * (-len(body) % 4), altchars=b'-_' if '-' in body or '_' in body else None).decode('utf-8', 'replace')
        except ValueError:
            raise SplitError('подписка в непонятном формате (ожидались ссылки или base64)')
    lines = [l.strip() for l in body.splitlines() if re.match(r'^(vless|vmess|trojan|ss|hysteria2|hy2|tuic)://', l.strip(), re.I)]
    if not lines:
        raise SplitError('в подписке не нашлось ссылок на серверы, которые понимает Podkop')
    return parse_links('\n'.join(lines[:60]))


ENG = {
    'tachyon': {'cfg': 'tachyon', 'bin': '/usr/bin/tachyon', 'title': 'Tachyon', 'ours': ('rl_ru', 'rl_vpn'),
                'items': ('section', 'subscription_url', 'section_interface', 'urltest', 'priority_group', 'priority_level', 'condition',
                          'outbound_source', 'outbound_group', 'balancer'),
                'run': "ps w | grep -v grep | grep -q -E 'tachyon-core|sing-box'"},
    'podkop': {'cfg': 'podkop', 'bin': '/usr/bin/podkop', 'title': 'Podkop', 'ours': ('rl_ru', 'main'), 'items': ('section',),
               'run': 'pidof sing-box >/dev/null'},
}


def status_script(engine):
    e = ENG[engine]
    return rf"""
[ -x {e['bin']} ] || {{ echo "@@nofk"; echo "@@end"; exit 0; }}
. /lib/functions/network.sh 2>/dev/null; network_get_subnet S lan 2>/dev/null
if [ -n "$S" ]; then eval "$(ipcalc.sh "$S" 2>/dev/null)"; echo "@@lan $NETWORK/$PREFIX"; fi
uci -q show {e['cfg']} | grep -E '^{e['cfg']}\.[^.]+=section$' | while IFS== read -r k t; do
  s=${{k#{e['cfg']}.}}; echo "@@sec section $s $(uci -q get {e['cfg']}.$s.rl_managed)- |$(uci -q get {e['cfg']}.$s.action)$(uci -q get {e['cfg']}.$s.connection_type)|$(uci -q get {e['cfg']}.$s.label)"; done
[ -e /lib/netifd/proto/amneziawg.sh ] && echo "@@awgproto"
{e['run']} && echo "@@run"
echo "@@end"
"""


def parse_status(engine, out):
    ours = ENG[engine]['ours']
    st = {'forkop': '@@nofk' not in out, 'lan': '', 'running': '@@run' in out, 'sections': [], 'children': [], 'awgProto': '@@awgproto' in out}
    for line in out.splitlines():
        if line.startswith('@@lan '):
            st['lan'] = line[6:].strip()
        m = re.match(r'@@sec section (\S+) (\S*) \|([^|]*)\|(.*)$', line)
        if m:
            s, rl, action, name = m.groups()
            action = {'proxy': 'connection', 'vpn': 'connection', 'exclusion': 'bypass'}.get(action, action)
            mine = s in ours and rl.startswith('1')
            st['sections'].append({'id': s, 'action': action, 'name': name or ('Россия напрямую' if s == 'rl_ru' else 'Через VPN' if mine else s), 'ours': mine})
    st['applied'] = any(x['ours'] for x in st['sections'])
    st['lists'] = LISTS
    return st


def _head(e, extra_backup=()):
    L = [f"B=/root/{e['cfg']}.rl-$(date +%Y%m%d-%H%M%S).bak",
         f"cp /etc/config/{e['cfg']} \"$B\" || {{ echo \"@@fail не удалось сохранить копию /etc/config/{e['cfg']}\"; exit 0; }}"]
    for c in extra_backup:
        L.append(f'cp /etc/config/{c} "$B.{c}"')
    L += [f"ls -1t /root/{e['cfg']}.rl-*.bak 2>/dev/null | tail -n +4 | while read -r f; do rm -f \"$f\" \"$f\".*; done", 'echo "@@bak $B"']
    return L


def _net(L, net):
    if net:
        L.append(f'NET={q(net)}')
    else:
        L += ['. /lib/functions/network.sh; network_get_subnet S lan', 'eval "$(ipcalc.sh "$S" 2>/dev/null)"', 'NET="${NETWORK:-}/${PREFIX:-}"',
              '[ "$NET" = "/" ] && { echo "@@fail не определил сеть роутера (lan) — укажите её вручную"; exit 0; }']
    L.append('echo "@@net $NET"')


def _tail(e, L, restore=()):
    cfg = e['cfg']
    L += [f'uci commit {cfg}', f'/etc/init.d/{cfg} enable 2>/dev/null', f'/etc/init.d/{cfg} restart > /tmp/rl-vpn.log 2>&1',
          f"ok=0; for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do sleep 2; {e['run']} && {{ ok=1; break; }}; done",
          f"if [ $ok = 1 ]; then sleep 4; {e['run']} || ok=0; fi",
          'if [ $ok = 1 ]; then echo "@@ok"; else',
          '  echo "@@why $(grep -v -i -E "key|uuid|password" /tmp/rl-vpn.log | tail -n 4 | tr "\\n" " " | cut -c1-400)"',
          f'  echo "@@why2 $(logread 2>/dev/null | grep -i -E "{cfg}|sing-box|tachyon" | grep -v -i -E "key|uuid|password" | tail -n 3 | tr "\\n" " " | cut -c1-400)"',
          f'  cp "$B" /etc/config/{cfg}']
    for c in restore:
        L.append(f'  cp "$B.{c}" /etc/config/{c}')
    if restore:
        L.append('  /etc/init.d/network reload >/dev/null 2>&1; /etc/init.d/firewall reload >/dev/null 2>&1')
    L += [f'  /etc/init.d/{cfg} restart >/dev/null 2>&1; echo "@@restored"; fi', 'rm -f /tmp/rl-vpn.log']


def _delete(e, L, replace_all):
    cfg, types = e['cfg'], '|'.join(e['items'])
    L.append(f"""uci -q show {cfg} | sed -n -E 's/^{cfg}\\.([^.=]+)=({types})$/\\1 \\2/p' > /tmp/rl-vpn.items""")
    ours = '|'.join(e['ours'])
    if replace_all:
        L.append(f'while read -r s t; do uci -q delete {cfg}.$s; done < /tmp/rl-vpn.items')
    else:
        L.append(f"""while read -r s t; do case "$t" in section) case "$s" in {ours}) uci -q delete {cfg}.$s;; esac;;
  *) case "$(uci -q get {cfg}.$s.section)" in {ours}) uci -q delete {cfg}.$s;; esac;; esac; done < /tmp/rl-vpn.items""")
    L.append('rm -f /tmp/rl-vpn.items')


def tachyon_script(p, net='', replace_all=True, mode='split', lists=(), domains=(), auto=True):
    e = ENG['tachyon']
    L = _head(e)
    if mode == 'split':
        _net(L, check_net(net))
    _delete(e, L, replace_all)
    S = lambda path, v: L.append(f'uci set tachyon.{path}={q(str(v))}')
    A = lambda path, v: L.append(f'uci add_list tachyon.{path}={q(str(v))}')
    if mode == 'split':
        S('rl_ru', 'section'); S('rl_ru.label', 'Россия напрямую'); S('rl_ru.enabled', '1'); S('rl_ru.action', 'bypass'); S('rl_ru.rl_managed', '1')
        for d in RU_SUFFIX:
            A('rl_ru.domain_suffix', d)
        A('rl_ru.community_lists', RU_SERVICES)
    S('rl_vpn', 'section'); S('rl_vpn.label', 'Через VPN' if mode == 'sites' else 'Зарубеж через VPN'); S('rl_vpn.enabled', '1'); S('rl_vpn.action', 'connection')
    S('rl_vpn.rl_managed', '1')
    if mode == 'split':
        L.append('uci add_list tachyon.rl_vpn.fully_routed_ips="$NET"')
    else:
        for x in lists:
            A('rl_vpn.community_lists', x)
        for d in domains:
            A('rl_vpn.user_domains', d)
    if p['type'] == 'tunnel':
        A('rl_vpn.amnezia_configs', json.dumps({'name': p['name'], 'config': p['raw']}, ensure_ascii=False))
    elif p['type'] == 'links':
        for l in p['links']:
            A('rl_vpn.selector_proxy_links', l['uri'])
    else:
        S('rl_vpn_sub', 'subscription_url'); S('rl_vpn_sub.section', 'rl_vpn'); S('rl_vpn_sub.url', p['url'])
        S('rl_vpn_sub.subscription_update_enabled', '1'); S('rl_vpn_sub.subscription_update_interval', '12h')
    if auto and p['type'] == 'subscription':
        S('rl_vpn.urltest_enabled', '0')
        S('rl_vpn.section_selection_mode', 'priority_failover')
        for gid, _name, _title in (PRIORITY_MAIN, PRIORITY_BACKUP):
            A('rl_vpn.outbound_group_levels', gid)
            L.append(f'uci -q delete tachyon.{gid}')
        for gid, name, title in (PRIORITY_MAIN, PRIORITY_BACKUP):
            S(gid, 'outbound_group'); S(f'{gid}.name', title); S(f'{gid}.filter_mode', 'include')
            A(f'{gid}.include_outbounds', name); A(f'{gid}.include_transports', 'xhttp')
    elif auto and p['type'] == 'links' and p['count'] > 1:
        S('rl_vpn.urltest_enabled', '1')
    if mode == 'split':
        L.append('uci reorder tachyon.rl_ru=1')
    L.append('uci reorder tachyon.rl_vpn=%d' % (2 if mode == 'split' else 1))
    _tail(e, L)
    return '\n'.join(L) + '\n'


AWG_UCI = {'jc': 'awg_jc', 'jmin': 'awg_jmin', 'jmax': 'awg_jmax', 's1': 'awg_s1', 's2': 'awg_s2', 's3': 'awg_s3', 's4': 'awg_s4',
           'h1': 'awg_h1', 'h2': 'awg_h2', 'h3': 'awg_h3', 'h4': 'awg_h4', 'i1': 'awg_i1', 'i2': 'awg_i2', 'i3': 'awg_i3', 'i4': 'awg_i4', 'i5': 'awg_i5'}


def podkop_script(p, net='', replace_all=True, mode='split', lists=(), domains=(), auto=True):
    """Podkop: section «main» = through the VPN (proxy by links, or vpn = an AmneziaWG/WireGuard interface rl_awg made here),
    section rl_ru = exclusion (Russian sites straight) in the split mode."""
    e = ENG['podkop']
    tun = p['type'] == 'tunnel'
    L = _head(e, ('network', 'firewall') if tun else ())
    if mode == 'split':
        _net(L, check_net(net))
    if tun:                                     # the interface Podkop sends the traffic to
        t, pr, awg = p['tunnel'], p['peer'], p['kind'] == 'amneziawg'
        proto, pk = ('amneziawg', 'kmod-amneziawg amneziawg-tools luci-proto-amneziawg') if awg else ('wireguard', 'kmod-wireguard wireguard-tools luci-proto-wireguard')
        L += [f'if [ ! -e /lib/netifd/proto/{proto}.sh ]; then',
              '  PM=opkg; command -v apk >/dev/null 2>&1 && PM=apk',
              f'  if [ $PM = apk ]; then apk update >/dev/null 2>&1; apk add {pk} 2>&1 | tail -3; else opkg update >/dev/null 2>&1; opkg install {pk} 2>&1 | tail -3; fi',
              f'  [ -e /lib/netifd/proto/{proto}.sh ] || {{ echo "@@fail {"на роутере нет AmneziaWG (пакетов kmod-amneziawg / amneziawg-tools нет в репозитории этой прошивки) — поставьте их по инструкции github.com/Slava-Shchipunov/awg-openwrt или используйте Tachyon / Forkop: им отдельный пакет не нужен" if awg else "не получилось поставить WireGuard (kmod-wireguard)"}"; exit 0; }}',
              '  /etc/init.d/network reload; sleep 2', 'fi']
        N = lambda path, v: L.append(f'uci set network.{path}={q(str(v))}')
        NA = lambda path, v: L.append(f'uci add_list network.{path}={q(str(v))}')
        L += ['uci -q delete network.rl_awg', 'for s in $(uci -q show network | sed -n -E "s/^network\\.([^.=]+)=(amneziawg|wireguard)_rl_awg$/\\1/p"); do uci -q delete network.$s; done']
        N('rl_awg', 'interface'); N('rl_awg.proto', proto); N('rl_awg.private_key', t['private_key'])
        for a in t['address']:
            NA('rl_awg.addresses', a)
        if t.get('mtu'):
            N('rl_awg.mtu', t['mtu'])
        if awg:
            for k, opt in AWG_UCI.items():
                if t.get('amnezia_' + k, '') != '':
                    N(f'rl_awg.{opt}', t['amnezia_' + k])
        N('rl_awg_peer', f'{proto}_rl_awg'); N('rl_awg_peer.description', p['name']); N('rl_awg_peer.public_key', pr['public_key'])
        if pr.get('pre_shared_key'):
            N('rl_awg_peer.preshared_key', pr['pre_shared_key'])
        N('rl_awg_peer.endpoint_host', pr['address']); N('rl_awg_peer.endpoint_port', pr['port'])
        NA('rl_awg_peer.allowed_ips', '0.0.0.0/0'); N('rl_awg_peer.route_allowed_ips', '0')
        N('rl_awg_peer.persistent_keepalive', pr.get('persistent_keepalive_interval') or '25')
        L.append(r"""Z=$(uci -q show firewall | sed -n "s/^firewall\.\([^.]*\)\.name='wan'$/\1/p" | head -1)
if [ -n "$Z" ]; then N=$(uci -q get firewall.$Z.network); case " $N " in *" rl_awg "*) ;; *) uci -q delete firewall.$Z.network; for x in $N rl_awg; do uci add_list firewall.$Z.network=$x; done;; esac; fi
uci commit network; uci commit firewall; /etc/init.d/network reload; /etc/init.d/firewall reload >/dev/null 2>&1; sleep 3; ifup rl_awg; sleep 3""")
    _delete(e, L, replace_all)
    S = lambda path, v: L.append(f'uci set podkop.{path}={q(str(v))}')
    A = lambda path, v: L.append(f'uci add_list podkop.{path}={q(str(v))}')
    if mode == 'split':
        S('rl_ru', 'section'); S('rl_ru.connection_type', 'exclusion'); A('rl_ru.community_lists', RU_SERVICES); S('rl_ru.rl_managed', '1')
        S('rl_ru.user_domain_list_type', 'dynamic')
        for d in RU_SUFFIX:
            A('rl_ru.user_domains', d)
    S('main', 'section'); S('main.rl_managed', '1')
    if tun:
        S('main.connection_type', 'vpn'); S('main.interface', 'rl_awg')
    else:
        links = p['links']
        S('main.connection_type', 'proxy')
        if len(links) == 1:
            S('main.proxy_config_type', 'url'); S('main.proxy_string', links[0]['uri'])
        elif auto:
            S('main.proxy_config_type', 'urltest'); S('main.urltest_check_interval', '3m'); S('main.urltest_tolerance', '50')
            for l in links:
                A('main.urltest_proxy_links', l['uri'])
        else:
            S('main.proxy_config_type', 'selector')
            for l in links:
                A('main.selector_proxy_links', l['uri'])
    if mode == 'split':
        L.append('uci add_list podkop.main.fully_routed_ips="$NET"')
    else:
        for x in lists:
            A('main.community_lists', x)
        if domains:
            S('main.user_domain_list_type', 'dynamic')
            for d in domains:
                A('main.user_domains', d)
    if mode == 'split':
        L.append('uci reorder podkop.rl_ru=1')
    L.append('uci reorder podkop.main=%d' % (2 if mode == 'split' else 1))
    _tail(e, L, ('network', 'firewall') if tun else ())
    return '\n'.join(L) + '\n'
