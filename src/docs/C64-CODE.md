# C64 code: what is code, what is data, and what touches the machine

Measured on 2026-10-10 from the **Original_v2** set. This is Phase 1's result: every binary of the game is split into code and data, every code file reassembles to the original bytes, and every operand that ties the code to C64 hardware or the KERNAL is listed. How the files get into memory is in [C64-LOADER.md](C64-LOADER.md); what the running game does is in [C64-RUNTIME.md](C64-RUNTIME.md); how this was worked out is entry 10 of [PORTING-LOG.md](PORTING-LOG.md).

**In one line for the port:** the game is 71 KB of 6502 code in 76 files, and only 382 of its 32,850 instructions name a C64-specific address. They sit in 106 routines, of which 26 are in the resident code.

## Reproduce

```bash
python3 tools/analyze_c64.py && python3 tools/mmdisk.py   # the binaries (needed first)
python3 tools/disassemble.py --rebuild                    # trace, write info files, rebuild, compare
python3 tools/disassemble.py -v                           # per-file byte counts and outside calls
```

The first form rewrites `source/c64/game/info/*.info` and [c64-code-map.json](c64-code-map.json), writes listings to `build/source/game/*.s`, and fails if any file does not rebuild.

| Kept by hand | Holds |
| --- | --- |
| [hints.txt](../source/c64/game/hints.txt) | What a static trace cannot work out: two address tables' sizes, which files are in memory together, code nothing refers to |
| [symbols.txt](../source/c64/game/symbols.txt) | Names for addresses whose meaning is established |

Everything else is generated. The info files are committed so that a change in names or in the code/data split shows up as a diff.

## What the game is made of

There are **109 binaries**: side A's 11 fixed reads and the named files of sides B–D, counting a file that is identical on several sides once.

| Kind | Files | Bytes | Code | Text | Tables | Other data | Fill |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Resident code (`$0B00`, `$3500`, `$4A00`, `$8C00`, `$A000`, `$C92C`) | 6 | 27,492 | 16,529 | 3,607 | 432 | 6,645 | 279 |
| Overlays (`ST`, `EN`, `CM`, `C3` × 3, `GO`, `91`–`96`) | 13 | 35,710 | 20,048 | 11,143 | 102 | 3,708 | 709 |
| Area files | 55 | 97,680 | 31,158 | 26,772 | 34,236 | 4,792 | 722 |
| Start-up (title program, start-up stub) | 2 | 4,480 | 3,527 | 33 | – | 857 | 63 |
| Data files (pictures, font, roster, title screens) | 33 | 106,333 | – | – | – | – | – |
| **Total** | **109** | **271,695** | **71,262** | 41,555 | 34,770 | 16,002 | 1,773 |

The title program was read on 2026-10-12 and now runs on the Atari: [TITLE.md](TITLE.md). Its "title screens" are ten packed pictures and four colour matrices; this inventory lists the first two pictures, [C64-LOADER.md](C64-LOADER.md) all of them.

"Tables" are the parts whose layout is known: the area files' two map grids, their 50 data bytes and event tables, and tables of code addresses. "Other data" is everything not yet typed: mostly item, spell and monster tables in the resident blocks. "Text" is found by its look (upper-case ASCII, 13 for a new line, 0 to end), not from the code that prints it.

Per-file figures, hashes and sources are in [c64-code-map.json](c64-code-map.json) under `modules`.

### Things this settled about the files

- **The block at `$3500` is combat code.** It calls 30-odd addresses inside the combat file `CM` and the three jumps at the start of `C3`. It is loaded once at start-up and stays.
- **The block at `$4A00` looks like the trap code** for opening treasure. That is judged from its texts ("A SWARM", "POISONOUS", "SPRING FORTH!"); the code has not been read.
- **`$8C00` and `$C92C` hold no code.** They are tables: item names and other strings, and numbers.
- **`C3` is the same code on sides B, C and D.** Only the last 10 bytes differ, and side B's copy is 33 bytes longer.
- **`8A`–`8D`, `8P`, `1C`, `7N` and `BB` are packed pictures.** Each starts with a length word and uses `$7B` to mark a run. This is judged from the bytes; the unpacker has not been read. The loader notes had them as files with no text and no known use.
- **Two later loads overwrite part of an earlier one.** The `$4A00` block replaces the last 494 bytes of the `$3500` block, and the file table at `$4700–$48FF` lands inside it too. No traced code lies in either overlap.

## How the code was found

`tools/code6502.py` follows instructions from known entry addresses and marks what it reaches. `tools/disassemble.py` supplies the entries and repeats until nothing new turns up. An overlay is traced together with the resident code, so a call from an overlay into the resident code becomes an entry there.

