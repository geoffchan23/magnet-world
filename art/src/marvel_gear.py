# Marvel / Avengers gear: Infinity Gauntlet + stones, Mjolnir, Cap's shield, stone pedestal.
# Run: blender --background --python art/src/marvel_gear.py
#   (GEAR_NO_ICONS=1 skips the icons, GEAR_PREVIEW=1 also renders art/renders/marvel_gear.png)
#
# Reuses the helpers, materials and icon look of weapons.py (same conventions):
# units are GAME units, Blender Z-up, -Y = forward (= Godot +Z), exported with +Y up.
# Exports assets/weapons/gear.glb with top-level nodes, all at the origin with identity transforms:
#
#   HAND SCALE (sized for the 0.55-tall figures like weapons.glb; parent under the hand with scale 1/0.55)
#   Gauntlet        origin = centre of the fist (the player's Hand node). Arm goes up (Godot +Y), back of
#                   the hand faces outward (Godot +X, away from the body for ArmR), thumb/index at the
#                   front (Godot +Z). Children, each origin at its socket centre, own material:
#                     Stone_Power (index knuckle), Stone_Space (middle), Stone_Reality (ring),
#                     Stone_Soul (little finger), Stone_Time (thumb), Stone_Mind (back of hand)
#                   Hide a child to show its socket empty.
#   Mjolnir         origin = grip (centre of the fist), handle along Godot Z, head forward (+Z),
#                   striking faces up/down (Godot +-Y), like the Hammer in weapons.glb.
#   CapShield       origin = centre of the disc, front (star) faces Godot +Z, 0.24 across.
#
#   WORLD SCALE (place directly in the world, no 1/0.55)
#   InfinityStone_Space/_Mind/_Reality/_Power/_Time/_Soul
#                   faceted oval gems 0.25 tall (Godot Y), origin at their centre.
#   Pedestal        0.8 wide, 0.7 tall, origin at floor centre, flat top at Godot y = 0.70;
#                   glowing ring on top + rune strips + base band use the material "Glow".
#
# Icons (256x256, transparent, weapons.py style): assets/weapons/
#   gauntlet.png, mjolnir.png, capshield.png, pedestal.png, stone_<space|mind|...>.png
import bpy, bmesh, math, os, sys
import numpy as np
from mathutils import Vector, Matrix, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weapons as W  # noqa: E402  (resets the scene, defines the shared helpers/materials)

ROOT = W.ROOT
OUT = os.path.join(ROOT, "assets", "weapons")
ICONS = OUT  # icons sit next to the weapon icons: assets/weapons/<name>.png
TAU = W.TAU
mat, lathe, loft, sweep, box, sphere, prism, collapse = W.mat, W.lathe, W.loft, W.sweep, W.box, W.sphere, W.prism, W.collapse

# ---------------------------------------------------------------- materials
GOLD = mat("Gold", "f2b632", 0.2, metal=1.0, coat=0.6)
GOLD_DK = mat("GoldDark", "b97a1c", 0.32, metal=1.0, coat=0.4)
SOCKET = mat("SocketDark", "2a1d10", 0.45, metal=0.5)
URU = mat("Uru", "8f9aa8", 0.26, metal=0.9, coat=0.3)
URU_EDGE = mat("UruEdge", "e6edf5", 0.14, metal=1.0)
URU_DK = mat("UruDark", "4a515c", 0.34, metal=0.9)
LEATHER = mat("Leather", "6b3d22", 0.55, coat=0.25)
SH_RED = mat("ShieldRed", "d3202c", 0.24, coat=0.9)
SH_SILVER = mat("ShieldSilver", "e8edf2", 0.18, metal=0.85, coat=0.6)
SH_BLUE = mat("ShieldBlue", "1d3f9e", 0.24, coat=0.9)
SH_BACK = mat("ShieldBack", "5d6672", 0.34, metal=0.85)
STONE = mat("PedestalStone", "7d8494", 0.62, coat=0.15)
STONE_DK = mat("PedestalStoneDark", "4c5262", 0.7, coat=0.1)
GLOW = mat("Glow", "b8f4ff", 0.2, emit="5fe6ff", emit_strength=4.0)

