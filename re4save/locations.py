"""Where the game keeps its saves, backups, and the safety checks around overwriting them."""
import json
import os
import shutil
import subprocess
import sys
import time

BUNDLE = "jp.co.capcom.RE4US"
# What the game loads at boot (inside its sandbox; reading it needs Full Disk Access for your terminal)
LOCAL = os.path.expanduser(f"~/Library/Containers/{BUNDLE}/Data/Library/Application Support/CAPCOM/{BUNDLE}/SaveData")
# What Options > iCloud > Upload/Download exchanges with the game
ICLOUD = os.path.expanduser(
    f"~/Library/Mobile Documents/iCloud~jp~co~capcom~RE4US/Documents/CAPCOM/{BUNDLE}/SaveData/saveDataPackFile.bin")
BACKUP_ROOT = os.path.expanduser("~/Documents/RE4 save backups")
GAME_PROCESS = "Resident Evil 4.app/Contents/MacOS/Resident Evil 4"

FDA_HELP = """\
macOS blocks your terminal from reading the game's save folder:
  {path}

Pick one:
  1. Give your terminal app Full Disk Access (one time): System Settings > Privacy & Security >
     Full Disk Access > enable Terminal (or iTerm, ...), then restart the terminal and run this again.
  2. Use the iCloud copy instead: in the game do Options > iCloud > Upload, quit, run this command
     with --icloud, then start the game and do Options > iCloud > Download.
  3. Copy the SaveData folder out with Finder (Cmd+Shift+G, paste the path above) and pass its path."""


def resolve(path, icloud):
    if path and icloud:
        sys.exit("give either a PATH or --icloud, not both")
    if path:
        return os.path.expanduser(path)
    if icloud:
        if not os.path.exists(ICLOUD):
            sys.exit(f"no iCloud save found at {ICLOUD}\n"
                     "In the game use Options > iCloud > Upload first, and make sure iCloud Drive is on.")
        return ICLOUD
    return LOCAL


def permission_help(path):
    return FDA_HELP.format(path=path)


def game_running():
    try:
        return subprocess.run(["pgrep", "-f", GAME_PROCESS], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


def backup(path, root=None):
    """Copy a save folder or file to a timestamped backup folder; returns the backup folder."""
    root = root or BACKUP_ROOT
    dest = base = os.path.join(root, time.strftime("%Y-%m-%d %H.%M.%S"))
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = f"{base} ({n})"
    os.makedirs(dest)
    target = os.path.join(dest, os.path.basename(path.rstrip("/")))
    if os.path.isdir(path):
        shutil.copytree(path, target)
    else:
        shutil.copy2(path, target)
    with open(os.path.join(dest, "origin.json"), "w") as f:
        json.dump({"source": path}, f)
    return dest


def list_backups(root=None):
    root = root or BACKUP_ROOT
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root) if os.path.exists(os.path.join(root, d, "origin.json")))


def restore(name=None, root=None):
    root = root or BACKUP_ROOT
    backups = list_backups(root)
    if not backups:
        sys.exit(f"no backups in {root}")
    name = name or backups[-1]
    folder = name if os.path.isabs(name) else os.path.join(root, name)
    with open(os.path.join(folder, "origin.json")) as f:
        source = json.load(f)["source"]
    saved = os.path.join(folder, os.path.basename(source.rstrip("/")))
    if os.path.isdir(saved):
        for fn in os.listdir(saved):
            shutil.copy2(os.path.join(saved, fn), os.path.join(source, fn))
    else:
        shutil.copy2(saved, source)
    return folder, source
