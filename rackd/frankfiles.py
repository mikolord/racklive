"""Frank: files and photos attached to a question, and his memory — FRANK.md (like CLAUDE.md: the person's rules and notes, read in every chat).
Files live in data/frank/files/<id>.<ext> with <id>.json beside (name, kind, type, size); the chat message keeps only that description.
The type is decided by the first bytes, never by the name: a picture (PNG, JPEG, WebP, GIF) goes to the model as a picture, text (UTF-8 without
zero bytes) is read into the question, anything else is kept and named (the model can't open it yet)."""
import base64
import json
import os
import re
import secrets
import time

MAX_IMAGE = 8_000_000
MAX_TEXT = 1_000_000
MAX_OTHER = 25_000_000
TEXT_TO_MODEL = 60_000          # characters of one text file that go into the question
MEMORY_MAX = 20_000             # characters of FRANK.md


def folder(data_dir):
    return os.path.join(data_dir, 'frank', 'files')


def kind_of(data):
    """→ (kind, mime, ext): image | text | pdf | other"""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image', 'image/png', 'png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image', 'image/jpeg', 'jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image', 'image/webp', 'webp'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image', 'image/gif', 'gif'
    if data[:5] == b'%PDF-':
        return 'pdf', 'application/pdf', 'pdf'
    if b'\x00' not in data[:65536]:
        try:
            data[:200_000].decode('utf-8')
            return 'text', 'text/plain', 'txt'
        except UnicodeDecodeError as e:
            if e.start > 199_990:                           # cut in the middle of a letter at the edge of the sample
                return 'text', 'text/plain', 'txt'
    return 'other', 'application/octet-stream', 'bin'


def save(data_dir, name, data):
    """→ (meta, error)"""
    if not data:
        return None, 'файл пустой'
    kind, mime, ext = kind_of(data)
    limit = {'image': MAX_IMAGE, 'text': MAX_TEXT}.get(kind, MAX_OTHER)
    if len(data) > limit:
        return None, f'файл больше {limit // 1_000_000} МБ'
    name = re.sub(r'[\x00-\x1f/\\]+', '_', (name or '').strip())[:120] or ('фото.' + ext if kind == 'image' else 'файл')
    fid = secrets.token_hex(8)
    os.makedirs(folder(data_dir), exist_ok=True)
    with open(os.path.join(folder(data_dir), f'{fid}.{ext}'), 'wb') as f:
        f.write(data)
    meta = {'id': fid, 'name': name, 'kind': kind, 'mime': mime, 'ext': ext, 'size': len(data), 't': int(time.time())}
    with open(os.path.join(folder(data_dir), f'{fid}.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False)
    return meta, ''


def meta(data_dir, fid):
    if not re.match(r'^[0-9a-f]{16}$', str(fid or '')):
        return None
    try:
        with open(os.path.join(folder(data_dir), f'{fid}.json'), encoding='utf-8') as f:
            m = json.load(f)
        return m if os.path.isfile(path(data_dir, m)) else None
    except (OSError, ValueError):
        return None


def path(data_dir, m):
    return os.path.join(folder(data_dir), f"{m['id']}.{m['ext']}")


def read_text(data_dir, m, limit=TEXT_TO_MODEL):
    try:
        with open(path(data_dir, m), 'rb') as f:
            t = f.read(limit * 4).decode('utf-8', 'replace')
    except OSError:
        return ''
    return t[:limit] + ('\n…(дальше обрезано)' if len(t) > limit else '')


def b64(data_dir, m):
    try:
        with open(path(data_dir, m), 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return ''


def remove(data_dir, fids):
    for fid in fids or []:
        if re.match(r'^[0-9a-f]{16}$', str(fid)):
            for f in os.listdir(folder(data_dir)) if os.path.isdir(folder(data_dir)) else []:
                if f.startswith(fid + '.'):
                    try:
                        os.remove(os.path.join(folder(data_dir), f))
                    except OSError:
                        pass


def prune(data_dir, used, older=86400):
    """files uploaded but never sent (the person changed their mind) — gone after a day"""
    d = folder(data_dir)
    if not os.path.isdir(d):
        return
    now = time.time()
    for f in os.listdir(d):
        fid = f.split('.', 1)[0]
        if fid not in used:
            try:
                if now - os.path.getmtime(os.path.join(d, f)) > older:
                    os.remove(os.path.join(d, f))
            except OSError:
                pass


# ── FRANK.md: the memory ──
def memory_path(data_dir):
    return os.path.join(data_dir, 'frank', 'FRANK.md')


def memory_get(data_dir):
    try:
        with open(memory_path(data_dir), encoding='utf-8') as f:
            return f.read()[:MEMORY_MAX]
    except OSError:
        return ''


def memory_set(data_dir, text):
    text = str(text or '').replace('\r\n', '\n')
    if len(text) > MEMORY_MAX:
        raise ValueError(f'память длиннее {MEMORY_MAX} символов — сократите её')
    os.makedirs(os.path.dirname(memory_path(data_dir)), exist_ok=True)
    tmp = memory_path(data_dir) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, memory_path(data_dir))
    return text


def memory_add(data_dir, line):
    """one more point at the end (what Frank was asked to remember)"""
    line = re.sub(r'\s+', ' ', str(line or '')).strip()[:1000]
    if not line:
        raise ValueError('пустая запись')
    cur = memory_get(data_dir).rstrip()
    return memory_set(data_dir, (cur + '\n' if cur else '') + '- ' + line + '\n')
