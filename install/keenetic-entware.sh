#!/bin/sh
# Rack Live — установка на Keenetic / Netcraze через Entware.
#
#   sh keenetic-entware.sh            установить (или обновить) и запустить
#   sh keenetic-entware.sh update     то же самое: скачать свежую версию, данные остаются
#   sh keenetic-entware.sh uninstall  удалить программу (данные остаются; RL_PURGE=1 — удалить и их)
#   sh keenetic-entware.sh status     запущен ли Rack Live и по какому адресу
#
# Настройки (необязательно, переменными окружения перед командой):
#   RL_PORT=8080            порт панели
#   RL_DATA=/opt/var/racklive   где хранить данные (настройки устройств, история) — на флешке Entware
#   RL_SRC=/путь/к/racklive.tar.gz   взять программу из файла или папки, а не из интернета
#   RL_REF=v2.6.0           поставить конкретную версию (метку) вместо последней: так обновляйте роутеры
#                           только после проверки новой версии на основном устройстве
#   RL_URL=https://…/racklive.tar.gz  другой адрес архива
#
# Нужно: установленный Entware на флешке или диске (инструкция: https://help.keenetic.com/hc/ru/articles/360021214160).
set -u

PREFIX="${RL_PREFIX:-/opt}"
APP="$PREFIX/share/racklive"
DATA="${RL_DATA:-$PREFIX/var/racklive}"
PORT="${RL_PORT:-8080}"
URL="${RL_URL:-https://github.com/mikolord/racklive/archive/${RL_REF:-main}.tar.gz}"
INIT="$PREFIX/etc/init.d/S98racklive"
LOG="$PREFIX/var/log/racklive.log"
CMD="${1:-install}"

say() { printf '%s\n' "$*"; }
die() { printf '\n[ОШИБКА] %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

lan_ip() {
  ip -4 addr show br0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1
}

stop_service() { [ -x "$INIT" ] && "$INIT" stop >/dev/null 2>&1; return 0; }

do_status() {
  if [ -x "$INIT" ]; then "$INIT" status; else say "Rack Live не установлен ($INIT не найден)"; fi
  ip="$(lan_ip)"; [ -n "$ip" ] && say "Адрес панели: http://$ip:$PORT"
}

do_uninstall() {
  stop_service
  have crontab && { crontab -l 2>/dev/null | grep -v "S98racklive watch" | crontab - 2>/dev/null; }
  rm -f "$INIT"; rm -rf "$APP"
  if [ "${RL_PURGE:-0}" = 1 ]; then rm -rf "$DATA" "$LOG" "$LOG.1"; say "Rack Live и все его данные удалены."
  else say "Rack Live удалён. Данные оставлены в $DATA (удалить: RL_PURGE=1 sh $0 uninstall)."; fi
  exit 0
}

case "$CMD" in
  status) do_status; exit 0 ;;
  uninstall) do_uninstall ;;
  install|update) ;;
  *) die "неизвестная команда «$CMD». Допустимо: install, update, uninstall, status" ;;
esac

say "== Rack Live для Keenetic / Netcraze (Entware) =="

# 1. Entware на месте?
if [ -z "${RL_SKIP_PKG:-}" ]; then
  have opkg || [ -x "$PREFIX/bin/opkg" ] || die "Entware не найден. Сначала установите Entware на флешку (инструкция: https://help.keenetic.com/hc/ru/articles/360021214160), затем запустите скрипт ещё раз из Entware (ssh на порт 222, пользователь root)."
  PATH="$PREFIX/bin:$PREFIX/sbin:$PREFIX/usr/bin:$PATH"; export PATH
  free_kb="$(df -k "$PREFIX" 2>/dev/null | awk 'NR==2{print $4}')"
  [ -n "$free_kb" ] && [ "$free_kb" -lt 120000 ] && die "На разделе Entware мало места ($((free_kb/1024)) МБ). Нужно хотя бы 120 МБ."
  # 2. пакеты
  say "-- Пакеты (python3, curl, tar, ca-certificates, openssh-client) — несколько минут..."
  opkg update || die "opkg update не удался: проверьте интернет на роутере."
  opkg install python3 ca-certificates curl tar unzip openssh-client || die "не удалось поставить пакеты через opkg."
  opkg install sshpass >/dev/null 2>&1 || say "   (пакета sshpass в Entware нет — это нормально: Rack Live входит по паролю средствами самого ssh)"
fi
have python3 || [ -n "${RL_SKIP_PKG:-}" ] || die "python3 не установился."

# 3. программа
STAGE="${TMPDIR:-$PREFIX/tmp}/racklive-src.$$"
mkdir -p "$STAGE" || die "не могу создать $STAGE"
trap 'rm -rf "$STAGE"' EXIT INT TERM
SRCDIR=""
if [ -n "${RL_SRC:-}" ] && [ -d "$RL_SRC" ]; then
  SRCDIR="$RL_SRC"
