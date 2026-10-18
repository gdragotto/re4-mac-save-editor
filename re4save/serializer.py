"""Reader for RE Engine's binary save serializer (via.storage.saveService).

The format is self-describing, so no type database is needed:

    payload  := { u32 root_hash ; Class }*
    Class    := u32 field_count ; u32 class_hash ; Field[field_count]
    Field    := u32 name_hash ; i32 type ; Value ; align(4)
    Value    := Class                         (type 0x11)
              | Array                         (type -1)
              | align(4) u32 n ; u16[n]       (type 0x0f, UTF-16 string)
              | align(4) u32 size ; align(size) bytes[size]   (scalars / structs)
    Array    := align(4) i32 member_type ; u32 member_size ; u32 count ; i32 kind ;
                [kind == 1: optional 0xFFEEFFEE + u32 hashes[count]] ; elements ; align(4)

Name hashes are murmur3_32(utf-8 name, seed 0xFFFFFFFF). Alignment is relative to the
start of the save *file*, and the payload starts at file offset 0x20.

Values are never re-serialized: edits patch bytes in place, so the layout cannot break.
"""
import struct

from .crypto import DATA_OFFSET, murmur3_32

T_ARRAY, T_ENUM, T_BOOL, T_STRING, T_STRUCT, T_CLASS = -1, 0x1, 0x2, 0xF, 0x10, 0x11
_SCALAR_FMT = {0x2: "<?", 0x3: "<b", 0x4: "<B", 0x5: "<h", 0x6: "<H", 0x7: "<i", 0x8: "<I",
               0x9: "<q", 0xA: "<Q", 0xB: "<f", 0xC: "<d", 0xD: "<B", 0xE: "<H"}
_ENUM_FMT = {1: "<b", 2: "<h", 4: "<i", 8: "<q"}
TYPE_NAMES = {-1: "array", 1: "enum", 2: "bool", 3: "s8", 4: "u8", 5: "s16", 6: "u16", 7: "s32",
              8: "u32", 9: "s64", 10: "u64", 11: "f32", 12: "f64", 13: "c8", 14: "c16",
              15: "string", 16: "struct", 17: "class"}


def h(name):
    return murmur3_32(name.encode(), 0xFFFFFFFF)


class Value:
    __slots__ = ("type", "offset", "size", "fmt", "value")

    def __init__(self, type_, offset, size, fmt, value):
        self.type, self.offset, self.size, self.fmt, self.value = type_, offset, size, fmt, value

    def set(self, buf, new):
        if not self.fmt:
            raise TypeError("only scalar values can be edited")
        struct.pack_into(self.fmt, buf, self.offset, new)
        self.value = new


class Obj:
    __slots__ = ("hash", "fields", "parent")

    def __init__(self, class_hash, parent):
        self.hash = class_hash
        self.fields = {}            # name_hash -> Value | Obj | list
        self.parent = parent

    def get(self, name_hash, default=None):
        return self.fields.get(name_hash, default)


class _Reader:
    def __init__(self, buf):
        self.b = buf
        self.p = 0
        self.objects = []

    def align(self, a):
        self.p = ((self.p + DATA_OFFSET + a - 1) & ~(a - 1)) - DATA_OFFSET

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def string(self):
        self.align(4)
        n = self.u32()
        s = bytes(self.b[self.p:self.p + 2 * n]).decode("utf-16le", "replace")
        v = Value(T_STRING, self.p, 2 * n, None, s)
        self.p += 2 * n
        return v

    def sized(self, t, size):
        if size != 1:
            self.align(size)
        off = self.p
        if t == T_STRUCT:
            self.p += size
            return Value(t, off, size, None, bytes(self.b[off:off + size]))
        if t == T_ARRAY:
            return self.array(None)
        fmt = _ENUM_FMT[size] if t == T_ENUM else _SCALAR_FMT[t]
        v = struct.unpack_from(fmt, self.b, off)[0]
        self.p += struct.calcsize(fmt)
        return Value(t, off, struct.calcsize(fmt), fmt, v)

    def value(self, t, parent):
        if t == T_ARRAY:
            return self.array(parent)
        if t == T_CLASS:
            return self.cls(parent)
        if t == T_STRING:
            return self.string()
        self.align(4)
        return self.sized(t, self.u32())

    def array(self, parent):
        self.align(4)
        member_type, member_size, count, kind = self.i32(), self.u32(), self.u32(), self.i32()
        if kind == 1:
            if self.u32() == 0xFFEEFFEE:
                self.p += 4 * count
            else:
                self.p -= 4
        out = []
        for _ in range(count):
            if kind == 1:
                out.append(self.cls(parent))
            elif member_type == T_STRING:
                out.append(self.string())
            else:
                out.append(self.sized(member_type, member_size))
        self.align(4)
        return out

    def cls(self, parent):
        count, class_hash = self.u32(), self.u32()
        o = Obj(class_hash, parent)
        self.objects.append(o)
        for _ in range(count):
            name, t = self.u32(), self.i32()
            o.fields[name] = self.value(t, o)
            self.align(4)
        return o


def parse(payload):
    """Return (roots, objects): roots is a list of (root_hash, Obj); objects lists every Obj."""
    r = _Reader(payload)
    roots = []
    while r.p < len(payload) - 7:
        root_hash = r.u32()
        roots.append((root_hash, r.cls(None)))
    return roots, r.objects


def walk(obj, names=None, path=""):
    """Yield (path, Value) for every leaf value, for dumping."""
    names = names or {}
    for fh, v in obj.fields.items():
        p = f"{path}.{names.get(fh, '%08x' % fh)}"
        items = v if isinstance(v, list) else [v]
        for i, item in enumerate(items):
            ip = f"{p}[{i}]" if isinstance(v, list) else p
            if isinstance(item, Obj):
                yield from walk(item, names, f"{ip}<{item.hash:08x}>")
            else:
                yield ip, item
