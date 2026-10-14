# Atari design

Written 2026-10-10, at the start of Phase 3, and updated the same day when the first build ran. This is the plan for the Atari build and the reasons behind it; "What runs" below says how much of it exists. How it was arrived at is in entries 14 to 18 of [PORTING-LOG.md](PORTING-LOG.md).

## What runs (2026-10-11)

```bash
python3 port/atari/build.py                                  # build/atari/mm1.atr, bootable in a 130XE emulator; starts with the title
python3 port/atari/build.py --no-title                       # the same starting at the game's first prompt, as the checks below build it
python3 port/atari/title_check.py                            # the title: frames, tune, scenes, Escape (docs/TITLE.md)
python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt [--pictures]
python3 port/atari/play_check.py                             # a short game through the emulated keyboard
python3 port/atari/screenshots.py                            # the gallery, docs/SCREENSHOTS.md
python3 -m unittest tests.test_atari                         # all eight scripts and the play check, about 35 seconds
python3 port/atari/altirra_check.py [--sio]                  # a save, a restart and a short game in AltirraSDL
python3 -m unittest tests.test_altirra                       # both ways, about 50 seconds
```

To play: open `build/atari/mm1.atr` in Atari800 or Altirra set up as a 130XE with BASIC off, on a copy, since the game saves to it. Press ESC at the title (SPACE shows the scenes first) and RETURN at the first prompt.

**The game runs on the emulated Atari, and its memory equals the host oracle's at every checkpoint of all eight scripts** (106 marks): the options menu, creating and saving a character, the town's five services, a spell, a fight in the dungeon, the walk across three outdoor sectors, and all four disk sides; and since 2026-10-11 a wandering group met and beaten, a chest found and opened, the save loaded again after the Atari is switched off and on, and a party wiped out and renewed from the options menu (log entry 20). All three saves leave the Atari's disk equal to the oracle's.

What that does and does not cover:

- **Covered:** the game's logic, data, random numbers and disk traffic. The game's own code does all of it; 35 instructions have an operand changed and nothing else in the game's files is touched.
- **Not covered by that comparison:** the Atari kernel, which has no counterpart on the C64, and what is on the screen. Two further checks stand in. At every mark the kernel's code and tables must equal what was assembled; and when pictures are taken, ANTIC must be on the display list that goes with the screen. See "Checks on the kernel itself" below.
- **Text screens are shown** (the disk prompt, the options menu, the inn, character creation, character sheets, combat). Until 2026-10-11 they were garbage in every build since the colour work: the game was overwriting an instruction of the kernel (log entry 18).
- **The play screen is shown in colour.** Whenever the game asks for a key, the kernel copies what a C64 would be showing into the Atari's display buffer. For each row it first picks the three colours that serve the row best, and a fourth for the command panel's columns. Twenty-five screens, each beside the C64's, are in [SCREENSHOTS.md](SCREENSHOTS.md). A row with more colours than registers loses some: the gremlin and the snake, green on the C64, come out tan.
- **The keyboard works.** `play_check.py` goes from the first prompt through the options menu and the inn into the town and takes a step, all through the emulated keyboard, CTRL keys included.
- **Disk swapping, in the four-disk build only (2026-10-13).** In the one-image build people play by default, the kernel gives the game whichever side it asks for; the prompts for sides C and D never appear and the first prompt is a "press RETURN" screen. `build.py --disks` makes four 130 KB images for real 1050 disks, where the game's own `INSERT DISK x AND PRESS 'RETURN'` prompts are real: [DISKS.md](DISKS.md).
- **The screen goes black during disk transfers** on the play screen. Text screens stay on.
- **It starts with the C64's title (checked, 2026-10-12).** The original title program runs before the game: two frames, a three-voice tune, eight scenes, Escape to start. It is a stage of its own in front of the kernel, gone when the game is loaded; the game after it equals the oracle in all nine scripts. [TITLE.md](TITLE.md), log entry 36.
- **Sound works (checked, 2026-10-11).** The game's stand-in SID registers drive joined POKEY channels 1+2. All nine original effects produce PCM audio, with approximate envelopes; the key interruption rules and sound-off option are preserved. Both Altirra disk modes check pitch and POKEY/keyboard restoration after SIO. [Sound design and evidence](SOUND.md), log entry 21.
- **It plays in two emulators.** Atari800 runs the lockstep scripts and the play check. AltirraSDL runs `altirra_check.py`: a character created and saved, the machine started again from the written disk, then the inn, the town and a step, with the kernel and the display list checked at eight stops. It passes with Altirra's disk patch on and with it off, when the OS ROM does every transfer over the emulated serial line (log entry 19). Both emulators use Altirra's OS ROM; Atari's own has not been tried.
- **Play speed is measured and transitions fixed (checked, 2026-10-11).** Both Atari emulators reproduce and now eliminate transient `2` characters on text-to-graphics switches. Completed text snapshots and publication after conversion prevent the game from displaying colour bytes as characters. Walking/turns improve from 38 to 34–35 NTSC frames; return from a character sheet improves from 34 to 26. The earlier eleven-frame copy estimate was wrong. Details, C64 timings and remaining conversion cost: [SPEED.md](SPEED.md), log entry 22. Earlier standard-SIO measurements were 52 seconds to the first prompt, 5.5 to options, 11 inn-to-town, 1.8 to save; these have not been remeasured after the display change.

