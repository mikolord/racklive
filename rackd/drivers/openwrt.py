"""OpenWrt via ubus JSON-RPC (uhttpd-mod-ubus / LuCI); plugins (Forkop, Podkop, modem drivers) over SSH."""
import re

from . import Driver, FIELD_HOST, FIELD_PASS, FIELD_USER
from .. import plugins
from ..util import DriverError, http_json


class OpenWrt(Driver):
    id = 'openwrt'
    title = 'OpenWrt'
    kind = 'router'
    description = 'Модель, прошивка, аптайм, память, интерфейсы и их адреса, DHCP-клиенты.'
    fields = [FIELD_HOST, dict(FIELD_USER, default='root'), FIELD_PASS,
              {'name': 'sshPort', 'label': 'Порт SSH (для плагинов)', 'type': 'text', 'default': '22',
               'hint': 'Плагины (Forkop, Podkop, драйверы модемов) ставятся по SSH с тем же логином и паролем'}]
    actions = [{'id': 'reboot', 'label': 'Перезагрузить', 'scope': 'device', 'confirm': 'Перезагрузить OpenWrt?'}]

    def _rpc(self, cfg):
        host = cfg['host'].rstrip('/')
        url = (host if host.startswith('http') else 'http://' + host) + '/ubus'

        def call(sid, obj, method, args=None):
            r = http_json(url, data={'jsonrpc': '2.0', 'id': 1, 'method': 'call', 'params': [sid, obj, method, args or {}]}, timeout=15)
            if 'error' in r:
                return None
            res = r.get('result') or [1]
            return res[1] if len(res) > 1 else {}
        sid = (call('0' * 32, 'session', 'login', {'username': cfg.get('username') or 'root', 'password': cfg.get('password', '')}) or {}).get('ubus_rpc_session')
        if not sid:
            raise DriverError('неверный логин/пароль или ubus недоступен')
        return lambda obj, method, args=None: call(sid, obj, method, args)

    def poll(self, cfg):
        call = self._rpc(cfg)
        board, info = call('system', 'board') or {}, call('system', 'info') or {}
        ifs = {i['interface']: i for i in (call('network.interface', 'dump') or {}).get('interface', [])}
        dev = call('network.device', 'status') or {}
        leases = (call('luci-rpc', 'getDHCPLeases') or {}).get('dhcp_leases', [])
        mem = info.get('memory', {})
        ip = lambda i: ', '.join(a['address'] for a in i.get('ipv4-address', [])) or '—'
        ports = []
        for name, d in sorted(dev.items()):
            if '.' in name or not (name.startswith('eth') or name.startswith('lan') or name.startswith('wan')):
                continue
            sp = str(d.get('speed') or '')
            ports.append({'n': len(ports) + 1, 'name': name, 'kind': 'wan' if name.startswith('wan') else 'rj45', 'link': bool(d.get('carrier')),
                          'speed': int(''.join(c for c in sp if c.isdigit()) or 0) if d.get('carrier') else 0,
                          'label': '', 'vlansU': [], 'vlansT': [], 'peers': []})
        clients = [{'mac': (l.get('macaddr') or '').lower(), 'ip': l.get('ipaddr'), 'name': l.get('hostname') or '', 'segment': 'LAN',
                    'online': True, 'kind': 'phone'} for l in leases]
        load = info.get('load') or [0]
        return {'status': 'online',
                'summary': {'model': board.get('model'), 'fw': (board.get('release') or {}).get('description'), 'uptime': info.get('uptime'),
                            'mem': round(100 - (mem.get('free', 0) + mem.get('buffered', 0)) * 100 / max(1, mem.get('total', 1))),
                            'cpu': round(load[0] / 65536 * 100), 'ip': cfg['host'],
                            'macs': sorted({(d.get('macaddr') or '').lower() for d in dev.values() if d.get('macaddr')})},
                'ports': ports, 'clients': clients,
                'sections': [{'title': 'Интерфейсы', 'rows': [[k, f"{'▲' if v.get('up') else '▽'} {ip(v)} · {v.get('l3_device') or ''}"]
                                                              for k, v in sorted(ifs.items()) if k != 'loopback']}]}

    def action(self, cfg, action_id, params):
        if action_id == 'reboot':
            self._rpc(cfg)('system', 'reboot')
            return 'OpenWrt перезагружается'
        return super().action(cfg, action_id, params)

    # ───────── plugins (SSH: same root login as the web interface) ─────────
    @staticmethod
    def _hostname(cfg):
        return re.sub(r'^\w+://', '', cfg['host'].strip()).split('/')[0].split(':')[0]

    def _ssh(self, cfg, script, timeout=30):
        from .sshhost import SSHHost
        return SSHHost()._run({'host': self._hostname(cfg), 'sshPort': cfg.get('sshPort') or 22, 'username': cfg.get('username') or 'root',
                               'password': cfg.get('password') or ''}, script, timeout=timeout)

    def inet_test(self, cfg, iface=None):
        from .. import inet
        return inet.parse_curl(self._ssh(cfg, 'IFACE=""\nBIN=/tmp/rl-bin\n' + inet.CURL_TEST, 180))

    def backup(self, cfg):
        """Full UCI configuration (all /etc/config files) — the text that is versioned."""
        out = self._ssh(cfg, 'uci export 2>/dev/null; echo @@end', 40)
        if '@@end' not in out:
            raise DriverError('OpenWrt не отдал конфигурацию')
        return out.split('@@end')[0]

    def _state(self, cfg):
        out = self._ssh(cfg, plugins.OWRT_STATUS, 30)
        if '@@end' not in out:
            raise DriverError('OpenWrt ответил не полностью')
        return plugins.parse_owrt(out)

    def plugins(self, cfg):
        st = self._state(cfg)
        major = int((re.findall(r'\d+', st['rel']) or ['0'])[0])
        free_mb = (st['free'] or 0) // 1024
        host, out = self._hostname(cfg), []
        for p in plugins.for_driver(self.id):
            p['pm'], p['fw'] = st['pm'], st['rel']
            if p['id'] in plugins.OWRT_INSTALLERS:
                inst = plugins.OWRT_INSTALLERS[p['id']]
                other = inst['conflict']
                p['installed'] = inst['packages'][0] in st['pkgs']
                p['version'] = st['pkgs'].get(inst['packages'][0])
                p['url'], p['login'] = f"http://{host}/cgi-bin/luci/{inst['luci']}", 'логин и пароль от OpenWrt (LuCI)'
                p['ssh'] = {'ok': True, 'native': True}
                p['checks'] = [{'label': f"OpenWrt 24.10 или новее (у вас {st['rel'] or '?'})", 'ok': major >= 24},
                               {'label': f"Свободно на флеше от {inst['freeMB']} МБ (сейчас {free_mb} МБ)", 'ok': p['installed'] or free_mb >= inst['freeMB']},
                               {'label': f"Не установлен {other.capitalize()} — они конфликтуют", 'ok': other not in st['pkgs']}]
                if 'https-dns-proxy' in st['pkgs'] and not p['installed']:
                    p['warning'] = 'Установщик удалит конфликтующий пакет https-dns-proxy (DNS через HTTPS).'
                if p['id'] == 'forkop':
                    p['singbox'] = st['sb']
                    p['options'] = [{'id': 'extended', 'label': 'sing-box extended — поддержка XHTTP', 'on': True,
                                     'hint': 'Без него XHTTP-ссылки не заработают. Обычный sing-box легче.'}]
            elif p['id'] == 'modem':
                sug = plugins.modem_suggest(st)
                p['usb'], p['drivers'], p['devs'], p['suggest'] = st['usb'], st['drv'], st['dev'], sug
                p['profiles'] = [dict(m, installed=m['key'] in st['pkgs'], suggested=m['id'] == sug) for m in plugins.MODEM_PROFILES]
                p['installed'] = any(m['installed'] for m in p['profiles'])
                p['checks'] = [{'label': 'Модем подключён к USB' + (f": {st['usb'][0]}" if st['usb'] else ''), 'ok': bool(st['usb'])}]
            out.append(p)
        return {'fw': st['rel'], 'pm': st['pm'], 'plugins': out}

    def plugin(self, cfg, pid, op, params):
        clean = lambda s: re.sub(r'\x1b\[[0-9;]*m', '', s)
        to_log = lambda body: [{'cmd': l[:200], 'ok': '@@fail' not in l and not re.search(r'\berror\b|failed|ошибка', l, re.I), 'msg': ''}
                               for l in clean(body).splitlines() if l.strip() and not l.startswith('@@')][-60:]
        if pid in plugins.OWRT_INSTALLERS:
            inst, meta = plugins.OWRT_INSTALLERS[pid], next(p for p in plugins.CATALOG if p['id'] == pid)
            st = self._state(cfg)
            if op == 'install':
                if inst['conflict'] in st['pkgs']:
                    raise DriverError(f"сначала удалите {inst['conflict'].capitalize()} — два менеджера маршрутизации конфликтуют")
                if int((re.findall(r'\d+', st['rel']) or ['0'])[0]) < 24:
                    raise DriverError(f"{meta['title']} нужен OpenWrt 24.10 или новее (у вас {st['rel']})")
                free_mb = (st['free'] or 0) // 1024
                if pid not in st['pkgs'] and free_mb < inst['freeMB']:
                    raise DriverError(f"мало места на флеше: {free_mb} МБ, нужно от {inst['freeMB']} МБ")
                env = f"RL_EXT={1 if params.get('extended', True) else 0}\n"
                out = self._ssh(cfg, env + inst['install'] + plugins.OWRT_STATUS, timeout=1200)
            elif op == 'remove':
                out = self._ssh(cfg, inst['remove'] + '\n' + plugins.OWRT_STATUS, timeout=300)
            else:
                raise DriverError('неизвестное действие')
            body, after = out.split('@@rel', 1)[0], plugins.parse_owrt(out)
            if '@@fail' in body:
                raise DriverError(clean(body).split('@@fail', 1)[1].splitlines()[0].strip())
            main, log = inst['packages'][0], to_log(body)
            if op == 'remove':
                if main in after['pkgs']:
                    raise DriverError(f"{meta['title']} не удалился — см. журнал")
                return {'ok': True, 'log': log, 'message': f"{meta['title']} удалён (sing-box и настройки оставлены)"}
            if main not in after['pkgs']:
                return {'ok': False, 'log': log, 'error': f"{meta['title']} не установился — посмотрите журнал ниже", 'message': f"{meta['title']} не установился"}
            url = f"http://{self._hostname(cfg)}/cgi-bin/luci/{inst['luci']}"
            sb = f" · {after['sb'].replace('sing-box version ', 'sing-box ')}" if after['sb'] else ''
            return {'ok': True, 'log': log, 'version': after['pkgs'][main], 'url': url,
                    'message': f"{meta['title']} {after['pkgs'][main]} установлен{sb}. Настройка: LuCI → Службы → {meta['title']} ({url})"}
        if pid == 'modem':
            prof = next((m for m in plugins.MODEM_PROFILES if m['id'] == params.get('profile')), None)
            if not prof or op not in ('install', 'remove'):
                raise DriverError('неизвестный вариант модема')
            st = self._state(cfg)
            others = [m for m in plugins.MODEM_PROFILES if m['id'] != prof['id'] and m['key'] in st['pkgs']]
            if op == 'install':
                clash = [m['title'] for m in others if m['id'] in prof.get('conflicts', [])]
                if clash:
                    raise DriverError(f"сначала удалите вариант «{clash[0]}» — они мешают друг другу")
                script = plugins.OWRT_PKG + 'pupd >/dev/null 2>&1\npadd ' + ' '.join(prof['packages']) + ' 2>&1 | tail -15\n'
            else:                                       # keep packages that another installed variant still needs
                keep = {x for m in others for x in m['packages']}
                script = plugins.OWRT_PKG + 'pdel ' + ' '.join(x for x in prof['packages'] if x not in keep) + ' 2>&1 | tail -15\n'
            out = self._ssh(cfg, script + plugins.OWRT_STATUS, timeout=600)
            after = plugins.parse_owrt(out)
            log = to_log(out.split('@@rel', 1)[0])
            ok = (prof['key'] in after['pkgs']) == (op == 'install')
            if not ok:
                return {'ok': False, 'log': log, 'error': 'не получилось — посмотрите журнал ниже', 'message': f"«{prof['title']}»: не получилось"}
            if op == 'remove':
                return {'ok': True, 'log': log, 'message': f"Вариант «{prof['title']}» удалён — можно поставить другой"}
            return {'ok': True, 'log': log, 'message': f"Установлено: {prof['title']}. Дальше: {prof['after']} Если модем не заработал — "
                                                         'удалите этот вариант и попробуйте другой (иногда нужно переподключить модем).'}
        raise DriverError('неизвестный плагин')
