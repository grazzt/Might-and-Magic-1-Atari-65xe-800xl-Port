#!/usr/bin/env python3
"""Reassemble the first bootstrap and compare every byte to the G64 extraction."""
import hashlib
import subprocess
from c64 import ROOT, shared_root


def main():
    expected = ROOT / 'build/c64/original-v2-a/files/00.prg'
    if not expected.exists():
        raise SystemExit('Run python3 tools/analyze_c64.py first')
    out = ROOT / 'build/source'
    out.mkdir(parents=True, exist_ok=True)
    toolchain = shared_root() / 'tools/toolchain/local/bin'
    subprocess.run([str(toolchain / 'ca65'), str(ROOT / 'source/c64/boot.s'),
                    '-o', str(out / 'boot.o')], check=True)
    subprocess.run([str(toolchain / 'ld65'), '-C', str(ROOT / 'source/c64/boot.cfg'),
                    '-o', str(out / 'boot.prg'), str(out / 'boot.o')], check=True)
    actual = (out / 'boot.prg').read_bytes()
    if actual != expected.read_bytes():
        raise SystemExit('Bootstrap does not match original G64 extraction')
    print(f'OK: bootstrap matches all {len(actual)} bytes; SHA256 {hashlib.sha256(actual).hexdigest()}')


if __name__ == '__main__':
    main()
