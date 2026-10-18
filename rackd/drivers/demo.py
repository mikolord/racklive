"""Demo devices with realistic, made-up data (RL_DEMO=1). Lets people try Rack Live without hardware
and is used for the screenshots. Hidden from the "Add device" picker."""
from ..util import DriverError
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

    shell = 'демо-CLI (ничего не меняет): show …, любые команды'

    def command(self, cfg, cmd):
        time.sleep(0.3)
        return '\n\n'.join(f'> {c}\n(демо) выполнено, password secret123' for c in cmd.split('\n') if c.strip())


class DemoRouter(DemoBase):
    id, title, kind = 'demo_router', 'Демо: роутер', 'router'
    actions = [{'id': 'reboot', 'label': 'Перезагрузить роутер', 'scope': 'device', 'confirm': 'Это демо — ничего не произойдёт. Продолжить?'},
               {'id': 'reboot_child', 'label': 'Перезагрузить точку', 'scope': 'child', 'confirm': 'Перезагрузить точку (демо)?'}]

    OVR = {}                                     # demo: what «настроить клиента» changed, by MAC

    def client(self, cfg, mac, want):
        o = self.OVR.setdefault(str(mac).lower(), {})
        if want.get('forget'):
            self.OVR[str(mac).lower()] = {'registered': False}
            return ['регистрация снята (демо)']
        done = []
        if want.get('name'):
            o.update(name=want['name'], registered=True); done.append(f"имя «{want['name']}»")
        if want.get('ip'):
            cur = next((c for c in self.poll(cfg)['clients'] if c['mac'] == str(mac).lower()), {})
            if cur.get('ip') and want['ip'].rsplit('.', 1)[0] != cur['ip'].rsplit('.', 1)[0]:
                raise DriverError(f"адрес {want['ip']} не из сети этого устройства ({cur['ip'].rsplit('.', 1)[0]}.0/24)")
            if want['ip'].endswith(('.0', '.1', '.255')):
                raise DriverError(f"{want['ip']} — служебный адрес сети или адрес роутера, выберите другой")
        if 'ip' in want:
            o['ip'] = want['ip'] or None; done.append(f"постоянный адрес {want['ip']}" if want['ip'] else 'постоянный адрес снят')
        if 'limit' in want:
            o['limit'] = float(want['limit'] or 0); done.append(f"скорость до {o['limit']:g} Мбит/с" if o['limit'] else 'без ограничения')
        if 'policy' in want:
            o['policy'] = want['policy'] or None; done.append({'deny': 'интернет запрещён', '': 'политика по умолчанию'}.get(want['policy'] or '', f"политика {want['policy']}"))
        return done

    def poll(self, cfg):
        t = time.time()
        clients = [{'mac': m, 'ip': ip, 'name': n, 'segment': 'Камеры' if v == 10 else 'Основная', 'ap': None, 'port': '1', 'online': True, 'kind': k}
                   for _, n, k, ip, m, v, _, _ in WIRED if k not in ('ap',)]
        for i, (n, k, ap, rssi) in enumerate(WIFI):
            seg = 'IoT' if k in ('iot', 'speaker', 'tv') else ('Гости' if 'Гость' in n else 'Основная')
            clients.append({'mac': MAC(100 + i), 'ip': f'10.0.{20 if seg == "IoT" else 30 if seg == "Гости" else 0}.{100 + i}', 'name': n,
                            'segment': seg, 'ap': ap, 'rssi': rssi + random.randint(-2, 2), 'rate': random.choice([144, 286, 573, 866, 1201]),
                            'band': '5 ГГц' if rssi > -62 else '2.4 ГГц', 'online': True, 'kind': k})
        # someone's own router behind ours (a guest house): shows up in «Роутеры в сети»
        clients.append({'mac': '80:af:ca:00:00:99', 'ip': '10.0.30.150', 'name': 'Гостевой домик', 'hostname': 'WR3000E', 'segment': 'Гости',
                        'ap': None, 'port': '1', 'online': True, 'kind': 'router'})
        segid = {'Основная': 'Bridge0', 'Камеры': 'Bridge1', 'IoT': 'Bridge2', 'Гости': 'Bridge3'}
        for c in clients:                       # registration / static IP / limit / policy, as the real driver reports them
            o = self.OVR.get(c['mac'], {})
            c.update(segId=segid.get(c['segment']), registered=o.get('registered', c['segment'] != 'Гости'), access='deny' if o.get('policy') == 'deny' else 'permit',
                     policy=o.get('policy') if o.get('policy') not in (None, 'deny') else '', staticIp=o.get('ip'), limit=o.get('limit', 0))
            if o.get('name'):
                c['name'] = o['name']
        by = {}
        for c in clients:
            by[c['segment']] = by.get(c['segment'], 0) + 1
        return {'status': 'online',
                'networks': [{'id': 'Bridge0', 'name': 'Основная', 'alias': 'Home', 'vlan': 1, 'ip': '10.0.0.1', 'mask': '255.255.255.0'},
                             {'id': 'Bridge1', 'name': 'Камеры', 'alias': '', 'vlan': 10, 'ip': '10.0.10.1', 'mask': '255.255.255.0'},
                             {'id': 'Bridge2', 'name': 'IoT', 'alias': '', 'vlan': 20, 'ip': '10.0.20.1', 'mask': '255.255.255.0'},
                             {'id': 'Bridge3', 'name': 'Гости', 'alias': '', 'vlan': 30, 'ip': '10.0.30.1', 'mask': '255.255.255.0'}],
                'policies': [{'id': 'Policy0', 'name': 'VPN'}, {'id': 'Policy1', 'name': 'Без VPN'}],
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

    def backup(self, cfg):
        fw = '\n'.join(f"ip static {f['rule']} !{f['name']}" for f in self._security()['forwards'])
        return f'! $$$ Model: Keenetic Ultra\n! $$$ Last change: {time.ctime()}\nsystem\n    hostname Office\n!\n{fw}\nip telnet\n    port 23\n!\n'

    def inet_test(self, cfg, iface):
        time.sleep(.5)
        return {'down': round(random.uniform(280, 340), 1), 'up': round(random.uniform(60, 90), 1), 'ping': round(random.uniform(38, 45), 1),
                'server': 'Cloudflare AMS', 'ip': '194.5.53.17', 'loc': 'NL'}

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
                'sections': [{'title': 'Интерфейсы', 'rows': [['lan', '▲ 10.0.40.1'], ['wwan', '▲ 192.168.0.100 · usb0 (LTE-модем)']]}],
                # a guest router with a captive portal: client settings are switched off here on purpose
                'networks': [{'id': 'lan', 'name': 'lan', 'alias': 'br-lan', 'vlan': None, 'ip': '10.0.40.1', 'mask': '255.255.255.0'}],
                'clients': [{'mac': 'ee:40:00:00:00:0' + str(i), 'ip': f'10.0.40.{10 + i}', 'name': n, 'segment': 'lan', 'segId': 'lan', 'registered': False,
                             'access': 'permit', 'policy': '', 'limit': 0, 'online': True, 'kind': 'phone'} for i, n in enumerate(('Гость-1', 'Гость-2'))],
                'clientMgmt': {'ok': False, 'reason': 'на роутере работает captive-портал OpenNDS — он сам управляет доступом клиентов; чтобы ничего не сломать, '
                                                      'настройки клиентов из Rack Live на этом роутере отключены'},
                'clientCaps': {'limit': False, 'policy': False, 'deny': True}}

    def client(self, cfg, mac, want):
        raise DriverError('на роутере captive-портал OpenNDS — настройки клиентов из Rack Live отключены (демо)')

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


