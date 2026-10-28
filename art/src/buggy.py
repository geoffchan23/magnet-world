# Scavenger dune buggy: open-top off-roader the toy figures can drive.
# Run: blender --background --python art/src/buggy.py
# Game units (character = 0.55 tall). Blender Z-up, the buggy faces -Y (= Godot +Z).
# Exports assets/vehicles/buggy.glb with top-level nodes:
#   Body                       - everything except wheels/steering; origin = ground centre (0,0,0).
#   WheelFL/WheelFR/WheelRL/WheelRR - tyre + rim, origin at wheel centre, axle along X.
#                                L = vehicle's left = Blender/Godot +X (facing -Y in Blender / +Z in Godot).
#   Steering                   - steering wheel; origin at its hub, local Z (Godot local Y) = column axis.
#   Seat                       - empty at the driver's hips (top of the seat cushion).
# plus a 512x512 transparent menu thumbnail assets/vehicles/buggy.png.
import bpy, bmesh, math, os, random
from mathutils import Vector, Euler, Quaternion
from mathutils.bvhtree import BVHTree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
OUT = os.path.join(ROOT, "assets", "vehicles")
os.makedirs(OUT, exist_ok=True)

WHEEL_R = 0.30
TRACK = 0.50          # wheel centre |x|
FRONT_Y = -0.70       # front axle
REAR_Y = 0.70         # rear axle
CAGE_TOP = 0.925
SEAT_HIP = Vector((0.0, 0.08, 0.37))      # top of the seat cushion, under the driver's hips
STEER_HUB = Vector((0.0, -0.215, 0.475))
STEER_AXIS = Vector((0.0, 0.6, 0.8))      # column direction, pointing up toward the driver

random.seed(7)
bpy.ops.wm.read_factory_settings(use_empty=True)


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
        b.inputs["Coat Roughness"].default_value = 0.12
    if emit:
        b.inputs["Emission Color"].default_value = lin(emit)
        b.inputs["Emission Strength"].default_value = emit_strength
    mats[name] = m
    return m


PAINT = mat("Paint", "e8742a", 0.36, coat=0.55)
RUST = mat("Rust", "6b2c12", 0.92, metal=0.15)
METAL = mat("Metal", "4a4e55", 0.36, metal=1.0)
CHROME = mat("Chrome", "f2f2f5", 0.07, metal=1.0)
RUBBER = mat("Rubber", "1c1c1e", 0.82)
SEAT = mat("Seat", "6b3a1f", 0.55, coat=0.15)
GLASS = mat("Glass", "fff1c9", 0.05, emit="ffc76b", emit_strength=2.5)
BLACK = mat("Black", "151517", 0.5)


# ---------------------------------------------------------------- object helpers
class Group:
    def __init__(self):
        self.parts = []


GROUP = None


def finish_obj(name, bm, m, smooth=True, bevel=0.0, seg=2, angle=30):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth if not callable(smooth) else smooth(p)
    me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if bevel:
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width = bevel
        bev.segments = seg
        bev.limit_method = "ANGLE"
        bev.angle_limit = math.radians(angle)
        bev.harden_normals = True
    GROUP.parts.append(ob)
    return ob


def xform(bm, rot=None, loc=None, pivot=Vector()):
    for v in bm.verts:
        p = v.co - pivot
        if rot is not None:
            p = rot @ p
        v.co = p + pivot + (Vector(loc) if loc is not None else Vector())


def shaped_box(name, corner_fn, m, bevel=0.02, seg=2):
    """Box whose 8 corners come from corner_fn(sx, sy, sz), signs in {-1, 1}."""
    bm = bmesh.new()
    vs = {}
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                vs[(sx, sy, sz)] = bm.verts.new(Vector(corner_fn(sx, sy, sz)))
    quads = [((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1)),   # bottom
             ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),       # top
             ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)),   # -Y
             ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)),       # +Y
             ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)),   # -X
             ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))]       # +X
    for q in quads:
        bm.faces.new([vs[k] for k in q])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, bevel=bevel, seg=seg)


def box(name, c, size, m, bevel=0.015, seg=2, rot=None):
    c, h = Vector(c), Vector(size) / 2
    q = Euler([math.radians(a) for a in rot]).to_matrix() if rot else None

    def fn(sx, sy, sz):
        p = Vector((sx * h.x, sy * h.y, sz * h.z))
        return c + (q @ p if q else p)
    return shaped_box(name, fn, m, bevel, seg)


