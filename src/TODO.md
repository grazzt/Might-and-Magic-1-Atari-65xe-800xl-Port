# TODO: Might and Magic I → Atari 130XE

Handoff written 2026-10-11, initially at commit `be75784` on `main`; updated the same day through encounter colour selection (log entry 34) and on 2026-10-12 for the title (entry 36). If you are picking this up later, run the checks in "Start here" first and trust them over this file.

## Where the project stands

The original C64 game code runs unchanged on an emulated Atari 130XE. A small Atari kernel stands in for the C64's hardware; 35 instruction operands in the game's files are redirected and nothing else in them is touched.

- **Game logic is proven identical to the C64.** Nine scripted sessions run on the Atari with memory equal to the reference at 116 checkpoints, and three saves equal on disk. They cover the menu, creating a character, town services, a spell, fights won and lost, Ctrl+A automatic combat, treasure, a save loaded after a power cycle, death, the outdoors and all four disk sides.
- **It displays.** Text screens and the play screen (in colour) both work. 25 screens are shown beside the C64's in `docs/SCREENSHOTS.md`.
- **It plays in two emulators.** Atari800 runs the lockstep comparison; AltirraSDL runs a shorter play-through, including with real serial disk transfers.
- **Sound now works (2026-10-11):** all nine effects translated to POKEY, with approximate envelopes. Oracle/VICE SID traces, Atari800 PCM, key rules and Altirra SIO restoration are checked ([details](docs/SOUND.md), log entry 21).
- **It starts with the C64's title (2026-10-12):** the original title program runs first, with its two frames, its three-voice tune and its eight scenes; Escape starts the game. Both frames are pixel-exact, the tune's pitches are checked tick by tick, and all nine scripts still equal the reference with the title in front ([details](docs/TITLE.md), log entry 36). The checks of the game itself use a disk without the title (`build.py --no-title`), which is byte for byte the disk as it was.
- **Transitions and speed checked (2026-10-11):** text-to-graphics transient `2` characters fixed in both emulators, movement 8–11% faster, return to graphics 24% faster; [details](docs/SPEED.md), log entry 22. Further bitmap-conversion speed, matched real-time effect pacing and wider coverage remain open.

## Start here

Read these, in this order. They are short and current.

1. `SPEC.md` — the decisions that are settled (target machine, fidelity, method).
2. `docs/ATARI-DESIGN.md` — how the Atari build works and what is checked.
3. `docs/ORACLE.md` — the host reference, the script language, the three timing rules.
4. `docs/PORTING-LOG.md` — entries 15 to 22 for the Atari work; the "Recipes" and "Mistakes worth not repeating" sections near the end.
5. `docs/TITLE.md` — the title stage, if that is what you are touching: it is separate from the kernel and gone when the game starts.

Then confirm the tree is healthy (about six and a half minutes):

```bash
python3 -m unittest discover -s tests        # 103 tests; Altirra needs local socket access
```

If the tests are skipped rather than run, the generated inputs are missing: run `python3 tools/analyze_c64.py && python3 tools/mmdisk.py` first. The emulators and the assembler come from the sibling project `../wizardry_1` (or `$WIZARDRY_ROOT`); do not modify or copy that project.

## The three machines and how they are compared

| Machine | Tool | Role |
| --- | --- | --- |
| C64 in VICE | `tools/c64_trace.py` | The real thing. Slow; used to record reference sessions |
| Host oracle | `tools/oracle.py` | The game's code on a minimal C64 in Python. Fast, deterministic. The reference the Atari is compared with |
| Atari in Atari800 | `port/atari/lockstep.py` | The build under test; memory compared with the oracle at every mark of a script |

A new behaviour is proven in that order: work it out on the oracle, record it in VICE and compare (`oracle.py SCRIPT --compare DIR`), then run the Atari against the oracle. Scripts are in `tools/traces/`; the step language is documented at the top of `tools/c64_trace.py`.

