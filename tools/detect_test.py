"""Auto-detect must not take a camera («answers 200 to everything», echoes requests) for a router. Run: python tools/detect_test.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import detect

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:200] if extra and not cond else ''))
    if not cond:
        fails.append(name)


orig = detect._http


def run(fake):
    detect._http = fake
    try:
        return detect.p_openwrt('10.0.7.5')
    finally:
        detect._http = orig


# a camera whose web server echoes the JSON it receives, and returns a page that merely mentions «luci»
echo = lambda url, data=None, timeout=3: (200, {}, json.dumps(data) if data is not None else '<html>Welcome to the IP camera. gluciose?</html>')
ok('камера, повторяющая запрос, не OpenWrt', run(echo) is None, run(echo))
anything = lambda url, data=None, timeout=3: (200, {}, '<html><title>IPC</title> luci </html>')
ok('камера «200 на всё» со словом luci — не OpenWrt', run(anything) is None)
real = lambda url, data=None, timeout=3: (200, {}, '{"jsonrpc":"2.0","id":1,"result":[6]}') if data is not None else (200, {}, '')
ok('настоящий ubus узнаётся', (run(real) or {}).get('driver') == 'openwrt')
luci = lambda url, data=None, timeout=3: (200, {}, '<link rel="stylesheet" href="/luci-static/bootstrap/cascade.css">') if data is None else (404, {}, '')
ok('настоящий LuCI узнаётся', (run(luci) or {}).get('driver') == 'openwrt')

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