def ring_verts(bm, c, axis, r, seg, phase=0.5):
    axis = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    return [bm.verts.new(c + (u * math.cos(2 * math.pi * (i + phase) / seg) + v * math.sin(2 * math.pi * (i + phase) / seg)) * r)
            for i in range(seg)]


def cyl(name, p0, p1, r, m, seg=12, r1=None, caps=(True, True), bevel=0.0, smooth_sides=True):
    """Cylinder (or cone with r1) from p0 to p1; smooth sides, flat caps."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    bm = bmesh.new()
    a = ring_verts(bm, p0, axis, r, seg)
    b = ring_verts(bm, p1, axis, r1 if r1 is not None else r, seg)
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new([a[i], a[j], b[j], b[i]])
    if caps[0]:
        bm.faces.new(a[::-1])
    if caps[1]:
        bm.faces.new(b)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=(lambda p: smooth_sides and len(p.vertices) == 4), bevel=bevel, seg=1)


def ring(name, c, axis, r_in, r_out, depth, m, seg=20, bevel=0.0, sides=(0, 1, 2, 3)):
    """Flat annulus (washer) of the given depth along axis, centred at c."""
    c, axis = Vector(c), Vector(axis).normalized()
    bm = bmesh.new()
    rings = [ring_verts(bm, c + axis * (s * depth / 2), axis, r, seg)
             for (s, r) in ((-1, r_out), (1, r_out), (1, r_in), (-1, r_in))]
    for k in sides:  # 0 outer rim, 1 front face, 2 bore, 3 back face
        A, B = rings[k], rings[(k + 1) % 4]
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new([A[i], A[j], B[j], B[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, bevel=bevel, seg=1, angle=50)


def disc(name, c, normal, r, m, seg=16):
    """Flat round face (one-sided, facing along normal)."""
    bm = bmesh.new()
    vs = ring_verts(bm, Vector(c), normal, r, seg)
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(Vector(normal)) < 0:
        f.normal_flip()
    return finish_obj(name, bm, m, smooth=False)


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


def tube(name, pts, r, m, sides=8, rad=0.09, n=3):
    """Bent tube swept along a filleted polyline (roll-cage style)."""
    pts = fillet(pts, rad, n) if rad else [Vector(p) for p in pts]
    bm = bmesh.new()
    rings, u = [], None
    for i, p in enumerate(pts):
        if i == 0:
            t = (pts[1] - pts[0]).normalized()
        elif i == len(pts) - 1:
            t = (pts[-1] - pts[-2]).normalized()
        else:
            t = ((pts[i + 1] - p).normalized() + (p - pts[i - 1]).normalized()).normalized()
        if u is None:
            ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            u = t.cross(ref).normalized()
        else:
            u = (u - t * t.dot(u)).normalized()
        v = t.cross(u)
        rings.append([bm.verts.new(p + (u * math.cos(2 * math.pi * k / sides) + v * math.sin(2 * math.pi * k / sides)) * r)
                      for k in range(sides)])
    for A, B in zip(rings, rings[1:]):
        for k in range(sides):
            j = (k + 1) % sides
            bm.faces.new([A[k], A[j], B[j], B[k]])
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=lambda p: len(p.vertices) == 4)


def patch(name, c, normal, size, m=None, n=8, aspect=1.0, spin=0.0):
    """Irregular flat blob just proud of a surface (rust spots, scuffs)."""
    normal = Vector(normal).normalized()
    c = Vector(c) + normal * 0.004
    ref = Vector((0, 0, 1)) if abs(normal.z) < 0.9 else Vector((1, 0, 0))
    u = normal.cross(ref).normalized()
    v = normal.cross(u).normalized()
    q = Quaternion(normal, spin)
    u, v = q @ u, q @ v
    bm = bmesh.new()
    vs = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = size * (0.6 + 0.4 * random.random())
        vs.append(bm.verts.new(c + u * math.cos(a) * rr * aspect + v * math.sin(a) * rr))
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(normal) < 0:
        f.normal_flip()
    return finish_obj(name, bm, m or RUST, smooth=False)


def bolt(c, normal, r=0.011, m=None):
    normal = Vector(normal).normalized()
    c = Vector(c)
    return cyl("Bolt", c - normal * 0.004, c + normal * 0.009, r, m or CHROME, seg=4, caps=(False, True), r1=r * 0.8)


def plate(name, c, size, rot, m, bolt_inset=0.022):
    """Scrap armour plate (size = x,y,z with the thin axis local) with a bolt in each corner."""
    box(name, c, size, m, bevel=0.006, seg=1, rot=rot)
    q = Euler([math.radians(a) for a in rot]).to_matrix()
    h = Vector(size) / 2
    thin = min(range(3), key=lambda i: size[i])
    others = [i for i in range(3) if i != thin]
    nrm = Vector((0, 0, 0))
    nrm[thin] = 1
    for s0, s1 in ((-1, -1), (1, 1)):
        if True:
            p = Vector((0, 0, 0))
            p[others[0]] = s0 * (h[others[0]] - bolt_inset)
            p[others[1]] = s1 * (h[others[1]] - bolt_inset)
            sign = 1 if (Vector(c) + q @ (p + nrm * h[thin])).length >= (Vector(c) + q @ (p - nrm * h[thin])).length else -1
            p[thin] = sign * h[thin]
            bolt(Vector(c) + q @ p, q @ (nrm * sign))


def collapse(name, group, loc=(0, 0, 0)):
    """Apply modifiers and join a group's parts into one mesh object."""
    if os.environ.get("BUGGY_TRIS"):
        dg = bpy.context.evaluated_depsgraph_get()
        acc = {}
        for o in group.parts:
            k = o.name.split(".")[0]
            acc[k] = acc.get(k, 0) + sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons)
        print("TRIS", name, sorted(acc.items(), key=lambda kv: -kv[1]))
    bpy.ops.object.select_all(action="DESELECT")
    for o in group.parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = group.parts[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    me = ob.data
    # merge materials that got duplicated slots on join
    bpy.ops.object.material_slot_remove_unused()
    ob.location = loc
    return ob


# ---------------------------------------------------------------- wheel
TREAD_STEPS = 16


def build_tyre(name, scale=1.0, m=RUBBER, knobs=True):
    prof = [(-0.094, 0.176), (-0.112, 0.214), (-0.110, 0.250), (-0.088, 0.276),
            (0.0, 0.281), (0.088, 0.276), (0.110, 0.250), (0.112, 0.214), (0.094, 0.176)]
    bm = bmesh.new()
    vs = [bm.verts.new((x * scale, 0, r * scale)) for x, r in prof]
    es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(1, 0, 0), dvec=(0, 0, 0),
                   angle=2 * math.pi, steps=TREAD_STEPS, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # make sure normals point away from the axle
    for f in bm.faces:
        c = f.calc_center_median()
        radial = Vector((0, c.y, c.z))
        if f.normal.dot(radial) < 0 and abs(c.x) < 0.09 * scale:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
            break
    # checkerboard knobs on the two tread rows + shoulder lugs
    sel = []
    step = 2 * math.pi / TREAD_STEPS
    for f in bm.faces:
        c = f.calc_center_median()
        r = math.hypot(c.y, c.z)
        k = int(math.floor((math.atan2(c.z, c.y) % (2 * math.pi)) / step))
        side = 1 if c.x > 0 else 0
        if knobs and r > 0.272 * scale and (k + side) % 2 == 0:
            sel.append(f)
    ext = bmesh.ops.extrude_discrete_faces(bm, faces=sel)
    for f in ext["faces"]:
        f.normal_update()
        n = f.normal.copy()
        c = f.calc_center_median()
        for v in f.verts:
            v.co = c + (v.co - c) * 0.86 + n * 0.024 * scale
    bm.normal_update()
    ob = finish_obj(name, bm, m, smooth=True)
    return ob


def build_wheel(name, right, spare=False):
    global GROUP
    GROUP = Group()
    s = 0.92 if spare else 1.0
    tyre = build_tyre(name + "_Tyre", s, knobs=not spare)
    X = Vector((1, 0, 0))
    # rim: inner + outer dish discs inside the tyre, chrome beadlock ring, black spokes, chrome hub
    disc(name + "_Dish", (0.07 * s, 0, 0), X, 0.182 * s, METAL, seg=16)
    disc(name + "_Back", (-0.082 * s, 0, 0), -X, 0.182 * s, METAL, seg=12)
    if not spare:
        ring(name + "_Beadlock", (0.078 * s, 0, 0), X, 0.135 * s, 0.19 * s, 0.022 * s, CHROME, seg=16, sides=(1, 2))
    for i in range(5 if not spare else 0):  # chunky spokes
        a = 2 * math.pi * i / 5
        q = Euler((a, 0, 0)).to_matrix()
        box("Spoke", q @ Vector((0.072 * s, 0, 0.1 * s)), (0.026, 0.04 * s, 0.1 * s), BLACK, bevel=0.0,
            rot=(math.degrees(a), 0, 0))
    cyl(name + "_Hub", (0.06 * s, 0, 0), (0.1 * s, 0, 0), 0.058 * s, CHROME, seg=10, r1=0.05 * s)
    cyl(name + "_Cap", (0.1 * s, 0, 0), (0.112 * s, 0, 0), 0.026 * s, BLACK, seg=8, caps=(False, True))
    for o in GROUP.parts:
        if right:
            o.data.transform(Euler((0, 0, math.pi)).to_matrix().to_4x4())
        if spare:
            o.data.transform(Euler((0, 0, math.pi / 2)).to_matrix().to_4x4())
    ob = collapse(name, GROUP)
    if not spare:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40), keep_sharp_edges=True)
    return ob


