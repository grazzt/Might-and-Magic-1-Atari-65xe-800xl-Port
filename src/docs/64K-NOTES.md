# Notes towards a 64 KB Atari build

The port targets the 130XE (owner's decision, 2026-10-10). A build for 64 KB machines (65XE, 800XL) may be wanted later. This file collects, as they come up, the design choices that cost memory and the observations that could save it, so that the option is not closed by accident. Add a dated line whenever one turns up; do not act on them unless asked.

## Where the 130XE design spends memory a 64 KB machine does not have

| Date | Item | Cost | What a 64 KB build would do instead |
| --- | --- | --- | --- |
| 2026-10-10 | Display buffer in an extended bank, copied from the game's two C64-format bitmaps | About 9 KB of extended memory, plus copy time | Show the game's own bitmaps directly: lay their rows out three to a 1 KB block (see [ATARI-DESIGN.md](ATARI-DESIGN.md), "Rejected for now") and replace the drawing routines' row arithmetic with a row table |
| 2026-10-10 | Colour tables for the screen copy (16 tables of 256 bytes) and the per-row colour choice | 4 KB and 0.6 KB of extended memory; extended bank 0 is now full | Re-code the game's pictures and font once, on disk, so that no table is needed at run time. That needs the picture-set format, which is not decoded yet |
| 2026-10-10 | Atari support code and tables kept in an extended bank | 810 bytes | Fit them into the holes listed below |
| 2026-10-10 | Two bitmaps and page flipping kept from the C64 | 13 KB of main memory for bitmaps (5 KB upper, 8 KB lower) | Draw the view into one screen. The owner named this as the fallback for memory savings |
| 2026-10-11 | POKEY translation of the original nine SID effects | 366 bytes in existing main-memory kernel padding: LOADER 93, UNDER 241, TOP 32; no additional segment, boot sector or extended bank | Retain the same translator in a 64 KB build. It leaves only 8 bytes free in LOADER and 72 in UNDER; future support code may need another proven hole. Pitch tables use 84 bytes for 21 known pitches rather than a general divider ([checked](SOUND.md)) |

## Memory the game leaves unused (measured on the oracle, ten sessions)

Never changed and never loaded, so candidates for Atari code on a 64 KB machine. Not proof: only what ten sessions exercised.

| Range | Bytes | Note |
| --- | --- | --- |
| `$9D26–$9FFF` | 730 | The C64 disk loader. Its two entry points stay; the rest is free |
| `$D800–$DFFF` | 2,048 | RAM on the Atari with the OS switched out (I/O and colour RAM on the C64). The game does write colours to `$D800–$DBE7`; the 130XE build's screen copy reads them. Anything put at `$DC00–$DDFF` needs the game's CIA accesses redirected first, as the 130XE build does (log entry 18) |
| `$CFC0–$CFFF` | 64 | After the lower colour matrix |
| `$FF4A–$FFF9` | 176 | After the lower bitmap |
| `$03AE–$03FF` | 82 | Partly used by game variables; check before use |

## Code and data that need not be carried

| Date | Item | Bytes | Evidence |
| --- | --- | --- | --- |
| 2026-10-10 | Twelve unreferenced routines | About 500, of which 190 in `EN` | [C64-CODE.md](C64-CODE.md), "Code that nothing reaches" |
| 2026-10-10 | The C64 colour matrices at `$0400–$07E7` and `$CC00–$CFE7` | 2,000 | The Atari display has no per-cell colours. The game also uses `$0400` as its text screen in menus, so only the play-time use is spare; needs reading |
| 2026-10-10 | The title program and start-up stub | 4,480 on disk; no resident cost | Replaced whole by the Atari start-up. Since 2026-10-12 the title program runs first; still no resident cost (below) |
| 2026-10-10 | Sound routines and effect data in the `$A000` block | Not measured | Sound is optional (SPEC) |

## Ideas not yet examined

- **2026-10-10: the first Atari kernel is small and sits entirely in main memory the game does not use:** about 620 bytes at `$9D00` (150 spare) and 360 at `$DC00`. Only the text display list and font (1 KB) are in the extended bank. So far the 130XE's extra memory is needed for the display alone.
- **2026-10-10: the boot loads a 42 KB image of the C64's memory at the game's entry**, mostly title-program leftovers, so that the two machines can be compared byte for byte. It costs no memory in play and can be cut down to what the game needs once that is known.

- **2026-10-10: the display experiment already uses the layout a 64 KB build needs.** `port/atari/display_demo.py` shows a picture laid out three rows to a 1 KB block, 9 KB for 25 rows. Showing the game's own bitmaps that way needs 6 KB for the upper one (16 rows) where the C64 has 5 KB, so its last row must live elsewhere or the overlays' ceiling at `$34FF` moves.

- **Overlays already share `$2000–$34FF` with the upper bitmap.** The game shows only the lower bitmap while an overlay is loaded. A single-screen design could keep that region for overlays alone.
- **The three picture sets (13 KB at `$4EA0–$81FF`) are the largest data in memory.** They are loaded per area. Whether all three are needed at once, or could be unpacked piece by piece, is not known.
- **2026-10-11: stable text and palette caches reuse display memory.** Text snapshots use the bitmap buffer's first 1 KB only while showing text. Nineteen exact 60-byte palette records use 1,140 of its 1,216 unused bytes; no extra bank, main game RAM or boot sector. Five duplicate address tables save 125 bytes, offsetting some new code. Net occupied kernel padding grows by 288 bytes (UNDER 11, EXT 81, EXT2 196), plus 19 boot-code bytes; spare LOADER 8, UNDER 61, EXT 50, EXT2 173. The sound probes need 25 of UNDER's spare bytes. A full bitmap cache would need another roughly 10 KB; the stock 130XE cannot select different extended banks for CPU and ANTIC simultaneously. Keep the snapshot/palette idea for 64 KB, but its screen must first be accommodated in main RAM. Checked in both emulators; [SPEED.md](SPEED.md).
- **`GO` and `RO` (8 KB) load over the picture sets** when the party is at an inn. That sharing is the game's own and must be kept.

- **2026-10-11 reverse-transition investigation:** the new `transition_check.py` is a host-side capture helper. No target code, data, RAM allocation or boot-sector change; rebuilt the existing playable ATR and provided a distinctly named copy. Windows failure remains unidentified ([checked evidence](../test-artifacts/reverse/README.md)).

- **2026-10-11 graphics deep dive:** no target-memory or boot-sector change; probes exist only in emulator RAM and reports run on the host. A proposed exact unchanged-row predicate can reuse the converted buffer rather than a 10 KB raw cache. Optional row qualification plus a per-call flag would need about 26 bytes; current display tail `$63D4–$63FF` has 44 contiguous free bytes. Code fit and runtime gain remain unimplemented/unmeasured. A lookup-page patch guard would add five code bytes and no cache RAM. [Read layout / checked predicate / estimates](GRAPHICS-PERFORMANCE.md).

- **2026-10-11 graphics implementation, checked:** all three paths fit the
  existing segments/bank. Row qualifications plus exact-hit state occupy 26
  display-padding bytes at `$63D4–$63ED`, leaving 50 spare (18 contiguous).
  Moving 32 palette-scratch bytes from EXT2 to UNDER frees code space; UNDER
  explicitly reserves the existing 25-byte probe trampoline. Occupied segment
  sizes grow by UNDER 57, EXT 20 and EXT2 147 bytes (the UNDER growth includes
  the previously implicit probe reserve). Spare LOADER 8, UNDER 4, EXT 30,
  EXT2 26. No extra boot sector or raw bitmap cache. The row shortcut remains
  suitable for a future 64 KB conversion buffer, subject to the same exact
  palette-input and idempotence requirements; [measured result](GRAPHICS-PERFORMANCE.md).

- **2026-10-11 palette mapping reuse, checked:** three mutable key bytes in
  existing UNDER padding (`$DFFC–$DFFE`) plus 32 code bytes. Move the existing
  16-byte idempotence constant from EXT2 to EXT: net occupied growth UNDER 3,
  EXT 16, EXT2 16. Spare LOADER 8, UNDER 1, EXT 14, EXT2 10. Display padding,
  boot sectors and extended bank use unchanged. Key comparison requires no
  raw bitmap or additional per-row cache. This optimization can carry to a
  future 64 KB layout, but remaining code space now needs explicit planning;
  [exact conditions and measured gains](PALETTE-PERFORMANCE.md).

- **2026-10-11 held-key repeat, checked:** 39 extra keyboard instruction
  bytes use the game's existing counters, with no new repeat state. Share
  the 25-byte test trampoline with the loader's 128-byte buffer while idle;
  SIO replaces buffer contents before use. Move 16 matrix-scratch bytes
  to EXT and two row/cell bytes to UNDER. Net segment occupation: UNDER 0,
  EXT +14, LOADER/EXT2 0; spare 8 / 1 / 0 / 10. Display padding, banks and
  boot sectors unchanged. The scratch can accompany a future 64 KB palette
  region; no game RAM cache allocation. [Lifecycle and validation](KEYBOARD-REPEAT.md).

- **2026-10-11, checked:** disk batching needs no extra buffer or extended bank;
 sharing the DCB sector word and removing a redundant stack pair limit net
 LOADER growth to three bytes (five spare). Clearing 8,010 verified startup
 zero bytes saves 63 disk reads / 8,192 image bytes, not RAM. This is also
 applicable to a 64 KB build. Larger sectors would require a safe larger
 bounce buffer; none is allocated here. [Findings](DISK-PERFORMANCE.md).

- **2026-10-11, checked:** encounter colour correction uses no new bank or
  bitmap cache. Packing the exact symmetric distances saves 104 table bytes;
  less unrolling frees code, and sixteen idempotence constants move to TOP
  `$FFD3–$FFE2`. Matrix scratch returns to EXT2. Spare LOADER / UNDER / EXT /
  EXT2 is 5 / 1 / 0 / 3; TOP has one byte before GETIN and nineteen after it.
  Presence scanning reuses an existing mapping table and skips blank bytes.
  These techniques can carry to 64 KB; final output-buffer placement remains
  its separate design problem. [Timing/fit](COLOUR-SELECTION.md).

- **2026-10-12 title stage, checked:** no resident memory. The stage (2,021
  bytes at `$8000`), the parked boot code (`$A000-$BBFF`) and six rows of
  picture (`$1400-$1BFF`) use main memory that is free until the game is
  loaded, and are overwritten by it. Kernel segments unchanged, spare
  5 / 1 / 0 / 3; boot code +57 bytes; disk +8 blocks. On a 64 KB machine the
  title frames and the tune would work as they are: they need no extended
  memory. The scenes would not: they go through the kernel's screen copy into
  the extended bank. [TITLE.md](TITLE.md).
- **2026-10-12, an observation for showing the game's bitmaps in place:** the
  title frames are shown straight from the C64 bitmap at `$E000`. A row at
  `$E000 + 320 r` fits a 1 KB character-set block whenever `320 r mod 1024` is
  at most 704, which is 19 of the 25 rows; only rows 3, 6, 9, 12, 19 and 22
  need copying (1,920 bytes, two blocks). The same holds for the upper bitmap
  at `$2000`: 12 of its 16 rows. So "lay the bitmaps out three rows to a
  block and change the drawing routines" (first table above) has a cheaper
  variant: leave the bitmaps and the drawing code alone and copy ten rows,
  3.2 KB, into a 4 KB buffer. It still needs pixels that are right as drawn,
  that is pictures re-coded on disk for row colours, since nothing converts
  the 19 rows shown in place. *Checked* for the title's three-colour frames
  only.

- **2026-10-12: coverage/pause and walking follow-up.** The exact-target pause can miss its clock value during conversion; the existing PORTB selection provides the busy indication, requiring no additional flag byte. Six volatile envelope bytes use previously unused TOP bytes above GETIN, freeing UNDER space for the clock guard. Moving `rf_blank` beside them and deriving colour RAM high bytes remove an otherwise necessary table and make room for wider copy loops. No extra bank or game RAM; all are applicable ideas for a future 64 KB layout.

- **2026-10-13, four-disk build ([DISKS.md](DISKS.md)):** no resident memory beyond the one-image kernel's: the streaming unpacker fits in the same 768 bytes. Three ideas that bought the room, usable on a 64 KB machine: **the 128-byte sector buffer in the stack page** (the game's stack pointer is `$F0` or more at every disk call, so `$0100-$017F` is free during one); **variables in the padding of the loader's jump table** (four of its calls are a bare `rts`, two free bytes each); **the boot code's last step run from `$0180`** instead of from the kernel. A 64 KB build has no extended bank for display or staging, so its unpacker would also be free of both. The packed disks are 77% full at 130 KB; the compression is per item, so a smaller disk would need fewer items per disk, not a different format.