DEMO_LOOP = {'guard': False, 'sim': False}      # the demo switch: loop protection on/off, and a pretend loop on ports 15 and 17


class DemoSwitch(DemoBase):
    id, title, kind = 'demo_switch', 'Демо: коммутатор', 'switch'
    actions = [{'id': 'poe_cycle', 'label': 'Перезапустить PoE', 'scope': 'port', 'needs': 'poe', 'confirm': 'Перезапустить PoE на порту {port}? (демо)'},
               {'id': 'port_bounce', 'label': 'Перезапустить порт', 'scope': 'port', 'confirm': 'Перезапустить порт {port}? (демо)'},
               {'id': 'cable_test', 'label': 'Проверить кабель', 'scope': 'port', 'kind': 'cable', 'confirm': 'Измерить кабель на порту {port}? (демо)'},
               {'id': 'loop_guard', 'label': 'Включить защиту от петель', 'scope': 'device', 'confirm': 'Включить защиту от петель? (демо)'},
               {'id': 'loop_guard_off', 'label': 'Выключить защиту от петель', 'scope': 'device', 'confirm': 'Выключить защиту от петель? (демо)'},
               {'id': 'loop_recover', 'label': 'Вернуть порт после петли', 'scope': 'port', 'confirm': 'Вернуть порт {port}? (демо)'},
               {'id': 'loop_demo', 'label': 'Демо: показать/убрать петлю', 'scope': 'device', 'confirm': 'Показать в демо воображаемую петлю на портах 15 и 17?'}]

    def action(self, cfg, action_id, params):
        if action_id in ('loop_guard', 'loop_guard_off'):
            DEMO_LOOP['guard'] = action_id == 'loop_guard'
            return 'Защита от петель включена на портах 1–23 (демо)' if DEMO_LOOP['guard'] else 'Защита от петель выключена (демо)'
        if action_id == 'loop_demo':
            DEMO_LOOP['sim'] = not DEMO_LOOP['sim']
            return 'Воображаемая петля ' + ('появилась' if DEMO_LOOP['sim'] else 'убрана')
        if action_id == 'loop_recover':
            DEMO_LOOP['sim'] = False
            return f"Порт {params.get('port')} возвращён (демо)"
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
        on, sim = DEMO_LOOP['guard'], DEMO_LOOP['sim']
        gp = {}
        for p in ports:
            guarded = on and p['n'] <= 23                         # port 24 is the uplink: not touched
            hit = sim and p['n'] in (15, 17)
            p.update(loopOn=guarded, loopDetected=hit and guarded, loopBlocked=hit and guarded)
            if hit:
                p['bcastPps'] = 18000 + p['n'] * 130              # a storm: tens of thousands of broadcast frames a second
            gp[p['n']] = {'on': guarded, 'mode': 'port-based' if guarded else 'alert', 'loop': p['loopDetected'], 'blocked': p['loopBlocked']}
        guard = {'supported': True, 'enabled': on, 'interval': 30, 'recoveryTime': 90, 'ports': gp, 'onPorts': sum(1 for v in gp.values() if v['on'])}
        return {'status': 'online', 'loopGuard': guard,
                'summary': {'model': 'JetStream 24-Port Gigabit L2+ PoE+ Switch', 'fw': '4.0.5', 'uptime': int(t - T0 + 2_592_000), 'ip': '10.0.0.2', 'mac': MAC(2)},
                'ports': ports, 'metrics': [{'label': 'Порты с линком', 'value': f"{sum(1 for p in ports if p['link'])}/28"}, {'label': 'PoE', 'value': round(poe, 1), 'unit': 'Вт'}],
                'sections': [{'title': 'Коммутатор', 'rows': [['Модель', 'T2600G-28MPS'], ['PoE-бюджет', '384 Вт']]}]}


