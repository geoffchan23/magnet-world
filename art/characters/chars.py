import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import toykit
importlib.reload(toykit)
from toykit import *
from mathutils import Vector, Quaternion

OUT = "/Users/geoff/Desktop/Work/Personal/magnet-world"


def common_mats():
    return (mat("EyeBlack", "141821", rough=0.08, coat=1.0),
            mat("EyeShine", "ffffff", rough=0.2, coat=0.0, emit="ffffff", emit_strength=1.5))


# ------------------------------------------------------------------ 1. Kid
def kid():
    reset("Kid")
    black, white = common_mats()
    skin = mat("Skin", "f4c09a", rough=0.45, coat=0.25, sss=0.15)
    shirt = mat("Shirt", "2f8cff")
    shorts = mat("Shorts", "2b3d66", rough=0.5, coat=0.2)
    cap = mat("Cap", "ff4b3e")
    hair = mat("Hair", "6b3f22", rough=0.45)
    shoe = mat("Shoe", "ff8a2a")
    sole = mat("Sole", "fafafa", rough=0.5)
    pack = mat("Backpack", "ffd02e")
    pack2 = mat("BackpackPocket", "ff9f1c")
    blush = mat("Blush", "ff8c8c", rough=0.6, coat=0.0)
    mouth = mat("Mouth", "6a2a20", rough=0.4)

    hc, hr = (0, 0, 0.70), (0.235, 0.215, 0.215)
    sphere("Head", hc, hr, skin, seg=32, ring=16)
    # hair poking out under the cap
    for i, (x, y, z, s) in enumerate([(-0.19, 0.07, 0.70, 0.075), (0.19, 0.07, 0.70, 0.075),
                                       (-0.13, 0.15, 0.72, 0.085), (0.13, 0.15, 0.72, 0.085),
                                       (0.0, 0.18, 0.71, 0.09), (-0.2, -0.06, 0.735, 0.05), (0.2, -0.06, 0.735, 0.05),
                                       (-0.1, -0.17, 0.75, 0.045), (-0.045, -0.19, 0.745, 0.04)]):
        sphere(f"Hair_{i}", (x, y, z), (s, s, s * 0.9), hair, seg=16, ring=8)
    half_sphere("Cap", (0, 0.005, 0.735), (0.245, 0.232, 0.225), cap, keep_above=0.0, seg=32, ring=16)
    sphere("Cap_Brim", (0, -0.2, 0.745), (0.19, 0.15, 0.022), cap, seg=24, ring=8,
           rot=Quaternion((1, 0, 0), math.radians(-8)))
    sphere("Cap_Button", (0, 0.005, 0.958), (0.03, 0.03, 0.02), cap, seg=12, ring=6)
    for s in (-1, 1):
        sphere(f"Ear_{'L' if s < 0 else 'R'}", (s * 0.232, 0.01, 0.68), (0.035, 0.028, 0.048), skin, seg=12, ring=6)
        eye(f"Eye_{'L' if s < 0 else 'R'}", hc, hr, (s * 0.38, -1, -0.12), 0.034, 0.048, black, white)
        decal(f"Blush_{'L' if s < 0 else 'R'}", hc, hr, (s * 0.62, -1, -0.42), (0.034, 0.008, 0.02), blush)
    decal("Nose", hc, hr, (0, -1, -0.24), (0.02, 0.014, 0.016), skin, sink=0.2)
    tube("Smile", arc_on(hc, hr, [(t * 0.16, -1, -0.40 - 0.07 * (1 - t * t)) for t in (-1, -0.5, 0, 0.5, 1)]),
         mouth, radius=0.007)

    # body
    sphere("Torso", (0, 0, 0.385), (0.155, 0.128, 0.165), shirt, seg=24, ring=12)
    sphere("Shorts", (0, 0, 0.255), (0.148, 0.122, 0.085), shorts, seg=24, ring=12)
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        sphere(f"Sleeve_{side}", (s * 0.145, 0, 0.455), (0.058, 0.055, 0.055), shirt, seg=16, ring=8)
        tube(f"Arm_{side}", [(s * 0.17, -0.005, 0.44), (s * 0.205, -0.015, 0.37), (s * 0.215, -0.025, 0.31)], skin,
             radius=0.031)
        sphere(f"Hand_{side}", (s * 0.218, -0.028, 0.285), (0.042, 0.04, 0.046), skin, seg=16, ring=8)
        tube(f"Leg_{side}", [(s * 0.068, 0, 0.2), (s * 0.07, 0, 0.08)], skin, radius=0.04)
        sphere(f"Shoe_{side}", (s * 0.074, -0.03, 0.05), (0.062, 0.09, 0.045), shoe, seg=20, ring=10)
        sphere(f"Sole_{side}", (s * 0.074, -0.03, 0.018), (0.064, 0.092, 0.018), sole, seg=20, ring=8)
        # backpack straps
        tube(f"Strap_{side}", [(s * 0.075, 0.13, 0.49), (s * 0.078, 0.03, 0.545), (s * 0.08, -0.095, 0.5),
                               (s * 0.082, -0.125, 0.40)], pack, radius=0.014, caps=False)
    rbox("Backpack", (0, 0.165, 0.40), (0.22, 0.10, 0.23), pack, bevel=0.035)
    rbox("Backpack_Pocket", (0, 0.222, 0.355), (0.15, 0.04, 0.10), pack2, bevel=0.018)
    rbox("Backpack_Flap", (0, 0.2, 0.495), (0.2, 0.08, 0.05), pack2, bevel=0.02)
    return dict(backdrop="d6e8ff")