### What the comparison had to learn on 2026-10-11

- **A restart.** The script step `restart` cold-starts the emulated Atari, which boots again from the disk the game has written to. Memory after that boot equals the oracle's new machine at every mark: the boot code sets everything the game reads and does not lean on what power-on leaves in memory.
- **A key during a pause.** The test kernel gives the pause routine's poll (`$C378`) the key the harness names in `pause_key`, as the oracle does. `lockstep.py --quick` plays a script that way; the fight-and-save script passes in a third of the time.
- **Two bytes that belong to the machine.** After a lost fight `$271E/$271F` hold `$DC86` on the Atari and `$FE43` on the C64: the combat file's copy of the NMI vector, taken while it has the C64's KERNAL switched out and put back afterwards ([C64-RUNTIME.md](C64-RUNTIME.md)). On the Atari it saves the kernel's own vector and stores the same two bytes back, so nothing changes. The two addresses are left out of the comparison (`MACHINE` in `lockstep.py`), and the kernel check confirms the vector is intact.

### Checks on the kernel itself

The lockstep comparison leaves out the memory the kernel occupies, because the oracle has nothing there to compare with. That let a store by the game into the kernel go unseen: `$DD02`, CIA 2's data direction register on the C64, was the opcode of an instruction in the vertical-blank handler (log entry 18). Three checks now cover it:

- **The kernel's code and tables equal what was assembled, at every mark** (`lockstep.py`, `kernel_changes`). `build.py` lists the pieces that never change (`fixed`, in `layout.json`): everything in the three main-memory segments except the variables and one operand the disk code writes. `lockstep.py --kernel-writes` lists by label every kernel byte a run did change, which is how the list of pieces was drawn up.
- **ANTIC is on the right display list** whenever a picture is taken (`lockstep.py --pictures`, so for every screen of the gallery) and twice in `play_check.py`: the text list on a text screen, the play screen's list otherwise. The emulator is asked where ANTIC's list pointer is.
- **`build.py` refuses to build** if the kernel's stand-in registers are not where it points the game's operands, or if the inventory holds a CIA register with no stand-in.

Not checked: the two segments in the extended bank (display lists, the screen copy, the colour choice). The game's code cannot address that bank. The inventory behind the redirections is static: an access through a pointer would not be in it, and the first check is what would catch one.

### How little had to be written

