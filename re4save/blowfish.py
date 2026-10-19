"""Pure-Python Blowfish, used when pycryptodome isn't installed (slower, no dependencies).

The initial P-array and S-boxes are the hexadecimal digits of pi, computed here instead
of being pasted in as 4 KB of constants.
"""
import struct


def _pi_words(count):
    """First `count` 32-bit words of pi's fractional part (0x243F6A88, 0x85A308D3, ...)."""
    bits = count * 32 + 64
    one = 1 << bits

    def arctan_inv(x):
        total = term = one // x
        x2, n, sign = x * x, 1, 1
        while term:
            term //= x2
            n += 2
            sign = -sign
            total += sign * (term // n)
        return total

    pi = 16 * arctan_inv(5) - 4 * arctan_inv(239)     # Machin's formula
    frac = (pi - 3 * one) >> 64
    return [(frac >> (32 * (count - 1 - i))) & 0xFFFFFFFF for i in range(count)]


_INIT = None


def _init():
    global _INIT
    if _INIT is None:
        w = _pi_words(18 + 4 * 256)
        _INIT = (w[:18], w[18:])
    return _INIT


class Blowfish:
    def __init__(self, key):
        p0, s0 = _init()
        self.P = list(p0)
        self.S = list(s0)
        n = len(key)
        j = 0
        for i in range(18):
            k = 0
            for _ in range(4):
                k = (k << 8) | key[j]
                j = (j + 1) % n
            self.P[i] ^= k
        l = r = 0
        for i in range(0, 18, 2):
            l, r = self.encrypt_block(l, r)
            self.P[i], self.P[i + 1] = l, r
        for i in range(0, 1024, 2):
            l, r = self.encrypt_block(l, r)
            self.S[i], self.S[i + 1] = l, r

    def encrypt_block(self, l, r):
        P, S = self.P, self.S
        for i in range(16):
            l ^= P[i]
            r ^= ((((S[l >> 24] + S[256 + ((l >> 16) & 0xFF)]) & 0xFFFFFFFF)
                   ^ S[512 + ((l >> 8) & 0xFF)]) + S[768 + (l & 0xFF)]) & 0xFFFFFFFF
            l, r = r, l
        return r ^ P[17], l ^ P[16]

    def decrypt_block(self, l, r):
        P, S = self.P, self.S
        for i in range(17, 1, -1):
            l ^= P[i]
            r ^= ((((S[l >> 24] + S[256 + ((l >> 16) & 0xFF)]) & 0xFFFFFFFF)
                   ^ S[512 + ((l >> 8) & 0xFF)]) + S[768 + (l & 0xFF)]) & 0xFFFFFFFF
            l, r = r, l
        return r ^ P[0], l ^ P[1]

    # The game reads each 8-byte block as two little-endian u32 halves.
    def ecb(self, data, encrypt):
        f = self.encrypt_block if encrypt else self.decrypt_block
        words = struct.unpack("<%dI" % (len(data) // 4), data)
        out = []
        for i in range(0, len(words), 2):
            out.extend(f(words[i], words[i + 1]))
        return struct.pack("<%dI" % len(out), *out)

    def cbc(self, data, encrypt):
        words = struct.unpack("<%dI" % (len(data) // 4), data)
        out = [0] * len(words)
        pl = pr = 0
        if encrypt:
            f = self.encrypt_block
            for i in range(0, len(words), 2):
                pl, pr = f(words[i] ^ pl, words[i + 1] ^ pr)
                out[i], out[i + 1] = pl, pr
        else:
            f = self.decrypt_block
            for i in range(0, len(words), 2):
                cl, cr = words[i], words[i + 1]
                l, r = f(cl, cr)
                out[i], out[i + 1] = l ^ pl, r ^ pr
                pl, pr = cl, cr
        return struct.pack("<%dI" % len(out), *out)
