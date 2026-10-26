"""Frank as an agent (like Claude Code / opencode): files and commands on the machine where Rack Live runs.
The working folder is data/frank/work (relative paths start there). Three modes, chosen by the person (cfg.ai.agentMode):
  ask   — looking (reading files, read-only commands) runs at once; writing files and other commands become a card «Выполнить»
  edits — files are written at once too; commands that change something still ask
  full  — everything runs at once
In every mode two things are never done: what would wreck the machine (rm -rf /, mkfs, dd onto a disk, shutting it down, accounts and passwords),
and touching Rack Live itself — its data (passwords of devices, sign-in; only data/frank is Frank's) and, for writing, its program."""
import fnmatch
import os
import platform
import re
import subprocess
import time

MODES = {'ask': 'спрашивать', 'edits': 'правки сам', 'full': 'полный доступ'}
CODE = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # the Rack Live program (rackd/, web/)
OUT_MAX = 14000
READ_LINES = 2000
SECRET_NAMES = re.compile(r'(?i)(^|[/\\\s"\'])(config(\.bak[\w-]*)?\.json|auth\.json|sessions\.json|mfa\.json|camcreds\.json|tg_frank\.json|known\.json)\b')
CATASTROPHE = re.compile(r'(?i)(\brm\s+(-\w+\s+)*-\w*r\w*\s+(-\w+\s+)*(/|/\*|~|~/|\$HOME)(\s|$)|\bdd\s+[^\n]*of=/dev/|>\s*/dev/(sd|nvme|mmc|hd|vd|md)|'
                         r':\(\)\s*\{|\bchmod\s+-R\s+\S+\s+/\s*$|\bchown\s+-R\s+\S+\s+/\s*$|>\s*/etc/(shadow|passwd|sudoers))')
# the same, but only as the command itself (a «grep reboot /var/log/…» is fine)
CATASTROPHE_CMD = re.compile(r'(?i)^\s*(sudo\s+(-\S+\s+)*)?(shutdown|poweroff|halt|reboot|init\s+[06]|mkfs\S*|wipefs|fdisk|parted|sfdisk|passwd|chpasswd|'
                             r'user(add|del|mod)|group(add|del|mod)|visudo|systemctl\s+(poweroff|reboot|halt))\b')
READ_CMD = re.compile(r'(?i)^\s*(cat|ls|ll|head|tail|grep|egrep|rg|wc|sort|uniq|awk|cut|df|du|free|uptime|uname|id|whoami|date|hostname|ps|pwd|env|printenv|'
                      r'find|stat|file|which|type|echo|printf|true|tree|less|more|diff|cmp|md5sum|sha\d*sum|ping|traceroute|nslookup|dig|host|ip\s+(a|addr|r|route|link)|'
                      r'ss|netstat|lsblk|lsusb|mount|python3?\s+--version|node\s+--version|git\s+(status|log|diff|show|branch)|docker\s+(ps|images|logs|inspect|version|info)|'
                      r'apk\s+(info|list|search)|apt\s+(list|show|search)|dpkg\s+-l|systemctl\s+(status|is-active|list-units)|journalctl|curl\s+-[sIfL]*\s+-?I?\s*\S+\s*$)\b')


class Denied(Exception):
    pass


def work(data_dir):
    p = os.path.join(data_dir, 'frank', 'work')
    os.makedirs(p, exist_ok=True)
    return p


def where():
    """where the commands run, in words, for the model and the person"""
    box = ' в контейнере Docker' if os.path.exists('/.dockerenv') else ''
    return f'{platform.system()} {platform.machine()}{box}'


def _within(p, root):
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


