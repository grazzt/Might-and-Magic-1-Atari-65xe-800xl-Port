# C64 runtime notes

Measured on 2026-10-09 and 2026-10-10 from the **Original_v2** set in VICE. These are the parts of the running game the port and the host oracle will have to replace or reproduce. Each item says how it is known: *traced* (seen in a recorded run), *checked* (a prediction from it was tested), or *read* (from disassembly only). The disk side is in [C64-LOADER.md](C64-LOADER.md).

Seven runs are recorded under `test-artifacts/c64/`: `trace-outdoors`, `trace-fight-save`, `trace-town-services`, `trace-side-d`, `trace-new-character`, and since 2026-10-11 `trace-treasure-reload` and `trace-death`. Each `trace.json` holds, in order, the keys the game accepted, everything it printed and every disk command. All seven replay identically from their scripts in `tools/traces/`. [PORTING-LOG.md](PORTING-LOG.md) tells how each item below was found (entries 7 and 8) and gives the recipes.

## Keys and random numbers

- **Key wait (traced).** Game code asks for a key through `$0B18` → `$0E37`. That clears the KERNAL buffer, then loops at `$0E3B`: add 1 to `$2D`, poll `$A087` → `$C648` → KERNAL `GETIN`, and on no key add to `$2E` and repeat. An accepted key calls `$1271` before returning.
- **Generator (read).** `$0B15` → `$1293` takes a range in A and steps a 32-bit shift register in `$16–$19`. `$1271` swaps `$17` and `$18` and replaces `$19` with `$2E`.
- **Consequence (checked).** Dice depend on how many times the wait loop ran before each key. With keys sent after fixed delays, the same route to the arena gave six battle rats and a win when resumed from a snapshot, and a different group that wiped the party out when played from boot. With every key delivered on the first pass of `$0E3B`, repeated runs from boot give the same fight, the same damage text and the same saved roster.

The trace tool's `press` step does exactly that. **It is the key-timing model for the oracle:** a key is defined to arrive on the first poll. An Atari build fed the same way should then roll the same dice.

**Disk prompts in play (checked, 2026-10-10).** `INSERT DISK C` and `D` are asked through the same key wait, so its counters run for as long as the swap takes. A script therefore resets them after the wait: `ready`, `poke 002d 00 00`, `press 0d`. With that, the host oracle's memory equals VICE's after a swap; without it `$2D/$2E` and the random state differ from then on ([ORACLE.md](ORACLE.md)).

**Pauses (checked, 2026-10-11).** `$A036` → `$C355` waits A × 32 ticks of the KERNAL clock (`$A1/$A2`) or until a key, and has 31 callers. It empties the keyboard buffer first, does nothing at all for A = 0, and otherwise loops: ask the key reader `$C648` for a key (the call at `$C378`), return if there is one, else compare the clock with its target in `$C353/$C354`. The game switches the CIA timer interrupt off and chains the KERNAL's handler from its own raster interrupt, so that clock ticks once a frame, or twice in the split-screen mode.

- **A key during a pause ends it and is used up. It changes nothing else.** The key comes back in A. *Read:* none of the 33 calls and jumps to the routine is followed by a test of A; several go straight on into other routines, which were not followed. *Checked:* the arena fight with a key at every one of its 35 pauses gives the same text, the same disk traffic and the same saved roster as without, in VICE and on the oracle ([ORACLE.md](ORACLE.md), timing rule 3).
- **The key reader `$C648` (read; sound exceptions checked on Atari800, 2026-10-11).** After KERNAL `GETIN` returns a key: if a sound is playing (`$03A0`), the key stops it (`$C62F`), except that effect 9 plays on, effect 5 swallows key `$01`, and effect 6 stops only for RETURN. With the shift flag `$028D` = 1, keys `$21–$29` have `$10` added. The key is then compared with the last one returned, kept in `$0371`: a different key sets the KERNAL's repeat delay `$028C` to `$30` and becomes the new last key. All nine sound lists are now decoded and their 468 SID writes traced on the oracle and VICE: [SOUND.md](SOUND.md).

**Other key readers (read).** A search of the code finds 307 calls to the key wait. Outside it, `GETIN` is reached by the pause routine and by three area files on side D (`IF` at `$89F0`, `EH` at `$86D2`, `DP` at `$890E`); keys read there do not stir the random numbers.

