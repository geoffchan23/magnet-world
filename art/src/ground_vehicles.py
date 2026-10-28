# Ground vehicles for Magnet World: fire truck, police car, garbage truck, race car,
# monster truck and ice cream truck. Same conventions as art/src/buggy.py.
# Run: blender --background --python art/src/ground_vehicles.py [-- fire_truck police_car ...]
#   (no names = build all six)
# Game units (character = 0.55 tall). Blender Z-up, every vehicle faces -Y (= Godot +Z),
# the vehicle's left = Blender/Godot +X.
# Each vehicle exports assets/vehicles/<name>.glb with top-level nodes (no parenting):
#   Body                    - everything that doesn't move; origin = ground centre (0,0,0).
#   WheelFL/FR/RL/RR (+ML/MR on a middle axle) - tyre + rim, origin at the hub, axle along X.
#   Steering                - steering wheel; origin at its hub, local Z (Godot local +Y) = column axis.
#   Seat                    - empty at the top of the driver's seat cushion.
#   LightBar                - (fire truck, police car) roof light bar, emissive SirenRed / SirenBlue.
#   Cannon, Nozzle          - (fire truck) water cannon, origin at its pivot; Nozzle empty at the tip,
#                             its local Godot +Z (Blender local -Y) points along the water stream.
# plus a 512x512 transparent Items-menu thumbnail assets/vehicles/<name>.png.
# Env: VEH_PREVIEW=<dir> also renders side / 3-4 / rear views with a seated figure into <dir>.
#      VEH_NO_RENDER=1 skips the thumbnail.  VEH_TRIS=1 prints a per-part tri breakdown.
import bpy, bmesh, math, os, random, sys
from mathutils import Vector, Euler, Quaternion, Matrix
from mathutils.bvhtree import BVHTree

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
OUT = os.path.join(ROOT, "assets", "vehicles")
os.makedirs(OUT, exist_ok=True)
PREVIEW = os.environ.get("VEH_PREVIEW")
FONT_DIR = "/System/Library/Fonts/Supplemental"
X = Vector((1, 0, 0))
Y = Vector((0, 1, 0))
Z = Vector((0, 0, 1))
pi = math.pi


