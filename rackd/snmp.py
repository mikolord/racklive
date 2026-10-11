"""Minimal SNMP v1/v2c client (GET, GETBULK walk) — standard library only."""
import random, socket

# ── BER encoding ──
def _len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(b)]) + b


def _tlv(tag, payload):
    return bytes([tag]) + _len(len(payload)) + payload


def _int(v):
    n = (v.bit_length() + 8) // 8 or 1
    return _tlv(0x02, v.to_bytes(n, 'big', signed=True))


def _oid(oid):
    parts = [int(x) for x in oid.strip('.').split('.')]
    out = bytearray([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(chunk))
    return _tlv(0x06, bytes(out))


def _msg(version, community, pdu_tag, req_id, oids, non_rep=0, max_rep=0):
    vbs = b''.join(_tlv(0x30, _oid(o) + b'\x05\x00') for o in oids)
    pdu = _tlv(pdu_tag, _int(req_id) + _int(non_rep) + _int(max_rep) + _tlv(0x30, vbs))
    return _tlv(0x30, _int(version) + _tlv(0x04, community.encode()) + pdu)


# ── BER decoding ──
def _read(data, i):
    tag = data[i]
    i += 1
    ln = data[i]
    i += 1
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(data[i:i + k], 'big')
        i += k
    return tag, data[i:i + ln], i + ln


def _dec_oid(b):
    parts = [b[0] // 40, b[0] % 40]
    v = 0
    for x in b[1:]:
        v = (v << 7) | (x & 0x7F)
        if not x & 0x80:
            parts.append(v)
            v = 0
    return '.'.join(map(str, parts))


END = object()


def _value(tag, b):
    if tag == 0x02:
        return int.from_bytes(b, 'big', signed=True) if b else 0
    if tag in (0x41, 0x42, 0x43, 0x46, 0x47):          # Counter32, Gauge32, TimeTicks, Counter64
        return int.from_bytes(b, 'big') if b else 0
    if tag == 0x04:
        return b
    if tag == 0x06:
        return _dec_oid(b)
    if tag == 0x40:
        return '.'.join(str(x) for x in b)
    if tag in (0x80, 0x81, 0x82):
        return END
    return None


def _parse(data):
    _, msg, _ = _read(data, 0)
    i = 0
    _, _, i = _read(msg, i)                               # version
    _, _, i = _read(msg, i)                               # community
    _, pdu, _ = _read(msg, i)
    j = 0
    _, rid, j = _read(pdu, j)
    _, err, j = _read(pdu, j)
    _, _, j = _read(pdu, j)
    _, vbl, _ = _read(pdu, j)
    out, k = [], 0
    while k < len(vbl):
        _, vb, k = _read(vbl, k)
        _, ob, m = _read(vb, 0)
        tag, val, _ = _read(vb, m)
        out.append((_dec_oid(ob), _value(tag, val)))
    return int.from_bytes(rid, 'big', signed=True), int.from_bytes(err, 'big') if err else 0, out


class SnmpError(Exception):
    pass


class Snmp:
    def __init__(self, host, community='public', version='2c', port=161, timeout=2.0, retries=2):
        self.addr = (host, int(port))
        self.community = community
        self.version = 0 if str(version) == '1' else 1
        self.timeout, self.retries = timeout, retries

    def _req(self, tag, oids, non_rep=0, max_rep=0):
        rid = random.randint(1, 2 ** 31 - 1)
        pkt = _msg(self.version, self.community, tag, rid, oids, non_rep, max_rep)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.timeout)
        try:
            for _ in range(self.retries + 1):
                s.sendto(pkt, self.addr)
                try:
                    while True:
                        data, _ = s.recvfrom(65535)
                        r, err, vbs = _parse(data)
                        if r == rid:
                            if err and err != 2:
                                raise SnmpError(f'SNMP error {err}')
                            return vbs
                except socket.timeout:
                    continue
            raise SnmpError('нет ответа по SNMP (проверьте community и что SNMP включён)')
        finally:
            s.close()

    def get(self, *oids):
        return {o: v for o, v in self._req(0xA0, list(oids)) if v is not END}

    def walk(self, base, max_rep=20, limit=5000):
        """GETBULK walk; some agents silently drop big bulk replies, so the batch shrinks on timeout."""
        base = base.strip('.')
        out, cur = {}, base
        while len(out) < limit:
            if self.version == 0 or max_rep <= 1:
                vbs = self._req(0xA1, [cur])
            else:
                try:
                    vbs = self._req(0xA5, [cur], 0, max_rep)
                except SnmpError:
                    if max_rep <= 5:
                        raise
                    max_rep = max(1, max_rep // 3)
                    continue
            done = False
            for oid, val in vbs:
                if val is END or not oid.startswith(base + '.'):
                    done = True
                    break
                out[oid] = val
                cur = oid
            if done or not vbs:
                break
        return out

    def table(self, base, optional=False):
        """walk → {index_suffix: value}; optional=True returns {} when the agent doesn't answer for this MIB"""
        base = base.strip('.')
        try:
            if optional:                                   # quick probe so unsupported MIBs don't cost seconds of retries
                saved = self.retries
                self.retries = 0
                try:
                    probe = self._req(0xA1, [base])
                finally:
                    self.retries = saved
                if not probe or probe[0][1] is END or not probe[0][0].startswith(base + '.'):
                    return {}
            return {oid[len(base) + 1:]: v for oid, v in self.walk(base).items()}
        except SnmpError:
            if optional:
                return {}
            raise


def text(v):
    if isinstance(v, bytes):
        try:
            return v.decode('utf-8').strip('\x00').strip()
        except UnicodeDecodeError:
            return v.hex(':')
    return '' if v is None else str(v)


def mac(v):
    return ':'.join(f'{b:02x}' for b in v) if isinstance(v, bytes) and len(v) == 6 else text(v)
