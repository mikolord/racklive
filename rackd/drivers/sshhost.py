"""Any Linux server / VPS over SSH — no agent to install. One POSIX shell script collects everything,
so it works on Debian, Ubuntu, Alpine, CentOS, OpenWrt/BusyBox and Synology alike.

Transport: paramiko when it is installed (dev machines), otherwise the system ssh client
(+ sshpass for passwords, or OpenSSH's own SSH_ASKPASS helper when sshpass is missing) — the Docker image ships openssh-client and sshpass.
"""
import json, os, random, re, secrets, shlex, shutil, subprocess, tempfile, time

from . import Driver, FIELD_PASS
from .. import agents, collector_install, hostops, speedtest, vps
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
               {'id': 'iperf', 'label': 'Тест скорости (iperf3)', 'scope': 'device', 'kind': 'speed',
                'confirm': 'Rack Live измерит скорость сети до этого устройства в обе стороны (около 15 секунд). '
                           'На время теста канал будет загружен. На устройстве нужен iperf3. Продолжить?'},
               {'id': 'reboot', 'label': 'Перезагрузить сервер', 'scope': 'device', 'confirm': 'Сервер перезагрузится, всё на нём будет недоступно 1–3 минуты. Продолжить?'}]

    # ── transport ──
    shell = 'shell Linux по SSH (sh): systemctl, docker, journalctl, df, ip …'

    def command(self, cfg, cmd):
        return self._run(cfg, '{\n' + cmd + '\n} 2>&1\n', timeout=180)

    def interactive_args(self, cfg, remote=None):
        """the command line of an interactive `ssh -tt` (for the browser terminal): → (args, env, temp file to delete). Same ways of signing in as _run."""
        if cfg.get('local') and hostops.local_ok():         # «Эта машина»: a login shell right here, no SSH to itself
            env = hostops.local_env()
            env.setdefault('TERM', 'xterm-256color')
            return [shutil.which('bash') or '/bin/sh', '-l'] + (['-c', remote] if remote else []), env, None
        host, port = cfg['host'].strip(), int(cfg.get('sshPort') or 22)
        user = cfg.get('username') or 'root'
        key, pw = (cfg.get('privateKey') or '').strip(), cfg.get('password') or ''
        if not shutil.which('ssh'):
            raise DriverError('в системе нет ssh-клиента')
        args = ['ssh', '-tt', '-p', str(port), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR', '-o', 'ServerAliveInterval=15', '-o', 'ConnectTimeout=12']
        env, keyfile = dict(os.environ), None
        env.setdefault('TERM', 'xterm-256color')
        if key:
            fd, keyfile = tempfile.mkstemp()
            with os.fdopen(fd, 'w') as f:
                f.write(key.replace('\r\n', '\n') + '\n')
            os.chmod(keyfile, 0o600)
            args += ['-i', keyfile, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes']
        elif pw:
            if shutil.which('sshpass'):
                env['SSHPASS'] = pw
                args = ['sshpass', '-e'] + args + ['-o', 'PubkeyAuthentication=no']
            else:
                askdir = os.environ.get('RL_DATA') or None
                if askdir and not os.path.isdir(askdir):
                    askdir = None
                fd, keyfile = tempfile.mkstemp(prefix='rl-ask-', suffix='.sh', dir=askdir)
                with os.fdopen(fd, 'w') as f:
                    f.write('#!/bin/sh\nprintf \'%s\\n\' "$RL_SSH_PW"\n')
                os.chmod(keyfile, 0o700)
                env.update(RL_SSH_PW=pw, SSH_ASKPASS=keyfile, SSH_ASKPASS_REQUIRE='force', DISPLAY=env.get('DISPLAY') or 'rl:0')
                args += ['-o', 'PubkeyAuthentication=no', '-o', 'NumberOfPasswordPrompts=1']
        args += [f'{user}@{host}']
        if remote:
            args.append(remote)                      # a fixed command from a whitelist (server.terminal), not text from the page
        return args, env, keyfile

    def disks(self, cfg):
        """S.M.A.R.T. of every disk (rackd/smart.py)"""
        from .. import smart
        return smart.parse(self._run(cfg, smart.SCRIPT, timeout=90))

    def disk_test(self, cfg, disk, kind):
        from .. import smart
        try:
            return self._run(cfg, smart.test_script(disk, kind), timeout=60).strip() or 'Команда отправлена диску'
        except ValueError as e:
            raise DriverError(str(e))

    def containers(self, cfg, notes=None):
        """Docker in detail: image, ports, addresses, uptime, CPU / memory / traffic (rackd/dockerinfo.py)"""
        from .. import dockerinfo
        return dockerinfo.parse(self._run(cfg, dockerinfo.SCRIPT, timeout=90), cfg['host'].strip(), notes)

    def _run(self, cfg, script, timeout=30, remote='sh -s'):          # remote: what the other side runs to read the script from stdin (Windows: PowerShell, see drivers/windows.py)
        if cfg.get('local') and remote == 'sh -s' and hostops.local_ok():          # «Эта машина»: Rack Live runs right here as root — the script runs directly
            try:
                return hostops.run_local(script, timeout)
            except (OSError, RuntimeError) as e:
                raise DriverError(str(e))
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
                if not pkey and not pw:                         # a fresh OpenWrt: root has no password yet — the server lets us in with «none»
                    t = paramiko.Transport((host, port))
                    t.banner_timeout = 12
                    t.start_client(timeout=12)
                    t.auth_none(user)
                    c._transport = t
                else:
                    c.connect(host, port=port, username=user, password=pw or None, pkey=pkey, timeout=12, banner_timeout=12,
                              auth_timeout=12, look_for_keys=False, allow_agent=False)
                i, o, e = c.exec_command(remote, timeout=timeout)
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
                if shutil.which('sshpass'):                       # the Docker image has it: this path is unchanged
                    env['SSHPASS'] = pw
                    args = ['sshpass', '-e'] + args + ['-o', 'PubkeyAuthentication=no']
                else:
                    # no sshpass (Entware on a Keenetic, a bare OpenWrt): OpenSSH 8.4+ can ask a helper program for the password
                    # (SSH_ASKPASS_REQUIRE=force) — the helper just prints it from the environment, nothing is written to disk but the tiny script
                    askdir = os.environ.get('RL_DATA') or None
                    if askdir and not os.path.isdir(askdir):
                        askdir = None
                    fd, keyfile = tempfile.mkstemp(prefix='rl-ask-', suffix='.sh', dir=askdir)
                    with os.fdopen(fd, 'w') as f:
                        f.write('#!/bin/sh\nprintf \'%s\\n\' "$RL_SSH_PW"\n')
                    os.chmod(keyfile, 0o700)
                    env.update(RL_SSH_PW=pw, SSH_ASKPASS=keyfile, SSH_ASKPASS_REQUIRE='force', DISPLAY=env.get('DISPLAY') or 'rl:0')
                    args += ['-o', 'PubkeyAuthentication=no', '-o', 'NumberOfPasswordPrompts=1']
            else:
                args += ['-o', 'BatchMode=yes']
            args += [f'{user}@{host}', remote]
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
        if action_id == 'iperf':
            return self.iperf(cfg)
        return super().action(cfg, action_id, params)

    def inet_test(self, cfg, iface=None):
        """Internet speed of the server itself (Cloudflare, 4 streams via curl)."""
        from .. import inet
        return inet.parse_curl(self._run(cfg, 'IFACE=""\nBIN=/tmp/rl-bin\n' + inet.CURL_TEST, 180))

    def port_scan(self, cfg, ip, ports):
        """From this (outside) server: which TCP ports of `ip` answer. bash /dev/tcp, nc as a fallback."""
        plist = ' '.join(str(int(p)) for p in ports)
        script = f'''T=""; command -v timeout >/dev/null 2>&1 && T="timeout 3"
for p in {plist}; do
  ( if command -v bash >/dev/null 2>&1; then $T bash -c "</dev/tcp/{ip}/$p" 2>/dev/null; else nc -z -w 3 {ip} $p 2>/dev/null; fi && echo "@@open $p" ) &
done; wait; echo @@end'''
        out = self._run(cfg, script, 90)
        if '@@end' not in out:
            raise DriverError('сервер не завершил проверку портов')
        return sorted({int(l.split()[1]) for l in out.splitlines() if l.startswith('@@open ')})

    # ───────── plugins: 3x-ui / Remnawave (see rackd/vps.py) ─────────
    async_ops = ('install', 'remove')                  # minutes long → the server runs them as background jobs

    def plugins(self, cfg):
        st = vps.parse_status(self._run(cfg, vps.STATUS, 40))
        info = cfg.get('panelInfo') or {}
        mem, root = int(st.get('mem') or 0), st.get('uid') == '0'
        out = []
        for p in vps.CATALOG:
            p = dict(p)
            mine, other = ('xui', 'rw') if p['id'] == '3xui' else ('rw', 'xui')
            p['installed'] = bool(st.get(mine))
            p['version'] = st.get(mine) or None
            p['ip'], p['info'] = st.get('ip'), info.get(p['id'])
            web = {k: v for k, v in st['ports'].items() if k in (80, 443) and 'nginx' not in v}
            need = 1500 if p['id'] == 'remnawave' else 400
            p['checks'] = [{'label': f"Ubuntu или Debian (у вас {st.get('os') or '?'})", 'ok': st.get('id') in ('ubuntu', 'debian')},
                           {'label': 'Вход под root', 'ok': root},
                           {'label': f'Память от {need} МБ (у вас {mem} МБ)', 'ok': mem >= need},
                           {'label': f"Внешний IP определён{': ' + st['ip'] if st.get('ip') else ''}", 'ok': bool(st.get('ip'))},
                           {'label': 'Порты 80 и 443 свободны (или заняты nginx)' + (f" — занято: {', '.join(f'{k} ({v})' for k, v in web.items())}" if web else ''),
                            'ok': not web or p['installed']},
                           {'label': f"Не установлен {'Remnawave' if other == 'rw' else '3x-ui'} — две панели на одном сервере конфликтуют", 'ok': not st.get(other)}]
            out.append(p)
        try:
            out.append(self._agents_card(cfg))
        except DriverError:
            pass
        try:
            if cfg.get('local'):                                            # Rack Live itself runs here: installing it onto itself makes no sense
                raise DriverError('local')
            s = collector_install.parse_status(self._run(cfg, collector_install.STATUS, 40))
            out.append(self._collector_card(cfg, True, s))
            if 'rcos' not in s:                                             # a machine turned into ReckController OS has no use for the plain collector card
                out.append(self._collector_card(cfg, False, s))
        except DriverError:
            pass
        return {'os': st.get('os'), 'ip': st.get('ip'), 'plugins': out}

    # ───────── plugin «Сборщик площадки» (rackd/collector_install.py): a whole Rack Live in collector mode on this server ─────────
    def _collector_card(self, cfg, rcos=False, s=None):
        s = s if s is not None else collector_install.parse_status(self._run(cfg, collector_install.STATUS, 40))
        mem, free = int(s.get('mem') or 0), int(s.get('free') or 0)
        have = 'apt' in s or 'python' in s
        p = dict(collector_install.RCOS_CARD if rcos else collector_install.CARD, installed=bool(s.get('ver')) and (not rcos or 'rcos' in s), version=s.get('ver') or None, active=s.get('active') == 'active', defaultPort=collector_install.DEFAULT_PORT,
                 ip=s.get('ip'), host=s.get('host'))
        p['checks'] = [{'label': f"Debian, Ubuntu, Raspberry Pi OS или другой Linux с systemd (у вас {s.get('os') or '?'})", 'ok': 'systemd' in s},
                       {'label': 'Вход под root', 'ok': s.get('uid') == '0'},
                       {'label': f'Память от 512 МБ (у вас {mem} МБ)', 'ok': mem >= 512},
                       {'label': f'Свободно от 300 МБ (у вас {free} МБ)', 'ok': free >= 300 or p['installed']},
                       {'label': 'Пакеты (python3, ssh, ping, curl) поставятся сами через apt' if 'apt' in s else 'Нет apt: python3, ssh, ping и curl нужно поставить заранее',
                        'ok': have or p['installed'], 'optional': 'apt' not in s}]
        if rcos:
            p['checks'].append({'label': ('Wi-Fi-адаптер виден: ' + s['wifi']) if s.get('wifi') else 'Wi-Fi-адаптер пока не виден — драйверы поставятся при установке; нужен адаптер с режимом точки доступа (AP)', 'ok': bool(s.get('wifi')), 'optional': True})
        return p

    def _collector(self, cfg, op, params, pid='collector'):
        progress = params.get('_progress') or (lambda s: None)
        log = []

        def run(script, timeout):
            body = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', self._run(cfg, script, timeout=timeout))
            for l in (x.strip() for x in body.splitlines()):
                if l and not l.startswith('@@'):
                    log.append({'cmd': l[:220], 'ok': True, 'msg': ''})
            if '@@fail' in body:
                raise DriverError(body.split('@@fail', 1)[1].splitlines()[0].strip())
            return body

        if op == 'remove':
            progress('Удаляю службу и программу с сервера')
            if pid == 'rcos':
                try:
                    run(hostops.AP_FORGET_SCRIPT, 40)
                except DriverError:
                    pass
            run(collector_install.remove_script(bool(params.get('purge'))), 120)
            if pid == 'rcos':
                run(collector_install.RCOS_UNMARK_SCRIPT, 20)
            return {'ok': True, 'log': log, 'removed': pid, 'removeSite': params.get('_site'), 'message': ('ReckController OS' if pid == 'rcos' else 'Сборщик') + ' удалён с сервера' + (' вместе с площадкой' if params.get('_site') else '')}
        if op != 'install':
            raise DriverError('неизвестное действие')
        c = params.get('_collector')
        if not c:
            raise DriverError('нет данных для установки')
        rc, warnings, ap_info = (params.get('_rcos') if pid == 'rcos' else None), [], None
        src = c.get('pack') or c['url']
        if not src:
            raise DriverError('неизвестно, откуда скачивать Rack Live')
        progress('Проверяю, что машина достаёт до этой панели')
        run(collector_install.reach_script(src), 40)                        # first, before anything on the machine is changed
        if rc:                                                              # ReckController OS: time zone, Wi-Fi drivers, our own access point — before the collector, whose config remembers the point
            if rc.get('tz'):
                progress(f"Часовой пояс: {rc['tz']}")
                try:
                    run(hostops.tz_script(rc['tz']), 40)
                except (DriverError, ValueError) as e:
                    warnings.append(f'часовой пояс: {e}')
            progress('Драйверы Wi-Fi и NetworkManager (2–5 минут)')
            try:
                w = hostops.parse_wifi(self._run(cfg, hostops.WIFI_STATUS, 40))
                osid = collector_install.parse_status(self._run(cfg, collector_install.STATUS, 40)).get('id') or 'debian'
                run(hostops.drivers_script(hostops.firmware_packages(w['chips'], osid)), 1500)
                w = hostops.parse_wifi(self._run(cfg, hostops.WIFI_STATUS, 40))
                if rc.get('ap'):
                    ifaces = [i['name'] for i in w['interfaces']]
                    if not ifaces:
                        warnings.append('Wi-Fi-адаптер не виден системе: точка не создана (после перезагрузки её можно создать в Настройки → Сеть → Wi-Fi)')
                    elif w.get('defaultDev') == ifaces[0]:
                        warnings.append(f'через Wi-Fi-адаптер {ifaces[0]} идёт связь машины — точка не создана, чтобы не отрезать её от сети')
                    elif w.get('iw') and not w.get('apCapable'):
                        warnings.append('Wi-Fi-адаптер не умеет работать точкой доступа (нет режима AP) — нужен другой адаптер')
                    else:
                        nets = hostops.nets_of(w['routes'], ifaces[0])
                        address = hostops.check_address(rc.get('address') or hostops.suggest_address(nets), nets)
                        progress(f"Wi-Fi-точка «{rc['ssid']}» ({address})")
                        run(hostops.ap_on_script(ifaces[0], rc['ssid'], rc['password'], address, rc.get('band') or 'bg'), 150)
                        ap_info = {'iface': ifaces[0], 'ssid': rc['ssid'], 'password': rc['password'], 'address': address, 'band': rc.get('band') or 'bg'}
                        c['cfg'].setdefault('dev', {})['ap'] = ap_info
            except (DriverError, ValueError) as e:
                warnings.append(f'Wi-Fi: {e}')
        progress('Ставлю Rack Live на сервер: пакеты, скачивание, запуск (1–4 минуты)')
        body = run(collector_install.install_script(c['url'], c['token'], c['cfg'], c['port'], c.get('insecure'), pack=c.get('pack')), 900)
        if '@@ok' not in body:
            raise DriverError('установка не завершилась: нет подтверждения от сервера')
        ver = next((l[6:].strip() for l in body.splitlines() if l.startswith('@@ver ')), '')
        ip = next((l[5:].strip() for l in body.splitlines() if l.startswith('@@ip ')), '')
        if rc:
            run(collector_install.RCOS_MARK_SCRIPT, 20)
        prev = (cfg.get('panelInfo') or {}).get(pid) or {}
        host = (cfg.get('host') or ip or '').strip()
        info = {'url': f"http://{host}:{c['port']}", 'port': c['port'], 'siteId': c['siteId'], 'siteName': c['siteName'], 'server': c['url'], 'version': ver, 'level': c['level'],
                'password': c['password'] if '@@created 1' in body else prev.get('password'), 't': int(time.time())}
        if rc:
            info.update(rcos=True, warnings=warnings, tz=rc.get('tz') or None)
            if ap_info:
                info['ap'] = dict(ap_info, url=f"http://{ap_info['address'].split('/')[0]}:{c['port']}")
        return {'ok': True, 'log': log, 'info': info,
                'message': (f"ReckController OS готов: панель {info['url']}" + (f", точка «{ap_info['ssid']}», панель в ней {info['ap']['url']}" if ap_info else '') if rc else f"Сборщик установлен: версия {ver}, панель {info['url']}")
                + ('' if '@@created 1' in body else ' (администратор остался прежним)') + (f". Замечания: {'; '.join(warnings)}" if warnings else '')}

    # ───────── plugin «ИИ-агенты» (rackd/agents.py) ─────────
    def _agents_card(self, cfg):
        s = agents.parse_status(self._run(cfg, agents.STATUS, 60))
        root = s.get('uid') == '0'
        conf = s.get('conf') or {}
        p = dict(agents.CATALOG[0])
        p['installed'] = bool(s['bins'])
        p['agents'] = [{k: a[k] for k in ('id', 'title', 'by', 'home')} | {'key': bool(a['key']), 'installed': a['bin'] in s['bins'], 'version': s['bins'].get(a['bin'])} for a in agents.AGENTS]
        p['config'] = {'rc': conf.get('RC') == '1', 'auto': conf.get('AUTO') == '1', 'name': conf.get('NAME') or '', 'model': conf.get('MODEL') or '',
                       'auth': conf.get('AUTH') or 'sub', 'keys': [k for k in s['envkeys'] if k.endswith('_API_KEY')]}
        p['sessions'] = s['sessions']
        p['claudeAuth'] = s.get('cauth') or ''
        p['helper'] = bool(s.get('helper'))
        p['models'] = agents.MODELS
        p['checks'] = [{'label': f"Linux (у вас {s.get('os') or '?'})", 'ok': bool(s.get('os'))},
                       {'label': 'Вход под root (или sudo без пароля — для tmux и Node.js)', 'ok': root, 'optional': True},
                       {'label': f"tmux: {s.get('tmux') or 'будет установлен'}", 'ok': bool(s.get('tmux')), 'optional': True},
                       {'label': f"Node.js 18+ для Codex и Gemini CLI: {s.get('node') or 'будет установлен'}", 'ok': bool(s.get('node')), 'optional': True}]
        return p

    def _agents(self, cfg, op, params):
        progress = params.get('_progress') or (lambda s: None)
        log = []

        def stage(title, script, timeout=900, fatal=True):
            progress(title)
            body = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', self._run(cfg, script, timeout=timeout))
            log.append({'cmd': f'— {title}', 'ok': True, 'msg': ''})
            log.extend({'cmd': l[:220], 'ok': '@@fail' not in l, 'msg': ''} for l in body.splitlines() if l.strip() and not l.startswith('@@ok'))
            if '@@fail' in body and fatal:
                raise DriverError(f"{title}: " + body.split('@@fail', 1)[1].splitlines()[0].strip())
            return body

        try:
            if op == 'new_chat':
                name = agents.check_text(params.get('name'), r'^[\w .\-А-Яа-яЁё]+$', 'имя чата', 40)
                out = self._run(cfg, agents.PATHS + f'\nracklive-agent new {shlex.quote(name)} 2>&1 | tail -3', 30)
                return {'ok': True, 'message': 'Чат запущен' + (': ' + out.strip().splitlines()[-1] if out.strip() else ''), 'log': []}
            if op == 'restart':
                self._run(cfg, agents.PATHS + '\nracklive-agent restart 2>&1 | tail -2', 40)
                return {'ok': True, 'message': 'Сессии перезапущены', 'log': []}
            if op == 'stop':
                s = agents.check_text(params.get('session'), r'^(rl-[\w.\-]+|all)$', 'сессия', 60)
                self._run(cfg, agents.PATHS + f'\nracklive-agent stop {shlex.quote(s)} 2>&1 | tail -2', 20)
                return {'ok': True, 'message': 'Сессия остановлена', 'log': []}
            if op == 'remove':
                a = agents.BY_ID.get(str(params.get('agent') or ''))
                if not a:
                    raise DriverError('неизвестный агент')
                stage(f'Удаление {a["title"]}', agents.remove_script(a), 300)
                return {'ok': True, 'log': log, 'message': f'{a["title"]} удалён'}
            if op not in ('install', 'save'):
                raise DriverError('неизвестное действие')

            want = [i for i in (params.get('agents') or []) if i in agents.BY_ID] if op == 'install' else []
            cl = params.get('claude') or {}
            st = agents.parse_status(self._run(cfg, agents.STATUS, 60))
            have_claude = 'claude' in st['bins'] or 'claude' in want
            if want or have_claude:
                stage('tmux и нужные программы', agents.PREREQ, 600)
            if any(not agents.BY_ID[i].get('install') and agents.BY_ID[i]['bin'] not in st['bins'] for i in want):      # Codex, Gemini CLI come from npm
                stage('Node.js', agents.NODE, 900)
            for i in want:
                a = agents.BY_ID[i]
                if a['bin'] in st['bins'] and not params.get('reinstall'):
                    log.append({'cmd': f'{a["title"]} уже установлен ({st["bins"][a["bin"]]})', 'ok': True, 'msg': ''})
                    continue
                try:
                    stage(f'Установка {a["title"]}', agents.install_script(a), 900)
                except DriverError:
                    if not (a.get('install') and a.get('npm')):
                        raise
                    stage('Node.js', agents.NODE, 900)
                    stage(f'Установка {a["title"]} через npm', agents.install_script(a, via_npm=True), 900)
            msg = ', '.join(agents.BY_ID[i]['title'] for i in want) or 'настройки'
            res = {'ok': True, 'log': log, 'message': f'Готово: {msg}', 'needSetup': False}
            if have_claude:
                rc, auto = bool(cl.get('rc')), bool(cl.get('auto'))
                name = agents.check_text(cl.get('name') or 'server', r'^[\w .\-А-Яа-яЁё]+$', 'имя сессии', 40) or 'server'
                model = agents.check_text(cl.get('model'), r'^[A-Za-z0-9._\-\[\]]+$', 'модель', 60)
                auth = 'key' if (cl.get('auth') == 'key' and not rc) else 'sub'
                keys, strip = {}, []
                if auth == 'key' and cl.get('apiKey'):
                    keys['ANTHROPIC_API_KEY'] = agents.check_text(cl.get('apiKey'), r'^[A-Za-z0-9_\-.]+$', 'ключ Claude', 300)
                elif auth == 'sub':
                    strip.append('ANTHROPIC_API_KEY')                     # a key in the environment would switch Claude Code (and Remote Control) to API billing
                for ident, var in (('codex', 'OPENAI_API_KEY'), ('gemini', 'GEMINI_API_KEY')):
                    v = (params.get('keys') or {}).get(ident)
                    if v:
                        keys[var] = agents.check_text(v, r'^[A-Za-z0-9_\-.]+$', 'ключ ' + ident, 300)
                stage('Настройки, команда racklive-agent и автозапуск', agents.configure_script(rc, auto, name, model, auth, keys, strip), 120)
                if rc:
                    res['needSetup'] = True
                    res['message'] += '. Осталось один раз войти в аккаунт Claude: кнопка «Войти и запустить»'
                elif 'claude' in (st['bins'] or {}) or 'claude' in want:
                    self._run(cfg, agents.PATHS + '\nracklive-agent restart 2>&1 | tail -2', 40)
            else:
                keys = {}
                for ident, var in (('codex', 'OPENAI_API_KEY'), ('gemini', 'GEMINI_API_KEY')):
                    v = (params.get('keys') or {}).get(ident)
                    if v:
                        keys[var] = agents.check_text(v, r'^[A-Za-z0-9_\-.]+$', 'ключ ' + ident, 300)
                if keys:
                    stage('Ключи и команда racklive-agent', agents.configure_script(False, False, 'server', '', 'sub', keys), 60)
            return res
        except ValueError as e:
            raise DriverError(str(e))

    def plugin(self, cfg, pid, op, params):
        if pid == 'agents':
            return self._agents(cfg, op, params)
        if pid in ('collector', 'rcos'):
            return self._collector(cfg, op, params, pid)
        meta = next((p for p in vps.CATALOG if p['id'] == pid), None)
        if not meta:
            raise DriverError('неизвестный плагин')
        progress = params.get('_progress') or (lambda s: None)
        log = []

        def stage(title, script, timeout=900):
            progress(title)
            out = self._run(cfg, script, timeout=timeout)
            body = re.sub(r'\x1b\[[0-9;]*m', '', out)
            log.append({'cmd': f'— {title}', 'ok': True, 'msg': ''})
            log.extend({'cmd': l[:220], 'ok': not re.search(r'@@fail|\berror\b|failed', l, re.I), 'msg': ''}
                       for l in body.splitlines() if l.strip() and not l.startswith(('@@ok', '@@link', '@@url', '@@a ')))
            if '@@fail' in body:
                raise DriverError(f"{title}: " + body.split('@@fail', 1)[1].splitlines()[0].strip())
            return body

        if op == 'dns':
            domain = vps.clean_domain(params.get('domain'))
            if not domain:
                raise DriverError('неверное имя домена')
            ip = params.get('ip') or vps.parse_status(self._run(cfg, vps.STATUS, 40)).get('ip')
            recs = sorted({l[4:].strip() for l in self._run(cfg, vps.dns_script(domain), 20).splitlines() if l.startswith('@@a ')})
            return {'ok': True, 'domain': domain, 'ip': ip, 'records': recs, 'match': bool(ip) and ip in recs}
        if op == 'remove':
            stage(f'Удаление {meta["title"]}', vps.xui_remove() if pid == '3xui' else vps.rw_remove(), 600)
            return {'ok': True, 'log': log, 'removed': pid, 'message': f"{meta['title']} удалён" + ('' if pid == '3xui' else ' (вместе с базой данных)')}
        if op != 'install':
            raise DriverError('неизвестное действие')

        domain = vps.clean_domain(params.get('domain')) if params.get('withDomain') else ''
        if params.get('withDomain') and not domain:
            raise DriverError('укажите домен')
        if meta['needsDomain'] and not domain:
            raise DriverError(f"для {meta['title']} нужен домен")
        inbounds = bool(params.get('inbounds')) and bool(domain)
        st = vps.parse_status(self._run(cfg, vps.STATUS, 40))
        if st.get('uid') != '0':
            raise DriverError('нужен вход под root')
        if st.get('rw' if pid == '3xui' else 'xui'):
            raise DriverError('на сервере уже стоит другая панель — сначала удалите её')
        if domain:
            progress(f'Проверка DNS: {domain} → {st.get("ip")}')
            recs = {l[4:].strip() for l in self._run(cfg, vps.dns_script(domain), 20).splitlines() if l.startswith('@@a ')}
            if st.get('ip') not in recs:
                raise DriverError(f"домен {domain} пока не указывает на {st.get('ip')} — создайте A-запись и подождите")
            stage('nginx, сайт-заглушка и сертификат Let\'s Encrypt', vps.stage_cert(domain), 600)
        links = []
        if pid == '3xui':
            user, pw = vps.rnd(10, 'abcdefghijkmnpqrstuvwxyz23456789'), vps.strong_password(20)
            port, path = 20000 + secrets.randbelow(40000), vps.rnd(16, 'abcdefghijkmnpqrstuvwxyz23456789')
            body = stage('Установка 3x-ui', vps.xui_install(domain, user, pw, port, path), 1200)
            url = f'https://{domain}/{path}/' if domain else next((l[6:].strip().strip("'\"") for l in body.splitlines() if l.startswith('@@url ')),
                                                                     f"https://{st.get('ip')}:{port}/{path}/")
            if inbounds:
                body = stage('Инбаунды VLESS TCP + XHTTP и тестовый пользователь', vps.xui_inbounds(domain, user, pw, port, path, '/' + vps.rnd(12).lower()), 300)
                links = [json.loads(l[7:]) for l in body.splitlines() if l.startswith('@@link ')]
            info = {'url': url, 'user': user, 'password': pw, 'domain': domain or None, 'links': links, 't': int(time.time())}
        else:
            admin, pw, key = 'rl' + vps.rnd(8, 'abcdefghijkmnpqrstuvwxyz23456789'), vps.strong_password(32), vps.rnd(24)
            stage('Docker и панель Remnawave (скачивание образов — несколько минут)', vps.rw_install(domain, key), 1800)
            body = stage('Администратор, нода' + (', инбаунды и тестовый пользователь' if inbounds else ''),
                         vps.rw_setup(domain, admin, pw, inbounds, '/' + vps.rnd(12).lower()), 600)
            links = [json.loads(l[7:]) for l in body.splitlines() if l.startswith('@@link ')]
            info = {'url': f'https://{domain}/?rlkey={key}', 'user': admin, 'password': pw, 'domain': domain, 'links': links,
                    'note': 'Без этой ссылки домен показывает сайт-заглушку — откройте её один раз в каждом браузере.', 't': int(time.time())}
        return {'ok': True, 'log': log, 'info': info, 'message': f"{meta['title']} установлен" + (f' на {domain}' if domain else '')}

    def iperf(self, cfg):
        """iperf3 server on the device (one-off, started over SSH), client in Rack Live: both directions."""
        host, port = cfg['host'].strip(), random.randint(5300, 5399)
        start = (f'command -v iperf3 >/dev/null 2>&1 || {{ echo @@none; exit 0; }}\n'
                 f'iperf3 -s -1 -D -p {port} >/dev/null 2>&1 && echo @@ok\nsleep 1\n')
        res = {}
        try:
            for direction, reverse in (('down', True), ('up', False)):      # down = device → Rack Live
                out = self._run(cfg, start, timeout=20)
                if '@@none' in out:
                    raise DriverError('на устройстве нет iperf3. Установите: apt install iperf3 · opkg install iperf3 (OpenWrt, Entware) · apk add iperf3')
                if '@@ok' not in out:
                    raise DriverError('iperf3 на устройстве не запустился')
                try:
                    res[direction] = speedtest.iperf_client(host, port, reverse)
                except RuntimeError as e:
                    msg = str(e)
                    if 'connect' in msg.lower() or 'refused' in msg.lower():
                        msg = f'не удалось подключиться к iperf3 на {host}:{port} — проверьте firewall устройства'
                    raise DriverError(msg)
        finally:
            try:
                self._run(cfg, f'pkill -f "iperf3 -s -1 -D -p {port}" 2>/dev/null; echo', timeout=15)
            except DriverError:
                pass
        mbit = lambda k: round(res[k]['bps'] / 1e6, 1)
        retr = sum(r.get('retr') or 0 for r in res.values())
        return {'message': f"iperf3 до {host}: к устройству {mbit('up')} Мбит/с, от устройства {mbit('down')} Мбит/с",
                'speedtest': {'down': mbit('down'), 'up': mbit('up'), 'retr': retr, 'host': host}}