def resolve(data_dir, path, write=False):
    p = os.path.expanduser(str(path or '.').strip() or '.')
    if not os.path.isabs(p):
        p = os.path.join(work(data_dir), p)
    p = os.path.realpath(p)
    data, mine = os.path.realpath(data_dir), os.path.realpath(os.path.join(data_dir, 'frank'))
    if _within(p, data) and not _within(p, mine):
        raise Denied('это данные самой Rack Live (пароли устройств, вход, настройки) — Frank их не читает и не меняет. Твоя папка — ' + work(data_dir))
    if write and _within(p, CODE):
        raise Denied('это программа самой Rack Live, которая сейчас работает — её Frank не меняет. Для работы над проектом: git clone в свою рабочую папку и правки там')
    return p


def classify(data_dir, name, args):
    """→ (kind, why): kind = read | edit | command | deny"""
    if name in ('read_file', 'list_dir', 'find_files', 'search_text'):
        return 'read', ''
    if name in ('write_file', 'edit_file'):
        try:
            resolve(data_dir, args.get('path'), write=True)
        except Denied as e:
            return 'deny', str(e)
        return 'edit', ''
    if name == 'shell':
        cmd = str(args.get('command') or '')
        if not cmd.strip():
            return 'deny', 'пустая команда'
        if CATASTROPHE.search(cmd) or any(CATASTROPHE_CMD.match(s) for s in re.split(r'\|\||&&|;|\||\n', cmd) if s.strip()):
            return 'deny', 'такую команду Frank не выполняет никогда (удаление системы, форматирование, выключение машины, пароли и пользователи). Объясни пользователю, как сделать это вручную'
        dd = os.path.realpath(data_dir)
        if SECRET_NAMES.search(cmd) or re.search(re.escape(dd) + r'(?!' + re.escape(os.sep) + r'frank)', cmd) or re.search(r'(^|[\s"\'=])/data(/(?!frank)|\s|$)', cmd):
            return 'deny', 'команда касается данных Rack Live (пароли устройств, вход) — их Frank не трогает'
        lines = [l for l in cmd.split('\n') if l.strip()]
        if all('>' not in l and '$(' not in l and '`' not in l and all(READ_CMD.match(s) for s in re.split(r'\|\||&&|;|\|', l) if s.strip()) for l in lines):
            return 'read', ''
        return 'command', ''
    return 'deny', 'неизвестный инструмент'


def needs_ok(mode, kind):
    """does this step need the person's press in this mode"""
    if kind == 'read':
        return False
    if mode == 'full':
        return False
    if mode == 'edits':
        return kind == 'command'
    return True


def preview(data_dir, name, args):
    """what the card shows before the press"""
    if name == 'shell':
        return str(args.get('command') or '')[:3000]
    path = str(args.get('path') or '')
    if name == 'write_file':
        c = str(args.get('content') or '')
        lines = c.split('\n')
        return f'Файл: {path} ({len(lines)} строк)\n\n' + '\n'.join(lines[:40]) + ('\n…' if len(lines) > 40 else '')
    if name == 'edit_file':
        old, new = str(args.get('old_string') or ''), str(args.get('new_string') or '')
        return (f'Файл: {path}\n\n' + '\n'.join('- ' + l for l in old.split('\n')[:20]) + '\n' + '\n'.join('+ ' + l for l in new.split('\n')[:20]))[:3000]
    return path


def label(name, args):
    p = str(args.get('path') or args.get('pattern') or '')
    return {'read_file': 'Читаю ' + p, 'write_file': 'Записать файл ' + p, 'edit_file': 'Изменить файл ' + p, 'list_dir': 'Папка ' + (p or '.'),
            'find_files': 'Ищу файлы ' + p, 'search_text': 'Ищу текст «' + str(args.get('pattern') or '')[:40] + '»',
            'shell': 'Команда: ' + str(args.get('command') or '').split('\n')[0][:70]}.get(name, name)


def _cut(s):
    s = str(s or '')
    return s[:OUT_MAX] + f'\n…(обрезано, всего {len(s)} символов)' if len(s) > OUT_MAX else s


def _text(p):
    with open(p, 'rb') as f:
        b = f.read(8_000_000)
    if b'\x00' in b[:8192]:
        return None
    return b.decode('utf-8', 'replace')


