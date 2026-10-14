#!/usr/bin/env python3
"""Host-only memory survey for a possible 64 KB Atari build.

Runs the existing boot-to-* scenarios, recording CPU accesses only after the
game's startup stub is entered. Includes operand fetches, stack operations,
indirect pointers, chip accesses and hooked disk writes. Does not establish
whole-game liveness. Outputs go to build/atari/64k-survey by default.
"""
import argparse
import hashlib
import json
from pathlib import Path

import oracle

ROOT = Path(__file__).resolve().parents[1]


def ranges(flags, first, last, mask, minimum=1):
    start = None
    result = []
    for address in range(first, last + 2):
        unused = address <= last and not flags[address] & mask
        if unused and start is None:
            start = address
        elif not unused and start is not None:
            if address - start >= minimum:
                result.append({'first': f'${start:04X}', 'last': f'${address-1:04X}',
                               'bytes': address - start})
            start = None
    return result


class AccessMemory:
    """Wrap CPU memory, leaving the oracle's observation reads uncounted."""
    def __init__(self, memory, owner):
        self.memory, self.owner = memory, owner

    def __getitem__(self, address):
        if isinstance(address, int) and self.owner.active:
            self.owner.flags[address] |= 1
        return self.memory[address]

    def __setitem__(self, address, value):
        if isinstance(address, int) and self.owner.active:
            self.owner.flags[address] |= 2
        self.memory[address] = value


class Survey(oracle.Oracle):
    def __init__(self):
        self.flags = bytearray(65536)
        self.active = False
        self.entries = 0
        super().__init__()

    def power_on(self):
        self.active = False
        super().power_on()
        self.cpu.mem = AccessMemory(self.machine.mem, self)
        original_read, original_special = self.cpu.io_read, self.cpu.special

        def read(address):
            if self.active:
                self.flags[address] |= 1
            return original_read(address)

        def special(address, value):
            if self.active:
                self.flags[address] |= 2
            return original_special(address, value)

        self.cpu.io_read, self.cpu.special = read, special
        self.handlers[0x2000] = self.enter
        self.cpu.hooks[0x2000] = 1

    def enter(self):
        if not self.active:
            self.active = True
            self.entries += 1

    def disk_read(self):
        if self.active:
            p = self.mem[0x9d00:0x9d04]
            address, length = p[0] | p[1] << 8, p[2] | p[3] << 8
            for index in range(length):
                self.flags[(address + index) & 65535] |= 4
        super().disk_read()


