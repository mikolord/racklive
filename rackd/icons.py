"""Icons of devices on the map. Two parts, both plain data:
  - the library of uploaded pictures: data/icons/<id>.<svg|png|webp>, the list is cfg['iconLib'] = [{id, name, ext}]
  - the choice per node: cfg['icons'] = {<map node id>: 'std:<name>' | 'up:<id>'}; node id = 'd:<device>' for a device, 'h:<mac>' for a client,
    'c:<device>:<key>' for an access point of a mesh. No choice = the icon of the device kind (as before).
An uploaded picture is only ever shown through <img> / <image> (scripts never run there); on top of that it is checked here and served with a sandbox policy."""
import os
import re
import secrets

MAX_BYTES = 100_000
MAX_LIB = 200
STD_RE = re.compile(r'^[a-z0-9]{1,24}$')
_SVG_BAD = re.compile(r'<\s*(script|foreignobject|iframe|object|embed|audio|video|link|meta|style\b[^>]*@import)|<!entity|\son[a-z]+\s*=|javascript:|data:text/html', re.I)
_SVG_HREF = re.compile(r'''(?:xlink:)?href\s*=\s*["']?\s*([^"'\s>]+)''', re.I)
_SVG_URL = re.compile(r'url\(\s*["\']?\s*(?!#)', re.I)


def folder(data_dir):
    return os.path.join(data_dir, 'icons')


def kind_of(data):
    """file type by its first bytes (the name and Content-Type are not trusted)"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    head = data[:2048].lstrip(b'\xef\xbb\xbf \t\r\n').lower()
    if head.startswith(b'<?xml') or head.startswith(b'<svg') or head.startswith(b'<!--') or head.startswith(b'<!doctype svg'):
        return 'svg' if b'<svg' in data[:4096].lower() else None
    return None


def check_svg(data):
    """returns an error text or ''"""
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return 'SVG должен быть в кодировке UTF-8'
    if _SVG_BAD.search(text):
        return 'в SVG есть скрипты, стили-импорты или внешние вставки — такие файлы не принимаются'
    for m in _SVG_HREF.finditer(text):
        if not m.group(1).startswith('#'):
            return 'в SVG есть ссылки наружу — оставьте только саму картинку'
    if _SVG_URL.search(text):
        return 'в SVG есть внешние ссылки url(...)'
    return ''


def add(cfg, data_dir, name, data):
    """store one picture; returns (entry, error)"""
    if not data or len(data) > MAX_BYTES:
        return None, 'файл пустой или больше 100 КБ'
    ext = kind_of(data)
    if not ext:
        return None, 'нужен SVG, PNG или WebP'
    if ext == 'svg':
        err = check_svg(data)
        if err:
            return None, err
    lib = cfg.setdefault('iconLib', [])
    if len(lib) >= MAX_LIB:
        return None, 'слишком много своих иконок — удалите ненужные'
    iid = secrets.token_hex(4)
    name = re.sub(r'\.(svg|png|webp)$', '', (name or '').strip(), flags=re.I)[:40] or 'Иконка'
    os.makedirs(folder(data_dir), exist_ok=True)
    with open(os.path.join(folder(data_dir), f'{iid}.{ext}'), 'wb') as f:
        f.write(data)
    entry = {'id': iid, 'name': name, 'ext': ext}
    lib.append(entry)
    return entry, ''


def path_of(cfg, data_dir, iid):
    e = next((x for x in cfg.get('iconLib') or [] if x.get('id') == iid), None)
    if not e:
        return None, None
    f = os.path.join(folder(data_dir), f"{e['id']}.{e['ext']}")
    return (f, e['ext']) if os.path.isfile(f) else (None, None)


def remove(cfg, data_dir, iid):
    e = next((x for x in cfg.get('iconLib') or [] if x.get('id') == iid), None)
    if not e:
        return False
    cfg['iconLib'] = [x for x in cfg['iconLib'] if x is not e]
    try:
        os.remove(os.path.join(folder(data_dir), f"{e['id']}.{e['ext']}"))
    except OSError:
        pass
    ch = cfg.get('icons') or {}
    for k in [k for k, v in ch.items() if v == 'up:' + iid]:
        del ch[k]                                           # nodes that used it go back to the icon of their kind
    return True


def choose(cfg, key, icon):
    """set (or clear, icon = '') the icon of one map node; returns an error text or ''"""
    key = str(key or '')
    if not re.match(r'^[A-Za-z0-9:_.\-]{2,80}$', key):
        return 'неверный адрес узла'
    ch = cfg.setdefault('icons', {})
    if not icon:
        ch.pop(key, None)
        return ''
    icon = str(icon)
    if icon.startswith('std:'):
        if not STD_RE.match(icon[4:]):
            return 'неверное имя иконки'
    elif icon.startswith('up:'):
        if not any(x.get('id') == icon[3:] for x in cfg.get('iconLib') or []):
            return 'такой иконки нет в библиотеке'
    else:
        return 'неверная иконка'
    ch[key] = icon
    if len(ch) > 3000:
        return 'слишком много назначенных иконок'
    return ''
