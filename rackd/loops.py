"""Network loops: what a cable plugged into two ports of the same network does, and how it is noticed.

A loop makes frames circle for ever: the switch table «forgets» where devices are (the same MAC appears on one port, then on another, over and over)
and broadcast / multicast frames multiply until the network stops. Three witnesses, any of them is enough to raise the alarm:
  guard — the switch's own loop protection says it found one (TP-Link loopback-detection) — the most reliable;
  storm — a port receives thousands of broadcast / multicast frames per second for several polls in a row;
  flap  — several devices «jump» between the same ports again and again.
The result of every poll of a switch gets st['loops'] = {active, why, guard, storm, flap}; events go to the journal once per incident."""
import time
from collections import defaultdict

STORM_PPS = 5000             # broadcast + multicast frames per second on one port (a home port sees tens)
STORM_POLLS = 2              # ...for this many polls in a row
FLAP_WINDOW = 900            # seconds that count
FLAP_MOVES = 4               # a device that changed port this many times in the window is «jumping»
FLAP_MACS = 3                # ...and this many of them at once is a loop (a couple of roaming phones are not)
FLAP_SAME = 3                # ...or this many that jump between the very same two ports (one or two roaming phones are normal Wi-Fi)
CALM = 600                   # seconds without signs before the loop is declared gone


class LoopWatch:
    def __init__(self, store):
        self.store = store
        self.moves = defaultdict(dict)       # did -> mac -> [(t, port)]  (appended when the port changed)
        self.streak = defaultdict(int)       # (did, port) -> polls in a row over the storm limit
        self.active = {}                     # did -> {'since', 'last'}

    def observe(self, d, st, wifi=()):
        """called for every fresh poll that carries ports; fills st['loops'] and writes the journal"""
        ports = st.get('ports') or []
        if not ports or st.get('status') == 'offline':
            return
        did, now = d['id'], st.get('updated') or time.time()
        guard = [{'port': p['n'], 'blocked': bool(p.get('loopBlocked'))} for p in ports if p.get('loopDetected') or p.get('loopBlocked')]
        storm = []
        for p in ports:
            k = (did, p['n'])
            self.streak[k] = self.streak[k] + 1 if (p.get('bcastPps') or 0) >= STORM_PPS else 0
            if self.streak[k] >= STORM_POLLS:
                storm.append({'port': p['n'], 'pps': p['bcastPps'], 'label': p.get('label') or ''})
        hist = self.moves[did]
        here = {}                                            # one port per device per poll: if the table lists it on several (an uplink also sees the whole
        for p in ports:                                      # network), the lowest number wins — a device is not «jumping» just because of how the list is ordered
            for peer in p.get('peers') or []:
                mac = (peer.get('mac') or '').lower()
                if not mac or mac in wifi:                   # wireless clients are skipped: the switch only sees them through an access
                    continue                                 # point's port, and they move between access points by design
                if mac not in here or p['n'] < here[mac]:
                    here[mac] = p['n']
        for mac, port in here.items():
            h = hist.setdefault(mac, [])
            if not h or h[-1][1] != port:
                h.append((now, port))
        for mac in list(hist):
            hist[mac] = [x for x in hist[mac] if now - x[0] <= FLAP_WINDOW]
            if not hist[mac]:
                del hist[mac]
        jumpers = {m: h for m, h in hist.items() if len(h) - 1 >= FLAP_MOVES}
        by_pair = defaultdict(list)
        for m, h in jumpers.items():
            by_pair[frozenset(x[1] for x in h)].append(m)
        # a phone walking between two Wi-Fi access points «jumps» between their ports — that is roaming, not a loop, so one or two devices never count
        flap_on = len(jumpers) >= FLAP_MACS or any(len(v) >= FLAP_SAME and len(k) == 2 for k, v in by_pair.items())
        flap = [{'mac': m, 'moves': len(h) - 1, 'ports': sorted({x[1] for x in h})} for m, h in jumpers.items()] if flap_on else []
        why = []
        if guard:
            why.append('коммутатор сам нашёл петлю на ' + ('порту ' if len(guard) == 1 else 'портах ') + ', '.join(str(g['port']) for g in guard) +
                       (' и отключил его' if any(g['blocked'] for g in guard) and len(guard) == 1 else ''))
        if storm:
            why.append('порт ' + ', '.join(str(s['port']) for s in storm) + f" принимает ~{max(s['pps'] for s in storm):,} широковещательных кадров в секунду".replace(',', ' ') + ' (норма — десятки)')
        if flap:
            ps = sorted({p for f in flap for p in f['ports']})
            why.append(f"{len(flap)} устр. «прыгают» между портами {', '.join(map(str, ps[:6]))}")
        active = bool(why)
        st['loops'] = {'active': active, 'why': '; '.join(why), 'guard': guard, 'storm': storm, 'flap': flap[:6],
                       'since': self.active.get(did, {}).get('since') if active else None}
        name = d.get('name') or d.get('host')
        if active:
            if did not in self.active:
                self.active[did] = {'since': now, 'last': now}
                st['loops']['since'] = now
                self.store.add_event(did, name, 'warning', 'возможна петля: ' + st['loops']['why'])
            self.active[did]['last'] = now
        elif did in self.active and now - self.active[did]['last'] > CALM:
            self.store.add_event(did, name, 'online', 'признаков петли больше нет')
            del self.active[did]
        elif did in self.active:                              # quiet, but not for long enough: still «recent»
            st['loops']['recent'] = True
