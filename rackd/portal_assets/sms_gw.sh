#!/bin/sh
# Rack Live: prepares the router that holds the SIM card (runs ON that router, started by the portal router over SSH).
#   sh sms_gw.sh net <portal router address>   the router gets internet through the portal router (for packages), mobile data is not used
#   sh sms_gw.sh sms                           stty + modem port + /usr/bin/rl-sms + the portal router's key (forced command)
PM=opkg; command -v apk >/dev/null 2>&1 && PM=apk
pkg() { if [ $PM = apk ]; then apk add "$@" </dev/null; else opkg install "$@" </dev/null; fi; }
upd() { if [ $PM = apk ]; then apk update </dev/null; else opkg update </dev/null; fi; }

case "$1" in
net)
	GW=$2
	[ "$(uci -q get network.lan.gateway)" = "$GW" ] && { echo "@@net ok"; exit 0; }
	uci set network.lan.gateway="$GW"; uci -q delete network.lan.dns; uci add_list network.lan.dns="$GW"
	for w in wwan wwan6 wan wan6; do uci -q get network.$w >/dev/null && { uci set network.$w.defaultroute=0; uci set network.$w.peerdns=0; }; done
	uci -q set dhcp.@dnsmasq[0].filter_aaaa=1
	uci commit network; uci commit dhcp
	setsid sh -c 'sleep 2; /etc/init.d/network restart; sleep 6; /etc/init.d/dnsmasq restart' </dev/null >/dev/null 2>&1 &
	echo "@@net restarting"
	;;
sms)
	if ! command -v stty >/dev/null 2>&1; then
		echo "@@step Ставлю пакет coreutils-stty"
		n=0; while ! command -v stty >/dev/null 2>&1 && [ $n -lt 3 ]; do upd >/dev/null 2>&1; pkg coreutils-stty >/tmp/rl-pkg.log 2>&1; n=$((n+1)); command -v stty >/dev/null 2>&1 || sleep 5; done
		command -v stty >/dev/null 2>&1 || { echo "@@fail не удалось поставить coreutils-stty: нет интернета у роутера с SIM (проверьте, что его LAN-порт в LAN у главного роутера) — $(tail -1 /tmp/rl-pkg.log)"; exit 0; }
	fi
	if ! ls /dev/ttyUSB* >/dev/null 2>&1; then
		echo "@@step Ставлю драйвер последовательных портов модема"
		upd >/dev/null 2>&1; pkg kmod-usb-serial-option kmod-usb-serial-wwan >/dev/null 2>&1; sleep 4
		ls /dev/ttyUSB* >/dev/null 2>&1 || { echo "@@fail у роутера нет портов модема /dev/ttyUSB*. Так работают модемы с командами AT; модем в режиме «сетевая карта» (HiLink) СМС по AT не отдаёт"; exit 0; }
	fi
	echo "@@step Ищу порт модема"
	DEV=""
	for d in /dev/ttyUSB*; do
		if ( stty -F "$d" 115200 raw -echo 2>/dev/null; exec 3<>"$d"; printf 'ATE0\r' >&3; n=0; while read -t 2 -r l <&3; do case "$l" in *OK*) exit 0 ;; esac; n=$((n+1)); [ $n -gt 6 ] && break; done; exit 1 ); then DEV=$d; break; fi
	done
	[ -n "$DEV" ] || { echo "@@fail ни один порт /dev/ttyUSB* не отвечает на команды AT"; exit 0; }
	echo "DEV=$DEV" > /etc/rl-sms.conf
	mv /tmp/rl-sms.new /usr/bin/rl-sms; chmod 755 /usr/bin/rl-sms
	mkdir -p /etc/dropbear; touch /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys
	sed -i '/rl-sms/d' /etc/dropbear/authorized_keys
	echo "command=\"/usr/bin/rl-sms\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $(cat /tmp/rl-pub)" >> /etc/dropbear/authorized_keys
	rm -f /tmp/rl-pub
	echo "@@port $DEV"
	;;
esac
