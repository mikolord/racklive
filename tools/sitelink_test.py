"""The control channel of remote sites: framing, requests, terminal streams, permission levels, a real pty session (Linux only). Run: python tools/sitelink_test.py  (the pty part: in the Docker image)"""
import base64, json, os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)) if os.path.isfile(globals().get('__file__', '')) else '/app/tools', '..'))
from rackd import sitelink, terminal, collector

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


# framing: what a client sends, the server-side reader understands (masked), also big ones
for n in (0, 5, 125, 126, 70000):
    msg = os.urandom(n)
    got = terminal.Reader().feed(sitelink.client_frame(msg, 2))
    ok(f'кадр клиента {n} байт: туда и обратно', got == [(2, msg)])

# a Link against a fake collector over a socket pair
a, b = socket.socketpair()
link = sitelink.Link(a, {'id': 'x', 'name': 'Тест'})
th = threading.Thread(target=link.run, daemon=True)
th.start()
rd = terminal.Reader()


def site_send(obj):
    b.sendall(sitelink.client_frame(json.dumps(obj).encode(), 1))


def site_recv(timeout=3):
    b.settimeout(timeout)
    while True:
        data = b.recv(65536)
        for op, payload in rd.feed(data):
            if op == 1:
                return json.loads(payload)


site_send({'t': 'hello', 'version': '9.9', 'level': 'actions'})
site_send({'t': 'ping'})
ok('центр отвечает на ping', site_recv() == {'t': 'pong'})
time.sleep(.2)
ok('приветствие запомнено', link.caps == {'level': 'actions', 'version': '9.9'}, link.caps)

res = {}
t = threading.Thread(target=lambda: res.update(v=link.request('state', {'key': 'k1'})))
t.start()
req = site_recv()
ok('запрос дошёл до площадки', req['t'] == 'req' and req['op'] == 'state' and req['args'] == {'key': 'k1'})
site_send({'t': 'res', 'id': req['id'], 'result': {'ok': 1}})
t.join(3)
ok('ответ вернулся тому, кто спрашивал', res.get('v') == {'ok': 1})

err = {}
def ask_err():
    try:
        link.request('action', {})
    except Exception as e:
        err['e'] = str(e)
t = threading.Thread(target=ask_err); t.start()
req = site_recv(); site_send({'t': 'res', 'id': req['id'], 'error': 'владелец площадки разрешил только: смотреть'})
t.join(3)
ok('отказ площадки приходит как понятная ошибка', 'разрешил только' in err.get('e', ''), err)
try:
    link.request('x', {}, timeout=.4); ok('молчание площадки → таймаут', False)
except TimeoutError:
    ok('молчание площадки → таймаут', True)
site_recv()                                                  # the request that nobody answered is still in the pipe

sid, qs = link.open_stream('dev1', 100, 30)
op = site_recv()
ok('терминал: запрос открытия дошёл', op['t'] == 'term_open' and op['dev'] == 'dev1' and op['s'] == sid and op['cols'] == 100)
site_send({'t': 'term', 's': sid, 'd': base64.b64encode(b'hello\r\n').decode()})
m = qs.get(timeout=2)
ok('терминал: вывод площадки попал в поток', base64.b64decode(m['d']) == b'hello\r\n')
link.send({'t': 'term', 's': sid, 'd': base64.b64encode(b'ls\r').decode()})
ok('терминал: нажатия ушли на площадку', site_recv()['d'] == base64.b64encode(b'ls\r').decode())
link.close_stream(sid)
ok('терминал: закрытие передано', site_recv()['t'] == 'term_close')

pend = {}
t = threading.Thread(target=lambda: pend.update(e=str(__import__('sys').exc_info()[1])) if False else None)
def ask_then_drop():
    try:
        link.request('state', {}, timeout=10)
    except Exception as e:
        pend['e'] = str(e)
t = threading.Thread(target=ask_then_drop); t.start(); time.sleep(.3)
b.close()                                                   # the site vanishes
t.join(4)
ok('обрыв канала не оставляет вопрос висеть', 'закрыт' in pend.get('e', ''), pend)
time.sleep(.3)
ok('канал помечен закрытым', link.dead)

# levels at the collector (no network needed)
class Store:
    cfg = {'collector': {'level': 'view'}, 'devices': [{'id': 'd1', 'name': 'R', 'driver': 'ping'}, {'id': 's1', 'driver': 'site_node'}]}
    def add_event(self, *a): pass
    def save(self): pass
class App:
    store = Store(); states = {'d1': {'status': 'online', 'clients': [{'mac': 'm'}], 'security': {'x': 1}}}
    def run_action(self, d, a, p): return {'ok': True, 'message': 'сделано'}
c = collector.Collector(App(), '1')
st = c._op('state', {'key': 'd1'})
ok('просмотр разрешён на уровне view, лишние секции убраны', st['state']['clients'] and 'security' not in st['state'] and st['actions'] == [])
for lv, want in (('view', False), ('actions', True), ('terminal', True)):
    App.store.cfg['collector']['level'] = lv
    try:
        c._op('action', {'key': 'd1', 'action': 'x'}); got = True
    except RuntimeError as e:
        got = 'разрешил только' not in str(e)           # reaching «no such action» means the level passed
    ok(f'кнопки на уровне {lv}: {"можно" if want else "нельзя"}', got == want)
try:
    c._op('state', {'key': 's1'}); ok('чужие устройства других площадок не отдаются', False)
except RuntimeError:
    ok('чужие устройства других площадок не отдаются', True)
App.store.cfg['collector']['level'] = 'off'
try:
    c._op('state', {'key': 'd1'}); ok('на уровне off ничего не отдаётся', False)
except RuntimeError:
    ok('на уровне off ничего не отдаётся', True)

# a real shell session on a pty (Linux)
if terminal.supported():
    got, done = [], threading.Event()
    p = terminal.Pty(['/bin/sh', '-c', 'echo привет-из-pty; sleep .3; exit 0'], dict(os.environ, TERM='xterm'), 80, 24, got.append, lambda why: done.set())
    done.wait(5)
    out = b''.join(got).decode('utf-8', 'replace')
    ok('pty: вывод оболочки дошёл', 'привет-из-pty' in out, out)
    ok('pty: сеанс завершился сам', done.is_set() and p.closed)
    got2, done2 = [], threading.Event()
    p2 = terminal.Pty(['/bin/sh'], dict(os.environ, TERM='xterm'), 80, 24, got2.append, lambda why: done2.set())
    p2.write(b'echo $((6*7))\n'); time.sleep(.6); p2.write(b'exit\n'); done2.wait(5)
    ok('pty: ввод доходит, команда выполнена', '42' in b''.join(got2).decode('utf-8', 'replace'))
    p3 = terminal.Pty(['/bin/sh'], dict(os.environ, TERM='xterm'), 80, 24, lambda b_: None, lambda why: None)
    p3.close(); ok('pty: закрытие снимает сеанс', p3.closed and p3.sid not in terminal.KEYS)
else:
    print('  skip pty (не POSIX)')

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
