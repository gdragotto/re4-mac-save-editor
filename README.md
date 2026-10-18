# re4-mac-save-editor

Save editor for **Resident Evil 4 (2023 remake) on macOS** (Mac App Store build, `jp.co.capcom.RE4US`).
It can unlock the infinite-ammo bonuses and other bonus-shop items, complete challenges, set CP and pesetas, and refill ammo, either on every save or only on the ones you pick.

The Steam/PC version uses a different encryption ("Lime"), so this tool doesn't support it. For PC, use
[LimebrellaSharp](https://github.com/mi5hmash/LimebrellaSharp) or [ree-save-editor](https://github.com/kvasszn/ree-save-editor).
The iPhone/iPad build should use the same format, but I haven't tested it.

## What it can do

| Option | Save | Effect |
|---|---|---|
| `--infinite-ammo` | system | Unlocks **and marks as purchased** every Extra Content Shop weapon and accessory. That includes the **Cat Ears** (infinite ammo for every weapon except rocket launchers) and the bonus weapons. |
| `--cp N` | system | Sets your Extra Content Shop CP. |
| `--unlock CAT…` | system | Unlocks any of: `gamemodes weapons costumes accessories figures artwork photostyles cp11-weapons cp11-costumes cp11-accessories cp11-figures cp12-costumes cp12-figures all` |
| `--challenges SET…` | system | Marks challenges (Bonuses → Records) as completed: `main` (111), `separate-ways` (60), `all`. Their CP rewards aren't paid out, so use `--cp` for that. This may also unlock the matching Game Center achievements. |
| `--unlock-only` | system | Makes items buyable with CP instead of marking them purchased. |
| `--ptas N` | slots | Sets pesetas. |
| `--ammo N` | slots | Sets every ammo stack (attaché case and storage) to N rounds. Experimental: the game may clamp stacks above their normal size. |
| `--slot LIST` | slots | Picks which slots `--ptas`/`--ammo` touch: `all` (default), `autosave`, or e.g. `1,3`. |

Bonus unlocks and CP are stored in the **system save**, so every slot shares them. Pesetas and ammo belong to each slot.

## Install

Requires Python 3.9+.

```sh
git clone https://github.com/gdragotto/re4-mac-save-editor.git
cd re4-mac-save-editor
python3 -m pip install pycryptodome
```

You can then run it as `python3 -m re4save …`. Optionally, `python3 -m pip install .` installs a `re4save` command.

## Usage

**Quit the game first.** If the game is running, it overwrites your edit the next time it saves, so the tool refuses to edit until you quit.

```sh
python3 -m re4save info                                   # what's in your saves
python3 -m re4save edit --infinite-ammo --cp 999999       # Cat Ears, bonus weapons, CP
python3 -m re4save edit --ptas 2000000                    # pesetas in every slot
python3 -m re4save edit --slot 2 --ptas 2000000 --ammo 99 # only slot 2
python3 -m re4save edit --unlock all --challenges all     # everything in the bonus shop + all challenges
python3 -m re4save restore                                # undo: put the latest backup back
```

With no path, the tool works on **the save folder the game actually loads**:
`~/Library/Containers/jp.co.capcom.RE4US/Data/Library/Application Support/CAPCOM/jp.co.capcom.RE4US/SaveData`.
Edits go straight into that folder, so the next time you start the game you see them.

### Backups

Before every edit, the tool copies the saves it's about to change to `~/Documents/RE4 save backups/<date time>/`.
The backups are kept outside the game's folder and iCloud, so the game never sees them.

- `python3 -m re4save restore` puts the most recent backup back.
- `restore --list` shows all backups, and `restore "<name>"` restores a specific one.
- `--no-backup` skips the backup.
- `-o PATH` writes a modified copy somewhere else and leaves your saves alone.

### macOS permission (first run)

macOS protects other apps' data, so the first time you'll probably see *"macOS blocks your terminal from reading the
game's save folder"*. You have three options:

1. **Give your terminal Full Disk Access** (simplest, one time). Go to System Settings → Privacy & Security → Full Disk Access,
   enable Terminal (or iTerm, …), then restart the terminal.
2. **Use the iCloud copy instead.** No permission is needed:
   in the game choose *Options → iCloud → Upload*, quit, run the commands with `--icloud`, then start the game and choose
   *Options → iCloud → Download*. The iCloud copy is only as recent as your last Upload, so upload first.
3. **Work on a copy.** In Finder, press ⌘⇧G and paste the folder path above, then copy `SaveData` somewhere and pass that path to the tool.
   When you're done, copy the files back with Finder.

### What's in the folder

`data00-1.bin` is the system save (bonuses, CP, challenges). `data000.bin` is the autosave, and `data001Slot.bin`,
`data002Slot.bin`, … are the manual slots. The tool also accepts a single file or an iCloud-style `saveDataPackFile.bin` as PATH.

Equip the Cat Ears from the game's Extras menu (*Leon's Accessories*). `python3 -m re4save dump --save system|autosave|N`
prints every field of a save, if you want to explore further.

## How it works

The saves are RE Engine `DSSS` files, encrypted with **Blowfish** (CBC with a zero IV, little-endian blocks) and signed
with **murmur3**. The payload is RE Engine's self-describing binary serializer, so fields are found by the murmur3 hash
of their names. Edits patch values in place, so the file layout never changes, and the tool recomputes the signatures
(and the SHA-256 for pack files). Each save stays bound to the account that created it, because its user ID is left untouched.

The Blowfish key isn't stored in the game binary as a constant. It's loaded at runtime, and I read it from the running game's memory.
[docs/FORMAT.md](docs/FORMAT.md) has the full format.

## Disclaimer

Not affiliated with or endorsed by Capcom. This is for editing your own single-player saves. **Back up your saves first.**
A broken save is your responsibility. Online features and achievements aren't affected by anything this tool does, but use it at your own risk.

Thanks to mi5hmash ([AutostrongSharp](https://github.com/mi5hmash/AutostrongSharp)) and kvasszn
([ree-save-editor](https://github.com/kvasszn/ree-save-editor)) for documenting the RE Engine save formats.

## License

MIT
