"""Internet speed on a schedule: from Rack Live itself (Ookla CLI, Cloudflare as a fallback), through each channel
of a Keenetic router (Entware + curl bound to the tunnel interface), and from SSH servers. History for 30 days.
"""
import copy, json, os, random, shutil, subprocess, threading, time, urllib.request

DEFAULT = {'enabled': True, 'hours': 4, 'tariff': 0, 'server': 'auto', 'channels': {}, 'servers': []}
KEEP_DAYS = 30
CF_DOWN, CF_UP = 'https://speed.cloudflare.com/__down?bytes=', 'https://speed.cloudflare.com/__up'
UA = {'User-Agent': 'Mozilla/5.0 (RackLive speed test)'}         # Cloudflare answers 403 to Python's default agent

# On a router / server: Speedtest CLI by Ookla if it can be had for this CPU (downloaded once into $BIN),
# bound to the channel with «-I <iface>»; otherwise 4 parallel curl streams to Cloudflare for 10 s each way.
# Cloudflare serves at most 50 MB per request → each stream loops. IFACE is «nwg1» or empty; BIN is where to keep speedtest.
CURL_TEST = r'''B=/tmp/rl-inet; rm -rf $B; mkdir -p $B
ST=""; for p in "$BIN/speedtest" /usr/local/bin/speedtest /usr/bin/speedtest; do [ -x "$p" ] && ST="$p" && break; done
if [ -z "$ST" ] && [ -n "$BIN" ] && command -v curl >/dev/null 2>&1; then
  case "$(uname -m)" in x86_64) a=x86_64;; aarch64) a=aarch64;; armv7l) a=armhf;; *) a="";; esac
  if [ -n "$a" ] && [ -z "$(find "$BIN/.rl-no-ookla" -mtime -7 2>/dev/null)" ]; then        # a failed download is not retried for a week
    mkdir -p "$BIN"
    curl -fsSL -m 20 "https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-$a.tgz" | tar xz -C "$BIN" speedtest 2>/dev/null
    if [ -x "$BIN/speedtest" ]; then ST="$BIN/speedtest"; else touch "$BIN/.rl-no-ookla"; fi
  fi
fi
if [ -n "$ST" ] && [ "$SERVER" != cloudflare ]; then             # Ookla blocked (e.g. in Russia) → fall through to Cloudflare
  J=$($ST --accept-license --accept-gdpr -f json ${IFACE:+-I $IFACE} 2>/dev/null | tail -1)
  case "$J" in *'"type":"result"'*) echo "@@ookla $J"; rm -rf $B; exit 0;; esac
  echo "@@note Speedtest (Ookla) недоступен — замер через Cloudflare"
fi
command -v curl >/dev/null 2>&1 || { echo "@@fail нет ни Speedtest, ни curl"; exit 0; }
CI=""; [ -n "$IFACE" ] && CI="--interface $IFACE"
P=""; for k in 1 2 3; do t=$(curl -s $CI -m 5 -o /dev/null -w '%{time_pretransfer} %{time_starttransfer}' 'https://speed.cloudflare.com/__down?bytes=0'); P="$P $t"; done
END=$(( $(date +%s) + 10 ))
dl() { S=0; while [ $(date +%s) -lt $END ]; do L=$((END - $(date +%s))); [ $L -lt 1 ] && break
  n=$(curl -s $CI -m $L -o /dev/null -w '%{size_download}' 'https://speed.cloudflare.com/__down?bytes=50000000'); S=$((S + ${n%%.*})); done; echo $S > $B/d$1; }
for k in 1 2 3 4; do dl $k & done; wait
END=$(( $(date +%s) + 10 ))
ul() { S=0; while [ $(date +%s) -lt $END ]; do L=$((END - $(date +%s))); [ $L -lt 1 ] && break
  n=$(head -c 50000000 /dev/zero | curl -s $CI -m $L -T - -X POST -o /dev/null -w '%{size_upload}' 'https://speed.cloudflare.com/__up'); S=$((S + ${n%%.*})); done; echo $S > $B/u$1; }
for k in 1 2 3 4; do ul $k & done; wait
D=0; U=0; for k in 1 2 3 4; do D=$((D + $(cat $B/d$k 2>/dev/null || echo 0))); U=$((U + $(cat $B/u$k 2>/dev/null || echo 0))); done
T=$(curl -s $CI -m 6 https://speed.cloudflare.com/cdn-cgi/trace | grep -E '^(ip|colo|loc)=' | tr '\n' ' ')
echo "@@r $D $U $P"; echo "@@trace $T"; rm -rf $B
'''


