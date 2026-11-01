"""Saved visual patch cords; passive port maps keep their original wiring."""
import re


def clean(rack, units):
    by_id = {str(u.get('id')): u for u in units if isinstance(u, dict)}
    def endpoint(value):
        if not isinstance(value, dict):
            return None
        uid, port = str(value.get('unit') or ''), str(value.get('port') or '').strip()[:64]
        unit = by_id.get(uid)
        if not unit or not port:
            return None
        result = {'unit': uid, 'port': port}
        device = str(value.get('device') or '')
        if device:
            ids = unit.get('deviceIds') or [unit.get('deviceId')]
            if device not in ids:
                return None
            result['device'] = device
        return result
    cords, seen = [], set()
    for c in (rack.get('patchCords') or [])[:256] if isinstance(rack.get('patchCords'), list) else []:
        if not isinstance(c, dict):
            continue
        a, b = endpoint(c.get('a')), endpoint(c.get('b'))
        if not a or not b or a == b:
            continue
        key = '|'.join(sorted(f"{e['unit']}:{e.get('device', '')}:{e['port']}" for e in (a, b)))
        if key in seen:
            continue
        seen.add(key)
        cords.append({'a': a, 'b': b})
    colors = rack.get('cordColors')
    colors = {str(k)[:400]: v.lower() for k, v in list(colors.items())[:512]
              if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', v)} if isinstance(colors, dict) else {}
    return {'patchCords': cords, 'cordColors': colors}
