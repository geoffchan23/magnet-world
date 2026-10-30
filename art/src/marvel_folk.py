# Marvel-city folk for Magnet World: people and creatures for the city after the battle.
# Toy-real collectible figures (vinyl/brick-figure feel), built from primitives with npc_kit.
#
# Run one:  blender --background --python art/src/marvel_folk.py -- civilian
# Run all:  blender --background --python art/src/marvel_folk.py -- all
# Add --fast to skip the concept/portrait render. NPC_SCRATCH=<dir> also writes review sheets.
#
# Each run writes art/characters/npc_<id>.blend, concepts/npc_<id>.png,
# assets/portraits/npc_<id>.png (320px) and assets/characters/npc_<id>.glb.
#
# Same conventions as art/src/npcs.py: Blender faces -Y, feet on z=0, L = -X; every limb is one
# node with its origin at the joint and identity rotation/scale. Each figure copies the node layout
# of the npc it replaces:
#   civilian      <- survivor     Body Head ArmL ArmR LegL LegR
#   shield_agent  <- mechanic     Body Head ArmL ArmR LegL LegR
#   nick_fury     <- trader       Body Head ArmL ArmR LegL LegR
#   lucky         <- dog          Body Head LegL LegR LegL2 LegR2 Tail (same pivots as the dog)
#   hydra_agent   <- raider       Body Head ArmL ArmR LegL LegR (blaster is part of ArmR)
#   ultron_sentry <- scrap_robot  Body Head Jaw(child of Head) ArmL ArmR LegL LegR
#   symbiote      <- slime        Body BlobTop BlobL BlobR BlobBack (same pivots as the slime)
#   spider_drone  <- spider_bot   Body Head LegL1..4 LegR1..4 (same pivots as the spider bot)
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import npc_kit
importlib.reload(npc_kit)
from npc_kit import *
from mathutils import Vector, Quaternion, Euler, Matrix
from mathutils.bvhtree import BVHTree

SCRATCH = os.environ.get("NPC_SCRATCH", "")
X90 = Quaternion((1, 0, 0), math.pi / 2)
Y90 = Quaternion((0, 1, 0), math.pi / 2)
FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def sides():
    return ((-1, "L"), (1, "R"))


# ====================================================================== extra primitives
def ell(name, c, r, m, seg=24, ring=12, fn=None, keep=None, hero=False, rot=None):
    """Ellipsoid whose cross-section can be reshaped per vertex: fn(unit_dir) -> (sx, sy, sz).
    keep(unit_dir) trims it (cut along meridians for clean edges). Clean quads, no decimation."""
    seg, ring = npc_kit._d(seg, npc_kit.FLOOR.get(seg, 10), hero), npc_kit._d(ring, 6, hero, even=False)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    if keep is not None:
        dead = [v for v in bm.verts if not keep(v.co.normalized())]
        bmesh.ops.delete(bm, geom=dead, context="VERTS")
    for v in bm.verts:
        d = v.co.normalized()
        s = fn(d) if fn else (1, 1, 1)
        v.co = Vector((d.x * r[0] * s[0], d.y * r[1] * s[1], d.z * r[2] * s[2]))
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m, c)
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    return o


def taper(top=1.0, bottom=0.8, front=1.0):
    """Cross-section scale that narrows towards the bottom (a V-shaped chest)."""
    def f(d):
        t = (d.z + 1) * 0.5
        k = bottom + (top - bottom) * t
        return (k, (front if d.y < 0 else 1.0) * (0.9 + 0.1 * k), 1.0)
    return f


def front_angle(d):
    """Angle (deg) of a unit direction round the vertical axis, 0 = straight ahead (-Y)."""
    return abs(math.degrees(math.atan2(d.x, -d.y)))


def _curve_to_obj(name, cu, m):
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    toykit.STATE["coll"].objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    me.name = name
    bpy.data.objects.remove(tmp)
    if isinstance(cu, bpy.types.TextCurve):
        bpy.data.curves.remove(cu)
    else:
        bpy.data.curves.remove(cu)
    me.materials.clear()
    o = toykit._obj(name, me, m, smooth=False)
    # soft bevelled edges, flat faces: auto-smooth by angle
    for p in me.polygons:
        p.use_smooth = True
    _sharpen(me, 40)
    return o


def _sharpen(me, deg):
    bm = bmesh.new()
    bm.from_mesh(me)
    lim = math.radians(deg)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > lim:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()


