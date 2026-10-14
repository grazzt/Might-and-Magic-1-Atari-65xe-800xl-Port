# Display transitions and play speed — checked 2026-10-11

The user reported repeated `2` characters when leaving text for the town
graphics. This is a separate bug from the permanent text corruption fixed
in log entry 18. Both Atari800 and AltirraSDL reproduced the transient.

## Cause: a shared buffer exposed during drawing

**Read and captured:** the old Atari text display list read `$0400` directly.
The C64 game uses that same memory for its upper bitmap's per-cell colour
matrix. Preparing graphics replaces character codes with colour bytes while
ANTIC is still showing the text list. In the captured inn transition, the
garble is already visible at frame 61, before the fake VIC bitmap-enable bit
is set. Blanking only when that bit changes would therefore miss it.

![Before: colour bytes displayed as characters](../test-artifacts/speed/before-atari800/enter-town-061.png)
![After: the completed inn stays visible](../test-artifacts/speed/after-atari800/enter-town-061.png)

The old kernel then kept showing the live text until `refresh` finished
converting all 25 bitmap rows. The previous estimate of eleven frames ignored
the real display-DMA cost and overstated the available CPU time. A return
from a character sheet to graphics took 34 frames before the fix.

## Implemented in the Atari kernel

- **Completed text snapshot.** `text_list` now reads `$4000` in display bank 0.
  `rf_text` copies the game's `$0400–$07FF` there when GETIN refreshes the
  screen. Later colour-matrix writes cannot change the displayed text.
  Boot initializes the snapshot with spaces.
- **Publication on a mode change.** The snapshot reuses the graphics buffer.
  Before overwriting it for a text/bitmap transition, `rf_blank` clears
  `frame_ready` and disables DMA. VBI keeps DMA disabled until all rows are
  ready and `shown_mode` has been published. The finished screen appears on
  the next VBI. There is a short black interval; there are no colour bytes
  displayed as characters or bitmap glyphs displayed as text. Graphics-to-
  graphics updates retain their existing display behavior.
- **Exact palette caches for rows 6–24.** Nineteen 60-byte records occupy
  unused bytes of the existing 9 KB display allocation. Each records 40
  matrix bytes, 16 pixel mappings, a uniform colour-RAM nibble, and three
  chosen colours. Uniform colour-RAM rows with identical matrix bytes reuse
  palettes and mappings. Other rows still count their colours, but reuse
  mappings when the three selected colours match. No hashes are used. A
  transition from text bypasses all caches, since the snapshot overwrites
  one of them. Changes to the command panel are covered too.
- **Conversion loops.** Unroll the eight pixel bytes per cell and the three
  nearest-colour candidates. Keep the original strict comparison and tie
  order. Alias five duplicate address tables, recovering 125 bytes to fit
  the new routines. DLI's timing-sensitive instruction sequence is unchanged.

No game instruction or data byte changed beyond the existing 35 hardware
operand redirections / 70 changed disk bytes. No comparison exclusions were
added. No additional extended bank or boot sector was allocated.

## Measurements

Frame counts run from a first-poll input to the next held first-poll wait.
Two extra frames publish the final screenshot, and are excluded from timing.
Both Atari emulators are NTSC with patched disk transfers and agree on the
following before/after timings. Wall time here means emulated time.

| Action | Before, frames | After, frames | After, ms | Original PAL C64, ms |
| --- | ---: | ---: | ---: | ---: |
| Enter town from inn | 94 | 86 | 1435.2 | 13228.0, including true-drive loading |
| Step forward | 38 | 35 | 584.1 | 143.4 |
| Turn left | 38 | 34 | 567.4 | 129.7 |
| Turn right | 38 | 35 | 584.1 | 142.5 |
| `#`: choose character | 30 | 26 | 433.9 | 0.5 |
| `6`: character sheet | 5 | 6 | 100.1 | 81.4 |
| Escape back to town | 34 | 26 | 433.9 | 159.8 |

