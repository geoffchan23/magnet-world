# Enterable buildings: hollow building shells, floor slabs, stairs and furnished rooms.
# Run: blender --background --python art/src/interiors_kit.py [-- preview [out.png]]
# Exports assets/city/interiors.glb (one top-level mesh per piece) and
# assets/city/interiors.json (collision boxes, stair ramps and lamp spots per piece,
# in Godot coordinates, read by city.gd).
#
# Same conventions as city_kit.py (and it reuses its builders and materials): game
# units, a storey is 1.25, origin at the footprint centre on the floor, front faces
# Blender -Y (= Godot +Z), Blender (x, y, z) -> Godot (x, z, -y).
#
# One storey layout is shared by every enterable building (Blender coords):
#   inside the walls     x, y in [-1.76, 1.76] (ground floor: y from -1.5, behind the shopfront)
#   floor surface        z = 0.06 (each storey's slab is z 0..0.06; the ceiling is the next slab)
#   stair "A"            x in [1.02, 1.72], climbing +y from y = -1.07 to y = 1.13
#   stairwell hole "A'"  x in [-1.78, -0.98], y in [-1.3, 0.1]  (the stair A of the storey
#                        below, seen from a storey turned 180 degrees)
# Storey k of a building is turned k * 180 degrees, so a stair always lands in the next
# storey's A' hole and every storey uses the same pieces. Keep clear for walking: the
# front strip y < -1.2 (landing -> next stair), the hole and the stair.
#
# Materials: the shells use the kit's textured materials (Brick, Plaster, Concrete...).
# Furniture uses "Furn" (white base, colour in the vertex colours) and "Glow" (lamps and
# screens; unshaded in Godot), so a whole furnished room is two draw calls.
import bpy, bmesh, math, os, random, sys, json
from mathutils import Vector, Matrix, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import city_kit as K
from city_kit import H, WO, EDGE, T, TR, side_M, t_box, t_cyl, t_bar, t_tube, t_quad, t_panel, t_prism, sstep, clamp

OUT = K.OUT
F = 0.06                  # floor surface
CEIL = H                  # ceiling (underside of the next slab)
IN = 1.76                 # inner face of the walls
STAIR = (1.02, 1.72)      # stair x range
STAIR_Y = (-1.07, 1.13)   # ramp foot / top (tread midpoints)
STEPS = 9
STEP_Y0 = -0.95           # first riser
HOLE = (-1.78, -1.3, -0.98, 0.1)
I4 = Matrix.Identity(4)

K.MAT_DEFS["Furn"] = ((1.0, 1.0, 1.0, 1), 0.75, 0.0)
K.MAT_DEFS["Glow"] = ((1.0, 1.0, 1.0, 1), 1.0, 0.0)

COLL = {}    # piece -> {"boxes": [[minx, miny, minz, maxx, maxy, maxz]], "ramps": [[x0, x1, z_foot, z_top, y0, y1]]}
LIGHTS = {}  # piece -> [[x, y, z]] lamp spots (Godot)


def C(h, k=1.0):
    """sRGB hex -> tint tuple (vertex colours are sRGB), optionally darkened."""
    h = h.lstrip("#")
    return tuple(min(1.0, int(h[i:i + 2], 16) / 255 * k) for i in (0, 2, 4))


def mul(c, k):
    return tuple(min(1.0, x * k) for x in c)


def gd_box(M, x0, y0, z0, x1, y1, z1):
    pts = [M @ Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    xs, ys, zs = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
    return [round(v, 3) for v in (min(xs), min(zs), -max(ys), max(xs), max(zs), -min(ys))]


def solid(name, x0, y0, z0, x1, y1, z1, M=None):
    COLL.setdefault(name, {"boxes": []})["boxes"].append(gd_box(M if M is not None else I4, x0, y0, z0, x1, y1, z1))


class PieceIn(K.Piece):
    """A kit Piece whose dark "Interior" stand-ins are dropped and whose wall backs are plaster."""

    def add(self, tmp, M=None, m="Concrete", tint=1.0, smooth=None):
        if m == "Interior":
            tmp.free()
            return
        if isinstance(m, (list, tuple)):
            m = ["Plaster" if x == "Interior" else x for x in m]
        super().add(tmp, M, m, tint, smooth)


def grime_furn(p, n):
    v = 0.86 + 0.14 * noise.noise(p * 5.0)
    if n.z < -0.5:
        v *= 0.7
    v *= 0.82 + 0.18 * sstep((p.z - F) / 0.12)
    return v


def t_box_faces(x0, y0, z0, x1, y1, z1):
    """Box whose faces get material index 0 (sides), 1 (top), 2 (bottom)."""
    bm = t_box(x0, y0, z0, x1, y1, z1)
    for f in bm.faces:
        f.material_index = 1 if f.normal.z > 0.5 else 2 if f.normal.z < -0.5 else 0
    return bm


def t_sphere(r, sub=1):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    for f in bm.faces:
        f.smooth = True
    return bm


# ---------------------------------------------------------------- room builder
class Room:
    def __init__(self, name, seed, upper):
        self.name = name
        self.rng = random.Random(seed)
        self.upper = upper
        self.P = PieceIn(name, grime_furn)
        COLL.setdefault(name, {"boxes": []})
        LIGHTS.setdefault(name, [])

    def box(self, x0, y0, z0, x1, y1, z1, col, M=None, bevel=0.0, solid=False, m="Furn"):
        M = M if M is not None else I4
        self.P.add(t_box(x0, y0, z0, x1, y1, z1, bevel), M, m, col)
        if solid:
            self.solid(x0, y0, z0, x1, y1, z1, M)

    def solid(self, x0, y0, z0, x1, y1, z1, M=None):
        solid(self.name, x0, y0, z0, x1, y1, z1, M)

    def cyl(self, x, y, z, r, h, col, M=None, seg=8, r2=None, m="Furn"):
        M = M if M is not None else I4
        self.P.add(t_cyl(r, h, seg, r2=r2), M @ TR((x, y, z)), m, col)

    def bar(self, p0, p1, r, col, M=None, sides=5, m="Furn"):
        self.P.add(t_bar(p0, p1, r, sides=sides, smooth=False), M if M is not None else I4, m, col)

    def ball(self, x, y, z, r, col, M=None, m="Furn"):
        self.P.add(t_sphere(r), (M if M is not None else I4) @ TR((x, y, z)), m, col)

    def quad_up(self, x0, y0, x1, y1, z, col, M=None, m="Furn"):
        self.P.add(t_quad([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]), M if M is not None else I4, m, col)

    def quad_down(self, x0, y0, x1, y1, z, col, M=None, m="Furn"):
        self.P.add(t_quad([(x0, y0, z), (x0, y1, z), (x1, y1, z), (x1, y0, z)]), M if M is not None else I4, m, col)

    def quad_front(self, x0, z0, x1, z1, y, col, M=None, m="Furn"):
        """Vertical quad facing -y (the item's front)."""
        self.P.add(t_quad([(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]), M if M is not None else I4, m, col)

    def light(self, x, y, z):
        LIGHTS[self.name].append([round(x, 3), round(z, 3), round(-y, 3)])

    def finish(self):
        return self.P.finish()


def at(x, y, rot=0.0, z=F):
    return TR((x, y, z), (0, 0, rot))


def floor_rects(upper, ground_front=-1.5):
    if upper:
        return [(-IN, 0.14, IN, IN), (-0.94, -IN, IN, 0.14), (-IN, -IN, -0.94, -1.3)]
    return [(-IN, ground_front, IN, IN)]


def floor_grid(R, sx, sy, colfn, stagger=0.0, z=F + 0.002):
    """Floor covering (tiles, boards, carpet squares) laid over the walkable floor."""
    for (x0, y0, x1, y1) in floor_rects(R.upper):
        nj = int(math.ceil(4.0 / sy))
        for j in range(nj):
            gy0, gy1 = -2 + j * sy, -2 + (j + 1) * sy
            off = (j % 2) * stagger * sx
            ni = int(math.ceil(4.0 / sx)) + 1
            for i in range(ni):
                gx0, gx1 = -2 + i * sx - off, -2 + (i + 1) * sx - off
                a, b = max(gx0, x0), min(gx1, x1)
                c, d = max(gy0, y0), min(gy1, y1)
                if b - a > 1e-3 and d - c > 1e-3:
                    R.quad_up(a, c, b, d, z, colfn(i, j, R.rng))


def bare_floor(R, col):
    for (x0, y0, x1, y1) in floor_rects(R.upper):
        R.quad_up(x0, y0, x1, y1, F + 0.002, mul(col, R.rng.uniform(0.92, 1.0)))


# ---------------------------------------------------------------- furniture
WOOD = C("8a5a3a")
WOOD_D = C("5c3a24")
WOOD_L = C("b98a5a")
GREY = C("8d9296")
GREY_D = C("4a4e52")
WHITE = C("e8e4da")
BLACK = C("232426")
WARM = C("ffd9a0")
COOL = C("dff2ff")
SCREEN = C("7fb6e0")


def sofa(R, x, y, rot, col, w=1.0, d=0.42):
    M = at(x, y, rot)
    R.box(-w / 2, -d / 2, 0.03, w / 2, d / 2, 0.12, mul(col, 0.75), M)
    for fx in (-w / 2 + 0.05, w / 2 - 0.05):
        for fy in (-d / 2 + 0.05, d / 2 - 0.05):
            R.cyl(fx, fy, 0.0, 0.02, 0.03, WOOD_D, M, 5)
    n = 2 if w > 0.7 else 1
    cw = (w - 0.18) / n
    for i in range(n):
        x0 = -w / 2 + 0.09 + i * cw
        R.box(x0 + 0.005, -d / 2 + 0.02, 0.12, x0 + cw - 0.005, d / 2 - 0.1, 0.19, col, M, bevel=0.02)
        R.box(x0 + 0.01, d / 2 - 0.16, 0.18, x0 + cw - 0.01, d / 2 - 0.08, 0.36, mul(col, 0.95), M @ TR((0, 0, 0), (-0.15, 0, 0)), bevel=0.02)
    R.box(-w / 2, d / 2 - 0.1, 0.12, w / 2, d / 2, 0.4, mul(col, 0.88), M, bevel=0.02)
    for sx in (-1, 1):
        R.box(sx * w / 2 - (0.09 if sx > 0 else 0), -d / 2, 0.12, sx * w / 2 + (0.09 if sx < 0 else 0), d / 2, 0.27,
              mul(col, 0.85), M, bevel=0.02)
    R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, 0.19, M)
    R.solid(-w / 2, d / 2 - 0.1, 0, w / 2, d / 2, 0.4, M)


def cushion(R, x, y, z, rot, col):
    R.box(-0.08, -0.03, -0.07, 0.08, 0.03, 0.07, col, TR((x, y, z), (0.3, 0.2, rot)), bevel=0.02)


def tv_stand(R, x, y, rot):
    M = at(x, y, rot)
    R.box(-0.42, -0.12, 0.0, 0.42, 0.12, 0.17, WOOD, M, bevel=0.01, solid=True)
    R.box(-0.4, -0.125, 0.02, -0.01, -0.12, 0.15, mul(WOOD, 0.85), M)
    R.box(0.01, -0.125, 0.02, 0.4, -0.12, 0.15, mul(WOOD, 0.85), M)
    R.box(-0.06, -0.06, 0.17, 0.06, 0.04, 0.19, BLACK, M)
    R.box(-0.02, -0.01, 0.19, 0.02, 0.02, 0.25, BLACK, M)
    R.box(-0.27, -0.03, 0.24, 0.27, 0.0, 0.56, BLACK, M, bevel=0.008)
    R.quad_front(-0.25, 0.26, 0.25, 0.54, -0.032, SCREEN, M, m="Glow")
    # a picture on the screen: hills and a sun
    R.quad_front(-0.25, 0.26, 0.25, 0.34, -0.033, C("6fbf73"), M, m="Glow")
    R.quad_front(0.1, 0.44, 0.17, 0.51, -0.033, C("ffe27a"), M, m="Glow")
    # game console + controller
    R.box(0.22, -0.08, 0.17, 0.36, 0.05, 0.2, WHITE, M)
    R.box(-0.35, -0.08, 0.17, -0.25, 0.0, 0.19, GREY_D, M)


def coffee_table(R, x, y, rot, w=0.5, d=0.28):
    M = at(x, y, rot)
    R.box(-w / 2, -d / 2, 0.14, w / 2, d / 2, 0.17, WOOD_L, M, bevel=0.01, solid=True)
    for fx in (-w / 2 + 0.03, w / 2 - 0.03):
        for fy in (-d / 2 + 0.03, d / 2 - 0.03):
            R.box(fx - 0.015, fy - 0.015, 0, fx + 0.015, fy + 0.015, 0.14, WOOD, M)
    R.box(-0.15, -0.08, 0.17, 0.02, 0.05, 0.175, C("d04a3a"), M @ TR((0, 0, 0), (0, 0, 0.3)))
    R.cyl(0.13, 0.03, 0.17, 0.025, 0.045, WHITE, M, 6)


def rug(R, x0, y0, x1, y1, col, border, stripes=None):
    R.box(x0, y0, F, x1, y1, F + 0.008, border)
    R.box(x0 + 0.06, y0 + 0.06, F, x1 - 0.06, y1 - 0.06, F + 0.011, col)
    if stripes:
        n = 4
        for i in range(n):
            a = x0 + 0.12 + (x1 - x0 - 0.24) * (i + 0.35) / n
            R.box(a, y0 + 0.1, F, a + 0.05, y1 - 0.1, F + 0.013, stripes)


def round_rug(R, x, y, r, col, ring):
    R.cyl(x, y, F, r, 0.008, ring, seg=14)
    R.cyl(x, y, F, r - 0.06, 0.011, col, seg=14)


def floor_lamp(R, x, y):
    R.cyl(x, y, F, 0.07, 0.02, BLACK, seg=8)
    R.bar((x, y, F), (x, y, F + 0.68), 0.012, GREY_D)
    R.cyl(x, y, F + 0.62, 0.11, 0.15, WARM, seg=10, r2=0.07, m="Glow")
    R.light(x, y, F + 0.7)


def table_lamp(R, x, y, z):
    R.cyl(x, y, z, 0.035, 0.08, C("c9b27a"), seg=8, r2=0.02)
    R.cyl(x, y, z + 0.08, 0.06, 0.08, WARM, seg=8, r2=0.04, m="Glow")


def bookshelf(R, x, y, rot, w=0.8, h=0.78, d=0.17, col=WOOD):
    M = at(x, y, rot)
    rng = R.rng
    R.box(-w / 2, -d / 2, 0, -w / 2 + 0.025, d / 2, h, col, M)
    R.box(w / 2 - 0.025, -d / 2, 0, w / 2, d / 2, h, col, M)
    R.box(-w / 2, d / 2 - 0.01, 0, w / 2, d / 2, h, mul(col, 0.7), M)
    levels = 4
    for i in range(levels + 1):
        z = 0.02 + i * (h - 0.04) / levels
        R.box(-w / 2 + 0.025, -d / 2, z - 0.012, w / 2 - 0.025, d / 2, z + 0.012, col, M)
    cols = [C("b23a3a"), C("2f5d8c"), C("e0b040"), C("3f7f4f"), C("7a3f8f"), C("d07030"), WHITE]
    for i in range(levels):
        z = 0.032 + i * (h - 0.04) / levels
        u = -w / 2 + 0.035
        while u < w / 2 - 0.08:
            bw = rng.uniform(0.025, 0.045)
            bh = rng.uniform(0.11, 0.16)
            if rng.random() < 0.12:
                u += 0.06
                continue
            if rng.random() < 0.08:
                R.box(u, -d / 2 + 0.02, z, u + bh, -d / 2 + 0.02 + 0.11, z + bw, rng.choice(cols), M)
                u += bh + 0.01
                continue
            R.box(u, -d / 2 + 0.02, z, u + bw, d / 2 - 0.02, z + bh, rng.choice(cols), M)
            u += bw + 0.003
    R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, h, M)