def shape2d(name, outlines, m, depth=0.004, bevel=0.0015, res=3, scale=1.0, offset=(0, 0), poly=False):
    """Flat extruded badge shape in local XY (thickness along Z, centred on z=0).
    outlines: list of point lists; a point is (x, y) for a smooth point or (x, y, 1) for a corner.
    Inner outlines become holes (2D curve fill)."""
    cu = bpy.data.curves.new(name + "_cu", "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = depth
    cu.bevel_depth = bevel
    cu.bevel_resolution = 1
    cu.resolution_u = res
    for pts in outlines:
        if poly:
            sp = cu.splines.new("POLY")
            sp.points.add(len(pts) - 1)
            sp.use_cyclic_u = True
            for i, p in enumerate(pts):
                sp.points[i].co = ((p[0] + offset[0]) * scale, (p[1] + offset[1]) * scale, 0, 1)
            continue
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        sp.use_cyclic_u = True
        for i, p in enumerate(pts):
            bp = sp.bezier_points[i]
            bp.co = ((p[0] + offset[0]) * scale, (p[1] + offset[1]) * scale, 0)
            t = "VECTOR" if len(p) > 2 and p[2] else "AUTO"
            bp.handle_left_type = bp.handle_right_type = t
    return _curve_to_obj(name, cu, m)


def text2d(name, body, m, size=0.05, depth=0.004, bevel=0.0012, res=2, font=FONT, spacing=1.0):
    cu = bpy.data.curves.new(name + "_txt", "FONT")
    cu.body = body
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    cu.size = size
    cu.extrude = depth
    cu.bevel_depth = bevel
    cu.bevel_resolution = 1
    cu.resolution_u = res
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.space_character = spacing
    return _curve_to_obj(name, cu, m)


def heart_pts(w=1.0):
    pts = [(0, -1.0, 1), (-0.62, -0.38), (-0.98, 0.18), (-0.82, 0.68), (-0.42, 0.8), (0, 0.48, 1),
           (0.42, 0.8), (0.82, 0.68), (0.98, 0.18), (0.62, -0.38)]
    return [(p[0] * w, p[1] * w) + tuple(p[2:]) for p in pts]


def circle_pts(r, n=12, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


# ------------------------------------------------------------------ emblems
EAGLE = [(-0.66, 0.40, 1), (-0.4, 0.62), (-0.12, 0.62), (0.08, 0.45, 1), (0.36, 0.58), (0.8, 0.64, 1),
         (0.6, 0.4, 1), (0.84, 0.3, 1), (0.6, 0.12, 1), (0.74, 0.0, 1), (0.46, -0.1, 1), (0.52, -0.3, 1),
         (0.22, -0.28, 1), (0.14, -0.74, 1), (-0.1, -0.44), (-0.26, -0.05), (-0.3, 0.24, 1), (-0.5, 0.3, 1),
         (-0.44, 0.38, 1)]


def badge(name, targets, origin, normal, up, r, m_disc, m_rim, m_icon, icon, icon_scale=0.78, lift=0.0015,
          holes=()):
    """Round tampo-printed badge wrapped onto a curved surface: disc, rim ring, icon on top."""
    d = shape2d(name, [circle_pts(r, 18)], m_disc, depth=0.0025, bevel=0.0, poly=True)
    stick(d, targets, origin, normal, up, lift=lift)
    rim = shape2d(name + "_Rim", [circle_pts(r * 1.02, 18), circle_pts(r * 0.86, 18)], m_rim, depth=0.0025,
                  bevel=0.0, poly=True)
    stick(rim, targets, origin, normal, up, lift=lift + 0.003)
    k = r * icon_scale
    outs = [[(p[0] * k, p[1] * k) + tuple(p[2:]) for p in icon]]
    outs += [[(p[0] * k, p[1] * k) for p in h] for h in holes]
    ic = shape2d(name + "_Icon", outs, m_icon, depth=0.0022, bevel=0.0, res=2)
    stick(ic, targets, origin, normal, up, lift=lift + 0.003)
    return d


def eagle_badge(name, targets, origin, normal, up, r, m_disc, m_rim, m_icon):
    return badge(name, targets, origin, normal, up, r, m_disc, m_rim, m_icon, EAGLE,
                 holes=[circle_pts(0.06, 8, -0.24, 0.5)])


def skirt(name, z_top, z_bot, r_top, r_bot, m, open_deg=0.0, seg=24, rings=4, thick=0.008, bulge=0.0):
    """Coat tails / collars: a flared shell round the Z axis, optionally open at the front (-Y)."""
    seg = npc_kit._d(seg, 12)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    a0, a1 = math.radians(open_deg), math.radians(360 - open_deg)
    closed = open_deg <= 0
    ncol = seg if closed else seg + 1
    grid = []
    for j in range(rings + 1):
        t = j / rings
        z = z_top + (z_bot - z_top) * t
        rx = r_top[0] + (r_bot[0] - r_top[0]) * t + bulge * math.sin(math.pi * t)
        ry = r_top[1] + (r_bot[1] - r_top[1]) * t + bulge * math.sin(math.pi * t)
        row = []
        for i in range(ncol):
            a = a0 + (a1 - a0) * i / (seg if not closed else seg)
            row.append(bm.verts.new((rx * math.sin(a), -ry * math.cos(a), z)))
        grid.append(row)
    for j in range(rings):
        for i in range(seg if closed else seg):
            i2 = (i + 1) % ncol if closed else i + 1
            bm.faces.new((grid[j][i], grid[j][i2], grid[j + 1][i2], grid[j + 1][i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=thick)
    bm.to_mesh(me)
    bm.free()
    return toykit._obj(name, me, m)


HYDRA_SKULL = [(0, 0.66), (0.3, 0.6), (0.43, 0.34), (0.38, 0.06), (0.26, -0.06, 1), (0.25, -0.28, 1),
               (-0.25, -0.28, 1), (-0.26, -0.06, 1), (-0.38, 0.06), (-0.43, 0.34), (-0.3, 0.6)]


def hydra_emblem(name, targets, origin, normal, up, size, m, lift=0.002, depth=0.0025):
    """Cartoon Hydra skull with six curly tentacles, printed onto a curved surface."""
    k = size
    eyes = [[(x * k, y * k) for x, y in circle_pts(0.125, 10, sx * 0.19, 0.25)] for sx in (-1, 1)]
    nose = [(-0.055 * k, -0.07 * k), (0.055 * k, -0.07 * k), (0.0, 0.05 * k)]
    K = 1.3
    sk = shape2d(name, [[(p[0] * k * K, p[1] * k * K) + tuple(p[2:]) for p in HYDRA_SKULL]] +
                 [[(x * K, y * K) for x, y in e] for e in eyes] + [[(x * K, y * K) for x, y in nose]], m, depth=depth,
                 bevel=0.0, res=2)
    stick(sk, targets, origin, normal, up, lift=lift + 0.006)
    for i, (a, curl) in enumerate([(-2, 1), (182, -1), (-38, 1), (218, -1), (-74, 1), (254, -1)]):
        left, right = [], []
        n = 11

        def cen(t):
            ang = math.radians(a) + curl * 1.1 * t ** 2.2
            r = 0.25 + 0.85 * t
            return Vector((math.cos(ang) * r, 0.05 + math.sin(ang) * r))
        for j in range(n + 1):
            t = j / n
            c = cen(t)
            d = (cen(min(1.0, t + 0.02)) - cen(max(0.0, t - 0.02))).normalized()
            perp = Vector((-d.y, d.x))
            w = 0.08 * (1 - t) + 0.032
            left.append(c + perp * w)
            right.append(c - perp * w)
        pts = [(p.x * k, p.y * k, 1) for p in left] + [(p.x * k, p.y * k, 1) for p in reversed(right)]
        tn = shape2d(f"{name}_Tentacle{i}", [pts], m, depth=depth, bevel=0.0, poly=True)
        stick(tn, targets, origin, normal, up, lift=lift + 0.003)


def bvh_of(objs):
    bpy.context.view_layer.update()
    verts, polys = [], []
    for o in objs:
        mw = o.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in o.data.vertices]
        polys += [[base + i for i in p.vertices] for p in o.data.polygons]
    return BVHTree.FromPolygons(verts, polys)


class Frame:
    """A tangent frame on a surface: 2D (x, y) on a plane above it -> point/normal on the surface."""

    def __init__(self, targets, origin, normal, up=(0, 0, 1)):
        self.tree = bvh_of(targets if isinstance(targets, (list, tuple)) else [targets])
        self.n = Vector(normal).normalized()
        u = Vector(up)
        self.u = (u - self.n * u.dot(self.n)).normalized()
        self.r = self.u.cross(self.n)
        self.o = Vector(origin)

    def at(self, x, y, off=0.0):
        p = self.o + self.r * x + self.u * y
        hit, hn, _, dist = self.tree.ray_cast(p + self.n * 0.4, -self.n, 1.0)
        if hit is None:
            hit, hn = self.tree.find_nearest(p)[:2]
        return hit + hn * off, hn


def stroke(pts, w0, w1=None):
    """Outline polygon of a tapered thick polyline (for tentacles, spider legs...)."""
    w1 = w0 if w1 is None else w1
    pts = [Vector(p) for p in pts]
    left, right = [], []
    for i, p in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        d = (b - a).normalized()
        perp = Vector((-d.y, d.x))
        w = w0 + (w1 - w0) * i / (len(pts) - 1)
        left.append(p + perp * w)
        right.append(p - perp * w)
    return [(p.x, p.y, 1) for p in left] + [(p.x, p.y, 1) for p in reversed(right)]


def stick(o, targets, origin, normal, up=(0, 0, 1), lift=0.002, spin=0.0, subdiv=0):
    """Wrap a flat shape (local XY, thickness Z) onto the surface of `targets`, like a printed
    tampo decal standing proud of the surface. origin = a point roughly on/above the surface."""
    tree = bvh_of(targets if isinstance(targets, (list, tuple)) else [targets])
    n = Vector(normal).normalized()
    u = Vector(up)
    u = (u - n * u.dot(n)).normalized()
    r = u.cross(n)
    if spin:
        q = Quaternion(n, spin)
        u, r = q @ u, q @ r
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    z0 = min(v.co.z for v in bm.verts)
    back = [f for f in bm.faces if all(abs(v.co.z - z0) < 1e-5 for v in f.verts)]
    bmesh.ops.delete(bm, geom=back, context="FACES_ONLY")
    bm.to_mesh(me)
    bm.free()
    if subdiv:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdiv, use_grid_fill=True)
        bm.to_mesh(me)
        bm.free()
    zs = [v.co.z for v in me.vertices]
    zmin = min(zs)
    O = Vector(origin)
    for v in me.vertices:
        x, y, z = v.co
        p = O + r * x + u * y
        hit, hn, _, dist = tree.ray_cast(p + n * 0.4, -n, 1.0)
        near = tree.find_nearest(p)
        if hit is None or dist > 0.4 + near[3] * 2.0 + 0.04:  # shot through a gap: use the nearest surface
            hit = near[0]
        base = hit if hit is not None else p
        v.co = base + n * (z - zmin + lift)
    me.update()
    o.location = (0, 0, 0)
    return o


# ====================================================================== shared person bits
def face_eyes(hc, hr, black, white, x=0.34, z=-0.02, w=0.033, h=0.045, shine2=True):
    for s, side in sides():
        eye(f"Eye_{side}", hc, hr, (s * x, -1, z), w, h, black, white, shine2=shine2)


def face_brows(hc, hr, m, x=0.34, z=0.2, r=0.012, angry=0.0, lift=0.004, skip=()):
    for s, side in sides():
        if side in skip:
            continue
        pts = [(s * (x - 0.15), -1, z - angry), (s * x, -1, z + 0.04), (s * (x + 0.16), -1, z + 0.0 + angry * 0.3)]
        tube(f"Brow_{side}", arc_on(hc, hr, pts, lift=lift), m, r=r, radii=[0.85, 1, 0.7], caps=False)


def face_smile(hc, hr, m, width=0.15, z=-0.42, depth=0.06, r=0.0075, skew=0.0):
    pts = [(-width, -1, z + 0.04 + skew), (-width * 0.4, -1, z - depth * 0.7), (width * 0.4, -1, z - depth * 0.7),
           (width, -1, z + 0.04 - skew)]
    tube("Smile", arc_on(hc, hr, pts, lift=0.002), m, r=r)


def mitten(name, c, m, size=0.05, thumb=True, s=1):
    """Toy hand: soft mitten with a little thumb pointing forward/inwards."""
    c = Vector(c)
    sph(name, c, (size * 0.92, size * 0.85, size * 1.05), m, seg=14, ring=7)
    if thumb:
        sph(name + "_Thumb", c + Vector((-s * size * 0.55, -size * 0.55, size * 0.25)), (size * 0.38, size * 0.36, size * 0.5),
            m, rot=Quaternion((0, 1, 0), -s * 0.4), seg=10, ring=5)


def sneaker(side, s, x, y, m_upper, m_sole, m_toe=None, m_lace=None, scale=1.0, z0=0.0):
    k = scale
    c = Vector((s * x, y - 0.03 * k, z0 + 0.052 * k))
    sph(f"Shoe_{side}", c, (0.068 * k, 0.106 * k, 0.055 * k), m_upper, seg=16, ring=8)
    sph(f"Shoe_{side}_Sole", c + Vector((0, -0.002, -0.034 * k)), (0.072 * k, 0.11 * k, 0.022 * k), m_sole, seg=16, ring=6)
    if m_toe:
        sph(f"Shoe_{side}_Toe", c + Vector((0, -0.07 * k, -0.018 * k)), (0.05 * k, 0.04 * k, 0.03 * k), m_toe, seg=12, ring=6)
    if m_lace:
        for i in range(3):
            box(f"Shoe_{side}_Lace{i}", c + Vector((0, -0.035 * k + i * 0.022 * k, 0.05 * k - i * 0.004 * k)),
                (0.05 * k, 0.008 * k, 0.008 * k), m_lace, bevel=0.003, rot=(0.5, 0, 0))


def boot(side, s, x, y, m, m_sole, k=1.0, top=0.13):
    c = Vector((s * x, y - 0.035 * k, 0.058 * k))
    cyl(f"Boot_{side}_Shaft", (s * x, y - 0.005, top * 0.6), 0.064 * k, top * 0.8, m, seg=14)
    sph(f"Boot_{side}", c, (0.076 * k, 0.112 * k, 0.058 * k), m, seg=16, ring=8)
    sph(f"Boot_{side}_Sole", c + Vector((0, 0, -0.036 * k)), (0.08 * k, 0.116 * k, 0.022 * k), m_sole, seg=16, ring=6)
    box(f"Boot_{side}_Heel", (s * x, y + 0.05 * k, 0.018 * k), (0.11 * k, 0.07 * k, 0.036 * k), m_sole, bevel=0.01)


def person_pivots(head_bottom, shoulder_x, shoulder_z, hip_x, hip_z):
    return {"Body": (0, 0, 0), "Head": (0, 0, head_bottom + 0.05),
            "ArmL": (-shoulder_x, 0, shoulder_z), "ArmR": (shoulder_x, 0, shoulder_z),
            "LegL": (-hip_x, 0, hip_z), "LegR": (hip_x, 0, hip_z)}


# ====================================================================== 1. Civilian
def civilian():
    reset("Civilian")
    black, white = common_mats()
    skin = mat("Skin", "d99a6c", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "2e2019", rough=0.45, coat=0.3)
    tee = mat("Tee", "f6f4ee", rough=0.5, coat=0.2)
    ink = mat("Ink", "1c1c22", rough=0.4, coat=0.3)
    heart = mat("Heart", "e8283a", rough=0.3, coat=0.6)
    hood = mat("Hoodie", "2a9d8f", rough=0.5, coat=0.25)
    hood2 = mat("HoodieDark", "1f7a70", rough=0.55, coat=0.2)
    zip_ = mat("Zip", "d9dde2", rough=0.25, metal=0.8, coat=0.3)
    jeans = mat("Jeans", "3d5f9e", rough=0.55, coat=0.15)
    jeans2 = mat("JeansDark", "2f4b80", rough=0.55, coat=0.15)
    shoe = mat("Sneaker", "e83b3b", rough=0.35, coat=0.5)
    sole = mat("SneakerSole", "fbfaf5", rough=0.4, coat=0.3)
    pack = mat("Backpack", "f2a93b", rough=0.45, coat=0.35)
    pack2 = mat("BackpackDark", "c9822a", rough=0.5, coat=0.3)
    phones = mat("Headphones", "26262c", rough=0.3, coat=0.6)
    phones2 = mat("HeadphonePad", "ff7a3d", rough=0.4, coat=0.4)
    cup = mat("Cup", "fbfaf5", rough=0.4, coat=0.4)
    sleeve = mat("CupSleeve", "a8724a", rough=0.6, coat=0.1)
    lid = mat("CupLid", "3b2a24", rough=0.35, coat=0.4)
    mouth = mat("Mouth", "6a2a20", rough=0.4)
    blush = mat("Blush", "f08a78", rough=0.6, coat=0.0)
    pin = mat("PinBlue", "2f6fd8", rough=0.3, coat=0.6)
    pin2 = mat("PinRed", "e23b3b", rough=0.3, coat=0.6)

    HZ, HR = 0.72, (0.215, 0.198, 0.2)
    hc, hr = (0, 0, HZ), HR
    with limb("Head"):
        sph("Head", hc, hr, skin, seg=28, ring=14, hero=True)
        # curly mop: one cap sitting up/back on the skull (clean natural hairline where they cross),
        # soft curls sunk into it, a curly fringe flick over the brow
        shc, shr = (0, 0.012, HZ + 0.008), (0.229, 0.215, 0.214)
        tilt = Quaternion((1, 0, 0), -0.45)
        hsph("Hair", shc, shr, hair, keep_above=-0.06, rot=tilt, seg=28, ring=14, hero=True)
        # a big swept quiff over the brow (soft lobes swept to his left), tufts at the crown and nape
        lobes = [((0.35, -0.85, 0.3), 0.075, 0.13, (-1, -0.25, 0.25)), ((-0.05, -0.85, 0.4), 0.08, 0.14, (-1, -0.2, 0.35)),
                 ((-0.45, -0.75, 0.48), 0.07, 0.11, (-1, 0.1, -0.15)), ((0.15, -0.55, 0.85), 0.075, 0.13, (-1, 0.2, 0.3)),
                 ((0.62, -0.35, 0.55), 0.06, 0.1, (-0.5, -0.6, 0.6)), ((-0.2, 0.25, 1.0), 0.06, 0.1, (-0.6, 0.8, 0.1)),
                 ((0.2, 0.75, 0.62), 0.065, 0.1, (0.3, 0.7, -0.6))]
        for i, (d, w, ln, sw) in enumerate(lobes):
            p, n = on(shc, shr, tilt @ Vector(d), -0.03)
            dirv = (Vector(sw).normalized() - n * Vector(sw).normalized().dot(n)).normalized()
            sph(f"Hair_Lobe{i}", p + dirv * ln * 0.25, (w, w * 0.62, ln), hair, rot=aim(dirv, 0.0) @ Quaternion((0, 0, 1), 0.0),
                seg=14, ring=7)
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.212, 0.01, HZ - 0.015), (0.034, 0.027, 0.046), skin)
            decal(f"Blush_{side}", hc, hr, (s * 0.6, -1, -0.3), (0.032, 0.008, 0.019), blush)
        face_eyes(hc, hr, black, white, x=0.34, z=-0.04, w=0.032, h=0.045)
        face_brows(hc, hr, hair, x=0.34, z=0.17, r=0.011)
        p, n = on(hc, hr, (0, -1, -0.18), 0.012)
        sph("Nose", p, (0.03, 0.026, 0.026), skin)
        face_smile(hc, hr, mouth, width=0.15, z=-0.42, depth=0.085, r=0.008)

    TC, TR = (0, 0, 0.405), (0.158, 0.13, 0.165)
    with limb("Body"):
        torso = sph("Torso", TC, TR, tee, seg=24, ring=12, hero=True)
        # open hoodie: same shell, a little bigger, cut open down the front along meridians
        hood_shell = ell("Hoodie", TC, (TR[0] + 0.012, TR[1] + 0.012, TR[2] + 0.006), hood, seg=24, ring=12,
                         keep=lambda d: front_angle(d) > 33 or d.z < -0.62)
        ell("Hoodie_Hem", (0, 0, 0.29), (0.168, 0.14, 0.05), hood2, seg=24, ring=8)
        # hood bunched up behind the neck
        sph("Hood", (0, 0.07, 0.545), (0.14, 0.085, 0.07), hood2, seg=16, ring=8)
        sph("Hood_Inner", (0, 0.06, 0.565), (0.1, 0.05, 0.035), hood, seg=12, ring=6)
        for s, side in sides():
            a = math.radians(34)
            pts = []
            for k in range(5):
                el = math.radians(-35 + k * 22)
                d = Vector((s * math.sin(a) * math.cos(el), -math.cos(a) * math.cos(el), math.sin(el)))
                pts.append(Vector(TC) + Vector((d.x * (TR[0] + 0.016), d.y * (TR[1] + 0.016), d.z * (TR[2] + 0.01))))
            tube(f"Zip_{side}", pts, zip_, r=0.007, caps=False)
            # drawstrings
            p0 = Vector((s * 0.045, -0.115, 0.52))
            tube(f"String_{side}", [p0, p0 + Vector((s * 0.004, -0.02, -0.05)), p0 + Vector((s * 0.008, -0.022, -0.09))],
                 sole, r=0.0045, caps=False)
            sph(f"String_{side}_Tip", p0 + Vector((s * 0.008, -0.022, -0.095)), 0.008, zip_)
        # I <3 NY on the tee
        t1 = text2d("Logo_I", "I", ink, size=0.056, depth=0.003, bevel=0.0)
        t1.data.transform(Matrix.Translation((-0.028, 0.027, 0)))
        stick(t1, torso, (0, -0.2, 0.45), (0, -1, 0))
        h = shape2d("Logo_Heart", [heart_pts(0.024)], heart, depth=0.0035, bevel=0.0, res=2)
        h.data.transform(Matrix.Translation((0.016, 0.026, 0)))
        stick(h, torso, (0, -0.2, 0.45), (0, -1, 0))
        t2 = text2d("Logo_NY", "NY", ink, size=0.056, depth=0.003, bevel=0.0, spacing=0.9)
        t2.data.transform(Matrix.Translation((0.0, -0.022, 0)))
        stick(t2, torso, (0, -0.2, 0.45), (0, -1, 0))
        # badge pins on the hoodie
        p, n = on(TC, TR, (-0.6, -1, 0.35), 0.014)
        cyl("Pin_Star", p, 0.016, 0.006, pin, rot=aim(n), seg=12)
        p, n = on(TC, TR, (-0.66, -1, 0.05), 0.014)
        cyl("Pin_Red", p, 0.013, 0.006, pin2, rot=aim(n), seg=12)
        # headphones round the neck
        torus("Phones_Band", (0, 0.012, 0.565), 0.1, 0.012, phones, rot=(math.radians(-18), 0, 0), scale=(1, 0.95, 1))
        for s, side in sides():
            q = aim((s, -0.5, -0.1))
            p = Vector((s * 0.09, -0.065, 0.54))
            cyl(f"Phones_Cup_{side}", p, 0.034, 0.026, phones, rot=q, seg=14)
            cyl(f"Phones_Pad_{side}", p - (q @ Vector((0, 0, 0.016))), 0.03, 0.01, phones2, rot=q, seg=14)
        # jeans seat + belt line
        sph("Jeans", (0, 0, 0.255), (0.148, 0.122, 0.08), jeans, seg=20, ring=10)
        # backpack
        box("Backpack", (0, 0.175, 0.42), (0.22, 0.1, 0.25), pack, bevel=0.04)
        box("Backpack_Pocket", (0, 0.23, 0.37), (0.16, 0.035, 0.11), pack2, bevel=0.016)
        box("Backpack_Top", (0, 0.18, 0.55), (0.2, 0.09, 0.03), pack2, bevel=0.012)
        torus("Backpack_Loop", (0, 0.2, 0.575), 0.022, 0.006, phones, rot=(0, math.pi / 2, 0), seg=10)
        for s, side in sides():
            tube(f"Strap_{side}", [(s * 0.09, 0.13, 0.5), (s * 0.1, 0.03, 0.548), (s * 0.122, -0.088, 0.49),
                                   (s * 0.128, -0.1, 0.39)], pack2, r=0.013, caps=False)
            box(f"Strap_{side}_Clip", (s * 0.127, -0.108, 0.42), (0.03, 0.012, 0.022), zip_, bevel=0.004,
                rot=(0, 0, -s * 0.5))

    SX, SZ = 0.165, 0.465
    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Shoulder_{side}", (s * 0.15, 0, 0.475), (0.056, 0.054, 0.056), hood)
            tube(f"Sleeve_{side}", [(s * 0.165, 0.0, 0.46), (s * 0.198, -0.012, 0.39), (s * 0.21, -0.02, 0.335)], hood,
                 r=0.036, radii=[1, 0.95, 0.9], caps=False)
            torus(f"Cuff_{side}", (s * 0.211, -0.021, 0.33), 0.031, 0.012, hood2)
            mitten(f"Hand_{side}", (s * 0.214, -0.025, 0.295), skin, size=0.04, s=s)
            if s < 0:  # coffee to go
                cp = Vector((-0.218, -0.07, 0.29))
                cyl("Cup", cp, 0.03, 0.085, cup, r2=0.036, seg=14)
                cyl("Cup_Sleeve", cp + Vector((0, 0, -0.004)), 0.033, 0.036, sleeve, r2=0.035, seg=14, bevel=0.0)
                cyl("Cup_Lid", cp + Vector((0, 0, 0.047)), 0.039, 0.012, lid, seg=14)
                cyl("Cup_LidTop", cp + Vector((0, 0, 0.056)), 0.03, 0.008, lid, seg=14)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.07, 0, 0.22), (s * 0.072, -0.004, 0.09)], jeans, r=0.048, radii=[1, 0.92],
                 caps=False)
            torus(f"Leg_{side}_Cuff", (s * 0.072, -0.004, 0.095), 0.045, 0.014, jeans2)
            sneaker(side, s, 0.074, 0.0, shoe, sole, m_toe=sole, m_lace=sole)

    pivots = person_pivots(HZ - HR[2], SX, SZ, 0.07, 0.22)
    return dict(backdrop="dbe6ee", pivots=pivots, target=(0, 0, 0.5), dist=2.15, kind="friendly person", budget=7000)


