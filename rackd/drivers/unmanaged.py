"""An unmanaged switch (a «soap box», a hub): nothing to poll — the user says where it is plugged in.
Its state comes from that port of the router / managed switch: link and speed, and how many devices that port sees.
On the map (rackd/topology.py) everything seen behind that port hangs on this switch instead of a «N устройств» group."""
from . import Driver


class Unmanaged(Driver):
    id = 'unmanaged'
    title = 'Неуправляемый коммутатор'
    kind = 'switch'
    description = ('Простой коммутатор без настроек («мыльница», хаб). Опросить его нельзя — укажите, куда он подключён: '
                   'на карте за ним появятся устройства, которые роутер или управляемый коммутатор видят за этим портом.')
    wants_ctx = True
    fields = [{'name': 'ports', 'label': 'Портов', 'type': 'select', 'default': '8',
               'options': [{'value': v, 'label': v} for v in ('4', '5', '8', '10', '16', '24', '48')]},
              {'name': 'uplinkDevice', 'label': 'Подключён к', 'type': 'device',
               'hint': 'Роутер или управляемый коммутатор, в который воткнут кабель от этого коммутатора'},
              {'name': 'uplinkPort', 'label': 'В порт №', 'type': 'text', 'placeholder': 'например 7'}]

    def poll(self, cfg):
        ctx = cfg.get('_ctx') or {}
        states, devices = ctx.get('states') or {}, ctx.get('devices') or []
        n = int(cfg.get('ports') or 8)
        up_id, up_port = cfg.get('uplinkDevice'), str(cfg.get('uplinkPort') or '').strip()
        up_dev = next((d for d in devices if d['id'] == up_id), None)
        st = states.get(up_id) or {}
        port = next((p for p in st.get('ports') or [] if str(p.get('n')) == up_port), None)
        behind = len(port.get('peers') or []) if port else None
        if not up_dev or not up_port:
            status, err = 'unknown', 'укажите, к какому устройству и в какой порт подключён коммутатор'
        elif not port:
            status, err = 'unknown', f"у «{up_dev.get('name')}» нет данных о порте {up_port}"
        else:
            status, err = ('online' if port.get('link') else 'offline'), None if port.get('link') else f"на порту {up_port} «{up_dev.get('name')}» нет линка"
        out = {'status': status, 'summary': {'model': f'Неуправляемый коммутатор · {n} портов'},
               'metrics': [{'label': 'Линк', 'value': (f"{port.get('speed')} Мбит/с" if port.get('speed') else 'есть') if port and port.get('link') else 'нет'},
                           {'label': 'За ним устройств', 'value': behind if behind is not None else '—'}],
               'sections': [{'title': 'Подключение', 'rows': [['К устройству', up_dev.get('name') if up_dev else '—'], ['Порт', up_port or '—'],
                                                              ['Портов у коммутатора', str(n)]]}]}
        if err:
            out['metrics'].append({'label': 'Нужно', 'value': err, 'level': 'warn'})
        if up_dev and not st:
            out['_retry'] = True                     # the uplink isn't polled yet — look again in a few seconds
        return out
