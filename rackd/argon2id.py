"""Argon2id (RFC 9106) on the standard library only: Rack Live also runs on Entware and OpenWrt, where a compiled package is not an option.
Needed for the sign-in of KeeneticOS 5.2 (x-ndw4), whose parameters are tiny (8 KiB, 2 passes). It is slow on big parameters, so there is a limit."""
import hashlib

MASK = (1 << 64) - 1
MAX_KIB_PASSES = 64 * 1024          # memory (KiB) × passes; about a minute of work on a NAS


def _le32(n):
    return n.to_bytes(4, 'little')


def _hprime(data, size):
    """H′: the variable-length hash built on BLAKE2b."""
    data = _le32(size) + data
    if size <= 64:
        return hashlib.blake2b(data, digest_size=size).digest()
    out, v = [], hashlib.blake2b(data, digest_size=64).digest()
    r = (size + 31) // 32 - 2
    for _ in range(r - 1):
        out.append(v[:32])
        v = hashlib.blake2b(v, digest_size=64).digest()
    out.append(v[:32])
    out.append(hashlib.blake2b(v, digest_size=size - 32 * r).digest())
    return b''.join(out)


def _round(v, a, b, c, d):
    def gb(a, b, c, d):
        x, y, z, w = v[a], v[b], v[c], v[d]
        x = (x + y + 2 * (x & 0xffffffff) * (y & 0xffffffff)) & MASK
        w ^= x
        w = ((w >> 32) | (w << 32)) & MASK
        z = (z + w + 2 * (z & 0xffffffff) * (w & 0xffffffff)) & MASK
        y ^= z
        y = ((y >> 24) | (y << 40)) & MASK
        x = (x + y + 2 * (x & 0xffffffff) * (y & 0xffffffff)) & MASK
        w ^= x
        w = ((w >> 16) | (w << 48)) & MASK
        z = (z + w + 2 * (z & 0xffffffff) * (w & 0xffffffff)) & MASK
        y ^= z
        y = ((y >> 63) | (y << 1)) & MASK
        v[a], v[b], v[c], v[d] = x, y, z, w
    return gb


def _permute(v, i):
    """P over 16 words starting at the given list of indexes."""
    gb = _round(v, 0, 0, 0, 0)
    gb(i[0], i[4], i[8], i[12]); gb(i[1], i[5], i[9], i[13]); gb(i[2], i[6], i[10], i[14]); gb(i[3], i[7], i[11], i[15])
    gb(i[0], i[5], i[10], i[15]); gb(i[1], i[6], i[11], i[12]); gb(i[2], i[7], i[8], i[13]); gb(i[3], i[4], i[9], i[14])


def _g(x, y):
    """The compression function G: 1024-byte blocks as 128 words."""
    r = [a ^ b for a, b in zip(x, y)]
    q = r[:]
    for row in range(8):
        _permute(q, list(range(16 * row, 16 * row + 16)))
    for col in range(8):
        _permute(q, [2 * col + 16 * k + d for k in range(8) for d in (0, 1)])
    return [a ^ b for a, b in zip(r, q)]


def argon2id(password, salt, passes, memory_kib, size, parallelism=1, secret=b'', data=b''):
    if isinstance(password, str):
        password = password.encode()
    if passes < 1 or parallelism < 1 or memory_kib < 8 * parallelism or size < 4:
        raise ValueError('неверные параметры Argon2id')
    if memory_kib * passes > MAX_KIB_PASSES:
        raise ValueError(f'слишком большие параметры Argon2id ({memory_kib} КиБ × {passes})')
    h0 = hashlib.blake2b(b''.join((_le32(parallelism), _le32(size), _le32(memory_kib), _le32(passes), _le32(0x13), _le32(2),
                                   _le32(len(password)), password, _le32(len(salt)), salt, _le32(len(secret)), secret,
                                   _le32(len(data)), data)), digest_size=64).digest()
    seg = memory_kib // (4 * parallelism)
    cols = seg * 4                                     # blocks in one lane
    total = cols * parallelism
    words = lambda b: [int.from_bytes(b[i:i + 8], 'little') for i in range(0, 1024, 8)]
    mem = [None] * total
    for lane in range(parallelism):
        mem[lane * cols] = words(_hprime(h0 + _le32(0) + _le32(lane), 1024))
        mem[lane * cols + 1] = words(_hprime(h0 + _le32(1) + _le32(lane), 1024))
    zero = [0] * 128
    for r in range(passes):
        for s in range(4):
            for lane in range(parallelism):
                independent = r == 0 and s < 2         # the «i» part of Argon2id
                start = 2 if r == 0 and s == 0 else 0
                inp, addr = None, None
                if independent:
                    inp = [r, lane, s, total, passes, 2, 0] + [0] * 121

                    def next_addr():
                        inp[6] += 1
                        return _g(zero, _g(zero, inp))
                    if start:
                        addr = next_addr()
                cur = lane * cols + s * seg + start
                prev = cur - 1 if cur % cols else cur + cols - 1
                for i in range(start, seg):
                    if cur % cols == 1:
                        prev = cur - 1
                    if independent:
                        if i % 128 == 0:
                            addr = next_addr()
                        pseudo = addr[i % 128]
                    else:
                        pseudo = mem[prev][0]
                    ref_lane = lane if r == 0 and s == 0 else (pseudo >> 32) % parallelism
                    same = ref_lane == lane
                    if r == 0:
                        area = i - 1 if s == 0 else (s * seg + i - 1 if same else s * seg - (i == 0))
                    else:
                        area = cols - seg + i - 1 if same else cols - seg - (i == 0)
                    j1 = pseudo & 0xffffffff
                    rel = area - 1 - ((area * ((j1 * j1) >> 32)) >> 32)
                    first = 0 if r == 0 or s == 3 else (s + 1) * seg
                    ref = mem[ref_lane * cols + (first + rel) % cols]
                    new = _g(mem[prev], ref)
                    mem[cur] = new if r == 0 else [a ^ b for a, b in zip(mem[cur], new)]
                    cur += 1
                    prev += 1
    last = mem[cols - 1]
    for lane in range(1, parallelism):
        last = [a ^ b for a, b in zip(last, mem[lane * cols + cols - 1])]
    return _hprime(b''.join(w.to_bytes(8, 'little') for w in last), size)
