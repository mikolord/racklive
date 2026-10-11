"""TP-Link JetStream switches (T2600G / T1600G / SG3xxx) over the telnet CLI."""
import re, threading, time

from . import Driver, FIELD_HOST, FIELD_PASS, FIELD_USER
from ..snmp import Snmp, SnmpError, text
from ..util import DriverError, parse_ranges, telnet_session, uptime_seconds


class TPLinkJetStream(Driver):
    id = 'tplink_jetstream'
    title = 'TP-Link JetStream (telnet)'
    kind = 'switch'
    description = 'Управляемый коммутатор: линк, скорость, PoE по портам, VLAN, кто подключён. Нужен включённый telnet.'
    fields = [FIELD_HOST, dict(FIELD_USER, default='admin'), FIELD_PASS,
              {'name': 'protectedPorts', 'label': 'Защищённые порты (uplink), через запятую', 'type': 'text',
               'hint': 'Эти порты нельзя будет выключить из интерфейса, чтобы не потерять связь'},
              {'name': 'snmpCommunity', 'label': 'SNMP community (для графиков трафика)', 'type': 'password', 'secret': True,
               'hint': 'Необязательно. На коммутаторе: snmp-server community <имя> read-only'}]
    actions = [{'id': 'poe_cycle', 'label': 'Перезапустить PoE', 'scope': 'port', 'needs': 'poe',
                'confirm': 'Устройство на порту {port} обесточится на 10 секунд и перезагрузится. Продолжить?'},
               {'id': 'port_bounce', 'label': 'Перезапустить порт', 'scope': 'port',
                'confirm': 'Связь на порту {port} пропадёт на 5 секунд. Продолжить?'}]
    protected_ports_hint = 'uplink'

    _locks = {}

    def _cli(self, cfg, cmds, wait=1.0):
        # one telnet session per switch at a time: the switch drops/mixes parallel CLI sessions
        lock = self._locks.setdefault(cfg['host'], threading.Lock())
        with lock:
            return telnet_session(cfg['host'], cfg.get('username') or 'admin', cfg.get('password', ''),
                                  ['enable', 'terminal length 0'] + cmds, wait=wait)

    def _run_checked(self, cfg, cmds):
        """Runs config commands, retries once, raises if the switch reported an error."""
        for attempt in range(2):
            out = self._cli(cfg, ['configure'] + cmds + ['end'])
            errs = [f'{c}: {o.strip().splitlines()[-2] if len(o.strip().splitlines()) > 1 else o.strip()}'
                    for c, o in out.items() if c in cmds and 'Error' in o]
            if not errs and all(c in out for c in cmds):
                return out
            time.sleep(2)
        raise DriverError('коммутатор не выполнил команду: ' + '; '.join(errs)[:200])

    def poll(self, cfg):
        o = self._cli(cfg, ['show system-info', 'show interface status', 'show power inline information interface',
                            'show mac address-table', 'show running-config'])
        info = {}
        for l in o['show system-info'].splitlines():
            m = re.match(r'\s*([A-Za-z][A-Za-z ]+?)\s+-\s+(.*)', l)
            if m:
                info[m.group(1).strip()] = m.group(2).strip()
        if not info:
            raise DriverError('коммутатор не ответил на команды CLI')
        ports = {}
        for l in o['show interface status'].splitlines():
            m = re.match(r'\s*Gi1/0/(\d+)\s+(LinkUp|LinkDown)\s+(\S+)\s+\S+\s+\S+\s+(\S+)', l)
            if m:
                n, sp = int(m.group(1)), m.group(3).rstrip('M')
                ports[n] = {'n': n, 'name': 'Gi1/0/%d' % n, 'kind': 'sfp' if m.group(4) == 'Fiber' else 'rj45', 'link': m.group(2) == 'LinkUp',
                            'speed': int(sp) if sp.isdigit() else 0, 'poeW': 0.0, 'poe': False, 'label': '', 'vlansU': [], 'vlansT': [],
                            'pvid': 1, 'peers': [], 'disabled': False}
        poe_total = 0.0
        for l in o['show power inline information interface'].splitlines():
            m = re.match(r'\s*Gi1/0/(\d+)\s+([\d.]+)\s+\d+\s+[\d.]+\s+(.+?)\s+(ON|OFF)\s*$', l)
            if m and int(m.group(1)) in ports:
                p = ports[int(m.group(1))]
                p['poeW'] = float(m.group(2))
                p['poe'] = True
                p['poeOn'] = m.group(4) == 'ON'
                poe_total += p['poeW']
        for l in o['show mac address-table'].splitlines():
            m = re.match(r'\s*([0-9a-f:]{17})\s+(\d+)\s+Gi1/0/(\d+)', l)
            if m and int(m.group(3)) in ports:
                ports[int(m.group(3))]['peers'].append({'mac': m.group(1), 'vlan': int(m.group(2))})
        cur, vlan_names, cur_vlan = None, {}, None
        for l in o['show running-config'].splitlines():
            s = l.strip()
            mv = re.match(r'vlan (\d+)$', s)
            if mv:
                cur_vlan, cur = int(mv.group(1)), None
                continue
            if cur_vlan and s.startswith('name '):
                vlan_names[cur_vlan] = s[5:].strip('"')
                continue
            m = re.match(r'interface gigabitEthernet 1/0/(\d+)', s)
            if m:
                cur, cur_vlan = int(m.group(1)), None
                continue
            if cur is None or cur not in ports:
                continue
            if s.startswith('description'):
                ports[cur]['label'] = s.split(' ', 1)[1].strip('"')
            elif s == 'shutdown':
                ports[cur]['disabled'] = True
            m = re.match(r'switchport general allowed vlan (\S+) (tagged|untagged)', s)
            if m:
                ports[cur]['vlansT' if m.group(2) == 'tagged' else 'vlansU'] += parse_ranges(m.group(1))
            m = re.match(r'switchport pvid (\d+)', s)
            if m:
                ports[cur]['pvid'] = int(m.group(1))
        for p in ports.values():
            if not p['vlansU']:
                p['vlansU'] = [p['pvid']]
        plist = [ports[k] for k in sorted(ports)]
        if cfg.get('snmpCommunity'):
            try:
                s = Snmp(cfg['host'], cfg['snmpCommunity'], timeout=2, retries=1)
                descr = s.table('1.3.6.1.2.1.2.2.1.2')
                hin, hout = s.table('1.3.6.1.2.1.31.1.1.1.6'), s.table('1.3.6.1.2.1.31.1.1.1.10')
                for idx, d in descr.items():
                    m = re.search(r'1/0/(\d+)$', text(d))
                    if m and int(m.group(1)) in ports:
                        ports[int(m.group(1))].update(rxBytes=hin.get(idx), txBytes=hout.get(idx))
            except SnmpError:
                pass
        up = sum(1 for p in plist if p['link'])
        return {'status': 'online',
                'summary': {'model': info.get('System Description') or info.get('Hardware Version'), 'fw': info.get('Software Version'),
                            'uptime': uptime_seconds(info.get('Running Time')), 'ip': cfg['host'],
                            'mac': (info.get('Mac Address') or '').replace('-', ':').lower()},
                'ports': plist,
                'vlanNames': vlan_names,
                'metrics': [{'label': 'Порты с линком', 'value': f'{up}/{len(plist)}'},
                            {'label': 'PoE', 'value': round(poe_total, 1), 'unit': 'Вт'}],
                'sections': [{'title': 'Коммутатор', 'rows': [['Аппаратная версия', info.get('Hardware Version', '—')],
                                                               ['Серийный номер', info.get('Serial Number', '—')],
                                                               ['Имя', info.get('System Name', '—')]]}]}

    def action(self, cfg, action_id, params):
        port = int(params.get('port') or 0)
        if not 1 <= port <= 64:
            raise DriverError('неверный номер порта')
        if port in [int(x) for x in str(cfg.get('protectedPorts') or '').replace(' ', '').split(',') if x.isdigit()]:
            raise DriverError(f'порт {port} защищён (uplink) — его нельзя отключать отсюда')
        iface = f'interface gigabitEthernet 1/0/{port}'
        if action_id == 'poe_cycle':
            self._run_checked(cfg, [iface, 'power inline supply disable'])
            time.sleep(8)
            self._run_checked(cfg, [iface, 'power inline supply enable'])
            out = self._cli(cfg, [f'show power inline configuration interface gigabitEthernet 1/0/{port}'])
            txt = ''.join(out.values())
            if re.search(rf'Gi1/0/{port}\s+Disable', txt):
                self._run_checked(cfg, [iface, 'power inline supply enable'])
            return f'PoE на порту {port} перезапущено — устройство загружается'
        if action_id == 'port_bounce':
            self._run_checked(cfg, [iface, 'shutdown'])
            time.sleep(4)
            self._run_checked(cfg, [iface, 'no shutdown'])
            out = self._cli(cfg, ['show running-config interface gigabitEthernet 1/0/%d' % port])
            if re.search(r'^\s*shutdown\s*$', ''.join(out.values()), re.M):
                self._run_checked(cfg, [iface, 'no shutdown'])
            return f'Порт {port} перезапущен'
        return super().action(cfg, action_id, params)
