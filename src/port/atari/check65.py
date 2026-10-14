#!/usr/bin/env python3
"""Run 65XE gameplay, display, kernel and disk checks in isolated processes.

Default: all current scenarios on four disks in Atari800, with exactly 64 KB.
Select --altirra, --sio or --single for an additional compatibility pass.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scripts', nargs='*')
    parser.add_argument('--single', action='store_true')
    parser.add_argument('--altirra', action='store_true')
    parser.add_argument('--sio', action='store_true')
    parser.add_argument('--colour', action='store_true')
    parser.add_argument('--title', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT/'build/atari65xe/check')
    args = parser.parse_args()
    scripts = args.scripts or [p.stem for p in sorted((ROOT/'tools/traces').glob('boot-to-*.txt'))]
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for name in scripts:
        script = ROOT/'tools/traces'/f'{name}.txt'
        command = [sys.executable, str(ROOT/'port/atari/lockstep.py'), str(script), '--65xe', '--pictures']
        command += [] if args.single else ['--disks']
        command += ['--altirra'] if args.altirra else []
        command += ['--sio'] if args.sio else []
        command += ['--colour'] if args.colour else []
        command += ['--title'] if args.title else []
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        case = args.out/name
        case.mkdir(exist_ok=True)
        (case/'log.txt').write_text(result.stdout+result.stderr)
        match = re.search(r'OK: memory equal at all (\d+) marks', result.stdout)
        if result.returncode or not match:
            raise RuntimeError(f'{name}: check failed; {case}/log.txt\n'+(result.stdout+result.stderr)[-2000:])
        for mark in re.findall(r'^([^:]+): equal$', result.stdout, re.MULTILINE):
            path = ROOT/'build/atari65xe/lockstep'/f'{mark}.png'
            if path.exists():
                shutil.copyfile(path, case/path.name)
        results.append({'scenario': name, 'marks': int(match.group(1)),
                        'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest()})
        print(f'{name}: {match.group(1)} checkpoints passed', flush=True)
    report = {'emulator': 'AltirraSDL' if args.altirra else 'Atari800', 'ram_kb': 64,
              'disks': 1 if args.single else 4, 'serial_sio': args.sio, 'colour': args.colour, 'title': args.title, 'scenarios': results,
              'checks': ['original event equality', 'game RAM', 'kernel integrity',
                         'OS font reconstruction', 'crossing-row copies', 'display pixels', 'disk/save equality'],
              'marks': sum(r['marks'] for r in results),
              'kernel_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT/'build/atari65xe').glob('*.bin'))
                                if p.name in ('loader.bin','under.bin','top.bin','colour65.bin','play65.bin',
                                              'bank65.bin','wait65.bin','pause65.bin','delay65.bin','waitspy65.bin',
                                              'flip65.bin','copycolour65.bin')}}
    (args.out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'OK: {len(results)} scenarios / {report["marks"]} checkpoints; {args.out}/report.json')


if __name__ == '__main__':
    main()
