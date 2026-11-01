"""Контейнерные приложения (rackd/capps.py): проверка описания app.json — что принимается, что отклоняется и что показывается администратору.
Run: python tools/capps_test.py   (prints ВСЁ OK)"""
import copy, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import capps

N, BAD = 0, []


def check(name, ok, extra=''):
    global N
    N += 1
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok or not extra else ' — ' + str(extra)[:300]))
    if not ok:
        BAD.append(name)


DIG = 'a' * 64
GOOD = {
    'app_api': 1, 'id': 'uptime-kuma', 'title': 'Uptime Kuma', 'description': 'Мониторинг сайтов и служб', 'version': '1.23.16', 'home': 'https://github.com/louislam/uptime-kuma',
    'license': 'MIT', 'author': 'Louis Lam', 'targets': ['ssh', 'synology'],
    'fields': [{'id': 'tz', 'label': 'Часовой пояс', 'type': 'text', 'default': 'Europe/Moscow'}, {'id': 'music', 'label': 'Папка', 'type': 'path'}],
    'services': {'app': {'image': 'louislam/uptime-kuma@sha256:' + DIG, 'memory': '512m', 'cpus': 1,
                         'ports': [{'container': 3001, 'host': 3001, 'label': 'Веб-интерфейс', 'web': True}],
                         'volumes': [{'name': 'data', 'path': '/app/data'}], 'env': {'TZ': '${RL_P_TZ}'}}},
    'ui': {'mode': 'link', 'service': 'app', 'port': 3001, 'path': '/', 'title': 'Открыть Uptime Kuma'}}


def run(mut=None, files=None):
    m = copy.deepcopy(GOOD)
    if mut:
        mut(m)
    f = {'app.json': json.dumps(m).encode()} if files is None else files
    return capps.check(f)


def refused(name, mut, word=None):
    e, w, m = run(mut)
    check(name, m is None and e and (word is None or any(word in x for x in e)), e)


e, w, m = run()
check('хорошее приложение принимается', m is not None and not e, e)
check('уровень риска «низкий», разрешения в словах', m and m['risk'] == 'low' and any('3001/tcp' in p for p in m['permissions']), m and (m['risk'], m['permissions']))
check('есть отпечаток, файл compose и подсказка про роутер', m and len(m['digest']) == 16 and m['compose'].startswith('name: rl-uptime-kuma') and 'роутер' in m['expose_note'])
cp = m['compose']
check('compose: предел памяти, cap_drop ALL, no-new-privileges, том приложения и порт', 'mem_limit: 512m' in cp and 'cap_drop: [ALL]' in cp and 'no-new-privileges:true' in cp and '"data:/app/data"' in cp and 'cpus' not in cp and '"3001:3001/tcp"' in cp, cp)
check('compose: переменная из поля подставляется как ${RL_P_TZ}', 'TZ: "${RL_P_TZ}"' in cp)
check('compose: ни privileged, ни host-сети, ни docker.sock', not any(x in cp for x in ('privileged', 'network_mode', 'docker.sock', 'pid:', 'ipc:')))
e2, w2, m2 = run()
check('отпечаток стабилен', m2['digest'] == m['digest'])
e3, w3, m3 = run(lambda x: x['services']['app'].update(memory='768m'))
check('любое изменение запуска меняет отпечаток', m3 and m3['digest'] != m['digest'])

