#!/usr/bin/env python3
"""Builds the example look «Океанская ночь» (docs/themes/ocean-night/ + docs/themes/ocean-night.zip) — a complete sample for authors:
colours for both themes, css, own icons, renamed tabs, Frank's new name with its own tour texts, app icons and the PNGs for the home screen.
    python tools/make_example_theme.py"""
import json, os, struct, sys, zlib, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'themes', 'ocean-night')
sys.path.insert(0, ROOT)
from rackd import themes as th


def png(size, top, bottom):
    """a plain PNG without any library: a vertical gradient with three white 'server' bars"""
    def px(x, y):
        t = y / size
        c = [int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)]
        bx0, bx1 = int(size * .26), int(size * .74)
        for k in range(3):
            y0 = int(size * (.28 + k * .17)); y1 = y0 + int(size * .11)
            if bx0 <= x <= bx1 and y0 <= y <= y1:
                return (255, 255, 255, 235) if abs(x - bx0) > size * .03 else (80, 230, 190, 255)
        return (*c, 255)
    raw = b''.join(b'\x00' + b''.join(bytes(px(x, y)) for x in range(size)) for y in range(size))
    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


def app_icon(glyph):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f3a63"/>'
            '<stop offset="1" stop-color="#04121f"/></linearGradient></defs><rect width="512" height="512" rx="114" fill="url(#g)"/>'
            '<path d="M40 372c60-40 120-40 180 0s120 40 180 0 60-20 72-30v130H40z" fill="#33b6ff" opacity=".35"/>' + glyph + '</svg>')


RACK = '<g fill="none" stroke="#bfe9ff" stroke-width="14" stroke-linecap="round"><rect x="128" y="104" width="256" height="70" rx="24"/><rect x="128" y="196" width="256" height="70" rx="24"/><rect x="128" y="288" width="256" height="70" rx="24"/></g><circle cx="172" cy="139" r="12" fill="#3ddc97"/><circle cx="172" cy="231" r="12" fill="#3ddc97"/><circle cx="172" cy="323" r="12" fill="#ffb454"/>'
FRANK = '<g fill="none" stroke="#bfe9ff" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"><path d="M86 230c46-76 110-112 170-112s124 36 170 112c-46 76-110 112-170 112S132 306 86 230z"/><circle cx="256" cy="230" r="58"/></g><circle cx="256" cy="230" r="24" fill="#33b6ff"/>'
SPEED = '<g fill="none" stroke="#bfe9ff" stroke-width="16" stroke-linecap="round"><path d="M112 320a160 160 0 1 1 288 0"/><path d="M256 308l74-96"/></g><circle cx="256" cy="308" r="22" fill="#3ddc97"/>'

