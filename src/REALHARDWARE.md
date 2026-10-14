# Running on real hardware: Atari 130XE and a 1050 drive

Written 2026-10-12 on the branch `changed-game-binary`, at the end of a session that began as a graphics-speed investigation and turned into a real-hardware disk study. **Update 2026-10-13: the four-disk layout of section 2 is now built, as `build.py --disks`, with a different unpacker and a different answer to the memory problem (section 10, [docs/DISKS.md](docs/DISKS.md)).** What follows was written before that, and is left as it was, apart from section 10 and the notes there. Originally: nothing described here was implemented; the only code added was a ZX0 decoder spike and host-side analysis scripts. All numbers come from the host (the oracle, the built ATR, Python compressors), not from real hardware. Real-drive timing, disk-change detection and 1050 sector numbering are untested.

Contents: 10. Four disks built (added 2026-10-13, read this first). 1. Where we stand and what to do next. 2. The disk problem and layout. 3. The ZX0 decoder spike. 4. The disk-read survey. 5. Open problems (5a: questions for the owner). 6. Plan. 7. Graphics-speed investigation (the other thread of this session). 8. Files and how to rerun. 9. Corrections to things I said earlier.

## 1. Where we stand, and what to do next

- **Target:** Atari 130XE with a stock 1050 in enhanced density: 1,040 sectors of 128 bytes, 133,120 bytes a disk. (The 180 KB double-density format needs a modified 1050 or an XF551; out of scope.)
- **Verdict so far:** four disks with per-item ZX0 compression fit (73-78% full). A 6502 decoder is small (193 bytes) and works. **The unsolved part is where the decoder and a ~3.7 KB staging buffer live in memory**, and how to decode without overrunning the destination.
- **Next step I recommended:** test the upper bitmap region (`$2000-$34FF`) properly as a staging area, with the clobber limited so it doesn't destroy overlay code that is running. The first attempt hung (section 4.4).
- **Other open decision:** the graphics speed work (section 7) stopped at "idea 2, pointer advance, about one frame per step", awaiting a choice between options A, B and C.

## 2. The disk problem and layout

### 2.1 The problem

The current ATR is 724,736 bytes of sector data: 56 boot sectors, then five 170 KB images. Four are the C64's disk sides (664 blocks of 256 bytes, 169,984 bytes each). The fifth is a 147-block memory image the boot code loads. A 130 KB disk is smaller than one C64 side, so the current layout cannot go on real disks.

(`build/atari/mm1.atr` is 724,752 bytes with its 16-byte header. The title build `mm1-title.atr` is 726,800 bytes. Both were just rebuilt or stale; see the rebuild note in section 8.)

The C64 game already spans four disks (A boot and title, B, C, D) and asks for them with its own "INSERT DISK x" prompt. The Atari kernel hides this: when the game reads a file table, `kernel.s:160-169` copies the wanted side from `WANTED_SIDE` (`$C54D`) into `side`, so one big ATR serves every side. The first prompt remains as a "press RETURN" screen. `docs/ATARI-DESIGN.md` line 30 records "no disk swapping".

The game compares the side number at `$48FF` with the one it wants and repeats "INSERT DISK x" until they agree. The header ID plays no part (it is `00` everywhere). See `docs/C64-LOADER.md`.

### 2.2 What each side needs

I counted every block the game can read: its files, the 77 monster pictures, the monster records (blocks `$165-$17D`) and the file table (`$296-$297`). A 130 KB disk holds 520 blocks of 256 bytes.

| Side | Blocks needed | Fits 520? |
| --- | ---: | --- |
| A (boot, title) | 27 | yes |
| B | 622 | no, 102 over |
| C | 604 | no, 84 over |
| D | 613 | no, 93 over |

Per side: B has 36 files, C 37, D 39; all have 77 monster pictures (251 blocks). Pictures overlap files by 12-15 blocks.

Things that do not close the gap:

