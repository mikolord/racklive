"""Windows PC / server over SSH — the built-in OpenSSH server, no agent (rackd/winhost.py)."""
from . import Driver, FIELD_PASS
from . import sshhost as _ssh
from .. import winhost
from ..util import DriverError


class WindowsHost(Driver):
    id = 'windows'
    title = 'Компьютер / сервер Windows (по SSH)'
    kind = 'pc'
    description = ('Windows 10 / 11 и Windows Server: процессор, память, диски и их состояние, перезагрузка после обновлений, Docker. '
                   'Подключение через встроенный OpenSSH Windows, без агента. Подготовь ПК по шагам ниже.')
    fields = [{'name': 'host', 'label': 'Адрес (IP или имя)', 'type': 'text', 'required': True},
              {'name': 'sshPort', 'label': 'Порт SSH', 'type': 'text', 'default': '22'},
              {'name': 'username', 'label': 'Пользователь Windows', 'type': 'text',
               'hint': 'Узнай логин командой whoami на ПК. Для физических дисков нужен локальный администратор.'},
              dict(FIELD_PASS, hint='Пароль учётной записи, не PIN Windows Hello. Если пароля нет — используй SSH-ключ по инструкции выше.'),
              {'name': 'privateKey', 'label': 'Приватный ключ (вместо пароля)', 'type': 'textarea', 'secret': True,
               'hint': 'Для ключа положите открытую часть в C:\\ProgramData\\ssh\\administrators_authorized_keys.'}]
    actions = [{'id': 'reboot', 'label': 'Перезагрузить компьютер', 'scope': 'device',
                'confirm': 'Компьютер перезагрузится через 5 секунд, несохранённая работа на нём будет потеряна. Продолжить?'}]
    help = winhost.ENABLE_SSH

    def plugins(self, cfg):
        from ..windesktop import CARD
        return {'plugins': [dict(CARD)]}  # application fills the managed installation's status

    def _ps(self, cfg, script, timeout=60):
        return _ssh.SSHHost()._run(cfg, winhost.PRELUDE + script if not script.startswith(winhost.PRELUDE) else script, timeout=timeout, remote=winhost.REMOTE)

    def poll(self, cfg):
        out = self._ps(cfg, winhost.POLL, 60)
        try:
            return winhost.parse_poll(out, cfg['host'].strip())
        except ValueError as e:
            raise DriverError(str(e) + '. Включён ли OpenSSH-сервер и запускается ли PowerShell?')

    def disks(self, cfg):
        """Windows' own storage health (rackd/winhost.py)"""
        return winhost.parse_disks(self._ps(cfg, winhost.DISKS, 90))

    def disk_test(self, cfg, disk, kind):
        raise DriverError('Windows не умеет запускать самотест диска через PowerShell. Для полного SMART используйте CrystalDiskInfo или смартмонтулс на самом компьютере.')

    def action(self, cfg, action_id, params):
        if action_id == 'reboot':
            self._ps(cfg, winhost.RESTART, 20)
            return 'Перезагрузка запущена'
        raise DriverError('действие не поддерживается')