# ------------------------------------------------------------------ 2. Fox
def fox():
    reset("Fox")
    black, white = common_mats()
    fur = mat("Fur", "f27a2b", rough=0.4, coat=0.35)
    cream = mat("Cream", "fff1dc", rough=0.45, coat=0.3)
    dark = mat("DarkFur", "4a2b22", rough=0.45, coat=0.3)
    inner = mat("InnerEar", "ffb4a2", rough=0.5, coat=0.2)
    scarf = mat("Scarf", "22b8a6", rough=0.5, coat=0.2)
    nose = mat("Nose", "1d1515", rough=0.1, coat=1.0)
    blush = mat("Blush", "ff7f7f", rough=0.6, coat=0.0)

    hc, hr = (0, 0, 0.665), (0.24, 0.21, 0.195)
    sphere("Head", hc, hr, fur, seg=32, ring=16)
    mc, mr = (0, -0.165, 0.615), (0.115, 0.11, 0.08)
    sphere("Muzzle", mc, mr, cream, seg=24, ring=12)
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        sphere(f"Cheek_{side}", (s * 0.165, -0.06, 0.6), (0.105, 0.085, 0.085), cream, seg=20, ring=10)
        eye(f"Eye_{side}", hc, hr, (s * 0.42, -1, 0.06), 0.036, 0.046, black, white)
        decal(f"Blush_{side}", hc, hr, (s * 0.75, -1, -0.2), (0.03, 0.008, 0.018), blush)
        # ears: tall, flattened, tilted out, with pale insides
        base = Vector((s * 0.13, 0.01, 0.815))
        d = Vector((s * 0.42, 0.05, 1.0))
        cone(f"Ear_{side}", base, d, 0.085, 0.21, fur, flatten=0.5)
        cone(f"EarInner_{side}", base + Vector((0, -0.02, 0.015)), d, 0.055, 0.15, inner, flatten=0.35)
    sphere("Nose", (0, -0.272, 0.638), (0.032, 0.025, 0.024), nose, seg=16, ring=8)
    tube("Smile", arc_on(mc, mr, [(t * 0.45, -1, -0.45 - 0.2 * (1 - t * t)) for t in (-1, -0.5, 0, 0.5, 1)]),
         nose, radius=0.006)

    sphere("Body", (0, 0.01, 0.33), (0.155, 0.135, 0.175), fur, seg=24, ring=12)
    decal("Belly", (0, 0.01, 0.33), (0.155, 0.135, 0.175), (0, -1, -0.15), (0.1, 0.05, 0.12), cream, sink=0.7, seg=28, ring=14)
    torus("Scarf", (0, -0.005, 0.485), 0.12, 0.034, scarf, scale=(1.0, 0.92, 1.0))
    tube("Scarf_Tail", [(0.05, -0.12, 0.48), (0.08, -0.15, 0.42), (0.085, -0.14, 0.36)], scarf, radius=0.026,
         radii=[1, 1, 0.8])
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        tube(f"Arm_{side}", [(s * 0.13, 0, 0.42), (s * 0.19, -0.02, 0.35), (s * 0.2, -0.04, 0.29)], fur,
             radius=0.033)
        sphere(f"Paw_{side}", (s * 0.2, -0.045, 0.27), (0.04, 0.04, 0.042), dark, seg=16, ring=8)
        tube(f"Leg_{side}", [(s * 0.07, 0, 0.19), (s * 0.075, -0.005, 0.07)], dark, radius=0.042)
        sphere(f"Foot_{side}", (s * 0.078, -0.035, 0.04), (0.06, 0.085, 0.04), dark, seg=20, ring=10)
    # big fluffy tail with a cream tip
    tube("Tail", [(0, 0.12, 0.22), (0.03, 0.27, 0.22), (0.1, 0.38, 0.33), (0.13, 0.42, 0.5)], fur, radius=0.1,
         radii=[0.45, 0.9, 1.15, 1.0], caps=False, bevel_res=5)
    sphere("Tail_Tip", (0.135, 0.425, 0.53), (0.098, 0.098, 0.11), cream, seg=20, ring=10)
    return dict(backdrop="d4f3e4")