The expectation was that 76 machine routines would be replaced. In the event almost none were:

- **Video, sound and CIA registers:** the 35 instructions in the kept code that address them have their operand pointed at a stand-in register file in RAM (31 for the video and sound chips, 4 for the CIAs). The game's display switches, its interrupt handler and its sound code then run unchanged and harmlessly.
- **Keys:** the game calls the C64 KERNAL at `$FFE4`. With the Atari's OS switched out that address is RAM, and the kernel puts its own key routine there.
- **Interrupt and clock:** the game installs its handler at `$0314` and chains to the address it found there. The kernel's vertical-blank handler jumps through `$0314` as the KERNAL does, and what the game finds there is the kernel's routine that counts the clock.
- **Disk:** the two entry points at `$9D0D` and `$9D10` lead to a sector loop that switches the OS in for each transfer, with the game's zero page swapped out.
- **Start-up:** the C64's own start-up stub runs. The boot code loads what the title program would have loaded, sets memory as the title program leaves it (taken from the oracle), and jumps to the stub. Since 2026-10-12 the title program itself runs first when the disk is built with it; Escape hands back to the same boot code, which still loads everything and sets memory from the oracle.

The kernel is about 660 bytes in the old loader's page, 650 under the OS (128 of them the saved zero page), and in the extended bank about 1.5 KB of display lists, tables, the copy routine and the colour choice beside the 9 KB picture, the 1 KB text font and 4 KB of colour tables. That bank is now full apart from a few hundred bytes.

## Decisions by the owner (2026-10-10)

- **Target: the 130XE (128 KB).** A build for 64 KB machines may follow later. Anything that would help one is logged in [64K-NOTES.md](64K-NOTES.md).
- **Keep the C64's screen scheme:** two bitmaps, the 3-D view drawn into the hidden one and flipped. Drawing into a single screen is the fallback if memory has to be saved.

## Principle

**The game's code and data stay at their C64 addresses and are not changed, except where a routine touches the machine.** The Atari has the same CPU, and with its OS and BASIC ROMs switched out it has RAM everywhere the game lives. The 76 machine routines outside the start-up code ([C64-CODE.md](C64-CODE.md)) are replaced at their entry points. Nothing is relocated, so the generated listings need no symbolic pointers, and the Atari's memory can be compared with the oracle's byte for byte.

## Memory

| Address | On the C64 | On the Atari |
| --- | --- | --- |
| `$0000–$00FF` | Game variables, KERNAL variables | Game variables; the few KERNAL ones the game reads (`$A1/$A2` clock, `$C6`) kept up by Atari code |
| `$0200–$03FF` | KERNAL variables, game variables from `$0334` | The same game variables; interrupt vectors while the OS is switched in |
| `$0400–$07FF` | Text screen; colour matrix of the upper bitmap | As written by the game; copied to a completed text snapshot before ANTIC displays it |
| `$0B00–$1FFE` | Resident code | Unchanged, apart from replaced routines |
| `$2000–$34FF` | Upper bitmap; overlays load here | The same |
| `$3500–$4E9F` | Resident combat and trap code; file table at `$4700` | Unchanged |
| `$4EA0–$81FF` | Picture sets; `C3`, `RO`, `GO` at times | The same, with pictures re-coded for Atari colours when the disk is built |
| `$8200–$8BFF` | Area file | Unchanged |
| `$8C00–$9CEE` | Tables | Unchanged |
| `$9D00–$9FFF` | Disk loader | **Atari disk code and interrupt handlers.** The two entries `$9D0D` and `$9D10` stay where the game calls them |
| `$A000–$CBFF` | Resident code, tables, font | Unchanged. Needs BASIC out (`$A000–$BFFF`) and the OS out (`$C000–$CBFF`) |
| `$CC00–$CFFF` | Colour matrix of the lower bitmap | As written by the game; not displayed |
| `$D000–$D7FF` | I/O chips | Atari hardware. Only replaced routines address it |
| `$D800–$DFFF` | Colour RAM, CIAs | 2 KB of RAM under the OS. The game's colour writes land in `$D800–$DBE7` and the screen copy reads them. **The kernel's interrupt handlers and key reading are at `$DC00–$DFFF`**, where the C64 has its CIAs: the game's four CIA accesses are pointed at stand-ins, or they would be stores into the kernel |
| `$E000–$FF3F` | Lower bitmap | The same, in RAM under the OS |
| Extended banks | – | The picture ANTIC shows, and Atari support code and tables |

