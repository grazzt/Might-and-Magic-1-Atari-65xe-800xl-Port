#!/usr/bin/env python3
"""Copy the port's own source to github/src for the public repository.

  python3 tools/export_github_src.py [--out github/src] [--readme tools/github_src_README.md]

The 64 KB / 65XE release folder uses the same export with its own guide:

  python3 tools/export_github_src.py --out 65xe/src --readme tools/github_src_65xe_README.md

What goes: the Atari port (kernel, boot code, title stage, build, harnesses and
checks), the host tools (oracle, 6502 core, disk readers, scripts of keys), the
tests, the notes and the log, and the vendored ZX02 compressor.

What does not, because it is the game and not the port, or is too big or private:
the original disk images and manuals (c64/), anything generated from them
(build/, state/, test-artifacts/ and the four docs/*.json made by tools/mmdisk.py,
tools/area.py and tools/disassemble.py), the 59-byte C64 boot file's source, the
other porting prompts and kit, and credentials.
"""
import argparse
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]

TREES = ['port', 'tools', 'tests', 'docs', 'source']
FILES = ['SPEC.md', 'PLAN.md', 'TODO.md', 'FIX.md', 'PROMPT.md', 'REALHARDWARE.md']
SKIP_PARTS = {'__pycache__', 'porting-kit'}
SKIP = {
    'tools/package_porting.py',
    'port/atari/zx0/zx0.bin',
    'source/c64/boot.s',                # the original game's boot file, as source
    'docs/c64-logical-disk.json',       # generated from the original disks
    'docs/c64-areas.json',
    'docs/c64-code-map.json',
    'docs/c64-disk-layout.json',
}


def copy_tree(source, target, copied):
    for path in sorted((ROOT / source).rglob('*')):
        relative = path.relative_to(ROOT)
        if path.is_dir() or SKIP_PARTS & set(relative.parts) or str(relative) in SKIP or path.suffix == '.pyc':
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        copied.append(relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=ROOT / 'github/src')
    parser.add_argument('--readme', type=Path, default=ROOT / 'tools/github_src_README.md',
                        help="the guide that becomes the folder's README.md")
    args = parser.parse_args()
    shutil.rmtree(args.out, ignore_errors=True)
    args.out.mkdir(parents=True)
    copied = []
    for tree in TREES:
        copy_tree(tree, args.out, copied)
    for name in FILES:
        shutil.copyfile(ROOT / name, args.out / name)
        copied.append(Path(name))
    # the project README, under another name: src/README.md is the guide to this folder
    shutil.copyfile(ROOT / 'README.md', args.out / 'PROJECT-README.md')
    shutil.copyfile(args.readme, args.out / 'README.md')
    # the sentence about a private server and where a token was kept
    notes = args.out / 'REALHARDWARE.md'
    notes.write_text(re.sub(r' Gitea: `http://192[^\n]*did not store it\.', '', notes.read_text()))
    (args.out / '.gitignore').write_text('__pycache__/\n*.pyc\n/build/\n/state/\n/c64/\n/test-artifacts/\n')
    # the author's home folder, in the few notes and scripts that name an absolute path
    home = str(Path.home())
    for path in args.out.rglob('*'):
        if path.is_file() and path.suffix in {'.md', '.json', '.sh', '.py', '.txt', '.s', '.inc', '.cfg'}:
            text = path.read_text()
            if home in text:
                path.write_text(text.replace(home, '~'))
    size = sum((args.out / p).stat().st_size for p in copied)
    print(f'{len(copied)} files, {size / 1e6:.1f} MB, to {args.out}')


if __name__ == '__main__':
    main()
