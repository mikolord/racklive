"""Configuration backups with history: the running config of routers / switches is saved when it changes,
with a diff to the previous version. Files live in data/backups/<device>/<unix time>.txt (full text, for restore);
the comparison ignores service lines (Keenetic «! $$$ Last change / Md5 / Agent»), the diff shown in the UI hides secrets.
"""
import difflib, hashlib, json, os, re, threading, time

KEEP = 60                                   # versions per device
EVERY = 6 * 3600                            # automatic check interval by default (settings.backupEvery, hours, overrides it)
CHOICES = (6, 24, 168, 0)                   # every 6 h · once a day · once a week · only by hand
KEEP_DAYS = 7                               # old versions go after this many days by default (settings.backupKeepDays; 0 = only the KEEP limit)
KEEP_CHOICES = (7, 30, 90, 0)               # the newest version of a device is never removed
# any word containing key / pass / secret / psk / token / hash (private_key, faskey, wpa_passphrase, community…): hide the rest of the line
SECRET = re.compile(r'''(?i)(?<!['"\w-])([\w-]*(?:key|pass|secret|psk|token|community|hash|authentication)[\w-]*)\b(\s*=?\s*)(\S.*)$''')
NOISE = re.compile(r'^! \$\$\$ ')


def normalize(text):
    return '\n'.join(l.rstrip() for l in text.replace('\r', '').split('\n') if not NOISE.match(l)).strip() + '\n'


def mask(line):
    return SECRET.sub(lambda m: m.group(1) + (m.group(2) or ' ') + '••••••', line)


class Backups:
    def __init__(self, store):
        self.store = store
        self.dir = os.path.join(store.dir, 'backups')
        os.makedirs(self.dir, exist_ok=True)
        self.index = store._load('backups.json', {})          # did -> [{t, hash, lines, added, removed}]
        self.lock = threading.Lock()
        self.last_try = {}

    def _save_index(self):
        self.store._dump('backups.json', self.index)
        self.store.bump()

    def path(self, did, t):
        return os.path.join(self.dir, re.sub(r'\W', '', did), f'{int(t)}.txt')

    def read(self, did, t):
        with open(self.path(did, t), encoding='utf-8') as f:
            return f.read()

    def due(self, did, hours=None):
        """time for the automatic check? `hours` from the settings (None = default, 0 = never by itself).
        The last check survives a restart through the index (else a weekly schedule would run on every start)."""
        every = EVERY if hours is None else int(hours) * 3600
        if every <= 0:
            return False
        vers = self.index.get(did) or []
        last = max(self.last_try.get(did, 0), (vers[-1].get('checked') or vers[-1]['t']) if vers else 0)
        return time.time() - last >= every

    def take(self, d, drv, force=False):
        """Fetch the config; store a new version only when it differs. → (version | None, message)."""
        did = d['id']
        self.last_try[did] = time.time()
        text = drv.backup(d)
        norm = normalize(text)
        h = hashlib.sha256(norm.encode()).hexdigest()[:16]
        with self.lock:
            vers = self.index.setdefault(did, [])
            if vers and vers[-1]['hash'] == h:
                vers[-1]['checked'] = int(time.time())
                self._save_index()
                return None, 'конфигурация не изменилась'
            added = removed = 0
            if vers:
                old = normalize(self.read(did, vers[-1]['t'])).splitlines()
                for l in difflib.ndiff(old, norm.splitlines()):
                    added += l.startswith('+ ')
                    removed += l.startswith('- ')
            t = int(time.time())
            os.makedirs(os.path.dirname(self.path(did, t)), exist_ok=True)
            with open(self.path(did, t), 'w', encoding='utf-8') as f:
                f.write(text)
            try:
                os.chmod(self.path(did, t), 0o600)
            except OSError:
                pass
            v = {'t': t, 'hash': h, 'lines': len(norm.splitlines()), 'added': added, 'removed': removed, 'first': not vers, 'checked': t}
            vers.append(v)
            for old in vers[:-KEEP]:
                try:
                    os.remove(self.path(did, old['t']))
                except OSError:
                    pass
            del vers[:-KEEP]
            self._save_index()
        msg = 'сохранена первая копия конфигурации' if v['first'] else f"конфигурация изменилась: +{added} −{removed} строк"
        return v, msg

    def prune(self, days):
        """remove versions older than `days` (0 = keep all up to KEEP); the newest version of every device always stays. → removed count"""
        days = KEEP_DAYS if days is None else int(days)
        if days <= 0:
            return 0
        edge = time.time() - days * 86400
        n = 0
        with self.lock:
            for did, vers in self.index.items():
                old = [v for v in vers[:-1] if v['t'] < edge]
                if not old:
                    continue
                for v in old:
                    try:
                        os.remove(self.path(did, v['t']))
                    except OSError:
                        pass
                gone = {v['t'] for v in old}
                vers[:] = [v for v in vers if v['t'] not in gone]
                n += len(old)
            if n:
                self._save_index()
        return n

    def diff(self, did, t, prev=None):
        """Unified diff (secrets masked) between version `t` and the previous one (or `prev`)."""
        vers = self.index.get(did) or []
        i = next((k for k, v in enumerate(vers) if v['t'] == int(t)), None)
        if i is None:
            return []
        p = int(prev) if prev else (vers[i - 1]['t'] if i else None)
        a = normalize(self.read(did, p)).splitlines() if p else []
        b = normalize(self.read(did, t)).splitlines()
        out = []
        for l in difflib.unified_diff(a, b, lineterm='', n=2):
            if l.startswith(('---', '+++')):
                continue
            out.append(mask(l))
        return out[:4000]

    def forget(self, did):
        with self.lock:
            for v in self.index.pop(did, []):
                try:
                    os.remove(self.path(did, v['t']))
                except OSError:
                    pass
            self._save_index()
