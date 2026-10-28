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
        shc, shr = (0, 0.02, 0.735), (0.243, 0.222, 0.2)
        blob("Hair", shc, shr, hair, [((0, 0.9, 0.2), 0.02, 0.5), ((0, -1, 0.35), 0.02, 0.3)], seg=26, ring=14)
        # soft clumps swept up and to the right, a fringe flick over the brow
        clumps = [((-0.05, -0.75, 0.6), 0.07, 0.1, 0.9), ((-0.35, -0.35, 0.9), 0.065, 0.1, 0.6),
                  ((0.15, -0.3, 1.0), 0.075, 0.115, 0.7), ((0.5, -0.1, 0.85), 0.06, 0.09, 0.6),
                  ((-0.2, 0.25, 1.0), 0.07, 0.105, 0.4), ((0.25, 0.4, 0.9), 0.068, 0.1, 0.4),
                  ((-0.6, 0.3, 0.6), 0.055, 0.08, 0.3), ((0.0, 0.75, 0.6), 0.065, 0.085, 0.2)]
        for i, (d, w, ln, fwd) in enumerate(clumps):
            p, n = on(shc, shr, d, -0.02)
            dirv = (n + Vector((0.55, -0.25 * fwd, 0.15))).normalized()
            sph(f"Hair_Clump{i}", p + dirv * ln * 0.45, (w, w * 0.7, ln), hair, rot=aim(dirv, 0.4 * i), seg=12, ring=7)

        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.232, 0.01, 0.68), (0.035, 0.028, 0.048), skin)
            eye(f"Eye_{side}", hc, hr, (s * 0.37, -1, -0.12), 0.036, 0.05, black, white, shine2=False)
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
        cyl_between("Goggle_Bridge", on(hc, hr, (-0.12, -1, 0.52), 0.02)[0], on(hc, hr, (0.12, -1, 0.52), 0.02)[0],
                    0.01, brass)

    with limb("Body"):
        sph("Torso", (0, 0, 0.385), (0.16, 0.132, 0.17), hood, seg=20, ring=10, hero=True)
        sph("Hood", (0, 0.085, 0.51), (0.135, 0.075, 0.06), hood2)
        decal("Pocket", (0, 0, 0.385), (0.16, 0.132, 0.17), (0, -1, -0.45), (0.1, 0.03, 0.055), hood2, sink=0.75)
        p, n = on((0, 0, 0.385), (0.16, 0.132, 0.17), (-0.45, -1, 0.15), 0.0)
        box("Patch", p + n * 0.002, (0.05, 0.012, 0.045), patch, bevel=0.005, rot=facing(n))
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
            sph(f"Boot_{side}", (s * 0.074, -0.028, 0.058), (0.064, 0.094, 0.06), boot, seg=14, ring=7)
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
    hair = mat("Hair", "3a2a22", rough=0.55, coat=0.15)
    shirt = mat("Shirt", "4a5a78", rough=0.5, coat=0.25)
    over = mat("Overalls", "ee7d2c", rough=0.48, coat=0.3)
    over2 = mat("OverallsDark", "c45f1c", rough=0.5, coat=0.25)
    cap = mat("Cap", "27a69b")
    boot = mat("Boot", "4a3b33", rough=0.4, coat=0.4)
    sole = mat("Sole", "1e1a19", rough=0.6, coat=0.1)
    steel = mat("Steel", "c9ced6", rough=0.18, metal=1.0, coat=0.0)
    brass = mat("Brass", "d9a441", rough=0.25, metal=0.8, coat=0.3)
    rag = mat("Rag", "f2f0e6", rough=0.6, coat=0.1)
    grease = mat("Grease", "5a4c50", rough=0.7, coat=0.0)
    mouth = mat("Mouth", "5a2218", rough=0.4)
    tooth = mat("Tooth", "fffdf6", rough=0.25, coat=0.7)
    blush = mat("Blush", "e0806a", rough=0.6, coat=0.0)
    pencil = mat("Pencil", "ffcc33", rough=0.4)
    grip = mat("Grip", "e23b3b", rough=0.4, coat=0.4)

    with limb("Head"):
        hc, hr = (0, 0, 0.91), (0.235, 0.215, 0.212)
        sph("Head", hc, hr, skin, seg=24, ring=12, hero=True)
        # teal cap on backwards, brim over the neck, a gear badge on the front
        cc, cr = (0, 0.012, 0.965), (0.243, 0.227, 0.198)
        hsph("Cap", cc, cr, cap, seg=24, ring=12, hero=True)
        sph("Cap_Brim", (0, 0.215, 0.975), (0.15, 0.13, 0.016), cap, rot=Quaternion((1, 0, 0), math.radians(14)))
        sph("Cap_Button", (0, 0.012, 1.162), (0.024, 0.024, 0.014), cap)
        p, n = on(cc, cr, (0, -1, 0.42), 0.003)
        torus("Cap_Gear", p, 0.034, 0.01, white, rot=aim(n), seg=12)
        for k in range(6):
            a = k * math.pi / 3
            q = aim(n)
            sph(f"Cap_GearTooth{k}", p + q @ Vector((math.cos(a) * 0.047, math.sin(a) * 0.047, 0)),
                (0.011, 0.011, 0.007), white, rot=q)
        # short hair poking out under the cap at the sides and back
        blob("Hair", (0, 0.004, 0.912), (0.241, 0.221, 0.217), hair, [((0, 1, -0.2), 0.012, 0.6)], seg=28, ring=14,
             hero=False, keep=lambda d: d.z > -0.3 + 0.25 * max(0.0, -d.y) and d.y > -0.42)
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.232, 0.01, 0.895), (0.036, 0.029, 0.05), skin)
            eye(f"Eye_{side}", hc, hr, (s * 0.34, -1, -0.02), 0.033, 0.045, black, white)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.2, -1, 0.19), (s * 0.34, -1, 0.23), (s * 0.5, -1, 0.19)],
                                         lift=0.004), hair, r=0.013, radii=[0.8, 1, 0.7], caps=False)
            decal(f"Blush_{side}", hc, hr, (s * 0.6, -1, -0.27), (0.034, 0.008, 0.02), blush)
        p, n = on(hc, hr, (0, -1, -0.15), 0.014)
        sph("Nose", p, (0.04, 0.034, 0.033), skin)
        # big open D-shaped grin with a row of top teeth
        p, n = on(hc, hr, (0, -1, -0.4), 0.0)
        q = facing(n)
        hsph("Smile_Mouth", p - n * 0.004, (0.072, 0.014, 0.05), mouth, rot=q @ Quaternion((0, 1, 0), math.pi),
             seg=16, ring=8)
        p2, n2 = on(hc, hr, (0, -1, -0.415), 0.0)
        sph("Smile_Teeth", p2 + n2 * 0.003, (0.056, 0.01, 0.014), tooth, rot=facing(n2))
        decal("Grease", hc, hr, (-0.58, -1, -0.12), (0.03, 0.006, 0.016), grease)
        cyl("Pencil", (0.212, 0.05, 0.96), 0.008, 0.11, pencil, rot=aim((0.15, 1, -0.35)))

    with limb("Body"):
        tc, tr = (0, 0, 0.52), (0.2, 0.162, 0.2)
        sph("Torso", tc, tr, shirt, seg=20, ring=10, hero=True)
        sph("Pants", (0, 0, 0.38), (0.195, 0.158, 0.12), over, seg=20, ring=10)
        blob("Bib", tc, (0.206, 0.168, 0.206), over, (), seg=24, ring=12, hero=False,
             keep=lambda d: d.y < -0.1 and abs(d.x) < 0.72 and d.z < 0.62)
        decal("Bib_Pocket", tc, tr, (0, -1, 0.1), (0.065, 0.02, 0.05), over2, sink=-0.25)
        cyl("Bib_Screwdriver", (0.035, -0.172, 0.585), 0.012, 0.06, grip, seg=8)
        for s, side in sides():
            p, n = on(tc, tr, (s * 0.42, -1, 0.5), 0.01)
            sph(f"Button_{side}", p, (0.018, 0.012, 0.018), brass, rot=facing(n))
            tube(f"Strap_{side}", [tuple(p), (s * 0.1, -0.12, 0.69), (s * 0.11, 0.0, 0.728), (s * 0.1, 0.14, 0.64),
                                   (s * 0.08, 0.16, 0.5)], over, r=0.018, caps=False)
        # tool pouch on the hip, a rag in the back pocket
        box("Pouch", (-0.17, -0.07, 0.38), (0.06, 0.09, 0.1), over2, bevel=0.015, rot=(0, 0, 0.35))
        sph("Rag", (0.09, 0.16, 0.35), (0.045, 0.02, 0.07), rag, rot=Quaternion((0, 1, 0), 0.25))
        decal("Pants_Smudge", (0, 0, 0.38), (0.195, 0.158, 0.12), (0.5, -1, -0.1), (0.03, 0.006, 0.02), grease)

    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Sleeve_{side}", (s * 0.205, 0, 0.635), (0.072, 0.068, 0.07), shirt)
            tube(f"Sleeve_{side}_Arm", [(s * 0.215, 0, 0.62), (s * 0.24, -0.012, 0.55)], shirt, r=0.047, caps=False)
            torus(f"Sleeve_{side}_Roll", (s * 0.242, -0.013, 0.545), 0.045, 0.017, shirt, rot=(0, s * 0.25, 0))
            tube(f"Arm_{side}", [(s * 0.24, -0.012, 0.56), (s * 0.255, -0.025, 0.48), (s * 0.262, -0.032, 0.44)],
                 skin, r=0.04, caps=False)
            sph(f"Hand_{side}", (s * 0.268, -0.036, 0.41), (0.053, 0.05, 0.058), skin, seg=12, ring=6)
            if s > 0:  # big shiny wrench
                wx, wy = 0.27, -0.058
                box("Wrench_Handle", (wx, wy, 0.37), (0.032, 0.016, 0.25), steel, bevel=0.007)
                torus("Wrench_Ring", (wx, wy, 0.515), 0.032, 0.012, steel, rot=(math.pi / 2, 0, 0), seg=12)
                sph("Wrench_Head", (wx, wy, 0.23), (0.048, 0.015, 0.038), steel)
                for k in (-1, 1):
                    box(f"Wrench_Jaw{k}", (wx + k * 0.032, wy, 0.195), (0.024, 0.025, 0.058), steel, bevel=0.007,
                        rot=(0, k * 0.35, 0))
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.088, 0, 0.33), (s * 0.09, 0, 0.12)], over, r=0.064, caps=False)
            torus(f"Leg_{side}_Cuff", (s * 0.09, 0, 0.12), 0.062, 0.018, over2)
            sph(f"Boot_{side}", (s * 0.092, -0.035, 0.058), (0.077, 0.112, 0.058), boot, seg=14, ring=7)
            sph(f"Sole_{side}", (s * 0.092, -0.035, 0.022), (0.08, 0.115, 0.022), sole)
            box(f"Boot_{side}_Toecap", (s * 0.092, -0.115, 0.05), (0.07, 0.03, 0.04), sole, bevel=0.012)

    return dict(backdrop="dfe4ee", pivots=adult_pivots(0.205, 0.635, 0.088, 0.33, 0.91 - 0.212),
                target=(0, 0, 0.58), dist=2.5, kind="friendly person")


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
        blob("Bandana", bc, br, bandana, [((0, -1, -0.8), 0.045, 0.3, (0, 0, -0.035))], seg=28, ring=14,
             hero=False, keep=lambda d: d.y < 0.12 and d.z < -0.12 + 0.25 * max(0.0, d.y + 0.2))
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