Two places read keys differently. The title polls at `$41AB`, and the first `INSERT DISK B` prompt polls `GETIN` from the start-up stub. The inn tests bit 2 of `$028E`, the KERNAL's CTRL flag, at `$78A2` after it has the letter, so CTRL-A needs both PETSCII `$01` and that flag.

## Screen

- **Menus (traced).** Text mode, matrix at `$0400`, written by the string printer at `$0E91` (`$0B24`; cursor column `$24`, row `$25`).
- **Play screen (traced).** A raster interrupt (handler stores at `$C5E3` and `$C5F4`) splits the frame. Above line 177: VIC bank 0, multicolour bitmap at `$2000`, colours at `$0400` and colour RAM. Below: bank 3 with `$D018 = $38`, bitmap at `$E000`, colours at `$CC00`. Bank changes go through the loader's `$9D0A`.
- **All play text is drawn into the bitmap (traced).** `$0D42` (`$0B39`) draws a string at row `$0B`, column `$0C`; `$0D1C` (`$0B2D`) draws one character. Glyphs are 8 bytes each from `$C9E8`, indexed by character − `$20`, stored inverted. The font is the `$0218`-byte read from side A block `$190`. Entry `$0B33` appears to draw rows below 17 on both bitmaps (read).
- **Combat (checked on the oracle, 2026-10-11).** The fight screen is a text screen: display mode 0 at the `fight` mark of `boot-to-fight-and-save.txt`, with the text in the matrix at `$0400`. The earlier guess here, that combat shows only the `$E000` bitmap, was wrong. The combat file does load over `$2000–$34FF`, where the upper bitmap lives. In the same run the mode is 1 at the `arena`, `monsters` and `innkeeper` marks and 2 at `won`.

- **Page flipping (checked on the oracle).** The 3-D view is drawn into whichever of the two bitmaps is not being shown; `$07` names it. Then the display switches: mode 2 (split) when the new view is in the upper bitmap, mode 1 (whole frame from `$E000`) when it is in the lower one. The mode therefore alternates on every redraw. See [C64-CODE.md](C64-CODE.md).
- **Display modes (read).** `$0389` selects what the raster interrupt does: 0 nothing (text screen), 1 bank 3 for the whole frame (lower bitmap only), 2 the split at raster line `$B0`. `show_text` at `$1BC7` and `show_bitmaps` at `$1BF1` set it. A fight uses mode 0 (see Combat above).

- **Text-to-bitmap preparation (read and captured, 2026-10-11).** `$0400` is also the upper bitmap's colour matrix. Preparing the inn-to-town display writes colour bytes there before the bitmap-enable/mode flags change. An Atari text list reading it live therefore showed repeated `2` characters. The kernel now displays a completed snapshot until it starts conversion, then blanks until publication. Original game code remains unchanged; [SPEED.md](SPEED.md).
- **Original C64 play timings (traced in VICE PAL/true-drive, 2026-10-11).** First poll to next first poll: step 141,299 cycles / 143.4 ms, left turn 127,752 / 129.7 ms, right turn 140,432 / 142.5 ms, character sheet 80,166 / 81.4 ms, return to town 157,460 / 159.8 ms. Inn-to-town includes disk loading and takes 13.228 seconds. Raw monitor stamps and Atari comparisons: [SPEED.md](SPEED.md).
- **Packed pictures (read).** `draw_picture` at `$C2C0` unpacks from `$3002` to the lower bitmap at `$E2C0` with colours at `$CC58`; a run is `$7B`, count, value.

Because there is no text matrix during play, the trace tool records text at the printers. That gives the oracle a ready comparison stream: row, column and string for everything the game prints.

## Resident memory, as loaded

