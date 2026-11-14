"""«Аврора» app icons (web/look-aurora/): a glass glyph on a saturated colour, as on iOS 26+.
   python tools/aurora_icons.py           → writes <app>.svg and <app>-180/-192/-512.png for every app
   The SVG has its own rounded corners (shown inside the app); -180.png is full-bleed (iOS cuts the corners itself), -192 / -512 are rounded on transparent."""
import math, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'web', 'look-aurora')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'


def frame(c1, c2, shade, body, full=False, extra=''):
    """c1 → c2: the colour from the top-left to the bottom-right; shade: the colour of the glyph's shadow."""
    rx = 0 if full else 114
    rim = '' if full else '<rect x="3" y="3" width="506" height="506" rx="111" fill="none" stroke="url(#rim)" stroke-width="6"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>
  <linearGradient id="bg" x1=".15" y1="0" x2=".85" y2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>
  <radialGradient id="sheen" cx=".22" cy="-.05" r="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset=".55" stop-color="#fff" stop-opacity=".06"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
  <radialGradient id="deep" cx=".85" cy="1.1" r=".8"><stop offset="0" stop-color="#000" stop-opacity=".22"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset=".22" stop-color="#fff" stop-opacity=".16"/><stop offset=".72" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".3"/></linearGradient>
  <linearGradient id="gl" gradientUnits="userSpaceOnUse" x1="0" y1="100" x2="0" y2="420"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity=".84"/></linearGradient>
  <linearGradient id="edge" gradientUnits="userSpaceOnUse" x1="0" y1="100" x2="0" y2="420"><stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset=".5" stop-color="#fff" stop-opacity=".18"/><stop offset="1" stop-color="#fff" stop-opacity=".45"/></linearGradient>
  <filter id="sh" filterUnits="userSpaceOnUse" x="0" y="0" width="512" height="512"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="{shade}" flood-opacity=".5"/></filter>
  <filter id="sh2" filterUnits="userSpaceOnUse" x="0" y="0" width="512" height="512"><feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="{shade}" flood-opacity=".35"/></filter>
  <clipPath id="r"><rect width="512" height="512" rx="{rx}"/></clipPath>{extra}</defs>
<g clip-path="url(#r)"><rect width="512" height="512" fill="url(#bg)"/><rect width="512" height="512" fill="url(#deep)"/><rect width="512" height="512" fill="url(#sheen)"/>
{body}
{rim}</g></svg>
'''


def pt(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def arc(cx, cy, r, a0, a1):
    x0, y0 = pt(cx, cy, r, a0); x1, y1 = pt(cx, cy, r, a1)
    return f'M{x0:.1f} {y0:.1f}A{r} {r} 0 {1 if a1 - a0 > 180 else 0} 1 {x1:.1f} {y1:.1f}'


def shrink(pts, k):
    cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
    return 'M' + 'L'.join(f'{cx + (x - cx) * k:.1f} {cy + (y - cy) * k:.1f}' for x, y in pts) + 'Z'


def frank(full):
    eye = 'M3 20C8 11 14 7.5 20 7.5S32 11 37 20C32 29 26 32.5 20 32.5S8 29 3 20Z'
    extra = ('<radialGradient id="iris" cx=".38" cy=".3" r=".8"><stop offset="0" stop-color="#9cccff"/><stop offset=".55" stop-color="#2f7dff"/><stop offset="1" stop-color="#0b2f9c"/></radialGradient>'
             f'<clipPath id="eyec"><path d="{eye}" transform="translate(256 256) scale(10.6) translate(-20 -20)"/></clipPath>')
    body = f'''<circle cx="256" cy="256" r="176" fill="#fff" fill-opacity=".14"/><circle cx="256" cy="256" r="175" fill="none" stroke="url(#edge)" stroke-width="2.5" stroke-opacity=".8"/>
<g filter="url(#sh)"><path d="{eye}" transform="translate(256 256) scale(10.6) translate(-20 -20)" fill="url(#gl)"/></g>
<g clip-path="url(#eyec)"><circle cx="256" cy="256" r="92" fill="url(#iris)"/><circle cx="256" cy="256" r="40" fill="#06164f"/><circle cx="284" cy="228" r="18" fill="#fff"/><circle cx="232" cy="283" r="8" fill="#fff" fill-opacity=".65"/></g>'''
    return frame('#3b3b41', '#050506', '#000000', body, full, extra)


def speed(full):
    cx, cy, r = 256, 262, 150
    body = f'''<path d="{arc(cx, cy, r, 150, 390)}" fill="none" stroke="#fff" stroke-opacity=".3" stroke-width="38" stroke-linecap="round"/>