# ====================================================================== 5. Mutant rat
def mutant_rat():
    reset("MutantRat")
    black, white = common_mats()
    fur = mat("Fur", "8f87a6", rough=0.5, coat=0.25)
    fur2 = mat("FurDark", "6a6283", rough=0.5, coat=0.25)
    belly = mat("Belly", "e6d6dc", rough=0.5, coat=0.2)
    pink = mat("Pink", "f5a3b4", rough=0.4, coat=0.3, sss=0.1)
    pink2 = mat("PinkDark", "dc7d93", rough=0.4, coat=0.3)
    nose = mat("Nose", "ff5f8c", rough=0.25, coat=0.7)
    tooth = mat("Tooth", "fff4d6", rough=0.25, coat=0.7)
    toxic = mat("Toxic", "8dff4a", rough=0.3, coat=0.3, emit="6dff2a", emit_strength=2.5)
    eyey = mat("EyeYellow", "ffe14d", rough=0.1, coat=1.0)
    mouth = mat("Mouth", "4a1a26", rough=0.4)
    bandage = mat("Bandage", "f3ead8", rough=0.6)
    whisk = mat("Whisker", "f2eefa", rough=0.4)

    with limb("Body"):
        bc, br = (0, 0.07, 0.3), (0.205, 0.29, 0.19)
        bumps = [((0, 0.6, 0.8), 0.05, 0.5), ((0, -0.2, 1), 0.035, 0.45),       # hunched back
                 ((0, -0.95, -0.1), 0.03, 0.5)]                                  # chest
        for k, a in enumerate((-30, 0, 30, 60)):                                  # scruffy spine tufts
            r = math.radians(a)
            bumps.append(((0.12 * (-1) ** k, math.sin(r), math.cos(r)), 0.03, 0.14, (0, 0.02, 0)))
        blob("Body", bc, br, fur, bumps, seg=32, ring=16)
        decal("Belly", bc, br, (0, -0.55, -1), (0.15, 0.06, 0.2), belly, sink=0.75, seg=14, ring=7)
        for k, (d, sz) in enumerate([((0.75, 0.3, 0.55), 0.07), ((-0.65, 0.5, 0.55), 0.055), ((0.2, 0.8, 0.6), 0.045),
                                     ((-0.3, -0.1, 1), 0.04)]):
            decal(f"Toxic_{k}", bc, br, d, (sz, 0.012, sz * 0.8), toxic, sink=0.3)
        decal("Scar", bc, br, (-0.85, -0.1, 0.4), (0.04, 0.008, 0.008), pink2, sink=0.2)

    with limb("Head"):
        hc, hr = (0, -0.27, 0.42), (0.15, 0.15, 0.135)
        blob("Head", hc, hr, fur, [((0, 0.3, 1), 0.025, 0.35), ((-0.9, 0.2, -0.3), 0.025, 0.4),
                                   ((0.9, 0.2, -0.3), 0.025, 0.4)], seg=24, ring=12)
        sc, sr = (0, -0.4, 0.385), (0.08, 0.11, 0.07)
        sph("Snout", sc, sr, fur, seg=16, ring=8)
        sph("Nose", (0, -0.507, 0.405), (0.034, 0.028, 0.028), nose)
        sph("Nose_Shine", (-0.01, -0.53, 0.418), (0.008, 0.005, 0.006), white)
        for s in (-1, 1):  # goofy buck teeth
            box(f"Tooth{s}", (s * 0.017, -0.492, 0.33), (0.031, 0.014, 0.056), tooth, bevel=0.007)
        for s, side in sides():
            for k, (dz, ang) in enumerate([(0.01, 0.25), (-0.012, -0.05)]):
                p0 = Vector((s * 0.055, -0.46, 0.39 + dz))
                tube(f"Whisker_{side}{k}", [p0, p0 + Vector((s * 0.09, 0.02, ang * 0.08)),
                                            p0 + Vector((s * 0.17, 0.05, ang * 0.2))], whisk, r=0.0035, caps=False,
                     radii=[1, 0.8, 0.5])
            # big round ears, the right one bent over
            tilt = Quaternion((0, 0, 1), -s * 0.35) @ Quaternion((1, 0, 0), -0.2)
            if s > 0:
                tilt = tilt @ Quaternion((0, 1, 0), 0.5)
            ec = Vector((s * 0.12, -0.22, 0.54))
            sph(f"Ear_{side}", ec, (0.085, 0.026, 0.085), fur, rot=tilt, seg=16, ring=8)
            sph(f"Ear_{side}_Inner", ec + tilt @ Vector((0, -0.012, -0.004)), (0.062, 0.016, 0.062), pink, rot=tilt)
        # mismatched mutant eyes (one big, one small) with grumpy brows
        for s, side, w in ((-1, "L", 0.05), (1, "R", 0.036)):
            p, n = on(hc, hr, (s * 0.42, -1, 0.28), 0.0)
            q = facing(n)
            sph(f"Eye_{side}", p - n * 0.008, (w, 0.022, w * 1.05), eyey, rot=q)
            sph(f"Eye_{side}_Pupil", p + n * 0.01 + q @ Vector((-s * 0.006, 0, -0.004)), (w * 0.42, 0.01, w * 0.55),
                black, rot=q)
            sph(f"Eye_{side}_Shine", p + n * 0.017 + q @ Vector((-0.008, 0, w * 0.35)), (w * 0.17, 0.005, w * 0.17),
                white, rot=q)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.2, -1, 0.55 - 0.05), (s * 0.45, -1, 0.62), (s * 0.68, -1, 0.5)],
                                         lift=0.008), fur2, r=0.013, radii=[1.1, 1, 0.6], caps=False)
        decal("Head_Toxic", hc, hr, (0.3, 0.2, 1), (0.03, 0.008, 0.026), toxic, sink=0.3)

    with limb("Jaw"):
        sph("Jaw", (0, -0.415, 0.325), (0.062, 0.08, 0.026), pink2, seg=14, ring=7)
        decal("Jaw_Mouth", (0, -0.42, 0.33), (0.065, 0.085, 0.028), (0, -0.4, 1), (0.045, 0.01, 0.05), mouth, sink=0.3)

    for s, side in sides():
        with limb("Leg" + side):  # front legs
            tube(f"Leg_{side}", [(s * 0.11, -0.14, 0.22), (s * 0.12, -0.16, 0.12), (s * 0.125, -0.18, 0.05)], fur,
                 r=0.045, radii=[1.2, 0.9, 0.75])
            sph(f"Paw_{side}", (s * 0.127, -0.205, 0.028), (0.048, 0.06, 0.03), pink)
            for t in (-1, 0, 1):
                sph(f"Toe_{side}{t}", (s * 0.127 + t * 0.025, -0.258, 0.024), (0.014, 0.016, 0.014), pink)
        with limb("Leg" + side + "2"):  # back legs: big haunches, long feet
            sph(f"Haunch_{side}", (s * 0.15, 0.2, 0.21), (0.08, 0.12, 0.11), fur, seg=16, ring=8)
            tube(f"Shin_{side}", [(s * 0.16, 0.24, 0.15), (s * 0.16, 0.22, 0.05)], fur, r=0.035, caps=False)
            sph(f"Foot_{side}", (s * 0.16, 0.17, 0.025), (0.048, 0.1, 0.026), pink)
            for t in (-1, 0, 1):
                sph(f"Toe2_{side}{t}", (s * 0.16 + t * 0.025, 0.075, 0.022), (0.014, 0.016, 0.013), pink)

    with limb("Tail"):
        pts = [(0, 0.33, 0.24), (0, 0.5, 0.19), (0.07, 0.66, 0.2), (0.17, 0.75, 0.28), (0.21, 0.77, 0.39)]
        tube("Tail", pts, pink, r=0.032, radii=[1, 0.78, 0.58, 0.42, 0.28], res=4, br=2)
        for k, (p, rr) in enumerate([((0, 0.42, 0.21), 0.027), ((0.02, 0.58, 0.19), 0.022)]):
            torus(f"Tail_Ring{k}", p, rr, 0.006, pink2, rot=aim((0, 1, -0.15)), seg=12, mseg=4)
        torus("Tail_Bandage", (0.14, 0.73, 0.255), 0.016, 0.009, bandage, rot=aim((0.7, 0.5, 0.5)), seg=12, mseg=5)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.17, 0.38), "Jaw": (0, -0.36, 0.345),
              "LegL": (-0.11, -0.14, 0.22), "LegR": (0.11, -0.14, 0.22),
              "LegL2": (-0.15, 0.2, 0.24), "LegR2": (0.15, 0.2, 0.24), "Tail": (0, 0.32, 0.25)}
    return dict(backdrop="e4e9d5", pivots=pivots, parents={"Jaw": "Head"}, target=(0, 0.1, 0.3), dist=2.2,
                yaw=40, kind="aggressive creature")


