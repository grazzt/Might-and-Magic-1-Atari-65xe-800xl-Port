# Held Ctrl+A in combat — 2026-10-11

**Checked:** the old Atari keyboard handler accepted only key-down edges.
Every sample equal to `last_code` returned immediately, so a continuous
Ctrl+A hold produced one command. The original game enables all-key repeat
and expects the KERNAL scanner to generate further keys. The port now obeys
that repeat setting, initial delay and repeat counter.

## Original behaviour

**Read / checked against ROM execution:**

- The original `GO` inn program stores `$80` at `$028A` (`RPTFLAG`), enabling
  all-key repeat. This setting remains enabled during play and combat.
- KERNAL `901227-03` scans at `$EA87`. Its repeat decision uses `$028A`,
  initial delay `$028C` and repeat-rate counter `$028B`. A new key initializes
  delay to `$10`; repeats reload the rate counter with four and enqueue only
  if the keyboard buffer is empty. Existing startup rate state is retained.
- The unchanged game reader `$C648` may extend the delay to `$30` when a new
  key is returned. Its effect-5 exception swallows Ctrl+A while that sound
  plays; repeat must preserve that exception, not bypass the game reader.
- Combat's command table at `$209C` includes PETSCII `$01`. Dispatch at
  `$20F9` selects attack if available, otherwise shooting, otherwise block.
  It does not depend on a new press edge or implement holding on its own.

`keyboard_check.py --unit` executes the original KERNAL ROM with a simulated
physical CIA matrix (A plus CTRL), then the original game reader. The new
Atari routine matches its letter-key queue, held CTRL flag and counters for
eight cases: Ctrl+A, plain A, repeat disabled/default, backpressure, effect 5,
release/repress and changing keys. With immediate application consumption,
the ordinary game-reader case returns at scans 0, 53, 57, 61…; effect 5
swallows the same raw keys at scans 0, 21, 25, 29…. These are eligible scan
counts, not a promise of four frames per character: drawing, pauses and
interrupt masking also determine actual action times.

The new first-poll trace `boot-to-ctrl-attack.txt` gives six `$01` commands.
VICE and the oracle match all 149 events; the Atari matches its ten game-state
checkpoints. That proves original command semantics independently of the
normal physical-hold tests. Default special-key repeat and SHIFT translation
remain the earlier port's behaviour; this implements the game-enabled
all-key repeat path, not a complete replacement for every KERNAL key policy.

## Implementation

**Checked:** `keyboard` still accepts fresh keys immediately. If a held key
matches `last_code`, it tests bit 7 of `$028A`, counts down `$028C/$028B`,
reloads the rate to four and translates/enqueues the key through the same
PETSCII/CTRL path. A repeat enters only an empty buffer. Key release resets
`last_code`, stops new repeat generation and permits an immediate fresh press.
One already queued key may still be consumed after release, as on the C64.
The original game's buffer flush, pauses, sound exceptions, RNG and attack
code are unchanged. Scripted first-poll keys do not pass through repeat.

Space was tight, so the 25-byte native test trampoline now shares the disk
loader's 128-byte buffer while SIO is idle. Each buffered disk read fills all
128 bytes before using them; sound tests and Altirra's one-shot IRQ probe
finish before another transfer. The mutable buffer is already excluded from
immutable-kernel checks. `probe_scratch` remains an explicit label.

Move the 16-byte matrix histogram scratch to EXT, where palette code already
runs, and move `row`/`cells` to UNDER. This fits 39 extra instruction bytes
without a new bank or new repeat state; the C64's existing counters hold it.
Net occupied growth: UNDER 0, EXT 14, LOADER/EXT2 0, after reclaiming the
dedicated 25-byte test reserve. Spare LOADER 8, UNDER 1, EXT 0, EXT2 10.
Display padding, 56 boot sectors and 35 redirected game instructions remain
unchanged. Differential helpers migrate previous row palettes when injecting
kernels with different label layouts, in both directions, before comparing
old/new output; they do not disable cache invalidation checks.

## Reproduction and checks

**Checked in ordinary Atari800 input:** the old named palette build accepts
one combat command during a 600-frame hold; a new press advances another
character, proving input was connected. The new build accepts **18 combat
commands**, visits all six characters over three rounds and wins the fight.
The observer at `$0E45` emulates the displaced JSR, stack and six CPU cycles;
it exists only in emulator RAM and is removed afterwards. No script key is
delivered during the hold. Releasing stops additional events after allowing
the pending key to drain.

**Checked in Altirra:** real `KEYRAW A down ctrl`, with sampled game state,
visits all six characters in rounds 1–3 and wins; releasing clears the held
state and no more keys fill the buffer. Both endpoint pictures were inspected
and show the victory/250 XP text correctly.

**Checked:** all 85 tests pass in 155.824 seconds with Altirra socket access.
Nine lockstep scripts / 116 checkpoints and three exact saves pass; sounds,
keyboard play, both disk modes, palette/graphics/cache checks remain valid.
The two new regressions check the original ROM scanner/reader and a real
continuous combat hold. No comparison exclusions or game-file edits added.
Physical holds have elapsed-time RNG inputs and are not compared directly
with the first-poll oracle; that separate scripted trace remains deterministic.
PAL, Atari ROM/hardware and the prior SHIFT limitation remain untested/open.

Run these sequentially because they share build output:

```bash
python3 port/atari/keyboard_check.py --unit --out build/atari/keyboard-unit
python3 port/atari/keyboard_check.py --battle --out build/atari/held-combat
python3 port/atari/keyboard_check.py --battle --altirra --out build/atari/held-altirra
python3 -m unittest discover -s tests
python3 port/atari/build.py
```

For the old-build reproduction, add `--baseline` while the previous
`build/atari/mm1-palette-fast.atr` is available. The helper restores the current
normal playable ATR in `finally`, including failed captures. New playable
disk: `build/atari/mm1-held-keys.atr`, identical to normal `mm1.atr`, 732,944
bytes, test mode false. SHA-256:
`02467f68ec64a75508ee3fe86dc2054bd25168ac91dbcdfd527a4d91864c816c`.
[Raw evidence and reference trace](../test-artifacts/keyboard-repeat/README.md).
