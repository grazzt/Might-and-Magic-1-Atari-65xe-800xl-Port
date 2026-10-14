# Encounter colours — checked 2026-10-11

The gremlin and snake now draw green, and the whole encounter-name panel
keeps its blue background instead of turning white on the left. The
dinosaur's name panel is fixed too. Atari800 and Altirra captures agree;
all 87 tests pass. The 25-pair [gallery](SCREENSHOTS.md) is regenerated.

![Previous Atari, corrected Atari and original C64](../test-artifacts/colour-selection/comparison.png)

Baseline: `d2410f17ea104d7d840a18af49760a15a5343b2d`. Original game files,
operand redirections, RNG/input rules, disk layout and saves are unchanged.
[Evidence and reproduction](../test-artifacts/colour-selection/README.md).

## Two causes, read and checked

The old selector counts both matrix nibbles of every cell, even when its
bitmap never uses either colour. Encounter pictures occupy a subset of
the view; surrounding blank cells retain old wall/picture matrix values.
In a gremlin body row, seventeen cells still advertise tan/black, while
thirteen advertise green/pink. Tan wins although those cells draw black.
The green pixel is then mapped to tan. The snake has the same stale-input
problem, with different matrix colours in different rows.

The command panel starts at column 30, but the encounter list starts at 22.
Original `EN` at `$2742` paints eighteen colour-RAM cells from `$D816` blue
(`$0E`), repeating for each monster row. The Atari marked only the last ten
columns for its fourth colour register. The remaining eight blue cells
therefore took the view's shared white colour. The C64 names themselves use
a dark matrix colour; the conspicuous white area was their background.

Display mode 1 alone does not identify an encounter. It also shows ordinary
door messages and the arena; widening all of those panels turns walls cyan.
The new layout decision uses mode 1 **and the original blue-strip marker at
`$D816`**, masked to a nibble. Other screens retain column 30. No monster IDs
or special green palette entry are hardcoded into selection.

## What changed

On wide encounter panels, the first sixteen rows now count a matrix colour
only when the cell's eight bitmap bytes contain its pixel pair. A cell
contributes at most one vote for each of pairs 01 and 10; colour/tie order
and nearest-colour distances otherwise remain the same. The common view
colour-RAM nibble still serves PF2, and the panel's common nibble serves PF3.

The presence scan needs no new lookup table. Existing mapping table 6 swaps
01 and 10 while preserving 00/11. `(swap(byte) XOR byte) AND byte` therefore
marks pair 01 in the `$55` bits and pair 10 in the `$AA` bits. OR these marks
over eight lines, then test the two masks. Blank bytes skip the lookup work.
An independent direct enumeration of all 256 byte values proves this rule.

Refresh also adjusts the character-code high bits for columns 22–29 in each
of its three code rows. Those bits select PF3 for pixel pair 11. Returning
to a normal panel clears them. Lower party/text rows use the plain code
table throughout. Source bitmap and matrix bytes are never changed.

Palette selection now depends on bitmap pixels in the encounter rows, so
the old matrix/uniform-RAM cache cannot authorize them. They always scan,
mark their cache record `$FF` and clear row-reuse qualification. This also
prevents a stale cache when leaving an encounter. Walking and lower rows
retain the existing exact caches and mapping reuse. A bitmap-only change,
with identical matrix and colour RAM, is an explicit negative regression.

## Fit and timing

The kernel already had almost no free space. The new implementation fits
the same bank and 56 boot sectors by packing symmetric distances: 136
entries plus sixteen offsets replace 256 entries, saving 104 table bytes.
All 256 source/candidate distances retain their original rounded values and
strict tie order. The idempotence table moves into sixteen unused TOP bytes
at `$FFD3–$FFE2`, before GETIN. Immutable-kernel checks cover it there.

The general converter now processes two bytes per loop instead of eight;
the identity copy uses a small loop. The table-page guard, identity path and
qualified unchanged-row reuse remain. Histogram scratch moves to EXT2.
The final spare bytes are LOADER 5, UNDER 1, EXT 0, EXT2 3, plus one byte
before GETIN and nineteen after it. No new framebuffer, raw cache or bank.

