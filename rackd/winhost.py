"""Windows PC / server over SSH (the built-in OpenSSH server of Windows 10/11 and Server 2019+): PowerShell scripts and parsers.

Rack Live pipes a script into `powershell -NoProfile -Command -` over SSH and reads one line `@@json {…}` back. Nothing is installed on the computer — only the
optional Windows feature «OpenSSH Server» has to be on (see ENABLE_SSH, shown to the user).  Read-only: nothing here changes the computer except the explicit restart action."""
import json, re, time

REMOTE = 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command -'

PRELUDE = "$ErrorActionPreference='SilentlyContinue'\n$ProgressPreference='SilentlyContinue'\n[Console]::OutputEncoding=[Text.Encoding]::UTF8\n"

SETUP_SSH = r'''$ErrorActionPreference = 'Stop'
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
}
Set-Service sshd -StartupType Automatic
Start-Service sshd
$rule = 'RackLive-SSH-LAN'
if (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -Name $rule -Enabled True -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort 22 -RemoteAddress LocalSubnet
} else {
    New-NetFirewallRule -Name $rule -DisplayName 'Rack Live: SSH in LAN' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort 22 -RemoteAddress LocalSubnet | Out-Null
}
Get-Service sshd | Select-Object Status, StartType'''

WINDOWS_IDENTITY = r'''whoami
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
    Select-Object InterfaceAlias, IPAddress'''

SETUP_KEY = r'''$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:USERPROFILE '.ssh'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$key = Join-Path $dir 'racklive_rsa'
if (-not (Test-Path $key)) {
    $argsForKey = @('-q','-t','rsa','-b','3072','-N','""','-f',('"'+$key+'"'),'-C','RackLive')
    $p = Start-Process ssh-keygen.exe -ArgumentList $argsForKey -Wait -NoNewWindow -PassThru
    if ($p.ExitCode -ne 0) { throw 'SSH key generation failed' }
}
$file = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
$public = (Get-Content -LiteralPath ($key + '.pub') -Raw).Trim()
$previous = if (Test-Path $file) { [IO.File]::ReadAllText($file) } else { '' }
if (-not ($previous -split '\r?\n' | Where-Object { $_.Trim() -eq $public })) {
    [IO.File]::WriteAllText($file, $previous.TrimEnd() + "`r`n" + $public + "`r`n", [Text.Encoding]::ASCII)
}
icacls.exe $file /inheritance:r /grant '*S-1-5-18:F' '*S-1-5-32-544:F'
if ($LASTEXITCODE -ne 0) { throw 'Cannot set SSH key permissions' }'''

COPY_KEY = r'''Get-Content -LiteralPath (Join-Path $env:USERPROFILE '.ssh\racklive_rsa') -Raw | Set-Clipboard'''

ENABLE_SSH = {
    'title': 'Подключение Windows',
    'intro': 'Для ПК в одной локальной сети с Rack Live. Windows 10/11 или Windows Server; для состояния физических дисков нужен локальный администратор.',
    'steps': [
        {'title': 'Подготовь компьютер', 'text': 'На самом ПК открой Пуск → PowerShell → «Запуск от имени администратора». Скопируй и выполни весь блок. В конце должно быть Running и Automatic.',
         'code': SETUP_SSH, 'note': 'SSH разрешается только из локальной сети, в том числе если Windows считает её общедоступной. Порты на роутере открывать не нужно.'},
        {'title': 'Узнай логин и адрес ПК', 'text': 'В том же PowerShell выполни команду. Первая строка — логин; ниже выбери IPv4 подключения Ethernet или Wi-Fi к домашней сети.', 'code': WINDOWS_IDENTITY},
        {'title': 'Заполни поля ниже', 'fields': [
            ['Адрес', 'IPv4 компьютера из предыдущего шага'], ['Порт SSH', '22'],
            ['Пользователь Windows', 'логин из whoami; для локальной учётной записи можно только имя после обратного слеша'],
            ['Пароль', 'пароль учётной записи Windows, а не PIN Windows Hello']],
         'note': 'Пустой пароль не подходит. Если пароля нет или входишь только по PIN — раскрой «Вход по SSH-ключу» ниже.',
         'text': 'Нажми «Проверить». Если появились сведения о Windows — нажми «Сохранить». В списке устройств появятся CPU, память и диски.'},
    ],
    'key': {'title': 'Вход по SSH-ключу — без пароля Windows', 'steps': [
        {'title': 'Создай ключ и разреши вход', 'text': 'Выполни в PowerShell от имени администратора под той учётной записью, которую указываешь в Rack Live. Скрипт сохраняет отдельный ключ и добавляет его открытую часть; существующие ключи остаются.', 'code': SETUP_KEY},
        {'title': 'Скопируй приватный ключ в Rack Live', 'code': COPY_KEY,
         'text': 'Эта команда копирует ключ в буфер обмена. Вставь его целиком в поле «Приватный ключ (вместо пароля)», поле «Пароль» оставь пустым. Затем «Проверить» → «Сохранить».',
         'note': 'Приватный ключ даёт доступ к этому ПК. Вставляй его только в свою панель Rack Live; не отправляй в чат.'},
    ]},
    'troubleshoot': [
        ['Таймаут / нет соединения', 'Проверь, что ПК включён и адрес верный. Повтори шаг 1 с правами администратора: стандартное правило OpenSSH может работать только для частной сети.'],
        ['Неверный логин, пароль или ключ', 'Нужен пароль учётной записи, не PIN. Проверь логин через whoami или используй SSH-ключ.'],
        ['Нет состояния SSD / HDD', 'Для физических дисков нужны права локального администратора. Температуру и ресурс Windows отдаёт не для каждого диска.'],
    ],
    'source': 'https://learn.microsoft.com/windows-server/administration/openssh/openssh_install_firstuse',
}

