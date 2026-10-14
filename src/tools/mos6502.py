#!/usr/bin/env python3
"""A fast NMOS 6502 core for the host oracle (tools/oracle.py).

The interpreter loop is generated as Python source from the opcode table in
tools/code6502.py and compiled once: one flat function with the registers in
local variables and a binary decision tree on the opcode. That is several
times faster than a method per opcode, which matters when a scripted session
runs hundreds of millions of instructions.

Only the 151 documented opcodes exist; anything else raises, as does decimal
arithmetic and BRK, none of which the game uses. Cycle counts are the base
counts plus one for a taken branch; page-crossing penalties are left out, so
the count is a clock for interrupts and not a cycle-exact one.

Memory model, chosen for speed: `mem` is what the CPU reads, all 64 KB. The
owner keeps it up to date (for a C64, ROM or RAM in $E000-$FFFF as the
banking says). Reads of $D000-$DFFF go to `io_read`. Writes to $0000/$0001
and to $D000 and above go to `special`, which is where banking and hardware
live. Everything else is a plain bytearray store.

Hooks: `hooks` is a 64 KB bytearray; a non-zero byte at an address calls
`on_hook(pc)` before the instruction there runs. The callback may change the
registers (to stand in for a subroutine) and returns true to stop the run.
`on_event()` is called whenever the cycle count reaches `next_event`, and
after any instruction that can unmask interrupts.

`CPU(mem, coverage=True)` uses a second copy of the loop that also counts in
`seen` how often an instruction started at each address; it is about a fifth
slower.
"""
from itertools import repeat

from code6502 import LENGTH, OPCODES


class CPUError(RuntimeError):
    pass


_CYCLES = {'imp': 2, 'acc': 2, 'imm': 2, 'zp': 3, 'zpx': 4, 'zpy': 4, 'abs': 4,
           'absx': 4, 'absy': 4, 'indx': 6, 'indy': 5, 'rel': 2, 'ind': 5}
_SPECIAL_CYCLES = {'PHA': 3, 'PHP': 3, 'PLA': 4, 'PLP': 4, 'RTS': 6, 'RTI': 6, 'JSR': 6}
_MODIFY = {'ASL', 'LSR', 'ROL', 'ROR', 'INC', 'DEC'}
_STORE = {'STA': 'a', 'STX': 'x', 'STY': 'y'}

_ADDRESS = {
    'zp': 'ea = mem[pc + 1]',
    'zpx': 'ea = (mem[pc + 1] + x) & 0xFF',
    'zpy': 'ea = (mem[pc + 1] + y) & 0xFF',
    'abs': 'ea = mem[pc + 1] | mem[pc + 2] << 8',
    'absx': 'ea = ((mem[pc + 1] | mem[pc + 2] << 8) + x) & 0xFFFF',
    'absy': 'ea = ((mem[pc + 1] | mem[pc + 2] << 8) + y) & 0xFFFF',
    'indx': 't = (mem[pc + 1] + x) & 0xFF\nea = mem[t] | mem[(t + 1) & 0xFF] << 8',
    'indy': 't = mem[pc + 1]\nea = ((mem[t] | mem[(t + 1) & 0xFF] << 8) + y) & 0xFFFF',
}
_ZERO_PAGE = {'zp', 'zpx', 'zpy'}

# N and Z live in one value: Z is set when its low byte is 0, N when bit 7 or
# bit 8 is set. Bit 8 lets N and Z both be set (after PLP or BIT).
_PACK = ('((0x80 if nz & 0x180 else 0) | (0x40 if fv else 0) | 0x20 | (8 if fd else 0)'
         ' | (4 if fi else 0) | (0 if nz & 0xFF else 2) | fc)')
_UNPACK = ('fc = t & 1\nnz = ((t & 0x80) << 1) | (0 if t & 2 else 1)\n'
           'fi = t & 4\nfd = t & 8\nfv = t & 0x40')
