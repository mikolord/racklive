"""Rack Live desktop: managed TightVNC on Windows, noVNC in the browser, SSH transport.

VNC is loopback-only. A dedicated SSH key permits exactly that loopback port and
cannot run commands. Its host key is pinned from the authenticated setup channel.
Credentials live in private server data; only an authenticated viewer receives
the VNC password for its one-time connection.
"""
import base64
import json
import os
from pathlib import Path
import re
import secrets
import select
import socket
import subprocess
import threading
import time

from . import terminal, winhost
from .util import DriverError


def keendns(devices, apply=False):
    """Preserve same-origin headers for the single existing Rack Live proxy only.

    Never create forwarding rules or change ports, TLS, authentication or other
    proxies. Ambiguous discovery fails closed. Driver errors can contain secrets.
    """
    import ipaddress
    import shlex
    from urllib.parse import urlsplit
    from .drivers.keenetic import Keenetic

    def read(cli):
        raw = cli(['show running-config'])[0]['parse']['message']
        groups, current = [], None
        for line in raw.splitlines() if isinstance(raw, str) else raw:
            if not line.startswith((' ', '\t')):
                current = [line] if line.startswith('ip http proxy ') else None
                if current is not None:
                    groups.append(current)
            elif current is not None:
                current.append(line)
        return [g for g in groups if shlex.split(g[0]) == ['ip', 'http', 'proxy', 'racklive']
                and any('9998' in shlex.split(line) for line in g[1:])]

    def command(cli, text):
        response = cli([text])
        def accepted(item):
            status = item.get('parse', {}).get('status')
            return status == 'ok' or (isinstance(status, list) and bool(status)
                                     and all(s.get('status') in ('message', 'warning') for s in status))
        if not response or not all(accepted(r) for r in response):
            raise DriverError('Keenetic не подтвердил команду. Настройка не завершена.')

    matches = []
    incomplete = False
    for device in devices:
        if device.get('driver') != 'keenetic' or device.get('enabled') is False:
            continue
        try:
            host = device.get('host', '')
            if not ipaddress.ip_address(urlsplit(host if '://' in host else '//' + host).hostname).is_private:
                continue
        except ValueError:
            continue
        try:
            get, cli = Keenetic()._session(device)
            groups = read(cli)
            for group in groups:
                matches.append((get, cli, group))
        except Exception:
            incomplete = True
    if incomplete or len(matches) != 1:
        raise DriverError('Не удалось однозначно найти домашний Keenetic с правилом racklive на порт Rack Live. Проверь доступ к роутеру в устройствах; остальные правила не изменены.')
    get, cli, group = matches[0]
    try:
        proxy = get('/rci/show/ip/http/proxy').get('racklive', {})
        if not proxy.get('fqdn'):
            raise DriverError('Для существующего правила Rack Live не настроен домен KeenDNS.')
        flags = ('preserve-host', 'preserve-origin')
        present = {line.strip() for line in group[1:]}
        missing = [flag for flag in flags if flag not in present]
        if apply:
            changed = []
            try:
                for flag in missing:
                    command(cli, 'ip http proxy racklive ' + flag)
                    changed.append(flag)
                updated = read(cli)
                if len(updated) != 1 or not set(flags).issubset({s.strip() for s in updated[0][1:]}):
                    raise DriverError('Keenetic не подтвердил сохранение заголовков.')
                command(cli, 'system configuration save')
            except Exception:
                # Undo only flags introduced by this invocation.
                for flag in changed:
                    try:
                        command(cli, 'no ip http proxy racklive ' + flag)
                    except Exception:
                        pass
                try:
                    command(cli, 'system configuration save')
                except Exception:
                    pass
                raise DriverError('Настройка не завершена. Проверь правило Rack Live на Keenetic; повторная проверка покажет состояние.') from None
            missing = []
        return {'ok': True, 'ready': not missing, 'message':
                'Заголовки для доступа через KeenDNS настроены. Проверь подключение через домен.' if not missing else
                'Keenetic меняет заголовки сайта. Для рабочего стола через домен нужно сохранить Host и Origin.'}
    except DriverError:
        raise
    except Exception:
        raise DriverError('Не удалось проверить KeenDNS. Проверь доступ к домашнему роутеру.') from None

