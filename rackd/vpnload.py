"""VPN clients of a VPS and how many more it can take (the «Клиенты VPN» block of a device, a widget).

Every 5 minutes a read-only shell script (nothing is changed on the server, no secrets leave it) is run over SSH. It reports:
  · the clients of every VPN it can recognise — 3x-ui (its database), Remnawave (its database), AmneziaWG / WireGuard (the peers and their last handshake,
    on the host and inside Docker), and for everything else (xray, sing-box, hysteria, OpenVPN, Shadowsocks, Trojan …) the distinct addresses connected to the ports
    that those daemons listen on;
  · counters of CPU, network and memory.
From the history of the counters («how much each connected client costs») and the limits typed by the owner (channel, monthly traffic, safe load)
the module estimates how many more clients the server will take: the most limiting resource wins. A «main VPN server» adds up its nodes.
d['vpn'] = {on, main, mbps, quotaTb, quotaMode 'out'|'sum', margin %}
"""
import calendar, datetime, re, threading, time

EVERY = 300                       # seconds between scans
KEEP = 14 * 86400                 # history kept
DAEMONS = 'xray|sing-box|hysteria|hysteria2|tuic-server|ssserver|ss-server|ss-rust|trojan|trojan-go|openvpn|v2ray|ocserv|naive'

SCRIPT = r'''
echo "@@t $(date +%s)"
echo "@@id $(id -u)"
awk '/^cpu /{t=0; for(i=2;i<=9;i++)t+=$i; print "@@cpu", t-$5-$6, t; exit}' /proc/stat
echo "@@nproc $(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)"
awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print "@@mem", t, a}' /proc/meminfo
IF=$(ip -4 route show default 2>/dev/null | awk '{for(i=1;i<NF;i++)if($i=="dev"){print $(i+1);exit}}')
[ -n "$IF" ] || IF=$(awk -F'[: ]+' 'NR>2 && $2!="lo"{print $2; exit}' /proc/net/dev)
[ -r "/sys/class/net/$IF/statistics/rx_bytes" ] && echo "@@net $IF $(cat /sys/class/net/$IF/statistics/rx_bytes) $(cat /sys/class/net/$IF/statistics/tx_bytes)"
if [ -f /etc/x-ui/x-ui.db ] && command -v python3 >/dev/null 2>&1; then
python3 - <<'PY' 2>/dev/null
import sqlite3, json, time
c = sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True, timeout=3)
clients = enabled = 0
for en, st in c.execute('select enable, settings from inbounds'):
    try:
        for x in (json.loads(st).get('clients') or []):
            clients += 1
            if en and x.get('enable', True):
                enabled += 1
    except Exception:
        pass
online = ''
if 'last_online' in [r[1] for r in c.execute('pragma table_info(client_traffics)')]:
    online = c.execute('select count(*) from client_traffics where enable=1 and last_online>?', (int(time.time() * 1000) - 180000,)).fetchone()[0]
print('@@xui', clients, enabled, online)
PY
fi
if command -v docker >/dev/null 2>&1; then
  RW=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -Ei 'remnawave.*(db|postgres)' | head -1)
  if [ -n "$RW" ]; then
    echo "@@rwc $RW"
    docker exec "$RW" psql -U postgres -d postgres -tA -F ' ' -c "select count(*), count(*) filter (where status='ACTIVE') from users" 2>/dev/null </dev/null | head -1 | sed 's/^/@@rw /'
  fi
fi
wgdump() { awk -v s="$1" 'NF==9 && $6 ~ /^[0-9]+$/ {print "@@wg", s, $1, $6}'; }
if command -v docker >/dev/null 2>&1; then
  for C in $(docker ps --format '{{.Names}}' 2>/dev/null | grep -Ei 'awg|amnezia|wireguard|wg-|wg$'); do
    { docker exec "$C" awg show all dump 2>/dev/null || docker exec "$C" wg show all dump 2>/dev/null; } </dev/null | wgdump "$C"
  done
fi
for B in awg wg; do command -v $B >/dev/null 2>&1 && $B show all dump 2>/dev/null </dev/null | wgdump "host-$B"; done
if command -v ss >/dev/null 2>&1; then
  T1=$(mktemp 2>/dev/null || echo /tmp/rl_vpn1.$$); T2=$(mktemp 2>/dev/null || echo /tmp/rl_vpn2.$$)
  ss -Htlnp > "$T1" 2>/dev/null; ss -Htnp state established > "$T2" 2>/dev/null
  [ -s "$T1" ] && awk -v names='@DAEMONS@' '
function pname(s) { if (match(s, /\(\("[^"]+"/)) return substr(s, RSTART + 3, RLENGTH - 4); return "" }
function lport(s,  a, n) { n = split(s, a, ":"); return a[n] }
FNR == NR { n = pname($0); if (n != "" && n ~ ("^(" names ")$")) { lp[n SUBSEP lport($3)] = 1; ln[n] = 1 } next }
{ n = pname($0); if (n == "" || !((n SUBSEP lport($3)) in lp)) next; ip = $4; sub(/:[0-9]+$/, "", ip); gsub(/[][]/, "", ip)
  if (ip == "127.0.0.1" || ip == "::1") next; seen[n SUBSEP ip] = 1 }
END { for (k in seen) { split(k, x, SUBSEP); c[x[1]]++ } for (n in ln) print "@@gen", n, c[n] + 0 }' "$T1" "$T2"
  rm -f "$T1" "$T2"
fi
echo @@end
'''.replace('@DAEMONS@', DAEMONS)


