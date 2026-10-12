"""Demo devices with realistic, made-up data (RL_DEMO=1). Lets people try Rack Live without hardware
and is used for the screenshots. Hidden from the "Add device" picker."""
import math, random, secrets, time

from . import Driver
from .. import cable, plugins, vps

T0 = time.time()
MAC = lambda n: 'aa:00:00:00:%02x:%02x' % (n // 256, n % 256)
ROUTER_MAC = MAC(1)
APS = [('ap1', 'Точка · Холл', '10.0.0.11', MAC(11)), ('ap2', 'Точка · Офис', '10.0.0.12', MAC(12)), ('ap3', 'Точка · Двор', '10.0.0.13', MAC(13))]
WIRED = [  # port, name, kind, ip, mac, vlan, speed, poeW
    (1, 'Камера · Вход', 'camera', '10.0.10.21', MAC(21), 10, 100, 3.4), (2, 'Камера · Парковка', 'camera', '10.0.10.22', MAC(22), 10, 100, 3.9),
    (3, 'Камера · Склад', 'camera', '10.0.10.23', MAC(23), 10, 100, 2.8), (4, 'Камера · Двор', 'camera', '10.0.10.24', MAC(24), 10, 100, 4.1),
    (5, 'Точка · Холл', 'ap', '10.0.0.11', MAC(11), 1, 1000, 6.2), (6, 'Точка · Офис', 'ap', '10.0.0.12', MAC(12), 1, 1000, 5.7),
    (7, 'Точка · Двор', 'ap', '10.0.0.13', MAC(13), 1, 1000, 6.9), (8, 'Хранилище', 'nas', '10.0.0.5', MAC(5), 1, 1000, 0),
    (9, 'Home Assistant', 'server', '10.0.0.6', MAC(6), 1, 1000, 0), (10, 'Принтер · Офис', 'printer', '10.0.0.40', MAC(40), 1, 100, 0),
    (11, 'ПК · Бухгалтерия', 'pc', '10.0.0.41', MAC(41), 1, 1000, 0), (12, 'ПК · Директор', 'pc', '10.0.0.42', MAC(42), 1, 100, 0),
    (14, 'Видеорегистратор', 'nvr', '10.0.10.5', MAC(15), 10, 1000, 0), (16, 'Телефон · Ресепшн', 'phone', '10.0.0.43', MAC(43), 1, 100, 2.1),
]
WIFI = [('iPhone · Анна', 'phone', 'ap1', -52), ('iPhone · Дмитрий', 'phone', 'ap2', -61), ('MacBook · Офис', 'laptop', 'ap2', -48),
        ('Galaxy · Сергей', 'phone', 'ap1', -67), ('iPad · Переговорная', 'tablet', 'ap2', -58), ('Телевизор · Холл', 'tv', 'ap1', -55),
        ('Колонка · Кухня', 'speaker', 'ap1', -63), ('Пылесос', 'iot', 'ap3', -71), ('Кондиционер', 'iot', 'ap3', -69),
        ('Ноутбук · Гость', 'laptop', 'ap3', -74), ('Pixel · Ольга', 'phone', 'ap2', -57), ('Термостат', 'iot', 'ap1', -60)]


def wave(t, period=86400, phase=0.0):
    """Daily activity curve 0..1: quiet at night, busy in the afternoon."""
    return max(0.05, (math.sin((t / period) * 2 * math.pi + phase) + 1) / 2)


class DemoBase(Driver):
    hidden = True
    fields = []

    def action(self, cfg, action_id, params):
        time.sleep(0.6)
        return {'poe_cycle': f"PoE на порту {params.get('port')} перезапущено (демо)", 'port_bounce': f"Порт {params.get('port')} перезапущен (демо)",
                'toggle': 'Готово', 'reboot': 'Перезагрузка (демо)', 'reboot_child': 'Точка перезагружается (демо)',
                'container_restart': f"Контейнер {params.get('name')} перезапущен (демо)"}.get(action_id, 'Готово (демо)')


class DemoRouter(DemoBase):
    id, title, kind = 'demo_router', 'Демо: роутер', 'router'
    actions = [{'id': 'reboot', 'label': 'Перезагрузить роутер', 'scope': 'device', 'confirm': 'Это демо — ничего не произойдёт. Продолжить?'},
               {'id': 'reboot_child', 'label': 'Перезагрузить точку', 'scope': 'child', 'confirm': 'Перезагрузить точку (демо)?'}]

    def poll(self, cfg):
        t = time.time()
        clients = [{'mac': m, 'ip': ip, 'name': n, 'segment': 'Камеры' if v == 10 else 'Основная', 'ap': None, 'port': '1', 'online': True, 'kind': k}
                   for _, n, k, ip, m, v, _, _ in WIRED if k not in ('ap',)]
        for i, (n, k, ap, rssi) in enumerate(WIFI):
            seg = 'IoT' if k in ('iot', 'speaker', 'tv') else ('Гости' if 'Гость' in n else 'Основная')
            clients.append({'mac': MAC(100 + i), 'ip': f'10.0.{20 if seg == "IoT" else 30 if seg == "Гости" else 0}.{100 + i}', 'name': n,
                            'segment': seg, 'ap': ap, 'rssi': rssi + random.randint(-2, 2), 'rate': random.choice([144, 286, 573, 866, 1201]),
                            'band': '5 ГГц' if rssi > -62 else '2.4 ГГц', 'online': True, 'kind': k})
        by = {}
        for c in clients:
            by[c['segment']] = by.get(c['segment'], 0) + 1
        return {'status': 'online',
                'summary': {'model': 'Keenetic Ultra (KN-1811)', 'fw': '4.3.6', 'uptime': int(t - T0 + 1_296_000), 'cpu': round(8 + 20 * wave(t)),
                            'mem': 38, 'ip': '10.0.0.1', 'mac': ROUTER_MAC},
                'ports': [{'n': 1, 'name': 'Gi0/0', 'kind': 'rj45', 'link': True, 'speed': 1000, 'vlansU': [1], 'vlansT': [10, 20, 30], 'label': 'Коммутатор', 'peers': []},
                          {'n': 2, 'name': 'Gi0/1', 'kind': 'rj45', 'link': False, 'speed': 0, 'vlansU': [1], 'vlansT': [], 'label': '', 'peers': []},
                          {'n': 3, 'name': 'Gi0/2', 'kind': 'rj45', 'link': False, 'speed': 0, 'vlansU': [1], 'vlansT': [], 'label': '', 'peers': []},
                          {'n': 4, 'name': 'Gi0/3', 'kind': 'rj45', 'link': False, 'speed': 0, 'vlansU': [1], 'vlansT': [], 'label': '', 'peers': []},
                          {'n': 5, 'name': 'WAN', 'kind': 'wan', 'link': True, 'speed': 1000, 'vlansU': [], 'vlansT': [], 'label': 'WAN · оптика', 'peers': [], 'ip': '203.0.113.24'}],
                'clients': clients, 'security': self._security(),
                'children': [{'key': k, 'name': n, 'kind': 'ap', 'model': 'Keenetic Orbiter Pro', 'ip': ip, 'mac': m, 'status': 'online',
                              'clients': sum(1 for w in WIFI if w[2] == k), 'uptime': int(t - T0 + 864_000), 'uplink': 1000, 'fw': '4.3.6'} for k, n, ip, m in APS],
                'vpn': self._vpn(t),
                'sections': [{'title': 'Сегменты', 'rows': [[k, f'{v} устр.'] for k, v in sorted(by.items(), key=lambda kv: -kv[1])]},
                             {'title': 'Интернет', 'rows': [['WAN IP', '203.0.113.24'], ['Провайдер', 'Оптика 1 Гбит/с']]}]}

    # security facts (see rackd/security.py): a few classic mistakes of a small office
    _closed = set()

    def _security(self):
        fw = [('tcp', '3389', MAC(41), 'RDP бухгалтерии'), ('tcp', '22', MAC(5), 'NAS SSH'), ('tcpudp', '32400', MAC(5), 'Plex')]
        return {'forwards': [{'proto': p, 'iface': 'GigabitEthernet1', 'port': port, 'target': t, 'toPort': port, 'name': n,
                              'rule': f'{p} GigabitEthernet1 {port} {t} {port}'} for p, port, t, n in fw if port not in self._closed],
                'remote': {'telnet': {'on': True, 'level': 'private' if 'telnet' in self._closed else 'public', 'port': 23},
                           'ssh': {'on': True, 'level': 'private', 'port': 22}, 'http': {'level': 'private'}},
                'upnp': True, 'update': {'available': True, 'title': '4.3.7', 'channel': 'stable'}}

    def action(self, cfg, action_id, params):
        if action_id == 'sec_fix':
            self._closed.add(params.get('service') or str(params.get('rule', '')).split()[2])
            return 'Исправлено (демо)'
        return super().action(cfg, action_id, params)

    # plugins: same catalog as Keenetic, simulated
    _tunnels = []

    def plugins(self, cfg):
        out = []
        for p in plugins.for_driver('keenetic'):
            if p['id'] == 'entware':
                p.update(checks=[{'label': 'Компонент «Поддержка открытых пакетов» (OPKG)', 'ok': True},
                                 {'label': 'Компонент «Модули ядра подсистемы Netfilter» (нужен HydraRoute)', 'ok': False, 'optional': True},
                                 {'label': 'Выбран накопитель для Entware', 'ok': True, 'hint': 'USB-флешка, ext4'},
                                 {'label': 'Entware установлен', 'ok': False}], installed=False, arch='aarch64',
                         installer=plugins.ENTWARE_INSTALLER['aarch64'])
            elif p['id'] == 'awg':
                p.update(checks=[{'label': 'Компонент «WireGuard VPN»', 'ok': True}], installed=bool(cfg.get('rlTunnels')), fw='4.3.6',
                         tunnels=[{'iface': 'Wireguard0', 'name': 'Офисный VPN', 'managed': False, 'groups': 0, 'domains': 0}] +
                                 [dict(t, managed=True, groups=1 if t.get('domains') else 0) for t in cfg.get('rlTunnels') or []])
            else:
                inst = plugins.INSTALLERS[p['id']]
                p.update(checks=[{'label': 'Entware установлен', 'ok': True}, {'label': 'Rack Live может зайти в Entware по SSH', 'ok': True}],
                         ssh={'set': True, 'ok': True, 'port': 222, 'user': 'root'}, url=f"http://10.0.0.1:{inst['port']}", login=inst['login'],
                         installed=p['id'] in self._installed, version=self._installed.get(p['id']))
            out.append(p)
        return {'model': 'Keenetic Ultra (KN-1811)', 'fw': '4.3.6', 'arch': 'aarch64', 'plugins': out}

    _installed = {}

    def plugin(self, cfg, pid, op, params):
        if pid in plugins.INSTALLERS:
            meta = next(p for p in plugins.CATALOG if p['id'] == pid)
            if op == 'ssh':
                return {'ok': True, 'message': 'SSH в Entware работает (aarch64, демо)'}
            time.sleep(1)
            if op == 'remove':
                self._installed.pop(pid, None)
                return {'ok': True, 'log': [], 'message': f"{meta['title']} удалён (демо)"}
            self._installed[pid] = '1.0.0-demo'
            url = f"http://10.0.0.1:{plugins.INSTALLERS[pid]['port']}"
            return {'ok': True, 'log': [{'cmd': 'opkg install …', 'ok': True, 'msg': ''}], 'version': '1.0.0-demo', 'url': url,
                    'message': f"{meta['title']} 1.0.0-demo установлен (демо). Панель: {url}"}
        if pid != 'awg':
            raise ValueError('этот плагин пока в разработке')
        if op == 'preview':
            c = plugins.parse_conf(params.get('conf'))
            doms, skipped = plugins.parse_domains(params.get('domains') or '')
            return {'ok': True, 'preview': plugins.conf_preview(c), 'domains': len(doms), 'skipped': skipped[:20]}
        if op == 'remove':
            return {'ok': True, 'log': [{'cmd': f"no interface {params.get('iface')}", 'ok': True, 'msg': 'removed (демо)'}],
                    'removed': params.get('iface'), 'message': f"Подключение {params.get('iface')} удалено (демо)"}
        if op == 'domains':
            doms, skipped = plugins.parse_domains(params.get('domains') or '')
            return {'ok': True, 'log': [], 'iface': params.get('iface'), 'domains': len(doms), 'skipped': skipped, 'message': f'Списки обновлены: {len(doms)} (демо)'}
        c = plugins.parse_conf(params.get('conf'))
        doms, skipped = plugins.parse_domains(params.get('domains') or '') if params.get('routing') else ([], [])
        time.sleep(1)
        iface = f"Wireguard{len(cfg.get('rlTunnels') or []) + 1}"
        name = params.get('name') or 'AmneziaWG'
        log = [{'cmd': f'interface {iface}', 'ok': True, 'msg': 'interface created (демо)'},
               {'cmd': f"interface {iface} wireguard peer … endpoint {c['peer']['endpoint']}", 'ok': True, 'msg': 'ok'}]
        if doms:
            log.append({'cmd': f'object-group fqdn rl_{iface.lower()}_1: +{len(doms)} сайтов', 'ok': True, 'msg': ''})
        return {'ok': True, 'log': log, 'iface': iface, 'name': name, 'domains': len(doms), 'skipped': skipped, 'up': True,
                'message': f'Подключение «{name}» ({iface}) создано (демо)'}

    def _vpn(self, t):
        gw = [('Ноутбук · Директор', '10.20.0.2', True, 40), ('iPhone · Директор', '10.20.0.3', True, 120),
              ('Дом · Склад', '10.20.0.4', True, 15), ('Ноутбук · Бухгалтер', '10.20.0.5', False, None)]
        peers = [{'name': n, 'online': on, 'endpoint': f'{85 + i * 7}.{12 + i}.{i * 9}.{40 + i}:51820' if on else None,
                  'subnet': ip, 'handshake': int(t - (hs or 0)) if on else None,
                  'rx': int(2e8 * (i + 1) * (.5 + .5 * wave(t))) if on else 0, 'tx': int(6e7 * (i + 1)) if on else 0}
                 for i, (n, ip, on, hs) in enumerate(gw)]
        return [
            {'id': 'wg0', 'name': 'Офисный VPN', 'kind': 'wireguard', 'role': 'server', 'up': True, 'address': '10.20.0.1',
             'routing': False, 'listenPort': 51820, 'endpoint': None, 'handshake': None,
             'rx': sum(p['rx'] for p in peers), 'tx': sum(p['tx'] for p in peers), 'peers': peers},
            {'id': 'wg1', 'name': 'Выход · Нидерланды', 'kind': 'wireguard', 'role': 'client', 'up': True, 'address': '10.8.1.2',
             'routing': True, 'endpoint': '194.5.53.17:51820', 'listenPort': None, 'peers': [],
             'rx': int(3.2e10 * (.6 + .4 * wave(t))), 'tx': int(1.6e9), 'handshake': int(t - 40)},
            {'id': 'ovpn', 'name': 'Бухгалтерия · банк', 'kind': 'openvpn', 'role': 'client', 'up': False, 'address': None,
             'routing': False, 'endpoint': 'vpn.bank.example:1194', 'listenPort': None, 'peers': [],
             'rx': None, 'tx': None, 'handshake': int(t - 7200)}]


class DemoOpenWrt(DemoBase):
    """Guest-network router on OpenWrt with an LTE modem: shows the OpenWrt plugins."""
    id, title, kind = 'demo_openwrt', 'Демо: OpenWrt', 'router'
    _installed = {'hilink'}
    _pkgs = {}

    def poll(self, cfg):
        t = time.time()
        return {'status': 'online', 'summary': {'model': 'Cudy WR3000', 'fw': 'OpenWrt 25.12.1', 'uptime': int(t - T0 + 400_000), 'cpu': 4, 'mem': 31, 'ip': '10.0.0.3'},
                'sections': [{'title': 'Интерфейсы', 'rows': [['lan', '▲ 10.0.40.1'], ['wwan', '▲ 192.168.0.100 · usb0 (LTE-модем)']]}]}

    def plugins(self, cfg):
        out = []
        for p in plugins.for_driver('openwrt'):
            p.update(pm='apk', fw='25.12.1')
            if p['id'] in plugins.OWRT_INSTALLERS:
                inst = plugins.OWRT_INSTALLERS[p['id']]
                p.update(installed=p['id'] in self._pkgs, version=self._pkgs.get(p['id']), ssh={'ok': True, 'native': True},
                         url=f"http://10.0.0.3/cgi-bin/luci/{inst['luci']}", login='логин и пароль от OpenWrt (LuCI)',
                         checks=[{'label': 'OpenWrt 24.10 или новее (у вас 25.12.1)', 'ok': True}, {'label': f"Свободно на флеше от {inst['freeMB']} МБ (сейчас 84 МБ)", 'ok': True},
                                 {'label': f"Не установлен {inst['conflict'].capitalize()} — они конфликтуют", 'ok': inst['conflict'] not in self._pkgs}])
                if p['id'] == 'forkop':
                    p['options'] = [{'id': 'extended', 'label': 'sing-box extended — поддержка XHTTP', 'on': True, 'hint': 'Без него XHTTP-ссылки не заработают.'}]
            else:
                p.update(usb=['12d1:14dc Huawei E3372h'], drivers=['cdc_ether'], devs=[], suggest='hilink', installed=bool(self._installed),
                         checks=[{'label': 'Модем подключён к USB: 12d1:14dc Huawei E3372h', 'ok': True}],
                         profiles=[dict(m, installed=m['id'] in self._installed, suggested=m['id'] == 'hilink') for m in plugins.MODEM_PROFILES])
            out.append(p)
        return {'fw': '25.12.1', 'pm': 'apk', 'plugins': out}

    def plugin(self, cfg, pid, op, params):
        time.sleep(.8)
        if pid == 'modem':
            (self._installed.add if op == 'install' else self._installed.discard)(params.get('profile'))
            return {'ok': True, 'log': [], 'message': f"{'Установлено' if op == 'install' else 'Удалено'} (демо)"}
        if op == 'remove':
            self._pkgs.pop(pid, None)
            return {'ok': True, 'log': [], 'message': f'{pid} удалён (демо)'}
        if plugins.OWRT_INSTALLERS[pid]['conflict'] in self._pkgs:
            raise ValueError('сначала удалите второй менеджер маршрутизации')
        self._pkgs[pid] = '0.7.9-r1'
        return {'ok': True, 'log': [{'cmd': 'apk add …', 'ok': True, 'msg': ''}], 'version': '0.7.9-r1',
                'url': f"http://10.0.0.3/cgi-bin/luci/{plugins.OWRT_INSTALLERS[pid]['luci']}", 'message': f'{pid} 0.7.9-r1 установлен (демо)'}


class DemoSwitch(DemoBase):
    id, title, kind = 'demo_switch', 'Демо: коммутатор', 'switch'
    actions = [{'id': 'poe_cycle', 'label': 'Перезапустить PoE', 'scope': 'port', 'needs': 'poe', 'confirm': 'Перезапустить PoE на порту {port}? (демо)'},
               {'id': 'port_bounce', 'label': 'Перезапустить порт', 'scope': 'port', 'confirm': 'Перезапустить порт {port}? (демо)'},
               {'id': 'cable_test', 'label': 'Проверить кабель', 'scope': 'port', 'kind': 'cable', 'confirm': 'Измерить кабель на порту {port}? (демо)'}]

    def action(self, cfg, action_id, params):
        if action_id != 'cable_test':
            return super().action(cfg, action_id, params)
        time.sleep(1.5)
        n = int(params.get('port') or 0)
        p = next((x for x in self.poll(cfg)['ports'] if x['n'] == n), None)
        if not p:
            raise ValueError('нет такого порта')
        L = 6 + (n * 7) % 38
        if n == 12:      # the demo office's flaky cable: two pairs badly crimped at the rack end
            run = [{'pair': 'A', 'status': 'normal', 'len': L}, {'pair': 'B', 'status': 'normal', 'len': L},
                   {'pair': 'C', 'status': 'open', 'len': 1}, {'pair': 'D', 'status': 'open', 'len': 1}]
        elif p['link']:
            run = [{'pair': x, 'status': 'normal', 'len': L + random.randint(-1, 1)} for x in 'ABCD']
        else:
            far = 0 if n % 3 else L
            run = [{'pair': x, 'status': 'open', 'len': far} for x in 'ABCD']
        res = cable.analyze([run], p['link'], p['speed'])
        return {'message': f'Порт {n}: ' + res['text'], 'cable': res, 'port': n}

    def poll(self, cfg):
        t = time.time()
        ports = []
        for n in range(1, 29):
            ports.append({'n': n, 'name': f'Gi1/0/{n}', 'kind': 'sfp' if n > 24 else 'rj45', 'link': False, 'speed': 0, 'poeW': 0, 'poe': n <= 24,
                          'label': '', 'vlansU': [1], 'vlansT': [], 'peers': [], 'disabled': False})
        for port, name, kind, ip, mac, vlan, speed, poe in WIRED:
            p = ports[port - 1]
            p.update(link=True, speed=speed, poeW=poe, label=name, vlansU=[vlan], vlansT=[20, 30] if kind == 'ap' else [], peers=[{'mac': mac, 'vlan': vlan}])
            if kind == 'ap':
                key = next(a[0] for a in APS if a[3] == mac)
                p['peers'] += [{'mac': MAC(100 + i), 'vlan': 1} for i, w in enumerate(WIFI) if w[2] == key]
        up = ports[23]
        up.update(link=True, speed=1000, label='Uplink · роутер', vlansU=[1], vlansT=[10, 20, 30], peers=[{'mac': ROUTER_MAC, 'vlan': 1}] +
                  [{'mac': MAC(100 + i), 'vlan': 1} for i in range(len(WIFI))])
        ports[24].update(link=True, speed=10000, label='SFP+ · сервер', kind='sfp', peers=[])
        for p in ports:
            if p['link']:
                base = {'camera': 4e6, 'nvr': 25e6, 'nas': 60e6, 'ap': 35e6}.get(next((w[2] for w in WIRED if w[0] == p['n']), ''), 3e6)
                if p['n'] == 24:
                    base = 180e6
                # monotonic counters: the rate between two polls is the current point of the daily curve
                age = t - T0
                p['rxBytes'] = int(9e12 + age * base * (.3 + .7 * wave(t)) / 8)
                p['txBytes'] = int(4e12 + age * base * .35 * (.3 + .7 * wave(t, phase=1)) / 8)
            if p['kind'] == 'rj45':
                # port 11 has a cable that links at 1 Gbit but keeps producing CRC errors; port 10 had a few once
                crc = int(1200 + (t - T0) / 60 * 2.5) if p['n'] == 11 else 3 if p['n'] == 10 else 0
                p.update(inErrors=crc, outErrors=0, crc=crc)
        poe = sum(p['poeW'] for p in ports)
        return {'status': 'online',
                'summary': {'model': 'JetStream 24-Port Gigabit L2+ PoE+ Switch', 'fw': '4.0.5', 'uptime': int(t - T0 + 2_592_000), 'ip': '10.0.0.2', 'mac': MAC(2)},
                'ports': ports, 'metrics': [{'label': 'Порты с линком', 'value': f"{sum(1 for p in ports if p['link'])}/28"}, {'label': 'PoE', 'value': round(poe, 1), 'unit': 'Вт'}],
                'sections': [{'title': 'Коммутатор', 'rows': [['Модель', 'T2600G-28MPS'], ['PoE-бюджет', '384 Вт']]}]}


class DemoNas(DemoBase):
    id, title, kind = 'demo_nas', 'Демо: NAS', 'nas'
    actions = [{'id': 'container_restart', 'label': 'Перезапустить контейнер', 'scope': 'service', 'confirm': 'Перезапустить {name}? (демо)'}]

    def poll(self, cfg):
        t = time.time()
        return {'status': 'online',
                'summary': {'model': 'DS920+', 'fw': 'DSM 7.2.2', 'uptime': int(t - T0 + 3_888_000), 'cpu': round(6 + 25 * wave(t, phase=.5)), 'mem': 41,
                            'temp': 44 + round(4 * wave(t)), 'ip': '10.0.0.5', 'mac': MAC(5)},
                'ports': [{'n': 1, 'name': 'eth0', 'kind': 'rj45', 'link': True, 'speed': 1000, 'label': '10.0.0.5', 'vlansU': [], 'vlansT': [], 'peers': []},
                          {'n': 2, 'name': 'eth1', 'kind': 'rj45', 'link': True, 'speed': 1000, 'label': '10.0.0.7', 'vlansU': [], 'vlansT': [], 'peers': []}],
                'storage': {'volumes': [{'name': 'Том 1 · SHR', 'status': 'normal', 'used': 9.3e12, 'total': 16e12},
                                        {'name': 'Том 2 · SSD-кэш', 'status': 'normal', 'used': 0.31e12, 'total': 0.96e12}],
                            'disks': [{'name': f'Диск {i}', 'model': 'WD Red Plus 8TB' if i < 5 else 'Samsung 990 EVO 1TB', 'kind': 'hdd' if i < 5 else 'ssd',
                                       'sizeGB': 8000 if i < 5 else 1000, 'temp': 37 + i, 'status': 'normal'} for i in range(1, 6)]},
                'services': [{'name': n, 'state': s} for n, s in [('immich', 'running'), ('nextcloud', 'running'), ('vaultwarden', 'running'),
                                                                   ('jellyfin', 'running'), ('paperless', 'running'), ('backup-runner', 'exited')]],
                'sections': [{'title': 'Система', 'rows': [['Серийный номер', 'DEMO-0001'], ['Оперативная память', '20480 МБ']]}]}


class DemoHA(DemoBase):
    id, title, kind = 'demo_ha', 'Демо: Home Assistant', 'server'
    actions = [{'id': 'toggle', 'label': 'Переключить', 'scope': 'entity', 'instant': True}]
    _state = {}

    def poll(self, cfg):
        ents = [('light.hall', 'Свет · Холл'), ('light.office', 'Свет · Офис'), ('switch.boiler', 'Бойлер'), ('switch.gate', 'Ворота'),
                ('light.yard', 'Фонари · Двор'), ('switch.server_fan', 'Вентилятор шкафа')]
        out = [{'id': e, 'name': n, 'state': self._state.get(e, 'on' if i % 2 == 0 else 'off')} for i, (e, n) in enumerate(ents)]
        return {'status': 'online', 'summary': {'model': 'Home Assistant', 'fw': '2026.9.4', 'ip': '10.0.0.6', 'mac': MAC(6)},
                'metrics': [{'label': 'Объекты', 'value': 214}, {'label': 'Недоступно', 'value': 0}, {'label': 'Автоматизации', 'value': 37}],
                'entities': out}

    def action(self, cfg, action_id, params):
        e = params.get('entity')
        cur = next((x['state'] for x in self.poll(cfg)['entities'] if x['id'] == e), 'off')
        self._state[e] = 'off' if cur == 'on' else 'on'
        return 'Готово'


class DemoServer(DemoBase):
    id, title, kind = 'demo_server', 'Демо: удалённый сервер', 'server'
    actions = [{'id': 'iperf', 'label': 'Тест скорости (iperf3)', 'scope': 'device', 'kind': 'speed',
                'confirm': 'Измерить скорость до сервера в обе стороны? (демо)'}]

    # VPS panels, simulated: the same stages as the real installer
    async_ops = ('install', 'remove')
    _panels = {}

    def plugins(self, cfg):
        out = []
        for p in vps.CATALOG:
            p = dict(p, installed=p['id'] in self._panels, ip='198.51.100.40', info=(cfg.get('panelInfo') or {}).get(p['id']),
                     checks=[{'label': 'Ubuntu или Debian (у вас Ubuntu 24.04 LTS)', 'ok': True}, {'label': 'Вход под root', 'ok': True},
                             {'label': 'Память от 400 МБ (у вас 1987 МБ)', 'ok': True}, {'label': 'Внешний IP определён: 198.51.100.40', 'ok': True},
                             {'label': 'Порты 80 и 443 свободны (или заняты nginx)', 'ok': True},
                             {'label': 'Не установлена вторая панель — две панели на одном сервере конфликтуют', 'ok': not (set(self._panels) - {p['id']})}])
            out.append(p)
        return {'os': 'Ubuntu 24.04 LTS', 'ip': '198.51.100.40', 'plugins': out}

    def plugin(self, cfg, pid, op, params):
        progress = params.get('_progress') or (lambda s: None)
        if op == 'dns':
            dom = vps.clean_domain(params.get('domain'))
            ok = dom.endswith('example.com')
            return {'ok': True, 'domain': dom, 'ip': '198.51.100.40', 'records': ['198.51.100.40'] if ok else [], 'match': ok}
        if op == 'remove':
            progress('Удаление (демо)'); time.sleep(.5)
            self._panels.pop(pid, None)
            return {'ok': True, 'log': [], 'removed': pid, 'message': f'{pid} удалён (демо)'}
        if (set(self._panels) - {pid}):
            raise ValueError('на сервере уже стоит другая панель — сначала удалите её')
        dom = vps.clean_domain(params.get('domain')) if params.get('withDomain') else ''
        for s in (['Проверка DNS', "nginx, сайт-заглушка и сертификат Let's Encrypt"] if dom else []) + [f'Установка {pid} (демо)'] + \
                (['Инбаунды VLESS TCP + XHTTP и тестовый пользователь'] if params.get('inbounds') and dom else []):
            progress(s)
            time.sleep(.6)
        self._panels[pid] = '2.6.0'
        uid = '1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed'
        links = [{'name': 'VLESS TCP TLS', 'url': f'vless://{uid}@{dom}:8443?type=tcp&security=tls&sni={dom}&fp=chrome&flow=xtls-rprx-vision#RL-TCP'},
                 {'name': 'VLESS XHTTP TLS', 'url': f'vless://{uid}@{dom}:2053?type=xhttp&security=tls&sni={dom}&fp=chrome&path=/xh7k2m&mode=auto#RL-XHTTP'}] \
            if params.get('inbounds') and dom else []
        info = {'url': f'https://{dom}/k3v9q2m7x4p8w1z6/' if dom else 'https://198.51.100.40:41873/k3v9q2m7x4p8w1z6/', 'user': 'rq7m2k9x4p',
                'password': 'Xk29fLq8Zr4Mn7Pw3Ty6', 'domain': dom or None, 'links': links, 't': int(time.time())}
        return {'ok': True, 'log': [{'cmd': '— демо-установка', 'ok': True, 'msg': ''}], 'info': info, 'message': f'{pid} установлен (демо)'}

    def action(self, cfg, action_id, params):
        if action_id != 'iperf':
            return super().action(cfg, action_id, params)
        time.sleep(2)
        down, up = round(random.uniform(280, 320), 1), round(random.uniform(85, 95), 1)
        return {'message': f'iperf3 до 198.51.100.40: к устройству {up} Мбит/с, от устройства {down} Мбит/с',
                'speedtest': {'down': down, 'up': up, 'retr': random.randint(0, 40), 'host': '198.51.100.40'}}

    def poll(self, cfg):
        t = time.time()
        return {'status': 'online', 'summary': {'model': 'vps-frankfurt', 'fw': 'Ubuntu 24.04 LTS', 'uptime': int(t - T0 + 5_184_000),
                                                'cpu': round(12 + 30 * wave(t, phase=2)), 'mem': 63, 'ip': '198.51.100.40'},
                'metrics': [{'label': 'Нагрузка', 'value': 0.42}],
                'storage': {'volumes': [{'name': '/', 'status': 'normal', 'used': 41e9, 'total': 80e9}], 'disks': []},
                'services': [{'name': 'nginx', 'state': 'Up 12 days'}, {'name': 'wireguard', 'state': 'Up 12 days'}, {'name': 'uptime-kuma', 'state': 'Up 3 days'}]}


class DemoSite(DemoBase):
    id, title, kind = 'demo_site', 'Демо: сайт', 'web'

    def poll(self, cfg):
        return {'status': 'online', 'summary': {'ip': 'example.com'},
                'metrics': [{'label': 'Ответ', 'value': 200}, {'label': 'Время', 'value': random.randint(90, 160), 'unit': 'мс'},
                            {'label': 'Сертификат', 'value': 74, 'unit': 'дн.'}]}


def seed(store):
    """Fill an empty config with the demo office: devices, rack, VLANs and 24h of history."""
    if store.cfg['devices']:
        return
    D = lambda **k: store.cfg['devices'].append(dict({'id': 'demo' + secrets.token_hex(3), 'enabled': True, 'location': 'local'}, **k)) or store.cfg['devices'][-1]['id']
    r = D(name='Роутер', driver='demo_router', kind='router', host='10.0.0.1')
    s = D(name='Коммутатор ядра', driver='demo_switch', kind='switch', host='10.0.0.2')
    n = D(name='Хранилище', driver='demo_nas', kind='nas', host='10.0.0.5')
    h = D(name='Home Assistant', driver='demo_ha', kind='server', host='10.0.0.6')
    D(name='Гостевой роутер · LTE', driver='demo_openwrt', kind='router', host='10.0.0.3')
    D(name='VPS · Франкфурт', driver='demo_server', kind='server', host='198.51.100.40', location='remote', site='Облако')
    D(name='Сайт компании', driver='demo_site', kind='web', host='https://example.com', location='remote', site='Облако')
    ups = D(name='ИБП 1500 ВА', driver='ups', kind='ups', mode='manual', powerW='900', batteryV='12', batteryAh='9', batteryCount='2',
            connected=[r, s, n], extraW='15', extraNote='оптический терминал и мелочь')
    U = lambda **k: dict({'id': 'u' + secrets.token_hex(3), 'side': 'front', 'notes': '', 'deviceId': None}, **k)
    rooms = ['Вход', 'Парковка', 'Склад', 'Двор', 'Холл', 'Офис', 'Двор, столб', 'Серверная', 'Серверная', 'Кабинет 1', 'Бухгалтерия', 'Директор']
    patch = {'count': 24, 'ports': {str(i): {'label': f'{rooms[i - 1]}' + (', розетка ' + str(i) if i > 9 else ''), 'dev': s, 'port': str(i)}
                                    for i in range(1, 13)}}
    cross = {'count': 8, 'connector': 'SC', 'fiber': 'SM', 'ports': {
        '1': {'color': 'синий', 'label': 'Провайдер, ввод', 'note': 'к оптическому терминалу', 'db': '0.4'},
        '2': {'color': 'оранжевый', 'label': 'Склад, ОКЛ-4', 'dev': s, 'port': '25', 'db': '0.6'},
        '3': {'color': 'зелёный', 'label': 'Склад, ОКЛ-4', 'note': 'резерв'}, '4': {'color': 'коричневый', 'label': 'Склад, ОКЛ-4', 'note': 'резерв'}}}
    store.cfg['racks'] = [{'id': 'rack0', 'name': 'Серверная', 'totalU': 15, 'units': [
        U(id='ucross', name='Оптический кросс', type='cross', uSize=1, uStart=1, color='#ffd60a', portmap=cross),
        U(name='Роутер', type='router', uSize=1, uStart=2, color='#0a84ff', deviceId=r),
        U(name='Патч-панель 24', type='patch', uSize=1, uStart=3, color='#8e8e93', portmap=patch),
        U(name='Коммутатор ядра', type='switch', uSize=1, uStart=4, color='#30d158', deviceId=s),
        U(name='Органайзер', type='organizer', uSize=1, uStart=5, color='#8e8e93'),
        U(name='Хранилище', type='nas', uSize=2, uStart=6, color='#64d2ff', deviceId=n),
        U(name='Полка', type='shelf', uSize=1, uStart=8, color='#8e8e93'),
        U(id='uont', name='Оптический терминал', type='modem', uSize=1, uStart=10, color='#bf5af2', portmap={'count': 5, 'ports': {
            '1': {'name': 'PON', 'label': 'оптика провайдера', 'dev': 'u:ucross', 'port': '1'},
            '2': {'name': 'LAN1', 'label': 'к роутеру', 'dev': r, 'port': '5'},
            '3': {'name': 'LAN2'}, '4': {'name': 'LAN3'}, '5': {'name': 'TEL'}}}),
        U(name='ИБП 1500 ВА', type='ups', uSize=2, uStart=13, color='#ff9f0a', deviceId=ups)]},
        {'id': 'rack1', 'name': 'Этаж 2 · щиток', 'kind': 'box', 'totalU': 1, 'units': [
            U(name='Home Assistant', type='server', uStart=1, color='#5e5ce6', deviceId=h),
            U(name='Патч-панель 12', type='patch', uStart=2, color='#8e8e93'),
            U(name='PoE-инжектор', type='other', uStart=3, color='#ffd60a'),
            U(name='ИБП 650 ВА', type='ups', uStart=4, color='#ff9f0a')]}]
    store.cfg['settings'].update(title='Офис · серверная', publicView=True, vlans=[
        {'vid': 1, 'name': 'Основная', 'color': '#0A84FF'}, {'vid': 10, 'name': 'Камеры', 'color': '#FF453A'},
        {'vid': 20, 'name': 'IoT', 'color': '#30D158'}, {'vid': 30, 'name': 'Гости', 'color': '#BF5AF2'}])
    I = lambda **k: dict({'id': 'i' + secrets.token_hex(3)}, **k)
    R = lambda **k: dict({'id': 'r' + secrets.token_hex(3), 'color': '#0a84ff'}, **k)
    store.cfg['plan'] = {'poles': [{'id': 'p1', 'name': 'Столб у дороги', 'x': 820, 'y': 120}],
                         'links': [{'id': 'l1', 'from': 'b1', 'to': 'b2', 'label': 'Оптика 10 Гбит', 'via': {'unit': 'ucross', 'port': 2}},
                                   {'id': 'l2', 'from': 'p1', 'to': 'b2', 'label': 'Воздушка от провайдера'}], 'buildings': [
        {'id': 'b1', 'name': 'Главный офис', 'x': 40, 'y': 40, 'floors': [
            {'id': 'f1', 'name': '1 этаж',
             'rooms': [R(x=0, y=0, w=240, h=220, text='Серверная', color='#0a84ff'), R(x=240, y=0, w=240, h=220, text='Кабинет', color='#30d158')],
             'walls': [], 'items': [I(kind='place', ref='rack0', x=120, y=90), I(kind='place', ref='rack1', x=360, y=90),
                                    I(kind='device', ref=r, x=120, y=170), I(kind='device', ref=n, x=200, y=170), I(kind='device', ref=h, x=360, y=170)]},
            {'id': 'f1b', 'name': '2 этаж',
             'rooms': [R(x=0, y=0, w=240, h=220, text='Переговорная', color='#bf5af2'), R(x=240, y=0, w=240, h=220, text='Кабинет 2', color='#ff9f0a')],
             'walls': [], 'items': []},
            {'id': 'yard', 'name': 'Двор', 'outdoor': True,
             'rooms': [R(x=0, y=0, w=300, h=200, text='Парковка', color='#8e8e93')], 'walls': [], 'items': []}]},
        {'id': 'b2', 'name': 'Склад', 'x': 420, 'y': 300, 'floors': [
            {'id': 'f2', 'name': '1 этаж', 'rooms': [R(x=0, y=0, w=200, h=160, text='Приёмка', color='#ff9f0a')], 'walls': [], 'items': []}]}]}
    now = int(time.time())
    for i in range(288):
        tt = now - (287 - i) * 300
        store.history.setdefault(n, []).append({'t': tt, 't0': tt, 'cpu': round(6 + 25 * wave(tt, phase=.5) + 2 * math.sin(i / 4)), 'mem': 40 + round(math.sin(i / 20)), 'temp': 44 + round(4 * wave(tt))})
        store.history.setdefault(r, []).append({'t': tt, 't0': tt, 'cpu': round(8 + 20 * wave(tt) + 2 * math.sin(i / 5)), 'mem': 38})
        for port, base in ((1, 4e6), (5, 35e6), (8, 60e6), (14, 25e6), (24, 180e6)):
            jitter = 1 + .06 * math.sin(i / 3.0 + port) + random.uniform(-.03, .03)
            store.history.setdefault(f'{s}:p{port}', []).append({'t': tt, 't0': tt, 'rx': int(base * (.3 + .7 * wave(tt)) * jitter),
                                                                 'tx': int(base * .35 * (.3 + .7 * wave(tt, phase=1)) * jitter)})
        store.history.setdefault(f'{s}:p11', []).append({'t': tt, 't0': tt, 'err': random.randint(8, 16)})
    # Wi-Fi coverage: browser speed tests pinned on the plan
    tests = [('f1', 120, 40, 612, 540, 3, 'ap1', '5 ГГц', -45, 'iPhone · Анна'), ('f1', 380, 60, 421, 377, 4, 'ap2', '5 ГГц', -55, 'MacBook · Офис'),
             ('f1', 450, 200, 158, 117, 6, 'ap2', '5 ГГц', -68, 'iPhone · Дмитрий'), ('f1b', 100, 100, 236, 198, 5, 'ap2', '5 ГГц', -63, 'iPad · Переговорная'),
             ('f1b', 430, 180, 54, 38, 11, 'ap2', '2.4 ГГц', -74, 'Pixel · Ольга'), ('yard', 60, 40, 88, 64, 9, 'ap3', '2.4 ГГц', -70, 'Galaxy · Сергей'),
             ('yard', 260, 170, 11.5, 5.8, 24, 'ap3', '2.4 ГГц', -82, 'Galaxy · Сергей')]
    ap_name = {k: n for k, n, _, _ in APS}
    store._dump('speedtests.json', [{'id': 's' + secrets.token_hex(4), 't': now - (len(tests) - i) * 5400, 'kind': 'browser',
                                     'down': dn, 'up': upl, 'ping': png, 'jitter': round(png / 3, 1), 'note': '',
                                     'where': {'b': 'b1', 'f': f, 'x': x, 'y': y},
                                     'client': {'ip': '10.0.0.' + str(100 + i), 'name': who, 'wifi': True, 'apName': ap_name[ap], 'band': band, 'rssi': rssi,
                                                'rate': 866 if band.startswith('5') else 144}}
                                    for i, (f, x, y, dn, upl, png, ap, band, rssi, who) in enumerate(tests)])
    store.add_event(None, 'Камера · Склад', 'offline', 'нет связи: не отвечает')
    store.add_event(s, 'Коммутатор ядра', 'info', 'PoE на порту 3 перезапущено')
    store.add_event(None, 'Камера · Склад', 'online', 'снова в сети')
    res = DemoSwitch().action({}, 'cable_test', {'port': 12})
    res['cable']['t'] = now - 3600
    store.set_cable(s, 12, res['cable'])
    store.add_event(s, 'Коммутатор ядра', 'warning', res['message'])
    store.save()
    store.save_runtime()
