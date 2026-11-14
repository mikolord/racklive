"""Payment reminders for a VPS / hosting (the «Оплата» block of a device).

d['pay'] = {on, due 'YYYY-MM-DD', every 'month'|'year'|'days'|'once', days, amount, cur, url, remind [7,3,1,0], hour, sent [...]}
A reminder goes out once per chosen day-before (at `hour` o'clock local time), and every day after the due date until «Оплатил» is pressed,
which moves `due` forward by the period. The text goes to every notification channel that is on (Telegram first of all) and into «События».
"""
import calendar, datetime, re

CHOICES = (14, 7, 3, 2, 1, 0)              # «за сколько дней»; 0 = в день оплаты
EVERY = ('month', 'year', 'days', 'once')
DEFAULT_REMIND = [7, 3, 1, 0]


def parse(s):
    try:
        return datetime.date.fromisoformat(str(s or '')[:10])
    except ValueError:
        return None


def clean(new, old=None):
    """What the browser sent → what is stored (the bookkeeping fields survive while the due date stays the same)."""
    n = new if isinstance(new, dict) else {}
    old = old if isinstance(old, dict) else {}
    due = parse(n.get('due'))
    url = str(n.get('url') or '').strip()[:300]
    if url and not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    try:
        hour = min(23, max(0, int(n.get('hour', 10))))
    except (TypeError, ValueError):
        hour = 10
    try:
        days = min(3650, max(1, int(n.get('days') or 30)))
    except (TypeError, ValueError):
        days = 30
    remind = sorted({int(x) for x in n.get('remind') or [] if str(x).lstrip('-').isdigit() and int(x) in CHOICES}, reverse=True)
    out = {'on': bool(n.get('on')), 'due': due.isoformat() if due else '', 'every': n.get('every') if n.get('every') in EVERY else 'month',
           'days': days, 'amount': str(n.get('amount') or '').strip()[:20], 'cur': str(n.get('cur') or '').strip()[:4], 'url': url,
           'remind': remind if 'remind' in n else list(DEFAULT_REMIND), 'hour': hour}
    same = old.get('due') == out['due']
    out['sent'] = list(old.get('sent') or []) if same else []
    if same and old.get('anchor'):
        out['anchor'] = old['anchor']
    return out


def add_period(due, pay):
    every = pay.get('every')
    if every == 'year':
        y = due.year + 1
        return due.replace(year=y, day=min(due.day, calendar.monthrange(y, due.month)[1]))
    if every == 'days':
        return due + datetime.timedelta(days=int(pay.get('days') or 30))
    anchor = pay.get('anchor') or []
    day = anchor[1] if len(anchor) == 2 and anchor[0] == due.isoformat() else due.day      # 31 Jan → 28 Feb → 31 Mar, not 28 forever
    y, r = divmod(due.year * 12 + due.month, 12)             # r is the zero-based number of the NEXT month
    m = r + 1
    nxt = datetime.date(y, m, min(day, calendar.monthrange(y, m)[1]))
    pay['anchor'] = [nxt.isoformat(), day]
    return nxt


def mark_paid(pay, today):
    """«Оплатил»: the due date moves to the next period (past periods are skipped); a single payment switches the reminder off."""
    due = parse(pay.get('due'))
    if not due:
        return None
    if pay.get('every') == 'once':
        pay['on'], pay['sent'] = False, []
        return None
    nxt = add_period(due, pay)
    while nxt < today:
        nxt = add_period(nxt, pay)
    pay['due'], pay['sent'] = nxt.isoformat(), []
    return nxt


def days_left(pay, today):
    due = parse(pay.get('due'))
    return (due - today).days if due else None


def line(name, pay, left):
    due = parse(pay.get('due'))
    when = ('сегодня' if left == 0 else 'завтра' if left == 1 else f'через {left} дн.') if left >= 0 else f'просрочена на {-left} дн.'
    amount = (' — ' + pay['amount'] + (' ' + pay['cur'] if pay.get('cur') else '')) if pay.get('amount') else ''
    text = f"💳 {name}: оплата {when} ({due.strftime('%d.%m.%Y')}){amount}"
    if pay.get('url'):
        text += f"\n{pay['url']}"
    return text


def due_now(pay, today, hour):
    """The days-left numbers to announce right now (an empty list: nothing to send). Marks them as sent."""
    due = parse(pay.get('due'))
    if not pay.get('on') or not due or hour < int(pay.get('hour', 10)):
        return None
    left = (due - today).days
    sent = pay.setdefault('sent', [])
    if left >= 0:
        keys = {n: f'{due.isoformat()}:{n}' for n in pay.get('remind') or [] if left <= n}
        fresh = [k for k in keys.values() if k not in sent]
        if not fresh:
            return None
        sent.extend(fresh)                                  # down to the closest day is sent once: after a long pause there is no burst of old reminders
    else:
        k = f'{due.isoformat()}:late:{today.isoformat()}'
        if k in sent:
            return None
        sent.append(k)
    pay['sent'] = [k for k in sent if k.startswith(due.isoformat())][-40:]
    return left


def check(devices, now, send, save, event):
    """Called every few seconds by the poller. send(lines, dev_id), save(), event(dev_id, name, text)."""
    changed = False
    for d in devices:
        pay = d.get('pay')
        if not pay or not pay.get('on'):
            continue
        left = due_now(pay, now.date(), now.hour)
        if left is None:
            continue
        changed = True
        name = re.sub(r'^\s*/abh(?:\s+|$)', '', d.get('name') or '', flags=re.I) or d.get('name') or d.get('host') or 'Сервер'
        text = line(name, pay, left)
        event(d['id'], d.get('name'), text.split('\n')[0])
        send([text], d['id'])
    if changed:
        save()
