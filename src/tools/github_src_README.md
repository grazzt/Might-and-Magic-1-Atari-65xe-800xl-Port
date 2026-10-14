# Source of the Atari 130XE port of Might and Magic I

This folder is the working tree of the port, minus the game. It is a **fan project**, not affiliated with or endorsed by New World Computing or the present owners of *Might and Magic*, whose property the game is (see the README one folder up). Nothing here is the game: no original disk image, manual, memory dump or listing of the game's code is included. What is here is the port's own code, its tools, its tests and the notes written along the way.

It is a research project's tree rather than a polished package: it was written to get the port working and checked, on one Linux machine. **To rebuild the disks you need your own copy of the original game** (see "Building"). The four finished disk images are in the folder above.

## What the port is

The C64 game's own 6502 code runs on the Atari, unchanged except for the operands of the few instructions that address the C64's video, sound and timer chips. An Atari kernel supplies the rest of the C64: the screen (the game's two C64-format bitmaps are turned into ANTIC graphics with per-row palettes), the keyboard, sound (translated to POKEY), the clock and the disk (the game's block reads and writes served from four small Atari disks). Everything is checked against a host-side model of the C64 game, the **oracle**, key by key, in two Atari emulators.

Where to start reading:

| Document | About |
| --- | --- |
| [docs/DISKS.md](docs/DISKS.md) | The four 130 KB disks: the format, the unpacker, the checks, what is not known |
| [docs/ATARI-DESIGN.md](docs/ATARI-DESIGN.md) | The design: memory map, display, what runs and how it is checked |
| [docs/PORTING-LOG.md](docs/PORTING-LOG.md) | Everything that was done, in order, with the wrong turns |
| [REALHARDWARE.md](REALHARDWARE.md) | The study that led to the four-disk layout, and the questions about a real 1050 |
| [docs/64K-NOTES.md](docs/64K-NOTES.md) | What it would take to run on a 64 KB machine (not done; probably not viable as designed) |
| [docs/ORACLE.md](docs/ORACLE.md) | The host oracle and how the sessions are compared |
| [docs/C64-LOADER.md](docs/C64-LOADER.md), [C64-CODE.md](docs/C64-CODE.md), [C64-RUNTIME.md](docs/C64-RUNTIME.md) | What was learned about the C64 game |
| [docs/GRAPHICS-PERFORMANCE.md](docs/GRAPHICS-PERFORMANCE.md), [SOUND.md](docs/SOUND.md), [TITLE.md](docs/TITLE.md) | Screen conversion, sound, the title stage |
| [PROJECT-README.md](PROJECT-README.md) | The project's own README, as it was in the working tree |

## What is in the tree

| Path | What |
| --- | --- |
| `port/atari/src/kernel.s` | The Atari kernel: disk loader and ZX02 unpacker, interrupts, keyboard, sound, the screen conversion and colour choice |
| `port/atari/src/boot.s`, `title.s` | The boot code (loads the game from disk 1), and the stage that runs the C64's own title program |
| `port/atari/build.py` | Builds the Atari disk images: `--disks` for the four 130 KB disks, otherwise one big image |
| `port/atari/disks.py` | The four-disk layout: items, ZX02 compression, index, ATR files |
| `port/atari/lockstep.py` | Plays a recorded key script on the oracle and on the Atari (Atari800 or AltirraSDL) and compares memory at every mark; `--disks` changes the disk as a player does |
| `port/atari/*_check.py`, `survey/`, `gfx_probes/` | Checks, measurements and one-off investigations (colour, sound, keyboard, speed, graphics, disk reads) |
| `port/atari/demo_video.py` | Records the demo video from the recorded sessions |
| `tools/oracle.py`, `mos6502.py` | The oracle: the game's code on a host 6502 core, with the KERNAL ROM and a model of the disk |
| `tools/d64.py`, `g64.py`, `mmdisk.py`, `analyze_c64.py`, `area.py`, `disassemble.py` | Reading the original disks, the file tables and areas, and tracing the game's code |
| `tools/c64_trace.py`, `c64.py` | Recording the original C64 in VICE |
| `tools/traces/*.txt` | The recorded key sessions (menu, characters, shops, fights, spells, chests, outdoors, ...) |
| `tools/zx02/` | The ZX02 compressor, vendored (see below) |
| `tests/` | Unit tests for all of the above |
| `docs/` | The design notes, findings and log (the generated `c64-*.json` files are left out) |
| `source/c64/` | Annotations for the disassembly of the game (`da65` info files and hints), not the code |
| `SPEC.md`, `PLAN.md`, `TODO.md`, `FIX.md`, `PROMPT.md` | The specification, plan, to-do list, a bug investigation, and a reusable prompt for porting other 8-bit games to the Atari |

