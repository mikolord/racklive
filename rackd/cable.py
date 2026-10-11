"""Cable diagnostics (TDR / VCT) — turns raw per-pair results into a verdict a human understands.

A driver measures and passes `pairs` = [{'pair': 'A'..'D', 'status': 'normal'|'open'|'short'|'unknown'|..., 'len': metres|None}]
(one list per run; several runs are merged, because a single TDR shot on a live link is noisy).
"""
import statistics, time

# T568B: A = 1-2, B = 3-6, C = 4-5, D = 7-8
PAIRS = {'A': ('1-2', 'оранжевая'), 'B': ('3-6', 'зелёная'), 'C': ('4-5', 'синяя'), 'D': ('7-8', 'коричневая')}
FAULTS = ('open', 'short', 'impedance', 'crosstalk')


def _merge(runs):
    out = []
    for name in 'ABCD':
        seen = [p for r in runs for p in r if p['pair'] == name]
        if not seen:
            continue
        normal = [p for p in seen if p['status'] == 'normal']
        if normal:                                   # one clean shot is enough — faults on a live pair are noise
            lens = [p['len'] for p in normal if p.get('len') is not None]
            out.append({'pair': name, 'status': 'normal', 'len': round(statistics.median(lens)) if lens else None})
            continue
        faults = [p for p in seen if p['status'] in FAULTS]
        if faults:
            st = max(set(p['status'] for p in faults), key=lambda s: sum(1 for p in faults if p['status'] == s))
            lens = [p['len'] for p in faults if p['status'] == st and p.get('len') is not None]
            out.append({'pair': name, 'status': st, 'len': round(statistics.median(lens)) if lens else None})
        else:
            out.append({'pair': name, 'status': 'unknown', 'len': None})
    for p in out:
        p['pins'], p['color'] = PAIRS[p['pair']]
    return out


def _where(m, total):
    if m is None:
        return ''
    if m <= 2:
        return 'у самого коммутатора (разъём в шкафу)'
    if total and m >= total * .7:
        return f'≈ {m} м от коммутатора — ближе к дальнему концу'
    return f'≈ {m} м от коммутатора'


def analyze(runs, link=False, speed=0):
    pairs = _merge(runs)
    good = [p for p in pairs if p['status'] == 'normal']
    bad = [p for p in pairs if p['status'] in FAULTS]
    lens = [p['len'] for p in good if p['len']]
    total = round(statistics.median(lens)) if lens else None
    res = {'t': int(time.time()), 'pairs': pairs, 'length': total, 'link': link, 'speed': speed}
    names = lambda ps: ', '.join(f"{p['pair']} ({p['color']}, {p['pins']})" for p in ps)

    if link and speed >= 1000:
        # gigabit needs all four pairs — whatever the TDR said about one of them is measurement noise
        for p in pairs:
            if p['status'] != 'normal':
                p['status'], p['note'] = 'normal', 'по линку 1 Гбит/с'
        res.update(verdict='ok', text='Кабель в порядке: работают все 4 пары' + (f', длина ≈ {total} м' if total else '') + '.')
        return res
    if not bad and len(good) == len(pairs) and pairs:
        res.update(verdict='ok', text='Кабель в порядке' + (f', длина ≈ {total} м' if total else '') + '.')
        return res
    if not good and bad and all(p['status'] == 'open' for p in bad):
        ls = [p['len'] for p in bad if p['len'] is not None]
        far = round(statistics.median(ls)) if ls else None
        if not far or far <= 2:
            res.update(verdict='empty', text='Кабель не подключён (или обрыв прямо у коммутатора).')
        else:
            res.update(verdict='empty', length=far, text=f'Подключён кабель ≈ {far} м, на другом конце ничего нет — '
                                                          'устройство выключено или кабель никуда не воткнут.')
        return res
    if not bad:
        res.update(verdict='unknown', text='Коммутатор не смог измерить кабель. Попробуйте ещё раз.')
        return res
    shorts = [p for p in bad if p['status'] == 'short']
    lines = []
    for p in bad:
        what = {'open': 'обрыв', 'short': 'замыкание', 'impedance': 'плохое сопротивление', 'crosstalk': 'наводки'}[p['status']]
        lines.append(f"пара {p['pair']} ({p['color']}, контакты {p['pins']}): {what} {_where(p['len'], total)}".strip())
    if link and len(good) >= 2 and not shorts:
        head = f"Работают только {len(good)} пары из 4 — поэтому скорость {speed} Мбит/с вместо 1 Гбит/с."
    elif shorts:
        head = 'Замыкание в кабеле — неправильно обжат или перебит.'
    else:
        head = 'Повреждение кабеля.'
    near = [p for p in bad if (p['len'] or 0) <= 2]
    where = ' разъём со стороны шкафа' if len(near) == len(bad) else ' оба разъёма, начните со стороны шкафа' if near else ' оба разъёма'
    hint = 'Скорее всего плохой обжим: переобожмите' + where + '. Если не поможет — кабель перебит, ищите место по расстоянию (точность ±5–10 м).'
    res.update(verdict='bad' if shorts or not link else 'warn', text=head, details=lines, hint=hint)
    return res
