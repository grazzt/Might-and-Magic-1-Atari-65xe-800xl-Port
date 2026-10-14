#!/usr/bin/env python3
"""Extract standard sectors with VICE c1541; retain G64s as the boot reference.

The generated D64s are analysis views, NOT substitutes for protected originals.
Nonstandard tracks, weak bits and duplicate sectors are not represented by D64.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from c64 import ROOT, command, shared_root
from d64 import D64, SECTORS


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/c64')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    _, env = command(headless=True)
    c1541 = shared_root() / 'tools/emulators/local/usr/bin/c1541'
    summary = []
    for side in 'ABCD':
        image = ROOT / f'c64/images/Might_and_Magic_1_(Original_v2)_Side_{side}.g64'
        dest = out / f'original-v2-{side.lower()}'
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='mm-sectors-') as tmp:
            files = [(t, s, Path(tmp) / f'{t:02d}-{s:02d}.bin')
                     for t in range(1, 36) for s in range(SECTORS[t])]
            commands = ''.join(f'bread "{p}" {t} {s}\n' for t, s, p in files) + 'quit\n'
            result = subprocess.run([str(c1541), str(image)], input=commands,
                                    capture_output=True, text=True, env=env, timeout=60)
            (dest / 'c1541.log').write_text(result.stdout + result.stderr)
            if result.returncode or 'ERR' in result.stderr.upper():
                raise SystemExit(f'c1541 failed for {image}; see {dest}/c1541.log')
            missing = [(t, s) for t, s, p in files if not p.exists() or p.stat().st_size != 256]
            if missing:
                raise SystemExit(f'Cannot decode standard sectors in {image}: {missing}')
            data = b''.join(p.read_bytes() for _, _, p in files)
        (dest / 'sectors.d64').write_bytes(data)
        disk = D64(data)
        report = disk.inspect(dest / 'files')
        report.update(image=image.name, image_sha256=sha(image.read_bytes()),
                      decoded_sha256=sha(data), decoded_bytes=len(data))
        # Independent directory-chain validation against VICE's file reader.
        for i, row in enumerate(report['entries']):
            if row['type'] != 'PRG':
                continue
            vice_file = dest / f'vice-{i:02d}.prg'
            result = subprocess.run([str(c1541), '-attach', str(image), '-read',
                                     row['name'].lower(), str(vice_file)],
                                    env=env, capture_output=True, text=True, timeout=30)
            expected = (dest / 'files' / row['extracted_file']).read_bytes()
            if result.returncode or not vice_file.exists() or vice_file.read_bytes() != expected:
                raise SystemExit(f'Directory extraction disagrees with c1541: {side}/{row["name"]}')
            row['c1541_file_matches'] = True
        comparisons = {}
        for variant in ['None', 'FAC']:
            other = ROOT / f'c64/images/Might_and_Magic_1_({variant})_Side_{"ABCD".index(side) + 1}.d64'
            other_data = other.read_bytes()
            comparisons[variant] = [[t, s] for t in range(1, 36) for s in range(SECTORS[t])
                                    if disk.sector(t, s) != D64(other_data).sector(t, s)]
        report['differing_sectors_vs_d64'] = comparisons
        (dest / 'directory.json').write_text(json.dumps(report, indent=2) + '\n')
        summary.append(report)
        print(f'{side}: 683 sectors decoded; {len(report["entries"])} directory entries; '
              f'None/FAC differences: {len(comparisons["None"])}/{len(comparisons["FAC"])} sectors')
    (out / 'disk-layout.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
