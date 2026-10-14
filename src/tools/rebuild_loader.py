#!/usr/bin/env python3
"""Disassemble the loader pieces from their da65 info files, reassemble them
with ca65/ld65 and compare every byte with the original-v2 disk.

  loader-stage2.info  $2000-$22FF of ACTIVISION INC. (side A)
  fastload-c64.info   its last three pages, which run at $9D00-$9FFF
  drive-check.info    the 96 bytes it uploads to the 1541 at $0300
  drive.info          track 18 sectors 7-11, unscrambled, at $0300-$07FF

The info files are the source: they hold the code/data split, labels and
comments. Generated listings go to build/source/*.s.
"""
import hashlib
import subprocess

from c64 import ROOT, shared_root
from d64 import D64


def scramble(image):
    """Inverse of the drive's own unscrambling: $0300-$07FF -> five sectors."""
    data = bytearray(image)
    for y in range(1, 0xed):
        for low, high, key in ((0x100, 0x200, 0x55), (0x300, 0x400, 0xaa)):
            data[low + y], data[high + y] = data[high + y] ^ key, data[low + y] ^ key
    return bytes(data)


def rebuild(name, start, original, out, toolchain):
    info = ROOT / f'source/c64/{name}.info'
    (out / f'{name}.orig').write_bytes(original)
    run = lambda *args: subprocess.run([str(a) for a in args], check=True)
    run(toolchain / 'da65', '-i', info, '-o', out / f'{name}.s', out / f'{name}.orig')
    (out / f'{name}.cfg').write_text(
        f'MEMORY {{ MAIN: start = ${start:04X}, size = ${len(original):04X}, file = %O; }}\n'
        'SEGMENTS { CODE: load = MAIN, type = ro; }\n')
    run(toolchain / 'ca65', out / f'{name}.s', '-o', out / f'{name}.o')
    run(toolchain / 'ld65', '-C', out / f'{name}.cfg', '-o', out / f'{name}.bin', out / f'{name}.o')
    built = (out / f'{name}.bin').read_bytes()
    if built != original:
        raise SystemExit(f'{name}: rebuild differs from the original')
    print(f'OK: {name} matches all {len(built)} bytes at ${start:04X}; '
          f'SHA256 {hashlib.sha256(built).hexdigest()}')
    return built


def main():
    side = ROOT / 'build/c64/original-v2-a'
    if not (side / 'sectors.d64').exists():
        raise SystemExit('Run python3 tools/analyze_c64.py first')
    out = ROOT / 'build/source'
    out.mkdir(parents=True, exist_ok=True)
    toolchain = shared_root() / 'tools/toolchain/local/bin'
    prg = (side / 'files/01.prg').read_bytes()
    if prg[:2] != b'\x00\x20' or len(prg) != 0x602:
        raise SystemExit('Unexpected ACTIVISION INC. file')
    stage2 = rebuild('loader-stage2', 0x2000, prg[2:0x302], out, toolchain)
    fastload = rebuild('fastload-c64', 0x9d00, prg[0x302:], out, toolchain)
    if prg[:2] + stage2 + fastload != prg:
        raise SystemExit('Reassembled PRG differs')
    # Each M-W command is "M-W", address, count, then 32 bytes of drive code.
    uploads = b''.join(stage2[o + 6:o + 38] for o in (0x7b, 0xb7, 0xf3))
    rebuild('drive-check', 0x0300, uploads, out, toolchain)

    disk = D64((side / 'sectors.d64').read_bytes())
    sectors = b''.join(disk.sector(18, s) for s in range(7, 12))
    plain = scramble(sectors)  # the transform is its own inverse
    drive = rebuild('drive', 0x0300, plain, out, toolchain)
    if scramble(drive) != sectors:
        raise SystemExit('Scrambled drive code differs from track 18 sectors 7-11')
    for other in 'bcd':
        other_disk = D64((ROOT / f'build/c64/original-v2-{other}/sectors.d64').read_bytes())
        if b''.join(other_disk.sector(18, s) for s in range(7, 12)) != sectors:
            raise SystemExit(f'Side {other.upper()} carries different drive code')
    print('OK: scrambled drive code matches track 18 sectors 7-11 on all four sides')


if __name__ == '__main__':
    main()