def _int(x, d=None):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return d


def parse(out):
    """The script's output → {t, cpu:[busy,total], nproc, mem:[total,avail] kB, net:[rx,tx], sources:[{id,label,clients,online}], panel}"""
    r = {'sources': [], 'panel': None, 'root': True}
    wg, gen, xui, rw = {}, {}, None, None
    for l in (out or '').splitlines():
        p = l.split()
        if not p or not p[0].startswith('@@'):
            continue
        k, a = p[0][2:], p[1:]
        if k == 't' and a:
            r['t'] = _int(a[0])
        elif k == 'id' and a:
            r['root'] = a[0] == '0'
        elif k == 'cpu' and len(a) == 2:
            r['cpu'] = [_int(a[0], 0), _int(a[1], 0)]
        elif k == 'nproc' and a:
            r['nproc'] = max(1, _int(a[0], 1))
        elif k == 'mem' and len(a) == 2:
            r['mem'] = [_int(a[0], 0), _int(a[1], 0)]
        elif k == 'net' and len(a) == 3:
            r['net'] = [_int(a[1], 0), _int(a[2], 0)]
            r['iface'] = a[0]
        elif k == 'xui' and len(a) >= 2:
            xui = {'clients': _int(a[0], 0), 'enabled': _int(a[1], 0), 'online': _int(a[2]) if len(a) > 2 else None}
        elif k == 'rwc':
            r['panel'] = 'Remnawave'
        elif k == 'rw' and len(a) >= 2:
            rw = {'clients': _int(a[0], 0), 'enabled': _int(a[1], 0)}
        elif k == 'wg' and len(a) >= 3:                      # @@wg <where> <interface> <last handshake>
            src = wg.setdefault(a[0], {'n': 0, 'on': 0})
            src['n'] += 1
            hs = _int(a[2], 0)
            if hs and (r.get('t') or time.time()) - hs <= 180:
                src['on'] += 1
        elif k == 'gen' and len(a) >= 2:
            gen[a[0]] = _int(a[1], 0)
    covered_xray = False
    if xui:
        r['panel'] = '3x-ui'
        covered_xray = True
        gx = gen.get('xray')
        online = xui['online'] if xui['online'] is not None else gx
        r['sources'].append({'id': '3xui', 'label': '3x-ui', 'clients': xui['enabled'], 'online': online,
                             'how': 'по базе панели' if xui['online'] is not None else 'по соединениям xray'})
    if rw:
        covered_xray = True
        r['sources'].append({'id': 'remnawave', 'label': 'Remnawave', 'clients': rw['enabled'], 'online': gen.get('xray'), 'how': 'пользователи — из базы панели, онлайн — по соединениям xray'})
    elif r['panel'] == 'Remnawave':
        covered_xray = True
        r['sources'].append({'id': 'remnawave', 'label': 'Remnawave', 'clients': None, 'online': gen.get('xray'), 'how': 'по соединениям xray (базу панели прочитать не удалось)'})
    for name, s in sorted(wg.items()):
        label = 'AmneziaWG' if re.search(r'awg|amnezia', name, re.I) or name == 'host-awg' else 'WireGuard'
        r['sources'].append({'id': 'wg:' + name, 'label': label + (f' ({name})' if not name.startswith('host-') else ''), 'clients': s['n'], 'online': s['on'], 'how': 'пиры и последнее рукопожатие'})
    for name, n in sorted(gen.items()):
        if name == 'xray' and covered_xray:
            continue
        r['sources'].append({'id': 'gen:' + name, 'label': name, 'clients': None, 'online': n, 'how': 'по соединениям на порты службы'})
    return r