| Range | Source | Contents so far |
| --- | --- | --- |
| `$0B00–$1FFE` | A `$017` | Jump table at `$0B00`; printers, key wait, random numbers |
| `$2000–$34FF` | – | Upper bitmap in play; also where `EN`, `CM`, `ST` and the `9x` files load |
| `$3500–$49FF` | A `$140` | Combat code that stays resident: it calls into `CM` and `C3` (read). The file table and the next block overwrite its tail |
| `$4A00–$4E9F` | A `$184` | Looks like the trap code for treasure, judged from its texts |
| `$4700–$48FF` | side's last two blocks | File table, picture index, side number |
| `$4EA0`, `$5FC0`, `$70E0` | three files per area | `$1120`-byte picture sets; `C3` loads at `$4EA0` for combat |
| `$6000–$68FF`, `$6900–$7F99` | B `RO`, `GO` | Roster and inn/menu code, loaded when at an inn or menu |
| `$8200–…` | area file | Map grids, then 6502 code for the area's events |
| `$8C00–$9CEE` | A `$160` | Item names and other tables; no code (read) |
| `$9D00–$9FFF` | boot file | Disk loader |
| `$A000–$C92B` | A `$03F` | Jump table at `$A000`; play-mode logic and strings; spells; file loading, sound, the interrupt handler and key reading from `$C355` up |
| `$C92C–$CBFF` | A `$195`, `$190` | `$C9E8` on is the font |
| `$CC00`, `$E000` | – | Lower-screen colours and bitmap |

## Party position

