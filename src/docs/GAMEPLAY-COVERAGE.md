# Expanded gameplay coverage — 2026-10-12

**Traced / checked.** Twelve new sessions match recordings of the original C64 in VICE and the host oracle. Atari800 matches memory at 141 additional checkpoints, checks the kernel's constant code/tables and display list, and compares the complete disk payloads. Together with the previous nine sessions this is **21 scripts / 257 Atari checkpoints**. There are **153 new settled C64 pictures**, each pixel equal to the oracle's drawing.

```sh
python3 tools/coverage_check.py --pictures --atari
python3 port/atari/lockstep.py tools/traces/boot-to-wilderness-travel.txt --altirra --sio
python3 -m unittest discover -s tests -v
```

Evidence: [C64 recordings](../test-artifacts/c64/README.md), [Atari logs and pictures](../test-artifacts/gameplay/README.md). All game files, rules, random-number routines and save layouts retain the existing operand-only redirection policy.

## Scenarios and fixture scope

Each script is `tools/traces/boot-to-NAME.txt`. Fixtures are explicit `poke` lines, replayed identically on all three machines; they change test state, not game instructions.

| NAME | Observed behavior | Fixture beyond the existing script's dice/input rules |
| --- | --- | --- |
| `direct-if` | IF's empty-vault alarm reads SPACE at `$89F0`; returns to the ordinary key wait | Position/facing at outdoor boundaries; pending native area-load destination changed to IF/D; position at its vault |
| `direct-eh` | EH's moving maze reads SPACE at `$86D2`, cancelling automatic movement; remains at 6,4 | Same loader/position fixtures, for EH/D |
| `direct-dp` | DP's floor spins; its direct `$890E` GETIN reads I and moves from 12,3 to 12,4 | Same loader/position fixtures, for DP/D |
| `combat-actions` | Wizz casts a level-1 spell and spends a spell point; Zenon shoots and downs a gremlin; Swifty exchanges into position 1 | None |
| `combat-item` | A flaming club casts its native power at a gremlin; charges 3 → 2 | Item `$18` and three charges in Wizz's first equipped slot |
| `encounter-retreat` | Retreat returns the party to the dungeon entrance, 14,0 | None |
| `encounter-bribe` | Gremlins say `NO RESPONSE`, then combat starts | None |
| `encounter-surrender` | Gremlins refuse prisoners, then combat starts | None |
| `chest-traps` | Wizz attempts detection (`MAGIC (N) TRAP (N)`); Swifty removes the trap and opens the chest without gas or injured characters | Swifty's robbery skill set to 100 for the successful removal branch |
| `chest-trap-failure` | Detection attempt followed by Swifty's failed removal; the gas trap springs | None |
| `death-and-raising` | Crag falls unconscious in combat, five companions win, then the gas trap kills him (condition `$C0`, zero HP); the native temple clears his condition, restores HP and charges gold | Crag starts at 1 HP; companions have enough HP to survive the diagnostic fight; positions shortened for the trip back to stairs/temple |
| `wilderness-travel` | Walk from RK/C through EJ/C to BB/C, win a kobold encounter, and continue to 14,2 | **None: stock party, real walking route** |

These are focused compatibility scenarios. Destination/position fixtures do not establish a natural playthrough to IF, EH or DP, and temple coverage does not establish every fatal condition or restoration price. Bribery/surrender cover the refused branches, not successful negotiations. EH's no-key movement and DP's default no-key turn remain useful follow-ups. All 55 areas / 818 event squares remain the long-term coverage target.

## Direct polls

The normal `press` step stops at the original key wait. A new `poll CALLER KEY` step, immediately after the triggering `press`, supplies a **nonzero** key at a specific call outside that wait. IF/EH call the wrapper at `$A087`; DP calls `$FFE4` directly.

VICE stops at the specified caller and fills the KERNAL buffer. The oracle does the same and verifies the instruction is a supported key call. The Atari harness arms its existing test wait **before releasing the triggering key**, selects the appropriate return address/stack depth, then restores all four operand bytes before releasing the direct key. This catches calls within the same emulator frame and avoids changing any game file or adding runtime bytes. The kernel's ordinary code checks apply again at the following mark; no comparison exclusion was added.

## A real pause stall found by the route

**Reproduced / fixed.** The first wilderness fight stalled on Atari while waiting in the original pause's `$C378` poll. The pause compares the KERNAL clock with an **exact** target. A GETIN screen conversion took longer than its remaining interval: at the timeout, the target was `$0B72`, but the clock had already passed it. The old nine scripts had not exercised this timing combination.

The kernel now holds the KERNAL clock while the CPU is on the extended bank for screen conversion (`PORTB` bit 4 clear). The original game is suspended then; its sound/IRQ sequencing and keyboard scan still run. Once conversion returns to main RAM, clock ticks resume and the pause reaches its target. The new route completes and all game-state comparisons remain exact, without patching the pause or adding timing exclusions.

Six volatile envelope-state bytes moved into unused TOP bytes `$FFE7–$FFEC`, making room for the seven-byte clock guard in UNDER. Constant-code checks still cover GETIN, the remaining TOP code/padding and vectors; only the explicit volatile variables are omitted from that kernel check. The ATR layout and extended-bank allocation did not grow.

## Screenshots without changing the scenario

The old `--settle` recorder reset the key-wait counters to zero after its delay. That intentionally creates a different deterministic session, and for these new routes it changed encounters and subsequent actions. The new `--settle-preserve` first records each mark's original counters on the oracle, then restores those exact bytes after the screenshot delay. Both the plain and settled versions must exercise the stated behavior; the settled trace and pixels must also match VICE. Older recordings keep their original settling convention.

## Second emulator

`lockstep.py --altirra [--sio]` now drives the same script and performs the same memory, kernel, display-list and disk comparisons through AltirraSDL's bridge. It reads/writes memory in bulk where possible and takes screenshots from that emulator. Startup clears only the test-hook flags before the boot code loads, because Altirra initializes RAM randomly; otherwise a random flag can falsely report that boot finished. A held test wait allows four-frame batches without adding passes of the game's random-number loop.

The wilderness route is the regression for the pause fix in Altirra, including serial transfers. Broader Altirra lockstep, Atari OS ROM, PAL and physical-hardware coverage remain separate work.

The reusable raw-step/position exploration helper is `tools/scenario_explore.py`: it preserves the script prefix, records explicit fixtures, and saves a full candidate only after its steps succeed. Its candidates still require VICE and Atari verification.

Atari photographs are taken at a held first input poll. Some text snapshots still show the preceding action message while the settled C64 photograph already shows the next character's options. The RAM comparisons include the current text, but do not establish exact snapshot publication timing; that presentation follow-up remains open.