Useful commands:

```bash
python3 port/atari/build.py                                              # build/atari/mm1.atr (the playable disk, title first)
python3 port/atari/build.py --no-title                                   # the same without the title: what the checks below build
python3 port/atari/title_check.py [--gallery | --altirra [--sio]]        # the title: frames, tune, scenes, Escape
python3 port/atari/lockstep.py tools/traces/boot-to-death.txt --pictures # one script, Atari vs oracle, with pictures
python3 tools/oracle_explore.py tools/traces/boot-to-fight-and-save.txt dungeon 'LIIIIIJI|A|' --screen   # try keys
python3 port/atari/altirra_check.py [--sio]                              # play-through in AltirraSDL
python3 port/atari/screenshots.py                                        # regenerate the gallery
```

## Rules the owner has set

These are standing instructions, not suggestions.

- **Log everything.** Before every commit, append an entry to `docs/PORTING-LOG.md`: goal, what was done and how, result, evidence, what went wrong, what carries over to another game. Entries are append-only; correct an old entry with a new one. The log is meant to let someone port a different game by the same method, so wrong turns belong in it.
- **Keep the findings documents current** (`docs/C64-RUNTIME.md`, `docs/ATARI-DESIGN.md`, `docs/ORACLE.md`, `SPEC.md`, `PLAN.md`). Mark each claim as *traced*, *checked* or *read*.
- **Release target is the 130XE; the owner authorized the separate `65xe` branch/profile on 2026-10-13.** For its checked prototype see `docs/65XE.md`. For future memory work: when a choice costs memory, or you notice memory that could be saved, add a dated line to `docs/64K-NOTES.md`.
- **Fidelity:** game rules, random numbers, data and saves must match the C64 exactly. Presentation (layout, palette, sound) need not.
- **Do not change the game's files** beyond redirecting operands that name C64 hardware in the 130XE profile. The owner-authorized 65XE profile additionally replaces presentation colour writers and adds checked frame-publication entry wrappers; it preserves game logic and verifies original events/saves. Fix things in the kernel (`port/atari/src/kernel.s`) or the build (`port/atari/build.py`).
- **Commits** go directly on `main` unless the owner requests a branch (the current 65XE work uses `65xe`). The commit that does the work leaves `commit \`PENDING\`` in its log entry; a second commit ("Fill in the commit of log entry N") fills in the hash. Commit and push only when the owner asks.
- **Helpers used more than once** move out of scratch folders into `tools/`.

## Tasks, in suggested order

### 1. Sound

Implemented and checked 2026-10-11; see [docs/SOUND.md](docs/SOUND.md).

- `python3 tools/c64_sound.py --vice` records all nine effects: 468 SID writes equal on the oracle and VICE. The indexed setup/clear also reaches pulse width and ADSR registers `$D402–$D407`; the earlier four-register inventory was incomplete.
- `python3 port/atari/sound_check.py` runs all effects, checks pitches, endings, release, key exceptions and sound-off, and writes PCM WAVs to `build/atari/sound/`.
- POKEY translation runs at the VBI tail, after the unchanged game's IRQ. No comparison exclusions or additional game operand redirections were needed.
- Altirra's bridge checks audio registers and SIO restoration; the shared Atari800 harness records PCM with `sound=True`. These are different interfaces.
- Follow-up: timbres are square-tone approximations, envelopes are linear, and the existing Atari fake-raster scheme advances split-mode sound every second VBI. Matching real-time pacing across display modes remains open. PAL/hardware remain untested.

### 2. Measure and improve play speed

First measurement and improvement implemented 2026-10-11; [docs/SPEED.md](docs/SPEED.md).

