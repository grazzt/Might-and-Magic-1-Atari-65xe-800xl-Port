#!/usr/bin/env python3
"""Verify downloaded archives, extracted reference files, and ZIP membership."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    count = 0
    for folder in ['c64/images', 'c64/manuals']:
        root = ROOT / folder
        manifest = json.loads((root / 'SOURCES.json').read_text())
        for record in manifest['archives'] + manifest['files']:
            data = (root / record['file']).read_bytes()
            if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise SystemExit(f'Checksum mismatch: {root / record["file"]}')
            if 'archive' in record:
                with zipfile.ZipFile(root / record['archive']) as archive:
                    if archive.read(record['member']) != data:
                        raise SystemExit(f'Archive member mismatch: {record["file"]}')
            count += 1
    print(f'OK: {count} archives/reference files; extracted files match archived members.')


if __name__ == '__main__':
    main()
