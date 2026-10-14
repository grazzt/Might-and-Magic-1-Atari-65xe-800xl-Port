# Host oracle

Written 2026-10-10. The oracle runs the original C64 game code on the host, without an emulator, and produces the same record a VICE run does: keys accepted, text printed, disk commands. It is the reference the Atari build will be compared with, key by key. How it was built and what went wrong is entry 12 of [PORTING-LOG.md](PORTING-LOG.md).

**Result:** all seven recorded sessions replay on the oracle with every event equal to VICE's, including two fights won, one lost, treasure, three saves and a saved game loaded again after a restart, and its memory equals VICE's at every checkpoint except for a handful of timing bytes. The longest session takes 10 seconds.

## Reproduce

```bash
python3 tools/analyze_c64.py && python3 tools/mmdisk.py        # decoded disk sides (needed first)
python3 tools/oracle.py tools/traces/boot-to-fight-and-save.txt --compare test-artifacts/c64/trace-fight-save
python3 -m unittest tests.test_oracle                          # all seven sessions and the rules, about 50 seconds
python3 tools/oracle_explore.py tools/traces/boot-to-fight-and-save.txt dungeon 'LIIIIIJI|A|' --screen   # try keys
```

`oracle.py SCRIPT` writes `build/oracle/<script>/trace.json` and a picture `NAME.png` for every mark. Options: `--settle` plays the script as `c64_trace.py --settle` does (see "Pictures"); `--quick` plays it with a key at every pause (timing rule 3); `--compare DIR` checks it against a VICE `trace.json`; `--keep-ram` writes 64 KB of RAM at every mark; `--coverage` writes which addresses were executed, per disk load.

`oracle_explore.py SCRIPT MARK KEYS` plays a script up to one of its marks and then the keys given, and prints what the game printed, read and took, with the text screen at every `|`. A run takes a second or two, so a route, a fight or a prompt can be tried many times over. It is how the two sessions added on 2026-10-11 were worked out.

It needs the C64 KERNAL and character ROMs from the shared VICE installation ([REFERENCES.md](REFERENCES.md)); their hashes are checked.

## What it is made of

