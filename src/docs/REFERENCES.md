# Shared reference library

Use the existing sibling `../wizardry_1` project. Set `WIZARDRY_ROOT` to override that path. Nothing in this project installs into or changes the sibling project. [REFERENCES.json](REFERENCES.json) records its revision and the hashes observed for the reused files; it does not imply all sibling working-tree files were committed at that revision.

Required locally: Python 3 (standard library only), the sibling's VICE 3.7.1 `x64sc`/`c1541`, C64 and 1541 ROMs, and its cc65 tools. Missing installations can be rebuilt with that project's `tools/emulators/setup.sh` and `tools/toolchain/setup.sh`; read their README files first. Interactive VICE additionally needs a working desktop display. Headless smoke checks use VICE console mode.

Ghidra 12.1.4 is installed separately at `~/tools/ghidra_12.1.4_PUBLIC`, with Temurin JDK 21 at `~/tools/jdk-21.0.12.1+1`. The `~/.local/bin/ghidra` and `ghidra-headless` launchers select that JDK for their own processes. It is available for static 6502 analysis and is not required by the existing VICE/ca65 checks. See [GHIDRA.md](GHIDRA.md) for use and validation, and [GHIDRA-SOURCES.json](GHIDRA-SOURCES.json) for verified download URLs and SHA256 hashes. The installation is local to this machine; cloning the repository does not install it.

The host oracle (`tools/oracle.py`) loads `kernal-901227-03.bin` and `chargen-901225-01.bin` from that VICE installation's `share/vice/C64/`. Their SHA256 hashes are pinned in `test-artifacts/c64/oracle-start/entry.json`. The ROMs are not stored in this repository.

Reused references:

| Sibling path | Purpose |
| --- | --- |
| `c64/disk/D64_Format.txt` | Peter Schepers' D64 sector geometry, directory and file-chain layout |
| `c64/manuals/Commodore_64_Programmers_Reference_Guide.txt` | C64 hardware and KERNAL calls |
| `c64/manuals/Mapping_the_Commodore_64.txt` | Memory locations and vectors |
| `c64/programming/VIC_II_Reference.txt` | Display modes, banking and layout |
| `c64/tools/VICE_Monitor.html` | Monitor scripts, RAM capture and disk attachment |
| `common/tools/{ca65,da65,ld65}.html` | Assembler, disassembler and linker |
| `tools/pvm/cpu6502.py` | Looked at for the host oracle and not used: it runs single native routines with Apple I/O and has no interrupts. The oracle's core is `tools/mos6502.py` in this project |
| `port/atari/` | Future reuse of Atari hardware routines and lockstep methods |

Online primary references consulted on 2026-10-09:

- [VICE monitor manual](https://vice-emu.sourceforge.io/vice_12.html): command-file playback, bank selection, memory dumps and screenshots. Local documentation and the installed tool's help determine the commands used here.
- [ScummVM MM1 map implementation](https://github.com/scummvm/scummvm/blob/master/engines/mm/mm1/maps/map.cpp): PC-format map records use 512 bytes (walls plus states), with separate overlays. This is a research lead only; **no C64 format compatibility has been established**. No ScummVM code has been copied.

The game media and manuals came from the [C64Games listing](https://www.c64games.de/phpseiten/spieledetail.php?filnummer=3121). The two `SOURCES.json` manifests retain exact download URLs, original ZIP member names, byte counts and SHA256 hashes; archives are retained. The archive documentation is historical evidence, not a substitute for tests on the installed VICE.
