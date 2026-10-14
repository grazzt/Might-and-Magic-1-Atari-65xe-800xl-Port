# ZX02 compressor source

Vendored, unchanged, from https://github.com/dmsc/zx02 at revision
`7ffa0e782c9f5718a8d77ba021c6babc78c7fe19` (by way of the Wizardry port's copy).
`port/atari/disks.py` compiles it with the system C compiler into `build/atari`.

- `LICENSE`: the licence of ZX02 (Daniel Serpell, MIT).
- `LICENSE.zx0`: the licence of the ZX0 compressor that ZX02 is derived from
  (Einar Saukas, BSD-style).

The 6502 unpacker in `port/atari/src/kernel.s` is Daniel Serpell's
`zx02-optim` (MIT), adapted to read from a sector buffer and stop at a given length.
