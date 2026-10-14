# C64 Phase 0 findings

Measured on 2026-10-09 and 2026-10-10. Source choice is C64; the initial baseline is the archive-labelled **Original_v2** G64 set. This is a starting map, not a completed reverse engineering specification. The disk loader, logical block layout and file tables are worked out in [C64-LOADER.md](C64-LOADER.md); the screen, keys, random numbers, area files, fights and saving are in [C64-RUNTIME.md](C64-RUNTIME.md). Which bytes are code, the rebuilt listings and everything that touches C64 hardware are in [C64-CODE.md](C64-CODE.md). How each of these was found, in order, is in [PORTING-LOG.md](PORTING-LOG.md).

## Reference media

The retained disk ZIPs contain two original G64 sets (`Original_v1`, `Original_v2`) and two D64 sets (`None`, `FAC`), each with four sides. The manual ZIP includes the manual, C64 instructions, map, spell tables and town example. All extracted files match their retained archive members; [image provenance](../c64/images/SOURCES.json) and [manual provenance](../c64/manuals/SOURCES.json) record URLs and hashes.

The archive's warning describes side-C recognition failures in many cracked copies. Its original-v2 notes recommend PAL, true drive emulation, and disabled virtual device traps. The baseline follows those settings. The A→B, B→C and C→D exchanges all work here: B→C by the archive's own route out of Sorpigal, C→D, which is shown by the `direct-if`, `direct-eh` and `direct-dp` sessions (position fixtures put the party at a castle entrance; the game asks for disk D and loads from it). The first attempt, `trace-side-d`, walks to the portal square but meets a wandering group there and never goes through (corrected 2026-10-13).

`tools/analyze_c64.py` asks VICE c1541 to decode each of the 683 standard sectors on each original-v2 side, then uses our D64 reader for directory chains. Every extracted directory PRG also matches c1541's independent file extraction. The complete results are in [c64-disk-layout.json](c64-disk-layout.json).

| Side | COPYRIGHT 1987 | ACTIVISION INC. | Standard sectors differing from None / FAC |
| --- | --- | --- | --- |
| A | 59-byte PRG → `$02CB–$0303` | 1,538-byte PRG → `$2000–$25FF` | 0 / 238 |
| B | same bootstrap | same bootstrap | 0 / 51 |
| C | same bootstrap | 811-byte PRG → `$8000–$8328` | 0 / 15 |
| D | same bootstrap | same bootstrap | 0 / 6 |

PRG lengths include the two-byte load header; ranges describe payload bytes. The bootstrap is track 18/sector 6. Side A's loader chain is 18/2, 18/12, 18/3, 18/13, 18/4, 18/14, 18/5; side C's second file uses its first four sectors. Disk labels read `   MIGHT & MAGIC`, with ID bytes `30 30` (`00`) and DOS type `2A`.

**All standard decoded sectors match the `None` D64 set byte-for-byte.** This does not establish equivalence of physical tracks, protection, or drive timing. The generated D64s discard those features and are for analysis. Keep the G64s as the execution reference. `tools/g64.py` decodes the G64 tracks without c1541 and agrees on all 2,732 sectors. Directory files cover only a small fraction of the disk; the rest is the loader's [logical block array](C64-LOADER.md).

## Executed boot path

1. VICE loads `COPYRIGHT 1987` at `$02CB`. Its 57-byte payload blanks the screen, sets KERNAL logical file 2/device 8/secondary address 1, loads `ACTIVISION INC.`, and jumps to `$2000`. The bootstrap also overwrites BASIC's warm-start vector at `$0302`.
2. The second PRG jumps to `$21AF`. Its code runs a disk check in the drive, copies three pages from `$2300–$25FF` to `$9D00–$9FFF`, starts the drive half of the fastloader from track 18, loads logical block 0 to `$4000` and jumps there.
3. Native 6502 title code at `$4000` displays the animated title. The smoke check stops at its keyboard polling routine `$41AB` and supplies `$5F`, the C64 left-arrow character, through the KERNAL buffer.
4. The game displays `INSERT DISK B / AND PRESS 'RETURN'`. After attaching side B and supplying Return, it loads the options menu offering character creation, character viewing, and town selection.
5. Town 1 opens the Inn of Sorpigal with six supplied characters. Leaving the inn loads the town; walking out of the gate asks for side C and loads the outdoors. [Screens and the load trace](../test-artifacts/c64/trace-outdoors) record this.
6. A second recorded run takes the stairs under Sorpigal, wins an arena fight against six snakes for 300 experience each, returns and signs in at the inn, which writes the roster. [Screens, text and loads](../test-artifacts/c64/trace-fight-save).
7. Three more recorded runs use Sorpigal's five services, view a character and cast a spell; walk to side D; and create and save a new character. They are under `test-artifacts/c64/trace-town-services`, `trace-side-d` and `trace-new-character`.

[Title screenshot](../test-artifacts/c64/baseline/title.png) · [disk prompt](../test-artifacts/c64/baseline/insert-b.png) · [options menu](../test-artifacts/c64/baseline/menu.png) · [monitor evidence](../test-artifacts/c64/baseline/monitor.txt)

This establishes native machine-code execution for the inspected boot/title/menu path. It does not yet classify every overlay or rule out embedded interpreters elsewhere.

## Initial memory and hardware inventory

