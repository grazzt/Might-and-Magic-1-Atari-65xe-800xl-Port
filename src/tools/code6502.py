#!/usr/bin/env python3
"""Static 6502 flow tracing: which bytes of a memory image are instructions.

Starting from entry addresses, follow every instruction to the ones that can
run after it. What is reached is code; what is not is data or code reached in
a way this cannot see (address tables, computed jumps), which the caller has
to supply as further entries. Only the 151 documented opcodes are accepted, so
a path that runs into data usually shows up as a problem.

No hardware is modelled. Used by tools/disassemble.py.
"""

_TABLE = """
ADC imm 69 zp 65 zpx 75 abs 6D absx 7D absy 79 indx 61 indy 71
AND imm 29 zp 25 zpx 35 abs 2D absx 3D absy 39 indx 21 indy 31
ASL acc 0A zp 06 zpx 16 abs 0E absx 1E
BCC rel 90
BCS rel B0
BEQ rel F0
BMI rel 30
BNE rel D0
BPL rel 10
BVC rel 50
BVS rel 70
BIT zp 24 abs 2C
BRK imp 00
CLC imp 18
CLD imp D8
CLI imp 58
CLV imp B8
CMP imm C9 zp C5 zpx D5 abs CD absx DD absy D9 indx C1 indy D1
CPX imm E0 zp E4 abs EC
CPY imm C0 zp C4 abs CC
DEC zp C6 zpx D6 abs CE absx DE
DEX imp CA
DEY imp 88
EOR imm 49 zp 45 zpx 55 abs 4D absx 5D absy 59 indx 41 indy 51
INC zp E6 zpx F6 abs EE absx FE
INX imp E8
INY imp C8
JMP abs 4C ind 6C
JSR abs 20
LDA imm A9 zp A5 zpx B5 abs AD absx BD absy B9 indx A1 indy B1
LDX imm A2 zp A6 zpy B6 abs AE absy BE
LDY imm A0 zp A4 zpx B4 abs AC absx BC
LSR acc 4A zp 46 zpx 56 abs 4E absx 5E
NOP imp EA
ORA imm 09 zp 05 zpx 15 abs 0D absx 1D absy 19 indx 01 indy 11
PHA imp 48
PHP imp 08
PLA imp 68
PLP imp 28
ROL acc 2A zp 26 zpx 36 abs 2E absx 3E
ROR acc 6A zp 66 zpx 76 abs 6E absx 7E
RTI imp 40
RTS imp 60
SBC imm E9 zp E5 zpx F5 abs ED absx FD absy F9 indx E1 indy F1
SEC imp 38
SED imp F8
SEI imp 78
STA zp 85 zpx 95 abs 8D absx 9D absy 99 indx 81 indy 91
STX zp 86 zpy 96 abs 8E
STY zp 84 zpx 94 abs 8C
TAX imp AA
TAY imp A8
TSX imp BA
TXA imp 8A
TXS imp 9A
TYA imp 98
"""
LENGTH = {'imp': 1, 'acc': 1, 'imm': 2, 'zp': 2, 'zpx': 2, 'zpy': 2, 'rel': 2,
          'indx': 2, 'indy': 2, 'abs': 3, 'absx': 3, 'absy': 3, 'ind': 3}
OPCODES = {}
for _line in _TABLE.split('\n'):
    _words = _line.split()
    for _mode, _code in zip(_words[1::2], _words[2::2]):
        OPCODES[int(_code, 16)] = (_words[0], _mode)

BRANCHES = {'BCC', 'BCS', 'BEQ', 'BMI', 'BNE', 'BPL', 'BVC', 'BVS'}
WRITES = {'STA', 'STX', 'STY', 'INC', 'DEC', 'ASL', 'LSR', 'ROL', 'ROR'}
MEMORY_MODES = {'zp', 'zpx', 'zpy', 'abs', 'absx', 'absy', 'ind', 'indx', 'indy'}


class Instruction:
    __slots__ = ('address', 'opcode', 'mnemonic', 'mode', 'length', 'operand')

    def __init__(self, address, opcode, mnemonic, mode, operand):
        self.address, self.opcode, self.mnemonic, self.mode = address, opcode, mnemonic, mode
        self.length, self.operand = LENGTH[mode], operand

    @property
    def target(self):
        """The address a branch, jump or call goes to; None for JMP (ind)."""
        if self.mode == 'rel':
            return (self.address + 2 + (self.operand ^ 0x80) - 0x80) & 0xffff
        if self.mnemonic in ('JMP', 'JSR') and self.mode == 'abs':
            return self.operand
        return None

    @property
    def writes(self):
        return self.mnemonic in WRITES and self.mode != 'acc'

    def __repr__(self):
        return f'${self.address:04x} {self.mnemonic} {self.mode} ${self.operand or 0:x}'


