"""«ИИ-агенты на сервере» (driver «Сервер / VPS по SSH»): Claude Code (+ Remote Control, автозапуск, «новый чат»), Codex CLI, Gemini CLI, OpenCode, Aider.

Everything runs as ordinary shell over SSH, in stages. On the server one small helper `racklive-agent` is written (start-all / new / list / stop / restart / setup / status):
it keeps every chat in its own tmux session, so a session survives the SSH connection and a reboot (systemd unit when root, otherwise cron @reboot).
Claude Code's Remote Control only works with a claude.ai subscription login (no API key, no `setup-token`) — the one-time login is done in the built-in terminal (`setup`)."""
import re, shlex

CATALOG = [
    {'id': 'agents', 'drivers': ['ssh'], 'title': 'ИИ-агенты (Claude Code и другие)', 'icon': 'terminal', 'kind': 'agents',
     'description': 'Ставит Claude Code, Codex, Gemini CLI, OpenCode, Aider. Для Claude Code — Remote Control (чат с телефона), автозапуск после перезагрузки и кнопка «Новый чат».',
     'author': 'Anthropic · OpenAI · Google · sst · Aider', 'home': 'https://code.claude.com/docs/en/remote-control'},
]

# id → (title, binary, how to install, key variable | None, note)
AGENTS = [
    {'id': 'claude', 'title': 'Claude Code', 'bin': 'claude', 'key': 'ANTHROPIC_API_KEY', 'by': 'Anthropic', 'home': 'https://code.claude.com',
     'install': 'curl -fsSL https://claude.ai/install.sh | bash', 'npm': '@anthropic-ai/claude-code'},
    {'id': 'codex', 'title': 'Codex CLI', 'bin': 'codex', 'key': 'OPENAI_API_KEY', 'by': 'OpenAI', 'home': 'https://github.com/openai/codex',
     'npm': '@openai/codex'},
    {'id': 'gemini', 'title': 'Gemini CLI', 'bin': 'gemini', 'key': 'GEMINI_API_KEY', 'by': 'Google', 'home': 'https://github.com/google-gemini/gemini-cli',
     'npm': '@google/gemini-cli'},
    {'id': 'opencode', 'title': 'OpenCode', 'bin': 'opencode', 'key': None, 'by': 'sst', 'home': 'https://opencode.ai',
     'install': 'curl -fsSL https://opencode.ai/install | bash', 'npm': 'opencode-ai'},
    {'id': 'aider', 'title': 'Aider', 'bin': 'aider', 'key': None, 'by': 'Aider-AI', 'home': 'https://aider.chat',
     'install': 'curl -LsSf https://aider.chat/install.sh | sh'},
]
BY_ID = {a['id']: a for a in AGENTS}
MODELS = [('', 'по умолчанию'), ('opus', 'Opus (самая умная)'), ('sonnet', 'Sonnet (быстрее, дешевле)'), ('haiku', 'Haiku (самая быстрая)')]

PATHS = 'export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$HOME/.aider/bin:/usr/local/bin:$PATH"'

STATUS = PATHS + r'''
. /etc/os-release 2>/dev/null; echo "@@os $PRETTY_NAME"; echo "@@id $ID"; echo "@@uid $(id -u)"; echo "@@home $HOME"
command -v tmux >/dev/null 2>&1 && echo "@@tmux $(tmux -V)"
command -v node >/dev/null 2>&1 && echo "@@node $(node -v)"
command -v npm >/dev/null 2>&1 && echo "@@npm $(npm -v)"
[ -d /run/systemd/system ] && echo "@@systemd 1"
for b in claude codex gemini opencode aider; do
  if command -v $b >/dev/null 2>&1; then echo "@@bin $b $( ( timeout 10 $b --version 2>/dev/null || $b --version 2>/dev/null ) | head -1 | tr ' ' '_')"; fi
done
[ -x /usr/local/bin/racklive-agent ] || [ -x "$HOME/.local/bin/racklive-agent" ] && echo "@@helper 1"
D="$HOME/.racklive-agents"
[ -f "$D/conf" ] && sed -n 's/^\(RC\|AUTO\|NAME\|MODEL\|AUTH\)=/@@conf \1 /p' "$D/conf"
[ -f "$D/env" ] && grep -o '^export [A-Z_]*' "$D/env" | sed 's/^export /@@envkey /'
command -v tmux >/dev/null 2>&1 && tmux ls 2>/dev/null | grep '^rl-' | sed 's/^/@@sess /'
if command -v claude >/dev/null 2>&1; then echo "@@cauth $( (timeout 15 claude auth status 2>&1) | head -3 | tr '\n' ' ' | cut -c1-200)"; fi
echo @@end
'''


