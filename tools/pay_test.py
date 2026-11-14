"""Payment reminders of a VPS (rackd/payment.py): who is reminded when, «Оплатил», the stored form.   python tools/pay_test.py"""
import datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import payment as P

bad = 0
def check(name, ok):
    global bad
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok:
        bad += 1

D = dt.date
def dev(due, **kw):
    return {'id': 'd1', 'name': '/abh Мой VPS', 'pay': P.clean({'on': True, 'due': due, 'amount': '500', 'cur': '₽', 'url': 'hoster.example/pay', **kw})}
def run(d, now):
    out = []
    P.check([d], now, lambda lines, did: out.append((lines, did)), lambda: out.append('saved'), lambda *a: out.append(('event',) + a))
    return [x for x in out if isinstance(x, tuple) and x[0] != 'event']

# clean
c = P.clean({'on': True, 'due': '2026-11-20', 'url': 'hoster.example/pay', 'remind': [3, 99, 'x', 1], 'hour': 77, 'every': 'weird'})
check('clean: url gets https, junk reminders dropped, hour clamped, period falls back', c['url'] == 'https://hoster.example/pay' and c['remind'] == [3, 1] and c['hour'] == 23 and c['every'] == 'month')
check('clean: a bad date is empty', P.clean({'due': '31.11.2026'})['due'] == '')
check('clean: no `remind` sent → the default set', P.clean({'on': True, 'due': '2026-11-20'})['remind'] == [7, 3, 1, 0])
old = {'due': '2026-11-20', 'sent': ['2026-11-20:7']}
check('clean: the sent list survives while the date is the same, is reset when it moves', P.clean({'due': '2026-11-20'}, old)['sent'] == ['2026-11-20:7'] and P.clean({'due': '2026-12-20'}, old)['sent'] == [])

# reminders
d = dev('2026-11-20')
check('10 days before: nothing yet', run(d, dt.datetime(2026, 11, 10, 12)) == [])
r = run(d, dt.datetime(2026, 11, 13, 10, 5))
check('7 days before: one message with the sum and the site', len(r) == 1 and 'через 7 дн.' in r[0][0][0] and '500 ₽' in r[0][0][0] and 'https://hoster.example/pay' in r[0][0][0] and r[0][1] == 'd1')
check('the name has no «/abh» prefix', '/abh' not in r[0][0][0] and 'Мой VPS' in r[0][0][0])
check('the same day again: not repeated', run(d, dt.datetime(2026, 11, 13, 18)) == [])
check('before the chosen hour: waits', run(dev('2026-11-20', hour=15), dt.datetime(2026, 11, 13, 9)) == [])
r = run(d, dt.datetime(2026, 11, 17, 10))
check('3 days before', len(r) == 1 and 'через 3 дн.' in r[0][0][0])
r = run(d, dt.datetime(2026, 11, 19, 10))
check('tomorrow', len(r) == 1 and 'завтра' in r[0][0][0])
r = run(d, dt.datetime(2026, 11, 20, 10))
check('on the day', len(r) == 1 and 'сегодня' in r[0][0][0])
check('on the day again: not repeated', run(d, dt.datetime(2026, 11, 20, 20)) == [])
r = run(d, dt.datetime(2026, 11, 21, 10))
check('overdue: every day', len(r) == 1 and 'просрочена на 1 дн.' in r[0][0][0])
check('overdue, same day: once', run(d, dt.datetime(2026, 11, 21, 22)) == [])
check('overdue, next day: again', len(run(d, dt.datetime(2026, 11, 22, 10))) == 1)
d2 = dev('2026-11-20')
r = run(d2, dt.datetime(2026, 11, 19, 10))
check('after a pause: one message, not a burst of old ones', len(r) == 1 and d2['pay']['sent'] == ['2026-11-20:7', '2026-11-20:3', '2026-11-20:1'])
off = dev('2026-11-20'); off['pay']['on'] = False
check('switched off: silent', run(off, dt.datetime(2026, 11, 20, 10)) == [])
check('no reminders chosen: silent before the date', run(dev('2026-11-20', remind=[]), dt.datetime(2026, 11, 19, 10)) == [])

# «Оплатил»
p = P.clean({'on': True, 'due': '2026-01-31', 'every': 'month'})
P.mark_paid(p, D(2026, 1, 30)); a = p['due']
P.mark_paid(p, D(2026, 2, 27)); b = p['due']
P.mark_paid(p, D(2026, 3, 30)); c3 = p['due']
check('monthly keeps the day of the month: 31 Jan → 28 Feb → 31 Mar', (a, b, c3) == ('2026-02-28', '2026-03-31', '2026-04-30'))
y = P.clean({'on': True, 'due': '2028-02-29', 'every': 'year'}); P.mark_paid(y, D(2028, 2, 1))
check('yearly: 29 Feb → 28 Feb', y['due'] == '2029-02-28')
n = P.clean({'on': True, 'due': '2026-11-20', 'every': 'days', 'days': 10}); P.mark_paid(n, D(2026, 11, 19))
check('every N days', n['due'] == '2026-11-30')
late = P.clean({'on': True, 'due': '2026-08-20', 'every': 'month'}); P.mark_paid(late, D(2026, 11, 7))
check('paid long after: the date skips the past periods', late['due'] == '2026-11-20')
check('paid: the sent list is cleared', late['sent'] == [])
one = P.clean({'on': True, 'due': '2026-11-20', 'every': 'once'}); P.mark_paid(one, D(2026, 11, 7))
check('a single payment switches the reminder off', one['on'] is False)
check('days_left', P.days_left({'due': '2026-11-20'}, D(2026, 11, 7)) == 13 and P.days_left({}, D(2026, 11, 7)) is None)

print('BAD' if bad else 'GOOD')
sys.exit(1 if bad else 0)
