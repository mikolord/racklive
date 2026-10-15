#!/bin/sh
# Rack Live — установка на OpenWrt (apk или opkg).
#
#   sh openwrt.sh            установить (или обновить) и запустить
#   sh openwrt.sh update     то же самое: скачать свежую версию, данные остаются
#   sh openwrt.sh uninstall  удалить программу (данные остаются; RL_PURGE=1 — удалить и их)
#   sh openwrt.sh status     запущен ли Rack Live и по какому адресу
#
# Настройки (необязательно, переменными окружения перед командой):
#   RL_PORT=8080             порт панели
#   RL_DATA=/mnt/sda1/racklive   где хранить данные. ОЧЕНЬ советуем USB-флешку: Rack Live часто пишет
#                                историю, а флеш-память роутера от этого изнашивается.
#   RL_SRC=/путь/к/racklive.tar.gz   взять программу из файла или папки, а не из интернета
#   RL_REF=v2.5.0           поставить конкретную версию (метку) вместо последней: так обновляйте роутеры
#                           только после проверки новой версии на основном устройстве
#   RL_URL=https://…/racklive.tar.gz  другой адрес архива
#
# Нужно: ~40 МБ свободного места и ~30 МБ свободной памяти (лучше 128 МБ ОЗУ и больше).
set -u

PREFIX="${RL_PREFIX:-}"
APP="$PREFIX/usr/share/racklive"
PORT="${RL_PORT:-8080}"
URL="${RL_URL:-https://github.com/mikolord/racklive/archive/${RL_REF:-main}.tar.gz}"
INIT="$PREFIX/etc/init.d/racklive"
CMD="${1:-install}"

