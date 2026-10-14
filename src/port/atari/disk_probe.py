#!/usr/bin/env python3
"""Native sector-loop checks: exact bytes, OS/ZP restoration and swap counts.

python3 port/atari/disk_probe.py --out test-artifacts/disk-loading/sector-probe
The temporary call trampoline is in unused TOP padding, away from the SIO
buffer. It is restored after each call; no instrumentation enters the ATR.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'port/atari')]
import build
import lockstep


def check(out, existing=False, batched=True):
    out.mkdir(parents=True,exist_ok=True)
    layout=json.loads((build.OUT/'layout.json').read_text()) if existing else build.build(test=True)
    assert layout['test_mode']
    game=lockstep.Game(layout)
    game.frames(300)
    m,lab,emu=game.memory,game.label,game.atari
    m[lab['side']]=1
    game.keys([13]);game.ready()
    lib=emu._lib
    regs={k:t.in_dll(lib,'CPU_reg'+k) for k,t in
          [('PC',ctypes.c_uint16)]+[(k,ctypes.c_ubyte) for k in 'AXYSP']}
    callback_type=ctypes.CFUNCTYPE(None)
    lib.ESC_Add.argtypes=[ctypes.c_uint16,ctypes.c_ubyte,callback_type]
    address=lab['swap_zero_page']
    original=bytes(m[address:address+2])
    assert original==bytes((0xa2,0x7f))
    swaps=[0]
    def swapped():
        swaps[0]+=1
        regs['X'].value=0x7f
        regs['P'].value &= ~0x82
        regs['PC'].value=address+2
    callback=callback_type(swapped)
    lib.ESC_Add(address,0x7d,callback)
    images={k:(build.OUT/k).read_bytes() for k in build.SEGMENTS}
    records=[]
    def call(entry, side, block, offset, dest, length):
        params=bytes((dest&255,dest>>8,length&255,length>>8,offset,block&255,block>>8))
        m[lab['param_address']:lab['param_address']+7]=params
        m[lab['side']]=side
        state=emu.cpu()
        # Six bytes in free TOP padding. Disk reads can overwrite the shared
        # probe_scratch/sector buffer, so it cannot hold this call trampoline.
        start=0xffe7; stop=start+3
        old=bytes(m[start:start+6])
        m[start:start+6]=bytes((0x20,entry&255,entry>>8,0x4c,stop&255,stop>>8))
        zp=bytes(m[2:128]);irq=bytes(m[0x314:0x316]);swaps[0]=0
        regs['PC'].value=start
        try:
            game.until(lambda: emu.cpu()['PC']==stop,'disk call completion')
            result=emu.cpu()
            assert result['A']==0 and result['X']==m[lab['x_after']] and result['Y']==length&255
            assert result['P']&3==3, result
            assert bytes(m[2:128])==zp, 'Game zero page changed'
            assert bytes(m[0x314:0x316])==irq, 'Game IRQ vector changed'
            assert ctypes.c_ubyte.in_dll(lib,'PIA_PORTB').value==0xd2
            assert bytes(m[0xfc:0x100])==bytes((dest&255,((dest>>8)+(length>>8))&255,0,0))
            return swaps[0]
        finally:
            m[start:start+6]=old
            for name,value in state.items():
                if name in regs:
                    regs[name].value=value
    try:
        # Direct, partial first/last sectors, page/sector boundaries, all
        # sides, upper RAM, and direct-to-bounce boundary crossing.
        cases=[(0,0,0,0x5000,1024),(1,3,0,0x5001,0)]
        cases += [(i%4,10+i,offset,0x5001,length) for i,(offset,length) in enumerate(
                  [(0,1),(0,127),(0,128),(0,129),(1,255),(127,1024),(128,512),(255,333)])]
        cases += [(2,20,offset,dest,length) for offset,dest,length in
                  [(0,0xbe80,512),(0,0xbf40,512),(3,0xc900,333),(255,0xe080,513),(0,0xfe80,128)]]
        for side,block,offset,dest,length in cases:
            before=bytes(m[dest-1:dest+length+1])
            disk=game.disk.read_bytes()
            first=16+(layout['boot_sectors']+side*layout['sectors_per_side'])*128+block*256+offset
            want=disk[first:first+length]
            count=call(lab['disk_read'],side,block,offset,dest,length)
            assert bytes(m[dest:dest+length])==want,(side,offset,dest,length)
            assert m[dest-1]==before[0] and m[dest+length]==before[-1], 'Read crossed its bounds'
            if length==0: assert count==0
            if offset==0 and dest==0x5000:
                assert count==(2 if batched else 16), 'Unexpected direct-sector swap count'
            records.append(dict(side=side,block=block,offset=offset,address=dest,length=length,swaps=count))
            m[dest-1:dest+length+1]=before
        # Full roster-sized write then an unaligned read back from that disk.
        dest,length,block=0x6000,2304,25
        old=bytes(m[dest:dest+length])
        data=bytes((i*37+i//127)&255 for i in range(length))
        m[dest:dest+length]=data
        before=game.disk.read_bytes()
        count=call(lab['disk_write'],1,block,0,dest,length)
        assert count==(2 if batched else 36), 'Unexpected write-sector swap count'
        first=16+(layout['boot_sectors']+layout['sectors_per_side'])*128+block*256
        expected=before[:first]+data+before[first+length:]
        call(lab['disk_read'],1,block,127,0x5000,513)
        assert bytes(m[0x5000:0x5201])==data[127:640]
        m[dest:dest+length]=old
        records.append(dict(write_bytes=length,swaps=count,readback_bytes=513))
        m[address:address+2]=original
        assert not lockstep.kernel_changes(m,layout['fixed'],images)
        lib.libatari800_exit()   # flush buffered writes before checking the whole disk
        assert game.disk.read_bytes()==expected,'Write changed other disk bytes'
        report=dict(cases=records,exact=True,write_sha256=hashlib.sha256(expected).hexdigest())
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(f'OK: {len(cases)} exact reads, roster-sized write/readback, zero page, IRQ and OS restoration')
        return report
    finally:
        m[address:address+2]=original
        lib.ESC_Remove(0x7d)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=build.OUT/'disk-probe')
    a=p.parse_args()
    try:
        check(a.out)
    finally:
        build.build(test=False)

if __name__=='__main__': main()