- Both Atari emulators: step/turns 38 → 34–35 NTSC frames; character-sheet return 34 → 26. Original VICE PAL movement is 130–143 ms; Atari still needs 567–584 ms. The eleven-frame estimate was wrong.
- The transition garble came from displaying `$0400` live while the game reused it for bitmap colours, before its mode flag changed. A completed text snapshot and DMA blanking until publication fix it. All fourteen settled benchmark pictures remain pixel-identical.
- Exact palette caches and unrolled conversion loops improve speed within the existing display bank. The subsequent graphics optimization skips redundant lookup writes, directly copies identity mappings and reuses exact unchanged rows. A stock 130XE cannot keep ANTIC on bank 0 while the CPU accesses extended bank 1.
- `speed_check.py` measures both Atari emulators and original VICE, captures transients, and probes cache invalidation against full calculation. Two new regression tests bring the suite to 81 passing tests, with unchanged game-state/save comparisons.
- Ordinary idle GETIN polling does **not** repeatedly copy the screen: each poll updates its timestamp. The proposed extra wait filter was removed after measurement disproved that theory.
- Still open: further speed work, real-time sound pacing, PAL/hardware. The direct-display alternative in `docs/ATARI-DESIGN.md` would change the game's address arithmetic and requires a deliberate design decision first.

**Reverse-transition follow-up resolved:** the owner confirms that the freshly recopied ATR has no `2`s and attributes the earlier report to the wrong disk copy. No additional kernel fix was made. The 240 ordinary-key character-screen captures remain in [FIX.md](FIX.md).

**Graphics optimizations checked 2026-10-11:** the deep profile found conversion consuming 76.5% of a walking step. All three proposed paths are now implemented: skip redundant lookup-page writes, directly copy identity mappings and reuse exact unchanged rows. Atari800 steps/turns fall from 34–35 to 30 frames (Altirra 30–31), scripted character prompt 26 → 21 and return to town 26 → 25. Walking conversion falls from 441 to 364 ms; 640 cells are converted instead of 1,000. All 82 tests pass with Altirra's required socket access; all fourteen final benchmark pictures are unchanged. No new bank, game changes or comparison exclusions. [Detailed cycles, safety checks and memory limits](docs/GRAPHICS-PERFORMANCE.md), `graphics_profile.py`, `graphics_check.py`, log entries 25–26.

**Palette follow-up checked 2026-10-11:** reuse the live nearest-colour mapping
when the ordered three selected colours match; restored mappings invalidate
its key. Thirteen of sixteen walking rebuilds are skipped. Palette CPU work
falls 19.7%, full conversion 8.1% (364 → 335 ms), Atari800 movement 30 → 29
frames (Altirra 30–31 → 29) and return 25 → 24. Nine town/outdoor/dungeon/encounter/battle captures
retain identical pixels/game bytes; sampled battle commands are text and do
no palette work. All 83 tests pass with Altirra socket access. Only 1 UNDER,
14 EXT and 10 EXT2 bytes remain spare. [Method, broader cases and limits](docs/PALETTE-PERFORMANCE.md),
`palette_check.py`, log entry 28. Further histogram/pixel optimization is open;
disk loading remains the next separate TODO item.

**Held keys fixed, checked 2026-10-11:** the keyboard now honours the game's
all-key repeat flag and original delay/rate counters. Holding Ctrl+A advances
all six characters over multiple rounds in Atari800 and Altirra; release
stops new repeats, with at most one already queued. Original C64 scanner/
reader timing and Ctrl+A command semantics are checked; all 85 tests pass.
The test trampoline now shares the idle disk buffer; palette scratch/row
state moved to fit. Spare LOADER 8, UNDER 1, EXT 0, EXT2 10. The current disk
is `build/atari/mm1-held-keys.atr`. [Cause, tests and exact scope](docs/KEYBOARD-REPEAT.md), log entry 30.

### 3. Disk load times

