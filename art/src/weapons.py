# Toy weapons for the player figures (kid/fox/robot/dino).
# Run: blender --background --python art/src/weapons.py
# Units are GAME units: the figure is 0.55 tall in the world (glb 1.0 x player MODEL_SCALE 0.55),
# its fist is ~0.04 across. If a weapon is parented under the scaled character model (e.g. ArmR),
# give it scale 1/0.55 to keep these sizes.
#
# Blender Z-up, weapons point -Y (= Godot +Z, forward). Exports assets/weapons/weapons.glb with
# top-level nodes, all at the origin with identity transforms:
#   Sword, Knife, Blaster, Bow, Arrow, Hammer, RocketLauncher, Rocket, Bat   (one mesh each)
#   Blaster_Muzzle, Bow_Muzzle, RocketLauncher_Muzzle                         (empties)
# Each weapon's origin is its grip (centre of the closed fist). The fist wraps the handle along
# the weapon axis (Godot Z) for Sword/Knife/Hammer/Bat, around a pistol grip for Blaster and
# RocketLauncher (grip runs Godot Y, tilted), and around the vertical riser for the Bow.
# Arrow: origin at its nock, points +Z. Rocket: origin at its tail, points +Z.
# Bow_Muzzle sits at the nocking point on the string, so an Arrow spawned there with the
# muzzle's transform sits nocked on the bow, resting on the arrow shelf.
# Plus a 256x256 transparent picker icon per weapon: assets/weapons/<name>.png (lowercase).
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector, Euler, Matrix

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
OUT = os.path.join(ROOT, "assets", "weapons")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
TAU = 2 * math.pi


# ---------------------------------------------------------------- materials
def lin(hexstr):
    out = []
    for i in (0, 2, 4):
        c = int(hexstr[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


mats = {}


def mat(name, color, rough, metal=0.0, coat=0.0, emit=None, emit_strength=0.0):
    if name in mats:
        return mats[name]
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = lin(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
    if emit:
        b.inputs["Emission Color"].default_value = lin(emit)
        b.inputs["Emission Strength"].default_value = emit_strength
    mats[name] = m
    return m


STEEL = mat("Steel", "b4bfcc", 0.26, metal=0.85)
EDGE = mat("SteelEdge", "f4f8fc", 0.12, metal=1.0)
DKSTEEL = mat("DarkSteel", "59606b", 0.32, metal=0.9)
RED = mat("RedPlastic", "e3372c", 0.3, coat=0.7)
ORANGE = mat("OrangePlastic", "f7821c", 0.3, coat=0.7)
YELLOW = mat("YellowPlastic", "fac22e", 0.28, coat=0.7)
TEAL = mat("TealPlastic", "17b4a2", 0.3, coat=0.7)
BLUE = mat("BluePlastic", "2c74d6", 0.32, coat=0.6)
OLIVE = mat("OlivePlastic", "74903a", 0.36, coat=0.5)
DARK = mat("DarkPlastic", "2b2f36", 0.4, coat=0.35)
CREAM = mat("CreamPlastic", "f4ecda", 0.3, coat=0.6)
WOOD = mat("Wood", "c98844", 0.36, coat=0.55)
TAPE = mat("DuctTape", "bcc1c8", 0.48, metal=0.35)
BLKTAPE = mat("BlackTape", "26282d", 0.62)
BRASS = mat("Brass", "dca83f", 0.22, metal=1.0)
CYAN = mat("GlowCyan", "3fdcff", 0.08, emit="2ad8ff", emit_strength=2.2)
EMBER = mat("GlowOrange", "ffbd5c", 0.2, emit="ff7a12", emit_strength=6.0)
STRING = mat("String", "f3e7c4", 0.75)


# ---------------------------------------------------------------- mesh helpers
PARTS = []


def mk(name, bm, mlist, sharp=38, bevel=0.0, seg=2, bevel_angle=30):
    """bmesh -> object. Faces carry material_index into mlist; edges sharper than `sharp` are split."""
    for f in bm.faces:
        f.smooth = True
    bm.normal_update()
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(sharp):
            e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mlist:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if bevel:
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = seg
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(bevel_angle)
        bv.harden_normals = True
    PARTS.append(ob)
    return ob


def frame(axis, u=None):
    a = Vector(axis).normalized()
    if u is None:
        ref = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))
        u = ref.cross(a)
    u = Vector(u)
    u = (u - a * a.dot(u)).normalized()
    v = a.cross(u).normalized()
    return a, u, v


def lathe(name, prof, mlist, p0=(0, 0, 0), axis=(0, -1, 0), u=None, seg=16, sx=1.0, sy=1.0,
          tilt=0.0, caps=(0, 0), closed=False, phase=0.5, sharp=38):
    """Surface of revolution. prof = [(t, r, mi[, twist_segments])]; mi (int or fn(j)) colours the band
    from that ring to the next. caps = material index for the end caps (None = open).
    tilt (deg) tilts every ring plane, for a wrapped-tape look."""
    a, uu, vv = frame(axis, u)
    p0 = Vector(p0)
    tt = math.tan(math.radians(tilt))
    bm = bmesh.new()
    rings = []
    for row in prof:
        t, r = row[0], row[1]
        tw = row[3] if len(row) > 3 else 0
        if r <= 0:
            rings.append([bm.verts.new(p0 + a * t)])
            continue
        ring = []
        for j in range(seg):
            ang = TAU * (j + phase + tw) / seg
            c, s = math.cos(ang), math.sin(ang)
            ring.append(bm.verts.new(p0 + a * (t + tt * r * c) + uu * (c * r * sx) + vv * (s * r * sy)))
        rings.append(ring)
    n = len(rings)
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]
        mi = prof[i][2]
        if len(A) == 1 and len(B) == 1:
            continue
        for j in range(seg):
            k = (j + 1) % seg
            if len(A) == 1:
                f = bm.faces.new([A[0], B[j], B[k]])
            elif len(B) == 1:
                f = bm.faces.new([A[j], B[0], A[k]])
            else:
                f = bm.faces.new([A[j], B[j], B[k], A[k]])
            f.material_index = mi(j) if callable(mi) else mi
    if not closed:
        if caps[0] is not None and len(rings[0]) > 1:
            f = bm.faces.new(rings[0])
            f.material_index = caps[0]
        if caps[1] is not None and len(rings[-1]) > 1:
            f = bm.faces.new(rings[-1][::-1])
            f.material_index = caps[1]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mk(name, bm, mlist, sharp=sharp)