# ====================================================================== 2. S.H.I.E.L.D. agent
def shield_agent():
    reset("ShieldAgent")
    black, white = common_mats()
    skin = mat("Skin", "f0c4a2", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "3a2216", rough=0.38, coat=0.4)
    suit = mat("Suit", "22335c", rough=0.4, coat=0.4)
    suit2 = mat("SuitPanel", "33508a", rough=0.4, coat=0.4)
    vest = mat("Vest", "1c2029", rough=0.45, coat=0.35)
    vest2 = mat("VestPouch", "2a303d", rough=0.5, coat=0.3)
    silver = mat("Silver", "c8d0da", rough=0.2, metal=0.9, coat=0.3)
    emblem = mat("Emblem", "f4f6fa", rough=0.3, coat=0.5)
    glove = mat("Glove", "16181f", rough=0.32, coat=0.55)
    bootm = mat("Boot", "17191f", rough=0.28, coat=0.65)
    sole = mat("Sole", "2c2f36", rough=0.6, coat=0.1)
    lips = mat("Lips", "c0565c", rough=0.35, coat=0.4)
    blush = mat("Blush", "f29a8a", rough=0.6, coat=0.0)
    tie = mat("HairTie", "e23b3b", rough=0.35, coat=0.5)
    tablet = mat("Tablet", "2a2f3a", rough=0.3, metal=0.4, coat=0.5)
    holo = mat("Holo", "8fe8ff", rough=0.1, coat=0.4, emit="35c6ff", emit_strength=2.5)

    HZ, HR = 0.9, (0.212, 0.196, 0.205)
    hc, hr = (0, 0, HZ), HR
    with limb("Head"):
        sph("Head", hc, hr, skin, seg=28, ring=14, hero=True)
        # sleek hair: a cap with a side part and a swept fringe, high ponytail
        shc, shr = (0, 0.01, HZ + 0.008), (0.222, 0.208, 0.214)
        tilt = Quaternion((1, 0, 0), -0.5) @ Quaternion((0, 1, 0), 0.12)
        hsph("Hair", shc, shr, hair, keep_above=-0.08, rot=tilt, seg=28, ring=14, hero=True)
        for i, (d, w, ln, sw) in enumerate([((-0.25, -0.85, 0.3), 0.075, 0.15, (1, -0.15, -0.35)),
                                            ((0.25, -0.8, 0.28), 0.06, 0.11, (1, 0.1, -0.6)),
                                            ((-0.6, -0.55, 0.35), 0.06, 0.1, (0.4, -0.3, -0.8))]):
            p, n = on(shc, shr, tilt @ Vector(d), -0.026)
            dv = Vector(sw).normalized()
            dv = (dv - n * dv.dot(n)).normalized()
            sph(f"Hair_Fringe{i}", p + dv * ln * 0.3, (w, w * 0.55, ln), hair, rot=aim(dv), seg=14, ring=7)
        tp = Vector((0, 0.19, HZ + 0.1))
        sph("Hair_Tie_Base", tp, (0.06, 0.05, 0.055), hair)
        torus("Hair_Tie", tp + Vector((0, 0.035, -0.005)), 0.033, 0.012, tie, rot=aim((0, 1, 0.3)), seg=12)
        tube("Ponytail", [tp + Vector((0, 0.04, 0)), tp + Vector((0, 0.11, -0.04)), tp + Vector((0.01, 0.14, -0.15)),
                          tp + Vector((0.025, 0.12, -0.26))], hair, r=0.045, radii=[0.9, 1.0, 0.75, 0.3], br=2)
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.208, 0.01, HZ - 0.02), (0.032, 0.026, 0.044), skin)
            decal(f"Blush_{side}", hc, hr, (s * 0.6, -1, -0.32), (0.03, 0.008, 0.018), blush)
            # long lashes: a little flick at the outer corner
            p, n = on(hc, hr, (s * 0.5, -1, 0.06), 0.004)
            sph(f"Lash_{side}", p, (0.016, 0.008, 0.007), black, rot=facing(n) @ Quaternion((0, 1, 0), -s * 0.6))
        face_eyes(hc, hr, black, white, x=0.34, z=-0.04, w=0.031, h=0.045)
        face_brows(hc, hr, hair, x=0.34, z=0.15, r=0.0095, angry=0.03)
        p, n = on(hc, hr, (0, -1, -0.19), 0.01)
        sph("Nose", p, (0.024, 0.02, 0.022), skin)
        face_smile(hc, hr, lips, width=0.11, z=-0.42, depth=0.05, r=0.0085, skew=0.02)
        # earpiece with a coiled wire down to the collar
        sph("Earpiece", (0.215, -0.02, HZ - 0.03), (0.016, 0.016, 0.02), glove)
        tube("Earpiece_Wire", [(0.215, -0.01, HZ - 0.05), (0.2, 0.02, HZ - 0.12), (0.17, 0.04, HZ - 0.19)], glove,
             r=0.0045, caps=False)

    TC, TR = (0, 0, 0.535), (0.182, 0.13, 0.185)
    with limb("Body"):
        torso = ell("Torso", TC, TR, suit, seg=24, ring=12, fn=taper(1.0, 0.8), hero=True)
        # tactical vest: same shape, a touch bigger, front and back, with straps over the shoulders
        vst = ell("Vest", TC, (TR[0] + 0.014, TR[1] + 0.016, TR[2] + 0.008), vest, seg=24, ring=12, fn=taper(1.0, 0.8),
                  keep=lambda d: -0.72 < d.z < 0.5)
        for s, side in sides():
            tube(f"Vest_Strap_{side}", [(s * 0.1, -0.115, 0.6), (s * 0.108, -0.07, 0.68), (s * 0.112, 0.0, 0.705),
                                        (s * 0.108, 0.08, 0.675), (s * 0.1, 0.115, 0.6)], vest, r=0.02, caps=False)
        cyl("Collar", (0, 0, 0.705), 0.085, 0.05, suit2, r2=0.078, seg=18)
        box("Vest_Zip", (0, -0.152, 0.51), (0.012, 0.012, 0.2), silver, bevel=0.004)
        vt = (TR[0] + 0.014, TR[1] + 0.016, TR[2] + 0.008)
        for s, side in sides():
            for k, z in enumerate((0.0, -0.4)):
                if k == 0 and s < 0:
                    continue  # badge goes there
                p, n = on(TC, vt, (s * 0.42, -1, z), 0.008)
                q = facing(n)
                box(f"Pouch_{side}{k}", p, (0.06, 0.03, 0.055), vest2, bevel=0.01, rot=q)
                box(f"Pouch_{side}{k}_Flap", p + n * 0.012 + Vector((0, 0, 0.02)), (0.064, 0.012, 0.022), vest,
                    bevel=0.005, rot=q)
                sph(f"Pouch_{side}{k}_Snap", p + n * 0.02 + Vector((0, 0, 0.014)), (0.006, 0.004, 0.006), silver,
                    rot=q)
        # small eagle badge on the chest, left side (her left = -X)
        eagle_badge("Chest_Badge", vst, (-0.07, -0.2, 0.545), (-0.3, -1, 0.1), (0, 0, 1), 0.034, suit, silver, emblem)
        ell("Hips", (0, 0, 0.385), (0.152, 0.122, 0.095), suit, seg=20, ring=10)
        torus("Belt", (0, 0, 0.405), 0.15, 0.02, vest, scale=(1, 0.84, 1), seg=24)
        box("Belt_Buckle", (0, -0.128, 0.405), (0.05, 0.016, 0.036), silver, bevel=0.006)
        box("Belt_Pouch", (0.13, -0.07, 0.4), (0.05, 0.05, 0.05), vest2, bevel=0.01, rot=(0, 0, -0.5))

    SX, SZ = 0.205, 0.64
    for s, side in sides():
        with limb("Arm" + side):
            sh = sph(f"Shoulder_{side}", (s * 0.2, 0, 0.645), (0.064, 0.062, 0.064), suit)
            eagle_badge(f"Shoulder_{side}_Badge", sh, (s * 0.26, -0.03, 0.66), (s * 1, -0.35, 0.3), (0, 0.15, 1), 0.04,
                        suit, silver, emblem)
            tube(f"Arm_{side}", [(s * 0.208, 0, 0.63), (s * 0.24, -0.012, 0.53), (s * 0.255, -0.026, 0.46)], suit,
                 r=0.042, radii=[1, 0.95, 0.9], caps=False)
            torus(f"Glove_{side}_Cuff", (s * 0.256, -0.027, 0.455), 0.04, 0.014, glove)
            mitten(f"Hand_{side}", (s * 0.26, -0.03, 0.415), glove, size=0.048, s=s)
            if s < 0:  # holo tablet
                tq = Quaternion((1, 0, 0), 0.35) @ Quaternion((0, 0, 1), 0.25)
                tpp = Vector((-0.255, -0.085, 0.4))
                box("Tablet", tpp, (0.1, 0.012, 0.13), tablet, bevel=0.008, rot=tq)
                box("Tablet_Screen", tpp + tq @ Vector((0, -0.006, 0)), (0.084, 0.004, 0.11), holo, bevel=0.003, rot=tq)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.085, 0, 0.33), (s * 0.088, 0, 0.12)], suit, r=0.06, caps=False)
            sph(f"Knee_{side}", (s * 0.088, -0.05, 0.215), (0.045, 0.022, 0.045), vest)
            boot(side, s, 0.09, 0.0, bootm, sole, k=1.0, top=0.15)
            if s > 0:  # sidearm in a thigh holster
                box("Holster", (0.14, -0.01, 0.27), (0.03, 0.07, 0.1), vest, bevel=0.012)
                torus("Holster_Strap", (0.088, 0, 0.24), 0.062, 0.01, vest2, seg=14)
                box("Holster_Grip", (0.142, 0.015, 0.33), (0.026, 0.035, 0.05), glove, bevel=0.01, rot=(-0.3, 0, 0))

    pivots = person_pivots(HZ - HR[2], SX, SZ, 0.085, 0.33)
    return dict(backdrop="dde3ee", pivots=pivots, target=(0, 0, 0.58), dist=2.5, kind="friendly person", budget=7000)


