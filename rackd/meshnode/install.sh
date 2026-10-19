#!/bin/sh
# Rack Live вЂ” СѓСЃС‚Р°РЅРѕРІРєР° СѓР·Р»Р° Keenetic Mesh РЅР° OpenWrt (СѓРЅРёРІРµСЂСЃР°Р»СЊРЅРѕ).
# Р”РµР»Р°РµС‚ СЂРѕСѓС‚РµСЂ В«С‚РѕС‡РєРѕР№ РґРѕСЃС‚СѓРїР°В» СЃРёСЃС‚РµРјС‹ Keenetic: СЃС‚Р°РІРёС‚ РїР°РєРµС‚С‹, СЃР»СѓР¶Р±Сѓ mws,
# Рё (РїРѕ Р¶РµР»Р°РЅРёСЋ) РїРµСЂРµРІРѕРґРёС‚ СЂРѕСѓС‚РµСЂ РІ СЂРµР¶РёРј dumb-AP. Р—Р°РїСѓСЃРє: sh install.sh [--dumb-ap <ip>] [--uninstall]
set -e
DIR=/etc/mws
SBIN=/usr/sbin/mws_stub.py
INIT=/etc/init.d/mws
LOG=/tmp/mws.log
SRC_STUB="${SRC_STUB:-$(dirname "$0")/mws_stub.py}"

say() { echo "mws-install: $*"; }
die() { echo "mws-install РћРЁРР‘РљРђ: $*" >&2; exit 1; }

pkg_install() {
	if command -v apk >/dev/null 2>&1; then
		apk update >/dev/null 2>&1 || true
		for p in "$@"; do apk add --no-progress "$p" >/dev/null 2>&1 || say "РЅРµ РїРѕСЃС‚Р°РІРёР»СЃСЏ РїР°РєРµС‚ $p"; done
	else
		opkg update >/dev/null 2>&1 || true
		for p in "$@"; do opkg install "$p" >/dev/null 2>&1 || say "РЅРµ РїРѕСЃС‚Р°РІРёР»СЃСЏ РїР°РєРµС‚ $p"; done
	fi
}

uninstall() {
	say "СѓРґР°Р»РµРЅРёРµ"
	[ -x "$INIT" ] && { "$INIT" stop 2>/dev/null || true; "$INIT" disable 2>/dev/null || true; }
	# СЃРЅСЏС‚СЊ СЃРµС‚Рё mws (РІРµСЂРЅСѓС‚СЊ СЃРІРѕР№ Wi-Fi)
	for s in $(uci show wireless 2>/dev/null | sed -n "s/^wireless\.\(mws_[A-Za-z0-9_]*\)=.*/\1/p"); do uci -q delete wireless."$s"; done
	for s in $(uci show network 2>/dev/null | sed -n "s/^network\.\(mws_[A-Za-z0-9_]*\)=.*/\1/p"); do uci -q delete network."$s"; done
	for s in $(uci show wireless 2>/dev/null | sed -n "s/^wireless\.\([A-Za-z0-9_]*\)\.disabled='1'/\1/p"); do
		case "$s" in default_radio*) uci -q set wireless."$s".disabled='0';; esac
	done
	uci -q commit wireless; uci -q commit network
	wifi reload 2>/dev/null || true
	# РІРµСЂРЅСѓС‚СЊ РІРµР±-РёРЅС‚РµСЂС„РµР№СЃСѓ OpenWrt РїРѕСЂС‚ 443 (HTTPS), РєРѕС‚РѕСЂС‹Р№ РјС‹ РѕС‚РґР°РІР°Р»Рё РЅР°С€РµР№ СЃР»СѓР¶Р±Рµ
	if uci -q get uhttpd.main >/dev/null 2>&1 && ! uci -q get uhttpd.main.listen_https >/dev/null 2>&1; then
		uci add_list uhttpd.main.listen_https='0.0.0.0:443'
		uci add_list uhttpd.main.listen_https='[::]:443'
		uci -q delete uhttpd.main.redirect_https
		uci commit uhttpd
		/etc/init.d/uhttpd restart 2>/dev/null || true
	fi
	rm -f "$INIT" "$SBIN"; rm -rf "$DIR"
	say "РіРѕС‚РѕРІРѕ. РЈР·РµР» СѓРґР°Р»С‘РЅ РёР· СЃРёСЃС‚РµРјС‹ (РІ Keenetic Р·Р°РїРёСЃСЊ РјРѕР¶РЅРѕ СѓР±СЂР°С‚СЊ РёР· РІРµР±-РёРЅС‚РµСЂС„РµР№СЃР°)."
	exit 0
}

