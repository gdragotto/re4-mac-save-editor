"""Known fields and the edits the CLI offers. Fields are located by name hash, not by offset."""
from .serializer import Obj, Value, h

# Field name hashes. Some names are not recoverable from the game, those were identified
# from their position in the class and their values.
EX_POINT = h("_ExPoint")              # CP in the Extra Content Shop (system save)
BONUS_ID = h("_BonusID")              # chainsaw.ExShopData
IS_UNLOCK = 0x9A447DAD                # chainsaw.ExShopData._IsUnlock
IS_BUY = 0x550CD0C2                   # chainsaw.ExShopData._IsBuy
RECORD_ID = 0x835F7CE2                # chainsaw.GameRecordData._RecordID (challenges)
RECORD_COUNT = 0x688FBADB             # chainsaw.GameRecordData._Count
PTAS = h("PTAS")                      # pesetas (slot saves)
CURRENT_AMMO = h("_CurrentAmmo")      # chainsaw.WeaponItem: item id of the ammo it uses
ITEM_ID = 0x3A833CEC                  # chainsaw.Item._ItemId
ITEM_COUNT = 0xF6AD4887               # chainsaw.Item._CurrentItemCount
ELAPSED = h("_GameElapsedTime")       # microseconds
SAVE_COUNT = 0x45157494               # chainsaw.CampaignManager.GameData._SaveCount

NAMES = {v: k for k, v in {
    "_ExPoint": EX_POINT, "_BonusID": BONUS_ID, "_IsUnlock": IS_UNLOCK, "_IsBuy": IS_BUY,
    "_RecordID": RECORD_ID, "_Count": RECORD_COUNT,
    "PTAS": PTAS, "_CurrentAmmo": CURRENT_AMMO, "_ItemId": ITEM_ID, "_CurrentItemCount": ITEM_COUNT,
    "_GameElapsedTime": ELAPSED, "_SaveCount": SAVE_COUNT, "VersionValue": h("VersionValue"),
}.items()}

# chainsaw.ExShopBonusID ranges (the "...End" sentinels in between are skipped)
BONUS_CATEGORIES = {
    "gamemodes": range(0, 5),
    "weapons": range(6, 16),
    "costumes": range(17, 37),
    "accessories": range(38, 68),       # includes the Cat Ears (infinite ammo)
    "figures": range(69, 269),
    "artwork": range(270, 331),
    "photostyles": range(332, 357),
    "cp11-weapons": range(358, 362),
    "cp11-costumes": range(363, 369),
    "cp11-accessories": range(370, 391),
    "cp11-figures": range(392, 422),
    "cp12-costumes": range(424, 425),
    "cp12-figures": range(426, 431),
}
# Challenge record ids: main game 0-110, Separate Ways 200-259
CHALLENGE_SETS = {"main": range(0, 200), "separate-ways": range(200, 300)}
MAX_MONEY = 9_999_999
MAX_AMMO = 999


def _scalar(obj, field):
    v = obj.get(field)
    return v if isinstance(v, Value) else None


def find(objects, field):
    """All scalar Values named `field`, with their owning object."""
    return [(o, o.fields[field]) for o in objects if isinstance(o.fields.get(field), Value)]


def ex_shop(objects):
    """{bonus_id: Obj} for every Extra Content Shop entry."""
    return {o.fields[BONUS_ID].value: o for o in objects
            if isinstance(o.fields.get(BONUS_ID), Value) and IS_UNLOCK in o.fields and IS_BUY in o.fields}


def challenges(objects):
    """{record_id: Obj} for every challenge (chainsaw.GameRecordData). _IsUnlock shares the shop field's hash."""
    return {o.fields[RECORD_ID].value: o for o in objects
            if isinstance(o.fields.get(RECORD_ID), Value) and IS_UNLOCK in o.fields and RECORD_COUNT in o.fields}


def category_of(bonus_id):
    for name, r in BONUS_CATEGORIES.items():
        if bonus_id in r:
            return name
    return None