# ====================================================================== 3. Nick Fury
def nick_fury():
    reset("NickFury")
    black, white = common_mats()
    skin = mat("Skin", "6e432f", rough=0.33, coat=0.5, sss=0.1)
    beard = mat("Goatee", "26201e", rough=0.55, coat=0.15)
    patch = mat("Eyepatch", "121216", rough=0.25, coat=0.8)
    coat = mat("Leather", "1e1f25", rough=0.22, coat=0.8)
    coat2 = mat("LeatherEdge", "2c2e36", rough=0.25, coat=0.7)
    lining = mat("Lining", "5a1f24", rough=0.45, coat=0.3)
    shirt = mat("Turtleneck", "565b68", rough=0.55, coat=0.15)
    pants = mat("Pants", "23242a", rough=0.45, coat=0.3)
    bootm = mat("Boot", "141418", rough=0.22, coat=0.8)
    sole = mat("Sole", "34363c", rough=0.6, coat=0.1)
    buckle = mat("Buckle", "c8ccd2", rough=0.2, metal=0.9, coat=0.3)
    mouth = mat("Mouth", "3a1814", rough=0.4)
    eagle = mat("EagleSilver", "dfe3ea", rough=0.25, metal=0.6, coat=0.4)

    HZ, HR = 0.93, (0.205, 0.192, 0.208)
    hc, hr = (0, 0, HZ), HR
    with limb("Head"):
        sph("Head", hc, hr, skin, seg=28, ring=14, hero=True)
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.202, 0.01, HZ - 0.02), (0.033, 0.026, 0.046), skin)
        # one sharp eye (his right), eyepatch over his left; a stern brow and a knowing half smile
        eye("Eye_R", hc, hr, (0.33, -1, -0.04), 0.03, 0.04, black, white)
        p, n = on(hc, hr, (-0.33, -1, -0.02), 0.0)
        q = facing(n)
        sph("Eyepatch", p + n * 0.002, (0.058, 0.014, 0.05), patch, rot=q, seg=16, ring=8)
        P = Vector((-0.38, -1, 0.0)).normalized()
        Q = Vector((0.7, -0.35, 0.5)).normalized()
        w = P.cross(Q).normalized()
        v = w.cross(P)
        pts = []
        for k in range(1, 18):
            t = 2 * math.pi * k / 18
            pts.append((P * math.cos(t) + v * math.sin(t)))
        tube("Eyepatch_Strap", arc_on(hc, hr, [tuple(d) for d in pts], lift=0.004), patch, r=0.008, caps=False, res=2)
        tube("Brow_R", arc_on(hc, hr, [(0.16, -1, 0.12), (0.33, -1, 0.17), (0.5, -1, 0.15)], lift=0.004), beard,
             r=0.012, radii=[1.1, 1, 0.7], caps=False)
        tube("Brow_L", arc_on(hc, hr, [(-0.18, -1, 0.17), (-0.33, -1, 0.21), (-0.48, -1, 0.19)], lift=0.004), beard,
             r=0.011, radii=[1.1, 1, 0.7], caps=False)
        p, n = on(hc, hr, (0, -1, -0.17), 0.012)
        sph("Nose", p, (0.034, 0.026, 0.026), skin)
        # goatee: moustache + chin tuft, and a lopsided smirk
        tube("Smirk", arc_on(hc, hr, [(-0.1, -1, -0.4), (-0.02, -1, -0.43), (0.07, -1, -0.42), (0.13, -1, -0.36)],
                              lift=0.002), mouth, r=0.0078)
        p, n = on(hc, hr, (0, -1, -0.7), -0.004)
        sph("Goatee", p, (0.034, 0.022, 0.03), beard, rot=facing(n))
        tube("Goatee_Ring", arc_on(hc, hr, [(-0.15, -1, -0.37), (-0.13, -1, -0.52), (-0.06, -1, -0.62), (0.0, -1, -0.64),
                                            (0.06, -1, -0.62), (0.13, -1, -0.52), (0.16, -1, -0.37)], lift=0.003),
             beard, r=0.0065, radii=[0.6, 1, 1, 1, 1, 1, 0.6], caps=False)
        tube("Moustache", arc_on(hc, hr, [(-0.15, -1, -0.37), (-0.06, -1, -0.31), (0.06, -1, -0.31), (0.16, -1, -0.37)],
                                  lift=0.003), beard, r=0.0065, caps=False)

    TC, TR = (0, 0, 0.545), (0.19, 0.142, 0.19)
    with limb("Body"):
        ell("Turtleneck", TC, (TR[0] - 0.006, TR[1] - 0.006, TR[2] - 0.004), shirt, seg=24, ring=12, fn=taper(1.0, 0.84),
            hero=True)
        cyl("Turtleneck_Collar", (0, 0, 0.715), 0.075, 0.07, shirt, r2=0.07, seg=16)
        for k in range(3):
            torus(f"Turtleneck_Rib{k}", (0, 0, 0.695 + k * 0.02), 0.075 - k * 0.002, 0.007, shirt, seg=16)
        ct = (TR[0] + 0.01, TR[1] + 0.012, TR[2] + 0.004)
        ell("Coat", TC, ct, coat, seg=28, ring=14, fn=taper(1.0, 0.84), hero=True,
            keep=lambda d: front_angle(d) > 20 or d.z > 0.72 or d.z < -0.7)
        coat_o = bpy.data.objects["Coat"]
        # lapels: flat leather wedges pressed onto the coat along the opening
        for s_, side in sides():
            lap = shape2d(f"Lapel_{side}", [[(0.0, 0.0, 1), (0.045, 0.035, 1), (0.07, 0.11, 1), (0.04, 0.13, 1), (0.012, 0.14, 1),
                                             (0.0, 0.06, 1)]], coat, depth=0.004, bevel=0.0, poly=True)
            if s_ < 0:
                lap.data.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
                lap.data.flip_normals()
            stick(lap, coat_o, (s_ * 0.085, -0.2, 0.545), (s_ * 0.25, -1, 0.1), lift=0.0, subdiv=3)
        # tall turned-up collar, open at the front
        skirt("Coat_Collar", 0.67, 0.78, (0.13, 0.11), (0.15, 0.13), coat, open_deg=40, seg=24, rings=2, thick=0.01)
        # long coat tails down to the knees, open at the front for the legs
        skirt("Coat_Tails", 0.43, 0.17, (0.17, 0.13), (0.225, 0.19), coat, open_deg=24, seg=28, rings=4, thick=0.01,
              bulge=0.01)
        skirt("Coat_Lining", 0.4, 0.172, (0.16, 0.12), (0.21, 0.176), lining, open_deg=24, seg=28, rings=3, thick=0.004)
        torus("Coat_Belt", (0, 0, 0.43), 0.168, 0.016, coat2, scale=(1, 0.84, 1), seg=28)
        for s in (-1, 1):
            for k, z in enumerate((0.6, 0.5)):
                p, n = on(TC, ct, (s * 0.32, -1, (z - TC[2]) / TR[2]), 0.004)
                sph(f"Coat_Button{s}{k}", p, (0.012, 0.008, 0.012), coat2, rot=facing(n))
        ell("Hips", (0, 0, 0.39), (0.155, 0.125, 0.09), pants, seg=20, ring=10)
        torus("Belt", (0, 0, 0.42), 0.15, 0.016, bootm, scale=(1, 0.84, 1), seg=24)
        box("Belt_Buckle", (0, -0.128, 0.42), (0.044, 0.014, 0.03), buckle, bevel=0.005)
        # little silver eagle pin on the coat (he's the boss of S.H.I.E.L.D.)
        p, n = on(TC, ct, (-0.52, -1, 0.28), 0.0)
        ic = shape2d("Coat_Pin", [[(q[0] * 0.024, q[1] * 0.024) + tuple(q[2:]) for q in EAGLE]], eagle, depth=0.002,
                     bevel=0.0, res=2)
        stick(ic, coat_o, (0.165, -0.2, 0.49), (0.5, -1, 0.0), lift=0.002)

    SX, SZ = 0.21, 0.645
    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Shoulder_{side}", (s * 0.2, 0, 0.648), (0.062, 0.06, 0.06), coat)
            cyl_between(f"Sleeve_{side}", (s * 0.212, 0, 0.635), (s * 0.255, -0.022, 0.47), 0.048, coat, r2=0.054, seg=14)
            torus(f"Sleeve_{side}_Cuff", (s * 0.256, -0.023, 0.468), 0.05, 0.012, coat2, rot=(0.12, s * -0.25, 0))
            mitten(f"Hand_{side}", (s * 0.262, -0.03, 0.425), skin, size=0.048, s=s)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.085, 0, 0.33), (s * 0.088, 0, 0.12)], pants, r=0.058, caps=False)
            boot(side, s, 0.09, 0.0, bootm, sole, k=1.0, top=0.14)

    pivots = person_pivots(HZ - HR[2], SX, SZ, 0.085, 0.33)
    return dict(backdrop="e2dfdb", pivots=pivots, target=(0, 0, 0.6), dist=2.6, kind="friendly person", budget=7000)


