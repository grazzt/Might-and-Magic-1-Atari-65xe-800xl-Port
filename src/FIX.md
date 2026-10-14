# Fix the garbled Atari text screens

**Current status, 2026-10-11:** the historical CIA overwrite below was fixed
and verified in porting-log entry 18. A separate transient `2`-character bug
on text/graphics switches has now also been implemented and checked (entry
22). Read [docs/SPEED.md](docs/SPEED.md) for its cause, exact cache design,
measurements, tests, memory limits and remaining work. The earlier proposed
fix and live `$0400` display descriptions below are historical.

## Follow-up: right-window `2`s entering a character sheet (2026-10-11)

The owner still reports this in **Windows Atari800** using the previously
provided command. A fresh build did not reproduce it. The owner now confirms **no more `2`s**
after recopying the disk, and attributes the earlier report to the wrong copy.
This follow-up is closed without a newly demonstrated kernel fault.
No additional kernel or game code fix has been made in this follow-up.

**Checked:** a scratch run of the pre-existing generated ATR did not match the
current layout: the byte expected to be `frame_ready` increased every frame
instead of holding 0/1. A normal `build.py` rebuild removed that discrepancy.
The original ATR's hash was not preserved, so its exact version is unknown.
An older Windows disk copy is a hypothesis, not a confirmed cause.

**Checked:** `port/atari/transition_check.py` now rebuilds the playable kernel,
boots using ordinary POKEY keys, forms the six-character party and opens all
six character sheets directly from town. It varies starting delays and records
40 frames per character, including both bitmap modes. All six settle on the
text display list; immutable main-memory kernel bytes still match assembly.
The 240 frames were visually inspected: an old/partial town view, a blank
interval and correct character text; no right window of repeated `2`s.
This is Linux libatari800, 130XE, NTSC, Altirra OS. It does not identify the
Windows executable, ROM or configuration. [Captured evidence](test-artifacts/reverse/README.md).

**Read:** original `show_text` at `$1BC7` first calls `$1C2A`, which may copy
the upper view down and temporarily select bitmap mode 1; it then clears the
text matrix, fills colour RAM and sets text mode. The current Atari VBI uses
`shown_mode`, not the game's in-progress mode. `rf_text` disables DMA before
reusing the display buffer, then publishes the completed snapshot. No newly
identified missing reverse-transition path has been demonstrated.

**Reproduction / disk identification:** copy the freshly built disk and fully restart the Windows
emulator with that explicit filename. `build/atari/mm1-9d64689.atr` is an
identical, distinctly named copy of the normal playable `mm1.atr` (732944
bytes). Its SHA-256 is
`0039e59910fc729cecb11f7a12cd20ff76801acc353f4f0c8fc7f1f59e5ba17a`.
If the failure persists on that exact copy, obtain the full launch command,
Atari800 version, selected OS and precise keys leading to the failure. Replay
those conditions and capture the actual transient before changing the kernel.
Frame-end mode/DMA flags and correct settled pictures alone are insufficient.

The helper captures direct digit keys: the kernel currently strips SHIFT
from its normal keyboard translation, so an emulated `#` becomes `3` rather
than the scripted hook's `$23`. Do not mistake that different action for a
reproduction of the earlier first-poll benchmark. This keyboard limitation
was read in `keyboard`/`key_table`; it is not changed by this investigation.

**Graphics performance follow-up:** the owner next requests a deep drawing
analysis. Conversion takes 76.5% of measured walking time; cycle breakdowns,
controls and exact row-reuse conditions are in
[docs/GRAPHICS-PERFORMANCE.md](docs/GRAPHICS-PERFORMANCE.md). The owner then
authorized all three optimizations, now implemented: repeated lookup-page
guard, identity copy and exact qualified row reuse. Movement is 30 frames
instead of 34–35 in Atari800, with identical benchmark pixels/game bytes.

Investigation date: 2026-10-11. Repository HEAD during investigation: `1a7214f`
(following `ae5b53f`, the colour display and screenshot gallery commit).

This is an implementation handoff. The investigation changed no repository
source or original disk image. Only this document is being added. Emulator
experiments used copies of the existing Atari image in temporary directories.
The proposed fix has **not** been implemented or validated through a full run.

