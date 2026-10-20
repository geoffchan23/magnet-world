# Magnet World

A 3D magnetic-tile building game (think Magna-Tiles meets Lego Worlds), made by Geoff & Levi in Godot 4.

## Run it

    /Applications/Godot.app/Contents/MacOS/Godot --path ~/Desktop/Work/Personal/magnet-world

Or open the folder in the Godot editor (Import → pick `project.godot`) and press ▶.

## How it plays

- **Build mode**: click the ground to lay a floor tile, then hover any tile edge — the new tile hinges off it like a magnet.
  If its corners would meet existing corners, it snaps to that angle (that's how boxes and pyramid roofs close up).
  **R** flips through the other ways it can attach.
- **Play mode** (Tab / Play! button): drop in a little explorer and walk/jump around your builds.
- **Pick your explorer**: the portrait button (or P) opens the character picker: Kid, Fox, Robot or Dino. Switch any time; the choice is remembered.
- The world autosaves.

Dev flags (after `--`): `--demo` builds a sample scene (doesn't touch the save), `--shot=path.png` saves a screenshot and quits,
`--cam=yaw,pitch,dist,x,y,z`, `--play`, `--char=fox`, `--walk`, `--picker`.

## Art pipeline (Blender 5.2)

- `art/src/tiles.py`, `art/src/islands.py`: regenerate the tile and island models into `assets/`.
- `art/characters/*.blend`: the four explorers; `art/src/export_characters.py` groups their parts into
  jointed limbs and exports `assets/characters/<name>.glb` (`blender --background art/characters/fox.blend --python art/src/export_characters.py`).
