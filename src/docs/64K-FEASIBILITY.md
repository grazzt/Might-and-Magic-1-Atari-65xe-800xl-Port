# A 65XE build: feasibility and implementation route

Historical investigation, 2026-10-13. The implementation and native checks
that followed are in [65XE.md](65XE.md). The estimates and unimplemented
status below describe the investigation stage.

2026-10-13, investigated on `main` at `c1d0058`, with the existing working-tree
changes left in place. This is a design study, not a working 64 KB release.
No game binary, Atari kernel, boot code, disk layout or emulator harness was
changed. The new helper is host-only: `tools/atari64_survey.py`.

**Assessment:** a 64 KB build is plausible. The best first experiment is a
small direct display of the existing bitmaps, retaining the game's page
flipping and combat backup, with a deliberately simpler palette. A richer
single-screen renderer is a second route. Neither has an assembled, verified
memory layout yet. Merely changing the machine setting or shrinking the ATR
cannot make the present build work.

The recommendation is to keep the 130XE release and add a separate 64 KB
build profile. Preserve game rules, random numbers, event order, character
data and saves. Treat renderer changes as presentation changes with explicit
entry contracts and their own validation. The standing project policy allows
only hardware operand redirections in game files; the renderer changes below
would extend that policy for the 64 KB variant. This study does not silently
make that implementation decision.

## 1. What actually needs the extra memory

*Read:* current `build.py`, `src/boot.s`, `src/kernel.s`, and generated linker
configuration. The game still runs at its C64 addresses; there is no heap or
general extended-memory allocator to optimize. Only one of the four extended
16 KB banks is used for the running game.

| Extended bank 0 | Allocation | Bytes |
| --- | --- | ---: |
| `$4000–$63FF` | Converted bitmap, also the completed text snapshot | 9,216 |
| `$6400–$67FF` | Reordered Atari text font | 1,024 |
| `$6800–$6BFF` | EXT: display lists, character codes, address tables, converter | 1,024 |
| `$6C00–$7BFF` | Sixteen byte-conversion lookup tables | 4,096 |
| `$7C00–$7FFF` | EXT2: colour selector, conversion helpers, scratch and constants | 1,024 |
| **Total allocated** | | **16,384** |

The 1,140-byte palette cache and 26 bytes of row-reuse state are **inside**
the 9,216-byte screen allocation's padding. They are not additional RAM.
The text snapshot also overlaps that allocation. Do not add these costs twice.

Main-memory kernel allocations are already occupied: 768 bytes at `$9D00`,
1,024 at `$DC00`, and 176 at `$FF50`, or 1,968 bytes allocated. The original
loader region and RAM under the OS are not unclaimed reserves anymore.