| Entry kind | Count | Where it comes from |
| --- | --- | --- |
| Address tables | 868 | The dispatch idiom below; 54 area files' event tables and 9 others |
| Jump tables | 119 | Rows of `JMP` at `$0B00` (48), `$A000` (53) and the start of `CM`, `C3` and `GO` |
| Area entry `$8432` | 55 | Resident code jumps to it after a move, when bit 7 of `$38` is set |
| Calls from another file | 35 | For example the 30-odd calls from `$3500` into `CM` |
| Load addresses | 10 | Files that are entered at their first byte |
| Unreferenced | 12 | Read by eye; see below |
| Interrupt handlers | 2 | Two immediates stored to `$0314/$0315` |

**The dispatch idiom.** Wherever the game picks a routine from a table it writes the address into the operand of a `JSR` or `JMP`:

```
LDA low,X  / STA op+1 / LDA high,X / STA op+2 / … / op: JSR $0000
```

The tracer recognises this, reads both tables and takes their length from the distance between them. It finds 60 such tables. Three more keep low and high bytes together (`$14C0`, `$ACE9`, and `$20A8` in `CM`) and need their length given in `hints.txt`.

| Table | Entries | Selects |
| --- | --- | --- |
| `$14C0` | 13 | Play-mode command for a key (keys at `$14B3`) |
| `$B6EF` / `$B74D` | 94 | Spell handler outside combat |
| `$3C6F` / `$3CCD` | 94 | Spell handler in combat |
| `$3F74` / `$3F7C` | 8 | Eight entries four bytes apart in `CM` |
| `$ACE9` | 7 | The game's only `JMP (indirect)`, at `$ACC8` |
| `$20A8` in `CM` | 12 | Combat command for a key (keys at `$209C`) |
| `$2CA2` / `$2CC2` in `CM` | 32 | Handler chosen by a monster byte |
| `$3139` / `$3140` in `CM` | 7 | Not examined |
| `$4F93` / `$4FAC` in `C3` | 25 | Called from `CM` at `$2966`; not examined |
| Event tables in area files | 54 | Handler for the party's square and facing |

**Branches that always go one way.** A branch right after `LDA #0`, `CLC`, `SEC` or the opposite branch is always or never taken. The tracer does not walk the dead side. Without this rule one path ran on into the `INSERT DISK` text after a `BNE`/`BEQ` pair at `$C529`, and some table-reached routines were found only by accident, which hid that their tables were missing.

### What a static trace cannot promise

- **A routine reached only by a computed address it does not recognise** would be missed. Every `JMP (indirect)` and every write into a `JSR`/`JMP` operand in the traced code is accounted for, and no return-address trick (`PHA / PHA / RTS`) occurs. A search of the untraced bytes for calls to known routines turned up two short unreferenced routines (now in the list below); the remaining 23 matches are text and table bytes that happen to contain `$20`, and two cut-off leftovers at the ends of files.
- **Text can be mistaken for code only where a traced path leads into it.** No path does: there are no tracing problems left (no undocumented opcode, no `BRK`, no instruction overlapping another).
- **Checked against the recorded runs:** all 16 call sites of the disk loader that the five traces saw inside game files are traced instructions in the right file. Fifteen call the loader directly; the save calls a routine in `GO` that jumps to it.
- **Checked against the area tool:** the event handlers this trace finds in 54 area files are the same set `tools/area.py` reads from them by pattern matching, which was written separately in Phase 0. The tool fails if they ever differ.

### Code that nothing reaches

Twelve routines are plainly code but have no caller, jump, branch or table entry anywhere on the four sides.

| File | Address | What it is |
| --- | --- | --- |
| Title program | `$417B`, `$41CE` | Clear the colour RAM (two copies) |
| Start-up stub | `$2120` | The same routine again |
| `EN` | `$28E9` | **190 bytes that talk to the drive through the KERNAL** (`SETLFS`, `OPEN`, `CHKOUT`, `CHRIN`, …). The only KERNAL file calls in the game |
| `$3500` block | `$3502`, `$3D2B`, `$3DCD`, `$46B1` | Combat display helpers; `$46B1` calls `$3DCD`; `$3D2B` is one `JSR` in front of a used entry |
| Area `DM` (side B) | `$8B47` | Five instructions at the end of the file |
| `CM` | `$33AB`, `$33BE` | A longer variant of a used entry; a lone `JMP` |
| `$A000` block | `$C91A` | A second copy of the Y/N reader at `$C909` |

They are disassembled as code and listed under `unreferenced_code` in the code map. The port can leave them out, the KERNAL one in particular.

Two more stretches look like code but run off the end of their file in the middle of an instruction (`$4E87` in the `$4A00` block, `$5BD5` in `C3`). They are leftovers after the real end and stay data.

## Rebuilding

For each of the 76 code files the tool writes a da65 info file (code/data ranges, table types, names), then runs `da65`, `ca65 -t none` and `ld65` and compares the result with the original. **All 76 match on every byte.** The loader pieces and the bootstrap were already rebuilt in Phase 0 (`tools/rebuild_loader.py`, `tools/rebuild_boot.py`).

