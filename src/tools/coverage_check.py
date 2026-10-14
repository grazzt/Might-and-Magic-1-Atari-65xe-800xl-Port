#!/usr/bin/env python3
"""Check the expanded gameplay scenarios against their C64 recordings.

  python3 tools/coverage_check.py [--pictures] [--atari] [--out DIR]

Position, destination, health, equipment and robber-skill fixtures are written
in the scripts. Wilderness travel and encounter choices use the stock party.
The checks assert the intended behavior as well as reference trace equality.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from c64 import ROOT
from c64_trace import settled
import c64_screen
import oracle

CASES = ('direct-if', 'direct-eh', 'direct-dp', 'combat-actions', 'combat-item',
         'chest-traps', 'chest-trap-failure', 'encounter-retreat', 'encounter-bribe',
         'encounter-surrender', 'death-and-raising', 'wilderness-travel')


def verify(name, player, marks):
    """Assert that a passing trace exercised the behavior its name promises."""
    text = '\n'.join(line for event in player.events for line in event.get('text', []))
    def require(condition, message):
        if not condition:
            raise AssertionError(f'{name}: {message}')
    if name == 'direct-if':
        mem = marks['if-direct-key']
        require('EMPTY VAULT, ALARM!' in text and mem[0x0371] == 0x20, 'vault key was not read')
    elif name == 'direct-eh':
        mem = marks['eh-direct-key']
        require(mem[0x3b:0x3d] == b'\x06\x04' and mem[0x0371] == 0x20,
                'maze key did not cancel the automatic movement')
    elif name == 'direct-dp':
        mem = marks['dp-direct-key']
        require('THE FLOOR SPINS!' in text and mem[0x3b:0x3d] == b'\x0c\x04',
                'spinning floor did not dispatch the direct I key')
    elif name == 'combat-actions':
        require(marks['spell-cast'][0x0aab] == 4, 'spell did not spend a spell point')
        require('SHOOTS' in text, 'bow shot was not made')
        require(marks['bow-fired'][0x0684:0x0691].startswith(b'CRAG THE HACK') and
                marks['positions-exchanged'][0x0684:0x0691].startswith(b'SWIFTY SARG'),
                'exchange did not move Swifty to position 1')
    elif name == 'combat-item':
        require(marks['item-target'][0x0acc] == 3 and marks['item-used'][0x0acc] == 2,
                'charged item was not used on a target')
    elif name == 'chest-traps':
        require('MAGIC (N)  TRAP (N)' in text and 'IT OPENS!' in text and 'GAS!!' not in text and
                all(marks['trap-removed'][base + 0x3f] == 0 for base in range(0x0800, 0x0b00, 128)),
                'detection and successful removal were not exercised')
    elif name == 'chest-trap-failure':
        require('MAGIC (N)  TRAP (N)' in text and 'GAS!!' in text,
                'failed removal did not spring the gas trap')
    elif name == 'encounter-retreat':
        require(marks['retreat-result'][0x3b:0x3d] == b'\x0e\x00', 'retreat did not return to the entrance')
    elif name == 'encounter-bribe':
        require('NO RESPONSE' in text and marks['bribe-result'][0x0389] == 0,
                'refused bribe did not enter combat')
    elif name == 'encounter-surrender':
        require("THE MONSTERS DON'T TAKE PRISONERS!" in text and marks['surrender-result'][0x0389] == 0,
                'refused surrender did not enter combat')
    elif name == 'death-and-raising':
        dead, raised = marks['one-character-dead'], marks['raised']
        require(dead[0x083f] == 0xc0 and dead[0x0833:0x0835] == b'\0\0', 'Crag did not die')
        require(all(dead[base + 0x3f] & 0xc0 != 0xc0 for base in range(0x0880, 0x0b00, 128)),
                'a companion also died')
        require(raised[0x083f] == 0 and raised[0x0833:0x0835] == raised[0x0835:0x0837],
                'temple did not restore condition and health')
        require(int.from_bytes(raised[0x0839:0x083c], 'little') <
                int.from_bytes(marks['dead-at-temple'][0x0839:0x083c], 'little'), 'restoration did not cost gold')
    elif name == 'wilderness-travel':
        require({'sector-ej', 'sector-bb', 'travel-victory-1', 'forest-after-battle'} <= marks.keys(),
                'route did not visit both new sectors and win its encounter')
        require(marks['forest-after-battle'][0x3b:0x3d] == b'\x0e\x02', 'route did not finish in BB')


def check(pictures=False, atari=False, out=None):
    report = {}
    for name in CASES:
        script = ROOT / f'tools/traces/boot-to-{name}.txt'
        lines = script.read_text().splitlines()
        player, marks = oracle.Oracle(), {}
        player.play(lines, pictures=False, on_mark=lambda mark: marks.__setitem__(mark, player.machine.ram_image()))
        reference = json.loads((ROOT / f'test-artifacts/c64/trace-{name}/trace.json').read_text())
        difference = oracle.compare(player.events, reference)
        if difference:
            raise AssertionError(f'{name}: differs from VICE: {difference}')
        verify(name, player, marks)
        row = {'marks': len(marks), 'reference_equal': True, 'behavior_checked': True}
        if pictures:
            folder = ROOT / f'test-artifacts/c64/settled-{name}'
            visual, images, visual_marks = oracle.Oracle(), {}, {}
            def visual_mark(mark):
                images[mark] = visual.picture()
                visual_marks[mark] = visual.machine.ram_image()
            counters = {mark: memory[0x2d:0x2f] for mark, memory in marks.items()}
            visual.play(settled(lines, counters=counters), pictures=False, on_mark=visual_mark)
            verify(name, visual, visual_marks)
            difference = oracle.compare(visual.events, json.loads((folder / 'trace.json').read_text()))
            if difference:
                raise AssertionError(f'{name}: settled trace differs: {difference}')
            for mark, pixels in images.items():
                count, where = c64_screen.differences(c64_screen.vice_picture(folder / f'{mark}.png'), pixels)
                if count:
                    raise AssertionError(f'{name} {mark}: {count} C64 pixels differ; {where[:3]}')
            row['pictures_equal'] = len(images)
        if atari:
            run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py', script, '--pictures'],
                                 capture_output=True, text=True, timeout=300)
            if run.returncode:
                raise AssertionError(f'{name}: Atari failed:\n{run.stdout[-4000:]}{run.stderr[-2000:]}')
            row['atari_equal'] = True
            if out:
                destination = out / name
                destination.mkdir(parents=True, exist_ok=True)
                (destination / 'atari.txt').write_text(run.stdout)
                for mark in marks:
                    image = ROOT / f'build/atari/lockstep/{mark}.png'
                    if image.exists():
                        shutil.copyfile(image, destination / f'{mark}-atari.png')
        report[name] = row
        print(f'ok: {name}: {row}', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pictures', action='store_true')
    parser.add_argument('--atari', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/coverage/check')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = check(args.pictures, args.atari, args.out)
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