def kitchen(R, x0, x1, y, rot, top=C("d8d2c4"), front=C("6f9a8d")):
    """Counter run along a wall: back at local +y."""
    M = at(0, y, rot)
    d = 0.26
    R.box(x0, -d, 0.02, x1, 0.0, 0.36, front, M, solid=True)
    R.box(x0, -d, 0, x1, -0.02, 0.02, BLACK, M)
    R.box(x0 - 0.01, -d - 0.02, 0.36, x1 + 0.01, 0.0, 0.385, top, M)
    n = max(1, int((x1 - x0) / 0.3))
    for i in range(n):
        a = x0 + (x1 - x0) * i / n
        b = x0 + (x1 - x0) * (i + 1) / n
        R.box(a + 0.01, -d - 0.004, 0.03, b - 0.01, -d, 0.34, mul(front, 0.9), M)
        R.box((a + b) / 2 - 0.04, -d - 0.016, 0.3, (a + b) / 2 + 0.04, -d - 0.004, 0.31, GREY, M)
    # sink + tap, stove
    sx = x0 + (x1 - x0) * 0.3
    R.box(sx - 0.12, -d + 0.04, 0.37, sx + 0.12, -0.04, 0.386, GREY_D, M)
    R.bar((sx, -0.03, 0.385), (sx, -0.03, 0.47), 0.01, GREY, M)
    R.bar((sx, -0.03, 0.47), (sx, -0.1, 0.46), 0.01, GREY, M)
    st = x0 + (x1 - x0) * 0.75
    for dx in (-0.06, 0.06):
        for dy in (-0.17, -0.08):
            R.cyl(st + dx, dy, 0.385, 0.035, 0.006, BLACK, M, 8)
    # pot, kettle, plates
    R.cyl(st - 0.06, -0.17, 0.39, 0.045, 0.06, C("c04030"), M, 8)
    R.cyl(sx + 0.2, -0.1, 0.385, 0.035, 0.07, WHITE, M, 8)


def fridge(R, x, y, rot, col=WHITE, h=0.78):
    M = at(x, y, rot)
    R.box(-0.17, -0.15, 0, 0.17, 0.15, h, col, M, bevel=0.015, solid=True)
    R.box(-0.165, -0.155, h * 0.62, 0.165, -0.15, h * 0.625, GREY, M)
    R.box(0.12, -0.17, h * 0.67, 0.135, -0.155, h * 0.85, GREY, M)
    R.box(0.12, -0.17, h * 0.3, 0.135, -0.155, h * 0.55, GREY, M)
    for i, c in enumerate([C("e04040"), C("40a0e0"), C("f0c030")]):
        R.box(-0.1 + i * 0.06, -0.16, h * 0.4 + i * 0.04, -0.07 + i * 0.06, -0.152, h * 0.43 + i * 0.04, c, M)
    R.quad_front(-0.12, h * 0.36, -0.02, h * 0.5, -0.152, C("f6f0d8"), M)


def bed(R, x, y, rot, blanket, w=0.62, L=0.92):
    """Headboard at local +y."""
    M = at(x, y, rot)
    R.box(-w / 2, -L / 2, 0.03, w / 2, L / 2, 0.12, WOOD, M)
    R.box(-w / 2, L / 2 - 0.04, 0, w / 2, L / 2, 0.38, WOOD_D, M, bevel=0.01)
    R.box(-w / 2, -L / 2, 0, w / 2, -L / 2 + 0.03, 0.18, WOOD_D, M)
    R.box(-w / 2 + 0.02, -L / 2 + 0.03, 0.12, w / 2 - 0.02, L / 2 - 0.04, 0.19, WHITE, M, bevel=0.015)
    R.box(-w / 2 + 0.005, -L / 2 + 0.01, 0.13, w / 2 - 0.005, L / 2 * 0.25, 0.205, blanket, M, bevel=0.015)
    R.box(-w / 2 + 0.01, L / 2 * 0.25 - 0.06, 0.19, w / 2 - 0.01, L / 2 * 0.25 + 0.04, 0.215, mul(blanket, 0.85), M @ TR((0, 0, 0), (-0.25, 0, 0)), bevel=0.012)
    for px in (-w / 4, w / 4):
        R.box(px - 0.12, L / 2 - 0.2, 0.19, px + 0.12, L / 2 - 0.06, 0.25, C("f4f1ea"), M, bevel=0.02)
    R.solid(-w / 2, -L / 2, 0, w / 2, L / 2, 0.2, M)
    R.solid(-w / 2, L / 2 - 0.04, 0, w / 2, L / 2, 0.38, M)


def bedside(R, x, y, rot, lamp=True):
    M = at(x, y, rot)
    R.box(-0.1, -0.09, 0, 0.1, 0.09, 0.2, WOOD_L, M, bevel=0.008, solid=True)
    R.box(-0.08, -0.095, 0.1, 0.08, -0.09, 0.17, mul(WOOD_L, 0.85), M)
    if lamp:
        p = M @ Vector((0.0, 0.02, 0.2))
        table_lamp(R, p.x, p.y, p.z)
        R.light(p.x, p.y, p.z + 0.12)