- Dropping unreferenced blocks or the overlaps saves under 60 blocks per side.
- B, C and D share about 320 identical nonblank blocks each (B=C 320, B=D 319, C=D 340; 1,230 distinct against 1,844 total), but sharing would need the game to read from a common disk.
- Side A's 154 unreferenced blocks are probably leftovers of earlier builds (`docs/C64-LOADER.md`); side A is small either way.
- Whole-side compression is not usable: the game reads item by item (section 4).
- Unexplained blocks per side, for completeness: B 40 blocks (zlib 2,688 bytes), C 44 (2,142), D 14 (575).

Rejected: about 7 disks with no compression. It would need new swap prompts in the middle of play, which the game does not have.

### 2.3 Layout: four disks, each item compressed

Keep four disks so the game's swap prompts stay as they are. Compress each file and picture separately with ZX0. Store the monster records and the file table raw.

First estimate, everything compressed, each item padded to 128-byte sectors:

| Side | Raw bytes | ZX0 bytes | Sectors | Of 1,040 |
| --- | ---: | ---: | ---: | ---: |
| B | 158,505 | 92,133 | 774 | 74% |
| C | 152,972 | 88,054 | 743 | 71% |
| D | 155,926 | 87,839 | 740 | 71% |

**Revised after the survey** (monster records raw, file table raw, `RO` raw, plus about 6 sectors of index; `analyze.py sizes` reproduces this):

| Side | Sectors | Of 1,040 | Largest compressed item |
| --- | ---: | ---: | --- |
| B | 809 | 78% | `CM`, 3,746 bytes |
| C | 763 | 73% | `CM`, 3,746 bytes |
| D | 762 | 73% | `CM`, 3,746 bytes |

(Whole-run zlib, which the game cannot use, would give about 71-77 KB a side. lzma about 62-68 KB. The ZX0 numbers use exact file lengths; an earlier zlib figure rounded to whole blocks, which is why ZX0 looked better than zlib.)

The raw monster records cost 50 sectors a side. Compressing them per 256-byte block does not help: 5,025 bytes against 6,400, which pads back to 6,400. Compressed as one item they are 3,992 bytes, but the game reads them one block at a time (section 4.1).

## 3. The ZX0 decoder spike

Source: `port/atari/zx0/zx0.s`, `zx0.cfg`. Host tests: `run.py` (single items), `full.py SIDE` (a whole side), `ref.py` (Python reference decoder). The scripts need the PyPI `zx0` package and `zx0.bin`, built with `ca65`/`ld65` from `zx0.cfg`. `zx0.bin` is not committed.

- **Correct.** Decoded all 344 items of sides B, C and D (114, 114, 116 items; files, 77 pictures, monster records) byte-for-byte on `tools/mos6502.py`.
- **Size.** 193 bytes including about 30 bytes of helper routines. About 12 zero-page bytes: `$E8-$EC` and `$F8-$FF` in the spike (the real kernel already uses `$F0-$F7`, so these must be moved).
- **Speed.** About 117-120 cycles per output byte on average (62 for highly repetitive data, up to 150 for short items). Slowest item: the 6,400-byte monster records at about 870,000 cycles (about 0.5 s). A 2 KB area file takes about 0.14 s. Totals per side: B 18.9M, C 18.1M, D 18.2M cycles for every item once. Reading the sectors from a 1050 will take longer than unpacking.
- **Staging buffer.** Largest compressed item: `CM` at 3,746 bytes (3,992 bytes was the monster records as one item, which will be stored raw). A compressed item must be read somewhere before it is unpacked. The loader's 128-byte bounce buffer is too small.
- **Format.** The PyPI package writes ZX0 v2 with every Elias-gamma data bit inverted, and the first literal indicator bit implicit. `zx0_compress` returns `(data, stats)`, not bytes, and prints a lot of progress output. It takes about 75 seconds a side, so a build step must silence it and cache the results.
- **Bugs fixed on the way** (both mine): (1) I measured the length of the returned tuple and got "230 bytes, 11%"; (2) the decoder's gamma loop used `bcc` after `rol mhi`, but carry is always set there because m is `$FFxx`, so everything hung; replaced with `jmp`.
- **Not in the spike:** `.org $0800` and a `.export` line are left over and must go when it moves into the kernel. The host test calls it from a stub.
- **Not tried:** ZX0 backward mode; ZX0 in-place decode into the destination (section 4.5); anything on real hardware.

