"""«Слепок сервера»: a whole Linux VPS copied over SSH into Rack Live's data folder, and laid back onto another VPS.

Snapshot = one tar.gz of every real file of the server (system, programs, settings, Docker with its volumes, databases,
sites, certificates, users), streamed over SSH straight into data/snapshots/<id>/root.tar.gz + meta.json.
Optionally the running Docker containers are stopped for the copy (databases are then copied whole), and started again.

Restore onto a server of the same OS (ID + VERSION_ID) and CPU architecture:
  1. the archive is uploaded to /root/.rl-restore/ and its SHA-256 is checked — nothing is touched before that;
  2. it is unpacked over / , keeping the target's own boot loader, kernel modules, disks (fstab) and network settings,
     so the server comes up at its new provider; 3. reboot, and Rack Live waits for SSH with the source's login.
"""
import hashlib, json, os, re, secrets, shlex, shutil, subprocess, threading, time

from .util import DriverError

INFO = r'''. /etc/os-release 2>/dev/null; echo "@@id $ID"; echo "@@ver $VERSION_ID"; echo "@@os $PRETTY_NAME"
echo "@@arch $(uname -m)"; echo "@@uid $(id -u)"; echo "@@host $(hostname 2>/dev/null)"
echo "@@used $(df -kP -x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null | awk 'NR>1 && !seen[$1]++ {s+=$3} END{printf "%.0f", s}')"
echo "@@free $(df -kP / | awk 'NR==2{print $4}')"
echo "@@tar $(tar --version 2>/dev/null | head -1)"
command -v docker >/dev/null 2>&1 && echo "@@docker $(docker ps -q 2>/dev/null | wc -l)"
command -v pigz >/dev/null 2>&1 && echo "@@pigz"
echo @@end
'''

# never copied: kernel views, devices, temporary and removable things, swap, package downloads, our own restore folder
SKIP = ['./proc', './sys', './dev', './run', './tmp', './var/tmp', './mnt', './media', './lost+found', './swapfile', './swap.img',
        './var/swap', './var/cache/apt/archives/*.deb', './var/lib/docker/overlay2/*/merged', './var/log/journal', './root/.rl-restore',
        './snap/*/*/tmp']
# never laid over the target: its boot loader and kernel (+ the matching modules), disks, network, cloud-init, machine identity
KEEP = ['./boot', './lib/modules', './usr/lib/modules', './etc/fstab', './etc/crypttab', './etc/default/grub', './etc/network',
        './etc/netplan', './etc/systemd/network', './etc/NetworkManager/system-connections', './etc/resolv.conf', './etc/cloud',
        './var/lib/cloud', './etc/machine-id', './var/lib/dbus/machine-id', './etc/udev/rules.d/70-persistent-net.rules',
        './etc/initramfs-tools', './etc/kernel']
ID_RE = re.compile(r'^[a-z0-9]{6,24}$')


def parse_info(out):
    s = {}
    for l in out.splitlines():
        k, _, v = l.partition(' ')
        if k.startswith('@@') and k != '@@end':
            s[k[2:]] = v.strip()
    for k in ('used', 'free', 'docker'):                     # numbers in KB / pieces; never trust awk's formatting
        if k in s:
            try:
                s[k] = str(int(float(s[k] or 0)))
            except ValueError:
                s[k] = '0'
    return s


def _excl(paths):
    return ' '.join('--exclude=' + shlex.quote(p) for p in paths)


def take_script(stop_docker):
    """runs on the server (sh -c): the archive goes to stdout, everything else to stderr with @@ markers."""
    return f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужен вход под root" >&2; exit 3; }}
tar --version 2>/dev/null | grep -q GNU || {{ echo "@@fail на сервере нет GNU tar" >&2; exit 3; }}
RUN=""
if [ {1 if stop_docker else 0} = 1 ] && command -v docker >/dev/null 2>&1; then
  RUN=$(docker ps -q 2>/dev/null | tr '\\n' ' ')
  [ -n "$RUN" ] && docker stop -t 30 $RUN >/dev/null 2>&1 && echo "@@stopped $(echo $RUN | wc -w)" >&2
fi
trap '[ -n "$RUN" ] && docker start $RUN >/dev/null 2>&1' EXIT
A=""; tar --help 2>/dev/null | grep -q -- --acls && A="--acls --xattrs --xattrs-include=*"
GZ="gzip -1"; command -v pigz >/dev/null 2>&1 && GZ="pigz -1"
cd / && {{ tar --numeric-owner -cpf - $A --ignore-failed-read --warning=no-file-changed --warning=no-file-removed --warning=no-file-ignored \\
  {_excl(SKIP)} . ; echo "@@tarrc $?" >&2; }} | $GZ
