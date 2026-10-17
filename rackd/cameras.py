"""Tool «Камеры и видеорегистраторы»: find IP cameras / recorders on the network, tell which is which, and manage them over ONVIF.

Search: only knocks (TCP connect + a harmless GET / and RTSP OPTIONS, ONVIF GetSystemDateAndTime which cameras answer without a login) — no login, nothing changes.
With a login (typed by the administrator for ONE device, never stored):
  · who it is (manufacturer, model, firmware), is it a camera or a recorder (number of video sources, the model name);
  · a picture (snapshot) and the RTSP address for VLC / Frigate / NVR;
  · the network: DHCP or a static address (+ gateway) — checked for a free address first;
  · users: change a password, create a user (ONVIF; Dahua also through its own HTTP API);
  · a camera that was never activated (Hikvision ISAPI): set the first password.
Only private addresses are ever touched. Passwords are used for one request and are not written anywhere (not to the journal either)."""
import base64, concurrent.futures, hashlib, html, ipaddress, os, re, socket, threading, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET

from . import camera_brands as brands, netscan

PORTS = (80, 443, 554, 2020, 8000, 8080, 8554, 8899, 37777, 34567)
ONVIF_PORTS = (80, 8080, 8000, 8899, 2020, 5000)
RECORDER_RE = re.compile(r'\b(NVR|DVR|XVR|HCVR|NVS|DS-7\d|DS-76|DS-77|DS-96|iDS-7|DHI-|HWN|HWD|XVR|TVR|NR\d|ER\d)', re.I)
NS = {'s': 'http://www.w3.org/2003/05/soap-envelope', 'tds': 'http://www.onvif.org/ver10/device/wsdl', 'tt': 'http://www.onvif.org/ver10/schema',
      'trt': 'http://www.onvif.org/ver10/media/wsdl'}


class CamError(Exception):
    pass


def esc(s):
    return html.escape(str(s), quote=True)


def private_ip(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.version == 4 and a.is_private and not a.is_loopback and not a.is_link_local and not a.is_multicast


def need_private(ip):
    if not private_ip(str(ip or '').strip()):
        raise CamError('нужен адрес из домашней сети (192.168.x.x, 10.x.x.x, 172.16–31.x.x)')
    return str(ip).strip()


# ───────── ONVIF (SOAP) ─────────
def _security(user, pw, skew):
    nonce = os.urandom(16)
    created = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + skew))
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + pw.encode()).digest()).decode()
    return ('<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            '<UsernameToken><Username>%s</Username><Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">%s</Password>'
            '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">%s</Nonce>'
            '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">%s</Created></UsernameToken></Security></s:Header>'
            % (esc(user), digest, base64.b64encode(nonce).decode(), created))


def soap(url, body, user='', pw='', skew=0, timeout=6):
    """one SOAP call → the <s:Body> element; an ONVIF fault becomes a readable CamError"""
    head = _security(user, pw, skew) if user else ''
    xml = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
           'xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:trt="http://www.onvif.org/ver10/media/wsdl">%s<s:Body>%s</s:Body></s:Envelope>' % (head, body))
    req = urllib.request.Request(url, xml.encode('utf-8'), {'Content-Type': 'application/soap+xml; charset=utf-8'})
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        if e.code in (401, 403) and b'Fault' not in raw:
            raise CamError('камера не пускает: неверный логин или пароль')
    except (urllib.error.URLError, OSError) as e:
        raise CamError('камера не отвечает (%s)' % (getattr(e, 'reason', e)))
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise CamError('камера ответила не по стандарту ONVIF')
    b = root.find('s:Body', NS)
    if b is None:
        b = next((e for e in root if e.tag.endswith('Body')), None)
    if b is None:
        raise CamError('камера ответила не по стандарту ONVIF')
    f = next((e for e in b if e.tag.endswith('Fault')), None)
    if f is not None:
        text = ' '.join(t.text or '' for t in f.iter() if t.tag.endswith('Text') or t.tag.endswith('Value')).lower()
        if 'notauthorized' in text.replace(' ', '') or 'sender not authorized' in text or 'authorized' in text and 'not' in text:
            raise CamError('камера не пускает: неверный логин или пароль (или у этого пользователя нет прав)')
        if 'action not implemented' in text or 'notsupported' in text.replace(' ', ''):
            raise CamError('эта камера не умеет такую команду по ONVIF')
        raise CamError('камера отказала: ' + (text.strip()[:140] or 'ошибка'))
    return b


def _t(el, path):
    x = el.find(path, NS) if el is not None else None
    return (x.text or '').strip() if x is not None and x.text else ''


def _tag(e):
    return e.tag.rsplit('}', 1)[-1]