## 4. The disk-read survey

Method: replayed 22 recorded sessions (`tools/traces/*.txt`, minus `capture-entry` and the unsupported `snapshot` script) on the host oracle and logged every call to the loader entries `$9D0D` (read) and `$9D10` (write). 596 calls in total, including 230 on side A (boot and title).

### 4.1 What the game reads

- **Whole items:** on sides B-D nearly every read starts at the first block of an item, offset 0: 294 files whole, 14 pictures whole, 33 file tables whole. No read had a nonzero offset.
- **Monster records:** read one 256-byte block at a time to `$2D00` (blocks `$165`, `$166`/`$169`, ...). 14 reads on B-D; 10 are "prefix of the item" in my classifier, the rest are neighbouring blocks. They cannot be treated as one item.
- **Partial pictures:** 8 picture reads were shorter than my table's item length (for example `$DC` read 811 of 1,024 bytes, `$E0` 675 of 768): the table is in whole blocks, the game reads the exact length. Compress by exact length.
- **One item, two destinations:** side C block 507 (`LL`/`NB` style 4,384-byte picture sets) is read to both `$4EA0` and `$70E0`. The index must map items to data only; the caller supplies the destination.
- **Destinations seen:** `$2000`, `$2800`, `$3000`, `$2D00`, `$4700`, `$4EA0`, `$5FC0`, `$6000`, `$6900`, `$70E0`, `$8200`.
- **By display mode at call time** (sides B-D): 176 reads in text mode (`display_mode` 0), 187 in bitmap mode, plus the 3 saves in text mode.
- **Read classes (destination, mode, count, largest length):**
  - area files and overlays to `$2000`: 24 bitmap-mode (max 2,486), 12 text-mode (`CM`, 5,376);
  - `$2800` 4 and `$3000` 7+14 pictures, bitmap mode;
  - monster records `$2D00`, 14 reads of 256 bytes;
  - file table `$4700`, 512 bytes: 24 text-mode, 9 bitmap-mode;
  - picture sets (4,384 bytes) to `$4EA0`, `$5FC0`, `$70E0`, both modes;
  - `RO` to `$6000` (2,304 bytes, text) and `GO` to `$6900` (5,786, text), 24 each;
  - area files to `$8200` (up to 2,559), 20 text-mode and 34 bitmap-mode.
- **Save:** only the roster is written: 3 writes of `$0900` bytes from `$6000` (side B block `$152`), at text-mode time. The kernel writes whole sectors only (18 from `$6000`).
- **Assumption not proven:** the recorded sessions are a sample; an unrecorded path could read partially or by another route.

### 4.2 Memory the game never touches

I hooked the host 6502 core's read, write and opcode-fetch paths and merged the result of 22 sessions. Ranges of 64+ bytes in `$0200-$CFFF` never read, written or executed (about 10.7 KB total):

`$0200-$0276` 119, `$0292-$0313` 130, `$03AE-$03FD` 80, `$13FD-$146A` 110, `$180B-$18FA` 240, `$1995-$1B1C` 392, `$1C40-$1D0F` 208, `$1DFD-$1EDD` 225, `$3FA5-$3FFF` 91, `$8821-$8900` 224, `$8AE4-$8B3F` 92, `$8B51-$8BFF` 175, `$8D65-$8DB9` 85, **`$95FE-$9CFF` 1,794**, `$9D26-$9E39` 276, `$9E68-$9FBC` 341, `$9FBE-$A002` 69, `$A141-$A235` 245, `$A684-$A938` 693, `$A9C6-$AA2E` 105, `$AA39-$AA93` 91, `$AB09-$AB9F` 151, **`$ABD4-$B1C2` 1,519**, `$B1E4-$B235` 82, `$B264-$B478` 533, `$B495-$B4DA` 70, `$B725-$B781` 93, **`$B783-$BAFA` 888**, `$BB07-$BB99` 147, **`$BCA5-$C023` 895**, `$C161-$C275` 277, `$C4F7-$C54C` 86, `$C7DA-$C85C` 131, `$C962-$C9B8` 87.