# ------------------------------------------------------------------ 3. Robot
def robot():
    reset("Robot")
    black, white = common_mats()
    shell = mat("Shell", "f4f6fa", rough=0.25, coat=0.8)
    blue = mat("Blue", "3d8bff", rough=0.28, coat=0.7)
    orange = mat("Orange", "ff8a3d", rough=0.3, coat=0.6)
    joint = mat("Joint", "5b6577", rough=0.35, coat=0.4)
    screen = mat("Screen", "141b29", rough=0.06, coat=1.0)
    glow = mat("Glow", "7ff5ff", rough=0.3, coat=0.0, emit="6ff2ff", emit_strength=6)
    red = mat("MagnetRed", "e8322f", rough=0.25, coat=0.8)
    steel = mat("Steel", "c9ced6", rough=0.18, metal=1.0, coat=0.0)
    bulb = mat("Bulb", "ffcf3a", rough=0.2, emit="ffc23a", emit_strength=4)

    rbox("Head", (0, 0, 0.71), (0.37, 0.3, 0.29), shell, bevel=0.07)
    rbox("Screen", (0, -0.142, 0.70), (0.29, 0.03, 0.2), screen, bevel=0.035)
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        sphere(f"Eye_{side}", (s * 0.065, -0.16, 0.725), (0.032, 0.012, 0.042), glow, seg=16, ring=8)
        cyl(f"EarBolt_{side}", (s * 0.19, 0, 0.71), 0.05, 0.04, orange,
            rot=Quaternion((0, 1, 0), math.radians(90)), bevel=0.008)
    tube("Smile", [(-0.045, -0.162, 0.66), (0, -0.165, 0.645), (0.045, -0.162, 0.66)], glow, radius=0.008)
    tube("Antenna", [(0, 0, 0.85), (0.01, 0, 0.92), (0.03, 0, 0.97)], joint, radius=0.012)
    sphere("Antenna_Bulb", (0.03, 0, 0.985), (0.035, 0.035, 0.035), bulb, seg=16, ring=8)
    cyl("Neck", (0, 0, 0.555), 0.06, 0.06, joint, bevel=0.0)

    rbox("Body", (0, 0, 0.385), (0.3, 0.23, 0.27), blue, bevel=0.06)
    rbox("ChestPanel", (0, -0.112, 0.4), (0.18, 0.03, 0.14), shell, bevel=0.025)
    for i, c in enumerate([red, bulb, glow]):
        sphere(f"Button_{i}", (-0.05 + i * 0.05, -0.13, 0.42), (0.02, 0.012, 0.02), c, seg=12, ring=6)
    rbox("Grill", (0, -0.13, 0.365), (0.12, 0.012, 0.025), joint, bevel=0.006, subsurf=0)
    rbox("Hips", (0, 0, 0.235), (0.22, 0.17, 0.06), joint, bevel=0.025)

    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        sphere(f"Shoulder_{side}", (s * 0.17, 0, 0.47), (0.05, 0.05, 0.05), orange, seg=16, ring=8)
        tube(f"Arm_{side}", [(s * 0.19, 0, 0.45), (s * 0.23, -0.01, 0.37), (s * 0.24, -0.02, 0.31)], joint,
             radius=0.022)
        tube(f"Leg_{side}", [(s * 0.07, 0, 0.21), (s * 0.07, 0, 0.08)], joint, radius=0.03)
        rbox(f"Foot_{side}", (s * 0.075, -0.025, 0.04), (0.11, 0.17, 0.08), orange, bevel=0.03)
    # right hand: a round mitten; left hand: the horseshoe magnet claw!
    sphere("Hand_R", (0.245, -0.025, 0.285), (0.042, 0.042, 0.042), shell, seg=16, ring=8)
    hx, hy, hz = -0.245, -0.03, 0.28
    u = [(hx - 0.05, hy, hz - 0.09), (hx - 0.05, hy, hz - 0.02), (hx, hy, hz + 0.03),
         (hx + 0.05, hy, hz - 0.02), (hx + 0.05, hy, hz - 0.09)]
    tube("Magnet", u, red, radius=0.026, caps=False)
    cyl("Magnet_TipL", (hx - 0.05, hy, hz - 0.105), 0.027, 0.04, steel, bevel=0.006)
    cyl("Magnet_TipR", (hx + 0.05, hy, hz - 0.105), 0.027, 0.04, steel, bevel=0.006)
    return dict(backdrop="e6e0ff")


