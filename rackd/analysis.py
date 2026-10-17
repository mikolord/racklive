"""Network health: what topology this is, where the single points of failure are, and what to fix.

Works on the graph from topology.build() plus the raw device states, so every driver benefits.
"""
from collections import defaultdict, deque

INFRA = ('router', 'switch', 'ap', 'modem')
IMPORTANT = ('router', 'switch', 'ap', 'nas', 'server', 'nvr', 'pc')       # 100 Мбит/с for these is suspicious
KIND_RU = {'camera': ('камера', 'камеры', 'камер'), 'ap': ('точка доступа', 'точки доступа', 'точек доступа'),
           'switch': ('коммутатор', 'коммутатора', 'коммутаторов'), 'nas': ('хранилище', 'хранилища', 'хранилищ'),
           'server': ('сервер', 'сервера', 'серверов'), 'pc': ('компьютер', 'компьютера', 'компьютеров'),
           'phone': ('телефон', 'телефона', 'телефонов'), 'iot': ('умное устройство', 'умных устройства', 'умных устройств'),
           'nvr': ('регистратор', 'регистратора', 'регистраторов'), 'printer': ('принтер', 'принтера', 'принтеров'),
           'router': ('роутер', 'роутера', 'роутеров'), 'laptop': ('ноутбук', 'ноутбука', 'ноутбуков'), 'tv': ('телевизор', 'телевизора', 'телевизоров')}

TYPES = {
    'single': ('Одиночная', 'Все устройства подключены прямо к роутеру.',
               'Просто и дёшево, но портов мало, а роутер отвечает за всё сразу.'),
    'star': ('Звезда', 'Все устройства подключены к одному центральному узлу.',
             'Обрыв одного кабеля задевает только одно устройство, легко искать проблему. Слабое место — центральный узел.'),
    'tree': ('Дерево (иерархическая звезда)', 'Несколько уровней: роутер → коммутатор → точки и устройства.',
             'Стандарт для дома и офиса: легко расширять. Слабые места — узлы верхних уровней и кабели между ними.'),
    'chain': ('Цепочка', 'Коммутаторы соединены последовательно, один за другим.',
              'Дёшево по кабелю, но каждый следующий коммутатор зависит от всех предыдущих, а трафик идёт через всю цепочку.'),
    'ring': ('Кольцо', 'Коммутаторы соединены по кругу — у каждого два пути.',
             'Обрыв одного кабеля не страшен: трафик пойдёт в обход (нужен STP/ERPS, чтобы не было петли).'),
    'mesh': ('Ячеистая (mesh)', 'Между узлами несколько путей.',
             'Самая надёжная, но дорогая и сложная в настройке.'),
}
TYPE_ORDER = ['single', 'star', 'tree', 'chain', 'ring', 'mesh']


def _plural(n, one, few, many):
    n10, n100 = n % 10, n % 100
    return one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many