# ================================================================= materials
def lin(hexstr):
    out = []
    for i in (0, 2, 4):
        c = int(hexstr[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


mats = {}


def mat(name, color, rough, metal=0.0, coat=0.0, emit=None, emit_strength=0.0, alpha=1.0):
    if name in mats:
        return mats[name]
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = lin(color)
    m.diffuse_color = lin(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.12
    if emit:
        b.inputs["Emission Color"].default_value = lin(emit)
        b.inputs["Emission Strength"].default_value = emit_strength
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    mats[name] = m
    return m


def common_mats():
    """Shared trim materials; each vehicle adds its own paints."""
    g = globals()
    g["CHROME"] = mat("Chrome", "f2f2f5", 0.07, metal=1.0)
    g["METAL"] = mat("Metal", "4a4e55", 0.36, metal=1.0)
    g["ALU"] = mat("Aluminium", "c3c8cf", 0.28, metal=1.0)
    g["RUBBER"] = mat("Rubber", "1c1c1e", 0.82)
    g["BLACK"] = mat("Black", "151517", 0.5)
    g["RUST"] = mat("Rust", "6b2c12", 0.92, metal=0.15)
    g["GRIME"] = mat("Grime", "3b3226", 0.95)
    g["WINDOW"] = mat("Window", "a9c8d8", 0.04, alpha=0.28)
    g["HEADLIGHT"] = mat("Headlight", "fff1c9", 0.05, emit="ffc76b", emit_strength=2.5)
    g["TAILLIGHT"] = mat("TailLight", "d4142a", 0.15, emit="ff1a2e", emit_strength=1.6)
    g["AMBER"] = mat("Amber", "ffa31a", 0.15, emit="ff8a00", emit_strength=1.2)
    g["SEATM"] = mat("Seat", "2e2f33", 0.6, coat=0.1)


# ================================================================= object helpers
class Group:
    def __init__(self):
        self.parts = []


GROUP = None


def new_group():
    global GROUP
    GROUP = Group()
    return GROUP


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


def shaped_box(name, corner_fn, m, bevel=0.02, seg=2, angle=30):
    """Box whose 8 corners come from corner_fn(sx, sy, sz), signs in {-1, 1}."""
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
    return finish_obj(name, bm, m, bevel=bevel, seg=seg, angle=angle)


def box(name, c, size, m, bevel=0.015, seg=2, rot=None):
    c, h = Vector(c), Vector(size) / 2
    q = Euler([math.radians(a) for a in rot]).to_matrix() if rot else None

    def fn(sx, sy, sz):
        p = Vector((sx * h.x, sy * h.y, sz * h.z))
        return c + (q @ p if q else p)
    return shaped_box(name, fn, m, bevel, seg)


def bbox(name, lo, hi, m, bevel=0.015, seg=2):
    """Axis-aligned box from two corners."""
    lo, hi = Vector(lo), Vector(hi)
    return box(name, (lo + hi) / 2, hi - lo, m, bevel=bevel, seg=seg)


def beam(name, p0, p1, w, d, m, side=X, bevel=0.01, seg=1):
    """Box swept from p0 to p1; w along `side`, d along the third axis."""
    p0, p1 = Vector(p0), Vector(p1)
    a = (p1 - p0).normalized()
    s = (Vector(side) - a * a.dot(Vector(side))).normalized()
    t = a.cross(s).normalized()

    def fn(sx, sy, sz):
        return (p0 if sz < 0 else p1) + s * sx * w / 2 + t * sy * d / 2
    return shaped_box(name, fn, m, bevel, seg)


def ring_verts(bm, c, axis, r, seg, phase=0.5):
    axis = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    return [bm.verts.new(c + (u * math.cos(2 * pi * (i + phase) / seg) + v * math.sin(2 * pi * (i + phase) / seg)) * r)
            for i in range(seg)]


def cyl(name, p0, p1, r, m, seg=12, r1=None, caps=(True, True), bevel=0.0, smooth_sides=True, phase=0.5):
    """Cylinder (or cone with r1) from p0 to p1; smooth sides, flat caps."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    bm = bmesh.new()
    a = ring_verts(bm, p0, axis, r, seg, phase)
    b = ring_verts(bm, p1, axis, r1 if r1 is not None else r, seg, phase)
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


def disc(name, c, normal, r, m, seg=16, phase=0.5):
    """Flat round face (one-sided, facing along normal)."""
    bm = bmesh.new()
    vs = ring_verts(bm, Vector(c), normal, r, seg, phase)
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(Vector(normal)) < 0:
        f.normal_flip()
    return finish_obj(name, bm, m, smooth=False)


def ball(name, c, r, m, seg=10, rings_=6, squash=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings_, radius=r)
    for v in bm.verts:
        v.co.z *= squash
        v.co += Vector(c)
    return finish_obj(name, bm, m)


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


def tube(name, pts, r, m, sides=8, rad=0.09, n=3, caps=True):
    """Bent tube swept along a filleted polyline."""
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
        rings.append([bm.verts.new(p + (u * math.cos(2 * pi * k / sides) + v * math.sin(2 * pi * k / sides)) * r)
                      for k in range(sides)])
    for A, B in zip(rings, rings[1:]):
        for k in range(sides):
            j = (k + 1) % sides
            bm.faces.new([A[k], A[j], B[j], B[k]])
    if caps:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=lambda p: len(p.vertices) == 4)


def bolt(c, normal, r=0.011, m=None, seg=4):
    normal = Vector(normal).normalized()
    c = Vector(c)
    return cyl("Bolt", c - normal * 0.004, c + normal * 0.009, r, m or CHROME, seg=seg, caps=(False, True), r1=r * 0.8)


def prism(name, pts, x0, x1, m, bevel=0.02, seg=2, angle=30):
    """Side profile [(y, z), ...] extruded across X from x0 to x1 (concave outlines are fine)."""
    bm = bmesh.new()
    A = [bm.verts.new((x0, y, z)) for y, z in pts]
    B = [bm.verts.new((x1, y, z)) for y, z in pts]
    n = len(pts)
    bm.faces.new(A)
    bm.faces.new(B[::-1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([A[i], A[j], B[j], B[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, bevel=bevel, seg=seg, angle=angle)


def xprism(name, pts, y0, y1, m, bevel=0.02, seg=2, angle=30):
    """Front profile [(x, z), ...] extruded along Y from y0 to y1."""
    bm = bmesh.new()
    A = [bm.verts.new((x, y0, z)) for x, z in pts]
    B = [bm.verts.new((x, y1, z)) for x, z in pts]
    n = len(pts)
    bm.faces.new(A)
    bm.faces.new(B[::-1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([A[i], A[j], B[j], B[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, bevel=bevel, seg=seg, angle=angle)


def loft(name, sections, m, bevel=0.0, seg=2, angle=30, caps=True, smooth=True):
    """Join closed loops of equal vertex count (lists of 3D points) with quads."""
    bm = bmesh.new()
    rows = [[bm.verts.new(Vector(p)) for p in s] for s in sections]
    n = len(sections[0])
    for A, B in zip(rows, rows[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new([A[i], A[j], B[j], B[i]])
    if caps:
        bm.faces.new(rows[0][::-1])
        bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, smooth=smooth, bevel=bevel, seg=seg, angle=angle)


def rrect(cx, cz, hw, hh, r, n=2):
    """Rounded rectangle loop in the (x, z) plane, CCW, 4*(n+1) points."""
    pts = []
    for (sx, sz, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ccx, ccz = cx + sx * (hw - r), cz + sz * (hh - r)
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((ccx + math.cos(a) * r, ccz + math.sin(a) * r))
    return pts


def arch(cy, cz, r, zb, n=8):
    """Wheel-arch cut-out points along a body's bottom edge, front (-Y) to back."""
    s = max(-1.0, min(1.0, (zb - cz) / r))
    a0, a1 = pi - math.asin(s), math.asin(s)
    return [(cy + math.cos(a0 + (a1 - a0) * k / n) * r, cz + math.sin(a0 + (a1 - a0) * k / n) * r)
            for k in range(n + 1)]


def arc_band(name, cy, cz, r_in, r_out, x0, x1, m, a0=0.0, a1=pi, steps=8, bevel=0.006):
    """Arched band around a wheel (fender lip / mudguard), angles from the front (a=0 is +Y side)."""
    bm = bmesh.new()
    rows = []
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / steps
        d = Vector((0, math.cos(a), math.sin(a)))
        c = Vector((0, cy, cz))
        rows.append([bm.verts.new(c + d * r + Vector((x, 0, 0))) for (x, r) in
                     ((x0, r_in), (x1, r_in), (x1, r_out), (x0, r_out))])
    for A, B in zip(rows, rows[1:]):
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new([A[k], A[j], B[j], B[k]])
    bm.faces.new(rows[0][::-1])
    bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return finish_obj(name, bm, m, bevel=bevel, seg=1, angle=40)


def lathe(name, prof, m, steps=16, out=(1.0, 0.0), phase=0.0):
    """Surface of revolution about X from a profile [(x, r), ...]. `out` = (dx, dr) hint for the
    side the first segment's normal should face."""
    bm = bmesh.new()
    rings = []
    for i in range(steps):
        a = 2 * pi * (i + phase) / steps
        rings.append([bm.verts.new((x, r * math.cos(a), r * math.sin(a))) for x, r in prof])
    first = None
    for i in range(steps):
        A, B = rings[i], rings[(i + 1) % steps]
        for k in range(len(prof) - 1):
            f = bm.faces.new([A[k], A[k + 1], B[k + 1], B[k]])
            if first is None:
                first = f
    bm.normal_update()
    c = first.calc_center_median()
    radial = Vector((0, c.y, c.z)).normalized()
    hint = Vector((out[0], 0, 0)) + radial * out[1]
    if first.normal.dot(hint) < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
    return finish_obj(name, bm, m, smooth=True)


def frame_from(right, up):
    right, up = Vector(right).normalized(), Vector(up).normalized()
    nrm = right.cross(up).normalized()
    return right, up, nrm


def flat_poly(name, pts2d, origin, right, up, m, lift=0.003):
    """Flat polygon decal: 2D points in the (right, up) frame at origin, lifted along the normal."""
    r, u, nrm = frame_from(right, up)
    o = Vector(origin) + nrm * lift
    bm = bmesh.new()
    vs = [bm.verts.new(o + r * x + u * y) for x, y in pts2d]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(nrm) < 0:
        f.normal_flip()
    return finish_obj(name, bm, m, smooth=False)


_fonts = {}


def text(name, s, size, origin, right, up, m, font="Arial Rounded Bold.ttf", extrude=0.0, res=2, lift=0.004,
         spacing=1.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = extrude
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = res
    cu.space_character = spacing
    path = os.path.join(FONT_DIR, font)
    if os.path.exists(path):
        if path not in _fonts:
            _fonts[path] = bpy.data.fonts.load(path)
        cu.font = _fonts[path]
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    r, u, nrm = frame_from(right, up)
    mtx = Matrix((r, u, nrm)).transposed().to_4x4()
    mtx.translation = Vector(origin) + nrm * (lift + extrude)
    ob.matrix_world = mtx
    cu.materials.append(m)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.view_layer.objects.active
    GROUP.parts.append(ob)
    return ob


def collapse(name, group, origin=None):
    """Apply modifiers and join a group's parts into one mesh object (origin optional, world space)."""
    if os.environ.get("VEH_TRIS"):
        dg = bpy.context.evaluated_depsgraph_get()
        acc = {}
        for o in group.parts:
            k = o.name.split(".")[0]
            acc[k] = acc.get(k, 0) + sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons)
        print("TRIS", name, sorted(acc.items(), key=lambda kv: -kv[1])[:25])
    bpy.ops.object.select_all(action="DESELECT")
    for o in group.parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = group.parts[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.material_slot_remove_unused()
    if origin is not None:
        ob.data.transform(Matrix.Translation(-Vector(origin)))
        ob.location = Vector(origin)
    return ob


def join_into(target, others):
    bpy.ops.object.select_all(action="DESELECT")
    for o in others:
        o.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()
    bpy.ops.object.material_slot_remove_unused()
    return target


def empty(name, loc, rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 0.1
    e.location = loc
    e.rotation_euler = rot
    bpy.context.collection.objects.link(e)
    return e


# ================================================================= wheels
def tyre(name, R, W, rim_r, steps=18, tread="road", depth=0.014, m=None, grooves=2):
    """Tyre with outer radius R (tread included), width W, sitting on a rim of radius rim_r."""
    m = m or RUBBER
    w = W / 2
    Rc = R - (depth if tread in ("blocks", "knobs", "monster") else 0.0)
    sh = Rc - rim_r
    side = [(-0.86 * w, rim_r), (-w, rim_r + sh * 0.45), (-0.95 * w, Rc - sh * 0.16), (-0.72 * w, Rc - 0.006)]
    crown = []
    if tread == "road":
        # circumferential grooves cut straight into the profile
        gs = [(-0.34, 0.0), (0.34, 0.0)] if grooves == 2 else [(-0.42, 0), (0.0, 0), (0.42, 0)]
        crown.append((-0.6 * w, Rc))
        for g, _ in gs:
            crown += [((g - 0.07) * w, Rc), ((g - 0.045) * w, Rc - depth), ((g + 0.045) * w, Rc - depth),
                      ((g + 0.07) * w, Rc)]
        crown.append((0.6 * w, Rc))
    elif tread == "slick":
        crown = [(-0.55 * w, Rc), (0.0, Rc + 0.002), (0.55 * w, Rc)]
    else:
        crown = [(-0.5 * w, Rc), (0.0, Rc), (0.5 * w, Rc)]
    prof = side + crown + [(-x, r) for x, r in reversed(side)]
    ob = lathe(name, prof, m, steps=steps, out=(-1, 0))
    if tread in ("blocks", "knobs", "monster"):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        step = 2 * pi / steps
        groups = {}
        for f in bm.faces:
            c = f.calc_center_median()
            r = math.hypot(c.y, c.z)
            k = int(math.floor((math.atan2(c.z, c.y) % (2 * pi)) / step + 1e-4)) % steps
            if tread == "blocks":         # truck lug blocks on the shoulders, solid centre rib
                if r > Rc - sh * 0.2:
                    key = (k, 1 if c.x > 0 else -1, abs(c.x) > 0.25 * w)
                    groups.setdefault(key, []).append(f)
            elif tread == "knobs":
                if r > Rc - 0.01 and (k + (1 if c.x > 0 else 0)) % 2 == 0:
                    groups.setdefault((k, c.x > 0), []).append(f)
            else:  # monster: big staggered paddles running over the shoulder
                sidek = 1 if c.x > 0 else -1
                if r > Rc - sh * 0.45 and ((k % 2 == 0 and sidek < 0) or (k % 2 == 1 and sidek > 0)):
                    groups.setdefault((k, sidek), []).append(f)
        for key, faces in groups.items():
            ext = bmesh.ops.extrude_face_region(bm, geom=faces)
            nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
            cen = sum((v.co for v in nv), Vector()) / len(nv)
            for v in nv:
                rad = Vector((0, v.co.y, v.co.z)).normalized()
                push = rad * depth
                if abs(v.co.x) > 0.8 * w:
                    push += Vector((math.copysign(depth * 0.6, v.co.x), 0, 0))
                # shrink the block a touch around its centre so neighbours read as separate lugs
                t = Vector((0, -rad.z, rad.y))
                off = v.co - cen
                v.co = v.co - t * t.dot(off) * 0.12 + push
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data)
        bm.free()
    return ob


def rim(name, W, rim_r, style, paint, steps=16, lugs=6, cap=None):
    """Rim facing +X. styles: truck, steel, dog, race, beadlock."""
    w = W / 2
    lip_x = 0.80 * w
    if style in ("truck", "steel", "dog"):
        dish_x = 0.18 * w if style == "truck" else 0.30 * w
        prof = [(lip_x, rim_r + 0.018), (lip_x + 0.012, rim_r + 0.004), (lip_x - 0.01, rim_r - 0.008),
                (dish_x, rim_r - 0.012), (dish_x + 0.01, rim_r * 0.74), (dish_x + 0.05 * w, rim_r * 0.52),
                (dish_x + 0.16 * w, rim_r * 0.42), (dish_x + 0.2 * w, rim_r * 0.30)]
        lathe(name + "_Rim", prof, paint, steps=steps, out=(1, 0.3))
        hub_x = dish_x + 0.2 * w
        disc(name + "_Back", (-0.5 * w, 0, 0), -X, rim_r, BLACK, seg=12)
        if style == "dog":
            # chrome dog-dish hubcap
            lathe(name + "_Cap", [(hub_x - 0.01, rim_r * 0.62), (hub_x + 0.035, rim_r * 0.56),
                                  (hub_x + 0.055, rim_r * 0.36), (hub_x + 0.06, rim_r * 0.05)],
                  cap or CHROME, steps=steps, out=(1, 0.2))
        else:
            disc(name + "_HubFace", (hub_x, 0, 0), X, rim_r * 0.30, paint, seg=steps)
            cyl(name + "_Hub", (hub_x - 0.005, 0, 0), (hub_x + 0.035, 0, 0), rim_r * 0.2, cap or CHROME,
                seg=10, r1=rim_r * 0.15)
            for i in range(lugs):
                a = 2 * pi * (i + 0.5) / lugs
                p = Vector((hub_x, math.cos(a) * rim_r * 0.24, math.sin(a) * rim_r * 0.24))
                cyl("Lug", p, p + X * 0.016, 0.009, CHROME, seg=5, caps=(False, True), r1=0.007)
            if style == "truck":
                for i in range(lugs):  # hand holes in the dish
                    a = 2 * pi * i / lugs
                    disc("HandHole", (dish_x + 0.03 * w, math.cos(a) * rim_r * 0.6, math.sin(a) * rim_r * 0.6),
                         X, rim_r * 0.1, BLACK, seg=6)
    elif style in ("race", "beadlock"):
        dish_x = 0.25 * w if style == "race" else 0.05 * w
        prof = [(lip_x, rim_r + 0.014), (lip_x + 0.01, rim_r + 0.002), (lip_x - 0.01, rim_r - 0.008),
                (dish_x, rim_r - 0.01), (dish_x, rim_r * 0.3)]
        lathe(name + "_Rim", prof, paint if style == "race" else BLACK, steps=steps, out=(1, 0.3))
        disc(name + "_Back", (-0.5 * w, 0, 0), -X, rim_r, BLACK, seg=12)
        n = 6 if style == "race" else 5
        for i in range(n):  # spokes
            a = 2 * pi * i / n
            q = Euler((a, 0, 0)).to_matrix()
            sw = 0.11 * rim_r if style == "race" else 0.2 * rim_r
            for t in (-1, 1) if style == "race" else (0,):
                q2 = Euler((a + t * 0.16, 0, 0)).to_matrix()
                beam("Spoke", Vector((dish_x + 0.02, 0, 0)) + q @ Vector((0, 0, rim_r * 0.22)),
                     Vector((dish_x + 0.005, 0, 0)) + q2 @ Vector((0, 0, rim_r * 0.96)),
                     sw, 0.02, paint, side=q @ Vector((0, 1, 0)), bevel=0.0)
        cyl(name + "_Hub", (dish_x, 0, 0), (dish_x + 0.04, 0, 0), rim_r * 0.26, paint, seg=12, r1=rim_r * 0.2)
        cyl(name + "_Nut", (dish_x + 0.04, 0, 0), (dish_x + 0.065, 0, 0), rim_r * 0.12, cap or CHROME, seg=6)
        if style == "beadlock":
            ring(name + "_Beadlock", (lip_x + 0.008, 0, 0), X, rim_r * 0.84, rim_r + 0.02, 0.024, CHROME, seg=steps,
                 sides=(0, 1, 2))
            for i in range(12):
                a = 2 * pi * i / 12
                bolt((lip_x + 0.02, math.cos(a) * rim_r * 0.92, math.sin(a) * rim_r * 0.92), X, r=0.013)


def build_wheel(name, R, W, rim_r, tread, rim_style, rim_paint, right, steps=18, rim_steps=16, depth=0.014,
                lugs=6, cap=None, tyre_m=None, grooves=2, extra=None):
    new_group()
    tyre(name + "_Tyre", R, W, rim_r, steps=steps, tread=tread, depth=depth, m=tyre_m, grooves=grooves)
    rim(name, W, rim_r, rim_style, rim_paint, steps=rim_steps, lugs=lugs, cap=cap)
    if extra:
        extra(name, W, rim_r)
    for o in GROUP.parts:
        if right:
            o.data.transform(Euler((0, 0, pi)).to_matrix().to_4x4())
    ob = collapse(name, GROUP)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40), keep_sharp_edges=True)
    return ob


def place_wheels(specs, **kw):
    """specs: [(name, x, y, z)]; right-hand wheels (x < 0) get mirrored."""
    out = []
    for name, x, y, z in specs:
        w = build_wheel(name, right=x < 0, **kw)
        w.location = (x, y, z)
        out.append(w)
    return out


def build_steering(hub, axis, R=0.075, rim_m=None, spoke_m=None, spokes=3):
    new_group()
    bm = bmesh.new()
    r, seg_a, seg_b = 0.013 * R / 0.075, 14, 5
    rows = []
    for i in range(seg_a):
        a = 2 * pi * i / seg_a
        c = Vector((math.cos(a) * R, math.sin(a) * R, 0))
        out = Vector((math.cos(a), math.sin(a), 0))
        rows.append([bm.verts.new(c + out * math.cos(2 * pi * j / seg_b) * r +
                                  Z * math.sin(2 * pi * j / seg_b) * r) for j in range(seg_b)])
    for i in range(seg_a):
        for j in range(seg_b):
            bm.faces.new([rows[i][j], rows[(i + 1) % seg_a][j], rows[(i + 1) % seg_a][(j + 1) % seg_b],
                          rows[i][(j + 1) % seg_b]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    finish_obj("Rim", bm, rim_m or BLACK)
    angs = (90, 210, 330) if spokes == 3 else (0, 90, 180, 270) if spokes == 4 else (0, 180, 270)
    for a in angs:
        q = Euler((0, 0, math.radians(a))).to_matrix()
        box("Spoke", q @ Vector((R * 0.53, 0, 0)), (R * 0.93, 0.018, 0.01), spoke_m or METAL, bevel=0.0, rot=(0, 0, a))
    cyl("Hub", (0, 0, -0.012), (0, 0, 0.018), 0.026 * max(1.0, R / 0.075), CHROME, seg=8)
    ob = collapse("Steering", GROUP)
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Z.rotation_difference(Vector(axis).normalized())
    ob.location = Vector(hub)
    return ob


def seat_block(c, w, d, m, back_h=0.24, cushion_t=0.07, tilt=-12, bolster=True, base_m=None, base_h=0.0):
    """Bucket seat; c = top-centre of the cushion."""
    c = Vector(c)
    if base_h > 0:
        box("SeatBase", c + Vector((0, 0.02, -cushion_t - base_h / 2)), (w * 0.75, d * 0.8, base_h), base_m or BLACK,
            bevel=0.01, seg=1)
    box("Cushion", c + Vector((0, 0, -cushion_t / 2)), (w, d, cushion_t), m, bevel=0.022, seg=2)
    box("SeatBack", c + Vector((0, d / 2 + 0.02, back_h / 2 - 0.01)), (w * 1.02, 0.07, back_h), m, bevel=0.025, seg=2,
        rot=(tilt, 0, 0))
    if bolster:
        for s in (-1, 1):
            box("Bolster", c + Vector((s * (w / 2 + 0.01), 0.06, 0.03)), (0.045, d * 0.8, 0.1), m, bevel=0.012, seg=1)


# ================================================================= weathering
def project_patches(body, specs, seed=3):
    """specs: [(origin, dir, size, aspect, spin, material)] - patches projected onto the body."""
    rnd = random.Random(seed)
    new_group()
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    for (o, d, size, aspect, spin, m) in specs:
        hit, nrm, _, _ = bvh.ray_cast(Vector(o), Vector(d).normalized())
        if hit is None:
            continue
        ref = Z if abs(nrm.z) < 0.9 else X
        u = nrm.cross(ref).normalized()
        v = nrm.cross(u).normalized()
        q = Quaternion(nrm, spin)
        u, v = q @ u, q @ v
        bm = bmesh.new()

        def project(p):
            h = bvh.ray_cast(p + nrm * 0.05, -nrm, 0.12)
            if h[0] is None or h[1].dot(nrm) < 0.5:
                return None
            return h[0] + h[1] * 0.0035
        centre = bm.verts.new(project(hit) or hit + nrm * 0.0035)
        rim_ = []
        n = 10
        for i in range(n):
            a = 2 * pi * i / n
            rr = size * (0.55 + 0.45 * rnd.random())
            p = project(hit + u * math.cos(a) * rr * aspect + v * math.sin(a) * rr)
            if p is not None:
                rim_.append(bm.verts.new(p))
        if len(rim_) < 5:
            bm.free()
            continue
        for a, b in zip(rim_, rim_[1:] + rim_[:1]):
            f = bm.faces.new([centre, a, b])
            f.normal_update()
            if f.normal.dot(nrm) < 0:
                f.normal_flip()
        finish_obj("Patch", bm, m, smooth=False)
    if GROUP.parts:
        spots = collapse("Patches", GROUP)
        join_into(body, [spots])


def weather(body, n, seed, palette, allowed, zone=None, bottom_bias=1.0, sides=("x",), size=(0.03, 0.07)):
    """Scatter n patches over painted surfaces. palette: [(material, weight, aspect_range)];
    allowed: material names a patch may land on; zone: (lo, hi) corners limiting ray origins."""
    rnd = random.Random(seed)
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for c in body.bound_box:
        lo = Vector(map(min, lo, Vector(c)))
        hi = Vector(map(max, hi, Vector(c)))
    if zone:
        lo = Vector(map(max, lo, Vector(zone[0])))
        hi = Vector(map(min, hi, Vector(zone[1])))
    me = body.data
    specs = []
    tries = 0
    tot = sum(p[1] for p in palette)
    while len(specs) < n and tries < n * 40:
        tries += 1
        axis = rnd.choice(sides)
        t = rnd.random() ** bottom_bias
        if axis == "x":
            s = rnd.choice((-1, 1))
            o = Vector((s * (hi.x + 0.3), rnd.uniform(lo.y, hi.y), lo.z + (hi.z - lo.z) * t))
            d = Vector((-s, 0, 0))
        elif axis == "y":
            s = rnd.choice((-1, 1))
            o = Vector((rnd.uniform(lo.x, hi.x), s * 3.0, lo.z + (hi.z - lo.z) * t))
            d = Vector((0, -s, 0))
        else:
            o = Vector((rnd.uniform(lo.x, hi.x), rnd.uniform(lo.y, hi.y), hi.z + 0.3))
            d = Vector((0, 0, -1))
        hit, nrm, idx, _ = bvh.ray_cast(o, d)
        if hit is None or nrm.dot(-d) < 0.75:
            continue
        mi = me.polygons[idx].material_index
        if me.materials[mi].name not in allowed:
            continue
        r = rnd.random() * tot
        for m, wgt, asp in palette:
            r -= wgt
            if r <= 0:
                break
        aspect = rnd.uniform(*asp)
        spin = 0.0 if axis != "z" else rnd.uniform(0, pi)
        if axis == "x":
            spin = rnd.uniform(-0.25, 0.25) + (pi / 2)
        specs.append((o, d, rnd.uniform(*size), aspect, spin, m))
    project_patches(body, specs, seed)


# ================================================================= export + renders
def godot(v):
    return (round(v[0], 3), round(v[2], 3), round(-v[1], 3))


def world_bbox(objs):
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def export(name, objs, info):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, name + ".glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True)
    dg = bpy.context.evaluated_depsgraph_get()
    tris = {o.name: sum(len(p.vertices) - 2 for p in o.evaluated_get(dg).data.polygons) for o in objs if o.type == "MESH"}
    lo, hi = world_bbox(objs)
    print("=" * 70)
    print("EXPORTED %s.glb" % name, tris, "TOTAL TRIS", sum(tris.values()))
    glo, ghi = godot(lo), godot(hi)
    print("BBOX godot x[%.3f, %.3f] y[%.3f, %.3f] z[%.3f, %.3f]  size %.3f x %.3f x %.3f" % (
        lo.x, hi.x, lo.z, hi.z, -hi.y, -lo.y, hi.x - lo.x, hi.z - lo.z, hi.y - lo.y))
    for o in objs:
        print("NODE", o.name, o.type, "godot", godot(o.location))
    for k, v in info.items():
        print("INFO", k, v)
    print("MATERIALS", sorted({s.material.name for o in objs if o.type == "MESH" for s in o.material_slots}))


def setup_render(samples):
    scn = bpy.context.scene
    scn.render.engine = "CYCLES"
    scn.cycles.samples = samples
    scn.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scn.cycles.device = "GPU"
    except Exception as e:  # noqa
        print("GPU unavailable", e)
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scn.render.film_transparent = True
    if not scn.world:
        world = bpy.data.worlds.new("Studio")
        scn.world = world
        bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
        bg.inputs["Color"].default_value = (0.62, 0.7, 0.82, 1)
        bg.inputs["Strength"].default_value = 0.55
    if "ShadowCatcher" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
        floor = bpy.context.active_object
        floor.name = "ShadowCatcher"
        floor.is_shadow_catcher = True


BUGGY_DIR = Vector((2.55, -3.25, 1.75)) - Vector((0.0, -0.1, 0.45))


def frame_camera(objs, direction, lens, fill=0.86, res=(512, 512)):
    lo, hi = world_bbox(objs)
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (max(lo.z, 0.0), hi.z)]
    f = -Vector(direction).normalized()
    r = f.cross(Z).normalized()
    u = r.cross(f)
    aspect = res[0] / res[1]
    th = 18.0 / lens  # tan(half fov) along the 36mm sensor width
    thx, thy = (th, th / aspect) if aspect >= 1 else (th * aspect, th)
    target = (lo + hi) / 2
    for _ in range(4):
        def fits(D):
            cam = target - f * D
            return all(abs((p - cam).dot(r)) / max((p - cam).dot(f), 1e-3) <= thx * fill and
                       abs((p - cam).dot(u)) / max((p - cam).dot(f), 1e-3) <= thy * fill for p in corners)
        a, b = 0.5, 40.0
        for _ in range(40):
            mid = (a + b) / 2
            if fits(mid):
                b = mid
            else:
                a = mid
        D = b
        cam = target - f * D
        xs = [(p - cam).dot(r) / (p - cam).dot(f) for p in corners]
        ys = [(p - cam).dot(u) / (p - cam).dot(f) for p in corners]
        target = target + r * ((max(xs) + min(xs)) / 2) * D + u * ((max(ys) + min(ys)) / 2) * D
    return target - f * D, target


def shoot(objs, path, direction=BUGGY_DIR, lens=57, samples=96, res=(512, 512), fill=0.86, ortho=False):
    scn = bpy.context.scene
    setup_render(samples)
    scn.render.resolution_x, scn.render.resolution_y = res
    for o in [o for o in bpy.data.objects if o.name.startswith("_rig")]:
        bpy.data.objects.remove(o, do_unlink=True)
    lo, hi = world_bbox(objs)
    size = (hi - lo).length / 2.6
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0.4 * size))
    for loc, energy, sz, col in [((3.4, -2.2, 3.8), 320, 2.5, (1, 0.95, 0.88)),
                                 ((-2.5, -3.5, 1.6), 110, 3.0, (0.8, 0.88, 1.0)),
                                 ((0.5, 3.5, 2.8), 260, 2.0, (1, 0.95, 0.9))]:
        ld = bpy.data.lights.new("_rigL", "AREA")
        ld.energy = energy * size * size
        ld.size = sz * size
        ld.color = col
        lt = bpy.data.objects.new("_rigLight", ld)
        bpy.context.collection.objects.link(lt)
        lt.location = centre + Vector(loc) * size
        lt.rotation_euler = (centre - lt.location).to_track_quat("-Z", "Y").to_euler()
    cd = bpy.data.cameras.new("_rigC")
    cam = bpy.data.objects.new("_rigCam", cd)
    bpy.context.collection.objects.link(cam)
    cd.lens = lens
    loc, target = frame_camera(objs, direction, lens, fill, res)
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    scn.camera = cam
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


def add_figure(seat_loc):
    """Preview-only: the kid figure posed as vehicle.gd poses the driver."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "assets", "characters", "kid.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    origin = Vector(seat_loc) + Vector((0, 0, -0.094))
    S = Matrix.Translation(origin) @ Matrix.Scale(0.55, 4)
    roots = [o for o in new if o.parent is None]
    for o in roots:
        o.matrix_world = S @ o.matrix_world
    bpy.context.view_layer.update()
    for o in new:
        for part, ang in (("LegL", -1.45), ("LegR", -1.45), ("ArmL", -1.2), ("ArmR", -1.2)):
            if o.name.startswith(part):
                p = o.matrix_world.translation.copy()
                o.matrix_world = Matrix.Translation(p) @ Matrix.Rotation(ang, 4, "X") @ Matrix.Translation(-p) @ o.matrix_world
    return [o for o in new if o.type == "MESH"]


def renders(name, objs, seat_loc):
    if os.environ.get("VEH_NO_RENDER") != "1":
        shoot(objs, os.path.join(OUT, name + ".png"))
    if PREVIEW:
        os.makedirs(PREVIEW, exist_ok=True)
        fig = add_figure(seat_loc)
        allo = objs + fig
        shoot(allo, os.path.join(PREVIEW, name + "_34.png"), samples=32, res=(900, 700), fill=0.9)
        shoot(allo, os.path.join(PREVIEW, name + "_side.png"), direction=(1, 0, 0.12), lens=90, samples=24,
              res=(1000, 560), fill=0.94)
        shoot(allo, os.path.join(PREVIEW, name + "_rear.png"), direction=(-1.6, 2.4, 1.3), lens=57, samples=24,
              res=(800, 640), fill=0.9)
        shoot(allo, os.path.join(PREVIEW, name + "_front.png"), direction=(-0.9, -3.0, 0.9), lens=57, samples=24,
              res=(800, 640), fill=0.9)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats.clear()
    _fonts.clear()
    common_mats()


# ================================================================= 1. FIRE TRUCK
def maltese(scale=1.0):
    """Maltese-cross outline (2D, centred), arms flaring outward with notched ends."""
    pts = []
    for k in range(4):
        a = k * pi / 2
        arm = [(0.10, 0.0), (0.42, -0.30), (0.34, 0.0), (0.42, 0.30)]
        for (rx, ry) in arm:
            x = rx * math.cos(a) - ry * math.sin(a)
            y = rx * math.sin(a) + ry * math.cos(a)
            pts.append((x * scale, y * scale))
    return pts


def build_fire_truck():
    PAINT = mat("Paint", "c8141c", 0.3, coat=0.7)
    WHITE = mat("White", "f3f1ea", 0.35, coat=0.5)
    GOLD = mat("Gold", "e6b33a", 0.25, metal=1.0)
    HOSE = mat("Hose", "e9c23c", 0.7)
    STRIPE = mat("Stripe", "f6f3e8", 0.3)
    GAUGE = mat("Gauge", "f4f1e6", 0.3)

    WR = 0.30
    FY, RY = -0.92, 0.80
    FT, RT = 0.44, 0.42
    CAB_F, CAB_R = -1.42, -0.46
    HW = 0.52            # cab half width
    BW = 0.505           # body half width
    BELT, ROOF0, ROOF1 = 0.86, 1.28, 1.35
    FLOOR = 0.66
    SEAT = Vector((0.24, -0.80, 0.745))
    STEER = SEAT + Vector((0, -0.29, 0.10))
    STEER_AX = Vector((0, 0.5, 0.866))
    BODY_TOP = 1.10
    PIVOT = Vector((0.0, -0.30, 1.40))
    AIM = Vector((0, -math.cos(math.radians(28)), math.sin(math.radians(28))))
    NOZ = PIVOT + AIM * 0.44
    LB = Vector((0.0, -1.24, ROOF1))

    new_group()
    # ---------- chassis
    for s in (-1, 1):
        bbox("Rail", (s * 0.34, -1.40, 0.17), (s * 0.24, 1.46, 0.29), BLACK, bevel=0.01, seg=1)
    cyl("AxleF", (-FT, FY, WR), (FT, FY, WR), 0.045, BLACK, seg=8)
    cyl("AxleR", (-RT, RY, WR), (RT, RY, WR), 0.06, BLACK, seg=8)
    cyl("Diff", (0, RY - 0.08, WR), (0, RY + 0.08, WR), 0.1, METAL, seg=10)
    # fuel tank + battery box under the pump module, either side
    cyl("FuelTank", (0.36, -0.42, 0.25), (0.36, 0.02, 0.25), 0.09, ALU, seg=12, bevel=0.0)
    for y in (-0.36, -0.04):
        ring("TankStrap", (0.36, y, 0.25), Y, 0.09, 0.1, 0.02, BLACK, seg=12, sides=(0,))

    # ---------- cab: hollow tub with big open side windows
    zb = 0.26
    prof = [(CAB_F, zb)] + arch(FY, WR, 0.365, zb, 8) + [(CAB_R, zb), (CAB_R, BELT), (CAB_F + 0.01, BELT)]
    for s in (-1, 1):
        prism("CabSide", prof, s * (HW - 0.05), s * HW, PAINT, bevel=0.02, seg=2)
        arc_band("FenderLip", FY, WR, 0.365, 0.395, s * (HW - 0.01), s * (HW + 0.03), BLACK, a0=0.05, a1=pi - 0.05,
                 steps=8)
        # door seam, handle, step
        beam("DoorSeam", (s * (HW + 0.002), -0.52, 0.30), (s * (HW + 0.002), -0.52, BELT - 0.01), 0.004, 0.008, BLACK,
             side=Y, bevel=0)
        box("DoorHandle", (s * (HW + 0.01), -0.6, BELT - 0.06), (0.02, 0.09, 0.022), CHROME, bevel=0.006, seg=1)
        bbox("CabStep", (s * (HW - 0.06), -0.56, 0.21), (s * (HW + 0.03), -0.46, 0.25), ALU, bevel=0.006, seg=1)
        # gold Maltese cross on the door
        flat_poly("Cross", maltese(0.17), (s * HW, -0.82, 0.50), (0, -s, 0), Z, GOLD)
        flat_poly("CrossIn", maltese(0.12), (s * HW, -0.82, 0.50), (0, -s, 0), Z, PAINT, lift=0.005)
        text("Num", "7", 0.075, (s * HW, -0.82, 0.50), (0, -s, 0), Z, GOLD, font="Arial Black.ttf", lift=0.006)
        # reflective stripe along the cab
        bbox("CabStripe", (min(s * HW, s * (HW + 0.005)), -1.27, 0.73), (max(s * HW, s * (HW + 0.005)), -0.47, 0.77),
             STRIPE, bevel=0.0)
    # front wall + grille, floor, rear wall
    bbox("CabFront", (-HW, CAB_F, zb), (HW, CAB_F + 0.06, BELT), PAINT, bevel=0.025, seg=2)
    bbox("CabFloor", (-HW + 0.04, CAB_F + 0.05, FLOOR - 0.04), (HW - 0.04, CAB_R, FLOOR), BLACK, bevel=0.0)
    bbox("CabBack", (-HW, CAB_R - 0.05, zb), (HW, CAB_R, ROOF0 + 0.01), PAINT, bevel=0.02, seg=1)
    bbox("Dash", (-HW + 0.05, CAB_F + 0.05, BELT - 0.14), (HW - 0.05, CAB_F + 0.17, BELT + 0.02), BLACK, bevel=0.02,
         seg=1)
    for gx in (0.16, 0.30):
        disc("Gauge", (gx, CAB_F + 0.171, BELT - 0.04), Y, 0.026, GAUGE, seg=8)
    bbox("Doghouse", (-0.1, CAB_F + 0.15, FLOOR - 0.01), (0.1, -0.75, FLOOR + 0.12), PAINT, bevel=0.02, seg=1)
    # windshield: raked pillars, split glass, rubber surround
    wb, wt = CAB_F + 0.02, CAB_F + 0.10
    for s in (-1, 1):
        beam("APillar", (s * (HW - 0.03), wb, BELT), (s * (HW - 0.03), wt, ROOF0), 0.06, 0.06, PAINT, bevel=0.012)
        beam("BPillar", (s * (HW - 0.03), CAB_R - 0.03, BELT), (s * (HW - 0.03), CAB_R - 0.03, ROOF0), 0.06, 0.06,
             PAINT, bevel=0.012)
        # glass pane each side of the centre post
        glass = [(s * 0.02, wb + 0.01, BELT + 0.02), (s * (HW - 0.06), wb + 0.01, BELT + 0.02),
                 (s * (HW - 0.06), wt + 0.01, ROOF0 - 0.02), (s * 0.02, wt + 0.01, ROOF0 - 0.02)]
        bm = bmesh.new()
        bm.faces.new([bm.verts.new(p) for p in glass])
        finish_obj("Windshield", bm, WINDOW, smooth=False)
        # big west-coast mirror on an arm
        tube("MirrorArm", [(s * (HW - 0.01), wb + 0.02, BELT + 0.04), (s * (HW + 0.1), wb - 0.02, BELT + 0.04),
                           (s * (HW + 0.1), wb - 0.02, BELT + 0.3)], 0.01, CHROME, sides=6, rad=0.04, n=2)
        box("Mirror", (s * (HW + 0.11), wb - 0.03, BELT + 0.17), (0.03, 0.08, 0.2), BLACK, bevel=0.01, seg=1)
        box("MirrorGlass", (s * (HW + 0.11), wb - 0.05, BELT + 0.17), (0.022, 0.012, 0.18), CHROME, bevel=0.0)
    beam("CentrePost", (0, wb, BELT), (0, wt, ROOF0), 0.03, 0.03, BLACK, bevel=0.006)
    beam("Cowl", (-HW + 0.03, wb, BELT), (HW - 0.03, wb, BELT), 0.05, 0.05, BLACK, side=Z, bevel=0.01)
    # roof: white, overhanging visor
    shaped_box("Roof", lambda sx, sy, sz: (sx * (HW + 0.01), (CAB_F + 0.06 if sz > 0 else CAB_F + 0.08) if sy < 0
               else CAB_R + 0.01, ROOF0 if sz < 0 else ROOF1), WHITE, bevel=0.035, seg=3)
    # roof marker lights + air horns
    for x in (-0.3, -0.15, 0.15, 0.3):
        box("Marker", (x, CAB_F + 0.075, ROOF1 - 0.03), (0.05, 0.02, 0.025), AMBER, bevel=0.005, seg=1)
    for s in (-1, 1):
        cyl("Horn", (s * 0.34, -0.62, ROOF1 + 0.04), (s * 0.34, -0.95, ROOF1 + 0.04), 0.022, CHROME, seg=8,
            r1=0.05, caps=(True, False))
        box("HornMount", (s * 0.34, -0.7, ROOF1 + 0.015), (0.03, 0.06, 0.03), BLACK, bevel=0.0)

    # ---------- interior: seats, column
    seat_block(SEAT, 0.28, 0.26, SEATM, back_h=0.36, tilt=-6, base_h=SEAT.z - 0.07 - FLOOR, base_m=BLACK)
    seat_block(Vector((-SEAT.x, SEAT.y, SEAT.z)), 0.28, 0.26, SEATM, back_h=0.36, tilt=-6,
               base_h=SEAT.z - 0.07 - FLOOR, base_m=BLACK)
    col_end = STEER - STEER_AX * 0.03
    cyl("Column", col_end - STEER_AX * 0.3, col_end, 0.02, BLACK, seg=6, caps=(False, True))

    # ---------- front: grille, lights, bumper
    gy = CAB_F - 0.004
    bbox("GrilleSurround", (-0.27, gy - 0.02, 0.38), (0.27, gy + 0.01, 0.80), CHROME, bevel=0.015, seg=2)
    bbox("GrilleBack", (-0.23, gy - 0.025, 0.42), (0.23, gy - 0.01, 0.76), BLACK, bevel=0.0)
    for i in range(7):
        z = 0.44 + i * 0.05
        bbox("GrilleBar", (-0.23, gy - 0.03, z), (0.23, gy - 0.02, z + 0.016), CHROME, bevel=0.0)
    for s in (-1, 1):
        x = s * 0.40
        bbox("LampBox", (x - 0.09, gy - 0.02, 0.46), (x + 0.09, gy + 0.01, 0.76), CHROME, bevel=0.012, seg=1)
        for z in (0.53, 0.68):
            cyl("Lamp", (x, gy - 0.02, z), (x, gy - 0.035, z), 0.05, HEADLIGHT, seg=10, r1=0.042, caps=(False, True))
        box("Turn", (x, gy - 0.02, 0.41), (0.12, 0.03, 0.04), AMBER, bevel=0.006, seg=1)
        # emergency flashers in the bumper face
        cyl("BumperLamp", (s * 0.47, CAB_F - 0.1, 0.27), (s * 0.47, CAB_F - 0.12, 0.27), 0.03, TAILLIGHT, seg=8,
            caps=(False, True))
        tube("TowHook", [(s * 0.2, CAB_F - 0.08, 0.2), (s * 0.2, CAB_F - 0.14, 0.2), (s * 0.2, CAB_F - 0.14, 0.26)],
             0.016, PAINT, sides=6, rad=0.03, n=2)
    shaped_box("Bumper", lambda sx, sy, sz: (sx * (0.56 if sy > 0 else 0.53), CAB_F - (0.12 if sy < 0 else 0.0),
                                             0.17 if sz < 0 else 0.35), CHROME, bevel=0.03, seg=2)
    text("FrontText", "FIRE RESCUE", 0.06, (0, CAB_F - 0.001, 0.835), (-1, 0, 0), Z, GOLD, font="Arial Black.ttf",
         lift=0.004)

    # ---------- pump module: chrome control panels with gauges and valves
    PM0, PM1 = CAB_R, -0.20
    bbox("PumpHouse", (-BW, PM0, 0.28), (BW, PM1, BODY_TOP), PAINT, bevel=0.02, seg=2)
    for s in (-1, 1):
        x = s * BW
        bbox("PumpPanel", (x - 0.012 if s > 0 else x - 0.006, PM0 + 0.03, 0.36),
             (x + 0.006 if s > 0 else x + 0.012, PM1 - 0.03, 1.02), ALU, bevel=0.006, seg=1)
        for i, (y, z, r) in enumerate([(-0.39, 0.92, 0.035), (-0.28, 0.92, 0.035), (-0.335, 0.80, 0.045)]):
            cyl("GaugeRim", (x, y, z), (x + s * 0.02, y, z), r, CHROME, seg=10, caps=(False, True))
            disc("GaugeFace", (x + s * 0.021, y, z), (s, 0, 0), r * 0.8, GAUGE, seg=10)
        for y in (-0.40, -0.27):
            cyl("Outlet", (x, y, 0.52), (x + s * 0.07, y, 0.52), 0.035, CHROME, seg=8, caps=(False, False))
            cyl("OutletCap", (x + s * 0.07, y, 0.52), (x + s * 0.09, y, 0.52), 0.045, GOLD, seg=6)
            tube("Valve", [(x + s * 0.01, y, 0.62), (x + s * 0.06, y, 0.62), (x + s * 0.06, y, 0.68)], 0.009, CHROME,
                 sides=5, rad=0.02, n=1)
            ball("ValveKnob", (x + s * 0.06, y, 0.69), 0.018, BLACK, seg=6, rings_=4)
        # crosslay hose poking out over the pump panel
        for k in range(3):
            box("Crosslay", (x + s * 0.0, -0.33, BODY_TOP + 0.035 + k * 0.035), (0.04, 0.2, 0.034), HOSE, bevel=0.012,
                seg=1)
    bbox("Crosslays", (-BW + 0.02, -0.43, BODY_TOP), (BW - 0.02, -0.23, BODY_TOP + 0.12), HOSE, bevel=0.03, seg=2)

    # ---------- body: compartments with roll-up doors, hose bed on top
    B0, B1 = PM1, 1.46
    bprof = [(B0, zb)] + arch(RY, WR, 0.375, zb, 8) + [(B1, zb), (B1, BODY_TOP), (B0, BODY_TOP)]
    prism("BodyBox", bprof, -BW, BW, PAINT, bevel=0.025, seg=2)
    for s in (-1, 1):
        arc_band("RearLip", RY, WR, 0.375, 0.405, s * (BW - 0.01), s * (BW + 0.03), BLACK, a0=0.05, a1=pi - 0.05,
                 steps=8)
        x = s * (BW + 0.004)
        for (y0, y1, z0, z1) in ((-0.16, 0.37, 0.36, 1.02), (0.44, 1.16, 0.76, 1.02), (1.22, 1.41, 0.36, 1.02)):
            bbox("Shutter", (min(x, x + s * 0.012), y0, z0), (max(x, x + s * 0.012), y1, z1), ALU, bevel=0.006, seg=1)
            nrib = max(2, int((z1 - z0) / 0.06))
            for k in range(1, nrib):
                z = z0 + (z1 - z0) * k / nrib
                bbox("Rib", (min(x, x + s * 0.02), y0 + 0.01, z - 0.004), (max(x, x + s * 0.02), y1 - 0.01, z + 0.004),
                     METAL, bevel=0.0)
            bbox("ShutterBar", (min(x, x + s * 0.03), y0 + 0.04, z0 + 0.03), (max(x, x + s * 0.03), y1 - 0.04, z0 + 0.055),
                 CHROME, bevel=0.006, seg=1)
        # white reflective stripe below the compartments
        bbox("BodyStripe", (min(s * BW, s * (BW + 0.006)), -0.19, 0.30), (max(s * BW, s * (BW + 0.006)), 0.40, 0.34),
             STRIPE, bevel=0.0)
        bbox("BodyStripe", (min(s * BW, s * (BW + 0.006)), 1.20, 0.30), (max(s * BW, s * (BW + 0.006)), 1.44, 0.34),
             STRIPE, bevel=0.0)
        # running-board step + grab rail
        bbox("SideStep", (min(s * (BW - 0.04), s * (BW + 0.06)), -0.16, 0.22), (max(s * (BW - 0.04), s * (BW + 0.06)),
                                                                                0.38, 0.27), ALU, bevel=0.006, seg=1)
        tube("GrabRail", [(s * (BW + 0.005), -0.19, 0.44), (s * (BW + 0.045), -0.19, 0.46),
                          (s * (BW + 0.045), -0.19, 0.98), (s * (BW + 0.005), -0.19, 1.0)], 0.011, CHROME, sides=6,
             rad=0.02, n=1)
    # hose bed: a low railed tray with folded yellow hose
    for s in (-1, 1):
        bbox("BedRail", (s * BW - (0.03 if s > 0 else 0), 0.50, BODY_TOP), (s * BW + (0.0 if s > 0 else 0.03), 1.46,
                                                                             BODY_TOP + 0.1), ALU, bevel=0.008, seg=1)
    for k in range(8):
        y = 0.56 + k * 0.111
        box("HoseFold", (0, y, BODY_TOP + 0.045), (0.92, 0.1, 0.09), HOSE, bevel=0.035, seg=2)
    bbox("Deck", (-BW + 0.01, -0.21, BODY_TOP), (BW - 0.01, 0.50, BODY_TOP + 0.02), ALU, bevel=0.0)

    # ---------- deck-gun riser (fixed part)
    cyl("Riser", (PIVOT.x, PIVOT.y, BODY_TOP + 0.10), (PIVOT.x, PIVOT.y, PIVOT.z - 0.05), 0.04, CHROME, seg=10)
    cyl("RiserFlange", (PIVOT.x, PIVOT.y, BODY_TOP + 0.10), (PIVOT.x, PIVOT.y, BODY_TOP + 0.13), 0.07, PAINT, seg=10)
    for s in (-1, 1):
        beam("GunStand", (s * 0.12, PIVOT.y, BODY_TOP + 0.1), (s * 0.03, PIVOT.y, PIVOT.z - 0.12), 0.03, 0.03, BLACK)

    # ---------- ladder on overhead racks
    LZ = BODY_TOP + 0.20
    for y in (-0.08, 1.30):
        for s in (-1, 1):
            beam("RackPost", (s * 0.3, y, BODY_TOP + 0.02), (s * 0.24, y, LZ - 0.02), 0.035, 0.035, BLACK, bevel=0.006)
        bbox("RackBar", (-0.32, y - 0.025, LZ - 0.035), (0.32, y + 0.025, LZ - 0.015), BLACK, bevel=0.006, seg=1)
    L0, L1 = -0.15, 1.62
    for s in (-1, 1):
        bbox("LadderRail", (s * 0.22 - 0.02, L0, LZ - 0.015), (s * 0.22 + 0.02, L1, LZ + 0.055), ALU, bevel=0.008, seg=1)
        bbox("LadderRail2", (s * 0.17 - 0.015, L0 + 0.05, LZ + 0.055), (s * 0.17 + 0.015, L1 - 0.12, LZ + 0.1), ALU,
             bevel=0.006, seg=1)
    n = 13
    for k in range(n):
        y = L0 + 0.07 + (L1 - L0 - 0.14) * k / (n - 1)
        cyl("Rung", (-0.21, y, LZ + 0.02), (0.21, y, LZ + 0.02), 0.012, ALU, seg=5, caps=(False, False))
    for k in range(n - 2):
        y = L0 + 0.13 + (L1 - L0 - 0.3) * k / (n - 3)
        cyl("Rung2", (-0.16, y, LZ + 0.08), (0.16, y, LZ + 0.08), 0.01, ALU, seg=5, caps=(False, False))

    # ---------- rear: tail lights, step, grab handles
    for s in (-1, 1):
        x = s * 0.42
        bbox("TailHousing", (x - 0.07, B1 - 0.01, 0.40), (x + 0.07, B1 + 0.02, 0.78), CHROME, bevel=0.01, seg=1)
        for z, m in ((0.72, TAILLIGHT), (0.62, AMBER), (0.52, TAILLIGHT)):
            cyl("TailLamp", (x, B1 + 0.02, z), (x, B1 + 0.035, z), 0.04, m, seg=10, caps=(False, True))
        bbox("RearStripe", (x - 0.06, B1, 0.83), (x + 0.06, B1 + 0.006, 1.0), STRIPE, bevel=0.0)
        tube("RearGrab", [(s * 0.26, B1, 0.5), (s * 0.26, B1 + 0.05, 0.52), (s * 0.26, B1 + 0.05, 0.98),
                          (s * 0.26, B1, 1.0)], 0.011, CHROME, sides=6, rad=0.02, n=1)
    bbox("RearShutter", (-0.2, B1, 0.38), (0.2, B1 + 0.012, 1.02), ALU, bevel=0.006, seg=1)
    for k in range(1, 10):
        z = 0.38 + 0.064 * k
        bbox("Rib", (-0.19, B1 + 0.01, z - 0.004), (0.19, B1 + 0.02, z + 0.004), METAL, bevel=0.0)
    bbox("TailStep", (-BW, B1 - 0.02, 0.20), (BW, B1 + 0.14, 0.27), ALU, bevel=0.01, seg=1)
    for s in (-1, 1):
        box("MudFlap", (s * RT, RY + 0.42, 0.25), (0.26, 0.015, 0.22), BLACK, bevel=0.0)

    body = collapse("Body", GROUP)
    weather(body, 26, 11, [(GRIME, 3, (2.0, 4.0)), (RUST, 1, (1.0, 1.8))], {"Paint", "White"}, bottom_bias=2.6,
            sides=("x", "x", "y"), size=(0.025, 0.06))

    # ---------- LightBar (separate, origin at its base centre)
    new_group()
    shaped_box("LBBase", lambda sx, sy, sz: (sx * (0.42 if sz < 0 else 0.4), LB.y + sy * 0.07, LB.z + (0.012 if sz < 0 else 0.03)),
               BLACK, bevel=0.01, seg=1)
    for s in (-1, 1):
        box("LBFoot", (s * 0.3, LB.y, LB.z + 0.006), (0.06, 0.1, 0.012), BLACK, bevel=0.0)
    for i in range(6):
        x0 = -0.4 + i * (0.8 / 6)
        m = mat("SirenRed", "ff1a1a", 0.15, emit="ff0d0d", emit_strength=4.0) if i < 3 else \
            mat("SirenBlue", "2a5bff", 0.15, emit="1f4dff", emit_strength=4.0)
        shaped_box("Lens", lambda sx, sy, sz, x0=x0: (x0 + (0.005 if sx < 0 else 0.8 / 6 - 0.005), LB.y + sy * 0.064,
                                                      LB.z + (0.03 if sz < 0 else 0.09)), m, bevel=0.018, seg=2)
    lightbar = collapse("LightBar", GROUP, origin=LB)

    # ---------- Cannon (deck gun) - origin at the swivel pivot, aimed forward + up
    new_group()
    ball("Swivel", PIVOT, 0.055, CHROME, seg=10, rings_=6)
    cyl("Yoke", PIVOT - Z * 0.05, PIVOT - Z * 0.09, 0.07, PAINT, seg=10)
    side = AIM.cross(X).normalized()  # 'up' across the barrel
    cyl("Barrel", PIVOT + AIM * 0.04, PIVOT + AIM * 0.28, 0.035, PAINT, seg=10)
    ring("BarrelBand", PIVOT + AIM * 0.27, AIM, 0.03, 0.045, 0.03, CHROME, seg=10, sides=(0, 1, 3))
    cyl("Tip", PIVOT + AIM * 0.28, PIVOT + AIM * 0.40, 0.04, CHROME, seg=10, r1=0.026, caps=(False, False))
    ring("TipRing", PIVOT + AIM * 0.42, AIM, 0.02, 0.034, 0.04, BLACK, seg=10)
    for s in (-1, 1):
        tube("Handle", [PIVOT + AIM * 0.10 + X * s * 0.03, PIVOT + AIM * 0.02 + X * s * 0.1 - side * 0.02,
                        PIVOT - AIM * 0.12 + X * s * 0.1 - side * 0.05], 0.011, BLACK, sides=6, rad=0.03, n=2)
    cannon = collapse("Cannon", GROUP, origin=PIVOT)
    nozzle = empty("Nozzle", NOZ, rot=(-math.radians(28), 0, 0))

    wheels = place_wheels([("WheelFL", FT, FY, WR), ("WheelFR", -FT, FY, WR)], R=WR, W=0.22, rim_r=0.18,
                          tread="road", rim_style="truck", rim_paint=ALU, steps=18, rim_steps=14, lugs=6, cap=PAINT)
    wheels += place_wheels([("WheelRL", RT, RY, WR), ("WheelRR", -RT, RY, WR)], R=WR, W=0.28, rim_r=0.18,
                           tread="road", rim_style="truck", rim_paint=ALU, steps=18, rim_steps=14, lugs=6, cap=PAINT,
                           grooves=3)
    steering = build_steering(STEER, STEER_AX, R=0.09)
    seat = empty("Seat", SEAT)
    objs = [body, *wheels, steering, seat, lightbar, cannon, nozzle]
    info = {"wheel_radius": WR, "Cannon pivot godot": godot(PIVOT), "Nozzle godot": godot(NOZ),
            "Nozzle aim godot (+Z local)": godot(AIM)}
    return objs, info, SEAT


VEHICLES = {
    "fire_truck": build_fire_truck,
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = [a for a in argv if a in VEHICLES] or list(VEHICLES)
    for name in names:
        reset()
        objs, info, seat = VEHICLES[name]()
        export(name, objs, info)
        renders(name, objs, seat)


if __name__ == "__main__":
    main()
