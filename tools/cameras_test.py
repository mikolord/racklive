#!/usr/bin/env python3
"""Tool «Камеры»: the ONVIF client against a small imitation camera (no real device is touched).
    python tools/cameras_test.py"""
import http.server, os, re, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import cameras  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


STATE = {'user': 'admin', 'pw': 'secret1', 'dhcp': False, 'ip': '192.168.7.50', 'seen': []}
ENV = '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Body>%s</s:Body></s:Envelope>'


def fault(text):
    return ENV % ('<s:Fault><s:Code><s:Value>s:Sender</s:Value></s:Code><s:Reason><s:Text xml:lang="en">%s</s:Text></s:Reason></s:Fault>' % text)


class Cam(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith('/snap'):
            self.send_response(200); self.send_header('Content-Type', 'image/jpeg'); self.end_headers(); self.wfile.write(b'\xff\xd8\xff\xe0fakejpeg'); return
        if self.path.startswith('/ISAPI/Security/activateStatus'):
            self.send_response(200); self.end_headers(); self.wfile.write(b'<ActivateStatus><activated>true</activated></ActivateStatus>'); return
        self.send_response(200); self.send_header('Server', 'App-webs/'); self.end_headers(); self.wfile.write(b'<html><title>NVR DS-7608NI</title></html>')

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0))).decode()
        STATE['seen'].append(body)
        port = self.server.server_address[1]

        def reply(x, code=200):
            self.send_response(code); self.send_header('Content-Type', 'application/soap+xml'); self.end_headers(); self.wfile.write((ENV % x if '<s:Envelope' not in x else x).encode())
        if 'GetSystemDateAndTime' in body:
            return reply('<tds:GetSystemDateAndTimeResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><tds:SystemDateAndTime><tt:UTCDateTime>'
                         '<tt:Time><tt:Hour>10</tt:Hour><tt:Minute>0</tt:Minute><tt:Second>0</tt:Second></tt:Time><tt:Date><tt:Year>2024</tt:Year><tt:Month>1</tt:Month><tt:Day>1</tt:Day></tt:Date>'
                         '</tt:UTCDateTime></tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>')
        if STATE['user'] not in body or 'PasswordDigest' not in body:
            return reply(fault('Sender not authorized'), 400)
        # verify the digest the way a camera does
        import base64, hashlib
        nonce = base64.b64decode(re.search(r'<Nonce[^>]*>(.*?)</Nonce>', body).group(1))
        created = re.search(r'<Created[^>]*>(.*?)</Created>', body).group(1)
        want = base64.b64encode(hashlib.sha1(nonce + created.encode() + STATE['pw'].encode()).digest()).decode()
        if want not in body:
            return reply(fault('Sender not authorized'), 400)
        if 'GetDeviceInformation' in body:
            return reply('<tds:GetDeviceInformationResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><tds:Manufacturer>ACME</tds:Manufacturer><tds:Model>IPC-9000</tds:Model>'
                         '<tds:FirmwareVersion>1.2.3</tds:FirmwareVersion><tds:SerialNumber>SN123</tds:SerialNumber></tds:GetDeviceInformationResponse>')
        if 'GetCapabilities' in body:
            return reply('<tds:GetCapabilitiesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><tds:Capabilities><tt:Media>'
                         '<tt:XAddr>http://10.9.9.9:%d/onvif/media_service</tt:XAddr></tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>' % port)
        if 'GetVideoSources' in body:
            return reply('<trt:GetVideoSourcesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl"><trt:VideoSources token="v1"/><trt:VideoSources token="v2"/></trt:GetVideoSourcesResponse>')
        if 'GetProfiles' in body:
            return reply('<trt:GetProfilesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl"><trt:Profiles token="p1"/></trt:GetProfilesResponse>')
        if 'GetStreamUri' in body:
            return reply('<trt:GetStreamUriResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><trt:MediaUri><tt:Uri>rtsp://10.9.9.9:554/s1</tt:Uri></trt:MediaUri></trt:GetStreamUriResponse>')
        if 'GetSnapshotUri' in body:
            return reply('<trt:GetSnapshotUriResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><trt:MediaUri><tt:Uri>http://10.9.9.9:%d/snap.jpg</tt:Uri></trt:MediaUri></trt:GetSnapshotUriResponse>' % port)
        if 'GetNetworkInterfaces' in body:
            return reply('<tds:GetNetworkInterfacesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><tds:NetworkInterfaces token="eth0"><tt:Enabled>true</tt:Enabled>'
                         '<tt:Info><tt:HwAddress>AA:BB:CC:00:11:22</tt:HwAddress></tt:Info><tt:IPv4><tt:Enabled>true</tt:Enabled><tt:Config><tt:Manual><tt:Address>%s</tt:Address><tt:PrefixLength>24</tt:PrefixLength></tt:Manual>'
                         '<tt:DHCP>%s</tt:DHCP></tt:Config></tt:IPv4></tds:NetworkInterfaces></tds:GetNetworkInterfacesResponse>' % (STATE['ip'], 'true' if STATE['dhcp'] else 'false'))
        if 'GetNetworkDefaultGateway' in body:
            return reply('<tds:GetNetworkDefaultGatewayResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><tds:NetworkGateway><tt:IPv4Address>192.168.7.1</tt:IPv4Address></tds:NetworkGateway></tds:GetNetworkDefaultGatewayResponse>')
        if 'SetNetworkInterfaces' in body:
            STATE['dhcp'] = '<tt:DHCP>true</tt:DHCP>' in body
            m = re.search(r'<tt:Address>(.*?)</tt:Address>', body)
            if m:
                STATE['ip'] = m.group(1)
            return reply('<tds:SetNetworkInterfacesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><tds:RebootNeeded>false</tds:RebootNeeded></tds:SetNetworkInterfacesResponse>')
        if 'SetNetworkDefaultGateway' in body:
            return reply('<tds:SetNetworkDefaultGatewayResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>')
        if 'GetUsers' in body:
            return reply('<tds:GetUsersResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><tds:User><tt:Username>admin</tt:Username><tt:UserLevel>Administrator</tt:UserLevel></tds:User>'
                         '<tds:User><tt:Username>viewer</tt:Username><tt:UserLevel>User</tt:UserLevel></tds:User></tds:GetUsersResponse>')
        if 'SetUser' in body:
            m = re.search(r'<tt:Username>(.*?)</tt:Username><tt:Password>(.*?)</tt:Password>', body)
            if m and m.group(1) == STATE['user']:
                STATE['pw'] = m.group(2)
            return reply('<tds:SetUserResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>')
        if 'CreateUsers' in body:
            return reply('<tds:CreateUsersResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl"/>')
        return reply(fault('Action not implemented'), 400)


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Cam)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

