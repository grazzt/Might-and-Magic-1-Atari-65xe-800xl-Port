#!/usr/bin/env python3
"""Audit game colour writers for the direct-display 65XE profile.

Record instruction identity and actual targets, including indirect writes.
Host-only; does not change disks or game instructions. The title is excluded.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import disassemble
import mos6502
import oracle

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts', nargs='*', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT/'build/atari65xe/colour-writers.json')
    args = parser.parse_args()
    modules, _, _ = disassemble.analyse()
    loaded = {(side, block, m.base): m for m in modules for side, block in m.blocks}
    resident = [m for m in modules if m.kind == 'resident']
    writes = {}

    class Audit(oracle.Oracle):
        def power_on(self):
            self.active = False
            super().power_on()
            self.cpu.audit_owner = self
            self.handlers[0x2000] = lambda: setattr(self, 'active', True)
            self.cpu.hooks[0x2000] = 1

        def identify(self, pc):
            for start, end, key in reversed(self.loaded):
                if start <= pc < end:
                    module = loaded.get(key)
                    if module and pc in module.instructions:
                        return module
            return next((m for m in resident if pc in m.instructions), None)

    def record(cpu, pc, address):
        player = cpu.audit_owner
        if not player.active:
            return
        module = player.identify(pc)
        if module is None:
            raise RuntimeError(f'Unidentified colour writer ${pc:04X} to ${address:04X}')
        instruction = module.instructions[pc]
        key = module.name, pc
        if key not in writes:
            raw = module.data[pc-module.base:pc-module.base+instruction.length]
            writes[key] = {'module': module.name, 'pc': f'${pc:04x}',
                           'instruction': f'{instruction.mnemonic} {instruction.mode}',
                           'before': list(raw), 'targets': Counter()}
        writes[key]['targets'][address] += 1

    original_write, original_run = mos6502._WRITE, mos6502._RUN[False]
    mos6502._WRITE = ('if 0xCC00 <= ea < 0xD000 or 0xD800 <= ea < 0xDC00:\n'
                      '    record(self, audit_pc, ea)\n' + original_write)
    source = mos6502._source(False).replace('        op = mem[pc]',
                                           '        audit_pc = pc\n        op = mem[pc]')
    namespace = {'repeat': mos6502.repeat, 'CPUError': mos6502.CPUError, 'record': record}
    exec(compile(source, '<colour write audit>', 'exec'), namespace)
    mos6502._RUN[False] = namespace['run']
    scripts = [p.resolve() for p in args.scripts] or sorted((ROOT/'tools/traces').glob('boot-to-*.txt'))
    try:
        for script in scripts:
            player = Audit()
            player.play(script.read_text().splitlines(), pictures=False)
            print(script.stem, 'complete', flush=True)
    finally:
        mos6502._WRITE, mos6502._RUN[False] = original_write, original_run
    report = []
    for key, entry in sorted(writes.items()):
        targets = entry.pop('targets')
        entry['first_target'], entry['last_target'] = f'${min(targets):04x}', f'${max(targets):04x}'
        entry['unique_targets'], entry['writes'] = len(targets), sum(targets.values())
        report.append(entry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'scripts': [str(p.relative_to(ROOT)) for p in scripts],
                                    'writers': report}, indent=2)+'\n')
    print(f'{len(report)} instruction sites: {args.out}')


if __name__ == '__main__':
    main()