def wardrobe(R, x, y, rot, w=0.7, d=0.3, h=0.88, col=WOOD):
    M = at(x, y, rot)
    R.box(-w / 2, -d / 2, 0, w / 2, d / 2, h, col, M, bevel=0.01, solid=True)
    R.box(-0.006, -d / 2 - 0.004, 0.04, 0.006, -d / 2, h - 0.03, mul(col, 0.6), M)
    for sx in (-1, 1):
        R.box(sx * 0.03 - 0.006, -d / 2 - 0.02, h * 0.45, sx * 0.03 + 0.006, -d / 2, h * 0.6, GREY, M)
    R.box(-w / 2 + 0.05, -d / 2 + 0.05, h, -w / 2 + 0.3, d / 2 - 0.02, h + 0.12, C("b08850"), M @ TR((0, 0, 0), (0, 0, 0.1)))


def chair(R, x, y, rot, col=WOOD, tipped=False):
    M = at(x, y, rot) if not tipped else TR((x, y, F + 0.0), (0, 0, rot)) @ TR((0, 0, 0.09), (math.radians(90), 0, 0)) @ TR((0, 0, -0.09))
    R.box(-0.08, -0.08, 0.16, 0.08, 0.08, 0.185, col, M)
    for fx in (-0.065, 0.065):
        for fy in (-0.065, 0.065):
            R.box(fx - 0.01, fy - 0.01, 0, fx + 0.01, fy + 0.01, 0.16, mul(col, 0.8), M)
    R.box(-0.08, 0.06, 0.185, 0.08, 0.08, 0.38, col, M)


def dining(R, x, y, rot, w=0.56, d=0.36):
    M = at(x, y, rot)
    R.box(-w / 2, -d / 2, 0.28, w / 2, d / 2, 0.305, WOOD_L, M, bevel=0.008)
    for fx in (-w / 2 + 0.04, w / 2 - 0.04):
        for fy in (-d / 2 + 0.04, d / 2 - 0.04):
            R.box(fx - 0.018, fy - 0.018, 0, fx + 0.018, fy + 0.018, 0.28, WOOD, M)
    R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, 0.305, M)
    R.box(-0.08, -0.06, 0.305, 0.08, 0.06, 0.307, C("f0ece0"), M)
    R.cyl(0.0, 0.0, 0.307, 0.05, 0.03, C("c06040"), M, 8)
    for (cx, cy, cr) in [(-w / 4, -d / 2 - 0.08, 0), (w / 4, -d / 2 - 0.06, 0.2), (-w / 4, d / 2 + 0.08, math.pi)]:
        p = M @ Vector((cx, cy, 0))
        chair(R, p.x, p.y, rot + cr)


def desk(R, x, y, rot, top=C("cfc6b4"), screen=True, rng=None):
    """Worker sits at local -y."""
    rng = rng or R.rng
    M = at(x, y, rot)
    w, d = 0.62, 0.3
    R.box(-w / 2, -d / 2, 0.285, w / 2, d / 2, 0.305, top, M, bevel=0.006)
    R.box(-w / 2, -d / 2 + 0.03, 0, -w / 2 + 0.02, d / 2, 0.285, GREY, M)
    R.box(w / 2 - 0.15, -d / 2 + 0.02, 0, w / 2, d / 2, 0.285, GREY, M)
    for i in range(3):
        z = 0.02 + i * 0.09
        R.box(w / 2 - 0.145, -d / 2 + 0.015, z + 0.01, w / 2 - 0.005, -d / 2 + 0.02, z + 0.08, mul(GREY, 0.9), M)
    R.box(-w / 2 + 0.02, d / 2 - 0.02, 0.08, w / 2 - 0.15, d / 2, 0.285, mul(GREY, 0.85), M)
    R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, 0.305, M)
    if screen:
        R.box(-0.04, 0.03, 0.305, 0.04, 0.09, 0.315, BLACK, M)
        R.box(-0.012, 0.06, 0.315, 0.012, 0.075, 0.37, BLACK, M)
        R.box(-0.14, 0.05, 0.35, 0.14, 0.075, 0.53, BLACK, M, bevel=0.005)
        R.quad_front(-0.13, 0.36, 0.13, 0.52, 0.049, rng.choice([SCREEN, C("8fd0a0"), C("a0a8e8")]), M, m="Glow")
        R.box(-0.13, -0.08, 0.305, 0.1, -0.02, 0.312, mul(BLACK, 1.6), M)
        R.box(0.13, -0.07, 0.305, 0.17, -0.02, 0.312, BLACK, M)
    for i in range(rng.randint(1, 3)):
        R.box(-0.28, -0.1, 0.305 + i * 0.004, -0.17, 0.04, 0.308 + i * 0.004, C("f6f4ee"), M @ TR((0, 0, 0), (0, 0, rng.uniform(-0.3, 0.3))))
    R.cyl(0.22, 0.06, 0.305, 0.022, 0.04, rng.choice([C("d04a3a"), WHITE, C("3a70c0")]), M, 6)


def office_chair(R, x, y, rot, col=C("33384a"), tipped=False):
    if tipped:
        M = TR((x, y, F), (0, 0, rot)) @ TR((0, 0, 0.12), (math.radians(80), 0, 0)) @ TR((0, 0, -0.04))
    else:
        M = at(x, y, rot)
    for k in range(5):
        a = k * 2 * math.pi / 5
        R.bar((0, 0, 0.03), (math.cos(a) * 0.1, math.sin(a) * 0.1, 0.02), 0.012, BLACK, M, 4)
    R.bar((0, 0, 0.02), (0, 0, 0.17), 0.015, GREY_D, M, 6)
    R.box(-0.09, -0.09, 0.16, 0.09, 0.09, 0.2, col, M, bevel=0.015)
    R.box(-0.08, 0.07, 0.2, 0.08, 0.1, 0.42, col, M @ TR((0, 0.08, 0.2), (-0.12, 0, 0)) @ TR((0, -0.08, -0.2)), bevel=0.015)


def filing(R, x, y, rot, col=C("9aa0a3"), open_drawer=None):
    M = at(x, y, rot)
    w, d, h = 0.2, 0.26, 0.56
    R.box(-w / 2, -d / 2, 0, w / 2, d / 2, h, col, M, bevel=0.006, solid=True)
    for i in range(4):
        z0 = 0.02 + i * 0.135
        if open_drawer == i:
            R.box(-w / 2 + 0.01, -d / 2 - 0.16, z0, w / 2 - 0.01, -d / 2 + 0.02, z0 + 0.12, mul(col, 0.9), M)
            for j in range(4):
                R.box(-w / 2 + 0.02, -d / 2 - 0.14 + j * 0.035, z0 + 0.03, w / 2 - 0.02, -d / 2 - 0.135 + j * 0.035, z0 + 0.14, C("e8d9a8"), M)
        else:
            R.box(-w / 2 + 0.01, -d / 2 - 0.004, z0, w / 2 - 0.01, -d / 2, z0 + 0.12, mul(col, 0.92), M)
            R.box(-0.03, -d / 2 - 0.014, z0 + 0.08, 0.03, -d / 2 - 0.004, z0 + 0.095, GREY_D, M)


def water_cooler(R, x, y, rot=0.0):
    M = at(x, y, rot)
    R.box(-0.08, -0.08, 0, 0.08, 0.08, 0.38, C("e6e6e2"), M, bevel=0.008, solid=True)
    R.box(-0.04, -0.085, 0.24, 0.04, -0.08, 0.3, GREY_D, M)
    R.box(-0.02, -0.1, 0.27, -0.005, -0.085, 0.285, C("3060c0"), M)
    R.box(0.005, -0.1, 0.27, 0.02, -0.085, 0.285, C("c03030"), M)
    R.cyl(0, 0, 0.38, 0.07, 0.17, C("8cc8ec"), M, 10, m="Glow")
    R.cyl(0, 0, 0.55, 0.03, 0.03, C("8cc8ec"), M, 8, m="Glow")
    R.cyl(0.11, -0.02, 0.0, 0.035, 0.12, C("8a8f94"), M, 8)


def plant(R, x, y, big=False):
    s = 1.4 if big else 1.0
    R.cyl(x, y, F, 0.07 * s, 0.13 * s, C("b5653d"), seg=8, r2=0.09 * s)
    R.cyl(x, y, F + 0.12 * s, 0.08 * s, 0.01, C("3a2a1c"), seg=8)
    rng = R.rng
    for i in range(5):
        a = i * 1.3 + rng.uniform(-0.3, 0.3)
        tip = (x + math.cos(a) * 0.12 * s, y + math.sin(a) * 0.12 * s, F + (0.4 + rng.uniform(-0.08, 0.1)) * s)
        R.bar((x, y, F + 0.12 * s), tip, 0.008, C("6b5a32"))
        R.box(-0.04, -0.012, -0.004, 0.04, 0.012, 0.004, rng.choice([C("7a8a3a"), C("8a6a2a"), C("5f7a35")]),
              TR(tip, (rng.uniform(-0.6, 0.6), 0.3, a)))
    R.solid(x - 0.08 * s, y - 0.08 * s, F, x + 0.08 * s, y + 0.08 * s, F + 0.3 * s)


def pendant(R, x, y, col=WARM):
    R.bar((x, y, CEIL), (x, y, CEIL - 0.22), 0.004, BLACK)
    R.cyl(x, y, CEIL - 0.32, 0.12, 0.1, col, seg=10, r2=0.03, m="Glow")
    R.light(x, y, CEIL - 0.36)


def panel_light(R, x, y, w=0.5, d=0.16, col=C("f4f6ee")):
    R.box(x - w / 2 - 0.02, y - d / 2 - 0.02, CEIL - 0.03, x + w / 2 + 0.02, y + d / 2 + 0.02, CEIL, C("d8d8d0"))
    R.quad_down(x - w / 2, y - d / 2, x + w / 2, y + d / 2, CEIL - 0.031, col, m="Glow")
    R.light(x, y, CEIL - 0.15)


def rubble_bits(R, cx, cy, spread, n, cols=(C("a9a49a"), C("8f8a80"), C("c8bfae"), C("9a6050"))):
    rng = R.rng
    for i in range(n):
        s = rng.uniform(0.03, 0.09)
        r = spread * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        R.box(-s, -s * 0.8, -s * 0.4, s, s * 0.8, s * 0.4, mul(rng.choice(cols), rng.uniform(0.8, 1.0)),
              TR((x, y, F + s * 0.35), (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0, 3))))


