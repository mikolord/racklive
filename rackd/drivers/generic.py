"""Generic drivers: availability check, website check and push agent for remote hosts."""
import datetime, hashlib, socket, ssl, subprocess, time, urllib.request

from . import Driver
from ..util import DriverError, NOSSL, tcp_check


class Ping(Driver):
    id = 'ping'
    title = 'Доступность (ping / порт)'
    kind = 'other'
    description = 'Любое устройство по IP или домену: онлайн или нет и задержка. Подходит для камер, точек, удалённых серверов.'
    fields = [{'name': 'host', 'label': 'Адрес (IP или домен)', 'type': 'text', 'required': True},
              {'name': 'tcpPort', 'label': 'TCP-порт (если ping закрыт)', 'type': 'text', 'placeholder': 'например 80 или 554'}]

    def poll(self, cfg):
        host, port = cfg['host'].strip(), str(cfg.get('tcpPort') or '').strip()
        ms = None
        if port.isdigit():
            ms = tcp_check(host, int(port))
        else:
            try:
                out = subprocess.run(['ping', '-c', '2', '-W', '2', host], capture_output=True, text=True, timeout=10).stdout
                if ' 0% packet loss' in out or 'bytes from' in out:
                    for l in out.splitlines():
                        if 'min/avg' in l:
                            ms = float(l.split('=')[1].split('/')[1])
                    ms = ms if ms is not None else 1
            except Exception:
                ms = None
            if ms is None:
                for p in (443, 80, 22, 554):
                    ms = tcp_check(host, p, 2)
                    if ms is not None:
                        break
        if ms is None:
            raise DriverError('не отвечает')
        try:
            ip = socket.gethostbyname(host)
        except OSError:
            ip = host
        return {'status': 'online', 'summary': {'ip': ip}, 'metrics': [{'label': 'Задержка', 'value': ms, 'unit': 'мс'}]}


class Website(Driver):
    id = 'http'
    title = 'Сайт / веб-сервис'
    kind = 'web'
    description = 'Проверяет, что сайт открывается: код ответа, время ответа, сколько дней до окончания сертификата.'
    fields = [{'name': 'host', 'label': 'URL', 'type': 'text', 'required': True, 'placeholder': 'https://example.com'},
              {'name': 'expect', 'label': 'Ожидаемый текст на странице (необязательно)', 'type': 'text'}]

    def poll(self, cfg):
        url = cfg['host'].strip()
        if not url.startswith('http'):
            url = 'https://' + url
        t = time.time()
        try:
            resp = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'RackLive/2'}), timeout=15, context=NOSSL)
            code, body = resp.status, resp.read(200000).decode(errors='ignore')
        except urllib.error.HTTPError as e:
            code, body = e.code, ''
        except Exception as e:
            raise DriverError(f'не открывается: {e.__class__.__name__}')
        ms = round((time.time() - t) * 1000)
        metrics = [{'label': 'Ответ', 'value': code, 'level': 'warn' if code >= 400 else ''}, {'label': 'Время', 'value': ms, 'unit': 'мс'}]
        status = 'online' if code < 400 else 'warning'
        if cfg.get('expect') and cfg['expect'] not in body:
            status = 'warning'
            metrics.append({'label': 'Текст', 'value': 'не найден', 'level': 'warn'})
        if url.startswith('https://'):
            try:
                host = url.split('/')[2].split(':')[0]
                port = int(url.split('/')[2].split(':')[1]) if ':' in url.split('/')[2] else 443
                ctx = ssl.create_default_context()
                with socket.create_connection((host, port), 8) as s, ctx.wrap_socket(s, server_hostname=host) as ss:
                    exp = datetime.datetime.strptime(ss.getpeercert()['notAfter'], '%b %d %H:%M:%S %Y %Z')
                days = (exp - datetime.datetime.utcnow()).days
                metrics.append({'label': 'Сертификат', 'value': days, 'unit': 'дн.', 'level': 'warn' if days < 14 else ''})
                if days < 7:
                    status = 'warning'
            except ssl.SSLCertVerificationError:
                metrics.append({'label': 'Сертификат', 'value': 'недействителен', 'level': 'warn'})
                status = 'warning'
            except Exception:
                pass
        return {'status': status, 'summary': {'ip': url.split('/')[2]}, 'metrics': metrics}


LOGIN_CHECKED = {}          # remote_web: sha256(url, login, password) → did the Keenetic login work (checked once)


