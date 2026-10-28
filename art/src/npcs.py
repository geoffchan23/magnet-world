# NPC people and creatures for the ruined city: toy-real figures built from primitives.
# Run one:  blender --background --python art/src/npcs.py -- survivor
# Run all:  blender --background --python art/src/npcs.py -- all
# Each run writes art/characters/npc_<name>.blend (parts, pre-join), concepts/npc_<name>.png,
# assets/portraits/npc_<name>.png (320px) and assets/characters/npc_<name>.glb.
#
# Conventions (same as the explorers; see export_characters.py / player.gd):
# - Blender: faces -Y, feet on z=0, L = -X. After glTF import Godot sees them facing +Z.
# - Same units as kid.glb (the kid is ~0.97 tall; the game scales by 0.55).
# - Every limb is one node, origin at its joint, identity rotation/scale (transforms baked),
#   so animation = rotate the node about its origin.
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import npc_kit
importlib.reload(npc_kit)
from npc_kit import *
from mathutils import Vector, Quaternion, Euler

SCRATCH = os.environ.get("NPC_SCRATCH", "")
X90 = Quaternion((1, 0, 0), math.pi / 2)
Y90 = Quaternion((0, 1, 0), math.pi / 2)


def sides():
    return ((-1, "L"), (1, "R"))