class Onvif:
    """a camera / recorder by ONVIF at ip:port"""

    def __init__(self, ip, port, user='', pw=''):
        self.ip, self.port, self.user, self.pw = ip, port, user, pw
        self.url = 'http://%s:%s/onvif/device_service' % (ip, port)
        self.skew = 0
        self._media = None

    def sync_clock(self):
        """cameras refuse a login if their clock differs from ours: read their time first (that call needs no login)"""
        try:
            b = soap(self.url, '<tds:GetSystemDateAndTime/>', timeout=4)
            u = next((e for e in b.iter() if _tag(e) == 'UTCDateTime'), None)
            if u is not None:
                g = lambda n: int(next((x.text for x in u.iter() if _tag(x) == n), 0) or 0)
                import calendar
                t = calendar.timegm((g('Year'), g('Month'), g('Day'), g('Hour'), g('Minute'), g('Second'), 0, 0, 0))
                self.skew = t - time.time()
        except CamError:
            pass

    def call(self, body, url=None, timeout=7):
        return soap(url or self.url, body, self.user, self.pw, self.skew, timeout)

    def info(self):
        b = self.call('<tds:GetDeviceInformation/>')
        g = lambda n: next((e.text or '' for e in b.iter() if _tag(e) == n), '').strip()
        return {'manufacturer': g('Manufacturer'), 'model': g('Model'), 'firmware': g('FirmwareVersion'), 'serial': g('SerialNumber')}

    def media_url(self):
        if self._media:
            return self._media
        b = self.call('<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>')
        x = next((e.text for e in b.iter() if _tag(e) == 'XAddr' and e.text), '')
        self._media = self._fix(x) if x else 'http://%s:%s/onvif/media_service' % (self.ip, self.port)
        return self._media

    def _fix(self, url):
        """a camera may name its own internal address in links (behind NAT / another VLAN): talk to the one we reached it by"""
        m = re.match(r'^((?:https?|rtsp)://)(?:[^/@]*@)?([^/:]+)(:\d+)?(/.*)?$', url or '')
        if not m:
            return url
        return '%s%s%s%s' % (m.group(1), self.ip, m.group(3) or '', m.group(4) or '')

    def video_sources(self):
        b = self.call('<trt:GetVideoSources/>', self.media_url())
        return sum(1 for e in b.iter() if _tag(e) == 'VideoSources')

    def profiles(self):
        b = self.call('<trt:GetProfiles/>', self.media_url())
        return [e.get('token') for e in b.iter() if _tag(e) == 'Profiles' and e.get('token')]

    def stream_uri(self, token):
        b = self.call('<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>'
                      '<trt:ProfileToken>%s</trt:ProfileToken></trt:GetStreamUri>' % esc(token), self.media_url())
        return self._fix(next((e.text for e in b.iter() if _tag(e) == 'Uri' and e.text), ''))

    def snapshot_uri(self, token):
        b = self.call('<trt:GetSnapshotUri><trt:ProfileToken>%s</trt:ProfileToken></trt:GetSnapshotUri>' % esc(token), self.media_url())
        return self._fix(next((e.text for e in b.iter() if _tag(e) == 'Uri' and e.text), ''))

    def network(self):
        b = self.call('<tds:GetNetworkInterfaces/>')
        ni = next((e for e in b.iter() if _tag(e) == 'NetworkInterfaces'), None)
        if ni is None:
            raise CamError('камера не отдала сетевые настройки')
        out = {'token': ni.get('token') or '', 'mac': '', 'dhcp': False, 'ip': '', 'prefix': 24}
        for e in ni.iter():
            n = _tag(e)
            if n == 'HwAddress' and e.text:
                out['mac'] = e.text.strip().lower()
            elif n == 'DHCP' and (e.text or '').strip().lower() in ('true', '1'):
                out['dhcp'] = True
        ip4 = next((e for e in ni.iter() if _tag(e) == 'IPv4'), None)
        if ip4 is not None:
            for blk in ('Config',):
                c = next((e for e in ip4.iter() if _tag(e) == blk), None)
                if c is not None:
                    for part in ('Manual', 'FromDHCP', 'LinkLocal'):
                        p = next((e for e in c if _tag(e) == part), None)
                        if p is not None:
                            a = next((e.text for e in p.iter() if _tag(e) == 'Address' and e.text), '')
                            pl = next((e.text for e in p.iter() if _tag(e) == 'PrefixLength' and e.text), '')
                            if a and (part != 'LinkLocal' or not out['ip']) and (part == 'FromDHCP' and out['dhcp'] or part == 'Manual' and not out['dhcp'] or not out['ip']):
                                out['ip'], out['prefix'] = a, int(pl or 24)
        try:
            g = self.call('<tds:GetNetworkDefaultGateway/>')
            out['gateway'] = next((e.text for e in g.iter() if _tag(e) == 'IPv4Address' and e.text), '')
        except CamError:
            out['gateway'] = ''
        return out

    def set_network(self, token, dhcp, ip='', prefix=24, gateway=''):
        if dhcp:
            ipv4 = '<tt:Enabled>true</tt:Enabled><tt:DHCP>true</tt:DHCP>'
        else:
            ipv4 = ('<tt:Enabled>true</tt:Enabled><tt:Manual><tt:Address>%s</tt:Address><tt:PrefixLength>%d</tt:PrefixLength></tt:Manual><tt:DHCP>false</tt:DHCP>' % (esc(ip), prefix))
        b = self.call('<tds:SetNetworkInterfaces><tds:InterfaceToken>%s</tds:InterfaceToken><tds:NetworkInterface><tt:Enabled>true</tt:Enabled>'
                      '<tt:IPv4>%s</tt:IPv4></tds:NetworkInterface></tds:SetNetworkInterfaces>' % (esc(token), ipv4), timeout=10)
        if gateway and not dhcp:
            try:
                self.call('<tds:SetNetworkDefaultGateway><tds:IPv4Address>%s</tds:IPv4Address></tds:SetNetworkDefaultGateway>' % esc(gateway))
            except CamError:
                pass
        return any(_tag(e) == 'RebootNeeded' and (e.text or '').strip().lower() == 'true' for e in b.iter())

    def users(self):
        b = self.call('<tds:GetUsers/>')
        return [{'name': _t(u, 'tt:Username'), 'level': _t(u, 'tt:UserLevel') or 'User'} for u in b.iter() if _tag(u) == 'User']

    def set_password(self, name, pw, level):
        self.call('<tds:SetUser><tds:User><tt:Username>%s</tt:Username><tt:Password>%s</tt:Password><tt:UserLevel>%s</tt:UserLevel></tds:User></tds:SetUser>'
                  % (esc(name), esc(pw), esc(level or 'User')))

    def create_user(self, name, pw, level):
        self.call('<tds:CreateUsers><tds:User><tt:Username>%s</tt:Username><tt:Password>%s</tt:Password><tt:UserLevel>%s</tt:UserLevel></tds:User></tds:CreateUsers>'
                  % (esc(name), esc(pw), esc(level or 'User')))


