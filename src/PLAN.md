# Might and Magic I → Atari 8-bit: port plan

Updated · 2026-10-10 · Phase 0's exit condition is met, with C64 selected by the owner. See [SPEC.md](SPEC.md) and [measured findings](docs/C64-BASELINE.md). This plan reuses what worked for the Wizardry I port in `~/coding/wizardry_1` (the "Wizardry project" below) and changes what doesn't apply.

The step-by-step record of the work done so far, with reusable recipes, is [docs/PORTING-LOG.md](docs/PORTING-LOG.md). Each phase below adds its entries there.

## The key difference from Wizardry

Wizardry I was UCSD Pascal p-code. The Atari port runs the **original, unmodified game code** on a new 6502 interpreter, and only 1 KB of Apple machine code had to be rewritten.

**Might and Magic I (New World Computing, 1986) appears to be native 6502 machine code.** A first look at the Apple 4am crack (2026-10-09) found:

- disk A boots through a DOS 3.3 bootloader and then the game's own RWTS (disk routines);
- disks B–D have DOS 3.3 structure but empty catalogs, so data is read by raw track and sector;
- disk A holds hundreds of Apple-style high-bit ASCII strings (item names, "INSERT DISK B");
- disk A has the opcode density of machine code, plus direct soft-switch and disk-controller accesses;
- there is no trace of Pascal or p-code.

This needs confirming in Phase 0, but it changes the port:

- **No interpreter layer.** The game logic itself touches Apple (or C64) hardware and memory layout directly, so the port is a **retargeting of 6502 code**. Wizardry's port was a new runtime under untouched code.
- **The game logic can still run unchanged.** The Atari has the same CPU. The work is finding and replacing every hardware-dependent part (graphics, text, keyboard, sound, disk) and resolving memory-map conflicts.
- **The verification idea carries over.** A host oracle runs the original binary in a 6502 emulator with trapped I/O, like `pvm`, and the Atari build is compared with it key by key in lockstep.

## Which version to port from: Apple II or C64

**Decision: C64, selected by the owner on 2026-10-09.** The original v2 G64 set is the initial baseline. The comparison below records the original planning rationale; Apple collection and execution are deferred.

| | Apple II (original) | Commodore 64 |
| --- | --- | --- |
| Graphics | Hi-res, 7 pixels per byte, interleaved rows: needs the same byte mapping used in the Wizardry port | Bitmap with **8 pixels per byte**, like Atari mode F; only the cell layout differs |
| Memory map | Uses `$C000`–`$CFFF` for I/O and probably the language card at `$D000`–`$FFFF` | Already avoids `$D000`–`$DFFF` (I/O), like the Atari's `$D000`–`$D7FF` hardware area |
| Disk | Custom RWTS, raw track/sector, 4 disks | KERNAL or custom 1541 code |
| Status | Original; 4am crack available, and the Wizardry project's tools understand Apple disks | Port; images and VICE (with MCP) already set up in the Wizardry project |

The C64 baseline defines behaviour for this port. Apple may be consulted later for differences, but an Apple comparison is not a prerequisite for starting. The table's assumptions are hypotheses: measured C64 title graphics are multicolor, and the banking/memory use still needs a complete inventory.

## Target

- **Emulators first.** The owner plays on emulators (Atari800, Altirra), not real hardware. That allows a large single ATR or several disk images, and makes real-drive limits a later concern.
- **Machine: the 130XE, decided by the owner on 2026-10-10**, with a 64 KB build as a possible later goal ([docs/64K-NOTES.md](docs/64K-NOTES.md) collects what would help it). The original line read: 65XE (64 KB) preferred, with the 130XE as fallback. Expect this game to need the 130XE more than Wizardry did. A native 6502 game written for a 64 KB machine has no p-machine to shrink, and the Atari loses `$D000`–`$D7FF` to hardware. The XL/XE OS ROM can be switched out to recover `$C000`–`$CFFF` and `$D800`–`$FFFF`, at the cost of driving SIO and the keyboard ourselves. The 130XE's banked 16 KB windows can hold overlays or map data.
- **Fidelity:** the same rules as the Wizardry project. Game behaviour, the RNG, data and saves match exactly. Colours, pixel aspect and layout may differ if they look similar. Sound is optional, and the first thing dropped if memory is short.

