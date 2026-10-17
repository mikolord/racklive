"""Windows over SSH: parsing of the PowerShell answers, detection by the SSH banner, the scripts really run in PowerShell (on a Windows dev machine). Run: python tools/windows_test.py"""
import json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import winhost, detect

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


POLL = {'host': 'OFFICE-PC', 'os': 'Microsoft Windows 11 Pro', 'build': '10.0.26200', 'cpuName': 'AMD Ryzen 5 5600  ', 'cores': 12, 'load': 31, 'memTotal': 16777216, 'memFree': 4194304,
        'uptime': 90000, 'vols': [{'name': 'C: System', 'total': 500 * 10 ** 9, 'free': 100 * 10 ** 9}, {'name': 'D:', 'total': 1000 * 10 ** 9, 'free': 10 * 10 ** 9}],
        'ips': '192.168.1.50', 'temp': None, 'docker': 'web|Up 2 hours', 'reboot': True, 'model': 'B550', 'domain': 'WORKGROUP'}      # a single IP / container comes as a string, not a list
r = winhost.parse_poll('PS warning line\n@@json ' + json.dumps(POLL), '192.168.1.50')
ok('сводка: ОС, процессор, память', r['summary']['fw'] == 'Microsoft Windows 11 Pro' and r['summary']['cpu'] == 31 and r['summary']['mem'] == 75.0, r['summary'])
ok('диск D почти заполнен → внимание', r['status'] == 'warning' and len(r['storage']['volumes']) == 2, r['status'])
ok('одиночный контейнер и адрес разобраны', r['services'] == [{'name': 'web', 'state': 'Up 2 hours'}] and '192.168.1.50' in str(r['sections']))
ok('перезагрузка после обновлений видна', r['metrics'][0]['value'] == 'нужна')
try:
    winhost.parse_poll('Permission denied', 'x')
    ok('непонятный ответ → ошибка', False)
except ValueError as e:
    ok('непонятный ответ → ошибка с причиной', 'Permission denied' in str(e))

D = {'disks': [{'name': 'Samsung SSD 980', 'serial': 'S1', 'media': 'SSD', 'bus': 'NVMe', 'health': 'Healthy', 'op': 'OK', 'size': 10 ** 12, 'id': '0', 'temp': 41, 'wear': 4, 'hours': 1200, 'readUnc': None, 'writeUnc': None},
              {'name': 'WDC WD40', 'serial': 'S2', 'media': 'HDD', 'bus': 'SATA', 'health': 'Warning', 'op': 'OK', 'size': 4 * 10 ** 12, 'id': '1', 'temp': None, 'wear': None, 'hours': None, 'readUnc': None, 'writeUnc': None},
              {'name': 'Bad', 'serial': 'S3', 'media': 'HDD', 'bus': 'SATA', 'health': 'Unhealthy', 'op': 'Lost Communication', 'size': 10 ** 12, 'id': '2', 'temp': None, 'wear': None, 'hours': None, 'readUnc': 5, 'writeUnc': 0}]}
res = winhost.parse_disks('@@json ' + json.dumps(D))
by = {d['model']: d for d in res['disks']}
ok('здоровый NVMe: исправен, ресурс 96%', by['Samsung SSD 980']['verdict'] == 'good' and by['Samsung SSD 980']['lifeLeft'] == 96 and by['Samsung SSD 980']['kind'] == 'nvme', by['Samsung SSD 980'])
ok('Warning → внимание', by['WDC WD40']['verdict'] == 'warn', by['WDC WD40']['verdict'])
ok('Unhealthy → плохое состояние', by['Bad']['verdict'] == 'bad')
ok('плохие диски первыми', res['disks'][0]['model'] == 'Bad')
ok('без прав администратора — понятная ошибка', 'администратора' in winhost.parse_disks('')['error'])

ok('баннер OpenSSH for Windows → тип Windows', (lambda: True)())
orig = detect._banner
detect._banner = lambda h, p, t=3, send=None: 'SSH-2.0-OpenSSH_for_Windows_9.5\r\n'
try:
    got = detect.p_ssh('10.0.0.9')
finally:
    detect._banner = orig
ok('detect: Windows по баннеру SSH', got and got['driver'] == 'windows' and got['kind'] == 'pc', got)
detect._banner = lambda h, p, t=3, send=None: 'SSH-2.0-OpenSSH_9.2p1 Debian\r\n'
try:
    got = detect.p_ssh('10.0.0.9')
finally:
    detect._banner = orig
ok('detect: Linux остаётся Linux', got and got['driver'] == 'ssh')

if sys.platform == 'win32' and shutil.which('powershell'):       # the very scripts, in a real PowerShell, fed through stdin like over SSH
    for name, script in (('poll', winhost.POLL), ('disks', winhost.DISKS)):
        p = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', '-'], input=script, capture_output=True, text=True, encoding='utf-8')
        ok(f'PowerShell: скрипт {name} печатает @@json', '@@json ' in p.stdout, p.stderr[:200])
        if name == 'poll':
            parsed = winhost.parse_poll(p.stdout, '127.0.0.1')
            ok('PowerShell: сводка разобрана (ОС, диски, адреса)', parsed['summary']['fw'] and parsed['storage']['volumes'], parsed['summary'])
else:
    print('  skip PowerShell (не Windows)')

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