# ====================================================================== 1. Survivor
def survivor():
    reset("Survivor")
    black, white = common_mats()
    skin = mat("Skin", "eab38a", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "9a4524", rough=0.45)
    hood = mat("Hoodie", "5f9441", rough=0.5, coat=0.25)
    hood2 = mat("HoodieDark", "467233", rough=0.55, coat=0.2)
    shorts = mat("Cargo", "56677d", rough=0.55, coat=0.15)
    boot = mat("Boot", "8a5330", rough=0.4, coat=0.4)
    sole = mat("Sole", "3a2c26", rough=0.6, coat=0.1)
    strap = mat("GoggleStrap", "4a3428", rough=0.5, coat=0.2)
    brass = mat("Brass", "d9a441", rough=0.25, metal=0.8, coat=0.3)
    lens = mat("Lens", "6fe0ff", rough=0.05, coat=1.0, emit="49c8ff", emit_strength=0.6)
    scarf = mat("Scarf", "e8473a", rough=0.5, coat=0.2)
    canvas = mat("Canvas", "b58a55", rough=0.55, coat=0.2)
    canvas2 = mat("CanvasDark", "8d6a3f", rough=0.55, coat=0.2)
    patch = mat("Patch", "f2a33a", rough=0.5, coat=0.2)
    patch2 = mat("PatchBlue", "3f8fd8", rough=0.5, coat=0.2)
    roll = mat("Bedroll", "2f6fa8", rough=0.55, coat=0.2)
    tin = mat("Tin", "b9c0c8", rough=0.25, metal=0.9, coat=0.2)
    blush = mat("Blush", "ff8c7c", rough=0.6, coat=0.0)
    mouth = mat("Mouth", "6a2a20", rough=0.4)
    plaster = mat("Plaster", "f6d9b0", rough=0.5, coat=0.1)
    dirt = mat("Smudge", "b98d6c", rough=0.7, coat=0.0)
    knee = mat("KneePad", "4a5260", rough=0.4, coat=0.4)

    with limb("Head"):
        hc, hr = (0, 0, 0.70), (0.235, 0.215, 0.215)
        sph("Head", hc, hr, skin, seg=24, ring=12, hero=True)
        # one hair mesh: a cap a bit up/back from the skull (natural hairline where they cross),
        # with soft tufts pushed out of it, swept up and to the right; a few fringe flicks
        bumps = [((0.05, -0.75, 0.65), 0.07, 0.3, (0.03, -0.01, 0.0)),    # front swoop
                 ((-0.25, -0.2, 1.0), 0.1, 0.32, (0.035, 0, 0)),        # top tufts
                 ((0.3, -0.05, 1.0), 0.095, 0.3, (0.04, 0, 0)),
                 ((0.0, 0.55, 0.85), 0.085, 0.32, (0.03, 0.01, 0)),     # crown
                 ((-0.75, 0.25, 0.6), 0.05, 0.3, (0.0, 0.0, 0.0)),      # sides
                 ((0.75, 0.25, 0.55), 0.06, 0.3, (0.02, 0.0, 0.0)),
                 ((0.0, 0.9, 0.3), 0.05, 0.3, (0, 0.01, -0.01))]        # nape
        blob("Hair", (0, 0.02, 0.735), (0.243, 0.222, 0.2), hair, bumps, seg=28, ring=16)
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.232, 0.01, 0.68), (0.035, 0.028, 0.048), skin)
            eye(f"Eye_{side}", hc, hr, (s * 0.37, -1, -0.12), 0.036, 0.05, black, white)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.22, -1, 0.09), (s * 0.37, -1, 0.14), (s * 0.52, -1, 0.1)],
                                         lift=0.004), hair, r=0.0085, radii=[0.7, 1, 0.7], caps=False)
            decal(f"Blush_{side}", hc, hr, (s * 0.62, -1, -0.42), (0.034, 0.008, 0.02), blush)
        decal("Nose", hc, hr, (0, -1, -0.26), (0.02, 0.014, 0.016), skin, sink=0.2)
        # lopsided, brave grin
        tube("Smile", arc_on(hc, hr, [(-0.13, -1, -0.43), (-0.05, -1, -0.49), (0.06, -1, -0.48), (0.16, -1, -0.38)]),
             mouth, r=0.0075)
        # sticking plaster on the cheek + a smudge of dirt on the other
        p, n = on(hc, hr, (0.58, -1, -0.2), 0.002)
        q = facing(n) @ Quaternion((0, 1, 0), 0.5)
        box("Plaster", p, (0.06, 0.008, 0.022), plaster, bevel=0.004, rot=q)
        decal("Smudge", hc, hr, (-0.6, -1, -0.15), (0.022, 0.006, 0.014), dirt)
        # aviator goggles pushed up on the forehead
        torus("Goggle_Strap", (0, 0.01, 0.775), 0.236, 0.014, strap, rot=(math.radians(-14), 0, 0),
              scale=(1.02, 0.95, 1.0))
        for s, side in sides():
            p, n = on(hc, hr, (s * 0.3, -1, 0.5), 0.012)
            q = Vector((0, 0, 1)).rotation_difference(n)
            cyl(f"Goggle_{side}", p, 0.058, 0.04, brass, rot=q)
            sph(f"Goggle_{side}_Lens", p + n * 0.016, (0.046, 0.046, 0.014), lens, rot=q)
            sph(f"Goggle_{side}_Glint", p + n * 0.026 + Vector((-0.016 * s, 0, 0.018)), (0.011, 0.011, 0.004),
                white, rot=q)
        cyl_between("Goggle_Bridge", on(hc, hr, (-0.12, -1, 0.52), 0.02)[0], on(hc, hr, (0.12, -1, 0.52), 0.02)[0],
                    0.01, brass)

    with limb("Body"):
        sph("Torso", (0, 0, 0.385), (0.16, 0.132, 0.17), hood, seg=20, ring=10, hero=True)
        sph("Hood", (0, 0.085, 0.51), (0.135, 0.075, 0.06), hood2)
        decal("Pocket", (0, 0, 0.385), (0.16, 0.132, 0.17), (0, -1, -0.45), (0.1, 0.03, 0.055), hood2, sink=0.75)
        p, n = on((0, 0, 0.385), (0.16, 0.132, 0.17), (-0.45, -1, 0.15), 0.0)
        box("Patch", p + n * 0.002, (0.05, 0.012, 0.045), patch, bevel=0.005, rot=facing(n))
        for s, side in sides():
            tube(f"Drawstring_{side}", [(s * 0.03, -0.122, 0.495), (s * 0.036, -0.138, 0.455)], plaster, r=0.006, caps=False)
        torus("Scarf", (0, -0.005, 0.535), 0.105, 0.042, scarf, scale=(1, 0.92, 0.9))
        tube("Scarf_Tail", [(-0.06, -0.1, 0.52), (-0.095, -0.13, 0.46), (-0.09, -0.125, 0.39)], scarf, r=0.03,
             radii=[1, 0.95, 0.8], br=2)
        sph("Shorts", (0, 0, 0.255), (0.152, 0.125, 0.088), shorts)
        # patched backpack with a bed roll and a tin mug
        box("Backpack", (0, 0.17, 0.40), (0.23, 0.11, 0.24), canvas, bevel=0.035)
        box("Backpack_Pocket", (0, 0.228, 0.35), (0.16, 0.035, 0.1), canvas2, bevel=0.014)
        box("Backpack_Flap", (0, 0.2, 0.495), (0.21, 0.085, 0.05), canvas2, bevel=0.018)
        box("Backpack_Patch", (0.06, 0.247, 0.36), (0.045, 0.006, 0.04), patch2, bevel=0.004)
        cyl("Bedroll", (0, 0.17, 0.565), 0.052, 0.3, roll, rot=Y90)
        for x in (-0.09, 0.09):
            torus(f"Bedroll_Tie{x}", (x, 0.17, 0.565), 0.054, 0.008, canvas2, rot=(0, math.pi / 2, 0), seg=10)
        cyl("Mug", (0.14, 0.2, 0.33), 0.03, 0.05, tin)
        for s, side in sides():
            tube(f"Strap_{side}", [(s * 0.075, 0.13, 0.49), (s * 0.078, 0.03, 0.545), (s * 0.085, -0.098, 0.5),
                                   (s * 0.088, -0.127, 0.40)], canvas2, r=0.014, caps=False)

    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Sleeve_{side}", (s * 0.148, 0, 0.455), (0.058, 0.056, 0.056), hood)
            tube(f"Arm_{side}", [(s * 0.17, -0.005, 0.44), (s * 0.205, -0.015, 0.37), (s * 0.213, -0.024, 0.32)],
                 hood, r=0.034, caps=False)
            torus(f"Cuff_{side}", (s * 0.214, -0.025, 0.315), 0.033, 0.012, hood2)
            sph(f"Hand_{side}", (s * 0.218, -0.028, 0.285), (0.042, 0.04, 0.046), skin)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.068, 0, 0.2), (s * 0.07, 0, 0.08)], skin, r=0.04, caps=False)
            sph(f"Leg_{side}_Cargo", (s * 0.07, -0.005, 0.2), (0.058, 0.055, 0.05), shorts)
            if s < 0:
                sph("Leg_L_KneePad", (s * 0.07, -0.034, 0.135), (0.035, 0.016, 0.03), knee)
            cyl(f"Boot_{side}_Cuff", (s * 0.072, -0.01, 0.1), 0.05, 0.05, boot)
            sph(f"Boot_{side}", (s * 0.074, -0.03, 0.052), (0.064, 0.094, 0.05), boot)
            sph(f"Sole_{side}", (s * 0.074, -0.03, 0.02), (0.066, 0.096, 0.02), sole)

    hmn = 0.70 - 0.215
    pivots = {"Body": (0, 0, 0), "Head": (0, 0, hmn + 0.05),
              "ArmL": (-0.17, 0, 0.44), "ArmR": (0.17, 0, 0.44),
              "LegL": (-0.068, 0, 0.2), "LegR": (0.068, 0, 0.2)}
    return dict(backdrop="dce9d6", pivots=pivots, target=(0, 0, 0.5), dist=2.15, kind="friendly person")


