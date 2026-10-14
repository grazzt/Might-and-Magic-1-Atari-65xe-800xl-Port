# Sound: C64 effects on Atari POKEY

2026-10-11. **Traced** on the host oracle and VICE; **checked** on Atari800
and AltirraSDL. Implementation: `port/atari/src/kernel.s`, generated tables in
`port/atari/build.py`. The original game code and sound data are unchanged.

The title's three-voice tune is a separate translator in the title stage,
with its own pitch table (NTSC clock) and channels 3 and 4 beside the joined
pair: [TITLE.md](TITLE.md), "The tune". Nothing below changed for it.

## What the original game writes

Every effect enters through `$A02D`, a jump to `$C557`, with effect 1–9 in A.
The pointer table is `$C6A3 + 2*effect`. Entry 0 overlaps the saved IRQ vector;
it is not an effect. Sound-off is `$03A1 != 0`. `$03A0` means playing, `$03A4`
keeps the effect number, and `$29/$2A` point to its next step.

An effect starts with eight bytes: seven voice-1 SID registers `$D400–$D406`
(frequency, pulse width, control, attack/decay, sustain/release), then its
waveform base. The code copies the first seven with `STA $D400,Y` at `$C579`.
This includes pulse width and envelopes, absent from the earlier sound inventory.

Each following step has four bytes: frequency low, frequency high, timer, gate.
`sound_step` at `$C60C` writes frequency and waveform-base OR gate to `$D404`.
The **low byte alone** being zero is the terminator. The IRQ decrements the
timer and steps when it becomes negative: a stored timer N lasts N+1 sound ticks.
`sound_off` at `$C62F` clears `$D400–$D407` and `$03A0`. `$D418` is set to `$0F`
when the game's interrupt is installed. Only voice 1 is used.

| Effect | Data address | Waveform | Steps | Total sound ticks | SID writes |
| --- | --- | --- | --- | --- | --- |
| 1 | `$C84C` | triangle | 2 | 22 | 21 |
| 2 | `$C85D` | pulse | 2 | 12 | 21 |
| 3 | `$C6B7` | saw | 6 | 88 | 33 |
| 4 | `$C6D8` | saw | 10 | 90 | 45 |
| 5 | `$C709` | pulse | 48 | 506 | 159 |
| 6 | `$C7D2` | pulse | 12 | 338 | 51 |
| 7 | `$C80B` | triangle | 14 | 54 | 57 |
| 8 | `$C86E` | pulse | 7 | 177 | 36 |
| 9 | `$C893` | pulse | 10 | 114 | 45 |

There are 21 distinct nonzero frequency words, including setup values.
`tools/c64_sound.py` decodes them and records every SID write with cycle and
PAL frame number. The CPU exposes the instruction's `write_cycle` to the
recorder; its public `cycles` field can be stale between event/hook boundaries.
The trace is optional and separate from gameplay events. SID reads retain the
oracle's original behavior; the saved register bytes are observational state.

**Checked key rules:** ordinary effects stop on a key; effect 5 consumes CTRL-A
without stopping but stops on other keys; effect 6 stops only on RETURN; effect
9 continues on keys. The game's original `$C648` reader still implements this.

## Translation and ownership

`irq_tail` calls `sound_update` after the original game IRQ. Channels 1+2 are
joined with `AUDCTL=$50`; channel 1 has zero volume and channel 2 produces a
pure square tone (`AUDC2=$A0 | volume`). Pitch tables are generated from the
original nine effects, rather than a second hand-written tune list:

```
SID Hz = 985248 * SID_frequency / 16777216
POKEY divisor = round(1789790 / (2 * SID_Hz)) - 7
AUDF1 = divisor low byte; AUDF2 = divisor high byte
```