def loft(name, stations, mlist, p0=(0, 0, 0), axis=(0, -1, 0), u=(1, 0, 0), fmat=None, cap0=0, sharp=38):
    """Lofted prism: stations = [(t, [(x, z), ...])] (same point count; a single point = apex).
    fmat(k) gives the material for side k (point k -> k+1)."""
    a, uu, vv = frame(axis, u)
    p0 = Vector(p0)
    bm = bmesh.new()
    rings = [[bm.verts.new(p0 + a * t + uu * x + vv * z) for (x, z) in pts] for t, pts in stations]
    for A, B in zip(rings, rings[1:]):
        m = len(A) if len(A) > 1 else len(B)
        for k in range(m):
            k1 = (k + 1) % m
            if len(B) == 1:
                f = bm.faces.new([A[k], B[0], A[k1]])
            elif len(A) == 1:
                f = bm.faces.new([A[0], B[k], B[k1]])
            else:
                f = bm.faces.new([A[k], B[k], B[k1], A[k1]])
            f.material_index = fmat(k) if fmat else 0
    if cap0 is not None and len(rings[0]) > 2:
        f = bm.faces.new(rings[0])
        f.material_index = cap0
    if len(rings[-1]) > 2:
        f = bm.faces.new(rings[-1])
        f.material_index = cap0 or 0
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mk(name, bm, mlist, sharp=sharp)


def fillet(pts, rad, n=3):
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        A, P, B = pts[i - 1], pts[i], pts[i + 1]
        da, db = A - P, B - P
        a = P + da.normalized() * min(rad, da.length * 0.45)
        b = P + db.normalized() * min(rad, db.length * 0.45)
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * a + 2 * (1 - t) * t * P + t * t * b)
    out.append(pts[-1])
    return out


def sweep(name, pts, radii, m, sides=8, uref=(1, 0, 0), rad=0.0, n=3, caps=True):
    """Tube along a polyline with per-point elliptical section; radii(s) -> (ru, rv), s in [0,1].
    ru runs along uref (kept perpendicular to the path)."""
    pts = fillet(pts, rad, n) if rad else [Vector(p) for p in pts]
    L = [0.0]
    for p, q in zip(pts, pts[1:]):
        L.append(L[-1] + (q - p).length)
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t = (pts[1] - pts[0]).normalized()
        elif i == len(pts) - 1:
            t = (pts[-1] - pts[-2]).normalized()
        else:
            t = ((pts[i + 1] - p).normalized() + (p - pts[i - 1]).normalized()).normalized()
        u = Vector(uref)
        u = (u - t * t.dot(u)).normalized()
        v = t.cross(u)
        ru, rv = radii(L[i] / L[-1])
        rings.append([bm.verts.new(p + u * (math.cos(TAU * (k + 0.5) / sides) * ru) + v * (math.sin(TAU * (k + 0.5) / sides) * rv))
                      for k in range(sides)])
    for A, B in zip(rings, rings[1:]):
        for k in range(sides):
            j = (k + 1) % sides
            bm.faces.new([A[k], A[j], B[j], B[k]])
    if caps:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mk(name, bm, [m], sharp=50)


def shaped_box(name, corner_fn, m, bevel=0.004, seg=2):
    bm = bmesh.new()
    vs = {}
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                vs[(sx, sy, sz)] = bm.verts.new(Vector(corner_fn(sx, sy, sz)))
    quads = [((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1)),
             ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
             ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)),
             ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)),
             ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)),
             ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))]
    for q in quads:
        bm.faces.new([vs[k] for k in q])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mk(name, bm, [m], bevel=bevel, seg=seg)


def box(name, c, size, m, bevel=0.003, seg=2, rot=None):
    c, h = Vector(c), Vector(size) / 2
    q = Euler([math.radians(x) for x in rot]).to_matrix() if rot else None

    def fn(sx, sy, sz):
        p = Vector((sx * h.x, sy * h.y, sz * h.z))
        return c + (q @ p if q else p)
    return shaped_box(name, fn, m, bevel, seg)


def sphere(name, c, r, m, scale=(1, 1, 1), useg=12, vseg=8):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=useg, v_segments=vseg, radius=r)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + Vector(c)
    return mk(name, bm, [m], sharp=60)