class Plain(http.server.BaseHTTPRequestHandler):          # a camera that names nothing: 401 on its maker's path, 404 elsewhere (or 200 for everything)
    mode = 'hik'
    def log_message(self, *a): pass
    def do_GET(self):
        if Plain.mode == 'catchall':
            self.send_response(200); self.end_headers(); self.wfile.write(b'<html>hi</html>'); return
        if self.path.startswith('/ISAPI/Security/activateStatus') and Plain.mode == 'hik':
            self.send_response(401); self.end_headers(); return
        if self.path.startswith('/cgi-bin/magicBox.cgi') and Plain.mode == 'dahua':
            self.send_response(401); self.end_headers(); return
        self.send_response(404); self.end_headers()


plain = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Plain)
threading.Thread(target=plain.serve_forever, daemon=True).start()
print('ONVIF against an imitation camera:')
check('the port is found without a login', cameras.find_onvif('127.0.0.1', [port]) == port)
check('private-address guard', not cameras.private_ip('8.8.8.8') and not cameras.private_ip('127.0.0.1') and cameras.private_ip('192.168.7.5'))
try:
    cameras.need_private('1.2.3.4'); check('a public address is refused', False)
except cameras.CamError:
    check('a public address is refused', True)

cam = cameras.Onvif('127.0.0.1', port, 'admin', 'secret1'); cam.sync_clock()
check('clock difference is read from the camera', abs(cam.skew) > 3600)
info = cam.info()
check('device information', info['model'] == 'IPC-9000' and info['serial'] == 'SN123', info)
check('media address inside the camera is replaced by the one we reached it by', cam.media_url().startswith('http://127.0.0.1:%d/' % port), cam.media_url())
check('two video sources = a recorder', cam.video_sources() == 2)
toks = cam.profiles()
check('stream address', cam.stream_uri(toks[0]) == 'rtsp://127.0.0.1:554/s1', cam.stream_uri(toks[0]))
net = cam.network()
check('network read', net['ip'] == '192.168.7.50' and net['prefix'] == 24 and not net['dhcp'] and net['gateway'] == '192.168.7.1' and net['mac'] == 'aa:bb:cc:00:11:22', net)
check('users read', [u['name'] for u in cam.users()] == ['admin', 'viewer'])
img = cameras.fetch_snapshot(cam.snapshot_uri(toks[0]), 'admin', 'secret1')
check('snapshot comes as a picture', img.startswith('data:image/jpeg;base64,'))