Caveats: this is what 22 sessions did not touch, not proof. Many of these ranges hold data that was loaded and simply not read (for example `$95FE-$9CFE` has 1,409 nonzero bytes, `$ABD4-$B1C1` has 1,478), so they are table or text space the game may use elsewhere. `$9D26-$9E39` is the C64 loader (`docs/64K-NOTES.md` lists `$9D26-$9FFF` as free for Atari code, but the kernel already uses part of it). Zero page: the game uses everything except `$00`/`$01`.

### 4.3 What the free-memory finding means

No range is both large (3.7 KB) and proven free. The largest, `$95FE-$9CFF` (1.8 KB), is not enough. See 4.4 for the regions that are free only during loads.

### 4.4 Clobber experiment: which memory can be overwritten at load time

Idea: at each text-mode read, overwrite a region with `$A5` before the load and see whether the game behaves identically (same events, same code and data memory at every mark). If so, that region is free as a staging buffer while the game is in text mode.

Results (`port/atari/survey/clobber-results/`, one file per run):

| Region | Finished | Identical | Verdict |
| --- | ---: | ---: | --- |
| `$CC00-$CFE7` lower colour matrix | 21 | 21 | Safe, but only 1,000 bytes |
| `$E000-$FF3F` lower bitmap | 20 | 14 | **Not safe.** Events differed in 5 sessions (chest-trap-failure, chest-traps, death-and-raising, fight-and-save, treasure-and-reload), and memory differed in a 6th (wilderness-travel) even with the same events. The game keeps data there across text-mode reads (mostly after fights, in chests and the inn) |
| `$2000-$34FF` upper bitmap | 0 | - | **No result.** All 7 runs hung, as did one `bitmap_lo` run (`boot-to-death`). Probably the clobber overwrote overlay code that was still executing, since `CM` loads to `$2000` in text mode. I killed them after more than 7 minutes. Needs a narrower experiment |

The `matrix_lo` result is the only clean "free" finding. Its limits: it only proves the game does not need those bytes while a text-mode read is in progress, in these 22 sessions.

Practical note: clobber runs are about 10 times slower than a normal replay (two replays each, hooked core). Run them in the background, one output file per job (`runall.sh`), because a 30-minute foreground timeout killed my first attempt, and `pkill -f` matched my own shell.

### 4.5 In-place decoding

ZX0 reports a "delta" for each item: how far the compressed data may need to extend past the end of the output for in-place decode. On side B the delta is 6-115 bytes over 114 items (median about 16). Decoding straight into the destination, with the compressed data placed at the end of the output buffer, would therefore overrun the destination by up to 115 bytes, onto whatever follows. For example, `$8200` area files end near the tables at `$8C00`; `$4EA0` picture sets (4,384 bytes) end at `$5FC0`, where the next set starts. Not tried: backward-mode ZX0, or tail placement that stays inside the destination plus a known gap.

### 4.6 The 130XE bank window problem

The kernel selects banks through PORTB: `PB_GAME $D2` (CPU on main memory, OS out), `PB_GAME_EXT $C2` (CPU on the extended bank), `PB_OS $D3`, `PB_OS_EXT $C3`. The extended bank is visible only in `$4000-$7FFF`. Most load destinations (`$4700`, `$4EA0`, `$5FC0`, `$6000`, `$6900`, `$70E0`) lie inside that window. So compressed data cannot sit in an extended bank while output is written to main memory in the same range. A staging buffer in an extended bank also means ANTIC must not read the picture during loads: the PORTB bank bits are shared between CPU and ANTIC (`docs/GRAPHICS-PERFORMANCE.md` line 273: "a second-bank cache read while ANTIC remains on bank 0 is invalid"). The kernel today blanks DMA only for bitmap screens; text screens stay on. A staging buffer in plain main memory outside `$4000-$7FFF` avoids both problems; none was found yet.

