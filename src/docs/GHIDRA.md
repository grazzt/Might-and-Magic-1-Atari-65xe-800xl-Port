# Ghidra for the C64 port

Installed and verified on 2026-10-09, on Mark's Linux x86-64 / WSL machine.

| Component | Installed location |
| --- | --- |
| Ghidra 12.1.4 PUBLIC | `~/tools/ghidra_12.1.4_PUBLIC` |
| Temurin JDK 21.0.12.1+1 | `~/tools/jdk-21.0.12.1+1` |
| Desktop launcher | `~/.local/bin/ghidra` |
| Headless launcher | `~/.local/bin/ghidra-headless` |
| Desktop-menu entry | `~/.local/share/applications/ghidra.desktop` |

The launchers are on this machine's PATH and set `JAVA_HOME` only for the Ghidra process. Existing Java 17 installations and other projects' Java settings are unchanged. Run `ghidra` in a desktop terminal to open the GUI, or `ghidra-headless` for the batch interface. Headless analysis has been tested; the GUI has not been exercised.

Both downloads matched their published SHA256 checksums before extraction. [GHIDRA-SOURCES.json](GHIDRA-SOURCES.json) retains their exact URLs, versions and hashes. Local installation notes also live in `~/tools/GHIDRA.md` and `~/tools/ghidra-installation.json`. Ghidra/JDK binaries are not stored in this repository. On another machine, extract the pinned releases into new directories and point launchers at that machine's paths; cloning this project does not install these tools.

## Role in the port

Use Ghidra for persistent routine labels, references, control-flow inspection and exploratory pseudocode. Use VICE to establish execution, memory banking, disk transfers and self-modifying code, and use da65/ca65 to produce and verify reassemblable source. Decompiler output does not establish source-code equivalence or exact 6502 behaviour.

Model C64 memory and the 1541's address space separately. Likewise, distinguish code loaded into the same address range at different times. Our 64 KB VICE RAM captures contain RAM under the C64's ROM/I/O windows, not a complete picture of the CPU-visible memory map. Supply the appropriate regions and entry points before relying on references or decompiler results.

REA is not installed. The REA revision inspected on 2026-10-09 (`077d6c407b3ea7443a7277ae0e5531b3927dd742`) limits its Ghidra adapter to x86, x86-64, ARM and ARM64; it does not expose our raw 6502 import workflow. Ghidra itself includes the `6502:LE:16:default` language. We can use its native scripting/headless interface directly. [REA adapter at the inspected revision](https://github.com/morluto/rea/blob/077d6c407b3ea7443a7277ae0e5531b3927dd742/src/ghidra/GhidraProvider.ts)

## Verified bootstrap import

The 59-byte bootstrap PRG has a two-byte load-address header and a 57-byte payload. Import it using these explicit settings:

| Setting | Value |
| --- | --- |
| Loader | `BinaryLoader` (Raw Binary) |
| Language | `6502:LE:16:default` |
| Compiler specification | `default` |
| Base address | `0x02cb` |
| File offset | `0x2` |
| Payload length | `0x39` (57 bytes) |

Set the length as well as the offset. In the tested headless import, changing only the offset retained the full 59-byte default block length. Ghidra also creates separate uninitialized zero-page and stack blocks from its 6502 processor definition; those are not extra bytes from the PRG.

From the repository root, first generate the verified PRG if necessary:

```bash
python3 tools/analyze_c64.py
python3 tools/rebuild_boot.py
```

Then run the installation check. The named Ghidra project is temporary and deleted on completion; keep this name reserved for the check.

```bash
mkdir -p build/ghidra-validation/projects
ghidra-headless "$PWD/build/ghidra-validation/projects" installation-smoke \
  -import "$PWD/build/source/boot.prg" \
  -processor 6502:LE:16:default -cspec default \
  -loader BinaryLoader -loader-baseAddr 0x02cb \
  -loader-fileOffset 0x2 -loader-length 0x39 \
  -scriptPath "$PWD/tools/ghidra" -postScript Ghidra6502Smoke.java \
  -deleteProject > build/ghidra-validation/headless.log 2>&1
rg 'GHIDRA_6502_SMOKE_PASS' build/ghidra-validation/headless.log
```

[Ghidra6502Smoke.java](../tools/ghidra/Ghidra6502Smoke.java) checks the language, imported block size and entry instruction, creates a bootstrap function, and invokes the native decompiler. Check the explicit success marker: Ghidra can exit with status zero even when a post-script throws an exception.

**Verified:** the payload occupies `$02CB–$0303`, begins with `SEI`, and native decompilation completes. **Known scope:** the final jump to `$2000` reaches code outside this bootstrap-only import. Ghidra reports unresolved flow and incomplete pseudocode there; importing the second stage and establishing its entry points is future work. This check validates the installation, not whole-game analysis.

The installed headless documentation is `~/tools/ghidra_12.1.4_PUBLIC/support/analyzeHeadlessREADME.html`. Release and processor references: [Ghidra 12.1.4](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build), [6502 language definitions](https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/Ghidra/Processors/6502/data/languages/6502.ldefs).
