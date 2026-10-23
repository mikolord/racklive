"""Portal login by SMS: phone normalising, profile checks, the scripts are built and keep the SIM-router password off the router."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from rackd import portal

ok = True


def check(name, cond):
    global ok
    print(('  ok   ' if cond else '  FAIL ') + name)
    ok = ok and bool(cond)


for src in ('8 (988) 280-94-77', '+7 988 280 94 77', '9882809477', '79882809477'):
    check('номер ' + src, portal.phone(src) == '+79882809477')
for bad in ('', '12', 'abc', '123456789012345678'):
    try:
        portal.phone(bad); check('плохой номер ' + repr(bad), False)
    except ValueError:
        check('плохой номер ' + repr(bad), True)

HW = {'radios': [{'band': '2g', 'name': 'radio0'}], 'lan': ['lan1'], 'wanip': ''}
base = dict(mainSsid='Office', mainKey='12345678', guestSsid='Guest', login='sms', smsHost='192.168.10.2', smsPass='sim-pass-1', hours=24)
prof = portal.validate(base, HW)
check('профиль с СМС принят', prof['login'] == 'sms' and prof['smsHost'] == '192.168.10.2' and prof['smsPort'] == 22)
for bad in ({'smsHost': ''}, {'smsHost': '8.8.8.8'}, {'smsHost': 'a b'}, {'smsPort': 0}, {'smsUser': 'a;b'}):
    try:
        portal.validate(dict(base, **bad), HW, strict_sms=True); check('плохой роутер с SIM ' + str(bad), False)
    except ValueError:
        check('плохой роутер с SIM ' + str(bad), True)
check('без СМС адрес не нужен', portal.validate(dict(base, login='click', smsHost=''), HW)['login'] == 'click')

pub = portal.public(prof)
check('пароль SIM-роутера не уходит в интерфейс', 'smsPass' not in pub and pub['smsPassSet'])
check('пароль SIM-роутера не пишется на роутер', 'sim-pass-1' not in portal.router_profile(prof) and 'sim-pass-1' not in portal.login_script(prof))
setup = portal.sms_setup_script(prof)
check('скрипт подготовки: пароль только в окружении', setup.count('sim-pass-1') == 1 and 'DROPBEAR_PASSWORD' in setup)
check('шлюз и ограниченный ключ в скрипте', 'rl-sms' in setup and 'command=' in portal._asset('sms_gw.sh'))
conf = portal.portal_conf(prof)
check('в настройках темы есть адрес и хвост текста', "RL_SMSHOST='192.168.10.2'" in conf and 'RL_SMSTAIL=' in conf)
check('текст СМС: хвост в UCS2', portal.sms_tail(prof).startswith('0020'))
check('тема читает номер и код', 'rlphone rlcode' in portal.theme_script())
sys.exit(0 if ok else 1)
