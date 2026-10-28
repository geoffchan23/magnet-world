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


# ====================================================================== runner
CHARS = {"survivor": survivor}


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