bad = cameras.Onvif('127.0.0.1', port, 'admin', 'wrong'); bad.skew = cam.skew
try:
    bad.info(); check('a wrong password is refused', False)
except cameras.CamError as e:
    check('a wrong password is refused with a clear text', 'логин или пароль' in str(e), e)

# through the tool (the address guard is switched off for the loopback imitation)
REAL_PRIVATE = cameras.private_ip
cameras.private_ip = lambda ip: True


class FakeStore:
    cfg = {}; events = []

    def bump(self): pass
    def _load(self, n, d): return dict(d)
    def _dump(self, n, d): pass
    def add_event(self, *a): self.events.append(a)


class FakeNet:
    def subnets(self): return []


class FakeApp:
    store = FakeStore(); netscan = FakeNet()


t = cameras.Cameras(FakeApp(), False)
base = {'ip': '127.0.0.1', 'port': port, 'user': 'admin', 'password': 'secret1'}
r = t.op(dict(base, op='login'))
check('login: recorder is recognised by the number of channels', r['kind'] == 'recorder' and r['channels'] == 2 and r['info']['manufacturer'] == 'ACME', r)
r = t.op(dict(base, op='snapshot'))
check('snapshot + RTSP with and without a login', r['image'].startswith('data:image') and r['rtsp'].startswith('rtsp://127.0.0.1') and 'admin:secret1@' in r['rtspAuth'], r)
r = t.op(dict(base, op='set_password', new='newpass99'))
check('password changed, the camera really holds the new one', STATE['pw'] == 'newpass99' and 'изменён' in r['message'], r)
try:
    t.op(dict(base, op='login')); check('the old password no longer works', False)
except cameras.CamError:
    check('the old password no longer works', True)
base['password'] = 'newpass99'
for bad_new, why in (('abc', 'short'), ('abcdef"<', 'bad characters')):
    try:
        t.op(dict(base, op='set_password', new=bad_new)); check('password refused: ' + why, False)
    except cameras.CamError:
        check('password refused: ' + why, True)
r = t.op(dict(base, op='create_user', name='guest1', new='guestpass'))
check('a user is created', 'создан' in r['message'])
try:
    t.op(dict(base, op='create_user', name='a b', new='guestpass')); check('a bad login name is refused', False)
except cameras.CamError:
    check('a bad login name is refused', True)
r = t.op(dict(base, op='set_ip', mode='dhcp'))
check('DHCP switched on', STATE['dhcp'] and r['dhcp'], r)
r = t.op(dict(base, op='set_ip', mode='static', address='192.168.7.77', prefix=24, gateway='192.168.7.1'))
check('a static address is set', STATE['ip'] == '192.168.7.77' and not STATE['dhcp'] and r['ip'] == '192.168.7.77', (STATE, r))
for kw, why in ((dict(address='192.168.7.0', prefix=24, gateway='192.168.7.1'), 'a network address'), (dict(address='192.168.7.78', prefix=24, gateway='10.1.1.1'), 'a gateway from another network'),
                (dict(address='192.168.7.78', prefix=40, gateway=''), 'a nonsense mask')):
    try:
        t.op(dict(base, op='set_ip', mode='static', **kw)); check('refused: ' + why, False)
    except cameras.CamError:
        check('refused: ' + why, True)
# ── saved passwords, auto login, bulk, where to look ──
creds = t.creds_public()
check('typed passwords were saved into the list; the list never shows a password', len(creds) >= 2 and all('password' not in c for c in creds), creds)
r = t.op({'op': 'login', 'ip': '127.0.0.1', 'port': port})
check('login without typing: the camera\'s own saved password is tried first', r['user'] == 'admin' and r['credId'], r)
cid = r['credId']
r = t.op({'op': 'snapshot', 'ip': '127.0.0.1', 'port': port, 'credId': cid})
check('a saved password works by its id (the browser never holds it)', r['image'].startswith('data:image'))
for i in range(5):
    t.add_cred('admin', 'wrongpass%d' % i)
t.creds['map'].clear()
STATE['pw'] = 'brandnew1'
try:
    t.op({'op': 'login', 'ip': '127.0.0.1', 'port': port}); check('wrong saved passwords: not accepted', False)
except cameras.CamError as e:
    check('at most %d saved passwords per press (cameras lock out), the rest can be tried next' % cameras.MAX_TRIES, 'ни один из %d' % cameras.MAX_TRIES in str(e) and 'следующие' in str(e), e)