def fallen_tile(R, x, y, rot):
    """A ceiling tile come down: a dark gap above, the tile leaning on the floor, wires."""
    rng = R.rng
    R.quad_down(x - 0.24, y - 0.24, x + 0.24, y + 0.24, CEIL - 0.004, C("1c1a18"))
    for k in range(4):
        a = k * math.pi / 2
        R.box(-0.25, -0.012, -0.008, 0.25, 0.012, 0.0, C("d6d3c8"), TR((x + math.cos(a) * 0.24, y + math.sin(a) * 0.24, CEIL - 0.004), (0, 0, a + math.pi / 2)))
    R.box(-0.22, -0.22, -0.01, 0.22, 0.22, 0.01, C("d9d6cc"), TR((x + 0.12, y, F + 0.16), (0.1, -0.62, rot)))
    R.box(-0.12, -0.15, -0.01, 0.1, 0.12, 0.01, C("cfccc0"), TR((x - 0.2, y + 0.18, F + 0.012), (0, 0, rot + 0.7)))
    R.P.add(t_tube([(x, y + 0.05, CEIL), (x + 0.03, y + 0.06, CEIL - 0.25), (x + 0.08, y + 0.02, CEIL - 0.38)],
                   [0.006] * 3, 4, caps=False), None, "Furn", C("c03028"))
    R.P.add(t_tube([(x - 0.05, y - 0.04, CEIL), (x - 0.07, y - 0.08, CEIL - 0.3)], [0.006] * 2, 4, caps=False),
            None, "Furn", BLACK)
    rubble_bits(R, x + 0.05, y, 0.3, 8, (C("d9d6cc"), C("c8c4b8"), C("a9a49a")))


def papers(R, cx, cy, spread, n):
    rng = R.rng
    for i in range(n):
        r = spread * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        R.box(-0.04, -0.055, 0, 0.04, 0.055, 0.003, rng.choice([C("f4f2ec"), C("efe6c8"), C("e8eef4")]),
              TR((cx + r * math.cos(a), cy + r * math.sin(a), F + 0.003 + i * 0.0006), (0, 0, rng.uniform(0, 3.14))))


def can_row(R, x0, x1, y, z, M, cols, r=0.028, h=0.075, gap=0.004):
    rng = R.rng
    c = rng.choice(cols)
    u = x0 + r
    while u < x1 - r:
        if rng.random() < 0.12:
            u += 2 * r + gap
            continue
        R.cyl(u, y, z, r, h, c, M, 6)
        u += 2 * r + gap


def box_row(R, x0, x1, y0, y1, z, M, cols, w=(0.05, 0.08), h=(0.09, 0.14)):
    rng = R.rng
    c = rng.choice(cols)
    u = x0
    while True:
        bw = rng.uniform(*w)
        if u + bw > x1:
            break
        if rng.random() < 0.1:
            u += bw
            continue
        R.box(u, y0, z, u + bw - 0.006, y1, z + rng.uniform(*h), c, M)
        u += bw


GOODS = [C("d8402f"), C("2f7fd0"), C("f0c419"), C("3aa35a"), C("f08a2a"), C("9b59b6"), C("e8e2d0")]


def shop_shelf(R, x, y, rot, w=1.2, h=0.8, d=0.24, double=False, col=C("b9bec2"), rng=None):
    """Steel shelving with groceries; back at local +y (or goods both sides)."""
    M = at(x, y, rot)
    y0 = -d / 2
    y1 = d / 2
    for sx in (-w / 2, w / 2 - 0.025):
        R.box(sx, y0, 0, sx + 0.025, y1, h, mul(col, 0.85), M)
    R.box(-w / 2, -0.008 if double else y1 - 0.01, 0.04, w / 2, 0.008 if double else y1, h - 0.02, mul(col, 0.7), M)
    levels = 4
    for i in range(levels):
        z = 0.03 + i * (h - 0.05) / (levels - 0.6)
        R.box(-w / 2 + 0.025, y0, z, w / 2 - 0.025, y1, z + 0.018, col, M)
        sides = [(y0 + 0.02, -0.02)] if double else [(y0 + 0.02, y1 - 0.03)]
        if double:
            sides.append((0.02, y1 - 0.02))
        for (a, b) in sides:
            if R.rng.random() < 0.55:
                can_row(R, -w / 2 + 0.03, w / 2 - 0.03, (a + b) / 2, z + 0.018, M, GOODS)
            else:
                box_row(R, -w / 2 + 0.03, w / 2 - 0.03, a, b, z + 0.018, M, GOODS)
    R.box(-w / 2, y0 - 0.005, 0, w / 2, y1 + 0.005, 0.03, mul(col, 0.6), M)
    R.solid(-w / 2, y0, 0, w / 2, y1, h, M)


def spilled_cans(R, cx, cy, spread, n):
    rng = R.rng
    for i in range(n):
        r = spread * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        R.cyl(0, 0, -0.028, 0.028, 0.075, rng.choice(GOODS), TR((cx + r * math.cos(a), cy + r * math.sin(a), F + 0.028), (math.pi / 2, 0, rng.uniform(0, 3.14))), 6)


def register(R, M):
    R.box(-0.09, -0.07, 0, 0.09, 0.08, 0.05, GREY_D, M, bevel=0.006)
    R.box(-0.08, -0.08, 0.005, 0.08, -0.07, 0.04, mul(GREY_D, 0.8), M)
    R.box(-0.07, -0.04, 0.05, 0.07, 0.06, 0.08, mul(GREY_D, 1.2), M @ TR((0, 0, 0.05), (0.35, 0, 0)) @ TR((0, 0, -0.05)))
    R.box(-0.06, 0.04, 0.05, 0.06, 0.07, 0.14, GREY_D, M)
    R.quad_front(-0.05, 0.09, 0.05, 0.13, 0.039, C("7dff9a"), M, m="Glow")
    for i in range(3):
        for j in range(3):
            R.box(-0.05 + i * 0.03, -0.03 + j * 0.025, 0.08, -0.03 + i * 0.03, -0.012 + j * 0.025, 0.088, WHITE,
                  M @ TR((0, 0, 0.05), (0.35, 0, 0)) @ TR((0, 0, -0.05)))


def shop_counter(R, x, y, rot, w=0.9, front=C("c0392b")):
    """Customer side at local -y."""
    M = at(x, y, rot)
    d = 0.3
    R.box(-w / 2, -d / 2, 0, w / 2, d / 2, 0.4, front, M, solid=True)
    R.box(-w / 2 - 0.02, -d / 2 - 0.03, 0.4, w / 2 + 0.02, d / 2 + 0.01, 0.42, C("e9e4d8"), M, bevel=0.006)
    R.box(-w / 2 + 0.02, -d / 2 - 0.005, 0.05, w / 2 - 0.02, -d / 2, 0.08, mul(front, 0.7), M)
    for i in range(int(w / 0.2)):
        R.box(-w / 2 + 0.05 + i * 0.2, -d / 2 - 0.005, 0.12, -w / 2 + 0.17 + i * 0.2, -d / 2, 0.36, mul(front, 1.15), M)
    register(R, M @ TR((w / 2 - 0.16, 0.02, 0.42), (0, 0, math.pi)))
    # candy jars + a bell
    for i, c in enumerate([C("ff6f91"), C("ffd166"), C("06d6a0")]):
        R.cyl(-w / 2 + 0.1 + i * 0.09, -0.05, 0.42, 0.035, 0.07, c, M, 8)
        R.cyl(-w / 2 + 0.1 + i * 0.09, -0.05, 0.49, 0.037, 0.015, C("d0d0d0"), M, 8)
    R.cyl(0.0, -0.08, 0.42, 0.03, 0.025, C("d4b030"), M, 8, r2=0.006)


def drinks_fridge(R, x, y, rot, w=0.7, h=0.85):
    """Glass-fronted chiller, lit inside; back at local +y."""
    M = at(x, y, rot)
    d = 0.26
    R.box(-w / 2, -d / 2, 0, w / 2, d / 2, 0.06, GREY_D, M)
    R.box(-w / 2, -d / 2, h - 0.1, w / 2, d / 2, h, C("2c6eb5"), M)
    R.box(-w / 2 + 0.05, -d / 2 - 0.004, h - 0.085, w / 2 - 0.05, -d / 2, h - 0.03, C("f2f2f2"), M)
    R.box(-w / 2, -d / 2, 0.06, -w / 2 + 0.03, d / 2, h - 0.1, C("dcdcdc"), M)
    R.box(w / 2 - 0.03, -d / 2, 0.06, w / 2, d / 2, h - 0.1, C("dcdcdc"), M)
    R.box(-0.012, -d / 2, 0.06, 0.012, -d / 2 + 0.02, h - 0.1, C("dcdcdc"), M)
    R.quad_front(-w / 2 + 0.03, 0.06, w / 2 - 0.03, h - 0.1, d / 2 - 0.02, COOL, M, m="Glow")
    for i in range(4):
        z = 0.08 + i * (h - 0.2) / 4
        R.box(-w / 2 + 0.03, -d / 2 + 0.03, z, w / 2 - 0.03, d / 2 - 0.02, z + 0.01, C("c8d0d4"), M)
        u = -w / 2 + 0.06
        c = R.rng.choice(GOODS)
        while u < w / 2 - 0.05:
            if R.rng.random() > 0.15:
                R.cyl(u, -0.02, z + 0.01, 0.022, 0.12, c, M, 6)
            u += 0.05
    R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, h, M)


def elevator(R, x, rot_y=IN):
    """Lift doors on the back wall at x (wall at +y)."""
    M = at(x, rot_y, 0.0)
    R.box(-0.26, -0.03, 0, 0.26, 0.0, 0.84, C("6b6f73"), M)
    R.box(-0.21, -0.035, 0.0, -0.003, -0.03, 0.76, C("b8bec4"), M)
    R.box(0.003, -0.035, 0.0, 0.21, -0.03, 0.76, C("b8bec4"), M)
    R.box(-0.08, -0.04, 0.78, 0.08, -0.03, 0.82, BLACK, M)
    R.quad_front(-0.06, 0.79, 0.06, 0.81, -0.041, C("ff7040"), M, m="Glow")
    R.box(0.3, -0.03, 0.36, 0.36, 0.0, 0.46, C("6b6f73"), M)
    R.quad_front(0.315, 0.39, 0.345, 0.43, -0.031, C("ffcc66"), M, m="Glow")


def reception(R, x, y, rot, col=C("c9a77a")):
    """Visitor side at local -y."""
    M = at(x, y, rot)
    w, d = 0.95, 0.3
    R.box(-w / 2, -d / 2, 0, w / 2, -d / 2 + 0.06, 0.4, col, M, solid=True)
    R.box(-w / 2 - 0.02, -d / 2 - 0.04, 0.4, w / 2 + 0.02, -d / 2 + 0.1, 0.42, C("3a3a3c"), M)
    R.box(-w / 2, -d / 2, 0, -w / 2 + 0.06, d / 2, 0.4, col, M, solid=True)
    R.box(-w / 2, -d / 2 + 0.06, 0.27, w / 2, d / 2, 0.29, C("e0dccf"), M)
    R.box(-w / 2 + 0.1, -d / 2 - 0.004, 0.12, w / 2 - 0.1, -d / 2, 0.3, mul(col, 1.2), M)
    R.box(-0.14, 0.0, 0.29, 0.14, 0.025, 0.47, BLACK, M, bevel=0.005)
    R.quad_front(-0.13, 0.30, 0.13, 0.46, -0.0015, SCREEN, M @ TR((0, 0.0, 0), (0, 0, 0)), m="Glow")
    R.cyl(0.32, -0.12, 0.42, 0.025, 0.02, C("d4b030"), M, 8, r2=0.006)
    office_chair(R, *(M @ Vector((0.05, 0.18, 0)))[:2], rot + math.pi)


