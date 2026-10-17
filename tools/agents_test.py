"""Plugin «ИИ-агенты»: scripts are valid shell (bash -n), status parsing, input checks, the whole install flow against a fake SSH. Run: python tools/agents_test.py"""
import os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import agents
from rackd.drivers.sshhost import SSHHost
from rackd.util import DriverError

fails = []


def ok(name, cond, extra=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (' — ' + str(extra) if extra and not cond else ''))
    if not cond:
        fails.append(name)


BASH = shutil.which('bash') or next((p for p in (r'C:\Users\Admin\network-tools\bin\git\usr\bin\bash.exe', r'C:\Users\Admin\network-tools\bin\git\usr\bin\sh.exe', r'C:\Program Files\Git\bin\bash.exe') if os.path.exists(p)), None)


def syntax(name, script):
    if not BASH:
        print('  skip ' + name + ' (нет bash)')
        return
    f = tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False, encoding='utf-8', newline='\n')
    f.write(script)
    f.close()
    r = subprocess.run([BASH, '-n', f.name], capture_output=True, text=True)
    os.remove(f.name)
    ok('bash -n: ' + name, r.returncode == 0, r.stderr)


syntax('status', agents.STATUS)
syntax('prereq', agents.PREREQ)
syntax('node', agents.NODE)
syntax('helper', agents.HELPER)
for a in agents.AGENTS:
    syntax('install ' + a['id'], agents.install_script(a))
    syntax('install npm ' + a['id'], agents.install_script(a, via_npm=True)) if a.get('npm') else None
    syntax('remove ' + a['id'], agents.remove_script(a))
cs = agents.configure_script(True, True, 'Мой сервер', 'opus', 'sub', {'OPENAI_API_KEY': 'sk-test_123'}, ['ANTHROPIC_API_KEY'])
syntax('configure', cs)
ok('в скрипте настройки нет ключа Anthropic', 'sk-ant' not in cs)
ok('ключ только в env-файле (heredoc)', cs.count('sk-test_123') == 1)

s = agents.parse_status('@@os Debian GNU/Linux 12\n@@uid 0\n@@tmux tmux 3.3a\n@@bin claude 2.1.300_(Claude_Code)\n@@conf RC 1\n@@conf NAME "Мой сервер"\n'
                        '@@envkey OPENAI_API_KEY\n@@sess rl-main: 1 windows (created Fri)\n@@sess rl-c-Test: 1 windows\n@@cauth Logged in as a@b.c\n@@end\n')
ok('статус: программа и версия', s['bins'].get('claude') == '2.1.300 (Claude Code)', s['bins'])
ok('статус: настройки', s['conf'] == {'RC': '1', 'NAME': 'Мой сервер'}, s['conf'])
ok('статус: сессии и ключи', [x['name'] for x in s['sessions']] == ['rl-main', 'rl-c-Test'] and s['envkeys'] == ['OPENAI_API_KEY'])

for bad in ('a;rm -rf /', 'a$(id)', 'a`id`', 'a"b', "a'b", 'a\nb'):
    try:
        agents.check_text(bad, r'^[\w .\-А-Яа-яЁё]+$', 'имя', 40)
        ok('отклонено: ' + repr(bad), False)
    except ValueError:
        ok('отклонено: ' + repr(bad), True)

# the whole flow against a fake SSH: remembers what was run
class Fake(SSHHost):
    def __init__(self, bins=()):
        self.ran, self.bins = [], set(bins)

    def _run(self, cfg, script, timeout=30):
        self.ran.append(script)
        if script is agents.STATUS:
            return '@@os Debian\n@@uid 0\n' + ''.join(f'@@bin {b} 1.0\n' for b in self.bins) + '@@end\n'
        if 'command -v' in script and 'не появился' in script:
            for a in agents.AGENTS:
                if f'command -v {a["bin"]} ' in script and a['title'] in script:
                    self.bins.add(a['bin'])
        return '@@ok\n'


f = Fake()
res = f.plugin({}, 'agents', 'install', {'agents': ['claude', 'codex'], 'claude': {'rc': True, 'auto': True, 'name': 'VPS 1', 'model': 'opus', 'auth': 'key', 'apiKey': 'sk-ant-zzz'}, 'keys': {'codex': 'sk-openai-1'}, '_progress': lambda s: None})
joined = '\n'.join(f.ran)
ok('установка: готово и нужен вход', res['ok'] and res['needSetup'], res)
ok('с Remote Control ключ Anthropic не пишется', 'sk-ant-zzz' not in joined)
ok('ключ Codex записан', 'sk-openai-1' in joined)
ok('Node.js ставится для Codex', agents.NODE in f.ran)

f = Fake()
f.plugin({}, 'agents', 'install', {'agents': ['claude'], 'claude': {'rc': False, 'auto': False, 'name': 'x', 'auth': 'key', 'apiKey': 'sk-ant-zzz'}, '_progress': lambda s: None})
ok('без Remote Control ключ записан', 'sk-ant-zzz' in '\n'.join(f.ran))
ok('и сессия запущена', any('racklive-agent restart' in r for r in f.ran))

for bad in ({'op': 'new_chat', 'name': 'x; reboot'}, {'op': 'stop', 'session': 'rl-main; id'}, {'op': 'remove', 'agent': 'nope'}, {'op': 'install', 'agents': ['claude'], 'claude': {'model': 'a b'}}):
    try:
        Fake().plugin({}, 'agents', bad.pop('op'), dict(bad, _progress=lambda s: None))
        ok('отклонено: ' + str(bad), False)
    except DriverError:
        ok('отклонено: ' + str(bad), True)

card = Fake(['claude'])._agents_card({})
ok('карточка: список агентов', [a['id'] for a in card['agents']] == ['claude', 'codex', 'gemini', 'opencode', 'aider'] and card['agents'][0]['installed'])

print('\n' + ('ВСЁ OK' if not fails else 'ОШИБКИ: ' + ', '.join(fails)))
sys.exit(1 if fails else 0)
