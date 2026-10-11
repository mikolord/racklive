"""Generic SNMP v2c driver: works with almost any managed switch, router, NAS, UPS, printer or Linux host."""
import re

from . import Driver
from ..snmp import Snmp, SnmpError, mac, text
from ..util import DriverError

SYS = '1.3.6.1.2.1.1'
IF = '1.3.6.1.2.1.2.2.1'           # ifTable
IFX = '1.3.6.1.2.1.31.1.1.1'       # ifXTable
ETHER_TYPES = {6, 7, 26, 62, 69, 117}


def interfaces(s, physical_only=True):
    """Ports from IF-MIB with octet counters: {ifIndex: port}."""
    descr = s.table(IF + '.2')
    types = s.table(IF + '.3')
    speed = s.table(IF + '.5')
    admin = s.table(IF + '.7')
    oper = s.table(IF + '.8')
    name = s.table(IFX + '.1', optional=True)
    hs = s.table(IFX + '.15', optional=True)
    alias = s.table(IFX + '.18', optional=True)
    hin = s.table(IFX + '.6', optional=True)
    hout = s.table(IFX + '.10', optional=True)
    lin = s.table(IF + '.10') if not hin else {}
    lout = s.table(IF + '.16') if not hout else {}
    ports = {}
    for idx in sorted(descr, key=lambda x: int(x)):
        t = types.get(idx)
        d = text(descr[idx])
        if physical_only and t not in ETHER_TYPES:
            continue
        if physical_only and re.search(r'vlan|loopback|bridge|tunnel|null|cpu|virtual|port-channel|lag|bond|br-|docker|veth', d, re.I):
            continue
        up = oper.get(idx) == 1
        sp = hs.get(idx) or round((speed.get(idx) or 0) / 1e6)
        nm = text(name.get(idx)) or d
        ports[idx] = {'n': 0, 'name': nm, 'ifIndex': int(idx), 'kind': 'sfp' if re.search(r'sfp|fiber|ten|xe-|te\d|10g', nm + d, re.I) else 'rj45',
                      'link': up, 'speed': sp if up else 0, 'disabled': admin.get(idx) == 2, 'label': text(alias.get(idx)),
                      'vlansU': [], 'vlansT': [], 'peers': [], 'poeW': 0,
                      'rxBytes': hin.get(idx) if hin else lin.get(idx), 'txBytes': hout.get(idx) if hout else lout.get(idx)}
    for i, p in enumerate(ports.values()):
        m = re.search(r'(\d+)$', p['name'])
        p['n'] = i + 1
        p['label'] = p['label'] if p['label'] != p['name'] else ''
    return ports


def bridge(s, ports):
    """MAC table and VLAN membership from BRIDGE-MIB / Q-BRIDGE-MIB."""
    bp_if = {int(k): v for k, v in s.table('1.3.6.1.2.1.17.1.4.1.2', optional=True).items()}
    by_if = {p['ifIndex']: p for p in ports.values()}
    to_port = lambda bp: by_if.get(bp_if.get(bp, bp)) or by_if.get(bp)

    seen = set()
    for idx, bp in s.table('1.3.6.1.2.1.17.7.1.2.2.1.2', optional=True).items():      # dot1qTpFdbPort: vlan.mac → port
        parts = idx.split('.')
        if len(parts) < 7:
            continue
        m = ':'.join(f'{int(x):02x}' for x in parts[-6:])
        p = to_port(bp)
        if p and (m, p['n']) not in seen:
            seen.add((m, p['n']))
            p['peers'].append({'mac': m, 'vlan': int(parts[0])})
    if not seen:
        for idx, bp in s.table('1.3.6.1.2.1.17.4.3.1.2', optional=True).items():       # dot1dTpFdbPort: mac → port
            m = ':'.join(f'{int(x):02x}' for x in idx.split('.')[-6:])
            p = to_port(bp)
            if p:
                p['peers'].append({'mac': m})

    egress = s.table('1.3.6.1.2.1.17.7.1.4.3.1.2', optional=True)                          # dot1qVlanStaticEgressPorts
    untag = s.table('1.3.6.1.2.1.17.7.1.4.3.1.4', optional=True)
    if not egress:                                                                          # dot1qVlanCurrent* (index timeMark.vid)
        egress = {k.split('.')[-1]: v for k, v in s.table('1.3.6.1.2.1.17.7.1.4.2.1.4', optional=True).items()}
        untag = {k.split('.')[-1]: v for k, v in s.table('1.3.6.1.2.1.17.7.1.4.2.1.5', optional=True).items()}
    names = {int(k): text(v) for k, v in s.table('1.3.6.1.2.1.17.7.1.4.3.1.1', optional=True).items()}
    pvid = s.table('1.3.6.1.2.1.17.7.1.4.5.1.1', optional=True)                            # dot1qPvid
    bits = lambda b: [i * 8 + j + 1 for i, byte in enumerate(b if isinstance(b, bytes) else b'') for j in range(8) if byte & (0x80 >> j)]
    for vid, eg in egress.items():
        un = set(bits(untag.get(vid, b'')))
        for bp in bits(eg):
            p = to_port(bp)
            if p:
                (p['vlansU'] if bp in un else p['vlansT']).append(int(vid))
    for bp, v in pvid.items():
        p = to_port(int(bp))
        if p and not p['vlansU']:
            p['vlansU'] = [v]
    return names


