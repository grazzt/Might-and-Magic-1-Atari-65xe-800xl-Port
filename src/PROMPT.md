# Prompt: port an 8-bit game to Atari 8-bit computers

Fill in the project brief below, then give this entire document to the LLM working in the new project folder. Everything needed from the earlier porting work is explained here; no sibling repository or previous conversation is required. Unfilled optional fields use the stated defaults. The instructions assume an agent with filesystem, terminal and web access; an agent without those capabilities must identify that limitation and provide runnable steps without claiming to have executed them.

---

## Project brief

- **Game:** [TITLE, EDITION, LANGUAGE, REGION if known]
- **Source platform/version:** [NES / Apple II / C64 / other; or investigate and recommend]
- **Source media:** [local paths or download/reference links; or ask me for the game media]
- **Target:** [default: stock Atari 130XE, 128 KB; consider a 64 KB XL/XE build if feasible]
- **Target environment:** [default: Atari800 and Altirra emulators first; real hardware compatibility tracked separately]
- **TV standard:** [default: NTSC first; PAL compatibility remains a separate acceptance item]
- **Output:** [default: bootable ATR disk image; consider XEX or cartridge if better suited]
- **Fidelity:** [default: preserve game logic, data, RNG results under equivalent inputs, and logical save contents; adapt graphics and sound to Atari hardware]
- **Host development OS:** [detect it if omitted]
- **Special constraints:** [memory limit, original-code policy, deadline, distribution requirements, etc.]
- **Git/remote policy:** [default: initialize a local repository if absent; commit and push only when requested; no remote is assumed]

## Your assignment and working rules

Build this port, starting from the folder and resources actually available. You are responsible for setting up the tools, investigating the original, choosing an architecture, implementing it, and producing evidence that it works. Proceed through the milestones below. A plan alone does not complete the assignment.

Ask early for the game identity or unavailable media if essential. Resolve routine implementation choices yourself. While waiting for necessary answers, complete independent setup and research. Write down assumptions before relying on them. If a blocker prevents one milestone, continue work that does not depend on it and state precisely what is missing.

Preserve the original game media. Run emulators on disposable writable copies. Keep pristine downloads, hashes, decoding and patches distinct. Do not silently change game rules to make a test pass. Default to retaining original game code and data where practical, but first establish whether native retargeting is possible. An operand-only patch policy worked for one C64 game; it is not automatically possible for NES, 65C02, Z80 or other sources. Document necessary changes and their behavioral consequences.

Use primary manuals, emulator documentation/source, original binaries and recorded execution as evidence. Verify downloads and command syntax against the versions you actually install. Never invent an address, flag, API, screenshot, benchmark or test result. Distinguish:

- **Read:** inferred from code or documentation.
- **Traced:** observed in a recorded execution.
- **Checked:** a prediction was tested independently.
- **Hypothesis:** plausible but unverified.

Maintain a useful written handoff throughout the work. Explain what changed, why, how it was checked, and what remains uncertain. Record mistakes as reusable lessons. Keep helpers used repeatedly in `tools/`, rather than in untracked scratch scripts. Keep progress reports concise and continue the work after reporting them.

## 1. Bootstrap an empty folder

Inspect the host OS, shell, available programs, network access and applicable project instructions first. Do not assume any emulator, ROM, assembler, Python library, debugger bridge or previous port exists. Reuse an existing installation only after identifying its version and testing it; do not modify another project's installation.

Create this structure, adapting platform names as needed:

```text
README.md                    current status, build and play commands
SPEC.md                      fidelity contract, target and acceptance criteria
PLAN.md                      milestones, dependencies and exit evidence
TODO.md                      current priorities, blockers and next commands
docs/PORTING-LOG.md           chronological methods, results and wrong turns
docs/REFERENCES.md            reference and tool sources, versions, hashes
docs/SOURCE-BASELINE.md       source boot, configuration and capture procedure
docs/SOURCE-RUNTIME.md        memory, interfaces, overlays, RNG, input, timing
docs/ATARI-DESIGN.md          target memory map and service contracts
docs/VALIDATION.md            comparisons, exclusions and coverage limits
assets/original/             pristine media; never emulator working disks
references/                  downloaded manuals and extracted searchable text
source/<platform>/           labels, analysis hints, reproducible disassembly
tools/                       setup, decoding, capture, exploration, comparison
tools/traces/                replayable input scenarios
port/atari/src/              boot code and Atari runtime
tests/                       meaningful automated checks
test-artifacts/              selected evidence, with commands and manifests
build/                       ignored generated output and scratch analysis
state/                       ignored writable play disks and emulator profiles
```

Ignore build output, caches, installed tool binaries, credentials and personal saves. Track enough reference evidence and acquisition scripts to reproduce the work; decide whether game media can be redistributed before including it in Git. If media must stay local, retain its manifest and verification procedure in the repository. Initialize Git only if no repository exists, and preserve any existing work.