## Phases

### Phase 0: research library and baseline (structure as in the Wizardry project)

Progress: complete C64 image/manual archives collected and hashed; original v2 standard sectors decoded and directory files independently verified; VICE title and A-to-B/options-menu baseline established; shared toolchain reused. The loader is traced end to end: both boot files, the C64 fastloader and the 1541 drive code are labelled and rebuild exactly, each side decodes to 664 logical blocks, and sides B–D have a named file table ([findings](docs/C64-LOADER.md)). The B→C swap works. A fight and a save are traced and replay identically once keys are delivered on the game's first key poll, which is the timing rule the oracle will use ([runtime notes](docs/C64-RUNTIME.md)). On 2026-10-10 shops, a spell, character creation and side D were traced, the 55 area files' links were extracted ([areas](docs/c64-areas.json)), and a search of all four sides found no further caller of the disk loader. **The exit condition below is met**; what the loaded code does is Phase 1.

Ghidra 12.1.4 is also installed under `~/tools` with a dedicated JDK 21. Headless 6502 import, disassembly and native decompiler operation have been verified on the bootstrap; [setup and reproduction](docs/GHIDRA.md) are documented. The full loader/overlay analysis remains pending.

- **Disk images** with provenance (`SOURCES.json`, `SHA256SUMS`):
  - Apple: 4am crack disks A–D, and the original/clean-crack sets on the Asimov mirror (`images/games/rpg/might_and_magic_I/`);
  - C64: images, with the manual and map/spell texts if available.
- **Reuse rather than copy** the Wizardry project's reference library (6502, Atari, Apple, C64 manuals), emulator setup, toolchain, and `fetch_refs.py`. Either link to them, or factor them into a shared repository that both projects use.
- **Existing work.** ScummVM's `mm` engine reimplements MM1 (PC version) and documents game logic and data formats. Check which formats are shared across platforms. Also look for community notes on MM1 data (maps, monsters, items, roster).
- **Identify the code:** boot each version in an emulator with logging, map what loads where (load addresses, overlays, data disks), and confirm whether it is all 6502 assembly.

**Exit:** a measured C64 memory map and disk-layout map covering the loader, resident code, and overlays. The source decision is already made; Apple analysis is deferred.

### Phase 1: reassemblable source

Progress (2026-10-10): both exit items exist. A static tracer splits all 76 code files into code and data, generated da65 info files rebuild every one byte for byte, and the machine inventory is written ([code findings](docs/C64-CODE.md)): 382 operands in 106 routines, 201 and 76 outside the start-up code. The display, interrupt, sound, key, pause and disk routines of the resident code are read and named. **Still open:** most routines carry generated labels, 16 KB of tables are untyped, and the 3-D view's geometry is unread (its code was located on the oracle later the same day: `$0F1D–$135F`, page-flipped). Ghidra was not needed; the tracer is `tools/code6502.py`.

**Decision, 2026-10-10 (owner):** move on to Phase 2 now and come back to Phase 1 as needed. The open items above are not blocking the host oracle, and running the game on the host will show which code runs (the view drawing included), which is a faster way to find and name routines than static reading. Return here before Phase 3 at the latest: the Atari layout needs the drawing code and the untyped tables understood.

- Use Ghidra to explore the extracted code and VICE captures, label routines, and follow references. Import PRGs with explicit load address, two-byte header offset and payload length; model the C64 and 1541 separately. Pseudocode is an analysis aid, not a replacement for assembly or execution evidence.
- Disassemble the chosen version into ca65 source with da65 info files, built up iteratively, separating code from data and tables.
- **The check is a byte-identical rebuild of every binary.** This is the counterpart of verifying Ewers's Wizardry listings against the disk.
- Label the hardware-dependent routines: screen, text, keyboard, sound, disk, timing. Inventory every absolute I/O address and every place the code assumes a memory layout. The Wizardry game's own p-code computing Apple hi-res addresses was the surprise there; expect more of that here.