## 5. Open problems

1. **Staging buffer and decoder placement.** Need about 3.75 KB for compressed data and about 200 bytes for code plus zero page. Free space now: LOADER 5 bytes, UNDER 2, EXT 7, EXT2 1 (from `build/atari/*.bin` trailing zeros; the docs say spare 5 / 1 / 0 / 3). The extended bank is full. Candidates:
   - the lower colour matrix `$CC00-$CFE7` (1,000 bytes, verified safe) plus other regions: not enough alone;
   - the upper bitmap `$2000-$34FF` (5 KB) in text mode: untested, see 4.4;
   - the game's unreferenced routines (about 500 bytes, `docs/64K-NOTES.md`), which is another change to the game binary, allowed on this branch;
   - decode in pieces: read a few sectors at a time into a small buffer and feed the decoder from it (a streaming decoder), so only about 256 bytes of staging are needed. This changes the decoder (it must refill its input pointer) and slows loads. Not explored; probably the best option.
2. **In-place overrun** (4.5).
3. **Read patterns.** Unrecorded paths might read partially (4.1).
4. **The save.** The roster write needs an uncompressed area on whichever disk is in the drive, and the game's own side logic decides which. The write is 18 sectors from `$6000`, raw.
5. **Sector numbering on a real 1050.** The kernel reads 128-byte sectors, two per block. The boot disk's 56 boot sectors and the first three sectors need checking against real 1050 numbering and boot rules.
6. **Disk-change detection.** A 1050 does not signal a disk change cleanly; the game's prompt compares the side number from the file table. Untested.
7. **Timing.** At standard SIO speed a 3 KB compressed item takes about 1.5 s to read (an estimate). Decompression adds about 10-30% on top, partly offset by reading fewer sectors.
8. **The index.** Maps (side, block, length) to a compressed item; must handle the one-item-two-destinations case, partial lengths and the per-block monster reads.
9. **A stock 1050 in single density** holds only 90 KB a disk; that would need a different layout.
10. **130XE-only features.** The picture buffer relies on ANTIC bank selection, which many third-party memory upgrades lack (`docs/ATARI-DESIGN.md`).
11. **Boot disk.** Side A has the 147-block memory image (about 37 KB, 13 KB compressed) plus boot sectors; about 14 KB is free if side A keeps its 154 blocks, more if the unreferenced blocks are dropped.

## 5a. What I need to know (questions for the owner)

Decisions:

1. **Can the game binary change to free memory?** This branch allows it. Removing the unreferenced routines (about 500 bytes, `docs/C64-CODE.md`, "Code that nothing reaches") or other unread code would buy room for the decoder and loader changes. Without it, code space is the limit.
2. **Is a streaming decoder acceptable?** It reads a few sectors at a time into a small buffer (about 256 bytes) instead of staging a whole 3.7 KB item. It needs only a little memory, but it changes the decoder and slows loads a little.
3. **Which drive do you actually have?** I assumed a stock 1050 in enhanced density (1,040 x 128 bytes). If it has a speed-up or double-density upgrade, the layout changes.
4. **Is a 130XE with real ANTIC bank selection the only target?** Many third-party memory upgrades lack it. Supporting them is a separate design (`docs/64K-NOTES.md`).
5. **Graphics speed (section 7.4): A, B or C?** A: implement the pointer-advance idea (about one frame a step). B: skip no-change refreshes (needs code space first, so it depends on question 1). C: stop, since this converter is near its limit.
6. **Is losing the byte-for-byte match with the oracle acceptable** for the changed-binary work? The existing checks compare Atari memory with the oracle's, and a changed binary breaks that.

Facts I could not establish from the host and want checked:

