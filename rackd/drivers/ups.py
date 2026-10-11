"""UPS (ИБП). Three ways to know it:
  manual — no data cable: what is plugged in, estimated draw, battery, how long it will last;
  nut    — UPS on USB to a NAS / server running Network UPS Tools (Synology, TrueNAS, Proxmox, Linux), port 3493;
  snmp   — UPS with a network card (standard UPS-MIB, RFC 1628).
In every mode the list of plugged-in devices is kept, and live device data (PoE watts, disks) refines the estimate.
"""
import socket

from . import Driver
from ..snmp import Snmp, SnmpError, text
from ..util import DriverError

# rough typical draw, W — refined below from live data where possible
TYPICAL_W = {'router': 12, 'switch': 15, 'server': 60, 'nas': 30, 'ap': 8, 'camera': 6, 'nvr': 25, 'modem': 8, 'pc': 80,
             'laptop': 30, 'phone': 5, 'tv': 60, 'printer': 15, 'iot': 3, 'web': 0, 'other': 10, 'ups': 0}
SHOW_NET = {'field': 'mode', 'in': ['nut', 'snmp']}


def device_draw(d, st):
    """(watts, how we know): PoE switches report their PoE budget, NAS draw scales with disks."""
    kind = d.get('kind') or 'other'
    st = st or {}
    w, src = TYPICAL_W.get(kind, 10), 'типично'
    poe = sum(p.get('poeW') or 0 for p in st.get('ports') or [])
    if poe:
        w, src = 15 + poe / 0.9, f'PoE {round(poe, 1)} Вт'
    disks = len(((st.get('storage') or {}).get('disks')) or [])
    if kind == 'nas' and disks:
        word = 'диск' if disks % 10 == 1 and disks % 100 != 11 else 'диска' if 2 <= disks % 10 <= 4 and not 12 <= disks % 100 <= 14 else 'дисков'
        w, src = 18 + 7 * disks, f'{disks} {word}'
    return round(w), src