VERSION = '2.8.90'
URL = 'https://www.tightvnc.com/download/2.8.90/tightvnc-2.8.90-gpl-setup-64bit.msi'
SHA256 = '9693cb4cdc2e7e482e8e3f5890415b57ef87de3369fa5c337db516218a1170ce'
CARD = {'id': 'desktop', 'title': 'Рабочий стол Rack Live', 'icon': 'pc', 'kind': 'desktop',
        'description': 'Экран Windows, мышь и клавиатура прямо в браузере. TightVNC + noVNC, соединение через SSH. Без облачной учётной записи и проброса портов.',
        'home': 'https://novnc.com/', 'drivers': ['windows']}
PROBE = r'''$m=Join-Path $env:ProgramData 'RackLiveDesktop\owner.json'
$owner=$null
if(Test-Path -LiteralPath $m){try{$owner=Get-Content -LiteralPath $m -Raw|ConvertFrom-Json}catch{}}
$s=Get-Service tvnserver -ErrorAction SilentlyContinue
$app=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue|Where-Object{$_.DisplayName -like 'TightVNC*'}|Select-Object -First 1
$r=Get-ItemProperty 'HKLM:\SOFTWARE\TightVNC\Server' -ErrorAction SilentlyContinue
'@@json '+(@{present=[bool]($s -or $app);running=([string]$s.Status -eq 'Running');owner=$owner.owner;device=$owner.device;loopback=($r.LoopbackOnly -eq 1 -and $r.AllowLoopback -eq 1);httpOff=($r.AcceptHttpConnections -eq 0);captureCompatible=($null -ne $r.UseD3D -and $r.UseD3D -eq 0)}|ConvertTo-Json -Compress)
'''

