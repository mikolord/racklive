"""Any Linux server / VPS over SSH — no agent to install. One POSIX shell script collects everything,
so it works on Debian, Ubuntu, Alpine, CentOS, OpenWrt/BusyBox and Synology alike.

Transport: paramiko when it is installed (dev machines), otherwise the system ssh client
(+ sshpass for passwords) — the Docker image ships openssh-client and sshpass.
"""
import os, re, shlex, shutil, subprocess, tempfile

from . import Driver, FIELD_PASS
from ..util import DriverError

SCRIPT = r'''
echo @@host; hostname 2>/dev/null || cat /proc/sys/kernel/hostname
echo @@os; ( . /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" ) || ( . /etc.defaults/VERSION 2>/dev/null && echo "Synology DSM $productversion" ) || uname -o; uname -r
echo @@uptime; cat /proc/uptime
echo @@load; cat /proc/loadavg
echo @@nproc; nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo
echo @@stat1; head -1 /proc/stat; sleep 1; echo @@stat2; head -1 /proc/stat
echo @@mem; cat /proc/meminfo
echo @@temp; cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null
echo @@mounts; cat /proc/mounts
echo @@df; df -P 2>/dev/null
echo @@docker; docker ps -a --format '{{.Names}}\t{{.Status}}' 2>/dev/null
echo @@ip; hostname -I 2>/dev/null || ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}'
echo @@end
'''
REAL_FS = ('ext4', 'ext3', 'ext2', 'xfs', 'btrfs', 'zfs', 'f2fs', 'vfat', 'ntfs', 'ntfs3', 'apfs', 'jfs', 'reiserfs')


def _sections(out):
    sec, cur = {}, None
    for l in out.splitlines():
        if l.startswith('@@'):
            cur = l[2:].strip()
            sec[cur] = []
        elif cur:
            sec[cur].append(l)
    return sec


