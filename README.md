# Magnet World

A 3D magnetic-tile building game (think Magna-Tiles meets Lego Worlds), made by Geoff & Levi in Godot 4.

## Run it

    /Applications/Godot.app/Contents/MacOS/Godot --path ~/Desktop/Work/Personal/magnet-world

Or open the folder in the Godot editor (Import → pick `project.godot`) and press ▶.

## How it plays

Everything works from the keyboard (an on-screen controls card shows the keys; H hides it):

| Build mode | | Explore mode (Tab) | |
|---|---|---|---|
| W A S D | move the aim (crosshair) | W A S D | walk |
| Left / Right | spin camera | Space | jump |
| Up / Down | aim higher / lower | Up / Down | look up / down |
| Q / E | zoom out / in | Q / E | zoom |
| Space | place tile | P | pick explorer |
| R | flip / turn the tile | Tab | back to building |
| Backspace | remove tile | | |
| 1–5, C, Z, X | shape, colour, undo, eraser | | |
| I | Items menu (add our couch!) | | |

The mouse still works too (click to place, right-click to remove, right-drag to spin, scroll to zoom).

- Shapes: square, triangle, right triangle (half a square, Picasso Tiles style), tall triangle, big square.
- Point at a tile edge and the new tile hinges off it like a magnet; if its corners would meet existing
  corners it snaps to that angle. R flips through the other ways it fits (mirror image first).
- Items (I): add things to the world, like **Our Living Room Couch**. Move the see-through preview, R turns it
  (45° steps), Space puts it down, Esc cancels. Backspace / eraser removes it; Z undoes. You can climb on it.
- Pick your explorer (P): Kid, Fox, Robot or Dino; arrows + Enter or 1–4. The choice is remembered.
- The world autosaves.

Dev flags (after `--`): `--demo` builds a sample scene (doesn't touch the save), `--shot=path.png` saves a screenshot and quits,
`--cam=yaw,pitch,dist,x,y,z`, `--play`, `--char=fox`, `--walk`, `--picker`,
`--keys=d:20,space:1` (replay key presses: name:frames held), `--shotframe=N`.

## Art pipeline (Blender 5.2)

- `art/src/tiles.py`, `art/src/islands.py`: regenerate the tile and island models into `assets/`.
- `art/src/couch.py`: our living-room sectional, modelled from photos (real metres), exported to
  `assets/items/couch.glb` with a thumbnail `couch.png` for the Items menu. New items go in `ITEMS` in main.gd.
- `art/characters/*.blend`: the four explorers; `art/src/export_characters.py` groups their parts into
  jointed limbs and exports `assets/characters/<name>.glb` (`blender --background art/characters/fox.blend --python art/src/export_characters.py`).
