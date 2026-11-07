"""«🇩🇪 Germany» → the flag picture as the icon of a server (KindIcon in web/src/00_core.jsx, files in web/flags).
Checks the JS helpers (flagOf / nameNoFlag, run in Node), that every country the helpers can return has a picture where it matters,
that the pictures are plain SVG, and that the files travel with the app (Dockerfile + deploy list).   python tools/flags_test.py"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = True


def check(name, cond, extra=''):
    global ok
    print(('OK   ' if cond else 'FAIL ') + name + (' — ' + str(extra) if extra and not cond else ''))
    ok = ok and bool(cond)


core = open(os.path.join(ROOT, 'web', 'src', '00_core.jsx'), encoding='utf-8').read()
m = re.search(r'const FLAG_RE = .*?\nfunction nameNoFlag\(name\) \{.*?\n\}', core, re.S)
check('helpers found in 00_core.jsx', m)
if m:
    js = m.group(0) + r'''
const flag = (cc) => String.fromCodePoint(...[...cc.toUpperCase()].map(c => 0x1F1E6 + c.charCodeAt(0) - 65));
const cases = [
  [flag('de') + 'GE10G', 'de', 'GE10G'],
  [flag('nl') + ' NE10G', 'nl', 'NE10G'],
  ['  ' + flag('fi') + 'FinBogart1G', 'fi', 'FinBogart1G'],
  [flag('eu') + ' Auto', 'eu', 'Auto'],
  ['VPS ' + flag('de'), '', 'VPS ' + flag('de')],      // the flag must lead the name
  ['Synology', '', 'Synology'],
  ['', '', ''],
  [flag('de'), 'de', flag('de')],                       // nothing but a flag: keep the name as it is
  ['D' + flag('e'), '', 'D' + flag('e')],               // one regional letter is not a flag
  ['/abh Гагра', 'abh', 'Гагра'],
  ['  /ABH   Сухум', 'abh', 'Сухум'],
  ['/abh', 'abh', '/abh'],                              // nothing but the code: keep the name as it is
  ['/abhazia дом', '', '/abhazia дом'],                 // a longer word is not the code
  ['/foo дом', '', '/foo дом'],                         // an unknown code stays part of the name
  ['Дом /abh', '', 'Дом /abh'],                         // the code must lead the name
];
let bad = 0;
for (const [name, cc, shown] of cases) {
  const a = flagOf(name), b = nameNoFlag(name, 'server');
  if (a !== cc || b !== shown) { bad++; console.log('MISMATCH', JSON.stringify(name), '->', a, JSON.stringify(b), 'expected', cc, JSON.stringify(shown)); }
}
if (nameNoFlag(flag('de') + 'NAS', 'nas') !== 'NAS') { bad++; console.log('MISMATCH: every kind loses the emoji'); }
console.log(bad ? 'BAD' : 'GOOD');
'''
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
    try:
        r = subprocess.run(['node', f.name], capture_output=True, text=True, timeout=30)
        check('flagOf / nameNoFlag on 15 names', r.stdout.strip().endswith('GOOD'), r.stdout + r.stderr)
    finally:
        os.remove(f.name)

fl = os.path.join(ROOT, 'web', 'flags')
files = {x[:-4] for x in os.listdir(fl) if x.endswith('.svg')} if os.path.isdir(fl) else set()
check('web/flags has the pictures', len(files) >= 250, len(files))
need = ['de', 'nl', 'fi', 'ru', 'us', 'gb', 'fr', 'se', 'pl', 'tr', 'ae', 'jp', 'kr', 'cn', 'hk', 'sg', 'in', 'br', 'ua', 'kz', 'by', 'ge', 'am', 'az', 'al', 'ee', 'lv', 'lt', 'cz', 'at', 'ch', 'it', 'es', 'ca', 'au', 'il', 'eu', 'ng', 'abh']
check('the usual VPS countries are there', not [c for c in need if c not in files], [c for c in need if c not in files])
bad = []
for c in files:
    t = open(os.path.join(fl, c + '.svg'), encoding='utf-8', errors='replace').read()
    if not t.lstrip().startswith('<svg') or re.search(r'<script|onload=|javascript:|<foreignObject|<!ENTITY', t, re.I):
        bad.append(c)
check('every picture is a plain SVG (no scripts)', not bad, bad)
check('licence file is there', os.path.isfile(os.path.join(fl, 'LICENSE.txt')))
check('Dockerfile copies web/flags', 'COPY web/flags' in open(os.path.join(ROOT, 'Dockerfile'), encoding='utf-8').read())
dep = os.path.join(os.path.dirname(ROOT), 'racklive_deploy.py')
if os.path.isfile(dep):
    check('deploy list has web/flags', "'web/flags'" in open(dep, encoding='utf-8').read())
css = open(os.path.join(ROOT, 'web', 'styles.css'), encoding='utf-8').read()
check('styles for .kind-flag (own class, not squeezed by «Test»)', '.kind-flag img' in css and 'data-look="test"] .kind-flag' in css)
for f, needle in (('50_devices.jsx', 'nameNoFlag(d.name, d.kind)'), ('20_device.jsx', 'nameNoFlag(device.name'), ('65_tools.jsx', 'nameNoFlag(d.name'),
                  ('40_map.jsx', 'nameNoFlag(n.label, n.kind)'), ('40_map.jsx', "'/flags/' + cc + '.svg'"), ('52_clients.jsx', 'name={c.name}'), ('40_map.jsx', 'const cc = flagOf(n.label)')):
    check('used in ' + f + ' (' + needle[:24] + ')', needle in open(os.path.join(ROOT, 'web', 'src', f), encoding='utf-8').read())
dev = open(os.path.join(ROOT, 'web', 'src', '20_device.jsx'), encoding='utf-8').read()
check('no empty «Вид» panel: only an «Добавить вид» button without a photo / model', 'Добавить вид' in dev and 'Нет фото и 3D-модели' not in dev)
print('\nВСЁ OK' if ok else '\nЕСТЬ ОШИБКИ')
sys.exit(0 if ok else 1)
