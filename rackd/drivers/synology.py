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
              FIELD_USER, FIELD_PASS,
              {'name': 'sshPort', 'label': 'Порт SSH (для полного доступа Frank)', 'type': 'text', 'default': '22',
               'hint': 'Панель управления → Терминал → «Включить SSH». Вход тем же пользователем DSM (он должен быть администратором).'}]
    actions = [{'id': 'container_restart', 'label': 'Перезапустить контейнер', 'scope': 'service',
                'confirm': 'Перезапустить контейнер {name}?'}]
    shell = 'shell DSM по SSH, команды выполняются от root (sudo): docker / docker compose (папки в /volume1/docker), synopkg, df, ls, cat …'

    def command(self, cfg, cmd):
        """Frank with full access: SSH as the DSM admin, the command runs through sudo (Docker on DSM needs root)"""
        import shlex
        from .sshhost import SSHHost
        host = urllib.parse.urlparse(self._base(cfg)).hostname
        pw = cfg.get('password') or ''
        script = (f"printf '%s\\n' {shlex.quote(pw)} | sudo -S -p '' sh -c "
                  + shlex.quote('export PATH=$PATH:/usr/local/bin:/usr/syno/bin:/usr/syno/sbin\n' + cmd) + ' 2>&1\n')
        return SSHHost()._run({'host': host, 'sshPort': cfg.get('sshPort') or 22, 'username': cfg.get('username') or '',
                               'password': pw}, script, timeout=300)

    def containers(self, cfg, notes=None):
        """Docker in detail over SSH (DSM admin + sudo): image, ports, addresses, uptime, CPU / memory / traffic"""
        from .. import dockerinfo
        out = self.command(cfg, dockerinfo.SCRIPT)
        if 'Permission denied' in out[:300] or 'sudo' in out[:200].lower() and '@@ver' not in out:
            raise DriverError('SSH: ' + out.strip()[:160] + ' — включите SSH в DSM и войдите администратором')
        return dockerinfo.parse(out, urllib.parse.urlparse(self._base(cfg)).hostname or '', notes)

    SS_STATUS = {1: 'работает', 2: 'удалена', 3: 'нет связи', 4: 'недоступна', 5: 'готова', 6: 'нет доступа', 7: 'отключена', 8: 'неизвестно'}

    def surveillance(self, cfg):
        """Synology Surveillance Station (the NAS as a video recorder): version, licences and its cameras — None when the package is not installed"""
        call, logout = self._login(cfg)
        try:
            info = call('SYNO.API.Info', '1', 'query', query='SYNO.SurveillanceStation.Camera') or {}
            if 'SYNO.SurveillanceStation.Camera' not in info:
                return None
            si = call('SYNO.SurveillanceStation.Info', '1', 'GetInfo') or {}
            cams = (call('SYNO.SurveillanceStation.Camera', '9', 'List', blIncludeDeletedCam='false', privCamType='1') or {}).get('cameras') or []
        finally:
            logout()
        v = si.get('version') or {}
        host = urllib.parse.urlparse(self._base(cfg)).hostname or ''
        return {'name': 'Surveillance Station', 'host': host, 'url': f"http://{host}:{si.get('customizedPortHttp') or 9900}", 'version': '.'.join(str(v.get(k)) for k in ('major', 'minor', 'small') if v.get(k) is not None),
                'licences': si.get('liscenseNumber'), 'max': si.get('maxCameraSupport'),
                'cameras': [{'id': c.get('id'), 'name': c.get('newName') or c.get('name') or ('Камера %s' % c.get('id')), 'ip': c.get('ip') or c.get('host') or '', 'port': c.get('port'), 'vendor': c.get('vendor') or '', 'model': c.get('model') or '',
                             'mac': c.get('mac') or '', 'status': c.get('status'), 'statusText': self.SS_STATUS.get(c.get('status'), 'статус %s' % c.get('status')), 'keepDays': c.get('recordingKeepDays') if c.get('enableRecordingKeepDays') else None}
                            for c in cams]}

    def disks(self, cfg):
        """S.M.A.R.T. of every disk over SSH (rackd/smart.py)"""
        from .. import smart
        return smart.parse(self.command(cfg, smart.SCRIPT))

    def disk_test(self, cfg, disk, kind):
        from .. import smart
        try:
            return self.command(cfg, smart.test_script(disk, kind)).strip() or 'Команда отправлена диску'
        except ValueError as e:
            raise DriverError(str(e))

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
