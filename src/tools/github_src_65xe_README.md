# Source of the Atari 65XE (64 KB) port of Might and Magic I

This folder is the working tree of the port, minus the game, as it stands on the `65xe` branch. It is a **fan project**, not affiliated with or endorsed by New World Computing or the present owners of *Might and Magic*, whose property the game is (see the README one folder up). Nothing here is the game: no original disk image, manual, memory dump or listing of the game's code is included. What is here is the port's own code, its tools, its tests and the notes written along the way.

It is a research project's tree rather than a polished package: it was written to get the port working and checked, on one Linux machine. **To rebuild the disks you need your own copy of the original game** (see "Building"). The finished disk images are in the folder above.

The tree builds **two profiles from one code base**: the 130 KB-disk **130XE** build (128 KB machine; extended bank, per-row palettes) and the **65XE** build described here (stock 64 KB, direct ANTIC display). The 65XE disks are made with `--65xe`.

## What the 65XE profile is

The C64 game's own 6502 code runs on the Atari, unchanged except for the operands of the few instructions that address the C64's video, sound and timer chips. On the 130XE an extra 16 KB bank holds a converted copy of the screen and its colour tables. A stock 64 KB machine has no such bank, so the 65XE profile **shows the game's own two C64-format bitmaps directly** in ANTIC mode 4 and changes the character-set base per row from a display-list interrupt: nineteen of the 25 bitmap rows display where the game drew them, and the six rows that cross a 1 KB character-set boundary are copied into two shared blocks. The price is colour: a fixed four-colour palette (grey, or a warm one with `--colour`), not the C64's colour per cell. Text, geometry, menus, page flipping, the game's rules, random numbers, disk traffic and saves are the original's. The original title program runs first, with its tune translated to POKEY.

Where to start reading:

| Document | About |
| --- | --- |
| [docs/65XE.md](docs/65XE.md) | The 65XE profile: memory allocation, display, SIO, patch contracts, results, limits |
| [docs/64K-FEASIBILITY.md](docs/64K-FEASIBILITY.md) | The investigation that came first: what a 64 KB build needs and what it costs |
| [docs/64K-NOTES.md](docs/64K-NOTES.md) | The running list of memory-saving ideas, from the 130XE design onward |
| [docs/PORTING-LOG.md](docs/PORTING-LOG.md) | Everything that was done, in order, with the wrong turns (entries 44 onward are the 64 KB work) |
| [docs/DISKS.md](docs/DISKS.md) | The four 130 KB disks: the format, the unpacker, the checks, what is not known |
| [docs/ATARI-DESIGN.md](docs/ATARI-DESIGN.md) | The 130XE design the 65XE profile started from |
| [docs/TITLE.md](docs/TITLE.md) | The title stage |
| [REALHARDWARE.md](REALHARDWARE.md) | The study that led to the four-disk layout, and the questions about a real 1050 |
| [docs/ORACLE.md](docs/ORACLE.md) | The host oracle and how the sessions are compared |
| [docs/C64-LOADER.md](docs/C64-LOADER.md), [C64-CODE.md](docs/C64-CODE.md), [C64-RUNTIME.md](docs/C64-RUNTIME.md) | What was learned about the C64 game |
| [PROJECT-README.md](PROJECT-README.md) | The project's own README, as it was in the working tree |

## What is in the tree

| Path | What |
| --- | --- |
| `port/atari/src/display65.s`, `font65.s`, `title65.s` | The 65XE display (direct ANTIC mode 4, row DLIs, crossing-row copies, VBI publication), the ROM-font reconstruction, and the title stage with its POKEY tune |
| `port/atari/src/kernel.s`, `boot.s`, `title.s` | The Atari kernel (disk loader and ZX02 unpacker, interrupts, keyboard, sound), the boot code, and the 130XE title stage; one source for both profiles, the `XE64` conditionals in `kernel.s` select the 65XE one |
| `port/atari/profile65.py` | The 65XE patch set: checks the literal original bytes, then patches the colour stores and installs the shortened routines and entry wrappers |
| `port/atari/title65.py` | Builds the intro plans (palette and cell-role mappings for the eight scenes) from the original artwork |
| `port/atari/build.py` | Builds the Atari images: `--65xe` for the 64 KB profile, `--disks` for four 130 KB disks, `--colour` for the warm palette, `--no-title` to start at the game |
| `port/atari/disks.py` | The four-disk layout: items, ZX02 compression, index, ATR files |
| `port/atari/lockstep.py` | Plays a recorded key script on the oracle and on the Atari (Atari800 or AltirraSDL) and compares memory at every mark; `--65xe` selects the profile, `--disks` changes the disk as a player does, `--sio` uses the OS's own serial code |
| `port/atari/check65.py`, `speed65.py`, `title65_check.py` | The 65XE checks: all scenarios on four disks, frame timing and transient (flicker) captures, the intro |
| `port/atari/*_check.py`, `survey/`, `gfx_probes/` | The other checks, measurements and one-off investigations (colour, sound, keyboard, speed, graphics, disk reads) |
| `tools/atari64_survey.py`, `atari65_colour_writes.py` | The 64 KB survey of the game's memory use on the oracle, and the audit of every code path that writes colour |
| `tools/oracle.py`, `mos6502.py` | The oracle: the game's code on a host 6502 core, with the KERNAL ROM and a model of the disk |
| `tools/d64.py`, `g64.py`, `mmdisk.py`, `analyze_c64.py`, `area.py`, `disassemble.py` | Reading the original disks, the file tables and areas, and tracing the game's code |
| `tools/c64_trace.py`, `c64.py` | Recording the original C64 in VICE |
| `tools/traces/*.txt` | The recorded key sessions (menu, characters, shops, fights, spells, chests, outdoors, ...) |
| `tools/zx02/` | The ZX02 compressor, vendored (see below) |
| `tests/` | Unit tests for all of the above; `test_65xe.py` and `test_65xe_title.py` are the 65XE contracts |
| `docs/` | The design notes, findings and log (the generated `c64-*.json` files are left out) |
| `source/c64/` | Annotations for the disassembly of the game (`da65` info files and hints), not the code |
| `SPEC.md`, `PLAN.md`, `TODO.md`, `FIX.md`, `PROMPT.md` | The specification, plan, to-do list, a bug investigation, and a reusable prompt for porting other 8-bit games to the Atari |