# ====================================================================== 6. Slime
def slime():
    reset("Slime")
    black, white = common_mats()
    goo = mat("Goo", "7fe04f", rough=0.06, coat=1.0, emit="49c22a", emit_strength=0.35, sss=0.25)
    goo2 = mat("GooDeep", "52c23d", rough=0.08, coat=1.0, emit="2f9e22", emit_strength=0.2)
    shine = mat("GooShine", "f2fff0", rough=0.1, coat=0.0, emit="ffffff", emit_strength=0.9)
    mouth = mat("Mouth", "1f4a1a", rough=0.3, coat=0.5)
    tongue = mat("Tongue", "ff7b9a", rough=0.35, coat=0.5)
    steel = mat("Steel", "b9c0c8", rough=0.25, metal=0.9, coat=0.2)
    cap = mat("BottleCap", "e83a3a", rough=0.3, metal=0.4, coat=0.5)
    eyew = mat("EyeWhite", "fbfbf6", rough=0.12, coat=0.9)

    with limb("Body"):
        # squashed goo dome; its centre is set so the flattened bottom sits on the ground
        sq = -0.5
        rz = 0.22
        cz = -rz * (sq + (-1 - sq) * 0.35)
        bc, br = (0, 0, cz), (0.3, 0.27, rz)
        bumps = [((0, 0, 1), 0.04, 0.6)]
        for k in range(7):  # drips sagging round the bottom edge
            a = 2 * math.pi * k / 7 + 0.3
            bumps.append(((math.cos(a), math.sin(a), -0.35), 0.022 + 0.01 * (k % 2), 0.22, (0, 0, -0.012)))
        blob("Body", bc, br, goo, bumps, seg=30, ring=16, squash_below=sq)
        sph("Puddle", (0, 0.0, 0.01), (0.33, 0.3, 0.014), goo2, seg=24, ring=6)
        # face: big googly eyes looking two ways and a goofy D grin with a tongue
        for s, side, look in ((-1, "L", (-0.25, 0.3)), (1, "R", (0.35, -0.1))):
            p, n = on(bc, br, (s * 0.36, -1, 0.42), -0.012)
            q = facing(n)
            sph(f"Eye_{side}", p, (0.07, 0.035, 0.078), eyew, rot=q, seg=20, ring=10)
            # cross little brows: a goo ridge slanting down to the middle
            tube(f"Brow_{side}", arc_on(bc, br, [(s * 0.18, -1, 0.66), (s * 0.36, -1, 0.74), (s * 0.54, -1, 0.75)],
                                         lift=0.004), goo2, r=0.016, radii=[1.1, 1, 0.7])
            sv, uv = q @ Vector((1, 0, 0)), q @ Vector((0, 0, 1))
            pp = p + n * 0.03 + sv * look[0] * 0.035 + uv * look[1] * 0.035
            sph(f"Eye_{side}_Pupil", pp, (0.03, 0.012, 0.034), black, rot=q)
            sph(f"Eye_{side}_Shine", pp + n * 0.008 + uv * 0.012 - sv * 0.01, (0.009, 0.004, 0.009), white, rot=q)
        p, n = on(bc, br, (0, -1, 0.05), 0.0)
        q = facing(n)
        hsph("Mouth", p - n * 0.006, (0.1, 0.02, 0.07), mouth, rot=q @ Quaternion((0, 1, 0), math.pi), seg=16, ring=8)
        sph("Tongue", p + n * 0.002 + Vector((0.02, 0, -0.045)), (0.04, 0.012, 0.025), tongue, rot=q)
        for k, (d, sz) in enumerate([((-0.45, -0.6, 0.85), (0.05, 0.01, 0.028)), ((-0.25, -0.75, 0.75), (0.016, 0.006, 0.016))]):
            decal(f"Shine_{k}", bc, br, d, sz, shine, sink=0.1)
        # junk stuck in the goo: a bolt and a bottle cap
        p, n = on(bc, br, (0.8, 0.3, 0.3), -0.02)
        cyl("Bolt_Head", p + n * 0.035, 0.028, 0.02, steel, rot=aim(n), seg=6, bevel=0.003)
        cyl("Bolt_Shank", p, 0.012, 0.06, steel, rot=aim(n), seg=8)
        p, n = on(bc, br, (-0.3, 0.6, 0.75), -0.006)
        cyl("BottleCap", p, 0.028, 0.012, cap, rot=aim(n + Vector((0.4, 0, 0))), seg=12, bevel=0.003)

    # Blob parts: soft lumps with their origin where they join the body, so scaling them squishes into it
    with limb("BlobTop"):
        sph("BlobTop", (0, 0.01, cz + rz + 0.035), (0.085, 0.08, 0.065), goo)
        sph("BlobTop_Curl", (0.03, 0.015, cz + rz + 0.1), (0.04, 0.038, 0.045), goo, rot=Quaternion((0, 1, 0), 0.5))
    for s, side in sides():
        with limb("Blob" + side):
            sph(f"Blob_{side}", (s * 0.29, -0.02, 0.1), (0.085, 0.075, 0.07), goo)
            sph(f"Blob_{side}_Drop", (s * 0.355, -0.04, 0.04), (0.04, 0.038, 0.035), goo)
    with limb("BlobBack"):
        sph("BlobBack", (0.03, 0.27, 0.12), (0.1, 0.075, 0.08), goo)

    pivots = {"Body": (0, 0, 0), "BlobTop": (0, 0.01, cz + rz - 0.01),
              "BlobL": (-0.24, -0.02, 0.11), "BlobR": (0.24, -0.02, 0.11), "BlobBack": (0.02, 0.21, 0.12)}
    return dict(backdrop="e2f0e6", pivots=pivots, target=(0, 0, 0.22), dist=1.75, yaw=28, kind="aggressive creature")