_PUSH = 'mem[0x100 | s] = {}\ns = (s - 1) & 0xFF'
_PULL = 's = (s + 1) & 0xFF\n{} = mem[0x100 | s]'
_ADC = ('if fd:\n    raise CPUError("decimal arithmetic at $%04X" % pc)\n'
        't = a + v + fc\nfv = ~(a ^ v) & (a ^ t) & 0x80\nfc = t >> 8\na = nz = t & 0xFF')

_VALUE_OPS = {      # operand value in v
    'LDA': 'a = nz = v', 'LDX': 'x = nz = v', 'LDY': 'y = nz = v',
    'AND': 'a = nz = a & v', 'ORA': 'a = nz = a | v', 'EOR': 'a = nz = a ^ v',
    'ADC': _ADC, 'SBC': 'v ^= 0xFF\n' + _ADC,
    'CMP': 't = a - v\nfc = 0 if t < 0 else 1\nnz = t & 0xFF',
    'CPX': 't = x - v\nfc = 0 if t < 0 else 1\nnz = t & 0xFF',
    'CPY': 't = y - v\nfc = 0 if t < 0 else 1\nnz = t & 0xFF',
    'BIT': 'nz = ((v & 0x80) << 1) | (1 if a & v else 0)\nfv = v & 0x40',
}
_MODIFY_OPS = {     # v in, v out
    'ASL': 'fc = v >> 7\nv = nz = (v << 1) & 0xFF',
    'LSR': 'fc = v & 1\nv = nz = v >> 1',
    'ROL': 't = (v << 1) | fc\nfc = t >> 8\nv = nz = t & 0xFF',
    'ROR': 't = v | (fc << 8)\nfc = t & 1\nv = nz = t >> 1',
    'INC': 'v = nz = (v + 1) & 0xFF',
    'DEC': 'v = nz = (v - 1) & 0xFF',
}
_IMPLIED = {
    'TAX': 'x = nz = a', 'TAY': 'y = nz = a', 'TXA': 'a = nz = x', 'TYA': 'a = nz = y',
    'TSX': 'x = nz = s', 'TXS': 's = x',
    'INX': 'x = nz = (x + 1) & 0xFF', 'INY': 'y = nz = (y + 1) & 0xFF',
    'DEX': 'x = nz = (x - 1) & 0xFF', 'DEY': 'y = nz = (y - 1) & 0xFF',
    'CLC': 'fc = 0', 'SEC': 'fc = 1', 'CLV': 'fv = 0', 'CLD': 'fd = 0', 'SED': 'fd = 8',
    'SEI': 'fi = 4', 'CLI': 'fi = 0\nnev = 0', 'NOP': 'pass',
    'PHA': _PUSH.format('a'), 'PLA': _PULL.format('a') + '\nnz = a',
    'PHP': _PUSH.format(_PACK + ' | 0x10'),
    'PLP': _PULL.format('t') + '\n' + _UNPACK + '\nnev = 0',
}
_BRANCH = {'BPL': 'not nz & 0x180', 'BMI': 'nz & 0x180', 'BNE': 'nz & 0xFF',
           'BEQ': 'not nz & 0xFF', 'BCC': 'not fc', 'BCS': 'fc', 'BVC': 'not fv', 'BVS': 'fv'}

_READ = 'v = mem[ea] if ea & 0xF000 != 0xD000 else io_read(ea)'
_WRITE = ('if 1 < ea < 0xD000:\n    mem[ea] = {0}\nelse:\n    self.write_cycle = cyc\n    special(ea, {0})\n    nev = self.next_event')
_WRITE_ZP = ('if ea > 1:\n    mem[ea] = {0}\nelse:\n    special(ea, {0})\n    nev = self.next_event')