def parse_ookla(line):
    """Speedtest CLI JSON (the last line of its output) → result dict."""
    try:
        j = json.loads(line)
    except ValueError:
        return {'error': (line or 'speedtest не ответил').strip()[:160]}
    if j.get('type') != 'result':
        return {'error': str(j.get('message') or j.get('error') or 'speedtest: ошибка')[:160]}
    s = j.get('server') or {}
    return {'down': round(j['download']['bandwidth'] * 8 / 1e6, 1), 'up': round(j['upload']['bandwidth'] * 8 / 1e6, 1),
            'ping': round((j.get('ping') or {}).get('latency') or 0, 1), 'jitter': round((j.get('ping') or {}).get('jitter') or 0, 1),
            'server': f"{s.get('name', '')}, {s.get('location', '')}".strip(', '), 'isp': j.get('isp'),
            'ip': (j.get('interface') or {}).get('externalIp'), 'url': (j.get('result') or {}).get('url')}


def parse_curl(out, seconds=10):
    """Ookla JSON («@@ookla …») or «@@r <down bytes> <up bytes> <pre start …>» from Cloudflare → Mbit/s and ping (ms)."""
    ok = next((l[8:] for l in out.splitlines() if l.startswith('@@ookla ')), None)
    if ok is not None:
        return parse_ookla(ok.strip() or '{}')
    r = next((l.split()[1:] for l in out.splitlines() if l.startswith('@@r ')), None)
    if not r:
        fail = next((l[7:] for l in out.splitlines() if l.startswith('@@fail ')), 'замер не удался')
        return {'error': fail}
    down, up = int(r[0]), int(r[1])
    pairs = [(float(r[i]), float(r[i + 1])) for i in range(2, len(r) - 1, 2)]
    pings = [max(0.0, b - a) * 1000 for a, b in pairs if b > 0]
    tr = dict(x.split('=', 1) for x in next((l[8:] for l in out.splitlines() if l.startswith('@@trace ')), '').split() if '=' in x)
    if not down:
        return {'error': 'нет связи через этот канал'}
    note = next((l[7:].strip() for l in out.splitlines() if l.startswith('@@note ')), None)
    return {'down': round(down * 8 / seconds / 1e6, 1), 'up': round(up * 8 / seconds / 1e6, 1), 'ping': round(min(pings), 1) if pings else None,
            'ip': tr.get('ip'), 'server': f"Cloudflare {tr.get('colo', '')}".strip(), 'loc': tr.get('loc'), **({'note': note} if note else {})}


def measure_ookla():
    exe = shutil.which('speedtest')
    if not exe:
        return None
    r = subprocess.run([exe, '--accept-license', '--accept-gdpr', '-f', 'json'], capture_output=True, text=True, timeout=120)
    lines = (r.stdout or '').strip().splitlines()
    return parse_ookla(lines[-1] if lines else (r.stderr or ''))


def measure_cloudflare(seconds=8, streams=4):
    """The same 4-stream test in pure Python (no curl, no Ookla)."""
    def ping():
        t = time.time()
        urllib.request.urlopen(urllib.request.Request(CF_DOWN + '0', headers=UA), timeout=5).read()
        return (time.time() - t) * 1000
    try:
        ping()
        pings = sorted(ping() for _ in range(4))
    except Exception as e:
        return {'error': f'Cloudflare недоступен: {e}'}
    def run(fn):
        total, stop, lock = [0], time.time() + seconds, threading.Lock()
        def worker():
            while time.time() < stop:
                try:
                    n = fn(stop)
                except Exception:
                    break
                with lock:
                    total[0] += n
        th = [threading.Thread(target=worker, daemon=True) for _ in range(streams)]
        [t.start() for t in th]
        [t.join(seconds + 15) for t in th]
        return total[0]
    def down(stop):
        n, r = 0, urllib.request.urlopen(urllib.request.Request(CF_DOWN + str(50_000_000), headers=UA), timeout=10)
        while time.time() < stop:
            b = r.read(1 << 16)
            if not b:
                break
            n += len(b)
        return n
    chunk = b'\0' * (4 << 20)
    def up(stop):
        urllib.request.urlopen(urllib.request.Request(CF_UP, data=chunk, method='POST', headers=UA), timeout=15).read()
        return len(chunk)
    d, u = run(down), run(up)
    return {'down': round(d * 8 / seconds / 1e6, 1), 'up': round(u * 8 / seconds / 1e6, 1), 'ping': round(pings[1], 1), 'server': 'Cloudflare'}