class SSHHost(Driver):
    id = 'ssh'
    title = 'Сервер / VPS по SSH'
    kind = 'server'
    description = 'Любой Linux-сервер или VPS: процессор, память, диски, температура, Docker. Ничего ставить на сервер не нужно — нужен только SSH.'
    fields = [{'name': 'host', 'label': 'Адрес (IP или домен)', 'type': 'text', 'required': True},
              {'name': 'sshPort', 'label': 'Порт SSH', 'type': 'text', 'default': '22'},
              {'name': 'username', 'label': 'Пользователь', 'type': 'text', 'default': 'root'},
              dict(FIELD_PASS, hint='Пароль или ключ — что-то одно'),
              {'name': 'privateKey', 'label': 'Приватный ключ (вместо пароля)', 'type': 'textarea', 'secret': True,
               'hint': 'Содержимое файла id_ed25519 / id_rsa целиком. Надёжнее пароля.'}]
    actions = [{'id': 'container_restart', 'label': 'Перезапустить контейнер', 'scope': 'service', 'confirm': 'Перезапустить контейнер {name}?'},
               {'id': 'reboot', 'label': 'Перезагрузить сервер', 'scope': 'device', 'confirm': 'Сервер перезагрузится, всё на нём будет недоступно 1–3 минуты. Продолжить?'}]

    # ── transport ──
    def _run(self, cfg, script, timeout=30):
        host, port = cfg['host'].strip(), int(cfg.get('sshPort') or 22)
        user = cfg.get('username') or 'root'
        key, pw = (cfg.get('privateKey') or '').strip(), cfg.get('password') or ''
        try:
            import paramiko
        except ImportError:
            paramiko = None
        if paramiko:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                pkey = None
                if key:
                    import io
                    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
                        try:
                            pkey = cls.from_private_key(io.StringIO(key + '\n'))
                            break
                        except Exception:
                            pass
                    if not pkey:
                        raise DriverError('не удалось прочитать приватный ключ')
                c.connect(host, port=port, username=user, password=pw or None, pkey=pkey, timeout=12, banner_timeout=12,
                          auth_timeout=12, look_for_keys=False, allow_agent=False)
                i, o, e = c.exec_command('sh -s', timeout=timeout)
                i.write(script)
                i.channel.shutdown_write()
                return o.read().decode('utf-8', 'replace')
            except paramiko.AuthenticationException:
                raise DriverError('SSH: неверный логин, пароль или ключ')
            except DriverError:
                raise
            except Exception as ex:
                raise DriverError(f'SSH: {ex}')
            finally:
                c.close()
        if not shutil.which('ssh'):
            raise DriverError('в системе нет ssh-клиента')
        args = ['ssh', '-p', str(port), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'ConnectTimeout=12', '-o', 'LogLevel=ERROR', '-o', 'ServerAliveInterval=10']
        env, keyfile = dict(os.environ), None
        try:
            if key:
                fd, keyfile = tempfile.mkstemp()
                with os.fdopen(fd, 'w') as f:
                    f.write(key.replace('\r\n', '\n') + '\n')
                os.chmod(keyfile, 0o600)
                args += ['-i', keyfile, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes']
            elif pw:
                if not shutil.which('sshpass'):
                    raise DriverError('для входа по паролю нужен sshpass — или используйте ключ')
                env['SSHPASS'] = pw
                args = ['sshpass', '-e'] + args + ['-o', 'PubkeyAuthentication=no']
            else:
                args += ['-o', 'BatchMode=yes']
            args += [f'{user}@{host}', 'sh -s']
            r = subprocess.run(args, input=script, capture_output=True, text=True, timeout=timeout, env=env)
            if r.returncode == 255 or (r.returncode and not r.stdout):
                err = (r.stderr or '').strip().splitlines()
                msg = err[-1] if err else f'код {r.returncode}'
                if 'denied' in msg.lower() or r.returncode == 5:
                    msg = 'неверный логин, пароль или ключ'
                raise DriverError('SSH: ' + msg)
            return r.stdout
        except subprocess.TimeoutExpired:
            raise DriverError('SSH: сервер не ответил вовремя')
        finally:
            if keyfile:
                try:
                    os.remove(keyfile)
                except OSError:
                    pass

    # ── poll ──
    def poll(self, cfg):
        s = _sections(self._run(cfg, SCRIPT))
        if 'end' not in s:
            raise DriverError('сервер ответил не полностью')
        cpu = None
        try:
            a = [int(x) for x in s['stat1'][0].split()[1:]]
            b = [int(x) for x in s['stat2'][0].split()[1:]]
            idle = (b[3] + (b[4] if len(b) > 4 else 0)) - (a[3] + (a[4] if len(a) > 4 else 0))
            tot = sum(b) - sum(a)
            cpu = round(100 * (1 - idle / tot), 1) if tot else None
        except Exception:
            pass
        mem = {}
        for l in s.get('mem', []):
            if ':' in l:
                k, v = l.split(':', 1)
                try:
                    mem[k] = int(v.split()[0])
                except (ValueError, IndexError):
                    pass
        avail = mem.get('MemAvailable', mem.get('MemFree', 0) + mem.get('Buffers', 0) + mem.get('Cached', 0))
        mem_pct = round(100 * (1 - avail / mem['MemTotal']), 1) if mem.get('MemTotal') else None
        temps = [int(t) / 1000 for t in s.get('temp', []) if t.strip().isdigit() and 0 < int(t) < 150000]
        # real filesystems from /proc/mounts, sizes from df -P
        real = {}
        for l in s.get('mounts', []):
            p = l.split()
            if len(p) >= 3 and p[2] in REAL_FS and not p[1].startswith(('/snap', '/boot/efi', '/var/lib/docker', '/run', '/tmp')):
                real.setdefault(p[0], p[1])
        vols, seen = [], set()
        for l in s.get('df', [])[1:]:
            p = l.split()
            if len(p) >= 6 and p[0] in real and p[5] == real[p[0]] and p[0] not in seen and p[1].isdigit() and int(p[1]) > 0:
                seen.add(p[0])
                tot, used = int(p[1]) * 1024, int(p[2]) * 1024
                vols.append({'name': p[5], 'status': 'normal' if used / tot < .95 else 'почти заполнен', 'used': used, 'total': tot})
        services = [{'name': l.split('\t')[0], 'state': l.split('\t')[1]} for l in s.get('docker', []) if '\t' in l]
        load = (s.get('load') or ['0 0 0'])[0].split()
        try:
            up = int(float((s.get('uptime') or ['0'])[0].split()[0]))
        except ValueError:
            up = None
        ips = ' '.join(s.get('ip', [])).split()
        os_lines = s.get('os') or []
        os_name = os_lines[0].strip() if os_lines else ''
        kernel = os_lines[1].strip() if len(os_lines) > 1 else '—'
        status = 'online'
        if any(v['used'] / v['total'] > .95 for v in vols) or (mem_pct or 0) > 95:
            status = 'warning'
        ncpu = (s.get('nproc') or ['?'])[0].strip()
        return {'status': status,
                'summary': {'model': (s.get('host') or [''])[0].strip(), 'fw': os_name, 'uptime': up, 'cpu': cpu, 'mem': mem_pct,
                            'temp': round(max(temps)) if temps else None, 'ip': cfg['host'].strip()},
                'metrics': [{'label': 'Нагрузка', 'value': load[0] if load else '—'}],
                'storage': {'volumes': vols, 'disks': []}, 'services': services,
                'sections': [{'title': 'Система', 'rows': [['ОС', os_name or '—'], ['Ядро', kernel], ['Процессоров', ncpu],
                                                          ['Память', f"{round(mem.get('MemTotal', 0) / 1048576, 1)} ГБ" if mem.get('MemTotal') else '—'],
                                                          ['Адреса', ', '.join(ips[:4]) or '—'], ['Подключение', 'SSH, без агента']]}]}

    def action(self, cfg, action_id, params):
        if action_id == 'container_restart':
            name = str(params.get('name') or '')
            if not re.match(r'^[\w.-]+$', name):
                raise DriverError('неверное имя контейнера')
            out = self._run(cfg, f'docker restart {shlex.quote(name)} 2>&1; echo @@rc$?', timeout=90)
            if '@@rc0' not in out:
                raise DriverError((out.split('@@rc')[0].strip() or 'docker не ответил')[:160])
            return f'Контейнер {name} перезапущен'
        if action_id == 'reboot':
            self._run(cfg, '(sleep 1; reboot || sudo -n reboot) >/dev/null 2>&1 &\necho ok', timeout=20)
            return 'Сервер перезагружается'
        return super().action(cfg, action_id, params)
