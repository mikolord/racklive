"""OpenWrt via ubus JSON-RPC (uhttpd-mod-ubus / LuCI)."""
from . import Driver, FIELD_HOST, FIELD_PASS, FIELD_USER
from ..util import DriverError, http_json


class OpenWrt(Driver):
    id = 'openwrt'
    title = 'OpenWrt'
    kind = 'router'
    description = 'Модель, прошивка, аптайм, память, интерфейсы и их адреса, DHCP-клиенты.'
    fields = [FIELD_HOST, dict(FIELD_USER, default='root'), FIELD_PASS]
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
