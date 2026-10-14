# Might and Magic I → Atari: working specification

Updated 2026-10-13. Phase 0's exit condition is met and Phase 1's two deliverables exist; this records decisions and verified scope.

- **Source:** C64, selected by the owner. Initial execution baseline: the archive's `Original_v2` G64 sides A–D. This is an archive label, not a verified in-game release number. Source files are unchanged; hashes and URLs are in `c64/images/SOURCES.json`.
- **Target:** Atari 130XE (128 KB), decided by the owner on 2026-10-10. Emulator-first. A build for 64 KB machines may be wanted later: nothing should close that off needlessly, and every idea that would help it is logged in [docs/64K-NOTES.md](docs/64K-NOTES.md).
- **Screen scheme:** keep the C64's two bitmaps and page-flipped view (owner, 2026-10-10). Drawing into a single screen is the noted fallback if memory has to be saved.
- **65XE profile (2026-10-13, emulator-checked):** owner authorized investigation and implementation on `65xe`. `build.py --65xe` makes a separate playable 64 KB prototype: direct display, grayscale or optional fixed warm colour, original intro with temporary POKEY music, no in-game POKEY effects. Original rules, RNG, data, saves, two bitmaps and combat backup remain. All 21 scenarios / 257 native checkpoints pass. [Implementation, memory budget and remaining scope](docs/65XE.md).
- **Atari design:** game code and data stay at their C64 addresses, OS and BASIC ROMs out, machine routines replaced at their entries; the game's bitmap rows are shown as ANTIC mode 4 character sets ([design](docs/ATARI-DESIGN.md)). The display idea is tried on Atari800.
- **Atari build:** `port/atari/build.py` makes `build/atari/mm1.atr`. On an emulated 130XE the game runs through all eight scripts with its memory equal to the oracle's at 106 checkpoints and all three saves equal on disk (`port/atari/lockstep.py`); the scripts include treasure, a party wiped out, and a saved game loaded again after the machine is switched off and on. 35 instruction operands in the game's files are changed; nothing else. Since 2026-10-12 the disk people play starts with the C64's title program, with 25 more operands changed in it ([title findings](docs/TITLE.md)); `build.py --no-title` gives the disk without it, which the checks of the game use. The play screen is displayed in colour, each row's three colours chosen from what is on it ([screenshots](docs/SCREENSHOTS.md)), the keyboard works and no disk swapping is needed (`port/atari/play_check.py`). The build also plays in a second emulator, AltirraSDL, with a save and a restart, with and without the emulator's disk patch (`port/atari/altirra_check.py`). All nine original sound effects now drive POKEY, with approximate envelopes and timbres (checked 2026-10-11; [sound findings](docs/SOUND.md)). Text-to-graphics transitions are now stable; movement improves from 38 to 34–35 NTSC frames and bitmap return from 34 to 26, checked in both emulators (2026-10-11; [speed findings](docs/SPEED.md)). Effect pacing across display modes remains open.
- **Fidelity:** C64 game rules, RNG, data and saves match exactly. Presentation does not have to: the Atari gets its own screen layout, palette and pictures, and sound remains optional. The lockstep comparison is on game state and text, never pixels. "Byte-identical" applies only to rebuilding the C64 original from our sources before changing it. Confirmed with the owner on 2026-10-09; matching the RNG may be dropped later if it proves too costly, at the price of testing by hand.
- **Method:** retarget the original native 6502 code, with byte-identical source rebuilds before modifications. Build a deterministic host oracle and compare the Atari build against it in lockstep.
- **References/tools:** reuse `../wizardry_1`, or `WIZARDRY_ROOT`, without modifying or duplicating its library. Recorded hashes are in `docs/REFERENCES.json`.
- **Static analysis:** Ghidra 12.1.4 is installed separately under `~/tools`, with dedicated Temurin JDK 21 and `ghidra` / `ghidra-headless` launchers. Use it for routine labels, references and code exploration; confirm conclusions in VICE and retain ca65 byte-identical rebuilds. See [Ghidra workflow](docs/GHIDRA.md).
- **Documentation:** the owner wants a record complete enough to convert another game by. [docs/PORTING-LOG.md](docs/PORTING-LOG.md) gets an entry for every piece of work before it is committed: goal, what was done and how, result, evidence, what went wrong, what carries over. Findings documents state how each fact is known (traced, checked or read). A helper used more than once moves into `tools/`. Requested by the owner on 2026-10-10.
- **Originals and saves:** keep downloaded images unchanged. Interactive sessions use persistent copies under `state/`; smoke runs use disposable copies. Generated sector D64s are analysis views and do not preserve G64 protection/timing details.