def parse_status(out):
    s = {'bins': {}, 'conf': {}, 'envkeys': [], 'sessions': []}
    for l in out.splitlines():
        if not l.startswith('@@'):
            continue
        k, _, v = l[2:].partition(' ')
        v = v.strip()
        if k == 'bin':
            n, _, ver = v.partition(' ')
            s['bins'][n] = ver.replace('_', ' ')
        elif k == 'conf':
            n, _, val = v.partition(' ')
            s['conf'][n] = val.strip().strip('"\'')
        elif k == 'envkey':
            s['envkeys'].append(v)
        elif k == 'sess':
            m = re.match(r'(rl-[\w.\-]+):', v)
            if m:
                s['sessions'].append({'name': m.group(1), 'line': v})
        elif k != 'end':
            s[k] = v
    return s


def check_text(v, pat, what, maxlen=80):
    v = (v or '').strip()
    if v and (len(v) > maxlen or not re.match(pat, v)):
        raise ValueError(f'{what}: недопустимые символы')
    return v


PREREQ = PATHS + r'''
SUDO=""; [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null && SUDO=sudo
pm() { if command -v apt-get >/dev/null 2>&1; then DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y "$@";
  elif command -v apk >/dev/null 2>&1; then $SUDO apk add "$@"; elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y "$@";
  elif command -v yum >/dev/null 2>&1; then $SUDO yum install -y "$@"; elif command -v pacman >/dev/null 2>&1; then $SUDO pacman -S --noconfirm "$@"; else return 1; fi; }
command -v curl >/dev/null 2>&1 || pm curl ca-certificates >/dev/null 2>&1
command -v tmux >/dev/null 2>&1 || { command -v apt-get >/dev/null 2>&1 && $SUDO apt-get update -qq >/dev/null 2>&1; pm tmux >/dev/null 2>&1; }
command -v tmux >/dev/null 2>&1 || echo "@@fail не удалось поставить tmux (нужен root или sudo без пароля): apt install tmux"
echo "tmux: $(tmux -V)"
echo @@ok
'''

NODE = PATHS + r'''
SUDO=""; [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null && SUDO=sudo
need() { v=$(node -v 2>/dev/null | sed 's/v//;s/\..*//'); [ -n "$v" ] && [ "$v" -ge 18 ]; }
need || {
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq >/dev/null 2>&1; DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y nodejs npm >/dev/null 2>&1
    need || { curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO -E bash - >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y nodejs >/dev/null 2>&1; }
  elif command -v apk >/dev/null 2>&1; then $SUDO apk add nodejs npm >/dev/null 2>&1
  elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y nodejs npm >/dev/null 2>&1
  elif command -v yum >/dev/null 2>&1; then $SUDO yum install -y nodejs npm >/dev/null 2>&1; fi
}
need || { echo "@@fail нужен Node.js 18 или новее (сейчас: $(node -v 2>/dev/null || echo нет))"; exit 0; }
echo "node $(node -v), npm $(npm -v)"; echo @@ok
'''


def install_script(a, via_npm=False):
    """one agent: its own installer, or npm (-g into ~/.local if not root)"""
    npm = ('SUDO=""; [ "$(id -u)" != 0 ] && { mkdir -p "$HOME/.local"; npm config set prefix "$HOME/.local" >/dev/null 2>&1; }\n'
           f'npm install -g {shlex.quote(a["npm"])} 2>&1 | tail -5' if a.get('npm') else '')
    body = (npm if (via_npm or not a.get('install')) else a['install'] + ' 2>&1 | tail -8')
    return (PATHS + '\n' + body + '\n'
            f'command -v {a["bin"]} >/dev/null 2>&1 || {{ echo "@@fail {a["title"]} не появился в системе после установки"; exit 0; }}\n'
            f'echo "{a["title"]}: $( {a["bin"]} --version 2>/dev/null | head -1)"; echo @@ok\n')


def needs_node(a, ok_native=False):
    return bool(a.get('npm')) and not a.get('install')


