# Playable hero figures (set A): stylised toy versions of the Avengers, built from primitives.
# Run one:  blender --background --python art/src/heroes_a.py -- spider_man
# Run all:  blender --background --python art/src/heroes_a.py -- all
# Flags:    --fast (skip the concept/portrait renders), --preview (only render a quick concept to
#           $HERO_SCRATCH, no export)
# Each run writes art/characters/hero_<id>.blend, concepts/hero_<id>.png,
# assets/portraits/hero_<id>.png (320px head-and-shoulders) and assets/characters/hero_<id>.glb.
#
# Conventions (same as the npc figures; see npcs.py / player.gd):
# - Blender: faces -Y, feet on z=0, L = -X. After glTF import Godot sees them facing +Z.
# - Same units as kid.glb (the kid is ~0.97 tall; the game scales by 0.55). Heroes ~1.06, Hulk ~1.35.
# - Nodes Body, Head, ArmL, ArmR, LegL, LegR (+ Cape for Thor / Doctor Strange), each one mesh with
#   its origin at the joint and identity rotation/scale, so animation = rotate the node about its origin.
# - ArmR ends in an empty hand at its lowest point (the game hangs held items off the bottom of ArmR).
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import npc_kit
importlib.reload(npc_kit)
from npc_kit import *
from npc_kit import _d, FLOOR
from mathutils import Vector, Quaternion, Euler

SCRATCH = os.environ.get("HERO_SCRATCH", "")
X90 = Quaternion((1, 0, 0), math.pi / 2)
Y90 = Quaternion((0, 1, 0), math.pi / 2)


def sides():
    return ((-1, "L"), (1, "R"))


def V(*a):
    return Vector(a[0] if len(a) == 1 else a)


# ====================================================================== surface-hugging details
class S:
    """An ellipsoid (optionally with blob bumps) parametrised by unit-sphere direction, so raised
    lines and decal plates can be laid exactly on a part's surface."""

    def __init__(self, center, radii, bumps=(), taper=0.0, jaw=0.0, flat_back=0.0):
        self.c, self.r = Vector(center), Vector(radii)
        self.bumps = [(Vector(b[0]).normalized(), b[1], b[2]) for b in bumps]
        self.taper, self.jaw, self.flat_back = taper, jaw, flat_back

    def pos(self, d):
        d = Vector(d).normalized()
        off = sum(h * math.exp(-(d.angle(bd, 0.0) / w) ** 2) for bd, h, w in self.bumps)
        x, y, z = d.x * self.r.x, d.y * self.r.y, d.z * self.r.z
        if self.taper and d.z < 0:  # narrower towards the chin (egg / mask shape)
            k = 1 - self.taper * (-d.z) ** 1.6
            x *= k
            y *= 1 - self.taper * 0.5 * (-d.z) ** 1.6
        if self.jaw and d.z < 0 and d.y < 0:  # chin pushes forward a touch
            y -= self.jaw * (-d.z) * (-d.y) * self.r.y
        if self.flat_back and d.y > 0:
            y *= 1 - self.flat_back * d.y
        return self.c + Vector((x, y, z)) + d * off

    def mesh(self, name, m, seg=28, ring=16, hero=True):
        """A smooth mesh of exactly this surface (so lines/plates laid on it sit flush)."""
        seg, ring = _d(seg, FLOOR.get(seg, 14), hero), _d(ring, 8, hero, even=False)
        me = bpy.data.meshes.new(name)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
        for v in bm.verts:
            v.co = self.pos(v.co) - self.c
        bm.to_mesh(me)
        bm.free()
        return toykit._obj(name, me, m, self.c)

    def at(self, d):
        d = Vector(d).normalized()
        a = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        t1 = a.cross(d).normalized()
        t2 = d.cross(t1).normalized()
        e = 0.01
        p = self.pos(d)
        n = (self.pos(d + t1 * e) - self.pos(d - t1 * e)).cross(self.pos(d + t2 * e) - self.pos(d - t2 * e))
        n.normalize()
        if n.dot(p - self.c) < 0:
            n = -n
        return p, n


def frame(d0):
    F = Vector(d0).normalized()
    up = Vector((0, 0, 1)) if abs(F.z) < 0.95 else Vector((0, 1, 0))
    R = up.cross(F).normalized()
    U = F.cross(R).normalized()
    return F, R, U


def uvdir(d0, u, v):
    """Direction at 'longitude' u (towards image-right, +X for a front-facing d0) and 'latitude' v
    (up) around d0, both in radians."""
    F, R, U = frame(d0)
    return (math.cos(v) * (math.cos(u) * F + math.sin(u) * R) + math.sin(v) * U).normalized()


def polar(d0, phi, theta):
    """Direction phi radians away from d0, at angle theta around it (0 = image-right, pi/2 = up)."""
    F, R, U = frame(d0)
    return (math.cos(phi) * F + math.sin(phi) * (math.cos(theta) * R + math.sin(theta) * U)).normalized()


def _cr(pts, n, closed=False):
    """Catmull-Rom through points (Vectors), n samples per span."""
    P = [Vector(p) for p in pts]
    m = len(P)
    out = []
    spans = m if closed else m - 1
    for i in range(spans):
        p0 = P[(i - 1) % m] if closed else P[max(i - 1, 0)]
        p1, p2 = P[i % m], P[(i + 1) % m]
        p3 = P[(i + 2) % m] if closed else P[min(i + 2, m - 1)]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return out


def _fix(bm, f, want):
    if f.normal.length > 0 and f.normal.dot(want) < 0:
        f.normal_flip()


def ridge(name, srf, dirs, m, w=0.006, h=0.003, closed=False, flat=False, smooth=4, step=0.012, sink=0.0015, lean=None):
    """A raised line hugging a surface, through control directions (smoothed). 4 tris per sample
    (6 when flat)."""
    lean = (DETAIL[0] < 0.8 and not flat) if lean is None else lean
    D = _cr([Vector(d).normalized() for d in dirs], smooth, closed) if smooth > 1 else [Vector(d).normalized() for d in dirs]
    D = [d.normalized() for d in D]
    # resample by arc length on the surface
    P = [srf.at(d) for d in D]
    tot = sum((P[i + 1][0] - P[i][0]).length for i in range(len(P) - 1))
    st = step / max(0.4, DETAIL[0])
    n = max(3, int(tot / st))
    if len(P) > n * 1.4:
        keep = [round(i * (len(P) - 1) / n) for i in range(n + 1)]
        P = [P[k] for k in keep]
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    secs = []
    cnt = len(P)
    for i, (p, nn) in enumerate(P):
        a = P[(i - 1) % cnt][0] if (closed or i > 0) else p
        b = P[(i + 1) % cnt][0] if (closed or i < cnt - 1) else p
        t = (b - a).normalized()
        sd = t.cross(nn).normalized()
        if flat:
            sec = [p + sd * w / 2 - nn * sink, p + sd * w * 0.36 + nn * h, p - sd * w * 0.36 + nn * h, p - sd * w / 2 - nn * sink]
        elif lean:  # game build: a flat ribbon just proud of the surface (2 tris per sample)
            sec = [p + sd * w * 0.55 + nn * h * 0.45, p - sd * w * 0.55 + nn * h * 0.45]
        else:
            sec = [p + sd * w / 2 - nn * sink, p + nn * h, p - sd * w / 2 - nn * sink]
        secs.append(([bm.verts.new(v) for v in sec], nn))
    rng = range(cnt if closed else cnt - 1)
    for i in rng:
        A, na = secs[i]
        B, _ = secs[(i + 1) % cnt]
        for k in range(len(A) - 1):
            f = bm.faces.new((A[k], A[k + 1], B[k + 1], B[k]))
            f.normal_update()
            _fix(bm, f, na)
    if not closed and not lean:
        for idx, sgn in ((0, -1), (cnt - 1, 1)):
            A, na = secs[idx]
            f = bm.faces.new(A)
            f.normal_update()
            o = secs[min(cnt - 1, idx + 1)][0][0].co - A[0].co if sgn < 0 else A[0].co - secs[idx - 1][0][0].co
            _fix(bm, f, o * sgn * -1 if sgn < 0 else o)
    bm.to_mesh(me)
    bm.free()
    return toykit._obj(name, me, m)