class DemoNas(DemoBase):
    id, title, kind = 'demo_nas', 'Демо: NAS', 'nas'

    def surveillance(self, cfg):
        cams = [(10, 'Проход', '10.0.7.2', 'Dahua', 1), (11, 'Вход', '10.0.7.11', 'Hikvision', 1), (12, 'Парковка', '10.0.7.12', 'Dahua', 1), (13, 'Двор', '10.0.7.14', 'Tapo', 3)]
        return {'name': 'Surveillance Station', 'host': cfg.get('host') or '10.0.0.5', 'url': 'http://10.0.0.5:9900', 'version': '9.2.0', 'licences': 60, 'max': 40,
                'cameras': [{'id': i, 'name': n, 'ip': ip, 'port': 80, 'vendor': v, 'model': 'ONVIF', 'mac': '', 'status': s, 'statusText': 'работает' if s == 1 else 'нет связи', 'keepDays': 14} for i, n, ip, v, s in cams]}

    def disks(self, cfg):
        from .. import smart
        return smart.demo()

    def disk_test(self, cfg, disk, kind):
        return 'Testing has begun (демо). Короткий тест займёт около 2 минут.'

    def containers(self, cfg, notes=None):
        from .. import dockerinfo
        return dockerinfo.demo(cfg.get('host') or '10.0.0.5', notes)
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

    def disks(self, cfg):
        from .. import smart
        return smart.demo()

    def disk_test(self, cfg, disk, kind):
        return 'Testing has begun (демо). Короткий тест займёт около 2 минут.'

    def containers(self, cfg, notes=None):
        from .. import dockerinfo
        return dockerinfo.demo(cfg.get('host') or '198.51.100.40', notes)
    actions = [{'id': 'iperf', 'label': 'Тест скорости (iperf3)', 'scope': 'device', 'kind': 'speed',
                'confirm': 'Измерить скорость до сервера в обе стороны? (демо)'}]

    def inet_test(self, cfg, iface=None):
        time.sleep(.5)
        return {'down': round(random.uniform(850, 940), 1), 'up': round(random.uniform(820, 930), 1), 'ping': 1.2, 'server': 'Cloudflare FRA', 'ip': '198.51.100.40'}

    def port_scan(self, cfg, ip, ports):
        time.sleep(.5)
        return sorted({22, 3389, 32400, 1900} & set(ports) | ({32400} if 32400 in ports else set()))

    # VPS panels, simulated: the same stages as the real installer
    async_ops = ('install', 'remove')
    _panels = {}
    _coll = {}                                           # the «Сборщик площадки» plugin is not a panel: it does not conflict with 3x-ui / Remnawave

    def plugins(self, cfg):
        out = []
        for p in vps.CATALOG:
            p = dict(p, installed=p['id'] in self._panels, ip='198.51.100.40', info=(cfg.get('panelInfo') or {}).get(p['id']),
                     checks=[{'label': 'Ubuntu или Debian (у вас Ubuntu 24.04 LTS)', 'ok': True}, {'label': 'Вход под root', 'ok': True},
                             {'label': 'Память от 400 МБ (у вас 1987 МБ)', 'ok': True}, {'label': 'Внешний IP определён: 198.51.100.40', 'ok': True},
                             {'label': 'Порты 80 и 443 свободны (или заняты nginx)', 'ok': True},
                             {'label': 'Не установлена вторая панель — две панели на одном сервере конфликтуют', 'ok': not (set(self._panels) - {p['id']})}])
            out.append(p)
        from .. import agents
        a = dict(agents.CATALOG[0], installed=True, helper=True, models=agents.MODELS, claudeAuth='Logged in as demo@example.com',
                 config={'rc': True, 'auto': True, 'name': 'Франкфурт', 'model': 'sonnet', 'auth': 'sub', 'keys': []},
                 sessions=[{'name': 'rl-main', 'line': 'rl-main: 1 windows'}, {'name': 'rl-c-Proverka-123', 'line': 'rl-c-Proverka-123: 1 windows'}],
                 agents=[{k: x[k] for k in ('id', 'title', 'by', 'home')} | {'key': bool(x['key']), 'installed': x['id'] in ('claude', 'aider'), 'version': '2.1.300' if x['id'] == 'claude' else '0.86' if x['id'] == 'aider' else None} for x in agents.AGENTS],
                 checks=[{'label': 'Linux (у вас Ubuntu 24.04 LTS)', 'ok': True}, {'label': 'Вход под root (или sudo без пароля — для tmux и Node.js)', 'ok': True, 'optional': True},
                         {'label': 'tmux: tmux 3.4', 'ok': True, 'optional': True}, {'label': 'Node.js 18+ для Codex и Gemini CLI: будет установлен', 'ok': False, 'optional': True}])
        out.append(a)
        from .. import collector_install
        installed = bool(self._coll)
        out.append(dict(collector_install.RCOS_CARD, installed=installed and bool(self._coll.get('rcos')), version='2.9.0' if installed else None, active=installed, defaultPort=collector_install.DEFAULT_PORT, ip='198.51.100.40', host='vps-frankfurt',
                        checks=[{'label': 'Debian, Ubuntu, Raspberry Pi OS или другой Linux с systemd (у вас Ubuntu 24.04 LTS)', 'ok': True}, {'label': 'Вход под root', 'ok': True},
                                {'label': 'Память от 512 МБ (у вас 1987 МБ)', 'ok': True}, {'label': 'Свободно от 300 МБ (у вас 38400 МБ)', 'ok': True},
                                {'label': 'Пакеты (python3, ssh, ping, curl) поставятся сами через apt', 'ok': True, 'optional': False},
                                {'label': 'Wi-Fi-адаптер виден: wlp3s0', 'ok': True, 'optional': True}]))
        out.append(dict(collector_install.CARD, installed=installed and not self._coll.get('rcos'), version='2.9.0' if installed else None, active=installed, defaultPort=collector_install.DEFAULT_PORT, ip='198.51.100.40', host='vps-frankfurt',
                        checks=[{'label': 'Debian, Ubuntu, Raspberry Pi OS или другой Linux с systemd (у вас Ubuntu 24.04 LTS)', 'ok': True}, {'label': 'Вход под root', 'ok': True},
                                {'label': 'Память от 512 МБ (у вас 1987 МБ)', 'ok': True}, {'label': 'Свободно от 300 МБ (у вас 38400 МБ)', 'ok': True},
                                {'label': 'Пакеты (python3, ssh, ping, curl) поставятся сами через apt', 'ok': True, 'optional': False}]))
        return {'os': 'Ubuntu 24.04 LTS', 'ip': '198.51.100.40', 'plugins': out}

    def plugin(self, cfg, pid, op, params):
        progress = params.get('_progress') or (lambda s: None)
        if pid in ('collector', 'rcos'):
            if op == 'remove':
                progress('Удаляю (демо)'); time.sleep(.5)
                self._coll.clear()
                return {'ok': True, 'log': [], 'removed': 'collector', 'removeSite': params.get('_site'), 'message': 'Сборщик удалён (демо)'}
            c = params.get('_collector') or {}
            for s in ('Пакеты: python3, openssh-client, ping, curl', 'Скачиваю Rack Live с главной панели', 'Проверяю, что код запускается', 'Записываю настройки и ключ площадки', 'Запускаю службу'):
                progress(s + ' (демо)'); time.sleep(.5)
            self._coll['v'] = '2.9.0'
            self._coll['rcos'] = pid == 'rcos'
            info = {'url': f"http://198.51.100.40:{c.get('port') or 9998}", 'port': c.get('port') or 9998, 'siteId': c.get('siteId'), 'siteName': c.get('siteName'), 'server': c.get('url'),
                    'version': '2.9.0', 'level': c.get('level') or 'view', 'password': c.get('password'), 't': int(time.time())}
            rc = params.get('_rcos')
            if pid == 'rcos' and rc:
                info.update(rcos=True, warnings=[], tz=rc.get('tz') or None)
                if rc.get('ap'):
                    info['ap'] = {'ssid': rc['ssid'], 'password': rc['password'], 'address': '10.77.0.1/24', 'url': f"http://10.77.0.1:{info['port']}"}
            return {'ok': True, 'log': [{'cmd': '— демо-установка', 'ok': True, 'msg': ''}], 'info': info, 'message': ('ReckController OS установлен (демо)' if pid == 'rcos' else 'Сборщик установлен (демо)')}
        if pid == 'agents':
            progress('Демо: установка агентов'); time.sleep(.6)
            return {'ok': True, 'log': [{'cmd': '— демо', 'ok': True, 'msg': ''}], 'message': 'Готово (демо)', 'needSetup': False}
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


