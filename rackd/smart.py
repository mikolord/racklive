"""Disk health (S.M.A.R.T.) for Synology and servers over SSH: model, size, temperature, hours, wear of SSD / NVMe, bad sectors, last self-test — and a plain-words verdict.

smartctl is read as TEXT (`-a`): the 6.x version on Synology has no JSON. Reading does not wake or load a disk noticeably.
A self-test (short ~2 min, extended hours) runs inside the disk and the disk stays usable; the result appears in its log afterwards."""
import re, time

SCRIPT = r'''
export PATH=$PATH:/usr/local/bin:/usr/syno/bin:/usr/syno/sbin:/usr/sbin:/sbin
command -v smartctl >/dev/null 2>&1 || { echo "@@nosmart"; exit 0; }
S="smartctl"; $S --version >/dev/null 2>&1 || S="sudo -n smartctl"
echo "@@version $($S --version 2>&1 | head -1)"
for d in $(ls /dev/sd? /dev/hd? /dev/nvme?n1 2>/dev/null); do
  echo "@@disk $d"
  case "$d" in
    /dev/nvme*) out=$($S -a $d 2>&1) ;;
    *) out=$($S -a -d sat $d 2>&1); echo "$out" | grep -q -E "Device Model|Model Number" || out=$($S -a $d 2>&1) ;;
  esac
  echo "$out"
done
echo "@@end"
'''

NAMES_LIFE = ('Wear_Leveling_Count', 'SSD_Life_Left', 'Media_Wearout_Indicator', 'Percent_Lifetime_Remain', 'Remaining_Lifetime_Perc', 'Perc_Rated_Life_Used', 'Lifetime_Remaining')


def test_script(dev, kind):
    """command that starts a self-test: short (~2 min) or extended (hours)"""
    if not re.match(r'^/dev/(sd[a-z]+|hd[a-z]+|nvme\d+n\d+)$', dev or ''):
        raise ValueError('неверное имя диска')
    t = 'long' if kind == 'long' else 'short'
    a = '' if 'nvme' in dev else '-d sat '
    return ('export PATH=$PATH:/usr/local/bin:/usr/syno/bin:/usr/syno/sbin:/usr/sbin:/sbin\nS=smartctl; $S --version >/dev/null 2>&1 || S="sudo -n smartctl"\n'
            f'$S -t {t} {a}{dev} 2>&1 | grep -E "Testing has begun|Please wait|aborted|not supported|failed|Failed|error" | head -4')


def _int(s):
    m = re.match(r'\s*([\d,]+)', str(s or ''))
    return int(m.group(1).replace(',', '')) if m else None