`$3D` is the square as y × 16 + x, with 0,0 in the south-west corner; `$3C` is y and `$3B` is x (read at `$0F29` and seen on the oracle). `$40` is the facing as a mask: `$C0` north, `$30` east, `$0C` south, `$03` west. (*Checked:* routes computed from these and the state grid below reached the gate, the stairs, the arena, the inn door, five shops and the portal square two sectors away (where a wandering group met the party; the portal itself was not entered, corrected 2026-10-13). The game's own Location spell reports the same square and facing.)

## Area files

An area file loads at `$8200`. *Checked* against Sorpigal (`EG`, side B) and the dungeon under it (`RK`, side B):

| Offset | Contents |
| --- | --- |
| `$000` | 16 × 16 bytes, first grid. Two bits per direction in the same order as the facing mask; presumably what the walls look like. Not examined |
| `$100` | 16 × 16 bytes, state grid. In each two-bit direction field the low bit blocks movement that way |
| `$200` | 50 data bytes |
| `$232` | 6502 code. It looks up `$3D` in a table of event squares, checks the facing mask, and calls that square's handler |

**The event code runs only for flagged squares (checked on the oracle).** Resident code jumps to `$8432` after a move only when bit 7 of `$38` is set (tested at `$10F9`). Twenty moves through sector `EJ` executed nothing in the area file. What sets that bit is not worked out; it is related to bit 7 of the square's state byte, but not equal to "this square has an event".

**Areas are programs.** The handlers are native code inside the area file with their text inline: the innkeeper, shop signs, statues, stairs, the arena. Sorpigal has 24 event squares. This is why the game's logic can move to the Atari unchanged, and also why every area file has to be disassembled far enough to find its hardware-touching calls.

### How areas connect (checked)

- **Exits.** A handler leaves for another area with `LDA #c1 / LDX #c2 / LDY #side / JMP $0B78`. The two codes make the file name (below 26 a letter, from 26 a digit) and the side is 1 to 3 for B to D. Sorpigal's gate is `$11, $0A, 2`: file `RK` on side C. Where needed the handler first sets the arrival square in `$3B` and `$3C` (read; both are 10 in the one case walked).
- **Neighbours.** Data bytes 8–19 name the areas to the north, east, south and west. Walking off an open edge of an outdoor sector loads that neighbour, and the party appears on the opposite edge. An area that names itself has no neighbour.
- **What loads.** A crossing loads the new area file and only those of the three picture sets that differ.

[c64-areas.json](c64-areas.json) lists all 55 areas (14 on side B, 20 on C, 21 on D) with their neighbours, 82 exits and 818 event squares. Every exit names a file that exists on the side it names. The route to side D in `trace-side-d` was computed from this graph before it was walked.

File names are per side: `RK` on side B is the dungeon under Sorpigal, `RK` on side C is the country outside it. One file, `SE` on side D, has other code where the event lookup normally is.

ScummVM's PC engine describes maps as 512 bytes of walls and states with separate code. The C64 layout looks analogous, but **no byte-level comparison has been made.**

## A fight (traced)

Accepting the arena fight at dungeon square 1,13:

1. `EN` loads at `$2000`.
2. `EN` reads one block of monster records to `$2D00`: block `$0165` plus an index it computes from the monster's group and number (code at `$24D0–$251C`). Blocks `$0165`, `$0166` and `$0168` were seen.
3. `EN` reads the monster's picture to `$3000`, taking the start block from the picture index at `$4880` and the length from the next entry (code at `$2183`).
4. `CM` loads at `$2000` (`$1500` bytes) and `C3` at `$4EA0`.
5. The fight runs with no further disk access, including the experience award. Leaving it needs none either.

Monster records are 32 bytes: a 15-character name and 17 data bytes, eight to a block. There are 195, identical on sides B, C and D; names and data are listed in [c64-logical-disk.json](c64-logical-disk.json). The 17 bytes are not decoded.

## Encounters, treasure and death (traced, 2026-10-11)

From `trace-treasure-reload` and `trace-death`, both under Sorpigal (`RK` on side B).

- **Where encounters come from (read).** The area's dispatcher at `$8432` looks the party's square up in its table. A square that is not there gets `JSR $A084 / JMP $0B48`: resident `$0B48` starts an encounter with a group of the game's choosing. That is what a wandering group is, and it explains why resident code enters the area file on squares that have no event. A handler can make the same jump itself, with a throw first (`$87DC`, six squares: an encounter on one of two outcomes), or after filling the monster list: number in `$0343,X`, 1 in `$0334,X`, the count in `$8B`. The lair at 13,5 lists ten of monster `$0E`, snakes; four squares at 4–7,2 list a throw of five plus three of monsters 1, 9, 13 and 20.
- **The choice before a fight (traced).** `EN` loads, reads the monster block and the picture, lists the group, and asks `'A' ATTACK 'R' RETREAT 'B' BRIBE 'S' SURRENDER` on display mode 1. Attack loads `CM` and `C3` as in the arena. *Seen in exploration only:* to surrender the answer was `THE MONSTERS DON'T TAKE PRISONERS!`, to a bribe `NO RESPONSE`, and the fight began either way.
- **Who can do what in a fight (traced).** The prompt lists only what the character can do: `'A' ATTACK` and `'F' FIGHT` for those in reach of the monsters, `'S' SHOOT` for some of those behind them (Zenon III and Swifty Sarg here), `'C' CAST` for the two spell casters, and always exchange, use, retreat and block. A key not on the list is taken and ignored.
- **Treasure (traced).** After three gremlins were beaten at 4,5, `S` printed `SEARCH: YOU FOUND...` and loaded three pieces at once: `ST` at `$2000` (`$063D` bytes, block `$FC`), and `$032B` bytes to `$2800` and `$02A3` to `$3000` (blocks `$DC` and `$E0`). The screen shows a picture and `-IRON CHEST-` with `1) OPEN IT  2) FIND/REMOVE TRAP  3) DETECT MAGIC/TRAP`. `1` asks `WHO WILL TRY '1'-'6'?`. Character 1 set off a trap (`GAS!! A FAINT HISS CAN BE HEARD AS NOXIOUS FUMES FILL THE AIR!`), then `IT OPENS! EACH SHARE IS WORTH 7 GOLD` and `CRAG THE HACK FOUND HALBERD`. No disk access after the search. Afterwards the sheet shows gold 207 from 200, the halberd in the backpack, and the opener unconscious with no hit points; five of the six are marked `*` in the party panel. The arena's fights and the snakes' lair leave nothing: `SEARCH: NOTHING`.
- **Saving it and loading it again (traced and checked).** Signing in at the inn after that writes the roster with 24 bytes different from the original. After a restart the options menu's roster read returns those bytes, and the inn's sheet shows experience 185, gold 207, the halberd and `UNCONSCIOUS`: nothing is put right by saving or loading.
- **Death (traced).** When the last character is down the game reads `RO` and `GO` again (the roster and the menu code), switches to text and shows `THE SHADOW OF DEATH HAS FALLEN UPON YOUR PARTY! FORTUNATELY, YOU MAY RENEW YOUR QUEST FROM THE LAST INN IN WHICH YOU STAYED BY PRESSING RETURN`. RETURN leads to the options menu, not to the inn. Nothing is written. The roster is as it was last saved: experience 60 and full hit points here, where no save had been made. The party is empty and is put together again at the inn.
- **The combat file borrows the NMI vector (read, and seen on the Atari).** Before it copies the lower bitmap from `$E000` to `$4000` (`$1F` pages, at `$26C9`) the combat file saves `$FFFA/$FFFB` in `$271E/$271F`, masks interrupts and switches the KERNAL out; afterwards it switches it in again and stores the two bytes back to `$FFFA/$FFFB`, which then go to the RAM under the ROM. The two routines are called from one place only, as a pair.

## Town services, spells and characters (traced)

- **Services.** Each of Sorpigal's five services loads one file at `$2000` when the party accepts: `91` blacksmith, `92` temple, `93` food, `95` training, `96` tavern. Buying a dagger needed nothing further. **Leaving a service turns the party to face away from it.**
- **Character sheet and spells.** Viewing a character and casting Location load nothing; that code is resident.
- **Play commands.** Quick reference, protect, search, bash, unlock and order load nothing.
- **Creating a character** runs from `GO` with no disk access until `SAVE CHARACTER (Y/N)?`, which writes the roster exactly as signing in does.

## Saving (traced and checked)

The game saves when the party signs in at an inn, and when a new character is kept. Signing in loads `RO` to `$6000` and `GO` to `$6900`, re-reads the file table, and writes `$0900` bytes from `$6000` back to `RO`'s blocks (`GO` at `$7A02`, through the jump at `$7F6E`). After each traced write the disk copy holds exactly the bytes that were in RAM (18 and 38 of them different from the original), and **no other block on the side changed.** `$0900` is 18 × 128, which fits a roster of 18 characters; the record layout is not decoded.

Taking stairs loads the new area file and its three picture sets and writes nothing.

## Not yet known

- The exact rule behind bit 7 of `$38`. It is at least partly the chance of a wandering group: see "Encounters, treasure and death".

- What most resident routines do. Which bytes are code and what touches the hardware is now known ([C64-CODE.md](C64-CODE.md)), and the display, view, sound, key and disk routines are named; the view's geometry is not decoded. The sound data was decoded and traced on 2026-10-11 ([SOUND.md](SOUND.md)).
- The first map grid, most of the 50 data bytes, the roster record and the monster data bytes.
- Treasure beyond one chest: what `ST` and its two companions hold, what finding or removing a trap and detecting magic do, and which monsters carry anything.
- The pre-fight choices other than attack are not in a recorded run. Nor is a single character's death and raising.
- How the three side-D areas that read keys themselves behave. Known only from the code.

**Graphics-to-text sequence, read 2026-10-11:** `show_text` calls `$1C2A` before clearing text; when `view_page=$40`, that routine copies the upper view down, selects lower bitmap mode 1 and clears the hidden view. Only afterwards does `show_text` clear the text matrix and set mode 0. Fresh normal Atari800 captures of six character sheets did not reproduce the reported Windows `2` window; the game routines remain untouched. [Follow-up](../FIX.md).

**Original drawing work, host-profiled 2026-10-11:** one walking step calls three wall pieces (68,643 corrected instruction cycles), clears 3,840 hidden-view bytes (42,713 cycles), and fills play colours (10,179 cycles). These host instruction counts add page penalties but are not real C64 DMA-inclusive timings. Native Atari work outside conversion is about 135 ms, versus 441 ms for conversion. Keep original routines unchanged and optimize the Atari presentation first; [detailed evidence](GRAPHICS-PERFORMANCE.md).

**Presentation optimization checked 2026-10-11:** repeated-page guards, identity
copies and exact unchanged-row reuse now reduce walking conversion from 441
to 364 ms in Atari800. All seven benchmark game-byte hashes and settled
screens match the baseline. Original wall drawing, clear, colour-fill and
sound routines are untouched; first-poll delivery/comparison rules are unchanged.

**Palette follow-up checked 2026-10-11:** the kernel now avoids repeated
nearest-colour calculations when successive rows select the same ordered
colours. Walking conversion is 335 ms (previously 364), while original wall
pieces, bitmap clears and colour writes still execute unchanged. Native
town/outdoor/dungeon/arena/encounter/fight states retain pixels and compared
game bytes; the sampled battle commands use text mode and do no palette
work. [Measured workloads](PALETTE-PERFORMANCE.md).

**Ctrl+A combat and repeat, read/checked 2026-10-11:** `GO` enables all-key
repeat by storing `$80` at `$028A`. Original scanner `$EA87` uses delay
`$028C` and rate `$028B`; the game's `$C648` reader controls the initial
delay and swallows Ctrl+A during effect 5. `CM` includes `$01` in the command
table at `$209C`; `$20F9` chooses attack, shooting or block. Six scripted
commands match VICE/oracle at 149 events and Atari at ten new checkpoints.
The fixed normal Atari keyboard generates held repeats through that same
reader/dispatcher, without changing game routines. [Reference and tests](KEYBOARD-REPEAT.md).

**Atari disk optimization, checked 2026-10-11:** original disk entry points,
parameters, game files, logical blocks and loader return values remain
unchanged. Only the Atari sector loop batches OS setup/restoration, and the
build replaces a known zero-filled startup image range with an exact clear.
Nine scripts / 116 checkpoints and three exact saves still pass. Fifteen
native boundary/partial/upper-RAM reads and a roster-sized write/readback
also verify state restoration and disk bounds. [Evidence](DISK-PERFORMANCE.md).

**Encounter panel, read/checked 2026-10-11:** EN `$2742` starts at colour RAM
`$D816` (column 22), writes eighteen `$0E` nibbles and advances forty bytes
per monster row (`$8B`). Ordinary commands begin at column 30. This explains
the Atari's former eight-column white strip. Bitmap cells outside the drawn
monster still advertise stale matrix colours. The Atari now uses the actual
panel boundary and present pixel pairs; the original routines are unchanged.
Original pause `$C355` tests exact equality with its jiffy target. Extra
rendering initially skipped it; blank-byte skipping restores both combat
routes. All 87 tests / original state and saves pass. [Evidence](COLOUR-SELECTION.md).

## Additional traced behavior — 2026-10-12

IF's `$89F0` and EH's `$86D2` call the `$A087` key-reader wrapper; DP's `$890E` calls GETIN directly. SPACE ends the IF vault-alarm wait and cancels EH's maze drift; I at DP's spinning floor is dispatched as forward movement. **Traced / checked** on VICE, the oracle and Atari. The new combat and chest sessions exercise actual spells, shooting, exchange, charged-item use, failed negotiations and trap removal. **Condition `$40` is unconsciousness; `$C0` is death.** The new death scenario first leaves Crag unconscious in combat, then the gas trap kills him; the native temple raises him. The original pause uses equality against its clock target; the Atari conversion can pass that target unless the clock is held during conversion. [Fixtures, outcomes and coverage](GAMEPLAY-COVERAGE.md).

## Memory lifetimes clarified — 2026-10-13

**Read and checked on the oracle:** the lower-to-`$4000` copy described above
is a **restore of resident code and data**, not a saved picture. Before loading
combat, EN `$2456/$2458` copies `$4000–$5EFF` to `$E000–$FEFF` after switching
to text. At CM `$26C9`, all 7,936 backup bytes equal the captured resident bytes.
This prevents use of lower-bitmap padding for permanent support code. GO
`$795D` fills party-record slots at `$0800–$0AFF` through a self-modified
indirect store; 762 of these 768 bytes are accessed in the 21 surveyed
gameplay scenarios. [Probe, complete scope and 64 KB implications](64K-FEASIBILITY.md).


## 65XE presentation contracts — 2026-10-13

**Traced / emulator-checked:** the optional 65XE profile suppresses colour
metadata writers while preserving bitmap/text drawing and game state. The
glyph-colour writer is `$C38E` with store `$C3CD`; `$C137` is a message routine,
correcting the initial feasibility inventory. Its three shortened helpers and
wait/pause wrappers are guarded by original-byte checks. The wrapper in the
unused `$C91A–$C92B` reader forces publication before a new wait; actual RNG
wait loops and pause/input dispatch remain. All 21 scenarios / 257 native
marks, original events and saves pass. [Contracts and comparison scope](65XE.md).