def nut_vars(host, port, name, user, pw):
    try:
        s = socket.create_connection((host, int(port or 3493)), timeout=6)
    except OSError as e:
        raise DriverError(f'NUT {host}:{port or 3493} не отвечает ({e.strerror or e})')
    f = s.makefile('rb')

    def ask(cmd, until=None):
        s.sendall((cmd + '\n').encode())
        lines = []
        while True:
            l = f.readline().decode('utf-8', 'replace').rstrip('\r\n')
            if not l:
                raise DriverError('NUT закрыл соединение')
            if l.startswith('ERR'):
                msg = {'ERR ACCESS-DENIED': 'доступ запрещён — разрешите этот адрес в настройках NUT / ИБП на NAS',
                       'ERR UNKNOWN-UPS': f'ИБП «{name}» не найден'}.get(l.split(' ', 2)[0] + ' ' + (l.split(' ')[1] if ' ' in l else ''), l)
                raise DriverError('NUT: ' + msg)
            lines.append(l)
            if until is None or l.startswith(until):
                return lines
    try:
        if user:
            ask(f'USERNAME {user}')
            ask(f'PASSWORD {pw or ""}')
        if not name:
            ups = [l.split()[1] for l in ask('LIST UPS', 'END LIST UPS') if l.startswith('UPS ')]
            if not ups:
                raise DriverError('NUT не сообщил ни одного ИБП')
            name = ups[0]
        out = {}
        for l in ask(f'LIST VAR {name}', 'END LIST VAR'):
            if l.startswith('VAR '):
                p = l.split(' ', 3)
                if len(p) == 4:
                    out[p[2]] = p[3].strip('"')
        return name, out
    finally:
        try:
            s.sendall(b'LOGOUT\n')
        except OSError:
            pass
        s.close()


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class UPS(Driver):
    id = 'ups'
    title = 'ИБП (бесперебойник)'
    kind = 'ups'
    description = 'Что подключено, сколько потребляет, заряд и на сколько хватит. Без кабеля данных — расчётом; с USB (через NAS/NUT) или сетевой картой — живые данные.'
    wants_ctx = True
    fields = [
        {'name': 'mode', 'label': 'Как подключён', 'type': 'select', 'default': 'manual', 'options': [
            {'value': 'manual', 'label': 'Без кабеля данных — считать по устройствам'},
            {'value': 'nut', 'label': 'USB к NAS / серверу (NUT, порт 3493)'},
            {'value': 'snmp', 'label': 'Сетевая карта ИБП (SNMP)'}]},
        {'name': 'host', 'label': 'Адрес NAS / сервера / карты ИБП', 'type': 'text', 'required': True, 'showIf': SHOW_NET},
        {'name': 'nutPort', 'label': 'Порт NUT', 'type': 'text', 'default': '3493', 'showIf': {'field': 'mode', 'in': ['nut']}},
        {'name': 'upsName', 'label': 'Имя ИБП в NUT', 'type': 'text', 'placeholder': 'пусто — первый найденный (у Synology «ups»)',
         'showIf': {'field': 'mode', 'in': ['nut']}},
        {'name': 'username', 'label': 'Логин NUT (если нужен)', 'type': 'text', 'showIf': {'field': 'mode', 'in': ['nut']}},
        {'name': 'password', 'label': 'Пароль NUT', 'type': 'password', 'secret': True, 'showIf': {'field': 'mode', 'in': ['nut']}},
        {'name': 'community', 'label': 'SNMP community', 'type': 'text', 'default': 'public', 'showIf': {'field': 'mode', 'in': ['snmp']}},
        {'name': 'powerW', 'label': 'Мощность ИБП, Вт', 'type': 'text', 'placeholder': 'например 900',
         'hint': 'На наклейке: «1500 ВА / 900 Вт». Нужно для процента нагрузки.'},
        {'name': 'batteryV', 'label': 'Аккумулятор: напряжение, В', 'type': 'text', 'default': '12'},
        {'name': 'batteryAh', 'label': 'Аккумулятор: ёмкость, А·ч', 'type': 'text', 'default': '9'},
        {'name': 'batteryCount', 'label': 'Сколько аккумуляторов', 'type': 'text', 'default': '1'},
        {'name': 'connected', 'label': 'Что подключено к ИБП', 'type': 'devices',
         'hint': 'Потребление считается по типу устройства и живым данным (PoE, число дисков)'},
        {'name': 'extraW', 'label': 'Прочая нагрузка, Вт', 'type': 'text', 'placeholder': 'то, чего нет в списке устройств'},
        {'name': 'extraNote', 'label': 'Что это за прочая нагрузка', 'type': 'text', 'placeholder': 'например «4 камеры по 5 Вт, модем»'},
    ]

    def poll(self, cfg):
        ctx = cfg.get('_ctx') or {}
        states, devices = ctx.get('states') or {}, {d['id']: d for d in ctx.get('devices') or []}
        mode = cfg.get('mode') or 'manual'
        nominal_w = num(cfg.get('powerW'))
        bat_v, bat_ah, bat_n = num(cfg.get('batteryV')) or 12, num(cfg.get('batteryAh')) or 9, num(cfg.get('batteryCount')) or 1
        battery_wh = bat_v * bat_ah * bat_n

        # what is plugged in
        connected, est_w = [], 0
        ids = [x for x in cfg.get('connected') or [] if x in devices]
        # devices powered over PoE by a switch that is itself on this UPS are already inside the switch's PoE draw
        poe_fed = {}
        for sid in ids:
            for p in (states.get(sid) or {}).get('ports') or []:
                if (p.get('poeW') or 0) > 0:
                    for peer in p.get('peers') or []:
                        if peer.get('mac'):
                            poe_fed[peer['mac'].lower()] = (devices[sid].get('name'), p.get('n'))
        for did in ids:
            d = devices.get(did)
            mac = (((states.get(did) or {}).get('summary') or {}).get('mac') or d.get('mac') or '').lower()
            if mac and mac in poe_fed and len(ids) > 1:
                sw, port = poe_fed[mac]
                st = (states.get(did) or {}).get('status')
                connected.append({'id': did, 'name': d.get('name'), 'kind': d.get('kind'), 'w': 0, 'status': st,
                                  'src': f'по PoE от «{sw}», порт {port} — уже в его нагрузке'})
                continue
            w, src = device_draw(d, states.get(did))
            st = (states.get(did) or {}).get('status')
            connected.append({'id': did, 'name': d.get('name'), 'kind': d.get('kind'), 'w': w, 'src': src, 'status': st})
            est_w += w
        extra = num(cfg.get('extraW')) or 0
        est_w += extra

        ups = {'mode': mode, 'connected': connected, 'extraW': extra, 'extraNote': cfg.get('extraNote') or '',
               'nominalW': nominal_w, 'batteryWh': round(battery_wh), 'batteryDesc': f'{int(bat_n)} × {bat_v:g} В {bat_ah:g} А·ч',
               'estimated': True, 'onBattery': False, 'lowBattery': False, 'charging': False, 'charge': None,
               'runtimeMin': None, 'loadW': round(est_w), 'loadPct': None, 'inputV': None, 'outputV': None}
        summary = {'model': 'ИБП', 'ip': cfg.get('host') or ''}
        sections = []

        if mode == 'nut':
            name, v = nut_vars(cfg.get('host', '').strip(), cfg.get('nutPort'), (cfg.get('upsName') or '').strip(),
                               cfg.get('username'), cfg.get('password'))
            status = v.get('ups.status', '')
            summary['model'] = ' '.join(x for x in (v.get('device.mfr') or v.get('ups.mfr'), v.get('device.model') or v.get('ups.model')) if x) or 'ИБП'
            summary['fw'] = v.get('ups.firmware') or v.get('driver.name')
            nominal_w = nominal_w or num(v.get('ups.realpower.nominal')) or (num(v.get('ups.power.nominal')) or 0) * .6 or None
            load_pct = num(v.get('ups.load'))
            load_w = num(v.get('ups.realpower')) or (load_pct * nominal_w / 100 if load_pct is not None and nominal_w else None)
            rt = num(v.get('battery.runtime'))
            ups.update(estimated=False, onBattery='OB' in status.split(), lowBattery='LB' in status.split(), charging='CHRG' in status.split(),
                       charge=num(v.get('battery.charge')), runtimeMin=round(rt / 60) if rt else None, loadPct=load_pct,
                       loadW=round(load_w) if load_w is not None else ups['loadW'], nominalW=nominal_w,
                       inputV=num(v.get('input.voltage')), outputV=num(v.get('output.voltage')), batteryV=num(v.get('battery.voltage')),
                       replace='RB' in status.split())
            sections.append({'title': 'Данные ИБП (NUT)', 'rows': [['Имя в NUT', name], ['Статус', status or '—'],
                                                                   ['Дата батареи', v.get('battery.date') or v.get('battery.mfr.date') or '—'],
                                                                   ['Температура', f"{v['ups.temperature']} °C" if v.get('ups.temperature') else '—']]})
        elif mode == 'snmp':
            b = '1.3.6.1.2.1.33.1.'
            oids = {'mfr': b + '1.1.0', 'model': b + '1.2.0', 'bstat': b + '2.1.0', 'onbat': b + '2.2.0', 'mins': b + '2.3.0',
                    'charge': b + '2.4.0', 'bv': b + '2.5.0', 'inv': b + '3.3.1.3.1', 'src': b + '4.1.0', 'outv': b + '4.4.1.2.1',
                    'outw': b + '4.4.1.4.1', 'load': b + '4.4.1.5.1'}
            try:
                r = Snmp(cfg.get('host', '').strip(), cfg.get('community') or 'public', timeout=2, retries=1).get(*oids.values())
            except SnmpError as e:
                raise DriverError(f'SNMP: {e}')
            g = {k: r.get(o) for k, o in oids.items()}
            if all(x is None for x in g.values()):
                raise DriverError('карта ИБП не отдаёт UPS-MIB (проверьте SNMP и community)')
            summary['model'] = ' '.join(x for x in (text(g['mfr']) if g['mfr'] else '', text(g['model']) if g['model'] else '') if x) or 'ИБП'
            load_pct = num(g['load'])
            load_w = num(g['outw']) or (load_pct * nominal_w / 100 if load_pct is not None and nominal_w else None)
            ups.update(estimated=False, onBattery=g['src'] == 5, lowBattery=g['bstat'] in (3, 4), charge=num(g['charge']),
                       runtimeMin=int(g['mins']) if g['mins'] is not None else None, loadPct=load_pct,
                       loadW=round(load_w) if load_w is not None else ups['loadW'], inputV=num(g['inv']), outputV=num(g['outv']),
                       batteryV=(num(g['bv']) or 0) / 10 or None)

        # derived numbers for every mode
        if ups['loadPct'] is None and nominal_w and ups['loadW']:
            ups['loadPct'] = round(ups['loadW'] * 100 / nominal_w)
        ups['nominalW'] = nominal_w
        if ups['runtimeMin'] is None and ups['loadW']:
            # usable energy: ~80% depth of discharge, ~85% inverter efficiency; Peukert-ish penalty at high load
            usable = battery_wh * .8 * .85 * (ups['charge'] / 100 if ups['charge'] is not None else 1)
            c_rate = ups['loadW'] / max(1, battery_wh)
            if c_rate > .5:
                usable *= max(.55, 1 - (c_rate - .5) * .5)
            ups['runtimeMin'] = round(usable / ups['loadW'] * 60)
            ups['runtimeEstimated'] = True
        status = 'online'
        if ups['onBattery'] or ups['lowBattery'] or ups.get('replace') or (ups['loadPct'] or 0) > 85 or (ups['charge'] is not None and ups['charge'] < 40):
            status = 'warning'
        rt = ups['runtimeMin']
        metrics = [{'label': 'Нагрузка', 'value': ups['loadW'], 'unit': 'Вт', 'level': 'warn' if (ups['loadPct'] or 0) > 85 else ''},
                   {'label': 'Хватит на', 'value': (('≈ ' if ups.get('runtimeEstimated') else '') + (f'{rt // 60} ч {rt % 60} мин' if rt >= 60 else f'{rt} мин')) if rt else '—'}]
        if ups['charge'] is not None:
            metrics.append({'label': 'Заряд', 'value': round(ups['charge']), 'unit': '%', 'level': 'warn' if ups['charge'] < 40 else ''})
        # neighbours not polled yet (fresh start) → ask the server to poll us again shortly
        retry = any(did in devices and did not in states for did in cfg.get('connected') or [])
        return {'status': status, 'summary': summary, 'ups': ups, 'metrics': metrics, 'sections': sections, '_retry': retry}