- Whether any game path reads a disk item partially or by another route than the recorded sessions (section 4.1).
- Whether the upper bitmap `$2000-$34FF` is free as a staging area during text-mode loads. My clobber run hung, so I have no result (section 4.4).
- Real 1050 behaviour: sector numbering at boot, disk-change detection and the time to read a 3 KB item. I used an estimate of 1.5 s.
- Whether the roster save can stay raw on the disk the player has in the drive when the game saves.

## 6. Plan

1. Settle where the decoder and buffer go (test the upper bitmap with a narrow clobber; consider a streaming decoder).
2. Build four 1,040-sector images and an index mapping each read to a compressed item.
3. Add the decompressor to the kernel's read path.
4. Remove the `WANTED_SIDE` bypass so the game's own "INSERT DISK x" runs, and map "side" to whichever disk is in the drive.
5. Test swapping in the emulator by changing the mounted disk image at the prompt (needs a small harness change).
6. Check the save, then test on real hardware.

## 7. Graphics-speed investigation (earlier in the session)

Goal: close the gap to the C64 (a step takes about 484 ms against 130-143 ms). Method: static read of `kernel.s` and the profiling harness, then measurements. **No speed change was implemented.**

### 7.1 Baseline (reproduced, unchanged tree)

`python3 port/atari/graphics_profile.py --out DIR` runs in about 4 s. Walking step: 29 frames, 616,740 elapsed conversion cycles, 323,314 CPU cycles. Turn left 29 frames (640,338 elapsed), turn right 29, choose-character 21 (616,284), enter-town 48 (500,688), character-sheet 6, back-to-town 24 (473,670). Elapsed is about 1.9 times CPU because ANTIC DMA and 500-515 row interrupts steal cycles. One frame is about 29,900 cycles, so about 15,000 saved CPU cycles is about one frame.

Where the 323k CPU cycles of a step go: palette 112k (34%), pixel lookup 90k (27%), unchanged-row compare 51k (15%), cell setup 38k (11%), pointer advance 29k (9%). Enter-town (455,767 total): palette 42%, pixels 33%, cell setup 13%, advance 10%. The row compare already pays: 51k cost against about 118k of conversion skipped on nine rows (16-24). In a step all 25 rows have changed palette inputs for rows 0-15.

### 7.2 Structure of the converter (`port/atari/src/kernel.s`)

`getin` (503) calls `refresh` on the first key poll after a gap of 2+ frames or when a key was taken. `refresh` (892) goes to `rf_text` (copy `$0400` to `PICTURE`) or `rf_bitmap` (25 rows). Per row: pointers, `choose_colours` (1224), `reuse_row` (1182, exact 320-byte compare, rows 16-24 only in practice). Per cell: read matrix byte, combine `pair[]`/`pair4[]` into one of 16 lookup pages (identity page `MAPS+9` jumps to `rf_identity`), patch four self-modified operands only when the page changes, `rf_lookup` (4-way unrolled `lda (source),y / tax / lda MAPS,x / sta (dest),y`, about 19 cycles a byte), `rf_advance` (carry-checked 16-bit adds for source, dest, matrix). In-place conversion into `PICTURE` ($4000) while ANTIC displays it; no double buffer. Free bytes: LOADER 5, UNDER 2, EXT 7, EXT2 1.

### 7.3 Direct display of the game's bitmaps (option 1): measured, not workable as hoped

Idea: show the game's C64 bitmaps in place, so no conversion. `docs/64K-NOTES.md` observes that 19 of 25 rows of `$E000` (and 12 of 16 of `$2000`) already sit on 1 KB boundaries usable as ANTIC character sets.

**Writers into the bitmaps** (host core hooked; one session, `boot-to-fight-and-save`): only about 13 resident instructions write bitmap memory: `$1F4F` clear_view (764,160 writes), `$11C2`/`$11F6` draw_wall_piece, `$0D3C` bitmap_putchar, `$0DF2`/`$0E13` copy_view_down, `$0C1A`, `$0C23`, `$0DBC`, `$0DC8`, `$0DD1`, `$0DD7`, `$C2F4` draw_picture. Most are `STA (zp),Y`, so the address arithmetic is in pointer set-up code. Other writes in the trace were overlays and title code. One session only; rare paths could add sites.

