# Screenshots: Atari beside C64

Made by `python3 port/atari/screenshots.py`. Each pair is the same instant of the same scripted
session: on the left the Atari 130XE build in Atari800, on the right the C64 as the host oracle
draws it, which equals VICE's screenshot. The two machines' memory is equal at each of these
points (`port/atari/lockstep.py`); what differs is how the Atari shows it.

The Atari has three colours per row of text cells, where the C64 has three per cell, and the
kernel picks each row's three from what is on it. See "Colours" in [ATARI-DESIGN.md](ATARI-DESIGN.md).

Encounter colours were corrected on 2026-10-11: unused matrix colours no longer outvote
green artwork, and the full eighteen-column name panel keeps its blue background.
[Cause, validation and timing tradeoff](COLOUR-SELECTION.md).

The title and its eight scenes have a page of their own, made by
`port/atari/title_check.py --gallery`: [TITLE.md](TITLE.md), "The pictures".

| Screen | Atari 130XE | C64 |
| --- | --- | --- |
| Options menu<br>`boot-to-menu`, mark `menu` | ![Atari](screenshots/menu-menu-atari.png) | ![C64](screenshots/menu-menu-c64.png) |
| Creating a character: the rolled statistics<br>`boot-to-new-character`, mark `rolled` | ![Atari](screenshots/new-character-rolled-atari.png) | ![C64](screenshots/new-character-rolled-c64.png) |
| Creating a character: class, race, alignment and sex chosen<br>`boot-to-new-character`, mark `class` | ![Atari](screenshots/new-character-class-atari.png) | ![C64](screenshots/new-character-class-c64.png) |
| The inn of Sorpigal: the roster<br>`boot-to-town-services`, mark `inn` | ![Atari](screenshots/town-services-inn-atari.png) | ![C64](screenshots/town-services-inn-c64.png) |
| Sorpigal, outside the inn<br>`boot-to-town-services`, mark `town` | ![Atari](screenshots/town-services-town-atari.png) | ![C64](screenshots/town-services-town-c64.png) |
| At the blacksmith's door<br>`boot-to-town-services`, mark `blacksmith-door` | ![Atari](screenshots/town-services-blacksmith-door-atari.png) | ![C64](screenshots/town-services-blacksmith-door-c64.png) |
| The blacksmith<br>`boot-to-town-services`, mark `blacksmith` | ![Atari](screenshots/town-services-blacksmith-atari.png) | ![C64](screenshots/town-services-blacksmith-c64.png) |
| The temple<br>`boot-to-town-services`, mark `temple` | ![Atari](screenshots/town-services-temple-atari.png) | ![C64](screenshots/town-services-temple-c64.png) |
| The training hall<br>`boot-to-town-services`, mark `training` | ![Atari](screenshots/town-services-training-atari.png) | ![C64](screenshots/town-services-training-c64.png) |
| The tavern<br>`boot-to-town-services`, mark `tavern` | ![Atari](screenshots/town-services-tavern-atari.png) | ![C64](screenshots/town-services-tavern-c64.png) |
| A character sheet<br>`boot-to-town-services`, mark `character` | ![Atari](screenshots/town-services-character-atari.png) | ![C64](screenshots/town-services-character-c64.png) |
| The Location spell<br>`boot-to-town-services`, mark `location` | ![Atari](screenshots/town-services-location-atari.png) | ![C64](screenshots/town-services-location-c64.png) |
| The dungeon under Sorpigal, unlit<br>`boot-to-fight-and-save`, mark `dungeon` | ![Atari](screenshots/fight-and-save-dungeon-atari.png) | ![C64](screenshots/fight-and-save-dungeon-c64.png) |
| The arena<br>`boot-to-fight-and-save`, mark `arena` | ![Atari](screenshots/fight-and-save-arena-atari.png) | ![C64](screenshots/fight-and-save-arena-c64.png) |
| Combat<br>`boot-to-fight-and-save`, mark `fight` | ![Atari](screenshots/fight-and-save-fight-atari.png) | ![C64](screenshots/fight-and-save-fight-c64.png) |
| After the fight<br>`boot-to-fight-and-save`, mark `won` | ![Atari](screenshots/fight-and-save-won-atari.png) | ![C64](screenshots/fight-and-save-won-c64.png) |
| Outside Sorpigal<br>`boot-to-outdoors`, mark `outdoors` | ![Atari](screenshots/outdoors-outdoors-atari.png) | ![C64](screenshots/outdoors-outdoors-c64.png) |
| One sector south<br>`boot-to-side-d`, mark `sector-ej` | ![Atari](screenshots/side-d-sector-ej-atari.png) | ![C64](screenshots/side-d-sector-ej-c64.png) |
| An encounter in the forest<br>`boot-to-side-d`, mark `portal` | ![Atari](screenshots/side-d-portal-atari.png) | ![C64](screenshots/side-d-portal-c64.png) |
| The same encounter, still: the session never gets past it, so it never reaches the portal or disk D (corrected 2026-10-13)<br>`boot-to-side-d`, mark `side-d` | ![Atari](screenshots/side-d-side-d-atari.png) | ![C64](screenshots/side-d-side-d-c64.png) |
| A wandering group: attack, retreat, bribe or surrender<br>`boot-to-treasure-and-reload`, mark `encounter` | ![Atari](screenshots/treasure-and-reload-encounter-atari.png) | ![C64](screenshots/treasure-and-reload-encounter-c64.png) |
| Treasure found after the fight<br>`boot-to-treasure-and-reload`, mark `chest` | ![Atari](screenshots/treasure-and-reload-chest-atari.png) | ![C64](screenshots/treasure-and-reload-chest-c64.png) |
| After switching off and on: the saved character, halberd and all<br>`boot-to-treasure-and-reload`, mark `sheet-2` | ![Atari](screenshots/treasure-and-reload-sheet-2-atari.png) | ![C64](screenshots/treasure-and-reload-sheet-2-c64.png) |
| The snakes' lair under Sorpigal<br>`boot-to-death`, mark `lair` | ![Atari](screenshots/death-lair-atari.png) | ![C64](screenshots/death-lair-c64.png) |
| The party wiped out<br>`boot-to-death`, mark `dead` | ![Atari](screenshots/death-dead-atari.png) | ![C64](screenshots/death-dead-c64.png) |

More gameplay pictures and VICE references are retained with the [expanded coverage evidence](../test-artifacts/gameplay/README.md). The direct-key, combat, trap, death/raising and wilderness cases use the original key-wait counters for settled C64 pictures.
