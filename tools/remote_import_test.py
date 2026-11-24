"""Import a management-only WireGuard config without a live router."""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rackd import remote

KEY = base64.b64encode(b'a' * 32).decode()
KEY2 = base64.b64encode(b'b' * 32).decode()
PSK = base64.b64encode(b'c' * 32).decode()
CONF = f'''[Interface]
PrivateKey = {KEY}
Address = 172.16.6.18/32
[Peer]
PublicKey = {KEY2}
PresharedKey = {PSK}
Endpoint = 203.0.113.5:41495
AllowedIPs = 172.16.6.0/24, 192.168.1.3/32
PersistentKeepalive = 25
'''


class FakeRouter:
    def __init__(self, handshake=True, reachable=True, installed=False):
        self.handshake, self.reachable, self.installed = handshake, reachable, installed
        self.scripts = []

    def _ssh(self, d, script, timeout):
        self.scripts.append((d['host'], script))
        if script == remote.STATUS:
            return '@@ip 172.16.6.4\n@@end' if self.installed else '@@end'
        if '@@pub $(cat' in script:
            return '@@pub ' + KEY2
        if '@@done' in script:
            return '@@hs ' + ('100' if self.handshake else '0') + '\n@@done'
        return '@@ok' if self.reachable else ''


class ImportTests(unittest.TestCase):
    def test_reject_unsafe_configs_before_router_changes(self):
        cases = [CONF.replace('172.16.6.0/24, 192.168.1.3/32', '0.0.0.0/0'),
                 CONF.replace('172.16.6.0/24, 192.168.1.3/32', '8.8.8.8/32'),
                 CONF.replace('PrivateKey = ' + KEY, 'PrivateKey = broken'),
                 CONF + '\n[Peer]\nPublicKey = ' + KEY2,
                 CONF.replace('[Peer]', 'S3 = 12\n[Peer]'),
                 CONF.replace('203.0.113.5:41495', '127.0.0.1:41495')]
        for conf in cases:
            with self.subTest(conf=conf.replace(KEY, '[private]')):
                router = FakeRouter()
                with self.assertRaises(Exception):
                    remote.connect_import(None, {'host': '192.168.2.1'}, router, {'conf': conf}, lambda _: None)
                self.assertFalse(any('uci set' in script for _, script in router.scripts))

    def test_success_sets_only_management_routes_and_switches_after_ssh(self):
        router = FakeRouter()
        result = remote.connect_import(None, {'host': '192.168.2.1'}, router, {'conf': CONF}, lambda _: None)
        self.assertTrue(result['handshake'])
        self.assertEqual(result['deviceUpdate']['host'], '172.16.6.18')
        self.assertEqual(result['deviceUpdate']['remote']['mode'], 'import')
        self.assertNotIn(KEY, str(result))
        self.assertNotIn(PSK, str(result))
        script = next(s for _, s in router.scripts if '@@done' in s)
        self.assertIn("allowed_ips='172.16.6.0/24'", script)
        self.assertIn("allowed_ips='192.168.1.3/32'", script)
        self.assertNotIn('0.0.0.0/0', script)
        self.assertIn('firewall.rl_wgz.forward=REJECT', script)
        self.assertIn('network.rl_wg.ip4table=3141', script)

    def test_no_handshake_keeps_original_host(self):
        result = remote.connect_import(None, {'host': '192.168.2.1'}, FakeRouter(handshake=False), {'conf': CONF}, lambda _: None)
        self.assertFalse(result['ok'])
        self.assertNotIn('host', result['deviceUpdate'])

    def test_preshared_key_is_optional(self):
        router = FakeRouter()
        result = remote.connect_import(None, {'host': '192.168.2.1'}, router,
                                       {'conf': CONF.replace('PresharedKey = ' + PSK + '\n', '')}, lambda _: None)
        self.assertTrue(result['ok'])
        script = next(s for _, s in router.scripts if '@@done' in s)
        self.assertIn('[ -z "$P" ] || uci set network.rl_wgpeer.preshared_key="$P"', script)

    def test_existing_tunnel_is_not_replaced(self):
        router = FakeRouter(installed=True)
        with self.assertRaises(Exception):
            remote.connect_import(None, {'host': '192.168.2.1'}, router, {'conf': CONF}, lambda _: None)
        self.assertEqual(len(router.scripts), 1)


if __name__ == '__main__':
    unittest.main()