**First optimizations implemented and checked 2026-10-11:** batch consecutive
direct sectors under one OS switch, and recreate the exactly-zero startup
range instead of reading it. Atari800 patched SIO: boot 4.19 → 1.29 s,
options 0.43 → 0.10 s, inn-to-town 1.42 → 0.78 s and sign-in/save/reload
0.55 → 0.27 s. Altirra patched town/sign-in waits agree; its boot is 3.84 →
0.93 s. Standard serial boot falls 51.9 → 44.2 s and town 10.85 → 10.18 s.
Serial results have ten-frame resolution; the sign-in interval includes
loads after saving, unlike the historical 1.8 s write-only figure.
All 86 tests pass, including exact partial/upper reads and a roster-sized
write/readback. The four game-side payloads and all comparison exclusions
are unchanged. Spare LOADER 5, UNDER 1, EXT 0, EXT2 10. Current normal disk:
`build/atari/mm1-disk-fast.atr`. [Method, controls and limits](docs/DISK-PERFORMANCE.md),
`disk_check.py`, `disk_probe.py`, log entry 32.

- Startup `$E000–$FF49` is now cleared exactly, guarded by a build assertion;
  63 sector reads and 8,192 padded image bytes removed. Other title leftovers
  remain loaded; compression could recreate those patterns without dropping
  state, whereas omitting them requires read-before-overwrite evidence.
- Standard serial SIO still dominates. High-speed negotiation or larger
  sectors remain unimplemented; larger sectors need a safe larger buffer and
  new disk-layout/save checks. The common OS-switch overhead is now batched.
- VICE PAL/true-drive inn-to-town is now measured at 13.228 seconds (`docs/SPEED.md`). C64 boot, options and save times still need measuring so the other Atari loads have a target.

### 4. Colour limits on the play screen

