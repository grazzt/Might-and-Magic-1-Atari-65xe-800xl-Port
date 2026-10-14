#!/usr/bin/env python3
"""Make the screenshot gallery: the Atari build beside the C64, screen by screen.

  python3 port/atari/screenshots.py

Each screen is taken at a mark of one of the key scripts in tools/traces. The
Atari picture is Atari800's display while port/atari/lockstep.py plays the
script; the C64 picture is the host oracle's drawing of the same instant,
which equals VICE's screenshot (docs/ORACLE.md). Writes docs/screenshots/ and
docs/SCREENSHOTS.md.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import c64_screen                       # noqa: E402
import oracle                           # noqa: E402

OUT = ROOT / 'docs/screenshots'
SCREENS = [  # script, mark, what it shows
    ('boot-to-menu', 'menu', 'Options menu'),
    ('boot-to-new-character', 'rolled', 'Creating a character: the rolled statistics'),
    ('boot-to-new-character', 'class', 'Creating a character: class, race, alignment and sex chosen'),
    ('boot-to-town-services', 'inn', 'The inn of Sorpigal: the roster'),
    ('boot-to-town-services', 'town', 'Sorpigal, outside the inn'),
    ('boot-to-town-services', 'blacksmith-door', 'At the blacksmith\'s door'),
    ('boot-to-town-services', 'blacksmith', 'The blacksmith'),
    ('boot-to-town-services', 'temple', 'The temple'),
    ('boot-to-town-services', 'training', 'The training hall'),
    ('boot-to-town-services', 'tavern', 'The tavern'),
    ('boot-to-town-services', 'character', 'A character sheet'),
    ('boot-to-town-services', 'location', 'The Location spell'),
    ('boot-to-fight-and-save', 'dungeon', 'The dungeon under Sorpigal, unlit'),
    ('boot-to-fight-and-save', 'arena', 'The arena'),
    ('boot-to-fight-and-save', 'fight', 'Combat'),
    ('boot-to-fight-and-save', 'won', 'After the fight'),
    ('boot-to-outdoors', 'outdoors', 'Outside Sorpigal'),
    ('boot-to-side-d', 'sector-ej', 'One sector south'),
    ('boot-to-side-d', 'portal', 'An encounter in the forest'),
    ('boot-to-side-d', 'side-d', 'Beyond the portal, on side D'),
    ('boot-to-treasure-and-reload', 'encounter', 'A wandering group: attack, retreat, bribe or surrender'),
    ('boot-to-treasure-and-reload', 'chest', 'Treasure found after the fight'),
    ('boot-to-treasure-and-reload', 'sheet-2', 'After switching off and on: the saved character, halberd and all'),
    ('boot-to-death', 'lair', 'The snakes\' lair under Sorpigal'),
    ('boot-to-death', 'dead', 'The party wiped out'),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.png'):
        old.unlink()
    rows = []
    for script in dict.fromkeys(s for s, _, _ in SCREENS):
        wanted = [(mark, what) for s, mark, what in SCREENS if s == script]
        lines = (ROOT / f'tools/traces/{script}.txt').read_text().splitlines()
        run = subprocess.run([sys.executable, ROOT / 'port/atari/lockstep.py',
                              ROOT / f'tools/traces/{script}.txt', '--pictures'], capture_output=True, text=True)
        if run.returncode:
            raise SystemExit(run.stdout[-500:] + run.stderr[-500:])
        player = oracle.Oracle()
        pictures = {}
        player.play(lines, on_mark=lambda name: pictures.__setitem__(name, player.picture()))
        for mark, what in wanted:
            name = f"{script.replace('boot-to-', '')}-{mark}"
            shutil.copyfile(ROOT / f'build/atari/lockstep/{mark}.png', OUT / f'{name}-atari.png')
            c64_screen.write_png(OUT / f'{name}-c64.png', pictures[mark])
            rows.append((what, name, script, mark))
    page = ['# Screenshots: Atari beside C64', '',
            'Made by `python3 port/atari/screenshots.py`. Each pair is the same instant of the same scripted',
            'session: on the left the Atari 130XE build in Atari800, on the right the C64 as the host oracle',
            'draws it, which equals VICE\'s screenshot. The two machines\' memory is equal at each of these',
            'points (`port/atari/lockstep.py`); what differs is how the Atari shows it.', '',
            'The Atari has three colours per row of text cells, where the C64 has three per cell, and the',
            'kernel picks each row\'s three from what is on it. See "Colours" in [ATARI-DESIGN.md](ATARI-DESIGN.md).', '',
            'Encounter colours were corrected on 2026-10-11: unused matrix colours no longer outvote',
            'green artwork, and the full eighteen-column name panel keeps its blue background.',
            '[Cause, validation and timing tradeoff](COLOUR-SELECTION.md).', '',
            'The title and its eight scenes have a page of their own, made by',
            '`port/atari/title_check.py --gallery`: [TITLE.md](TITLE.md), "The pictures".', '',
            '| Screen | Atari 130XE | C64 |', '| --- | --- | --- |']
    for what, name, script, mark in rows:
        page.append(f'| {what}<br>`{script}`, mark `{mark}` | ![Atari](screenshots/{name}-atari.png) '
                    f'| ![C64](screenshots/{name}-c64.png) |')
    (ROOT / 'docs/SCREENSHOTS.md').write_text('\n'.join(page) + '\n')
    print(f'{len(rows)} pairs in {OUT}; page docs/SCREENSHOTS.md')


if __name__ == '__main__':
    main()
