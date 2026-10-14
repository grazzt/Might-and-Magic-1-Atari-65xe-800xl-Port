"""65XE memory and presentation contracts; gameplay uses check65.py."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'port/atari')]
import build
from c64 import shared_root
from mos6502 import CPU
import profile65

READY = ((ROOT/'build/c64/original-v2-b/logical.bin').exists()
         and (shared_root()/'tools/toolchain/local/bin/ca65').exists())


@unittest.skipUnless(READY, 'needs original logical disks and cc65')
class Presentation65(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(build.select_profile, False)
        cls.layout = build.build_disks(test=True, xe64=True)
        cls.labels = {k: int(v[1:], 16) for k, v in cls.layout['labels'].items()}
        cls.images = {name: (build.OUT/name).read_bytes() for name in build.SEGMENTS}
        cls.bases = dict(build.SEGMENTS)

    def memory(self):
        memory = bytearray(65536)
        for name, data in self.images.items():
            base = self.bases[name]
            memory[base:base+len(data)] = data
        return memory

    def cpu(self, memory):
        cpu = CPU(memory)
        cpu.io_read = lambda address: memory[address]
        cpu.special = lambda address, value: memory.__setitem__(address, value)
        return cpu

    def run_to(self, cpu, address, limit=100000):
        cpu.hooks[address] = 1
        cpu.run(limit)
        self.assertEqual(cpu.pc, address, 'routine did not finish within its budget')

    def test_original_register_and_pointer_results(self):
        # Exercise both carry states, both overflow states and both IRQ masks.
        # Colour output and CIA hardware are replaced, all other effects agree.
        for name in ('colour65.bin', 'play65.bin', 'bank65.bin', 'copycolour65.bin'):
            _, base, before = profile65.BORROWED[name]
            for flags in (0x20, 0x21, 0x24, 0x25, 0x60, 0x61, 0x64, 0x65):
                results = []
                for original in (True, False):
                    memory = self.memory()
                    if original:
                        memory[base:base+len(bytes.fromhex(before))] = bytes.fromhex(before)
                    memory[0x4d:0x4f] = b'\x12\x34'
                    memory[0xdd00:0xdd03] = b'\xa4\x66\xa0'
                    cpu = self.cpu(memory)
                    cpu.pc, cpu.a, cpu.x, cpu.y, cpu.p = base, 2, 0x31, 0x73, flags
                    cpu.push(0x04)
                    cpu.push(0x9f)  # RTS to $04A0
                    self.run_to(cpu, 0x04a0)
                    results.append((cpu.a, cpu.x, cpu.y, cpu.s, cpu.p,
                                    bytes(memory[0x4d:0x4f]), memory[0xc40c]))
                self.assertEqual(results[0], results[1], (name, flags))

    def test_wait_entries_preserve_contract_and_force_one_refresh(self):
        memory = self.memory()
        cpu = self.cpu(memory)
        cpu.pc, cpu.a, cpu.x, cpu.y, cpu.p = 0x0e37, 7, 9, 11, 0x61
        memory[0xc6] = 4
        self.run_to(cpu, 0x0e3b)
        self.assertEqual((cpu.a, cpu.x, cpu.y, cpu.p, memory[0xc6]), (0, 9, 11, 0x63, 0))
        self.assertEqual(memory[self.labels['key_given']], 1)
        for entry in (0xa036, 0xb233):
            memory = self.memory()
            cpu = self.cpu(memory)
            cpu.pc, cpu.a, cpu.x, cpu.y, cpu.p = entry, 7, 9, 11, 0x61
            memory[0xc6] = 4
            memory[0xc355:0xc359] = bytes.fromhex('a20086c6')
            self.run_to(cpu, 0xc359)  # original LDX #0/STX KEY_COUNT completed
            self.assertEqual((cpu.a, cpu.x, cpu.y, cpu.p, memory[0xc6]), (7, 0, 11, 0x63, 0))
            self.assertEqual(memory[self.labels['key_given']], 1)

    def test_flip_publishes_before_clear_and_restores_cpu_state(self):
        for mode in (0, 1, 2):
            for flags in (0x20, 0x21, 0x24, 0x25, 0x60, 0x61, 0x64, 0x65):
                memory = self.memory()
                cpu = self.cpu(memory)
                cpu.pc, cpu.a, cpu.x, cpu.y, cpu.p = 0x1c13, mode, 19, 29, flags
                cpu.push(0x04)
                cpu.push(0x9f)
                cpu.hooks[self.labels['refresh']] = 1
                def refresh(pc):
                    if pc != self.labels['refresh']:
                        return True
                    self.assertEqual(memory[0x0389], mode)
                    cpu.a, cpu.x, cpu.y, cpu.p = 77, 88, 99, 0x25
                    cpu.rts()
                    cpu.next_event = cpu.cycles+200
                    return False
                cpu.on_hook = refresh
                def vbi():
                    if cpu.cycles >= cpu.next_event:
                        memory[self.labels['frames']] += 1
                        cpu.next_event = 1 << 62
                cpu.on_event = vbi
                self.run_to(cpu, 0x04a0)
                self.assertEqual((cpu.a, cpu.x, cpu.y, cpu.p, cpu.s),
                                 (mode, 19, 29, flags & ~4, 255))
                self.assertEqual(memory[self.labels['frames']], 1)

    def font(self, stack):
        memory = self.memory()
        memory[0xcc00:0xd000] = bytes([0xa5])*1024
        font = bytes((n*73+n//8) & 255 for n in range(1024))
        original = bytes(memory[0xe000:0xe400])
        port_writes = []
        cpu = self.cpu(memory)
        def store(address, value):
            memory[address] = value
            if address == 0xd301:
                port_writes.append(value)
                memory[0xe000:0xe400] = font if value & 1 else original
        cpu.special = store
        memory[0xd301] = 0xfe
        cpu.s = stack+2
        cpu.push(0x04)
        cpu.push(0x9f)
        cpu.pc = self.labels['make_font']
        cpu.p = 0x61
        self.run_to(cpu, 0x04a0)
        self.assertEqual(cpu.p, 0x61)
        self.assertEqual(memory[0xd301], 0xfe)
        self.assertEqual(memory[0xd40e], 0x40)
        return memory, font, port_writes

    def test_font_banks_rom_and_reorders_all_128_glyphs(self):
        memory, font, writes = self.font(0x91)  # lowest accepted caller stack
        self.assertEqual(memory[0xcc00:0xd000], font[768:]+font[:768])
        self.assertEqual(writes, [0xff, 0xfe]*8)
        self.assertEqual(memory[self.labels['font_failed']], 0)

    def test_font_rejects_a_stack_overlapping_the_sio_buffer(self):
        memory, _, writes = self.font(0x90)
        self.assertEqual(memory[0xcc00:0xd000], bytes([0xa5])*1024)
        self.assertEqual(writes, [])
        self.assertEqual(memory[self.labels['font_failed']], 1)

    def test_layout_has_only_main_memory_and_six_copy_slots(self):
        self.assertEqual(self.layout['ram_kb'], 64)
        self.assertNotIn('ext.bin', self.images)
        self.assertNotIn('ext2.bin', self.images)
        copies = (0xcc00, 0xcd40, 0xce80, 0xd800, 0xd940, 0xda80)
        for destination in copies:
            self.assertTrue(0xcc00 <= destination and destination+320 <= 0xd000
                            or 0xd800 <= destination and destination+320 <= 0xdc00)
        regions = sorted((base, base+len(self.images[name])) for name, base in self.bases.items())
        self.assertTrue(all(first[1] <= second[0] for first, second in zip(regions, regions[1:])))
        for disk in self.layout['disks']:
            self.assertLess(disk['sectors'], self.layout['index_sector'])


if __name__ == '__main__':
    unittest.main()
