"""Device drivers.

Every driver module defines a subclass of Driver. A driver turns a device config
(host, credentials, options) into a normalized state dict that the UI understands:

    status    'online' | 'warning' | 'offline'
    summary   {model, fw, uptime (sec), cpu (%), mem (%), temp (°C), ip, mac}
    ports     [{n, name, kind ('rj45'|'sfp'|'wan'), link, speed (Mbit), poeW, vlansU, vlansT, label, peers:[{mac, ip, name}]}]
    clients   [{mac, ip, name, segment, ap ('self' | child key), rssi, online, kind}]
    children  [{key, name, kind, model, ip, mac, status, clients, uptime, uplink}]   (mesh APs and the like)
    storage   {volumes: [{name, status, used, total}], disks: [{name, model, kind, sizeGB, temp, status}]}
    services  [{name, state}]
    vpn       [{id, name, kind ('wireguard'|'openvpn'|'l2tp'|'pptp'|'sstp'|'ipsec'), role ('server'|'client'),
                up, address, endpoint, routing (client tunnel carries default route), listenPort,
                rx, tx, handshake (unix ts of last handshake | None),
                peers: [{name, online, endpoint, subnet, handshake, rx, tx}]}]   VPN tunnels
    sections  [{title, rows: [[key, value], ...]}]   free-form structured info
    actions   [{id, label, scope ('device'|'port'), confirm}]
"""

import importlib, pkgutil

FIELD_HOST = {'name': 'host', 'label': 'Адрес (IP или домен)', 'type': 'text', 'required': True}
FIELD_USER = {'name': 'username', 'label': 'Логин', 'type': 'text'}
FIELD_PASS = {'name': 'password', 'label': 'Пароль', 'type': 'password', 'secret': True}


class Driver:
    id = ''
    title = ''
    kind = 'other'            # default device kind for the icon
    description = ''
    fields = []               # form fields shown in "Add device"
    actions = []              # actions this driver can perform
    hidden = False            # not offered in "Add device" (demo drivers)

    def poll(self, cfg):
        raise NotImplementedError

    def action(self, cfg, action_id, params):
        raise NotImplementedError('действие не поддерживается')

    @classmethod
    def schema(cls):
        return {'id': cls.id, 'title': cls.title, 'kind': cls.kind, 'description': cls.description,
                'fields': cls.fields, 'actions': cls.actions, 'hidden': cls.hidden,
                'plugins': callable(getattr(cls, 'plugins', None)),      # driver has a «Плагины» tab (see rackd/plugins.py)
                'backup': callable(getattr(cls, 'backup', None)),        # config versions (rackd/backups.py)
                'inetTest': callable(getattr(cls, 'inet_test', None))}   # internet speed through it (rackd/inet.py)


REGISTRY = {}


def load_all():
    for m in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(__name__ + '.' + m.name)
        for obj in vars(mod).values():
            if isinstance(obj, type) and issubclass(obj, Driver) and obj is not Driver and obj.id:
                REGISTRY[obj.id] = obj()
    return REGISTRY