def prism(name, outline, normal, thick, m, sharp=40, bevel=0.0):
    """Flat shape (list of 3D points, planar) extruded +-thick/2 along normal."""
    nrm = Vector(normal).normalized() * thick / 2
    bm = bmesh.new()
    A = [bm.verts.new(Vector(p) + nrm) for p in outline]
    B = [bm.verts.new(Vector(p) - nrm) for p in outline]
    bm.faces.new(A)
    bm.faces.new(B[::-1])
    n = len(outline)
    for k in range(n):
        j = (k + 1) % n
        bm.faces.new([A[k], B[k], B[j], A[j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mk(name, bm, [m], sharp=sharp, bevel=bevel, seg=1)


def bolt(c, normal, r=0.0035, m=None):
    """Hex bolt head sitting on a surface."""
    n = Vector(normal).normalized()
    c = Vector(c)
    return lathe("Bolt", [(-0.001, r, 0), (0.0018, r, 0), (0.0026, r * 0.7, 0)], [m or BRASS],
                 p0=c, axis=n, seg=6, caps=(None, 0), phase=0.0, sharp=30)


def tape(c, axis, r, width, tilt=0.0, m=None, seg=16, twist=0.0):
    """A band of tape wrapped round a cylinder of radius r (slightly proud, with soft lips)."""
    w = width / 2
    return lathe("Tape", [(-w, r - 0.0004, 0), (-w + 0.0006, r + 0.0011, 0), (w - 0.0006, r + 0.0011, 0),
                          (w, r - 0.0004, 0)], [m or TAPE], p0=c, axis=axis, seg=seg, tilt=tilt,
                 caps=(None, None), phase=twist, sharp=60)


def ridged(t0, t1, r_hi, r_lo, pitch, mi):
    """Profile rows for a ridged wrap (tape/leather) from t0 to t1."""
    rows, t, up = [], t0, True
    while t < t1 - 1e-6:
        rows.append((t, r_hi if up else r_lo, mi))
        t += pitch / 2
        up = not up
    rows.append((t1, r_hi, mi))
    return rows


def hazard(seg, a=1, b=0):
    return lambda j: a if j % 2 == 0 else b


def collapse(name):
    global PARTS
    bpy.ops.object.select_all(action="DESELECT")
    for o in PARTS:
        o.select_set(True)
    bpy.context.view_layer.objects.active = PARTS[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    bpy.ops.object.material_slot_remove_unused()
    PARTS = []
    return ob


def empty(name, loc):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "SINGLE_ARROW"
    e.empty_display_size = 0.05
    e.location = loc
    bpy.context.collection.objects.link(e)
    return e


# ---------------------------------------------------------------- shared bits
def pistol_grip(top_z=0.034, color=DARK, cap=YELLOW, guard=True):
    """Chunky pistol grip centred on the origin, raked back 15 deg, with trigger + guard."""
    box("Grip", (0, 0.004, -0.004), (0.026, 0.033, 0.078), color, bevel=0.009, seg=2, rot=(15, 0, 0))
    # finger bumps on the front
    for z in (-0.022, -0.006, 0.010):
        sphere("Finger", (0, -0.012 - z * 0.27, z), 0.0075, color, scale=(1.55, 0.75, 1.0), useg=8, vseg=6)
    # side grip panels
    for sx in (-1, 1):
        box("GripPanel", (sx * 0.0128, 0.005, -0.004), (0.003, 0.022, 0.052), cap, bevel=0.0012, seg=1, rot=(15, 0, 0))
    box("GripCap", (0, 0.016, -0.043), (0.029, 0.038, 0.01), cap, bevel=0.004, seg=2, rot=(15, 0, 0))
    box("Trigger", (0, -0.027, 0.018), (0.007, 0.006, 0.017), YELLOW, bevel=0.0025, seg=2, rot=(-14, 0, 0))
    if guard:
        sweep("Guard", [(0, -0.008, top_z - 0.004), (0, -0.044, top_z - 0.004), (0, -0.046, 0.004), (0, -0.024, -0.004),
                        (0, -0.012, 0.0)], lambda s: (0.0042, 0.0032), color, sides=6, rad=0.01, n=3)


# ---------------------------------------------------------------- weapons
def build_sword():
    # pommel
    sphere("Pommel", (0, 0.05, 0), 0.0145, YELLOW, useg=12, vseg=8)
    lathe("PommelNub", [(0, 0.0, 0), (0.004, 0.006, 0), (0.008, 0.0, 0)], [BRASS], p0=(0, 0.071, 0), axis=(0, -1, 0), seg=8)
    # wrapped grip (tilted ridges read as a leather/tape wrap)
    prof = [(0, 0.0095, 0)] + ridged(0.004, 0.072, 0.0118, 0.0104, 0.0085, 0)
    lathe("Grip", prof, [BLUE], p0=(0, 0.04, 0), axis=(0, -1, 0), seg=10, tilt=14, caps=(0, 0))
    # crossguard: curved bar with ball ends + red centre block with a glowing gem
    # (the guard spans the blade's width, Z, like a real crossguard)
    sweep("Guard", [(0, -0.05, -0.06), (0, -0.034, -0.045), (0, -0.031, 0), (0, -0.034, 0.045), (0, -0.05, 0.06)],
          lambda s: (0.0085 + 0.003 * abs(s - 0.5) * 2, 0.0085 + 0.003 * abs(s - 0.5) * 2), YELLOW,
          sides=8, uref=(1, 0, 0), rad=0.03, n=4)
    for sz in (-1, 1):
        sphere("GuardBall", (0, -0.053, sz * 0.062), 0.0125, YELLOW, useg=10, vseg=7)
    box("GuardBlock", (0, -0.031, 0), (0.026, 0.026, 0.04), RED, bevel=0.007, seg=2)
    sphere("Gem", (0, -0.031, 0), 0.0085, CYAN, scale=(1.7, 1, 1), useg=10, vseg=6)
    # blade: hexagonal section, bright bevelled edges, flat steel faces
    def sec(w, t):
        e = min(0.008, w * 0.42)
        return [(0, w), (t, w - e), (t, -(w - e)), (0, -w), (-t, -(w - e)), (-t, w - e)]
    st = [(0.0, sec(0.021, 0.0055)), (0.03, sec(0.023, 0.0055)), (0.09, sec(0.025, 0.0055)),
          (0.17, sec(0.0265, 0.005)), (0.22, sec(0.025, 0.0048)), (0.252, sec(0.019, 0.0042)),
          (0.272, sec(0.011, 0.0034)), (0.29, [(0, 0)])]
    loft("Blade", st, [STEEL, EDGE], p0=(0, -0.036, 0), fmat=lambda k: 0 if k in (1, 4) else 1, cap0=0)
    # fuller inlay down both faces
    for sx in (-1, 1):
        box("Fuller", (sx * 0.0055, -0.15, 0), (0.0016, 0.15, 0.0065), DKSTEEL, bevel=0.0007, seg=1)
    # scrappy repair: a bolted plate clamped round the blade root
    box("Clamp", (0, -0.062, 0), (0.016, 0.02, 0.05), DKSTEEL, bevel=0.003, seg=1)
    for sx in (-1, 1):
        for z in (-0.016, 0.016):
            bolt((sx * 0.008, -0.062, z), (sx, 0, 0), r=0.0034)
    return collapse("Sword")


def build_knife():
    prof = [(0, 0.008, 1), (0.004, 0.0125, 1), (0.011, 0.0125, 1), (0.013, 0.0108, 0),
            (0.02, 0.0124, 0), (0.028, 0.0109, 0), (0.036, 0.0124, 0), (0.044, 0.0109, 0),
            (0.052, 0.0124, 0), (0.06, 0.0116, 0), (0.067, 0.0116, 0)]
    lathe("Handle", prof, [ORANGE, DKSTEEL], p0=(0, 0.047, 0), axis=(0, -1, 0), seg=12, sx=0.82, sy=1.12, caps=(1, 0))
    tape((0, 0.014, 0), (0, -1, 0), 0.0122, 0.011, tilt=12, m=BLKTAPE, seg=12)
    lathe("Lanyard", [(0, 0.0, 0), (0.0, 0.0035, 0), (0.006, 0.0035, 0)], [BRASS], p0=(0, 0.053, 0), axis=(0, -1, 0), seg=8)
    box("Guard", (0, -0.024, 0.002), (0.017, 0.009, 0.05), DKSTEEL, bevel=0.003, seg=2)
    for z in (-0.019, 0.023):
        sphere("GuardEnd", (0, -0.024, z), 0.0068, RED, useg=8, vseg=6)
    # single-edged clip-point blade: spine on top (+Z), edge below
    L, T = 0.13, 0.0034
    st = []
    for s in (0.0, 0.12, 0.28, 0.44, 0.56, 0.66, 0.75, 0.83, 0.9, 0.95):
        ztop = 0.011 if s < 0.62 else 0.011 - 0.0115 * ((s - 0.62) / 0.38) ** 0.9
        zbot = -0.016 if s < 0.5 else -0.016 * math.sqrt(max(0.0, 1 - ((s - 0.5) / 0.5) ** 2))
        zm = zbot + (ztop - zbot) * 0.38
        t = T * (1 - 0.6 * max(0, s - 0.6) / 0.4)
        st.append((s * L, [(t, ztop), (t, zm), (0, zbot), (-t, zm), (-t, ztop)]))
    st.append((L, [(0, -0.0005)]))
    loft("Blade", st, [STEEL, EDGE], p0=(0, -0.028, 0), fmat=lambda k: 1 if k in (1, 2) else 0, cap0=0)
    # saw teeth on the spine
    for i in range(5):
        y0 = -0.036 - i * 0.0105
        prism("Tooth", [(0, y0, 0.0105), (0, y0 - 0.0095, 0.0105), (0, y0 - 0.0015, 0.0175)], (1, 0, 0), 0.005, STEEL)
    return collapse("Knife")


def build_blaster():
    pistol_grip(top_z=0.034, color=DARK, cap=YELLOW)
    # body: wedge-ish rounded block
    def body(sx, sy, sz):
        y = 0.056 if sy > 0 else -0.074
        z = 0.027 if sz < 0 else (0.09 if sy > 0 else 0.079)
        w = 0.022 if sz < 0 else 0.019
        return (sx * w, y, z)
    shaped_box("Body", body, ORANGE, bevel=0.009, seg=2)
    # side armour panels with bolts
    for sx in (-1, 1):
        box("SidePanel", (sx * 0.0215, -0.004, 0.057), (0.003, 0.064, 0.028), DARK, bevel=0.0012, seg=1)
        for y in (0.022, -0.03):
            bolt((sx * 0.023, y, 0.057), (sx, 0, 0), r=0.003)
        box("Vent", (sx * 0.0225, 0.04, 0.05), (0.003, 0.012, 0.004), YELLOW, bevel=0.001, seg=1)
        box("Vent", (sx * 0.0225, 0.04, 0.059), (0.003, 0.012, 0.004), YELLOW, bevel=0.001, seg=1)
    # barrel with cooling fins and a glowing muzzle
    BZ = 0.058
    lathe("Barrel", [(0, 0.0168, 0), (0.1, 0.0168, 0)], [DKSTEEL], p0=(0, -0.066, BZ), axis=(0, -1, 0), seg=16, caps=(None, None))
    for t in (0.022, 0.038, 0.054):
        lathe("Fin", [(0, 0.017, 0), (0.0, 0.0245, 0), (0.008, 0.0245, 0), (0.008, 0.017, 0)], [YELLOW],
              p0=(0, -0.066 - t, BZ), axis=(0, -1, 0), seg=16, caps=(None, None))
    lathe("Muzzle", [(0.0, 0.0175, 0), (0.016, 0.0255, 0), (0.026, 0.0255, 0), (0.029, 0.0225, 0),
                     (0.029, 0.0135, 1), (0.024, 0.0125, 1)],
          [ORANGE, DARK, CYAN], p0=(0, -0.149, BZ), axis=(0, -1, 0), seg=16, caps=(None, 2))
    tape((0, -0.073, BZ), (0, -1, 0), 0.0168, 0.010, tilt=-10, seg=16)
    # glowing energy cell on top, clamped down
    CZ = 0.103
    lathe("Cell", [(0, 0.0155, 0), (0.012, 0.0155, 0), (0.012, 0.0122, 1), (0.062, 0.0122, 0), (0.062, 0.0155, 0),
                   (0.074, 0.0155, 0)], [DARK, CYAN], p0=(0, 0.04, CZ), axis=(0, -1, 0), seg=14, caps=(0, 0))
    for y in (0.034, -0.028):
        box("CellClamp", (0, y, 0.093), (0.02, 0.008, 0.012), DARK, bevel=0.002, seg=1)
    # rear dial, front sight
    lathe("Dial", [(0, 0.012, 0), (0.008, 0.012, 0), (0.01, 0.009, 0)], [YELLOW], p0=(0, 0.054, 0.058), axis=(0, 1, 0), seg=12, caps=(None, 0))
    box("DialNub", (0, 0.0645, 0.058), (0.004, 0.003, 0.016), RED, bevel=0.001, seg=1)
    box("Sight", (0, -0.062, 0.084), (0.005, 0.014, 0.012), YELLOW, bevel=0.002, seg=1)
    collapse_obj = collapse("Blaster")
    return collapse_obj, Vector((0, -0.178, BZ))


def build_bow():
    # riser: grip at the origin, sight window offset to the left (-X) so the arrow passes at x = 0
    sweep("Riser", [(0, 0.0, -0.088), (0, 0.0, -0.03), (0, -0.002, 0.016), (-0.012, -0.002, 0.03), (-0.013, -0.002, 0.06),
                    (0, 0.0, 0.08), (0, 0.0, 0.104)],
          lambda s: (0.012 if (s < 0.45 or s > 0.78) else 0.0085, 0.0155), WOOD, sides=10, rad=0.012, n=3)
    prof = ridged(-0.026, 0.022, 0.0142, 0.0128, 0.008, 0)
    lathe("GripTape", prof, [BLKTAPE], p0=(0, 0, 0), axis=(0, 0, 1), u=(1, 0, 0), seg=12, sx=0.92, sy=1.18, tilt=10, caps=(None, None))
    box("Shelf", (-0.003, -0.002, 0.0255), (0.014, 0.02, 0.006), YELLOW, bevel=0.002, seg=1)
    # limbs: swept back, recurved tips
    upper = [(0.0, 0.09), (0.004, 0.122), (0.016, 0.152), (0.035, 0.179), (0.051, 0.197), (0.055, 0.209), (0.048, 0.219)]
    for sgn in (1, -1):
        zc = 0.008
        pts = [(0, y, zc + sgn * (z - zc)) for y, z in upper]
        sweep("Limb", pts, lambda s: (0.021 - 0.009 * s, 0.0095 - 0.003 * s), TEAL, sides=8, rad=0.012, n=2)
        tip = Vector(pts[-1])
        sphere("Tip", tip, 0.0068, RED, useg=8, vseg=6)
        # limb bolts where the limb meets the riser
        for z in (0.096, 0.112):
            for sx in (-1, 1):
                bolt((sx * 0.0128, 0.0, zc + sgn * (z - zc)), (sx, 0, 0), r=0.0034)
        box("LimbPad", (0, 0.0, zc + sgn * (0.104 - zc)), (0.027, 0.019, 0.026), DARK, bevel=0.004, seg=2)
    # string, straight between the tips' nock points, with a red serving round the nocking point
    SY, SZ = upper[5][0], upper[5][1] - 0.002
    top = Vector((0, SY, SZ))
    bot = Vector((0, SY, 0.016 - SZ))
    lathe("String", [(0, 0.0017, 0), ((top - bot).length, 0.0017, 0)], [STRING], p0=bot, axis=top - bot, seg=6, caps=(None, None))
    lathe("Serving", [(0, 0.0019, 0), (0.002, 0.0028, 0), (0.026, 0.0028, 0), (0.028, 0.0019, 0)], [RED],
          p0=(0, SY, 0.031 - 0.014), axis=(0, 0, 1), seg=6, caps=(None, None))
    return collapse("Bow"), Vector((0, SY, 0.031))


ARROW_LEN = 0.252


def build_arrow():
    prof = [(0, 0.0052, 0), (0.002, 0.0062, 0), (0.013, 0.0062, 0), (0.016, 0.0046, 1), (0.212, 0.0046, 1),
            (0.212, 0.0058, 2), (0.222, 0.0058, 2)]
    lathe("Shaft", prof, [ORANGE, WOOD, DKSTEEL], p0=(0, 0, 0), axis=(0, -1, 0), seg=8, caps=(0, 2))
    # nock slot: two little prongs
    for sz in (-1, 1):
        box("Nock", (0, 0.0015, sz * 0.0037), (0.007, 0.006, 0.0028), ORANGE, bevel=0.001, seg=1)
    # broadhead: flattened diamond, edges bright
    st = [(0.0, [(0, 0.0125), (0.0032, 0.004), (0.0032, -0.004), (0, -0.0125), (-0.0032, -0.004), (-0.0032, 0.004)]),
          (0.008, [(0, 0.0118), (0.0028, 0.004), (0.0028, -0.004), (0, -0.0118), (-0.0028, -0.004), (-0.0028, 0.004)]),
          (ARROW_LEN - 0.214, [(0, 0)])]
    loft("Head", st, [STEEL, EDGE], p0=(0, -0.214, 0), fmat=lambda k: 0 if k in (1, 4) else 1, cap0=0)
    # three vanes, cock vane yellow
    for i, m in enumerate((YELLOW, RED, RED)):
        ang = math.radians(90 + 120 * i)
        d = Vector((math.cos(ang), 0, math.sin(ang)))
        r0 = 0.004
        outline = [Vector((0, -0.014, 0)) + d * r0, Vector((0, -0.068, 0)) + d * r0,
                   Vector((0, -0.05, 0)) + d * (r0 + 0.008), Vector((0, -0.03, 0)) + d * (r0 + 0.0135),
                   Vector((0, -0.017, 0)) + d * (r0 + 0.0135)]
        prism("Vane", outline, d.cross(Vector((0, 1, 0))), 0.0016, m)
    return collapse("Arrow")


def build_hammer():
    prof = [(0, 0.009, 0), (0.004, 0.0158, 0), (0.014, 0.0165, 0), (0.021, 0.0118, 1)]
    prof += ridged(0.022, 0.1, 0.0128, 0.0116, 0.009, 1)
    prof += [(0.104, 0.0112, 2), (0.42, 0.0118, 2)]
    lathe("Handle", prof, [RED, BLKTAPE, WOOD], p0=(0, 0.056, 0), axis=(0, -1, 0), seg=12, tilt=0, caps=(0, None))
    # scrappy repair wraps on the shaft
    tape((0, -0.15, 0), (0, -1, 0), 0.0114, 0.016, tilt=16, seg=12)
    tape((0, -0.17, 0), (0, -1, 0), 0.0115, 0.012, tilt=-12, seg=12)
    lathe("Collar", [(0, 0.0118, 0), (0.002, 0.0152, 0), (0.026, 0.0152, 0), (0.028, 0.013, 0)], [DKSTEEL],
          p0=(0, -0.286, 0), axis=(0, -1, 0), seg=12, caps=(None, None))
    for sx in (-1, 1):
        bolt((sx * 0.0152, -0.299, 0), (sx, 0, 0), r=0.0038)
    # head: barrel along Z, chamfered striking faces, red rims, hazard band
    HY, HALF, R = -0.36, 0.088, 0.054
    seg = 20
    tw = 2
    # bands: face chamfer bright steel(0) / rim red(1) / body dark steel(2) / diagonal hazard stripes(3/4)
    H2 = 2 * HALF
    fix = [(0, 0.041, 0), (0.008, 0.0525, 1), (0.026, 0.0525, 1), (0.029, 0.0495, 2), (0.062, 0.0495, 2),
           (0.066, R, hazard(seg, 3, 4)), (H2 - 0.066, R, 2, tw), (H2 - 0.062, 0.0495, 2, tw),
           (H2 - 0.029, 0.0495, 1, tw), (H2 - 0.026, 0.0525, 1, tw), (H2 - 0.008, 0.0525, 0, tw), (H2, 0.041, 0, tw)]
    lathe("Head", fix, [EDGE, RED, DKSTEEL, YELLOW, BLKTAPE], p0=(0, HY, -HALF), axis=(0, 0, 1), u=(1, 0, 0),
          seg=seg, caps=(0, 0), sharp=30)
    # wedge plate + bolts on the head's sides (where the handle goes through)
    for sx in (-1, 1):
        box("HeadPlate", (sx * 0.048, HY, 0), (0.006, 0.03, 0.03), DKSTEEL, bevel=0.002, seg=1, rot=(0, 0, 0))
        bolt((sx * 0.051, HY, 0), (sx, 0, 0), r=0.0055)
    return collapse("Hammer")


def build_launcher():
    ZC, R, BORE = 0.08, 0.04, 0.033
    seg = 20
    tw = 2
    prof = [(0.0, 0.049, 0), (0.004, 0.051, 0), (0.014, 0.0475, 0), (0.034, 0.0415, 0), (0.044, 0.0415, 1),
            (0.048, R, 1), (0.358, R, hazard(seg, 2, 3)), (0.384, R, 1, tw), (0.384, 0.0455, 0, tw), (0.40, 0.0455, 0, tw),
            (0.403, 0.042, 0, tw), (0.403, BORE + 0.001, 4, tw), (0.395, BORE, 4, tw), (0.012, BORE + 0.003, 4, tw),
            (0.0, 0.044, 4, tw)]
    # fix the band that steps up into the front collar so the hazard band ends with olive lip
    prof[6] = (0.358, R + 0.001, hazard(seg, 2, 3))
    prof[7] = (0.384, R + 0.001, 1, tw)
    lathe("Tube", prof, [ORANGE, OLIVE, YELLOW, BLKTAPE, DARK], p0=(0, 0.2, ZC), axis=(0, -1, 0), seg=seg,
          closed=True, sharp=32)
    # rear bell rim ring
    tape((0, 0.07, ZC), (0, -1, 0), R, 0.016, tilt=7, seg=20)
    tape((0, -0.06, ZC), (0, -1, 0), R, 0.013, tilt=-6, seg=20)
    for y, sx in ((0.07, 1), (-0.06, -1)):
        bolt((sx * 0.0293, y, ZC + 0.0293), (sx, 0, 1), r=0.0042)
    # grips and mounts
    pistol_grip(top_z=0.036, color=DARK, cap=ORANGE)
    box("GripMount", (0, -0.008, 0.036), (0.026, 0.06, 0.016), DARK, bevel=0.004, seg=2)
    box("FrontGrip", (0, -0.112, 0.02), (0.022, 0.026, 0.06), DARK, bevel=0.008, seg=2, rot=(-8, 0, 0))
    box("FrontGripCap", (0, -0.109, -0.009), (0.024, 0.028, 0.008), ORANGE, bevel=0.003, seg=1, rot=(-8, 0, 0))
    box("ShoulderPad", (0, 0.11, 0.036), (0.048, 0.09, 0.02), DARK, bevel=0.007, seg=2)
    # sight on the upper left
    box("SightBase", (-0.03, -0.05, ZC + 0.03), (0.012, 0.03, 0.012), DARK, bevel=0.002, seg=1, rot=(0, -40, 0))
    box("Sight", (-0.036, -0.05, ZC + 0.04), (0.02, 0.048, 0.02), YELLOW, bevel=0.005, seg=2)
    lathe("Lens", [(0, 0.0072, 0), (0.003, 0.0072, 0)], [DARK, CYAN], p0=(-0.036, -0.026, ZC + 0.04), axis=(0, 1, 0), seg=10, caps=(None, 1))
    lathe("Lens", [(0, 0.0072, 0), (0.003, 0.0072, 0)], [DARK, CYAN], p0=(-0.036, -0.074, ZC + 0.04), axis=(0, -1, 0), seg=10, caps=(None, 1))
    return collapse("RocketLauncher"), Vector((0, -0.203, ZC))


def build_rocket():
    prof = [(0, 0.0118, 0), (0.0, 0.0145, 0), (0.007, 0.0158, 0), (0.013, 0.011, 0), (0.014, 0.0195, 1),
            (0.018, 0.0215, 1), (0.088, 0.0215, 2), (0.088, 0.0222, 2), (0.1, 0.0222, 1), (0.1, 0.0215, 1),
            (0.116, 0.0215, 2), (0.13, 0.0205, 2), (0.144, 0.0172, 2), (0.155, 0.0122, 2), (0.162, 0.0066, 2),
            (0.1655, 0.0, 2)]
    lathe("Body", prof, [DKSTEEL, CREAM, RED, EMBER], p0=(0, 0, 0), axis=(0, -1, 0), seg=16, caps=(3, None), sharp=40)
    # 4 swept fins in an X
    for i in range(4):
        ang = math.radians(45 + 90 * i)
        d = Vector((math.cos(ang), 0, math.sin(ang)))
        o = [Vector((0, -0.016, 0)) + d * 0.019, Vector((0, -0.058, 0)) + d * 0.019,
             Vector((0, -0.024, 0)) + d * 0.038, Vector((0, -0.006, 0)) + d * 0.04]
        prism("Fin", o, d.cross(Vector((0, 1, 0))), 0.0032, RED, bevel=0.0008)
    # porthole windows
    for i in range(2):
        ang = math.radians(180 * i)
        d = Vector((math.cos(ang), 0, math.sin(ang)))
        lathe("Window", [(0, 0.0058, 0), (0.0018, 0.0058, 0)], [BLUE], p0=Vector((0, -0.06, 0)) + d * 0.0205, axis=d, seg=10, caps=(None, 0))
    return collapse("Rocket")


def bat_r(t):
    pts = [(0.0, 0.0), (0.003, 0.0095), (0.008, 0.015), (0.013, 0.0152), (0.018, 0.0105), (0.03, 0.0094),
           (0.1, 0.0098), (0.16, 0.0118), (0.21, 0.0155), (0.26, 0.0208), (0.30, 0.0242), (0.34, 0.0258),
           (0.375, 0.026), (0.388, 0.0245), (0.396, 0.019), (0.399, 0.0)]
    return pts


def build_bat():
    P0 = Vector((0, 0.048, 0))
    pts = bat_r(0)
    mi = lambda t: 0 if t < 0.016 else (1 if t < 0.103 else 2)
    prof = []
    for t, r in pts:
        prof.append((t, r, mi(t)))
    # grip zone: ridged black tape replaces the plain rows between 0.018 and 0.103
    grip = ridged(0.02, 0.103, 0.0104, 0.0096, 0.0085, 1)
    prof = [p for p in prof if p[0] < 0.019] + grip + [p for p in prof if p[0] > 0.104]
    prof = [(t, r, mi(t) if t > 0.103 else m) for (t, r, m) in prof]
    lathe("Bat", prof, [RED, BLKTAPE, WOOD], p0=P0, axis=(0, -1, 0), seg=16, tilt=0, caps=(None, None), sharp=50)

    def rad_at(t):
        for (t0, r0), (t1, r1) in zip(pts, pts[1:]):
            if t0 <= t <= t1:
                return r0 + (r1 - r0) * (t - t0) / (t1 - t0)
        return pts[-1][1]
    # duct tape: a single band, then a crossed pair, then a red stripe near the end
    for t, w, tl, m in ((0.19, 0.016, 8, TAPE), (0.27, 0.018, 20, TAPE), (0.27, 0.018, -20, TAPE),
                        (0.345, 0.008, 0, RED)):
        rr = rad_at(t) + (0.0006 if tl < 0 else 0.0)
        tape(P0 + Vector((0, -t, 0)), (0, -1, 0), rr + 0.0003, w, tilt=tl, m=m, seg=16)
    # a loose tape flap peeling off the single band
    r = rad_at(0.19) + 0.0012
    prism("Flap", [(r * 0.97, -0.148 + 0.008, -0.004), (r * 0.97, -0.148 - 0.007, -0.004),
                   (r + 0.006, -0.148 - 0.009, -0.011), (r + 0.008, -0.148 + 0.006, -0.012)], (1, 0, 0.3), 0.0012, TAPE)
    return collapse("Bat")


# ---------------------------------------------------------------- export + report
def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def godot(v):
    return (round(v[0], 3), round(v[2], 3), round(-v[1], 3))


def build():
    out, muzzles = [], {}
    out.append(build_sword())
    out.append(build_knife())
    b, mz = build_blaster(); out.append(b); muzzles["Blaster"] = mz
    b, mz = build_bow(); out.append(b); muzzles["Bow"] = mz
    out.append(build_arrow())
    out.append(build_hammer())
    b, mz = build_launcher(); out.append(b); muzzles["RocketLauncher"] = mz
    out.append(build_rocket())
    out.append(build_bat())
    empties = [empty(f"{k}_Muzzle", v) for k, v in muzzles.items()]
    return out, empties


def export(objs, empties):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs + empties:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "weapons.glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True)
    for o in objs:
        ws = [Vector(c) for c in o.bound_box]
        lo = Vector([min(w[i] for w in ws) for i in range(3)])
        hi = Vector([max(w[i] for w in ws) for i in range(3)])
        size = hi - lo
        print(f"WEAPON {o.name:15s} tris {tris(o):5d}  size godot (x,y,z) = "
              f"({size.x:.3f}, {size.z:.3f}, {size.y:.3f})  godot bbox {godot(lo)} .. {godot(hi)}")
    for e in empties:
        print(f"MUZZLE {e.name:22s} godot {godot(e.location)}")


# ---------------------------------------------------------------- icons
ICON_TILT = {"Sword": 45, "Knife": 45, "Blaster": 18, "Bow": 45, "Arrow": 45, "Hammer": 45,
             "RocketLauncher": 22, "Rocket": 45, "Bat": 45}
VIEW = Vector((1.0, 0.22, -0.34)).normalized()   # camera looks along this: from the weapon's left, a bit above


def icon_setup():
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.samples = int(os.environ.get("WEAPON_SAMPLES", "160"))
    scn.cycles.use_denoising = True
    try:
        scn.cycles.device = "GPU"
    except TypeError:
        pass
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    scn.render.resolution_x = scn.render.resolution_y = 512
    scn.render.film_transparent = True
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGBA"
    world = bpy.data.worlds.new("Studio")
    scn.world = world
    # studio sweep: dark floor, bright horizon band, soft white ceiling -> metals get a crisp horizon glint
    nt = world.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    bg.inputs["Strength"].default_value = 0.9
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mapr = nt.nodes.new("ShaderNodeMapRange")
    mapr.inputs["From Min"].default_value = -1.0
    mapr.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.06, 0.065, 0.08, 1)
    els[1].position, els[1].color = 1.0, (0.85, 0.9, 1.0, 1)
    e = els.new(0.47); e.color = (0.18, 0.19, 0.22, 1)
    e = els.new(0.53); e.color = (1.3, 1.3, 1.35, 1)
    e = els.new(0.62); e.color = (0.55, 0.6, 0.7, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    cam_data = bpy.data.cameras.new("IconCam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("IconCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.rotation_euler = VIEW.to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam
    # lights fixed relative to the view: warm key upper-left-front, cool fill right, strong rim behind
    q = VIEW.to_track_quat("-Z", "Y")
    for off, energy, size, col in [((-0.7, 0.9, 1.0), 13.0, 0.5, (1.0, 0.95, 0.88)),
                                   ((1.0, -0.2, 0.7), 3.0, 0.8, (0.8, 0.88, 1.0)),
                                   ((0.3, 0.8, -1.0), 8.0, 0.35, (1.0, 1.0, 1.0)),
                                   ((-0.5, -0.9, -0.4), 2.5, 0.6, (1.0, 0.9, 0.85))]:
        ld = bpy.data.lights.new("L", "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = col
        lt = bpy.data.objects.new("L", ld)
        bpy.context.collection.objects.link(lt)
        lt.location = q @ Vector(off)
        lt.rotation_euler = (-lt.location).to_track_quat("-Z", "Y").to_euler()
    return cam


def outline_and_shrink(src, dst, px=5, col=(0.09, 0.1, 0.14)):
    img = bpy.data.images.load(src, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    alpha = a[..., 3]
    # disc dilation of alpha -> outline mask
    dil = alpha.copy()
    for dy in range(-px, px + 1):
        for dx in range(-px, px + 1):
            if dx * dx + dy * dy <= px * px + 1:
                dil = np.maximum(dil, np.roll(np.roll(alpha, dy, 0), dx, 1))
    # soft drop shadow, offset down-right
    sh = np.roll(np.roll(dil, -6, 0), 5, 1) * 0.28
    out_rgb = np.zeros((h, w, 3), np.float32)
    out_a = np.zeros((h, w), np.float32)

    def over(rgb, al):
        nonlocal out_rgb, out_a
        na = al + out_a * (1 - al)
        out_rgb = np.where(na[..., None] > 1e-6,
                           (rgb * al[..., None] + out_rgb * out_a[..., None] * (1 - al[..., None])) / np.maximum(na[..., None], 1e-6),
                           0)
        out_a = na
    over(np.broadcast_to(np.array(col, np.float32) * 0.6, (h, w, 3)), sh)
    over(np.broadcast_to(np.array(col, np.float32), (h, w, 3)), dil * 0.92)
    over(a[..., :3], alpha)
    # 2x box downsample in premultiplied space
    pm = np.concatenate([out_rgb * out_a[..., None], out_a[..., None]], axis=2)
    pm = pm.reshape(h // 2, 2, w // 2, 2, 4).mean(axis=(1, 3))
    rgb = np.where(pm[..., 3:] > 1e-6, pm[..., :3] / np.maximum(pm[..., 3:], 1e-6), 0)
    res = np.concatenate([rgb, pm[..., 3:]], axis=2)
    im = bpy.data.images.new("icon", w // 2, h // 2, alpha=True)
    im.pixels.foreach_set(res.astype(np.float32).ravel())
    im.filepath_raw = dst
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def icons(objs, empties):
    cam = icon_setup()
    scn = bpy.context.scene
    for e in empties:
        e.hide_render = True
    raw = os.path.join(bpy.app.tempdir or "/tmp", "weapon_icon_raw.png")
    only = os.environ.get("WEAPON_ICON")
    for o in objs:
        if only and o.name != only:
            continue
        for p in objs:
            p.hide_render = p is not o
        o.rotation_euler = (math.radians(-ICON_TILT[o.name]), 0, 0)
        bpy.context.view_layer.update()
        mw = o.matrix_world
        ci = cam.rotation_euler.to_matrix().inverted()
        pts = [ci @ (mw @ v.co) for v in o.data.vertices]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        c = (lo + hi) / 2
        ext = max(hi.x - lo.x, hi.y - lo.y)
        cam.data.ortho_scale = ext * 1.16
        cam.location = cam.rotation_euler.to_matrix() @ Vector((c.x, c.y, hi.z + 1.0))
        cam.data.clip_end = 5
        scn.render.filepath = raw
        bpy.ops.render.render(write_still=True)
        dst = os.path.join(OUT, o.name.lower() + ".png")
        outline_and_shrink(raw, dst)
        print("ICON", dst)
        o.rotation_euler = (0, 0, 0)
    for p in objs:
        p.hide_render = False


if __name__ == "__main__":
    objs, empties = build()
    export(objs, empties)
    if os.environ.get("WEAPON_NO_ICONS") != "1":
        icons(objs, empties)