[ "$1" = "--uninstall" ] && uninstall

[ -f "$SRC_STUB" ] || die "РЅРµС‚ С„Р°Р№Р»Р° Р·Р°РіР»СѓС€РєРё $SRC_STUB"
command -v openssl >/dev/null 2>&1 || true

# 1. РїР°РєРµС‚С‹: python3-light (RCI РЅР° РїРёС‚РѕРЅРµ), openssl-util (РєР»СЋС‡/CSR), wpad c SAE (WPA3)
say "СЃС‚Р°РІР»СЋ РїР°РєРµС‚С‹"
pkg_install python3-light openssl-util iw
command -v openssl >/dev/null 2>&1 || pkg_install openssl-util
# wpad: РґР»СЏ WPA3 РЅСѓР¶РµРЅ РІР°СЂРёР°РЅС‚ СЃ SAE. wpad-mini/basic (Р±РµР· mbedtls/openssl) РµРіРѕ РЅРµ СѓРјРµСЋС‚ вЂ” РґРѕСЃС‚Р°РІРёРј.
if command -v apk >/dev/null 2>&1; then INSTALLED=$(apk list -I 2>/dev/null); else INSTALLED=$(opkg list-installed 2>/dev/null); fi
case "$INSTALLED" in
	*wpad-basic-mbedtls*|*wpad-mbedtls*|*wpad-openssl*|*wpad-wolfssl*) : ;;   # СѓР¶Рµ СЃ SAE
	*) say "СЃС‚Р°РІР»СЋ wpad СЃ РїРѕРґРґРµСЂР¶РєРѕР№ WPA3"; pkg_install wpad-basic-mbedtls || pkg_install wpad-mbedtls || true ;;
esac

command -v python3 >/dev/null 2>&1 || die "РЅРµС‚ python3 вЂ” РЅР° СЌС‚РѕРј СЂРѕСѓС‚РµСЂРµ РјР°Р»Рѕ РїР°РјСЏС‚Рё РґР»СЏ СѓР·Р»Р°"
command -v openssl >/dev/null 2>&1 || die "РЅРµС‚ openssl вЂ” РїРѕСЃС‚Р°РІСЊС‚Рµ openssl-util"
iw dev 2>/dev/null | grep -q Interface || die "РЅРµС‚ Wi-Fi (mac80211) вЂ” СЌС‚РѕС‚ СЂРѕСѓС‚РµСЂ РЅРµ РіРѕРґРёС‚СЃСЏ РІ С‚РѕС‡РєСѓ РґРѕСЃС‚СѓРїР°"

