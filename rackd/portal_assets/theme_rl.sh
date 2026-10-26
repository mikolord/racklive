#!/bin/sh
# openNDS ThemeSpec «Rack Live»: the guest page is the template uploaded in Rack Live (/etc/opennds/htdocs/rl/index.html)
# with its {{…}} marks filled in: {{form}} {{error}} {{name}} {{hours}} {{assets}} {{rules}} {{continue}}.
# Settings come from /etc/rl-portal/conf (written by Rack Live): login by a button or by a shared password, session length, speed.

title="theme_rl"
TPL=/etc/opennds/htdocs/rl
RL_LOGIN=click; RL_PASSHASH=""; RL_MIN=1440; RL_UP=0; RL_DOWN=0; RL_name="Wi-Fi"; RL_hours=24; RL_rules=""; RL_terms=""; RL_after=""
RL_SMSHOST=""; RL_SMSPORT=22; RL_SMSUSER=root; RL_SMSTAIL=""
[ -f /etc/rl-portal/conf ] && . /etc/rl-portal/conf

generate_splash_sequence() {
	rl_login
}

header() {
	:
}

footer() {
	exit 0
}

# a page of the template with the marks filled in (plain string replacement: no regex, so «&» and «\» in values are safe)
rl_page() {
	f="$TPL/$1"; [ -f "$f" ] || f="$TPL/index.html"
	RL_assets="$(printf "${gatewayurl//%/\\x}")/rl"
	export RL_form RL_error RL_name RL_hours RL_assets RL_rules RL_continue
	awk 'function rep(s, key, val,   out, p, t) { t = "{{" key "}}"; out = ""; while ((p = index(s, t)) > 0) { out = out substr(s, 1, p - 1) val; s = substr(s, p + length(t)) } return out s }
	{ n = split("form error name hours assets rules continue", k, " "); for (i = 1; i <= n; i++) $0 = rep($0, k[i], ENVIRON["RL_" k[i]]); print }' "$f"
	# the «you are online» page moves on to the site by itself: an iPhone re-checks the internet (and puts the tick, closing the sign-in window)
	# only when the page changes — until then it stays «not confirmed» and the guest has to tap the link by hand. 3 s: the sign-in runs a second after the page.
	if [ "$1" = "done.html" ]; then
		go=$(printf '%s' "$RL_continue" | sed 's/&amp;/\&/g; s/&quot;//g' | tr -d "\"'\\\\<> ")
		org=$(printf '%s' "$go" | sed 's#^\(https\{0,1\}://[^/]*\).*#\1#')
		case "$go" in
			# https site: move on the moment the internet is really open (before the sign-in the router drops https, so the probe fails and is repeated); at the latest after 7 s
			https://*) printf '<script>(function(){var u="%s",o="%s",t=Date.now();function go(){location.replace(u)}try{(function tick(){if(Date.now()-t>7000)return go();var c=new AbortController(),m=setTimeout(function(){c.abort()},900);fetch(o+"/favicon.ico?"+t,{mode:"no-cors",cache:"no-store",signal:c.signal}).then(function(){clearTimeout(m);go()},function(){clearTimeout(m);setTimeout(tick,250)})})()}catch(e){setTimeout(go,3000)}})()</script><noscript><meta http-equiv="refresh" content="3;url=%s"></noscript>\n' "$go" "$org" "$go" ;;
			http://*) printf '<script>setTimeout(function(){location.replace("%s")},2500)</script><noscript><meta http-equiv="refresh" content="3;url=%s"></noscript>\n' "$go" "$go" ;;
		esac
	fi
	footer
}

rl_esc() {
	sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'
}

rl_form() {
	# pressed → the button says «Подключаем…» and is locked at once (no second press); disabled after submit so its rlgo=1 still goes out
	RL_form="<form class=\"rl-form\" data-wait=\"Подключаем…\" onsubmit=\"var f=this;if(f.getAttribute('data-sent'))return false;f.setAttribute('data-sent','1');f.classList.add('rl-loading');var s=event.submitter||f.querySelector('.rl-btn');setTimeout(function(){if(s)s.textContent=f.getAttribute('data-wait');Array.prototype.forEach.call(f.querySelectorAll('button'),function(x){x.disabled=true})},0)\" action=\"/opennds_preauth/\" method=\"get\"><input type=\"hidden\" name=\"fas\" value=\"$fas\">"
	if [ "$RL_LOGIN" = "password" ]; then
		RL_form="$RL_form<input class=\"rl-field\" type=\"password\" name=\"rlpass\" placeholder=\"Пароль\" autocomplete=\"off\" required>"
	fi
	if [ -n "$RL_terms" ]; then
		RL_form="$RL_form<label class=\"rl-terms\"><input type=\"checkbox\" required> Принимаю <a href=\"#rl-rules\">правила пользования</a></label>"
	fi
	RL_form="$RL_form<button class=\"rl-btn\" type=\"submit\" name=\"rlgo\" value=\"1\">Подключиться</button></form>"
}

rl_login() {
	RL_error=""
	RL_continue=$(printf "${originurl//%/\\x}" | rl_esc)
	[ -n "$RL_after" ] && RL_continue="$RL_after"                # the owner chose where guests go after login
	# never back to the portal itself or to a phone's «is there internet» check: after login that shows openNDS's own status page
	case "$RL_continue" in
		""|*status.client*|*:2050*|*captive.apple.com*|*hotspot-detect*|*generate_204*|*connectivitycheck*|*msftconnecttest*|*detectportal*|*nmcheck*) RL_continue="https://ya.ru" ;;
	esac
	[ "$RL_LOGIN" = "sms" ] && rl_sms
	if [ "$rlgo" = "1" ]; then
		ok=1
		if [ "$RL_LOGIN" = "password" ]; then
			p=$(printf "${rlpass//%/\\x}" | tr '+' ' ')
			[ "$(printf '%s' "$p" | sha256sum | cut -c1-64)" = "$RL_PASSHASH" ] || ok=0
		fi
		if [ "$ok" = 1 ]; then
			rl_grant
		fi
		RL_error="<p class=\"rl-error\">Неверный пароль — спросите его у администратора.</p>"
	fi
	rl_form
	rl_page index.html
}

