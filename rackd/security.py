"""Security advisor: what in this network is unsafe or misconfigured, in plain words, with a fix where it is safe.

Facts come from the device states (the Keenetic driver adds `state.security`: port forwards, remote access, UPnP,
firmware update) and from Rack Live's own device settings (default passwords, telnet, SNMP «public»).
Every finding has a stable id, so the user can mark it «это нормально» (ignored) and alerts fire only once.
"""

LEVEL_COST = {'bad': 20, 'warn': 8, 'info': 0}       # «к сведению» informs, it doesn't lower the score
DEFAULT_PASSWORDS = {'', 'admin', 'password', '1234', '12345', '123456', '12345678', 'root', 'keenetic', 'public', 'ubnt', 'default', 'guest', 'user', 'toor'}

# well-known services behind a forwarded port: (level, what it is, why it matters)
RISKY_PORTS = {
    21: ('bad', 'FTP', 'пароли и файлы передаются открытым текстом'),
    22: ('warn', 'SSH', 'из интернета постоянно перебирают пароли SSH'),
    23: ('bad', 'Telnet', 'пароль передаётся открытым текстом, telnet постоянно сканируют боты'),
    139: ('bad', 'SMB (общие папки Windows)', 'через SMB распространяются вирусы-шифровальщики'),
    445: ('bad', 'SMB (общие папки Windows)', 'через SMB распространяются вирусы-шифровальщики'),
    3389: ('bad', 'RDP (удалённый рабочий стол)', 'RDP — частая цель взлома и подбора паролей'),
    5900: ('bad', 'VNC', 'VNC часто без шифрования и с простым паролем'),
    3306: ('bad', 'MySQL', 'база данных не должна быть видна из интернета'),
    5432: ('bad', 'PostgreSQL', 'база данных не должна быть видна из интернета'),
    6379: ('bad', 'Redis', 'Redis без пароля позволяет захватить сервер'),
    27017: ('bad', 'MongoDB', 'база данных не должна быть видна из интернета'),
    5000: ('warn', 'Synology DSM (http)', 'панель NAS открыта в интернет без шифрования'),
    5001: ('warn', 'Synology DSM', 'панель NAS открыта в интернет — включите 2FA и блокировку IP'),
    8123: ('warn', 'Home Assistant', 'умный дом открыт в интернет — нужен надёжный пароль и 2FA'),
    80: ('warn', 'веб-сервер (http)', 'сайт или панель без шифрования'),
    8080: ('warn', 'веб-панель (http)', 'веб-панель без шифрования'),
    1900: ('bad', 'UPnP', 'UPnP не должен быть виден из интернета'),
}


def _port0(p):
    try:
        return int(str(p).split('-')[0])
    except ValueError:
        return 0