STONES = [  # name, base colour (deep), emission colour (bright, saturated)
    ("Space", "0e35c8", "2a6cff"),
    ("Mind", "d99a00", "ffc81a"),
    ("Reality", "b0000c", "ff1a24"),
    ("Power", "5a10b8", "a040ff"),
    ("Time", "08963a", "2cff6a"),
    ("Soul", "d04400", "ff7a10"),
]
GEM = {n: mat(f"Gem_{n}", c, 0.06, coat=1.0, emit=e, emit_strength=1.2) for n, c, e in STONES}
GEM_LOOSE = {n: mat(f"GemLoose_{n}", c, 0.05, coat=1.0, emit=e, emit_strength=1.6) for n, c, e in STONES}
GAUNTLET_SCALE = 1.2  # a bit oversized on the figure's hand (fun!)


# ---------------------------------------------------------------- shapes
def basis(n, u):
    """Matrix with local Z = n, local X = u (made perpendicular)."""
    n = Vector(n).normalized()
    u = Vector(u)
    u = (u - n * n.dot(u)).normalized()
    v = n.cross(u)
    return Matrix((u, v, n)).transposed()


def gem(name, L, Wd, D, m, n=16, back=True):
    """Faceted oval gem: long axis local X (L), width local Y (Wd), depth local Z (D), centred on the origin.
    back=False gives a flat-backed cabochon-like cut (for sockets)."""
    bm = bmesh.new()
    pts = []
    g = D * 0.07
    for k in range(n):
        a = TAU * k / n
        for z in ((g, -g) if back else (g, -D * 0.25)):
            pts.append((L / 2 * math.cos(a), Wd / 2 * math.sin(a), z))
    for sgn in ((1, -1) if back else (1,)):
        for k in range(n // 2):
            a = TAU * (k + 0.5) / (n // 2)
            pts.append((L / 2 * 0.8 * math.cos(a), Wd / 2 * 0.8 * math.sin(a), sgn * D * 0.33))
            a = TAU * k / (n // 2)
            pts.append((L / 2 * 0.5 * math.cos(a), Wd / 2 * 0.5 * math.sin(a), sgn * D * 0.5))
    vs = [bm.verts.new(p) for p in pts]
    res = bmesh.ops.convex_hull(bm, input=vs)
    bmesh.ops.delete(bm, geom=[v for v in res["geom_interior"] if isinstance(v, bmesh.types.BMVert)], context="VERTS")
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), verts=bm.verts[:], edges=bm.edges[:])
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return W.mk(name, bm, [m], sharp=4)


def socket(c, n, u, a, b, m_rim=None):
    """Empty oval bezel on a surface at c (normal n, long axis u): gold rim + dark cavity."""
    c, M = Vector(c), basis(n, u)
    nn = M.col[2].to_3d()
    lathe("Socket", [(-0.004, 1.34, 0), (0.0012, 1.36, 0), (0.0026, 1.2, 0), (0.0026, 1.04, 1),
                     (0.0006, 0.94, 1)], [m_rim or GOLD, SOCKET], p0=c, axis=nn, u=M.col[0].to_3d(),
          seg=14, sx=a, sy=b, caps=(None, 1), sharp=50)


def place(ob, c, n, u):
    ob.matrix_world = Matrix.Translation(Vector(c)) @ basis(n, u).to_4x4()


# ---------------------------------------------------------------- Infinity Gauntlet (hand scale)
FINGERS = [  # stone, y, radius   (index at the front = -Y)
    ("Power", -0.0225, 0.0081),
    ("Space", -0.0075, 0.0082),
    ("Reality", 0.0075, 0.0079),
    ("Soul", 0.0222, 0.0071),
]
KNUCKLE_N = Vector((0.8, 0, -0.6)).normalized()


def build_gauntlet():
    sockets = {}
    # palm / back of the hand
    box("Palm", (0.006, 0.0, 0.004), (0.04, 0.062, 0.052), GOLD, bevel=0.012, seg=3)
    # raised back plate (shield-shaped), the Mind stone in its middle
    outline = [(0.0275, y, z) for y, z in ((0.0, 0.031), (0.024, 0.026), (0.029, 0.004), (0.022, -0.016),
                                           (0.0, -0.022), (-0.022, -0.016), (-0.029, 0.004), (-0.024, 0.026))]
    prism("BackPlate", outline, (1, 0, 0), 0.007, GOLD, bevel=0.0022)
    prism("BackPlateRim", [(0.026, y * 1.1, z * 1.08 + 0.0006) for _, y, z in outline], (1, 0, 0), 0.004, GOLD_DK)
    sockets["Mind"] = ((0.0312, 0.0, 0.006), (1, 0, 0), (0, 0, 1), 0.0105, 0.0082)
    # fingers curled round under the palm, knuckle domes with a stone each
    for stone, y, r in FINGERS:
        k0 = Vector((0.018, y, -0.024))
        # three armour segments (proximal / middle / tip) pinched at the joints
        for seg_pts, r1 in (([k0, (-0.013, y, -0.0335)], 1.0),
                            ([(-0.011, y, -0.034), (-0.027, y, -0.0265), (-0.0315, y, -0.013)], 0.95),
                            ([(-0.0318, y, -0.015), (-0.0315, y, -0.002), (-0.022, y, 0.007)], 0.88)):
            sweep("Finger", seg_pts, lambda s, r=r * r1: (r * (0.84 + 0.16 * math.sin(math.pi * s) ** 0.5),) * 2,
                  GOLD, sides=8, uref=(0, 1, 0), rad=0.008, n=2)
        sphere("Knuckle", k0, r * 1.18, GOLD, useg=10, vseg=6)
        a = r * 0.86
        sockets[stone] = (k0 + KNUCKLE_N * r * 1.12, KNUCKLE_N, (0.6, 0, 0.8), a, a * 0.8)
        # tendon ridge from the back plate to the knuckle
        sweep("Tendon", [(0.027, y * 0.8, 0.0), (0.026, y * 0.95, -0.016), k0 + KNUCKLE_N * r * 0.9],
              lambda s: (0.0026, 0.0026), GOLD_DK, sides=6, rad=0.006, n=2)
    # thumb wrapped across the front of the fingers, stone on its first segment
    tpts = [(0.012, -0.022, 0.016), (0.003, -0.04, 0.003), (-0.014, -0.043, -0.011), (-0.03, -0.031, -0.014),
            (-0.036, -0.017, -0.01)]
    for a0, a1, r1 in ((0, 2, 1.0), (2, 4, 0.9)):
        seg_pts = tpts[a0:a1 + 1]
        sweep("Thumb", seg_pts, lambda s, r=0.0098 * r1: (r * (0.84 + 0.16 * math.sin(math.pi * s) ** 0.5),) * 2,
              GOLD, sides=10, uref=(0, 0, 1), rad=0.008, n=2)
    tn = Vector((0.55, -0.8, 0.25)).normalized()
    sockets["Time"] = (Vector((0.004, -0.04, 0.004)) + tn * 0.0102, tn, (0.75, 0.25, -0.6), 0.0072, 0.0058)
    # flared cuff over the wrist, open at the top for the arm
    prof = [(0.016, 0.022, 0), (0.027, 0.0238, 0), (0.0295, 0.0266, 1), (0.0345, 0.0266, 1), (0.037, 0.0242, 0),
            (0.039, 0.0242, 0), (0.058, 0.0274, 0), (0.0605, 0.0298, 1), (0.0655, 0.0298, 1), (0.0675, 0.0276, 2),
            (0.0675, 0.0252, 2), (0.052, 0.0232, 2)]
    lathe("Cuff", prof, [GOLD, GOLD_DK, SOCKET], p0=(0.004, 0, 0), axis=(0, 0, 1), u=(1, 0, 0), seg=20,
          sx=1.0, sy=1.16, caps=(None, 2), sharp=40)
    # pointed crest on the cuff, outer side
    prism("CuffCrest", [(0.0298, 0.0, 0.062), (0.0272, 0.011, 0.048), (0.0255, 0.0, 0.037), (0.0272, -0.011, 0.048)],
          (1, 0, 0), 0.005, GOLD_DK, bevel=0.0015)
    for stone, (c, n, u, a, b) in sockets.items():
        socket(c, n, u, a, b)
    g = collapse("Gauntlet")
    S = Matrix.Scale(GAUNTLET_SCALE, 4)
    g.data.transform(S)
    stones = []
    for stone, (c, n, u, a, b) in sockets.items():
        s = gem("Stone_" + stone, a * 2 * 0.98, b * 2 * 0.98, b * 1.3, GEM[stone], n=12, back=False)
        W.PARTS.clear()
        s.name = s.data.name = "Stone_" + stone
        s.data.transform(S)
        place(s, (Vector(c) + Vector(n).normalized() * 0.0016) * GAUNTLET_SCALE, n, u)
        s.parent = g
        stones.append(s)
    return g, stones


# ---------------------------------------------------------------- loose stones (world scale)
def build_loose_stones():
    out = []
    for i, (stone, _, _) in enumerate(STONES):
        s = gem("InfinityStone_" + stone, 0.25, 0.17, 0.12, GEM_LOOSE[stone], n=16)
        W.PARTS.clear()
        s.name = s.data.name = "InfinityStone_" + stone
        # long axis up, table facing front/back
        s.data.transform(Matrix.Rotation(math.radians(90), 4, "Y") @ Matrix.Rotation(math.radians(90), 4, "X"))
        out.append(s)
    return out


# ---------------------------------------------------------------- Mjolnir (hand scale)
def build_mjolnir():
    PY = 0.06  # pommel end
    prof = [(0, 0.0, 0), (0, 0.0118, 0), (0.003, 0.0142, 0), (0.009, 0.0142, 0), (0.012, 0.0112, 1), (0.015, 0.0108, 1)]
    prof += W.ridged(0.016, 0.118, 0.0122, 0.0108, 0.0105, 2)
    prof += [(0.12, 0.0112, 1), (0.122, 0.0138, 0), (0.134, 0.0138, 0), (0.136, 0.0114, 1), (0.17, 0.0114, 1)]
    lathe("Handle", prof, [URU_EDGE, URU_DK, LEATHER], p0=(0, PY, 0), axis=(0, -1, 0), seg=12, tilt=16, caps=(0, None))
    # wrist strap loop out of the pommel
    sweep("Strap", [(0, PY - 0.002, 0.0), (0, PY + 0.02, 0.013), (0, PY + 0.05, 0.0), (0, PY + 0.02, -0.013),
                    (0, PY - 0.002, -0.001)], lambda s: (0.0058, 0.0017), LEATHER, sides=6, uref=(1, 0, 0),
          rad=0.012, n=3)
    # head: chamfered block, striking faces along Z
    HY, HX, HYh, HZ, C = -0.146, 0.045, 0.048, 0.094, 0.015

    def octo(hx, hy, c):
        return [(hx, hy - c), (hx, -(hy - c)), (hx - c, -hy), (-(hx - c), -hy), (-hx, -(hy - c)), (-hx, hy - c),
                (-(hx - c), hy), (hx - c, hy)]
    st = [(-HZ, octo(HX - 0.009, HYh - 0.009, C - 0.004)), (-HZ + 0.008, octo(HX, HYh, C)),
          (HZ - 0.008, octo(HX, HYh, C)), (HZ, octo(HX - 0.009, HYh - 0.009, C - 0.004))]
    loft("Head", st, [URU, URU_EDGE], p0=(0, HY, 0), axis=(0, 0, 1), u=(1, 0, 0),
         fmat=lambda k: 1 if k % 2 == 1 else 0, cap0=0, sharp=20)
    # striking faces: concentric relief rings
    for sz in (-1, 1):
        lathe("FaceRing", [(-0.002, 0.03, 0), (0.0012, 0.03, 0), (0.0018, 0.027, 0), (0.0018, 0.023, 0),
                           (0.0012, 0.02, 0), (-0.001, 0.02, 0)], [URU_EDGE], p0=(0, HY, sz * HZ), axis=(0, 0, sz),
              seg=20, caps=(None, None))
    # knot-ring medallions on the long sides
    for n in ((1, 0, 0), (-1, 0, 0), (0, -1, 0)):
        n = Vector(n)
        c = Vector((0, HY, 0)) + Vector((n.x * HX, n.y * HYh, 0))
        lathe("Knot", [(-0.002, 0.026, 0), (0.0025, 0.026, 0), (0.0035, 0.023, 0), (0.0035, 0.018, 0), (0.002, 0.016, 1),
                       (0.0015, 0.0, 1)], [URU_EDGE, URU], p0=c, axis=n, seg=20, caps=(None, 1))
        lathe("KnotCore", [(-0.002, 0.009, 0), (0.0025, 0.009, 0), (0.0045, 0.006, 0)], [URU_EDGE], p0=c, axis=n,
              seg=12, caps=(None, 0))
    return collapse("Mjolnir")


# ---------------------------------------------------------------- Captain America's shield (hand scale)
def build_shield():
    R = 0.12

    def h(r):
        return 0.004 + 0.02 * (1 - (r / R) ** 2)
    prof = [(h(0), 0, 0)]
    # bands: blue centre, red, silver, red; each band starts with a little raised lip
    for r0, r1, mi in ((0.0, 0.043, 0), (0.043, 0.067, 1), (0.067, 0.091, 2), (0.091, 0.114, 1)):
        if r0 > 0:
            prof += [(h(r0) - 0.0006, r0, mi), (h(r0) + 0.0008, r0 + 0.0016, mi)]
        for r in np.linspace(r0 + 0.006, r1 - 0.001, 3 if r1 - r0 > 0.03 else 2):
            prof.append((h(r) + 0.0008, float(r), mi))
    prof += [(h(0.114) - 0.0004, 0.1144, 2), (h(0.117) + 0.0018, 0.1172, 2), (0.0035, 0.1205, 2), (-0.0005, 0.1206, 3),
             (-0.0025, 0.118, 3)]
    for r in (0.112, 0.09, 0.06, 0.03):
        prof.append((h(r) - 0.0065, r, 3))
    prof.append((h(0) - 0.0065, 0.0, 3))
    lathe("Shield", prof, [SH_BLUE, SH_RED, SH_SILVER, SH_BACK], p0=(0, 0, 0), axis=(0, -1, 0), u=(1, 0, 0),
          seg=36, caps=(None, None), sharp=50, phase=0.0)
    # star
    pts = []
    for k in range(10):
        a = math.radians(90 + 36 * k)
        r = 0.0385 if k % 2 == 0 else 0.0158
        pts.append((r * math.cos(a), -(h(0) + 0.0003), r * math.sin(a)))
    prism("Star", pts, (0, -1, 0), 0.004, SH_SILVER, bevel=0.0009)
    # back: two bolted brackets and a leather strap
    for sx in (-1, 1):
        box("Bracket", (sx * 0.036, -0.013, 0), (0.016, 0.01, 0.034), SH_BACK, bevel=0.003, seg=1)
    box("Strap", (0, -0.0066, 0), (0.082, 0.005, 0.022), LEATHER, bevel=0.0018, seg=1)
    box("Strap2", (0, -0.0072, -0.03), (0.06, 0.004, 0.016), LEATHER, bevel=0.0015, seg=1, rot=(0, 0, 0))
    return collapse("CapShield")


# ---------------------------------------------------------------- Pedestal (world scale)
def build_pedestal():
    k = 1 / math.cos(math.pi / 8)  # apothem -> octagon vertex radius

    def P(rows):
        return [(z, a * k, mi) for z, a, mi in rows]
    S, T, D = 0, 1, 2  # stone, gold trim, dark stone
    rows = [(0.0, 0.0, D), (0.0, 0.4, S), (0.064, 0.4, S), (0.074, 0.39, S), (0.074, 0.352, T), (0.08, 0.352, T),
            (0.086, 0.346, S), (0.086, 0.338, S), (0.142, 0.338, S), (0.15, 0.33, S), (0.15, 0.24, D),
            # column
            (0.165, 0.226, S), (0.172, 0.224, T), (0.186, 0.224, T), (0.19, 0.218, S), (0.505, 0.196, S),
            (0.51, 0.202, T), (0.524, 0.202, T), (0.53, 0.208, S),
            # capital flaring out to the top slab
            (0.585, 0.29, S), (0.592, 0.305, S), (0.598, 0.305, T), (0.608, 0.305, T), (0.612, 0.315, S),
            (0.69, 0.315, S), (0.7, 0.305, S), (0.7, 0.0, S)]
    lathe("Body", P(rows), [STONE, GOLD, STONE_DK], p0=(0, 0, 0), axis=(0, 0, 1), u=(1, 0, 0), seg=8, phase=0.5,
          caps=(None, None), sharp=30)
    # glowing ring set into the top (round), with gold rims; top surface stays at z = 0.70
    lathe("TopRing", [(0.698, 0.262, 0), (0.7015, 0.262, 0), (0.7025, 0.256, 0), (0.7025, 0.242, 1),
                      (0.7025, 0.212, 0), (0.7015, 0.206, 0), (0.698, 0.206, 0)], [GOLD, GLOW],
          p0=(0, 0, 0), axis=(0, 0, 1), seg=40, caps=(None, None), closed=False, sharp=50)
    lathe("TopDisc", [(0.698, 0.07, 0), (0.7015, 0.07, 0), (0.7015, 0.0, 0)], [STONE_DK], p0=(0, 0, 0),
          axis=(0, 0, 1), seg=24, caps=(None, None))
    # glowing band round the base step, set into a dark groove
    lathe("BaseGlow", P([(0.104, 0.336, 0), (0.106, 0.3415, 1), (0.122, 0.3415, 1), (0.124, 0.336, 0)]),
          [STONE_DK, GLOW], p0=(0, 0, 0), axis=(0, 0, 1), u=(1, 0, 0), seg=8, phase=0.5, caps=(None, None), sharp=30)
    # rune strips on four column faces (taper ~3.4 deg), each a slot with a glowing diamond rune
    tilt = math.atan((0.218 - 0.196) / (0.505 - 0.19))
    for i in range(4):
        ang = TAU * i / 4
        n = Vector((math.cos(ang), math.sin(ang), 0))
        for z, hgt, w in ((0.35, 0.22, 0.016),):
            a = 0.218 - (z - 0.19) * math.tan(tilt)
            c = n * (a + 0.001) + Vector((0, 0, z))
            rot = (0, -math.degrees(tilt), math.degrees(ang))
            box("Rune", c, (0.006, w, hgt), GLOW, bevel=0.002, seg=1, rot=rot)
            box("RuneSlot", n * (a - 0.0015) + Vector((0, 0, z)), (0.008, w + 0.014, hgt + 0.014), STONE_DK,
                bevel=0.003, seg=1, rot=rot)
            box("RuneGem", n * (a + 0.004) + Vector((0, 0, z)), (0.012, 0.03, 0.03), GLOW, bevel=0.004, seg=1,
                rot=(45, -math.degrees(tilt), math.degrees(ang)))
    # small gold corner studs on the base
    for i in range(8):
        ang = TAU * (i + 0.5) / 8
        p = Vector((math.cos(ang), math.sin(ang), 0)) * (0.40 * k - 0.012)
        sphere("Stud", p + Vector((0, 0, 0.037)), 0.014, GOLD, useg=8, vseg=5)
    return collapse("Pedestal")


# ---------------------------------------------------------------- export
def export(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
        for c in o.children:
            c.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "gear.glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True)
    for o in objs:
        dg = bpy.context.evaluated_depsgraph_get()
        allo = [o] + list(o.children)
        ws = [c.matrix_world @ Vector(v) for c in allo for v in c.bound_box]
        lo = Vector([min(w[i] for w in ws) for i in range(3)])
        hi = Vector([max(w[i] for w in ws) for i in range(3)])
        t = sum(W.tris(c) for c in allo)
        s = hi - lo
        print(f"GEAR {o.name:22s} tris {t:5d}  size godot (x,y,z) = ({s.x:.3f}, {s.z:.3f}, {s.y:.3f})  "
              f"bbox {W.godot(lo)} .. {W.godot(hi)}  mats {sorted({m.name for c in allo for m in c.data.materials})}")


# ---------------------------------------------------------------- icons
# (object rotation for the icon shot, relative to the weapons.py icon camera which looks from -X, a bit above)
ICON_ROT = {"Gauntlet": (-20, 180, 0), "Mjolnir": (-45, 0, 0), "CapShield": (0, 0, -70), "Pedestal": (0, 0, 20)}


def glow_halo(path, col, strength=0.85, rad=22):
    """Soft coloured glow behind an icon (for the stones)."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    al = a[..., 3]
    # separable box blur x3 ~ gaussian
    g = al.copy()
    for _ in range(3):
        for ax in (0, 1):
            c = np.cumsum(np.pad(g, [(rad, rad) if i == ax else (0, 0) for i in range(2)]), axis=ax)
            if ax == 0:
                g = (c[2 * rad:, :] - np.vstack([np.zeros((1, w)), c[:-2 * rad - 1, :]])[:h]) / (2 * rad + 1)
            else:
                g = (c[:, 2 * rad:] - np.hstack([np.zeros((h, 1)), c[:, :-2 * rad - 1]])[:, :w]) / (2 * rad + 1)
    halo = np.clip(g * 1.8, 0, 1) * strength
    ca = halo * (1 - al)
    na = al + ca
    rgb = (a[..., :3] * al[..., None] + np.array(col, np.float32) * ca[..., None]) / np.maximum(na[..., None], 1e-6)
    res = np.concatenate([rgb, na[..., None]], axis=2)
    im = bpy.data.images.new("halo", w, h, alpha=True)
    im.pixels.foreach_set(res.astype(np.float32).ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def icons(objs):
    cam = W.icon_setup()
    scn = bpy.context.scene
    raw = os.path.join(bpy.app.tempdir or "/tmp", "gear_icon_raw.png")
    only = os.environ.get("GEAR_ICON")
    shots = [(o, o.name.lower().replace("infinitystone_", "stone_")) for o in objs]
    for o, fname in shots:
        if only and o.name != only:
            continue
        for p in objs:
            p.hide_render = p is not o
            for c in p.children:
                c.hide_render = p is not o
        stone = o.name.startswith("InfinityStone_")
        # AgX washes saturated emissive colours out to pastel; the gems keep their colour under Standard
        # (closer to what Godot's per-channel filmic does with them).
        scn.view_settings.view_transform = "Standard" if stone else "AgX"
        scn.view_settings.look = "None" if stone else "AgX - Punchy"
        if stone:  # tone the glow down for the shot so the facets read; the halo carries the glow
            b = next(n for n in o.data.materials[0].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            b.inputs["Emission Strength"].default_value = 0.45
        o.rotation_euler = [math.radians(x) for x in (ICON_ROT.get(o.name) or (0, 0, -90 + 18))]
        bpy.context.view_layer.update()
        ci = cam.rotation_euler.to_matrix().inverted()
        pts = [ci @ (c.matrix_world @ v.co) for c in [o] + list(o.children) for v in c.data.vertices]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        c = (lo + hi) / 2
        ext = max(hi.x - lo.x, hi.y - lo.y)
        cam.data.ortho_scale = ext * (1.5 if stone else 1.16)
        cam.location = cam.rotation_euler.to_matrix() @ Vector((c.x, c.y, hi.z + 2.0))
        cam.data.clip_end = 6
        scn.render.filepath = raw
        bpy.ops.render.render(write_still=True)
        dst = os.path.join(ICONS, fname + ".png")
        W.outline_and_shrink(raw, dst)
        if stone:
            col = next(W.lin(e)[:3] for n, _, e in STONES if "InfinityStone_" + n == o.name)
            glow_halo(dst, [min(1.0, x * 1.6 + 0.12) for x in col], rad=10)
        print("ICON", dst)
        if stone:
            b.inputs["Emission Strength"].default_value = 1.6
        o.rotation_euler = (0, 0, 0)
    for p in objs:
        p.hide_render = False
        for c in p.children:
            c.hide_render = False


# ---------------------------------------------------------------- preview sheet
def preview(objs):
    """Everything laid out on a floor, with the kid figure (0.55 tall) for scale -> art/renders/marvel_gear.png."""
    scn = bpy.context.scene
    by = {o.name: o for o in objs}
    lay = {"Pedestal": (0.0, 0.25, 0), "InfinityStone_Space": (-0.75, 0.35, 0.16), "InfinityStone_Mind": (-0.45, 0.35, 0.16),
           "InfinityStone_Reality": (0.45, 0.35, 0.16), "InfinityStone_Power": (0.75, 0.35, 0.16),
           "InfinityStone_Time": (-0.6, 0.0, 0.16), "InfinityStone_Soul": (0.6, 0.0, 0.16)}
    for n, p in lay.items():
        by[n].location = p
    by["InfinityStone_Mind"].location.z = 0.7 + 0.2
    by["InfinityStone_Mind"].location.x, by["InfinityStone_Mind"].location.y = 0.0, 0.25
    # figure with the gauntlet on its hand
    kid = os.path.join(ROOT, "assets", "characters", "kid.glb")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=kid)
    new = [o for o in bpy.data.objects if o not in before]
    rootk = [o for o in new if o.parent is None]
    fig = bpy.data.objects.new("Figure", None)
    bpy.context.collection.objects.link(fig)
    for o in rootk:
        o.parent = fig
    fig.scale = (0.55,) * 3
    fig.location = (-0.25, -0.45, 0)
    bpy.context.view_layer.update()
    arm = next((o for o in new if "ArmR" in o.name and o.type == "MESH"), None) or \
        next(o for o in new if "ArmR" in o.name)
    mesh_o = arm if arm.type == "MESH" else next(c for c in arm.children_recursive if c.type == "MESH")
    ws = [mesh_o.matrix_world @ Vector(v) for v in mesh_o.bound_box]
    lo = Vector([min(w[i] for w in ws) for i in range(3)])
    hi = Vector([max(w[i] for w in ws) for i in range(3)])
    hand = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + (hi.z - lo.z) * 0.12))
    by["Gauntlet"].location = hand
    # a second figure holding mjolnir + shield
    by["Mjolnir"].location = (0.45, -0.5, 0.25)
    by["Mjolnir"].rotation_euler = (math.radians(-60), 0, math.radians(20))
    by["CapShield"].location = (0.15, -0.55, 0.15)
    by["CapShield"].rotation_euler = (math.radians(-10), 0, math.radians(-20))
    # big gauntlet close-up copy (x3) on the right
    big = by["Gauntlet"].copy()
    bpy.context.collection.objects.link(big)
    for c in by["Gauntlet"].children:
        cc = c.copy()
        bpy.context.collection.objects.link(cc)
        cc.parent = big
    big.scale = (3.2,) * 3
    big.location = (1.05, -0.35, 0.18)
    big.rotation_euler = (0, 0, math.radians(-150))
    big2 = by["Mjolnir"].copy()
    bpy.context.collection.objects.link(big2)
    big2.scale = (2.0,) * 3
    big2.location = (-1.05, -0.35, 0.25)
    big2.rotation_euler = (math.radians(-80), 0, math.radians(200))
    # floor + light + camera
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    fl = bpy.context.active_object
    fl.data.materials.append(mat("PreviewFloor", "c9cfd8", 0.6))
    scn.render.engine = "CYCLES"
    scn.cycles.samples = int(os.environ.get("GEAR_SAMPLES", "96"))
    scn.cycles.use_denoising = True
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    scn.render.film_transparent = False
    scn.render.resolution_x, scn.render.resolution_y = 1800, 1000
    world = bpy.data.worlds.new("Sky")
    scn.world = world
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.55, 0.62, 0.75, 1)
    bg.inputs["Strength"].default_value = 0.7
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = 3.2
    sd.angle = math.radians(8)
    sun = bpy.data.objects.new("Sun", sd)
    scn.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    cd = bpy.data.cameras.new("PrevCam")
    cd.lens = 50
    cam = bpy.data.objects.new("PrevCam", cd)
    scn.collection.objects.link(cam)
    cam.location = (0.0, -3.4, 1.75)
    cam.rotation_euler = (Vector((0, 0.05, 0.3)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam
    for o in bpy.data.objects:
        o.hide_render = False
    scn.render.filepath = os.path.join(ROOT, "art", "renders", "marvel_gear.png")
    bpy.ops.render.render(write_still=True)
    print("PREVIEW", scn.render.filepath)


if __name__ == "__main__":
    g, stones = build_gauntlet()
    loose = build_loose_stones()
    objs = [g] + loose + [build_mjolnir(), build_shield(), build_pedestal()]
    export(objs)
    if os.environ.get("GEAR_NO_ICONS") != "1":
        icons(objs)
    if os.environ.get("GEAR_PREVIEW") == "1":
        preview(objs)
