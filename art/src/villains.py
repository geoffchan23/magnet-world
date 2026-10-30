# Bad guys for Magnet World: toy-real collectible-figure versions of Thanos and his crew.
# Run one:  blender --background --python art/src/villains.py -- thanos
# Run all:  blender --background --python art/src/villains.py -- all
# (add --fast to skip the concept render; set NPC_SCRATCH=<dir> for multi-view check sheets)
# Each run writes art/characters/npc_<id>.blend, concepts/npc_<id>.png,
# assets/portraits/npc_<id>.png (320px) and assets/characters/npc_<id>.glb.
#
# Same conventions as npcs.py: Blender faces -Y, feet on z=0, L = -X, kid units (kid ~0.97 tall,
# the game scales by 0.55). Every limb is one node with its origin at the joint and identity
# rotation/scale. Bipeds: Body/Head/ArmL/ArmR/LegL/LegR, weapons ride on ArmR and the arm's
# lowest point is the hand. The outrider is a four-legged runner: front legs LegL/LegR, back legs
# LegL2/LegR2, plus its upper pair of arms as ArmL/ArmR (they swing and do the strike) and a Jaw.
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import npc_kit
importlib.reload(npc_kit)
from npc_kit import *
from npc_kit import _d, FLOOR, DETAIL
import bpy, bmesh
from mathutils import Vector, Quaternion, Euler, Matrix

SCRATCH = os.environ.get("NPC_SCRATCH", "")
X90 = Quaternion((1, 0, 0), math.pi / 2)
Y90 = Quaternion((0, 1, 0), math.pi / 2)
Z90 = Quaternion((0, 0, 1), math.pi / 2)
V = Vector


def sides():
    return ((-1, "L"), (1, "R"))


# ====================================================================== extra primitives
def _crease(me, angle=40):
    """Hard edges where faces meet at more than `angle` degrees; soft everywhere else."""
    for p in me.polygons:
        p.use_smooth = True
    try:
        me.set_sharpness_by_angle(angle=math.radians(angle))
    except Exception:
        pass


def _cut_rim(bm, cuts, c, thick, inward=True):
    """Trim a bmesh by planes [(point, normal)] (normal side removed), then fold the cut edges into
    a rim `thick` deep so the open edge reads as a solid moulded plate. Returns the rim edges."""
    for co, no in cuts:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=V(co) - V(c), plane_no=V(no).normalized(), clear_outer=True)
    bm.normal_update()
    rim = [e for e in bm.edges if e.is_boundary]
    if rim and thick > 0:
        src = {tuple(round(x, 6) for x in v.co): v.normal.copy() for e in rim for v in e.verts}
        res = bmesh.ops.extrude_edge_only(bm, edges=rim)
        for v in [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]:
            n = src.get(tuple(round(x, 6) for x in v.co), V((0, 0, 0)))
            v.co -= n * thick * (1 if inward else -1)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return rim


def lathe(name, prof, m, loc=(0, 0, 0), seg=24, rot=None, scale=None, crease=50, cuts=(), thick=0.012,
          sx=1.0, sy=1.0, caps=True):
    """Surface of revolution about local Z from a (radius, z) profile, bottom to top.
    A radius of 0 makes a pole; otherwise the ends are closed with flat caps."""
    seg = _d(seg, max(8, int(seg * 0.6)))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, z in prof:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z))
                          for i in range(seg)])
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(seg):
            j = (i + 1) % seg
            if len(a) == 1:
                bm.faces.new((a[0], b[j], b[i]))
            elif len(b) == 1:
                bm.faces.new((a[i], a[j], b[0]))
            else:
                bm.faces.new((a[i], a[j], b[j], b[i]))
    if len(rings[0]) > 1 and caps:
        bm.faces.new(list(reversed(rings[0])))
    if len(rings[-1]) > 1 and caps:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if sx != 1.0 or sy != 1.0:
        bmesh.ops.scale(bm, vec=(sx, sy, 1.0), verts=bm.verts)
    rim = _cut_rim(bm, cuts, loc, thick) if cuts else []
    bm.to_mesh(me)
    bm.free()
    _crease(me, crease)
    o = toykit._obj(name, me, m, loc)
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot if isinstance(rot, Quaternion) else Euler(rot).to_quaternion()
    if scale is not None:
        o.scale = scale
    return o


def _smooth2d(pts, n=4):
    """Catmull-Rom resample of a 2D/3D polyline (passes through every point)."""
    pts = [V(p) for p in pts]
    if len(pts) < 3:
        return pts
    out = []
    ext = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(pts[-1])
    return out


def ribbon2d(center, widths, n=4, tip=True):
    """Outline (x, z) of a tapering curved blade/horn around a 2D centreline.
    widths are half-widths per centreline point; tip=True closes to a point at the end."""
    n = max(2, int(round(n * DETAIL[0])))
    c = _smooth2d([V((p[0], p[1], 0)) for p in center], n)
    w = _smooth2d([V((x, 0, 0)) for x in widths], n)
    w = [v.x for v in w]
    left, right = [], []
    for i, p in enumerate(c):
        a = c[max(0, i - 1)]
        b = c[min(len(c) - 1, i + 1)]
        t = (b - a).normalized()
        nrm = V((-t.y, t.x, 0))
        if tip and i == len(c) - 1:
            left.append(p)
            continue
        left.append(p + nrm * w[i])
        right.append(p - nrm * w[i])
    pts = left + list(reversed(right))
    return [(p.x, p.y) for p in pts]


