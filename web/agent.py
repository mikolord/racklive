#!/usr/bin/env python3
"""Rack Live agent: sends CPU, memory, disks, temperature and Docker containers of this Linux host
to a Rack Live server. Standard library only, no open ports needed on this machine.

    python3 racklive-agent.py --server https://rack.example.com --token TOKEN            # run in foreground
    python3 racklive-agent.py --server https://rack.example.com --token TOKEN --install  # install as a systemd service
"""
import argparse, json, os, platform, shutil, socket, ssl, subprocess, sys, time, urllib.request


def read(path, default=''):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def cpu_times():
    parts = read('/proc/stat').splitlines()[0].split()[1:]
    vals = [int(x) for x in parts]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return idle, sum(vals)


def collect(prev):
    idle, total = cpu_times()
    cpu = None
    if prev:
        di, dt = idle - prev[0], total - prev[1]
        cpu = round(100 * (1 - di / dt), 1) if dt else None
    mem = {}
    for l in read('/proc/meminfo').splitlines():
        k, v = l.split(':', 1)
        mem[k] = int(v.split()[0])
    mem_pct = round(100 * (1 - mem.get('MemAvailable', 0) / mem['MemTotal']), 1) if mem.get('MemTotal') else None
    temps = []
    for zone in sorted(os.listdir('/sys/class/thermal')) if os.path.isdir('/sys/class/thermal') else []:
        t = read(f'/sys/class/thermal/{zone}/temp').strip()
        if t.isdigit():
            temps.append(int(t) / 1000)
    vols, seen = [], set()
    for l in read('/proc/mounts').splitlines():
        dev, mnt, fs = l.split()[:3]
        if fs in ('ext4', 'xfs', 'btrfs', 'zfs', 'ext3', 'f2fs', 'vfat', 'ntfs', 'apfs') and dev not in seen and not mnt.startswith(('/snap', '/boot/efi')):
            seen.add(dev)
            try:
                u = shutil.disk_usage(mnt)
                vols.append({'name': mnt, 'status': 'normal' if u.used / u.total < .95 else 'почти заполнен', 'used': u.used, 'total': u.total})
            except OSError:
                pass
    services = []
    if shutil.which('docker'):
        try:
            out = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}\t{{.Status}}'], capture_output=True, text=True, timeout=10).stdout
            services = [{'name': l.split('\t')[0], 'state': l.split('\t')[1]} for l in out.splitlines() if '\t' in l]
        except Exception:
            pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('1.1.1.1', 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        ip = None
    osname = dict(l.split('=', 1) for l in read('/etc/os-release').splitlines() if '=' in l).get('PRETTY_NAME', platform.platform()).strip('"')
    load = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
    status = 'online'
    if any(v['used'] / v['total'] > .95 for v in vols) or (mem_pct or 0) > 95:
        status = 'warning'
    state = {'status': status,
             'summary': {'model': socket.gethostname(), 'fw': osname, 'uptime': int(float(read('/proc/uptime', '0').split()[0])),
                         'cpu': cpu, 'mem': mem_pct, 'temp': round(max(temps)) if temps else None, 'ip': ip},
             'metrics': [{'label': 'Нагрузка', 'value': round(load[0], 2)}],
             'storage': {'volumes': vols, 'disks': []}, 'services': services,
             'sections': [{'title': 'Система', 'rows': [['Ядро', platform.release()], ['Процессоров', os.cpu_count()],
                                                        ['Память', f"{round(mem.get('MemTotal', 0) / 1048576, 1)} ГБ"]]}]}
    return state, (idle, total)


def send(server, token, state, insecure):
    req = urllib.request.Request(server.rstrip('/') + '/api/agent', data=json.dumps(state).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    ctx = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return json.loads(r.read() or b'{}')


def install(args):
    path = os.path.abspath(__file__)
    unit = f"""[Unit]
Description=Rack Live agent
After=network-online.target

[Service]
ExecStart={sys.executable} {path} --server {args.server} --token {args.token}{' --insecure' if args.insecure else ''}
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
"""
    if not shutil.which('systemctl'):
        print('systemd не найден. Запустите агент вручную или добавьте в автозагрузку:')
        print(f'  {sys.executable} {path} --server {args.server} --token {args.token}')
        return
    with open('/etc/systemd/system/racklive-agent.service', 'w') as f:
        f.write(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'racklive-agent'], check=True)
    print('Агент установлен и запущен: systemctl status racklive-agent')


def main():
    ap = argparse.ArgumentParser(description='Rack Live agent')
    ap.add_argument('--server', required=True)
    ap.add_argument('--token', required=True)
    ap.add_argument('--interval', type=int, default=0, help='секунд между отправками (по умолчанию — как на сервере)')
    ap.add_argument('--insecure', action='store_true', help='не проверять HTTPS-сертификат сервера')
    ap.add_argument('--install', action='store_true', help='установить как службу systemd')
    args = ap.parse_args()
    if args.install:
        return install(args)
    prev, interval = None, args.interval or 60
    _, prev = collect(None)
    time.sleep(1)
    while True:
        try:
            state, prev = collect(prev)
            r = send(args.server, args.token, state, args.insecure)
            interval = args.interval or int(r.get('poll') or 60)
        except Exception as e:
            print(time.strftime('%H:%M:%S'), 'ошибка отправки:', e, flush=True)
        time.sleep(interval)


if __name__ == '__main__':
    main()
