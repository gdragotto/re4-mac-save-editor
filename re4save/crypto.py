"""DSSS container crypto used by the macOS / iOS build of Resident Evil 4 (2023).

Layout of one save file (all little endian):

    0x00  "DSSS"  u32 version=2  u32 flags=3 (BLOWFISH | HAS_ID)  u32 blowfish_option=3
    0x10  Blowfish-ECB("DSSSDSSS")
    0x18  Blowfish-ECB(user id, 8 bytes)
    0x20  Blowfish-CBC(IV = 0) over the serialized payload (only whole 8-byte blocks;
          a trailing remainder is stored in the clear)
    -4    murmur3_32(everything before, seed 0xFFFFFFFF)

Blowfish runs on little-endian 32-bit halves, which is why every block is byte-swapped
around the (big-endian) pycryptodome implementation. Without pycryptodome a slower
pure-Python implementation is used.
"""
import os
import struct

try:
    if os.environ.get("RE4SAVE_PURE_PYTHON"):
        raise ImportError
    from Crypto.Cipher import Blowfish
except ImportError:  # pure-Python fallback: no dependencies, just slower
    Blowfish = None
from . import blowfish as _pyblowfish

# Key the game loads at runtime (it is not stored as a plain constant in the binary).
KEY = b"wa9Ui_tFKa_6E_D5gVChjM69xMKDX8QxEykYKhzb4cRNLknpCZUra"

MAGIC = b"DSSS"
DATA_OFFSET = 0x20


def _swap32(b):
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


_py = None


def _pure():
    global _py
    if _py is None:
        _py = _pyblowfish.Blowfish(KEY)
    return _py


def _ecb(b, encrypt):
    if Blowfish is None:
        return _pure().ecb(b, encrypt)
    c = Blowfish.new(KEY, Blowfish.MODE_ECB)
    return _swap32((c.encrypt if encrypt else c.decrypt)(_swap32(b)))


def _cbc(b, encrypt):
    if Blowfish is None:
        return _pure().cbc(b, encrypt)
    c = Blowfish.new(KEY, Blowfish.MODE_CBC, iv=b"\0" * 8)
    return _swap32((c.encrypt if encrypt else c.decrypt)(_swap32(b)))


def murmur3_32(data, seed=0xFFFFFFFF):
    M = 0xFFFFFFFF
    h = seed
    n = len(data) // 4
    for (k,) in struct.iter_unpack("<I", data[:n * 4]):
        k = (k * 0xCC9E2D51) & M
        k = ((k << 15) | (k >> 17)) & M
        k = (k * 0x1B873593) & M
        h ^= k
        h = ((h << 13) | (h >> 19)) & M
        h = (h * 5 + 0xE6546B64) & M
    tail = data[n * 4:]
    if tail:
        k = int.from_bytes(tail, "little")
        k = (k * 0xCC9E2D51) & M
        k = ((k << 15) | (k >> 17)) & M
        k = (k * 0x1B873593) & M
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & M
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & M
    h ^= h >> 16
    return h


class DsssFile:
    """A decrypted save file. `payload` can be edited in place (same length) and re-encrypted."""

    def __init__(self, header, user_id, payload):
        self.header = header        # 16 plaintext bytes
        self.user_id = user_id      # 8 bytes, kept as-is so the save stays bound to its owner
        self.payload = payload      # decrypted serialized data

    @classmethod
    def decrypt(cls, data):
        if data[:4] != MAGIC:
            raise ValueError("not a DSSS save file")
        version, flags, bf_opt = struct.unpack_from("<III", data, 4)
        if (version, flags, bf_opt) != (2, 3, 3):
            raise ValueError(f"unsupported DSSS variant (version={version}, flags={flags}, opt={bf_opt}); "
                             "only the macOS/iOS Blowfish format is supported")
        if struct.unpack("<I", data[-4:])[0] != murmur3_32(data[:-4]):
            raise ValueError("file signature mismatch (corrupted or truncated file)")
        if _ecb(data[0x10:0x18], False) != b"DSSSDSSS":
            raise ValueError("wrong key / not an RE4 macOS save")
        user_id = _ecb(data[0x18:0x20], False)
        raw = data[DATA_OFFSET:-4]
        n = len(raw) // 8 * 8
        return cls(data[:0x10], user_id, bytearray(_cbc(raw[:n], False) + raw[n:]))

    def encrypt(self):
        p = bytes(self.payload)
        n = len(p) // 8 * 8
        out = (self.header + _ecb(b"DSSSDSSS", True) + _ecb(self.user_id, True)
               + _cbc(p[:n], True) + p[n:])
        return out + struct.pack("<I", murmur3_32(out))