def audit(devices, states, peer_index=None, ignored=(), ext=None):
    """→ {score, counts, findings: [...], ignored: [...]} — findings sorted bad → warn → info.
    `ext` = the last outside port check {open, checked, ...}: confirms findings and reveals unexpected open ports."""
    found, by_id = [], {d['id']: d for d in devices}
    idx = peer_index or {}
    ext = ext if ext and not ext.get('error') and ext.get('checked') else None
    ext_open, ext_checked, explained = set(ext['open']) if ext else set(), set(ext['checked']) if ext else set(), set()

    def add(fid, level, title, text, did=None, fix=None, how='', port=None):
        if ext and port:
            explained.add(port)
            if port in ext_open:
                text += ' ✔ Проверено снаружи: порт действительно открыт.'
            elif port in ext_checked:
                text += ' Снаружи порт сейчас не отвечает (устройство выключено или сервис не слушает), но проброс остаётся.'
        found.append({'id': fid, 'level': level, 'title': title, 'text': text, 'deviceId': did, 'fix': fix, 'how': how})

    for d in devices:
        if d.get('enabled') is False:
            continue
        st, did, name = states.get(d['id']) or {}, d['id'], d.get('name') or d.get('host')
        sec = st.get('security') or {}
        # ── router: port forwards ──
        for f in sec.get('forwards') or []:
            port = _port0(f['port'])
            to = (idx.get((f.get('target') or '').lower()) or {}).get('name') or f.get('target')
            lvl, what, why = RISKY_PORTS.get(_port0(f['toPort']), RISKY_PORTS.get(port, ('info', '', '')))
            label = f"{f['port']}/{f['proto'].replace('tcpudp', 'tcp+udp')} → {to}" + (f" ({f['name']})" if f.get('name') else '')
            add(f"fwd:{did}:{f['proto']}:{f['port']}", lvl,
                f"Открыт порт {f['port']} в интернет → {to}" + (f' · {what}' if what else ''),
                (f'{what}: {why}. ' if what else 'Любой в интернете может подключиться к этому порту. ') +
                'Если доступ нужен только вам — используйте VPN (у вас есть WireGuard на роутере), а проброс закройте.',
                did, {'action': 'sec_fix', 'params': {'kind': 'forward', 'rule': f['rule'], 'label': label}, 'label': 'Закрыть проброс',
                      'confirm': f'Закрыть проброс {label}? Доступ из интернета к этому порту пропадёт.'}, port=port)
        # ── router: management from the internet ──
        rem = sec.get('remote') or {}
        t = rem.get('telnet') or {}
        if t.get('on') and t.get('level') == 'public':
            add(f'remote:{did}:telnet', 'bad', f"Telnet роутера «{name}» открыт в интернет (порт {t.get('port', 23)})",
                'Через telnet можно управлять роутером, а пароль летит открытым текстом. Боты сканируют telnet постоянно.', did,
                {'action': 'sec_fix', 'params': {'kind': 'remote', 'service': 'telnet'}, 'label': 'Только из домашней сети',
                 'confirm': 'Оставить telnet роутера доступным только из домашней сети?'}, port=t.get('port', 23))
        s = rem.get('ssh') or {}
        if s.get('on') and s.get('level') == 'public':
            add(f'remote:{did}:ssh', 'warn', f"SSH роутера «{name}» открыт в интернет (порт {s.get('port', 22)})",
                'Управление роутером доступно из интернета — его будут перебирать. Для доступа снаружи надёжнее VPN.', did,
                {'action': 'sec_fix', 'params': {'kind': 'remote', 'service': 'ssh'}, 'label': 'Только из домашней сети',
                 'confirm': 'Оставить SSH роутера доступным только из домашней сети?'}, port=s.get('port', 22))
        h = rem.get('http') or {}
        if h.get('level') == 'public':
            add(f'remote:{did}:http', 'warn', f"Веб-интерфейс роутера «{name}» доступен из интернета",
                'Страница входа в роутер открыта всему интернету. Если веб-приложения KeenDNS вам не нужны снаружи — запретите удалённый доступ.',
                did, None, 'Веб-интерфейс роутера → «Пользователи и доступ» → доступ к веб-конфигуратору — только из домашней сети. '
                           'Внимание: опубликованные через KeenDNS веб-приложения тоже перестанут открываться снаружи.', port=h.get('port', 80))
            explained.add(h.get('sslPort', 443))
        if sec.get('upnp'):
            add(f'upnp:{did}', 'info', 'UPnP включён',
                'Любая программа или умное устройство в сети может само открыть себе порт в интернет — без вашего ведома.', did, None,
                'Если не играете в онлайн-игры на консоли и не пользуетесь торрентами — выключите UPnP в настройках роутера (раздел «Домашняя сеть»).')
        u = sec.get('update') or {}
        if u.get('available'):
            beta = (u.get('channel') or '') in ('draft', 'preview')
            add(f"fw:{did}:{u.get('title')}", 'info' if beta else 'warn', f"Доступна прошивка {u.get('title')} для «{name}»",
                ('Это тестовая версия (у роутера выбран канал обновлений с бета-версиями). ' if beta else
                 'В новых прошивках закрывают уязвимости. ') + 'Обновление займёт несколько минут, интернет пропадёт.', did, None,
                'Веб-интерфейс роутера → «Параметры системы» → «Обновления».')
        for ch in st.get('children') or []:
            if ch.get('fwUpdate'):
                add(f"fwch:{did}:{ch.get('mac') or ch.get('name')}", 'info', f"Точка «{ch.get('name')}»: доступно обновление прошивки",
                    'Mesh-точки лучше держать на той же версии, что и роутер.', did, None, 'Обновляется вместе с роутером в его веб-интерфейсе.')
        # ── Rack Live's own knowledge: passwords, protocols ──
        user = (d.get('username') or '').strip().lower()
        if d.get('password') is not None and str(d.get('password')).strip().lower() in DEFAULT_PASSWORDS and user in ('admin', 'root', 'user', ''):
            if d.get('driver') not in ('ping', 'http', 'agent', 'ups'):
                add(f'defpw:{did}', 'bad', f"«{name}»: пароль по умолчанию",
                    f"Логин {d.get('username') or '—'} с паролем по умолчанию знает любой, кто попал в вашу сеть (или вирус на любом компьютере).", did, None,
                    'Смените пароль в веб-интерфейсе устройства, затем обновите его в Rack Live: «Настроить» в карточке устройства.')
        if (d.get('entwarePassword') or '').strip() == 'keenetic':
            add(f'defpw:{did}:entware', 'warn', f"«{name}»: у Entware пароль по умолчанию «keenetic»",
                'Пароль root от Entware стандартный — его знают все, кто ставил Entware.', did, None,
                'Зайдите в Entware по SSH (порт 222) и выполните passwd, затем обновите пароль в плагине Entware.')
        if d.get('driver') == 'tplink_jetstream':
            add(f'telnet:{did}', 'info', f"«{name}» управляется по telnet",
                'Telnet передаёт пароль открытым текстом по домашней сети. Не критично, если в сеть не пускают чужих.', did, None,
                'Если коммутатор поддерживает SSH — включите его; Rack Live пока управляет TP-Link по telnet.')
        comm = d.get('snmpCommunity') if d.get('driver') == 'tplink_jetstream' else d.get('community') if d.get('driver') == 'snmp' else None
        if d.get('driver') == 'snmp' and not comm:
            comm = 'public'
        if comm and str(comm).strip().lower() in ('public', 'private'):
            add(f'snmp:{did}', 'warn', f"«{name}»: SNMP с community «{comm}»",
                f"«{comm}» — общеизвестное значение: любой в сети прочитает настройки{' и даже изменит их' if comm == 'private' else ''}.", did, None,
                'Задайте на устройстве своё community (только чтение) и укажите его в настройках устройства в Rack Live.')
        for m in st.get('metrics') or []:
            if m.get('label') == 'Сертификат' and isinstance(m.get('value'), (int, float)) and m['value'] <= 14:
                add(f'cert:{did}', 'warn' if m['value'] > 3 else 'bad', f"«{name}»: сертификат истекает через {m['value']} дн.",
                    'После истечения браузеры и приложения покажут ошибку безопасности.', did, None, 'Проверьте автопродление сертификата на сервере.')

    # ports that answer from the internet although no router forwards them (UPnP, the router's own services, another router)
    for port in sorted(ext_open - explained):
        lvl, what, why = RISKY_PORTS.get(port, ('warn', '', ''))
        add(f'ext:{port}', lvl, f"Снаружи отвечает порт {port}" + (f' · {what}' if what else ''),
            (f'{what}: {why}. ' if what else '') + 'Проброса для него в настройках роутера нет — его могла открыть программа через UPnP, '
            'это может быть сервис самого роутера или второго роутера за ним.', None, None,
            'Найдите, кто слушает порт: список UPnP-пробросов и приложений в веб-интерфейсе роутера. Если порт не нужен — выключите UPnP или сервис.')

    ign = set(ignored or ())
    order = {'bad': 0, 'warn': 1, 'info': 2}
    active = sorted([f for f in found if f['id'] not in ign], key=lambda f: (order[f['level']], f['title']))
    hidden = [f for f in found if f['id'] in ign]
    score = max(0, 100 - sum(LEVEL_COST[f['level']] for f in active))
    counts = {k: sum(1 for f in active if f['level'] == k) for k in order}
    return {'score': score, 'counts': counts, 'findings': active, 'ignored': hidden}