class RemoteWeb(Driver):
    """A router (or anything with a web panel) somewhere else: Rack Live can't manage it, but keeps the link and the login,
    shows whether the panel opens — and says so when it turns out to be a Keenetic that could be managed after all."""
    id = 'remote_web'
    title = 'Роутер / веб-панель (без управления)'
    kind = 'router'
    description = ('Роутер абонента, родных, на даче или в офисе — в вашей сети или удалённо (домен KeenDNS, белый IP). Rack Live проверяет, что '
                   'веб-интерфейс открывается, а в карточке — кнопка «Открыть», логин и пароль с кнопкой «Скопировать».')
    fields = [{'name': 'host', 'label': 'Адрес веб-интерфейса', 'type': 'text', 'required': True,
               'placeholder': 'https://имя.keenetic.pro или http://1.2.3.4:8080',
               'hint': 'Домен KeenDNS, белый IP с портом или любой адрес, по которому панель открывается в браузере'},
              {'name': 'username', 'label': 'Логин для входа', 'type': 'text', 'default': 'admin'},
              {'name': 'password', 'label': 'Пароль для входа', 'type': 'password', 'secret': True,
               'hint': 'Хранится в Rack Live; в карточке устройства его можно показать и скопировать (только администратору)'}]

    @staticmethod
    def url(cfg):
        u = (cfg.get('host') or '').strip().rstrip('/')
        return u if '://' in u else 'http://' + u

    def poll(self, cfg):
        url = self.url(cfg)
        t = time.time()
        try:
            resp = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'RackLive/2'}), timeout=15, context=NOSSL)
            code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code                                     # 401 / 403 = the panel is there and asks for a login
        except Exception as e:
            raise DriverError(f'веб-интерфейс не открывается: {getattr(e, "reason", e.__class__.__name__)}')
        ms = round((time.time() - t) * 1000)
        metrics = [{'label': 'Время ответа', 'value': ms, 'unit': 'мс'}]
        summary = {'ip': url.split('/')[2]}
        sections = []
        # a Keenetic that answers RCI directly (KeenDNS «direct» or a forwarded port) could be fully managed
        try:
            r = urllib.request.urlopen(urllib.request.Request(url + '/auth', headers={'User-Agent': 'RackLive/2'}), timeout=8, context=NOSSL)
            realm = r.headers.get('X-NDM-Realm')
        except urllib.error.HTTPError as e:
            realm = e.headers.get('X-NDM-Realm')
        except Exception:
            realm = None
        if realm:
            summary['model'] = f'Keenetic / Netcraze ({realm})'
            note = 'Роутер отвечает напрямую — им можно управлять: смените тип устройства на «Keenetic» с этим же адресом, логином и паролем.'
            # the login is tried ONCE per address/login/password: a wrong password every minute would get our IP locked out by the router
            key = hashlib.sha256(f"{url}\0{cfg.get('username')}\0{cfg.get('password')}".encode()).hexdigest()
            if key not in LOGIN_CHECKED:
                try:
                    from .keenetic import Keenetic
                    Keenetic()._session({'host': url, 'username': cfg.get('username') or 'admin', 'password': cfg.get('password') or ''})
                    LOGIN_CHECKED[key] = True
                except Exception:
                    LOGIN_CHECKED[key] = False
            note = ('✔ Логин и пароль подходят. ' + note) if LOGIN_CHECKED[key] else note + ' (Логин или пароль для управления не подошли — проверьте.)'
            sections.append({'title': 'Управление', 'rows': [['Можно больше', note]]})
        else:
            sections.append({'title': 'Управление', 'rows': [['Режим', 'Только ссылка и данные для входа — данные с роутера Rack Live не получает']]})
        return {'status': 'online' if code < 500 else 'warning', 'summary': summary, 'metrics': metrics, 'sections': sections}


class SiteNode(Driver):
    """a device of a remote site: its data is pushed by the site's collector (rackd/sites.py, rackd/collector.py)"""
    id = 'site_node'
    title = 'Устройство удалённой площадки'
    kind = 'other'
    description = 'Появляется само, когда сборщик удалённой площадки присылает данные (Инструменты → Удалённые площадки).'
    fields = []
    hidden = True
    push = True

    def poll(self, cfg):
        raise DriverError('данные присылает сборщик площадки')


class Agent(Driver):
    id = 'agent'
    title = 'Агент (удалённый сервер)'
    kind = 'server'
    description = 'Для серверов в другом месте или за NAT: на сервере запускается agent.py, он сам присылает данные. Открывать порты не нужно.'
    fields = [{'name': 'staleMinutes', 'label': 'Считать офлайн, если нет данных (минут)', 'type': 'text', 'default': '5'}]
    push = True
    hidden = True               # added in «Инструменты → Удалённые площадки и агенты», not in the list of device types

    def poll(self, cfg):
        raise DriverError('ожидание данных от агента')