HELPER = r'''#!/bin/bash
# racklive-agent — written by Rack Live. Chats live in tmux sessions named rl-*.
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$HOME/.aider/bin:/usr/local/bin:$PATH"
D="$HOME/.racklive-agents"; mkdir -p "$D"
[ -f "$D/env" ] && . "$D/env"
RC=0; AUTO=0; NAME="$(hostname)"; DIR="$HOME"; [ -f "$D/conf" ] && . "$D/conf"; [ -d "$DIR" ] || DIR="$HOME"
slug() { echo "$(echo "$1" | tr -c 'A-Za-z0-9\n' '-' | sed 's/--*/-/g;s/^-//;s/-$//' | cut -c1-24)-$(printf %s "$1" | cksum | cut -d' ' -f1)"; }   # readable part + a hash: Cyrillic names stay distinct
# the main chat CONTINUES the last conversation of its folder (after a reboot it is the same chat in the Claude app); a new one only when there is nothing to continue
mainsess() { tmux has-session -t rl-main 2>/dev/null && return 0
  if [ "$RC" = 1 ]; then tmux new-session -d -s rl-main -c "$DIR" "claude --continue --remote-control \"$NAME\" || claude --remote-control \"$NAME\""
  else tmux new-session -d -s rl-main -c "$DIR" "claude --continue || claude"; fi; }
chat() { s="rl-c-$(slug "$1")"; tmux has-session -t "$s" 2>/dev/null && { echo "$s уже запущен"; return 0; }
  if [ "$RC" = 1 ]; then tmux new-session -d -s "$s" -c "$HOME" "claude --remote-control \"$1\""; else tmux new-session -d -s "$s" -c "$HOME" "claude"; fi; echo "$s"; }
case "$1" in
  start-all) mainsess; [ -f "$D/chats" ] && while IFS= read -r n; do [ -n "$n" ] && chat "$n" >/dev/null; done < "$D/chats"; echo ok ;;
  new) n="${2:-Чат $(date +%H:%M)}"; chat "$n"; [ "$AUTO" = 1 ] && { grep -qxF "$n" "$D/chats" 2>/dev/null || echo "$n" >> "$D/chats"; } ;;
  list) tmux ls 2>/dev/null | grep '^rl-' ;;
  stop) if [ "$2" = all ]; then for s in $(tmux ls 2>/dev/null | grep '^rl-' | cut -d: -f1); do tmux kill-session -t "$s"; done
        else tmux kill-session -t "$2"; [ -f "$D/chats" ] && while IFS= read -r n; do [ "rl-c-$(slug "$n")" = "$2" ] && "$0" forget "$n"; done < "$D/chats"; fi ;;
  forget) [ -f "$D/chats" ] && grep -vxF "$2" "$D/chats" > "$D/chats.tmp"; mv -f "$D/chats.tmp" "$D/chats" 2>/dev/null ;;
  restart) for s in $(tmux ls 2>/dev/null | grep '^rl-' | cut -d: -f1); do tmux kill-session -t "$s"; done; "$0" start-all ;;
  attach) exec tmux attach -t "${2:-rl-main}" ;;
  setup)
    echo "── Шаг 1. Вход в аккаунт Claude (нужна подписка Pro / Max / Team) ──"
    if claude auth status >/dev/null 2>&1; then echo "Вход уже выполнен."; else claude auth login; fi
    echo; echo "── Шаг 2. Первый запуск Remote Control ──"
    echo "Ответьте y на вопросы «Enable Remote Control?» и «Trust ...?», дождитесь ссылки на сессию и нажмите Ctrl+C."
    cd "$DIR" && claude remote-control --name "$NAME"
    echo; echo "Готово. Запускаю сессию в фоне…"; "$0" restart; echo "Сессия «$NAME» ждёт вас в приложении Claude и на claude.ai/code." ;;
  *) echo "racklive-agent start-all | new [имя] | list | stop <имя|all> | restart | attach [сессия] | setup" ;;
esac
'''