# ====================================================================== grown-up proportions
# Grown-ups are a head taller than the kid figures: hips 0.33, shoulders ~0.65, head centre ~0.9.
ADULT_HEAD = 0.9


def adult_pivots(shoulder_x=0.2, shoulder_z=0.64, hip_x=0.085, hip_z=0.33, head_bottom=0.70):
    return {"Body": (0, 0, 0), "Head": (0, 0, head_bottom + 0.05),
            "ArmL": (-shoulder_x, 0, shoulder_z), "ArmR": (shoulder_x, 0, shoulder_z),
            "LegL": (-hip_x, 0, hip_z), "LegR": (hip_x, 0, hip_z)}


# ====================================================================== 2. Mechanic
def mechanic():
    reset("Mechanic")
    black, white = common_mats()
    skin = mat("Skin", "b97a52", rough=0.45, coat=0.25, sss=0.12)
    hair = mat("Hair", "2b1f1a", rough=0.5, coat=0.2)
    shirt = mat("Shirt", "f0b23a", rough=0.5, coat=0.25)
    denim = mat("Overalls", "3a6cc0", rough=0.5, coat=0.25)
    denim2 = mat("OverallsDark", "2a4f8f", rough=0.55, coat=0.2)
    cap = mat("Cap", "d9412f")
    boot = mat("Boot", "4a3b33", rough=0.4, coat=0.4)
    sole = mat("Sole", "1e1a19", rough=0.6, coat=0.1)
    steel = mat("Steel", "c9ced6", rough=0.18, metal=1.0, coat=0.0)
    brass = mat("Brass", "d9a441", rough=0.25, metal=0.8, coat=0.3)
    rag = mat("Rag", "e64a4a", rough=0.6, coat=0.1)
    grease = mat("Grease", "5a4c50", rough=0.7, coat=0.0)
    mouth = mat("Mouth", "5a2218", rough=0.4)
    blush = mat("Blush", "e0806a", rough=0.6, coat=0.0)
    pencil = mat("Pencil", "ffcc33", rough=0.4)

    with limb("Head"):
        hc, hr = (0, 0, ADULT_HEAD), (0.22, 0.2, 0.2)
        sph("Head", hc, hr, skin, seg=24, ring=12, hero=True)
        # cap on backwards, brim over the neck
        cc, cr = (0, 0.012, 0.955), (0.228, 0.212, 0.185)
        hsph("Cap", cc, cr, cap, seg=24, ring=12, hero=True)
        sph("Cap_Brim", (0, 0.2, 0.965), (0.14, 0.12, 0.016), cap, rot=Quaternion((1, 0, 0), math.radians(14)))
        sph("Cap_Button", (0, 0.012, 1.14), (0.024, 0.024, 0.014), cap)
        p, n = on(cc, cr, (0, -1, 0.42), 0.003)
        torus("Cap_Gear", p, 0.032, 0.009, white, rot=aim(n), seg=12)
        sph("Cap_GearHub", p, (0.012, 0.012, 0.004), white, rot=aim(n))
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.218, 0.01, 0.885), (0.034, 0.028, 0.048), skin)
            decal(f"Sideburn_{side}", hc, hr, (s * 0.9, -0.3, 0.05), (0.035, 0.01, 0.05), hair, sink=0.3)
            eye(f"Eye_{side}", hc, hr, (s * 0.34, -1, -0.04), 0.03, 0.042, black, white)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.2, -1, 0.17), (s * 0.34, -1, 0.21), (s * 0.5, -1, 0.17)],
                                         lift=0.004), hair, r=0.013, radii=[0.8, 1, 0.7], caps=False)
            decal(f"Blush_{side}", hc, hr, (s * 0.62, -1, -0.3), (0.034, 0.008, 0.02), blush)
            # big friendly handlebar moustache
            p, n = on(hc, hr, (s * 0.15, -1, -0.34), 0.012)
            sph(f"Moustache_{side}", p, (0.078, 0.032, 0.036), hair,
                rot=facing(n) @ Quaternion((0, 1, 0), s * 0.32))
            p, n = on(hc, hr, (s * 0.42, -1, -0.26), 0.01)
            sph(f"Moustache_{side}_Curl", p, (0.024, 0.024, 0.03), hair)
        p, n = on(hc, hr, (0, -1, -0.17), 0.014)
        sph("Nose", p, (0.042, 0.036, 0.034), skin)
        tube("Smile", arc_on(hc, hr, [(t * 0.14, -1, -0.5 - 0.06 * (1 - t * t)) for t in (-1, 0, 1)]), mouth, r=0.008)
        decal("Grease", hc, hr, (-0.55, -1, -0.22), (0.03, 0.006, 0.016), grease)
        cyl("Pencil", (0.2, 0.045, 0.95), 0.008, 0.11, pencil, rot=aim((0.15, 1, -0.35)))

    with limb("Body"):
        tc, tr = (0, 0, 0.52), (0.19, 0.155, 0.2)
        sph("Torso", tc, tr, shirt, seg=20, ring=10, hero=True)
        sph("Pants", (0, 0, 0.38), (0.185, 0.15, 0.12), denim, seg=20, ring=10)
        decal("Bib", tc, tr, (0, -1, -0.08), (0.13, 0.045, 0.15), denim, sink=0.62, seg=16, ring=8)
        decal("Bib_Pocket", tc, tr, (0, -1, 0.05), (0.06, 0.02, 0.045), denim2, sink=0.05)
        for s, side in sides():
            p, n = on(tc, tr, (s * 0.42, -1, 0.42), 0.006)
            sph(f"Button_{side}", p, (0.017, 0.012, 0.017), brass, rot=facing(n))
            tube(f"Strap_{side}", [tuple(p), (s * 0.1, -0.11, 0.69), (s * 0.11, 0.0, 0.725), (s * 0.1, 0.13, 0.64),
                                   (s * 0.08, 0.15, 0.5)], denim, r=0.017, caps=False)
        # rag hanging out of the back pocket + a smudge on the overalls
        sph("Rag", (0.09, 0.155, 0.35), (0.045, 0.02, 0.07), rag, rot=Quaternion((0, 1, 0), 0.25))
        decal("Pants_Smudge", (0, 0, 0.38), (0.185, 0.15, 0.12), (-0.5, -1, -0.1), (0.03, 0.006, 0.02), grease)

    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Sleeve_{side}", (s * 0.195, 0, 0.635), (0.07, 0.066, 0.068), shirt)
            torus(f"Sleeve_{side}_Roll", (s * 0.212, -0.004, 0.592), 0.044, 0.016, shirt, rot=(0, s * 0.35, 0))
            tube(f"Arm_{side}", [(s * 0.21, 0, 0.62), (s * 0.245, -0.02, 0.5), (s * 0.255, -0.03, 0.44)], skin,
                 r=0.038, caps=False)
            sph(f"Hand_{side}", (s * 0.262, -0.035, 0.41), (0.05, 0.048, 0.056), skin, seg=12, ring=6)
            if s > 0:  # big shiny wrench
                wx, wy = 0.262, -0.055
                box("Wrench_Handle", (wx, wy, 0.37), (0.03, 0.016, 0.24), steel, bevel=0.007)
                torus("Wrench_Ring", (wx, wy, 0.51), 0.03, 0.012, steel, rot=(math.pi / 2, 0, 0), seg=12)
                sph("Wrench_Head", (wx, wy, 0.235), (0.045, 0.014, 0.036), steel)
                for k in (-1, 1):
                    box(f"Wrench_Jaw{k}", (wx + k * 0.03, wy, 0.2), (0.022, 0.024, 0.055), steel, bevel=0.007,
                        rot=(0, k * 0.35, 0))
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.085, 0, 0.33), (s * 0.088, 0, 0.12)], denim, r=0.062, caps=False)
            torus(f"Leg_{side}_Cuff", (s * 0.088, 0, 0.12), 0.06, 0.018, denim2)
            sph(f"Boot_{side}", (s * 0.09, -0.035, 0.058), (0.075, 0.11, 0.058), boot, seg=14, ring=7)
            sph(f"Sole_{side}", (s * 0.09, -0.035, 0.022), (0.078, 0.113, 0.022), sole)

    return dict(backdrop="dfe4ee", pivots=adult_pivots(0.2, 0.635), target=(0, 0, 0.58), dist=2.5,
                kind="friendly person")