def parse_disk(dev, text):
    d = {'dev': dev, 'model': '', 'family': '', 'serial': '', 'sizeBytes': None, 'kind': 'hdd', 'rpm': None, 'health': 'UNKNOWN', 'temp': None, 'hours': None, 'attrs': [],
         'realloc': None, 'pending': None, 'uncorrectable': None, 'crc': None, 'lifeLeft': None, 'spare': None, 'written': None, 'selftest': None, 'testRunning': None, 'readable': False}
    for l in text.splitlines():
        k, _, v = l.partition(':')
        k, v = k.strip(), v.strip()
        if k == 'Model Family':
            d['family'] = v
        elif k in ('Device Model', 'Model Number', 'Product'):
            d['model'] = v if k != 'Product' or not d['model'] else d['model']
        elif k == 'Serial Number' or k == 'Serial number':
            d['serial'] = v
        elif k in ('User Capacity', 'Total NVM Capacity'):
            m = re.search(r'([\d,]+)\s*(?:bytes)?', v)
            d['sizeBytes'] = int(m.group(1).replace(',', '')) if m else None
        elif k == 'Rotation Rate':
            if 'Solid State' in v:
                d['kind'] = 'ssd'
            else:
                d['rpm'] = _int(v)
        elif k == 'SMART overall-health self-assessment test result':
            d['health'] = re.sub(r'[^A-Z]', '', v.split()[0].upper()) if v else 'UNKNOWN'
        elif k == 'SMART Health Status':
            d['health'] = 'PASSED' if v.upper() == 'OK' else v.upper()
        # NVMe block
        elif k == 'Percentage Used':
            d['lifeLeft'] = max(0, 100 - (_int(v) or 0)); d['kind'] = 'nvme'
        elif k == 'Available Spare':
            d['spare'] = _int(v)
        elif k == 'Temperature' and 'Celsius' in v and d['temp'] is None:
            d['temp'] = _int(v)
        elif k == 'Power On Hours' and d['hours'] is None:
            d['hours'] = _int(v)
        elif k == 'Data Units Written':
            m = re.search(r'\[([\d.]+)\s*(TB|GB|PB)\]', v)
            d['written'] = f'{m.group(1)} {m.group(2)}' if m else None
        elif k == 'Media and Data Integrity Errors':
            d['uncorrectable'] = _int(v)
        elif k == 'Self-test execution status':
            if 'in progress' in v:
                d['testRunning'] = 'идёт'
        m = re.match(r'\s*(\d+)\s+% of test remaining', l) or re.match(r'\s*(\d+)%\s+of test remaining', l)
        if m and d['testRunning']:
            d['testRunning'] = f'идёт, осталось {m.group(1)}%'
    for l in text.splitlines():
        m = re.match(r'\s*(\d+)\s+([A-Za-z_0-9\-]+)\s+0x[0-9a-f]+\s+(\d+)\s+(\d+)\s+(\d+)\s+\S+\s+\S+\s+\S+\s+(.*)$', l)
        if not m:
            continue
        aid, name, val, worst, thr, raw = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), m.group(6).strip()
        rawn = _int(raw) or 0
        d['attrs'].append({'id': aid, 'name': name, 'value': val, 'worst': worst, 'thresh': thr, 'raw': raw})
        d['readable'] = True
        if aid == 5:
            d['realloc'] = rawn
        elif aid == 197:
            d['pending'] = rawn
        elif aid == 198:
            d['uncorrectable'] = rawn
        elif aid == 199:
            d['crc'] = rawn
        elif aid in (194, 190) and (d['temp'] is None or aid == 194):
            d['temp'] = _int(raw) if aid == 194 else (d['temp'] if d['temp'] is not None else _int(raw))
        elif aid == 9 and d['hours'] is None:
            d['hours'] = rawn
        elif name in NAMES_LIFE and d['lifeLeft'] is None:
            d['lifeLeft'] = (100 - val) if name == 'Perc_Rated_Life_Used' else min(100, val)
            d['kind'] = 'ssd'
        elif name in ('Total_LBAs_Written', 'Host_Writes_32MiB') and d['written'] is None:
            d['written'] = None
    if d['kind'] == 'nvme' or 'nvme' in dev:
        d['readable'] = d['readable'] or d['temp'] is not None or d['health'] in ('PASSED', 'FAILED')
    # last self-test line:  «# 1  Short offline  Completed without error  00%  12345  -»
    for l in text.splitlines():
        m = re.match(r'#\s*1\s+(.+?)\s{2,}(.+?)\s{2,}(\d+)%\s+(\d+)\s+(\S+)', l)
        if m:
            d['selftest'] = {'type': m.group(1).strip(), 'result': m.group(2).strip(), 'hours': int(m.group(4)), 'ok': 'without error' in m.group(2) or 'Completed' == m.group(2).strip()}
            break
    if d['readable'] is False and d['health'] in ('PASSED', 'FAILED'):
        d['readable'] = True
    d['verdict'], d['reasons'] = verdict(d)
    return d


