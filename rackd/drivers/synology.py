"""Synology DSM 7 via the Web API."""
import urllib.parse

from . import Driver, FIELD_PASS, FIELD_USER
from ..util import DriverError, http_json, uptime_seconds


class Synology(Driver):
    id = 'synology'
    title = 'Synology DSM'
    kind = 'nas'
    description = 'NAS: диски, тома, температура, CPU/RAM, сетевые карты, Docker-контейнеры.'
    fields = [{'name': 'host', 'label': 'Адрес DSM', 'type': 'text', 'required': True, 'placeholder': 'https://192.168.1.3:5001'},
              FIELD_USER, FIELD_PASS]
    actions = [{'id': 'container_restart', 'label': 'Перезапустить контейнер', 'scope': 'service',
                'confirm': 'Перезапустить контейнер {name}?'}]

    def _base(self, cfg):
        h = cfg['host'].rstrip('/')
        return h if h.startswith('http') else 'https://' + h + ':5001'

    def _login(self, cfg):
        base = self._base(cfg)
        r = http_json(base + '/webapi/entry.cgi?' + urllib.parse.urlencode(
            {'api': 'SYNO.API.Auth', 'version': '6', 'method': 'login', 'account': cfg.get('username', ''),
             'passwd': cfg.get('password', ''), 'session': 'racklive', 'format': 'sid'}))
        if not r or not r.get('success'):
            code = (r or {}).get('error', {}).get('code')
            raise DriverError({400: 'неверный логин или пароль', 403: 'нужен код 2FA — создайте отдельного пользователя без 2FA',
                               407: 'IP заблокирован автоблокировкой DSM'}.get(code, f'ошибка входа {code}'))
        sid = r['data']['sid']

        def call(api, ver, method, **kw):
            res = http_json(base + '/webapi/entry.cgi?' + urllib.parse.urlencode(dict(api=api, version=ver, method=method, _sid=sid, **kw)))
            return (res or {}).get('data') if (res or {}).get('success') else None

        def logout():
            try:
                call('SYNO.API.Auth', '6', 'logout', session='racklive')
            except Exception:
                pass
        return call, logout

    def poll(self, cfg):
        call, logout = self._login(cfg)
        try:
            info = call('SYNO.Core.System', '1', 'info') or {}
            util = call('SYNO.Core.System.Utilization', '1', 'get') or {}
            st = call('SYNO.Storage.CGI.Storage', '1', 'load_info') or {}
            nets = call('SYNO.Core.Network.Ethernet', '1', 'list') or []
            cont = (call('SYNO.Docker.Container', '1', 'list', limit='-1', offset='0', type='"all"') or {}).get('containers', [])
        finally:
            logout()
        disks = [{'name': d.get('longName') or d.get('name'), 'model': (d.get('model') or '').strip(), 'kind': 'ssd' if d.get('isSsd') else 'hdd',
                  'sizeGB': round(int(d.get('size_total') or 0) / 1e9), 'temp': d.get('temp'), 'status': d.get('status')}
                 for d in st.get('disks', [])]
        vols = [{'name': v.get('display_name') or v.get('id'), 'status': v.get('status'),
                 'used': int((v.get('size') or {}).get('used') or 0), 'total': int((v.get('size') or {}).get('total') or 0)}
                for v in st.get('volumes', [])]
        ports = []
        for i, n in enumerate(nets if isinstance(nets, list) else []):
            up = n.get('status') == 'connected'
            ports.append({'n': i + 1, 'name': (n.get('ifname') or '').replace('ovs_', ''), 'kind': 'rj45', 'link': up,
                          'speed': n.get('speed') if up and (n.get('speed') or 0) > 0 else 0, 'label': n.get('ip') if up else '',
                          'vlansU': [], 'vlansT': [], 'peers': []})
        cpu = util.get('cpu') or {}
        status = 'online'
        if any(d['status'] not in ('normal', 'not_use') for d in disks) or any(v['status'] != 'normal' for v in vols):
            status = 'warning'
        services = [{'name': c.get('name'), 'state': c.get('status') or c.get('State')} for c in cont]
        return {'status': status,
                'summary': {'model': info.get('model'), 'fw': info.get('firmware_ver'), 'uptime': uptime_seconds(info.get('up_time')),
                            'cpu': (cpu.get('user_load') or 0) + (cpu.get('system_load') or 0),
                            'mem': (util.get('memory') or {}).get('real_usage'), 'temp': info.get('sys_temp'),
                            'ip': next((p['label'] for p in ports if p['link']), None)},
                'ports': ports, 'storage': {'volumes': vols, 'disks': disks}, 'services': services,
                'sections': [{'title': 'Система', 'rows': [['Серийный номер', info.get('serial', '—')],
                                                           ['Оперативная память', f"{info.get('ram_size', '—')} МБ"],
                                                           ['Часовой пояс', info.get('time_zone_desc') or info.get('time_zone') or '—']]}]}

    def action(self, cfg, action_id, params):
        if action_id == 'container_restart':
            name = params.get('name')
            if not name:
                raise DriverError('не указан контейнер')
            call, logout = self._login(cfg)
            try:
                if call('SYNO.Docker.Container', '1', 'restart', name=f'"{name}"') is None:
                    call('SYNO.Docker.Container', '1', 'stop', name=f'"{name}"')
                    call('SYNO.Docker.Container', '1', 'start', name=f'"{name}"')
            finally:
                logout()
            return f'Контейнер {name} перезапущен'
        return super().action(cfg, action_id, params)