Walking improves by 8–11%, and return to graphics by 24%. Text copying adds
about a frame to small text actions. Walking remains slower than the C64:
the kernel still converts all bitmap bytes. These are measured improvements,
not a claim of C64-speed play. PAL/NTSC and different disk modes make the
inn-to-town comparison unsuitable for a disk-speed conclusion.

**Checked:** all 14 settled Atari800 screenshots (setup and seven measured
actions) are pixel-identical before and after. The transition pictures change
only as described above. Every visible text snapshot throughout both
text-to-graphics actions remains byte-identical to its starting snapshot, in
both emulators, including the period before the game's mode flag changes.

**Checked:** 50 synthetic cached/full palette comparisons cover five rows,
both cache layouts, unchanged inputs, matrix changes, colour-RAM low and high
nibbles, varied panel colours, equal histograms with different cell positions,
and text invalidation. Four uniform-cache hits are positively proven by
poisoning the calculation's `chosen` scratch bytes; the fast path leaves those
untouched while returning the correct mappings. For each case, forcing a full
calculation must give the same palettes and mappings.

**Checked:** an ordinary real input wait spends 0 of 60 sampled frames in
conversion. Artificially ageing the refresh timestamp spends 58 of 60 frames
there, proving the sampler detects conversion. The initial theory of repeated
idle copies was wrong: GETIN updates its timestamp on every poll, so the
original build already avoids that problem. The proposed extra wait filter
was removed.

## Reproduce / evidence

```bash
python3 port/atari/speed_check.py --out build/atari/speed
python3 port/atari/speed_check.py --emulator altirra --out build/atari/speed-altirra
python3 port/atari/speed_check.py --emulator vice --out build/atari/speed-c64
python3 port/atari/speed_check.py --cache-probe --out build/atari/speed
python3 -m unittest discover -s tests
python3 port/atari/build.py  # restore the normal playable disk after test builds
```

Raw frame states, transient PNGs, the original VICE monitor/cycle stamps and
cache-probe results are in [test-artifacts/speed](../test-artifacts/speed/README.md).
Tests in `test_atari_speed.py` assert stable transition text, faster movement
and bitmap return, positive timing control, and cached/full palette equality.
The other tests retain the eight lockstep sessions / 106 checkpoints, three
identical saves, keyboard play, all nine sounds, and Altirra with patched and
true serial transfers.

## Remaining work / constraints for the next LLM

