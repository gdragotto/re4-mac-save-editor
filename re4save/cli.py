import argparse
import sys

from . import edits, locations, serializer
from .container import SYSTEM, SaveSet, slot_name


def _load(a):
    path = locations.resolve(a.path, a.icloud)
    try:
        return SaveSet.load(path)
    except PermissionError:
        sys.exit(locations.permission_help(path))
    except FileNotFoundError:
        if path == locations.LOCAL:
            sys.exit(f"game save folder not found: {path}\nHas the game been started on this Mac?")
        sys.exit(f"not found: {path}")
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
    saves = _load(a)
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
    saves = _load(a)
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
    _check_range("cp", a.cp, 0, edits.MAX_MONEY)
    _check_range("ptas", a.ptas, 0, edits.MAX_MONEY)
    _check_range("ammo", a.ammo, 1, edits.MAX_AMMO)
    unlock = sorted(set(edits.BONUS_CATEGORIES) if "all" in (a.unlock or []) else set(a.unlock or []),
                    key=list(edits.BONUS_CATEGORIES).index)
    if a.infinite_ammo:
        unlock = sorted(set(unlock) | {"weapons", "accessories"}, key=list(edits.BONUS_CATEGORIES).index)
    chal = sorted(set(edits.CHALLENGE_SETS) if "all" in (a.challenges or []) else set(a.challenges or []))
    wants_system = a.cp is not None or unlock or chal
    wants_slots = a.ptas is not None or a.ammo is not None
    if not (wants_system or wants_slots):
        sys.exit("nothing to do: pass at least one of --infinite-ammo, --cp, --unlock, --challenges, --ptas, --ammo")

    saves = _load(a)
    if not a.output and locations.game_running() and not a.force:
        sys.exit("Resident Evil 4 is running: save, quit the game and run this again "
                 "(otherwise the game overwrites the edit). --force skips this check.")
    changed = False
    if wants_system:
        if SYSTEM not in saves.files:
            sys.exit("system save (data00-1.bin) not found; --cp/--unlock/--challenges need it")
        dsss = saves.files[SYSTEM][1]
        _, objs = serializer.parse(dsss.payload)
        log = []
        if a.cp is not None:
            log += edits.set_cp(dsss.payload, objs, a.cp)
        if unlock:
            log += edits.unlock(dsss.payload, objs, unlock, purchase=not a.unlock_only)
        if chal:
            log += edits.complete_challenges(dsss.payload, objs, chal)
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

    if a.output:
        written = saves.write(a.output)
    else:
        if not a.no_backup:
            print(f"backup: {locations.backup(saves.path)}")
        try:
            written = saves.write(saves.path)
        except PermissionError:
            sys.exit(locations.permission_help(saves.path))
    for p in written:
        print(f"wrote {p}")
    if not a.output and saves.path == locations.ICLOUD:
        print("Now start the game and use Options > iCloud > Download to load the edited save.")


def cmd_restore(a):
    if a.list:
        for b in locations.list_backups():
            print(b)
        return
    if locations.game_running() and not a.force:
        sys.exit("Resident Evil 4 is running: quit it first (--force skips this check).")
    try:
        folder, source = locations.restore(a.backup)
    except PermissionError:
        sys.exit(locations.permission_help(locations.LOCAL))
    print(f"restored {folder}\n      -> {source}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="re4save", description="Save editor for Resident Evil 4 (2023) on macOS / iOS.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def where(sp):
        sp.add_argument("path", nargs="?",
                        help="SaveData folder, saveDataPackFile.bin or single save file "
                             "(default: the folder the game loads from)")
        sp.add_argument("--icloud", action="store_true",
                        help="use the iCloud copy (what Options > iCloud > Upload/Download uses)")

    i = sub.add_parser("info", help="show what is in your saves")
    where(i)
    i.set_defaults(func=cmd_info)

    e = sub.add_parser("edit", help="modify saves (in place, after a backup)",
                       description="Edits the game's saves in place after backing them up to "
                                   f"'{locations.BACKUP_ROOT}'. Use -o to write a copy elsewhere instead.")
    where(e)
    e.add_argument("-o", "--output", help="write the result here instead of overwriting (no backup needed)")
    e.add_argument("--no-backup", action="store_true", help="overwrite without making a backup")
    e.add_argument("--force", action="store_true", help="edit even if the game seems to be running")
    e.add_argument("--in-place", action="store_true", help=argparse.SUPPRESS)  # default since 1.2
    g = e.add_argument_group("system save (shared by every slot)")
    g.add_argument("--infinite-ammo", action="store_true",
                   help="shortcut for --unlock weapons accessories: unlocks + purchases the bonus weapons and the "
                        "Cat Ears accessory (infinite ammo for everything except rocket launchers)")
    g.add_argument("--cp", type=int, metavar="N", help=f"set Extra Content Shop CP (max {edits.MAX_MONEY:,})")
    g.add_argument("--unlock", nargs="+", metavar="CATEGORY", choices=list(edits.BONUS_CATEGORIES) + ["all"],
                   help="unlock Extra Content Shop items: " + ", ".join(edits.BONUS_CATEGORIES) + ", all")
    g.add_argument("--unlock-only", action="store_true",
                   help="make items available to buy with CP instead of marking them purchased")
    g.add_argument("--challenges", nargs="+", metavar="SET", choices=list(edits.CHALLENGE_SETS) + ["all"],
                   help="mark challenges (Bonuses > Records) completed: main, separate-ways, all. "
                        "Their CP rewards are not paid out, use --cp for that")
    s = e.add_argument_group("slot saves")
    s.add_argument("--slot", metavar="LIST", help="which slots: 'all' (default), 'autosave', or e.g. '1,3'")
    s.add_argument("--ptas", type=int, metavar="N", help=f"set pesetas (max {edits.MAX_MONEY:,})")
    s.add_argument("--ammo", type=int, metavar="N",
                   help="set every ammo stack in inventory/storage to N rounds (experimental, the game may clamp it)")
    e.set_defaults(func=cmd_edit)

    r = sub.add_parser("restore", help="put a backup back where it came from")
    r.add_argument("backup", nargs="?", help="backup folder name (default: the most recent)")
    r.add_argument("--list", action="store_true", help="list backups")
    r.add_argument("--force", action="store_true", help="restore even if the game seems to be running")
    r.set_defaults(func=cmd_restore)

    d = sub.add_parser("dump", help="print every field of one save (for exploring)")
    where(d)
    d.add_argument("--save", default="system", help="system (default), autosave, or slot number")
    d.add_argument("-o", "--output", help="write to a file instead of stdout")
    d.set_defaults(func=cmd_dump)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