def _body(opcode):
    """Python statements for one opcode; pc still points at the opcode."""
    mnemonic, mode = OPCODES[opcode]
    cycles = _SPECIAL_CYCLES.get(mnemonic, _CYCLES[mode])
    lines = []
    step = f'pc += {LENGTH[mode]}'
    write = _WRITE_ZP if mode in _ZERO_PAGE else _WRITE
    read = 'v = mem[ea]' if mode in _ZERO_PAGE else _READ
    if mnemonic in _BRANCH:
        lines += [f'if {_BRANCH[mnemonic]}:', '    t = mem[pc + 1]',
                  '    pc = (pc + 2 + (t if t < 0x80 else t - 0x100)) & 0xFFFF',
                  '    cyc += 3', 'else:', '    pc += 2', '    cyc += 2']
        return lines
    if mnemonic == 'JMP':
        if mode == 'abs':
            lines += ['pc = mem[pc + 1] | mem[pc + 2] << 8']
            cycles = 3
        else:   # the NMOS chip does not carry into the high byte of the pointer
            lines += ['t = mem[pc + 1] | mem[pc + 2] << 8',
                      'pc = mem[t] | mem[(t & 0xFF00) | ((t + 1) & 0xFF)] << 8']
    elif mnemonic == 'JSR':
        lines += ['t = pc + 2'] + _PUSH.format('t >> 8').split('\n') + _PUSH.format('t & 0xFF').split('\n')
        lines += ['pc = mem[pc + 1] | mem[pc + 2] << 8']
    elif mnemonic == 'RTS':
        lines += _PULL.format('t').split('\n') + _PULL.format('pc').split('\n')
        lines += ['pc = ((pc << 8 | t) + 1) & 0xFFFF']
    elif mnemonic == 'RTI':
        lines += _PULL.format('t').split('\n') + _UNPACK.split('\n')
        lines += _PULL.format('t').split('\n') + _PULL.format('pc').split('\n')
        lines += ['pc = pc << 8 | t', 'nev = 0']
    elif mnemonic == 'BRK':
        lines += ['raise CPUError("BRK at $%04X" % pc)']
    elif mode == 'imp':
        lines += _IMPLIED[mnemonic].split('\n') + [step]
    elif mode == 'acc':
        lines += ['v = a'] + _MODIFY_OPS[mnemonic].split('\n') + ['a = v', step]
    elif mode == 'imm':
        lines += ['v = mem[pc + 1]'] + _VALUE_OPS[mnemonic].split('\n') + [step]
    elif mnemonic in _STORE:
        lines += _ADDRESS[mode].split('\n') + [step] + write.format(_STORE[mnemonic]).split('\n')
        cycles += {'absx': 1, 'absy': 1, 'indy': 1}.get(mode, 0)
    elif mnemonic in _MODIFY:
        lines += (_ADDRESS[mode].split('\n') + [step, read] + _MODIFY_OPS[mnemonic].split('\n')
                  + write.format('v').split('\n'))
        cycles += 3 if mode == 'absx' else 2
    else:
        lines += _ADDRESS[mode].split('\n') + [step, read] + _VALUE_OPS[mnemonic].split('\n')
    return lines + [f'cyc += {cycles}']


def _tree(low, high, indent):
    """Nested if/else over opcode values low..high-1; a value with no
    documented opcode raises."""
    pad = '    ' * indent
    known = [code for code in range(low, high) if code in OPCODES]
    if not known:
        return [f'{pad}raise CPUError("undocumented opcode $%02X at $%04X" % (op, pc))']
    if high - low == 1:
        return [pad + line for line in _body(low)]
    middle = (low + high) // 2
    return ([f'{pad}if op < {middle}:'] + _tree(low, middle, indent + 1)
            + [f'{pad}else:'] + _tree(middle, high, indent + 1))


_LOAD = ('a, x, y, s, pc, cyc = self.a, self.x, self.y, self.s, self.pc, self.cycles\n'
         'nz, fc, fv, fi, fd = self.nz, self.fc, self.fv, self.fi, self.fd\n'
         'nev = self.next_event')