- **2026-10-13, 64 KB feasibility study, read/checked:**
  [64K-FEASIBILITY.md](64K-FEASIBILITY.md) audits the current 16 KB display bank
  and proposes a separate 65XE profile. Correction to the 2026-10-12 estimate:
  only **six crossing rows are visible at once**, so shared slots need **2 KB**,
  not 4 KB. A fixed-palette direct-display prototype could retain both original
  bitmaps; richer native single-screen rendering remains a second route.
  **EN saves 7,936 bytes of resident code/data from `$4000–$5EFF` into the
  lower bitmap; CM restores them**, so its padding cannot hold permanent
  support code. Removing the upper bitmap does not remove the overlay window.
  The host survey covers 21 scenarios with event equality against normal
  replay: **762 of 768 bytes at `$0800–$0AFF` are active party records**.
  A 256-byte nibble table exactly replaces the 4,096-byte mapping table in all
  4,096 checked cases, but needs a different conversion loop. Reusing colour
  matrices for the crossing buffers/font/snapshot requires redirecting their
  writers and blanking text during OS/SIO. No target code changed; no assembled
  64 KB layout or playable 65XE image exists yet.



**2026-10-13 — implemented / emulator-checked:** the direct-display prototype
now fits and plays at 64 KB, preserving both bitmaps and EN/CM's 7,936-byte
backup. All 21 scenarios / 257 native checkpoints pass; serial SIO saves and
cold reload pass in both emulators. Crossing rows/font/snapshot use two shared
1 KB blocks; 127 bytes of original presentation code/entries supply helper
space. Four-disk loader/display headroom is only 2/1 bytes. Fixed grayscale,
no title and no POKEY translator; walking measures 9 NTSC frames versus the
130XE converter's 29. [Full ledger, contracts and future budget](65XE.md).