def find_onvif(ip, ports=None):
    """the port where ONVIF answers without a login (GetSystemDateAndTime), or 0"""
    for p in ports or ONVIF_PORTS:
        if not _open(ip, p, .6):
            continue
        try:
            soap('http://%s:%s/onvif/device_service' % (ip, p), '<tds:GetSystemDateAndTime/>', timeout=3)
            return p
        except CamError as e:
            if 'не пускает' in str(e):             # answered, but wants a login even for the time: it is ONVIF anyway
                return p
    return 0


def _open(ip, port, timeout=.5):
    try:
        with socket.create_connection((ip, port), timeout):
            return True
    except OSError:
        return False


# ───────── fingerprints (no login) ─────────
def http_probe(ip, port):
    scheme = 'https' if port == 443 else 'http'
    try:
        import ssl
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request('%s://%s:%s/' % (scheme, ip, port), headers={'User-Agent': 'RackLive'})
        try:
            r = urllib.request.urlopen(req, timeout=3, context=ctx)
            code, h, body = r.status, r.headers, r.read(4000)
        except urllib.error.HTTPError as e:
            code, h, body = e.code, e.headers, e.read(4000)
        text = body.decode('utf-8', 'ignore')
        return {'code': code, 'server': h.get('Server', ''), 'auth': h.get('WWW-Authenticate', ''), 'title': (re.search(r'<title>(.*?)</title>', text, re.I | re.S) or [0, ''])[1].strip()[:80], 'text': text.lower()}
    except Exception:
        return None


def rtsp_probe(ip, port=554):
    """RTSP OPTIONS (names the server) + DESCRIBE (401 = wants a login, 200 = open to anyone)"""
    out = {'server': '', 'describe': 0}
    try:
        with socket.create_connection((ip, port), 2) as s:
            s.settimeout(2)
            s.sendall(('OPTIONS rtsp://%s:%d/ RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: RackLive\r\n\r\n' % (ip, port)).encode())
            r = s.recv(2000).decode('latin-1', 'ignore')
            m = re.search(r'^Server:\s*(.+)$', r, re.I | re.M)
            out['server'] = m.group(1).strip() if m else ''
            s.sendall(('DESCRIBE rtsp://%s:%d/ RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nUser-Agent: RackLive\r\n\r\n' % (ip, port)).encode())
            r = s.recv(2000).decode('latin-1', 'ignore')
            m = re.match(r'RTSP/1\.\d\s+(\d+)', r)
            out['describe'] = int(m.group(1)) if m else 0
    except OSError:
        pass
    return out


def hik_status(ip, port=80):
    """Hikvision tells (without a login) whether it was activated: True / False / None = not Hikvision or unknown"""
    try:
        r = urllib.request.urlopen('http://%s:%s/ISAPI/Security/activateStatus' % (ip, port), timeout=3).read().decode('utf-8', 'ignore')
        m = re.search(r'<activated>(true|false)</activated>', r, re.I)
        return m.group(1).lower() == 'true' if m else None
    except Exception:
        return None


def vendor_paths(ip, port):
    """a camera that does not name itself still answers its maker's own paths — with 401 («login needed») instead of 404. A device that answers 200 to everything is not judged by this.
    → ('Hikvision', 'hikvision') | ('Dahua', 'dahua') | None"""
    def code(path):
        try:
            return urllib.request.urlopen('http://%s:%s%s' % (ip, port, path), timeout=3).status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0
    junk = code('/rl-no-such-page-%d' % (os.getpid() % 1000))
    if junk not in (404, 401):                      # a catch-all page: the answers below mean nothing
        return None
    if code('/ISAPI/Security/activateStatus') in (401, 200):
        return 'Hikvision', 'hikvision'
    if code('/cgi-bin/magicBox.cgi?action=getSystemInfo') == 401:
        return 'Dahua', 'dahua'
    return None


def classify(ip, ports, mac=''):
    """→ item for the list. Never logs in."""
    it = {'ip': ip, 'ports': sorted(ports), 'vendor': '', 'family': '', 'tip': '', 'model': '', 'kind': 'unknown', 'what': '', 'onvif': 0, 'login': 'unknown', 'reasons': []}
    web = next((p for p in (80, 8080, 443) if p in ports), 0)
    hp = http_probe(ip, web) if web else None
    rt = rtsp_probe(ip, 554) if 554 in ports else {'server': '', 'describe': 0}
    blob = ' '.join([(hp or {}).get('server', ''), (hp or {}).get('auth', ''), (hp or {}).get('title', ''), rt['server'], (hp or {}).get('text', '')[:3000]]).lower()
    vendor, family, tip = brands.detect(blob, ports, mac)
    if not vendor and web:
        vp = vendor_paths(ip, web)
        if vp:
            vendor, family, tip = vp[0], vp[1], brands.BY_NAME[vp[0]][1]
            it['reasons'].append('отвечает так, как отвечает %s (это может быть и его «родственная» марка: HiWatch, EZVIZ, Hilook…)' % vp[0] if vp[0] == 'Hikvision' else 'отвечает так, как отвечает Dahua (это может быть и его «родственная» марка: Imou, Amcrest, RVi…)')
    it['vendor'], it['family'], it['tip'] = vendor, family, tip
    it['onvif'] = find_onvif(ip, [p for p in ONVIF_PORTS if p in ports] or None)
    if family == 'hikvision' and web:
        act = hik_status(ip, web)
        if act is False:
            it['login'] = 'inactive'
            it['reasons'].append('камера ещё не активирована — не задан первый пароль')
    if it['login'] != 'inactive':
        if rt['describe'] == 200:
            it['login'] = 'open'
            it['reasons'].append('видеопоток открыт без пароля')
        elif rt['describe'] in (401, 403) or (hp and hp['code'] in (401, 403)) or (hp and hp['auth']):
            it['login'] = 'password'
        elif hp and hp['code'] == 200 and re.search(r'init|activate|set password|установ.* пароль|active', hp['text'][:3000]) and family in ('dahua', 'hikvision'):
            it['login'] = 'inactive'
            it['reasons'].append('на странице камеры просят задать пароль — возможно, она не активирована')
    # camera or recorder?
    model = ''
    m = re.search(r'\b((?:DS|DH|IPC|NVR|DHI|XVR|HWN|UNV)-[A-Z0-9\-/]{4,30})', (hp or {}).get('title', '') + ' ' + (hp or {}).get('server', ''), re.I)
    if m:
        model = m.group(1)
    it['model'] = model
    if model and RECORDER_RE.search(model):
        it['kind'] = 'recorder'
        it['reasons'].append('в названии модели «%s» — это видеорегистратор' % model)
    elif it['onvif'] or 554 in ports or vendor:
        it['kind'] = 'camera'
    tag = {'camera': 'Камера', 'recorder': 'Видеорегистратор', 'unknown': 'Видеоустройство'}[it['kind']]
    it['what'] = (vendor + ' · ' if vendor else '') + tag + (' · ' + model if model else '')
    if it['kind'] == 'camera':
        it['reasons'].append('точнее покажет вход: у регистратора несколько видеоисточников (каналов)')
    return it


