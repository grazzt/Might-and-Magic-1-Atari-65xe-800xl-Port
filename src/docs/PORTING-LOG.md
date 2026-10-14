# Porting log

This is the record of **how** the port was worked out, step by step, in the order it happened, including the wrong turns. It is written so that someone converting a different game can follow the same path and skip the mistakes.

The other documents say what is true now and are rewritten as knowledge improves: [C64-BASELINE.md](C64-BASELINE.md) (media and boot), [C64-LOADER.md](C64-LOADER.md) (disk), [C64-RUNTIME.md](C64-RUNTIME.md) (the running game), [PLAN.md](../PLAN.md) and [SPEC.md](../SPEC.md). This log is append-only: an entry is corrected by a later entry, not by editing history.

**Rule for keeping it.** Every piece of work gets an entry before it is committed. An entry states the goal, what was done and with which command or technique, the result, where the evidence is, what went wrong, and what would carry over to another game. A claim is marked *traced* (seen in a recorded run), *checked* (a prediction from it was tested), or *read* (from disassembly only).

Status at the last entry: **Phase 0 done. Phase 1 parked: every code file is split, rebuilt and inventoried; most routines are still unnamed. Phase 2 done: the host oracle replays the recorded sessions exactly as VICE does, in events, memory and pictures. Phase 3's exit met and Phase 4 under way: the game is playable on an emulated Atari 130XE, in colour and without sound, with memory equal to the oracle's through six scripts; its text screens are right since entry 18, it plays in a second emulator, AltirraSDL, with the OS doing real serial transfers (entry 19), and the slice's last pieces (treasure, a save loaded after a restart, death, a key in a pause) pass on VICE, the oracle and the Atari (entry 20).**

## The method so far, in one page

The port keeps the game's own 6502 code and replaces what touches the machine. So the first job is to find every place the game touches the machine, and to make the original playable by script so that later builds can be compared with it. In order:

1. **Collect and pin the originals.** Keep the downloaded archives, record URL, size and SHA256 for each, and never run on the originals. Prefer a flux-level or GCR image (G64) over a sector image (D64): this game's protection lives in bytes a D64 cannot hold.
2. **Get one scripted boot working in an emulator, headless.** A monitor command file that boots, feeds keys and dumps RAM is the base everything else stands on.
3. **Find the disk interface before anything else.** Follow the boot chain until the game stops using the operating system. Disassemble the loader on both sides (computer and drive). The aim is a small table: entry points, parameters, status codes.
4. **Decode the disk in your own code and prove it.** Write a decoder from the loader's logic, then compare its output with what the real loader put in RAM, for every read in a recorded run.
5. **Rebuild what you have disassembled, byte for byte.** A labelled disassembly that reassembles to the original bytes is the proof the labels and the code/data split are right.
6. **Instrument the running game instead of patching it.** Emulator trace points at a few addresses (loader command, text printers, key accept) give an ordered record of disk, text and keys without changing a byte.
7. **Find what makes runs differ, and remove it.** Here it was the time spent waiting for each key, which feeds the dice. Fixing when a key arrives made whole sessions replay identically.
8. **Learn enough of the data to steer.** Position, facing and the movement grid let routes be computed rather than found by screenshot. The same files then gave the world's whole link graph.
9. **Exercise every kind of activity once**, each as a script that replays from boot: walk, change disk, shop, cast, fight, save, create a character.
10. **Close the list statically.** Search every block of every disk for calls to the disk entries. If the recorded runs cover all of them, the load map is complete.

11. **Split code from data by following the code**, not by eye. Start from the entries you can prove (jump tables, load addresses) and add the game's own dispatch idioms until nothing is left unexplained.
12. **Rebuild every file from its listing**, generated, so that the whole game is checked on every run and not only the files someone looked at.
13. **List every operand that names the machine, grouped by routine.** That list is the port's work list.

14. **Run the original code on the host**, with the smallest machine around it that the game needs, and its disk interface replaced at the entry points found in step 3.
15. **Prove the host run against the emulator**, first on the recorded events, then on whole memory. Explain every byte that differs.

16. **Draw the host run's screen and compare it with the emulator's**, and use execution counts on the host to find the code static reading did not.

17. **Find the target's display mode that matches the source's memory format**, and try it alone before designing around it.
18. **Run the original code on the target with as few changes as possible**: redirect the addresses it uses rather than rewrite the routines that use them, and compare memory with the host run at every key.

Entries 1–8 below carry out steps 1–10 for this game, entry 10 carries out 11–13, entry 12 carries out 14–15, entry 13 carries out 16, entry 14 carries out 17 and entry 15 carries out 18. Later phases will add to the list.

## Tools and how they fit

| Tool | Role |
| --- | --- |
| VICE 3.7.1 `x64sc`, console mode | The execution reference. PAL, true drive emulation, virtual device traps off, `-seed 1`. Launch flags are in [tools/c64.py](../tools/c64.py) |
| VICE monitor command files | Scripted play and measurement: `until`, `step`, `trace exec`, `command N "m …"`, `bsave`, `screenshot`, `dump`/`undump`, `attach` |
| VICE `c1541` | Independent sector extraction to cross-check our own readers |
| cc65 `da65` / `ca65` / `ld65` | Disassemble from an info file, reassemble, compare bytes |
| Python 3, standard library only | Every project tool |
| Ghidra 12.1.4 | Installed and checked ([GHIDRA.md](GHIDRA.md)); not used so far. Phase 0's pieces were at most 1.5 KB each. Phase 1 needed the same analysis repeated over 76 files with overlays sharing addresses, which a 300-line tracer of our own did reproducibly (entry 10). It remains available for reading single routines |

VICE and cc65 are reused from the sibling Wizardry project (`../wizardry_1`, or `WIZARDRY_ROOT`); nothing is installed into it. See [REFERENCES.md](REFERENCES.md).

Project tools, in the order they were written:

| Tool | Does |
| --- | --- |
| `tools/verify_sources.py` | Checks every archived and extracted file against its recorded hash |
| `tools/analyze_c64.py`, `tools/d64.py` | Sector images and directory files from the G64s, cross-checked with `c1541` |
| `tools/rebuild_boot.py` | Reassembles the 59-byte bootstrap and compares |
| `tools/c64.py`, `tools/c64_smoke.py` | Launch VICE on writable copies; headless boot-to-menu check |
| `tools/g64.py` | Our own G64 reader: headers, header gaps, data blocks |
| `tools/mmdisk.py` | The game's logical disk: blocks, key, file table, monster data |
| `tools/c64_trace.py` | Plays a key script; records disk commands, printed text and accepted keys; checks reads and writes |
| `tools/rebuild_loader.py` | Rebuilds the loader pieces from da65 info files and compares |
| `tools/area.py` | Area files: movement grid, events, exits, routes, world graph |
| `tools/c64_explore.py` | Resume a snapshot, try keys, print what happened |
| `tools/code6502.py` | Static 6502 flow tracer: which bytes are instructions |
| `tools/disassemble.py` | Whole-game code/data split, generated da65 info files, rebuild check, code map and machine inventory |
| `tools/mos6502.py` | Fast 6502 core; its interpreter loop is generated from the opcode table |
| `tools/oracle.py` | Host oracle: a minimal C64, the disk stand-in, the script player and the comparison with a VICE trace |
| `tools/oracle_explore.py` | Play a script to a mark on the oracle, then try keys: text, disk commands, the text screen. A second or two a run |
| `tools/c64_screen.py` | Draws the C64 screen from memory; reads and writes PNG; compares with a VICE screenshot |
| `port/atari/build.py`, `src/kernel.s`, `src/boot.s` | The Atari disk image: kernel, boot code, the four sides with 35 operands changed |
| `port/atari/lockstep.py` | Plays a script on the oracle and on the Atari in Atari800; compares memory and disks, the kernel with its assembled image, and ANTIC's display list with the screen |
| `port/atari/play_check.py`, `port/atari/screenshots.py` | A short game through the emulated keyboard; the gallery of Atari and C64 screens |
| `port/atari/altirra.py`, `port/atari/altirra_check.py` | Drives AltirraSDL through its bridge; a save, a restart and a short game there, with or without the emulator's disk patch |

## Log

Times are the owner's local dates. Entries 1–3 were made by an earlier assistant session and are reconstructed here from its commits and documents; entry 4 re-ran its checks. Entries 4–9 are first-hand.

### Entry 1 · 2026-10-09 · Plan · commit `1e41f2d`

- **Goal.** Decide how a Might and Magic port would differ from the finished Wizardry I port.
- **Done.** Wrote [PLAN.md](../PLAN.md): phases 0–5, risks, decisions and when to take them. A first look at the Apple disks (4am crack) suggested native 6502 code with a custom disk routine and no Pascal p-code.
- **Result.** The central difference is recorded: Wizardry ran untouched p-code on a new interpreter; this game's logic is machine code that touches hardware itself, so the port is a retargeting of that code.
- **Carries over.** Decide first whether the game is interpreted or native. It sets the whole shape of the port.

### Entry 2 · 2026-10-09 · Reference media and a reproducible baseline · commit `a44c8ea`

- **Goal.** A known-good original that boots by script.
- **Done.**
  - The owner chose the C64 version as the source.
  - Downloaded two original G64 sets (`Original_v1`, `Original_v2`), two D64 sets (`None`, `FAC`) and the manuals. Kept the ZIPs; wrote `SOURCES.json` and `SHA256SUMS` for both folders.
  - `analyze_c64.py` extracted all 683 standard sectors per side through `c1541`; `d64.py` followed the directory chains.
  - Disassembled the 59-byte bootstrap `COPYRIGHT 1987` into [boot.s](../source/c64/boot.s); `rebuild_boot.py` rebuilds it exactly.
  - `c64_smoke.py` boots headless to the options menu and asserts the menu text from screen RAM at `$0400`.
