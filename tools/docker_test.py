#!/usr/bin/env python3
"""Docker in detail: the parser against output shaped like the real docker / ss (no Docker needed).
    python tools/docker_test.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import dockerinfo  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


A, B, C = 'a' * 64, 'b' * 64, 'c' * 64
inspect = [
    {'Id': A, 'Name': '/racklive', 'Created': '2026-10-11T12:21:29.1Z', 'RestartCount': 2,
     'Config': {'Image': 'racklive:2', 'Labels': {}, 'Env': ['SECRET=hunter2']},
     'State': {'Status': 'running', 'Running': True, 'StartedAt': '2020-01-17T02:15:23.5Z', 'FinishedAt': '0001-01-01T00:00:00Z', 'Health': {'Status': 'healthy'}},
     'HostConfig': {'NetworkMode': 'host', 'RestartPolicy': {'Name': 'always'}, 'Memory': 0},
     'NetworkSettings': {'Ports': {}, 'Networks': {'host': {'IPAddress': ''}}}, 'Mounts': [{'Type': 'bind', 'Source': '/volume1/docker/racklive/data', 'Destination': '/data', 'RW': True}]},
    {'Id': B, 'Name': '/immich_server', 'Created': '2026-10-01T00:00:00Z', 'RestartCount': 0,
     'Config': {'Image': 'ghcr.io/immich-app/immich-server:release', 'Labels': {'com.docker.compose.project': 'immich', 'com.docker.compose.service': 'server'}},
     'State': {'Status': 'running', 'Running': True, 'StartedAt': '2026-10-08T00:00:00Z', 'FinishedAt': '0001-01-01T00:00:00Z'},
     'HostConfig': {'NetworkMode': 'immich_default', 'RestartPolicy': {'Name': 'unless-stopped'}},
     'NetworkSettings': {'Ports': {'2283/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '2283'}, {'HostIp': '::', 'HostPort': '2283'}], '9999/tcp': None}, 'Networks': {'immich_default': {'IPAddress': '172.19.0.4', 'Gateway': '172.19.0.1'}}}, 'Mounts': []},
    {'Id': C, 'Name': '/old-test', 'Created': '2026-09-01T00:00:00Z', 'RestartCount': 0, 'Config': {'Image': 'nginx:1.25', 'Labels': {'org.opencontainers.image.description': 'NGINX web server'}},
     'State': {'Status': 'exited', 'Running': False, 'StartedAt': '2026-09-01T00:00:00Z', 'FinishedAt': '2026-10-16T10:00:00Z', 'ExitCode': 137, 'OOMKilled': True},
     'HostConfig': {'NetworkMode': 'bridge', 'RestartPolicy': {'Name': 'no'}}, 'NetworkSettings': {'Ports': {}, 'Networks': {}}, 'Mounts': []},
]
stats = [{'ID': A[:12], 'Name': 'racklive', 'CPUPerc': '3.40%', 'MemUsage': '118.5MiB / 7.69GiB', 'MemPerc': '1.50%', 'NetIO': '1.2MB / 3.4kB', 'BlockIO': '5.2MB / 31MB', 'PIDs': '14'},
         {'ID': B[:12], 'Name': 'immich_server', 'CPUPerc': '6.10%', 'MemUsage': '940MiB / 7.69GiB', 'MemPerc': '11.9%', 'NetIO': '2GB / 1GB', 'BlockIO': '0B / 1GB', 'PIDs': '33'}]
out = '\n'.join(['@@ver', '24.0.2', '@@ps', '@@stats'] + [json.dumps(s) for s in stats] + ['@@inspect', json.dumps(inspect), '@@listen',
                 'LISTEN 0 4096 0.0.0.0:9998 0.0.0.0:* users:(("python",pid=4242,fd=5))', 'LISTEN 0 128 [::]:22 [::]:* users:(("sshd",pid=900,fd=3))',
                 '@@cg', '4242 ' + A, '900 ', '@@end'])
r = dockerinfo.parse(out, '192.168.1.3', {'immich_server': 'Фото семьи'})
d = r['docker']; cs = {c['name']: c for c in r['containers']}
check('docker summary: version, counts, total CPU and memory', d['version'] == '24.0.2' and d['total'] == 3 and d['running'] == 2 and d['cpu'] == 9.5 and d['mem'] > 1e9, d)
c = cs['racklive']
check('host-network container: what it listens on is found through the process', c['hostNetwork'] and c['listening'] == [{'addr': '0.0.0.0', 'port': 9998, 'proc': 'python'}], c['listening'])
check('uptime, restarts, policy, health, folders', c['uptime'] > 0 and c['restarts'] == 2 and c['restartPolicy'] == 'always' and c['health'] == 'healthy' and c['mounts'][0]['dst'] == '/data')
check('CPU / memory / traffic / disk / processes are numbers', c['cpu'] == 3.4 and 117e6 < c['mem'] < 125e6 and c['memPct'] == 1.5 and c['netRx'] == 1200000 and c['blkW'] == 31000000 and c['pids'] == 14, c)
i = cs['immich_server']
check('published ports: the host address is filled in, duplicates (IPv4 + IPv6) merged', [(p['host'], p['hostPort'], p['port']) for p in i['ports'] if p['published']] == [('192.168.1.3', 2283, 2283)], i['ports'])
check('an unpublished port is listed as internal only', any(not p['published'] and p['port'] == 9999 for p in i['ports']))
check('docker network and its address', i['networks'] == [{'name': 'immich_default', 'ip': '172.19.0.4', 'gateway': '172.19.0.1'}] and i['project'] == 'immich' and i['service'] == 'server')
check('your own note wins over any guess', i['description'] == 'Фото семьи' and i['descriptionFrom'] == 'ваша заметка')
check('a known image is described by its name', cs['racklive']['description'].startswith('Rack Live'), cs['racklive']['description'])
x = cs['old-test']
check('a stopped container: state, exit code, memory kill, description by the name', not x['running'] and x['exitCode'] == 137 and x['oom'] and x['description'].startswith('Веб-сервер') and x['descriptionFrom'] == 'по названию', x)
check('an unknown image is described by its own label', dockerinfo.describe('me/app:1', {'org.opencontainers.image.description': 'My app'}, '', 'app')[0] == 'My app')
ns = dockerinfo.parse(out.replace("LISTEN 0 4096 0.0.0.0:9998 0.0.0.0:* users:((\"python\",pid=4242,fd=5))", 'tcp        0      0 0.0.0.0:9998            0.0.0.0:*               LISTEN      4242/python'), '192.168.1.3')
check('the same on Synology: netstat instead of ss', {c['name']: c for c in ns['containers']}['racklive']['listening'] == [{'addr': '0.0.0.0', 'port': 9998, 'proc': 'python'}], ns['containers'])
check('dnsmasq in the NAME beats a generic «alpine» image', dockerinfo.describe('alpine:3.19', {}, '', 'pxe-dnsmasq')[0].startswith('dnsmasq'))
check('a label inherited from a base image does not beat a known name', dockerinfo.describe('tensorchord/pgvecto-rs:pg14', {'org.opencontainers.image.description': 'Base images for Immich containers'}, '', 'immich_postgres')[0].startswith('База данных'))
check('environment variables (passwords) are never carried', 'hunter2' not in json.dumps(r))
check('running first, then by CPU', [c['name'] for c in r['containers']] == ['immich_server', 'racklive', 'old-test'])
bad = dockerinfo.parse('@@ver\npermission denied while trying to connect to the Docker daemon socket\n@@end', '1.2.3.4')
check('no access to Docker is reported clearly', bad['docker'] is None and 'недоступен' in bad['error'])
check('no Docker at all', dockerinfo.parse('@@ver\n@@end', '1.2.3.4')['docker'] is None)
check('units: KiB / MiB / GB / kB', dockerinfo._bytes('1KiB') == 1024 and dockerinfo._bytes('2.5MB') == 2500000 and dockerinfo._bytes('0B') == 0)
print('\n' + ('ВСЁ OK' if not FAILS else 'ЕСТЬ ОШИБКИ: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
