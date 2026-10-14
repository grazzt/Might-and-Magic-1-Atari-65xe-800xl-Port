#!/usr/bin/env python3
"""Decode and record MM1's nine effects using its original C64 sound routines.

python3 tools/c64_sound.py --out test-artifacts/sound/c64-effects.json
Frame numbers use the oracle's PAL clock, not a cycle-exact SID emulator.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

import oracle

SID_CLOCK = 985248                 # PAL C64 reference
POKEY_CLOCK = 1789790              # NTSC Atari target


def at_menu():
    game = oracle.Oracle()
    game.play((oracle.ROOT / 'tools/traces/boot-to-menu.txt').read_text().splitlines(), pictures=False)
    return game


def decode(ram):
    """Seven voice registers, waveform base, then (frequency, timer, gate).
    A zero frequency LOW byte ends the effect; duration is timer+1 ticks.
    """
    effects = []
    for number in range(1, 10):
        pointer = ram[0xc6a3 + 2 * number] | ram[0xc6a4 + 2 * number] << 8
        setup = list(ram[pointer:pointer + 8])
        steps, cursor = [], pointer + 8
        while ram[cursor]:
            steps.append({'frequency': ram[cursor] | ram[cursor + 1] << 8,
                          'ticks': ram[cursor + 2] + 1, 'gate': ram[cursor + 3]})
            cursor += 4
            if cursor - pointer > 1024:
                raise ValueError(f'Effect {number} has no terminator')
        effects.append({'effect': number, 'address': pointer, 'setup': setup, 'steps': steps})
    return effects


def pitches(effects):
    frequencies = {s['frequency'] for e in effects for s in e['steps']}
    frequencies.update(e['setup'][0] | e['setup'][1] << 8 for e in effects)
    return sorted(frequencies - {0})


def divisor(frequency):
    hz = SID_CLOCK * frequency / 2**24
    return round(POKEY_CLOCK / (2 * hz)) - 7


def call(game, address, a=0):
    """Invoke an original subroutine, leaving the running program's PC intact.
    The temporary return hook needs no code or data injected into the game.
    """
    cpu = game.cpu
    pc, flags = cpu.pc, cpu.p
    cpu.fi = 4
    cpu.push(0x02)
    cpu.push(0xfe)                       # RTS to $02FF, held by an observation hook
    cpu.pc, cpu.a, cpu.resume_at = address, a, -1
    game.run_until(0x02ff, 100000)
    cpu.pc, cpu.p, cpu.resume_at = pc, flags, -1


def record():
    result = []
    for effect in range(1, 10):
        game = at_menu()
        call(game, 0xc62f)
        description = decode(game.machine.ram_image())[effect - 1]
        game.machine.sid_trace = []
        call(game, 0xc557, effect)
        game.run_until(0xc62f, 20000000)   # real raster IRQ drives the whole sequence
        game.run_until(0xc609, 10000)      # include the final register clear
        writes = game.machine.sid_trace
        first_frame, first_cycle = writes[0]['frame'], writes[0]['cycle']
        for write in writes:
            write['frame'] -= first_frame
            write['cycle'] -= first_cycle
        result.append(dict(description, writes=writes))
    return {'clock': 'oracle PAL; approximate instruction timing', 'effects': result}


def verify_vice(reference, out):
    """Independent SID-write trace points on VICE's original, true-drive game.
    CPU/stack setup invokes each original routine; no original code is patched.
    """
    from c64 import command
    from c64_trace import monitor_script
    with tempfile.TemporaryDirectory(prefix='mm1-sid-vice-') as folder:
        folder = Path(folder)
        cmd, env = command(headless=True, state=folder)
        lines = (oracle.ROOT / 'tools/traces/boot-to-menu.txt').read_text().splitlines()
        commands, _ = monitor_script([line for line in lines if not line.startswith('mark ')],
                                      out, folder / 'disks', 'vice-sid-monitor.txt')
        commands.pop()                  # replace quit with the isolated effect probes
        commands += ['delete']
        sites = {0xc579: None, 0xc612: 0, 0xc618: 1, 0xc627: 4, 0xc633: None}
        commands += [f'trace exec ${pc:04x}' for pc in sites]
        for effect in reference['effects']:
            commands += ['> $03a0 $00', '> $00c6 $00', '> $01fe $3a $0e',
                         f"r pc=$c557,a=${effect['effect']:02x},sp=$fd",
                         'until $c62f', 'until $c609', 'until $0e3b']
        commands += ['quit']
        playback = folder / 'sound.mon'
        playback.write_text('\n'.join(commands) + '\n')
        with (out / 'vice.log').open('w') as log:
            subprocess.run(cmd + ['-warp', '-moncommands', str(playback)], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    raw = (out / 'vice-sid-monitor.txt').read_text()
    pattern = r'^\.C:(c579|c612|c618|c627|c633) .* A:([0-9a-f]{2}) .* Y:([0-9a-f]{2}) SP:.*\s+(\d+)$'
    writes = []
    for pc, a, y, cycle in re.findall(pattern, raw, re.MULTILINE | re.IGNORECASE):
        register = sites[int(pc, 16)]
        writes.append({'register': int(y, 16) if register is None else register,
                       'value': int(a, 16), 'cycle': int(cycle), 'frame': int(cycle) // oracle.FRAME})
    result, offset = [], 0
    for effect in reference['effects']:
        part = writes[offset:offset + len(effect['writes'])]
        expected = [(w['register'], w['value']) for w in effect['writes']]
        if [(w['register'], w['value']) for w in part] != expected:
            raise AssertionError(f"VICE SID writes differ for effect {effect['effect']}; see {out}")
        start_cycle, start_frame = part[0]['cycle'], part[0]['frame']
        for write in part:
            write['cycle'] -= start_cycle
            write['frame'] -= start_frame
        if abs(part[-1]['frame'] - effect['writes'][-1]['frame']) > 1:
            raise AssertionError(f"VICE duration differs for effect {effect['effect']}")
        result.append({'effect': effect['effect'], 'writes': part})
        offset += len(part)
    assert offset == len(writes), 'Unexpected SID writes after the last effect'
    (out / 'vice-effects.json').write_text(json.dumps({'effects': result}, indent=2) + '\n')
    print(f'VICE: all {len(writes)} SID writes equal the oracle; duration within one PAL frame')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=oracle.ROOT / 'test-artifacts/sound/c64-effects.json')
    parser.add_argument('--vice', action='store_true', help='also verify the register sequences in VICE')
    args = parser.parse_args()
    result = record()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    if args.vice:
        verify_vice(result, args.out.parent)
    for effect in result['effects']:
        print(f"Effect {effect['effect']}: {len(effect['steps'])} steps, "
              f"{len(effect['writes'])} writes, {effect['writes'][-1]['frame']} PAL frames")


if __name__ == '__main__':
    main()
