import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from code6502 import OPCODES, Image, Trace
from disassemble import Module, address_tables, gaps, is_text, text_runs, vector_handlers


def trace(base, code, entries=None, **options):
    image = Image().load('test', base, bytes(code))
    return Trace(image, **options).run(entries or {base: 'start'})


class Decode(unittest.TestCase):
    def test_only_documented_opcodes(self):
        self.assertEqual(len(OPCODES), 151)
        self.assertEqual(OPCODES[0x4c], ('JMP', 'abs'))
        self.assertNotIn(0x02, OPCODES)

    def test_branch_target_is_signed(self):
        image = Image().load('t', 0x1000, bytes([0xd0, 0xfe, 0xf0, 0x02]))
        self.assertEqual(image.decode(0x1000).target, 0x1000)
        self.assertEqual(image.decode(0x1002).target, 0x1006)


class Flow(unittest.TestCase):
    def test_call_branch_and_return(self):
        #        JSR $1006     BNE $1006  RTS   sub: LDA #1  RTS   data
        code = [0x20, 0x06, 0x10, 0xd0, 0x01, 0x60, 0xa9, 0x01, 0x60, 0xff, 0xff]
        t = trace(0x1000, code)
        self.assertEqual(sorted(t.instructions), [0x1000, 0x1003, 0x1005, 0x1006, 0x1008])
        self.assertEqual(t.code, set(range(0x1000, 0x1009)))
        self.assertEqual(t.problems, [])
        self.assertIn((0x1000, 'jsr'), t.references[0x1006])

    def test_running_into_data_is_reported(self):
        t = trace(0x1000, [0xa9, 0x00, 0xff])
        self.assertEqual([(a, reason) for a, reason, _ in t.problems],
                         [(0x1002, 'undocumented opcode $ff')])

    def test_branch_after_a_constant_load_is_always_taken(self):
        #        LDA #0  BEQ +2   data,data  RTS
        t = trace(0x1000, [0xa9, 0x00, 0xf0, 0x02, 0xff, 0xff, 0x60])
        self.assertNotIn(0x1004, t.code)
        self.assertIn(0x1006, t.instructions)
        self.assertEqual(t.problems, [])

    def test_branch_after_its_opposite_is_always_taken(self):
        #        BNE +3  BEQ +1  data  RTS  RTS
        t = trace(0x1000, [0xd0, 0x03, 0xf0, 0x01, 0xff, 0x60, 0x60])
        self.assertNotIn(0x1004, t.code)
        self.assertEqual(t.problems, [])

    def test_call_outside_the_image_is_a_reference_not_a_problem(self):
        t = trace(0x1000, [0x20, 0xe4, 0xff, 0x60])
        self.assertEqual(t.problems, [])
        self.assertIn((0x1000, 'jsr'), t.references[0xffe4])

    def test_stop_addresses_are_not_entered(self):
        t = trace(0x1000, [0x4c, 0x04, 0x10, 0xea, 0xa9, 0x01, 0x60], stop={0x1004})
        self.assertEqual(sorted(t.instructions), [0x1000])


class Idioms(unittest.TestCase):
    def test_split_address_tables_behind_a_patched_call(self):
        # LDA low,X / STA op+1 / LDA high,X / STA op+2 / JSR $0000 / RTS / low / high
        code = [0xbd, 0x10, 0x10, 0x8d, 0x0d, 0x10, 0xbd, 0x12, 0x10, 0x8d, 0x0e, 0x10,
                0x20, 0x00, 0x00, 0x60, 0x14, 0x15, 0x10, 0x10, 0x60, 0x60]
        t = trace(0x1000, code)
        self.assertEqual(address_tables(t), [(0x100c, 0x1010, 0x1012)])

    def test_interrupt_handler_from_stored_immediates(self):
        # LDA #$10 / STA $0314 / LDA #$20 / STA $0315 / RTS
        code = [0xa9, 0x10, 0x8d, 0x14, 0x03, 0xa9, 0x20, 0x8d, 0x15, 0x03, 0x60]
        self.assertEqual(vector_handlers(trace(0x1000, code)), [(0x2010, 'IRQ', 0x1000)])


class Data(unittest.TestCase):
    def test_text(self):
        self.assertTrue(is_text(b'THE INNKEEPER ASKS:\r"WOULD YOU"'))
        self.assertFalse(is_text(b'A B'))                 # too short
        self.assertFalse(is_text(b'$$$$((((0000'))       # no letters
        self.assertFalse(is_text(b'HELLO\x80'))

    def test_gaps_and_text_runs(self):
        module = Module('m', 0x2000, b'\x60' + b'\x01\x02HELLO WORLD\x00\x07', 'overlay', '', [])
        module.code = {0x2000}
        self.assertEqual(gaps(module), [(0x2001, 0x2010)])
        self.assertEqual(text_runs(module, 0x2001, 0x2010),
                         [(0x2001, 0x2003, 'data'), (0x2003, 0x200e, 'text'), (0x200e, 0x2010, 'data')])


if __name__ == '__main__':
    unittest.main()
