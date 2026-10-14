# Four disks of 130 KB

Written 2026-10-13 on the branch `changed-game-binary`, as the follow-through to [REALHARDWARE.md](../REALHARDWARE.md), which found that the 727 KB image cannot go on real 1050 disks and sketched a layout. **This is implemented and checked in the emulators. It has not been run on a real drive.**

```bash
python3 port/atari/build.py --disks             # build/atari/disks/mm1-disk1.atr ... mm1-disk4.atr, with the C64 title
python3 port/atari/build.py --disks --no-title  # the same starting at the game's first prompt
python3 port/atari/lockstep.py tools/traces/boot-to-fight-and-save.txt --disks [--sio] [--altirra]
python3 port/atari/disks_check.py [--sio]       # the prompts, with the disk changed as a person changes it
python3 -m unittest tests.test_disks            # all of it, about 3½ minutes
```

## What the player does

1. Boot from **disk 1** (the boot disk). The title shows; Escape starts the game; the game loads the rest of what it keeps in memory from disk 1.
2. The game asks, in its own words, **`INSERT DISK B AND PRESS 'RETURN'`**. Take disk 1 out, put disk 2 in, press RETURN. This is the C64 game's own prompt: its disks are A to D, and the Atari's are 1 to 4.
3. Later the game asks for **disk C** (`INSERT DISK C AND PRESS 'RETURN'`, over the play screen) when the party goes out through Sorpigal's gate, and for **disk D** where the world continues there. Each time, swap and press RETURN. The prompt comes back if the wrong disk, or no disk, is in the drive.
4. Characters are saved to **disk B** (the inn's sign-in writes the roster there). Keep disk B, and no other, write-enabled; disk A can be write-protected.

| Disk | Is | Data sectors used (of 1,029) |
| --- | --- | --- |
| 1 | The C64's side A: boot sectors, the title, the resident code, the memory the game starts with | 471 (56 of them boot sectors; 459 without the title) |
| 2 | Side B: Sorpigal, and the roster | 795 |
| 3 | Side C | 749 |
| 4 | Side D | 743 |

Each image is an **enhanced-density disk: 1,040 sectors of 128 bytes** (133,120 bytes, ATR header 16 more), which is what a stock 1050 formats. The last 11 sectors hold the index (below); the rest is free for data, so the fullest disk is 77% full.

## The format

The C64 game reads *items* by block number: a file, a monster picture, the monster records, the file table. **A disk holds the items of one side, each compressed on its own with ZX02**, padded to whole sectors, and **an index at its end**: two bytes for every block number (704 of them, 64 to a sector), naming the item that starts there. Bits 0-10 are its first sector; bit 15 is set for an item **stored as it is**: the roster (the game writes it back), the monster records and the file table (the game reads them a block at a time), and anything incompressible. A stored run has an entry for every one of its blocks.

`port/atari/disks.py` lays the disks out; items come from the game's own tables (`docs/c64-logical-disk.json`: file table, picture index, the fixed reads of side A), not from the recorded sessions. Two items starting at one block (a picture read in full and in part) are one item at the longer length: the unpacker stops at the length asked for.

| Disk | Items | Raw bytes | Sectors | Biggest |
| --- | ---: | ---: | ---: | --- |
| 1 | 27 | 110,570 | 403 | image piece (the memory image's `$3E00-$9CFF`), 63 |
| 2 | 111 | 156,300 | 795 | monster records (stored), 52 |
| 3 | 111 | 150,767 | 749 | monster records, 52 |
| 4 | 112 | 152,953 | 743 | monster records, 52 |

The compressor is the ZX02 one vendored in the Wizardry port (`$SHARED/tools/zx02`, compiled with `cc` into `build/atari`, results cached by content). It is a close relative of the ZX0 that REALHARDWARE.md measured; its decoder is smaller (132 bytes), which mattered more here than the few percent of ratio.

## The kernel

`kernel.s` assembles in two ways. The one-image kernel (`DISKS = 0`) is the one every older check uses and is unchanged. With `DISKS = 1` the disk code is replaced by this, in the same 768 bytes at `$9D00`:

- **A call** (`$9D0D` read, `$9D10` write; block, length, address, as before) reads the **index sector** (`INDEX_SECTOR + block / 64`), takes the entry (`block & 63`), and then either copies the item sector by sector or unpacks it. The offset parameter is not used: each of the 17 stores to `$9D04` in the game, the start-up stub and the title program (found with `tools/disassemble.py`) stores a constant 0.
- **The unpacker** is Daniel Serpell's `zx02-optim` as adapted for the Atari Wizardry port: a streaming, bounded decoder. It pulls bytes one at a time from a 128-byte buffer and refills it with the next sector when it runs out, so **no staging area for a whole compressed item is needed**: the problem REALHARDWARE.md left open. It stops at the length the game asked for, so the prefix reads (a picture asked for in part) are free. It runs with the OS ROM in, as the transfers do, so its zero page is the four bytes `$FC-$FF` that the C64 loader used as scratch anyway.
- **A failure** (no such block on this disk, an SIO error, a stream that ends early, a stack too deep) returns status 8. The game's own file-table check treats that as the wrong disk, and asks again. A wrong game disk (side byte not the wanted one) it already refused.
- **The write** (the roster, 18 sectors from `$6000`) goes to the sectors the index gives for block `$152`, raw. The index is always read first, whichever the call (a write call that read its index with the write command overwrote the index in the first version; the check against the oracle's written disk found it).
- **Which disk is in the drive is not tracked.** The one-image kernel was told by the game's file-table read; this one only reads what is in the drive. The first call after a swap is the game's read of the file table, and the index sector it reads is the new disk's.

### Where it found room

The kernel's segments were full (spare 5 / 1 / 0 / 3) and this needs about 180 bytes more than the code it replaces. What was done:

- **The sector buffer is in the stack page** (`$0100-$017F`, not in the kernel). At each of the game's 107 disk calls in four sessions (fight-and-save, side-d, town-services, outdoors; measured on the oracle) its stack pointer was `$F0` or more, 16 bytes deep at most: the 128 bytes at the bottom of the page are free for the length of a call, with the OS's own use of the stack above them. The kernel refuses a call, with status 8, if the stack pointer is below `$D0`. Not measured: the other 18 recorded sessions.
- **Five variables are in the jump table's padding.** The table has three bytes an entry and four entries are a bare `rts` (start the drive, set and get the disk ID, protected read, reset): two bytes each were free.
- **`enter_game` is not in the kernel.** The boot code copies its last step to `$0180`, where the last load (the memory it ran in) does not reach.
- **The memory above `$C000`.** The OS ROM is in while the kernel unpacks and hides what it writes at `$C000-$FFFF`; the one-image kernel copied such pieces in game mode, a sector at a time, and so does not need to here. Only the boot code loads there (the tail of the `$A000` block and `$CC00-$CFFF`): it reads such a piece to `$4000` and moves it up with the ROM out (`load_staged`, `boot.s`). The title program skips its own loads above `$8000`, as before.
- LOADER has 3 bytes spare, UNDER 2, EXT 7, EXT2 1.

## Checks

- **`lockstep.py --disks`**: the whole of the existing set (21 scripts, 6 to 27 marks each) on four disk images. The harness changes the mounted image at every `attach`, and at a `restart` puts disk 1 back (a power cycle, as a person does it). At the end every item of every disk is read the way the kernel reads it (the disk's own index, then a stored copy or a ZX02 stream, by `disks.read_item`) and compared with the oracle's side, so **the bytes the game never asked for in these sessions are checked too**, and so is what the game wrote: after a save disk B's roster equals the oracle's and nothing else on any disk has changed. **All 21 pass, memory equal at every mark, in Atari800 with the fast disk shortcut. Also passed:** with the shortcut off (`--sio`, the OS ROM's own serial code) for the save and reload, the three sessions that load from **disk D** (`direct-if`, `-eh`, `-dp`: a position fixture puts the party at a castle entrance, the game asks for disk D and loads the area from it; `boot-to-side-d`, whose name suggests it, never gets there: [C64-LOADER.md](C64-LOADER.md)), and the options menu; with the title in front (`--title`); in AltirraSDL, with the shortcut and with the OS doing every transfer (`--altirra --disks [--sio]`), for the fight and save, and (serial transfers) the disk D session `direct-if`; and the save, restart and reload script and the wilderness fight in Altirra with real serial transfers.
- **`disks_check.py`**: the build people play, with nothing told which disk is in: the first prompt asks for disk B; RETURN with disk 1, or with disk C, still in gets the same prompt; disk B gets the options menu; the short game of `play_check.py` goes as before; nothing is written to any disk by then. Pictures of the prompts: `build/atari/disks-check/insert-b.png`, `wrong-disk.png`.
- **`tests/test_disks.py`**: the same, as a unit test, with the format checks on made-up data.

## Time

Measured in Atari800, no title, test build, power-on to the first prompt:

| | Fast disk shortcut | OS doing the serial transfers |
| --- | --- | --- |
| One big image | 77 frames (1.3 s) | 2,391 frames (39.9 s) |
| Four disks | 450 frames (7.5 s) | 1,628 frames (27.1 s) |

With real transfers the four disks are faster to the prompt: the memory image is 13 KB packed where it was 37 KB, fewer sectors to read. With the shortcut they are slower: the unpacker is the whole cost, about 180 cycles an output byte (it works through a byte-at-a-time stream and a 16-bit bound), and the boot unpacks about 60 KB. In the game every load pays that too: a 5 KB overlay about 0.5 s on top of its sectors, which on a real drive (about 25 sectors packed, plus the index sector) will mostly be rotation and serial time. **Not measured on a 1050, whose own timing neither emulator has.** A faster unpacker (a decrementing bound and an inlined `lz_next` would be the first steps) is not done: there are 3 bytes of room.

## What is not known

- **Real hardware.** Nothing here has run on a drive. In particular: how a stock 1050 answers the first command after a disk change (the kernel treats any failure as "ask again", so the worst case is a second RETURN); the sector order on a disk written by a tool that formats with interleave; write-protect (the roster write fails and the status goes back to the game as 8; what the game does then was not examined); and the time of a read. Altirra and Atari800 are both fast and have no rotation.
- **A drive that is not enhanced density.** The index is at sectors 1030-1040: a 90 KB (single density) disk cannot hold this. A 180 KB drive reads it as it is.
- **Reads the sessions did not make.** The item set is the game's own tables, not the trace, and the check compares every item; but a read at a block that is no item's start (none was seen) gets status 8.
- **A 64 KB build** can retain this kernel's streaming unpacker and 128-byte stack-page buffer, which already live in main memory. The unresolved allocation is the Atari display and its support data/code: see [64K-FEASIBILITY.md](64K-FEASIBILITY.md) and the historical [64K-NOTES.md](64K-NOTES.md).