| Location | Evidence / current interpretation |
| --- | --- |
| `$0001 = $36` | Observed at title and menu: banking must be accounted for when capturing or porting RAM |
| `$02CB–$0303` | File bootstrap, including warm-start vector |
| `$00C6`, `$0277…` | KERNAL buffered-key count/data used for scripted input |
| `$0400–$07E7` | 40×25 menu screen matrix, verified by text assertions |
| `$0E37…$0E54` | Menu-stage input wait; calls `$A087`, whose jump target is `$C648` and which calls KERNAL GETIN (`$FFE4`) |
| `$2000–$25FF` | Side-A second-stage loader at initial load; later contents must not be assumed resident |
| `$4000…` | Title code entry; title-stage input polling at `$41AB` |
| `$9D00–$9FFF` | Fastloader: parameters at `$9D00–$9D06`, eight-entry jump table at `$9D07`; uses `$FC–$FF` |
| `$4700–$48FF` | File table of the inserted side; `$48FF` is the side number |
| `$16–$1A`, `$1271`, `$1293` | Random generator and its per-key reseed; fights change with key timing as this predicts |
| `$028E` | KERNAL CTRL flag, tested by the inn for CTRL-letter keys |
| `$3C`, `$3D`, `$40` | Party row, square (y × 16 + x) and facing mask |
| `$0D42`, `$0D1C`, `$C9E8` | Bitmap string and character printers and their font |
| `$2000`, `$E000` | Upper (multicolour) and lower bitmaps of the play screen, split by a raster interrupt |
| `$A000…` | Menu-stage jump table reaching routines in `$Axxx–$Cxxx`; precise code/data boundaries pending |
| `$CC00` | Title screen attribute matrix reported by VICE |
| `$D800–$DBE7` | C64 colour RAM; additional title colour information cannot simply be treated as ordinary RAM |
| `$E000` | Title bitmap base reported by VICE; title uses **multicolor bitmap**, not a simple monochrome mode-F equivalent |
| `$D011`, `$D016`, `$D018`, `$D020/$D021` | VIC-II mode, layout and colour state; bootstrap/title touch these directly |
| `$DD00` | CIA2 port participates in VIC-bank/serial configuration; measured `$90` at title and `$93` at menu |
| `$FFBA`, `$FFBD`, `$FFD5`, `$FFE4` | KERNAL file setup, filename, load and keyboard calls in the inspected path |

The menu input wait increments `$2D` and updates `$2E` while polling. Each accepted key then copies `$2E` into the random generator's state (`$1271`, `$1293`). The effect is confirmed: the same keys after different delays produce different fights, and keys delivered on the wait loop's first pass reproduce the same fight every time. The smoke check still uses fixed instruction counts; the trace scripts use first-pass delivery.

There is also drive-side machine code: a disk check uploaded with `M-W`, and the fastloader's drive half on track 18. Both are disassembled, labelled and rebuilt byte for byte; the sector order, the XOR key and the file tables are described in [C64-LOADER.md](C64-LOADER.md). A host disk trap can now replace the eight loader entries.

## First reassembly and verification

[source/c64/boot.s](../source/c64/boot.s) labels the first bootstrap, its filename and warm-start vector. `tools/rebuild_boot.py` assembles/links it and compares all 59 PRG bytes with the original-v2 extraction. SHA256: `3219afdee68cc19437dd9b547c9a156079793635e01d643402b791297601d564`.

Validation completed:

- All 31 archived/extracted reference files match recorded sizes and SHA256 hashes; extracted files match ZIP members.
- Four D64-reader tests exercise geometry, final-sector byte counts, cycles, and recorded disk errors.
- All four original-v2 standard sector views decoded; all eight PRG extractions agree with c1541.
- Bootstrap rebuild matches every byte.
- A fresh-copy VICE run reaches the options menu; text is asserted directly from captured screen RAM.
- `tools/rebuild_loader.py` regenerates all 1,538 bytes of `ACTIVISION INC.`, the 96-byte disk check and the 1,280 bytes of drive code from labelled da65 info files.
- The logical-disk decoding reproduces every traced read in five sessions (127 reads on all four sides), and both traced writes put the expected bytes in the expected blocks and change nothing else.
- All five trace scripts replay to identical results, including the fight's text and the saved roster.
- A search of all four sides finds no caller of the disk loader beyond those the sessions exercised, apart from one read in the title program.
- Ghidra 12.1.4 imports the bootstrap's 57-byte payload at `$02CB` using `6502:LE:16:default`, decodes its initial `SEI`, and runs the native decompiler. This installation check leaves the final jump to the unloaded `$2000` stage unresolved; it is not a complete decompilation of the loader. See [Ghidra commands and scope](GHIDRA.md).

## Next work

Phase 0's exit condition is met: the disk layout is mapped for all four sides, every path by which the game reaches the disk is known, and the load address of every resident block, overlay and area file is recorded. What those blocks contain is Phase 1: extract and label the resident code (`$0B00–$1FFE`, `$3500–$4E9F`, `$8C00–$9CEE`, `$A000–$CBFF`), the overlays and the 55 area files with byte-identical rebuilds, and inventory their hardware accesses; that is the size where Ghidra starts to pay off. Small leftovers are listed at the end of [C64-LOADER.md](C64-LOADER.md) and [C64-RUNTIME.md](C64-RUNTIME.md). An Apple comparison, the host oracle and Atari execution are not started.

**Update, 2026-10-10:** that extraction is done. All 76 code files rebuild exactly and the machine inventory is written; see [C64-CODE.md](C64-CODE.md). The table above is the Phase 0 view and is kept as measured then; the code map supersedes it where they overlap.
