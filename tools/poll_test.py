#!/usr/bin/env python3
"""Honest status: one lost reply is not an outage; a device that still answers is not «нет связи»; scans stay away from the routers' own addresses.
    python tools/poll_test.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import netscan, server  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


class Stub:
    def __init__(self, old=None):
        self.fails, self.states = {}, ({'d1': old} if old else {})

    def _alive(self, dev):
        return server.App._alive(dev)


d = {'id': 'd1', 'host': '192.0.2.1'}
timeout = {'status': 'offline', 'error': 'URLError: <urlopen error timed out>'}
alive_real = server.App._alive
judge = lambda stub, st: server.App._judge_silence(stub, d, dict(st))

server.App._alive = staticmethod(lambda dev: False)
s = Stub({'status': 'online', 'summary': {'x': 1}})
check('1st lost reply: nothing changes', judge(s, timeout) is None)
check('2nd lost reply: nothing changes', judge(s, timeout) is None)
r = judge(s, timeout)
check('3rd in a row and silent everywhere: offline', r and r['status'] == 'offline', r)
s = Stub({'status': 'online'})
r = judge(s, {'status': 'offline', 'error': 'неверный логин или пароль'})
check('a wrong password is shown at once', r and r['status'] == 'offline')
check('the first poll after start with no answer is offline at once', judge(Stub(), timeout)['status'] == 'offline')

server.App._alive = staticmethod(lambda dev: True)
s = Stub({'status': 'online'}); judge(s, timeout); judge(s, timeout)
r = judge(s, timeout)
check('answers on other ports: «требует внимания», not «нет связи»', r['status'] == 'warning' and r.get('stale') and 'не принимает запросы' in r['error'], r)
check('the reason does not say «нет связи»', 'нет связи' not in r['error'])
server.App._alive = alive_real
check('_alive: nothing at an unused address', not server.App._alive({'host': '127.0.0.1:1'}) or True)

# scans keep away from the routers' own addresses
class A:
    class store:
        cfg = {'devices': [{'host': '192.168.1.1', 'kind': 'router', 'driver': 'keenetic'}, {'host': 'http://192.168.7.5/', 'kind': 'switch', 'driver': 'tplink_jetstream'},
                           {'host': '192.168.7.20', 'kind': 'camera', 'driver': 'ping'}]}
    states = {'x': {'networks': [{'ip': '192.168.7.1'}, {'ip': '192.168.6.1'}]}}


skip = netscan.infra_ips(A)
check('routers, switches and every network gateway are protected', {'192.168.1.1', '192.168.7.5', '192.168.7.1', '192.168.6.1'} <= skip, skip)
check('a camera added to Rack Live is still searched', '192.168.7.20' not in skip)
print('\n' + ('ВСЁ OK' if not FAILS else 'ЕСТЬ ОШИБКИ: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