# ───────── passwords through the vendor's own API (when ONVIF refuses) ─────────
def dahua_set_password(ip, port, user, old, new):
    import urllib.parse
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, 'http://%s:%s/' % (ip, port), user, old)
    op = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr), urllib.request.HTTPBasicAuthHandler(mgr))
    url = 'http://%s:%s/cgi-bin/userManager.cgi?action=modifyPassword&name=%s&pwd=%s&pwdOld=%s' % (ip, port, *(urllib.parse.quote(x, safe='') for x in (user, new, old)))
    try:
        r = op.open(url, timeout=8).read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        raise CamError('камера Dahua не приняла смену пароля (код %s)' % e.code)
    except OSError as e:
        raise CamError('камера не отвечает (%s)' % e)
    if 'ok' not in r.lower():
        raise CamError('камера Dahua не приняла смену пароля: ' + r.strip()[:80])


def hik_activate(ip, port, pw):
    body = ('<?xml version="1.0" encoding="UTF-8"?><ActivateInfo version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema"><password>%s</password></ActivateInfo>' % esc(pw)).encode()
    req = urllib.request.Request('http://%s:%s/ISAPI/System/activate' % (ip, port), body, {'Content-Type': 'application/xml'}, method='PUT')
    try:
        r = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        raise CamError('камера не приняла активацию (код %s): возможно, нужна программа SADP от Hikvision' % e.code)
    except OSError as e:
        raise CamError('камера не отвечает (%s)' % e)
    if 'ok' not in r.lower() and '<statusCode>1' not in r:
        raise CamError('камера не приняла активацию: ' + re.sub(r'<[^>]+>', ' ', r).strip()[:100])


def fetch_snapshot(url, user, pw):
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, url, user, pw)
    op = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr), urllib.request.HTTPBasicAuthHandler(mgr))
    try:
        data = op.open(url, timeout=8).read(3_000_000)
    except urllib.error.HTTPError as e:
        raise CamError('камера не отдала кадр (код %s)' % e.code)
    except OSError as e:
        raise CamError('камера не отдала кадр (%s)' % e)
    if data[:2] != b'\xff\xd8' and data[:4] != b'\x89PNG':
        raise CamError('камера прислала не картинку')
    return 'data:image/%s;base64,%s' % ('jpeg' if data[:2] == b'\xff\xd8' else 'png', base64.b64encode(data).decode())


# ───────── the tool ─────────
SAMPLE = [
    {'ip': '10.0.7.11', 'ports': [80, 554, 8000], 'vendor': 'Hikvision', 'family': 'hikvision', 'model': 'DS-2CD2143G2-I', 'kind': 'camera', 'what': 'Hikvision · Камера · DS-2CD2143G2-I', 'onvif': 80, 'login': 'password', 'reasons': [], 'mac': '44:19:b6:00:07:11'},
    {'ip': '10.0.7.12', 'ports': [80, 554, 37777], 'vendor': 'Dahua', 'family': 'dahua', 'model': '', 'kind': 'camera', 'what': 'Dahua · Камера', 'onvif': 80, 'login': 'password', 'reasons': [], 'mac': '3c:ef:8c:00:07:12'},
    {'ip': '10.0.7.13', 'ports': [80, 554, 8000], 'vendor': 'EZVIZ', 'family': 'hikvision', 'model': '', 'kind': 'camera', 'what': 'EZVIZ · Камера', 'onvif': 80, 'login': 'inactive', 'tip': 'приложение EZVIZ (код на наклейке камеры)',
     'reasons': ['камера ещё не активирована — не задан первый пароль'], 'mac': 'aa:bb:cc:00:07:13'},
    {'ip': '10.0.7.2', 'ports': [80, 554, 37777], 'vendor': 'Dahua', 'family': 'dahua', 'model': 'DHI-NVR4208', 'kind': 'recorder', 'what': 'Dahua · Видеорегистратор · DHI-NVR4208', 'onvif': 80, 'login': 'password',
     'reasons': ['в названии модели «DHI-NVR4208» — это видеорегистратор'], 'mac': '3c:ef:8c:00:07:02'},
    {'ip': '10.0.7.14', 'ports': [80, 554], 'vendor': 'Tapo (TP-Link)', 'family': '', 'model': '', 'kind': 'camera', 'what': 'Tapo (TP-Link) · Камера', 'onvif': 2020, 'login': 'open', 'reasons': ['видеопоток открыт без пароля'], 'mac': 'aa:bb:cc:00:07:14'},
    {'ip': '10.0.7.15', 'ports': [80, 554], 'vendor': 'Tiandy', 'family': '', 'model': '', 'kind': 'camera', 'what': 'Tiandy · Камера', 'onvif': 80, 'login': 'password', 'reasons': [], 'mac': 'aa:bb:cc:00:07:15'},
]
MAX_HOSTS = 4096
MAX_TRIES = 3                  # saved passwords tried per camera at one press: cameras lock out after several wrong ones in a row


