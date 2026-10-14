import sys, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from mos6502 import CPU
from pathlib import Path
from zx0 import zx0_compress
bin_ = (HERE / 'zx0.bin').read_bytes()
def run(comp, expect_len):
    mem = bytearray(65536)
    mem[0x0800:0x0800+len(bin_)] = bin_
    SRC, DST, STOP = 0x2000, 0x4000, 0x0300
    mem[SRC:SRC+len(comp)] = comp
    mem[0xF8], mem[0xF9] = SRC & 255, SRC >> 8
    mem[0xFA], mem[0xFB] = DST & 255, DST >> 8
    mem[STOP] = 0x4C; mem[STOP+1] = 0x00; mem[STOP+2] = 0x03   # spin
    # JSR zx0 ; then spin
    mem[0x0300] = 0x20; mem[0x0301] = 0x00; mem[0x0302] = 0x08
    mem[0x0303] = 0x4C; mem[0x0304] = 0x03; mem[0x0305] = 0x03
    cpu = CPU(mem); cpu.pc = 0x0300; cpu.s = 0xFF
    cpu.run(5_000_000) if False else None
    start = cpu.cycles
    for _ in range(3_000_000):
        cpu.run(1)
        if cpu.pc == 0x0303: break
    else:
        return None, None
    return bytes(mem[DST:DST+expect_len]), cpu.cycles - start

if __name__ == '__main__':
    L = (ROOT / 'build/c64/original-v2-b/logical.bin').read_bytes()
    tests = [b'a', b'abababababab', bytes(300), L[0xfc*256:0xfc*256+0x63d], L[0x104*256:0x104*256+0x9b6],
             L[0x111*256:0x111*256+0x1500], bytes(random.Random(1).randrange(256) for _ in range(500))]
    for t in tests:
        c = zx0_compress(t)[0]
        out, cyc = run(c, len(t))
        print(f'{len(t):6d} bytes -> {len(c):5d}:', 'FAIL/hang' if out is None else ('OK  %d cycles (%.0f/byte)' % (cyc, cyc/len(t)) if out == t else 'MISMATCH'))