# --- что отклоняется ---
refused('образ без хеша (latest) отклоняется', lambda x: x['services']['app'].update(image='louislam/uptime-kuma:latest'), 'хешу')
refused('образ с тегом и хешем не из списка реестров отклоняется', lambda x: x['services']['app'].update(image='evil.example.com/x/y@sha256:' + DIG), 'реестр')
refused('привилегированный режим отклоняется', lambda x: x['services']['app'].update(privileged=True), 'privileged')
refused('network_mode host отклоняется', lambda x: x['services']['app'].update(network_mode='host'), 'network_mode')
refused('cap_add (в обход списка) отклоняется', lambda x: x['services']['app'].update(cap_add=['SYS_ADMIN']), 'cap_add')
refused('security_opt отклоняется', lambda x: x['services']['app'].update(security_opt=['seccomp=unconfined']), 'security_opt')
refused('право SYS_ADMIN в caps отклоняется', lambda x: x['services']['app'].update(caps=['SYS_ADMIN']), 'caps')
refused('устройство /dev/sda отклоняется', lambda x: x['services']['app'].update(devices=['/dev/sda']), 'devices')
refused('без предела памяти отклоняется', lambda x: x['services']['app'].pop('memory'), 'памяти')
refused('предел памяти 64g отклоняется', lambda x: x['services']['app'].update(memory='64g'), 'памяти')
e, w, m = run(lambda x: (x['services']['app']['ports'][0].update(host=53), x['ui'].update(port=53)))
check('порт ниже 1024 принимается, но риск «средний» и сказано словами', m and m['risk'] == 'medium' and any('системные порты' in p for p in m['permissions']), e)
refused('порт 0 отклоняется', lambda x: x['services']['app']['ports'][0].update(host=0), 'host')
refused('том docker.sock отклоняется', lambda x: x['services']['app']['volumes'].append({'name': 'sock', 'path': '/var/run/docker.sock'}), 'path')
refused('том /proc отклоняется', lambda x: x['services']['app']['volumes'].append({'name': 'p', 'path': '/proc'}), 'path')
refused('путь с «..» отклоняется', lambda x: x['services']['app']['volumes'].append({'name': 'p', 'path': '/app/../etc'}), 'path')
refused('том и папка одновременно отклоняются', lambda x: x['services']['app']['volumes'].append({'name': 'p', 'field': 'music', 'path': '/m'}), 'name')
refused('папка хоста без поля path в fields отклоняется', lambda x: x['services']['app']['volumes'].append({'field': 'tz', 'path': '/m'}), 'path')
refused('неизвестное поле верхнего уровня отклоняется', lambda x: x.update(post_install='rm -rf /'), 'post_install')
refused('ссылка на несуществующее поле отклоняется', lambda x: x['services']['app']['env'].update(A='${RL_P_NOPE}'), 'NOPE'.lower())
refused('«$» вне ${RL_P_…} в env отклоняется', lambda x: x['services']['app']['env'].update(A='$(id)'), '$')
refused('«$» в command отклоняется', lambda x: x['services']['app'].update(command=['sh', '-c', 'echo $HOME']), 'command')
refused('ui указывает на порт, которого нет', lambda x: x['ui'].update(port=9999), 'web')
refused('ui.mode неизвестный', lambda x: x['ui'].update(mode='iframe'), 'ui')
refused('нет id', lambda x: x.pop('id'), 'id')
refused('неверный app_api', lambda x: x.update(app_api=2), 'app_api')
refused('цель не из списка', lambda x: x.update(targets=['router']), 'targets')
refused('зависимость от несуществующего контейнера', lambda x: x['services']['app'].update(depends_on=['db']), 'depends_on')
refused('два одинаковых порта хоста', lambda x: x['services']['app']['ports'].append({'container': 3002, 'host': 3001}), 'занят')
refused('home не https', lambda x: x.update(home='http://x.ru'), 'https')
refused('системная папка по умолчанию в поле path', lambda x: x['fields'][1].update(default='/etc'), 'системной')
refused('системная папка вложенная (/var/lib)', lambda x: x['fields'][1].update(default='/var/lib/x'), 'системной')
check('нет app.json в архиве', capps.check({'x.txt': b'1'})[2] is None)
check('сломанный JSON', capps.check({'app.json': b'{'})[2] is None)
check('имя файла с «..» в архиве', capps.check({'app.json': json.dumps(GOOD).encode(), '../x': b'1'})[2] is None)