# ---------------------------------------------------------------- body
def hood_z(y):
    """Top of the bonnet: 0.48 at the nose (y=-1.0) rising to 0.56 at the dash (y=-0.38)."""
    return 0.48 + (y + 1.0) / 0.62 * 0.08


HOOD_TILT = math.degrees(math.atan2(0.08, 0.62))


def fender(name, cx, cy, m, a0=0.28, a1=2.86, steps=6):
    """Arched mudguard over a wheel: a bent plate with a lip."""
    r_in, r_out = 0.345, 0.375
    x0, x1 = cx - 0.135, cx + 0.135
    bm = bmesh.new()
    rows = []
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / steps
        d = Vector((0, -math.cos(a), math.sin(a)))
        c = Vector((0, cy, WHEEL_R))
        rows.append([bm.verts.new(c + d * r + Vector((x, 0, 0))) for (x, r) in
                     ((x0, r_in), (x1, r_in), (x1, r_out), (x0, r_out))])
    for A, B in zip(rows, rows[1:]):
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new([A[k], A[j], B[j], B[k]])
    bm.faces.new(rows[0][::-1])
    bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, bevel=0.008, seg=1, angle=40)


def build_body():
    global GROUP
    GROUP = Group()

    # --- chassis / skid pan
    box("Skid", (0, 0.0, 0.205), (0.78, 1.92, 0.07), BLACK, bevel=0.02, seg=1)
    box("SkidNose", (0, -0.98, 0.25), (0.6, 0.12, 0.08), METAL, bevel=0.015, seg=1, rot=(-25, 0, 0))

    # --- bonnet (sloped), with grille and headlights
    def hood(sx, sy, sz):
        y = -1.0 if sy < 0 else -0.38
        x = sx * (0.335 if sy < 0 else 0.365)
        z = 0.24 if sz < 0 else hood_z(y)
        return (x, y, z)
    shaped_box("Hood", hood, PAINT, bevel=0.035, seg=2)
    box("Grille", (0, -1.004, 0.36), (0.34, 0.03, 0.16), BLACK, bevel=0.01, seg=1)
    for i in range(3):
        box("Slat", (0, -1.02, 0.31 + i * 0.05), (0.32, 0.012, 0.014), METAL, bevel=0.0)
    for s in (-1, 1):
        cyl("LampBezel", (s * 0.255, -0.985, 0.405), (s * 0.255, -1.035, 0.405), 0.062, CHROME, seg=10, caps=(False, True))
        cyl("Lamp", (s * 0.255, -1.03, 0.405), (s * 0.255, -1.044, 0.405), 0.048, GLASS, seg=10, r1=0.04, caps=(False, True))

    # --- dash + cowl
    box("Dash", (0, -0.36, 0.52), (0.74, 0.1, 0.13), BLACK, bevel=0.02, seg=1)
    for s in ():
        cyl("Gauge", (s * 0.12, -0.31, 0.535), (s * 0.12, -0.30, 0.545), 0.03, CHROME, seg=6, caps=(False, True))

    # --- cockpit tub side walls + floor
    for s in (-1, 1):
        def wall(sx, sy, sz, s=s):
            x = s * (0.37 if sx * s < 0 else 0.465)
            y = -0.38 if sy < 0 else 0.42
            if sz < 0:
                z = 0.2
            else:
                z = 0.52 if sy < 0 else 0.5
            return (x, y, z)
        shaped_box("SideWall", wall, PAINT, bevel=0.03, seg=1)
        box("Sill", (s * 0.47, 0.02, 0.22), (0.05, 0.86, 0.06), BLACK, bevel=0.0)
    box("Floor", (0, 0.02, 0.255), (0.76, 0.8, 0.03), METAL, bevel=0.0)

    # --- rear bulkhead + engine deck
    box("Bulkhead", (0, 0.40, 0.42), (0.76, 0.05, 0.4), METAL, bevel=0.012, seg=1)
    box("RearDeck", (0, 0.66, 0.33), (0.74, 0.5, 0.22), PAINT, bevel=0.03, seg=2)
    box("Tail", (0, 0.93, 0.33), (0.6, 0.08, 0.2), METAL, bevel=0.015, seg=1)
    for s in (-1, 1):
        box("TailLight", (s * 0.22, 0.972, 0.38), (0.08, 0.01, 0.04), GLASS, bevel=0.0)

    # engine: block, rocker covers, air cleaner, chrome stacks
    box("Engine", (0, 0.66, 0.5), (0.3, 0.32, 0.14), METAL, bevel=0.015, seg=1)
    for s in (-1, 1):
        box("Rocker", (s * 0.11, 0.66, 0.585), (0.08, 0.3, 0.05), CHROME, bevel=0.0)
    cyl("AirCleaner", (0, 0.66, 0.57), (0, 0.66, 0.64), 0.085, CHROME, seg=12, caps=(False, True))
    cyl("AirCleanerLid", (0, 0.66, 0.64), (0, 0.66, 0.655), 0.07, BLACK, seg=12, caps=(False, True))
    for s in (-1, 1):
        tube("Exhaust", [(s * 0.15, 0.78, 0.5), (s * 0.24, 0.84, 0.5), (s * 0.25, 0.86, 0.80)], 0.024, CHROME,
             sides=6, rad=0.06, n=2)
        cyl("ExhaustTip", (s * 0.25, 0.86, 0.78), (s * 0.25, 0.86, 0.83), 0.03, BLACK, seg=8)

    # jerry cans either side of the engine
    for s, m in ((-1, METAL), (1, RUST)):
        x = s * 0.27
        box("JerryCan", (x, 0.62, 0.55), (0.1, 0.2, 0.22), m, bevel=0.012, seg=1)
        box("JerryRib", (x + s * 0.052, 0.62, 0.55), (0.01, 0.14, 0.16), m, bevel=0.0)
        box("JerryHandle", (x, 0.56, 0.68), (0.03, 0.08, 0.03), BLACK, bevel=0.0)
        cyl("JerryCap", (x, 0.69, 0.66), (x, 0.70, 0.70), 0.018, BLACK, seg=6, caps=(False, True))
        box("Strap", (x, 0.62, 0.55), (0.11, 0.025, 0.226), BLACK, bevel=0.0)

    # spare tyre on a bracket off the tail
    box("SpareBracket", (0, 0.97, 0.52), (0.12, 0.08, 0.12), METAL, bevel=0.01, seg=1)

    # --- mudguards: factory orange at the front, a scavenged rusty pair at the back
    for s in (-1, 1):
        fender("FenderF", s * TRACK, FRONT_Y, PAINT)
        fender("FenderR", s * TRACK, REAR_Y, RUST)
        box("FenderStrutF", (s * 0.39, FRONT_Y, 0.5), (0.06, 0.06, 0.12), BLACK, bevel=0.0)
        box("FenderStrutR", (s * 0.39, REAR_Y, 0.47), (0.06, 0.06, 0.12), BLACK, bevel=0.0)
        box("MudFlap", (s * TRACK, 1.04, 0.255), (0.2, 0.015, 0.29), BLACK, bevel=0.0)

    # --- bull bar + winch
    tube("Bumper", [(-0.38, -0.96, 0.28), (-0.38, -1.1, 0.28), (0.38, -1.1, 0.28), (0.38, -0.96, 0.28)], 0.03, CHROME, sides=6, n=2,
         rad=0.07)
    tube("BullHoop", [(-0.17, -1.1, 0.28), (-0.17, -1.13, 0.62), (0.17, -1.13, 0.62), (0.17, -1.1, 0.28)], 0.026,
         CHROME, sides=6, rad=0.08, n=2)
    for s in (-1, 1):
        tube("BullBrace", [(s * 0.17, -1.13, 0.58), (s * 0.15, -0.95, 0.495)], 0.02, CHROME, rad=0)
    box("WinchPlate", (0, -1.08, 0.31), (0.3, 0.1, 0.03), METAL, bevel=0.006, seg=1)
    cyl("WinchDrum", (-0.1, -1.08, 0.375), (0.1, -1.08, 0.375), 0.045, RUST, seg=12)
    for s in (-1, 1):
        box("WinchEnd", (s * 0.12, -1.08, 0.375), (0.04, 0.1, 0.11), BLACK, bevel=0.0)
    box("WinchMotor", (0.0, -1.035, 0.43), (0.2, 0.05, 0.05), BLACK, bevel=0.012, seg=1)
    box("Fairlead", (0, -1.135, 0.36), (0.1, 0.02, 0.05), METAL, bevel=0.005, seg=1)
    tube("WinchHook", [(0, -1.14, 0.36), (0, -1.16, 0.3), (0, -1.18, 0.26), (0.025, -1.17, 0.24), (0.035, -1.15, 0.265)],
         0.008, CHROME, sides=4, rad=0.02, n=1)

    # --- seat (low-back bucket) + steering column
    box("SeatBase", (0, SEAT_HIP.y + 0.02, 0.29), (0.26, 0.24, 0.06), BLACK, bevel=0.01, seg=1)
    box("Cushion", (0, SEAT_HIP.y + 0.0, SEAT_HIP.z - 0.035), (0.34, 0.3, 0.07), SEAT, bevel=0.025, seg=1)
    box("SeatBack", (0, SEAT_HIP.y + 0.175, SEAT_HIP.z + 0.075), (0.36, 0.07, 0.2), SEAT, bevel=0.025, seg=1,
        rot=(-14, 0, 0))
    for s in (-1, 1):
        box("Bolster", (s * 0.18, SEAT_HIP.y + 0.08, SEAT_HIP.z + 0.01), (0.05, 0.26, 0.11), SEAT, bevel=0.0)
    col_end = STEER_HUB - STEER_AXIS * 0.03
    cyl("Column", col_end - STEER_AXIS * 0.24, col_end, 0.018, BLACK, seg=6, caps=(False, True))

    # --- roll cage (gunmetal tube)
    T = CAGE_TOP
    for s in (-1, 1):
        tube("CageSide", [(s * 0.43, -0.37, 0.53), (s * 0.39, -0.13, T), (s * 0.39, 0.41, T), (s * 0.43, 0.41, 0.49)],
             0.026, METAL, rad=0.11, n=2)
        tube("CageBrace", [(s * 0.385, 0.41, T - 0.03), (s * 0.3, 0.86, 0.43)], 0.022, METAL, rad=0)
    tube("CageFront", [(-0.39, -0.13, T), (0.39, -0.13, T)], 0.026, METAL, rad=0)
    tube("CageRear", [(-0.39, 0.41, T), (0.39, 0.41, T)], 0.026, METAL, rad=0)
    tube("CageDiag", [(-0.42, 0.41, 0.5), (0.38, 0.41, T - 0.02)], 0.022, METAL, rad=0)

    # roof light bar
    box("LightBar", (0, -0.13, T + 0.055), (0.62, 0.07, 0.065), BLACK, bevel=0.012, seg=1)
    for s in (-1, 1):
        box("LightMount", (s * 0.2, -0.13, T + 0.02), (0.03, 0.03, 0.04), BLACK, bevel=0.0)
    for x in (-0.225, -0.075, 0.075, 0.225):
        box("BarLamp", (x, -0.166, T + 0.055), (0.12, 0.008, 0.045), GLASS, bevel=0.0)

    # --- scrap armour plates bolted on
    for s in (-1, 1):
        plate("ArmourA", (s * 0.48, -0.17, 0.37), (0.02, 0.32, 0.2), (0, 0, 0) if s > 0 else (0, 0, 0),
              RUST if s > 0 else METAL)
        plate("ArmourB", (s * 0.482, 0.21, 0.33), (0.02, 0.26, 0.17), (6 * s, 0, 0), METAL if s > 0 else RUST)
    y = -0.72
    plate("HoodPlate", (-0.1, y, hood_z(y) + 0.012), (0.3, 0.28, 0.018), (HOOD_TILT, 0, 8), METAL)

    return collapse("Body", GROUP)