def patch(name, srf, d0, outline, m, thick=0.004, rings=3, sub=3, sink=0.002, bevel=0.35, closed_smooth=True):
    """A raised plate hugging a surface: outline is a closed list of (u, v) radians around d0 (see uvdir).
    The rim is slightly rounded (bevel = fraction of the thickness pulled in at the top edge)."""
    O = [Vector((u, v, 0)) for u, v in outline]
    if closed_smooth and sub > 1:
        O = _cr(O, max(1, int(round(sub * max(0.5, DETAIL[0])))), closed=True)
    c = sum(O, Vector()) / len(O)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()

    def top(uv):
        p, nn = srf.at(uvdir(d0, uv.x, uv.y))
        return p + nn * thick, nn

    cp, cn = top(c)
    ctr = bm.verts.new(cp)
    rings_v = []
    for k in range(1, rings + 1):
        t = k / rings
        if k == rings:
            # pull the top rim in a touch for a soft bevel
            row = [top(c + (o - c) * (1.0 - bevel * 0.04 / max(0.05, (o - c).length) * thick / 0.004)) for o in O]
        else:
            row = [top(c + (o - c) * t) for o in O]
        rings_v.append([(bm.verts.new(p), nn) for p, nn in row])
    base = []
    for o in O:
        p, nn = srf.at(uvdir(d0, o.x, o.y))
        base.append(bm.verts.new(p - nn * sink))
    L = len(O)
    for i in range(L):
        j = (i + 1) % L
        f = bm.faces.new((ctr, rings_v[0][i][0], rings_v[0][j][0]))
        f.normal_update(); _fix(bm, f, cn)
        for k in range(rings - 1):
            f = bm.faces.new((rings_v[k][i][0], rings_v[k + 1][i][0], rings_v[k + 1][j][0], rings_v[k][j][0]))
            f.normal_update(); _fix(bm, f, rings_v[k][i][1])
        a, b = rings_v[-1][i][0], rings_v[-1][j][0]
        f = bm.faces.new((a, base[i], base[j], b))
        f.normal_update()
        _fix(bm, f, ((a.co + b.co) / 2 - cp))
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m)
    return o


def shell(name, center, radii, m, planes, inflate=0.006, seg=24, ring=12, hero=False, srf=None):
    """A skin-tight layer over an ellipsoid (or an S surface), cut by planes (unit-sphere space, keep
    the side the normal points to) - crisp-edged suit panels, stripes, helmets."""
    seg, ring = _d(seg, FLOOR.get(seg, 12), hero), _d(ring, 6, hero, even=False)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_inner=True)
    srf = srf or S(center, radii)
    for v in bm.verts:
        d = v.co.normalized()
        p, n = srf.at(d)
        v.co = p - srf.c + n * inflate
    bm.to_mesh(me)
    bm.free()
    return toykit._obj(name, me, m, srf.c)


def offset_outline(O, amt):
    """Grow a closed (u, v) outline outward by amt (radians), along the averaged edge normals."""
    P = [Vector((u, v)) for u, v in O]
    n = len(P)
    c = sum(P, Vector((0, 0))) / n
    out = []
    for i in range(n):
        a, b = P[i - 1], P[(i + 1) % n]
        t = (b - a).normalized()
        nn = Vector((t.y, -t.x))
        if nn.dot(P[i] - c) < 0:
            nn = -nn
        q = P[i] + nn * amt
        out.append((q.x, q.y))
    return out


def star_plate(name, center, normal, R, m, thick=0.006, inner=0.42, up=(0, 0, 1)):
    """Flat five-point star with bevelled-looking sides, facing `normal`."""
    n = Vector(normal).normalized()
    upv = Vector(up)
    upv = (upv - n * upv.dot(n)).normalized()
    rt = upv.cross(n).normalized()
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    c = Vector(center)
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = R if k % 2 == 0 else R * inner
        pts.append(c + (rt * math.cos(a) + upv * math.sin(a)) * rr)
    ctop = bm.verts.new(c + n * thick * 1.6)
    topv = [bm.verts.new(p + n * thick) for p in pts]
    bot = [bm.verts.new(p - n * 0.001) for p in pts]
    for i in range(10):
        j = (i + 1) % 10
        f = bm.faces.new((ctop, topv[i], topv[j])); f.normal_update(); _fix(bm, f, n)
        f = bm.faces.new((topv[i], bot[i], bot[j], topv[j])); f.normal_update(); _fix(bm, f, (pts[i] + pts[j]) / 2 - c)
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m)
    for p in o.data.polygons:
        p.use_smooth = False
    return o


