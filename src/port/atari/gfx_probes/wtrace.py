import sys, collections
sys.path.insert(0, 'tools')
import mos6502 as m
LOG = collections.Counter()
m._WRITE = ("if 1 < ea < 0xD000:\n    mem[ea] = {0}\n    if 0x2000 <= ea < 0x4000: LOG[(pc,ea>>8)] += 1\nelse:\n"
            "    if ea >= 0xE000: LOG[(pc,ea>>8)] += 1\n    self.write_cycle = cyc\n    special(ea, {0})\n    nev = self.next_event")
m._WRITE_ZP = m._WRITE_ZP
ns = {'repeat': m.repeat, 'CPUError': m.CPUError, 'LOG': LOG}
exec(compile(m._source(False), '<g>', 'exec'), ns)
m._RUN[False] = ns['run']
import oracle
o = oracle.Oracle()
lines = open(sys.argv[1]).read().splitlines()
o.play(lines, pictures=False)
mem = o.machine.mem
by = collections.defaultdict(lambda: [0, set()])
for (pc, page), n in LOG.items():
    # instruction start: find 3/2/1 byte candidate
    for L in (3, 2, 1):
        s = pc - L
        op = mem[s]
        if op in (0x8d,0x9d,0x99,0x91,0x8e,0x8c,0x2e,0x6e,0x0e,0x4e,0xee,0xce,0x1e,0x3e,0x5e,0x7e,0xfe,0xde,0x81,0x95,0x85,0x84,0x86,0x96,0x94,0x06,0x26,0x46,0x66,0xe6,0xc6,0x16,0x36,0x56,0x76,0xf6,0xd6) and (L == {0x8d:3,0x9d:3,0x99:3,0x8e:3,0x8c:3}.get(op, L)):
            by[s][0] += n; by[s][1].add(page); break
    else:
        by[pc][0] += n; by[pc][1].add(page)
print(len(by), 'writer instructions')
for s in sorted(by):
    print(f'{s:04x} op={mem[s]:02x} n={by[s][0]} pages={min(by[s][1]):02x}-{max(by[s][1]):02x}')