def analyze(topo, devices, states, cable_tests):
    nodes = {n['id']: n for n in topo['nodes']}
    edges = [e for e in topo['edges'] if e['source'] in nodes and e['target'] in nodes]
    adj = defaultdict(set)
    for e in edges:
        adj[e['source']].add(e['target'])
        adj[e['target']].add(e['source'])
    root = 'inet' if 'inet' in nodes else next((i for i, n in nodes.items() if n.get('kind') == 'router'), None)
    # the ONT / modem in front of the router (map.wan) is the provider's side, not part of the LAN
    wanbox = {i for i, n in nodes.items() if n.get('wan')}
    main = next((e['target'] for e in edges if e.get('kind') == 'wan' and (e['source'] == 'inet' or e['source'] in wanbox)), None) \
        or next((i for i, n in nodes.items() if n.get('kind') == 'router'), None)
    # other routers (a captive-portal box, a tenant's router) are separate networks: endpoints, never a path for our LAN
    other_router = lambda i: nodes[i].get('kind') == 'router' and i != main
    is_infra = lambda i: i != 'inet' and i not in wanbox and not other_router(i) and (nodes[i].get('kind') in INFRA or i.startswith('x:'))
    checks = []

    def reach(skip_node=None, skip_edge=None):
        if not root or root == skip_node:
            return set()
        seen, q = {root}, deque([root])
        while q:
            a = q.popleft()
            if a != root and other_router(a):
                continue
            for b in adj[a]:
                if b in seen or b == skip_node or (skip_edge and {a, b} == skip_edge):
                    continue
                seen.add(b)
                q.append(b)
        return seen

    base = reach()
    # tree parents (first non-extra edge into a node) → depth from the main router
    parent = {}
    for e in edges:
        if not e.get('extra') and not e.get('manual') and e['target'] not in parent:
            parent[e['target']] = e
    def depth(i):
        d, cur, guard = 0, i, 0
        while cur in parent and guard < 40:
            cur = parent[cur]['source']
            if cur == 'inet' or cur in wanbox:
                break
            d, guard = d + 1, guard + 1
        return d

    # ── single points of failure ──
    def describe(ids):
        cnt = defaultdict(int)
        for i in ids:
            cnt[nodes[i].get('kind') or 'other'] += 1
        parts = [f'{v} {_plural(v, *KIND_RU[k])}' for k, v in sorted(cnt.items(), key=lambda kv: -kv[1]) if k in KIND_RU][:3]
        return ', '.join(parts)

    spof = []
    for i in nodes:
        if i == root or not is_infra(i) or i not in base:
            continue
        lost = base - reach(skip_node=i) - {i}
        lost = {x for x in lost if not nodes[x].get('remote')}
        if len(lost) >= 2:
            spof.append({'id': i, 'label': nodes[i]['label'], 'kind': nodes[i].get('kind'), 'deviceId': nodes[i].get('deviceId'),
                         'affected': len(lost), 'what': describe(lost)})
    spof.sort(key=lambda s: -s['affected'])
    total_local = len([x for x in base if x != 'inet' and x not in wanbox and not nodes[x].get('remote')])

    # cables between infrastructure nodes that have no alternative path
    bridges = []
    for e in edges:
        a, b = e['source'], e['target']
        # backbone only: a cable to a single access point is a bridge by nature, not news
        if a == 'inet' or not (is_infra(a) and is_infra(b)) or e.get('kind') in ('remote', 'wifi') or nodes[b].get('kind') == 'ap':
            continue
        lost = base - reach(skip_edge={a, b})
        if len(lost) >= 3:
            bridges.append({'edge': e['id'], 'a': nodes[a]['label'], 'b': nodes[b]['label'], 'port': e.get('sourcePort'),
                            'speed': e.get('speed'), 'affected': len(lost), 'kind': e.get('kind')})
    bridges.sort(key=lambda x: -x['affected'])

    # ── topology type ──
    infra = [i for i in nodes if is_infra(i) and not nodes[i].get('remote')]
    iset = set(infra)
    ie = [e for e in edges if e['source'] in iset and e['target'] in iset and e.get('kind') != 'remote']
    uniq = {frozenset((e['source'], e['target'])) for e in ie}
    comps, seen = 0, set()
    for i in infra:
        if i in seen:
            continue
        comps += 1
        q = deque([i]); seen.add(i)
        while q:
            a = q.popleft()
            for b in adj[a]:
                if b in iset and b not in seen and frozenset((a, b)) in uniq:
                    seen.add(b); q.append(b)
    cycles = max(0, len(uniq) - len(infra) + comps)
    wired_parents = {e['source'] for e in edges if e.get('kind') in ('wire', 'lan', 'manual') and e['source'] in iset}
    levels = sorted({depth(i) for i in wired_parents})
    switches = [i for i in infra if nodes[i].get('kind') == 'switch' and not i.startswith('x:')]
    chain = 0
    for s in switches:                              # longest run of switch → switch → switch
        n, cur = 1, s
        while cur in parent and nodes.get(parent[cur]['source'], {}).get('kind') == 'switch':
            cur, n = parent[cur]['source'], n + 1
        chain = max(chain, n)
    aps = [i for i in infra if nodes[i].get('kind') == 'ap']
    mesh_aps = [i for i in aps if nodes[i].get('childOf')]
    if cycles:
        deg = defaultdict(int)
        for p in uniq:
            for x in p:
                deg[x] += 1
        tid = 'ring' if cycles == 1 and all(deg[x] <= 2 for x in switches) and len(switches) >= 3 else 'mesh'
    elif chain >= 3:
        tid = 'chain'
    elif len(levels) >= 2:
        tid = 'tree'
    elif switches:
        tid = 'star'
    else:
        tid = 'single'
    traits = []
    wired = 0
    if mesh_aps:
        # the router tells the backhaul itself (Ethernet / air); without it — whether the point hangs on a cable on the map
        wired = sum(1 for i in mesh_aps if nodes[i].get('backhaul') == 'wire' or (nodes[i].get('backhaul') is None and parent.get(i, {}).get('kind') == 'wire'))
        traits.append(f"Wi-Fi mesh: {len(mesh_aps)} {_plural(len(mesh_aps), 'точка', 'точки', 'точек')}" +
                      (', связь с роутером по кабелю' if wired == len(mesh_aps) else ', часть по воздуху' if wired else ', связь по воздуху'))
    remote = [n for n in nodes.values() if n.get('remote')]
    if remote:
        traits.append(f"удалённые объекты: {len(remote)}")
    if cycles:
        traits.append('есть резервные пути')
    if any(i.startswith('x:') for i in infra):
        traits.append('есть неуправляемые коммутаторы')
    name, what, note = TYPES[tid]
    hybrid = bool(mesh_aps or (tid in ('tree', 'star') and cycles))
    mesh_name = '' if not mesh_aps or tid == 'mesh' else (' + Wi-Fi mesh по кабелю' if wired == len(mesh_aps)
                                                          else ' + Wi-Fi mesh (кабель и воздух)' if wired else ' + беспроводной mesh')
    ttype = {'id': tid, 'name': name + mesh_name, 'what': what, 'note': note,
             'traits': traits, 'hybrid': hybrid, 'levels': len(levels), 'chain': chain, 'cycles': cycles,
             'all': [{'id': k, 'name': TYPES[k][0], 'what': TYPES[k][1], 'note': TYPES[k][2]} for k in TYPE_ORDER]}

    # ── checks ──
    def add(level, title, text='', **kw):
        checks.append(dict(level=level, title=title, text=text, **kw))

    for d in devices:
        st = states.get(d['id']) or {}
        if d.get('enabled', True) and st.get('status') == 'offline' and d.get('kind') in INFRA + ('nas', 'server'):
            add('bad', f"{d.get('name')} не на связи", st.get('error') or '', deviceId=d['id'])

    # ── loops: a live one is an emergency; a missing protection is a warning when the network has cables that can close a ring ──
    for d in devices:
        st = states.get(d['id']) or {}
        lp, g = st.get('loops') or {}, st.get('loopGuard') or {}
        if lp.get('active'):
            add('bad', f"В сети похоже петля: {d.get('name')}", lp.get('why', '') + '. Из-за петли кадры ходят по кругу, сеть тормозит или встаёт целиком. '
                'Найдите кабель, который воткнут в два порта одной сети (коммутатор в самого себя, два кабеля между двумя коммутаторами без STP) и отключите его.',
                deviceId=d['id'], port=(lp.get('guard') or lp.get('storm') or [{}])[0].get('port'))
        elif lp.get('recent'):
            add('info', f"Недавно была петля: {d.get('name')}", 'Признаки уже пропали. Чтобы это не повторилось, найдите причину — кабель, который кто-то замкнул, — и включите защиту от петель.',
                deviceId=d['id'])
        if g.get('supported') and not g.get('enabled') and d.get('enabled', True) and st.get('status') != 'offline':
            add('warn' if cycles else 'info', f"Защита от петель выключена: {d.get('name')}",
                ('В сети есть резервные кабели (кольцо) — без защиты любой из них замкнёт сеть. ' if cycles else '') +
                'Достаточно одного случайно воткнутого кабеля (коммутатор сам в себя), чтобы сеть встала. Коммутатор умеет отключать такой порт сам — '
                'включите это в карточке коммутатора («Защита от петель»), связь не пропадёт.', deviceId=d['id'])

    for s in spof[:2]:
        if s['kind'] == 'router':
            text = 'Через него идёт весь интернет. Резервного канала нет — при сбое роутера или провайдера сеть останется без интернета.'
        else:
            text = (f"При его сбое связь потеряют {s['affected']} из {total_local} {_plural(total_local, 'устройства', 'устройств', 'устройств')}" + (f" ({s['what']})" if s['what'] else '') +
                    '. Подключите к ИБП и держите настройки в резервной копии.')
        add('warn' if s['affected'] >= 5 and s['kind'] != 'router' else 'info', f"Единая точка отказа: {s['label']}", text,
            nodeId=s['id'], deviceId=s.get('deviceId'))
    for b in bridges[:2]:
        add('info', f"Один кабель {b['a']} ↔ {b['b']}" + (f" (порт {b['port']})" if b.get('port') else ''),
            f"Через него {b['affected']} {_plural(b['affected'], 'устройство', 'устройства', 'устройств')}, обходного пути нет. Можно добавить второй кабель и объединить "
            'порты в агрегацию (LACP) — будет и запас, и вдвое больше скорость.')

    bad_cable = set()
    for did, tests in (cable_tests or {}).items():
        d = next((x for x in devices if x['id'] == did), None)
        if not d:
            continue
        ports = {str(p.get('n')): p for p in (states.get(did) or {}).get('ports') or []}
        for port, c in tests.items():
            cur = ports.get(port) or {}
            if c.get('verdict') not in ('warn', 'bad') or (cur.get('link') and (cur.get('speed') or 0) >= 1000):
                continue                                  # fine, or already fixed since the test
            bad_cable.add((did, int(port)))
            lbl = cur.get('label') or ''
            add('warn' if c['verdict'] == 'warn' else 'bad', f"Кабель на порту {port}{' · ' + lbl if lbl else ''} неисправен",
                c.get('text', '') + ' ' + '. '.join(x[:1].upper() + x[1:] for x in c.get('details') or []) + '.', deviceId=did, port=int(port))

    for d in devices:
        for p in (states.get(d['id']) or {}).get('ports') or []:
            n = p.get('errDay') or 0
            if n >= 10 and (d['id'], p.get('n')) not in bad_cable:
                lbl = p.get('label') or ''
                add('bad' if (p.get('errHour') or 0) >= 10 else 'warn', f"Ошибки на порту {p['n']}{' · ' + lbl if lbl else ''}: {n} за сутки",
                    'Коммутатор получает повреждённые кадры (CRC) — их приходится передавать заново, скорость падает. '
                    'Обычно виноват обжим, перегиб кабеля или силовой кабель рядом. Проверьте кабель в карточке порта.',
                    deviceId=d['id'], port=p['n'])

    for e in edges:
        t = nodes[e['target']]
        sp = e.get('speed') or 0
        if (nodes[e['source']].get('deviceId'), e.get('sourcePort')) in bad_cable:
            continue
        if e.get('kind') == 'wire' and 0 < sp < 1000 and t.get('kind') in IMPORTANT and not e.get('extra'):
            src = nodes[e['source']]
            add('warn', f"{t['label']}: всего {sp} Мбит/с",
                f"Подключено к «{src['label']}»" + (f", порт {e['sourcePort']}" if e.get('sourcePort') else '') +
                ('. Для точки доступа это потолок скорости Wi-Fi.' if t.get('kind') == 'ap' else '.') +
                ' Обычно виноват кабель или обжим — проверьте его в карточке порта.',
                deviceId=src.get('deviceId'), port=e.get('sourcePort'), nodeId=t['id'])

    for d in devices:
        for t in (states.get(d['id']) or {}).get('vpn') or []:
            if t.get('role') == 'client' and t.get('routing') and not t.get('up'):
                add('warn', f"VPN «{t['name']}» отключён",
                    'Через этот туннель должен идти трафик, но он не поднят — значит, он идёт напрямую, в обход VPN. '
                    'Проверьте настройки туннеля и сервер.', deviceId=d['id'])

    if chain >= 3:
        add('warn', f'Цепочка из {chain} коммутаторов', 'Дальние коммутаторы зависят от всех предыдущих, а общий трафик идёт через каждый. '
                                                       'Лучше подключить их звездой к центральному.')
    for i in infra:
        if i.startswith('x:'):
            e = parent.get(i) or {}
            src = nodes.get(e.get('source'), {})
            add('info', f"Неуправляемый узел: {nodes[i]['label']}",
                f"За портом {e.get('sourcePort')} на «{src.get('label', '')}» видно {nodes[i].get('sub', '').split()[0]} устройств — "
                'там стоит простой коммутатор или хаб. Добавьте его в «Устройства» как «Неуправляемый коммутатор» (куда подключён и в какой порт) — '
                'тогда на карте будет видно, что за ним.', deviceId=src.get('deviceId'), port=e.get('sourcePort'))

    weak = []
    for d in devices:
        for c in (states.get(d['id']) or {}).get('clients') or []:
            if isinstance(c.get('rssi'), (int, float)) and c['rssi'] <= -75 and c.get('online', True):
                weak.append(f"{c.get('name') or c.get('mac')} ({c['rssi']} дБм)")
    if weak:
        add('info', f"Слабый Wi-Fi у {len(weak)} {_plural(len(weak), 'устройства', 'устройств', 'устройств')}",
            ', '.join(weak[:6]) + ('…' if len(weak) > 6 else '') + '. Им может не хватать скорости — поможет ещё одна точка или перенос текущей.')

    for d in devices:
        st = states.get(d['id']) or {}
        if d.get('driver') not in ('tplink_jetstream', 'snmp', 'demo_switch', 'demo_sim_switch'):
            continue
        for p in st.get('ports') or []:
            sp = p.get('speed') or 0
            bps = max(p.get('rxBps') or 0, p.get('txBps') or 0)
            if p.get('link') and sp and bps > sp * 1e6 * .7:
                add('warn', f"{d.get('name')}: порт {p['n']} загружен на {round(bps / sp / 1e4)}%",
                    f"{p.get('label') or ''} — канал близок к пределу {sp} Мбит/с.", deviceId=d['id'], port=p['n'])

    order = {'bad': 0, 'warn': 1, 'info': 2}
    checks.sort(key=lambda c: order.get(c['level'], 3))
    score = max(0, 100 - sum({'bad': 20, 'warn': 8, 'info': 2}.get(c['level'], 0) for c in checks))
    if not checks:
        add('ok', 'Замечаний нет', 'Все узлы на связи, кабели в порядке, скорость линков нормальная.')
    stats = {'devices': total_local, 'infra': len(infra), 'switches': len(switches), 'aps': len(aps), 'remote': len(remote),
             'levels': len(levels), 'clients': sum(1 for n in nodes.values() if n.get('client'))}
    return {'type': ttype, 'score': score, 'spof': spof[:6], 'bridges': bridges[:4], 'checks': checks, 'stats': stats}