# ====================================================================== 4. Lucky the pizza dog
def lucky():
    reset("Lucky")
    black, white = common_mats()
    fur = mat("Fur", "efa035", rough=0.45, coat=0.35)
    fur2 = mat("FurDeep", "cf7f22", rough=0.48, coat=0.3)
    cream = mat("Cream", "f6dfae", rough=0.5, coat=0.25)
    nose = mat("Nose", "1d1515", rough=0.1, coat=1.0)
    tongue = mat("Tongue", "ff7b8f", rough=0.35, coat=0.5)
    mouth = mat("Mouth", "4a2420", rough=0.4)
    collar = mat("Collar", "d93030", rough=0.35, coat=0.55)
    gold = mat("Tag", "f2c13a", rough=0.25, metal=0.8, coat=0.3)
    blush = mat("Blush", "ff9a8a", rough=0.6, coat=0.0)
    cheese = mat("Cheese", "ffd34d", rough=0.35, coat=0.5)
    crust = mat("Crust", "d98c3a", rough=0.5, coat=0.3)
    sauce = mat("Sauce", "e8452c", rough=0.35, coat=0.5)
    pepp = mat("Pepperoni", "c22a2a", rough=0.4, coat=0.5)
    basil = mat("Basil", "3fa34a", rough=0.4, coat=0.4)

    with limb("Body"):
        bc, br = (0, 0.06, 0.3), (0.15, 0.225, 0.14)
        bumps = [((0, -1, -0.15), 0.05, 0.45), ((0.35, -0.9, -0.55), 0.03, 0.3), ((-0.35, -0.9, -0.55), 0.03, 0.3)]
        for k, a in enumerate((20, 50, 80, 110, 140)):  # soft wavy coat along the back
            r = math.radians(a)
            bumps.append(((0.25 * (-1) ** k, -math.cos(r), math.sin(r)), 0.012, 0.2, (0, 0.006, 0)))
        for k, y in enumerate((-0.4, 0.0, 0.4)):  # feathering under the belly
            bumps.append(((0, y, -1), 0.03, 0.22, (0, 0, -0.01)))
        blob("Body", bc, br, fur, bumps, seg=30, ring=16)
        # fluffy cream chest ruff
        blob("Ruff", (0, -0.13, 0.33), (0.105, 0.08, 0.11), cream,
             [((0, -1, -0.4), 0.03, 0.4, (0, -0.01, -0.02)), ((0.5, -0.8, -0.6), 0.02, 0.3), ((-0.5, -0.8, -0.6), 0.02, 0.3)],
             seg=20, ring=10)
        torus("Collar", (0, -0.1, 0.42), 0.084, 0.02, collar, rot=(-0.75, 0, 0), scale=(1.05, 1, 1), seg=20)
        # gold tag shaped like a pizza slice
        tq = Quaternion((1, 0, 0), math.pi / 2 - 0.25)
        tag = shape2d("Tag", [[(0, -0.026, 1), (-0.02, 0.012, 1), (0.02, 0.012, 1)]], gold, depth=0.003, bevel=0.001,
                      poly=True)
        tag.rotation_mode = "QUATERNION"
        tag.rotation_quaternion = tq
        tag.location = (0.0, -0.175, 0.355)
        sph("Tag_Ring", (0.0, -0.17, 0.375), (0.008, 0.005, 0.008), gold)

    with limb("Head"):
        hc, hr = (0, -0.2, 0.525), (0.138, 0.125, 0.112)
        blob("Head", hc, hr, fur, [((0, 0.2, 1), 0.02, 0.45), ((-0.95, 0.1, -0.2), 0.025, 0.35),
                                   ((0.95, 0.1, -0.2), 0.025, 0.35)], seg=24, ring=12)
        mc, mr = (0, -0.31, 0.47), (0.075, 0.09, 0.058)
        sph("Muzzle", mc, mr, cream, seg=16, ring=8)
        sph("Muzzle_Top", (0, -0.28, 0.5), (0.06, 0.08, 0.04), fur, seg=14, ring=7)
        sph("Nose", (0, -0.393, 0.5), (0.03, 0.022, 0.024), nose)
        sph("Nose_Shine", (-0.01, -0.411, 0.51), (0.008, 0.004, 0.006), white)
        # his good eye, and a cute closed-eye patch on the other side (like a wink)
        eye("Eye_R", hc, hr, (0.4, -1, 0.2), 0.03, 0.037, black, white)
        decal("Eye_L_Patch", hc, hr, (-0.4, -1, 0.2), (0.05, 0.012, 0.046), fur2, sink=0.4)
        tube("Eye_L_Closed", arc_on(hc, hr, [(-0.28, -1, 0.2), (-0.4, -1, 0.14), (-0.52, -1, 0.2)], lift=0.008),
             black, r=0.0085)
        for s, side in sides():
            decal(f"Blush_{side}", hc, hr, (s * 0.62, -1, -0.15), (0.024, 0.007, 0.015), blush)
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.27, -1, 0.5), (s * 0.4, -1, 0.56), (s * 0.53, -1, 0.5)], lift=0.006),
                 fur2, r=0.01, caps=False)
            # long floppy retriever ears hanging flat against the head
            top = Vector((s * 0.112, -0.165, 0.6))
            bot = Vector((s * 0.15, -0.155, 0.45))
            q = aim(bot - top) @ Quaternion((0, 0, 1), 0.0)
            blob(f"Ear_{side}", (s * 0.138, -0.175, 0.505), (0.026, 0.056, 0.09), fur2, [((0, 0, -1), 0.012, 0.7)],
                 seg=14, ring=8, rot=Quaternion((0, 1, 0), -s * 0.32) @ Quaternion((1, 0, 0), 0.15), hero=False)
        tube("Smile", arc_on(mc, mr, [(t * 0.6, -1, -0.2 - 0.25 * (1 - t * t)) for t in (-1, -0.5, 0, 0.5, 1)]),
             mouth, r=0.006)
        sph("Tongue", (-0.025, -0.37, 0.42), (0.022, 0.012, 0.03), tongue, rot=Quaternion((0, 1, 0), 0.2))
        # a slice of pizza held in his mouth, sticking out to his right (crust at the far end)
        sq = Quaternion((0, 0, 1), -0.45) @ Quaternion((1, 0, 0), 0.25)
        pc = Vector((0.0, -0.37, 0.448))
        L, W = 0.2, 0.075
        sl = shape2d("Pizza", [[(-0.03, 0.0, 1), (L, W, 1), (L, -W, 1)]], cheese, depth=0.006, bevel=0.0025, poly=True)
        sl.rotation_mode = "QUATERNION"
        sl.rotation_quaternion = sq
        sl.location = pc
        tube("Pizza_Crust", [pc + sq @ Vector((L - 0.004, W + 0.008, 0.0)), pc + sq @ Vector((L + 0.012, 0.0, 0.002)),
                             pc + sq @ Vector((L - 0.004, -W - 0.008, 0.0))], crust, r=0.013, br=2)
        for k, (x, y) in enumerate([(0.07, 0.012), (0.135, -0.032), (0.145, 0.035)]):
            cyl(f"Pizza_Pepperoni{k}", pc + sq @ Vector((x, y, 0.0085)), 0.019, 0.004, pepp, rot=sq, seg=12, bevel=0.001)
        for k, (x, y) in enumerate([(0.1, 0.035), (0.17, 0.0)]):
            sph(f"Pizza_Basil{k}", pc + sq @ Vector((x, y, 0.008)), (0.011, 0.006, 0.0025), basil, rot=sq)
        # a stringy cheese drip off the side
        tube("Pizza_Drip", [pc + sq @ Vector((0.11, -0.045, 0.0)), pc + sq @ Vector((0.112, -0.05, -0.025)),
                            pc + sq @ Vector((0.11, -0.05, -0.045))], cheese, r=0.006, radii=[1, 0.9, 1.25])

    for s, side in sides():
        with limb("Leg" + side):  # front legs
            tube(f"Leg_{side}", [(s * 0.078, -0.1, 0.25), (s * 0.08, -0.11, 0.06)], fur, r=0.044, caps=False,
                 radii=[1.15, 0.9])
            sph(f"Leg_{side}_Feather", (s * 0.08, -0.07, 0.15), (0.03, 0.03, 0.055), fur)
            sph(f"Paw_{side}", (s * 0.081, -0.13, 0.034), (0.05, 0.062, 0.035), cream)
            for t in (-1, 0, 1):
                sph(f"Paw_{side}_Toe{t}", (s * 0.081 + t * 0.022, -0.183, 0.03), (0.014, 0.012, 0.012), cream)
        with limb("Leg" + side + "2"):  # back legs
            sph(f"Thigh_{side}", (s * 0.092, 0.19, 0.24), (0.068, 0.1, 0.095), fur)
            sph(f"Thigh_{side}_Feather", (s * 0.095, 0.27, 0.2), (0.04, 0.04, 0.06), fur)
            tube(f"Shin_{side}", [(s * 0.094, 0.21, 0.17), (s * 0.094, 0.21, 0.06)], fur, r=0.04, caps=False)
            sph(f"Paw2_{side}", (s * 0.094, 0.19, 0.034), (0.05, 0.064, 0.035), cream)

    with limb("Tail"):
        tube("Tail", [(0, 0.27, 0.34), (0, 0.35, 0.4), (0.03, 0.42, 0.47), (0.06, 0.46, 0.5)], fur, r=0.042,
             radii=[0.8, 1.0, 0.9, 0.6], br=2)
        tube("Tail_Feather", [(0, 0.3, 0.33), (0.0, 0.38, 0.37), (0.03, 0.45, 0.43)], cream, r=0.03, radii=[0.6, 0.9, 0.6])
        sph("Tail_Tip", (0.065, 0.465, 0.505), (0.03, 0.03, 0.03), cream)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.14, 0.43),
              "LegL": (-0.075, -0.1, 0.24), "LegR": (0.075, -0.1, 0.24),
              "LegL2": (-0.085, 0.2, 0.26), "LegR2": (0.085, 0.2, 0.26), "Tail": (0, 0.26, 0.34)}
    return dict(backdrop="f3e6d2", pivots=pivots, target=(0, 0.02, 0.32), dist=2.0, yaw=38, kind="friendly creature",
                budget=6000)