POLL = PRELUDE + r'''$os=Get-CimInstance Win32_OperatingSystem
$cs=Get-CimInstance Win32_ComputerSystem
$cpu=@(Get-CimInstance Win32_Processor)
$load=($cpu|Measure-Object -Property LoadPercentage -Average).Average
$vols=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'|ForEach-Object{@{name=($_.DeviceID+' '+$_.VolumeName).Trim();total=[int64]$_.Size;free=[int64]$_.FreeSpace}})
$ips=@(Get-NetIPAddress -AddressFamily IPv4|Where-Object{$_.IPAddress -notmatch '^(127\.|169\.254)'}|ForEach-Object{$_.IPAddress})
$temp=$null
try{$t=Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop|Select-Object -First 1;if($t){$temp=[math]::Round($t.CurrentTemperature/10-273.15)}}catch{}
$docker=@()
if(Get-Command docker -ErrorAction SilentlyContinue){$docker=@(docker ps -a --format '{{.Names}}|{{.Status}}' 2>$null)}
$rb=(Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending')-or(Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
$o=@{host=$env:COMPUTERNAME;os=$os.Caption;build=$os.Version;cpuName=($cpu|Select-Object -First 1).Name;cores=($cpu|Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum;load=$load;memTotal=[int64]$os.TotalVisibleMemorySize;memFree=[int64]$os.FreePhysicalMemory;uptime=[int](New-TimeSpan -Start $os.LastBootUpTime -End (Get-Date)).TotalSeconds;vols=$vols;ips=$ips;temp=$temp;docker=$docker;reboot=[bool]$rb;model=$cs.Model;domain=$cs.Domain}
'@@json '+($o|ConvertTo-Json -Compress -Depth 4)
'''

DISKS = PRELUDE + r'''$list=@(Get-PhysicalDisk|ForEach-Object{$d=$_;$c=$d|Get-StorageReliabilityCounter;@{name=[string]$d.FriendlyName;serial=([string]$d.SerialNumber).Trim();media=[string]$d.MediaType;bus=[string]$d.BusType;health=[string]$d.HealthStatus;op=(@($d.OperationalStatus)-join ',');size=[int64]$d.Size;id=[string]$d.DeviceId;temp=$c.Temperature;wear=$c.Wear;hours=$c.PowerOnHours;readUnc=$c.ReadErrorsUncorrected;writeUnc=$c.WriteErrorsUncorrected}})
'@@json '+(@{disks=$list}|ConvertTo-Json -Compress -Depth 4)
'''

RESTART = PRELUDE + "shutdown /r /t 5 /c \"Rack Live: перезагрузка по запросу администратора\"\n'@@json {\"ok\":true}'\n"


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def payload(out):
    """the JSON object after `@@json ` (PowerShell may print warnings around it)"""
    for l in reversed(out.splitlines()):
        if l.startswith('@@json '):
            try:
                return json.loads(l[7:])
            except ValueError:
                break
    return None


