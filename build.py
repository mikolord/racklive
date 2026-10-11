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
    sh(['npx', 'babel', '.bundle.jsx', '--presets=@babel/preset-react', '--compact=false', '-o', 'app.js'])
    os.remove(bundle)
    print('ok:', os.path.getsize(os.path.join(WEB, 'app.js')), 'bytes')


if __name__ == '__main__':
    sys.exit(main())
