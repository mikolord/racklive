#!/usr/bin/env python3
"""S.M.A.R.T.: the text parser and the verdicts, on output shaped like smartctl 6.x / 7.x.
    python tools/smart_test.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import smart  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


HDD = '''=== START OF INFORMATION SECTION ===
Model Family:     Seagate IronWolf
Device Model:     ST2000VN004-2E4164
Serial Number:    Z52C2VNA
User Capacity:    2,000,398,934,016 bytes [2.00 TB]
Rotation Rate:    5900 rpm
=== START OF READ SMART DATA SECTION ===
SMART overall-health self-assessment test result: PASSED
Self-test execution status:      (   0)	The previous self-test routine completed without error or no self-test has ever been run.
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  1 Raw_Read_Error_Rate     0x000f   082   064   044    Pre-fail  Always       -       169906480
  5 Reallocated_Sector_Ct   0x0033   100   100   010    Pre-fail  Always       -       0
  9 Power_On_Hours          0x0032   072   072   000    Old_age   Always       -       24840
194 Temperature_Celsius     0x0022   028   040   000    Old_age   Always       -       28 (0 18 0 0 0)
197 Current_Pending_Sector  0x0012   100   100   000    Old_age   Always       -       0
198 Offline_Uncorrectable   0x0010   100   100   000    Old_age   Offline      -       0
199 UDMA_CRC_Error_Count    0x003e   200   200   000    Old_age   Always       -       1
SMART Self-test log structure revision number 1
Num  Test_Description    Status                  Remaining  LifeTime(hours)  LBA_of_first_error
# 1  Short offline       Completed without error       00%     24800         -
'''
d = smart.parse_disk('/dev/sdd', HDD)
check('HDD: model, size, kind, rpm, health, temperature, hours', d['model'] == 'ST2000VN004-2E4164' and d['sizeBytes'] == 2000398934016 and d['kind'] == 'hdd' and d['rpm'] == 5900 and d['health'] == 'PASSED' and d['temp'] == 28 and d['hours'] == 24840, d)
check('HDD: bad-sector counters read', (d['realloc'], d['pending'], d['uncorrectable'], d['crc']) == (0, 0, 0, 1))
check('HDD: one CRC error is not a warning', d['verdict'] == 'good', (d['verdict'], d['reasons']))
check('the last self-test is read', d['selftest'] and d['selftest']['ok'] and d['selftest']['type'] == 'Short offline', d['selftest'])
w = smart.parse_disk('/dev/sdd', HDD.replace('Always       -       0\n  9', 'Always       -       3\n  9'))
check('3 replaced sectors: attention, not alarm', w['verdict'] == 'warn' and w['realloc'] == 3, w['reasons'])
b = smart.parse_disk('/dev/sdd', HDD.replace('Always       -       0\n198', 'Always       -       8\n198'))
check('pending sectors: bad state with advice to copy the data', b['verdict'] == 'bad' and 'копию' in b['reasons'][0], b['reasons'])
f = smart.parse_disk('/dev/sdd', HDD.replace('PASSED', 'FAILED'))
check('SMART FAILED: bad', f['verdict'] == 'bad' and f['health'] == 'FAILED')
hot = smart.parse_disk('/dev/sdd', HDD.replace('28 (0 18 0 0 0)', '58 (0 18 0 0 0)'))
check('58 °C on a hard disk: attention', hot['verdict'] == 'warn' and any('Температура' in x for x in hot['reasons']))

SSD = HDD.replace('Rotation Rate:    5900 rpm', 'Rotation Rate:    Solid State Device').replace('Seagate IronWolf', 'Samsung').replace('ST2000VN004-2E4164', 'Samsung SSD 860 EVO 500GB') + '177 Wear_Leveling_Count     0x0013   018   018   000    Pre-fail  Always       -       1200\n'
s = smart.parse_disk('/dev/sda', SSD)
check('SATA SSD: wear from the normalised value (18% left → bad)', s['kind'] == 'ssd' and s['lifeLeft'] == 18 and s['verdict'] == 'warn', (s['lifeLeft'], s['verdict'], s['reasons']))
s2 = smart.parse_disk('/dev/sda', SSD.replace('018   018   000', '008   008   000'))
check('SATA SSD with 8% left: bad', s2['verdict'] == 'bad')

NVME = '''Model Number:                       Samsung SSD 980 1TB
Serial Number:                      S6B0NX0
Total NVM Capacity:                 1,000,204,886,016 [1.00 TB]
SMART overall-health self-assessment test result: PASSED
SMART/Health Information (NVMe Log 0x02)
Critical Warning:                   0x00
Temperature:                        38 Celsius
Available Spare:                    100%
Available Spare Threshold:          10%
Percentage Used:                    6%
Data Units Written:                 80,000,000 [40.9 TB]
Power On Hours:                     1,234
Media and Data Integrity Errors:    0
'''
n = smart.parse_disk('/dev/nvme0n1', NVME)
check('NVMe: temperature, hours, used → 94% left, written, healthy', n['kind'] == 'nvme' and n['temp'] == 38 and n['hours'] == 1234 and n['lifeLeft'] == 94 and n['written'] == '40.9 TB' and n['verdict'] == 'good', n)
n2 = smart.parse_disk('/dev/nvme0n1', NVME.replace('Percentage Used:                    6%', 'Percentage Used:                    96%'))
check('NVMe 96% used: bad', n2['verdict'] == 'bad')

odd = '''Model Family:     Seagate Skyhawk
Device Model:     ST3000VX010-2H916L
User Capacity:    137,438,952,960 bytes [137 GB]
Rotation Rate:    7200 rpm
SMART overall-health self-assessment test result: UNKNOWN!
Read SMART Data failed: scsi error badly formed scsi parameters
'''
o = smart.parse_disk('/dev/sdb', odd)
check('a 3 TB model that shows 137 GB: bad, with the reason in plain words', o['verdict'] == 'bad' and o['health'] == 'UNKNOWN' and any('137' in x for x in o['reasons']), o['reasons'])
run = smart.parse_disk('/dev/sdd', HDD.replace('(   0)	The previous self-test routine completed without error or no self-test has ever been run.', '( 249)	Self-test routine in progress...\n\t\t\t\t\t90% of test remaining.'))
check('a running self-test shows its progress', run['testRunning'] and '90' in run['testRunning'], run['testRunning'])

out = '@@version smartctl 6.5\n@@disk /dev/sdd\n' + HDD + '@@disk /dev/sdz\nSmartctl open device: failed\n@@end\n'
r = smart.parse(out)
check('parse(): a bay that reported nothing is not listed', r['smartctl'] and [x['dev'] for x in r['disks']] == ['/dev/sdd'], r['disks'])
check('no smartctl is said plainly', smart.parse('@@nosmart')['smartctl'] is False)
for bad in ('/dev/sda; rm -rf /', '/dev/sda1', 'sda', '/dev/../etc/passwd'):
    try:
        smart.test_script(bad, 'short'); check('test_script refuses ' + bad, False)
    except ValueError:
        check('test_script refuses ' + bad, True)
check('test_script: short and extended', '-t short' in smart.test_script('/dev/sda', 'short') and '-t long' in smart.test_script('/dev/sdb', 'long') and '-d sat' in smart.test_script('/dev/sda', 'short') and '-d sat' not in smart.test_script('/dev/nvme0n1', 'short'))
dm = smart.demo()
check('demo has a good, a warning and a bad disk', {x['verdict'] for x in dm['disks']} >= {'good', 'warn', 'bad'}, [x['verdict'] for x in dm['disks']])
print('\n' + ('ВСЁ OK' if not FAILS else 'ЕСТЬ ОШИБКИ: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
