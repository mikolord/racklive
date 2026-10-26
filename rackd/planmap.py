"""The picture under the «План» (territory): a satellite snapshot or a photo of the plot, and the outlines of the houses on it.
  - the picture is ONE file, data/plan/bg.<jpg|png|webp> (the browser stitches a satellite snapshot from map tiles once and uploads the result, so the
    server never decodes images and never talks to a map service); its place/size/transparency is plan['bg'] = {v, ext, x, y, w, h, op, attr, ...};
  - the outline of a house is building['outline'] = [[x, y], …] in the plan's own units (10 units = 1 metre when the picture comes from a map).
Everything the browser sends is checked here: kinds of files by their first bytes, numbers clamped, the number of points limited."""
import os
import time

MAX_BYTES = 3_000_000
MAX_POINTS = 120
LIMIT = 200_000                 # plan units: nothing is placed further than this from the origin
EXTS = ('jpg', 'png', 'webp')


def folder(data_dir):
    return os.path.join(data_dir, 'plan')


def kind_of(data):
    """file type by its first bytes (the name and Content-Type are not trusted)"""
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def path_of(data_dir):
    for ext in EXTS:
        f = os.path.join(folder(data_dir), 'bg.' + ext)
        if os.path.isfile(f):
            return f
    return None


def remove(data_dir):
    for ext in EXTS:
        try:
            os.remove(os.path.join(folder(data_dir), 'bg.' + ext))
        except OSError:
            pass


def save(data_dir, raw):
    """→ (ext, error)"""
    if not raw or len(raw) > MAX_BYTES:
        return None, 'картинка пустая или больше 3 МБ'
    ext = kind_of(raw)
    if not ext:
        return None, 'нужна картинка JPEG, PNG или WebP'
    os.makedirs(folder(data_dir), exist_ok=True)
    remove(data_dir)
    tmp = os.path.join(folder(data_dir), 'bg.tmp')
    with open(tmp, 'wb') as f:
        f.write(raw)
    os.replace(tmp, os.path.join(folder(data_dir), 'bg.' + ext))
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


def make_bg(meta, ext):
    """the record of a freshly uploaded picture: meta = what the browser says about its place → dict or None"""
    meta = meta or {}
    x, y = _num(meta.get('x'), -LIMIT, LIMIT), _num(meta.get('y'), -LIMIT, LIMIT)
    w, h = _num(meta.get('w'), 50, LIMIT), _num(meta.get('h'), 50, LIMIT)
    if None in (x, y, w, h):
        return None
    bg = {'v': int(time.time()), 'ext': ext, 'x': x, 'y': y, 'w': w, 'h': h, 'op': _num(meta.get('op'), 0.1, 1, 2) or 0.85,
          'attr': str(meta.get('attr') or '')[:120]}
    for k, lo, hi, nd in (('lat', -90, 90, 6), ('lon', -180, 180, 6), ('z', 1, 22, 0)):
        n = _num(meta.get(k), lo, hi, nd)
        if n is not None:
            bg[k] = int(n) if k == 'z' else n
    return bg


def clean_bg(new, old):
    """what the browser may change about an existing picture: place, size, transparency. No picture on the server → no record."""
    if not isinstance(old, dict) or not old.get('ext'):
        return None
    out = dict(old)
    if isinstance(new, dict):
        for k, lo, hi, nd in (('x', -LIMIT, LIMIT, 1), ('y', -LIMIT, LIMIT, 1), ('w', 50, LIMIT, 1), ('h', 50, LIMIT, 1), ('op', 0.1, 1, 2)):
            n = _num(new.get(k), lo, hi, nd)
            if n is not None:
                out[k] = n
    return out


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
