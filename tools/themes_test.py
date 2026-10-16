#!/usr/bin/env python3
"""Custom looks: what is accepted, what is refused, and that a look which no longer fits is switched off by itself.
    python tools/themes_test.py      → «ВСЁ OK»"""
import io, json, os, shutil, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rackd import themes as th

FAILS = []
check = lambda name, ok, extra='': (print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else (' — ' + str(extra)[:260]))), None if ok else FAILS.append(name))


def zipof(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.writestr(k, v if isinstance(v, (bytes, str)) else json.dumps(v, ensure_ascii=False))
    return b.getvalue()


def good(**over):
    m = {'id': 'test-look', 'name': 'Тест', 'author': 'me', 'version': '1.0.0', 'api': th.THEME_API, 'base': 'graphite',
         'tokens': {'dark': {'--accent': '#38bdf8', '--bg': '#0b1220'}, 'light': {'--accent': '#0284c7'}, 'all': {'--r-lg': '22px'}},
         'css': 'theme.css', 'strings': {'tab.rack': 'Дом'}, 'icons': {'home': 'M3 11l9-8 9 8'}, 'kindColors': {'router': '#38bdf8'},
         'appIcons': {'rack': 'assets/a.svg'}, 'pwa': {'favicon': 'assets/a.svg'}}
    m.update(over)
    return m


SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#38bdf8"/></svg>'
CSS = 'html[data-theme-id="test-look"] .card { border-radius: 22px; background-image: url(assets/a.svg); }\n@media (max-width: 600px) { html[data-theme-id="test-look"] .btn { padding: 12px; } }'


def pack(m=None, css=CSS, extra=None):
    f = {'theme.json': m or good(), 'theme.css': css, 'assets/a.svg': SVG}
    f.update(extra or {})
    return zipof(f)


tmp = tempfile.mkdtemp()
try:
    T = th.Themes(tmp, os.path.join(ROOT, 'web'), '2.5.0')
    rep = T.install(pack())
    check('a good look is accepted and installed', rep['ok'] and not rep['errors'], rep)
    check('the look is listed as fitting', [t['id'] for t in T.list() if t['ok']] == ['test-look'])
    css = T.css('test-look')
    check('css: variables per theme and the rule, url rewritten to the look\'s own folder', 'html[data-theme-id="test-look"][data-theme="dark"]{' in css and '--accent:#38bdf8' in css
          and '--r-lg:22px' in css and 'url("/themes/test-look/assets/a.svg")' in css and '@media' in css, css[:300])
    d = T.data('test-look')
    T2 = T.validate(pack(good(tileArt={'stats': 'assets/a.svg'}, tileColors={'stats': '#abc'}, pwaFrank={'favicon': 'assets/a.svg'})))
    ok_av = T.validate(pack(good(frankAvatar='assets/f.svg'), extra={'assets/f.svg': SVG}))
    check('a Frank avatar picture is accepted', ok_av['ok'], ok_av)
    check('data for the app: texts, icons, colours of kinds, picture addresses', d and d['strings'] == {'tab.rack': 'Дом'} and 'home' in d['icons'] and d['kindColors']['router'] == '#38bdf8'
          and d['appIcons']['rack'] == '/themes/test-look/assets/a.svg', d)
    check('a picture of the look is served', T.asset('test-look', 'assets/a.svg') and T.asset('test-look', 'assets/a.svg')[1] == 'image/svg+xml')
    check('theme.json itself is not served as a file', T.asset('test-look', 'theme.json') is None)
    check('outside the look\'s folder is refused', T.asset('test-look', '../status.json') is None and T.asset('test-look', 'assets/../../status.json') is None)

    bad = lambda name, blob, word='': (lambda r: check(name, not r['ok'] and (not word or any(word in e for e in r['errors'])), r))(T.validate(blob))
    bad('not a zip', b'hello', 'zip')
    bad('a path going up out of the archive', zipof({'theme.json': good(), '../evil.css': 'x'}), 'путь')
    bad('a file type that is not allowed (.js)', zipof({'theme.json': good(), 'app.js': 'alert(1)'}), 'не разрешён')
    bad('an executable is not allowed', zipof({'theme.json': good(), 'x.exe': 'MZ'}), 'не разрешён')
    bad('no theme.json', zipof({'theme.css': CSS}), 'theme.json')
    bad('theme.json is not valid JSON', zipof({'theme.json': '{oops', 'theme.css': CSS}), 'не читается')
    bad('a reserved id', pack(good(id='classic')), 'зарезервирован')
    bad('an id with capital letters', pack(good(id='MyLook')), 'id')
    bad('a look made for another contract version (api)', pack(good(api=99)), 'api')
    bad('a look that needs a newer Rack Live (minVersion)', pack(good(minVersion='9.0.0')), 'minVersion')
    bad('a script inside an svg', pack(extra={'assets/a.svg': '<svg><script>alert(1)</script></svg>'}), 'скрипт')
    bad('an event handler inside an svg', pack(extra={'assets/a.svg': '<svg onload="x()"></svg>'}), 'скрипт')
    bad('an outside link inside an svg', pack(extra={'assets/a.svg': '<svg><image href="https://evil.example/x.png"/></svg>'}), 'внешни')
    bad('@import in css', pack(css='@import url(x.css);\n' + CSS), '@import')
    bad('a css rule that is not scoped to the look', pack(css='body { background: red; }'), 'начинаться')
    bad('a css rule scoped to another look', pack(css='html[data-theme-id="other"] .card { color: red; }'), 'начинаться')
    bad('an outside url() in css', pack(css='html[data-theme-id="test-look"] .card { background: url(https://evil.example/x.png); }'), 'url(')
    bad('a backslash escape in css', pack(css='html[data-theme-id="test-look"] .card { color: \\72 ed; }'), 'экранирование')
    bad('expression() in css', pack(css='html[data-theme-id="test-look"] .card { width: expression(alert(1)); }'), 'запрещённое')
    bad('a Frank avatar that is not in the archive', pack(good(frankAvatar='assets/none.svg')), 'frankAvatar')
    bad('a script inside the Frank avatar', pack(good(frankAvatar='assets/f.svg'), extra={'assets/f.svg': '<svg onload="x()"/>'}), 'скрипт')
    ok_t = T.validate(pack(good(tileArt={'stats': 'assets/a.svg'}, tileColors={'stats': '#33b6ff'}, pwaFrank={'favicon': 'assets/a.svg'}, pwaSpeed={'favicon': 'assets/a.svg'})))
    check('a tile picture, a tile colour and the home-screen pictures of Frank and the speed test are accepted', ok_t['ok'] and not ok_t['warnings'], ok_t)
    bad('a tile picture that is not in the archive', pack(good(tileArt={'stats': 'assets/none.svg'})), 'не найден')
    bad('a bad tile colour', pack(good(tileColors={'stats': 'url(x)'})), 'цвет')
    bad('a script inside a tile picture', pack(good(tileArt={'stats': 'assets/t.svg'}), extra={'assets/t.svg': '<svg><script>x</script></svg>'}), 'скрипт')
    bad('a missing picture', pack(good(appIcons={'rack': 'assets/none.svg'})), 'не найден')
    bad('a bad token value (url)', pack(good(tokens={'dark': {'--bg': 'url(x)'}})), 'недопустимое')
    bad('a bad icon path', pack(good(icons={'home': '<script>'})), 'путь SVG')
    bad('a css file that is not in the archive', zipof({'theme.json': good()}), 'css')
    big = pack(css='html[data-theme-id="test-look"] .card { color: red; }\n' + '/* ' + 'x' * (th.MAX_CSS + 10) + ' */')
    bad('css that is too big', big, 'большой')

    r = T.validate(pack(good(tokens={'dark': {'--nope': '#fff'}}, strings={'no.such.key': 'x'}, icons={'nosuchicon': 'M0 0L1 1'}, kindColors={'toaster': '#fff'}),
                        css='html[data-theme-id="test-look"] .some-unlisted-class { color: red; }\nhtml[data-theme-id="test-look"] .card { color: red; }'))
    check('unknown names are only warnings (they are ignored): token, text, icon, kind, class', r['ok'] and len(r['warnings']) >= 5, r)
    r = T.validate(zipof({'my-folder/theme.json': good(), 'my-folder/theme.css': CSS, 'my-folder/assets/a.svg': SVG}))
    check('a single top folder inside the archive is fine', r['ok'], r)
    check('the starter template passes the checks', T.validate(T.template_zip())['ok'], T.validate(T.template_zip()))

    ex = os.path.join(ROOT, 'docs', 'themes', 'ocean-night.zip')
    if os.path.exists(ex):
        r = T.validate(open(ex, 'rb').read())
        check('the example look in docs/themes passes the checks with no errors and no warnings', r['ok'] and not r['warnings'], r)

    # ── after an update: the contract changes → the look is switched off by itself, with the reason; back when it fits again ──
    check('start: the look is fine', T.recheck() == [] and T.status['test-look']['ok'])
    th.THEME_API = th.THEME_API + 1
    broke = T.recheck()
    check('after the contract version goes up: the look is reported and switched off', len(broke) == 1 and broke[0][0] == 'test-look' and 'api' in broke[0][2][0], broke)
    check('a switched-off look gives no css, no data, no files', 'switched off' in T.css('test-look') and T.data('test-look') is None and T.asset('test-look', 'assets/a.svg') is None
          and T.all_css() == '' and not T.list()[0]['ok'] and T.list()[0]['problems'])
    check('it is reported once (not on every start)', T.recheck() == [])
    th.THEME_API = th.THEME_API - 1
    check('and it comes back when the versions match again', T.recheck() == [] and T.status['test-look']['ok'] and T.data('test-look'))
    th.Themes.version = '2.5.0'

    # ── the instruction for authors is complete: every text, icon, token and step is in it ──
    g = T.guide_text(); dfl = T.defaults()
    missing = [k for k in list(dfl['strings']) + dfl['icons'] + list(th.TOKENS) + dfl['tourSteps'] if k not in g]
    check('the guide mentions ports, hints, Frank, tiles and the three home-screen pictures', all(w in g for w in ('--faceplate-bg', '--port-g', '--hint-bg', '--frank-iris-1', 'frankAvatar', '.faceplate', 'tileArt', 'tileColors', 'pwaFrank', 'pwaSpeed', '--tile-ic-bg')) and 'stats' in g.split('8в.')[1])
    check('the guide lists every text key, icon, variable and tour step', not missing and len(dfl['icons']) > 50 and len(dfl['strings']) > 30, missing[:8])
    check('the guide has the rules a neural network needs (scope, forbidden, limits, checklist)', all(w in g for w in ('html[data-theme-id=', 'ЗАПРЕЩЕНО', 'ЧЕК-ЛИСТ', 'api', 'zip')))
    check('removing a look deletes its files', T.remove('test-look') and not os.path.exists(os.path.join(tmp, 'themes', 'test-look')) and not T.list())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('\nОШИБКИ: ' + ', '.join(FAILS) if FAILS else '\nВСЁ OK')
sys.exit(1 if FAILS else 0)