'''


UPLOAD = 'umask 077; mkdir -p /root/.rl-restore && cat > /root/.rl-restore/root.tar.gz && sha256sum /root/.rl-restore/root.tar.gz | sed "s/^/@@sha /"'


def unpack_script():
    return f'''[ "$(id -u)" = 0 ] || {{ echo "@@fail нужен вход под root"; exit 0; }}
[ -f /root/.rl-restore/root.tar.gz ] || {{ echo "@@fail архив не найден на сервере"; exit 0; }}
if command -v docker >/dev/null 2>&1; then R=$(docker ps -q 2>/dev/null); [ -n "$R" ] && docker stop -t 20 $R >/dev/null 2>&1; fi
systemctl stop docker.socket docker containerd >/dev/null 2>&1
A=""; tar --help 2>/dev/null | grep -q -- --acls && A="--acls --xattrs --xattrs-include=*"
cd / && tar --numeric-owner -xpzf /root/.rl-restore/root.tar.gz $A -C / {_excl(KEEP)} 2>/tmp/rl-restore.err
rc=$?
tail -5 /tmp/rl-restore.err
echo "@@rc $rc"
rm -rf /root/.rl-restore
sync
[ $rc -le 1 ] && {{ (sleep 2; reboot || systemctl reboot) >/dev/null 2>&1 & }}
echo @@end
'''


def human(n):
    n = float(n or 0)
    for u in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if n < 1024 or u == 'ТБ':
            return (f'{n:.0f} {u}' if u in ('Б', 'КБ') else f'{n:.1f} {u}').replace('.', ',')
        n /= 1024


class Snapshots:
    def __init__(self, data_dir):
        self.dir = os.path.join(data_dir, 'snapshots')
        self.busy = {}                                        # device id → what is running on it
        self.lock = threading.Lock()

    # ── storage ──
    def _path(self, sid, name=''):
        if not ID_RE.match(str(sid or '')):
            raise DriverError('неверный слепок')
        return os.path.join(self.dir, sid, name) if name else os.path.join(self.dir, sid)

    def list(self):
        out = []
        if not os.path.isdir(self.dir):
            return out
        for sid in os.listdir(self.dir):
            try:
                with open(self._path(sid, 'meta.json'), encoding='utf-8') as f:
                    m = json.load(f)
                if os.path.exists(self._path(sid, 'root.tar.gz')):
                    out.append(m)
            except (OSError, ValueError, DriverError):
                pass
        return sorted(out, key=lambda m: -m.get('t', 0))

    def get(self, sid):
        m = next((m for m in self.list() if m['id'] == sid), None)
        if not m:
            raise DriverError('слепок не найден')
        return m

    def delete(self, sid):
        self.get(sid)
        shutil.rmtree(self._path(sid), ignore_errors=True)

    def free(self):
        os.makedirs(self.dir, exist_ok=True)
        return shutil.disk_usage(self.dir).free

    # ── the card in «Плагины» of an SSH server ──
    def card(self, d, drv):
        st = parse_info(drv._run(d, INFO, 40))
        mine = [m for m in self.list() if m.get('device') == d['id']]
        fits = [dict(m, compatible=self.compatible(m, st)[0], why=self.compatible(m, st)[1]) for m in self.list()]
        used = int(st.get('used') or 0) * 1024
        free = self.free()
        return {'id': 'snapshot', 'kind': 'snapshot', 'title': 'Слепок сервера', 'icon': 'download',
                'description': 'Полная копия этого сервера на Rack Live — и перенос её на другой VPS один в один.',
                'installed': bool(mine), 'server': {'os': st.get('os'), 'arch': st.get('arch'), 'used': used, 'docker': int(st.get('docker') or 0) if 'docker' in st else None,
                                                     'host': st.get('host')},
                'storeFree': free, 'mine': mine, 'all': fits, 'busy': self.busy.get(d['id']),
                'checks': [{'label': 'Вход под root', 'ok': st.get('uid') == '0'},
                           {'label': f"GNU tar на сервере{' (' + st['tar'] + ')' if st.get('tar') else ''}", 'ok': 'GNU' in (st.get('tar') or '')},
                           {'label': f'Место на Rack Live: свободно {human(free)}, на сервере занято {human(used)} (архив обычно в 2–3 раза меньше)',
                            'ok': free > used * 0.6 + 512 * 2 ** 20}]}

    @staticmethod
    def compatible(m, st):
        if m.get('osId') != st.get('id') or m.get('osVer') != st.get('ver'):
            return False, f"на сервере {st.get('os') or '?'}, а слепок с {m.get('os') or '?'} — нужна та же система той же версии"
        if m.get('arch') != st.get('arch'):
            return False, f"другой процессор ({st.get('arch')} вместо {m.get('arch')})"
        return True, ''

    # ── background jobs (server.start_plugin_job → plugin()) ──
    def plugin(self, d, pid, op, params):
        drv, progress = params['_drv'], params.get('_progress') or (lambda s: None)
        with self.lock:
            if self.busy.get(d['id']):
                raise DriverError('с этим сервером уже идёт ' + self.busy[d['id']])
            self.busy[d['id']] = 'снятие слепка' if op == 'take' else 'восстановление'
        try:
            return self.take(d, drv, bool(params.get('stopDocker')), str(params.get('note') or '')[:120], progress) if op == 'take' \
                else self.restore(d, drv, params, progress)
        finally:
            self.busy.pop(d['id'], None)

    def _stream(self, drv, d, remote, *, out=None, inp=None, total=0, label, progress):
        """one ssh call with binary data: stdout → `out` file object, or `inp` file object → stdin. → (stdout text when out is None, stderr text)"""
        args, env, tmp = drv.interactive_args(d, remote)
        args = [a for a in args if a != '-tt']
        err_chunks, done, last = [], [0], [0]
        try:
            p = subprocess.Popen(args, stdin=subprocess.PIPE if inp else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            t_err = threading.Thread(target=lambda: err_chunks.append(p.stderr.read()), daemon=True)
            t_err.start()
            text = b''
            if inp:
                def feed():
                    try:
                        while True:
                            b = inp.read(1 << 20)
                            if not b:
                                break
                            p.stdin.write(b)
                            done[0] += len(b)
                            if time.time() - last[0] > 2:
                                last[0] = time.time()
                                progress(f'{label}: {human(done[0])} из {human(total)} ({done[0] * 100 // max(total, 1)}%)')
                    except (BrokenPipeError, OSError):
                        pass
                    finally:
                        try:
                            p.stdin.close()
                        except OSError:
                            pass
                t_in = threading.Thread(target=feed, daemon=True)
                t_in.start()
                text = p.stdout.read()
                t_in.join()
            else:
                h = hashlib.sha256()
                while True:
                    b = p.stdout.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
                    h.update(b)
                    done[0] += len(b)
                    if time.time() - last[0] > 2:
                        last[0] = time.time()
                        progress(f'{label}: получено {human(done[0])}' + (f' (на сервере занято {human(total)}, архив обычно в 2–3 раза меньше)' if total else ''))
                text = h.hexdigest().encode()
            p.wait()
            t_err.join(5)
            return p.returncode, text.decode('utf-8', 'replace'), b''.join(err_chunks).decode('utf-8', 'replace'), done[0]
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def take(self, d, drv, stop_docker, note, progress):
        if d.get('local'):
            raise DriverError('слепок снимается с другого сервера, не с машины, где работает сам Rack Live')
        progress('Проверяю сервер…')
        st = parse_info(drv._run(d, INFO, 40))
        if st.get('uid') != '0':
            raise DriverError('нужен вход под root')
        if 'GNU' not in (st.get('tar') or ''):
            raise DriverError('на сервере нет GNU tar (apt install tar)')
        used = int(st.get('used') or 0) * 1024
        if self.free() < used * 0.6 + 512 * 2 ** 20:
            raise DriverError(f'на Rack Live мало места: свободно {human(self.free())}, а на сервере занято {human(used)}')
        sid = time.strftime('%Y%m%d') + secrets.token_hex(4)
        folder = self._path(sid)
        os.makedirs(folder, exist_ok=True)
        part = self._path(sid, 'root.tar.gz.part')
        t0 = time.time()
        progress('Останавливаю контейнеры и начинаю копирование…' if stop_docker else 'Начинаю копирование…')
        try:
            with open(part, 'wb') as f:
                os.chmod(part, 0o600)
                rc, sha, err, size = self._stream(drv, d, 'sh -c ' + shlex.quote(take_script(stop_docker)), out=f, total=used, label='Копирую сервер', progress=progress)
            m = re.search(r'@@tarrc (\d+)', err)
            if '@@fail' in err:
                raise DriverError(err.split('@@fail', 1)[1].splitlines()[0].strip())
            if rc != 0 or not m or int(m.group(1)) > 1 or size < 1024 * 1024:
                lines = [l for l in err.splitlines() if l.strip() and not l.startswith('@@')]
                raise DriverError('копирование прервалось' + (': ' + lines[-1][:200] if lines else f' (код {rc})'))
            os.replace(part, self._path(sid, 'root.tar.gz'))
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        stopped = re.search(r'@@stopped (\d+)', err)
        meta = {'id': sid, 'device': d['id'], 'deviceName': d.get('name') or d.get('host'), 'host': d.get('host'), 'hostname': st.get('host'),
                'os': st.get('os'), 'osId': st.get('id'), 'osVer': st.get('ver'), 'arch': st.get('arch'), 't': int(time.time()),
                'size': size, 'used': used, 'sha256': sha, 'dur': round(time.time() - t0), 'stoppedContainers': int(stopped.group(1)) if stopped else 0,
                'note': note}
        with open(self._path(sid, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        return {'ok': True, 'snapshot': meta,
                'message': f'Слепок снят: {human(size)} за {max(1, round(meta["dur"] / 60))} мин' + (f', контейнеров останавливалось: {meta["stoppedContainers"]}' if meta['stoppedContainers'] else '')}

    def restore(self, d, drv, params, progress):
        if d.get('local'):
            raise DriverError('нельзя восстанавливать слепок на машину, где работает сам Rack Live')
        m = self.get(str(params.get('snapshot') or ''))
        src = params.get('_source')                                 # the device the snapshot was taken from (if it is still in Rack Live)
        progress('Проверяю сервер…')
        st = parse_info(drv._run(d, INFO, 40))
        if st.get('uid') != '0':
            raise DriverError('нужен вход под root')
        if 'GNU' not in (st.get('tar') or ''):
            raise DriverError('на сервере нет GNU tar')
        ok, why = self.compatible(m, st)
        if not ok:
            raise DriverError(why)
        need = m['size'] + max(0, m.get('used', 0) - int(st.get('used') or 0) * 1024) + 300 * 2 ** 20
        if int(st.get('free') or 0) * 1024 < need:
            raise DriverError(f"на сервере мало места: свободно {human(int(st.get('free') or 0) * 1024)}, нужно около {human(need)}")
        with open(self._path(m['id'], 'root.tar.gz'), 'rb') as f:
            rc, out, err, _ = self._stream(drv, d, 'sh -c ' + shlex.quote(UPLOAD), inp=f, total=m['size'], label='Загружаю слепок на сервер', progress=progress)
        got = re.search(r'@@sha ([0-9a-f]{64})', out)
        if rc != 0 or not got:
            lines = [l for l in (err or out).splitlines() if l.strip()]
            raise DriverError('загрузка прервалась' + (': ' + lines[-1][:200] if lines else ''))
        if got.group(1) != m['sha256']:
            drv._run(d, 'rm -rf /root/.rl-restore', 30)
            raise DriverError('архив повредился при передаче (контрольная сумма не совпала) — на сервере ничего не изменено, попробуйте ещё раз')
        progress('Раскладываю файлы по серверу (несколько минут, сервер затем перезагрузится)…')
        out = drv._run(d, unpack_script(), timeout=4 * 3600)
        if '@@fail' in out:
            raise DriverError(out.split('@@fail', 1)[1].splitlines()[0].strip())
        rc = re.search(r'@@rc (\d+)', out)
        if not rc or int(rc.group(1)) > 1:
            tail = [l for l in out.splitlines() if l.strip() and not l.startswith('@@')]
            raise DriverError('распаковка завершилась с ошибкой' + (': ' + tail[-1][:200] if tail else '') + '. Сервер не перезагружен — откройте терминал и проверьте')
        # after the reboot the server signs in like the old one: its users, passwords, SSH keys and port came with the snapshot
        login = {k: src.get(k) for k in ('username', 'password', 'privateKey', 'sshPort') if src and src.get(k) is not None} if src else {}
        trial = dict(d, **login)
        progress('Сервер перезагружается — жду, когда он снова ответит по SSH…')
        time.sleep(25)
        back, until = None, time.time() + 480
        while time.time() < until:
            try:
                back = parse_info(drv._run(trial, INFO, 25))
                if back.get('uid'):
                    break
            except DriverError:
                pass
            time.sleep(10)
        upd = dict(login)
        if src and src.get('panelInfo'):
            upd['panelInfo'] = src['panelInfo']
        warn = '' if login else ' Вход на сервер теперь как на старом сервере (тот же пользователь, пароль и ключи) — обновите их в настройках устройства.'
        dns = ' Не забудьте перенаправить домены (A-записи) на новый IP этого сервера.'
        if not back or not back.get('uid'):
            return {'ok': True, 'deviceUpdate': upd, 'message': f'Слепок «{m.get("deviceName")}» разложен, сервер перезагружен, но пока не отвечает по SSH. Подождите пару минут или проверьте консоль хостера.' + warn + dns}
        return {'ok': True, 'deviceUpdate': upd,
                'message': f'Готово: сервер — копия «{m.get("deviceName")}» от {time.strftime("%d.%m.%Y %H:%M", time.localtime(m["t"]))}, снова на связи ({back.get("os")}).' + warn + dns}