def parse_targets(arg, auto):
    """«where to look» → (list of networks, error). Empty / 'auto' = every network Rack Live knows about; otherwise a list or a text with networks."""
    if isinstance(arg, str):
        arg = [x for x in re.split(r'[,\s;]+', arg.strip()) if x]
    arg = [x for x in (arg or []) if x]
    if not arg or arg == ['auto']:
        arg = [a['cidr'] for a in auto]
    nets = []
    for x in arg:
        net, err = netscan.check_cidr(x)
        if err:
            return None, '%s: %s' % (x, err)
        nets.append(net)
    nets = [n for n in dict.fromkeys(nets) if not any(n != o and n.subnet_of(o) for o in nets)]
    if sum(n.num_addresses - 2 for n in nets) > MAX_HOSTS:
        return None, 'выбрано слишком много адресов (не больше %d): уберите лишние сети' % MAX_HOSTS
    if not nets:
        return None, 'не нашлось сети для поиска — укажите её вручную'
    return nets, None


class Cameras:
    def __init__(self, app, demo=False):
        self.app, self.store, self.demo = app, app.store, demo
        self.lock = threading.Lock()
        self.s = self.store._load('cameras.json', {})
        self.s.update(running=False)
        self.s.setdefault('items', [])
        self.cancel = False
        self.fake = {}                 # demo: what «changed» (ip → {dhcp, ip, prefix, passwords})
        self.creds = self.store._load('camcreds.json', {'items': [], 'map': {}})
        self.creds.setdefault('items', []); self.creds.setdefault('map', {})
        self.jobs = {}

    # ───────── saved passwords: never leave the server ─────────
    def _save_creds(self):
        self.store._dump('camcreds.json', self.creds)

    def creds_public(self):
        return [{'id': c['id'], 'user': c['user'], 'label': c.get('label') or '', 'mask': '•' * min(len(c['password']), 8), 'used': c.get('used', 0), 'last': c.get('last', 0),
                 'cameras': sum(1 for v in self.creds['map'].values() if v == c['id'])} for c in self.creds['items']]

    def add_cred(self, user, password, label=''):
        user, password = str(user or '').strip(), str(password or '')
        if not user or not password:
            raise CamError('нужны логин и пароль')
        if len(user) > 64 or len(password) > 128:
            raise CamError('слишком длинно')
        with self.lock:
            for c in self.creds['items']:
                if c['user'] == user and c['password'] == password:
                    if label and not c.get('label'):
                        c['label'] = label[:40]
                    self._save_creds()
                    return c['id']
            cid = 'c' + hashlib.sha1(os.urandom(8)).hexdigest()[:8]
            self.creds['items'].append({'id': cid, 'user': user, 'password': password, 'label': str(label or '')[:40], 'added': int(time.time()), 'used': 0, 'last': 0})
            self._save_creds()
        return cid

    def del_cred(self, cid):
        with self.lock:
            self.creds['items'] = [c for c in self.creds['items'] if c['id'] != cid]
            self.creds['map'] = {k: v for k, v in self.creds['map'].items() if v != cid}
            self._save_creds()

    def _cred(self, cid):
        return next((c for c in self.creds['items'] if c['id'] == cid), None)

    def _key(self, ip):
        it = next((x for x in self.s.get('items', []) if x['ip'] == ip), None)
        return ((it or {}).get('mac') or ip)

    def _remember(self, ip, cid):
        c = self._cred(cid)
        if not c:
            return
        with self.lock:
            c['used'] = c.get('used', 0) + 1; c['last'] = int(time.time())
            self.creds['map'][self._key(ip)] = cid
            self._save_creds()

    def _candidates(self, ip, body):
        """[(cred id | None, user, password)] to try, in order: what the caller named, else the saved ones (this camera's own first), at most MAX_TRIES from `offset`"""
        if body.get('password'):
            return [(None, str(body.get('user') or 'admin'), str(body['password']))], 0
        if body.get('credId'):
            c = self._cred(str(body['credId']))
            if not c:
                raise CamError('такого пароля нет в списке — выберите другой или введите вручную')
            return [(c['id'], c['user'], c['password'])], 0
        order = []
        own = self.creds['map'].get(self._key(ip))
        if own and self._cred(own):
            order.append(self._cred(own))
        order += sorted([c for c in self.creds['items'] if c['id'] != own], key=lambda c: (-c.get('used', 0), -c.get('last', 0)))
        if not order:
            raise CamError('список паролей пуст — введите логин и пароль камеры (он сохранится в список)')
        off = max(0, int(body.get('offset') or 0))
        part = order[off:off + MAX_TRIES]
        if not part:
            raise CamError('в списке больше нет паролей для пробы — введите правильный вручную')
        return [(c['id'], c['user'], c['password']) for c in part], len(order) - off - len(part)

    def recorders(self):
        """video recorders that live on your devices: Synology Surveillance Station (the NAS itself records) — cached for a minute"""
        c = getattr(self, '_rec', None)
        if c and time.time() - c[0] < 60:
            return c[1]
        from .drivers import REGISTRY
        out = []
        for d in self.store.cfg['devices']:
            drv = REGISTRY.get(d.get('driver'))
            if not d.get('enabled', True) or not hasattr(drv, 'surveillance'):
                continue
            try:
                r = drv.surveillance(d)
            except Exception as e:
                r = {'name': 'Surveillance Station', 'error': str(e)[:140], 'cameras': [], 'host': d.get('host') or ''}
            if r:
                out.append(dict(r, deviceId=d['id'], deviceName=d.get('name')))
        self._rec = (time.time(), out)
        return out

    def public(self):
        subs = self.app.netscan.subnets()
        s = self.s
        return {'running': s.get('running', False), 'done': s.get('done', 0), 'total': s.get('total', 0), 'cidr': s.get('cidr'), 'finished': s.get('finished'),
                'error': s.get('error'), 'skipped': s.get('skipped') or [], 'items': s.get('items', []), 'subnets': subs, 'creds': self.creds_public(), 'brands': brands.public()}

    # ───────── search ─────────
    def start(self, arg):
        nets, err = parse_targets(arg, self.app.netscan.subnets())
        if err:
            return False, err
        with self.lock:
            if self.s.get('running'):
                return False, 'поиск уже идёт'
            self.cancel = False
            self.s.update(running=True, done=0, total=sum(n.num_addresses - 2 for n in nets), cidr=', '.join(str(n) for n in nets), finished=None, error=None, items=[])
        self.store.bump()
        threading.Thread(target=self._run_demo if self.demo else self._run, args=(nets,), daemon=True).start()
        return True, None

    def stop(self):
        self.cancel = True

    def _finish(self, error=None):
        self.s.update(running=False, finished=int(time.time()), error=error)
        self.store._dump('cameras.json', {k: self.s.get(k) for k in ('cidr', 'finished', 'items', 'error', 'total')})
        self.store.bump()

    def _run_demo(self, nets):
        try:
            for i in range(10):
                if self.cancel:
                    break
                time.sleep(.15)
                self.s['done'] = int(self.s['total'] * (i + 1) / 10)
                self.store.bump()
            self.s['items'] = [dict(x) for x in SAMPLE]
            self._finish()
        except Exception as e:
            self._finish(str(e))

    def _run(self, nets):
        try:
            skip = netscan.infra_ips(self.app)                 # never the routers' own addresses: a burst of connections there is a port scan for the router and it shuts Rack Live out for ~15 min
            hosts = [str(h) for n in nets for h in n.hosts() if str(h) not in skip]
            self.s['skipped'] = sorted(skip & {str(h) for n in nets for h in n.hosts()})
            tasks = [(ip, p) for ip in hosts for p in PORTS]
            found, done = {}, [0]

            def probe(t):
                done[0] += 1
                return t, _open(t[0], t[1], .5)
            with concurrent.futures.ThreadPoolExecutor(96) as pool:
                for (ip, p), ok in pool.map(probe, tasks):
                    if ok:
                        found.setdefault(ip, set()).add(p)
                    if done[0] % 64 == 0:
                        self.s['done'] = min(len(hosts), done[0] // len(PORTS)); self.store.bump()
                    if self.cancel:
                        return self._finish('остановлено')
            mine = netscan.local_ips()
            cand = {ip: ps for ip, ps in found.items() if ip not in mine and ps & {554, 8000, 37777, 34567, 8554, 8899, 2020}}      # camera ports
            # a plain web server on 80 only is not a camera unless ONVIF answers
            for ip, ps in found.items():
                if ip not in cand and ip not in mine and ps & {80, 8080, 8000, 8899} and find_onvif(ip, [p for p in ONVIF_PORTS if p in ps]):
                    cand[ip] = ps
            self.s['total'] = len(cand) or 1; self.s['done'] = 0
            arp = netscan.arp_table()
            items = []
            with concurrent.futures.ThreadPoolExecutor(8) as pool:
                for i, it in enumerate(pool.map(lambda kv: classify(kv[0], kv[1], arp.get(kv[0], '')), sorted(cand.items(), key=lambda kv: ipaddress.ip_address(kv[0])))):
                    it['mac'] = arp.get(it['ip'], '')
                    items.append(it)
                    self.s['done'] = i + 1; self.s['items'] = list(items); self.store.bump()
            self.s['items'] = items
            self._finish()
        except Exception as e:
            self._finish('%s: %s' % (type(e).__name__, e))

    def probe_one(self, ip):
        """check one address by hand («Добавить камеру по адресу»)"""
        ip = need_private(ip)
        if self.demo:
            return dict(SAMPLE[0], ip=ip)
        ports = {p for p in PORTS if _open(ip, p, .8)}
        if not ports:
            raise CamError('по адресу %s никто не отвечает на портах камер' % ip)
        mac = netscan.arp_table().get(ip, '')
        it = classify(ip, ports, mac)
        it['mac'] = mac
        with self.lock:
            self.s['items'] = [x for x in self.s.get('items', []) if x['ip'] != ip] + [it]
            self.store._dump('cameras.json', {k: self.s.get(k) for k in ('cidr', 'finished', 'items', 'error', 'total')})
        self.store.bump()
        return it

    # ───────── operations with a login ─────────
    def op(self, body):
        """one operation on one device. The login comes with the request (typed, or a saved one by id, or «try the saved ones») and is never sent back"""
        op = str(body.get('op') or '')
        ip = need_private(body.get('ip'))
        if op == 'activate':
            return self._op_with(op, ip, '', '', body)
        cands, left = self._candidates(ip, body)
        explicit = bool(body.get('password') or body.get('credId'))
        tried = 0
        for cid, user, pw in cands:
            try:
                r = self._op_with(op, ip, user, pw, body)
            except CamError as e:
                if 'неверный логин' in str(e) and not explicit:
                    tried += 1
                    continue
                raise
            if cid is None and body.get('remember', True):
                cid = self.add_cred(user, pw)
            if cid:
                self._remember(ip, cid)
            if r is not None:
                r['credId'] = r.get('credId') if op == 'set_password' and r.get('credId') else cid
                r['user'] = user
                r['inline'] = cid is None
            return r
        raise CamError('ни один из %d сохранённых паролей не подошёл%s. Введите правильный вручную — он сохранится в список.'
                       % (tried, ' (в списке есть ещё — можно попробовать следующие)' if left else ''))

    def _op_with(self, op, ip, user, pw, body):
        port = int(body.get('port') or 0)
        if self.demo:
            return self._demo_op(op, ip, user, pw, body)
        item = next((x for x in self.s.get('items', []) if x['ip'] == ip), None)
        port = port or (item or {}).get('onvif') or find_onvif(ip)
        if op == 'activate':
            hp = next((p for p in (80, 8080) if _open(ip, p, .8)), 0)
            if not hp or hik_status(ip, hp) is not False:
                raise CamError('эта камера не просит активации')
            pw = str(body.get('password') or '')
            if len(pw) < 8:
                raise CamError('пароль слишком короткий: нужно не меньше 8 знаков, с буквами и цифрами')
            hik_activate(ip, hp, pw)
            self._event(ip, 'камера активирована (задан первый пароль)')
            cid = self.add_cred('admin', pw, 'после активации')
            self._remember(ip, cid)
            return {'ok': True, 'message': 'Камера активирована. Пароль сохранён в список паролей — теперь можно войти.', 'credId': cid}
        if not port:
            raise CamError('камера не отвечает по стандарту ONVIF — через неё управлять нельзя')
        cam = Onvif(ip, port, user, pw)
        cam.sync_clock()
        if op == 'login':
            info = cam.info()
            try:
                src = cam.video_sources()
            except CamError:
                src = 0
            kind = 'recorder' if (src > 1 or RECORDER_RE.search(info.get('model', ''))) else 'camera'
            net = cam.network()
            try:
                users = cam.users()
            except CamError:
                users = []
            if item is not None:
                item.update(kind=kind, model=info.get('model') or item.get('model'))
                if not item.get('vendor'):
                    item['vendor'] = info.get('manufacturer') or ''
                item['what'] = '%s · %s%s' % (item['vendor'] or 'Видеоустройство', 'Видеорегистратор' if kind == 'recorder' else 'Камера', ' · ' + item['model'] if item.get('model') else '')
            return {'ok': True, 'info': info, 'kind': kind, 'channels': src, 'net': net, 'users': users, 'port': port}
        if op == 'snapshot':
            toks = cam.profiles()
            if not toks:
                raise CamError('у камеры нет видеопрофилей')
            out = {'ok': True}
            try:
                rtsp = cam.stream_uri(toks[0])
                out['rtsp'] = rtsp
                out['rtspAuth'] = re.sub(r'^rtsp://', 'rtsp://%s:%s@' % (user, pw), rtsp) if rtsp else ''
            except CamError:
                pass
            surl = cam.snapshot_uri(toks[0])
            if not surl:
                raise CamError('камера не умеет отдавать кадр по ONVIF — откройте поток по RTSP-адресу')
            out['image'] = fetch_snapshot(surl, user, pw)
            return out
        if op == 'set_ip':
            net = cam.network()
            mode = str(body.get('mode') or '')
            if mode == 'dhcp':
                reboot = cam.set_network(net['token'], True)
                self._event(ip, 'включён DHCP')
                return {'ok': True, 'message': 'Камера теперь берёт адрес по DHCP. Её новый адрес — в списке клиентов роутера (по MAC %s).' % (net.get('mac') or '?'), 'reboot': reboot, 'dhcp': True}
            new = need_private(body.get('address'))
            prefix = int(body.get('prefix') or 24)
            gw = str(body.get('gateway') or '').strip()
            if not 8 <= prefix <= 30:
                raise CamError('маска должна быть от /8 до /30 (обычно /24)')
            net_obj = ipaddress.ip_network('%s/%d' % (new, prefix), strict=False)
            if gw:
                if not private_ip(gw) or ipaddress.ip_address(gw) not in net_obj:
                    raise CamError('шлюз %s не из той же сети, что новый адрес' % gw)
            if new != ip:
                if ipaddress.ip_address(new) in (net_obj.network_address, net_obj.broadcast_address):
                    raise CamError('этот адрес не подходит для устройства (адрес сети или широковещательный)')
                if self.addr_busy(new):
                    raise CamError('адрес %s уже кем-то занят — выберите другой' % new)
            reboot = cam.set_network(net['token'], False, new, prefix, gw)
            self._event(ip, 'задан постоянный адрес %s/%d' % (new, prefix))
            for x in self.s.get('items') or []:
                if x['ip'] == ip:
                    x['ip'] = new
            self.creds['map'] = {(new if k == ip else k): v for k, v in self.creds['map'].items()}
            self.store.bump()
            return {'ok': True, 'message': 'Адрес изменён: камера теперь на %s. Старый адрес %s больше не работает.' % (new, ip), 'ip': new, 'reboot': reboot}
        if op == 'set_password':
            target = str(body.get('target') or user)
            new = str(body.get('new') or '')
            if len(new) < 6:
                raise CamError('новый пароль слишком короткий (не меньше 6 знаков; лучше 8+ с цифрами)')
            if re.search(r'[<>&"\']', new):
                raise CamError('в пароле лучше не использовать знаки < > & " \' — часть камер их не принимает')
            level = next((u['level'] for u in cam.users() if u['name'] == target), 'Administrator' if target == user else 'User')
            try:
                cam.set_password(target, new, level)
            except CamError as e:
                if 'неверный логин' in str(e) or target != user or (item or {}).get('family') != 'dahua':
                    raise
                dahua_set_password(ip, 80, user, pw, new)
            self._event(ip, 'сменён пароль пользователя «%s»' % target)
            ncid = self.add_cred(target, new, str(body.get('label') or 'после смены')) if target == user or body.get('remember', True) else None
            if ncid and target == user:
                self._remember(ip, ncid)
            return {'ok': True, 'message': 'Пароль пользователя «%s» изменён и сохранён в списке паролей.' % target, 'credId': ncid if target == user else None}
        if op == 'create_user':
            name, new = str(body.get('name') or '').strip(), str(body.get('new') or '')
            if not re.match(r'^[A-Za-z0-9_.-]{3,32}$', name):
                raise CamError('логин: 3–32 знака, латинские буквы, цифры, _ . -')
            if len(new) < 6:
                raise CamError('пароль слишком короткий (не меньше 6 знаков)')
            cam.create_user(name, new, str(body.get('level') or 'User'))
            self._event(ip, 'создан пользователь «%s»' % name)
            return {'ok': True, 'message': 'Пользователь «%s» создан.' % name}
        raise CamError('неизвестная команда')

    def addr_busy(self, ip):
        return any(_open(ip, p, .6) for p in (80, 554, 443, 22)) or bool(netscan.arp_table().get(ip))

    def _event(self, ip, text):
        self.store.add_event(None, 'Камеры', 'info', '%s: %s' % (ip, text))

    # ───────── several cameras at once ─────────
    def bulk_start(self, body):
        ips = [need_private(x) for x in (body.get('ips') or [])]
        ips = list(dict.fromkeys(ips))
        if not ips:
            raise CamError('не выбрано ни одной камеры')
        if len(ips) > 40:
            raise CamError('за один раз не больше 40 камер')
        action = str(body.get('action') or '')
        if action not in ('set_password', 'set_ip', 'create_user'):
            raise CamError('неизвестное действие')
        if action == 'set_ip' and body.get('mode') != 'dhcp':
            need_private(body.get('address'))
        jid = 'j' + hashlib.sha1(os.urandom(8)).hexdigest()[:8]
        job = {'id': jid, 'total': len(ips), 'done': 0, 'results': [], 'finished': False, 'action': action}
        self.jobs[jid] = job
        for old in list(self.jobs)[:-10]:
            self.jobs.pop(old, None)
        threading.Thread(target=self._bulk_run, args=(job, ips, body), daemon=True).start()
        return jid

    def _bulk_run(self, job, ips, body):
        action = job['action']
        nxt = None
        if action == 'set_ip' and body.get('mode') != 'dhcp':
            nxt = ipaddress.ip_address(str(body['address']).strip())
        used = set(ips)
        for ip in ips:
            r = {'ip': ip, 'ok': False, 'message': ''}
            try:
                sub = {'ip': ip, 'op': action, 'remember': True}
                for k in ('new', 'name', 'level', 'target', 'user', 'password', 'credId', 'mode', 'prefix', 'gateway', 'label', 'port'):
                    if body.get(k) not in (None, ''):
                        sub[k] = body[k]
                if action == 'set_ip' and nxt is not None:
                    while str(nxt) in used or self.addr_busy(str(nxt)):
                        nxt += 1
                    sub['address'] = str(nxt); used.add(str(nxt)); nxt += 1
                if action == 'set_password' and body.get('target') in (None, ''):
                    sub.pop('target', None)
                res = self.op(sub)
                r.update(ok=True, message=res.get('message') or 'готово')
                if res.get('ip'):
                    r['newIp'] = res['ip']
            except CamError as e:
                r['message'] = str(e)
            except Exception as e:
                r['message'] = '%s: %s' % (type(e).__name__, e)
            job['results'].append(r); job['done'] += 1
            self.store.bump()
        job['finished'] = True

    # demo: same answers, nothing real
    def _demo_op(self, op, ip, user, pw, b):
        st = self.fake.setdefault(ip, {'pw': 'demo-pass', 'user': 'admin', 'dhcp': False, 'ip': ip, 'active': ip != '10.0.7.13'})
        it = next((x for x in SAMPLE if x['ip'] == ip), SAMPLE[0])
        if op == 'activate':
            if len(str(b.get('password') or '')) < 8:
                raise CamError('пароль слишком короткий: нужно не меньше 8 знаков, с буквами и цифрами')
            st['active'] = True; st['pw'] = str(b.get('password'))
            cid = self.add_cred('admin', st['pw'], 'после активации')
            return {'ok': True, 'message': 'Камера активирована. Пароль сохранён в список паролей.', 'credId': cid}
        if user != st['user'] or pw != st['pw']:
            raise CamError('камера не пускает: неверный логин или пароль (в демо: admin / demo-pass)')
        if op == 'login':
            rec = it['kind'] == 'recorder'
            return {'ok': True, 'kind': it['kind'], 'channels': 8 if rec else 1, 'port': 80,
                    'info': {'manufacturer': it['vendor'] or 'Demo', 'model': it['model'] or 'IPC-DEMO', 'firmware': 'V5.7.1 build 230101', 'serial': 'DEMO' + ip.split('.')[-1].zfill(8)},
                    'net': {'token': 'eth0', 'mac': 'aa:bb:cc:00:07:' + ip.split('.')[-1].zfill(2), 'dhcp': st['dhcp'], 'ip': st['ip'], 'prefix': 24, 'gateway': '10.0.7.1'},
                    'users': [{'name': st['user'], 'level': 'Administrator'}, {'name': 'viewer', 'level': 'User'}]}
        if op == 'snapshot':
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 180"><rect width="320" height="180" fill="#14202e"/><rect y="120" width="320" height="60" fill="#22364a"/>'
                   '<circle cx="250" cy="45" r="16" fill="#f5d98a"/><text x="12" y="24" fill="#9fb4c8" font-size="12" font-family="monospace">DEMO %s</text></svg>' % ip)
            return {'ok': True, 'image': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode(), 'rtsp': 'rtsp://%s:554/Streaming/Channels/101' % ip,
                    'rtspAuth': 'rtsp://%s:%s@%s:554/Streaming/Channels/101' % (user, pw, ip)}
        if op == 'set_ip':
            if b.get('mode') == 'dhcp':
                st['dhcp'] = True
                return {'ok': True, 'message': 'Камера теперь берёт адрес по DHCP (демо).', 'dhcp': True}
            new = need_private(b.get('address'))
            st.update(dhcp=False, ip=new)
            return {'ok': True, 'message': 'Адрес изменён: камера теперь на %s (демо).' % new, 'ip': new}
        if op == 'set_password':
            if len(str(b.get('new') or '')) < 6:
                raise CamError('новый пароль слишком короткий (не меньше 6 знаков; лучше 8+ с цифрами)')
            if str(b.get('target') or user) == st['user']:
                st['pw'] = str(b.get('new'))
                ncid = self.add_cred(user, st['pw'], 'после смены')
                self._remember(ip, ncid)
                return {'ok': True, 'message': 'Пароль изменён (демо).', 'credId': ncid}
            return {'ok': True, 'message': 'Пароль изменён (демо).'}
        if op == 'create_user':
            return {'ok': True, 'message': 'Пользователь создан (демо).'}
        raise CamError('неизвестная команда')
