"""The «Аврора» look is wired everywhere it must be: the list of looks, the first-paint script, the reserved ids, the CSS block and the six dot icons.   python tools/aurora_test.py"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda *p: open(os.path.join(ROOT, *p), encoding='utf-8').read()
look, html, css, themes = rd('web', 'src', '62_look.jsx'), rd('web', 'index.html'), rd('web', 'styles.css'), rd('rackd', 'themes.py')
bad = 0
def check(name, ok):
    global bad
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok:
        bad += 1
check('listed among the looks with a name', "id: 'aurora', name: 'Аврора'" in look)
check('counted as built-in (no download of a custom theme)', re.search(r"BUILTIN_SKINS = \[[^\]]*'aurora'", look) is not None)
check('applyLook sets data-look and no data-skin (it sits on the «Стекло» base)', "skin !== 'classic' && skin !== 'aurora'" in look and "data-look', 'aurora'" in look)
check('the first-paint script knows it, and ?skin=aurora works', "sk==='aurora'" in html and 'test|aurora' in html)
check('a custom look cannot take the id', "'aurora'" in re.search(r'RESERVED = \{[^}]*\}', themes).group(0))
check('the cover is drawn', "id === 'aurora'" in look)
check('the CSS block is there: both themes, sidebar, phone dock', all(s in css for s in ('html[data-look="aurora"][data-theme="dark"] {', 'html[data-look="aurora"][data-theme="light"] {',
      '@media (min-width: 1000px)', '--au-side', 'html[data-look="aurora"] .au-dock', 'html[data-look="aurora"] .au-circle')))
app = rd('web', 'src', '90_app.jsx')
check('phone: a round button + a capsule on top, a small dock with two round buttons below', 'function AuTop(' in app and 'function AuDock(' in app and '<AuDock ' in app and '<AuTop ' in app)
check('glass only on the navigation layer: the cards have no blur', 'html[data-look="aurora"] .card, html[data-look="aurora"] .wg-in { background: var(--card); border: 0; border-radius: var(--r-lg); box-shadow: var(--shadow); backdrop-filter: none' in css)
check('PC sidebar: the same line icons as the phone, no dot-matrix masks', 'html[data-look="aurora"] .topbar .tab svg { width: 20px' in css and 'mask-image' not in css.split('«Аврора» (data-look="aurora")')[1])
dev, rack = rd('web', 'src', '20_device.jsx'), rd('web', 'src', '30_rack.jsx')
check('every feature of «Витрина» (3D rack, device picture, instruments) is on for «Аврора» too', "const isRichLook = () => ['test', 'aurora']" in dev and 'isRichLook() && r3' in rack and 'isTestLook()' not in rack)
check('the shell of «Витрина» (burger + side menu) stays its own', "isTestLook() ? <button type=\"button\" className=\"tl-burger\"" in rd('web', 'src', '90_app.jsx'))
check('colourless icons: settings / tools / widgets, kinds monochrome, Frank a line icon', ':is(.set-ic, .tool-ic, .wg-opt-ic' in css.split('«Аврора»')[1] and "['test', 'aurora'].includes" in rd('web', 'src', '00_core.jsx') and 'frank-mono' in rd('web', 'src', '57_ai.jsx'))
check('top-left button leads to the devices', "ssSet('rl_pending_tool', 'devices')" in rd('web', 'src', '90_app.jsx'))
check('map and plan full-screen under the glass, their own buttons moved clear of the top buttons and the dock', '--au-in-top' in css and 'html[data-look="aurora"] .page-full .plan-ctx { top: calc(var(--au-in-top)' in css)
check('map and plan buttons fold into one glass circle with a macOS-like «genie» animation', 'function AuTuck(' in app and "el.animate(frames" in app and 'html.au-tucked[data-look="aurora"]' in css and '<AuTuck />' in app)
check('the top-left button is «Назад» where a screen can go back (settings, tools, a house, the network of a house)', 'function useAuBackTop(' in rd('web', 'src', '00_core.jsx') and 'useAuBack(phone && !!open' in rd('web', 'src', '60_settings.jsx')
      and '<AuBack active={phone && !!open}' in rd('web', 'src', '65_tools.jsx') and '<AuBack fn={back} label="Все дома" />' in rd('web', 'src', '47_plan.jsx') and 'useAuBackTop()' in app)
check('the in-page back buttons are hidden in «Аврора» on a phone', '.au-inpage-back { display: none !important; }' in css and '.ios-nav .ios-back { visibility: hidden; }' in css)
check('the dock is alive: a sliding lens, shrinking on scroll', 'au-lens' in app and "'au-dock' + (mini && !arr ? ' mini' : '')" in app and '.au-dock.mini' in css)
check('liquid glass in every menu, window and panel', ':is(.modal, .sheet, .hdr-menu, .toast, .wm-panel' in css and '--au-menu' in css)
ai, dash, speed = rd('web', 'src', '57_ai.jsx'), rd('web', 'src', '92_dashboard.jsx'), rd('web', 'src', '55_speed.jsx')
check('Frank is a living line eye everywhere: the pupil in the system colour looks around, the eye blinks', 'function AuEye(' in ai and "isAurora()) return <span className=\"frank-mono\"" in ai
      and 'isAurora() ? <AuEye size={21} />' in dash and '<AuEye size={23} />' in app and '@keyframes ae-blink' in css and '.au-eye .ae-pupil { fill: var(--accent); }' in css)
check('the separate apps (Frank, speed, terminal, cards, plan) know the look too', all("sk==='aurora'" in rd('web', n) for n in ('frank.html', 'speed.html', 'terminal.html', 'cards.html', 'plan.html')))
check('icons of Settings / Tools and the like: the line in the system colour', '.hdr-row > svg) { color: var(--accent) !important; }' in css)
check('widgets in the iOS manner, not the instruments of «Витрина»: batteries as rings, the rack tile, no lamp / radar / ruler',
      'function AuUps(' in dash and 'function AuRing(' in dash and 'AU_TILE_ART' in dash and "if (size === 'S' && isTestLook()) body = <TestTile" in dash
      and 'if (isTestLook()) return <StatsInstr />' in dash and 'isTestLook() ? <NewDevInstr />' in dash)
check('squares drawn whole (iOS + UniFi): UPS as iOS Batteries, Frank advice as a notification stack, new devices as UniFi clients',
      all(s in dash for s in ('function AuUpsTile(', 'function AuAdviceTile(', 'function AuNewTile(', "className={'wg-tile au-w au-w-' + w.type}")) and '.auw-stack.n3::before' in css)
check('UPS square: the iPhone status-bar battery (body, nub, fill, number inside), not a ring; «Сводка» as a notification; new devices: iPhone / Android / laptop take turns',
      'function AuBattery(' in dash and '<AuBattery u={u} />' in dash and 'function AuStatsTile(' in dash and 'stats: d => <AuStatsTile' in dash
      and 'function AuDevShow(' in dash and '@keyframes ads-cycle' in css and '.au-batt-nub' in css)
check('«Сводка»: notifications keep arriving — a new card drops from above, the older ones slide down into a stack; «Состояние сети»: the wall of «Витрина» in the Apple manner',
      'setK(v => v + 1)' in dash and '@keyframes auw-drop' in css and 'function AuWallTile(' in dash and 'state: d => <AuWallTile' in dash and '@keyframes aw-shine' in css and '@keyframes aw-fall' in css)
check('speed test: an iOS / macOS arc with a knob', 'function AuGauge(' in speed and 'if (isAurora()) return <AuGauge' in speed and '.aug-knob' in css)
check('the rack: its buttons in one menu in the system style', '<AuMenu label="Вид"' in rack and 'function AuMenu(' in rd('web', 'src', '00_core.jsx') and '.au-menu {' in css)
check('accent: the blue of «Витрина»', 'html[data-look="aurora"][data-theme="light"]:not([data-accent]) { --accent: #1f6feb; }' in css)
check('the shrunk dock shows the open side section (tools, settings) instead of an empty capsule', 'au-side-mini' in app and '.au-dock.mini .au-tabs > button.au-side-mini { width: 54px' in css)
check('a house / node card makes the dock and the «⋯» circle step down out of its way', ':has(.page-full :is(.live-card, .live-bar, .node-info, .plan-survey-card, .plan-testcard)) .au-dock { transform' in css
      and 'html[data-look="aurora"] .page-full :is(.live-card, .live-bar) { bottom: calc(env(safe-area-inset-bottom) + 12px)' in css)
check('no black strip under the iOS status bar on the map and the plan: the page takes the colour of their canvas', 'html[data-look="aurora"]:has(main.page-full) body' in css and ':has(.page-full .live-map) :is(body, .app-bg) { background: #1b1c20; }' in css)
check('no «notch» on the map and the plan: their canvas lies on the page (not fixed), no strip on top', 'au-sbar' not in app
      and 'html[data-look="aurora"] main.page.page-full { position: relative; padding: 0 !important; height: calc(var(--au-vh, 100dvh) + var(--au-shift, 0px))' in css
      and 'position: absolute; top: 0; bottom: 0; left: 0; right: 0; height: calc(var(--au-vh, 100dvh) + var(--au-shift, 0px)) !important; }' in css)
check('the canvas is exactly the visible height plus a reserve on top the page is scrolled by — the map shows under the clock, the bottom stays on screen',
      'function AuFullFit(' in app and "setProperty('--au-vh', innerHeight + 'px')" in app and 'window.scrollTo(0, shift)' in app and '<AuFullFit />' in app
      and "if (document.querySelector('main.page-full')) return;" in app and '66px + var(--au-shift, 0px))' in css)
check('the page is pinned at its reserve: when iOS moves it, it comes back (the house card never slides off the screen)',
      "addEventListener('scroll', pin, { passive: true })" in app and 'window.scrollTo(0, want)' in app and "addEventListener('pageshow', again)" in app
      and '.page-full :is(.live-card, .live-bar, .node-info, .plan-survey-card, .zoom-btns, .plan-edit-dock, .map-legend, .plan-hint) { position: fixed; }' in css)
check('one even column on the right: zoom buttons 46px at 16px like «⋯», «+» and the settings', '.page-full .zoom-btns { right: calc(env(safe-area-inset-right) + 16px)' in css and '.page-full .zoom-btns .btn { width: 46px; height: 46px; }' in css)
check('the «+» of the plan tools sits above the zoom buttons and folds into «⋯» too', '.plan-edit-dock), .wm-fab' in app and '.rack-jump, .plan-edit-dock),' in css and '.page-full .plan-edit-dock { right:' in css)
check('PC: invisible scrollbars', 'html[data-look="aurora"], html[data-look="aurora"] * { scrollbar-width: none; }' in css)
check('hold a widget like on an iPhone: a haptic tick, the home page goes into arranging; «Готово» leaves it',
      'function holdToArrange(' in dash and 'function haptic(' in dash and "i.setAttribute('switch', '')" in dash and "ctx.setMode('edit'); ctx.setArrange(true)" in dash
      and 'setArrange, setMode, theme' in app and '>Готово</Btn>' in dash)
check('the device show: iPhone in the system colour, Android, Surface (grey, blue screen, four squares), MacBook (grey screen, the apple)',
      'ads ads-d' in dash and 'AU_APPLE' in dash and '#00a4ef' in dash and '.ads-lid' in css and '.ads-d { animation-delay: 9s; }' in css)
check('less red and orange: «bad» is the system colour growing dim, the worst is grey; red only on the notification badges; pay buttons in the system colour',
      'html[data-look="aurora"][data-theme] { --red: #8e8e93;' in css and 'AU_DIM' in speed and "isAurora() ? (p >= 99.9 ? 'var(--accent)'" in rd('web', 'src', '49_uptime.jsx')
      and 'html[data-look="aurora"] .pay-row .btn { background: var(--accent)' in css)
check('note and pay squares in the system colour (no yellow paper), the pay list compact: one line, «Оплатить» and a round tick',
      'function AuNoteTile(' in dash and 'function AuPayTile(' in dash and '<AuPayTile data={d} />' in dash and 'className="pay-acts"' in dash
      and '.auw-cal' in css and 'html[data-look="aurora"] .mini-note' in css and '.pay-acts .pay-done' in css)
rack, core, ai = rd('web', 'src', '30_rack.jsx'), rd('web', 'src', '00_core.jsx'), rd('web', 'src', '57_ai.jsx')
check('2.51: the pay square rolls through the servers, the note is a ruled sheet in the system colour, VPN clients are faces like «Новые в сети»',
      "'auw-slide ' + cls" in dash and '@keyframes auw-in' in css and '.auw-dots i.on' in css and "'auw-paper'" in dash and '.auw-paper::after' in css and '#ffd60a' not in css.split('.auw-paper {')[1][:900]
      and 'function AuVpnTile(' in dash and '<AuVpnTile data={d} />' in dash and '.auw-face.more' in css and '.auw-live' in css)
check('2.51: arranging — a «+» tile last in the grid, «Готово» instead of the top row, «Как было» instead of «Инструменты», all of them animated',
      "'wg size-S wg-add ' + plus" in dash and "addEventListener('rl-dash-reset'" in dash and '.wg-add.in' in css and 'function useAuSwap(' in app and "new Event('rl-dash-reset')" in app
      and 'au-done au-sw' in app and 'html[data-look="aurora"] .au-sw.out' in css and 'main.au-arr > .hint-box' in css)
check('2.51: no hints under the rack, the places fold into one menu in the name of the place',
      "isAurora() ? null : <div className=\"r3-hint\">" in rd('web', 'src', '93_test_look.jsx') and 'cls="au-place"' in rack and "{!placeMenu && !embedded" in rack and '.au-menu.l' in css and "(left ? ' l' : '')" in core)
check('2.51: the main buttons play their icon on a press, the folded dock lives off the scroll',
      'const AU_FX = {' in app and "setAttribute('data-go', '1')" in app and all(f'@keyframes aufx-{k}' in css for k in ('spin', 'wiggle', 'ring', 'hop', 'fold', 'draw', 'blink', 'rev', 'dots', 'stack', 'nudge', 'back'))
      and "'--au-sv'" in app and "'--au-sp'" in app and 'var(--au-sp, 0) * 360deg' in css)
check('2.51: Frank inside the app is the PWA one (round buttons, a floating input) in liquid glass',
      "'ai-panel standalone' + (standalone ? '' : ' inapp')" in ai and 'className="ai-foot"' not in ai and 'html[data-look="aurora"] .fr-circle' in css and '.ai-panel.standalone.inapp' in css)
check('the «Сканер» app (QR cards) in the look: ?skin=aurora works there, system font instead of mono, the system colour instead of red / orange',
      all("skin=(classic|graphite|net|test|aurora)" in rd('web', n) for n in ('cards.html', 'frank.html', 'speed.html', 'terminal.html', 'plan.html'))
      and 'html[data-look="aurora"] .cd-sheet2' in css and '.vt-k { font-size: 13px' in css and "const flow = au ? 'var(--accent)'" in rd('web', 'src', '68_cards.jsx'))
srv, sysj, mod = rd('rackd', 'server.py'), rd('web', 'src', '63_system.jsx'), rd('web', 'modeler.html')
check('2.51: the look the admin picked is shared — the server keeps it and hands it to every page before the first paint',
      "path == '/api/look'" in srv and 'def look_script(' in srv and "b.replace(b'<head>', b'<head>\\n' + look_script(), 1)" in srv and 'window.RL_LOOK=L' in srv
      and 'const pushLook = ' in look and 'await pushLook()' in look and '!window.RL_LOOK' in app)
check('2.51: glass icons of the apps (Frank, speed test, terminal, plan, «Создать модель», Reck Controller) — files, manifests, first paint',
      all(os.path.isfile(os.path.join(ROOT, 'web', 'look-aurora', f'{a}{x}')) for a in ('frank', 'speed', 'terminal', 'plan', 'modeler', 'controller') for x in ('.svg', '-180.png', '-192.png', '-512.png'))
      and "APP_LOOK === 'aurora' ? APP_ICONS_A" in core and "'/look-aurora/{a}-{s}.png" in srv and "('look-aurora', 2) if server_look().get('skin') == 'aurora'" in srv
      and all(f"'/look-aurora/{a}-180.png?v={2 if a == 'modeler' else 3}'" in rd('web', a + '.html') and f"/{a}-manifest.json?skin=aurora" in rd('web', a + '.html') for a in ('frank', 'speed', 'terminal', 'plan', 'modeler'))
      and 'web/look-aurora' in rd('Dockerfile'))
check('2.51: «Создать модель» and the terminal app in the look (a glass back button and step capsule, switches, no borders)',
      "H.setAttribute('data-look','aurora')" in mod and 'html[data-look="aurora"] .tabs {' in mod and 'class="au-back"' in mod and 'input[type=checkbox]:checked::after' in mod
      and 'html[data-look="aurora"] .term-app-top {' in css)
check('2.51.1: one blue for all the app icons, the dock answers a press at once (the page is drawn in a transition), Frank without dots and with a delete button, a sleeping app picks the look up',
      "'#4aa8ff', '#0a52e8'" in rd('tools', 'aurora_icons.py') and "'#a18bff'" not in rd('tools', 'aurora_icons.py')
      and 'React.startTransition(() => setTabRaw(n))' in app and 'cur={dockCur}' in app
      and 'html[data-look="aurora"] .ai-panel.standalone { background: var(--bg) !important;' in css and 'radial-gradient' not in css.split('html[data-look="aurora"] .ai-panel.standalone {')[1].split('}')[0]
      and 'title="Удалить разговор" aria-label="Удалить разговор"' in rd('web', 'src', '57_ai.jsx')
      and "if path == '/api/look':" in srv and 'visibilitychange' in srv)
check('2.51.2: «План» — Wi-Fi devices are blue drop pins with a glowing coverage radius on the floor',
      'const WIFI_KINDS = {' in rd('web', 'src', '47_plan.jsx') and 'function PlanWifiRange' in rd('web', 'src', '47_plan.jsx') and 'className="pp-pin"' in rd('web', 'src', '47_plan.jsx')
      and 'id="plan-wifi-grad"' in rd('web', 'src', '47_plan.jsx') and '.plan-pin .pp-pin' in css and '.plan-wifi .pw-ring' in css)
check('2.51: settings — hints, folding notes, selects, sliders and the look picker restyled',
      all(x in css for x in ('html[data-look="aurora"] .hint-box {', 'html[data-look="aurora"] .guide > summary::after', 'html[data-look="aurora"] select:is(.input, .select)',
                             'html[data-look="aurora"] input[type="range"]:not(.plain)::-webkit-slider-thumb', 'html[data-look="aurora"] .look-skin.on {', 'html[data-look="aurora"] .apps-router')))
check('the other looks are untouched: «Test» still sets its own attribute', "if (skin === 'test') h.setAttribute('data-look', 'test')" in look)
print('BAD' if bad else 'GOOD')
sys.exit(1 if bad else 0)
