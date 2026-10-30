# Magnet World

A 3D magnetic-tile building game (think Magna-Tiles meets Lego Worlds), made by Geoff & Levi in Godot 4.
You build with magnetic tiles anywhere in a ruined Marvel city, play as any of 17 Avengers, hunt down the six
Infinity Stones (guarded by Thanos and the Black Order) and use their powers in the Infinity Gauntlet. Drive or fly
12 vehicles, explore inside buildings, fight Thanos's army and take on random missions.

## Run it

    /Applications/Godot.app/Contents/MacOS/Godot --path ~/Desktop/Work/Personal/magnet-world

Or open the folder in the Godot editor (Import → pick `project.godot`) and press ▶.

## How it plays

Mouse + keyboard on the Mac, touch on the iPad (an on-screen controls card shows the keys; H hides it):

| Build mode | | Explore mode (Tab) | | Driving (Enter by the buggy) | |
|---|---|---|---|---|---|
| W A S D | move the camera around | W A S D | walk | W / S | gas / brake + reverse |
| Q / E (or Left / Right) | spin camera | Space | jump | A / D | steer |
| Up / Down | tilt camera | Up / Down | look up / down | Space | handbrake |
| Mouse wheel (or - / =) | zoom | Q / E | spin camera | R | flip back over |
| Click (or Space) | place tile at the mouse | P | pick explorer | Q / E | look around |
| R | flip / turn the tile | Enter | hop in a vehicle | Enter | hop out |
| F / G | tilt the tile to any angle (stand ground tiles up) | 1–8 | pick a weapon | F | special move |
| Right-click (or Backspace) | remove tile | F | fight! | G | honk |
| | | I | summon a vehicle | Flying: Space / Shift | up / down |
| | | Tab | back to building | | |
| 1–5, C, Z, X | shape, colour, undo, eraser | | |
| I | Items menu (add our couch!) | | |
| K | Smash! menu (Giant Levi or the wrecking ball) | | |

Mouse: click places at the pointer, right-click removes, right-drag orbits, middle-drag slides the camera, scroll zooms.
iPad: tap places, one finger drags the lot around, two fingers turn the camera, pinch zooms; the thumb stick walks, drives or slides the camera.

- Shapes: square, triangle, right triangle (half a square, Picasso Tiles style), tall triangle, big square.
- Point at a tile edge and the new tile hinges off it like a magnet; if its corners would meet existing
  corners it snaps to that angle. R flips through the other ways it fits (mirror image first).
- Items (I): add things to the world, like **Our Living Room Couch**. Move the see-through preview, R turns it
  (45° steps), Space puts it down, Esc cancels. Backspace / eraser removes it; Z undoes. You can climb on it.
- Smash! (K): **Giant Levi** drops in and smashes your build a random way (stomp, kick, swipe or
  double-fist smash), or a **crane** drops in and swings a wrecking ball through it. Every tile becomes a
  physics piece and goes flying; Z (undo) rebuilds the whole thing. Code: `destroy.gd`.
- Pick your hero (P): Spider-Man (default), Iron Man, Captain America, Thor, Hulk, Black Widow, Hawkeye, Black Panther,
  Doctor Strange, Captain Marvel, Scarlet Witch, Vision, Ant-Man, Wasp, Falcon, War Machine, Winter Soldier
  (`art/src/heroes_a.py`, `heroes_b.py` → `assets/characters/hero_<name>.glb`). Slot 1 is each hero's own move
  (webs, repulsors, shield throw, Mjolnir throw, Hulk smash...). The choice is remembered.
- **Build anywhere**: Tab while exploring builds right where you're standing (anywhere within 24 m, on the ground,
  rooftops, ledges); Tab again puts you back where you were.