Verified: VICE PAL/true-1541 boot to title, all three disk exchanges, options menu, inn, town, shops, a spell, character creation, a dungeon and the outdoors; all four standard sector maps; all eight directory-file extractions against c1541; 59-byte bootstrap PRG rebuilt exactly; the second-stage loader, C64 fastloader and 1541 drive code rebuilt exactly from labelled info files; the logical block decoding checked against every traced read and a traced save; all 76 code files rebuilt exactly from generated listings; five scripted sessions, including a fight and a save, that replay identically; Ghidra import/disassembly and native decompiler operation on its 57-byte payload at `$02CB`. The bootstrap-only Ghidra import leaves the jump to `$2000` unresolved. This does not establish full-game compatibility, deterministic input timing, or a working Atari port.

- **Disk interface:** the game reaches the disk only through eight entries at `$9D07–$9D1C` with parameters at `$9D00–$9D06`: address, length, offset, logical block. A side is 664 blocks of 256 bytes; sides B–D end with a table of two-character file names. The port and the oracle replace these entries and keep the block numbering. See [loader findings](docs/C64-LOADER.md).

- **Host oracle:** `tools/oracle.py` runs the original code on a minimal C64 on the host (own 6502 core, real KERNAL ROM, stub chips, disk reads served from the decoded sides). It starts from a memory image captured in VICE where the game's first program is entered. It replays all five recorded sessions with every event equal to VICE's, and its RAM equals VICE's at 29 checkpoints apart from 9 to 23 timing bytes ([oracle notes](docs/ORACLE.md)). This is the reference for the Atari lockstep.
- **Key timing:** a key is delivered on the first pass of the game's wait loop at `$0E3B`. After a wait at a disk prompt in play the two wait counters are reset to zero. The game's dice depend on how long each wait lasted, so this rule is what makes runs repeatable; the oracle and the Atari lockstep use the same rule. See [runtime notes](docs/C64-RUNTIME.md).
- **Comparison stream:** everything the game prints passes through three printer routines; the trace tool already records row, column and text there.

- **World:** 55 area files on sides B–D, each a map plus the 6502 code for its events, linked by named exits and neighbour fields ([docs/c64-areas.json](docs/c64-areas.json)).

- **Code:** 109 binaries, 76 of them code (71 KB). Each code file is traced, typed and rebuilt byte for byte from a generated da65 info file; `source/c64/game/hints.txt` and `symbols.txt` are the hand-kept inputs. 201 operands in 76 routines outside the start-up code name C64 hardware or the KERNAL ([code findings](docs/C64-CODE.md)). All play-time sound starts at one entry; disk reads are two resident routines plus two block reads in `EN`; the only KERNAL routine the reachable code calls is `GETIN`.
- **Timing sources found in the code:** the key wait's counters (random numbers) and the KERNAL clock (pauses), which the game drives from its raster interrupt.

Phase 2's exit condition (scripted, repeatable play on the host that matches the emulator) was met on 2026-10-10. The oracle also draws the screen; all 66 pictures of the five sessions equal VICE's screenshots pixel for pixel. **Checked 2026-10-11:** death, treasure and save-then-reload sessions were added (log entry 20); all nine sound effects are decoded and their 468 SID writes match VICE (log entry 21, [sound findings](docs/SOUND.md)).