A rebuild proves the listing is a faithful copy. It does not prove a label is well named or that a data range is not really code; the tracing above is the argument for the split.

The 33 data files are not turned into source. Their hashes are in the code map.

## What ties the code to the C64

Every operand of every traced instruction was sorted by address. Immediate values are not operands in this sense; see "Through pointers" below.

| Category | Addresses | Uses | In resident code | In overlays | In area files | In start-up |
| --- | --- | --- | --- | --- | --- | --- |
| Disk loader `$9D00–$9D10` | 10 | 140 | 19 | 24 | – | 97 |
| Text screen `$0400–$07FF` | 32 | 77 | 16 | 37 | 14 | 10 |
| VIC-II | 8 | 36 | 23 | – | – | 13 |
| KERNAL variables | 11 | 32 | 13 | 3 | 1 | 15 |
| KERNAL calls and RAM under ROM | 14 | 29 | 1 | 18 | 1 | 9 |
| Colour RAM | 9 | 22 | 6 | 4 | – | 12 |
| SID | 10 | 17 | 6 | – | – | 11 |
| CPU port `$00/$01` | 2 | 15 | 1 | 7 | – | 7 |
| CIA | 3 | 7 | 4 | – | – | 3 |
| Lower-screen colours `$CC00–$CFFF` | 6 | 7 | 3 | – | – | 4 |
| **Total** | **105** | **382** | 92 | 93 | 16 | 181 |

The start-up column is the title program and the start-up stub, which the port replaces whole. That leaves **201 operands** in code the port keeps. An indexed operand one below a region (`STA $D7FF,X`) is counted with the region it reaches.

What each is used for:

