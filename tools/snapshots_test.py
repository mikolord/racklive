"""«Слепок сервера» (rackd/snapshots.py) without a server: parsing, compatibility, what is copied / kept, storage.
The whole cycle (take → restore with SHA-256 check → a broken archive refused) was run against two throwaway Debian SSH containers."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from rackd import snapshots as S
from rackd.util import DriverError

ok = True
def check(name, cond):
    global ok
    print(('  ok   ' if cond else '  FAIL ') + name)
    ok = ok and bool(cond)

i = S.parse_info('@@id debian\n@@ver 12\n@@arch x86_64\n@@uid 0\n@@used 2.57702e+09\n@@free 1234\n@@docker 3\n@@end\n')
check('объём в научной записи awk читается числом', i['used'] == '2577020000' and i['free'] == '1234' and i['docker'] == '3')
m = {'osId': 'debian', 'osVer': '12', 'arch': 'x86_64', 'os': 'Debian 12'}
check('та же система и процессор — подходит', S.Snapshots.compatible(m, i)[0])
check('другая версия системы — не подходит', not S.Snapshots.compatible(m, dict(i, ver='13'))[0])
check('другой процессор — не подходит', not S.Snapshots.compatible(m, dict(i, arch='aarch64'))[0])
take = S.take_script(True)
check('в слепок не попадают /proc, /sys, /dev, своп', all(f"--exclude={p}" in take for p in ('./proc', './sys', './dev', './swapfile')))
check('контейнеры запускаются обратно даже при ошибке (trap EXIT)', "trap '[ -n \"$RUN\" ] && docker start $RUN" in take)
check('нет несуществующих ключей tar --warning', 'socket-ignored' not in take)
un = S.unpack_script()
check('у нового сервера остаются загрузчик, ядро, диски и сеть', all(f"--exclude={p}" in un for p in ('./boot', './lib/modules', './usr/lib/modules', './etc/fstab', './etc/network', './etc/netplan')))
check('перезагрузка только после успешной распаковки', '[ $rc -le 1 ] &&' in un and un.index('@@rc') < un.index('reboot'))
check('архив проверяется по SHA-256 до распаковки', 'sha256sum' in S.UPLOAD)

with tempfile.TemporaryDirectory() as d:
    s = S.Snapshots(d)
    check('пусто — пустой список', s.list() == [])
    os.makedirs(os.path.join(d, 'snapshots', '20261102abcd1234'))
    with open(os.path.join(d, 'snapshots', '20261102abcd1234', 'meta.json'), 'w') as f:
        json.dump({'id': '20261102abcd1234', 't': 1}, f)
    check('недокачанный слепок (нет архива) не показывается', s.list() == [])
    open(os.path.join(d, 'snapshots', '20261102abcd1234', 'root.tar.gz'), 'wb').close()
    check('готовый слепок в списке', [x['id'] for x in s.list()] == ['20261102abcd1234'])
    try:
        s.delete('../../etc')
        check('чужой путь при удалении отклоняется', False)
    except DriverError:
        check('чужой путь при удалении отклоняется', True)
    s.delete('20261102abcd1234')
    check('слепок удаляется', s.list() == [])

print('\nВСЁ OK' if ok else '\nЕСТЬ ОШИБКИ')
sys.exit(0 if ok else 1)