`tools/export_github_src.py --out 65xe/src --readme tools/github_src_65xe_README.md` made this folder from the working tree.

## Left out, and why

- `c64/`: the original disk images and manuals.
- `build/`, `state/`, `test-artifacts/`: everything generated from the original game, including recordings and pictures of the C64 version, and the 65XE evidence reports and screenshots (`test-artifacts/64k/`) that `docs/65XE.md` links to. Their numbers are quoted in `docs/65XE.md`.
- `docs/c64-logical-disk.json`, `c64-areas.json`, `c64-code-map.json`, `c64-disk-layout.json`, and `source/c64/boot.s`: generated from, or part of, the original game. `tools/mmdisk.py`, `area.py` and `disassemble.py` make the first four from your own copy.

So the tests and tools that read the game do not run from a bare checkout. A few do: `python3 -m unittest tests.test_mos6502 tests.test_code6502 tests.test_disks.Format`.

## Building

You need:

- **Your own copy of the original game**: the *Original_v2* four-side set, as `.g64` images in `c64/images/` (see `tools/c64.py` for the names it looks for).
- **Python 3**, a **C compiler** (for ZX02).
- **cc65** (`ca65`, `ld65`) for the kernel.
- **VICE** (`x64sc`, with its C64 ROMs) to capture the C64 state the oracle starts from (`tools/traces/capture-entry.txt`) and to re-record sessions.
- **libatari800** (Atari800 built as a shared library) and its Python harness (`port/atari/harness.py`, from the author's Wizardry port, **not included here**), and optionally **AltirraSDL**, to run the Atari side. The tools look for all of this under the folder named by the environment variable `WIZARDRY_ROOT` (default `../wizardry_1`): `tools/toolchain/local/bin/`, `tools/emulators/local/`, and `port/atari/harness.py`. Adapting `shared_root()` in `tools/c64.py` is the place to point them elsewhere.

Then, roughly (see [docs/C64-LOADER.md](docs/C64-LOADER.md), [docs/ORACLE.md](docs/ORACLE.md) and [docs/65XE.md](docs/65XE.md) for the details):

```bash
python3 tools/analyze_c64.py            # decode the disks (build/c64/)
python3 tools/mmdisk.py                 # logical sides and docs/c64-logical-disk.json
# capture the oracle's start state with VICE into test-artifacts/c64/oracle-start/
#   (tools/traces/capture-entry.txt, docs/ORACLE.md "Start state")
python3 port/atari/build.py --65xe --disks            # build/atari65xe/disks/mm1-disk1.atr ... mm1-disk4.atr
python3 port/atari/build.py --65xe --colour --disks   # the warm-palette variant (overwrites the same folder: copy the grey set first)
python3 port/atari/check65.py                         # all scenarios on four disks at 64 KB, against the oracle
python3 port/atari/lockstep.py tools/traces/boot-to-treasure-and-reload.txt --65xe --disks --pictures --altirra --sio
python3 -m unittest discover -s tests                 # everything
```

Built this way from a clean export of this folder (the original images and the oracle's start state supplied), the four disks come out the same as the ones in the folder above. They were rebuilt and compared byte for byte before they were put there.

## Third-party code

- **ZX02** compressor, `tools/zx02/`, vendored unchanged from <https://github.com/dmsc/zx02> by **Daniel Serpell** (MIT licence, `tools/zx02/LICENSE`), derived from **ZX0** by **Einar Saukas** (BSD-style, `tools/zx02/LICENSE.zx0`).
- The 6502 **unpacker** in `port/atari/src/kernel.s` is Daniel Serpell's `zx02-optim` (MIT), adapted to read from a sector buffer and stop at a given length.

## Licence of the port's own code

No licence has been chosen yet. Until one is added, treat the port's own code and notes as shared for reading and learning. The game itself remains the property of its owners.
