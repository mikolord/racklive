"""Схема дома: своя картинка-чертёж (одна на дом) + линии и зоны поверх (провода, помещения).
Хранится в cfg['plan']['buildings'][i]['scheme'] = {'bg': {'ext','v'} | None, 'shapes': [...]}.
Картинка — файл data/scheme/scheme-<id дома>.<ext>, по одной на дом (тот же приём, что у фона территории в planmap.py,
только без списка из нескольких штук — на дом нужна ровно одна)."""
import os, re
from . import planmap

MAX_SHAPES = 300
MAX_WIRE_PTS = 40
DEV_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
LIM_LO, LIM_HI = -4.0, 5.0            # поле не ограничено картинкой: фигуры можно ставить и за её краями
SHAPE_RE = re.compile(r'^[a-z0-9]{1,16}$')
ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
EXTS = ('jpg', 'png', 'webp')


def folder(data_dir):
    return os.path.join(data_dir, 'scheme')


def path_of(data_dir, bid):
    if not ID_RE.match(str(bid or '')):
        return None
    for ext in EXTS:
        f = os.path.join(folder(data_dir), f'scheme-{bid}.{ext}')
        if os.path.isfile(f):
            return f
    return None


def remove(data_dir, bid):
    if not ID_RE.match(str(bid or '')):
        return
    for ext in EXTS:
        try:
            os.remove(os.path.join(folder(data_dir), f'scheme-{bid}.{ext}'))
        except OSError:
            pass


def save(data_dir, bid, raw):
    """→ (ext, ошибка)"""
    if not ID_RE.match(str(bid or '')):
        return None, 'неверный дом'
    if not raw or len(raw) > planmap.MAX_BYTES:
        return None, 'картинка пустая или больше 3 МБ'
    ext = planmap.kind_of(raw)
    if not ext:
        return None, 'нужна картинка JPEG, PNG или WebP'
    os.makedirs(folder(data_dir), exist_ok=True)
    remove(data_dir, bid)
    tmp = os.path.join(folder(data_dir), f'scheme-{bid}.tmp')
    with open(tmp, 'wb') as f:
        f.write(raw)
    os.replace(tmp, os.path.join(folder(data_dir), f'scheme-{bid}.{ext}'))
    return ext, ''


COLORS = ('blue', 'green', 'red', 'orange', 'purple', 'teal')


def _coord(v):
    """0..1 — доля от картинки (не пиксели): переживает замену фото на другой по размеру"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):  # nan / inf
        return None
    return round(max(LIM_LO, min(LIM_HI, v)), 5)


def clean_shapes(new):
    """браузер → проверенный список {id, kind: line|rect|wire, [pts], x1,y1,x2,y2, color, label}"""
    if new is None:
        return []
    if not isinstance(new, list):
        raise ValueError('неверные данные схемы')
    if len(new) > MAX_SHAPES:
        raise ValueError(f'слишком много линий и зон (максимум {MAX_SHAPES})')
    out, seen = [], set()
    for s in new:
        if not isinstance(s, dict):
            raise ValueError('неверная фигура')
        sid = str(s.get('id') or '')
        if not ID_RE.match(sid) or sid in seen:
            raise ValueError('неверный номер фигуры')
        seen.add(sid)
        if s.get('kind') not in ('line', 'rect', 'wire', 'text', 'node'):
            raise ValueError('тип фигуры: line, rect, wire, text или node')
        pts = None
        if s['kind'] == 'wire':          # провод А→Б: ломаная с прямыми углами, 2..MAX_WIRE_PTS точек
            raw = s.get('pts')
            if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_WIRE_PTS:
                raise ValueError('провод: от 2 до %d точек' % MAX_WIRE_PTS)
            pts = []
            for p in raw:
                if not isinstance(p, (list, tuple)) or len(p) != 2:
                    raise ValueError('точка провода — пара чисел')
                px, py = _coord(p[0]), _coord(p[1])
                if px is None or py is None:
                    raise ValueError('координаты должны быть числами от 0 до 1')
                pts.append([px, py])
            coords = {'x1': pts[0][0], 'y1': pts[0][1], 'x2': pts[-1][0], 'y2': pts[-1][1]}
        elif s['kind'] == 'text':        # надпись на схеме: одна точка, сам текст — в label
            x, y = _coord(s.get('x1')), _coord(s.get('y1'))
            coords = {'x1': x, 'y1': y, 'x2': x, 'y2': y}
        else:
            coords = {k: _coord(s.get(k)) for k in ('x1', 'y1', 'x2', 'y2')}
        if None in coords.values():
            raise ValueError('координаты должны быть числами от 0 до 1')
        color = str(s.get('color') or 'blue').lower()
        if color not in COLORS:
            color = 'blue'
        item = {'id': sid, 'kind': s['kind'], **coords, 'color': color, 'label': str(s.get('label') or '').strip()[:120 if s['kind'] == 'text' else 60]}
        if s['kind'] == 'node':            # готовый объект из набора: блок, роутер, дверь… (рисует интерфейс по имени)
            sh = str(s.get('shape') or 'block').lower()
            item['shape'] = sh if SHAPE_RE.match(sh) else 'block'
        if s['kind'] in ('rect', 'node', 'text'):   # разворот в градусах (-180..180]
            try:
                rot = float(s.get('rot') or 0)
            except (TypeError, ValueError):
                rot = 0.0
            if rot == rot and abs(rot) != float('inf'):
                rot = round(((rot + 180) % 360) - 180, 1)
                if rot:
                    item['rot'] = rot
        if s['kind'] == 'text' and not item['label']:
            continue                       # пустая надпись не нужна
        for k in ('w', 'fs'):              # толщина и размер текста: 1..3, по умолчанию 1
            try:
                v = int(s.get(k) or 1)
            except (TypeError, ValueError):
                v = 1
            if v in (2, 3):
                item[k] = v
        for k in ('dash', 'anim', 'lock'):     # пунктир, бегущий пунктир, замок (не двигается)
            if s.get(k) is True:
                item[k] = True
        if s['kind'] in ('line', 'wire'):
            try:
                ar = int(s.get('arrow') or 0)       # 0 нет, 1 на конце, 2 с обоих концов (True из старых схем = 1)
            except (TypeError, ValueError):
                ar = 0
            if ar in (1, 2):
                item['arrow'] = ar
            if s['kind'] == 'line' and s.get('curve') is True:
                item['curve'] = True
            if s['kind'] == 'wire':
                for k in ('closed', 'free'):        # замкнутый многоугольник; ломаная «по точкам» (не пересчитывается)
                    if s.get(k) is True:
                        item[k] = True
                fr, to = str(s.get('from') or ''), str(s.get('to') or '')
                if ID_RE.match(fr) and ID_RE.match(to):   # провод «узел → узел»: тянется за объектами
                    item['from'], item['to'] = fr, to
        if s['kind'] == 'node' and DEV_RE.match(str(s.get('dev') or '')):   # объект связан с устройством Rack Live
            item['dev'] = str(s['dev'])
        if pts:
            item['pts'] = pts
        out.append(item)
    return out
