# Disk loading — checked 2026-10-11

The first TODO #3 improvements are implemented. With Atari800's patched SIO,
boot falls from 4.19 to 1.29 seconds, entering town from 1.42 to 0.78, and
signing in (save plus return to the inn) from 0.55 to 0.27. Standard serial
boot in Altirra falls from 51.9 to 44.2 seconds. The game, sector size and
save layout remain unchanged.

Evidence: [reports, controls and pictures](../test-artifacts/disk-loading/README.md).
The baseline is `d117e552995871cf250aeae7c41abd01d81efa93` (held-key fix).

## What was measured

`port/atari/disk_check.py` boots a 130XE with BASIC off, Altirra XL OS and
NTSC. Atari800 uses the existing native harness; Altirra uses its bridge.
Keys arrive at the existing first-poll test hook, so thinking time and
physical key repeat do not contaminate the intervals. The first disk prompt
receives RETURN and side B; then town 1, the six supplied characters, X,
I/J/J/I to the innkeeper, and Y to sign in. The innkeeper prompt is drawn
into the bitmap: searching `$0400` for its ASCII text is not a valid check.

Boot ends when the first prompt is printed and GETIN has polled. Other
intervals end at the next held key wait. Each screenshot waits two additional
VBIs for publication; these are outside the measured interval. Screens were
inspected after all capture processes finished. They show the normal prompt,
menu, inn and town, with matching before/after native pixels.

Altirra is explicitly cold-reset *after* its bridge pauses and SIO is
configured. Its initial process startup can otherwise consume a variable
number of uncounted frames. Patched runs sample every frame; serial runs
sample every ten (167 ms). Serial measurements round up to that resolution.
Frame counts describe emulated time, not host script duration or every
possible Windows emulator configuration.

| Interval | Atari800 patched, before → after | Altirra patched, before → after | Altirra standard serial, before → after |
| --- | --- | --- | --- |
| Boot to first prompt | 251 → 77 frames; 4.189 → 1.285 s | 230 → 56; 3.838 → 0.935 s | 3,110 → 2,650; 51.900 → 44.223 s |
| RETURN to options | 26 → 6; 0.434 → 0.100 s | 26 → 6; 0.434 → 0.100 s | 340 → 320; 5.674 → 5.340 s |
| Options to inn | 3 → 3; 0.050 → 0.050 s | 3 → 3; 0.050 → 0.050 s | 10 → 10; same sampling bin |
| X: inn to town | 85 → 47; 1.419 → 0.784 s | 85 → 47; 1.419 → 0.784 s | 650 → 610; 10.847 → 10.180 s |
| Y: sign in, save and reload inn | 33 → 16; 0.551 → 0.267 s | 35 → 16; 0.584 → 0.267 s | 420 → 410; 7.009 → 6.842 s |

The sign-in interval includes reads after the write. It is not the historical
1.8-second *write-only* measurement. The apparent serial sign-in gain is only
one sampling bin; do not claim a meaningful serial-save speedup from it.

## The bottleneck and the changes

**Read in the old kernel, checked by native probes:** every sector call saved
the game IRQ vector, swapped 128 zero-page bytes, enabled the OS ROM and its
interrupts, called SIOV, disabled the OS, swapped zero page back, restored
sound/keyboard state and restored the IRQ vector. Even an instant emulator
disk patch paid this setup and restoration for every 128 bytes. Eight direct
sectors used sixteen swaps; an 18-sector roster-sized write used thirty-six.

**Implemented:** `read_sector` enables the OS only when PORTB says it is
currently out. Subsequent direct sectors continue with OS zero page, ROM
and interrupts active. `game_mode` restores the game once at the end, or
before a bounce-buffer copy that needs RAM beneath the OS ROM. This gives
two swaps for both eight direct sectors and the 18-sector write. Partial
first/last sectors and upper destinations still take the required restore
path. A zero-length read performs no swaps. The caller's saved flags and
the original loader's register / `$FC–$FF` return convention are preserved.

