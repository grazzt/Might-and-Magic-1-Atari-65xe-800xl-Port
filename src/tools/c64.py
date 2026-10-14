#!/usr/bin/env python3
"""Launch the reference C64 from a writable copy; reuse Wizardry's VICE."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def shared_root():
    return Path(os.environ.get("WIZARDRY_ROOT", ROOT.parent / "wizardry_1")).resolve()


def command(headless=False, variant="Original_v2", side="A", state=None):
    install = shared_root() / "tools/emulators/local/usr"
    exe = install / "bin/x64sc"
    if not exe.is_file():
        raise SystemExit(f"Missing {exe}; see docs/REFERENCES.md")
    state = Path(state or ROOT / "state/c64").resolve()
    env = os.environ.copy()
    for key, folder in [("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config"),
                        ("XDG_DATA_HOME", "data")]:
        path = state / folder
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    disks = state / "disks"
    disks.mkdir(parents=True, exist_ok=True)
    originals = sorted((ROOT / "c64/images").glob(f"*({variant})*"))
    originals = [p for p in originals if p.suffix in (".g64", ".d64")]
    if len(originals) != 4:
        raise SystemExit(f"Expected four disks for {variant}, found {len(originals)}")
    for original in originals:
        target = disks / original.name
        if not target.exists():
            shutil.copyfile(original, target)
    suffix = side if variant.startswith("Original") else str("ABCD".index(side) + 1)
    image = next(p for p in originals if p.stem.endswith("Side_" + suffix))
    roms = install / "share/vice"
    args = [str(exe)] + (["-console"] if headless else [])
    args += ["-default", "+sound", "+binarymonitor", "+remotemonitor",
             "-directory", str(roms),
             "-kernal", str(roms / "C64/kernal-901227-03.bin"),
             "-basic", str(roms / "C64/basic-901226-01.bin"),
             "-chargen", str(roms / "C64/chargen-901225-01.bin"),
             "-dos1541", str(roms / "DRIVES/dos1541-325302-01+901229-05.bin"),
             "-drive8type", "1541", "-drive8truedrive", "+virtualdev8",
             "+autostart-handle-tde", "+autostart-delay-random", "-seed", "1",
             "-pal", "-autostart", str(disks / image.name)]
    return args, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--variant", choices=["Original_v1", "Original_v2", "FAC", "None"], default="Original_v2")
    parser.add_argument("--side", choices=list("ABCD"), default="A")
    parser.add_argument("--state", type=Path)
    args, extra = parser.parse_known_args()
    cmd, env = command(args.headless, args.variant, args.side, args.state)
    raise SystemExit(subprocess.call(cmd + extra, env=env))


if __name__ == "__main__":
    main()