class InetSpeed:
    def __init__(self, app):
        self.app, self.store = app, app.store
        self.items = self.store._load('inetspeed.json', [])
        self.lock, self.running, self.last_run = threading.Lock(), False, max([x['t'] for x in self.items] or [0])

    def cfg(self):
        c = copy.deepcopy(DEFAULT)
        c.update(self.store.cfg.get('inet') or {})
        return c

    def due(self):
        c = self.cfg()
        return c['enabled'] and not self.running and time.time() - self.last_run >= max(1, float(c['hours'] or 4)) * 3600

    def start(self):
        if self.running:
            return False
        self.running = True
        self.store.bump()
        threading.Thread(target=self.run_all, daemon=True).start()
        return True

    def _add(self, rec):
        with self.lock:
            self.items.append(dict(rec, t=int(time.time())))
            cut = time.time() - KEEP_DAYS * 86400
            self.items = [x for x in self.items if x['t'] >= cut]
            self.store._dump('inetspeed.json', self.items)
            self.store.bump()

    def run_all(self):
        from .drivers import REGISTRY
        try:
            c = self.cfg()
            if os.environ.get('RL_DEMO', '').lower() in ('1', 'true', 'yes'):        # demo: no real traffic
                res = {'down': round(random.uniform(870, 940), 1), 'up': round(random.uniform(400, 460), 1), 'ping': 4.1, 'server': 'Ростелеком, Москва (демо)'}
            else:
                res = measure_ookla() if c['server'] in ('auto', 'ookla') else None
                if not res or res.get('error'):                         # Ookla is blocked in some countries (Russia)
                    res = dict(measure_cloudflare(), **({'note': 'Speedtest (Ookla) недоступен — замер через Cloudflare'} if res else {}))
            self._add(dict(res, source='racklive', label='Rack Live (основной канал)'))
            devs = {d['id']: d for d in self.store.cfg['devices']}
            for did, ifaces in (c.get('channels') or {}).items():
                d = devs.get(did)
                drv = REGISTRY.get((d or {}).get('driver'))
                if not d or not hasattr(drv, 'inet_test'):
                    continue
                vpn = {t['id']: t['name'] for t in (self.app.states.get(did) or {}).get('vpn') or []}
                for iface in ifaces:
                    try:
                        r = drv.inet_test(d, iface)
                    except Exception as e:
                        r = {'error': str(e)}
                    self._add(dict(r, source=f'{did}:{iface}', label=f"{d.get('name')} · {'провайдер' if iface == 'isp' else vpn.get(iface, iface)}"))
            for did in c.get('servers') or []:
                d = devs.get(did)
                drv = REGISTRY.get((d or {}).get('driver'))
                if not d or not hasattr(drv, 'inet_test'):
                    continue
                try:
                    r = drv.inet_test(d, None)
                except Exception as e:
                    r = {'error': str(e)}
                self._add(dict(r, source=did, label=d.get('name')))
        finally:
            self.last_run, self.running = time.time(), False
            self.store.bump()

    def public(self):
        c = self.cfg()
        return {'cfg': c, 'running': self.running, 'items': self.items[-600:], 'ookla': bool(shutil.which('speedtest')),
                'next': (self.last_run + float(c['hours'] or 4) * 3600) if c['enabled'] else None}

    def slow(self):
        """Main channel below the alert threshold on the last two runs → (down, tariff) else None."""
        c = self.cfg()
        tariff = float(c.get('tariff') or 0)
        pct = float(((self.store.cfg.get('notify') or {}).get('rules') or {}).get('inet', {}).get('pct') or 50)
        main = [x for x in self.items if x.get('source') == 'racklive' and x.get('down') is not None][-2:]
        if tariff and len(main) == 2 and all(x['down'] < tariff * pct / 100 for x in main):
            return main[-1]['down'], tariff
        return None