r = t.op({'op': 'login', 'ip': '127.0.0.1', 'port': port, 'user': 'admin', 'password': 'brandnew1'})
check('a new typed password is accepted and joins the list', any(c['mask'] for c in t.creds_public()) and any(x['password'] == 'brandnew1' for x in t.creds['items']))
t.del_cred(r['credId'])
check('a password can be removed from the list', not any(x['password'] == 'brandnew1' for x in t.creds['items']))
STATE['pw'] = 'secret1'; STATE['dhcp'] = False
jid = t.bulk_start({'ips': ['127.0.0.1'], 'action': 'set_ip', 'mode': 'dhcp', 'port': port, 'user': 'admin', 'password': 'secret1'})
for _ in range(100):
    if t.jobs[jid]['finished']:
        break
    import time as _t; _t.sleep(.1)
check('a bulk job runs and reports each camera', t.jobs[jid]['finished'] and t.jobs[jid]['results'][0]['ok'] and STATE['dhcp'], t.jobs[jid])
for bad_args, why in (({'ips': [], 'action': 'set_ip'}, 'no cameras'), ({'ips': ['8.8.8.8'], 'action': 'set_ip', 'mode': 'dhcp'}, 'a public address'), ({'ips': ['192.168.7.2'], 'action': 'format'}, 'an unknown action'),
                      ({'ips': ['192.168.7.%d' % i for i in range(2, 50)], 'action': 'set_ip', 'mode': 'dhcp'}, 'more than 40 cameras')):
    cameras.private_ip = REAL_PRIVATE
    try:
        t.bulk_start(bad_args); check('bulk refused: ' + why, False)
    except cameras.CamError:
        check('bulk refused: ' + why, True)
auto = [{'cidr': '192.168.1.0/24'}, {'cidr': '192.168.7.0/24'}, {'cidr': '192.168.7.0/25'}]
nets, err = cameras.parse_targets('', auto)
check('where to look: empty = every known network, an inner network is not scanned twice', [str(n) for n in nets] == ['192.168.1.0/24', '192.168.7.0/24'], (nets, err))
check('where to look: own networks, a list or a text', [str(n) for n in cameras.parse_targets('10.0.0.0/24, 10.0.1.0/24', auto)[0]] == ['10.0.0.0/24', '10.0.1.0/24'] and cameras.parse_targets(['172.16.0.0/24'], auto)[0])
check('where to look: public / nonsense / too much are refused', all(cameras.parse_targets(x, auto)[1] for x in ('8.8.8.0/24', 'abc', '10.0.0.0/22, 10.4.0.0/22, 10.8.0.0/22, 10.12.0.0/22, 10.16.0.0/22')))
from rackd import camera_brands as cb
check('brands: at least 30, the famous ones among them', len(cb.BRANDS) >= 30 and all(n in [b[0] for b in cb.BRANDS] for n in ('Hikvision', 'Dahua', 'Tiandy', 'Tapo (TP-Link)', 'Imou', 'Tracer', 'Reolink', 'EZVIZ', 'Uniview (UNV)')))
check('brands: recognised by what the device says, by ports and by MAC', cb.detect('server: app-webs/', [80])[0] == 'Hikvision' and cb.detect('', [37777])[0] == 'Dahua' and cb.detect('', [2020])[0].startswith('Tapo')
      and cb.detect('', [], '3c:ef:8c:11:22:33')[0] == 'Dahua' and cb.detect('welcome to tiandy web')[0] == 'Tiandy' and cb.detect('ezviz cam')[0] == 'EZVIZ')
pp = plain.server_address[1]
Plain.mode = 'hik'; check('a camera without a name is recognised by its maker\'s path (Hikvision)', cameras.vendor_paths('127.0.0.1', pp) == ('Hikvision', 'hikvision'))
Plain.mode = 'dahua'; check('... Dahua', cameras.vendor_paths('127.0.0.1', pp) == ('Dahua', 'dahua'))
Plain.mode = 'catchall'; check('a device that answers 200 to everything is not judged', cameras.vendor_paths('127.0.0.1', pp) is None)
check('events carry no passwords', not any('newpass99' in str(e) or 'guestpass' in str(e) or 'secret1' in str(e) for e in FakeApp.store.events), FakeApp.store.events)
c = cameras.classify.__doc__ is not None
check('classify() is documented as never logging in', c)
print('\n' + ('ВСЁ OK' if not FAILS else 'ЕСТЬ ОШИБКИ: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