Earlier note (owner's decision, 2026-10-10): start Phase 2's host oracle, which needs only what is already named: the loader entries, `GETIN`, the clock and the interrupt. **Phase 1 is parked, not closed:** the 3-D view drawing is not located, most routines are unnamed and 16 KB of tables are untyped. Come back to it as Phase 2 shows which code runs, and before Phase 3 at the latest. See [code findings](docs/C64-CODE.md) and [plan](PLAN.md).

**Checked 2026-10-11, reverse-transition follow-up:** six character screens were captured with ordinary Atari800 keyboard input after a fresh playable rebuild. No repeated `2` window was reproduced; the owner subsequently confirms the recopied ATR has no repeated `2`s. No new runtime fix; [findings](FIX.md), [evidence](test-artifacts/reverse/README.md).

**Graphics performance checked 2026-10-11:** native Atari800 profiling attributes 76.5% of baseline walking latency to screen conversion. The three subsequent kernel optimizations reduce movement from 34–35 to 30 frames: repeated-page operand guard, identity direct copy and exact unchanged-row reuse. All seven baseline game-byte hashes and settled pictures remain equal. No original game changes or new comparison exclusions. [Analysis, implementation and safety conditions](docs/GRAPHICS-PERFORMANCE.md).

**Palette reuse checked 2026-10-11:** an exact ordered-colour key reuses the
live mapping across neighbouring rows. Walking palette CPU work falls 19.7%
and Atari800 movement 30 → 29 frames, with unchanged colour selection and
game state. Nine broader captures and all 83 regressions pass; no original
game edits, new exclusions, bank or boot sectors. [Evidence and limitations](docs/PALETTE-PERFORMANCE.md).

**Held-key repeat checked 2026-10-11:** restore the original game-enabled
repeat flag/delay/rate path in the Atari keyboard. A continuous Ctrl+A hold
advances all six combat characters in both emulators; original scanner/
reader timing and automatic attack/shoot/block dispatch are checked.
All 85 tests, nine scripts / 116 checkpoints and three saves pass, with no
game-file or exclusion changes. [Implementation and limits](docs/KEYBOARD-REPEAT.md).

**Disk loading checked 2026-10-11:** keep the OS enabled across consecutive
direct sectors and restore it before upper-RAM copies/return. Recreate the
exactly-zero startup range, with a build assertion. Atari800 patched boot
4.19 → 1.29 s and town 1.42 → 0.78; Altirra standard serial boot 51.9 →
44.2 s. All 86 tests pass, same game bytes, save layout and exclusions.
[Measurements and scope](docs/DISK-PERFORMANCE.md).

**Encounter colours checked 2026-10-11:** count only matrix pixel pairs
actually drawn in the wide encounter layout, and mark all eighteen panel
columns for PF3. Gremlins/snakes are green and names keep their blue band in
both emulators. Eleven game hashes, nine scripts / 116 checkpoints and three
saves remain exact; all 87 tests pass. The existing bank fits by preserving
all distances in a symmetric table and reducing unrolling. Walking 29 → 30
NTSC frames; [implementation and limits](docs/COLOUR-SELECTION.md).

**Title checked 2026-10-12:** the C64's title program runs before the game:
two frames shown in place from the C64's own bitmap, pixel for pixel; its
three-voice tune on POKEY, every pitch checked tick by tick; eight scenes
through the kernel's screen copy; Escape starts the game. All nine scripts /
116 checkpoints and three saves stay exact with the title in front, and the
disk without it is byte for byte as before. The kernel is unchanged; the
title stage lives in memory that is free until the game is loaded. Checked in
Atari800 and AltirraSDL with both disk modes; all 98 tests pass. Scenes with
two pictures in a frame lose some colours; frames change in 1.0 s against
0.67 ([implementation, measurements and limits](docs/TITLE.md)).

**Checked 2026-10-12, gameplay and walking follow-up:** twelve additional sessions bring Atari800 coverage to 21 scripts / 257 checkpoints, with 153 new pixel-equal C64 reference pictures. Direct IF/EH/DP keys, combat actions, refused negotiations, trap outcomes, a real death followed by temple raising, and a stock-party wilderness route are covered. Holding the KERNAL clock during extended-bank conversion fixes a missed exact pause target; the game files and comparison exclusions are unchanged. Walking/turns 30 → 29 frames and character-sheet return 25 → 24, with unchanged benchmark pixels/game hashes. [Scope and fixtures](docs/GAMEPLAY-COVERAGE.md), [performance](docs/WALKING-PERFORMANCE.md).
