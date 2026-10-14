#!/usr/bin/env python3
"""Compare held keys with the original C64 ROM and hold Ctrl+A in combat.

--unit executes the original KERNAL scanner against a physical CIA matrix,
then the unchanged game's reader. --battle drives real POKEY input, with
instruction-preserving RAM observation of accepted keys. Normal disk restored.
"""
import argparse
import ctypes
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools'),str(ROOT/'port/atari')]
import build
from c64 import shared_root
import lockstep
import mos6502


def call(mem, pc, read=None, getin=False):
    cpu=mos6502.CPU(mem)
    cpu.pc,cpu.s=pc,0xfd
    mem[0x1fe:0x200]=bytes([255,1])
    cpu.io_read=read or (lambda a:mem[a])
    cpu.special=lambda a,v:mem.__setitem__(a,v)
    cpu.hooks[0x200]=1
    if getin:
        cpu.hooks[0xffe4]=1
    def hook(address):
        if address==0x200:
            return True
        value=mem[0x277] if mem[0xc6] else 0
        if mem[0xc6]:
            mem[0x277:0x280]=mem[0x278:0x281]
            mem[0xc6]-=1
        cpu.a=cpu.nz=value
        cpu.rts()
        return False
    cpu.on_hook=hook
    cpu.run(30_000)
    assert cpu.pc==0x200
    return cpu.a