Use Python 3 for analysis and harnesses, and ca65/ld65 from cc65 for Atari assembly unless a measured requirement favors another tool. Start with the standard library when sufficient; pin added dependencies in an environment file. Create project-local or user-local tool installations instead of unnecessarily changing the host system. A Linux source build may need a C/C++ compiler, make, SDL development packages and other dependencies named by the selected emulator's build guide; determine actual package names from the host distribution.

### Tool and documentation starting points

These are starting URLs, not version pins. Follow current release links, read their installation instructions, and record the exact version/commit installed. Prefer a working stable build over chasing an unneeded update.

| Need | Starting point and role |
| --- | --- |
| Atari emulator | [Atari800](https://atari800.github.io/), [source](https://github.com/atari800/atari800), and its `DOC/INSTALL` and [usage guide](https://github.com/atari800/atari800/blob/master/DOC/USAGE); portable target execution |
| Independent Atari emulator | [Altirra](https://www.virtualdub.org/altirra.html); Windows releases, debugger and replacement firmware; inspect the bundled help for automation |
| Atari hardware | [Altirra Hardware Reference Manual](https://www.virtualdub.org/downloads/Altirra%20Hardware%20Reference%20Manual.pdf); supplement with scans of Atari's Technical Reference Notes, OS manual and *De Re Atari* |
| 6502 assembly tools | [cc65](https://cc65.github.io/), [source](https://github.com/cc65/cc65), [documentation](https://cc65.github.io/doc/): ca65 assembles, ld65 links, da65 disassembles |
| C64 reference emulator | [VICE](https://vice-emu.sourceforge.io/), [monitor manual](https://vice-emu.sourceforge.io/vice_12.html); `x64sc` for execution and `c1541` for independent disk extraction |
| C64 hardware references | Commodore's *Programmer's Reference Guide*, KERNAL entry documentation and VIC-II/CIA/SID references; obtain searchable copies and record their provenance |
| Apple II reference emulator | [AppleWin source/releases](https://github.com/AppleWin/AppleWin); Windows debugger and bundled help; select a documented alternative for other hosts if necessary |
| Apple II hardware references | Apple's *Apple II Reference Manual*, relevant IIe/IIc supplements, DOS 3.3/RWTS and Disk II documentation; choose the manual for the actual machine/CPU |
| NES reference emulator | [Mesen website](https://www.mesen.ca/) and the [Mesen CE repository](https://github.com/nesdev-org/MesenCE/); inspect the chosen release's debugger, trace and scripting documentation |
| NES hardware references | [NESdev](https://www.nesdev.org/wiki/Nesdev_Wiki), especially [CPU memory map](https://www.nesdev.org/wiki/CPU_memory_map), [PPU programmer reference](https://www.nesdev.org/wiki/PPU_programmer_reference), APU, controller and the cartridge's specific mapper documentation |
| Optional reverse engineering | [Ghidra](https://github.com/NationalSecurityAgency/ghidra); install the JDK required by that release, preferably isolated from the system Java |

For each needed tool: download an official release or build a pinned source revision, retain its provenance, verify the executable starts, and exercise its required capture/debugging features. Old documentation may describe a different emulator generation; match APIs to the installed release. A GUI emulator does not necessarily have a headless command mode.

Use the following acquisition sequence:

1. **Atari800:** use a host-compatible release linked from its website, or clone the source and follow [the installation guide](https://github.com/atari800/atari800/blob/master/DOC/INSTALL). On a suitable Unix host the source-build sequence is `./autogen.sh` if `configure` is absent, `./configure` with the selected frontend/options, then `make`. Run the built executable locally; global installation is unnecessary. Check `-help` and `-v`, configure firmware, and boot a tiny Atari test image before testing the game.
2. **Altirra:** download and extract a Windows release from the author's page, read its README/help, select the intended machine and firmware, and boot the same test image. On a non-Windows host, arrange a supported second-emulator environment or a documented port; do not assume Windows APIs or a debugger bridge will work natively.
3. **Source emulator:** install only what the chosen source requires. For C64, obtain VICE and verify both `x64sc` and `c1541`; for Apple II, obtain AppleWin or a host-compatible alternative with proven debugger access; for NES, obtain the current Mesen-family release and verify trace/scripting callbacks. Read any firmware requirements before interpreting a failed boot as broken game media.
4. **References:** download the target hardware manual and the source CPU/hardware/storage manuals. Preserve PDFs, generate searchable text when useful, and record page numbers with findings. Confirm extracted text against the page when diagrams, address tables or OCR are ambiguous.

Choose an automation strategy during setup. Atari800's [documented library target](https://github.com/atari800/atari800/blob/master/DOC/INSTALL) can be built with `./configure --target=libatari800` and `make`; inspect the pinned version's public headers/examples before writing a C adapter or Python binding. It does not automatically create the custom API used by an earlier project. Whether using a library, monitor or scripting API, prove frame/instruction stepping, register and bank-aware memory capture, hardware input, screenshots and disk persistence in a small harness. Distinguish CPU-visible memory from RAM hidden under ROM/I/O and from ANTIC's view.

As an example of a local assembler build on a suitable Unix host, after checking cc65's current build guide:

```sh
git clone https://github.com/cc65/cc65.git build/tool-src/cc65
# Select and record a tested tag or commit before relying on this checkout.
make -C build/tool-src/cc65 -j2
build/tool-src/cc65/bin/ca65 -V
build/tool-src/cc65/bin/ld65 -V
build/tool-src/cc65/bin/da65 -V
```

Write a repeatable setup helper that verifies or selects the recorded revision on subsequent runs. Use a local release archive on Windows if more practical. Smoke-test the toolchain by assembling a tiny binary at a known address and checking its bytes; merely finding the executable is insufficient.

Obtain source firmware required by the chosen emulator, and Atari OS firmware or an available replacement OS. Use owner-provided dumps or distributable replacements where applicable. Record names, sizes and SHA-256 hashes. Do not treat a replacement OS as proof of compatibility with Atari's original OS. Missing game media or required firmware is a concrete blocker to execution, not a reason to fabricate a baseline.

Make one explicit emulator profile per test configuration. Pin machine model, CPU, RAM, ROM hashes, PAL/NTSC, disk acceleration/traps, drive emulation, input mapping, palette and power-on initialization. Use separate settings folders so tests do not inherit a person's interactive configuration.

## 2. Choose the conversion architecture from evidence

Identify the actual execution model before writing the Atari kernel. Boot the original, trace its entry path and storage operations, inspect its headers and loaded code, and establish the CPU variant. A high density of plausible opcodes alone does not prove a blob is machine code.

| Source characteristic | Likely approach | What must be proved first |
| --- | --- | --- |
| Native NMOS 6502 with limited hardware coupling | Run original logic natively, retaining addresses where feasible; redirect hardware operands and replace service boundaries | Address conflicts, ROM/banking semantics, interrupts, indirect hardware accesses and self-modifying code |
| Bytecode or p-code game | Port the VM/interpreter and its platform services; retain bytecode and data | VM version, opcode semantics, arithmetic, memory model and native extensions |
| BASIC or another interpreted language | Adapt the program/runtime or compile/reimplement with checked semantics | Language dialect, arithmetic, arrays, string handling and timing |
| 65C02 or another related CPU | Retarget instructions and services with explicit compatibility work | Which extra instructions and CPU quirks are exercised; Atari's stock CPU cannot execute arbitrary 65C02 code |
| NES cartridge with banks/PPU/APU coupling | Retain logic where possible, but redesign hardware-facing graphics, input, audio and bank services | Mapper/submapper, PRG/CHR layout, NMI cadence, RAM mirroring, PPU side effects and banked call conventions |
| Different CPU, e.g. Z80 | Semantic translation or reimplementation validated against the original | Whether interpretation/translation meets target speed and memory limits |

Write a short architecture decision with measured risks and a small experiment for the largest risk. Do not spend weeks naming every routine before testing feasibility. Reuse reliable CPU cores or emulator interfaces when available; building a new CPU emulator is justified only by concrete requirements.

Source-specific cautions:

- **C64:** the 6510's `$0000/$0001` CPU-port banking must be accounted for on an Atari where those are RAM. Track RAM underneath ROM/I/O, VIC bank selection, color RAM's effective low nibble, raster IRQs, CIAs, KERNAL calls and drive-side code. Standard DOS directory files may contain almost none of the game's data.
- **Apple II:** reads as well as writes can operate soft switches. Track hi-res interleaving and seven pixel bits plus the artifact-color bit, keyboard latch/strobe, language-card or auxiliary banking, slot ROMs, custom RWTS and disk ordering. A IIe/IIc title can require a 65C02 or 128 KB; do not assume every Apple game is a 48 KB NMOS 6502 program.
- **NES:** parse iNES/NES 2.0 metadata and verify it against observed mapper behavior. Model CPU/PPU address spaces separately. PPU ports have latches, auto-increment and read side effects; controllers use serial shift registers; mapper writes may target addresses that otherwise read as ROM. A RAM proxy is not a universal replacement for these devices. The NES CPU does not perform decimal arithmetic; establish a safe D-flag policy when running its code on Atari. Preserve bank identity in every code/data label and capture. CHR tiles, nametables, attributes, sprite priority/collision and scrolling need an explicit Atari representation.

Retaining native logic does not mean building a general NES, C64 or Apple emulator on the Atari. Test a representative update/render/audio path early against the target's frame and memory budgets. If the game's coupling makes that approach infeasible, propose a measured alternative before committing to it. A semantic rewrite still uses the original as its reference and needs the same outcome checks.

## 3. Establish the original as the execution reference

For every archive and extracted asset, record URL or local origin, retrieval date, original member name, byte count and SHA-256 in `SOURCES.json`/`SHA256SUMS`. Keep different editions separate. Prefer media that retains the behavior you need to inspect: sector images can discard custom tracks, protection data or timing information present in G64, WOZ or flux/nibble captures. A working crack can be useful, but record its differences rather than treating it as an unmodified original.

First automate boot to a recognizable prompt or gameplay state. Use debugger commands, monitor files or Lua callbacks rather than host keystrokes and arbitrary wall-clock sleeps whenever possible. For C64, a VICE monitor command file is a useful starting point; consult the installed monitor's help for `until`, stepping, tracepoints, memory saves, screenshots, snapshots and disk attachment. For other systems, first prove the equivalent supported interface.

Capture registers, memory/bank state, visible output and media state at a known entry boundary. Starting a host reference from a recorded entry snapshot is acceptable if the skipped boot is documented; the finished Atari release still needs a genuine cold-boot test. A snapshot can contain hidden device state, so a RAM dump alone may not recreate it.

Instrument a few high-value boundaries: storage reads/writes, text output, key acceptance, frame/NMI/IRQ events, bank switches and screen publication. Log caller addresses or stack return addresses as well as parameters. These often reveal the load map faster than exhaustive static analysis. Record ordered events and distinguish stable game events from volatile emulator diagnostic lines.

Get the same scripted session to replay at least twice with identical relevant events and state. Use several activities, not just a title/menu: actual gameplay, scene/level transitions, a failure, and save/reload if supported. Add source title/demo behavior early to the inventory, even if it will be ported later.

## 4. Decode storage and map the executable

Find the narrow interface used by game logic for disk or cartridge data. Write its contract: entry addresses, parameter locations, transfer geometry, flags/registers clobbered, error statuses and post-call memory effects. On a C64 custom loader, follow both the computer and drive code; uploads, DOS command strings and track/sector execution commands are strong leads. For cartridges, map each physical bank and the logic that selects it.

Implement a decoder/extractor and compare its output with bytes captured **immediately after** the original loader returns. A later capture may show memory already overwritten by the game. Check full transfers, partial reads, offsets, boundary crossings and writes. Validate with an independent extraction tool where possible. Disk tracks are circular: a data block spanning the index must be associated with the correct preceding sector header.

Track writes in a working-media model. A read after saving or rebooting must use the modified media, not the pristine archive. Document physical and logical save formats separately. An ATR can have a different outer layout while preserving the game's logical save records byte for byte.

Build a load/bank inventory containing physical asset identity, load address, length, entry points, lifetime, callers and overlapping address ranges. Trace overlays under their own identities: the same CPU address can mean different code in different scenes.

Disassemble from proven entry points and follow control flow. Add jump tables, indirect dispatch and self-modifying operand patterns deliberately. Keep data as data. Reassemble extracted modules and compare every byte with the unmodified original; reapply container headers, compression/encryption or drive scrambling at the appropriate stage. A byte-identical rebuild proves preservation of bytes, while trace/control-flow checks are still needed to validate the code/data interpretation.

Ghidra is optional. For raw imports, set processor, origin, file offset **and payload length**. Do not merge overlays or mapper banks just because they share an address. Decompiled pseudocode is a reading aid; assembly and recorded execution decide behavior.

Create a machine-dependency inventory covering direct, indexed and indirect accesses, reads/writes, ROM calls, vectors, IRQ/NMI behavior, timers, graphics memory, input and audio. Search every known executable asset for interface callers, then compare static findings with dynamic coverage. Include a known positive in every search so that an empty result has meaning. A list of immediate hardware operands does not cover pointers, mirrored registers or computed addresses.

## 5. Make a deterministic reference and shared scenario language

A **host oracle** means a fast reference runner on the development computer that executes original game code/bytecode with the platform services it needs. It is a testing aid, not the Atari release. Use an existing emulator automation API as the oracle if writing a separate runner would duplicate a complex NES PPU/mapper or other hardware model. A minimal host machine is valuable only after it agrees with the source emulator.

Implement required CPU semantics, flags, interrupts, banking and device side effects. Do not inherit a CPU core's omissions unnoticed: decimal mode, unofficial opcodes, interrupt behavior and cycle accounting may matter. Fail clearly on unsupported operations. Traps for storage or other services must reproduce return flags, registers, scratch bytes and status, not merely copy a payload.

Identify RNG state, seeding and all timing-dependent inputs. For a turn-based game, delivering each key at the **first eligible input poll** can make replay repeatable; in the earlier C64 port, wait-loop counters fed the RNG. For an action game, use frame-indexed controller states with press/release duration, including lag-frame behavior. Do not freeze frame updates or change movement rules to obtain determinism.

Define one shared scenario format for the source emulator, oracle and Atari harness. Implement commands only when their semantics are established. For example:

```text
# Conceptual format to implement; these are not existing emulator commands.
ready                        # stop at an identified ordinary input boundary
press RETURN                 # deliver at the first eligible poll
mark options                 # capture state/events at that boundary
attach B                     # switch the working source medium, if applicable
hold CTRL+A 120               # hold for 120 emulated frames
release                      # release input and check pending repeats
poll area-reader Y            # target a separately identified direct reader
pause_key SPACE              # deliver to an interruptible delay's own poll
assert character.status DEAD # verify semantics, not just matching memory
save                         # invoke the game's actual save flow
restart                      # new machine, same modified working media
mark reloaded
```

Give every wait an instruction/frame budget and useful timeout diagnostics: PC, bank, stack, current input boundary, last events and clock/target values. Keep exploration and replay on the same engine. Playing a script in two segments must produce the same state as playing it whole; one extra input-wait iteration can change the dice.

Compare oracle versus source execution on event order, game memory, logical media writes and screen reconstruction. Explain the first divergence before continuing. A host screen renderer can be checked pixel for pixel against source screenshots after normalizing palette indices, crop and frame boundary. That checks the source renderer; the Atari's adapted colors need their own acceptance rules.

Capture screenshots without altering the scenario's RNG inputs. Waiting for a completed video frame can advance input counters. Preserve and restore the exact defined wait state only where that is legitimate and documented, or record the delayed capture as a distinct scenario. Resetting counters to zero may make oracle and emulator agree on an entirely different fight. Assert the intended outcomes in both the plain and screenshot versions.

## 6. Design the Atari memory map and a display experiment

Before implementation, budget every occupied interval and bank: original logic, overlays, zero page, stack, ROM-hidden RAM, hardware I/O, vectors, boot/runtime code, display lists, frame buffers, fonts, palettes, caches, audio state, disk buffers and test instrumentation. Record lifetimes and ownership, not just sizes. Unused-looking padding is not free until reads/writes and future loads have been considered.

Atari XL/XE hardware I/O occupies `$D000–$D7FF`; switching out OS ROM does not turn it into ordinary RAM. OS ROM covers `$C000–$CFFF` and `$D800–$FFFF`; BASIC covers `$A000–$BFFF`. On a stock 130XE, the extended 16 KB window is `$4000–$7FFF`, controlled through PIA PORTB. Verify CPU/ANTIC access behavior from the hardware manual and a small test. Do not assume stock XE banking permits the CPU and ANTIC to select two different extended banks simultaneously.

If preserving source addresses, resolve overlaps explicitly. An address that is an I/O register on the source can be executable Atari RAM: an overlooked store to a C64 CIA register once replaced an Atari kernel opcode. Conversely, source RAM can fall in Atari's hardware hole. Inventory both directions of conflict.

Prove the proposed display with a standalone program using a real source-screen capture. Test row addressing, character-set alignment, display-list boundaries, player/missile data if used, color registers, display-list interrupts (DLIs), vertical blank interrupts (VBIs) and pixel aspect ratio. Pick a mode from source data characteristics rather than screenshots alone. ANTIC character modes can sometimes display source cell-ordered bitmap data economically by using different character sets per row; this is a candidate to measure, not a general solution.

Document visual compromises. C64 colors per cell, Apple artifact colors and NES background/sprite palettes do not map directly to Atari row/global registers. Choose colors from **visible pixels**, not stale color bytes attached to blank cells. Weight actual pixel use where appropriate, preserve deterministic tie order, and include backgrounds, borders, highlights and command-panel regions. Extra DLI colors cost timing and complexity.

Choose a safe frame publication policy. The game may reuse text memory as bitmap colors before changing its mode flag. Display completed snapshots or retain a completed frame until conversion finishes; otherwise live ANTIC reads can turn color bytes into text garbage. Check both transition directions and within-mode redraws. A correct final picture does not prove the intermediate frames are correct.

## 7. Implement platform services, preserving their contracts

Write the smallest useful Atari runtime and boot path. Keep the game's logical state distinct from target hardware state. For simple source registers, redirect proven operands to a proxy register file in RAM and let the original sequencer/logic continue to run. Build patches must assert expected original opcodes/operands, record each changed byte and reject unknown source hashes. Side-effectful I/O requires a real service implementation, not passive proxy bytes.

Reproduce service entry/return behavior, including flags and interrupt stack conventions. A debugger test that calls a routine must preserve all needed CPU state before resuming the game; changing Z just before a BEQ can create a phantom keypress. Keep runtime scratch out of game-owned zero page unless proven safe. Control NMI/IRQ ordering and save/restore banking around interrupt handlers.

For OS-assisted disk access with the OS normally switched out, define ownership handover: game versus OS zero page, vectors, bank registers, interrupt masks, DMA/display state, POKEY and buffers. Restore it on successful and failed transfers. Batch transfers under one handover when safe. Test accelerated emulator disk access **and standard emulated serial SIO**; accelerated paths can hide restoration and timing bugs.

POKEY is shared by sound, keyboard scanning and serial I/O. Reinitialize its relevant control registers after SIO, invalidate stale audio caches, and confirm both keyboard and sound resume. Avoid resetting unrelated game sequencer state as a shortcut.

Translate input semantics, including modifiers, alternate key codes, press/release, held-key delay/rate, all-key repeat flags, joystick directions and simultaneous buttons. Direct polling, menus, gameplay and interruptible pauses may use different readers. Arm a special input hook before releasing its triggering action; fast code can pass the desired poll before the harness notices. Injected deterministic keys validate logic; separately test the production keyboard/controller path through the emulated hardware.

Handle game time and real time explicitly. If a source delay waits for exact clock equality, a slow conversion can skip the target and stall until wraparound. Trace its clock ownership and loop before choosing a fix. Suspending an emulated source clock during presentation work fixed that case, while input/audio continued; it is not appropriate for every real-time game. Verify pause duration, key interruption, wraparound and sound cadence after any clock change.

Translate sound from actual source register-write traces or music data. Check effects, music, gate/envelope behavior, muting, sound-off and key interruptions. POKEY timbres may be approximations; document them. Register values show intent, while PCM recordings and measured pitch/duration show that audible output actually occurs. Validate audio and input after a disk operation. Include title music and demos in the eventual scope.

## 8. Validate the game and the Atari runtime independently

At each scenario checkpoint, compare relevant game state and ordered events with the established reference. If retaining addresses, compare broad memory ranges. If translating or relocating, define a semantic state export: positions, inventory, flags, actors, RNG, timers and save records, with an explicit source-to-target mapping.

Every comparison exclusion needs an address/range, the instruction or service responsible, a reason and a separate check where appropriate. Different machine vectors, stale stack bytes and hardware-owned state may be legitimate; broad exclusions for unexplained differences are not. Do not widen exclusions to make a failure disappear.

The Atari runtime is not present in the source, so equality of game memory cannot validate it. Independently check immutable runtime code/tables, vectors, bank state, stack bounds, active display list, screen buffer ownership and service restoration. List intentional self-modifying operands and volatile state explicitly. Use write watchpoints and canaries where useful. Protect extended-bank code as well as main-memory code when it can be reached or overwritten.

Add semantic outcome assertions. Two machines can agree on the same wrong scenario. In the earlier port, `$40` meant unconsciousness, whereas `$C0` meant actual death; a supposed resurrection test was merely healing until the branch was checked. Find status definitions, cross-check visible output and consequences, and require a negative control that rejects the near miss.

Use fixtures sparingly to reach rare branches: record each position, health, equipment or seed change, why it is needed and which coverage claim it does **not** support. A teleported rare-area test validates that area's code, not natural travel to it. Keep natural gameplay sessions alongside focused fixtures. Invoke actual game logic after setup; do not replace the event being tested with a patch.

For relevant games, cover:

- Cold boot, title/demo, start/exit keys, menus, options and character setup.
- Movement, turns, boundaries, scrolling, stairs, levels, overlays and bank changes.
- NPC/services, purchases, spells, items and inventory/equipment operations.
- Encounter alternatives, combat commands, victory, escape, defeat and rewards.
- Trap success/failure, status effects, actual death, restoration and game-over recovery.
- Saves, writes near sector boundaries, reload after a new emulator process, and continued play.
- Ordinary and held input, release behavior, modifiers, direct readers and keys during delays.
- For action games: collision edges, sprite priority, damage, moving platforms, boss phases and missed/late frames.
- Sound/music and display transitions around disk access and mode changes.

Do not claim whole-game coverage because a boot or first combat works. Maintain a matrix of exercised branches, assets/areas and known gaps. Derive route/world graphs from data where possible; they make exploration systematic.

Run early on Atari800 and an independent emulator such as Altirra. The earlier work used a separately installed AltirraSDL bridge; a stock download does not automatically provide that bridge or its Python API. Select and document an available automation interface, or perform explicit manual checks and report that limitation.

Discover where each emulator really persists disk writes. Some configurations use private working copies keyed by image hash rather than changing the attached file. Identify the effective written media before comparing saves or restarting. Isolate profiles and clear stale writable copies deliberately. Initialize test-hook flags explicitly; randomized power-on RAM can otherwise look like a completed test.

Include DMA-off tests with standard SIO. ANTIC can repeat a display-list instruction while DMA is off; if that instruction requests a DLI, interrupts may keep occurring and collide with VBI or OS activity. A title-stage hang was visible in Altirra with serial transfers but absent in Atari800. Follow the hardware's behavior rather than labeling a discrepancy an emulator bug without evidence.

## 9. Measure and optimize after the playable slice

Capture a clean baseline and compare identical scenarios. Measure original and Atari action latency in emulated frames/cycles and milliseconds, stating PAL/NTSC, ROM, disk mode and boundaries. Warp mode speeds up the host; its wall time is not player latency. Never compare an accelerated Atari load with a true-drive source load without labeling both.

Separate game simulation/drawing from target conversion, palette selection, buffer copying, interrupts, DMA contention and storage. Instruction-cycle sums exclude stolen DMA cycles and possibly interrupt work; native elapsed time includes them. Attribution by PC alone can miss an IRQ that interrupts banked conversion. Verify profiling hooks against an uninstrumented control and preserve output hashes/images.

Useful measured optimization candidates:

- Skip redundant writes to self-modifying lookup operands when the selected table page is unchanged; update every operand in unrolled loops together.
- Use a direct copy for identity mappings and unroll loops only when saved cycles justify code size.
- Reuse exact palette/mapping keys. Preserve tie order and invalidate on layout/mode changes.
- Skip unchanged rows only when exact input/mapping conditions prove unchanged output. A lossy checksum or matching histogram is insufficient. Reusing already-converted bytes requires checking transform idempotence; a pair-swap mapping is a useful negative control.
- Count only drawn pixel colors; blank cells can carry stale metadata that distorts selection.
- Derive address tables from proven relationships instead of storing duplicates.
- Reduce stack traffic with registers or safe rereads, after checking IRQ ownership of the input.
- Batch OS entry/exit for multiple sectors, respecting buffer lifetimes and error recovery.
- Recreate proven zero-filled startup ranges rather than reading them, with build assertions that they really are zero. Do not discard title leftovers without read-before-overwrite evidence.

Use frozen real refresh snapshots and an independent unoptimized converter for differential checks. Add adversarial mapping, cache invalidation, changed pixels with unchanged colors, layout switches and cold-cache cases. Do not compare two paths sharing the same bug and call it independent validation.

Fit costs before coding: tables, extra unrolled operands, state and padding can consume apparent gains. Build assertions must reject overlaps and exhausted segments. Keep a ledger of remaining bytes by segment/bank, and note possible savings for a later 64 KB target without weakening the selected build.

Report measured gains separately from estimates. A converter saving 2.3% of instruction cycles once improved an action by one whole frame because publication is quantized. Conversely, a faster loop might not improve the frame count at all. Do not claim additive gains from overlapping prototypes. Keep the normal playable build restored after diagnostic skip-render/blanking experiments.

## 10. Milestones and exit evidence

Use this order as the starting plan. Adapt dependencies to the source and record why. Close a milestone only when its exit evidence exists; incomplete side investigations should remain listed instead of blocking useful progress indefinitely.

| Milestone | Deliverable | Exit evidence |
| --- | --- | --- |
| M0: brief and environment | SPEC, tool/reference manifests, setup helper and project structure | Required tools exercised; missing media/firmware named; target and fidelity assumptions explicit |
| M1: source baseline | Verified original, emulator profile and automated boot/gameplay capture | Repeatable source runs with matching state/events and preserved originals |
| M2: storage and execution map | Proven decoder/extractor, load/bank map, service contracts | Captured transfers match; writes/readback verified; critical executable modules rebuild exactly |
| M3: deterministic reference | Shared scenarios and oracle or source-emulator adapter | Reference agrees with source execution; timing/RNG rules and exclusions explained; split replay agrees |
| M4: Atari feasibility | Memory budget, architecture decision and display/boot experiments | Riskiest banking/display assumption tested; small native program boots in both target emulators |
| M5: playable slice | Genuine game flow through representative input, graphics and storage | State/events match; native controls work; representative save survives a cold restart |
| M6: presentation and services | Stable transitions, title, sound/music and complete input semantics | Actual frame/audio evidence; held/released inputs; standard SIO restoration; documented compromises |
| M7: breadth | Coverage matrix and scripts for varied branches/levels, success and failure | Intended outcomes asserted; game and runtime integrity pass; natural routes distinguished from fixtures |
| M8: performance | Native profile, measured optimizations and memory ledger | Before/after fidelity retained; second-emulator confirmation; action/load latency and limits stated |
| M9: compatibility and release | Reproducible normal image, build/play instructions and final handoff | Clean build from documented dependencies; tests rerun; release hash; compatibility claims limited to configurations actually checked |

Do not require a full oracle before the first Atari display experiment if the experiment is independent. For a frame-driven game, timing/input/display integration may need to happen earlier than in a turn-based RPG. Keep the principle: establish a trustworthy reference, test the largest risks, then widen the playable result.

## 11. Debugging recipes and lessons that saved time

**When runs diverge:** stop at the first differing checkpoint, bisect the scenario, locate the first differing event or state byte, then trace its writer and upstream inputs. Check key timing, RNG, overlays, loader return flags and modified disk state. A matching transcript alone can hide divergent dice until a later event.

**When graphics corrupt:** inspect the actual ANTIC display list, bank and bytes it is reading. Compare immutable runtime code to the assembled image. Use a write watchpoint on the first changed opcode. If unrelated code movement changes the symptom, investigate an overwrite or timing race before blaming an emulator. Separate persistent corruption from transition artifacts.

**When a wait hangs:** print PC/bank/stack and identify whether it is an ordinary input wait, direct poll, disk prompt, timer equality loop or interrupt failure. Inspect the live clock and target, elapsed presentation time, interrupt enable state and device ownership. A generic extra sleep cannot fix a missed semantic boundary.

**When a save seems unchanged:** inspect effective emulator working media, not just the mounted filename. Compare logical written records, restart using the written copy in a new process, then play far enough to prove the state was consumed. A warm reset may preserve RAM and hide a broken loader.

**When a test passes too easily:** add a known positive and a deliberate negative. A search must find a known caller, a cache test must force both hits and misses, and a death test must reject unconsciousness. Ensure the harness is reaching the real branch rather than manipulating its final state.

**When the screenshot looks old:** distinguish emulator's last completed frame from current game memory and target buffer publication. Wait at a documented capture boundary while preserving scenario timing. Also inspect intermediate frames; a later settled image can hide seconds of wrong text.

**When a user reports a bug you cannot reproduce:** identify their exact image hash, machine/ROM/TV settings, emulator version and controls. Reproduce through ordinary input and capture transitions. Keep the report and tested scope; do not invent a fix for a stale disk or conclude that failure to reproduce proves correctness.

**When adding instrumentation:** reserve its bytes in the memory map, keep it out of the release image, preserve CPU state and confirm control runs match. A trampoline sharing a disk buffer is safe only if their lifetimes demonstrably do not overlap. Never assume zero-filled power-on RAM.

**When handing off:** read the current TODO, design, log and test evidence, verify source/tool hashes, run the checks relevant to the next change, and continue from the existing milestone. Do not restart the investigation merely because a new LLM session has no prior conversation.

## 12. Records, release instructions and completion

Before each work commit, append a `docs/PORTING-LOG.md` entry with goal, method/commands, results, evidence paths, failed attempts, memory/timing costs, open limits and lessons useful for another port. Keep history append-only; correct a previous claim in a later entry. Keep current findings documents accurate instead of relying on an old log status paragraph.

For commit references, use a provisional log reference and a small later bookkeeping commit if needed; a commit cannot contain its own final hash. Keep this policy simple and honor the owner's Git instructions. Never guess a remote or expose credentials. A request to create a prompt or inspect a port does not itself authorize publication.

Every evidence folder needs a short README describing image/media hashes, emulator configuration, command/scenario, expected assertions and limitations. Retain useful raw captures, not every scratch run. Inspect every screenshot you present. Use a contact sheet or animation for many transitions, then inspect suspicious individual frames. A generated gallery is not reviewed just because its script succeeded.

For a documentation-only change, check the document and commands rather than rerunning unrelated gameplay tests. For changes to runtime, patches, storage, timing or rendering, run affected checks and the established regression suite required for release. Report passed, failed and skipped tests separately. An unavailable second emulator is an untested configuration, not a pass.

Provide exact build and launch commands for the installed tool versions. For a 130XE NTSC ATR build, current Atari800 syntax starts with the following pattern, to be verified against the chosen version's help and firmware profile:

```sh
atari800 -xe -ntsc -nobasic build/atari/game.atr
```

On Windows PowerShell, if the executable is in the current directory:

```powershell
.\atari800.exe -xe -ntsc -nobasic .\build\atari\game.atr
```

For the standard SIO check, inspect support for `-nopatch`/`-nopatchall` and document the exact chosen option. For Altirra, provide the tested machine, RAM, firmware, TV and acceleration settings even if launch is through its GUI. Play on a writable copy when saves modify the disk. Describe title/start keys, keyboard/joystick mapping, save location and reset behavior.

Test the normal release artifact, including title/boot stages. Test-mode builds or title-free harness starts must say so explicitly and must not replace the image the owner plays. Give the final file path, size and SHA-256 so copies on another machine can be identified. Rebuild deterministically where possible; state unavoidable build variance.

Completion requires a playable artifact and evidence against the agreed specification. State unresolved visual/audio differences, remaining branches, PAL/ROM/hardware configurations not exercised, and performance limits. If full completion is blocked, leave reproducible partial output and the next concrete commands; do not relabel a first playable slice as a finished port.

## Start now

Inspect the folder and host, resolve only essential missing brief fields, create the project records, and begin M0/M1. Report what you actually find and do, then continue milestone by milestone. The objective is a working, reproducible Atari port whose behavior is supported by evidence.