# ====================================================================== 7. Scrap robot
def scrap_robot():
    reset("ScrapRobot")
    black, white = common_mats()
    rust = mat("Rust", "c4622d", rough=0.55, coat=0.15, metal=0.3)
    rust2 = mat("RustDark", "8a3b1f", rough=0.65, coat=0.1, metal=0.2)
    teal = mat("TVPaint", "5aa39b", rough=0.4, coat=0.35)
    teal2 = mat("TVPaintChipped", "c9b79a", rough=0.6, coat=0.1)
    steel = mat("Steel", "a7afb8", rough=0.3, metal=0.9, coat=0.2)
    dark = mat("DarkMetal", "474c55", rough=0.4, metal=0.7, coat=0.2)
    chrome = mat("Chrome", "dfe4ea", rough=0.12, metal=1.0, coat=0.3)
    screen = mat("Screen", "141b29", rough=0.06, coat=1.0)
    red = mat("RedGlow", "ff4030", rough=0.2, coat=0.3, emit="ff3020", emit_strength=6)
    yel = mat("YellowGlow", "ffd23a", rough=0.2, coat=0.3, emit="ffc21a", emit_strength=4)
    hazard = mat("Hazard", "f2c230", rough=0.4, coat=0.4)
    stripe = mat("HazardStripe", "1d1d22", rough=0.4, coat=0.4)
    rubber = mat("Rubber", "343033", rough=0.6, coat=0.1)
    can = mat("PaintCan", "3d7fd1", rough=0.3, metal=0.5, coat=0.4)
    label = mat("CanLabel", "f4f1e6", rough=0.5, coat=0.2)
    glove = mat("Glove", "e2342c", rough=0.3, coat=0.6)
    tape = mat("Tape", "d8cfb6", rough=0.6, coat=0.1)

    with limb("Body"):
        cyl("Drum", (0, 0, 0.52), 0.2, 0.38, rust, seg=22, bevel=0.02)
        for k, z in enumerate((0.41, 0.63)):
            torus(f"Drum_Rib{k}", (0, 0, z), 0.2, 0.014, rust2, seg=22)
        cyl("Drum_Lid", (0, 0, 0.715), 0.185, 0.025, dark, seg=20)
        dc, dr = (0, 0, 0.52), (0.2, 0.2, 0.25)
        for k, (d, sz) in enumerate([((0.7, -0.7, 0.3), 0.05), ((-0.8, -0.3, -0.5), 0.04), ((-0.3, 0.9, 0.4), 0.06),
                                     ((0.9, 0.3, -0.6), 0.035)]):
            decal(f"Rust_{k}", dc, dr, d, (sz, 0.008, sz * 0.8), rust2, sink=0.2)
        box("Hazard", (0, -0.197, 0.525), (0.15, 0.014, 0.09), hazard, bevel=0.006)
        for k in range(3):
            box(f"Hazard_Stripe{k}", (-0.05 + k * 0.05, -0.205, 0.525), (0.018, 0.006, 0.1), stripe, bevel=0.002,
                rot=(0, 0.6, 0))
        for k in range(5):  # rivets
            a = -math.pi / 2 + (k - 2) * 0.32
            sph(f"Rivet{k}", (0.2 * math.cos(a), 0.2 * math.sin(a), 0.68), (0.012, 0.012, 0.012), steel)
        cyl_between("Exhaust", (0.09, 0.19, 0.5), (0.11, 0.23, 0.86), 0.026, dark, seg=10)
        cyl("Exhaust_Cap", (0.112, 0.232, 0.87), 0.033, 0.03, steel, seg=10)
        box("Hips", (0, 0, 0.31), (0.25, 0.17, 0.07), dark, bevel=0.025)
        cyl("Neck", (0, 0, 0.745), 0.05, 0.06, dark, seg=12)

    with limb("Head"):
        hc = Vector((0, 0, 0.9))
        box("Head", hc, (0.33, 0.25, 0.24), teal, bevel=0.035)
        box("Head_Chip", (0.12, -0.11, 1.0), (0.05, 0.04, 0.03), teal2, bevel=0.01)
        box("Screen", (0, -0.12, 0.895), (0.25, 0.02, 0.18), screen, bevel=0.03)
        # one big angry red eye, one little yellow one, cross metal brows
        sph("Eye_L", (-0.06, -0.13, 0.9), (0.048, 0.012, 0.048), red)
        torus("Eye_L_Rim", (-0.06, -0.132, 0.9), 0.05, 0.008, chrome, rot=(math.pi / 2, 0, 0), seg=14)
        sph("Eye_R", (0.07, -0.13, 0.91), (0.026, 0.01, 0.026), yel)
        box("Brow_L", (-0.06, -0.135, 0.962), (0.1, 0.012, 0.02), chrome, bevel=0.004, rot=(0, -0.3, 0))
        box("Brow_R", (0.07, -0.135, 0.955), (0.07, 0.012, 0.018), chrome, bevel=0.004, rot=(0, 0.4, 0))
        for k in range(2):  # dials on the side
            cyl(f"Knob{k}", (0.168, -0.04 + k * 0.07, 0.86), 0.022, 0.02, dark, rot=(0, math.pi / 2, 0), seg=10)
        # bent rabbit-ear antenna
        for s in (-1, 1):
            top = Vector((s * 0.14, 0.05, 1.17 + (0.03 if s > 0 else 0)))
            cyl_between(f"Antenna{s}", (s * 0.04, 0.03, 1.01), top, 0.007, steel, seg=6)
            sph(f"Antenna{s}_Ball", top, (0.016, 0.016, 0.016), red if s < 0 else steel)
        sph("Antenna_Base", (0, 0.03, 1.02), (0.045, 0.035, 0.022), dark)
        for k, r in enumerate((0.6, -0.6)):  # a taped-up dent
            box(f"Tape{k}", (-0.12, -0.04, 1.022), (0.09, 0.022, 0.006), tape, bevel=0.002, rot=(0, 0, r))

    with limb("Jaw"):
        box("Jaw", (0, -0.08, 0.76), (0.22, 0.12, 0.045), steel, bevel=0.012)
        for k in range(4):
            cone(f"Jaw_Tooth{k}", (-0.06 + k * 0.04, -0.13, 0.78), (0, 0, 1), 0.016, 0.03, chrome, seg=6)

    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Shoulder_{side}", (s * 0.235, 0, 0.66), (0.055, 0.055, 0.055), dark)
            if s < 0:  # pipe arm with a pincer claw
                cyl_between("Arm_L", (-0.24, 0, 0.65), (-0.28, -0.02, 0.43), 0.028, steel, seg=10)
                sph("Arm_L_Elbow", (-0.255, -0.008, 0.55), (0.034, 0.034, 0.034), rust2)
                cyl("Arm_L_Wrist", (-0.282, -0.022, 0.42), 0.04, 0.035, dark, seg=12)
                for k in (-1, 1):
                    tube(f"Claw_{k}", [(-0.282 + k * 0.022, -0.025, 0.41), (-0.282 + k * 0.05, -0.03, 0.35),
                                       (-0.282 + k * 0.025, -0.035, 0.3)], chrome, r=0.012, radii=[1.2, 1, 0.6])
            else:  # accordion hose arm + a big red boxing glove, under a hubcap shoulder pad
                cyl("Hubcap", (0.25, 0, 0.705), 0.085, 0.03, chrome, rot=(0, 0.45, 0), seg=18)
                sph("Hubcap_Nut", (0.268, 0, 0.74), (0.025, 0.025, 0.012), dark, rot=Quaternion((0, 1, 0), 0.45))
                cyl_between("Hose_Core", (0.24, 0, 0.64), (0.278, -0.012, 0.46), 0.024, dark, seg=10)
                for k in range(6):
                    t = k / 5
                    torus(f"Hose{k}", (0.24 + 0.038 * t, -0.012 * t, 0.625 - 0.15 * t), 0.03, 0.015, rubber, seg=12,
                          mseg=5)
                sph("Glove", (0.285, -0.03, 0.4), (0.07, 0.07, 0.078), glove, seg=16, ring=8)
                sph("Glove_Thumb", (0.24, -0.075, 0.42), (0.03, 0.028, 0.04), glove)
                torus("Glove_Cuff", (0.28, -0.025, 0.47), 0.05, 0.016, label, seg=14)
        with limb("Leg" + side):
            if s < 0:  # pipe leg + rubber boot
                cyl_between("Leg_L", (-0.1, 0, 0.3), (-0.1, 0, 0.1), 0.035, steel, seg=10)
                sph("Leg_L_Knee", (-0.1, 0, 0.2), (0.042, 0.042, 0.04), rust2)
                sph("Boot_L", (-0.1, -0.035, 0.055), (0.075, 0.11, 0.058), rubber, seg=14, ring=7)
            else:  # spring leg + paint-can foot
                for k in range(5):
                    torus(f"Spring{k}", (0.1, 0, 0.29 - k * 0.035), 0.038, 0.009, chrome, rot=(0.15, 0, 0), seg=12,
                          mseg=4)
                cyl("PaintCan", (0.1, -0.01, 0.065), 0.068, 0.12, can, seg=16)
                cyl("PaintCan_Label", (0.1, -0.01, 0.06), 0.07, 0.05, label, seg=16, bevel=0.0)
                sph("PaintCan_Drip", (0.1, -0.075, 0.1), (0.018, 0.01, 0.03), white)

    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 0.76), "Jaw": (0, 0.0, 0.77),
              "ArmL": (-0.235, 0, 0.66), "ArmR": (0.235, 0, 0.66), "LegL": (-0.1, 0, 0.3), "LegR": (0.1, 0, 0.3)}
    return dict(backdrop="e9e2da", pivots=pivots, parents={"Jaw": "Head"}, target=(0, 0, 0.58), dist=2.5,
                kind="aggressive creature")