# ====================================================================== 3. Trader
def trader():
    reset("Trader")
    black, white = common_mats()
    skin = mat("Skin", "e3a984", rough=0.45, coat=0.25, sss=0.12)
    beard = mat("Beard", "f1ece3", rough=0.6, coat=0.1)
    nose = mat("RosyNose", "e88f78", rough=0.4, coat=0.3)
    hat = mat("Hat", "8b6b47", rough=0.55, coat=0.2)
    band = mat("HatBand", "c4473a", rough=0.5, coat=0.2)
    feather = mat("Feather", "34b3a0", rough=0.5, coat=0.2)
    pon = mat("Poncho", "c8673c", rough=0.55, coat=0.2)
    pon2 = mat("PonchoDark", "9c4a2b", rough=0.55, coat=0.2)
    p1 = mat("PatchBlue", "4f8fc0", rough=0.5, coat=0.2)
    p2 = mat("PatchYellow", "e3b740", rough=0.5, coat=0.2)
    scarf = mat("Scarf", "e3b740", rough=0.5, coat=0.2)
    pants = mat("Pants", "67646f", rough=0.55, coat=0.15)
    boot = mat("Boot", "5a3d2a", rough=0.4, coat=0.4)
    sole = mat("Sole", "2a1f19", rough=0.6, coat=0.1)
    wood = mat("Wood", "a87b4f", rough=0.55, coat=0.2)
    sack = mat("Sack", "cdb68b", rough=0.6, coat=0.1)
    roll = mat("Bedroll", "4c6fb5", rough=0.55, coat=0.2)
    metal = mat("Pot", "aab3bc", rough=0.25, metal=0.85, coat=0.2)
    copper = mat("Copper", "c77a43", rough=0.25, metal=0.8, coat=0.3)
    rubber = mat("Tyre", "2c2b2e", rough=0.6, coat=0.1)
    teddy = mat("Teddy", "b07a4a", rough=0.6, coat=0.1)
    teddy2 = mat("TeddyMuzzle", "e8cfa8", rough=0.6, coat=0.1)
    brolly = mat("Umbrella", "3fa37a", rough=0.4, coat=0.4)
    brass = mat("Brass", "d9a441", rough=0.25, metal=0.8, coat=0.3)
    glow = mat("LanternGlow", "ffd27a", rough=0.2, coat=0.3, emit="ffbe4a", emit_strength=5)
    flag = mat("Flag", "ff5a4a", rough=0.5, coat=0.2)

    with limb("Head"):
        hc, hr = (0, 0, 0.88), (0.21, 0.195, 0.195)
        sph("Head", hc, hr, skin, seg=24, ring=12, hero=True)
        # big fluffy beard: one lumpy mesh hanging off the jaw
        bumps = [((0, -0.4, -1), 0.07, 0.5, (0, -0.015, -0.02)), ((-0.7, -0.5, -0.5), 0.035, 0.35),
                 ((0.7, -0.5, -0.5), 0.035, 0.35), ((-0.3, -1, -0.6), 0.03, 0.3), ((0.3, -1, -0.6), 0.03, 0.3)]
        blob("Beard", (0, -0.075, 0.79), (0.175, 0.13, 0.135), beard, bumps, seg=20, ring=12, hero=False)
        for s, side in sides():
            p, n = on(hc, hr, (s * 0.16, -1, -0.3), 0.016)
            sph(f"Moustache_{side}", p, (0.075, 0.034, 0.036), beard, rot=facing(n) @ Quaternion((0, 1, 0), s * 0.5))
            sph(f"Ear_{side}", (s * 0.205, 0.01, 0.87), (0.032, 0.026, 0.045), skin)
            eye(f"Eye_{side}", hc, hr, (s * 0.3, -1, 0.0), 0.026, 0.034, black, white, shine2=False)
            p, n = on(hc, hr, (s * 0.3, -1, 0.0), 0.02)
            torus(f"Specs_{side}", p, 0.046, 0.0065, brass, rot=aim(n), seg=16, mseg=4)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.16, -1, 0.26), (s * 0.32, -1, 0.31), (s * 0.5, -1, 0.24)],
                                         lift=0.006), beard, r=0.014, radii=[0.8, 1.1, 0.6], caps=False)
            cyl_between(f"Specs_{side}_Arm", on(hc, hr, (s * 0.53, -1, 0.02), 0.02)[0], (s * 0.205, 0.0, 0.89),
                        0.005, brass, seg=6)
        cyl_between("Specs_Bridge", on(hc, hr, (-0.1, -1, 0.04), 0.024)[0], on(hc, hr, (0.1, -1, 0.04), 0.024)[0],
                    0.005, brass, seg=6)
        p, n = on(hc, hr, (0, -1, -0.13), 0.02)
        sph("Nose", p, (0.046, 0.042, 0.042), nose)
        # wide-brimmed traveller's hat with a feather
        cyl("Hat_Brim", (0, 0.01, 1.0), 0.32, 0.022, hat, seg=28, rot=Quaternion((1, 0, 0), math.radians(-6)))
        cyl("Hat_Crown", (0, 0.015, 1.075), 0.17, 0.14, hat, r2=0.145, seg=20)
        sph("Hat_Top", (0, 0.015, 1.145), (0.145, 0.14, 0.03), hat)
        cyl("Hat_Band", (0, 0.013, 1.03), 0.173, 0.04, band, r2=0.166, seg=20, bevel=0.004)
        sph("Hat_Feather", (0.15, 0.06, 1.1), (0.022, 0.012, 0.1), feather, rot=aim((0.5, 0.4, 1)))

    with limb("Body"):
        cyl("Poncho", (0, 0.0, 0.5), 0.245, 0.44, pon, r2=0.13, seg=22, bevel=0.03)
        sph("Poncho_Shoulders", (0, 0, 0.68), (0.175, 0.15, 0.075), pon)
        torus("Poncho_Hem", (0, 0, 0.285), 0.238, 0.018, pon2, seg=22)
        box("Poncho_Patch1", (-0.11, -0.19, 0.42), (0.07, 0.02, 0.07), p1, bevel=0.006, rot=(0.25, 0, 0.3))
        box("Poncho_Patch2", (0.12, -0.165, 0.56), (0.055, 0.02, 0.05), p2, bevel=0.006, rot=(0.28, 0, -0.35))
        torus("Scarf", (0, 0, 0.725), 0.105, 0.036, scarf, scale=(1, 0.95, 0.9))
        # the big pack of junk: frame, lumpy sack, and stuff hanging off it
        for s in (-1, 1):
            cyl_between(f"Pack_Pole{s}", (s * 0.15, 0.2, 0.3), (s * 0.15, 0.2, 1.28), 0.017, wood, seg=8)
            tube(f"Pack_Strap{s}", [(s * 0.09, 0.14, 0.62), (s * 0.1, 0.02, 0.73), (s * 0.11, -0.12, 0.66),
                                    (s * 0.12, -0.15, 0.55)], pon2, r=0.016, caps=False)
        cyl_between("Pack_Bar", (-0.17, 0.2, 1.22), (0.17, 0.2, 1.22), 0.016, wood, seg=8)
        bumps = [((0.6, 0.5, 0.4), 0.04, 0.5), ((-0.5, 0.6, -0.3), 0.04, 0.5), ((0.1, 1, -0.5), 0.03, 0.6),
                 ((0, 0, 1), 0.03, 0.5)]
        blob("Pack_Sack", (0, 0.32, 0.73), (0.22, 0.145, 0.3), sack, bumps, seg=20, ring=12)
        torus("Pack_Rope", (0, 0.32, 0.73), 0.205, 0.012, pon2, scale=(1.05, 0.7, 1))
        cyl("Pack_Bedroll", (0, 0.28, 1.08), 0.075, 0.42, roll, rot=Y90)
        torus("Pack_Tyre", (0, 0.48, 0.66), 0.115, 0.045, rubber, rot=(math.pi / 2, 0, 0), seg=18)
        # pot on the right, frying pan on the left
        cyl("Pack_Pot", (0.25, 0.32, 0.55), 0.075, 0.1, metal, seg=14)
        torus("Pack_PotHandle", (0.25, 0.32, 0.61), 0.06, 0.006, metal, rot=(0, 0.6, 0), seg=10, mseg=4)
        cyl("Pack_Pan", (-0.245, 0.34, 0.8), 0.085, 0.02, copper, rot=Y90, seg=16)
        cyl_between("Pack_PanHandle", (-0.255, 0.34, 0.72), (-0.255, 0.34, 0.56), 0.013, wood, seg=6)
        # teddy bear peeking out of the top
        tb = Vector((0.08, 0.33, 1.17))
        sph("Teddy_Head", tb, (0.06, 0.055, 0.055), teddy)
        for s in (-1, 1):
            sph(f"Teddy_Ear{s}", tb + Vector((s * 0.045, 0.0, 0.045)), (0.022, 0.012, 0.022), teddy)
            sph(f"Teddy_Eye{s}", tb + Vector((s * 0.022, -0.05, 0.012)), (0.008, 0.006, 0.009), black)
        sph("Teddy_Muzzle", tb + Vector((0, -0.05, -0.012)), (0.024, 0.014, 0.018), teddy2)
        # closed umbrella and a little flag sticking up
        cone("Pack_Umbrella", (-0.1, 0.3, 1.0), (-0.25, 0.05, 1), 0.045, 0.3, brolly, seg=8)
        tube("Pack_UmbrellaHook", [(-0.16, 0.31, 1.27), (-0.17, 0.31, 1.33), (-0.14, 0.31, 1.345)], wood, r=0.008,
             caps=False)
        cyl_between("Pack_FlagPole", (0.15, 0.2, 1.28), (0.15, 0.2, 1.4), 0.008, wood, seg=6)
        box("Pack_Flag", (0.21, 0.2, 1.37), (0.11, 0.008, 0.065), flag, bevel=0.003)
        for k, (x, z) in enumerate([(0.2, 0.42), (0.13, 0.4)]):  # dangling tin cans
            cyl(f"Pack_Can{k}", (x, 0.43, z), 0.026, 0.06, metal, seg=10)

    for s, side in sides():
        with limb("Arm" + side):
            cyl_between(f"Sleeve_{side}", (s * 0.18, 0, 0.65), (s * 0.245, -0.025, 0.47), 0.05, pon, r2=0.065, seg=12)
            sph(f"Hand_{side}", (s * 0.25, -0.03, 0.43), (0.046, 0.044, 0.05), skin, seg=12, ring=6)
            if s < 0:  # a glowing lantern
                lx, ly = -0.25, -0.05
                torus("Lantern_Handle", (lx, ly, 0.385), 0.03, 0.006, brass, rot=(math.pi / 2, 0, 0), seg=10, mseg=4)
                cyl("Lantern_Cap", (lx, ly, 0.345), 0.04, 0.025, brass, r2=0.02, seg=10)
                cyl("Lantern_Glass", (lx, ly, 0.29), 0.034, 0.08, glow, seg=10)
                cyl("Lantern_Base", (lx, ly, 0.24), 0.042, 0.022, brass, seg=10)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.08, 0, 0.3), (s * 0.083, 0, 0.1)], pants, r=0.05, caps=False)
            sph(f"Boot_{side}", (s * 0.085, -0.035, 0.055), (0.068, 0.1, 0.056), boot, seg=14, ring=7)
            sph(f"Sole_{side}", (s * 0.085, -0.035, 0.02), (0.07, 0.102, 0.02), sole)

    return dict(backdrop="efe2cf", pivots=adult_pivots(0.19, 0.64, 0.08, 0.3, 0.88 - 0.195),
                target=(0, 0, 0.68), dist=2.75, kind="friendly person")