| Part | In the oracle |
| --- | --- |
| CPU | `tools/mos6502.py`: the 151 documented opcodes, no decimal mode, approximate cycle counts. The interpreter loop is generated from the opcode table and runs about 5 million instructions a second |
| Memory | 64 KB of RAM; KERNAL ROM at `$E000–$FFFF` and I/O or character ROM at `$D000–$DFFF` as the CPU port says. BASIC ROM is never mapped: the game switches it out in its first instructions |
| KERNAL | The real ROM. The game uses its interrupt handler (clock, keyboard scan) and `GETIN`; both run as on a C64 |
| Video chip | Registers are stored. The raster counter, the raster compare and its interrupt work, because the game's split screen and clock depend on them. Nothing is drawn |
| CIA 1 | Timer A and its interrupt (the KERNAL's 60 Hz tick until the game turns it off). The keyboard matrix reads "nothing held" |
| CIA 2, sound chip, colour RAM | Stored; SID writes counted, with an optional cycle/frame/register/value trace (`machine.sid_trace`) |
| Disk drive | None. See below |
| Keyboard | A script puts PETSCII codes into the KERNAL's keyboard buffer, as the VICE scripts do |

### Start state

The run starts where the second boot file jumps to the game's first program, `$4000`, from a memory image captured in VICE at that instant: `test-artifacts/c64/oracle-start/` holds the 64 KB of RAM, the I/O area and the registers. `tools/traces/capture-entry.txt` regenerates it. Everything executed after that is the game's own code or the KERNAL's.

The capture is needed because the game inherits state from the C64's power-on (zero page, vectors, the keyboard buffer) and from its own loader, which the oracle does not run.

### The disk

The game reaches the disk through `$9D0D` (read) and `$9D10` (write). The oracle stops at those two addresses, copies the bytes between RAM and the decoded side ([mmdisk.py](../tools/mmdisk.py)) and returns as the real routine does: A = 0 with Z and carry set, Y = the low byte of the length, X = the loader's clock-line byte, and `$FC–$FF` left as the loader leaves them. The other loader entries raise an error if called; the entry that sets the video bank runs as original code.

A write changes the oracle's copy of the side for the rest of the run. Nothing is written to the files under `build/`.

### Scripts

The same files as for VICE, in `tools/traces/`. Two steps differ:

- `wait N` runs until the game asks the KERNAL for a key and none is there, or N instructions. Nothing in the oracle needs real time.
- `snapshot` and `resume` are not supported. A run from boot takes under a second to reach the town.
- `restart` (switch the machine off and on) makes a new machine from the start state and keeps the disks as the game has left them. VICE does it with a second emulator on the first one's disk copies; the Atari harness with a cold start. What the game saved is then what the new machine loads.
- `pauses XX` and `pauses off`: see timing rule 3.

## The timing rules

The oracle is not cycle-exact and a disk read takes no time, so interrupts fall at different instructions than in VICE. The game's logic must not depend on that. Three rules, the same on both sides, remove the places where it would:

1. **`press`: a key arrives on the first pass of the key-wait loop** (`$0E3B`). The loop counts its passes into `$2D/$2E`, and those feed the random numbers. (Phase 0.)
2. **After waiting at a disk prompt in play, the script resets those two counters:** `ready`, then `poke 002d 00 00`, then `press 0d`. While VICE gives the drive time to notice the new disk, the game sits in the key-wait loop and the counters run. How far they run depends on exact timing; a person swapping a disk would make it arbitrary anyway. The reset defines it.

3. **`pauses XX`: a key that ends a pause arrives on the pause's first poll** (`$C378`). The pause routine (`$C355`) waits on the KERNAL clock and asks for a key on every pass; a key ends it. After `pauses XX` every pause finds key `XX` on its first poll, until `pauses off`. The step may only follow `ready`, when the machine is still. (Added 2026-10-11.)

Rule 2 was found here, not predicted. Without it the five sessions still printed the same text, but memory showed `$2D/$2E` and the random state `$16–$19` different from VICE after the first disk swap in play. Nothing random happened to be printed afterwards.

**What a key during a pause does (checked, 2026-10-11).** It ends the pause and is used up; nothing else in the game's logic notices. The fight-and-save session played with a key at each of its 35 pauses (`--quick`) prints, reads and writes exactly what the plain session does, the saved roster is the same, and it takes 24 seconds of C64 time instead of 94. At the end, memory differs from the plain run's only in the timing bytes listed below. During the run one more byte differs for a while: `$0371`, where the key reader keeps the last key it returned, holds the pause's key until the next key replaces it. The reader uses that byte only to restart the KERNAL's repeat delay when a key differs from the last one. VICE agrees: the same session with the same keys at the same polls gives the same 264 events. *Checked on Atari800, 2026-10-11:* the reader stops ordinary effects on keys and preserves the exceptions for effects 5, 6 and 9 (`$C650–$C674`). The oracle now records SID writes; all nine effect sequences equal VICE ([SOUND.md](SOUND.md)).

**The dice have little to work with when every key comes on the first pass (checked, 2026-10-11).** The key wait mixes the number of passes it made into the generator. With `press` that number is always the same, so the same walk gives the same throws however often it is repeated: after fourteen different prefixes of turns and nine of searches, repeated visits to a square whose handler starts an encounter on one of two outcomes of a throw (4,7 under Sorpigal, `$87DC`) met nothing every time. A script that wants other dice says so with the device of rule 2, a `poke` of the counters after `ready`: `boot-to-treasure-and-reload.txt` sets them to what they are one pass later, and the party meets three gremlins on the same walk.

## How well it agrees with VICE

**Events.** `--compare` requires every key, every printed string with its row and column, and every disk command (side, block, offset, length, address, caller and the hash of the data) to be equal and in the same order.

| Session | Instructions | C64 time | Host time | Events equal |
| --- | --- | --- | --- | --- |
| `boot-to-outdoors` | 1,317,287 | 5 s | 0.3 s | 58 |
| `boot-to-fight-and-save` | 26,516,552 | 94 s | 5.1 s | 264 |
| `boot-to-town-services` | 5,446,291 | 20 s | 1.1 s | 122 |
| `boot-to-side-d` | 3,099,443 | 11 s | 0.6 s | 83 |
| `boot-to-new-character` | 388,722 | 1 s | 0.1 s | 51 |
| `boot-to-treasure-and-reload` | 17,217,910 | 61 s | 3.9 s | 277 |
| `boot-to-death` | 48,802,794 | 171 s | 10.4 s | 178 |
| `boot-to-fight-and-save --quick` | 6,682,426 | 24 s | 1.6 s | 264 |
| `title-scenes` | 9,577,909 | 28 s | 1.8 s | 31 |

The fight is the strong case: which monsters appear, every hit and miss and the experience award all come from the random numbers, and the roster written at the inn has the same hash. All five matched on the first run of the finished oracle.

The two sessions added on 2026-10-11 were worked out on the oracle first and played in VICE afterwards. The death session matched on VICE's first run. The treasure session's first comparison stopped at the roster read after the restart: the trace tool had hashed that read against the original disk, not the one the first machine left. That was the tool's fault; with it put right all 277 events are equal. `boot-to-treasure-and-reload` has a wandering group and the choice before a fight, a fight won, a search, a chest with a trap, gold and an item, a save, then a restart after which the roster read from the disk has the hash of the one written. `boot-to-death` has a lair, a fight lost, the death screen, and the game going on from the options menu with the roster read again.

**Memory.** With `--keep-ram` on both sides, RAM was compared at every mark of the fight-and-save and side-D sessions (29 marks) and of the two sessions added on 2026-10-11 (47 marks). Between 9 and 23 of 65,536 bytes differ, always from this list:

| Bytes | Why they differ |
| --- | --- |
| `$00–$01` | VICE's RAM dump shows the RAM under the CPU port |
| `$A1–$A2` | KERNAL clock: the oracle's disk reads take no time |
| `$01E3–$01F8` | Old return addresses below the stack pointer, left by interrupts |
| `$9D22–$9D25`, `$9EF8`, `$9F53`, `$9FBD`, `$9FC3` | Variables inside the loader, which the oracle does not run |
| `$C353–$C354` | The pause routine's target time on the clock |
| `$29`, `$03A0`, `$C40C`, `$C69F` | Sound position and the split-screen bank byte: where an interrupt happened to be |

Everything the game's logic lives in is equal.

**Pictures.** `tools/c64_screen.py` draws the screen from the oracle's memory: text, hires or multicolour bitmap, from the bank and addresses the game's display mode selects, with the split between the two bitmaps at picture row 127. Compared with VICE's screenshots, pixel for pixel after mapping both to the sixteen colours: **all 66 pictures of the five sessions are identical.**

**The title and its scenes (traced, 2026-10-12).** `tools/traces/title-scenes.txt` stays in the title program: its two frames, `SPACE`, the eight scenes, the frames again. It has no key wait, so the three timing rules do not come into it; its marks are taken with `until` at the title program's two waits and a short `wait` for VICE's screenshot. The oracle and VICE agree on all 20 disk reads and all 11 pictures on the first run ([recording](../test-artifacts/c64/trace-title-scenes), `tests/test_title.py`). This is the reference the Atari's title is checked against ([TITLE.md](TITLE.md)).

**Transient Atari screens and speed (checked, 2026-10-11).** Settled oracle pictures cannot detect the colour bytes briefly displayed as text during a mode switch. `port/atari/speed_check.py` therefore captures every transition frame and checks the actual displayed text snapshot before the mode flags change as well as afterwards. Its inputs retain the first-poll rule; VICE speed measurements also stop at successive first polls. Exact palette-cache probes compare cached results with forced full calculations. These are separate presentation/timing checks: the game-state comparison and all its exclusions stay unchanged. [Findings and limits](SPEED.md).

That needed one change on the VICE side. A VICE screenshot is its last finished frame, and at a mark taken the instant the game asks for a key it does not yet show the newest text (the options menu came out as an empty frame). `c64_trace.py --settle` waits a few frames before each such mark and then resets the wait counters (rule 2). The settled runs are therefore different sessions from the plain ones: other random numbers, another fight. They are stored as `test-artifacts/c64/settled-*`, and the oracle agrees with them in events as well as pictures, which makes ten sessions in all.

**Coverage against the static split.** In the five sessions the oracle executed 7,095 distinct instruction addresses in 17 files. Every one is an instruction start in Phase 1's static code map (`python3 tools/disassemble.py --coverage build/oracle/*/coverage.json`). The two were made independently.

## What it does not do

- **Pictures are of a still screen.** Mid-line effects at the split are not modelled (VICE shows the switch part-way through row 126; the oracle switches at row 127, which matched every picture). Sprites are not drawn; the game has shown none.
- **No audio synthesis.** SID register writes can be recorded with `machine.sid_trace = []` (traced, 2026-10-11). `tools/c64_sound.py --vice` decodes all nine effects and proves their 468 writes equal VICE's. The oracle does not emulate SID waveforms or output PCM; [SOUND.md](SOUND.md) records the Atari translation and evidence.
- **Approximate time.** No page-crossing or bad-line cycles, instant disk. Good enough for interrupts; not a measure of real duration.
- **No held keys.** Keys come from the buffer only; the CTRL flag is poked as in the VICE scripts.
- **Only what seven sessions exercise is confirmed.** Of the pre-fight choices only "attack" is in a recorded session. Retreat, bribe and surrender, finding or removing a trap, a character raised from the dead, and the three side-D areas that read keys themselves have not been run on either side.
- **No settled pictures for the two newest sessions.** Their events and memory are compared with VICE; their pictures are not (the five older sessions' 66 are).
- **A run's disk changes are dropped at its end.** Within a run, `restart` keeps them.

## What it found about the game

- **The area's event code is not entered on every move.** Resident code jumps to `$8432` only when bit 7 of `$38` is set (tested at `$10F9`). Walking 20 squares through sector `EJ` executed nothing in the area file. Event squares are a subset of the squares whose state byte has bit 7 set in 52 of 55 areas; the exact rule is not worked out.
- **The 3-D view code**, by counting executed instructions over one step: `$0F1D–$135F`, page-flipped between the two bitmaps ([C64-CODE.md](C64-CODE.md)).
- **The first disk swap in play is where runs diverge** if the wait counters are left alone. See rule 2.
- **How the party dies, and where treasure is** (2026-10-11): see "Encounters, treasure and death" in [C64-RUNTIME.md](C64-RUNTIME.md).
- **The combat file keeps the machine's NMI vector** at `$271E/$271F` while it copies the lower bitmap with the KERNAL switched out, and puts it back afterwards. Seen first as two bytes that differ between the C64 and the Atari after a lost fight.

**Ordinary-key reverse transitions, checked 2026-10-11:** `transition_check.py` captures six character sheets through POKEY input with the normal kernel. These inputs do not obey first-poll timing and cannot be compared directly with oracle RNG checkpoints. Its settled assertions check the display list and kernel integrity; transient correctness also needs visual inspection. All 240 captured frames were inspected without reproducing the Windows report. [Evidence and limits](../test-artifacts/reverse/README.md).

**Profiling model, checked 2026-10-11:** `graphics_profile.py` traces the unchanged original oracle for drawing attribution and replays actual native refresh snapshots on the host core for conversion attribution. It adds page-crossing penalties to the reported instruction sums without changing the oracle IRQ clock. All seven completed conversion buffers/cache records and row palettes equal native output. Native scanline timestamps separately measure DMA/interrupt-inclusive time. This does not replace game-state or VICE validation. [Method and limits](GRAPHICS-PERFORMANCE.md).

**Optimized converter checks, checked 2026-10-11:** `graphics_check.py` executes
the captured pre-optimization kernel as an independent full-conversion
reference. It compares all 8,000 visible bytes and 100 palette values for 24
real/adversarial refreshes, plus all 16 mapping qualifications and exhaustive
byte/mixed-page translation tests. Optimized native snapshots also reproduce
host output. No new lockstep exclusions or oracle timing changes. The idle
sampler follows code labels after palette scratch moved to UNDER; test-call
trampolines use an explicit reserved label, outside that scratch.

**Shared mapping checks, checked 2026-10-11:** `palette_check.py` captures
nine native settled states through the existing first-poll scripts in
separate Atari800 processes. It compares the new complete refresh and 228
adversarial palette calls with the captured pre-change kernel, including
the build-A/build-B/restore-A/request-B invalidation negative and positive
shared hits. The old host refresh also reproduces the captured native
display. It injects the new boot-invalid mapping key when replacing a
kernel, rather than interpreting old scratch bytes as a valid new key.
Game hashes retain existing exclusions; the eight lockstep sessions/saves
remain the gameplay proof. [Evidence](PALETTE-PERFORMANCE.md).

**Held-key checks, checked 2026-10-11:** `keyboard_check.py` runs the original
C64 ROM scanner against a CIA key matrix and calls the original reader,
comparing eight held-letter cases with the Atari routine. The separate
`boot-to-ctrl-attack.txt` first-poll script matches all 149 VICE events and
ten Atari checkpoints; total nine scripts / 116 checkpoints and three saves.
Ordinary physical holds affect wait-counter RNG and are not claimed equal
to first-poll damage results. Their accepted command/character coverage and
release behaviour are tested in both emulators. Temporary Atari800 observation
at `$0E45` emulates the original JSR/stack/cycles and is removed afterwards.
Differential kernel injection migrates relocated row palettes in both
directions, preserving warm cache/row-reuse tests. [Method](KEYBOARD-REPEAT.md).

**Disk checks, checked 2026-10-11:** OS switching is now batched across Atari
direct sectors; a startup zero range is recreated exactly. Neither oracle
timing rules nor comparison exclusions change. The same nine scripts / 116
checkpoints and three exact saves pass, including cold-start reload. Native
disk probes check exact partial/upper reads, zero page, IRQ, loader returns
and a patterned write/readback separately. Their trampoline uses free TOP
padding because SIO overwrites the shared probe/sector buffer.
[Method](DISK-PERFORMANCE.md).

**Colour policy, checked 2026-10-11:** `colour_policy.py` independently
enumerates original bitmap pairs and matrix/colour-RAM inputs. Its old
policy reproduces nine frozen native graphics frames; its corrected policy
matches all new native buffers/palettes and three Altirra frames. Colours
intentionally change for the wide encounter layout; walking still compares
with the frozen converter. New regressions cover bitmap-only changes,
layout transitions, all 256 distances and all byte-presence values. Game
exclusions, oracle inputs and timing rules stay unchanged; nine scripts /
116 checkpoints and three saves pass (87 tests). [Scope](COLOUR-SELECTION.md).

## Additional scenario checks — 2026-10-12

`tools/coverage_check.py` verifies twelve new sessions against plain and settled VICE recordings, including explicit outcome assertions and 153 new pixel comparisons. `poll CALLER KEY` supplies a nonzero key at a direct GETIN or `$A087` call, after its triggering `press`. `c64_trace.py --settle-preserve` records each mark's original key-wait counters on the oracle and restores those exact bytes after its screenshot delay; resetting every mark to zero could change encounters and the entire scenario. Both plain and settled sessions must exercise the intended behavior. The earlier recordings retain their settling convention. [Findings](GAMEPLAY-COVERAGE.md).
