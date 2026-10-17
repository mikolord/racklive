#!/usr/bin/env python3
"""Browser terminal: the WebSocket frames and a whole session over a socket pair with a local shell (POSIX only — on Windows the session part is skipped).
    python tools/terminal_test.py"""
import json, os, socket, struct, sys, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..') if '__file__' in globals() else '/app')
from rackd import terminal as T  # noqa: E402

FAILS = []


def check(name, ok, extra=''):
    print(('  ok   ' if ok else '  FAIL ') + name + ('' if ok else '  ' + str(extra)))
    if not ok:
        FAILS.append(name)


def client_frame(payload, opcode=1):
    mask = os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | opcode]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n)) + mask
    return head + bytes(c ^ mask[i % 4] for i, c in enumerate(payload))


def read_frames(sock, until, timeout=8):
    got, end = b'', time.time() + timeout
    buf = b''
    while time.time() < end:
        sock.settimeout(.5)
        try:
            d = sock.recv(65536)
        except socket.timeout:
            continue
        if not d:
            break
        buf += d
        while len(buf) >= 2:
            ln, i = buf[1] & 0x7F, 2
            if ln == 126:
                ln, i = struct.unpack('>H', buf[2:4])[0], 4
            if len(buf) < i + ln:
                break
            got += buf[i:i + ln]
            buf = buf[i + ln:]
        if until in got:
            return got
    return got


check('the handshake key is computed as in RFC 6455', T.accept_key('dGhlIHNhbXBsZSBub25jZQ==') == 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
r = T.Reader()
big = client_frame(b'x' * 300)
ev = r.feed(client_frame(b'ls -la\n') + big[:5])
check('a masked frame is read, a half frame waits', ev == [(1, b'ls -la\n')] and r.buf, ev)
ev = r.feed(big[5:])
check('...and completes when the rest arrives', len(ev) == 1 and ev[0][1] == b'x' * 300)
check('server frames are never masked and carry the length', T.frame(b'abc')[1] == 3 and T.frame(b'a' * 200)[1] == 126 and T.frame(b'a' * 70000)[1] == 127)
try:
    T.Reader().feed(bytes([0x81, 0xFF]) + struct.pack('>Q', 10 ** 9) + b'0000'); check('a frame over 1 MB is refused', False)
except ValueError:
    check('a frame over 1 MB is refused', True)

if not T.supported():
    print('  (сеанс пропущен: не POSIX)')
else:
    a, b = socket.socketpair()
    res = {}
    t = threading.Thread(target=lambda: res.update(r=T.run(a, ['sh'], dict(os.environ, TERM='xterm', PS1='$ '), 80, 24, None)), daemon=True)
    t.start()
    b.sendall(client_frame(b'echo hello-$((6*7))\n'))
    out = read_frames(b, b'hello-42')
    check('a command typed in the page runs in a real shell and its output comes back', b'hello-42' in out, out[-120:])
    b.sendall(client_frame(json.dumps({'resize': [120, 40]}).encode()))
    b.sendall(client_frame(b'stty size\n'))
    out = read_frames(b, b'40 120')
    check('the page window size reaches the terminal (stty size)', b'40 120' in out, out[-120:])
    b.sendall(client_frame(b'exit\n'))
    t.join(10)
    check('after «exit» the session ends by itself', not t.is_alive() and res.get('r') and 'заверш' in res['r'][0], res)
    a2, b2 = socket.socketpair()
    res2 = {}
    t2 = threading.Thread(target=lambda: res2.update(r=T.run(a2, ['sh'], dict(os.environ, TERM='xterm'), 80, 24, None)), daemon=True)
    t2.start(); time.sleep(.5)
    b2.sendall(client_frame(b'', 8))
    t2.join(10)
    check('closing the tab ends the session and the shell is stopped', not t2.is_alive() and not T.KEYS, (res2, T.KEYS))
print('\n' + ('ВСЁ OK' if not FAILS else 'ЕСТЬ ОШИБКИ: ' + ', '.join(FAILS)))
sys.exit(1 if FAILS else 0)