say() { printf '%s\n' "$*"; }
die() { printf '\n[ОШИБКА] %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

lan_ip() {
  v="$(uci -q get network.lan.ipaddr 2>/dev/null | cut -d/ -f1)"
  [ -z "$v" ] && v="$(ip -4 addr show br-lan 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)"
  printf '%s' "$v"
}

# где хранить данные: заданное → смонтированная флешка → папка в /root (с предупреждением)
pick_data() {
  [ -n "${RL_DATA:-}" ] && { printf '%s' "$RL_DATA"; return; }
  for m in /mnt/*; do
    [ -d "$m" ] && grep -q " $m " /proc/mounts 2>/dev/null && { printf '%s' "$m/racklive"; return; }
  done
  printf '%s' "$PREFIX/root/racklive-data"
}
DATA="$(pick_data)"

pm_install() {
  if have apk; then apk add "$@"; else opkg install "$@"; fi
}

do_status() {
  if [ -x "$INIT" ]; then "$INIT" status; else say "Rack Live не установлен ($INIT не найден)"; fi
  ip="$(lan_ip)"; [ -n "$ip" ] && say "Адрес панели: http://$ip:$PORT"
}

do_uninstall() {
  [ -x "$INIT" ] && { "$INIT" stop >/dev/null 2>&1; "$INIT" disable >/dev/null 2>&1; }
  rm -f "$INIT"; rm -rf "$APP"
  if [ "${RL_PURGE:-0}" = 1 ]; then rm -rf "$DATA"; say "Rack Live и все его данные удалены."
  else say "Rack Live удалён. Данные оставлены в $DATA (удалить: RL_PURGE=1 sh $0 uninstall). Пакеты python3 не удалялись."; fi
  exit 0
}

case "$CMD" in
  status) do_status; exit 0 ;;
  uninstall) do_uninstall ;;
  install|update) ;;
  *) die "неизвестная команда «$CMD». Допустимо: install, update, uninstall, status" ;;
esac

say "== Rack Live для OpenWrt =="

# 1. хватит ли ресурсов
mem_kb="$(awk '/MemAvailable/{print $2}' /proc/meminfo 2>/dev/null)"
[ -n "$mem_kb" ] && [ "$mem_kb" -lt 30000 ] && say "!! Свободной памяти мало ($((mem_kb/1024)) МБ). Rack Live может работать нестабильно; закройте лишнее или ставьте на NAS / мини-ПК."
fl_kb="$(df -k "${PREFIX:-/}overlay" 2>/dev/null | awk 'NR==2{print $4}')"; [ -z "$fl_kb" ] && fl_kb="$(df -k "${PREFIX:-/}" 2>/dev/null | awk 'NR==2{print $4}')"
[ -n "$fl_kb" ] && [ "$fl_kb" -lt 40000 ] && die "На роутере мало места ($((fl_kb/1024)) МБ), нужно хотя бы 40 МБ (python3 + Rack Live)."
case "$DATA" in /mnt/*) : ;; *) say "!! Данные будут в $DATA — это память самого роутера. Для долгой жизни флеш-памяти воткните USB-флешку и запустите: RL_DATA=/mnt/sda1/racklive sh $0" ;; esac

# 2. пакеты
if [ -z "${RL_SKIP_PKG:-}" ]; then
  if have apk; then say "-- Обновляю список пакетов (apk)"; apk update || die "apk update не удался: проверьте интернет на роутере."
  elif have opkg; then say "-- Обновляю список пакетов (opkg)"; opkg update || die "opkg update не удался: проверьте интернет на роутере."
  else die "не найден ни apk, ни opkg — это точно OpenWrt?"; fi
  say "-- Ставлю Python и нужные модули (несколько минут)"
  pm_install python3-light python3-openssl python3-urllib python3-email python3-codecs ca-bundle curl openssh-client sshpass \
    || die "не удалось поставить пакеты. Проверьте интернет и свободное место (df -h)."
  # проверка: все модули, которые использует Rack Live
  CHECK='import ssl,http.server,urllib.request,smtplib,email.mime.text,concurrent.futures,hashlib,hmac,json,socket,threading,shlex,secrets,statistics,difflib,ipaddress,mimetypes,gzip,html,base64,struct,platform,argparse,random'
  if ! python3 -c "$CHECK" 2>/dev/null; then
    say "-- Не хватает модулей Python, ставлю полный python3 (займёт больше места)"
    pm_install python3 || die "не удалось поставить python3."
    python3 -c "$CHECK" || die "Python всё равно не может загрузить нужные модули."
  fi
else
  :
fi
have python3 || [ -n "${RL_SKIP_PKG:-}" ] || die "python3 не установился."

# 3. программа
TMP="${TMPDIR:-/tmp}"; STAGE="$TMP/racklive-src.$$"
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
    elif have uclient-fetch; then uclient-fetch -O "$FILE" "$URL" || die "не скачалось."
    else die "нет ни curl, ни uclient-fetch."; fi
  fi
  [ -f "$FILE" ] || die "файл $FILE не найден"
  say "-- Распаковываю"
  case "$FILE" in
    *.zip) have unzip || pm_install unzip; unzip -q -o "$FILE" -d "$STAGE/x" || die "zip не распаковался" ;;
    *) mkdir -p "$STAGE/x"; top="$(tar -tzf "$FILE" | head -1 | cut -d/ -f1)"
       tar -xzf "$FILE" -C "$STAGE/x" "$top/rackd" "$top/web" 2>/dev/null || tar -xzf "$FILE" -C "$STAGE/x" || die "архив не распаковался" ;;
  esac
  SRCDIR="$(find "$STAGE/x" -maxdepth 2 -type d -name rackd 2>/dev/null | head -1)"; SRCDIR="${SRCDIR%/rackd}"
fi
[ -n "$SRCDIR" ] && [ -d "$SRCDIR/rackd" ] && [ -d "$SRCDIR/web" ] || die "в архиве нет папок rackd и web — это точно архив Rack Live?"

say "-- Устанавливаю в $APP"
[ -x "$INIT" ] && "$INIT" stop >/dev/null 2>&1
mkdir -p "$APP" "$DATA" "$(dirname "$INIT")"
rm -rf "$APP/rackd" "$APP/web"
cp -R "$SRCDIR/rackd" "$APP/rackd" && cp -R "$SRCDIR/web" "$APP/web" || die "не удалось скопировать файлы"
rm -rf "$APP/web/src" "$APP/web/.bundle.jsx" "$APP/rackd/__pycache__"

# 4. служба procd (перезапускается сама, стартует при загрузке)
cat >"$INIT" <<'EOF'
#!/bin/sh /etc/rc.common
# Rack Live — служба OpenWrt (создано установщиком)
START=95
STOP=10
USE_PROCD=1

start_service() {
	mkdir -p "@DATA@"
	procd_open_instance
	procd_set_param command python3 -m rackd
	procd_set_param dir "@APP@"
	procd_set_param env RL_DATA="@DATA@" RL_PORT="@PORT@" RL_WEB="@APP@/web" PYTHONUNBUFFERED=1
	procd_set_param respawn 3600 5 5
	procd_set_param stdout 1
	procd_set_param stderr 1
	procd_close_instance
}
EOF
sed -i "s|@DATA@|$DATA|g; s|@APP@|$APP|g; s|@PORT@|$PORT|g" "$INIT"
chmod +x "$INIT"

if [ -z "${RL_SKIP_START:-}" ]; then
  say "-- Запускаю"
  "$INIT" enable
  "$INIT" restart
  sleep 3
  if netstat -ln 2>/dev/null | grep -q ":$PORT "; then :; else
    say "!! Порт $PORT пока не слушается. Лог: logread -e racklive | tail -n 30"
  fi
fi

ip="$(lan_ip)"; [ -z "$ip" ] && ip="IP-адрес-роутера"
say ""
say "Готово!"
say "  Панель:     http://$ip:$PORT   (при первом входе задайте пароль администратора)"
say "  Данные:     $DATA"
say "  Управление: /etc/init.d/racklive {start|stop|restart|status}   — стартует при загрузке сам"
say "  Обновить:   sh $0 update"
say "Из интернета (WAN) порт $PORT закрыт файрволом по умолчанию — так и оставьте."