def parse_poll(out, host):
    j = payload(out)
    if not isinstance(j, dict):
        tail = ' '.join(out.strip().splitlines()[-2:])[:160]
        raise ValueError('Windows ответил непонятно' + (f': {tail}' if tail else ''))
    mt, mf = j.get('memTotal') or 0, j.get('memFree') or 0
    mem = round(100 * (1 - mf / mt), 1) if mt else None
    vols = []
    for v in as_list(j.get('vols')):
        tot, free = v.get('total') or 0, v.get('free') or 0
        if tot > 0:
            used = tot - free
            vols.append({'name': v.get('name') or '?', 'status': 'normal' if used / tot < .95 else 'почти заполнен', 'used': used, 'total': tot})
    ips = [str(x) for x in as_list(j.get('ips'))]
    services = []
    for l in as_list(j.get('docker')):
        n, _, s = str(l).partition('|')
        if n:
            services.append({'name': n, 'state': s})
    status = 'online'
    if any(v['used'] / v['total'] > .95 for v in vols) or (mem or 0) > 95:
        status = 'warning'
    cpu = j.get('load')
    rows = [['ОС', f"{j.get('os') or 'Windows'} ({j.get('build') or '—'})"], ['Процессор', f"{(j.get('cpuName') or '—').strip()}"], ['Логических процессоров', str(j.get('cores') or '—')],
            ['Память', f"{round(mt / 1048576, 1)} ГБ" if mt else '—'], ['Модель', j.get('model') or '—'], ['Домен / группа', j.get('domain') or '—'],
            ['Адреса', ', '.join(ips[:4]) or '—'], ['Ожидает перезагрузки', 'да — после обновлений' if j.get('reboot') else 'нет'], ['Подключение', 'SSH (OpenSSH Windows), без агента']]
    return {'status': status,
            'summary': {'model': j.get('host') or '', 'fw': j.get('os') or 'Windows', 'uptime': j.get('uptime'), 'cpu': round(cpu, 1) if isinstance(cpu, (int, float)) else None, 'mem': mem,
                        'temp': j.get('temp'), 'ip': host},
            'metrics': [{'label': 'Перезагрузка', 'value': 'нужна' if j.get('reboot') else 'не нужна'}],
            'storage': {'volumes': vols, 'disks': []}, 'services': services,
            'sections': [{'title': 'Система', 'rows': rows}]}


def parse_disks(out):
    """→ the same shape as smart.parse: {'smartctl': True, 'disks': [...]} with Windows' own storage health (Get-PhysicalDisk + reliability counters)"""
    from . import smart
    j = payload(out)
    if not isinstance(j, dict):
        return {'smartctl': False, 'disks': [], 'error': 'Windows не отдал состояние дисков (нужен вход администратора)'}
    disks = []
    for x in as_list(j.get('disks')):
        media, bus = (x.get('media') or '').upper(), (x.get('bus') or '').upper()
        kind = 'nvme' if bus == 'NVME' else 'ssd' if media == 'SSD' else 'hdd'
        health = {'HEALTHY': 'PASSED', 'UNHEALTHY': 'FAILED', 'WARNING': 'PASSED'}.get((x.get('health') or '').upper(), 'UNKNOWN')
        wear = x.get('wear')
        d = {'dev': f"Диск {x.get('id')}", 'model': x.get('name') or '', 'family': '', 'serial': x.get('serial') or '', 'sizeBytes': x.get('size'), 'kind': kind, 'rpm': None, 'health': health,
             'temp': x.get('temp') if isinstance(x.get('temp'), (int, float)) and 0 < x['temp'] < 150 else None, 'hours': x.get('hours'), 'attrs': [], 'realloc': None, 'pending': None,
             'uncorrectable': (x.get('readUnc') or 0) + (x.get('writeUnc') or 0) or None, 'crc': None,
             'lifeLeft': max(0, 100 - wear) if isinstance(wear, (int, float)) and kind != 'hdd' else None, 'spare': None, 'written': None, 'selftest': None, 'testRunning': None,
             'readable': health != 'UNKNOWN'}
        d['verdict'], d['reasons'] = smart.verdict(d)
        if (x.get('health') or '').upper() == 'WARNING' and d['verdict'] == 'good':
            d['verdict'], d['reasons'] = 'warn', ['Windows считает состояние диска «Warning» (Get-PhysicalDisk). Проверьте диск в «Управлении дисками» и сделайте копию данных.']
        disks.append(d)
    order = {'bad': 0, 'warn': 1, 'unknown': 2, 'good': 3}
    disks.sort(key=lambda d: (order.get(d['verdict'], 9), d['dev']))
    return {'smartctl': True, 'disks': disks, 'at': time.time(), 'source': 'windows'}