## Confirmed cause

**Unredirected C64 CIA register accesses corrupt the Atari kernel's own
instructions.** In particular, a C64 write to `$DD02` changes the instruction
that loads the high byte of the Atari text display-list address. The corrupted
handler selects `$0000` instead of `$6800`, so ANTIC interprets unrelated memory
as display instructions.

The game text, text screen memory, font, and intended display list were correct
in the inspected runs. The main fault is in the hardware adaptation layer.

## Screens and display modes

The side-by-side gallery is [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md), generated
by [port/atari/screenshots.py](port/atari/screenshots.py). Representative failures:

- `docs/screenshots/new-character-rolled-atari.png`: mostly blank, with rows of
  symbols instead of the character statistics and choices.
- `docs/screenshots/fight-and-save-fight-atari.png`: garbled symbols and repeated
  rows instead of combat text.
- `docs/screenshots/menu-menu-atari.png` and
  `docs/screenshots/town-services-character-atari.png`: similarly corrupt.

Oracle runs of the existing scripts showed these actual states at checkpoints:

| Checkpoint | `$0389` display mode | C64 VIC `$D011/$D016/$D018` | VIC bank |
| --- | --- | --- | --- |
| Options menu | 0 | `$1B / $C8 / $17` | 0 |
| Character creation: rolled and class | 0 | `$1B / $C8 / $17` | 0 |
| Inn roster | 0 | `$1B / $C8 / $17` | 0 |
| Character sheet | 0 | `$1B / $C8 / $17` | 0 |
| Combat: fight | 0 | `$1B / $C8 / $17` | 0 |
| Town view | 2 | `$3B / $D8 / $18` | 0 at the sampled instant |

The game's IRQ vector was `$C5C5` in these samples. The failing examples share
the Atari mode-0 text path. The older combat discussion in `docs/C64-RUNTIME.md`
guesses that combat uses a bitmap; the sampled `fight` checkpoint actually uses
text mode. Use observed state rather than that earlier inference.

## Exact corruption mechanism

Relevant files:

- [port/atari/build.py](port/atari/build.py): `patches()` currently redirects
  only the `VIC-II` and `SID` categories into `FAKE_VIC` and `FAKE_SID`.
- [port/atari/src/kernel.s](port/atari/src/kernel.s): the `UNDER` segment occupies
  `$DC00–$DFFF`; its vertical-blank handler selects the text display list.
- [tools/disassemble.py](tools/disassemble.py): `machine_uses()` already
  inventories CIA accesses separately from VIC-II and SID accesses.
- [docs/c64-code-map.json](docs/c64-code-map.json): existing CIA access inventory.

The C64 routine `set_vic_bank_bits`, at `$C40D`, includes:

1. Read the C64 CIA2 data-direction register at `$DD02` (`$C410`).
2. Set its bottom two bits for output.
3. Write it back to `$DD02` (`$C415`).

On the Atari these addresses are RAM under the disabled OS ROM. In the current
kernel layout, `$DD02` happens to hold opcode `$A9` (`LDA #immediate`) for:

```asm
@text:  lda #<text_list
        sta DLISTL
        lda #>text_list       ; currently opcode at $DD02, operand $68 at $DD03
        sta DLISTH
```

The original CIA operation changes `$A9` to `$AB` because `$A9 | $03 = $AB`.
That turns a valid load into an undocumented opcode. Do not depend on the
undocumented opcode's behaviour on another emulator or real hardware; the
instruction overwrite itself is the bug.

Expected versus observed bytes at `$DD02`:

```text
As assembled: A9 68 8D 03 D4    ; LDA #$68 / STA $D403
In game RAM:  AB 68 8D 03 D4    ; overwritten opcode
```

This exact mutation was observed at both `rolled` in
`boot-to-new-character.txt` and `fight` in `boot-to-fight-and-save.txt`.
Addresses describe the current build; linker changes can move the vulnerable
instruction. Redirecting the CIA accesses is necessary even if a later layout
places something else at `$DD02`.

