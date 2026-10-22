#!/bin/sh
# openNDS ThemeSpec «Rack Live»: the guest page is the template uploaded in Rack Live (/etc/opennds/htdocs/rl/index.html)
# with its {{…}} marks filled in: {{form}} {{error}} {{name}} {{hours}} {{assets}} {{rules}} {{continue}}.
# Settings come from /etc/rl-portal/conf (written by Rack Live): login by a button or by a shared password, session length, speed.

title="theme_rl"
TPL=/etc/opennds/htdocs/rl
RL_LOGIN=click; RL_PASSHASH=""; RL_MIN=1440; RL_UP=0; RL_DOWN=0; RL_name="Wi-Fi"; RL_hours=24; RL_rules=""; RL_terms=""
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
	footer
}

rl_esc() {
	sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'
}

rl_form() {
	RL_form="<form class=\"rl-form\" action=\"/opennds_preauth/\" method=\"get\"><input type=\"hidden\" name=\"fas\" value=\"$fas\">"
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
	[ -z "$RL_continue" ] && RL_continue="https://ya.ru"
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

rl_grant() {
	session_length="$RL_MIN"
	quotas="$session_length $RL_UP $RL_DOWN 0 0"
	configure_log_location
	. $mountpoint/ndscids/ndsinfo
	userinfo="$title"
	auth_log
	if [ "$ndsstatus" = "authenticated" ]; then
		RL_form=""
		rl_page done.html
	fi
	RL_error="<p class=\"rl-error\">Не получилось подключиться. Попробуйте ещё раз.</p>"
}

#### main ####

session_length="0"
quotas="$session_length 0 0 0 0"

ndscustomparams=""
ndscustomimages=""
ndscustomfiles=""
ndsparamlist="$ndsparamlist $ndscustomparams $ndscustomimages $ndscustomfiles"

additionalthemevars="rlgo rlpass"
fasvarlist="$fasvarlist $additionalthemevars"

userinfo="$title"