else
  FILE="${RL_SRC:-}"
  if [ -z "$FILE" ]; then
    FILE="$STAGE/racklive.tar.gz"
    say "-- Скачиваю $URL"
    if have curl; then curl -fL --retry 3 -o "$FILE" "$URL" || die "не скачалось. Если GitHub недоступен — скачайте архив на компьютере и передайте на роутер (см. инструкцию, способ «без интернета»)."
    elif have wget; then wget -O "$FILE" "$URL" || die "не скачалось."
    else die "нет ни curl, ни wget."; fi
  fi
  [ -f "$FILE" ] || die "файл $FILE не найден"
  say "-- Распаковываю"
  case "$FILE" in
    *.zip) have unzip || die "нужен unzip"; unzip -q -o "$FILE" -d "$STAGE/x" || die "zip не распаковался" ;;
    *) mkdir -p "$STAGE/x"; top="$(tar -tzf "$FILE" | head -1 | cut -d/ -f1)"
       tar -xzf "$FILE" -C "$STAGE/x" "$top/rackd" "$top/web" 2>/dev/null || tar -xzf "$FILE" -C "$STAGE/x" || die "архив не распаковался" ;;
  esac
  SRCDIR="$(find "$STAGE/x" -maxdepth 2 -type d -name rackd 2>/dev/null | head -1)"; SRCDIR="${SRCDIR%/rackd}"
fi
[ -n "$SRCDIR" ] && [ -d "$SRCDIR/rackd" ] && [ -d "$SRCDIR/web" ] || die "в архиве нет папок rackd и web — это точно архив Rack Live?"

say "-- Устанавливаю в $APP"
stop_service
mkdir -p "$APP" "$DATA" "$(dirname "$LOG")" "$PREFIX/var/run" "$(dirname "$INIT")"
rm -rf "$APP/rackd" "$APP/web"
cp -R "$SRCDIR/rackd" "$APP/rackd" && cp -R "$SRCDIR/web" "$APP/web" || die "не удалось скопировать файлы"
rm -rf "$APP/web/src" "$APP/web/.bundle.jsx" "$APP/rackd/__pycache__"

# 4. служба
cat >"$INIT" <<EOF
#!/bin/sh
# Rack Live — служба для Entware (создано установщиком)
PATH=$PREFIX/bin:$PREFIX/sbin:$PREFIX/usr/bin:/usr/sbin:/usr/bin:/sbin:/bin
APP="$APP"; DATA="$DATA"; PORT="$PORT"; LOG="$LOG"; PID="$PREFIX/var/run/racklive.pid"; STOPPED="$PREFIX/var/run/racklive.stopped"
running() { [ -f "\$PID" ] && kill -0 "\$(cat "\$PID")" 2>/dev/null; }
case "\$1" in
  start)
    running && { echo "Rack Live уже запущен"; exit 0; }
    rm -f "\$STOPPED"
    mkdir -p "\$DATA"
    [ -f "\$LOG" ] && [ "\$(wc -c <"\$LOG")" -gt 1048576 ] && mv "\$LOG" "\$LOG.1"
    cd "\$APP" || exit 1
    RL_DATA="\$DATA" RL_PORT="\$PORT" RL_WEB="\$APP/web" PYTHONUNBUFFERED=1 nohup python3 -m rackd >>"\$LOG" 2>&1 &
    echo \$! >"\$PID"; sleep 2
    if running; then echo "Rack Live запущен (порт \$PORT)"; else echo "Rack Live не запустился, смотрите \$LOG"; exit 1; fi ;;
  stop)
    if running; then kill "\$(cat "\$PID")"; i=0; while running && [ \$i -lt 10 ]; do sleep 1; i=\$((i+1)); done; running && kill -9 "\$(cat "\$PID")"; fi
    rm -f "\$PID"; touch "\$STOPPED"; echo "Rack Live остановлен" ;;
  watch) [ -f "\$STOPPED" ] && exit 0; running || "\$0" start >/dev/null 2>&1 ;;
  restart) "\$0" stop; "\$0" start ;;
  status|check) if running; then echo "Rack Live работает (pid \$(cat "\$PID"), порт \$PORT)"; else echo "Rack Live не запущен"; exit 1; fi ;;
  *) echo "Использование: \$0 {start|stop|restart|status}"; exit 1 ;;
esac
EOF
chmod +x "$INIT"

# авто-перезапуск: раз в минуту cron проверяет, жив ли Rack Live, и поднимает его, если упал (ручная остановка уважается)
if have crontab; then
  ( crontab -l 2>/dev/null | grep -v "S98racklive watch"; echo "* * * * * $INIT watch >/dev/null 2>&1" ) | crontab - 2>/dev/null \
    && say "-- Авто-перезапуск включён (cron, раз в минуту)" || say "   (cron недоступен — авто-перезапуска не будет)"
else
  say "   (команды crontab нет — авто-перезапуска не будет)"
fi

if [ -z "${RL_SKIP_START:-}" ]; then
  say "-- Запускаю"
  "$INIT" start || die "не запустился. Лог: tail -n 40 $LOG"
fi

ip="$(lan_ip)"; [ -z "$ip" ] && ip="IP-адрес-роутера"
say ""
say "Готово!"
say "  Панель:     http://$ip:$PORT   (при первом входе задайте пароль администратора)"
say "  Данные:     $DATA"
say "  Управление: $INIT {start|stop|restart|status}   — запускается вместе с Entware сам"
say "  Обновить:   sh $0 update"
say "Не открывайте порт $PORT в интернет — панель только для домашней сети."
