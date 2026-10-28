# Magnet World

A 3D magnetic-tile building game (think Magna-Tiles meets Lego Worlds), made by Geoff & Levi in Godot 4.
You build on a dirt lot in the middle of a ruined, post-apocalyptic city, and you can drive a buggy around it.

## Run it

    /Applications/Godot.app/Contents/MacOS/Godot --path ~/Desktop/Work/Personal/magnet-world

Or open the folder in the Godot editor (Import → pick `project.godot`) and press ▶.

## How it plays

Everything works from the keyboard (an on-screen controls card shows the keys; H hides it):

| Build mode | | Explore mode (Tab) | | Driving (Enter by the buggy) | |
|---|---|---|---|---|---|
| W A S D | move the crosshair (scrolls at the screen edge) | W A S D | walk | W / S | gas / brake + reverse |
| Left / Right | spin camera | Space | jump | A / D | steer |
| Up / Down | tilt camera | Up / Down | look up / down | Space | handbrake |
| Q / E | zoom out / in | Q / E | zoom | R | flip back over |
| Space | place tile | P | pick explorer | Left / Right | look around |
| R | flip / turn the tile | Enter | hop in the buggy | Enter | hop out |
| F / G | tilt the tile to any angle (stand ground tiles up) | Tab | back to building | | |
| Backspace | remove tile | | | | |
| 1–5, C, Z, X | shape, colour, undo, eraser | | |
| I | Items menu (add our couch!) | | |
| K | Smash! menu (Giant Levi or the wrecking ball) | | |

The mouse still works too (click to place, right-click to remove, right-drag to spin, scroll to zoom).

- Shapes: square, triangle, right triangle (half a square, Picasso Tiles style), tall triangle, big square.
- Point at a tile edge and the new tile hinges off it like a magnet; if its corners would meet existing
  corners it snaps to that angle. R flips through the other ways it fits (mirror image first).
- Items (I): add things to the world, like **Our Living Room Couch**. Move the see-through preview, R turns it
  (45° steps), Space puts it down, Esc cancels. Backspace / eraser removes it; Z undoes. You can climb on it.
- Smash! (K): **Giant Levi** drops in and smashes your build a random way (stomp, kick, swipe or
  double-fist smash), or a **crane** drops in and swings a wrecking ball through it. Every tile becomes a
  physics piece and goes flying; Z (undo) rebuilds the whole thing. Code: `destroy.gd`.
- Pick your explorer (P): Kid, Fox, Robot or Dino; arrows + Enter or 1–4. The choice is remembered.
- The city (`city.gd`) is generated from a seed out of a Blender kit of building storeys, roofs, ruined tops and
  street junk: a grid of blocks around the lot, taller towards the edge, then open wasteland and a far-off skyline.
  Every copy of a kit piece is one MultiMesh, so it stays cheap on an iPad.
- The buggy (`vehicle.gd`) is a VehicleBody3D: your explorer sits in it. Barrels and tyres get knocked flying, and
  crashing into your build fast enough smashes it (Z rebuilds).
- The world autosaves.

Dev flags (after `--`): `--demo` builds a sample scene (doesn't touch the save), `--shot=path.png` saves a screenshot and quits,
`--cam=yaw,pitch,dist,x,y,z`, `--play`, `--char=fox`, `--walk`, `--picker`,
`--keys=d:20,space:1` (replay key presses: name:frames held; the first press can get lost, so lead with `shift:20`),
`--shotframe=N`, `--smash=ball|giant|giant:kick`, `--drive` (start in the buggy), `--buggy=x,z,heading`.

## Art pipeline (Blender 5.2)

- `art/src/tiles.py`: regenerates the tile models into `assets/tiles/`.
- `art/src/city_kit.py`: the ruined-city kit → `assets/city/kit.glb` (4x4 storeys, roofs, ruins, wrecks, rubble, props).
  Godot swaps its materials (by name) for the Poly Haven textures in `assets/textures/`.
- `art/src/buggy.py`: the scavenger buggy → `assets/vehicles/buggy.glb` (Body, four wheels, Seat).
- `art/src/couch.py`: our living-room sectional, modelled from photos (real metres), exported to
  `assets/items/couch.glb` with a thumbnail `couch.png` for the Items menu. New items go in `ITEMS` in main.gd.
- `art/src/giant.py`: Giant Levi (from photos), exported via `export_characters.py` to `assets/characters/giant.glb`.
- `art/src/crane.py`: tower crane + wrecking ball → `assets/crane/crane.glb` (jib tip at Godot (9, 14.6, 0)).
- `art/characters/*.blend`: the four explorers; `art/src/export_characters.py` groups their parts into
  jointed limbs and exports `assets/characters/<name>.glb` (`blender --background art/characters/fox.blend --python art/src/export_characters.py`).