def unit(out):
    layout=build.build()
    lab={k:int(v[1:],16) for k,v in layout['labels'].items()}
    rom=(shared_root()/'tools/emulators/local/usr/share/vice/C64/kernal-901227-03.bin').read_bytes()
    game=(ROOT/'test-artifacts/palette/before/fight/fight.bin').read_bytes()
    cases=[]
    # All are letter keys; the default KERNAL's special cursor/space policy is
    # outside the port's all-key repeat path and is not claimed by this check.
    for name,flag,drain,effect in [('ctrl-A',128,True,0),('plain-A',128,True,0),
                                  ('disabled',64,True,0),('default-letter',0,True,0),
                                  ('backpressure',128,False,0),('sound-5',128,True,5),
                                  ('release-repress',128,True,0),('change-key',128,True,0)]:
        ref,actual=bytearray(65536),bytearray(65536)
        ref[0xe000:]=rom
        ref[0x28f:0x291]=bytes([0x48,0xeb]) # normal KERNAL shift-table dispatch
        ref[0xc5]=64
        for file,base in build.SEGMENTS.items():
            actual[base:base+len((build.OUT/file).read_bytes())]=(build.OUT/file).read_bytes()
        for mem in (ref,actual):
            mem[0xc648:0xc69e]=game[0xc648:0xc69e]
            mem[0x289],mem[0x28a],mem[0x28b]=10,flag,6
            if effect:
                mem[0x3a0],mem[0x3a4]=1,effect
        events=[]
        for frame in range(140):
            held=not(name=='release-repress' and 45<=frame<60) and frame<120
            ctrl=name!='plain-A'
            letter='B' if name=='change-key' and frame>=65 else 'A'
            matrix_index=28 if letter=='B' else 10
            keys=({matrix_index,58} if ctrl else {matrix_index}) if held else set()
            def cia(address):
                if address!=0xdc01:
                    return ref[address]
                value=255
                for key in keys:
                    if not(ref[0xdc00] & (1<<(key//8))):
                        value &= ~(1<<(key%8))
                return value
            actual[0xd20f]=0 if held else 4
            actual[0xd209]=(0x15 if letter=='B' else 0x3f)|(0x80 if ctrl else 0)
            call(ref,0xea87,cia)
            call(actual,lab['keyboard'])
            assert bytes(actual[0x277:0x277+actual[0xc6]])==bytes(ref[0x277:0x277+ref[0xc6]]),(name,frame)
            if held:
                assert actual[0x28b:0x28d]==ref[0x28b:0x28d],(name,frame,'counters')
                assert actual[0x28d]&4==ref[0x28d]&4,(name,frame,'CTRL')
            if (drain or frame==100) and actual[0xc6]:
                raw=actual[0x277]
                want=call(ref,0xc648,getin=True)
                got=call(actual,0xc648,getin=True)
                assert got==want and actual[0x28c]==ref[0x28c],(name,frame,'reader')
                events.append(dict(frame=frame,raw=raw,returned=got))
            if not drain:
                assert actual[0xc6]<=1, 'Held repeats accumulated a backlog'
        if flag==128 and drain:
            assert len(events)>1,(name,'no repeats')
        elif flag in (0,64):
            assert len(events)==1,(name,'disabled repeat')
        cases.append(dict(case=name,events=events))
    out.mkdir(parents=True,exist_ok=True)
    (out/'unit.json').write_text(json.dumps(dict(cases=cases),indent=2)+'\n')
    print('OK: eight keyboard scenarios match original C64 scanner/reader, including held CTRL and queue limits')


def battle(out, baseline=False):
    if baseline:
        layout=json.loads((ROOT/'test-artifacts/palette/build.json').read_text())
        shutil.copyfile(ROOT/'build/atari/mm1-palette-fast.atr',build.OUT/'mm1.atr')
    else:
        layout=build.build(test=True)
    game=lockstep.Game(layout)
    lab,mem=game.label,game.memory
    game.frames(300)
    mem[lab['test_mode']]=1
    lines=(ROOT/'tools/traces/boot-to-fight-and-save.txt').read_text().splitlines()
    end=next(i for i,line in enumerate(lines) if line.split('#')[0].split()==['mark','fight'])
    waiting=False
    for words in lockstep.atari_steps(lines[:end+1]):
        op,values=words[0],words[1:]
        if op=='press':
            game.press(int(values[0],16));waiting=False
        elif op=='ready':
            game.ready();waiting=True
        elif op=='wait':
            game.idle();waiting=False
        elif op=='key':
            game.keys([int(v,16) for v in values]);waiting=False
        elif op=='attach':
            mem[lab['side']]='ABCD'.index(values[0])
        elif op=='poke':
            for i,v in enumerate(values[1:]):
                a=int(values[0],16)+i;b=int(v,16)
                if a==lockstep.KEY_WAIT_COUNT and waiting:b=(b+1)&255
                mem[a]=b
        elif op not in ('mark','skip'):
            raise AssertionError(words)
    mem[lab['test_mode']]=0
    mem[lab['script_key']]=0x23 # leave held test hook with an invalid combat command
    game.frames(60)
    out.mkdir(parents=True,exist_ok=True)
    game.atari.screenshot(out/'fight-start.png')
    lib=game.atari._lib
    reg={k:t.in_dll(lib,'CPU_reg'+k) for k,t in [('PC',ctypes.c_uint16),('A',ctypes.c_ubyte),('S',ctypes.c_ubyte)]}
    xpos=ctypes.c_int.in_dll(lib,'ANTIC_xpos')
    CALLBACK=ctypes.CFUNCTYPE(None)
    events=[]
    old=bytes(mem[0xe45:0xe48]);assert old==bytes([0x20,0x71,0x12])
    def accepted():
        s=reg['S'].value
        caller=mem[0x100+((s+2)&255)]|mem[0x100+((s+3)&255)]<<8 # accepted key was pushed first
        events.append(dict(frame=game.atari.frames,key=reg['A'].value,caller=caller,
                           character=mem[0x27],round=mem[0x2012]))
        ret=0xe47
        mem[0x100+s]=ret>>8;s=(s-1)&255
        mem[0x100+s]=ret&255;reg['S'].value=(s-1)&255
        reg['PC'].value=0x1271;xpos.value+=4 # JSR costs six, escape already charged two
    callback=CALLBACK(accepted)
    lib.ESC_Add.argtypes=[ctypes.c_uint16,ctypes.c_ubyte,CALLBACK]
    lib.ESC_Add(0xe45,0x7e,callback)
    try:
        game.atari.input.control,game.atari.input.keychar=1,ord('a')
        game.frames(600)
        held=list(events)
        game.atari.input.control=game.atari.input.keychar=0
        game.frames(30)
        released=len(events)
        game.frames(90)
        assert len(events)==released,'New keys appeared after release'
        game.atari.screenshot(out/'fight-end.png')
        commands=[e for e in held if e['caller']==0x20d6 and e['key']==1]
        characters=sorted({e['character'] for e in commands})
        if baseline:
            assert len(commands)==1,(len(commands),characters)
            game.atari.input.control,game.atari.input.keychar=1,ord('a')
            game.frames(120)
            game.atari.input.control=game.atari.input.keychar=0
            game.frames(30)
            assert sum(e['caller']==0x20d6 and e['key']==1 for e in events)>1,'Manual tap positive failed'
        else:
            assert characters==list(range(6)),characters
        report=dict(baseline=baseline,held_combat_commands=len(commands),characters=characters,
                    events=events,release_stopped=True)
        (out/'battle.json').write_text(json.dumps(report,indent=2)+'\n')
        print('OK: held CTRL-A:',len(commands),'combat commands; characters',characters,'release stops repeats')
    finally:
        lib.ESC_Remove(0x7e)
        mem[0xe45:0xe48]=old


def altirra_battle(out):
    from speed_check import Runner
    layout=build.build(test=True)
    out.mkdir(parents=True,exist_ok=True)
    runner=Runner(layout,'altirra',out)
    lab=runner.label
    try:
        runner.frame()
        runner.until(lambda:b'INSERT DISK B' in runner.read(0x400,1000))
        lines=(ROOT/'tools/traces/boot-to-fight-and-save.txt').read_text().splitlines()
        end=next(i for i,line in enumerate(lines) if line.split('#')[0].split()==['mark','fight'])
        waiting=False
        def ready():
            runner.until(lambda:runner.read(lab['waiting'])[0])
        for words in lockstep.atari_steps(lines[:end+1]):
            op,values=words[0],words[1:]
            if op=='press':
                ready();runner.write(lab['script_key'],int(values[0],16))
                runner.until(lambda:not runner.read(lab['script_key'])[0]);waiting=False
            elif op=='ready':
                ready();waiting=True
            elif op=='wait':
                runner.emulator.frame(2);runner.write(lab['idle'],0)
                runner.until(lambda:runner.read(lab['idle'])[0] or runner.read(lab['waiting'])[0]);waiting=False
            elif op=='key':
                for i,v in enumerate(values):runner.write(0x277+i,int(v,16))
                runner.write(0xc6,len(values));waiting=False
            elif op=='attach':
                runner.write(lab['side'],'ABCD'.index(values[0]))
            elif op=='poke':
                for i,v in enumerate(values[1:]):
                    address=int(values[0],16)+i;byte=int(v,16)
                    if address==lockstep.KEY_WAIT_COUNT and waiting:byte=(byte+1)&255
                    runner.write(address,byte)
            elif op not in ('mark','skip'):
                raise AssertionError(words)
        runner.write(lab['test_mode'],0);runner.write(lab['script_key'],0x23)
        runner.emulator.frame(60)
        runner.emulator.screenshot(out/'fight-start.png')
        signature=runner.read(0x2000,3)
        runner.emulator.command('KEYRAW A down ctrl')
        states=[]
        for frame in range(4,601,4):
            runner.emulator.frame(4)
            if runner.read(0x2000,3)==signature:
                states.append(dict(frame=frame,character=runner.read(0x27)[0],round=runner.read(0x2012)[0]))
        runner.emulator.command('KEYRAW all up')
        runner.emulator.frame(30)
        runner.write(0xc6,0)
        runner.emulator.frame(30)
        assert runner.read(0xc6)[0]==0,'Released key kept filling buffer'
        assert runner.read(lab['last_code'])[0]==255,'Release was not scanned'
        runner.emulator.screenshot(out/'fight-end.png')
        characters=sorted({s['character'] for s in states if s['character']<6})
        rounds=sorted({s['round'] for s in states})
        assert characters==list(range(6)),characters
        assert len(rounds)>=2,rounds
        report=dict(characters=characters,rounds=rounds,release_stopped=True,states=states)
        (out/'battle.json').write_text(json.dumps(report,indent=2)+'\n')
        print('OK: Altirra held CTRL-A visits all six characters in rounds',rounds,'and release stops repeats')
    finally:
        runner.emulator.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unit',action='store_true');p.add_argument('--battle',action='store_true')
    p.add_argument('--baseline',action='store_true');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--altirra',action='store_true')
    a=p.parse_args()
    try:
        if a.unit:unit(a.out)
        elif a.battle:
            if a.altirra:altirra_battle(a.out)
            else:battle(a.out,a.baseline)
        else:p.error('select --unit or --battle')
    finally:
        build.build()
