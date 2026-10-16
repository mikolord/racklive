#!/usr/bin/env python3
"""Builds web/app.js from web/src/*.jsx (Babel preset-react) and fetches React into web/vendor.

    python build.py           # needs Node.js; installs Babel into web/node_modules on first run
"""
import glob, os, shutil, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, 'web')
REACT = '18.3.1'
VENDOR = {
    'react.production.min.js': f'https://unpkg.com/react@{REACT}/umd/react.production.min.js',
    'react-dom.production.min.js': f'https://unpkg.com/react-dom@{REACT}/umd/react-dom.production.min.js',
}


def sh(cmd):
    print('$', ' '.join(cmd))
    subprocess.run(cmd, cwd=WEB, check=True, shell=os.name == 'nt')


def main():
    os.makedirs(os.path.join(WEB, 'vendor'), exist_ok=True)
    for name, url in VENDOR.items():
        p = os.path.join(WEB, 'vendor', name)
        if not os.path.exists(p):
            print('download', url)
            urllib.request.urlretrieve(url, p)
    if not os.path.exists(os.path.join(WEB, 'node_modules', '@babel', 'cli')):
        sh(['npm', 'install', '--no-audit', '--no-fund', '--silent'])
    src = sorted(glob.glob(os.path.join(WEB, 'src', '*.jsx')))
    bundle = os.path.join(WEB, '.bundle.jsx')
    with open(bundle, 'w', encoding='utf-8', newline='\n') as out:
        for f in src:
            out.write(f'\n/* ── {os.path.basename(f)} ── */\n')
            out.write(open(f, encoding='utf-8').read())
    # --minified strips whitespace/comments (names stay readable in errors); the server also gzips it
    sh(['npx', 'babel', '.bundle.jsx', '--presets=@babel/preset-react', '--minified', '--no-comments', '-o', 'app.js'])
    os.remove(bundle)
    print('ok:', os.path.getsize(os.path.join(WEB, 'app.js')), 'bytes')
    defaults()


def defaults():
    """web/theme-defaults.json: what a custom look (rackd/themes.py) may replace — read from the code itself, so the list and the guide never drift from the app:
    the names of the icons (ICON_PATHS), every text wrapped as T('key', 'default'), and the welcome-tour step texts."""
    import json, re
    src = {os.path.basename(f): open(f, encoding='utf-8').read() for f in sorted(glob.glob(os.path.join(WEB, 'src', '*.jsx')))}
    core = src['00_core.jsx']
    m = re.search(r'const ICON_PATHS = \{(.*?)\n\};', core, re.S)
    icons = re.findall(r"(?:^|[\s,{])([a-z][a-z0-9]*):\s*'", m.group(1)) if m else []
    kinds = re.findall(r"(\w+): '#[0-9a-f]{6}'", re.search(r'const KIND_COLOR = \{(.*?)\};', core, re.S).group(1))
    strings = {}
    for text in src.values():
        for k, v in re.findall(r"\bT\('([\w.]+)',\s*'((?:[^'\\]|\\.)*)'\)", text):
            strings[k] = v.replace("\\'", "'")
    app = src['90_app.jsx']; a0 = app.index('const TABS = [')
    for tid, label in re.findall(r"\{ id: '(\w+)', label: '([^']*)'", app[a0:app.index('\n];', a0)]):
        strings[f'tab.{tid}'] = label
    tour = src['95_tour.jsx']
    a = tour.index('const TOUR_STEPS = ['); block = tour[a:tour.index('\n];', a)]
    S = r"'((?:[^'\\]|\\.)*)'"
    steps = []
    for p in re.split(r"\n  \{ id: '", block)[1:]:
        sid = p.split("'", 1)[0]
        g = lambda k: (re.search(k + r': ' + S, p) or [None, ''])[1].replace("\\'", "'")
        steps.append(sid)
        for field in ('title', 'text', 'next'):
            if g(field):
                strings[f'tour.{sid}.{field}'] = g(field)
    dash = src['92_dashboard.jsx']; w0 = dash.index('const WIDGETS = {')
    widgets = re.findall(r"^  (\w+): \{ title:", dash[w0:dash.index('\n};', w0)], re.M)
    out = {'icons': icons, 'kinds': kinds, 'strings': dict(sorted(strings.items())), 'tourSteps': steps, 'widgets': widgets}
    with open(os.path.join(WEB, 'theme-defaults.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('theme-defaults.json:', len(icons), 'icons,', len(strings), 'texts,', len(kinds), 'kinds,', len(widgets), 'widgets')


if __name__ == '__main__':
    sys.exit(main())