# ====================================================================== 5. Hydra agent
def hydra_agent():
    reset("HydraAgent")
    black, white = common_mats()
    skin = mat("Skin", "f0c09a", rough=0.45, coat=0.25, sss=0.12)
    mask = mat("Mask", "1b1d22", rough=0.4, coat=0.4)
    helm = mat("Helmet", "263a2c", rough=0.25, coat=0.75, metal=0.2)
    helm2 = mat("HelmetRim", "16201a", rough=0.3, coat=0.6)
    suit = mat("Suit", "2f4433", rough=0.45, coat=0.3)
    armor = mat("Armor", "1c1f24", rough=0.3, coat=0.6)
    armor2 = mat("ArmorEdge", "2c3138", rough=0.35, coat=0.5)
    red = mat("HydraRed", "e3222c", rough=0.3, coat=0.6)
    glove = mat("Glove", "15171b", rough=0.35, coat=0.5)
    bootm = mat("Boot", "15171b", rough=0.28, coat=0.65)
    sole = mat("Sole", "2c2f36", rough=0.6, coat=0.1)
    gun = mat("Blaster", "3a3f48", rough=0.25, metal=0.6, coat=0.5)
    gun2 = mat("BlasterDark", "1e2127", rough=0.3, metal=0.5, coat=0.5)
    glow = mat("TesseractGlow", "38c8ff", rough=0.15, coat=0.3, emit="1aa8ff", emit_strength=4)
    buckle = mat("Buckle", "c8ccd2", rough=0.2, metal=0.9, coat=0.3)

    HZ, HR = 0.9, (0.212, 0.198, 0.205)
    hc, hr = (0, 0, HZ), HR
    with limb("Head"):
        sph("Head", hc, hr, skin, seg=28, ring=14, hero=True)
        # black balaclava over the lower face (clean cut along a ring)
        ell("Mask", hc, (HR[0] + 0.006, HR[1] + 0.008, HR[2] + 0.004), mask, seg=28, ring=14,
            keep=lambda d: d.z < -0.2, hero=True)
        ell("Mask_Back", hc, (HR[0] + 0.004, HR[1] + 0.006, HR[2] + 0.003), mask, seg=28, ring=14,
            keep=lambda d: d.y > -0.25 or d.z < -0.2)
        # rounded combat helmet with a brow ridge and a crest
        hq = Quaternion((1, 0, 0), -0.22)
        hsph("Helmet", (0, 0.008, HZ + 0.012), (0.232, 0.222, 0.228), helm, keep_above=0.12, rot=hq, seg=28, ring=14,
             hero=True)
        k = 0.12
        rr = math.sqrt(1 - k * k)
        torus("Helmet_Rim", Vector((0, 0.008, HZ + 0.012)) + hq @ Vector((0, 0, 0.228 * k)), 1.0, 0.014, helm2,
              rot=hq, scale=(0.232 * rr + 0.004, 0.222 * rr + 0.004, 1.0), seg=28)
        tube("Helmet_Crest", arc_on((0, 0.008, HZ + 0.012), (0.232, 0.222, 0.228),
                                     [(0, -0.6, 0.8), (0, -0.2, 1), (0, 0.3, 0.95), (0, 0.7, 0.7)], lift=0.0),
             helm2, r=0.018, caps=False)
        hydra_emblem("Helmet_Emblem", bpy.data.objects["Helmet"], (0, -0.25, HZ + 0.12), (0, -1, 0.45), (0, 0.45, 1),
                     0.042, red)
        for s, side in sides():  # ear protectors
            cyl(f"Helmet_Ear_{side}", (s * 0.21, 0.01, HZ - 0.01), 0.05, 0.03, helm2, rot=Y90, seg=16)
        # cross cartoon eyes and heavy angry brows
        face_eyes(hc, hr, black, white, x=0.33, z=0.0, w=0.031, h=0.04)
        for s, side in sides():
            tube(f"Brow_{side}", arc_on(hc, hr, [(s * 0.14, -1, 0.12), (s * 0.33, -1, 0.2), (s * 0.52, -1, 0.21)],
                                         lift=0.005), mask, r=0.015, radii=[1.2, 1, 0.7], caps=False)
        # a hint of a frown through the mask
        tube("Mask_Frown", arc_on(hc, (HR[0] + 0.006, HR[1] + 0.008, HR[2] + 0.004),
                                   [(-0.12, -1, -0.5), (0, -1, -0.46), (0.12, -1, -0.5)], lift=0.002), helm2, r=0.006,
             caps=False)

    TC, TR = (0, 0, 0.535), (0.192, 0.142, 0.185)
    with limb("Body"):
        ell("Torso", TC, TR, suit, seg=24, ring=12, fn=taper(1.0, 0.82), hero=True)
        vt = (TR[0] + 0.018, TR[1] + 0.02, TR[2] + 0.01)
        vest = ell("Vest", TC, vt, armor, seg=24, ring=12, fn=taper(1.0, 0.82), keep=lambda d: -0.7 < d.z < 0.58)
        hydra_emblem("Chest_Emblem", vest, (0, -0.25, 0.56), (0, -1, 0.05), (0, 0, 1), 0.098, red)
        cyl("Collar", (0, 0, 0.705), 0.085, 0.05, armor2, r2=0.078, seg=18)
        for s, side in sides():
            tube(f"Vest_Strap_{side}", [(s * 0.1, -0.13, 0.62), (s * 0.108, -0.07, 0.69), (s * 0.112, 0.0, 0.712),
                                        (s * 0.108, 0.08, 0.68), (s * 0.1, 0.13, 0.62)], armor, r=0.02, caps=False)
            for k, x in enumerate((0.55, 0.8)):
                p, n = on(TC, vt, (s * x, -1, -0.62), 0.004)
                box(f"Pouch_{side}{k}", p, (0.05, 0.03, 0.06), armor2, bevel=0.01, rot=facing(n))
        ell("Hips", (0, 0, 0.385), (0.158, 0.128, 0.098), suit, seg=20, ring=10)
        torus("Belt", (0, 0, 0.405), 0.156, 0.022, armor, scale=(1, 0.84, 1), seg=24)
        box("Belt_Buckle", (0, -0.133, 0.405), (0.05, 0.016, 0.038), red, bevel=0.006)

    SX, SZ = 0.21, 0.64
    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Shoulder_{side}", (s * 0.205, 0, 0.645), (0.064, 0.062, 0.064), suit)
            hsph(f"Shoulder_{side}_Pad", (s * 0.215, 0, 0.655), (0.085, 0.085, 0.06), armor,
                 rot=Quaternion((0, 1, 0), s * 0.5), seg=16, ring=8)
            tube(f"Arm_{side}", [(s * 0.212, 0, 0.63), (s * 0.245, -0.012, 0.53), (s * 0.258, -0.026, 0.46)], suit,
                 r=0.043, radii=[1, 0.95, 0.9], caps=False)
            if s < 0:
                torus("Armband", (-0.235, -0.008, 0.57), 0.045, 0.014, red, rot=(0, -0.3, 0), seg=14)
            torus(f"Glove_{side}_Cuff", (s * 0.258, -0.027, 0.455), 0.042, 0.015, glove)
            if s < 0:
                mitten(f"Hand_{side}", (s * 0.262, -0.03, 0.415), glove, size=0.05, s=s)
            else:
                # gripping the blaster: a fist round the grip
                sph("Hand_R", (0.262, -0.035, 0.41), (0.05, 0.05, 0.052), glove, seg=14, ring=7)
                bq = Quaternion((1, 0, 0), 0.0)
                gp = Vector((0.262, -0.05, 0.43))
                box("Blaster_Grip", gp + Vector((0, 0.01, -0.02)), (0.028, 0.035, 0.07), gun2, bevel=0.01,
                    rot=(0.25, 0, 0))
                box("Blaster_Body", gp + Vector((0, -0.06, 0.03)), (0.058, 0.17, 0.07), gun, bevel=0.018)
                box("Blaster_Top", gp + Vector((0, -0.03, 0.072)), (0.034, 0.1, 0.022), gun2, bevel=0.009)
                box("Blaster_Sight", gp + Vector((0, -0.005, 0.09)), (0.016, 0.03, 0.022), gun2, bevel=0.006)
                for kk in (-1, 1):  # side fins
                    box(f"Blaster_Fin{kk}", gp + Vector((kk * 0.034, -0.1, 0.03)), (0.012, 0.07, 0.05), gun2, bevel=0.006)
                cyl("Blaster_Barrel", gp + Vector((0, -0.175, 0.035)), 0.024, 0.06, gun2, rot=X90, seg=12)
                for kk in range(2):  # glowing energy rings
                    torus(f"Blaster_Coil{kk}", gp + Vector((0, -0.16 - kk * 0.026, 0.035)), 0.028, 0.007, glow,
                          rot=(math.pi / 2, 0, 0), seg=12, mseg=4)
                sph("Blaster_Muzzle", gp + Vector((0, -0.207, 0.035)), (0.02, 0.01, 0.02), glow)
                box("Blaster_Cell", gp + Vector((0, 0.035, 0.035)), (0.04, 0.02, 0.045), glow, bevel=0.008)
                box("Blaster_Stripe", gp + Vector((0.03, -0.06, 0.03)), (0.004, 0.1, 0.014), red, bevel=0.002)
        with limb("Leg" + side):
            tube(f"Leg_{side}", [(s * 0.088, 0, 0.33), (s * 0.09, 0, 0.12)], suit, r=0.062, caps=False)
            sph(f"Knee_{side}", (s * 0.09, -0.052, 0.215), (0.05, 0.026, 0.05), armor)
            boot(side, s, 0.092, 0.0, bootm, sole, k=1.0, top=0.16)

    pivots = person_pivots(HZ - HR[2], SX, SZ, 0.088, 0.33)
    return dict(backdrop="f0dcdc", pivots=pivots, target=(0, 0, 0.58), dist=2.5, kind="aggressive person", budget=7000)