class Image:
    """Bytes at addresses; holes allowed. `name_at` says which block a byte is from."""

    def __init__(self):
        self.memory = {}
        self.owner = {}

    def load(self, name, base, data):
        for i, byte in enumerate(data):
            self.memory[base + i] = byte
            self.owner[base + i] = name
        return self

    def decode(self, address):
        """The instruction at an address, or None (undocumented opcode or a hole)."""
        opcode = self.memory.get(address)
        if opcode not in OPCODES:
            return None
        mnemonic, mode = OPCODES[opcode]
        length = LENGTH[mode]
        if any(address + i not in self.memory for i in range(length)):
            return None
        operand = None
        if length == 2:
            operand = self.memory[address + 1]
        elif length == 3:
            operand = self.memory[address + 1] | self.memory[address + 2] << 8
        return Instruction(address, opcode, mnemonic, mode, operand)


# A branch right after one of these is always or never taken.
_ALWAYS = {('CLC', 'BCC'), ('SEC', 'BCS'), ('CLV', 'BVC')}
_NEVER = {('CLC', 'BCS'), ('SEC', 'BCC'), ('CLV', 'BVS')}
_OPPOSITE = {('BNE', 'BEQ'), ('BCC', 'BCS'), ('BPL', 'BMI'), ('BVC', 'BVS')}


def _fixed_branch(previous, branch):
    """True if the branch is always taken given the instruction before it,
    False if never, None if it depends."""
    if previous is None:
        return None
    pair = (previous.mnemonic, branch.mnemonic)
    if pair in _OPPOSITE or pair[::-1] in _OPPOSITE:
        return True   # the first one was not taken, so this one is
    if pair in _ALWAYS:
        return True
    if pair in _NEVER:
        return False
    if previous.mnemonic in ('LDA', 'LDX', 'LDY') and previous.mode == 'imm':
        value = previous.operand
        return {'BEQ': value == 0, 'BNE': value != 0,
                'BPL': value < 0x80, 'BMI': value >= 0x80}.get(branch.mnemonic)
    return None


class Trace:
    """Result of following code from a set of entries.

    instructions: address -> Instruction for every instruction reached
    code:         every byte that belongs to one of them
    references:   target address -> set of (from address, kind); kind is
                  'jsr', 'jmp', 'branch', or 'read'/'write'/'modify' for data
    problems:     (address, reason, entry) where a path stopped unexpectedly
    """

    def __init__(self, image, no_return=(), stop=()):
        self.image = image
        self.no_return = set(no_return)   # subroutines that do not come back
        self.stop = set(stop)             # addresses a path must not enter
        self.instructions, self.code = {}, set()
        self.references, self.problems = {}, []
        self.entries = {}                 # entry -> why

    def refer(self, target, source, kind):
        self.references.setdefault(target, set()).add((source, kind))

    def follow(self, queue, target, entry):
        """Queue a jump target; one outside the image is only a reference."""
        if target in self.image.memory:
            queue.append((target, entry, None))

    def run(self, entries):
        """entries: {address: reason}. May be called again with more."""
        queue = []
        for address, reason in entries.items():
            if address not in self.entries:
                self.entries[address] = reason
                queue.append((address, address, None))
        while queue:
            address, entry, previous = queue.pop()
            while True:
                if address in self.instructions or address in self.stop:
                    break
                inst = self.image.decode(address)
                if inst is None:
                    if address in self.image.memory:
                        self.problems.append((address, f'undocumented opcode ${self.image.memory[address]:02x}', entry))
                    else:
                        self.problems.append((address, 'ran outside the image', entry))
                    break
                overlap = [a for a in range(address, address + inst.length) if a in self.code]
                if overlap:
                    self.problems.append((address, 'overlaps an instruction already found', entry))
                self.instructions[address] = inst
                self.code.update(range(address, address + inst.length))
                m = inst.mnemonic
                if inst.mode in MEMORY_MODES and m not in ('JMP', 'JSR'):
                    kind = 'write' if m in ('STA', 'STX', 'STY') else 'modify' if inst.writes else 'read'
                    self.refer(inst.operand, address, kind)
                if m in BRANCHES:
                    fixed = _fixed_branch(previous, inst)
                    self.refer(inst.target, address, 'branch')
                    if fixed is not False:
                        self.follow(queue, inst.target, entry)
                    if fixed is True:
                        break
                elif m == 'JSR':
                    self.refer(inst.target, address, 'jsr')
                    self.follow(queue, inst.target, entry)
                    if inst.target in self.no_return:
                        break
                elif m == 'JMP':
                    if inst.mode == 'abs':
                        self.refer(inst.target, address, 'jmp')
                        self.follow(queue, inst.target, entry)
                    else:
                        self.refer(inst.operand, address, 'read')
                    break
                elif m in ('RTS', 'RTI'):
                    break
                elif m == 'BRK':
                    self.problems.append((address, 'BRK', entry))
                    break
                previous = inst
                address += inst.length
        return self

    def linear(self, start, end):
        """Decode start..end as straight-line code; None if it does not fit."""
        out, address = [], start
        while address < end:
            inst = self.image.decode(address)
            if inst is None or address + inst.length > end:
                return None
            out.append(inst)
            address += inst.length
        return out
