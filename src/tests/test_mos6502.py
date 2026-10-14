import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from mos6502 import CPU, CPUError


def run(code, steps=None, **registers):
    """Run bytes at $1000 until the hook at their end; returns the CPU."""
    mem = bytearray(65536)
    mem[0x1000:0x1000 + len(code)] = bytes(code)
    cpu = CPU(mem)
    cpu.pc = 0x1000
    for name, value in registers.items():
        setattr(cpu, name, value)
    cpu.hooks[0x1000 + len(code)] = 1
    cpu.run(steps or 1000)
    return cpu


class Arithmetic(unittest.TestCase):
    def test_adc_carry_and_overflow(self):
        cases = [  # a, operand, carry in -> a, carry, overflow, zero, negative
            (0x50, 0x10, 0, 0x60, 0, 0, 0, 0), (0x50, 0x50, 0, 0xa0, 0, 1, 0, 1),
            (0x50, 0xd0, 0, 0x20, 1, 0, 0, 0), (0xd0, 0x90, 0, 0x60, 1, 1, 0, 0),
            (0xff, 0x00, 1, 0x00, 1, 0, 1, 0), (0x7f, 0x00, 1, 0x80, 0, 1, 0, 1)]
        for a, operand, carry, result, c, v, z, n in cases:
            cpu = run([0x69, operand], a=a, fc=carry)
            self.assertEqual((cpu.a, cpu.p & 1, cpu.p >> 6 & 1, cpu.p >> 1 & 1, cpu.p >> 7),
                             (result, c, v, z, n), (a, operand, carry))

    def test_sbc_borrow_and_overflow(self):
        cases = [(0x50, 0xf0, 1, 0x60, 0, 0), (0x50, 0xb0, 1, 0xa0, 0, 1),
                 (0xd0, 0x70, 1, 0x60, 1, 1), (0x00, 0x00, 0, 0xff, 0, 0), (0x05, 0x05, 1, 0x00, 1, 0)]
        for a, operand, carry, result, c, v in cases:
            cpu = run([0xe9, operand], a=a, fc=carry)
            self.assertEqual((cpu.a, cpu.p & 1, cpu.p >> 6 & 1), (result, c, v), (a, operand, carry))

    def test_compare(self):
        for a, operand, c, z, n in [(5, 5, 1, 1, 0), (5, 6, 0, 0, 1), (6, 5, 1, 0, 0), (0x80, 1, 1, 0, 0)]:
            cpu = run([0xc9, operand], a=a)
            self.assertEqual((cpu.p & 1, cpu.p >> 1 & 1, cpu.p >> 7), (c, z, n), (a, operand))

    def test_shifts_and_rotates_through_carry(self):
        cpu = run([0x0a], a=0x81)                      # ASL A
        self.assertEqual((cpu.a, cpu.p & 1), (0x02, 1))
        cpu = run([0x2a], a=0x80, fc=1)                # ROL A
        self.assertEqual((cpu.a, cpu.p & 1), (0x01, 1))
        cpu = run([0x6a], a=0x01, fc=1)                # ROR A
        self.assertEqual((cpu.a, cpu.p & 1), (0x80, 1))
        cpu = run([0x4a], a=0x01)                      # LSR A
        self.assertEqual((cpu.a, cpu.p & 3), (0x00, 3))

    def test_bit_sets_n_v_from_memory_and_z_from_and(self):
        cpu = run([0x24, 0x10], a=0x01)
        cpu.mem[0x10] = 0xc0
        cpu = run([0x24, 0x10], a=0x01)
        self.assertEqual(cpu.p & 0xc2, 0x02)           # memory was 0 here: Z only
        mem_test = run([0xa9, 0xc0, 0x85, 0x10, 0xa9, 0x01, 0x24, 0x10])
        self.assertEqual(mem_test.p & 0xc2, 0xc2)      # N, V and Z all set


