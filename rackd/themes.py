"""Custom looks («оформления»): the administrator uploads a .zip, Rack Live checks it, stores it and any device can switch to it
(Настройки → Оформление → «Добавить своё»).

A look is DATA, never a program: theme.json (colours, texts, icons, tour texts) + optional theme.css + pictures. No JavaScript is ever run.
What keeps it safe and keeps updates from breaking it:
  * every upload is checked (structure, sizes, file types, CSS scope, no outside links, no scripts in pictures) — see check() below;
  * CSS must be scoped to its own look (html[data-theme-id="<id>"] …), so it cannot leak into anything else;
  * THEME_API is the version of the contract (the variables, the stable class names, the text keys, the icon names). When an update changes the
    contract incompatibly THEME_API goes up, and every installed look is re-checked at start: a look that no longer fits is switched off by itself and
    the interface falls back to the built-in look (the person is told why);
  * unknown keys are only warnings (they are ignored), so a look made for an older version keeps working as long as the contract holds.
The text of the contract (what may be changed) is built from the app itself: web/theme-defaults.json (written by build.py) + the lists below."""
import hashlib, io, json, os, re, shutil, struct, threading, time, zipfile

THEME_API = 1
MAX_ZIP = 8 * 1024 * 1024
MAX_UNPACKED = 16 * 1024 * 1024
MAX_FILES = 200
MAX_FILE = 3 * 1024 * 1024
MAX_CSS = 400 * 1024
EXT = {'.json', '.css', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.woff2', '.txt', '.md'}
RESERVED = {'classic', 'graphite', 'none', 'default', 'custom', 'auto', 'light', 'dark', 'system'}
ID_RE = re.compile(r'^[a-z][a-z0-9-]{2,31}$')
APP_ICON_SLOTS = ('rack', 'frank', 'speed')

# CSS variables a look may set (everything else the app colours with is derived from these or reachable by theme.css)
TOKENS = {
    '--bg': 'фон страницы', '--bg2': 'фон полей ввода и вложенных блоков', '--card': 'фон карточки', '--card-solid': 'сплошной фон карточки (плитки, виджеты)',
    '--elev': 'фон окон и шторок', '--text': 'основной текст', '--text2': 'второстепенный текст', '--text3': 'приглушённый текст',
    '--line': 'тонкая линия', '--line2': 'линия поярче (рамки полей)', '--fill': 'заливка кнопок, чипов, вложенных плиток', '--fill2': 'заливка поярче',
    '--accent': 'акцентный цвет (кнопки, выбранное, переключатели)', '--green': 'цвет «в сети»', '--yellow': 'цвет предупреждения (жёлтый)', '--orange': 'оранжевый',
    '--red': 'цвет ошибки и «нет связи»', '--purple': 'фиолетовый', '--teal': 'бирюзовый', '--indigo': 'индиго',
    '--shadow': 'тень карточек', '--shadow-lg': 'тень окон', '--r': 'скругление кнопок и полей (например 14px)', '--r-lg': 'скругление карточек (например 20px)',
    '--font': 'шрифт интерфейса (список, как в CSS)', '--mono': 'моноширинный шрифт',
    '--dock': 'фон верхней панели и нижнего дока', '--glass': 'стекло Frank и меню', '--glass-line': 'линия стекла', '--dock-glass': 'фон дока ввода Frank и меню «⋯»', '--fr-btn': 'круглые кнопки Frank',
    '--rack': 'шкаф: корпус', '--unit': 'юнит в шкафу: фон (запасной)', '--unit-text': 'юнит: текст',
    '--rack-bg': 'шкаф: фон корпуса (можно градиент)', '--rack-body': 'шкаф: внутренняя область', '--rack-text': 'шкаф: заголовок', '--rack-meta': 'шкаф: подпись',
    '--rack-rail': 'шкаф: цифры на направляющих', '--rack-hole': 'шкаф: отверстия направляющих', '--rack-slot': 'шкаф: линии между юнитами', '--rack-icon': 'шкаф: цвет значков',
    '--rack-seg-bg': 'шкаф: переключатель «Фронт / Тыл» — фон', '--rack-seg-text': 'переключатель — текст', '--rack-seg-on': 'переключатель — выбранное', '--rack-seg-on-text': 'переключатель — текст выбранного',
    '--unit-bg': 'юнит: фон (можно градиент)', '--unit-meta': 'юнит: подпись', '--unit-icon-bg': 'юнит: подложка значка', '--unit-shadow': 'юнит: тень и блик',
    '--unit-passive': 'пассивный юнит (патч-панель): узор', '--unit-blank': 'заглушка',
    '--led-off': 'светодиод порта: нет линка', '--led-dead': 'светодиод: порт с проблемой',
    '--faceplate-bg': 'ПАНЕЛЬ ПОРТОВ: подложка (по умолчанию тёмная; можно градиент)', '--faceplate-radius': 'панель портов: скругление подложки',
    '--port-bg': 'порт без линка: фон', '--port-border': 'порт без линка: рамка', '--port-text': 'порт: цвет номера', '--port-radius': 'порт: скругление (например 6px или 50%)',
    '--port-w': 'порт: ширина (38px)', '--port-h': 'порт: высота (34px)', '--port-sfp-w': 'порт SFP: ширина (44px)', '--port-sfp-radius': 'порт SFP: скругление',
    '--port-base': 'порт с линком: тёмная основа, с которой смешивается цвет скорости', '--port-g': 'порт 1 Гбит и выше: цвет', '--port-y': 'порт 100 Мбит: цвет', '--port-o': 'порт 10 Мбит: цвет',
    '--port-link-text': 'порт с линком: цвет номера', '--port-dis': 'порт отключён/ошибка: рамка', '--port-dis-bg': 'порт отключён: фон', '--port-wan': 'порт WAN: рамка',
    '--port-sel': 'выбранный порт: обводка', '--poe-badge': 'значок PoE на порту: цвет',
    '--hint-bg': 'ПОДСКАЗКА: фон', '--hint-line': 'подсказка: рамка', '--hint-text': 'подсказка: текст', '--hint-ico': 'подсказка: цвет лампочки', '--hint-ico-bg': 'подсказка: подложка лампочки',
    '--hint-close-bg': 'подсказка: кнопка «Понятно» — фон', '--hint-close-text': 'подсказка: кнопка «Понятно» — текст', '--hint-radius': 'подсказка: скругление',
    '--frank-bg': 'FRANK: плитка за глазом', '--frank-sclera': 'Frank: белок глаза', '--frank-pupil': 'Frank: зрачок', '--frank-lid': 'Frank: веко',
    '--frank-iris-0': 'Frank: радужка, светлый край', '--frank-iris-1': 'Frank: радужка, основной цвет', '--frank-iris-2': 'Frank: радужка, тёмный край', '--frank-glow': 'Frank в обучении: цвет сияния',
    '--frank-m2-0': 'Frank «напряжён» (долгий запрос): светлый', '--frank-m2-1': 'Frank «напряжён»: основной', '--frank-m2-2': 'Frank «напряжён»: тёмный',
    '--frank-m3-0': 'Frank «тревога» (очень долго): светлый', '--frank-m3-1': 'Frank «тревога»: основной', '--frank-m3-2': 'Frank «тревога»: тёмный',
    '--map-rack-frame': 'карта: рамка шкафа', '--map-rack-stroke': 'карта: контур шкафа', '--map-unit': 'карта: юнит и устройство', '--map-unit-stroke': 'карта: контур юнита',
}
# class names that are promised to stay (a look may style them); other classes work too but earn a warning: an update may rename them
HOOKS = set('''app-bg topbar brand brand-title brand-text live tabs tab tab-label count hdr-tools hdr-more bottombar page page-title page-sub card card-title btn primary danger ghost sm icon
chip on badge online offline warning seg switch input select textarea modal modal-head modal-body overlay sheet toast list li empty stat stats state-tile tile hint-box hint-close ev dot
wg wg-in wg-body wg-tile wg-tile-ic wg-tile-name wg-tile-art wg-tile-big wg-tile-v wg-tile-s size-S size-M size-L dash mini-svg gauge gauge-val gauge-bar dev-card cards grid
set-layout set-nav set-item set-ic ios-group ios-cell ios-label ios-val ios-list auth look-skin look-prev ai-panel ai-head ai-bubble ai-msg ai-list ai-foot user assistant err frank frank-btn
fr-top fr-title fr-circle fr-dock fr-send fr-dbtn fr-model tour-layer tour-dim tour-ring tour-bubble tour-title tour-text tour-next tour-link tour-skip tour-dots tour-hint tour-card tour-block
faceplate ports port sel g y o dis sfp wan poe vl legend hint-ico frank-img frank-eye frank-iris frank-pupil frank-lid frank-brow frank-body s0 s1 s2 m0 m1 m2 m3 busy tour-frank tf-bob
hdr-menu hdr-tiles hdr-row advice advice-t advice-ic sys-log link-btn found-type netscan-row mono dim dim3 row col grow wrap center between ellipsis app-ic-c app-ic-g'''.split())

_KIND_FALLBACK = ['router', 'switch', 'server', 'nas', 'ap', 'camera', 'nvr', 'phone', 'tablet', 'tv', 'laptop', 'pc', 'printer', 'speaker', 'iot', 'internet', 'web', 'ups', 'patch', 'cross', 'pdu', 'modem', 'other']
COLOR_RE = re.compile(r'^(#[0-9a-fA-F]{3,8}|(rgb|rgba|hsl|hsla|oklch|color-mix)\([#\w\s%.,()/+\-]*\)|[a-zA-Z]{3,20})$')
TOKEN_VALUE_RE = re.compile(r'^[#\w\s%.,()/\'"+\-*:!]{1,240}$')
PATH_RE = re.compile(r'^[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s\-]{2,2500}$')
BAD_CSS = re.compile(r'@import|expression\s*\(|javascript\s*:|vbscript\s*:|behavior\s*:|-moz-binding|<\s*/?\s*(script|style)|@charset|@namespace|@page|@container', re.I)
BAD_SVG = re.compile(r'<\s*script|javascript\s*:|\bon\w+\s*=|<\s*foreignObject|<\s*iframe|<\s*embed|<\s*object|<\s*audio|<\s*video|<!ENTITY|xlink:href\s*=\s*["\'](?!#)|href\s*=\s*["\']\s*(https?:|//|data:text)', re.I)


def vtuple(v):
    return tuple(int(x) for x in (re.findall(r'\d+', str(v)) + ['0', '0', '0'])[:3])


def png_size(b):
    return struct.unpack('>II', b[16:24]) if b[:8] == b'\x89PNG\r\n\x1a\n' and len(b) > 24 else None


def _split_top(text, sep=','):
    out, depth, q, cur = [], 0, '', ''
    for ch in text:
        if q:
            cur += ch
            if ch == q:
                q = ''
            continue
        if ch in '"\'':
            q = ch
        elif ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        elif ch == sep and depth == 0:
            out.append(cur); cur = ''
            continue
        cur += ch
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def _blocks(css):
    """[(prelude, body | None)] on one level; braces inside strings are ignored"""
    out, i, n = [], 0, len(css)
    while i < n:
        j, q = i, ''
        while j < n:
            c = css[j]
            if q:
                if c == q:
                    q = ''
            elif c in '"\'':
                q = c
            elif c in '{;':
                break
            j += 1
        prelude = css[i:j].strip()
        if j >= n:
            if prelude:
                out.append((prelude, None))
            break
        if css[j] == ';':
            if prelude:
                out.append((prelude, None))
            i = j + 1
            continue
        depth, k, q = 1, j + 1, ''
        while k < n and depth:
            c = css[k]
            if q:
                if c == q:
                    q = ''
            elif c in '"\'':
                q = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            k += 1
        out.append((prelude, css[j + 1:k - 1]))
        i = k
    return out


def check_css(css, tid, assets):
    """→ (errors, warnings, compiled css): every rule scoped to this look, no outside links, no scripts"""
    errors, warnings = [], []
    if len(css.encode()) > MAX_CSS:
        return ['theme.css слишком большой (не больше %d КБ)' % (MAX_CSS // 1024)], [], ''
    plain = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    m = BAD_CSS.search(plain)
    if m:
        errors.append(f'в CSS есть запрещённое: «{m.group(0)}»')
    if re.search(r'\\', re.sub(r'(["\']).*?\1', '', plain)):
        errors.append('в CSS нельзя использовать экранирование «\\» вне кавычек')
    for u in re.findall(r'url\(\s*([^)]*)\)', plain, flags=re.I):
        u = u.strip().strip('"\'')
        if u.startswith('data:image/') and re.match(r'data:image/(png|jpeg|webp|svg\+xml)[;,]', u):
            continue
        if not re.match(r'^assets/[\w.\-]+$', u) or u not in assets:
            errors.append(f'url({u[:50]}): разрешены только файлы из папки assets/ этой темы (и data:image) — внешние ссылки запрещены')
    sel_re = re.compile(r'^(html)?\[data-theme-id=("|\')' + re.escape(tid) + r'\2\]')
    classes = set()

    def walk(text, depth=0):
        for prelude, body in _blocks(text):
            low = prelude.lower()
            if prelude.startswith('@'):
                name = re.match(r'@([\w-]+)', low).group(1) if re.match(r'@([\w-]+)', low) else ''
                if body is None:
                    errors.append(f'правило @{name} не поддерживается')
                elif name in ('media', 'supports') and depth < 3:
                    walk(body, depth + 1)
                elif name in ('keyframes', '-webkit-keyframes'):
                    if not re.match(r'@[\w-]*keyframes\s+' + re.escape(tid) + r'-[\w-]+$', prelude):
                        warnings.append(f'анимацию лучше назвать «{tid}-имя»: «{prelude[:40]}»')
                elif name == 'font-face':
                    if not re.search(r'url\(\s*["\']?assets/[\w.\-]+\.woff2["\']?\s*\)', body):
                        errors.append('@font-face: шрифт должен быть файлом .woff2 из папки assets/')
                else:
                    errors.append(f'правило @{name} не поддерживается')
                continue
            if body is None:
                continue
            for sel in _split_top(prelude):
                if not sel_re.match(sel):
                    errors.append(f'селектор «{sel[:60]}» должен начинаться с html[data-theme-id="{tid}"] — иначе тема повлияет на всё приложение')
                for c in re.findall(r'\.([A-Za-z_][\w-]*)', re.sub(r'(["\']).*?\1', '', sel)):
                    classes.add(c)
    walk(plain)
    unknown = sorted(c for c in classes if c not in HOOKS)
    if unknown:
        warnings.append('классы вне списка стабильных (при обновлении Rack Live могут измениться, тогда этот кусок темы перестанет действовать): ' + ', '.join('.' + c for c in unknown[:12]) + ('…' if len(unknown) > 12 else ''))
    out = re.sub(r'url\(\s*["\']?(assets/[\w.\-]+)["\']?\s*\)', lambda m: f'url("/themes/{tid}/{m.group(1)}")', plain)
    return errors, warnings, out


class Themes:
    def __init__(self, data_dir, web_dir, version):
        self.dir = os.path.join(data_dir, 'themes')
        self.web, self.version = web_dir, version
        self.lock = threading.RLock()
        os.makedirs(self.dir, exist_ok=True)
        self.status = self._load('status.json', {})
        self.rev = 0
        self._defaults = None

    # ── the contract, as the app itself reports it ──
    def defaults(self):
        if self._defaults is None:
            try:
                with open(os.path.join(self.web, 'theme-defaults.json'), encoding='utf-8') as f:
                    d = json.load(f)
            except (OSError, ValueError):
                d = {}
            d.setdefault('icons', []); d.setdefault('strings', {}); d.setdefault('tourSteps', []); d.setdefault('kinds', _KIND_FALLBACK)
            self._defaults = d
        return self._defaults

    def _load(self, name, default):
        try:
            with open(os.path.join(self.dir, name), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save_status(self):
        with open(os.path.join(self.dir, 'status.json'), 'w', encoding='utf-8') as f:
            json.dump(self.status, f, ensure_ascii=False)
        self.rev += 1

    # ── checking ──
    def check(self, files, manifest=None):
        """files: {relative path: bytes} → (errors, warnings, manifest, compiled css); the same checks run on upload and on every start"""
        errors, warnings = [], []
        d = self.defaults()
        try:
            m = manifest if manifest is not None else json.loads(files['theme.json'].decode('utf-8-sig'))
        except KeyError:
            return ['в архиве нет файла theme.json'], [], None, ''
        except ValueError as e:
            return [f'theme.json не читается: {e}'], [], None, ''
        if not isinstance(m, dict):
            return ['theme.json должен быть объектом {…}'], [], None, ''
        tid = m.get('id')
        if not isinstance(tid, str) or not ID_RE.match(tid):
            errors.append('id: латиницей, строчными, цифры и дефис, 3–32 символа, начинается с буквы (например «ocean-night»)')
            tid = 'invalid'
        elif tid in RESERVED:
            errors.append(f'id «{tid}» зарезервирован, выберите другой')
        for k, mx in (('name', 40), ('author', 60), ('description', 300)):
            v = m.get(k)
            if k == 'name' and not (isinstance(v, str) and v.strip()):
                errors.append('name: нужно название темы')
            elif v is not None and (not isinstance(v, str) or len(v) > mx):
                errors.append(f'{k}: текст не длиннее {mx} символов')
        if not re.match(r'^\d+(\.\d+){0,2}([-+][\w.]+)?$', str(m.get('version', ''))):
            errors.append('version: номер версии темы, например 1.0.0')
        api = m.get('api')
        if api != THEME_API:
            errors.append(f'api: тема сделана для версии оформления {api!r}, эта версия Rack Live поддерживает {THEME_API}. Обновите тему по актуальной инструкции')
        mv = m.get('minVersion')
        if mv is not None and vtuple(mv) > vtuple(self.version):
            errors.append(f'minVersion: тема требует Rack Live {mv} или новее, установлен {self.version}')
        if m.get('base', 'classic') not in ('classic', 'graphite'):
            errors.append('base: «classic» или «graphite» — оформление, на которое тема накладывается')
        # tokens
        tokens = m.get('tokens') or {}
        if not isinstance(tokens, dict) or any(k not in ('all', 'dark', 'light') for k in tokens):
            errors.append('tokens: объект с ключами all / dark / light')
            tokens = {}
        for grp, vals in tokens.items():
            if not isinstance(vals, dict):
                errors.append(f'tokens.{grp}: объект {{"--accent": "#0a84ff", …}}')
                continue
            for k, v in vals.items():
                if k not in TOKENS:
                    warnings.append(f'tokens.{grp}.{k}: неизвестная переменная (игнорируется)')
                elif not isinstance(v, str) or not TOKEN_VALUE_RE.match(v) or re.search(r'url\s*\(|expression|javascript', v, re.I):
                    errors.append(f'tokens.{grp}.{k}: недопустимое значение «{str(v)[:40]}»')
        # texts
        strings = m.get('strings') or {}
        if not isinstance(strings, dict):
            errors.append('strings: объект {"ключ": "текст"}')
            strings = {}
        for k, v in strings.items():
            if k not in d['strings']:
                warnings.append(f'strings.{k}: такого текста в приложении нет (игнорируется)')
            elif not isinstance(v, str) or len(v) > 400:
                errors.append(f'strings.{k}: текст не длиннее 400 символов')
        # icons (path data, 24×24)
        icons = m.get('icons') or {}
        if not isinstance(icons, dict):
            errors.append('icons: объект {"имя": "M… путь SVG"}')
            icons = {}
        for k, v in icons.items():
            if d['icons'] and k not in d['icons']:
                warnings.append(f'icons.{k}: такой иконки нет (игнорируется)')
            if not isinstance(v, str) or not PATH_RE.match(v):
                errors.append(f'icons.{k}: ожидается путь SVG (команды M L H V C S Q T A Z и числа), сетка 24×24')
        kc = m.get('kindColors') or {}
        if not isinstance(kc, dict):
            errors.append('kindColors: объект {"router": "#0a84ff", …}')
            kc = {}
        for k, v in kc.items():
            if k not in d['kinds']:
                warnings.append(f'kindColors.{k}: такого типа устройства нет (игнорируется)')
            if not isinstance(v, str) or not COLOR_RE.match(v):
                errors.append(f'kindColors.{k}: нужен цвет (#rrggbb)')
        # files
        assets = {p for p in files if p.startswith('assets/')}

        def pic(rel, what, kinds=('svg', 'png', 'jpg', 'jpeg', 'webp')):
            if not isinstance(rel, str) or rel not in files:
                errors.append(f'{what}: файл «{rel}» не найден в архиве')
                return None
            ext = rel.rsplit('.', 1)[-1].lower()
            if ext not in kinds:
                errors.append(f'{what}: допустимы {", ".join(kinds)}')
                return None
            b = files[rel]
            if ext == 'svg':
                try:
                    s = b.decode('utf-8')
                except UnicodeDecodeError:
                    errors.append(f'{what}: SVG должен быть в UTF-8')
                    return None
                if BAD_SVG.search(s):
                    errors.append(f'{what}: в SVG есть скрипты или внешние ссылки — это запрещено')
                if len(b) > 300 * 1024:
                    errors.append(f'{what}: SVG больше 300 КБ')
            elif ext == 'png' and b[:4] != b'\x89PNG' or ext in ('jpg', 'jpeg') and b[:3] != b'\xff\xd8\xff' or ext == 'webp' and not (b[:4] == b'RIFF' and b[8:12] == b'WEBP'):
                errors.append(f'{what}: файл не похож на {ext.upper()}')
            elif len(b) > 1024 * 1024:
                errors.append(f'{what}: картинка больше 1 МБ')
            return b
        ai = m.get('appIcons') or {}
        if not isinstance(ai, dict):
            errors.append('appIcons: объект {"rack": "assets/rack.svg", …}')
            ai = {}
        for k, rel in ai.items():
            if k not in APP_ICON_SLOTS:
                warnings.append(f'appIcons.{k}: есть только {", ".join(APP_ICON_SLOTS)} (игнорируется)')
            else:
                pic(rel, f'appIcons.{k}')
        if m.get('frankAvatar') is not None:
            pic(m['frankAvatar'], 'frankAvatar')
        pwa = m.get('pwa') or {}
        if not isinstance(pwa, dict):
            errors.append('pwa: объект {"favicon": …, "appleTouch": …, "icon192": …, "icon512": …}')
            pwa = {}
        for k in pwa:
            if k not in ('favicon', 'appleTouch', 'icon192', 'icon512'):
                warnings.append(f'pwa.{k}: неизвестный ключ (игнорируется)')
        for k, rel in pwa.items():
            if k in ('favicon', 'appleTouch', 'icon192', 'icon512'):
                b = pic(rel, f'pwa.{k}', ('svg', 'png') if k == 'favicon' else ('png',))
                if b and k != 'favicon':
                    want = {'appleTouch': 180, 'icon192': 192, 'icon512': 512}[k]
                    sz = png_size(b)
                    if sz and sz != (want, want):
                        warnings.append(f'pwa.{k}: размер {sz[0]}×{sz[1]}, ожидается {want}×{want}')
        if m.get('preview'):
            pic(m['preview'], 'preview', ('png', 'jpg', 'jpeg', 'webp', 'svg'))
        for p in assets:
            if p.endswith('.woff2') and files[p][:4] != b'wOF2':
                errors.append(f'{p}: файл не похож на woff2')
        css = ''
        if m.get('css'):
            if m['css'] not in files:
                errors.append(f'css: файл «{m["css"]}» не найден в архиве')
            else:
                try:
                    e, w, css = check_css(files[m['css']].decode('utf-8-sig'), tid, assets)
                    errors += e; warnings += w
                except UnicodeDecodeError:
                    errors.append('theme.css должен быть в UTF-8')
        return errors, warnings, m, css

    def read_zip(self, blob):
        """→ ({path: bytes}, error) — safe unpacking: no absolute / .. paths, limits on count and size, only known file types"""
        if len(blob) > MAX_ZIP:
            return None, f'архив больше {MAX_ZIP // 1024 // 1024} МБ'
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile:
            return None, 'это не zip-архив'
        infos = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/') and not os.path.basename(i.filename).startswith('.')]
        if len(infos) > MAX_FILES:
            return None, f'в архиве больше {MAX_FILES} файлов'
        names = [i.filename.replace('\\', '/') for i in infos]
        top = ''
        if 'theme.json' not in names:                         # a single top folder is fine: «my-theme/theme.json»
            c = {n.split('/')[0] for n in names if '/' in n}
            if len(c) == 1 and f'{next(iter(c))}/theme.json' in names:
                top = next(iter(c)) + '/'
        files, total = {}, 0
        for i, n in zip(infos, names):
            rel = n[len(top):] if top and n.startswith(top) else n
            if rel.startswith('/') or '..' in rel.split('/') or ':' in rel or not rel:
                return None, f'недопустимый путь в архиве: «{n}»'
            if os.path.splitext(rel)[1].lower() not in EXT:
                return None, f'тип файла не разрешён: «{rel}» (можно: {", ".join(sorted(EXT))})'
            if i.file_size > MAX_FILE:
                return None, f'файл «{rel}» больше {MAX_FILE // 1024 // 1024} МБ'
            total += i.file_size
            if total > MAX_UNPACKED:
                return None, 'архив слишком большой после распаковки'
            files[rel] = z.read(i)
        return files, None

    def validate(self, blob):
        files, err = self.read_zip(blob)
        if err:
            return {'ok': False, 'errors': [err], 'warnings': []}
        errors, warnings, m, css = self.check(files)
        return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'manifest': m, 'files': files, 'css': css}

    def install(self, blob):
        """→ report; the look is written to disk only when there are no errors"""
        r = self.validate(blob)
        if not r['ok']:
            return {k: r[k] for k in ('ok', 'errors', 'warnings')}
        m, files = r['manifest'], r['files']
        tid = m['id']
        with self.lock:
            dst = os.path.join(self.dir, tid)
            tmp = dst + '.new'
            shutil.rmtree(tmp, ignore_errors=True)
            for rel, b in files.items():
                p = os.path.join(tmp, *rel.split('/'))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'wb') as f:
                    f.write(b)
            shutil.rmtree(dst, ignore_errors=True)
            os.replace(tmp, dst)
            self.status[tid] = {'ok': True, 'problems': [], 'warnings': r['warnings'], 'installed': int(time.time()), 'name': m['name'], 'version': str(m['version']), 'api': m['api']}
            self._save_status()
        return {'ok': True, 'errors': [], 'warnings': r['warnings'], 'id': tid, 'name': m['name']}

    def remove(self, tid):
        if not ID_RE.match(tid or ''):
            return False
        with self.lock:
            shutil.rmtree(os.path.join(self.dir, tid), ignore_errors=True)
            self.status.pop(tid, None)
            self._save_status()
        return True

    # ── at start (and after every update): does every installed look still fit? ──
    def _files(self, tid):
        base = os.path.join(self.dir, tid)
        files = {}
        for dp, dn, fn in os.walk(base):
            for f in fn:
                p = os.path.join(dp, f)
                with open(p, 'rb') as fh:
                    files[os.path.relpath(p, base).replace(os.sep, '/')] = fh.read()
        return files

    def recheck(self):
        """→ [(id, name, [problems])] for looks that just stopped fitting (so the journal can say it)"""
        broke = []
        with self.lock:
            for tid in [d for d in os.listdir(self.dir) if os.path.isdir(os.path.join(self.dir, d)) and ID_RE.match(d)]:
                try:
                    errors, warnings, m, css = self.check(self._files(tid))
                except OSError as e:
                    errors, warnings, m = [str(e)], [], None
                old = self.status.get(tid) or {}
                st = {'ok': not errors, 'problems': errors, 'warnings': warnings, 'installed': old.get('installed') or int(time.time()),
                      'name': (m or {}).get('name') or old.get('name') or tid, 'version': str((m or {}).get('version') or old.get('version') or ''), 'api': (m or {}).get('api')}
                if old.get('ok', True) and errors:
                    broke.append((tid, st['name'], errors))
                self.status[tid] = st
            for tid in [t for t in self.status if not os.path.isdir(os.path.join(self.dir, t))]:
                self.status.pop(tid)
            self._save_status()
        return broke

    # ── what the browser gets ──
    def list(self):
        out = []
        for tid, st in sorted(self.status.items(), key=lambda x: x[1].get('name', '')):
            m = {}
            try:
                with open(os.path.join(self.dir, tid, 'theme.json'), encoding='utf-8-sig') as f:
                    m = json.load(f)
            except (OSError, ValueError):
                pass
            prev = m.get('preview') if isinstance(m.get('preview'), str) else None
            out.append({'id': tid, 'name': st.get('name') or tid, 'author': m.get('author') or '', 'version': st.get('version') or '', 'description': m.get('description') or '',
                        'base': m.get('base') or 'classic', 'ok': bool(st.get('ok')), 'problems': st.get('problems') or [], 'warnings': st.get('warnings') or [],
                        'preview': f'/themes/{tid}/{prev}' if prev else None, 'installed': st.get('installed')})
        return out

    def _manifest(self, tid):
        if tid not in self.status or not self.status[tid].get('ok'):
            return None
        try:
            with open(os.path.join(self.dir, tid, 'theme.json'), encoding='utf-8-sig') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def css(self, tid):
        """compiled CSS of one look: the variables, then theme.css; empty when the look is switched off"""
        m = self._manifest(tid)
        if not m:
            return f'/* {tid}: not installed or switched off */'
        tk = m.get('tokens') or {}
        out = [f'/* Rack Live look «{m.get("name")}» {m.get("version")} (api {m.get("api")}) */']
        for mode in ('dark', 'light'):
            vals = {**(tk.get('all') or {}), **(tk.get(mode) or {})}
            vals = {k: v for k, v in vals.items() if k in TOKENS}
            if vals:
                out.append(f'html[data-theme-id="{tid}"][data-theme="{mode}"]{{' + ';'.join(f'{k}:{v}' for k, v in vals.items()) + '}')
        if m.get('css'):
            try:
                with open(os.path.join(self.dir, tid, *m['css'].split('/')), encoding='utf-8-sig') as f:
                    out.append(check_css(f.read(), tid, {p for p in self._files(tid) if p.startswith('assets/')})[2])
            except OSError:
                pass
        return '\n'.join(out)

    def all_css(self):
        return '\n'.join(self.css(t) for t, st in sorted(self.status.items()) if st.get('ok'))

    def data(self, tid):
        """what the app reads at start: texts, icons, colours of kinds, picture addresses — or None (switched off → the built-in look)"""
        m = self._manifest(tid)
        if not m:
            return None
        url = lambda rel: f'/themes/{tid}/{rel}' if isinstance(rel, str) else None
        pwa = {k: url(v) for k, v in (m.get('pwa') or {}).items() if k in ('favicon', 'appleTouch', 'icon192', 'icon512')}
        return {'id': tid, 'name': m.get('name'), 'version': str(m.get('version')), 'base': m.get('base') or 'classic',
                'strings': {k: v for k, v in (m.get('strings') or {}).items() if k in self.defaults()['strings']},
                'icons': {k: v for k, v in (m.get('icons') or {}).items() if isinstance(v, str)},
                'kindColors': {k: v for k, v in (m.get('kindColors') or {}).items() if k in self.defaults()['kinds']},
                'appIcons': {k: url(v) for k, v in (m.get('appIcons') or {}).items() if k in APP_ICON_SLOTS}, 'frankAvatar': url(m.get('frankAvatar')), 'pwa': pwa, 'rev': self.rev,
                'installed': (self.status.get(tid) or {}).get('installed')}

    def asset(self, tid, rel):
        """(bytes, content-type) of a file of a look that is switched on, only from its own folder"""
        if not ID_RE.match(tid or '') or not (self.status.get(tid) or {}).get('ok'):
            return None
        rel = (rel or '').replace('\\', '/')
        if rel.startswith('/') or '..' in rel.split('/') or os.path.splitext(rel)[1].lower() not in EXT - {'.json'}:
            return None
        p = os.path.join(self.dir, tid, *rel.split('/'))
        if not os.path.isfile(p):
            return None
        ct = {'.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2',
              '.css': 'text/css; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8'}[os.path.splitext(p)[1].lower()]
        with open(p, 'rb') as f:
            return f.read(), ct

    # ── for authors ──
    def template_zip(self):
        """a small working look to start from (graphite base, a few colours, one icon, one text, an app icon)"""
        rack = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="114" fill="#16213a"/>'
                '<g fill="none" stroke="#7fd1ff" stroke-width="14" stroke-linecap="round"><rect x="130" y="120" width="252" height="74" rx="24"/><rect x="130" y="219" width="252" height="74" rx="24"/>'
                '<rect x="130" y="318" width="252" height="74" rx="24"/></g><circle cx="174" cy="157" r="12" fill="#7fffd4"/><circle cx="174" cy="256" r="12" fill="#7fffd4"/><circle cx="174" cy="355" r="12" fill="#ffd23f"/></svg>')
        manifest = {
            'id': 'my-look', 'name': 'Моё оформление', 'author': 'Ваше имя', 'version': '1.0.0', 'description': 'Шаблон: тёмно-синий фон и бирюзовый акцент.',
            'api': THEME_API, 'minVersion': self.version, 'base': 'graphite',
            'tokens': {'dark': {'--bg': '#0b1220', '--card-solid': '#16213a', '--card': '#16213a', '--fill': '#1f2c4a', '--accent': '#38bdf8', '--line': '#223253', '--text': '#eaf2ff'},
                       'light': {'--bg': '#eef4fb', '--accent': '#0284c7'}, 'all': {'--r-lg': '22px'}},
            'css': 'theme.css',
            'strings': {'tab.rack': 'Дом', 'tour.hi.title': 'Привет! Это моё оформление'},
            'icons': {'home': 'M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10'},
            'kindColors': {'router': '#38bdf8', 'nas': '#7fffd4'},
            'appIcons': {'rack': 'assets/rack.svg'},
            'pwa': {'favicon': 'assets/rack.svg'},
        }
        css = (f'/* Правила ТОЛЬКО с этим началом селектора: html[data-theme-id="my-look"] … (замените my-look на свой id, если меняли его в theme.json) */\n'
               f'html[data-theme-id="my-look"] .card {{ border-radius: 22px; }}\n'
               f'html[data-theme-id="my-look"] .btn.primary {{ background: linear-gradient(135deg, #38bdf8, #0284c7); }}\n'
               f'/* Фоновую картинку кладите в assets/ и подключайте так: background-image: url(assets/bg.png) */\n')
        readme = ('Шаблон оформления Rack Live.\n\n1) Измените theme.json: id, name, author, цвета (tokens), тексты (strings), иконки (icons).\n'
                  '2) Если меняете id — замените его и в theme.css (html[data-theme-id="…"]).\n3) Сожмите в .zip (theme.json в корне архива) и загрузите: Настройки → Оформление → «Добавить своё».\n'
                  'Полная инструкция: в том же окне «Инструкция для нейросети» (текстовый файл — отдайте его ИИ вместе с идеей оформления).\n')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('theme.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            z.writestr('theme.css', css)
            z.writestr('assets/rack.svg', rack)
            z.writestr('README.txt', readme)
        return buf.getvalue()

    def guide_text(self):
        d = self.defaults()
        L = []
        w = L.append
        w('ИНСТРУКЦИЯ: КАК СДЕЛАТЬ СВОЁ ОФОРМЛЕНИЕ ДЛЯ RACK LIVE')
        w(f'Версия контракта оформления (api): {THEME_API}. Rack Live {self.version}.')
        w('')
        w('Это файл для человека и для нейросети. Если вы читаете его как нейросеть: ваша задача — по описанию пользователя создать ZIP-архив оформления,')
        w('строго соблюдая правила ниже. Ничего вне этих правил не придумывайте — архив с нарушениями Rack Live не примет и объяснит, что не так.')
        w('')
        w('1. ЧТО ТАКОЕ ОФОРМЛЕНИЕ')
        w('Это набор ФАЙЛОВ-ДАННЫХ (JSON, CSS, картинки). Никакого JavaScript, HTML-страниц и программ — они не запускаются и не принимаются.')
        w('Оформление может поменять: цвета и скругления, шрифт, любую иконку интерфейса, иконки приложений (Rack Live, Frank, Тест скорости),')
        w('иконку для экрана «Домой» (PWA) и значок вкладки, цвета типов устройств, тексты (вкладки, окно входа, имя Frank, ВСЕ шаги приветственного обучения),')
        w('а через theme.css — внешний вид любого блока (карточки, кнопки, плитки, шапка, док, окна, Frank, обучение), включая фоновые картинки и шрифты woff2.')
        w('')
        w('2. СТРУКТУРА АРХИВА (.zip)')
        w('   theme.json        — обязательный, описание и настройки (см. раздел 3)')
        w('   theme.css         — необязательный, свои правила CSS (см. раздел 5)')
        w('   assets/…          — картинки (svg, png, jpg, webp) и шрифты (woff2), на которые ссылаются файлы выше')
        w('Файл theme.json должен лежать в корне архива (допускается одна общая папка внутри). Разрешённые типы файлов: ' + ', '.join(sorted(EXT)) + '.')
        w(f'Лимиты: архив до {MAX_ZIP // 1024 // 1024} МБ, не больше {MAX_FILES} файлов, файл до {MAX_FILE // 1024 // 1024} МБ, theme.css до {MAX_CSS // 1024} КБ, картинка до 1 МБ, SVG до 300 КБ.')
        w('')
        w('3. theme.json — ПОЛЯ')
        w('{')
        w('  "id": "ocean-night",              // обязательно: латиница в нижнем регистре, цифры, дефис; 3–32 символа; начинается с буквы. Нельзя: ' + ', '.join(sorted(RESERVED)))
        w('  "name": "Океанская ночь",         // обязательно, до 40 символов')
        w('  "author": "Имя автора",           // до 60 символов')
        w('  "version": "1.0.0",               // обязательно: версия самой темы')
        w('  "description": "Коротко о теме",  // до 300 символов')
        w(f'  "api": {THEME_API},                       // обязательно: версия контракта (сейчас {THEME_API}); с другим числом тема отклоняется')
        w(f'  "minVersion": "{self.version}",          // необязательно: с какой версии Rack Live тема работает')
        w('  "base": "graphite",               // "classic" (стекло, синий) или "graphite" (плоский чёрный, зелёный): тема накладывается поверх выбранного')
        w('  "tokens": { "dark": {...}, "light": {...}, "all": {...} },   // цвета и размеры, раздел 4 («all» — для обеих тем, «dark»/«light» перекрывают)')
        w('  "css": "theme.css",               // необязательно')
        w('  "strings": { "tab.rack": "Дом" }, // тексты, раздел 6')
        w('  "icons": { "home": "M3 11l9-8 9 8..." },   // свои иконки, раздел 7')
        w('  "kindColors": { "router": "#38bdf8" },     // цвета значков типов устройств, раздел 7')
        w('  "appIcons": { "rack": "assets/rack.svg", "frank": "assets/frank.svg", "speed": "assets/speed.svg" },  // иконки приложений в интерфейсе')
        w('  "frankAvatar": "assets/frank-eye.svg",   // СВОЯ КАРТИНКА ВМЕСТО ГЛАЗА Frank (кнопка в шапке, чат, обучение); без неё глаз рисуется сам, его цвета — переменные --frank-…')
        w('  "pwa": { "favicon": "assets/fav.svg", "appleTouch": "assets/touch-180.png", "icon192": "assets/i192.png", "icon512": "assets/i512.png" },  // значки для экрана «Домой»')
        w('  "preview": "assets/preview.png"   // необязательно: картинка для карточки темы')
        w('}')
        w('Комментарии // в настоящем JSON ЗАПРЕЩЕНЫ — здесь они только для пояснения.')
        w('')
        w('4. ПЕРЕМЕННЫЕ (tokens) — значение подставляется как значение CSS (цвет, размер, список шрифтов). Нельзя url(), ;, {, }.')
        for k, v in TOKENS.items():
            w(f'   {k:14} — {v}')
        w('Цвета: #rrggbb, rgb(), rgba(), hsl(), color-mix(). Размеры: 14px. Неизвестные переменные игнорируются (с предупреждением).')
        w('')
        w('5. theme.css — СВОИ ПРАВИЛА')
        w('ГЛАВНОЕ ПРАВИЛО: каждый селектор начинается с  html[data-theme-id="ВАШ-ID"]  (id из theme.json). Пример:')
        w('   html[data-theme-id="ocean-night"] .card { border-radius: 28px; }')
        w('   html[data-theme-id="ocean-night"] .btn.primary, html[data-theme-id="ocean-night"] .tour-next { background: #0ea5e9; }')
        w('Так тема не может повлиять на что-то вне себя. Разрешено: обычные правила, @media, @supports, @keyframes (имя начинайте с id темы: ocean-night-имя), @font-face (только .woff2 из assets/).')
        w('ЗАПРЕЩЕНО: @import, внешние ссылки (https://…), url() кроме assets/имя и data:image, обратный слэш вне кавычек, expression(), javascript:, behavior, <script>, @charset, @page, @container.')
        w('Фон-картинка:  background-image: url(assets/bg.jpg)   (файл лежит в assets/).')
        w('СТАБИЛЬНЫЕ КЛАССЫ (их названия не меняются без повышения api; стильте их свободно):')
        hooks = sorted(HOOKS)
        line = '   '
        for h in hooks:
            if len(line) + len(h) > 100:
                w(line); line = '   '
            line += '.' + h + ' '
        w(line)
        w('Другие классы тоже можно использовать, но Rack Live покажет предупреждение: при обновлении они могут быть переименованы, и этот кусок темы перестанет действовать.')
        w('Совет: сначала меняйте цвета через tokens — это самое устойчивое; theme.css используйте для формы, теней, картинок, анимаций.')
        w('')
        w('6. ТЕКСТЫ (strings) — ключ → ваш текст (до 400 символов, обычный текст без HTML). Что не указано — остаётся по умолчанию.')
        for k, v in d['strings'].items():
            w(f'   {k}  =  {v}')
        w('Тексты обучения: tour.<шаг>.title / .text / .next. Шаги по порядку: ' + ', '.join(d['tourSteps']) + '.')
        w('')
        w('7. ИКОНКИ И ЦВЕТА УСТРОЙСТВ')
        w('icons: имя → путь SVG (атрибут d), сетка 24×24, рисуется контуром (stroke) толщиной, которую задаёт интерфейс; можно несколько подпутей, начинающихся с M.')
        w('   Допустимые символы пути: M L H V C S Q T A Z, числа, пробелы, запятые, точка, минус. Пример: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10"')
        w('   Имена иконок: ' + ' '.join(d['icons']))
        w('kindColors: тип устройства → цвет. Типы: ' + ' '.join(d['kinds']))
        w('')
        w('8. ИКОНКИ ПРИЛОЖЕНИЙ И PWA')
        w('appIcons.rack / frank / speed — картинки (svg, png, jpg, webp), показываются в шапке, на экране входа, в настройках и в приложениях Frank и «Тест скорости».')
        w('pwa.favicon — значок вкладки (svg или png). pwa.appleTouch — PNG 180×180, pwa.icon192 — PNG 192×192, pwa.icon512 — PNG 512×512: ими пользуется iPhone/Android')
        w('при добавлении на экран «Домой». ВАЖНО: уже установленный значок на телефоне сам не меняется — нужно удалить его и добавить заново после выбора темы.')
        w('SVG: без скриптов, без внешних ссылок, без foreignObject, без атрибутов on…=.')
        w('')
        w('8б. ПАНЕЛЬ ПОРТОВ, ПОДСКАЗКИ И FRANK — ЧТО ЕЩЁ МОЖНО ОФОРМИТЬ')
        w('   • Панель портов коммутатора/роутера (в карточке устройства): подложка — --faceplate-bg (по умолчанию тёмная; сделайте светлой или цветной), цвета состояний портов — --port-g (1 Гбит), --port-y (100 Мбит),')
        w('     --port-o (10 Мбит), --port-dis, --port-wan, форма и размер — --port-radius, --port-w, --port-h; значок PoE — --poe-badge и иконка "bolt" в icons. Классы для CSS: .faceplate .ports .port .port.g .port.y .port.o')
        w('     .port.dis .port.sfp .port.wan .port.sel .poe .vl. Пример своей формы и картинки в порту:')
        w('       html[data-theme-id="ID"] .port { border-radius: 50%; }')
        w('       html[data-theme-id="ID"] .port.g { background-image: url(assets/port-up.svg); background-size: 62%; background-repeat: no-repeat; background-position: center; }')
        w('   • Подсказки (жёлтые плашки вверху вкладок): --hint-bg, --hint-line, --hint-text, --hint-ico, --hint-ico-bg, --hint-close-bg, --hint-close-text, --hint-radius; иконка лампочки — icons "bulb"; класс .hint-box.')
        w('   • Frank: глаз рисуется сам — его цвета задают --frank-sclera (белок), --frank-pupil, --frank-lid (веко), --frank-iris-0/1/2 (радужка), --frank-bg (плитка за глазом), --frank-glow (сияние в обучении),')
        w('     настроения --frank-m2-* («напряжён») и --frank-m3-* («тревога»). ИЛИ замените глаз своей картинкой: "frankAvatar": "assets/файл.svg" (svg/png/webp, квадрат). Имя — strings "frank.name"; значок приложения — appIcons.frank.')
        w('')
        w('8а. ПОДСКАЗКИ И ЛОВУШКИ ДЛЯ АВТОРА')
        w('   • Сначала tokens, потом css. Цвета через переменные работают везде, в том числе внутри шкафа, карты и виджетов, и переживают обновления лучше всего.')
        w('   • Всегда задавайте и dark, и light (или «all»): человек может переключить тему. Проверьте контраст текста и фона в обеих.')
        w('   • Виджеты на главной содержат вложенные .card без рамки и фона. Если вы стилите .card (тень, рамка, фон) — добавьте исключение:')
        w('       html[data-theme-id="ID"] .wg-body > .card { box-shadow: none; border: 0; background: none; }')
        w('   • Не прячьте элементы через display:none: можно скрыть кнопку, без которой нельзя пользоваться приложением. Тема не должна ломать управление.')
        w('   • Проверьте узкий экран (телефон, ширина 390 px): правила для него пишутся через @media (max-width: 760px) { html[data-theme-id="ID"] … }.')
        w('   • Имена Frank и текст приветствия заменяются только там, где есть ключ в списке строк (раздел 6); остальные подписи остаются по умолчанию.')
        w('   • Иконку на экране «Домой» меняют только при новой установке значка; в самом интерфейсе иконки приложений (appIcons) меняются сразу.')
        w('   • Меняйте контракт осторожно: если при обновлении Rack Live число api станет другим, тема будет отключена и вернётся стандартный вид — тогда обновите тему по новой инструкции.')
        w('')
        w('9. КАК ЗАГРУЗИТЬ И ПРОВЕРИТЬ')
        w('Настройки → Оформление → «Добавить своё» → выберите .zip. Rack Live проверит архив и покажет ОШИБКИ (тема не установится) и ПРЕДУПРЕЖДЕНИЯ (установится).')
        w('Если после выбора темы интерфейс стал нечитаемым — откройте адрес панели с добавкой ?skin=classic (например http://адрес:порт/?skin=classic): вернётся стандартное оформление.')
        w('После каждого обновления Rack Live все темы проверяются заново; несовместимая тема отключается сама, интерфейс возвращается к стандартному, причина показывается в разделе «Оформление».')
        w('')
        w('10. ПОРЯДОК РАБОТЫ ДЛЯ НЕЙРОСЕТИ')
        w('   а) уточните у пользователя идею (цвета, настроение, что менять: только цвета / ещё иконки / тексты / обучение / иконки приложений);')
        w('   б) придумайте id, name, version "1.0.0", api ' + str(THEME_API) + ', выберите base;')
        w('   в) составьте theme.json: начните с tokens (dark и light), затем strings/icons/kindColors при необходимости;')
        w('   г) только если нужно — theme.css с селекторами html[data-theme-id="id"] …; картинки — в assets/;')
        w('   д) выдайте файлы и структуру архива; проверьте себя по чек-листу ниже.')
        w('ЧЕК-ЛИСТ: ☐ theme.json — валидный JSON без комментариев  ☐ id из допустимых символов и не зарезервирован  ☐ "api": ' + str(THEME_API) + '  ☐ все пути (css, assets/…) существуют в архиве')
        w('   ☐ каждый селектор в theme.css начинается с html[data-theme-id="id"]  ☐ нет @import, http(s)://, обратных слэшей, url() вне assets/  ☐ в SVG нет скриптов и внешних ссылок')
        w('   ☐ для светлой и тёмной темы заданы читаемые цвета текста и фона (контраст)  ☐ ключи strings, icons, kindColors взяты из списков выше.')
        w('')
        w('ПРИМЕР МИНИМАЛЬНОГО theme.json:')
        w('{"id":"ocean-night","name":"Океанская ночь","author":"Ваше имя","version":"1.0.0","api":' + str(THEME_API) + ',"base":"graphite","tokens":{"dark":{"--bg":"#0b1220","--accent":"#38bdf8"},"light":{"--accent":"#0284c7"}}}')
        return '\n'.join(L) + '\n'