def ammo_stacks(objects):
    ammo_ids = {v.value for _, v in find(objects, CURRENT_AMMO) if v.value > 0}
    return [(o, o.fields[ITEM_COUNT]) for o in objects
            if _scalar(o, ITEM_ID) and _scalar(o, ITEM_COUNT) and CURRENT_AMMO not in o.fields
            and o.fields[ITEM_ID].value in ammo_ids]


# ---- summaries -------------------------------------------------------------------------

def summarize_system(objects):
    lines = []
    cp = find(objects, EX_POINT)
    if cp:
        lines.append(f"CP: {cp[0][1].value:,}")
    shop = ex_shop(objects)
    for cat in BONUS_CATEGORIES:
        entries = [o for bid, o in shop.items() if category_of(bid) == cat]
        if entries:
            u = sum(o.fields[IS_UNLOCK].value for o in entries)
            b = sum(o.fields[IS_BUY].value for o in entries)
            lines.append(f"  {cat:<17} {u:>3}/{len(entries)} unlocked, {b:>3}/{len(entries)} purchased")
    recs = challenges(objects)
    for name, r in CHALLENGE_SETS.items():
        sel = [o for rid, o in recs.items() if rid in r]
        if sel:
            done = sum(o.fields[IS_UNLOCK].value for o in sel)
            lines.append(f"challenges {name}: {done}/{len(sel)} completed")
    return lines


def summarize_slot(objects):
    out = []
    t = find(objects, ELAPSED)
    if t:
        out.append(f"playtime {t[0][1].value / 3.6e9:.1f} h")
    p = find(objects, PTAS)
    if p:
        out.append(f"pesetas {p[0][1].value:,}")
    sc = find(objects, SAVE_COUNT)
    if sc:
        out.append(f"saves {sc[0][1].value}")
    stacks = ammo_stacks(objects)
    if stacks:
        out.append(f"ammo stacks {len(stacks)} ({sum(v.value for _, v in stacks)} rounds)")
    return ", ".join(out)


# ---- edits (return a list of human readable changes) ---------------------------------------

def set_cp(buf, objects, value):
    hits = find(objects, EX_POINT)
    if not hits:
        raise ValueError("CP field not found (is this the system save?)")
    old = hits[0][1].value
    for _, v in hits:
        v.set(buf, value)
    return [f"CP {old:,} -> {value:,}"]


def unlock(buf, objects, categories, purchase=True):
    shop = ex_shop(objects)
    if not shop:
        raise ValueError("Extra Content Shop data not found (is this the system save?)")
    changes = []
    for cat in categories:
        n = 0
        for bid, o in shop.items():
            if category_of(bid) != cat:
                continue
            flags = [IS_UNLOCK, IS_BUY] if purchase else [IS_UNLOCK]
            for f in flags:
                if not o.fields[f].value:
                    o.fields[f].set(buf, True)
                    n += 1
        changes.append(f"{cat}: {'unlocked + purchased' if purchase else 'unlocked'} ({n} flags changed)")
    return changes


def complete_challenges(buf, objects, sets):
    recs = challenges(objects)
    if not recs:
        raise ValueError("challenge records not found (is this the system save?)")
    changes = []
    for name in sets:
        n = 0
        for rid, o in recs.items():
            if rid in CHALLENGE_SETS[name] and not o.fields[IS_UNLOCK].value:
                o.fields[IS_UNLOCK].set(buf, True)
                n += 1
        changes.append(f"challenges {name}: {n} marked completed")
    return changes


def set_ptas(buf, objects, value):
    hits = find(objects, PTAS)
    if not hits:
        raise ValueError("pesetas field not found")
    old = hits[0][1].value
    for _, v in hits:
        v.set(buf, value)
    return [f"pesetas {old:,} -> {value:,}"]


def set_ammo(buf, objects, count):
    stacks = ammo_stacks(objects)
    for _, v in stacks:
        v.set(buf, count)
    return [f"{len(stacks)} ammo stacks set to {count}"]