def run(data_dir, name, args, mask=lambda l: l):
    """do one step → text for the model (errors as text too, prefixed «ошибка:»)"""
    try:
        if name == 'read_file':
            p = resolve(data_dir, args.get('path'))
            if os.path.isdir(p):
                return 'ошибка: это папка — используй list_dir'
            t = _text(p)
            if t is None:
                return f'двоичный файл, {os.path.getsize(p)} байт — прочитать как текст нельзя (можно командой: file, strings, pdftotext…)'
            lines = t.split('\n')
            off = max(1, int(args.get('offset') or 1))
            lim = max(1, min(READ_LINES, int(args.get('limit') or READ_LINES)))
            part = lines[off - 1:off - 1 + lim]
            out = '\n'.join(f'{i:6}\t{mask(l)}' for i, l in enumerate(part, off))
            more = len(lines) - (off - 1 + len(part))
            return _cut(out + (f'\n…ещё {more} строк (offset={off + len(part)})' if more > 0 else '')) or '(файл пустой)'
        if name == 'write_file':
            p = resolve(data_dir, args.get('path'), write=True)
            c = str(args.get('content') or '')
            os.makedirs(os.path.dirname(p), exist_ok=True)
            existed = os.path.exists(p)
            with open(p, 'w', encoding='utf-8', newline='') as f:
                f.write(c)
            return f"{'перезаписан' if existed else 'создан'} {p}: {c.count(chr(10)) + (1 if c and not c.endswith(chr(10)) else 0)} строк"
        if name == 'edit_file':
            p = resolve(data_dir, args.get('path'), write=True)
            t = _text(p)
            if t is None:
                return 'ошибка: двоичный файл'
            old, new = str(args.get('old_string') or ''), str(args.get('new_string') or '')
            if not old:
                return 'ошибка: old_string пустой — чтобы создать файл, используй write_file'
            n = t.count(old)
            if n == 0:
                return 'ошибка: такого фрагмента в файле нет — перечитай файл (read_file) и возьми текст точно'
            if n > 1 and not args.get('replace_all'):
                return f'ошибка: фрагмент встречается {n} раз — добавь вокруг него больше строк, чтобы он стал единственным, или replace_all=true'
            with open(p, 'w', encoding='utf-8', newline='') as f:
                f.write(t.replace(old, new) if args.get('replace_all') else t.replace(old, new, 1))
            return f'изменён {p}: заменено {n if args.get("replace_all") else 1}'
        if name == 'list_dir':
            p = resolve(data_dir, args.get('path'))
            rows = []
            for e in sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower()))[:500]:
                try:
                    rows.append(f"{e.name}/" if e.is_dir() else f"{e.name}  ({e.stat().st_size} байт)")
                except OSError:
                    rows.append(e.name)
            return f'{p}:\n' + ('\n'.join(rows) or '(пусто)')
        if name == 'find_files':
            p = resolve(data_dir, args.get('path'))
            pat = str(args.get('pattern') or '*')
            hits = []
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, p).replace(os.sep, '/')
                    if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(f, pat):
                        hits.append(full)
                if len(hits) > 2000:
                    break
            hits.sort(key=lambda f: -os.path.getmtime(f))
            return '\n'.join(hits[:500]) + (f'\n…ещё {len(hits) - 500}' if len(hits) > 500 else '') or 'ничего не найдено'
        if name == 'search_text':
            p = resolve(data_dir, args.get('path'))
            try:
                rx = re.compile(str(args.get('pattern') or ''), re.I if args.get('ignore_case') else 0)
            except re.error as e:
                return f'ошибка в регулярном выражении: {e}'
            g = str(args.get('glob') or '*')
            out, files = [], [p] if os.path.isfile(p) else (os.path.join(r, f) for r, ds, fs in os.walk(p) for f in fs if fnmatch.fnmatch(f, g))
            for f in files:
                if len(out) >= 300:
                    break
                try:
                    if os.path.getsize(f) > 2_000_000:
                        continue
                    t = _text(f)
                except OSError:
                    continue
                if t is None:
                    continue
                for i, l in enumerate(t.split('\n'), 1):
                    if rx.search(l):
                        out.append(f'{f}:{i}: {mask(l.strip())[:300]}')
                        if len(out) >= 300:
                            break
            return _cut('\n'.join(out)) or 'совпадений нет'
        if name == 'shell':
            cwd = resolve(data_dir, args.get('cwd') or '.')
            timeout = max(5, min(600, int(args.get('timeout') or 120)))
            cmd = str(args.get('command') or '')
            argv = ['cmd', '/c', cmd] if os.name == 'nt' else ['sh', '-c', cmd]
            env = dict(os.environ, HOME=work(data_dir))
            for k in [k for k in env if k.startswith('RL_')]:
                env.pop(k)                                      # the panel's own settings stay out of reach
            t0 = time.time()
            try:
                r = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            except subprocess.TimeoutExpired as e:
                out = (e.output or b'').decode('utf-8', 'replace')
                return _cut(f'команда не уложилась в {timeout} с и остановлена\n' + '\n'.join(mask(l) for l in out.split('\n')))
            out = r.stdout.decode('utf-8', 'replace')
            body = '\n'.join(mask(l) for l in out.rstrip('\n').split('\n')) if out.strip() else '(вывода нет)'
            return _cut(f'код выхода {r.returncode}, {time.time() - t0:.1f} с\n{body}')
        return 'ошибка: неизвестный инструмент'
    except Denied as e:
        return 'отказано: ' + str(e)
    except FileNotFoundError:
        return 'ошибка: нет такого файла или папки'
    except (OSError, ValueError) as e:
        return f'ошибка: {e}'