An Atari row has three colour registers (four in the command panel's columns); a C64 cell has its own three. The kernel picks each row's colours from what is on it (`choose_colours` in `kernel.s`).

**Reported issues fixed, checked 2026-10-11:** encounter artwork now counts
matrix colours only when their pixel pairs are drawn. Stale blank-cell
colours no longer outvote green monsters. The panel uses the original blue
strip to distinguish the eighteen-column encounter list from ten-column
commands. Gremlin/snake source-green pixels and all blue-name backgrounds
are retained in the checked frames, in Atari800 and Altirra; the gallery is
regenerated. No original game changes or new comparison exclusions.

- All 87 tests pass, including bitmap-only palette invalidation and layout
  switches. Eleven native captures retain their game hashes. Exact distance
  packing and smaller copy loops fit the same bank; spare 5 / 1 / 0 / 3.
- Walking/turns now take 30 rather than 29 NTSC frames in both emulators;
  the existing speed/transition bounds still pass. An initial conversion-cost
  regression skipped an exact pause target; blank-byte skipping fixes both
  affected combat routes without changing the original pause/clock rules.
- Some border/highlight colours remain approximations: the hardware still
  has fewer colours per row than the C64 has per cell. Broader artwork and
  pixel-weighted selection remain possible follow-ups, with nearly full
  memory. Current normal disk: `build/atari/mm1-colours.atr`.
  [Cause, proof, timing and limits](docs/COLOUR-SELECTION.md), `colour_check.py`,
  `colour_policy.py`, log entry 34.

### 5. Widen what is tested

Each is a new script, worked out with `tools/oracle_explore.py`, recorded in VICE, then run in lockstep.

- **Choices before a fight** other than attack: retreat, bribe, surrender. (Seen in exploration: surrender gave `THE MONSTERS DON'T TAKE PRISONERS!`, a bribe gave `NO RESPONSE`.)
- **Traps:** find/remove and detect magic on a chest. Only "open it" is recorded.
- **One character's death and raising** at the temple.
- **Spells in combat**, shooting, exchanging places, using an item.
- **The three side-D areas that read keys themselves** (`IF` at `$89F0`, `EH` at `$86D2`, `DP` at `$890E`). These bypass the key wait, so the scripts' `press` step does not reach them; they may need their own rule, as pauses did.
- **Settled pictures** for the two newest sessions: `c64_trace.py --settle` recordings, so the oracle's drawing is compared with VICE's screenshots as it is for the five older sessions (`tests/test_oracle.py`, class `Pictures`).
- **Areas beyond Sorpigal.** `docs/c64-areas.json` lists all 55 areas, their exits and 818 event squares. Whole-game coverage is Phase 5 in `PLAN.md`.

When a script needs different dice: with every key delivered on the first poll the game's random numbers barely vary, so walking the same way gives the same result every time. Set the key-wait counters with a `poke` after a `ready` and say why in a comment (see `tools/traces/boot-to-treasure-and-reload.txt`).

**2026-10-12 follow-up implemented and checked:** twelve new scripts cover the three direct input paths, a successful combat spell/bow shot/exchange/charged item, refused bribery/surrender and retreat, trap detection/removal/failure, Crag's death to a gas trap and raising at the temple, and stock-party travel through EJ/C and BB/C. Atari coverage is 21 scripts / 257 checkpoints, with 153 new pixel-equal C64 pictures. The wilderness fight found and fixed a pause-clock stall. Position/destination/party fixtures and remaining branches are explicit in [GAMEPLAY-COVERAGE.md](docs/GAMEPLAY-COVERAGE.md).

### 6. Harden across emulators and ROMs

- **Run the remaining lockstep scripts in AltirraSDL.** `lockstep.py --altirra [--sio]` now supports the same memory/kernel/disk comparisons. The wilderness route passes with both disk modes; other scripts remain to be run there.
- **Atari's own XL OS ROM.** Both emulators use Altirra's replacement OS. The boot builds the text font from the OS ROM at `$E000` and all disk transfers go through the OS's `SIOV`.
- **PAL.** Everything so far is NTSC.
- **A real machine or a cycle-exact check of the display-list interrupt.** The per-row interrupt has little time before `WSYNC`; see "Timing lesson" in `docs/ATARI-DESIGN.md`.

### 7. Parked, pick up when needed

- **Phase 1 leftovers:** most routines carry generated names, 16 KB of tables are untyped, and the 3-D view's geometry (`$0F1D–$135F`) is unread.
- **64 KB prototype implemented.** [docs/65XE.md](docs/65XE.md): two shared display blocks, no extra bank, single ATR or four disks. Complete grayscale gameplay checks pass. Title, colour refinement, sound translation, PAL and physical-hardware validation remain open; keep the working 130XE profile.
- **The rule behind bit 7 of `$38`** (when resident code enters the area file after a move). Partly explained: squares without an event go to a wandering-group encounter.
- **154 blocks on side A are never read** by any recorded session (274 before the title's scenes were traced on 2026-10-12).

### 8. The title (asked for and done 2026-10-12)

The C64's title program runs before the game: [docs/TITLE.md](docs/TITLE.md), `port/atari/src/title.s`, `title_check.py`, log entry 36. Checked in Atari800 and in AltirraSDL with and without its disk patch. The kernel is unchanged; spare LOADER / UNDER / EXT / EXT2 still 5 / 1 / 0 / 3. Current disk: `build/atari/mm1-title.atr`, 726,800 bytes, SHA-256 `fc10b1b7…`.

Open, none of it needed for play:

- **Scenes 3, 5, 7 and 9 lose colours:** two pictures side by side need two more colours in a row than an Atari row has. Changing colour registers in mid-line would give all of them. It cannot be done in ANTIC mode 4 on the first line of a row, so it means a bitmap mode for those 13 rows, a converter of its own and a timed loop. The analysis is in TITLE.md, "Different from the C64, and open".
- **The title frames change in 1.0 seconds against the C64's 0.67**, and scenes stay 3.4 to 4 seconds against 2.8.
- **Black screen during disk transfers**, as in play. With a real drive that is about three seconds before each scene. Keeping the picture up needs row interrupts while the OS has the machine, which the kernel does not do anywhere yet.
- **About ten more seconds to the first prompt with serial transfers** (17 to the title, 37 after Escape). The 42 KB memory image the boot loads after Escape repeats what the title program has just put in memory; with the title in front it could be cut down, but then the two machines no longer start equal unless the title's leftovers are proven unread.
- **The same trap may sit in the kernel:** while it blanks the play screen with row interrupts on, ANTIC can go on interrupting (see "Traps" below). *Read*, not measured.

## Traps that have already cost time

- **C64 hardware addresses that are plain RAM on the Atari are dangerous.** The kernel sits at `$DC00–$DFFF`, where the C64 has its CIAs. An unredirected CIA store once changed an opcode in the kernel and garbled every text screen (log entry 18). The redirection list is static: an access through a pointer would not be in it. `lockstep.py` now compares the kernel's code with its assembled image at every mark; keep that check passing and extend `fixed()` in `build.py` if the kernel's layout changes.
- **The lockstep comparison leaves ranges out** (`IGNORED`, `TIMING`, `MACHINE` in `lockstep.py`). Never add an exclusion without finding the instruction that causes the difference and writing the reason next to it.
- **A symptom that changes when unrelated code moves is an overwrite**, not an emulator fault. One was misdiagnosed that way for two commits.
- **Look at every picture in the gallery before committing it.** Seven garbage pictures were once committed unseen.
- **AltirraSDL never writes to the disk image it is given.** Writes go to a working copy under its settings folder, keyed by the image's SHA-256 (`altirra.working_copy`), and persist between runs.
- **Exploration tools must replay exactly as scripts do.** One extra pass of the game's key-wait loop changes the dice. `tests/test_oracle.py` checks that a script played in two calls equals one played whole.
- **Put a known positive in every search.** A search that reports nothing is only believable if it would have found a case you already know.
- **With its DMA off, ANTIC repeats the instruction it had.** If that was a row with an interrupt, the interrupt comes every eight lines while the screen is off, and the one before the vertical blank is still running when the vertical blank's handler starts. The title stage hung on that in AltirraSDL with serial transfers only (log entry 36). Atari800 does not do it: **run anything that turns the screen off in AltirraSDL, with `--sio`.**
- **A check that needs a title-free start must say so.** `build.build()` makes the disk without the title unless asked (`title=True`); `build.py` on the command line makes the one with it. A harness that boots `mm1.atr` and waits for the first prompt will wait for ever on the titled disk.

## Handoff records and local helper

- `FIX.md` — historical investigation of the permanently garbled text screens (fixed in log entry 18), with a current note linking the separate transition fix (entry 22).
- `resume.sh` — resumes an earlier assistant session; its note about the project's status is out of date.
- `build/atari/mm1-title.atr` — the disk with the title, as built on 2026-10-12 (not in Git: `build/` is ignored).
- `TODO.md` — this handoff, maintained with the implementation.

**Latest walking result (2026-10-12):** movement/turns 30 → 29 NTSC frames and character-sheet return 25 → 24. Independent converter checks, all 28 benchmark pictures and seven game hashes remain exact. [Measurements](docs/WALKING-PERFORMANCE.md).


**65XE town redraw and colour (2026-10-13):** movement/turn blackouts removed;
mode publication now precedes hidden-page clear. Brief shared-row tearing
remains. `build.py --65xe --colour` makes an optional warm palette with zero
extra RAM. Preserve transient tests as well as settled pictures. Details and
remaining work: [docs/65XE.md](docs/65XE.md).


**65XE intro restored (2026-10-13):** disk A now starts the original title,
scenes and tune, using temporary startup RAM. SPACE runs scenes; ESC starts
game/disk B. No extra permanent allocation. `--no-title` remains available.
Remaining 65XE work is atomic redraw, richer gameplay palettes/effects,
PAL/hardware and coverage; [docs/65XE.md](docs/65XE.md).
