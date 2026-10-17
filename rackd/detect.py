"""«Определить автоматически»: what kind of device answers at this address.

Every probe is quick and harmless (no login, no changes): HTTP fingerprints, SNMP sysDescr with «public»,
telnet / SSH greetings. The result is a ranked list of driver suggestions with a human explanation.
"""
import concurrent.futures, json, re, socket, ssl, urllib.error, urllib.request

from .snmp import Snmp, SnmpError, text

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def _http(url, data=None, timeout=3):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'RackLive-detect'})
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=CTX)
    except urllib.error.HTTPError as e:
        r = e
    body = r.read(65536).decode('utf-8', 'replace')
    return r.status if hasattr(r, 'status') else r.code, dict(r.headers), body


def _banner(host, port, timeout=3, send=None):
    try:
        with socket.create_connection((host, port), timeout) as s:
            s.settimeout(timeout)
            if send:
                s.sendall(send)
            data = b''
            try:
                while len(data) < 2048:
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                    if b'\n' in data and port == 22:
                        break
            except socket.timeout:
                pass
            return re.sub(rb'\xff[\xfb-\xfe].', b'', data).decode('utf-8', 'replace')     # drop telnet negotiation
    except OSError:
        return None


def p_keenetic(host):
    for base in (f'http://{host}', f'https://{host}'):
        try:
            code, h, _ = _http(base + '/auth')
        except Exception:
            continue
        realm = h.get('X-NDM-Realm') or h.get('x-ndm-realm')
        if realm:
            return {'driver': 'keenetic', 'score': 100, 'what': f'Keenetic / Netcraze ({realm})', 'host': host if base.startswith('http:') else base}


def p_openwrt(host):
    try:
        code, _, body = _http(f'http://{host}/ubus', {'jsonrpc': '2.0', 'id': 1, 'method': 'call',
                                                      'params': ['0' * 32, 'session', 'access', {}]})
        try:
            j = json.loads(body)
        except ValueError:
            j = None
        # a real ubus answers {"jsonrpc":"2.0","id":1,"result":[…]}; a camera / «answers 200 to everything» device that echoes the request (it has "method") is not OpenWrt
        if isinstance(j, dict) and j.get('jsonrpc') == '2.0' and 'method' not in j and ('result' in j or 'error' in j):
            return {'driver': 'openwrt', 'score': 95, 'what': 'OpenWrt (ubus)'}
    except Exception:
        pass
    try:
        code, _, body = _http(f'http://{host}/cgi-bin/luci/')
        if 'luci-static' in body or ('LuCI' in body and 'openwrt' in body.lower()):
            return {'driver': 'openwrt', 'score': 80, 'what': 'OpenWrt (LuCI)'}
    except Exception:
        pass


def p_synology(host):
    for base in (f'http://{host}:5000', f'https://{host}:5001'):
        try:
            code, _, body = _http(base + '/webapi/query.cgi?api=SYNO.API.Info&version=1&method=query&query=SYNO.API.Auth')
        except Exception:
            continue
        if '"success"' in body and 'SYNO.API.Auth' in body:
            return {'driver': 'synology', 'score': 100, 'what': 'Synology DSM'}


def p_homeassistant(host):
    try:
        code, _, body = _http(f'http://{host}:8123/manifest.json')
        if 'Home Assistant' in body:
            return {'driver': 'homeassistant', 'score': 100, 'what': 'Home Assistant', 'host': f'http://{host}:8123'}
    except Exception:
        pass


def p_snmp(host):
    try:
        d = text(Snmp(host, 'public', timeout=1.5, retries=0).get('1.3.6.1.2.1.1.1.0').get('1.3.6.1.2.1.1.1.0'))
    except (SnmpError, OSError):
        return None
    if not d:
        return None
    if re.search(r'jetstream|t2600|t1600|tl-sg3', d, re.I):
        return {'driver': 'tplink_jetstream', 'score': 90, 'what': f'TP-Link JetStream: {d[:80]}'}
    return {'driver': 'snmp', 'score': 70, 'what': f'SNMP: {d[:80]}'}


def p_telnet(host):
    b = _banner(host, 23, 3)
    if b is None:
        return None
    if re.search(r'tp-?link|jetstream|user ?name:|user:', b, re.I):
        return {'driver': 'tplink_jetstream', 'score': 60 if 'tp' not in b.lower() else 85,
                'what': 'Управляемый коммутатор с telnet' + (' (TP-Link)' if 'tp' in b.lower() else ' — похоже на TP-Link JetStream')}


def p_ssh(host):
    b = _banner(host, 22, 3)
    if b and b.startswith('SSH-'):
        sw = b.strip().split('\n')[0][:60]
        if 'IPSSH' in sw:                                    # TP-Link switches greet with «SSH-1.99-IPSSH-…»
            return {'driver': 'tplink_jetstream', 'score': 85, 'what': f'TP-Link JetStream (SSH {sw})'}
        if 'for_windows' in sw.lower():                      # «SSH-2.0-OpenSSH_for_Windows_9.5»: the built-in OpenSSH server of Windows
            return {'driver': 'windows', 'score': 88, 'kind': 'pc', 'username': 'Administrator',
                    'what': f'Компьютер / сервер Windows с включённым SSH ({sw}): нагрузка, память, диски и их состояние'}
        return {'driver': 'ssh', 'score': 40, 'what': f'Linux / сервер по SSH ({sw})'}


