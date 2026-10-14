#!/usr/bin/env python3
"""Profile the graphics kernel using temporary Atari800 RAM probes.

python3 port/atari/graphics_profile.py --out build/atari/graphics-profile
--experiment skip: bypass conversion (stale display), diagnostic upper bound.
--experiment blank: disable DMA during conversion (black flash), diagnostic.
No instrumented bytes are written to the ATR or production assembly source.
"""
import argparse
from collections import Counter
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'port/atari')]
import build
import code6502
import lockstep
import mos6502
from speed_check import Runner, ACTION_KEYS


class Probes:
    """Replace selected instructions with registered two-byte emulator escapes.

    The callback executes the displaced instruction and accounts for its CPU
    cycles. No additional emulated instructions or register/flag clobbers.
    Scanline clock stamps have 114-cycle resolution, avoiding the internal
    CPU-to-ANTIC cycle mapping in Atari800's cycle-exact core.
    """
    CALLBACK = ctypes.CFUNCTYPE(None)

    def __init__(self, runner, experiment):
        self.runner, self.atari, self.lab = runner, runner.emulator, runner.label
        self.lib = self.atari._lib
        self.reg = {k: typ.in_dll(self.lib, 'CPU_reg' + k)
                    for k, typ in [('PC', ctypes.c_uint16), *[(r, ctypes.c_ubyte) for r in 'AXYSP']]}
        self.clock = ctypes.c_uint.in_dll(self.lib, 'ANTIC_screenline_cpu_clock')
        self.xpos = ctypes.c_int.in_dll(self.lib, 'ANTIC_xpos')
        self.hooks, self.events, self.snapshots = {}, [], []
        self.errors = []
        self.action, self.experiment = None, experiment
        self.lib.ESC_Add.argtypes = [ctypes.c_uint16, ctypes.c_ubyte, self.CALLBACK]
        self.lib.PIA_PutByte.argtypes = [ctypes.c_uint16, ctypes.c_ubyte]
        self.lib.ANTIC_PutByte.argtypes = [ctypes.c_uint16, ctypes.c_ubyte]
        # ca65's repeated operand aliases are not present in ld65's label file.
        code_image = (build.OUT / 'ext.bin').read_bytes()
        offset = self.lab['rf_cell'] - 0x6800
        sequence = bytes([0xb1, 0xf0, 0xaa, 0xbd, 0, 0x6c, 0x91, 0xf2, 0x88])
        points = [i for i in range(offset, offset + 150) if code_image[i:i+9] == sequence]
        assert len(points) in (1, 2, 4, 8)  # partially/fully unrolled layouts
        self.lab.update({f'table{i}': 0x6800+p+4 for i,p in enumerate(points)})
        # Label the call and its return, including the true conversion exit.
        start, end = self.lab['getin'], self.lab['keyboard']
        code = runner.read(start, end - start)
        call = start + code.index(bytes([0x20, self.lab['refresh'] & 255, self.lab['refresh'] >> 8]))
        self.install(call, 'refresh-start')
        self.install(call + 3, 'refresh-end')
        self.install(self.lab['rf_row'], 'row-start')
        self.install(self.lab['choose_colours'], 'palette-start')
        cstart = self.lab['rf_both']
        self.install(cstart + 3, 'palette-end')
        self.install(self.lab['rf_cell'], 'cell')
        # First-poll key consumed and the following wait entered.
        script = bytes([0x8e, self.lab['script_key'] & 255, self.lab['script_key'] >> 8])
        self.install(start + code.index(script), 'key-taken')
        wait = bytes([0x8d, self.lab['waiting'] & 255, self.lab['waiting'] >> 8])
        self.install(start + code.index(wait), 'wait-entered')
        nmi = runner.read(self.lab['nmi'], self.lab['vbi']-self.lab['nmi'])
        dli = bytes([0xae, self.lab['dli_row'] & 255, self.lab['dli_row'] >> 8])
        self.install(self.lab['nmi']+nmi.index(dli), 'dli')

    def bank(self, extended):
        old = ctypes.c_ubyte.in_dll(self.lib, 'PIA_PORTB').value
        self.lib.PIA_PutByte(0xd301, old & ~0x10 if extended else old)
        return old

    def install(self, address, name):
        old_port = self.bank(0x4000 <= address < 0x8000)
        mem = self.atari.memory
        op = mem[address]
        mnemonic, mode = code6502.OPCODES[op]
        length = code6502.LENGTH[mode]
        assert length >= 2, (hex(address), mnemonic, mode)
        assert (mnemonic, mode) in {('JSR','abs'), ('LDA','imm'), ('LDY','imm'),
                                     ('LDA','abs'), ('LDX','abs'), ('STA','abs'), ('STX','abs')}
        raw = bytes(mem[address:address + length])
        code = 0x70 + len(self.hooks)  # unused by this emulator's OS/device escapes
        callback = self.CALLBACK(lambda: self.hit(address, name, raw, mnemonic, mode))
        self.lib.ESC_Add(address, code, callback)
        self.hooks[address] = (raw, code, callback)
        self.lib.PIA_PutByte(0xd301, old_port)

    def snapshot(self):
        # Called while getin has already selected the extended CPU bank.
        mem = bytearray(self.atari.memory)
        for address, (raw, _, _) in self.hooks.items():
            mem[address:address + len(raw)] = raw
        return bytes(mem)

    def hit(self, address, name, raw, mnemonic, mode):
        try:
            mem, reg = self.atari.memory, self.reg
            row = reg['X'].value if name in ('row-start', 'palette-start') else mem[self.lab['row']]
            if self.action:
                event = dict(action=self.action, event=name, clock=self.clock.value, row=row,
                             mode=mem[0x389], shown=mem[self.lab['shown_mode']])
                if name == 'cell':
                    matrix = mem[0xf4] | mem[0xf5] << 8
                    value = mem[matrix]
                    event['table'] = mem[self.lab['pair']+(value >> 4)] | mem[self.lab['pair4']+(value & 15)]
                self.events.append(event)
                if name in ('refresh-start', 'refresh-end'):
                    self.snapshots.append((self.action, name, self.snapshot()))
            if mnemonic == 'JSR':
                if name == 'refresh-start' and self.experiment == 'skip':
                    reg['PC'].value = address + 3
                    self.xpos.value += 10  # JSR + RTS, escape already charged 2
                    return
                if name == 'refresh-start' and self.experiment == 'blank' and mem[0x389]:
                    mem[self.lab['frame_ready']] = 0
                    self.lib.ANTIC_PutByte(0xd400, 0)
                ret = address + 2
                mem[0x100 + reg['S'].value] = ret >> 8
                reg['S'].value = (reg['S'].value - 1) & 255
                mem[0x100 + reg['S'].value] = ret & 255
                reg['S'].value = (reg['S'].value - 1) & 255
                reg['PC'].value = raw[1] | raw[2] << 8
                self.xpos.value += 4
                return
            operand = raw[1] if mode == 'imm' else mem[raw[1] | raw[2] << 8]
            if mnemonic in ('LDA', 'LDX', 'LDY'):
                reg[mnemonic[-1]].value = operand
                reg['P'].value = (reg['P'].value & ~0x82) | (operand & 0x80) | (2 if operand == 0 else 0)
            else:
                mem[raw[1] | raw[2] << 8] = reg[mnemonic[-1]].value
            reg['PC'].value = address + len(raw)
            self.xpos.value += (2 if mode == 'abs' else 0)
        except BaseException as error:
            self.errors.append(repr(error))

    def remove(self):
        for address, (raw, code, _) in self.hooks.items():
            old = self.bank(0x4000 <= address < 0x8000)
            for i, value in enumerate(raw):
                self.atari.memory[address+i] = value
            self.lib.ESC_Remove(code)
            self.lib.PIA_PutByte(0xd301, old)


