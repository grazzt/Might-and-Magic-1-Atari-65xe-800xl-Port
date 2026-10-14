# Walking follow-up — 2026-10-12

**Profiled / checked.** Walking and turning now take **29 rather than 30 NTSC frames** in Atari800; return from a character sheet takes **24 rather than 25**. This is a modest one-frame improvement, not C64-speed walking. The baseline includes the new pause-clock fix so this comparison isolates conversion changes.

```sh
python3 port/atari/graphics_profile.py --out build/atari/walking-profile
python3 port/atari/graphics_check.py
python3 port/atari/speed_check.py --emulator altirra --settled-only
```

[Reports and pictures](../test-artifacts/walking/README.md).

| Action | Before, frames | After, frames | Conversion elapsed cycles, before → after |
| --- | ---: | ---: | ---: |
| Step | 30 | 29 | 627,114 → 616,740 |
| Turn left | 30 | 29 | 649,686 → 640,338 |
| Turn right | 30 | 29 | 627,228 → 616,512 |
| Character prompt | 22 | 21 | 627,912 → 616,284 |
| Return from character sheet | 25 | 24 | 486,552 → 473,670 |

The step's converter instruction cost falls **330,909 → 323,314 cycles (2.3%)**. Its elapsed conversion cost falls **1.65%**; the full action gains **3.3%** because frame boundaries quantize the result. Step/turn latency remains about 484 ms, compared with the original C64's previously measured 130–143 ms.

## Changes

- Four pixel lookups per loop iteration instead of two; all four lookup operands remain synchronized. The identity-copy loop copies two bytes per iteration instead of one.
- Cell mapping keeps its raw matrix byte in X rather than pushing/pulling it. Histogram counting reads the matrix byte a second time instead of using the stack; the original IRQ does not modify that input.
- Derive colour RAM's high byte from the matrix row's high byte plus `$D4`, removing a redundant 25-byte table.
- Move the nine-byte `rf_blank` helper into unused TOP bytes after envelope state, freeing room for the larger copy loop. No bank, sector or game-file changes are required by the speed work.

The pixel conversion/palette policy is unchanged. All **28 common benchmark PNGs** and all **seven game-state hashes** match the baseline exactly. The independent frozen converter checks 24 differential refreshes, all 16 qualification mappings, exhaustive/mixed pixel patterns and a deliberate pair-swap failure. Regression limits now retain the 29-frame movement and 24-frame return bounds.

More speed needs a larger change to palette/cache or screen-conversion work. Blanking the display during conversion saves time but introduces a visible flash, and altering the original renderer would conflict with the current operand-only policy. Neither is part of this follow-up.

The idle positive control now asserts the kernel's `key_given` flag. Artificially aging `stamp` can miss the branch when a frame stops after SBC has already read it. Sampling CPU bank ownership also counts conversion frames that stop inside a main-memory IRQ; the ordinary idle negative control remains zero.

**Final checks:** all 103 tests pass. AltirraSDL independently confirms 29-frame step/turns and a 24-frame return, with zero ordinary idle conversion and 58/60 forced-control frames in conversion. [Altirra report](../test-artifacts/walking/altirra-report.json), [full regression](../test-artifacts/gameplay/regression.txt).