**2026-10-13 — town-redraw/colour follow-up, emulator-checked:** mode publication
now precedes hidden-page clearing; in-place bitmap row copies retain DMA.
Reclaim unused stand-in VIC bytes rather than game tables for return code and
25 CHBASE bytes; the static operand inventory rejects conflicts. New mode entry
and shortened colour-copy footer add 29 borrowed bytes (resident segments now
2,124 total). Four-disk UNDER has 7 spare bytes; LOADER still 2. Movement is
12 frames with zero black frames, at the cost of brief shared-row tearing.
An optional warm palette costs no RAM; the entire kernel differs by exactly
two immediate operand bytes. Full original per-cell colour remains a different
renderer/asset problem. [Details](65XE.md).


**2026-10-13 — original intro restored, emulator-checked:** before loading the
game, the title stage uses `$8000` (~2.6 KB), original code `$4000–$4F7F`,
converted scenes `$5000–$73FF` and parked boot `$A000–$BBFF`. Crossing-row RAM
`$1400–$1BFF` becomes a 600-byte scene plan. A 256-byte nibble map and packed
plans avoid the full converter bank; music tables also live in temporary code.
ESC discards every temporary owner. Permanent kernel segments are byte-identical
to the no-intro build. Disk A uses 468 of 1,029 sectors. [Full validation](65XE.md).
