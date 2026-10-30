# Playable hero figures (set B): stylised toy-real Marvel heroes built from primitives.
# Run one:  blender --background --python art/src/heroes_b.py -- captain_marvel
# Run all:  blender --background --python art/src/heroes_b.py -- all
# Each run writes art/characters/hero_<id>.blend (parts, pre-join), concepts/hero_<id>.png,
# assets/portraits/hero_<id>.png (320px head-and-shoulders) and assets/characters/hero_<id>.glb.
#
# Conventions (same as the npc figures; see npc_kit.py / player.gd):
# - Blender: faces -Y, feet on z=0, L = -X. After glTF import Godot sees them facing +Z.
# - Same units as kid.glb (the kid is ~0.97 tall; the game scales by 0.55). Heroes are ~1.05-1.1.
# - Nodes Body, Head, ArmL, ArmR, LegL, LegR (+ optional Cape, WingL, WingR): one node each,
#   origin at its joint, identity rotation/scale (transforms baked).
# - ArmR ends in an (empty) hand at its lowest point: the game hangs held items there.
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
import npc_kit
importlib.reload(npc_kit)
from npc_kit import *
from npc_kit import _d
from mathutils import Vector, Quaternion, Euler

SCRATCH = os.environ.get("HERO_SCRATCH", "")
Y90 = Quaternion((0, 1, 0), math.pi / 2)


def sides():
    return ((-1, "L"), (1, "R"))


# ====================================================================== shared hero anatomy
# Heroic toy proportions: a big friendly head on a V-shaped torso.
HC, HR = Vector((0, 0, 0.875)), (0.205, 0.19, 0.198)        # head
SH = Vector((0.195, 0, 0.625))                               # right shoulder joint
HIP = Vector((0.085, 0, 0.335))                              # right hip joint
HEAD_PIVOT = (0, 0, HC.z - HR[2] + 0.05)


def pivots(**extra):
    p = {"Body": (0, 0, 0), "Head": HEAD_PIVOT,
         "ArmL": (-SH.x, SH.y, SH.z), "ArmR": (SH.x, SH.y, SH.z),
         "LegL": (-HIP.x, HIP.y, HIP.z), "LegR": (HIP.x, HIP.y, HIP.z)}
    p.update(extra)
    return p


def glass(name, color, alpha=0.35, emit=None, emit_strength=1.0, rough=0.05):
    m = mat(name, color, rough=rough, coat=1.0, emit=emit, emit_strength=emit_strength)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Alpha"].default_value = alpha
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    try:
        m.use_backface_culling = False
    except Exception:
        pass
    return m