def configure_script(rc, auto, name, model, auth, keys, strip=()):
    """write the helper, the env file (0600), the conf and the autostart. `keys` = {ENV_NAME: value} (already validated);
    variables in `keys` / `strip` are replaced / removed in the env file, all others stay as they were (keys given earlier are kept)"""
    env = ''.join(f'export {k}={shlex.quote(v)}\n' for k, v in keys.items())
    if model:
        env += f'export ANTHROPIC_MODEL={shlex.quote(model)}\n'
    names = sorted(set(keys) | set(strip) | {'ANTHROPIC_MODEL'})
    drop = ''.join(f'grep -v "^export {n}=" "$D/env" > "$D/env.tmp" 2>/dev/null; mv -f "$D/env.tmp" "$D/env" 2>/dev/null\n' for n in names)
    conf = f'RC={1 if rc else 0}\nAUTO={1 if auto else 0}\nNAME={shlex.quote(name)}\nMODEL={shlex.quote(model)}\nAUTH={shlex.quote(auth)}\n'
    return (PATHS + '\nD="$HOME/.racklive-agents"; mkdir -p "$D"; chmod 700 "$D"; touch "$D/env"; chmod 600 "$D/env"\n' + drop
            + f"cat >> \"$D/env\" <<'RL_ENV_EOF'\n{env}RL_ENV_EOF\nchmod 600 \"$D/env\"\n"
            'ODIR=$(grep "^DIR=" "$D/conf" 2>/dev/null)\n'                                    # the chat's working folder survives «Сохранить настройки»
            f"cat > \"$D/conf\" <<'RL_CONF_EOF'\n{conf}RL_CONF_EOF\n"
            '[ -n "$ODIR" ] && echo "$ODIR" >> "$D/conf"\n'
            f"cat > \"$D/racklive-agent\" <<'RL_HELPER_EOF'\n{HELPER}RL_HELPER_EOF\nchmod 755 \"$D/racklive-agent\"\n"
            'if [ "$(id -u)" = 0 ]; then ln -sf "$D/racklive-agent" /usr/local/bin/racklive-agent; else mkdir -p "$HOME/.local/bin"; ln -sf "$D/racklive-agent" "$HOME/.local/bin/racklive-agent"; fi\n'
            # keys also for hand-made sessions: a login shell reads them
            'for f in "$HOME/.profile" "$HOME/.bashrc"; do [ -f "$f" ] || continue; grep -q racklive-agents "$f" 2>/dev/null || printf \'\\n[ -f "$HOME/.racklive-agents/env" ] && . "$HOME/.racklive-agents/env"  # Rack Live\\n\' >> "$f"; done\n'
            + AUTOSTART.replace('@AUTO@', '1' if auto else '0') + 'echo @@ok\n')


AUTOSTART = r'''
CRONTMP=$(mktemp); (crontab -l 2>/dev/null | grep -v racklive-agent) > "$CRONTMP"
if [ "$(id -u)" = 0 ] && [ -d /run/systemd/system ]; then
  crontab "$CRONTMP" 2>/dev/null
  if [ "@AUTO@" = 1 ]; then
    cat > /etc/systemd/system/racklive-agent.service <<'RL_UNIT_EOF'
[Unit]
Description=Rack Live: AI agent sessions (tmux)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=HOME=/root
ExecStart=/usr/local/bin/racklive-agent start-all
ExecStop=/usr/local/bin/racklive-agent stop all

[Install]
WantedBy=multi-user.target
RL_UNIT_EOF
    systemctl daemon-reload && systemctl enable racklive-agent.service >/dev/null 2>&1 && echo "автозапуск: служба systemd racklive-agent включена"
  else
    systemctl disable racklive-agent.service >/dev/null 2>&1; rm -f /etc/systemd/system/racklive-agent.service; systemctl daemon-reload 2>/dev/null
  fi
else
  if [ "@AUTO@" = 1 ]; then echo "@reboot $HOME/.racklive-agents/racklive-agent start-all >/dev/null 2>&1  # racklive-agent" >> "$CRONTMP"; echo "автозапуск: cron @reboot"; fi
  crontab "$CRONTMP" 2>/dev/null
fi
rm -f "$CRONTMP"
'''


def remove_script(a):
    if a['id'] == 'claude':
        pre = ('racklive-agent stop all 2>/dev/null; systemctl disable --now racklive-agent.service >/dev/null 2>&1; rm -f /etc/systemd/system/racklive-agent.service\n'
               '(crontab -l 2>/dev/null | grep -v racklive-agent) | crontab - 2>/dev/null\n'
               'rm -f /usr/local/bin/racklive-agent "$HOME/.local/bin/racklive-agent"; rm -rf "$HOME/.racklive-agents"\n')
    else:
        pre = ''
    cmds = {
        'claude': 'rm -f "$HOME/.local/bin/claude"; rm -rf "$HOME/.local/share/claude"; npm uninstall -g @anthropic-ai/claude-code >/dev/null 2>&1',
        'codex': 'npm uninstall -g @openai/codex 2>&1 | tail -2',
        'gemini': 'npm uninstall -g @google/gemini-cli 2>&1 | tail -2',
        'opencode': 'rm -rf "$HOME/.opencode"; npm uninstall -g opencode-ai >/dev/null 2>&1',
        'aider': 'rm -rf "$HOME/.local/bin/aider" "$HOME/.local/share/uv/tools/aider-chat" 2>/dev/null; pipx uninstall aider-chat >/dev/null 2>&1',
    }
    return PATHS + '\n' + pre + cmds[a['id']] + '\necho @@ok\n'