# login by an SMS code: the code is made here, the SMS is sent by the router with the SIM card (rl-sms there, over SSH with a key that can only send SMS)
rl_sms_form() {
	W="Отправляем СМС…"; [ "$1" = "code" ] && W="Подождите…"
	RL_form="<form class=\"rl-form\" data-wait=\"$W\" onsubmit=\"var f=this;f.classList.add('rl-loading');var s=event.submitter||f.querySelector('.rl-btn');setTimeout(function(){if(s)s.textContent=f.getAttribute('data-wait');Array.prototype.forEach.call(f.querySelectorAll('button'),function(x){x.disabled=true})},0)\" action=\"/opennds_preauth/\" method=\"get\"><input type=\"hidden\" name=\"fas\" value=\"$fas\">"
	if [ "$1" = "code" ]; then
		RL_form="$RL_form<p class=\"rl-note\">Код отправлен на $ph</p><input type=\"hidden\" name=\"rlphone\" value=\"$ph\">"
		RL_form="$RL_form<input class=\"rl-field\" type=\"text\" name=\"rlcode\" inputmode=\"numeric\" autocomplete=\"one-time-code\" maxlength=\"4\" placeholder=\"Код из СМС\" required autofocus>"
		RL_form="$RL_form<button class=\"rl-btn\" type=\"submit\" name=\"rlgo\" value=\"code\">Подтвердить</button>"
		RL_form="$RL_form<button class=\"rl-btn rl-btn2\" type=\"submit\" name=\"rlgo\" value=\"sms\" formnovalidate>Отправить код ещё раз</button></form>"
		return
	fi
	RL_form="$RL_form<input class=\"rl-field\" type=\"tel\" name=\"rlphone\" value=\"$ph\" inputmode=\"tel\" autocomplete=\"tel\" placeholder=\"+7 900 123-45-67\" required>"
	[ -n "$RL_terms" ] && RL_form="$RL_form<label class=\"rl-terms\"><input type=\"checkbox\" required> Принимаю <a href=\"#rl-rules\">правила пользования</a></label>"
	RL_form="$RL_form<button class=\"rl-btn\" type=\"submit\" name=\"rlgo\" value=\"sms\">Получить код</button></form>"
}