# ====================================================================== 6. Ultron sentry
def ultron_sentry():
    reset("UltronSentry")
    black, white = common_mats()
    chrome = mat("Chrome", "dfe4ec", rough=0.26, metal=1.0, coat=0.5)
    chrome2 = mat("ChromeShade", "aab2be", rough=0.3, metal=1.0, coat=0.4)
    dark = mat("Gunmetal", "3c414c", rough=0.3, metal=0.8, coat=0.4)
    darker = mat("Joint", "23262d", rough=0.35, metal=0.6, coat=0.4)
    red = mat("RedGlow", "e00000", rough=0.2, coat=0.3, emit="ff0000", emit_strength=1.6)
    red2 = mat("RedRing", "a80000", rough=0.25, coat=0.6, emit="ff0000", emit_strength=0.5)

    HZ, HR = 0.97, (0.19, 0.172, 0.205)
    hc = Vector((0, 0, HZ))
    hfn = taper(1.0, 0.72)
    with limb("Head"):
        head = ell("Head", hc, HR, chrome, seg=28, ring=14, fn=hfn, hero=True)
        # crest fin from the brow over the top, cheek plates, ear discs
        tube("Crest", arc_on(hc, HR, [(0, -0.75, 0.62), (0, -0.3, 0.97), (0, 0.25, 0.97), (0, 0.7, 0.7)], lift=-0.004),
             chrome2, r=0.022, radii=[0.5, 1, 1, 0.6], caps=True, br=2)
        for s, side in sides():
            cyl(f"Ear_{side}", (s * 0.185, 0.0, HZ - 0.01), 0.055, 0.03, dark, rot=Y90, seg=16)
            cyl(f"Ear_{side}_Glow", (s * 0.2, 0.0, HZ - 0.01), 0.026, 0.01, red2, rot=Y90, seg=12)
            # angled dark brow plate and an angry glowing eye
            p, n = on(hc, HR, (s * 0.36, -1, 0.1), 0.0)
            pts = [(-1.0, -0.15, 1), (0.25, 0.32), (1.0, 0.42, 1), (0.7, -0.18), (-0.3, -0.42)]
            pts = [(x * s * 0.05, y * 0.034) + tuple(r[2:]) for (x, y, *r) in [(q[0], q[1]) + tuple(q[2:]) for q in pts]]
            if s < 0:
                pts = pts[::-1]
            sock = shape2d(f"Eye_{side}_Socket", [[(x * 1.18, y * 1.3 + 0.002) + tuple(r) for (x, y, *r) in pts]], darker,
                           depth=0.002, bevel=0.0, res=3)
            stick(sock, head, p, n, lift=0.0, subdiv=1)
            ey = shape2d(f"Eye_{side}", [pts], red, depth=0.002, bevel=0.0, res=3)
            stick(ey, head, p, n, lift=0.004, subdiv=1)
        tube("Nose_Ridge", arc_on(hc, HR, [(0, -1, 0.15), (0, -1, -0.05), (0, -1, -0.22)], lift=0.002), chrome2,
             r=0.012, radii=[0.6, 1, 0.8])
        # glowing jagged grin across the lower face
        p, n = on(hc, HR, (0, -1, -0.42), 0.0)
        g = []
        for i in range(9):
            x = -1 + i / 4
            g.append((x * 0.075, (0.012 if i % 2 == 0 else -0.012) - 0.018 * (1 - x * x), 1))
        g2 = [(x, y - 0.018 - 0.004 * (1 - (x / 0.075) ** 2), 1) for x, y, _ in reversed(g)]
        mouth = shape2d("Grin", [g + g2], red, depth=0.002, bevel=0.0, poly=True)
        stick(mouth, head, p, n, lift=0.003, subdiv=1)

    with limb("Jaw"):
        jc, jr = Vector((0, -0.085, HZ - 0.15)), (0.085, 0.07, 0.04)
        ell("Jaw", jc, jr, chrome, seg=16, ring=8)
        sph("Jaw_Chin", jc + Vector((0, -0.045, -0.006)), (0.045, 0.026, 0.03), chrome2)

    TC, TR = Vector((0, 0, 0.57)), (0.185, 0.13, 0.18)
    with limb("Body"):
        torso = ell("Torso", TC, TR, chrome, seg=24, ring=12, fn=taper(1.0, 0.62), hero=True)
        cyl("Neck", (0, 0, 0.77), 0.05, 0.12, darker, seg=12)
        for k in range(3):
            torus(f"Neck_Ring{k}", (0, 0, 0.74 + k * 0.03), 0.052, 0.008, dark, seg=12, mseg=4)
        # chest plate seams in a V
        for s_, side in sides():
            tube(f"Chest_Seam_{side}", arc_on(TC, TR, [(s_ * 0.75, -1, 0.75), (s_ * 0.35, -1, 0.1), (s_ * 0.05, -1, -0.45)],
                                              lift=0.0), darker, r=0.006, caps=False)
        # glowing core
        p, n = on(TC, TR, (0, -1, 0.15), 0.0)
        cyl("Core_Housing", p + n * 0.004, 0.05, 0.03, darker, rot=aim(n), seg=18)
        torus("Core_Ring", p + n * 0.02, 0.04, 0.009, red2, rot=aim(n), seg=18)
        sph("Core", p + n * 0.018, (0.03, 0.03, 0.014), red, rot=aim(n), seg=14, ring=7)
        # segmented abdomen, hips
        for k, z in enumerate((0.43, 0.395)):
            torus(f"Abs{k}", (0, 0, z), 0.12 - k * 0.006, 0.026, dark, scale=(1, 0.8, 1), seg=20)
        ell("Hips", (0, 0, 0.36), (0.14, 0.11, 0.075), chrome, seg=20, ring=10)
        p, n = on((0, 0, 0.36), (0.14, 0.11, 0.075), (0, -1, 0), 0.0)
        box("Hips_Plate", p + n * 0.006, (0.06, 0.012, 0.05), chrome2, bevel=0.01)

    SX, SZ = 0.215, 0.655
    for s, side in sides():
        with limb("Arm" + side):
            sph(f"Shoulder_{side}", (s * 0.21, 0, 0.66), (0.06, 0.06, 0.06), darker)
            hsph(f"Shoulder_{side}_Plate", (s * 0.22, 0, 0.672), (0.075, 0.072, 0.055), chrome,
                 rot=Quaternion((0, 1, 0), s * 0.55), seg=16, ring=8)
            cyl_between(f"UpperArm_{side}", (s * 0.225, 0, 0.64), (s * 0.245, -0.008, 0.55), 0.036, chrome, r2=0.032, seg=12)
            sph(f"Elbow_{side}", (s * 0.247, -0.01, 0.545), (0.032, 0.032, 0.032), darker)
            cyl_between(f"Forearm_{side}", (s * 0.249, -0.012, 0.54), (s * 0.258, -0.025, 0.445), 0.036, chrome2,
                        r2=0.042, seg=12)
            torus(f"Wrist_{side}", (s * 0.259, -0.026, 0.44), 0.035, 0.009, red2, seg=12, mseg=4)
            sph(f"Hand_{side}", (s * 0.262, -0.03, 0.405), (0.045, 0.042, 0.05), chrome, seg=14, ring=7)
            for f in range(3):
                sph(f"Hand_{side}_Knuckle{f}", (s * 0.262 + (f - 1) * 0.022 * s, -0.064, 0.395),
                    (0.012, 0.012, 0.016), chrome2, seg=8, ring=4)
        with limb("Leg" + side):
            sph(f"Hip_{side}", (s * 0.085, 0, 0.335), (0.05, 0.05, 0.05), darker)
            cyl_between(f"Thigh_{side}", (s * 0.087, 0, 0.32), (s * 0.09, -0.004, 0.2), 0.052, chrome, r2=0.044, seg=14)
            sph(f"Knee_{side}", (s * 0.09, -0.02, 0.19), (0.042, 0.036, 0.04), dark)
            cyl_between(f"Shin_{side}", (s * 0.09, 0, 0.185), (s * 0.092, 0, 0.07), 0.044, chrome2, r2=0.05, seg=14)
            box(f"Foot_{side}", (s * 0.092, -0.035, 0.035), (0.09, 0.17, 0.07), chrome, bevel=0.03)
            box(f"Foot_{side}_Toe", (s * 0.092, -0.108, 0.025), (0.08, 0.04, 0.05), dark, bevel=0.016)

    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 0.78), "Jaw": (0, 0.0, HZ - 0.13),
              "ArmL": (-SX, 0, SZ), "ArmR": (SX, 0, SZ), "LegL": (-0.085, 0, 0.335), "LegR": (0.085, 0, 0.335)}
    return dict(backdrop="e6e1e4", pivots=pivots, parents={"Jaw": "Head"}, target=(0, 0, 0.6), dist=2.6,
                kind="aggressive creature", budget=7000)


# ====================================================================== 7. Symbiote
VENOM_EYE = [(-0.42, 0.05), (-0.36, -0.28), (0.0, -0.42), (0.45, -0.22), (0.82, 0.25), (1.05, 0.78, 1), (0.5, 0.42),
             (0.02, 0.32), (-0.34, 0.28)]


def symbiote():
    reset("Symbiote")
    black, white = common_mats()
    goo = mat("Symbiote", "151a2b", rough=0.08, coat=1.0, metal=0.0)
    goo2 = mat("SymbioteSheen", "27304f", rough=0.12, coat=1.0)
    eyew = mat("EyeWhite", "f6f8ff", rough=0.15, coat=0.9)
    mouth = mat("MouthInside", "5a0f1e", rough=0.35, coat=0.5)
    tooth = mat("Teeth", "fbf8ee", rough=0.2, coat=0.9)
    tongue = mat("Tongue", "ff6f8f", rough=0.25, coat=0.7)
    spider = mat("SpiderWhite", "eef2ff", rough=0.25, coat=0.8)

    sq, rz = -0.5, 0.22
    cz = -rz * (sq + (-1 - sq) * 0.35)
    bc, br = Vector((0, 0, cz)), (0.3, 0.27, rz)
    with limb("Body"):
        bumps = [((0, 0, 1), 0.04, 0.6), ((0, -1, 0.35), 0.03, 0.5)]
        for k in range(8):  # gloopy drips round the bottom edge
            a = 2 * math.pi * k / 8 + 0.2
            bumps.append(((math.cos(a), math.sin(a), -0.35), 0.022 + 0.012 * (k % 2), 0.2, (0, 0, -0.014)))
        body = blob("Body", bc, br, goo, bumps, seg=40, ring=24, squash_below=sq)
        sph("Puddle", (0, 0.0, 0.01), (0.33, 0.3, 0.014), goo2, seg=24, ring=6)
        # big white Venom eyes
        for s, side in sides():
            pts = [(x * s * 0.1, y * 0.1) + tuple(r) for (x, y, *r) in VENOM_EYE]
            if s < 0:
                pts = pts[::-1]
            e = shape2d(f"Eye_{side}", [pts], eyew, depth=0.003, bevel=0.0, res=3)
            stick(e, body, (s * 0.088, -0.4, cz + 0.205), (s * 0.3, -1, 1.1), lift=0.001, subdiv=2)
        # wide toothy grin
        F = Frame(body, (0, -0.4, cz + 0.02), (0, -1, 0.15))
        W = 0.19
        upper = [(W * t, 0.025 - 0.02 * (1 - t * t)) for t in [i / 8 for i in range(-8, 9)]]
        lower = [(W * t, 0.025 - 0.11 * (1 - t * t) ** 0.8) for t in [i / 8 for i in range(8, -9, -1)]]
        mo = shape2d("Mouth", [[(x, y, 1) for x, y in upper + lower]], mouth, depth=0.003, bevel=0.0, poly=True)
        stick(mo, body, F.o, F.n, (0, 0, 1), lift=0.0, subdiv=2)
        for i in range(7):  # top teeth pointing down
            t = -0.78 + i * 0.26
            x, y = W * t, 0.025 - 0.02 * (1 - t * t)
            p, n = F.at(x, y, 0.002)
            cone(f"Tooth_Top{i}", p, -F.u + n * 0.25, 0.02, 0.045 - 0.014 * abs(t), tooth, seg=8)
        for i in range(6):  # bottom teeth pointing up
            t = -0.66 + i * 0.264
            x, y = W * t, 0.025 - 0.11 * (1 - t * t) ** 0.8
            p, n = F.at(x, y, 0.002)
            cone(f"Tooth_Bot{i}", p, F.u + n * 0.25, 0.017, 0.036 - 0.01 * abs(t), tooth, seg=8)
        # long goofy tongue lolling out the side
        p0, n0 = F.at(0.05, -0.045, 0.0)
        tube("Tongue", [p0 - n0 * 0.01, p0 + n0 * 0.04 + Vector((0.02, 0, -0.01)), p0 + n0 * 0.065 + Vector((0.06, 0, -0.045)),
                        p0 + n0 * 0.065 + Vector((0.085, 0, -0.07))], tongue, r=0.026, radii=[0.9, 1, 0.95, 0.85], br=2)
        # glossy highlights
        for k, (d, sz) in enumerate([((-0.5, -0.5, 0.85), (0.06, 0.01, 0.025)), ((-0.3, -0.7, 0.75), (0.018, 0.006, 0.018))]):
            decal(f"Shine_{k}", bc, br, d, sz, goo2, sink=0.1)
        # white spider emblem on its back
        Fb = Frame(body, (0, 0.4, cz + 0.2), (0, 1, 1.0), (0, 0, 1))
        sp = []
        sp.append(shape2d("Spider_Body", [circle_pts(0.032, 12, 0, -0.005)], spider, depth=0.002, bevel=0.0, poly=True))
        sp.append(shape2d("Spider_Head", [circle_pts(0.02, 10, 0, 0.042)], spider, depth=0.002, bevel=0.0, poly=True))
        for sx in (-1, 1):
            for j, (a0, a1, a2) in enumerate([((0.02, 0.04), (0.08, 0.1), (0.1, 0.17)), ((0.025, 0.02), (0.1, 0.05), (0.15, 0.11)),
                                              ((0.025, -0.01), (0.1, -0.04), (0.15, -0.1)), ((0.02, -0.03), (0.08, -0.09), (0.1, -0.16))]):
                pts = [(sx * a0[0], a0[1]), (sx * a1[0], a1[1]), (sx * a2[0], a2[1])]
                sp.append(shape2d(f"Spider_Leg{sx}{j}", [stroke(pts, 0.011, 0.006)], spider, depth=0.002, bevel=0.0,
                                  poly=True))
        for o in sp:
            stick(o, body, Fb.o, Fb.n, (0, 0, 1), lift=0.002, subdiv=1)

    # Blob parts (origins where they join the body so they squish into it): wiggly tendrils
    with limb("BlobTop"):
        top = Vector((0, 0.01, cz + rz))
        sph("BlobTop", top + Vector((0, 0, 0.02)), (0.075, 0.07, 0.05), goo)
        tube("BlobTop_Tendril", [top + Vector((0, 0, 0.03)), top + Vector((0.02, 0.01, 0.1)), top + Vector((-0.02, 0.02, 0.16)),
                                  top + Vector((-0.06, 0.02, 0.17))], goo, r=0.032, radii=[1, 0.7, 0.45, 0.25], br=2)
    for s, side in sides():
        with limb("Blob" + side):
            base = Vector((s * 0.27, -0.02, 0.11))
            sph(f"Blob_{side}", base, (0.08, 0.07, 0.065), goo)
            tube(f"Blob_{side}_Tendril", [base + Vector((s * 0.03, 0, 0.02)), base + Vector((s * 0.1, -0.02, 0.07)),
                                           base + Vector((s * 0.13, -0.03, 0.15)), base + Vector((s * 0.1, -0.04, 0.2))], goo,
                 r=0.03, radii=[1, 0.75, 0.5, 0.3], br=2)
            sph(f"Blob_{side}_Drop", base + Vector((s * 0.07, -0.02, -0.07)), (0.04, 0.038, 0.035), goo)
    with limb("BlobBack"):
        bb = Vector((0.02, 0.26, 0.13))
        sph("BlobBack", bb, (0.1, 0.07, 0.08), goo)
        for k, sx in enumerate((-1, 1)):
            tube(f"BlobBack_Tendril{k}", [bb + Vector((sx * 0.03, 0.03, 0.03)), bb + Vector((sx * 0.07, 0.1, 0.08)),
                                          bb + Vector((sx * 0.06, 0.15, 0.16)), bb + Vector((sx * 0.02, 0.16, 0.2))], goo,
                 r=0.026, radii=[1, 0.7, 0.45, 0.25], br=2)

    pivots = {"Body": (0, 0, 0), "BlobTop": (0, 0.01, cz + rz - 0.01),
              "BlobL": (-0.24, -0.02, 0.11), "BlobR": (0.24, -0.02, 0.11), "BlobBack": (0.02, 0.21, 0.12)}
    return dict(backdrop="e4e2f0", pivots=pivots, target=(0, 0, 0.22), dist=1.75, yaw=28, kind="aggressive creature",
                budget=6500)


