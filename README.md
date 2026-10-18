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

**1. Quit the game, then copy your saves out.** macOS blocks Terminal from reading other apps' data, but Finder is allowed:

1. In Finder, press **⌘⇧G** and paste
   `~/Library/Containers/jp.co.capcom.RE4US/Data/Library/Application Support/CAPCOM/jp.co.capcom.RE4US/SaveData`
2. Copy the whole `SaveData` folder to e.g. your Desktop. **Keep an untouched copy as your backup.**

The folder holds `data00-1.bin` (system save: bonuses and CP), `data000.bin` (autosave), and `data001Slot.bin`,
`data002Slot.bin`, … (manual slots). The tool also accepts a single file, or an iCloud-style `saveDataPackFile.bin`.

**2. Look at what's inside:**

```sh
python3 -m re4save info ~/Desktop/SaveData
```
```
[system]  data00-1.bin
  CP: 20,400
    weapons             0/10 unlocked,   0/10 purchased
    accessories         9/30 unlocked,   0/30 purchased
    ...
[slot1]  data001Slot.bin: playtime 25.4 h, pesetas 154,990, saves 55, ammo stacks 5 (118 rounds)
```

**3. Edit.** The output keeps the same format as the input, and the input is never modified unless you pass `--in-place`:

```sh
# infinite ammo bonuses + lots of CP
python3 -m re4save edit ~/Desktop/SaveData -o ~/Desktop/SaveData-modded --infinite-ammo --cp 999999

# pesetas and full ammo stacks, only for slot 2
python3 -m re4save edit ~/Desktop/SaveData -o ~/Desktop/SaveData-modded --slot 2 --ptas 2000000 --ammo 99

# unlock everything in the bonus shop and complete every challenge
python3 -m re4save edit ~/Desktop/SaveData -o ~/Desktop/SaveData-modded --unlock all --challenges all
```

**4. Copy the modded files back** into the game's `SaveData` folder with Finder, replacing the originals, then start the game.
Equip the Cat Ears from the game's accessories menu.

> **iCloud:** don't use *Options → iCloud → Download* afterwards, because it replaces your local saves with the cloud copy.
> Use *Upload* once you're happy, if you want the modded save on your other devices.

`python3 -m re4save dump <path> --save system|autosave|N` prints every field of a save, if you want to explore further.

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