# ------------------------------------------------------------------ 4. Dino
def dino():
    reset("Dino")
    black, white = common_mats()
    green = mat("Scales", "63c74d", rough=0.35, coat=0.5)
    belly = mat("Belly", "f6eeb4", rough=0.45, coat=0.3)
    spike = mat("Spikes", "ffae2b", rough=0.3, coat=0.5)
    blush = mat("Blush", "ff8c8c", rough=0.6, coat=0.0)
    mouth = mat("Mouth", "2a3b22", rough=0.4)
    tooth = mat("Tooth", "ffffff", rough=0.3)
    spots = mat("Spots", "4fa83c", rough=0.4, coat=0.4)

    hc, hr = (0, 0.0, 0.67), (0.225, 0.215, 0.2)
    sphere("Head", hc, hr, green, seg=32, ring=16)
    sc, sr = (0, -0.15, 0.6), (0.185, 0.14, 0.125)
    sphere("Snout", sc, sr, green, seg=28, ring=14)
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        eye(f"Eye_{side}", hc, hr, (s * 0.48, -1, 0.32), 0.04, 0.052, black, white)
        decal(f"Blush_{side}", sc, sr, (s * 0.85, -0.7, 0.05), (0.032, 0.008, 0.02), blush)
        decal(f"Nostril_{side}", sc, sr, (s * 0.25, -1, 0.45), (0.012, 0.008, 0.008), mouth)
    tube("Smile", arc_on(sc, sr, [(t * 0.7, -1, -0.05 - 0.22 * (1 - t * t)) for t in (-1, -0.5, 0, 0.5, 1)]),
         mouth, radius=0.007)
    for s in (-1, 1):
        p, n = surf(sc, sr, (s * 0.2, -1, -0.32))
        cone(f"Tooth_{'L' if s < 0 else 'R'}", p + n * 0.002, (0, 0, -1), 0.014, 0.024, tooth, seg=10, subsurf=1)

    bc, br = (0, 0.03, 0.3), (0.185, 0.175, 0.205)
    sphere("Body", bc, br, green, seg=24, ring=12)
    decal("Belly", bc, br, (0, -1, -0.15), (0.125, 0.06, 0.15), belly, sink=0.75, seg=28, ring=14)
    for i, (d, sz) in enumerate([((0.7, -0.2, 0.5), 0.03), ((-0.75, 0.2, 0.3), 0.035), ((0.6, 0.6, 0.1), 0.028)]):
        decal(f"Spot_{i}", bc, br, d, (sz, 0.008, sz * 0.8), spots)
    for i, (d, sz) in enumerate([((0.65, 0.35, 0.6), 0.026), ((-0.55, 0.2, 0.7), 0.022)]):
        decal(f"HeadSpot_{i}", hc, hr, d, (sz, 0.008, sz * 0.8), spots)
    # tail
    tail = [(0, 0.17, 0.24), (0, 0.32, 0.17), (0.07, 0.46, 0.1), (0.17, 0.52, 0.07)]
    tube("Tail", tail, green, radius=0.11, radii=[1.0, 0.68, 0.38, 0.1], caps=False, bevel_res=4)
    # back spikes along head, body and tail
    spikes = []
    for a in (5, 35, 65):
        spikes.append((hc, hr, (0, math.sin(math.radians(a)), math.cos(math.radians(a))), 0.06))
    for a in (45, 70, 95):
        spikes.append((bc, br, (0, math.sin(math.radians(a)), math.cos(math.radians(a))), 0.065))
    for i, (c, r, d, sz) in enumerate(spikes):
        p, n = surf(c, r, d)
        cone(f"Spike_{i}", p - n * 0.01, n, sz, sz * 1.5, spike, flatten=0.45, seg=12)
    for i, (p, sz) in enumerate([((0, 0.31, 0.24), 0.05), ((0.04, 0.42, 0.16), 0.038), ((0.1, 0.49, 0.11), 0.026)]):
        cone(f"TailSpike_{i}", p, (0.1, 0.35, 1), sz, sz * 1.4, spike, flatten=0.45, seg=12)
    for s in (-1, 1):
        side = "L" if s < 0 else "R"
        tube(f"Arm_{side}", [(s * 0.12, -0.05, 0.39), (s * 0.2, -0.1, 0.33), (s * 0.2, -0.13, 0.3)], green,
             radius=0.03)
        tube(f"Leg_{side}", [(s * 0.1, 0.0, 0.17), (s * 0.105, -0.01, 0.07)], green, radius=0.06)
        sphere(f"Foot_{side}", (s * 0.108, -0.04, 0.04), (0.07, 0.095, 0.042), green, seg=20, ring=10)
        for t in (-1, 0, 1):
            sphere(f"Toe_{side}_{t + 1}", (s * 0.108 + t * 0.035, -0.128, 0.03), (0.017, 0.017, 0.015), belly,
                   seg=10, ring=5)
    return dict(backdrop="ffe3cf")


CHARS = {"kid": (1, kid), "fox": (2, fox), "robot": (3, robot), "dino": (4, dino)}

if __name__ == "__main__":
    name = sys.argv[sys.argv.index("--") + 1]
    n, fn = CHARS[name]
    opts = fn()
    tris = finalize()
    studio(backdrop=opts["backdrop"])
    print(f"TRIS {name} {tris}")
    render_and_save(f"{OUT}/concepts/{n}-{name}.png", f"{OUT}/art/characters/{name}.blend")
    print("DONE", name)
