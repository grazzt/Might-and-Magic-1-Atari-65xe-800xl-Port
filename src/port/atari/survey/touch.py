import sys
sys.path.insert(0, 'tools')
import mos6502 as m
T = bytearray(65536)
m._READ = 'v = mem[ea] if ea & 0xF000 != 0xD000 else io_read(ea); T[ea] |= 1'
m._WRITE = ('if 1 < ea < 0xD000:\n    mem[ea] = {0}\n    T[ea] |= 2\nelse:\n    T[ea] |= 2\n    self.write_cycle = cyc\n    special(ea, {0})\n    nev = self.next_event')
src = m._source(False)
src = src.replace("        op = mem[pc]\n", "        op = mem[pc]\n        T[pc] |= 4; T[pc+1] |= 4; T[(pc+2) & 0xFFFF] |= 4\n")
ns = {'repeat': m.repeat, 'CPUError': m.CPUError, 'T': T}
exec(compile(src, '<g>', 'exec'), ns)
m._RUN[False] = ns['run']
import oracle
name = sys.argv[1]
o = oracle.Oracle()
o.play(open(f'tools/traces/{name}.txt').read().splitlines(), pictures=False)
open(f'/tmp/opencode/survey/touch-{name}.bin', 'wb').write(T)