rl_sms() {
	S=/tmp/rl-sms; mkdir -p "$S"
	if [ -z "$RL_SMSHOST" ] || [ ! -f /etc/rl-portal/sms_rsa ]; then
		RL_error="<p class=\"rl-error\">Вход по СМС ещё не настроен администратором.</p>"; RL_form=""; rl_page index.html
	fi
	F="$S/$(printf '%s' "${clientmac:-${clientip:-$fas}}" | tr -c 'A-Za-z0-9' '_')"
	d=$(printf "${rlphone//%/\\x}" | tr -dc '0-9')
	[ ${#d} = 11 ] && [ "${d%${d#?}}" = 8 ] && d="7${d#8}"
	[ ${#d} = 10 ] && [ "${d%${d#?}}" = 9 ] && d="7$d"
	ph=""; [ ${#d} -ge 11 ] && [ ${#d} -le 15 ] && ph="+$d"
	step=phone
	if [ "$rlgo" = "sms" ]; then
		if [ -z "$ph" ]; then
			RL_error="<p class=\"rl-error\">Введите номер телефона, например +7 900 123-45-67.</p>"
		else
			code=$(tr -dc '0-9' </dev/urandom | head -c 4)
			hex="$(printf '%s' "$code" | sed 's/./003&/g')$RL_SMSTAIL"
			res=$(dbclient -y -y -i /etc/rl-portal/sms_rsa -p "$RL_SMSPORT" "$RL_SMSUSER@$RL_SMSHOST" "send $ph $hex" </dev/null 2>/dev/null)
			case "$res" in
				*@@sent*) printf '%s|%s|%s|0' "$ph" "$code" "$(date +%s)" > "$F"; step=code; logger -t rl-portal "SMS-код отправлен на $ph" ;;
				*) RL_error="<p class=\"rl-error\">Не получилось отправить СМС. Проверьте номер и попробуйте ещё раз.</p>"; logger -t rl-portal "SMS не отправлено на $ph: $res" ;;
			esac
		fi
	elif [ "$rlgo" = "code" ]; then
		step=code
		IFS='|' read -r sp sc st sn < "$F" 2>/dev/null
		c=$(printf "${rlcode//%/\\x}" | tr -dc '0-9')
		if [ -z "$sc" ] || [ $(( $(date +%s) - ${st:-0} )) -gt 600 ] || [ "${sn:-0}" -ge 5 ]; then
			rm -f "$F"; step=phone; ph=""
			RL_error="<p class=\"rl-error\">Код устарел или введён неверно слишком много раз. Запросите новый.</p>"
		elif [ "$c" = "$sc" ]; then
			rm -f "$F"
			rl_grant
			step=phone
		else
			printf '%s|%s|%s|%s' "$sp" "$sc" "$st" $(( ${sn:-0} + 1 )) > "$F"
			ph="$sp"
			RL_error="<p class=\"rl-error\">Неверный код. Проверьте СМС и попробуйте ещё раз.</p>"
		fi
	fi
	rl_sms_form "$step"
	rl_page index.html
}

rl_grant() {
	# the phone repeats the request when the answer is slow (iOS sends the same «Подключиться» several times): only the first one signs in,
	# the repeats within two minutes get the «you are online» page at once instead of queueing for ndsctl («busy» → 5 s sleeps, up to 80 s)
	K=/tmp/rl-auth; mkdir -p "$K"; K="$K/$(printf '%s' "${clientmac:-${clientip:-x}}" | tr -c 'A-Za-z0-9' '_')"
	if [ -f "$K" ] && [ $(( $(date +%s) - $(cat "$K" 2>/dev/null || echo 0) )) -lt 120 ]; then
		RL_form=""
		rl_page done.html
	fi
	date +%s > "$K"
	session_length="$RL_MIN"
	quotas="$session_length $RL_UP $RL_DOWN 0 0"
	configure_log_location
	. $mountpoint/ndscids/ndsinfo
	userinfo="$title"
	# answer first, let the guest in a moment later: on a slow router signing in + writing the log takes seconds, the phone sees the internet open
	# before the page arrives and closes the login window with «the connection was interrupted». The sign-in runs on its own (output off,
	# so openNDS is not kept waiting); if it fails, the mark is removed and the next press shows the form again.
	( sleep 0.3 2>/dev/null || sleep 1; auth_log; [ "$ndsstatus" = "authenticated" ] || rm -f "$K" ) </dev/null >/dev/null 2>&1 &
	RL_form=""
	rl_page done.html
}

#### main ####

session_length="0"
quotas="$session_length 0 0 0 0"

ndscustomparams=""
ndscustomimages=""
ndscustomfiles=""
ndsparamlist="$ndsparamlist $ndscustomparams $ndscustomimages $ndscustomfiles"

additionalthemevars="rlgo rlpass rlphone rlcode"
fasvarlist="$fasvarlist $additionalthemevars"

userinfo="$title"