To fit, the sector counter now *is* the DCB sector word, removing a redundant
copy into `$030A/$030B`. Saving the advance count directly replaces a
PHA/PLA pair. Net LOADER growth is three bytes; spare LOADER / UNDER / EXT /
EXT2 is **5 / 1 / 0 / 10**. There is no extra buffer, bank or display memory.
The OS remains available for real serial interrupts; this is not a new SIO
patch or high-speed protocol.

**Read and checked at every build:** the startup snapshot's `$E000–$FF49`
contains exactly 8,010 zero bytes. `boot.s` now clears those bytes while the
OS is out, stopping before the stand-in registers and interrupt vectors.
`build.py` refuses to build if the captured range ever contains a nonzero
byte. This removes 63 kernel sector reads and 8,192 padded image bytes.
Kernel boot reads fall from 527 to 464; the OS still reads 56 boot sectors.
Other startup/title leftovers remain loaded: no unproven assumption that the
game never reads them is needed, and comparison exclusions are unchanged.

**Checked separately, Atari800 patched:** batching alone gives 103-frame
boot; zero-fill alone gives 226; baseline is 251 and combined is 77. Runtime
load gains come from batching; zero-fill affects boot only. The control
builds use the old/new kernel and old/new build/boot independently in `/tmp`.

## Validation and reproduction

All **86 tests pass in 151.729 s**, including nine scripts / 116 game-state
checkpoints, three exact saves, save/reload after cold start, sound, held
keys, graphics/palette checks, ordinary keyboard play and both Altirra SIO
modes. Original game bytes still have only the same 35 operand redirections
(70 disk bytes); the four game-side payloads are identical to the baseline.

`disk_probe.py` adds fifteen native exact-byte read cases: zero/short length,
unaligned addresses, offsets 0/1/127/128/255, all four sides, direct-to-bounce
boundaries, and RAM beneath the OS. Guards check destination bounds. A
2,304-byte patterned write changes exactly the requested disk bytes and an
unaligned readback returns the expected slice. It checks zero page, IRQ,
PORTB, loader returns and immutable kernel bytes, and measures swaps with
an instruction-preserving temporary LDX hook. The same cases pass with the
old kernel as a positive control, with sixteen / thirty-six swaps.

The disk-call trampoline uses free TOP padding at `$FFE7`, not the shared
`probe_scratch` sector buffer: SIO reads overwrite that buffer. It restores
the padding and CPU state after each call. Atari800 writes are flushed on
exit before comparing the whole disk. Altirra uses an isolated input copy
and its persistent working disk. No probe bytes enter the playable ATR.

```bash
python3 port/atari/disk_check.py --out build/atari/disk-atari800
python3 port/atari/disk_check.py --emulator altirra --out build/atari/disk-altirra
python3 port/atari/disk_check.py --emulator altirra --sio --out build/atari/disk-serial
python3 port/atari/disk_probe.py --out build/atari/disk-probe
python3 -m unittest discover -s tests
python3 port/atari/build.py
```

The helper CLIs restore the normal build afterwards. `disk_check.py
--existing` measures an already-built **test** disk without rebuilding; keep
its matching layout/segment files. Altirra checks require local socket access.

Playable `build/atari/mm1.atr` and `build/atari/mm1-disk-fast.atr` are identical,
normal input enabled, 724,752 bytes. SHA-256:
`4132030ed4dcbc9f2333748361a6b0b2c77a2a4e69f275ece4c1e0628721418c`.

## Remaining opportunities

Standard serial transfers still dominate. A negotiated high-speed SIO path
or 256-byte sectors could improve that, but neither is implemented or
measured here. Larger sectors need a safe larger bounce buffer and changes
to all disk offsets/save checks. Main-memory kernel space is nearly full.
Further startup compression could recreate title patterns exactly, whereas
omitting them would require evidence of every read before overwrite. There
is no Atari ROM, PAL or physical-hardware performance claim from these tests.
