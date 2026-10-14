# Palette mapping reuse — 2026-10-11

**Checked:** neighbouring rows often select the same ordered three C64
colours, so they need the same nearest-colour mapping. Reusing the live
mapping avoids 13 of 16 rebuilds on the measured walking refresh. Palette
CPU work falls **19.7%** and the full conversion interval **8.1%**. This is
an incremental improvement over the three graphics optimizations, not over
the original unoptimized port. Starting runtime: commit `a72ff09` / metadata
`b49ee35`. Original game files, colour decisions, lookup tables, tie order,
sound and input timing rules remain unchanged.

## Measured movement

Atari800, 130XE, NTSC, Altirra OS, patched SIO, first-poll script keys. Native
scanline timer includes DMA/interrupt work; 114-cycle resolution. As in the
previous profiler, intervals start at key consumption and end at the next
held wait, excluding two final publication frames. Frame counts include
rounding, while conversion times below use the measured cycle interval.

| Action | Previous frames | New frames | Previous conversion ms | New conversion ms |
| --- | ---: | ---: | ---: | ---: |
| Enter town | 86 | 85 | 287.77 | 269.87 |
| Forward | 30 | 29 | 364.08 | 334.52 |
| Left | 30 | 29 | 375.23 | 349.43 |
| Right | 30 | 29 | 364.14 | 334.27 |
| Scripted character prompt | 21 | 21 | 345.80 | 335.67 |
| Character sheet | 6 | 6 | 6.69 | 6.69 |
| Return to town | 25 | 24 | 280.83 | 257.39 |

**Checked in AltirraSDL:** entry 86 → 85 frames, forward/right 30 → 29,
left 31 → 29, return 25 → 24; prompt/sheet remain 21/6. All seven final
RGB images match its baseline. Both emulators' ordinary idle checks find
zero refresh frames with a working forced-refresh positive control.

**Checked instruction attribution:** walking palette work 133,362 → 107,041
CPU cycles; whole conversion 342,179 → 315,858. Thirteen shared mapping hits
leave three actual rebuilds and nine cached restores. The converter still
processes 640 cells and skips nine qualified unchanged lower rows. The
palette share drops from 39.0% to 33.9% of conversion CPU work. Host replay
equals all seven native converted buffers/cache bytes and 100 palette values.

## What changed and why it is exact

`choose_colours` still scans/counts the inputs, selects the same colours and
writes each row's hardware palette. Immediately before rebuilding `pair`
and `pair4`, it compares the **ordered three chosen C64 colours** with the
key belonging to the live mapping. Exact equality reuses those arrays; any
difference calculates the original nearest-colour mapping. Black is always
the fourth candidate; the distance table and strict tie order are constants.
Panel colour affects the per-row register but not this mapping key.

The key is three bytes at `$DFFC–$DFFE`, initialized to `$FF,$FF,$FF` by the
normal boot image. All selected colours are nibbles, so the invalid marker
cannot match. A rebuilt mapping records its key. Both palette-cache restore
paths replace the mapping and set the first key byte to `$FF`, preventing
an old key from advertising different restored pairs. Text snapshots leave
the mapping arrays intact. A power cycle reloads the invalid key.

**Checked:** the explicit adversarial sequence builds mapping A, builds B,
restores cached A, then requests B through an uncached row. It must rebuild
B and match full calculation. Without restore invalidation it could falsely
reuse A under B's stale key. Ordered comparisons also retain the original
pair/register interpretation; no sorted key, hash or collision assumption.

No matrix/colour-RAM fast-path assumption was added. In particular, movement
changes the upper matrices, and view/panel colour-RAM patterns differ. This
shortcut works after selecting the palette even when those inputs changed.

## Broader workloads

**Checked:** `palette_check.py` captures nine settled native states from
existing first-poll routes: town, gate, outdoors, dungeon, arena, encounter,
fight and one attack (town occurs in two routes). It compares the complete
new refresh against the captured old kernel, not a reimplementation of its
palette algorithm. The reference also reproduces the original native display.
All nine new native captures retain the old pixels and compared game bytes.

| Settled graphics state | Palette CPU cycles before | After | Reduction |
| --- | ---: | ---: | ---: |
| Town | 116,629 | 115,712 | 0.8% |
| Town gate | 116,352 | 108,888 | 6.4% |
| Outdoors | 116,670 | 113,587 | 2.6% |
| Dungeon | 116,510 | 113,325 | 2.7% |
| Arena | 116,544 | 111,177 | 4.6% |
| Encounter | 116,739 | 113,554 | 2.7% |