def build_steering():
    global GROUP
    GROUP = Group()
    # wheel in the local XY plane, axis = local Z
    bm = bmesh.new()
    R, r, seg_a, seg_b = 0.075, 0.013, 12, 5
    rows = []
    for i in range(seg_a):
        a = 2 * math.pi * i / seg_a
        c = Vector((math.cos(a) * R, math.sin(a) * R, 0))
        out = Vector((math.cos(a), math.sin(a), 0))
        rows.append([bm.verts.new(c + out * math.cos(2 * math.pi * j / seg_b) * r +
                                  Vector((0, 0, 1)) * math.sin(2 * math.pi * j / seg_b) * r) for j in range(seg_b)])
    for i in range(seg_a):
        for j in range(seg_b):
            bm.faces.new([rows[i][j], rows[(i + 1) % seg_a][j], rows[(i + 1) % seg_a][(j + 1) % seg_b],
                          rows[i][(j + 1) % seg_b]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    finish_obj("Rim", bm, BLACK)
    for a in (90, 210, 330):
        q = Euler((0, 0, math.radians(a))).to_matrix()
        box("Spoke", q @ Vector((0.04, 0, 0)), (0.07, 0.018, 0.01), METAL, bevel=0.0, rot=(0, 0, a))
    cyl("Hub", (0, 0, -0.012), (0, 0, 0.018), 0.026, CHROME, seg=8)
    ob = collapse("Steering", GROUP)
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(STEER_AXIS.normalized())
    ob.location = STEER_HUB
    return ob


RUST_SPOTS = [  # (ray origin, ray direction, radius, aspect, spin) - rust blooms and grime
    ((0.22, -0.86, 1.2), (0, 0, -1), 0.075, 1.6, 0.4),     # bonnet, nose left
    ((-0.25, -0.47, 1.2), (0, 0, -1), 0.05, 1.3, 1.2),     # bonnet, by the dash
    ((0.56, -0.66, 1.2), (0, 0, -1), 0.06, 1.5, 0.2),      # left front mudguard top
    ((-0.47, -1.5, 0.52), (0, 1, 0), 0.05, 1.4, 0.9),      # right front mudguard nose
    ((-0.6, -0.48, 1.0), (0.3, 0.3, -1), 0.045, 1.2, 0.0),  # right front mudguard tail
    ((1.0, -0.86, 0.32), (-1, 0, 0), 0.055, 1.8, 0.2),     # bonnet flank left
    ((-1.0, -0.6, 0.30), (1, 0, 0), 0.05, 1.6, -0.3),      # bonnet flank right
    ((1.0, 0.25, 0.29), (-1, 0, 0), 0.045, 1.5, 0.1),      # side armour, left
    ((-1.0, -0.2, 0.43), (1, 0, 0), 0.04, 1.7, 0.4),       # side armour, right
    ((1.0, 0.8, 0.30), (-1, 0, 0), 0.05, 1.7, 0.3),        # rear deck flank left
    ((-1.0, 0.62, 0.31), (1, 0, 0), 0.04, 1.4, -0.2),      # rear deck flank right
    ((-0.12, 0.88, 1.2), (0, 0, -1), 0.045, 1.4, 0.7),     # rear deck top
    ((0.3, -1.5, 0.35), (0, 1, 0), 0.035, 1.2, 0.0),       # nose, under the left lamp
]


def rust_spots(body):
    """Rust blooms projected onto the finished body so they hug curved panels."""
    global GROUP
    GROUP = Group()
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    for (o, d, size, aspect, spin) in RUST_SPOTS:
        hit, nrm, _, _ = bvh.ray_cast(Vector(o), Vector(d).normalized())
        if hit is None:
            print("RUST MISS", o)
            continue
        ref = Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((1, 0, 0))
        u = nrm.cross(ref).normalized()
        v = nrm.cross(u).normalized()
        q = Quaternion(nrm, spin)
        u, v = q @ u, q @ v
        bm = bmesh.new()
        def project(p):
            h = bvh.ray_cast(p + nrm * 0.05, -nrm, 0.12)
            if h[0] is None:
                return None
            return h[0] + h[1] * 0.004
        centre = bm.verts.new(project(hit) or hit + nrm * 0.004)
        rim = []
        n = 10
        for i in range(n):
            a = 2 * math.pi * i / n
            rr = size * (0.55 + 0.45 * random.random())
            p = project(hit + u * math.cos(a) * rr * aspect + v * math.sin(a) * rr)
            if p is not None:
                rim.append(bm.verts.new(p))
        for a, b in zip(rim, rim[1:] + rim[:1]):
            f = bm.faces.new([centre, a, b])
            f.normal_update()
            if f.normal.dot(nrm) < 0:
                f.normal_flip()
        finish_obj("Rust", bm, RUST, smooth=False)
    spots = collapse("RustSpots", GROUP)
    bpy.ops.object.select_all(action="DESELECT")
    spots.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()


def build():
    body = build_body()
    rust_spots(body)
    wheels = []
    for name, x, y in (("WheelFL", TRACK, FRONT_Y), ("WheelFR", -TRACK, FRONT_Y),
                       ("WheelRL", TRACK, REAR_Y), ("WheelRR", -TRACK, REAR_Y)):
        w = build_wheel(name, right=x < 0)
        w.location = (x, y, WHEEL_R)
        wheels.append(w)
    # spare: joined into the Body
    spare = build_wheel("Spare", right=False, spare=True)
    spare.location = (0, 1.04, 0.53)
    bpy.ops.object.select_all(action="DESELECT")
    spare.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    steering = build_steering()
    seat = bpy.data.objects.new("Seat", None)
    seat.empty_display_type = "ARROWS"
    seat.empty_display_size = 0.1
    seat.location = SEAT_HIP
    bpy.context.collection.objects.link(seat)
    return [body, *wheels, steering, seat]


def godot(v):
    return (round(v[0], 3), round(v[2], 3), round(-v[1], 3))


def export(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "buggy.glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True)
    tris = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs if o.type == "MESH"}
    print("EXPORTED buggy.glb", tris, "total", sum(tris.values()))
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    print("BBOX blender", tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi))
    for o in objs:
        print("NODE", o.name, "godot", godot(o.location))


def thumbnail(objs):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.samples = 96
    scn.cycles.use_denoising = True
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scn.render.resolution_x = scn.render.resolution_y = 512
    scn.render.film_transparent = True
    world = bpy.data.worlds.new("Studio")
    scn.world = world
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.62, 0.7, 0.82, 1)
    bg.inputs["Strength"].default_value = 0.55
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.is_shadow_catcher = True
    for loc, energy, size, col in [((3.4, -2.2, 3.8), 320, 2.5, (1, 0.95, 0.88)),
                                   ((-2.5, -3.5, 1.6), 110, 3.0, (0.8, 0.88, 1.0)),
                                   ((0.5, 3.5, 2.8), 260, 2.0, (1, 0.95, 0.9))]:
        bpy.ops.object.light_add(type="AREA", location=loc)
        lt = bpy.context.active_object
        lt.data.energy = energy
        lt.data.size = size
        lt.data.color = col
        lt.rotation_euler = (Vector((0, 0, 0.4)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.object.camera_add(location=(2.55, -3.25, 1.75))
    cam = bpy.context.active_object
    cam.rotation_euler = (Vector((0.0, -0.1, 0.45)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 57
    scn.camera = cam
    scn.render.filepath = os.path.join(OUT, "buggy.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scn.render.filepath)


if __name__ == "__main__":
    objs = build()
    export(objs)
    if os.environ.get("BUGGY_NO_RENDER") != "1":
        thumbnail(objs)
