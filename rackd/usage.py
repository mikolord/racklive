"""What Rack Live itself costs: processor, memory, disk (Настройки → О программе → «Потребление»). Only this program is measured, not the whole NAS.
Nothing here changes anything: it reads /proc (or the Windows API), the sizes of Rack Live's own folders and the figures the assistant already keeps."""
import os
import shutil
import threading
import time
from collections import deque

# what is in the data folder, by the top-level name → the group shown to the person
GROUPS = [
    ('config', 'Настройки и устройства', ('config.json', 'auth.json', 'sessions.json', 'mfa.json', 'known.json', 'routers.json', 'camcreds.json', 'models.json', 'apps.json')),
    ('history', 'История, события и замеры', ('history.json', 'events.json', 'uptime.json', 'speedtests.json', 'inetspeed.json', 'cable.json', 'alerts.json', 'smart.json', 'advice.json')),
    ('backups', 'Копии настроек роутеров', ('backups', 'backups.json', 'scene-backups')),
    ('frank', 'Разговоры и расход Frank', ('ai_chats.json', 'ai.json', 'tg_frank.json')),
    ('media', 'Фото карточек, иконки, оформления, шаблоны', ('cardphotos', 'icons', 'themes', 'portal')),
]
_KNOWN = {name: (gid, label) for gid, label, names in GROUPS for name in names}


def _tree_size(path):
    """bytes under a path (files only, links are not followed)"""
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            if os.path.isfile(p):
                try:
                    total += os.path.getsize(p)
                except OSError:
                    pass
    return total


def rss_bytes():
    """(now, peak) resident memory of this process"""
    try:
        now = peak = None
        with open('/proc/self/status') as f:
            for l in f:
                if l.startswith('VmRSS:'):
                    now = int(l.split()[1]) * 1024
                elif l.startswith('VmHWM:'):
                    peak = int(l.split()[1]) * 1024
        if now:
            return now, peak
    except OSError:
        pass
    try:                                                    # Windows (a local run on a PC)
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(pmc)
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        f = getattr(k, 'K32GetProcessMemoryInfo', None) or ctypes.WinDLL('psapi').GetProcessMemoryInfo
        f.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        f.restype = wintypes.BOOL
        if f(k.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return int(pmc.WorkingSetSize), int(pmc.PeakWorkingSetSize)
    except Exception:
        pass
    return None, None


def container_memory():
    """(used, limit) of the whole container when the program runs in Docker (cgroup v2 or v1); limit None = not set"""
    for used_f, lim_f in (('/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory.max'),
                          ('/sys/fs/cgroup/memory/memory.usage_in_bytes', '/sys/fs/cgroup/memory/memory.limit_in_bytes')):
        try:
            used = int(open(used_f).read().strip())
        except (OSError, ValueError):
            continue
        try:
            raw = open(lim_f).read().strip()
            lim = None if raw == 'max' else int(raw)
            if lim is not None and lim > 1 << 50:           # «no limit» is written as a huge number
                lim = None
        except (OSError, ValueError):
            lim = None
        return used, lim
    return None, None


class Usage:
    def __init__(self, data_dir, code_dirs):
        self.data_dir, self.code_dirs = data_dir, [d for d in code_dirs if d]
        self.t0 = time.time()
        self.samples = deque(maxlen=120)                    # one point a minute → the last two hours
        self.lock = threading.Lock()
        self._disk = (0.0, None)                            # (time, result) — walking the folders is not free, so it is cached
        self._code = (0.0, 0)

    def sample(self):
        """called from the poller; keeps one point a minute"""
        now = time.time()
        with self.lock:
            if self.samples and now - self.samples[-1]['t'] < 55:
                return
            rss, _ = rss_bytes()
            self.samples.append({'t': now, 'cpu': time.process_time(), 'rss': rss})

    def _cpu(self, now):
        """% of one processor core: over the last minutes, and over the whole run"""
        cpu_now, total = time.process_time(), time.process_time()
        up = max(1.0, now - self.t0)
        recent = None
        with self.lock:
            ref = next((s for s in reversed(self.samples) if now - s['t'] >= 20), None)
        if ref:
            recent = max(0.0, (cpu_now - ref['cpu']) / max(1.0, now - ref['t']) * 100)
        return {'now': None if recent is None else round(recent, 1), 'avg': round(total / up * 100, 1), 'seconds': round(total, 1), 'cores': os.cpu_count() or 1}

    def _disk_info(self, now):
        if self._disk[1] is not None and now - self._disk[0] < 120:
            return self._disk[1]
        groups = {}
        other = 0
        try:
            names = os.listdir(self.data_dir)
        except OSError:
            names = []
        for n in names:
            size = _tree_size(os.path.join(self.data_dir, n))
            if n.startswith('config') and n.endswith('.json') or n.startswith('config.bak'):
                gid, label = 'config', 'Настройки и устройства'
            elif n in _KNOWN:
                gid, label = _KNOWN[n]
            else:
                other += size
                continue
            g = groups.setdefault(gid, {'id': gid, 'label': label, 'bytes': 0})
            g['bytes'] += size
        items = sorted(groups.values(), key=lambda g: -g['bytes'])
        if other:
            items.append({'id': 'other', 'label': 'Прочее', 'bytes': other})
        try:
            du = shutil.disk_usage(self.data_dir)
            free, total = du.free, du.total
        except OSError:
            free = total = None
        res = {'data': sum(i['bytes'] for i in items), 'items': items, 'free': free, 'total': total}
        self._disk = (now, res)
        return res

    def _code_size(self, now):
        if self._code[0] and now - self._code[0] < 1800:
            return self._code[1]
        size = sum(_tree_size(d) for d in self.code_dirs)
        self._code = (now, size)
        return size

    def public(self, ai=None):
        now = time.time()
        rss, peak = rss_bytes()
        c_used, c_lim = container_memory()
        with self.lock:
            hist = [{'t': s['t'], 'rss': s['rss']} for s in self.samples]
            cpus = list(self.samples)
        # the processor line for the chart: % between two neighbouring points
        for i in range(1, len(cpus)):
            dt = cpus[i]['t'] - cpus[i - 1]['t']
            hist[i]['cpu'] = round(max(0.0, (cpus[i]['cpu'] - cpus[i - 1]['cpu']) / dt * 100), 1) if dt > 0 else 0
        disk = dict(self._disk_info(now), code=self._code_size(now))
        out = {'now': now, 'uptime': round(now - self.t0), 'pid': os.getpid(), 'threads': threading.active_count(),
               'cpu': self._cpu(now), 'mem': {'rss': rss, 'peak': peak, 'container': c_used, 'limit': c_lim},
               'disk': disk, 'history': hist[1:]}
        if ai:
            out['frank'] = ai
        return out