# --- что принимается с повышением риска ---
e, w, m = run(lambda x: x['services']['app'].update(caps=['NET_RAW'], volumes=[{'name': 'data', 'path': '/app/data'}, {'field': 'music', 'path': '/music', 'ro': True}]))
check('чтение папки хоста + NET_RAW = средний риск, оба в разрешениях', m and m['risk'] == 'medium' and any('читает' in p for p in m['permissions']) and any('сырые' in p for p in m['permissions']), m and (m and m['risk'], m['permissions']))
check('compose: папка хоста монтируется только для чтения из поля', m and '"${RL_P_MUSIC}:/music:ro"' in m['compose'], m and m['compose'])
e, w, m = run(lambda x: x['services']['app'].update(volumes=[{'field': 'music', 'path': '/music', 'ro': False}]))
check('запись в папку хоста = высокий риск', m and m['risk'] == 'high' and any('ПИШЕТ' in p for p in m['permissions']), e)
e, w, m = run(lambda x: x['services']['app'].update(caps=['NET_ADMIN'], devices=['/dev/net/tun']))
check('NET_ADMIN и /dev/net/tun = высокий риск', m and m['risk'] == 'high')
e, w, m = run(lambda x: x['ui'].update(mode='embed'))
check('embed принимается, но с предупреждением', m is not None and any('embed' in t for t in w), (e, w))
e, w, m = run(lambda x: (x['services']['app'].update(ports=[{'container': 5000, 'host': 5000}]), x.update(ui={'mode': 'none'})))
check('служба без интерфейса (ui none) принимается', m is not None and m['ui']['mode'] == 'none', e)
e, w, m = run(lambda x: x.pop('ui'))
check('ui не указан = none', m is not None and m['ui']['mode'] == 'none', e)


def two(x):
    x['services']['db'] = {'image': 'postgres@sha256:' + 'b' * 64, 'memory': '256m', 'volumes': [{'name': 'pg', 'path': '/var/lib/postgresql/data'}], 'env': {'POSTGRES_PASSWORD': '${RL_P_TZ}'}}
    x['services']['app']['depends_on'] = ['db']


e, w, m = run(two)
check('приложение из двух контейнеров: depends_on и оба тома', m is not None and 'depends_on: [db]' in m['compose'] and m['compose'].count('pg') >= 2, e)


def cycle(x):
    two(x)
    x['services']['db']['depends_on'] = ['app']


refused('цикл в depends_on отклоняется', cycle, 'зациклен')
refused('больше пяти контейнеров', lambda x: x['services'].update({f's{i}': copy.deepcopy(x['services']['app']) for i in range(6)}), 'services')

# ───────── на устройстве: значения, сценарии, состояние ─────────
import shutil, subprocess, tempfile
e, w, m = run()
for bad_val, name in (("a'b", 'кавычка'), ('a\nb', 'перевод строки'), ('a\\b', 'обратная косая черта')):
    try:
        capps.clean_values(m, {'tz': bad_val}); ok = False
    except ValueError:
        ok = True
    check(f'значение поля: {name} отклоняется (оно попадёт в .env)', ok)
try:
    capps.clean_values(m, {'music': '/etc'}); ok = False
except ValueError as ex:
    ok = 'не системная' in str(ex)
check('поле path: системная папка отклоняется при установке', ok)
check('поле path: обычная папка принимается', capps.clean_values(m, {'music': '/volume1/music'})['RL_P_MUSIC'] == '/volume1/music')
check('значения по умолчанию подставляются', capps.clean_values(m, {})['RL_P_TZ'] == 'Europe/Moscow')

