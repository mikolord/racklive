"""Availability over the last 30 days: every poll adds the time since the previous one to the device's day
(up or down by the previous status) and opens / closes outages. Mesh access points the router reports
(state.children) are tracked too, under '<device>:c:<key>'.

data/uptime.json: {key: {name, dev, kind, up: bool, last: t, days: {'YYYY-MM-DD': [up_s, total_s]}, outs: [[start, end|None], …]}}
A gap longer than GAP between samples (Rack Live itself was stopped) counts as neither up nor down.
"""
import threading, time

DAYS = 30
GAP = 900
SAVE_EVERY = 120
UP = ('online', 'warning')


def _day(t):
    return time.strftime('%Y-%m-%d', time.localtime(t))


class Uptime:
    def __init__(self, store):
        self.store = store
        self.data = store._load('uptime.json', {})
        self.lock = threading.Lock()
        self.saved = 0

    def sample(self, key, name, dev, up, t, kind='device'):
        with self.lock:
            e = self.data.setdefault(key, {'days': {}, 'outs': []})
            e.update(name=name, dev=dev, kind=kind)
            last, was = e.get('last'), e.get('up')
            if last and 0 < t - last <= GAP:
                dd = e['days'].setdefault(_day(t), [0, 0])
                dd[1] += round(t - last)
                if was:
                    dd[0] += round(t - last)
            if was is not None and was != up:
                if not up:
                    e['outs'].append([round(t), None])
                elif e['outs'] and e['outs'][-1][1] is None:
                    e['outs'][-1][1] = round(t)
            e['up'], e['last'] = up, t
        if t - self.saved > SAVE_EVERY:
            self.save(t)

    def from_state(self, d, st, t):
        """one poll of a device (and of the mesh points it reports)"""
        status = st.get('status')
        if status not in UP and status != 'offline':
            return
        self.sample(d['id'], d.get('name') or d.get('host'), d['id'], status in UP, t)
        if status not in UP:
            return                                   # the router is down: we know nothing about its mesh points
        seen = set()
        for ch in st.get('children') or []:
            if not ch.get('key'):
                continue
            k = f"{d['id']}:c:{ch['key']}"
            seen.add(k)
            self.sample(k, ch.get('name') or 'Точка доступа', d['id'], (ch.get('status') or 'online') in UP, t, 'ap')
        for k, e in list(self.data.items()):          # a mesh point that vanished from the router's list is down
            if e.get('dev') == d['id'] and e.get('kind') == 'ap' and k not in seen and e.get('up') is not None:
                self.sample(k, e.get('name'), d['id'], False, t, 'ap')

    def save(self, t=None):
        t = t or time.time()
        cut = t - (DAYS + 1) * 86400
        with self.lock:
            for k, e in list(self.data.items()):
                e['days'] = {d: v for d, v in e['days'].items() if d >= _day(cut)}
                e['outs'] = [o for o in e['outs'] if (o[1] or t) >= cut][-200:]
                if (e.get('last') or 0) < cut:
                    del self.data[k]
            self.saved = t
            self.store._dump('uptime.json', self.data)

    def seed_demo(self, devices, now=None):
        """demo mode: a month of made-up history (a flaky camera, one router reboot) so the screens aren't empty"""
        import random
        now, rnd = now or time.time(), random.Random(7)
        for i, d in enumerate(devices):
            e = self.data.setdefault(d['id'], {'days': {}, 'outs': [], 'name': d.get('name'), 'dev': d['id'], 'kind': 'device'})
            flaky = (d.get('kind') == 'camera' and i % 3 == 0) or d.get('kind') == 'router'
            for k in range(1, DAYS):
                day, down = _day(now - k * 86400), 0
                if flaky and rnd.random() < (.25 if d.get('kind') == 'camera' else .05):
                    down = rnd.choice([90, 240, 600, 1500, 4200])
                    start = now - k * 86400 + rnd.randint(3600, 70000)
                    e['outs'].append([round(start), round(start + down)])
                e['days'][day] = [86400 - down, 86400]
            e['outs'].sort()
            e['up'], e['last'] = True, now - 60

    def forget(self, dev):
        with self.lock:
            for k in [k for k, e in self.data.items() if e.get('dev') == dev]:
                del self.data[k]

    def public(self, devices, now=None):
        """→ [{key, name, dev, kind, pct, pct7, days: [pct|None ×30], outs, downNow, last: {start, end, dur}, longest, worstDay}]"""
        now = now or time.time()
        ids = {d['id'] for d in devices}
        out = []
        with self.lock:
            items = [(k, dict(e, days=dict(e['days']), outs=[list(o) for o in e['outs']])) for k, e in self.data.items()]
        for k, e in items:
            if e.get('dev') not in ids:
                continue
            days = [_day(now - i * 86400) for i in range(DAYS - 1, -1, -1)]
            per = [e['days'].get(d) for d in days]
            def pct(rows):
                rows = [r for r in rows if r and r[1]]
                tot = sum(r[1] for r in rows)
                return round(sum(r[0] for r in rows) * 100 / tot, 2) if tot else None
            outs = [o for o in e['outs'] if (o[1] or now) >= now - DAYS * 86400]
            durs = [((o[1] or now) - o[0]) for o in outs]
            lo = outs[-1] if outs else None
            out.append({'key': k, 'name': e.get('name'), 'dev': e.get('dev'), 'kind': e.get('kind'),
                        'pct': pct(per), 'pct7': pct(per[-7:]), 'days': [round(r[0] * 100 / r[1], 1) if r and r[1] else None for r in per],
                        'outs': len(outs), 'outs7': sum(1 for o in outs if (o[1] or now) >= now - 7 * 86400),
                        'downNow': e.get('up') is False, 'down': sum(durs),
                        'last': {'start': lo[0], 'end': lo[1], 'dur': round((lo[1] or now) - lo[0])} if lo else None,
                        'longest': round(max(durs)) if durs else 0,
                        'since': min((d for d in e['days']), default=None)})
        out.sort(key=lambda x: (x['pct'] if x['pct'] is not None else 101, x['name'] or ''))
        return out
