"""Save locations: a SaveData folder (one DSSS file per save) or a saveDataPackFile.bin bundle.

saveDataPackFile.bin (used for iCloud transfers):
    0x00  "PACK", version bytes, u64 user id
    0x10  6 entries of (i32 slot index, 4 pad, u64 size)   slot -1 = system data
    ...   the DSSS files, back to back
    -32   SHA-256 of everything before it
"""
import hashlib
import os
import re
import struct

from .crypto import DsssFile

PACK_MAGIC = b"PACK"
PACK_HEADER_SIZE = 0x70
PACK_ENTRIES = 6

SYSTEM = -1


def slot_name(index):
    if index == SYSTEM:
        return "system"
    if index == 0:
        return "autosave"
    return f"slot{index}"


def _folder_index(filename):
    """data00-1.bin -> -1, data000.bin -> 0, data003Slot.bin -> 3."""
    m = re.fullmatch(r"data00(-1)\.bin|data(\d{3})(?:Slot)?\.bin", filename)
    if not m:
        return None
    return -1 if m.group(1) else int(m.group(2))


class SaveSet:
    """All saves found at a path, decrypted, plus enough info to write them back the same way."""

    def __init__(self, kind, path, files, pack_header=None):
        self.kind = kind            # "pack" | "folder" | "file"
        self.path = path
        self.files = files          # {index: (filename, DsssFile)}
        self.pack_header = pack_header

    @classmethod
    def load(cls, path):
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            files = {}
            for name in sorted(os.listdir(path)):
                idx = _folder_index(name)
                if idx is not None:
                    with open(os.path.join(path, name), "rb") as f:
                        files[idx] = (name, DsssFile.decrypt(f.read()))
            if not files:
                pack = os.path.join(path, "saveDataPackFile.bin")
                if os.path.exists(pack):
                    return cls.load(pack)
                raise SystemExit(f"no RE4 save files found in {path}")
            return cls("folder", path, files)
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] == PACK_MAGIC:
            return cls._load_pack(path, data)
        idx = _folder_index(os.path.basename(path))
        return cls("file", path, {SYSTEM if idx is None else idx: (os.path.basename(path), DsssFile.decrypt(data))})

    @classmethod
    def _load_pack(cls, path, data):
        if hashlib.sha256(data[:-32]).digest() != data[-32:]:
            raise SystemExit("pack checksum mismatch (corrupted file?)")
        files = {}
        off = PACK_HEADER_SIZE
        for i in range(PACK_ENTRIES):
            idx, size = struct.unpack_from("<i4xQ", data, 0x10 + 0x10 * i)
            files[idx] = (f"pack[{idx}]", DsssFile.decrypt(data[off:off + size]))
            off += size
        return cls("pack", path, files, pack_header=data[:PACK_HEADER_SIZE])

    def write(self, out_path):
        out_path = os.path.expanduser(out_path)
        if self.kind == "pack":
            header = bytearray(self.pack_header)
            body = b""
            for i, idx in enumerate(sorted(self.files)):
                blob = self.files[idx][1].encrypt()
                struct.pack_into("<i", header, 0x10 + 0x10 * i, idx)
                struct.pack_into("<Q", header, 0x18 + 0x10 * i, len(blob))
                body += blob
            data = bytes(header) + body
            data += hashlib.sha256(data).digest()
            if os.path.isdir(out_path):
                out_path = os.path.join(out_path, "saveDataPackFile.bin")
            with open(out_path, "wb") as f:
                f.write(data)
            return [out_path]
        if self.kind == "file":
            (name, dsss), = self.files.values()
            if os.path.isdir(out_path):
                out_path = os.path.join(out_path, name)
            with open(out_path, "wb") as f:
                f.write(dsss.encrypt())
            return [out_path]
        os.makedirs(out_path, exist_ok=True)
        written = []
        for name, dsss in self.files.values():
            p = os.path.join(out_path, name)
            with open(p, "wb") as f:
                f.write(dsss.encrypt())
            written.append(p)
        return written