`tools/export_github_src.py` made this folder from the working tree.

## Left out, and why

- `c64/`: the original disk images and manuals.
- `build/`, `state/`, `test-artifacts/`: everything generated from the original game, including recordings and pictures of the C64 version.
- `docs/c64-logical-disk.json`, `c64-areas.json`, `c64-code-map.json`, `c64-disk-layout.json`, and `source/c64/boot.s`: generated from, or part of, the original game. `tools/mmdisk.py`, `area.py` and `disassemble.py` make the first four from your own copy.

So the tests and tools that read the game do not run from a bare checkout. A few do: `python3 -m unittest tests.test_mos6502 tests.test_code6502 tests.test_disks.Format`.

## Building

You need:

- **Your own copy of the original game**: the *Original_v2* four-side set, as `.g64` images in `c64/images/` (see `tools/c64.py` for the names it looks for).
- **Python 3** (numpy and Pillow for the video), a **C compiler** (for ZX02).
- **cc65** (`ca65`, `ld65`) for the kernel.
- **VICE** (`x64sc`, with its C64 ROMs) to capture the C64 state the oracle starts from (`tools/traces/capture-entry.txt`) and to re-record sessions.
- **libatari800** (Atari800 built as a shared library) and its Python harness (`port/atari/harness.py`, from the author's Wizardry port, **not included here**), and optionally **AltirraSDL**, to run the Atari side. The tools look for all of this under the folder named by the environment variable `WIZARDRY_ROOT` (default `../wizardry_1`): `tools/toolchain/local/bin/`, `tools/emulators/local/`, and `port/atari/harness.py`. Adapting `shared_root()` in `tools/c64.py` is the place to point them elsewhere.

Then, roughly (see [docs/C64-LOADER.md](docs/C64-LOADER.md) and [docs/ORACLE.md](docs/ORACLE.md) for the details):

```bash
python3 tools/analyze_c64.py            # decode the disks (build/c64/)
python3 tools/mmdisk.py                 # logical sides and docs/c64-logical-disk.json
# capture the oracle's start state with VICE into test-artifacts/c64/oracle-start/
#   (tools/traces/capture-entry.txt, docs/ORACLE.md "Start state")
python3 port/atari/build.py --disks     # build/atari/disks/mm1-disk1.atr ... mm1-disk4.atr
python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt --disks   # check against the oracle
python3 port/atari/disks_check.py       # the disk prompts, as a player sees them
python3 -m unittest discover -s tests   # everything
python3 tools/area.py --world           # optional: docs/c64-areas.json
python3 tools/disassemble.py --rebuild  # optional: docs/c64-code-map.json (needs da65 from cc65)
```

Built this way from a clean export of this folder (the original images and the oracle's start state supplied), the four disks came out **byte for byte the same** as the ones in the folder above.

## Third-party code

- **ZX02** compressor, `tools/zx02/`, vendored unchanged from <https://github.com/dmsc/zx02> by **Daniel Serpell** (MIT licence, `tools/zx02/LICENSE`), derived from **ZX0** by **Einar Saukas** (BSD-style, `tools/zx02/LICENSE.zx0`).
- The 6502 **unpacker** in `port/atari/src/kernel.s` is Daniel Serpell's `zx02-optim` (MIT), adapted to read from a sector buffer and stop at a given length.

## Licence of the port's own code

No licence has been chosen yet. Until one is added, treat the port's own code and notes as shared for reading and learning. The game itself remains the property of its owners.