TOOLS = [
    ('read_file', 'Прочитать текстовый файл на рабочей машине (с номерами строк). Большие файлы — частями: offset (с какой строки) и limit (сколько строк, до 2000).',
     {'path': ('string', 'путь; относительный — от рабочей папки Frank'), 'offset': ('integer', 'с какой строки (необязательно)'), 'limit': ('integer', 'сколько строк (необязательно)')}),
    ('write_file', 'Создать файл или полностью переписать его содержимым content (папки создаются сами). Существующий файл перед этим прочитай.',
     {'path': ('string', 'путь'), 'content': ('string', 'полный текст файла')}),
    ('edit_file', 'Изменить часть файла: точная замена old_string на new_string. old_string должен встречаться ровно один раз (или replace_all=true). Сначала прочитай файл.',
     {'path': ('string', 'путь'), 'old_string': ('string', 'точный фрагмент, как в файле'), 'new_string': ('string', 'на что заменить'),
      'replace_all': ('boolean', 'заменить все вхождения (необязательно)')}),
    ('list_dir', 'Список файлов и папок.', {'path': ('string', 'папка (необязательно — рабочая папка)')}),
    ('find_files', 'Найти файлы по шаблону имени (glob: *.py, **/*.conf), новые первыми.', {'pattern': ('string', 'шаблон'), 'path': ('string', 'где искать (необязательно)')}),
    ('search_text', 'Найти строки по регулярному выражению в файлах (как grep -rn).',
     {'pattern': ('string', 'регулярное выражение'), 'path': ('string', 'файл или папка (необязательно)'), 'glob': ('string', 'какие файлы, например *.py (необязательно)'),
      'ignore_case': ('boolean', 'без учёта регистра (необязательно)')}),
    ('shell', 'Выполнить команду оболочки (sh) на рабочей машине — той, где работает Rack Live. Для роутеров, NAS и серверов из Rack Live используй device_command.',
     {'command': ('string', 'команда; можно несколько строк'), 'cwd': ('string', 'папка (необязательно — рабочая папка)'), 'timeout': ('integer', 'секунд, до 600 (по умолчанию 120)')}),
]
NAMES = {t[0] for t in TOOLS}