These are **host instruction counts for re-refreshing settled states**,
without DMA or interrupts. They are not outdoor input-latency benchmarks.
More per-row caches already hit there, so fewer rebuilds remain to eliminate
than during the measured movement's page flip. Gains depend on content.
The sampled fight and attack use mode 0 (text), do no palette calculation
and receive no benefit from this shortcut. Monster/encounter graphics remain
covered by their bitmap captures. This is not whole-game artwork coverage.

## Memory and verification

**Checked layout:** 32 extra code bytes and three state bytes fit the existing
segments. Move the 16-byte idempotence table from EXT2 into EXT spare space.
Net changes: UNDER +3, EXT +16, EXT2 +16. Remaining spare bytes: LOADER 8,
UNDER 1, EXT 14, EXT2 10. The 25-byte test trampoline remains reserved;
display-padding allocation, bank count, 56 boot sectors and 35 redirected
game instructions remain unchanged. `palette_code_end` bounds the idle
sampler independently of the moved constant table.

The new differential regression exercises 228 palette cases across rows
0, 5, 6, 13, 14, 15, 16 and 24: cold/warm state, uniform or varied RAM,
view/panel patterns, high bits, matrix permutations, ties, black and cached
restore invalidation. All 16 mappings and their shifted copies plus all
four row registers match full original calculation. Positive shared hits
are required. Existing complete graphics/row-reuse and 50 palette-cache
probes remain in the suite. Comparison exclusions are unchanged.

The new native benchmark retains the previous seven game hashes and final
RGB images. A fresh uninstrumented control checks probe timing/pixels.
**Checked:** all 83 tests pass in 147.025 seconds with Altirra's local-socket
access, including eight lockstep sessions / 106 checkpoints, three exact
saves, sound, ordinary keyboard play and both Altirra disk modes. Fourteen
benchmark endpoint images remain unchanged across the two emulators, plus
all nine broader native captures. Full regression and Altirra results are
retained in the evidence folder.
PAL, Atari ROM and real hardware remain untested; sound pacing is unchanged.

The normal playable ATR is restored and copied as
`build/atari/mm1-palette-fast.atr` (732,944 bytes, test mode false).
SHA-256: `6f153c9b8e91117a2f37684e8597c43bb7162a1cc5f5ea97d9ace166665faf91`.
The earlier `mm1-graphics-fast.atr` is the previous optimization build.

## Reproduce

Run sequentially: every helper shares build output, and native scenarios need
separate processes because libatari800 is one machine per process.

```bash
python3 port/atari/palette_check.py --capture outdoors --out build/atari/palette/outdoors
python3 port/atari/palette_check.py --capture fight --out build/atari/palette/fight
python3 port/atari/palette_check.py --capture encounter --out build/atari/palette/encounter
python3 port/atari/palette_check.py --check test-artifacts/palette/before --out build/atari/palette-check
python3 port/atari/graphics_profile.py --out build/atari/palette-profile
python3 port/atari/speed_check.py --emulator altirra --settled-only --out build/atari/palette-altirra
python3 -m unittest discover -s tests
python3 port/atari/build.py
```

`--settled-only` omits intermediate PNG files, but still reads/checks every
transition-frame state and displayed text byte and saves start/end pictures.
The palette/profile helpers restore the normal playable ATR in `finally`;
the suite/speed tool uses test builds, so rebuild afterwards. See
[raw captures, timings, differential output and logs](../test-artifacts/palette/README.md).

**Wrong turns:** copying all three cached colours into the live key after
every restore added enough work to slightly slow the settled town case.
Cheap invalidation retained the movement benefit and removed that measured
regression. An early direct-call reference fixture replaced EXT data and
accidentally reset its row to 24; set the requested row after injecting the
old kernel. The corrected fixture matches the unchanged baseline before
testing the optimization.

**Later keyboard layout follow-up, checked 2026-10-11:** held-key repeat
moves matrix histogram scratch into EXT and row/cell state into UNDER,
while native test calls share the idle sector buffer. Current spare LOADER
8, UNDER 1, EXT 0, EXT2 10; the earlier layout figures describe the palette
implementation before that change. Palette selection/mapping remains exact
and all differential checks pass. [Lifecycle and migration](KEYBOARD-REPEAT.md).

**Later colour-policy change, checked 2026-10-11:** wide encounter rows now
select matrix colours from actual bitmap-pair presence and use an
18-column panel. Their old cache is bypassed/invalidated; walking retains
its exact selection, caches and mapping reuse. Distances are packed
symmetrically with all 256 values/ties unchanged. Historical encounter
pixels are intentionally improved and compared to independent enumeration;
walking remains differential against the frozen kernel. The regenerated
gallery fixes tan gremlins/snakes and the white panel strip. Spare 5 / 1 /
0 / 3; steps/turns 29 → 30 NTSC frames in both emulators, all 87 tests pass.
[Colour findings](COLOUR-SELECTION.md), log entry 34.