# ====================================================================== 4. Raider
def raider():
    reset("Raider")
    black, white = common_mats()
    skin = mat("Skin", "f0b58e", rough=0.45, coat=0.25, sss=0.12)
    mohawk = mat("Mohawk", "ff3d9e", rough=0.4, coat=0.4)
    stubble = mat("Stubble", "d9a08a", rough=0.7, coat=0.0)
    mask = mat("MaskBlack", "26262e", rough=0.35, coat=0.5)
    googly = mat("GooglyWhite", "fbfbf6", rough=0.15, coat=0.8)
    bandana = mat("Bandana", "d9363a", rough=0.5, coat=0.2)
    shirt = mat("Shirt", "2fa39a", rough=0.5, coat=0.25)
    vest = mat("Vest", "6a4630", rough=0.45, coat=0.3)
    pants = mat("Pants", "7b8a46", rough=0.55, coat=0.15)
    boot = mat("Boot", "2a2626", rough=0.4, coat=0.4)
    sole = mat("Sole", "5a5656", rough=0.6, coat=0.1)
    metal = mat("Metal", "9aa3ad", rough=0.3, metal=0.85, coat=0.2)
    spike = mat("Spike", "e9edf2", rough=0.2, metal=0.6, coat=0.4)
    gold = mat("Gold", "f2c13a", rough=0.25, metal=0.8, coat=0.3)
    stick = mat("PlungerStick", "c08a52", rough=0.5, coat=0.2)
    cup = mat("PlungerCup", "e0362f", rough=0.35, coat=0.4)
    cupin = mat("PlungerInside", "7a1a17", rough=0.5, coat=0.1)

    with limb("Head"):
        hc, hr = (0, 0, 0.9), (0.235, 0.215, 0.21)
        sph("Head", hc, hr, skin, seg=24, ring=12, hero=True)
        for s, side in sides():
            decal(f"Shaved_{side}", hc, hr, (s * 0.85, 0.15, 0.4), (0.12, 0.012, 0.09), stubble, sink=0.5)
        # big floppy pink mohawk: a row of fins from the brow to the nape
        for i, a in enumerate((-35, -10, 15, 40, 65, 92)):
            r = math.radians(a)
            p, n = on(hc, hr, (0, math.sin(r), math.cos(r)), -0.01)
            d = (n + Vector((0, 0.45, 0.25))).normalized()
            ln = (0.1, 0.13, 0.14, 0.13, 0.11, 0.08)[i]
            sph(f"Mohawk_{i}", p + d * ln * 0.55, (0.032, 0.05, ln), mohawk, rot=aim(d), seg=10, ring=7)
        # goofy goggle mask: black band, two cups, googly eyes looking different ways
        torus("Mask_Band", (0, 0.0, 0.915), 0.226, 0.018, mask, scale=(1.02, 0.98, 1.0), seg=22, mseg=5)
        for s, side, look in ((-1, "L", (-0.35, 0.45)), (1, "R", (0.4, -0.3))):
            p, n = on(hc, hr, (s * 0.36, -1, 0.07), 0.0)
            q = aim(n)
            cyl(f"Mask_Cup_{side}", p + n * 0.012, 0.062, 0.05, mask, rot=q, seg=16)
            pe = p + n * 0.035
            sph(f"Eye_{side}", pe, (0.052, 0.052, 0.022), googly, rot=q, seg=14, ring=7)
            side_v = q @ Vector((1, 0, 0))
            up_v = q @ Vector((0, 1, 0))
            pp = pe + n * 0.016 + side_v * look[0] * 0.03 + up_v * look[1] * 0.03
            sph(f"Eye_{side}_Pupil", pp, (0.02, 0.02, 0.01), black, rot=q)
            sph(f"Eye_{side}_Shine", pp + n * 0.006 + up_v * 0.007 - side_v * 0.006, (0.006, 0.006, 0.003), white,
                rot=q)
            # cross, wonky brows above the mask
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.17, -1, 0.3 - 0.03 * s), (s * 0.36, -1, 0.36), (s * 0.55, -1, 0.31)],
                                         lift=0.006), mask, r=0.014, radii=[1.1, 1, 0.7], caps=False)
            sph(f"Ear_{side}", (s * 0.232, 0.01, 0.88), (0.036, 0.028, 0.05), skin)
        torus("Earring", (-0.24, -0.005, 0.83), 0.022, 0.0055, gold, rot=(0, math.pi / 2, 0), seg=10, mseg=4)
        p, n = on(hc, hr, (0, -1, -0.12), 0.014)
        sph("Nose", p, (0.04, 0.036, 0.04), skin)
        # polka-dot bandana over the mouth
        bc, br = (0, -0.012, 0.86), (0.242, 0.222, 0.2)
        blob("Bandana", bc, br, bandana, [((0, -1, -0.75), 0.05, 0.35, (0, 0, -0.03))], seg=20, ring=12,
             squash_below=None, hero=False)
        for k, (x, z) in enumerate([(-0.4, -0.45), (0.05, -0.55), (0.45, -0.4), (-0.15, -0.8), (0.25, -0.75)]):
            decal(f"Bandana_Dot{k}", bc, br, (x, -1, z), (0.016, 0.004, 0.016), googly, sink=0.1)

    with limb("Body"):
        tc, tr = (0, 0, 0.52), (0.205, 0.165, 0.2)
        sph("Torso", tc, tr, shirt, seg=20, ring=10, hero=True)
        for s, side in sides():
            decal(f"Vest_{side}", tc, tr, (s * 0.62, -1, 0.05), (0.11, 0.05, 0.2), vest, sink=0.72, seg=12, ring=8)
            for k, z in enumerate((0.22, -0.1)):
                p, n = on(tc, tr, (s * 0.42, -1, z), 0.008)
                sph(f"Vest_Stud_{side}{k}", p, (0.012, 0.008, 0.012), gold, rot=facing(n))
        decal("Vest_Back", tc, tr, (0, 1, 0.05), (0.18, 0.06, 0.19), vest, sink=0.7, seg=12, ring=8)
        sph("Pants", (0, 0, 0.37), (0.198, 0.158, 0.11), pants, seg=20, ring=10)
        torus("Belt", (0, 0, 0.42), 0.195, 0.024, vest, scale=(1, 0.82, 1))
        box("Belt_Buckle", (0, -0.165, 0.42), (0.07, 0.02, 0.05), gold, bevel=0.008)
        box("Belt_Buckle_Hole", (0, -0.176, 0.42), (0.03, 0.006, 0.018), vest, bevel=0.003)

    for s, side in sides():
        with limb("Arm" + side):
            tube(f"Arm_{side}", [(s * 0.2, 0, 0.64), (s * 0.24, -0.015, 0.52), (s * 0.255, -0.03, 0.45)], skin,
                 r=0.043, caps=False)
            sph(f"Shoulder_{side}", (s * 0.2, 0, 0.635), (0.06, 0.058, 0.06), shirt)
            torus(f"Wristband_{side}", (s * 0.255, -0.03, 0.46), 0.042, 0.017, mask, seg=12)
            sph(f"Hand_{side}", (s * 0.262, -0.035, 0.415), (0.054, 0.05, 0.058), mask, seg=12, ring=6)
            if s < 0:  # spiky shoulder pad (and its strap)
                pc, pr = Vector((-0.215, 0, 0.665)), (0.105, 0.11, 0.075)
                hsph("Shoulder_Pad", pc, pr, metal, rot=Quaternion((0, 1, 0), -0.45), seg=16, ring=8)
                torus("Shoulder_Pad_Rim", pc + Vector((0.0, 0, -0.004)), 0.1, 0.012, mask, rot=(0, -0.45, 0), seg=16)
                for k, (dx, dy) in enumerate([(-0.55, -0.45), (-0.65, 0.4), (-0.05, 0.0)]):
                    d = Quaternion((0, 1, 0), -0.45) @ Vector((dx, dy, 1)).normalized()
                    base = pc + Vector((d.x * pr[0], d.y * pr[1], d.z * pr[2])) * 0.85
                    cone(f"Shoulder_Spike{k}", base, d, 0.03, 0.085, spike, seg=10)
                    sph(f"Shoulder_SpikeTip{k}", base + d * 0.082, (0.008, 0.008, 0.008), spike)
                tube("Shoulder_Pad_Strap", [(-0.17, -0.07, 0.62), (-0.04, -0.15, 0.55), (0.12, -0.13, 0.43)], mask,
                     r=0.013, caps=False)
            else:  # the mighty plunger
                px, py = 0.262, -0.04
                cyl_between("Plunger_Stick", (px, py, 0.33), (px, py, 0.7), 0.014, stick, seg=8)
                sph("Plunger_Cup", (px, py, 0.73), (0.068, 0.068, 0.05), cup, seg=14, ring=7)
                sph("Plunger_Rim", (px, py, 0.765), (0.06, 0.06, 0.012), cupin, seg=14, ring=4)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.09, 0, 0.32), (s * 0.093, 0, 0.12)], pants, r=0.064, caps=False)
            if s > 0:
                sph("Leg_R_KneePad", (s * 0.093, -0.058, 0.2), (0.048, 0.022, 0.045), mask)
            else:
                box("Leg_L_Patch", (s * 0.095, -0.06, 0.22), (0.05, 0.02, 0.045), vest, bevel=0.006)
            cyl(f"Boot_{side}_Top", (s * 0.093, -0.005, 0.115), 0.064, 0.07, boot, seg=14)
            sph(f"Boot_{side}", (s * 0.095, -0.04, 0.06), (0.08, 0.115, 0.06), boot, seg=14, ring=7)
            sph(f"Sole_{side}", (s * 0.095, -0.04, 0.022), (0.083, 0.118, 0.022), sole)

    return dict(backdrop="f2dcdc", pivots=adult_pivots(0.2, 0.64, 0.09, 0.32, 0.9 - 0.21),
                target=(0, 0, 0.6), dist=2.6, kind="aggressive person")