# ====================================================================== 8. Spider drone
def spider_drone():
    reset("SpiderDrone")
    black, white = common_mats()
    shell = mat("Carapace", "2a2e36", rough=0.18, metal=0.5, coat=0.9)
    shell2 = mat("Underside", "1b1d22", rough=0.35, metal=0.5, coat=0.4)
    green = mat("OscorpGreen", "2fa25a", rough=0.22, metal=0.3, coat=0.8)
    gold = mat("Gold", "e0ad45", rough=0.22, metal=0.9, coat=0.4)
    steel = mat("Steel", "aeb6c2", rough=0.22, metal=0.95, coat=0.3)
    glow = mat("GreenGlow", "00d43a", rough=0.15, coat=0.3, emit="00ff3c", emit_strength=1.6)
    glow2 = mat("GreenGlowSoft", "0a9a30", rough=0.2, coat=0.5, emit="00ff3c", emit_strength=0.5)

    bcen = Vector((0, 0.03, 0.3))
    with limb("Body"):
        hull = ell("Hull", bcen, (0.19, 0.21, 0.1), shell, seg=28, ring=14, hero=True,
                   fn=lambda d: (1.0, 1.0, 1.0 if d.z > 0 else 0.7))
        ell("Hull_Green", bcen + Vector((0, 0, 0.004)), (0.193, 0.213, 0.1), green, seg=28, ring=14,
            fn=lambda d: (1.0, 1.0, 1.0), keep=lambda d: abs(d.z) < 0.28)
        # raised spine plates and gold trim
        for k, (y, w) in enumerate([(-0.1, 0.06), (0.0, 0.075), (0.1, 0.06)]):
            p, n = on(bcen, (0.19, 0.21, 0.1), (0, y / 0.21, 1), 0.0)
            box(f"Spine_Plate{k}", p + n * 0.006, (w * 1.6, 0.06, 0.02), shell2, bevel=0.008, rot=facing(n) @ X90.inverted()
                if False else Quaternion((1, 0, 0), -y * 2.5))
            box(f"Spine_Glow{k}", p + n * 0.017, (w * 0.9, 0.02, 0.008), glow2, bevel=0.003,
                rot=Quaternion((1, 0, 0), -y * 2.5))
        sph("Underside", bcen + Vector((0, 0, -0.045)), (0.15, 0.17, 0.05), shell2)
        # abdomen pod with a glowing hex core
        ac, ar = Vector((0, 0.27, 0.33)), (0.14, 0.16, 0.12)
        ell("Abdomen", ac, ar, shell, seg=24, ring=12, fn=lambda d: (1.0, 1.0, 1.0 if d.z > 0 else 0.8))
        for k, dy in enumerate((-0.06, 0.05)):
            f = math.sqrt(1 - (dy / ar[1]) ** 2)
            torus(f"Abdomen_Band{k}", ac + Vector((0, dy, 0)), ar[0] * f, 0.012, gold, rot=(math.pi / 2, 0, 0),
                  scale=(1, ar[2] / ar[0], 1), seg=20)
        p, n = on(ac, ar, (0, 0.1, 1), 0.0)
        cyl("Core_Housing", p, 0.05, 0.03, shell2, rot=aim(n), seg=6, bevel=0.006)
        cyl("Core", p + n * 0.016, 0.036, 0.012, glow, rot=aim(n), seg=6, bevel=0.003)
        cyl("Stinger_Base", ac + Vector((0, 0.15, -0.03)), 0.03, 0.04, gold, rot=aim((0, 1, 0.2)), seg=10)
        cone("Stinger", ac + Vector((0, 0.17, -0.025)), (0, 1, -0.3), 0.022, 0.07, steel, seg=8)

    with limb("Head"):
        tc = Vector((0, -0.2, 0.31))
        head = ell("Head", tc, (0.105, 0.09, 0.075), shell, seg=20, ring=10)
        ell("Head_Visor", tc + Vector((0, -0.01, 0.0)), (0.108, 0.093, 0.078), green, seg=20, ring=10,
            keep=lambda d: d.z > 0.35)
        # cluster of glowing eyes: two big, four small
        for s in (-1, 1):
            p, n = on(tc, (0.105, 0.09, 0.075), (s * 0.35, -1, 0.15), 0.0)
            cyl(f"Eye_Big{s}_Rim", p, 0.03, 0.016, gold, rot=aim(n), seg=14)
            sph(f"Eye_Big{s}", p + n * 0.008, (0.024, 0.024, 0.012), glow, rot=aim(n))
            sph(f"Eye_Big{s}_Shine", p + n * 0.016 + Vector((-0.008, 0, 0.008)), (0.006, 0.003, 0.006), white)
            for k, (dx, dz) in enumerate([(0.7, 0.35), (0.75, -0.15)]):
                p2, n2 = on(tc, (0.105, 0.09, 0.075), (s * dx, -1, dz), 0.0)
                sph(f"Eye_Small{s}{k}", p2, (0.012, 0.008, 0.012), glow, rot=facing(n2))
            # gold pincer mandibles
            m0 = tc + Vector((s * 0.035, -0.075, -0.04))
            tube(f"Mandible{s}", [m0, m0 + Vector((s * 0.02, -0.03, -0.02)), m0 + Vector((-s * 0.005, -0.055, -0.03))], gold,
                 r=0.011, radii=[1, 0.8, 0.4])

    for s, side in sides():
        for i, a in enumerate((-48, -16, 16, 46)):
            ar_ = math.radians(a)
            d = Vector((s * math.cos(ar_), math.sin(ar_), 0))
            hip = bcen + Vector((d.x * 0.17, d.y * 0.19, 0.0))
            knee = hip + d * 0.17 + Vector((0, 0, 0.15))
            foot = hip + d * 0.36 + Vector((0, 0, -0.3 + 0.004))
            nm = f"Leg{side}{i + 1}"
            with limb(nm):
                sph(f"{nm}_Hip", hip, (0.036, 0.036, 0.036), gold)
                tube(f"{nm}_Femur", [hip, hip + d * 0.07 + Vector((0, 0, 0.12)), knee], shell, r=0.022, caps=False, br=2)
                for k, t in enumerate((0.35, 0.65)):  # segment rings, Doc Ock style
                    pos = hip.lerp(knee, t) + Vector((0, 0, 0.035 if t < 0.5 else 0.03))
                    torus(f"{nm}_Ring{k}", pos, 0.025, 0.009, green, rot=aim(knee - hip), seg=10, mseg=4)
                sph(f"{nm}_Knee", knee, (0.03, 0.03, 0.03), gold)
                tube(f"{nm}_Shin", [knee, knee + d * 0.11 + Vector((0, 0, -0.1)), foot + Vector((0, 0, 0.04))], shell,
                     r=0.022, radii=[1, 0.85, 0.6], caps=False, br=2)
                sph(f"{nm}_Ankle", foot + Vector((0, 0, 0.04)), (0.016, 0.016, 0.016), green)
                cone(f"{nm}_Claw", foot + Vector((0, 0, 0.045)), (d.x * 0.25, d.y * 0.25, -1), 0.016, 0.05, steel, seg=8)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.14, 0.3)}
    for s, side in sides():
        for i, a in enumerate((-48, -16, 16, 46)):
            ar_ = math.radians(a)
            pivots[f"Leg{side}{i + 1}"] = (bcen.x + s * math.cos(ar_) * 0.17, bcen.y + math.sin(ar_) * 0.19, bcen.z)
    return dict(backdrop="dfe8e2", pivots=pivots, target=(0, 0.02, 0.22), dist=2.0, yaw=35, pitch=22,
                kind="aggressive creature", budget=6000)


# ====================================================================== runner
CHARS = {"civilian": civilian, "shield_agent": shield_agent, "nick_fury": nick_fury, "lucky": lucky, "hydra_agent": hydra_agent, "ultron_sentry": ultron_sentry, "symbiote": symbiote, "spider_drone": spider_drone}


def build(name, budget=6000):
    fast = "--fast" in sys.argv
    concept = os.path.join(ROOT, "concepts", f"npc_{name}.png")
    portrait = os.path.join(ROOT, "assets", "portraits", f"npc_{name}.png")
    if not fast:
        npc_kit.DETAIL[0] = 1.0
        opts = CHARS[name]()
        finalize()
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        cam_at(opts["target"], opts["dist"], opts.get("yaw", 32), opts.get("pitch", 14))
        render(concept, 1024, samples=96)
        downscale(concept, portrait, 320)
    npc_kit.DETAIL[0] = 1.0
    budget = None
    for attempt in range(5):
        opts = CHARS[name]()
        finalize()
        budget = opts.get("budget", 6000)
        total = sum(tri_report().values())
        print(f"BUDGET {name} detail={npc_kit.DETAIL[0]:.2f} tris={total}")
        if total <= budget:
            break
        if npc_kit.DETAIL[0] <= 0.5:
            print(f"WARNING {name} over budget at the detail floor")
            break
        npc_kit.DETAIL[0] = max(0.5, npc_kit.DETAIL[0] * (budget / total) ** 1.2 * 0.97)
    if os.environ.get("NPC_DEBUG"):
        objs = sorted(mesh_objs(), key=lambda o: -len(o.data.loop_triangles))
        print("HEAVY", [(o.name, len(o.data.loop_triangles)) for o in objs[:18]])
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
        cam_at(tgt, dist, 25, 35)
        small = os.path.join(SCRATCH, f"{name}_small.png")
        render(small, 72, samples=16)
        views.append(small)
        contact_sheet(views, os.path.join(SCRATCH, f"{name}_sheet.png"), cols=3, cell=420)
        cam_at(tgt, dist * 0.6, opts.get("yaw", 32), 10)
        render(os.path.join(SCRATCH, f"{name}_close.png"), 900, samples=48)
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