The stock 65XE has 64 KB installed. Disabling BASIC and the OS exposes their
underlying RAM, but `$D000–$D7FF` stays hardware: 63,488 bytes of the CPU
address space can hold ordinary RAM data. The port already banks the OS out
during play, so doing that again buys no new space. These mapping details are
documented in the [cc65 Atari hardware definitions](https://github.com/cc65/cc65/blob/master/include/atari.h)
and Atari's [65XE owner's manual](https://www.rigpix.com/vcomp/atari_65xe_manual.pdf).

## 2. Findings that rule out easy but unsafe savings

### The lower bitmap is also a combat backup

*Read and checked:* `EN`, immediately before loading combat, calls the text
display and copies `$4000–$5EFF` to `$E000–$FEFF`. The copy starts at EN
`$2456/$2458`. That is **7,936 bytes of resident code and data**, not a saved
picture. CM's `$26C9` routine copies it back on the way out, including after
defeat. The separate copies of `$2B00/$2C00` to `$5D00/$5E00` are also part of
this transition and must remain correct.

The targeted oracle probe captured the bytes before EN's copy and compared
them with `$E000–$FEFF` at CM's restore entry: all 7,936 matched. This explains
the failed lower-bitmap clobber tests in `REALHARDWARE.md`. Permanent code,
fonts or tables put in the middle of that range would be overwritten during
combat. A native framebuffer there is fine only if it yields to the backup
in text mode. Its apparent character-block padding is also overwritten.

### Removing the upper bitmap does not free a permanent 5 KB hole

*Read:* the upper view uses `$2000–$33FF`, 5,120 bytes. Its allocation also
serves as the overlay window `$2000–$34FF`, 5,376 bytes: CM fills it, and EN,
ST, shops and their picture loads use parts of it. A single-screen design
removes bitmap writes there, but the overlay window is still required.

It can hold optional graphics data while no overlay is using it. It cannot
hold an always-resident display routine without a load/lifetime scheme.
Similarly, the three 4,384-byte wall sets overlap GO, RO and C3 at different
times; their 13,152 bytes cannot just be repurposed as permanent storage.

### Low RAM is not empty

*Traced:* across 21 gameplay scenarios, **762 of the 768 bytes at
`$0800–$0AFF` were read or written after the startup stub**. GO's instruction
at `$795D` copies roster records into this region through a self-modified
indirect store. Bitmap text, resident combat and CM read the characters
through pointers. This is six party-record slots, with 127 accessed bytes
per 128-byte slot in these scenarios. A search for literal `$0800` operands
would have missed the use.

The new survey separates CPU accesses from hooked disk loads, counts actual
instruction and operand fetches, and excludes the title before game entry.
It covers 21 scenarios, including cold restart. Every comparable event
matches an independent, uninstrumented replay. The resulting unused ranges
are **leads, not a free-memory map**. In particular, `$95FE–$9CFF` (1,794
bytes) and `$ABD2–$B1C2` (1,521 bytes) hold resident data that other items,
spells or areas may need. Initial resident loads occur before the survey is
enabled; its “no load” field means no subsequent recorded load.

`$0200–$0333` also belongs to the Atari OS during SIO, regardless of what the
C64 oracle accesses. The 82-byte `$03AE–$03FF` candidate needs a whole-game
writer check and protection from startup initialization before allocation.

### “About 500 bytes of unused code” is not 500 permanent bytes

*Read:* that historical total includes title, stub and overlay routines.
Some unreferenced entries fall through into used code. For example, the
three-byte prefix at `$3D2B` does not make the following used routine free.
Combat backup/restore also overwrites some resident ranges. Reclaim only
proved private instruction bytes, and account for all later reloads.

## 3. A smaller direct-display route

ANTIC mode 4 can interpret the game's eight-byte C64 bitmap cells directly
as characters. Its character set base is aligned to 1 KB; a row must fit
within that block. Atari describes character graphics in
[De Re Atari, chapter 3](https://www.atariarchives.org/dere/chapt03.php);
the register alignment is also in the
[Atari hardware manual](https://www.atarimania.com/documents/atari-400-800-hardware-manual.pdf).

*Checked arithmetic:* each row is 320 bytes. At either `$2000` or `$E000`,
only rows **3, 6, 9, 12, 19 and 22** cross a 1 KB boundary. Their boundary
positions are 8, 16, 24, 32, 8 and 16 cells into the row. The title stage
already demonstrates displaying the other nineteen rows directly.

The old notes added four crossing rows of the upper bitmap to six of the
lower one. But a visible screen uses **one source per logical row**:

| Logical rows | Mode 1 | Mode 2 |
| --- | --- | --- |
| 0–15 | Lower bitmap | Upper bitmap |
| 16–24 | Lower bitmap | Lower bitmap |

There are six crossing rows visible in either mode, not ten. The same six
copy slots serve both modes. **1,920 pixel bytes fit in two 1 KB blocks**,
three rows per block, leaving 128 bytes of padding. No 4 KB copy area is
necessary unless both sources are deliberately cached at once.

The obstacle is colour, not pixel layout. The current kernel converts each
cell's three C64 colours into the chosen Atari row palette. If nineteen rows
are displayed directly, that conversion cannot take place in a separate
buffer. Recolouring only the six copied rows would produce inconsistent
output. Offline recolouring must also account for wall pieces drawn at
multiple positions, glyphs, packed creatures, chests and area-dependent
colour choices; it is not a mechanical rewrite of one picture file.

### Recommended first prototype: retain geometry, use fixed pixel roles

Use a fixed four-colour palette for raw pixel pairs, initially three shades
on black. Preserve all source bitmap bytes and the game's page flipping.
This avoids both the 9 KB converted screen and the 4 KB lookup tables without
needing the picture-set format decoded first. It preserves the source bitmap
bytes, while losing original per-cell hues and initially the separate blue
command-panel colour. Some cells assign black to a nonzero pixel pair; a fixed
palette could reveal previously invisible pixels there. Readability and
contrast need actual captures, not an assumption that all shapes stay exact.

A candidate layout uses `$CC00–$CFFF` and `$D800–$DBFF` for the two crossing
blocks in graphics mode. In text mode those same 2 KB hold the font and the
completed snapshot. This is a **proposal with conditions**, not presently
free memory:

1. Replace or redirect **every** original colour-matrix/colour-RAM writer that
   can hit these blocks, including indirect writes in resident code and EN.
   Prove that omitted colour metadata is presentation-only. Retain `$0400`
   as the game's text screen. Keep the snapshot during preparation that
   overwrites it with upper-bitmap colours.
2. Blank DMA before changing ownership; populate all six copy slots or the
   complete font/snapshot, then publish the display mode. Regenerate the
   reordered text font when returning to text, since graphics overwrites it.
   A short OS-font bounce routine outside ROM can do this without disk reads;
   its buffer and stack lifetime need a fit check.
3. **Blank text as well as graphics during SIO.** With the OS enabled, ANTIC
   would see ROM instead of RAM at these proposed font/snapshot addresses.
   The 130XE's extended-bank text display does not have that problem.
4. Put additional resident code in reclaimed kernel/private presentation
   bytes, never in EN's combat backup or the overlay window.

For fixed colours the display codes can be one 128-byte sequence `0..127`;
each display-list LMS points at the appropriate start within it. Copy-slot
rows use starts 0, 40 or 80. Native rows use their source offset divided by
eight. This avoids a separate 1,000-byte character-code matrix. A separate
panel colour makes sharing less simple and belongs in a later budget.

**Provisional additional resident budget:** 112 bytes for the text/graphics
lists, 128 for character codes, and roughly 200–350 for copying, source
selection, mode publication, font handling and state: **440–590 bytes**.
This estimate must be assembled. Removing four per-row colour arrays frees
100 existing UNDER bytes; simplifying their DLI/VBI loads and removing
converter-only state provides more. Replacing private C64 colour writers
can provide code space. If necessary, the optional POKEY effect translator
previously added about 366 bytes across existing main-memory padding and
could be omitted in the first prototype while preserving the original SID
sequencer and key rules. These savings overlap existing allocations; they
are not new RAM blocks, and there is no established headroom yet.

This route gives the first useful answer to “will the complete game work on
a 65XE?” while leaving the hardest rendering algorithms unchanged. It also
retains the proven combat backup format and overlay addresses.

## 4. A richer single-screen route

If the first prototype's palette is unacceptable, replace the original
presentation routines with a native renderer and one screen. This is the
owner's previously recorded fallback. It offers better long-term speed and
control of colour, but changes more contracts and needs stronger checks.

One possible native layout has three rows per character block at
`$E000–$FFFF` for rows 0–23 and a ninth block at `$D800` for row 24.
Pixel rows use `$E000–$FFBF` in the eight blocks and `$D800–$D93F` in the
ninth, with 64-byte gaps between each group of three rows. `$CC00` can hold
the permanent text font after its colour-matrix writers are removed.

Important consequences:

- The old fake VIC/SID/CIA registers at `$FF50` overlap row 23 and must move,
  for example into the 704-byte tail `$D940–$DBFF`. GETIN at `$FFE4` and the
  vectors at `$FFFA` are outside the pixel area. Only use padding that survives
  every applicable lifetime: the eight `$E000` block tails **do not survive
  EN's backup**. `$FF00` and above are outside that particular 31-page copy.
- Reserve `$2000–$34FF` for overlays even though it no longer holds a view.
  Keep `$E000–$FEFF` available for the **unchanged combat backup** in text
  mode, and prevent renderer activity from damaging it. After restoration,
  the framebuffer can be redrawn. Do not change the backup to copy a native
  picture instead of the original resident bytes.
- `view_page` cannot simply have both bases mapped to the same framebuffer.
  The original sequence draws, flips, then clears the hidden view; with
  aliased pages that last clear would erase the new picture. Move clearing
  to the start of a redraw, neutralize the post-flip clear, and audit callers.
- Recode picture/font pixel roles at build time or translate during drawing.
  Merely changing row addresses does not solve the per-cell colour problem.
  A native renderer can use area palettes and per-row registers, but metadata
  and all simultaneous picture combinations need a separate exact budget.
- Reading text live at `$0400` is possible only if new graphics routines no
  longer overwrite it before changing mode. Otherwise retain a snapshot with
  a proved lifetime. The present transition regression is a real constraint.

The starting routine inventory is:

| Entry/site | Contract to replace or audit |
| --- | --- |
| `$0C98` | Bitmap row/column to address, including forced lower-page rows |
| `$0D1C`, `$0D42`, dual-page wrappers | Glyph/string drawing, cursor advances, inline strings |
| `$1111` | Wall drawing, mirroring, source strides and colour writes |
| `$1F36` | Hidden-page view clear and every caller |
| `$0DFD`, `$1C2A`, `$1BF1` | View copy, text transition, flip/publication |
| `$C38E` (store `$C3CD`), `$C276`, `$1C18` | Cell colours, play colours, colour-RAM fill |
| `$C2C0`, `$C31F` | Packed-picture row layout and stream consumption |
| EN `$2456`, CM `$26C9` | Preserve resident combat backup, not graphics |
| Kernel GETIN, VBI, DLI | Publish completed frames, direct-input paths, interrupt integrity |

Fit replacement routines into their old private presentation space where
possible. Larger helpers need measured placement outside overlays/backup.
This design removes the extra display bank but does not yet prove where
every replacement instruction and palette byte fits. A successful link with
all lifetime assertions is the next proof, not “5 KB saved by single buffering.”

## 5. Useful optimizations that are not a complete solution

**Reduce lookup tables from 4,096 to 256 bytes.** For each of sixteen mappings,
store the output for sixteen possible input nibbles. Convert a byte by mapping
its high and low nibble and combining them. The host helper exhaustively
checked all **4,096 mapping/input-byte combinations** against the four-pixel
definition. A 512-byte pair of tables can avoid the final four shifts.
This is exact, with a speed/code-size tradeoff. It helps a native renderer
or a reduced converter, but leaves the screen placement problem unsolved.

**Keep streaming disk decompression.** The four-disk kernel already reads a
ZX02 stream through a 128-byte stack-page buffer. The historical 3.7 KB
compressed-item staging problem is resolved; do not revive it. The four-disk
boot's `$4000` staging for upper-memory loads is temporary main RAM, not an
extended bank. Keep new resident code outside it, and keep the roster raw and
byte-exact. Disk compression reduces sectors read, not the expanded wall-set
or overlay sizes in RAM. `DISKS.md`'s old 64 KB footnote should not be read as
evidence that the current decoder needs a new large staging allocation.

**Stream wall sets only if later budgets require it.** Three sets occupy
13,152 bytes, but the drawing routine chooses among them repeatedly. Keeping
one set could nominally release 8,768 bytes while adding loads or decoded-piece
caches, new pointer contracts and possible rotation delays on a 1050. First
trace distinct pieces/set accesses for every area. This is a more invasive
fallback than fixing presentation and may worsen walking substantially.

**Do not rely on an extra cartridge, hidden `$D000` RAM or another bank.**
Those change the stock-65XE target. Hardware-timed CHBASE changes within a
scanline might avoid crossing-row copies, but six rows need correct switching
on all eight scanlines, alongside keyboard/sound/IRQ and PAL/NTSC timings.
That is an experimental raster implementation, not a dependable budget item.

## 6. Implementation order and acceptance gates

1. **Add an isolated 64 KB build profile and allocation assertions.** Keep the
   normal 130XE build reproducible. Specify occupied ranges per phase: boot,
   title, text/SIO, exploration, encounter, combat, treasure, service and death.
   Reject overlaps, not just total sizes. Make patch lists assert original
   bytes, and include direct and computed colour writers.
2. **Build the minimal direct-display experiment.** First a frozen screen on
   real 64 KB emulator settings, then menu → inn → town → two page flips.
   Prove the two crossing blocks and text font/snapshot can change ownership
   without corrupting the source, kernel or transitions. Inspect the palette
   before committing to it. This is the earliest practical go/no-go gate.
3. **Exercise backup and overlays early.** Encounter → combat → victory/defeat,
   then chest and return to town; all services; sign-in/save/cold restart.
   Confirm the resident bytes survive backup/restore. Add guards around new
   support bytes, and inspect intermediate frames, not only settled ones.
4. **Retain deterministic gameplay evidence.** Run all current scenarios.
   Compare logical state, RNG, text events, loader contracts and exact save
   bytes. For modified code or relocated graphics, use explicit expected
   patch images and normalized presentation comparisons. Do not exclude broad
   RAM ranges to hide discrepancies; compare new kernel/code regions against
   the build separately. Extend coverage to all 55 areas and distinct wall
   sets before declaring whole-game compatibility.
5. **Check actual 64 KB configurations.** Atari800's shared harness defaults
   to an 800XL/64 KB; this game's `lockstep.Game` explicitly overrides it with
   `-xe`. Altirra's wrapper hardcodes `130xe` and `128K`. Parameterize both,
   assert configured RAM size, and test without extended-memory selection.
   Run standard serial SIO, disk swapping, writes, cold restart, BASIC off,
   NTSC and PAL, then Atari's XL ROM and a real 65XE/1050. A 130XE with the
   extended bank merely unused is not sufficient compatibility evidence.
6. **Improve presentation only within the proved budget.** Add a panel colour,
   area palettes, artwork recoding or a native single screen as needed. Measure
   frame time, redraw cost and disk latency after each change. Replace the
   current clock guard based on PORTB bit 4 with explicit presentation-busy
   state if banking calls disappear; equality-based pauses must not miss ticks.

The direct route should eliminate most of the present conversion work, but
there is no measured speed result for it. Six copied rows are less work than
a converted screen; original view drawing, DMA, interrupts and publication
still cost time. The current measured movement baseline is 29 NTSC frames,
not a prediction for the new build. Title frames can reuse their existing
direct-display technique with temporary pre-game RAM; title scenes need the
new palette/display treatment. The title has no permanent resident cost.

## Evidence and reproduction

```sh
python3 tools/atari64_survey.py --verify
python3 tools/atari64_survey.py --targeted
```

Full generated output: `build/atari/64k-survey/`, including the combined
65,536-byte access map. Retained reports and scope:
[`test-artifacts/64k/README.md`](../test-artifacts/64k/README.md).
These are host measurements and arithmetic checks. **No playable 65XE ATR,
native 64 KB rendering result, PAL result or real-hardware result is claimed.**