<g filter="url(#sh)"><path d="{arc(cx, cy, r, 150, 330)}" fill="none" stroke="url(#gl)" stroke-width="38" stroke-linecap="round"/>
<path d="M286 150L196 286H252L230 382L328 240H270Z" fill="#fff" stroke="#fff" stroke-width="16" stroke-linejoin="round"/></g>'''
    return frame('#4aa8ff', '#0a52e8', '#03256e', body, full)

def terminal(full):
    body = '''<rect x="74" y="96" width="364" height="320" rx="68" fill="#fff" fill-opacity=".09"/><rect x="75" y="97" width="362" height="318" rx="67" fill="none" stroke="url(#edge)" stroke-width="2.5" stroke-opacity=".7"/>
<g filter="url(#sh)"><path d="M152 186l96 70-96 70" fill="none" stroke="url(#gl)" stroke-width="42" stroke-linecap="round" stroke-linejoin="round"/><path d="M286 326h78" stroke="#fff" stroke-opacity=".62" stroke-width="42" stroke-linecap="round"/></g>'''
    return frame('#2c2d31', '#000000', '#000000', body, full)


def plan(full):
    body = '''<rect x="196" y="262" width="120" height="130" rx="20" fill="#fff" fill-opacity=".34"/>
<g filter="url(#sh)" fill="none" stroke="#fff" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"><path d="M92 250L256 112L420 250"/><path d="M134 222V392H378V222"/></g>
<circle cx="256" cy="226" r="24" fill="#fff"/>'''
    return frame('#6ee59a', '#0f9d4e', '#04431f', body, full)

def modeler(full):
    cx, cy, s = 256, 262, 138
    h = s * .5; w = s * .92
    top = [(cx, cy - 2 * h), (cx + w, cy - h), (cx, cy), (cx - w, cy - h)]
    left = [(cx - w, cy - h), (cx, cy), (cx, cy + s), (cx - w, cy + s - h)]
    right = [(cx, cy), (cx + w, cy - h), (cx + w, cy + s - h), (cx, cy + s)]
    f = lambda pts, op: f'<path d="{shrink(pts, .86)}" fill="#fff" stroke="#fff" stroke-width="20" stroke-linejoin="round" opacity="{op}"/>'
    body = f'<g filter="url(#sh)">{f(left, .62)}{f(right, .36)}{f(top, 1)}</g>'
    return frame('#4aa8ff', '#0a52e8', '#03256e', body, full)


def controller(full):
    body = '''<g filter="url(#sh)"><rect x="100" y="136" width="312" height="108" rx="36" fill="url(#gl)"/></g>
<rect x="100" y="268" width="312" height="108" rx="36" fill="#fff" fill-opacity=".34"/><rect x="101" y="269" width="310" height="106" rx="35" fill="none" stroke="url(#edge)" stroke-width="2.5" stroke-opacity=".8"/>
<circle cx="148" cy="190" r="14" fill="#0a52e8"/><path d="M190 190h36l18-28 28 56 22-40 14 12h44" fill="none" stroke="#0a52e8" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="148" cy="322" r="14" fill="#fff"/><path d="M194 322h170" stroke="#fff" stroke-opacity=".9" stroke-width="14" stroke-linecap="round"/>'''
    return frame('#4aa8ff', '#0a52e8', '#03256e', body, full)


ICONS = {'frank': frank, 'speed': speed, 'terminal': terminal, 'plan': plan, 'modeler': modeler, 'controller': controller}


def png(svg, path, size):
    """Draws the SVG in headless Edge at 1024 and scales it down (a window narrower than ~500 px gets cut)."""
    from PIL import Image
    tmp = tempfile.mkdtemp()
    page = os.path.join(tmp, 'i.html'); shot = os.path.join(tmp, 'i.png')
    with open(page, 'w', encoding='utf-8') as f:
        f.write('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:transparent}svg{display:block;width:1024px;height:1024px}</style>' + svg)
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--window-size=1024,1024', '--default-background-color=00000000',
                    f'--screenshot={shot}', f'--user-data-dir={os.path.join(tmp, "p")}', 'file:///' + page.replace('\\', '/')], timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    im = Image.open(shot).convert('RGBA').resize((size, size), Image.LANCZOS)
    if size == 180: im = im.convert('RGB')
    im.save(path, optimize=True)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:]
    for name, fn in ICONS.items():
        if only and name not in only: continue
        with open(os.path.join(OUT, name + '.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(fn(False))
        png(fn(True), os.path.join(OUT, f'{name}-180.png'), 180)
        for s in (192, 512):
            png(fn(False), os.path.join(OUT, f'{name}-{s}.png'), s)
        print('ok', name)
