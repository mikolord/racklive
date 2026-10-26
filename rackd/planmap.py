"""The pictures under the «План» (territory): satellite snapshots or photos of the plot, and the outlines of the houses on them.
  - up to 6 pictures («фоны»): a wide overview of the district plus detailed ones where the houses are. Each is ONE file, data/plan/bg-<id>.<jpg|png|webp>
    (the browser stitches a satellite snapshot from map tiles once and uploads the result, so the server never decodes images and never talks to a map
    service); its place / size / transparency is an entry of plan['bgs'] = [{id, name, v, ext, x, y, w, h, op, attr, lat, lon, z, r}];
  - the outline of a house is building['outline'] = [[x, y], …] in the plan's own units (10 units = 1 metre when the picture comes from a map).
Everything the browser sends is checked here: kinds of files by their first bytes, numbers clamped, the number of points and pictures limited.
The browser may move / dim / rename a picture it already has, but never add, remove or swap one through the plan: that goes through the picture routes only
(so an old tab can neither bring a deleted picture back nor drop a new one)."""
import os
import re
import secrets
import time

MAX_BYTES = 3_000_000
MAX_BGS = 6
MAX_POINTS = 120
LIMIT = 400_000                 # plan units: nothing is placed further than this from the origin (a 20 km overview is 200 000 units wide)
EXTS = ('jpg', 'png', 'webp')
ID_RE = re.compile(r'^[a-z0-9]{3,12}$')


def folder(data_dir):
    return os.path.join(data_dir, 'plan')


def new_id():
    return 'g' + secrets.token_hex(3)


def kind_of(data):
    """file type by its first bytes (the name and Content-Type are not trusted)"""
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def path_of(data_dir, bid):
    if not ID_RE.match(str(bid or '')):
        return None
    for ext in EXTS:
        f = os.path.join(folder(data_dir), f'bg-{bid}.{ext}')
        if os.path.isfile(f):
            return f
    return None


def remove(data_dir, bid):
    if not ID_RE.match(str(bid or '')):
        return
    for ext in EXTS:
        try:
            os.remove(os.path.join(folder(data_dir), f'bg-{bid}.{ext}'))
        except OSError:
            pass


def save(data_dir, bid, raw):
    """→ (ext, error)"""
    if not ID_RE.match(str(bid or '')):
        return None, 'неверный номер фона'
    if not raw or len(raw) > MAX_BYTES:
        return None, 'картинка пустая или больше 3 МБ'
    ext = kind_of(raw)
    if not ext:
        return None, 'нужна картинка JPEG, PNG или WebP'
    os.makedirs(folder(data_dir), exist_ok=True)
    remove(data_dir, bid)
    tmp = os.path.join(folder(data_dir), f'bg-{bid}.tmp')
    with open(tmp, 'wb') as f:
        f.write(raw)
    os.replace(tmp, os.path.join(folder(data_dir), f'bg-{bid}.{ext}'))
    return ext, ''


def _num(v, lo, hi, nd=1):
    if isinstance(v, bool):
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return round(max(lo, min(hi, v)), nd)


def _name(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip()[:40]


def make_bg(meta, ext, bid):
    """the record of a freshly uploaded picture: meta = what the browser says about its place → dict or None"""
    meta = meta or {}
    x, y = _num(meta.get('x'), -LIMIT, LIMIT), _num(meta.get('y'), -LIMIT, LIMIT)
    w, h = _num(meta.get('w'), 50, LIMIT), _num(meta.get('h'), 50, LIMIT)
    if None in (x, y, w, h):
        return None
    bg = {'id': bid, 'name': _name(meta.get('name')), 'v': int(time.time()), 'ext': ext, 'x': x, 'y': y, 'w': w, 'h': h,
          'op': _num(meta.get('op'), 0.1, 1, 2) or 0.85, 'attr': str(meta.get('attr') or '')[:120]}
    for k, lo, hi, nd in (('lat', -90, 90, 6), ('lon', -180, 180, 6), ('z', 1, 22, 0), ('r', 10, 100_000, 0)):
        n = _num(meta.get(k), lo, hi, nd)
        if n is not None:
            bg[k] = int(n) if k in ('z', 'r') else n
    return bg


def clean_bgs(new, old):
    """what the browser may change about the pictures it already has: place, size, transparency, name.
    Pictures are never added or removed from here; whatever the browser lists that the server does not know is ignored."""
    old = [b for b in (old or []) if isinstance(b, dict) and ID_RE.match(str(b.get('id') or '')) and b.get('ext') in EXTS]
    given = {str(b.get('id')): b for b in (new or []) if isinstance(b, dict)}
    out = []
    for b in old:
        c, n = dict(b), given.get(b['id'])
        if n:
            for k, lo, hi, nd in (('x', -LIMIT, LIMIT, 1), ('y', -LIMIT, LIMIT, 1), ('w', 50, LIMIT, 1), ('h', 50, LIMIT, 1), ('op', 0.1, 1, 2)):
                v = _num(n.get(k), lo, hi, nd)
                if v is not None:
                    c[k] = v
            if 'name' in n:
                c['name'] = _name(n.get('name'))
        out.append(c)
    return out


def migrate(cfg, data_dir):
    """the single picture of the first version (plan['bg'], data/plan/bg.<ext>) becomes the first of the list (the file is renamed). → True when the config changed"""
    plan = cfg.get('plan')
    if not isinstance(plan, dict) or 'bg' not in plan:
        return False
    old = plan.pop('bg')
    if isinstance(old, dict) and old.get('ext') in EXTS and not plan.get('bgs'):
        src = os.path.join(folder(data_dir), 'bg.' + old['ext'])
        if os.path.isfile(src):
            bid = new_id()
            try:
                os.replace(src, os.path.join(folder(data_dir), f'bg-{bid}.{old["ext"]}'))
                plan['bgs'] = [dict(old, id=bid, name=old.get('name') or 'Фон')]
            except OSError:
                pass
    return True


def clean_outline(o):
    """[[x, y], …] with 3…120 points, or None"""
    if not isinstance(o, list) or not 3 <= len(o) <= MAX_POINTS:
        return None
    pts = []
    for p in o:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            return None
        x, y = _num(p[0], -LIMIT, LIMIT), _num(p[1], -LIMIT, LIMIT)
        if x is None or y is None:
            return None
        pts.append([x, y])
    return pts


def clean_buildings(buildings):
    """the outlines are checked; the rest of a building is the plan's own business (as before)"""
    out = []
    for b in buildings:
        if isinstance(b, dict) and 'outline' in b:
            b = dict(b)
            o = clean_outline(b.get('outline'))
            if o:
                b['outline'] = o
            else:
                b.pop('outline', None)
        out.append(b)
    return out
