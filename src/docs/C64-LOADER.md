# C64 disk loader and logical disk

Measured on 2026-10-09 from the **Original_v2** set. Everything here is either reassembled byte for byte from labelled sources or checked against VICE; the last section lists what is still open. What the running game does with the data is in [C64-RUNTIME.md](C64-RUNTIME.md).

The game does not use the DOS directory after its two boot files. Each side is a flat array of 256-byte blocks read and written by a custom loader. Sides B–D carry the game's own file table. **For the Atari port, the whole 1541 mechanism reduces to five calls on a parameter block**, served from four decoded 170 KB images.

## Reproduce

```bash
python3 tools/analyze_c64.py      # sector views (needed first)
python3 tools/rebuild_loader.py   # labelled loader sources -> identical bytes
python3 tools/mmdisk.py           # logical images, named files, docs/c64-logical-disk.json
python3 tools/area.py --world     # area graph -> docs/c64-areas.json
for t in outdoors fight-and-save town-services side-d new-character; do
  python3 tools/c64_trace.py tools/traces/boot-to-$t.txt     # writes build/trace/boot-to-$t/
done
```

The committed results of those five scripts are under `test-artifacts/c64/trace-*`. The order in which all of this was worked out, and the mistakes on the way, are in [PORTING-LOG.md](PORTING-LOG.md) (entries 5, 7 and 8).

## Boot sequence

1. `COPYRIGHT 1987` (`$02CB`, [boot.s](../source/c64/boot.s)) loads `ACTIVISION INC.` with the KERNAL and jumps to `$2000`.
2. `$2000–$22FF` ([loader-stage2.info](../source/c64/loader-stage2.info)) shows `ONE MOMENT PLEASE` and `VERSION 2.0`, runs the disk check below, copies its last three pages to `$9D00–$9FFF` and calls the fastloader's init.
3. Init sends two DOS commands: open `#0` (drive buffer 0, `$0300`) and `B-E,2,0,18,7`, which loads track 18 sector 7 into that buffer and runs it. That code reads sectors 8–11 into `$0400–$07FF`, unscrambles them and takes over the serial bus ([drive.info](../source/c64/drive.info)). The same five sectors are on all four sides.
4. Stage 2 reads the header ID (`00` on every side), hands it back to the DOS, loads block 0 to `$4000` (`$0F80` bytes) and jumps there.

The version string agrees with the archive's `Original_v2` label.

## Calls the game makes

The game fills `$9D00–$9D06` and calls a jump table. A returns the status, with Z set when it is 0.

| Entry | Drive command | Action |
| --- | --- | --- |
| `$9D07` | – | Start the drive code (step 3 above) |
| `$9D0A` | – | Set the VIC bank bits in A; the loader keeps them in every later write to `$DD00` |
| `$9D0D` | 0 | Read `length` bytes to `address` |
| `$9D10` | 1 | Write `length` bytes from `address` |
| `$9D13` | 2 | Set the disk ID the DOS expects (X, Y) |
| `$9D16` | 3 | Get the disk ID from a sector header (X, Y) |
| `$9D19` | 4 | Protected read (see below); no caller found |
| `$9D1C` | 5 | Reset the drive; no caller found |

| Parameter | Meaning |
| --- | --- |
| `$9D00/01` | C64 address |
| `$9D02/03` | Length in bytes |
| `$9D04` | Offset of the first byte in the first block |
| `$9D05/06` | Logical block number |

Status bits: 1 wrong disk ID, 2 write protected, 4 no disk, 8 read/write failed after ten tries, `$10` checksum mismatch, `$FF` drive did not answer. The loader also uses `$FC–$FF` as pointer and counter.

The wire protocol is one data bit on each edge of a clock driven by the C64, with an 8-bit sum per transfer. It matters only for running the original in an emulator; the Atari port and the host oracle can replace the eight entries directly.

## Logical blocks