def lldp(s, ports):
    names = s.table('1.0.8802.1.1.2.1.4.1.1.9', optional=True)       # lldpRemSysName: timemark.localPort.index
    loc = {int(k): text(v) for k, v in s.table('1.0.8802.1.1.2.1.3.7.1.3', optional=True).items()}   # lldpLocPortId
    out = []
    for idx, v in names.items():
        parts = idx.split('.')
        lp = int(parts[1]) if len(parts) > 2 else 0
        port = next((p for p in ports.values() if p['ifIndex'] == lp or p['n'] == lp or p['name'] == loc.get(lp)), None)
        out.append({'port': port['n'] if port else lp, 'name': text(v)})
        if port:
            port['lldp'] = text(v)
    return out


class SNMP(Driver):
    id = 'snmp'
    title = 'SNMP (любое устройство)'
    kind = 'switch'
    description = 'Универсально: коммутаторы любых брендов, MikroTik, ИБП, принтеры, Linux. Порты, трафик, VLAN, кто на каком порту, LLDP, CPU и диски.'
    fields = [{'name': 'host', 'label': 'Адрес (IP или домен)', 'type': 'text', 'required': True},
              {'name': 'community', 'label': 'Community (только чтение)', 'type': 'password', 'secret': True, 'placeholder': 'public',
               'hint': 'Включите SNMP v2c на устройстве и задайте community только для чтения'},
              {'name': 'allPorts', 'label': 'Показывать и виртуальные интерфейсы (да/нет)', 'type': 'text', 'placeholder': 'нет'}]

    def poll(self, cfg):
        s = Snmp(cfg['host'], cfg.get('community') or 'public', timeout=2, retries=1)
        try:
            sysd = s.get(SYS + '.1.0', SYS + '.3.0', SYS + '.5.0', SYS + '.6.0')
        except SnmpError as e:
            raise DriverError(str(e))
        descr = text(sysd.get(SYS + '.1.0'))
        ports = interfaces(s, physical_only=str(cfg.get('allPorts') or '').lower() not in ('да', 'yes', '1', 'true'))
        vlan_names = bridge(s, ports) if ports else {}
        neighbors = lldp(s, ports) if ports else []
        cpu = [v for v in s.table('1.3.6.1.2.1.25.3.3.1.2', optional=True).values() if isinstance(v, int)]
        storage, mem, vols = s.table('1.3.6.1.2.1.25.2.3.1', optional=True), None, []
        if storage:
            rows = {}
            for k, v in storage.items():
                col, idx = k.split('.', 1)
                rows.setdefault(idx, {})[int(col)] = v
            for r in rows.values():
                unit, size, used, typ = r.get(4) or 1, r.get(5) or 0, r.get(6) or 0, str(r.get(2) or '')
                if typ.endswith('.25.2.1.2') and size:
                    mem = round(used * 100 / size)
                elif typ.endswith('.25.2.1.4') and size:
                    vols.append({'name': text(r.get(3)), 'status': 'normal', 'used': used * unit, 'total': size * unit})
        plist = list(ports.values())
        up = sum(1 for p in plist if p['link'])
        res = {'status': 'online',
               'summary': {'model': descr.split('\n')[0][:120] or text(sysd.get(SYS + '.5.0')), 'fw': None,
                           'uptime': (sysd.get(SYS + '.3.0') or 0) // 100, 'cpu': round(sum(cpu) / len(cpu)) if cpu else None,
                           'mem': mem, 'ip': cfg['host']},
               'ports': plist, 'vlanNames': vlan_names,
               'metrics': [{'label': 'Порты с линком', 'value': f'{up}/{len(plist)}'}] if plist else [],
               'sections': [{'title': 'SNMP', 'rows': [['Имя', text(sysd.get(SYS + '.5.0'))], ['Расположение', text(sysd.get(SYS + '.6.0'))],
                                                     ['Описание', descr[:300]]]}]}
        if neighbors:
            res['sections'].append({'title': 'Соседи (LLDP)', 'rows': [[f"порт {n['port']}", n['name']] for n in neighbors]})
        if vols:
            res['storage'] = {'volumes': vols, 'disks': []}
        return res