def p_nut(host):
    b = _banner(host, 3493, 2, send=b'VER\n')
    if b and 'upsd' in b.lower() or (b and 'Network UPS Tools' in b):
        return {'driver': 'ups', 'score': 80, 'what': 'ИБП через NUT', 'mode': 'nut'}


def p_http(host):
    for url in (f'http://{host}', f'https://{host}'):
        try:
            code, _, body = _http(url)
        except Exception:
            continue
        title = re.search(r'<title[^>]*>([^<]{1,80})', body, re.I)
        return {'driver': 'http', 'score': 15, 'what': f"Веб-сайт / веб-интерфейс{': ' + title.group(1).strip() if title else ''}", 'host': url}


def p_proxmox(host):
    try:
        code, _, body = _http(f'https://{host}:8006/')
    except Exception:
        return None
    if 'proxmox' in body.lower():
        return {'driver': 'proxmox', 'score': 92, 'what': 'Proxmox VE — виртуалки и контейнеры, хранилища, диски (вход логином Proxmox)',
                'kind': 'server', 'host': host, 'webUrl': f'https://{host}:8006'}


def _open(host, port, timeout=1.2):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def p_windows(host):
    rdp, smb = _open(host, 3389), _open(host, 445)
    if rdp or (smb and _open(host, 135)):
        return {'driver': 'ping', 'score': 30, 'kind': 'pc',
                'what': 'Компьютер с Windows (' + ', '.join(x for x, on in (('удалённый рабочий стол', rdp), ('общие папки', smb)) if on) + ') — пока можно следить за доступностью. '
                        'Чтобы видеть нагрузку, диски и их состояние, включите на компьютере встроенный OpenSSH-сервер — Rack Live предложит тип «Windows» сам',
                'alt': 'windows'}


PROBES = [p_keenetic, p_openwrt, p_synology, p_homeassistant, p_proxmox, p_snmp, p_telnet, p_ssh, p_nut, p_windows, p_http]


def _bases(hostport, url):
    return [url] if url else [f'https://{hostport}', f'http://{hostport}']


def p_keenetic_remote(hostport, url):
    """A Keenetic somewhere else (KeenDNS domain, white IP:port): manageable when it answers RCI directly."""
    for base in _bases(hostport, url):
        try:
            code, h, _ = _http(base + '/auth', timeout=5)
        except Exception:
            continue
        realm = h.get('X-NDM-Realm') or h.get('x-ndm-realm')
        if realm:
            return {'driver': 'keenetic', 'score': 101, 'what': f'Keenetic / Netcraze ({realm}) — можно управлять удалённо', 'host': base}


def p_remote_web(hostport, url):
    """Anything with a web panel outside the home network: at least a link and the login in the card."""
    for base in _bases(hostport, url):
        try:
            code, _, body = _http(base, timeout=5)
        except Exception:
            continue
        title = re.search(r'<title[^>]*>([^<]{1,80})', body, re.I)
        return {'driver': 'remote_web', 'score': 50, 'host': base,
                'what': f"Веб-панель{': ' + title.group(1).strip() if title else ''} — ссылка, логин и пароль в карточке (без управления)"}


def _private(host):
    try:
        import ipaddress
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host.endswith('.local') or '.' not in host


def detect(host):
    raw = (host or '').strip()
    url = raw.rstrip('/') if re.match(r'^https?://', raw) else None
    hostport = re.sub(r'^\w+://', '', raw).split('/')[0]
    if not hostport:
        return []
    bare = hostport.split(':')[0]
    remote = bool(url) or ':' in hostport or not _private(bare)
    jobs = [lambda p=p: p(bare) for p in PROBES]
    if remote:                                       # an address outside: probe exactly what was typed (scheme, port)
        jobs += [lambda: p_keenetic_remote(hostport, url), lambda: p_remote_web(hostport, url)]
    with concurrent.futures.ThreadPoolExecutor(len(jobs)) as pool:
        results = [r for r in pool.map(lambda j: _safe(j), jobs) if r]
    out, seen = [], set()
    for r in sorted(results, key=lambda r: -r['score']):
        if r['driver'] in seen:
            continue
        seen.add(r['driver'])
        out.append(dict({'host': bare}, **r))
    if out and out[0]['score'] >= 85:              # a sure match: the generic guesses only add noise
        out = [r for r in out if r['score'] >= 60 or r['driver'] == 'remote_web']     # remote: the link-only option stays (cloud KeenDNS)
    out.append({'driver': 'ping', 'score': 1, 'what': 'Только доступность (ping) — если ничего не подошло', 'host': bare})
    return out


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None