**Exit:** the source rebuilds exactly, with a written inventory of everything machine-specific.

### Phase 2: host oracle

Progress (2026-10-10): **exit condition met.** `tools/oracle.py` replays the five recorded sessions event for event and agrees with VICE's memory at every checkpoint apart from timing bytes ([oracle notes](docs/ORACLE.md)). It did not start from the Wizardry project's `cpu6502.py`: that core is built for single native routines with Apple I/O, and a full-machine run needed a faster one with interrupts, so `tools/mos6502.py` is new. The regression tests are the five sessions (create a character, town, dungeon walk, combat, save). Pictures were added the same day (`tools/c64_screen.py`; 66 of 66 equal to VICE's screenshots). Those open items were completed on 2026-10-11: save-then-reload and pause timing in log entry 20; a SID write record checked against VICE in entry 21 ([sound findings](docs/SOUND.md)).

- Run the original binary in a Python 6502 emulator (start from the Wizardry project's `tools/pvm/cpu6502.py`). Trap hardware I/O: keyboard from a script, disk from the images, screen memory rendered to PNG/text.
- Make it deterministic: find the game's RNG and how it is seeded, and give it the same kind of key-timing model `pvm` uses.
- Add regression tests for creating a party, the town, a dungeon walk, combat, and save/reload.

**Exit:** scripted, repeatable play on the host, matching the real version in an emulator at spot checks.

### Phase 3: memory map and Atari skeleton

Progress (2026-10-10): the design is written ([docs/ATARI-DESIGN.md](docs/ATARI-DESIGN.md)) and its riskiest part is tried: an emulated Atari shows the game's town screen straight from C64-ordered bitmap memory, using ANTIC mode 4 with each row's bitmap as its character set (`port/atari/display_demo.py`). Decisions taken: 130XE; OS ROM out during play; no relocation; keep the two-bitmap scheme, feeding the display by copying into an extended bank at first.

**Exit condition met the same day, and more.** `port/atari/build.py` makes a bootable disk; `port/atari/lockstep.py` plays a script on the oracle and on the Atari in Atari800 and compares memory at every mark. All six scripts pass: 62 marks with memory equal and both saves equal on disk. That is most of Phase 4's slice too, at the level of game state. Later the same day the play screen was joined on (in grey shades), the keyboard was shown to work and the disk prompts were made unnecessary: `port/atari/play_check.py` plays from the first prompt into the town through the emulated keyboard. Colours followed ([screenshots](docs/SCREENSHOTS.md)). Missing for a finished Phase 4 slice: sound, a measured speed, and play on a second emulator (Altirra). **2026-10-11:** it plays in AltirraSDL, a save and a restart included, also with the OS doing real serial transfers (`port/atari/altirra_check.py`, log entry 19); disk times are measured there. Sound was added later on 2026-10-11 (log entry 21): all nine original effects produce POKEY audio, with their write records checked against VICE and their PCM/pitch/key rules checked on Atari800; Altirra checks pitch, key-stop and SIO restoration. Play speed was then measured on VICE and both Atari emulators (log entry 22): text/graphics transition garble fixed, movement 38 → 34–35 NTSC frames and bitmap return 34 → 26, without changing game code or settled pixels ([docs/SPEED.md](docs/SPEED.md)). Further conversion speed and matched real-time effect pacing remain open. **Later the same day** the slice's last pieces were scripted and pass on all three (VICE, the oracle, the Atari): treasure, a save loaded again after a restart, death and renewal, and a key during a pause (log entry 20). That is the whole of "create a party → town → dungeon → fight → return → save → reload".

- Lay out the Atari memory: where code, data, the screen (320×192 mode F, or a character mode for text screens), buffers and the stack go.
- Decide whether to switch out the OS ROM and whether 130XE banking is needed.
- Replace the hardware layer with Atari routines, and convert disk access to SIO sectors on ATR images.

**Exit:** the retargeted build boots on Atari800 to the first screen. A lockstep harness (the Wizardry project's `harness.py` + `lockstep.py` pattern on `libatari800`) compares screens and game state with the oracle after each key.

### Phase 4: playable slice

Create a party → town → dungeon → fight → return → save → reload, identical to the oracle in lockstep.

### Phase 5: whole game and polish

All areas, spells, items and endgame; a bootable disk set; optional sound; PAL check; and testing in both Atari800 and Altirra.

Progress on the polish, 2026-10-12: the disk starts with the C64's title program, its tune and its scenes, in front of an unchanged game ([docs/TITLE.md](docs/TITLE.md)). Sound, speed, disk loading and encounter colours were done on 2026-10-11 ([TODO.md](TODO.md) has the list and what is open).

## Decisions to make, and when

| Decision | When | Inputs |
| --- | --- | --- |
| Apple or C64 as the source | **Done: C64** | Owner's decision, 2026-10-09; original v2 G64 baseline |
| 65XE or 130XE | **Done: 130XE** | Owner's decision, 2026-10-10; 64 KB kept as a possible later goal |
| OS ROM in or out | **Done: out during play** | The game's code runs through `$C000–$CBFF` and its second bitmap is at `$E000` |
| Disk layout | Phase 3 | Number of images, one big ATR vs a set; emulators only for now |

## Main risks

- **Memory.** The game may genuinely need more than a 64 KB Atari offers once `$D000`–`$D7FF` and the screen are taken out. Mitigations, in order: switch the OS ROM out, use 130XE banking, then shrink the screen.
- **Hidden hardware assumptions.** Self-modifying code, timing loops and absolute screen arithmetic can be scattered through the game logic. Phase 1's inventory and Phase 2's oracle are there to find them early.
- **Disassembly effort.** Native code has to be understood well enough to relocate, which is much more work than Wizardry, where the p-code ran untouched. The byte-identical rebuild keeps this honest.
- **Copy protection** on Apple disk A: work from the 4am crack and record that.

## What carries over from the Wizardry project

- **Methods:** provenance discipline, verifying a reconstruction against the original binaries, a host oracle with a deterministic key-timing RNG model, lockstep comparison on `libatari800`, and the fidelity rules.
- **Code:** `cpu6502.py`, `harness.py`, `lockstep.py`, the PNG renderers, the emulator and toolchain setup scripts, and the Atari display-list, SIO and keyboard routines in `port/atari/src`.

**2026-10-11 follow-up, checked:** the owner still reports reverse-transition `2`s in Windows Atari800. A fresh normal build passes six direct character-screen captures with ordinary keys; the local pre-existing generated image did not match its layout before rebuilding. The owner subsequently confirms that recopying the ATR removes the symptom; no new kernel fix. see [FIX.md](FIX.md).

**Graphics follow-up, checked 2026-10-11:** all three converter paths are implemented: avoid identical lookup-page operand patches; directly copy identity mappings; exactly reuse qualified unchanged rows. Movement falls from 34–35 to 30 Atari800 NTSC frames and walking conversion from 441 to 364 ms. Original game code and benchmark pixels/game bytes remain equal. Native timing, CPU attribution, DMA diagnostics, memory costs and validity checks are in [GRAPHICS-PERFORMANCE.md](docs/GRAPHICS-PERFORMANCE.md), log entry 26. Palette selection and display contention remain major costs.

**Palette follow-up, checked 2026-10-11:** the live nearest-colour mapping
now reuses an exact ordered three-colour key across rows. Walking palette
work falls 19.7%; Atari800 movement is 29 frames and conversion 335 ms.
All 83 tests and broader screen comparisons pass. Histogram work and display
contention remain; code space is almost exhausted. Disk loading is the next
separate optimization task. [Results and constraints](docs/PALETTE-PERFORMANCE.md), log entry 28.

**Keyboard follow-up, checked 2026-10-11:** held Ctrl+A now repeats through
all six characters in both Atari emulators. Restore the game-controlled
delay/rate counters, suppress repeat backlog and stop on release. The new
original C64/VICE automatic-combat script brings gameplay coverage to nine
scripts / 116 checkpoints; all 85 tests pass. Memory rearrangement fits
existing banks; EXT now has zero spare bytes. [Findings](docs/KEYBOARD-REPEAT.md), log entry 30.

**TODO #3 first improvements, checked 2026-10-11:** disk calls now batch OS
switching across direct sectors, and boot recreates 8,010 known zero bytes.
Atari800 patched boot falls 4.19 → 1.29 s and inn-to-town 1.42 → 0.78;
Altirra standard serial boot falls 51.9 → 44.2 s. All 86 tests pass, with
unchanged game-state/save comparisons. Main-memory LOADER spare is now five
bytes. Standard serial transfers, startup compression and broader gameplay
coverage remain opportunities. [Findings](docs/DISK-PERFORMANCE.md), log entry 32.

**TODO #4 reported losses resolved, checked 2026-10-11:** green monsters no
longer lose to colours advertised by blank cells, and the wider encounter
name panel keeps its blue background. Atari800/Altirra checks and the updated
25-pair gallery confirm it; all 87 tests pass. Game bytes and comparison
rules are unchanged. No extra bank; walking costs one additional NTSC frame.
Broader gameplay/areas (TODO #5) remain the next coverage task.
[Findings](docs/COLOUR-SELECTION.md), log entry 34.

### 2026-10-12: wider coverage and walking follow-up

Twelve new scripts exercise the unusual side-D key paths, combat actions, encounter choices, chest traps, one death/raising and a stock-party wilderness route. Phase 5 now has 21 Atari scripts / 257 checkpoints; this is still partial world coverage. The wilderness fight exposed a skipped exact pause-clock target, fixed in the kernel without game changes. Walking/turns improve by one NTSC frame (30 → 29); larger conversion changes remain open. [Coverage](docs/GAMEPLAY-COVERAGE.md), [measurements](docs/WALKING-PERFORMANCE.md).

### 2026-10-13: 64 KB feasibility investigated

**Read/host-checked:** [64K-FEASIBILITY.md](docs/64K-FEASIBILITY.md) contains the
memory ledger, a two-block direct-display proposal, a native single-screen
alternative and implementation gates. The host survey covers all 21 gameplay
scripts with unchanged events. Combat backup and overlay lifetimes rule out
naive framebuffer reclamation. This completes the requested investigation;
implementation and native 65XE validation remain separate work.


### 2026-10-13: separate 65XE prototype implemented

**Emulator-checked:** the direct-display route links without extended RAM and
passes all 21 native gameplay scenarios / 257 checkpoints in Atari800 at
64 KB. Keep the 130XE profile and its presentation. The 65XE prototype uses
fixed grayscale, omits title and POKEY effects, and preserves original game
state/data/saves. [Build commands, allocations and next work](docs/65XE.md).


**65XE redraw/colour follow-up, 2026-10-13:** fixed black town redraws by
publishing at the game flip and retaining bitmap DMA; shared-row tearing is
still open. Optional fixed warm palette costs zero extra RAM. Preserve this
baseline while budgeting atomic crossing-row staging and richer palettes;
[transient captures and contracts](docs/65XE.md).


**65XE intro follow-up, 2026-10-13:** original C64 title, eight scenes and
three-voice POKEY translation now run in temporary pre-game RAM. No permanent
kernel bytes or bank added. Default CLI builds include it; `--no-title` skips.
Both frames/scene pixels and post-intro game state are checked; [details](docs/65XE.md).