# 1b. РѕСЃРІРѕР±РѕРґРёС‚СЊ 443 РґР»СЏ СЃР»СѓР¶Р±С‹: Keenetic РѕР±С‰Р°РµС‚СЃСЏ СЃ С‚РѕС‡РєР°РјРё РїРѕ HTTPS:443, Р° РІРµР±-РёРЅС‚РµСЂС„РµР№СЃ OpenWrt (uhttpd) С‚РѕР¶Рµ
# Р·Р°РЅРёРјР°РµС‚ 443 вЂ” РёР·-Р·Р° РєРѕРЅС„Р»РёРєС‚Р° uhttpd РЅРµ СЃС‚Р°СЂС‚СѓРµС‚ Рё РїСЂРѕРїР°РґР°РµС‚ РїРѕСЂС‚ 80 (С‡РµСЂРµР· РЅРµРіРѕ Rack Live РѕРїСЂР°С€РёРІР°РµС‚ СЂРѕСѓС‚РµСЂ).
# РЈР±РёСЂР°РµРј Сѓ uhttpd https-СЃР»СѓС€Р°С‚РµР»СЊ, РѕСЃС‚Р°РІР»СЏСЏ РµРјСѓ 80 (LuCI + ubus СЂР°Р±РѕС‚Р°СЋС‚, 443 РґРѕСЃС‚Р°С‘С‚СЃСЏ РЅР°С€РµР№ СЃР»СѓР¶Р±Рµ).
if uci -q get uhttpd.main.listen_https >/dev/null 2>&1; then
	say "РѕСЃРІРѕР±РѕР¶РґР°СЋ РїРѕСЂС‚ 443 РґР»СЏ Mesh (РІРµР±-РёРЅС‚РµСЂС„РµР№СЃ OpenWrt РѕСЃС‚Р°С‘С‚СЃСЏ РЅР° РїРѕСЂС‚Сѓ 80)"
	uci -q delete uhttpd.main.listen_https
	uci -q set uhttpd.main.redirect_https='0'
	uci commit uhttpd
	/etc/init.d/uhttpd restart 2>/dev/null || true
fi

# 2. С„Р°Р№Р»С‹
say "СЃС‚Р°РІР»СЋ СЃР»СѓР¶Р±Сѓ"
mkdir -p "$DIR"
cp "$SRC_STUB" "$SBIN"; chmod 755 "$SBIN"

cat > "$INIT" <<'EOF'
#!/bin/sh /etc/rc.common
# РЈР·РµР» Keenetic Mesh (Rack Live). HTTP 8090 вЂ” РїСЂРёС‘Рј, HTTPS 443 вЂ” С‡Р»РµРЅ СЃРёСЃС‚РµРјС‹.
START=95
STOP=10
USE_PROCD=1
start_service() {
	procd_open_instance
	procd_set_param command /usr/bin/python3 /usr/sbin/mws_stub.py \
		--iface br-lan --port 8090 --tls-port 443 --dir /etc/mws --log /tmp/mws.log
	procd_set_param respawn 3600 5 20
	procd_set_param stdout 1
	procd_set_param stderr 1
	procd_close_instance
}
EOF
chmod 755 "$INIT"

# 3. Р·Р°РїСѓСЃРє СЃР»СѓР¶Р±С‹ (Р”Рћ СЃРјРµРЅС‹ Р°РґСЂРµСЃР° вЂ” РёРЅР°С‡Рµ СЃРјРµРЅР° Р°РґСЂРµСЃР° РѕР±РѕСЂРІС‘С‚ SSH Рё СЃР»СѓР¶Р±Р° РЅРµ РґРѕСѓСЃС‚Р°РЅРѕРІРёС‚СЃСЏ)
"$INIT" enable
"$INIT" restart
say "Р·Р°РїСѓС‰РµРЅРѕ. Р–РґСѓ РїРѕСЏРІР»РµРЅРёСЏ РєР°РЅРґРёРґР°С‚Р° РІ Keenetic (Mesh Wi-Fi), РїСЂРёС‘РјРєСѓ Р·Р°РїСѓСЃС‚РёС‚Рµ РЅР° РєРѕРЅС‚СЂРѕР»Р»РµСЂРµ."
say "Р»РѕРіРё: tail -f $LOG"