def exact_penalty(cpu, pc):
    """Page penalties omitted by the host core, observed before each instruction."""
    mem = cpu.mem
    mnemonic, mode = code6502.OPCODES[mem[pc]]
    if mnemonic in ('STA','STX','STY','ASL','LSR','ROL','ROR','INC','DEC'):
        return 0
    if mode in ('absx','absy'):
        base = mem[pc+1] | mem[pc+2] << 8
        index = cpu.x if mode == 'absx' else cpu.y
        return int((base & 255) + index > 255)
    if mode == 'indy':
        zp = mem[pc+1]
        return int(mem[zp] + cpu.y > 255)
    if mode == 'rel':
        flag = {'BPL':0x80, 'BMI':0x80, 'BNE':2, 'BEQ':2,
                'BCC':1, 'BCS':1, 'BVC':0x40, 'BVS':0x40}[mnemonic]
        taken = bool(cpu.p & flag) == (mnemonic in ('BMI','BEQ','BCS','BVS'))
        delta = mem[pc+1]
        target = (pc + 2 + (delta if delta < 128 else delta-256)) & 65535
        return int(taken and (pc+2) // 256 != target // 256)
    return 0


def cpu_profile(snapshot, expected, lab):
    mem = bytearray(snapshot)
    cpu = mos6502.CPU(mem)
    cpu.io_read = lambda address: mem[address]
    cpu.special = lambda address, value: mem.__setitem__(address, value)
    cpu.pc, cpu.s = lab['refresh'], 0xfd
    mem[0x1fe:0x200] = bytes([0xff, 1])  # return to stop hook at $0200
    cpu.hooks[:] = bytes([1]) * 65536
    previous = None
    by_pc, cycles = Counter(), Counter()
    rows = [Counter() for _ in range(25)]
    maps, palette_paths = Counter(), Counter()
    row_maps = [Counter() for _ in range(25)]
    last_table, repeats, zero_bytes, identity_cells, cell_count = None, 0, 0, 0, 0
    phase, row = 'setup', 0
    def hook(pc):
        nonlocal previous, phase, row, last_table, repeats, zero_bytes, identity_cells, cell_count
        if previous is not None:
            oldpc, oldcycles, penalty, oldphase, oldrow = previous
            cost = cpu.cycles - oldcycles + penalty
            by_pc[oldpc] += cost
            cycles[oldphase] += cost
            rows[oldrow][oldphase] += cost
        if pc == 0x0200:
            return True
        if pc == lab['rf_row']:
            row, phase = cpu.x, 'row-setup'
        if pc == lab['choose_colours']:
            phase = 'palette'
        if pc == lab['rf_both']+3:
            phase = 'cell-setup'
        if pc == lab.get('reuse_row'):
            phase = 'row-check'
        if pc == lab['cc_scan']:
            palette_paths['histogram'] += 1
        if pc == lab.get('cc_new_mapping', lab['cc_rebuild']):
            palette_paths['mapping-rebuild'] += 1
        if pc == lab.get('cc_shared_hit'):
            palette_paths['shared-mapping-hit'] += 1
        if pc == lab['cc_restore']:
            palette_paths['mapping-restore'] += 1
        if pc == lab['rf_cell']:
            phase = 'cell-setup'
            source = mem[0xf0] | mem[0xf1] << 8
            matrix = mem[0xf4] | mem[0xf5] << 8
            value = mem[matrix]
            pair = mem[lab['pair'] + (value >> 4)]
            pair4 = mem[lab['pair4'] + (value & 15)]
            table = pair | pair4
            maps[table] += 1
            row_maps[row][table] += 1
            repeats += table == last_table
            last_table = table
            identity_cells += table == 9
            zero_bytes += bytes(mem[source:source+8]).count(0)
            cell_count += 1
        if pc == lab['table0']-4:
            phase = 'pixels'
        if pc == lab.get('rf_identity', -2)+2:
            phase = 'pixels'
        # The pixel loop exits at the CLC that advances both pointers.
        if pc == (lab['rf_advance'] if 'rf_advance' in lab else lab['table7'] + 5):
            phase = 'advance'
        previous = (pc, cpu.cycles, exact_penalty(cpu, pc), phase, row)
        return False
    cpu.on_hook = hook
    cpu.run(2_000_000)
    assert cpu.pc == 0x0200
    # Independent completed-output comparison with the real emulator.
    assert mem[0x4000:0x6400] == expected[0x4000:0x6400]
    assert all(mem[lab[n]:lab[n]+25] == expected[lab[n]:lab[n]+25]
               for n in ('row_pf0','row_pf1','row_pf2','row_pf3'))
    return dict(cycles=dict(cycles), total_cycles=sum(cycles.values()),
                rows=[dict(r) for r in rows], palette_paths=dict(palette_paths),
                cells=cell_count, table_histogram=dict(maps), row_tables=[dict(r) for r in row_maps], table_repeats=repeats,
                identity_cells=identity_cells, zero_source_bytes=zero_bytes,
                hot_instructions=[dict(pc=f'${pc:04x}', cycles=count,
                                       op=code6502.OPCODES[snapshot[pc]][0])
                                  for pc,count in by_pc.most_common(20)])


def source_rows(mem):
    mode = mem[0x389]
    result = []
    for row in range(25):
        upper = mode == 2 and row < 16
        pixels = (0x2000 if upper else 0xe000) + row*320
        matrix = (0x0400 if upper else 0xcc00) + row*40
        cram = 0xd800 + row*40
        result.append([mem[pixels:pixels+320],mem[matrix:matrix+40],mem[cram:cram+40]])
    return result



def row_skip_candidates(before, after, lab):
    """Exact proposed skip predicate, no raw cache and no hash assumptions.

    If unchanged palette inputs select the same idempotent mapping f, the old
    output f(old_raw) is a fixed point. If new_raw equals that output, applying
    f again cannot change it. Reject non-idempotent maps such as pair swapping.
    This is a predicate experiment, not a deployed conversion optimization.
    """
    raw = source_rows(before)
    pages = [before[0x6c00+i*256:0x6d00+i*256] for i in range(16)]
    idempotent = [all(page[page[v]]==page[v] for v in range(256)) for page in pages]
    assert not idempotent[6] and pages[6][pages[6][0x55]] != pages[6][0x55]
    candidates=[]
    for row in range(6,25):
        cache = before[lab['palette_low']+row] | before[lab['palette_high']+row]<<8
        pixels,matrix,cram = raw[row]
        tag = before[cache+56]
        exact_inputs = (before[lab['shown_mode']] != 0 and tag != 255
                        and all((value & 15)==tag for value in cram)
                        and before[cache:cache+40]==matrix)
        if not exact_inputs:
            continue
        pairs = before[cache+40:cache+56]
        safe_maps = all(idempotent[pairs[value>>4] | (pairs[value & 15]<<2)] for value in matrix)
        dest=0x4000+row//3*1024+row%3*320
        equal=pixels==before[dest:dest+320]
        if exact_inputs and safe_maps and equal:
            assert before[dest:dest+320]==after[dest:dest+320]
            assert all(before[lab[n]+row]==after[lab[n]+row] for n in ('row_pf0','row_pf1','row_pf2','row_pf3'))
            candidates.append(row)
    return dict(rows=candidates, idempotent_tables=[i for i,v in enumerate(idempotent) if v])


def change_profile(previous, before, after, lab):
    raw = source_rows(before)
    old = source_rows(previous) if previous is not None else None
    rows = []
    for row in range(25):
        address = 0x4000 + row//3*1024 + row%3*320
        palettes = [after[lab[n]+row] for n in ('row_pf0','row_pf1','row_pf2','row_pf3')]
        prior_palettes = [before[lab[n]+row] for n in ('row_pf0','row_pf1','row_pf2','row_pf3')]
        byte_changes = sum(a != b for a,b in zip(before[address:address+320],after[address:address+320]))
        cell_changes = sum(before[address+c*8:address+c*8+8] != after[address+c*8:address+c*8+8] for c in range(40))
        source_changes = None if old is None else sum(
            raw[row][0][c*8:c*8+8] != old[row][0][c*8:c*8+8]
            or raw[row][1][c] != old[row][1][c]
            or (raw[row][2][c] & 15) != (old[row][2][c] & 15) for c in range(40))
        rows.append(dict(row=row, converted_bytes_changed=byte_changes,
                         converted_cells_changed=cell_changes, palette_changed=palettes != prior_palettes,
                         raw_cells_changed=source_changes))
    return rows



def oracle_profiles():
    """Attribute original-game work; host cycle clock omits page penalties/DMA.

    Corrected instruction sums below add page penalties without changing the
    oracle's IRQ clock. Compare totals with the independently captured VICE
    timings in docs/SPEED.md rather than treating this as a real C64 clock.
    """
    import oracle
    player = oracle.Oracle()
    lines = (ROOT/'tools/traces/boot-to-town-services.txt').read_text().splitlines()
    player.play(lines[:lines.index('mark party')] + ['press 58','ready'])
    result = []
    ranges = [('view-control',0x0f1d,0x1110), ('wall-pieces',0x1111,0x1257),
              ('clear-view',0x1f36,0x1f64), ('copy-view-down',0x0dfd,0x0e36),
              ('bitmap-text',0x0cf8,0x0dfc), ('text-screen',0x0e55,0x0f1c),
              ('play-colours',0xc276,0xc2af), ('original-irq/sound',0xc5c5,0xc647)]
    for key,name,_ in ACTION_KEYS[1:]:
        cpu = player.cpu
        had_hooks, old_hook = bytes(cpu.hooks), cpu.on_hook
        cpu.hooks[:] = bytes([1])*65536
        previous = None
        cycles, instructions = Counter(), Counter()
        calls = Counter()
        def hook(pc):
            nonlocal previous
            if previous is not None:
                before,penalty,group = previous
                cycles[group] += cpu.cycles-before+penalty
                previous = None
            stopped = old_hook(pc)
            if stopped or cpu.pc != pc:
                return stopped
            group = next((group for group,first,last in ranges if first<=pc<=last),'other-game/KERNAL')
            instructions[group] += 1
            if pc in (0xf1d,0x1111,0x1f36,0xdfd,0xd1c):
                calls[f'${pc:04x}'] += 1
            previous = (cpu.cycles,exact_penalty(cpu,pc),group)
            return False
        cpu.on_hook = hook
        try:
            before=cpu.cycles
            player.play([f'press {key:02x}','ready'])
            if previous is not None:
                clock,penalty,group = previous
                cycles[group] += cpu.cycles-clock+penalty
            result.append(dict(action=name, host_clock_cycles=cpu.cycles-before,
                               corrected_instruction_cycles=dict(cycles),
                               instructions=dict(instructions), calls=dict(calls)))
        finally:
            cpu.hooks[:] = had_hooks
            cpu.on_hook = old_hook
    return result


def capture(out, experiment):
    out.mkdir(parents=True, exist_ok=True)
    layout = build.build(test=True)
    runner = Runner(layout, 'atari800', out)
    runner.until(lambda: b'INSERT DISK B' in runner.read(0x400,1000))
    runner.write(runner.label['side'],1)
    runner.write(0x277,0x0d); runner.write(0xc6,1)
    runner.until(lambda: runner.read(runner.label['waiting'])[0])
    runner.press(0x31,'inn',out)
    for key in range(1,7):
        runner.write(0x28e,4); runner.press(key,f'party-{key}',out); runner.write(0x28e,0)
    probes = Probes(runner, experiment)
    actions = []
    if experiment == 'control':
        probes.remove()
    try:
        for key,name,_ in ACTION_KEYS:
            probes.action = name
            action = runner.press(key,name,out,capture=(experiment == 'blank' and name in ('step','choose-character')))
            action.pop('states')
            state = bytes(runner.emulator.memory)
            ignored = set(lockstep.TIMING) | set(lockstep.MACHINE)
            for first,last,_ in lockstep.IGNORED:
                ignored.update(range(first,last+1))
            action['game_sha256'] = hashlib.sha256(bytes(b for i,b in enumerate(state) if i not in ignored)).hexdigest()
            actions.append(action)
        assert not probes.errors, probes.errors[:3]
        report = dict(experiment=experiment, labels=layout['labels'], actions=actions,
                      events=probes.events, refreshes=[])
        previous = None
        for i in range(0,len(probes.snapshots),2):
            name,event,before = probes.snapshots[i]
            name2,event2,after = probes.snapshots[i+1]
            assert name==name2 and event=='refresh-start' and event2=='refresh-end'
            (out/f'{i//2:02}-{name}-before.bin').write_bytes(before)
            (out/f'{i//2:02}-{name}-after.bin').write_bytes(after)
            item = dict(action=name, mode=before[0x389])
            if experiment == 'none':
                item['cpu'] = cpu_profile(before,after,runner.label)
                if before[0x389]:
                    item['changes'] = change_profile(previous,before,after,runner.label)
                    item['row_skip_candidate'] = row_skip_candidates(before,after,runner.label)
                    previous = before
            report['refreshes'].append(item)
        for action in actions:
            if experiment == 'control':
                continue
            events = [e for e in probes.events if e['action']==action['action']]
            start = next(e['clock'] for e in events if e['event']=='key-taken')
            end = next(e['clock'] for e in events if e['event']=='wait-entered')
            begins = [e for e in events if e['event']=='refresh-start']
            ends = [e for e in events if e['event']=='refresh-end']
            action['elapsed_cycles'] = (end-start) & 0xffffffff
            action['conversion_cycles'] = sum((b['clock']-a['clock']) & 0xffffffff for a,b in zip(begins,ends))
            action['other_cycles'] = action['elapsed_cycles']-action['conversion_cycles']
            action['conversion_dlis'] = sum(e['event']=='dli' and any(a['clock']<=e['clock']<b['clock'] for a,b in zip(begins,ends)) for e in events)
            print(action['action'], action['frames'], 'frames;', action['conversion_cycles'], 'conversion elapsed cycles')
        if experiment == 'none':
            report['oracle_original_game'] = oracle_profiles()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:
        if experiment != 'control':
            probes.remove()
        # Instrumentation existed only in emulator RAM.
    return report


def run(out, experiment):
    try:
        return capture(out,experiment)
    finally:
        build.build(test=False)  # also restore after setup or analysis failure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=build.OUT/'graphics-profile')
    parser.add_argument('--experiment',choices=('none','skip','blank','control'),default='none')
    args=parser.parse_args()
    run(args.out,args.experiment)


if __name__=='__main__':
    main()