def sample_of(p):
    """One history row: [t, busy, total, rx, tx, online, clients, mem%] — online / clients None when nothing was recognised."""
    srcs = p['sources']
    on = [s['online'] for s in srcs if s.get('online') is not None]
    cl = [s['clients'] for s in srcs if s.get('clients') is not None]
    mem = p.get('mem') or [0, 0]
    return [p.get('t') or int(time.time()), (p.get('cpu') or [0, 0])[0], (p.get('cpu') or [0, 0])[1], (p.get('net') or [0, 0])[0], (p.get('net') or [0, 0])[1],
            sum(on) if on else None, sum(cl) if cl else None, round(100 * (1 - mem[1] / mem[0]), 1) if mem[0] else None]


def _pct(v, q):
    v = sorted(v)
    if not v:
        return None
    i = (len(v) - 1) * q
    lo = int(i)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (i - lo)


def analyze(rows, conf, now=None):
    """History rows + the owner's limits → what the server carries and how many more clients it takes."""
    now = now or time.time()
    conf = conf or {}
    rows = [r for r in rows if now - r[0] <= KEEP]
    res = {'at': rows[-1][0] if rows else None, 'detected': False, 'clients': None, 'online': None, 'days': 0, 'confidence': 'low',
           'cpu': None, 'net': None, 'quota': None, 'mem': rows[-1][7] if rows else None, 'k': None, 'bottleneck': None, 'users': None, 'notes': []}
    if not rows:
        return res
    last = rows[-1]
    res['detected'] = any(r[5] is not None for r in rows[-3:])
    res['online'], res['clients'] = last[5], last[6]
    iv = []                                                 # intervals between two samples: dt, cpu %, rx / tx bits per second, online
    for a, b in zip(rows, rows[1:]):
        dt = b[0] - a[0]
        dB, dT, dr, dx = b[1] - a[1], b[2] - a[2], b[3] - a[3], b[4] - a[4]
        if not (60 <= dt <= 1800) or dT <= 0 or dB < 0 or dr < 0 or dx < 0 or b[5] is None:
            continue                                        # a gap or a reboot: the counters restarted
        iv.append({'dt': dt, 't': b[0], 'cpu': 100 * dB / dT, 'rx': dr * 8 / dt, 'tx': dx * 8 / dt, 'on': b[5], 'rxB': dr, 'txB': dx})
    res['days'] = round(sum(i['dt'] for i in iv) / 86400, 1)
    if not res['detected']:
        res['notes'].append('Не нашёл VPN на этом сервере: искал 3x-ui, Remnawave, AmneziaWG и WireGuard, а также xray, sing-box, hysteria, OpenVPN, Shadowsocks и Trojan.')
        return res
    if len(iv) < 12:
        res['notes'].append('Данных пока мало: оценка запаса появится после нескольких часов наблюдения.')
        return res
    margin = min(95, max(30, _int(conf.get('margin'), 75)))
    res['margin'] = margin
    res['confidence'] = 'good' if res['days'] >= 7 and max(i['on'] for i in iv) >= 5 else 'mid' if res['days'] >= 2 else 'low'
    active = [i for i in iv if i['on'] >= 1]
    multi = [i for i in iv if i['on'] >= 2] or active
    avg_on = sum(i['on'] for i in iv) / len(iv)
    peak_on = _pct([i['on'] for i in iv], .95) or 0
    res['peakOnline'] = round(peak_on)
    ks = {}
    # processor: the load above the idle baseline, per connected client
    cpus = [i['cpu'] for i in iv]
    cp95 = _pct(cpus, .95)
    cpu_limit = margin
    ons = [i['on'] for i in iv]
    mx, my = sum(ons) / len(iv), sum(cpus) / len(iv)
    sxx = sum((o - mx) ** 2 for o in ons)
    if max(ons) - min(ons) >= 3 and sxx > 0:                # the processor cost of one more client = the slope of «load against clients» (the idle baseline drops out)
        per = max(0, sum((o - mx) * (c - my) for o, c in zip(ons, cpus)) / sxx)
    else:                                                   # clients hardly change: assume an idle baseline of at most 2 % (a cautious guess)
        per = max(0, (my - min(_pct(cpus, .1), 2.0)) / max(1, mx))
    res['cpu'] = {'p95': round(cp95, 1), 'limit': cpu_limit, 'perClient': round(per, 2) if per > 0.01 else None,
                  'k': max(0, int((cpu_limit - cp95) / per)) if per > 0.01 else None}
    if res['cpu']['k'] is not None:
        ks['cpu'] = res['cpu']['k']
    # channel: the busier direction against the typed speed
    mbps = _int(conf.get('mbps'), 0)
    if mbps > 0:
        bps = [max(i['rx'], i['tx']) for i in iv]
        p95 = _pct(bps, .95)
        qs = [max(i['rx'], i['tx']) / i['on'] for i in multi]
        pc = _pct(qs, .9) if qs else 0
        lim = mbps * 1e6 * margin / 100
        res['net'] = {'p95Mbps': round(p95 / 1e6, 1), 'limitMbps': round(lim / 1e6), 'capMbps': mbps, 'perClientMbps': round(pc / 1e6, 2) if pc else None,
                      'k': max(0, int((lim - p95) / pc)) if pc > 0 else None}
        if res['net']['k'] is not None:
            ks['net'] = res['net']['k']
    else:
        res['notes'].append('Укажите скорость канала сервера — тогда учту и его.')
    # monthly traffic quota: the daily rate of the last week against the limit
    q = float(conf.get('quotaTb') or 0)
    if q > 0:
        span = min(7, max(res['days'], .5))
        cut = now - span * 86400
        tot = sum((i['txB'] if conf.get('quotaMode') != 'sum' else i['txB'] + i['rxB']) for i in iv if i['t'] >= cut)
        month = tot / span * 30 / 1e12
        lim = q * margin / 100
        per_m = month / max(1, avg_on)
        res['quota'] = {'monthTb': round(month, 2), 'limitTb': round(lim, 2), 'capTb': q, 'perClientGb': round(per_m * 1000, 1), 'k': max(0, int((lim - month) / per_m)) if per_m > 0 else None}
        if res['quota']['k'] is not None:
            ks['quota'] = res['quota']['k']
    if ks:
        res['bottleneck'] = min(ks, key=ks.get)
        res['k'] = ks[res['bottleneck']]
        if res['clients'] and peak_on > 0:                  # how many new people that is, at the share of them who are online together
            res['users'] = int(res['k'] / max(.02, peak_on / res['clients']))
    elif not res['notes']:
        res['notes'].append('Нужны данные, пока к серверу подключены клиенты.')
    if res['confidence'] == 'low':
        res['notes'].append('Оценка пока грубая: наблюдаю меньше двух суток.')
    return res