def slab(name, poly, depth, m, loc=(0, 0, 0), rot=None, bevel=0.01, segs=2):
    """Flat bevelled plate: a 2D outline in local XZ (x, z), `depth` thick along local Y.
    Blades, fins, tines, crests - crisp toy-moulded edges."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for x, z in poly]
    f = bm.faces.new(vs)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, depth, 0), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    segs = segs if (DETAIL[0] > 0.6 and bevel >= 0.008) else 1
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=min(bevel, depth * 0.45), segments=segs, profile=0.5,
                    affect="EDGES", clamp_overlap=True)
    # big outline ngons triangulate cleanly (beauty) instead of as fans
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY",
                          ngon_method="BEAUTY")
    bm.to_mesh(me)
    bm.free()
    _crease(me, 35)
    o = toykit._obj(name, me, m, loc)
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot if isinstance(rot, Quaternion) else Euler(rot).to_quaternion()
    return o


def shell(name, center, radii, m, cuts=(), thick=0.014, bumps=(), seg=28, ring=14, hero=False, bevel=True,
          inward=True):
    """Armour plate: an ellipsoid (with optional soft bumps) trimmed by planes [(point, normal), ...]
    - the side each normal points to is cut away - then given real thickness and a softened rim."""
    seg, ring = _d(seg, FLOOR.get(seg, 12), hero), _d(ring, 7, hero, even=False)
    c = V(center)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    bs = [(V(b[0]).normalized(), b[1], b[2]) for b in bumps]
    for v in bm.verts:
        d = v.co.normalized()
        off = sum(h * math.exp(-(d.angle(bd, 0.0) / w) ** 2) for bd, h, w in bs)
        v.co = V((d.x * radii[0], d.y * radii[1], d.z * radii[2])) + d * off
    rim = _cut_rim(bm, cuts, c, thick, inward)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = toykit._obj(name, me, m, c)
    if bevel and rim:
        bv = o.modifiers.new("Bevel", "BEVEL")
        bv.width = thick * 0.35
        bv.segments = 2 if DETAIL[0] > 0.8 else 1
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(50)
    return o


_BVH = {}


def hit(o, direction, lift=0.0, origin=None):
    """Point + normal where a ray from the part's centre (or `origin`) along `direction` meets its
    actual surface (bumps and all) - for features that must sit exactly on a sculpted blob."""
    from mathutils.bvhtree import BVHTree
    key = (o.name, len(o.data.vertices))
    if key not in _BVH:
        _BVH[key] = BVHTree.FromPolygons([v.co.copy() for v in o.data.vertices], [p.vertices[:] for p in o.data.polygons])
    mw = o.matrix_basis
    inv = mw.inverted()
    org = inv @ V(origin) if origin is not None else V((0, 0, 0))
    d = (inv.to_3x3() @ V(direction)).normalized()
    loc, nrm, _, _ = _BVH[key].ray_cast(org, d)
    if loc is None:
        loc, nrm = org, d
    n = (mw.to_3x3().inverted().transposed() @ nrm).normalized()
    if n.dot(mw.to_3x3() @ d) < 0:
        n = -n
    return mw @ loc + n * lift, n


def arc_hit(o, dirs, lift=0.0):
    return [hit(o, d, lift)[0] for d in dirs]


def fist(name, at, size, m, aim_dir=(0, 0, -1), knuckle_dir=(0, -1, 0), seg=None, grip=False):
    """Chunky toy fist: a rounded palm, a row of four curled fingers along the front and a thumb
    folded across them. aim_dir points from wrist to knuckles, knuckle_dir is where the fingers face.
    grip=True leaves a hole through the fist (along the side axis) for a weapon shaft."""
    s = size
    ad, kd = V(aim_dir).normalized(), V(knuckle_dir).normalized()
    kd = (kd - ad * kd.dot(ad)).normalized()
    side = ad.cross(kd).normalized()
    c = V(at)
    rot = Matrix((side, kd, ad)).transposed().to_quaternion()
    sph(name, c, (s * 0.95, s * 0.78, s * 0.85), m, rot=rot, seg=seg or 16, ring=(seg or 16) // 2)
    for k, t in enumerate((-0.6, -0.2, 0.2, 0.6)):
        fc = c + side * t * s * 0.95 + kd * s * 0.5 + ad * s * 0.42
        sph(f"{name}_Finger{k}", fc, (s * 0.26, s * 0.36, s * 0.38), m, rot=rot, seg=10, ring=6)
    tc = c + kd * s * 0.62 - side * s * 0.3 + ad * s * 0.05
    sph(f"{name}_Thumb", tc, (s * 0.24, s * 0.22, s * 0.5), m, rot=rot @ Quaternion((0, 1, 0), -1.1), seg=10, ring=6)


def grow(limb_name, f, about):
    """Scale every part of one limb about a point (e.g. a bigger toy head)."""
    about = V(about)
    M = Matrix.Translation(about) @ Matrix.Scale(f, 4) @ Matrix.Translation(-about)
    for o in [o for o in bpy.data.objects if o.get("limb") == limb_name]:
        o.matrix_basis = M @ o.matrix_basis


def angry_eye(name, center, radii, direction, w, h, black, white, lid_m, tilt=0.35, depth=0.02):
    """Toy eye with a skin-coloured lid sliced across the top: an instant scowl."""
    eye(name, center, radii, direction, w, h, black, white, depth=depth)
    p, n = surf(center, radii, direction)
    s = 1 if direction[0] >= 0 else -1
    q = facing(n) @ Quaternion((0, 1, 0), -s * tilt)
    hsph(name + "_Lid", p + n * 0.002 + (facing(n) @ V((0, 0, 1))) * h * 0.25, (w * 1.35, depth * 1.6, h * 0.9),
         lid_m, keep_above=0.0, rot=q, seg=14, ring=8)


def eye_at(name, p, n, w, h, black, white, depth=0.02, lid=None, tilt=0.35, iris=None, shine2=True):
    """Glossy toy eye sitting on the surface point p (normal n). Optional coloured iris and a
    skin lid sliced across the top at `tilt` (inner end low = scowl)."""
    q = facing(n)
    side = q @ V((1, 0, 0))
    up = q @ V((0, 0, 1))
    sgn = 1 if p.x >= 0 else -1
    if iris is not None:
        sph(name + "_White", p - n * depth * 0.3, (w * 1.25, depth, h * 1.15), white, rot=q, seg=14, ring=7)
        sph(name, p + n * depth * 0.25, (w * 0.75, depth * 0.6, h * 0.8), iris, rot=q, seg=12, ring=6)
        sph(name + "_Pupil", p + n * depth * 0.55, (w * 0.4, depth * 0.4, h * 0.45), black, rot=q, seg=10, ring=5)
        w2, h2 = w * 0.75, h * 0.8
    else:
        sph(name, p - n * depth * 0.35, (w, depth, h), black, seg=12, ring=6, rot=q)
        w2, h2 = w, h
    hl = p + n * depth * 0.75 + up * h2 * 0.38 - side * w2 * 0.3 * sgn
    s_ = min(w2, h2) * 0.34
    sph(name + "_Shine", hl, (s_, s_ * 0.6, s_), white, seg=8, ring=4, rot=q)
    if shine2:
        hl2 = p + n * depth * 0.7 - up * h2 * 0.35 + side * w2 * 0.3 * sgn
        sph(name + "_Shine2", hl2, (s_ * 0.45, s_ * 0.27, s_ * 0.45), white, seg=6, ring=4, rot=q)
    if lid is not None:
        ww = w * (1.25 if iris is not None else 1.0)
        hh = h * (1.15 if iris is not None else 1.0)
        ql = q @ Quaternion((0, 1, 0), -sgn * tilt)
        hsph(name + "_Lid", p + n * 0.003 + up * hh * 0.22, (ww * 1.4, depth * 1.9, hh * 0.95), lid, keep_above=0.0,
             rot=ql, seg=14, ring=8)


# ====================================================================== 1. Thanos
def thanos():
    reset("Thanos")
    black, white = common_mats()
    skin = mat("Skin", "9c6cc6", rough=0.42, coat=0.35, sss=0.1)
    skin2 = mat("SkinDark", "7a4ea3", rough=0.45, coat=0.3)
    lip = mat("Lip", "4e2462", rough=0.4, coat=0.3)
    gold = mat("Gold", "f0b93a", rough=0.24, metal=0.85, coat=0.45)
    gold2 = mat("GoldDeep", "c98b22", rough=0.28, metal=0.85, coat=0.4)
    suit = mat("Suit", "3157b8", rough=0.38, coat=0.5)
    suit2 = mat("SuitDark", "1d2c66", rough=0.42, coat=0.4)

    # ---------------------------------------------------------------- legs
    hx, hz = 0.19, 0.76
    for s, side in sides():
        with limb("Leg" + side):
            x = s * hx
            tube(f"Thigh_{side}", [(x, 0, hz + 0.02), (x * 1.05, -0.01, 0.47)], suit, r=0.15, radii=[1.05, 0.9],
                 caps=False, br=2)
            sph(f"Knee_{side}", (x * 1.05, -0.01, 0.46), (0.135, 0.13, 0.11), suit)
            bx = x * 1.05
            lathe(f"Boot_{side}", [(0.0, 0.07), (0.135, 0.07), (0.148, 0.12), (0.14, 0.33), (0.16, 0.37),
                                   (0.155, 0.41), (0.0, 0.41)], gold, loc=(bx, 0.0, 0), seg=22)
            sph(f"Boot_{side}_Toe", (bx, -0.1, 0.1), (0.14, 0.2, 0.095), gold, seg=20, ring=10)
            hsph(f"Boot_{side}_Sole", (bx, -0.07, 0.0), (0.158, 0.26, 0.075), suit2, seg=20, ring=10)
            # rounded gold knee pad with a raised rim
            sph(f"KneePad_{side}", (bx, -0.105, 0.47), (0.095, 0.05, 0.085), gold, seg=18, ring=9)
            torus(f"KneePad_{side}_Rim", (bx, -0.1, 0.47), 0.088, 0.014, gold2, rot=(math.pi / 2, 0, 0),
                  scale=(1, 0.9, 1), seg=18)

    # ---------------------------------------------------------------- body
    with limb("Body"):
        sph("Hips", (0, 0, 0.84), (0.33, 0.25, 0.2), suit, seg=24, ring=12)
        sph("Belly", (0, -0.01, 1.0), (0.33, 0.25, 0.2), suit, seg=24, ring=12)
        tc, tr = V((0, 0.0, 1.24)), (0.47, 0.31, 0.32)
        blob("Torso", tc, tr, suit, [((0, 1, 0.5), 0.03, 0.6), ((-1, 0, 0.6), 0.03, 0.5), ((1, 0, 0.6), 0.03, 0.5)],
             seg=32, ring=16)
        for k, z in enumerate((0.93, 1.03)):  # abs: two rows of moulded pads
            for s, side in sides():
                p, n = on((0, -0.01, 1.0), (0.33, 0.25, 0.2), (s * 0.32, -1, (z - 1.0) * 4), -0.012)
                sph(f"Ab{k}_{side}", p, (0.085, 0.03, 0.045), suit, rot=facing(n))
        # gold pec plates either side of a blue centre line
        pc, pr = tc + V((0, -0.006, 0.012)), (0.487, 0.328, 0.335)
        for s, side in sides():
            shell(f"Chest_{side}", pc, pr, gold,
                  cuts=[((0, 0.02, 0), (0, 1, 0)), ((s * 0.03, 0, 0), (-s, 0, 0)),
                        ((0, 0, 1.11), (s * -0.3, 0, -1)), ((s * 0.42, 0, 0), (s, 0, 0))],
                  bumps=[((s * 0.5, -1, 0.3), 0.03, 0.35)], thick=0.032, seg=32, ring=16, hero=True)
        torus("Belt", (0, 0, 0.88), 0.34, 0.05, gold2, scale=(1, 0.76, 1), seg=28)
        cyl("Buckle", (0, -0.225, 0.88), 0.075, 0.05, gold, rot=X90, seg=20)
        cyl("Buckle_Gem", (0, -0.25, 0.88), 0.042, 0.02, suit2, rot=X90, seg=16)
        lathe("Neck", [(0.0, 1.46), (0.165, 1.46), (0.155, 1.62), (0.0, 1.62)], skin, seg=20)
        torus("Collar", (0, 0.0, 1.52), 0.2, 0.055, gold2, scale=(1.05, 0.95, 1), seg=24)

    # ---------------------------------------------------------------- arms
    sh, shz = 0.5, 1.42
    for s, side in sides():
        with limb("Arm" + side):
            sx = s * sh
            sph(f"Shoulder_{side}", (sx, 0, shz), (0.16, 0.16, 0.16), suit)
            shell(f"Pauldron_{side}", (sx + s * 0.03, 0.0, shz + 0.035), (0.2, 0.2, 0.17), gold,
                  cuts=[((0, 0, shz - 0.04), (0, 0, -1)), ((s * 0.3, 0, 0), (-s, 0, 0))], thick=0.03, seg=26,
                  ring=12)
            shell(f"Pauldron_{side}_Lower", (sx + s * 0.04, 0.0, shz - 0.02), (0.215, 0.215, 0.14), gold2,
                  cuts=[((0, 0, shz - 0.1), (0, 0, -1)), ((0, 0, shz - 0.01), (0, 0, 1)),
                        ((s * 0.33, 0, 0), (-s, 0, 0))], thick=0.025, seg=26, ring=10)
            el = V((s * 0.6, -0.02, 1.06))
            wr = V((s * 0.63, -0.07, 0.8))
            tube(f"UpperArm_{side}", [(sx + s * 0.03, 0, shz - 0.05), tuple(el)], suit, r=0.135, radii=[1.0, 0.92],
                 caps=False, br=2)
            sph(f"Elbow_{side}", el, (0.115, 0.115, 0.115), suit)
            d = (wr - el).normalized()
            lathe(f"Bracer_{side}", [(0.0, -0.02), (0.125, -0.02), (0.14, 0.02), (0.135, 0.19), (0.152, 0.23),
                                     (0.0, 0.23)], gold, loc=tuple(wr - d * 0.22), rot=aim(d), seg=22)
            fist(f"Hand_{side}", wr + d * 0.1 + V((0, -0.01, 0)), 0.14, skin, aim_dir=d, knuckle_dir=(0, -1, -0.1))

    # ---------------------------------------------------------------- head
    with limb("Head"):
        hc, hr = V((0, -0.02, 1.77)), (0.235, 0.225, 0.255)
        sk = blob("Head_Skull", hc, hr, skin, [((0, -0.62, -0.78), 0.1, 0.36), ((-0.72, -0.45, -0.55), 0.06, 0.32),
                                               ((0.72, -0.45, -0.55), 0.06, 0.32), ((0, -1, 0.3), 0.015, 0.5)],
                  seg=36, ring=18)
        # the famous ridged chin: long creases down the big square chin
        for k, x in enumerate((-0.27, -0.09, 0.09, 0.27)):
            pts = arc_hit(sk, [(x, -1, -0.58), (x * 1.05, -0.95, -0.8), (x * 1.1, -0.7, -1.05)], lift=-0.003)
            tube(f"Chin_Crease{k}", pts, skin2, r=0.0105, radii=[0.5, 1, 0.6], caps=True)
        for s, side in sides():
            p, n = hit(sk, (s * 0.36, -1, 0.14))
            eye_at(f"Eye_{side}", p, n, 0.03, 0.036, black, white, lid=skin, tilt=0.42)
            p, n = hit(sk, (s * 0.38, -1, 0.34), -0.006)
            sph(f"Brow_{side}", p, (0.08, 0.034, 0.026), skin2, rot=facing(n) @ Quaternion((0, 1, 0), -s * 0.3))
            tube(f"Cheek_{side}", arc_hit(sk, [(s * 0.55, -1, -0.12), (s * 0.58, -1, -0.3), (s * 0.52, -1, -0.45)],
                                          lift=-0.003), skin2, r=0.006, caps=False)
            sph(f"Ear_{side}", (s * 0.232, 0.01, 1.74), (0.035, 0.05, 0.06), skin)
        p, n = hit(sk, (0, -1, 0.02), 0.012)
        sph("Nose", p, (0.036, 0.03, 0.042), skin)
        tube("Mouth", arc_hit(sk, [(-0.26, -1, -0.33), (-0.1, -1, -0.37), (0.12, -1, -0.35), (0.28, -1, -0.25)]),
             lip, r=0.011, radii=[0.6, 1, 1, 0.6])
        # gold helmet: dome over the brow and back of the head, cheek guards, a crest and two swept fins
        hm = (0.252, 0.243, 0.272)
        hcc = hc + V((0, 0.006, 0.012))
        shell("Helmet", hcc, hm, gold, cuts=[((0, -0.13, 1.87), (0, -0.55, -0.83)), ((0, 0, 1.6), (0, 0, -1))],
              thick=0.03, seg=30, ring=15, hero=True)
        tube("Helmet_Crest", arc_on(hcc, hm, [(0, -1, 0.5), (0, -0.6, 1), (0, 0.3, 1), (0, 1, 0.5)], lift=0.012),
             gold2, r=0.032, radii=[0.55, 1, 1, 0.8], caps=True, br=2)
        for s, side in sides():
            shell(f"Helmet_Cheek_{side}", hc + V((0, 0.0, -0.01)), (0.262, 0.24, 0.262), gold,
                  cuts=[((s * 0.14, 0, 0), (-s, 0, 0)), ((0, -0.12, 0), (0, -1, 0)), ((0, 0, 1.84), (0, 0, 1)),
                        ((0, 0, 1.6), (0, 0, -1))], thick=0.028, seg=24, ring=12)
            fin = ribbon2d([(0.0, 0.0), (0.04, 0.11), (0.13, 0.21), (0.27, 0.26)], [0.09, 0.08, 0.055, 0.014])
            rot = Quaternion((0, 1, 0), s * 0.5) @ Quaternion((0, 0, 1), math.pi / 2)
            slab(f"Helmet_Fin_{side}", fin, 0.05, gold, loc=(s * 0.235, -0.07, 1.8), rot=rot, bevel=0.016)
            sph(f"Helmet_Stud_{side}", (s * 0.262, -0.03, 1.77), (0.04, 0.04, 0.04), gold2)

    grow("Head", 1.12, (0, 0, 1.55))
    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 1.55),
              "ArmL": (-sh, 0, shz), "ArmR": (sh, 0, shz),
              "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return dict(backdrop="e6dcef", pivots=pivots, target=(0, 0, 1.05), face=(0, -0.05, 1.76), dist=4.3,
                kind="boss", budget=10000, scale=0.95)


# ====================================================================== 2. Ebony Maw
def _prof_r(prof, z):
    """Radius of a (r, z) lathe profile at height z (linear between points)."""
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[-1][0]


def ebony_maw():
    reset("EbonyMaw")
    black, white = common_mats()
    skin = mat("Skin", "b3b0c2", rough=0.4, coat=0.35, sss=0.08)
    skin2 = mat("SkinShadow", "8f8ba3", rough=0.45, coat=0.2)
    lip = mat("Lip", "5d5470", rough=0.4, coat=0.3)
    robe = mat("Robe", "34313f", rough=0.42, coat=0.35)
    robe2 = mat("RobeInner", "1d1b25", rough=0.55, coat=0.15)
    trim = mat("Trim", "d7d2e4", rough=0.25, metal=0.6, coat=0.5)
    pants = mat("Pants", "26242e", rough=0.5, coat=0.2)
    shoe = mat("Shoe", "5f5a70", rough=0.3, coat=0.5)
    gem = mat("Gem", "9f7bff", rough=0.1, coat=1.0, emit="8a5cff", emit_strength=1.5)
    tunic = mat("Tunic", "77728c", rough=0.45, coat=0.3)

    hx, hz = 0.065, 0.42
    for s, side in sides():
        with limb("Leg" + side):
            x = s * hx
            tube(f"Leg_{side}", [(x, 0, hz), (x * 1.1, -0.01, 0.08)], pants, r=0.034, caps=False)
            sph(f"Shoe_{side}", (x * 1.1, -0.08, 0.035), (0.045, 0.1, 0.036), shoe, seg=14, ring=7)
            cone(f"Shoe_{side}_Tip", (x * 1.1, -0.15, 0.03), (s * 0.1, -1, 0.45), 0.03, 0.09, shoe, seg=10)

    with limb("Body"):
        # long robe: a bell skirt in two halves with a slit up the front, lined dark inside
        skirt = [(0.255, 0.035), (0.235, 0.12), (0.2, 0.3), (0.162, 0.46), (0.142, 0.56), (0.0, 0.56)]
        hem = [(0.245, 0.0), (0.262, 0.0), (0.27, 0.02), (0.262, 0.042), (0.245, 0.042)]
        for s, side in sides():
            cuts = [((0, 0, 0), (-s, 0, 0)), ((0, -0.14, 0), (-s, -1, -0.12))]
            lathe(f"Robe_Skirt_{side}", skirt, robe, seg=32, cuts=cuts, thick=0.014, sx=1.08, caps=False)
            lathe(f"Robe_Hem_{side}", hem + [hem[0]], trim, seg=32, cuts=cuts, thick=0.0, sx=1.08, caps=False)
            pts = []
            for z in (0.035, 0.15, 0.27, 0.39, 0.5):
                r = _prof_r(skirt, z)
                lo, hi = 0.0, math.pi / 2  # angle from the front, find where the cut plane crosses
                for _ in range(30):
                    t = (lo + hi) / 2
                    x, y = s * r * 1.08 * math.sin(t), -r * math.cos(t)
                    f = (-s) * x + 0.08 - 0.12 * z - y - 0.22
                    if f > 0:
                        lo = t
                    else:
                        hi = t
                pts.append((s * r * 1.08 * math.sin(t), -r * math.cos(t) - 0.004, z))
            tube(f"Robe_Edge_{side}", pts, trim, r=0.013, caps=False)
        lathe("Robe_Lining", [(0.24, 0.04), (0.22, 0.12), (0.185, 0.3), (0.15, 0.46), (0.0, 0.5)], robe2, seg=24,
              cuts=[((0, 0.02, 0), (0, -1, 0))], thick=0.0, sx=1.06)
        upper = [(0.0, 0.5), (0.142, 0.5), (0.14, 0.6), (0.152, 0.72), (0.162, 0.83), (0.145, 0.91), (0.085, 0.965),
                 (0.0, 0.975)]
        lathe("Robe_Top", upper, robe, seg=28, sx=1.15, sy=0.85)
        torus("Sash", (0, 0, 0.57), 0.146, 0.022, trim, scale=(1.13, 0.86, 1), seg=24)
        sph("Sash_Gem", (0, -0.13, 0.57), (0.03, 0.02, 0.04), gem)
        # V lapels
        for s, side in sides():
            tube(f"Lapel_{side}", [(s * 0.06, -0.1, 0.94), (s * 0.05, -0.13, 0.8), (s * 0.015, -0.135, 0.62)], trim,
                 r=0.013, caps=True)
        decal("Robe_V", (0, 0, 0.8), (0.17, 0.132, 0.16), (0, -1, 0.05), (0.045, 0.012, 0.13), tunic, sink=0.45)
        # tall stiff collar fanning up behind the head, edged in silver
        cc, cr = V((0, 0.035, 0.97)), (0.17, 0.12, 0.22)
        shell("Collar", cc, cr, robe, cuts=[((0, 0.005, 0), (0, -1, 0)), ((0, 0, 0.9), (0, 0, -1))], thick=0.016,
              seg=28, ring=14)
        pts = []
        for k in range(9):
            t = math.radians(-10 + 200 * k / 8)
            pts.append((cr[0] * 1.02 * math.cos(t), 0.005, cc.z + cr[2] * 1.0 * math.sin(t) * (1 if math.sin(t) > 0 else 0.3)))
        pts = [p for p in pts if p[2] > 0.905]
        tube("Collar_Edge", pts, trim, r=0.011, caps=True)
        cyl("Neck", (0, 0, 0.99), 0.046, 0.1, skin, seg=12)

    sh, shz = 0.17, 0.87
    for s, side in sides():
        with limb("Arm" + side):
            a = V((s * 0.17, 0, 0.885))
            w = V((s * 0.235, -0.03, 0.56))
            d = (w - a).normalized()
            L = (w - a).length
            sph(f"Shoulder_{side}", a, (0.06, 0.06, 0.06), robe)
            lathe(f"Sleeve_{side}", [(0.0, -0.01), (0.055, -0.01), (0.06, 0.1), (0.075, L * 0.7), (0.098, L),
                                     (0.08, L - 0.01), (0.0, L - 0.03)], robe, loc=tuple(a), rot=aim(d), seg=18)
            torus(f"Sleeve_{side}_Cuff", a + d * L, 0.096, 0.012, trim, rot=aim(d), seg=18)
            # long thin fingers, gently curled
            hc = a + d * (L + 0.02)
            sph(f"Hand_{side}", hc, (0.032, 0.026, 0.04), skin, rot=aim(d))
            for k, t in enumerate((-1, 0, 1)):
                b = hc + V((s * 0.012 * t, -0.012, -0.02))
                tube(f"Hand_{side}_Finger{k}", [b, b + V((s * 0.01 * t, -0.012, -0.045)),
                                                b + V((s * 0.012 * t, -0.04, -0.08))], skin, r=0.011,
                     radii=[1, 0.9, 0.7], caps=True)
            b = hc + V((-s * 0.02, -0.02, -0.005))
            tube(f"Hand_{side}_Thumb", [b, b + V((-s * 0.012, -0.03, -0.03))], skin, r=0.009, caps=True)

    with limb("Head"):
        hc, hr = V((0, -0.005, 1.155)), (0.118, 0.125, 0.165)
        sk = blob("Head_Skull", hc, hr, skin, [((0, 0.65, 0.75), 0.045, 0.5), ((0, -0.45, -1), 0.03, 0.32),
                                               ((-1, 0, 0.5), 0.01, 0.5), ((1, 0, 0.5), 0.01, 0.5)], seg=30, ring=16)
        for s, side in sides():
            p, n = hit(sk, (s * 0.42, -1, -0.1))
            decal(f"Socket_{side}", hc, hr, (s * 0.42, -1, -0.16), (0.04, 0.008, 0.032), skin2, sink=0.25)
            eye_at(f"Eye_{side}", p, n, 0.021, 0.028, black, white, lid=skin, tilt=0.15, shine2=False)
            p, n = hit(sk, (s * 0.12, -1, -0.38), -0.002)
            sph(f"Nostril_{side}", p, (0.006, 0.004, 0.01), skin2, rot=facing(n))
        # smug little smile, higher on one side
        tube("Mouth", arc_hit(sk, [(-0.22, -1, -0.56), (-0.05, -1, -0.6), (0.12, -1, -0.57), (0.25, -1, -0.47)]),
             lip, r=0.0065, radii=[0.6, 1, 1, 0.7])
        # big-brain forehead lines
        for k, z in enumerate((0.5, 0.62)):
            tube(f"Brow_Line{k}", arc_hit(sk, [(-0.32, -1, z), (0, -1, z + 0.05), (0.32, -1, z)], lift=-0.001), skin2,
                 r=0.004, caps=False)

    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 0.96),
              "ArmL": (-sh, 0, shz), "ArmR": (sh, 0, shz),
              "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return dict(backdrop="e1e0ea", pivots=pivots, target=(0, 0, 0.66), face=(0, -0.05, 1.12), dist=2.9,
                kind="aggressive person", budget=6000)


# ====================================================================== 3. Proxima Midnight
def proxima_midnight():
    reset("ProximaMidnight")
    black, white = common_mats()
    skin = mat("Skin", "a2afcc", rough=0.4, coat=0.35, sss=0.08)
    skin2 = mat("SkinShadow", "7d8aab", rough=0.45, coat=0.2)
    lip = mat("Lip", "1f1a2c", rough=0.3, coat=0.5)
    hair = mat("Hair", "1b1c2c", rough=0.35, coat=0.5)
    iris = mat("Iris", "ffc93a", rough=0.15, coat=1.0, emit="ffb000", emit_strength=0.4)
    arm = mat("Armour", "1c2136", rough=0.35, coat=0.55)
    plate = mat("Plate", "34467e", rough=0.3, coat=0.6, metal=0.3)
    silver = mat("Silver", "c3cce0", rough=0.22, metal=0.8, coat=0.4)
    glow = mat("Glow", "7fe8ff", rough=0.15, coat=0.6, emit="2fd0ff", emit_strength=3.0)
    shaft = mat("Shaft", "2b3045", rough=0.3, metal=0.5, coat=0.5)

    hx, hz = 0.078, 0.38
    for s, side in sides():
        with limb("Leg" + side):
            x = s * hx
            tube(f"Thigh_{side}", [(x, 0, hz + 0.01), (x * 1.04, -0.005, 0.2)], arm, r=0.052, radii=[1.05, 0.88],
                 caps=False)
            lathe(f"Greave_{side}", [(0.0, 0.06), (0.05, 0.06), (0.056, 0.12), (0.05, 0.2), (0.0, 0.215)], plate,
                  loc=(x * 1.05, -0.005, 0), seg=16)
            knee = [(-0.045, 0.0), (0.045, 0.0), (0.035, 0.06), (0.0, 0.1), (-0.035, 0.06)]
            slab(f"Knee_{side}", knee, 0.018, silver, loc=(x * 1.05, -0.055, 0.17), rot=Quaternion((1, 0, 0), 0.15),
                 bevel=0.007)
            sph(f"Boot_{side}", (x * 1.05, -0.03, 0.042), (0.052, 0.085, 0.042), arm, seg=14, ring=7)
            cone(f"Boot_{side}_Toe", (x * 1.05, -0.09, 0.035), (0, -1, 0.25), 0.036, 0.08, arm, seg=10)
            hsph(f"Boot_{side}_Sole", (x * 1.05, -0.04, 0.0), (0.056, 0.11, 0.02), plate, seg=14, ring=7)

    with limb("Body"):
        sph("Hips", (0, 0, 0.4), (0.128, 0.098, 0.085), arm, seg=20, ring=10)
        sph("Waist", (0, 0, 0.5), (0.1, 0.08, 0.09), arm, seg=18, ring=9)
        tc, tr = V((0, 0, 0.62)), (0.15, 0.108, 0.125)
        blob("Torso", tc, tr, arm, [((0, 1, 0.3), 0.01, 0.6)], seg=24, ring=12)
        shell("Chest", tc + V((0, -0.004, 0.005)), (0.157, 0.116, 0.132), plate,
              cuts=[((0, 0.01, 0), (0, 1, 0)), ((0, 0, 0.56), (0.55, 0, -1)), ((0, 0, 0.56), (-0.55, 0, -1)),
                    ((0.135, 0, 0), (1, 0, 0)), ((-0.135, 0, 0), (-1, 0, 0))],
              thick=0.012, seg=28, ring=14, hero=True)
        tube("Chest_Ridge", arc_on(tc, (0.165, 0.122, 0.135), [(0, -1, 0.75), (0, -1, 0.3), (0, -1, -0.35)],
                                   lift=0.0), silver, r=0.008, caps=True)
        sph("Chest_Gem", on(tc, (0.165, 0.122, 0.135), (0, -1, 0.15), 0.0)[0], (0.022, 0.012, 0.026), glow)
        torus("Belt", (0, 0, 0.45), 0.112, 0.016, silver, scale=(1, 0.85, 1), seg=22)
        box("Belt_Buckle", (0, -0.098, 0.45), (0.05, 0.02, 0.035), glow, bevel=0.008)
        # armoured skirt plates at the hips
        for s, side in sides():
            tas = [(-0.05, 0.0), (0.05, 0.0), (0.045, -0.12), (0.0, -0.16), (-0.045, -0.12)]
            q = Quaternion((0, 0, 1), s * 0.55) @ Quaternion((1, 0, 0), -0.18)
            slab(f"Tasset_{side}", tas, 0.016, plate, loc=(s * 0.085, -0.075, 0.45), rot=q, bevel=0.006)
        torus("Collar", (0, 0, 0.745), 0.06, 0.02, plate, seg=16)
        cyl("Neck", (0, 0, 0.76), 0.045, 0.06, skin, seg=12)
        # long coat-tail cape at the back
        cape = [(-0.12, 0.0), (0.12, 0.0), (0.14, -0.38), (0.0, -0.44), (-0.14, -0.38)]
        slab("Cape", cape, 0.014, arm, loc=(0, 0.1, 0.72), rot=Quaternion((1, 0, 0), -0.12), bevel=0.006)

    sh, shz = 0.168, 0.7
    for s, side in sides():
        with limb("Arm" + side):
            a = V((s * sh, 0, shz))
            sph(f"Shoulder_{side}", a, (0.048, 0.048, 0.048), arm)
            shell(f"Pauldron_{side}", a + V((s * 0.012, 0, 0.012)), (0.072, 0.072, 0.06), plate,
                  cuts=[((0, 0, shz - 0.025), (0, 0, -1))], thick=0.01, seg=20, ring=10)
            for k, (dy, ln) in enumerate(((-0.025, 0.07), (0.025, 0.055))):
                cone(f"Pauldron_{side}_Spike{k}", a + V((s * 0.035, dy, 0.05)), (s * 0.6, dy * 4, 1), 0.016, ln,
                     silver, seg=8)
            el = V((s * 0.2, 0.0, 0.55))
            wr = V((s * 0.225, -0.03, 0.445)) if s < 0 else V((s * 0.215, -0.1, 0.48))
            tube(f"UpperArm_{side}", [a + V((s * 0.01, 0, -0.03)), el], arm, r=0.034, caps=False)
            sph(f"Elbow_{side}", el, (0.034, 0.034, 0.034), arm)
            d = (wr - el).normalized()
            lathe(f"Bracer_{side}", [(0.0, -0.01), (0.034, -0.01), (0.042, 0.06), (0.046, 0.1), (0.0, 0.1)], plate,
                  loc=tuple(el + d * 0.01), rot=aim(d), seg=14)
            fist(f"Hand_{side}", wr + d * 0.03, 0.046, arm, aim_dir=d, knuckle_dir=(0, -1, 0) if s < 0 else (1, -0.3, 0))
            if s > 0:
                # the trident, held near the bottom of its shaft
                g = wr + d * 0.03
                up = V((0, -0.14, 1)).normalized()
                b0 = g - up * 0.012
                top = g + up * 0.98
                cyl_between("Trident_Shaft", b0, top, 0.015, shaft, seg=10)
                for k, t in enumerate((0.12, 0.45, 0.8)):
                    c = g + up * t
                    cyl_between(f"Trident_Band{k}", c - up * 0.015, c + up * 0.015, 0.021, silver, seg=10)
                sph("Trident_Pommel", b0, (0.019, 0.019, 0.019), silver)
                # head: collar, crossbar and three glowing tines, flat face towards the front
                rot = V((0, 0, 1)).rotation_difference(up)
                base = top
                lathe("Trident_Collar", [(0.0, 0.0), (0.024, 0.0), (0.032, 0.03), (0.022, 0.05), (0.0, 0.05)],
                      silver, loc=tuple(base - up * 0.01), rot=rot, seg=12)
                cross = ribbon2d([(-0.12, 0.09), (-0.07, 0.04), (0.0, 0.03), (0.07, 0.04), (0.12, 0.09)],
                                 [0.012, 0.018, 0.022, 0.018, 0.012], tip=False)
                slab("Trident_Cross", cross, 0.02, silver, loc=tuple(base), rot=rot, bevel=0.006)
                mid = ribbon2d([(0.0, 0.04), (0.0, 0.14), (0.0, 0.26)], [0.02, 0.016, 0.0])
                slab("Trident_Tine_Mid", mid, 0.016, glow, loc=tuple(base), rot=rot, bevel=0.005)
                for k in (-1, 1):
                    tine = ribbon2d([(k * 0.11, 0.08), (k * 0.12, 0.14), (k * 0.1, 0.22)], [0.016, 0.013, 0.0])
                    slab(f"Trident_Tine{k}", tine, 0.016, glow, loc=tuple(base), rot=rot, bevel=0.005)

    with limb("Head"):
        hc, hr = V((0, -0.005, 0.9)), (0.142, 0.133, 0.152)
        sk = blob("Head_Skull", hc, hr, skin, [((0, -0.5, -1), 0.03, 0.3), ((-0.8, -0.3, -0.5), -0.012, 0.4),
                                               ((0.8, -0.3, -0.5), -0.012, 0.4)], seg=30, ring=15)
        for s, side in sides():
            p, n = hit(sk, (s * 0.37, -1, -0.02))
            eye_at(f"Eye_{side}", p, n, 0.026, 0.03, black, white, lid=skin, tilt=0.4, iris=iris)
            tube(f"Liner_{side}", arc_hit(sk, [(s * 0.55, -1, 0.02), (s * 0.66, -1, 0.06), (s * 0.74, -1, 0.13)],
                                          lift=0.001), lip, r=0.005, radii=[1, 0.8, 0.3], caps=False)
            tube(f"Brow_{side}", arc_hit(sk, [(s * 0.15, -1, 0.24), (s * 0.38, -1, 0.33), (s * 0.6, -1, 0.3)],
                                         lift=0.003), hair, r=0.007, radii=[1, 1, 0.5], caps=False)
            sph(f"Ear_{side}", (s * 0.14, 0.01, 0.89), (0.022, 0.02, 0.035), skin)
        p, n = hit(sk, (0, -1, -0.15), 0.008)
        sph("Nose", p, (0.018, 0.016, 0.024), skin)
        # dark lips in a cold little smirk
        tube("Mouth", arc_hit(sk, [(-0.18, -1, -0.43), (-0.05, -1, -0.45), (0.08, -1, -0.44), (0.18, -1, -0.39)]),
             lip, r=0.009, radii=[0.5, 1, 1, 0.5])
        # slicked hair cap and the two famous hair horns
        shell("Hair", hc + V((0, 0.006, 0.006)), (0.152, 0.143, 0.161), hair,
              cuts=[((0, -0.075, 0.97), (0, -0.72, -0.69)), ((0, 0, 0.8), (0, 0, -1))], thick=0.012, seg=30, ring=15)
        p, n = hit(sk, (0, -1, 0.62), 0.0)
        cone("Hair_Peak", p + V((0, 0.012, 0.03)), (0, -0.25, -1), 0.035, 0.06, hair, flatten=0.4, seg=8)
        for s, side in sides():
            pts = [(s * 0.05, -0.01, 0.99), (s * 0.08, 0.0, 1.09), (s * 0.11, 0.045, 1.17), (s * 0.12, 0.11, 1.22)]
            tube(f"Horn_{side}", pts, hair, r=0.052, radii=[1, 0.75, 0.45, 0.12], res=3, br=2)
        tube("Hair_Tail", [(0, 0.12, 0.92), (0, 0.17, 0.8), (0, 0.16, 0.68)], hair, r=0.035, radii=[1, 0.8, 0.4],
             br=2)

    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 0.76),
              "ArmL": (-sh, 0, shz), "ArmR": (sh, 0, shz),
              "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return dict(backdrop="dfe3f0", pivots=pivots, target=(0, 0, 0.82), face=(0, -0.05, 0.92), dist=3.5,
                kind="aggressive person", budget=7500)


# ====================================================================== 4. Corvus Glaive
def corvus_glaive():
    reset("CorvusGlaive")
    black, white = common_mats()
    skin = mat("Skin", "93a28c", rough=0.4, coat=0.35, sss=0.08)
    skin2 = mat("SkinShadow", "6d7c68", rough=0.45, coat=0.2)
    lip = mat("Lip", "2e2a2e", rough=0.4, coat=0.3)
    hair = mat("Hair", "17161d", rough=0.3, coat=0.6)
    iris = mat("Iris", "e9e25a", rough=0.15, coat=1.0, emit="d8d020", emit_strength=0.4)
    arm = mat("Armour", "262330", rough=0.32, coat=0.6)
    coat = mat("Coat", "35303e", rough=0.45, coat=0.3)
    bronze = mat("Bronze", "c08a4a", rough=0.26, metal=0.85, coat=0.4)
    blade = mat("Blade", "e4e9f2", rough=0.1, metal=1.0, coat=0.3)
    edge = mat("BladeGlow", "a8f0ff", rough=0.1, coat=0.5, emit="5fd6ff", emit_strength=2.0)
    shaft = mat("Shaft", "1e1c24", rough=0.3, metal=0.5, coat=0.5)

    hx, hz = 0.07, 0.42
    for s, side in sides():
        with limb("Leg" + side):
            x = s * hx
            tube(f"Thigh_{side}", [(x, 0, hz + 0.01), (x * 1.05, -0.005, 0.2)], arm, r=0.042, radii=[1.05, 0.85],
                 caps=False)
            lathe(f"Boot_{side}", [(0.0, 0.06), (0.044, 0.06), (0.05, 0.15), (0.046, 0.23), (0.054, 0.26),
                                   (0.0, 0.26)], arm, loc=(x * 1.05, -0.005, 0), seg=16)
            sph(f"Knee_{side}", (x * 1.05, -0.04, 0.245), (0.034, 0.025, 0.04), bronze)
            sph(f"Foot_{side}", (x * 1.05, -0.035, 0.04), (0.046, 0.09, 0.04), arm, seg=14, ring=7)
            cone(f"Foot_{side}_Toe", (x * 1.05, -0.095, 0.03), (0, -1, 0.3), 0.032, 0.07, arm, seg=10)
            hsph(f"Foot_{side}_Sole", (x * 1.05, -0.045, 0.0), (0.05, 0.11, 0.018), bronze, seg=14, ring=7)

    with limb("Body"):
        sph("Hips", (0, 0, 0.44), (0.11, 0.085, 0.08), arm, seg=18, ring=9)
        sph("Waist", (0, 0, 0.54), (0.09, 0.07, 0.09), arm, seg=18, ring=9)
        tc, tr = V((0, 0, 0.66)), (0.135, 0.095, 0.13)
        blob("Torso", tc, tr, arm, [((-1, 0, 0.7), 0.015, 0.5), ((1, 0, 0.7), 0.015, 0.5)], seg=24, ring=12)
        # ribbed chest plate with bronze trims
        for k, z in enumerate((0.7, 0.63, 0.56)):
            f = math.sqrt(max(0.0, 1 - ((z - tc.z) / 0.15) ** 2))
            torus(f"Rib{k}", (0, -0.006, z), 0.128 * f + 0.004, 0.009, bronze, scale=(1, 0.74, 1), seg=20)
        tube("Chest_Strap", [(-0.11, -0.07, 0.76), (-0.02, -0.1, 0.66), (0.08, -0.08, 0.52)], bronze, r=0.012)
        # long open coat, split wide at the front, falling behind the legs
        skirt = [(0.155, 0.17), (0.145, 0.3), (0.12, 0.45), (0.1, 0.55), (0.0, 0.55)]
        for s, side in sides():
            cuts = [((0, 0, 0), (-s, 0, 0)), ((0, -0.06, 0), (-s, -1.4, -0.25))]
            lathe(f"Coat_{side}", skirt, coat, seg=28, cuts=cuts, thick=0.012, sx=1.2, caps=False)
        torus("Belt", (0, 0, 0.5), 0.094, 0.016, bronze, scale=(1.05, 0.85, 1), seg=20)
        box("Belt_Buckle", (0, -0.08, 0.5), (0.04, 0.02, 0.035), bronze, bevel=0.008)
        cyl("Neck", (0, 0, 0.79), 0.036, 0.08, skin, seg=12)
        # high, pointed collar flaring up behind the head
        for s, side in sides():
            col = ribbon2d([(0.0, 0.0), (0.03, 0.1), (0.06, 0.2)], [0.045, 0.035, 0.0])
            q = Quaternion((0, 0, 1), s * 0.55) @ Quaternion((1, 0, 0), 0.25)
            slab(f"Collar_{side}", [(s * x, z) for x, z in col], 0.016, arm, loc=(s * 0.04, 0.045, 0.75), rot=q,
                 bevel=0.006)
        torus("Collar_Ring", (0, 0, 0.765), 0.055, 0.014, bronze, seg=16)

    sh, shz = 0.15, 0.735
    for s, side in sides():
        with limb("Arm" + side):
            a = V((s * sh, 0, shz))
            sph(f"Shoulder_{side}", a, (0.042, 0.042, 0.042), arm)
            shell(f"Pauldron_{side}", a + V((s * 0.01, 0, 0.01)), (0.062, 0.062, 0.05), arm,
                  cuts=[((0, 0, shz - 0.02), (0, 0, -1))], thick=0.01, seg=18, ring=9)
            sp = ribbon2d([(0.0, 0.0), (0.012, 0.05), (0.04, 0.1)], [0.022, 0.016, 0.0])
            slab(f"Pauldron_{side}_Spike", [(s * x, z) for x, z in sp], 0.012, bronze, loc=tuple(a + V((s * 0.03, 0, 0.04))),
                 bevel=0.004)
            el = V((s * 0.18, 0.0, 0.575))
            wr = V((s * 0.205, -0.03, 0.465)) if s < 0 else V((s * 0.195, -0.1, 0.5))
            tube(f"UpperArm_{side}", [a + V((s * 0.008, 0, -0.03)), el], arm, r=0.03, caps=False)
            sph(f"Elbow_{side}", el, (0.03, 0.03, 0.03), arm)
            d = (wr - el).normalized()
            lathe(f"Bracer_{side}", [(0.0, -0.01), (0.03, -0.01), (0.036, 0.06), (0.04, 0.1), (0.0, 0.1)], bronze,
                  loc=tuple(el + d * 0.01), rot=aim(d), seg=12)
            fist(f"Hand_{side}", wr + d * 0.03, 0.04, skin, aim_dir=d,
                 knuckle_dir=(0, -1, 0) if s < 0 else (1, -0.3, 0))
            if s > 0:
                # the glaive: a long staff with a big curved blade on top
                g = wr + d * 0.03
                up = V((0, -0.12, 1)).normalized()
                b0 = g - up * 0.012
                top = g + up * 1.0
                cyl_between("Glaive_Shaft", b0, top, 0.013, shaft, seg=10)
                sph("Glaive_Pommel", b0, (0.017, 0.017, 0.017), bronze)
                for k, t in enumerate((0.15, 0.55)):
                    c = g + up * t
                    cyl_between(f"Glaive_Wrap{k}", c - up * 0.03, c + up * 0.03, 0.018, bronze, seg=10)
                rot = V((0, 0, 1)).rotation_difference(up)
                lathe("Glaive_Guard", [(0.0, -0.01), (0.026, -0.01), (0.036, 0.02), (0.024, 0.045), (0.0, 0.045)],
                      bronze, loc=tuple(top - up * 0.02), rot=V((0, 0, 1)).rotation_difference(up), seg=12)
                bl = ribbon2d([(0.0, 0.0), (-0.03, 0.12), (-0.01, 0.26), (0.06, 0.38), (0.15, 0.45)],
                              [0.035, 0.07, 0.075, 0.055, 0.0])
                slab("Glaive_Blade", bl, 0.012, blade, loc=tuple(top), rot=rot, bevel=0.005)
                edge_pts = ribbon2d([(-0.06, 0.08), (-0.09, 0.17), (-0.07, 0.29), (0.0, 0.39), (0.13, 0.445)],
                                    [0.007, 0.008, 0.008, 0.007, 0.0])
                slab("Glaive_Edge", edge_pts, 0.016, edge, loc=tuple(top), rot=rot, bevel=0.003)
                spike = ribbon2d([(0.02, 0.0), (0.06, 0.03), (0.1, 0.035)], [0.02, 0.014, 0.0])
                slab("Glaive_Spike", spike, 0.012, blade, loc=tuple(top + up * 0.02), rot=rot, bevel=0.004)

    with limb("Head"):
        hc, hr = V((0, -0.005, 0.94)), (0.112, 0.118, 0.158)
        sk = blob("Head_Skull", hc, hr, skin, [((0, -0.45, -1), 0.035, 0.3), ((-0.85, -0.45, -0.35), -0.018, 0.3),
                                               ((0.85, -0.45, -0.35), -0.018, 0.3), ((0, -1, 0.25), 0.01, 0.4)],
                  seg=30, ring=15)
        for s, side in sides():
            p, n = hit(sk, (s * 0.38, -1, 0.06))
            eye_at(f"Eye_{side}", p, n, 0.022, 0.025, black, white, lid=skin2, tilt=0.5, iris=iris, shine2=False)
            p, n = hit(sk, (s * 0.38, -1, 0.3), -0.004)
            sph(f"Brow_{side}", p, (0.05, 0.02, 0.016), skin2, rot=facing(n) @ Quaternion((0, 1, 0), -s * 0.45))
            cone(f"Ear_{side}", (s * 0.1, 0.02, 0.94), (s * 1, 0.5, 0.45), 0.026, 0.07, skin, flatten=0.45, seg=8)
        p, n = hit(sk, (0, -1, -0.1), 0.006)
        sph("Nose", p, (0.014, 0.02, 0.03), skin, rot=facing(n))
        tube("Mouth", arc_hit(sk, [(-0.18, -1, -0.43), (-0.04, -1, -0.47), (0.1, -1, -0.45), (0.2, -1, -0.38)]),
             lip, r=0.007, radii=[0.5, 1, 1, 0.5])
        # slicked-back black hair, gathered into a long tail that falls down his back
        shell("Hair", hc + V((0, 0.004, 0.004)), (0.117, 0.123, 0.163), hair,
              cuts=[((0, -0.05, 1.03), (0, -0.85, -0.5)), ((0, 0, 0.86), (0, 0, -1))], thick=0.008, seg=28, ring=14)
        tube("Hair_Knot", [(0, 0.03, 1.09), (0, 0.1, 1.11), (0, 0.15, 1.06)], hair, r=0.035, radii=[0.9, 1, 0.9],
             caps=False, br=2)
        tube("Hair_Tail", [(0, 0.15, 1.06), (0, 0.19, 0.96), (0, 0.19, 0.82), (0, 0.16, 0.66)], hair, r=0.033,
             radii=[1, 0.95, 0.8, 0.3], res=3, br=2)
        torus("Hair_Band", (0, 0.155, 1.05), 0.03, 0.009, bronze, rot=aim((0, 0.5, -1)), seg=12)

    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 0.79),
              "ArmL": (-sh, 0, shz), "ArmR": (sh, 0, shz),
              "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return dict(backdrop="e0e6dc", pivots=pivots, target=(0, 0, 0.88), face=(0, -0.05, 0.95), dist=3.7,
                kind="aggressive person", budget=7000)


# ====================================================================== 5. Cull Obsidian
def cull_obsidian():
    reset("CullObsidian")
    black, white = common_mats()
    skin = mat("Skin", "9a8f9c", rough=0.45, coat=0.3, sss=0.06)
    skin2 = mat("SkinDark", "74697a", rough=0.5, coat=0.2)
    mouth = mat("Mouth", "3a2430", rough=0.4)
    horn = mat("Horn", "efe3c4", rough=0.3, coat=0.6)
    arm = mat("Armour", "4d5566", rough=0.3, metal=0.55, coat=0.45)
    arm2 = mat("ArmourDark", "2c313d", rough=0.35, metal=0.4, coat=0.4)
    bronze = mat("Bronze", "cf8a3e", rough=0.26, metal=0.85, coat=0.4)
    steel = mat("Steel", "b9c0cc", rough=0.2, metal=0.95, coat=0.3)
    glow = mat("Glow", "ffb347", rough=0.2, coat=0.4, emit="ff8a1a", emit_strength=2.5)

    hx, hz = 0.2, 0.55
    for s, side in sides():
        with limb("Leg" + side):
            x = s * hx
            tube(f"Thigh_{side}", [(x, 0, hz + 0.02), (x * 1.05, -0.01, 0.3)], skin2, r=0.13, radii=[1.05, 0.88],
                 caps=False, br=2)
            sph(f"Knee_{side}", (x * 1.05, -0.02, 0.3), (0.135, 0.135, 0.11), arm)
            lathe(f"Boot_{side}", [(0.0, 0.07), (0.125, 0.07), (0.135, 0.12), (0.125, 0.25), (0.135, 0.28),
                                   (0.0, 0.28)], arm2, loc=(x * 1.05, 0.0, 0), seg=20)
            sph(f"Boot_{side}_Toe", (x * 1.05, -0.08, 0.095), (0.13, 0.17, 0.09), arm2, seg=18, ring=9)
            hsph(f"Boot_{side}_Sole", (x * 1.05, -0.05, 0.0), (0.145, 0.22, 0.06), bronze, seg=18, ring=9)

    with limb("Body"):
        sph("Hips", (0, 0, 0.6), (0.3, 0.24, 0.17), arm2, seg=22, ring=11)
        sph("Belly", (0, -0.03, 0.76), (0.32, 0.26, 0.2), skin, seg=22, ring=11)
        tc, tr = V((0, 0.03, 1.0)), (0.42, 0.31, 0.33)
        blob("Torso", tc, tr, skin, [((0, 0.75, 0.65), 0.1, 0.5), ((-0.8, 0, 0.6), 0.04, 0.45),
                                     ((0.8, 0, 0.6), 0.04, 0.45)], seg=28, ring=14)
        # one big chest plate with bronze rim and rivets, a glowing core
        pc, pr = tc + V((0, -0.01, 0.0)), (0.44, 0.335, 0.35)
        shell("Chest", pc, pr, arm, cuts=[((0, 0.0, 0), (0, 1, 0)), ((0, 0, 0.82), (0, 0, -1)),
                                          ((0.36, 0, 0), (1, 0, 0)), ((-0.36, 0, 0), (-1, 0, 0))],
              bumps=[((-0.45, -1, 0.3), 0.03, 0.4), ((0.45, -1, 0.3), 0.03, 0.4)], thick=0.03, seg=32, ring=16,
              hero=True)
        for k, d in enumerate([(-0.62, -1, -0.35), (0.62, -1, -0.35), (-0.55, -1, 0.5), (0.55, -1, 0.5)]):
            p, n = on(pc, pr, d, 0.006)
            sph(f"Rivet{k}", p, (0.025, 0.012, 0.025), bronze, rot=facing(n))
        p, n = on(pc, pr, (0, -1, 0.0), 0.004)
        cyl("Core_Rim", p, 0.07, 0.03, bronze, rot=aim(n), seg=18)
        sph("Core", p + n * 0.012, (0.05, 0.05, 0.02), glow, rot=aim(n))
        torus("Belt", (0, -0.01, 0.67), 0.31, 0.04, bronze, scale=(1, 0.8, 1), seg=26)
        box("Belt_Buckle", (0, -0.21, 0.67), (0.13, 0.04, 0.1), arm, bevel=0.02)
        flap = [(-0.12, 0.0), (0.12, 0.0), (0.1, -0.2), (0.0, -0.25), (-0.1, -0.2)]
        slab("Loin_Plate", flap, 0.025, arm2, loc=(0, -0.2, 0.64), rot=Quaternion((1, 0, 0), -0.08), bevel=0.01)
        # bony bumps down the hunched back
        for k, (y, z) in enumerate(((0.3, 1.25), (0.36, 1.12), (0.37, 0.98), (0.34, 0.85))):
            cone(f"Back_Spike{k}", (0, y, z), (0, 1, 0.5), 0.05, 0.08, horn, seg=8)

    sh, shz = 0.44, 1.18
    for s, side in sides():
        with limb("Arm" + side):
            a = V((s * sh, 0.02, shz))
            sph(f"Shoulder_{side}", a, (0.15, 0.15, 0.15), skin, seg=16)
            shell(f"Pauldron_{side}", a + V((s * 0.04, 0, 0.04)), (0.2, 0.2, 0.16), arm,
                  cuts=[((0, 0, shz - 0.04), (0, 0, -1)), ((s * 0.28, 0, 0), (-s, 0, 0))], thick=0.03, seg=24,
                  ring=12)
            cone(f"Pauldron_{side}_Spike", a + V((s * 0.12, 0, 0.13)), (s * 0.5, 0, 1), 0.045, 0.1, horn, seg=8)
            el = V((s * 0.56, -0.02, 0.9))
            wr = V((s * 0.6, -0.1, 0.66)) if s < 0 else V((s * 0.58, -0.2, 0.7))
            tube(f"UpperArm_{side}", [a + V((s * 0.02, 0, -0.04)), el], skin, r=0.12, radii=[1.05, 0.88], caps=False,
                 br=1)
            sph(f"Elbow_{side}", el, (0.122, 0.122, 0.122), skin, seg=16)
            d = (wr - el).normalized()
            if s < 0:
                tube(f"Forearm_{side}", [el, wr], skin, r=0.115, radii=[0.9, 1.1], caps=False, br=2)
                lathe(f"Bracer_{side}", [(0.0, -0.01), (0.12, -0.01), (0.135, 0.12), (0.145, 0.17), (0.0, 0.17)],
                      bronze, loc=tuple(wr - d * 0.17), rot=aim(d), seg=18)
                fist(f"Hand_{side}", wr + d * 0.1, 0.15, skin, aim_dir=d, knuckle_dir=(0, -1, 0))
            else:
                # the chain-hammer arm: a heavy gauntlet, a hammer gripped in the fist, chain back to the gauntlet
                lathe(f"Gauntlet_{side}", [(0.0, -0.06), (0.12, -0.06), (0.15, 0.0), (0.16, 0.22), (0.17, 0.27),
                                           (0.0, 0.27)], arm, loc=tuple(el + d * 0.03), rot=aim(d), seg=20)
                torus(f"Gauntlet_{side}_Ring", el + d * 0.27, 0.16, 0.025, bronze, rot=aim(d), seg=20)
                fc = wr + d * 0.1
                fist(f"Hand_{side}", fc, 0.15, arm2, aim_dir=d, knuckle_dir=(1, -0.3, 0))
                hd = V((0.3, -0.85, 0.45)).normalized()
                h0 = fc - hd * 0.05
                h1 = fc + hd * 0.4
                cyl_between("Hammer_Haft", h0, h1, 0.035, arm2, seg=12)
                torus("Hammer_Grip", fc + hd * 0.17, 0.042, 0.012, bronze, rot=aim(hd), seg=12)
                ax = hd.cross(V((1, 0, 0))).normalized()  # head axis, square to the haft
                if ax.z < 0:
                    ax = -ax
                hc = h1 + hd * 0.1
                lathe("Hammer_Head", [(0.0, -0.17), (0.11, -0.17), (0.135, -0.14), (0.14, -0.06), (0.125, 0.0),
                                      (0.14, 0.06), (0.135, 0.14), (0.11, 0.17), (0.0, 0.17)], steel,
                      loc=tuple(hc), rot=aim(ax), seg=20)
                for k in (-1, 1):
                    torus(f"Hammer_Band{k}", hc + ax * 0.1 * k, 0.142, 0.018, bronze, rot=aim(ax), seg=20)
                    cyl(f"Hammer_Face{k}", hc + ax * 0.172 * k, 0.085, 0.02, arm2, rot=aim(ax), seg=16)
                # chain: links swinging from the gauntlet ring to the hammer head
                c0 = el + d * 0.2 + V((s * 0.16, 0, 0))
                c1 = hc + V((s * 0.13, 0, 0))
                n_ = 6
                for k in range(n_ + 1):
                    t = k / n_
                    p = c0.lerp(c1, t) + V((s * 0.03 * math.sin(t * math.pi), 0, -0.12 * math.sin(t * math.pi)))
                    tang = (c1 - c0).normalized()
                    q = aim(tang) @ Quaternion((0, 0, 1), (k % 2) * math.pi / 2) @ Quaternion((1, 0, 0), math.pi / 2)
                    torus(f"Chain_Link{k}", p, 0.03, 0.011, steel, rot=q, scale=(0.75, 1, 1), seg=10, mseg=5)

    with limb("Head"):
        hc, hr = V((0, -0.2, 1.36)), (0.155, 0.145, 0.14)
        sk = blob("Head_Skull", hc, hr, skin, [((0, -0.6, -0.8), 0.06, 0.4), ((-0.8, -0.4, -0.5), 0.04, 0.35),
                                               ((0.8, -0.4, -0.5), 0.04, 0.35), ((0, 0.3, 1), 0.02, 0.4)],
                  seg=28, ring=14)
        # bony crown ridge
        for k, a_ in enumerate((-20, 15, 50, 85)):
            r = math.radians(a_)
            p, n = hit(sk, (0, math.sin(r), math.cos(r)), -0.01)
            cone(f"Crown{k}", p, n, 0.03, 0.05, horn, seg=8)
        for s, side in sides():
            p, n = hit(sk, (s * 0.37, -1, 0.15))
            eye_at(f"Eye_{side}", p, n, 0.022, 0.026, black, white, lid=skin2, tilt=0.5, shine2=False)
            p, n = hit(sk, (s * 0.38, -1, 0.36), -0.005)
            sph(f"Brow_{side}", p, (0.06, 0.03, 0.025), skin2, rot=facing(n) @ Quaternion((0, 1, 0), -s * 0.35))
            # big curling bull horns
            pts = [(s * 0.12, -0.2, 1.43), (s * 0.22, -0.2, 1.47), (s * 0.28, -0.22, 1.56), (s * 0.27, -0.28, 1.64)]
            tube(f"Horn_{side}", pts, horn, r=0.048, radii=[1, 0.82, 0.55, 0.2], res=3, br=2)
            torus(f"Horn_{side}_Ring", V(pts[0]) + V((s * 0.04, 0, 0.005)), 0.046, 0.012, bronze,
                  rot=aim((s, 0, 0.3)), seg=12)
        p, n = hit(sk, (0, -1, 0.0), 0.008)
        sph("Nose", p, (0.04, 0.026, 0.026), skin2, rot=facing(n))
        # under-bite grin with two little tusks
        mp = arc_hit(sk, [(-0.4, -1, -0.32), (-0.15, -1, -0.38), (0.15, -1, -0.38), (0.4, -1, -0.32)])
        tube("Mouth", mp, mouth, r=0.011, radii=[0.6, 1, 1, 0.6])
        for s in (-1, 1):
            p, n = hit(sk, (s * 0.22, -1, -0.4), -0.004)
            cone(f"Tusk{s}", p, (s * 0.15, -0.35, 1), 0.016, 0.05, horn, seg=8)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.12, 1.24),
              "ArmL": (-sh, 0.02, shz), "ArmR": (sh, 0.02, shz),
              "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return dict(backdrop="e7e1da", pivots=pivots, target=(0, 0, 0.82), face=(0, -0.2, 1.35), dist=3.9,
                kind="aggressive person", budget=8000)


# ====================================================================== 6. Chitauri soldier
def chitauri():
    reset("Chitauri")
    black, white = common_mats()
    skin = mat("Skin", "97928c", rough=0.45, coat=0.3)
    skin2 = mat("SkinDark", "6c6863", rough=0.5, coat=0.2)
    arm = mat("Armour", "73845f", rough=0.3, metal=0.35, coat=0.5)
    arm2 = mat("ArmourDark", "3b4535", rough=0.35, metal=0.3, coat=0.45)
    brass = mat("Brass", "c2a35a", rough=0.26, metal=0.85, coat=0.4)
    glow = mat("Visor", "8ff6ff", rough=0.1, coat=0.6, emit="33e6ff", emit_strength=3.5)
    gun = mat("Gun", "4a4f58", rough=0.28, metal=0.7, coat=0.45)
    gun2 = mat("GunDark", "262a31", rough=0.35, metal=0.5, coat=0.4)

    hx, hz = 0.075, 0.34
    for s, side in sides():
        with limb("Leg" + side):
            x = s * hx
            tube(f"Thigh_{side}", [(x, 0, hz + 0.01), (x * 1.08, -0.01, 0.19)], arm2, r=0.046, radii=[1.05, 0.88],
                 caps=False)
            sph(f"Knee_{side}", (x * 1.08, -0.02, 0.19), (0.05, 0.05, 0.045), arm)
            cone(f"Knee_{side}_Spike", (x * 1.08, -0.06, 0.2), (0, -1, 0.5), 0.025, 0.045, brass, seg=8)
            lathe(f"Shin_{side}", [(0.0, 0.05), (0.04, 0.05), (0.048, 0.1), (0.042, 0.18), (0.0, 0.18)], arm,
                  loc=(x * 1.08, -0.01, 0), seg=14)
            # three-toed alien boot
            sph(f"Foot_{side}", (x * 1.08, -0.035, 0.035), (0.05, 0.075, 0.035), arm2, seg=14, ring=7)
            for k, t in enumerate((-1, 0, 1)):
                cone(f"Toe_{side}{k}", (x * 1.08 + t * 0.025, -0.07, 0.025), (t * 0.35, -1, 0.1), 0.019, 0.06, arm2,
                     seg=8)
            hsph(f"Sole_{side}", (x * 1.08, -0.045, 0.0), (0.055, 0.095, 0.016), brass, seg=14, ring=7)

    with limb("Body"):
        sph("Hips", (0, 0, 0.36), (0.115, 0.09, 0.07), arm2, seg=18, ring=9)
        sph("Waist", (0, 0.005, 0.44), (0.09, 0.075, 0.08), skin2, seg=16, ring=8)
        tc, tr = V((0, 0.01, 0.555)), (0.14, 0.108, 0.12)
        blob("Torso", tc, tr, skin2, [((0, 0.8, 0.5), 0.03, 0.5)], seg=24, ring=12)
        # segmented chest plating
        shell("Chest", tc + V((0, -0.004, 0.01)), (0.148, 0.116, 0.125), arm,
              cuts=[((0, 0.03, 0), (0, 1, 0)), ((0, 0, 0.5), (0, 0, -1))], thick=0.014, seg=26, ring=13, hero=True)
        for k, z in enumerate((0.48, 0.445)):
            shell(f"Ab{k}", (0, -0.004, z), (0.105, 0.088, 0.03), arm,
                  cuts=[((0, 0.0, 0), (0, 1, 0))], thick=0.01, seg=20, ring=6)
        tube("Chest_Seam", arc_on(tc, (0.152, 0.12, 0.13), [(0, -1, 0.7), (0, -1, 0.0), (0, -1, -0.4)], lift=0.0),
             arm2, r=0.007, caps=False)
        for s, side in sides():
            p, n = on(tc, (0.152, 0.12, 0.13), (s * 0.55, -1, 0.35), 0.0)
            sph(f"Chest_Light_{side}", p, (0.018, 0.008, 0.018), glow, rot=facing(n))
        # spine plates down the hunched back
        for k, (y, z) in enumerate(((0.11, 0.66), (0.125, 0.59), (0.125, 0.52))):
            sh_ = ribbon2d([(0.0, 0.0), (0.0, 0.035), (0.0, 0.07)], [0.035, 0.028, 0.0])
            slab(f"Spine{k}", sh_, 0.014, arm, loc=(0, y, z), rot=Quaternion((0, 0, 1), math.pi / 2) @
                 Quaternion((0, 1, 0), 0.0) if False else Quaternion((1, 0, 0), -0.9) @ Quaternion((0, 0, 1), math.pi / 2),
                 bevel=0.004)
        torus("Belt", (0, 0, 0.385), 0.1, 0.014, brass, scale=(1.05, 0.85, 1), seg=20)
        box("Belt_Pouch", (0.08, -0.06, 0.37), (0.04, 0.03, 0.045), arm2, bevel=0.01, rot=(0, 0, 0.6))
        cyl("Neck", (0, -0.01, 0.67), 0.04, 0.06, skin2, seg=12)

    sh, shz = 0.16, 0.62
    for s, side in sides():
        with limb("Arm" + side):
            a = V((s * sh, 0.01, shz))
            sph(f"Shoulder_{side}", a, (0.045, 0.045, 0.045), skin2)
            shell(f"Pauldron_{side}", a + V((s * 0.012, 0, 0.012)), (0.068, 0.068, 0.056), arm,
                  cuts=[((0, 0, shz - 0.025), (0, 0, -1))], thick=0.01, seg=18, ring=9)
            torus(f"Pauldron_{side}_Rim", a + V((s * 0.012, 0, -0.012)), 0.066, 0.008, brass, seg=16)
            el = V((s * 0.185, 0.0, 0.48))
            wr = V((s * 0.2, -0.03, 0.385)) if s < 0 else V((s * 0.18, -0.12, 0.43))
            tube(f"UpperArm_{side}", [a + V((s * 0.006, 0, -0.03)), el], skin2, r=0.03, caps=False)
            sph(f"Elbow_{side}", el, (0.034, 0.034, 0.034), arm)
            d = (wr - el).normalized()
            lathe(f"Bracer_{side}", [(0.0, -0.01), (0.031, -0.01), (0.038, 0.05), (0.04, 0.09), (0.0, 0.09)], arm,
                  loc=tuple(el + d * 0.012), rot=aim(d), seg=12)
            fist(f"Hand_{side}", wr + d * 0.028, 0.04, skin, aim_dir=d,
                 knuckle_dir=(0, -1, 0) if s < 0 else (1, 0, 0))
            if s > 0:
                # Chitauri blaster rifle, held level and pointing ahead; the hand is its lowest point
                g = wr + d * 0.028
                gz = g.z + 0.045
                gx = g.x - 0.005
                box("Rifle_Body", (gx, -0.14, gz + 0.005), (0.06, 0.34, 0.066), gun, bevel=0.018)
                box("Rifle_Top", (gx, -0.12, gz + 0.05), (0.04, 0.22, 0.034), gun2, bevel=0.012)
                cyl("Rifle_Barrel", (gx, -0.33, gz + 0.005), 0.018, 0.14, gun2, rot=X90, seg=12)
                cyl("Rifle_Muzzle", (gx, -0.405, gz + 0.005), 0.026, 0.03, brass, rot=X90, seg=14)
                sph("Rifle_Muzzle_Glow", (gx, -0.42, gz + 0.005), (0.016, 0.006, 0.016), glow)
                for k in range(3):
                    cyl(f"Rifle_Cell{k}", (gx + 0.032, -0.22 + k * 0.05, gz + 0.005), 0.019, 0.03, glow, rot=Y90, seg=10)
                box("Rifle_Stock", (gx, 0.06, gz - 0.005), (0.04, 0.12, 0.045), gun2, bevel=0.012)
                cyl("Rifle_Grip", (g.x, g.y, g.z + 0.02), 0.018, 0.05, gun2, seg=10)
                cone("Rifle_Blade", (gx, -0.32, gz - 0.025), (0, -1, -0.15), 0.022, 0.09, brass, flatten=0.35, seg=8)

    with limb("Head"):
        hc, hr = V((0, -0.025, 0.8)), (0.13, 0.13, 0.12)
        sk = blob("Head_Skull", hc, hr, skin, [((0, -1, -0.5), 0.03, 0.4)], seg=26, ring=13)
        # armoured helmet: dome, a ridge crest, the glowing visor band and a vented mouth guard
        hm = (0.14, 0.14, 0.13)
        shell("Helmet", hc + V((0, 0.004, 0.008)), hm, arm,
              cuts=[((0, -0.11, 0.84), (0, -0.5, -0.86)), ((0, 0, 0.72), (0, 0, -1))], thick=0.014, seg=28, ring=14,
              hero=True)
        tube("Helmet_Crest", arc_on(hc + V((0, 0.004, 0.008)), hm, [(0, -1, 0.6), (0, -0.3, 1), (0, 0.6, 0.8),
                                                                    (0, 1, 0.1)], lift=0.006), arm2, r=0.018,
             radii=[0.5, 1, 1, 0.7], caps=True)
        for s, side in sides():
            cone(f"Helmet_Fin_{side}", hc + V((s * 0.12, 0.04, 0.06)), (s * 1, 0.6, 0.6), 0.03, 0.07, arm2,
                 flatten=0.4, seg=8)
        vis = arc_hit(sk, [(-0.85, -0.5, 0.32), (-0.45, -1, 0.22), (0, -1, 0.08), (0.45, -1, 0.22), (0.85, -0.5, 0.32)],
                      lift=0.006)
        tube("Visor_Frame", vis, arm2, r=0.03, radii=[0.8, 1, 1, 1, 0.8], caps=True)
        vis2 = arc_hit(sk, [(-0.75, -0.6, 0.31), (-0.4, -1, 0.22), (0, -1, 0.09), (0.4, -1, 0.22), (0.75, -0.6, 0.31)],
                       lift=0.02)
        tube("Visor", vis2, glow, r=0.017, radii=[0.7, 1, 1, 1, 0.7], caps=True)
        p, n = hit(sk, (0, -1, -0.38), 0.0)
        mg = box("Mouth_Guard", p + n * 0.01, (0.1, 0.04, 0.06), brass, bevel=0.015, rot=facing(n))
        for k, t in enumerate((-1, 0, 1)):
            box(f"Mouth_Vent{k}", p + n * 0.032 + V((t * 0.026, 0, 0)), (0.012, 0.01, 0.042), arm2, bevel=0.004,
                rot=facing(n))
        for s, side in sides():
            tube(f"Cheek_Tube_{side}", [p + V((s * 0.045, 0.0, 0.0)), p + V((s * 0.09, 0.03, 0.03)),
                                        p + V((s * 0.11, 0.08, 0.04))], arm2, r=0.012, caps=False)

    pivots = {"Body": (0, 0, 0), "Head": (0, 0, 0.68),
              "ArmL": (-sh, 0.01, shz), "ArmR": (sh, 0.01, shz),
              "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return dict(backdrop="dde6df", pivots=pivots, target=(0, -0.05, 0.5), face=(0, -0.08, 0.8), dist=2.5,
                kind="aggressive person", budget=6500)


# ====================================================================== 7. Outrider
def outrider():
    """Thanos' Outriders: eyeless, four-armed, they bound along on all fours like hounds.
    Quadruped layout (like npc_dog / npc_mutant_rat): front legs LegL/LegR (the lower pair of arms),
    back legs LegL2/LegR2, plus the upper pair of clawed arms as ArmL/ArmR and a snapping Jaw."""
    reset("Outrider")
    black, white = common_mats()
    skin = mat("Skin", "3e3856", rough=0.38, coat=0.55)
    skin2 = mat("SkinDark", "2a253b", rough=0.4, coat=0.45)
    bone = mat("Bone", "b3aed0", rough=0.3, coat=0.6)
    tooth = mat("Tooth", "fbf6e8", rough=0.2, coat=0.8)
    mouth = mat("Mouth", "7a2147", rough=0.35, coat=0.4)
    claw = mat("Claw", "ece6d6", rough=0.25, coat=0.7)
    glow = mat("Glow", "c48cff", rough=0.2, coat=0.5, emit="a35cff", emit_strength=1.6)

    with limb("Body"):
        bc, br = V((0, 0.06, 0.42)), (0.16, 0.27, 0.145)
        body = blob("Torso", bc, br, skin, [((0, -0.65, 0.75), 0.07, 0.45), ((-0.7, -0.6, 0.2), 0.03, 0.4),
                                            ((0.7, -0.6, 0.2), 0.03, 0.4), ((0, 0.7, -0.4), -0.02, 0.5)],
                    seg=30, ring=15)
        decal("Belly", bc, br, (0, -0.2, -1), (0.1, 0.03, 0.2), skin2, sink=0.6)
        # bony spine plates from the neck to the rump
        for k, a in enumerate((-55, -32, -10, 12, 34, 56)):
            r = math.radians(a)
            p, n = hit(body, (0, math.sin(r), math.cos(r)), -0.012)
            w = 0.055 - abs(a) * 0.0003
            sph(f"Spine{k}", p, (w, 0.045, 0.022), bone, rot=aim(n))
            cone(f"Spine{k}_Spike", p + n * 0.012, n + V((0, 0.5, 0)), 0.02, 0.045, bone, seg=8)
        # ribs along the flanks
        for s, side in sides():
            for k, yy in enumerate((-0.3, -0.08, 0.14)):
                pts = arc_hit(body, [(s * 0.45, yy - 0.08, 0.85), (s * 1, yy, 0.3), (s * 0.95, yy + 0.08, -0.15)],
                              lift=0.0)
                tube(f"Rib_{side}{k}", pts, bone, r=0.013, radii=[0.5, 1, 0.4], caps=True)

    with limb("Head"):
        hc, hr = V((0, -0.37, 0.5)), (0.105, 0.14, 0.085)
        sk = blob("Head_Skull", hc, hr, skin, [((0, -1, -0.3), 0.02, 0.4), ((0, 0.4, 1), 0.02, 0.5)], seg=26, ring=13)
        # smooth bony brow plate where eyes should be (they have none!)
        shell("Head_Plate", hc + V((0, 0.0, 0.006)), (0.112, 0.148, 0.09), bone,
              cuts=[((0, 0, 0.5), (0, 0, -1)), ((0, -0.48, 0), (0, -1, 0))], thick=0.01, seg=24, ring=12)
        for k, s in enumerate((-1, 1)):
            cone(f"Head_Horn{k}", hc + V((s * 0.06, 0.1, 0.05)), (s * 0.4, 1, 0.5), 0.022, 0.08, bone, seg=8)
        sph("Head_Gem", hit(sk, (0, -0.6, 0.8), 0.004)[0], (0.02, 0.02, 0.012), glow, rot=aim((0, -0.6, 0.8)))
        # wide toothy mouth: dark gums inside, a row of rounded fangs along the upper jaw
        sph("Mouth_Inside", hc + V((0, -0.04, -0.06)), (0.085, 0.11, 0.035), mouth)
        for k in range(7):
            t = (k - 3) / 3.0
            ang = t * 1.05
            p = hc + V((math.sin(ang) * 0.085, -math.cos(ang) * 0.12 - 0.005, -0.065))
            ln = 0.035 if k in (1, 5) else 0.024
            cone(f"Fang{k}", p, (0, -0.15, -1), 0.013, ln, tooth, seg=8)

    with limb("Jaw"):
        jc = V((0, -0.38, 0.405))
        sph("Jaw", jc, (0.085, 0.12, 0.03), skin2, seg=18, ring=9)
        for k in range(6):
            t = (k - 2.5) / 2.5
            ang = t * 0.95
            p = jc + V((math.sin(ang) * 0.072, -math.cos(ang) * 0.1, 0.02))
            ln = 0.03 if k in (0, 5) else 0.02
            cone(f"Jaw_Fang{k}", p, (0, -0.1, 1), 0.012, ln, tooth, seg=8)

    def claws(name, at, fwd, m, size=1.0, up=(0, 0, 1)):
        fwd = V(fwd).normalized()
        side = fwd.cross(V(up)).normalized()
        for k, t in enumerate((-1, 0, 1)):
            cone(f"{name}_Claw{k}", V(at) + side * t * 0.025 * size + V((0, 0, 0.012)), fwd + side * t * 0.25 - V(up) * 0.2,
                 0.014 * size, 0.06 * size, claw, seg=8)

    for s, side in sides():
        with limb("Leg" + side):  # front legs: the lower pair of arms, knuckle-walking
            sp, el, wr = V((s * 0.13, -0.16, 0.4)), V((s * 0.18, -0.2, 0.22)), V((s * 0.17, -0.27, 0.06))
            sph(f"Leg_{side}_Shoulder", sp, (0.06, 0.07, 0.07), skin)
            tube(f"Leg_{side}_Upper", [sp, el], skin, r=0.042, radii=[1.1, 0.85], caps=False)
            sph(f"Leg_{side}_Elbow", el, (0.04, 0.04, 0.04), skin)
            cone(f"Leg_{side}_ElbowSpike", el + V((0, 0.03, 0)), (s * 0.3, 1, 0.3), 0.018, 0.05, bone, seg=8)
            tube(f"Leg_{side}_Fore", [el, wr], skin, r=0.04, radii=[0.95, 1.1], caps=False)
            lathe(f"Leg_{side}_Cuff", [(0.0, -0.01), (0.047, -0.01), (0.054, 0.05), (0.0, 0.06)], bone,
                  loc=tuple(el + (wr - el) * 0.35), rot=aim(wr - el), seg=12)
            sph(f"Leg_{side}_Hand", wr + V((0, -0.01, -0.02)), (0.045, 0.055, 0.035), skin2)
            claws(f"Leg_{side}", wr + V((0, -0.05, -0.03)), (0, -1, -0.35), claw)
        with limb("Leg" + side + "2"):  # back legs: digitigrade haunches
            hp = V((s * 0.12, 0.22, 0.38))
            kn, hk, ft = V((s * 0.15, 0.13, 0.24)), V((s * 0.15, 0.3, 0.11)), V((s * 0.15, 0.24, 0.036))
            sph(f"Leg{side}2_Haunch", hp + V((s * 0.02, -0.02, -0.04)), (0.075, 0.11, 0.1), skin, seg=18, ring=9)
            tube(f"Leg{side}2_Thigh", [hp, kn], skin, r=0.045, caps=False)
            tube(f"Leg{side}2_Shin", [kn, hk], skin, r=0.034, radii=[1, 0.85], caps=True)
            tube(f"Leg{side}2_Foot", [hk, ft], skin2, r=0.03, radii=[0.9, 1.0], caps=False)
            sph(f"Leg{side}2_Paw", ft + V((0, -0.02, -0.005)), (0.04, 0.055, 0.028), skin2)
            claws(f"Leg{side}2", ft + V((0, -0.06, -0.01)), (0, -1, -0.3), claw, size=0.9)
        with limb("Arm" + side):  # upper pair of arms, reaching forward to grab
            sp, el, wr = V((s * 0.14, -0.2, 0.5)), V((s * 0.23, -0.27, 0.47)), V((s * 0.19, -0.42, 0.45))
            sph(f"Arm_{side}_Shoulder", sp, (0.045, 0.045, 0.045), skin)
            shell(f"Arm_{side}_Plate", sp + V((0, 0, 0.008)), (0.055, 0.055, 0.045), bone,
                  cuts=[((0, 0, sp.z - 0.005), (0, 0, -1))], thick=0.008, seg=16, ring=8)
            tube(f"Arm_{side}_Upper", [sp, el], skin, r=0.028, caps=False)
            sph(f"Arm_{side}_Elbow", el, (0.03, 0.03, 0.03), skin)
            tube(f"Arm_{side}_Fore", [el, wr], skin, r=0.026, radii=[1, 1.1], caps=False)
            sph(f"Arm_{side}_Hand", wr, (0.035, 0.04, 0.03), skin2)
            claws(f"Arm_{side}", wr + V((0, -0.03, 0)), (0, -1, 0.1), claw, size=0.9)

    pivots = {"Body": (0, 0, 0), "Head": (0, -0.24, 0.47), "Jaw": (0, -0.29, 0.43),
              "LegL": (-0.13, -0.16, 0.4), "LegR": (0.13, -0.16, 0.4),
              "LegL2": (-0.12, 0.22, 0.38), "LegR2": (0.12, 0.22, 0.38),
              "ArmL": (-0.14, -0.2, 0.5), "ArmR": (0.14, -0.2, 0.5)}
    return dict(backdrop="e6e1ee", pivots=pivots, parents={"Jaw": "Head"}, target=(0, -0.05, 0.32),
                face=(0, -0.4, 0.46), dist=2.2, yaw=38, kind="aggressive creature", budget=6000)


# ====================================================================== runner
CHARS = {"thanos": thanos, "ebony_maw": ebony_maw, "proxima_midnight": proxima_midnight,
         "corvus_glaive": corvus_glaive, "cull_obsidian": cull_obsidian,
         "chitauri": chitauri, "outrider": outrider}


def make(name):
    opts = CHARS[name]()
    f = opts.get("scale", 1.0)
    if f != 1.0:
        toykit.STATE["root"].scale = (f, f, f)
        bpy.context.view_layer.update()
        opts["pivots"] = {k: tuple(c * f for c in v) for k, v in opts["pivots"].items()}
        opts["target"] = tuple(c * f for c in opts["target"])
        if "face" in opts:
            opts["face"] = tuple(c * f for c in opts["face"])
    return opts


def build(name, budget=6500):
    fast = "--fast" in sys.argv
    concept = os.path.join(ROOT, "concepts", f"npc_{name}.png")
    portrait = os.path.join(ROOT, "assets", "portraits", f"npc_{name}.png")
    if not fast:
        npc_kit.DETAIL[0] = 1.0
        opts = make(name)
        finalize()
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        cam_at(opts["target"], opts["dist"], opts.get("yaw", 32), opts.get("pitch", 14))
        render(concept, 1024, samples=96)
        downscale(concept, portrait, 320)
    npc_kit.DETAIL[0] = 1.0
    for attempt in range(6):
        opts = make(name)
        finalize()
        total = sum(tri_report().values())
        print(f"BUDGET {name} detail={npc_kit.DETAIL[0]:.2f} tris={total}")
        if os.environ.get("NPC_TOP"):
            per = []
            for o in mesh_objs():
                o.data.calc_loop_triangles()
                per.append((len(o.data.loop_triangles), o.name))
            print("TOP", sorted(per, reverse=True)[:18])
        if total <= opts.get("budget", budget):
            break
        if npc_kit.DETAIL[0] <= 0.45:
            print(f"WARNING {name} over budget at the detail floor")
            break
        npc_kit.DETAIL[0] = max(0.45, npc_kit.DETAIL[0] * (opts.get("budget", budget) / total) ** 1.2 * 0.97)
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
            cam_at(tgt, dist * 0.55 if k == 3 else dist, yaw, pitch, lens=60)
            if k == 3:  # close-up of the face
                cam_at(opts.get("face", tgt), dist * 0.4, 15, 5, lens=60)
            pth = os.path.join(SCRATCH, f"{name}_v{k}.png")
            render(pth, 420, samples=24)
            views.append(pth)
        cam_at(tgt, dist, 25, 35)
        small = os.path.join(SCRATCH, f"{name}_small.png")
        render(small, 72, samples=16)
        views.append(small)
        contact_sheet(views, os.path.join(SCRATCH, f"{name}_sheet.png"), cols=3, cell=420)
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