**The blocker is colour, not addresses.** An ANTIC mode 4 row has black plus three registers; pair `11` is one register, so only two colours per row are available for pairs `01` and `10`. Distinct colours in each row's screen-matrix nibbles: `boot-to-fight-and-save` 182 of 225 mark-rows need more than 2 (only 18 need 1 and 25 need 2); `boot-to-outdoors` 81 of 100. Typical 3D-view rows use 4, town rows 6-15. Recoding pictures on disk cannot fix this: matrix bytes are written by the game per drawn piece, and one piece appears on many rows. Only the text rows (bottom nine) are one or two colours, and those are the rows the existing row-reuse already skips.

Decision: abandoned in favour of option 1 below. Probes: `gfx_probes/rows.py`, `matrix.py`.

### 7.4 Option 1 (keep the converter, speed it up): analysis only

Measured facts and corrections:

- About 85% of cells have the same matrix byte as the previous cell (`gfx_probes/runs.py`: 78-88% per screen), so the existing lookup-page guard already captures most of the gain a smarter loop would.
- My first estimate (ideas 1-3 take 335 ms to 220-250 ms) was too optimistic. A realistic expectation is 1-3 frames (35-100 ms). The C64's 130-143 ms is out of reach with this converter.
- Candidate ideas, by cost per frame:
  1. **Skip refreshes that change nothing** (the `#` prompt takes 21 frames with zero pixel change; the game work is 0.45 ms). A checksum of bitmaps and matrices costs about 110k cycles (about 4 frames) and needs about 60 bytes. Does not help real steps. Risk: a weak checksum misses a change.
  2. **Cheaper pointer advance**, indexing within a page: about 15k CPU cycles, about one frame per step. Fiddly because a 320-byte row crosses a page. Needs bytes that do not exist.
  3. **Palette**: rows 0-5 have no cache; 360 bytes of cache would get few hits while walking.
  4. Better identity-mapping tie-break in `cc_pick`; a one-index-register copy loop (about 15 cycles a byte instead of 19).
- Code space is the real limit. One way to buy space on this branch is to remove the game's unreferenced routines (about 500 bytes), which changes the game binary.
- Awaiting a choice: **A** implement idea 2 and measure (about one frame), **B** implement idea 1 for no-change prompts (needs the space first), **C** stop; larger gains need a different approach.

## 8. Files and how to rerun

Committed to this branch:

- `REALHARDWARE.md`: this file.
- `port/atari/zx0/`: `zx0.s`, `zx0.cfg`, `ref.py`, `run.py`, `full.py`. Build: `ca65 zx0.s -o /tmp/zx0.o && ld65 -C zx0.cfg /tmp/zx0.o -o zx0.bin` using the toolchain at `shared_root()/tools/toolchain/local/bin` (`~/coding/wizardry_1/...`). Run: `python3 port/atari/zx0/run.py`, `python3 port/atari/zx0/full.py B`. Needs the `zx0` PyPI package (`pip install zx0` in a venv; I used `/tmp/opencode/zxenv`, which is temporary).
- `port/atari/survey/`: the survey. `collect.py NAME` (disk calls, writes `/tmp/opencode/survey/NAME.json`), `mode.py NAME` (display mode at each call), `touch.py NAME` (read/write/execute map, `touch-NAME.bin`), `clobber.py NAME REGION` (REGION is `bitmap_lo`, `matrix_lo` or `bitmap_hi`), `runall.sh` (clobber over all sessions, 8 in parallel, background), `inplace.py` (monster-record and ZX0 delta statistics, side B), `analyze.py reads|touched|sizes` (the analysis steps I ran inline). The scripts hard-code `/tmp/opencode/survey/` as the output directory; create it first. `clobber-results/` holds the 49 result files from my run (several empty ones are the hung runs).
- `port/atari/gfx_probes/`: `wtrace.py` (bitmap writers), `matrix.py` and `rows.py` (colours per row), `runs.py` (equal-neighbour cells), `zxsize.py` (ZX0 sizes per side).

