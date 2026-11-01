"""«Удалённый доступ»: the router-side script must survive a fresh OpenWrt that has no root crontab (it died with code 1 under `set -e`
before the tunnel came up). Builds the real script, checks its syntax with `sh -n` and runs the cron step against a temp directory."""
import os, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import remote

fails = []


def check(name, ok, detail=''):
    print(('  ok   ' if ok else '  FAIL ') + name + (f' — {detail}' if detail and not ok else ''))
    if not ok:
        fails.append(name)


GIT_SH = r'C:\Users\Admin\network-tools\bin\git\usr\bin\sh.exe'
SH = shutil.which('sh') or (GIT_SH if os.path.exists(GIT_SH) else None)

script = remote.apply_script('172.16.6.13', 'A' * 43 + '=', '203.0.113.5', 41495, 'example.test', ['172.16.6.0/24', '192.168.1.3/32'], '192.168.1.1')
check('the script is built', 'rl_wg' in script and 'set -e' in script)
cron = [l for l in script.splitlines() if 'rl-wg-watch' in l and 'crontabs' in l and 'sed -i' in l]
check('the cron step is one line and creates the crontab before sed', len(cron) == 1 and cron[0].index('touch') < cron[0].index('sed -i'), '\n'.join(cron))

if not SH:
    print('  skip sh not found — syntax and cron run skipped')
else:
    d = tempfile.mkdtemp(prefix='rl-cron-')
    try:
        p = os.path.join(d, 'script.sh')
        open(p, 'w', encoding='utf-8', newline='\n').write(script)
        r = subprocess.run([SH, '-n', p], capture_output=True, text=True)
        check('the whole script passes sh -n', r.returncode == 0, r.stderr[:300])
        # the cron step alone, with set -e, on a router that has no /etc/crontabs/root
        root = os.path.join(d, 'etc', 'crontabs')
        step = cron[0].strip().strip('",').replace('/etc/crontabs', root.replace('\\', '/'))
        for _ in range(2):                                           # the second run is the repeat install: still one line
            env = dict(os.environ, PATH=os.path.dirname(SH) + os.pathsep + os.environ.get('PATH', ''))
            r = subprocess.run([SH, '-c', 'set -e\n' + step], capture_output=True, text=True, env=env)
            check('the cron step succeeds with set -e on a fresh router', r.returncode == 0, r.stderr[:300])
        lines = open(os.path.join(root, 'root'), encoding='utf-8').read().splitlines()
        check('exactly one watchdog line after two installs', sum('rl-wg-watch' in x for x in lines) == 1, str(lines))
    finally:
        shutil.rmtree(d, ignore_errors=True)

print('\nВСЁ OK' if not fails else '\nПРОВАЛЫ: ' + ', '.join(fails))
sys.exit(1 if fails else 0)