# 4. (РїРѕ Р¶РµР»Р°РЅРёСЋ) СЂРµР¶РёРј dumb-AP вЂ” Р’ РЎРђРњРћРњ РљРћРќР¦Р•: РјРѕСЃС‚ LAN РЅР° РјР°РіРёСЃС‚СЂР°Р»СЊ, DHCP РІС‹РєР», СЃРІРѕР№ Р°РґСЂРµСЃ РІ СЃРµС‚Рё Keenetic.
# РЎРјРµРЅР° Р°РґСЂРµСЃР° СЂРІС‘С‚ С‚РµРєСѓС‰РµРµ SSH-СЃРѕРµРґРёРЅРµРЅРёРµ, РїРѕСЌС‚РѕРјСѓ РґРµР»Р°РµРј СЌС‚Рѕ РїРѕСЃР»РµРґРЅРёРј С€Р°РіРѕРј, РєРѕРіРґР° РІСЃС‘ РѕСЃС‚Р°Р»СЊРЅРѕРµ СѓР¶Рµ СѓСЃС‚Р°РЅРѕРІР»РµРЅРѕ Рё Р·Р°РїСѓС‰РµРЅРѕ.
if [ "$1" = "--dumb-ap" ] && [ -n "$2" ]; then
	GW="${3:-$(echo "$2" | sed 's/\.[0-9]*$/.1/')}"
	say "СЂРµР¶РёРј dumb-AP: Р°РґСЂРµСЃ $2, С€Р»СЋР· $GW (СЃРІСЏР·СЊ РїРѕ СЃС‚Р°СЂРѕРјСѓ Р°РґСЂРµСЃСѓ СЃРµР№С‡Р°СЃ РѕР±РѕСЂРІС‘С‚СЃСЏ вЂ” СЌС‚Рѕ РЅРѕСЂРјР°Р»СЊРЅРѕ)"
	uci -q delete network.wan; uci -q delete network.wan6
	uci set network.lan.proto='static'
	uci set network.lan.ipaddr="$2"
	uci set network.lan.netmask='255.255.255.0'
	uci set network.lan.gateway="$GW"
	uci set network.lan.dns="$GW"
	uci -q delete dhcp.lan 2>/dev/null; uci set dhcp.lan=dhcp; uci set dhcp.lan.interface='lan'; uci set dhcp.lan.ignore='1'
	for z in $(uci show firewall 2>/dev/null | sed -n "s/^firewall\.\(@zone\[[0-9]*\]\)\.name='lan'/\1/p"); do uci -q set firewall."$z".input='ACCEPT'; done
	# РїСЂРёРјРµРЅСЏРµРј РІ С„РѕРЅРµ СЃ Р·Р°РґРµСЂР¶РєРѕР№, С‡С‚РѕР±С‹ СЌС‚РѕС‚ СЃРєСЂРёРїС‚ СѓСЃРїРµР» Р·Р°РІРµСЂС€РёС‚СЊСЃСЏ Рё РѕС‚РґР°С‚СЊ РІС‹РІРѕРґ РґРѕ РѕР±СЂС‹РІР° СЃРІСЏР·Рё (setsid вЂ” РїРµСЂРµР¶РёРІС‘С‚ Р·Р°РєСЂС‹С‚РёРµ SSH)
	if command -v setsid >/dev/null 2>&1; then
		setsid sh -c 'sleep 3; uci commit; /etc/init.d/network reload' </dev/null >/dev/null 2>&1 &
	else
		( sleep 3; uci commit; /etc/init.d/network reload ) </dev/null >/dev/null 2>&1 &
	fi
	say "Р°РґСЂРµСЃ СЃРјРµРЅРёС‚СЃСЏ РЅР° $2 С‡РµСЂРµР· РїР°СЂСѓ СЃРµРєСѓРЅРґ вЂ” РґР°Р»СЊС€Рµ Р·Р°С…РѕРґРёС‚Рµ РЅР° СЂРѕСѓС‚РµСЂ СѓР¶Рµ РїРѕ РЅРѕРІРѕРјСѓ Р°РґСЂРµСЃСѓ"
fi