st = capps.parse_states('@@c uptime-kuma|rl-uptime-kuma-app-1|running|Up 2 hours|0.0.0.0:3001->3001/tcp\n@@c pastura-x|c2|exited|Exited (0)|\n@@c bad id|c|running|x|\nmusor')
check('состояния: запущено / остановлено, чужие строки и мусор пропущены', st['uptime-kuma']['state'] == 'running' and st['pastura-x']['state'] == 'stopped' and 'bad id' not in st and len(st) == 2, st)
check('состояния: нет Docker', capps.parse_states('@@nodocker 1').get('_nodocker') is True)
check('сценарий состояний использует .Label (в `docker ps` .Labels — строка, index по ней падает)', '.Label "racklive.app"' in capps.SCRIPT_STATES and 'index .Labels' not in capps.SCRIPT_STATES)


class _D:
    def __init__(self, out):
        self.out = out

    def command(self, cfg, cmd):
        return self.out


try:
    capps.Apps.states({}, _D('failed to execute template: error calling index\n')); ok = False
except RuntimeError as ex:
    ok = 'failed to execute' in str(ex)
check('ошибка Docker при чтении состояния показывается, а не выдаётся за «ничего не установлено»', ok)
check('пустой ответ = ничего не запущено (не ошибка)', capps.Apps.states({}, _D('')) == {})