def whiteboard(R, x, y, rot):
    M = at(x, y, rot)
    for sx in (-0.25, 0.25):
        R.bar((sx, 0.04, 0), (sx, 0.0, 0.75), 0.012, GREY, M)
        R.bar((sx, -0.06, 0), (sx, 0.0, 0.5), 0.01, GREY, M)
    R.box(-0.3, -0.015, 0.36, 0.3, 0.0, 0.74, GREY, M)
    R.quad_front(-0.29, 0.37, 0.29, 0.73, -0.016, C("f7f7f2"), M)
    rng = R.rng
    for i in range(5):
        c = rng.choice([C("d03030"), C("2050c0"), C("20a050"), BLACK])
        x0 = rng.uniform(-0.25, 0.05)
        z = 0.67 - i * 0.06
        R.box(x0, -0.019, z, x0 + rng.uniform(0.08, 0.2), -0.016, z + 0.012, c, M)
    R.box(-0.29, -0.05, 0.35, 0.29, 0.0, 0.365, GREY, M)


def teddy(R, x, y, z, rot, col=C("a0703c")):
    M = TR((x, y, z), (0, 0, rot))
    R.ball(0, 0, 0.09, 0.08, col, M)
    R.ball(0, -0.01, 0.21, 0.065, col, M)
    for sx in (-1, 1):
        R.ball(sx * 0.05, 0.0, 0.27, 0.025, col, M)
        R.ball(sx * 0.08, -0.03, 0.12, 0.032, col, M)
        R.ball(sx * 0.05, -0.06, 0.03, 0.035, col, M)
    R.ball(0, -0.065, 0.2, 0.022, C("e8c9a0"), M)
    R.ball(0, -0.083, 0.205, 0.008, BLACK, M)
    for sx in (-1, 1):
        R.ball(sx * 0.025, -0.055, 0.235, 0.008, BLACK, M)
    R.box(-0.04, -0.07, 0.15, 0.04, -0.05, 0.17, C("d03040"), M)


def toy_car(R, x, y, z, rot, col):
    M = TR((x, y, z), (0, 0, rot))
    R.box(-0.04, -0.07, 0.015, 0.04, 0.07, 0.045, col, M, bevel=0.008)
    R.box(-0.03, -0.03, 0.045, 0.03, 0.03, 0.07, mul(col, 0.8), M, bevel=0.008)
    for sx in (-0.042, 0.042):
        for sy in (-0.045, 0.045):
            R.cyl(0, 0, -0.008, 0.016, 0.016, BLACK, M @ TR((sx, sy, 0.016), (0, math.pi / 2, 0)), 6)


# ---------------------------------------------------------------- rooms
def room_grocery(name, seed):
    R = Room(name, seed, upper=False)
    floor_grid(R, 0.32, 0.32, lambda i, j, r: C("e4dccb") if (i + j) % 2 else C("4f8a8b", r.uniform(0.92, 1.0)))
    shop_shelf(R, -0.4, 1.62, 0.0, w=2.6, h=0.82, d=0.26)
    shop_shelf(R, -0.45, 0.32, 0.0, w=1.6, h=0.6, d=0.3, double=True)
    drinks_fridge(R, -1.62, -0.05, -math.pi / 2, w=1.0)
    shop_counter(R, -0.95, -0.85, math.pi)
    # a shelf tipped over, its goods all over the floor
    M = TR((0.45, 1.05, F + 0.15), (0, math.radians(-78), 0.15))
    R.box(-0.15, -0.12, -0.6, 0.0, 0.12, 0.0, C("aab0b4"), M)
    spilled_cans(R, 0.2, 0.95, 0.35, 14)
    for i in range(3):
        R.box(-0.08, -0.06, 0, 0.08, 0.06, 0.1, C("b88a55"), TR((1.35 + i * 0.03, 1.55 - i * 0.12, F + i * 0.1), (0, 0, i * 0.4)))
    panel_light(R, -0.45, -0.2, 0.9, 0.12)
    panel_light(R, -0.45, 0.95, 0.9, 0.12, col=C("6a6a66"))   # this one's dead
    fallen_tile(R, 0.35, -0.35, 0.4)
    papers(R, -0.9, -0.3, 0.3, 4)
    return R.finish()