# ====================================================================== runner
CHARS = {"survivor": survivor, "mechanic": mechanic, "trader": trader, "raider": raider}


def build(name, budget=5000):
    fast = "--fast" in sys.argv
    concept = os.path.join(ROOT, "concepts", f"npc_{name}.png")
    portrait = os.path.join(ROOT, "assets", "portraits", f"npc_{name}.png")
    # 1) full-detail build for the concept art + menu portrait
    if not fast:
        npc_kit.DETAIL[0] = 1.0
        opts = CHARS[name]()
        finalize()
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        cam_at(opts["target"], opts["dist"], opts.get("yaw", 32), opts.get("pitch", 14))
        render(concept, 1024, samples=96)
        downscale(concept, portrait, 320)
    # 2) game build: lower detail until it fits the triangle budget
    npc_kit.DETAIL[0] = 1.0
    for attempt in range(5):
        opts = CHARS[name]()
        finalize()
        total = sum(tri_report().values())
        print(f"BUDGET {name} detail={npc_kit.DETAIL[0]:.2f} tris={total}")
        if total <= opts.get("budget", budget):
            break
        if npc_kit.DETAIL[0] <= 0.5:
            print(f"WARNING {name} over budget at the detail floor")
            break
        npc_kit.DETAIL[0] = max(0.5, npc_kit.DETAIL[0] * (opts.get("budget", budget) / total) ** 1.2 * 0.97)
    bake_transforms()
    tris = tri_report()
    lo, hi = height()
    mn, mx = extents()
    print(f"TRIS {name} total={sum(tris.values())} per={tris}")
    print(f"SIZE {name} height={hi - lo:.3f} (z {lo:.3f}..{hi:.3f}) x {mn.x:.3f}..{mx.x:.3f} y {mn.y:.3f}..{mx.y:.3f}")
    studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
    tgt, dist = opts["target"], opts["dist"]
    if SCRATCH:
        views = []
        for k, (yaw, pitch) in enumerate([(0, 8), (32, 14), (90, 8), (160, 12), (-40, 30)]):
            cam_at(tgt, dist, yaw, pitch)
            pth = os.path.join(SCRATCH, f"{name}_v{k}.png")
            render(pth, 420, samples=24)
            views.append(pth)
        # tiny in-game-ish view, blown up, to judge readability
        cam_at(tgt, dist, 25, 35)
        small = os.path.join(SCRATCH, f"{name}_small.png")
        render(small, 72, samples=16)
        views.append(small)
        contact_sheet(views, os.path.join(SCRATCH, f"{name}_sheet.png"), cols=3, cell=420)
        cam_at(tgt, dist * 0.75, 32, 14)
        render(os.path.join(SCRATCH, f"{name}_game.png"), 900, samples=48)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "art", "characters", f"npc_{name}.blend"), compress=True)
    export(name, opts["pivots"])
    print("KIND", name, opts["kind"])


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    names = [a for a in args if not a.startswith("--")]
    if names == ["all"]:
        names = list(CHARS)
    for n in names:
        build(n)
