#!/usr/bin/env python3
"""Read 35-track D64 directories/chains without changing source images.

Reference: Wizardry's c64/disk/D64_Format.txt (Peter Schepers, revision 1.11).
Unlisted sectors are retained: this game's directory is not its full disk map.
"""
import argparse
import hashlib
import json
from pathlib import Path

SECTORS = [0] + [21] * 17 + [19] * 7 + [18] * 6 + [17] * 5
DATA_SIZE = 683 * 256


def petscii(raw):
    return ''.join(chr(c) if 32 <= c <= 126 else f"\\x{c:02x}"
                   for c in raw.rstrip(b'\xa0'))


class D64:
    def __init__(self, data):
        if len(data) not in (DATA_SIZE, DATA_SIZE + 683):
            raise ValueError(f"Expected a 35-track D64, got {len(data)} bytes")
        self.data = data
        self.errors = data[DATA_SIZE:] or None

    @staticmethod
    def index(track, sector):
        if not 1 <= track <= 35 or not 0 <= sector < SECTORS[track]:
            raise ValueError(f"Invalid track/sector {track}/{sector}")
        return sum(SECTORS[:track]) + sector

    def sector(self, track, sector):
        index = self.index(track, sector)
        if self.errors and self.errors[index] != 1:
            raise ValueError(f"Disk error {self.errors[index]} at {track}/{sector}")
        start = index * 256
        return self.data[start:start + 256]

    def chain(self, track, sector):
        seen = set()
        result = bytearray()
        locations = []
        while track:
            if (track, sector) in seen:
                raise ValueError(f"Cyclic sector chain at {track}/{sector}")
            seen.add((track, sector))
            locations.append([track, sector])
            block = self.sector(track, sector)
            next_track, next_sector = block[:2]
            if next_track:
                result.extend(block[2:])
            else:
                if next_sector < 1:
                    raise ValueError(f"Invalid final-sector byte count at {track}/{sector}")
                result.extend(block[2:next_sector + 1])
            track, sector = next_track, next_sector
        return bytes(result), locations

    def directory(self):
        bam = self.sector(18, 0)
        track, sector = bam[:2]
        seen = set()
        entries = []
        while track:
            if (track, sector) in seen:
                raise ValueError(f"Cyclic directory at {track}/{sector}")
            seen.add((track, sector))
            block = self.sector(track, sector)
            for offset in range(0, 256, 32):
                entry = block[offset:offset + 32]
                if entry[2] == 0:
                    continue
                kind = entry[2] & 7
                row = {"name": petscii(entry[5:21]), "type":
                       {0: "DEL", 1: "SEQ", 2: "PRG", 3: "USR", 4: "REL"}.get(kind, str(kind)),
                       "closed": bool(entry[2] & 128), "locked": bool(entry[2] & 64),
                       "start": list(entry[3:5]), "directory_blocks": int.from_bytes(entry[30:32], 'little')}
                entries.append(row)
            track, sector = block[:2]
        return entries

    def inspect(self, extract=None):
        bam = self.sector(18, 0)
        entries = self.directory()
        for i, row in enumerate(entries):
            data, locations = self.chain(*row['start'])
            row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), sectors=locations)
            if row['type'] == 'PRG' and len(data) >= 2:
                address = int.from_bytes(data[:2], 'little')
                row['load_address'] = f"${address:04x}"
                row['end_address_exclusive'] = f"${address + len(data) - 2:04x}"
            if extract is not None:
                extract.mkdir(parents=True, exist_ok=True)
                name = f"{i:02d}." + row['type'].lower()
                (extract / name).write_bytes(data)
                row['extracted_file'] = name
        return {"disk_name": petscii(bam[144:160]), "disk_id_hex": bam[162:164].hex(),
                "dos_type": petscii(bam[165:167]), "entries": entries,
                "tracks": [{"track": t, "sectors": SECTORS[t],
                            "bam_free_count": bam[4 + (t - 1) * 4],
                            "nonzero_sectors": [s for s in range(SECTORS[t]) if any(self.sector(t, s))]}
                           for t in range(1, 36)],
                "note": "Directory chains alone do not describe custom/raw game data."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--extract', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = args.image.read_bytes()
    result = D64(data).inspect(args.extract)
    result.update(image=args.image.name, image_sha256=hashlib.sha256(data).hexdigest())
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