def ps(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(device, script, timeout):
    """EncodedCommand executes multiline blocks as one script, not interactive stdin."""
    from .drivers.sshhost import SSHHost
    wrapped = "$ProgressPreference='SilentlyContinue'\n[Console]::OutputEncoding=[Text.Encoding]::UTF8\ntry {\n" + script + "\n} catch {\n'@@json '+(@{ok=$false;error=[string]$_.Exception.Message}|ConvertTo-Json -Compress)\n}\n"
    # Windows' default SSH shell is cmd.exe, whose command line is limited to
    # 8191 characters. Encode only a small bootstrap; read the actual script once.
    bootstrap = '[Console]::InputEncoding=[Text.Encoding]::UTF8; [Console]::OutputEncoding=[Text.Encoding]::UTF8; & ([ScriptBlock]::Create([Console]::In.ReadToEnd()))'
    remote = 'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand ' + base64.b64encode(bootstrap.encode('utf-16-le')).decode('ascii')
    return SSHHost()._run(device, wrapped, timeout=timeout, remote=remote)


def install_script(owner, device, password, public_key):
    """Fixed destination, verified download; preserve an existing unrelated install."""
    return r'''$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$owner=__OWNER__; $device=__DEVICE__
$dir=Join-Path $env:ProgramData 'RackLiveDesktop'
$mark=Join-Path $dir 'owner.json'
$old=$null
if(Test-Path -LiteralPath $mark){$old=Get-Content -LiteralPath $mark -Raw|ConvertFrom-Json}
$service=Get-Service tvnserver -ErrorAction SilentlyContinue
$package=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue|Where-Object{$_.DisplayName -like 'TightVNC*'}|Select-Object -First 1
if(($service -or $package) -and (-not $old -or $old.owner -ne $owner -or $old.device -ne $device)){throw 'An existing TightVNC installation is not managed by this Rack Live'}
if(-not [Environment]::Is64BitOperatingSystem){throw 'This plugin requires 64-bit Windows'}
if(-not $service -and (Get-NetTCPConnection -LocalPort 5900 -State Listen -ErrorAction SilentlyContinue)){throw 'Port 5900 is already occupied'}
New-Item -ItemType Directory -Force -Path $dir|Out-Null
& icacls.exe $dir /inheritance:r /grant '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if($LASTEXITCODE -ne 0){throw 'Cannot protect desktop helper directory'}
# A dedicated key can forward exactly one loopback port; it cannot run commands.
$peer=($env:SSH_CONNECTION -split ' ')[0]
if($peer -notmatch '^[0-9a-fA-F:.]+$'){throw 'SSH client address is unavailable'}
$comment='racklive-desktop-'+$owner+'-'+$device
$line='from="'+$peer+'",restrict,port-forwarding,permitopen="127.0.0.1:5900",command="echo Rack Live desktop tunnel only" '+__PUBLIC__+' '+$comment
$keys=Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
$before=if(Test-Path -LiteralPath $keys){[IO.File]::ReadAllText($keys)}else{''}
$keep=@($before -split '\r?\n'|Where-Object{$_ -and -not $_.EndsWith(' '+$comment)})
[IO.File]::WriteAllText($keys,($keep -join "`r`n")+"`r`n"+$line+"`r`n",[Text.Encoding]::ASCII)
& icacls.exe $keys /inheritance:r /grant '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
if($LASTEXITCODE -ne 0){throw 'Cannot protect SSH tunnel key'}
$hostKey=(Get-Content -LiteralPath (Join-Path $env:ProgramData 'ssh\ssh_host_ed25519_key.pub') -Raw).Trim()
$msi=Join-Path $dir 'tightvnc.msi'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -UseBasicParsing -Uri __URL__ -OutFile $msi
if((Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash.ToLower() -ne __HASH__){Remove-Item -LiteralPath $msi -Force;throw 'Installer SHA256 does not match'}
$argsMsi=@('/i',('"'+$msi+'"'),'/quiet','/norestart','ADDLOCAL=Server','SERVER_REGISTER_AS_SERVICE=1','SERVER_ADD_FIREWALL_EXCEPTION=0',
'SET_ALLOWLOOPBACK=1','VALUE_OF_ALLOWLOOPBACK=1','SET_LOOPBACKONLY=1','VALUE_OF_LOOPBACKONLY=1',
'SET_ACCEPTHTTPCONNECTIONS=1','VALUE_OF_ACCEPTHTTPCONNECTIONS=0','SET_USEVNCAUTHENTICATION=1','VALUE_OF_USEVNCAUTHENTICATION=1',
'SET_PASSWORD=1',__PASSWORD__,'SET_ALWAYSSHARED=1','VALUE_OF_ALWAYSSHARED=1','SET_REMOVEWALLPAPER=1','VALUE_OF_REMOVEWALLPAPER=0')
# Record ownership before installation, so an interrupted install can be repaired.
@{owner=$owner;device=$device;version=__VERSION__}|ConvertTo-Json -Compress|Set-Content -LiteralPath $mark -Encoding UTF8
$p=Start-Process msiexec.exe -ArgumentList $argsMsi -Wait -PassThru -WindowStyle Hidden
if($p.ExitCode -notin @(0,3010)){throw ('Installer failed: '+$p.ExitCode)}
$reboot=($p.ExitCode -eq 3010)
Set-Service tvnserver -StartupType Automatic
# DXGI duplication may return access denied / black frames on a powered-off
# physical display (confirmed on Radeon 780M). GDI captures the console without
# installing a virtual monitor or changing the user's display configuration.
New-ItemProperty -Path 'HKLM:\SOFTWARE\TightVNC\Server' -Name UseD3D -PropertyType DWord -Value 0 -Force|Out-Null
$visual=Get-ItemProperty 'HKLM:\SOFTWARE\TightVNC\Server'
if($null -eq $visual.RemoveWallpaper){New-ItemProperty -Path 'HKLM:\SOFTWARE\TightVNC\Server' -Name RemoveWallpaper -PropertyType DWord -Value 0 -Force|Out-Null}
Restart-Service tvnserver
$r=Get-ItemProperty 'HKLM:\SOFTWARE\TightVNC\Server'
if($r.LoopbackOnly -ne 1 -or $r.AllowLoopback -ne 1 -or $r.AcceptHttpConnections -ne 0){Stop-Service tvnserver;throw 'Loopback protection was not applied; server stopped'}
$c=New-Object Net.Sockets.TcpClient('127.0.0.1',5900)
$c.ReceiveTimeout=5000;$b=New-Object byte[] 12;$n=$c.GetStream().Read($b,0,12);$c.Close()
if($n -ne 12 -or [Text.Encoding]::ASCII.GetString($b) -notlike 'RFB *'){throw 'Desktop server did not answer'}
Remove-Item -LiteralPath $msi -Force -ErrorAction SilentlyContinue
'@@json '+(@{ok=$true;reboot=$reboot;hostKey=$hostKey}|ConvertTo-Json -Compress)
'''.replace('__OWNER__', ps(owner)).replace('__DEVICE__', ps(device)).replace('__URL__', ps(URL)).replace('__HASH__', ps(SHA256)).replace('__PASSWORD__', ps('VALUE_OF_PASSWORD=' + password)).replace('__VERSION__', ps(VERSION)).replace('__PUBLIC__', ps(public_key))


def remove_script(owner, device):
    return r'''$ErrorActionPreference='Stop'
$mark=Join-Path $env:ProgramData 'RackLiveDesktop\owner.json'
if(-not (Test-Path -LiteralPath $mark)){throw 'No Rack Live desktop ownership marker'}
$m=Get-Content -LiteralPath $mark -Raw|ConvertFrom-Json
if($m.owner -ne __OWNER__ -or $m.device -ne __DEVICE__){throw 'This desktop belongs to another installation'}
$app=Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue|Where-Object{$_.DisplayName -eq 'TightVNC'}|Select-Object -First 1
if($app){
  if($app.PSChildName -notmatch '^\{[0-9A-Fa-f-]{36}\}$'){throw 'Unrecognized TightVNC product code'}
  $p=Start-Process msiexec.exe -ArgumentList @('/x',$app.PSChildName,'/quiet','/norestart') -Wait -PassThru -WindowStyle Hidden
  if($p.ExitCode -notin @(0,1605,3010)){throw ('Uninstall failed: '+$p.ExitCode)}
}
if(Get-Service tvnserver -ErrorAction SilentlyContinue){throw 'The desktop service still exists'}
Remove-Item -LiteralPath $mark -Force
$comment='racklive-desktop-'+__OWNER__+'-'+__DEVICE__
$keys=Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
if(Test-Path -LiteralPath $keys){
  $keep=@([IO.File]::ReadAllLines($keys)|Where-Object{-not $_.EndsWith(' '+$comment)})
  [IO.File]::WriteAllText($keys,($keep -join "`r`n")+"`r`n",[Text.Encoding]::ASCII)
}
'@@json {"ok":true}'
'''.replace('__OWNER__', ps(owner)).replace('__DEVICE__', ps(device))


class Desktops:
    def __init__(self, data):
        self.root = Path(data) / 'desktop'
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        owner = self.root / 'owner'
        if not owner.exists():
            owner.write_text(secrets.token_hex(16), encoding='ascii')
            os.chmod(owner, 0o600)
        self.owner = owner.read_text(encoding='ascii').strip()
        self.lock = threading.RLock()
        self.busy = set()
        self.tickets = {}
        self.active = {}

    def _path(self, did):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', did or ''):
            raise DriverError('неверное устройство')
        return self.root / (did + '.json')

    def apps(self):
        try:
            return json.loads((self.root / 'app-links.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}

    def visual(self, device, full=None):
        """Only our managed service; wallpaper preference, no capture/SSH changes."""
        did = device['id']
        self._path(did)
        if full is not None and not isinstance(full, bool):
            raise DriverError('неверный режим изображения')
        with self.lock:
            if did in self.busy:
                raise DriverError('операция с этим ПК уже выполняется')
            self.busy.add(did)
        try:
            script = r'''$ErrorActionPreference='Stop'
$m=Get-Content (Join-Path $env:ProgramData 'RackLiveDesktop\owner.json') -Raw|ConvertFrom-Json
if($m.owner -ne __OWNER__ -or $m.device -ne __DEVICE__){throw 'This desktop is not managed by this Rack Live'}
$r=Get-ItemProperty 'HKLM:\SOFTWARE\TightVNC\Server'
$changed=$false
__SET__
$r=Get-ItemProperty 'HKLM:\SOFTWARE\TightVNC\Server'
'@@json '+(@{ok=$true;full=($null -ne $r.RemoveWallpaper -and $r.RemoveWallpaper -eq 0);changed=$changed}|ConvertTo-Json -Compress)
'''.replace('__OWNER__', ps(self.owner)).replace('__DEVICE__', ps(did))
            change = ''
            if full is not None:
                value = 0 if full else 1
                change = rf"if($null -eq $r.RemoveWallpaper -or $r.RemoveWallpaper -ne {value}){{New-ItemProperty -Path 'HKLM:\SOFTWARE\TightVNC\Server' -Name RemoveWallpaper -PropertyType DWord -Value {value} -Force|Out-Null;Restart-Service tvnserver;$changed=$true}}"
            result = winhost.payload(run_ps(device, script.replace('__SET__', change), 45))
            if not result or not result.get('ok'):
                raise DriverError('Не удалось настроить обои. Проверь доступ к ПК и принадлежность плагина Rack Live.')
            return dict(result, message='Полный рабочий стол с обоями включён.' if result.get('full') else 'Быстрый режим: обои скрыты.')
        finally:
            with self.lock:
                self.busy.discard(did)

    def create_app(self, device, name, pictures):
        """Public opaque install URL contains presentation only, never credentials.

        Rasterization happens in the authenticated browser, using the same icon
        choices and brand paths as the map. The server remains stdlib-only.
        """
        import struct
        self._path(device['id'])
        if not isinstance(pictures, dict):
            raise DriverError('неверные иконки приложения')
        icons = {}
        for size in (192, 512):
            value = pictures.get(str(size), '')
            if not isinstance(value, str) or len(value) > 500_000:
                raise DriverError('неверная иконка приложения')
            try:
                raw = base64.b64decode(value, validate=True)
                if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR' or struct.unpack('>II', raw[16:24]) != (size, size):
                    raise ValueError()
            except (ValueError, struct.error):
                raise DriverError('нужна PNG-иконка правильного размера') from None
            icons[str(size)] = value
        with self.lock:
            apps = self.apps()
            previous = apps.get(device['id'], {})
            item = {'token': previous.get('token') or secrets.token_hex(16), 'device': device['id'],
                    'name': str(name or 'Компьютер').strip()[:80] or 'Компьютер', 'icons': icons}
            apps[device['id']] = item
            path = self.root / 'app-links.json'
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(apps), encoding='utf-8')
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        return {'ok': True, 'url': '/desktop-app/' + item['token'] + '/', 'installUrl': '/desktop-install/' + item['token'] + '/', 'name': item['name']}

    def find_app(self, token, devices):
        if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
            return None
        item = next((v for v in self.apps().values() if v.get('token') == token), None)
        if not item or not any(d.get('id') == item.get('device') and d.get('driver') == 'windows' and d.get('enabled', True) for d in devices):
            return None
        return item

    def state(self, did):
        try:
            return json.loads(self._path(did).read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}

    def _key(self, did):
        return self._path(did).with_suffix('.key')

    def _known(self, did):
        return self._path(did).with_suffix('.hosts')

    def _public_key(self, did):
        path = self._key(did)
        if not path.exists():
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        os.chmod(path, 0o600)
        text = path.with_suffix('.key.pub').read_text(encoding='ascii').strip().split()
        return ' '.join(text[:2])

    def _save(self, did, state):
        path = self._path(did)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state), encoding='utf-8')
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def card(self, device, driver, demo=False):
        card = dict(CARD, installed=False, running=False, managed=False, demo=demo)
        if demo:
            return card
        info = winhost.payload(run_ps(device, PROBE, 30))
        if not isinstance(info, dict):
            raise DriverError('Windows не отдал состояние рабочего стола')
        own = info.get('owner') == self.owner and info.get('device') == device['id']
        local = self.state(device['id'])
        card.update(installed=bool(info.get('present')), running=bool(info.get('running')), managed=own,
                    ready=bool(own and info.get('running') and info.get('loopback') and info.get('httpOff') and info.get('captureCompatible') and local.get('ready')
                               and self._key(device['id']).is_file() and self._known(device['id']).is_file()))
        if info.get('present') and not own:
            card['warning'] = 'На ПК уже есть TightVNC, установленный отдельно. Rack Live не будет менять или удалять его.'
        elif info.get('present') and not card['ready']:
            card['warning'] = 'Сервер установлен, но подключение не готово. Проверь SSH и нажми «Восстановить».'
        return card

    def plugin(self, device, pid, op, params):
        if pid != 'desktop' or op not in ('install', 'remove') or device.get('driver') != 'windows':
            raise DriverError('неверная операция рабочего стола')
        if os.name != 'posix':
            raise DriverError('установка доступна на Rack Live в Linux / NAS')
        did = device['id']
        progress = params.get('_progress', lambda _: None)
        driver = params['_drv']
        with self.lock:
            if did in self.busy:
                raise DriverError('операция с этим ПК уже выполняется')
            self.busy.add(did)
        try:
            if op == 'install':
                progress('Проверяю SSH и существующий рабочий стол…')
                card = self.card(device, driver)
                if card['installed'] and not card['managed']:
                    raise DriverError(card['warning'])
                state = self.state(did)
                state.setdefault('password', ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8)))
                state['ready'] = False
                self._save(did, state)
                self.close_device(did)
                progress('Скачиваю проверенный установщик и настраиваю сервер Windows…')
                public_key = self._public_key(did)
                result = winhost.payload(run_ps(device, install_script(self.owner, did, state['password'], public_key), 240))
                if not result or not result.get('ok'):
                    detail = (result or {}).get('error') or 'Проверь права администратора и доступ ПК к tightvnc.com.'
                    raise DriverError('Установка не завершена: ' + str(detail).replace(state['password'], '<секрет>')[:350])
                host_key = str(result.get('hostKey') or '').split()
                if len(host_key) < 2 or host_key[0] != 'ssh-ed25519' or not re.fullmatch(r'[A-Za-z0-9+/=]+', host_key[1]):
                    raise DriverError('Windows не отдал открытый ключ SSH-сервера')
                self._known(did).write_text('* ' + ' '.join(host_key[:2]) + '\n', encoding='ascii')
                os.chmod(self._known(did), 0o600)
                state.pop('bridge', None)
                state.update(ready=True, version=VERSION, installed=time.time())
                self._save(did, state)
                return {'ok': True, 'message': 'Рабочий стол установлен. Можно подключаться.', 'rebootSuggested': bool(result.get('reboot'))}
            progress('Закрываю подключения и удаляю наш сервер рабочего стола…')
            self.close_device(did)
            result = winhost.payload(run_ps(device, remove_script(self.owner, did), 180))
            if not result or not result.get('ok'):
                raise DriverError('Windows не подтвердил удаление рабочего стола: ' + str((result or {}).get('error') or '')[:250])
            self._path(did).unlink(missing_ok=True)
            self._key(did).unlink(missing_ok=True)
            self._key(did).with_suffix('.key.pub').unlink(missing_ok=True)
            self._known(did).unlink(missing_ok=True)
            return {'ok': True, 'removed': True, 'message': 'Рабочий стол удалён. SSH и мониторинг ПК продолжают работать.'}
        finally:
            with self.lock:
                self.busy.discard(did)

    def ticket(self, device, session):
        state = self.state(device['id'])
        if not state.get('ready'):
            raise DriverError('сначала установи плагин рабочего стола на этот ПК')
        with self.lock:
            now = time.time()
            self.tickets = {k: v for k, v in self.tickets.items() if v['until'] > now}
            ticket = secrets.token_urlsafe(24)
            self.tickets[ticket] = {'session': session, 'device': device['id'], 'until': now + 30}
        return {'ticket': ticket, 'password': state['password']}

    def consume(self, ticket):
        with self.lock:
            result = self.tickets.pop(ticket, None)
        return result if result and result['until'] > time.time() else None

    def spawn(self, device):
        if not self._key(device['id']).is_file() or not self._known(device['id']).is_file():
            raise DriverError('нужно восстановить установку плагина')
        host, user, port = device.get('host') or '', device.get('username') or '', int(device.get('sshPort') or 22)
        if not host or host.startswith('-') or not user or user.startswith('-'):
            raise DriverError('неверный адрес или логин SSH')
        args = ['ssh', '-T', '-p', str(port), '-i', str(self._key(device['id'])), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes',
                '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(self._known(device['id'])),
                '-o', 'LogLevel=ERROR', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-o', 'ConnectTimeout=12',
                '-W', '127.0.0.1:5900', user + '@' + host]
        env, keyfile = dict(os.environ), None
        process = None
        try:
            process = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            initial = b''
            until = time.monotonic() + 20
            while len(initial) < 12 and time.monotonic() < until:
                ready, _, _ = select.select([process.stdout], [], [], .25)
                if ready:
                    chunk = os.read(process.stdout.fileno(), 12 - len(initial))
                    if not chunk:
                        break
                    initial += chunk
                elif process.poll() is not None:
                    break
            if not initial.startswith(b'RFB ') or len(initial) != 12:
                raise DriverError('не удалось открыть экран по SSH: проверь службу рабочего стола и вход на ПК')
            return process, keyfile, initial
        except Exception:
            self.cleanup(process, keyfile)
            raise

    @staticmethod
    def cleanup(process, keyfile):
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(3)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        if keyfile:
            try:
                os.unlink(keyfile)
            except FileNotFoundError:
                pass

    def close_device(self, did):
        with self.lock:
            for entry in list(self.active.values()):
                if entry['device'] == did:
                    try:
                        entry['conn'].shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

    def relay(self, conn, device, process, keyfile, initial, valid, log):
        sid = secrets.token_hex(8)
        reader = terminal.Reader(require_mask=True)
        try:
            conn.settimeout(15)
            with self.lock:
                if len(self.active) >= 3:
                    raise DriverError('открыто слишком много рабочих столов (не больше трёх)')
                self.active[sid] = {'device': device['id'], 'conn': conn}
            log('рабочий стол: подключение открыто')
            conn.sendall(terminal.frame(initial))
            start, checked = time.monotonic(), 0
            while process.poll() is None and time.monotonic() - start < 4 * 3600:
                now = time.monotonic()
                if now - checked > 10:
                    if not valid():
                        break
                    checked = now
                ready, _, _ = select.select([conn, process.stdout], [], [], 1)
                if conn in ready:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    for op, data in reader.feed(chunk):
                        if op == 8:
                            return
                        if op == 9:
                            conn.sendall(terminal.frame(data, 10))
                        elif op in (0, 2):
                            view = memoryview(data)
                            while view:
                                view = view[os.write(process.stdin.fileno(), view):]
                        elif op != 10:
                            raise ValueError('ожидались двоичные данные')
                if process.stdout in ready:
                    data = os.read(process.stdout.fileno(), 65536)
                    if not data:
                        break
                    conn.sendall(terminal.frame(data))
        except (OSError, ValueError, DriverError):
            pass
        finally:
            with self.lock:
                self.active.pop(sid, None)
            self.cleanup(process, keyfile)
            log('рабочий стол: подключение закрыто')