Tracing the emulator's ANTIC writes during three subsequent frames showed:

```text
At vertical blank, scanline 248:
    write $D402 = $00
    write $D403 = $00       ; should be $68
    write $D409 = $64       ; intended text font base
    write $D40E = $40       ; vertical-blank NMI enabled

Next frame, starting scanline 8:
    fetch display-list instruction from $0000
    fetch from $0001, $0002, ... and later unrelated addresses
```

This explains the missing text and repeated rows: the display is executing
unrelated bytes as a display list. The colour differences in these failed
screens are also not evidence that the intended text palette needs redesign.

## Evidence that the intended text renderer works

At both inspected Atari checkpoints:

- `$0400–$07E7` matched the oracle's 1,000 screen bytes exactly.
- Extended-bank font `$6400–$67FF` matched the font constructed from the Atari
  OS ROM by the existing boot code.
- Character `$20` was a blank glyph; character `$41` was a recognisable `A`.
- ANTIC could fetch the correct display-list bytes from the extended bank at
  `$6800`.
- `shown_mode` was 0, `CHBASE=$64`, `CHACTL=$02`, `DMACTL=$22`, `PRIOR=$00`,
  `COLPF1=$0E`, `COLPF2=$00`, and `PORTB=$D2`.

The correct 32-byte text display list was:

```text
70 70 42 00 04
02 02 02 02 02 02 02 02 02 02 02 02
02 02 02 02 02 02 02 02 02 02 02 02
41 00 68
```

It has two blank-line instructions, an ANTIC mode-2 LMS pointing at `$0400`,
24 more mode-2 rows, then a jump-and-wait back to `$6800`.

In isolated emulator sessions, with the game already waiting for scripted
input, disabling NMIs and setting the display-list pointer manually produced
readable character creation and combat screens. No instruction repair or font
replacement was required for that experiment:

```python
lib.ANTIC_PutByte(0xD40E, 0x00)  # temporarily suspend the faulty NMI handler
lib.ANTIC_PutByte(0xD402, 0x00)
lib.ANTIC_PutByte(0xD403, 0x68)
game.frames(2)
```

This is a diagnostic isolation step, **not a gameplay fix**: disabling NMIs
also stops normal interrupt-driven work such as the clock and keyboard.

Temporary evidence available in the investigation environment:

- `/tmp/mm1-display-p1gmdcz4/rolled-before.png`
- `/tmp/mm1-display-p1gmdcz4/rolled-manual-dlist.png`
- `/tmp/mm1-display-yrh4wir_/fight-before.png`
- `/tmp/mm1-display-yrh4wir_/fight-manual-dlist.png`
- `/tmp/mm1-display-inspect.py`: diagnostic script using the existing build,
  copied disks, oracle checkpoints, and direct emulator register inspection.
- `/tmp/mm1-display-trace.c`, `/tmp/mm1-display-trace.so`,
  `/tmp/mm1-display-trace.log`, `/tmp/mm1-display-trace.out`: temporary
  instrumentation of emulator register writes and display-list fetches.

These temporary files may disappear. This document contains the essential
evidence and does not require them to implement the fix. A later experiment
relocating display-list data into main RAM produced a blank screen and was not
investigated further; it is not a validated alternative solution.

## Proposed implementation

### Redirect all remaining resident CIA accesses

Extend the operand-patching scheme in `build.py` to redirect the CIA registers
to safe, separate stand-in storage, just as VIC-II and SID accesses are already
redirected. The existing inventory identifies four resident instruction sites:

| Instruction address | Original operand | Access |
| --- | --- | --- |
| `$C410` | `$DD02` | Read CIA2 data-direction register |
| `$C415` | `$DD02` | Write CIA2 data-direction register |
| `$C418` | `$DD00` | Read CIA2 port A |
| `$C59D` | `$DC0D` | Write CIA1 interrupt-control register |

The inventory also contains title-program accesses. The Atari build does not
execute the C64 title program; retain the existing exclusion for module
`title`. Confirm the inventory against the current disassembly before editing.

Redirect `$DC0D` as well: it currently overlaps the kernel's saved OS zero-page
area. No separate disk failure from that write was established, but leaving it
unredirected still permits the game to overwrite Atari support data.

