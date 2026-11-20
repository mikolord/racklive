"""Name tags: roles, IoT brands, aliases, catalogue and preserving the device name."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / 'web/src/01_brands.jsx').read_text(encoding='utf-8')
js = "const NAME_CODES = { abh: 'abh' };\n" + src[:src.index('function TagCatalog(')] + r'''
let bad = 0;
const check = (name, ok) => { console.log((ok ? 'OK   ' : 'FAIL ') + name); if (!ok) bad++; };
check('IoT role with Tuya and alias', tagBrand('/iot/tuya Розетка') === 'tuya' && tagRole('/iot/toya Розетка') === 'IOT');
check('standalone IoT icon and badge', tagBrand('/iot Датчик') === 'iot' && tagRole('/iot Датчик') === 'IOT' && nameNoTag('/iot Датчик') === 'Датчик');
check('old roles and brands', tagBrand('/ap/keenetic Кухня') === 'keenetic' && tagRole('/ap/keenetic Кухня') === 'AP');
check('subscriber shorthand', tagBrand('/ab Иван') === 'abon' && tagBrand('/cam Двор') === 'cam');
check('new brands have icons and tags', ['tapo','kasa','meross','switchbot','broadlink','govee','yeelight','nanoleaf','roborock','dreame','eufy','smartlife'].every(k => tagBrand('/iot/' + k + ' Устройство') === k && (BRANDS[k].d || BRANDS[k].t)));
check('search includes Russian aliases', tagSuggestions('/туя').items.some(i => i.key === 'tuya'));
check('suggestions include IoT role', tagSuggestions('/').roles.some(([r]) => r === 'iot'));
check('catalogue contains every canonical tag and country code', tagCatalogItems().length === Object.keys(BRANDS).length + Object.keys(NAME_CODES).length);
check('catalogue includes every alias under its brand', Object.entries(TAG_ALIAS).every(([a,k]) => a === k || tagCatalogItems().find(i => i.key === k)?.aliases.includes(a)));
check('catalogue search by slash alias', tagCatalogItems('/toya').some(i => i.key === 'tuya') && tagCatalogItems('умное').some(i => i.key === 'iot'));
check('plain name preserved', nameWithTag('Розетка у окна', 'tuya', 'iot') === '/iot/tuya Розетка у окна');
check('old brand and role replaced, name preserved', nameWithTag('/ap/keenetic Кухня', 'tuya', 'iot') === '/iot/tuya Кухня');
check('partial tag replaced', nameWithTag('/iot/tu', 'tuya', 'iot') === '/iot/tuya ');
check('country tag replaced without losing name', nameWithTag('/abh Гагра', 'tuya') === '/tuya Гагра');
check('unknown tag stays part of the name', nameWithTag('/zzzz Имя', 'tuya') === '/tuya /zzzz Имя');
console.log(bad ? 'BAD' : 'GOOD'); process.exitCode = bad ? 1 : 0;
'''
with tempfile.TemporaryDirectory(prefix='rl-brands-') as tmp:
    path = Path(tmp) / 'test.js'
    path.write_text(js, encoding='utf-8')
    result = subprocess.run(['node', str(path)], capture_output=True, text=True, encoding='utf-8', timeout=30)
    print(result.stdout + result.stderr)
    raise SystemExit(result.returncode)