The linked fast-clock timer period is divisor+7 cycles and a square wave takes
two periods. **Read:** [Altirra Hardware Reference Manual](https://www.virtualdub.org/downloads/Altirra%20Hardware%20Reference%20Manual.pdf),
POKEY timer period/linking and AUDCTL. **Checked:** all 21 generated pitches
are within 0.1% of the PAL SID reference pitch. `STIMER` is written only when
the pitch changes or the cache is invalidated after SIO, avoiding a phase reset
on every frame. An unknown frequency fails silent rather than keeping an old note.

The kernel approximates attack, decay/sustain and release at one update per VBI.
It keeps an 8-bit level (0–240), with its high nibble as the 4-bit POKEY volume.
Rising gate attacks; falling gate releases rather than muting immediately.
Decay approaches the SID sustain nibble. Rate tables use the envelope times in
the [original MOS 6581 datasheet, Table 2](https://myoldcomputer.nl/Files/mos_6581_sid.pdf),
rounded to an NTSC frame and a linear step. This is an approximation, not SID
emulation: triangle/saw/pulse all become square tones, pulse width is ignored,
and decay/release are linear. The game's master volume normally remains 15;
zero mutes, and a lower value caps output volume. Stopped effects and sound-off
mute at the next eligible VBI, within one frame during ordinary play.

SIO temporarily owns POKEY. `read_sector` silences channels 1+2 before switching
the OS in. After switching the OS out, `sound_restore` restores `AUDCTL=$50`,
`SKCTL=3` for the keyboard, silences all four channels and invalidates the pitch
cache. The next eligible VBI reinstates the game's note. No game sound pointer,
timer or option byte is changed by the translator. It uses no game zero page.
The row DLI's instruction sequence is unchanged.

**Memory checked:** 366 additional bytes occupy existing kernel padding:
93 in LOADER (84-byte pitch table plus 9 bytes of SIO calls/muting), 241 in
UNDER (state, code, VBI call), 32 in TOP (envelope tables). The segment sizes,
56 boot sectors and extended-bank allocation stay unchanged. Spare bytes:
8 in LOADER, 72 in UNDER, 17 before GETIN in TOP after sound alone. The later
display work leaves 61 in UNDER; see [SPEED.md](SPEED.md). `build.fixed()` now protects
both generated sound tables as well as the translator code. No comparison
exclusions or game operand redirections were added: still 35 instructions,
70 changed disk bytes.

## Evidence and reproduction

```bash
python3 tools/c64_sound.py --vice
python3 port/atari/sound_check.py
python3 -m unittest discover -s tests
python3 port/atari/build.py               # restore the normal playable build
```

- **VICE vs oracle:** all 468 SID register/value writes equal, in order, for all
  nine effects. Durations differ by at most one PAL frame because capture phase
  and oracle instruction timing differ. `test-artifacts/sound/` retains both
  complete records and the VICE monitor log. No claim of sample-identical SID audio.
- **Atari800:** all nine original effect routines run to completion. Generated
  PCM WAVs have ranges 12,994–13,330 (signed 16-bit samples); every audible frame
  has the expected pitch registers, and every effect ends silent. Gate-off release,
  all six key interruption cases and the sound-off option are checked. WAVs and
  the report are generated under `build/atari/sound/`, not added to the source tree.
- **AltirraSDL:** a one-shot IRQ probe runs original effect 3 and checks pitch
  and volume; C then stops it through the original key reader. The existing
  save/restart/town walk checks POKEY/keyboard restoration at eight stops, both
  with disk patching and with real serial transfers. PCM is recorded with the
  Atari800 harness; the Altirra bridge exposes registers, not a PCM recording API.
- **Full regression:** 79 tests passed after sound; 81 pass with the later
  display-transition tests, including eight scripts/106 checkpoints,
  three identical saves, kernel integrity, keyboard, display and both Altirra
  disk modes. Original inputs and the sibling project are unchanged.

The effect probes use temporary code in unused kernel padding, saving registers
and flags on Atari800 and restoring a one-shot IRQ vector on Altirra. This test
code is not in the disk build. Returning to a held key-wait branch without saving
flags caused a false silence result: it made the branch consume an invented key.

## Remaining presentation limits

Pitch is calibrated for the current NTSC Atari and PAL C64 reference. PAL Atari,
Atari's own OS and physical hardware remain untested. Text mode advances sound
once per Atari frame (about 60 Hz, versus 50 Hz on the reference). In split mode
the existing fake-raster alternation reaches `$C5FC` every second VBI, whereas
the C64 receives two raster IRQs per frame and reaches it once per frame:
**read** from the handler, not corrected or measured here. The translator follows
the original game's existing Atari sequencing; matching real-time effect pacing
in every display mode remains follow-up work. Play speed is now measured in
[SPEED.md](SPEED.md).

**2026-10-12 layout/timing follow-up:** six envelope-state bytes moved to unused TOP bytes `$FFE7–$FFEC`. The new clock guard holds KERNAL jiffies during screen conversion; original sound IRQ sequencing and POKEY envelope updates continue. The nine-effect translator/pitch tables are unchanged. [Reason and checks](GAMEPLAY-COVERAGE.md).