tmp = tempfile.mkdtemp()
try:
    ap = capps.Apps(tmp)
    r = ap.add(json.dumps(GOOD))
    check('приложение добавляется и читается', r['ok'] and ap.get('uptime-kuma')['digest'] == r['app']['digest'] and len(ap.list()) == 1, r)
    check('публичное описание содержит compose, риск и порты', r['app']['compose'].startswith('name:') and r['app']['risk'] == 'low' and r['app']['ports'][0]['host'] == 3001)
    check('плохое описание не сохраняется', not ap.add('{}')['ok'] and len(ap.list()) == 1)
    check('цель по драйверу', ap.target_of('synology') == 'synology' and ap.target_of('demo_server') == 'ssh' and ap.target_of('keenetic') is None)

    class Drv:
        def __init__(self, reply=''):
            self.reply, self.sent = reply, []

        def command(self, cfg, cmd):
            self.sent.append(cmd)
            return self.reply

    d = {'id': 'n1', 'driver': 'synology', 'name': 'NAS'}
    dg = ap.get('uptime-kuma')['digest']
    drv = Drv('@@c rl-uptime-kuma-app-1|running|Up 3 seconds|0.0.0.0:3001->3001/tcp\n')
    res = ap.run(d, drv, 'uptime-kuma', 'install', {'digest': dg, 'values': {'tz': 'Europe/Moscow'}})
    check('установка: контейнер запущен, состояние running', res['ok'] and res['state'] == 'running', res)
    sc = drv.sent[0]
    check('сценарий установки: compose через base64, .env с правами 600, up -d, закреплённые порты', 'base64 -d > "$D/compose.yml"' in sc and 'umask 077' in sc and 'up -d' in sc and '3001/tcp' in sc, sc[:400])
    for bad_call, name in (({'values': {}}, 'без отпечатка'), ({'digest': 'x' * 16, 'values': {}}, 'с чужим отпечатком')):
        try:
            ap.run(d, Drv(), 'uptime-kuma', 'install', bad_call); ok = False
        except ValueError as ex:
            ok = 'изменилось' in str(ex)
        check(f'установка {name} отклоняется', ok)
    try:
        ap.run({'id': 'r1', 'driver': 'keenetic'}, Drv(), 'uptime-kuma', 'install', {'digest': dg}); ok = False
    except ValueError:
        ok = True
    check('на роутере приложение не ставится', ok)
    try:
        ap.run(d, Drv('@@fail Порт 3001/tcp на устройстве уже занят другой программой\n'), 'uptime-kuma', 'install', {'digest': dg, 'values': {}}); ok = False
    except RuntimeError as ex:
        ok = 'уже занят' in str(ex)
    check('ошибка из сценария (порт занят) показывается человеку', ok)
    try:
        ap.run(d, Drv('Error: pull access denied\n'), 'uptime-kuma', 'install', {'digest': dg, 'values': {}}); ok = False
    except RuntimeError as ex:
        ok = 'не запустилось' in str(ex)
    check('нет контейнеров после установки = ошибка «не запустилось»', ok)
    res = ap.run(d, Drv('@@c rl-uptime-kuma-app-1|exited|Exited (0)|\n'), 'uptime-kuma', 'stop', {})
    check('остановка: состояние stopped', res['state'] == 'stopped', res)
    drv = Drv('@@removed 1\n')
    res = ap.run(d, drv, 'uptime-kuma', 'remove', {'keep_data': False})
    check('удаление с данными: down -v --rmi all, папка приложения удаляется, состояние none', 'down -v --rmi all' in drv.sent[0] and 'rm -rf "$D"' in drv.sent[0] and res['state'] == 'none', drv.sent[0][-300:])
    drv = Drv('@@removed 1\n')
    ap.run(d, drv, 'uptime-kuma', 'remove', {'keep_data': True})
    check('удаление без данных: тома остаются (нет -v)', 'down 2>&1' in drv.sent[0] and ' -v' not in drv.sent[0].split('down', 1)[1].split('\n')[0])
    ap.remove('uptime-kuma')
    check('описание удаляется', ap.get('uptime-kuma') is None and not ap.list())

    # настоящий запуск сценариев в sh с подставным docker: синтаксис и порядок действий
    sh = next((p for p in (r'C:\Users\Admin\network-tools\bin\git\usr\bin\sh.exe', '/bin/bash', '/bin/sh') if os.path.isfile(p)), None)
    sh_ok = bool(sh) and subprocess.run([sh, '-c', 'for c in mkdir tail sleep rm grep awk; do command -v $c >/dev/null || exit 1; done'], capture_output=True).returncode == 0      # MinGit's sh has no coreutils
    if sh_ok:
        stub = os.path.join(tmp, 'bin'); os.makedirs(stub)
        log = os.path.join(tmp, 'docker.log')
        open(os.path.join(stub, 'docker'), 'w', newline='\n').write(
            '#!/bin/sh\necho "$@" >> "' + log.replace('\\', '/') + '"\n'
            'case "$1 $2" in "compose version") echo v2;; "ps -a") case "$*" in *"-q"*) ;; *) echo "@@c rl-uptime-kuma-app-1|running|Up 1 second|";; esac;; esac\nexit 0\n')
        open(os.path.join(stub, 'base64'), 'w', newline='\n').write('#!/bin/sh\nexec python -c "import sys,base64;sys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.read()))"\n')       # MinGit has no base64
        base = os.path.join(tmp, 'apps').replace('\\', '/')
        envp = dict(os.environ, PATH=stub.replace('\\', '/') + os.pathsep + os.environ['PATH'], RL_APPS_BASE=base)
        m1 = capps.check({'app.json': json.dumps(GOOD).encode()})[2]
        scr = capps.script_install(m1, capps.clean_values(m1, {'tz': 'Europe/Moscow'}))
        r = subprocess.run([sh, '-c', scr], env=envp, capture_output=True, text=True, encoding='utf-8')
        d_ = os.path.join(tmp, 'apps', 'uptime-kuma')
        dlog = open(log).read() if os.path.isfile(log) else ''
        check('сценарий установки выполняется в sh: файлы записаны, docker compose up вызван', r.returncode == 0 and os.path.isfile(os.path.join(d_, 'compose.yml')) and 'up -d --remove-orphans' in dlog and '@@c rl-uptime-kuma-app-1|running' in r.stdout, (r.stdout[-300:], r.stderr[-300:], dlog))
        check('записанный compose = показанному администратору', open(os.path.join(d_, 'compose.yml'), encoding='utf-8').read() == m1['compose'])
        envtxt = open(os.path.join(d_, '.env'), encoding='utf-8').read()
        check('.env содержит значения полей в одинарных кавычках', "RL_P_TZ='Europe/Moscow'" in envtxt, envtxt)
        scr = capps.script_op(m1, 'remove', False)
        r = subprocess.run([sh, '-c', scr], env=envp, capture_output=True, text=True, encoding='utf-8')
        check('сценарий удаления выполняется: папка приложения исчезла, @@removed выведен', r.returncode == 0 and not os.path.isdir(d_) and '@@removed 1' in r.stdout and 'down -v --rmi all' in open(log).read(), (r.stdout[-200:], r.stderr[-200:]))
        r = subprocess.run([sh, '-c', capps.script_op(m1, 'start')], env=envp, capture_output=True, text=True, encoding='utf-8')
        check('запуск несуществующего приложения даёт @@fail, а не падение', '@@fail' in r.stdout, r.stdout)
    else:
        print('  --   нет sh — запуск сценариев пропущен')
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# --- свои порты, проверка занятости ---
def _raises(f, word):
    try:
        f()
    except ValueError as x:
        return word in str(x)
    return False


