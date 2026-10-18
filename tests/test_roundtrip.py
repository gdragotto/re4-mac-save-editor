"""Self-contained tests: synthetic saves are built from scratch, no real save data is shipped."""
import hashlib
import os
import struct
import tempfile
import unittest

from re4save import edits, serializer
from re4save.cli import main
from re4save.container import SaveSet
from re4save.crypto import DsssFile, murmur3_32

H = serializer.h


class W:
    """Minimal writer for the serializer format (alignment relative to file offset 0x20)."""

    def __init__(self):
        self.b = bytearray()

    def align(self, a):
        while (len(self.b) + 0x20) % a:
            self.b += b"\0"

    def u32(self, v):
        self.b += struct.pack("<I", v)

    def i32(self, v):
        self.b += struct.pack("<i", v)

    def field_scalar(self, name, t, fmt, value):
        self.u32(name)
        self.i32(t)
        size = struct.calcsize(fmt)
        self.align(4)
        self.u32(size)
        self.align(size)
        self.b += struct.pack(fmt, value)
        self.align(4)

    def cls(self, class_hash, fields):
        self.u32(len(fields))
        self.u32(class_hash)
        for f in fields:
            f(self)


def shop_entry(bonus_id, unlocked):
    return lambda w: w.cls(0x1234, [
        lambda w: w.field_scalar(edits.BONUS_ID, 7, "<i", bonus_id),
        lambda w: w.field_scalar(edits.IS_UNLOCK, 2, "<?", unlocked),
        lambda w: w.field_scalar(edits.IS_BUY, 2, "<?", False),
    ])


def system_payload():
    w = W()
    w.u32(0xD0986E29)
    ids = [6, 7, 38, 39, 69]

    def shop_list(w):
        w.u32(H("SaveRecordExShopList"))
        w.i32(-1)
        w.align(4)
        w.i32(0x11); w.u32(8); w.u32(len(ids)); w.i32(1)
        for i in ids:
            shop_entry(i, i == 38)(w)
        w.align(4)

    def records(w):
        w.u32(0xF83B6FF0)
        w.i32(-1)
        w.align(4)
        w.i32(0x11); w.u32(8); w.u32(3); w.i32(1)
        for rid in (0, 1, 200):
            w.cls(0x5678, [lambda w, rid=rid: w.field_scalar(edits.RECORD_ID, 7, "<i", rid),
                           lambda w: w.field_scalar(edits.IS_UNLOCK, 2, "<?", False),
                           lambda w: w.field_scalar(edits.RECORD_COUNT, 7, "<i", 0)])
        w.align(4)

    w.cls(0xAAAA, [shop_list, records, lambda w: w.field_scalar(edits.EX_POINT, 7, "<i", 20400)])
    return bytes(w.b)


def slot_payload():
    w = W()
    w.u32(0xD0986E29)
    weapon = lambda w: w.cls(0xEE05DC31, [
        lambda w: w.field_scalar(edits.CURRENT_AMMO, 7, "<i", 112800000),
        lambda w: w.field_scalar(edits.ITEM_ID, 7, "<i", 274835456),
        lambda w: w.field_scalar(edits.ITEM_COUNT, 7, "<i", 1)])
    ammo = lambda w: w.cls(0xA84686D9, [
        lambda w: w.field_scalar(edits.ITEM_ID, 7, "<i", 112800000),
        lambda w: w.field_scalar(edits.ITEM_COUNT, 7, "<i", 12)])
    herb = lambda w: w.cls(0xA84686D9, [
        lambda w: w.field_scalar(edits.ITEM_ID, 7, "<i", 114416000),
        lambda w: w.field_scalar(edits.ITEM_COUNT, 7, "<i", 1)])

    def obj_field(name, maker):
        def f(w):
            w.u32(name); w.i32(0x11); maker(w); w.align(4)
        return f

    w.cls(0xBBBB, [obj_field(1, weapon), obj_field(2, ammo), obj_field(3, herb),
                   lambda w: w.field_scalar(edits.PTAS, 7, "<i", 1000),
                   lambda w: w.field_scalar(edits.ELAPSED, 10, "<Q", 3_600_000_000)])
    return bytes(w.b)