class DemoProxmox(DemoBase):
    id, title, kind = 'demo_proxmox', 'Демо: Proxmox', 'server'
    actions = [{'id': 'vm_start', 'label': 'Запустить', 'scope': 'vm', 'confirm': ''},
               {'id': 'vm_shutdown', 'label': 'Выключить', 'scope': 'vm', 'confirm': 'Выключить «{name}»?'},
               {'id': 'vm_reboot', 'label': 'Перезагрузить', 'scope': 'vm', 'confirm': 'Перезагрузить «{name}»?'}]
    VMS = [(100, 'vm', 'Windows Server · 1С', 'running', 4, 8), (101, 'ct', 'pihole', 'running', 1, .5), (102, 'ct', 'nextcloud', 'running', 2, 4),
           (103, 'vm', 'Ubuntu · тесты', 'stopped', 2, 4), (104, 'ct', 'zabbix', 'running', 2, 2)]

    def poll(self, cfg):
        t = time.time()
        g = 2 ** 30
        vms = [{'id': f'pve/{"qemu" if k == "vm" else "lxc"}/{i}', 'vmid': i, 'name': n, 'type': k, 'node': 'pve', 'status': s,
                'cpu': round((8 + 25 * wave(t, phase=i)) if s == 'running' else 0, 1), 'cpus': c, 'mem': m * g * .6 if s == 'running' else 0,
                'maxmem': m * g, 'uptime': int(t - T0 + 86400 * (i - 98)) if s == 'running' else 0} for i, k, n, s, c, m in self.VMS]
        return {'status': 'online', 'summary': {'model': 'Proxmox VE 9.0', 'fw': 'pve-manager/9.0.6', 'uptime': int(t - T0 + 2_592_000),
                                                'cpu': round(15 + 25 * wave(t)), 'mem': 58, 'ip': cfg.get('host')},
                'metrics': [{'label': 'Виртуалки', 'value': f"{sum(v['status'] == 'running' for v in vms)} из {len(vms)}"}], 'vms': vms,
                'storage': {'volumes': [{'name': 'local-lvm', 'status': 'normal', 'used': 610e9, 'total': 900e9},
                                        {'name': 'backup (NFS)', 'status': 'normal', 'used': 1.2e12, 'total': 4e12}],
                            'disks': [{'name': '/dev/nvme0n1', 'model': 'Samsung 980 PRO 1TB', 'kind': 'nvme', 'sizeGB': 1000, 'temp': None, 'status': 'normal'}]},
                'sections': [{'title': 'Proxmox', 'rows': [['Версия', 'Proxmox VE 9.0'], ['Процессор', 'Intel Xeon E-2236 · 12 потоков'], ['Память', '64 ГБ']]}]}


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
    o = D(name='Гостевой роутер · LTE', driver='demo_openwrt', kind='router', host='10.0.0.3')
    um = D(name='Свитч в кабинете', driver='unmanaged', kind='switch', ports='8', uplinkDevice=s, uplinkPort='10')     # an unmanaged one on port 10 — the printer hangs on it
    media = D(name='Медиасервер', driver='demo_server', kind='server', host='10.0.0.7')
    D(name='VPS · Франкфурт', driver='demo_server', kind='server', host='198.51.100.40', location='remote', site='Облако')
    D(name='Сайт компании', driver='demo_site', kind='web', host='https://example.com', location='remote', site='Облако')
    pve = D(name='Proxmox · виртуализация', driver='demo_proxmox', kind='server', host='10.0.0.8')
    ups = D(name='ИБП 1500 ВА', driver='ups', kind='ups', mode='manual', powerVA='1500', powerW='900', batteryV='12', batteryAh='9', batteryCount='2',
            efficiency='85', outlets='6', powerFrom='upduB', powerFromOutlet='2',      # fed from the outlet block in the panel, socket 2
            loads=[{'dev': r, 'outlet': '1'}, {'dev': s, 'outlet': '2'}, {'pdu': 'upduA', 'outlet': '3'}, {'label': 'Модем и мелочь', 'w': '15', 'outlet': '4'},
                   {'unit': 'uont', 'outlet': '5'}, {'label': 'Камеры (блок питания 12 В 2 А)', 'v': '12', 'a': '2', 'outlet': '6'}])
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
        U(name='Полка', type='shelf', uSize=1, uStart=8, color='#8e8e93', deviceIds=[um, o], deviceId=um),     # two devices on one shelf
        U(name='Proxmox', type='server', uSize=2, uStart=11, color='#5e5ce6', deviceId=pve),
        U(id='uont', name='Оптический терминал', type='modem', uSize=1, uStart=10, color='#bf5af2', pwr={'v': '12', 'a': '1'}, portmap={'count': 5, 'provider': 'Оптика-Демо', 'ports': {
            '1': {'name': 'PON', 'label': 'оптика провайдера', 'dev': 'u:ucross', 'port': '1'},
            '2': {'name': 'LAN1', 'label': 'к роутеру', 'dev': r, 'port': '5'},
            '3': {'name': 'LAN2'}, '4': {'name': 'LAN3'}, '5': {'name': 'TEL'}}}),
        U(name='ИБП 1500 ВА', type='ups', uSize=2, uStart=13, color='#ff9f0a', deviceId=ups),
        U(id='upduA', name='Блок розеток 8', type='pdu', uSize=1, uStart=15, color='#8e8e93',                    # plugged into UPS socket 3
          power={'count': 8, 'ports': {'1': {'dev': n}, '2': {'dev': pve, 'w': '95'}, '3': {'label': 'Мониторы в серверной', 'w': '40'}}})]},
        {'id': 'rack1', 'name': 'Этаж 2 · щиток', 'kind': 'box', 'totalU': 1, 'units': [
            U(name='Home Assistant', type='server', uStart=1, color='#5e5ce6', deviceId=h),
            U(name='Патч-панель 12', type='patch', uStart=2, color='#8e8e93'),
            U(name='PoE-инжектор', type='other', uStart=3, color='#ffd60a'),
            U(name='ИБП 650 ВА', type='ups', uStart=4, color='#ff9f0a'),
            U(id='upduB', name='Блок розеток · щиток', type='pdu', uStart=5, color='#8e8e93',                       # 220 V from the panel: feeds the UPS
              power={'count': 6, 'ports': {'1': {'label': 'Освещение щитка', 'w': '25'}}})]},
        {'id': 'rack2', 'name': 'Кабинет директора', 'kind': 'place', 'totalU': 1, 'units': [
            U(name='Медиасервер', type='server', uStart=1, color='#bf5af2', deviceId=media)]}]
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
    # internet speed: a week every 4 hours, the provider sags in the evening; the Netherlands tunnel alongside
    hist = []
    for k in range(42):
        tt = now - (41 - k) * 4 * 3600
        hour = time.localtime(tt).tm_hour
        sag = .35 if 19 <= hour <= 23 else 1
        hist.append({'t': tt, 'source': 'racklive', 'label': 'Rack Live (основной канал)', 'down': round(random.uniform(880, 940) * sag, 1),
                     'up': round(random.uniform(400, 460), 1), 'ping': round(random.uniform(3, 6), 1), 'server': 'Ростелеком, Москва', 'isp': 'Оптика 1 Гбит/с'})
        hist.append({'t': tt + 60, 'source': f'{r}:wg1', 'label': 'Роутер · Выход · Нидерланды', 'down': round(random.uniform(260, 330), 1),
                     'up': round(random.uniform(60, 90), 1), 'ping': round(random.uniform(38, 46), 1), 'server': 'Cloudflare AMS', 'loc': 'NL'})
    store._dump('inetspeed.json', hist)
    store.cfg['inet'] = {'enabled': True, 'hours': 4, 'tariff': 1000, 'server': 'ookla', 'channels': {r: ['wg1']}, 'servers': []}
    store._dump('known.json', {'sources': {r: now, s: now}, 'trusted': [], 'macs': {},          # learning the office's devices silently
                               'recent': [{'t': now - 5400, 'mac': 'de:ad:be:ef:10:01', 'name': 'Galaxy-A54', 'ip': '10.0.30.141', 'segment': 'Гости',
                                           'via': 'Роутер', 'random': False},
                                          {'t': now - 600, 'mac': '7a:11:22:33:44:55', 'name': '', 'ip': '10.0.0.188', 'segment': 'Основная',
                                           'via': 'Роутер', 'random': True}]})
    store.add_event(None, 'Камера · Склад', 'offline', 'нет связи: не отвечает')
    store.add_event(s, 'Коммутатор ядра', 'info', 'PoE на порту 3 перезапущено')
    store.add_event(None, 'Камера · Склад', 'online', 'снова в сети')
    res = DemoSwitch().action({}, 'cable_test', {'port': 12})
    res['cable']['t'] = now - 3600
    store.set_cable(s, 12, res['cable'])
    store.add_event(s, 'Коммутатор ядра', 'warning', res['message'])
    store.save()
    store.save_runtime()