A side has **664 blocks**: tracks 1–35 without track 18, in track order. Within a track the sectors are visited in a fixed order that depends on the track's sector count, and every byte is XORed with a key derived from track and sector. All 256 bytes of a sector are data; there are no link bytes. [mmdisk.py](../tools/mmdisk.py) implements the mapping, and its tests step through the drive's own arithmetic for the key.

Check: in the five recorded sessions, each of the 127 reads, on all four sides, was compared with RAM at the next capture. 101 match on every byte still in place. The other 26 cover memory the running program had changed by then: 21 differ by 1 to 65 bytes, and the first `$5000` title load (once per session) by 1,000 of its 1,300 surviving bytes. Captured immediately after that read instead, all 5,214 bytes match.

**Writes are checked too.** After each of the two traced writes (a save at the inn and a new character), the disk copy VICE wrote was decoded with our own G64 reader: the 2,304 bytes at the written blocks equal what the game had in RAM, 18 and 38 of them differ from the original disk, and no other block changed.

## File table (sides B, C, D)

The last two blocks (`$296–$297`) are loaded to `$4700` whenever a side is checked or a file is wanted (game code at `$C445` and `$C4BF`).

| Offset | Contents |
| --- | --- |
| `$000` | Two-character names, 48 slots |
| `$060` | Start block per slot |
| `$0C0` | Length per slot |
| `$120` | Default load address per slot |
| `$180` | Monster picture index: one start block per picture, each running to the next entry |
| `$1FF` | Side number: 1 = B, 2 = C, 3 = D |

The disk-swap prompt compares `$48FF` with the side it wants and repeats `INSERT DISK x` until they agree. The header ID plays no part: it is `00` on all sides.

Sides B, C and D list 36, 37 and 39 files; the complete tables with hashes are in [c64-logical-disk.json](c64-logical-disk.json). Files seen in use so far:

| File | Side | Loads to | Seen as |
| --- | --- | --- | --- |
| `RO` | B | `$6000`, `$0900` bytes | Read at the options menu and at an inn; written back when the party signs in. 18 × 128 bytes, so presumably the roster |
| `GO` | B | `$6900`, `$169A` | Options menu and inn code; contains the only call to the write entry |
| `EG` | B | `$8200`, `$09FF` | Area file for Sorpigal |
| `RK` | C | `$8200`, `$06E7` | Area file outside Sorpigal |
| `NB`, `LL`, `KF` | B, C | `$4EA0`, `$5FC0`, `$70E0` | Three `$1120`-byte picture sets per area; the caller overrides the default address |
| `EN` | B–D | `$2000`, `$09B6` | Start of an encounter; reads the monster record and picture itself |
| `CM`, `C3` | B–D | `$2000`, `$4EA0` | Combat |
| `RK` | B | `$8200`, `$0787` | Area file for the dungeon under Sorpigal (the name is reused per side) |
| `91`, `92`, `93`, `95`, `96` | B | `$2000` | Sorpigal's blacksmith, temple, food shop, training hall and tavern, one file each |
| `EJ`, `EP` | C | `$8200` | Outdoor sectors south of Sorpigal's |
| `BC` | D | `$8200`, `$04CB` | Area behind the portal in sector `EP` |

`ST`, `EN`, `CM` and `C3` sit at the same blocks on B, C and D. Side A has no table: its boot and title code use fixed block numbers.

Fifty-five of the named files are areas, loading at `$8200`. Their exits and neighbours are listed in [c64-areas.json](c64-areas.json); every one of the 82 exits names an area file that exists on the side it names.

