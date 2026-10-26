"""Frank's mini browser: a headless Chromium on the machine where Rack Live runs.

What it is for: Frank runs commands and edits files — and sometimes he must SEE the result: what a page looks like, what a web interface answers,
whether the panel/router/VPS admin page is really up. This module opens a page in Chromium without a window, takes a screenshot, reads the title and
the visible text, and keeps the picture so the person can get it in the chat (and in Telegram).

Rules: only http and https (no file://, no javascript:, no data:), a size and time limit, one temporary profile per run (no saved cookies or logins —
the browser is anonymous, an interface behind a password shows only its login page), the last SHOTS_KEEP pictures are kept, the rest go with the answer
history. `docs` in data/frank/shots.
"""
import html
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time

BINARIES = ('chromium', 'chromium-browser', 'google-chrome', 'chrome')
SHOTS_KEEP = 40
MAX_TEXT = 6000
MAX_DOM = 4_000_000
SIZES = {'S': (390, 844), 'M': (1280, 900), 'L': (1600, 1000), 'FULL': (1280, 2400)}
BAD_SCHEME = re.compile(r'^(file|javascript|data|chrome|view-source|about):', re.I)
SHOT_NAME = re.compile(r'^(\d{10})-([0-9a-f]{8})\.png$')
FORCE = None                       # tests: prepend this argv instead of looking for a browser


class BrowserError(Exception):
    pass


def binary():
    if FORCE:
        return FORCE[0]
    return next((p for b in BINARIES for p in [shutil.which(b)] if p), None)


def where():
    b = binary()
    if not b:
        return ''
    try:
        return subprocess.run([b] + ([] if FORCE else ['--version']), capture_output=True, text=True, timeout=20).stdout.strip()[:80]
    except (OSError, subprocess.SubprocessError):
        return b


def shots_dir(data_dir):
    p = os.path.join(data_dir, 'frank', 'shots')
    os.makedirs(p, exist_ok=True)
    return p


def check_url(url):
    """→ a proper address; raises BrowserError with a reason the model can pass on"""
    u = str(url or '').strip().strip('"\'')
    if not u:
        raise BrowserError('пустой адрес')
    if BAD_SCHEME.match(u):
        raise BrowserError('открывать можно только http и https: file://, javascript: и data: запрещены')
    if '://' not in u:
        u = 'http://' + u
    if not re.match(r'^https?://', u, re.I):
        raise BrowserError('адрес должен начинаться с http:// или https://')
    if len(u) > 2000:
        raise BrowserError('слишком длинный адрес')
    return u


def shot_file(data_dir, name):
    """the picture by its name (a strict name: no paths, no «..», nothing but our own files)"""
    m = SHOT_NAME.match(str(name or ''))
    if not m:
        raise BrowserError('нет такого снимка')
    p = os.path.join(shots_dir(data_dir), m.group(0))
    return p if os.path.isfile(p) else None


def prune(data_dir):
    d = shots_dir(data_dir)
    files = sorted((os.path.join(d, f) for f in os.listdir(d) if SHOT_NAME.match(f)), key=os.path.getmtime)
    for f in files[:-SHOTS_KEEP]:
        try:
            os.remove(f)
        except OSError:
            pass


