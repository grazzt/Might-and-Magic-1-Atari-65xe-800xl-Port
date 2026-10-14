#!/usr/bin/env python3
"""Capture palette workloads and compare complete colour-policy calculations.

--capture outdoors|fight|encounter replays existing first-poll Atari scripts.
Capture each scenario in its own process: libatari800 is a single machine.
--check BASELINE profiles saved snapshots and tests adversarial palette inputs.
Walking keeps the frozen selection; corrected encounters use direct enumeration.
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
import lockstep
import mos6502
from graphics_profile import exact_penalty
import colour_policy

SCENARIOS = {
    'outdoors': ('boot-to-outdoors', ['town', 'gate', 'outdoors']),
    'fight': ('boot-to-fight-and-save', ['town', 'dungeon', 'arena', 'fight']),
    'encounter': ('boot-to-treasure-and-reload', ['encounter']),
    'lair': ('boot-to-death', ['lair']),
    'portal': ('boot-to-side-d', ['portal']),
}


def labels(layout):
    return {k: int(v[1:],16) for k,v in layout['labels'].items()}


def capture(scenario, out):
    script, marks = SCENARIOS[scenario]
    lines = (ROOT/f'tools/traces/{script}.txt').read_text().splitlines()
    last = next(i for i,line in enumerate(lines) if line.split('#')[0].split()==['mark', marks[-1]])
    lines = lines[:last+1]
    if scenario == 'fight':
        lines += ['press 41', 'ready', 'mark fight-attack']
        marks = marks + ['fight-attack']
    layout = build.build(test=True)
    game = lockstep.Game(layout)
    out.mkdir(parents=True,exist_ok=True)
    report = dict(scenario=scenario, labels=layout['labels'], screens=[])
    waiting = False
    for words in lockstep.atari_steps(lines):
        op, values = words[0], words[1:]
        if op == 'press':
            game.press(int(values[0],16)); waiting = False
        elif op == 'ready':
            game.ready(); waiting = True
        elif op == 'wait':
            game.idle(); waiting = False
        elif op == 'key':
            game.keys([int(v,16) for v in values]); waiting = False
        elif op == 'attach':
            game.memory[game.label['side']] = 'ABCD'.index(values[0])
        elif op == 'poke':
            for i,value in enumerate(values[1:]):
                address, byte = int(values[0],16)+i,int(value,16)
                if address == lockstep.KEY_WAIT_COUNT and waiting:
                    byte = (byte+1)&255
                game.memory[address] = byte
        elif op == 'pauses':
            game.ready()
            game.memory[game.label['pause_key']] = 0 if values[0]=='off' else int(values[0],16)
        elif op == 'mark' and values[0] in marks:
            name = values[0]
            game.frames(2)
            game.atari.screenshot(out/f'{name}.png')
            main = bytes(game.memory)
            ignored = set(lockstep.TIMING) | set(lockstep.MACHINE)
            for first,last,_ in lockstep.IGNORED:
                ignored.update(range(first,last+1))
            digest = hashlib.sha256(bytes(v for i,v in enumerate(main) if i not in ignored)).hexdigest()
            lib = game.atari._lib
            port = ctypes.c_ubyte.in_dll(lib,'PIA_PORTB').value
            lib.PIA_PutByte.argtypes = [ctypes.c_uint16,ctypes.c_ubyte]
            lib.PIA_PutByte(0xd301,port&~0x10)
            try:
                snapshot = bytes(game.memory)
            finally:
                lib.PIA_PutByte(0xd301,port)
            (out/f'{name}.bin').write_bytes(snapshot)
            report['screens'].append(dict(name=name,mode=main[0x389],game_sha256=digest))
            print(scenario,name,'mode',main[0x389])
        elif op not in ('mark','skip'):
            raise AssertionError(words)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def capture_altirra(scenario, out):
    """Same first-poll route through the second emulator, with real ANTIC output."""
    from speed_check import Runner
    script, marks = SCENARIOS[scenario]
    lines=(ROOT/f'tools/traces/{script}.txt').read_text().splitlines()
    last=next(i for i,line in enumerate(lines) if line.split('#')[0].split()==['mark',marks[-1]])
    layout=build.build(test=True)
    out.mkdir(parents=True,exist_ok=True)
    runner=Runner(layout,'altirra',out)
    lab=runner.label
    report=dict(scenario=scenario,emulator='altirra',labels=layout['labels'],screens=[])
    current='boot'
    def until(condition):
        for _ in range(600):
            if condition(): return
            runner.emulator.frame(5)
        runner.emulator.screenshot(out/'failed.png')
        raise AssertionError(f'Altirra route timed out at {current}; '
                             f'PC {runner.emulator.registers()}; '
                             f'clock {runner.read(0xa0,3).hex()}, target {runner.read(0xc353,2).hex()}')
    ready=lambda:until(lambda:runner.read(lab['waiting'])[0])
    waiting=False
    try:
        # Power-on RAM at the kernel's future flag addresses is not initialized
        # in Altirra. Observe the printed prompt before trusting those flags.
        until(lambda:b'INSERT DISK B' in runner.read(0x400,1000))
        for words in lockstep.atari_steps(lines[:last+1]):
            current=' '.join(words)
            op,values=words[0],words[1:]
            if op=='press':
                ready();runner.write(lab['script_key'],int(values[0],16))
                until(lambda:not runner.read(lab['script_key'])[0]);waiting=False
            elif op=='ready':ready();waiting=True
            elif op=='wait':
                runner.emulator.frame(2);runner.write(lab['idle'],0)
                until(lambda:runner.read(lab['idle'])[0] or runner.read(lab['waiting'])[0]);waiting=False
            elif op=='key':
                for i,value in enumerate(values):runner.write(0x277+i,int(value,16))
                runner.write(0xc6,len(values));waiting=False
            elif op=='attach':runner.write(lab['side'],'ABCD'.index(values[0]))
            elif op=='poke':
                for i,value in enumerate(values[1:]):
                    address=int(values[0],16)+i;byte=int(value,16)
                    if address==lockstep.KEY_WAIT_COUNT and waiting:byte=(byte+1)&255
                    runner.write(address,byte)
            elif op=='pauses':
                ready();runner.write(lab['pause_key'],0 if values[0]=='off' else int(values[0],16))
            elif op=='mark' and values[0] in marks:
                name=values[0];runner.emulator.frame(2)
                runner.emulator.screenshot(out/f'{name}.png')
                main=runner.read(0,65536)
                images={n:(build.OUT/n).read_bytes() for n in build.SEGMENTS}
                assert not lockstep.kernel_changes(main,layout['fixed'],images),name
                snapshot=bytearray(main)
                snapshot[0x4000:0x8000]=runner.display_memory(0x4000,0x4000)
                if main[0x389]:
                    assert result(snapshot,lab)==colour_policy.convert(snapshot,main[0x389])[:2],name
                (out/f'{name}.bin').write_bytes(snapshot)
                ignored=set(lockstep.TIMING)|set(lockstep.MACHINE)
                for first,end,_ in lockstep.IGNORED:ignored.update(range(first,end+1))
                digest=hashlib.sha256(bytes(v for i,v in enumerate(main) if i not in ignored)).hexdigest()
                report['screens'].append(dict(name=name,mode=main[0x389],game_sha256=digest))
                print('altirra',scenario,name,'mode',main[0x389],flush=True)
            elif op not in ('mark','skip'):raise AssertionError(words)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:
        runner.emulator.close()


def execute(snapshot, lab, entry='refresh'):
    mem = bytearray(snapshot)
    cpu = mos6502.CPU(mem)
    cpu.io_read = lambda address: mem[address]
    cpu.special = lambda address,value: mem.__setitem__(address,value)
    cpu.pc, cpu.s = lab[entry],0xfd
    mem[0x1fe:0x200] = bytes([255,1])
    cpu.hooks[:] = bytes([1])*65536
    previous, phase = None,'other'
    cycles, rows = Counter(),[]
    def hook(pc):
        nonlocal previous,phase
        if previous:
            clock,penalty,group = previous
            cycles[group] += cpu.cycles-clock+penalty
        if pc == 0x200:
            return True
        if pc == lab['choose_colours']:
            phase = 'palette'
        if pc == lab['rf_both']+3:
            phase = 'other'
        if pc == lab['cc_near'] and cpu.x==15:
            rows.append(dict(row=mem[lab['row']],event='rebuild',
                             chosen=list(mem[lab['chosen']:lab['chosen']+3])))
        if pc == lab['cc_restore']:
            ptr=mem[0xf2]|mem[0xf3]<<8
            rows.append(dict(row=mem[lab['row']],event='restore',chosen=list(mem[ptr+57:ptr+60])))
        if pc == lab.get('cc_shared_hit'):
            rows.append(dict(row=mem[lab['row']],event='shared',
                             chosen=list(mem[lab['chosen']:lab['chosen']+3])))
        previous=(cpu.cycles,exact_penalty(cpu,pc),phase)
        return False
    cpu.on_hook=hook
    cpu.run(2_000_000)
    assert cpu.pc==0x200
    return mem,dict(cycles=dict(cycles),events=rows)


def result(mem, lab, row=None):
    if row is not None:
        return (bytes(mem[lab['pair']:lab['pair']+16]),bytes(mem[lab['pair4']:lab['pair4']+16]),
                bytes(mem[lab[n]+row] for n in ('row_pf0','row_pf1','row_pf2','row_pf3')))
    return (b''.join(mem[0x4000+r//3*1024+r%3*320:0x4000+r//3*1024+r%3*320+320] for r in range(25)),
            b''.join(mem[lab[n]:lab[n]+25] for n in ('row_pf0','row_pf1','row_pf2','row_pf3')))


def check(baseline, out):
    layout=build.build()
    new=labels(layout)
    report=dict(screens=[],cases=[])
    first=next(baseline.rglob('town.bin'))
    original=first.read_bytes()
    old=labels(json.loads(first.with_name('report.json').read_text()))
    def kernel(snapshot, optimized):
        mem=bytearray(snapshot)
        source_labels,target_labels=(old,new) if optimized else (new,old)
        palettes={n: bytes(mem[source_labels[n]:source_labels[n]+25])
                  for n in ('row_pf0','row_pf1','row_pf2','row_pf3')}
        for base,name in ((0x6800,'ext.bin'),(0x7c00,'ext2.bin')):
            mem[base:base+1024]=(build.OUT/name).read_bytes() if optimized else original[base:base+1024]
        if optimized and 'mapping_chosen' in new:
            address=new['mapping_chosen']
            mem[address:address+3]=bytes([255]*3)
        if optimized:
            first=new['idempotent']
            mem[first:first+16]=(build.OUT/'top.bin').read_bytes()[first-0xff50:first-0xff50+16]
        for n,data in palettes.items():
            mem[target_labels[n]:target_labels[n]+25]=data
        return mem
    for path in sorted(baseline.rglob('*.bin')):
        snapshot=path.read_bytes()
        before,bp=execute(snapshot,old)
        assert result(before,old)==result(snapshot,old), ('native publication',path)
        after,ap=execute(kernel(snapshot,True),new)
        wanted=colour_policy.convert(snapshot,1)[:2] if snapshot[0x389]==1 else result(before,old)
        assert result(after,new)==wanted,path
        # A second pass checks shared state populated by real cache restores.
        again,wp=execute(after,new)
        assert result(again,new)==wanted,path
        report['screens'].append(dict(screen=str(path.relative_to(baseline)),mode=snapshot[0x389],
                                      before=bp,after=ap,warm=wp))
    patterns=[('view-panel',[0x12]*30+[0x34]*10,[1]*30+[3]*10),
              ('uniform',[0x12]*40,[6]*40),
              ('ram-high-bits',[0x12]*40,[0xa6]*40),
              ('varied',[0x12]*30+[0x34]*10,[1,2,3,4]*10),
              ('matrix-swapped',[0x21]*30+[0x43]*10,[1]*30+[3]*10),
              ('tie',[0x12,0x34]*20,[5,6]*20),
              ('all-black',[0]*40,[0]*40)]
    state=kernel(original,True)
    state[0x389]=2  # cache/mapping policy stays exact for walking and lower text
    for row in (0,5,6,13,14,15,16,24):
        for cold in (True,False):
            for name,matrix,cram in patterns*2:
                state[new['row']]=row
                state[new['shown_mode']]=0 if cold else 2
                state[0xf4:0xf8]=bytes([0,4,0,0xd8])
                state[0x400:0x428],state[0xd800:0xd828]=bytes(matrix),bytes(cram)
                reference=kernel(state,False)
                reference[old['row']]=row
                reference[old['shown_mode']]=0  # force full original calculation
                expected,_=execute(reference,old,'choose_colours')
                actual,profile=execute(state,new,'choose_colours')
                assert result(actual,new,row)==result(expected,old,row),(row,cold,name)
                if name=='all-black':
                    assert list(actual[new['pair']:new['pair']+16])==[0]*16
                report['cases'].append(dict(row=row,cold=cold,case=name,
                                          shared_hits=sum(e['event']=='shared' for e in profile['events'])))
                state=actual
    # Build A, build B, restore cached A, then request B without a row cache.
    # Keeping B's key while restoring A's pairs would cause an incorrect hit.
    for row,cold,name,value,color in ((6,True,'build-A',0x12,6),
                                     (7,True,'build-B',0x78,1),
                                     (6,False,'restore-A',0x12,6),
                                     (0,False,'B-after-restore-A',0x78,1)):
        state[new['row']]=row
        state[new['shown_mode']]=0 if cold else 2
        state[0xf4:0xf8]=bytes([0,4,0,0xd8])
        state[0x400:0x428],state[0xd800:0xd828]=bytes([value]*40),bytes([color]*40)
        reference=kernel(state,False)
        reference[old['row']],reference[old['shown_mode']]=row,0
        expected,_=execute(reference,old,'choose_colours')
        state,profile=execute(state,new,'choose_colours')
        assert result(state,new,row)==result(expected,old,row),name
        if name=='restore-A' and 'mapping_chosen' in new:
            assert state[new['mapping_chosen']]==255, 'Restore left a stale live key'
        shared=sum(e['event']=='shared' for e in profile['events'])
        if name=='B-after-restore-A':
            assert shared==0, 'Cached A falsely advertised B'
        report['cases'].append(dict(row=row,cold=cold,case=name,shared_hits=shared))
    out.mkdir(parents=True,exist_ok=True)
    (out/'palette-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print('OK:',len(report['screens']),'complete screen comparisons;',len(report['cases']),'palette cases')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',choices=SCENARIOS)
    parser.add_argument('--check',type=Path)
    parser.add_argument('--emulator',choices=['atari800','altirra'],default='atari800')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.capture:
            (capture_altirra if args.emulator=='altirra' else capture)(args.capture,args.out)
        elif args.check:
            check(args.check,args.out)
        else:
            parser.error('choose --capture or --check')
    finally:
        build.build()