def sheet(name, grid, m, thick=0.012):
    """Cloth sheet from a grid of points (rows top->bottom), thickened (solidify, applied by finalize)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rows = [[bm.verts.new(p) for p in row] for row in grid]
    for i in range(len(rows) - 1):
        for j in range(len(rows[i]) - 1):
            bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1]))
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m)
    mod = o.modifiers.new("Solid", "SOLIDIFY")
    mod.thickness = thick
    mod.offset = 0.0
    mod.use_even_offset = True
    return o


def cape_grid(top_z, bot_z, top_w, bot_w, y0, depth, nu=14, nv=9, folds=3, fold_amp=0.012, wrap=0.05, hem=0.03,
              back_y=None):
    nu = max(8, int(nu * max(0.6, DETAIL[0])))
    nv = max(5, int(nv * max(0.6, DETAIL[0])))
    grid = []
    for i in range(nv + 1):
        v = i / nv
        row = []
        w = top_w + (bot_w - top_w) * v ** 0.8
        for j in range(nu + 1):
            u = -1 + 2 * j / nu
            x = u * w
            y = y0 + depth(v) - wrap * u * u * (1 - v) ** 2 + fold_amp * v * math.cos(u * folds * math.pi)
            z = top_z - (top_z - bot_z) * v - hem * v * (1 - u * u) + 0.012 * (1 - v) ** 3 * (u * u)
            row.append(Vector((x, y, z)))
        grid.append(row)
    return grid


# ====================================================================== flat plates
def poly_plate(name, center, normal, pts, m, thick=0.006, up=(0, 0, 1), dome=0.5):
    """Flat plate from a star-shaped 2D outline (x right, y up, in metres) facing `normal`."""
    n = Vector(normal).normalized()
    upv = Vector(up)
    upv = (upv - n * upv.dot(n)).normalized()
    rt = upv.cross(n).normalized()
    c = Vector(center)
    W = [c + rt * x + upv * y for x, y in pts]
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cc = sum(W, Vector()) / len(W)
    ctop = bm.verts.new(cc + n * thick * (1 + dome))
    topv = [bm.verts.new(p + n * thick) for p in W]
    bot = [bm.verts.new(p - n * 0.0015) for p in W]
    L = len(W)
    for i in range(L):
        j = (i + 1) % L
        f = bm.faces.new((ctop, topv[i], topv[j])); f.normal_update(); _fix(bm, f, n)
        f = bm.faces.new((topv[i], bot[i], bot[j], topv[j])); f.normal_update(); _fix(bm, f, (W[i] + W[j]) / 2 - cc)
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m)
    for p in o.data.polygons:
        p.use_smooth = False
    return o


def star_pts(R, inner=0.42):
    return [((R if k % 2 == 0 else R * inner) * math.cos(math.pi / 2 + k * math.pi / 5),
             (R if k % 2 == 0 else R * inner) * math.sin(math.pi / 2 + k * math.pi / 5)) for k in range(10)]


def circle_pts(R, n=16):
    return [(R * math.cos(2 * math.pi * k / n), R * math.sin(2 * math.pi * k / n)) for k in range(n)]


# ====================================================================== faces
def on_s(H, d, out=0.0):
    p, n = H.at(d)
    return p + n * out


def eye_s(name, H, d, w, h, black, white, depth=0.02, tilt=0.0):
    p, n = H.at(d)
    q = facing(n) @ Quaternion((0, 1, 0), tilt)
    sph(name, p - n * depth * 0.3, (w, depth, h), black, seg=14, ring=8, rot=q)
    side = q @ Vector((1, 0, 0))
    up = q @ Vector((0, 0, 1))
    sgn = 1 if d[0] >= 0 else -1
    s = min(w, h) * 0.36
    sph(name + "_Shine", p + n * depth * 0.6 + up * h * 0.36 - side * w * 0.28 * sgn, (s, s * 0.6, s), white, seg=8, ring=4, rot=q)
    s2 = s * 0.45
    sph(name + "_Shine2", p + n * depth * 0.55 - up * h * 0.34 + side * w * 0.3 * sgn, (s2, s2 * 0.6, s2), white, seg=6, ring=4, rot=q)


def face(H, black, white, skin, brow_m, mouth_m, ex=0.34, ez=0.0, ew=0.03, eh=0.04, brow_z=0.27, angry=0.05,
         brow_r=0.012, mouth="smirk", mz=-0.42, nose=True, blush=None, brow_lift=(0.0, 0.0), do_ears=True, ear_z=-0.03):
    for s, side in sides():
        eye_s(f"Eye_{side}", H, (s * ex, -1, ez), ew, eh, black, white)
        if brow_m is not None:
            bl = brow_lift[0 if s < 0 else 1]
            pts = [on_s(H, (s * (ex - 0.15), -1, ez + brow_z - angry + bl), 0.004),
                   on_s(H, (s * ex, -1, ez + brow_z + 0.025 + bl), 0.004),
                   on_s(H, (s * (ex + 0.16), -1, ez + brow_z + 0.0 + bl * 0.6), 0.004)]
            tube(f"Brow_{side}", pts, brow_m, r=brow_r, radii=[0.85, 1, 0.65], caps=False)
        if blush is not None:
            p, n = H.at((s * 0.56, -1, ez - 0.27))
            sph(f"Blush_{side}", p - n * 0.003, (0.03, 0.006, 0.017), blush, rot=facing(n), seg=10, ring=4)
        if do_ears:
            p, n = H.at((s, 0.05, ear_z))
            sph(f"Ear_{side}", p - n * 0.008, (0.026, 0.03, 0.044), skin)
    if nose:
        p, n = H.at((0, -1, ez - 0.2))
        sph("Nose", p, (0.022, 0.018, 0.02), skin, seg=10, ring=6)
    if mouth == "smirk":
        pts = [on_s(H, d, 0.001) for d in [(-0.12, -1, mz + 0.02), (-0.03, -1, mz - 0.025), (0.06, -1, mz - 0.02), (0.14, -1, mz + 0.045)]]
        tube("Smile", pts, mouth_m, r=0.0072)
    elif mouth == "smile":
        pts = [on_s(H, d, 0.001) for d in [(-0.13, -1, mz + 0.05), (-0.05, -1, mz - 0.01), (0.05, -1, mz - 0.01), (0.13, -1, mz + 0.05)]]
        tube("Smile", pts, mouth_m, r=0.0072)
    elif mouth == "flat":
        pts = [on_s(H, d, 0.001) for d in [(-0.1, -1, mz + 0.01), (0.0, -1, mz - 0.01), (0.1, -1, mz + 0.01)]]
        tube("Smile", pts, mouth_m, r=0.0068)


# ====================================================================== base figure
BASE = dict(sx=0.212, sz=0.625, hx=0.082, hz=0.335,
            chest_c=(0, 0, 0.565), chest_r=(0.198, 0.136, 0.152),
            waist_c=(0, 0.008, 0.44), waist_r=(0.136, 0.104, 0.092),
            pelvis_c=(0, 0.008, 0.36), pelvis_r=(0.146, 0.114, 0.07),
            delt=(0.054, 0.053, 0.06), arm_r=0.04, fore_r=0.042, fist=(0.05, 0.052, 0.056),
            thigh_r=0.062, shin_r=0.052, knee_z=0.18, boot_top=0.15,
            head_c=(0, 0, 0.855), head_r=(0.188, 0.178, 0.188), pecs=0.016, lats=0.014)


def pecs_bumps(P):
    k, l = P["pecs"], P["lats"]
    return [((-0.42, -1, 0.32), k, 0.36), ((0.42, -1, 0.32), k, 0.36), ((-0.9, 0.15, 0.5), l, 0.4),
            ((0.9, 0.15, 0.5), l, 0.4), ((0, 0.7, 0.8), 0.008, 0.45)]


def figure(M, P=None, gloves=True, boots=True, skip=()):
    """Toy-hero body: chest, waist, pelvis, two arms ending in fists, two legs ending in boots.
    M maps region -> material. Returns the parameters (with surfaces and key points) for decorating."""
    P = dict(BASE, **(P or {}))
    g = lambda k, d=None: M.get(k, M.get(d) if d else None) or M["chest"]
    sx, sz, hx, hz = P["sx"], P["sz"], P["hx"], P["hz"]
    P["C"] = S(P["chest_c"], P["chest_r"], pecs_bumps(P))
    P["W"] = S(P["waist_c"], P["waist_r"])
    P["Pv"] = S(P["pelvis_c"], P["pelvis_r"])
    with limb("Body"):
        if "chest" not in skip:
            P["C"].mesh("Chest", g("chest"), seg=28, ring=16)
        if "waist" not in skip:
            P["W"].mesh("Waist", g("waist", "chest"), seg=24, ring=12)
        if "pelvis" not in skip:
            P["Pv"].mesh("Pelvis", g("pelvis", "waist"), seg=24, ring=12)
    P["elbow"], P["wrist"], P["fist_c"], P["shoulder"], P["foot"], P["knee"] = {}, {}, {}, {}, {}, {}
    for s, side in sides():
        with limb("Arm" + side):
            sh = V(s * (sx - 0.012), 0, sz + 0.004)
            el = V(s * (sx + 0.03), 0.004, sz - 0.128)
            wr = V(s * (sx + 0.04), -0.018, sz - 0.228)
            fc = V(s * (sx + 0.042), -0.024, sz - 0.27)
            P["elbow"][side], P["wrist"][side], P["fist_c"][side], P["shoulder"][side] = el, wr, fc, sh
            if "delt" not in skip:
                sph(f"Shoulder_{side}", sh, P["delt"], g("shoulder", "chest"))
            tube(f"Arm_{side}", [sh + V(s * 0.006, 0, -0.025), (sh + el) / 2 + V(s * 0.005, 0, 0), el], g("upper", "chest"),
                 r=P["arm_r"], radii=[1.08, 1.0, 0.86], caps=False)
            sph(f"Arm_{side}_Elbow", el, (P["arm_r"] * 0.98,) * 3, g("upper", "chest"))
            tube(f"Arm_{side}_Fore", [el, wr], g("fore", "upper"), r=P["fore_r"], radii=[0.84, 1.04], caps=False)
            if gloves:
                tube(f"Arm_{side}_Cuff", [wr + (el - wr) * 0.3, wr - (el - wr) * 0.02], g("cuff", "glove"),
                     r=P["fore_r"] * 1.13, radii=[1.1, 1.0], caps=False)
            fr = P["fist"]
            sph(f"Hand_{side}", fc, fr, g("glove", "fore"), seg=16, ring=8)
            sph(f"Hand_{side}_Thumb", fc + V(-s * fr[0] * 0.5, -fr[1] * 0.66, fr[2] * 0.22), (fr[0] * 0.4, fr[0] * 0.38, fr[0] * 0.5),
                g("glove", "fore"), seg=10, ring=5)
            sph(f"Hand_{side}_Knuckles", fc + V(s * fr[0] * 0.08, -fr[1] * 0.38, -fr[2] * 0.22), (fr[0] * 0.9, fr[1] * 0.7, fr[2] * 0.68),
                g("glove", "fore"), seg=12, ring=6)
        with limb("Leg" + side):
            hip = V(s * hx, 0.0, hz)
            kn = V(s * (hx + 0.004), -0.004, P["knee_z"])
            an = V(s * (hx + 0.004), 0.0, 0.07)
            P["knee"][side] = kn
            tube(f"Leg_{side}", [hip, (hip + kn) / 2, kn], g("thigh", "pelvis"), r=P["thigh_r"], radii=[1.06, 1.0, 0.78], caps=False)
            sph(f"Leg_{side}_Knee", kn, (P["shin_r"] * 1.02,) * 3, g("shin", "thigh"))
            tube(f"Leg_{side}_Shin", [kn, an], g("shin", "thigh"), r=P["shin_r"], radii=[0.9, 0.86], caps=False)
            bx = s * (hx + 0.006)
            if boots:
                bt = P["boot_top"]
                tube(f"Boot_{side}_Top", [V(bx, 0.0, bt), V(bx, -0.004, 0.05)], g("boot", "shin"),
                     r=P["shin_r"] * 1.12, radii=[1.12, 1.0], caps=False)
                torus(f"Boot_{side}_Rim", V(bx, 0.0, bt), P["shin_r"] * 1.2, 0.012, g("boot_rim", "boot"))
            P["foot"][side] = V(bx, -0.03, 0.052)
            sph(f"Foot_{side}", V(bx, -0.03, 0.052), (0.064, 0.1, 0.054), g("boot", "shin"), seg=16, ring=8)
            sph(f"Sole_{side}", V(bx, -0.032, 0.02), (0.067, 0.103, 0.021), g("sole", "boot"), seg=16, ring=6)
    hc, hr = P["head_c"], P["head_r"]
    P["pivots"] = {"Body": (0, 0, 0), "Head": (0, 0, hc[2] - hr[2] + 0.05),
                   "ArmL": (-sx, 0, sz), "ArmR": (sx, 0, sz), "LegL": (-hx, 0, hz), "LegR": (hx, 0, hz)}
    return P


def neck(P, m, r=0.056):
    hc = P["head_c"]
    cyl("Neck", (0, 0.008, hc[2] - P["head_r"][2] + 0.0), r, 0.12, m, seg=16)


def web_disc(name, srf, ctr, m, phis, nrad=10, phi0=0.06, phi1=None, w=0.005, h=0.0027, sag=0.07, rot=0.5):
    """Spider-web: strands radiating from direction ctr, scalloped rings between them."""
    phi1 = phi1 or phis[-1] + 0.4
    thetas = [2 * math.pi * (k + rot) / nrad for k in range(nrad)]
    for k, th in enumerate(thetas):
        ps = [phi0 + (phi1 - phi0) * t for t in (0, 0.25, 0.5, 0.75, 1.0)]
        ridge(f"{name}_R{k}", srf, [polar(ctr, ph, th) for ph in ps], m, w=w, h=h, smooth=3)
    for i, ph in enumerate(phis):
        pts = []
        for k, th in enumerate(thetas):
            pts.append(polar(ctr, ph, th))
            pts.append(polar(ctr, ph - sag * (0.6 + 0.4 * i / max(1, len(phis) - 1)), th + math.pi / nrad))
        ridge(f"{name}_C{i}", srf, pts, m, w=w * 0.95, h=h, closed=True, smooth=3)


# ====================================================================== 1. Spider-Man
def spider_man():
    reset("SpiderMan")
    black, white = common_mats()
    red = mat("SpideyRed", "d21f2b", rough=0.3, coat=0.85)
    blue = mat("SpideyBlue", "1b4cc0", rough=0.32, coat=0.75)
    web = mat("Web", "17111a", rough=0.3, coat=0.5)
    lens = mat("Lens", "f7faff", rough=0.06, coat=1.0, emit="ffffff", emit_strength=0.3)
    rim = mat("LensRim", "0e0e12", rough=0.18, coat=0.9)
    sole = mat("Sole", "8f141c", rough=0.4, coat=0.5)

    P = figure(dict(chest=red, waist=red, pelvis=blue, shoulder=red, upper=blue, fore=red, cuff=red, glove=red,
                    thigh=blue, shin=blue, boot=red, sole=sole), dict(pecs=0.014))
    hc = Vector(P["head_c"])
    H = S(hc, (0.18, 0.172, 0.195), taper=0.26)
    with limb("Head"):
        neck(P, red, 0.055)
        H.mesh("Head", red, seg=30, ring=18)
        web_disc("Head_Web", H, Vector((0, -1, -0.28)), web, (0.32, 0.66, 1.02, 1.42, 1.86, 2.32), nrad=12,
                 phi1=2.8, sag=0.075)
        # big white lenses, heavy black rims; inner corners point down towards the nose
        lens_o = [(0.075, -0.17), (0.09, -0.02), (0.17, 0.14), (0.32, 0.25), (0.52, 0.28), (0.68, 0.2), (0.73, 0.04),
                  (0.64, -0.11), (0.44, -0.19), (0.22, -0.21)]
        for s, side in sides():
            lo = [(s * u, v) for u, v in lens_o]
            if s < 0:
                lo = lo[::-1]
            ro = offset_outline(lo, 0.04)
            patch(f"Eye_{side}_Rim", H, (0, -1, 0), ro, rim, thick=0.008, rings=3)
            patch(f"Eye_{side}_Lens", H, (0, -1, 0), lo, lens, thick=0.0125, rings=3)

    C, W = P["C"], P["W"]
    with limb("Body"):
        # blue flanks; blue back below the shoulder yoke (red web up top, front panel stays red)
        for s, side in sides():
            shell(f"Chest_Side_{side}", None, None, blue, [((s * 0.6, 0, 0), (s, 0.0, 0.0))], inflate=0.009, seg=28, ring=16, srf=C)
            shell(f"Waist_Side_{side}", None, None, blue, [((s * 0.52, 0, 0), (s, 0, 0.0))], inflate=0.008, srf=W)
        shell("Chest_Back", None, None, blue, [((0, 0.25, 0), (0, 1, 0)), ((0, 0, 0.5), (0, -0.4, -1))], inflate=0.0085,
              seg=28, ring=16, srf=C)
        shell("Waist_Back", None, None, blue, [((0, 0.2, 0), (0, 1, 0))], inflate=0.007, srf=W)
        # web over the red: chest panel radiates from the spider, shoulders/yoke get their own
        sc = Vector((0, -1, 0.32))
        web_disc("Chest_Web", C, sc, web, (0.3, 0.6, 0.92, 1.25), nrad=10, phi1=1.7, sag=0.06, rot=0.0)
        web_disc("Waist_Web", W, Vector((0, -1, 0.9)), web, (0.6, 0.95, 1.3), nrad=12, phi0=0.3, phi1=1.7, sag=0.06)
        web_disc("Yoke_Web", C, Vector((0, 0.3, 1)), web, (0.4, 0.8), nrad=10, phi0=0.1, phi1=1.2, sag=0.06)
        # black spider on the chest (covers the web centre)
        def spider(nm, srf, cdir, m, k=1.0, th=0.006):
            patch(nm + "_Body", srf, cdir, [(0, 0.03 * k), (0.03 * k, 0.0), (0.028 * k, -0.07 * k), (0, -0.15 * k),
                                            (-0.028 * k, -0.07 * k), (-0.03 * k, 0.0)], m, thick=th)
            patch(nm + "_Head", srf, cdir, [(0, 0.09 * k), (0.022 * k, 0.065 * k), (0, 0.035 * k), (-0.022 * k, 0.065 * k)], m,
                  thick=th)
            for sg in (-1, 1):
                for j, pts in enumerate([((0.02, 0.05), (0.12, 0.13), (0.17, 0.27)), ((0.025, 0.02), (0.15, 0.06), (0.24, 0.14)),
                                         ((0.025, -0.01), (0.15, -0.05), (0.23, -0.02)), ((0.02, -0.04), (0.11, -0.13), (0.16, -0.26))]):
                    ridge(f"{nm}_Leg{sg}{j}", srf, [uvdir(cdir, sg * a * k, b * k) for a, b in pts], m, w=0.008 * k ** 0.5,
                          h=th * 0.7, smooth=3, lean=False)
        spider("Spider", C, sc, web, 1.3)
        spider("Spider_Back", C, Vector((0, 1, 0.1)), red, 2.3, th=0.013)
        shell("Belt_Line", None, None, red, [((0, 0, -0.12), (0, 0, 1)), ((0, 0, 0.12), (0, 0, -1))], inflate=0.006,
              srf=P["Pv"], seg=24, ring=12)
    for s, side in sides():
        with limb("Arm" + side):
            fc = P["fist_c"][side]
            G = S(fc, P["fist"])
            web_disc(f"Hand_{side}_Web", G, Vector((0, -0.3, -1)), web, (0.5, 1.0), nrad=6, phi0=0.1, phi1=1.5,
                     w=0.004, h=0.002)
            Sh = S(P["shoulder"][side], P["delt"])
            web_disc(f"Shoulder_{side}_Web", Sh, Vector((s * 0.6, 0, 1)), web, (0.5, 1.0), nrad=8, phi0=0.1, phi1=1.6,
                     w=0.0045, h=0.0022)
        with limb("Leg" + side):
            F = S(P["foot"][side], (0.064, 0.1, 0.054))
            web_disc(f"Foot_{side}_Web", F, Vector((0, -1, 0.5)), web, (0.45, 0.9), nrad=8, phi0=0.08, phi1=1.4,
                     w=0.0045, h=0.0022)
    return dict(P=P, backdrop="dfe6f2", target=(0, 0, 0.55), dist=2.35, budget=7500)


# ====================================================================== 2. Iron Man
def iron_man():
    reset("IronMan")
    black, white = common_mats()
    red = mat("ArmourRed", "b8141f", rough=0.2, metal=0.55, coat=1.0)
    gold = mat("ArmourGold", "e2a83a", rough=0.2, metal=0.9, coat=0.6)
    dark = mat("Joint", "2c2e35", rough=0.35, metal=0.6, coat=0.4)
    glow = mat("ArcReactor", "e8fdff", rough=0.1, coat=0.5, emit="8eeaff", emit_strength=9)
    eyeg = mat("EyeGlow", "f4feff", rough=0.1, coat=0.5, emit="c6f6ff", emit_strength=8)
    steel = mat("Steel", "aab3be", rough=0.2, metal=1.0, coat=0.2)

    P = figure(dict(chest=red, waist=gold, pelvis=red, shoulder=red, upper=gold, fore=red, cuff=red, glove=red,
                    thigh=red, shin=gold, boot=red, sole=dark, boot_rim=gold),
               dict(pecs=0.018, arm_r=0.042, fore_r=0.046, fist=(0.053, 0.055, 0.058), thigh_r=0.066, shin_r=0.056,
                    delt=(0.06, 0.058, 0.058)))
    C, W = P["C"], P["W"]
    hc = Vector(P["head_c"])
    H = S(hc, (0.172, 0.172, 0.196), taper=0.3, jaw=0.05)
    with limb("Head"):
        neck(P, dark, 0.05)
        H.mesh("Head", red, seg=30, ring=18)
        F = (0, -1, 0)
        plate = [(0.0, 0.5), (0.22, 0.48), (0.5, 0.42), (0.62, 0.15), (0.6, -0.25), (0.5, -0.5), (0.3, -0.72), (0.0, -0.8),
                 (-0.3, -0.72), (-0.5, -0.5), (-0.6, -0.25), (-0.62, 0.15), (-0.5, 0.42), (-0.22, 0.48)]
        patch("Head_Faceplate", H, F, plate[::-1], gold, thick=0.007, rings=4, sub=3)
        Hf = S(hc, (0.172 + 0.007, 0.172 + 0.007, 0.196 + 0.007), taper=0.3, jaw=0.05)
        for s, side in sides():
            slit = [(0.1, 0.13), (0.27, 0.15), (0.44, 0.19), (0.47, 0.13), (0.3, 0.075), (0.13, 0.06)]
            o = [(s * u, v) for u, v in slit]
            patch(f"Eye_{side}_Glow", Hf, F, o if s > 0 else o[::-1], eyeg, thick=0.004, rings=2, closed_smooth=False)
            # cheek seams down from the eyes, ear discs
            ridge(f"Head_Seam_{side}", Hf, [uvdir(F, s * 0.47, 0.1), uvdir(F, s * 0.5, -0.2), uvdir(F, s * 0.38, -0.5)], dark,
                  w=0.006, h=0.002, lean=False)
            p, n = H.at((s, 0.05, -0.05))
            cyl(f"Head_Ear_{side}", p, 0.05, 0.016, gold, rot=aim(n), seg=18)
            cyl(f"Head_Ear_{side}_In", p + n * 0.008, 0.032, 0.01, dark, rot=aim(n), seg=14)
        ridge("Head_Mouth", Hf, [uvdir(F, -0.17, -0.5), uvdir(F, 0, -0.52), uvdir(F, 0.17, -0.5)], dark, w=0.007, h=0.002, lean=False)
        ridge("Head_Crest", H, [uvdir(F, 0, 0.5), uvdir(F, 0, 1.2), uvdir(F, 0, 2.0), uvdir(F, 0, 2.6)], gold, w=0.035, h=0.004, flat=True)

    with limb("Body"):
        # arc reactor: gold bezel, dark ring, glowing core
        rp, rn = C.at((0, -1, 0.28))
        cyl("Reactor_Bezel", rp - rn * 0.004, 0.058, 0.026, gold, rot=aim(rn), seg=24)
        cyl("Reactor_Ring", rp + rn * 0.008, 0.045, 0.012, dark, rot=aim(rn), seg=24)
        cyl("Reactor_Core", rp + rn * 0.012, 0.034, 0.01, glow, rot=aim(rn), seg=24)
        for k in range(8):
            a = k * math.pi / 4
            q = aim(rn)
            box(f"Reactor_Rib{k}", rp + rn * 0.017 + q @ Vector((math.cos(a) * 0.026, math.sin(a) * 0.026, 0)),
                (0.006, 0.014, 0.004), white, bevel=0.002, rot=q @ Quaternion((0, 0, 1), a))
        # gold collar + pec plate seams
        shell("Chest_Collar", None, None, gold, [((0, 0, 0.82), (0, 0, 1))], inflate=0.006, srf=C, seg=28, ring=16)
        for s in (-1, 1):
            ridge(f"Chest_Seam{s}", C, [(s * 0.22, -1, 0.05), (s * 0.5, -1, 0.0), (s * 0.85, -0.6, 0.15)], dark, w=0.006, h=0.002, lean=False)
            ridge(f"Chest_SeamU{s}", C, [(s * 0.2, -1, 0.55), (s * 0.45, -0.9, 0.7)], dark, w=0.006, h=0.002, lean=False)
            # red side armour over the gold abs
            shell(f"Waist_Side{s}", None, None, red, [((s * 0.5, 0, 0), (s, 0, 0))], inflate=0.007, srf=W)
        for k, z in enumerate((0.45, -0.05)):
            ridge(f"Waist_Ab{k}", W, [(-0.42, -1, z), (0, -1, z - 0.06), (0.42, -1, z)], dark, w=0.006, h=0.002, lean=False)
        ridge("Waist_AbV", W, [(0, -1, 0.85), (0, -1, -0.6)], dark, w=0.006, h=0.002, lean=False)
        torus("Belt", (0, 0.008, 0.398), 0.142, 0.012, gold, scale=(1, 0.8, 1))
        for s in (-1, 1):
            p, n = C.at((0, 1, 0.3))
            box(f"Back_Vent{s}", p + n * 0.004 + V(s * 0.06, 0, 0), (0.05, 0.012, 0.11), dark, bevel=0.006)
    for s, side in sides():
        with limb("Arm" + side):
            fc, fr = P["fist_c"][side], P["fist"]
            G = S(fc, fr)
            p, n = G.at((-s, -0.15, -0.1))
            cyl(f"Hand_{side}_Repulsor", p - n * 0.002, 0.021, 0.01, glow, rot=aim(n), seg=14)
            Sh = S(P["shoulder"][side], P["delt"])
            ridge(f"Shoulder_{side}_Trim", Sh, [(s * 0.2, -1, -0.35), (s * 1, -0.2, -0.3), (s * 0.2, 1, -0.35)], gold, w=0.012, h=0.003,
                  flat=True)
            el, wr = P["elbow"][side], P["wrist"][side]
            sph(f"Arm_{side}_ElbowCap", el + V(0, 0.01, 0), (P["arm_r"] * 1.02,) * 3, dark)
        with limb("Leg" + side):
            kn = P["knee"][side]
            sph(f"Leg_{side}_KneeCap", kn + V(0, -0.012, 0), (0.05, 0.04, 0.05), red)
            p, n = S(P["foot"][side], (0.064, 0.1, 0.054)).at((0, -1, 0.5))
            sph(f"Foot_{side}_Toe", p - n * 0.01, (0.05, 0.03, 0.03), gold, rot=facing(n))
    return dict(P=P, backdrop="e9e2dc", target=(0, 0, 0.55), dist=2.35)


# ====================================================================== 3. Captain America
def captain_america():
    reset("CaptainAmerica")
    black, white = common_mats()
    blue = mat("CapBlue", "2a4fae", rough=0.38, coat=0.6)
    navy = mat("CapNavy", "1e2f66", rough=0.4, coat=0.5)
    wht = mat("CapWhite", "f3f4f7", rough=0.3, coat=0.7)
    red = mat("CapRed", "cc2434", rough=0.32, coat=0.7)
    leather = mat("Leather", "6a4126", rough=0.4, coat=0.5)
    skin = mat("Skin", "eab38e", rough=0.45, coat=0.25, sss=0.12)
    mouth = mat("Mouth", "6a2a20", rough=0.4)
    sole = mat("Sole", "2a1f1b", rough=0.6, coat=0.1)
    silver = mat("Silver", "c9ced6", rough=0.2, metal=1.0, coat=0.3)
    sh_red = mat("ShieldRed", "c8202f", rough=0.18, metal=0.55, coat=1.0)
    sh_wht = mat("ShieldWhite", "e8eaee", rough=0.15, metal=0.6, coat=1.0)
    sh_blu = mat("ShieldBlue", "1f3f96", rough=0.18, metal=0.55, coat=1.0)

    P = figure(dict(chest=blue, waist=red, pelvis=blue, shoulder=blue, upper=blue, fore=blue, cuff=red, glove=red,
                    thigh=blue, shin=blue, boot=red, sole=sole, boot_rim=red),
               dict(pecs=0.018, boot_top=0.16))
    C, W = P["C"], P["W"]
    hc = Vector(P["head_c"])
    hr = Vector((0.174, 0.168, 0.19))
    H = S(hc, hr, taper=0.1, jaw=0.12)
    with limb("Head"):
        neck(P, skin, 0.052)
        H.mesh("Head", skin, seg=28, ring=16)
        brow = mat("Brow", "5a3a22", rough=0.5)
        face(H, black, white, skin, brow, mouth, ex=0.33, ez=-0.05, ew=0.028, eh=0.037, brow_z=0.235, angry=0.045, mouth="smirk",
             mz=-0.47, do_ears=False)
        p, n = H.at((0, -0.75, -0.95))
        sph("Chin", p - n * 0.01, (0.05, 0.03, 0.03), skin)
        # helmet: covers the crown, comes down over the ears; the front edge is a heroic brow line
        HS = S(hc, hr + Vector((0.012, 0.012, 0.012)), taper=0.1, jaw=0.12)
        shell("Helmet", None, None, blue, [((0, 0, -0.45), (0, 0.85, 1)), ((0, 0, -0.62), (0, 0, 1))], inflate=0.0, srf=HS,
              seg=30, ring=18)
        F = (0, -1, 0)
        # white A on the forehead
        for k, (a, b) in enumerate((((-0.16, 0.27), (0.0, 0.72)), ((0.16, 0.27), (0.0, 0.72)), ((-0.09, 0.43), (0.09, 0.43)))):
            ridge(f"Helmet_A{k}", HS, [uvdir(F, *a), uvdir(F, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2), uvdir(F, *b)], wht,
                  w=0.032 if k < 2 else 0.026, h=0.005, flat=True, smooth=1)
        # little white wings at the temples: three swept-back feathers
        wing = [(0.0, 0.0), (0.03, 0.022), (0.075, 0.052), (0.068, 0.03), (0.098, 0.04), (0.084, 0.012), (0.105, 0.012),
                (0.08, -0.012), (0.03, -0.018)]
        for s, side in sides():
            p, n = HS.at((s, -0.3, 0.3))
            poly_plate(f"Helmet_Wing_{side}", p + n * 0.001, n, [(s * x, y) for x, y in wing], wht, thick=0.005, up=(0, 0, 1),
                       dome=0.3)
        # chin strap edge
        for s in (-1, 1):
            ridge(f"Helmet_Edge{s}", HS, [(s * 0.55, -1, 0.42), (s * 0.95, -0.4, -0.05), (s * 0.85, 0.2, -0.55)], navy, w=0.008, h=0.002,
                  lean=False)

    with limb("Body"):
        sp, sn = C.at((0, -1, 0.3))
        poly_plate("Chest_Star", sp + sn * 0.002, sn, star_pts(0.082), wht, thick=0.006)
        # red & white stripes on the belly
        for k, (a, b) in enumerate(((-0.62, -0.38), (-0.14, 0.14), (0.38, 0.62))):
            shell(f"Waist_Stripe{k}", None, None, wht, [((a, 0, 0), (1, 0, 0)), ((b, 0, 0), (-1, 0, 0))], inflate=0.005, srf=W)
        shell("Waist_SideL", None, None, blue, [((-0.8, 0, 0), (-1, 0, 0))], inflate=0.006, srf=W)
        shell("Waist_SideR", None, None, blue, [((0.8, 0, 0), (1, 0, 0))], inflate=0.006, srf=W)
        torus("Belt", (0, 0.008, 0.39), 0.14, 0.017, leather, scale=(1, 0.8, 1))
        bp, bn = P["Pv"].at((0, -1, 0.42))
        box("Belt_Buckle", bp + bn * 0.012, (0.05, 0.016, 0.034), silver, bevel=0.006, rot=facing(bn))
        for s in (-1, 1):
            p, n = P["Pv"].at((s * 0.6, -0.8, 0.42))
            box(f"Belt_Pouch{s}", p + n * 0.016, (0.036, 0.026, 0.04), leather, bevel=0.008, rot=facing(n))
        # the shield, slung on the back
        sc = Vector((0, 0.188, 0.53))
        q = Quaternion((1, 0, 0), -math.pi / 2)
        n = Vector((0, 1, 0))
        cyl("Shield_Rim", sc, 0.185, 0.022, sh_red, rot=q, seg=36, bevel=0.008)
        cyl("Shield_W1", sc + n * 0.006, 0.146, 0.022, sh_wht, rot=q, seg=32, bevel=0.004)
        cyl("Shield_R2", sc + n * 0.012, 0.108, 0.022, sh_red, rot=q, seg=32, bevel=0.004)
        cyl("Shield_Blue", sc + n * 0.018, 0.071, 0.022, sh_blu, rot=q, seg=28, bevel=0.004)
        poly_plate("Shield_Star", sc + n * 0.029, n, star_pts(0.066), sh_wht, thick=0.004, dome=0.6)
        box("Shield_Strap", (0, 0.15, 0.53), (0.16, 0.03, 0.03), leather, bevel=0.008)
    for s, side in sides():
        with limb("Arm" + side):
            pass
        with limb("Leg" + side):
            pass
    return dict(P=P, backdrop="dfe4ee", target=(0, 0, 0.55), dist=2.35)


# ====================================================================== 4. Thor
def thor():
    reset("Thor")
    black, white = common_mats()
    armour = mat("ThorArmour", "2a2f3d", rough=0.32, metal=0.45, coat=0.8)
    plate = mat("ThorPlate", "3b4254", rough=0.3, metal=0.5, coat=0.8)
    silver = mat("Silver", "d3d8e0", rough=0.16, metal=1.0, coat=0.4)
    cape_m = mat("Cape", "b51d26", rough=0.5, coat=0.3)
    cape_in = mat("CapeInner", "8e141c", rough=0.55, coat=0.2)
    hair = mat("Hair", "e3b04c", rough=0.45, coat=0.25)
    beard = mat("Beard", "c8923a", rough=0.5, coat=0.15)
    skin = mat("Skin", "eab38e", rough=0.45, coat=0.25, sss=0.12)
    mouth = mat("Mouth", "6a2a20", rough=0.4)
    boot = mat("Boot", "2f323b", rough=0.35, metal=0.3, coat=0.6)
    sole = mat("Sole", "1c1c20", rough=0.6, coat=0.1)
    pants = mat("Leggings", "23252d", rough=0.5, coat=0.3)

    P = figure(dict(chest=armour, waist=armour, pelvis=pants, shoulder=plate, upper=skin, fore=silver, cuff=silver, glove=skin,
                    thigh=pants, shin=pants, boot=boot, sole=sole, boot_rim=silver),
               dict(pecs=0.02, lats=0.018, sx=0.22, chest_r=(0.206, 0.14, 0.156), arm_r=0.043, fore_r=0.044,
                    delt=(0.062, 0.06, 0.062), boot_top=0.17))
    C, W = P["C"], P["W"]
    hc = Vector(P["head_c"])
    hr = Vector((0.172, 0.165, 0.185))
    H = S(hc, hr, taper=0.15, jaw=0.06)
    with limb("Head"):
        neck(P, skin, 0.054)
        H.mesh("Head", skin, seg=28, ring=16)
        face(H, black, white, skin, beard, mouth, ex=0.33, ez=0.0, ew=0.028, eh=0.038, brow_z=0.25, angry=0.05, mouth=None,
             mz=-0.42, do_ears=False)
        # golden hair: one mesh - parted crown, flowing down the back to the shoulders
        hair_bumps = [((0, 0.55, -1), 0.13, 0.5, (0, 0.02, -0.05)), ((-0.75, 0.35, -0.8), 0.07, 0.38, (-0.01, 0.01, -0.04)),
                      ((0.75, 0.35, -0.8), 0.07, 0.38, (0.01, 0.01, -0.04)), ((-0.5, -0.2, 0.85), 0.018, 0.3),
                      ((0.5, -0.2, 0.85), 0.018, 0.3), ((0, 0.3, 1), 0.012, 0.4), ((-0.95, 0.0, 0.1), 0.02, 0.4),
                      ((0.95, 0.0, 0.1), 0.02, 0.4)]
        blob("Hair", hc + Vector((0, 0.014, 0.008)), hr + Vector((0.016, 0.02, 0.016)), hair, hair_bumps, seg=32, ring=18,
             keep=lambda d: d.z > 0.42 - 0.8 * (1 + d.y) + 0.1 * abs(d.x))
        ridge("Hair_Part", S(hc + Vector((0, 0.014, 0.008)), hr + Vector((0.016, 0.02, 0.016)), [((-0.5, -0.2, 0.85), 0.018, 0.3),
              ((0.5, -0.2, 0.85), 0.018, 0.3), ((0, 0.3, 1), 0.012, 0.4)]), [(0.12, -0.5, 0.85), (0.1, 0, 1), (0.08, 0.6, 0.8)],
              beard, w=0.006, h=0.0005, sink=0.004, lean=False)
        # short full beard over the jaw, up the cheeks into sideburns; moustache on top
        hb = S(hc, hr + Vector((0.008, 0.01, 0.008)), taper=0.15, jaw=0.06,
               bumps=[((0, -0.55, -1), 0.026, 0.42), ((-0.6, -0.6, -0.7), 0.01, 0.35), ((0.6, -0.6, -0.7), 0.01, 0.35)])
        shell("Beard", None, None, beard, [((0, 0, -0.06), (0, 0.4, -1)), ((0, 0.3, 0), (0, -1, 0))], inflate=0.0, srf=hb, seg=30, ring=18)
        for s, side in sides():
            p, n = H.at((s * 0.1, -1, -0.31))
            sph(f"Beard_Stache_{side}", p + n * 0.01, (0.052, 0.016, 0.017), beard, rot=facing(n) @ Quaternion((0, 1, 0), s * 0.3))
        p, n = hb.at((0, -1, -0.43))
        sph("Mouth_Lip", p + n * 0.002, (0.04, 0.008, 0.012), mouth, rot=facing(n))

    with limb("Body"):
        # six silver discs on the breastplate
        for row, z in enumerate((0.55, 0.15, -0.25)):
            for s in (-1, 1):
                p, n = C.at((s * 0.36, -1, z))
                cyl(f"Disc_{row}{s}", p + n * 0.002, 0.034, 0.016, silver, rot=aim(n), seg=18, bevel=0.005)
                sph(f"Disc_{row}{s}_Dome", p + n * 0.01, (0.024, 0.024, 0.008), silver, rot=aim(n), seg=12, ring=5)
        ridge("Chest_Seam", C, [(0, -1, 0.85), (0, -1, -0.8)], plate, w=0.016, h=0.003, flat=True)
        # scale-mail belly, silver belt
        for k, z in enumerate((0.5, 0.05, -0.4)):
            ridge(f"Waist_Band{k}", W, [(x, -1, z) for x in (-0.95, -0.5, 0, 0.5, 0.95)], plate, w=0.014, h=0.003, flat=True)
        torus("Belt", (0, 0.008, 0.395), 0.142, 0.017, silver, scale=(1, 0.8, 1))
        bp, bn = P["Pv"].at((0, -1, 0.4))
        cyl("Belt_Buckle", bp + bn * 0.012, 0.025, 0.014, silver, rot=aim(bn), seg=16)
        # cape clasps (two big silver discs at the collar), the high cape collar
        for s in (-1, 1):
            p, n = C.at((s * 0.62, -0.55, 0.82))
            cyl(f"Clasp{s}", p + n * 0.006, 0.036, 0.016, silver, rot=aim(n), seg=18, bevel=0.005)
            sph(f"Clasp{s}_Dome", p + n * 0.015, (0.025, 0.025, 0.01), silver, rot=aim(n), seg=12, ring=5)
        torus("Collar", (0, 0.01, 0.69), 0.1, 0.02, armour, scale=(1, 0.85, 1))
    with limb("Cape"):
        g = cape_grid(0.672, 0.085, 0.19, 0.29, 0.118, lambda v: 0.055 * min(1, v * 3.2) + 0.06 * v, folds=3, fold_amp=0.014,
                      wrap=0.07, hem=0.025)
        sheet("Cape", g, cape_m, thick=0.014)
        g2 = [[p + Vector((0, -0.006, 0)) for p in row] for row in g[:2]]
    for s, side in sides():
        with limb("Arm" + side):
            el, wr = P["elbow"][side], P["wrist"][side]
            for k, t in enumerate((0.15, 0.85)):
                torus(f"Arm_{side}_Bracer{k}", el + (wr - el) * t, P["fore_r"] * 1.05, 0.008, plate,
                      rot=Euler((0, 0, 0)).to_quaternion() @ aim(wr - el), seg=16)
            sh = P["shoulder"][side]
            Sh = S(sh, P["delt"])
            for k in range(3):
                ridge(f"Shoulder_{side}_Plate{k}", Sh, [(s * 0.2, -1, 0.1 - 0.35 * k), (s, 0, 0.2 - 0.35 * k), (s * 0.2, 1, 0.1 - 0.35 * k)],
                      silver if k == 0 else plate, w=0.012, h=0.004, flat=True, lean=False)
        with limb("Leg" + side):
            pass
    pv = dict(P["pivots"])
    pv["Cape"] = (0, 0.118, 0.672)
    return dict(P=P, pivots=pv, backdrop="dfe2ea", target=(0, 0, 0.55), dist=2.35)


# ====================================================================== runner
CHARS = {"spider_man": spider_man, "iron_man": iron_man, "captain_america": captain_america, "thor": thor}


def export_hero(hid, pivots):
    """npc_kit.export, but written to hero_<id>.glb."""
    groups = {}
    for o in mesh_objs():
        groups.setdefault(o["limb"], []).append(o)
    missing = set(groups) - set(pivots)
    assert not missing, f"no pivot for {missing}"
    exported = []
    for g, members in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for o in members:
            o.select_set(True)
        bpy.context.view_layer.objects.active = members[0]
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        if len(members) > 1:
            bpy.ops.object.join()
        ob = bpy.context.view_layer.objects.active
        ob.name = g
        ob.data.name = g
        bpy.context.scene.cursor.location = Vector(pivots[g])
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        exported.append(ob)
    bpy.ops.object.select_all(action="DESELECT")
    for o in exported:
        o.select_set(True)
    out = os.path.join(ROOT, "assets", "characters", f"hero_{hid}.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True)
    print("EXPORTED", out)
    for g in sorted(pivots):
        if g in groups:
            p = Vector(pivots[g])
            print(f"  NODE {g:9s} blender=({p.x:+.3f},{p.y:+.3f},{p.z:+.3f})  godot=({p.x:+.3f},{p.z:+.3f},{-p.y:+.3f})")
    return out


def portrait_cam(opts):
    P = opts["P"]
    hc = Vector(P["head_c"])
    t = opts.get("portrait_target", (0, 0, hc.z - 0.1))
    cam_at(t, opts.get("portrait_dist", 1.15), opts.get("portrait_yaw", 22), opts.get("portrait_pitch", 6), lens=60)


def build(hid, budget=7000):
    fast = "--fast" in sys.argv
    preview = "--preview" in sys.argv
    concept = os.path.join(ROOT, "concepts", f"hero_{hid}.png")
    portrait = os.path.join(ROOT, "assets", "portraits", f"hero_{hid}.png")
    if preview:
        npc_kit.DETAIL[0] = 1.0
        opts = CHARS[hid]()
        finalize()
        print(f"PREVIEW TRIS {hid} full={sum(tri_report().values())}")
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        views = []
        for k, (yaw, pitch) in enumerate([(0, 6), (32, 12), (150, 12)]):
            cam_at(opts["target"], opts["dist"], yaw, pitch)
            pth = os.path.join(SCRATCH, f"{hid}_p{k}.png")
            render(pth, 560, samples=16)
            views.append(pth)
        portrait_cam(opts)
        pth = os.path.join(SCRATCH, f"{hid}_pp.png")
        render(pth, 560, samples=16)
        views.append(pth)
        contact_sheet(views, os.path.join(SCRATCH, f"{hid}_sheet.png"), cols=2, cell=560)
        return
    if not fast:
        npc_kit.DETAIL[0] = 1.0
        opts = CHARS[hid]()
        finalize()
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        cam_at(opts["target"], opts["dist"], opts.get("yaw", 32), opts.get("pitch", 12))
        render(concept, 1024, samples=96)
        portrait_cam(opts)
        tmp = os.path.join(SCRATCH or os.path.dirname(concept), f"_portrait_{hid}.png")
        render(tmp, 640, samples=64)
        downscale(tmp, portrait, 320)
        if not SCRATCH:
            os.remove(tmp)
    npc_kit.DETAIL[0] = 1.0
    for attempt in range(8):
        opts = CHARS[hid]()
        finalize()
        total = sum(tri_report().values())
        b = opts.get("budget", budget)
        print(f"BUDGET {hid} detail={npc_kit.DETAIL[0]:.2f} tris={total}")
        if total <= b:
            break
        if npc_kit.DETAIL[0] <= 0.45:
            print(f"WARNING {hid} over budget at the detail floor")
            break
        npc_kit.DETAIL[0] = max(0.45, npc_kit.DETAIL[0] * max(0.72, (b / total) ** 0.9 * 0.97))
    bake_transforms()
    tris = tri_report()
    lo, hi = height()
    mn, mx = extents()
    print(f"TRIS {hid} total={sum(tris.values())} per={tris}")
    print(f"SIZE {hid} height={hi - lo:.3f} (z {lo:.3f}..{hi:.3f}) x {mn.x:.3f}..{mx.x:.3f} y {mn.y:.3f}..{mx.y:.3f}")
    if SCRATCH:
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        cam_at(opts["target"], opts["dist"] * 0.8, 32, 14)
        render(os.path.join(SCRATCH, f"{hid}_game.png"), 700, samples=32)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "art", "characters", f"hero_{hid}.blend"), compress=True)
    export_hero(hid, opts["P"]["pivots"] if "pivots" not in opts else opts["pivots"])


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = [a for a in args if not a.startswith("--")]
    if names == ["all"]:
        names = list(CHARS)
    for n in names:
        build(n)