- A full bitmap-input cache needs roughly 10 KB. It does not fit in display
  bank 0. On a stock 130XE, CPU and ANTIC share PORTB's bank-selection bits
  when both use extended RAM; CPU bank 1 with ANTIC bank 0 is not available.
  This is checked against Atari800's `MEMORY_HandlePORTB` and read in Atari's
  [130XE manual](https://www.digitpress.com/library/manuals/atari8bit/130xe_manual.pdf).
  Do not add a second-bank cache under that false assumption.
- The later three-path optimization reuses exact unchanged rows without a
  full raw cache. Further improvements may need a different conversion/storage
  scheme or the documented direct-display design and its constraints.
  Benchmark graphics-to-graphics updates separately from
  blanked mode transitions: blanking frees DMA cycles but must not add a black
  flash to every walking step merely to improve a benchmark.
- Keep exact cache invalidation. Matrix/colour caches alone cannot establish
  that bitmap pixels are unchanged; row reuse additionally checks idempotent
  mappings and compares all 320 bytes against the previous encoded output.
  `shown_mode=0` deliberately bypasses caches after text reused the buffer.
- After the three-path optimization, free bytes are LOADER 8, UNDER 4, EXT 30,
  EXT2 26. The 25-byte sound/Altirra probe area is explicitly reserved as
  `probe_scratch`. Palette records and row flags occupy 1,166 of the display
  buffer's 1,216 unused bytes. Main game RAM is not available for an unproven
  cache allocation.
- Fake-raster sound pacing between display modes remains as documented in
  [SOUND.md](SOUND.md); this work does not change it. PAL, Atari's own OS ROM,
  physical hardware and whole-game visual coverage remain untested.

## Reverse-transition report follow-up — checked 2026-10-11

The owner reports a repeated `2` window entering character information in Windows Atari800. Fresh normal-key captures of all six character sheets did not reproduce it in Linux Atari800. The initial generated ATR did not match its layout until rebuilt; the owner subsequently confirms the recopied Windows ATR has no repeated `2`s. No new kernel fix was applied. `python3 port/atari/transition_check.py` captures 240 frames and checks settled text/kernel integrity. All captures were inspected, including partial old frames and blanking; this does not establish behavior for the unidentified Windows setup. [Evidence](../test-artifacts/reverse/README.md), [full handoff and next steps](../FIX.md).

## Deep graphics profile — checked 2026-10-11

Baseline native walking work is about 135 ms outside conversion and 441 ms inside it. The converter executes 414,862 CPU cycles; pixels account for 37%, palettes 32%, setup/advance about 31%. It processes all 1,000 cells while only 336 change. Unchanged bottom rows cost 118,570 cycles. Diagnostic bypass gives 8 frames instead of 35 but a stale display; DMA blanking gives 24 with a black flash. Neither is a shipping fix. [GRAPHICS-PERFORMANCE.md](GRAPHICS-PERFORMANCE.md) gives the initial measurements and subsequent three-path implementation: walking conversion 364 ms / 342,179 CPU cycles, 640 cells converted and movement at 30 Atari800 frames (30–31 Altirra). All seven Atari800 baseline pixels/game hashes and seven Altirra pictures remain equal; all 82 unique tests pass with Altirra's required access. [Evidence](../test-artifacts/graphics-optimized/README.md).

## Palette mapping reuse — checked 2026-10-11

The later exact ordered-colour key reduces walking palette CPU work by
19.7%, whole conversion elapsed time by 8.1% (364 → 335 ms), movement
30 → 29 Atari800 frames (Altirra 30–31 → 29) and return to town 25 → 24. The sampled battle
commands are text and receive no palette benefit. All 83 tests pass;
broader captures keep the same pixels/game bytes. Current spare bytes:
LOADER 8, UNDER 1, EXT 14, EXT2 10. Prior memory/frame figures above are
historical baselines. [Full palette report](PALETTE-PERFORMANCE.md).

**Keyboard follow-up checked 2026-10-11:** held Ctrl+A now repeats across
combat characters through the original delay/rate controls. The layout
reuses the idle disk buffer for test calls and moves palette scratch/state;
current spare LOADER 8, UNDER 1, EXT 0, EXT2 10. All 85 tests pass, including
the graphics/palette speed and cache checks. [Details](KEYBOARD-REPEAT.md).

**Disk-loading follow-up, checked 2026-10-11:** OS setup/restoration is now
batched across direct sectors; known zero startup bytes are cleared exactly.
Patched Atari800 boot 4.19 → 1.29 s, inn-to-town 1.42 → 0.78 and signing in
(save plus inn loads) 0.55 → 0.27. Altirra standard serial boot 51.9 → 44.2 s.
These are first-poll NTSC waits; serial samples have ten-frame resolution.
All 86 tests pass. [Full timings, controls and limits](DISK-PERFORMANCE.md).

**Colour-quality tradeoff, checked 2026-10-11:** encounter selection filters
unused matrix colours and fixes the wide blue panel. Exact distance packing
and smaller copy loops keep it in the same bank. Atari800 and Altirra now
measure 30-frame steps/turns (previously 29), 48-frame town entry (47),
22-frame character prompt (21), 25-frame return (24); sheets stay six.
Stable text, idle controls and existing speed bounds pass. A slower first
prototype skipped an original exact pause target; zero-byte skipping fixes
the two affected combat routes. All 87 tests pass. [Details](COLOUR-SELECTION.md).