class Flow(unittest.TestCase):
    def test_jsr_rts_and_stack(self):
        #      JSR $1006      LDX #2    (hook)   sub: LDA #7  RTS
        code = [0x20, 0x06, 0x10, 0xa2, 0x02, 0xea, 0xa9, 0x07, 0x60]
        mem = bytearray(65536)
        mem[0x1000:0x1009] = bytes(code)
        cpu = CPU(mem)
        cpu.pc = 0x1000
        cpu.hooks[0x1005] = 1
        cpu.run(100)
        self.assertEqual((cpu.a, cpu.x, cpu.pc, cpu.s), (7, 2, 0x1005, 0xff))

    def test_branches_backward_and_forward(self):
        #      LDX #3   loop: DEX  BNE loop  BEQ +1  (skipped) LDA #9
        cpu = run([0xa2, 0x03, 0xca, 0xd0, 0xfd, 0xf0, 0x01, 0x00, 0xa9, 0x09])
        self.assertEqual((cpu.x, cpu.a), (0, 9))

    def test_indirect_modes(self):
        mem = bytearray(65536)
        mem[0x20:0x22] = bytes([0x00, 0x30])           # pointer to $3000
        mem[0x3005] = 0x77
        #      LDY #5  LDA ($20),Y  STA ($20),Y+... LDX #0  STA ($20,X)
        code = [0xa0, 0x05, 0xb1, 0x20, 0xa2, 0x00, 0x81, 0x20]
        mem[0x1000:0x1000 + len(code)] = bytes(code)
        cpu = CPU(mem)
        cpu.pc = 0x1000
        cpu.hooks[0x1000 + len(code)] = 1
        cpu.run(100)
        self.assertEqual((cpu.a, mem[0x3000]), (0x77, 0x77))

    def test_php_plp_round_trip_keeps_n_and_z_together(self):
        cpu = run([0x08, 0xa9, 0x01, 0x28], nz=0x100)  # N and Z set; PHP, LDA #1, PLP
        self.assertEqual(cpu.p & 0x82, 0x82)

    def test_undocumented_opcode_and_brk_raise(self):
        with self.assertRaises(CPUError):
            run([0x02])
        with self.assertRaises(CPUError):
            run([0x00])


class Callbacks(unittest.TestCase):
    def test_writes_to_port_and_high_memory_go_to_special(self):
        seen = []
        mem = bytearray(65536)
        code = [0xa9, 0x36, 0x85, 0x01, 0x8d, 0x20, 0xd0, 0x8d, 0x00, 0x30]
        mem[0x1000:0x1000 + len(code)] = bytes(code)
        cpu = CPU(mem)
        cpu.special = lambda address, value: seen.append((address, value))
        cpu.pc = 0x1000
        cpu.hooks[0x1000 + len(code)] = 1
        cpu.run(100)
        self.assertEqual(seen, [(1, 0x36), (0xd020, 0x36)])
        self.assertEqual(mem[0x3000], 0x36)

    def test_hook_can_stand_in_for_a_subroutine(self):
        mem = bytearray(65536)
        mem[0x1000:0x1004] = bytes([0x20, 0x00, 0x90, 0xea])   # JSR $9000 ; NOP
        cpu = CPU(mem)
        cpu.pc = 0x1000

        def hook(pc):
            if pc == 0x9000:
                cpu.a = 0x42
                cpu.rts()
                return False
            return True
        cpu.on_hook = hook
        cpu.hooks[0x9000] = cpu.hooks[0x1004] = 1
        cpu.run(100)
        self.assertEqual((cpu.a, cpu.pc), (0x42, 0x1004))

    def test_stopped_run_resumes_past_the_hook(self):
        mem = bytearray(65536)
        mem[0x1000:0x1003] = bytes([0xe8, 0xe8, 0xe8])
        cpu = CPU(mem)
        cpu.pc = 0x1000
        cpu.hooks[0x1001] = cpu.hooks[0x1003] = 1
        cpu.run(100)
        self.assertEqual((cpu.pc, cpu.x), (0x1001, 1))
        cpu.run(100)
        self.assertEqual((cpu.pc, cpu.x), (0x1003, 3))

    def test_interrupt_entry(self):
        mem = bytearray(65536)
        mem[0xfffe:0x10000] = bytes([0x00, 0x80])
        cpu = CPU(mem)
        cpu.pc, cpu.fi = 0x1234, 0
        cpu.interrupt(0xfffe)
        self.assertEqual((cpu.pc, cpu.fi, mem[0x1ff], mem[0x1fe], mem[0x1fd] & 0x14), (0x8000, 4, 0x12, 0x34, 0))


if __name__ == '__main__':
    unittest.main()