def summary(devices, hist, now=None):
    """Per-device results and, for the one marked «главный сервер», the whole VPN: clients, online and the room left in all nodes together."""
    out, nodes = {}, []
    for d in devices:
        v = d.get('vpn')
        if not v or not v.get('on'):
            continue
        r = analyze((hist.get(d['id']) or {}).get('s') or [], v, now)
        r['main'] = bool(v.get('main'))
        r['name'] = d.get('name')
        r['sources'] = (hist.get(d['id']) or {}).get('src') or []
        r['panel'] = (hist.get(d['id']) or {}).get('panel')
        out[d['id']] = r
        nodes.append((d, r))
    system = None
    main = next(((d, r) for d, r in nodes if r['main']), None)
    if main:
        tot_cl = main[1]['clients'] if main[1].get('clients') else sum(r['clients'] or 0 for _, r in nodes) or None
        ks = [(r['name'], r['k'], r['bottleneck']) for _, r in nodes if r['k'] is not None]
        system = {'main': main[0]['id'], 'nodes': len(nodes), 'clients': tot_cl, 'online': sum(r['online'] or 0 for _, r in nodes if r['online'] is not None),
                  'k': sum(k for _, k, _ in ks) if ks else None, 'weakest': min(ks, key=lambda x: x[1]) if ks else None,
                  'unknown': [r['name'] for _, r in nodes if r['k'] is None]}
        peak = sum(r.get('peakOnline') or r['online'] or 0 for _, r in nodes)          # the share of people who are online together is taken at the busiest hours
        if system['k'] is not None and tot_cl and peak:
            system['users'] = int(system['k'] / max(.02, peak / tot_cl))
    return {'devices': out, 'system': system}