**The OS ROM is out during play.** The game's code runs through `$C000–$CBFF` and its second bitmap is at `$E000`, both under the Atari's OS. So the build has its own interrupt and keyboard handling. The OS is switched in only for disk transfers, if that route is taken (below).

Measured on the oracle over ten sessions, the game never touches `$9D26–$9FFF`, `$D800–$DFFF` beyond colour writes, or `$FF4A–$FFF9`. That is where Atari code can live in main memory.

## Display

### The idea, tried and working

The game keeps its screen as a C64 multicolour bitmap: 25 rows of 40 cells, each cell 8 bytes, two bits per pixel. **ANTIC mode 4 draws characters that are exactly such cells**, with the same bit order: pairs `00`, `01`, `10`, `11` select the background and three colour registers. So a row of the game's bitmap can serve directly as that row's character set. The "text" on screen is then fixed: character codes 0 to 39 on every row.

`port/atari/display_demo.py` does this with a screen taken from the oracle and photographs the result in Atari800:

```bash
python3 port/atari/display_demo.py              # build/atari/display-demo.png and display-demo-c64.png
```

The town screen comes out complete: the view, the command panel and the party list, all 25 rows.

What it takes:

- **Rows three to a 1 KB block.** A character set starts on a 1 KB boundary and holds 128 cells. A row is 40 cells (320 bytes), so three rows fill a block with 64 bytes to spare, and a row then uses codes 0–39, 40–79 or 80–119. The picture is 9 blocks. In the C64's own layout, rows 320 bytes apart, four rows in every sixteen cross a boundary and could not be shown this way.
- **A display-list interrupt on every row** sets the character-set address and that row's colours for the next row.
- **25 rows are 200 scanlines.** The display list starts with two blank-line instructions instead of the usual three. Atari800 shows all of it; a real television's overscan is untested.
- **Timing lesson.** On these lines ANTIC takes about 40 of a scanline's 114 cycles. With 24 cycles of work before `STA WSYNC` (under the OS's dispatcher) the character set changed one scanline late and the first line of every new block showed the wrong cells. Keeping it to `PHA / TXA / PHA / LDX / LDA table,X` fixed it. The real build has no OS dispatcher in the way, which gives it more room.

### Colours

The C64 chooses three colours for every cell; the Atari has three registers for a whole row, plus a fourth that replaces `11` in cells whose character code has bit 7 set. Rows can each have their own colours. In the experiment:

- Each row takes its three most used C64 colours; other colours go to the nearest of them.
- The command panel beside the view (columns 30–39 of the first 16 rows) is marked with bit 7 and drawn in the fourth register, so its cyan does not cost the view a colour.

That is already recognisable: grey walls, a brown door, yellow torches. It is done on the host on a finished screen. **In the port the pixel values have to be right in the data the game draws from:** the three picture sets, the monster pictures, the packed pictures and the font are re-coded when the disk is built, and the game copies them as it always did. Choosing those palettes well is graphics work still to do, and it is where the Atari version will look different from the C64, as agreed in [SPEC.md](../SPEC.md).

### From the game's bitmaps to the screen

The game draws into two bitmaps in the C64's layout, rows 320 bytes apart, and decides with `display_mode` and `view_page` which rows of which bitmap are on screen. ANTIC needs the three-rows-per-block layout. Two ways to bridge that:

**Chosen first, and built: copy.** A routine copies the 25 rows that should be visible into a 9 KB buffer in an extended bank, in ANTIC's layout. The 130XE lets ANTIC read an extended bank while the CPU sees main memory, so the buffer costs no main memory. The copy runs when the game asks for a key (`$FFE4`) and it is either the first such call for two frames, which marks a new key wait or pause, or a key has been taken since the last copy. The game is turn-based, so those are the moments the screen matters.

The copy also does the colours, which the experiment did on the host. For every cell it reads the C64 screen-matrix byte, works out which of 16 tables fits that cell's two colours in this row, and passes the cell's 8 bytes through the table. The tables are built by `build.py`. Pixel pair `11` (the C64's colour RAM) is always kept as `11`.

**Checked 2026-10-11:** exact palette-input/mapping caches for rows 6–24 reuse 1,140 bytes of unused display padding. Uniform colour-RAM rows can skip colour selection when every matrix byte matches; otherwise matching selected colours can skip the nearest-colour calculation. The later row shortcut uses another 26 padding bytes: only an exact prior input hit with idempotent mappings and equality of all 320 raw/output bytes can skip conversion. It skips nine lower rows in the measured town movements. Identity mappings copy directly and unchanged lookup pages avoid operand updates. Fifty cached/full palette cases and complete old/new converter checks retain the same output and tie order; [GRAPHICS-PERFORMANCE.md](GRAPHICS-PERFORMANCE.md).

**How a row's colours are chosen** (`choose_colours` in `kernel.s`), on the Atari, every time the screen is copied:

1. Count the colour-RAM colours of the row's cells and the screen-matrix colours (both nibbles of every cell).
2. Register 2, which draws pair `11`, gets the commonest colour-RAM colour. In the first 16 rows the last ten columns are counted apart and their commonest colour goes to register 3; those cells have bit 7 set in their character code, which is what makes `11` use register 3.
3. Registers 0 and 1 get the two commonest matrix colours other than black and register 2's.
4. Every C64 colour is then assigned to the nearest of black and those three, by a table of distances between the C64's colours.

The Atari colour standing in for each C64 colour is the nearest one in Atari800's NTSC palette to VICE's, measured from the two emulators.

**What this cannot do.** A row holds at most black and three colours, plus the panel's. Where the C64 has more on one row, the rarer ones turn into their nearest neighbour: in the encounter screen the white monster names over a blue band come out in the band's colour scheme of that row. Two ideas for later, neither tried: let any cell use register 3 (a per-row choice between two colour-RAM colours, at the cost of 1 KB of character codes), and weight the counts by pixels instead of cells.

- For: **the game's drawing code runs unchanged**, all of it: the view, the printers, the picture unpacker, the page flip. The Atari's bitmaps can be compared with the oracle's byte for byte.
- For: the picture does not depend on the OS being out, so it stays up during disk transfers.
- Against: about 8,000 bytes copied per update, roughly 110,000 cycles or four frames. The C64 takes about as long to draw one step, so a step would take about twice as long. Copying only the rows that changed would cut that; not designed yet.
- Against: needs the 130XE's separate ANTIC banking, which many third-party memory upgrades lack.

**Rejected for now: show the game's bitmaps directly.** Lay the game's own bitmaps out three rows to a block and change every routine that computes a bitmap address to use a row table. No copy, no extra buffer, and no page-flip cost. It means rewriting the address arithmetic in the printers, the view code, the clear, the page copy and the picture unpackers, and the upper bitmap no longer fits in `$2000–$34FF` in one piece. This is the route for a 64 KB machine and for speed, once the port runs. Logged in [64K-NOTES.md](64K-NOTES.md).

### Text screens

Menus, the inn and character sheets use the C64 text screen at `$0400`. **Checked 2026-10-11:** ANTIC mode 2 now shows a completed copy at `$4000` in display bank 0, using the reordered OS font, 40 columns by 25 rows with the same shortened top margin. Reading `$0400` live exposed bitmap colour bytes as text during transitions. The snapshot reuses the bitmap buffer; mode transitions disable DMA until conversion and `shown_mode` publication finish. VBI honors `frame_ready`; the DLI instruction sequence is unchanged. Graphics-to-graphics updates retain their existing behavior. [Transition evidence](SPEED.md).

## The rest of the machine

| Part | C64 | Atari plan |
| --- | --- | --- |
| Keys | KERNAL `GETIN` at `$C648`, CTRL flag at `$028E` | POKEY keyboard interrupt; a table from key codes to the PETSCII values the game compares with. `get_key` replaced; the key wait and its counters untouched |
| Clock | KERNAL clock `$A1/$A2`, driven by the raster interrupt | The vertical-blank interrupt counts the same two bytes |
| Interrupt | Raster split, sound step, KERNAL chain | Vertical blank: clock, keyboard, sound step. Display-list interrupts: row set-up |
| Display switches | `show_text`, `show_bitmaps`, `irq_install` | Choose the display list; set a flag for the copy routine |
| Sound | One entry, `$A02D`; effect lists stepped by the interrupt | Original sequencer writes stand-in SID registers; the VBI tail translates them to POKEY with generated pitches and approximate envelopes ([checked](SOUND.md)) |
| Disk | `$9D0D` read, `$9D10` write: block, offset, length, address | The same calls, served from an ATR by sector reads. One image can hold all four sides (2,656 sectors of 256 bytes), which makes the disk prompts unnecessary |
| Start-up | Title program and start-up stub | An Atari boot loader that loads the resident blocks and enters the game where the title program does, at the stub. Since 2026-10-12 it runs the title program first ([TITLE.md](TITLE.md)) |

**Disk transfers with the OS out: settled by trying.** The OS is switched in for each sector, with the game's zero page (`$00–$7F`) swapped for the OS's and `$0314/$0315` saved, because the OS's serial code uses those two bytes. Sectors wanted whole and below `$BF00` go straight to their destination; others go through a 128-byte buffer. All 62 checkpoints agree with this in place.

## Checking it

The method is the one from the Wizardry port: the Atari build runs in Atari800 through `libatari800`, fed the same keys as the oracle, and the two are compared after every key. Because nothing is relocated, the comparison can be on memory itself (game variables, both bitmaps, the roster) as well as on the text the game prints.

## Order of work

1. ~~Build skeleton: assemble Atari code, lay out an ATR with the four sides, boot loader.~~ Done.
2. ~~Memory set-up: ROMs out, resident blocks in place, vectors, a vertical-blank handler.~~ Done.
3. ~~Disk read behind `$9D0D`.~~ Done, and the write behind `$9D10`.
4. ~~Text display; reach the options menu with the lockstep harness. **Phase 3's exit.**~~ Done; the harness runs whole sessions.
5. ~~Bitmap display by copy, so the play screen is seen.~~ Done, in grey shades.
6. ~~Colours: per-row palettes chosen from what is on screen.~~ Done. (Re-coding the pictures on disk turned out not to be needed: the copy re-codes each cell.)
7. ~~The keyboard; the disk prompts made unnecessary.~~ Done.
8. ~~Sound: all nine effects translated to POKEY.~~ Checked on Atari800, with a pitch/interruption probe and SIO checks on AltirraSDL (2026-10-11). Play speed measured and text/graphics transition fixed later that day ([SPEED.md](SPEED.md)). Still to do: further conversion speed, effect pacing across display modes, the black screen during disk transfers.

**Reverse-transition follow-up, checked 2026-10-11:** a fresh normal build in Linux Atari800 shows all six character sheets without a repeated `2` window in 240 captured frames. Partial old-screen lines and a black interval are visible. The owner subsequently confirms the freshly recopied Windows disk has no repeated `2`s. No new display-code change. [Evidence](../test-artifacts/reverse/README.md), [next investigation steps](../FIX.md).

**Graphics deep profile and implementation, checked 2026-10-11:** baseline walking conversion executes 414,862 CPU instruction cycles and spans 788,538 elapsed cycles including display/interrupt work. The three optimized paths reduce these to 342,179 and 651,624. Exact idempotent-mapping reuse skips nine unchanged bottom rows; identity copy and redundant operand-write suppression accelerate the others. The original drawing and display interrupt code remain unchanged. [Full analysis, layout and validation](GRAPHICS-PERFORMANCE.md).

**Palette reuse, checked 2026-10-11:** after selection, compare the ordered
three C64 colours with the key for the live mapping. Equality skips rebuilding
all 16 nearest-colour entries. Cached restores invalidate that key; boot
initializes its three bytes at `$DFFC–$DFFE` to `$FF`. Palette decisions,
mapping tie order and per-row panel registers remain exact. Thirteen of
sixteen walking rebuilds are avoided; palette CPU 133,362 → 107,041, whole
conversion 342,179 → 315,858. Move the idempotence constant into EXT;
remaining spare LOADER 8, UNDER 1, EXT 14, EXT2 10. No new bank or game RAM
cache. [Native/differential checks](PALETTE-PERFORMANCE.md).

**Held-key repeat, checked 2026-10-11:** the edge-only keyboard dropped all
same-key samples. It now reads the game's `$028A` all-key repeat flag and
uses `$028C/$028B` exactly as the original scanner's enabled letter-repeat
path, including the game's own delay writes and empty-buffer repeat limit.
Release resets the latch. The unchanged combat code accepts Ctrl+A normally.
Test trampoline storage now aliases the loader's idle 128-byte buffer;
buffered SIO fills it before use. Move matrix scratch to EXT and row/cell
state to UNDER: net UNDER 0 / EXT +14 bytes, spare LOADER 8, UNDER 1, EXT 0,
EXT2 10. DLI instructions and per-row timing are unchanged. [ROM, combat,
disk/sound and layout checks](KEYBOARD-REPEAT.md).

**Disk batching, checked 2026-10-11:** consecutive direct sector reads/writes
now share OS zero page, ROM and interrupts. The kernel restores the game
before bounce copies and before returning, including sound/keyboard state
and the saved IRQ vector. The sector counter shares the DCB word; no new
buffer/bank is allocated. Net LOADER +3 bytes, spare 5 / 1 / 0 / 10.
Boot clears the exactly-zero `$E000–$FF49` snapshot range under a build
assertion instead of reading 63 sectors; all other startup bytes are kept.
Atari800 patched boot 4.19 → 1.29 s, town 1.42 → 0.78; all 86 tests and both
Altirra disk modes pass. [Details](DISK-PERFORMANCE.md).

**Encounter selection, checked 2026-10-11:** wide panels are identified by
mode 1 and the original EN blue-strip marker at `$D816`; other mode-1 views
keep the command layout. Character high bits extend PF3 from column 30 to
22 and are cleared on return. Matrix histograms count only drawn 01/10
pairs in the first sixteen wide-panel rows. Their old palette-input cache
is bypassed and invalidated because selection now depends on bitmap bytes.
Walking/lower rows keep the exact cache/reuse paths. Symmetric distances
remain byte-exact; idempotence constants move into protected TOP padding.
No new bank/buffer, spare LOADER / UNDER / EXT / EXT2 5 / 1 / 0 / 3.
Both emulators show corrected monsters/panels; 87 tests pass. Walking/turns
29 → 30 frames, with stable text transitions. [Details](COLOUR-SELECTION.md).

**Title stage, checked 2026-10-12:** `src/title.s`, 2,021 bytes loaded to
`$8000` by the boot code, which parks itself at `$A000` meanwhile: the title
program unpacks pictures over `$2000-$3F3F`. It runs the unchanged title
program (25 operands redirected like the game's 35) and hooks the kernel in
three places while it does: the key entry, the disk read and the NMI vector's
high byte. The two title frames are shown where the title program draws them:
their cells all have the same three colours, so 19 of the C64 bitmap's 25
rows are character sets as they stand and six are copied to `$1400`. Scenes
go through `rf_bitmap` once each, when the title program waits; the tune's
three voices are translated on channels 1+2, 3 and 4. Escape restores the
hooks, the stand-in registers and the blank text snapshot and returns to the
boot code. No kernel byte changed: spare LOADER / UNDER / EXT / EXT2 5 / 1 /
0 / 3. The disk without the title is identical to the previous one. All nine
scripts pass with the title in front; 98 tests. A hang seen only in
AltirraSDL with serial transfers came from ANTIC repeating a row interrupt
while its DMA is off; the stage turns row interrupts off with the screen.
[Details](TITLE.md).

## 2026-10-12: broader gameplay and conversion follow-up

**Checked:** 21 scripts / 257 Atari checkpoints, including IF/EH/DP direct key calls, combat spells/shooting/items/exchange, encounter choices, chest traps, death/raising and travel through EJ/C and BB/C. The wilderness fight missed the original pause's exact clock target while GETIN converted a screen. IRQ tail now holds the KERNAL clock when PORTB bit 4 selects extended RAM; game IRQ/sound and keyboard handling continue. Six envelope variables moved above GETIN, and `rf_blank` occupies spare TOP bytes. No new bank, sector or game-file changes. Four-byte lookup loops and two-byte identity loops, stack-free matrix decoding and a derived colour-RAM high byte bring movement 30 → 29 frames. [Scope and evidence](GAMEPLAY-COVERAGE.md), [performance](WALKING-PERFORMANCE.md).

## 2026-10-13: a possible 65XE profile

**Read/host-checked, unimplemented:** [64K-FEASIBILITY.md](64K-FEASIBILITY.md)
budgets the present display bank and recommends a fixed-palette direct-display
prototype before a richer single-screen renderer. Six crossing rows share two
1 KB buffers across both bitmap modes. The game's lower bitmap is also a
7,936-byte resident combat backup; the upper region remains an overlay window
even if page flipping is removed. The proposed colour-matrix reuse needs
writer redirections and different text/SIO ownership. The current 130XE
implementation, memory map and compatibility claims are unchanged.


## Implemented 65XE profile — 2026-10-13

**Linked / emulator-checked:** `build.py --65xe` removes the extended bank.
Nineteen raw mode-4 rows and six copies share `$CC00/$D800` with the text
font/snapshot. ROM-font reconstruction reuses the 128-byte SIO staging buffer
with a stack guard; both display modes blank during SIO/publication. Fixed
grayscale and no POKEY effects fit the resident segments, leaving two loader
bytes and one display byte on four disks. Small original presentation helpers
supply 127 resident bytes including entry wrappers. Publication holds the clock
and disables row DLIs while busy. Atari800 and Altirra run at actual 64 KB;
serial save/restart works. [Allocations, checks and limitations](65XE.md).


**Town-redraw follow-up, checked 2026-10-13:** native raw-page display must
follow the game's semantic flip before it clears the old page; waiting until
GETIN erases the visible bitmap. A guarded mode-store wrapper refreshes and
waits for VBI, preserving AXY/P. Visible bitmap copies hold the clock with a
separate busy bit while retaining DMA/DLIs. Reclaimed unused stand-in VIC bytes
hold CHBASE/return code, guarded by the hardware-operand inventory. Captured
movement/turns have zero black frames, but shared-row copying still tears
briefly. Fixed warm colour uses two changed immediate bytes and zero extra
resident RAM. [Implementation, cost and transient evidence](65XE.md).