def prism(name, pts, depth, m, loc, rot=None, bevel=0.003):
    """Extruded 2D outline (local XY), thickness along local Z, centred; rot aims it (aim(n))."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, -depth / 2)) for x, y in pts]
    hi = [bm.verts.new((x, y, depth / 2)) for x, y in pts]
    n = len(pts)
    bm.faces.new(list(reversed(lo)))
    bm.faces.new(hi)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=min(bevel, depth * 0.45), segments=1, profile=0.5,
                        affect="EDGES", clamp_overlap=True)
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m, loc)
    for e in me.edges:
        e.use_edge_sharp = False
    if rot is not None:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = rot
    # crisp silhouette, soft bevel: auto-smooth by angle
    try:
        o.data.set_sharp_from_angle(angle=math.radians(40))
    except Exception:
        pass
    return o


def star_pts(n, r_out, r_in, rot=0.0):
    return [((r_out if i % 2 == 0 else r_in) * math.cos(math.pi / 2 + rot + i * math.pi / n),
             (r_out if i % 2 == 0 else r_in) * math.sin(math.pi / 2 + rot + i * math.pi / n)) for i in range(2 * n)]


def sheet(name, f, nu, nv, thick, m, closed_u=False):
    """Parametric cloth sheet f(u, v) -> point (u, v in 0..1), solidified (applied at finalize)."""
    nu, nv = max(3, _d(nu, 4)), max(3, _d(nv, 3))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cols = nu if closed_u else nu + 1
    grid = [[bm.verts.new(f(i / nu, j / nv)) for i in range(cols)] for j in range(nv + 1)]
    for j in range(nv):
        for i in range(nu if closed_u else nu):
            i2 = (i + 1) % cols
            bm.faces.new((grid[j][i], grid[j][i2], grid[j + 1][i2], grid[j + 1][i]))
    bm.to_mesh(me)
    bm.free()
    o = toykit._obj(name, me, m)
    mod = o.modifiers.new("Solid", "SOLIDIFY")
    mod.thickness = thick
    mod.offset = 0.0
    mod.use_even_offset = True
    return o


def clip(bm, g):
    """Trim a bmesh to g(co) >= 0 along the exact zero contour (edges split, faces cut), so costume
    panels get clean, smooth borders instead of a stair-step of deleted vertices."""
    vals = {v: g(v.co) for v in bm.verts}
    new = set()
    for e in list(bm.edges):
        a, b = e.verts
        ga, gb = vals[a], vals[b]
        if (ga >= 0) != (gb >= 0):
            t = ga / (ga - gb)
            if t <= 1e-4 or t >= 1 - 1e-4:
                continue
            _, nv = bmesh.utils.edge_split(e, a, t)
            vals[nv] = 0.0
            new.add(nv)
    for f in list(bm.faces):
        vs = [v for v in f.verts if v in new]
        if len(vs) == 2:
            try:
                bmesh.utils.face_split(f, vs[0], vs[1])
            except Exception:
                pass
        elif len(vs) == 4:
            try:
                f2, _ = bmesh.utils.face_split(f, vs[0], vs[1])
            except Exception:
                pass
    dead = [v for v in bm.verts if vals.get(v, 0.0) < -1e-9]
    bmesh.ops.delete(bm, geom=dead, context="VERTS")


def head_shell(name, m, g, center=None, radii=None, seg=32, ring=16, hero=False):
    """A shell over an ellipsoid (the head by default) trimmed by g(unit_direction) >= 0."""
    c = Vector(center if center is not None else HC)
    r = radii or HR
    seg, ring = _d(seg, 20, hero), _d(ring, 10, hero, even=False)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=1.0)
    clip(bm, lambda co: g(co.normalized()))
    for v in bm.verts:
        v.co = Vector((v.co.x * r[0], v.co.y * r[1], v.co.z * r[2]))
    bm.to_mesh(me)
    bm.free()
    return toykit._obj(name, me, m, c)


# Torso profile: (z, half-width, half-depth, forward shift). A lathe with a V taper: broad chest,
# nipped waist, hips; capped at the crotch and the neck.
TORSO = [(0.282, 0.0, 0.0, 0.0), (0.298, 0.095, 0.08, 0.0), (0.33, 0.138, 0.106, 0.0), (0.37, 0.15, 0.114, 0.0),
         (0.42, 0.136, 0.104, -0.004), (0.475, 0.146, 0.108, -0.008), (0.535, 0.168, 0.118, -0.012),
         (0.59, 0.18, 0.122, -0.01), (0.632, 0.172, 0.114, -0.004), (0.668, 0.142, 0.094, 0.0),
         (0.693, 0.085, 0.062, 0.0), (0.705, 0.0, 0.0, 0.0)]


def _profile(prof, n):
    """Catmull-Rom resample of the profile into n rings (poles kept)."""
    pts = [Vector(p) for p in prof]
    out = [pts[0]]
    inner = pts[1:-1]
    m = len(inner)
    for k in range(n):
        t = k / (n - 1) * (m - 1)
        i = min(int(t), m - 2)
        f = t - i
        p0, p1, p2, p3 = inner[max(i - 1, 0)], inner[i], inner[i + 1], inner[min(i + 2, m - 1)]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f +
                          (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f))
    out.append(pts[-1])
    return out


def lathe(name, m, prof=None, grow=0.0, keep=None, seg=28, rings=18, power=2.3, hero=True):
    """Elliptic (slightly squared) lathe through a (z, rx, ry, dy) profile. keep(c, s, z) trims a costume panel."""
    prof = prof or TORSO
    seg = _d(seg, 16, hero)
    rings = _d(rings, 10, hero, even=False)
    rs = _profile(prof, rings)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    e = 2.0 / power
    grid = []
    for r in rs[1:-1]:
        row = []
        for i in range(seg):
            t = 2 * math.pi * i / seg
            c, s_ = math.cos(t), math.sin(t)
            x = (r.y + grow) * math.copysign(abs(c) ** e, c)
            y = (r.z + grow) * math.copysign(abs(s_) ** e, s_) + r[3]
            row.append(bm.verts.new((x, y, r.x)))
        grid.append(row)
    bot = bm.verts.new((0, rs[0][3], rs[0].x - grow))
    top = bm.verts.new((0, rs[-1][3], rs[-1].x + grow))
    for j in range(len(grid) - 1):
        for i in range(seg):
            i2 = (i + 1) % seg
            bm.faces.new((grid[j][i], grid[j][i2], grid[j + 1][i2], grid[j + 1][i]))
    for i in range(seg):
        i2 = (i + 1) % seg
        bm.faces.new((grid[0][i2], grid[0][i], bot))
        bm.faces.new((grid[-1][i], grid[-1][i2], top))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if keep is not None:  # keep(c, s, z) -> signed: >= 0 keeps (c, s = cos/sin of the angle round the body)
        def g(co):
            a = math.atan2(co.y, co.x)
            return keep(math.cos(a), math.sin(a), co.z)
        clip(bm, g)
    bm.to_mesh(me)
    bm.free()
    return toykit._obj(name, me, m)


def prof_scale(sx=1.0, sy=1.0, prof=None, chest=1.0):
    """A wider/deeper torso profile (chest > 1 broadens only the upper half)."""
    out = []
    for z, rx, ry, dy in (prof or TORSO):
        k = chest if z > 0.5 else 1.0
        out.append((z, rx * sx * k, ry * sy, dy))
    return out


def orient(ydir, znorm):
    """Rotation whose local +Y runs along ydir and local +Z faces znorm (orthogonalised)."""
    from mathutils import Matrix
    y = Vector(ydir).normalized()
    z = Vector(znorm)
    z = (z - y * z.dot(y)).normalized()
    x = y.cross(z)
    return Matrix((x, y, z)).transposed().to_quaternion()


def torso_at(z, prof=None):
    """(half-width, half-depth, forward shift) of the torso profile at height z."""
    rs = _profile(prof or TORSO, 40)
    best = min(rs[1:-1], key=lambda r: abs(r.x - z))
    return best.y, best.z, best[3]


def panel(name, m, keep, grow=0.005, prof=None):
    """Costume panel hugging the torso; keep(c, s, z) is signed (>= 0 keeps)."""
    return lathe(name, m, prof, grow=grow, keep=keep, hero=True)


def band(name, z, m, minor=0.014, grow=0.004, prof=None):
    rx, ry, dy = torso_at(z, prof)
    return torus(name, (0, dy, z), rx + grow, minor, m, scale=(1, (ry + grow) / (rx + grow), 1), seg=26)


def body_core(suit, lower=None, neck_m=None, prof=None):
    lathe("Torso", suit, prof)
    if lower:
        panel("Pants", lower, lambda c, s, z: 0.385 - 0.02 * max(0.0, -s) - z, prof=prof)
    cyl("Neck", (0, 0.005, 0.705), 0.05, 0.08, neck_m or suit, seg=14, bevel=0.0)


def arm(s, side, upper, fore=None, hand=None, cuff=None, shoulder=None, glove=True, thick=1.0):
    """Shoulder ball, a gently bent arm tube, a fist at the bottom. Returns the hand centre."""
    fore = fore or upper
    hand = hand or fore
    x = s
    sp = Vector((x * SH.x, SH.y, SH.z))
    sph(f"Shoulder_{side}", sp + Vector((x * 0.005, 0, 0.0)), (0.057 * thick, 0.056 * thick, 0.056 * thick),
        shoulder or upper, seg=16, ring=8)
    elbow = Vector((x * 0.228, -0.006, 0.505))
    wrist = Vector((x * 0.243, -0.03, 0.428))
    tube(f"Arm_{side}", [sp + Vector((x * 0.008, 0, -0.02)), elbow], upper, r=0.042 * thick, radii=[1.05, 0.92],
         caps=False, br=2)
    tube(f"Arm_{side}_Fore", [elbow + Vector((0, 0, 0.012)), wrist], fore, r=0.04 * thick, radii=[0.98, 0.86],
         caps=False, br=2)
    sph(f"Arm_{side}_Elbow", elbow, (0.039 * thick,) * 3, upper if fore is upper else fore, seg=12, ring=6)
    hc = Vector((x * 0.247, -0.036, 0.392))
    sph(f"Hand_{side}", hc, (0.047, 0.045, 0.05), hand, seg=16, ring=8)
    sph(f"Hand_{side}_Thumb", hc + Vector((-x * 0.026, -0.03, 0.012)), (0.019, 0.017, 0.026), hand, seg=10, ring=5,
        rot=Quaternion((0, 1, 0), x * 0.4))
    if cuff:
        cyl(f"Arm_{side}_Cuff", wrist + Vector((0, -0.002, 0.004)), 0.045 * thick, 0.03, cuff, r2=0.042 * thick,
            seg=14, rot=aim(wrist - elbow))
    return hc, elbow, wrist


def leg(s, side, m, boot, sole=None, boot_top=0.2, cuff=None, thick=1.0, knee=None):
    x = s
    hp = Vector((x * HIP.x, 0, HIP.z))
    ank = Vector((x * 0.09, 0, 0.1))
    tube(f"Leg_{side}", [hp + Vector((0, 0, -0.005)), Vector((x * 0.089, 0, 0.21)), ank], m, r=0.058 * thick,
         radii=[1.12, 0.92, 0.82], caps=False, br=2)
    if knee:
        sph(f"Leg_{side}_Knee", (x * 0.09, -0.04, 0.2), (0.045, 0.024, 0.042), knee, seg=12, ring=6)
    # superhero boot: shaft up the shin, rounded foot, a sole
    cyl(f"Boot_{side}_Shaft", (x * 0.09, -0.002, (boot_top + 0.06) / 2), 0.054 * thick, boot_top - 0.06, boot,
        r2=0.058 * thick, seg=16, bevel=0.004)
    sph(f"Boot_{side}", (x * 0.091, -0.032, 0.058), (0.068, 0.1, 0.058), boot, seg=16, ring=8)
    sph(f"Sole_{side}", (x * 0.091, -0.032, 0.02), (0.07, 0.102, 0.02), sole or boot, seg=16, ring=4)
    if cuff:
        torus(f"Boot_{side}_Cuff", (x * 0.09, -0.002, boot_top), 0.057 * thick, 0.012, cuff, seg=16, mseg=5)


def face(skin, black, white, brow_m, mouth_m, blush=None, eye_z=-0.05, eye_w=0.033, eye_h=0.046, grin="smile",
         brow_tilt=0.0, nose=True):
    """Toy face in the npc style: glossy black eyes with shines, brows, a little mouth."""
    for s, side in sides():
        eye(f"Eye_{side}", HC, HR, (s * 0.35, -1, eye_z), eye_w, eye_h, black, white)
        b0 = 0.17 + brow_tilt
        tube(f"Brow_{side}", arc_on(HC, HR, [(s * 0.19, -1, eye_z + b0), (s * 0.34, -1, eye_z + 0.235),
                                               (s * 0.5, -1, eye_z + 0.2 - brow_tilt * 0.5)], lift=0.004),
             brow_m, r=0.0095, radii=[1.05, 1, 0.65], caps=False)
        if blush:
            decal(f"Blush_{side}", HC, HR, (s * 0.58, -1, eye_z - 0.24), (0.03, 0.007, 0.017), blush)
        sph(f"Ear_{side}", (s * 0.2, 0.012, HC.z - 0.015), (0.03, 0.026, 0.045), skin, seg=10, ring=5)
    if nose:
        p, n = on(HC, HR, (0, -1, eye_z - 0.15), 0.008)
        sph("Nose", p, (0.026, 0.022, 0.022), skin, seg=10, ring=5)
    if grin == "smile":
        tube("Smile", arc_on(HC, HR, [(-0.15, -1, -0.38), (-0.06, -1, -0.43), (0.05, -1, -0.43),
                                      (0.14, -1, -0.37)], lift=0.002), mouth_m, r=0.0075)
    elif grin == "smirk":
        tube("Smile", arc_on(HC, HR, [(-0.11, -1, -0.41), (-0.02, -1, -0.43), (0.08, -1, -0.41),
                                      (0.15, -1, -0.34)], lift=0.002), mouth_m, r=0.0075)
    elif grin == "firm":
        tube("Smile", arc_on(HC, HR, [(-0.1, -1, -0.41), (0.0, -1, -0.425), (0.1, -1, -0.41)], lift=0.002),
             mouth_m, r=0.007)


def chest(m, name, pts, z, depth, x=0.0):
    """An emblem stuck flat-ish on the front of the torso at height z."""
    rx, ry, dy = torso_at(z)
    p = Vector((x, -ry + dy - 0.002, z))
    n = Vector((0, -1, 0.18 if z > 0.55 else 0.0)).normalized()
    q = Vector((0, 0, 1)).rotation_difference(n)
    up = q @ Vector((0, 1, 0))
    want = (Vector((0, 0, 1)) - n * n.z).normalized()
    ang = math.atan2(up.cross(want).dot(n), up.dot(want))
    return prism(name, pts, depth, m, p + n * depth * 0.5, rot=aim(n, ang))


def hair_shell(name, m, edge, center=(0, 0.02, 0.0), radii=(0.226, 0.218, 0.222), bumps=(), nphi=44, nv=14,
               tuck=0.018, hero=True):
    """Hair as a polar shell whose lower edge is one clean grid row: edge(phi) -> elevation (radians) of the
    hairline at azimuth phi (0 = straight ahead, +pi/2 = the figure's right/+X, pi = the back).
    The last row tucks in toward the skull, so the edge reads as a thick rounded lip."""
    nphi = _d(nphi, 28, hero)
    nv = _d(nv, 8, hero, even=False)
    c = Vector(center) + HC
    bs = [(Vector(b[0]).normalized(), b[1], b[2], Vector(b[3]) if len(b) > 3 else Vector()) for b in bumps]
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rows = []
    for j in range(nv + 1):
        t = j / nv
        row = []
        for i in range(nphi):
            ph = 2 * math.pi * i / nphi
            e0 = edge(ph)
            el = e0 + (math.pi / 2 - e0) * (t ** 0.9) if j < nv else math.pi / 2
            d = Vector((math.cos(el) * math.sin(ph), -math.cos(el) * math.cos(ph), math.sin(el)))
            off, sweep = 0.0, Vector()
            for bd, h, w, sw in bs:
                k = math.exp(-(d.angle(bd, 0.0) / w) ** 2)
                off += h * k
                sweep += sw * k
            p = Vector((d.x * radii[0], d.y * radii[1], d.z * radii[2])) + d * off + sweep
            if j == 0:
                p = p - d * tuck
            row.append(bm.verts.new(c + p))
            if j == nv:
                break
        rows.append(row)
    for j in range(nv - 1):
        for i in range(nphi):
            i2 = (i + 1) % nphi
            bm.faces.new((rows[j][i], rows[j][i2], rows[j + 1][i2], rows[j + 1][i]))
    pole = rows[nv][0]
    for i in range(nphi):
        bm.faces.new((rows[nv - 1][i], rows[nv - 1][(i + 1) % nphi], pole))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    return toykit._obj(name, me, m)


def edge_fn(front, side, back, face_half=0.95, soft=0.28, part=0.0):
    """Hairline: `front` elevation over the face (|phi| < face_half), dropping to `side` past the cheeks and
    `back` at the nape (radians). part > 0 lifts the fringe toward +X (a side sweep)."""
    def f(ph):
        a = (ph + math.pi) % (2 * math.pi) - math.pi            # -pi..pi, 0 = front
        x = abs(a)
        k = 1 / (1 + math.exp(-(x - face_half) / (soft * 0.25)))  # 0 over the face, 1 at the sides
        fr = front + part * math.sin(a)
        sb = side + (back - side) * max(0.0, (x - math.pi / 2) / (math.pi / 2))
        return fr * (1 - k) + sb * k
    return f


def emblem_on(name, center, radii, direction, pts, depth, m, out=0.004, spin=0.0):
    p, n = on(center, radii, direction, out)
    q = aim(n, spin)
    # local Y of the prism should point "up": aim() maps +Z to n; twist so +Y ~ world up
    up = q @ Vector((0, 1, 0))
    want = (Vector((0, 0, 1)) - n * n.z).normalized()
    ang = math.atan2(up.cross(want).dot(n), up.dot(want))
    q = aim(n, spin + ang)
    return prism(name, pts, depth, m, p + n * depth * 0.5, rot=q)


def common():
    black, white = common_mats()
    return black, white


# ====================================================================== 1. Captain Marvel
def captain_marvel():
    reset("CaptainMarvel")
    black, white = common()
    skin = mat("Skin", "f1c2a0", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "f4b83a", rough=0.36, coat=0.45)
    hair2 = mat("HairShade", "d9ab4f", rough=0.45, coat=0.3)
    blue = mat("SuitBlue", "23408f", rough=0.35, coat=0.6)
    navy = mat("SuitNavy", "182a5e", rough=0.4, coat=0.5)
    red = mat("SuitRed", "d3243a", rough=0.32, coat=0.65)
    gold = mat("Gold", "f5c24a", rough=0.22, metal=0.85, coat=0.4)
    brow = mat("Brow", "b98a3c", rough=0.5)
    mouth = mat("Mouth", "a8443e", rough=0.4)
    blush = mat("Blush", "ff9c8c", rough=0.6, coat=0.0)
    glow = mat("FistGlow", "ffa41c", rough=0.25, coat=0.2, emit="ff8a00", emit_strength=3.5)
    halo = glass("FistHalo", "ffa020", alpha=0.32, emit="ff8a00", emit_strength=3.0)

    with limb("Head"):
        sph("Head", HC, HR, skin, seg=28, ring=14, hero=True)
        face(skin, black, white, brow, mouth, blush, grin="smirk", brow_tilt=0.02)
        # jaw-length blonde bob, a fringe swept across the brow from a side part
        hair_shell("Hair", hair, edge_fn(0.5, -0.62, -0.95, face_half=0.88, part=0.22),
                   bumps=[((0, 0.3, 1), 0.012, 0.6), ((-0.5, -0.8, 0.45), 0.02, 0.4, (0.01, 0, 0)),
                          ((1, 0.1, -0.6), 0.02, 0.5), ((-1, 0.1, -0.6), 0.02, 0.5), ((0, 1, -0.5), 0.022, 0.6)])
        for s, side in sides():  # ends flicking out at the jaw
            sph(f"Hair_Flick_{side}", (s * 0.2, 0.035, 0.735), (0.048, 0.08, 0.03), hair,
                rot=Quaternion((0, 1, 0), s * 0.55), seg=16, ring=8)

    with limb("Body"):
        body_core(blue, navy, blue)
        # red chest yoke over the shoulders + a red centre panel running down to the belt
        yoke = lambda c, s, z: max(z - 0.575 + 0.03 * c * c, min(0.3 - abs(c), -s, z - 0.41))
        panel("Suit_Red", red, yoke)
        # gold piping along the panel edges
        for k in (-1, 1):
            pts = []
            for z in (0.415, 0.47, 0.53):
                rx, ry, dy = torso_at(z)
                a = math.acos(0.3)
                pts.append(Vector((k * rx * 0.3 ** 0.87 + 0.0, -ry * math.sin(a) ** 0.87 - 0.006 + dy, z)))
            rx, ry, dy = torso_at(0.575)
            pts.append(Vector((k * rx * 0.62, -ry * 0.86 - 0.006 + dy, 0.578)))
            pts.append(Vector((k * rx * 1.0, -ry * 0.1 + dy, 0.555)))
            tube(f"Piping{k}", pts, gold, r=0.0055, caps=False)
        chest(gold, "Star", star_pts(8, 0.068, 0.028), 0.6, 0.012)
        band("Belt", 0.405, gold, minor=0.014)
        box("Belt_Buckle", (0, -0.112, 0.405), (0.05, 0.016, 0.04), red, bevel=0.008)
        torus("Collar", (0, 0.004, 0.69), 0.058, 0.013, red, seg=16)

    for s, side in sides():
        with limb("Arm" + side):
            hc, el, wr = arm(s, side, blue, red, glow, cuff=gold, shoulder=red)
            sph(f"Hand_{side}_Halo", hc + Vector((0, 0, -0.004)), (0.066, 0.064, 0.064), halo, seg=16, ring=8)
            for k, (dx, dz) in enumerate([(-0.06, 0.04), (0.055, 0.025), (0.02, -0.035)]):
                sph(f"Hand_{side}_Spark{k}", hc + Vector((s * dx, -0.045, dz)), (0.009,) * 3, glow, seg=6, ring=3)
        with limb("Leg" + side):
            leg(s, side, blue, red, navy, boot_top=0.215, cuff=gold)
            p0 = Vector((s * 0.135, -0.02, 0.33))
            tube(f"Leg_{side}_Stripe", [p0, Vector((s * 0.142, -0.012, 0.25)), Vector((s * 0.142, -0.01, 0.22))],
                 red, r=0.011, caps=False)

    return dict(backdrop="dfe5f3", pivots=pivots(), target=(0, 0, 0.56), dist=2.55, ptarget=(0, 0, 0.79), pdist=1.5)


# ====================================================================== 2. Scarlet Witch
def scarlet_witch():
    reset("ScarletWitch")
    black, white = common()
    skin = mat("Skin", "f3c7aa", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "a5432a", rough=0.4, coat=0.35)
    hair2 = mat("HairShade", "86321e", rough=0.45, coat=0.3)
    coat = mat("Coat", "b8182f", rough=0.38, coat=0.55)
    coat2 = mat("CoatDark", "7c0e22", rough=0.42, coat=0.45)
    corset = mat("Corset", "5e0b1b", rough=0.35, coat=0.6)
    tights = mat("Leggings", "3a0a14", rough=0.45, coat=0.35)
    boot = mat("Boot", "4c0c1a", rough=0.3, coat=0.7)
    crown = mat("Tiara", "d4203a", rough=0.18, metal=0.55, coat=0.8)
    brow = mat("Brow", "7a2a18", rough=0.5)
    mouth = mat("Mouth", "a83a44", rough=0.4)
    blush = mat("Blush", "ff9a8e", rough=0.6, coat=0.0)
    glow = mat("ChaosGlow", "ff1a36", rough=0.25, coat=0.2, emit="ff0020", emit_strength=3.0)
    wisp = glass("ChaosWisp", "ff1a3a", alpha=0.6, emit="ff0028", emit_strength=2.5)

    with limb("Head"):
        sph("Head", HC, HR, skin, seg=28, ring=14, hero=True)
        face(skin, black, white, brow, mouth, blush, grin="smile", brow_tilt=-0.01)
        # long auburn hair, centre parting, falling past the shoulders
        hair_shell("Hair", hair, edge_fn(0.56, -1.05, -1.3, face_half=0.82, soft=0.22),
                   bumps=[((0, 0.2, 1), 0.012, 0.5), ((1, 0.2, -0.5), 0.025, 0.5), ((-1, 0.2, -0.5), 0.025, 0.5),
                          ((0, 1, -0.6), 0.03, 0.7)])
        blob("Hair_Back", (0, 0.105, 0.69), (0.19, 0.085, 0.17), hair,
             [((0, 0.3, -1), 0.03, 0.5, (0, 0.01, -0.02)), ((0.8, 0.3, -0.6), 0.02, 0.4), ((-0.8, 0.3, -0.6), 0.02, 0.4)],
             seg=22, ring=12, hero=False)
        for s, side in sides():  # front locks falling over the shoulders
            tube(f"Hair_Lock_{side}", [(s * 0.165, -0.03, 0.83), (s * 0.19, -0.035, 0.74), (s * 0.175, -0.05, 0.64),
                                       (s * 0.15, -0.06, 0.585)], hair2 if s > 0 else hair, r=0.04,
                 radii=[1.0, 1.05, 0.85, 0.45], br=2, res=3)
        # the tiara: a band over the brow, a point dipping onto the forehead, horns sweeping up at the temples
        tube("Tiara_Band", arc_on(HC, HR, [(-0.75, -0.65, 0.5), (-0.4, -1, 0.56), (0, -1, 0.5), (0.4, -1, 0.56),
                                           (0.75, -0.65, 0.5)], lift=0.026), crown, r=0.011, br=2)
        p, n = on(HC, HR, (0, -1, 0.5), 0.03)
        prism("Tiara_Point", [(-0.045, 0.02), (0.045, 0.02), (0.0, -0.06)], 0.012, crown, p,
              rot=orient((0, 0, 1), n))
        for s, side in sides():
            p, n = on(HC, HR, (s * 0.7, -0.66, 0.5), 0.028)
            prism(f"Tiara_Horn_{side}", [(-s * 0.032, -0.012), (s * 0.03, -0.012), (s * 0.034, 0.03), (s * 0.012, 0.1)],
                  0.014, crown, p, rot=orient((s * 0.22, 0.25, 1), n))

    with limb("Body"):
        body_core(corset, tights, skin)
        # long red coat: open over the corset at the front, sleeves are the arms
        panel("Coat_Top", coat, lambda c, s, z: min(z - 0.39, max(s, abs(c) - 0.42 + 0.6 * max(0.0, 0.62 - z))),
              grow=0.008)
        for k in (-1, 1):  # the coat's lapel edges
            tube(f"Coat_Lapel{k}", [(k * 0.11, -0.1, 0.665), (k * 0.085, -0.118, 0.56), (k * 0.06, -0.112, 0.45),
                                    (k * 0.07, -0.108, 0.4)], coat2, r=0.012, caps=False)
            tube(f"Corset_V{k}", [(k * 0.075, -0.112, 0.55), (0, -0.112, 0.43)], coat, r=0.006, caps=False)
        band("Corset_Belt", 0.405, coat2, minor=0.016, grow=0.01)
        sph("Corset_Gem", (0, -0.116, 0.405), (0.024, 0.012, 0.024), crown, seg=12, ring=6)

        def skirt(u, v):  # coat tails: u wraps from the front-left round the back to the front-right
            a = math.radians(-145 + 290 * u) + math.pi / 2
            z = 0.4 - 0.225 * v
            rx = 0.152 + 0.075 * v ** 1.2
            ry = 0.122 + 0.085 * v ** 1.2
            ripple = 0.008 * math.sin(a * 6) * v
            return ((rx + ripple) * math.cos(a), (ry + ripple) * math.sin(a) + 0.01 * v, z)
        sheet("Coat_Skirt", skirt, 28, 5, 0.012, coat)
        hem = [Vector(skirt(i / 20, 1.0)) for i in range(21)]
        tube("Coat_Hem", hem, coat2, r=0.009, caps=False)
        # tall collar standing up behind the neck
        sheet("Coat_Collar", lambda u, v: ((0.11 + 0.01 * v) * math.cos(math.radians(200 + 140 * u)),
                                           -(0.085 + 0.02 * v) * math.sin(math.radians(200 + 140 * u)) + 0.01,
                                           0.665 + 0.07 * v), 12, 2, 0.012, coat2)

    for s, side in sides():
        with limb("Arm" + side):
            hc, el, wr = arm(s, side, coat, coat, glow, cuff=coat2, shoulder=coat)
            # swirling chaos magic round the hand
            for k, (tilt, r_) in enumerate([(0.5, 0.062), (-0.7, 0.055)]):
                torus(f"Hand_{side}_Wisp{k}", hc + Vector((0, 0, 0.004 - 0.01 * k)), r_, 0.007, wisp,
                      rot=(tilt, s * 0.4 * (k + 1), k * 0.8), seg=18, mseg=4)
            for k, (dx, dz) in enumerate([(-0.065, 0.03), (0.06, -0.01), (0.0, 0.065)]):
                sph(f"Hand_{side}_Spark{k}", hc + Vector((s * dx, -0.03, dz)), (0.009,) * 3, glow, seg=6, ring=3)
        with limb("Leg" + side):
            leg(s, side, tights, boot, coat2, boot_top=0.24)

    return dict(backdrop="f1dfe2", pivots=pivots(), target=(0, 0, 0.56), dist=2.55)


# ====================================================================== 3. Vision
def vision():
    reset("Vision")
    black, white = common()
    skin = mat("SynthSkin", "c8203a", rough=0.26, coat=0.8, metal=0.1)
    seam = mat("Seam", "8e1626", rough=0.35, coat=0.5)
    green = mat("SuitGreen", "2f8a52", rough=0.35, coat=0.6)
    green2 = mat("SuitGreenDark", "1d5e39", rough=0.38, coat=0.55)
    yellow = mat("Yellow", "e8a000", rough=0.32, coat=0.5)
    cape_m = mat("Cape", "e59a00", rough=0.42, coat=0.4)
    cape_in = mat("CapeInside", "b86e00", rough=0.45, coat=0.4)
    silver = mat("Silver", "c9d1da", rough=0.2, metal=0.9, coat=0.3)
    gold = mat("Gold", "e2b13c", rough=0.22, metal=0.85, coat=0.4)
    gem = mat("MindStone", "ffd400", rough=0.05, coat=1.0, emit="ffc400", emit_strength=4.0)
    mouth = mat("Mouth", "6e0f1c", rough=0.4)

    with limb("Head"):
        sph("Head", HC, HR, skin, seg=28, ring=14, hero=True)
        face(skin, black, white, seam, mouth, None, grin="smile", brow_tilt=0.0, nose=False)
        # synthezoid panel seams: two grooves sweeping back over the crown from beside the stone,
        # and one round each temple
        for s in (-1, 1):
            tube(f"Seam_Crown{s}", arc_on(HC, HR, [(s * 0.2, -1, 0.5), (s * 0.3, -0.5, 1), (s * 0.32, 0.5, 1),
                                                    (s * 0.3, 1, 0.35)], lift=0.001), seam, r=0.0055, caps=False)
            tube(f"Seam_Temple{s}", arc_on(HC, HR, [(s * 0.55, -1, 0.42), (s * 1, -0.5, 0.25), (s * 1, 0.3, 0.1),
                                                    (s * 0.8, 0.8, -0.3)], lift=0.001), seam, r=0.0055, caps=False)
        # the Mind Stone, set in a gold diamond on the forehead
        p, n = on(HC, HR, (0, -1, 0.48), 0.0)
        q = orient((0, 0, 1), n)
        prism("MindStone_Setting", [(0, 0.062), (0.047, 0), (0, -0.052), (-0.047, 0)], 0.012, silver, p + n * 0.004, rot=q)
        prism("MindStone", [(0, 0.046), (0.033, 0), (0, -0.038), (-0.033, 0)], 0.018, gem, p + n * 0.013, rot=q,
              bevel=0.006)

    with limb("Body"):
        body_core(green, None, skin)
        # darker green diamond pattern on the chest and a yellow V collar
        panel("Suit_Sides", green2, lambda c, s, z: min(abs(c) - 0.62 - 0.25 * max(0.0, z - 0.45), z - 0.4))
        p = []
        for z, xk in ((0.665, 1.0), (0.6, 0.55), (0.53, 0.0)):
            rx, ry, dy = torso_at(z)
            p.append((xk, -ry + dy - 0.006, z, rx))
        for k in (-1, 1):
            tube(f"Collar_V{k}", [(k * a[0] * a[3] * 0.6, a[1], a[2]) for a in p], yellow, r=0.014, caps=False)
        chest(green2, "Chest_Diamond", [(0, 0.085), (0.075, 0), (0, -0.085), (-0.075, 0)], 0.53, 0.01)
        band("Belt", 0.405, yellow, minor=0.017)
        chest(gold, "Belt_Diamond", [(0, 0.035), (0.03, 0), (0, -0.035), (-0.03, 0)], 0.405, 0.012)

    with limb("Cape"):
        def cape(u, v):
            x0 = -1 + 2 * u
            z = 0.672 - 0.5 * v
            w = 0.135 + 0.14 * v
            rx, ry, dy = torso_at(min(max(z, 0.31), 0.69))
            back = ry + dy + 0.022 + 0.06 * v * v
            y = back + 0.035 * (1 - x0 * x0) * (0.3 + v) - 0.06 * (1 - v) ** 3 * x0 * x0
            y += 0.012 * math.sin(x0 * math.pi * 2.5) * v                                   # soft folds
            return (x0 * w, y, z)
        sheet("Cape", cape, 22, 10, 0.012, cape_m)
        # inside lining peeks out at the hem; clasp discs at the shoulders
        tube("Cape_Hem", [Vector(cape(i / 18, 1.0)) for i in range(19)], cape_in, r=0.009, caps=False)
        for k in (-1, 1):
            cyl(f"Cape_Clasp{k}", (k * 0.125, 0.07, 0.668), 0.024, 0.012, gold, rot=aim((k * 0.2, -1, 0.4)), seg=12)
        # high standing collar
        sheet("Cape_Collar", lambda u, v: ((0.125 + 0.03 * v) * math.cos(math.radians(195 + 150 * u)),
                                           -(0.1 + 0.03 * v) * math.sin(math.radians(195 + 150 * u)) + 0.025,
                                           0.66 + 0.09 * v), 14, 2, 0.012, cape_m)

    for s, side in sides():
        with limb("Arm" + side):
            arm(s, side, green, yellow, yellow, cuff=gold)
        with limb("Leg" + side):
            leg(s, side, green, yellow, cape_in, boot_top=0.23, cuff=gold)

    return dict(backdrop="e2efe6", pivots=pivots(Cape=(0, 0.1, 0.67)), target=(0, 0, 0.56), dist=2.55, yaw=34)


# ====================================================================== 4. Ant-Man
def ant_man():
    reset("AntMan")
    black, white = common()
    red = mat("SuitRed", "c8202e", rough=0.3, coat=0.7)
    dark = mat("SuitBlack", "24262c", rough=0.38, coat=0.55)
    silver = mat("Silver", "d5dce4", rough=0.26, metal=0.6, coat=0.6)
    steel = mat("Steel", "8c96a3", rough=0.3, metal=0.6, coat=0.4)
    grille = mat("Grille", "30343c", rough=0.3, metal=0.6, coat=0.4)
    lens = mat("Lens", "1f9cff", rough=0.04, coat=1.0, emit="0a7cff", emit_strength=1.4)
    lens_rim = mat("LensRim", "1b1d22", rough=0.3, coat=0.6)
    glint = mat("Glint", "ffffff", rough=0.1, coat=0.0, emit="ffffff", emit_strength=2.0)
    led = mat("LED", "ff5a3a", rough=0.2, coat=0.5, emit="ff3a1a", emit_strength=4.0)

    with limb("Head"):
        hr = (0.212, 0.2, 0.205)
        sph("Helmet", HC, hr, silver, seg=28, ring=14, hero=True)
        # red top shell running front-to-back, black jaw/faceplate
        hair_shell("Helmet_Top", red, edge_fn(0.62, 0.3, -0.35, face_half=1.1, soft=0.3), radii=(0.222, 0.212, 0.216),
                   center=(0, 0, 0), tuck=0.004, nphi=36, nv=10)
        head_shell("Helmet_Jaw", grille, lambda d: min(-0.25 - d.z, 0.35 - d.y), HC + Vector((0, -0.01, -0.05)),
                   (0.2, 0.19, 0.16))
        # big blue eye lenses
        for s, side in sides():
            p, n = on(HC, hr, (s * 0.4, -1, 0.08), 0.0)
            q = aim(n)
            cyl(f"Lens_{side}_Rim", p + n * 0.006, 0.075, 0.03, lens_rim, rot=q, seg=24)
            sph(f"Lens_{side}", p + n * 0.02, (0.064, 0.064, 0.02), lens, rot=q, seg=20, ring=8)
            sph(f"Lens_{side}_Glint", p + n * 0.036 + q @ Vector((-0.022, 0.024, 0)), (0.014, 0.01, 0.004), glint,
                rot=q, seg=8, ring=4)
            # round side pods with the antennae rising out of them
            pod = Vector((s * 0.205, 0.015, HC.z + 0.02))
            cyl(f"Pod_{side}", pod, 0.06, 0.04, red, rot=aim((s, 0, 0)), seg=20)
            cyl(f"Pod_{side}_Cap", pod + Vector((s * 0.022, 0, 0)), 0.042, 0.016, silver, rot=aim((s, 0, 0)), seg=16)
            sph(f"Pod_{side}_LED", pod + Vector((s * 0.031, 0, 0)), (0.008, 0.012, 0.012), led, seg=8, ring=4)
            base = Vector((s * 0.12, 0.04, HC.z + 0.17))
            tip = Vector((s * 0.2, 0.06, HC.z + 0.33))
            tube(f"Antenna_{side}", [base, base + Vector((s * 0.03, 0.0, 0.08)), tip], steel, r=0.009,
                 radii=[1.2, 1, 0.75], caps=False)
            sph(f"Antenna_{side}_Tip", tip, (0.016, 0.016, 0.016), silver, seg=10, ring=5)
            sph(f"Antenna_{side}_Base", base, (0.022, 0.022, 0.014), steel, seg=10, ring=5)
        # mouth grille: a silver rounded mask with vents
        p, n = on(HC, hr, (0, -1, -0.38), 0.0)
        q = orient((0, 0, 1), n)
        sph("Mouthpiece", p + n * 0.005, (0.075, 0.03, 0.05), silver, rot=q, seg=18, ring=8)
        for k in range(4):
            box(f"Mouth_Vent{k}", p + n * 0.032 + Vector(((k - 1.5) * 0.026, 0, -0.004)), (0.01, 0.01, 0.05), grille,
                bevel=0.004, rot=q)
        # centre ridge running over the top of the helmet
        tube("Helmet_Ridge", arc_on(HC, (0.222, 0.212, 0.216), [(0, -1, 0.62), (0, -0.6, 1), (0, 0.4, 1), (0, 1, 0.2)],
                                    lift=0.0), silver, r=0.012, caps=False)

    with limb("Body"):
        body_core(red, None, dark)
        panel("Suit_Sides", dark, lambda c, s, z: min(abs(c) - 0.55, 0.6 - 0.1 * abs(s) - z))
        panel("Suit_Shoulders", dark, lambda c, s, z: z - 0.64)
        # silver chest plate with the ant emblem
        chest(silver, "Chest_Disc", [(0.06 * math.cos(a * math.pi / 10), 0.06 * math.sin(a * math.pi / 10))
                                     for a in range(20)], 0.58, 0.012)
        chest(red, "Chest_Emblem", [(0.044 * math.cos(a * math.pi / 10), 0.044 * math.sin(a * math.pi / 10))
                                    for a in range(20)], 0.581, 0.02)
        rx, ry, dy = torso_at(0.585)
        p = Vector((0, -ry + dy - 0.018, 0.585))
        sph("Chest_Ant", p + Vector((0, -0.006, 0.0)), (0.02, 0.008, 0.026), dark, seg=10, ring=5)
        for k in (-1, 1):
            sph(f"Chest_AntEye{k}", p + Vector((k * 0.011, -0.012, 0.008)), (0.007, 0.004, 0.009), silver, seg=8, ring=4)
            tube(f"Chest_AntFeeler{k}", [p + Vector((k * 0.008, -0.008, 0.02)), p + Vector((k * 0.025, -0.01, 0.04))],
                 dark, r=0.003, caps=False)
        band("Belt", 0.405, dark, minor=0.018)
        rx, ry, dy = torso_at(0.405)
        cyl("Belt_Buckle", (0, -ry + dy - 0.022, 0.405), 0.034, 0.016, silver, rot=aim((0, -1, 0)), seg=20)
        sph("Belt_Buckle_Light", (0, -ry + dy - 0.032, 0.405), (0.02, 0.006, 0.02), led, seg=10, ring=4)
        for k in (-1, 1):  # Pym-particle canisters
            cyl(f"Belt_Canister{k}", (k * 0.105, -0.08, 0.405), 0.02, 0.05, silver, rot=aim((k * 0.6, -1, 0)), seg=12)
            sph(f"Belt_Canister{k}_Glow", (k * 0.118, -0.1, 0.405), (0.012, 0.006, 0.012), red, seg=8, ring=4)
        # back pack unit
        box("Backpack", (0, 0.125, 0.555), (0.17, 0.05, 0.16), steel, bevel=0.02)
        box("Backpack_Panel", (0, 0.152, 0.555), (0.11, 0.012, 0.1), red, bevel=0.008)

    for s, side in sides():
        with limb("Arm" + side):
            arm(s, side, red, dark, dark, cuff=silver, shoulder=dark)
            cyl(f"Arm_{side}_Disc", (s * 0.252, -0.025, 0.455), 0.02, 0.012, silver, rot=aim((s, -0.4, 0)), seg=12)
        with limb("Leg" + side):
            leg(s, side, red, dark, dark, boot_top=0.21, cuff=silver)
            tube(f"Leg_{side}_Stripe", [(s * 0.14, 0, 0.32), (s * 0.143, 0, 0.24)], dark, r=0.012, caps=False)
            sph(f"Leg_{side}_Knee", (s * 0.09, -0.047, 0.215), (0.04, 0.02, 0.036), silver, seg=12, ring=6)

    return dict(backdrop="f2e0dc", pivots=pivots(), target=(0, 0, 0.57), dist=2.6)


# ====================================================================== 5. Wasp
def wasp():
    reset("Wasp")
    black, white = common()
    skin = mat("Skin", "f0c4a2", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "2a2226", rough=0.35, coat=0.45)
    yel = mat("SuitYellow", "ffbf00", rough=0.3, coat=0.7)
    blk = mat("SuitBlack", "1f2026", rough=0.35, coat=0.6)
    gold = mat("Gold", "e7a51c", rough=0.22, metal=0.8, coat=0.4)
    brow = mat("Brow", "2a2226", rough=0.5)
    mouth = mat("Mouth", "b34a52", rough=0.4)
    blush = mat("Blush", "ff9a8e", rough=0.6, coat=0.0)
    wing = glass("Wing", "c9efff", alpha=0.38, emit="7fd8ff", emit_strength=0.5)
    vein = mat("WingVein", "f3d36a", rough=0.25, metal=0.6, coat=0.6)
    sting = mat("Sting", "ffe27a", rough=0.2, coat=0.4, emit="ffcc33", emit_strength=4.0)

    with limb("Head"):
        sph("Head", HC, HR, skin, seg=28, ring=14, hero=True)
        face(skin, black, white, brow, mouth, blush, grin="smile")
        # sleek black bob with blunt bangs
        hair_shell("Hair", hair, edge_fn(0.42, -0.6, -0.75, face_half=0.9, soft=0.18),
                   bumps=[((0, 0.2, 1), 0.012, 0.6), ((1, 0, -0.6), 0.025, 0.5), ((-1, 0, -0.6), 0.025, 0.5),
                          ((0, 1, -0.5), 0.02, 0.6)])
        # yellow headband with two antennae
        tube("Headband", arc_on(HC, (0.228, 0.22, 0.224), [(-1, 0.1, 0.35), (-0.6, -0.8, 0.62), (0, -1, 0.68),
                                                            (0.6, -0.8, 0.62), (1, 0.1, 0.35)], lift=0.006),
             yel, r=0.013, br=2)
        for s, side in sides():
            base = Vector((s * 0.09, -0.12, HC.z + 0.17))
            mid = Vector((s * 0.13, -0.17, HC.z + 0.29))
            tip = Vector((s * 0.2, -0.15, HC.z + 0.34))
            tube(f"Antenna_{side}", [base, mid, tip], blk, r=0.0075, caps=False)
            sph(f"Antenna_{side}_Tip", tip, (0.017, 0.017, 0.017), yel, seg=10, ring=5)

    with limb("Body"):
        body_core(yel, blk, blk)
        # wasp stripes round the waist, black shoulders and side panels
        panel("Suit_Shoulders", blk, lambda c, s, z: z - 0.62 + 0.05 * (1 - abs(c)))
        panel("Suit_Sides", blk, lambda c, s, z: abs(c) - 0.78)
        for k, z in enumerate((0.455, 0.51)):
            band(f"Stripe{k}", z, blk, minor=0.013, grow=0.0)
        rx, ry, dy = torso_at(0.575)
        chest(blk, "Chest_Chevron", [(-0.08, 0.025), (0, -0.025), (0.08, 0.025), (0.08, 0.0), (0, -0.05), (-0.08, 0.0)],
              0.58, 0.01)
        band("Belt", 0.405, gold, minor=0.014)
        chest(yel, "Belt_Buckle", [(0, 0.03), (0.03, 0), (0, -0.03), (-0.03, 0)], 0.405, 0.012)
        # wing mount on the back
        sph("Wing_Mount", (0, 0.125, 0.585), (0.06, 0.03, 0.05), blk, seg=14, ring=7)

    for s, side in sides():
        with limb("Wing" + side):
            root = Vector((s * 0.035, 0.145, 0.59))
            for k, (ang, ln, wd, back) in enumerate([(38, 0.27, 0.09, 0.03), (-30, 0.19, 0.065, 0.05)]):
                a = math.radians(ang)
                d = Vector((s * math.cos(a), 0.22, math.sin(a))).normalized()
                cen = root + d * (ln * 0.95) + Vector((0, back, 0))
                q = orient(d, (0, 1, 0))
                sph(f"Wing_{side}{k}", cen, (wd, ln, 0.004), wing, rot=q, seg=28, ring=12)
                # gold rim + veins
                rim = [cen + q @ Vector((math.sin(t) * wd * 0.97, math.cos(t) * ln * 0.97, 0))
                       for t in [i * 2 * math.pi / 20 for i in range(21)]]
                tube(f"Wing_{side}{k}_Rim", rim, vein, r=0.0032, caps=False, res=1)
                tube(f"Wing_{side}{k}_Vein", [root + Vector((0, back * 0.4, 0)), cen - d * ln * 0.3, cen + d * ln * 0.8],
                     vein, r=0.0035, caps=False)
                for j in (-1, 1):
                    tube(f"Wing_{side}{k}_Vein{j}", [cen - d * ln * 0.2, cen + q @ Vector((j * wd * 0.55, ln * 0.45, 0))],
                         vein, r=0.0025, caps=False)
            sph(f"Wing_{side}_Root", root + Vector((0, 0.01, 0)), (0.018, 0.016, 0.018), vein, seg=10, ring=5)
        with limb("Arm" + side):
            hc, el, wr = arm(s, side, yel, blk, blk, cuff=gold, shoulder=blk)
            # wrist stingers
            cyl(f"Arm_{side}_Stinger", wr + Vector((s * 0.012, -0.03, 0.01)), 0.016, 0.03, gold, rot=aim((0, -1, 0)), seg=12)
            sph(f"Arm_{side}_StingerGlow", wr + Vector((s * 0.012, -0.048, 0.01)), (0.01, 0.006, 0.01), sting, seg=8, ring=4)
        with limb("Leg" + side):
            leg(s, side, blk, yel, blk, boot_top=0.22, cuff=blk)
            tube(f"Leg_{side}_Stripe", [(s * 0.14, -0.005, 0.33), (s * 0.143, -0.003, 0.25)], yel, r=0.011, caps=False)

    return dict(backdrop="f4ecd2", pivots=pivots(WingL=(-0.035, 0.145, 0.59), WingR=(0.035, 0.145, 0.59)),
                target=(0, 0, 0.57), dist=2.6)


# ====================================================================== 6. Falcon
def falcon():
    reset("Falcon")
    black, white = common()
    skin = mat("Skin", "8a5638", rough=0.42, coat=0.25, sss=0.12)
    hair = mat("Hair", "1e1714", rough=0.6, coat=0.1)
    grey = mat("SuitGrey", "7f8792", rough=0.4, coat=0.45)
    dark = mat("SuitDark", "373c45", rough=0.42, coat=0.45)
    red = mat("SuitRed", "cf2b30", rough=0.32, coat=0.65)
    metal = mat("WingMetal", "9aa4b0", rough=0.22, metal=0.9, coat=0.35)
    metal2 = mat("WingMetalDark", "5b6470", rough=0.25, metal=0.85, coat=0.35)
    silver = mat("Silver", "d0d7df", rough=0.18, metal=0.9, coat=0.4)
    goggle = mat("GoggleLens", "ff3a3a", rough=0.04, coat=1.0, emit="ff1a1a", emit_strength=0.9)
    frame = mat("GoggleFrame", "2a2d33", rough=0.3, coat=0.6)
    glint = mat("Glint", "ffffff", rough=0.1, coat=0.0, emit="ffffff", emit_strength=2.0)
    brow = mat("Brow", "1e1714", rough=0.5)
    mouth = mat("Mouth", "4a2018", rough=0.4)
    jet = mat("JetGlow", "ffb36a", rough=0.2, coat=0.3, emit="ff8a2a", emit_strength=4.0)

    with limb("Head"):
        sph("Head", HC, HR, skin, seg=28, ring=14, hero=True)
        for s, side in sides():
            sph(f"Ear_{side}", (s * 0.2, 0.012, HC.z - 0.015), (0.03, 0.026, 0.045), skin, seg=10, ring=5)
            tube(f"Brow_{side}", arc_on(HC, HR, [(s * 0.17, -1, 0.3), (s * 0.34, -1, 0.34), (s * 0.52, -1, 0.3)],
                                         lift=0.004), brow, r=0.0105, radii=[1.1, 1, 0.65], caps=False)
            # red flight goggles
            p, n = on(HC, HR, (s * 0.35, -1, 0.02), 0.0)
            q = orient((0, 0, 1), n)
            q = q @ Quaternion((0, 0, 1), -s * 0.12)
            sph(f"Goggle_{side}_Frame", p + n * 0.004, (0.074, 0.06, 0.026), frame, rot=q, seg=20, ring=8)
            sph(f"Goggle_{side}", p + n * 0.016, (0.064, 0.05, 0.02), goggle, rot=q, seg=20, ring=8)
            sph(f"Goggle_{side}_Glint", p + n * 0.033 + q @ Vector((-s * 0.022, 0.018, 0.0)), (0.016, 0.01, 0.003), glint,
                rot=q, seg=8, ring=4)
        tube("Goggle_Strap", arc_on(HC, (0.21, 0.198, 0.2), [(-0.62, -0.75, 0.05), (-1, 0, 0.05), (-0.6, 0.8, 0.05),
                                                           (0, 1, 0.05), (0.6, 0.8, 0.05), (1, 0, 0.05),
                                                           (0.62, -0.75, 0.05)], lift=0.006), frame, r=0.011)
        p, n = on(HC, HR, (0, -1, 0.04), 0.012)
        sph("Goggle_Bridge", p, (0.03, 0.014, 0.014), frame, seg=10, ring=5)
        p, n = on(HC, HR, (0, -1, -0.2), 0.008)
        sph("Nose", p, (0.03, 0.024, 0.024), skin, seg=10, ring=5)
        tube("Smile", arc_on(HC, HR, [(-0.17, -1, -0.38), (-0.06, -1, -0.45), (0.06, -1, -0.45), (0.17, -1, -0.37)],
                             lift=0.002), mouth, r=0.0085)
        # close-cropped hair + a neat short beard line
        hair_shell("Hair", hair, edge_fn(0.6, -0.05, -0.55, face_half=1.05, soft=0.3), radii=(0.216, 0.203, 0.212),
                   tuck=0.01, bumps=[((0, 0.2, 1), 0.006, 0.6)])

    with limb("Body"):
        body_core(grey, dark, dark)
        panel("Suit_Sides", dark, lambda c, s, z: min(abs(c) - 0.7, 0.62 - z))
        # red chest harness: straps over the shoulders crossing at a silver buckle
        rx, ry, dy = torso_at(0.53)
        cx = Vector((0, -ry + dy - 0.012, 0.53))
        for k in (-1, 1):
            tube(f"Harness_Up{k}", [cx, Vector((k * 0.08, -0.115, 0.6)), Vector((k * 0.11, -0.07, 0.675)),
                                    Vector((k * 0.11, 0.07, 0.675)), Vector((k * 0.09, 0.128, 0.6))], red, r=0.014,
                 caps=False)
            tube(f"Harness_Down{k}", [cx, Vector((k * 0.1, -0.11, 0.45)), Vector((k * 0.13, -0.085, 0.41))], red,
                 r=0.014, caps=False)
        cyl("Harness_Buckle", cx + Vector((0, -0.006, 0)), 0.032, 0.014, silver, rot=aim((0, -1, 0.1)), seg=18)
        sph("Harness_Buckle_Gem", cx + Vector((0, -0.016, 0)), (0.016, 0.006, 0.016), red, seg=10, ring=5)
        band("Belt", 0.405, dark, minor=0.018)
        cyl("Belt_Buckle", (0, -0.12, 0.405), 0.024, 0.014, silver, rot=aim((0, -1, 0)), seg=14)
        # wing pack on the back, twin jet nozzles at the bottom
        box("Pack", (0, 0.16, 0.555), (0.2, 0.07, 0.2), metal2, bevel=0.03)
        box("Pack_Plate", (0, 0.195, 0.565), (0.15, 0.02, 0.14), metal, bevel=0.012)
        box("Pack_Stripe", (0, 0.207, 0.565), (0.03, 0.01, 0.13), red, bevel=0.004)
        for k in (-1, 1):
            cyl(f"Pack_Jet{k}", (k * 0.055, 0.17, 0.44), 0.026, 0.045, silver, r2=0.032, seg=14)
            sph(f"Pack_JetGlow{k}", (k * 0.055, 0.17, 0.418), (0.022, 0.022, 0.006), jet, seg=10, ring=4)

    for s, side in sides():
        with limb("Wing" + side):
            # folded wing: a spar rising from the pack, metal feathers hanging from it
            root = Vector((s * 0.085, 0.2, 0.61))
            wrist = Vector((s * 0.2, 0.235, 0.77))
            tube(f"Wing_{side}_Spar", [root, root + Vector((s * 0.06, 0.02, 0.1)), wrist], metal2, r=0.022,
                 radii=[1.0, 0.9, 0.75], br=2)
            tube(f"Wing_{side}_Edge", [root + Vector((s * 0.01, -0.01, 0.03)), wrist + Vector((0, -0.012, 0.012))],
                 red, r=0.01, caps=False)
            for k in range(5):
                t = k / 4
                top = root.lerp(wrist, 0.15 + 0.85 * t) + Vector((0, 0.012 * k, 0))
                ln = 0.34 + 0.12 * t
                d = Vector((s * (0.12 + 0.28 * t), 0.05, -1)).normalized()
                w = 0.06
                pts = [(-w / 2, 0), (w / 2, 0), (w / 2, ln * 0.82), (0, ln), (-w / 2, ln * 0.82)]
                prism(f"Wing_{side}_Feather{k}", pts, 0.012, metal if k % 2 == 0 else metal2,
                      top + Vector((0, 0.008 * k, 0)), rot=orient(d, (s * 0.25, 1, 0)))
                if k == 4:
                    prism(f"Wing_{side}_Tip", [(-w / 2, 0), (w / 2, 0), (0, 0.07)], 0.014, red,
                          top + d * (ln - 0.075) + Vector((0, 0.006 * k + 0.004, 0)), rot=orient(d, (s * 0.25, 1, 0)))
        with limb("Arm" + side):
            arm(s, side, grey, grey, dark, cuff=red, shoulder=dark)
            tube(f"Arm_{side}_Stripe", [(s * 0.214, -0.036, 0.6), (s * 0.232, -0.046, 0.52)], red, r=0.01, caps=False)
        with limb("Leg" + side):
            leg(s, side, dark, frame, frame, boot_top=0.2, cuff=red, knee=grey)

    return dict(backdrop="e3e7ee", pivots=pivots(WingL=(-0.085, 0.2, 0.61), WingR=(0.085, 0.2, 0.61)),
                target=(0, 0, 0.57), dist=2.6)


# ====================================================================== 7. War Machine
WM = prof_scale(1.1, 1.08, chest=1.06)


def war_machine():
    reset("WarMachine")
    black, white = common()
    gun = mat("Gunmetal", "656c77", rough=0.3, metal=0.55, coat=0.6)
    dark = mat("DarkArmour", "3a3f48", rough=0.32, metal=0.5, coat=0.55)
    silver = mat("Silver", "d3d9e0", rough=0.24, metal=0.6, coat=0.6)
    joint = mat("Joint", "23262b", rough=0.45, coat=0.3)
    glow = mat("EyeGlow", "e6f6ff", rough=0.1, coat=0.3, emit="9fdcff", emit_strength=4.0)
    reactor = mat("Reactor", "d6f0ff", rough=0.1, coat=0.5, emit="6fc8ff", emit_strength=3.5)
    barrel = mat("Barrel", "30343b", rough=0.3, metal=0.6, coat=0.4)
    hazard = mat("Hazard", "f2b02a", rough=0.35, coat=0.5)

    with limb("Head"):
        hr = (0.208, 0.196, 0.2)
        sph("Helmet", HC, hr, dark, seg=30, ring=16, hero=True)
        # silver faceplate (Iron-Man style) with glowing eye slits and a mouth line
        def plate_w(z):  # half-width of the faceplate (direction space) by height: brow, cheeks, jaw
            pts = [(-0.86, 0.3), (-0.7, 0.42), (-0.4, 0.6), (0.05, 0.74), (0.3, 0.5), (0.62, 0.34)]
            for (z0, w0), (z1, w1) in zip(pts, pts[1:]):
                if z <= z1:
                    return w0 + (w1 - w0) * max(0.0, (z - z0) / (z1 - z0))
            return pts[-1][1]
        head_shell("Faceplate", silver, lambda d: min(-d.y - 0.2, plate_w(d.z) - abs(d.x), 0.62 - d.z, d.z + 0.86),
                   HC + Vector((0, -0.004, -0.004)), (0.212, 0.2, 0.204), seg=36, ring=18)
        for s, side in sides():
            p, n = on(HC, hr, (s * 0.33, -1, 0.1), 0.006)
            q = orient((0, 0, 1), n) @ Quaternion((0, 0, 1), s * 0.2)
            prism(f"Eye_{side}", [(-0.052, 0.012), (0.052, 0.012), (0.04, -0.012), (-0.04, -0.012)], 0.012, glow, p,
                  rot=q)
            # round "ear" discs
            pod = Vector((s * 0.198, 0.02, HC.z + 0.01))
            cyl(f"Pod_{side}", pod, 0.058, 0.03, gun, rot=aim((s, 0, 0)), seg=20)
            cyl(f"Pod_{side}_Cap", pod + Vector((s * 0.018, 0, 0)), 0.035, 0.012, silver, rot=aim((s, 0, 0)), seg=14)
        p, n = on(HC, hr, (0, -1, -0.42), 0.004)
        box("Mouth_Line", p, (0.09, 0.008, 0.008), joint, bevel=0.003, rot=orient((0, 0, 1), n))
        tube("Helmet_Crest", arc_on(HC, hr, [(0, -1, 0.62), (0, -0.5, 1), (0, 0.5, 1), (0, 1, 0.3)], lift=0.002),
             gun, r=0.016, caps=False)

    with limb("Body"):
        lathe("Torso", gun, WM)
        panel("Pants", dark, lambda c, s, z: 0.385 - z, prof=WM)
        cyl("Neck", (0, 0.005, 0.705), 0.058, 0.08, joint, seg=14, bevel=0.0)
        # silver chest plates, round arc reactor, armoured abs
        panel("Chest_Plate", silver, lambda c, s, z: min(-s - 0.2, z - 0.52, 0.66 - z, 0.75 - abs(c)), prof=WM,
              grow=0.008)
        rx, ry, dy = torso_at(0.585, WM)
        rc = Vector((0, -ry + dy - 0.012, 0.585))
        cyl("Reactor_Ring", rc, 0.04, 0.02, dark, rot=aim((0, -1, 0.12)), seg=22)
        cyl("Reactor", rc + Vector((0, -0.008, 0)), 0.028, 0.012, reactor, rot=aim((0, -1, 0.12)), seg=20)
        for row, z in enumerate((0.475, 0.43)):
            rx, ry, dy = torso_at(z, WM)
            for k in (-1, 1):
                box(f"Abs{row}{k}", (k * 0.03, -ry + dy - 0.002, z), (0.05, 0.016, 0.036), silver, bevel=0.008)
        band("Belt", 0.392, dark, minor=0.02, prof=WM)
        # shoulder-mounted rotary cannon over the right shoulder
        gc = Vector((0.285, 0.02, 0.785))
        box("Cannon_Mount", (0.215, 0.07, 0.69), (0.09, 0.1, 0.05), dark, bevel=0.014)
        cyl_between("Cannon_Arm", (0.23, 0.07, 0.7), gc + Vector((0, 0.06, 0)), 0.022, joint, seg=12)
        cyl("Cannon_Body", gc + Vector((0, 0.05, 0)), 0.058, 0.15, gun, rot=aim((0, -1, 0)), seg=22)
        cyl("Cannon_Cap", gc + Vector((0, 0.13, 0)), 0.045, 0.02, silver, rot=aim((0, -1, 0)), seg=18)
        cyl("Cannon_Collar", gc + Vector((0, -0.032, 0)), 0.05, 0.03, silver, rot=aim((0, -1, 0)), seg=20)
        for k in range(6):
            a = k * math.pi / 3
            off = Vector((math.cos(a) * 0.028, 0, math.sin(a) * 0.028))
            cyl(f"Cannon_Barrel{k}", gc + off + Vector((0, -0.13, 0)), 0.012, 0.18, barrel, rot=aim((0, -1, 0)), seg=8)
        cyl("Cannon_Spindle", gc + Vector((0, -0.13, 0)), 0.014, 0.18, silver, rot=aim((0, -1, 0)), seg=8)
        cyl("Cannon_Clamp", gc + Vector((0, -0.19, 0)), 0.047, 0.018, silver, rot=aim((0, -1, 0)), seg=20)
        box("Cannon_Ammo", (0.12, 0.155, 0.6), (0.09, 0.06, 0.11), dark, bevel=0.014)
        box("Cannon_Stripe", (0.12, 0.187, 0.6), (0.07, 0.006, 0.022), hazard, bevel=0.003)
        tube("Cannon_Feed", [(0.15, 0.16, 0.66), (0.22, 0.15, 0.74), (0.28, 0.11, 0.785)], joint, r=0.014, caps=False)
        box("Backpack", (0, 0.13, 0.545), (0.2, 0.06, 0.17), dark, bevel=0.025)

    for s, side in sides():
        with limb("Arm" + side):
            hc, el, wr = arm(s, side, gun, gun, dark, cuff=silver, shoulder=dark, thick=1.25)
            hsph(f"Pauldron_{side}", (s * 0.205, 0, 0.64), (0.088, 0.082, 0.07), gun, rot=Quaternion((0, 1, 0), s * 0.45),
                 seg=20, ring=10)
            torus(f"Pauldron_{side}_Rim", (s * 0.205, 0, 0.638), 0.083, 0.012, silver, rot=(0, s * 0.45, 0), seg=20)
            box(f"Gauntlet_{side}", (s * 0.247, -0.034, 0.46), (0.07, 0.07, 0.065), silver, bevel=0.016,
                rot=Quaternion((1, 0, 0), 0.25))
            if s < 0:  # wrist gun on the left
                cyl("Wrist_Gun", (s * 0.29, -0.05, 0.465), 0.012, 0.08, barrel, rot=aim((0, -1, 0.3)), seg=8)
        with limb("Leg" + side):
            leg(s, side, gun, dark, joint, boot_top=0.21, cuff=silver, thick=1.18, knee=silver)
            box(f"Thigh_{side}", (s * 0.09, -0.06, 0.28), (0.075, 0.03, 0.08), silver, bevel=0.012)

    return dict(backdrop="e2e4e8", pivots=pivots(), target=(0, 0, 0.58), dist=2.6)


# ====================================================================== 8. Winter Soldier
def winter_soldier():
    reset("WinterSoldier")
    black, white = common()
    skin = mat("Skin", "eec2a2", rough=0.45, coat=0.25, sss=0.15)
    hair = mat("Hair", "5a3a26", rough=0.45, coat=0.3)
    hair2 = mat("HairShade", "45291a", rough=0.5, coat=0.25)
    jacket = mat("Jacket", "262a31", rough=0.4, coat=0.45)
    vest = mat("Vest", "353b44", rough=0.42, coat=0.4)
    strap = mat("Strap", "1a1b1f", rough=0.4, coat=0.5)
    pants = mat("Pants", "2f3442", rough=0.48, coat=0.3)
    boot = mat("Boot", "18191c", rough=0.3, coat=0.7)
    buckle = mat("Buckle", "aab2bc", rough=0.22, metal=0.9, coat=0.3)
    metal = mat("MetalArm", "dfe5ec", rough=0.22, metal=0.65, coat=0.7)
    metal2 = mat("MetalArmDark", "9aa4b0", rough=0.26, metal=0.65, coat=0.5)
    red = mat("Star", "d4202e", rough=0.3, coat=0.7)
    brow = mat("Brow", "45291a", rough=0.5)
    mouth = mat("Mouth", "8a3a34", rough=0.4)
    
    with limb("Head"):
        sph("Head", HC, HR, skin, seg=28, ring=14, hero=True)
        face(skin, black, white, brow, mouth, None, grin="firm", brow_tilt=-0.04)
        # shoulder-length messy hair, centre-ish parting
        hair_shell("Hair", hair, edge_fn(0.52, -1.0, -1.25, face_half=0.86, soft=0.2, part=0.05),
                   bumps=[((0, 0.2, 1), 0.015, 0.5), ((1, 0.1, -0.5), 0.03, 0.45), ((-1, 0.1, -0.5), 0.03, 0.45),
                          ((0, 1, -0.6), 0.03, 0.6), ((-0.4, -0.85, 0.55), 0.018, 0.25, (0.006, 0, -0.006)),
                          ((0.4, -0.85, 0.55), 0.018, 0.25, (-0.006, 0, -0.006))])
        for s, side in sides():
            tube(f"Hair_Lock_{side}", [(s * 0.17, -0.03, 0.83), (s * 0.2, -0.03, 0.74), (s * 0.2, -0.02, 0.68)],
                 hair2 if s < 0 else hair, r=0.034, radii=[1.0, 1.0, 0.55], br=2)
        blob("Hair_Back", (0, 0.1, 0.72), (0.18, 0.08, 0.13), hair, [((0, 0.4, -1), 0.02, 0.6)], seg=20, ring=10,
             hero=False)

    with limb("Body"):
        body_core(jacket, pants, skin)
        # tactical vest, straps and buckles
        panel("Vest", vest, lambda c, s, z: min(z - 0.42, 0.64 - z, 0.85 - abs(c)), grow=0.01)
        panel("Collar", jacket, lambda c, s, z: z - 0.655, grow=0.012)
        for k in (-1, 1):
            tube(f"Strap{k}", [(k * 0.1, 0.12, 0.62), (k * 0.11, 0.0, 0.69), (k * 0.09, -0.125, 0.6),
                               (k * 0.07, -0.135, 0.45)], strap, r=0.012, caps=False)
            box(f"Buckle{k}", (k * 0.082, -0.137, 0.54), (0.026, 0.01, 0.02), buckle, bevel=0.004)
        for k, x in enumerate((-0.07, 0.0, 0.07)):  # magazine pouches
            box(f"Pouch{k}", (x, -0.128, 0.475), (0.05, 0.03, 0.06), strap, bevel=0.01)
        band("Belt", 0.405, strap, minor=0.018)
        box("Belt_Buckle", (0, -0.117, 0.405), (0.045, 0.012, 0.03), buckle, bevel=0.006)
        box("Belt_Pouch", (-0.135, -0.06, 0.39), (0.04, 0.06, 0.06), strap, bevel=0.01, rot=(0, 0, 0.5))

    # ArmL: the silver metal arm with the red star; ArmR: jacket sleeve + black glove
    with limb("ArmL"):
        hc, el, wr = arm(-1, "L", metal, metal, metal2, shoulder=metal)
        for k, t in enumerate((0.2, 0.45, 0.7)):
            p = Vector((-0.2, 0, 0.61)).lerp(el, t)
            torus(f"Arm_L_Seg{k}", p, 0.042, 0.004, metal2, rot=aim(el - Vector((-0.2, 0, 0.61))), seg=16, mseg=4)
        for k, t in enumerate((0.35, 0.7)):
            p = el.lerp(wr, t)
            torus(f"Arm_L_ForeSeg{k}", p, 0.039, 0.004, metal2, rot=aim(wr - el), seg=16, mseg=4)
        for k in range(3):  # overlapping shoulder plates
            hsph(f"Arm_L_Plate{k}", (-0.205, 0, 0.64 - 0.03 * k), (0.07 - 0.004 * k, 0.068 - 0.004 * k, 0.05),
                 metal if k % 2 == 0 else metal2, rot=Quaternion((0, 1, 0), -0.55), seg=18, ring=8)
        p = Vector((-0.258, -0.004, 0.618))
        prism("Arm_L_Star", star_pts(5, 0.04, 0.017), 0.01, red, p, rot=orient((0.2, 0, 1), (-1, -0.2, 0.3)))
    with limb("ArmR"):
        arm(1, "R", jacket, jacket, strap, cuff=strap, shoulder=jacket)
        tube("Arm_R_Strap", [(0.205, -0.04, 0.6), (0.225, -0.035, 0.56)], strap, r=0.008, caps=False)
    for s, side in sides():
        with limb("Leg" + side):
            leg(s, side, pants, boot, strap, boot_top=0.21, cuff=strap)
            if s > 0:  # thigh holster
                box("Leg_R_Holster", (0.145, -0.01, 0.27), (0.03, 0.07, 0.09), strap, bevel=0.01)
                torus("Leg_R_HolsterStrap", (0.09, 0, 0.27), 0.066, 0.008, strap, seg=16)


    return dict(backdrop="dfe3ea", pivots=pivots(), target=(0, 0, 0.57), dist=2.6, yaw=-32, pyaw=-24)


# ====================================================================== runner
HEROES = {"captain_marvel": captain_marvel, "scarlet_witch": scarlet_witch, "vision": vision, "ant_man": ant_man,
          "wasp": wasp, "falcon": falcon, "war_machine": war_machine, "winter_soldier": winter_soldier}


def export_hero(name, pv, parents=None):
    groups = {}
    for o in mesh_objs():
        groups.setdefault(o["limb"], []).append(o)
    missing = set(groups) - set(pv)
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
        bpy.context.scene.cursor.location = Vector(pv[g])
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        exported.append(ob)
    bpy.ops.object.select_all(action="DESELECT")
    for o in exported:
        o.select_set(True)
    out = os.path.join(ROOT, "assets", "characters", f"hero_{name}.glb")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True)
    print("EXPORTED", out)
    for g in sorted(pv):
        if g in groups:
            p = Vector(pv[g])
            print(f"  NODE {g:6s} blender=({p.x:+.3f},{p.y:+.3f},{p.z:+.3f})  godot=({p.x:+.3f},{p.z:+.3f},{-p.y:+.3f})")
    # sanity: ArmR's lowest point must be its hand
    arm_r = bpy.data.objects.get("ArmR")
    if arm_r:
        zs = [(arm_r.matrix_world @ v.co).z for v in arm_r.data.vertices]
        print(f"  ArmR z {min(zs):.3f}..{max(zs):.3f}")
    return out


def portrait(name, opts, path):
    sc = bpy.context.scene
    cam_at(opts.get("ptarget", (0, 0, 0.79)), opts.get("pdist", 1.5), opts.get("pyaw", 24), opts.get("ppitch", 8),
           lens=60)
    tmp = path + ".tmp.png"
    render(tmp, 640, samples=96)
    downscale(tmp, path, 320)
    os.remove(tmp)


def build(name, budget=7500):
    fast = "--fast" in sys.argv
    concept = os.path.join(ROOT, "concepts", f"hero_{name}.png")
    port = os.path.join(ROOT, "assets", "portraits", f"hero_{name}.png")
    if not fast:
        npc_kit.DETAIL[0] = 1.0
        opts = HEROES[name]()
        finalize()
        studio(backdrop=opts["backdrop"], target=opts["target"], dist=opts["dist"])
        cam_at(opts["target"], opts["dist"], opts.get("yaw", 30), opts.get("pitch", 12))
        render(concept, 1024, samples=96)
        portrait(name, opts, port)
    npc_kit.DETAIL[0] = 1.0
    for attempt in range(6):
        opts = HEROES[name]()
        finalize()
        total = sum(tri_report().values())
        print(f"BUDGET {name} detail={npc_kit.DETAIL[0]:.2f} tris={total}")
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
        for k, (yaw, pitch) in enumerate([(0, 6), (30, 12), (90, 6), (155, 10), (-40, 28)]):
            cam_at(tgt, min(dist, 1.9) if k == 3 else dist, yaw, pitch, lens=48 if k == 3 else 60)
            pth = os.path.join(SCRATCH, f"{name}_v{k}.png")
            render(pth, 420, samples=24)
            views.append(pth)
        cam_at(tgt, dist, 25, 35)
        small = os.path.join(SCRATCH, f"{name}_small.png")
        render(small, 72, samples=16)
        views.append(small)
        contact_sheet(views, os.path.join(SCRATCH, f"{name}_sheet.png"), cols=3, cell=420)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "art", "characters", f"hero_{name}.blend"), compress=True)
    export_hero(name, opts["pivots"], opts.get("parents"))


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    names = [a for a in args if not a.startswith("--")]
    if names == ["all"]:
        names = list(HEROES)
    for n in names:
        build(n)
