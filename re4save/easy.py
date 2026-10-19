"""Guided mode for people who don't want to touch the command line: pick numbers, press Enter."""
import os
import subprocess
import sys

from . import edits, locations, serializer
from .container import SYSTEM, SaveSet, slot_name

RED, GREEN, YELLOW, DIM, BOLD, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
FDA_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"

CP = 999_999
PTAS = 2_000_000
CHOICES = [
    ("ammo", "Infinite ammo", "Cat Ears + all bonus weapons and accessories, already purchased"),
    ("cp", f"{CP:,} CP", "spend it in Bonuses > Extra Content Shop"),
    ("ptas", f"{PTAS:,} pesetas", "in every save slot"),
    ("shop", "Unlock the whole bonus shop", "costumes, figures, artwork, game modes, DLC items"),
    ("challenges", "Complete all challenges", "Bonuses > Records (may also unlock Game Center achievements)"),
]
DEFAULT = ["ammo", "cp", "ptas"]


def say(text=""):
    print(text, flush=True)


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        say()
        sys.exit(0)


def goodbye(code=0):
    ask(f"\n{DIM}Press Enter to close.{RESET}")
    sys.exit(code)


def wait_for_game_to_close():
    while locations.game_running():
        say(f"\n{YELLOW}Resident Evil 4 is open.{RESET} Save your game, quit it (Cmd+Q), then come back here.")
        ask("Press Enter when the game is closed... ")


def find_saves():
    """Return (SaveSet, where) with where = 'local' | 'icloud', guiding the user through permissions."""
    try:
        return SaveSet.load(locations.LOCAL), "local"
    except FileNotFoundError:
        if os.path.exists(locations.ICLOUD):
            say(f"{YELLOW}No local saves found, using your iCloud save.{RESET}")
            return SaveSet.load(locations.ICLOUD), "icloud"
        say(f"{RED}No Resident Evil 4 saves found on this Mac.{RESET} Play the game once, save, and try again.")
        goodbye(1)
    except PermissionError:
        pass

    say(f"\n{BOLD}Your Mac needs to give permission first.{RESET}")
    say("macOS keeps each game's saves private, so this window has to be allowed to open them.\n")
    say(f"  {BOLD}1{RESET}  Allow it (recommended, only once): I'll open the right settings page.")
    has_icloud = os.path.exists(locations.ICLOUD)
    if has_icloud:
        say(f"  {BOLD}2{RESET}  Use my iCloud save instead (you'll press Upload/Download inside the game).")
    say(f"  {BOLD}q{RESET}  Quit")
    choice = ask("\nChoose: ").lower()
    if choice == "1":
        subprocess.run(["open", FDA_PANE])
        say(f"""
In the window that just opened (Privacy & Security > Full Disk Access):
  1. Turn on {BOLD}Terminal{RESET} (use the + button if it isn't listed).
  2. If macOS asks, click "Quit & Reopen". Otherwise quit Terminal yourself (Cmd+Q).
  3. Open the editor again.""")
        goodbye()
    if choice == "2" and has_icloud:
        say(f"\n{BOLD}Before continuing:{RESET} open the game, go to Options > iCloud > {BOLD}Upload{RESET}, then quit the game.")
        ask("Press Enter when that's done... ")
        wait_for_game_to_close()
        return SaveSet.load(locations.ICLOUD), "icloud"
    sys.exit(0)


def summary(saves):
    say(f"\n{BOLD}What's in your saves now{RESET}")
    if SYSTEM in saves.files:
        _, objs = serializer.parse(saves.files[SYSTEM][1].payload)
        shop = edits.ex_shop(objs)
        cp = edits.find(objs, edits.EX_POINT)
        ammo_ready = all(o.fields[edits.IS_BUY].value for bid, o in shop.items()
                         if edits.category_of(bid) in ("weapons", "accessories"))
        say(f"  CP: {cp[0][1].value:,}" if cp else "  CP: ?")
        say(f"  Infinite ammo bonuses: {GREEN + 'unlocked' if ammo_ready else DIM + 'not unlocked'}{RESET}")
    for idx in sorted(i for i in saves.files if i != SYSTEM):
        _, objs = serializer.parse(saves.files[idx][1].payload)
        p = edits.find(objs, edits.PTAS)
        t = edits.find(objs, edits.ELAPSED)
        hours = f"{t[0][1].value / 3.6e9:.1f} h played" if t else ""
        money = f"{p[0][1].value:,} pesetas" if p else ""
        say(f"  {slot_name(idx):<9} {hours:<16} {money}")