MANIFEST = {
    'id': 'ocean-night', 'name': 'Океанская ночь', 'author': 'Rack Live (пример)', 'version': '1.0.0',
    'description': 'Глубокий синий, голубой акцент, крупные скругления, свои иконки и тексты; Frank здесь — «Нептун».',
    'api': th.THEME_API, 'minVersion': '2.5.0', 'base': 'graphite',
    'tokens': {
        'dark': {'--bg': '#06121f', '--bg2': '#0a1b2d', '--card': '#0f2742', '--card-solid': '#0f2742', '--elev': '#0d2038', '--fill': '#16385c', '--fill2': '#1c4572',
                 '--line': '#1b3a5e', '--line2': '#28507d', '--text': '#e8f4ff', '--text2': '#9dbbd8', '--text3': '#6a8cad', '--accent': '#33b6ff', '--green': '#3ddc97',
                 '--orange': '#ffb454', '--red': '#ff6b81', '--dock': '#081a2b', '--glass': '#0d2038', '--glass-line': '#1b3a5e', '--dock-glass': '#0d2038', '--fr-btn': '#16385c',
                 '--rack-bg': 'linear-gradient(180deg, #123456, #0b2540)', '--rack-body': '#06121f', '--rack-hole': '#16385c', '--rack-text': '#e8f4ff',
                 '--unit-bg': 'linear-gradient(180deg, #17406a, #0f2f50)', '--unit-text': '#e8f4ff', '--unit-icon-bg': 'rgba(127,209,255,.14)', '--led-off': '#1c3556',
                 '--map-rack-frame': '#0a1b2d', '--map-rack-stroke': '#28507d', '--map-unit': '#12304f',
                 '--faceplate-bg': 'linear-gradient(180deg, #0f3157, #0a2340)', '--port-bg': '#16385c', '--port-border': '#2b5d94', '--port-radius': '9px', '--port-base': '#0a2340',
                 '--port-g': '#3ddc97', '--port-y': '#ffd479', '--port-o': '#ffa45c', '--poe-badge': '#7fd1ff',
                 '--hint-bg': 'rgba(51,182,255,.10)', '--hint-line': 'rgba(51,182,255,.45)', '--hint-ico': '#7fd1ff', '--hint-ico-bg': 'rgba(51,182,255,.18)',
                 '--frank-iris-0': '#b9f3ff', '--frank-iris-1': '#33b6ff', '--frank-iris-2': '#0a4f8a', '--frank-glow': '#33b6ff', '--frank-bg': '#0f2742'},
        'light': {'--bg': '#eaf4fb', '--bg2': '#ffffff', '--card': '#ffffff', '--card-solid': '#ffffff', '--elev': '#ffffff', '--fill': '#dcebf7', '--fill2': '#c9ddef', '--line': '#cfe0ee',
                  '--line2': '#b6cfe4', '--text': '#0b2740', '--text2': '#4b6a85', '--text3': '#7f9ab2', '--accent': '#0a7fd6', '--dock': '#ffffff', '--glass': '#ffffff', '--dock-glass': '#ffffff',
                  '--rack-bg': 'linear-gradient(180deg, #f4faff, #d9ebf8)', '--rack-body': '#cfe3f3', '--unit-bg': 'linear-gradient(180deg, #ffffff, #eaf4fb)', '--led-off': '#b9d0e4',
                  '--faceplate-bg': 'linear-gradient(180deg, #e3f1fb, #cfe3f3)', '--port-bg': '#ffffff', '--port-border': '#9cc0dc', '--port-text': '#4b6a85', '--port-base': '#ffffff', '--port-link-text': '#0b2740',
                  '--hint-bg': 'rgba(10,127,214,.08)', '--hint-line': 'rgba(10,127,214,.40)', '--hint-ico': '#0a7fd6', '--hint-ico-bg': 'rgba(10,127,214,.14)'},
        'all': {'--r': '14px', '--r-lg': '24px'}},
    'css': 'theme.css',
    'strings': {
        'tab.rack': 'Порт', 'tab.map': 'Карта', 'tab.devices': 'Корабли', 'tab.events': 'Вахта', 'tab.settings': 'Штурвал',
        'frank.name': 'Нептун', 'app.name': 'Океан', 'auth.welcome': 'Добро пожаловать на борт', 'auth.login': 'Назовите пароль, капитан', 'auth.signin': 'Поднять якорь', 'auth.start': 'Выйти в море',
        'tour.skipAll': 'Выйти из обучения', 'tour.next': 'Дальше по курсу',
        'tour.hi.title': 'Привет! Я Нептун', 'tour.hi.text': 'Покажу, как здесь всё устроено: корабли (устройства), карта и штурвал (настройки). Нажимать можно только подсвеченное.',
        'tour.devices.title': 'Начнём с кораблей', 'tour.end.title': 'Попутного ветра!'},
    'frankAvatar': 'assets/frank-eye.svg',
    'icons': {'home': 'M12 3a2 2 0 100 4 2 2 0 000-4M12 7v14M5 12H3a9 9 0 0018 0h-2', 'bell': 'M6 8a6 6 0 0112 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 004 0', 'bulb': 'M12 2a6 6 0 00-3 11v3h6v-3a6 6 0 00-3-11M10 20h4M11 22h2'},
    'kindColors': {'router': '#33b6ff', 'switch': '#3ddc97', 'server': '#7c8cff', 'nas': '#4fd1e6', 'ap': '#5ee0c8', 'camera': '#ff6b81', 'ups': '#ffb454'},
    'appIcons': {'rack': 'assets/rack.svg', 'frank': 'assets/frank.svg', 'speed': 'assets/speed.svg'},
    'pwa': {'favicon': 'assets/rack.svg', 'appleTouch': 'assets/touch-180.png', 'icon192': 'assets/icon-192.png', 'icon512': 'assets/icon-512.png'},
    'pwaFrank': {'favicon': 'assets/frank.svg', 'appleTouch': 'assets/frank-touch-180.png', 'icon192': 'assets/frank-192.png', 'icon512': 'assets/frank-512.png'},
    'pwaSpeed': {'favicon': 'assets/speed.svg', 'appleTouch': 'assets/speed-touch-180.png', 'icon192': 'assets/speed-192.png', 'icon512': 'assets/speed-512.png'},
    'tileArt': {'stats': 'assets/tile-stats.svg', 'uptime': 'assets/tile-uptime.svg'},
    'tileColors': {'stats': '#33b6ff', 'internet': '#3ddc97', 'problems': '#ffb454'},
    'preview': 'assets/preview.svg',
}
CSS = '''/* Океанская ночь: всё начинается с html[data-theme-id="ocean-night"] — так правила не выходят за пределы темы */
html[data-theme-id="ocean-night"] .app-bg { background: radial-gradient(1100px 600px at 10% -10%, rgba(51,182,255,.22), transparent 60%), radial-gradient(900px 500px at 100% 10%, rgba(61,220,151,.10), transparent 60%), var(--bg); }
html[data-theme-id="ocean-night"] .card { border-radius: 24px; box-shadow: 0 10px 30px rgba(0,20,60,.35), inset 0 1px 0 rgba(255,255,255,.05); }
html[data-theme-id="ocean-night"] .btn.primary, html[data-theme-id="ocean-night"] .tour-next { background: linear-gradient(135deg, #33b6ff, #0a7fd6); color: #fff; box-shadow: 0 6px 18px rgba(10,127,214,.45); }
html[data-theme-id="ocean-night"] .tab.on { box-shadow: 0 0 0 1px rgba(51,182,255,.5), 0 4px 14px rgba(51,182,255,.25); }
html[data-theme-id="ocean-night"] .wg-in { border-radius: 30px; }
html[data-theme-id="ocean-night"] .wg-body > .card { box-shadow: none; border: 0; background: none; }     /* вложенные карточки виджетов остаются плоскими */
html[data-theme-id="ocean-night"] .tour-bubble { border-radius: 24px; background: #0b1d33; border: 1px solid #28507d; }
html[data-theme-id="ocean-night"] .page-title { letter-spacing: -.6px; background: linear-gradient(90deg, #e8f4ff, #7fd1ff); -webkit-background-clip: text; background-clip: text; color: transparent; }
html[data-theme-id="ocean-night"][data-theme="light"] .page-title { background: linear-gradient(90deg, #0b2740, #0a7fd6); -webkit-background-clip: text; background-clip: text; color: transparent; }
html[data-theme-id="ocean-night"] .port.g { background-image: url(assets/port-up.svg); background-size: 58%; background-repeat: no-repeat; background-position: center 70%; }     /* свой значок на порту с линком */
@media (max-width: 760px) { html[data-theme-id="ocean-night"] .bottombar { border-radius: 30px; } }
'''
PREVIEW = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 160"><rect width="320" height="160" fill="#06121f"/><rect x="16" y="16" width="288" height="44" rx="14" fill="#0f2742"/>'
           '<rect x="28" y="30" width="16" height="16" rx="5" fill="#33b6ff"/><rect x="54" y="34" width="90" height="8" rx="4" fill="#9dbbd8"/><rect x="16" y="72" width="136" height="72" rx="18" fill="#0f2742"/>'
           '<path d="M16 120c30-14 60-14 90 0s30 6 46-2v26H16z" fill="#33b6ff" opacity=".4"/><rect x="168" y="72" width="136" height="72" rx="18" fill="#0f2742"/><circle cx="236" cy="108" r="22" fill="none" stroke="#3ddc97" stroke-width="7"/></svg>')

