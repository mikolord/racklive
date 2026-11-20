"""Desktop connection security and lifecycle, with no access to a real PC."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rackd import terminal, windesktop as desktop
from rackd.util import DriverError
from rackd import server


class KeenDNSTests(unittest.TestCase):
    def exercise(self, flags=(), apply=False, count=1, fail=None):
        state = set(flags)
        commands = []
        def cli(batch):
            cmd = batch[0]
            if cmd == 'show running-config':
                return [{'parse': {'message': ['ip http proxy racklive', ' upstream http test.invalid 9998'] + [' ' + f for f in sorted(state)]}}]
            commands.append(cmd)
            if cmd == fail:
                return [{'parse': {'status': [{'status': 'error', 'message': 'test failure'}]}}]
            flag = cmd.split()[-1]
            if cmd.startswith('no '):
                state.discard(flag)
            elif cmd.startswith('ip '):
                state.add(flag)
            return [{'parse': {'status': [{'status': 'message'}]}}]
        get = lambda path: {'racklive': {'fqdn': 'test.invalid'}}
        devices = [{'driver': 'keenetic', 'host': '192.168.55.' + str(i + 1)} for i in range(count)]
        with patch('rackd.drivers.keenetic.Keenetic._session', return_value=(get, cli)):
            try:
                result = desktop.keendns(devices, apply=apply)
            except DriverError:
                result = None
        return result, state, commands

    def test_inspection_does_not_write(self):
        result, state, commands = self.exercise()
        self.assertFalse(result['ready'])
        self.assertEqual(commands, [])

    def test_setup_only_two_flags_and_save(self):
        result, state, commands = self.exercise(apply=True)
        self.assertTrue(result['ready'])
        self.assertEqual(commands, ['ip http proxy racklive preserve-host', 'ip http proxy racklive preserve-origin', 'system configuration save'])

    def test_ambiguous_routers_never_write(self):
        result, state, commands = self.exercise(count=2, apply=True)
        self.assertIsNone(result)
        self.assertEqual(commands, [])

    def test_failure_rolls_back_only_new_flag(self):
        result, state, commands = self.exercise(flags=['preserve-host'], apply=True, fail='system configuration save')
        self.assertIsNone(result)
        self.assertEqual(state, {'preserve-host'})
        self.assertIn('no ip http proxy racklive preserve-origin', commands)
        self.assertNotIn('no ip http proxy racklive preserve-host', commands)


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rl-desktop-test-')
        self.addCleanup(self.tmp.cleanup)
        self.manager = desktop.Desktops(self.tmp.name)
        self.device = {'id': 'windows-test', 'driver': 'windows'}

    def prepare(self):
        m, did = self.manager, self.device['id']
        m._save(did, {'ready': True, 'password': 'test-only'})
        m._key(did).write_text('test-only')
        m._known(did).write_text('test-only')

    def app_icons(self):
        import base64, zlib
        def png(size):
            def chunk(kind, data):
                return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
            raw = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\0' + b'\x22\x66\xcc' * size) * size)) + chunk(b'IEND', b'')
            return base64.b64encode(raw).decode()
        return {str(s): png(s) for s in (192, 512)}

    def test_pwa_identity_stable_and_private_state_separate(self):
        self.prepare()
        a = self.manager.create_app(self.device, 'Рабочий ПК', self.app_icons())
        b = self.manager.create_app(self.device, 'Новое имя', self.app_icons())
        self.assertEqual(a['url'], b['url'])
        token = a['url'].split('/')[-2]
        item = self.manager.find_app(token, [self.device])
        self.assertEqual(item['name'], 'Новое имя')
        self.assertNotIn('password', item)
        self.assertNotIn('test-only', json.dumps(item))
        self.assertEqual(self.manager.state(self.device['id'])['password'], 'test-only')
        self.assertIsNone(self.manager.find_app(token, []))
        self.assertIsNone(self.manager.find_app(token, [dict(self.device, enabled=False)]))

    def test_pwa_rejects_invalid_png_and_dimension(self):
        for pictures in ({}, {'192': 'not png'}, [], dict(self.app_icons(), **{'192': self.app_icons()['512']})):
            with self.subTest(pictures=type(pictures).__name__), self.assertRaises(DriverError):
                self.manager.create_app(self.device, 'ПК', pictures)

    def test_pwa_manifest_page_and_icons_are_device_scoped(self):
        a = self.manager.create_app(self.device, '<ПК> & тест', self.app_icons())
        handler = server.Handler.__new__(server.Handler)
        handler.send_raw = Mock()
        handler.err = Mock()
        app = SimpleNamespace(desktop=self.manager, store=SimpleNamespace(cfg={'devices': [self.device], 'settings': {}}))
        with patch.object(server, 'APP', app):
            self.assertTrue(handler.desktop_app(a['url'] + 'manifest.webmanifest'))
            man = json.loads(handler.send_raw.call_args.args[0])
            self.assertEqual(man['id'], a['url'])
            self.assertEqual(man['start_url'], a['url'])
            self.assertEqual(man['scope'], a['url'])
            self.assertNotEqual(a['installUrl'], a['url'])
            self.assertTrue(handler.desktop_app(a['installUrl']))
            install_page = handler.send_raw.call_args.args[0].decode()
            self.assertIn('"installing": true', install_page)
            self.assertIn(a['url'] + 'manifest.webmanifest', install_page)
            self.assertTrue(handler.desktop_app(a['url']))
            page = handler.send_raw.call_args.args[0].decode()
            self.assertIn('&lt;ПК&gt; &amp; тест', page)
            self.assertIn('window.RL_DESKTOP_APP=', page)
            self.assertIn('apple-touch-icon', page)
            self.assertNotIn('test-only', page)
            self.assertTrue(handler.desktop_app(a['url'] + 'icon-192.png'))
            self.assertTrue(handler.send_raw.call_args.args[0].startswith(b'\x89PNG'))
            self.assertTrue(handler.desktop_app(a['url'] + 'sw.js'))
            worker = handler.send_raw.call_args.args[0].decode()
            self.assertNotIn('caches.', worker)
            self.assertIn("fetch(e.request)", worker)

    def test_pwa_creation_requires_admin_before_body(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = '/api/desktop/app'
        handler.need_admin = Mock(return_value=False)
        handler.body = Mock()
        with patch.object(server, 'APP', SimpleNamespace(store=Mock())):
            handler.route('POST')
        handler.need_admin.assert_called_once()
        handler.body.assert_not_called()

    def test_wallpaper_mode_is_owner_guarded_and_idempotent(self):
        with patch.object(desktop, 'run_ps', return_value='@@json {"ok":true,"full":true,"changed":false}') as call:
            result = self.manager.visual(self.device, True)
        script = call.call_args.args[1]
        self.assertIn('owner.json', script)
        self.assertIn(self.manager.owner, script)
        self.assertIn('-Name RemoveWallpaper', script)
        self.assertIn('Restart-Service tvnserver', script)
        self.assertNotIn('UseD3D', script)
        self.assertTrue(result['full'])
        self.assertNotIn(self.device['id'], self.manager.busy)
        with patch.object(desktop, 'run_ps', return_value='@@json {"ok":true,"full":true,"changed":false}') as call:
            self.manager.visual(self.device)
        self.assertNotIn('Restart-Service', call.call_args.args[1])

    def test_wallpaper_mode_denies_failed_probe(self):
        with patch.object(desktop, 'run_ps', return_value='@@json {"ok":false,"error":"private detail"}'), self.assertRaises(DriverError):
            self.manager.visual(self.device, True)
        self.assertNotIn(self.device['id'], self.manager.busy)

    def test_ticket_one_use_and_expiry(self):
        self.prepare()
        with patch.object(desktop.time, 'time', return_value=100):
            ticket = self.manager.ticket(self.device, 'session-test')
            item = self.manager.consume(ticket['ticket'])
            self.assertEqual(item['session'], 'session-test')
            self.assertEqual(item['device'], self.device['id'])
            self.assertIsNone(self.manager.consume(ticket['ticket']))
            expired = self.manager.ticket(self.device, 'session-test')
        with patch.object(desktop.time, 'time', return_value=131):
            self.assertIsNone(self.manager.consume(expired['ticket']))

    def test_uninstalled_has_no_connection_ticket(self):
        with self.assertRaises(DriverError):
            self.manager.ticket(self.device, 'session-test')

    def test_ownership_and_transport_required(self):
        self.prepare()
        m = self.manager
        info = dict(owner=m.owner, device=self.device['id'], present=True,
                    running=True, loopback=True, httpOff=True, captureCompatible=True)
        def card():
            with patch.object(desktop, 'run_ps', return_value='@@json '+json.dumps(info)):
                return m.card(self.device, None)
        self.assertTrue(card()['ready'])
        self.assertNotIn('password', card())
        info['owner'] = 'another-rack-live'
        self.assertFalse(card()['managed'])
        self.assertFalse(card()['ready'])
        self.assertIn('warning', card())
        info['owner'] = m.owner
        info['loopback'] = False
        self.assertFalse(card()['ready'])
        info['loopback'] = True
        info['captureCompatible'] = False
        self.assertFalse(card()['ready'])
        info['captureCompatible'] = True
        m._key(self.device['id']).unlink()
        self.assertFalse(card()['ready'])

    def test_demo_does_not_contact_pc(self):
        with patch.object(desktop, 'run_ps', side_effect=AssertionError('network used')):
            self.assertTrue(self.manager.card(self.device, None, demo=True)['demo'])

    def test_paths_and_missing_transport(self):
        for did in ('../escape', '/absolute', 'a/b', 'a\\b', '', 'a'*81):
            with self.subTest(did=did), self.assertRaises(DriverError):
                self.manager.state(did)
        with patch.object(desktop.subprocess, 'Popen', side_effect=AssertionError('SSH used')):
            with self.assertRaises(DriverError):
                self.manager.spawn(self.device)

    def test_private_storage_and_persistent_identity(self):
        self.prepare()
        self.assertEqual(desktop.Desktops(self.tmp.name).owner, self.manager.owner)
        if os.name == 'posix':
            self.assertEqual(self.manager.root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(self.manager._path(self.device['id']).stat().st_mode & 0o777, 0o600)

    def test_busy_operation_does_not_run_install(self):
        self.manager.busy.add(self.device['id'])
        with patch.object(desktop.os, 'name', 'posix'), patch.object(desktop, 'run_ps', side_effect=AssertionError('network used')):
            with self.assertRaises(DriverError):
                self.manager.plugin(self.device, 'desktop', 'install', {'_drv': None})

    def test_masked_binary_frames_incremental(self):
        payload = bytes(range(256))*3
        mask = b'abcd'
        frame = b'\x82\xfe'+struct.pack('>H',len(payload))+mask+bytes(c^mask[i%4] for i,c in enumerate(payload))
        reader = terminal.Reader(require_mask=True)
        self.assertEqual(reader.feed(frame[:7]), [])
        self.assertEqual(reader.feed(frame[7:]), [(2,payload)])
        with self.assertRaises(ValueError):
            reader.feed(terminal.frame(b'unmasked'))
        with self.assertRaises(ValueError):
            terminal.Reader(require_mask=True).feed(b'\x82\xff'+struct.pack('>Q',1_000_001))

    def connect(self, *, origin='http://rack.test', cookie='session-test', valid=True,
                demo=False, enabled=True, ticket=True):
        self.prepare()
        m = self.manager
        m.spawn = Mock(return_value=(None, None, b'RFB 003.008\n'))
        m.relay = Mock()
        token = m.ticket(self.device, 'session-test')['ticket'] if ticket else 'invalid'
        handler = object.__new__(server.Handler)
        handler.path = '/api/desktop/ws?t='+token
        handler.headers = Message()
        for k,v in {'Host':'rack.test','Origin':origin,'Upgrade':'websocket',
                    'Sec-WebSocket-Key':'test-handshake','User-Agent':'test'}.items():
            if v is not None:
                handler.headers[k] = v
        if cookie:
            handler.headers['Cookie'] = 'rl_session='+cookie
        handler.client_address = ('127.0.0.1',1234)
        handler.connection = object()
        handler.err = Mock()
        handler._upgrade = Mock()
        device = dict(self.device, enabled=enabled)
        app = SimpleNamespace(desktop=m, store=SimpleNamespace(device=lambda _:device),
                              sessions=SimpleNamespace(valid=lambda *args:valid))
        with patch.object(server, 'APP', app), patch.object(server, 'DEMO', demo):
            handler.desktop_socket()
        return handler, m

    def test_socket_denies_invalid_ticket_or_session(self):
        for args,code in (({'ticket':False},401),({'valid':False},401),
                          ({'cookie':'another-session'},403)):
            with self.subTest(args=args):
                handler,m = self.connect(**args)
                self.assertEqual(handler.err.call_args.args[1],code)
                m.spawn.assert_not_called()

    def test_socket_requires_same_origin_real_enabled_pc(self):
        for args,code in (({'origin':None},403),({'origin':'http://elsewhere.test'},403),
                          ({'demo':True},400),({'enabled':False},400)):
            with self.subTest(args=args):
                handler,m = self.connect(**args)
                self.assertEqual(handler.err.call_args.args[1],code)
                m.spawn.assert_not_called()

    def test_socket_authenticated_cookie_or_ticket(self):
        for cookie in ('session-test',None):
            with self.subTest(cookie=cookie):
                handler,m = self.connect(cookie=cookie)
                handler.err.assert_not_called()
                handler._upgrade.assert_called_once()
                m.relay.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
