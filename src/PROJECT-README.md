# Might and Magic I → Atari 8-bit

A separate **64 KB / 65XE prototype** is available on `65xe`: build with
`python3 port/atari/build.py --65xe` or add `--disks` for four 1050-sized
images. It now includes the original animated title, intro scenes and POKEY
intro music. Gameplay uses grayscale (or `--colour` for a warm palette);
in-game POKEY effects remain omitted.
[Memory design, validation and remaining work](docs/65XE.md).

A port project for *Might and Magic Book One: Secret of the Inner Sanctum* to the Atari 8-bit computers, using the **C64 version** as its source.

**Status (2026-10-12): playable on an emulated Atari 130XE, in colour with sound and the original title sequence.** Game state matches the C64 reference across 21 scripts / 257 checkpoints, and saves match byte for byte. The original 6502 code runs through an Atari hardware kernel, with only hardware operands redirected. [Screenshots](docs/SCREENSHOTS.md), [design](docs/ATARI-DESIGN.md), [specification](SPEC.md), [plan](PLAN.md).

**Since 2026-10-12 the disk starts as the C64's does:** the original title program runs first, with its two frames, its tune and its eight scenes, and Escape starts the game ([how, and beside the C64](docs/TITLE.md)). Sound has worked since 2026-10-11 ([effects](docs/SOUND.md)).

**How it was done:** [docs/PORTING-LOG.md](docs/PORTING-LOG.md) is the step-by-step record of the work, with the method, the recipes and the mistakes, kept so that another game can be converted the same way. Every piece of work adds an entry there before it is committed.

**For another game:** [PROMPT.md](PROMPT.md) is a self-contained prompt for an LLM starting an Atari port in an empty folder, including tool setup, source-platform differences, milestones, validation and lessons from this project.

[POR.md](POR.md) specializes that prompt for SSI's C64 NTSC *Pool of Radiance* on a stock 64 KB Atari 65XE, including memory feasibility, tactical-combat coverage and source-specific references.

[PORTING.md](PORTING.md) is the version for this machine's supplied toolkit.
Extract [porting.tgz](porting.tgz) into a new project folder: it contains that
prompt plus reusable tools, prior tool sources and ten reference PDFs with
searchable text/HTML and provenance under `tools/`. The wrappers reuse existing
compiler/emulator installations here. Rebuild the archive with
`python3 tools/package_porting.py`; see [the kit guide](tools/porting-kit/README.md).

The approach follows the Wizardry I port in `~/coding/wizardry_1`, which runs the original Apple game code on an Atari 65XE and is checked key by key against a host reference. Might and Magic I appears to be native 6502 machine code rather than Pascal p-code, so this port retargets the original 6502 code instead of writing an interpreter. The verification method (host oracle plus lockstep comparison in Atari800) carries over unchanged.

From this directory:

```bash
python3 tools/verify_sources.py
python3 tools/analyze_c64.py
python3 tools/rebuild_boot.py
python3 tools/rebuild_loader.py
python3 tools/mmdisk.py
python3 tools/area.py --world
python3 tools/disassemble.py --rebuild
python3 tools/oracle.py tools/traces/boot-to-fight-and-save.txt --compare test-artifacts/c64/trace-fight-save
python3 port/atari/build.py
python3 port/atari/build.py --disks   # four 130 KB disk images for a real 1050: docs/DISKS.md
python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt
python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt --disks
python3 port/atari/play_check.py
python3 port/atari/title_check.py
python3 port/atari/screenshots.py
python3 -m unittest discover -s tests -v
python3 tools/c64_smoke.py
python3 tools/c64_trace.py tools/traces/boot-to-fight-and-save.txt
```

`tools/traces/` holds four more scripts run the same way, and `snapshot-town.txt`, which saves a VICE snapshot for quick experiments:

```bash
python3 tools/c64_trace.py tools/traces/snapshot-town.txt
python3 tools/c64_explore.py look build/trace/snapshot-town/town.vsf B 'IIJII|Y|'
```

`c64_explore.py` resumes the snapshot, presses the keys and prints the disk commands, text and keys in order; a run takes under a second. `oracle_explore.py` does the same on the host oracle, from any mark of any script and without a snapshot:

```bash
python3 tools/oracle_explore.py tools/traces/boot-to-fight-and-save.txt dungeon 'LIIIIIJI|A|' --screen
```

`c64_smoke.py` boots a fresh copy headlessly and checks the options menu in screen RAM. It writes screenshots, RAM captures, and logs to [test-artifacts/c64/baseline](test-artifacts/c64/baseline). `c64_trace.py` plays a key script, logs every disk-loader call and everything the game prints, and checks each read and write against the decoded disk; it writes to `build/trace/` unless given `--output`. Its `press` step hands the game each key on its first poll, which makes a run repeatable. It still drives VICE; it is not the host oracle.

For interactive play, run `python3 tools/c64.py` in a desktop terminal. It preserves writable disks in `state/c64/disks/`; attach side B from that directory when prompted. The C64 left-arrow key is the game's Escape. The automated check covers the A-to-B swap only.

Both commands reuse the sibling `../wizardry_1` installation without modifying it; set `WIZARDRY_ROOT` if it is elsewhere. See [shared references](docs/REFERENCES.md) for prerequisites.

**Ghidra is now available:** Ghidra 12.1.4 and a dedicated JDK 21 are installed under `~/tools`. Run `ghidra` for the desktop application or `ghidra-headless` for scripted analysis. Its 6502 importer and native decompiler have been checked against our bootstrap. See [Ghidra setup and C64 workflow](docs/GHIDRA.md) for paths, exact import settings, and the repeatable check. VICE remains the execution reference; ca65 rebuilds remain the byte-identity check.

Layout, mirroring the Wizardry project:

| Path | Contents |
| --- | --- |
| `c64/images/`, `c64/manuals/` | Archived downloads and extracted references with `SOURCES.json` and `SHA256SUMS` |
| `source/c64/` | Bootstrap source and da65 info files for the loader and drive code |
| `source/c64/game/` | Hand-kept `hints.txt` and `symbols.txt`; generated da65 info files for the 76 code files in `info/` |
| `tools/` | Source verification, sector/G64/logical-disk decoding, area files and routes, VICE launcher, smoke check, session trace, snapshot explorer, static tracer, whole-game disassembly and rebuilds, 6502 core and host oracle |
| `docs/` | The porting log; baseline, loader, runtime and code findings; disk-layout, logical-disk, area and code-map reports; shared reference pins |
| `build/`, `state/` | Ignored generated analysis and writable emulator disks |
| `port/atari/` | Atari side: the kernel and boot code (`src/kernel.s`, `src/boot.s`), `build.py` (disk image), `lockstep.py` (comparison with the oracle in Atari800), `play_check.py` (a short game through the emulated keyboard), `screenshots.py` (the gallery), `altirra.py` and `altirra_check.py` (the same and a save in a second emulator, AltirraSDL) and the display experiment (`display_demo.py`) |

**2026-10-12 follow-up:** twelve more gameplay sessions cover direct area input, combat spells/shooting/items/exchange, encounter choices, traps, death/resurrection and wilderness travel. They found and fixed a pause-clock stall. Walking/turns now take 29 NTSC frames. [Coverage and fixture scope](docs/GAMEPLAY-COVERAGE.md), [walking measurements](docs/WALKING-PERFORMANCE.md).