# ====================================================================== 8. Spider bot
def spider_bot():
    reset("SpiderBot")
    black, white = common_mats()
    hull = mat("Hull", "5d6878", rough=0.3, metal=0.6, coat=0.4)
    dark = mat("DarkMetal", "2e333b", rough=0.35, metal=0.6, coat=0.3)
    hazard = mat("Hazard", "f2c230", rough=0.35, coat=0.5)
    steel = mat("Steel", "a9b2bd", rough=0.25, metal=0.9, coat=0.2)
    joint = mat("Joint", "f2c230", rough=0.3, coat=0.5)
    red = mat("RedGlow", "ff3b30", rough=0.2, coat=0.3, emit="ff2a1a", emit_strength=6)
    rubber = mat("Rubber", "26262a", rough=0.6, coat=0.1)

    bcen = Vector((0, 0.03, 0.3))
    with limb("Body"):
        sph("Hull", bcen, (0.19, 0.22, 0.105), hull, seg=24, ring=12, hero=True)
        sph("Hull_Dome", bcen + Vector((0, -0.02, 0.06)), (0.14, 0.15, 0.075), dark, seg=18, ring=9)
        torus("Hull_Band", bcen, 0.19, 0.016, hazard, scale=(1, 1.16, 1), seg=24)
        ac, ar = Vector((0, 0.26, 0.33)), (0.15, 0.16, 0.125)
        sph("Abdomen", ac, ar, hull, seg=20, ring=10)
        for k, dy in enumerate((-0.05, 0.06)):
            f = math.sqrt(1 - (dy / ar[1]) ** 2)
            torus(f"Abdomen_Stripe{k}", ac + Vector((0, dy, 0)), ar[0] * f, 0.014, hazard, rot=(math.pi / 2, 0, 0),
                  scale=(1, ar[2] / ar[0], 1), seg=20)
        cyl("Beacon_Base", ac + Vector((0, 0.0, 0.125)), 0.028, 0.02, dark, seg=10)
        sph("Beacon", ac + Vector((0, 0.0, 0.15)), (0.025, 0.025, 0.025), red)
        for k in range(6):
            a = math.pi * (0.15 + 0.7 * k / 5)
            sph(f"Rivet{k}", bcen + Vector((0.13 * math.cos(a), -0.15 * math.sin(a), 0.075)), (0.01, 0.01, 0.008), steel)
        sph("Underside", bcen + Vector((0, 0, -0.05)), (0.15, 0.17, 0.05), dark)

    with limb("Head"):
        tc = Vector((0, -0.2, 0.31))
        sph("Head", tc, (0.11, 0.09, 0.08), dark, seg=18, ring=9)
        sph("Eye_Big", tc + Vector((0, -0.08, 0.008)), (0.045, 0.02, 0.045), red)
        torus("Eye_Big_Rim", tc + Vector((0, -0.084, 0.008)), 0.047, 0.009, steel, rot=(math.pi / 2, 0, 0), seg=16)
        sph("Eye_Big_Shine", tc + Vector((-0.015, -0.1, 0.025)), (0.01, 0.004, 0.01), white)
        for s in (-1, 1):
            for k, (dx, dz, r) in enumerate([(0.06, 0.04, 0.017), (0.075, -0.012, 0.012)]):
                sph(f"Eye_{s}{k}", tc + Vector((s * dx, -0.065, dz)), (r, r * 0.6, r), red)
            cone(f"Mandible{s}", tc + Vector((s * 0.035, -0.07, -0.045)), (s * 0.15, -0.6, -1), 0.016, 0.05, steel, seg=6)

    # eight legs, front to back; each origin at its hip ball on the hull
    for s, side in sides():
        for i, a in enumerate((-48, -16, 16, 46)):
            ar_ = math.radians(a)
            d = Vector((s * math.cos(ar_), math.sin(ar_), 0))
            hip = bcen + Vector((d.x * 0.17, d.y * 0.19, 0.0))
            knee = hip + d * 0.17 + Vector((0, 0, 0.15))
            foot = hip + d * 0.36 + Vector((0, 0, -0.282))
            with limb(f"Leg{side}{i + 1}"):
                sph(f"Leg{side}{i + 1}_Hip", hip, (0.036, 0.036, 0.036), joint)
                tube(f"Leg{side}{i + 1}_Femur", [hip, hip + d * 0.08 + Vector((0, 0, 0.12)), knee], steel, r=0.024,
                     caps=False)
                sph(f"Leg{side}{i + 1}_Knee", knee, (0.03, 0.03, 0.03), joint)
                tube(f"Leg{side}{i + 1}_Shin", [knee, knee + d * 0.12 + Vector((0, 0, -0.1)), foot], dark, r=0.024,
                     radii=[1, 0.75, 0.5], caps=False)
                sph(f"Leg{side}{i + 1}_Foot", foot, (0.02, 0.02, 0.018), rubber)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.14, 0.3)}
    for s, side in sides():
        for i, a in enumerate((-48, -16, 16, 46)):
            ar_ = math.radians(a)
            pivots[f"Leg{side}{i + 1}"] = (bcen.x + s * math.cos(ar_) * 0.17, bcen.y + math.sin(ar_) * 0.19, bcen.z)
    return dict(backdrop="e0e4ec", pivots=pivots, target=(0, 0.02, 0.22), dist=2.0, yaw=35, pitch=22,
                kind="aggressive creature")