def _run(args, url, wait, timeout, profile):
    """one Chromium run; → (stdout text, stderr text)

    Chromium starts helper processes that inherit its stdout/stderr and outlive the parent for a moment. Reading a pipe would wait for all of them
    (and hang when one stays), so the output goes to real files and the whole process group is killed on a timeout."""
    base = list(FORCE) if FORCE else [binary()]
    argv = base + ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--hide-scrollbars', '--mute-audio',
                   '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--disable-background-networking',
                   '--disable-sync', '--disable-features=Translate,BackForwardCache', f'--user-data-dir={profile}',
                   f'--virtual-time-budget={wait}'] + args + [url]
    d = tempfile.mkdtemp(prefix='rl-browse-')
    fo, fe = os.path.join(d, 'out'), os.path.join(d, 'err')
    try:
        with open(fo, 'wb') as o, open(fe, 'wb') as e:
            try:
                p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=o, stderr=e, start_new_session=(os.name == 'posix'))
            except FileNotFoundError:
                raise BrowserError('в этой установке нет браузера (Chromium) — мини-браузер работает только там, где он есть')
            except OSError as ex:
                raise BrowserError(f'не удалось запустить браузер: {ex}')
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == 'posix':
                        os.killpg(os.getpgid(p.pid), 15)          # chromium's helpers go with it
                    else:
                        p.kill()
                except OSError:
                    pass
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                raise BrowserError(f'страница не открылась за {timeout} с — возможно, адрес недоступен или отвечает слишком долго')
        with open(fo, 'rb') as f1:
            out = f1.read(MAX_DOM).decode('utf-8', 'replace')
        with open(fe, 'rb') as f2:
            err = f2.read(200_000).decode('utf-8', 'replace')
        return out, err
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _text_of(dom):
    """title + readable text out of the DOM"""
    title = ''
    m = re.search(r'<title[^>]*>(.*?)</title>', dom, re.S | re.I)
    if m:
        title = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', m.group(1)))).strip()[:300]
    body = re.sub(r'<(script|style|noscript|template)[^>]*>.*?</\1>', ' ', dom, flags=re.S | re.I)
    body = re.sub(r'<br[^>]*>|</p>|</div>|</li>|</h[1-6]>', '\n', body, flags=re.I)
    body = re.sub(r'<[^>]+>', ' ', body)
    body = html.unescape(body).replace('\xa0', ' ')
    lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in body.split('\n')]
    text = '\n'.join([l for l in lines if l])
    return title, (text[:MAX_TEXT] + ('\n…(текст обрезан)' if len(text) > MAX_TEXT else ''))


def open_page(data_dir, url, size='M', text=True, wait=6000, timeout=120, full=False):
    """open the page → {'ok', 'url', 'title', 'text', 'shot', 'bytes', 'size', 'ms'}
    `shot` is the name of the picture in data/frank/shots (serve it with GET /api/ai/shot/<name>)"""
    url = check_url(url)          # the argument is checked first: a wrong address must not look like «no browser»
    if not binary():
        raise BrowserError('в этой установке нет браузера (Chromium). Он ставится в образ Docker при сборке — обновите панель')
    w, h = SIZES.get(str(size or 'M').upper(), SIZES['M'])
    if full:
        w, h = SIZES['FULL']
    name = f'{int(time.time())}-{secrets.token_hex(4)}.png'
    out = os.path.join(shots_dir(data_dir), name)
    wait = max(500, min(30000, int(wait or 6000)))
    timeout = max(10, min(300, int(timeout or 120)))
    t0 = time.time()
    with tempfile.TemporaryDirectory() as prof:
        _out, err = _run([f'--window-size={w},{h}', f'--screenshot={out}'], url, wait, timeout, prof)
    if not os.path.isfile(out) or os.path.getsize(out) < 1000:
        hint = ''
        if re.search(r'ERR_(NAME_NOT_RESOLVED|CONNECTION|ADDRESS_UNREACHABLE|TIMED_OUT|SSL)', err + _out):
            hint = ' — адрес не открылся (нет такого хоста, отказ в соединении или ошибка сертификата)'
        raise BrowserError('скриншот не получился' + hint)
    title, body = '', ''
    if text:
        try:
            with tempfile.TemporaryDirectory() as prof:
                dom, _e2 = _run(['--dump-dom'], url, wait, timeout, prof)
            title, body = _text_of(dom[:MAX_DOM])
        except BrowserError:
            title, body = '', ''
    prune(data_dir)
    return {'ok': True, 'url': url, 'title': title, 'text': body, 'shot': name, 'bytes': os.path.getsize(out),
            'size': f'{w}×{h}', 'ms': round((time.time() - t0) * 1000)}