_SAVE = ('self.a, self.x, self.y, self.s, self.pc, self.cycles = a, x, y, s, pc, cyc\n'
         'self.nz, self.fc, self.fv, self.fi, self.fd = nz, fc, fv, fi, fd')


def _source(coverage):
    def block(text, indent):
        return ['    ' * indent + line for line in text.split('\n')]
    lines = ['def run(self, limit):',
             '    mem, hooks, io_read, special = self.mem, self.hooks, self.io_read, self.special',
             '    seen = self.seen',
             '    done = 0', '    skip = self.resume_at'] + block(_LOAD, 1)
    lines += ['    for _ in repeat(None, limit):',
              '        if cyc >= nev:'] + block(_SAVE, 3) + ['            self.on_event()'] + block(_LOAD, 3)
    lines += ['        if hooks[pc] and pc != skip:'] + block(_SAVE, 3)
    lines += ['            stop = self.on_hook(pc)', '            t = pc'] + block(_LOAD, 3)
    lines += ['            if stop:', '                self.resume_at = pc', '                break',
              '            if pc != t:', '                continue',
              '        skip = -1',
              '        op = mem[pc]',
              '        done += 1'] + (['        seen[pc] += 1'] if coverage else [])
    lines += _tree(0, 256, 2)
    lines += ['    else:', '        self.resume_at = -1']
    lines += block(_SAVE, 1) + ['    self.instructions += done', '    return done']
    return '\n'.join(lines) + '\n'


_namespace = {'repeat': repeat, 'CPUError': CPUError}
_RUN = {}
for _coverage in (False, True):
    exec(compile(_source(_coverage), '<generated 6502 core>', 'exec'), _namespace)
    _RUN[_coverage] = _namespace['run']


class CPU:
    def __init__(self, mem, coverage=False):
        self.mem = mem
        self.hooks = bytearray(65536)
        self.seen = [0] * 65536         # with coverage: how often an instruction started here
        self._run = _RUN[coverage]
        self.a = self.x = self.y = 0
        self.s = 0xFF
        self.pc = 0
        self.nz, self.fc, self.fv, self.fi, self.fd = 1, 0, 0, 4, 0
        self.cycles = self.instructions = 0
        self.next_event = 1 << 62
        self.resume_at = -1
        self.io_read = lambda address: 0
        self.special = lambda address, value: None
        self.on_hook = lambda pc: True
        self.on_event = lambda: None

    @property
    def p(self):
        return ((0x80 if self.nz & 0x180 else 0) | (0x40 if self.fv else 0) | 0x20
                | (8 if self.fd else 0) | (4 if self.fi else 0)
                | (0 if self.nz & 0xFF else 2) | self.fc)

    @p.setter
    def p(self, value):
        self.fc = value & 1
        self.nz = ((value & 0x80) << 1) | (0 if value & 2 else 1)
        self.fi, self.fd, self.fv = value & 4, value & 8, value & 0x40

    def push(self, value):
        self.mem[0x100 | self.s] = value & 0xFF
        self.s = (self.s - 1) & 0xFF

    def pull(self):
        self.s = (self.s + 1) & 0xFF
        return self.mem[0x100 | self.s]

    def rts(self):
        """Return from a subroutine a hook stood in for."""
        low = self.pull()
        self.pc = ((self.pull() << 8 | low) + 1) & 0xFFFF

    def interrupt(self, vector):
        """Enter an IRQ or NMI: push PC and P (B clear), mask, load the vector."""
        self.push(self.pc >> 8)
        self.push(self.pc)
        self.push(self.p & ~0x10)
        self.fi = 4
        self.pc = self.mem[vector] | self.mem[vector + 1] << 8
        self.cycles += 7

    def run(self, limit=1 << 62):
        """Run up to `limit` instructions; returns how many ran. Stops early
        when a hook returns true, leaving pc at the hooked instruction."""
        return self._run(self, limit)