# ====================================================================== 9. Dog
def dog():
    reset("Dog")
    black, white = common_mats()
    fur = mat("Fur", "d9a066", rough=0.5, coat=0.25)
    cream = mat("Cream", "f6e6c8", rough=0.5, coat=0.2)
    patch = mat("Patch", "6b4428", rough=0.5, coat=0.25)
    nose = mat("Nose", "1d1515", rough=0.1, coat=1.0)
    tongue = mat("Tongue", "ff7b8f", rough=0.35, coat=0.5)
    mouth = mat("Mouth", "4a2420", rough=0.4)
    bandana = mat("Bandana", "e23b3b", rough=0.5, coat=0.2)
    gold = mat("Tag", "f2c13a", rough=0.25, metal=0.8, coat=0.3)
    blush = mat("Blush", "ff9a8a", rough=0.6, coat=0.0)

    with limb("Body"):
        bc, br = (0, 0.06, 0.29), (0.145, 0.22, 0.14)
        bumps = [((0, -1, -0.2), 0.04, 0.45), ((0.3, -0.9, -0.6), 0.03, 0.3), ((-0.3, -0.9, -0.6), 0.03, 0.3)]
        for k, a in enumerate((10, 40, 70, 100, 130)):                                # scruffy back
            r = math.radians(a)
            bumps.append(((0.2 * (-1) ** k, -math.cos(r), math.sin(r)), 0.028, 0.17, (0, 0.015, 0)))
        blob("Body", bc, br, fur, bumps, seg=30, ring=16)
        decal("Belly", bc, br, (0, -0.4, -1), (0.09, 0.05, 0.16), cream, sink=0.75, seg=14, ring=7)
        decal("Back_Patch", bc, br, (0.5, 0.35, 0.8), (0.08, 0.02, 0.07), patch, sink=0.5, seg=14, ring=7)
        torus("Bandana_Knot", (0, -0.1, 0.41), 0.08, 0.026, bandana, rot=(-0.7, 0, 0), scale=(1.05, 1, 1))
        cone("Bandana", (0, -0.165, 0.39), (0, -0.45, -1), 0.065, 0.1, bandana, flatten=0.35, seg=8)
        cyl("Tag", (0.02, -0.19, 0.33), 0.022, 0.008, gold, rot=(math.pi / 2, 0, 0), seg=12, bevel=0.002)

    with limb("Head"):
        hc, hr = (0, -0.2, 0.52), (0.135, 0.125, 0.12)
        blob("Head", hc, hr, fur, [((0.1, -0.4, 1), 0.035, 0.28, (0, -0.015, 0)), ((-0.3, 0.1, 1), 0.025, 0.25),
                                   ((-0.95, 0.1, -0.2), 0.025, 0.3), ((0.95, 0.1, -0.2), 0.025, 0.3)], seg=24, ring=12)
        mc, mr = (0, -0.31, 0.475), (0.078, 0.08, 0.06)
        sph("Muzzle", mc, mr, cream, seg=16, ring=8)
        sph("Nose", (0, -0.385, 0.505), (0.032, 0.022, 0.024), nose)
        sph("Nose_Shine", (-0.01, -0.403, 0.515), (0.008, 0.004, 0.006), white)
        tube("Smile", arc_on(mc, mr, [(t * 0.6, -1, -0.15 - 0.25 * (1 - t * t)) for t in (-1, -0.5, 0, 0.5, 1)]),
             mouth, r=0.006)
        sph("Tongue", (0.018, -0.365, 0.43), (0.026, 0.012, 0.036), tongue, rot=Quaternion((0, 1, 0), -0.2))
        decal("Eye_Patch", hc, hr, (0.42, -1, 0.2), (0.058, 0.012, 0.056), patch, sink=0.4)
        for s, side in sides():
            eye(f"Eye_{side}", hc, hr, (s * 0.4, -1, 0.18), 0.03, 0.036, black, white)
            decal(f"Blush_{side}", hc, hr, (s * 0.62, -1, -0.15), (0.026, 0.007, 0.016), blush)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.25, -1, 0.5), (s * 0.4, -1, 0.56), (s * 0.55, -1, 0.5)], lift=0.006),
                 patch if s > 0 else fur, r=0.011, caps=False)
        # one ear perked up, one flopped over
        cone("Ear_L", (-0.085, -0.18, 0.61), (-0.35, 0.1, 1), 0.05, 0.11, fur, flatten=0.45, seg=10)
        cone("Ear_L_Inner", (-0.085, -0.192, 0.615), (-0.35, 0.1, 1), 0.032, 0.08, cream, flatten=0.3, seg=8)
        sph("Ear_R", (0.13, -0.17, 0.55), (0.034, 0.026, 0.075), patch, rot=Quaternion((0, 1, 0), 0.55) @
            Quaternion((1, 0, 0), 0.2))

    for s, side in sides():
        with limb("Leg" + side):  # front legs
            tube(f"Leg_{side}", [(s * 0.075, -0.1, 0.24), (s * 0.078, -0.11, 0.06)], fur, r=0.043, caps=False,
                 radii=[1.1, 0.9])
            sph(f"Paw_{side}", (s * 0.079, -0.128, 0.034), (0.048, 0.06, 0.034), cream)
        with limb("Leg" + side + "2"):  # back legs
            sph(f"Thigh_{side}", (s * 0.09, 0.19, 0.23), (0.065, 0.095, 0.09), fur)
            tube(f"Shin_{side}", [(s * 0.092, 0.21, 0.17), (s * 0.092, 0.21, 0.06)], fur, r=0.04, caps=False)
            sph(f"Paw2_{side}", (s * 0.092, 0.192, 0.034), (0.048, 0.062, 0.034), cream if s < 0 else fur)

    with limb("Tail"):
        tube("Tail", [(0, 0.26, 0.34), (0, 0.33, 0.42), (0.02, 0.36, 0.52)], fur, r=0.03, radii=[1, 0.9, 0.7])
        sph("Tail_Tuft", (0.022, 0.365, 0.55), (0.032, 0.03, 0.045), cream)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.14, 0.43),
              "LegL": (-0.075, -0.1, 0.24), "LegR": (0.075, -0.1, 0.24),
              "LegL2": (-0.085, 0.2, 0.26), "LegR2": (0.085, 0.2, 0.26), "Tail": (0, 0.26, 0.34)}
    return dict(backdrop="f3e6d2", pivots=pivots, target=(0, 0.02, 0.32), dist=2.0, yaw=38, kind="friendly creature")


# ====================================================================== runner
CHARS = {"survivor": survivor, "mechanic": mechanic, "trader": trader, "raider": raider,
         "mutant_rat": mutant_rat, "slime": slime, "scrap_robot": scrap_robot, "spider_bot": spider_bot, "dog": dog}


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
            cam_at(tgt, min(dist, 1.9) if k == 3 else dist, yaw, pitch, lens=48 if k == 3 else 60)
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
    export(name, opts["pivots"], opts.get("parents"))
    print("KIND", name, opts["kind"])


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    names = [a for a in args if not a.startswith("--")]
    if names == ["all"]:
        names = list(CHARS)
    for n in names:
        build(n)