def room_toys(name, seed):
    R = Room(name, seed, upper=False)
    floor_grid(R, 0.45, 0.45, lambda i, j, r: [C("f2c14e"), C("e86a5b"), C("5fa8d3"), C("7cc47f")][(i * 3 + j) % 4])
    # shelves of toy boxes along the back and left walls
    for (x, y, rot, w) in [(-0.35, 1.62, 0.0, 2.6), (-1.62, 0.25, -math.pi / 2, 1.5)]:
        M = at(x, y, rot)
        d, h = 0.26, 0.82
        R.box(-w / 2, -d / 2, 0, w / 2, d / 2, 0.03, WOOD_D, M)
        R.box(-w / 2, d / 2 - 0.02, 0, w / 2, d / 2, h, C("f4e3c3"), M)
        for i in range(4):
            z = 0.03 + i * 0.2
            R.box(-w / 2, -d / 2, z, w / 2, d / 2, z + 0.02, C("e8a33d"), M)
            box_row(R, -w / 2 + 0.03, w / 2 - 0.03, -d / 2 + 0.03, d / 2 - 0.04, z + 0.02, M,
                    [C("e63946"), C("457b9d"), C("ffb703"), C("8ac926"), C("ff70a6"), C("6a4c93")], (0.08, 0.16), (0.08, 0.15))
        R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, h, M)
    shop_counter(R, -0.95, -0.85, math.pi, front=C("3d7dca"))
    # display table: balls, blocks, a big teddy
    R.box(-0.35, -0.25, 0.0, 0.35, 0.25, 0.25, C("ffd166"), at(0.05, 0.35), bevel=0.01, solid=True)
    for i, c in enumerate([C("e63946"), C("457b9d"), C("8ac926"), C("ff70a6")]):
        R.ball(-0.2 + i * 0.12, 0.25 + (i % 2) * 0.1, F + 0.25 + 0.05, 0.05, c)
    for i in range(6):
        R.box(-0.025, -0.025, 0, 0.025, 0.025, 0.05, GOODS[i % 6], TR((0.12 + (i % 3) * 0.055, 0.45 + (i // 3) * 0.055, F + 0.25 + (0.05 if i == 4 else 0)), (0, 0, i * 0.3)))
    teddy(R, 0.05, 0.3, F + 0.25, math.pi + 0.2, C("a0703c"))
    teddy(R, -1.35, -0.25, F, -2.2, C("e8a3b8"))
    toy_car(R, 0.6, -0.1, F, 0.8, C("e63946"))
    toy_car(R, -0.3, -0.45, F, 2.3, C("457b9d"))
    R.ball(0.75, 0.55, F + 0.07, 0.07, C("e63946"))
    R.ball(-0.6, 1.0, F + 0.06, 0.06, C("8ac926"))
    # rocking horse
    M = at(0.6, 1.1, 0.6)
    R.box(-0.03, -0.14, 0.0, 0.03, 0.14, 0.03, C("c0392b"), M @ TR((0, 0, 0.0), (0, 0, 0)))
    R.box(-0.06, -0.12, 0.12, 0.06, 0.12, 0.2, C("f4e3c3"), M, bevel=0.02)
    R.box(-0.04, -0.17, 0.18, 0.04, -0.09, 0.32, C("f4e3c3"), M @ TR((0, -0.12, 0.2), (0.4, 0, 0)) @ TR((0, 0.12, -0.2)), bevel=0.015)
    for sy in (-0.09, 0.09):
        for sx in (-0.04, 0.04):
            R.bar((sx, sy, 0.03), (sx, sy * 0.8, 0.13), 0.012, C("f4e3c3"), M)
    R.box(-0.065, -0.05, 0.2, 0.065, 0.05, 0.215, C("c0392b"), M)
    panel_light(R, -0.45, -0.1, 0.9, 0.12, col=C("fff2d0"))
    panel_light(R, -0.45, 1.0, 0.9, 0.12)
    fallen_tile(R, 0.55, -0.45, 1.1)
    rubble_bits(R, -1.3, 1.2, 0.25, 6)
    return R.finish()


def room_lobby(name, seed):
    R = Room(name, seed, upper=False)
    floor_grid(R, 0.88, 0.88, lambda i, j, r: C("cfc8b8", r.uniform(0.9, 1.0)) if (i + j) % 2 else C("b8b0a0", r.uniform(0.9, 1.0)))
    reception(R, -1.0, -0.05, math.pi)
    elevator(R, -0.85)
    elevator(R, 0.0)
    # waiting area
    sofa(R, -1.55, 1.0, -math.pi / 2, C("6b7f99"), w=0.85, d=0.38)
    coffee_table(R, -1.0, 1.0, math.pi / 2, w=0.4, d=0.24)
    sofa(R, 0.35, 0.75, math.pi / 2 + 0.25, C("6b7f99"), w=0.45, d=0.38)
    plant(R, -1.55, -1.25, big=True)
    plant(R, 0.75, 1.5, big=True)
    plant(R, 1.4, 1.55)
    water_cooler(R, -0.4, 1.55)
    # a filing cabinet dumped in the hall, papers everywhere
    filing(R, 0.55, 0.15, 2.4, open_drawer=1)
    papers(R, 0.1, 0.0, 0.5, 10)
    papers(R, -1.0, 0.5, 0.3, 5)
    office_chair(R, -0.45, 0.45, 0.8, tipped=True)
    panel_light(R, -0.8, -0.4, 0.6, 0.16)
    panel_light(R, -0.8, 0.9, 0.6, 0.16)
    panel_light(R, 0.35, 0.25, 0.6, 0.16, col=C("5a5a58"))
    fallen_tile(R, 0.3, -0.5, 2.0)
    return R.finish()


def room_living(name, seed):
    R = Room(name, seed, upper=True)
    boards = [C("8a5a3a"), C("7d5035"), C("94643f"), C("845637")]
    floor_grid(R, 0.7, 0.14, lambda i, j, r: mul(boards[(i * 7 + j * 3) % 4], r.uniform(0.92, 1.05)), stagger=0.5)
    rug(R, -0.6, -0.55, 0.75, 0.55, C("9c3b2a"), C("d9b26a"), C("c86a3a"))
    sofa(R, 0.05, 0.8, 0.0, C("4f7a6a"))
    cushion(R, -0.3, 0.72, F + 0.26, 0.4, C("e0b040"))
    cushion(R, 0.36, 0.72, F + 0.26, -0.3, C("d06050"))
    tv_stand(R, 0.05, -0.98, math.pi)
    coffee_table(R, 0.05, 0.05, 0.0)
    floor_lamp(R, -0.72, 1.2)
    bookshelf(R, -1.65, 0.95, -math.pi / 2, w=1.0)
    kitchen(R, -0.2, 0.95, 1.76, 0.0)
    fridge(R, 1.35, 1.58, 0.0)
    plant(R, 0.82, -0.85)
    pendant(R, 0.05, -0.1)
    # toys on the rug
    toy_car(R, -0.3, -0.25, F + 0.011, 0.6, C("e63946"))
    R.ball(0.5, -0.35, F + 0.06, 0.05, C("ffb703"))
    rubble_bits(R, -1.35, 1.5, 0.2, 5)
    return R.finish()


def room_bedroom(name, seed):
    R = Room(name, seed, upper=True)
    floor_grid(R, 0.88, 0.88, lambda i, j, r: C("5d6b7a", r.uniform(0.9, 1.0)))
    bed(R, 0.1, 1.28, 0.0, C("3f7fbf"))
    bedside(R, -0.33, 1.6, 0.0)
    bedside(R, 0.53, 1.6, 0.0, lamp=False)
    round_rug(R, 0.1, 0.3, 0.42, C("e8c547"), C("d06a4a"))
    wardrobe(R, -1.6, 1.15, -math.pi / 2)
    dining(R, 0.35, -0.6, 0.0, w=0.5, d=0.32)
    # toy box with a teddy peeking out
    R.box(-0.18, -0.12, 0, 0.18, 0.12, 0.2, C("c0392b"), at(-0.62, 0.55, 0.2), bevel=0.01, solid=True)
    R.box(-0.18, -0.12, 0, 0.18, 0.12, 0.02, C("e0a030"), at(-0.62, 0.55, 0.2) @ TR((0, 0.12, 0.2), (-1.2, 0, 0)) @ TR((0, -0.12, 0)))
    teddy(R, -0.62, 0.55, F + 0.12, math.pi, C("c89058"))
    wardrobe(R, 1.4, 1.6, 0.0, w=0.62, d=0.26, h=0.36, col=WOOD_L)
    table_lamp(R, 1.55, 1.6, F + 0.36)
    pendant(R, 0.1, 0.2, col=C("ffe0b0"))
    fallen_tile(R, -0.4, -0.55, 0.7)
    return R.finish()


def room_office(name, seed):
    R = Room(name, seed, upper=True)
    floor_grid(R, 0.44, 0.44, lambda i, j, r: C("6b7078", 1.0 if (i + j) % 2 else 0.9))
    for (x, y, rot) in [(-0.45, -0.62, math.pi), (0.35, -0.62, math.pi), (-0.45, 0.35, 0.0), (0.35, 0.35, 0.0)]:
        desk(R, x, y, rot + math.pi)
    office_chair(R, -0.45, -0.95, 0.2)
    office_chair(R, 0.35, -0.98, -0.3)
    office_chair(R, -0.45, 0.72, math.pi + 0.3)
    office_chair(R, 0.75, 0.95, 1.4, tipped=True)
    for i in range(4):
        filing(R, -0.75 + i * 0.22, 1.6, 0.0, open_drawer=2 if i == 1 else None)
    water_cooler(R, -1.55, 0.4)
    plant(R, -1.55, 1.55, big=True)
    filing(R, -1.6, 0.95, -math.pi / 2)
    filing(R, -1.6, 1.17, -math.pi / 2)
    filing(R, 1.6, 1.6, 0.0)
    papers(R, 0.1, -0.1, 0.45, 9)
    panel_light(R, -0.05, -0.62, 0.7, 0.16)
    panel_light(R, -0.05, 0.4, 0.7, 0.16)
    return R.finish()


def room_meeting(name, seed):
    R = Room(name, seed, upper=True)
    floor_grid(R, 0.44, 0.44, lambda i, j, r: C("4a5a73", 1.0 if (i + j) % 2 else 0.92))
    M = at(0.05, 0.3, math.pi / 2)
    w, d = 1.2, 0.5
    R.box(-w / 2, -d / 2, 0.28, w / 2, d / 2, 0.305, C("6e4b33"), M, bevel=0.01)
    R.box(-w / 2 + 0.15, -0.06, 0, w / 2 - 0.15, 0.06, 0.28, GREY_D, M)
    R.solid(-w / 2, -d / 2, 0, w / 2, d / 2, 0.305, M)
    for i in range(3):
        u = -0.4 + i * 0.4
        for s in (-1, 1):
            p = M @ Vector((u, s * (d / 2 + 0.12), 0))
            office_chair(R, p.x, p.y, (math.pi / 2 if s > 0 else -math.pi / 2) + math.pi / 2 + R.rng.uniform(-0.4, 0.4), C("7a2e2e"))
        R.box(-0.05, -0.04, 0.305, 0.05, 0.04, 0.308, C("f4f2ec"), M @ TR((u, -0.12, 0), (0, 0, 0.2)))
    R.cyl(0.05, 0.3, F + 0.305, 0.06, 0.03, BLACK, seg=8)
    whiteboard(R, 0.1, 1.5, 0.0)
    for i in range(5):
        filing(R, -1.62, 0.45 + i * 0.22, -math.pi / 2, col=C("7d8487"))
    water_cooler(R, 1.5, 1.55)
    plant(R, -0.75, -1.0, big=True)
    fallen_tile(R, 0.6, -0.55, 0.3)
    rubble_bits(R, 0.5, -0.4, 0.3, 6)
    panel_light(R, 0.05, -0.2, 0.7, 0.16)
    panel_light(R, 0.05, 0.85, 0.7, 0.16)
    return R.finish()


def room_wreck(name, seed):
    R = Room(name, seed, upper=True)
    bare_floor(R, C("8f8a80"))
    rng = R.rng
    # heaps of fallen ceiling + a sofa on its back + broken table
    rubble_bits(R, -0.3, 0.9, 0.55, 30)
    rubble_bits(R, 0.5, -0.3, 0.35, 14)
    M = TR((0.3, 1.25, F + 0.2), (math.radians(-80), 0, 0.15))
    R.box(-0.45, -0.2, -0.2, 0.45, 0.2, 0.0, C("7a5a4a"), M)
    R.box(-0.45, 0.1, -0.2, 0.45, 0.2, 0.18, C("6a4a3a"), M)
    R.solid(-0.1, 1.0, F, 0.75, 1.5, F + 0.4)
    M = TR((-0.35, -0.2, F + 0.08), (0.0, math.radians(18), 0.6))
    R.box(-0.28, -0.16, 0.0, 0.28, 0.16, 0.025, WOOD_L, M)
    R.bar((-0.5, -0.4, F + 0.01), (-0.3, -0.25, F + 0.16), 0.018, WOOD)
    for i in range(4):
        R.box(-0.35, -0.025, 0, 0.35, 0.025, 0.02, mul(WOOD, rng.uniform(0.7, 1.0)),
              TR((rng.uniform(-0.6, 0.7), rng.uniform(-0.9, 1.4), F + 0.01 + i * 0.02), (0, rng.uniform(-0.1, 0.1), rng.uniform(0, 3))))
    # an old mattress, a barrel, a chair
    R.box(-0.3, -0.45, 0, 0.3, 0.45, 0.07, C("c9bfa0"), at(-1.35, 1.1, 0.2), bevel=0.02)
    R.cyl(1.35, 1.5, F, 0.12, 0.2, C("8a4a2a"), seg=10)
    chair(R, 0.7, 0.4, 1.1, tipped=True)
    fallen_tile(R, -0.5, 0.0, 0.2)
    fallen_tile(R, 0.4, 0.55, 1.4)
    papers(R, 0.0, -0.6, 0.5, 8)
    # the light still works, just about
    R.bar((0.1, -0.2, CEIL), (0.12, -0.2, CEIL - 0.42), 0.004, BLACK)
    R.ball(0.12, -0.2, CEIL - 0.45, 0.035, WARM, m="Glow")
    R.light(0.12, -0.2, CEIL - 0.45)
    return R.finish()


# ---------------------------------------------------------------- structure
def slab_boxes(P, s, z0, z1, top="Concrete", side="Concrete", bottom="Plaster", hole=True, name=None):
    hx0, hy0, hx1, hy1 = HOLE
    rects = [(-s, hy1, s, s), (hx1, -s, s, hy1), (-s, -s, hx1, hy0)] if hole else [(-s, -s, s, s)]
    for (a, b, c, d) in rects:
        P.add(t_box_faces(a, b, z0, c, d, z1), None, [side, top, bottom], 0.9)
        if name:
            solid(name, a, b, z0, c, d, z1)


def rails(P, name, z=F):
    """Railing round the stairwell hole (open at the front where the stair arrives)."""
    hx0, hy0, hx1, hy1 = HOLE
    m = "Metal"
    for y in (hy0 + 0.05, (hy0 + hy1) / 2, hy1):
        P.add(t_bar((hx1 + 0.02, y, z), (hx1 + 0.02, y, z + 0.3), 0.015, sides=5), None, m, 0.8)
    for x in (-1.7, (hx1 - 1.7) / 2):
        P.add(t_bar((x, hy1 + 0.02, z), (x, hy1 + 0.02, z + 0.3), 0.015, sides=5), None, m, 0.8)
    P.add(t_bar((hx1 + 0.02, hy0 + 0.05, z + 0.3), (hx1 + 0.02, hy1 + 0.02, z + 0.3), 0.02, sides=6), None, "TrimTeal", 0.9)
    P.add(t_bar((hx1 + 0.02, hy1 + 0.02, z + 0.3), (-IN, hy1 + 0.02, z + 0.3), 0.02, sides=6), None, "TrimTeal", 0.9)
    P.add(t_bar((hx1 + 0.02, hy0 + 0.05, z + 0.15), (hx1 + 0.02, hy1 + 0.02, z + 0.15), 0.01, sides=5), None, m, 0.8)
    P.add(t_bar((hx1 + 0.02, hy1 + 0.02, z + 0.15), (-IN, hy1 + 0.02, z + 0.15), 0.01, sides=5), None, m, 0.8)
    solid(name, hx1, hy0 + 0.05, z, hx1 + 0.04, hy1 + 0.04, z + 0.32)
    solid(name, -IN, hy1, z, hx1 + 0.04, hy1 + 0.04, z + 0.32)


def in_slab():
    """Floor slab of an upper storey, with the stairwell hole and its railing."""
    P = PieceIn("In_Slab", K.grime_building())
    slab_boxes(P, 1.79, 0.0, F, name="In_Slab")
    hx0, hy0, hx1, hy1 = HOLE
    # broken-off edge trim inside the hole
    P.add(t_box(hx1, hy0, 0.0, hx1 + 0.02, hy1, F + 0.005), None, "Concrete", 0.7)
    rails(P, "In_Slab")
    return P.finish()


def in_stair():
    P = PieceIn("In_Stair", K.grime_building())
    x0, x1 = STAIR
    d = 2.2 / STEPS
    rise = H / STEPS
    for i in range(STEPS):
        y0 = STEP_Y0 + i * d
        z1 = F + (i + 1) * rise
        P.add(t_box_faces(x0, y0, F, x1, y0 + d + 0.002, z1), None, ["Concrete", "Concrete", "Concrete"], 0.9 if i % 2 else 0.85)
        # worn nosing
        P.add(t_box(x0 + 0.02, y0 - 0.012, z1 - 0.02, x1 - 0.02, y0 + 0.01, z1 + 0.004), None, "Metal", 0.6)
    # banister on the open side
    bx = x0 - 0.015
    for i in range(0, STEPS, 2):
        y = STEP_Y0 + (i + 0.5) * d
        z = F + (i + 1) * rise
        P.add(t_bar((bx, y, z), (bx, y, z + 0.32), 0.012, sides=5), None, "Metal", 0.8)
    P.add(t_bar((bx, STEP_Y0 + 0.5 * d, F + rise + 0.32), (bx, STEP_Y0 + (STEPS - 0.5) * d, F + H + 0.32), 0.02, sides=6),
          None, "TrimTeal", 0.9)
    COLL.setdefault("In_Stair", {"boxes": []})["ramps"] = [[x0, x1, round(F, 3), round(F + H, 3),
                                                             round(-STAIR_Y[0], 3), round(-STAIR_Y[1], 3),
                                                             round(-(STEP_Y0 + STEPS * d), 3)]]
    return P.finish()


SIDE_KINDS = {
    "brick": ["glass", "broken", "boarded", "glass", "missing", "glass", "broken", "glass", "boarded"],
    "conc": ["broken", "glass", "missing", "glass", "boarded", "glass", "glass", "broken", "missing"],
    "office": ["glass", "broken", "glass", "missing", "glass", "boarded", "glass", "glass", "broken"],
}


def ground_in(name, fam, seed, layout, sign):
    """Ground storey with a shopfront and an open door at the front, hollow inside."""
    rng = random.Random(seed)
    P = PieceIn(name, K.grime_building(ground=True))
    wall = {"brick": "Brick", "conc": "Plaster", "office": "Concrete"}[fam]
    K.shopfront(P, 0, fam, layout, rng, sign)
    for k in (0, 3):
        K.corner_L(P, k, 0, 0.9, 0.4, 0.4, wall if fam != "office" else "Concrete", depth=0.4, tint=0.95)
    if fam == "office":
        P.box(-0.55, -EDGE, 0, -0.42, -1.62, 0.9, "Concrete", 0.95)
        P.box(0.42, -EDGE, 0, 0.55, -1.62, 0.9, "Concrete", 0.95)
    fascia = wall if fam != "office" else "Concrete"
    P.box(-1.96, -1.96, 0.9, 1.96, -1.62, 1.15, fascia, 0.92)
    P.box(-EDGE, -EDGE, 1.15, EDGE, -1.62, H, "Concrete", 0.95, bevel=0.015 if fam != "office" else 0)
    P.box(-1.6, -1.62, 0.9, 1.6, -1.5, H, "Plaster", 0.95)     # inside face above the shopfront
    # the other three sides: walls with windows, like the floors above
    f = K.FAM["brick" if fam == "brick" else "conc"]
    kinds = SIDE_KINDS[fam]
    for k in (1, 2, 3):
        wins = []
        for i, (a, b) in enumerate(f["wins"]):
            wins.append((a, b, f["wz"][0], f["wz"][1], kinds[(k * 3 + i) % len(kinds)]))
        pb = t_panel(-WO, WO - T, 0, H, -WO, -WO + T, [w[:4] for w in wins], extra_z=[f["wz"][0] - 0.3], caps=("ends",))
        P.add(pb, side_M(k), [wall, "Interior"], K.soot_tint(wins))
        for (a, b, c, d, kind) in wins:
            K.window(P, k, a, b, c, d, kind, -WO, rng, "brick" if fam == "brick" else "conc")
        if fam == "brick":
            for i, (z0, z1) in enumerate([(0.07, 0.42), (0.44, 0.79), (0.81, 1.16)]):
                a, b = (0.34, 0.22) if i % 2 == 0 else (0.22, 0.34)
                if k in (1, 2):
                    K.corner_L(P, k, z0, z1, a, b, "Concrete", depth=0.12, tint=0.92)
        elif k in (1, 2):
            K.corner_L(P, k, 0.16, H, 0.26, 0.26, "Concrete", depth=0.26, tint=0.95)
    # plinth band round the sides and back
    for k in (1, 2, 3):
        P.box(-WO, -1.97, 0, WO, -WO + 0.02, 0.1, "Concrete", 0.8, M=side_M(k))
    # floor
    P.add(t_box_faces(-1.78, -1.62, 0.0, 1.78, 1.78, F), None, ["Concrete", "Concrete", "Concrete"], 0.85)
    # door leaf swung right open against the wall inside
    a, b = (0.42, 0.92) if fam != "office" else (-0.42, 0.42)
    leaf_mat = layout.get("door_mat", "Trim")
    if fam != "office":
        P.add(t_box(-0.02, 0.0, 0.0, 0.02, b - a - 0.02, 0.78), TR((b + 0.03, -1.5, F + 0.005), (0, 0, 0.12)), leaf_mat, 0.85)
        P.box(b + 0.01, -1.5 + 0.15, F + 0.35, b + 0.05, -1.5 + 0.2, F + 0.38, "Metal", 0.7)
    # threshold: a low ramp so you walk (not hop) in over the floor slab
    P.add(t_prism([(a + 0.02, -1.5, 0.0), (a + 0.02, -1.5, F), (a + 0.02, -1.76, 0.0)], (b - a - 0.04, 0, 0)), None, "Metal", 0.7)
    COLL.setdefault(name, {"boxes": []})["ramps"] = [[a, b, 0.0, F, 1.78, 1.5, 1.3]]
    # collision: walls with a doorway
    dh = 0.8 if fam != "office" else 0.86
    solid(name, -EDGE, -EDGE, 0, a, -1.5, H)
    solid(name, b, -EDGE, 0, EDGE, -1.5, H)
    solid(name, a, -EDGE, dh, b, -1.5, H)
    solid(name, IN, -1.5, 0, EDGE, EDGE, H)
    solid(name, -EDGE, -1.5, 0, -IN, EDGE, H)
    solid(name, -IN, IN, 0, IN, EDGE, H)
    solid(name, -IN, -1.5, 0, IN, IN, F)
    return P.finish()


def upper_in(name, fam, seed, kinds):
    """An upper storey shell: the kit's floor module, hollow, with plaster inside."""
    saved = (K.Piece, K.interior_core)
    K.Piece = PieceIn
    K.interior_core = lambda *a, **k: None
    try:
        if fam == "office":
            ob = K.office_floor(name, seed, kinds)
        else:
            ob = K.floor_module(name, fam, seed, kinds)
    finally:
        K.Piece, K.interior_core = saved
    inner = 1.78 if fam == "office" else IN
    solid(name, inner, -EDGE, 0, EDGE, EDGE, H)
    solid(name, -EDGE, -EDGE, 0, -inner, EDGE, H)
    solid(name, -inner, inner, 0, inner, EDGE, H)
    solid(name, -inner, -EDGE, 0, inner, -inner, H)
    return ob


def roof_in(name, fam, seed):
    """Flat roof you can walk out onto: a stair bulkhead over the stairwell, clutter round it."""
    rng = random.Random(seed)
    P = PieceIn(name, K.grime_building(base=1.0))
    wall = {"brick": "Brick", "conc": "Plaster", "office": "Concrete"}[fam]
    slab_boxes(P, WO, 0.0, F, name=name)
    ph, pt = 0.36, 0.12
    for k in range(4):
        top, xu = None, []
        if fam != "office" and k == (seed % 4) and k != 0:
            top, xu = K.profile([(-WO, ph), (-0.7, ph), (-0.5, 0.18), (-0.2, 0.12), (0.15, 0.22), (0.35, ph), (WO, ph)])
        pb = t_panel(-WO, WO - pt, 0.0, ph, -WO, -WO + pt, [], top=top, extra_u=xu, caps=("ends", "top"))
        P.add(pb, side_M(k), [wall, wall], 1.0)
        cm = "Concrete" if fam != "office" else "Metal"
        if top is None:
            P.add(t_box(-EDGE, -EDGE, ph, EDGE - 0.001 - 0.18, -WO + pt + 0.02, ph + 0.06, 0.012), side_M(k), cm, 0.95)
        else:
            for (u0, u1) in [(-EDGE, -0.7), (0.35, EDGE - 0.18)]:
                P.add(t_box(u0, -EDGE, ph, u1, -WO + pt + 0.02, ph + 0.06, 0.012), side_M(k), "Concrete", 0.95)
        P.add(t_box(EDGE - 0.18, -EDGE, ph, EDGE, -WO + pt + 0.02, ph + 0.06, 0.0), side_M(k), cm, 0.95)
    if fam != "office":
        K.ring(P, 0, 0.12, EDGE, WO - 0.02, "Concrete", 0.95)
    else:
        K.ring(P, 0, 0.38, EDGE, WO - 0.02, "Concrete", 0.95)
    solid(name, WO - pt, -EDGE, 0, EDGE, EDGE, ph + 0.06)
    solid(name, -EDGE, -EDGE, 0, -WO + pt, EDGE, ph + 0.06)
    solid(name, -EDGE, WO - pt, 0, EDGE, EDGE, ph + 0.06)
    solid(name, -EDGE, -EDGE, 0, EDGE, -WO + pt, ph + 0.06)
    # stair bulkhead: open at the front, where the stair comes up
    hx0, hy0, hx1, hy1 = HOLE
    bz = 0.92
    bwall = wall
    P.box(hx1, hy0, 0.0, hx1 + 0.1, hy1 + 0.12, bz, bwall, lambda p: 0.75 + 0.25 * sstep(p.z / 0.5))
    P.box(-1.8, hy1, 0.0, hx1 + 0.1, hy1 + 0.12, bz, bwall, lambda p: 0.75 + 0.25 * sstep(p.z / 0.5))
    P.box(-1.8, hy0, 0.0, -1.73, hy1 + 0.12, bz, bwall, 0.9)
    P.box(-1.8, hy0 - 0.02, 0.76, hx1 + 0.1, hy0 + 0.06, bz, bwall, 0.85)
    P.box(-1.86, hy0 - 0.08, bz, hx1 + 0.16, hy1 + 0.18, bz + 0.06, "Concrete", 0.85, bevel=0.01)
    P.add(t_quad([(-1.8, hy0 + 0.06, bz - 0.001), (-1.8, hy1, bz - 0.001), (hx1, hy1, bz - 0.001), (hx1, hy0 + 0.06, bz - 0.001)]),
          None, "Plaster", 0.8)
    door = "TrimTeal" if fam != "brick" else "TrimRed"
    P.add(t_box(-0.02, -0.5, 0.0, 0.02, 0.0, 0.72), TR((-1.71, hy0 - 0.02, F), (0, 0, 0.15)), door, 0.85)
    P.box(-1.66, hy0 - 0.06, 0.62, -1.6, hy0 - 0.02, 0.68, "Metal", 0.8)
    solid(name, hx1, hy0, 0.0, hx1 + 0.1, hy1 + 0.12, bz)
    solid(name, -1.8, hy1, 0.0, hx1 + 0.1, hy1 + 0.12, bz)
    solid(name, -1.86, hy0 - 0.08, bz, hx1 + 0.16, hy1 + 0.18, bz + 0.06)
    solid(name, -1.8, hy0 - 0.02, 0.76, hx1 + 0.1, hy0 + 0.06, bz)
    # clutter (clear of the bulkhead door and the front strip)
    if fam == "brick":
        tx, ty = 0.85, 0.85
        for (dx, dy) in [(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)]:
            P.add(t_bar((tx + dx, ty + dy, 0.06), (tx + dx * 0.9, ty + dy * 0.9, 0.5), 0.03, sides=4, smooth=False), None, "Rust", 0.8)
        P.add(t_box(tx - 0.38, ty - 0.38, 0.46, tx + 0.38, ty + 0.38, 0.5), None, "Rust", 0.75)
        P.add(t_cyl(0.42, 0.5, 14), TR((tx, ty, 0.5)), "Wood", 0.9)
        for z in (0.6, 0.85):
            P.add(t_cyl(0.43, 0.025, 14), TR((tx, ty, z)), "Rust", 0.7)
        P.add(t_cyl(0.46, 0.18, 14, r2=0.03), TR((tx, ty, 1.0)), "Metal", 0.75)
        solid(name, tx - 0.42, ty - 0.42, 0.0, tx + 0.42, ty + 0.42, 1.0)
        P.add(t_box(-1.5, 1.2, 0.06, -1.1, 1.6, 0.62), None, "Brick", K.soot_tint([], lambda p: 1 - 0.5 * sstep((p.z - 0.4) / 0.2)))
        P.add(t_box(-1.54, 1.16, 0.62, -1.06, 1.64, 0.68, 0.01), None, "Concrete", 0.5)
        solid(name, -1.54, 1.16, 0.0, -1.06, 1.64, 0.68)
        K.roof_clutter_ac(P, 0.9, -0.3, 0.2, rng)
        solid(name, 0.6, -0.55, 0.0, 1.2, -0.05, 0.4)
        K.dish(P, 1.3, -1.3, 0.6)
        K.antenna(P, -0.5, 1.0, 1.1, rng)
    elif fam == "conc":
        K.roof_clutter_ac(P, 0.4, 0.9, 0.0, rng)
        K.roof_clutter_ac(P, 1.1, 0.9, 0.0, rng)
        K.roof_clutter_ac(P, 1.3, 0.0, 1.57, rng)
        solid(name, 0.1, 0.7, 0.0, 1.4, 1.1, 0.4)
        solid(name, 1.1, -0.3, 0.0, 1.5, 0.3, 0.4)
        K.dish(P, -0.4, 1.4, -0.4, 0.26)
        K.antenna(P, 0.3, -0.2, 1.0, rng)
        for (x, y) in [(-0.2, 0.5), (-0.1, 0.65)]:
            P.add(t_cyl(0.05, 0.3, 8), TR((x, y, 0.06)), "Rust", 0.8)
    else:
        P.add(t_box(-0.2, 0.3, 0.06, 1.3, 1.5, 0.95, 0.015), None, "Concrete", lambda p: 0.75 + 0.25 * sstep(p.z / 0.5))
        for i in range(5):
            z = 0.25 + i * 0.12
            P.add(t_box(0.0, 0.26, z, 1.1, 0.3, z + 0.06), None, "Metal", 0.8)
        P.add(t_box(-0.26, 0.24, 0.95, 1.36, 1.56, 1.0), None, "Metal", 0.8)
        solid(name, -0.26, 0.24, 0.0, 1.36, 1.56, 1.0)
        K.roof_clutter_ac(P, 1.1, -0.6, 1.57, rng, big=True)
        solid(name, 0.8, -1.05, 0.0, 1.4, -0.15, 0.5)
        K.roof_clutter_ac(P, -1.2, 1.2, 0.0, rng)
        solid(name, -1.5, 1.0, 0.0, -0.9, 1.4, 0.4)
        K.dish(P, 0.2, -0.3, 2.5, 0.28)
        K.antenna(P, -0.5, 0.9, 1.2, rng)
    return P.finish()


# ---------------------------------------------------------------- build
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    K.mats.clear()
    objs = []
    brick_front = dict(win="broken", door="open", awning="TrimRed", torn=1)
    conc_front = dict(win="shutter", door="open", awning="TrimYellow", door_mat="TrimTeal")
    office_front = dict(win="x", door="x", office=["broken", "open", "glass"], awning=None)
    objs.append(ground_in("Brick_ShopIn", "brick", 101, brick_front, "TrimRed"))
    objs.append(ground_in("Conc_ShopIn", "conc", 102, conc_front, "TrimTeal"))
    objs.append(ground_in("Office_LobbyIn", "office", 103, office_front, "TrimTeal"))
    objs.append(upper_in("Brick_FloorIn", "brick", 104,
                         ["glass", "broken", "missing", "glass", "boarded", "glass", "broken", "missing", "glass",
                          "glass", "missing", "broken"]))
    objs.append(upper_in("Conc_FloorIn", "conc", 106,
                         ["glass", "missing", "glass", "broken", "glass", "boarded", "missing", "glass", "ac",
                          "glass", "broken", "glass"]))
    objs.append(upper_in("Office_FloorIn", "office", 108,
                         ["glass", "glass", "broken", "glass", "missing", "glass", "glass", "broken", "glass",
                          "glass", "missing", "glass", "boarded", "glass", "glass", "broken", "glass", "missing",
                          "glass", "glass", "broken", "glass", "glass", "missing"]))
    objs.append(roof_in("Brick_RoofIn", "brick", 110))
    objs.append(roof_in("Conc_RoofIn", "conc", 111))
    objs.append(roof_in("Office_RoofIn", "office", 112))
    objs.append(in_slab())
    objs.append(in_stair())
    objs.append(room_grocery("Room_Grocery", 201))
    objs.append(room_toys("Room_Toys", 202))
    objs.append(room_lobby("Room_Lobby", 203))
    objs.append(room_living("Room_Living", 204))
    objs.append(room_bedroom("Room_Bedroom", 205))
    objs.append(room_office("Room_Office", 206))
    objs.append(room_meeting("Room_Meeting", 207))
    objs.append(room_wreck("Room_Wreck", 208))
    return objs


def export(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "interiors.glb"), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_cameras=False, export_lights=False,
                              export_vertex_color="ACTIVE", export_all_vertex_colors=False)
    data = {"pieces": {}, "lights": LIGHTS,
            "layout": {"floor": F, "storey": H, "inner": IN, "hole": [HOLE[0], -HOLE[3], HOLE[2], -HOLE[1]],
                       "stair": [STAIR[0], STAIR[1], -STAIR_Y[1], -STAIR_Y[0]]}}
    for name, c in COLL.items():
        data["pieces"][name] = c
    with open(os.path.join(OUT, "interiors.json"), "w") as f:
        json.dump(data, f, indent=1)
    print("EXPORTED", os.path.join(OUT, "interiors.glb"))


def preview(objs, path):
    """Cutaway: each room in its shell with the ceiling off, seen from above."""
    K.preview_materials()
    for m in K.mats.values():
        if m.name == "Glow":
            b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            vc = m.node_tree.nodes.new("ShaderNodeVertexColor")
            vc.layer_name = "Col"
            m.node_tree.links.new(vc.outputs["Color"], b.inputs["Emission Color"])
            b.inputs["Emission Strength"].default_value = 2.0
    by = {o.name: o for o in objs}
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x, scn.render.resolution_y = (2400, 1200)
    world = bpy.data.worlds.new("W")
    scn.world = world
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.6, 0.62, 0.65, 1)
    bg.inputs["Strength"].default_value = 0.8
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object
    sun.data.energy = 2.5
    sun.rotation_euler = (math.radians(35), math.radians(-10), math.radians(-30))
    for o in objs:
        o.hide_render = True
    rooms = [("Room_Grocery", "Brick_ShopIn", False), ("Room_Toys", "Conc_ShopIn", False), ("Room_Lobby", "Office_LobbyIn", False),
             ("Room_Living", "Brick_FloorIn", True), ("Room_Bedroom", "Conc_FloorIn", True), ("Room_Office", "Office_FloorIn", True),
             ("Room_Meeting", "Office_FloorIn", True), ("Room_Wreck", "Conc_FloorIn", True)]
    for i, (room, shell, up) in enumerate(rooms):
        x, y = (i % 4) * 5.0, -(i // 4) * 5.5
        K.place_copy(by[room], (x, y, 0))
        K.place_copy(by[shell], (x, y, 0))
        if up:
            K.place_copy(by["In_Slab"], (x, y, 0))
        K.place_copy(by["In_Stair"], (x, y, 0))
    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (7.5, -16.0, 14.0)
    target = Vector((7.5, -2.8, 0.0))
    cam.rotation_euler = (target - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = 40
    scn.camera = cam
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    objs = build()
    K.report(objs)
    export(objs)
    if "preview" in argv:
        i = argv.index("preview")
        out = argv[i + 1] if len(argv) > i + 1 else os.path.join(K.RENDERS, "interiors_preview.png")
        preview(objs, out)