- **Result.** `Original_v2` chosen as the baseline (the archive's notes recommend it with PAL, true drive and no device traps). All its standard sectors equal the `None` D64 set. Each side has only two small directory files, so almost the whole game is outside the DOS file system.
- **Evidence.** [C64-BASELINE.md](C64-BASELINE.md), [c64-disk-layout.json](c64-disk-layout.json), `test-artifacts/c64/baseline/`.
- **Carries over.** The provenance files and the smoke test are generic. Keys were fed through the KERNAL keyboard buffer (`$0277`, count in `$00C6`), which works for any C64 program that reads keys through the KERNAL.

### Entry 3 · 2026-10-09 · Ghidra installed · commit `f788fa9`

- **Goal.** Have a static-analysis tool ready for the large code blocks.
- **Done.** Installed Ghidra 12.1.4 and a private JDK 21 under `~/tools`; verified headless 6502 import, disassembly and decompiler on the bootstrap. Import settings are in [GHIDRA.md](GHIDRA.md).
- **Result.** Works. Not used further in Phase 0.
- **Carries over.** For a raw 6502 import, set base address, file offset **and** length; setting only the offset kept the whole file length.

### Entry 4 · 2026-10-09 · Audit of the inherited work · no commit

- **Goal.** The owner asked a new session to "get up to date". Do not build on claims that have not been re-run.
- **Done.** Re-ran `verify_sources.py`, `analyze_c64.py`, `rebuild_boot.py`, the unit tests and the smoke test into a scratch folder, and compared the smoke test's RAM dumps and screenshots with the committed ones.
- **Result.** Everything passed; the dumps and screenshots were bit-identical. The reverse engineering proper had not started: the loader behind the two boot files was untraced.
- **Carries over.** Start every new session by re-running the checks. It took two minutes and it is the only way to know the base is sound.

### Entry 5 · 2026-10-09 · The disk loader and the logical disk · commit `7c35247`

About 30 minutes of working time.

- **Goal.** Find how the game reads the disk, since the DOS directory holds almost nothing.
- **Done, in order.**
  1. **Second boot file.** Disassembled `ACTIVISION INC.` (`$2000–$25FF`) with `da65` and searched it for DOS command strings. Found an `M-W` upload of 96 bytes, an open of `#0`, and `B-E,2,0,18,7` (run track 18 sector 7 in a drive buffer). Its last three pages are copied to `$9D00–$9FFF`.
  2. **The C64 half.** Disassembled `$9D00–$9FFF`: seven parameter bytes, then a table of eight jumps. Every drive command passes through one routine at `$9E74` with the command number in A. That address became the trace point.
  3. **The drive half.** Read track 18 sector 7 from each side (identical on all four) and disassembled it at `$0300`. It queues sectors 8–11 into `$0400–$07FF`, **unscrambles them**, and jumps in. Reproduced the unscrambling in Python, then disassembled the result: a command table for six commands, four sector-order tables, the routine that turns a block number into track and sector, and the routine that computes a per-sector XOR key.
  4. **Protection.** The uploaded 96 bytes return one byte from the gap after a sector header. A sector image cannot answer that, so `g64.py` was written to read G64 tracks directly. Sides A and C carry `$AF` there. A failed check turns the `JMP` at the write entry into `BRK`; our RAM dumps hold `$4C`, so it passes.
  5. **Decoder.** `mmdisk.py` implements block → track/sector, the key and a `read(block, offset, length)`. First test: compare decoded blocks with the RAM dumps the baseline smoke test had already captured. They matched byte for byte.
  6. **Trace.** `c64_trace.py` sets two trace points on `$9E74`, one dumping the parameters and one dumping the stack (the game's call site is the second return address on it). Ran boot → menu → inn → town → gate → side C → outdoors.
  7. **File table.** The trace showed the last two blocks of a side loaded to `$4700` whenever a side was inserted. Disassembling the resident wrapper near `$C400` gave the table's layout: names, start blocks, lengths, load addresses, side number.
  8. **Sources.** Wrote da65 info files for the four pieces and `rebuild_loader.py`, which regenerates all of them byte for byte (the drive code after applying the scrambling).
- **Result.** The whole 1541 mechanism is eight entry points on a seven-byte parameter block. A side is 664 blocks of 256 bytes. Sides B–D end with a table of two-character file names. All 23 reads in the traced run matched the decoder. The B→C swap works, which had been in doubt from the archive's notes.
- **Evidence.** [C64-LOADER.md](C64-LOADER.md), [c64-logical-disk.json](c64-logical-disk.json), `source/c64/*.info`, `test-artifacts/c64/trace-outdoors/`, `tests/test_g64.py`, `tests/test_mmdisk.py`.
- **Went wrong.**
  - **G64 reader mis-paired sectors.** A data block that wraps past the index hole was attached to the wrong header (sector 0 mismatches). Fixed by rotating the block list to start at a header. Caught because `c1541`'s extraction was the cross-check: 2,732 sectors now agree.
  - **The monitor log does not record `attach` or `screenshot`.** The parser could not tell where a disk swap fell. Fixed by issuing `registers` at each such step and counting register dumps.
  - **CTRL-letter keys were ignored at the inn.** Putting PETSCII `$01` in the buffer was not enough. Single-stepping the inn showed it tests bit 2 of `$028E`, the KERNAL's CTRL flag.
  - **One read "failed" its check.** The first `$5000` title load matched only 300 of 1,300 bytes at the next capture. The title program had overwritten it by then; captured straight after the read, all bytes match. The check now reports bytes compared and bytes equal, not pass or fail.
  - **I called the loader "2-bit" in a progress note.** It sends one bit per clock edge. Corrected in the report and the document.
- **Carries over.**
  - Search the first loaded file for DOS command strings (`M-W`, `M-E`, `B-E`, `U1`). They point straight at the drive code.
  - Expect drive code to be scrambled on disk, and expect the scrambling to be its own inverse or nearly so.
  - A loader usually funnels every command through one routine. Find it and you have a single trace point for all disk activity.
  - Dump the stack at that trace point. It gives the caller of every load for free.
  - Check a decoder against RAM from a real run, byte by byte, and count rather than assert.

### Entry 6 · 2026-10-09 · How exact the port must be · recorded in `SPEC.md`

- **Question from the owner.** Does everything have to match perfectly, given that the C64 and Atari screens differ?
- **Decision, agreed with the owner.** Game rules, random numbers, data and saves match exactly. The screen, colours and sound do not have to. Comparisons between the two versions are on game state and text, never pixels. "Byte-identical" applies only to rebuilding the C64 original from our sources before changing it. Matching the random numbers may be dropped later if it proves too costly, at the price of testing by hand.
- **Carries over.** Settle this early and write it down. It decides what the reference run has to record: here text and state, not pictures.

### Entry 7 · 2026-10-09 · A fight, a save, and repeatable runs · commit `a43fac3`

About 55 minutes of working time.

- **Goal.** See what loads during a fight and how the game saves.
- **Done, in order.**
  1. **Snapshots.** Added `snapshot` and `resume` to the trace tool so an experiment starts in town instead of at power-on. A try from a snapshot runs in under a second; from boot it takes 9 to 18 seconds.
  2. **Reading the play screen.** Needed the game's text to know what happened. See "went wrong" below; the outcome was three more trace points on the game's own printers.
  3. **Save.** Walked back to the inn and signed in. The trace showed `RO` (`$0900` bytes) written from `$6000`. After the run, decoded VICE's copy of the disk with `g64.py` and compared: the written blocks equal RAM, 18 bytes differ from the original, nothing else on the side changed.
  4. **Position.** Captured RAM before and after single moves and turns and diffed them: `$3D` is the square (y × 16 + x), `$3C` is y, `$40` is the facing as a bit mask.
  5. **Area file.** Dumped Sorpigal's file as two 16 × 16 grids. With the position known, the second grid's low bit per direction was found to block movement. After the grids comes 6502 code that looks the square up in a table and calls a handler; the handlers contain the area's text.
  6. **Routes.** A breadth-first search over the movement grid gave key sequences. They reached the gate, the stairs, the arena and the inn door at the first attempt, which is the check on the grid and position.
  7. **Fight.** Took the stairs, walked to the arena square, accepted. The trace gave the load order: `EN`, a block of monster records, a monster picture, `CM`, `C3`.
  8. **Monster data.** Disassembled the two reads inside `EN`. They use block numbers, not names: records from block `$165` on, pictures through an index stored beside the file table. Added both to `mmdisk.py`. Unexplained blocks on B, C and D fell from about 300 each to 40, 44 and 14.
  9. **From boot.** Wrote the whole route as one script from power-on. It did not reproduce the fight; see below. Fixed with the `press` step.
- **Result.** A scripted run from boot wins an arena fight, climbs back and saves, and replays identically: same monsters, same damage text, same saved bytes.
- **Evidence.** [C64-RUNTIME.md](C64-RUNTIME.md), `tools/traces/boot-to-fight-and-save.txt`, `test-artifacts/c64/trace-fight-save/`.
- **Went wrong.**
  - **Random encounters would not come.** Thirty rests in a row outdoors all ended `REST COMPLETE: NO ENCOUNTERS!`, and walking about met nothing either. Gave that up and used the arena, a fixed fight at a known square found by listing the dungeon's event handlers.
  - **The screen text could not be read from memory.** The text matrix at `$0400` was stale during play; a second matrix at `$CC00` held colours; a trace point on the menu string printer never fired. The play screen is all bitmap. The way in was the text itself: find the "rest" prompt string in RAM, find the code that references it, follow the call to the printer. That gave `$0D42` (string) and `$0D1C` (character), which draw glyphs into the bitmap.
  - **A helper truncated its own output** at 6,000 characters and made a finished fight look unfinished. Cost several wasted runs.
  - **Attack is not valid for every character.** `A` does nothing for the back row, so a script of `A`s stalled. Alternating `A` and `B` (block) moves every character.
  - **The from-boot run got a different fight** and the party died, though the keys were the same as in the snapshot runs. The random generator is reseeded on every key from a counter that runs while the game waits. Keys sent after fixed delays arrive after different waits depending on how long the disk took. **Fix:** run to the first pass of the wait loop (`$0E3B`) and put the key in the buffer there. Every key is then taken on the first poll.
  - **`ready` hung VICE at the first disk prompt.** That prompt reads the keyboard itself and never reaches `$0E3B`. It keeps a fixed `wait` and `key`. The hung emulator had to be killed by hand; the tool has a host timeout for this.
  - **A resumed snapshot asked for the disk again.** The drive needs time to notice the image. A `wait $100000` after `resume` and after every `attach` fixes it.
  - **CTRL keys raced.** Poking the CTRL flag together with the key lost one character in one run. Exact version: `press 0N`, `until $78a2` (the test itself), `poke 028e 04`.
  - **Monster parsing stopped at 69** because "5 HEADED HYDRA" starts with a digit and the name test wanted a letter.
  - **The raw monitor log was 6.4 MB** per run. It is now deleted unless `--keep-log` is given; `trace.json` holds what matters.
- **Carries over.**
  - If a game's dice depend on timing, look at the key wait first. Defining "the key arrives on the first poll" is cheap in an emulator and can be made true on the target machine and in a host reference too.
  - To find a bitmap text printer, start from a string you can see on screen and walk back through its references.
  - Record text at the printers, not from screen memory. It works in every display mode and gives row, column and string.
  - Verify writes against the emulator's disk image afterwards, and count changed bytes everywhere else.
  - Fixed encounters are better test material than random ones.

### Entry 8 · 2026-10-10 · Services, spells, characters, side D, and closing the load map · commit `6a53a9d`

About 15 minutes of working time, after resuming the session with `resume.sh`.

- **Goal.** The owner asked to continue Phase 0 testing "with the shop, etc.": exercise the remaining kinds of activity and reach the fourth disk side.
- **Done, in order.**
  1. **Area tool.** Moved the grid, event and route code from scratch scripts into `tools/area.py` with tests.
  2. **Services.** From the town snapshot, walked to each of Sorpigal's five service squares and accepted. Each loads one file at `$2000`: `91` blacksmith, `92` temple, `93` food, `95` training, `96` tavern. Bought a dagger: no further disk access.
  3. **Play commands.** Pressed each command key (quick reference, protect, search, bash, unlock, order), opened a character sheet and cast the Location spell. None touches the disk. The spell printed the same square and facing that had been worked out from `$3D` and `$40`.
  4. **Character creation.** Created "TEST" from the options menu. No disk access until `SAVE CHARACTER (Y/N)?`, which writes the roster; 38 bytes changed on disk, none elsewhere.
  5. **How areas link.** Disassembled Sorpigal's gate and stairs handlers. Both end in `LDA #a / LDX #b / LDY #side / JMP $0B78`; the two codes spell the target file's name. Scanned all area files for that pattern, then found the four neighbour names in the 50 data bytes by comparing outdoor sectors. Result: 55 areas, 82 exits, 818 event squares in [c64-areas.json](c64-areas.json).
  6. **Side D.** Searched that graph for the shortest walk from outside Sorpigal to any exit naming side D: two sectors south, a portal at 13,13 of sector `EP`. Walked it; the game asked for side D and accepted it.
  7. **Treasure.** The file `ST` holds the treasure text. Fought a fixed lair in the dungeon and searched straight after the experience award: `SEARCH: NOTHING`. `ST` remains unseen.
  8. **Every caller.** Searched all four decoded sides for `JSR`/`JMP` to the eight loader entries and mapped each hit to its file and load address.
  9. **Key record.** Added a ninth trace point at `$0E44`, where the key wait accepts a key, so each trace now holds its input as well as its output.
  10. **Scripts.** Wrote three from-boot scripts (town services, side D, new character), regenerated the two earlier traces with the key record, and ran all five twice to confirm identical results.
- **Result.** All three disk swaps work. Every way the game reaches the disk is known: named files, the file table, monster records and pictures, and the roster write. Across the five runs, 127 reads were checked (101 exact; the rest overlap memory the program had since changed) and both writes. **Phase 0's exit condition is met.**
- **Evidence.** `test-artifacts/c64/trace-town-services/`, `trace-side-d/`, `trace-new-character/`, [c64-areas.json](c64-areas.json), "Every caller of the loader" in [C64-LOADER.md](C64-LOADER.md), `tests/test_area.py`.
- **Went wrong.**
  - **The town script derailed after the first shop.** Leaving a service turns the party to face away from it, so every later route started from the wrong facing. Found by reading `$3D` and `$40` step by step around the exit. The route generator now flips the facing after each service.
  - **Three area files broke the event parser.** `0L` on B and C reach the table by a longer path, and `SE` on D has other code there. The search window was widened and a file with no lookup returns no events.
  - **Two test mistakes of mine:** a fixture placed its tables at `$8232` instead of `$8432`, and one expected route was wrong. Both were in the tests, not the tool.
  - **Finding the end of a fight by guesswork** wasted runs: keys sent after the fight ended went to the map. The key record (item 9) shows exactly which key ended it.
- **Carries over.**
  - When areas are programs, exits are code. Find one exit by hand, then pattern-match the rest.
  - Compute routes; do not steer by screenshot. A route that works is also a test of the map decoding.
  - A static search for callers closes the question "have we seen every load?" far faster than more play does. Its limit is computed jumps, which it cannot see.
  - Record accepted keys alongside output. A trace that holds both is a complete test case for the next implementation.

### Entry 9 · 2026-10-10 · This log · commit `6a53a9d`

- **Goal.** The owner asked for meticulous documentation: a log good enough that another game could be converted the same way.
- **Done.**
  - Wrote this file from the session record (commands run, in order, with their results).
  - Added `tools/c64_explore.py`, a cleaned copy of the scratch helper used throughout entries 7 and 8, and `tools/traces/snapshot-town.txt`, which makes the snapshot it starts from. Until now that loop existed only in a temporary folder.
  - Corrected a stale line in `c64/images/README.md` that still said only the A→B swap had been tested.
  - Added the documentation rule to `SPEC.md` and links from `README.md`.
- **Not kept.** The one-off generator that wrote `boot-to-town-services.txt` from `area.py` routes. The script it produced is committed, and the recipe below regenerates any leg of it.

### Entry 10 · 2026-10-10 · Phase 1: code and data, rebuilds, machine inventory · commit `10bc3b9`

About 25 minutes of working time.

- **Goal.** Phase 1's exit: source that rebuilds exactly, and a written inventory of everything machine-specific.
- **Decision: generate, do not hand-write.** Phase 0's four loader pieces had hand-written da65 info files. The game is 76 code files, 55 of them area files of the same shape. So the code/data split is computed, the info files are generated, and only two small files are kept by hand: `hints.txt` (what the tracer cannot know) and `symbols.txt` (names).
- **Done, in order.**
  1. **Inventory of binaries.** Collected side A's 11 fixed reads and all named files; a file identical on several sides counts once. 109 binaries.
  2. **Tracer.** `tools/code6502.py`: a table of the 151 documented opcodes and a work-list loop that follows branches, jumps and calls from given entries, recording references. A path that meets an undocumented opcode, a `BRK`, or the end of the image is reported as a problem.
  3. **First run** from the two resident jump tables (`$0B00`, 48 entries; `$A000`, 53): 9 KB of code, one problem, and four resident blocks with no code reached at all (two of them, it turned out, hold none).
  4. **Overlays against the resident code.** Each overlay is traced in an image of resident code plus itself, stopping at its own edge; calls that cross become entries on the other side. This reached the blocks at `$3500` and `$4A00`, which only overlays call.
  5. **The dispatch idiom.** Listed every `JSR`/`JMP` whose operand the code writes. All are the same shape (two table loads, two stores), so the tracer now reads those tables itself. Repeated until stable, because tracing one table's targets exposes the next dispatcher: 60 tables found this way, three more given by hand.
  6. **Always-taken branches.** Added: a branch after a constant load, after `CLC`/`SEC`, or after its own opposite does not fall through.
  7. **Interrupt handlers** from two immediates stored to `$0314/$0315`.
  8. **Leftovers.** For each stretch of untraced bytes that decodes cleanly as code, searched every file for a reference. Twelve routines have none and are real code; they are listed as unreferenced.
  9. **Typing the data.** Area files get named parts (two grids, 50 data bytes, the event tables). Text is found by its look. Address tables are typed as such.
  10. **Rebuild.** One info file per code file → `da65` → `ca65` → `ld65` → compare. **All 76 matched at the first attempt.**
  11. **Machine inventory.** Sorted every operand by address range; grouped the hits by subroutine; added the pointer constants aimed at screen memory.
  12. **Reading the resident machine routines.** 26 routines; read the display, interrupt, sound and key ones and named them.
- **Result.** 71,262 bytes of code in 76 files; 32,850 instructions; 382 operands that name the machine, 201 of them outside the start-up code; 106 routines that hold them. 104 addresses named. Details in [C64-CODE.md](C64-CODE.md).
- **Evidence.** [c64-code-map.json](c64-code-map.json), `source/c64/game/`, `tests/test_code6502.py`. Checks: all 16 loader call sites seen in the recorded runs are traced instructions in the right file; the event handlers found in 54 area files equal the set `tools/area.py` reads by pattern matching; the generated files come out identical on a second run.
- **Found on the way.**
  - The `$3500` block is combat code and the `$4A00` block looks like trap code.
  - `EN` ends with 190 unreferenced bytes that drive the disk through the KERNAL: a development leftover.
  - The game turns the CIA timer interrupt off, so the KERNAL clock and keyboard scan run off the raster interrupt, twice a frame in split mode. Pauses are timed on that clock.
  - Three area files on side D read keys without going through the key wait.
  - Two area files' event counts are larger than their tables.
- **Went wrong.**
  - **Code found by accident hid missing tables.** Before the always-taken rule, the tracer fell through `BNE`/`BEQ` pairs into the next routine, which happened to be a table-dispatched one. Coverage looked better than it was. When the rule went in, 446 bytes of real code disappeared from the count, and that is what led to the dispatch tables.
  - **I called an entry unreferenced when it was not.** `$2A4A` in `CM` is the first of eight entries in a table that lives in the `$3500` block. The table's targets were not being resolved across files. Fixed (a table in one file may point into a file it calls) and the claim withdrawn.
  - **Operand versus address.** `STA $D7FF,X` was counted as a SID access. It is a colour RAM store with X from 1. Indexed operands one below a region are now counted with the region.
  - **A candidate that ran off the end.** `$4E87` looked like unreferenced code; tracing it stopped in the middle of an instruction at the file's last byte. It is a leftover past the real end of the block.
  - **A throwaway summary grouped files wrongly** (it showed one picture set as shared between sides B and D). The tool's own grouping, by name and hash, was right. Do not trust numbers from a one-off snippet in a document.
  - **Candidate lists were mostly noise.** "Decodes cleanly as code" matched text and tables far more often than code: all 31 such leftovers past the tables in area files were text or tables, and the one real routine there turned up in a different search. Each candidate was looked at before being accepted.
- **Carries over.**
  - Find the game's dispatch idioms before trusting any coverage figure. Listing every self-modified jump and every indirect jump takes a minute and names them all.
  - Trace overlays in the context of what they call, and let cross-file calls create entries. Resident routines called only by overlays are otherwise invisible.
  - Treat "falls through into code" as suspect after an unconditional pattern. It is the main way a tracer wanders into data.
  - Generate the info files. The first full rebuild then checks everything, and renaming something is a one-line change.
  - Group machine operands by routine. A list of 382 operands is a number; a list of 106 routines is a plan.
  - Count indexed accesses by the address they reach.

### Entry 11 · 2026-10-10 · Phase 1 parked, Phase 2 next · commit `10bc3b9`

- **Decision by the owner.** Commit Phase 1 as it stands, note that it may need more work, and start the host reference.
- **Why this order.** What Phase 1 still lacks is understanding (names, the view drawing, table layouts), not correctness: the rebuilds and the inventory are complete. A host run gives execution coverage for free, which turns "find the drawing code" from a search into a lookup.
- **What to come back for.** Listed under "Not done" in [C64-CODE.md](C64-CODE.md). Before Phase 3 at the latest.
- **Carries over.** Split a phase's exit into "proved" and "understood". Move on when the first is done if the next phase will make the second cheaper.

### Entry 12 · 2026-10-10 · Phase 2: the host oracle · commit `1b0f1f4`

About 25 minutes of working time.

- **Goal.** Run the original game on the host from a key script, repeatably, and show that it does what the emulator does.
- **Design decisions, with reasons.**
  - **Emulate a small C64, do not trap routines.** Phase 1 showed the kept code touches little hardware. So: a CPU, RAM, the CPU port's banking, a raster counter with its interrupt, one CIA timer, and stubs. The game's own interrupt handler, key reader and screen code run unchanged.
  - **Use the real KERNAL ROM** for the interrupt handler and `GETIN` instead of imitating them. The game chains to the KERNAL on every interrupt and reads its variables; running the real code leaves nothing to get subtly wrong. The ROM comes from the VICE installation already required.
  - **Replace the disk at its two entry points** and return exactly what the real routine returns, read off the Phase 0 listing (A, flags, X, Y and four zero-page bytes).
  - **Start from a captured machine state** at the first instruction of the game's first program, not from power-on. Booting for real would need BASIC, the KERNAL's serial code and a drive.
  - **Play the VICE scripts unchanged** and record at the same code addresses, so that the two records can be compared field by field.
  - **Write a new CPU core.** The plan was to start from the Wizardry project's `cpu6502.py`. It is built to run single native routines with Apple soft switches and has no interrupts; a whole session here is tens of millions of instructions. The new core generates its interpreter loop as one flat Python function from the Phase 1 opcode table and reaches about 5 million instructions a second.
- **Done, in order.**
  1. `tools/mos6502.py` and its tests (arithmetic flags, stack, indirect modes, hooks, interrupt entry).
  2. Captured the start state: added an I/O-area dump to the trace tool's `mark`, ran `capture-entry.txt`, stored RAM, I/O and registers under `test-artifacts/c64/oracle-start/`.
  3. `tools/oracle.py`: machine, disk stand-in, observation hooks, script player, comparison.
  4. Ran the five scripts with `--compare`. **All five matched VICE on the first run**: 578 events, among them a whole fight and both saves.
  5. Compared full RAM with VICE at every mark. Found 9 to 23 differing bytes per mark and explained each group.
  6. That comparison exposed the disk-swap problem (below). Added the counter reset to the two scripts that swap disks in play, regenerated their VICE traces, and compared again.
  7. Added execution coverage to the core and checked it against Phase 1's static split: all 7,095 executed addresses are known instruction starts.
  8. `tests/test_oracle.py`: the five sessions as a regression test (8 seconds), plus a check that a changed key is noticed.
- **Result.** Phase 2's exit condition is met. See [ORACLE.md](ORACLE.md).
- **Evidence.** `python3 -m unittest tests.test_oracle`; the tables in ORACLE.md; `build/oracle/*/coverage.json` after a run with `--coverage`.
- **Went wrong.**
  - **Matching output hid a real divergence.** After the first disk swap in play the oracle's random state differed from VICE's, yet every printed line still matched, because nothing random was printed afterwards in those two sessions. Only the memory comparison showed it. Cause: while VICE waits for the drive to notice the new disk, the game spins in the key-wait loop and its counters run; the oracle's wait ends at once. Fix: a rule, not an emulation. The scripts reset the two counters after such a wait.
  - **"Called on every move" was wrong.** Phase 1 said the resident code calls the area's event routine after every move. Coverage showed 20 moves through a sector with nothing executed in the area file. The call is gated by a bit. Corrected in the symbol file and both documents.
  - **A branch offset in my own speed test was off by two** and jumped into the middle of an instruction; the core reported `BRK` at a zero-page address. The core was right.
  - **Coverage has to be credited before the next load.** Overlays replace each other at `$2000` and `$8200`; marking executed addresses once at the end would have charged them to whatever was loaded last.
- **Carries over.**
  - Compare memory, not only output. Output equality over a few sessions is weak evidence that the hidden state is equal.
  - When two runs must agree on something that depends on real time, define it in the script instead of trying to emulate the time.
  - Use the platform's real ROM for the few system routines a game still calls, if it is at hand. It is less work and more faithful than stubs.
  - Make the stand-in for a replaced routine return everything the original does, including registers nobody is known to read.
  - Dynamic coverage and a static split check each other cheaply. Do both.

### Entry 13 · 2026-10-10 · Pictures from the oracle, and the view code found · commit `16730a8`

About 20 minutes of working time.

- **Goal.** Give the oracle a picture, check it against VICE, and use the oracle to find the 3-D view drawing that Phase 1 left unlocated.
- **Done, in order.**
  1. `tools/c64_screen.py`: draws 320 × 200 from memory (text, hires and multicolour bitmap, bank and addresses from the registers or from the game's display mode); a PNG writer and reader on zlib alone; a pixel comparison with a VICE screenshot.
  2. First comparison: 10 of 66 identical. Two separate causes, below.
  3. Measured VICE's screenshot palette from the picture pairs themselves and used it.
  4. Added `--settle` to the VICE tool and the oracle: wait a few frames before a mark in the key wait, then reset the wait counters.
  5. Moved the split one row down. **66 of 66 pictures identical.** Stored the settled VICE runs as references and added the test.
  6. Changed the core's coverage from flags to counts and profiled single steps in town. Two routines took over 80% of a step. Read them and their caller; named `draw_view`, `draw_wall_piece`, `clear_view`, `view_page`, `party_x`.
  7. Watched `$07` and `$0389` over several moves to confirm the page flipping.
- **Result.** The oracle's pictures equal VICE's. The view code is located: about 1 KB at `$0F1D–$135F`. Play alternates between the split display and the whole-frame display on every redraw, drawing each new view into the bitmap that is hidden.
- **Evidence.** `tests/test_oracle.py` (pictures), `test-artifacts/c64/settled-*`, the view section of [C64-CODE.md](C64-CODE.md).
- **Went wrong.**
  - **VICE's screenshots were stale, not the oracle's pictures wrong.** A screenshot is the last finished frame. At a mark taken the instant the game asks for a key, the newest text is not in it; the options menu was an empty frame. Phase 0's committed screenshots have had this flaw all along and nobody looked closely. Their trace records are unaffected.
  - **Nearest-colour matching used the wrong palette.** I mapped VICE's pixels to a textbook palette; VICE writes brighter colours, and its mid grey landed on light grey. Measuring the palette from the data fixed it.
  - **Settling shifted a mid-flow mark.** One mark sits inside the encounter code, not at a key wait. The oracle's `wait` stops at the first idle key poll and VICE's runs a fixed count, so the two stopped at different places. Settling now applies only to marks taken in the key wait.
  - **A test that played the script line by line lost the player's "already waiting" state** and diverged. The player now takes a callback for marks.
- **Carries over.**
  - Know when the emulator's screenshot is taken relative to what the program just drew.
  - Measure the emulator's palette; do not assume one.
  - To find drawing code, count executed instructions over one action. The hot routines are the answer, and reading three routines is quicker than tracing pointers.
  - A second set of sessions with different timing costs one option and doubles the evidence.

### Entry 14 · 2026-10-10 · Phase 3 begins: target, design, and the display tried · commit `01adb1e`

About 30 minutes of working time.

- **Decisions by the owner.** Target the 130XE. Keep a log of anything that would help a 64 KB machine, which may be a later goal. Try keeping the C64's screen scheme; the single-screen alternative stays noted as the memory-saving fallback.
- **Done, in order.**
  1. Recorded the decisions in `SPEC.md` and `PLAN.md` and started [64K-NOTES.md](64K-NOTES.md).
  2. Measured, on the oracle, which memory the game never changes or loads over ten sessions. Result: the old loader's space, 2 KB at `$D800`, and a little at `$FF4A`.
  3. Worked out the design ([ATARI-DESIGN.md](ATARI-DESIGN.md)). The key points: no relocation; OS ROM out; replace routines at their entries.
  4. Found the display mapping: the C64's multicolour cells are ANTIC mode 4 characters, bit for bit, so a bitmap row can be its own character set if rows are packed three to a 1 KB block.
  5. Tried it: `port/atari/display_demo.py` takes the town screen from the oracle, re-codes the pixels for per-row colour registers, builds a boot disk and photographs Atari800. The whole screen shows correctly.
- **Alternatives weighed for getting the game's bitmaps on screen.**
  - *Show them where they are, unchanged.* Impossible: with rows 320 bytes apart, four rows in sixteen cross a 1 KB boundary, whatever the base address.
  - *A raster bitmap mode (ANTIC E or F).* The game's data and blitter are cell-ordered; every drawing routine and every picture would have to be converted.
  - *Re-lay the game's bitmaps three rows to a block and patch the address arithmetic.* Works with no copy, but touches every drawing routine. Kept for later (speed, 64 KB).
  - *Copy to a display buffer in an extended bank.* Chosen first: no drawing code changes, so the first running build differs from the original as little as possible.
- **Went wrong.**
  - **The character set changed one scanline late.** The first version of the display-list interrupt saved three registers and loaded two table values before `STA WSYNC`. ANTIC takes about 40 cycles of each of these scanlines, and with the OS's dispatcher in front the wait was reached after the line's sync point. The first scanline of every row that began a new block showed cells from the old block. I misread the picture at first and went looking for unloaded sectors and a wrong sector count; comparing the emulator's memory with the disk image (identical) ruled that out, and printing the colour runs of single scanlines showed the one-line lag.
  - **I looked at the screenshot at thumbnail size and took a correct grey area for a fault.** The scanline dump settled what was really on screen.
- **Carries over.**
  - Look for a display mode on the target whose memory format equals the source's before deciding to convert graphics. Here it saved converting every picture and every drawing routine.
  - Try the riskiest design element in isolation, on real (emulated) hardware, with data from the reference run, before designing around it.
  - On the Atari, count the cycles a display-list interrupt spends before `WSYNC`, and remember ANTIC's share.
  - When a picture looks wrong, dump numbers from it before forming a theory.

### Entry 15 · 2026-10-10 · The game runs on the Atari, in lockstep with the oracle · commit `6c83812`

About 40 minutes of working time.

- **Goal.** Phase 3's exit: a build that boots on an emulated Atari to the first screen, and a harness that compares it with the oracle.
- **The idea that made it small.** Phase 1 listed 76 machine routines to replace. Reading how each reaches the machine showed that the game could be left to run its own routines if the *addresses* they use led somewhere harmless or useful:
  - Operands in `$D000–$D7FF` (C64 video and sound) are also Atari hardware. Point those 31 instructions at a stand-in register file in RAM. Nothing else in the game's files changes.
  - `$FFE4`, `$0314` and `$9D0D` are addresses the game jumps to or through. On an Atari with the OS out they are RAM. Put the Atari's own routines there.
- **Done, in order.**
  1. `port/atari/src/kernel.s`: the loader page (disk entry points, sector loop, zero-page swap), the part under the OS (vertical-blank handler, clock, key routine, keyboard), the stand-in registers and vectors, and a text display list. `boot.s`: installs these, builds a text font in C64 screen-code order from the OS's own font, loads what the C64 title program loads, sets memory from the oracle's image and enters the game at its start-up stub.
  2. `port/atari/build.py`: runs the oracle to the stub's first instruction for the memory image and registers; applies the 31 operand changes to the sides (checking each against Phase 1's traced instruction); assembles; writes one disk image with all four sides.
  3. First boot in Atari800: the C64's start-up stub drew its `INSERT DISK B` screen on the Atari, with the clock running.
  4. `port/atari/lockstep.py`: plays a script on both, compares memory at every mark, and the disks at the end. A test hook in the key routine holds the game in the first pass of its key wait until the harness offers a key.
  5. Worked through the differences (below) until all six scripts passed. Added `tests/test_atari.py`.
- **Result.** Memory equal at 62 marks across six scripts; both saves equal on disk. The play screen is drawn in memory but not yet displayed.
- **Evidence.** `python3 -m unittest tests.test_atari`; "What runs" in [ATARI-DESIGN.md](ATARI-DESIGN.md).
- **Went wrong.**
  - **The harness read ROM instead of its own variables.** The key routine's flags were first kept under the OS ROM. While the OS is switched in for a disk transfer the emulator's memory view shows ROM bytes there, so "the game is waiting" read as true during the boot. The flags moved to the loader page, which is always RAM.
  - **Comparing before the game had started.** The first `wait` ran a fixed 40 frames; the boot was still reading sectors, and the zero page on show was the OS's. It now waits until the game polls for a key.
  - **Memory the game never set.** After that, everything from `$0000` to `$21FF` matched and everything above was the C64's title-program leftovers against the Atari's boot code. Rather than teach the comparison to forgive untouched memory, the boot now loads an image of all of it, the last piece (under the boot code itself) from a few instructions in the kernel. Then nothing needs forgiving.
  - **The OS's serial code uses `$0314`.** Seen in the listing of Atari OS variables before it bit: the two bytes are saved around every transfer.
  - **The CTRL flag stayed set.** The harness set it before a CTRL key; on the C64 the KERNAL clears it again. One byte differed at every later mark until the harness cleared it after the key.
  - **Held one instruction further on.** The oracle stops before the key wait's `INC $2D`; the Atari is held in the key routine, after it. The comparison expects the counter one higher at such marks, and a script's reset of that counter is applied one higher.
  - **A mark in mid-flight.** One mark of the fight script sits inside the encounter code. The Atari cannot be stopped at an address, so that mark is not compared.
  - **A save that looked one byte short.** The emulator buffers disk writes; reading its image file while it still ran missed the last sector. The harness now shuts the emulator down before comparing disks. An earlier ad-hoc check had said "equal" because it happened to read the file after the process ended, and for a while the two answers contradicted each other.
  - **Assembler details:** a temporary label in the middle of a routine ends the scope of ca65's `@` labels; `*` is not constant in a relocatable segment; `ld65 -Ln` writes labels only for objects assembled with `-g`.
- **Carries over.**
  - Before replacing a routine, ask whether changing what its addresses mean is enough. An operand pointed at RAM, or a routine placed at the address the code already calls, leaves the original code and its timing-free behaviour intact.
  - Let the original start-up code run if it can; give it the memory it expects instead of reimplementing it.
  - Make the two machines equal at the start, completely. Every exception in a comparison is a place for a real difference to hide.
  - Keep a test harness's variables where they are visible in every banking state.
  - Compare what was written to disk only after the emulator has let go of the file.

### Entry 16 · 2026-10-10 · The play screen, the keyboard, and no more disk swapping · commit `4ed784e`

About 35 minutes of working time.

- **Goal.** See the play screen on the Atari, play with the real keyboard, and stop asking for disks.
- **Done, in order.**
  1. **Screen copy.** A routine in the extended bank copies the rows a C64 would show from the game's two bitmaps into the display buffer, three rows to a 1 KB block. It runs when the game asks for a key and has not done so for two frames, or has taken a key since the last copy.
  2. **Colours in the copy, not on disk.** The plan was to re-code the game's pictures when the disk is built. That needs the picture-set format, which is not decoded. The copy has the C64's colour matrices at hand instead: for each cell it picks one of 16 tables by the cell's two matrix colours and passes the cell's bytes through it. The game's data stays untouched and the lockstep comparison is unaffected.
  3. **Display.** The play screen's display list and its per-row interrupt, in the kernel; the vertical-blank handler chooses text or play list from what the copy last showed.
  4. **Disk sides.** The game's prompt routine keeps the side it wants at `$C54D` and reads the file table to check. In the build people play, the kernel sets the side from that byte whenever the file table is read.
  5. **Keyboard check.** `port/atari/play_check.py` plays through the emulated keyboard: RETURN, `1`, CTRL-A to CTRL-F, `X`, `I`. All of it worked on the first run.
- **Result.** The game is playable on an emulated 130XE: text screens, the play screen in grey shades with a cyan command panel, the keyboard, saves, no disk swapping. All six lockstep scripts still pass.
- **Evidence.** `tests/test_atari.py`; `build/atari/lockstep/*.png` after `lockstep.py --pictures`; `build/atari/play-step.png`.
- **Went wrong.**
  - **Text went dark grey.** After the new vertical-blank code went in, every text screen showed its letters at brightness 4 instead of 14. The emulator's own register dump said the text register held 14. Removing one unrelated store made it right again, which pointed at order or timing; writing the background register before the text register fixed it. Atari800 7.2.1 seems to work out the text colour wrongly when the background register is written after the text register. The OS writes them in the working order, which may be why nobody notices. **Cause not found; it may be an emulator fault and not a property of the machine.** To be tried on Altirra.
  - **I chased that for a long time by reasoning.** Six theories, none right. What settled it was bisecting: remove one piece of new code at a time and look at the pixel values. That took three short runs.
  - **A blanking bug found by reading, not by symptom:** in text mode the code stored 0, not `$22`, into the OS's display-control shadow before a transfer.
  - **Interrupt status.** The first handler tested the display-list bit first. On the real chip that bit stays set until reset, so a vertical blank after any display-list interrupt would have been taken for one. The emulator did not show it. The handler now tests the vertical-blank bit first and resets the status after a display-list interrupt.
  - **A segment outgrew its memory area**, and the boot code's copy of it was a page count that had to grow with it.
  - **`@` labels again:** a named label inside the copy routine (for a self-modified operand) cut the routine's local labels in two.
- **Carries over.**
  - If the target's display can be fed from the source machine's own colour information at run time, the source's pictures need no conversion and no format needs decoding.
  - Look for the variable behind a prompt before designing a way round the prompt.
  - When an effect makes no sense, bisect the change that introduced it before theorising.
  - Read an emulator's register state when the picture and the code disagree; then at least one of them is known to be right.
  - Test an interrupt handler's status handling against the chip's documented behaviour, not only against the emulator's.

### Entry 17 · 2026-10-10 · Colours, and a gallery · commit `ae5b53f`

About 30 minutes of working time.

- **Goal.** Colour on the Atari's play screen, and screenshots of a range of screens for the owner to look at.
- **Done, in order.**
  1. **Per-row colour choice in the kernel** (`choose_colours`). Before a row is copied, count its colour-RAM colours and its matrix colours, give the registers the commonest ones, and assign every C64 colour to the nearest of the four available. The copy then picks each cell's table from that assignment.
  2. **The stand-in colours measured.** For each of the C64's sixteen colours, the nearest in Atari800's palette to VICE's, taken from the two emulators' own palettes.
  3. **A colour for the command panel per row**, set by the row's interrupt with the other three.
  4. `port/atari/screenshots.py`: plays the scripts in lockstep, photographs the Atari at chosen marks, has the oracle draw the C64 at the same instants, and writes `docs/SCREENSHOTS.md` with twenty pairs.
- **Result.** The play screen is in colour and close to the C64's on most screens. All six lockstep scripts still pass: the colour work touches only what ANTIC is shown, never the game's memory.
- **Evidence.** [SCREENSHOTS.md](SCREENSHOTS.md).
- **Went wrong.**
  - **My first colour table was guessed and far too dark.** Brown and yellow both came out olive, red was maroon. Asking the emulators for their palettes and taking nearest neighbours took one command and fixed it.
  - **One panel colour for the whole frame was wrong for the encounter screen**, where a list overlies the top of the panel. The panel's colour is now chosen per row.
  - **`STX` has no absolute-indexed form.** The assembler's message was about operand size; it meant the addressing mode does not exist.
  - **An edit removed a constant** that sat between two blocks I replaced. The build said so at once.
  - **The extended bank filled up.** The colour code went into the last kilobyte, loaded with the colour tables instead of in the boot sectors.
- **What it cannot do, seen in the gallery.** A row with more than three colours besides black loses the rarest. The encounter screen's white names on a blue band are the visible case.
- **Carries over.**
  - Take colour equivalents from the emulators' palettes, not from a mental picture of the two machines.
  - Per-row colour registers go a long way towards per-cell colour when the pictures are made of horizontal bands, as a first-person view is.
  - Build the side-by-side gallery early. Twenty pairs showed at a glance what a memory comparison cannot: how it looks.

### Entry 18 · 2026-10-11 · Garbage on the text screens: the game was writing into the kernel · commit `8cedb1b`

About an hour of working time, after an investigation by another assistant session.

- **Goal.** The owner saw that the Atari's text screens (character creation, combat, the menu) were garbage. Find out why and put it right.
- **The cause** *(checked)*. `set_vic_bank_bits` at `$C40D` reads `$DD02`, sets its two low bits and stores it back: on the C64 that makes two lines of CIA 2 outputs. On the Atari `$DD02` is RAM under the OS, inside the kernel's `UNDER` segment, and in the build of entry 17 it was the opcode of `LDA #>text_list` in the vertical-blank handler. `$A9 | $03` is `$AB`, an undocumented opcode. In Atari800 it loaded A AND the operand, and A still held the list's low byte, 0. So the handler set the display list's high byte to 0 and ANTIC ran whatever is at `$0000` as a display list. The play screen takes the handler's other branch and was untouched. The screen memory, the font and the display list were all correct throughout.
- **Done, in order.**
  1. **The diagnosis came as a write-up** (`FIX.md`, left in the working tree and not committed; what matters of it is in this entry). That session had compared `$0400` with the oracle's (equal), traced ANTIC's register writes in the emulator (`$D403` got 0, not `$68`), and shown readable screens by setting the list pointer by hand.
  2. **Checked before changing anything.** The assembled `under.bin` has `A9 68` at `$DD02`. A lockstep run that printed that byte at every mark showed `AB` at all of them. The disassembly shows the four instructions: `$C410` and `$C415` (`$DD02`), `$C418` (`$DD00`, read) and `$C59D` (`$DC0D`, the interrupt install's store of `$7F`).
  3. **Tried the fix without touching the repository**: a scratch script that imports `build.py` and `lockstep.py`, replaces `build.patches` with one that adds the four operands, and points `build.OUT` at a scratch folder. Result: the opcode stays `A9`, all 62 marks and both saves still equal, the screens readable.
  4. **Looked for other damage.** At every mark of three scripts, compared the kernel's three main-memory segments with the assembled files and grouped the differing bytes by the label before them. Before the fix the only changed code byte was `$DD02`; the `$7F` for `$DC0D` landed in the saved OS zero page, in the high byte of `DOSINI`, which only a warm start reads. After the fix only variables change. That listing is now `lockstep.py --kernel-writes`.
  5. **The fix.** Three bytes `fake_cia` at `$FFB0` in the kernel's `TOP` segment, one for each CIA register the kept code names (`$DC0D`, `$DD00`, `$DD02`). `build.py` points the four operands at them with the same mechanism as the video and sound chips: 35 instructions now, 70 bytes on disk. No initial values are needed: what the game reads from `$DD02` it only stores back, and what it reads from `$DD00` is masked and combined with the two bank bits before the call to the loader's entry `$9D0A`, where the kernel keeps those two bits and nothing else.
  6. **Checks, so that this kind of fault cannot pass again.**
     - `lockstep.py` compares the kernel's code and tables with what was assembled at every mark (`kernel_changes`; the pieces are `fixed` in `build.py`).
     - With `--pictures` it asks the emulator where ANTIC's display-list pointer is and compares with the list that goes with the screen. `play_check.py` does the same on a text screen and on the play screen.
     - `build.py` stops if the kernel's stand-ins are not where it points the operands, or if the inventory has a CIA register without a stand-in.
  7. **Tried the checks against the fault.** The same scratch technique, this time removing the four redirections from the build: every mark reports `1 bytes of the kernel are not as assembled: $dd02 ab (assembled a9)`, and with pictures `ANTIC's display list is at $0000, not at $6800 for text`.
  8. **The gallery made again** and all twenty pairs looked at. Seven Atari pictures changed, the seven text screens; the thirteen play-screen pictures came out byte for byte as before.
- **Result.** The menu, character creation, the inn's roster, character sheets, the Location spell's page and combat show their text, row for row as on the C64. All six lockstep scripts and the keyboard check pass.
- **Evidence.** [SCREENSHOTS.md](SCREENSHOTS.md); `python3 -m unittest tests.test_atari`; `python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt --kernel-writes`.
- **A wrong finding in entry 16, corrected.** Entry 16 reported that Atari800 shows text dark when the background register is written after the text register, cause not found, possibly an emulator fault. It was this bug. Two experiments:
  - On the fixed build the two stores were put in the other order: the menu's picture is identical, pixel for pixel (text at 211, 211, 211 both ways). *(checked)*
  - The tree of commit `4ed784e` (entry 16) was unpacked into a scratch folder and the handler arranged so that `LDA #$0E` (the text brightness) sits at `$DD02` straight after `LDA #>FONT`: the text comes out at 51, 51, 51. The store turns the load into `$AB`, which gives `$64 AND $0E` = 4. Brightness 4 instead of 14 is exactly what entry 16 saw. *(checked)*
  - So the "fix" of entry 16 most likely worked by moving instructions: with the stores swapped, `LDA #0` would sit at the damaged address, and `$AB` with operand 0 still loads 0. *(Inferred: the build that showed the dark text was not kept.)*
  - The fault was there from the first build and hit something else each time the code moved. Built again from their commits: for entry 15 the byte at `$DD02` is the operand of `STA last_code` in the key reader (`$DC80` becomes `$DC83`), for entry 16 the opcode of the `STA` to the character-set register (`$8D` becomes `$8F`, which stores A AND X). *(Read from the assembled bytes; the effects were not looked for.)*
  - The comment in `kernel.s` that blamed the emulator is corrected. The item "to be tried on Altirra" for it is closed.
- **Went wrong.**
  - **Entry 17's gallery went in with seven garbage pictures.** The work was on the play screen and those were the pictures looked at. The entry even says a gallery shows "at a glance what a memory comparison cannot".
  - **The inventory had the answer.** Phase 1 listed the CIA accesses ([C64-CODE.md](C64-CODE.md): "`$DD00`/`$DD02` for the VIC bank, `$DC0D` once"). Only the ranges that are hardware on the Atari were redirected; the CIAs' range is plain RAM there, was written down as "free", and the kernel was then put in it.
  - **The comparison could not see it.** `lockstep.py` leaves out `$D800–$DFFF` because the two machines differ there by design. Nothing else looked at that memory.
  - **Entry 16's symptom was explained away.** An effect that changed when unrelated code moved was put down to the emulator. Code that behaves differently when it moves is being overwritten or mis-addressed until shown otherwise.
  - **`target = * + 1` is not in the linker's label file**; `:=` makes it a label. Needed so that `build.py` can leave that self-modified operand out of the fixed pieces.
  - **My first scratch script for the listing in step 4** was put together by executing pieces of another script and failed on a missing name. Written out plainly it worked at once.
  - **I first reported the frame's corner pieces as wrong glyphs**, from one small picture. Side by side at full size they are the same solid blocks as the C64's, a little greyer.
- **Still open.** `$AB` is one of the unstable undocumented opcodes: on a real 130XE the same fault could have looked different again. The kernel is still at `$DC00–$DFFF`; the inventory behind the redirections is static, so an access through a pointer would not be in it. The kernel check is the guard for that. The two kernel segments in the extended bank are not checked; the game's code cannot address them.
- **Carries over.**
  - **Hardware addresses of the source machine that are plain RAM on the target are the dangerous ones.** A store to an address that is hardware on both machines shows at once. A store into RAM is silent. Redirect every hardware access in the inventory, not only the ones that collide with target hardware, before putting anything of your own in such a range.
  - **Whatever the memory comparison leaves out needs its own check.** For your own support code: compare it with its assembled image at every checkpoint. It is ten lines.
  - **Ask the emulator what the display chip is doing**, not only what is in the memory it should be showing.
  - **Run a new check against the fault it is for** before trusting it.
  - **When a symptom moves with the code, find what is at the old address.** List which bytes of your own code change during a run.
  - **Look at every picture of a gallery before it is committed.**
  - **A fix can be tried without touching the tree**: import the build script, replace one function and the output folder, run the comparison. Old commits build the same way from `git archive` into a scratch folder.

### Entry 19 · 2026-10-11 · The build in a second emulator: AltirraSDL · commit `7b6157b`

About 40 minutes of working time.

- **Goal.** The plan asked for play on a second emulator. The owner had AltirraSDL installed (a Linux port of Altirra, nightly 4.50.21, in `~/tools/altirrasdl`, launcher `~/.local/bin/altirra`). See whether the build runs there, and make that a check that can be repeated.
- **Done, in order.**
  1. **Found how to drive it.** AltirraSDL has a bridge: started with `--bridge`, it takes one-line commands over a local socket and answers in JSON: run frames, read and write memory, hold keys, read ANTIC's registers, take a picture. `--headless` needs no display. `port/atari/altirra.py` is a small client for it.
  2. **Booted the disk.** It came up at the first prompt on the first try, with ANTIC on the text list.
  3. `port/atari/altirra_check.py`: the play check of entry 16 again, in Altirra, with a save added. Create a robber named ALTI, save, stop the emulator, start it again from the written disk, find ALTI among the characters; then the inn, six characters, the town, a step. At eight stops: the kernel's code against its assembled image, ANTIC's display list, a picture.
  4. **The same with Altirra's disk patch off** (`--sio`). Both emulators normally answer the OS's disk call themselves. With the patch off the OS ROM does each sector over the emulated serial line with its own interrupts, which is what a real machine does and what no run had done before.
  5. **The unfixed build of entry 18 tried in Altirra too**: its text screens are garbage there as well (list pointer at `$0043`).
- **Result.** Everything passes both ways: 32 checks each. The save changes 38 bytes on side B, as it does in the lockstep run, and the restarted machine lists the new character. Of the eight pictures, six are identical with and without the disk patch. The two of character creation show different rolled statistics, as they must: the dice depend on how long the game waited for each key ([C64-RUNTIME.md](C64-RUNTIME.md)).
- **Disk times, measured for the first time** *(Altirra, standard serial speed, patch off; to the nearest 10 frames at 60 a second)*:

  | Step | Frames | Seconds |
  | --- | --- | --- |
  | Power on to the first prompt | 3,110 | 52 |
  | RETURN to the options menu | 330 | 5.5 |
  | Saving a character | 110 | 1.8 |
  | From the inn into the town | 660 | 11 |

  With the patch on the same steps take 230, 20, 10 and 90 frames. The C64's times for the same steps have not been measured, so there is nothing to compare with yet.
- **Evidence.** `python3 -m unittest tests.test_altirra` (about 50 seconds); pictures in `build/atari/altirra/` after a run.
- **Went wrong.**
  - **The save test said nothing had been written.** It compared the disk image file. AltirraSDL never writes to the image it is given: it keeps a working copy among its settings, in `disk_state/<SHA-256 of the image>/disk.atr`, and starts from that copy the next time the same image is opened. The game's write was there, 38 bytes. The test now reads the working copy.
  - **That working copy outlives a run.** A second run would have started from the first run's disk, with ALTI already on it. Caught while looking for the missing write, before it gave a wrong result: the client clears the working copies unless told to keep them.
  - **The first full run with the patch off took three and a half minutes** and half an hour of processor time. The frames were not the cost: the default renderer was. `--renderer sdlrenderer` runs the same frames eight times faster. Its pictures have the same pixels with each colour one level darker.
- **What was not tried.** `KEY`, the bridge's other way to press a key: its documentation says it waits for the keyboard interrupt, which the kernel never enables, so `KEYRAW` (hold a key in the matrix) was used from the start. The six lockstep scripts are not played in Altirra; they could be, since the test kernel's hooks are memory locations. Both emulators run Altirra's own OS ROM, not Atari's.
- **Carries over.**
  - **Run the disk code once with the emulator's disk patch off.** With it on, the OS's serial routine and its interrupts never run, and everything that was set up for them (the swapped zero page, the saved vector, the interrupt masks) is untested.
  - **Find out where an emulator puts what the program writes** before testing a save. It may not be the file you gave it, and it may still be there on the next run.
  - **When a headless emulator is slow, suspect the renderer.**
  - A second emulator cost forty minutes once the first one's checks were scripts. Most of the check was reused: the kernel comparison and the stops' logic came from `lockstep.py` and `play_check.py` unchanged.

### Entry 20 · 2026-10-11 · The untested parts of the slice: treasure, reload, death, a key in a pause · commit `7491278`

About an hour and a quarter of working time.

- **Goal.** Phase 4's slice is create a party → town → dungeon → fight → return → save → reload, the same on the Atari as on the reference. Four things in or near it had never been run on any machine: loading a saved game in a later session, treasure, death, and a key arriving during a pause. Script each, prove the oracle against VICE on it, and run the Atari against the oracle.
- **Done, in order.**
  1. **Read the pause routine** (`$C355`) and its key reader (`$C648`). A key ends the pause and is used up; the reader also remembers it as the last key (`$0371`) and stops a playing sound. Listed all 33 calls and jumps to the pause: none tests the key that comes back.
  2. **Tried it on the oracle before building anything**: a hook at the pause's poll (`$C378`) that puts a key in the buffer, on the whole fight-and-save session. Same events, same saved roster, a quarter of the time; memory different only in clock, stack leavings and the like, plus `$0371` for a while.
  3. `tools/oracle_explore.py`: play a script to a mark, then keys, print what happened, show the text screen. Runs from boot in a second or two, with no emulator and no snapshot.
  4. **Found a death, a treasure and the choice before a fight** with it, all under Sorpigal: the lair at 13,5 (ten snakes), wandering groups, a chest. Read the area's dispatcher and handlers to see where groups come from ([C64-RUNTIME.md](C64-RUNTIME.md), "Encounters, treasure and death").
  5. **Three script steps**, in all three players (`c64_trace.py` for VICE, `oracle.py`, `lockstep.py` for the Atari):
     - `pauses XX` / `pauses off`: every pause gets key XX on its first poll. VICE: two trace points at `$C378` whose commands write the key and a count of one into the KERNAL's buffer, enabled and disabled. Oracle: a hook. Atari: a byte in the test kernel that its `GETIN` puts in the buffer when the call comes from the pause.
     - `restart`: off and on with the disks as they are. VICE: a second emulator run on the first one's disk copies. Oracle: a new machine from the start state, same disks. Atari: `Atari800_Coldstart` in the running emulator, which boots again from the disk it has open.
     - `--quick` on all three: the script with `pauses 20` after its first `ready`.
  6. **Two scripts**: `boot-to-treasure-and-reload.txt` (139 keys, 29 marks) and `boot-to-death.txt` (85 keys, 18 marks).
  7. **VICE, then the Atari.** Both scripts recorded in VICE (`test-artifacts/c64/trace-treasure-reload`, `trace-death`) and the fight-and-save session with `--quick` (`quick-fight-save`). Oracle against VICE: events, and memory at all 47 marks. Atari against oracle: memory at 27 and 17 marks, and the disk.
  8. **Five screens added to the gallery** (25 pairs): the choice before a fight, the chest, the saved character after the restart, the lair, the death screen. All looked at.
- **Result.**
  - **Oracle = VICE** on both new sessions: 277 and 178 events, and memory at every mark apart from the known timing bytes.
  - **Atari = oracle** on both: every mark, and the save's 24 bytes on disk. The saved game loaded after a cold start shows the experience, the gold, the halberd and the unconscious knight.
  - **A key during a pause changes nothing but time**, on all three machines. That is now timing rule 3 in [ORACLE.md](ORACLE.md).
  - Eight lockstep scripts, 106 marks, three saves. The Atari suite takes 35 seconds.
- **Evidence.** `python3 -m unittest tests.test_oracle tests.test_atari`; the three new folders under `test-artifacts/c64/`; [SCREENSHOTS.md](SCREENSHOTS.md).
- **Found on the way.**
  - **Two bytes that differ by nature.** After the lost fight the Atari had `$DC86` at `$271E` where the C64 has `$FE43`. The combat file saves the machine's NMI vector there while it copies a bitmap with the KERNAL switched out, and stores it back afterwards. On the Atari that is the kernel's own vector, stored back unchanged. Read the code to make sure the store-back cannot happen without the save (one caller, as a pair); left the two addresses out of the comparison with the reason next to them. The kernel check of entry 18 covers the vector itself.
  - **The dice hardly vary when every key comes on the first pass.** The key wait feeds the number of passes it made into the generator; with `press` that is always the same. Walking the same squares again gave the same throws every time, and extra keys in front changed nothing: twenty-three variants, no encounter. One pass more at one key gave a wandering group at once. A script can say that with a `poke` of the wait counters, as the disk-prompt rule already does, and the treasure script does.
  - **Wandering groups come through the area file**: its dispatcher sends a square that has no event to resident `$0B48`. That is why resident code enters the area file on squares without events, which the oracle's first notes recorded without an explanation.
  - **The boot does not lean on power-on memory**: after a cold start in the same emulator, with the old session still in RAM, the Atari's memory equals the oracle's fresh machine at every mark.
  - **Monsters that are green on the C64 are tan on the Atari** (the gremlin, the snake). The rows they stand on have more colours than registers.
- **Went wrong.**
  - **My new exploration tool did not play what a script plays.** It played the base script and then the keys in a second call, and the second call began by running to the key wait again although the machine was already there: one extra pass of the wait loop, which is exactly what the dice are made from. A treasure found that way did not appear when the same keys were written as a script. The oracle now keeps "held at the key wait" between calls, and a test plays one script whole and in two parts and compares memory.
  - **That flaw is also what found the treasure.** The extra pass was the one thing that changed the dice; without it I would have gone on believing the dungeon had no wandering groups. It was then written into the script on purpose.
  - **A search that reported "no encounter" for all forty-two of its walks** was reading the wrong three characters of each text line to find the monsters' names, and so threw away every encounter it met. Seen because a walk known to meet sprites was in the list.
  - **`pkill -f` on a script's name killed the shell that ran it**: the pattern was in that shell's own command line.
  - **The trace tool hashed reads against the original disk.** Right until a script restarts after a save. A later machine's reads are now hashed against the disk the machine before it left.
  - **The Atari harness took the old machine for the new** after the first cold start: the kernel's "waiting for a key" byte still said yes until the boot had loaded the kernel again, half a second later. The harness clears its four bytes at a restart.
  - **The oracle's summary line counted only the machine after the restart.**
- **Not done.** Settled pictures (VICE screenshots compared with the oracle's drawing) for the two new sessions. Retreat, bribe and surrender, finding and removing a trap, one character's death and raising. The new scripts in Altirra. The three side-D areas that read keys themselves.
- **Carries over.**
  - **Explore on the host reference, not in the emulator.** With a run from boot taking a second, a fight can be tried under ten policies and a route under fifty variations. Two sessions that would have taken an evening of snapshots took minutes each.
  - **An exploration tool must play exactly what the recorded script will play.** Test it by playing one script whole and in pieces and comparing memory, before trusting anything found with it.
  - **Know where the game's randomness comes from before searching for an outcome.** If the reference removes the entropy (keys on the first pass), outcomes are few; give scripts an explicit, replayable way to change the dice.
  - **Try a rule on the reference alone first.** The pause rule was tested with a three-line hook on the oracle before any of the three players was touched.
  - **A restart is a cheap, strong test of a boot**: it runs it a second time, over memory that is anything but clean.
  - **When two machines differ in a byte, find the instruction that wrote it.** Two bytes took one search for their address in the disassembly; the alternative was an exclusion nobody could explain later.
  - **Put a known positive into every search.** A search that finds nothing is only believable if it would have found the case you already know.

## Recipes

Each is a thing that had to be worked out once. Addresses are this game's; the approach is general.

### Run the original by script

```bash
python3 tools/c64_trace.py tools/traces/boot-to-fight-and-save.txt   # writes build/trace/<script name>/
```

A script is one step per line: `press XX` (run to the key prompt, give PETSCII XX), `ready` (run to the key prompt), `mark NAME` (screenshot), `attach SIDE`, `wait N`, `until ADDR`, `key XX`, `poke ADDR XX`, `snapshot NAME`, `resume FILE SIDE`. The tool turns these into a VICE monitor command file, runs `x64sc -console -warp -moncommands`, and parses the monitor's log.

`trace.json` is what must come out identical when a script is run again. `vice.log` holds emulator diagnostics, and a few of its lines vary from run to run.

### Explore quickly

```bash
python3 tools/c64_trace.py tools/traces/snapshot-town.txt                        # once: makes town.vsf
python3 tools/c64_explore.py look build/trace/snapshot-town/town.vsf B 'IIJII|Y|'
```

Prints `DISK`, `TEXT` and `KEYS` lines in order. `|` marks a point and takes a screenshot (`build/explore/look/m01.png`). To start deeper in the game, add `<snap NAME>` to the keys and resume from the new file next time.

### Find the disk interface

1. Disassemble the first file the operating system loads; follow jumps until a file is loaded by other means.
2. Search for DOS command strings. `M-W` and `M-E` mean code is uploaded to the drive; `B-E` means a sector is executed in the drive.
3. Disassemble the drive code at its drive address (`$0300–$07FF` are the 1541's buffers). Look for tables of sector numbers and for arithmetic on track and sector: that is the block mapping and any encryption.
4. Find the one routine on the computer side that sends a command byte. Set `trace exec` there and dump the parameter block and the stack.

### Prove a disk decoding

Compare `mmdisk.read(side, block, offset, length)` with emulator RAM at the load address after each traced read. Report bytes compared and bytes equal. Where they differ, capture earlier (straight after the read) before suspecting the decoder. For writes, decode the emulator's disk image after the run and count differences inside and outside the written range.

### Prove a disassembly

Keep the da65 info file as the source (code/data ranges, labels, comments). `rebuild_loader.py` runs `da65 -i`, `ca65`, `ld65` and compares every byte with the original. A label that is wrong still rebuilds; a code/data split that is wrong usually does not.

### Find where the game reads keys and rolls dice

1. Break while the game is waiting for a key; the loop you land in is the key wait (`$0E3B` here).
2. Look for counters incremented in that loop. Follow where they are read: that led to the reseed at `$1271` and the generator at `$1293`.
3. Test it: same keys with different delays should give different outcomes; keys delivered on the first pass should give the same outcome every time.
4. Note every prompt that does **not** use the common wait (the title and the first disk prompt here), and CTRL or shift flags read separately (`$028E`).

### Find the text printers

1. Find a string you can see on screen in a RAM dump. Try plain ASCII, screen codes and constant offsets.
2. Search the code for the string's address, as an absolute operand or as an immediate pair (the area files use `LDX #lo / LDY #hi / JSR`).
3. Follow the call that comes next to the printer. Set trace points at its entry (for row and column) and in its character loop (for the character in A).
4. If the printer draws to two places (this game draws the top rows on both bitmaps), trace one and skip the other, or every string appears twice.

### Find position and facing

Capture 64 KB of RAM before and after one step forward, one turn, and one step in another direction, and diff. Bytes that change with moves but not turns are position; with turns but not moves, facing. Confirm by computing a route and walking it.

### Compute a route

```bash
python3 tools/area.py build/c64/original-v2-b/logical/31-EG.bin 8 3 N 6 5 W   # -> ('IIJII', 'W')
python3 tools/area.py build/c64/original-v2-b/logical/31-EG.bin               # event squares and their text
```

`area.world_route()` does the same across area boundaries using the neighbour fields.

### Split a game into code and data

```bash
python3 tools/disassemble.py -v          # per-file byte counts, problems, calls that leave the file
python3 tools/disassemble.py --rebuild   # also write info files, rebuild and compare
```

1. List the binaries with their load addresses, and which are in memory together.
2. Trace from the entries you can prove. Report problems instead of guessing.
3. List every jump or call whose operand is written by code, every indirect jump, and every pair of immediates stored to a vector. Each is a dispatch mechanism; teach the tracer the idiom or give the table in a hints file.
4. For untraced bytes that decode as code, search all files for a reference before believing them. Look at each one.
5. Stop when there are no problems and every leftover is explained.

### Inventory what ties the code to the machine

Sort every traced operand by address into ranges (I/O chips, system variables, screen memory, ROM entry points, the disk interface). Group the hits by subroutine. Add the constants loaded into pointers that aim at screen memory. Then read the routines on the list: on this game that was 26 in the resident code.

### Run the game on the host and prove it

```bash
python3 tools/oracle.py tools/traces/boot-to-fight-and-save.txt --compare test-artifacts/c64/trace-fight-save
python3 tools/c64_trace.py tools/traces/boot-to-fight-and-save.txt --keep-ram      # VICE, RAM at each mark
python3 tools/oracle.py tools/traces/boot-to-fight-and-save.txt --keep-ram         # oracle, the same
```

Then diff `build/trace/<script>/NAME-ram.bin` against `build/oracle/<script>/NAME-ram.bin` for every mark and account for each differing byte. Expect the clock, the stack below the stack pointer, the replaced routine's own variables and anything an interrupt was in the middle of. Anything else is a finding.

### Check that the game is not writing into your own code

```bash
python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt --kernel-writes   # every kernel byte the run changed, by label
python3 port/atari/lockstep.py tools/traces/boot-to-menu.txt --pictures                  # also: is the display chip on the right list
```

Every changed byte should be a variable you know. Then list the unchanging pieces by label (`fixed` in `port/atari/build.py`) and compare them with the assembled files at every checkpoint. To see that the check works, build once without the redirection it guards and run it.

### Play the build in a second emulator

```bash
python3 port/atari/altirra_check.py          # AltirraSDL, its disk patch on
python3 port/atari/altirra_check.py --sio    # the OS ROM does the serial transfers; prints how many frames each load took
```

`port/atari/altirra.py` is the client: frames, memory, keys held in the matrix, ANTIC's registers, pictures. What the Atari writes is in `altirra.working_copy(disk, folder)`, not in the image file.

### Explore on the oracle, then write the script

```bash
python3 tools/oracle_explore.py tools/traces/boot-to-fight-and-save.txt dungeon 'LIIIIIJI|A|' --screen
python3 tools/area.py build/c64/original-v2-b/logical/06-RK.bin                 # the area's event squares and their text
python3 tools/area.py build/c64/original-v2-b/logical/06-RK.bin 14 0 W 13 5     # keys for a route
```

`|` marks a stop and prints where the party is. Read the area's handlers for squares worth visiting, compute the route, try it, and try the prompt that comes up. For a fight, loop: run to the key wait, read the text screen, choose a key from what the prompt offers. When the outcome is what the script needs, write the keys down as `press` lines. If the dice have to be different, set the wait counters with a `poke` after a `ready` and say why in a comment.

### Add a kind of step to the scripts

Put it in all three players or in none: `tools/c64_trace.py` (VICE monitor commands), `tools/oracle.py`, `port/atari/lockstep.py`. Try the idea on the oracle alone first. Then record the session in VICE, compare the oracle with it (`oracle.py SCRIPT --compare DIR`, and memory with `--keep-ram` on both), and only then run the Atari.

### Find every caller of an interface

For each decoded side, search for `20 lo hi` and `4C lo hi` for each entry address, then map each offset to the file (or fixed read) that contains it and that file's load address. Compare the list with the callers recorded in the traces. Matches outside any known file deserve a look: on side A they turned out to be shifted copies of known code.

## Mistakes worth not repeating

| Mistake | Cost | What to do instead |
| --- | --- | --- |
| Sending keys after fixed delays | A whole session that could not be reproduced; a party lost | Deliver each key at the game's first poll |
| Trusting screen memory for text | A dozen commands spent looking in the wrong place | Check the video mode first; hook the printer |
| Steering by screenshot | Slow, and wrong whenever a facing was misjudged | Decode position and the movement grid, compute routes |
| Assuming a shop leaves you facing it | A derailed script | Read position and facing after every new kind of action |
| A check that says pass or fail | A false alarm on the title load | Report counts and the moment of capture |
| Truncating tool output silently | Wasted runs on a fight that had already ended | Print in full, or say that output was cut |
| Leaving a working helper in a temporary folder | It nearly went undocumented | Move it into `tools/` once it has been used twice |
| Using a hook that the code never reaches (`ready` at a prompt with its own key loop) | A hung emulator | Give every emulator run a host timeout; know which prompts are special |
| Calling a result by a familiar name ("2-bit loader") before reading the code | A wrong statement in a report | Describe what the code does |
| Trusting a coverage figure before the dispatch tables were known | Code found by accident hid the missing tables | List the dispatch idioms first |
| Declaring code unreferenced after searching one file's context | A wrong entry in the unused list | Resolve tables across the files that call each other, then search |
| Classifying an indexed access by its operand | Two colour stores counted as sound | Use the address the access can reach |
| Reasoning about an inexplicable effect instead of bisecting the change | Six wrong theories about a dark text colour | Take the new code out a piece at a time and measure |
| Trusting an emulator screenshot taken the instant the program stops | Reference pictures missing the newest text; a false alarm about the oracle | Let a few frames pass first, in a run kept apart from the reference session |
| Taking equal output as equal state | A diverged random state went unnoticed in two sessions | Compare memory at checkpoints |
| Describing when a routine is called from its call site alone ("on every move") | A wrong statement in two documents | Check with coverage, or read the condition in front of the call |
| Redirecting only the source machine's hardware addresses that are hardware on the target too | The game stored into the kernel; every text screen was garbage | Redirect every access in the inventory; treat source hardware that is RAM on the target as the dangerous kind |
| Leaving your own code out of the memory comparison with nothing in its place | The overwritten instruction passed 62 checkpoints | Compare support code with its assembled image at every checkpoint |
| Blaming the emulator for an effect that changed when unrelated code moved | A wrong finding on record, and the real fault left in for two more commits | Find what is being written at the address the code moved away from |
| Committing a gallery after looking only at the pictures the work was about | Seven garbage pictures in the repository | Look at every picture, each time |
| Checking a save by reading the image file given to the emulator | A test that said nothing was written | Find where the emulator keeps writes, and whether they survive to the next run |
| An exploration tool that joined two runs with one extra pass of the key wait | A treasure that was not there when the keys became a script | Play one script whole and in pieces and compare memory before trusting the tool |
| A search with no known positive in it | Forty-two "no encounter" results, most of them wrong, from a string index that was off by one | Put a case you know the answer to in every search |

## What another game will probably do differently

- **Disk.** This loader replaced the DOS entirely and encrypted every sector. Another game may use KERNAL files, a different fastloader, or a real file system. The steps are the same: find the one interface, decode in your own code, prove against RAM.
- **Protection.** Here it only disabled saving and passes in VICE with a G64. Elsewhere it may stop the boot, in which case a cracked image may be the practical baseline; record that choice.
- **Text.** Many games use the character matrix throughout, and screen memory is then enough.
- **Randomness.** Other common seeds are the raster position, a free-running timer, or frame counts. Each needs its own rule for the reference run.
- **Areas as code.** This game stores each area's events as machine code in the area file. A game with data-driven events needs a table decoder instead of a pattern search.
- **Interpreted games.** If the game runs on a virtual machine (as Wizardry did on p-code), port the interpreter and leave the game alone. That is a different and usually smaller job.

## Open at the last entry

See the "Open", "Not yet known", "Not done" and "What it does not do" sections of [C64-LOADER.md](C64-LOADER.md), [C64-RUNTIME.md](C64-RUNTIME.md), [C64-CODE.md](C64-CODE.md) and [ORACLE.md](ORACLE.md). In short: most routines are unnamed and the view's geometry is unread (Phase 1, parked); the oracle has no sound record; of the choices before a fight only "attack" is recorded, and traps, a single death and raising are not; the three side-D areas that read keys themselves have not been run; 274 blocks on side A are never read. On the Atari: no sound, no measured play speed, and Atari's own OS ROM untried.

## 21 · 2026-10-11 · Translate all nine sound effects to POKEY · commit `321de256b43c544b246ba04657427d7bdd2f1ed5`

- **Goal.** Read `TODO.md` and implement sound while preserving original game code, data, RNG and saves. No commit or push requested.
- **Done and how.**
  1. Read the current specification, design, oracle and recent log entries. Baseline: 75 tests passed in the sandbox; two Altirra bridge tests could not open their socket. All three Altirra tests passed when rerun outside the sandbox, confirming the existing build was healthy.
  2. Decoded effects 1–9 through the original `$C557` setup, `$C60C` step and `$C62F` stop routines. Seven voice registers are copied by an indexed store, including pulse width and ADSR, not just the four addresses named in the TODO. Effects contain eight setup bytes, then four-byte steps; a zero low frequency byte terminates, and timer N lasts N+1 sound ticks. There are 21 nonzero pitches and 468 writes over all nine effects.
  3. Added optional SID state/trace to the host oracle, separate from its gameplay event stream. The 6502 core supplies an instruction write timestamp rather than the stale public cycle count. `tools/c64_sound.py --vice` traces all nine original effects independently in VICE PAL/true-drive; every register/value write equals the oracle, durations within one frame.
  4. Added `sound_update` to the kernel's VBI tail after the unchanged game IRQ. It uses joined POKEY channels 1+2, square tones with generated 16-bit pitch divisors, and approximate attack/decay/sustain/release. Falling gate releases; sound stop, sound-off, absent waveform, master zero or unknown pitch mute. No game zero page or sequencer bytes are written by the translator. DLI instructions stay unchanged.
  5. SIO temporarily owns POKEY: mute before OS entry, restore audio clock and keyboard scanning after OS exit, invalidate the pitch cache so the next eligible VBI restores the tone. The 84-byte pitch table occupies LOADER padding and the 32-byte envelope table TOP padding. UNDER carries code/state. Added both constant tables to kernel-integrity checking.
  6. Added `port/atari/sound_check.py`: invokes every original effect with a test trampoline in unused kernel padding, checks every audible frame's pitch and every ending, records actual PCM WAVs, and exercises all six key interruption cases plus sound-off. Added a one-shot original-effect probe to Altirra's existing save/restart/play check, with register restoration checked at every stop in both disk modes. No test trampoline is present in the assembled disk.
  7. Updated the specification, plan, runtime/oracle/design findings, TODO, 64 KB notes and new [SOUND.md](SOUND.md). The old "Open at the last entry" paragraph above is superseded for sound: there is now a sound record and audible Atari sound.
- **Result.** All nine effects produce PCM in Atari800; ranges 12,994–13,330 for signed 16-bit samples. All 21 pitches are within 0.1% of the PAL SID pitch. Key rules, release and sound-off pass. Altirra passes pitch/key-stop, save/restart and POKEY/keyboard restoration with and without real serial transfers. **79 tests pass** (142.539 seconds), including all eight lockstep scripts/106 checkpoints and all three identical saves. Still 35 redirected instructions and 70 changed disk bytes; no new comparison exclusions.
- **Evidence.** [Sound reference folder](../test-artifacts/sound/README.md), including all oracle/VICE writes, raw monitor output and the full-suite result. PCM WAVs and the Atari report are generated by `sound_check.py` in `build/atari/sound/`. Commands and limits are in [SOUND.md](SOUND.md).
- **Memory cost.** 366 extra bytes inside existing segments: LOADER 93, UNDER 241, TOP 32. No extra boot sectors or extended memory. Only 8 bytes remain spare in LOADER and 72 in UNDER; logged in [64K-NOTES.md](64K-NOTES.md).
- **Went wrong.**
  - A shortcut oracle menu script forgot to attach side B, then tried `ready` at the disk prompt's separate key loop. Stopped it and reused the recorded boot-to-menu script.
  - A direct Atari CPU/stack subroutine call preserved the return address but not flags. When it returned to the BEQ in the held key wait, the routine's changed Z flag made that branch consume an invented key and stop sound immediately. A register/flag-saving trampoline fixed the test; the production translator was not responsible.
  - An attempted positive sound check at character creation found no note: that flow has no sound call. Read its overlay, then explicitly invoked original effect 3 through a one-shot IRQ probe and checked that a real C key stopped it. Do not infer which UI action has sound without tracing its call.
  - Assembler `.res $FFE4-*` cannot use a relocatable current address as a constant. Computed TOP padding from the two local envelope labels instead.
  - Altirra bridge binding is blocked in the sandbox; checks require an approved execution outside it. This was also true on the untouched baseline.
- **Not done.** Exact SID timbres/pulse widths/exponential envelopes; PAL Atari or physical hardware; real-time pacing matching. The existing fake raster alternates split-mode sound stepping every second VBI. Left the sequencer unchanged and documented this for the speed/timing task. Game rules, random state and saves remain protected by the same comparisons.
- **Carries over.** Decode the effects and trace actual hardware writes before choosing a target sound scheme. Look through indexed stores, not only named register operands. Fit lookup tables into proven free kernel space and protect them with immutable-code checks. Treat keyboard, sound and serial I/O as shared ownership of one chip. Prove both register intent and non-flat PCM output. Debugger-style subroutine probes must preserve flags as well as registers when resuming at a conditional branch.

## 22 · 2026-10-11 · Fix transient text/graphics corruption and measure play speed · commit `321de256b43c544b246ba04657427d7bdd2f1ed5`

- **Goal.** Investigate the user's repeated `2` characters during text-to-graphics transitions and tackle TODO task 2: measure original C64 and Atari speed, improve the kernel, retain exact game logic/RNG/saves. No commit or push requested.
- **Done and how.**
  1. Added `port/atari/speed_check.py`. It forms the same six-character party with first-poll inputs, measures inn-to-town, movement, turning and character-screen transitions, captures each transition frame, and records PC/ANTIC/mode state. Ran the untouched sound-enabled build in Atari800 and AltirraSDL before production changes. Both give 94 frames inn-to-town, 38 per movement/turn, and 34 returning from a character sheet. Original VICE PAL/true-drive cycle stamps give 130–143 ms per movement/turn, 81 ms to a character sheet and 160 ms back; inn-to-town includes a 13.228-second real drive load.
  2. Read the shared text/colour memory and the game's mode setters. Confirmed on the captured frame 61 that `$0400` becomes bitmap colour bytes while ANTIC still reads it as text, before the fake bitmap-enable flag changes. The kernel delays publishing graphics until all 25 rows are converted, extending the garble. This is distinct from the CIA opcode overwrite fixed in entry 18.
  3. Changed the text list to a completed snapshot in display-bank `$4000`. Boot fills it with spaces; `rf_text` updates it from the game's text matrix. A `frame_ready` flag and VBI-controlled DMA blanking keep text/bitmap interpretation from changing while the shared display buffer is being overwritten. Graphics-to-graphics presentation stays as before. DLI's instruction sequence is unchanged.
  4. Added exact palette caches for rows 6–24 in 1,140 bytes of existing display padding. Uniform colour-RAM rows with matching 40-byte matrices reuse their palettes/mappings; varied rows may reuse mappings after their three selected colours match. No hashes, no assumptions that unchanged palettes mean unchanged pixels. Text-to-bitmap refresh bypasses all caches. Unrolled the pixel and distance-candidate loops, preserving tie order; aliased five address tables to recover 125 bytes.
  5. Added displayed-text byte checks and real-idle/positive-control measurements to the runner, plus 50 synthetic cached/full palette comparisons. The probe covers both padding layouts, matrix/colour changes, panel colours, high colour-RAM bits, equal histograms with different cell positions, and invalidation after text. Poisoned calculation scratch positively proves four uniform-cache hits. Added two regression tests.
  6. Compared all fourteen settled Atari800 before/after images: every RGB pixel identical. Inspected the captured old `2` frame, the retained inn and the blank conversion interval. Updated specification, plan, runtime/oracle/design findings, TODO, FIX handoff, 64 KB notes and new [SPEED.md](SPEED.md).
- **Result.** Both Atari emulators agree after the fix: inn-to-town 86 frames, step/right turn 35, left turn 34, character selection 26, sheet 6, return to town 26. Movement improves 8–11%; bitmap return 24%. The snapshot remains unchanged during both text-to-graphics actions, including the period before mode flags change. **81 tests pass in 137.606 seconds**, including all eight lockstep scripts / 106 checkpoints, three identical saves, ordinary keyboard play, all nine effects and Altirra with patched and real serial transfers. Still 35 redirected instructions / 70 changed disk bytes and no new comparison exclusions.
- **Evidence.** [Speed evidence](../test-artifacts/speed/README.md): both emulators' raw before/after frame states and transient pictures, VICE monitor stamps, full-suite log, cache probes and settled-pixel comparison. `python3 port/atari/speed_check.py` reproduces the Atari measurements, `--emulator vice` the original reference, and `--cache-probe` the synthetic checks. Final normal `build.py` rebuild restores the playable ATR after test builds.
- **Memory cost.** No new bank, main game RAM, or boot sector. Snapshot reuses the graphics buffer. Cache uses 1,140 of its 1,216 unused bytes. Net occupied kernel padding grows 288 bytes: UNDER 11, EXT 81, EXT2 196; boot code adds 19. Remaining free LOADER 8, UNDER 61, EXT 50, EXT2 173; the sound probes still have their 25-byte UNDER tail. Recorded in [64K-NOTES.md](64K-NOTES.md).
- **Went wrong / corrected.**
  - The old eleven-frame cycle estimate ignored display-DMA contention. Actual bitmap return was 34 frames; measure the actual machine before choosing a target.
  - The first transient detector used the fake bitmap-enable bit. A screenshot showed the colour writes happened earlier. Added checks of ANTIC's actual displayed bytes rather than trusting the delayed flag.
  - Initially suspected the timed GETIN refresh repeatedly copied an idle screen, and proposed an extra wait filter. Real-idle PC samples found no conversions: every poll updates its timestamp. Removed the filter. Artificially ageing the timestamp finds conversion in 58 of 60 frames, proving the negative result has a working positive control.
  - Considered a full raw-input cache in another extended bank. Verified against Atari800's banking implementation and Atari's 130XE manual that CPU and ANTIC cannot select different extended banks simultaneously. Did not implement that invalid design; used existing display padding instead.
  - A first mapping-only cache saved four frames on character selection but just one on movement; retained an exact uniform-input shortcut and measured the final combined scheme. Unrolling increased the cell-loop branch beyond 6502 relative range; replaced it with a conditional exit and absolute jump.
  - Altirra's local socket requires approved execution outside the sandbox. Its working emulator directories contain disposable disk/config copies and are ignored by Git.
- **Not done.** C64-speed play: all bitmap bytes still require conversion and walking still takes 567–584 ms, versus 130–143 ms on the PAL C64. Text snapshots add approximately one frame to small text actions. Mode transitions now have a brief black conversion interval. Exact sound pacing across display modes, PAL/physical hardware, Atari OS and whole-game visual coverage remain open. Earlier "Open at the last entry" claims of no sound or no measured play speed are superseded by entries 21–22.
- **Carries over.** Test transitions as well as settled frames. A logical mode flag may change after the memory has already been repurposed. Publish completed display buffers; gate the display while changing their interpretation. Cache exact inputs and retain a full-calculation path to test invalidation. Use hardware banking rules, not an assumed independent selector. Include DMA in timing. A profiler's negative finding needs a known positive control, and a disproved theory should be removed from both code and conclusions.

## 23 · 2026-10-11 · Publish sound and display work to Git and Gitea · commit `321de256b43c544b246ba04657427d7bdd2f1ed5`

- **Goal.** The owner now requests committing the completed work and pushing it to Gitea using `~/.config/gitea/`. Entries 21–22 describe the implementation and validation before publication was requested.
- **Done and how.** Reviewed the code, findings, tests and captured evidence. Refreshed the TODO and sound documentation to reflect both completed tasks. Fetched `gitea/main` and confirmed it matches the local starting commit. Prepare one implementation commit on `main`, followed by the required metadata commit filling in the hashes of entries 21–23, then push and verify the remote head. Authentication uses an external askpass helper reading the configured token; credentials are never placed in the remote URL or repository.
- **Validation.** The unchanged implementation already passed all 81 tests in 137.606 seconds (entry 22); the normal playable ATR was rebuilt afterwards. Commit review also checks whitespace and the readability of all 904 captured PNGs. No implementation changes or additional test run are needed for publication.
- **Scope.** Include sound, transition/speed changes, FIX/TODO handoffs, regression tests and reproducible evidence. Keep the local `resume.sh` session helper untracked and generated ATR/emulator working copies ignored. Original game inputs and the sibling project remain untouched.
- **Carries over.** Preserve the implementation/log-hash two-commit convention. Verify the pushed branch against the local commit without exposing credentials. Remote verification takes place after the two commits.

- **Review note.** Source and documentation whitespace checks are clean. Raw VICE launch logs retain the emulator’s emitted trailing spaces as part of the original evidence.

## 24 · 2026-10-11 · Investigate the remaining graphics-to-text report · commit `a72ff09212df529cf67f00dceb6f36686cc94207`

- **Goal.** Investigate the owner's right-window `2`s when opening character information in Windows Atari800. No commit/push requested for this follow-up.
- **Done.** Read the original mode setters and kernel refresh/VBI publication. Found the initial generated ATR disagreed with current layout readiness state; rebuilt the normal playable image. Promoted repeated scratch captures into `port/atari/transition_check.py`: normal POKEY keys, six supplied characters, direct character-sheet inputs, varied starting delay, forty screenshots per action, settled display-list and immutable main-memory kernel checks. Inspected all 240 final frames and recorded state/contact sheets. Updated FIX/TODO and findings documents. Supplied an identical distinctly named ATR to make the loaded version clear.
- **Result.** Six settled checks and kernel integrity pass. Captures show old/partial graphics, a blank interval, then correct text; no repeated `2` window. This is not a reproduced or newly fixed Windows bug. No production kernel/game code, patches, comparison exclusions, target memory or boot sectors changed. The earlier full suite remains the runtime validation; this follow-up ran the new targeted ordinary-key capture, not another full suite.
- **Evidence.** [Reverse captures](../test-artifacts/reverse/README.md); [handoff](../FIX.md). Fresh playable image SHA-256 `0039e59910fc729cecb11f7a12cd20ff76801acc353f4f0c8fc7f1f59e5ba17a`, 732944 bytes, test mode false. The initial mismatched image's hash was not retained; its exact origin is unknown.
- **Went wrong.** A scratch `#` key used the real keyboard's SHIFT-stripping translation and opened character 3 instead of reproducing the scripted `$23` action; changed the capture to direct digits. Trying to vary the view with turns at the inn door triggered its sign-in question, invalidating that attempt; removed the turns. These failed scratch runs are not included in final evidence.
- **Open.** Confirm the Windows disk hash/full launch command/emulator version/OS and exact failing input sequence if the fresh disk still fails. Settled pictures or sampled register flags cannot dismiss a transient report. The SHIFT translation limitation is separate and untouched.
- **Carries over.** Distinguish compiled artifacts from source revisions. Replay actual keyboard actions, and verify that a probe has reached the intended UI before interpreting screenshots. Preserve both positive reproductions and limits; do not invent an additional runtime patch from a failure that has not been reproduced.

## 25 · 2026-10-11 · Deep graphics performance analysis · commit `a72ff09212df529cf67f00dceb6f36686cc94207`

- **Goal.** The owner confirms the freshly recopied disk no longer shows `2`s, attributes the prior report to copying the wrong ATR, and requests a deep performance investigation focused on graphics. This closes entry 24's open report; no new corruption patch needed. No commit/push or production optimization requested.
- **Done.** Added `graphics_profile.py` with temporary instruction-preserving Atari800 RAM escape probes for key/refresh/row/palette/cell/DLI boundaries. Used the native scanline clock for elapsed time and a traced host execution of each real snapshot for CPU attribution, adding page penalties omitted by the oracle core. Compared host output against all native converted buffers/palettes. Profiled original game routines on the oracle. Ran uninstrumented controls, conversion bypass and DMA blanking diagnostics; compared game bytes under unchanged rules, settled images and frame counts. Read cache/banking constraints and proved a narrower idempotent-mapping row-reuse predicate against full native output with a pair-swapping negative control.
- **Result.** Walking: 35 frames / 575.74 ms precise interval; 135.16 ms game/other kernel work and 440.58 ms conversion (76.5%). Conversion consumes 414,862 CPU instruction cycles but 788,538 elapsed cycles, with 637 DLIs. Pixels are 37%, palettes 32%, setup/advance about 31% of conversion CPU work. Only 336 of 1,000 cells change. Nine unchanged lower rows cost 118,570 CPU cycles. Bypass gives 8 frames with stale graphics; blanking 24 with a black flash. These are bounds, not fixes. Recommendations: five-byte repeated-page guard, identity-copy path, then exact unchanged-row reuse without a full raw cache.
- **Validation.** Normal probes exactly match control action frames, seven game-byte hashes and seven settled RGB images. Blank/skip preserve the compared game bytes; blank retains final images, skip deliberately fails image equality. All seven host refresh outputs equal native, including cache padding and palettes. Two existing speed/cache tests pass in 2.399 seconds (50 palette cases included). No new exclusions or production runtime changes, so the full suite was not repeated. Normal playable ATR restored, test mode false, same SHA-256 `0039e59910fc729cecb11f7a12cd20ff76801acc353f4f0c8fc7f1f59e5ba17a`.
- **Evidence.** [Analysis and implementation handoff](GRAPHICS-PERFORMANCE.md), [raw controls/reports/snapshots/pictures](../test-artifacts/graphics-profile/README.md). Original game/build/assembly sources and sibling project unchanged. Updated FIX/TODO/specification/plan/design/runtime/oracle/memory findings.
- **Memory.** No target allocation change. The row shortcut might use 26 bytes in the existing 44-byte `$63D4–$63FF` tail; the remap-page guard needs no cache bytes. Estimates and code-fit limits are recorded in the handoff, not claimed as implemented gains.
- **Went wrong.** ca65 repeated operand aliases `table0…7` are absent from ld65's labels; first probe failed on that lookup. Derived and checked all eight positions from the assembled EXT image instead. The initial candidate analyzer inspected invalid palette-cache bytes after text before checking validity; moved the validity check before interpreting them. A Matplotlib plotting attempt found the package missing; kept tables and a Mermaid pipeline diagram without adding dependencies. Failed scratch runs were superseded by the final controls.
- **Open / limits.** No optimized assembly path yet. Estimated savings require actual benchmarks and full fidelity/visual validation when implemented. This profile covers one NTSC Atari800 town route; the native probes were not repeated in Altirra, PAL or hardware. Native timer resolution is a scanline, host CPU sums exclude DMA/interrupts, and original-game oracle IRQ pacing remains its existing approximation. Scripted `#` is distinct from the normal keyboard's currently limited SHIFT translation.
- **Carries over.** Separate game drawing from target presentation; separate CPU instructions from DMA/interrupt elapsed time. Validate instrumentation against an uninstrumented control. Measure what changes before allocating a raw cache. Existing converted output can sometimes prove unchanged rendering through exact fixed-point conditions, but require unchanged mappings and reject non-idempotent transforms. Keep diagnostic upper bounds distinct from playable optimizations.

## 26 · 2026-10-11 · Implement all three graphics conversion optimizations · commit `a72ff09212df529cf67f00dceb6f36686cc94207`

- **Goal.** The owner authorizes all three proposals from entry 25: skip
  redundant lookup-page operand writes, directly copy identity mappings and
  exactly reuse unchanged rows. No commit or push requested.
- **Done and how.** Added a page guard keeping all eight lookup operands
  coherent, an unrolled identity path that rejoins shared pointer advancement,
  and a 320-byte exact row check. Qualification requires every used mapping
  to be idempotent and is saved only with uniform palette records. Only a
  later exact input hit can authorize reuse; cold/text/varied/missed rows
  fall back. Both pointers are restored after either compare half fails.
  Added 25 row flags plus one exact-hit byte in display padding. Moved 32
  palette-scratch bytes to UNDER and explicitly reserved the existing native
  probe trampoline. Updated sound/Altirra helpers and idle/profile code labels.
- **Result, checked in Atari800 NTSC.** Steps/turns 34–35 → 30 frames,
  scripted character prompt 26 → 21, sheet return 26 → 25, town entry/sheet
  unchanged at 86/6. Walking conversion 440.58 → 364.08 ms and 414,862 →
  342,179 CPU cycles (17.4% elapsed / 17.5% CPU reduction). All nine lower
  rows reuse their pixels, so 640 rather than 1,000 cells are converted.
  Gains are combined measurements; they are not sums of prototype estimates.
- **Validation.** Seven native benchmark endpoints retain identical baseline
  game-byte hashes and RGB pixels under existing rules. Host snapshot replay
  reproduces optimized native output. New `graphics_check.py` compares 24
  complete real/adversarial refreshes with the captured original kernel,
  checks all 16 mapping qualifications, all 256 source values through each
  lookup, mixed identity/page changes and the swapping negative. Existing
  50 palette cases still pass. Full suite: 82 tests attempted, 80 pass inside
  the sandbox; only the two known Altirra socket checks fail there. All three
  Altirra tests pass outside it (52.862 s), including both disk modes,
  sound/keyboard restoration, save/restart and play. Thus all 82 unique tests
  pass with the required access. No new exclusions or hardware redirections.
- **Final emulator comparison.** Altirra takes 30 / 31 / 30 movement frames,
  21 at the scripted prompt and 25 returning to town; entry/sheet remain 86/6.
  Its left differs by one frame from Atari800. All seven final pictures match
  its baseline, giving fourteen unchanged pictures across the emulators.
  An uninstrumented Atari800 control also matches all seven instrumented
  frame counts, game hashes and images. Both ordinary idle checks find zero
  refresh frames with a working forced-refresh positive control. The final
  three targeted speed tests are rerun after tightening frame limits.
- **Evidence.** [Implementation report](GRAPHICS-PERFORMANCE.md), [timings,
  snapshots, pixels, differential checks and raw test logs](../test-artifacts/graphics-optimized/README.md).
  Standing specification, plan, design/runtime/oracle/TODO and memory notes
  updated. Original game files and sibling project are untouched.
- **Memory.** Existing bank/boot-sector count unchanged. 26 display-padding
  bytes at `$63D4–$63ED`; 50 padding bytes remain. Segment occupation grows
  UNDER 57 (including the 25-byte explicit probe reserve), EXT 20, EXT2 147
  (net of moved scratch). Spare LOADER 8, UNDER 4, EXT 30, EXT2 26.
- **Went wrong.** Relative branches could not reach the next-row exit or
  the identity routine in EXT2; used conditional skips plus absolute jumps.
  Initially moving all 48 scratch bytes consumed the test trampoline and
  moved the idle sampler's upper boundary into main memory, causing false
  conversion samples. Reserved the trampoline, moved only 32 bytes and
  bounded the sampler with actual code labels. A warm host fixture injected
  the new kernel into old already-valid palette records without generating
  new qualifications, so it correctly did not reuse rows; initialized through
  a cold miss before asserting warm skips. A high-bit-only RAM fixture also
  changed the low nibble; corrected it to preserve the actual nibble. Constant
  qualification addresses were absent from ld65 labels; explicitly exported
  them. All corrected cases pass. Sandbox Altirra bridge failures were rerun
  with approved access rather than misdiagnosed as regressions.
- **Limits / next.** Movement still needs about half a second. Upper-row
  palette scanning and DMA/interrupt contention remain major costs. This
  is one town graphics route plus broader game-state regression, not full
  artwork validation. PAL, Atari ROM/hardware and real-time sound pacing
  remain open. No flash-on-every-step blanking or raw 10 KB cache was added.
- **Carries over.** Qualify cached output using exact mathematical conditions,
  then test complete fallback output at boundary failures. Keep a captured
  pre-change kernel as an independent differential reference. Treat code,
  scratch and test trampolines as separate allocated regions; instrumentation
  boundaries must follow code when data moves. Measure final combined gains.
- **Playable artifact.** Normal build restored after every test/benchmark;
  final `build/atari/mm1.atr` and distinctly named `mm1-graphics-fast.atr`
  are identical, test mode false, 732,944 bytes, SHA-256
  `d19423e3597b82df2c4b5be4974f51e7cf3f0867c35035465293fc729d7ac06e`.
  Final targeted tests: three pass in 4.279 s. Source whitespace checks pass;
  no commit/push made during implementation.

## 27 · 2026-10-11 · Publish graphics profiling and optimizations · commit `a72ff09212df529cf67f00dceb6f36686cc94207`

- **Goal.** The owner requests committing the completed work locally and to
  Gitea, then recommending the next task. Entries 24–26 retain the earlier
  investigation and implementation chronology.
- **Done and how.** Reviewed the kernel, regression/profiling helpers,
  findings and evidence; checked whitespace, all 358 retained PNGs and the
  final playable disk's hash/test-mode flag. Fetched Gitea and checked that
  its main branch matches the local starting commit. Publish one implementation
  commit containing entries 24–27, followed by the required metadata commit
  filling in their hashes, then push main and verify the remote head.
  Authentication uses the external askpass helper and configured token;
  no credentials enter repository files or the remote URL.
- **Validation.** Entry 26's all-82-test result, fourteen unchanged emulator
  benchmark endpoints, matched uninstrumented control and normal playable
  disk remain the runtime validation. No implementation change or repeated
  full suite is needed for publication. Source whitespace is clean.
- **Scope.** Include the reverse-transition follow-up, deep analysis,
  three-path graphics optimization, tests, current findings and reproducible
  evidence. Keep the unrelated local `resume.sh`, generated ATRs and emulator
  working copies out of the commits. Original game files/sibling untouched.
- **Next recommendation, checked/read.** Upper-row palette work now accounts
  for 39.0% of walking conversion CPU time (133,362 / 342,179 cycles). Profile
  it across town, outdoors and battle screens, then test specialization for
  repeated view/panel colour-RAM patterns with exact fallback. Do not assume
  unchanged matrices during movement or cache a lossy hash. Code space is
  tight (UNDER 4, EXT 30, EXT2 26 spare); prove layout before choosing a new
  cache. Disk loading remains the following TODO item and a separate route
  to improving startup/area-change experience.
- **Carries over.** Preserve the implementation/log-hash two-commit rule,
  verify the pushed branch against the local head, and distinguish remaining
  measured bottlenecks from unbenchmarked optimization ideas.

## 28 · 2026-10-11 · Optimize repeated palette mappings · commit `8b43c5891182ee83dab9dedbf763affe92fbf901`

- **Goal.** The owner requests investigating and optimizing palette work
  after the three graphics paths. No new commit/push requested.
- **Done and how.** Captured nine native settled town/outdoor/dungeon/arena/
  encounter/fight states through existing first-poll routes and checked a
  captured old-kernel reference before changing code. Walking rows rebuild
  identical ordered selected-colour mappings 13 of 16 times. Added a three-
  byte live-mapping key and exact comparison before nearest-colour calculation.
  A match reuses pair/pair4; a miss computes and records the original mapping.
  Cached restores invalidate the key; boot initializes it to three `$FF`s.
  Selection, distance/tie order and per-row panel palettes are unchanged.
  Moved the idempotence table to EXT and bounded the idle sampler by an
  explicit code-end label. Profiling distinguishes actual rebuilds from hits.
- **Result, checked.** Walking palette CPU 133,362 → 107,041 (-19.7%), full
  conversion CPU 342,179 → 315,858 (-7.7%), elapsed 364.08 → 334.52 ms
  (-8.1%). Thirteen shared hits leave three rebuilds and nine cached restores.
  Atari800 movement 30 → 29 frames; Altirra forward/right 30 → 29 and left
  31 → 29. Both town entry 86 → 85 and return 25 → 24; prompt/sheet 21/6
  unchanged. Settled bitmap palette re-refreshes save 0.8–6.4% in the broader
  host profiles; those are instruction counts, not outdoor action timings.
  Sampled fight commands are text mode, with zero palette work or benefit.
- **Validation.** All 83 tests pass in 147.025 s with approved Altirra socket
  access, including the eight lockstep sessions/106 checkpoints, three exact
  saves, nine sounds, keyboard and both disk modes. New regression compares
  nine complete refreshes and 228 palette calls to the independent old kernel:
  cold/warm/uncached/uniform/varied/matrix/permutation/high-bit/tie/black cases,
  positive hits and build-A/build-B/restore-A/request-B invalidation. The old
  host refresh reproduces its native snapshot. All fourteen benchmark images
  and nine broader captures retain exact RGB pixels; Atari800 game hashes
  retain existing comparison rules. All seven new host snapshots reproduce
  native output/cache/palettes, and the uninstrumented control matches probe
  frames/game hashes/pixels. Both idle checks retain a working positive control.
  No original game edits, new redirections, exclusions or oracle timing rules.
- **Evidence.** [Palette performance report](PALETTE-PERFORMANCE.md),
  [snapshots, reference/optimized profiles, endpoint comparisons and logs](../test-artifacts/palette/README.md).
  Updated standing specification/plan/runtime/design/oracle/memory/TODO and
  speed findings. `palette_check.py` makes captures/checks reproducible.
  `--settled-only` saves repeated benchmark PNG work while still checking
  every transition frame state/text byte. Default transient capture remains.
- **Memory.** 32 extra code bytes and three mutable bytes at `$DFFC–$DFFE`.
  Net segment growth UNDER 3, EXT 16, EXT2 16 after moving the existing
  16-byte constant. Spare LOADER 8, UNDER 1, EXT 14, EXT2 10. Display padding,
  25-byte test trampoline, bank count and boot-sector count unchanged.
- **Went wrong.** First copied all three cached colours into the key after
  each restore, adding enough cost to slow settled town palette work by 0.4%.
  Cheap invalidation instead preserves safety and produces a 0.8% reduction.
  An early direct-call reference injected old EXT data after setting the
  requested row, resetting it to row 24; set the row after kernel injection,
  then verified the unchanged baseline first. Kernels injected into old
  snapshots must also initialize the new key as boot does; added this to
  both differential helpers. Moving a constant changed a sampler boundary;
  use code-end labels rather than data addresses.
- **Playable artifact.** Normal build restored after tests and benchmarks,
  with identical `mm1.atr` / `mm1-palette-fast.atr`, test mode false,
  732,944 bytes and SHA-256
  `6f153c9b8e91117a2f37684e8597c43bb7162a1cc5f5ea97d9ace166665faf91`.
- **Open / limits.** Movement still takes 29 NTSC frames; palette histograms,
  pixel work and DMA/interrupt contention remain. Code space is almost full.
  No outdoor movement-latency or whole-game artwork claim; sampled battle
  text cannot benefit from bitmap palette work. PAL, Atari ROM/hardware and
  real-time sound pacing remain open. Disk loading is the next separate TODO
  optimization. No sibling changes or commit/push during this implementation.
- **Carries over.** Reuse exact computed results after normalizing the real
  inputs. An ordered selected-palette key can be cheaper than a new raw-input
  cache. Every writer of cached output must update or invalidate its key.
  Compare complete output with independent old code, include warm/negative
  paths, and separate settled re-refresh CPU savings from native action times.

## 29 · 2026-10-11 · Publish palette optimization · commit `8b43c5891182ee83dab9dedbf763affe92fbf901`

- **Goal.** The owner requests committing locally and to Gitea, then a
  recommendation for the next task. Entry 28 records the implementation.
- **Done and how.** Reviewed the code, findings, regression and 160 evidence
  files; all 102 retained PNGs decode correctly. Checked the old/new endpoint
  comparisons, whitespace and normal playable ATR hash/test-mode flag.
  Fetched Gitea and confirmed main matches the local starting commit.
  Publish an implementation commit, then the required metadata commit filling
  entries 28–29 with its hash, push main and verify the remote head.
  The external askpass helper reads the configured token; credentials are
  absent from repository files and the remote URL.
- **Validation.** The unchanged runtime passed all 83 tests in 147.025 s,
  including both Altirra disk modes, all game-state/save checks and the new
  228-case palette differential regression. Fourteen benchmark endpoint
  images and nine broader captures remain identical. The normal disk matches
  entry 28's validated hash. Publication changes no runtime code and does
  not require repeating that suite.
- **Scope.** Include palette reuse, updated profiling/check helpers and
  benchmark option, test, findings and reproducible evidence. Generated ATRs,
  emulator working copies and unrelated local `resume.sh` remain outside
  the commits. Original game files and sibling project are untouched.
- **Next recommendation, read/checked.** Tackle TODO item 3: disk load times.
  Measure boot, area changes and saves in the normal Atari800/Altirra setups
  first, separating disk transfer time from loader/OS-switch work. Previous
  standard serial Altirra timings were 52 s to the first prompt and 11 s
  inn-to-town; these are not timings for fast patched-SIO emulator settings.
  Investigate unneeded initial memory-image loads and repeated sector/SIO
  work, then benchmark any change with exact game-state/save validation.
  Graphics support code has only UNDER 1, EXT 14 and EXT2 10 spare bytes;
  further additions require explicit layout planning.
- **Carries over.** Preserve the implementation/log-hash two-commit rule,
  authenticate without embedding tokens, and verify the remote branch after
  publication. Measure the owner's actual emulator configuration before
  choosing the next optimization.

## 30 · 2026-10-11 · Restore held Ctrl+A combat input · commit `b6d8ea9fb842713ad4d4fa974a477fd9f16b3edb`

- **Goal.** The owner reports that Ctrl+A works for one character but cannot
  be held across characters, and asks for investigation/fix. No commit/push
  requested for this implementation.
- **Read / reference.** Atari `keyboard` returned immediately for every
  sample equal to `last_code`. The original `GO` enables all-key repeat at
  `$028A`; KERNAL `$EA87` uses `$028C/$028B`, and game `$C648` adjusts the
  delay and swallows Ctrl+A during effect 5. `CM` accepts `$01` and selects
  attack, shooting or block. New six-command first-poll trace matches 149
  VICE/oracle events and ten Atari game-state checkpoints.
- **Done and how.** Repeated held keys now follow the enabled flag and the
  original counters, reload at four eligible scans and enqueue only into an
  empty buffer. Fresh presses set the initial delay; release resets the
  latch. Translation and the original reader/dispatcher remain unchanged.
  Share the test trampoline with the loader's idle sector buffer, move the
  matrix histogram to EXT and row/cell state to UNDER to fit. Updated old/new
  kernel-injection helpers to migrate row palettes in both directions.
- **Result, checked.** A 600-frame physical Ctrl+A hold on the previous
  build produces one combat command; another press advances the next
  character. The new Atari800 build produces 18 commands across all six
  characters in three rounds and wins; release stops new commands after a
  pending key drains. Altirra physical KEYRAW holding also visits all six in
  rounds 1–3, wins and stops filling the buffer after release. Both final
  pictures were inspected and show the victory/250 XP message correctly.
- **Validation.** All 85 tests pass in 155.824 s with Altirra socket access,
  including nine scripts / 116 game-state checkpoints, three exact saves,
  sound, keyboard play, both disk modes and all palette/graphics checks.
  Eight host cases execute the original C64 ROM scanner with a CIA key matrix
  and original reader, matching enabled-letter queue/delay/rate/CTRL state:
  plain/control A, disabled/default letter repeat, backpressure, effect 5,
  release/repress and changed key. Two new regressions cover those cases and
  real held combat. No comparison exclusions or original game-file edits.
  Normal physical input has timing-dependent RNG; no first-poll equivalence
  claim is made for its damage transcript.
- **Evidence.** [Keyboard report](KEYBOARD-REPEAT.md), [ROM comparisons,
  old/new/Altirra holds, original C64 trace and logs](../test-artifacts/keyboard-repeat/README.md).
  The native observer replaces only emulator RAM at `$0E45`, emulates its
  JSR/stack/six cycles and is removed afterwards. No script key is supplied
  during the physical hold. Standing findings/TODO/specification/plan and
  memory notes are updated; original game and sibling files untouched.
- **Memory.** 39 extra keyboard code bytes, no new repeat state. Reclaim the
  25-byte dedicated test reserve by aliasing the existing 128-byte SIO buffer;
  probes finish while SIO is idle and buffered reads replace it before use.
  Move 16 histogram bytes to EXT and two row/cell bytes to UNDER. Net segment
  occupation UNDER 0, EXT +14, LOADER/EXT2 0; spare 8 / 1 / 0 / 10. No new
  bank, display allocation, boot sector or hardware redirection.
- **Went wrong.** The first scanner reference copied the reader only through
  its final CMP operand, omitting RTS; extended the slice through `$C69D`.
  The first native observer assumed `$0E44` was JSR, but it is PHA; moved to
  `$0E45` and accounted for the pushed key when reading the caller. Moving
  row-register arrays invalidated warm old/new snapshot injection: migrate
  all four palettes using the source/target labels before either direction
  of code replacement. Corrected all fixtures and retained full cache checks.
  The initial trace comment misnamed the shooting fallback as casting;
  decoded the `$20F9` branches and corrected it. No engine rule changed.
- **Playable artifact.** Normal disk restored after checks, with identical
  `mm1.atr` / `mm1-held-keys.atr`, test mode false, 732,944 bytes, SHA-256
  `02467f68ec64a75508ee3fe86dc2054bd25168ac91dbcdfd527a4d91864c816c`.
- **Limits / next.** The game-controlled initial delay remains; release can
  leave one already queued key. This adds the all-key repeat path used by
  the game, while default special-key repeat/SHIFT translation remain the
  prior scope. PAL, Atari ROM/hardware and real-time sound pacing remain open.
  Code space is full in EXT; disk-load work still needs measured planning.
- **Carries over.** Keep input-level repeat under the original application's
  controls, preserve debounce and queue limits, and test a held key in an
  actual multi-prompt workflow. Use original ROM code as the reference for
  scanner counters and original game traces for command semantics. Scratch
  reuse needs an explicit lifetime; historical snapshots need data migration
  when a new kernel's label layout changes.

## 31 · 2026-10-11 · Publish held-key repeat and recommend next work · commit `b6d8ea9fb842713ad4d4fa974a477fd9f16b3edb`

- **Goal.** The owner asks to commit to Git and Gitea, and recommend the next
  task. Publication of entry 30's completed fix is authorized.
- **Read / checked.** Reviewed the working tree, entry 30, TODO, test logs,
  evidence images and the normal ATR manifest/hash. All 85 tests passed in
  155.824 s; the normal disk matches the validated artifact and has test mode
  disabled. Fetched Gitea: its main and local HEAD both start at `975add50`.
- **Done and how.** Commit the keyboard fix, reference/physical-input checks,
  original Ctrl+A trace, documentation and reproducible evidence. Follow with
  the required metadata commit filling entries 30–31 with the implementation
  hash, push main, then fetch and compare local/remote heads. Use the existing
  external askpass helper; no credentials enter the repository or remote URL.
- **Scope / validation.** Generated disks, ignored emulator working copies
  and unrelated local `resume.sh` stay outside the commits. Original game
  files and the sibling project are untouched. Whitespace checks are clean;
  all evidence PNGs decode. Publication requires no further runtime changes
  or repeat of the completed suite. Staging also checks previously untracked
  files: source/docs/data are whitespace-clean; raw VICE/trace logs retain
  their emitted trailing spaces, including significant screen-text spaces.
- **Next recommendation, read/checked.** TODO item 3: disk loading. Measure
  startup, area changes and saves using the owner's normal emulator settings
  before choosing a change. Separate transfers from loader/OS-switch work;
  investigate unneeded initial memory-image loads and repeated sector/SIO
  calls. Earlier 52 s boot / 11 s inn-to-town measurements used standard true
  serial SIO, not fast patched-SIO settings. Benchmark improvements against
  exact game-state/save checks. Spare LOADER 8, UNDER 1, EXT 0 and EXT2 10
  bytes require explicit layout planning for additions.
- **Went wrong / carries over.** The full staged whitespace check flags the
  raw trace/emulator logs; preserve this evidence and check the other files
  separately. No new runtime issue found. Keep the
  implementation/log-hash two-commit rule, authenticate without embedded
  tokens and verify the remote after pushing. Base performance priorities
  on the emulator configuration actually used for play.

## 32 · 2026-10-11 · Measure and improve disk loading · commit `f1f3cbc2e30fccd3de1524ee5feaebf79a4bfff7`

- **Goal.** The owner asks to tackle TODO #3 and report how it goes. Implement
  useful disk-loading improvements after measuring normal patched-SIO waits
  and standard serial transfers. No commit or push requested in this turn.
- **Read / baseline.** Read specification, design, oracle, TODO, loader/build/
  boot and emulator harnesses. Starting tree has only unrelated `resume.sh`;
  85 tests pass in 157.215 s. Atari800 patched boot 251 frames, options 26,
  town 85, sign-in/save/reload 33. Explicitly cold-reset Altirra patched boot
  230 frames; serial boot 3,110. Every old sector pays OS/zero-page/IRQ/sound
  setup and restoration; the captured startup `$E000–$FF49` is all zero.
- **Done and how.** Keep the OS enabled across consecutive direct reads or
  writes; restore game zero page, bank, IRQ and sound/keyboard before bounce
  copies and return. Share the sector counter with the DCB word and replace
  PHA/PLA advance accounting with a saved count to fit. Boot clears the exact
  8,010-byte zero range; the build asserts it remains zero. Remove 63 kernel
  reads and 8,192 padded payload bytes. Original game/sibling files unchanged.
- **Result, checked.** Atari800 patched boot 251 → 77 frames (4.189 → 1.285 s),
  options 26 → 6, town 85 → 47 (1.419 → 0.784 s), sign-in 33 → 16
  (0.551 → 0.267 s). Altirra patched boot 230 → 56 (3.838 → 0.935 s),
  options/town agree, sign-in 35 → 16. Altirra standard serial boot
  3,110 → 2,650 frames (51.900 → 44.223 s), town 650 → 610 (10.847 →
  10.180 s). Serial samples are ten frames; its sign-in difference of one
  bin is not a meaningful save-speed claim. Sign-in includes inn reloads,
  unlike the historical 1.8-second write-only measurement.
- **Attribution, checked.** Isolated native controls: baseline 251-frame boot,
  batching only 103, zero-fill only 226, combined 77. Runtime gains come from
  batching. Native probes confirm eight direct sectors use 16 → 2 swaps;
  the 18-sector patterned write uses 36 → 2. Zero-length reads use none.
  Kernel boot reads 527 → 464; OS bootstrap remains 56 sectors. Net LOADER
  +3 bytes, spare LOADER / UNDER / EXT / EXT2 5 / 1 / 0 / 10; no new buffer,
  bank, boot sector or disk-sector format. Four game-side payloads are equal.
- **Validation.** All 86 tests pass in 151.729 s: nine scripts / 116 exact
  game-state checkpoints, three saves, cold-start reload, sound, held keys,
  ordinary keyboard, graphics/palettes and both Altirra disk modes. New native
  test checks 15 exact reads with guards, all sides, partial sectors, offsets,
  ROM-covered destinations and direct-to-bounce transitions, plus a
  2,304-byte write and unaligned readback; original-kernel positive control
  passes the same data checks. Verify zero page, IRQ, PORTB, return flags/
  registers/$FC–$FF and immutable code. Temporary LDX observation preserves
  instructions/cycles; trampoline lives at free `$FFE7`, restored afterwards.
  No comparison exclusions or new game operand redirections. Targeted test
  rerun passes after helper CLI normal-build cleanup changes.
- **Evidence / documentation.** [Findings](DISK-PERFORMANCE.md), [reports,
  isolated controls, original kernel, logs and fifty pictures](../test-artifacts/disk-loading/README.md).
  All final PNGs decoded and visually inspected after capture processes
  finish. Five before/after native settled images are pixel-identical.
  Spec/plan/TODO/design/runtime/oracle/speed/memory notes are updated. Normal
  `mm1.atr` / `mm1-disk-fast.atr` restored, identical, test mode false,
  724,752 bytes, SHA-256
  `4132030ed4dcbc9f2333748361a6b0b2c77a2a4e69f275ece4c1e0628721418c`.
- **Went wrong.** ca65's non-local operand alias reset a cheap-label scope;
  make the boot zero-loop label non-local. The first short route turned
  before leaving the inn square; the original oracle confirms I/J/J/I.
  Searching `$0400` for the innkeeper text was invalid because it is drawn
  into a bitmap. The first disk comparison ran before Atari800 flushed its
  buffered writes; compare after exit. A `/tmp/build.py` import lacked enough
  parent directories for ROOT; control compilation preserves the original
  module's file context while redirecting output/source into `/tmp`.
  Early pictures captured unpublished/black frames; wait two VBIs outside
  the timing interval. Altirra startup had uncounted pre-bridge frames;
  issue COLD_RESET after configuring SIO and then count from zero. Final
  evidence replaces these preliminary measurements/captures.
- **Limits / next.** Serial transfers still dominate. High-speed negotiation,
  larger sectors and exact compression of title patterns remain possible
  follow-ups, unimplemented/unmeasured here. Larger buffers/code need layout
  planning. Other startup leftovers are retained; no assumption of unused
  memory or weakened equality check. PAL, Atari OS ROM and hardware are not
  covered by these emulator measurements.
- **Carries over.** Measure patched and true-serial modes separately. Batch
  expensive machine-context switches where the whole transfer can use one
  context, restoring before copies that need hidden RAM. Assert deterministic
  startup data before replacing disk reads with generated state. Preserve
  disk and RAM equivalence, flush emulator writes before checking them, and
  isolate probe lifetime from buffers that the operation itself overwrites.

## 33 · 2026-10-11 · Publish disk-loading improvements · commit `f1f3cbc2e30fccd3de1524ee5feaebf79a4bfff7`

- **Goal.** The owner asks to commit to Git and Gitea and recommend the next
  task. Publish entry 32's completed disk-loading work.
- **Read / checked.** Reviewed TODO, entry 32, changes, test logs and the
  playable disk. All 86 tests passed in 151.729 s; the targeted disk test
  also passes after helper cleanup. Normal ATR hash/test-mode match the
  evidence manifest; fifty PNGs decode and five native endpoints remain
  pixel-identical. Fetched Gitea: main and local HEAD both start at `d117e55`.
- **Done and how.** Commit the loader/boot/build changes, benchmark and native
  disk helpers, new regression, standing findings and reproducible evidence.
  Follow with the required metadata commit filling entries 32–33 with the
  implementation hash. Push main, fetch and verify the remote head. Use the
  external askpass helper without putting credentials in files or URLs.
- **Scope / validation.** Generated ATRs, ignored emulator/input copies and
  unrelated `resume.sh` stay outside the commits. Original game and sibling
  files are untouched. Review the staged file list and whitespace before
  committing. No runtime changes are required for publication, so the
  completed suite does not need repeating.
- **Next recommendation, read.** TODO #4: colour fidelity on the play screen.
  Start with side-by-side C64/Atari gremlin, snake and encounter captures;
  explain why green monsters become tan and white names lose their blue
  band. Measure colour selection before choosing a better row palette or
  priority rule, retaining the existing pixel/state checks. Atari rows have
  fewer simultaneous colours than C64 cells, so identify feasible gains.
  Spare LOADER / UNDER / EXT / EXT2 is only 5 / 1 / 0 / 10 bytes; additions
  need explicit layout planning. Broader combat/spell coverage is the next
  useful testing task after that.
- **Went wrong / carries over.** No new publication issue found. Preserve
  the implementation/log-hash two-commit rule, verify the remote after
  pushing, and base the next visual improvement on captured examples and
  the actual machine's colour/memory limits.

## 34 · 2026-10-11 · Correct encounter artwork colours and panel selection · commit `28b57ac733aef25665a2202b192fbc0db7427256`

- **Goal.** The owner asks to investigate/fix the colouring and selection
  issues in TODO #4; after an interruption asks to continue. No commit/push
  requested for this implementation.
- **Read / checked baseline.** Specification/design/oracle/palette/performance
  notes, gallery, converter, caches and original EN listing. Main starts at
  `d2410f1`, only unrelated `resume.sh`; 86 tests pass in 146.442 s. Capture
  eleven native frames and freeze the old kernel. Direct enumeration of
  source pairs reproduces all nine old graphics buffers/palettes exactly.
- **Cause.** Old histograms count matrix colours advertised by blank cells,
  so stale tan wall entries outvote drawn green artwork. EN `$2742` paints
  eighteen `$0E` colour-RAM cells from `$D816`; the Atari marks only ten
  command columns. Eight blue list columns therefore draw in view PF2 white.
  Names themselves use a dark matrix colour. Mode 1 also shows ordinary
  doors, so display mode alone is not a sufficient layout predicate.
- **Done and how.** Identify the wide layout from mode 1 and the masked blue
  marker at `$D816`; set character high bits from column 22 instead of 30,
  clearing them when returning to commands. For its first sixteen rows,
  count matrix colours only when their actual bitmap pairs occur. Reuse
  mapping 6: `(swap(b) XOR b) AND b` marks pairs 01/10; OR eight scanlines,
  skipping zero bytes. Keep the original nearest distances/ties and RAM
  colour policy. Bypass/invalidate the old matrix-only cache for these rows;
  other rows retain exact cache, mapping and qualified row reuse paths.
- **Fit.** Pack symmetric distances into 136 entries plus sixteen offsets
  (104 table bytes saved, all 256 values exact). Move the sixteen idempotence
  constants to `$FFD3–$FFE2`, covered by immutable TOP checks. Reduce lookup
  unrolling to two bytes and use a small identity loop; move matrix/scratch
  state to EXT2. Spare LOADER / UNDER / EXT / EXT2 5 / 1 / 0 / 3; TOP has
  one byte before GETIN and nineteen after. No new bank, bitmap cache, boot
  sector, original game modification, operand redirection or save format.
- **Result, checked.** All 898 gremlin and 2,060 snake source-green pixels
  now use the green entry (previously zero). All 2,710 / 9,510 blue panel
  pixels remain blue; dinosaur retains all 2,922 green and 4,082 blue pixels.
  Logical-colour errors: gremlin 2,236 → 224, snake 5,328 → 0, dinosaur
  1,814 → 502. These measure source colour indices, not equal Atari/C64 RGB.
  Actual native and Altirra monster pictures were inspected. All eleven
  native compared game hashes and all three Altirra hashes match baseline.
- **Validation.** All 87 tests pass in 152.657 s: nine scripts / 116 state
  checkpoints, three exact saves, cold-start reload, sound, held keys,
  ordinary keyboard, disk bounds and both Altirra SIO modes. New checker:
  eleven full cold/warm frames, 256 exact distances, 256 byte-presence cases,
  eleven bitmap/layout changes including a bitmap-only negative. Existing
  24 graphics cases, all mapping qualifications/exhaustive translations,
  50 cache probes and 228 palette cases remain. Walking stays differential
  against the frozen converter; intended encounter changes use independent
  direct enumeration that first reproduces the old native output. No
  game-state comparison exclusions added or relaxed. Native host replay of
  seven instrumented conversions is exact.
- **Timing, checked.** Both emulators walk/turn in 30 frames, previously 29;
  entry 47 → 48, character prompt 21 → 22, return 24 → 25, sheets six.
  Existing speed/transition bounds still pass and ordinary idle does no
  recopy. Accept a measured one-NTSC-frame quality tradeoff rather than
  presenting this as another optimization.
- **Went wrong.** A mode-1-only width rule made gate walls cyan; use EN's
  actual blue strip. Pixel-aware scanning on every mode-1 view slowed walking
  to 45 frames; scope it to wide panels. A fully rolled converter took 31
  frames; partial unrolling meets 30. Two full-suite combat routes initially
  hung because rendering skipped an original exact pause target. Zero-byte
  skipping fixes both, with exact checkpoints/save retained. An isolated slow
  control observes clock/target 1624 while PC 31868 is still rendering, then
  clock passes it and the next wait is absent after 360 frames. No original
  pause/clock change. TOP reserve arithmetic needed a same-segment label
  difference; rebalanced EXT/EXT2 after overflow reports. Altirra's harness
  initially trusted uninitialized kernel flags and supplied input before
  boot; wait for the printed prompt. Profiler assumed eight lookup aliases
  and eagerly evaluated absent `table7`; accept two and use the exit label.
- **Evidence / standing notes.** [Colour findings](COLOUR-SELECTION.md),
  [frozen/new/native/Altirra frames, policy and timing proofs](../test-artifacts/colour-selection/README.md).
  Regenerate all 25 gallery pairs: only four affected Atari images change,
  the other 21 and all C64 images remain byte-identical. All fifty gallery
  images decoded/visually inspected. Spec/plan/TODO/design/runtime/oracle/
  speed/palette/graphics/memory notes updated. Normal `mm1.atr` and distinctly
  named `mm1-colours.atr` are identical, test mode false, 724,752 bytes,
  SHA-256 `4547214f2fbb6e42aeaf90ec3ad62a36de3042f0227f3d982e8366276c8e746f`.
- **Limits / next.** Fewer hardware colours still approximate some borders
  and highlights. This is the traced encounter-layout fix, not an optimal
  pixel-weighted selector for all artwork. Atari palette RGB, sound pacing,
  PAL, original Atari ROM and hardware coverage remain unchanged/open.
  TODO #5 broader combat, spells/items, traps and areas is next useful work.
- **Carries over.** A colour advertised in a matrix is not necessarily drawn;
  count actual use where stale metadata affects decisions. Trace panel
  geometry rather than assuming one width. Cache validity must include every
  new selection input. Repack symmetric constants exactly before allocating
  another bank. Check real game transitions after a visual/performance change:
  a long rendering interval can skip a game's exact clock target. Inspect
  every final picture and distinguish logical-colour proof from RGB fidelity.

## 35 · 2026-10-11 · Publish encounter colour fix · commit `28b57ac733aef25665a2202b192fbc0db7427256`

- **Goal.** The owner asks to commit to local Git and Gitea.
- **Done and how.** Publish entry 34's kernel, independent colour reference,
  checks, refreshed gallery, documentation and captured evidence on `main`.
  Fetch Gitea before committing; local and remote start at the same `d2410f1`.
  Record the implementation hash in entries 34–35 with the usual metadata
  commit, then push and verify local/remote heads match. Leave unrelated
  `resume.sh` and ignored emulator working copies/generated ATRs outside Git.
- **Result / evidence.** The final recorded suite passes all 87 tests in
  152.657 s. Native and Altirra captures verify the corrected green artwork
  and blue encounter panels; the previous gallery inspection covers all
  fifty images. The normal playable disk and `mm1-colours.atr` share SHA-256
  `4547214f2fbb6e42aeaf90ec3ad62a36de3042f0227f3d982e8366276c8e746f`.
  The measured one-frame walking/turning cost remains documented.
- **Went wrong / carries over.** No new publication issue. Retain entry 34's
  failed approaches and exact-clock pause evidence alongside the final
  proofs so later changes can reproduce both the symptom and the fix.

## 36 · 2026-10-12 · Run the C64's title program: frames, tune and scenes · commit `58bcae0021c04758edc747cbe6e4c8d33d2d2ece`

- **Goal.** The owner asks whether the C64's intro "with screens and sound"
  could be done, hears an opinion (moderate, low risk, the tune the unknown)
  and says to do it and report. No commit or push requested in this turn.
- **Read / baseline.** Tree clean apart from `resume.sh`; 87 tests. Normal
  disk SHA-256 `4547214f…`, test disk `c375400c…`. Read specification,
  design, build, boot code, kernel, oracle and harnesses. Then the title
  program's listing (`build/source/game/title.s`, 3,968 bytes at `$4000`),
  which nobody had read: the port skipped it.
- **What the title program is, read then traced.** Two packed pictures that
  take turns, each shown from the edges inwards in twelve steps; a tune
  played from the 60 Hz interrupt, three voices of four-byte notes, 850
  ticks a round; `SPACE` for eight scenes, each a packed picture and for
  four of them a kilobyte of colours; Escape loads the game's first files
  and enters the stub. It draws into `$E000` with colours at `$CC00` and
  `$D800`: the game's own lower screen. Both title pictures give every cell
  the same three colours. The oracle already ran it (the build's start
  state comes from running it to `$2000`), so pictures, memory use and
  sound-chip writes came from the oracle within minutes
  ([what it does](TITLE.md)).
- **Decisions.** (1) Run the original program, as the game: 25 operands
  that name the video chip, sound chip and CIA 2 pointed at the kernel's
  stand-ins; nothing else in it changed. (2) Keep the proven start: Escape
  goes back to the boot code, which loads the game and sets memory from the
  oracle exactly as before. The title is a stage in front, not a new way
  into the game. (3) No kernel change: it has 5 / 1 / 0 / 3 bytes spare.
  Everything new is a separate 2 KB piece in memory the title program
  leaves alone, measured on the oracle. (4) The disk without the title
  stays buildable and is what every existing check builds.
- **Done and how.** `src/title.s`, loaded to `$8000` from the end of the
  disk; `boot.s` parks its own 7 KB at `$A000` first, because the title
  program unpacks pictures over it, and is copied back on Escape. Three
  hooks in the kernel while the title runs: the operands of `JMP getin` and
  `JMP disk_read`, and the NMI vector's high byte (the stage's handler is
  placed at an address with the kernel handler's low byte, so one store
  switches). **Title frames:** shown in place. A C64 bitmap row is a mode 4
  character set; 19 of the 25 rows at `$E000 + 320 r` fit a 1 KB block and
  ANTIC reads them where the title program draws, so the from-the-edges
  effect is live; six rows cross a block and are copied to `$1400`, two a
  frame, while the title program draws. **Scenes:** the kernel's
  `rf_bitmap`, once per scene, called from the vertical blank when the
  interrupted address is in the title program's wait between scenes.
  **Tune:** the title program's own handler writes the stand-in registers;
  the stage turns three voices into POKEY's every frame: voice 1 on the
  joined channels, voices 2 and 3 on channels 3 and 4 at 64 kHz, from a
  table of the tune's 14 pitches that `build.py` reads out of the title
  program. **Escape** is taken where the title program is handed the key.
  **Skipped reads:** the title program's three loads of game tables, which
  the boot code repeats.
- **Scenes with two pictures in a frame.** The kernel's count of matrix
  colours gave a grey frame beside the text and a frame in the wrong colour
  on two of the four. The kernel cannot change. The stage instead rewrites
  the colour matrix before the copy: a nibble a cell does not draw becomes
  the frame's colour or, in the pictures' rows, the commonest other colour
  drawn there. Frame and text right on all four; each picture keeps one
  colour pair and loses the rest to the nearest.
- **Result, checked.** Both title frames: all 64,000 pixels the colour the
  C64 shows, every time the title program waits (15 times each in 1,900
  frames). Tune: all three voices at the right pitch at each of 1,900
  ticks; voice 1 within 0.7 cents, voices 2 and 3 within 13.4. Eight
  scenes: the title program's screen memory equal to the oracle's and
  Atari800's picture equal to the independent model of the kernel's copy.
  After Escape: every byte of the kernel's code as assembled; main memory
  equal to the title-less disk's at the first prompt except 105 bytes in
  seven listed places (clocks, stack, display scratch); then the short game
  plays. **All nine lockstep scripts pass with the title in front: 116
  marks, three saves, one restart.** AltirraSDL passes with its disk patch
  and with serial transfers. The disk without the title and the test disk
  are byte for byte what they were.
- **The reference, traced.** `tools/traces/title-scenes.txt` recorded in
  VICE: the oracle agrees on all 20 disk reads and all 11 pictures on the
  first run. Side effect: the scenes account for 120 of side A's 274
  blocks that no session had read; 154 remain (`tools/mmdisk.py`,
  [C64-LOADER.md](C64-LOADER.md)). The tune's notes are in tune with the
  NTSC C64 clock (A = 439.94 Hz), not the PAL one the effects were
  converted with.
- **Validation.** All 98 tests pass in 194.720 s: the 87 earlier ones
  unchanged, and eleven in `tests/test_title.py`: the oracle against the
  VICE recording, the decoded tune and its pitches, the patch list with
  and without the title, the matrix rule, `title_check.py` (32 checks),
  two lockstep scripts through the title, the two disks differing only in
  the title's own bytes, and both AltirraSDL modes (12 checks each). No
  comparison exclusion added or relaxed; `lockstep.py` gained `--title` and
  nothing else.
- **Measurements.** Atari800: tune 96 frames after power-on; a change of
  frame 62 frames (41 drawing, 21 waiting) against the C64's 0.67 s; a
  scene 203–241 frames; Escape to the prompt about 100. AltirraSDL with
  serial transfers: 17.3 s to the title, 36.7 from Escape to the prompt,
  so about ten seconds more than the 44.2 without a title. Stage 2,021
  bytes; boot code +57; disk +8 blocks, 726,800 bytes; kernel +0.
- **Went wrong.** *Black for ever in AltirraSDL with serial transfers*,
  fine in Atari800 and with Altirra's disk patch. With DMA off ANTIC
  repeats its last instruction; a row with an interrupt then interrupts
  every eight lines, and the one before the vertical blank was still
  running when the vertical blank's handler looked at the interrupted
  flags and concluded "masked", every frame. Found from the stack and a
  row counter that read 31 at line 248. Fix: no row interrupts while the
  stage's screen is off. Whether the screen went dark on such a row
  depended on when the last transfer ended. *Others:* the first byte scan
  for sound-chip writes was a pattern match and reported a CIA address
  that was data; the matrix code first shared a counter with the row
  interrupt (caught by reading); ca65 define-style macros with arguments
  do not work inside larger expressions (generated symbols instead); my
  variable names clashed with the kernel's label file; the emulator's
  frame boundary is inside the vertical-blank handler, so "where is the
  program" has to be read from the stack or from memory; the check for a
  settled frame fired never, then early, because the bitmap stops changing
  eight frames before the title program stops copying; the tune seemed a
  tick late because recording began after it did; a count of sound-chip
  writes was off by the two stray bytes the title program writes below
  colour RAM (`$D7FE/$D7FF`), which is how they were found; one kernel
  hook byte equals the original by chance, so hooks are checked by value.
- **Evidence / documentation.** [Findings and the pictures beside the
  C64's](TITLE.md); [check outputs, AltirraSDL pictures, the nine lockstep
  runs](../test-artifacts/title/README.md); [VICE recording](../test-artifacts/c64/trace-title-scenes).
  All twenty gallery pictures and the eight AltirraSDL ones looked at.
  Specification, design, TODO, loader, code, oracle, sound and 64 KB notes
  updated. `build/atari/mm1.atr` and `mm1-title.atr`: the disk with the
  title, 726,800 bytes, SHA-256 `fc10b1b78ba12f7209e9fe4d54622163a3e8a6132c2ae4f3eb77b5593d6190e7`.
- **Limits / next.** The four two-picture scenes lose colours; all of them
  would need colour registers changed in mid-line, which mode 4 cannot do
  on the first line of a row. Frames change in 1.0 s, not 0.67. The screen
  is black during disk transfers, as in play. The tune's writes are the
  oracle's, not recorded in VICE. PAL, Atari's OS ROM and hardware remain
  untried. The kernel may have the stale-interrupt pattern where it blanks
  the play screen: read, not measured. TODO #5 is still the next useful
  work on the game itself.
- **Carries over.** Before writing presentation code for a part the port
  skipped, read what the original does: here it used the screen layout the
  port already converts, and a third of it needed no conversion at all.
  When the support code has no room, look for memory and time that are
  free only in that phase and take the piece out of the kernel entirely.
  Enter and leave such a phase through the proven path, and prove it by
  running the existing comparisons with the phase in front. Keep the build
  without it byte-identical and say so with a hash. Hook machine routines
  by their operands and restore them; check restored code against the
  assembled image. Sample the interrupted address to learn what unchanged
  code is doing. Run anything that turns the display off in the accurate
  emulator, with real serial transfers: timing there decides which
  instruction ANTIC is left repeating.

## 37 · 2026-10-12 · Expand gameplay coverage and fix a missed pause target · commit `26cee43a4940bb406ae9356243f584898fb2ec3b`

- **Goal.** Owner asked to work in order: unusual side-D input, combat actions,
  encounter choices/chest traps, death/raising and travel, then walking speed.
- **Method / work.** Read the original area and resident key code. IF `$89F0`
  and EH `$86D2` call `$A087`; DP `$890E` calls GETIN itself. Added `poll
  CALLER KEY` to VICE/oracle/Atari scripts. The Atari harness arms its existing
  held wait before releasing the triggering key, selects return address and
  stack depth, and restores four operand bytes before delivering the direct
  key. No game patch, runtime byte or comparison exclusion was added.
- **Scenarios.** Twelve new scripts: three direct readers; successful combat
  spell, bow shot and exchange; charged flaming-club use; retreat, refused
  bribe and refused surrender; trap detection and successful/failed removal;
  one character's death to a gas trap and temple raising; real walking through
  EJ/C and BB/C with a kobold victory. Position/load-destination, health,
  equipment and skill fixtures are explicit; wilderness uses the stock party
  without fixtures. Native code performs all events, combat, loading and
  restoration. `tools/coverage_check.py` checks outcomes as well as traces.
- **Found / fixed.** The wilderness fight matched through its encounter but
  stalled in the original pause's GETIN loop on Atari. The target was `$0B72`
  and the clock had passed it: screen conversion outlasted an exact-equality
  pause target. IRQ tail now holds KERNAL clock ticks when PORTB bit 4 selects
  extended RAM; sound IRQ sequencing/envelopes and keyboard handling continue.
  The fight completes with exact state. Six volatile envelope bytes moved into
  unused TOP bytes above GETIN, fitting the seven-byte guard in UNDER. Code,
  constant-table and vector checks remain protected; volatile bytes are named
  explicitly. No added bank or changed ATR/game-side/save layout.
- **Second emulator.** Added `lockstep.py --altirra [--sio]` through the bridge,
  with the same RAM/kernel/display-list/disk checks and persisted disk-copy
  handling. The wilderness route passes in both modes. Clear test-hook bytes
  before Altirra's boot: randomized initial RAM must not masquerade as flags.
  Held waits allow four-frame batches. Close the bridge even on a failed run.
- **Evidence.** Plain VICE recordings, preserved-counter settled recordings,
  153 oracle/VICE pixel comparisons, 141 new Atari checkpoints (total 21
  scripts / 257), checked native screenshots and Altirra wilderness logs.
  [Scope / findings](GAMEPLAY-COVERAGE.md),
  [Atari evidence](../test-artifacts/gameplay/README.md).
- **Went wrong.** Merely resetting screenshot wait counters to zero changed
  encounters and later actions while still producing matching oracle/VICE
  pictures. `--settle-preserve` restores each plain mark's exact counters, and
  both versions now have outcome assertions. A first death scenario checked
  `$40`, which is **unconsciousness**, and the 25-gold restoration was therefore
  not raising. Lowering endurance did not make ordinary gremlins kill the
  unconscious character. The native gas trap does: `$C0` is real death, and
  the original character sheet confirms it. The final scenario raises that
  character; a negative regression rejects `$40` as death. The first Altirra
  attempt treated random startup bytes as completed waits; another ran slowly
  polling each frame. Both were harness issues, fixed before counting a pass.
- **Limits / carries over.** Focused destination fixtures do not prove natural
  travel to IF/EH/DP. Successful negotiations, no-key maze/floor branches,
  every spell/item/fatal condition, all 55 areas, PAL, Atari OS ROM and hardware
  remain open. Prove the intended branch independently of a matching trace:
  two machines can follow the same wrong scenario. Preserve the input timing
  that controls dice when delaying for pictures. Presentation work must not
  let an original equality-based time wait skip its deadline.

## 38 · 2026-10-12 · Reduce walking conversion work within the existing bank · commit `26cee43a4940bb406ae9356243f584898fb2ec3b`

- **Goal / baseline.** Improve walking after broader gameplay checks. Capture
  a fresh native profile after the pause fix, so timing changes from that fix
  are not mistaken for converter gains. Steps/turns were 30 NTSC frames,
  character prompt 22 and character-sheet return 25.
- **Work.** Lookup copy unrolled from two bytes to four, with four synchronized
  operands; identity copy from one byte to two. Cell mapping keeps the raw
  matrix byte in X instead of the stack. Histogram rereads that byte, saving
  stack cycles. Derive colour-RAM high bytes from the matrix table plus `$D4`,
  removing 25 bytes. Move the nine-byte blanking helper into unused TOP space
  to fit the larger loop; remove a redundant zero load. Update native probe
  discovery for four lookup instructions and frozen-snapshot injection for
  the moved helper. Strengthen the existing speed bounds.
- **Measured.** Walking converter instruction cycles 330,909 → 323,314 (2.3%).
  Step conversion elapsed cycles 627,114 → 616,740 (1.65%); step/turns 30 → 29
  frames (3.3%), scripted character prompt 22 → 21 and return 25 → 24. Native
  frame boundaries quantize these gains; walking remains about 484 ms.
- **Checks / evidence.** All seven game-state hashes and all 28 common native
  benchmark PNGs equal the baseline. Independent converter: 24 differential
  refreshes, all 16 qualification tables, exhaustive/mixed pixel patterns and
  a deliberate pair-swap negative. [Measurements](WALKING-PERFORMANCE.md),
  [reports / pictures](../test-artifacts/walking/README.md). Full regression
  and second-emulator results are appended below after completion.
- **Went wrong / limits / carries over.** Four lookup instructions require
  four operand writes: the first layout estimate missed their six extra code
  bytes and overflowed EXT by two. Moving a small helper into proven unused
  TOP space solved it without another bank. Host snapshots initially retained
  zero padding at the helper's new address; update the injected constant code,
  not an exclusion. The profiler also needed to recognize four instructions.
  Larger cursor/cache prototypes were considered but not applied: memory and
  loop costs can consume their apparent gain. This is a measured, modest gain;
  major further speed remains separate work. Original game files, pixel policy,
  bank allocation and disk/save layout are unchanged by the speed work.

- **Regression follow-up for entries 37–38.** The full run first passed 101 of 103 tests. The idle positive control aged `stamp` after the sampled CPU had already read it, so it failed to force a copy; assert `key_given` instead, and measure active extended-bank ownership even while an IRQ runs outside the converter's PC range. Title/plain startup differed only in KERNAL jiffies after equal frame counts; synchronize both first-prompt captures to clock tick `$000080`, where the prompt polls directly and does not advance dice. Both failing tests then passed, with no new comparison exclusion. A full final rerun follows.

- **Final verification for entries 37–38.** All 103 tests pass (396.895 s), with no skips. All 21 Atari scripts / 257 checkpoints and disk comparisons pass; all 153 new C64 pictures and behavior assertions pass. Altirra confirms movement/turns 29 frames and return 24, ordinary idle conversion zero and forced positive control 58 of 60 frames. The title, all nine sound effects, saves/restarts, serial transfers and independent converter checks pass. Final normal/title-enabled `build/atari/mm1.atr`: 726800 bytes, SHA-256 `cfd581834897721987137ae3f46f277746cedaaba69d27e9208165a120098bed`. [Full regression](../test-artifacts/gameplay/regression.txt), [Altirra timing](../test-artifacts/walking/altirra.txt).

## 39 · 2026-10-12 · Write a reusable prompt for a new Atari port · commit `f9ec912638fb26ffe9cc2e76a5dc7eb9503af467`

- **Goal.** Owner requested a `PROMPT.md` that an LLM without previous project
  context can use to convert an 8-bit game from NES, Apple II, C64 or another
  platform, starting in an empty project folder.
- **Method / work.** Read the plan, owner rules, reference setup, porting
  recipes, runtime/oracle design and recent gameplay/performance findings.
  Checked upstream Atari800 installation/usage, Altirra downloads/hardware
  manual, cc65, AppleWin, current Mesen links and Ghidra. Wrote a configurable
  project brief, empty-folder/tool setup, architecture choices, deterministic
  reference workflow, storage and code reconstruction, Atari memory/display
  design, platform services, independent validation, profiling recipes, ten
  milestones with exit evidence, debugging and release/handoff instructions.
  Added a link from the README.
- **Result / evidence.** [PROMPT.md](../PROMPT.md) is self-contained and asks
  its recipient to implement and verify the port. Earlier project tools,
  addresses, operand-only patches and custom emulator bridges are not assumed
  available. Native logic, interpreted games and NES hardware have distinct
  guidance. Download URLs are starting points; new installations must pin and
  exercise their chosen versions.
- **Checks / limits.** Reviewed the prompt against the documented mistakes:
  kernel overwrites, incomplete I/O inventories, input/RNG and screenshot
  timing, unconsciousness versus death, serial-SIO/DMA-off behavior, writable
  disk copies, transient frames and measured cache optimizations. Checked
  Markdown structure, links and whitespace. No runtime or build changes;
  gameplay tests were not rerun for this documentation work. The prompt has
  not yet been exercised on a second game, so it does not establish feasibility
  for any arbitrary source title or mapper.
- **Carries over.** Preserve the method and evidence requirements, while
  treating a previous game's addresses and hardware substitutions as examples
  rather than universal rules. Bootstrap automation interfaces explicitly:
  a stock emulator download does not supply another project's custom bridge.

## 40 · 2026-10-12 · Specialize the prompt for Pool of Radiance on the 65XE · commit `52ca0d54c219208d121eefc3c6ab6dcd97fd04f0`

- **Goal.** Owner requested `POR.md`, based on `PROMPT.md`, for converting SSI's
  C64 NTSC Pool of Radiance to a stock Atari 65XE.
- **Method / work.** Adapted the general prompt into a self-contained project
  brief and implementation workflow. Fixed source to C64 NTSC and target to
  64 KB, replaced unrelated platform guidance, added SSI reference links,
  source-media/save inventory, exploration and tactical-combat coverage,
  early memory/lifetime feasibility checks, display/overlay/asset-conversion
  alternatives and the appropriate Atari800 64 KB launch pattern. Linked the
  new prompt from README.
- **Evidence / checks.** Read SSI's scanned C64/128 quick-start card for media,
  input and save setup; checked Atari800's usage and the Altirra hardware
  manual for target profiles, ROM mapping and the permanent I/O hole. Reviewed
  the adaptation for inherited 130XE assumptions, placeholder source choices,
  memory arithmetic, Markdown structure and whitespace.
- **Result / limits.** [POR.md](../POR.md) directs a future agent to establish
  the actual NTSC image baseline, budget both exploration and combat, preserve
  game/save semantics and validate a normal release in 64 KB configurations.
  No Pool of Radiance media was executed or analyzed here, and 65XE feasibility
  remains to be measured in the new project. No game/runtime change or gameplay
  test rerun for this documentation work.
- **Carries over.** A smaller target changes architecture and milestone exit
  conditions, not just the model name. The earlier extended display bank,
  large remap tables and bank-derived busy indication cannot be assumed on a
  65XE; evaluate native assets, shared lifetimes, relocation and disk overlays.

## 41 · 2026-10-12 · Package the local porting tools and reference library · commit `52ca0d54c219208d121eefc3c6ab6dcd97fd04f0`

- **Goal.** Owner requested `porting.tgz` with `PORTING.md` and useful tools
  under `tools/`, assuming all development happens on this machine; then
  explicitly requested PDFs and other documents, including Wizardry references.
- **Work / method.** Created `PORTING.md` from the POR prompt, documenting the
  supplied adapters, local installation paths, reference files and verification
  commands. Added a reproducible package builder and maintained kit templates.
  Included general D64/G64 readers, flow tracer, host CPU and screen/PNG helpers;
  adapted Atari800 and AltirraSDL harnesses to 64 KB; added a game-independent
  C64 NTSC launcher and wrappers for installed compilers/debuggers/emulators.
  Preserved all earlier Might and Magic tool/check/assembly sources in their
  original layout as adaptation examples, plus Wizardry harness/p-code/setup
  examples. Included the common/Atari/C64 reference libraries: ten existing
  PDFs, text, HTML, web assets and original provenance manifests. Checked
  document/asset hashes against Wizardry's manifests before packing.
- **Packaging / boundaries.** Root contains `PORTING.md` and the `tools/`
  tree, with installation/file manifests and SHA-256 checksums. Sorted paths
  and normalized gzip/tar metadata make builds reproducible. External binaries
  and firmware stay installed on this machine and are verified by hash; no
  credentials, working saves, game disks, generated port images or cached
  Python files are included. SSI-specific POR documentation remains linked
  acquisition material, not an already bundled local reference.
- **Checks / evidence.** Bundle integrity and external tool/firmware checks;
  all 27 existing media-free disk/CPU/renderer tests; assembler/linker bytes;
  native Atari800 probe at 64 KB; native AltirraSDL boot probes at 64 KB with
  accelerated and standard serial SIO; fresh extraction and rerun. Bounded
  VICE smoke on a newly formatted disk verifies effective NTSC, argument
  forwarding and writable-copy handling; D64 extraction cross-checks c1541.
  Validation logs and reports are under `build/porting-*`. No changes to the
  existing Atari game runtime; its full gameplay suite was not rerun.
- **Wrong turns / lessons.** Atari800's library frontend does not accept SDL
  keyboard-joystick flags; use its input structure and an explicit private
  configuration. Altirra's CONFIG response is flat and REGS is read-only; use
  a genuine assembled boot-sector probe instead of assuming a PC-setting API.
  The installed Altirra help option opens its UI, so use source/help inspection
  or isolated bridge settings when probing unfamiliar switches. Validate
  archived helpers after extraction rather than merely checking source files.
- **Limits.** Earlier CPU core lacks decimal/BRK/unofficial opcodes and screen
  comparison has PAL crop/palette defaults and no sprites; these limits are
  documented for POR adaptation. Original examples need their game inputs and
  are not standalone POR drivers. The kit validates working infrastructure,
  not Pool of Radiance's conversion or its 64 KB feasibility.

## 42 · 2026-10-13 · Four disks for real 1050 drives: packed items, an index, the game's own prompts · commit `52ca0d54c219208d121eefc3c6ab6dcd97fd04f0`

- **Goal.** Owner asked to continue the real-hardware study (`REALHARDWARE.md`,
  left unfinished when another session was stopped): get four disk images
  working, with prompts so the player knows when to swap. (The owner first
  named a `2DISK` branch; that is `2DISK-Wiz` in the Wizardry port, which
  supplied the streaming ZX02 decoder, its compressor and the harness's
  `mount_disk`. This repository has no such branch.)
- **Method / work.** `port/atari/disks.py` lays out four 1,040-sector
  (enhanced density) images from the game's own file table, picture index and
  side A's fixed reads: each item packed alone with ZX02 and padded to sectors,
  the roster, monster records and file table stored, and an index of two bytes
  a block in the last 11 sectors. `kernel.s` gained a `DISKS` mode that
  replaces the disk code in the same 768 bytes: index sector read, then a copy
  or a streaming, bounded ZX02 unpack through a 128-byte buffer, the write path
  for the roster, and status 8 for anything that fails so that the game's own
  file-table check asks again. `build.py --disks` builds it; `boot.s` stages
  loads that end above `$C000` (the OS ROM hides what the kernel writes
  there) and finishes from a stub at `$0180`. `lockstep.py --disks` changes
  the mounted image at each `attach` and puts disk 1 back at a `restart`; at the
  end it reads every item of every disk the way the kernel does and compares
  it with the oracle's side. `altirra.py` gained `mount`.
- **Where the room came from** (the kernel segments were full): the sector
  buffer in the stack page (stack pointer `$F0` or more at all 107 disk calls
  measured, guard at `$D0`); five variables in the padding of four `rts`-only
  jump-table entries; `enter_game` out of the kernel; the offset parameter
  dropped (all 17 stores to it are a constant 0). LOADER has 3 bytes spare.
- **Evidence / checks.** All 21 scripts of the existing set pass
  `lockstep.py --disks` in Atari800: memory equal at every mark, every item of
  all four disks equal to the oracle's, the roster on disk B equal after each
  save and no other disk changed. Also passing: fast disk shortcut off
  (`--sio`) for save/reload, side D and the menu; with the title in front; in
  AltirraSDL with and without the shortcut for fight-and-save, and with real
  serial transfers for save-restart-reload and the wilderness fight.
  `disks_check.py` (the playable build, nothing told which disk is in) sees the
  prompt for disk B repeat for disk 1 or disk C in the drive and give the
  options menu for B. The existing suites (`test_atari`, `test_title`, and the
  sound, keyboard, speed, display, colour, disk, Altirra, oracle and mmdisk
  modules) pass unchanged on the one-image kernel.
  `tests/test_disks.py` runs these in about 3½ minutes. Disks use 459, 795, 749
  and 743 of 1,029 data sectors (the fullest 77%). To the first prompt with
  real serial transfers: 27 s against 40 s, with the shortcut 7.5 s against
  1.3 s (the unpacker's cost, about 180 cycles a byte).
- **Wrong turns.** (1) A write call read its index with the write command and
  overwrote index sector 5 of disk B: the item-by-item comparison found it
  (RK, the monster records and FA "differed", all behind that index sector).
  (2) My first replace of the transfer entry hit the one-image kernel's identical
  text too and broke its build: caught by building it. (3) Packed pieces for
  `$C000` and up read their own history from the ROM: boot staging, not forced
  raw. (4) The Altirra bridge's `MOUNT` counts drives from 0, and `MOUNT 1` put
  the disk where nothing read it. (5) My first estimate needed about 180 bytes
  more LOADER than existed; the stack-page buffer alone (the first idea was a
  separate segment at `$9F80`) was the difference.
- **Not known / limits.** Not run on a real 1050: first command after a disk
  change, sector order and interleave of the written disks, timing, write
  protect on disk B (the status goes back as 8; what the game does was not
  examined). Needs an enhanced-density drive. The unpacker is slow and there
  are 3 bytes of room to speed it. The Altirra `--disks` runs covered three
  scripts, not 21.
- **Carries over.** Per-item compression with a streaming decoder removes the
  need for staging memory, and a call's own stack depth can be measured and
  used. A harness that reads every item back is the real check of a packed
  layout: it finds what the sessions never read. Prompts of the original game
  do the user-visible work; the port's job is to fail in the way they expect.

## 43 · 2026-10-13 · A demo video, and the `side-d` session that never reaches side D · commit `f03d0288eb8a40801e9a62029f51ad765bc6356f`

- **Goal.** Owner asked for a five-minute demo video of the game on the
  four-disk build. Owner then saw that the portal / disk D part showed a fight
  with dinolizards and not the portal.
- **Work.** `port/atari/demo_video.py` replays parts of the recorded sessions
  in Atari800 (four disks, the disk changed at each `attach`), records every
  frame and the sound, speeds up the long walks, adds captions and title cards
  with ffmpeg and joins eight segments: title and disk swap, making a character,
  the town and its shops, a dungeon fight and a save, spells, a chest, the
  outdoors with disk C, and a castle loaded from disk D. 4:52 at 1152x720.
- **The error.** The video's last segment used `boot-to-side-d` for the
  portal and disk D. In that session a wandering group of dinolizards meets
  the party on the portal square (13,13) and every key after it does nothing:
  the marks `portal`, `insert-d` and `side-d` are all the same encounter.
  The C64's own recording (`test-artifacts/c64/trace-side-d/portal.png` and
  `side-d.png`) shows the same, and neither it nor the oracle reads anything
  from side D after `attach D`. Several documents had said otherwise (the
  `side-d` row of C64-LOADER.md, C64-BASELINE.md, C64-RUNTIME.md, the
  screenshot gallery's "Beyond the portal"), and my own DISKS.md and log entry
  42 listed "the swap to side D" among the checks that passed on the strength
  of that session. **What actually exercised disk D:** `direct-if`, `-eh` and
  `-dp`, which put the party at a castle entrance with a position fixture; the
  game asks for disk D and loads an area from it. Those pass on four disks
  (Atari800 with real serial transfers for all three; AltirraSDL with real
  serial transfers for `direct-if`).
- **Fixed.** The video's segment now uses `direct-if` (the castle prompt, `INSERT
  DISK D`, the castle from disk D), and says in its caption that the test
  script jumped the party there. The wrong claims in the documents are
  corrected, a note is at the top of `boot-to-side-d.txt`, and
  `tests/test_disks.py` runs `direct-if` for disk D in place of `side-d`.
- **Not fixed.** Nobody has walked from side C through the portal to side D;
  the `side-d` route needs another recording that avoids or wins the encounter.
  `boot-to-side-d` is kept (it is a valid walk across sectors EJ and EP) under
  a name that overstates it.
- **Light.** Owner then noted that the dungeon is pitch dark on arrival. The
  dungeon segment now has Wizz Bane cast Light (`#`, `6`, then `C`, `1`, `6`,
  RETURN: Sorcerer level 1, number 6) after the stairs, so the walls show. The
  extra keys change the random numbers, so the arena fight is against kobolds
  and not snakes; it is still won and the save still follows. The video also
  writes 3x stills of every captioned moment to `build/atari/video/stills/`.
  The screenshot gallery (`docs/SCREENSHOTS.md`) shows the dark dungeon too, as
  each row sets the Atari beside the C64's recorded picture of the same mark;
  lit pictures would need new C64 recordings, so it is unchanged.
- **Lesson.** A mark's name says what its author meant; check the picture
  before relying on it, in a video or a claim of coverage. The lockstep
  comparison cannot tell: the Atari matched the oracle at a state that was
  not the one named.

## 44 · 2026-10-13 · Feasibility of a 64 KB / 65XE build · commit `bef35b2752d403b4fdd52f91b61e1b83df272516`

- **Goal.** Owner asked for a deep investigation of making the project run on
  a stock 64 KB Atari. Research and a concrete implementation route; no request
  to change the playable kernel or publish a build.
- **Work.** Read the current build, boot, kernel, C64 drawing routines, EN/CM
  and existing memory notes. Added host-only `tools/atari64_survey.py`: wraps
  CPU memory and chip callbacks after game-stub entry, records indirect and
  instruction/operand accesses separately from subsequent disk loads, replays
  all 21 gameplay scripts and optionally compares every event with a normal
  replay. A targeted probe captures the resident bytes before EN's backup and
  compares them at CM's restore; a second positive checks low-RAM party users.
  Wrote `docs/64K-FEASIBILITY.md`, updated findings/plan links and corrected
  DISKS.md's obsolete claim about needing new decoder staging on a 64 KB build.
- **Checked results.** All 21 scripts: events equal uninstrumented replay,
  281 script marks / 259 after stub entry (host marks, not new Atari checks).
  762 of 768 bytes at `$0800–$0AFF` are active party records. EN copies 7,936
  resident bytes from `$4000–$5EFF` into `$E000–$FEFF`; all equal at CM restore.
  A displayed frame has six crossing rows, so their shared slots fit two
  1 KB blocks, correcting the older four-block estimate. A 256-byte nibble
  table agrees with the original byte mapping in all 4,096 input/mapping cases.
  Evidence and input hashes: `test-artifacts/64k/`. Commands: survey `--verify`
  and `--targeted`; targeted probe and relative-path CLI smoke both pass.
- **Proposal and memory.** Begin with direct display of nineteen raw rows,
  six copied rows and fixed pixel-role colours, retaining original page flips
  and combat backup. Candidate copy blocks at `$CC00/$D800` can hold font and
  snapshot in text mode only after all conflicting colour writers are handled;
  OS/SIO must blank both display modes. Estimated extra resident support is
  440–590 bytes, with kernel/private-presentation reclamation and optional
  sound reduction requiring an actual link. A native single screen is the
  richer alternative, with flip/clear, artwork and backup contracts documented.
  No target allocation, instruction, boot sector, ATR or disk payload changed.
- **Wrong turns/limits.** Literal operand searches miss active low RAM. A
  sampled unused table range is not safe for the whole game. Removing the upper
  bitmap does not remove its 5,376-byte overlay window. The new tool's first
  explicit relative-path run failed path normalization; resolving arguments
  fixed it. No assembled 64 KB layout, native timing, emulator compatibility,
  PAL or hardware result is claimed. Original-binary patch policy needs an
  explicit implementation decision for renderer/colour-writer changes.
- **Carries over.** Budget maximum simultaneous lifetimes, not the sum of
  alternate screens. Check whether a display buffer doubles as a code backup.
  Count actual pointer accesses and retain positive controls. Factor lookup
  tables by smaller input units before dropping functionality; validate every
  combination. Require phase-specific allocation assertions and compare changed
  presentation independently without weakening gameplay/save checks.


## 45 · 2026-10-13 · Implement a separate stock-64 KB prototype · commit `bef35b2752d403b4fdd52f91b61e1b83df272516`

- **Goal.** After the feasibility study, the owner requested branch `65xe`
  and authorized investigation and implementation. Produce a playable 64 KB
  build while preserving original game rules, data, RNG and saves.
- **Work.** Added `--65xe` build/emulator profile, isolated artifacts under
  `build/atari65xe/`, direct ANTIC mode-4 renderer and independent pixel model.
  Nineteen rows display from original bitmaps; six crossing rows use two
  1 KB blocks. Text reuses those blocks for font/snapshot. Classified/traced
  colour writers and guarded all replacements with literal original bytes.
  Shortened three presentation helpers and reused the unused Y/N-reader copy
  for publication wrappers, preserving original wait/pause loops. Added OS-font
  reconstruction outside ROM with half-page staging and a stack guard. Both
  display modes blank for SIO; busy publication suppresses DLIs/clock advance.
  Dropped title startup and optional POKEY translation in this prototype.
- **Memory / performance.** No extended allocation. Resident segments total
  2,095 bytes, including 127 borrowed presentation/entry bytes. Four-disk
  LOADER has 2 spare bytes and UNDER 1; allocation checks reject overlaps and
  I/O-hole placement. Upper/lower bitmaps and 7,936-byte combat backup remain.
  Disk sectors used: A 440, B 795, C 749, D 743 of 1,029 data sectors each.
  Atari800 NTSC first-poll/patch-disk benchmark: walking 9 frames (about
  150 ms), previously 29; turns 8/9, sheet 6, return 9. Physical-drive and
  real keyboard latency are not measured.
- **Checked results.** Atari800 actual RAM-size assertion 64 KB: all 21
  scenarios / 257 settled checkpoints, game RAM, original events, all logical
  items/save payloads, kernel integrity, font/crossing storage and pixels.
  Single ATR with serial SIO: treasure/save/cold reload, 27 marks. AltirraSDL
  64K XL with serial SIO/four disks: treasure/reload 27 marks (24 saved bytes)
  and direct IF key callback 12 marks. PORTB alias probe rules out a hidden
  130XE bank. Ordinary non-test keyboard play adds a party, enters town and
  walks. Five new routine/font/stack/allocation contract tests pass. All 114
  existing regressions pass across two runs: 108 in the sandbox, six Altirra
  tests rerun successfully with local bridge access. Total 119 passing checks
  across the split runs. Rebuilt non-test 65XE single/four images and the
  ordinary 130XE title-first image; no commit or push.
- **Evidence.** `docs/65XE.md`; `test-artifacts/64k/` native case logs/PNGs,
  reports, colour-writer audit, tested layout/kernel hashes, input hashes and
  final playable-image hashes. `check65.py` reproduces all scenarios;
  `speed65.py` reproduces the seven-action timing measurement.
- **Wrong turns / corrections.** Initial four-disk link overflowed LOADER by
  90 bytes; relocating tables/font helper into shortened presentation routines
  resolved it. Initial image-item numbering wrongly assumed a conversion-table
  item still existed. A boot side-reset omission in the single ATR read the
  wrong logical side. Boolean assembler precedence needed explicit parentheses.
  A near JMP replaced an out-of-range font-error branch. The font reader reloads
  X after the bank thunk. Blank DMA needs DLIs disabled too. Faster refresh
  exposed a stale combat prompt after a pause; one publication per high-level
  wait/pause fixes it without recopying on every idle poll. `$C137` was wrongly
  listed as a colour helper: actual glyph-colour store is `$C3CD`. Altirra's
  cropped/tinted RGB output and artifact colours required deterministic pixel
  role normalization, not RGB equality with Atari800. Environmental sandbox
  socket failures were rerun, not waived.
- **Comparison scope / limits.** CC00–CFFF is separately checked presentation
  storage. Released CTRL latch 028E differs by IRQ timing in the shortened
  host reference; native settled marks assert zero, original event/party/save
  comparisons remain. The host executes original wait/pause entries and
  normalizes only wrapper code in captured RAM; immutable native code is
  checked independently. Fixed grayscale loses original hues and can expose
  previously black nonzero pixel pairs. No title or POKEY effects, PAL,
  physical 65XE/1050, DOS-boot or full-game certification. All existing
  scenarios pass, rather than every unexplored area/spell/path.
- **Carries over.** Count simultaneous display owners, not sum of alternate
  screens. Never turn combat backup into permanent tables. Preserve low-RAM
  positive controls, enumerate indirect colour writers, check complete routine
  register/flag outputs, and test font banking at the stack boundary. Faster
  rendering can invalidate time-gap publication heuristics; publish at semantic
  waits while keeping idle polling cheap. Check actual emulated bank behavior,
  serial transfers and cold save reload before claiming a 64 KB target.


## 46 · 2026-10-13 · Reduce 65XE town flicker and demonstrate colour · commit `bef35b2752d403b4fdd52f91b61e1b83df272516`

- **Goal.** Owner reports flicker on town movement/turns and asks whether
  colour can fit 64 KB. Reproduce transients, improve redraw and provide a
  colour option without reverting to extended RAM.
- **Found.** First-poll town captures show one or two fully black frames on
  movement/turns: refresh blanks DMA for every six-row copy. The raw bitmap
  has a separate lifetime problem: the game flips at `$1C13`, then clears its
  old view, but the native renderer waited until GETIN to publish the flip.
  Settled pixel checks could pass despite the visible transient erasure.
- **Changed.** Literal-guarded mode-store wrapper saves AXY/P, refreshes and
  waits for VBI before returning to hidden-page clear. Stable bitmap refresh
  retains DMA/DLIs while a separate bit holds the clock; font ownership/SIO
  still blank. Shortened the colour-copy footer at `$0E1F` with identical
  register/pointer/flags. Reused unused stand-in VIC bytes for flip completion
  and CHBASE rather than game data: allocation checks reject any non-title
  hardware user outside offsets `$11–$21` or indexed accesses needing an
  additional audit. Code integrity includes the added entries/helper. Host
  reference keeps the original flip entry and normalizes its captured code,
  since the wrapper accesses native kernel state; native code is separately
  checked. Publication checks now require bit zero, not just a nonzero flag.
- **Colour / budget.** Added `--65xe --colour`: black/dark-brown/gold/white
  graphics, white text menus. Same allocations as grayscale; whole-kernel
  comparison differs by exactly two immediate bytes. Resident segments total
  2,124 bytes (156 borrowed); four-disk headroom LOADER 2, UNDER 7. Ordinary
  130XE palette/renderer behavior is unchanged. Rebuilt separate non-test
  grayscale/colour single ATRs and four-disk sets, plus normal title-first ATR.
- **Checked.** All 21 grayscale scenarios / 257 native checkpoints pass;
  four colour scenarios / 65 marks cover town, outdoors, side D and cold save
  reload. Both emulators pass colour serial SIO/save/cold reload, 27 marks each;
  Altirra also checks actual 64 KB bank aliasing. Ordinary non-test keyboard
  play works. All **120 tests pass in one full suite with bridge access**,
  including six 65XE contracts. The new flip test verifies CPU state restored
  after publication; copy-footer differential checks include eight flag states.
  Frame captures show zero black frames and no completely erased view on
  movement/turns. Walking 12 frames (about 200 ms), turns 11/12; prior prototype
  was 9/8/9 frames. Holding the old page for publication has a small time cost.
- **Limits / wrong turns.** Shared crossing glyphs still change across a frame
  boundary, giving brief horizontal tearing. This reduces flicker rather than
  providing perfectly atomic frames; unblanking alone cannot supply another
  staged display. VBI alone does not fit the 1,920-byte indirect copy into the
  blank interval. Candidate spare `$C92C` bytes are game tables/font, and upper
  bitmap padding overlaps resident code: neither was reclaimed. The new unit
  test first mistook its return hook for refresh, then counted CLI/PLP IRQ
  schedule checks as fresh VBIs; correcting the test's event delivery resolved
  both. No further runtime change was needed. Fixed colours do not reproduce
  every C64 cell hue. PAL and physical hardware remain untested.
- **Evidence.** `test-artifacts/64k/flicker-{before,after,colour}/`,
  `flicker-comparison.json`, `flicker-gameplay/`, `colour-gameplay/`,
  `flicker-colour-altirra/`, `flicker-single-serial/`, keyboard/contract/full
  suite logs and `flicker-{inputs,playable-images}.json`. Build, profile and
  reproduction notes updated in `docs/65XE.md`. Nothing committed or pushed.
- **Carries over.** Direct displays must publish at the source program's
  page-flip lifetime boundary, not only its later input poll. Separate busy
  from visible state; preserve pause-clock semantics. Examine known unused
  stand-in registers before allocating game tables. Capture every transition
  frame and distinguish blackouts, erasure and tearing. A few fixed colours
  require palette operands, not a second screen bank; faithful per-cell colour
  remains a separate asset/renderer budget.


## 47 · 2026-10-13 · Commit and publish the 65XE work to Gitea · commit `bef35b2752d403b4fdd52f91b61e1b83df272516`

- **Goal.** Owner requests committing the completed work locally and to Gitea.
- **Work.** Reviewed the diff, fetched Gitea refs, checked that the implementation
  source hashes still match the validated snapshot, and prepared the `65xe`
  source, documentation, tests and retained evidence for commit. Follow with
  the repository's separate commit recording the implementation hash for
  entries 44–47, then push `65xe` and set its upstream on `gitea`.
- **Validation.** The unchanged implementation has 120 passing regression
  tests, all 21 grayscale scenarios / 257 checkpoints, colour/serial save and
  cold-reload checks in both emulators, and frame-by-frame flicker evidence.
  Whitespace validation passes. No extra test rerun for publishing metadata.
- **Scope.** Keep earlier unrelated changes out of these commits: GitHub source
  export/README, compressor vendoring/disk-test changes, `opencode.json`,
  generated ZX0 binary and the pre-existing porting archive. Generated ATRs
  remain under the ignored build directory; their hashes are retained in
  evidence. This request publishes the branch, not a release attachment.
- **Limits.** Remaining shared-row tearing, fixed-palette colour limits, and
  untested PAL/physical hardware are documented in entry 46 and `docs/65XE.md`.
- **Carries over.** Publish only reviewed task changes; preserve earlier local
  work. Verify the remote branch hash after pushing and record implementation
  commit references in the separate log-only commit.

## 48 · 2026-10-13 · Restore the original intro on 64 KB disk A · commit `91acd02734f4a2124da1d8f3f3bd4bffc255292e`

- **Asked for.** Disk A previously reached INSERT DISK B after a short load.
  The owner asked whether the original C64 intro could be used. Implemented
  it as a startup stage before the resident game is loaded, on `65xe`.
- **Result.** The original title program runs with its existing 25 hardware
  operand redirections: two animated frames, the original three-voice tune
  translated to POKEY, eight colour scenes after SPACE, and the title loop.
  ESC reclaims the stage, restores boot and proceeds to disk B. The default
  playable CLI build includes it; `--no-title` keeps the earlier startup.
  The build APIs retain `title=False` for existing tests.
- **Memory.** About 2.6 KB of native title code/tables at $8000, original code
  $4000–$4F7F, converted scene $5000–$73FF, and boot parked $A000–$BBFF.
  The $1400–$1BFF frame crossing buffer becomes a 600-byte scene plan. These
  are temporary owners: normal game startup overwrites them. Allocation
  metadata includes their ranges. Every permanent kernel segment is identical
  with and without the intro; the gameplay allocation remains 2,124 bytes,
  with no extended bank. The 130XE title source is unchanged.
- **Scene conversion.** Eight 600-byte plans contain 100 row palette values
  and 500 packed cell-role mappings, derived from the original Oracle artwork
  and the existing independent colour policy, including portrait framing.
  A 256-byte nibble table converts the bitmap drawn by the original program.
  Its raw bitmap and colour metadata are retained and checked unchanged.
  Plans load from disk A as needed, instead of a permanent converter bank.
- **Timing / false starts.** Testing a scene mode before WSYNC shifted the
  first scanline. Use one active CHBASE table and four initialized palette
  arrays, keeping the CHBASE write at the established DLI timing. Altirra
  serial SIO exposed palette timing and an early checker capture: the original
  scene counter advances before the old fresh flag is cleared. A committed
  scene counter identifies completed conversion. Music sampling initially
  skipped screenshot-settling frames, creating a false timing failure; frame
  captures now preserve continuous tick observation. Interrupts remain enabled
  during conversion, with a busy guard against nested copies and DLI disabled
  while ANTIC DMA is off.
- **Validation.** Full regression suite: 124 tests passed. After the final DLI
  and scene-commit changes, all four new intro/memory tests were rerun and
  passed. Atari800 at actual 64 KB checks both frames pixel for pixel, all
  eight scenes against the independent colour model, original raw bitmap and
  metadata, loop, ESC, immutable-kernel restoration, reconstructed font, disk
  B swap and options. Final four-disk and single-image sampled runs each
  match 1,899 music ticks (two late frames), and single-image serial SIO
  matches 1,900 ticks (one late frame); all three voices are audible. AltirraSDL
  with 64 KB and unpatched serial SIO passes both frame and eight scene pixel
  checks, loop, ESC and game handoff. Retained reports/screenshots/logs are
  under `test-artifacts/64k/title-*`.
- **Gameplay and downloads.** All 21 gameplay scenarios / 257 checkpoints
  pass with the title in front, including disk saves and cold reload. Rebuilt
  non-test single images and both four-disk ZIPs include the intro. Their RAM,
  sector use, source hashes and image hashes are recorded in
  `test-artifacts/64k/title-playable-images.json`; disk A uses 468 of 1,029
  data sectors. A non-test warm image also passes ordinary keyboard SPACE,
  ESC, options, six-character party, town and one step forward. Each ZIP includes a README
  and SHA256SUMS. Disk B/C/D payloads remain unchanged.
- **Limits / carries over.** POKEY approximates SID timbres. Scene hues follow
  the existing Atari row-colour policy. Gameplay keeps its grayscale or warm
  fixed palette and lacks POKEY effects; the existing brief crossing-row
  tearing remains. PAL and physical hardware are untested. The owner has now
  requested commit and publication to Gitea. Include the intro implementation,
  documentation, tests and final validation evidence; leave the earlier local
  GitHub export, compressor/disk changes and porting archive out. Generated
  playable ATRs/ZIPs remain under the ignored build directory, with their
  hashes retained in evidence. Record this implementation's hash in a separate
  log-only commit, push `65xe`, and verify the remote branch hash.

## 49 · 2026-10-14 · Assemble the `65xe/` release folder for GitHub · commit `(not yet committed; fill in)`

- **Goal.** Owner asked for a `65xe/` folder holding the 65XE floppies, the
  appropriate source and the appropriate docs, ready to commit to GitHub as a
  project of its own (the 130XE one is `github/`). Owner then asked for a scan
  for keys, tokens and personal data, a git identity for all projects, and for
  the folder to be published to a new GitHub repository, local git and Gitea.
- **Disks: rebuilt, not just copied.** `build.py --65xe --disks` and
  `--65xe --colour --disks` were rerun from the current tree and compared with
  the ATRs already in `build/atari65xe/`: byte for byte the same (disk 1
  `636cbe07...` grey, `37413985...` colour; disks 2-4 the same in both). So the
  folder's disks are what this source produces, intro included. Both builds
  write to `build/atari65xe/disks/` (the colour set is copied out to
  `colour-disks/` by hand), so running them in that order leaves the colour disk
  1 in `disks/`; the grey build was rerun last to put it right. Because disks
  2-4 are identical in the two sets, `65xe/` has the four grey disks and only
  `colour/mm1-65xe-colour-disk1.atr`.
- **Source.** `tools/export_github_src.py` gained `--readme`, and
  `tools/github_src_65xe_README.md` is the guide for the 65XE export:
  `--out 65xe/src --readme tools/github_src_65xe_README.md`. It is the same
  tree as the 130XE export (one code base, the `XE64` conditionals pick the
  profile), minus the game and everything generated from it. The earlier
  uncommitted compressor-vendoring change (`tools/zx02/`, `disks.py`,
  `test_disks.py`) goes in with it: without it the build needs the Wizardry
  port's copy.
- **Docs.** `65xe/docs/` has `65XE.md`, `64K-FEASIBILITY.md` and `64K-NOTES.md`
  with their links repaired: sibling notes point to `../src/docs/`, and the
  `test-artifacts/` evidence (recordings and pictures of the original, so not
  published) is named as left out, its numbers being quoted in the text.
  `65xe/README.md` is the player's page (what is in the folder, emulator
  commands, how it fits, differences, status, rights), with six screenshots
  taken from the retained evidence: intro title and scene, town and combat
  (grey), outdoors and an encounter (colour).
- **Checked.** Claims in the README were checked against `docs/65XE.md`
  and the code (`-xl` for 64 KB in `lockstep.py`, the sector counts from the
  build output, the walking-frame figures). One claim was dropped as untested:
  that the 65XE disks also run on a 130XE.
- **Scan.** Searched the whole folder (text, the five ATRs, the six PNGs) for
  private-key headers, API-key and token patterns, passwords, emails, IP
  addresses and hosts, and home-folder paths. Nothing secret. The one finding
  was the author's username in absolute paths (`GHIDRA-SOURCES.json`,
  `survey/runall.sh`); the export now rewrites the home folder to `~`.
- **Identity.** The global git identity was changed to the owner's GitHub
  account name and address (`user.name`, `user.email` in `~/.gitconfig`, no
  per-repo override here); earlier commits keep the old identity.
- **Publishing.** The contents of `65xe/` are the root of a new public GitHub
  repository, `Might-and-Magic-1-Atari-65xe-800xl-Port` (as the 130XE one is
  for `github/`), made from a copy of the folder in a scratch directory with
  its own one-commit history. The same files are committed here on `65xe` with
  the export tools and the compressor vendoring change they depend on, and
  `65xe` is pushed to Gitea over SSH (port 222), as before. Left out of the
  commit: `github/` changes, `opencode.json`, `porting.tgz*`, the generated
  `zx0.bin` and `title-first-check/`.
- **Not done.** No new emulator run: the disks are byte-identical to the ones
  already checked (entry 48). `github/src` (the 130XE export) was not
  regenerated and now lags this tree. The copy of this log inside `65xe/src`
  was exported before this entry's commit hash existed, so it shows the
  placeholder.
- **Carries over.** A release folder needs the images rebuilt from the source
  that is shipped beside them, a README that says only what was tested, and
  documents whose links still work once the evidence folder is left out.