def make_dsss(payload):
    header = b"DSSS" + struct.pack("<III", 2, 3, 3)
    return DsssFile(header, b"\x11" * 8, bytearray(payload)).encrypt()


def make_pack(blobs):
    header = bytearray(b"PACK" + b"\x02\x01\x06\x00" + b"\x22" * 8 + b"\0" * (0x70 - 16))
    for i, (idx, blob) in enumerate(blobs):
        struct.pack_into("<i", header, 0x10 + 0x10 * i, idx)
        struct.pack_into("<Q", header, 0x18 + 0x10 * i, len(blob))
    data = bytes(header) + b"".join(b for _, b in blobs)
    return data + hashlib.sha256(data).digest()


class Tests(unittest.TestCase):
    def test_murmur_known_values(self):
        self.assertEqual(murmur3_32(b"_ExPoint"), 0xB1BF9EBA)
        self.assertEqual(murmur3_32(b"PTAS"), 0x70C6ACD7)

    def test_dsss_roundtrip(self):
        blob = make_dsss(system_payload())
        d = DsssFile.decrypt(blob)
        self.assertEqual(bytes(d.payload), system_payload())
        self.assertEqual(d.encrypt(), blob)

    def test_edit_folder(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = os.path.join(t, "SaveData"), os.path.join(t, "out")
            os.mkdir(src)
            open(os.path.join(src, "data00-1.bin"), "wb").write(make_dsss(system_payload()))
            open(os.path.join(src, "data001Slot.bin"), "wb").write(make_dsss(slot_payload()))
            main(["edit", src, "-o", dst, "--infinite-ammo", "--cp", "999999", "--ptas", "5000", "--ammo", "50"])
            s = SaveSet.load(dst)
            _, objs = serializer.parse(s.files[-1][1].payload)
            self.assertEqual(edits.find(objs, edits.EX_POINT)[0][1].value, 999999)
            shop = edits.ex_shop(objs)
            for bid in (6, 7, 38, 39):
                self.assertTrue(shop[bid].fields[edits.IS_UNLOCK].value and shop[bid].fields[edits.IS_BUY].value)
            self.assertFalse(shop[69].fields[edits.IS_BUY].value)      # figures untouched
            _, objs = serializer.parse(s.files[1][1].payload)
            self.assertEqual(edits.find(objs, edits.PTAS)[0][1].value, 5000)
            counts = {o.fields[edits.ITEM_ID].value: o.fields[edits.ITEM_COUNT].value for o in objs
                      if edits.ITEM_ID in o.fields}
            self.assertEqual(counts[112800000], 50)
            self.assertEqual(counts[114416000], 1)                       # non-ammo untouched

    def test_challenges(self):
        with tempfile.TemporaryDirectory() as t:
            src, dst = os.path.join(t, "data00-1.bin"), os.path.join(t, "out.bin")
            open(src, "wb").write(make_dsss(system_payload()))
            main(["edit", src, "-o", dst, "--challenges", "separate-ways"])
            _, objs = serializer.parse(SaveSet.load(dst).files[-1][1].payload)
            done = {rid: o.fields[edits.IS_UNLOCK].value for rid, o in edits.challenges(objs).items()}
            self.assertEqual(done, {0: False, 1: False, 200: True})

    def test_pack_roundtrip_and_edit(self):
        with tempfile.TemporaryDirectory() as t:
            pack = make_pack([(-1, make_dsss(system_payload()))] + [(i, make_dsss(slot_payload())) for i in range(5)])
            src = os.path.join(t, "saveDataPackFile.bin")
            open(src, "wb").write(pack)
            SaveSet.load(src).write(os.path.join(t, "rt.bin"))
            self.assertEqual(open(os.path.join(t, "rt.bin"), "rb").read(), pack)
            main(["edit", src, "-o", os.path.join(t, "mod.bin"), "--slot", "2", "--ptas", "7"])
            s = SaveSet.load(os.path.join(t, "mod.bin"))
            for i in range(5):
                _, objs = serializer.parse(s.files[i][1].payload)
                self.assertEqual(edits.find(objs, edits.PTAS)[0][1].value, 7 if i == 2 else 1000)


if __name__ == "__main__":
    unittest.main()
