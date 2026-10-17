"""A real terminal in the browser (Settings → «Терминал») for the machine Rack Live runs on.

Browser (xterm.js) ⇄ WebSocket ⇄ this module ⇄ `ssh -tt` on a pseudo-terminal ⇄ the machine. The SSH login is the one already stored for that machine's device (Synology, a Linux server,
OpenWrt, Entware on a Keenetic), nothing new is saved. Only an administrator can open it; the page and the socket must come from the same site (no cross-site hijacking);
a session ends after 20 minutes without a keystroke or 8 hours in all; at most 3 at a time. Needs a POSIX system (the Docker image, Entware, OpenWrt) — not Windows."""
import base64, hashlib, json, os, select, signal, socket, struct, subprocess, threading, time
try:
    import fcntl, termios            # POSIX only: on Windows the terminal is simply unavailable
except ImportError:
    fcntl = termios = None

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
IDLE = 20 * 60
MAX = 8 * 3600
MAX_SESSIONS = 3
KEYS = {}                      # session id → process, so an admin can see / stop them


def accept_key(key):
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


def frame(payload, opcode=2):
    """a server → client frame (never masked)"""
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack('>H', n)
    else:
        head += bytes([127]) + struct.pack('>Q', n)
    return head + payload


class Reader:
    """client → server frames (masked), parsed from a growing buffer"""
    def __init__(self):
        self.buf = b''

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            b = self.buf
            if len(b) < 2:
                break
            op, ln, i = b[0] & 0x0F, b[1] & 0x7F, 2
            masked = bool(b[1] & 0x80)
            if ln == 126:
                if len(b) < 4:
                    break
                ln, i = struct.unpack('>H', b[2:4])[0], 4
            elif ln == 127:
                if len(b) < 10:
                    break
                ln, i = struct.unpack('>Q', b[2:10])[0], 10
            if ln > 1_000_000:
                raise ValueError('слишком большой кадр')
            if len(b) < i + (4 if masked else 0) + ln:
                break
            mask = b[i:i + 4] if masked else b''
            i += 4 if masked else 0
            data = b[i:i + ln]
            if masked:
                data = bytes(c ^ mask[k % 4] for k, c in enumerate(data))
            self.buf = b[i + ln:]
            out.append((op, data))
        return out


def supported():
    return fcntl is not None


def run(conn, args, env, cols, rows, log, on_start=None):
    """the session loop: until either side closes. `log(text)` writes a line to the journal"""
    import pty
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
    proc = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True, close_fds=True,
                            preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
    os.close(slave)
    sid = os.urandom(4).hex()
    KEYS[sid] = proc
    started = last = time.time()
    rd = Reader()
    why = 'закрыт'
    try:
        conn.settimeout(None)
        while True:
            now = time.time()
            if now - last > IDLE:
                why = 'закрыт: 20 минут без нажатий'
                conn.sendall(frame('\r\n\x1b[33m[Rack Live] Сеанс закрыт: 20 минут без нажатий]\x1b[0m\r\n'.encode(), 2))
                break
            if now - started > MAX:
                why = 'закрыт: прошло 8 часов'
                break
            r, _, _ = select.select([conn, master], [], [], 1.0)
            if master in r:
                try:
                    data = os.read(master, 8192)
                except OSError:
                    data = b''
                if not data:
                    why = 'завершён (команда выхода)'
                    break
                conn.sendall(frame(data, 2))
            if conn in r:
                data = conn.recv(65536)
                if not data:
                    why = 'вкладка закрыта'
                    break
                for op, payload in rd.feed(data):
                    if op == 8:
                        why = 'вкладка закрыта'
                        return why, int(now - started)
                    if op == 9:
                        conn.sendall(frame(payload, 10))
                    elif op in (1, 2):
                        if op == 1 and payload[:1] == b'{':                      # control message from the page: {"resize": [cols, rows]}
                            try:
                                m = json.loads(payload)
                                if 'resize' in m:
                                    c, rr = int(m['resize'][0]), int(m['resize'][1])
                                    if 1 <= c <= 500 and 1 <= rr <= 200:
                                        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', rr, c, 0, 0))
                                continue
                            except (ValueError, KeyError, TypeError):
                                pass
                        last = time.time()
                        os.write(master, payload)
            if proc.poll() is not None and master not in r:
                why = 'завершён'
                break
    except (OSError, ValueError) as e:
        why = f'прерван ({type(e).__name__})'
    finally:
        KEYS.pop(sid, None)
        try:
            os.killpg(proc.pid, signal.SIGHUP)
        except (OSError, ProcessLookupError):
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        try:
            os.close(master)
        except OSError:
            pass
    return why, int(time.time() - started)