- **Disk.** Seven parameter bytes and three calls (`read`, `write`, `set VIC bank`). Outside start-up the callers are two resident routines, `EN` twice and `GO` once, as Phase 0 found.
- **VIC-II.** `$D011`, `$D012`, `$D016`, `$D018`, `$D019`, `$D01A` in the resident code: the raster split between the two bitmaps and its interrupt. Border and background colour are set only at start-up.
- **SID.** `$D400`, `$D401`, `$D404`, `$D418`, all in the `$A000` block between `$C557` and `$C633`. All sound in play starts at **one entry, `$A02D`** (effect number in A), called from 106 places.
- **CIA.** `$DD00`/`$DD02` for the VIC bank, `$DC0D` once to change the timer interrupt.
- **KERNAL.** One routine in the kept code: `GETIN`, called at `$C648` and once from area file `DP`. (The 18 calls counted under overlays are 14 in `EN`'s unreferenced code and 4 accesses to the NMI vector in `CM`.) Variables: the jiffy clock `$A1/$A2`, the key count `$C6`, key repeat and shift flags `$028A–$028E`, the interrupt vector `$0314`.
- **Text screen.** Direct stores into `$0400–$07FF`. In play this memory is the colour matrix of the upper bitmap, so most of these are colour changes, not text.
- **RAM under ROM.** `CM` and the title program copy the NMI vector at `$FFFA` after switching the KERNAL out.

The full list, with every site, is `machine` in [c64-code-map.json](c64-code-map.json). `machine_routines` groups the sites by subroutine: **106 routines**, 26 in resident code, 36 in overlays, 14 in area files and 30 in start-up.

### The resident routines that do it

Read from the listings on 2026-10-10; none of this has been exercised separately in the emulator.

| Routine | Does |
| --- | --- |
| `show_text` `$1BC7` | Text mode, `display_mode` 0 |
| `show_bitmaps` `$1BF1` | Multicolour bitmap mode, `display_mode` 1 or 2 |
| `irq_install` `$C590` | Raster interrupt on, **CIA timer interrupt off**, old vector kept for chaining |
| `irq_handler` `$C5C5` | In mode 2: bank 0 and `$D018 = $18` from line 0, bank 3 and `$38` from line `$B0`. In mode 1: bank 3 for the whole frame. Then one step of the sound, then on to the KERNAL's handler |
| `set_vic_bank_bits` `$C40D` | The two bank bits, written through the loader's entry |
| `text_clear` `$0E55`, `color_ram_fill` `$1C18`, `play_colors` `$C276` | Fill the screen matrix and colour RAM |
| `copy_view_down` `$0DFD` | Copies the upper bitmap and its colours to the lower screen's memory |
| `draw_picture` `$C2C0`, `unpack_byte` `$C31F` | Unpack a picture from `$3002` to the lower bitmap; `$7B`, count, value is a run |
| `sound` `$C557`, `sound_step` `$C60C`, `sound_off` `$C62F` | One voice; an effect is a list of four-byte steps |
| `get_key` `$C648` | `GETIN`, then stops the sound, maps shifted punctuation and applies its own repeat delay |
| `pause` `$C355` | Waits on the KERNAL clock or for a key |
| `load_file` `$C499`, `load_file_table` `$C4DC`, `find_file` `$C445` | Every read of a named file and of the file table in play (`EN` makes its two block reads itself) |

**The KERNAL clock runs off the raster interrupt.** With the CIA timer interrupt off, the KERNAL's handler (keyboard scan and clock) is reached only by chaining from `irq_handler`. In split mode that is twice a frame, otherwise once. So the length of a `pause` in real time depends on the display mode. *Read, not measured.*

**The 3-D view** is drawn by about 1 KB of resident code at `$0F1D–$135F`, found on the oracle by counting which instructions run during one step (a step is about 35,000 instructions; this code is over 80% of them).

| Routine | Does |
| --- | --- |
| `draw_view` `$0F1D` | Jump-table entry `$0B5D`, 51 callers. Sets `party_square` from `party_x`/`party_y`, fetches the square's wall and state bytes, then draws the visible pieces |
| `draw_wall_piece` `$1111` | Called from seven places in `draw_view`. Copies one piece from a picture set into the view page; the three sets are `$1120` bytes apart |
| `clear_view` `$1F36` | Zeroes 16 rows of 30 columns |

**The view is page-flipped.** `view_page` (`$07`) names the bitmap the next view is drawn into, `$E000` or `$2000`, from the table at `$0C90`. After drawing, the game flips `view_page` and calls `show_bitmaps`, which sets `display_mode` 1 or 2 to show the page just drawn; both pages end up current. *Checked on the oracle:* over four moves `$07` alternated `$40`/`$60` and `display_mode` 2/1. So play does not sit in the split mode; it alternates with the whole-frame mode on every redraw.

Which piece goes where (the geometry in `draw_view`) has not been read.

### Through pointers

Most drawing goes through zero-page pointers, which no operand shows. The tracer lists where a pointer is aimed with two immediates (`LDA #low / STA p / LDA #high / STA p+1`) at screen, bitmap or colour memory: 18 targets, among them `$2000` and `$E000` (the bitmaps), `$D800` and `$CC58` (colours) and `$E2C0`. They are under `pointer_constants`. **This list is a lead, not a proof:** a pointer can also be computed. The routines that hold these constants (`$0DFD`, `$C137` and a few in `EN` and `CM`) are where the drawing code has to be read in full.

### Keys, time and sound, from the code

These answer questions the runtime notes left open.

- **Where keys are read.** 299 calls go through the key wait's jump at `$0B18` and 8 call it directly. Besides that, `GETIN` is reached from the pause routine, from two area files on side D through `$A087` (`IF` at `$89F0`, `EH` at `$86D2`), and directly from one (`DP` at `$890E`). Those three areas are the only play-time code that reads a key without stirring the random numbers.
- **Pauses read the KERNAL clock.** `$A036` → `$C355` waits A × 32 jiffies or until a key is pressed, and clears the key buffer first. It has 31 callers. A host reference needs a rule for this as it does for key waits.
- **Random numbers** are requested through `$0B15` from 215 places and from one more inside the resident code.

### A quirk in two area files

The count byte in front of the event tables says how many squares to search. In 52 of the 54 files that have tables it equals the tables' length. In Sorpigal (`EG`) it is 26 for 24 entries, and in `BC` on side D it is 20 for 15. The search would then read the first bytes of the next table as two (or five) more squares. *Read from the files; not tried in the emulator.* It matters to the port only in that the original data must be kept as it is.

## Names

[symbols.txt](../source/c64/game/symbols.txt) names 113 addresses: the hardware registers and KERNAL variables above, the loader's parameters and entries, the zero-page variables established in Phase 0, and the resident routines whose behaviour is traced, checked or read (key wait, random numbers, the printers, area change, file loading, pause, sound, the display switches and the interrupt handler). All other labels are da65's `Lxxxx`.

Naming is deliberately conservative: a name goes in only when its meaning is known, with the evidence in the runtime notes or here.

## Not done

- **Most routines are unnamed.** 101 resident jump-table entries exist and 16 have names. The listings are complete and correct but not yet readable as a program.
- **The 3-D view code is located and its three routines named, but its geometry is not read**, and the bitmap text printers are named but not read line by line.
- **The machine routines in overlays and area files (50 of them) are listed, not read.** Most are stores into the colour matrix at `$0400`.
- **"Other data" (16 KB) is untyped:** item, spell and monster-ability tables in the resident blocks, and tables inside overlays.
- **Text is found by its look.** Linking each string to the code that prints it would type the text exactly and name the strings.
- **The 50 data bytes of an area file** are named as a block; only bytes 8–19 are understood.
- **Original_v1** has not been run through any of this.