def layout():
    rows = []
    for row in range(25):
        address = 0xe000 + row * 320
        offset = address % 1024
        crossing = offset + 320 > 1024
        rows.append({'row': row, 'address': f'${address:04X}', 'offset': offset,
                     'crosses_1k': crossing,
                     'cells_before_boundary': (1024-offset)//8 if crossing else None})
    # Independent exhaustive check of a smaller replacement for colour_tables:
    # one 16-entry nibble table for each of the sixteen pair mappings.
    nibble = [((0, key & 3, key >> 2, 3)[v >> 2] << 2)
              | (0, key & 3, key >> 2, 3)[v & 3]
              for key in range(16) for v in range(16)]
    checked = 0
    for key in range(16):
        pairs = (0, key & 3, key >> 2, 3)
        for value in range(256):
            reference = sum(pairs[(value >> shift) & 3] << shift for shift in (0, 2, 4, 6))
            compact = nibble[key*16 + (value >> 4)] << 4 | nibble[key*16 + (value & 15)]
            assert reference == compact
            checked += 1
    return {'rows': rows, 'lower_crossing_rows': [r['row'] for r in rows if r['crosses_1k']],
            'upper_crossing_rows': [r['row'] for r in rows[:16] if r['crosses_1k']],
            'full_converted_screen': 9*1024, 'screen_pixel_bytes': 25*320,
            'screen_padding': 9*1024-25*320, 'upper_bitmap_bytes': 16*320,
            'lower_bitmap_bytes': 25*320,
            'crossing_rows_visible_at_once': sum(r['crosses_1k'] for r in rows),
            'crossing_row_buffer_blocks': 2, 'crossing_row_buffer_bytes': 2*1024,
            'nibble_map_bytes': len(nibble), 'nibble_map_cases_checked': checked}


def targeted(out):
    """Check the encounter's code backup and identify indirect low-RAM users."""
    import mos6502
    namespace = {'repeat': mos6502.repeat, 'CPUError': mos6502.CPUError}
    source = mos6502._source(False).replace('        op = mem[pc]',
                                            '        self.audit_pc = pc\n        op = mem[pc]')
    exec(compile(source, '<survey pc>', 'exec'), namespace)
    original_run = mos6502._RUN[False]
    mos6502._RUN[False] = namespace['run']
    try:
        player = oracle.Oracle()
        player.play(['until $41ab', 'key 5f', 'until $2000'], pictures=False)
        readers, writers, capture = {}, {}, {}

        class Watched:
            def __getitem__(self, address):
                if isinstance(address, int) and 0x0800 <= address < 0x0b00:
                    readers.setdefault(player.cpu.audit_pc, address)
                return player.machine.mem[address]

            def __setitem__(self, address, value):
                if isinstance(address, int) and 0x0800 <= address < 0x0b00:
                    writers.setdefault(player.cpu.audit_pc, address)
                player.machine.mem[address] = value

        player.cpu.mem = Watched()

        def saved():
            if player.cpu.x == 0x1f:
                capture['resident_before'] = player.machine.ram_image()[0x4000:0x5f00]

        def restore():
            if 'resident_before' in capture:
                backup = player.machine.ram_image()[0xe000:0xff00]
                capture['equal'] = backup == capture['resident_before']
                capture['bytes'] = len(backup)

        for pc, handler in ((0x2456, saved), (0x26c9, restore)):
            player.handlers[pc] = handler
            player.cpu.hooks[pc] = 1
        lines = (ROOT/'tools/traces/boot-to-fight-and-save.txt').read_text().splitlines()
        start = next(i for i, line in enumerate(lines)
                     if line.split('#')[0].strip() == 'wait $1000000')
        player.play(lines[start:], pictures=False)
        assert capture.get('equal') is True and capture.get('bytes') == 7936
        assert 0x795d in writers and 0x3508 in readers
        result = {'low_memory_reader_examples': {f'${k:04X}': f'${v:04X}' for k, v in readers.items()},
                  'low_memory_writer_examples': {f'${k:04X}': f'${v:04X}' for k, v in writers.items()},
                  'combat_backup_equal_before_restore': capture['equal'],
                  'combat_backup_bytes': capture['bytes']}
        (out/'targeted.json').write_text(json.dumps(result, indent=2)+'\n')
        print('Checked: 7936-byte combat backup; indirect low-RAM party reads and writes')
    finally:
        mos6502._RUN[False] = original_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts', nargs='*', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT/'build/atari/64k-survey')
    parser.add_argument('--verify', action='store_true', help='also compare every event with an uninstrumented replay')
    parser.add_argument('--targeted', action='store_true', help='only run the combat-backup and low-RAM probes')
    args = parser.parse_args()
    scripts = [p.resolve() for p in args.scripts] or sorted((ROOT/'tools/traces').glob('boot-to-*.txt'))
    args.out.mkdir(parents=True, exist_ok=True)
    if args.targeted:
        targeted(args.out)
        return
    combined = bytearray(65536)
    sessions = []
    for script in scripts:
        player = Survey()
        runtime_marks = []
        player.play(script.read_text().splitlines(), pictures=False,
                    on_mark=lambda name: runtime_marks.append(name) if player.active else None)
        if not player.entries:
            raise RuntimeError(f'{script}: game stub not reached')
        for index, value in enumerate(player.flags):
            combined[index] |= value
        events = oracle.comparable(player.events)
        result = {'script': str(script.relative_to(ROOT)), 'entries': player.entries,
                  'events_sha256': hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest(),
                  'marks': sum('mark' in e for e in player.events),
                  'runtime_marks': len(runtime_marks),
                  'cpu_accessed_bytes': sum(bool(v & 3) for v in player.flags)}
        if args.verify:
            reference = oracle.Oracle()
            reference.play(script.read_text().splitlines(), pictures=False)
            assert oracle.comparable(reference.events) == events, script
            result['events_equal_uninstrumented'] = True
        sessions.append(result)
        (args.out/f'{script.stem}.bin').write_bytes(player.flags)
        print(f'{script.stem}: {result["marks"]} marks, {result["cpu_accessed_bytes"]} CPU-accessed bytes', flush=True)
    report = {'method': 'bits: 1 CPU read including instruction fetch; 2 CPU write; 4 hooked disk load',
              'start': 'first execution of $2000 after each power-on; excludes title',
              'limits': 'Sampled scenarios, C64 oracle only; no Atari OS/kernel/ANTIC accesses. Loaded-but-unread data is not proven free.',
              'sessions': sessions, 'display_layout': layout(),
              'no_cpu_access_64_or_more': ranges(combined, 0x0200, 0xcfff, 3, 64),
              'no_cpu_access_or_load_64_or_more': ranges(combined, 0x0200, 0xcfff, 7, 64),
              'low_0800_0aff': {'bytes': 768,
                                'cpu_accessed_bytes': sum(bool(v & 3) for v in combined[0x0800:0x0b00]),
                                'disk_loaded_bytes': sum(bool(v & 4) for v in combined[0x0800:0x0b00])}}
    (args.out/'combined.bin').write_bytes(combined)
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Report: {args.out/"report.json"}', flush=True)


if __name__ == '__main__':
    main()
