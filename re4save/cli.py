import argparse
import os
import shutil
import sys
import time

from . import edits, serializer
from .container import SYSTEM, SaveSet, slot_name

DEFAULT_DIR = "~/Library/Containers/jp.co.capcom.RE4US/Data/Library/Application Support/CAPCOM/jp.co.capcom.RE4US/SaveData"


def _load(path):
    try:
        return SaveSet.load(path)
    except PermissionError:
        sys.exit(f"Permission denied reading {path}.\nmacOS protects other apps' data: copy the SaveData folder "
                 "somewhere else with Finder first (see README), or give your terminal Full Disk Access.")
    except ValueError as e:
        sys.exit(f"Cannot read save: {e}")


def _parse_slots(spec, saves):
    slots = sorted(i for i in saves.files if i != SYSTEM)
    if spec in (None, "all"):
        return slots
    wanted = []
    for part in spec.split(","):
        part = part.strip().lower()
        i = 0 if part in ("auto", "autosave") else int(part.replace("slot", ""))
        if i not in saves.files:
            sys.exit(f"slot {part} not found; available: {', '.join(slot_name(s) for s in slots)}")
        wanted.append(i)
    return wanted


def cmd_info(a):
    saves = _load(a.path)
    print(f"{saves.kind}: {saves.path}")
    for idx in sorted(saves.files):
        name, dsss = saves.files[idx]
        _, objs = serializer.parse(dsss.payload)
        if idx == SYSTEM:
            print(f"\n[system]  {name}")
            for line in edits.summarize_system(objs):
                print("  " + line)
        else:
            print(f"[{slot_name(idx)}]  {name}: {edits.summarize_slot(objs)}")


def cmd_dump(a):
    saves = _load(a.path)
    idx = SYSTEM if a.save == "system" else _parse_slots(a.save, saves)[0]
    _, dsss = saves.files[idx]
    roots, _ = serializer.parse(dsss.payload)
    out = open(a.output, "w") if a.output else sys.stdout
    for root_hash, obj in roots:
        for path, v in serializer.walk(obj, edits.NAMES, f"@{root_hash:08x}<{obj.hash:08x}>"):
            out.write(f"{v.offset:08x} {serializer.TYPE_NAMES.get(v.type, v.type):<6} {path} = {v.value!r}\n")


def _check_range(name, v, lo, hi):
    if v is not None and not lo <= v <= hi:
        sys.exit(f"--{name} must be between {lo:,} and {hi:,}")


def cmd_edit(a):
    if not a.output and not a.in_place:
        sys.exit("choose where to write: -o OUTPUT (recommended) or --in-place (makes a backup)")
    _check_range("cp", a.cp, 0, edits.MAX_MONEY)
    _check_range("ptas", a.ptas, 0, edits.MAX_MONEY)
    _check_range("ammo", a.ammo, 1, edits.MAX_AMMO)
    unlock = sorted(set(edits.BONUS_CATEGORIES) if "all" in (a.unlock or []) else set(a.unlock or []),
                    key=list(edits.BONUS_CATEGORIES).index)
    if a.infinite_ammo:
        unlock = sorted(set(unlock) | {"weapons", "accessories"}, key=list(edits.BONUS_CATEGORIES).index)
    wants_system = a.cp is not None or unlock
    wants_slots = a.ptas is not None or a.ammo is not None
    if not (wants_system or wants_slots):
        sys.exit("nothing to do: pass at least one of --infinite-ammo, --cp, --unlock, --ptas, --ammo")

    saves = _load(a.path)
    changed = False
    if wants_system:
        if SYSTEM not in saves.files:
            sys.exit("system save (data00-1.bin) not found; --cp/--unlock need it")
        dsss = saves.files[SYSTEM][1]
        _, objs = serializer.parse(dsss.payload)
        log = []
        if a.cp is not None:
            log += edits.set_cp(dsss.payload, objs, a.cp)
        if unlock:
            log += edits.unlock(dsss.payload, objs, unlock, purchase=not a.unlock_only)
        print("[system]\n  " + "\n  ".join(log))
        changed = True
    if wants_slots:
        for idx in _parse_slots(a.slot, saves):
            dsss = saves.files[idx][1]
            _, objs = serializer.parse(dsss.payload)
            log = []
            if a.ptas is not None:
                log += edits.set_ptas(dsss.payload, objs, a.ptas)
            if a.ammo is not None:
                log += edits.set_ammo(dsss.payload, objs, a.ammo)
            print(f"[{slot_name(idx)}]\n  " + "\n  ".join(log))
            changed = True
    if not changed:
        return

    if a.in_place:
        backup = f"{saves.path.rstrip('/')}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        (shutil.copytree if os.path.isdir(saves.path) else shutil.copy2)(saves.path, backup)
        print(f"backup: {backup}")
        written = saves.write(saves.path)
    else:
        written = saves.write(a.output)
    for p in written:
        print(f"wrote {p}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="re4save", description="Save editor for Resident Evil 4 (2023) on macOS / iOS.")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("info", help="show what is in a save folder / pack / file")
    i.add_argument("path", nargs="?", default=DEFAULT_DIR)
    i.set_defaults(func=cmd_info)

    e = sub.add_parser("edit", help="modify saves",
                       description="PATH is a SaveData folder, a saveDataPackFile.bin or a single save file. "
                                   "Output keeps the same format as the input.")
    e.add_argument("path")
    out = e.add_mutually_exclusive_group()
    out.add_argument("-o", "--output", help="output folder or file (input stays untouched)")
    out.add_argument("--in-place", action="store_true", help="overwrite the input after backing it up")
    g = e.add_argument_group("system save (shared by every slot)")
    g.add_argument("--infinite-ammo", action="store_true",
                   help="shortcut for --unlock weapons accessories: unlocks + purchases the bonus weapons and the "
                        "Cat Ears accessory (infinite ammo for everything except rocket launchers)")
    g.add_argument("--cp", type=int, metavar="N", help=f"set Extra Content Shop CP (max {edits.MAX_MONEY:,})")
    g.add_argument("--unlock", nargs="+", metavar="CATEGORY", choices=list(edits.BONUS_CATEGORIES) + ["all"],
                   help="unlock Extra Content Shop items: " + ", ".join(edits.BONUS_CATEGORIES) + ", all")
    g.add_argument("--unlock-only", action="store_true",
                   help="make items available to buy with CP instead of marking them purchased")
    s = e.add_argument_group("slot saves")
    s.add_argument("--slot", metavar="LIST", help="which slots: 'all' (default), 'autosave', or e.g. '1,3'")
    s.add_argument("--ptas", type=int, metavar="N", help=f"set pesetas (max {edits.MAX_MONEY:,})")
    s.add_argument("--ammo", type=int, metavar="N",
                   help="set every ammo stack in inventory/storage to N rounds (experimental, the game may clamp it)")
    e.set_defaults(func=cmd_edit)

    d = sub.add_parser("dump", help="print every field of one save (for exploring)")
    d.add_argument("path")
    d.add_argument("--save", default="system", help="system (default), autosave, or slot number")
    d.add_argument("-o", "--output", help="write to a file instead of stdout")
    d.set_defaults(func=cmd_dump)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