def verdict(d):
    """→ ('good' | 'warn' | 'bad' | 'unknown', [plain reasons])"""
    bad, warn, ok = [], [], []
    if d['health'] == 'FAILED':
        bad.append('Диск сам сообщает, что неисправен (SMART: FAILED). Срочно сделайте копию данных и замените диск.')
    if d.get('pending'):
        bad.append(f"{d['pending']} секторов ждут переназначения — диск не может их прочитать. Это частый предвестник отказа: сделайте копию данных.")
    if d.get('uncorrectable') and d['kind'] != 'nvme':
        bad.append(f"{d['uncorrectable']} неисправимых ошибок чтения. Диск ненадёжен.")
    if d.get('uncorrectable') and d['kind'] == 'nvme':
        bad.append(f"{d['uncorrectable']} ошибок целостности данных. Диск ненадёжен.")
    if d.get('realloc'):
        (bad if d['realloc'] >= 10 else warn).append(f"{d['realloc']} секторов уже заменены запасными. " + ('Их становится много — планируйте замену диска.' if d['realloc'] >= 10 else 'Пока немного; следите, не растёт ли число.'))
    if d.get('crc'):
        if d['crc'] >= 10:
            warn.append(f"{d['crc']} ошибок передачи по кабелю (CRC) — проверьте SATA-кабель и разъём; сам диск может быть исправен.")
        else:
            ok.append(f"Единичные ошибки передачи по кабелю (CRC): {d['crc']} — не страшно, если число не растёт")
    if d.get('lifeLeft') is not None:
        if d['lifeLeft'] <= 10:
            bad.append(f"Ресурс SSD почти исчерпан: осталось {d['lifeLeft']}%. Замените накопитель.")
        elif d['lifeLeft'] <= 30:
            warn.append(f"Ресурс SSD: осталось {d['lifeLeft']}%. Присмотритесь к замене.")
        else:
            ok.append(f"Ресурс SSD: осталось {d['lifeLeft']}%")
    if d.get('spare') is not None and d['spare'] < 10:
        bad.append(f"Запас ячеек NVMe на исходе ({d['spare']}%).")
    t = d.get('temp')
    if t is not None:
        hot = 70 if d['kind'] in ('ssd', 'nvme') else 55
        if t >= hot:
            warn.append(f'Температура {t} °C — слишком горячо, проверьте охлаждение.')
    st = d.get('selftest')
    if st and not st['ok'] and 'progress' not in st['result'].lower():
        bad.append(f"Последний самотест завершился ошибкой: {st['result']}.")
    # a drive that reports less space than its own model name promises (Seagate «ST3000…» = 3 TB)
    m = re.match(r'ST(\d{3,5})[A-Z]', d.get('model') or '')
    if m and d.get('sizeBytes'):
        want = int(m.group(1)) * 1e9
        if d['sizeBytes'] < want * .7:
            bad.append(f"По названию модели это диск на ~{int(m.group(1)) // 1000 if int(m.group(1)) >= 1000 else int(m.group(1))} {'ТБ' if int(m.group(1)) >= 1000 else 'ГБ'}, а диск показывает только {round(d['sizeBytes'] / 1e9)} ГБ — так ведёт себя неисправный диск.")
    if not d['readable'] or d['health'] == 'UNKNOWN':
        if not bad:
            warn.append('Диск не отдаёт данные SMART (или здоровье «UNKNOWN»). Возможно, он за RAID-контроллером или USB-переходником — либо неисправен.')
        else:
            bad.append('SMART у этого диска прочитать не удаётся.')
    if bad:
        return 'bad', bad + warn
    if warn:
        return ('unknown' if not d['readable'] and len(warn) == 1 else 'warn'), warn
    if d['health'] == 'PASSED':
        ok.insert(0, 'SMART: исправен, плохих секторов нет' if d['kind'] == 'hdd' else 'SMART: исправен')
        return 'good', ok
    return 'unknown', ['Состояние неизвестно']


def parse(out):
    """script output → {'smartctl': bool, 'disks': [...]}"""
    if '@@nosmart' in out:
        return {'smartctl': False, 'disks': [], 'error': 'на устройстве нет smartctl (пакет smartmontools)'}
    disks, cur, buf = [], None, []
    for l in out.splitlines():
        if l.startswith('@@disk '):
            if cur:
                disks.append(parse_disk(cur, '\n'.join(buf)))
            cur, buf = l[7:].strip(), []
        elif l.startswith('@@end'):
            break
        elif cur:
            buf.append(l)
    if cur:
        disks.append(parse_disk(cur, '\n'.join(buf)))
    # a bay / USB stick that reported nothing at all is not a disk
    disks = [d for d in disks if d['model'] or d['readable']]
    order = {'bad': 0, 'warn': 1, 'unknown': 2, 'good': 3}
    disks.sort(key=lambda d: (order.get(d['verdict'], 9), d['dev']))
    return {'smartctl': True, 'disks': disks, 'at': time.time()}


def demo():
    base = lambda **k: dict({'family': '', 'serial': 'DEMO0001', 'rpm': 7200, 'attrs': [], 'realloc': 0, 'pending': 0, 'uncorrectable': 0, 'crc': 0, 'lifeLeft': None, 'spare': None, 'written': None,
                             'selftest': {'type': 'Short offline', 'result': 'Completed without error', 'hours': 5000, 'ok': True}, 'testRunning': None, 'readable': True, 'health': 'PASSED', 'kind': 'hdd'}, **k)
    ds = [base(dev='/dev/sda', model='ST4000VN006-3CW104', family='Seagate IronWolf', sizeBytes=4000787030016, temp=34, hours=18250),
          base(dev='/dev/sdb', model='WDC WD40EFRX-68N32N0', family='WD Red', sizeBytes=4000787030016, temp=41, hours=36100, realloc=3, crc=0),
          base(dev='/dev/sdc', model='ST3000VX010-2H916L', family='Seagate Skyhawk', sizeBytes=137438952960, temp=38, hours=29800, pending=8, health='UNKNOWN'),
          base(dev='/dev/nvme0n1', model='Samsung SSD 980 PRO 1TB', sizeBytes=1000204886016, kind='nvme', rpm=None, temp=39, hours=4200, lifeLeft=94, spare=100, written='38.4 TB')]
    for d in ds:
        d['verdict'], d['reasons'] = verdict(d)
    ds.sort(key=lambda d: ({'bad': 0, 'warn': 1, 'unknown': 2, 'good': 3}.get(d['verdict'], 9), d['dev']))
    return {'smartctl': True, 'disks': ds, 'at': time.time()}
