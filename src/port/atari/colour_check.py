#!/usr/bin/env python3
"""Check the corrected colour policy against independent pixel enumeration.

python3 port/atari/colour_check.py --out build/atari/colour-check
Old native frames prove the reference model reproduces the previous policy;
new/cached frames and adversarial bitmap changes must match the corrected one.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'port/atari')]
import build
import colour_policy as policy
import mos6502
import palette_check

BASELINE = ROOT/'test-artifacts/colour-selection/before'


def inject(snapshot, old, new):
    state = bytearray(snapshot)
    palettes = {n:bytes(state[old[n]:old[n]+25]) for n in ('row_pf0','row_pf1','row_pf2','row_pf3')}
    for base,name in ((0x6800,'ext.bin'),(0x7c00,'ext2.bin')):
        state[base:base+1024] = (build.OUT/name).read_bytes()
    for name,data in palettes.items():
        state[new[name]:new[name]+25] = data
    first = new['idempotent']
    state[first:first+16] = (build.OUT/'top.bin').read_bytes()[first-0xff50:first-0xff50+16]
    first = new['rf_blank']
    state[first:first+9] = (build.OUT/'top.bin').read_bytes()[first-0xff50:first-0xff50+9]
    state[new['mapping_chosen']:new['mapping_chosen']+3] = bytes([255])*3
    return state


def call(state, lab, entry, a=0, x=0):
    state = bytearray(state)
    cpu = mos6502.CPU(state)
    cpu.io_read = lambda address: state[address]
    cpu.special = lambda address,value: state.__setitem__(address,value)
    cpu.pc,cpu.s,cpu.a,cpu.x = lab[entry],0xfd,a,x
    state[0x1fe:0x200] = bytes((255,1))
    cpu.hooks[0x200] = 1
    cpu.on_hook = lambda pc: pc==0x200
    cpu.run(100_000)
    assert cpu.pc==0x200, entry
    return state,cpu


def check(out):
    out.mkdir(parents=True,exist_ok=True)
    layout = build.build()
    new = palette_check.labels(layout)
    screens = []
    seed = None
    for path in sorted(BASELINE.rglob('*.bin')):
        snapshot = path.read_bytes()
        old = palette_check.labels(json.loads(path.with_name('report.json').read_text()))
        mode = snapshot[0x389]
        if mode:
            assert policy.convert(snapshot,mode,False)[:2]==palette_check.result(snapshot,old),path
        state = inject(snapshot,old,new)
        state[new['shown_mode']] = 0
        actual,profile = palette_check.execute(state,new)
        wanted = policy.convert(snapshot,mode)[:2] if mode else palette_check.result(snapshot,old)
        assert palette_check.result(actual,new)==wanted,path
        warm,_ = palette_check.execute(actual,new)
        assert palette_check.result(warm,new)==wanted,path
        if mode:
            edge = policy.panel_edge(snapshot,mode)
            assert all(bool(warm[new['codes_panel']+i]&128)==(i%40>=edge) for i in range(120)),path
        screens.append(dict(screen=str(path.relative_to(BASELINE)),mode=mode,after=profile))
        if path.stem=='town': seed=state
    assert seed is not None

    # The compact symmetric representation preserves every old rounded value.
    distances=[]
    for source in range(16):
        for dest in range(16):
            state=bytearray(seed);state[new['base']]=source
            _,cpu=call(state,new,'colour_distance',a=dest,x=source)
            assert cpu.a==policy.distance(source,dest),(source,dest,cpu.a)
            assert cpu.x==source
            distances.append(cpu.a)

    # Presence extraction uses a pre-existing swap map, with an independent
    # direct pair-enumeration oracle. Include every byte and mixed line usage.
    usage=[]
    for byte in range(256):
        state=bytearray(seed);row=6
        source,matrix,_=policy.addresses(1,row)
        state[new['row']]=row
        state[0xf0:0xf2]=bytes((source&255,source>>8))
        state[0xf4:0xf6]=bytes((matrix&255,matrix>>8))
        state[matrix:matrix+40]=bytes([0x5a])*40
        state[source:source+320]=bytes([byte])*320
        state[new['used_matrix']:new['used_matrix']+16]=bytes(16)
        actual,_=call(state,new,'matrix_usage')
        present={byte>>shift&3 for shift in (6,4,2,0)}
        want=bytearray(16)
        if 1 in present: want[5]=40
        if 2 in present: want[10]=40
        assert actual[new['used_matrix']:new['used_matrix']+16]==want,byte
        assert actual[0xf0:0xf2]==state[0xf0:0xf2], 'Usage moved the source pointer'
        usage.append(list(want))

    cases=[]
    state=bytearray(seed);state[0x389]=1;state[0xd816]=14
    row=6;source,matrix,cram=policy.addresses(1,row)
    state[new['row']]=row
    state[0xf0:0xf8]=bytes((source&255,source>>8,0,0,matrix&255,matrix>>8,cram&255,cram>>8))
    state[matrix:matrix+40]=bytes([0x80])*22+bytes([0xb0])*18
    state[cram:cram+40]=bytes([1])*22+bytes([14])*18
    state[source:source+320]=bytes(320)
    state[matrix+5:matrix+7]=bytes([0x5a])*2
    state[source+5*8:source+7*8]=bytes([0x55])*16
    state[source+22*8:source+30*8]=bytes([0x55])*64
    state[new['shown_mode']]=0
    for name,byte in [('green-present',0x55),('bitmap-only-change',0xaa),
                      ('both-pairs',0x66),('white-only',0xff),('black-only',0),('green-return',0x55)]:
        state[source+5*8:source+7*8]=bytes([byte])*16
        # Standalone palette calls use the panel edge supplied by refresh.
        state[new['panel_boundary']]=policy.panel_edge(state,1)
        chosen,panel,pairs,_=policy.select(state,1,row)
        actual,_=call(state,new,'choose_colours')
        assert actual[new['chosen']:new['chosen']+3]==bytes(chosen),name
        assert actual[new['pair']:new['pair']+16]==bytes(pairs),name
        assert bytes(actual[new[n]+row] for n in ('row_pf0','row_pf1','row_pf2','row_pf3'))==bytes(build.ATARI_COLOUR[c] for c in chosen+[panel]),name
        assert actual[new['cache_hit']]==0 and actual[new['row_reuse']+row]==0,name
        if name=='green-present': assert 5 in chosen and 8 not in chosen
        if name=='bitmap-only-change': assert 10 in chosen and 5 not in chosen
        cases.append(dict(case=name,chosen=chosen))
        state=actual;state[new['shown_mode']]=1

    # Layout must switch both directions and ignore colour-RAM high bits.
    for mode,colour,edge in [(1,0xfe,22),(2,0xfe,30),(1,1,30),(1,14,22),(2,14,30)]:
        state=bytearray(seed);state[0x389]=mode;state[0xd816]=colour
        actual,cpu=call(state,new,'update_panel_codes')
        assert actual[new['panel_boundary']]==edge
        assert all(bool(actual[new['codes_panel']+i]&128)==(i%40>=edge) for i in range(120))
        cases.append(dict(case='panel-layout',mode=mode,colour=colour,edge=edge))
    report=dict(screens=screens,distances=len(distances),presence_bytes=len(usage),cases=cases)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'OK: {len(screens)} complete frames, 256 distances, 256 presence bytes, {len(cases)} bitmap/layout cases')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=build.OUT/'colour-check')
    a=p.parse_args();check(a.out)