**Measured in both emulators:** walking/turns 29 → 30 NTSC frames (about
17 ms extra), town entry 47 → 48, character prompt 21 → 22 and return 24 →
25. Character sheets remain six frames. The existing speed/transition tests
still pass. This is a small, measured colour-quality tradeoff, not another
speed optimization. The seven native profiler outputs replay exactly on the
host, and ordinary idle polling still does no repeated conversion.

The first version made every mode-1 view pixel-aware. Walking also passes
through that mode, so it rose to 45 frames; limiting scanning to the actual
wide encounter layout removed that regression. A fully rolled lookup loop
gave 31-frame turns; processing two bytes restored the 30-frame bound.

The full suite also caught an encounter-to-combat pause hanging. Original
pause `$C355` waits for an **exact** jiffy target; the initial extra rendering
could skip that target. Skipping zero bitmap bytes reduced the work enough
for both failing encounter/death routes to complete, with their original
checkpoints and saves equal. Neither the pause code nor clock rule changed.
An isolated slow control confirms the clock equals its target while the CPU
is still rendering, then passes it before the pause can test it; the control
never reaches the next wait. Its frame samples are retained as evidence.
This makes actual play-throughs essential alongside isolated palette tests.

## Results and verification

Metrics below decode the row registers back to their corresponding C64
colour indices. They measure colour selection, not exact cross-platform RGB:
the Atari palette, luminance and emulator rendering still differ.

| Frame | Green view pixels retained, before → after | Blue panel pixels retained, before → after | Incorrect logical colours, whole frame |
| --- | --- | --- | --- |
| Gremlin | 0 / 898 → 898 / 898 | 1,746 / 2,710 → 2,710 / 2,710 | 2,236 → 224 |
| Snake | 0 / 2,060 → 2,060 / 2,060 | 6,400 / 9,510 → 9,510 / 9,510 | 5,328 → 0 |
| Dinosaur | 2,880 / 2,922 → 2,922 / 2,922 | 2,480 / 4,082 → 4,082 / 4,082 | 1,814 → 502 |

All eleven native before/after captures have identical compared game hashes.
Nine graphics buffers and all row palettes match the independent host model;
the two text frames are unchanged. Altirra's three monster captures also
match that model and those game hashes. Twenty-one Atari gallery images and
all twenty-five C64 images remain byte-identical; the four changed Atari
images are the affected encounter scenes, including the post-portal view.
All fifty gallery images were decoded and visually inspected.

**87 tests pass in 152.657 s:** nine scripts / 116 checkpoints, three exact
saves, cold-start reload, sound, held keys, ordinary play, disk boundaries
and both Altirra SIO modes. The new checker covers eleven full cold/warm
frames, 256 exact distances, 256 presence values and eleven bitmap/layout
cases. Existing 24 graphics differentials, 16 qualifications, exhaustive
pixel lookup checks, 50 cache probes and 228 palette cases remain. Walking
still compares with the frozen old converter. Changed encounter colours
compare with direct pixel enumeration, whose old policy first reproduces
the frozen native frames. No game-state exclusion was added or relaxed.

Other corrected tooling assumptions: new snapshots copy the relocated TOP
constant during kernel injection; the profiler supports two lookup operands
and avoids eagerly looking up absent `table7`. Altirra capture waits for the
printed boot prompt before trusting kernel flags: its power-on RAM at those
addresses is not initialized. The preliminary failure picture records that
harness error, not a current rendering failure.

The normal `mm1.atr` and `mm1-colours.atr` are identical, 724,752 bytes,
test mode false, SHA-256
`4547214f2fbb6e42aeaf90ec3ad62a36de3042f0227f3d982e8366276c8e746f`.

Atari rows still cannot preserve every C64 cell colour simultaneously.
Some border/highlight colours remain approximations; palette RGB and sound
pacing are unchanged. PAL, Atari's OS ROM and physical hardware remain
untested. The fix targets the traced encounter layout; it does not claim
optimal pixel-weighted selection for every artwork in the game.