FRANK_EYE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="26" fill="#0f3a63" stroke="#33b6ff" stroke-width="3"/>'
             '<path d="M10 36c8-14 14-14 22-6s14 8 22-6" fill="none" stroke="#bfe9ff" stroke-width="3.5" stroke-linecap="round"/><circle cx="24" cy="26" r="4" fill="#fff"/><circle cx="40" cy="26" r="4" fill="#fff"/>'
             '<circle cx="24" cy="26" r="1.8" fill="#06121f"/><circle cx="40" cy="26" r="1.8" fill="#06121f"/></svg>')
PORT_UP = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 4v10M7 9l5-5 5 5" fill="none" stroke="#bfffe6" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" opacity=".55"/></svg>'
TILE_STATS = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"><path d="M0 52c15-12 30-12 45 0s30 12 45 0 20-8 30-4v32H0z" fill="#33b6ff" opacity=".4"/>'
              '<path d="M0 40c15-12 30-12 45 0s30 12 45 0 20-8 30-4" fill="none" stroke="#bfe9ff" stroke-width="4" stroke-linecap="round"/><circle cx="60" cy="22" r="9" fill="#3ddc97"/></svg>')
TILE_UPTIME = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"><g fill="#3ddc97">' + ''.join(f'<rect x="{8 + i * 12}" y="{20 + (i * 7) % 18}" width="7" height="{44 - (i * 7) % 18}" rx="3.5"/>' for i in range(9)) + '</g></svg>')
files = {'theme.json': json.dumps(MANIFEST, ensure_ascii=False, indent=2), 'theme.css': CSS, 'assets/rack.svg': app_icon(RACK), 'assets/frank.svg': app_icon(FRANK), 'assets/speed.svg': app_icon(SPEED),
         'assets/preview.svg': PREVIEW, 'assets/tile-stats.svg': TILE_STATS, 'assets/tile-uptime.svg': TILE_UPTIME,
         'assets/frank-touch-180.png': png(180, (60, 40, 110), (10, 8, 30)), 'assets/frank-192.png': png(192, (60, 40, 110), (10, 8, 30)), 'assets/frank-512.png': png(512, (60, 40, 110), (10, 8, 30)),
         'assets/speed-touch-180.png': png(180, (15, 90, 70), (4, 25, 20)), 'assets/speed-192.png': png(192, (15, 90, 70), (4, 25, 20)), 'assets/speed-512.png': png(512, (15, 90, 70), (4, 25, 20)), 'assets/frank-eye.svg': FRANK_EYE, 'assets/port-up.svg': PORT_UP, 'assets/touch-180.png': png(180, (15, 58, 99), (4, 18, 31)), 'assets/icon-192.png': png(192, (15, 58, 99), (4, 18, 31)),
         'assets/icon-512.png': png(512, (15, 58, 99), (4, 18, 31))}
os.makedirs(OUT, exist_ok=True)
for rel, v in files.items():
    p = os.path.join(OUT, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(v if isinstance(v, bytes) else v.encode('utf-8'))
zp = os.path.join(ROOT, 'docs', 'themes', 'ocean-night.zip')
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for rel, v in files.items():
        z.writestr(rel, v)
print('written:', zp, os.path.getsize(zp) // 1024, 'KB')