_, _, mp = run(lambda x: x['services']['app']['ports'].append({'container': 9999, 'host': 9999, 'proto': 'udp', 'label': 'Служебный', 'fixed': True}))
k = 'app:3001/tcp'
m5 = capps.apply_ports(mp, {k: 3555})
check('свой порт: в compose новый хост-порт, порт контейнера прежний', '"3555:3001/tcp"' in m5['compose'] and '"3001:3001/tcp"' not in m5['compose'], m5['compose'])
check('свой порт: исходное описание не изменилось', mp['services']['app']['ports'][0]['host'] == 3001)
check('порт «менять нельзя» не меняется', _raises(lambda: capps.apply_ports(mp, {'app:9999/udp': 9000}), 'менять нельзя'))
check('порт вне диапазона и не число отклоняются', _raises(lambda: capps.apply_ports(mp, {k: 70000}), 'от 1 до 65535') and _raises(lambda: capps.apply_ports(mp, {k: 'abc'}), 'число'))
check('неизвестный порт отклоняется', _raises(lambda: capps.apply_ports(mp, {'app:1/tcp': 5}), 'не найден'))
check('в публичном описании у порта есть ключ, а у ui — порт контейнера', capps.Apps.public(mp)['ports'][0]['key'] == k and capps.Apps.public(mp)['ui']['cport'] == 3001)
scr = capps.script_ports(mp)
check('сценарий проверки читает /proc/net, без ss', '/proc/net/' in capps.PRELUDE and 'ss ' not in scr and '@@listen' in scr)
out = '@@listen tcp 22 80 3001 \n@@listen udp 5353 \n@@d plex|0.0.0.0:3555->32400/tcp, :::3555->32400/tcp\n@@d other|9999/udp\n'
r = capps.parse_ports(out, [(3001, 'tcp', 'a'), (3555, 'tcp', 'b'), (9999, 'udp', 'c'), (4000, 'tcp', 'd')])['ports']
check('занятый порт найден, свободный нет', [x['busy'] for x in r] == [True, True, False, False], r)
check('занят контейнером: известно, каким', r[1]['by'] == 'plex', r[1])
check('для занятого предложен ближайший свободный (не из выбранных)', r[0]['free'] == 3002 and r[1]['free'] == 3556, r)
check('приложение уже установлено: порты не проверяются', capps.parse_ports('@@installed 1\n', [(1, 'tcp', 'a')]) == {'installed': True, 'ports': []})
st = capps.parse_states('@@c uptime-kuma|rl-uptime-kuma-app-1|running|Up 2 minutes|0.0.0.0:3555->3001/tcp, :::3555->3001/tcp\n')
check('состояние: видны порты, которые приложение получило на самом деле', st['uptime-kuma']['ports'] == [{'host': 3555, 'container': 3001, 'proto': 'tcp'}], st)

print('\n' + ('ВСЁ OK' if not BAD else 'ОШИБКИ: ' + ', '.join(BAD)) + f'  (проверок: {N})')
sys.exit(1 if BAD else 0)