All of them are run from the repo root and need the host oracle (`python3 tools/analyze_c64.py && python3 tools/mmdisk.py` first, per `docs/ORACLE.md`). The probes monkey-patch `tools/mos6502.py` at run time; they change nothing on disk.

Build note: I ran `python3 port/atari/build.py --test --no-title`, which regenerates files under `build/atari/` (ignored by git), including `mm1.atr`. That is now the test build without the title program, not the playable build.

Not committed (not mine, present before the session): `README.md` and `docs/PORTING-LOG.md` modifications, `POR.md`, `PORTING.md`, `opencode.json`, `porting.tgz`, its checksum, `tools/package_porting.py`, `tools/porting-kit/`.

Branch: `changed-game-binary`, branched from `11bb542` at the start of the session.

## 9. Corrections to things I said earlier

- I first claimed 13 bitmap writers made the "rewrite the address arithmetic" route small. That count was right, but I had not yet considered colour; the colour limit is what stops direct display (7.3).
- I estimated 220-250 ms for the cheap graphics ideas. Revised to 1-3 frames (7.4).
- I said ZX0 would compress worse than zlib. It did not (section 2.3); my zlib figure rounded to blocks.
- `CM` (the combat overlay) is 5,376 bytes raw and 3,746 compressed. Only the compressed size matters for the staging buffer.
- My first picture-hash comparison in `clobber.py` was wrong (it hashed an unusable object) and was replaced by hashing code and data memory at each mark.

## 10. Four disks built (added 2026-10-13)

What happened to the open items above ([docs/DISKS.md](docs/DISKS.md) has the detail):

- **Staging buffer and decoder placement (section 5, item 1): solved with a streaming decoder**, the option section 5 called "probably the best". A ZX02 decoder (the Wizardry port's adaptation of Serpell's 132-byte `zx02-optim`; ZX02 rather than ZX0 for its smaller decoder) takes its input a byte at a time from a 128-byte sector buffer, refilled from SIO as it runs dry. No 3.7 KB staging area, so the clobber experiments of 4.4 were not needed. The buffer is **in the stack page** (`$0100-$017F`): the game's stack pointer is `$F0` or more at every disk call measured. The decoder replaced the one-image kernel's disk code in the same 768 bytes, with five variables moved into the jump table's padding and `enter_game` moved to the boot code.
- **In-place overrun (item 2):** not an issue; the unpacker writes to the destination only up to the length asked for, and reads from its own buffer.
- **Read patterns (item 3):** the item set comes from the game's own tables, and every item of every disk is compared with the oracle's side after every recorded session (21 of them), so a path the sessions did not take is checked for what it would read; a read at a block that is no item's start returns status 8 and the game asks again.
- **The save (item 4):** the roster is stored raw, and the write goes to the sectors the index gives for block `$152`. Checked against the oracle's disk after three saves.
- **The index (item 8):** two bytes a block, 11 sectors at the end of every disk; one index sector read a call.
- **Disk-change detection (item 6):** the kernel does not track which disk is in the drive. The game's file-table check and its own prompt do; a failed or empty read returns status 8, which the game treats as the wrong disk. Checked with the disk image changed under a running emulator, in Atari800 and AltirraSDL, with the fast shortcut off.
- **Questions for the owner (5a):** (1) the game binary was **not** changed: only the operands pointed at the stand-in registers, as in the one-image build. (2) A streaming decoder: yes, done. (6) The byte-for-byte match with the oracle is kept: `lockstep.py --disks` passes on all 21 scripts, and the item-by-item comparison is stricter than the old whole-side one.
- **Still open: items 5, 7, 9 and 10** and the real drive (sector numbering, the first command after a swap, timing).