def pick():
    say(f"\n{BOLD}What do you want?{RESET}")
    for i, (_, title, detail) in enumerate(CHOICES, 1):
        say(f"  {BOLD}{i}{RESET}  {title:<28}{DIM}{detail}{RESET}")
    say(f"  {BOLD}u{RESET}  Undo: put back my last backup")
    say(f"  {BOLD}q{RESET}  Quit")
    default_nums = " ".join(str(i) for i, (k, _, _) in enumerate(CHOICES, 1) if k in DEFAULT)
    raw = ask(f"\nType the numbers you want, separated by spaces [{default_nums}]: ").lower() or default_nums
    if raw in ("q", "quit"):
        sys.exit(0)
    if raw in ("u", "undo"):
        return "undo"
    picked = []
    for tok in raw.replace(",", " ").split():
        if tok.isdigit() and 1 <= int(tok) <= len(CHOICES):
            picked.append(CHOICES[int(tok) - 1][0])
        else:
            say(f"{RED}'{tok}' isn't one of the options.{RESET}")
            return pick()
    return list(dict.fromkeys(picked))


def apply(saves, picked):
    log = []
    if SYSTEM in saves.files and {"ammo", "cp", "shop", "challenges"} & set(picked):
        dsss = saves.files[SYSTEM][1]
        _, objs = serializer.parse(dsss.payload)
        if "cp" in picked:
            log += edits.set_cp(dsss.payload, objs, CP)
        cats = list(edits.BONUS_CATEGORIES) if "shop" in picked else []
        if "ammo" in picked:
            cats = sorted(set(cats) | {"weapons", "accessories"}, key=list(edits.BONUS_CATEGORIES).index)
        if cats:
            log += edits.unlock(dsss.payload, objs, cats)
        if "challenges" in picked:
            log += edits.complete_challenges(dsss.payload, objs, list(edits.CHALLENGE_SETS))
    if "ptas" in picked:
        for idx in sorted(i for i in saves.files if i != SYSTEM):
            dsss = saves.files[idx][1]
            _, objs = serializer.parse(dsss.payload)
            p = edits.find(objs, edits.PTAS)
            if p and p[0][1].value < PTAS:          # never lower someone's money
                log += [f"{slot_name(idx)}: " + edits.set_ptas(dsss.payload, objs, PTAS)[0]]
    return log


def undo():
    backups = locations.list_backups()
    if not backups:
        say("There are no backups yet.")
        goodbye()
    say(f"Latest backup: {BOLD}{backups[-1]}{RESET}")
    if ask("Put it back? [Y/n] ").lower() in ("", "y", "yes"):
        wait_for_game_to_close()
        try:
            folder, source = locations.restore()
        except PermissionError:
            say(locations.permission_help(locations.LOCAL))
            goodbye(1)
        say(f"{GREEN}Done.{RESET} Your saves are back to how they were on {backups[-1]}.")
    goodbye()


def run():
    os.system("clear")
    say(f"{RED}{BOLD}  RESIDENT EVIL 4 · Mac save editor{RESET}")
    say(f"{DIM}  Your saves are backed up before anything changes.{RESET}")
    wait_for_game_to_close()
    say(f"\n{DIM}Reading your saves (can take up to a minute)...{RESET}")
    saves, where = find_saves()
    summary(saves)

    picked = pick()
    if picked == "undo":
        undo()
    say(f"\nYou picked: {BOLD}{', '.join(t for k, t, _ in CHOICES if k in picked)}{RESET}")
    if ask("Go ahead? [Y/n] ").lower() not in ("", "y", "yes"):
        sys.exit(0)

    wait_for_game_to_close()
    log = apply(saves, picked)
    say(f"\n{DIM}Saving...{RESET}")
    backup = locations.backup(saves.path)
    try:
        saves.write(saves.path)
    except PermissionError:
        say(locations.permission_help(saves.path))
        goodbye(1)

    say("")
    for line in log:
        say(f"  {GREEN}✓{RESET} {line}")
    say(f"\n{GREEN}{BOLD}All done!{RESET}  Backup of your old saves: {DIM}{backup}{RESET}")
    if where == "icloud":
        say(f"\nNow open the game and go to Options > iCloud > {BOLD}Download{RESET} to load the edited saves.")
    else:
        say(f"\nJust start the game. {YELLOW}Don't use Options > iCloud > Download{RESET} (it would bring back "
            "the old cloud copy); use Upload if you want these saves on your other devices.")
    if "ammo" in picked:
        say(f"Equip the Cat Ears in {BOLD}Extras > Leon's Accessories{RESET} for infinite ammo.")
    goodbye()


if __name__ == "__main__":
    run()
