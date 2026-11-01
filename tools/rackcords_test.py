"""Patch-cord persistence accepts valid ends without changing passive port maps."""
import copy
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd.rackcords import clean

units = [{'id': 'patch', 'portmap': {'count': 24, 'ports': {'2': {'dev': 'sw', 'port': '14'}}}},
         {'id': 'switch', 'deviceId': 'sw'}, {'id': 'router', 'deviceId': 'rt'}]
before = copy.deepcopy(units)
a, b = {'unit': 'router', 'device': 'rt', 'port': '1'}, {'unit': 'switch', 'device': 'sw', 'port': '12'}
r = clean({'patchCords': [{'a': a, 'b': b}, {'a': b, 'b': a},
                         {'a': a, 'b': {'unit': 'removed', 'port': '1'}},
                         {'a': {'unit': 'router', 'device': 'other', 'port': '1'}, 'b': b}],
           'cordColors': {'port-key': '#12AB34', 'bad': 'url(secret)'}}, units)
assert r['patchCords'] == [{'a': a, 'b': b}], r
assert r['cordColors'] == {'port-key': '#12ab34'}
assert units == before, 'Passive wiring changed while saving visual cords'
assert clean({'patchCords': 'invalid', 'cordColors': []}, units) == {'patchCords': [], 'cordColors': {}}
assert clean({}, units) == {'patchCords': [], 'cordColors': {}}
print('Patch-cord storage OK')