Not seen loading: `ST` (its text is about opening treasure; a search after two won fights found none), `94` (the statues' verse), and `1C`, `7N`, `8A`–`8D`, `8P` and side D's `BB`, which hold no text. Those eight are packed pictures in the format `draw_picture` at `$C2C0` unpacks ([C64-CODE.md](C64-CODE.md)).

## Monster data (sides B, C, D)

Two things are read by block number rather than by name, both by the encounter file `EN`:

- **Pictures** occupy blocks `$000–$0FA`, 76 or 77 of them, one to five blocks each, located through the index at offset `$180` of the file table.
- **Records** occupy blocks `$165–$17D`: 195 monsters of 32 bytes, eight to a block, identical on all three sides.

With these, 40, 44 and 14 non-blank blocks remain unexplained on B, C and D. They sit in the gaps between files and after the last one; what they hold has not been examined.

## Load map

From [trace-outdoors/trace.json](../test-artifacts/c64/trace-outdoors/trace.json): boot, swap to B, take the six supplied characters out of the inn, walk to Sorpigal's gate, swap to C.

| Stage | Side | Block | Address range | Caller |
| --- | --- | --- | --- | --- |
| Title | A | `$000` | `$4000–$4F7F` | `$2225` |
| | A | `$190`, `$195` | `$C9E8–$CBFF`, `$C92C–$C9E7` | `$425F`, `$4285` |
| | A | `$160` | `$8C00–$9CEE` | `$42AB` |
| | A | `$070`, `$088` | `$5000–$645D`, `$5000–$5F49` | `$48D8` |
| After Escape | A | `$017` | `$0B00–$1FFE` | `$4303` |
| | A | `$03F` | `$A000–$C92B` | `$4327` |
| | A | `$1A0` | `$2000–$21FF` | `$434D` |
| | A | `$140`, `$184` | `$3500–$4BED`, `$4A00–$4E9F` | `$2023`, `$2049` |
| Side B in | B | `$296` | `$4700–$48FF` (file table) | `$C4DC` |
| | B | `RO`, `GO` | `$6000–$68FF`, `$6900–$7F99` | `$215F`, `$2185` |
| Leave inn | B | `EG`, `KF`, `LL`, `NB` | `$8200–$8BFE`, `$70E0`, `$5FC0`, `$4EA0` | `$C499` |
| Side C in | C | `$296` | `$4700–$48FF` | `$C4DC` |
| | C | `RK`, `NB`, `KF`, `LL` | `$8200–$88E6`, `$70E0`, `$5FC0`, `$4EA0` | `$C499` |

The other recorded sessions add:

| Session | Loads beyond the above |
| --- | --- |
| [fight-save](../test-artifacts/c64/trace-fight-save/trace.json) | Stairs down (`RK` and three picture sets), an arena fight (`EN`, a monster block to `$2D00`, a picture to `$3000`, `CM`, `C3`), stairs up (`EG` and its sets), signing in (`RO`, `GO`, the file table, then the write of `RO`) |
| [town-services](../test-artifacts/c64/trace-town-services/trace.json) | `91`, `93`, `92`, `95`, `96` at `$2000`, one per service. Buying, viewing a character and casting a spell load nothing |
| [side-d](../test-artifacts/c64/trace-side-d/trace.json) | Sector `EJ` (area file only), sector `EP` (area file and the two picture sets that differ). **Correction 2026-10-13:** it does not go on to side D. A wandering group of dinolizards meets the party at 13,13, the portal square, and the recorded keys after that do nothing; no read from side D is in the session (on the C64's trace and on the oracle alike). Side D is read by `direct-if`, `direct-eh` and `direct-dp` ([GAMEPLAY-COVERAGE.md](GAMEPLAY-COVERAGE.md)), which put the party at the edge of the area by a position fixture |
| [new-character](../test-artifacts/c64/trace-new-character/trace.json) | Creating a character loads nothing; saving it re-reads the file table and writes `RO` |

Choosing a town and picking characters at the inn caused no disk access. **All three disk swaps (B, C and D) work in VICE with this set**, which settles the doubt the archive notes raised about the baseline.

## Every caller of the loader

A search of all four decoded sides for a `JSR` or `JMP` to any of the eight entries finds:

| Where | Calls |
| --- | --- |
| Title program (A `$000`) | Eight reads, one bank change |
| Start-up stub (A `$1A0`) | Four reads |
| Resident code (A `$03F`) | `$C499` read by name or with preset parameters, `$C4DC` read of the file table, `$C420` bank change |
| `EN` (B, C, D) | `$219E` and `$251C`, the two monster reads |
| `GO` (B) | `$7F6E`, the one write |

All of these appear in the recorded sessions; the title read at `$4B36` since 2026-10-12, in the title's scenes (below). Nothing else on sides B–D calls the loader, so **every disk access during play is a named file, the file table, a monster block or picture, or the roster write.** A computed call through a pointer would escape this search; none has been seen.

Side A also has matches in blocks no trace read (`$105`, `$109`, `$1C2`, `$1C3`). Their offsets line up with `EN` and the title program shifted by a few bytes, which suggests earlier builds left on the disk.

### The title's scenes (traced 2026-10-12)

`SPACE` at the title shows eight scenes, each a packed picture read to `$5000` from `$48D8`; four of them also read 1 KB of colours to `$0400` from `$4B36`. From [trace-title-scenes/trace.json](../test-artifacts/c64/trace-title-scenes/trace.json); the title program itself is described in [TITLE.md](TITLE.md).

| Scene | Picture block, length | Colour block |
| --- | --- | --- |
| 2 | `$09B`, `$0AF2` | `$0A8` (read twice) |
| 3 | `$0B2`, `$098E` | – |
| 4 | `$0BD`, `$1052` | `$1A5` |
| 5 | `$0D3`, `$0A9C` | – |
| 6 | `$1C4`, `$1016` | `$1AC` |
| 7 | `$1D7`, `$0FFA` | – |
| 8 | `$1B1`, `$0FCE` | `$122` |
| 9 | `$12C`, `$0AFA` | – |

After the last scene the two title pictures (`$070`, `$088`) are read again.

## Copy protection

- **Header-gap check (runs at boot).** Stage 2 uploads 96 bytes to the drive ([drive-check.info](../source/c64/drive-check.info)) that return the eighth byte after a sector header on track 1. It expects `$AF`. Our own G64 decoder finds that value in the header gaps of sides A and C; B and D have the standard `$55`. If the check fails, the loader replaces the `JMP` at `$9D10` with `BRK` before installing itself, so the game runs but the first save jumps through the BRK vector. In our VICE runs the check passes (`$9D10` holds `$4C`). A sector image cannot hold gap bytes, so the D64 sets presumably fail it; that is not tested.
- **Protected read (command 4, unused).** It reads all 17 sectors of track 35 at three head positions, half a track apart. Every failure moves the read pointer down a byte, so the data that follows is wrong unless all 51 reads succeed. It then XORs the low block byte with `$25` and reads normally. That is consistent with a widened track 35 on the retail disk. Tracks 36–42 of our G64s hold only filler, so this command would return shifted data here. No direct call to `$9D19` exists in the boot files or in any block of the four sides.

Neither mechanism is needed by the port, but the write entry must stay enabled.

## Open

- **Side A.** 154 non-blank blocks were never read. They look like earlier builds (see above) and side A is not in the drive after boot, so they are probably unused; that is not proven. (274 until 2026-10-12: the title's scenes account for 120.)
- **`ST` and the picture-only files** have not been seen loading. They are named files and would load through the same path.
- **`EN` contains unreferenced code that uses KERNAL file calls** (`OPEN`, `CHRIN` and others at `$28E9`). Nothing reaches it, so the statement that every disk access goes through the loader stands; see [C64-CODE.md](C64-CODE.md).
- **Side C's second directory file** (`$8000–$8328`) contains another copy of the C64 loader with its own interrupt setup. Nothing loaded it in the recorded sessions.
- **Original_v1** differs from v2 in 50, 40, 7 and 3 sectors on sides A–D and has the `$AF` gaps on A and B instead of A and C. Not analysed further.
