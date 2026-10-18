# RE4 (2023) macOS save format

## Files

Saves live in the app sandbox:

```
~/Library/Containers/jp.co.capcom.RE4US/Data/Library/Application Support/CAPCOM/jp.co.capcom.RE4US/
  SaveData/data00-1.bin       system save (options, bonus shop, CP, records)
  SaveData/data000.bin        autosave
  SaveData/data00NSlot.bin    manual slot N
  SaveDataBackup/             the game's own backup copies
```

iCloud transfers bundle the same files into `saveDataPackFile.bin`:

| Offset | Content |
|---|---|
| 0x00 | `PACK`, version bytes, u64 user id |
| 0x10 | 6 × { i32 slot index (-1 = system), 4 bytes padding, u64 size } |
| 0x70 | the DSSS files, back to back |
| end-32 | SHA-256 of everything before it |

## DSSS container

| Offset | Content |
|---|---|
| 0x00 | `DSSS`, u32 version = 2, u32 flags = 3 (Blowfish \| has-id), u32 Blowfish option = 3 |
| 0x10 | Blowfish-ECB(`DSSSDSSS`) |
| 0x18 | Blowfish-ECB(8-byte user id) |
| 0x20 | Blowfish-CBC, IV = 0, over the payload (whole 8-byte blocks only, any remainder stays plain) |
| end-4 | murmur3_32(file[:-4], seed 0xFFFFFFFF) |

- Blowfish is standard (pi-initialised, big-endian key schedule), but each 8-byte block is read as two **little-endian** u32 halves.
- Key (53 bytes): `wa9Ui_tFKa_6E_D5gVChjM69xMKDX8QxEykYKhzb4cRNLknpCZUra`

### Finding the key

The binary isn't FairPlay-encrypted and is built without the hardened runtime. The DSSS reader (near the `DSSSDSSS`
literal) calls a Blowfish context. The context's key comes from a resource held by the save manager singleton
(`+0x7e8`: u32 length at `+0x1c`, key bytes at `+0x20`), not from a constant. A small library loaded with
`DYLD_INSERT_LIBRARIES` read that resource from memory after start-up, and the key checks out because it decrypts
`DSSSDSSS` and reproduces existing saves byte for byte.

## Payload

RE Engine `via.storage.saveService` serializer. It's the same as on PC once decrypted, except that alignment is
relative to the start of the file (the payload begins at 0x20, which matters for odd struct sizes such as 0x30).

```
payload := { u32 root_hash ; Class }*
Class   := u32 field_count ; u32 class_hash ; Field*
Field   := u32 murmur3(name) ; i32 type ; Value ; align 4
```

Types follow `via.reflection.TypeKind` (1 enum, 2 bool, 7 s32, 8 u32, 0xa u64, 0xf string, 0x10 struct, 0x11 class),
plus -1 for arrays. Every `*SaveData` class has a `HashValue` field. It is a per-type schema hash that is identical
across saves, **not** an integrity check.

### Fields used

| Field | Hash | Where |
|---|---|---|
| `_ExPoint` (CP) | b1bf9eba | system › chainsaw.GameRecordManager.SaveData |
| `_BonusID` / `_IsUnlock` / `_IsBuy` | fe3bc2b9 / 9a447dad / 550cd0c2 | system › chainsaw.ExShopData |
| `PTAS` | 70c6acd7 | slot › chainsaw.InventoryManager.GameSaveData |
| `_ItemId` / `_CurrentItemCount` | 3a833cec / f6ad4887 | slot › chainsaw.Item |
| `_CurrentAmmo` (ammo item id of a weapon) | murmur3("_CurrentAmmo") | slot › chainsaw.WeaponItem |

`chainsaw.ExShopBonusID` ranges: game modes 0–4, weapons 6–15, costumes 17–36, accessories 38–67, figures 69–268,
artwork 270–330, photo styles 332–356, then CP11 (358–421) and CP12 (424–430) DLC entries.