class Collector:
    """Runs the scans: every EVERY seconds for each device whose «vpn» switch is on; keeps the history in data/vpnload.json."""
    def __init__(self, store, registry):
        self.store, self.registry = store, registry
        self.hist = store._load('vpnload.json', {})
        self.next, self.busy, self.errors = {}, set(), {}
        self.lock = threading.Lock()

    def tick(self, devices):
        now = time.time()
        for d in devices:
            v = d.get('vpn')
            if not v or not v.get('on') or d.get('enabled') is False or d['id'] in self.busy or self.next.get(d['id'], 0) > now:
                continue
            self.next[d['id']] = now + EVERY
            self.busy.add(d['id'])
            threading.Thread(target=self._scan_safe, args=(d,), daemon=True).start()

    def _scan_safe(self, d):
        try:
            self.scan(d)
            self.errors.pop(d['id'], None)
        except Exception as e:
            self.errors[d['id']] = str(e)[:200]
        finally:
            self.busy.discard(d['id'])

    def scan(self, d, force=False):
        drv = self.registry.get(d.get('driver'))
        if not drv or not hasattr(drv, '_run'):
            raise ValueError('подсчёт VPN работает только для серверов по SSH')
        p = parse(drv._run(d, SCRIPT, timeout=45))
        if not p.get('cpu') or not p.get('net'):
            raise ValueError('сервер не вернул счётчики (нужен Linux)')
        row = sample_of(p)
        with self.lock:
            h = self.hist.setdefault(d['id'], {'s': []})
            if not h['s'] or row[0] - h['s'][-1][0] >= (60 if force else 240):
                h['s'].append(row)
            cut = time.time() - KEEP
            h['s'] = [r for r in h['s'] if r[0] >= cut]
            h['src'], h['panel'], h['root'] = p['sources'], p['panel'], p['root']
            self.store._dump('vpnload.json', self.hist)
        return p

    def forget(self, did):
        with self.lock:
            if self.hist.pop(did, None) is not None:
                self.store._dump('vpnload.json', self.hist)

    def summary(self, devices):
        with self.lock:
            res = summary(devices, self.hist)
        for did, r in res['devices'].items():
            if self.errors.get(did):
                r['error'] = self.errors[did]
        return res


def clean(new):
    n = new if isinstance(new, dict) else {}
    def num(x, lo, hi, d):
        try:
            return min(hi, max(lo, float(x)))
        except (TypeError, ValueError):
            return d
    return {'on': bool(n.get('on')), 'main': bool(n.get('main')) and bool(n.get('on')), 'mbps': int(num(n.get('mbps'), 0, 400000, 0)),
            'quotaTb': round(num(n.get('quotaTb'), 0, 100000, 0), 2), 'quotaMode': 'sum' if n.get('quotaMode') == 'sum' else 'out',
            'margin': int(num(n.get('margin'), 30, 95, 75))}