### Allocate and initialise stand-ins deliberately

The current `TOP` segment has free bytes at `$FFB0–$FFE3`, between `fake_sid`
and the `$FFE4` GETIN entry. One possible allocation is 16 bytes for each CIA,
using `$FFB0` for CIA1 and `$FFC0` for CIA2, with 20 free bytes remaining before
GETIN. Verify the assembled layout and adapt the `.res` padding accordingly.
These are proposed addresses, not existing labels.

Keep CIA1 and CIA2 distinct. The chip select is the difference between `$DCxx`
and `$DDxx`; each chip's register index is the low four bits. A single masked
mapping that aliases both chips to the same register array would be wrong.

Initialise the stand-in registers the game reads with values appropriate to
the C64 state at entry to the startup stub. `stub_entry()` currently returns
RAM and CPU registers only; inspect the oracle's CIA state and decide how to
carry the needed values into the build. Do not assume all-zero initial values
without checking the bank-selection routine and its effect on game state.

The port already supplies its own interrupts and bank-selection loader entry.
Full CIA emulation should not be necessary for these four accesses, but verify
that assumption with the existing oracle comparisons.

### Preserve the existing display design

Keep the game's screen at `$0400`, the mode-2 text list, and the reordered font
unless subsequent evidence identifies a separate defect. They were sufficient
to show both inspected screens correctly once ANTIC used the right list.

Moving the kernel away from `$DD02` alone would hide this particular collision
while leaving the original hardware writes active. Fix the accesses at their
source. Audit the other retained C64 hardware references for similar overlap.

## Why existing checks passed

`port/atari/lockstep.py` explicitly excludes `$D800–$DFFF` from the C64/Atari
memory comparison because that region includes Atari support code and C64
colour/CIA addresses. It also excludes the stand-in registers near the top of
memory. The game screen can therefore match the oracle while an instruction
inside the excluded Atari kernel has been overwritten.

The current tests exercise game state, disk saves, and keyboard behaviour.
They do not establish that the Atari renders the stored screen correctly.
Previous reports of 62 matching checkpoints are compatible with this bug.
The full test suite was not rerun during this investigation.

## Validation after implementing the fix

1. **Check the patch list and assembled layout.** Verify all four resident CIA
   instruction sites now address the intended stand-ins and the added storage
   does not overlap GETIN, interrupt vectors, or other kernel storage.
2. **Add a kernel instruction-integrity regression check.** Compare immutable
   code bytes in the Atari NMI/vertical-blank handler against the assembled
   image after boot and at text/graphics transitions. Avoid comparing the whole
   `UNDER` segment: it also contains legitimate mutable data. Find instruction
   locations from the current labels/layout rather than assuming `$DD02` is
   always an opcode.
3. **Run the existing Atari suite**, including all six lockstep scripts and
   the keyboard play check:

   ```bash
   python3 -m unittest tests.test_atari
   ```

   Both scripted saves should still match the oracle's disks. Investigate
   differences rather than adding exclusions to accommodate the fix.
4. **Regenerate and inspect the gallery**:

   ```bash
   python3 port/atari/screenshots.py
   ```

   Inspect all 20 pairs, especially menu, rolled statistics, class selection,
   inn roster, character sheet, combat, and returning to text after graphics.
   Readability, correct content, and row layout are the primary checks; Atari
   and C64 colours/fonts need not be pixel-identical.
5. **Check ordinary keyboard play and disk transfers.** The display should
   remain correct across text/graphics switches and the OS being temporarily
   switched in for SIO. Take any reproducible visual failures seriously even
   if the memory checks pass.
6. **Update relevant documentation** once validated: `docs/ATARI-DESIGN.md`,
   the screenshot gallery, and the porting log. The patch count and claims
   about harmless retained hardware accesses will change. Clarify the observed
   combat text mode in the older runtime notes if updating those notes.

Expected result: menus, character creation, combat, and character sheets show
their actual text, and the existing game-state/disk comparisons continue to
pass. The CIA redirection remains the proposed fix until those checks succeed.
