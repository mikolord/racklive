"""Proxmox VE via its REST API (https://host:8006/api2/json).

Login: an API token (Datacenter → Permissions → API Tokens; «user@pam!name» + secret, role PVEAuditor to watch,
PVEVMUser / PVEVMAdmin to start / stop) or a user + password (ticket + CSRF token).
Shows: nodes (CPU, RAM, uptime, version), virtual machines and LXC containers, storages, physical disks (SMART health).
"""
import json
import urllib.error
import urllib.parse

from . import Driver, FIELD_PASS
from ..util import DriverError, http_json

VM_ACTIONS = {'vm_start': 'start', 'vm_shutdown': 'shutdown', 'vm_reboot': 'reboot', 'vm_stop': 'stop'}


class Proxmox(Driver):
    id = 'proxmox'
    title = 'Proxmox VE'
    kind = 'server'
    description = 'Сервер виртуализации: виртуальные машины и контейнеры (запуск, выключение), нагрузка, хранилища, диски.'
    fields = [
        {'name': 'host', 'label': 'Адрес Proxmox', 'type': 'text', 'required': True, 'placeholder': '192.168.1.20 или https://pve.local:8006'},
        {'name': 'auth', 'label': 'Как входить', 'type': 'select', 'default': 'password', 'options': [
            {'value': 'password', 'label': 'Логин и пароль Proxmox'},
            {'value': 'token', 'label': 'API-токен (надёжнее)'}]},
        {'name': 'username', 'label': 'Пользователь', 'type': 'text', 'default': 'root@pam', 'showIf': {'field': 'auth', 'in': ['password']},
         'hint': 'С указанием области: root@pam или имя@pve'},
        dict(FIELD_PASS, showIf={'field': 'auth', 'in': ['password']}),
        {'name': 'tokenId', 'label': 'ID токена', 'type': 'text', 'placeholder': 'root@pam!racklive', 'showIf': {'field': 'auth', 'in': ['token']},
         'hint': 'Datacenter → Permissions → API Tokens → Add. Снимите «Privilege Separation» или дайте токену роль PVEAuditor (смотреть) / PVEVMUser (включать-выключать).'},
        {'name': 'tokenSecret', 'label': 'Секрет токена', 'type': 'password', 'secret': True, 'showIf': {'field': 'auth', 'in': ['token']}},
    ]
    actions = [
        {'id': 'vm_start', 'label': 'Запустить', 'scope': 'vm', 'confirm': ''},
        {'id': 'vm_shutdown', 'label': 'Выключить', 'scope': 'vm', 'confirm': 'Выключить «{name}»? Система внутри завершит работу штатно.'},
        {'id': 'vm_reboot', 'label': 'Перезагрузить', 'scope': 'vm', 'confirm': 'Перезагрузить «{name}»?'},
        {'id': 'vm_stop', 'label': 'Остановить принудительно', 'scope': 'vm',
         'confirm': '«{name}» будет остановлена сразу, как выдернутый шнур — несохранённые данные внутри пропадут. Продолжить?'},
        {'id': 'node_reboot', 'label': 'Перезагрузить сервер Proxmox', 'scope': 'device',
         'confirm': 'Перезагрузить сервер Proxmox? Все виртуалки на нём выключатся и будут недоступны несколько минут.'},
    ]

    def _base(self, cfg):
        h = (cfg.get('host') or '').strip().rstrip('/')
        if not h.startswith('http'):
            h = 'https://' + h
        p = urllib.parse.urlparse(h)
        return f'{p.scheme}://{p.hostname}:{p.port or 8006}/api2/json'

    def _session(self, cfg):
        """→ call(method, path, data=None) with auth applied"""
        base = self._base(cfg)
        if (cfg.get('auth') or 'password') == 'token':
            if not cfg.get('tokenId') or not cfg.get('tokenSecret'):
                raise DriverError('укажите ID и секрет API-токена')
            hdr = {'Authorization': f"PVEAPIToken={cfg['tokenId'].strip()}={cfg['tokenSecret'].strip()}"}
        else:
            user = (cfg.get('username') or 'root@pam').strip()
            if '@' not in user:
                user += '@pam'
            try:
                r = http_json(base + '/access/ticket', urllib.parse.urlencode({'username': user, 'password': cfg.get('password') or ''}),
                              headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST', timeout=12)
            except urllib.error.HTTPError as e:
                raise DriverError('неверный логин или пароль' if e.code in (401, 403) else f'вход: HTTP {e.code}')
            except OSError as e:
                raise DriverError(f'Proxmox не отвечает ({getattr(e, "reason", e)})')
            d = (r or {}).get('data') or {}
            if not d.get('ticket'):
                raise DriverError('неверный логин или пароль (или включена 2FA — используйте API-токен)')
            hdr = {'Cookie': 'PVEAuthCookie=' + urllib.parse.quote(d['ticket']), 'CSRFPreventionToken': d.get('CSRFPreventionToken', '')}

        def call(method, path, data=None):
            try:
                body = urllib.parse.urlencode(data) if data else None
                h = dict(hdr, **({'Content-Type': 'application/x-www-form-urlencoded'} if body else {}))
                return ((http_json(base + path, body, headers=h, method=method, timeout=15) or {}).get('data'))
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise DriverError('нет доступа — проверьте токен / пароль')
                if e.code == 403:
                    raise DriverError('у пользователя / токена не хватает прав (нужна роль PVEAuditor, для управления — PVEVMUser)')
                try:
                    msg = json.loads(e.read() or b'{}').get('message') or ''
                except ValueError:
                    msg = ''
                raise DriverError(f'HTTP {e.code} {msg}'.strip())
            except OSError as e:
                raise DriverError(f'Proxmox не отвечает ({getattr(e, "reason", e)})')
        return call

    def poll(self, cfg):
        call = self._session(cfg)
        ver = call('GET', '/version') or {}
        res = call('GET', '/cluster/resources') or []
        nodes = [r for r in res if r.get('type') == 'node']
        vms = []
        for r in res:
            if r.get('type') in ('qemu', 'lxc') and not r.get('template'):
                vms.append({'id': f"{r.get('node')}/{r['type']}/{r.get('vmid')}", 'vmid': r.get('vmid'), 'name': r.get('name') or f"#{r.get('vmid')}",
                            'type': 'vm' if r['type'] == 'qemu' else 'ct', 'node': r.get('node'), 'status': r.get('status'),
                            'cpu': round((r.get('cpu') or 0) * 100, 1), 'cpus': r.get('maxcpu'), 'mem': r.get('mem'), 'maxmem': r.get('maxmem'),
                            'disk': r.get('disk'), 'maxdisk': r.get('maxdisk'), 'uptime': r.get('uptime')})
        vms.sort(key=lambda v: (v['status'] != 'running', v['vmid'] or 0))
        vols, seen = [], set()
        for r in res:
            if r.get('type') == 'storage' and r.get('maxdisk'):
                key = (r.get('storage'), r.get('shared') and 'shared' or r.get('node'))
                if key in seen:
                    continue
                seen.add(key)
                pct = (r.get('disk') or 0) / r['maxdisk']
                vols.append({'name': r.get('storage') + ('' if r.get('shared') or len(nodes) < 2 else f" ({r.get('node')})"),
                             'status': 'normal' if r.get('status') == 'available' and pct < .95 else 'почти заполнен' if pct >= .95 else r.get('status') or '—',
                             'used': r.get('disk') or 0, 'total': r['maxdisk']})
        disks = []
        main = nodes[0] if nodes else {}
        node_st = {}
        for n in nodes:
            if n.get('status') != 'online':
                continue
            try:
                node_st[n['node']] = call('GET', f"/nodes/{n['node']}/status") or {}
                for d in call('GET', f"/nodes/{n['node']}/disks/list") or []:
                    disks.append({'name': d.get('devpath'), 'model': d.get('model') or d.get('vendor') or '', 'kind': d.get('type') or '',
                                  'sizeGB': round((d.get('size') or 0) / 1e9), 'temp': None,
                                  'status': 'normal' if (d.get('health') or '').upper() in ('PASSED', 'OK', '') else d.get('health'),
                                  'wearout': d.get('wearout') if isinstance(d.get('wearout'), (int, float)) else None})
            except DriverError:
                pass            # a token without Sys.Audit cannot read node status / disks — VMs are still shown
        ns = node_st.get(main.get('node')) or {}
        mem = ns.get('memory') or {}
        cpu = round((ns.get('cpu') if ns.get('cpu') is not None else main.get('cpu') or 0) * 100, 1)
        mem_pct = round(100 * mem['used'] / mem['total'], 1) if mem.get('total') else \
            (round(100 * main['mem'] / main['maxmem'], 1) if main.get('maxmem') else None)
        running = sum(1 for v in vms if v['status'] == 'running')
        status = 'online'
        if any(v['status'] != 'normal' for v in vols) or (mem_pct or 0) > 95 or any(n.get('status') != 'online' for n in nodes) \
                or any(d['status'] != 'normal' for d in disks):
            status = 'warning'
        ci = ns.get('cpuinfo') or {}
        rows = [['Версия', f"Proxmox VE {ver.get('version', '')}".strip()], ['Узлов', len(nodes)],
                ['Процессор', f"{ci.get('model', '—')}{' · ' + str(ci.get('cpus')) + ' потоков' if ci.get('cpus') else ''}"],
                ['Память', f"{round(mem.get('total', main.get('maxmem') or 0) / 2 ** 30, 1)} ГБ"],
                ['Виртуалки', f"{sum(1 for v in vms if v['type'] == 'vm')} ВМ, {sum(1 for v in vms if v['type'] == 'ct')} контейнеров · работает {running}"]]
        if len(nodes) > 1:
            rows.append(['Узлы', ', '.join(f"{n['node']} ({'в сети' if n.get('status') == 'online' else 'нет связи'})" for n in nodes)])
        return {'status': status,
                'summary': {'model': f"Proxmox VE {ver.get('version', '')}".strip(), 'fw': ns.get('pveversion') or ver.get('release'),
                            'uptime': ns.get('uptime') or main.get('uptime'), 'cpu': cpu, 'mem': mem_pct,
                            'ip': urllib.parse.urlparse(self._base(cfg)).hostname},
                'metrics': [{'label': 'Виртуалки', 'value': f'{running} из {len(vms)}'}],
                'vms': vms, 'storage': {'volumes': vols, 'disks': disks},
                'sections': [{'title': 'Proxmox', 'rows': rows}]}

    def action(self, cfg, action_id, params):
        call = self._session(cfg)
        if action_id in VM_ACTIONS:
            vid = str(params.get('id') or '')
            parts = vid.split('/')
            if len(parts) != 3 or parts[1] not in ('qemu', 'lxc') or not parts[2].isdigit():
                raise DriverError('неизвестная виртуалка')
            node, typ, vmid = parts
            call('POST', f'/nodes/{urllib.parse.quote(node)}/{typ}/{vmid}/status/{VM_ACTIONS[action_id]}')
            word = {'vm_start': 'запускается', 'vm_shutdown': 'выключается', 'vm_reboot': 'перезагружается', 'vm_stop': 'остановлена'}[action_id]
            return f"{params.get('name') or vmid} {word}"
        if action_id == 'node_reboot':
            node = ((call('GET', '/nodes') or [{}])[0]).get('node')
            if not node:
                raise DriverError('узел не найден')
            call('POST', f'/nodes/{urllib.parse.quote(node)}/status', {'command': 'reboot'})
            return 'Сервер Proxmox перезагружается'
        return super().action(cfg, action_id, params)
