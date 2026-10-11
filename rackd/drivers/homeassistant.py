"""Home Assistant via the REST API (long-lived access token)."""
import time

from . import Driver
from ..util import DriverError, http_json


class HomeAssistant(Driver):
    id = 'homeassistant'
    title = 'Home Assistant'
    kind = 'server'
    description = 'Версия, объекты, недоступные устройства, выключатели. Можно включать/выключать выключатели.'
    fields = [{'name': 'host', 'label': 'Адрес', 'type': 'text', 'required': True, 'placeholder': 'http://192.168.1.2:8123'},
              {'name': 'token', 'label': 'Долгосрочный токен', 'type': 'password', 'secret': True, 'required': True,
               'hint': 'Профиль HA → Безопасность → Долгосрочные токены доступа'}]
    actions = [{'id': 'toggle', 'label': 'Переключить', 'scope': 'entity', 'instant': True}]

    def _base(self, cfg):
        h = cfg['host'].rstrip('/')
        return h if h.startswith('http') else 'http://' + h + ':8123'

    def _get(self, cfg, path):
        try:
            return http_json(self._base(cfg) + path, headers={'Authorization': 'Bearer ' + cfg.get('token', '')})
        except Exception as e:
            if '401' in str(e):
                raise DriverError('токен недействителен')
            raise

    def poll(self, cfg):
        conf = self._get(cfg, '/api/config')
        states = self._get(cfg, '/api/states')
        unavail = [s for s in states if s['state'] == 'unavailable']
        doms = {}
        for s in states:
            d = s['entity_id'].split('.')[0]
            doms[d] = doms.get(d, 0) + 1
        switches = [{'id': s['entity_id'], 'name': s['attributes'].get('friendly_name') or s['entity_id'], 'state': s['state']}
                    for s in states if s['entity_id'].split('.')[0] in ('switch', 'light')
                    and not any(k in s['entity_id'] for k in ('child_lock', 'backlight', 'pre_release', 'permit_join'))
                    and s['attributes'].get('device_class') != 'update']
        return {'status': 'warning' if len(unavail) > 0 else 'online',
                'summary': {'model': 'Home Assistant', 'fw': conf.get('version'), 'ip': self._base(cfg).split('//')[1].split(':')[0]},
                'metrics': [{'label': 'Объекты', 'value': len(states)}, {'label': 'Недоступно', 'value': len(unavail), 'level': 'warn' if unavail else ''},
                            {'label': 'Автоматизации', 'value': doms.get('automation', 0)}],
                'entities': switches,
                'sections': [{'title': 'Недоступные объекты', 'rows': [[s['attributes'].get('friendly_name') or s['entity_id'], s['entity_id']] for s in unavail[:30]]}]
                if unavail else []}

    def action(self, cfg, action_id, params):
        if action_id == 'toggle':
            eid = params.get('entity')
            if not eid or '.' not in eid:
                raise DriverError('не указан объект')
            http_json(self._base(cfg) + f"/api/services/{eid.split('.')[0]}/toggle", data={'entity_id': eid},
                      headers={'Authorization': 'Bearer ' + cfg.get('token', '')})
            time.sleep(0.4)            # let HA apply the new state before we re-read it
            return 'Готово'
        return super().action(cfg, action_id, params)