- **Infinity Stones** (`stones.gd`): six sites out in the city, each under a force field that keeps vehicles out, each
  guarded and each a tile-building puzzle: Mind (roof of Ultron's tower, 6 m up), Space (floating Chitauri platform,
  5 m up), Reality (island in a goo pool: build a bridge), Power (temple with laser turrets: build cover; Thanos),
  Time (balcony inside Doctor Strange's Sanctum: bridge the gap), Soul (top of the Vormir spire, 7 m; Thanos).
  A coloured beam marks each one; Nick Fury points the way.
- **Infinity Gauntlet** (9, `powers.gd`): T picks a stone, F uses it. Space teleports, Mind turns baddies to your side,
  Reality pops them into bubbles, Power is a shockwave, Time freezes them, Soul heals and shields. All six: the Snap.
- The city (`city.gd`) is generated from a seed out of a Blender kit of building storeys, roofs, ruined tops and
  street junk: a grid of blocks around the lot, taller towards the edge, then open wasteland and a far-off skyline.
  Every copy of a kit piece is one MultiMesh, so it stays cheap on an iPad.
- The buggy (`vehicle.gd`) is a VehicleBody3D: your explorer sits in it. Barrels and tyres get knocked flying, and
  crashing into your build fast enough smashes it (Z rebuilds).
- **Vehicles** (Items menu, I): buggy, fire truck (F sprays water, puts out fires), police car (siren scares baddies),
  garbage truck (scoops up junk), race car (turbo), monster truck (big jump), ice cream truck (people come running),
  Santa's sleigh (drops presents), plane (loops), helicopter (spotlight), rocket ship, hoverboard. `rides.gd` lists them;
  `vehicle.gd` drives the wheeled ones, `flyer.gd` the flying ones, `ride_fx.gd` does the special moves.
- **People and creatures** (`npc.gd`): New Yorkers, S.H.I.E.L.D. agents, Nick Fury (hints) and Lucky the Pizza Dog
  (follows you); Chitauri, Outriders, symbiotes, Ultron sentries, spider drones and Hydra agents (some shoot slow blasts that
  tiles block); bosses Thanos, Ebony Maw, Proxima Midnight, Corvus Glaive and Cull Obsidian (health bars; they teleport
  away when beaten). Vehicles knock everyone flying; baddies poof into sparkles (no gore).
- **Weapons** (`combat.gd`): hero move, sword, knife, bat, hammer, blaster, bow, rocket launcher, Infinity Gauntlet. Attacks auto-aim at the
  nearest baddie. 6 hearts that heal over time; run out and you're back at base.
- **Missions** (`encounters.gd`): Chitauri ambush, rescue, Outrider pack, Ultron patrol, symbiotes, Hydra agents,
  S.H.I.E.L.D. supply drop, car on fire. They pay stars.
- **iPad**: touch controls (`touch.gd`) appear on touch screens: thumb stick, context buttons, two-finger camera.
- The world autosaves.

Dev flags (after `--`): `--demo` builds a sample scene (doesn't touch the save), `--shot=path.png` saves a screenshot and quits,
`--cam=yaw,pitch,dist,x,y,z`, `--play`, `--char=fox`, `--walk`, `--picker`,
`--keys=d:20,space:1` (replay key presses: name:frames held; the first press can get lost, so lead with `shift:20`),
`--shotframe=N`, `--smash=ball|giant|giant:kick`, `--drive` (start in the buggy), `--buggy=x,z,heading`,
`--ride=fire_truck` (summon and drive), `--scenario=rescue`, `--lineup` (all NPCs in a row), `--touch`, `--seed=N`,
`--goto=mind` (stand outside a stone site), `--grab=mind,time` (collect stones), `--mouse=x,y` (put the pointer there).

## Art pipeline (Blender 5.2)

- `art/src/tiles.py`: regenerates the tile models into `assets/tiles/`.
- `art/src/city_kit.py`: the ruined-city kit → `assets/city/kit.glb` (4x4 storeys, roofs, ruins, wrecks, rubble, props).
  Godot swaps its materials (by name) for the Poly Haven textures in `assets/textures/`.
- `art/src/buggy.py`, `ground_vehicles.py`, `air_vehicles.py`: the vehicles → `assets/vehicles/<name>.glb` + thumbnail.
- `art/src/npcs.py` (+ `npc_kit.py`): people and creatures → `assets/characters/npc_<name>.glb` + portraits.
- `art/src/weapons.py`: all weapons in `assets/weapons/weapons.glb` + icons.
- `art/src/marvel_gear.py`: Infinity Gauntlet (stones as child nodes), loose stones, Mjolnir, Cap's shield, pedestal →
  `assets/weapons/gear.glb` + icons. `art/src/villains.py`, `marvel_folk.py`: Thanos, the Black Order and the city's people.
- `art/src/sites_kit.py`: the stone sites' set pieces (tower, platform, goo pool, temple, Sanctum, Vormir) → `assets/sites/`.
- `art/src/couch.py`: our living-room sectional, modelled from photos (real metres), exported to
  `assets/items/couch.glb` with a thumbnail `couch.png` for the Items menu. New items go in `ITEMS` in main.gd.
- `art/src/giant.py`: Giant Levi (from photos), exported via `export_characters.py` to `assets/characters/giant.glb`.
- `art/src/crane.py`: tower crane + wrecking ball → `assets/crane/crane.glb` (jib tip at Godot (9, 14.6, 0)).
- `art/characters/*.blend`: the four explorers; `art/src/export_characters.py` groups their parts into
  jointed limbs and exports `assets/characters/<name>.glb` (`blender --background art/characters/fox.blend --python art/src/export_characters.py`).
